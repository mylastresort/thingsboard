
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

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, Subject } from 'rxjs';

export interface AvailableModelsResponse {
  ForecastModel?: { model_name: string }[];
  AnomalyPredictor?: { model_name: string }[];
}
import { defaultHttpOptionsFromConfig, RequestConfig } from './http-utils'; // Import utility functions if available
import { PageData, PageLink } from '@app/shared/public-api';
import { Order } from '@app/modules/home/models/predictive-maintenance.models';
import { Forecast, ForecastCreate } from '@app/shared/models/forecast.models';
import { AnomalyReport } from '@app/modules/home/components/predictive-maintenance/components/anomalies/anomalies.component';
// import { Order } from '../components/forecast/forcast-page.component'; // Adjust import path as needed

@Injectable({
  providedIn: 'root',
})
export class PredictiveModelsService {
  anomaliesDataSubject = new Subject<AnomalyReport>();
  anomaliesData$ = this.anomaliesDataSubject.asObservable();
  anomalies = [];

  sendAnomaly(anomaly: AnomalyReport) {
    this.anomalies.push(anomaly);
    this.anomaliesDataSubject.next(anomaly);
  }

  /**
   * Fetch available model types and algorithms from backend
   * @returns Observable with available models structure
   */
  getAvailableModels(): Observable<AvailableModelsResponse> {
    return this.http.get<AvailableModelsResponse>('/api/predictive-maintenance/availableModels');
  }

  getLoadModelConfigs(): Observable<any> {
    return this.http.get<any>('/api/models/loadModelConfig', {});
  }

  saveLoadModelConfig(config: any): Observable<any> {
    return this.http.post<any>('/api/models/saveLoadConfig', config, {});
  }

  private baseUrl = '/api/forecasts'; // Base URL for your API

  private baseUrlModels = '/api/models'; // Base URL for your API

  constructor(private http: HttpClient) {}

  // Fetch forecasts with pagination (PageLink handling like in DeviceService)
  getPredictiveModelsByPage(
    pageLink: PageLink,
    config?: RequestConfig
  ): Observable<PageData<any>> {
    return this.http.get<PageData<Order>>(
      `${this.baseUrl}${pageLink.toQuery()}`,
      defaultHttpOptionsFromConfig(config)
    );
  }

  /**
   * Fetch anomaly history predictions from the database.
   *
   * @param modelId - Model ID (predictive_maintenance_config UUID)
   * @param predictionType - Prediction type: 'Anomaly', 'Forecast', or 'Failure'
   * @param startTs - Optional start timestamp in milliseconds
   * @param endTs - Optional end timestamp in milliseconds
   * @param limit - Maximum number of records (default: 100)
   * @param config - Optional HTTP request config
   * @returns Observable with predictions array and totalCount
   */
  fetchHistoryPredictions(
    modelId: string,
    predictionType: string,
    startTs?: number,
    endTs?: number,
    limit: number = 100,
    config?: RequestConfig
  ): Observable<{ predictions: any[]; totalCount: number; limit: number }> {
    // Build query parameters
    let params = `limit=${limit}`;
    if (startTs) {
      params += `&startTs=${startTs}`;
    }
    if (endTs) {
      params += `&endTs=${endTs}`;
    }

    return this.http.get<{ predictions: any[]; totalCount: number; limit: number }>(
      `${this.baseUrlModels}/anomaly-history-predictions/${modelId}/${predictionType}?${params}`,
      defaultHttpOptionsFromConfig(config)
    );
  }

  deleteAnomalyHistoryPredictions(
    modelId: string,
    predictionType?: string,
    config?: RequestConfig
  ): Observable<{ deletedCount: number; message: string }> {
    // Build query parameters
    let params = '';
    if (predictionType) {
      params = `?predictionType=${predictionType}`;
    }

    return this.http.delete<{ deletedCount: number; message: string }>(
      `${this.baseUrlModels}/anomaly-history-predictions/${modelId}${params}`,
      defaultHttpOptionsFromConfig(config)
    );
  }

  // Fetch a specific predictive model by its ID
  getPredictiveModel(
    forecastId: string,
    config?: RequestConfig
  ): Observable<Forecast> {
    return this.http.get<Forecast>(
      `${this.baseUrl}/${forecastId}`,
      defaultHttpOptionsFromConfig(config)
    );
  }

  // Save a new predictive model
  addPredictiveModelConfig(
    forecast: ForecastCreate,
    config?: RequestConfig
  ): Observable<Forecast> {
    return this.http.post<Forecast>(
      `${this.baseUrl}`,
      forecast,
      defaultHttpOptionsFromConfig(config)
    );
  }

  // Update an existing predictive model
  updatePredictiveModel(forecast: any, config?: RequestConfig): Observable<Forecast> {
    const forecastId = forecast.id?.id || forecast.id;
    return this.http.post<Forecast>(
      `${this.baseUrl}/${forecastId}`,
      forecast,
      defaultHttpOptionsFromConfig(config)
    );
  }

  // Activate a predictive model
  activatePredictiveModel(
    forecastId: string,
    config?: RequestConfig
  ): Observable<void> {
    return this.http.patch<void>(
      `${this.baseUrl}/${forecastId}/activate`,
      {},
      defaultHttpOptionsFromConfig(config)
    );
  }

  // Delete a predictive model by its ID
  deletePredictiveModel(forecastId: string, config?: RequestConfig): Observable<void> {
    return this.http.delete<void>(
      `${this.baseUrl}/${forecastId}`,
      defaultHttpOptionsFromConfig(config)
    );
  }

  getPredictiveModelStatus(
    forecastId: string,
    config?: RequestConfig
  ): Observable<{ forecast_id: string; status: string }> {
    return this.http.get<{ forecast_id: string; status: string }>(
      `${this.baseUrl}/${forecastId}/status`,
      defaultHttpOptionsFromConfig(config)
    );
  }

  // Fetch forecasts by device ID
  getForecastsByDeviceId(
    deviceId: string,
    config?: RequestConfig
  ): Observable<PageData<any>> {
    return this.http.get<PageData<any>>(
      `${this.baseUrl}/device/${deviceId}`,
      defaultHttpOptionsFromConfig(config)
    );
  }

  // Fetch devices with their predictive maintenance models count
  getDevicesWithModelsCount(
    pageLink: PageLink,
    withModelsOnly: boolean = false,
    config?: RequestConfig
  ): Observable<PageData<any>> {
    const params = `${pageLink.toQuery()}&withModelsOnly=${withModelsOnly}`;
    return this.http.get<PageData<any>>(
      `/api/devices-with-models${params}`,
      defaultHttpOptionsFromConfig(config)
    );
  }
}
