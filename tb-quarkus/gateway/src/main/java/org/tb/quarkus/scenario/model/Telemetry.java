package org.tb.quarkus.scenario.model;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class Telemetry {
    private String mode;
    private String source;
    private String file;
    private int intervalMs = 5000;
    private boolean loop;
    private final List<String> metrics = new ArrayList<>();
    private final Map<String, MetricRange> metricRanges = new LinkedHashMap<>();

    public String getMode() {
        return mode;
    }

    public void setMode(String mode) {
        this.mode = mode;
    }

    public String getSource() {
        return source;
    }

    public void setSource(String source) {
        this.source = source;
    }

    public String getFile() {
        return file;
    }

    public void setFile(String file) {
        this.file = file;
    }

    public int getIntervalMs() {
        return intervalMs;
    }

    public void setIntervalMs(int intervalMs) {
        this.intervalMs = intervalMs;
    }

    public boolean isLoop() {
        return loop;
    }

    public void setLoop(boolean loop) {
        this.loop = loop;
    }

    public List<String> getMetrics() {
        return metrics;
    }

    public Map<String, MetricRange> getMetricRanges() {
        return metricRanges;
    }

    public static class MetricRange {
        private double min;
        private double max;

        public double getMin() {
            return min;
        }

        public void setMin(double min) {
            this.min = min;
        }

        public double getMax() {
            return max;
        }

        public void setMax(double max) {
            this.max = max;
        }
    }
}
