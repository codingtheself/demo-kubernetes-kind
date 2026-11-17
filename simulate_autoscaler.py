#!/usr/bin/env python3
"""
simulate_autoscaler.py

Offline Trace Replay & SLA Audit Simulator.
Simulates how each registered AI model would behave in a production Kubernetes
cluster when managing pod replicas under the Dang-Quang & Yoo (2021) capacity
formulation.

Evaluates:
  1. SLA Violations (%): Time steps where traffic exceeded cluster capacity.
  2. Max Traffic Deficit (RPS): Largest surge where pods fell short.
  3. Average Provisioned Pods: Mean active replicas.
  4. Over-provisioning Waste (%): Fraction of provisioned CPU/capacity left idle.
  5. Total Pod-Hours: Simulated infrastructure cost.
"""

import os
import sys

# Auto re-exec into local virtualenv if dependencies are not in current environment
VENV_PYTHON = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    try:
        import numpy  # noqa: F401
    except ImportError:
        os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)
import json
import pickle
import argparse
import numpy as np

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from model_zoo.registry import (
    get_model,
    list_available_models,
    get_default_model_filename,
)


def simulate_autoscaler_loop(
    predictions_rps: np.ndarray,
    actual_rps: np.ndarray,
    pod_capacity: float = 50.0,
    min_replicas: int = 1,
    max_replicas: int = 8,
    cooldown_steps: int = 2,  # 2 steps * 30s = 60s cooldown
    rrs: float = 0.5,
    step_duration_hours: float = 30.0 / 3600.0
):
    n_steps = len(actual_rps)
    replicas_history = np.zeros(n_steps, dtype=int)

    current_replicas = 1
    cooldown_counter = 0

    sla_violations = 0
    max_deficit = 0.0
    total_idle_capacity = 0.0
    total_provisioned_capacity = 0.0

    for t in range(n_steps):
        w_pred = predictions_rps[t]
        w_true = actual_rps[t]

        # Capacity dimensioning: R = ceil( W_{t+1} / C_pod )
        desired = int(np.ceil(w_pred / pod_capacity))
        target = max(min_replicas, min(max_replicas, desired))

        if target > current_replicas:
            # Scale-up immediately
            current_replicas = target
            cooldown_counter = 0
        elif target < current_replicas:
            # Scale-down cooldown
            cooldown_counter += 1
            if cooldown_counter >= cooldown_steps:
                surplus = current_replicas - target
                to_remove = max(1, int(np.ceil(surplus * rrs)))
                current_replicas = max(target, current_replicas - to_remove)
                cooldown_counter = 0

        replicas_history[t] = current_replicas
        cluster_capacity = current_replicas * pod_capacity
        total_provisioned_capacity += cluster_capacity

        if w_true > cluster_capacity:
            sla_violations += 1
            deficit = w_true - cluster_capacity
            if deficit > max_deficit:
                max_deficit = deficit
        else:
            total_idle_capacity += (cluster_capacity - w_true)

    sla_pct = (sla_violations / n_steps) * 100.0
    waste_pct = (total_idle_capacity / total_provisioned_capacity) * 100.0
    avg_pods = float(np.mean(replicas_history))
    pod_hours = float(np.sum(replicas_history) * step_duration_hours)

    return {
        "SLA Violation Rate (%)": round(sla_pct, 2),
        "Max Traffic Deficit (RPS)": round(float(max_deficit), 2),
        "Average Replicas": round(avg_pods, 2),
        "Capacity Waste (%)": round(waste_pct, 2),
        "Total Pod-Hours": round(pod_hours, 2),
    }


