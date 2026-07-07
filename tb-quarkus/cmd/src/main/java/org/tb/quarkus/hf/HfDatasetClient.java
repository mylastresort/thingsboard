package org.tb.quarkus.hf;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.quarkus.logging.Log;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import org.eclipse.microprofile.config.inject.ConfigProperty;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Pulls AssetOpsBench scenario rows straight from HuggingFace's
 * datasets-server (https://datasets-server.huggingface.co/rows), which
 * returns JSON directly - no parquet/arrow parsing needed on our side.
 *
 * This is a public, non-gated dataset, so no HF token is required in the
 * common case; aob.hf.token is wired in anyway for gated configs.
 */
@ApplicationScoped
public class HfDatasetClient {

    @ConfigProperty(name = "agents.hf.rows-api")
    String rowsApiBase;

    @ConfigProperty(name = "agents.hf.dataset")
    String dataset;

    @ConfigProperty(name = "agents.hf.config")
    String config;

    @ConfigProperty(name = "agents.hf.split")
    String split;

    @ConfigProperty(name = "agents.hf.page-size")
    int pageSize;

    @ConfigProperty(name = "agents.hf.token")
    Optional<String> token;

    @Inject
    ObjectMapper mapper;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(15))
            .build();

    /** Pulls every row of the configured dataset/config/split, paging until exhausted. */
    public List<Scenario> fetchAllScenarios() throws IOException, InterruptedException {
        return fetchAllScenarios(config, split);
    }

    public List<Scenario> fetchAllScenarios(String configName, String splitName) throws IOException, InterruptedException {
        List<Scenario> all = new ArrayList<>();
        int offset = 0;
        Integer total = null;

        do {
            RowsResponse page = fetchPage(configName, splitName, offset, pageSize);
            if (page.rows == null || page.rows.isEmpty()) {
                break;
            }
            for (RowsResponse.Row r : page.rows) {
                if (r.row != null) {
                    all.add(r.row);
                }
            }
            total = page.numRowsTotal;
            offset += page.rows.size();
            Log.infof("Pulled %d/%s rows from %s/%s (split=%s)", offset,
                    total != null ? total.toString() : "?", dataset, configName, splitName);
        } while (total != null && offset < total);

        return all;
    }

    public EndpointCheck testEndpoints() throws IOException, InterruptedException {
        List<String[]> splits = fetchAvailableConfigs();
        RowsResponse sample = fetchPage(config, split, 0, 1);
        int sampleRows = sample.rows != null ? sample.rows.size() : 0;
        int totalRows = sample.numRowsTotal != null ? sample.numRowsTotal : -1;
        return new EndpointCheck(dataset, config, split, splits.size(), sampleRows, totalRows);
    }

    private RowsResponse fetchPage(String configName, String splitName, int offset, int length) throws IOException, InterruptedException {
        String url = rowsApiBase
                + "?dataset=" + urlEncode(dataset)
                + "&config=" + urlEncode(configName)
                + "&split=" + urlEncode(splitName)
                + "&offset=" + offset
                + "&length=" + length;

        HttpRequest.Builder reqBuilder = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(30))
                .GET();

        if (token.isPresent() && !token.get().isBlank()) {
            reqBuilder.header("Authorization", "Bearer " + token.get());
        }

        HttpResponse<String> response = http.send(reqBuilder.build(), HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            throw new IOException("HF datasets-server returned HTTP " + response.statusCode()
                    + " for " + url + ": " + truncate(response.body(), 500));
        }

        return mapper.readValue(response.body(), RowsResponse.class);
    }

    /**
     * Discovers which (config, split) pairs actually exist for this dataset via the
     * /splits endpoint - useful because AssetOpsBench ships one config per asset
     * class (chillers, compressors, hydraulic pumps, ...) plus a "default" one,
     * and that list can grow as the community contributes new asset classes.
     */
    public List<String[]> fetchAvailableConfigs() throws IOException, InterruptedException {
        String splitsUrl = rowsApiBase.replace("/rows", "/splits") + "?dataset=" + urlEncode(dataset);
        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(splitsUrl))
                .timeout(Duration.ofSeconds(30))
                .GET()
                .build();
        HttpResponse<String> response = http.send(req, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() != 200) {
            throw new IOException("HF /splits returned HTTP " + response.statusCode() + ": " + truncate(response.body(), 500));
        }
        com.fasterxml.jackson.databind.JsonNode root = mapper.readTree(response.body());
        List<String[]> out = new ArrayList<>();
        for (com.fasterxml.jackson.databind.JsonNode split : root.path("splits")) {
            out.add(new String[]{split.path("config").asText(), split.path("split").asText()});
        }
        return out;
    }

    private static String urlEncode(String s) {

        return java.net.URLEncoder.encode(s, java.nio.charset.StandardCharsets.UTF_8);
    }

    private static String truncate(String s, int max) {
        return s == null ? "" : (s.length() > max ? s.substring(0, max) + "..." : s);
    }

    public record EndpointCheck(
            String dataset,
            String config,
            String split,
            int splitCount,
            int sampleRows,
            int totalRows
    ) {
    }
}
