"""A dependency-light trainer used to create the deployable edge artifact."""

from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .features import FEATURE_NAMES, extract_features
from .telemetry import generate_reading


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, value))))


def _make_dataset(seed: int = 23) -> list[tuple[dict[str, float], int]]:
    rows: list[tuple[dict[str, float], int]] = []
    for fault in [None, "energy_spike", "comfort_drift", "device_health"]:
        count = 480 if fault is None else 180
        for sample_index in range(count):
            # Fault labels must correspond to an active fault window; using arbitrary
            # steps here would silently label normal readings as positive examples.
            step = 10 if fault else 4
            reading = generate_reading(
                "training-device", step, fault=fault, seed=seed + sample_index * 11
            )
            rows.append((extract_features(reading), 0 if fault is None else 1))
    random.Random(seed).shuffle(rows)
    return rows


def _mean(values: list[float], default: float) -> float:
    return sum(values) / len(values) if values else default


def _label_from_reading(reading: dict[str, Any]) -> int:
    feedback = str(reading.get("feedback_label") or "")
    if feedback == "true_positive":
        return 1
    if feedback == "false_positive":
        return 0
    inference = reading.get("inference") or {}
    return 1 if bool(inference.get("is_anomaly")) else 0


def _profile_from_readings(readings: list[dict[str, Any]]) -> dict[str, float]:
    default_profile = {
        "occupied_energy": 1.20,
        "unoccupied_energy": 0.25,
        "occupied_temperature": 21.0,
        "unoccupied_temperature": 19.5,
        "humidity": 45.0,
        "signal_quality": 0.95,
        "harvested_energy": 0.18,
    }
    if not readings:
        return default_profile

    normal_readings = [reading for reading in readings if _label_from_reading(reading) == 0]
    source = normal_readings or readings
    occupied = [reading for reading in source if bool(reading.get("occupancy"))]
    unoccupied = [reading for reading in source if not bool(reading.get("occupancy"))]
    return {
        "occupied_energy": _mean([float(reading["energy_usage"]) for reading in occupied], default_profile["occupied_energy"]),
        "unoccupied_energy": _mean([float(reading["energy_usage"]) for reading in unoccupied], default_profile["unoccupied_energy"]),
        "occupied_temperature": _mean([float(reading["temperature"]) for reading in occupied], default_profile["occupied_temperature"]),
        "unoccupied_temperature": _mean([float(reading["temperature"]) for reading in unoccupied], default_profile["unoccupied_temperature"]),
        "humidity": _mean([float(reading["humidity"]) for reading in source], default_profile["humidity"]),
        "signal_quality": _mean([float(reading["signal_quality"]) for reading in source], default_profile["signal_quality"]),
        "harvested_energy": _mean([float(reading["harvested_energy"]) for reading in source], default_profile["harvested_energy"]),
    }


def _profiled_reading(
    profile: dict[str, float],
    fault: str | None,
    sample_index: int,
    rng: random.Random,
) -> dict[str, Any]:
    occupancy = sample_index % 9 not in {0, 1, 2}
    energy_baseline = profile["occupied_energy"] if occupancy else profile["unoccupied_energy"]
    temperature_target = (
        profile["occupied_temperature"] if occupancy else profile["unoccupied_temperature"]
    )
    reading: dict[str, Any] = {
        "device_id": "training-device",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temperature": round(temperature_target + rng.gauss(0, 0.45), 3),
        "humidity": round(profile["humidity"] + rng.gauss(0, 3.0), 3),
        "occupancy": occupancy,
        "energy_usage": round(max(0.03, energy_baseline + rng.gauss(0, max(0.06, energy_baseline * 0.08))), 3),
        "signal_quality": round(max(0.05, min(1.0, profile["signal_quality"] + rng.gauss(0, 0.035))), 3),
        "harvested_energy": round(max(0.0, profile["harvested_energy"] + rng.gauss(0, 0.025)), 3),
    }

    if fault == "energy_spike":
        reading["energy_usage"] = round(reading["energy_usage"] * rng.uniform(1.8, 2.5), 3)
    elif fault == "comfort_drift":
        reading["temperature"] = round(reading["temperature"] + rng.uniform(3.1, 5.1), 3)
        reading["humidity"] = round(min(100.0, reading["humidity"] + rng.uniform(11.0, 18.0)), 3)
    elif fault == "device_health":
        reading["signal_quality"] = round(max(0.02, rng.uniform(0.05, 0.35)), 3)
        reading["harvested_energy"] = round(max(0.0, rng.uniform(0.0, 0.04)), 3)
    return reading


