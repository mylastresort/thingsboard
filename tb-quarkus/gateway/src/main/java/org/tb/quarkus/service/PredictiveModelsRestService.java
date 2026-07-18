package org.tb.quarkus.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.quarkus.panache.common.Sort;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.persistence.EntityManager;
import jakarta.transaction.Transactional;
import jakarta.ws.rs.NotFoundException;
import org.tb.quarkus.entity.pdm.DeviceErrorEntity;
import org.tb.quarkus.entity.pdm.DeviceFailureEntity;
import org.tb.quarkus.entity.pdm.DeviceMaintenanceEntity;
import org.tb.quarkus.entity.pdm.PredictionEntity;
import org.tb.quarkus.entity.pdm.PredictiveMaintenanceConfigEntity;
import org.tb.quarkus.entity.pdm.PredictiveModelLoadModelConfigEntity;
import org.tb.quarkus.model.AvailableAlgorithmOption;
import org.tb.quarkus.model.DiscoveredKeysResponse;
import org.tb.quarkus.model.PredictionCreateRequest;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Naming convention in this class:
 *  - "PredictiveModel" refers to the overall model configuration
 *    (PredictiveMaintenanceConfigEntity), which bundles both a forecast
 *    sub-config and an anomaly sub-config.
 *  - "forecast" / "anomaly" are reserved for the sub-config fields
 *    (forecastAlgorithm/forecastStartDate/forecastEndDate,
 *    anomalyAlgorithm/anomalyStartDate/anomalyEndDate) and for
 *    PredictionEntity.predictionType values.
 *
 * NOTE: entityType "FORECAST" and any REST path segments are left
 * unchanged here since they are part of the external wire contract.
 * Renaming those is a breaking API change and should be done as a
 * separate, versioned step (see PR description).
 */
@ApplicationScoped
public class PredictiveModelsRestService {

    @Inject
    EntityManager em;
    @Inject
    ObjectMapper mapper;

    public Map<String, List<AvailableAlgorithmOption>> getAvailableAlgorithms() {
        return Map.of(
                "AnomalyPredictor", List.of(
                        algorithmOption("random_forest", Map.of()),
                        algorithmOption("xgboost", Map.of())),
                "ForecastModel", List.of(
                        algorithmOption("lstm", Map.of()),
                        algorithmOption("xgboost", Map.of())));
    }

    private AvailableAlgorithmOption algorithmOption(String name, Map<String, Object> parameters) {
        AvailableAlgorithmOption option = new AvailableAlgorithmOption();
        option.setModelName(name);
        option.setModelParameters(parameters);
        return option;
    }

    public Map<String, Object> getLoadModelConfigs() {
        var configs = new LinkedHashMap<String, Object>();
        for (PredictiveModelLoadModelConfigEntity entity : PredictiveModelLoadModelConfigEntity
                .<PredictiveModelLoadModelConfigEntity>listAll()) {
            configs.put(entity.name, toPlainJson(entity.config, Map.of()));
        }
        return configs;
    }

    @Transactional
    public Map<String, Object> saveLoadModelConfig(Object body) {
        JsonNode node = mapper.valueToTree(body);
        String name = text(node.get("name"));
        PredictiveModelLoadModelConfigEntity.delete("name = ?1", name);

        var entity = new PredictiveModelLoadModelConfigEntity();
        entity.name = name;
        entity.config = node.get("config") == null ? mapper.createObjectNode() : node.get("config");
        entity.persist();
        return Map.of("status", "Load model configuration saved successfully");
    }

    // --- PredictiveModel CRUD (formerly "Forecast*") ---
    // These operate on PredictiveMaintenanceConfigEntity, which stores a
    // full model configuration containing both a forecast sub-config and
    // an anomaly sub-config.

    public Map<String, Object> listPredictiveModels(Integer pageSize, Integer page, String sortProperty,
            String sortOrder, String textSearch) {
        int size = pageSize == null ? 10 : pageSize;
        int pageNumber = page == null ? 0 : page;
        int offset = pageNumber * size;
        Sort sort = Sort.by(sortField(sortProperty), sortDirection(sortOrder));

        List<PredictiveMaintenanceConfigEntity> entities;
        long total;
        if (textSearch != null && !textSearch.isBlank()) {
            String search = "%" + textSearch.toLowerCase() + "%";
            total = PredictiveMaintenanceConfigEntity.count("lower(name) like ?1", search);
            entities = PredictiveMaintenanceConfigEntity
                    .<PredictiveMaintenanceConfigEntity>find("lower(name) like ?1", sort, search)
                    .page(pageNumber, size)
                    .list();
        } else {
            total = PredictiveMaintenanceConfigEntity.count();
            entities = PredictiveMaintenanceConfigEntity
                    .<PredictiveMaintenanceConfigEntity>findAll(sort)
                    .page(pageNumber, size)
                    .list();
        }

        List<Map<String, Object>> data = entities.stream().map(this::toPredictiveModel).toList();
        return page(data, total, size, offset);
    }

