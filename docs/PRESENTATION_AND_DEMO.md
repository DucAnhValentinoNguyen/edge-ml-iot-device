# 10-minute presentation and demo

## Presentation script

### 0:00-1:00 - The problem

"Connected buildings generate a continuous stream of temperature, humidity,
occupancy, energy, and device-health signals. Sending every raw sample to the
cloud increases bandwidth, latency, and operational cost. It also makes the
system less useful when connectivity is intermittent. The product I built is a
reference implementation for moving a small, explainable ML decision directly
onto the device or gateway, while keeping the cloud responsible for fleet
visibility, model governance, and operator workflows."

### 1:00-2:00 - The outcome

"The operator does not need to inspect thousands of normal readings. The edge
runtime turns telemetry into a compact decision: normal or anomalous, a
probability, the likely anomaly type, the contributing signals, and a suggested
next action. The dashboard shows the model version, checksum, device health,
recent telemetry, and alerts. This makes the result actionable and auditable,
not just a black-box score."

### 2:00-3:00 - Architecture

"The stack has four layers. First, a device and gateway layer accepts raw
wireless-style telegrams. Second, a dependency-light Python edge runtime
normalizes features and executes the model. Third, a FastAPI service persists
telemetry, deployments, alerts, and gateway onboarding data in SQLite for a
self-contained demo. Fourth, a Next.js and TypeScript dashboard provides fleet
operations. Everything is packaged with Docker Compose, and GitHub Actions runs
the quality checks."

### 3:00-4:00 - Data and protocol boundary

"The adapter deliberately separates protocol concerns from ML concerns. A raw
telegram has a gateway ID, source device ID, radio profile, payload bytes,
signal strength, security level, and timestamp. The adapter validates it,
removes repeated packets, applies a registered profile, and emits normalized
key-value readings. In production, this boundary is where a real gateway,
MQTT broker, or vendor codec would be connected. The rest of the application
does not need to know how the radio packet was transported."

### 4:00-5:00 - Model lifecycle

"The model is a compact logistic anomaly detector trained on deterministic
synthetic building telemetry. Training produces a versioned JSON artifact with
feature names, threshold, metrics, and a SHA-256 checksum. The same normalized
weights are exported as C constants for firmware. At startup, the service
verifies and loads the artifact. A deployment records the model ID, version,
checksum, and time, so an operator can answer which model made a decision."

### 5:00-6:00 - Reliability and safety

"The design treats edge inference as a product boundary. Input validation
rejects impossible values. Event IDs make telemetry idempotent. Duplicate radio
repetitions are tracked and removed within a configurable time window. The
dashboard surfaces signal quality, harvested energy, last-seen time, and model
health. The demo uses SQLite to stay portable, but the interfaces are ready to
move to PostgreSQL, object storage, MQTT, and a signed artifact registry."

### 6:00-7:00 - Customer value

"For a building operator, this means earlier detection of abnormal energy use,
comfort drift, or failing devices. For a platform owner, it means less data
movement, lower cloud cost, faster local decisions, and graceful behavior when
the network is unreliable. For engineering and compliance teams, it provides
reproducibility, model provenance, explicit validation, and a clear separation
between untrusted device input and trusted server-side records."

### 7:00-9:00 - Live demo

"I will first show the fleet view and the current model card. I will inject an
energy spike and show that the alert appears with an explanation. Then I will
open the API documentation and simulate a new gateway telegram. The gateway
first reports an unknown device and suggests a profile. I register that device,
send the same packet again, and show that it is decoded into temperature and
humidity and passed into the edge inference path. Finally, I will send the same
packet within the deduplication window and show that the repeated transmission
is not counted as a second telemetry reading."

### 9:00-10:00 - Close

"This is intentionally a production-shaped vertical slice rather than a claim
that a laptop is a finished certified device. It proves the important seams:
model-to-firmware export, protocol adaptation, local inference, explainable
alerts, fleet observability, onboarding, and idempotent ingestion. The next
production steps would be a hardware transport, signed model updates, mTLS,
cohort rollout, persistent MQTT integration, and validation against real device
data."

## Demo runbook

### Start

```powershell
docker compose up --build
```

Open:

- Dashboard: http://localhost:3003
- API documentation: http://localhost:8000/docs
- Health check: http://localhost:8000/healthz

The API seeds two devices and a historical alert, so the dashboard is useful
immediately.

### Show the model and local decision

1. Point out the model card, artifact checksum, feature count, threshold, and F1 score.
2. Select `Inject energy spike`.
3. Click `Run device simulation`.
4. Show the new alert, probability, explanation, energy chart, and recommended action in the API response if needed.
5. Click `Deploy v1` and point out the deployment event and unchanged checksum.

### Show gateway learn-in and decoding

In a second terminal, after the containers are ready:

```powershell
python scripts/simulate_gateway.py --learn-in --steps 3
```

Explain the sequence:

1. The raw payload arrives with a source device ID, radio profile, bytes, RSSI, and timestamp.
2. Learn-in returns candidate profiles without silently trusting an unknown device.
3. Registration assigns a friendly name and location.
4. The next telegram is decoded into key-value data and routed to the edge model.
5. Repeated packets are accepted at the ingress boundary but marked as duplicates and do not create another telemetry record.

Useful API calls to show in Swagger:

```text
GET  /v1/profiles
GET  /v1/gateways
GET  /v1/gateways/{gateway_id}/health
GET  /v1/onboarding
```

### Do not spend demo time on

- Retraining the model live unless someone asks about the lifecycle.
- The C firmware compilation details; show the generated header briefly and explain the contract.
- Database internals or the full source tree.
- Production cloud deployment, since this release intentionally runs locally.

### Honest positioning

The profile registry contains simplified demo decoders so the project remains
portable and testable without a physical radio gateway. For a production
deployment, replace those fixtures with the relevant official equipment profile
codec and connect the adapter to the site's gateway or MQTT transport.

## Technical references

- [IoT Connector documentation](https://iotconnector-docs.readthedocs.io/en/latest/)
- [MQTT API reference](https://iotconnector-docs.readthedocs.io/en/latest/api_reference/mqtt-API/)
- [Bidirectional MQTT interface](https://iotconnector-docs.readthedocs.io/en/latest/bidirectional/mqtt-interface/)
- [Edge computing overview](https://www.enocean.com/en/products/iot-edge-computing-solutions/)
- [IoT Connector white paper](https://www.enocean.com/wp-content/uploads/redaktion/pdf/white_paper/220608_White_Paper_IoT-Connector_final.pdf)
