#!/usr/bin/env python3
"""
plot_live_benchmarks.py - Visualization Engine for Live Kubernetes Benchmarks

Generates publication-quality charts from live cluster k6 test runs:
  1. live_scaling_trajectories.png: Overlaid time-series subplots comparing traffic
     surges vs autoscaler replica scaling responses for each model.
  2. live_sla_latency_comparison.png: Bar charts comparing SLA violation rates,
     P95 latency, error rates, and pod cost efficiency across all tested models.
"""

import os
import sys

# Auto re-exec into local virtualenv if dependencies are in .venv
VENV_PYTHON = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)

import json
import csv
import glob
import argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Styling
plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.labelsize": 10,
    "axes.labelweight": "bold",
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.dpi": 300,
})

MODEL_COLORS = {
    "bilstm": "#1f77b4",          # Deep Blue
    "gru": "#2ca02c",             # Emerald Green
    "lstm": "#9467bd",            # Purple
    "transformer": "#e377c2",     # Pink
    "mlp": "#8c564b",             # Brown
    "ridge": "#ff7f0e",           # Vivid Orange
    "random_forest": "#d62728",   # Crimson Red
    "baseline_static": "#7f7f7f", # Charcoal Grey
}


def plot_trajectories(data_dir: str, output_path: str):
    """Plot time-series telemetry subplots for all tested models."""
    subdirs = sorted([d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))])
    models = []
    telemetry_data = {}

    for d in subdirs:
        csv_file = os.path.join(data_dir, d, "cluster_telemetry.csv")
        if os.path.exists(csv_file):
            rows = []
            with open(csv_file, "r") as cf:
                reader = csv.DictReader(cf)
                for r in reader:
                    rows.append({
                        "elapsed_sec": float(r["elapsed_sec"]),
                        "measured_rps": float(r["measured_rps"]),
                        "spec_replicas": int(r["spec_replicas"]),
                        "ready_replicas": int(r["ready_replicas"]),
                    })
            if rows:
                models.append(d)
                telemetry_data[d] = rows

    if not models:
        print("[WARN] No cluster telemetry CSV files found to plot trajectories.")
        return

    n_models = len(models)
    fig, axes = plt.subplots(n_models, 1, figsize=(10, 2.8 * n_models), sharex=True, sharey=False)
    if n_models == 1:
        axes = [axes]

    for idx, (ax, model) in enumerate(zip(axes, models)):
        data = telemetry_data[model]
        times = [d["elapsed_sec"] for d in data]
        rps = [d["measured_rps"] for d in data]
        replicas = [d["spec_replicas"] for d in data]
        ready = [d["ready_replicas"] for d in data]

        color = MODEL_COLORS.get(model, "#333333")

        # Left Y-axis: Traffic RPS
        ax.plot(times, rps, color="#4a7ebb", linewidth=1.8, label="Traffic RPS (Prometheus)", alpha=0.9)
        ax.fill_between(times, 0, rps, color="#4a7ebb", alpha=0.15)
        ax.set_ylabel("Incoming RPS", color="#2a5a99", fontweight="bold")
        ax.tick_params(axis="y", labelcolor="#2a5a99")
        ax.set_ylim(bottom=0, top=max(250, max(rps) * 1.2 if rps else 250))

        # Right Y-axis: Pod Replicas
        ax2 = ax.twinx()
        ax2.step(times, replicas, color=color, linewidth=2.4, where="post", label=f"{model.upper()} Desired Pods")
        ax2.plot(times, ready, color=color, linestyle="--", linewidth=1.4, alpha=0.7, label=f"Ready Pods")
        ax2.set_ylabel("Pod Replicas", color=color, fontweight="bold")
        ax2.tick_params(axis="y", labelcolor=color)
        ax2.set_ylim(0, max(8, max(replicas) + 2 if replicas else 8))
        ax2.grid(False)

        # Title
        ax.set_title(f"Model: {model.upper()} | Dynamic Live Scaling Trajectory", fontsize=11, fontweight="bold", pad=6)

        # Combined Legend
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left", framealpha=0.85, fontsize=8)

    axes[-1].set_xlabel("Elapsed Time (seconds)", fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  ✓ Trajectory plot saved: {output_path}")


def plot_summary_bars(data_dir: str, output_path: str):
    """Plot bar charts for SLA violations, P95 latency, and Pod cost."""
    leaderboard_csv = os.path.join(data_dir, "live_benchmark_leaderboard.csv")
    if not os.path.exists(leaderboard_csv):
        print(f"[WARN] Leaderboard CSV not found at {leaderboard_csv}")
        return

    models = []
    sla_rates = []
    p95_lats = []
    med_lats = []
    avg_reps = []
    colors = []

    with open(leaderboard_csv, "r") as cf:
        reader = csv.DictReader(cf)
        for r in reader:
            m = r["model"]
            models.append(m.upper())
            sla_rates.append(float(r["sla_violations_pct"]))
            p95_lats.append(float(r["p95_latency_ms"]))
            med_lats.append(float(r["med_latency_ms"]))
            avg_reps.append(float(r["avg_replicas"]))
            colors.append(MODEL_COLORS.get(m, "#444444"))

    if not models:
        return

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))

    x = np.arange(len(models))
    width = 0.55

    # 1. SLA Violations Rate (%)
    axes[0].bar(x, sla_rates, width=width, color=colors, edgecolor="black", alpha=0.85)
    axes[0].set_title("SLA Violations (>1000ms) Rate [%]\n(Lower is Better)", fontweight="bold")
    axes[0].set_ylabel("Violation Rate (%)", fontweight="bold")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(models, rotation=35, ha="right", fontweight="bold")
    axes[0].set_ylim(0, max(10, max(sla_rates) * 1.25 if sla_rates else 10))
    for i, val in enumerate(sla_rates):
        axes[0].text(i, val + 0.3, f"{val:.1f}%", ha="center", va="bottom", fontsize=8.5, fontweight="bold")

    # 2. P95 Latency (ms)
    axes[1].bar(x, p95_lats, width=width, color=colors, edgecolor="black", alpha=0.85)
    axes[1].axhline(y=1000, color="red", linestyle="--", linewidth=1.5, label="1000ms SLA Threshold")
    axes[1].set_title("P95 Tail Latency [ms]\n(Lower is Better)", fontweight="bold")
    axes[1].set_ylabel("Latency (ms)", fontweight="bold")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(models, rotation=35, ha="right", fontweight="bold")
    axes[1].legend(loc="upper left", fontsize=8)
    axes[1].set_ylim(0, max(1200, max(p95_lats) * 1.25 if p95_lats else 1200))
    for i, val in enumerate(p95_lats):
        axes[1].text(i, val + 20, f"{val:.0f}ms", ha="center", va="bottom", fontsize=8.5, fontweight="bold")

    # 3. Average Provisioned Pods (Cost / Efficiency)
    axes[2].bar(x, avg_reps, width=width, color=colors, edgecolor="black", alpha=0.85)
    axes[2].set_title("Average Pods Provisioned\n(Resource Cost)", fontweight="bold")
    axes[2].set_ylabel("Average Replicas", fontweight="bold")
    axes[2].set_xticks(x)
    axes[2].set_xticklabels(models, rotation=35, ha="right", fontweight="bold")
    axes[2].set_ylim(0, max(5, max(avg_reps) * 1.3 if avg_reps else 5))
    for i, val in enumerate(avg_reps):
        axes[2].text(i, val + 0.1, f"{val:.1f}", ha="center", va="bottom", fontsize=8.5, fontweight="bold")

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  ✓ Summary bars plot saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Plot Live Kubernetes Model Benchmark Results")
    parser.add_argument("--data-dir", type=str, default="models/live_benchmarks", help="Path to live benchmarks directory")
    args = parser.parse_args()

    traj_path = os.path.join(args.data_dir, "live_scaling_trajectories.png")
    bars_path = os.path.join(args.data_dir, "live_sla_latency_comparison.png")

    print("[PLOTS] Generating live benchmark visual comparison charts...")
    plot_trajectories(args.data_dir, traj_path)
    plot_summary_bars(args.data_dir, bars_path)


if __name__ == "__main__":
    main()
