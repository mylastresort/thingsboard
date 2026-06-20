import { ViewChild, ElementRef, ChangeDetectorRef, NgZone, Input, OnDestroy, EventEmitter } from '@angular/core';
// ...existing code...
/* eslint-disable @angular-eslint/use-lifecycle-interface */
import { Component } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { AppState } from '@app/core/core.state';
import { PredictiveModelsService } from '@app/core/http/forecast.service';
import { DeviceService } from '@app/core/http/device.service';
import { DialogService } from '@app/core/services/dialog.service';
import { Order } from '@app/modules/home/models/predictive-maintenance.models';
import { PageComponent } from '@app/shared/public-api';
import {
  ForecastStatus,
  getForecastStatusFromString,
  getForecastStatusDisplayText,
  isForecastActive,
  getForecastViewPreferences,
  setForecastViewPreferences,
  ForecastAttribute,
} from '@app/shared/models/forecast.models';
import {
  ForecastViewType,
  ForecastViewPreferences,
  DEFAULT_VIEW_PREFERENCES,
  parseForecastViewPreferences,
  stringifyForecastViewPreferences,
  isForecastViewSelected,
  isAnomalyViewSelected,
} from '@app/shared/models/forecast-view-preferences.models';
import { Store } from '@ngrx/store';
import { MatDialog } from '@angular/material/dialog';
import {
  AddModelDialogComponent
} from '../../../components/predictive-maintenance/components/model/add-model-dialog/add-model-dialog.component';
import { ModelSelectionDialogComponent } from './model-selection-dialog/model-selection-dialog.component';
import { ModelLogsDialogComponent } from './model-logs-dialog/model-logs-dialog.component';
import {
  AnomaliesComponent,
  LogEntry,
  AnomalyPrediction,
  AnomalyReport,
  ForecastPredictionLogEntry,
  AnomalyPredictionLogEntry,
  ForecastPrediction,
  ForecastSensorPredictions,
  ForecastPredictionLogEntryMessage,
  ForecastSensorPrediction
} from '../../../components/predictive-maintenance/components/anomalies/anomalies.component';
import { CommonModule } from '@angular/common';
import {
  TimeSeriesTelemetryComponent
} from '../../../components/predictive-maintenance/components/time-series-telemetry/time-series-telemetry.component';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatInputModule } from '@angular/material/input';
import { FormsModule } from '@angular/forms';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import {
  trigger,
  state,
  style,
  transition,
  animate,
} from '@angular/animations';
import { ModelWebSocketService } from '@app/core/http/model-websocket.service';
import { ModelLogsNotifierService } from './model-logs-notifier.service';
import { QuickTimeInterval, Timewindow } from '@shared/models/time/time.models';
import { flatMap, result } from 'lodash';
import { mergeMap, Observable } from 'rxjs';
import { distinctUntilChanged, filter, tap, share } from 'rxjs/operators';
import { HttpClient } from '@angular/common/http';
import { AnomalyAlertsComponent } from '../../../components/predictive-maintenance/components/anomaly-alerts/anomaly-alerts.component';

@Component({
  selector: 'tb-forecast',
  standalone: true,
  imports: [
    CommonModule,
    MatFormFieldModule,
    MatSelectModule,
    MatIconModule,
    MatButtonModule,
    MatInputModule,
    FormsModule,
    TimeSeriesTelemetryComponent,
    AnomaliesComponent,
    AnomalyAlertsComponent,
    MatTooltipModule,
    MatCheckboxModule,
    TranslateModule,
  ],
  templateUrl: './model.component.html',
  styleUrls: ['./model.component.scss'],
  animations: [
    trigger('slideCollapse', [
      state(
        'expanded',
        style({ height: '*', opacity: 1, overflow: 'visible' })
      ),
      state(
        'collapsed',
        style({ height: '0', opacity: 0, overflow: 'hidden' })
      ),
      transition(
        'expanded <=> collapsed',
        animate('300ms cubic-bezier(0.4, 0.0, 0.2, 1)')
      ),
    ]),
  ],
})
export class ModelComponent extends PageComponent implements Order, OnDestroy {
  activeDashboardTab: 'forecast' | 'anomalies' = 'forecast';
  // Timewindow config for telemetry chart
  timewindow: Timewindow = {
    displayValue: '',
    // hideInterval: false,
    hideAggregation: false,
    hideAggInterval: false,
    hideTimezone: false,
    selectedTab: 0, // Will be set to TimewindowType.REALTIME or HISTORY
    realtime: {
      realtimeType: 0,
      interval: 60000,
      timewindowMs: 600000, // 10 minutes
      quickInterval: QuickTimeInterval.CURRENT_DAY
    },
    history: undefined // Only set when in history mode
  };

  attributes: ForecastAttribute[]; // To store the temperature data

  // Reference to the anomalies table component
  @ViewChild(AnomaliesComponent) anomaliesComponent?: AnomaliesComponent;

  // Reference to the anomaly alerts component for testing
  @ViewChild(AnomalyAlertsComponent) anomalyAlertsComponent?: AnomalyAlertsComponent;

  // Reference to the logs button element
  @ViewChild('logsButton', { read: ElementRef }) logsButton?: ElementRef;

  deviceId: string; // To pass to the chart

  Attributes: string[]; // To store the temperature data

  forecastData: ForecastSensorPredictions = {}; //Order[];

  @Input() forecastMaxSteps: number; // Number of forecast points

  // Event emitter for real-time forecast history points
  forecastHistoryPoint$ = new EventEmitter<{ sensor: string; timestamp: number; value: number }>();

  modelsData: Order[];

  historyForecastPredictions: any;

  models: Order[];

  filteredModels: Order[] = []; // For storing filtered models

  modelSearchTerm = ''; // Search term for filtering models

  modelNames: Map<string, string> = new Map(); // Cache for model names

  id: string;

  trueId: string;

  device: string;

  forecastName: string;

  date: string;

  status = 'inactive';

  forecastAlgorithm: string;

  anomalyAlgorithm: string;

  forecastGrouping = 'hourly';

  // Collapse/expand states for charts
  forecastChartCollapsed = false;

  anomaliesCollapsed = false;

  timeSeriesChartCollapsed = false;

  // Per-sensor timewindow map for independent widget controls
  timewindowsPerSensor: { [sensor: string]: Timewindow } = {};

  private cloneDefaultTimewindow(): Timewindow {
    return {
      displayValue: '',
      // hideInterval: false,
      hideAggregation: false,
      hideAggInterval: false,
      hideTimezone: false,
      selectedTab: 0,
      realtime: {
        realtimeType: 0,
        interval: 60000,
        timewindowMs: 600000,
        quickInterval: QuickTimeInterval.CURRENT_DAY
      },
      history: undefined
    };
  }

  private initSensorTimewindows(): void {
    if (Array.isArray(this.attributes)) {
      const map: { [sensor: string]: Timewindow } = {};
      this.attributes.forEach(attr => {
        const key = attr.key;
        // Initialize if not present to preserve user changes
        if (!this.timewindowsPerSensor[key]) {
          map[key] = this.cloneDefaultTimewindow();
        } else {
          map[key] = this.timewindowsPerSensor[key];
        }
      });
      this.timewindowsPerSensor = map;
      console.log('[MODEL] Initialized timewindows for sensors:', Object.keys(this.timewindowsPerSensor));
      this.cdr.detectChanges();
    }
  }

  onChildTimewindowChange(sensor: string, tw: Timewindow): void {
    this.timewindowsPerSensor = {
      ...this.timewindowsPerSensor,
      [sensor]: tw
    };
    console.log('[MODEL] Updated timewindow for sensor:', sensor);
  }

  selectedViews: ForecastViewType[] = [];

  selectedSensor = 'rotate'; // Default sensor for forecast chart

  hideSensorTelemetry = false; // Hide sensor telemetry widget

  currentViewPreferences: ForecastViewPreferences; // Current view preferences with sensor colors

