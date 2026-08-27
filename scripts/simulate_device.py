"""Stream one synthetic device through the cloud API while inferring locally."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from edge_runtime import EdgeRuntime, ModelArtifact, generate_reading


def post_json(url: str, body: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--device-id", default="node-room-01")
    parser.add_argument("--fault", choices=["energy_spike", "comfort_drift", "device_health"], default="energy_spike")
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--interval", type=float, default=0.0)
    args = parser.parse_args()

    artifact_path = Path(__file__).parents[1] / "model_artifacts" / "edge_anomaly_v1.json"
    runtime = EdgeRuntime(ModelArtifact.load(artifact_path))
    for step in range(args.steps):
        reading = generate_reading(args.device_id, step, fault=args.fault)
        prediction = runtime.predict(reading)
        event = {**reading, "inference": prediction.to_dict()}
        response = post_json(f"{args.base_url.rstrip('/')}/v1/telemetry", event)
        print(json.dumps({"step": step, "edge": prediction.to_dict(), "accepted": response.get("accepted")}))
        if args.interval:
            time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as exc:
        print(f"Could not reach API: {exc}", file=sys.stderr)
        raise SystemExit(1)
