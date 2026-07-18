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

import { BaseData } from '@shared/models/base-data';
import { TenantId } from '@shared/models/id/tenant-id';
import { DeviceId } from '@shared/models/id/device-id';
import { ForecastId } from '@shared/models/id/forecast-id';
import {
  ForecastViewPreferences,
  parseForecastViewPreferences,
} from './forecast-view-preferences.models';

export enum ForecastStatus {
  INACTIVE = 'inactive',
  ACTIVE = 'active',
  PENDING = 'pending',
  FAILED = 'failed',
}

export const ForecastStatusTranslationMap = new Map<ForecastStatus, string>([
  [ForecastStatus.INACTIVE, 'forecast.status.inactive'],
  [ForecastStatus.ACTIVE, 'forecast.status.active'],
  [ForecastStatus.PENDING, 'forecast.status.pending'],
  [ForecastStatus.FAILED, 'forecast.status.failed'],
]);

export interface ForecastAttribute {
  key: string;
  aggregation?: string; // 'average', 'min', 'max'
  groupByMs?: number; // grouping interval in milliseconds
  epochs?: number; // training epochs per sensor (default 1)
}

export interface Forecast extends BaseData<ForecastId> {
  tenantId?: TenantId;
  deviceId: DeviceId;
  name: string;
  status: string;
  forecastAlgorithm?: string;
  // Grouping/scheduling option for timeseries aggregation (e.g. hourly, daily)
  forecastGrouping?: string;
  forecastStartDate?: number;
  forecastEndDate?: number;
  anomalyAlgorithm?: string;
  anomalyStartDate?: number;
  anomalyEndDate?: number;
  attributes?: ForecastAttribute[];
  viewPreferences?: string;
  additionalData?: string;
}

export interface ForecastCreate {
  name: string;
  deviceId: DeviceId;
  attributes: ForecastAttribute[];
  forecastAlgorithm: string;
  // Optional grouping/scheduling for timeseries when creating forecast
  // forecastGrouping?: string;
  anomalyAlgorithm: string;
  forecastStartDate: number;
  forecastEndDate: number;
  anomalyStartDate: number;
  anomalyEndDate: number;
  additionalData?: string;
}

export function getForecastStatusFromString(
  status: string | boolean
): ForecastStatus {
  if (typeof status === 'boolean') {
    // Handle legacy boolean active field
    return status ? ForecastStatus.ACTIVE : ForecastStatus.INACTIVE;
  }

  if (typeof status === 'string') {
    const lowerStatus = status.toLowerCase();
    switch (lowerStatus) {
      case 'active':
        return ForecastStatus.ACTIVE;
      case 'pending':
        return ForecastStatus.PENDING;
      case 'failed':
        return ForecastStatus.FAILED;
      case 'inactive':
      default:
        return ForecastStatus.INACTIVE;
    }
  }

  return ForecastStatus.INACTIVE;
}

export function getForecastStatusDisplayText(status: string | boolean): string {
  const forecastStatus = getForecastStatusFromString(status);
  return (
    ForecastStatusTranslationMap.get(forecastStatus) ||
    'forecast.status.inactive'
  );
}

export function isForecastActive(forecast: any): boolean {
  // Check both status field and legacy active field
  if (forecast.status) {
    return (
      getForecastStatusFromString(forecast.status) === ForecastStatus.ACTIVE
    );
  }
  if (forecast.active !== undefined) {
    return !!forecast.active;
  }
  return false;
}

export function isForecastInactive(forecast: any): boolean {
  if (forecast.status) {
    return (
      getForecastStatusFromString(forecast.status) === ForecastStatus.INACTIVE
    );
  }
  if (forecast.active !== undefined) {
    return !forecast.active;
  }
  return true;
}

export function isForecastPending(forecast: any): boolean {
  if (forecast.status) {
    return (
      getForecastStatusFromString(forecast.status) === ForecastStatus.PENDING
    );
  }
  return false;
}

export function isForecastFailed(forecast: any): boolean {
  if (forecast.status) {
    return (
      getForecastStatusFromString(forecast.status) === ForecastStatus.FAILED
    );
  }
  return false;
}

export function getForecastViewPreferences(
  forecast: Forecast
): ForecastViewPreferences {
  return parseForecastViewPreferences(forecast.viewPreferences || '');
}

export function setForecastViewPreferences(
  forecast: Forecast,
  preferences: ForecastViewPreferences
): void {
  forecast.viewPreferences = JSON.stringify(preferences);
}
