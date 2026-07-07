package org.tb.quarkus.cli;

import io.quarkus.logging.Log;
import jakarta.inject.Inject;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import picocli.CommandLine;
import org.tb.quarkus.hf.HfDatasetClient;
import org.tb.quarkus.hf.Scenario;
import org.tb.quarkus.tb.TbGateway;
import org.tb.quarkus.tb.TbScenarioStore;
import org.tb.quarkus.tb.TbSessionLedger;
import org.tb.quarkus.tb.TbTopologyBuilder;

import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.stream.Collectors;

@CommandLine.Command(
        name = "pull-push",
        mixinStandardHelpOptions = true,
        description = "Pull AssetOpsBench scenarios from HuggingFace and push topology + scenario data into ThingsBoard."
)
public class PullPushCommand implements Callable<Integer> {

    @Inject
    HfDatasetClient hf;

    @Inject
    TbGateway tb;

    @Inject
    TbTopologyBuilder topologyBuilder;

    @Inject
    TbScenarioStore scenarioStore;

    @Inject
    TbSessionLedger ledger;

    @ConfigProperty(name = "agents.tb.asset-class-filter")
    String assetClassFilterCsv;

    @CommandLine.Option(names = "--config", description = "HF dataset config to pull (default: property aob.hf.config)")
    String configOverride;

    @CommandLine.Option(names = "--split", description = "HF dataset split to pull (default: property aob.hf.split)")
    String splitOverride;

    @CommandLine.Option(names = "--list-configs", description = "List available (config, split) pairs for the dataset and exit")
    boolean listConfigs;

    @CommandLine.Option(names = "--topology-only", description = "Push asset/sensor topology only, skip scenario attribute upload")
    boolean topologyOnly;

    @CommandLine.Option(names = "--scenarios-only", description = "Push scenario attributes only, skip asset/sensor topology")
    boolean scenariosOnly;

    @CommandLine.Option(names = "--dry-run", description = "Pull and parse scenarios, print a summary, push nothing to ThingsBoard")
    boolean dryRun;

    @CommandLine.Option(names = "--no-rollback",
            description = "On failure, leave whatever was already pushed in place instead of rolling it back (useful for debugging a partial run)")
    boolean noRollback;

    @Override
    public Integer call() {
        try {
            if (listConfigs) {
                hf.fetchAvailableConfigs().forEach(pair ->
                        System.out.println("config=" + pair[0] + "  split=" + pair[1]));
                return 0;
            }

            String config = configOverride;
            String split = splitOverride;

            List<Scenario> scenarios = (config != null || split != null)
                    ? hf.fetchAllScenarios(
                        config != null ? config : "default",
                        split != null ? split : "train")
                    : hf.fetchAllScenarios();

            Log.infof("Pulled %d scenarios from HuggingFace", scenarios.size());
            printSummary(scenarios);

            if (dryRun) {
                Log.info("--dry-run set: not connecting to ThingsBoard");
                return 0;
            }

            ledger.reset();

            try {
                tb.login();

                if (!scenariosOnly) {
                    Set<String> assetClassFilter = Arrays.stream(assetClassFilterCsv.split(","))
                            .map(String::trim).filter(s -> !s.isBlank()).collect(Collectors.toSet());
                    Set<String> pushed = topologyBuilder.buildFromScenarios(scenarios, assetClassFilter);
                    Log.infof("Topology pushed for %d distinct assets: %s", pushed.size(), pushed);
                }

                if (!topologyOnly) {
                    scenarioStore.pushAll(scenarios);
                    Log.infof("Pushed %d scenario records as ThingsBoard attributes", scenarios.size());
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

    private void printSummary(List<Scenario> scenarios) {
        var byType = scenarios.stream()
                .collect(Collectors.groupingBy(s -> s.type != null ? s.type : "(unknown)", Collectors.counting()));
        var byDeterminism = scenarios.stream()
                .collect(Collectors.groupingBy(Scenario::isDeterministic, Collectors.counting()));
        Log.info("By agent type: " + byType);
        Log.info("Deterministic vs judged: " + byDeterminism);
    }
}
