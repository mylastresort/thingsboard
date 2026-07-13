///
/// Copyright © 2016-2024 The Thingsboard Authors
///
/// Licensed under the Apache License, Version 2.0 (the "License");
/// you may not use this file except in compliance with the License.
/// You may obtain a copy of the License at
///
///     http://www.apache.org/licenses/LICENSE-2.0
///
/// Unless required by applicable law or agreed to in writing, software
/// distributed under the License is distributed on an "AS IS" BASIS,
/// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
/// See the License for the specific language governing permissions and
/// limitations under the License.
///

// ponytail: wired against the REAL generated services — DefaultService for
// the untagged Models+Claims routes, AgenticBenchmarkService for the
// "AgenticBenchmark" tag. Only `getDevicesWithModelsCount` and
// `importAgenticBenchmarkRows` (the old CSV-import-style POST) have NO
// generated equivalent — neither endpoint exists in api-specs/openapi.yaml.
// Those two are left as direct HttpClient calls below. Everything else now
// goes through the generated client's real types (AgenticBenchmarkRow,
// AgenticBenchmarkRowRequest, AgenticBenchmarkSubset) instead of the
// hand-rolled interfaces the old service defined.

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, Subject } from 'rxjs';
import { PageData, PageLink } from '@app/shared/public-api';
import { AnomalyReport } from '@home/components/predictive-maintenance/components/anomalies/anomalies.component';
import { DefaultService, AgenticBenchmarkService  } from '@app/core/api-client';
import type {
  FailureModeHistoryResponse,
  FailureModeRecord,
  FailureModeRecordResponse,
  CreateFailureModeRecordsResponse,
  AgenticBenchmarkRow,
  AgenticBenchmarkRowRequest,
  AgenticBenchmarkSubset,
  AvailableModelOption,
  PdmSeedMachineOptions,
  PdmSeedMachineRequest,
  PdmSeedMachineResult,
} from '@app/core/api-client';

export type AvailableModelsResponse = Record<string, AvailableModelOption[]>;

export type FailureModeRecordType = 'maintenance' | 'errors' | 'failures';

@Injectable({
  providedIn: 'root',
})
export class PredictiveModelsService {
  // Not part of the OpenAPI spec (client-side push stream from the model
  // websocket service, not a REST call) — kept as-is, nothing to generate.
  anomaliesDataSubject = new Subject<AnomalyReport>();
  anomaliesData$ = this.anomaliesDataSubject.asObservable();
  anomalies = [];

  constructor(
    private api: DefaultService,
    private agenticBenchmarkApi: AgenticBenchmarkService,
    private http: HttpClient
  ) {}

  sendAnomaly(anomaly: AnomalyReport) {
    this.anomalies.push(anomaly);
    this.anomaliesDataSubject.next(anomaly);
  }

  getAvailableModels() {
    return this.api.getAvailableModels();
  }

  getLoadModelConfigs() {
    return this.api.getLoadModelConfigs();
  }

  saveLoadModelConfig(config: { [key: string]: any }) {
    return this.api.saveLoadModelConfig(config);
  }

  getPredictiveModelsByPage(pageLink: PageLink) {
    return this.api.getPredictiveModelsByPage(
      pageLink.pageSize,
      pageLink.page,
      pageLink.sortOrder?.property,
      pageLink.sortOrder?.direction as 'ASC' | 'DESC',
      pageLink.textSearch
    );
  }

  fetchHistoryPredictions(
    modelId: string,
    predictionType: string,
    startTs?: number,
    endTs?: number,
    limit: number = 100
  ) {
    return this.api.getAnomalyHistoryPredictions(modelId, predictionType, startTs, endTs, limit);
  }

  getFailureModeHistory(modelId: string, startTs?: number, endTs?: number): Observable<FailureModeHistoryResponse> {
    return this.api.getFailureModeHistory(modelId, startTs, endTs);
  }

  getAllDevicesFailureModeHistory(
    startTs?: number,
    endTs?: number,
    limit: number = 1000
  ): Observable<FailureModeHistoryResponse> {
    return this.api.getFailureModeHistoryAllDevices(startTs, endTs, limit);
  }

  createFailureModeRecord(record: FailureModeRecord) {
    return this.api.createFailureModeRecord(record);
  }

  createFailureModeRecords(records: FailureModeRecord[]) {
    return this.api.createFailureModeRecords(records);
  }

