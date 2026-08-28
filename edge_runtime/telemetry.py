"""Deterministic energy-harvesting-style telemetry for demos and repeatable tests."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any


def generate_reading(
    device_id: str,
    step: int,
    fault: str | None = None,
    seed: int = 7,
    start: datetime | None = None,
    fault_window: tuple[int, int] | None = None,
) -> dict[str, Any]:
    rng = random.Random(seed + step)
    timestamp = (start or datetime.now(timezone.utc)) + timedelta(minutes=step)
    occupancy = step % 9 not in {0, 1, 2}
    base_energy = 1.20 if occupancy else 0.25
    reading: dict[str, Any] = {
        "device_id": device_id,
        "timestamp": timestamp.isoformat(),
        "temperature": round((21.0 if occupancy else 19.5) + rng.gauss(0, 0.35), 2),
        "humidity": round(45.0 + rng.gauss(0, 2.5), 2),
        "occupancy": occupancy,
        "energy_usage": round(max(0.03, base_energy + rng.gauss(0, 0.08)), 3),
        "signal_quality": round(max(0.72, min(1.0, 0.95 + rng.gauss(0, 0.02))), 3),
        "harvested_energy": round(max(0.04, 0.18 + rng.gauss(0, 0.02)), 3),
    }

    fault_start, fault_end = fault_window or (8, 17)
    in_fault_window = fault_start <= step <= fault_end

    if fault == "energy_spike" and in_fault_window:
        reading["energy_usage"] = round(reading["energy_usage"] * 2.35, 3)
    elif fault == "comfort_drift" and in_fault_window:
        reading["temperature"] = round(reading["temperature"] + 4.2, 2)
        reading["humidity"] = round(reading["humidity"] + 16.0, 2)
    elif fault == "device_health" and in_fault_window:
        reading["signal_quality"] = round(max(0.05, 0.18 + rng.gauss(0, 0.03)), 3)
        reading["harvested_energy"] = round(max(0.0, 0.025 + rng.gauss(0, 0.008)), 3)
    return reading
