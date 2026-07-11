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
  ViewChild,
  ViewContainerRef,
  Injector,
  Output,
  EventEmitter,
} from "@angular/core";
import { CommonModule } from "@angular/common";
import { MatTableDataSource, MatTableModule } from "@angular/material/table";
import { MatPaginatorModule, MatPaginator } from "@angular/material/paginator";
import { MatSortModule, MatSort } from "@angular/material/sort";
import { MatIconModule } from "@angular/material/icon";
import { MatButtonModule } from "@angular/material/button";
import { MatTooltipModule } from "@angular/material/tooltip";
import { MatCardModule } from "@angular/material/card";
import { MatToolbarModule } from "@angular/material/toolbar";
import { MatDividerModule } from "@angular/material/divider";
import { FormsModule } from "@angular/forms";
import { MatDatepickerModule } from "@angular/material/datepicker";
import { MatNativeDateModule } from "@angular/material/core";
import { MatInputModule } from "@angular/material/input";
import { MatFormFieldModule } from "@angular/material/form-field";
import { MatMenuModule } from "@angular/material/menu";
import { Overlay, OverlayConfig, OverlayRef } from "@angular/cdk/overlay";
import { ComponentPortal } from "@angular/cdk/portal";
import { StaticProvider } from "@angular/core";
import { fromEvent, Observable, Subject, Subscription } from "rxjs";
import {
  DISPLAY_COLUMNS_PANEL_DATA,
  DisplayColumnsPanelComponent,
  DisplayColumnsPanelData,
} from "@home/components/widget/lib/display-columns-panel.component";
import { DisplayColumn } from "@home/components/widget/lib/table-widget.models";
import { DEFAULT_OVERLAY_POSITIONS } from "@shared/models/overlay.models";
import { WidgetComponentsModule } from "@home/components/widget/widget-components.module";
import { TranslateModule } from "@ngx-translate/core";
import { StreamMessage } from "@app/core/http/model-websocket.service";
import { PredictiveModelsService } from "@app/core/http/forecast.service";
import { AnomalyReport } from "@core/event-models/AnomalyReport";
import { AnomalyPrediction } from "@core/event-models/AnomalyPrediction";
import { ForecastSensorPrediction } from "@core/event-models/ForecastSensorPrediction";

export { AnomalyReport, ForecastSensorPrediction, AnomalyPrediction };

export interface AnomalyStreamSubscription {
  cmdId: number;
  forecastId: string;
  observable: Observable<StreamMessage>;
  subject: Subject<StreamMessage>;
}

@Component({
  selector: "tb-anomalies",
  standalone: true,
  imports: [
    CommonModule,
    MatTableModule,
    MatPaginatorModule,
    MatSortModule,
    MatIconModule,
    MatButtonModule,
    MatTooltipModule,
    MatCardModule,
    MatToolbarModule,
    MatDividerModule,
    WidgetComponentsModule,
    TranslateModule,
    FormsModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatInputModule,
    MatFormFieldModule,
    MatMenuModule,
  ],
  templateUrl: "./anomalies.component.html",
  styleUrls: ["./anomalies.component.scss"],
})
export class AnomaliesComponent implements OnInit {
  @Input() deviceId?: string;

  @Input() forecastId?: string;

  @Input() isExpanded?: boolean;

  @Input() modelId?: string;

  @Input() predictionType?: string;

  @Input() predictiveModelsService?: PredictiveModelsService;

  @ViewChild(MatPaginator) paginator!: MatPaginator;

  @ViewChild(MatSort) sort!: MatSort;

  @Output() refreshFilter = new EventEmitter<{
    startTs: number;
    endTs: number;
  }>();

  isStreamConnected = false;

  streamError: string | null = null;

  displayedColumns: string[] = [
    "timeRange",
    "componentType",
    "confidence",
    "creationDate",
    // 'severity',
    // 'deviceType',
    // 'location',
    // 'status',
    // 'actions',
  ];

  stickyColumns = new Set<string>();

  allColumns: DisplayColumn[] = [
    {
      title: "Failure Time Range",
      def: "timeRange",
      display: true,
      selectable: true,
    },
    {
      title: "Component Type",
      def: "componentType",
      display: true,
      selectable: true,
    },
    { title: "Confidence", def: "confidence", display: true, selectable: true },
    {
      title: "Prediction Time",
      def: "creationDate",
      display: true,
      selectable: true,
    },
    { title: "Severity", def: "severity", display: true, selectable: true },
    {
      title: "Device Type",
      def: "deviceType",
      display: true,
      selectable: true,
    },
    { title: "Location", def: "location", display: true, selectable: true },
    { title: "Status", def: "status", display: true, selectable: true },
    { title: "Actions", def: "actions", display: true, selectable: false },
  ];

