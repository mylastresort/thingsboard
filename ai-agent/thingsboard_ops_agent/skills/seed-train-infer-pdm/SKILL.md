---
name: seed-train-infer-pdm
description: >
  Use when the user asks to seed or "see" a new machine through the Quarkus
  PdM MCP endpoint, create a predictive model, train it, start inference, and
  poll forecast and anomaly results. This is a test-example PdM workflow skill
  for pdm_agent.
tools:
  - getSeedMachineOptions
  - seedMachine
  - getAvailableModels
  - createForecast
  - createPredictiveModel
  - createAndTrainPredictiveModel
  - trainPredictiveModel
  - inferPredictiveModel
  - pollPredictiveModelInference
  - getForecastStatus
  - getAnomalyHistoryPredictions
---

# Seed, Train, and Infer PdM

This skill is owned by `pdm_agent`. It drives the complete Quarkus PdM example
flow: use the Quarkus MCP endpoint, seed one machine, create a model config,
train it, start inference, then poll both forecast and anomaly outputs.

## Phase 0 - Defaults

If the user asks for a test/example flow and does not provide values, use these
defaults without asking follow-up questions:

- MCP source: the Quarkus PdM MCP service.
- Seed request: `mode=maxMachines`, `maxMachines=1`, `machinePrefix=agent-pdm`,
  `shiftToNow=true`, `workers=1`.
- Forecast training window: last 30 days ending now.
- Anomaly training window: last 60 days ending now.
- Forecast model type: first available `ForecastModel` from `getAvailableModels`.
- Anomaly model type: first available `AnomalyPredictor` from `getAvailableModels`.
- Prediction history limit: 100.

Ask only for missing values when the user explicitly wants a non-example,
production, or named-device run.

## Phase 1 - Use the Quarkus PdM MCP endpoint

Before calling any PdM operation, use `pdm_agent`, which must be connected to
the Quarkus MCP SSE endpoint. Do not use the Python predictive-maintenance
service as an MCP endpoint, and do not invent raw HTTP calls when Quarkus MCP
tools are available.

## Phase 2 - Seed and identify the machine

1. Call `getSeedMachineOptions` to verify server-supported defaults and machine
   options.
2. Call `seedMachine` with either the user's requested machine selection or the
   Phase 0 default seed request.
3. Read `machineToDevice` from the seed result. Use the returned ThingsBoard
   device id as the device id for the new predictive model. Never invent or
   transform a device id.

If no device id is returned, stop and report the seed result.

## Phase 3 - Create the predictive model

1. Call `getAvailableModels`.
2. Select one forecast algorithm and one anomaly algorithm using the user's
   preference or Phase 0 defaults.
3. Call `createForecast`, `createPredictiveModel`, or
   `createAndTrainPredictiveModel` with a model config containing:
   - `name`: a short unique name derived from the seeded machine name.
   - `deviceId`: the seeded device id.
   - `forecastAlgorithm`: selected forecast model name.
   - `anomalyAlgorithm`: selected anomaly predictor name.
   - `forecastStartDate` / `forecastEndDate`: millisecond timestamps.
   - `anomalyStartDate` / `anomalyEndDate`: millisecond timestamps.
   - `fields` or telemetry attributes only when known from the seed result or
     provided by the user; do not guess telemetry key names.
4. Capture the returned forecast/model id from `id`, `forecastId`, `trueId`, or
   the obvious id field in the response.

If the API returns no id, stop and report the create response.

## Phase 4 - Train and poll status

1. If you did not already use `createAndTrainPredictiveModel`, call
   `trainPredictiveModel` for the captured model id with `modelType=BOTH`
   unless the user requested only forecast or only anomaly.
2. Poll status using `getForecastStatus` and/or `pollPredictiveModelInference`,
   preferring the status tools exposed by `pdm_agent`.
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
- Never invent machine ids, device ids, model ids, telemetry keys, algorithm
  names, status values, or predictions.
- Keep forecast and anomaly status/results separate in the final answer.
- Surface API errors directly and stop at the failed phase.
