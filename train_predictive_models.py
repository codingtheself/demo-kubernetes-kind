#!/usr/bin/env python3
"""
train_predictive_models.py

Plug-and-play training and quantitative benchmarking engine for the Alibaba
Microservice Workload Trace.

Supported Models via model_zoo:
  - bilstm:        Bidirectional LSTM (Dang-Quang & Yoo 2021)
  - lstm:          Standard Unidirectional LSTM
  - gru:           Gated Recurrent Unit
  - transformer:   Self-Attention Temporal Transformer
  - mlp:           Multi-Layer Perceptron (Feed-Forward)
  - ridge:         L2-Regularized Linear Regression
  - random_forest: Ensemble of Decision Trees

Usage:
  python3 train_predictive_models.py --models all --epochs 15
  python3 train_predictive_models.py --models bilstm,gru,ridge --epochs 10
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
import time
import json
import pickle
import argparse
import numpy as np

# Ensure root dir is in python path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from model_zoo.registry import (
    get_model,
    list_available_models,
    get_default_model_filename,
)
from sklearn.metrics import mean_absolute_error, root_mean_squared_error


def benchmark_inference_speed(model, sample_window: np.ndarray, runs: int = 200) -> float:
    """Measures single-step inference latency in milliseconds."""
    # Warm-up passes
    for _ in range(20):
        _ = model.predict_step(sample_window)

    t0 = time.perf_counter()
    for _ in range(runs):
        _ = model.predict_step(sample_window)
    t1 = time.perf_counter()

    return ((t1 - t0) / runs) * 1000.0


def main():
    parser = argparse.ArgumentParser(description="Plug-and-Play AI Workload Forecaster Training & Benchmarking")
    parser.add_argument(
        "--models",
        type=str,
        default="all",
        help="Comma-separated list of models to train, or 'all' (default: all). Available: " +
             ", ".join(list_available_models())
    )
    parser.add_argument("--datadir", type=str, default="data", help="Directory containing train_data.npz, val_data.npz, test_data.npz")
    parser.add_argument("--modeldir", type=str, default="models", help="Directory to save model weights and benchmarks")
    parser.add_argument("--epochs", type=int, default=15, help="Training epochs for neural models (default: 15)")
    parser.add_argument("--batch-size", type=int, default=128, help="Batch size (default: 128)")
    parser.add_argument("--lr", type=float, default=0.001, help="Learning rate (default: 0.001)")
    args = parser.parse_args()

    os.makedirs(args.modeldir, exist_ok=True)

    # 1. Parse requested models
    available = list_available_models()
    if args.models.lower().strip() == "all":
        selected_models = available
    else:
        selected_models = [m.strip().lower() for m in args.models.split(",") if m.strip()]
        for m in selected_models:
            if m not in available:
                print(f"[ERROR] Unknown model '{m}'. Available options: {', '.join(available)}")
                sys.exit(1)

    print(f"\n===================================================================")
    print(f"       PLUG-AND-PLAY WORKLOAD MODEL BENCHMARKING ENGINE")
    print(f"===================================================================")
    print(f"  Target Models   : {', '.join(selected_models)}")
    print(f"  Training Epochs : {args.epochs}")
    print(f"  Batch Size      : {args.batch_size}")
    print(f"  Learning Rate   : {args.lr}")
    print(f"  Data Directory  : {args.datadir}")
    print(f"  Save Directory  : {args.modeldir}")
    print(f"===================================================================\n")

    # 2. Load datasets and scaler
    print(f"[1/4] Loading preprocessed datasets and fitted scaler...")
    train_data = np.load(os.path.join(args.datadir, "train_data.npz"))
    val_data = np.load(os.path.join(args.datadir, "val_data.npz"))
    test_data = np.load(os.path.join(args.datadir, "test_data.npz"))

    X_train, y_train = train_data["X"], train_data["y"]
    X_val, y_val = val_data["X"], val_data["y"]
    X_test, y_test = test_data["X"], test_data["y"]

    scaler_path = os.path.join(args.modeldir, "scaler.pkl")
    with open(scaler_path, "rb") as f:
        scaler = pickle.load(f)

    # Unscaled ground truth for test evaluations (in actual RPS)
    y_test_rps = scaler.inverse_transform(y_test.reshape(-1, 1)).flatten()
    sample_window = X_test[0, :, 0] if X_test.ndim == 3 else X_test[0]

    print(f"      Train samples: {len(X_train):,} | Val samples: {len(X_val):,} | Test samples: {len(X_test):,}")
    print(f"      Input window : {X_train.shape[1]} steps | Ground truth RPS range: [{y_test_rps.min():.1f} .. {y_test_rps.max():.1f}]")

    # 3. Train and benchmark each model
    results = {}
    test_predictions = {}

    print(f"\n[2/4] Training and evaluating selected model architectures...")
    for idx, model_key in enumerate(selected_models, 1):
        print(f"\n  ({idx}/{len(selected_models)}) Initializing '{model_key}'...")
        model = get_model(model_key, lookback=X_train.shape[1])

        # Train
        t_start = time.perf_counter()
        model.fit(
            X_train=X_train,
            y_train=y_train,
            X_val=X_val,
            y_val=y_val,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
            verbose=True
        )
        t_train = time.perf_counter() - t_start

        # Inference on test set
        preds_norm = model.predict_batch(X_test)
        preds_rps = scaler.inverse_transform(preds_norm.reshape(-1, 1)).flatten()
        test_predictions[model.name] = preds_rps

        # Calculate metrics
        mae = mean_absolute_error(y_test_rps, preds_rps)
        rmse = root_mean_squared_error(y_test_rps, preds_rps)
        mape = np.mean(np.abs((y_test_rps - preds_rps) / np.maximum(y_test_rps, 1e-5))) * 100.0
        inf_latency = benchmark_inference_speed(model, sample_window, runs=200)
        param_count = model.count_parameters()

        # Save model checkpoint
        save_filename = get_default_model_filename(model_key)
        save_path = os.path.join(args.modeldir, save_filename)
        model.save(save_path)

        results[model.name] = {
            "Model Key": model_key,
            "MAE (RPS)": round(float(mae), 2),
            "RMSE (RPS)": round(float(rmse), 2),
            "MAPE (%)": round(float(mape), 2),
            "Inference Latency (ms)": round(float(inf_latency), 2),
            "Parameters": int(param_count),
            "Training Time (s)": round(float(t_train), 2),
            "Artifact": save_filename
        }
        print(f"      ✓ Completed {model.name} -> MAE: {mae:.2f} RPS | MAPE: {mape:.2f}% | Latency: {inf_latency:.2f}ms | Saved: {save_filename}")

    # 4. Save results JSON
    benchmark_path = os.path.join(args.modeldir, "benchmark_results.json")
    with open(benchmark_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[3/4] Saved benchmark results to {benchmark_path}")

    # 5. Print Leaderboard
    print(f"\n[4/4] Quantitative Leaderboard (Sorted by MAPE):")
    print("=" * 100)
    header = f"{'Model Name':<24} | {'MAE (RPS)':<10} | {'RMSE (RPS)':<10} | {'MAPE (%)':<10} | {'Latency (ms)':<12} | {'Params':<8} | {'Train (s)':<9}"
    print(header)
    print("-" * 100)

    sorted_results = sorted(results.items(), key=lambda item: item[1]["MAPE (%)"])
    for name, m in sorted_results:
        star = " ◄" if "Bi-LSTM" in name else ""
        row = (f"{name:<24} | {m['MAE (RPS)']:<10.2f} | {m['RMSE (RPS)']:<10.2f} | "
               f"{m['MAPE (%)']:<10.2f} | {m['Inference Latency (ms)']:<12.2f} | "
               f"{m['Parameters']:<8} | {m['Training Time (s)']:<9.2f}{star}")
        print(row)
    print("=" * 100)

    # 6. Generate Multi-Model Comparison Plot
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.figure(figsize=(14, 7))
        # Plot 200 consecutive test intervals (100 minutes)
        window_slice = slice(100, 300)
        time_axis = np.arange(200) * 0.5  # in minutes

        plt.plot(time_axis, y_test_rps[window_slice], label="Ground Truth (Alibaba)", color="black", linewidth=2.2, zorder=5)

        colors = ["#00aa55", "#3388ff", "#ff8800", "#9933cc", "#e03333", "#00cccc", "#888800"]
        styles = ["--", "-.", ":", "--", "-.", ":", "--"]

        for i, (name, preds) in enumerate(test_predictions.items()):
            col = colors[i % len(colors)]
            sty = styles[i % len(styles)]
            plt.plot(time_axis, preds[window_slice], label=name, color=col, linestyle=sty, linewidth=1.5, alpha=0.85)

        plt.title("Workload Forecasting Comparison on Alibaba Microservice Trace", fontsize=15, fontweight="bold")
        plt.xlabel("Time (Minutes)", fontsize=12)
        plt.ylabel("Workload Demand (Requests / Second)", fontsize=12)
        plt.legend(loc="upper right", frameon=True, fontsize=10)
        plt.grid(True, linestyle="--", alpha=0.5)
        plt.tight_layout()

        plot_path = os.path.join(args.modeldir, "model_comparison.png")
        plt.savefig(plot_path, dpi=200)
        print(f"\n✓ Generated comprehensive comparison plot -> {plot_path}\n")
    except Exception as e:
        print(f"[WARN] Could not generate comparison plot: {e}")


if __name__ == "__main__":
    main()
