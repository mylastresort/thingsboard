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

import {
  Component,
  Input,
  OnInit,
  OnDestroy,
  AfterViewInit,
  OnChanges,
  SimpleChanges,
  ViewChild,
  ElementRef,
  ChangeDetectorRef,
  NgZone,
  Output,
  EventEmitter
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { SharedModule } from '@shared/shared.module';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import * as echarts from 'echarts/core';
import {
  TitleComponent,
  ToolboxComponent,
  TooltipComponent,
  GridComponent,
  DataZoomComponent,
  LegendComponent
} from 'echarts/components';
import { LineChart } from 'echarts/charts';
import { UniversalTransition } from 'echarts/features';
import { CanvasRenderer } from 'echarts/renderers';
import { Observable, Subscription } from 'rxjs';
import { filter, tap } from 'rxjs/operators';
import { TelemetryWebsocketService } from '@core/ws/telemetry-websocket.service';
import { TelemetrySubscriber, SubscriptionUpdate, LatestTelemetry, DataSortOrder } from '@shared/models/telemetry/telemetry.models';
import { EntityId } from '@shared/models/id/entity-id';
import { EntityType } from '@shared/models/entity-type.models';
import { TranslateService } from '@ngx-translate/core';
import { ECharts, echartsModule } from '@home/components/widget/lib/chart/echarts-widget.models';
import { AttributeService } from '@core/http/attribute.service';
import { Timewindow, QuickTimeInterval, AggregationType } from '@shared/models/time/time.models';
import { PredictiveModelsService } from '@app/core/http/forecast.service';
import { startCase } from 'lodash';
import { ForecastAttribute } from '@app/shared/models/forecast.models';
import { ForecastViewPreferences } from '@app/shared/models/forecast-view-preferences.models';

// Types for forecast prediction logs
interface LogEntry {
  type?: string;
  level?: string;
  message: any;
  timestamp?: string;
  source?: string;
}

interface ForecastPredictionLogEntry extends LogEntry {
  message: ForecastPredictionLogEntryMessage;
}

interface ForecastPredictionLogEntryMessage {
  device_id: string;
  iteration: number;
  prediction_type: string;
  recent_point_ts?: number;
  sensor?: string;
  result: ForecastSensorPrediction;
}

interface ForecastSensorPrediction {
  prediction_info?: {
    group_by_period_ms: number;
    recent_point_ts: number;
  };
  forecast?: number[];
  timestamp?: number[];
}

// Register ECharts components
echarts.use([
  TitleComponent,
  ToolboxComponent,
  TooltipComponent,
  GridComponent,
  DataZoomComponent,
  LegendComponent,
  LineChart,
  UniversalTransition,
  CanvasRenderer
]);

@Component({
  selector: 'tb-time-series-telemetry',
  templateUrl: './time-series-telemetry.component.html',
  styleUrls: ['./time-series-telemetry.component.scss'],
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    SharedModule,
    MatIconModule,
    MatButtonModule,
    MatMenuModule,
    MatTooltipModule
  ]
})
export class TimeSeriesTelemetryComponent implements OnInit, OnDestroy, AfterViewInit, OnChanges {
  @Input() timewindow: Timewindow;

  @Output() timewindowChange = new EventEmitter<Timewindow>();

  @ViewChild('chart', { static: false }) chartElement: ElementRef<HTMLElement>;

  @Input() deviceId: string;

  @Input() selectedSensor: string; // Single sensor - can be provided explicitly or auto-selected

  @Input() title = 'Sensor Telemetry';

//
  @Input() forecastData: any; // Forecast data passed from parent component

  @Input() forecastMaxSteps: number; // Number of forecast steps

  @Input() attributes: ForecastAttribute[]; // Predictive model attributes only

  @Input() modelId: string; // Model ID for fetching historical predictions

  @Input() forecastHistoryPoint$: EventEmitter<{ sensor: string; timestamp: number; value: number }>; // Real-time forecast history points

  @Output() sensorChanged = new EventEmitter<string>();

  @Input() historyPredictions: any;

  @Input() viewPreferences: ForecastViewPreferences; // View preferences including sensor colors

  @Output() viewPreferencesChange = new EventEmitter<ForecastViewPreferences>();

  // Observable stream of logs from the parent component (model websocket)
  @Input() logsObservable: Observable<LogEntry>;

  // Available sensors fetched from device
  availableSensors: string[] = [];

  // Subscription for real-time forecast history points
  private forecastHistorySubscription: Subscription;

  // Subscription for forecast prediction logs
  private forecastPredictionLogsSubscription: Subscription;

  // Track if sensor was explicitly provided vs auto-selected
  private sensorExplicitlyProvided = false;

  // Forecast data points for the chart
  private forecastDataPoints: Array<[number, number]> = [];

  private historyForecastDataPoints: Array<[number, number]> = [];

  private chart: ECharts;

  private chartOptions: any;

  private telemetrySubscription: Subscription;

  private timeAxisUpdateInterval: any;

  private resizeObserver: ResizeObserver;

  private windowResizeHandler = () => {
    if (this.chart) {
      this.chart.resize();
    }
  };

  // Wheel handler - stop ECharts from handling scroll when Ctrl is not held
  private chartWheelHandler = (event: WheelEvent) => {
    if (!event.ctrlKey) {
      // Stop propagation so ECharts doesn't capture it, allow page scroll
      event.stopPropagation();
    }
  };

  // Data storage - array of [timestamp, value] for the selected sensor
  private telemetryData: Array<[number, number]> = [];

  // Chart colors for different sensors - dynamically assigned
  private sensorColors: Map<string, string> = new Map();

  // Reserved colors for forecast and predictions series - DO NOT use for telemetry
  public static readonly FORECAST_COLOR = '#ff9800'; // Orange - used for Forecast series
  public static readonly PREDICTIONS_COLOR = '#4caf50'; // Green - used for Predictions (history forecast) series
  private static readonly RESERVED_COLORS = [
    TimeSeriesTelemetryComponent.FORECAST_COLOR,
    TimeSeriesTelemetryComponent.PREDICTIONS_COLOR
  ];

