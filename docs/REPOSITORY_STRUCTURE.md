# Repository Structure

This document explains the repository layout for `edge-ml-iot-device`, including
the purpose of each major directory and the local-only folders that are expected
to exist during development.

## Top-level tree

```text
edge-ml-iot-device/
|-- .github/
|   `-- workflows/
|       `-- ci.yml
|-- backend/
|   |-- __init__.py
|   |-- Dockerfile
|   |-- requirements.txt
|   `-- app/
|       |-- __init__.py
|       |-- config.py
|       |-- main.py
|       |-- schemas.py
|       `-- storage.py
|-- docs/
|   |-- PRESENTATION_AND_DEMO.md
|   |-- REPOSITORY_STRUCTURE.md
|   `-- TECHNICAL_FILE_GUIDE.md
|-- edge_runtime/
|   |-- __init__.py
|   |-- features.py
|   |-- model.py
|   |-- runtime.py
|   |-- telemetry.py
|   `-- training.py
|-- firmware/
|   |-- README.md
|   |-- edge_inference.c
|   |-- edge_inference.h
|   `-- edge_model.h
|-- frontend/
|   |-- Dockerfile
|   |-- next-env.d.ts
|   |-- next.config.mjs
|   |-- package-lock.json
|   |-- package.json
|   |-- tsconfig.json
|   `-- app/
|       |-- globals.css
|       |-- layout.tsx
|       `-- page.tsx
|-- gateway/
|   |-- __init__.py
|   |-- adapter.py
|   `-- profiles.py
|-- model_artifacts/
|   `-- edge_anomaly_v1.json
|-- scripts/
|   |-- simulate_device.py
|   |-- simulate_gateway.py
|   `-- train_model.py
|-- tests/
|   |-- test_api.py
|   |-- test_gateway.py
|   `-- test_runtime.py
|-- .dockerignore
|-- .env.example
|-- .gitignore
|-- docker-compose.yml
|-- pyproject.toml
|-- README.md
`-- uv.lock
```

## Local-only development folders

These folders are intentionally ignored by Git and should not be pushed:

```text
.venv/          local Python environment
.pytest_cache/  pytest cache artifacts
frontend/.next/ Next.js build output
frontend/node_modules/ installed frontend dependencies
data/           runtime SQLite database and other local state
```

## Directory responsibilities

- `.github/workflows/`: GitHub Actions automation for CI and secret scanning.
- `backend/`: FastAPI application, request validation, persistence, and API surface.
- `docs/`: presentation material and internal technical documentation.
- `edge_runtime/`: portable ML training and inference code shared across the simulator and backend.
- `firmware/`: C-facing deployment boundary for device-side inference.
- `frontend/`: Next.js dashboard for fleet visibility and demo interaction.
- `gateway/`: raw telegram onboarding, decoding, deduplication, and gateway health logic.
- `model_artifacts/`: checked-in deployable model artifacts produced by training.
- `scripts/`: command-line helpers for retraining and end-to-end demo simulation.
- `tests/`: regression coverage for runtime logic, gateway flows, and API behavior.

## Data flow through the repo

```text
edge_runtime/training.py
-> model_artifacts/edge_anomaly_v1.json
-> firmware/edge_model.h
-> backend/app/main.py loads artifact
-> frontend/app/page.tsx visualizes device and alert state

scripts/simulate_device.py
-> backend /v1/telemetry
-> backend/app/storage.py
-> frontend overview and device charts

scripts/simulate_gateway.py
-> gateway/adapter.py
-> backend onboarding + telegram endpoints
-> decoded telemetry may enter the same edge inference path
```
