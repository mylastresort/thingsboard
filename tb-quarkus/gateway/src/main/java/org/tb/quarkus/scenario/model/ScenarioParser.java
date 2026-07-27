package org.tb.quarkus.scenario.model;

import groovy.lang.Binding;
import groovy.lang.GroovyShell;
import io.quarkus.logging.Log;
import jakarta.enterprise.context.ApplicationScoped;
import org.codehaus.groovy.control.CompilerConfiguration;

import java.io.File;
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;

@ApplicationScoped
public class ScenarioParser {

    public Scenario parse(File file) throws IOException {
        String name = file.getName().toLowerCase();
        if (!name.endsWith(".groovy")) {
            throw new IOException("Only .groovy scenarios are supported: " + file);
        }
        return parseGroovy(file);
    }

    public Scenario parseGroovy(String groovyContent) throws IOException {
        try {
            GroovyShell shell = createGroovyShell(null);
            Object result = shell.evaluate(groovyContent);
            if (result instanceof Map) {
                @SuppressWarnings("unchecked")
                Map<String, Object> map = (Map<String, Object>) result;
                return buildScenarioFromGroovyResult(map);
            }
            throw new IOException("Groovy script must return a Map with 'scenario' and 'devices' keys");
        } catch (IOException e) {
            throw e;
        } catch (Exception e) {
            throw new IOException("Failed to evaluate Groovy content", e);
        }
    }

    @SuppressWarnings("unchecked")
    private Scenario parseGroovy(File file) throws IOException {
        try {
            File scenarioDir = file.getAbsoluteFile().getParentFile();
            Binding binding = new Binding();
            binding.setVariable("scenarioDir", scenarioDir);
            GroovyShell shell = createGroovyShell(scenarioDir, binding);
            Object result = shell.evaluate(file);
            if (result instanceof Map) {
                Map<String, Object> map = (Map<String, Object>) result;
                return buildScenarioFromGroovyResult(map);
            }
            throw new IOException("Groovy script must return a Map with 'scenario' and 'devices' keys");
        } catch (IOException e) {
            throw e;
        } catch (Exception e) {
            throw new IOException("Failed to evaluate Groovy file: " + file, e);
        }
    }

    private GroovyShell createGroovyShell(File scenarioDir) {
        return createGroovyShell(scenarioDir, new Binding());
    }

    private GroovyShell createGroovyShell(File scenarioDir, Binding binding) {
        CompilerConfiguration config = new CompilerConfiguration();
        config.setSourceEncoding("UTF-8");

        var classpath = new LinkedHashSet<URL>();
        try {
            classpath.add(new File(".").toURI().toURL());
        } catch (Exception ignored) {
        }

        if (scenarioDir != null && scenarioDir.exists()) {
            try {
                classpath.add(scenarioDir.toURI().toURL());
            } catch (Exception ignored) {
            }
        }

        ClassLoader parent = new URLClassLoader(classpath.toArray(new URL[0]), getClass().getClassLoader());
        return new GroovyShell(parent, binding, config);
    }

    @SuppressWarnings("unchecked")
    private Scenario buildScenarioFromGroovyResult(Map<String, Object> result) {
        Scenario scenario = new Scenario();

        Object scenarioObj = result.get("scenario");
        if (scenarioObj instanceof Map) {
            Map<String, Object> scenarioMap = (Map<String, Object>) scenarioObj;
            scenario.setName(getString(scenarioMap, "name"));
            scenario.setDescription(getString(scenarioMap, "description"));
            scenario.setVersion(getInt(scenarioMap, "version", 1));
        }

        Object devicesObj = result.get("devices");
        if (devicesObj instanceof List) {
            for (Object deviceObj : (List<?>) devicesObj) {
                if (deviceObj instanceof Map) {
                    Map<String, Object> deviceMap = (Map<String, Object>) deviceObj;
                    scenario.getDevices().add(parseDeviceFromMap(deviceMap));
                }
            }
        }

        Object assetsObj = result.get("assets");
        if (assetsObj instanceof List) {
            for (Object assetObj : (List<?>) assetsObj) {
                if (assetObj instanceof Map) {
                    Map<String, Object> assetMap = (Map<String, Object>) assetObj;
                    scenario.getAssets().add(parseAssetFromMap(assetMap));
                }
            }
        }

        Log.infof("Parsed Groovy scenario '%s' with %d devices, %d assets",
                scenario.getName(), scenario.getDevices().size(), scenario.getAssets().size());
        return scenario;
    }

