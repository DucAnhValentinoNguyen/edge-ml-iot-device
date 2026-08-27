#ifndef EDGE_INFERENCE_H
#define EDGE_INFERENCE_H

typedef struct {
    float temperature;
    float humidity;
    float occupancy;
    float energy_usage;
    float signal_quality;
    float harvested_energy;
} EdgeSensorFrame;

typedef struct {
    float probability;
    int is_anomaly;
} EdgeDecision;

void edge_infer(const EdgeSensorFrame *frame, EdgeDecision *decision);

#endif

