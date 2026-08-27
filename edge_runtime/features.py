"""Feature extraction shared by training, the device runtime, and tests."""

from __future__ import annotations

from typing import Mapping

FEATURE_NAMES = (
    "energy_ratio",
    "temperature_deviation",
    "humidity_deviation",
    "signal_loss",
    "harvested_energy_deficit",
    "occupancy_energy_mismatch",
)


def extract_features(reading: Mapping[str, float | int | bool]) -> dict[str, float]:
    occupancy = 1.0 if bool(reading.get("occupancy", False)) else 0.0
    expected_energy = 0.25 + (1.20 * occupancy)
    energy = max(0.0, float(reading.get("energy_usage", 0.0)))
    temperature_target = 21.0 if occupancy else 19.5
    humidity = float(reading.get("humidity", 45.0))
    signal_quality = max(0.0, min(1.0, float(reading.get("signal_quality", 0.0))))
    harvested_energy = max(0.0, float(reading.get("harvested_energy", 0.0)))

    return {
        "energy_ratio": energy / expected_energy,
        "temperature_deviation": abs(float(reading.get("temperature", temperature_target)) - temperature_target),
        "humidity_deviation": abs(humidity - 45.0),
        "signal_loss": 1.0 - signal_quality,
        "harvested_energy_deficit": max(0.0, 0.10 - harvested_energy),
        "occupancy_energy_mismatch": max(0.0, energy - 0.45) if not occupancy else 0.0,
    }


def classify_signal(reading: Mapping[str, float | int | bool], features: Mapping[str, float]) -> str:
    """Map a positive score to an operator-friendly fault class."""
    if features["signal_loss"] >= 0.45 or features["harvested_energy_deficit"] >= 0.08:
        return "device_health"
    if features["temperature_deviation"] >= 2.0 or features["humidity_deviation"] >= 12.0:
        return "comfort_drift"
    if features["energy_ratio"] >= 1.55 or features["occupancy_energy_mismatch"] >= 0.35:
        return "energy_spike"
    return "unknown"


def explain(reading: Mapping[str, float | int | bool], features: Mapping[str, float], anomaly_type: str) -> tuple[str, str]:
    energy = float(reading.get("energy_usage", 0.0))
    occupancy = bool(reading.get("occupancy", False))
    expected_energy = 0.25 + (1.20 if occupancy else 0.0)
    if anomaly_type == "energy_spike":
        delta = ((energy / expected_energy) - 1.0) * 100.0
        return (
            f"Energy is {max(0.0, delta):.0f}% above the occupancy-adjusted baseline.",
            "Check HVAC schedules and high-load equipment in this room.",
        )
    if anomaly_type == "comfort_drift":
        return (
            f"Comfort deviation is {max(features['temperature_deviation'], features['humidity_deviation'] / 3):.1f} units from target.",
            "Inspect the room setpoint, window state, and local HVAC actuator.",
        )
    if anomaly_type == "device_health":
        quality = float(reading.get("signal_quality", 0.0)) * 100.0
        return (
            f"Signal quality is {quality:.0f}% and harvested energy is {float(reading.get('harvested_energy', 0.0)):.2f} mJ.",
            "Inspect sensor placement, radio path, and available ambient energy.",
        )
    return ("The edge model found a deviation from the learned normal profile.", "Review the raw telemetry and compare nearby rooms.")

