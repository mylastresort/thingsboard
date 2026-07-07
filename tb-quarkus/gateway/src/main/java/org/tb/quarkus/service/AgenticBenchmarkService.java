package org.tb.quarkus.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.core.type.TypeReference;
import io.quarkus.panache.common.Page;
import io.quarkus.panache.common.Sort;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.transaction.Transactional;
import jakarta.ws.rs.NotFoundException;
import org.tb.quarkus.entity.agenticbenchmark.AgenticBenchmarkRowEntity;
import org.tb.quarkus.model.AgenticBenchmarkRow;
import org.tb.quarkus.model.AgenticBenchmarkRowRequest;
import org.tb.quarkus.model.AgenticBenchmarkRowsPage;
import org.tb.quarkus.model.AgenticBenchmarkSubset;
import org.tb.quarkus.model.DeleteAgenticBenchmarkRowResponse;
import org.tb.quarkus.model.UpsertAgenticBenchmarkRowsResponse;
import io.quarkus.hibernate.orm.panache.PanacheQuery;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@ApplicationScoped
public class AgenticBenchmarkService {

    private final ObjectMapper mapper;

    public AgenticBenchmarkService(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public List<AgenticBenchmarkSubset> subsets() {
        List<String> subsetNames = AgenticBenchmarkRowEntity.getEntityManager()
                .createQuery("select distinct e.subsetName from AgenticBenchmarkRowEntity e order by e.subsetName", String.class)
                .getResultList();

        return subsetNames.stream()
                .map(name -> {
                    var subset = new AgenticBenchmarkSubset();
                    subset.setName(name);
                    subset.setRowCount(AgenticBenchmarkRowEntity.count("subsetName", name));
                    return subset;
                })
                .toList();
    }

    public AgenticBenchmarkRowsPage rows(Integer pageSize, Integer page, String subsetName, String textSearch) {
        int size = clamp(pageSize, 25, 1, 100);
        int pageIndex = Math.max(page == null ? 0 : page, 0);
        var query = buildQuery(subsetName, textSearch);
        var sort = Sort.by("subsetName").and("datasetRecordId");

        PanacheQuery<AgenticBenchmarkRowEntity> panacheQuery = query.query().isEmpty()
                ? AgenticBenchmarkRowEntity.findAll(sort)
                : AgenticBenchmarkRowEntity.find(query.query(), sort, query.params());

        long total = panacheQuery.count();
        var data = panacheQuery.page(Page.of(pageIndex, size)).list().stream()
                .map(this::toResponse)
                .toList();
        var response = new AgenticBenchmarkRowsPage();
        response.setData(data);
        response.setTotalElements(total);
        response.setPage(pageIndex);
        response.setPageSize(size);
        return response;
    }

    @Transactional
    public AgenticBenchmarkRow create(AgenticBenchmarkRowRequest request) {
        var entity = new AgenticBenchmarkRowEntity();
        apply(entity, request);
        entity.persist();
        return toResponse(entity);
    }

    @Transactional
    public UpsertAgenticBenchmarkRowsResponse upsertBatch(List<AgenticBenchmarkRowRequest> requests) {
        int upserted = 0;
        for (AgenticBenchmarkRowRequest request : requests) {
            AgenticBenchmarkRowEntity entity = findExisting(request.getSubsetName(), request.getDatasetRecordId());
            if (entity == null) {
                entity = new AgenticBenchmarkRowEntity();
            }
            apply(entity, request);
            entity.persist();
            upserted++;
        }
        var response = new UpsertAgenticBenchmarkRowsResponse();
        response.setUpsertedCount(upserted);
        return response;
    }

    @Transactional
    public AgenticBenchmarkRow update(UUID id, AgenticBenchmarkRowRequest request) {
        AgenticBenchmarkRowEntity entity = AgenticBenchmarkRowEntity.findById(id);
        if (entity == null) {
            throw new NotFoundException("Agentic benchmark row not found");
        }
        apply(entity, request);
        return toResponse(entity);
    }

    @Transactional
    public DeleteAgenticBenchmarkRowResponse delete(UUID id) {
        var response = new DeleteAgenticBenchmarkRowResponse();
        response.setDeletedCount(AgenticBenchmarkRowEntity.deleteById(id) ? 1 : 0);
        return response;
    }

    private AgenticBenchmarkRowEntity findExisting(String subsetName, Long datasetRecordId) {
        if (datasetRecordId == null) {
            return null;
        }
        return AgenticBenchmarkRowEntity.find("subsetName = ?1 and datasetRecordId = ?2", subsetName, datasetRecordId)
                .firstResult();
    }

    private void apply(AgenticBenchmarkRowEntity entity, AgenticBenchmarkRowRequest request) {
        entity.subsetName = value(request.getSubsetName(), "custom");
        entity.datasetRecordId = request.getDatasetRecordId();
        entity.subject = request.getSubject();
        entity.question = value(request.getQuestion(), "");
        entity.options = jsonArray(request.getOptions());
        entity.optionIds = jsonArray(request.getOptionIds());
        entity.correct = jsonArray(request.getCorrect());
        entity.textType = request.getTextType();
        entity.assetName = request.getAssetName();
        entity.relevancy = request.getRelevancy();
        entity.questionType = request.getQuestionType();
        entity.triggerStatement = request.getTriggerStatement();
        entity.context = request.getContext();
        entity.rawPayload = request.getRawPayload() != null ? mapper.valueToTree(request.getRawPayload()) : mapper.createObjectNode();
    }

    private AgenticBenchmarkRow toResponse(AgenticBenchmarkRowEntity entity) {
        var response = new AgenticBenchmarkRow();
        response.setId(entity.id);
        response.setSubsetName(entity.subsetName);
        response.setSourceFile(entity.sourceFile);
        response.setDatasetRecordId(entity.datasetRecordId);
        response.setSubject(entity.subject);
        response.setQuestion(entity.question);
        response.setOptions(list(entity.options, new TypeReference<List<String>>() {}));
        response.setOptionIds(list(entity.optionIds, new TypeReference<List<String>>() {}));
        response.setCorrect(list(entity.correct, new TypeReference<List<Boolean>>() {}));
        response.setTextType(entity.textType);
        response.setAssetName(entity.assetName);
        response.setRelevancy(entity.relevancy);
        response.setQuestionType(entity.questionType);
        response.setTriggerStatement(entity.triggerStatement);
        response.setContext(entity.context);
        response.setRawPayload(mapper.convertValue(entity.rawPayload, new TypeReference<Map<String, Object>>() {}));
        response.setCreatedTime(entity.createdTime);
        response.setUpdatedTime(entity.updatedTime);
        return response;
    }

    private QueryParts buildQuery(String subsetName, String textSearch) {
        var clauses = new ArrayList<String>();
        var params = new ArrayList<Object>();
        if (subsetName != null && !subsetName.isBlank()) {
            params.add(subsetName);
            clauses.add("subsetName = ?" + params.size());
        }
        if (textSearch != null && !textSearch.isBlank()) {
            params.add("%" + textSearch.toLowerCase() + "%");
            String param = "?" + params.size();
            clauses.add("(lower(question) like " + param + " or lower(subject) like " + param + " or lower(assetName) like " + param + ")");
        }
        return new QueryParts(String.join(" and ", clauses), params.toArray());
    }

    private JsonNode jsonArray(List<?> value) {
        return value == null ? mapper.createArrayNode() : mapper.valueToTree(value);
    }

    private <T> T list(JsonNode value, TypeReference<T> typeReference) {
        return value == null || value.isNull() ? mapper.convertValue(List.of(), typeReference) : mapper.convertValue(value, typeReference);
    }

    private String value(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value;
    }

    private int clamp(Integer value, int fallback, int min, int max) {
        int candidate = value == null ? fallback : value;
        return Math.max(min, Math.min(max, candidate));
    }

    private record QueryParts(String query, Object[] params) {}
}