package org.tb.quarkus.tb;

import com.fasterxml.jackson.databind.JsonNode;
import org.tb.quarkus.hf.Scenario;
import org.tb.quarkus.model.AssetClassSensors;
import io.quarkus.logging.Log;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;

import java.io.IOException;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Option A topology: each distinct physical asset named across the scenario
 * set (e.g. "Chiller 6") becomes a TB Asset; each sensor in that asset
 * class's known sensor list becomes its own TB Device, related to the
 * parent Asset via a CONTAINS relation.
 *
 * Every entity/relation this run actually creates (as opposed to finds
 * already existing) is registered with the {@link TbSessionLedger} so it can
 * be undone if a later step in the same run fails.
 */
@ApplicationScoped
public class TbTopologyBuilder {

    @Inject
    TbGateway tb;

    @Inject
    TbSessionLedger ledger;

    /**
     * @return the set of distinct (assetClass, assetName) pairs actually pushed,
     *         so the caller can report a summary.
     */
    public Set<String> buildFromScenarios(List<Scenario> scenarios, Set<String> assetClassFilter)
            throws IOException, InterruptedException {

        Set<String> seenAssets = new HashSet<>();
        Set<String> pushed = new HashSet<>();

        for (Scenario s : scenarios) {
            String assetName = s.asset;
            if (assetName == null || assetName.isBlank()) {
                continue; // FMSR/WO rows without an explicit asset - topology-irrelevant
            }
            String assetClass = s.assetClassGuess();
            if (!assetClassFilter.isEmpty() && !assetClassFilter.contains(assetClass)) {
                continue;
            }
            if (!AssetClassSensors.isKnownClass(assetClass)) {
                continue; // no sensor map yet for this class - skip topology, scenario JSON still gets pushed separately
            }
            if (!seenAssets.add(assetName)) {
                continue; // already created this run
            }

            TbGateway.EntityResult asset = tb.createOrUpdateAsset(assetName, capitalize(assetClass), assetName);
            JsonNode assetId = asset.json().path("id");
            if (asset.created()) {
                String id = asset.id();
                ledger.record("Asset '" + assetName + "' (" + id + ")",
                        () -> tb.deleteAsset(id));
            }

            for (String sensorName : AssetClassSensors.sensorsFor(assetClass)) {
                String deviceName = assetName + " - " + sensorName;
                TbGateway.EntityResult device = tb.createOrUpdateDevice(deviceName, "sensor", sensorName);
                JsonNode deviceId = device.json().path("id");
                if (device.created()) {
                    String id = device.id();
                    ledger.record("Device '" + deviceName + "' (" + id + ")",
                            () -> tb.deleteDevice(id));
                }

                // Only worth an explicit undo if neither endpoint was fresh - if the
                // asset or device itself gets rolled back, TB cascades the relation.
                if (!asset.created() && !device.created()) {
                    ledger.record("Contains relation " + assetName + " -> " + deviceName,
                            () -> tb.deleteContainsRelation(assetId, deviceId));
                }
                tb.saveContainsRelation(assetId, deviceId);
            }

            Log.infof("Pushed topology for '%s' (%s): %d sensors", assetName, assetClass,
                    AssetClassSensors.sensorsFor(assetClass).size());
            pushed.add(assetClass + ":" + assetName);
        }

        return pushed;
    }

    private static String capitalize(String s) {
        return s.isEmpty() ? s : Character.toUpperCase(s.charAt(0)) + s.substring(1);
    }
}