    public Map<String, Object> getPredictiveModel(String predictiveModelId) {
        return toPredictiveModel(findPredictiveModelOrThrow(predictiveModelId));
    }

    @Transactional
    public Map<String, Object> createPredictiveModel(Object body) {
        JsonNode node = mapper.valueToTree(body);
        var entity = new PredictiveMaintenanceConfigEntity();
        entity.id = UUID.randomUUID();
        entity.createdTime = System.currentTimeMillis();
        entity.tenantId = uuidOr(firstNonBlank(nestedId(node.get("tenantId")), firstTenantId()));
        entity.deviceId = uuidOr(nestedId(node.get("deviceId")));
        applyPredictiveModelBody(entity, node, true);
        entity.persist();
        return toPredictiveModel(entity);
    }

    @Transactional
    public Map<String, Object> updatePredictiveModel(String predictiveModelId, Object body) {
        var entity = findPredictiveModelOrThrow(predictiveModelId);
        applyPredictiveModelBody(entity, mapper.valueToTree(body), false);
        return toPredictiveModel(entity);
    }

    @Transactional
    public Map<String, Object> deletePredictiveModel(String predictiveModelId) {
        boolean deleted = PredictiveMaintenanceConfigEntity.deleteById(UUID.fromString(predictiveModelId));
        if (!deleted) {
            throw new NotFoundException("Predictive model not found");
        }
        return Map.of("deleted", true, "id", predictiveModelId);
    }

    public Map<String, Object> getPredictiveModelStatus(String predictiveModelId) {
        findPredictiveModelOrThrow(predictiveModelId);
        return Map.of("forecast_id", predictiveModelId, "status", "inactive");
    }

    public Map<String, Object> getPredictiveModelsByDeviceId(String deviceId, Integer pageSize, Integer page) {
        int size = pageSize == null ? 1000 : pageSize;
        int pageNumber = page == null ? 0 : page;
        int offset = pageNumber * size;
        UUID deviceUuid = UUID.fromString(deviceId);
        long total = PredictiveMaintenanceConfigEntity.count("deviceId = ?1", deviceUuid);
        List<PredictiveMaintenanceConfigEntity> entities = PredictiveMaintenanceConfigEntity
                .<PredictiveMaintenanceConfigEntity>find("deviceId = ?1", Sort.descending("createdTime"), deviceUuid)
                .page(pageNumber, size)
                .list();
        List<Map<String, Object>> data = entities.stream().map(this::toPredictiveModel).toList();
        return page(data, total, size, offset);
    }

    public DiscoveredKeysResponse getDiscoveredKeys(String deviceId) {
        UUID deviceUuid = UUID.fromString(deviceId);

        List<String> errorCodes = DeviceErrorEntity
                .<DeviceErrorEntity>find("deviceId = ?1", deviceUuid)
                .list()
                .stream()
                .map(e -> e.errorCode)
                .filter(code -> code != null && !code.isBlank())
                .distinct()
                .sorted()
                .toList();

        List<String> rootCauses = DeviceFailureEntity
                .<DeviceFailureEntity>find("deviceId = ?1", deviceUuid)
                .list()
                .stream()
                .map(f -> f.rootCause)
                .filter(rc -> rc != null && !rc.isBlank())
                .distinct()
                .sorted()
                .toList();

        List<String> partsReplaced = DeviceMaintenanceEntity
                .<DeviceMaintenanceEntity>find("deviceId = ?1", deviceUuid)
                .list()
                .stream()
                .map(m -> m.partsReplaced)
                .filter(pr -> pr != null && !pr.isBlank())
                .distinct()
                .sorted()
                .toList();

        return new DiscoveredKeysResponse()
                .errorCodes(errorCodes)
                .rootCauses(rootCauses)
                .partsReplaced(partsReplaced);
    }

    // --- Prediction history (unchanged naming: keyed by modelId, values are forecast/anomaly predictions) ---

