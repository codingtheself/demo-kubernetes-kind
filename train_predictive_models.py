#!/usr/bin/env python3
"""
train_predictive_models.py

Trains and quantitatively benchmarks three predictive workload models
for the Alibaba Microservice cluster trace:
  1. Bidirectional LSTM (Bi-LSTM) - Proposed Primary Model (Dang-Quang & Yoo 2021)
  2. Unidirectional LSTM - Baseline 1
  3. Ridge Regression - Baseline 2 (Classical ML Benchmark)

Evaluation Metrics:
  - MAE (Mean Absolute Error in actual RPS)
  - RMSE (Root Mean Squared Error in actual RPS)
  - MAPE (%) (Mean Absolute Percentage Error)
  - Inference Latency (ms per single-sample inference)

Artifacts saved:
  - models/bilstm_workload_model.pt: Best trained PyTorch Bi-LSTM weights
  - models/lstm_workload_model.pt: Best trained PyTorch LSTM weights
  - models/benchmark_results.json: Full metrics for final report tables
  - models/model_comparison.png: Visualization plot of predictions vs actual
"""

import os
import time
import json
import pickle
import argparse
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, root_mean_squared_error


# --- Model 1: Bidirectional LSTM ---
class BiLSTMWorkloadPredictor(nn.Module):
    def __init__(self, input_dim: int = 1, hidden_dim: int = 64, num_layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0.0
        )
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim * 2, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1)
        )

    def forward(self, x):
        # x shape: (batch_size, seq_len, input_dim)
        out, _ = self.lstm(x)
        # Use output of last time-step
        last_step = out[:, -1, :]
        return self.fc(last_step).squeeze(-1)


# --- Model 2: Unidirectional LSTM ---
class LSTMWorkloadPredictor(nn.Module):
    def __init__(self, input_dim: int = 1, hidden_dim: int = 64, num_layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=False,
            dropout=dropout if num_layers > 1 else 0.0
        )
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1)
        )

    def forward(self, x):
        out, _ = self.lstm(x)
        last_step = out[:, -1, :]
        return self.fc(last_step).squeeze(-1)


def train_pytorch_model(model, train_loader, val_loader, epochs=15, lr=0.001, device="cpu"):
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    best_val_loss = float("inf")
    best_state = None

    for epoch in range(1, epochs + 1):
        model.train()
        train_loss = 0.0
        for batch_x, batch_y in train_loader:
            batch_x, batch_y = batch_x.to(device), batch_y.to(device)
            optimizer.zero_grad()
            preds = model(batch_x)
            loss = criterion(preds, batch_y)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * len(batch_y)
        train_loss /= len(train_loader.dataset)

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for batch_x, batch_y in val_loader:
                batch_x, batch_y = batch_x.to(device), batch_y.to(device)
                preds = model(batch_x)
                loss = criterion(preds, batch_y)
                val_loss += loss.item() * len(batch_y)
        val_loss /= len(val_loader.dataset)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = model.state_dict()

        if epoch % 5 == 0 or epoch == epochs:
            print(f"      Epoch {epoch:02d}/{epochs:02d} | Train MSE: {train_loss:.6f} | Val MSE: {val_loss:.6f}")

    if best_state is not None:
        model.load_state_dict(best_state)
    return model


def benchmark_inference_speed(model_fn, sample_x, runs=200):
    """Measures single-item inference latency in milliseconds."""
    # Warm up
    for _ in range(20):
        model_fn(sample_x)
    t0 = time.perf_counter()
    for _ in range(runs):
        model_fn(sample_x)
    t1 = time.perf_counter()
    return ((t1 - t0) / runs) * 1000.0


