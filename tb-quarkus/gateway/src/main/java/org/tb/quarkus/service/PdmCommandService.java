package org.tb.quarkus.service;

import io.smallrye.reactive.messaging.kafka.api.OutgoingKafkaRecordMetadata;
import jakarta.enterprise.context.ApplicationScoped;
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
import java.util.UUID;

@ApplicationScoped
public class PdmCommandService {

    private static final Logger LOG = Logger.getLogger(PdmCommandService.class);

    @Inject PdmJobStateService jobStateService;
    @Inject PdmAvroSchemas avroSchemas;

    @Channel("pdm-commands-out")
    Emitter<GenericRecord> commands;

    @Channel("pdm-job-state-out")
    Emitter<GenericRecord> jobStates;

    public Map<String, Object> train(String forecastId, Map<String, Object> request) {
        request = request == null ? Collections.emptyMap() : request;
        PdmModelType modelType = modelType(string(request.get("modelType")), PdmModelType.BOTH);
        String deviceId = string(request.get("deviceId"));
        String commandId = firstNonBlank(string(request.get("commandId")), UUID.randomUUID().toString());
        sendCommand(PdmCommandType.TRAIN, forecastId, modelType, deviceId, commandId, Instant.now());

        var response = new LinkedHashMap<String, Object>();
        response.put("commandId", commandId);
        response.put("forecastId", forecastId);
        response.put("modelType", modelType.name());
        response.put("status", "queued");
        response.put("jobs", initializeJobs(forecastId, modelType, deviceId));
        return response;
    }

    public Map<String, Object> infer(String forecastId, Map<String, Object> request) {
        request = request == null ? Collections.emptyMap() : request;
        PdmModelType modelType = modelType(string(request.get("modelType")), PdmModelType.BOTH);
        String deviceId = string(request.get("deviceId"));
        String commandId = firstNonBlank(string(request.get("commandId")), UUID.randomUUID().toString());
        sendCommand(PdmCommandType.INFER, forecastId, modelType, deviceId, commandId, Instant.now());

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
        PdmJobState forecast = jobStateService.get(modelId(forecastId, PdmModelType.FORECAST));
        var value = new LinkedHashMap<String, Object>();
        value.put("forecastId", forecastId);
        value.put("status", aggregateStatus(anomaly, forecast));
        value.put("trainingProgress", aggregateTrainingProgress(anomaly, forecast));
        value.put("trainingStep", aggregateTrainingStep(anomaly, forecast));
        value.put("anomaly", responseState(anomaly));
        value.put("forecast", responseState(forecast));
        return value;
    }

    public Map<String, Object> logs(String forecastId, String modelType, Integer limit) {
        PdmModelType type = modelType(modelType, PdmModelType.BOTH);
        int resolvedLimit = limit == null ? 100 : limit;
        if (type != PdmModelType.BOTH) {
            var logs = jobStateService.logs(modelId(forecastId, type), resolvedLimit);
            return Map.of("logs", logs, "count", logs.size(), "modelType", type.name());
        }

        List<Map<String, Object>> logs = new ArrayList<>();
        logs.addAll(jobStateService.logs(modelId(forecastId, PdmModelType.FORECAST), resolvedLimit));
        logs.addAll(jobStateService.logs(modelId(forecastId, PdmModelType.ANOMALY), resolvedLimit));
        logs.sort(Comparator.comparing(log -> string(log.get("timestamp")), Comparator.nullsLast(String::compareTo)));
        int from = Math.max(0, logs.size() - resolvedLimit);
        List<Map<String, Object>> limited = logs.subList(from, logs.size());
        return Map.of("logs", limited, "count", limited.size(), "modelType", type.name());
    }

    public Map<String, Object> predictions(String forecastId, String modelType, Long startTs, Long endTs, Integer limit) {
        PdmModelType type = modelType(modelType, PdmModelType.FORECAST);
        var predictions = jobStateService.predictions(modelId(forecastId, type), startTs, endTs, limit == null ? 100 : limit);
        var response = new LinkedHashMap<String, Object>();
        response.put("forecastId", forecastId);
        response.put("modelType", type.name());
        response.put("startTs", startTs);
        response.put("endTs", endTs);
        response.put("predictions", predictions);
        response.put("count", predictions.size());
        return response;
    }

