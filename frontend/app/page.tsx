"use client";

import { useEffect, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Model = {
  model_id: string;
  version: number;
  artifact_sha256: string;
  threshold: number;
  metrics: { accuracy: number; precision: number; recall: number; f1: number };
  deployment_target: string;
};

type ModelCatalog = {
  production: Model;
  candidate: Model | null;
};

type Device = {
  id: string;
  name: string;
  building: string;
  room: string;
  firmware_version: string;
  model_id: string;
  model_version: number;
  battery_pct: number;
  signal_quality: number;
  online: boolean;
  last_seen: string;
  anomaly_count: number;
};

type Inference = {
  probability: number;
  is_anomaly: boolean;
  anomaly_type: string;
  explanation: string;
  recommended_action: string;
  model_version: number;
};

type Reading = {
  id: string;
  device_id: string;
  timestamp: string;
  temperature: number;
  humidity: number;
  occupancy: boolean;
  energy_usage: number;
  signal_quality: number;
  harvested_energy: number;
  inference: Inference;
  feedback_label?: string;
};

type Overview = {
  total_readings: number;
  anomalies: number;
  edge_decisions: number;
  bandwidth_saved_pct: number;
  online_devices: number;
  devices: Device[];
  latest_anomalies: Reading[];
  model: Model;
};

type ModelOperations = {
  data_quality: { score: number; readings: number; low_signal_readings: number; reviewed_labels: number; status: string };
  drift: { score: number; threshold: number; status: string; features: { name: string; baseline: number; current: number; psi: number }[] };
  retraining: {
    status: string;
    candidate_version: number;
    training_window: string;
    candidate_metrics: { precision: number; recall: number; f1: number };
    candidate_artifact_sha256?: string | null;
    trained_at?: string | null;
  };
  deployment: { production_version: number; rollout: string; rollback_available: boolean };
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, options);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

function formatAge(value: string) {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 60000));
  return minutes < 1 ? "just now" : `${minutes}m ago`;
}

