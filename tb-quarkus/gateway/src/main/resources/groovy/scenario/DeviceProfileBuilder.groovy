package groovy.scenario

class DeviceProfileBuilder {
    String name
    String type = 'DEFAULT'
    String label
    Map<String, Object> attributes = [:]
    TelemetryBuilder telemetry = new TelemetryBuilder()

    DeviceProfileBuilder name(String name) { this.name = name; return this }
    DeviceProfileBuilder type(String type) { this.type = type; return this }
    DeviceProfileBuilder label(String label) { this.label = label; return this }
    DeviceProfileBuilder attribute(String key, Object value) { attributes[key] = value; return this }
    DeviceProfileBuilder attributes(Map<String, Object> attrs) { attributes.putAll(attrs); return this }

    DeviceProfileBuilder telemetry(@DelegatesTo(TelemetryBuilder) Closure spec) {
        spec.delegate = telemetry
        spec.resolveStrategy = Closure.DELEGATE_FIRST
        spec()
        return this
    }

    DeviceProfileBuilder deriveFrom(DeviceProfileBuilder parent) {
        this.name = parent.name
        this.type = parent.type
        this.label = parent.label
        this.attributes = new LinkedHashMap<>(parent.attributes)
        this.telemetry = parent.telemetry.clone()
        return this
    }

    Map<String, Object> build() {
        [
            name      : name,
            type      : type,
            label     : label ?: name,
            attributes: attributes,
            telemetry : telemetry.build(),
        ]
    }

    static class TelemetryBuilder {
        String mode = 'stream'
        String source = 'random'
        String file
        int intervalMs = 5000
        boolean loop = false
        List<String> metrics = []
        Map<String, MetricRange> metricRanges = [:]

        TelemetryBuilder mode(String mode) { this.mode = mode; return this }
        TelemetryBuilder source(String source) { this.source = source; return this }
        TelemetryBuilder file(String file) { this.file = file; return this }
        TelemetryBuilder intervalMs(int intervalMs) { this.intervalMs = intervalMs; return this }
        TelemetryBuilder interval_ms(int intervalMs) { this.intervalMs = intervalMs; return this }
        TelemetryBuilder loop(boolean loop) { this.loop = loop; return this }
        TelemetryBuilder metrics(String... names) { this.metrics.addAll(names); return this }
        TelemetryBuilder metrics(List<String> names) { this.metrics.addAll(names); return this }

        TelemetryBuilder metric(String name, @DelegatesTo(MetricRange) Closure spec) {
            def range = new MetricRange()
            spec.delegate = range
            spec.resolveStrategy = Closure.DELEGATE_FIRST
            spec()
            metricRanges[name] = range
            if (!metrics.contains(name)) metrics.add(name)
            return this
        }

        TelemetryBuilder clone() {
            def c = new TelemetryBuilder()
            c.mode = this.mode
            c.source = this.source
            c.file = this.file
            c.intervalMs = this.intervalMs
            c.loop = this.loop
            c.metrics = new ArrayList<>(this.metrics)
            c.metricRanges = new LinkedHashMap<>(this.metricRanges)
            return c
        }

        Map<String, Object> build() {
            if (!metrics) return null
            def m = [
                mode       : mode,
                source     : source,
                interval_ms: intervalMs,
                loop       : loop,
            ]
            if (file) m.file = file
            if (metrics) m.metrics = metrics
            if (metricRanges) m.metric_ranges = metricRanges.collectEntries { k, v -> [k, v.build()] }
            return m
        }

        static class MetricRange {
            double min = 0
            double max = 100

            MetricRange min(double min) { this.min = min; return this }
            MetricRange max(double max) { this.max = max; return this }

            Map<String, Object> build() { [min: min, max: max] }
        }
    }
}