  // Reserved colors for forecast and predictions - DO NOT allow users to select these for telemetry
  private static readonly RESERVED_COLORS = [
    TimeSeriesTelemetryComponent.FORECAST_COLOR,     // Orange - reserved for Forecast series
    TimeSeriesTelemetryComponent.PREDICTIONS_COLOR   // Green - reserved for Predictions series
  ];

  // Full color palette before filtering reserved colors
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

  // Available colors for sensor color picker (excludes reserved colors to prevent conflicts with Forecast/Predictions)
  availableColors: string[] = ModelComponent.FULL_COLOR_PALETTE.filter(
    color => !ModelComponent.RESERVED_COLORS.includes(color)
  );

  showViewSelector = false;

  sensorColorsExpanded = false;

  widgetsExpanded = false;

  // Track which widgets are visible (by sensor key or 'anomalies')
  hiddenWidgets: Set<string> = new Set();

  unreadLogs = false;

  isWidgetVisible(widgetKey: string): boolean {
    return !this.hiddenWidgets.has(widgetKey);
  }

  toggleWidgetVisibility(widgetKey: string, visible: boolean): void {
    if (visible) {
      this.hiddenWidgets.delete(widgetKey);
    } else {
      this.hiddenWidgets.add(widgetKey);
    }
    this.saveViewPreferences();
  }

  // Initialize unread logs state from the notifier service on component creation
  private initializeUnreadLogsState(): void {
    if (this.trueId) {
      const hasUnread = this.logsNotifier.hasUnreadLogs(this.trueId);
      console.log('Initializing unreadLogs from notifier for', this.trueId, ':', hasUnread);
      this.unreadLogs = hasUnread;
    }
  }

  // Logs tooltip properties
  showLogsTooltip = false; // Only true after calculations are complete

  dontShowLogsTooltipAgain = false;

  logsTooltipPosition = { top: -1000000, left: -1000000, zIndex: -1000 };

  private readonly LOGS_TOOLTIP_PREFERENCE_KEY = 'model-logs-tooltip-dont-show';

  // Log tracking properties
  private lastReadLogTimestamp = 0;

  logsObservable: Observable<LogEntry> = null; // Made public for template access

  private subscriptions: Array<any> = [];

  private notifierSubscription: any = null;

  private routeParamsSubscription: any = null;

  private readonly LAST_READ_LOG_KEY_PREFIX = 'model-last-read-log-';

  private forecastPredictionLogs$: Observable<ForecastPredictionLogEntry>;

  // Forecast job pause/unpause state
  forecastJobRunning = false;

  forecastJobPaused = false;

  constructor(
    protected store: Store<AppState>,
    protected route: ActivatedRoute,
    public predictiveModelsService: PredictiveModelsService,
    private deviceService: DeviceService,
    protected router: Router,
    public dialog: MatDialog,
    private translate: TranslateService,
    private modelWebSocketService: ModelWebSocketService,
    private dialogService: DialogService,
    private logsNotifier: ModelLogsNotifierService,
    private cdr: ChangeDetectorRef,
    private ngZone: NgZone,
    private http: HttpClient,
  ) {
    super(store);
  }


  ngOnDestroy(): void {
    console.log("ngOnDestroy()");
    this.predictiveModelsService.anomalies = [];
    // Unsubscribe from log updates
    if (this.logsObservable) {
      // this.logsObservable.unsubscribe();
      this.logsObservable = null;
    }

    // Unsubscribe from model status and logs
    if (this.trueId) {
      this.modelWebSocketService.unsubscribeFromModelStatus(this.trueId);
      this.modelWebSocketService.unsubscribeFromLogs(this.trueId);
    }
    this.modelWebSocketService.disconnect();

    // Unsubscribe from notifier
    if (this.notifierSubscription) {
      this.notifierSubscription.unsubscribe();
      this.notifierSubscription = null;
    }

    // Unsubscribe from route params
    if (this.routeParamsSubscription) {
      this.routeParamsSubscription.unsubscribe();
      this.routeParamsSubscription = null;
    }

    // Unsubscribe from all tracked subscriptions
    this.subscriptions.forEach((sub) => sub.unsubscribe());
  }

  /**
   * Fetch historical anomaly predictions from the database
   * and add them to the anomalies table component.
   */
  fetchAnomalyHistoryPredictions() {
    if (!this.trueId) {
      console.warn('[MODEL] Cannot fetch history: No model ID available');
      return;
    }

    console.log('[MODEL] Fetching anomaly history predictions for model:', this.trueId);

    // Calculate time range: last 30 days
    const endTs = Date.now();
    const startTs = endTs - (30 * 24 * 60 * 60 * 1000); // 30 days ago

    // Fetch anomaly predictions from the database
    this.predictiveModelsService.fetchHistoryPredictions(
      this.trueId,
      'Anomaly', // prediction type
      startTs,
      endTs,
      100 // limit
    ).subscribe({
      next: (response) => {
        console.log('[MODEL] Fetched anomaly history:', response);

        if (response.predictions && response.predictions.length > 0) {
          let addedCount = 0;
          // Process each historical prediction and add to the anomalies table
          response.predictions.forEach((prediction: any) => {
            try {
              // Parse the prediction value if it's a string
              const predictionValue = typeof prediction.predictionValue === 'string'
                ? JSON.parse(prediction.predictionValue)
                : prediction.predictionValue; 

              // Only show predictions where failure_predicted is true
              if (predictionValue.failure_predicted === true) {
                // Convert database prediction to AnomalyReport format
                const anomaly = this.convertPredictionToAnomaly(prediction, predictionValue);

                // Add to anomalies component
                // this.predictiveModelsService.anomaliesDataSubject.next(anomaly);
                this.predictiveModelsService.sendAnomaly(anomaly);
                addedCount++;
              } else {
                console.log('[MODEL] Skipping prediction (failure_predicted is not true):', prediction.id);
              }
            } catch (error) {
              console.error('[MODEL] Error processing historical prediction:', error, prediction);
            }
          });

          console.log(
            `[MODEL] ✓ Added ${addedCount} historical anomalies ` +
            `(filtered from ${response.predictions.length} total)`
          );
        } else {
          console.log('[MODEL] No historical anomaly predictions found');
        }
      },
      error: (error) => {
        console.error('[MODEL] Error fetching anomaly history:', error);
      }
    });
  }

  /**
   * Convert a database prediction record to an AnomalyReport
   */
  private convertPredictionToAnomaly(prediction: any, predictionValue: any): AnomalyReport {
    // Extract confidence and severity
    const confidence = predictionValue.general_failure_probability
      ? Math.round(predictionValue.general_failure_probability * 100)
      : predictionValue.confidence || 0;
    const severity = confidence >= 90 ? 'Critical' : confidence >= 70 ? 'Major' : 'Minor';

    // Extract time information - create 1 hour range
    let startTime: string | number | undefined;
    let endTime: string | number | undefined;

    if (predictionValue.datetime) {
      const parts = predictionValue.datetime.split('/');
      if (parts.length === 2) {
        startTime = parts[0];
        endTime = parts[1];
      } else {
        // Single datetime - create 1 hour range
        const startDate = new Date(predictionValue.datetime);
        const endDate = new Date(startDate.getTime() + 60 * 60 * 1000); // Add 1 hour
        startTime = startDate.toISOString();
        endTime = endDate.toISOString();
      }
    } else if (prediction.predictionTime) {
      // Use predictionTime and create 1 hour range
      const startDate = new Date(prediction.predictionTime);
      const endDate = new Date(startDate.getTime() + 60 * 60 * 1000); // Add 1 hour
      startTime = startDate.toISOString();
      endTime = endDate.toISOString();
    }

    // Get component type, remove "Unknown" fallback
    const componentType = predictionValue.predicted_failing_component || predictionValue.component_type || '';

    return {
      id: prediction.id,
      reportEntity: this.deviceId,
      errorName: predictionValue.predicted_failing_component || predictionValue.error_name || '',
      severity,
      creationDate: prediction.predictionTime || prediction.createdAt || new Date().toISOString(),
      componentType,
      deviceType: '',
      location: '',
      description: predictionValue.description ||
        `Predicted failure for component ${predictionValue.predicted_failing_component || ''}`,
      status: 'Active',
      timeRange: predictionValue.datetime || prediction.predictionTime || '',
      startTime,
      endTime,
      confidence,
      affectedMetrics: predictionValue.predicted_failing_component
        ? [predictionValue.predicted_failing_component]
        : predictionValue.affected_metrics || [],
    };
  }

