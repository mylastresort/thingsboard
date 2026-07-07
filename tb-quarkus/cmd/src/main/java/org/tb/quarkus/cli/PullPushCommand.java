package org.tb.quarkus.cli;

import io.quarkus.logging.Log;
import jakarta.inject.Inject;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import picocli.CommandLine;
import org.tb.quarkus.hf.HfDatasetClient;
import org.tb.quarkus.hf.Scenario;
import org.tb.quarkus.gateway.AgenticBenchmarkPushClient;
import org.tb.quarkus.tb.TbGateway;
import org.tb.quarkus.tb.TbScenarioStore;
import org.tb.quarkus.tb.TbSessionLedger;
import org.tb.quarkus.tb.TbTopologyBuilder;

import java.util.*;
import java.util.concurrent.Callable;
import org.tb.quarkus.model.AssetClassSensors;
import java.util.stream.Collectors;

@CommandLine.Command(
        name = "pull-push",
        mixinStandardHelpOptions = true,
        description = "Pull AssetOpsBench scenarios from HuggingFace and push topology + scenario data into ThingsBoard. " +
                "By default, sweeps every (config, split) pair the dataset exposes; pass --config/--split to restrict to one."
)
public class PullPushCommand implements Callable<Integer> {

    @Inject HfDatasetClient hf;
    @Inject TbGateway tb;
    @Inject TbTopologyBuilder topologyBuilder;
    @Inject TbScenarioStore scenarioStore;
    @Inject TbSessionLedger ledger;
    @Inject AgenticBenchmarkPushClient benchmarkPushClient;

    @ConfigProperty(name = "agents.tb.asset-class-filter", defaultValue = "")
    String assetClassFilterCsv;

    // Defaults used only as fallbacks when the person supplies just one of --config/--split.
    @ConfigProperty(name = "agents.hf.config")
    String defaultConfig;

    @ConfigProperty(name = "agents.hf.split")
    String defaultSplit;

    @CommandLine.Option(names = "--config", description = "Restrict to a single HF dataset config (default: sweep all configs)")
    String configOverride;

    @CommandLine.Option(names = "--split", description = "Restrict to a single HF dataset split (default: property agents.hf.split)")
    String splitOverride;

    @CommandLine.Option(names = "--list-configs", description = "List available (config, split) pairs for the dataset and exit")
    boolean listConfigs;

    @CommandLine.Option(names = "--topology-only", description = "Push asset/sensor topology only, skip scenario attribute upload")
    boolean topologyOnly;

    @CommandLine.Option(names = "--scenarios-only", description = "Push scenario attributes only, skip asset/sensor topology")
    boolean scenariosOnly;

    @CommandLine.Option(names = "--skip-agentic-benchmark",
            description = "Do not push pulled AssetOpsBench rows to tb-quarkus agentic benchmark endpoints")
    boolean skipAgenticBenchmark;

    @CommandLine.Option(names = "--dry-run", description = "Pull and parse scenarios, print a summary, push nothing to ThingsBoard")
    boolean dryRun;

    @CommandLine.Option(names = "--no-rollback",
            description = "On failure, leave whatever was already pushed in place instead of rolling it back")
    boolean noRollback;

