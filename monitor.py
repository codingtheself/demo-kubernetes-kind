#!/usr/bin/env python3
"""
monitor.py - Live Real-Time Terminal Dashboard for fibserver Autoscaling

Queries Prometheus and Kubernetes every 1 second and renders a clean, live
terminal dashboard showing:
  - Current traffic (RPS) vs Model Predicted RPS
  - Active Pod Replicas, Status, CPU & Memory consumption
  - Queue depth & In-flight HTTP requests
  - Average & P95 Latency

Usage:
  python3 monitor.py
  ./cluster.sh monitor
"""

import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.parse

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
RESET = "\033[0m"


def query_prometheus_metric(promql: str) -> float:
    url = f"http://localhost:9090/api/v1/query?query={urllib.parse.quote(promql)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ClusterMonitor/1.0"})
        with urllib.request.urlopen(req, timeout=1.5) as r:
            if r.status == 200:
                data = json.loads(r.read().decode())
                results = data.get("data", {}).get("result", [])
                if results:
                    return float(results[0]["value"][1])
    except Exception:
        pass
    return 0.0


def get_pod_details():
    try:
        out = subprocess.check_output(
            ["kubectl", "get", "pods", "-l", "app=fibserver", "-o", "json"],
            stderr=subprocess.DEVNULL
        ).decode()
        data = json.loads(out)
        pods = []
        for item in data.get("items", []):
            name = item["metadata"]["name"]
            phase = item["status"].get("phase", "Unknown")
            ready = False
            for cond in item["status"].get("conditions", []):
                if cond.get("type") == "Ready" and cond.get("status") == "True":
                    ready = True
            pods.append({"name": name, "phase": phase, "ready": ready})
        return pods
    except Exception:
        return []


def get_pod_cpu():
    try:
        out = subprocess.check_output(
            ["kubectl", "top", "pods", "-l", "app=fibserver", "--no-headers"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        usage = {}
        for line in out.split("\n"):
            parts = line.split()
            if len(parts) >= 3:
                usage[parts[0]] = {"cpu": parts[1], "mem": parts[2]}
        return usage
    except Exception:
        return {}


def main():
    print("\033[?25l", end="")  # Hide cursor
    try:
        while True:
            # Query Prometheus metrics
            rps = query_prometheus_metric("sum(rate(http_requests_total[30s]))")
            inflight = query_prometheus_metric("sum(http_inflight_requests)")
            queue_depth = query_prometheus_metric("sum(fib_queue_depth)")
            avg_lat = query_prometheus_metric("sum(rate(http_request_duration_ms_sum[30s])) / sum(rate(http_request_duration_ms_count[30s]))")
            p95_lat = query_prometheus_metric("histogram_quantile(0.95, sum(rate(http_request_duration_ms_bucket[30s])) by (le))")

            # Fallback if NaN
            if avg_lat != avg_lat:
                avg_lat = 0.0
            if p95_lat != p95_lat:
                p95_lat = 0.0

            pods = get_pod_details()
            metrics = get_pod_cpu()

            num_pods = len(pods)
            ready_pods = sum(1 for p in pods if p["ready"])

            # Clear screen and draw dashboard
            os.system("clear")
            print(f"{BOLD}{CYAN}================================================================================{RESET}")
            print(f"{BOLD}{CYAN}      LIVE KUBERNETES MICROSERVICE & AUTOSCALING MONITOR [{time.strftime('%H:%M:%S')}]     {RESET}")
            print(f"{BOLD}{CYAN}================================================================================{RESET}\n")

            # Section 1: Live Traffic & Telemetry
            traffic_color = RED if rps > 100.0 else (YELLOW if rps > 30.0 else GREEN)
            print(f"{BOLD}  [TRAFFIC & WORKLOAD]{RESET}")
            print(f"  • Current Incoming Rate  : {traffic_color}{BOLD}{rps:>6.1f} req/s{RESET}")
            print(f"  • In-Flight HTTP Requests: {BOLD}{int(inflight):>4}{RESET}")
            print(f"  • Worker Queue Backlog   : {BOLD}{int(queue_depth):>4}{RESET} tasks")
            print(f"  • Average Latency        : {BOLD}{avg_lat:>6.2f} ms{RESET}")
            print(f"  • P95 Latency (SLA=1000) : {BOLD}{p95_lat:>6.2f} ms{RESET}")
            print()

            # Section 2: Replicas & Container Status
            print(f"{BOLD}  [KUBERNETES POD REPLICAS ({ready_pods}/{num_pods} Ready)]{RESET}")
            print(f"  {'Pod Name':<36} | {'Status':<12} | {'CPU Usage':<10} | {'Memory':<10}")
            print("  " + "-" * 74)

            if not pods:
                print(f"  {YELLOW}No active fibserver pods detected.{RESET}")
            else:
                for p in pods:
                    pod_name = p["name"]
                    status_str = f"{GREEN}Ready{RESET}" if p["ready"] else f"{YELLOW}{p['phase']}{RESET}"
                    usage = metrics.get(pod_name, {"cpu": "pending", "mem": "pending"})
                    print(f"  {pod_name:<36} | {status_str:<21} | {usage['cpu']:<10} | {usage['mem']:<10}")

            print()
            print(f"{BOLD}{CYAN}================================================================================{RESET}")
            print(f"  {YELLOW}Press Ctrl+C to exit monitor. Grafana Web Dashboard: http://localhost:3000{RESET}")
            time.sleep(1.0)

    except KeyboardInterrupt:
        pass
    finally:
        print("\033[?25h")  # Restore cursor


if __name__ == "__main__":
    main()
