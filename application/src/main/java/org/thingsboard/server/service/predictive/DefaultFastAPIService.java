/**
 * Copyright © 2016-2024 The Thingsboard Authors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.thingsboard.server.service.predictive;

import java.time.Duration;
import java.time.temporal.ChronoUnit;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.DefaultUriBuilderFactory;
import org.thingsboard.server.common.data.exception.ThingsboardErrorCode;
import org.thingsboard.server.common.data.exception.ThingsboardException;
import org.thingsboard.server.common.data.id.PredictiveModelId;
import org.thingsboard.server.service.ws.PythonWebSocketClientService;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Service;
import lombok.extern.slf4j.Slf4j;

@Slf4j
@Service
public class DefaultFastAPIService implements FastAPIService {

    @Value("${fastapi.base.url:http://fastapi:8000/api/v1/}")
    private String baseUrl;

    private final RestTemplate restTemplate;

    @Autowired
    private PythonWebSocketClientService pythonWebSocketService;

    public DefaultFastAPIService(@Value("${fastapi.base.url:http://fastapi:8000/api/v1/}") String baseUrl) {
        this.baseUrl = baseUrl;
        this.restTemplate = new RestTemplateBuilder()
                .uriTemplateHandler(new DefaultUriBuilderFactory(baseUrl))
                .setConnectTimeout(Duration.of(15, ChronoUnit.SECONDS))
                .setReadTimeout(Duration.of(15, ChronoUnit.SECONDS))
                .build();
    }


    public JsonNode getHelloWorld() {
        return this.restTemplate.getForObject("predictiveMaintenance", JsonNode.class);
    }

    public JsonNode getAvailableModels() {
        // Calls the Python backend REST API for available models
        return this.restTemplate.getForObject("models/available", JsonNode.class);
    }

    public void activatePredictiveModel(PredictiveModelId predictiveModelId) throws ThingsboardException {
        try {
            log.info("[ACTIVATE] DefaultFastAPIService: Sending activate command for predictive model ID: {}", predictiveModelId);
            // Use unified WebSocket endpoint instead of REST
            pythonWebSocketService.sendActivateCommand(predictiveModelId);
            log.info("[ACTIVATE] DefaultFastAPIService: Activate command sent successfully for predictive model ID: {}", predictiveModelId);
        } catch (Exception e) {
            log.error("[ACTIVATE] DefaultFastAPIService: Failed to send activate command for predictive model ID: {}", predictiveModelId, e);
            throw new ThingsboardException("Failed to activate predictive model", e, ThingsboardErrorCode.GENERAL);
        }
    }

    public void saveLoadModelConfig(JsonNode loadModelConfig) throws ThingsboardException {
        try {
            log.info("[SAVE LOAD CONFIG] DefaultFastAPIService: Sending load model config to Python backend: {}", loadModelConfig);
            this.restTemplate.postForObject("models/saveLoadConfig", loadModelConfig, Void.class);
            log.info("[SAVE LOAD CONFIG] DefaultFastAPIService: Load model config sent successfully");
        } catch (Exception e) {
            log.error("[SAVE LOAD CONFIG] DefaultFastAPIService: Failed to send load model config to Python backend: {}", loadModelConfig, e);
            throw new ThingsboardException("Failed to save load model config", e, ThingsboardErrorCode.GENERAL);
        }
    }

    public JsonNode getLoadModelConfigs() throws ThingsboardException {
        try {
            log.info("[GET LOAD CONFIGS] DefaultFastAPIService: Retrieving load model configs from Python backend");
            JsonNode response = this.restTemplate.getForObject("models/loadModelConfig", JsonNode.class);
            log.info("[GET LOAD CONFIGS] DefaultFastAPIService: Load model configs retrieved successfully");
            return response;
        } catch (Exception e) {
            log.error("[GET LOAD CONFIGS] DefaultFastAPIService: Failed to retrieve load model configs from Python backend", e);
            throw new ThingsboardException("Failed to get load model configs", e, ThingsboardErrorCode.GENERAL);
        }
    }
}