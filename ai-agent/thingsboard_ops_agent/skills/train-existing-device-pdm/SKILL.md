---
name: train-existing-device-pdm
description: >
  Use when the user wants to create, train, or run predictive maintenance on an
  existing ThingsBoard device. The workflow first verifies that the device
  exists, then creates the predictive model, trains it, starts inference, and
  polls forecast and anomaly results.
tools:
  - getDeviceByName
  - getDevice
  - getAvailableAlgorithmsMap
  - createPredictiveModel
  - createAndTrainPredictiveModel
  - trainPredictiveModel
  - inferPredictiveModel
  - pollPredictiveModelInference
  - getPredictiveModelStatus
  - getAnomalyHistoryPredictions
---

# Train and Infer Predictive Maintenance for an Existing Device

This skill is owned by `pdm_agent`.

It operates only on existing ThingsBoard devices.

## Phase 0 - Resolve the target device

If the user provides:

- a device name
- a device id

verify that the device exists before continuing.

Resolution order:

1. If a device id is supplied:
   - call `getDevice`
   - if not found, stop immediately.

2. If only a device name is supplied:
   - call `getDeviceByName`
   - if not found, stop immediately.
   - extract the returned ThingsBoard device id.

Never fabricate or modify device ids.

If multiple devices match the supplied name, ask the user which one to use.

---

## Phase 1 - Choose algorithms

Call:

- `getAvailableAlgorithmsMap`

Select:

- ForecastModel
- AnomalyPredictor

Use the user's requested algorithms.

Otherwise choose the first available model of each type.

---

## Phase 1.5 - Discover all telemetry keys

Call `getTimeseriesKeys` on the resolved device to get every telemetry key
the device reports (e.g. `volt`, `rotate`, `pressure`, `vibration`).

ALL discovered keys MUST be included in the `attributes` array when creating the
model. The PdM training pipeline needs every sensor to build its feature matrix.
Do not cherry-pick a single sensor — pass them all.

---

## Phase 2 - Create the predictive model

Create a model using:

- `createAndTrainPredictiveModel`

or, if the user explicitly wants separate steps:

- `createPredictiveModel`

The request should contain:

- name
- deviceId (resolved during Phase 0)
- forecastAlgorithm (use the same algorithm id as returned by `getAvailableAlgorithmsMap` lowercase or uppercase)
- anomalyAlgorithm (use the same algorithm id as returned by `getAvailableAlgorithmsMap` lowercase or uppercase)
- forecastStartDate: use `0` (epoch milliseconds) to include ALL available data
- forecastEndDate: use current time in milliseconds
- anomalyStartDate: use `0` (epoch milliseconds) to include ALL available data
- anomalyEndDate: use current time in milliseconds
- attributes: include ALL telemetry keys discovered in Phase 1.5, each as
  `{aggregation: "average", groupByMs: 5000, key: "<discovered_key>"}`. Example
  for a device with `volt`, `rotate`, `pressure`, `vibration`:
  ```json
  "attributes": [
    {"key": "volt", "aggregation": "average", "groupByMs": 5000},
    {"key": "rotate", "aggregation": "average", "groupByMs": 5000},
    {"key": "pressure", "aggregation": "average", "groupByMs": 5000},
    {"key": "vibration", "aggregation": "average", "groupByMs": 5000}
  ]
  ```

CRITICAL: The anomaly detection algorithm performs feature engineering on the raw
telemetry (3-hour resampling, 24-hour rolling windows). It needs ALL historical
telemetry from the beginning of time to now. Always set start dates to 0 (epoch
milliseconds) unless the user explicitly provides a different start date.

Follow this structure to send create request to MCP for `createPredictiveModel`:

```json
{
  "additionalData": "{}",
  "anomalyAlgorithm": "random_forest",
  "anomalyEndDate": 1784069999999,
  "anomalyStartDate": 0,
  "attributes": [
    {"key": "volt", "aggregation": "average", "groupByMs": 5000},
    {"key": "rotate", "aggregation": "average", "groupByMs": 5000},
    {"key": "pressure", "aggregation": "average", "groupByMs": 5000},
    {"key": "vibration", "aggregation": "average", "groupByMs": 5000}
  ],
  "deviceId": {
    "entityType": "DEVICE",
    "id": "9f45fd90-0b66-11f1-add6-958e4a75fa7a"
  },
  "forecastAlgorithm": "lstm",
  "forecastEndDate": 1784069999999,
  "forecastStartDate": 0,
  "name": "dsadsa"
}
```

Only include telemetry keys discovered via `getTimeseriesKeys` in Phase 1.5.
Never invent telemetry keys that do not exist on the device.
Do not invent algorithms or use malformed algorithm ids.

Capture the returned model id.

If no model id is returned, stop.

---

## Phase 3 - Train

If `createAndTrainPredictiveModel` was not used:

Call:

- `trainPredictiveModel`

using

```
modelType = BOTH
```

unless the user explicitly requests only one model.

Poll using:

- `getPredictiveModelStatus`

until:

- completed
- failed
- error

or until the runtime limit is reached.

---

## Phase 4 - Run inference

Call:

- `inferPredictiveModel`

using

```
modelType = BOTH
```

unless otherwise requested.

---

## Phase 5 - Collect predictions

Retrieve:

- forecast predictions
- anomaly predictions

using:

- `pollPredictiveModelInference`

and/or

- `getAnomalyHistoryPredictions`

Summarize:

- forecast prediction count
- anomaly prediction count
- latest timestamps
- failures
- warnings

Do not report successful inference unless the API returns either predictions or an explicit successful empty response.

---

# Hard Rules

- Never create or seed a new ThingsBoard device.
- Always verify the target device exists before creating a model.
- Never invent device ids.
- Never invent model ids.
- Never invent telemetry keys. Always discover real keys via `getTimeseriesKeys` and include ALL of them in the model's `attributes`.
- Never invent algorithms.
- Stop immediately if the device cannot be resolved.
- Keep forecast and anomaly results separate.
- Surface API errors exactly as returned.
