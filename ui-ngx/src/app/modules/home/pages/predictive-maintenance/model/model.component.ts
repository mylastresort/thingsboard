import {
  ViewChild,
  ElementRef,
  ChangeDetectorRef,
  NgZone,
  Input,
  OnDestroy,
  EventEmitter,
} from "@angular/core";
import { Component, AfterViewInit } from "@angular/core";
import { ActivatedRoute, Router } from "@angular/router";
import { AppState } from "@app/core/core.state";
import { PredictiveModelsService } from "@app/core/http/forecast.service";
import { DeviceService } from "@app/core/http/device.service";
import { DialogService } from "@app/core/services/dialog.service";
import { Order } from "@app/modules/home/models/predictive-maintenance.models";
import { PageComponent } from "@app/shared/public-api";
import {
  ForecastStatus,
  getForecastStatusFromString,
  isForecastActive,
  ForecastAttribute,
} from "@app/shared/models/forecast.models";
import {
  ForecastViewType,
  ForecastViewPreferences,
  parseForecastViewPreferences,
  stringifyForecastViewPreferences,
} from "@app/shared/models/forecast-view-preferences.models";
import { Store } from "@ngrx/store";
import { MatDialog } from "@angular/material/dialog";
import { AddModelDialogComponent } from "../../../components/predictive-maintenance/components/model/add-model-dialog/add-model-dialog.component";
import { ModelSelectionDialogComponent } from "./model-selection-dialog/model-selection-dialog.component";
import { ModelLogsDialogComponent } from "./model-logs-dialog/model-logs-dialog.component";
import {
  AnomaliesComponent,
  AnomalyReport,
} from "../../../components/predictive-maintenance/components/anomalies/anomalies.component";
import { CommonModule } from "@angular/common";
import { TimeSeriesTelemetryComponent } from "../../../components/predictive-maintenance/components/time-series-telemetry/time-series-telemetry.component";
import { MatFormFieldModule } from "@angular/material/form-field";
import { MatSelectModule } from "@angular/material/select";
import { MatIconModule } from "@angular/material/icon";
import { MatButtonModule } from "@angular/material/button";
import { MatInputModule } from "@angular/material/input";
import { FormsModule } from "@angular/forms";
import { MatTooltipModule } from "@angular/material/tooltip";
import { MatCheckboxModule } from "@angular/material/checkbox";
import { TranslateModule, TranslateService } from "@ngx-translate/core";
import {
  trigger,
  state,
  style,
  transition,
  animate,
} from "@angular/animations";
import {
  EModelType,
  ModelWebSocketService,
} from "@app/core/http/model-websocket.service";
import { ModelLogsNotifierService } from "./model-logs-notifier.service";
import { QuickTimeInterval, Timewindow } from "@shared/models/time/time.models";
import { flatMap } from "lodash";
import { mergeMap, Observable } from "rxjs";
import { distinctUntilChanged, filter, share } from "rxjs/operators";
import { AnomalyAlertsComponent } from "../../../components/predictive-maintenance/components/anomaly-alerts/anomaly-alerts.component";
import { FailureModeComponent } from "../../../components/predictive-maintenance/components/failure-mode/failure-mode.component";
import { ForecastSensorPrediction } from "@core/event-models/ForecastSensorPrediction";
import { ForecastPredictionLogEntry } from "@core/event-models/ForecastPredictionLogEntry";
import { AnomalyPredictionLogEntry } from "@app/core/event-models/AnomalyPredictionLogEntry";
import { GenericLogEntry } from "@core/event-models/GenericLogEntry";