  dataSource = new MatTableDataSource<AnomalyReport>();

  isRefreshing = false;

  filterStartDate: Date | null = null;

  filterHour = 0;

  filterMinute = 0;

  filterSecond = 0;

  private streamSubscription?: AnomalyStreamSubscription;

  private anomalyStreamSubscription?: Subscription;

  private anomalies: Map<string, AnomalyReport> = new Map<
    string,
    AnomalyReport
  >();

  constructor(
    private overlay: Overlay,
    private viewContainerRef: ViewContainerRef,
    private predictiveMaintenanceService: PredictiveModelsService
  ) {}

  ngOnInit(): void {
    this.dataSource.data = Array.from(this.anomalies.values());
    this.stickyColumns.add("actions");

    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    this.filterStartDate = yesterday;
    this.filterHour = yesterday.getHours();
    this.filterMinute = yesterday.getMinutes();
    this.filterSecond = yesterday.getSeconds();

    if (this.forecastId) {
      this.connectToAnomalyStream();
    }

    this.predictiveMaintenanceService.anomalies.forEach((anomaly) => {
      this.handleNewAnomaly(anomaly);
    });

    this.predictiveMaintenanceService.anomaliesData$.subscribe((anomaly) => {
      this.handleNewAnomaly(anomaly);
    });
  }

  // eslint-disable-next-line @angular-eslint/use-lifecycle-interface
  ngAfterViewInit(): void {
    this.dataSource.paginator = this.paginator;
    this.dataSource.sort = this.sort;

    this.dataSource.sortingDataAccessor = (
      item: AnomalyReport,
      property: string
    ) => {
      if (property === "timeRange") {
        const start =
          item.startTime ||
          (item.timeRange ? item.timeRange.split("/")[0] : undefined);
        const ts = start ? new Date(start).getTime() : 0;
        return isNaN(ts) ? 0 : ts;
      }
      if (property === "creationDate") {
        const ts = item.creationDate
          ? new Date(item.creationDate).getTime()
          : 0;
        return isNaN(ts) ? 0 : ts;
      }
      if (property === "confidence") {
        return item.confidence || 0;
      }
      const value: any = (item as any)[property];
      if (value === null || value === undefined) {
        return "";
      }
      return typeof value === "string" ? value.toLowerCase() : value;
    };

    this.sort.active = "timeRange";
    this.sort.direction = "asc";
    this.dataSource.sort = this.sort;
  }

  viewDetails(anomaly: AnomalyReport): void {
    // Implementation for viewing anomaly details
    // console.log("View details for anomaly:", anomaly);
  }

  getSeverityIcon(severity: string): string {
    switch (severity) {
      case "Critical":
        return "error";
      case "Major":
        return "warning";
      case "Minor":
        return "info";
      default:
        return "help";
    }
  }

  getSeverityColor(severity: string): string {
    switch (severity) {
      case "Critical":
        return "warn";
      case "Major":
        return "accent";
      case "Minor":
        return "primary";
      default:
        return "";
    }
  }

  getStatusIcon(status: string): string {
    switch (status) {
      case "Active":
        return "play_circle_filled";
      case "Resolved":
        return "check_circle";
      case "Investigating":
        return "search";
      default:
        return "help";
    }
  }

  getStatusColor(status: string): string {
    switch (status) {
      case "Active":
        return "warn";
      case "Resolved":
        return "primary";
      case "Investigating":
        return "accent";
      default:
        return "";
    }
  }

  formatDate(dateString: string | Date | number): string {
    let date: Date;
    if (typeof dateString === "string") {
      date = new Date(dateString);
    } else if (typeof dateString === "number") {
      date = new Date(dateString);
    } else {
      date = dateString;
    }

    if (!date || isNaN(date.getTime())) {
      return "Invalid Date";
    }

    const hours = date.getHours();
    const minutes = date.getMinutes();
    const seconds = date.getSeconds();
    const hour12 = hours % 12 || 12;
    const ampm = hours >= 12 ? "PM" : "AM";

    const minutesStr = minutes.toString().padStart(2, "0");
    const secondsStr = seconds.toString().padStart(2, "0");

    const day = date.getDate().toString().padStart(2, "0");
    const month = (date.getMonth() + 1).toString().padStart(2, "0");
    const year = date.getFullYear();

    return `${hour12}:${minutesStr}:${secondsStr} ${ampm}\n${day}/${month}/${year}`;
  }