    private Map<String, Object> control(PdmCommandType commandType, String forecastId, String modelType, String commandId) {
        PdmModelType type = modelType(modelType, PdmModelType.BOTH);
        String id = firstNonBlank(commandId, UUID.randomUUID().toString());
        sendCommand(commandType, forecastId, type, null, id, Instant.now());

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

    private Map<String, Object> initializeJobs(String forecastId, PdmModelType modelType, String deviceId) {
        var jobs = new LinkedHashMap<String, Object>();
        if (modelType == PdmModelType.ANOMALY || modelType == PdmModelType.BOTH) {
            PdmJobState state = jobStateService.initialize(modelId(forecastId, PdmModelType.ANOMALY), "AnomalyPredictor", deviceId, PdmJobStatus.TRAINING);
            publishState(state);
            log(state.modelId(), "info", "AnomalyPredictor training command queued");
            jobs.put("anomaly", state.toResponse());
        }
        if (modelType == PdmModelType.FORECAST || modelType == PdmModelType.BOTH) {
            PdmJobState state = jobStateService.initialize(modelId(forecastId, PdmModelType.FORECAST), "ForecastModel", deviceId, PdmJobStatus.TRAINING);
            publishState(state);
            log(state.modelId(), "info", "ForecastModel training command queued");
            jobs.put("forecast", state.toResponse());
        }
        return jobs;
    }

    private Map<String, Object> updatePause(String forecastId, PdmModelType modelType, boolean paused) {
        var jobs = new LinkedHashMap<String, Object>();
        for (PdmModelType type : targetTypes(modelType)) {
            PdmJobState state = jobStateService.setPaused(modelId(forecastId, type), paused);
            publishState(state);
            log(state.modelId(), "info", paused ? "Job pause requested" : "Job resume requested");
            jobs.put(type.name().toLowerCase(), state.toResponse());
        }
        return jobs;
    }

    private Map<String, Object> updateStatus(String forecastId, PdmModelType modelType, PdmJobStatus status) {
        var jobs = new LinkedHashMap<String, Object>();
        for (PdmModelType type : targetTypes(modelType)) {
            PdmJobState state = jobStateService.updateStatus(modelId(forecastId, type), status);
            publishState(state);
            log(state.modelId(), "info", "Job " + status.name().toLowerCase() + " requested");
            jobs.put(type.name().toLowerCase(), state.toResponse());
        }
        return jobs;
    }

    private void sendCommand(PdmCommandType commandType, String forecastId, PdmModelType modelType,
                             String deviceId, String commandId, Instant timestamp) {
        GenericRecord command = new GenericRecordBuilder(avroSchemas.command())
                .set("commandType", enumValue(avroSchemas.command().getField("commandType").schema(), commandType.name()))
                .set("forecastId", forecastId)
                .set("modelType", modelType == null ? null : enumValue(nonNull(avroSchemas.command().getField("modelType").schema()), modelType.name()))
                .set("deviceId", deviceId)
                .set("timestamp", timestamp.toEpochMilli())
                .set("commandId", commandId)
                .build();
        try {
            commands.send(Message.of(command).addMetadata(OutgoingKafkaRecordMetadata.<String>builder()
                    .withKey(forecastId)
                    .build()));
            LOG.infof("Sent PdM command commandType=%s forecastId=%s modelType=%s commandId=%s",
                    commandType, forecastId, modelType, commandId);
        } catch (Exception e) {
            LOG.errorf(e, "Failed to send PdM command commandType=%s forecastId=%s modelType=%s commandId=%s",
                    commandType, forecastId, modelType, commandId);
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

    private String aggregateStatus(PdmJobState anomaly, PdmJobState forecast) {
        if (anomaly == null && forecast == null) {
            return "inactive";
        }
        if (hasStatus(PdmJobStatus.ERROR, anomaly, forecast)) {
            return "error";
        }
        if (hasStatus(PdmJobStatus.TRAINING, anomaly, forecast)) {
            return "pending";
        }
        if (hasStatus(PdmJobStatus.RUNNING, anomaly, forecast)) {
            return "active";
        }
        return "inactive";
    }

    private Integer aggregateTrainingProgress(PdmJobState anomaly, PdmJobState forecast) {
        Integer anomalyProgress = anomaly == null ? null : anomaly.trainingProgress();
        Integer forecastProgress = forecast == null ? null : forecast.trainingProgress();
        if (anomalyProgress == null) {
            return forecastProgress;
        }
        if (forecastProgress == null) {
            return anomalyProgress;
        }
        return Math.min(anomalyProgress, forecastProgress);
    }

    private String aggregateTrainingStep(PdmJobState anomaly, PdmJobState forecast) {
        if (forecast != null && forecast.status() == PdmJobStatus.TRAINING && forecast.trainingStep() != null) {
            return forecast.trainingStep();
        }
        if (anomaly != null && anomaly.status() == PdmJobStatus.TRAINING && anomaly.trainingStep() != null) {
            return anomaly.trainingStep();
        }
        if (forecast != null && forecast.trainingStep() != null) {
            return forecast.trainingStep();
        }
        return anomaly == null ? null : anomaly.trainingStep();
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

    private String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return null;
    }

    private String string(Object value) {
        return value == null ? null : value.toString();
    }
}
