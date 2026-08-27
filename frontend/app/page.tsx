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

function Sparkline({ readings }: { readings: Reading[] }) {
  const points = readings.map((reading, index) => {
    const x = readings.length === 1 ? 50 : (index / (readings.length - 1)) * 100;
    const y = 90 - Math.min(72, reading.energy_usage * 30);
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
  const selected = overview?.devices.find((device) => device.id === selectedId) || overview?.devices[0];

  async function refresh(nextDeviceId?: string) {
    try {
      setError("");
      const next = await request<Overview>("/v1/overview");
      setOverview(next);
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
    if (!selected) return;
    try {
      setBusy(true);
      setError("");
      await request(`/v1/devices/${selected.id}/deploy`, { method: "POST" });
      await refresh(selected.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deployment failed.");
    } finally {
      setBusy(false);
    }
  }

  const latest = overview?.latest_anomalies || [];
  const anomalyRate = useMemo(() => {
    if (!overview?.total_readings) return "0.0";
    return ((overview.anomalies / overview.total_readings) * 100).toFixed(1);
  }, [overview]);

  return (
    <main className="app-shell">
      <nav className="topbar">
        <div className="brand"><span className="brand-mark">&#9676;</span><span>EDGELOOP</span><small>DEVICE INTELLIGENCE</small></div>
        <div className="nav-status"><span className="status-dot" /> FLEET ONLINE <span className="nav-divider" /> v0.4.0</div>
      </nav>

      <section className="hero">
        <div className="hero-copy">
          <p className="kicker">DEVICE INTELLIGENCE / EDGE DEPLOYMENT LAB</p>
          <h1>Decisions that happen<br /><em>where the data lives.</em></h1>
          <p className="hero-description">A compact anomaly model runs inside every sensor gateway. The cloud receives verified decisions, not a firehose of raw telemetry.</p>
          <div className="hero-actions">
            <select value={fault} onChange={(event) => setFault(event.target.value as typeof fault)} aria-label="Simulation fault">
              <option value="energy_spike">Inject energy spike</option>
              <option value="comfort_drift">Inject comfort drift</option>
              <option value="device_health">Inject device health fault</option>
            </select>
            <button className="primary-button" disabled={busy || !selected} onClick={() => void runSimulation()}>{busy ? "Running..." : "Run device simulation"}<span>-&gt;</span></button>
          </div>
          {error && <p className="error-banner" role="alert">{error}</p>}
        </div>
        <div className="hero-orbit" aria-hidden="true"><div className="orbit orbit-a" /><div className="orbit orbit-b" /><div className="orbit-core"><span>ML</span><small>ON EDGE</small></div><div className="orbit-node node-a" /><div className="orbit-node node-b" /></div>
      </section>

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
          <div className="panel-heading detail-heading"><div><p className="section-label">02 / DEVICE TELEMETRY</p><h2>{selected?.name || "Loading device..."}</h2></div><button className="quiet-button" disabled={busy || !selected} onClick={() => void deploy()}>Deploy v{overview?.model.version ?? "-"} <span>v</span></button></div>
          {selected ? <>
            <div className="device-meta"><span><b>MODEL</b> {selected.model_id} / v{selected.model_version}</span><span><b>FIRMWARE</b> {selected.firmware_version}</span><span><b>LAST SEEN</b> {formatAge(selected.last_seen)}</span></div>
            <div className="chart-wrap"><div className="chart-header"><div><span>ENERGY USAGE</span><strong>{readings.at(-1)?.energy_usage.toFixed(2) || "--"} <small>kWh</small></strong></div><span className="chart-legend"><i className="legend-line" /> live edge stream</span></div><div className="chart-grid"><span>2.4</span><span>1.6</span><span>0.8</span><span>0.0</span><Sparkline readings={readings} /></div><div className="chart-axis"><span>36 samples ago</span><span>now</span></div></div>
            <div className="sensor-strip"><div><span className="sensor-label">TEMP</span><strong>{readings.at(-1)?.temperature.toFixed(1) || "--"} deg</strong></div><div><span className="sensor-label">HUMIDITY</span><strong>{readings.at(-1)?.humidity.toFixed(0) || "--"}%</strong></div><div><span className="sensor-label">SIGNAL</span><strong>{Math.round((selected.signal_quality || 0) * 100)}%</strong></div><div><span className="sensor-label">HARVEST</span><strong>{readings.at(-1)?.harvested_energy.toFixed(2) || "--"}<small>mJ</small></strong></div></div>
          </> : <div className="empty-state">Connect the API to inspect a deployed device.</div>}
        </section>

        <aside className="panel model-panel">
          <div className="panel-heading"><div><p className="section-label">03 / MODEL CARD</p><h2>Edge artifact</h2></div><span className="verified">&#10003; VERIFIED</span></div>
          <div className="model-name"><span className="model-chip">LOGISTIC</span><strong>{overview?.model.model_id || "edge-anomaly-logistic"}</strong><small>v{overview?.model.version ?? "-"} / 6 features / no dependencies</small></div>
          <div className="model-metrics"><div><span>F1 SCORE</span><strong>{overview ? `${(overview.model.metrics.f1 * 100).toFixed(0)}%` : "--"}</strong></div><div><span>THRESHOLD</span><strong>{overview ? overview.model.threshold : "--"}</strong></div></div>
          <div className="hash-block"><span>ARTIFACT CHECKSUM</span><code>{overview?.model.artifact_sha256 ? `${overview.model.artifact_sha256.slice(0, 20)}...` : "loading..."}</code></div>
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
      <footer><span>EDGELOOP LAB / SYNTHETIC TELEMETRY</span><span>MODEL-FIRST. DEVICE-BOUND. OBSERVABLE.</span></footer>
    </main>
  );
}
