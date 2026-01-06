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

import { QuickTimeInterval, Timewindow } from '@shared/models/time/time.models';

export enum ForecastViewType {
  FORECAST = 'forecast',
  ANOMALIES = 'anomalies',
}

export interface ForecastViewPreferences {
  selectedViews: ForecastViewType[];
  selectedSensor?: string; // Currently selected sensor for forecast chart (e.g., 'rotate', 'pressure', 'vibration', 'volt')
  hideSensorTelemetry?: boolean; // Hide sensor telemetry widget
  timewindow?: Timewindow; // Timewindow configuration for telemetry chart
  sensorColors?: { [sensorName: string]: string }; // Map of sensor names to their assigned colors
}

export const DEFAULT_VIEW_PREFERENCES: ForecastViewPreferences = {
  selectedViews: [ForecastViewType.FORECAST, ForecastViewType.ANOMALIES],
  selectedSensor: 'rotate', // Default to first sensor
  hideSensorTelemetry: false, // Show sensor telemetry by default
  timewindow: undefined, // Default to undefined timewindow
  sensorColors: {}, // Default to empty color map
};

export function parseForecastViewPreferences(
  viewPreferencesJson: string
): ForecastViewPreferences {
  try {
    if (!viewPreferencesJson) {
      return DEFAULT_VIEW_PREFERENCES;
    }

    const parsed = JSON.parse(viewPreferencesJson);
    console.log('Parsed forecast view preferences:', parsed);

    // Handle new format with selectedViews array
    if (parsed.selectedViews && Array.isArray(parsed.selectedViews)) {
      return {
        selectedViews: parsed.selectedViews.filter((view) =>
          Object.values(ForecastViewType).includes(view)
        ),
        selectedSensor: parsed.selectedSensor || DEFAULT_VIEW_PREFERENCES.selectedSensor,
        hideSensorTelemetry: parsed.hideSensorTelemetry !== undefined
          ? parsed.hideSensorTelemetry
          : DEFAULT_VIEW_PREFERENCES.hideSensorTelemetry,
        timewindow: parsed.timewindow || DEFAULT_VIEW_PREFERENCES.timewindow,
        sensorColors: parsed.sensorColors || DEFAULT_VIEW_PREFERENCES.sensorColors,
      };
    }

    return DEFAULT_VIEW_PREFERENCES;
  } catch (error) {
    console.warn('Failed to parse forecast view preferences:', error);
    return DEFAULT_VIEW_PREFERENCES;
  }
}

export function stringifyForecastViewPreferences(
  preferences: ForecastViewPreferences
): string {
  try {
    return JSON.stringify(preferences);
  } catch (error) {
    console.warn('Failed to stringify forecast view preferences:', error);
    return JSON.stringify(DEFAULT_VIEW_PREFERENCES);
  }
}

export function isForecastViewSelected(
  preferences: ForecastViewPreferences
): boolean {
  return preferences.selectedViews.includes(ForecastViewType.FORECAST);
}

export function isAnomalyViewSelected(
  preferences: ForecastViewPreferences
): boolean {
  return preferences.selectedViews.includes(ForecastViewType.ANOMALIES);
}

export function isBothViewsSelected(
  preferences: ForecastViewPreferences
): boolean {
  return (
    preferences.selectedViews.length === 2 &&
    preferences.selectedViews.includes(ForecastViewType.FORECAST) &&
    preferences.selectedViews.includes(ForecastViewType.ANOMALIES)
  );
}

export function isOnlyForecastSelected(
  preferences: ForecastViewPreferences
): boolean {
  return (
    preferences.selectedViews.length === 1 &&
    preferences.selectedViews.includes(ForecastViewType.FORECAST)
  );
}

export function isOnlyAnomaliesSelected(
  preferences: ForecastViewPreferences
): boolean {
  return (
    preferences.selectedViews.length === 1 &&
    preferences.selectedViews.includes(ForecastViewType.ANOMALIES)
  );
}
