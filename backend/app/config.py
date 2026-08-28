from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_path: str = os.getenv("DATABASE_PATH", "data/edge.db")
    model_artifact_path: str = os.getenv(
        "MODEL_ARTIFACT_PATH", "model_artifacts/edge_anomaly_v1.json"
    )
    candidate_artifact_path: str = os.getenv(
        "CANDIDATE_MODEL_ARTIFACT_PATH", "model_artifacts/edge_anomaly_candidate_v2.json"
    )
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:3003,http://127.0.0.1:3003"
        ).split(",")
        if origin.strip()
    )
