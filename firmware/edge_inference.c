#include "edge_model.h"
#include "edge_inference.h"

#include <math.h>

static float clamp01(float value) {
    if (value < 0.0f) return 0.0f;
    if (value > 1.0f) return 1.0f;
    return value;
}

static float sigmoid(float value) {
    if (value < -60.0f) value = -60.0f;
    if (value > 60.0f) value = 60.0f;
    return 1.0f / (1.0f + expf(-value));
}

/* This function has no heap allocation or third-party runtime dependency. */
void edge_infer(const EdgeSensorFrame *frame, EdgeDecision *decision) {
    float expected_energy = 0.25f + 1.20f * clamp01(frame->occupancy);
    float features[6];
    features[0] = frame->energy_usage / expected_energy;
    features[1] = fabsf(frame->temperature - (frame->occupancy ? 21.0f : 19.5f));
    features[2] = fabsf(frame->humidity - 45.0f);
    features[3] = 1.0f - clamp01(frame->signal_quality);
    features[4] = fmaxf(0.0f, 0.10f - frame->harvested_energy);
    features[5] = frame->occupancy < 0.5f ? fmaxf(0.0f, frame->energy_usage - 0.45f) : 0.0f;

    float linear = EDGE_MODEL_BIAS;
    for (int index = 0; index < 6; index++) {
        linear += ((features[index] - EDGE_MODEL_MEANS[index]) / EDGE_MODEL_SCALES[index]) * EDGE_MODEL_WEIGHTS[index];
    }
    decision->probability = sigmoid(linear);
    decision->is_anomaly = decision->probability >= EDGE_MODEL_THRESHOLD;
}
