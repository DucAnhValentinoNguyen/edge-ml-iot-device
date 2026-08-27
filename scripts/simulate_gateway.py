"""Send ESP3-like demo telegrams through the gateway adapter API."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone


def request(base_url: str, path: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request_obj = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request_obj, timeout=10) as response:
        return json.loads(response.read())


def temperature_byte(value: float) -> int:
    return max(0, min(255, round((value + 20.0) / 0.2)))


def humidity_byte(value: float) -> int:
    return max(0, min(255, round(value * 255.0 / 100.0)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--gateway-id", default="gateway-demo-01")
    parser.add_argument("--source-eurid", default="045F694E")
    parser.add_argument("--profile", default="A5-04-03")
    parser.add_argument("--steps", type=int, default=3)
    parser.add_argument("--learn-in", action="store_true")
    args = parser.parse_args()

    now = datetime.now(timezone.utc).isoformat()
    telegram = {
        "gateway_id": args.gateway_id,
        "source_eurid": args.source_eurid,
        "rorg": args.profile[:2],
        "data_hex": f"{temperature_byte(22.4):02X}{humidity_byte(46):02X}0000",
        "status_hex": "80",
        "rssi": 86,
        "security_level": 0,
        "timestamp": now,
    }

    if args.learn_in:
        print(json.dumps(request(args.base_url, f"/v1/gateways/{args.gateway_id}/learn-in", telegram), indent=2))
        registration = {
            "gateway_id": args.gateway_id,
            "source_eurid": args.source_eurid,
            "profile_id": args.profile,
            "friendly_id": "Demo room sensor",
            "location": "North wing / Room 01",
        }
        print(json.dumps(request(args.base_url, "/v1/onboarding/register", registration), indent=2))

    for step in range(max(1, args.steps)):
        telegram["timestamp"] = datetime.now(timezone.utc).isoformat()
        telegram["telegram_id"] = f"sim-gateway-{int(time.time() * 1000)}-{step}"
        print(json.dumps(request(args.base_url, f"/v1/gateways/{args.gateway_id}/telegrams", telegram), indent=2))
        time.sleep(0.15)
    return 0


if __name__ == "__main__":
    sys.exit(main())
