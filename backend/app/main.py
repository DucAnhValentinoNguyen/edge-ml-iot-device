from __future__ import annotations

import json
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
store = TelemetryStore(settings.database_path)
gateway = GatewayAdapter()
production_artifact: ModelArtifact
candidate_artifact: ModelArtifact | None
runtimes: dict[int, EdgeRuntime]


def _candidate_metadata() -> dict[str, Any] | None:
    path = Path(settings.candidate_artifact_path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _reload_artifacts() -> None:
    global production_artifact, candidate_artifact, runtimes
    production_artifact = ModelArtifact.load(settings.model_artifact_path)
    candidate_path = Path(settings.candidate_artifact_path)
    candidate_artifact = (
        ModelArtifact.load(candidate_path) if candidate_path.exists() else None
    )
    runtimes = {production_artifact.version: EdgeRuntime(production_artifact)}
    if candidate_artifact:
        runtimes[candidate_artifact.version] = EdgeRuntime(candidate_artifact)


def _artifact_for_version(version: int | None) -> ModelArtifact:
    if version is None or version == production_artifact.version:
        return production_artifact
    if candidate_artifact and version == candidate_artifact.version:
        return candidate_artifact
    raise HTTPException(status_code=404, detail=f"Model version {version} is not available")


def _artifact_for_device(device_id: str) -> ModelArtifact:
    deployment = store.get_deployment(device_id)
    deployed_version = int(deployment["model_version"]) if deployment else None
    if deployed_version is None:
        return production_artifact
    try:
        return _artifact_for_version(deployed_version)
    except HTTPException:
        return production_artifact


def _runtime_for_device(device_id: str) -> EdgeRuntime:
    active = _artifact_for_device(device_id)
    return runtimes[active.version]


@asynccontextmanager
async def lifespan(_: FastAPI):
    _reload_artifacts()
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
            production_artifact.model_id,
            production_artifact.version,
            name=name,
            building=building,
            room=room,
        )
        for step in range(24):
            reading = generate_reading(device_id, step, fault=fault, start=start)
            reading["event_id"] = f"seed:{device_id}:{step}"
            prediction = _runtime_for_device(device_id).predict(reading)
            store.record_telemetry(reading, prediction.to_dict())
        store.deploy(
            device_id,
            production_artifact.model_id,
            production_artifact.version,
            production_artifact.artifact_sha256,
        )


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "edgeloop-api", "docs": "/docs", "health": "/healthz"}


@app.get("/healthz")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "model_loaded": True,
        "model_id": production_artifact.model_id,
        "model_version": production_artifact.version,
        "artifact_sha256": production_artifact.artifact_sha256,
        "candidate_version": candidate_artifact.version if candidate_artifact else None,
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
            prediction = _runtime_for_device(str(reading["device_id"])).predict(reading)
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
        source,
        payload.gateway_id,
        payload.profile_id,
        payload.friendly_id,
        payload.location,
        "operable",
        device_id,
    )
    store.ensure_device(
        device_id,
        production_artifact.model_id,
        production_artifact.version,
        name=payload.friendly_id,
        room=payload.location,
    )
    return {**registered, "device_id": device_id}


@app.get("/v1/overview")
def overview() -> dict[str, Any]:
    return {**store.overview(), "model": model_response(production_artifact)}


@app.get("/v1/devices")
def list_devices() -> list[dict[str, Any]]:
    return store.list_devices()


@app.get("/v1/devices/{device_id}")
def get_device(device_id: str) -> dict[str, Any]:
    device = store.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return {
        **device,
        "deployment": store.get_deployment(device_id),
        "available_versions": [
            production_artifact.version,
            *([candidate_artifact.version] if candidate_artifact else []),
        ],
    }


@app.get("/v1/devices/{device_id}/telemetry")
def device_telemetry(
    device_id: str, limit: int = Query(default=48, ge=1, le=500)
) -> list[dict[str, Any]]:
    if not store.get_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    return store.list_readings(device_id, limit)


@app.get("/v1/devices/{device_id}/events")
def device_events(
    device_id: str, limit: int = Query(default=40, ge=1, le=200)
) -> list[dict[str, Any]]:
    if not store.get_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    return store.list_events(device_id, limit)


@app.post("/v1/devices/{device_id}/deploy")
def deploy_model(device_id: str, payload: DeployPayload | None = None) -> dict[str, Any]:
    requested = payload or DeployPayload()
    target = _artifact_for_version(requested.version)
    if requested.model_id and requested.model_id != target.model_id:
        raise HTTPException(status_code=409, detail="Requested model is not available")
    return store.deploy(
        device_id,
        target.model_id,
        target.version,
        target.artifact_sha256,
    )


