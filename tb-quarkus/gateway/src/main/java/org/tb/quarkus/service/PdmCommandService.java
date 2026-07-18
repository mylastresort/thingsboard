package org.tb.quarkus.service;

import io.smallrye.reactive.messaging.kafka.api.OutgoingKafkaRecordMetadata;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.context.control.ActivateRequestContext;
import jakarta.inject.Inject;
import org.apache.avro.Schema;
import org.apache.avro.generic.GenericData;
import org.apache.avro.generic.GenericRecord;
import org.apache.avro.generic.GenericRecordBuilder;
import org.eclipse.microprofile.reactive.messaging.Channel;
import org.eclipse.microprofile.reactive.messaging.Emitter;
import org.eclipse.microprofile.reactive.messaging.Message;
import org.jboss.logging.Logger;
import org.tb.quarkus.event.model.GenericLogEntry;
import org.tb.quarkus.event.model.LogEntrySource;
import org.tb.quarkus.event.model.LogEntryType;
import org.tb.quarkus.pdm.PdmAvroSchemas;
import org.tb.quarkus.pdm.PdmCommandType;
import org.tb.quarkus.pdm.PdmJobState;
import org.tb.quarkus.pdm.PdmJobStatus;
import org.tb.quarkus.pdm.PdmModelType;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

@ApplicationScoped
public class PdmCommandService {

    private static final Logger LOG = Logger.getLogger(PdmCommandService.class);

    @Inject PdmJobStateService jobStateService;
    @Inject PdmAvroSchemas avroSchemas;
    @Inject PredictiveModelsRestService predictiveModelsRestService;

    @Channel("pdm-commands-out")
    Emitter<GenericRecord> commands;

    @Channel("pdm-job-state-out")
    Emitter<GenericRecord> jobStates;

    @SuppressWarnings("unchecked")
    @ActivateRequestContext
    public Map<String, Object> train(String forecastId, Map<String, Object> request) {
        request = request == null ? Collections.emptyMap() : request;
        PdmModelType modelType = modelType(string(request.get("modelType")), PdmModelType.BOTH);
        String deviceId = string(request.get("deviceId"));
        String commandId = firstNonBlank(string(request.get("commandId")), UUID.randomUUID().toString());

        List<String> sensorKeys = extractSensorKeys(forecastId);

        List<Map<String, Object>> sentCommands = new ArrayList<>();

        if (modelType == PdmModelType.FORECAST || modelType == PdmModelType.BOTH) {
            if (sensorKeys.isEmpty()) {
                LOG.warnf("No sensors found for forecastId=%s, sending single FORECAST TRAIN", forecastId);
                sendCommand(PdmCommandType.TRAIN, forecastId, PdmModelType.FORECAST, deviceId, commandId, Instant.now(), null);
                sentCommands.add(Map.of("modelType", "FORECAST", "sensorKey", "null"));
            } else {
                for (String sensorKey : sensorKeys) {
                    String sensorCommandId = commandId + "-" + sensorKey;
                    sendCommand(PdmCommandType.TRAIN, forecastId, PdmModelType.FORECAST, deviceId, sensorCommandId, Instant.now(), sensorKey);
                    sentCommands.add(Map.of("modelType", "FORECAST", "sensorKey", sensorKey));
                }
            }
        }

        if (modelType == PdmModelType.ANOMALY || modelType == PdmModelType.BOTH) {
            sendCommand(PdmCommandType.TRAIN, forecastId, PdmModelType.ANOMALY, deviceId, commandId, Instant.now(), null);
            sentCommands.add(Map.of("modelType", "ANOMALY", "sensorKey", "null"));
        }

        var response = new LinkedHashMap<String, Object>();
        response.put("commandId", commandId);
        response.put("forecastId", forecastId);
        response.put("modelType", modelType.name());
        response.put("status", "queued");
        response.put("sensorCount", sensorKeys.size());
        response.put("jobs", initializeJobs(forecastId, modelType, deviceId, sensorKeys));
        return response;
    }

