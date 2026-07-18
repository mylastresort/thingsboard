package org.tb.quarkus.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.quarkus.redis.datasource.RedisDataSource;
import io.quarkus.redis.datasource.hash.HashCommands;
import io.quarkus.redis.datasource.keys.KeyCommands;
import io.quarkus.redis.datasource.keys.KeyScanArgs;
import io.quarkus.redis.datasource.list.ListCommands;
import jakarta.annotation.PostConstruct;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import org.tb.quarkus.event.model.GenericLogEntry;
import org.tb.quarkus.pdm.PdmJobState;
import org.tb.quarkus.pdm.PdmJobStatus;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@ApplicationScoped
public class PdmJobStateService {

    private static final int MAX_LOG_ENTRIES = 1000;
    private static final int MAX_PREDICTION_ENTRIES = 1000;
    private static final Duration LOG_TTL = Duration.ofHours(24);

    @Inject RedisDataSource redis;
    @Inject ObjectMapper mapper;

    HashCommands<String, String, String> hashes;
    ListCommands<String, String> lists;
    KeyCommands<String> keys;

    @PostConstruct
    void init() {
        hashes = redis.hash(String.class);
        lists = redis.list(String.class);
        keys = redis.key();
    }

    public PdmJobState initialize(String modelId, String modelType, String deviceId, PdmJobStatus status) {
        var state = new PdmJobState(modelId, modelType, deviceId, status, false, 0, Instant.now(), null, null, null);
        save(state);
        return state;
    }

    public PdmJobState get(String modelId) {
        Map<String, String> hash = hashes.hgetall(jobKey(modelId));
        if (hash == null || hash.isEmpty()) {
            return null;
        }
        return fromHash(modelId, hash);
    }

    public PdmJobState updateStatus(String modelId, PdmJobStatus status) {
        PdmJobState current = get(modelId);
        if (current == null) {
            current = new PdmJobState(modelId, inferModelType(modelId), null, status, status == PdmJobStatus.PAUSED, 0, Instant.now(), null, null, null);
        } else {
            current = new PdmJobState(
                    current.modelId(),
                    current.modelType(),
                    current.deviceId(),
                    status,
                    status == PdmJobStatus.PAUSED || current.paused() && status != PdmJobStatus.RUNNING,
                    current.iterations(),
                    current.startTime(),
                    Instant.now(),
                    current.trainingProgress(),
                    current.trainingStep());
        }
        save(current);
        return current;
    }

    public PdmJobState setPaused(String modelId, boolean paused) {
        PdmJobState current = get(modelId);
        PdmJobStatus status = paused ? PdmJobStatus.PAUSED : PdmJobStatus.RUNNING;
        if (current == null) {
            current = new PdmJobState(modelId, inferModelType(modelId), null, status, paused, 0, Instant.now(), Instant.now(), null, null);
        } else {
            current = new PdmJobState(
                    current.modelId(),
                    current.modelType(),
                    current.deviceId(),
                    status,
                    paused,
                    current.iterations(),
                    current.startTime(),
                    Instant.now(),
                    current.trainingProgress(),
                    current.trainingStep());
        }
        save(current);
        return current;
    }

    public void appendLog(String modelId, GenericLogEntry entry) {
        try {
            lists.rpush(logKey(modelId), mapper.writeValueAsString(entry));
            lists.ltrim(logKey(modelId), -MAX_LOG_ENTRIES, -1);
            keys.expire(logKey(modelId), LOG_TTL);
        } catch (Exception e) {
            throw new IllegalStateException("Failed to append PdM log entry", e);
        }
    }

    public PdmJobState updateTrainingProgress(String modelId, String step, Integer percent, PdmJobStatus status) {
        PdmJobState current = get(modelId);
        if (current == null) {
            current = new PdmJobState(modelId, inferModelType(modelId), null, status, false, 0, Instant.now(), Instant.now(), percent, step);
        } else {
            current = new PdmJobState(
                    current.modelId(),
                    current.modelType(),
                    current.deviceId(),
                    status,
                    current.paused(),
                    current.iterations(),
                    current.startTime(),
                    Instant.now(),
                    percent,
                    step);
        }
        save(current);
        return current;
    }

    public List<Map<String, Object>> logs(String modelId, int limit) {
        int cappedLimit = Math.max(1, Math.min(limit, MAX_LOG_ENTRIES));
        return lists.lrange(logKey(modelId), -cappedLimit, -1).stream()
                .map(this::readLog)
                .toList();
    }