@app.get("/v1/devices/{device_id}/deployment")
def device_deployment(device_id: str) -> dict[str, Any]:
    deployment = store.get_deployment(device_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="No model deployment found")
    return deployment


@app.post("/v1/telemetry")
def ingest_telemetry(payload: TelemetryPayload) -> dict[str, Any]:
    reading = payload.model_dump(mode="json", exclude={"inference"})
    active_artifact = _artifact_for_device(payload.device_id)
    server_prediction = _runtime_for_device(payload.device_id).predict(reading)
    edge_prediction = (
        payload.inference.model_dump(mode="json")
        if payload.inference
        else server_prediction.to_dict()
    )
    accepted, reading_id = store.record_telemetry(reading, edge_prediction)
    return {
        "accepted": accepted,
        "reading_id": reading_id,
        "edge_inference": edge_prediction,
        "server_verification": {
            "verified": (
                edge_prediction.get("artifact_sha256") == active_artifact.artifact_sha256
                and abs(float(edge_prediction["probability"]) - server_prediction.probability) < 0.08
            ),
            "artifact_verified": edge_prediction.get("artifact_sha256") == active_artifact.artifact_sha256,
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


def model_response(active_artifact: ModelArtifact) -> dict[str, Any]:
    return {
        "model_id": active_artifact.model_id,
        "version": active_artifact.version,
        "artifact_sha256": active_artifact.artifact_sha256,
        "feature_names": list(active_artifact.feature_names),
        "threshold": active_artifact.threshold,
        "metrics": dict(active_artifact.metrics),
        "runtime_dependencies": [],
        "deployment_target": "Python / C-compatible edge runtime",
    }


@app.get("/v1/models/current")
def current_model() -> dict[str, Any]:
    metadata = _candidate_metadata()
    return {
        "production": model_response(production_artifact),
        "candidate": {**model_response(candidate_artifact), "trained_at": metadata.get("trained_at")} if candidate_artifact and metadata else None,
    }


@app.get("/v1/model-operations")
def model_operations() -> dict[str, Any]:
    metadata = _candidate_metadata()
    return store.model_operations(
        production_artifact.version,
        candidate_artifact=metadata,
    )


@app.post("/v1/models/train")
def train_model() -> dict[str, Any]:
    destination = Path(settings.model_artifact_path)
    save_artifact(
        destination,
        version=production_artifact.version,
        firmware_path=Path("firmware/edge_model.h"),
        telemetry_readings=store.training_readings(limit=700),
    )
    _reload_artifacts()
    return model_response(production_artifact)


@app.post("/v1/models/retrain")
def retrain_model() -> dict[str, Any]:
    destination = Path(settings.candidate_artifact_path)
    training_rows = store.training_readings(limit=700)
    save_artifact(
        destination,
        seed=47,
        version=production_artifact.version + 1,
        telemetry_readings=training_rows,
    )
    _reload_artifacts()
    metadata = _candidate_metadata() or {}
    candidate = _artifact_for_version(production_artifact.version + 1)
    return {
        "job_id": f"retrain-{uuid.uuid4().hex[:10]}",
        "status": "candidate_ready",
        "candidate": {
            "model_id": candidate.model_id,
            "version": candidate.version,
            "artifact_sha256": candidate.artifact_sha256,
            "metrics": dict(candidate.metrics),
            "trained_at": metadata.get("trained_at"),
            "training_samples": len(training_rows),
            "approval_required": True,
        },
        "production": model_response(production_artifact),
    }


@app.post("/v1/simulations")
def run_simulation(payload: SimulationPayload) -> dict[str, Any]:
    simulation_id = f"sim-{uuid.uuid4().hex[:10]}"
    start = datetime.now(timezone.utc) - timedelta(minutes=payload.steps - 1)
    fault_window = (max(0, payload.steps - 8), payload.steps - 1)
    anomalies_found = 0
    accepted = 0
    last_prediction: dict[str, Any] | None = None
    active_artifact = _artifact_for_device(payload.device_id)
    store.ensure_device(payload.device_id, active_artifact.model_id, active_artifact.version)
    for step in range(payload.steps):
        reading = generate_reading(
            payload.device_id,
            step,
            fault=payload.fault,
            seed=41,
            start=start,
            fault_window=fault_window,
        )
        reading["event_id"] = f"{simulation_id}:{step}"
        prediction = _runtime_for_device(payload.device_id).predict(reading)
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
        "model": model_response(_artifact_for_device(payload.device_id)),
        "last_edge_decision": last_prediction,
    }