    private Device parseDeviceFromMap(Map<String, Object> map) {
        Device device = new Device();
        device.setName(getString(map, "name"));
        device.setType(getString(map, "type"));
        device.setLabel(getString(map, "label"));

        Object attrs = map.get("attributes");
        if (attrs instanceof Map) {
            device.getAttributes().putAll((Map<String, Object>) attrs);
        }

        Object telemetryObj = map.get("telemetry");
        if (telemetryObj instanceof Map) {
            device.setTelemetry(parseTelemetryFromMap((Map<String, Object>) telemetryObj));
        }

        return device;
    }

    @SuppressWarnings("unchecked")
    private Asset parseAssetFromMap(Map<String, Object> map) {
        Asset asset = new Asset();
        asset.setName(getString(map, "name"));
        asset.setType(getString(map, "type"));
        asset.setLabel(getString(map, "label"));

        Object relationsObj = map.get("relations");
        if (relationsObj instanceof List) {
            for (Object relObj : (List<?>) relationsObj) {
                if (relObj instanceof Map) {
                    Map<String, Object> relMap = (Map<String, Object>) relObj;
                    asset.addRelation(new Device.Relation(
                            getString(relMap, "entityType"),
                            "",
                            getString(relMap, "entityName"),
                            getString(relMap, "type")));
                }
            }
        }

        return asset;
    }

    private Telemetry parseTelemetryFromMap(Map<String, Object> map) {
        Telemetry tel = new Telemetry();
        tel.setMode(getString(map, "mode"));
        tel.setSource(getString(map, "source"));
        tel.setFile(getString(map, "file"));
        tel.setIntervalMs(getInt(map, "interval_ms", 5000));
        tel.setLoop(getBool(map, "loop", false));

        Object metricsObj = map.get("metrics");
        if (metricsObj instanceof List) {
            for (Object m : (List<?>) metricsObj) {
                tel.getMetrics().add(String.valueOf(m));
            }
        }

        Object metricRangesObj = map.get("metric_ranges");
        if (metricRangesObj instanceof Map) {
            for (Map.Entry<String, Object> entry : ((Map<String, Object>) metricRangesObj).entrySet()) {
                if (entry.getValue() instanceof Map) {
                    Map<String, Object> rangeDef = (Map<String, Object>) entry.getValue();
                    Telemetry.MetricRange range = new Telemetry.MetricRange();
                    range.setMin(getDouble(rangeDef, "min", 0));
                    range.setMax(getDouble(rangeDef, "max", 0));
                    tel.getMetricRanges().put(entry.getKey(), range);
                    if (!tel.getMetrics().contains(entry.getKey())) {
                        tel.getMetrics().add(entry.getKey());
                    }
                }
            }
        }

        return tel;
    }

    private String getString(Map<String, Object> map, String key) {
        Object val = map.get(key);
        return val != null ? String.valueOf(val) : null;
    }

    private int getInt(Map<String, Object> map, String key, int defaultVal) {
        Object val = map.get(key);
        if (val instanceof Number) {
            return ((Number) val).intValue();
        }
        return defaultVal;
    }

    private double getDouble(Map<String, Object> map, String key, double defaultVal) {
        Object val = map.get(key);
        if (val instanceof Number) {
            return ((Number) val).doubleValue();
        }
        return defaultVal;
    }

    private boolean getBool(Map<String, Object> map, String key, boolean defaultVal) {
        Object val = map.get(key);
        if (val instanceof Boolean) {
            return (Boolean) val;
        }
        return defaultVal;
    }
}
