from pathlib import Path

from edge_runtime import EdgeRuntime, ModelArtifact, generate_reading
from edge_runtime.training import create_artifact


ARTIFACT = Path(__file__).parents[1] / "model_artifacts" / "edge_anomaly_v1.json"


def test_artifact_checksum_and_dependency_free_runtime() -> None:
    artifact = ModelArtifact.load(ARTIFACT)
    assert artifact.artifact_sha256
    assert artifact.feature_names
    assert artifact.metrics["f1"] > 0.9


def test_normal_reading_is_not_flagged() -> None:
    runtime = EdgeRuntime(ModelArtifact.load(ARTIFACT))
    prediction = runtime.predict(generate_reading("test-device", 4))
    assert not prediction.is_anomaly
    assert prediction.anomaly_type == "none"


def test_energy_fault_is_detected_and_explained() -> None:
    runtime = EdgeRuntime(ModelArtifact.load(ARTIFACT))
    prediction = runtime.predict(generate_reading("test-device", 10, fault="energy_spike"))
    assert prediction.is_anomaly
    assert prediction.anomaly_type == "energy_spike"
    assert "baseline" in prediction.explanation
    assert prediction.top_contributors


def test_training_is_reproducible_for_fixed_seed() -> None:
    first = create_artifact(seed=31)
    second = create_artifact(seed=31)
    assert first["weights"] == second["weights"]
    assert first["metrics"] == second["metrics"]

