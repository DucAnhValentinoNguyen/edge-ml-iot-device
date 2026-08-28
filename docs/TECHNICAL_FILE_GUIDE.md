# Technical File Guide

This guide describes the responsibility of each committed file in the
`edge-ml-iot-device` repository.

## Repository root

| File | Responsibility |
| --- | --- |
| `README.md` | Main project overview, setup steps, architectural framing, and API summary for the portfolio demo. |
| `docker-compose.yml` | Runs the FastAPI backend and Next.js frontend together with the expected ports, environment variables, and persistent volume for the SQLite database. |
| `.env.example` | Safe environment template for local development and Docker startup. |
| `.gitignore` | Excludes local environments, build output, databases, logs, and other non-source artifacts from Git. |
| `.dockerignore` | Keeps unnecessary local files out of Docker build contexts so builds stay smaller and cleaner. |
| `pyproject.toml` | Python project metadata plus pytest and Ruff tool configuration. |
| `uv.lock` | Locked Python dependency resolution for reproducible local environments when using `uv`. |

## GitHub automation

| File | Responsibility |
| --- | --- |
| `.github/workflows/ci.yml` | Runs Python tests, Python bytecode compilation, frontend type checking, frontend production build, and Gitleaks secret scanning on pushes and pull requests. |

## Backend package

| File | Responsibility |
| --- | --- |
| `backend/__init__.py` | Marks `backend` as a Python package. |
| `backend/requirements.txt` | Minimal backend dependency list: FastAPI, Pydantic, Uvicorn, and HTTPX. |
| `backend/Dockerfile` | Builds the backend container image, installs Python dependencies, and copies the runtime, gateway, artifact, firmware, and API code into the image. |

## Backend application

| File | Responsibility |
| --- | --- |
| `backend/app/__init__.py` | Marks `backend.app` as a Python package. |
| `backend/app/config.py` | Reads environment-based settings such as database path, model artifact path, and allowed CORS origins. |
| `backend/app/schemas.py` | Defines Pydantic request models for telemetry ingestion, simulation, deployment, feedback, gateway telegrams, and onboarding registration. |
| `backend/app/storage.py` | Owns the SQLite schema and persistence methods for devices, readings, alerts, deployments, gateways, raw telegrams, and onboarding records. |
| `backend/app/main.py` | FastAPI entry point that seeds demo data, loads the model artifact, wires the gateway adapter, exposes all API endpoints, and coordinates inference plus persistence flows. |

## Edge runtime

| File | Responsibility |
| --- | --- |
| `edge_runtime/__init__.py` | Re-exports the main runtime primitives used by scripts, tests, and the backend. |
| `edge_runtime/features.py` | Extracts the six model features from raw readings and produces operator-friendly anomaly labels plus explanations. |
| `edge_runtime/model.py` | Loads the deployable JSON artifact, validates its schema, verifies its SHA-256 checksum, and computes probability scores and feature contributions. |
| `edge_runtime/runtime.py` | Wraps the artifact in a prediction API that returns anomaly flags, explanations, feature values, top contributors, and model provenance. |
| `edge_runtime/telemetry.py` | Generates deterministic synthetic telemetry with optional injected energy, comfort, and device-health faults for demos and tests. |
| `edge_runtime/training.py` | Builds the training dataset, fits the logistic model, evaluates candidate thresholds, writes the artifact JSON, and exports C constants into the firmware header. |

## Gateway module

| File | Responsibility |
| --- | --- |
| `gateway/__init__.py` | Re-exports the gateway adapter and profile registry as the public gateway module surface. |
| `gateway/adapter.py` | Validates raw telegrams, derives deduplication keys, tracks duplicate windows, performs learn-in flows, decodes known devices, and reports gateway health statistics. |
| `gateway/profiles.py` | Stores the simplified demo equipment-profile registry and the decoder functions used to translate raw payload bytes into normalized key-value fields. |

## Firmware boundary

| File | Responsibility |
| --- | --- |
| `firmware/README.md` | Explains how the C inference code is intended to be embedded in a real device or gateway firmware loop. |
| `firmware/edge_inference.h` | Defines the device-side C input and output structs and the `edge_infer` function signature. |
| `firmware/edge_inference.c` | Implements heap-free C inference using the same six engineered features and logistic score calculation as the Python runtime. |
| `firmware/edge_model.h` | Generated header containing model ID, version, checksum, threshold, normalization values, weights, and bias used by the C inference code. |

## Frontend dashboard

| File | Responsibility |
| --- | --- |
| `frontend/package.json` | Frontend package manifest with Next.js, React, TypeScript, and the local development scripts. |
| `frontend/package-lock.json` | NPM lockfile that pins frontend dependency versions for reproducible installs. |
| `frontend/tsconfig.json` | TypeScript compiler configuration for the Next.js application. |
| `frontend/next.config.mjs` | Next.js runtime configuration with React strict mode enabled. |
| `frontend/next-env.d.ts` | Next.js generated type definitions required by TypeScript. |
| `frontend/Dockerfile` | Builds the frontend container image and starts the Next.js development server inside Docker. |
| `frontend/app/layout.tsx` | Root layout and metadata for the dashboard app. |
| `frontend/app/page.tsx` | Main fleet dashboard UI, including overview loading, device selection, simulation triggering, deployment actions, telemetry charts, alert display, and model-operations lifecycle panels. |
| `frontend/app/globals.css` | Global visual system, layout rules, typography, responsive behavior, and component styling for the dashboard. |

## Model artifacts

| File | Responsibility |
| --- | --- |
| `model_artifacts/edge_anomaly_v1.json` | Versioned deployable model artifact containing weights, normalization stats, threshold, metrics, runtime metadata, and checksum. |

## Utility scripts

| File | Responsibility |
| --- | --- |
| `scripts/train_model.py` | Rebuilds the JSON model artifact and generated C header from the training pipeline. |
| `scripts/simulate_device.py` | Simulates a device that performs inference locally, then posts telemetry plus its decision envelope to the backend API. |
| `scripts/simulate_gateway.py` | Simulates raw gateway telegram ingestion, learn-in, profile registration, and repeated telemetry delivery through the gateway endpoints. |

## Tests

| File | Responsibility |
| --- | --- |
| `tests/test_runtime.py` | Verifies artifact integrity, normal-vs-anomalous runtime behavior, explanation output, and deterministic training results. |
| `tests/test_gateway.py` | Verifies unknown-device profile suggestions, successful device registration and decode behavior, duplicate suppression, and telegram validation. |
| `tests/test_api.py` | Verifies health and overview endpoints, idempotent telemetry ingestion, simulation behavior, and the gateway learn-in to onboarding to inference API flow. |

## Supporting docs

| File | Responsibility |
| --- | --- |
| `docs/PRESENTATION_AND_DEMO.md` | Speaker notes and demo choreography for a 10-minute product presentation. |
| `docs/REPOSITORY_STRUCTURE.md` | Repository tree plus folder-level architectural explanation. |
| `docs/TECHNICAL_FILE_GUIDE.md` | This file; file-by-file explanation of the repository. |

## Notes on generated or runtime content

- `frontend/.next/`, `frontend/node_modules/`, `.venv/`, `.pytest_cache/`, and `data/` are local build or runtime artifacts and are intentionally excluded from Git.
- `frontend/next-env.d.ts`, `frontend/package-lock.json`, `model_artifacts/edge_anomaly_v1.json`, and `firmware/edge_model.h` are generated or tool-managed files, but they are committed because they are part of the demo's reproducibility and deployment story.