  // Full color palette (before filtering reserved colors)
  private static readonly FULL_COLOR_PALETTE: string[] = [
    '#2196f3', // Blue
    '#f44336', // Red
    '#9c27b0', // Purple
    '#00bcd4', // Cyan
    '#ffeb3b', // Yellow
    '#e91e63', // Pink
    '#009688', // Teal
    '#ff5722', // Deep Orange
    '#673ab7', // Deep Purple
    '#3f51b5', // Indigo
    '#cddc39', // Lime
    '#ffc107', // Amber
    '#795548', // Brown
    '#607d8b', // Blue Grey
    '#8bc34a', // Light Green
    '#03a9f4', // Light Blue
    '#ff6f00', // Amber Dark
    '#d32f2f'  // Red Dark
  ];

  // Color palette for sensor assignment (excludes reserved colors)
  private colorPalette: string[] = TimeSeriesTelemetryComponent.FULL_COLOR_PALETTE.filter(
    color => !TimeSeriesTelemetryComponent.RESERVED_COLORS.includes(color)
  );

  // Public color palette for UI selection (excludes reserved colors to prevent conflicts)
  public availableColors: string[] = TimeSeriesTelemetryComponent.FULL_COLOR_PALETTE.filter(
    color => !TimeSeriesTelemetryComponent.RESERVED_COLORS.includes(color)
  );

  constructor(
    private telemetryWsService: TelemetryWebsocketService,
    private attributeService: AttributeService,
    private predictiveModelsService: PredictiveModelsService,
    private translate: TranslateService,
    private zone: NgZone,
    private cdr: ChangeDetectorRef
  ) { }

  ngOnInit(): void {
    // Initialize empty data array
    this.telemetryData = [];

    // Track if sensor was explicitly provided
    this.sensorExplicitlyProvided = !!this.selectedSensor;
  }

  processHistoryPredictions(): void {
    // same as processForecastData but for historyPredictions
    console.log(
      '[TIME-SERIES] Processing history predictions for sensor:',
      this.selectedSensor,
    );
    if (typeof this.selectedSensor == 'string'
      && typeof this.historyPredictions == 'object' && this.historyPredictions.sensor_name === this.selectedSensor) {
      const forecast = this.historyPredictions.forecast;
      const timestamp =
        this.historyPredictions.prediction_info.recent_point_ts + this.historyPredictions.prediction_info.group_by_period_ms;
      this.historyForecastDataPoints = this.historyForecastDataPoints.concat([[timestamp, forecast]]);
      this.historyForecastDataPoints.sort((a, b) => a[0] - b[0]);
      console.log(
        `[TIME-SERIES] ✓ Loaded ${this.historyForecastDataPoints.length} history forecast points for sensor ${this.selectedSensor}`,
      );
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
        // Update availableSensors if attributes input changes
        if (changes.attributes && Array.isArray(this.attributes)) {
          this.availableSensors = this.attributes.map(attr => attr.key);
          this.assignColorsToSensors();
          // Only auto-select if sensor was NOT explicitly provided via @Input
          if (!this.sensorExplicitlyProvided && !this.selectedSensor && this.availableSensors.length > 0) {
            this.selectedSensor = this.availableSensors[0];
            this.sensorChanged.emit(this.selectedSensor);
          }
          this.cdr.detectChanges();
        }

    // Handle viewPreferences changes (e.g., sensor colors updated)
    if (changes.viewPreferences && !changes.viewPreferences.firstChange) {
      this.assignColorsToSensors();
      if (this.chart) {
        this.updateChart();
      }
    }

    if (changes.deviceId && !changes.deviceId.firstChange) {
      // Device changed - fetch sensors and resubscribe
      if (this.telemetrySubscription) {
        this.telemetrySubscription.unsubscribe();
      }
      this.clearData();
      this.forecastDataPoints = [];
      if (this.deviceId && this.selectedSensor) {
        this.getSensorData();
        // Also fetch history predictions for the new device
        if (this.modelId) {
          this.fetchSensorForecastHistoryPredictions();
        }
      }
    }

    if (changes.selectedSensor && !changes.selectedSensor.firstChange) {
      // Sensor was explicitly changed - mark it as explicitly provided
      this.sensorExplicitlyProvided = !!this.selectedSensor;

      // Sensor changed - resubscribe
      if (this.telemetrySubscription) {
        this.telemetrySubscription.unsubscribe();
      }
      this.clearData();
      if (this.deviceId && this.selectedSensor) {
        // this.subscribeToTelemetry();
        this.getSensorData();
      }

      // Fetch saved forecast predictions for the new sensor
      if (this.modelId && this.selectedSensor) {
        this.fetchSensorForecastHistoryPredictions();
      }
    }

    if (changes.historyPredictions) {
      this.processHistoryPredictions();
    }

    if (changes.modelId && !changes.modelId.firstChange) {
      if (this.modelId && this.selectedSensor) {
        this.fetchSensorForecastHistoryPredictions();
      }
    }

    // Handle logsObservable changes - subscribe to forecast predictions
    if (changes.logsObservable && this.logsObservable) {
      this.subscribeToForecastPredictions();
      
      // Also fetch historical predictions when logsObservable becomes available
      // This handles the case when the component is initialized with an active model
      if (this.modelId && this.selectedSensor && this.historyForecastDataPoints.length === 0) {
        this.fetchSensorForecastHistoryPredictions();
      }
    }

    if (changes.forecastData) {
      console.log('[ngOnChanges] changes.forecastData', changes.forecastData);
      this.processSensorForecastData();
    }

    if (this.chart) {
      this.updateChart();
    }
  }

  ngAfterViewInit(): void {
    // Initialize ECharts
    this.initializeChart();

    // Fetch telemetry data if device ID and sensor are available
    if (this.deviceId && this.selectedSensor) {
      this.getSensorData();
    }

    // Process forecast data if available
    if (this.forecastData) {
      this.processSensorForecastData();
    }

    // Fetch saved forecast predictions if model ID is available
    if (this.modelId && this.selectedSensor) {
      this.fetchSensorForecastHistoryPredictions();
    }

    // Subscribe to real-time forecast history points
    if (this.forecastHistoryPoint$) {
      this.subscribeToForecastHistory();
    }

    // Listen to window resize events to trigger chart resize
    window.addEventListener('resize', this.windowResizeHandler);

    // Start time axis update interval (update every second)
    this.startTimeAxisUpdate();

    // Setup resize observer to handle window/container resize
    this.setupResizeObserver();
  }

  ngOnDestroy(): void {
    if (this.telemetrySubscription) {
      this.telemetrySubscription.unsubscribe();
    }
    if (this.forecastHistorySubscription) {
      this.forecastHistorySubscription.unsubscribe();
    }
    if (this.forecastPredictionLogsSubscription) {
      this.forecastPredictionLogsSubscription.unsubscribe();
    }
    if (this.timeAxisUpdateInterval) {
      clearInterval(this.timeAxisUpdateInterval);
    }
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
    }
    if (this.chart) {
      this.chart.dispose();
    }

    // Remove window resize event listener
    window.removeEventListener('resize', this.windowResizeHandler);

    // Remove chart wheel event listener
    if (this.chartElement?.nativeElement) {
      this.chartElement.nativeElement.removeEventListener('wheel', this.chartWheelHandler, true);
    }
  }

