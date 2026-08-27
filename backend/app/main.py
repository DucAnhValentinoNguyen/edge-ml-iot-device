from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from edge_runtime import EdgeRuntime, ModelArtifact, generate_reading
from edge_runtime.training import save_artifact
from gateway import GatewayAdapter, RawTelegram

from .config import Settings
from .schemas import (
    DeployPayload,
    FeedbackPayload,
    RegisterDevicePayload,
    SimulationPayload,
    TelegramPayload,
    TelemetryPayload,
)
from .storage import TelemetryStore

settings = Settings()
artifact = ModelArtifact.load(settings.model_artifact_path)
runtime = EdgeRuntime(artifact)
store = TelemetryStore(settings.database_path)
gateway = GatewayAdapter()

@asynccontextmanager
async def lifespan(_: FastAPI):
    _seed_demo_data()
    yield


app = FastAPI(
    title="EdgeLoop Device Intelligence API",
    version="0.1.0",
    description="Telemetry, model deployment, and edge anomaly decisions for an IoT fleet.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _seed_demo_data() -> None:
    if store.list_devices():
        return
    start = datetime.now(timezone.utc) - timedelta(minutes=23)
    demo_devices = [
        ("node-room-01", "Room 01 / North wing", "North wing", "Room 01", "energy_spike"),
        ("node-room-02", "Room 02 / South wing", "South wing", "Room 02", None),
    ]
    for device_id, name, building, room, fault in demo_devices:
        store.ensure_device(
            device_id,
            artifact.model_id,
            artifact.version,
            name=name,
            building=building,
            room=room,
        )
        for step in range(24):
            reading = generate_reading(device_id, step, fault=fault, start=start)
            reading["event_id"] = f"seed:{device_id}:{step}"
            prediction = runtime.predict(reading)
            store.record_telemetry(reading, prediction.to_dict())
        store.deploy(device_id, artifact.model_id, artifact.version, artifact.artifact_sha256)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "edgeloop-api", "docs": "/docs", "health": "/healthz"}


@app.get("/healthz")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "model_loaded": True,
        "model_id": artifact.model_id,
        "model_version": artifact.version,
        "artifact_sha256": artifact.artifact_sha256,
    }


def _raw_telegram(payload: TelegramPayload) -> RawTelegram:
    try:
        return RawTelegram.from_payload(payload.model_dump(mode="json"))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _decoded_reading(result: dict[str, Any], source_eurid: str) -> dict[str, Any] | None:
    values = {item["key"]: item["value"] for item in result["decoded"]}
    if "temperature" not in values:
        return None
    onboarding = store.get_onboarding(source_eurid)
    device_id = onboarding["device_id"] if onboarding else None
    if not device_id:
        return None
    occupancy = bool(values.get("occupancy", False))
    return {
        "device_id": device_id,
        "timestamp": result["timestamp"],
        "temperature": float(values["temperature"]),
        "humidity": float(values.get("humidity", 45.0)),
        "occupancy": occupancy,
        "energy_usage": float(values.get("energy_usage", 1.2 if occupancy else 0.25)),
        "signal_quality": float(result["rssi"]) / 100.0,
        "harvested_energy": 0.18,
        "event_id": f"telegram:{result['telegram_id']}",
    }


@app.get("/v1/profiles")
def list_profiles() -> list[dict[str, Any]]:
    return gateway.registry.list()


@app.get("/v1/gateways")
def list_gateways() -> list[dict[str, Any]]:
    return store.list_gateways()


@app.get("/v1/gateways/{gateway_id}/health")
def gateway_health(gateway_id: str) -> dict[str, Any]:
    stored = next((item for item in store.list_gateways() if item["id"] == gateway_id), {})
    return {**stored, **gateway.health(gateway_id)}


