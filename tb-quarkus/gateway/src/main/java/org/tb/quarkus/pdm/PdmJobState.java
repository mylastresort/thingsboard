package org.tb.quarkus.pdm;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

public record PdmJobState(
        String modelId,
        String modelType,
        String deviceId,
        PdmJobStatus status,
        boolean paused,
        int iterations,
        Instant startTime,
        Instant lastRun,
        Integer trainingProgress,
        String trainingStep) {

    public Map<String, Object> toResponse() {
        var value = new LinkedHashMap<String, Object>();
        value.put("model_id", modelId);
        value.put("model_type", modelType);
        value.put("device_id", deviceId);
        value.put("status", status == null ? null : status.name().toLowerCase());
        value.put("paused", paused);
        value.put("iterations", iterations);
        value.put("start_time", startTime == null ? null : startTime.toString());
        value.put("last_run", lastRun == null ? null : lastRun.toString());
        value.put("trainingProgress", trainingProgress);
        value.put("trainingStep", trainingStep);
        return value;
    }
}
