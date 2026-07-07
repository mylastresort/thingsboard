package org.tb.quarkus.hf;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Mirrors one row of the AssetOpsBench "scenarios" config, as returned by
 * the HF datasets-server /rows endpoint. Field names follow the dataset's
 * own column names so Jackson can bind directly without a mapping layer.
 *
 * Not every config carries every column (e.g. "note" is often null), so
 * everything is nullable on purpose.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public class Scenario {

    @JsonProperty("id")
    public Integer id;

    /** Free-text ask, e.g. "download Chiller 6 tonnage for last week of 2020". */
    @JsonProperty("utterance")
    public String utterance;

    /** Owning agent: IoT | FMSR | TSFM | WO | Vibration (per row). */
    @JsonProperty("type")
    public String type;

    /** Knowledge Query | Data Query | Inference Query | Tuning Query | Decision Support | Prediction. */
    @JsonProperty("category")
    public String category;

    /** retrospective | predictive | prescriptive (or a ; separated combo). */
    @JsonProperty("group")
    public String group;

    @JsonProperty("deterministic")
    public Boolean deterministic;

    /** Expected-answer shape/spec used for grading. Kept as raw text; may itself be JSON. */
    @JsonProperty("characteristic_form")
    public String characteristicForm;

    @JsonProperty("note")
    public String note;

    /** Asset the utterance is about, e.g. "Chiller 6". Column name varies slightly by config version. */
    @JsonProperty("asset")
    public String asset;

    public boolean isDeterministic() {
        return Boolean.TRUE.equals(deterministic);
    }

    /** Best-effort asset-class guess (chiller / ahu / compressor / pump / unknown), used for the TB filter. */
    public String assetClassGuess() {
        String source = (asset != null ? asset : "") + " " + (utterance != null ? utterance : "");
        String s = source.toLowerCase();
        if (s.contains("chiller")) return "chiller";
        if (s.contains("ahu") || s.contains("air handl")) return "ahu";
        if (s.contains("compressor")) return "compressor";
        if (s.contains("pump")) return "pump";
        return "unknown";
    }
}
