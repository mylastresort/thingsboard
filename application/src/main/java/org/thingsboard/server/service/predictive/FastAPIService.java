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

import org.thingsboard.server.common.data.exception.ThingsboardException;
import org.thingsboard.server.common.data.id.PredictiveModelId;

import com.fasterxml.jackson.databind.JsonNode;

public interface FastAPIService {
    public JsonNode getHelloWorld();

    public void activatePredictiveModel(PredictiveModelId predictiveModelId) throws ThingsboardException;

    public JsonNode getAvailableModels();

    public void saveLoadModelConfig(JsonNode loadModelConfig) throws ThingsboardException;

    public JsonNode getLoadModelConfigs() throws ThingsboardException;

}