function Sparkline({ readings, maxValue }: { readings: Reading[]; maxValue: number }) {
  const points = readings.map((reading, index) => {
    const x = readings.length === 1 ? 50 : (index / (readings.length - 1)) * 100;
    const normalized = maxValue <= 0 ? 0 : reading.energy_usage / maxValue;
    const y = 90 - Math.min(78, normalized * 78);
    return `${x},${y}`;
  });
  return (
    <svg className="sparkline" viewBox="0 0 100 90" preserveAspectRatio="none" aria-label="Energy trend">
      <defs>
        <linearGradient id="spark-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#f4a261" stopOpacity=".35" />
          <stop offset="1" stopColor="#f4a261" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,90 ${points.join(" ")} 100,90`} fill="url(#spark-fill)" />
      <polyline points={points.join(" ")} fill="none" stroke="#f4a261" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export default function Home() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [readings, setReadings] = useState<Reading[]>([]);
  const [fault, setFault] = useState<"energy_spike" | "comfort_drift" | "device_health">("energy_spike");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [operations, setOperations] = useState<ModelOperations | null>(null);
  const [models, setModels] = useState<ModelCatalog | null>(null);
  const [retraining, setRetraining] = useState(false);
  const selected = overview?.devices.find((device) => device.id === selectedId) || overview?.devices[0];
  const latestReading = readings.at(-1);
  const activeModel =
    selected?.model_version && models?.candidate && selected.model_version === models.candidate.version
      ? models.candidate
      : models?.production || overview?.model;
  const chartMax = Math.max(0.8, ...readings.map((reading) => reading.energy_usage));
  const chartTicks = [chartMax, chartMax * 0.67, chartMax * 0.33, 0];
  const deployVersion =
    operations?.retraining.status === "candidate_ready"
      ? operations.retraining.candidate_version
      : activeModel?.version;

  async function refresh(nextDeviceId?: string) {
    try {
      setError("");
      const next = await request<Overview>("/v1/overview");
      setOverview(next);
      setOperations(await request<ModelOperations>("/v1/model-operations"));
      setModels(await request<ModelCatalog>("/v1/models/current"));
      const preferredDeviceId = nextDeviceId || selectedId;
      const deviceId = next.devices.some((device) => device.id === preferredDeviceId)
        ? preferredDeviceId
        : next.devices[0]?.id;
      if (deviceId) {
        setSelectedId(deviceId);
        setReadings(await request<Reading[]>(`/v1/devices/${deviceId}/telemetry?limit=36`));
      } else {
        setSelectedId("");
        setReadings([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "The device API is unavailable.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function runSimulation() {
    try {
      setBusy(true);
      setError("");
      await request("/v1/simulations", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ device_id: selected?.id || overview?.devices[0]?.id || "node-room-01", fault, steps: 24 }),
      });
      await refresh(selected?.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function deploy() {
    if (!selected || !deployVersion) return;
    try {
      setBusy(true);
      setError("");
      await request(`/v1/devices/${selected.id}/deploy`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ version: deployVersion }),
      });
      await refresh(selected.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deployment failed.");
    } finally {
      setBusy(false);
    }
  }

  async function retrain() {
    try {
      setRetraining(true);
      setError("");
      await request("/v1/models/retrain", { method: "POST" });
      await refresh(selected?.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retraining failed.");
    } finally {
      setRetraining(false);
    }
  }

  const latest = overview?.latest_anomalies || [];
  const anomalyRate = useMemo(() => {
    if (!overview?.total_readings) return "0.0";
    return ((overview.anomalies / overview.total_readings) * 100).toFixed(1);
  }, [overview]);

  return (
    <main className="app-shell">
      <section className="control-strip">
        <div className="control-copy">
          <p className="section-label">LIVE DASHBOARD</p>
          <h1>Edge device operations</h1>
        </div>
        <div className="control-actions">
          <select value={fault} onChange={(event) => setFault(event.target.value as typeof fault)} aria-label="Simulation fault">
            <option value="energy_spike">Inject energy spike</option>
            <option value="comfort_drift">Inject comfort drift</option>
            <option value="device_health">Inject device health fault</option>
          </select>
          <button className="primary-button" disabled={busy || !selected} onClick={() => void runSimulation()}>{busy ? "Running..." : "Run simulation"}<span>-&gt;</span></button>
        </div>
      </section>
      {error && <p className="error-banner inline-error" role="alert">{error}</p>}

      <section className="metrics-grid" aria-label="Fleet metrics">
        <article className="metric-card accent-cyan"><span>ACTIVE NODES</span><strong>{overview?.online_devices ?? "--"}</strong><small>of {overview?.devices.length ?? "--"} provisioned</small></article>
        <article className="metric-card accent-orange"><span>ANOMALIES DETECTED</span><strong>{overview?.anomalies ?? "--"}</strong><small>{anomalyRate}% of edge decisions</small></article>
        <article className="metric-card accent-lime"><span>EDGE DECISIONS</span><strong>{overview?.edge_decisions ?? "--"}</strong><small>zero cloud round trips</small></article>
        <article className="metric-card accent-lilac"><span>BANDWIDTH AVOIDED</span><strong>{overview?.bandwidth_saved_pct ?? "--"}<i>%</i></strong><small>raw telemetry filtered locally</small></article>
      </section>

      <section className="workspace-grid">
        <aside className="panel fleet-panel">
          <div className="panel-heading"><div><p className="section-label">01 / FLEET</p><h2>Devices</h2></div><span className="count-pill">{overview?.devices.length ?? 0}</span></div>
          <div className="device-list">
            {(overview?.devices || []).map((device) => (
              <button className={`device-row ${selected?.id === device.id ? "selected" : ""}`} key={device.id} onClick={() => { setSelectedId(device.id); void refresh(device.id); }}>
                <span className="device-icon">~</span><span className="device-copy"><strong>{device.name}</strong><small>{device.building} / {device.room}</small></span><span className={`device-state ${device.online ? "online" : "offline"}`}><i />{device.online ? "online" : "offline"}</span>
              </button>
            ))}
            {!overview && <div className="skeleton-list"><span /><span /></div>}
          </div>
          <div className="fleet-footnote"><span className="pulse-ring" /> All decisions carry the deployed model checksum.</div>
        </aside>

        <section className="panel detail-panel">
          <div className="panel-heading detail-heading"><div><p className="section-label">02 / DEVICE TELEMETRY</p><h2>{selected?.name || "Loading device..."}</h2></div><button className="quiet-button" disabled={busy || !selected} onClick={() => void deploy()}>Deploy v{deployVersion ?? "-"} <span>v</span></button></div>
          {selected ? <>
            <div className="device-meta"><span><b>MODEL</b> {selected.model_id} / v{selected.model_version}</span><span><b>FIRMWARE</b> {selected.firmware_version}</span><span><b>LAST SEEN</b> {formatAge(selected.last_seen)}</span></div>
            <div className="chart-wrap"><div className="chart-header"><div><span>ENERGY USAGE</span><strong>{latestReading?.energy_usage.toFixed(2) || "--"} <small>kWh</small></strong></div><span className="chart-legend"><i className="legend-line" /> live edge stream</span></div><div className="chart-grid">{chartTicks.map((tick, index) => <span key={`${tick}-${index}`}>{tick.toFixed(1)}</span>)}<Sparkline readings={readings} maxValue={chartMax} /></div><div className="chart-axis"><span>{readings.length || 0} samples ago</span><span>now</span></div></div>
            <div className="sensor-strip"><div><span className="sensor-label">TEMP</span><strong>{latestReading?.temperature.toFixed(1) || "--"} deg</strong></div><div><span className="sensor-label">HUMIDITY</span><strong>{latestReading?.humidity.toFixed(0) || "--"}%</strong></div><div><span className="sensor-label">SIGNAL</span><strong>{latestReading ? `${Math.round(latestReading.signal_quality * 100)}%` : "--"}</strong></div><div><span className="sensor-label">HARVEST</span><strong>{latestReading?.harvested_energy.toFixed(2) || "--"}<small>mJ</small></strong></div></div>
          </> : <div className="empty-state">Connect the API to inspect a deployed device.</div>}
        </section>

        <aside className="panel model-panel">
          <div className="panel-heading"><div><p className="section-label">03 / MODEL CARD</p><h2>Edge artifact</h2></div><span className="verified">&#10003; VERIFIED</span></div>
          <div className="model-name"><span className="model-chip">LOGISTIC</span><strong>{activeModel?.model_id || "edge-anomaly-logistic"}</strong><small>v{activeModel?.version ?? "-"} / 6 features / no dependencies</small></div>
          <div className="model-metrics"><div><span>F1 SCORE</span><strong>{activeModel ? `${(activeModel.metrics.f1 * 100).toFixed(0)}%` : "--"}</strong></div><div><span>THRESHOLD</span><strong>{activeModel ? activeModel.threshold : "--"}</strong></div></div>
          <div className="hash-block"><span>ARTIFACT CHECKSUM</span><code>{activeModel?.artifact_sha256 ? `${activeModel.artifact_sha256.slice(0, 20)}...` : "loading..."}</code></div>
          <p className="model-note">The same normalized weights run in Python for training, C for firmware, and the device simulator for this demo.</p>
        </aside>
      </section>

      <section className="panel alerts-panel">
        <div className="panel-heading"><div><p className="section-label">04 / EVENT STREAM</p><h2>Latest edge alerts</h2></div><span className="live-label"><i /> LIVE</span></div>
        <div className="alert-list">
          {latest.map((reading) => <article className="alert-row" key={reading.id}><span className="alert-severity">!</span><div className="alert-main"><strong>{reading.inference.anomaly_type.replaceAll("_", " ")}</strong><span>{reading.inference.explanation}</span></div><div className="alert-device"><strong>{reading.device_id}</strong><span>{new Date(reading.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span></div><span className="probability">{Math.round(reading.inference.probability * 100)}%</span></article>)}
          {!latest.length && <div className="empty-state">No anomalies yet. Run a device simulation to create one.</div>}
        </div>
      </section>

      <section className="ops-grid" aria-label="Model operations">
        <section className="panel ops-panel">
          <div className="panel-heading"><div><p className="section-label">05 / MODEL OPERATIONS</p><h2>Trust signals</h2></div><span className={`ops-status ${operations?.drift.status === "action_required" ? "warn" : "ok"}`}>{operations?.drift.status.replaceAll("_", " ") || "loading"}</span></div>
          <div className="ops-cards">
            <div className="ops-card"><span>DATA QUALITY</span><strong>{operations ? `${Math.round(operations.data_quality.score * 100)}%` : "--"}</strong><small>{operations?.data_quality.low_signal_readings ?? "--"} low-signal readings</small></div>
            <div className="ops-card"><span>DRIFT SCORE</span><strong>{operations ? operations.drift.score.toFixed(2) : "--"}</strong><small>threshold {operations?.drift.threshold.toFixed(2) || "--"}</small></div>
            <div className="ops-card"><span>REVIEWED LABELS</span><strong>{operations?.data_quality.reviewed_labels ?? "--"}</strong><small>operator feedback</small></div>
          </div>
          <div className="feature-drift">
            {(operations?.drift.features || []).map((feature) => <div className="drift-row" key={feature.name}><span>{feature.name.replaceAll("_", " ")}</span><div className="drift-bar"><i style={{ width: `${Math.min(100, feature.psi * 100)}%` }} /></div><code>{feature.psi.toFixed(2)} PSI</code></div>)}
          </div>
        </section>
        <section className="panel lifecycle-panel">
          <div className="panel-heading"><div><p className="section-label">06 / LIFECYCLE</p><h2>Retrain safely</h2></div><span className="lifecycle-dot" /></div>
          <div className="lifecycle-step"><span>01</span><div><strong>Production</strong><small>v{operations?.deployment.production_version ?? "--"} / {operations?.deployment.rollout || "loading"}</small></div><b>LIVE</b></div>
          <div className="lifecycle-line" />
          <div className="lifecycle-step candidate"><span>02</span><div><strong>Candidate</strong><small>v{operations?.retraining.candidate_version ?? "--"} / {operations?.retraining.training_window || "waiting"}</small></div><b>{operations?.retraining.status.replaceAll("_", " ") || "--"}</b></div>
          <button className="retrain-button" disabled={retraining} onClick={() => void retrain()}>{retraining ? "Training candidate..." : "Train candidate model"}<span>-&gt;</span></button>
          <p className="lifecycle-note">Candidate F1 {operations ? (operations.retraining.candidate_metrics.f1 * 100).toFixed(0) : "--"}% / precision {operations ? (operations.retraining.candidate_metrics.precision * 100).toFixed(0) : "--"}% / recall {operations ? (operations.retraining.candidate_metrics.recall * 100).toFixed(0) : "--"}%.</p>
          <p className="lifecycle-note">A candidate never replaces production automatically. Evaluate it offline, approve a canary rollout, then keep rollback available.</p>
        </section>
      </section>
      <footer><span>EDGELOOP LAB / SYNTHETIC TELEMETRY</span><span>MODEL-FIRST. DEVICE-BOUND. OBSERVABLE.</span></footer>
    </main>
  );
}