    public void reissueInfer(String forecastId, PdmModelType modelType, String deviceId, String sensorKey) {
        String commandId = UUID.randomUUID().toString();
        sendCommand(PdmCommandType.INFER, forecastId, modelType, deviceId, commandId, Instant.now(), sensorKey);
    }

    @ActivateRequestContext
    public Map<String, Object> infer(String forecastId, Map<String, Object> request) {
        request = request == null ? Collections.emptyMap() : request;
        PdmModelType modelType = modelType(string(request.get("modelType")), PdmModelType.BOTH);
        String deviceId = string(request.get("deviceId"));
        String commandId = firstNonBlank(string(request.get("commandId")), UUID.randomUUID().toString());

        List<String> sensorKeys = extractSensorKeys(forecastId);

        if (modelType == PdmModelType.FORECAST || modelType == PdmModelType.BOTH) {
            if (sensorKeys.isEmpty()) {
                sendCommand(PdmCommandType.INFER, forecastId, PdmModelType.FORECAST, deviceId, commandId, Instant.now(), null);
            } else {
                for (String sensorKey : sensorKeys) {
                    sendCommand(PdmCommandType.INFER, forecastId, PdmModelType.FORECAST, deviceId, commandId + "-" + sensorKey, Instant.now(), sensorKey);
                }
            }
        }
        if (modelType == PdmModelType.ANOMALY || modelType == PdmModelType.BOTH) {
            sendCommand(PdmCommandType.INFER, forecastId, PdmModelType.ANOMALY, deviceId, commandId, Instant.now(), null);
        }

        var response = new LinkedHashMap<String, Object>();
        response.put("commandId", commandId);
        response.put("forecastId", forecastId);
        response.put("modelType", modelType.name());
        response.put("status", "queued");
        response.put("jobs", updateStatus(forecastId, modelType, PdmJobStatus.RUNNING));
        return response;
    }

    public Map<String, Object> stop(String forecastId, String commandId) {
        return control(PdmCommandType.STOP, forecastId, null, commandId);
    }

    public Map<String, Object> pause(String forecastId, String modelType, String commandId) {
        return control(PdmCommandType.PAUSE, forecastId, modelType, commandId);
    }

    public Map<String, Object> unpause(String forecastId, String modelType, String commandId) {
        return control(PdmCommandType.UNPAUSE, forecastId, modelType, commandId);
    }

    public Map<String, Object> status(String forecastId) {
        PdmJobState anomaly = jobStateService.get(modelId(forecastId, PdmModelType.ANOMALY));
        List<PdmJobState> forecastStates = getForecastSensorStates(forecastId);
        var value = new LinkedHashMap<String, Object>();
        value.put("forecastId", forecastId);
        value.put("status", aggregateStatus(anomaly, forecastStates));
        value.put("trainingProgress", aggregateTrainingProgress(anomaly, forecastStates));
        value.put("trainingStep", aggregateTrainingStep(anomaly, forecastStates));
        value.put("anomaly", responseState(anomaly));
        value.put("forecast", aggregateForecastResponse(forecastStates));
        value.put("recovering", isWorkerDisconnected(anomaly, forecastStates));
        return value;
    }

