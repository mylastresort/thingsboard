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
        return predictiveModelsRestService.listPredictiveModels(pageSize, page, sortProperty, sortOrder, textSearch);
    }

    @Override
    public Map<String, Object> createPredictiveModel(Map<String, Object> body) {
        return predictiveModelsRestService.createPredictiveModel(body);
    }

    @Override
    public Map<String, Object> getPredictiveModelById(String predictiveModelId) {
        return predictiveModelsRestService.getPredictiveModel(predictiveModelId);
    }

    @Override
    public Map<String, Object> updatePredictiveModelById(String predictiveModelId, Map<String, Object> body) {
        return predictiveModelsRestService.updatePredictiveModel(predictiveModelId, body);
    }

    @Override
    public Map<String, Object> deletePredictiveModelById(String predictiveModelId) {
        return predictiveModelsRestService.deletePredictiveModel(predictiveModelId);
    }

    @Override
    public Map<String, Object> getPredictiveModelStatus(String predictiveModelId) {
        return predictiveModelsRestService.getPredictiveModelStatus(predictiveModelId);
    }

    @Override
    public Map<String, Object> getPredictiveModelsByDeviceId(String deviceId, Integer pageSize, Integer page) {
        return predictiveModelsRestService.getPredictiveModelsByDeviceId(deviceId, pageSize, page);
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
