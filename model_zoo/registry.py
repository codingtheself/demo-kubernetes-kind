"""
model_zoo.registry

Factory registry mapping human-friendly model identifiers to model classes.
Enables plug-and-play dynamic selection via CLI arguments.
"""

from typing import Dict, Type, List
from .base import BaseWorkloadModel
from .neural import (
    BiLSTMPredictor,
    LSTMPredictor,
    GRUPredictor,
    MLPPredictor,
    TransformerPredictor,
)
from .classical import (
    RidgePredictor,
    RandomForestPredictor,
)


_MODEL_REGISTRY: Dict[str, Type[BaseWorkloadModel]] = {
    "bilstm": BiLSTMPredictor,
    "lstm": LSTMPredictor,
    "gru": GRUPredictor,
    "mlp": MLPPredictor,
    "transformer": TransformerPredictor,
    "ridge": RidgePredictor,
    "random_forest": RandomForestPredictor,
}


def register_model(name: str, model_cls: Type[BaseWorkloadModel]) -> None:
    """Register a new custom model architecture into the factory."""
    _MODEL_REGISTRY[name.lower()] = model_cls


def list_available_models() -> List[str]:
    """Return all registered model keys."""
    return sorted(list(_MODEL_REGISTRY.keys()))


def get_model(name: str, **kwargs) -> BaseWorkloadModel:
    """Instantiate a registered model by identifier."""
    key = name.lower().strip()
    if key not in _MODEL_REGISTRY:
        valid = ", ".join(list_available_models())
        raise ValueError(f"Unknown model architecture '{name}'. Available: {valid}")
    return _MODEL_REGISTRY[key](**kwargs)


def get_default_model_filename(name: str) -> str:
    """Returns standard artifact filename (e.g. bilstm_workload_model.pt)."""
    key = name.lower().strip()
    if key in ["ridge", "random_forest"]:
        return f"{key}_workload_model.pkl"
    return f"{key}_workload_model.pt"