  private initializeChart(): void {
    if (!this.chartElement?.nativeElement) {
      return;
    }

    // Initialize ECharts module
    echartsModule.init();

    // Create chart instance
    this.chart = echarts.init(this.chartElement.nativeElement, null, {
      renderer: 'canvas'
    });

    // Add wheel event listener in capture phase to intercept before ECharts
    this.chartElement.nativeElement.addEventListener('wheel', this.chartWheelHandler, true);

    // Define chart options
    this.chartOptions = {
      darkMode: true,
      backgroundColor: 'transparent',
      animation: false,
      title: {
        text: startCase(this.selectedSensor) + ' Data',
        left: 'center',
        textStyle: {
          color: '#fff',
          fontSize: 16
        }
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'cross'
        },
        formatter: (params: any) => {
          if (!params || params.length === 0) {
            return '';
          }
          const timestamp = params[0].value[0];
          const date = new Date(timestamp);
          let html = `<div style="font-weight: bold;">${date.toLocaleString()}</div>`;
          params.forEach((param: any) => {
            const value = param.value[1];
            html += `<div style="color: ${param.color};">
              ${param.seriesName}: ${value !== null && value !== undefined ? value.toFixed(2) : 'N/A'}
            </div>`;
          });
          return html;
        }
      },
      legend: {
        data: [this.selectedSensor],
        top: 40,
        textStyle: {
          color: '#fff'
        }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '15%',
        top: '20%',
        containLabel: true
      },
      xAxis: {
        type: 'time',
        boundaryGap: false,
        scale: true,
        axisLabel: {
          color: '#fff',
          formatter: (value: number, index: number) => {
            const date = new Date(value);

            // Calculate time range in milliseconds
            const timeRange = this.timewindow.realtime
              ? this.timewindow.realtime.timewindowMs || 60000
              : (this.timewindow.history?.timewindowMs || 3600000);

            // Determine format based on time range
            if (timeRange < 3600000) {
              // Less than 1 hour - show HH:MM:SS
              const hours = date.getHours().toString().padStart(2, '0');
              const minutes = date.getMinutes().toString().padStart(2, '0');
              const seconds = date.getSeconds().toString().padStart(2, '0');
              return `${hours}:${minutes}:${seconds}`;
            } else if (timeRange < 86400000) {
              // Less than 1 day - show HH:MM
              const hours = date.getHours().toString().padStart(2, '0');
              const minutes = date.getMinutes().toString().padStart(2, '0');
              return `${hours}:${minutes}`;
            } else if (timeRange < 2592000000) {
              // Less than 30 days - show MMM DD HH:mm
              const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
              const month = months[date.getMonth()];
              const day = date.getDate();
              const hours = date.getHours().toString().padStart(2, '0');
              const minutes = date.getMinutes().toString().padStart(2, '0');
              return `${month} ${day}\n${hours}:${minutes}`;
            } else {
              // More than 30 days - show MMM DD
              const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
              const month = months[date.getMonth()];
              const day = date.getDate();
              return `${month} ${day}`;
            }
          },
          interval: 'auto',
          hideOverlap: true
        },
        axisLine: {
          lineStyle: {
            color: '#fff'
          }
        }
      },
      yAxis: {
        type: 'value',
        name: this.selectedSensor,
        nameTextStyle: {
          color: '#fff'
        },
        axisLabel: {
          color: '#fff'
        },
        axisLine: {
          lineStyle: {
            color: '#fff'
          }
        },
        splitLine: {
          lineStyle: {
            color: 'rgba(255, 255, 255, 0.1)'
          }
        }
      },
      dataZoom: [
        {
          type: 'inside',
          start: 0,
          end: 100,
          zoomOnMouseWheel: true,
          moveOnMouseMove: true,
          moveOnMouseWheel: false
        },
        {
          type: 'slider',
          start: 0,
          end: 100,
          height: 30,
          bottom: 10,
          textStyle: {
            color: '#fff'
          },
          handleStyle: {
            color: '#2196f3'
          },
          borderColor: '#fff'
        }
      ],
      series: this.createSeries()
    };