    public Map<String, Object> logs(String forecastId, String modelType, Integer limit) {
        PdmModelType type = modelType(modelType, PdmModelType.BOTH);
        int resolvedLimit = limit == null ? 100 : limit;
        if (type != PdmModelType.BOTH) {
            if (type == PdmModelType.FORECAST) {
                List<Map<String, Object>> logs = new ArrayList<>();
                for (PdmJobState fs : getForecastSensorStates(forecastId)) {
                    logs.addAll(jobStateService.logs(fs.modelId(), resolvedLimit));
                }
                logs.sort(Comparator.comparing(log -> string(log.get("timestamp")), Comparator.nullsLast(String::compareTo)));
                int from = Math.max(0, logs.size() - resolvedLimit);
                List<Map<String, Object>> limited = logs.subList(from, logs.size());
                return Map.of("logs", limited, "count", limited.size(), "modelType", type.name());
            }
            var logs = jobStateService.logs(modelId(forecastId, type), resolvedLimit);
            return Map.of("logs", logs, "count", logs.size(), "modelType", type.name());
        }

        List<Map<String, Object>> logs = new ArrayList<>();
        for (PdmJobState fs : getForecastSensorStates(forecastId)) {
            logs.addAll(jobStateService.logs(fs.modelId(), resolvedLimit));
        }
        logs.addAll(jobStateService.logs(modelId(forecastId, PdmModelType.ANOMALY), resolvedLimit));
        logs.sort(Comparator.comparing(log -> string(log.get("timestamp")), Comparator.nullsLast(String::compareTo)));
        int from = Math.max(0, logs.size() - resolvedLimit);
        List<Map<String, Object>> limited = logs.subList(from, logs.size());
        return Map.of("logs", limited, "count", limited.size(), "modelType", type.name());
    }

    public Map<String, Object> predictions(String forecastId, String modelType, Long startTs, Long endTs, Integer limit) {
        PdmModelType type = modelType(modelType, PdmModelType.FORECAST);
        int resolvedLimit = limit == null ? 100 : limit;

        List<Map<String, Object>> allPredictions = new ArrayList<>();
        if (type == PdmModelType.FORECAST) {
            for (PdmJobState fs : getForecastSensorStates(forecastId)) {
                allPredictions.addAll(jobStateService.predictions(fs.modelId(), startTs, endTs, resolvedLimit));
            }
        } else {
            allPredictions.addAll(jobStateService.predictions(modelId(forecastId, type), startTs, endTs, resolvedLimit));
        }

        var response = new LinkedHashMap<String, Object>();
        response.put("forecastId", forecastId);
        response.put("modelType", type.name());
        response.put("startTs", startTs);
        response.put("endTs", endTs);
        response.put("predictions", allPredictions);
        response.put("count", allPredictions.size());
        return response;
    }

    private Map<String, Object> control(PdmCommandType commandType, String forecastId, String modelType, String commandId) {
        PdmModelType type = modelType(modelType, PdmModelType.BOTH);
        String id = firstNonBlank(commandId, UUID.randomUUID().toString());
        sendCommand(commandType, forecastId, type, null, id, Instant.now(), null);

        Map<String, Object> jobs = switch (commandType) {
            case PAUSE -> updatePause(forecastId, type, true);
            case UNPAUSE -> updatePause(forecastId, type, false);
            case STOP -> updateStatus(forecastId, type, PdmJobStatus.STOPPED);
            case TRAIN, INFER -> Map.of();
        };

        return Map.of(
                "commandId", id,
                "forecastId", forecastId,
                "commandType", commandType.name(),
                "modelType", type.name(),
                "status", "queued",
                "jobs", jobs);
    }

    private Map<String, Object> initializeJobs(String forecastId, PdmModelType modelType, String deviceId, List<String> sensorKeys) {
        var jobs = new LinkedHashMap<String, Object>();
        if (modelType == PdmModelType.ANOMALY || modelType == PdmModelType.BOTH) {
            PdmJobState state = jobStateService.initialize(modelId(forecastId, PdmModelType.ANOMALY), "AnomalyPredictor", deviceId, PdmJobStatus.TRAINING);
            publishState(state);
            log(state.modelId(), "info", "AnomalyPredictor training command queued");
            jobs.put("anomaly", state.toResponse());
        }
        if (modelType == PdmModelType.FORECAST || modelType == PdmModelType.BOTH) {
            List<Map<String, Object>> forecastJobs = new ArrayList<>();
            if (sensorKeys.isEmpty()) {
                PdmJobState state = jobStateService.initialize(modelId(forecastId, PdmModelType.FORECAST), "ForecastModel", deviceId, PdmJobStatus.TRAINING);
                publishState(state);
                log(state.modelId(), "info", "ForecastModel training command queued");
                forecastJobs.add(state.toResponse());
            } else {
                for (String sensorKey : sensorKeys) {
                    String sensorModelId = forecastModelId(forecastId, sensorKey);
                    PdmJobState state = jobStateService.initialize(sensorModelId, "ForecastModel", deviceId, PdmJobStatus.TRAINING);
                    publishState(state);
                    log(sensorModelId, "info", "ForecastModel training command queued for sensor " + sensorKey);
                    forecastJobs.add(state.toResponse());
                }
            }
            jobs.put("forecast", forecastJobs);
        }
        return jobs;
    }