  formatTimeRange(
    startTime: string | Date | number,
    endTime: string | Date | number
  ): string {
    let startDate: Date;
    if (typeof startTime === "string") {
      startDate = new Date(startTime);
    } else if (typeof startTime === "number") {
      startDate = new Date(startTime);
    } else {
      startDate = startTime;
    }

    let endDate: Date;
    if (typeof endTime === "string") {
      endDate = new Date(endTime);
    } else if (typeof endTime === "number") {
      endDate = new Date(endTime);
    } else {
      endDate = endTime;
    }

    if (
      !startDate ||
      isNaN(startDate.getTime()) ||
      !endDate ||
      isNaN(endDate.getTime())
    ) {
      return "Invalid Date Range";
    }

    const startHour = startDate.getHours();
    const startHour12 = startHour % 12 || 12;
    const startAmpm = startHour >= 12 ? "PM" : "AM";

    const endHour = endDate.getHours();
    const endHour12 = endHour % 12 || 12;
    const endAmpm = endHour >= 12 ? "PM" : "AM";

    return `${startHour12}${startAmpm} - ${endHour12}${endAmpm}`;
  }

  formatTimeRangeDate(startTime: string | Date | number): string {
    let startDate: Date;
    if (typeof startTime === "string") {
      startDate = new Date(startTime);
    } else if (typeof startTime === "number") {
      startDate = new Date(startTime);
    } else {
      startDate = startTime;
    }

    if (!startDate || isNaN(startDate.getTime())) {
      return "Invalid Date";
    }

    const month = startDate.getMonth() + 1;
    const day = startDate.getDate();
    const year = startDate.getFullYear();

    return `${month}-${day}-${year}`;
  }

  formatEndTime(endTime: string | Date | number): string {
    let endDate: Date;
    if (typeof endTime === "string") {
      endDate = new Date(endTime);
    } else if (typeof endTime === "number") {
      endDate = new Date(endTime);
    } else {
      endDate = endTime;
    }

    if (!endDate || isNaN(endDate.getTime())) {
      return "Invalid Time";
    }

    const endHour = endDate.getHours();
    const endHour12 = endHour % 12 || 12;
    const endAmpm = endHour >= 12 ? "PM" : "AM";

    return `${endHour12}${endAmpm}`;
  }

  formatPredictionTime(dateString: string | Date | number): string {
    let date: Date;
    if (typeof dateString === "string") {
      date = new Date(dateString);
    } else if (typeof dateString === "number") {
      date = new Date(dateString);
    } else {
      date = dateString;
    }

    if (!date || isNaN(date.getTime())) {
      return "Invalid Date";
    }

    const hours = date.getHours();
    const minutes = date.getMinutes();
    const seconds = date.getSeconds();
    const hour12 = hours % 12 || 12;
    const ampm = hours >= 12 ? "PM" : "AM";

    const minutesStr = minutes.toString().padStart(2, "0");
    const secondsStr = seconds.toString().padStart(2, "0");

    return `${hour12}:${minutesStr}:${secondsStr} ${ampm}`;
  }

  formatPredictionDate(dateString: string | Date | number): string {
    let date: Date;
    if (typeof dateString === "string") {
      date = new Date(dateString);
    } else if (typeof dateString === "number") {
      date = new Date(dateString);
    } else {
      date = dateString;
    }

    if (!date || isNaN(date.getTime())) {
      return "Invalid Date";
    }

    const day = date.getDate().toString().padStart(2, "0");
    const month = (date.getMonth() + 1).toString().padStart(2, "0");
    const year = date.getFullYear();

    return `${day}/${month}/${year}`;
  }

  resolveAnomaly(anomaly: AnomalyReport): void {
    const existingAnomaly = this.anomalies.get(anomaly.id);
    if (existingAnomaly) {
      existingAnomaly.status = "Resolved";
      this.dataSource.data = Array.from(this.anomalies.values());
    }
  }

  clearPredictions(): void {
    if (!this.predictiveModelsService || !this.modelId) {
      this.anomalies.clear();
      this.dataSource.data = [];
      return;
    }

    this.predictiveModelsService
      .deleteAnomalyHistoryPredictions(this.modelId, this.predictionType)
      .subscribe({
        next: (response: { deletedCount: number; message: string }) => {
          this.anomalies.clear();
          this.dataSource.data = [];
        },
        error: (error: any) => {
          console.error("Failed to delete predictions:", error);
          this.anomalies.clear();
          this.dataSource.data = [];
        },
      });
  }