  subscribeToAnomalyPredictions() {
    const anomalyPredictionLogs$ = this.logsObservable.pipe(
      filter((log: LogEntry) =>
        log.type && log.type.toLowerCase() === 'anomaly' && log.level && log.level.toLowerCase() === 'prediction')
    ) as Observable<AnomalyPredictionLogEntry>;

    const anomalyPredictionLogsSubscription = anomalyPredictionLogs$.subscribe(log => {
      // console.log('Log entry:', log);
      console.log('Anomaly Prediction Log entry:', log);
      // return

      // Check if this log is new (after last read timestamp)
      const logTimestamp = log.timestamp ? new Date(log.timestamp).getTime() : Date.now();
      console.log(
        'Log timestamp:',
        logTimestamp,
        'Last read:',
        this.lastReadLogTimestamp,
        'Is new?',
        logTimestamp > this.lastReadLogTimestamp
      );
      if (logTimestamp > this.lastReadLogTimestamp) {
        console.log('Setting unreadLogs to true');
        // Run inside Angular zone to ensure change detection
        this.ngZone.run(() => {
          this.unreadLogs = true;
          console.log('Inside zone, unreadLogs set to:', this.unreadLogs);
        });
        console.log('After zone.run, unreadLogs:', this.unreadLogs);
        // update global notifier
        try {
          if (this.trueId) {
            this.logsNotifier.setUnread(this.trueId, true);
          }
        } catch (e) {
          // ignore notifier errors
        }
      }

      if (log.level.toLowerCase() === 'prediction') {
        console.log('Job prediction:', log.message);
        // Try to parse prediction log as JSON

        if (typeof log.message !== 'string' && log.message?.result) {
          // Process each prediction result individually
          const results = Array.isArray(log.message.result) ? log.message.result : [log.message.result];

          results.forEach((predictionItem: any) => {
            // Only process results that predict a failure
            if (predictionItem.failure_predicted === true) {
              const anomaly = this.processAnomalyPrediction(predictionItem);
              this.anomaliesComponent?.addAnomaly(anomaly);
            }
          });
        }
      } else {
        // console.log4('Job log:', log.message);
      }
    });

    this.subscriptions.push(anomalyPredictionLogsSubscription);
  }

  subscribeToForecastPredictions(forecastId) {
    console.log('[MODEL] Subscribing to forecast prediction logs');
    this.forecastPredictionLogs$ = this.logsObservable.pipe(
      // tap the message
      // tap((log) => {
      //   console.log('%cReceived log entry for forecast prediction:', 'color: green;', log);
      // }),
      filter((log: LogEntry) =>
        log.level && log.level.toLowerCase() === 'prediction' &&
        (log.type && log.type.toLowerCase() === 'forecast') || (log.source && log.source.toLowerCase() === 'forecastmodel')),
      tap((log) => {
        console.log('%cProcessing forecast_history log entry:', 'color: orange;', log);
        if (typeof log.message !== 'string') {
          const msg = log.message as any;
          console.log('%cRecent point timestamp:', 'color: blue;', msg?.recent_point_ts);
        }
      }),
    ) as Observable<ForecastPredictionLogEntry>;

    const forecastLogsSubscription = this.forecastPredictionLogs$.subscribe(log => {
      // console.log('[MODEL] Forecast Prediction Log entry:', log);
      // const results: ForecastSensorPrediction = null;

      // Extract result from the message
      // Expected structure:
      // {
      //     "level": "PREDICTION",
      //     "message": {
      //         "device_id": "3f41e590-b890-11f0-a275-a13bd5e488b9",
      //         "iteration": 1,
      //         "prediction_type": "forecast",
      //         "recent_point_ts": 1709654400000,
      //         "result": {
      //             "prediction_info": {
      //                "group_by_period_ms": 5000,
      //                "recent_recent_ts": 1763487178717,
      //             },
      //             "timestamp": [],
      //             "forecast": [],
      //             "sensor": "rotate",
      //         }
      //     },
      //     "timestamp": "2025-11-10T14:11:02.747464Z",
      //     "type": "forecast"
      // }

      console.log('[MODEL] Received forecast prediction log:', log.message.prediction_type);

      if (log.message.prediction_type === 'forecast') {
        //   console.log(
        // '[MODEL] Processing forecast prediction log:', log
        //   );
        const results = log.message.result as ForecastSensorPrediction;

        if (results) {
          // Extract prediction_info for calculating forecast history points
          const predictionInfo = (results as any).prediction_info;
          const recentPointTs = predictionInfo?.recent_point_ts;
          const groupByPeriodMs = predictionInfo?.group_by_period_ms;
          const sensorName: string = (log.message as any).sensor;
          const forecast: number[] = (results as any).forecast;

          console.log({
            predictionInfo,
            recentPointTs,
            groupByPeriodMs,
            sensorName,
            forecast,
          });

          // Store forecast data for all sensors (removed filter)
          this.forecastData = {
            ...this.forecastData,
            [sensorName]: {
              forecast: Array.from(forecast),
              timestamp: forecast.map((_, i) => recentPointTs + (i + 2) * groupByPeriodMs)
            }
          };
          this.cdr.detectChanges();
        } else {
          console.warn('[MODEL] No forecast results to process');
        }
      } else if (log.message.prediction_type === 'history') {
        // Historical forecast prediction - add to historyForecastPredictions
        console.log('[MODEL] Processing historical forecast prediction log:', log);
        this.historyForecastPredictions = log.message;
      }
    });

    this.subscriptions.push(forecastLogsSubscription);
  }

  changeModel(value: any) {
    this.router.navigateByUrl('/predictive-maintenance/model/' + value);

    this.deviceId = '';
    this.Attributes = [];
    this.trueId = value;
    this.forecastAlgorithm = '';
    this.anomalyAlgorithm = '';
    this.forecastGrouping = 'hourly';
    this.fetchPredictiveModelConfig(value);
  }

  openModelSelectionDialog(): void {
    const panelClass = typeof document !== 'undefined' && document.body.classList.contains('tb-dark') ? 'tb-dark' : undefined;
    const dialogRef = this.dialog.open(ModelSelectionDialogComponent, {
      width: '600px',
      data: {
        models: this.models,
        currentModelId: this.id,
        getModelDisplayName: (model: any) => this.getModelDisplayName(model),
      },
      ...(panelClass ? { panelClass } : {}),
    });

    dialogRef.afterClosed().subscribe((selectedModel: Order) => {
      if (selectedModel && selectedModel.trueId !== this.id) {
        this.changeModel(selectedModel.trueId);
      }
    });
  }

  ngAfterViewInit(): void {
    // Check if data was passed via the router's state
    if (history.state && history.state.forecastData) {
      this.modelsData = history.state.forecastData;
      // console.log("Forecast data received:", this.forecastData);
    } else {
      // Optionally, handle the case when data is not passed
      console.error('No forecast data passed.');
    }



    // Add document click listener for view selector dropdown
    this.addDocumentClickListener();

    this.modelWebSocketService.connect();
    // Update anomalies component about connection status (if available)
    try {
      // const connected = this.modelWebSocketService.isConnected();
      // this.anomaliesComponent?.setStreamStatus(connected, connected ? null : null);
    } catch (e) {
      // ignore if service is not ready
    }
    // Ensure we update anomalies component when the WebSocket actually connects
    this.modelWebSocketService.onConnect(() => {
      // console.info('%c[ModelComponent] WebSocket connection established successfully', 'color: #9E9E9E; font-weight: bold');
      try {
        // const connected = this.modelWebSocketService.isConnected();
        // this.anomaliesComponent?.setStreamStatus(connected, connected ? null : null);
      } catch (e) {
        // ignore
      }
    });

    this.init();
  }

