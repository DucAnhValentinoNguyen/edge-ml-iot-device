"""Load and execute the compact model artifact on a constrained device."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class ModelArtifactError(ValueError):
    """Raised when an artifact is malformed or fails integrity verification."""


@dataclass(frozen=True)
class ModelArtifact:
    model_id: str
    version: int
    feature_names: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    weights: tuple[float, ...]
    bias: float
    threshold: float
    metrics: Mapping[str, float]
    artifact_sha256: str

    @classmethod
    def load(cls, path: str | Path, verify_hash: bool = True) -> "ModelArtifact":
        source = Path(path)
        raw = json.loads(source.read_text(encoding="utf-8"))
        required = {
            "model_id",
            "version",
            "feature_names",
            "normalization",
            "weights",
            "bias",
            "threshold",
            "metrics",
            "artifact_sha256",
        }
        missing = sorted(required - raw.keys())
        if missing:
            raise ModelArtifactError(f"Model artifact is missing: {', '.join(missing)}")

        supplied_hash = raw["artifact_sha256"]
        payload = {key: value for key, value in raw.items() if key != "artifact_sha256"}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        calculated_hash = hashlib.sha256(canonical).hexdigest()
        if verify_hash and supplied_hash != calculated_hash:
            raise ModelArtifactError("Model artifact checksum verification failed")

        names = tuple(str(name) for name in raw["feature_names"])
        normalization = raw["normalization"]
        try:
            means = tuple(float(normalization[name]["mean"]) for name in names)
            scales = tuple(float(normalization[name]["scale"]) for name in names)
            weights = tuple(float(raw["weights"][name]) for name in names)
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelArtifactError("Model artifact feature metadata is invalid") from exc

        if not names or len(names) != len(means) or len(names) != len(weights):
            raise ModelArtifactError("Model artifact has inconsistent feature dimensions")
        if any(scale <= 0 for scale in scales):
            raise ModelArtifactError("Model artifact scales must be positive")

        return cls(
            model_id=str(raw["model_id"]),
            version=int(raw["version"]),
            feature_names=names,
            means=means,
            scales=scales,
            weights=weights,
            bias=float(raw["bias"]),
            threshold=float(raw["threshold"]),
            metrics={str(key): float(value) for key, value in raw["metrics"].items()},
            artifact_sha256=str(supplied_hash),
        )

    def score(self, features: Mapping[str, float]) -> tuple[float, dict[str, float]]:
        """Return a sigmoid probability and per-feature contributions."""
        normalized: dict[str, float] = {}
        linear = self.bias
        for name, mean, scale, weight in zip(
            self.feature_names, self.means, self.scales, self.weights
        ):
            value = float(features.get(name, 0.0))
            z_value = (value - mean) / scale
            normalized[name] = z_value
            linear += z_value * weight
        probability = 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, linear))))
        contributions = {
            name: normalized[name] * weight
            for name, weight in zip(self.feature_names, self.weights)
        }
        return probability, contributions

