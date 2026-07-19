package org.tb.quarkus.scenario;

import io.quarkus.logging.Log;
import jakarta.enterprise.context.ApplicationScoped;
import org.tb.quarkus.scenario.model.Asset;
import org.tb.quarkus.scenario.model.Device;
import org.tb.quarkus.scenario.model.Scenario;
import org.tb.quarkus.scenario.model.Telemetry;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

@ApplicationScoped
public class ScenarioExporter {

    public List<Path> export(Scenario scenario, String basePath) throws IOException {
        Path dir = Path.of(basePath, scenario.getName());
        Files.createDirectories(dir);

        List<Path> written = new ArrayList<>();

        // Group devices by profile name
        Map<String, List<Device>> devicesByProfile = groupDevices(scenario.getDevices());
        Path devicesDir = dir.resolve("devices");
        Files.createDirectories(devicesDir);
        for (Map.Entry<String, List<Device>> entry : devicesByProfile.entrySet()) {
            Path file = devicesDir.resolve(sanitizeFileName(entry.getKey()) + ".groovy");
            Files.writeString(file, generateDeviceGroupGroovy(entry.getKey(), entry.getValue()));
            written.add(file);
            Log.infof("Exported %d devices with profile '%s' to %s", entry.getValue().size(), entry.getKey(), file);
        }

        // Group assets by type
        Map<String, List<Asset>> assetsByType = groupAssets(scenario.getAssets());
        Path assetsDir = dir.resolve("assets");
        Files.createDirectories(assetsDir);
        for (Map.Entry<String, List<Asset>> entry : assetsByType.entrySet()) {
            Path file = assetsDir.resolve(sanitizeFileName(entry.getKey()) + ".groovy");
            Files.writeString(file, generateAssetGroupGroovy(entry.getKey(), entry.getValue()));
            written.add(file);
            Log.infof("Exported %d assets with type '%s' to %s", entry.getValue().size(), entry.getKey(), file);
        }

        // Write main scenario file
        Path mainFile = dir.resolve(scenario.getName() + ".groovy");
        Files.writeString(mainFile, generateMainGroovy(scenario, devicesByProfile.keySet(), assetsByType.keySet()));
        written.add(mainFile);
        Log.infof("Exported main scenario to %s", mainFile);

        return written;
    }

    private Map<String, List<Device>> groupDevices(List<Device> devices) {
        Map<String, List<Device>> groups = new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
        for (Device device : devices) {
            String profile = device.getDeviceProfileName();
            if (profile == null || profile.isBlank()) {
                profile = device.getType();
            }
            if (profile == null || profile.isBlank()) {
                profile = "default";
            }
            groups.computeIfAbsent(profile, k -> new ArrayList<>()).add(device);
        }
        return groups;
    }

    private Map<String, List<Asset>> groupAssets(List<Asset> assets) {
        Map<String, List<Asset>> groups = new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
        for (Asset asset : assets) {
            String type = asset.getType();
            if (type == null || type.isBlank()) {
                type = "default";
            }
            groups.computeIfAbsent(type, k -> new ArrayList<>()).add(asset);
        }
        return groups;
    }

    private String generateMainGroovy(Scenario scenario, java.util.Set<String> deviceProfiles, java.util.Set<String> assetTypes) {
        StringBuilder sb = new StringBuilder();
        sb.append("import groovy.lang.GroovyShell\n\n");

        sb.append("// ── Scenario metadata ─────────────────────────────────────────\n");
        sb.append("def scenario = [\n");
        sb.append("    name       : '").append(esc(scenario.getName())).append("',\n");
        sb.append("    description: '").append(esc(scenario.getDescription())).append("',\n");
        sb.append("    version    : ").append(scenario.getVersion()).append(",\n");
        sb.append("]\n\n");

        sb.append("// ── Device groups (by profile) ─────────────────────────────────\n");
        sb.append("def devices = []\n");
        sb.append("def shell = new GroovyShell()\n\n");

        for (String profile : deviceProfiles) {
            String file = "devices/" + sanitizeFileName(profile) + ".groovy";
            sb.append("new File(scenarioDir, '").append(file).append("').with { if (exists()) devices.addAll(shell.evaluate(it)) }\n");
        }
        sb.append("\n");

        sb.append("// ── Asset groups (by type) ──────────────────────────────────────\n");
        sb.append("def assets = []\n\n");

        for (String type : assetTypes) {
            String file = "assets/" + sanitizeFileName(type) + ".groovy";
            sb.append("new File(scenarioDir, '").append(file).append("').with { if (exists()) assets.addAll(shell.evaluate(it)) }\n");
        }
        sb.append("\n");

        sb.append("return [scenario: scenario, devices: devices, assets: assets]\n");
        return sb.toString();
    }

