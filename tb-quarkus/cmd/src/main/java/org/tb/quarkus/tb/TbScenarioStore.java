package org.tb.quarkus.tb;

import com.fasterxml.jackson.databind.JsonNode;
import org.tb.quarkus.hf.Scenario;
import io.quarkus.logging.Log;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import org.eclipse.microprofile.config.inject.ConfigProperty;

import java.io.IOException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Every scenario row (utterance + expected-answer spec) is pushed as a single
 * SERVER_SCOPE attribute, keyed "scenario_<id>", on one umbrella Asset. This
 * is deliberately NOT modeled as one Device/Asset per scenario - scenarios
 * aren't physical entities, they're eval fixtures, and 152-467 extra entities
 * for that would be pure topology noise (ponytail: don't reify what isn't a
 * real thing in the domain).
 *
 * Your ADK orchestrator's eval harness (or the WO/FMSR agents themselves,
 * during a dry-run/self-check) can then pull these back via the ThingsBoard
 * MCP server's attribute-read tools instead of re-hitting HuggingFace.
 *
 * Before each batch write, existing values for the keys about to be
 * overwritten are snapshotted so a failure later in the run can restore
 * them (or delete the keys outright if they were brand new).
 */
@ApplicationScoped
public class TbScenarioStore {

    @ConfigProperty(name = "agents.tb.scenario-store-asset")
    String scenarioStoreAssetName;

    @Inject
    TbGateway tb;

    @Inject
    TbSessionLedger ledger;

    public void pushAll(String subsetKey, List<Scenario> scenarios) throws IOException, InterruptedException {
        TbGateway.EntityResult storeAsset = tb.createOrUpdateAsset(
                scenarioStoreAssetName, "AOB_Benchmark", "AssetOpsBench scenario fixtures");
        String assetId = storeAsset.id();
        if (storeAsset.created()) {
            ledger.record("Asset '" + scenarioStoreAssetName + "' (" + assetId + ")",
                    () -> tb.deleteAsset(assetId));
        }

        String keyPrefix = "scenario_" + subsetKey.replace("/", "_") + "_";

        int batchSize = 50;
        for (int i = 0; i < scenarios.size(); i += batchSize) {
            Map<String, Object> batch = new HashMap<>();
            List<Scenario> slice = scenarios.subList(i, Math.min(i + batchSize, scenarios.size()));
            for (Scenario s : slice) {
                batch.put(keyPrefix + s.id, toAttributeValue(s));
            }

            Map<String, JsonNode> before = tb.getServerAttributes("ASSET", assetId, batch.keySet());
            registerAttributeRollback(assetId, batch.keySet(), before);

            tb.saveServerAttributes("ASSET", assetId, batch);
            Log.infof("Pushed scenario attributes %d-%d of %d for subset %s", i, i + slice.size(), scenarios.size(), subsetKey);
        }
    }

    /**
     * If a key already had a value, rollback restores it. If a key didn't
     * exist before this write, rollback deletes it outright.
     */
    private void registerAttributeRollback(String assetId, java.util.Set<String> keys, Map<String, JsonNode> before) {
        java.util.Set<String> brandNewKeys = new java.util.HashSet<>(keys);
        brandNewKeys.removeAll(before.keySet());

        if (!brandNewKeys.isEmpty()) {
            ledger.record("New scenario attribute keys " + brandNewKeys + " on ASSET/" + assetId,
                    () -> tb.deleteServerAttributes("ASSET", assetId, brandNewKeys));
        }
        if (!before.isEmpty()) {
            Map<String, Object> restore = new HashMap<>();
            before.forEach((k, v) -> restore.put(k, v));
            ledger.record("Previous values for " + before.keySet() + " on ASSET/" + assetId,
                    () -> tb.saveServerAttributes("ASSET", assetId, restore));
        }
    }

    private Map<String, Object> toAttributeValue(Scenario s) {
        Map<String, Object> m = new HashMap<>();
        m.put("utterance", s.utterance);
        m.put("agent_type", s.type);
        m.put("category", s.category);
        m.put("group", s.group);
        m.put("deterministic", s.isDeterministic());
        m.put("characteristic_form", s.characteristicForm);
        m.put("asset", s.asset);
        m.put("note", s.note);
        return m;
    }
}
