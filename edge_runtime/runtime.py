"""The small inference service that can be copied to an IoT gateway or MCU."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .features import classify_signal, explain, extract_features
from .model import ModelArtifact


@dataclass(frozen=True)
class Prediction:
    probability: float
    is_anomaly: bool
    anomaly_type: str
    explanation: str
    recommended_action: str
    model_id: str
    model_version: int
    artifact_sha256: str
    features: dict[str, float]
    top_contributors: list[dict[str, float | str]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EdgeRuntime:
    def __init__(self, artifact: ModelArtifact):
        self.artifact = artifact

    def predict(self, reading: Mapping[str, Any]) -> Prediction:
        features = extract_features(reading)
        probability, contributions = self.artifact.score(features)
        is_anomaly = probability >= self.artifact.threshold
        anomaly_type = classify_signal(reading, features) if is_anomaly else "none"
        explanation, recommended_action = explain(reading, features, anomaly_type)
        top = sorted(contributions.items(), key=lambda item: abs(item[1]), reverse=True)[:3]
        top_contributors = [
            {"feature": name, "contribution": round(value, 4)} for name, value in top
        ]
        return Prediction(
            probability=round(probability, 5),
            is_anomaly=is_anomaly,
            anomaly_type=anomaly_type,
            explanation=explanation,
            recommended_action=recommended_action,
            model_id=self.artifact.model_id,
            model_version=self.artifact.version,
            artifact_sha256=self.artifact.artifact_sha256,
            features={name: round(value, 5) for name, value in features.items()},
            top_contributors=top_contributors,
        )
