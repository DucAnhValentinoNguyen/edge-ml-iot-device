"""The dependency-light inference runtime shipped to an edge device."""

from .model import ModelArtifact, ModelArtifactError
from .runtime import EdgeRuntime, Prediction
from .telemetry import generate_reading

__all__ = [
    "EdgeRuntime",
    "ModelArtifact",
    "ModelArtifactError",
    "Prediction",
    "generate_reading",
]