  getSeverityClass(severity: string): string {
    return `severity-${severity.toLowerCase()}`;
  }

  getStatusClass(status: string): string {
    return `status-${status.toLowerCase()}`;
  }

  getConfidenceClass(confidence: number): string {
    if (confidence >= 90) {
      return "high-confidence";
    }
    if (confidence >= 75) {
      return "medium-confidence";
    }
    return "low-confidence";
  }

  getConfidenceIcon(confidence: number): string {
    if (confidence >= 90) {
      return "trending_up";
    }
    if (confidence >= 75) {
      return "trending_flat";
    }
    return "trending_down";
  }

  isResolved(status: string): boolean {
    return status === "Resolved";
  }

  editColumnsToDisplay($event: Event): void {
    if ($event) {
      $event.stopPropagation();
    }

    const target = $event.target || $event.srcElement || $event.currentTarget;
    const config = new OverlayConfig({
      panelClass: "tb-panel-container",
      backdropClass: "cdk-overlay-transparent-backdrop",
      hasBackdrop: true,
      height: "fit-content",
      maxHeight: "75vh",
    });

    config.positionStrategy = this.overlay
      .position()
      .flexibleConnectedTo(target as HTMLElement)
      .withPositions(DEFAULT_OVERLAY_POSITIONS);

    const overlayRef = this.overlay.create(config);
    overlayRef.backdropClick().subscribe(() => {
      overlayRef.dispose();
    });

    const columns: DisplayColumn[] = this.allColumns.map((column) => ({
      title: column.title,
      def: column.def,
      display: this.displayedColumns.indexOf(column.def) > -1,
      selectable: column.selectable,
    }));

    const providers: StaticProvider[] = [
      {
        provide: DISPLAY_COLUMNS_PANEL_DATA,
        useValue: {
          columns,
          columnsUpdated: (newColumns: DisplayColumn[]) => {
            this.displayedColumns = newColumns
              .filter((column) => column.display)
              .map((column) => column.def);
            this.allColumns.forEach((col) => {
              const newCol = newColumns.find((nc) => nc.def === col.def);
              if (newCol) {
                col.display = newCol.display;
              }
            });
          },
        } as DisplayColumnsPanelData,
      },
      {
        provide: OverlayRef,
        useValue: overlayRef,
      },
    ];

    const injector = Injector.create({
      parent: this.viewContainerRef.injector,
      providers,
    });
    const componentRef = overlayRef.attach(
      new ComponentPortal(
        DisplayColumnsPanelComponent,
        this.viewContainerRef,
        injector
      )
    );

    const resizeWindows$ = fromEvent(window, "resize").subscribe(() => {
      overlayRef.updatePosition();
    });
    componentRef.onDestroy(() => {
      resizeWindows$.unsubscribe();
    });
  }

  toggleExpanded(): void {
    this.isExpanded = !this.isExpanded;
  }

  toggleColumnSticky(columnDef: string): void {
    if (this.stickyColumns.has(columnDef)) {
      this.stickyColumns.delete(columnDef);
    } else {
      this.stickyColumns.add(columnDef);
    }
  }

  isColumnSticky(columnDef: string): boolean {
    return this.stickyColumns.has(columnDef);
  }

  getPinIcon(columnDef: string): string {
    return this.isColumnSticky(columnDef) ? "push_pin" : "push_pin";
  }

  getPinTooltip(columnDef: string): string {
    return this.isColumnSticky(columnDef)
      ? "Unpin column"
      : "Pin column when scrolling vertically";
  }

  refreshTable(): void {
    this.isRefreshing = true;

    this.anomalies.clear();
    this.dataSource.data = [];

    const filterDateTime = this.getFilterDateTime();
    const startTs = filterDateTime
      ? filterDateTime.getTime()
      : Date.now() - 24 * 60 * 60 * 1000;
    this.refreshFilter.emit({ startTs, endTs: Date.now() });

    setTimeout(() => {
      this.isRefreshing = false;
    }, 1000);
  }

  getFilterDateTime(): Date | null {
    if (!this.filterStartDate) {
      return null;
    }

    const dateTime = new Date(this.filterStartDate);
    dateTime.setHours(this.filterHour || 0);
    dateTime.setMinutes(this.filterMinute || 0);
    dateTime.setSeconds(this.filterSecond || 0);
    dateTime.setMilliseconds(0);

    return dateTime;
  }

