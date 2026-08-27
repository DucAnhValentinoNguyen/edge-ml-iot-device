import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from edge_runtime.training import save_artifact


if __name__ == "__main__":
    destination = save_artifact(
        Path(__file__).parents[1] / "model_artifacts" / "edge_anomaly_v1.json",
        firmware_path=Path(__file__).parents[1] / "firmware" / "edge_model.h",
    )
    print(destination)