    private Map<String, Object> updatePause(String forecastId, PdmModelType modelType, boolean paused) {
        var jobs = new LinkedHashMap<String, Object>();
        for (PdmModelType type : targetTypes(modelType)) {
            if (type == PdmModelType.FORECAST) {
                for (PdmJobState fs : getForecastSensorStates(forecastId)) {
                    PdmJobState state = jobStateService.setPaused(fs.modelId(), paused);
                    publishState(state);
                    log(state.modelId(), "info", paused ? "Job pause requested" : "Job resume requested");
                    jobs.put(fs.modelId(), state.toResponse());
                }
            } else {
                PdmJobState state = jobStateService.setPaused(modelId(forecastId, type), paused);
                publishState(state);
                log(state.modelId(), "info", paused ? "Job pause requested" : "Job resume requested");
                jobs.put(type.name().toLowerCase(), state.toResponse());
            }
        }
        return jobs;
    }

    private Map<String, Object> updateStatus(String forecastId, PdmModelType modelType, PdmJobStatus status) {
        var jobs = new LinkedHashMap<String, Object>();
        for (PdmModelType type : targetTypes(modelType)) {
            if (type == PdmModelType.FORECAST) {
                for (PdmJobState fs : getForecastSensorStates(forecastId)) {
                    PdmJobState state = jobStateService.updateStatus(fs.modelId(), status);
                    publishState(state);
                    log(state.modelId(), "info", "Job " + status.name().toLowerCase() + " requested");
                    jobs.put(fs.modelId(), state.toResponse());
                }
            } else {
                PdmJobState state = jobStateService.updateStatus(modelId(forecastId, type), status);
                publishState(state);
                log(state.modelId(), "info", "Job " + status.name().toLowerCase() + " requested");
                jobs.put(type.name().toLowerCase(), state.toResponse());
            }
        }
        return jobs;
    }

    private void sendCommand(PdmCommandType commandType, String forecastId, PdmModelType modelType,
                             String deviceId, String commandId, Instant timestamp, String sensorKey) {
        GenericRecord command = new GenericRecordBuilder(avroSchemas.command())
                .set("commandType", enumValue(avroSchemas.command().getField("commandType").schema(), commandType.name()))
                .set("forecastId", forecastId)
                .set("modelType", modelType == null ? null : enumValue(nonNull(avroSchemas.command().getField("modelType").schema()), modelType.name()))
                .set("deviceId", deviceId)
                .set("timestamp", timestamp.toEpochMilli())
                .set("commandId", commandId)
                .set("sensorKey", sensorKey)
                .build();
        try {
            String partitionKey = sensorKey != null ? forecastId + "/" + sensorKey : forecastId;
            commands.send(Message.of(command).addMetadata(OutgoingKafkaRecordMetadata.<String>builder()
                    .withKey(partitionKey)
                    .build()));
            LOG.infof("Sent PdM command commandType=%s forecastId=%s modelType=%s sensorKey=%s commandId=%s",
                    commandType, forecastId, modelType, sensorKey, commandId);
        } catch (Exception e) {
            LOG.errorf(e, "Failed to send PdM command commandType=%s forecastId=%s modelType=%s sensorKey=%s commandId=%s",
                    commandType, forecastId, modelType, sensorKey, commandId);
            throw e;
        }
    }

