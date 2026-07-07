package org.tb.quarkus.model;

import java.util.List;
import java.util.Map;

/**
 * Option A topology: every physical asset (e.g. "Chiller 6") becomes a TB
 * Asset entity, and every sensor becomes its own TB Device entity related
 * to the parent Asset via a CONTAINS relation.
 *
 * This is the default sensor set per asset class, used only as a fallback
 * when a scenario's own text doesn't name a specific sensor/telemetry key
 * (most FMSR/WO rows just say "Chiller 6", not "Chiller 6 Tonnage"). Extend
 * this map as you cover more asset classes from the benchmark.
 */
public final class AssetClassSensors {

    private static final Map<String, List<String>> BY_CLASS = Map.of(
            "chiller", List.of(
                    "Power Input", "Tonnage", "Condenser Water Flow", "Chilled Water Flow",
                    "Return Temp", "Supply Temp", "Condenser Pressure", "Evaporator Pressure"
            ),
            "ahu", List.of(
                    "Supply Air Temp", "Return Air Temp", "Fan Speed", "Damper Position",
                    "Filter Pressure Drop", "Cooling Coil Valve", "Heating Coil Valve"
            ),
            "compressor", List.of(
                    "Discharge Pressure", "Suction Pressure", "Bearing Temp",
                    "Vibration RMS", "Motor Current", "Oil Pressure"
            ),
            "pump", List.of(
                    "Flow Rate", "Discharge Pressure", "Suction Pressure",
                    "Motor Current", "Bearing Temp", "Vibration RMS"
            )
    );

    private AssetClassSensors() {
    }

    public static List<String> sensorsFor(String assetClass) {
        return BY_CLASS.getOrDefault(assetClass, List.of());
    }

    public static boolean isKnownClass(String assetClass) {
        return BY_CLASS.containsKey(assetClass);
    }
}
