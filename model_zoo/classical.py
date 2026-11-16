"""
model_zoo.classical

Scikit-Learn implementations of classical machine learning models:
  1. RidgePredictor: L2 Regularized Linear Regression
  2. RandomForestPredictor: Ensemble of Decision Trees
"""

import os
import pickle
from typing import Optional, Dict, Any
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor

from .base import BaseWorkloadModel


class ClassicalWorkloadModel(BaseWorkloadModel):
    """Base wrapper for 2D tabular Scikit-Learn regressors."""

    def __init__(self, name: str, estimator, lookback: int = 12, **kwargs):
        super().__init__(name=name, lookback=lookback, **kwargs)
        self.estimator = estimator

    def _flatten_input(self, X: np.ndarray) -> np.ndarray:
        arr = np.asarray(X, dtype=np.float32)
        if arr.ndim == 3:
            return arr.reshape(arr.shape[0], -1)
        if arr.ndim == 1:
            return arr.reshape(1, -1)
        return arr

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
        X_2d = self._flatten_input(X_train)
        self.estimator.fit(X_2d, y_train)
        if verbose:
            print(f"      [{self.name}] Fitted successfully.")
        return {"status": "trained"}

    def predict_batch(self, X: np.ndarray) -> np.ndarray:
        X_2d = self._flatten_input(X)
        return np.asarray(self.estimator.predict(X_2d), dtype=np.float32)

    def save(self, filepath: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "wb") as f:
            pickle.dump(self.estimator, f)

    def load(self, filepath: str) -> None:
        with open(filepath, "rb") as f:
            self.estimator = pickle.load(f)


class RidgePredictor(ClassicalWorkloadModel):
    def __init__(self, lookback: int = 12, alpha: float = 1.0, **kwargs):
        estimator = Ridge(alpha=alpha)
        super().__init__(name="Ridge Regression", estimator=estimator, lookback=lookback, **kwargs)

    def count_parameters(self) -> int:
        # Weights + intercept
        return self.lookback + 1


class RandomForestPredictor(ClassicalWorkloadModel):
    def __init__(self, lookback: int = 12, n_estimators: int = 50, max_depth: int = 8, random_state: int = 42, **kwargs):
        estimator = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=random_state,
            n_jobs=-1
        )
        super().__init__(name="Random Forest", estimator=estimator, lookback=lookback, **kwargs)

    def count_parameters(self) -> int:
        if hasattr(self.estimator, "estimators_"):
            return sum(e.tree_.node_count for e in self.estimator.estimators_)
        return 0
