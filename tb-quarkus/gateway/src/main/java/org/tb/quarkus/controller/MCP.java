package org.tb.quarkus.controller;

import io.quarkiverse.mcp.server.Tool;
import io.quarkiverse.mcp.server.ToolArg;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import org.tb.quarkus.model.*;
import org.tb.quarkus.service.FailureModeRecordService;
import org.tb.quarkus.service.PredictiveModelsRestService;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@ApplicationScoped
public class MCP {

    @Inject
    FailureModeRecordService service;
    @Inject
    PredictiveModelsRestService predictiveModelsRestService;

    // --- Models / forecasts (read) ---

    @Tool(description = "Get available predictive maintenance models")
    public Map<String, List<AvailableModelOption>> getAvailableModels() {
        return predictiveModelsRestService.getAvailableModels();
    }

    @Tool(description = "Get all saved model load configurations")
    public Map<String, Object> getLoadModelConfigs() {
        return predictiveModelsRestService.getLoadModelConfigs();
    }

    @Tool(description = "List predictive models (forecasts), paginated with optional text search")
    public Map<String, Object> getPredictiveModelsByPage(
            @ToolArg(description = "Page size") Integer pageSize,
            @ToolArg(description = "Zero-based page number") Integer page,
            @ToolArg(description = "Property to sort by") String sortProperty,
            @ToolArg(description = "Sort order: ASC or DESC") String sortOrder,
            @ToolArg(description = "Optional free-text search filter") String textSearch) {
        return predictiveModelsRestService.listForecasts(pageSize, page, sortProperty, sortOrder, textSearch);
    }

    @Tool(description = "Get a single forecast/model by its id")
    public Map<String, Object> getForecast(@ToolArg(description = "Forecast id") String forecastId) {
        return predictiveModelsRestService.getForecast(forecastId);
    }

    @Tool(description = "Get the current status of a forecast/model job")
    public Map<String, Object> getForecastStatus(@ToolArg(description = "Forecast id") String forecastId) {
        return predictiveModelsRestService.getForecastStatus(forecastId);
    }

    @Tool(description = "List forecasts associated with a specific device, paginated")
    public Map<String, Object> getForecastsByDeviceId(
            @ToolArg(description = "ThingsBoard device id") String deviceId,
            @ToolArg(description = "Page size") Integer pageSize,
            @ToolArg(description = "Zero-based page number") Integer page) {
        return predictiveModelsRestService.getForecastsByDeviceId(deviceId, pageSize, page);
    }

    @Tool(description = "Get historical anomaly predictions for a model within a time range")
    public Map<String, Object> getAnomalyHistoryPredictions(
            @ToolArg(description = "Model id") String modelId,
            @ToolArg(description = "Prediction type filter") String predictionType,
            @ToolArg(description = "Range start, epoch millis") Long startTs,
            @ToolArg(description = "Range end, epoch millis") Long endTs,
            @ToolArg(description = "Max results") Integer limit) {
        return predictiveModelsRestService.getAnomalyHistoryPredictions(modelId, predictionType, startTs, endTs, limit);
    }

    @Tool(description = "Get failure mode history across all devices within a time range")
    public FailureModeHistoryResponse getFailureModeHistoryAllDevices(
            @ToolArg(description = "Range start, epoch millis") Long startTs,
            @ToolArg(description = "Range end, epoch millis") Long endTs,
            @ToolArg(description = "Max results") Integer limit) {
        return service.getHistory(null, startTs, endTs, limit);
    }

    @Tool(description = "Get failure mode history for a specific model within a time range")
    public FailureModeHistoryResponse getFailureModeHistory(
            @ToolArg(description = "Model id") String modelId,
            @ToolArg(description = "Range start, epoch millis") Long startTs,
            @ToolArg(description = "Range end, epoch millis") Long endTs) {
        return service.getHistoryForModel(modelId, startTs, endTs);
    }

    // --- Models / forecasts (write) ---

    @Tool(description = "Save or update a model load configuration. MUTATING.")
    public Map<String, Object> saveLoadModelConfig(
            @ToolArg(description = "Config body as key-value map") Map<String, Object> body) {
        return predictiveModelsRestService.saveLoadModelConfig(body);
    }

    @Tool(description = "Create a new forecast/predictive model job. MUTATING.")
    public Map<String, Object> createForecast(
            @ToolArg(description = "Forecast definition as key-value map") Map<String, Object> body) {
        return predictiveModelsRestService.createForecast(body);
    }

    @Tool(description = "Update an existing forecast/model. MUTATING.")
    public Map<String, Object> updateForecast(
            @ToolArg(description = "Forecast id") String forecastId,
            @ToolArg(description = "Updated fields as key-value map") Map<String, Object> body) {
        return predictiveModelsRestService.updateForecast(forecastId, body);
    }

    @Tool(description = "Delete a forecast/model by id. MUTATING, irreversible.")
    public Map<String, Object> deleteForecast(@ToolArg(description = "Forecast id") String forecastId) {
        return predictiveModelsRestService.deleteForecast(forecastId);
    }

    @Tool(description = "Delete stored anomaly history predictions for a model/type. MUTATING, irreversible.")
    public Map<String, Object> deleteAnomalyHistoryPredictions(
            @ToolArg(description = "Model id") String modelId,
            @ToolArg(description = "Prediction type") String predictionType) {
        return predictiveModelsRestService.deleteAnomalyHistoryPredictions(modelId, predictionType);
    }

    // --- Failure mode records (write) ---

    @Tool(description = "Create a single failure mode record. MUTATING.")
    public FailureModeRecordResponse createFailureModeRecord(
            @ToolArg(description = "Failure mode record") FailureModeRecord body) {
        return service.create(body);
    }

    @Tool(description = "Create multiple failure mode records in one batch. MUTATING.")
    public CreateFailureModeRecordsResponse createFailureModeRecords(
            @ToolArg(description = "List of failure mode records") List<FailureModeRecord> body) {
        return service.createBatch(body);
    }

    @Tool(description = "Update an existing failure mode record. MUTATING.")
    public FailureModeRecordResponse updateFailureModeRecord(
            @ToolArg(description = "Record type") String recordType,
            @ToolArg(description = "Record id (UUID)") String recordId,
            @ToolArg(description = "Updated failure mode record") FailureModeRecord body) {
        return service.update(recordType, UUID.fromString(recordId), body);
    }

    @Tool(description = "Delete a failure mode record by type and id. MUTATING, irreversible.")
    public DeleteFailureModeRecordResponse deleteFailureModeRecord(
            @ToolArg(description = "Record type") String recordType,
            @ToolArg(description = "Record id (UUID)") String recordId) {
        return service.delete(recordType, UUID.fromString(recordId));
    }

    @Tool(description = "Import failure mode records from CSV content. MUTATING.")
    public ImportFailureModeRecordsResponse importFailureModeRecords(
            @ToolArg(description = "Raw CSV file content") String csvContent,
            @ToolArg(description = "Record type") String recordType) {
        var stream = new ByteArrayInputStream(csvContent.getBytes(StandardCharsets.UTF_8));
        return service.importCsv(stream, recordType);
    }
}