    private void publishState(PdmJobState state) {
        GenericRecord record = new GenericRecordBuilder(avroSchemas.jobState())
                .set("modelId", state.modelId())
                .set("modelType", state.modelType() == null ? "" : state.modelType())
                .set("deviceId", state.deviceId())
                .set("status", enumValue(avroSchemas.jobState().getField("status").schema(), state.status().name()))
                .set("paused", state.paused())
                .set("iterations", state.iterations())
                .set("startTime", state.startTime() == null ? null : state.startTime().toEpochMilli())
                .set("lastRun", state.lastRun() == null ? null : state.lastRun().toEpochMilli())
                .build();
        try {
            jobStates.send(Message.of(record).addMetadata(OutgoingKafkaRecordMetadata.<String>builder()
                    .withKey(state.modelId())
                    .build()));
            LOG.debugf("Published PdM job state modelId=%s status=%s", state.modelId(), state.status());
        } catch (Exception e) {
            LOG.warnf(e, "Failed to publish PdM job state modelId=%s status=%s", state.modelId(), state.status());
        }
    }

    private void log(String modelId, String level, String message) {
        GenericLogEntry entry = new GenericLogEntry();
        entry.setLevel(level);
        entry.setSource(modelId.contains("forecast") ? LogEntrySource.FORECAST_MODEL : LogEntrySource.ANOMALY_MODEL);
        entry.setType(modelId.contains("forecast") ? LogEntryType.FORECAST : LogEntryType.ANOMALY);
        entry.setMessage(message);
        entry.setTimestamp(Instant.now().toString());
        jobStateService.appendLog(modelId, entry);
    }

    private GenericData.EnumSymbol enumValue(Schema schema, String value) {
        return new GenericData.EnumSymbol(schema, value);
    }