    @Override
    public Integer call() {
        try {
            if (listConfigs) {
                hf.fetchAvailableConfigs().forEach(pair ->
                        System.out.println("config=" + pair[0] + "  split=" + pair[1]));
                return 0;
            }

            Map<String, List<Scenario>> bySubset = resolveSubsets();

            int totalRows = bySubset.values().stream().mapToInt(List::size).sum();
            bySubset.forEach((key, rows) -> Log.infof("Subset %s: %d rows", key, rows.size()));
            Log.infof("Pulled %d subset(s), %d row(s) total", bySubset.size(), totalRows);

            List<Scenario> allScenarios = bySubset.values().stream()
                    .flatMap(List::stream).collect(Collectors.toList());
            printSummary(allScenarios);

            if (dryRun) {
                printDryRunPlan(bySubset, allScenarios);
                Log.info("--dry-run set: not pushing to tb-quarkus gateway or ThingsBoard");
                return 0;
            }

            if (!skipAgenticBenchmark) {
                int pushedRows = benchmarkPushClient.pushAll(bySubset);
                Log.infof("Pushed %d AssetOpsBench row(s) to tb-quarkus agentic benchmark gateway", pushedRows);
            }

            ledger.reset();

            try {
                tb.login();

                if (!scenariosOnly) {
                    // Called ONCE across the merged set so asset dedup (seenAssets) holds
                    // across configs - an asset named in both `scenarios` and `compressor`
                    // rows only gets created once.
                    Set<String> assetClassFilter = Arrays.stream(assetClassFilterCsv.split(","))
                            .map(String::trim).filter(s -> !s.isBlank()).collect(Collectors.toSet());
                    Set<String> pushed = topologyBuilder.buildFromScenarios(allScenarios, assetClassFilter);
                    Log.infof("Topology pushed for %d distinct assets: %s", pushed.size(), pushed);
                }

                if (!topologyOnly) {
                    // Pushed per-subset (not flattened) so TbScenarioStore can namespace
                    // attribute keys by subset - IDs are only guaranteed unique within a
                    // single HF config, not across all 6.
                    for (var entry : bySubset.entrySet()) {
                        scenarioStore.pushAll(entry.getKey(), entry.getValue());
                        Log.infof("Pushed %d scenario records for subset %s", entry.getValue().size(), entry.getKey());
                    }
                }
            } catch (Exception sessionFailure) {
                Log.errorf("Session failed after %d change(s): %s", ledger.size(), sessionFailure.getMessage());
                if (noRollback) {
                    Log.warn("--no-rollback set: leaving partial state in ThingsBoard for inspection.");
                } else {
                    int failedUndos = ledger.rollbackAll();
                    if (failedUndos > 0) {
                        Log.warn("Some steps could not be rolled back automatically - see errors above.");
                    }
                }
                throw sessionFailure;
            }

            Log.info("Done.");
            return 0;
        } catch (Exception e) {
            Log.error("pull-push failed", e);
            return 1;
        }
    }

    /**
     * No overrides -> sweep every (config, split) pair the dataset reports (fetchAvailableConfigs).
     * Either override given -> restrict to that one pair, falling back to the configured
     * defaults (agents.hf.config / agents.hf.split) rather than a hardcoded "default" that
     * doesn't correspond to any real HF config name.
     */
    private Map<String, List<Scenario>> resolveSubsets() throws Exception {
        if (configOverride == null && splitOverride == null) {
            return hf.fetchAllSubsets();
        }
        String cfg = configOverride != null ? configOverride : defaultConfig;
        String spl = splitOverride != null ? splitOverride : defaultSplit;
        List<Scenario> rows = hf.fetchAllScenarios(cfg, spl);
        return Map.of(cfg + "/" + spl, rows);
    }

    private void printSummary(List<Scenario> scenarios) {
        var byType = scenarios.stream()
                .collect(Collectors.groupingBy(s -> s.type != null ? s.type : "(unknown)", Collectors.counting()));
        var byDeterminism = scenarios.stream()
                .collect(Collectors.groupingBy(Scenario::isDeterministic, Collectors.counting()));
        Log.info("By agent type: " + byType);
        Log.info("Deterministic vs judged: " + byDeterminism);
    }

    private static String truncate(String value, int maxLen) {
        if (value == null) return "(none)";
        return value.length() <= maxLen ? value : value.substring(0, maxLen) + "...";
    }

