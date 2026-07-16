---
name: seed-train-infer-pdm
description: >
  Use when the user asks to create a predictive model through the Quarkus
  PdM MCP endpoint, train it, start inference, and poll forecast and anomaly
  results. This is a test-example PdM workflow skill for pdm_agent.
tools:
  - getAvailableAlgorithmsMap
  - getPredictiveModelsByPage
  - getPredictiveModel
  - getPredictiveModelStatus
  - createPredictiveModel
  - createAndTrainPredictiveModel
  - trainPredictiveModel
  - inferPredictiveModel
  - pollPredictiveModelInference
  - updateForecast
  - deleteForecast
  - getAnomalyHistoryPredictions
  - deleteAnomalyHistoryPredictions
  - getFailureModeHistory
---

# Train and Infer PdM

This skill is owned by `pdm_agent`. It drives the Quarkus PdM example
flow: use the Quarkus MCP endpoint, create a model config, train it, start
inference, then poll both forecast and anomaly outputs.

## Phase 0 - Defaults

If the user asks for a test/example flow and does not provide values, use these
defaults without asking follow-up questions:

- MCP source: the Quarkus PdM MCP service.
- Forecast training window: last 30 days ending now.
- Anomaly training window: last 60 days ending now.
- Forecast model type: first available `ForecastModel` from `getAvailableAlgorithmsMap`.
- Anomaly model type: first available `AnomalyPredictor` from `getAvailableAlgorithmsMap`.
- Prediction history limit: 100.

Ask only for missing values when the user explicitly wants a non-example,
production, or named-device run.

## Phase 1 - Use the Quarkus PdM MCP endpoint

Before calling any PdM operation, use `pdm_agent`, which must be connected to
the Quarkus MCP SSE endpoint. Do not use the Python predictive-maintenance
service as an MCP endpoint, and do not invent raw HTTP calls when Quarkus MCP
tools are available.

## Phase 2 - Choose the device and algorithms

1. The user must provide an existing ThingsBoard device id. Use `devices_agent`
   to look up the device if only a name is given.
2. Call `getAvailableAlgorithmsMap` to see available algorithms for
   Forecast/AnomalyPredictor models.
3. Select one forecast algorithm and one anomaly algorithm using the user's
   preference or Phase 0 defaults.

## Phase 3 - Create the predictive model

1. Call `createPredictiveModel` or `createAndTrainPredictiveModel` with a model
   config containing:
   - `name`: a short unique name.
   - `deviceId`: the target device id (as a nested object with `entityType` and
     `id`).
   - `forecastAlgorithm`: selected forecast model name.
   - `anomalyAlgorithm`: selected anomaly predictor name.
   - `forecastStartDate` / `forecastEndDate`: millisecond timestamps.
   - `anomalyStartDate` / `anomalyEndDate`: millisecond timestamps.
   - `fields` or telemetry attributes only when known; do not guess telemetry
     key names.
2. Capture the returned forecast/model id from the response.

If the API returns no id, stop and report the create response.

## Phase 4 - Train and poll status

1. If you did not already use `createAndTrainPredictiveModel`, call
   `trainPredictiveModel` for the captured model id with `modelType=BOTH`
   unless the user requested only forecast or only anomaly.
2. Poll status using `getPredictiveModelStatus` and/or
   `pollPredictiveModelInference`.
3. Continue until the API reports a terminal state such as `completed`, `failed`,
   or `error`, or until the tool/runtime limit is reached.

If the status is still running at the limit, report the latest status and the
model id so the user can continue polling.

## Phase 5 - Poll inference

After training completes:

1. Call `inferPredictiveModel` with `modelType=BOTH` unless the user requested
   only one model type.
2. Fetch forecast history with `getAnomalyHistoryPredictions(model_id,
   "forecast", startTs, endTs, limit)`.
3. Fetch anomaly history with `getAnomalyHistoryPredictions(model_id,
   "anomaly", startTs, endTs, limit)`.
4. Optionally call `pollPredictiveModelInference` with `modelType=BOTH` to get
   status and both prediction sets in one Quarkus MCP call.
5. Summarize counts, latest timestamps, and any error/anomaly highlights.

Do not claim inference succeeded unless one of those calls returns data or an
explicit successful empty result.

## Hard Rules

- Use the Quarkus PdM MCP endpoint. Do not point PdM MCP traffic at the Python
  predictive-maintenance service.
- Never invent device ids, model ids, telemetry keys, algorithm names, status
  values, or predictions.
- Keep forecast and anomaly status/results separate in the final answer.
- Surface API errors directly and stop at the failed phase.