    private String generateDeviceGroupGroovy(String profile, List<Device> devices) {
        StringBuilder sb = new StringBuilder();
        sb.append("import groovy.scenario.DeviceProfileBuilder\n\n");
        sb.append("// Devices with profile: ").append(profile).append(" (").append(devices.size()).append(" devices)\n");
        sb.append("return [\n");

        for (Device device : devices) {
            sb.append("    new DeviceProfileBuilder()\n");
            sb.append("        .type('").append(esc(device.getType())).append("')\n");
            if (device.getLabel() != null && !"null".equals(device.getLabel())) {
                sb.append("        .label('").append(esc(device.getLabel())).append("')\n");
            }
            sb.append("        .with {\n");
            sb.append("            name = '").append(esc(device.getName())).append("'\n");

            if (device.getRelations() != null && !device.getRelations().isEmpty()) {
                for (Device.Relation rel : device.getRelations()) {
                    sb.append("            // relation: ").append(rel.getEntityType())
                            .append(" '").append(rel.getEntityName()).append("' [")
                            .append(rel.getType()).append("]\n");
                }
            }

            Telemetry tel = device.getTelemetry();
            if (tel != null) {
                sb.append("            telemetry {\n");
                sb.append("                source('").append(tel.getSource()).append("')\n");
                if (tel.getFile() != null) {
                    sb.append("                file('").append(tel.getFile()).append("')\n");
                }
                sb.append("                intervalMs(").append(tel.getIntervalMs()).append(")\n");
                if (tel.isLoop()) {
                    sb.append("                loop(true)\n");
                }
                for (String metric : tel.getMetrics()) {
                    Telemetry.MetricRange range = tel.getMetricRanges().get(metric);
                    if (range != null) {
                        sb.append("                metric('").append(metric).append("') { min(")
                                .append(range.getMin()).append("); max(")
                                .append(range.getMax()).append(") }\n");
                    } else {
                        sb.append("                metrics('").append(metric).append("')\n");
                    }
                }
                sb.append("            }\n");
            } else {
                sb.append("            // TODO: add telemetry config\n");
            }

            sb.append("            build()\n");
            sb.append("        },\n");
        }

        sb.append("]\n");
        return sb.toString();
    }

    private String generateAssetGroupGroovy(String type, List<Asset> assets) {
        StringBuilder sb = new StringBuilder();
        sb.append("import groovy.scenario.AssetProfileBuilder\n\n");
        sb.append("// Assets with type: ").append(type).append(" (").append(assets.size()).append(" assets)\n");
        sb.append("return [\n");

        for (Asset asset : assets) {
            sb.append("    new AssetProfileBuilder()\n");
            sb.append("        .type('").append(esc(asset.getType())).append("')\n");
            if (asset.getLabel() != null && !"null".equals(asset.getLabel())) {
                sb.append("        .label('").append(esc(asset.getLabel())).append("')\n");
            }
            sb.append("        .with {\n");
            sb.append("            name = '").append(esc(asset.getName())).append("'\n");

            if (asset.getRelations() != null && !asset.getRelations().isEmpty()) {
                for (Device.Relation rel : asset.getRelations()) {
                    sb.append("            relation('").append(esc(rel.getEntityType()))
                            .append("', '").append(esc(rel.getEntityName()))
                            .append("', '").append(esc(rel.getType())).append("')\n");
                }
            }

            sb.append("            build()\n");
            sb.append("        },\n");
        }

        sb.append("]\n");
        return sb.toString();
    }

    private String sanitizeFileName(String name) {
        return name.replaceAll("[^a-zA-Z0-9_\\-]", "_").toLowerCase();
    }

    private String esc(String s) {
        if (s == null) return "";
        return s.replace("'", "\\'");
    }
}