  updateFailureModeRecord(recordType: FailureModeRecordType, recordId: string, record: FailureModeRecord) {
    return this.api.updateFailureModeRecord(recordType, recordId, record);
  }

  deleteFailureModeRecord(recordType: FailureModeRecordType, recordId: string) {
    return this.api.deleteFailureModeRecord(recordType, recordId);
  }

  // NOTE: generated signature is (file, recordType) — file first, flipped
  // from the old hand-written service's (recordType, file).
  importFailureModeRecords(recordType: FailureModeRecordType, file: File) {
    return this.api.importFailureModeRecords(file, recordType);
  }

  deleteAnomalyHistoryPredictions(modelId: string, predictionType?: string) {
    return this.api.deleteAnomalyHistoryPredictions(modelId, predictionType);
  }

  // renamed in the spec: Predictive Model -> Forecast
  getPredictiveModel(forecastId: string) {
    return this.api.getForecast(forecastId);
  }

  addPredictiveModelConfig(forecast: { [key: string]: any }) {
    return this.api.createForecast(forecast);
  }

  updatePredictiveModel(forecast: { id?: string; [key: string]: any }) {
    if (!forecast?.id) {
      throw new Error('updatePredictiveModel: forecast object is missing an id');
    }
    return this.api.updateForecast(forecast.id, forecast);
  }

  deletePredictiveModel(forecastId: string) {
    return this.api.deleteForecast(forecastId);
  }

  getPredictiveModelStatus(forecastId: string) {
    return this.api.getForecastStatus(forecastId);
  }

  getForecastsByDeviceId(deviceId: string, pageSize?: number, page?: number) {
    return this.api.getForecastsByDeviceId(deviceId, pageSize, page);
  }

  getSeedMachineOptions(): Observable<PdmSeedMachineOptions> {
    return this.api.getSeedMachineOptions();
  }

  seedMachine(config: PdmSeedMachineRequest): Observable<PdmSeedMachineResult> {
    return this.api.seedMachine(config);
  }

  getAgenticBenchmarkSubsets(): Observable<AgenticBenchmarkSubset[]> {
    return this.agenticBenchmarkApi.getAgenticBenchmarkSubsets();
  }

  getAgenticBenchmarkRows(pageSize?: number, page?: number, subsetName?: string, textSearch?: string) {
    return this.agenticBenchmarkApi.getAgenticBenchmarkRows(pageSize, page, subsetName, textSearch);
  }

  createAgenticBenchmarkRow(row: AgenticBenchmarkRowRequest): Observable<AgenticBenchmarkRow> {
    return this.agenticBenchmarkApi.createAgenticBenchmarkRow(row);
  }

  updateAgenticBenchmarkRow(rowId: string, row: AgenticBenchmarkRowRequest): Observable<AgenticBenchmarkRow> {
    return this.agenticBenchmarkApi.updateAgenticBenchmarkRow(rowId, row);
  }

  deleteAgenticBenchmarkRow(rowId: string) {
    return this.agenticBenchmarkApi.deleteAgenticBenchmarkRow(rowId);
  }

  // Batch upsert exists in the spec but had no equivalent in the old
  // hand-written service — new capability, not a rename.
  upsertAgenticBenchmarkRows(rows: AgenticBenchmarkRowRequest[]) {
    return this.agenticBenchmarkApi.upsertAgenticBenchmarkRows(rows);
  }

  // --- Not yet in the OpenAPI spec — unchanged manual HTTP calls ---

  getDevicesWithModelsCount(pageLink: PageLink, withModelsOnly: boolean = false): Observable<PageData<any>> {
    const params = `${pageLink.toQuery()}&withModelsOnly=${withModelsOnly}`;
    return this.http.get<PageData<any>>(`/api/devices-with-models${params}`);
  }

  // No "import" endpoint exists in the spec (only upsertAgenticBenchmarkRows,
  // which takes rows directly rather than a file) — left pointing at the old
  // path since there's nothing generated to delegate to.
  importAgenticBenchmarkRows(): Observable<{ importedCount: number; subsetCount: number }> {
    return this.http.post<{ importedCount: number; subsetCount: number }>('/api/v1/agentic-benchmark/import', {});
  }
}

export type {
  FailureModeHistoryResponse,
  FailureModeRecord,
  FailureModeRecordResponse,
  CreateFailureModeRecordsResponse,
  AgenticBenchmarkRow,
  AgenticBenchmarkSubset,
}