    private void printDryRunPlan(Map<String, List<Scenario>> bySubset, List<Scenario> allScenarios) {
        Log.info("---- Dry run plan ----");

        // 1. Agentic benchmark gateway push plan
        if (skipAgenticBenchmark) {
            Log.info("[gateway] --skip-agentic-benchmark set: no rows would be pushed to tb-quarkus.");
        } else {
            int totalRows = allScenarios.size();
            int batches = 0;
            Log.infof("[gateway] Would POST /agentic-benchmark/rows/upsert-batch for %d subset(s), %d row(s) total:",
                    bySubset.size(), totalRows);
            for (var entry : bySubset.entrySet()) {
                int rows = entry.getValue().size();
                int subsetBatches = (int) Math.ceil(rows / 500.0); // matches AgenticBenchmarkPushClient.BATCH_SIZE
                batches += subsetBatches;
                Log.infof("  - subset=%s rows=%d -> %d batch(es) of up to 500", entry.getKey(), rows, subsetBatches);
            }
            Log.infof("[gateway] %d total batch call(s) would be made.", batches);
        }

        // 2. ThingsBoard topology plan - mirrors TbTopologyBuilder.buildFromScenarios exactly
        if (scenariosOnly) {
            Log.info("[thingsboard] --scenarios-only set: no topology would be pushed.");
        } else {
            Set<String> assetClassFilter = Arrays.stream(assetClassFilterCsv.split(","))
                    .map(String::trim).filter(s -> !s.isBlank()).collect(Collectors.toSet());

            Set<String> seenAssets = new HashSet<>();
            Map<String, Integer> sensorDeviceCountByAsset = new TreeMap<>();
            int skippedNoAsset = 0, skippedFilter = 0, skippedUnknownClass = 0;

            for (Scenario s : allScenarios) {
                String assetName = s.asset;
                if (assetName == null || assetName.isBlank()) {
                    skippedNoAsset++;
                    continue;
                }
                String assetClass = s.assetClassGuess();
                if (!assetClassFilter.isEmpty() && !assetClassFilter.contains(assetClass)) {
                    skippedFilter++;
                    continue;
                }
                if (!AssetClassSensors.isKnownClass(assetClass)) {
                    skippedUnknownClass++;
                    continue;
                }
                if (!seenAssets.add(assetName)) {
                    continue; // would already be created earlier in the same run
                }
                int sensorCount = AssetClassSensors.sensorsFor(assetClass).size();
                sensorDeviceCountByAsset.put(assetClass + ":" + assetName, sensorCount);
            }

            int totalDevices = sensorDeviceCountByAsset.values().stream().mapToInt(Integer::intValue).sum();
            Log.infof("[thingsboard] Login would be attempted, then topology built for %d distinct asset(s), %d device(s) total (filter=%s):",
                    sensorDeviceCountByAsset.size(), totalDevices, assetClassFilter.isEmpty() ? "none" : assetClassFilter);
            sensorDeviceCountByAsset.forEach((asset, sensorCount) ->
                    Log.infof("  - %s -> %d sensor device(s) + CONTAINS relation(s)", asset, sensorCount));

            if (skippedNoAsset > 0) {
                Log.infof("[thingsboard] %d row(s) skipped: no asset field (FMSR/WO rows).", skippedNoAsset);
            }
            if (skippedFilter > 0) {
                Log.infof("[thingsboard] %d row(s) skipped: asset class excluded by asset-class-filter.", skippedFilter);
            }
            if (skippedUnknownClass > 0) {
                Log.infof("[thingsboard] %d row(s) skipped: asset class has no known sensor map yet.", skippedUnknownClass);
            }
        }

        // 3. ThingsBoard scenario attribute plan - mirrors TbScenarioStore.pushAll
        if (topologyOnly) {
            Log.info("[thingsboard] --topology-only set: no scenario attributes would be pushed.");
        } else {
            Log.info("[thingsboard] Scenario attributes would be pushed to umbrella asset 'agents.tb.scenario-store-asset', namespaced per subset:");
            bySubset.forEach((subset, rows) -> {
                String keyPrefix = "scenario_" + subset.replace("/", "_") + "_";
                int batchCount = (int) Math.ceil(rows.size() / 50.0); // matches TbScenarioStore.batchSize
                Log.infof("  - subset=%s -> %d attribute(s) as SERVER_SCOPE, key prefix '%s', %d batch(es) of up to 50",
                        subset, rows.size(), keyPrefix, batchCount);
            });
        }

        Log.info("---- End dry run plan ----");
    }
}
