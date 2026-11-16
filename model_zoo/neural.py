"""
model_zoo.neural

PyTorch implementations of deep learning models for sequence forecasting:
  1. BiLSTMPredictor: Bidirectional LSTM
  2. LSTMPredictor: Standard Unidirectional LSTM
  3. GRUPredictor: Gated Recurrent Unit
  4. MLPPredictor: Multi-Layer Perceptron (Dense Feed-Forward)
  5. TransformerPredictor: Self-Attention Temporal Transformer
"""

import math
import os
from typing import Optional, Dict, Any
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader

from .base import BaseWorkloadModel


# =============================================================================
# PyTorch Module Architectures
# =============================================================================

class BiLSTMModule(nn.Module):
    """Bidirectional LSTM matching existing checkpoint architecture."""
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

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        last_step = out[:, -1, :]
        return self.fc(last_step).squeeze(-1)


class LSTMModule(nn.Module):
    """Standard Unidirectional LSTM matching existing checkpoint architecture."""
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

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        last_step = out[:, -1, :]
        return self.fc(last_step).squeeze(-1)


class GRUModule(nn.Module):
    """Gated Recurrent Unit (GRU) - Faster training & fewer parameters than LSTM."""
    def __init__(self, input_dim: int = 1, hidden_dim: int = 64, num_layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.gru = nn.GRU(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0
        )
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.gru(x)
        last_step = out[:, -1, :]
        return self.fc(last_step).squeeze(-1)


class MLPModule(nn.Module):
    """Multi-Layer Perceptron (Dense Feed-Forward Network)."""
    def __init__(self, lookback: int = 12, hidden_dim: int = 64, dropout: float = 0.2):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(lookback, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Flatten sequence: (batch_size, lookback, 1) -> (batch_size, lookback)
        flat = x.view(x.size(0), -1)
        return self.net(flat).squeeze(-1)


class PositionalEncoding(nn.Module):
    """Sinusoidal Positional Encoding for Transformer."""
    def __init__(self, d_model: int, max_len: int = 64):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer("pe", pe.unsqueeze(0))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (batch_size, seq_len, d_model)
        return x + self.pe[:, :x.size(1), :]


class TransformerModule(nn.Module):
    """Lightweight Self-Attention Transformer for short time-series sequences."""
    def __init__(self, input_dim: int = 1, d_model: int = 32, nhead: int = 4, num_layers: int = 1, dropout: float = 0.1):
        super().__init__()
        self.input_proj = nn.Linear(input_dim, d_model)
        self.pos_encoder = PositionalEncoding(d_model=d_model, max_len=64)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=d_model * 2,
            dropout=dropout,
            batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.head = nn.Sequential(
            nn.Linear(d_model, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch_size, seq_len, input_dim)
        proj = self.input_proj(x)
        pos = self.pos_encoder(proj)
        encoded = self.transformer(pos)
        # Global mean pooling over sequence dimension
        pooled = encoded.mean(dim=1)
        return self.head(pooled).squeeze(-1)


# =============================================================================
# PyTorch Base Wrapper
# =============================================================================

class PyTorchWorkloadModel(BaseWorkloadModel):
    """Generic wrapper managing PyTorch lifecycle (training, inference, checkpointing)."""

    def __init__(self, name: str, net: nn.Module, lookback: int = 12, device: str = "cpu", **kwargs):
        super().__init__(name=name, lookback=lookback, **kwargs)
        self.device = torch.device(device)
        self.net = net.to(self.device)

    @property
    def is_neural(self) -> bool:
        return True

    def count_parameters(self) -> int:
        return sum(p.numel() for p in self.net.parameters() if p.requires_grad)

    def _prepare_tensor(self, X: np.ndarray) -> torch.Tensor:
        arr = np.asarray(X, dtype=np.float32)
        if arr.ndim == 2:
            arr = arr[..., np.newaxis]
        return torch.tensor(arr, dtype=torch.float32).to(self.device)

    def fit(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        epochs: int = 15,
        batch_size: int = 128,
        lr: float = 0.001,
        verbose: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        t_x = self._prepare_tensor(X_train)
        t_y = torch.tensor(y_train, dtype=torch.float32).to(self.device)
        train_loader = DataLoader(TensorDataset(t_x, t_y), batch_size=batch_size, shuffle=True)

        val_loader = None
        if X_val is not None and y_val is not None:
            v_x = self._prepare_tensor(X_val)
            v_y = torch.tensor(y_val, dtype=torch.float32).to(self.device)
            val_loader = DataLoader(TensorDataset(v_x, v_y), batch_size=batch_size, shuffle=False)

        criterion = nn.MSELoss()
        optimizer = torch.optim.Adam(self.net.parameters(), lr=lr)

        best_val_loss = float("inf")
        best_state = None
        history = {"train_loss": [], "val_loss": []}

        for epoch in range(1, epochs + 1):
            self.net.train()
            train_loss = 0.0
            for bx, by in train_loader:
                optimizer.zero_grad()
                preds = self.net(bx)
                loss = criterion(preds, by)
                loss.backward()
                optimizer.step()
                train_loss += loss.item() * len(by)
            train_loss /= len(train_loader.dataset)
            history["train_loss"].append(train_loss)

            val_loss = None
            if val_loader is not None:
                self.net.eval()
                val_loss = 0.0
                with torch.no_grad():
                    for bx, by in val_loader:
                        preds = self.net(bx)
                        loss = criterion(preds, by)
                        val_loss += loss.item() * len(by)
                val_loss /= len(val_loader.dataset)
                history["val_loss"].append(val_loss)

                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    best_state = {k: v.cpu().clone() for k, v in self.net.state_dict().items()}

            if verbose and (epoch % 5 == 0 or epoch == epochs):
                v_str = f" | Val MSE: {val_loss:.6f}" if val_loss is not None else ""
                print(f"      [{self.name}] Epoch {epoch:02d}/{epochs:02d} | Train MSE: {train_loss:.6f}{v_str}")

        if best_state is not None:
            self.net.load_state_dict(best_state)

        return history

    def predict_batch(self, X: np.ndarray) -> np.ndarray:
        self.net.eval()
        t_x = self._prepare_tensor(X)
        with torch.no_grad():
            preds = self.net(t_x)
        return preds.cpu().numpy().flatten()

    def save(self, filepath: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        torch.save(self.net.state_dict(), filepath)

    def load(self, filepath: str) -> None:
        state = torch.load(filepath, map_location=self.device, weights_only=True)
        self.net.load_state_dict(state)
        self.net.eval()


# Concrete wrapper classes
class BiLSTMPredictor(PyTorchWorkloadModel):
    def __init__(self, lookback: int = 12, hidden_dim: int = 64, num_layers: int = 2, dropout: float = 0.2, device: str = "cpu"):
        net = BiLSTMModule(input_dim=1, hidden_dim=hidden_dim, num_layers=num_layers, dropout=dropout)
        super().__init__(name="Bi-LSTM", net=net, lookback=lookback, device=device)


class LSTMPredictor(PyTorchWorkloadModel):
    def __init__(self, lookback: int = 12, hidden_dim: int = 64, num_layers: int = 2, dropout: float = 0.2, device: str = "cpu"):
        net = LSTMModule(input_dim=1, hidden_dim=hidden_dim, num_layers=num_layers, dropout=dropout)
        super().__init__(name="Standard LSTM", net=net, lookback=lookback, device=device)


class GRUPredictor(PyTorchWorkloadModel):
    def __init__(self, lookback: int = 12, hidden_dim: int = 64, num_layers: int = 2, dropout: float = 0.2, device: str = "cpu"):
        net = GRUModule(input_dim=1, hidden_dim=hidden_dim, num_layers=num_layers, dropout=dropout)
        super().__init__(name="GRU", net=net, lookback=lookback, device=device)


class MLPPredictor(PyTorchWorkloadModel):
    def __init__(self, lookback: int = 12, hidden_dim: int = 64, dropout: float = 0.2, device: str = "cpu"):
        net = MLPModule(lookback=lookback, hidden_dim=hidden_dim, dropout=dropout)
        super().__init__(name="MLP", net=net, lookback=lookback, device=device)


class TransformerPredictor(PyTorchWorkloadModel):
    def __init__(self, lookback: int = 12, d_model: int = 32, nhead: int = 4, num_layers: int = 1, dropout: float = 0.1, device: str = "cpu"):
        net = TransformerModule(input_dim=1, d_model=d_model, nhead=nhead, num_layers=num_layers, dropout=dropout)
        super().__init__(name="Transformer", net=net, lookback=lookback, device=device)
