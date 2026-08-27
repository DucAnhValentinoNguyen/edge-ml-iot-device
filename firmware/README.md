# Firmware target

`edge_inference.c` is the deployment boundary. It contains the same six-feature
normalization and logistic model as the Python runtime, but uses only C math and
static arrays. The model is 256 bytes of constants in this demo and does not need
an internet connection, a Python interpreter, or a cloud round trip.

The file is intentionally framework-neutral so it can be called from an
ESP32, STM32, or gateway firmware loop. A device integration would:

1. Fill `EdgeSensorFrame` from the sensor driver.
2. Call `edge_infer(&frame, &decision)`.
3. Publish only the compact alert or heartbeat over MQTT/HTTPS.
4. Include `EDGE_MODEL_SHA256` in the message for fleet-side verification.

For a quick native smoke test on Linux/macOS:

```bash
cc -std=c11 -Wall -Wextra -pedantic -c firmware/edge_inference.c -o /tmp/edge_inference.o
```

The Python simulator in `scripts/simulate_device.py` demonstrates the same
protocol against the local API and prints the edge decision for every sample.

