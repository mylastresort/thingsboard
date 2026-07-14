package org.tb.quarkus.controller;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.ws.rs.BadRequestException;
import org.tb.quarkus.api.ModelsApi;
import org.tb.quarkus.model.*;
import org.tb.quarkus.service.FailureModeRecordService;
import org.tb.quarkus.service.PdmSeedService;
import org.tb.quarkus.service.PredictiveModelsRestService;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.io.InputStream;

@ApplicationScoped
public class ModelsApiImpl implements ModelsApi {

    @Inject
    FailureModeRecordService service;
    @Inject
    PredictiveModelsRestService predictiveModelsRestService;
    @Inject
    PdmSeedService pdmSeedService;

    @Override
    public Map<String, List<AvailableAlgorithmOption>> getAvailableAlgorithms() {
        return predictiveModelsRestService.getAvailableAlgorithms();
    }

    @Override
    public Map<String, Object> saveLoadModelConfig(Map<String, Object> body) {
        return predictiveModelsRestService.saveLoadModelConfig(body);
    }

    @Override
    public Map<String, Object> getLoadModelConfigs() {
        return predictiveModelsRestService.getLoadModelConfigs();
    }

    @Override
    public Map<String, Object> getAnomalyHistoryPredictions(String modelId, String predictionType,
            Long startTs, Long endTs, Integer limit) {
        return predictiveModelsRestService.getAnomalyHistoryPredictions(modelId, predictionType, startTs, endTs, limit);
    }

    @Override
    public Map<String, Object> createAnomalyHistoryPrediction(String modelId, String predictionType,
            PredictionCreateRequest body) {
        return predictiveModelsRestService.createAnomalyHistoryPrediction(modelId, predictionType, body);
    }

    @Override
    public Map<String, Object> deleteAnomalyHistoryPredictions(String modelId, String predictionType) {
        return predictiveModelsRestService.deleteAnomalyHistoryPredictions(modelId, predictionType);
    }

    @Override
    public Map<String, Object> getPredictiveModelsByPage(Integer pageSize, Integer page,
            String sortProperty, String sortOrder, String textSearch) {
        return predictiveModelsRestService.listForecasts(pageSize, page, sortProperty, sortOrder, textSearch);
    }

    @Override
    public Map<String, Object> createForecast(Map<String, Object> body) {
        return predictiveModelsRestService.createForecast(body);
    }

    @Override
    public Map<String, Object> getForecast(String forecastId) {
        return predictiveModelsRestService.getForecast(forecastId);
    }

    @Override
    public Map<String, Object> updateForecast(String forecastId, Map<String, Object> body) {
        return predictiveModelsRestService.updateForecast(forecastId, body);
    }

    @Override
    public Map<String, Object> deleteForecast(String forecastId) {
        return predictiveModelsRestService.deleteForecast(forecastId);
    }

    @Override
    public Map<String, Object> getForecastStatus(String forecastId) {
        return predictiveModelsRestService.getForecastStatus(forecastId);
    }

    @Override
    public Map<String, Object> getForecastsByDeviceId(String deviceId, Integer pageSize, Integer page) {
        return predictiveModelsRestService.getForecastsByDeviceId(deviceId, pageSize, page);
    }

    @Override
    public PdmSeedMachineOptions getSeedMachineOptions() {
        return pdmSeedService.getOptions();
    }

    @Override
    public PdmSeedMachineResult seedMachine(PdmSeedMachineRequest body) {
        try {
            return pdmSeedService.seed(body);
        } catch (IllegalArgumentException e) {
            throw new BadRequestException(e.getMessage(), e);
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("Failed to seed PdM machine", e);
        }
    }

    @Override
    public FailureModeHistoryResponse getFailureModeHistoryAllDevices(Long startTs, Long endTs, Integer limit) {
        return service.getHistory(null, startTs, endTs, limit);
    }

    @Override
    public FailureModeHistoryResponse getFailureModeHistory(String modelId, Long startTs, Long endTs) {
        return service.getHistoryForModel(modelId, startTs, endTs);
    }

    @Override
    public FailureModeRecordResponse createFailureModeRecord(FailureModeRecord body) {
        return service.create(body);
    }

    @Override
    public CreateFailureModeRecordsResponse createFailureModeRecords(List<FailureModeRecord> body) {
        return service.createBatch(body);
    }

    @Override
    public FailureModeRecordResponse updateFailureModeRecord(String recordType, UUID recordId, FailureModeRecord body) {
        return service.update(recordType, recordId, body);
    }

    @Override
    public DeleteFailureModeRecordResponse deleteFailureModeRecord(String recordType, UUID recordId) {
        return service.delete(recordType, recordId);
    }

    @Override
    public ImportFailureModeRecordsResponse importFailureModeRecords(InputStream body, String recordType) {
        return service.importCsv(body, recordType);
    }
}