@Component({
  selector: "tb-forecast",
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
    FailureModeComponent,
    MatTooltipModule,
    MatCheckboxModule,
    TranslateModule,
  ],
  templateUrl: "./model.component.html",
  styleUrls: ["./model.component.scss"],
  animations: [
    trigger("slideCollapse", [
      state(
        "expanded",
        style({ height: "*", opacity: 1, overflow: "visible" })
      ),
      state(
        "collapsed",
        style({ height: "0", opacity: 0, overflow: "hidden" })
      ),
      transition(
        "expanded <=> collapsed",
        animate("300ms cubic-bezier(0.4, 0.0, 0.2, 1)")
      ),
    ]),
  ],
})
export class ModelComponent
  extends PageComponent
  implements Order, OnDestroy, AfterViewInit
{
  @ViewChild(AnomaliesComponent) anomaliesComponent?: AnomaliesComponent;

  activeDashboardTab: "forecast" | "anomalies" | "failure-mode" = "forecast";

  timewindow: Timewindow = {
    displayValue: "",
    hideAggregation: false,
    hideAggInterval: false,
    hideTimezone: false,
    selectedTab: 0,
    realtime: {
      realtimeType: 0,
      interval: 60000,
      timewindowMs: 600000,
      quickInterval: QuickTimeInterval.CURRENT_DAY,
    },
    history: undefined,
  };

  attributes!: ForecastAttribute[];

  @ViewChild(AnomalyAlertsComponent)
  anomalyAlertsComponent?: AnomalyAlertsComponent;

  @ViewChild("logsButton", { read: ElementRef }) logsButton?: ElementRef;

  deviceId!: string;

  Attributes!: string[];

  forecastData: {
    [sensor: string]: ForecastSensorPrediction;
  } = {};

  @Input() forecastMaxSteps!: number;

  forecastHistoryPoint$ = new EventEmitter<{
    sensor: string;
    timestamp: number;
    value: number;
  }>();

  modelsData!: Order[];

  historyForecastPredictions: any;

  models!: Order[];

  filteredModels: Order[] = [];

  modelSearchTerm = "";

  modelNames = new Map<string, string>();

  id!: string;

  trueId!: string;

  device!: string;

  forecastName!: string;

  date!: string;

  status = "inactive";

  forecastAlgorithm!: string;

  anomalyAlgorithm!: string;

  forecastGrouping = "hourly";

  forecastChartCollapsed = false;

  anomaliesCollapsed = false;

  timeSeriesChartCollapsed = false;

  timewindowsPerSensor: { [sensor: string]: Timewindow } = {};

  selectedViews: ForecastViewType[] = [];

  selectedSensor = "rotate";

  hideSensorTelemetry = false;

  currentViewPreferences!: ForecastViewPreferences;

  availableColors: string[] = ModelComponent.FULL_COLOR_PALETTE.filter(
    (color) => !ModelComponent.RESERVED_COLORS.includes(color)
  );

  showViewSelector = false;

  sensorColorsExpanded = false;

  widgetsExpanded = false;

  hiddenWidgets = new Set<string>();

  unreadLogs = false;

  showLogsTooltip = false;

  dontShowLogsTooltipAgain = false;

  logsTooltipPosition = { top: -1000000, left: -1000000, zIndex: -1000 };

  logsObservable!: Observable<
    AnomalyPredictionLogEntry | ForecastPredictionLogEntry | GenericLogEntry
  >;

  forecastJobRunning = false;

  forecastJobPaused = false;

  activationProgress = "";

  activationComplete = false;

  predictions: any = null;

  logs: string[] = [];

  isWsConnected = false;

  isActivating = false;

  progressMessage: { step: string; progress: number } | null = null;
  private subscriptions: Array<any> = [];

  private notifierSubscription: any = null;

  private routeParamsSubscription: any = null;

  private static readonly RESERVED_COLORS = [
    TimeSeriesTelemetryComponent.FORECAST_COLOR,
    TimeSeriesTelemetryComponent.PREDICTIONS_COLOR,
  ];

  private static readonly FULL_COLOR_PALETTE: string[] = [
    "#2196f3",
    "#f44336",
    "#9c27b0",
    "#00bcd4",
    "#ffeb3b",
    "#e91e63",
    "#009688",
    "#ff5722",
    "#673ab7",
    "#3f51b5",
    "#cddc39",
    "#ffc107",
    "#795548",
    "#607d8b",
    "#8bc34a",
    "#03a9f4",
    "#ff6f00",
    "#d32f2f",
  ];

  private readonly LAST_READ_LOG_KEY_PREFIX = "model-last-read-log-";
  private readonly LOGS_TOOLTIP_PREFERENCE_KEY = "model-logs-tooltip-dont-show";

  private lastReadLogTimestamp = 0;

  private forecastPredictionLogs$!: Observable<ForecastPredictionLogEntry>;

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
    private ngZone: NgZone
  ) {
    super(store);
  }

  onChildTimewindowChange(sensor: string, tw: Timewindow): void {
    this.timewindowsPerSensor = {
      ...this.timewindowsPerSensor,
      [sensor]: tw,
    };
  }

  isWidgetVisible(widgetKey: string): boolean {
    return !this.hiddenWidgets.has(widgetKey);
  }

  toggleWidgetVisibility(widgetKey: string, visible: boolean): void {
    if (visible) {
      this.hiddenWidgets.delete(widgetKey);
    } else {
      this.hiddenWidgets.add(widgetKey);
      if (
        widgetKey === "anomalies" &&
        this.activeDashboardTab === "anomalies"
      ) {
        this.activeDashboardTab = "forecast";
      }
    }
    this.saveViewPreferences();
  }

  ngOnDestroy(): void {
    this.predictiveModelsService.anomalies = [];
    if (this.logsObservable) {
      this.logsObservable = new Observable<GenericLogEntry>();
    }

    if (this.trueId) {
      this.modelWebSocketService.unsubscribeFromModelStatus(this.trueId);
      this.modelWebSocketService.unsubscribeFromLogs(this.trueId);
    }
    this.modelWebSocketService.disconnect();

    if (this.notifierSubscription) {
      this.notifierSubscription.unsubscribe();
      this.notifierSubscription = null;
    }

    if (this.routeParamsSubscription) {
      this.routeParamsSubscription.unsubscribe();
      this.routeParamsSubscription = null;
    }

    this.subscriptions.forEach((sub) => sub.unsubscribe());
  }

  onAnomalyRefreshFilter(range: { startTs: number; endTs: number }): void {
    this.fetchAnomalyHistoryPredictions(range.startTs, range.endTs);
  }

  fetchAnomalyHistoryPredictions(startTs?: number, endTs?: number) {
    if (!this.trueId) {
      console.warn("[MODEL] Cannot fetch history: No model ID available");
      return;
    }

    this.predictiveModelsService
      .fetchHistoryPredictions(this.trueId, "Anomaly", startTs, endTs, 100)
      .subscribe({
        next: (response) => {
          if (response.predictions && response.predictions.length > 0) {
            let addedCount = 0;
            response.predictions.forEach((prediction: any) => {
              try {
                const predictionValue =
                  typeof prediction.predictionValue === "string"
                    ? JSON.parse(prediction.predictionValue)
                    : prediction.predictionValue;
                if (predictionValue.failure_predicted === true) {
                  const anomaly = this.convertPredictionToAnomaly(
                    prediction,
                    predictionValue
                  );
                  this.predictiveModelsService.sendAnomaly(anomaly);
                  addedCount++;
                }
              } catch (error) {
                console.error(
                  "[MODEL] Error processing historical prediction:",
                  error,
                  prediction
                );
              }
            });
          }
        },
        error: (error) => {
          console.error("[MODEL] Error fetching anomaly history:", error);
        },
      });
  }

  subscribeToAnomalyPredictions() {
    const anomalyPredictionLogs$ = this.logsObservable!.pipe(
      filter(
        (log) =>
          !!(
            log.type?.toLowerCase() === "anomaly" &&
            log.level?.toLowerCase() === "prediction"
          )
      )
    ) as Observable<AnomalyPredictionLogEntry>;

    const anomalyPredictionLogsSubscription = anomalyPredictionLogs$.subscribe(
      (log) => {
        const logTimestamp = log.timestamp
          ? new Date(log.timestamp).getTime()
          : Date.now();
        if (logTimestamp > this.lastReadLogTimestamp) {
          this.ngZone.run(() => {
            this.unreadLogs = true;
          });
          try {
            if (this.trueId) {
              this.logsNotifier.setUnread(this.trueId, true);
            }
          } catch (e) {
            console.error("[MODEL] Error setting unread status:", e);
          }
        }

        if (log.level.toLowerCase() === "prediction") {
          if (typeof log.message !== "string" && log.message?.result) {
            const results = Array.isArray(log.message.result)
              ? log.message.result
              : [log.message.result];

            results.forEach((predictionItem: any) => {
              if (predictionItem.failure_predicted === true) {
                const anomaly = this.processAnomalyPrediction(predictionItem);
                this.anomaliesComponent?.addAnomaly(anomaly);
              }
            });
          }
        }
      }
    );

    this.subscriptions.push(anomalyPredictionLogsSubscription);
  }

  subscribeToForecastPredictions(forecastId: string) {
    this.forecastPredictionLogs$ = this.logsObservable.pipe(
      filter(
        (log) =>
          (log.level &&
            log.level.toLowerCase() === "prediction" &&
            log.type &&
            log.type.toLowerCase() === "forecast") ||
          (!!log.source && log.source.toLowerCase() === "forecastmodel")
      )
    ) as Observable<ForecastPredictionLogEntry>;

    const forecastLogsSubscription = this.forecastPredictionLogs$.subscribe(
      (log) => {
        if (log.message.prediction_type === "forecast") {
          const results = log.message.result;

          if (results) {
            const predictionInfo = (results as any).prediction_info;
            const recentPointTs = predictionInfo?.recent_point_ts;
            const groupByPeriodMs = predictionInfo?.group_by_period_ms;
            const sensorName: string = (log.message as any).sensor;
            const forecast: number[] = (results as any).forecast;

            this.forecastData = {
              ...this.forecastData,
              [sensorName]: {
                forecast: Array.from(forecast),
                timestamp: forecast.map(
                  (_, i) => recentPointTs + (i + 2) * groupByPeriodMs
                ),
              },
            };
            this.cdr.detectChanges();
          } else {
            console.warn("[MODEL] No forecast results to process");
          }
        } else if (log.message.prediction_type === "history") {
          this.historyForecastPredictions = log.message;
        }
      }
    );

    this.subscriptions.push(forecastLogsSubscription);
  }

  changeModel(value: any) {
    this.router.navigateByUrl("/predictive-maintenance/model/" + value);

    this.deviceId = "";
    this.Attributes = [];
    this.trueId = value;
    this.forecastAlgorithm = "";
    this.anomalyAlgorithm = "";
    this.forecastGrouping = "hourly";
    this.fetchPredictiveModelConfig(value);
  }

  openModelSelectionDialog(): void {
    const panelClass =
      typeof document !== "undefined" &&
      document.body.classList.contains("tb-dark")
        ? "tb-dark"
        : undefined;
    const dialogRef = this.dialog.open(ModelSelectionDialogComponent, {
      width: "600px",
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
    if (history.state && history.state.forecastData) {
      this.modelsData = history.state.forecastData;
    } else {
      console.error("No forecast data passed.");
    }
    this.addDocumentClickListener();
    this.modelWebSocketService.connect();
    this.init();
  }

  getModelDisplayName(model: any): string {
    return this.modelNames.get(model.trueId) || model.id;
  }

  filterModels(): void {
    if (!this.modelSearchTerm || this.modelSearchTerm.trim() === "") {
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

  fetchPredictiveModelConfig(forecastId: string): any {
    this.predictiveModelsService.getPredictiveModel(forecastId).subscribe(
      (data) => {
        this.deviceId = data.deviceId.id;
        this.Attributes = data.attributes.map((attr) => attr.key);
        this.attributes = data.attributes;
        this.initSensorTimewindows();
        if (
          this.Attributes.length > 0 &&
          !this.Attributes.includes(this.selectedSensor)
        ) {
          this.selectedSensor = this.Attributes[0];
        }
        this.trueId = data.id.id;
        this.forecastName = data.name || data.id.id.split("-")[0];
        this.forecastAlgorithm = data.forecastAlgorithm;
        this.anomalyAlgorithm = data.anomalyAlgorithm;
        const additionalData =
          typeof data.additionalData === "string"
            ? JSON.parse(data.additionalData || "{}")
            : data.additionalData || {};
        this.forecastGrouping = additionalData.forecastGrouping || "hourly";
        this.deviceService.getDevice(data.deviceId.id).subscribe(
          (device) => {
            this.device = device.name;
          },
          (error) => {
            console.error("Error fetching device:", error);
            this.device = data.deviceId.id;
          }
        );
      },
      (error) => {
        console.error("Error fetching forecast:", error);
      }
    );
  }

  openCreateModelDialog(): void {
    const dialogRef = this.dialog.open(AddModelDialogComponent, {
      width: "600px",
    });

    dialogRef.afterClosed().subscribe((result) => {
      if (result) {
        this.addForecast(result);
      }
    });
  }

  saveModelConfig(): void {
    if (!this.trueId) {
      console.error("No model currently loaded to save");
      return;
    }
    this.predictiveModelsService.getPredictiveModel(this.trueId).subscribe(
      (data) => {
        const payload: any = JSON.parse(JSON.stringify(data));
        if (payload.id) {
          delete payload.id;
        }
        const baseName = payload.name || `Model_${Date.now()}`;
        const templateName = baseName.endsWith("_template")
          ? baseName
          : baseName + "_template";
        payload.name = templateName;

        try {
          const template = {
            config: payload,
            savedAt: Date.now(),
            deviceId: this.deviceId,
            deviceName: this.device,
          };

          const record = {
            name: templateName,
            config: template,
          };

          this.predictiveModelsService.saveLoadModelConfig(record).subscribe(
            (response) => {
              alert(`Model template "${templateName}" saved successfully`);
            },
            (error) => {
              console.error(
                "Failed to save model template via service:",
                error
              );
              alert("Failed to save model template");
            }
          );

          alert(`Model template "${templateName}" saved successfully`);
        } catch (e) {
          console.error("Failed to save model template to localStorage:", e);
          alert("Failed to save model template");
        }
      },
      (error) => {
        console.error(
          "Failed to fetch current model config for saving:",
          error
        );
        alert("Failed to fetch model configuration");
      }
    );
  }

  openLogsDialog(): void {
    if (!this.trueId) {
      console.error("No model ID available for viewing logs");
      return;
    }

    this.unreadLogs = false;
    this.saveLastReadLogTimestamp();
    try {
      if (this.trueId) {
        this.logsNotifier.markAsRead(this.trueId);
      }
    } catch (e) {
      console.error("[MODEL] Error marking logs as read:", e);
    }

    const dialogRef = this.dialog.open(ModelLogsDialogComponent, {
      width: "900px",
      maxWidth: "95vw",
      height: "80vh",
      data: {
        modelId: this.trueId,
        modelName: this.forecastName || this.trueId,
        deviceId: this.deviceId,
        websocket: null,
        wsUrl: "",
      },
    });
  }

  openForecastLogsDialog(): void {
    if (!this.trueId) {
      console.error("No model ID available for viewing forecast logs");
      return;
    }

    const dialogRef = this.dialog.open(ModelLogsDialogComponent, {
      width: "900px",
      maxWidth: "95vw",
      height: "80vh",
      data: {
        modelId: this.trueId,
        modelName: this.forecastName || this.trueId,
        deviceId: this.deviceId,
        modelTypeFilter: "forecast",
      },
    });
  }

  openAnomalyLogsDialog(): void {
    if (!this.trueId) {
      console.error("No model ID available for viewing anomaly logs");
      return;
    }

    const dialogRef = this.dialog.open(ModelLogsDialogComponent, {
      width: "900px",
      maxWidth: "95vw",
      height: "80vh",
      data: {
        modelId: this.trueId,
        modelName: this.forecastName || this.trueId,
        deviceId: this.deviceId,
        modelTypeFilter: "anomaly",
      },
    });
  }

  pauseForecastJob(): void {
    console.log("[MODEL] pauseForecastJob called", {
      trueId: this.trueId,
      forecastJobRunning: this.forecastJobRunning,
      forecastJobPaused: this.forecastJobPaused,
    });

    if (!this.trueId) {
      console.error("[MODEL] Cannot pause: No forecast ID");
      return;
    }
    this.modelWebSocketService.pauseJob(this.trueId, EModelType.Forecast);
    this.forecastJobPaused = true;
    this.cdr.detectChanges();
  }

  unpauseForecastJob(): void {
    if (!this.trueId) {
      console.error("[MODEL] Cannot unpause: No forecast ID");
      return;
    }
    this.modelWebSocketService.unpauseJob(this.trueId, EModelType.Forecast);
    this.forecastJobPaused = false;
    this.cdr.detectChanges();
  }

  openForecastStatsDialog(): void {
    if (!this.trueId) {
      console.error("No model ID available for viewing forecast stats");
      return;
    }

    // TODO: Create ModelStatsDialogComponent
    // For now, show a placeholder dialog with model info
    this.dialogService.alert(
      "Forecast Training Stats",
      `<div style="text-align: left;">
        <p><strong>Model ID:</strong> ${this.trueId}</p>
        <p><strong>Model Name:</strong> ${this.forecastName || "N/A"}</p>
        <p><strong>Algorithm:</strong> ${this.forecastAlgorithm || "N/A"}</p>
        <p><strong>Device:</strong> ${this.device || "N/A"}</p>
        <p><strong>Status:</strong> ${this.status || "N/A"}</p>
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
      "Close",
      true
    );
  }

  openAnomalyStatsDialog(): void {
    if (!this.trueId) {
      console.error("No model ID available for viewing anomaly stats");
      return;
    }

    // TODO: Create ModelStatsDialogComponent
    // For now, show a placeholder dialog with model info
    this.dialogService.alert(
      "Anomaly Training Stats",
      `<div style="text-align: left;">
        <p><strong>Model ID:</strong> ${this.trueId}</p>
        <p><strong>Model Name:</strong> ${this.forecastName || "N/A"}</p>
        <p><strong>Algorithm:</strong> ${this.anomalyAlgorithm || "N/A"}</p>
        <p><strong>Device:</strong> ${this.device || "N/A"}</p>
        <p><strong>Status:</strong> ${this.status || "N/A"}</p>
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
      "Close",
      true
    );
  }

  openEditModelDialog(): void {
    if (!this.trueId) {
      console.error("No model ID available for editing");
      return;
    }
    this.predictiveModelsService.getPredictiveModel(this.trueId).subscribe(
      (forecastData) => {
        const additionalData =
          typeof forecastData.additionalData === "string"
            ? JSON.parse(forecastData.additionalData || "{}")
            : forecastData.additionalData || {};
        const forecastId =
          typeof forecastData.id === "string"
            ? forecastData.id
            : forecastData.id?.id || this.trueId;
        const forecastGrouping = additionalData.forecastGrouping || "hourly";
        const dialogData = {
          isEdit: true,
          forecastData: {
            id: forecastId,
            trueId: forecastId,
            modelName: forecastData.name || forecastId.split("-")[0],
            device: this.device,
            deviceId: forecastData.deviceId,
            attributes: forecastData.attributes || [],
            attributesText: forecastData.attributes
              ? forecastData.attributes.map((attr) => attr.key).join(", ")
              : "",
            forecastAlgorithm: forecastData.forecastAlgorithm,
            anomalyAlgorithm: forecastData.anomalyAlgorithm,
            forecastGrouping,
            forecastStartDate: forecastData.forecastStartDate,
            forecastEndDate: forecastData.forecastEndDate,
            anomaliesStartDate: forecastData.anomalyStartDate,
            anomaliesEndDate: forecastData.anomalyEndDate,
          },
        };
        const dialogRef = this.dialog.open(AddModelDialogComponent, {
          width: "600px",
          data: dialogData,
        });
        dialogRef.afterClosed().subscribe((result) => {
          if (result) {
            if (
              result.forecastData !== undefined &&
              result.needsRebuild !== undefined
            ) {
              if (result.needsRebuild) {
                this.dialogService
                  .confirm(
                    "Rebuild model",
                    "This change requires rebuilding the model. Do you want to rebuild it now?",
                    "Cancel",
                    "Rebuild",
                    true
                  )
                  .subscribe((confirmed) => {
                    if (confirmed) {
                      this.updateForecast(result.forecastData, true);
                    }
                  });
              } else {
                this.updateForecast(result.forecastData, false);
              }
            } else {
              console.warn(
                "Unexpected result format from edit dialog:",
                result
              );
              this.updateForecast(result, false);
            }
          }
        });
      },
      (error) => {
        console.error("Error fetching forecast data for editing:", error);
      }
    );
  }

  updateForecast(forecastData: any, shouldRebuild: boolean): void {
    this.predictiveModelsService.updatePredictiveModel(forecastData).subscribe(
      (response) => {
        this.forecastAlgorithm = forecastData.forecastAlgorithm;
        this.anomalyAlgorithm = forecastData.anomalyAlgorithm;
        if (shouldRebuild) {
          this.status = "pending";
          this.progressMessage = {
            step: "Starting rebuild",
            progress: 0,
          };
          this.activateModel();
        } else {
          this.refreshModel();
        }
      },
      (error) => {
        console.error("Error updating forecast:", error);
      }
    );
  }

  deleteModel(): void {
    if (!this.trueId) {
      console.error("No model ID available for deletion");
      return;
    }

    const modelName = this.getModelDisplayName(
      this.models.find((m) => m.trueId === this.trueId)
    );

    this.dialogService
      .confirm(
        this.translate.instant("forecast.delete-model-title"),
        this.translate.instant("forecast.delete-model-text", { modelName }),
        this.translate.instant("action.no"),
        this.translate.instant("action.yes"),
        true
      )
      .subscribe((result) => {
        if (result) {
          this.predictiveModelsService
            .deletePredictiveModel(this.trueId)
            .subscribe(
              () => {
                this.router.navigate(["/predictive-maintenance"]);
              },
              (error) => {
                console.error("Error deleting model:", error);
              }
            );
        }
      });
  }

  addForecast(forecast: any): void {
    if (!forecast.viewPreferences) {
      forecast.viewPreferences = JSON.stringify({ hidden: true });
    } else {
      try {
        const prefs =
          typeof forecast.viewPreferences === "string"
            ? JSON.parse(forecast.viewPreferences)
            : forecast.viewPreferences;
        prefs.hidden = true;
        forecast.viewPreferences = JSON.stringify(prefs);
      } catch {
        forecast.viewPreferences = JSON.stringify({ hidden: true });
      }
    }
    this.predictiveModelsService.addPredictiveModelConfig(forecast).subscribe(
      (response) => {
        const newModelId: string =
          typeof response.id === "string" ? response.id : response.id?.id;
        if (newModelId) {
          const newModel: Order = {
            id: response.name || newModelId.substring(0, 8),
            trueId: newModelId,
            device: "",
            date: new Date().toISOString(),
          };
          if (this.models) {
            this.models.push(newModel);
            this.updateFilteredModels();
            this.fetchModelNames();
          }
          this.router.navigate(["/predictive-maintenance/model", newModelId], {
            state: { forecastData: this.models || [newModel] },
          });
        } else {
          console.warn("Model ID not found in response, navigating to PM list");
          this.router.navigateByUrl("/predictive-maintenance");
        }
      },
      (error) => {
        console.error("Error adding forecast:", error);
      }
    );
  }

  refreshModel(): void {
    if (this.trueId) {
      this.fetchPredictiveModelConfig(this.trueId);
      // this.getModelStatus();
    }
  }

  activateModel(): void {
    if (!this.trueId) {
      return;
    }
    this.isActivating = true;
    this.activationProgress = "";
    this.activationComplete = false;
    this.predictions = null;
    this.logs = [];
    if (!this.progressMessage) {
      this.progressMessage = null;
    }
    if (this.status !== "pending") {
      this.status = "pending";
    }
    this.modelWebSocketService
      .sendActivateCommand(this.trueId)
      .subscribe((msg) => {
        this.handleWebSocketMessage(msg);
      });
  }

  closeLogsTooltip(): void {
    this.showLogsTooltip = false;
  }

  confirmLogsTooltip(): void {
    if (this.dontShowLogsTooltipAgain) {
      try {
        localStorage.setItem(this.LOGS_TOOLTIP_PREFERENCE_KEY, "true");
      } catch (error) {
        console.warn("Error saving logs tooltip preference:", error);
      }
    }
    this.showLogsTooltip = false;
  }

  toggleTimeSeriesChart(): void {
    this.timeSeriesChartCollapsed = !this.timeSeriesChartCollapsed;
    this.saveCollapsedStates();
    setTimeout(() => {
      window.dispatchEvent(new Event("resize"));
    }, 350);
  }

  toggleForecastChart(): void {
    this.forecastChartCollapsed = !this.forecastChartCollapsed;
    this.saveCollapsedStates();
    setTimeout(() => {
      window.dispatchEvent(new Event("resize"));
    }, 350);
  }

  toggleAnomalies(): void {
    this.anomaliesCollapsed = !this.anomaliesCollapsed;
    this.saveCollapsedStates();
  }

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
      return "Both Views";
    } else if (this.selectedViews.includes(ForecastViewType.FORECAST)) {
      return "Forecast Only";
    } else if (this.selectedViews.includes(ForecastViewType.ANOMALIES)) {
      return "Anomalies Only";
    }
    return "No Views Selected";
  }

  shouldShowForecastChart(): boolean {
    return (
      this.attributes?.some((attr) => this.isWidgetVisible(attr.key)) ?? true
    );
  }

  shouldShowAnomalies(): boolean {
    return this.isWidgetVisible("anomalies");
  }

  onSensorChanged(sensor: string): void {
    this.selectedSensor = sensor;
    this.saveViewPreferences();
  }

  onViewPreferencesChanged(preferences: ForecastViewPreferences): void {
    this.currentViewPreferences = preferences;
    this.saveViewPreferences();
  }

  getSensorColor(sensor: string): string {
    const explicit = this.currentViewPreferences?.sensorColors?.[sensor];
    if (explicit) {
      return explicit;
    }
    let hash = 0;
    for (let i = 0; i < sensor.length; i++) {
      hash = (hash * 31 + sensor.charCodeAt(i)) | 0;
    }
    return this.availableColors[Math.abs(hash) % this.availableColors.length];
  }

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

    this.currentViewPreferences = {
      ...this.currentViewPreferences,
      sensorColors: {
        ...this.currentViewPreferences.sensorColors,
        [sensor]: color,
      },
    };

    this.saveViewPreferences();
  }

  onTimewindowChanged(timewindow: Timewindow): void {
    if (timewindow.selectedTab === 0) {
      timewindow.history = undefined;
      if (!timewindow.realtime) {
        timewindow.realtime = {
          realtimeType: 0,
          interval: 60000,
          timewindowMs: 600000,
          quickInterval: QuickTimeInterval.CURRENT_DAY,
        };
      }
    } else if (timewindow.selectedTab === 1) {
      timewindow.realtime = undefined;
      if (!timewindow.history) {
        timewindow.history = {
          historyType: 0,
          interval: 60000,
          timewindowMs: 600000,
          quickInterval: QuickTimeInterval.CURRENT_DAY,
        };
      }
    }
    this.timewindow = timewindow;
    this.saveViewPreferences();
  }

  getForecastStatusDisplayText(status: string | boolean): string {
    const forecastStatus = getForecastStatusFromString(status);
    switch (forecastStatus) {
      case ForecastStatus.ACTIVE:
        return this.translate.instant("forecast.status.active");
      case ForecastStatus.PENDING:
        return this.translate.instant("forecast.status.pending");
      case ForecastStatus.FAILED:
        return this.translate.instant("forecast.status.failed");
      case ForecastStatus.INACTIVE:
      default:
        return this.translate.instant("forecast.status.inactive");
    }
  }

  getForecastStatusClass(status: string | boolean): string {
    const forecastStatus = getForecastStatusFromString(status);
    switch (forecastStatus) {
      case ForecastStatus.ACTIVE:
        return "status-active";
      case ForecastStatus.PENDING:
        return "status-pending";
      case ForecastStatus.FAILED:
        return "status-failed";
      case ForecastStatus.INACTIVE:
      default:
        return "status-inactive";
    }
  }

  isForecastActive(): boolean {
    return isForecastActive({ status: this.status });
  }

  navigateToDevice(): void {
    if (this.deviceId) {
      this.router.navigate(["/entities/devices", this.deviceId]);
    }
  }

  private cloneDefaultTimewindow(): Timewindow {
    return {
      displayValue: "",
      hideAggregation: false,
      hideAggInterval: false,
      hideTimezone: false,
      selectedTab: 0,
      realtime: {
        realtimeType: 0,
        interval: 60000,
        timewindowMs: 600000,
        quickInterval: QuickTimeInterval.CURRENT_DAY,
      },
      history: undefined,
    };
  }

  private initSensorTimewindows(): void {
    if (Array.isArray(this.attributes)) {
      const map: { [sensor: string]: Timewindow } = {};
      this.attributes.forEach((attr) => {
        const key = attr.key;
        if (!this.timewindowsPerSensor[key]) {
          map[key] = this.cloneDefaultTimewindow();
        } else {
          map[key] = this.timewindowsPerSensor[key];
        }
      });
      this.timewindowsPerSensor = map;
      this.cdr.detectChanges();
    }
  }

  private initializeUnreadLogsState(): void {
    if (this.trueId) {
      const hasUnread = this.logsNotifier.hasUnreadLogs(this.trueId);
      this.unreadLogs = hasUnread;
    }
  }

  private convertPredictionToAnomaly(
    prediction: any,
    predictionValue: any
  ): AnomalyReport {
    const confidence = predictionValue.general_failure_probability
      ? Math.round(predictionValue.general_failure_probability * 100)
      : predictionValue.confidence || 0;
    const severity =
      confidence >= 90 ? "Critical" : confidence >= 70 ? "Major" : "Minor";
    let startTime: string | number | undefined;
    let endTime: string | number | undefined;

    if (predictionValue.datetime) {
      const parts = predictionValue.datetime.split("/");
      if (parts.length === 2) {
        startTime = parts[0];
        endTime = parts[1];
      } else {
        const startDate = new Date(predictionValue.datetime);
        const endDate = new Date(startDate.getTime() + 60 * 60 * 1000);
        startTime = startDate.toISOString();
        endTime = endDate.toISOString();
      }
    } else if (prediction.predictionTime) {
      const startDate = new Date(prediction.predictionTime);
      const endDate = new Date(startDate.getTime() + 60 * 60 * 1000);
      startTime = startDate.toISOString();
      endTime = endDate.toISOString();
    }

    const componentType =
      predictionValue.predicted_failing_component ||
      predictionValue.component_type ||
      "";

    return {
      id: prediction.id,
      reportEntity: this.deviceId,
      errorName:
        predictionValue.predicted_failing_component ||
        predictionValue.error_name ||
        "",
      severity,
      creationDate:
        prediction.predictionTime ||
        prediction.createdAt ||
        new Date().toISOString(),
      componentType,
      deviceType: "",
      location: "",
      description:
        predictionValue.description ||
        `Predicted failure for component ${
          predictionValue.predicted_failing_component || ""
        }`,
      status: "Active",
      timeRange: predictionValue.datetime || prediction.predictionTime || "",
      startTime,
      endTime,
      confidence,
      affectedMetrics: predictionValue.predicted_failing_component
        ? [predictionValue.predicted_failing_component]
        : predictionValue.affected_metrics || [],
    };
  }

  private init() {
    this.routeParamsSubscription = this.route.params
      .pipe(distinctUntilChanged((prev, curr) => prev.id === curr.id))
      .subscribe((params) => {
        if (params.id) {
          this.trueId = params.id;
          this.id = params.id;
          this.fetchPredictiveModelConfig(params.id);
          this.models = this.modelsData;
          if (!this.models || this.models.length === 0) {
            this.models = [
              {
                id: params.id,
                trueId: params.id,
                device: "",
                date: new Date().toISOString(),
              },
            ];
          }

          this.loadCollapsedStates();
          this.updateFilteredModels();
          this.fetchModelNames();
          if (this.trueId !== params.id) {
            this.trueId = params.id;
            this.loadViewPreferences();
          }

          const forecast = this.models.find(
            (element) => element.trueId === this.id
          );
          if (!forecast) {
            return this.router.navigateByUrl("");
          }
          this.device = forecast.device;
          this.forecastName = forecast.id;
          this.date = forecast.date;

          this.modelWebSocketService.cleanUp();
          this.loadLastReadLogTimestamp();
          this.initializeUnreadLogsState();
          this.subscriptions.forEach((sub) => sub.unsubscribe());
          this.subscriptions = [];
          this.logsObservable = this.modelWebSocketService
            .requestJobLogs(this.trueId)
            .pipe(
              filter((msg) => {
                return (
                  //@ts-ignore
                  msg.forecastId == params.id || msg.forecast_id == params.id
                );
              }),
              mergeMap((msg) => flatMap(msg.data.logs)),
              share()
            );

          const modelStatusSubscription = this.modelWebSocketService
            .requestModelStatus(this.trueId)
            .subscribe((msg: any) => {
              if (msg.forecastId != params.id) return;
              const statusPayload = msg?.data?.data || msg?.data;
              if (statusPayload?.status) {
                const modelStatus = statusPayload.status.toLowerCase();
                if (
                  modelStatus === "inactive" ||
                  modelStatus === "pending" ||
                  modelStatus === "active" ||
                  modelStatus === "error"
                ) {
                  this.status =
                    modelStatus === "error" ? "failed" : modelStatus;
                }
                if (
                  modelStatus === "pending" &&
                  typeof statusPayload.trainingProgress === "number"
                ) {
                  this.progressMessage = {
                    step: statusPayload.trainingStep || "Training",
                    progress: statusPayload.trainingProgress || 0,
                  };
                } else if (modelStatus !== "pending") {
                  this.progressMessage = null;
                  if (modelStatus === "active") {
                    this.activationComplete = true;
                    this.isActivating = false;
                  }
                }
              }
            });
          this.subscriptions.push(modelStatusSubscription);
          this.fetchAnomalyHistoryPredictions();
          this.subscribeToAnomalyPredictions();
          this.subscribeToForecastPredictions(params.id);
        }

        if (this.notifierSubscription) {
          this.notifierSubscription.unsubscribe();
          this.notifierSubscription = null;
        }

        this.notifierSubscription = this.logsNotifier
          .changes()
          .subscribe((change) => {
            if (change.modelId === this.trueId) {
              this.ngZone.run(() => {
                this.unreadLogs = change.unread;
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
            const name = data.name || data.id.id.split("-")[0];
            this.modelNames.set(model.trueId, name);
            // Update filtered models after names are fetched
            this.filterModels();
          },
          (error) => {
            console.error(
              "Error fetching forecast name for",
              model.trueId,
              error
            );
            this.modelNames.set(model.trueId, model.id);
            this.filterModels();
          }
        );
      });
    }
  }

  private updateFilteredModels(): void {
    this.filteredModels = [...this.models];
    this.modelSearchTerm = "";
  }

  private handleWebSocketMessage(msg: any): void {
    if (!msg) {
      return;
    }

    const payload = msg?.data?.data || msg?.data || msg;
    switch (msg.type) {
      case "progress":
        if (
          typeof payload.trainingProgress === "number" ||
          typeof payload.progress === "number"
        ) {
          this.progressMessage = {
            step: payload.trainingStep || payload.step || "Processing",
            progress: payload.trainingProgress ?? payload.progress,
          };
        }
        this.status = "pending";
        break;
      case "complete":
        this.progressMessage = null;
        this.activationComplete = true;
        this.status = "active";
        this.anomaliesComponent?.setStreamStatus(true, null);
        break;
      case "error":
        this.progressMessage = null;
        this.status = "failed";
        break;
      case "model_status":
      case "response":
        if (payload.status === "active") {
          this.progressMessage = null;
          this.activationComplete = true;
          this.isActivating = false;
          this.status = "active";
        }
        break;
    }
  }

  private loadCollapsedStates(): void {
    try {
      const savedStates = localStorage.getItem(
        "forecast-dashboard-collapsed-states-" + (this.trueId || "default")
      );
      if (savedStates) {
        const states = JSON.parse(savedStates);
        this.timeSeriesChartCollapsed =
          states.timeSeriesChartCollapsed || false;
        this.forecastChartCollapsed = states.forecastChartCollapsed || false;
        this.anomaliesCollapsed = states.anomaliesCollapsed || false;
      }
    } catch (error) {
      console.warn("Error loading collapsed states:", error);
    }

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
        "forecast-dashboard-collapsed-states-" + (this.trueId || "default"),
        JSON.stringify(states)
      );
    } catch (error) {
      console.warn("Error saving collapsed states:", error);
    }
  }

  private loadViewPreferences(): void {
    if (!this.trueId) {
      return;
    }
    this.predictiveModelsService.getPredictiveModel(this.trueId).subscribe(
      (forecast) => {
        const preferences = parseForecastViewPreferences(
          forecast.viewPreferences || ""
        );
        this.selectedViews = preferences.selectedViews;
        this.selectedSensor = preferences.selectedSensor || "rotate";
        this.hideSensorTelemetry = preferences.hideSensorTelemetry || false;
        this.timewindow = preferences.timewindow || this.timewindow;
        this.hiddenWidgets = new Set(preferences.hiddenWidgets || []);
        this.currentViewPreferences = preferences;
      },
      (error) => {
        console.warn(
          "Error loading forecast data for view preferences:",
          error
        );
        this.selectedViews = [
          ForecastViewType.FORECAST,
          ForecastViewType.ANOMALIES,
        ]; // Default fallback
        this.selectedSensor = "rotate";
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
        const updatedForecast = {
          ...forecast,
          viewPreferences: stringifyForecastViewPreferences(preferences),
        };

        // Save the updated forecast
        this.predictiveModelsService
          .updatePredictiveModel(updatedForecast)
          .subscribe(
            (response) => {},
            (error) => {
              console.error(
                "Error saving view preferences to database:",
                error
              );
              // Fallback to localStorage if database save fails
              this.fallbackToLocalStorage();
            }
          );
      },
      (error) => {
        console.error(
          "Error loading forecast for view preferences save:",
          error
        );
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
    } catch (error) {
      console.error(
        "Error saving view preferences to localStorage fallback:",
        error
      );
    }
  }

  private addDocumentClickListener(): void {
    document.addEventListener("click", (event: Event) => {
      const target = event.target as HTMLElement;
      const viewSelectorButton = target.closest(".view-selector-button");
      const viewSelectorDropdown = target.closest(".view-selector-dropdown");

      if (
        !viewSelectorButton &&
        !viewSelectorDropdown &&
        this.showViewSelector
      ) {
        this.showViewSelector = false;
      }
    });
  }

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

  private saveLastReadLogTimestamp(): void {
    if (!this.trueId) {
      return;
    }
    const key = this.LAST_READ_LOG_KEY_PREFIX + this.trueId;
    localStorage.setItem(key, Date.now().toString());
    this.lastReadLogTimestamp = Date.now();
  }

  private processAnomalyPrediction(predictionResult: any): AnomalyReport {
    const confidence = predictionResult.general_failure_probability
      ? Math.round(predictionResult.general_failure_probability * 100)
      : 0;
    const severity =
      confidence >= 90 ? "Critical" : confidence >= 70 ? "Major" : "Minor";

    let startTime: string | number | undefined;
    let endTime: string | number | undefined;
    if (predictionResult.datetime) {
      const parts = (predictionResult.datetime || "").toString().split("/");
      if (parts.length === 2) {
        startTime = parts[0];
        endTime = parts[1];
      } else {
        const startDate = new Date(predictionResult.datetime);
        const endDate = new Date(startDate.getTime() + 60 * 60 * 1000); // Add 1 hour
        startTime = startDate.toISOString();
        endTime = endDate.toISOString();
      }
    }

    const componentType = predictionResult.predicted_failing_component || "";

    return {
      timeRange: predictionResult.datetime || "",
      startTime,
      endTime,
      confidence,
      affectedMetrics: predictionResult.predicted_failing_component
        ? [predictionResult.predicted_failing_component]
        : [],
      id:
        predictionResult.id ||
        `${this.trueId || "forecast"}-${Date.now()}-${Math.random()
          .toString(36)
          .slice(2, 8)}`,
      reportEntity: this.deviceId,
      errorName: predictionResult.predicted_failing_component || "",
      severity,
      creationDate: predictionResult.datetime || new Date().toISOString(),
      componentType,
      deviceType: "",
      location: "",
      description:
        "Predicted failure for component " +
        (predictionResult.predicted_failing_component || ""),
      status: "Active",
    };
  }
}
