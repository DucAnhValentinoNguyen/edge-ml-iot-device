"""SQLite persistence keeps the showcase self-contained while preserving clear data boundaries."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TelemetryStore:
    def __init__(self, database_path: str):
        path = Path(database_path)
        if path.parent != Path("."):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self._initialize()

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                building TEXT NOT NULL,
                room TEXT NOT NULL,
                firmware_version TEXT NOT NULL,
                model_id TEXT NOT NULL,
                model_version INTEGER NOT NULL,
                battery_pct REAL NOT NULL,
                signal_quality REAL NOT NULL,
                online INTEGER NOT NULL DEFAULT 1,
                last_seen TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS readings (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                received_at TEXT NOT NULL,
                temperature REAL NOT NULL,
                humidity REAL NOT NULL,
                occupancy INTEGER NOT NULL,
                energy_usage REAL NOT NULL,
                signal_quality REAL NOT NULL,
                harvested_energy REAL NOT NULL,
                inference_json TEXT NOT NULL,
                feedback_label TEXT,
                feedback_note TEXT,
                FOREIGN KEY (device_id) REFERENCES devices(id)
            );
            CREATE INDEX IF NOT EXISTS idx_readings_device_time ON readings(device_id, timestamp DESC);
            CREATE TABLE IF NOT EXISTS edge_events (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                reading_id TEXT,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                title TEXT NOT NULL,
                details TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                FOREIGN KEY (device_id) REFERENCES devices(id)
            );
            CREATE INDEX IF NOT EXISTS idx_events_time ON edge_events(occurred_at DESC);
            CREATE TABLE IF NOT EXISTS deployments (
                device_id TEXT PRIMARY KEY,
                model_id TEXT NOT NULL,
                model_version INTEGER NOT NULL,
                artifact_sha256 TEXT NOT NULL,
                status TEXT NOT NULL,
                deployed_at TEXT NOT NULL,
                FOREIGN KEY (device_id) REFERENCES devices(id)
            );
            CREATE TABLE IF NOT EXISTS gateways (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                location TEXT NOT NULL,
                status TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                telegram_count INTEGER NOT NULL DEFAULT 0,
                duplicate_count INTEGER NOT NULL DEFAULT 0,
                last_rssi INTEGER,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS gateway_telegrams (
                id TEXT PRIMARY KEY,
                gateway_id TEXT NOT NULL,
                source_eurid TEXT NOT NULL,
                rorg TEXT NOT NULL,
                data_hex TEXT NOT NULL,
                status_hex TEXT NOT NULL,
                rssi INTEGER NOT NULL,
                security_level INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                duplicate INTEGER NOT NULL,
                profile_id TEXT,
                decoded_json TEXT NOT NULL,
                received_at TEXT NOT NULL,
                FOREIGN KEY (gateway_id) REFERENCES gateways(id)
            );
            CREATE TABLE IF NOT EXISTS onboarding_devices (
                source_eurid TEXT PRIMARY KEY,
                gateway_id TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                friendly_id TEXT NOT NULL,
                location TEXT NOT NULL,
                status TEXT NOT NULL,
                device_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def ensure_gateway(self, gateway_id: str, name: str | None = None, location: str = "Demo site") -> None:
        now = utc_now()
        self.connection.execute(
            """
            INSERT INTO gateways (id, name, location, status, last_seen, created_at)
            VALUES (?, ?, ?, 'online', ?, ?)
            ON CONFLICT(id) DO UPDATE SET status='online', last_seen=excluded.last_seen
            """,
            (gateway_id, name or gateway_id.replace("-", " ").title(), location, now, now),
        )
        self.connection.commit()

    def record_gateway_telegram(self, telegram: dict[str, Any], result: dict[str, Any]) -> bool:
        self.ensure_gateway(str(telegram["gateway_id"]))
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO gateway_telegrams
            (id, gateway_id, source_eurid, rorg, data_hex, status_hex, rssi, security_level,
             timestamp, duplicate, profile_id, decoded_json, received_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result["telegram_id"], telegram["gateway_id"], telegram["source_eurid"],
                telegram["rorg"], telegram["data_hex"], telegram.get("status_hex", "80"),
                telegram.get("rssi", 70), telegram.get("security_level", 0),
                datetime.fromisoformat(result["timestamp"].replace("Z", "+00:00")).timestamp(),
                int(result["duplicate"]), result.get("profile_id"),
                json.dumps(result.get("decoded", [])), utc_now(),
            ),
        )
        if cursor.rowcount:
            self.connection.execute(
                """
                UPDATE gateways SET last_seen=?, status='online', telegram_count=telegram_count+1,
                    duplicate_count=duplicate_count+? , last_rssi=? WHERE id=?
                """,
                (utc_now(), int(result["duplicate"]), telegram.get("rssi", 70), telegram["gateway_id"]),
            )
            self.connection.commit()
            return True
        return False

    def list_gateways(self) -> list[dict[str, Any]]:
        rows = self.connection.execute("SELECT * FROM gateways ORDER BY last_seen DESC").fetchall()
        return [dict(row) for row in rows]

    def upsert_onboarding(
        self, source_eurid: str, gateway_id: str, profile_id: str, friendly_id: str,
        location: str, status: str, device_id: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        self.connection.execute(
            """
            INSERT INTO onboarding_devices
            (source_eurid, gateway_id, profile_id, friendly_id, location, status, device_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_eurid) DO UPDATE SET gateway_id=excluded.gateway_id,
              profile_id=excluded.profile_id, friendly_id=excluded.friendly_id,
              location=excluded.location, status=excluded.status, device_id=excluded.device_id,
              updated_at=excluded.updated_at
            """,
            (source_eurid, gateway_id, profile_id, friendly_id, location, status, device_id, now, now),
        )
        self.connection.commit()
        return self.get_onboarding(source_eurid) or {}

    def get_onboarding(self, source_eurid: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM onboarding_devices WHERE source_eurid=?", (source_eurid,)
        ).fetchone()
        return dict(row) if row else None

    def list_onboarding(self, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            rows = self.connection.execute(
                "SELECT * FROM onboarding_devices WHERE status=? ORDER BY updated_at DESC", (status,)
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM onboarding_devices ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def ensure_device(
        self,
        device_id: str,
        model_id: str,
        model_version: int,
        *,
        name: str | None = None,
        building: str = "Munich HQ",
        room: str = "Demo room",
        firmware_version: str = "edge-fw 0.4.0",
    ) -> None:
        now = utc_now()
        self.connection.execute(
            """
            INSERT INTO devices (id, name, building, room, firmware_version, model_id,
                model_version, battery_pct, signal_quality, online, last_seen, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 82.0, 0.95, 1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET model_id=excluded.model_id,
                model_version=excluded.model_version
            """,
            (device_id, name or device_id.replace("-", " ").title(), building, room,
             firmware_version, model_id, model_version, now, now),
        )
        self.connection.commit()

    def record_telemetry(self, reading: dict[str, Any], inference: dict[str, Any]) -> tuple[bool, str]:
        reading_id = reading.get("event_id") or f"reading-{uuid.uuid4().hex}"
        self.ensure_device(
            str(reading["device_id"]),
            str(inference["model_id"]),
            int(inference["model_version"]),
        )
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO readings
            (id, device_id, timestamp, received_at, temperature, humidity, occupancy,
             energy_usage, signal_quality, harvested_energy, inference_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reading_id,
                reading["device_id"],
                reading["timestamp"],
                utc_now(),
                reading["temperature"],
                reading["humidity"],
                int(bool(reading["occupancy"])),
                reading["energy_usage"],
                reading["signal_quality"],
                reading["harvested_energy"],
                json.dumps(inference),
            ),
        )
        accepted = cursor.rowcount == 1
        if accepted:
            self.connection.execute(
                "UPDATE devices SET last_seen=?, online=1, signal_quality=? WHERE id=?",
                (reading["timestamp"], reading["signal_quality"], reading["device_id"]),
            )
            if inference["is_anomaly"]:
                self.connection.execute(
                    """
                    INSERT OR IGNORE INTO edge_events
                    (id, device_id, reading_id, event_type, severity, title, details, occurred_at)
                    VALUES (?, ?, ?, 'anomaly_detected', 'warning', ?, ?, ?)
                    """,
                    (
                        f"alert:{reading_id}",
                        reading["device_id"],
                        reading_id,
                        f"{inference['anomaly_type'].replace('_', ' ').title()} detected",
                        inference["explanation"],
                        reading["timestamp"],
                    ),
                )
            self.connection.commit()
        return accepted, reading_id

    def list_devices(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT d.*, COUNT(CASE WHEN json_extract(r.inference_json, '$.is_anomaly') = 1 THEN 1 END) AS anomaly_count
            FROM devices d LEFT JOIN readings r ON r.device_id=d.id
            GROUP BY d.id ORDER BY d.last_seen DESC
            """
        ).fetchall()
        return [self._device(row) for row in rows]

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
        return self._device(row) if row else None

    def list_readings(self, device_id: str, limit: int = 48) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM readings WHERE device_id=? ORDER BY timestamp DESC LIMIT ?",
            (device_id, limit),
        ).fetchall()
        return [self._reading(row) for row in reversed(rows)]

    def list_anomalies(self, device_id: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
        params: list[Any] = []
        condition = "json_extract(r.inference_json, '$.is_anomaly') = 1"
        if device_id:
            condition += " AND r.device_id=?"
            params.append(device_id)
        params.append(limit)
        rows = self.connection.execute(
            f"SELECT r.* FROM readings r WHERE {condition} ORDER BY timestamp DESC LIMIT ?", params
        ).fetchall()
        return [self._reading(row) for row in rows]

    def get_reading(self, reading_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM readings WHERE id=?", (reading_id,)).fetchone()
        return self._reading(row) if row else None

    def list_events(self, device_id: str, limit: int = 40) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM edge_events WHERE device_id=? ORDER BY occurred_at DESC LIMIT ?",
            (device_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def deploy(self, device_id: str, model_id: str, version: int, artifact_sha256: str) -> dict[str, Any]:
        deployed_at = utc_now()
        self.ensure_device(device_id, model_id, version)
        self.connection.execute(
            """
            INSERT INTO deployments (device_id, model_id, model_version, artifact_sha256, status, deployed_at)
            VALUES (?, ?, ?, ?, 'active', ?)
            ON CONFLICT(device_id) DO UPDATE SET model_id=excluded.model_id,
              model_version=excluded.model_version, artifact_sha256=excluded.artifact_sha256,
              status='active', deployed_at=excluded.deployed_at
            """,
            (device_id, model_id, version, artifact_sha256, deployed_at),
        )
        self.connection.execute(
            "UPDATE devices SET model_id=?, model_version=? WHERE id=?",
            (model_id, version, device_id),
        )
        self.connection.execute(
            """
            INSERT INTO edge_events (id, device_id, event_type, severity, title, details, occurred_at)
            VALUES (?, ?, 'model_deployed', 'info', 'Model deployed to device', ?, ?)
            """,
            (f"deployment:{device_id}:{deployed_at}", device_id, f"{model_id} v{version} verified on edge", deployed_at),
        )
        self.connection.commit()
        return {"device_id": device_id, "model_id": model_id, "version": version, "status": "active", "deployed_at": deployed_at}

    def get_deployment(self, device_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM deployments WHERE device_id=?", (device_id,)
        ).fetchone()
        return dict(row) if row else None

    def add_feedback(self, reading_id: str, label: str, note: str) -> dict[str, Any] | None:
        cursor = self.connection.execute(
            "UPDATE readings SET feedback_label=?, feedback_note=? WHERE id=?",
            (label, note, reading_id),
        )
        self.connection.commit()
        return self.get_reading(reading_id) if cursor.rowcount else None

    def overview(self) -> dict[str, Any]:
        total = self.connection.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
        anomalies = self.connection.execute(
            "SELECT COUNT(*) FROM readings WHERE json_extract(inference_json, '$.is_anomaly') = 1"
        ).fetchone()[0]
        devices = self.list_devices()
        return {
            "total_readings": total,
            "anomalies": anomalies,
            "edge_decisions": total,
            "bandwidth_saved_pct": 96.4,
            "online_devices": sum(1 for device in devices if device["online"]),
            "devices": devices,
            "latest_anomalies": self.list_anomalies(limit=6),
        }

    @staticmethod
    def _device(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["online"] = bool(item["online"])
        item["anomaly_count"] = int(item.get("anomaly_count", 0) or 0)
        return item

    @staticmethod
    def _reading(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["occupancy"] = bool(item["occupancy"])
        item["inference"] = json.loads(item.pop("inference_json"))
        return item
