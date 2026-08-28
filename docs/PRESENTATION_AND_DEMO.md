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
next action. The dashboard only shows the operational surface that matters:
fleet status, recent telemetry, active alerts, model provenance, drift signals,
and retraining readiness. This makes the result actionable and auditable, not
just a black-box score."

### 2:00-3:00 - Architecture

"The stack has five layers. First, a simulated sensor or telegram source emits
temperature, humidity, occupancy, energy, signal, and harvested-energy data.
Second, a gateway adapter handles learn-in, profile decoding, deduplication,
and raw-packet validation. Third, a dependency-light Python edge runtime
normalizes the six model features and executes the anomaly model locally.
Fourth, a FastAPI backend persists telemetry, deployments, alerts, gateway
state, onboarding records, and model-operation signals in SQLite for a
self-contained demo. Fifth, a Next.js and TypeScript dashboard provides the
operator experience. Docker Compose runs the full stack locally, and GitHub
Actions covers tests, builds, and secret scanning."

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
verifies and loads the production artifact. The operations view then calculates
data-quality signals, drift indicators, and candidate retraining readiness from
accepted telemetry. A deployment records the model ID, version, checksum, and
time, so an operator can answer which model made a decision and whether a new
candidate should be reviewed before rollout."

### 5:00-6:00 - Reliability and safety

"The design treats edge inference as a product boundary. Input validation
rejects impossible values. Event IDs make telemetry idempotent. Duplicate radio
repetitions are tracked and removed within a configurable time window. The
backend can compare an edge-supplied decision envelope with a server-side
verification pass, so the cloud can confirm that the reported model checksum
matches the expected production artifact. The demo uses SQLite to stay
portable, but the interfaces are ready to move to PostgreSQL, object storage,
MQTT, signed artifact registries, and staged rollout workflows."

### 6:00-7:00 - Customer value

"For a building operator, this means earlier detection of abnormal energy use,
comfort drift, or failing devices without waiting for a round trip to the
cloud. For a platform owner, it means less data movement, lower cloud cost,
faster local decisions, and graceful behavior when the network is unreliable.
For engineering and compliance teams, it provides reproducibility, model
provenance, explicit validation, drift visibility, and a clear separation
between untrusted device input and trusted server-side records."

### 7:00-9:00 - Live demo

"I will start directly in the dashboard because it now opens straight into the
operational surface. First I will show the fleet metrics, a selected device,
its local telemetry trend, and the deployed model card.

Next I will inject an
energy spike and show a new alert with probability and explanation. Then I will
move to the model-operations area and explain drift, reviewed labels, and
candidate retraining. After that, I will open the API documentation and
simulate a new gateway telegram. The gateway first reports an unknown device
and suggests a profile. I register that device, send the same packet again, and
show that it is decoded into normalized values and passed into the edge
inference path. Finally, I send the same packet within the deduplication window
and show that the repeated transmission is not counted as a second telemetry
reading."

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

### What the dashboard means

Use this explanation while the dashboard is on screen:

1. The device or gateway produces telemetry locally.
2. The edge runtime scores the reading on-device or at the gateway boundary.
3. The backend stores the reading, decision, deployment metadata, and alert history.
4. The dashboard is the operator layer. It does not run the model itself; it shows the inputs, the decision outcome, model provenance, and fleet health.

### Show the model and local decision

1. Point out the compact simulation strip at the top and explain it is your fault-injection control for the demo.
2. Point out the metrics row, selected device, telemetry chart, and model card.
3. Explain that the model card proves the same artifact contract exists across Python training, backend verification, and C firmware export.
4. Select `Inject energy spike`.
5. Click `Run simulation`.
6. Show the new alert, probability, explanation, and device chart movement.
7. Click `Deploy v1` and point out the deployment event and unchanged checksum.

### Show drift monitoring and candidate retraining

1. Move to `MODEL OPERATIONS` and explain that drift is derived from accepted live telemetry, not a random placeholder.
2. Point out data quality, low-signal readings, reviewed labels, and the drift feature bars.
3. Move to `LIFECYCLE` and explain the separation between production and candidate models.
4. Click `Train candidate model`.
5. Explain that the action creates a reviewable candidate artifact and does not silently replace the production model.

### Show gateway learn-in and decoding

In a second terminal, after the containers are ready:

```powershell
python scripts/simulate_gateway.py --learn-in --steps 3
```

Explain the sequence:

1. The raw payload arrives with a gateway ID, source device ID, radio profile, payload bytes, RSSI, and timestamp.
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
GET  /v1/model-operations
POST /v1/models/retrain
```

### Optional technical proof points if they ask

1. Open `firmware/edge_model.h` and explain that the trained artifact is exported as C constants for embedded integration.
2. Open `/v1/models/current` or `/healthz` and show model version plus checksum.
3. Open `/v1/devices/{device_id}/telemetry` and show that stored readings already include the inference envelope.

### Do not spend demo time on

1. Database internals or the full source tree.
2. Full training math unless the audience explicitly wants the ML details.
3. Production cloud deployment, since this release intentionally runs locally.
4. Claiming that the demo laptop is a certified edge device; position it as a production-shaped reference implementation.

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
