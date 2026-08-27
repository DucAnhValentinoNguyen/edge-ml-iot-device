"""Ingress adapter: parse, deduplicate, decode, and prepare gateway events."""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .profiles import ProfileRegistry


@dataclass(frozen=True)
class RawTelegram:
    gateway_id: str
    source_eurid: str
    rorg: str
    data_hex: str
    status_hex: str = "80"
    rssi: int = 70
    security_level: int = 0
    timestamp: float = field(default_factory=time.time)
    telegram_id: str = field(default_factory=lambda: f"telegram-{uuid.uuid4().hex}")

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RawTelegram":
        source = str(payload["source_eurid"]).replace(" ", "").upper()
        data = str(payload["data_hex"]).replace(" ", "").upper()
        status = str(payload.get("status_hex", "80")).replace(" ", "").upper()
        if len(source) != 8 or any(character not in "0123456789ABCDEF" for character in source):
            raise ValueError("source_eurid must be an 8-character hexadecimal device ID")
        if len(data) == 0 or len(data) % 2 or any(character not in "0123456789ABCDEF" for character in data):
            raise ValueError("data_hex must be a non-empty hexadecimal byte string")
        if len(status) % 2 or any(character not in "0123456789ABCDEF" for character in status):
            raise ValueError("status_hex must be a hexadecimal byte string")
        timestamp = payload.get("timestamp")
        if isinstance(timestamp, datetime):
            timestamp = timestamp.timestamp()
        elif isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
        return cls(
            gateway_id=str(payload["gateway_id"]),
            source_eurid=source,
            rorg=str(payload["rorg"]).upper(),
            data_hex=data,
            status_hex=status,
            rssi=max(0, min(100, int(payload.get("rssi", 70)))),
            security_level=max(0, min(3, int(payload.get("security_level", 0)))),
            timestamp=float(timestamp if timestamp is not None else time.time()),
            telegram_id=str(payload.get("telegram_id") or f"telegram-{uuid.uuid4().hex}"),
        )

    @property
    def data(self) -> bytes:
        return bytes.fromhex(self.data_hex)

    @property
    def dedupe_key(self) -> str:
        material = f"{self.source_eurid}:{self.rorg}:{self.data_hex}:{self.status_hex}"
        return hashlib.sha256(material.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class IngressResult:
    telegram: RawTelegram
    duplicate: bool
    known_device: bool
    profile_id: str | None
    decoded: list[dict[str, Any]]
    candidates: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "telegram_id": self.telegram.telegram_id,
            "gateway_id": self.telegram.gateway_id,
            "source_eurid": self.telegram.source_eurid,
            "rorg": self.telegram.rorg,
            "data_hex": self.telegram.data_hex,
            "rssi": self.telegram.rssi,
            "security_level": self.telegram.security_level,
            "timestamp": datetime.fromtimestamp(self.telegram.timestamp, tz=timezone.utc).isoformat(),
            "duplicate": self.duplicate,
            "known_device": self.known_device,
            "profile_id": self.profile_id,
            "decoded": self.decoded,
            "candidates": self.candidates,
        }


class GatewayAdapter:
    def __init__(self, duplicate_window_ms: int = 100) -> None:
        self.registry = ProfileRegistry()
        self.duplicate_window_s = duplicate_window_ms / 1000
        self._last_seen: dict[str, float] = {}
        self._devices: dict[str, dict[str, str]] = {}
        self._gateway_stats: dict[str, dict[str, Any]] = {}

    def register_device(self, source_eurid: str, profile_id: str, friendly_id: str, location: str) -> dict[str, Any]:
        source = source_eurid.replace(" ", "").upper()
        profile = self.registry.get(profile_id)
        if not profile:
            raise ValueError(f"Unsupported profile: {profile_id}")
        self._devices[source] = {
            "source_eurid": source,
            "profile_id": profile.profile_id,
            "friendly_id": friendly_id,
            "location": location,
            "status": "operable",
        }
        return dict(self._devices[source])

    def ingest(self, telegram: RawTelegram) -> IngressResult:
        previous = self._last_seen.get(telegram.dedupe_key)
        duplicate = previous is not None and abs(telegram.timestamp - previous) <= self.duplicate_window_s
        if not duplicate:
            self._last_seen[telegram.dedupe_key] = telegram.timestamp
        profile_info = self._devices.get(telegram.source_eurid)
        profile_id = profile_info["profile_id"] if profile_info else None
        profile = self.registry.get(profile_id) if profile_id else None
        decoded = profile.decoder(telegram.data) if profile else []
        stats = self._gateway_stats.setdefault(telegram.gateway_id, {"telegrams": 0, "duplicates": 0, "last_rssi": telegram.rssi})
        stats["telegrams"] += 1
        stats["duplicates"] += int(duplicate)
        stats["last_rssi"] = telegram.rssi
        candidates = [] if profile else self.registry.suggest(telegram.rorg, telegram.data)
        return IngressResult(telegram, duplicate, profile_info is not None, profile_id, decoded, candidates)

    def learn_in(self, telegram: RawTelegram) -> dict[str, Any]:
        result = self.ingest(telegram)
        return {
            "status": "already_registered" if result.known_device else "pending_registration",
            "source_eurid": telegram.source_eurid,
            "gateway_id": telegram.gateway_id,
            "telegram": result.to_dict(),
            "candidates": result.candidates,
        }

    def health(self, gateway_id: str) -> dict[str, Any]:
        stats = self._gateway_stats.get(gateway_id, {"telegrams": 0, "duplicates": 0, "last_rssi": None})
        return {
            "gateway_id": gateway_id,
            "status": "online",
            "telegrams_received": stats["telegrams"],
            "duplicates_removed": stats["duplicates"],
            "last_rssi": stats["last_rssi"],
            "dedupe_window_ms": int(self.duplicate_window_s * 1000),
        }

    def devices(self) -> list[dict[str, str]]:
        return list(self._devices.values())

