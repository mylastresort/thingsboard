package org.tb.quarkus.service;

import org.apache.avro.generic.GenericRecord;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.eclipse.microprofile.reactive.messaging.Incoming;
import org.jboss.logging.Logger;
import org.tb.quarkus.event.model.GenericLogEntry;
import org.tb.quarkus.event.model.LogEntrySource;
import org.tb.quarkus.event.model.LogEntryType;
import org.tb.quarkus.pdm.PdmJobStatus;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.time.Instant;

@ApplicationScoped
public class PdmEventConsumer {

    private static final Logger LOG = Logger.getLogger(PdmEventConsumer.class);

    @Inject PdmJobStateService jobStateService;
    @Inject ObjectMapper mapper;

    @Incoming("pdm-events-in")
    public void consume(GenericRecord event) {
        String eventType = string(event.get("eventType"));
        String modelId = string(event.get("modelId"));
        if (modelId == null || eventType == null) {
            return;
        }

        switch (eventType) {
            case "LOG" -> appendLog(modelId, (GenericRecord) event.get("log"), longValue(event.get("timestamp")));
            case "PROGRESS" -> appendProgress(modelId, (GenericRecord) event.get("progress"), longValue(event.get("timestamp")));
            case "PREDICTION" -> appendPrediction(modelId, (GenericRecord) event.get("prediction"), event.get("iteration"), longValue(event.get("timestamp")));
            case "ALARM" -> LOG.infof("PdM alarm event received for %s", modelId);
            default -> LOG.debugf("Ignoring unknown PdM event type %s for %s", eventType, modelId);
        }
    }

    private void appendPrediction(String modelId, GenericRecord prediction, Object iteration, long timestamp) {
        jobStateService.updateStatus(modelId, PdmJobStatus.RUNNING);
        if (prediction == null) {
            return;
        }
        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("timestamp", timestamp);
        entry.put("modelId", modelId);
        entry.put("iteration", iteration instanceof Number number ? number.intValue() : null);
        entry.put("modelType", string(prediction.get("modelType")));
        entry.put("sensor", string(prediction.get("sensor")));
        entry.put("resultJson", string(prediction.get("resultJson")));
        jobStateService.appendPrediction(modelId, entry);
        jobStateService.appendLog(modelId, predictionLog(modelId, prediction, iteration, timestamp));
    }

    private void appendProgress(String modelId, GenericRecord progress, long timestamp) {
        if (progress == null) {
            return;
        }

        String step = string(progress.get("step"));
        String message = string(progress.get("message"));
        Integer percent = progress.get("percent") instanceof Number number ? number.intValue() : null;
        PdmJobStatus status = percent != null && percent >= 100 ? PdmJobStatus.RUNNING : PdmJobStatus.TRAINING;
        jobStateService.updateTrainingProgress(modelId, step, percent, status);
        String text = message == null || message.isBlank() ? step : message;
        if (percent != null) {
            text = "[" + percent + "%] " + text;
        }

        GenericLogEntry entry = new GenericLogEntry();
        entry.setLevel("info");
        entry.setSource(source(modelId.toLowerCase().contains("forecast") ? "ForecastModel" : "AnomalyPredictor"));
        entry.setType(modelId.toLowerCase().contains("forecast") ? LogEntryType.FORECAST : LogEntryType.ANOMALY);
        entry.setMessage(text);
        entry.setTimestamp(Instant.ofEpochMilli(timestamp).toString());
        jobStateService.appendLog(modelId, entry);
    }

    private GenericLogEntry predictionLog(String modelId, GenericRecord prediction, Object iteration, long timestamp) {
        boolean forecast = modelId.toLowerCase().contains("forecast");
        GenericLogEntry entry = new GenericLogEntry();
        entry.setLevel("PREDICTION");
        entry.setSource(source(forecast ? "ForecastModel" : "AnomalyPredictor"));
        entry.setType(forecast ? LogEntryType.FORECAST : LogEntryType.ANOMALY);
        entry.setTimestamp(Instant.ofEpochMilli(timestamp).toString());

        Object result = readJson(string(prediction.get("resultJson")));
        var message = new LinkedHashMap<String, Object>();
        message.put("sensor", string(prediction.get("sensor")));
        message.put("iteration", iteration instanceof Number number ? number.intValue() : null);
        if (forecast) {
            message.put("prediction_type", "forecast");
            message.put("result", result);
        } else {
            message.put("type", "prediction");
            message.put("result", result instanceof List<?> ? result : List.of(result));
        }
        entry.setMessage(message);
        return entry;
    }

    private void appendLog(String modelId, GenericRecord log, long timestamp) {
        if (log == null) {
            return;
        }
        GenericLogEntry entry = new GenericLogEntry();
        entry.setLevel(string(log.get("level")));
        entry.setSource(source(string(log.get("source"))));
        entry.setType(modelId.toLowerCase().contains("forecast") ? LogEntryType.FORECAST : LogEntryType.ANOMALY);
        entry.setMessage(string(log.get("message")));
        entry.setTimestamp(Instant.ofEpochMilli(timestamp).toString());
        jobStateService.appendLog(modelId, entry);
    }

    private LogEntrySource source(String value) {
        return "ForecastModel".equals(value) ? LogEntrySource.FORECAST_MODEL : LogEntrySource.ANOMALY_MODEL;
    }

    private long longValue(Object value) {
        return value instanceof Number number ? number.longValue() : System.currentTimeMillis();
    }

    private String string(Object value) {
        return value == null ? null : value.toString();
    }

    private Object readJson(String value) {
        if (value == null || value.isBlank()) {
            return Map.of();
        }
        try {
            return mapper.readValue(value, Object.class);
        } catch (Exception e) {
            return value;
        }
    }
}
