#ifndef EDGE_MODEL_H
#define EDGE_MODEL_H

/* Generated from model_artifacts/edge_anomaly_v1.json. */
#define EDGE_MODEL_ID "edge-anomaly-logistic"
#define EDGE_MODEL_VERSION 1
#define EDGE_MODEL_SHA256 "41133d6786861b955d9d316be6872f3731fc37bc5e181cec7633dfa9d2b3f8e2"
#define EDGE_MODEL_THRESHOLD 0.45f

static const float EDGE_MODEL_MEANS[6] = {1.15331998f, 0.96703431f, 4.36323529f, 0.19077819f, 0.01386642f, 0.0289277f};
static const float EDGE_MODEL_SCALES[6] = {0.6642615f, 1.51105762f, 5.57910864f, 0.29688526f, 0.02941293f, 0.08669086f};
static const float EDGE_MODEL_WEIGHTS[6] = {1.90745353f, 1.18785702f, 1.08625162f, 1.15867595f, 1.16433059f, 0.76241933f};
static const float EDGE_MODEL_BIAS = 0.74164591f;

#endif
