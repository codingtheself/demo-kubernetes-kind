#!/usr/bin/env python3
"""
plot_model_benchmarks.py

Generates publication-quality graphical comparisons (bar graphs, multi-panel dashboards)
comparing all AI model architectures across forecasting accuracy, inference speed,
cluster SLA violations, and infrastructure cloud cost.

Outputs:
  - models/model_performance_bars.png: MAE, MAPE, Inference Latency, Model Size
  - models/cluster_sla_cost_bars.png: SLA Violations (%), Capacity Waste (%), Pod-Hours
"""

import os
import sys
import json
import numpy as np

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def generate_graphical_comparisons(
    benchmark_json: str = "models/benchmark_results.json",
    simulation_json: str = "models/simulation_results.json",
    output_dir: str = "models"
):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(benchmark_json):
        print(f"[ERROR] Missing {benchmark_json}. Run train_predictive_models.py first.")
        return

    with open(benchmark_json, "r") as f:
        bench_data = json.load(f)

    # -------------------------------------------------------------------------
    # FIGURE 1: Model Forecasting Performance & Architecture Metrics
    # -------------------------------------------------------------------------
    models = list(bench_data.keys())
    maes = [bench_data[m]["MAE (RPS)"] for m in models]
    mapes = [bench_data[m]["MAPE (%)"] for m in models]
    latencies = [bench_data[m]["Inference Latency (ms)"] for m in models]
    params = [bench_data[m]["Parameters"] for m in models]

    # Palette
    colors = ["#2ecc71", "#3498db", "#e67e22", "#9b59b6", "#1abc9c", "#e74c3c", "#34495e"]

    fig, axes = plt.subplots(2, 2, figsize=(15, 11))
    fig.suptitle("Predictive Autoscaling AI Models — Benchmark Comparison", fontsize=16, fontweight="bold", y=0.98)

    # Subplot 1: MAE (RPS)
    ax1 = axes[0, 0]
    bars1 = ax1.bar(models, maes, color=colors[:len(models)], edgecolor="black", alpha=0.85)
    ax1.set_title("Forecast Error: MAE (Requests / Second) [Lower is Better]", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Mean Absolute Error (RPS)", fontsize=11)
    ax1.set_ylim(0, max(maes) * 1.25)
    ax1.grid(axis="y", linestyle="--", alpha=0.5)
    ax1.tick_params(axis="x", rotation=25)
    for bar in bars1:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width() / 2.0, yval + 0.15, f"{yval:.2f}", ha="center", va="bottom", fontweight="bold", fontsize=10)

    # Subplot 2: MAPE (%)
    ax2 = axes[0, 1]
    bars2 = ax2.bar(models, mapes, color=colors[:len(models)], edgecolor="black", alpha=0.85)
    ax2.axhline(10.0, color="#e74c3c", linestyle="--", linewidth=1.5, label="High Accuracy Threshold (10%)")
    ax2.set_title("Relative Error: MAPE (%) [Lower is Better]", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Mean Absolute Percentage Error (%)", fontsize=11)
    ax2.set_ylim(0, max(mapes) * 1.3)
    ax2.grid(axis="y", linestyle="--", alpha=0.5)
    ax2.tick_params(axis="x", rotation=25)
    ax2.legend(loc="upper right", frameon=True)
    for bar in bars2:
        yval = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width() / 2.0, yval + 0.25, f"{yval:.2f}%", ha="center", va="bottom", fontweight="bold", fontsize=10)

    # Subplot 3: Inference Latency (ms) - Log scale
    ax3 = axes[1, 0]
    bars3 = ax3.bar(models, latencies, color=colors[:len(models)], edgecolor="black", alpha=0.85)
    ax3.set_yscale("log")
    ax3.set_title("Reaction Time: Single-Step Inference Latency (ms) [Log Scale]", fontsize=12, fontweight="bold")
    ax3.set_ylabel("Latency in milliseconds (log scale)", fontsize=11)
    ax3.grid(axis="y", linestyle="--", alpha=0.5)
    ax3.tick_params(axis="x", rotation=25)
    for bar in bars3:
        yval = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width() / 2.0, yval * 1.15, f"{yval:.2f}ms", ha="center", va="bottom", fontweight="bold", fontsize=10)

    # Subplot 4: Parameter Count
    ax4 = axes[1, 1]
    bars4 = ax4.bar(models, params, color=colors[:len(models)], edgecolor="black", alpha=0.85)
    ax4.set_title("Model Footprint: Trainable Parameter Count [Memory Size]", fontsize=12, fontweight="bold")
    ax4.set_ylabel("Number of Parameters", fontsize=11)
    ax4.grid(axis="y", linestyle="--", alpha=0.5)
    ax4.tick_params(axis="x", rotation=25)
    for bar in bars4:
        yval = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width() / 2.0, yval + (max(params) * 0.02), f"{yval:,}", ha="center", va="bottom", fontweight="bold", fontsize=9)

    plt.tight_layout()
    perf_path = os.path.join(output_dir, "model_performance_bars.png")
    plt.savefig(perf_path, dpi=220)
    plt.close()
    print(f"✓ Saved model performance bar graphs to {perf_path}")

    # -------------------------------------------------------------------------
    # FIGURE 2: Kubernetes Cluster SLA Violations & Cloud Cost Impact
    # -------------------------------------------------------------------------
    if not os.path.exists(simulation_json):
        print(f"[WARN] Simulation results not found at {simulation_json}. Skipping Fig 2.")
        return

    with open(simulation_json, "r") as f:
        sim_data = json.load(f)

    sim_policies = list(sim_data.keys())
    sla_rates = [sim_data[p]["SLA Violation Rate (%)"] for p in sim_policies]
    waste_rates = [sim_data[p]["Capacity Waste (%)"] for p in sim_policies]
    pod_hours = [sim_data[p]["Total Pod-Hours"] for p in sim_policies]

    # Differentiate dynamic models from static/reactive baselines
    policy_colors = []
    for p in sim_policies:
        if "Static" in p:
            policy_colors.append("#7f8c8d")  # Gray
        elif "Reactive" in p:
            policy_colors.append("#e74c3c")  # Red
        elif "Bi-LSTM" in p:
            policy_colors.append("#2ecc71")  # Green (Proposed)
        else:
            policy_colors.append("#3498db")  # Blue

    fig2, axes2 = plt.subplots(1, 3, figsize=(18, 6))
    fig2.suptitle("Kubernetes Cluster Simulation — SLA Violations vs Cloud Infrastructure Cost", fontsize=16, fontweight="bold", y=0.98)

    # Subplot A: SLA Violation Rate (%)
    axA = axes2[0]
    barsA = axA.barh(sim_policies, sla_rates, color=policy_colors, edgecolor="black", alpha=0.85)
    axA.set_title("SLA Violations (%) [Lower is Better]", fontsize=12, fontweight="bold")
    axA.set_xlabel("Time Intervals with SLA Breaches (%)", fontsize=11)
    axA.grid(axis="x", linestyle="--", alpha=0.5)
    for bar in barsA:
        xval = bar.get_width()
        axA.text(xval + 0.15, bar.get_y() + bar.get_height() / 2.0, f"{xval:.2f}%", ha="left", va="center", fontweight="bold", fontsize=10)

    # Subplot B: Capacity Waste (%)
    axB = axes2[1]
    barsB = axB.barh(sim_policies, waste_rates, color=policy_colors, edgecolor="black", alpha=0.85)
    axB.set_title("Cluster Over-provisioning Waste (%)", fontsize=12, fontweight="bold")
    axB.set_xlabel("Unused Pod CPU/Capacity (%)", fontsize=11)
    axB.grid(axis="x", linestyle="--", alpha=0.5)
    for bar in barsB:
        xval = bar.get_width()
        axB.text(xval + 1.0, bar.get_y() + bar.get_height() / 2.0, f"{xval:.1f}%", ha="left", va="center", fontweight="bold", fontsize=10)

    # Subplot C: Pod-Hours (Cost)
    axC = axes2[2]
    barsC = axC.barh(sim_policies, pod_hours, color=policy_colors, edgecolor="black", alpha=0.85)
    axC.set_title("Operational Cloud Cost (Pod-Hours)", fontsize=12, fontweight="bold")
    axC.set_xlabel("Total Pod-Hours Billed", fontsize=11)
    axC.grid(axis="x", linestyle="--", alpha=0.5)
    for bar in barsC:
        xval = bar.get_width()
        axC.text(xval + 2.5, bar.get_y() + bar.get_height() / 2.0, f"{xval:.1f}h", ha="left", va="center", fontweight="bold", fontsize=10)

    plt.tight_layout()
    cost_path = os.path.join(output_dir, "cluster_sla_cost_bars.png")
    plt.savefig(cost_path, dpi=220)
    plt.close()
    print(f"✓ Saved cluster SLA and cost comparison bar graphs to {cost_path}\n")


if __name__ == "__main__":
    generate_graphical_comparisons()