  private positionLogsTooltip(): void {
    // setTimeout(() => {
    if (this.logsButton) {
      const buttonElement = this.logsButton.nativeElement;
      const iconElement = buttonElement.querySelector('mat-icon');

      // Use the icon element's bounding box if available, otherwise fall back to button
      const rect = iconElement ? iconElement.getBoundingClientRect() : buttonElement.getBoundingClientRect();

      // Calculate tooltip position so the arrow points right after the icon (not the button container)
      this.logsTooltipPosition = {
        top: rect.bottom + 14, // 2px below the icon itself
        left: rect.left + (rect.width / 2), // Align arrow with center of icon
        zIndex: 1000 // Ensure tooltip is above other elements
      };

      // Only show tooltip after calculations are complete (for testing purposes)
      // this.showLogsTooltip = true;
    }
    // }, 200); // Increased timeout to ensure UI is stable
  }

  private init() {
    // Track route params subscription for proper cleanup
    this.routeParamsSubscription = this.route.params.pipe(
      distinctUntilChanged((prev, curr) => prev.id === curr.id)
    ).subscribe((params) => {
      console.log('Route params:', params);
      if (params.id) {
        this.trueId = params.id;
        this.id = params.id;
        this.fetchPredictiveModelConfig(params.id);
        this.models = this.modelsData;
        // console.log("models === ", this.models);
        // If models data wasn't passed via navigation (page reload), create a fallback single-entry list
        // so the page can continue to load and fetch the model config and prediction history.
        if (!this.models || this.models.length === 0) {
          this.models = [{
            id: params.id,
            trueId: params.id,
            device: '',
            date: new Date().toISOString()
          }];
          // don't navigate away; we'll fetch the full model config below
        }

        // Load collapsed states from localStorage
        this.loadCollapsedStates();

        // Initialize filtered models
        this.updateFilteredModels();

        // Fetch names for all models
        this.fetchModelNames();

        // Load view preferences for the current forecast
        if (this.trueId !== params.id) {
          this.trueId = params.id;
          this.loadViewPreferences();
        }

        const forecast = this.models.find(
          (element) => element.trueId === this.id
        );
        if (!forecast) {
          return this.router.navigateByUrl('');
        }
        this.device = forecast.device;
        this.forecastName = forecast.id; // Use the forecast ID as the name
        this.date = forecast.date;

        this.modelWebSocketService.cleanUp();

        // Load last read log timestamp from localStorage
        this.loadLastReadLogTimestamp();
        console.log('Initial lastReadLogTimestamp for model', this.trueId, ':', this.lastReadLogTimestamp);

        // Initialize unread logs state from notifier service
        this.initializeUnreadLogsState();
        console.log('Initial unreadLogs after initialization:', this.unreadLogs);

        // Clean up previous subscriptions before creating new ones
        this.subscriptions.forEach((sub) => sub.unsubscribe());
        this.subscriptions = [];

        // map job logs to each log entry
        // Use share() to make this a hot observable - all subscribers receive the same data
        this.logsObservable = this.modelWebSocketService.requestJobLogs(this.trueId)
          .pipe(
            filter((msg) => {
              return msg.forecastId == params.id || msg.forecast_id == params.id;
            }),
            mergeMap((msg) => flatMap(msg.data.logs)),
            tap((log) => {
              console.log('%cReceived log entry:', 'color: green;', log);
            }),
            share() // Share the observable among all subscribers
          );

        // Subscribe to predictive model status updates (inactive, pending, active, error)
        const modelStatusSubscription = this.modelWebSocketService.requestModelStatus(this.trueId)
          .subscribe((msg: any) => {
            if (msg.forecastId != params.id) return;
            console.log('Predictive model status update:', msg);
            if (msg?.data?.status) {
              const modelStatus = msg.data.status.toLowerCase();
              // Map backend status to frontend status
              if (modelStatus === 'inactive' || modelStatus === 'pending' || modelStatus === 'active' || modelStatus === 'error') {
                this.status = modelStatus === 'error' ? 'failed' : modelStatus;
              }
              // Update progress if pending
              if (modelStatus === 'pending' && msg.data.trainingProgress !== undefined) {
                this.progressMessage = {
                  step: msg.data.trainingStep || 'Training',
                  progress: msg.data.trainingProgress || 0
                };
              } else if (modelStatus !== 'pending') {
                this.progressMessage = null;
              }
            }
          });
        this.subscriptions.push(modelStatusSubscription);

        console.log(`[ModelComponent] Fetch history of predictions`);

        this.fetchAnomalyHistoryPredictions();

        console.log(`[ModelComponent] Subscribing to anomaly predictions`);

        this.subscribeToAnomalyPredictions();
        this.subscribeToForecastPredictions(params.id);
      }

      // Clean up previous notifier subscription before creating new one
      if (this.notifierSubscription) {
        this.notifierSubscription.unsubscribe();
        this.notifierSubscription = null;
      }

      // Subscribe to notifier changes so the UI updates if other parts mark read
      this.notifierSubscription = this.logsNotifier.changes().subscribe(change => {
        if (change.modelId === this.trueId) {
          this.ngZone.run(() => {
            this.unreadLogs = change.unread;
            console.log('Notifier changed unreadLogs to:', this.unreadLogs, 'for model:', this.trueId);
          });
        }
      });
    });
  }

  private fetchModelNames() {
    if (this.models && this.models.length > 0) {
      this.models.forEach((model) => {
        this.predictiveModelsService.getPredictiveModel(model.trueId).subscribe(
          (data) => {
            const name = data.name || data.id.id.split('-')[0];
            this.modelNames.set(model.trueId, name);
            // Update filtered models after names are fetched
            this.filterModels();
          },
          (error) => {
            console.error(
              'Error fetching forecast name for',
              model.trueId,
              error
            );
            // Fallback to the existing ID
            this.modelNames.set(model.trueId, model.id);
            // Update filtered models even on error
            this.filterModels();
          }
        );
      });
    }
  }

  getModelDisplayName(model: any): string {
    return this.modelNames.get(model.trueId) || model.id;
  }

  filterModels(): void {
    if (!this.modelSearchTerm || this.modelSearchTerm.trim() === '') {
      this.filteredModels = [...this.models];
    } else {
      const searchTerm = this.modelSearchTerm.toLowerCase();
      this.filteredModels = this.models.filter(
        (model) =>
          this.getModelDisplayName(model).toLowerCase().includes(searchTerm) ||
          model.device.toLowerCase().includes(searchTerm) ||
          model.date.toLowerCase().includes(searchTerm)
      );
    }
  }

  private updateFilteredModels(): void {
    this.filteredModels = [...this.models];
    this.modelSearchTerm = ''; // Reset search term when models change
  }

  fetchPredictiveModelConfig(forecastId: string): any {
    this.predictiveModelsService.getPredictiveModel(forecastId).subscribe(
      (data) => {
        this.deviceId = data.deviceId.id;
        this.Attributes = data.attributes.map((attr) => attr.key);
        this.attributes = data.attributes;

        // Initialize per-sensor timewindows when attributes are available
        this.initSensorTimewindows();

        // Initialize selectedSensor from model's configured attributes (first sensor)
        if (this.Attributes.length > 0 && !this.Attributes.includes(this.selectedSensor)) {
          this.selectedSensor = this.Attributes[0];
          console.log(`[MODEL] Initialized selectedSensor to '${this.selectedSensor}' from model attributes`);
        }

        this.trueId = data.id.id;
        this.forecastName = data.name || data.id.id.split('-')[0]; // Use name if available, fallback to ID
        this.forecastAlgorithm = data.forecastAlgorithm;
        this.anomalyAlgorithm = data.anomalyAlgorithm;
        // this.forecastGrouping = JSON.parse(data.additionalData || '{}').forecastGrouping || 'hourly';
        const additionalData = typeof data.additionalData === 'string'
          ? JSON.parse(data.additionalData || '{}')
          : (data.additionalData || {});
        this.forecastGrouping = additionalData.forecastGrouping || 'hourly';

        // Fetch device name
        this.deviceService.getDevice(data.deviceId.id).subscribe(
          (device) => {
            this.device = device.name;
          },
          (error) => {
            console.error('Error fetching device:', error);
            this.device = data.deviceId.id; // Fallback to device ID
          }
        );
      },
      (error) => {
        console.error('Error fetching forecast:', error);
      }
    );
  }

