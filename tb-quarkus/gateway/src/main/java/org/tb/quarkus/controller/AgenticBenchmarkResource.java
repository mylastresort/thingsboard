package org.tb.quarkus.controller;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import org.tb.quarkus.api.AgenticBenchmarkApi;
import org.tb.quarkus.model.AgenticBenchmarkRow;
import org.tb.quarkus.model.AgenticBenchmarkRowRequest;
import org.tb.quarkus.model.AgenticBenchmarkRowsPage;
import org.tb.quarkus.model.AgenticBenchmarkSubset;
import org.tb.quarkus.model.DeleteAgenticBenchmarkRowResponse;
import org.tb.quarkus.model.UpsertAgenticBenchmarkRowsResponse;
import org.tb.quarkus.service.AgenticBenchmarkService;

import java.util.List;
import java.util.UUID;

@ApplicationScoped
public class AgenticBenchmarkResource implements AgenticBenchmarkApi {
    @Inject
    AgenticBenchmarkService service;

    @Override
    public List<AgenticBenchmarkSubset> getAgenticBenchmarkSubsets() {
        return service.subsets();
    }

    @Override
    public AgenticBenchmarkRowsPage getAgenticBenchmarkRows(Integer pageSize,
                                                            Integer page,
                                                            String subsetName,
                                                            String textSearch) {
        return service.rows(pageSize, page, subsetName, textSearch);
    }

    @Override
    public AgenticBenchmarkRow createAgenticBenchmarkRow(AgenticBenchmarkRowRequest request) {
        return service.create(request);
    }

    @Override
    public UpsertAgenticBenchmarkRowsResponse upsertAgenticBenchmarkRows(List<AgenticBenchmarkRowRequest> request) {
        return service.upsertBatch(request);
    }

    @Override
    public AgenticBenchmarkRow updateAgenticBenchmarkRow(UUID rowId, AgenticBenchmarkRowRequest request) {
        return service.update(rowId, request);
    }

    @Override
    public DeleteAgenticBenchmarkRowResponse deleteAgenticBenchmarkRow(UUID rowId) {
        return service.delete(rowId);
    }
}