    public Map<String, Object> getAnomalyHistoryPredictions(String modelId, String predictionType,
            Long startTs, Long endTs, Integer limit) {
        List<Object> params = new ArrayList<>();
        StringBuilder query = new StringBuilder("modelId = ?1");
        params.add(UUID.fromString(modelId));
        if (startTs != null) {
            params.add(startTs);
            query.append(" and createdTime >= ?").append(params.size());
        }
        if (endTs != null) {
            params.add(endTs);
            query.append(" and createdTime <= ?").append(params.size());
        }
        if (predictionType != null && !predictionType.isBlank()) {
            params.add(predictionType);
            query.append(" and predictionType = ?").append(params.size());
        }

        int resultLimit = limit == null ? 100 : limit;
        var predictionsQuery = PredictionEntity
                .<PredictionEntity>find(query.toString(), Sort.descending("createdTime"), params.toArray());
        if (resultLimit > 0) {
            predictionsQuery.range(0, resultLimit - 1);
        }
        List<Map<String, Object>> predictions = predictionsQuery.list().stream()
                .map(this::toPrediction)
                .toList();
        return Map.of("predictions", predictions, "totalCount", predictions.size(), "limit", resultLimit);
    }

    @Transactional
    public Map<String, Object> createAnomalyHistoryPrediction(String modelId, String predictionType,
            PredictionCreateRequest body) {
        var entity = new PredictionEntity();
        entity.modelId = UUID.fromString(modelId);
        entity.createdTime = body.getCreatedTime() == null ? System.currentTimeMillis() : body.getCreatedTime();
        entity.createdAt = instantOrNow(body.getCreatedAt());
        entity.predictionTime = instantOrNow(body.getPredictionTime());
        entity.predictionType = predictionType;
        entity.predictionValue = mapper
                .valueToTree(body.getPredictionValue() == null ? Map.of() : body.getPredictionValue());
        entity.persist();
        return toPrediction(entity);
    }

    @Transactional
    public Map<String, Object> deleteAnomalyHistoryPredictions(String modelId, String predictionType) {
        long deleted;
        UUID modelUuid = UUID.fromString(modelId);
        if (predictionType != null && !predictionType.isBlank()) {
            deleted = PredictionEntity.delete("modelId = ?1 and predictionType = ?2", modelUuid, predictionType);
        } else {
            deleted = PredictionEntity.delete("modelId = ?1", modelUuid);
        }
        return Map.of("deletedCount", deleted, "message", "Successfully deleted " + deleted + " predictions");
    }

    private void applyPredictiveModelBody(PredictiveMaintenanceConfigEntity entity, JsonNode node, boolean creating) {
        entity.name = text(node.get("name"));
        entity.deviceId = uuidOr(nestedId(node.get("deviceId")));
        entity.attributes = jsonNodeOr(node.get("attributes"), mapper.createArrayNode());
        entity.forecastAlgorithm = textOr(node.get("forecastAlgorithm"), "ARIMA");
        entity.forecastStartDate = longOr(node.get("forecastStartDate"), 0);
        entity.forecastEndDate = longOr(node.get("forecastEndDate"), 0);
        entity.anomalyAlgorithm = textOr(node.get("anomalyAlgorithm"), "THRESHOLD");
        entity.anomalyStartDate = longOr(node.get("anomalyStartDate"), 0);
        entity.anomalyEndDate = longOr(node.get("anomalyEndDate"), 0);
        entity.viewPreferences = jsonNodeOr(
                node.get("viewPreferences"),
                creating ? mapper.valueToTree(Map.of("selectedViews", List.of("forecast", "anomalies")))
                        : mapper.createObjectNode());
        entity.additionalData = jsonNodeOr(node.get("additionalData"), mapper.createObjectNode());
    }

    private PredictiveMaintenanceConfigEntity findPredictiveModelOrThrow(String predictiveModelId) {
        PredictiveMaintenanceConfigEntity entity = PredictiveMaintenanceConfigEntity
                .findById(UUID.fromString(predictiveModelId));
        if (entity == null) {
            throw new NotFoundException("Predictive model not found");
        }
        return entity;
    }

