#!/usr/bin/env python3
"""
predictive_autoscaler.py

AI-Driven Predictive Autoscaler for Kubernetes Microservice (fibserver).
Implements the MAPE-K (Monitor-Analyze-Plan-Execute) architecture using:
  - Deep Learning & Classical Forecasters via model_zoo (Bi-LSTM, LSTM, GRU, Transformer, MLP, Ridge, RF)
  - Adaption Manager: Capacity-based proactive pod dimensioning with Resource Removal Strategy (RRS)
    and Cooling Down Time (CDT) based on Dang-Quang & Yoo (Applied Sciences 2021).

Formulation:
  1. Monitor: Prometheus queries sliding request arrivals: [W_{t-k}, ..., W_t]
  2. Analyze: Forecaster infers predicted arrival rate for the upcoming interval: \\hat{W}_{t+1}
  3. Plan:
       Required Replicas R_{target} = ceil( \\hat{W}_{t+1} / C_{pod} )
       - If R_{target} > R_{current}: Proactive Scale-Out (provision ahead of traffic)
       - If R_{target} < R_{current}: Cooldown Window + Conservative RRS Scale-In
  4. Execute: kubectl scale deployment fibserver --replicas=R_{target}
"""

import os
import sys

# Auto re-exec into local virtualenv if torch is not in current environment
VENV_PYTHON = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    try:
        import torch  # noqa: F401
    except ImportError:
        os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)

import time
import json
import pickle
import argparse
import datetime
import subprocess
import urllib.request
import urllib.parse
from collections import deque
import numpy as np
import torch

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from model_zoo.registry import (
    get_model,
    list_available_models,
    get_default_model_filename,
)

# ANSI Color Codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
RESET = "\033[0m"


class AIWorkloadPredictor:
    """Encapsulates scaler, plug-and-play model, and sliding lookback window inference."""
    def __init__(self, model_type: str, model_path: str, scaler_path: str, lookback: int = 12, device: str = "cpu"):
        self.model_type = model_type
        self.model_path = model_path
        self.lookback = lookback
        self.device = device
        self.history = deque(maxlen=lookback)

        with open(scaler_path, "rb") as f:
            self.scaler = pickle.load(f)

        self.model = get_model(model_type, lookback=lookback, device=device)
        self.model.load(model_path)

    def update_history(self, current_rps: float):
        """Append latest measured Prometheus RPS to rolling history."""
        self.history.append(current_rps)

    def is_warmed_up(self) -> bool:
        return len(self.history) >= self.lookback

    def predict_next_workload(self, current_rps: float) -> float:
        """
        Predicts workload W_{t+1} in requests/sec for the next time interval.
        If history is still warming up, fills missing steps with current_rps.
        """
        self.update_history(current_rps)

        # Pad with current RPS if buffer not fully populated
        window = list(self.history)
        if len(window) < self.lookback:
            window = [current_rps] * (self.lookback - len(window)) + window

        # Normalize via MinMaxScaler
        arr = np.array(window).reshape(-1, 1)
        arr_norm = self.scaler.transform(arr).flatten()

        # Model inference via universal interface
        pred_norm = self.model.predict_step(arr_norm)

        # Inverse transform to get predicted requests/sec
        pred_rps = self.scaler.inverse_transform([[pred_norm]])[0][0]
        return max(0.0, float(pred_rps))


