package org.tb.quarkus.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.quarkus.panache.common.Sort;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.persistence.EntityManager;
import jakarta.transaction.Transactional;
import jakarta.ws.rs.NotFoundException;
import org.tb.quarkus.entity.pdm.PredictionEntity;
import org.tb.quarkus.entity.pdm.PredictiveMaintenanceConfigEntity;
import org.tb.quarkus.entity.pdm.PredictiveModelLoadModelConfigEntity;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@ApplicationScoped
public class PredictiveModelsRestService {

    @Inject EntityManager em;
    @Inject ObjectMapper mapper;

    public Map<String, Object> getAvailableModels() {
        return Map.of(
                "AnomalyPredictor", List.of(
                        Map.of("model_name", "random_forest", "model_parameters", Map.of()),
                        Map.of("model_name", "xgboost", "model_parameters", Map.of())),
                "ForecastModel", List.of(
                        Map.of("model_name", "lstm", "model_parameters", Map.of()),
                        Map.of("model_name", "xgboost", "model_parameters", Map.of())));
    }

    public Map<String, Object> getLoadModelConfigs() {
        var configs = new LinkedHashMap<String, Object>();
        for (PredictiveModelLoadModelConfigEntity entity : PredictiveModelLoadModelConfigEntity.<PredictiveModelLoadModelConfigEntity>listAll()) {
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

    public Map<String, Object> listForecasts(Integer pageSize, Integer page, String sortProperty,
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

        List<Map<String, Object>> data = entities.stream().map(this::toForecast).toList();
        return page(data, total, size, offset);
    }

    public Map<String, Object> getForecast(String forecastId) {
        return toForecast(findForecastOrThrow(forecastId));
    }

    @Transactional
    public Map<String, Object> createForecast(Object body) {
        JsonNode node = mapper.valueToTree(body);
        var entity = new PredictiveMaintenanceConfigEntity();
        entity.id = UUID.randomUUID();
        entity.createdTime = System.currentTimeMillis();
        entity.tenantId = uuidOr(firstNonBlank(nestedId(node.get("tenantId")), firstTenantId()));
        entity.deviceId = uuidOr(nestedId(node.get("deviceId")));
        applyForecastBody(entity, node, true);
        entity.persist();
        return toForecast(entity);
    }

    @Transactional
    public Map<String, Object> updateForecast(String forecastId, Object body) {
        var entity = findForecastOrThrow(forecastId);
        applyForecastBody(entity, mapper.valueToTree(body), false);
        return toForecast(entity);
    }

    @Transactional
    public Map<String, Object> deleteForecast(String forecastId) {
        boolean deleted = PredictiveMaintenanceConfigEntity.deleteById(UUID.fromString(forecastId));
        if (!deleted) {
            throw new NotFoundException("Forecast not found");
        }
        return Map.of("deleted", true, "id", forecastId);
    }

    public Map<String, Object> getForecastStatus(String forecastId) {
        findForecastOrThrow(forecastId);
        return Map.of("forecast_id", forecastId, "status", "inactive");
    }

    public Map<String, Object> getForecastsByDeviceId(String deviceId, Integer pageSize, Integer page) {
        int size = pageSize == null ? 1000 : pageSize;
        int pageNumber = page == null ? 0 : page;
        int offset = pageNumber * size;
        UUID deviceUuid = UUID.fromString(deviceId);
        long total = PredictiveMaintenanceConfigEntity.count("deviceId = ?1", deviceUuid);
        List<PredictiveMaintenanceConfigEntity> entities = PredictiveMaintenanceConfigEntity
                .<PredictiveMaintenanceConfigEntity>find("deviceId = ?1", Sort.descending("createdTime"), deviceUuid)
                .page(pageNumber, size)
                .list();
        List<Map<String, Object>> data = entities.stream().map(this::toForecast).toList();
        return page(data, total, size, offset);
    }

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

    private void applyForecastBody(PredictiveMaintenanceConfigEntity entity, JsonNode node, boolean creating) {
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
                creating ? mapper.valueToTree(Map.of("selectedViews", List.of("forecast", "anomalies"))) : mapper.createObjectNode());
        entity.additionalData = jsonNodeOr(node.get("additionalData"), mapper.createObjectNode());
    }

    private PredictiveMaintenanceConfigEntity findForecastOrThrow(String forecastId) {
        PredictiveMaintenanceConfigEntity entity = PredictiveMaintenanceConfigEntity.findById(UUID.fromString(forecastId));
        if (entity == null) {
            throw new NotFoundException("Forecast not found");
        }
        return entity;
    }

    private Map<String, Object> toForecast(PredictiveMaintenanceConfigEntity entity) {
        var forecast = new LinkedHashMap<String, Object>();
        forecast.put("id", entityId("FORECAST", string(entity.id)));
        forecast.put("tenantId", entityId("TENANT", string(entity.tenantId)));
        forecast.put("deviceId", entityId("DEVICE", string(entity.deviceId)));
        forecast.put("createdTime", entity.createdTime);
        forecast.put("name", entity.name);
        forecast.put("attributes", toPlainJson(entity.attributes, List.of()));
        forecast.put("forecastAlgorithm", entity.forecastAlgorithm);
        forecast.put("forecastStartDate", entity.forecastStartDate);
        forecast.put("forecastEndDate", entity.forecastEndDate);
        forecast.put("anomalyAlgorithm", entity.anomalyAlgorithm);
        forecast.put("anomalyStartDate", entity.anomalyStartDate);
        forecast.put("anomalyEndDate", entity.anomalyEndDate);
        forecast.put("viewPreferences", toPlainJson(entity.viewPreferences, null));
        forecast.put("additionalData", toPlainJson(entity.additionalData, Map.of()));
        return forecast;
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
        if (node == null || node.isNull() || node.isMissingNode()) return null;
        if (node.isTextual()) return node.asText();
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