  openCreateModelDialog(): void {
    const dialogRef = this.dialog.open(AddModelDialogComponent, {
      width: '600px',
    });

    // eslint-disable-next-line @typescript-eslint/no-shadow
    dialogRef.afterClosed().subscribe((result) => {
      if (result) {
        this.addForecast(result); // Call addForecast if a result is returned
      }
    });
  }

  saveModelConfig(): void {
    if (!this.trueId) {
      console.error('No model currently loaded to save');
      return;
    }
    // Fetch full model config and save to localStorage
    this.predictiveModelsService.getPredictiveModel(this.trueId).subscribe(
      (data) => {
        const payload: any = JSON.parse(JSON.stringify(data));
        if (payload.id) {
          delete payload.id;
        }
        // Give a distinct name for saved template
        const baseName = payload.name || `Model_${Date.now()}`;
        const templateName = baseName.endsWith('_template') ? baseName : baseName + '_template';
        payload.name = templateName;

        // Save to localStorage with unique key
        try {
          // Use template name as unique key
          const template = {
            config: payload,
            savedAt: Date.now(),
            deviceId: this.deviceId,
            deviceName: this.device
          };

          const record = {
            name: templateName,
            config: template
          };

          this.predictiveModelsService.saveLoadModelConfig(record).subscribe(
            (response) => {
              alert(`Model template "${templateName}" saved successfully`);
            },
            (error) => {
              console.error('Failed to save model template via service:', error);
              alert('Failed to save model template');
            }
          );

          alert(`Model template "${templateName}" saved successfully`);
        } catch (e) {
          console.error('Failed to save model template to localStorage:', e);
          alert('Failed to save model template');
        }
      },
      (error) => {
        console.error('Failed to fetch current model config for saving:', error);
        alert('Failed to fetch model configuration');
      }
    );
  }

  openLogsDialog(): void {
    if (!this.trueId) {
      console.error('No model ID available for viewing logs');
      return;
    }

    // Mark logs as read when opening the dialog
    this.unreadLogs = false;
    this.saveLastReadLogTimestamp();
    try {
      if (this.trueId) {
        this.logsNotifier.markAsRead(this.trueId);
      }
    } catch (e) {
      // ignore
    }

    const dialogRef = this.dialog.open(ModelLogsDialogComponent, {
      width: '900px',
      maxWidth: '95vw',
      height: '80vh',
      data: {
        modelId: this.trueId,
        modelName: this.forecastName || this.trueId,
        deviceId: this.deviceId,
        websocket: null,
        wsUrl: '',
      },
    });

    dialogRef.afterClosed().subscribe(() => {
      // console.log('Logs dialog closed');
    });
  }

  openForecastLogsDialog(): void {
    if (!this.trueId) {
      console.error('No model ID available for viewing forecast logs');
      return;
    }

    const dialogRef = this.dialog.open(ModelLogsDialogComponent, {
      width: '900px',
      maxWidth: '95vw',
      height: '80vh',
      data: {
        modelId: this.trueId,
        modelName: this.forecastName || this.trueId,
        deviceId: this.deviceId,
        modelTypeFilter: 'forecast',
      },
    });

    dialogRef.afterClosed().subscribe(() => {
      // console.log('Forecast logs dialog closed');
    });
  }

  openAnomalyLogsDialog(): void {
    if (!this.trueId) {
      console.error('No model ID available for viewing anomaly logs');
      return;
    }

    const dialogRef = this.dialog.open(ModelLogsDialogComponent, {
      width: '900px',
      maxWidth: '95vw',
      height: '80vh',
      data: {
        modelId: this.trueId,
        modelName: this.forecastName || this.trueId,
        deviceId: this.deviceId,
        modelTypeFilter: 'anomaly',
      },
    });

    dialogRef.afterClosed().subscribe(() => {
      // console.log('Anomaly logs dialog closed');
    });
  }

  // Pause forecast prediction job
  pauseForecastJob(): void {
    console.log('[MODEL] pauseForecastJob called', {
      trueId: this.trueId,
      forecastJobRunning: this.forecastJobRunning,
      forecastJobPaused: this.forecastJobPaused
    });

    if (!this.trueId) {
      console.error('[MODEL] Cannot pause: No forecast ID');
      return;
    }

    console.log('[MODEL] Pausing forecast predictions for', this.trueId);

    // Send pause command via WebSocket
    const commandId = Date.now();
    const command = {
      commandId,
      type: 'pause_job',
      forecastId: this.trueId,
      data: {
        modelType: 'forecast'
      }
    };

    const ws$ = this.modelWebSocketService.connect();
    ws$.next(command);

    // Update UI state
    this.forecastJobPaused = true;
    this.cdr.detectChanges();

    console.log('[MODEL] Pause command sent:', command);
  }

  // Resume (unpause) forecast prediction job
  unpauseForecastJob(): void {
    if (!this.trueId) {
      console.error('[MODEL] Cannot unpause: No forecast ID');
      return;
    }

    console.log('[MODEL] Resuming forecast predictions for', this.trueId);

    // Send unpause command via WebSocket
    const commandId = Date.now();
    const command = {
      commandId,
      type: 'unpause_job',
      forecastId: this.trueId,
      data: {
        modelType: 'forecast'
      }
    };

    const ws$ = this.modelWebSocketService.connect();
    ws$.next(command);

    // Update UI state
    this.forecastJobPaused = false;
    this.cdr.detectChanges();

    console.log('[MODEL] Unpause command sent:', command);
  }

  openForecastStatsDialog(): void {
    if (!this.trueId) {
      console.error('No model ID available for viewing forecast stats');
      return;
    }

    // TODO: Create ModelStatsDialogComponent
    // For now, show a placeholder dialog with model info
    this.dialogService.alert(
      'Forecast Training Stats',
      `<div style="text-align: left;">
        <p><strong>Model ID:</strong> ${this.trueId}</p>
        <p><strong>Model Name:</strong> ${this.forecastName || 'N/A'}</p>
        <p><strong>Algorithm:</strong> ${this.forecastAlgorithm || 'N/A'}</p>
        <p><strong>Device:</strong> ${this.device || 'N/A'}</p>
        <p><strong>Status:</strong> ${this.status || 'N/A'}</p>
        <hr>
        <p><em>Training stats dialog will show:</em></p>
        <ul>
          <li>Algorithm used</li>
          <li>Training period</li>
          <li>Model performance metrics</li>
          <li>Training duration</li>
          <li>Hyperparameters</li>
        </ul>
      </div>`,
      'Close',
      true
    );
  }

  openAnomalyStatsDialog(): void {
    if (!this.trueId) {
      console.error('No model ID available for viewing anomaly stats');
      return;
    }

    // TODO: Create ModelStatsDialogComponent
    // For now, show a placeholder dialog with model info
    this.dialogService.alert(
      'Anomaly Training Stats',
      `<div style="text-align: left;">
        <p><strong>Model ID:</strong> ${this.trueId}</p>
        <p><strong>Model Name:</strong> ${this.forecastName || 'N/A'}</p>
        <p><strong>Algorithm:</strong> ${this.anomalyAlgorithm || 'N/A'}</p>
        <p><strong>Device:</strong> ${this.device || 'N/A'}</p>
        <p><strong>Status:</strong> ${this.status || 'N/A'}</p>
        <hr>
        <p><em>Training stats dialog will show:</em></p>
        <ul>
          <li>Algorithm used</li>
          <li>Training period</li>
          <li>Model performance metrics</li>
          <li>Training duration</li>
          <li>Hyperparameters</li>
        </ul>
      </div>`,
      'Close',
      true
    );
  }

