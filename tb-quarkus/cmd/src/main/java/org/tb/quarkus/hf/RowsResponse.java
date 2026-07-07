package org.tb.quarkus.hf;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

/**
 * Shape of https://datasets-server.huggingface.co/rows?dataset=...&config=...&split=...&offset=...&length=...
 *
 * {
 *   "features": [...],
 *   "rows": [ { "row_idx": 0, "row": { ...Scenario fields... }, "truncated_cells": [] }, ... ],
 *   "num_rows_total": 152,
 *   ...
 * }
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public class RowsResponse {

    @JsonProperty("rows")
    public List<Row> rows;

    @JsonProperty("num_rows_total")
    public Integer numRowsTotal;

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Row {
        @JsonProperty("row_idx")
        public Integer rowIdx;

        @JsonProperty("row")
        public Scenario row;
    }
}
