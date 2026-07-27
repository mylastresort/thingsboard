package org.tb.quarkus.scenario;

import io.quarkus.logging.Log;
import io.quarkus.runtime.StartupEvent;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.Observes;
import jakarta.inject.Inject;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import org.tb.quarkus.scenario.model.Asset;
import org.tb.quarkus.scenario.model.Device;
import org.tb.quarkus.scenario.model.Scenario;
import org.tb.quarkus.scenario.model.ScenarioParser;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

@ApplicationScoped
public class ScenarioEngine {

    private static final String DEFAULT_SCENARIO_PATH = "/scenarios";

    @Inject
    ScenarioDiscoveryService discoveryService;

    @Inject
    ScenarioContextService contextService;

    @Inject
    MqttTelemetryService mqttService;

    @Inject
    ScenarioParser parser;

    @Inject
    ScenarioExporter exporter;

    @ConfigProperty(name = "scenario.run-on-startup", defaultValue = "true")
    boolean runOnStartup;

    @ConfigProperty(name = "scenario.path", defaultValue = DEFAULT_SCENARIO_PATH)
    String scenarioPath;

    void onStartup(@Observes StartupEvent event) {
        if (!runOnStartup) {
            Log.info("Scenario auto-execution disabled");
            return;
        }

        try {
            contextService.ensureTenant();
            Scenario scenario = loadOrCreate();
            execute(scenario);
        } catch (Exception e) {
            Log.errorf(e, "Failed to discover and execute scenario");
        }
    }

    private Scenario loadOrCreate() throws Exception {
        // Check for any existing scenario file in the scenarios directory
        Path basePath = Path.of(scenarioPath);
        if (Files.isDirectory(basePath)) {
            try (var dirs = java.nio.file.Files.list(basePath)) {
                for (Path dir : (Iterable<Path>) dirs.filter(Files::isDirectory)::iterator) {
                    String name = dir.getFileName().toString();
                    Path groovyFile = dir.resolve(name + ".groovy");
                    if (Files.exists(groovyFile)) {
                        Log.infof("Loading scenario from file: %s", groovyFile);
                        return parser.parse(groovyFile.toFile());
                    }
                }
            }
        }

        Log.info("No scenario file found, discovering from ThingsBoard...");
        Scenario scenario = discoveryService.discover();

        java.util.List<Path> exported = exporter.export(scenario, scenarioPath);
        Log.infof("Scenario exported to %d files under %s — edit to customize telemetry",
                exported.size(), Path.of(scenarioPath, scenario.getName()));

        return scenario;
    }

    public void execute(Scenario scenario) throws Exception {
        Log.infof("Executing scenario: %s (version %d) — %d devices, %d assets",
                scenario.getName(), scenario.getVersion(),
                scenario.getDevices().size(), scenario.getAssets().size());

        List<ScenarioContextService.DeviceContext> deviceContexts = new ArrayList<>();
        List<ScenarioContextService.AssetContext> assetContexts = new ArrayList<>();

        for (Asset asset : scenario.getAssets()) {
            try {
                ScenarioContextService.AssetContext ctx = contextService.createAssetContext(asset);
                if (ctx == null) {
                    continue;
                }
                assetContexts.add(ctx);
                Log.infof("Asset '%s' ready (id=%s, created=%s)",
                        asset.getName(), ctx.assetId(), ctx.created());
            } catch (Exception e) {
                Log.errorf(e, "Failed to set up asset '%s'", asset.getName());
            }
        }

        for (Device device : scenario.getDevices()) {
            try {
                ScenarioContextService.DeviceContext ctx = contextService.createDeviceContext(device);
                if (ctx == null) {
                    continue;
                }
                deviceContexts.add(ctx);
                Log.infof("Device '%s' ready (id=%s, created=%s)",
                        device.getName(), ctx.deviceId(), ctx.created());

                if (device.getTelemetry() != null && "stream".equals(device.getTelemetry().getMode())) {
                    mqttService.startStreaming(device, ctx);
                }
            } catch (Exception e) {
                Log.errorf(e, "Failed to set up device '%s'", device.getName());
            }
        }

        Log.infof("Scenario '%s' executed: %d devices, %d assets processed",
                scenario.getName(), deviceContexts.size(), assetContexts.size());
    }

    public void stopAll() {
        mqttService.stopAll();
    }
}