  openEditModelDialog(): void {
    if (!this.trueId) {
      console.error('No model ID available for editing');
      return;
    }

    // Fetch the current forecast data for editing
    this.predictiveModelsService.getPredictiveModel(this.trueId).subscribe(
      (forecastData) => {
        // console.log('Raw forecast data from service:', forecastData);

        const forecastGrouping = JSON.parse(forecastData.additionalData || '{}').forecastGrouping || 'hourly';

        // Prepare the data structure that the dialog expects
        const dialogData = {
          isEdit: true,
          forecastData: {
            id: forecastData.id, // Include the full ForecastId object
            trueId: forecastData.id,
            modelName: forecastData.name || forecastData.id.id.split('-')[0],
            device: this.device,
            deviceId: forecastData.deviceId,
            attributes: forecastData.attributes || [],
            attributesText: forecastData.attributes
              ? forecastData.attributes.map((attr) => attr.key).join(', ')
              : '',
            forecastAlgorithm: forecastData.forecastAlgorithm,
            anomalyAlgorithm: forecastData.anomalyAlgorithm,
            forecastGrouping,
            forecastStartDate: forecastData.forecastStartDate,
            forecastEndDate: forecastData.forecastEndDate,
            anomaliesStartDate: forecastData.anomalyStartDate,
            anomaliesEndDate: forecastData.anomalyEndDate,
          },
        };

        // console.log('Opening edit dialog with data:', dialogData);

        const dialogRef = this.dialog.open(AddModelDialogComponent, {
          width: '600px',
          data: dialogData,
        });

        // eslint-disable-next-line @typescript-eslint/no-shadow
        dialogRef.afterClosed().subscribe((result) => {
          if (result) {
            // Check if result contains needsRebuild flag (edit mode format)
            if (result.forecastData !== undefined && result.needsRebuild !== undefined) {
              if (result.needsRebuild) {
                // Show confirmation dialog for rebuild
                this.dialogService.confirm(
                  this.translate.instant('forecast.rebuild-model-title'),
                  this.translate.instant('forecast.rebuild-model-text'),
                  this.translate.instant('action.cancel'),
                  this.translate.instant('forecast.rebuild'),
                  true
                ).subscribe((confirmed) => {
                  if (confirmed) {
                    // User confirmed rebuild
                    this.updateForecast(result.forecastData, true);
                  } else {
                    // User cancelled, just close without updating
                    console.log('Model rebuild cancelled by user');
                  }
                });
              } else {
                // No significant changes, just update without rebuild
                this.updateForecast(result.forecastData, false);
              }
            } else {
              // Shouldn't happen in edit mode, but handle it gracefully
              console.warn('Unexpected result format from edit dialog:', result);
              this.updateForecast(result, false);
            }
          }
        });
      },
      (error) => {
        console.error('Error fetching forecast data for editing:', error);
      }
    );
  }

  updateForecast(forecastData: any, shouldRebuild: boolean): void {
    this.predictiveModelsService.updatePredictiveModel(forecastData).subscribe(
      (response) => {
        console.log('Forecast updated successfully:', response);

        // Update algorithm labels immediately from the saved data
        this.forecastAlgorithm = forecastData.forecastAlgorithm;
        this.anomalyAlgorithm = forecastData.anomalyAlgorithm;

        // If rebuild was requested, trigger activate command
        if (shouldRebuild) {
          console.log('Triggering model rebuild (activate)...');
          // Update status to pending immediately to show rebuild is in progress
          this.status = 'pending';
          this.progressMessage = {
            step: 'Starting rebuild',
            progress: 0
          };
          this.activateModel();
        } else {
          // Just refresh the current model to reflect changes
          this.refreshModel();
        }
      },
      (error) => {
        console.error('Error updating forecast:', error);
      }
    );
  }

  // Test method to trigger a test anomaly alert
  testAnomalyAlert(): void {
    console.log('[MODEL] Testing anomaly alert...');
    if (this.anomalyAlertsComponent) {
      this.anomalyAlertsComponent.addTestAlert();
    } else {
      console.error('[MODEL] AnomalyAlertsComponent not found');
    }
  }

  deleteModel(): void {
    if (!this.trueId) {
      console.error('No model ID available for deletion');
      return;
    }

    const modelName = this.getModelDisplayName(this.models.find(m => m.trueId === this.trueId));

    this.dialogService.confirm(
      this.translate.instant('forecast.delete-model-title'),
      this.translate.instant('forecast.delete-model-text', { modelName }),
      this.translate.instant('action.no'),
      this.translate.instant('action.yes'),
      true
      // eslint-disable-next-line @typescript-eslint/no-shadow
    ).subscribe((result) => {
      if (result) {
        this.predictiveModelsService.deletePredictiveModel(this.trueId).subscribe(
          () => {
            // console.log('Model deleted successfully');
            // Navigate back to predictive maintenance page
            this.router.navigate(['/predictive-maintenance']);
          },
          (error) => {
            console.error('Error deleting model:', error);
          }
        );
      }
    });
  }

  addForecast(forecast: any): void {
    // Add hidden: true to viewPreferences
    if (!forecast.viewPreferences) {
      forecast.viewPreferences = JSON.stringify({ hidden: true });
    } else {
      try {
        const prefs = typeof forecast.viewPreferences === 'string' ? JSON.parse(forecast.viewPreferences) : forecast.viewPreferences;
        prefs.hidden = true;
        forecast.viewPreferences = JSON.stringify(prefs);
      } catch {
        forecast.viewPreferences = JSON.stringify({ hidden: true });
      }
    }

    // Old logic commented out:
    // this.predictiveModelsService.addPredictiveModelConfig(forecast).subscribe(
    //   (response) => {
    //     ...
    //   },
    //   (error) => {
    //     ...
    //   }
    // );

    // New logic: Save config with hidden: true
    this.predictiveModelsService.addPredictiveModelConfig(forecast).subscribe(
      (response) => {
        console.log('Forecast created successfully:', response);
        const newModelId: string = typeof response.id === 'string' ? response.id : response.id?.id;
        if (newModelId) {
          const newModel: Order = {
            id: response.name || newModelId.substring(0, 8),
            trueId: newModelId,
            device: '',
            date: new Date().toISOString()
          };
          if (this.models) {
            this.models.push(newModel);
            this.updateFilteredModels();
            this.fetchModelNames();
          }
          this.router.navigate(['/predictive-maintenance/model', newModelId], {
            state: { forecastData: this.models || [newModel] }
          });
        } else {
          console.warn('Model ID not found in response, navigating to PM list');
          this.router.navigateByUrl('/PM');
        }
      },
      (error) => {
        console.error('Error adding forecast:', error);
      }
    );
  }

  refreshModel(): void {
    // Refresh the current forecast model data and status
    if (this.trueId) {
      this.fetchPredictiveModelConfig(this.trueId);
      // this.getModelStatus();
    }
  }

  // getModelStatus(): void {
  //   // Fetch the model status from the backend
  //   if (this.trueId) {
  //     this.predictiveModelsService.getPredictiveModelStatus(this.trueId).subscribe(
  //       (response) => {
  //         console.log('Model status fetched:', response);
  //         this.status = response.status;
  //       },
  //       (error) => {
  //         console.error('Error fetching model status:', error);
  //         // Default to inactive if status fetch fails
  //         this.status = 'inactive';
  //       }
  //     );
  //   }
  // }


  activationProgress = '';

  activationComplete = false;

  predictions: any = null;

  logs: string[] = [];

  isWsConnected = false;

  isActivating = false;

  progressMessage: { step: string; progress: number } | null = null;