  applyDateFilter(): void {
    const filterDateTime = this.getFilterDateTime();
    if (!filterDateTime) {
      return;
    }

    this.refreshTable();
  }

  clearDateFilter(): void {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    this.filterStartDate = yesterday;
    this.filterHour = yesterday.getHours();
    this.filterMinute = yesterday.getMinutes();
    this.filterSecond = yesterday.getSeconds();
    this.applyDateFilter();
  }

  public setStreamStatus(
    connected: boolean,
    error: string | null = null
  ): void {
    this.isStreamConnected = connected;
    this.streamError = error;
  }

  public addAnomaly(anomaly: AnomalyReport): void {
    this.handleNewAnomaly(anomaly);
  }

  public updateAnomalies(anomalies: AnomalyReport[]): void {
    this.anomalies.clear();
    anomalies.forEach((anomaly) => {
      if ((!anomaly.startTime || !anomaly.endTime) && anomaly.timeRange) {
        const parts = anomaly.timeRange.split("/");
        if (parts.length === 2) {
          anomaly.startTime = anomaly.startTime || parts[0];
          anomaly.endTime = anomaly.endTime || parts[1];
        } else {
          anomaly.startTime = anomaly.startTime || anomaly.timeRange;
          anomaly.endTime = anomaly.endTime || anomaly.timeRange;
        }
      }
      this.anomalies.set(anomaly.id, anomaly);
    });
    this.dataSource.data = Array.from(this.anomalies.values());
  }

  private connectToAnomalyStream(): void {
    if (!this.forecastId) {
      return;
    }
    if (!this.streamSubscription) {
      console.warn(
        "[Anomalies] Stream subscription not configured - live streaming disabled"
      );
      this.isStreamConnected = false;
      return;
    }

    const filterDateTime = this.getFilterDateTime();
    const startTime = filterDateTime ? filterDateTime.getTime() : undefined;

    this.streamError = null;

    try {
      this.anomalyStreamSubscription =
        this.streamSubscription.observable.subscribe({
          next: (message: StreamMessage) => {
            this.handleStreamMessage(message);
          },
          error: (error) => {
            console.error("[Anomalies] WebSocket error:", error);
            this.streamError = `Connection error: ${error}`;
            this.isStreamConnected = false;
            console.error(error.reason);
          },
          complete: () => {
            this.isStreamConnected = false;
          },
        });

      this.isStreamConnected = true;
    } catch (error) {
      console.error("[Anomalies] Failed to connect to stream:", error);
      this.streamError = `Failed to connect: ${error}`;
      this.isStreamConnected = false;
    }
  }

  private handleStreamMessage(message: StreamMessage): void {
    if (message.errorCode || message.errorMsg) {
      console.error("[Anomalies] Stream error:", message.errorMsg);
      this.streamError = message.errorMsg || "Unknown error";
      return;
    }

    const data = message.data;
    if (!data) {
      return;
    }

    switch (data.type) {
      case "connection":
        this.isStreamConnected = true;
        this.streamError = null;
        break;

      case "historical":
        if (Array.isArray(data.data)) {
          this.filterAnomalies();
        }
        break;

      case "error":
        console.error("[Anomalies] Stream error:", data.message);
        this.streamError = data.message || "Stream error";
        break;
    }
  }

  private handleNewAnomaly(anomaly: AnomalyReport): void {
    anomaly.creationDate = new Date().toISOString();

    if ((!anomaly.startTime || !anomaly.endTime) && anomaly.timeRange) {
      const parts = anomaly.timeRange.split("/");
      if (parts.length === 2) {
        anomaly.startTime = anomaly.startTime || parts[0];
        anomaly.endTime = anomaly.endTime || parts[1];
      } else {
        anomaly.startTime = anomaly.startTime || anomaly.timeRange;
        anomaly.endTime = anomaly.endTime || anomaly.timeRange;
      }
    }
    this.anomalies.set(anomaly.id, anomaly);
    this.dataSource.data = Array.from(this.anomalies.values());
    const maxAnomalies = 500;
    if (this.anomalies.size > maxAnomalies) {
      const excess = this.anomalies.size - maxAnomalies;
      const keysToRemove = Array.from(this.anomalies.keys()).slice(0, excess);
      keysToRemove.forEach((key) => this.anomalies.delete(key));
    }
  }

  private filterAnomalies(): void {
    const filterDateTime = this.getFilterDateTime();
    if (!filterDateTime) {
      return;
    }
  }
}