    private Map<String, Object> toPredictiveModel(PredictiveMaintenanceConfigEntity entity) {
        var predictiveModel = new LinkedHashMap<String, Object>();
        // entityType left as "FORECAST" intentionally: external wire contract, not renamed here.
        predictiveModel.put("id", entityId("FORECAST", string(entity.id)));
        predictiveModel.put("tenantId", entityId("TENANT", string(entity.tenantId)));
        predictiveModel.put("deviceId", entityId("DEVICE", string(entity.deviceId)));
        predictiveModel.put("createdTime", entity.createdTime);
        predictiveModel.put("name", entity.name);
        predictiveModel.put("attributes", toPlainJson(entity.attributes, List.of()));
        predictiveModel.put("forecastAlgorithm", entity.forecastAlgorithm);
        predictiveModel.put("forecastStartDate", entity.forecastStartDate);
        predictiveModel.put("forecastEndDate", entity.forecastEndDate);
        predictiveModel.put("anomalyAlgorithm", entity.anomalyAlgorithm);
        predictiveModel.put("anomalyStartDate", entity.anomalyStartDate);
        predictiveModel.put("anomalyEndDate", entity.anomalyEndDate);
        predictiveModel.put("viewPreferences", toPlainJson(entity.viewPreferences, null));
        predictiveModel.put("additionalData", toPlainJson(entity.additionalData, Map.of()));
        return predictiveModel;
    }

    private Map<String, Object> toPrediction(PredictionEntity entity) {
        var prediction = new LinkedHashMap<String, Object>();
        prediction.put("id", string(entity.id));
        prediction.put("modelId", string(entity.modelId));
        prediction.put("createdTime", entity.createdTime);
        prediction.put("createdAt", entity.createdAt == null ? null : entity.createdAt.toString());
        prediction.put("predictionTime", entity.predictionTime == null ? null : entity.predictionTime.toString());
        prediction.put("predictionType", entity.predictionType);
        prediction.put("predictionValue", toPlainJson(entity.predictionValue, Map.of()));
        return prediction;
    }

    private static Instant instantOrNow(Object value) {
        if (value == null) {
            return Instant.now();
        }
        if (value instanceof Date date) {
            return date.toInstant();
        }
        return Instant.parse(value.toString());
    }

    private Map<String, Object> page(List<Map<String, Object>> data, long total, int pageSize, int offset) {
        return Map.of(
                "data", data,
                "totalPages", (total + pageSize - 1) / pageSize,
                "totalElements", total,
                "hasNext", offset + pageSize < total);
    }

    private Map<String, Object> entityId(String entityType, String id) {
        var value = new LinkedHashMap<String, Object>();
        value.put("entityType", entityType);
        value.put("id", id);
        return value;
    }

    private String firstTenantId() {
        var rows = em.createNativeQuery("SELECT id FROM public.tenant LIMIT 1").getResultList();
        return rows.isEmpty() ? "13814000-1dd2-11b2-8080-808080808080" : string(rows.get(0));
    }

    private String sortField(String sortProperty) {
        return switch (sortProperty == null ? "createdTime" : sortProperty) {
            case "name" -> "name";
            case "deviceId" -> "deviceId";
            default -> "createdTime";
        };
    }

    private Sort.Direction sortDirection(String sortOrder) {
        return "ASC".equalsIgnoreCase(sortOrder) ? Sort.Direction.Ascending : Sort.Direction.Descending;
    }

    private JsonNode jsonNodeOr(JsonNode node, JsonNode fallback) {
        if (node == null || node.isNull() || node.isMissingNode()) {
            return fallback;
        }
        if (node.isTextual()) {
            try {
                return mapper.readTree(node.asText());
            } catch (Exception ignored) {
                return fallback;
            }
        }
        return node;
    }

    private Object toPlainJson(JsonNode value, Object fallback) {
        if (value == null || value.isNull()) {
            return fallback;
        }
        return mapper.convertValue(value, Object.class);
    }

    private UUID uuidOr(String value) {
        return value == null || value.isBlank() ? null : UUID.fromString(value);
    }

    private String nestedId(JsonNode node) {
        if (node == null || node.isNull() || node.isMissingNode())
            return null;
        if (node.isTextual())
            return node.asText();
        JsonNode id = node.get("id");
        return id == null || id.isNull() ? null : id.asText();
    }

    private String text(JsonNode node) {
        return node == null || node.isNull() ? null : node.asText();
    }

    private String textOr(JsonNode node, String fallback) {
        String value = text(node);
        return value == null || value.isBlank() ? fallback : value;
    }

    private long longOr(JsonNode node, long fallback) {
        return node == null || node.isNull() ? fallback : node.asLong(fallback);
    }

    private String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return null;
    }

    private String string(Object value) {
        return value == null ? null : value.toString();
    }
}