@app.post("/v1/gateways/{gateway_id}/telegrams")
def ingest_telegram(gateway_id: str, payload: TelegramPayload) -> dict[str, Any]:
    telegram = _raw_telegram(payload)
    if telegram.gateway_id != gateway_id:
        raise HTTPException(status_code=409, detail="gateway_id in path and payload must match")
    result = gateway.ingest(telegram)
    result_dict = result.to_dict()
    gateway_payload = payload.model_dump(mode="json")
    gateway_payload["timestamp"] = result_dict["timestamp"]
    accepted = store.record_gateway_telegram(gateway_payload, result_dict)
    telemetry_recorded = False
    if accepted and result.known_device and not result.duplicate:
        reading = _decoded_reading(result_dict, telegram.source_eurid)
        if reading:
            prediction = runtime.predict(reading)
            telemetry_recorded, _ = store.record_telemetry(reading, prediction.to_dict())
    return {
        "accepted": accepted,
        "telemetry_recorded": telemetry_recorded,
        "mqtt_topic": f"sensor/{telegram.source_eurid}/telemetry",
        "ingress": result_dict,
    }


@app.post("/v1/gateways/{gateway_id}/learn-in")
def learn_in(gateway_id: str, payload: TelegramPayload) -> dict[str, Any]:
    telegram = _raw_telegram(payload)
    if telegram.gateway_id != gateway_id:
        raise HTTPException(status_code=409, detail="gateway_id in path and payload must match")
    result = gateway.learn_in(telegram)
    result_dict = result["telegram"]
    gateway_payload = payload.model_dump(mode="json")
    gateway_payload["timestamp"] = result_dict["timestamp"]
    store.record_gateway_telegram(gateway_payload, result_dict)
    if result["status"] == "pending_registration" and result["candidates"]:
        candidate = result["candidates"][0]
        store.upsert_onboarding(
            telegram.source_eurid,
            gateway_id,
            candidate["profile_id"],
            f"New device {telegram.source_eurid}",
            "Unassigned",
            "pending_registration",
        )
    return result


@app.get("/v1/onboarding")
def onboarding(status: str | None = None) -> list[dict[str, Any]]:
    return store.list_onboarding(status)


