package org.tb.quarkus.service;

import io.quarkus.redis.datasource.RedisDataSource;
import io.quarkus.redis.datasource.keys.KeyCommands;
import io.quarkus.redis.datasource.keys.KeyScanArgs;
import io.quarkus.runtime.StartupEvent;
import io.quarkus.scheduler.Scheduled;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.Observes;
import jakarta.inject.Inject;
import org.jboss.logging.Logger;
import org.tb.quarkus.pdm.PdmJobStatus;
import org.tb.quarkus.pdm.PdmModelType;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

@ApplicationScoped
public class PdmStartupRecovery {

    private static final Logger LOG = Logger.getLogger(PdmStartupRecovery.class);

    @Inject RedisDataSource redis;
    @Inject PdmCommandService commandService;

    private final AtomicBoolean running = new AtomicBoolean(false);

    void onStartup(@Observes StartupEvent event) {
        recoverStaleJobs();
    }

    @Scheduled(every = "30s", concurrentExecution = Scheduled.ConcurrentExecution.SKIP)
    void periodicRecovery() {
        recoverStaleJobs();
    }

    private void recoverStaleJobs() {
        if (!running.compareAndSet(false, true)) {
            LOG.debug("PdM recovery already in progress, skipping");
            return;
        }
        try {
            doRecover();
        } catch (Exception e) {
            LOG.errorf(e, "PdM recovery failed");
        } finally {
            running.set(false);
        }
    }

    private void doRecover() {
        KeyCommands<String> keys = redis.key();
        List<String> jobKeys = new ArrayList<>();
        var cursor = keys.scan(new KeyScanArgs().match("job:*"));
        while (cursor.hasNext()) {
            jobKeys.addAll(cursor.next());
        }

        if (jobKeys.isEmpty()) {
            return;
        }

        int reissued = 0;
        for (String key : jobKeys) {
            try {
                if (recoverJob(key)) {
                    reissued++;
                }
            } catch (Exception e) {
                LOG.warnf(e, "PdM recovery: failed to recover job %s", key);
            }
        }

        if (reissued > 0) {
            LOG.infof("PdM recovery: re-issued INFER for %d/%d RUNNING jobs", reissued, jobKeys.size());
        }
    }

    private boolean recoverJob(String key) {
        var hashes = redis.hash(String.class);
        var hash = hashes.hgetall(key);
        if (hash == null || hash.isEmpty()) {
            return false;
        }

        String statusStr = hash.get("status");
        if (statusStr == null) {
            return false;
        }

        PdmJobStatus status;
        try {
            status = PdmJobStatus.valueOf(statusStr.toUpperCase());
        } catch (IllegalArgumentException e) {
            return false;
        }

        if (status != PdmJobStatus.RUNNING) {
            return false;
        }

        String modelId = key.substring("job:".length());
        String forecastId = extractForecastId(modelId);
        if (forecastId == null) {
            LOG.warnf("PdM recovery: cannot extract forecastId from modelId=%s", modelId);
            return false;
        }

        String modelType = hash.getOrDefault("model_type", "");
        String deviceId = hash.getOrDefault("device_id", null);

        LOG.infof("PdM recovery: re-issuing INFER for modelId=%s forecastId=%s modelType=%s",
                modelId, forecastId, modelType);

        commandService.reissueInfer(forecastId, resolveModelType(modelType),
                deviceId != null && !deviceId.isBlank() ? deviceId : null);

        return true;
    }

    private String extractForecastId(String modelId) {
        if (modelId == null) {
            return null;
        }
        int slash = modelId.lastIndexOf('/');
        return slash > 0 ? modelId.substring(0, slash) : modelId;
    }

    private PdmModelType resolveModelType(String storedType) {
        if (storedType == null || storedType.isBlank()) {
            return PdmModelType.BOTH;
        }
        if (storedType.contains("Anomaly")) {
            return PdmModelType.ANOMALY;
        }
        if (storedType.contains("Forecast")) {
            return PdmModelType.FORECAST;
        }
        return PdmModelType.BOTH;
    }
}