  activateModel(): void {
    // console.log('Activating model:', this.trueId);
    if (!this.trueId) {
      return;
    }
    this.isActivating = true;
    this.activationProgress = '';
    this.activationComplete = false;
    this.predictions = null;
    this.logs = [];
    // Only reset progressMessage if it's not already set (to preserve rebuild message)
    if (!this.progressMessage) {
      this.progressMessage = null;
    }
    // Set status to pending if not already set
    if (this.status !== 'pending') {
      this.status = 'pending';
    }
    this.modelWebSocketService.sendActivateCommand(this.trueId).subscribe((msg) => {
      this.handleWebSocketMessage(msg);
    });
    // this.displayLogsTooltip();
  }

  private shouldShowLogsTooltip(): boolean {
    // Always show for testing purposes
    return true;

    // Uncomment below for production behavior
    // try {
    //   const dontShow = localStorage.getItem(this.LOGS_TOOLTIP_PREFERENCE_KEY);
    //   return dontShow !== 'true';
    // } catch (error) {
    //   console.warn('Error checking logs tooltip preference:', error);
    //   return true;
    // }
  }

  private displayLogsTooltip(): void {
    if (!this.shouldShowLogsTooltip() || !this.logsButton) {
      return;
    }

    this.positionLogsTooltip();
    this.showLogsTooltip = true;
  }

  closeLogsTooltip(): void {
    this.showLogsTooltip = false;
  }

  confirmLogsTooltip(): void {
    if (this.dontShowLogsTooltipAgain) {
      try {
        localStorage.setItem(this.LOGS_TOOLTIP_PREFERENCE_KEY, 'true');
      } catch (error) {
        console.warn('Error saving logs tooltip preference:', error);
      }
    }
    this.showLogsTooltip = false;
  }

  private handleWebSocketMessage(msg: any): void {
    if (!msg) {
      return;
    }

    switch (msg.type) {
      case 'progress':
        // Update progress message for UI
        this.progressMessage = {
          step: msg.step || 'Processing',
          progress: msg.progress || 0
        };
        // Also update status to show pending state
        this.status = 'pending';
        break;
      case 'complete':
        // Clear progress and refresh status
        this.progressMessage = null;
        this.activationComplete = true;
        this.status = 'active';
        this.anomaliesComponent?.setStreamStatus(true, null);
        // Show the logs tooltip after activation
        // this.displayLogsTooltip();
        // this.getModelStatus();
        break;
      case 'error':
        // Clear progress and mark as failed
        this.progressMessage = null;
        this.status = 'failed';
        break;
    }
  }

  // Methods to toggle collapse/expand states
  toggleTimeSeriesChart(): void {
    this.timeSeriesChartCollapsed = !this.timeSeriesChartCollapsed;
    this.saveCollapsedStates();

    // Trigger window resize event after animation completes to resize charts
    // The animation duration is 300ms (defined in the slideCollapse animation)
    setTimeout(() => {
      window.dispatchEvent(new Event('resize'));
    }, 350);
  }

  toggleForecastChart(): void {
    this.forecastChartCollapsed = !this.forecastChartCollapsed;
    this.saveCollapsedStates();

    // Trigger window resize event after animation completes to resize charts
    // The animation duration is 300ms (defined in the slideCollapse animation)
    setTimeout(() => {
      window.dispatchEvent(new Event('resize'));
    }, 350);
  }

  toggleAnomalies(): void {
    this.anomaliesCollapsed = !this.anomaliesCollapsed;
    this.saveCollapsedStates();
  }

  // Methods to persist collapsed states
  private loadCollapsedStates(): void {
    try {
      console.log('Loading collapsed states for model:', this.trueId || 'default');
      const savedStates = localStorage.getItem(
        'forecast-dashboard-collapsed-states-' + (this.trueId || 'default')
      );
      console.log(savedStates);
      if (savedStates) {
        const states = JSON.parse(savedStates);
        this.timeSeriesChartCollapsed = states.timeSeriesChartCollapsed || false;
        this.forecastChartCollapsed = states.forecastChartCollapsed || false;
        this.anomaliesCollapsed = states.anomaliesCollapsed || false;
      }
    } catch (error) {
      console.warn('Error loading collapsed states:', error);
    }

    // Load view preferences from forecast model
    this.loadViewPreferences();
  }

  private saveCollapsedStates(): void {
    try {
      const states = {
        timeSeriesChartCollapsed: this.timeSeriesChartCollapsed,
        forecastChartCollapsed: this.forecastChartCollapsed,
        anomaliesCollapsed: this.anomaliesCollapsed,
      };
      localStorage.setItem(
        'forecast-dashboard-collapsed-states-' + (this.trueId || 'default'),
        JSON.stringify(states)
      );
    } catch (error) {
      console.warn('Error saving collapsed states:', error);
    }
  }

  // View selector methods
  toggleViewSelector(): void {
    this.showViewSelector = !this.showViewSelector;
  }

  selectView(viewValues: ForecastViewType[]): void {
    this.selectedViews = viewValues;
    this.showViewSelector = false;
    this.saveViewPreferences();
  }

  isViewSelected(viewType: ForecastViewType): boolean {
    return this.selectedViews.includes(viewType);
  }

  toggleView(viewType: ForecastViewType, checked: boolean): void {
    if (checked) {
      if (!this.selectedViews.includes(viewType)) {
        this.selectedViews.push(viewType);
      }
    } else {
      this.selectedViews = this.selectedViews.filter((v) => v !== viewType);
    }
    this.saveViewPreferences();
  }

  toggleSensorTelemetry(checked: boolean): void {
    this.hideSensorTelemetry = !checked;
    this.saveViewPreferences();
  }

  getCurrentViewLabel(): string {
    if (this.selectedViews.length === 2) {
      return 'Both Views';
    } else if (this.selectedViews.includes(ForecastViewType.FORECAST)) {
      return 'Forecast Only';
    } else if (this.selectedViews.includes(ForecastViewType.ANOMALIES)) {
      return 'Anomalies Only';
    }
    return 'No Views Selected';
  }

  shouldShowForecastChart(): boolean {
    // Show forecast charts if any sensor widget is visible
    return this.attributes?.some(attr => this.isWidgetVisible(attr.key)) ?? true;
  }

  shouldShowAnomalies(): boolean {
    return this.isWidgetVisible('anomalies');
  }

  private loadViewPreferences(): void {
    if (!this.trueId) {
      return;
    }

    // Load view preferences from forecast entity
    this.predictiveModelsService.getPredictiveModel(this.trueId).subscribe(
      (forecast) => {
        const preferences = parseForecastViewPreferences(
          forecast.viewPreferences || ''
        );
        this.selectedViews = preferences.selectedViews;
        this.selectedSensor = preferences.selectedSensor || 'rotate';
        this.hideSensorTelemetry = preferences.hideSensorTelemetry || false;
        this.timewindow = preferences.timewindow || this.timewindow;
        this.hiddenWidgets = new Set(preferences.hiddenWidgets || []);
        this.currentViewPreferences = preferences;
      },
      (error) => {
        console.warn(
          'Error loading forecast data for view preferences:',
          error
        );
        this.selectedViews = [
          ForecastViewType.FORECAST,
          ForecastViewType.ANOMALIES,
        ]; // Default fallback
        this.selectedSensor = 'rotate';
        this.hideSensorTelemetry = false;
        this.hiddenWidgets = new Set();
        this.currentViewPreferences = {
          selectedViews: this.selectedViews,
          selectedSensor: this.selectedSensor,
          hideSensorTelemetry: this.hideSensorTelemetry,
          timewindow: this.timewindow,
          sensorColors: {},
          hiddenWidgets: [],
        };
      }
    );
  }