def main():
    parser = argparse.ArgumentParser(description="Offline Trace Replay & SLA Audit Simulator")
    parser.add_argument("--datadir", type=str, default="data", help="Data directory")
    parser.add_argument("--modeldir", type=str, default="models", help="Models directory")
    parser.add_argument("--pod-capacity", type=float, default=50.0, help="Per-pod capacity in RPS")
    parser.add_argument("--cooldown-steps", type=int, default=2, help="Cooldown steps before downscale (default: 2)")
    args = parser.parse_args()

    # Load test data and scaler
    test_path = os.path.join(args.datadir, "test_data.npz")
    scaler_path = os.path.join(args.modeldir, "scaler.pkl")

    if not os.path.exists(test_path) or not os.path.exists(scaler_path):
        print(f"[ERROR] Missing test data or scaler. Run prepare_alibaba_data.py first.")
        sys.exit(1)

    test_data = np.load(test_path)
    X_test, y_test = test_data["X"], test_data["y"]

    with open(scaler_path, "rb") as f:
        scaler = pickle.load(f)

    y_test_rps = scaler.inverse_transform(y_test.reshape(-1, 1)).flatten()

    print(f"\n===================================================================")
    print(f"      OFFLINE TRACE REPLAY & SLA AUDIT SIMULATOR (Dang-Quang 2021)")
    print(f"===================================================================")
    print(f"  Test Intervals     : {len(y_test_rps):,} steps (approx. 50 hours of workload)")
    print(f"  Target Pod Capacity: {args.pod_capacity:.1f} RPS per pod")
    print(f"  Downscale Cooldown : {args.cooldown_steps} steps (60s)")
    print(f"===================================================================\n")

    sim_results = {}

    # Benchmark available trained models
    for model_key in list_available_models():
        weight_file = os.path.join(args.modeldir, get_default_model_filename(model_key))
        if not os.path.exists(weight_file):
            continue

        try:
            model = get_model(model_key, lookback=X_test.shape[1])
            model.load(weight_file)

            preds_norm = model.predict_batch(X_test)
            preds_rps = scaler.inverse_transform(preds_norm.reshape(-1, 1)).flatten()

            metrics = simulate_autoscaler_loop(
                predictions_rps=preds_rps,
                actual_rps=y_test_rps,
                pod_capacity=args.pod_capacity,
                cooldown_steps=args.cooldown_steps
            )
            sim_results[model.name] = metrics
        except Exception as e:
            print(f"[WARN] Could not simulate '{model_key}': {e}")

    # Add Baselines for academic context:
    # 1. Static Over-provisioning: Always run 4 pods
    static_preds = np.full_like(y_test_rps, 4 * args.pod_capacity)
    sim_results["Static (4 Pods Always)"] = simulate_autoscaler_loop(
        predictions_rps=static_preds,
        actual_rps=y_test_rps,
        pod_capacity=args.pod_capacity
    )

    # 2. Naive Reactive Sizing: Desired pods = ceil(current_RPS / C_pod)
    reactive_preds = np.roll(y_test_rps, 1)
    reactive_preds[0] = y_test_rps[0]
    sim_results["Reactive Baseline (Lags 1 Step)"] = simulate_autoscaler_loop(
        predictions_rps=reactive_preds,
        actual_rps=y_test_rps,
        pod_capacity=args.pod_capacity
    )

    # Print Report
    print(f"{'Autoscaling Policy / Model':<32} | {'SLA Violations':<15} | {'Max Deficit':<12} | {'Avg Pods':<10} | {'Waste (%)':<10} | {'Pod-Hours':<10}")
    print("-" * 105)
    for policy, m in sim_results.items():
        row = (f"{policy:<32} | {m['SLA Violation Rate (%)']:>13.2f}% | "
               f"{m['Max Traffic Deficit (RPS)']:>8.1f} RPS | {m['Average Replicas']:>10.2f} | "
               f"{m['Capacity Waste (%)']:>9.2f}% | {m['Total Pod-Hours']:>10.2f}")
        print(row)
    print("=" * 105)

    out_json = os.path.join(args.modeldir, "simulation_results.json")
    with open(out_json, "w") as f:
        json.dump(sim_results, f, indent=2)
    print(f"\n✓ Saved simulation audit to {out_json}\n")


if __name__ == "__main__":
    main()
