"""
model_zoo.base

Defines the abstract base class and contract for all predictive workload models.
Every model—neural (PyTorch) or classical (Scikit-Learn)—implements this interface.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import numpy as np


class BaseWorkloadModel(ABC):
    """
    Abstract Universal Interface for all Workload Forecasting Models.
    Ensures plug-and-play interchangeability in both training and live autoscaling loops.
    """

    def __init__(self, name: str, lookback: int = 12, **kwargs):
        self.name = name
        self.lookback = lookback
        self.kwargs = kwargs

    @abstractmethod
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
        """
        Train the model on normalized sliding windows.
        X_train: (N, lookback, 1) or (N, lookback)
        y_train: (N,)
        Returns training telemetry / loss dictionary.
        """
        pass

    @abstractmethod
    def predict_batch(self, X: np.ndarray) -> np.ndarray:
        """
        Predict normalized target values for a batch of sequences.
        X: (batch_size, lookback, 1) or (batch_size, lookback)
        Returns: (batch_size,) 1D array of predicted normalized values.
        """
        pass

    def predict_step(self, lookback_window: np.ndarray) -> float:
        """
        Predict the single next normalized value given the most recent history window.
        lookback_window: 1D array of shape (lookback,)
        Returns: single float.
        """
        arr = np.asarray(lookback_window, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, self.lookback, 1)
        elif arr.ndim == 2 and arr.shape == (self.lookback, 1):
            arr = arr.reshape(1, self.lookback, 1)
        preds = self.predict_batch(arr)
        return float(preds[0])

    @abstractmethod
    def save(self, filepath: str) -> None:
        """Serialize model weights/state to disk."""
        pass

    @abstractmethod
    def load(self, filepath: str) -> None:
        """Load model weights/state from disk."""
        pass

    @abstractmethod
    def count_parameters(self) -> int:
        """Return total trainable parameter count."""
        pass

    @property
    def is_neural(self) -> bool:
        """True if the model is implemented in PyTorch."""
        return False