  private saveViewPreferences(): void {
    if (!this.trueId) {
      return;
    }

    // Get the current forecast data and update the view preferences
    this.predictiveModelsService.getPredictiveModel(this.trueId).subscribe(
      (forecast) => {
        const preferences: ForecastViewPreferences = {
          selectedViews: this.selectedViews,
          selectedSensor: this.selectedSensor,
          hideSensorTelemetry: this.hideSensorTelemetry,
          timewindow: this.timewindow,
          sensorColors: this.currentViewPreferences?.sensorColors || {},
          hiddenWidgets: Array.from(this.hiddenWidgets),
        };

        // Update the forecast with new view preferences
        const updatedForecast = {
          ...forecast,
          viewPreferences: stringifyForecastViewPreferences(preferences),
        };

        // Save the updated forecast
        this.predictiveModelsService.updatePredictiveModel(updatedForecast).subscribe(
          (response) => {
            // console.log(
            //   'View preferences saved successfully to database for forecast:',
            //   this.trueId
            // );
          },
          (error) => {
            console.error('Error saving view preferences to database:', error);
            // Fallback to localStorage if database save fails
            this.fallbackToLocalStorage();
          }
        );
      },
      (error) => {
        console.error(
          'Error loading forecast for view preferences save:',
          error
        );
        // Fallback to localStorage if forecast load fails
        this.fallbackToLocalStorage();
      }
    );
  }

  private fallbackToLocalStorage(): void {
    try {
      const preferences: ForecastViewPreferences = {
        selectedViews: this.selectedViews,
        selectedSensor: this.selectedSensor,
      };
      localStorage.setItem(
        `forecast-view-${this.trueId}`,
        stringifyForecastViewPreferences(preferences)
      );
      // console.log(
      //   'View preferences saved to localStorage as fallback for forecast:',
      //   this.trueId
      // );
    } catch (error) {
      console.error(
        'Error saving view preferences to localStorage fallback:',
        error
      );
    }
  }

  /**
   * Handle sensor change from forecast chart
   */
  onSensorChanged(sensor: string): void {
    this.selectedSensor = sensor;
    this.saveViewPreferences();
  }

  /**
   * Handle view preferences change (e.g., sensor colors updated)
   */
  onViewPreferencesChanged(preferences: ForecastViewPreferences): void {
    this.currentViewPreferences = preferences;
    this.saveViewPreferences();
  }

  /**
   * Get the current color for a sensor
   */
  getSensorColor(sensor: string): string {
    return this.currentViewPreferences?.sensorColors?.[sensor] || this.availableColors[0];
  }

  /**
   * Update sensor color and save to preferences
   */
  updateSensorColor(sensor: string, color: string): void {
    if (!this.currentViewPreferences) {
      this.currentViewPreferences = {
        selectedViews: this.selectedViews,
        selectedSensor: this.selectedSensor,
        hideSensorTelemetry: this.hideSensorTelemetry,
        timewindow: this.timewindow,
        sensorColors: {},
      };
    }

    if (!this.currentViewPreferences.sensorColors) {
      this.currentViewPreferences.sensorColors = {};
    }

    // Create a new object reference to trigger Angular change detection
    this.currentViewPreferences = {
      ...this.currentViewPreferences,
      sensorColors: {
        ...this.currentViewPreferences.sensorColors,
        [sensor]: color
      }
    };

    this.saveViewPreferences();
  }

  onTimewindowChanged(timewindow: Timewindow): void {
    // Enforce correct mode structure
    if (timewindow.selectedTab === 0 /* TimewindowType.REALTIME */) {
      timewindow.history = undefined;
      if (!timewindow.realtime) {
        timewindow.realtime = {
          realtimeType: 0,
          interval: 60000,
          timewindowMs: 600000,
          quickInterval: QuickTimeInterval.CURRENT_DAY
        };
      }
    } else if (timewindow.selectedTab === 1 /* TimewindowType.HISTORY */) {
      timewindow.realtime = undefined;
      if (!timewindow.history) {
        timewindow.history = {
          historyType: 0,
          interval: 60000,
          timewindowMs: 600000,
          quickInterval: QuickTimeInterval.CURRENT_DAY
        };
      }
    }
    this.timewindow = timewindow;
    this.saveViewPreferences();
  }

  // Document click listener for closing dropdown
  private addDocumentClickListener(): void {
    document.addEventListener('click', (event: Event) => {
      const target = event.target as HTMLElement;
      const viewSelectorButton = target.closest('.view-selector-button');
      const viewSelectorDropdown = target.closest('.view-selector-dropdown');

      if (
        !viewSelectorButton &&
        !viewSelectorDropdown &&
        this.showViewSelector
      ) {
        this.showViewSelector = false;
      }
    });
  }

  // Forecast status helper methods
  getForecastStatusDisplayText(status: string | boolean): string {
    const forecastStatus = getForecastStatusFromString(status);
    switch (forecastStatus) {
      case ForecastStatus.ACTIVE:
        return this.translate.instant('forecast.status.active');
      case ForecastStatus.PENDING:
        return this.translate.instant('forecast.status.pending');
      case ForecastStatus.FAILED:
        return this.translate.instant('forecast.status.failed');
      case ForecastStatus.INACTIVE:
      default:
        return this.translate.instant('forecast.status.inactive');
    }
  }

  getForecastStatusClass(status: string | boolean): string {
    const forecastStatus = getForecastStatusFromString(status);
    switch (forecastStatus) {
      case ForecastStatus.ACTIVE:
        return 'status-active';
      case ForecastStatus.PENDING:
        return 'status-pending';
      case ForecastStatus.FAILED:
        return 'status-failed';
      case ForecastStatus.INACTIVE:
      default:
        return 'status-inactive';
    }
  }

  isForecastActive(): boolean {
    return isForecastActive({ status: this.status });
  }

  /**
   * Load the last read log timestamp from localStorage
   */
  private loadLastReadLogTimestamp(): void {
    if (!this.trueId) {
      return;
    }
    const key = this.LAST_READ_LOG_KEY_PREFIX + this.trueId;
    const stored = localStorage.getItem(key);
    if (stored) {
      this.lastReadLogTimestamp = parseInt(stored, 10);
    } else {
      this.lastReadLogTimestamp = 0;
    }
  }

  /**
   * Save the last read log timestamp to localStorage
   */
  private saveLastReadLogTimestamp(): void {
    if (!this.trueId) {
      return;
    }
    const key = this.LAST_READ_LOG_KEY_PREFIX + this.trueId;
    localStorage.setItem(key, Date.now().toString());
    this.lastReadLogTimestamp = Date.now();
  }

  /**
   * Navigate to the device details page
   */
  navigateToDevice(): void {
    if (this.deviceId) {
      this.router.navigate(['/entities/devices', this.deviceId]);
    }
  }

  /**
   * Process a single anomaly prediction result and convert it to an AnomalyReport
   */
  private processAnomalyPrediction(predictionResult: any): AnomalyReport {
    const confidence = predictionResult.general_failure_probability
      ? Math.round(predictionResult.general_failure_probability * 100)
      : 0;
    const severity = confidence >= 90 ? 'Critical' : confidence >= 70 ? 'Major' : 'Minor';

    // Normalize timeRange -> startTime/endTime with 1 hour range
    let startTime: string | number | undefined;
    let endTime: string | number | undefined;
    if (predictionResult.datetime) {
      const parts = (predictionResult.datetime || '').toString().split('/');
      if (parts.length === 2) {
        startTime = parts[0];
        endTime = parts[1];
      } else {
        // Single datetime - create 1 hour range
        const startDate = new Date(predictionResult.datetime);
        const endDate = new Date(startDate.getTime() + 60 * 60 * 1000); // Add 1 hour
        startTime = startDate.toISOString();
        endTime = endDate.toISOString();
      }
    }

    // Get component type, remove "Unknown" fallback
    const componentType = predictionResult.predicted_failing_component || '';

    return {
      timeRange: predictionResult.datetime || '',
      startTime,
      endTime,
      confidence,
      affectedMetrics: predictionResult.predicted_failing_component ? [predictionResult.predicted_failing_component] : [],
      id: predictionResult.id || `${this.trueId || 'forecast'}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      reportEntity: this.deviceId,
      errorName: predictionResult.predicted_failing_component || '',
      severity,
      creationDate: predictionResult.datetime || new Date().toISOString(),
      componentType,
      deviceType: '',
      location: '',
      description: 'Predicted failure for component ' + (predictionResult.predicted_failing_component || ''),
      status: 'Active',
    };
  }
}
