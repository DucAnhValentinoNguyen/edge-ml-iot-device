from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class InferencePayload(BaseModel):
    probability: float = Field(ge=0, le=1)
    is_anomaly: bool
    anomaly_type: str
    explanation: str
    recommended_action: str
    model_id: str
    model_version: int
    artifact_sha256: str | None = Field(default=None, max_length=64)
    features: dict[str, float] = Field(default_factory=dict)
    top_contributors: list[dict[str, Any]] = Field(default_factory=list)


class TelemetryPayload(BaseModel):
    device_id: str = Field(min_length=2, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    timestamp: datetime
    temperature: float = Field(ge=-50, le=100)
    humidity: float = Field(ge=0, le=100)
    occupancy: bool
    energy_usage: float = Field(ge=0, le=10000)
    signal_quality: float = Field(ge=0, le=1)
    harvested_energy: float = Field(ge=0, le=10000)
    event_id: str | None = Field(default=None, max_length=160)
    inference: InferencePayload | None = None


class DeployPayload(BaseModel):
    model_id: str | None = None
    version: int | None = Field(default=None, ge=1)


class SimulationPayload(BaseModel):
    device_id: str = Field(default="node-room-01", min_length=2, max_length=100)
    fault: Literal["energy_spike", "comfort_drift", "device_health"] = "energy_spike"
    steps: int = Field(default=24, ge=1, le=120)


class FeedbackPayload(BaseModel):
    label: Literal["true_positive", "false_positive", "not_reviewed"]
    note: str = Field(default="", max_length=500)


class TelegramPayload(BaseModel):
    gateway_id: str = Field(min_length=2, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    source_eurid: str = Field(min_length=8, max_length=11)
    rorg: str = Field(min_length=2, max_length=2)
    data_hex: str = Field(min_length=2, max_length=64)
    status_hex: str = Field(default="80", min_length=2, max_length=8)
    rssi: int = Field(default=70, ge=0, le=100)
    security_level: int = Field(default=0, ge=0, le=3)
    timestamp: datetime | None = None
    telegram_id: str | None = Field(default=None, max_length=160)


class RegisterDevicePayload(BaseModel):
    gateway_id: str = Field(default="gateway-demo-01", min_length=2, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    source_eurid: str = Field(min_length=8, max_length=11)
    profile_id: str = Field(min_length=4, max_length=20)
    friendly_id: str = Field(min_length=2, max_length=100)
    location: str = Field(min_length=2, max_length=160)
    device_id: str | None = Field(default=None, min_length=2, max_length=100)
