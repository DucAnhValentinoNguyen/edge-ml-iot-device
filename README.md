# EdgeLoop: ML on the device

EdgeLoop is a portfolio project showing how an ML model moves from a training
dataset into an IoT device runtime. It uses synthetic energy-harvesting-style
building telemetry and detects energy spikes, comfort drift, and device-health
faults.

The important boundary is deliberate:

```text
synthetic telemetry -> train + evaluate -> checksummed JSON artifact
                                      -> C firmware constants
                                      -> dependency-free device inference
                                      -> compact alert to the API
```

The cloud is an observability and fleet-management layer. It does not need to
receive every raw sample to know that a device has detected a problem.

## Run it

Requirements: Docker Desktop and Docker Compose.

```bash
cp .env.example .env
docker compose up --build
```

Open the dashboard at <http://localhost:3003> and the API docs at
<http://localhost:8000/docs>. The API seeds two devices, one with a historical
energy-spike event, so the dashboard is useful immediately.

To run a device simulator against the API from a Python environment:

```bash
python scripts/simulate_device.py --fault comfort_drift --steps 30
```

The simulator loads the same artifact as the device, makes the decision locally,
and posts the decision envelope to `/v1/telemetry`. Repeat the same event ID and
the API accepts it only once.

## What is implemented

- Deterministic synthetic telemetry with controllable fault injection.
- Logistic anomaly model trained with a fixed seed and exported to JSON.
- Artifact checksum verification before inference.
- Shared Python and framework-neutral C inference implementations.
- Fleet/device/deployment/telemetry/anomaly APIs with SQLite persistence.
- Idempotent telemetry ingestion and model deployment audit events.
- Operator-facing explanations and recommended investigation steps.
- Dashboard for model verification, live telemetry, and alert simulation.
- Model operations view for data quality, feature drift, candidate retraining, and safe rollout review.
- Gateway adapter with learn-in, demo profile decoding, deduplication, and health APIs.
- API tests, runtime tests, frontend typecheck/build, and Gitleaks CI.

## Model lifecycle

`edge_runtime/training.py` owns the small trainer. It standardizes six features,
fits logistic regression with gradient descent, selects a validation threshold,
and stores metrics with the artifact. Recreate the checked-in artifact with:

```bash
python scripts/train_model.py
```

The deployable runtime in `edge_runtime/` uses only `json`, `math`, and Python
standard-library types. The equivalent firmware implementation is
[`firmware/edge_inference.c`](firmware/edge_inference.c), with weights generated
into [`firmware/edge_model.h`](firmware/edge_model.h).

In a real rollout, a device would authenticate with mTLS, download a signed
artifact from object storage, verify its checksum and signature, canary the
model to a device cohort, and report model/version health over MQTT. This demo
keeps those boundaries visible without requiring a cloud account or physical
hardware.

## API highlights

| Endpoint | Purpose |
| --- | --- |
| `GET /v1/overview` | Dashboard fleet summary, model card, and recent alerts |
| `POST /v1/telemetry` | Receive a device heartbeat and edge inference envelope |
| `POST /v1/simulations` | Inject a repeatable fault into a synthetic device |
| `POST /v1/devices/{id}/deploy` | Record a verified model deployment |
| `GET /v1/devices/{id}/telemetry` | Inspect a device's recent samples |
| `GET /v1/anomalies` | Query explainable edge alerts |
| `POST /v1/models/train` | Retrain and reload the local artifact |
| `GET /v1/model-operations` | Inspect quality, drift, deployment, and retraining status |
| `POST /v1/models/retrain` | Create an isolated candidate artifact for review |
| `POST /v1/gateways/{id}/learn-in` | Discover an unknown device and suggest a profile |
| `POST /v1/onboarding/register` | Register a device profile and friendly location |
| `POST /v1/gateways/{id}/telegrams` | Decode a raw gateway telegram and run edge inference |

## Project layout

```text
edge_runtime/       device-compatible features, model loader, inference, trainer
model_artifacts/    versioned deployable model artifact
firmware/           C implementation of the same inference contract
backend/app/        FastAPI, validation, persistence, deployment endpoints
frontend/            Next.js fleet dashboard
scripts/             training and device-stream commands
gateway/             raw telegram adapter, profile registry, and deduplication
tests/               runtime and API tests
```

## Documentation

- [Presentation and demo runbook](docs/PRESENTATION_AND_DEMO.md)
- [Repository structure](docs/REPOSITORY_STRUCTURE.md)
- [Technical file guide](docs/TECHNICAL_FILE_GUIDE.md)

The presentation runbook covers the customer story, live walkthrough, API
sequence, and production hardening discussion. The additional docs explain the
folder layout and the responsibility of each committed file.