@app.post("/v1/onboarding/register")
def register_device(payload: RegisterDevicePayload) -> dict[str, Any]:
    source = payload.source_eurid.replace(" ", "").upper()
    try:
        registered = gateway.register_device(
            source, payload.profile_id, payload.friendly_id, payload.location
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    device_id = payload.device_id or f"node-{source.lower()}"
    store.upsert_onboarding(
        source, payload.gateway_id, payload.profile_id, payload.friendly_id,
        payload.location, "operable", device_id,
    )
    store.ensure_device(device_id, artifact.model_id, artifact.version, name=payload.friendly_id, room=payload.location)
    return {**registered, "device_id": device_id}


@app.get("/v1/overview")
def overview() -> dict[str, Any]:
    return {**store.overview(), "model": model_response()}


@app.get("/v1/devices")
def list_devices() -> list[dict[str, Any]]:
    return store.list_devices()


@app.get("/v1/devices/{device_id}")
def get_device(device_id: str) -> dict[str, Any]:
    device = store.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return {**device, "deployment": store.get_deployment(device_id)}


@app.get("/v1/devices/{device_id}/telemetry")
def device_telemetry(
    device_id: str, limit: int = Query(default=48, ge=1, le=500)
) -> list[dict[str, Any]]:
    if not store.get_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    return store.list_readings(device_id, limit)


@app.get("/v1/devices/{device_id}/events")
def device_events(device_id: str, limit: int = Query(default=40, ge=1, le=200)) -> list[dict[str, Any]]:
    if not store.get_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    return store.list_events(device_id, limit)


@app.post("/v1/devices/{device_id}/deploy")
def deploy_model(device_id: str, payload: DeployPayload | None = None) -> dict[str, Any]:
    requested = payload or DeployPayload()
    if requested.model_id and requested.model_id != artifact.model_id:
        raise HTTPException(status_code=409, detail="Requested model is not available")
    if requested.version and requested.version != artifact.version:
        raise HTTPException(status_code=409, detail="Requested model version is not available")
    return store.deploy(device_id, artifact.model_id, artifact.version, artifact.artifact_sha256)


@app.get("/v1/devices/{device_id}/deployment")
def device_deployment(device_id: str) -> dict[str, Any]:
    deployment = store.get_deployment(device_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="No model deployment found")
    return deployment


@app.post("/v1/telemetry")
def ingest_telemetry(payload: TelemetryPayload) -> dict[str, Any]:
    global runtime
    reading = payload.model_dump(mode="json", exclude={"inference"})
    server_prediction = runtime.predict(reading)
    edge_prediction = payload.inference.model_dump(mode="json") if payload.inference else server_prediction.to_dict()
    accepted, reading_id = store.record_telemetry(reading, edge_prediction)
    return {
        "accepted": accepted,
        "reading_id": reading_id,
        "edge_inference": edge_prediction,
        "server_verification": {
            "verified": (
                edge_prediction.get("artifact_sha256") == artifact.artifact_sha256
                and abs(float(edge_prediction["probability"]) - server_prediction.probability) < 0.08
            ),
            "artifact_verified": edge_prediction.get("artifact_sha256") == artifact.artifact_sha256,
            "model_id": server_prediction.model_id,
            "model_version": server_prediction.model_version,
        },
    }


@app.get("/v1/anomalies")
def anomalies(
    device_id: str | None = None, limit: int = Query(default=30, ge=1, le=200)
) -> list[dict[str, Any]]:
    return store.list_anomalies(device_id, limit)


@app.get("/v1/anomalies/{reading_id}")
def anomaly(reading_id: str) -> dict[str, Any]:
    item = store.get_reading(reading_id)
    if not item:
        raise HTTPException(status_code=404, detail="Anomaly reading not found")
    return item


@app.post("/v1/anomalies/{reading_id}/feedback")
def anomaly_feedback(reading_id: str, payload: FeedbackPayload) -> dict[str, Any]:
    item = store.add_feedback(reading_id, payload.label, payload.note)
    if not item:
        raise HTTPException(status_code=404, detail="Anomaly reading not found")
    return item


def model_response() -> dict[str, Any]:
    return {
        "model_id": artifact.model_id,
        "version": artifact.version,
        "artifact_sha256": artifact.artifact_sha256,
        "feature_names": list(artifact.feature_names),
        "threshold": artifact.threshold,
        "metrics": dict(artifact.metrics),
        "runtime_dependencies": [],
        "deployment_target": "Python / C-compatible edge runtime",
    }


@app.get("/v1/models/current")
def current_model() -> dict[str, Any]:
    return model_response()


@app.post("/v1/models/train")
def train_model() -> dict[str, Any]:
    global artifact, runtime
    destination = Path(settings.model_artifact_path)
    save_artifact(destination, firmware_path=Path("firmware/edge_model.h"))
    artifact = ModelArtifact.load(destination)
    runtime = EdgeRuntime(artifact)
    return model_response()


@app.post("/v1/simulations")
def run_simulation(payload: SimulationPayload) -> dict[str, Any]:
    simulation_id = f"sim-{uuid.uuid4().hex[:10]}"
    start = datetime.now(timezone.utc) - timedelta(minutes=payload.steps - 1)
    anomalies_found = 0
    accepted = 0
    last_prediction: dict[str, Any] | None = None
    store.ensure_device(payload.device_id, artifact.model_id, artifact.version)
    for step in range(payload.steps):
        reading = generate_reading(
            payload.device_id,
            step,
            fault=payload.fault,
            seed=41,
            start=start,
        )
        reading["event_id"] = f"{simulation_id}:{step}"
        prediction = runtime.predict(reading)
        inserted, _ = store.record_telemetry(reading, prediction.to_dict())
        accepted += int(inserted)
        anomalies_found += int(prediction.is_anomaly)
        last_prediction = prediction.to_dict()
    return {
        "simulation_id": simulation_id,
        "device_id": payload.device_id,
        "fault": payload.fault,
        "readings_ingested": accepted,
        "anomalies_detected": anomalies_found,
        "model": model_response(),
        "last_edge_decision": last_prediction,
    }
