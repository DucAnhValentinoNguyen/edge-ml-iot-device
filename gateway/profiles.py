"""Small, explicit EEP registry used by the gateway simulator.

The decoder contract is intentionally isolated so real EEP definitions can be
added from the official profile catalogue without changing ingestion or ML code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


Decoder = Callable[[bytes], list[dict[str, Any]]]


@dataclass(frozen=True)
class ProfileDefinition:
    profile_id: str
    rorg: str
    name: str
    fields: tuple[str, ...]
    decoder: Decoder


def _temperature(data: bytes) -> list[dict[str, Any]]:
    return [{"key": "temperature", "value": round(-20.0 + data[0] * 0.2, 2), "unit": "C"}]


def _temperature_humidity(data: bytes) -> list[dict[str, Any]]:
    return [
        {"key": "temperature", "value": round(-20.0 + data[0] * 0.2, 2), "unit": "C"},
        {"key": "humidity", "value": round(data[1] * 100 / 255, 2), "unit": "%"},
    ]


def _contact(data: bytes) -> list[dict[str, Any]]:
    return [{"key": "contact", "value": "open" if data[0] & 1 else "closed", "meaning": "Contact state"}]


def _switch(data: bytes) -> list[dict[str, Any]]:
    return [{"key": "switch", "value": "on" if data[0] & 1 else "off", "meaning": "Switch state"}]


class ProfileRegistry:
    def __init__(self) -> None:
        self._profiles = {
            profile.profile_id: profile
            for profile in (
                ProfileDefinition("A5-04-01", "A5", "Room temperature", ("temperature",), _temperature),
                ProfileDefinition("A5-04-03", "A5", "Room temperature and humidity", ("temperature", "humidity"), _temperature_humidity),
                ProfileDefinition("D5-00-01", "D5", "Single contact", ("contact",), _contact),
                ProfileDefinition("F6-02-04", "F6", "Rocker switch", ("switch",), _switch),
            )
        }

    def get(self, profile_id: str) -> ProfileDefinition | None:
        return self._profiles.get(profile_id.upper())

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "profile_id": profile.profile_id,
                "rorg": profile.rorg,
                "name": profile.name,
                "fields": list(profile.fields),
            }
            for profile in self._profiles.values()
        ]

    def suggest(self, rorg: str, data: bytes) -> list[dict[str, Any]]:
        candidates = [profile for profile in self._profiles.values() if profile.rorg == rorg.upper()]
        if not candidates:
            candidates = list(self._profiles.values())
        suggestions: list[dict[str, Any]] = []
        for profile in candidates:
            try:
                values = profile.decoder(data)
                plausible = all(isinstance(item.get("value"), (int, float, str)) for item in values)
            except (IndexError, ValueError):
                plausible = False
                values = []
            if plausible:
                confidence = 0.88 if profile.rorg == rorg.upper() else 0.42
                suggestions.append(
                    {
                        "profile_id": profile.profile_id,
                        "name": profile.name,
                        "confidence": confidence,
                        "reason": f"RORG {rorg.upper()} matches the registered profile family",
                        "sample_data": values,
                    }
                )
        return sorted(suggestions, key=lambda item: item["confidence"], reverse=True)

