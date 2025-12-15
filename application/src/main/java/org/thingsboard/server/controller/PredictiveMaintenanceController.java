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

package org.thingsboard.server.controller;

import org.springframework.web.bind.annotation.RestController;
import org.thingsboard.server.queue.util.TbCoreComponent;
import org.thingsboard.server.service.predictive.FastAPIService;
import org.thingsboard.server.service.predictive.TbPredictiveModelsService;

import com.fasterxml.jackson.databind.JsonNode;

import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;

import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestBody;
import org.thingsboard.server.common.data.exception.ThingsboardErrorCode;
import org.thingsboard.server.common.data.exception.ThingsboardException;
import org.thingsboard.server.common.data.id.PredictiveModelId;
import org.thingsboard.server.common.data.id.TenantId;
import org.thingsboard.server.common.data.page.PageData;
import org.thingsboard.server.common.data.page.PageLink;
import org.thingsboard.server.common.data.PredictiveModel;
import org.thingsboard.server.config.annotations.ApiOperation;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.ResponseBody;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;

import lombok.extern.slf4j.Slf4j;

@Slf4j
@RestController
@TbCoreComponent
@RequestMapping("/api")
public class PredictiveMaintenanceController extends BaseController {

    @Autowired
    private FastAPIService fastAPIService;

    @Autowired
    protected TbPredictiveModelsService predictiveModelsService;

