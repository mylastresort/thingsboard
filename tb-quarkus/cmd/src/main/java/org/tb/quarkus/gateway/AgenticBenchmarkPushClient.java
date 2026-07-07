package org.tb.quarkus.gateway;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.quarkus.logging.Log;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import org.eclipse.microprofile.rest.client.inject.RestClient;
import org.tb.quarkus.gateway.client.api.AgenticBenchmarkApi;
import org.tb.quarkus.gateway.client.model.AgenticBenchmarkRowRequest;
import org.tb.quarkus.gateway.client.model.UpsertAgenticBenchmarkRowsResponse;
import org.tb.quarkus.hf.Scenario;

import java.util.List;
import java.util.Map;

@ApplicationScoped
public class AgenticBenchmarkPushClient {
    private static final int BATCH_SIZE = 500;

    @Inject
    @RestClient
    AgenticBenchmarkApi api;

    @Inject
    ObjectMapper mapper;

    public int pushAll(Map<String, List<Scenario>> bySubset) {
        int pushed = 0;
        for (var entry : bySubset.entrySet()) {
            List<AgenticBenchmarkRowRequest> rows = entry.getValue().stream()
                    .map(scenario -> toRequest(entry.getKey(), scenario))
                    .toList();
            int upserted = 0;
            for (int start = 0; start < rows.size(); start += BATCH_SIZE) {
                List<AgenticBenchmarkRowRequest> batch =
                        rows.subList(start, Math.min(start + BATCH_SIZE, rows.size()));
                UpsertAgenticBenchmarkRowsResponse response = api.upsertAgenticBenchmarkRows(batch)
                        .await().indefinitely();
                upserted += response.getUpsertedCount() != null ? response.getUpsertedCount() : batch.size();
            }
            pushed += upserted;
            Log.infof("Upserted %d benchmark row(s) to tb-quarkus for subset %s", upserted, entry.getKey());
        }
        return pushed;
    }

    private AgenticBenchmarkRowRequest toRequest(String subsetName, Scenario scenario) {
        var request = new AgenticBenchmarkRowRequest();
        request.setSubsetName(subsetName);
        request.setDatasetRecordId(numericDatasetRecordId(scenario.id));
        request.setSubject(scenario.type);
        request.setQuestion(scenario.utterance != null ? scenario.utterance : "");
        request.setOptions(List.of());
        request.setOptionIds(List.of());
        request.setCorrect(List.of());
        request.setTextType(scenario.category);
        request.setAssetName(scenario.asset);
        request.setRelevancy(scenario.group);
        request.setQuestionType(scenario.characteristicForm);
        request.setContext(scenario.note);
        request.setRawPayload(mapper.convertValue(scenario, Map.class));
        return request;
    }

    private Long numericDatasetRecordId(String id) {
        if (id == null || id.isBlank()) {
            return null;
        }
        try {
            return Long.valueOf(id);
        } catch (NumberFormatException e) {
            return null;
        }
    }
}