    private Schema nonNull(Schema schema) {
        return schema.getTypes().stream()
                .filter(type -> type.getType() != Schema.Type.NULL)
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("Union schema does not contain a non-null type"));
    }

    private Object responseState(PdmJobState state) {
        return state == null ? null : state.toResponse();
    }

    private String aggregateStatus(PdmJobState anomaly, List<PdmJobState> forecastStates) {
        if (anomaly == null && forecastStates.isEmpty()) {
            return "inactive";
        }
        if (hasStatus(PdmJobStatus.ERROR, anomaly) || forecastStates.stream().anyMatch(s -> s != null && s.status() == PdmJobStatus.ERROR)) {
            return "error";
        }
        if (hasStatus(PdmJobStatus.TRAINING, anomaly) || forecastStates.stream().anyMatch(s -> s != null && s.status() == PdmJobStatus.TRAINING)) {
            return "pending";
        }
        if (hasStatus(PdmJobStatus.RUNNING, anomaly) || hasStatus(PdmJobStatus.PAUSED, anomaly)
                || forecastStates.stream().anyMatch(s -> s != null && (s.status() == PdmJobStatus.RUNNING || s.status() == PdmJobStatus.PAUSED))) {
            return "active";
        }
        return "inactive";
    }

    private Integer aggregateTrainingProgress(PdmJobState anomaly, List<PdmJobState> forecastStates) {
        Integer anomalyProgress = anomaly == null ? null : anomaly.trainingProgress();
        Integer minForecast = forecastStates.stream()
                .filter(s -> s != null && s.trainingProgress() != null)
                .map(PdmJobState::trainingProgress)
                .min(Integer::compareTo)
                .orElse(null);
        if (anomalyProgress == null) {
            return minForecast;
        }
        if (minForecast == null) {
            return anomalyProgress;
        }
        return Math.min(anomalyProgress, minForecast);
    }

    private String aggregateTrainingStep(PdmJobState anomaly, List<PdmJobState> forecastStates) {
        for (PdmJobState fs : forecastStates) {
            if (fs != null && fs.status() == PdmJobStatus.TRAINING && fs.trainingStep() != null) {
                return fs.trainingStep();
            }
        }
        if (anomaly != null && anomaly.status() == PdmJobStatus.TRAINING && anomaly.trainingStep() != null) {
            return anomaly.trainingStep();
        }
        for (PdmJobState fs : forecastStates) {
            if (fs != null && fs.trainingStep() != null) {
                return fs.trainingStep();
            }
        }
        return anomaly == null ? null : anomaly.trainingStep();
    }

    private List<Map<String, Object>> aggregateForecastResponse(List<PdmJobState> forecastStates) {
        return forecastStates.stream()
                .filter(Objects::nonNull)
                .map(PdmJobState::toResponse)
                .toList();
    }

    private List<PdmJobState> getForecastSensorStates(String forecastId) {
        String prefix = "job:" + forecastId + "/forecast_model";
        List<String> keys = jobStateService.scanJobKeys(prefix + "*");
        return keys.stream()
                .map(key -> {
                    String modelId = key.substring("job:".length());
                    return jobStateService.get(modelId);
                })
                .filter(Objects::nonNull)
                .toList();
    }

    private boolean hasStatus(PdmJobStatus status, PdmJobState... states) {
        for (PdmJobState state : states) {
            if (state != null && state.status() == status) {
                return true;
            }
        }
        return false;
    }

    private PdmModelType[] targetTypes(PdmModelType modelType) {
        return modelType == PdmModelType.BOTH
                ? new PdmModelType[]{PdmModelType.ANOMALY, PdmModelType.FORECAST}
                : new PdmModelType[]{modelType};
    }

    private PdmModelType modelType(String value, PdmModelType fallback) {
        if (value == null || value.isBlank()) {
            return fallback;
        }
        return switch (value.toLowerCase()) {
            case "anomaly", "anomaly_predictor", "anomalypredictor" -> PdmModelType.ANOMALY;
            case "forecast", "forecast_model", "forecastmodel" -> PdmModelType.FORECAST;
            case "both", "all" -> PdmModelType.BOTH;
            default -> PdmModelType.valueOf(value.toUpperCase());
        };
    }

    private String modelId(String forecastId, PdmModelType type) {
        return forecastId + (type == PdmModelType.ANOMALY ? "/anomaly_predictor" : "/forecast_model");
    }

    private String forecastModelId(String forecastId, String sensorKey) {
        return forecastId + "/forecast_model/" + sensorKey;
    }

    @SuppressWarnings("unchecked")
    List<String> extractSensorKeys(String forecastId) {
        try {
            Map<String, Object> model = predictiveModelsRestService.getPredictiveModel(forecastId);
            Object attributes = model.get("attributes");
            if (attributes instanceof List<?> list) {
                return list.stream()
                        .filter(obj -> obj instanceof Map<?, ?>)
                        .map(obj -> ((Map<?, ?>) obj).get("key"))
                        .filter(key -> key != null)
                        .map(Object::toString)
                        .toList();
            }
        } catch (Exception e) {
            LOG.warnf(e, "Failed to extract sensor keys for forecastId=%s", forecastId);
        }
        return List.of();
    }

    private String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return null;
    }

    private static final java.time.Duration FORECAST_STALE_THRESHOLD = java.time.Duration.ofSeconds(60);
    private static final java.time.Duration ANOMALY_STALE_THRESHOLD = java.time.Duration.ofHours(48);

    private boolean isWorkerDisconnected(PdmJobState anomaly, List<PdmJobState> forecastStates) {
        if (isJobStale(anomaly, ANOMALY_STALE_THRESHOLD)) {
            return true;
        }
        return forecastStates.stream().anyMatch(s -> isJobStale(s, FORECAST_STALE_THRESHOLD));
    }

    private boolean isJobStale(PdmJobState job, java.time.Duration threshold) {
        if (job == null || job.status() != PdmJobStatus.RUNNING || job.paused()) {
            return false;
        }
        if (job.lastRun() == null) {
            return true;
        }
        return java.time.Instant.now().isAfter(job.lastRun().plus(threshold));
    }

    private String string(Object value) {
        return value == null ? null : value.toString();
    }
}