    @ApiOperation(value = "Get predictiveMaintenance Hello World", notes = "access the hello world in predictive maintenance route directive")
    @PreAuthorize("hasAnyAuthority('TENANT_ADMIN')")
    @GetMapping(value = "/predictiveMaintenance", produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseBody
    public JsonNode getHelloWorld() {
        return fastAPIService.getHelloWorld();
    }

    @ApiOperation(value = "Get available model types for training", notes = "Fetch available models from Python backend")
    @PreAuthorize("hasAnyAuthority('TENANT_ADMIN')")
    @GetMapping(value = "/predictiveMaintenance/availableModels", produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseBody
    public JsonNode getAvailableModels() {
        // Calls FastAPIService to fetch available models from Python backend
        return fastAPIService.getAvailableModels();
    }

    @ApiOperation(value = "Save predictive maintenance load model config", notes = "Save predictive maintenance load model configuration")
    @PreAuthorize("hasAnyAuthority('TENANT_ADMIN')")
    @PostMapping(value = "/models/saveLoadConfig", consumes = MediaType.APPLICATION_JSON_VALUE)
    @ResponseBody
    public void saveLoadModelConfig(@RequestBody JsonNode loadModelConfig) throws ThingsboardException {
        fastAPIService.saveLoadModelConfig(loadModelConfig);
    }

    @ApiOperation(value = "Load predictive maintenance model config", notes = "Load predictive maintenance model configuration")
    @PreAuthorize("hasAnyAuthority('TENANT_ADMIN')")
    @GetMapping(value = "/models/loadModelConfig", produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseBody
    public JsonNode loadModelConfig() throws ThingsboardException {
        return fastAPIService.getLoadModelConfigs();
    }

    @ApiOperation(value = "Get predictiveMaintenance models", notes = "access the predictive models in predictive maintenance route directive")
    @PreAuthorize("hasAnyAuthority('TENANT_ADMIN')")
    @GetMapping(value = "/forecasts", params = { "pageSize", "page" })
    @ResponseBody
    public PageData<PredictiveModel> getPredictiveModels(
            @Parameter(description = "The number of items to return", required = true) @RequestParam int pageSize,
            @Parameter(description = "The page number", required = true) @RequestParam int page,
            @Parameter(description = "The sort property", schema = @Schema(allowableValues = { "name", "createdTime",
                    "entityId" })) @RequestParam(required = false) String sortProperty,
            @Parameter(description = "The sort order", schema = @Schema(allowableValues = { "ASC",
                    "DESC" })) @RequestParam(required = false) String sortOrder,
            @Parameter(description = "The text search") @RequestParam(required = false) String textSearch)
            throws ThingsboardException {
        TenantId tenantId = getCurrentUser().getTenantId();
        PageLink pageLink = createPageLink(pageSize, page, textSearch, sortProperty, sortOrder);
        return checkNotNull(predictiveModelsService.findTenantPredictiveModels(tenantId, pageLink));
    }

    @ApiOperation(value = "Get predictiveMaintenance model by id", notes = "access the predictive model by id")
    @PreAuthorize("hasAnyAuthority('TENANT_ADMIN')")
    @GetMapping(value = "/forecasts/{forecastId}")
    @ResponseBody
    public PredictiveModel getPredictiveModel(
            @Parameter(description = "Predictive Model Id") @PathVariable("forecastId") String strPredictiveModelId)
            throws ThingsboardException {
        checkParameter("forecastId", strPredictiveModelId);
        PredictiveModelId predictiveModelId = new PredictiveModelId(toUUID(strPredictiveModelId));
        return checkNotNull(predictiveModelsService.findTenantPredictiveModel(getTenantId(), predictiveModelId));
    }

    @ApiOperation(value = "Get devices with predictive maintenance models count", notes = "Get all tenant devices with their associated predictive maintenance models count using left join")
    @PreAuthorize("hasAnyAuthority('TENANT_ADMIN')")
    @GetMapping(value = "/devices-with-models", params = { "pageSize", "page" })
    @ResponseBody
    public PageData<org.thingsboard.server.common.data.DeviceWithModelsCount> getDevicesWithModelsCount(
            @Parameter(description = "The number of items to return", required = true) @RequestParam int pageSize,
            @Parameter(description = "The page number", required = true) @RequestParam int page,
            @Parameter(description = "The sort property", schema = @Schema(allowableValues = { "name", "createdTime",
                    "entityId", "modelsCount" })) @RequestParam(required = false) String sortProperty,
            @Parameter(description = "The sort order", schema = @Schema(allowableValues = { "ASC",
                    "DESC" })) @RequestParam(required = false) String sortOrder,
            @Parameter(description = "The text search") @RequestParam(required = false) String textSearch,
            @Parameter(description = "Filter to show only devices with at least one model") @RequestParam(required = false, defaultValue = "false") boolean withModelsOnly)
            throws ThingsboardException {
        TenantId tenantId = getCurrentUser().getTenantId();
        PageLink pageLink = createPageLink(pageSize, page, textSearch, sortProperty, sortOrder);
        return checkNotNull(predictiveModelsService.findDevicesWithModelsCount(tenantId, pageLink, withModelsOnly));
    }

    @ApiOperation(value = "Post predictiveMaintenance model", notes = "access the predictive models in predictive maintenance route directive")
    @PreAuthorize("hasAnyAuthority('TENANT_ADMIN')")
    @PostMapping(value = "/forecasts", consumes = MediaType.APPLICATION_JSON_VALUE)
    @ResponseBody
    public PredictiveModel savePredictiveModel(@RequestBody PredictiveModel predictiveModel) throws Exception {
        TenantId tenantId = getCurrentUser().getTenantId();
        predictiveModel.setId(null);
        predictiveModel.setTenantId(tenantId);
        return checkNotNull(predictiveModelsService.save(predictiveModel, getCurrentUser()));
    }

    @ApiOperation(value = "Update predictiveMaintenance model", notes = "Update an existing predictive model including view preferences")
    @PreAuthorize("hasAnyAuthority('TENANT_ADMIN')")
    @PostMapping(value = "/forecasts/{forecastId}", consumes = MediaType.APPLICATION_JSON_VALUE)
    @ResponseBody
    public PredictiveModel updatePredictiveModel(
            @Parameter(description = "Predictive Model Id") @PathVariable("forecastId") String strPredictiveModelId,
            @RequestBody PredictiveModel predictiveModel) throws Exception {
        checkParameter("forecastId", strPredictiveModelId);
        PredictiveModelId predictiveModelId = new PredictiveModelId(toUUID(strPredictiveModelId));
        TenantId tenantId = getCurrentUser().getTenantId();

        // Ensure the predictive model ID and tenant ID are set correctly
        predictiveModel.setId(predictiveModelId);
        predictiveModel.setTenantId(tenantId);

        return checkNotNull(predictiveModelsService.save(predictiveModel, getCurrentUser()));
    }

    @ApiOperation(value = "Delete predictiveMaintenance model", notes = "access the predictive models in predictive maintenance route directive")
    @PreAuthorize("hasAnyAuthority('TENANT_ADMIN')")
    @DeleteMapping(value = "/forecasts/{forecastId}")
    @ResponseBody
    public void deletePredictiveModel(@PathVariable("forecastId") String strPredictiveModelId)
            throws ThingsboardException {
        checkParameter("forecastId", strPredictiveModelId);
        PredictiveModelId predictiveModelId = new PredictiveModelId(toUUID(strPredictiveModelId));
        predictiveModelsService.delete(new PredictiveModel(predictiveModelId), getCurrentUser());
    }
}
