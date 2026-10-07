#!/usr/bin/env python3
"""
Custom Threshold-Based Autoscaler for fibserver Microservice.

Logic:
  - Continuously monitors Requests Per Second (RPS) via Prometheus.
  - If RPS > threshold (e.g. 100 req/s):
      Scales deployment up by 1 replica (up to --max).
      Resets cooldown timer.
  - If RPS <= threshold:
      Starts or increments a cooldown timer (default 30s).
      After 30s of sustained low traffic:
        Scales deployment down by 1 replica (down to --min).
"""

import argparse
import datetime
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def get_current_replicas(deployment_name: str, namespace: str = "default") -> int:
    """Fetch the current number of desired replicas from Kubernetes."""
    try:
        cmd = [
            "kubectl", "get", "deployment", deployment_name,
            "-n", namespace,
            "-o", "jsonpath={.spec.replicas}"
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        return int(out) if out else 1
    except Exception as e:
        print(f"{YELLOW}[WARN] Could not get replicas for {deployment_name}: {e}{RESET}")
        return 1


def scale_deployment(deployment_name: str, replicas: int, namespace: str = "default") -> bool:
    """Scale the deployment to target replicas using kubectl."""
    try:
        cmd = [
            "kubectl", "scale", "deployment", deployment_name,
            "-n", namespace,
            f"--replicas={replicas}"
        ]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError as e:
        print(f"{RED}[ERROR] Failed to scale {deployment_name} to {replicas}: {e}{RESET}")
        return False


def get_prometheus_rps(prom_url: str) -> float:
    """Query Prometheus for current RPS (requests per second over 30s window)."""
    promql = "sum(rate(http_requests_total[30s]))"
    query_url = f"{prom_url.rstrip('/')}/api/v1/query?query={urllib.parse.quote(promql)}"

    # 1. Try direct HTTP (if port-forwarding or reachable)
    try:
        req = urllib.request.Request(query_url, headers={"User-Agent": "Custom-Autoscaler/1.0"})
        with urllib.request.urlopen(req, timeout=2) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                results = data.get("data", {}).get("result", [])
                if results and len(results) > 0:
                    val = float(results[0]["value"][1])
                    return max(0.0, val)
                return 0.0
    except Exception:
        pass

    # 2. Fallback: Query directly inside cluster via kubectl exec deploy/prometheus
    try:
        in_cluster_cmd = [
            "kubectl", "exec", "deploy/prometheus", "--",
            "wget", "-q", "-O", "-",
            f"http://localhost:9090/api/v1/query?query={urllib.parse.quote(promql)}"
        ]
        out = subprocess.check_output(in_cluster_cmd, stderr=subprocess.DEVNULL).decode()
        data = json.loads(out)
        results = data.get("data", {}).get("result", [])
        if results and len(results) > 0:
            val = float(results[0]["value"][1])
            return max(0.0, val)
        return 0.0
    except Exception as e:
        # In case prometheus is temporarily unreachable
        return 0.0


def check_and_warn_hpa(deployment_name: str, namespace: str = "default"):
    """Check if native Kubernetes HPA is active and warn the user."""
    try:
        cmd = ["kubectl", "get", "hpa", deployment_name, "-n", namespace, "--no-headers"]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        if out:
            print(f"{YELLOW}{BOLD}[WARNING] Native HPA '{deployment_name}' is currently active!{RESET}")
            print(f"{YELLOW}Kubernetes HPA (CPU-based) and this script (RPS-based) may fight for control.{RESET}")
            print(f"{YELLOW}To let this custom script have exclusive control, run: {BOLD}kubectl delete hpa {deployment_name}{RESET}")
            print(f"{YELLOW}You can restore it later with: {BOLD}kubectl apply -f k8s/hpa.yaml{RESET}\n")
    except subprocess.CalledProcessError:
        pass


def main():
    parser = argparse.ArgumentParser(
        description="Custom RPS-based Autoscaler for Kubernetes Microservice"
    )
    parser.add_argument("--threshold", type=float, default=100.0,
                        help="RPS threshold to trigger scale-up (default: 100.0)")
    parser.add_argument("--cooldown", type=int, default=30,
                        help="Cooldown period in seconds before scaling down (default: 30)")
    parser.add_argument("--interval", type=int, default=3,
                        help="Poll interval in seconds (default: 3)")
    parser.add_argument("--min", type=int, default=1,
                        help="Minimum number of replicas (default: 1)")
    parser.add_argument("--max", type=int, default=5,
                        help="Maximum number of replicas (default: 5)")
    parser.add_argument("--target", type=str, default="fibserver",
                        help="Target Kubernetes Deployment name (default: fibserver)")
    parser.add_argument("--namespace", type=str, default="default",
                        help="Kubernetes namespace (default: default)")
    parser.add_argument("--prom-url", type=str, default="http://localhost:9090",
                        help="Prometheus Base URL (default: http://localhost:9090)")
    parser.add_argument("--step-down", action="store_true", default=True,
                        help="Step down by 1 replica per cooldown (default: True)")

    args = parser.parse_args()

    print(f"\n{BOLD}{CYAN}=== Custom Threshold Autoscaler Initialized ==={RESET}")
    print(f"  Target Deployment : {BOLD}{args.target}{RESET}")
    print(f"  RPS Threshold     : {BOLD}{args.threshold:.1f} req/s{RESET}")
    print(f"  Cooldown Window   : {BOLD}{args.cooldown} seconds{RESET}")
    print(f"  Replica Range     : {BOLD}[{args.min} .. {args.max}]{RESET}")
    print(f"  Poll Interval     : {BOLD}{args.interval}s{RESET}")
    print(f"  Prometheus Target : {BOLD}{args.prom_url}{RESET}")
    print(f"{CYAN}================================================={RESET}\n")

    check_and_warn_hpa(args.target, args.namespace)

    cooldown_start_time = None

    try:
        while True:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            current_rps = get_prometheus_rps(args.prom_url)
            current_replicas = get_current_replicas(args.target, args.namespace)

            # Condition 1: Traffic Spike (RPS > threshold)
            if current_rps > args.threshold:
                cooldown_start_time = None  # Cancel any pending scale-down

                if current_replicas < args.max:
                    new_replicas = current_replicas + 1
                    scale_deployment(args.target, new_replicas, args.namespace)
                    status_text = f"{RED}{BOLD}[SCALE UP] 🚀 RPS: {current_rps:.1f} > {args.threshold:.1f} | Replicas: {current_replicas} -> {new_replicas}{RESET}"
                else:
                    status_text = f"{YELLOW}[AT MAX] 🔥 RPS: {current_rps:.1f} > {args.threshold:.1f} | Max replicas ({args.max}) reached{RESET}"

            # Condition 2: Traffic Normal / Below Threshold (RPS <= threshold)
            else:
                if current_replicas > args.min:
                    if cooldown_start_time is None:
                        cooldown_start_time = time.time()
                        status_text = (
                            f"{YELLOW}[COOLDOWN] ⏳ RPS: {current_rps:.1f} <= {args.threshold:.1f} | "
                            f"Starting {args.cooldown}s cooldown (Replicas: {current_replicas}){RESET}"
                        )
                    else:
                        elapsed = time.time() - cooldown_start_time
                        if elapsed >= args.cooldown:
                            # Cooldown expired: trigger downscale
                            new_replicas = current_replicas - 1
                            scale_deployment(args.target, new_replicas, args.namespace)
                            cooldown_start_time = time.time()  # Reset for next downscale step
                            status_text = (
                                f"{GREEN}{BOLD}[SCALE DOWN] 📉 Cooldown expired ({elapsed:.1f}s >= {args.cooldown}s) | "
                                f"Replicas: {current_replicas} -> {new_replicas}{RESET}"
                            )
                        else:
                            remaining = args.cooldown - elapsed
                            status_text = (
                                f"{YELLOW}[COOLDOWN] ⏳ RPS: {current_rps:.1f} <= {args.threshold:.1f} | "
                                f"Cooling down... {elapsed:.0f}s/{args.cooldown}s (Replicas: {current_replicas}){RESET}"
                            )
                else:
                    cooldown_start_time = None
                    status_text = (
                        f"{GREEN}[STABLE] 🟢 RPS: {current_rps:.1f} <= {args.threshold:.1f} | "
                        f"At minReplicas ({args.min}){RESET}"
                    )

            print(f"[{timestamp}] {status_text}")
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\n{BOLD}{CYAN}Autoscaler stopped by user. Exiting gracefully.{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
