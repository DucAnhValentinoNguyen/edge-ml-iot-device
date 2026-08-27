import uuid

from fastapi.testclient import TestClient

from backend.app.main import app


def test_health_and_overview() -> None:
    with TestClient(app) as client:
        health = client.get("/healthz")
        overview = client.get("/v1/overview")
    assert health.status_code == 200
    assert health.json()["model_loaded"] is True
    assert overview.status_code == 200
    assert overview.json()["devices"]


def test_telemetry_event_is_idempotent() -> None:
    payload = {
        "device_id": "api-test-device",
        "timestamp": "2026-08-26T12:00:00+00:00",
        "temperature": 21.0,
        "humidity": 45.0,
        "occupancy": True,
        "energy_usage": 1.3,
        "signal_quality": 0.95,
        "harvested_energy": 0.18,
        "event_id": f"api-test-event-{uuid.uuid4().hex}",
    }
    with TestClient(app) as client:
        first = client.post("/v1/telemetry", json=payload)
        second = client.post("/v1/telemetry", json=payload)
    assert first.status_code == 200
    assert first.json()["accepted"] is True
    assert first.json()["server_verification"]["artifact_verified"] is True
    assert second.status_code == 200
    assert second.json()["accepted"] is False


def test_simulation_creates_edge_alerts() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/v1/simulations",
            json={"device_id": "api-simulation-device", "fault": "device_health", "steps": 18},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["readings_ingested"] == 18
    assert body["anomalies_detected"] > 0


def test_gateway_learn_in_register_and_ingest() -> None:
    source = f"{uuid.uuid4().int % 0xFFFFFFFF:08X}"
    raw = {
        "gateway_id": "gateway-api-test",
        "source_eurid": source,
        "rorg": "A5",
        "data_hex": "80B40000",
        "timestamp": "2026-08-26T12:00:00+00:00",
        "rssi": 88,
    }
    with TestClient(app) as client:
        learned = client.post("/v1/gateways/gateway-api-test/learn-in", json=raw)
        assert learned.status_code == 200
        assert learned.json()["status"] == "pending_registration"
        registration = client.post(
            "/v1/onboarding/register",
            json={
                "gateway_id": "gateway-api-test",
                "source_eurid": source,
                "profile_id": "A5-04-03",
                "friendly_id": "API test sensor",
                "location": "Test room",
            },
        )
        assert registration.status_code == 200
        raw["timestamp"] = "2026-08-26T12:00:01+00:00"
        ingested = client.post("/v1/gateways/gateway-api-test/telegrams", json=raw)
    assert ingested.status_code == 200
    assert ingested.json()["ingress"]["known_device"] is True
    assert ingested.json()["telemetry_recorded"] is True