    // Set initial options
    this.chart.setOption(this.chartOptions);
  }

  private createSeries(): any[] {
    if (!this.selectedSensor) {
      return [];
    }

    return [{
      name: this.selectedSensor,
      type: 'line',
      data: [],
      smooth: false,
      symbol: 'circle',
      symbolSize: 4,
      lineStyle: {
        width: 2,
        color: this.sensorColors.get(this.selectedSensor) || '#2196f3'
      },
      itemStyle: {
        color: this.sensorColors.get(this.selectedSensor) || '#2196f3'
      }
    }];
  }

  private assignColorsToSensors(): void {
    return;
    // First, load colors from view preferences if available
    if (this.viewPreferences?.sensorColors) {
      Object.entries(this.viewPreferences.sensorColors).forEach(([sensor, color]) => {
        if (this.availableSensors.includes(sensor)) {
          this.sensorColors.set(sensor, color);
        }
      });
    }

    // Assign colors to sensors that don't have colors yet
    let hasNewColors = false;
    this.availableSensors.forEach((sensor, index) => {
      if (!this.sensorColors.has(sensor)) {
        // Assign color from palette, cycling through if we run out
        const color = this.colorPalette[index % this.colorPalette.length];
        this.sensorColors.set(sensor, color);
        hasNewColors = true;
      }
    });

    // If new colors were assigned, emit the updated view preferences
    if (hasNewColors && this.viewPreferences) {
      this.emitSensorColorsUpdate();
    }
  }

  private emitSensorColorsUpdate(): void {
    // Convert Map to object for serialization
    const sensorColorsObj: { [key: string]: string } = {};
    this.sensorColors.forEach((color, sensor) => {
      sensorColorsObj[sensor] = color;
    });

    // Emit updated view preferences with sensor colors
    const updatedPreferences: ForecastViewPreferences = {
      ...this.viewPreferences,
      sensorColors: sensorColorsObj,
    };
    this.viewPreferencesChange.emit(updatedPreferences);
  }

  /**
   * Get the current color for a sensor
   */
  getSensorColor(sensor: string): string {
    return this.sensorColors.get(sensor) || this.colorPalette[0];
  }

  /**
   * Update sensor color and save to preferences
   */
  updateSensorColor(sensor: string, color: string): void {
    this.sensorColors.set(sensor, color);
    this.emitSensorColorsUpdate();
    
    // Update chart if it exists
    if (this.chart) {
      this.updateChart();
    }
  }

  private fetchAvailableSensors(): void {

    // No-op: handled in ngOnChanges

    // Assign colors to sensors
    this.assignColorsToSensors();

    // Only auto-select if sensor was NOT explicitly provided via @Input
    if (!this.sensorExplicitlyProvided && !this.selectedSensor && this.availableSensors.length > 0) {
      this.selectedSensor = this.availableSensors[0];
      this.sensorChanged.emit(this.selectedSensor);
    }

    this.cdr.detectChanges();
  }

  private subscribeToTelemetry(): void {
    if (!this.deviceId || !this.selectedSensor) {
      return;
    }

    // Create entity ID
    const entityId: EntityId = {
      entityType: EntityType.DEVICE,
      id: this.deviceId
    };

    // Create telemetry subscriber for latest telemetry
    const subscriber = TelemetrySubscriber.createEntityAttributesSubscription(
      this.telemetryWsService,
      entityId,
      LatestTelemetry.LATEST_TELEMETRY,
      this.zone,
      [this.selectedSensor] // Pass as array with single sensor
      // this.attributes.map(attr => attr.key) // Subscribe to all attributes
    );

    // Subscribe to data updates
    this.telemetrySubscription = subscriber.data$.subscribe((update: SubscriptionUpdate) => {
      this.handleTelemetryUpdate(update);
    });

    // Start the subscription with the telemetry service
    this.telemetryWsService.subscribe(subscriber);
  }

  private subscribeToForecastHistory(): void {
    if (!this.forecastHistoryPoint$) {
      return;
    }

    // Subscribe to real-time forecast history points
    this.forecastHistorySubscription = this.forecastHistoryPoint$.subscribe((point) => {
      // Only add points for the currently selected sensor
      if (point.sensor === this.selectedSensor) {
        // Add the new forecast history point
        this.forecastDataPoints.push([point.timestamp, point.value]);

        // Sort by timestamp
        this.forecastDataPoints.sort((a, b) => a[0] - b[0]);

        // filter points within time window
        const { minTime, maxTime } = this.calculateTimeWindow();
        this.forecastDataPoints = this.forecastDataPoints.filter(
          p => p[0] >= minTime && p[0] <= maxTime
        );

        // Update the chart
        if (this.chart) {
          this.updateChart();
        }
      }
    });
  }

  /**
   * Subscribe to forecast prediction logs from the websocket
   */
  private subscribeToForecastPredictions(): void {
    if (!this.logsObservable) {
      console.log('[TIME-SERIES] No logsObservable available for forecast predictions');
      return;
    }

    // Unsubscribe from previous subscription if it exists
    if (this.forecastPredictionLogsSubscription) {
      this.forecastPredictionLogsSubscription.unsubscribe();
    }

    console.log('[TIME-SERIES] Subscribing to forecast prediction logs for sensor:', this.selectedSensor);

    // Filter logs for forecast predictions only
    const forecastPredictionLogs$ = this.logsObservable.pipe(
      filter((log: LogEntry) =>
        log.level && log.level.toLowerCase() === 'prediction' &&
        (log.type && log.type.toLowerCase() === 'forecast') || 
        (log.source && log.source.toLowerCase() === 'forecastmodel')
      ),
      tap((log) => {
        console.log('[TIME-SERIES] Processing forecast log entry:', log);
        if (typeof log.message !== 'string') {
          const msg = log.message as any;
          console.log('[TIME-SERIES] Recent point timestamp:', msg?.recent_point_ts);
        }
      })
    ) as Observable<ForecastPredictionLogEntry>;

    // Subscribe to forecast prediction logs
    this.forecastPredictionLogsSubscription = forecastPredictionLogs$.subscribe(log => {
      console.log('[TIME-SERIES] Received forecast prediction log:', log.message.prediction_type);

      if (log.message.prediction_type === 'forecast') {
        const results = log.message.result as ForecastSensorPrediction;
        
        if (results) {
          // Extract prediction_info for calculating forecast points
          const predictionInfo = (results as any).prediction_info;
          const recentPointTs = predictionInfo?.recent_point_ts;
          const groupByPeriodMs = predictionInfo?.group_by_period_ms;
          const sensorName: string = (log.message as any).sensor;
          const forecast: number[] = (results as any).forecast;

          console.log('[TIME-SERIES] Forecast data:', {
            predictionInfo,
            recentPointTs,
            groupByPeriodMs,
            sensorName,
            forecast,
            selectedSensor: this.selectedSensor
          });

          // Only process if this is for the current sensor
          if (sensorName === this.selectedSensor) {
            // Before replacing forecastDataPoints, move the first point of the current forecast to historyForecastDataPoints
            // This preserves historical predictions on the chart
            if (this.forecastDataPoints && this.forecastDataPoints.length > 0) {
              const firstForecastPoint = this.forecastDataPoints[0];
              // Check if this point is not already in historyForecastDataPoints
              const alreadyExists = this.historyForecastDataPoints.some(
                point => point[0] === firstForecastPoint[0]
              );
              if (!alreadyExists) {
                this.historyForecastDataPoints.push(firstForecastPoint);
                this.historyForecastDataPoints.sort((a, b) => a[0] - b[0]);
                console.log('[TIME-SERIES] Moved previous forecast first point to history:', firstForecastPoint);
              }
            }

            this.forecastDataPoints = forecast.map((value, i) => 
              [recentPointTs + (i + 2) * groupByPeriodMs, value]
            );
            
            console.log('[TIME-SERIES] Updated forecast points:', this.forecastDataPoints.length);
            
            // Update the chart
            if (this.chart) {
              this.updateChart();
            }
            
            this.cdr.detectChanges();
          }
        } else {
          console.warn('[TIME-SERIES] No forecast results to process');
        }
      } else if (log.message.prediction_type === 'history') {
        // Historical forecast prediction - add to historyForecastDataPoints
        console.log('[TIME-SERIES] Processing historical forecast prediction log:', log);
        
        const results = log.message.result as ForecastSensorPrediction;
        if (results) {
          const predictionInfo = (results as any).prediction_info;
          const recentPointTs = predictionInfo?.recent_point_ts;
          const groupByPeriodMs = predictionInfo?.group_by_period_ms;
          const sensorName: string = (log.message as any).sensor;
          const forecastValue: number = (results as any).forecast;

          // Only process if this is for the current sensor
          if (sensorName === this.selectedSensor && recentPointTs && groupByPeriodMs) {
            const historyTimestamp = recentPointTs + groupByPeriodMs;
            
            // Check if this point is not already in historyForecastDataPoints
            const alreadyExists = this.historyForecastDataPoints.some(
              point => point[0] === historyTimestamp
            );
            
            if (!alreadyExists) {
              this.historyForecastDataPoints.push([historyTimestamp, forecastValue]);
              this.historyForecastDataPoints.sort((a, b) => a[0] - b[0]);
              console.log('[TIME-SERIES] Added history forecast point:', [historyTimestamp, forecastValue]);
              
              // Update the chart
              if (this.chart) {
                this.updateChart();
              }
              
              this.cdr.detectChanges();
            }
          }
        }
      }
    });
  }

  private processSensorForecastData(): void {
    if (!this.forecastData || !this.selectedSensor) {
      // console.log('[TIME-SERIES] No forecast data or sensor selected');
      this.forecastDataPoints = [];
      return;
    }

    // console.log('[TIME-SERIES] Processing forecast data for sensor:', this.selectedSensor);
    // console.log('[TIME-SERIES] Available sensors in forecast:', Object.keys(this.forecastData));

    // Get forecast data for the selected sensor
    if (this.forecastData[this.selectedSensor]) {
      const sensorForecast = this.forecastData[this.selectedSensor];
      // console.log('[TIME-SERIES] Sensor forecast data:', sensorForecast);

      // Convert forecast data to [timestamp, value] format
      if (sensorForecast.forecast && sensorForecast.timestamp) {
        const forecastDataPoints = sensorForecast.timestamp.map((ts: number, index: number) =>
          [ts, sensorForecast.forecast[index]]);

        this.forecastDataPoints = forecastDataPoints;

        // console.log(`[TIME-SERIES] ✓ Loaded ${this.forecastDataPoints.length} forecast points for sensor ${this.selectedSensor}`);
        // console.log('[TIME-SERIES] First few points:', this.forecastDataPoints.slice(0, 3));
      } else {
        console.warn(`[TIME-SERIES] Sensor forecast missing 'forecast' or 'timestamp' fields:`, sensorForecast);
        this.forecastDataPoints = [];
      }
    } else {
      console.warn(`[TIME-SERIES] No forecast data found for sensor: ${this.selectedSensor}`);
      console.warn('[TIME-SERIES] Available sensors in forecast data:', Object.keys(this.forecastData));
      this.forecastDataPoints = [];
    }

    this.updateChart();

    this.cdr.detectChanges();
  }

  /**
   * Fetch saved forecast predictions from database and display on chart
   */
  private fetchSensorForecastHistoryPredictions(): void {
    // return;
    if (!this.modelId || !this.selectedSensor) {
      console.log('[TIME-SERIES] Cannot fetch forecast history: missing modelId or selectedSensor');
      return;
    }

    console.log(`[TIME-SERIES] Fetching forecast history for model ${this.modelId}, sensor ${this.selectedSensor}`);

    const { minTime, maxTime } = this.calculateTimeWindow();

    const startTs = minTime;
    const endTs = maxTime;

    this.predictiveModelsService.fetchHistoryPredictions(
      this.modelId,
      'Forecast',
      startTs,
      endTs,
      100 // Limit to 100 predictions
    ).subscribe({
      next: (response) => {
        // console.log('[TIME-SERIES] Received forecast history response:', response);

        if (!response.predictions || response.predictions.length === 0) {
          // console.log('[TIME-SERIES] No saved predictions found');
          return;
        }

        // Process each saved prediction
        // NEW STRUCTURE: Each prediction is now for a SINGLE SENSOR
        const savedForecastPoints: Array<[number, number]> = [];

        response.predictions.forEach((prediction) => {
          try {
            const predictionValue = prediction.predictionValue;

            // Check if this prediction is for the selected sensor
            const sensorName = predictionValue.sensor_name;
            if (sensorName !== this.selectedSensor) {
              // This prediction is for a different sensor, skip it
              return;
            }

            // Extract prediction_info which contains recent_point_ts and group_by_period_ms
            const predictionInfo = predictionValue.prediction_info;
            if (!predictionInfo) {
              console.warn('[TIME-SERIES] Prediction missing prediction_info:', prediction);
              return;
            }

            const recentPointTs = predictionInfo.recent_point_ts;
            const groupByPeriodMs = predictionInfo.group_by_period_ms;

            if (!recentPointTs || !groupByPeriodMs) {
              console.warn('[TIME-SERIES] Prediction missing recent_point_ts or group_by_period_ms:', predictionInfo);
              return;
            }

            // Get the forecast value (now a single number, not an array)
            const forecastValue = predictionValue.forecast;
            if (forecastValue === undefined || forecastValue === null) {
              console.warn('[TIME-SERIES] Prediction missing forecast value:', predictionValue);
              return;
            }

            // Calculate X-axis timestamp: recent_point_ts + group_by_period_ms
            // This gives us the timestamp of the first forecast point
            const firstForecastTimestamp = recentPointTs + groupByPeriodMs;

            // Add the forecast point
            savedForecastPoints.push([firstForecastTimestamp, forecastValue]);
            console.log(`[TIME-SERIES] Added forecast point for ${sensorName}: ts=${new Date(firstForecastTimestamp).toISOString()}, ` +
              `value=${forecastValue}`);
          } catch (error) {
            console.error('[TIME-SERIES] Error processing prediction:', error, prediction);
          }
        });

        // Add saved forecast points to the existing forecast data
        if (savedForecastPoints.length > 0) {
          // console.log(`[TIME-SERIES] ✓ Loaded ${savedForecastPoints.length} saved forecast points`);
          this.historyForecastDataPoints = [...this.historyForecastDataPoints, ...savedForecastPoints];

          // Sort by timestamp
          this.historyForecastDataPoints.sort((a, b) => a[0] - b[0]);

          // Filter points within time window
          this.historyForecastDataPoints = this.historyForecastDataPoints.filter(
            point => point[0] >= minTime && point[0] <= maxTime
          );

          // Update chart
          if (this.chart) {
            this.updateChart();
          }
        }
      },
      error: (error) => {
        console.error('[TIME-SERIES] Error fetching forecast history:', error);
      }
    });
  }

  private handleTelemetryUpdate(update: SubscriptionUpdate): void {
    if (!update || !update.data) {
      return;
    }

    const { maxTime, minTime } = this.calculateTimeWindow();

    // Process incoming telemetry data for the selected sensor
    const sensorKey = this.selectedSensor;

    if (update.data[sensorKey]) {
      const values = update.data[sensorKey];

      if (Array.isArray(values)) {
        values.forEach(dataPoint => {
          // dataPoint is [timestamp, value]
          const timestamp = dataPoint[0];
          const value = parseFloat(dataPoint[1]);

          // Check if this timestamp already exists to avoid duplicates
          const existingIndex = this.telemetryData.findIndex(d => d[0] === timestamp);
          if (existingIndex >= 0) {
            // Update existing value
            this.telemetryData[existingIndex] = [timestamp, value];
          } else {
            // Add new data point
            this.telemetryData.push([timestamp, value]);
            this.telemetryData = this.telemetryData.filter(point => point[0] >= minTime && point[0] <= maxTime);
          }
        });

        // Keep only last 1000 points to avoid memory issues
        // if (this.telemetryData.length > 1000) {
        //   this.telemetryData = this.telemetryData.slice(-1000);
        // }

        // Sort by timestamp
        this.telemetryData.sort((a, b) => a[0] - b[0]);
      }
    }

    // Update chart
    this.updateChart();
    this.cdr.detectChanges();
  }

  private updateChart(): void {
    if (!this.chart) {
      return;
    }

    // Get current time window based on timewindow settings
    const { minTime, maxTime } = this.calculateTimeWindow();

    // Get the color for the selected sensor
    const sensorColor = this.sensorColors.get(this.selectedSensor) || '#2196f3';

    // Prepare series array
    const seriesArray: any[] = [
      {
        name: this.selectedSensor,
        type: 'line',
        data: this.telemetryData,
        smooth: false,
        symbol: 'circle',
        symbolSize: 4,
        lineStyle: {
          width: 2,
          color: sensorColor
        },
        itemStyle: {
          color: sensorColor
        }
      }
    ];

    // Add forecast series if forecast data is available
    if (this.forecastDataPoints && this.forecastDataPoints.length > 0) {
      this.forecastDataPoints.sort((a, b) => a[0] - b[0]);
      // console.log('[TIME-SERIES] Adding forecast series to chart with', this.forecastDataPoints.length, 'points');
      // console.log('[TIME-SERIES] Forecast data sample:', this.forecastDataPoints.slice(0, 3));
      seriesArray.push({
        name: `Forecast`, // Simplified name for debugging
        type: 'line',
        data: Array.from(this.forecastDataPoints),
        smooth: false,
        symbol: 'circle',
        symbolSize: 6, // Larger symbols for better visibility
        lineStyle: {
          width: 3, // Thicker line for better visibility
          color: TimeSeriesTelemetryComponent.FORECAST_COLOR, // Reserved orange color for forecast
          type: 'dashed' // Dashed line for forecast
        },
        itemStyle: {
          color: TimeSeriesTelemetryComponent.FORECAST_COLOR,
          opacity: 1 // Full opacity for debugging
        }
      });
    }

    // Update legend to include forecast if available
    const legendData = this.forecastDataPoints && this.forecastDataPoints.length > 0
      ? [this.selectedSensor, 'Forecast'] // Simplified legend
      : [this.selectedSensor];

    // Add history forecast series if history forecast data is available
    if (this.historyForecastDataPoints && this.historyForecastDataPoints.length > 0) {
      this.historyForecastDataPoints.sort((a, b) => a[0] - b[0]);
      this.historyForecastDataPoints = this.historyForecastDataPoints.filter(
        point => point[0] >= minTime
      );
      // console.log('[TIME-SERIES] Adding history forecast series to chart with', this.historyForecastDataPoints.length, 'points');
      // console.log('[TIME-SERIES] History forecast data sample:', this.historyForecastDataPoints.slice(0, 3));
      seriesArray.push({
        name: `Predictions`, // Simplified name for debugging
        type: 'line',
        data: this.historyForecastDataPoints,
        smooth: false,
        symbol: 'diamond',
        symbolSize: 6, // Larger symbols for better visibility
        lineStyle: {
          width: 3, // Thicker line for better visibility
          color: TimeSeriesTelemetryComponent.PREDICTIONS_COLOR, // Reserved green color for predictions
          type: 'dotted' // Dotted line for predictions
        },
        itemStyle: {
          color: TimeSeriesTelemetryComponent.PREDICTIONS_COLOR,
          opacity: 1 // Full opacity for debugging
        }
      });

      // Update legend to include predictions
      legendData.push('Predictions');
    }

    // console.log('[TIME-SERIES] Updating chart with:', {
    //   telemetryPoints: this.telemetryData.length,
    //   forecastPoints: this.forecastDataPoints.length,
    //   seriesCount: seriesArray.length,
    //   timeWindow: { minTime: new Date(minTime), maxTime: new Date(maxTime) }
    // });
    //
    if (this.chart) {
      // Expand the display range to include any forecast points so forecast history is visible
      let displayMin = minTime;
      let displayMax = maxTime;

      try {
        if (this.forecastDataPoints && this.forecastDataPoints.length > 0) {
          const fcMin = this.forecastDataPoints[0][0];
          const fcMax = this.forecastDataPoints[this.forecastDataPoints.length - 1][0];
          if (isFinite(fcMin)) {
            displayMin = Math.min(displayMin, fcMin - 1000); // 1s buffer
          }
          if (isFinite(fcMax)) {
            displayMax = Math.max(displayMax, fcMax + 1000);
          }
        }

        if (this.telemetryData && this.telemetryData.length > 0) {
          const tMin = this.telemetryData[0][0];
          const tMax = this.telemetryData[this.telemetryData.length - 1][0];
          if (isFinite(tMin)) {
            displayMin = Math.min(displayMin, tMin - 1000);
          }
          if (isFinite(tMax)) {
            displayMax = Math.max(displayMax, tMax + 1000);
          }
        }
      } catch (e) {
        // defensive: fall back to calculated window on unexpected data
        displayMin = minTime;
        displayMax = maxTime;
      }

      this.chart.setOption({
        title: {
          text: startCase(this.selectedSensor) + ' Data'
        },
        xAxis: {
          min: displayMin,
          max: displayMax,
        },
        legend: {
          data: legendData
        },
        series: seriesArray
      }, false, false);
    }

    // Update series data and axis range without animation


    // console.log('[TIME-SERIES] Chart updated successfully');
  }

  private calculateTimeWindow(): { minTime: number; maxTime: number } {
    const now = Date.now();
    let minTime: number;
    let maxTime: number = now;

    // Determine time window based on timewindow configuration
    if (this.timewindow.realtime) {
      // Realtime mode - use timewindowMs from configuration
      const timewindowMs = this.timewindow.realtime.timewindowMs || 60000; // Default to 1 minute
      minTime = now - timewindowMs;
    } else if (this.timewindow.history) {
      // History mode - calculate based on historyType
      if (this.timewindow.history.historyType === 0) { // LAST_INTERVAL
        // timewindowMs is a duration (e.g., 60000ms = 1 minute)
        const timewindowMs = this.timewindow.history.timewindowMs || 3600000; // Default to 1 hour
        minTime = now - timewindowMs;
        maxTime = now;
      } else if (this.timewindow.history.fixedTimewindow) { // FIXED
        // Use the fixed start/end times
        minTime = this.timewindow.history.fixedTimewindow.startTimeMs;
        maxTime = this.timewindow.history.fixedTimewindow.endTimeMs;
      } else {
        // Fallback
        minTime = now - 3600000;
        maxTime = now;
      }
    } else {
      // Default fallback - last 1 minute
      minTime = now - 60000;
    }

    return { minTime, maxTime };
  }

  private startTimeAxisUpdate(): void {
    // Only update time axis in realtime mode
    if (!this.timewindow?.realtime) {
      return;
    }

    // Update time axis every second to keep it moving
    this.timeAxisUpdateInterval = setInterval(() => {
      if (this.chart) {
        const { minTime, maxTime } = this.calculateTimeWindow();

        // Expand the display range to include any forecast points so forecast history is visible
        let displayMin = minTime;
        let displayMax = maxTime;

        try {
          if (this.forecastDataPoints && this.forecastDataPoints.length > 0) {
            const fcMin = this.forecastDataPoints[0][0];
            const fcMax = this.forecastDataPoints[this.forecastDataPoints.length - 1][0];
            if (isFinite(fcMin)) {
              displayMin = Math.min(displayMin, fcMin - 1000); // 1s buffer
            }
            if (isFinite(fcMax)) {
              displayMax = Math.max(displayMax, fcMax + 1000);
            }
          }

          if (this.telemetryData && this.telemetryData.length > 0) {
            const tMin = this.telemetryData[0][0];
            const tMax = this.telemetryData[this.telemetryData.length - 1][0];
            if (isFinite(tMin)) {
              displayMin = Math.min(displayMin, tMin - 1000);
            }
            if (isFinite(tMax)) {
              displayMax = Math.max(displayMax, tMax + 1000);
            }
          }
        } catch (e) {
          // defensive: fall back to calculated window on unexpected data
          displayMin = minTime;
          displayMax = maxTime;
        }

        // Update only the x-axis without changing series data
        this.chart.setOption({
          xAxis: {
            min: displayMin,
            max: displayMax
          }
        }, false, false);
      }
    }, 1000); // Update every second
  }

  private setupResizeObserver(): void {
    if (!this.chartElement?.nativeElement) {
      return;
    }

    // Create ResizeObserver to watch for container size changes
    this.resizeObserver = new ResizeObserver(() => {
      if (this.chart) {
        // Resize chart to fit new container dimensions
        this.chart.resize();
      }
    });

    // Observe the chart container element
    this.resizeObserver.observe(this.chartElement.nativeElement);
  }

  private clearData(): void {
    this.telemetryData = [];
    this.historyForecastDataPoints = [];
    this.forecastDataPoints = [];
    if (this.chart) {
      // Reset y-axis range to allow auto-scaling
      this.chart.setOption({
        yAxis: {
          min: null,
          max: null
        }
      });
      this.updateChart();
    }
  }

  private fetchHistoricalData(): Promise<void> {
    // return Promise.resolve();
    console.log('Fetching historical data for device:', this.deviceId, 'sensor:', this.selectedSensor);
    return new Promise((resolve) => {
      if (!this.deviceId || !this.selectedSensor) {
        // console.warn('Cannot fetch historical data: missing deviceId or sensor');
        resolve();
        return;
      }

      const entityId: EntityId = {
        entityType: EntityType.DEVICE,
        id: this.deviceId
      };

      // Calculate time range based on timewindow
      const { minTime, maxTime } = this.calculateTimeWindow();

      // Add extra 1 minute buffer to fetch more data points (in milliseconds)
      const bufferMs = 60000; // 1 minute
      const fetchMinTime = minTime - bufferMs;
      const fetchMaxTime = maxTime;

      // Get aggregation settings from timewindow
      const aggregationType = this.timewindow.aggregation?.type || AggregationType.NONE;
      const limit = this.timewindow.aggregation?.limit || 1000;
      const intervalValue = this.timewindow.aggregation?.interval;

      // Convert interval to number if needed
      let intervalMs: number | undefined;
      if (intervalValue !== undefined) {
        intervalMs = typeof intervalValue === 'number' ? intervalValue : undefined;
      }

      // console.log(`Fetching historical data for ${this.selectedSensor} from ${new Date(fetchMinTime)} to ${new Date(fetchMaxTime)}`);
      // console.log(`Actual display range: ${new Date(minTime)} to ${new Date(maxTime)}`);
      // console.log(`Aggregation: ${aggregationType}, Interval: ${intervalMs}, Limit: ${limit}`);

      console.log('=======================================Fetching Historical data:==================================');

      // Fetch historical telemetry data with buffer
      this.attributeService.getEntityTimeseries(
        entityId,
        [this.selectedSensor],
        fetchMinTime,
        fetchMaxTime,
        limit,
        aggregationType,
        intervalMs,
        DataSortOrder.ASC
      ).subscribe({
        next: (data) => {
          console.log('Historical data fetched successfully', data);
          // Process historical data
          if (data && data[this.selectedSensor]) {
            const { minTime: timewindowMin, maxTime: timewindowMax } = this.calculateTimeWindow();
            const historicalPoints = data[this.selectedSensor];

            // Convert to [timestamp, value] format
            const allDataPoints: Array<[number, number]> = historicalPoints.map((point: any) => [point.ts, parseFloat(point.value)]);

            // Filter out data points outside the actual requested time range
            // Keep data points within [minTime, maxTime]
            this.telemetryData = allDataPoints.filter(point => point[0] >= timewindowMin && point[0] <= timewindowMax);

            // Sort by timestamp
            this.telemetryData.sort((a, b) => a[0] - b[0]);

            // console.log(`Fetched ${allDataPoints.length} total, filtered to ${this.telemetryData.length} in range`);
            // console.log(`Aggregation: ${aggregationType}`);

            // Update chart with historical data
            this.updateChart();
            this.cdr.detectChanges();
          }

          resolve();
        },
        error: (error) => {
          console.error('Error fetching historical data:', error);
          resolve(); // Resolve anyway to continue with realtime subscription
        }
      });
    });
  }

  onTimewindowChanged(timewindow: Timewindow): void {
    this.timewindow = timewindow;
    this.timewindowChange.emit(timewindow);

    // Stop time axis updates if switching to history mode, start if switching to realtime
    if (this.timeAxisUpdateInterval) {
      clearInterval(this.timeAxisUpdateInterval);
      this.timeAxisUpdateInterval = null;
    }

    // Start time axis updates only in realtime mode
    if (this.timewindow.realtime) {
      this.startTimeAxisUpdate();
    }

    // Unsubscribe from current telemetry
    if (this.telemetrySubscription) {
      // console.log('Unsubscribing from existing telemetry subscription');
      this.telemetrySubscription.unsubscribe();
    }

    // Clear existing data
    // console.log('Clearing existing data');
    this.clearData();

    // Update chart to clear it immediately
    this.updateChart();

    // Fetch historical data first, then subscribe to realtime updates
    if (this.deviceId && this.selectedSensor) {
      this.getSensorData();
    } else {
      // console.log('Skipping historical data fetch - missing deviceId or selectedSensor');
    }
    // console.log('====== End timewindow change ======');
  }

  getSensorData() {
    console.log('Starting historical data fetch...');
    this.fetchHistoricalData().then(() => {
      console.log('Historical data fetch completed');
      // After historical data is loaded, subscribe to realtime updates if in realtime mode
      if (this.timewindow.realtime) {
        console.log('Re-subscribing to realtime telemetry');
        this.subscribeToTelemetry();
      }
      // In history mode, also fetch forecast predictions
      if (this.modelId) {
        console.log('[TIME-SERIES] History mode detected - fetching forecast predictions');
        this.fetchSensorForecastHistoryPredictions();
      }
      // Chart is already updated in fetchHistoricalData, no need to call updateChart again
    });
  }

  selectSensor(sensor: string): void {
    if (this.selectedSensor === sensor) {
      return; // Already selected
    }

    this.selectedSensor = sensor;
    this.onSensorChange();
  }

  refreshHistoryPredictions(): void {
    console.log('[TIME-SERIES] Manually refreshing history predictions');

    // Clear existing forecast data
    this.forecastDataPoints = [];

    // Refetch forecast history for the current sensor and model
    this.fetchSensorForecastHistoryPredictions();

    // Update the chart to reflect the new data
    if (this.chart) {
      this.updateChart();
    }
  }

  toCapitalizedWords(str: string): string {
    return str
      .replace(/([A-Z])/g, ' $1') // Insert space before capital letters
      .replace(/^./, (firstChar) => firstChar.toUpperCase()) // Capitalize first letter
      .trim();
  }

  onSensorChange(): void {
    // console.log('Sensor changed to:', this.selectedSensor);

    // Get the color for the selected sensor
    const sensorColor = this.sensorColors.get(this.selectedSensor) || '#2196f3';
    // console.log(`Switching to sensor ${this.selectedSensor} with color ${sensorColor}`);

    // Emit sensor change event
    this.sensorChanged.emit(this.selectedSensor);

    // Unsubscribe from current telemetry
    if (this.telemetrySubscription) {
      this.telemetrySubscription.unsubscribe();
    }

    // Clear existing data
    this.clearData();

    // Clear forecast data points
    this.forecastDataPoints = [];

    // Process forecast data for the new sensor
    if (this.forecastData) {
      this.processSensorForecastData();
    }

    // Update chart with new sensor color, legend, and axis labels
    if (this.chart) {
      this.chart.setOption({
        title: {
          text: startCase(this.selectedSensor) + ' Data'
        },
        legend: {
          data: [this.selectedSensor]
        },
        yAxis: {
          name: this.selectedSensor
        },
        series: [{
          name: this.selectedSensor,
          type: 'line',
          data: [],
          smooth: false,
          symbol: 'circle',
          symbolSize: 4,
          lineStyle: {
            width: 2,
            color: sensorColor
          },
          itemStyle: {
            color: sensorColor
          }
        }]
      }, false, false);
    }

    // Resubscribe with new sensor
    if (this.deviceId && this.selectedSensor) {
      this.subscribeToTelemetry();
    }
  }
}