def _make_dataset_from_telemetry(
    telemetry_readings: list[dict[str, Any]],
    seed: int = 23,
) -> tuple[list[tuple[dict[str, float], int]], dict[str, Any]]:
    rows: list[tuple[dict[str, float], int]] = []
    for reading in telemetry_readings:
        rows.append((extract_features(reading), _label_from_reading(reading)))

    profile = _profile_from_readings(telemetry_readings)
    rng = random.Random(seed)
    telemetry_count = len(rows)
    synthetic_normal = max(240, telemetry_count // 2)
    synthetic_fault = max(120, telemetry_count // 4)
    for sample_index in range(synthetic_normal):
        rows.append((extract_features(_profiled_reading(profile, None, sample_index, rng)), 0))
    for fault in ("energy_spike", "comfort_drift", "device_health"):
        for sample_index in range(synthetic_fault):
            rows.append((extract_features(_profiled_reading(profile, fault, sample_index + 10, rng)), 1))

    random.Random(seed).shuffle(rows)
    metadata = {
        "source": "telemetry-adapted-training",
        "telemetry_samples": telemetry_count,
        "synthetic_samples": len(rows) - telemetry_count,
        "profile": {key: round(value, 4) for key, value in profile.items()},
    }
    return rows, metadata


def _fit_logistic(
    rows: Iterable[tuple[dict[str, float], int]],
) -> tuple[dict[str, float], dict[str, tuple[float, float]], float, list[tuple[list[float], int]]]:
    dataset = list(rows)
    means: dict[str, float] = {}
    scales: dict[str, float] = {}
    for name in FEATURE_NAMES:
        values = [features[name] for features, _ in dataset]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        means[name] = mean
        scales[name] = max(0.0001, math.sqrt(variance))

    vectors = [
        ([(features[name] - means[name]) / scales[name] for name in FEATURE_NAMES], label)
        for features, label in dataset
    ]
    weights = [0.0] * len(FEATURE_NAMES)
    bias = 0.0
    learning_rate = 0.08
    l2 = 0.002
    for _ in range(500):
        grad_w = [0.0] * len(weights)
        grad_b = 0.0
        for vector, label in vectors:
            prediction = _sigmoid(bias + sum(weight * value for weight, value in zip(weights, vector)))
            error = prediction - label
            grad_b += error
            for index, value in enumerate(vector):
                grad_w[index] += error * value
        sample_count = len(vectors)
        bias -= learning_rate * grad_b / sample_count
        for index in range(len(weights)):
            weights[index] -= learning_rate * (grad_w[index] / sample_count + l2 * weights[index])

    return (
        dict(zip(FEATURE_NAMES, weights)),
        {name: (means[name], scales[name]) for name in FEATURE_NAMES},
        bias,
        vectors,
    )


def _metrics(vectors: list[tuple[list[float], int]], weights: list[float], bias: float, threshold: float) -> dict[str, float]:
    true_positive = false_positive = false_negative = true_negative = 0
    for vector, label in vectors:
        probability = _sigmoid(bias + sum(weight * value for weight, value in zip(weights, vector)))
        predicted = probability >= threshold
        if predicted and label:
            true_positive += 1
        elif predicted:
            false_positive += 1
        elif label:
            false_negative += 1
        else:
            true_negative += 1
    precision = true_positive / max(1, true_positive + false_positive)
    recall = true_positive / max(1, true_positive + false_negative)
    f1 = 2 * precision * recall / max(0.0001, precision + recall)
    accuracy = (true_positive + true_negative) / max(1, len(vectors))
    return {
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def create_artifact(
    seed: int = 23,
    version: int = 1,
    telemetry_readings: list[dict[str, Any]] | None = None,
) -> dict[str, object]:
    if telemetry_readings:
        rows, dataset_metadata = _make_dataset_from_telemetry(telemetry_readings, seed)
    else:
        rows = _make_dataset(seed)
        dataset_metadata = {
            "source": "synthetic-building-telemetry-v1",
            "telemetry_samples": 0,
            "synthetic_samples": len(rows),
        }
    split = int(len(rows) * 0.8)
    weights, normalization, bias, _ = _fit_logistic(rows[:split])
    validation_vectors = [
        (
            [
                (features[name] - normalization[name][0]) / normalization[name][1]
                for name in FEATURE_NAMES
            ],
            label,
        )
        for features, label in rows[split:]
    ]
    vector_weights = [weights[name] for name in FEATURE_NAMES]
    best_threshold = 0.5
    best_metrics = _metrics(validation_vectors, vector_weights, bias, best_threshold)
    for candidate in [0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
        candidate_metrics = _metrics(validation_vectors, vector_weights, bias, candidate)
        if candidate_metrics["f1"] > best_metrics["f1"]:
            best_threshold, best_metrics = candidate, candidate_metrics

    payload: dict[str, object] = {
        "model_id": "edge-anomaly-logistic",
        "version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_dataset": str(dataset_metadata["source"]),
        "training_summary": dataset_metadata,
        "feature_names": list(FEATURE_NAMES),
        "normalization": {
            name: {"mean": round(normalization[name][0], 8), "scale": round(normalization[name][1], 8)}
            for name in FEATURE_NAMES
        },
        "weights": {name: round(weights[name], 8) for name in FEATURE_NAMES},
        "bias": round(bias, 8),
        "threshold": best_threshold,
        "metrics": best_metrics,
        "runtime": {"python_dependencies": [], "estimated_model_bytes": 0},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["artifact_sha256"] = hashlib.sha256(canonical).hexdigest()
    payload["runtime"] = {
        "python_dependencies": [],
        "estimated_model_bytes": len(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    }
    # Runtime metadata is part of the integrity payload, so calculate the final hash again.
    unsigned = {key: value for key, value in payload.items() if key != "artifact_sha256"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["artifact_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def write_firmware_header(path: str | Path, artifact: dict[str, object]) -> Path:
    destination = Path(path)
    normalization = artifact["normalization"]
    weights = artifact["weights"]
    names = artifact["feature_names"]
    means = ", ".join(f"{normalization[name]['mean']}f" for name in names)
    scales = ", ".join(f"{normalization[name]['scale']}f" for name in names)
    values = ", ".join(f"{weights[name]}f" for name in names)
    content = f'''#ifndef EDGE_MODEL_H
#define EDGE_MODEL_H

/* Generated from model_artifacts/edge_anomaly_v1.json. */
#define EDGE_MODEL_ID "{artifact["model_id"]}"
#define EDGE_MODEL_VERSION {artifact["version"]}
#define EDGE_MODEL_SHA256 "{artifact["artifact_sha256"]}"
#define EDGE_MODEL_THRESHOLD {artifact["threshold"]}f

static const float EDGE_MODEL_MEANS[6] = {{{means}}};
static const float EDGE_MODEL_SCALES[6] = {{{scales}}};
static const float EDGE_MODEL_WEIGHTS[6] = {{{values}}};
static const float EDGE_MODEL_BIAS = {artifact["bias"]}f;

#endif
'''
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    return destination


def save_artifact(
    path: str | Path,
    seed: int = 23,
    version: int = 1,
    firmware_path: str | Path | None = None,
    telemetry_readings: list[dict[str, Any]] | None = None,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    artifact = create_artifact(seed, version=version, telemetry_readings=telemetry_readings)
    destination.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    if firmware_path:
        write_firmware_header(firmware_path, artifact)
    return destination


if __name__ == "__main__":
    save_artifact(Path(__file__).parents[1] / "model_artifacts" / "edge_anomaly_v1.json")
    print("Wrote model_artifacts/edge_anomaly_v1.json")