def main():
    parser = argparse.ArgumentParser(description="Train and Compare Predictive Autoscaling Models")
    parser.add_argument("--datadir", type=str, default="data", help="Directory containing preprocessed npz files")
    parser.add_argument("--modeldir", type=str, default="models", help="Directory to save models")
    parser.add_argument("--epochs", type=int, default=15, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=128, help="Mini-batch size")
    args = parser.parse_args()

    os.makedirs(args.modeldir, exist_ok=True)
    device = torch.device("cpu")
    print(f"\n[1/5] Loading datasets from {args.datadir}/...")

    train_data = np.load(os.path.join(args.datadir, "train_data.npz"))
    val_data = np.load(os.path.join(args.datadir, "val_data.npz"))
    test_data = np.load(os.path.join(args.datadir, "test_data.npz"))

    X_train, y_train = train_data["X"], train_data["y"]
    X_val, y_val = val_data["X"], val_data["y"]
    X_test, y_test = test_data["X"], test_data["y"]

    with open(os.path.join(args.modeldir, "scaler.pkl"), "rb") as f:
        scaler = pickle.load(f)

    # Convert to PyTorch tensors
    train_dataset = TensorDataset(torch.tensor(X_train, dtype=torch.float32), torch.tensor(y_train, dtype=torch.float32))
    val_dataset = TensorDataset(torch.tensor(X_val, dtype=torch.float32), torch.tensor(y_val, dtype=torch.float32))
    test_dataset = TensorDataset(torch.tensor(X_test, dtype=torch.float32), torch.tensor(y_test, dtype=torch.float32))

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False)

    # Actual test RPS targets (unscaled)
    y_test_rps = scaler.inverse_transform(y_test.reshape(-1, 1)).flatten()

    results = {}

    # ----------------------------------------------------
    # Model 1: Bidirectional LSTM
    # ----------------------------------------------------
    print("\n[2/5] Training Proposed Bidirectional LSTM (Bi-LSTM)...")
    bilstm = BiLSTMWorkloadPredictor(input_dim=1, hidden_dim=64, num_layers=2, dropout=0.2).to(device)
    bilstm = train_pytorch_model(bilstm, train_loader, val_loader, epochs=args.epochs, lr=0.001, device=device)

    # Evaluation on holdout test set
    bilstm.eval()
    with torch.no_grad():
        bilstm_preds_norm = []
        for bx, _ in test_loader:
            preds = bilstm(bx.to(device)).cpu().numpy()
            bilstm_preds_norm.extend(preds)
        bilstm_preds_norm = np.array(bilstm_preds_norm)

    bilstm_preds_rps = scaler.inverse_transform(bilstm_preds_norm.reshape(-1, 1)).flatten()
    mae_bilstm = mean_absolute_error(y_test_rps, bilstm_preds_rps)
    rmse_bilstm = root_mean_squared_error(y_test_rps, bilstm_preds_rps)
    mape_bilstm = np.mean(np.abs((y_test_rps - bilstm_preds_rps) / np.maximum(y_test_rps, 1e-5))) * 100.0

    sample_tensor = torch.tensor(X_test[:1], dtype=torch.float32).to(device)
    inf_bilstm = benchmark_inference_speed(lambda x: bilstm(x), sample_tensor)

    results["Bi-LSTM (Proposed)"] = {
        "MAE (RPS)": round(float(mae_bilstm), 2),
        "RMSE (RPS)": round(float(rmse_bilstm), 2),
        "MAPE (%)": round(float(mape_bilstm), 2),
        "Inference Latency (ms)": round(float(inf_bilstm), 2)
    }
    torch.save(bilstm.state_dict(), os.path.join(args.modeldir, "bilstm_workload_model.pt"))
    print(f"      ✓ Saved Bi-LSTM weights to {args.modeldir}/bilstm_workload_model.pt")

    # ----------------------------------------------------
    # Model 2: Unidirectional LSTM (Baseline 1)
    # ----------------------------------------------------
    print("\n[3/5] Training Baseline Unidirectional LSTM...")
    lstm = LSTMWorkloadPredictor(input_dim=1, hidden_dim=64, num_layers=2, dropout=0.2).to(device)
    lstm = train_pytorch_model(lstm, train_loader, val_loader, epochs=args.epochs, lr=0.001, device=device)

    lstm.eval()
    with torch.no_grad():
        lstm_preds_norm = []
        for bx, _ in test_loader:
            preds = lstm(bx.to(device)).cpu().numpy()
            lstm_preds_norm.extend(preds)
        lstm_preds_norm = np.array(lstm_preds_norm)

    lstm_preds_rps = scaler.inverse_transform(lstm_preds_norm.reshape(-1, 1)).flatten()
    mae_lstm = mean_absolute_error(y_test_rps, lstm_preds_rps)
    rmse_lstm = root_mean_squared_error(y_test_rps, lstm_preds_rps)
    mape_lstm = np.mean(np.abs((y_test_rps - lstm_preds_rps) / np.maximum(y_test_rps, 1e-5))) * 100.0
    inf_lstm = benchmark_inference_speed(lambda x: lstm(x), sample_tensor)

    results["Standard LSTM (Baseline 1)"] = {
        "MAE (RPS)": round(float(mae_lstm), 2),
        "RMSE (RPS)": round(float(rmse_lstm), 2),
        "MAPE (%)": round(float(mape_lstm), 2),
        "Inference Latency (ms)": round(float(inf_lstm), 2)
    }
    torch.save(lstm.state_dict(), os.path.join(args.modeldir, "lstm_workload_model.pt"))

    # ----------------------------------------------------
    # Model 3: Ridge Regression (Baseline 2)
    # ----------------------------------------------------
    print("\n[4/5] Training Baseline Ridge Regression...")
    X_train_2d = X_train.squeeze(-1)
    X_test_2d = X_test.squeeze(-1)
    ridge = Ridge(alpha=1.0)
    ridge.fit(X_train_2d, y_train)

    ridge_preds_norm = ridge.predict(X_test_2d)
    ridge_preds_rps = scaler.inverse_transform(ridge_preds_norm.reshape(-1, 1)).flatten()
    mae_ridge = mean_absolute_error(y_test_rps, ridge_preds_rps)
    rmse_ridge = root_mean_squared_error(y_test_rps, ridge_preds_rps)
    mape_ridge = np.mean(np.abs((y_test_rps - ridge_preds_rps) / np.maximum(y_test_rps, 1e-5))) * 100.0

    sample_np = X_test_2d[:1]
    inf_ridge = benchmark_inference_speed(lambda x: ridge.predict(x), sample_np)

    results["Ridge Regression (Baseline 2)"] = {
        "MAE (RPS)": round(float(mae_ridge), 2),
        "RMSE (RPS)": round(float(rmse_ridge), 2),
        "MAPE (%)": round(float(mape_ridge), 2),
        "Inference Latency (ms)": round(float(inf_ridge), 2)
    }

    # ----------------------------------------------------
    # Model Comparison Summary Table
    # ----------------------------------------------------
    print("\n[5/5] Quantitative Benchmark Summary (Hold-out Alibaba Test Set):")
    print("=" * 80)
    header = f"{'Model':<30} | {'MAE (RPS)':<10} | {'RMSE (RPS)':<11} | {'MAPE (%)':<10} | {'Latency (ms)':<12}"
    print(header)
    print("-" * 80)
    for model_name, m in results.items():
        row = f"{model_name:<30} | {m['MAE (RPS)']:<10.2f} | {m['RMSE (RPS)']:<11.2f} | {m['MAPE (%)']:<10.2f} | {m['Inference Latency (ms)']:<12.2f}"
        print(row)
    print("=" * 80)

    # Save metrics JSON for final thesis / reports
    with open(os.path.join(args.modeldir, "benchmark_results.json"), "w") as f:
        json.dump(results, f, indent=2)

    # Generate visual evaluation plot
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.figure(figsize=(12, 6))
        # Plot 200 consecutive test intervals (100 minutes)
        window_slice = slice(100, 300)
        time_axis = np.arange(200) * 0.5  # in minutes
        plt.plot(time_axis, y_test_rps[window_slice], label="Actual Alibaba Trace", color="black", linewidth=1.8)
        plt.plot(time_axis, bilstm_preds_rps[window_slice], label="Bi-LSTM (Proposed)", color="#00aa55", linestyle="--", linewidth=1.5)
        plt.plot(time_axis, lstm_preds_rps[window_slice], label="LSTM (Baseline 1)", color="#ff8800", linestyle=":", linewidth=1.3)
        plt.plot(time_axis, ridge_preds_rps[window_slice], label="Ridge Reg (Baseline 2)", color="#3388ff", linestyle="-.", linewidth=1.2)

        plt.title("Workload Forecasting Comparison on Alibaba Microservice Trace", fontsize=14, fontweight="bold")
        plt.xlabel("Time (Minutes)", fontsize=11)
        plt.ylabel("Workload Demand (Requests / Second)", fontsize=11)
        plt.legend(loc="upper right", frameon=True)
        plt.grid(True, linestyle="--", alpha=0.5)
        plt.tight_layout()

        plot_path = os.path.join(args.modeldir, "model_comparison.png")
        plt.savefig(plot_path, dpi=200)
        print(f"      ✓ Comparison plot saved to {plot_path}")
    except Exception as e:
        print(f"      [WARN] Could not save plot: {e}")

    print("\n✓ Task 3 Model Training & Comparison Complete!\n")


if __name__ == "__main__":
    main()