def get_current_replicas(deployment_name: str, namespace: str = "default") -> int:
    try:
        cmd = [
            "kubectl", "get", "deployment", deployment_name,
            "-n", namespace,
            "-o", "jsonpath={.spec.replicas}"
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        return int(out) if out else 1
    except Exception:
        return 1


def scale_deployment(deployment_name: str, replicas: int, namespace: str = "default") -> bool:
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
    """Fetch current instantaneous RPS from Prometheus."""
    promql = "sum(rate(http_requests_total[30s]))"
    query_url = f"{prom_url.rstrip('/')}/api/v1/query?query={urllib.parse.quote(promql)}"

    # 1. Direct HTTP
    try:
        req = urllib.request.Request(query_url, headers={"User-Agent": "AI-Predictive-Autoscaler/2.0"})
        with urllib.request.urlopen(req, timeout=2) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                results = data.get("data", {}).get("result", [])
                if results:
                    return max(0.0, float(results[0]["value"][1]))
                return 0.0
    except Exception:
        pass

    # 2. In-cluster fallback via kubectl exec
    try:
        in_cluster_cmd = [
            "kubectl", "exec", "deploy/prometheus", "--",
            "wget", "-q", "-O", "-",
            f"http://localhost:9090/api/v1/query?query={urllib.parse.quote(promql)}"
        ]
        out = subprocess.check_output(in_cluster_cmd, stderr=subprocess.DEVNULL).decode()
        data = json.loads(out)
        results = data.get("data", {}).get("result", [])
        if results:
            return max(0.0, float(results[0]["value"][1]))
    except Exception:
        pass

    return 0.0


def check_and_warn_hpa(deployment_name: str, namespace: str = "default"):
    try:
        cmd = ["kubectl", "get", "hpa", deployment_name, "-n", namespace, "--no-headers"]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        if out:
            print(f"{YELLOW}{BOLD}[WARNING] Native HPA '{deployment_name}' is currently active!{RESET}")
            print(f"{YELLOW}To allow AI-driven predictive control without interference, run:{RESET}")
            print(f"{YELLOW}  {BOLD}kubectl delete hpa {deployment_name}{RESET}")
            print(f"{YELLOW}Restore later with: {BOLD}kubectl apply -f k8s/hpa.yaml{RESET}\n")
    except subprocess.CalledProcessError:
        pass


def main():
    parser = argparse.ArgumentParser(description="AI-Driven Predictive Autoscaler for Kubernetes (Plug-and-Play)")
    parser.add_argument(
        "--model-type",
        type=str,
        default="bilstm",
        choices=list_available_models(),
        help=f"AI model architecture to use. Available: {', '.join(list_available_models())} (default: bilstm)"
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default=None,
        help="Path to trained model weights (default: models/<model_type>_workload_model.[pt|pkl])"
    )
    parser.add_argument(
        "--scaler-path",
        type=str,
        default="models/scaler.pkl",
        help="Path to serialized MinMaxScaler"
    )
    parser.add_argument(
        "--pod-capacity",
        type=float,
        default=50.0,
        help="Single pod max throughput C_pod before SLA violation (default: 50 req/s)"
    )
    parser.add_argument(
        "--cooldown",
        type=int,
        default=45,
        help="Cooling-down time (CDT) in seconds before scaling down (default: 45)"
    )
    parser.add_argument(
        "--rrs",
        type=float,
        default=0.5,
        help="Resource Removal Strategy ratio (0.1 - 1.0) on downscale (default: 0.5)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Poll & decision loop interval in seconds (default: 5)"
    )
    parser.add_argument(
        "--min",
        type=int,
        default=1,
        help="Minimum allowed replicas (default: 1)"
    )
    parser.add_argument(
        "--max",
        type=int,
        default=8,
        help="Maximum allowed replicas (default: 8)"
    )
    parser.add_argument(
        "--target",
        type=str,
        default="fibserver",
        help="Kubernetes Deployment name"
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default="default",
        help="Kubernetes namespace"
    )
    parser.add_argument(
        "--prom-url",
        type=str,
        default="http://localhost:9090",
        help="Prometheus Base URL"
    )

    args = parser.parse_args()

    # Automatically resolve weights path if not passed explicitly
    if args.model_path is None:
        args.model_path = os.path.join("models", get_default_model_filename(args.model_type))

    print(f"\n{BOLD}{CYAN}==================================================================={RESET}")
    print(f"{BOLD}{CYAN}    AI-DRIVEN PREDICTIVE AUTOSCALER (Plug-and-Play Controller)     {RESET}")
    print(f"{BOLD}{CYAN}==================================================================={RESET}")
    print(f"  Target Deployment   : {BOLD}{args.target}{RESET}")
    print(f"  AI Model Type       : {BOLD}{args.model_type.upper()}{RESET}")
    print(f"  AI Model Weights    : {BOLD}{args.model_path}{RESET}")
    print(f"  Pod Capacity (C_pod): {BOLD}{args.pod_capacity:.1f} req/s per replica{RESET}")
    print(f"  Replica Bounds      : {BOLD}[{args.min} .. {args.max}]{RESET}")
    print(f"  Cooldown Time (CDT) : {BOLD}{args.cooldown} seconds{RESET}")
    print(f"  Resource Removal RR : {BOLD}{args.rrs * 100:.0f}% gradual decay{RESET}")
    print(f"  Control Interval    : {BOLD}{args.interval}s{RESET}")
    print(f"{CYAN}==================================================================={RESET}\n")

    check_and_warn_hpa(args.target, args.namespace)

    # Initialize AI Predictor
    try:
        predictor = AIWorkloadPredictor(
            model_type=args.model_type,
            model_path=args.model_path,
            scaler_path=args.scaler_path,
            lookback=12,
            device="cpu"
        )
        print(f"{GREEN}✓ [{args.model_type.upper()}] model successfully loaded onto CPU inference engine.{RESET}\n")
    except Exception as e:
        print(f"{RED}[FATAL] Failed to load AI model '{args.model_type}' from {args.model_path}: {e}{RESET}")
        sys.exit(1)

    cooldown_start_time = None

    try:
        while True:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            current_rps = get_prometheus_rps(args.prom_url)
            current_replicas = get_current_replicas(args.target, args.namespace)

            # --- ANALYZE: Model Forecast ---
            predicted_rps = predictor.predict_next_workload(current_rps)

            # --- PLAN: Dang-Quang & Yoo Capacity-Based Dimensioning ---
            # Desired replicas required for future workload: R = ceil( W_{t+1} / C_{pod} )
            desired_replicas = int(np.ceil(predicted_rps / args.pod_capacity))
            target_replicas = max(args.min, min(args.max, desired_replicas))

            status_color = RESET
            action_tag = "[STABLE]"

            # Decision Logic 1: PROACTIVE SCALE-OUT
            if target_replicas > current_replicas:
                cooldown_start_time = None
                scale_deployment(args.target, target_replicas, args.namespace)
                action_tag = f"{RED}{BOLD}[PROACTIVE SCALE-UP] 🚀{RESET}"
                status_color = RED
                detail = f"Predicted: {predicted_rps:.1f} RPS | Scaling {current_replicas} -> {target_replicas} pods ahead of burst"

            # Decision Logic 2: COOLDOWN & CONSERVATIVE SCALE-IN (RRS)
            elif target_replicas < current_replicas:
                if cooldown_start_time is None:
                    cooldown_start_time = time.time()
                    action_tag = f"{YELLOW}[COOLDOWN ACTIVE] ⏳{RESET}"
                    status_color = YELLOW
                    detail = f"Predicted: {predicted_rps:.1f} RPS < Cap ({current_replicas * args.pod_capacity:.0f}) | CDT 0/{args.cooldown}s"
                else:
                    elapsed = time.time() - cooldown_start_time
                    if elapsed >= args.cooldown:
                        # Cooldown expired: Apply Resource Removal Strategy (RRS)
                        surplus = current_replicas - target_replicas
                        to_remove = max(1, int(np.ceil(surplus * args.rrs)))
                        new_replicas = max(target_replicas, current_replicas - to_remove)

                        scale_deployment(args.target, new_replicas, args.namespace)
                        cooldown_start_time = time.time()  # Reset for subsequent stepped downscale
                        action_tag = f"{GREEN}{BOLD}[CONSERVATIVE SCALE-DOWN] 📉{RESET}"
                        status_color = GREEN
                        detail = f"CDT Expired ({elapsed:.0f}s) | Shedding {to_remove} surplus pods: {current_replicas} -> {new_replicas}"
                    else:
                        action_tag = f"{YELLOW}[COOLDOWN] ⏳{RESET}"
                        status_color = YELLOW
                        detail = f"Predicted: {predicted_rps:.1f} RPS | Cooling down {elapsed:.0f}/{args.cooldown}s (Holding {current_replicas} pods)"

            # Decision Logic 3: SYSTEM STABLE
            else:
                cooldown_start_time = None
                action_tag = f"{GREEN}[BALANCED] 🟢{RESET}"
                status_color = GREEN
                detail = f"Predicted: {predicted_rps:.1f} RPS matches {current_replicas} pod(s) capacity"

            # Formatted log line
            print(f"[{timestamp}] {action_tag:<32} Current: {current_rps:>5.1f} RPS | {detail}", flush=True)
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\n{BOLD}{CYAN}AI Predictive Autoscaler shut down by user. Exiting gracefully.{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