    public void appendPrediction(String modelId, Map<String, Object> prediction) {
        try {
            lists.rpush(predictionKey(modelId), mapper.writeValueAsString(prediction));
            lists.ltrim(predictionKey(modelId), -MAX_PREDICTION_ENTRIES, -1);
            keys.expire(predictionKey(modelId), LOG_TTL);
        } catch (Exception e) {
            throw new IllegalStateException("Failed to append PdM prediction entry", e);
        }
    }

    public List<Map<String, Object>> predictions(String modelId, Long startTs, Long endTs, int limit) {
        int cappedLimit = Math.max(1, Math.min(limit, MAX_PREDICTION_ENTRIES));
        List<Map<String, Object>> matching = lists.lrange(predictionKey(modelId), -MAX_PREDICTION_ENTRIES, -1).stream()
                .map(this::readLog)
                .filter(prediction -> withinWindow(prediction, startTs, endTs))
                .toList();
        return matching.stream()
                .skip(Math.max(0, matching.size() - cappedLimit))
                .toList();
    }

    public List<String> scanJobKeys(String pattern) {
        List<String> result = new ArrayList<>();
        var cursor = keys.scan(new KeyScanArgs().match(pattern));
        while (cursor.hasNext()) {
            result.addAll(cursor.next());
        }
        return result;
    }

    public void save(PdmJobState state) {
        hashes.hset(jobKey(state.modelId()), toHash(state));
    }

    private Map<String, String> toHash(PdmJobState state) {
        var hash = new LinkedHashMap<String, String>();
        hash.put("status", state.status().name());
        hash.put("paused", state.paused() ? "1" : "0");
        hash.put("iterations", Integer.toString(state.iterations()));
        hash.put("model_type", nullToEmpty(state.modelType()));
        hash.put("device_id", nullToEmpty(state.deviceId()));
        if (state.startTime() != null) {
            hash.put("start_time", state.startTime().toString());
        }
        if (state.lastRun() != null) {
            hash.put("last_run", state.lastRun().toString());
        }
        if (state.trainingProgress() != null) {
            hash.put("training_progress", Integer.toString(state.trainingProgress()));
        }
        hash.put("training_step", nullToEmpty(state.trainingStep()));
        return hash;
    }

    private PdmJobState fromHash(String modelId, Map<String, String> hash) {
        return new PdmJobState(
                modelId,
                emptyToNull(hash.get("model_type")),
                emptyToNull(hash.get("device_id")),
                status(hash.get("status")),
                "1".equals(hash.get("paused")),
                parseInt(hash.get("iterations")),
                instant(hash.get("start_time")),
                instant(hash.get("last_run")),
                parseInteger(hash.get("training_progress")),
                emptyToNull(hash.get("training_step")));
    }

    private Map<String, Object> readLog(String value) {
        try {
            return mapper.readValue(value, Map.class);
        } catch (Exception e) {
            return Map.of("level", "error", "source", "Quarkus", "message", value, "timestamp", Instant.now().toString());
        }
    }

    private boolean withinWindow(Map<String, Object> value, Long startTs, Long endTs) {
        long timestamp = timestamp(value.get("timestamp"));
        return (startTs == null || timestamp >= startTs) && (endTs == null || timestamp <= endTs);
    }

    private long timestamp(Object value) {
        if (value instanceof Number number) {
            return number.longValue();
        }
        if (value instanceof String text) {
            try {
                return Long.parseLong(text);
            } catch (NumberFormatException ignored) {
                try {
                    return Instant.parse(text).toEpochMilli();
                } catch (Exception ignoredAgain) {
                    return 0;
                }
            }
        }
        return 0;
    }

    private PdmJobStatus status(String value) {
        if (value == null || value.isBlank()) {
            return PdmJobStatus.INITIALIZED;
        }
        return PdmJobStatus.valueOf(value.toUpperCase());
    }

    private Instant instant(String value) {
        return value == null || value.isBlank() ? null : Instant.parse(value);
    }

    private int parseInt(String value) {
        return value == null || value.isBlank() ? 0 : Integer.parseInt(value);
    }

    private Integer parseInteger(String value) {
        return value == null || value.isBlank() ? null : Integer.parseInt(value);
    }

    private String nullToEmpty(String value) {
        return value == null ? "" : value;
    }

    private String emptyToNull(String value) {
        return value == null || value.isBlank() ? null : value;
    }

    private String jobKey(String modelId) {
        return "job:" + modelId;
    }

    private String logKey(String modelId) {
        return "logs:" + modelId;
    }

    private String predictionKey(String modelId) {
        return "predictions:" + modelId;
    }

    private String inferModelType(String modelId) {
        return modelId != null && modelId.toLowerCase().contains("anomaly")
                ? "AnomalyPredictor"
                : "ForecastModel";
    }
}
