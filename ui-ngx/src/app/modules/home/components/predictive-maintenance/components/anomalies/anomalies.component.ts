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
  ViewChild,
  ViewContainerRef,
  Injector,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatTableDataSource, MatTableModule } from '@angular/material/table';
import { MatPaginatorModule, MatPaginator } from '@angular/material/paginator';
import { MatSortModule, MatSort } from '@angular/material/sort';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatCardModule } from '@angular/material/card';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatDividerModule } from '@angular/material/divider';
import { FormsModule } from '@angular/forms';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatMenuModule } from '@angular/material/menu';
import {
  ConnectedPosition,
  Overlay,
  OverlayConfig,
  OverlayRef,
} from '@angular/cdk/overlay';
import { ComponentPortal } from '@angular/cdk/portal';
import { StaticProvider } from '@angular/core';
import { fromEvent, Subscription } from 'rxjs';
import {
  DISPLAY_COLUMNS_PANEL_DATA,
  DisplayColumnsPanelComponent,
  DisplayColumnsPanelData,
} from '@home/components/widget/lib/display-columns-panel.component';
import { DisplayColumn } from '@home/components/widget/lib/table-widget.models';
import { DEFAULT_OVERLAY_POSITIONS } from '@shared/models/overlay.models';
import { WidgetComponentsModule } from '@home/components/widget/widget-components.module';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import {
  ModelWebSocketService,
  AnomalyStreamMessage,
  AnomalyStreamSubscription,
} from '@app/core/http/model-websocket.service';
import { PredictiveModelsService } from '@app/core/http/forecast.service';

export interface AnomalyReport {
  id: string;
  reportEntity: string;
  errorName: string;
  severity: 'Critical' | 'Major' | 'Minor';
  creationDate: string;
  componentType: string;
  deviceType: string;
  location: string;
  description: string;
  status: 'Active' | 'Resolved' | 'Investigating';
  affectedMetrics: string[];
  confidence: number;
  // timeRange may be a human-friendly string or an ISO range; startTime/endTime are used in template
  timeRange?: string;
  startTime?: string | number; // ISO string or epoch millis
  endTime?: string | number;
}

export interface AnomalyPrediction {
  datetime: string; // ISO date string
  predicted_failing_component: string;
  general_failure_probability: number; // 0 to 1
  component_failure_probabilities: { [component: string]: number }; // e.g., {comp1: 0.9, comp2: 0.1}
  component_probabilities: { [component: string]: number }; // e.g., {comp1: 0.8, comp2: 0.2, none: 0.0}
  failure_predicted: boolean;
}

export interface LogEntry {
  timestamp: string;
  type: 'forecast' | 'anomaly' | 'system' | 'other';
  level: string; // 'info', 'warn', 'error', etc.
  message: {
    result?: AnomalyPrediction | ForecastSensorPrediction;
    sensor?: string;
    prediction_type?: any;
  };
  source?: 'ForecastModel' | 'AnomalyModel';
}

export type AnomalyPredictionLogEntry = LogEntry & {
  type: 'anomaly';
  level: 'PREDICTION';
  message: {
    result?: AnomalyPrediction[];
    sensor?: string;
    type?: any;
  };
};

export interface ForecastSensorPrediction {
  forecast: number[];
  timestamp: number[];
};

export interface ForecastPrediction {
  [key: string]: ForecastSensorPrediction | number;
  forecast_max_steps: number;
}

export interface ForecastSensorPredictions {
  [sensor: string]: ForecastSensorPrediction;
}

export interface ForecastPredictionLogEntryMessage {
  result?: ForecastPrediction | ForecastSensorPredictions;
  sensor?: string;
  iteration?: number;
  prediction_type: 'forecast' | 'history';
  device_id?: string;
  recent_point_ts?: number; // Timestamp of the last real data point (in milliseconds)
}

export type ForecastPredictionLogEntry = LogEntry & {
  type: 'forecast';
  level: 'PREDICTION' | 'FORECAST_HISTORY';
  message: string | ForecastPredictionLogEntryMessage;
};


export interface AnomalyLogs {
  logs: Array<LogEntry>;
  count: number;
}

@Component({
  selector: 'tb-anomalies',
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
  templateUrl: './anomalies.component.html',
  styleUrls: ['./anomalies.component.scss'],
})
export class AnomaliesComponent implements OnInit, OnDestroy {
  @Input() deviceId?: string;

  @Input() forecastId?: string;

  @Input() isExpanded?: boolean;

  @Input() modelId?: string;

  @Input() predictionType?: string;

  @Input() predictiveModelsService?: PredictiveModelsService;

  @ViewChild(MatPaginator) paginator!: MatPaginator;

  @ViewChild(MatSort) sort!: MatSort;

  // WebSocket streaming
  private anomalyStreamSubscription?: Subscription;

  private streamSubscription?: AnomalyStreamSubscription;

  isStreamConnected = false;

  streamError: string | null = null;

  /**
   * External setter for stream connection status so parent components can update the UI
   */
  public setStreamStatus(connected: boolean, error: string | null = null): void {
    this.isStreamConnected = connected;
    this.streamError = error;
  }

  displayedColumns: string[] = [
    'timeRange',
    'componentType',
    'confidence',
    'creationDate',
    // 'severity',
    // 'deviceType',
    // 'location',
    // 'status',
    // 'actions',
  ];

  // Track which columns are pinned/sticky
  stickyColumns: Set<string> = new Set();

  allColumns: DisplayColumn[] = [
    { title: 'Failure Time Range', def: 'timeRange', display: true, selectable: true },
    {
      title: 'Component Type',
      def: 'componentType',
      display: true,
      selectable: true,
    },
    { title: 'Confidence', def: 'confidence', display: true, selectable: true },
    {
      title: 'Prediction Time',
      def: 'creationDate',
      display: true,
      selectable: true,
    },
    { title: 'Severity', def: 'severity', display: true, selectable: true },
    {
      title: 'Device Type',
      def: 'deviceType',
      display: true,
      selectable: true,
    },
    { title: 'Location', def: 'location', display: true, selectable: true },
    { title: 'Status', def: 'status', display: true, selectable: true },
    { title: 'Actions', def: 'actions', display: true, selectable: false },
  ];

  dataSource = new MatTableDataSource<AnomalyReport>();

  isRefreshing = false;

  // Start with empty array - will be populated only from stream - local
  private anomalies: Map<string, AnomalyReport> = new Map<string, AnomalyReport>();

  // Date filter
  filterStartDate: Date | null = null;

  filterHour = 0;

  filterMinute = 0;

  filterSecond = 0;

  constructor(
    private overlay: Overlay,
    private viewContainerRef: ViewContainerRef,
    private translate: TranslateService,
    private predictiveMaintenanceService: PredictiveModelsService,
  ) { }

  /**
   * Public method to add a new anomaly from outside (e.g., parent component)
   * Accepts an AnomalyReport and adds it to the table
   */
  public addAnomaly(anomaly: AnomalyReport): void {
    console.log(anomaly);
    this.handleNewAnomaly(anomaly);
  }

  public updateAnomalies(anomalies: AnomalyReport[]): void {
    this.anomalies.clear();
    anomalies.forEach((anomaly) => {
      // Ensure startTime/endTime exist - try to parse from timeRange (ISO range or single timestamp)
      if ((!anomaly.startTime || !anomaly.endTime) && anomaly.timeRange) {
        // Try formats like "2023-01-01T00:00:00Z/2023-01-01T01:00:00Z" or single ISO
        const parts = anomaly.timeRange.split('/');
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

  ngOnInit(): void {
    // Start with empty data
    this.dataSource.data = Array.from(this.anomalies.values());
    // Pin the actions column by default
    this.stickyColumns.add('actions');

    // Set default filter to last 24 hours with current time
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    this.filterStartDate = yesterday;
    this.filterHour = yesterday.getHours();
    this.filterMinute = yesterday.getMinutes();
    this.filterSecond = yesterday.getSeconds();
    // console.log(
    //   "[Anomalies] Default filter set to last 24 hours from:",
    //   this.getFilterDateTime()
    // );

    // Connect to real-time anomaly stream if forecastId is provided
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

  ngOnDestroy(): void {
    // this.disconnectFromAnomalyStream();
  }

  // eslint-disable-next-line @angular-eslint/use-lifecycle-interface
  ngAfterViewInit(): void {
    this.dataSource.paginator = this.paginator;
    this.dataSource.sort = this.sort;

    // Provide a sorting accessor that converts timeRange/startTime to numeric timestamp
    this.dataSource.sortingDataAccessor = (item: AnomalyReport, property: string) => {
      if (property === 'timeRange') {
        // Prefer explicit startTime if present, otherwise try to parse timeRange field
        const start = item.startTime || (item.timeRange ? item.timeRange.split('/')[0] : undefined);
        const ts = start ? new Date(start).getTime() : 0;
        return isNaN(ts) ? 0 : ts;
      }
      if (property === 'creationDate') {
        const ts = item.creationDate ? new Date(item.creationDate).getTime() : 0;
        return isNaN(ts) ? 0 : ts;
      }
      if (property === 'confidence') {
        return item.confidence || 0;
      }
      // Default string comparison
      const value: any = (item as any)[property];
      if (value === null || value === undefined) {
        return '';
      }
      return typeof value === 'string' ? value.toLowerCase() : value;
    };

    // Set default sort by failure time range (start time) in descending order
    this.sort.active = 'timeRange';
    this.sort.direction = 'asc';
    this.dataSource.sort = this.sort;
  }

  getSeverityIcon(severity: string): string {
    switch (severity) {
      case 'Critical':
        return 'error';
      case 'Major':
        return 'warning';
      case 'Minor':
        return 'info';
      default:
        return 'help';
    }
  }

  getSeverityColor(severity: string): string {
    switch (severity) {
      case 'Critical':
        return 'warn';
      case 'Major':
        return 'accent';
      case 'Minor':
        return 'primary';
      default:
        return '';
    }
  }

  getStatusIcon(status: string): string {
    switch (status) {
      case 'Active':
        return 'play_circle_filled';
      case 'Resolved':
        return 'check_circle';
      case 'Investigating':
        return 'search';
      default:
        return 'help';
    }
  }

  getStatusColor(status: string): string {
    switch (status) {
      case 'Active':
        return 'warn';
      case 'Resolved':
        return 'primary';
      case 'Investigating':
        return 'accent';
      default:
        return '';
    }
  }

  formatDate(dateString: string | Date | number): string {
    let date: Date;
    if (typeof dateString === 'string') {
      date = new Date(dateString);
    } else if (typeof dateString === 'number') {
      date = new Date(dateString);
    } else {
      date = dateString;
    }

    if (!date || isNaN(date.getTime())) {
      return 'Invalid Date';
    }

    // Format: Full time with DD/MM/YYYY (with line break)
    const hours = date.getHours();
    const minutes = date.getMinutes();
    const seconds = date.getSeconds();
    const hour12 = hours % 12 || 12;
    const ampm = hours >= 12 ? 'PM' : 'AM';

    // Pad with zeros
    const minutesStr = minutes.toString().padStart(2, '0');
    const secondsStr = seconds.toString().padStart(2, '0');

    // Format date as DD/MM/YYYY
    const day = date.getDate().toString().padStart(2, '0');
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const year = date.getFullYear();

    return `${hour12}:${minutesStr}:${secondsStr} ${ampm}\n${day}/${month}/${year}`;
  }

  formatTimeRange(startTime: string | Date | number, endTime: string | Date | number): string {
    // Parse start time
    let startDate: Date;
    if (typeof startTime === 'string') {
      startDate = new Date(startTime);
    } else if (typeof startTime === 'number') {
      startDate = new Date(startTime);
    } else {
      startDate = startTime;
    }

    // Parse end time
    let endDate: Date;
    if (typeof endTime === 'string') {
      endDate = new Date(endTime);
    } else if (typeof endTime === 'number') {
      endDate = new Date(endTime);
    } else {
      endDate = endTime;
    }

    if (!startDate || isNaN(startDate.getTime()) || !endDate || isNaN(endDate.getTime())) {
      return 'Invalid Date Range';
    }

    // Get hours
    const startHour = startDate.getHours();
    const startHour12 = startHour % 12 || 12;
    const startAmpm = startHour >= 12 ? 'PM' : 'AM';

    const endHour = endDate.getHours();
    const endHour12 = endHour % 12 || 12;
    const endAmpm = endHour >= 12 ? 'PM' : 'AM';

    // Format: "10AM - 11AM"
    return `${startHour12}${startAmpm} - ${endHour12}${endAmpm}`;
  }

  formatTimeRangeDate(startTime: string | Date | number): string {
    // Parse start time
    let startDate: Date;
    if (typeof startTime === 'string') {
      startDate = new Date(startTime);
    } else if (typeof startTime === 'number') {
      startDate = new Date(startTime);
    } else {
      startDate = startTime;
    }

    if (!startDate || isNaN(startDate.getTime())) {
      return 'Invalid Date';
    }

    // Format date as M-D-YYYY
    const month = startDate.getMonth() + 1;
    const day = startDate.getDate();
    const year = startDate.getFullYear();

    return `${month}-${day}-${year}`;
  }

  formatEndTime(endTime: string | Date | number): string {
    // Parse end time
    let endDate: Date;
    if (typeof endTime === 'string') {
      endDate = new Date(endTime);
    } else if (typeof endTime === 'number') {
      endDate = new Date(endTime);
    } else {
      endDate = endTime;
    }

    if (!endDate || isNaN(endDate.getTime())) {
      return 'Invalid Time';
    }

    // Get end hour
    const endHour = endDate.getHours();
    const endHour12 = endHour % 12 || 12;
    const endAmpm = endHour >= 12 ? 'PM' : 'AM';

    // Format: "11AM"
    return `${endHour12}${endAmpm}`;
  }

  formatPredictionTime(dateString: string | Date | number): string {
    let date: Date;
    if (typeof dateString === 'string') {
      date = new Date(dateString);
    } else if (typeof dateString === 'number') {
      date = new Date(dateString);
    } else {
      date = dateString;
    }

    if (!date || isNaN(date.getTime())) {
      return 'Invalid Date';
    }

    const hours = date.getHours();
    const minutes = date.getMinutes();
    const seconds = date.getSeconds();
    const hour12 = hours % 12 || 12;
    const ampm = hours >= 12 ? 'PM' : 'AM';

    const minutesStr = minutes.toString().padStart(2, '0');
    const secondsStr = seconds.toString().padStart(2, '0');

    return `${hour12}:${minutesStr}:${secondsStr} ${ampm}`;
  }

  formatPredictionDate(dateString: string | Date | number): string {
    let date: Date;
    if (typeof dateString === 'string') {
      date = new Date(dateString);
    } else if (typeof dateString === 'number') {
      date = new Date(dateString);
    } else {
      date = dateString;
    }

    if (!date || isNaN(date.getTime())) {
      return 'Invalid Date';
    }

    const day = date.getDate().toString().padStart(2, '0');
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const year = date.getFullYear();

    return `${day}/${month}/${year}`;
  }

  viewDetails(anomaly: AnomalyReport): void {
    // Implementation for viewing anomaly details
    // console.log("View details for anomaly:", anomaly);
  }

  resolveAnomaly(anomaly: AnomalyReport): void {
    // Implementation for resolving anomaly
    const existingAnomaly = this.anomalies.get(anomaly.id);
    if (existingAnomaly) {
      existingAnomaly.status = 'Resolved';
      this.dataSource.data = Array.from(this.anomalies.values());
    }
    // console.log("Resolve anomaly:", anomaly);
  }

  clearPredictions(): void {
    if (!this.predictiveModelsService || !this.modelId) {
      // Fallback: just clear the table locally
      this.anomalies.clear();
      this.dataSource.data = [];
      return;
    }

    // Call API to delete predictions from database
    this.predictiveModelsService
      .deleteAnomalyHistoryPredictions(this.modelId, this.predictionType)
      .subscribe({
        next: (response: { deletedCount: number; message: string }) => {
          console.log('Deleted predictions:', response);
          // Clear the table
          this.anomalies.clear();
          this.dataSource.data = [];
        },
        error: (error: any) => {
          console.error('Failed to delete predictions:', error);
          // Still clear the table locally on error
          this.anomalies.clear();
          this.dataSource.data = [];
        }
      });
  }

  getSeverityClass(severity: string): string {
    return `severity-${severity.toLowerCase()}`;
  }

  getStatusClass(status: string): string {
    return `status-${status.toLowerCase()}`;
  }

  getConfidenceClass(confidence: number): string {
    if (confidence >= 90) { return 'high-confidence'; }
    if (confidence >= 75) { return 'medium-confidence'; }
    return 'low-confidence';
  }

  getConfidenceIcon(confidence: number): string {
    if (confidence >= 90) { return 'trending_up'; }
    if (confidence >= 75) { return 'trending_flat'; }
    return 'trending_down';
  }

  isResolved(status: string): boolean {
    return status === 'Resolved';
  }

  editColumnsToDisplay($event: Event): void {
    if ($event) {
      $event.stopPropagation();
    }

    const target = $event.target || $event.srcElement || $event.currentTarget;
    const config = new OverlayConfig({
      panelClass: 'tb-panel-container',
      backdropClass: 'cdk-overlay-transparent-backdrop',
      hasBackdrop: true,
      height: 'fit-content',
      maxHeight: '75vh',
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
            // Update the allColumns display status
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

    const resizeWindows$ = fromEvent(window, 'resize').subscribe(() => {
      overlayRef.updatePosition();
    });
    componentRef.onDestroy(() => {
      resizeWindows$.unsubscribe();
    });
  }

  toggleExpanded(): void {
    this.isExpanded = !this.isExpanded;
  }

  /**
   * Toggle column stickiness for vertical scrolling
   */
  toggleColumnSticky(columnDef: string): void {
    if (this.stickyColumns.has(columnDef)) {
      this.stickyColumns.delete(columnDef);
    } else {
      this.stickyColumns.add(columnDef);
    }
  }

  /**
   * Check if a column is currently sticky
   */
  isColumnSticky(columnDef: string): boolean {
    return this.stickyColumns.has(columnDef);
  }

  /**
   * Get the pin icon for a column based on its sticky state
   */
  getPinIcon(columnDef: string): string {
    return this.isColumnSticky(columnDef) ? 'push_pin' : 'push_pin';
  }

  /**
   * Get the tooltip text for the pin button
   */
  getPinTooltip(columnDef: string): string {
    return this.isColumnSticky(columnDef)
      ? 'Unpin column'
      : 'Pin column when scrolling vertically';
  }

  /**
   * Connect to real-time anomaly stream via WebSocket
   */
  private connectToAnomalyStream(): void {
    if (!this.forecastId) {
      // console.warn(
      //   "[Anomalies] Cannot connect to stream - no forecastId provided"
      // );
      return;
    }
    // If stream subscription hasn't been configured (stream disabled in this build), bail safely
    if (!this.streamSubscription) {
      console.warn('[Anomalies] Stream subscription not configured - live streaming disabled');
      this.isStreamConnected = false;
      return;
    }

    // Get time window for historical data (including time)
    const filterDateTime = this.getFilterDateTime();
    const startTime = filterDateTime ? filterDateTime.getTime() : undefined;

    this.streamError = null;

    try {
      // this.streamSubscription =
      //   this.anomalyStreamService.subscribeToAnomalyStream(
      //     this.forecastId,
      //     startTime
      //   );

      this.anomalyStreamSubscription =
        this.streamSubscription.observable.subscribe({
          next: (message: AnomalyStreamMessage) => {
            this.handleStreamMessage(message);
          },
          error: (error) => {
            console.error('[Anomalies] WebSocket error:', error);
            this.streamError = `Connection error: ${error}`;
            this.isStreamConnected = false;
            console.error(error.reason);
            // console.log("dadsda");
          },
          complete: () => {
            this.isStreamConnected = false;
          },
        });

      this.isStreamConnected = true;
    } catch (error) {
      console.error('[Anomalies] Failed to connect to stream:', error);
      this.streamError = `Failed to connect: ${error}`;
      this.isStreamConnected = false;
    }
  }

  /**
   * Handle incoming WebSocket messages
   */
  private handleStreamMessage(message: AnomalyStreamMessage): void {
    // Handle error messages
    if (message.errorCode || message.errorMsg) {
      console.error('[Anomalies] Stream error:', message.errorMsg);
      this.streamError = message.errorMsg || 'Unknown error';
      return;
    }

    const data = message.data;
    if (!data) {
      return;
    }

    // Handle different message types
    switch (data.type) {
      case 'connection':
        this.isStreamConnected = true;
        this.streamError = null;
        break;

      case 'historical':
        // First message: historical data array from database
        if (Array.isArray(data.data)) {
          // console.log(
          //   `[Anomalies] Received ${data.data.length} historical anomalies`
          // );
          // this.anomalies = data.data;
          this.filterAnomalies(); // Apply current filter to historical data (internal filtering only)
        }
        break;

      // case 'anomaly':
      //   // Subsequent messages: real-time single anomalies
      //   if (data.data && !Array.isArray(data.data)) {
      //     this.handleNewAnomaly(data.data);
      //   }
      //   break;

      case 'error':
        console.error('[Anomalies] Stream error:', data.message);
        this.streamError = data.message || 'Stream error';
        break;
    }
  }

  /**
   * Handle new anomaly received from stream
   */
  private handleNewAnomaly(anomaly: AnomalyReport): void {
    console.log("[Anomalies] New anomaly received:", anomaly);

    // Update creation date to current timestamp (real-time)
    anomaly.creationDate = new Date().toISOString();

    // Ensure startTime/endTime exist - try to parse from timeRange if needed
    if ((!anomaly.startTime || !anomaly.endTime) && anomaly.timeRange) {
      const parts = anomaly.timeRange.split('/');
      if (parts.length === 2) {
        anomaly.startTime = anomaly.startTime || parts[0];
        anomaly.endTime = anomaly.endTime || parts[1];
      } else {
        anomaly.startTime = anomaly.startTime || anomaly.timeRange;
        anomaly.endTime = anomaly.endTime || anomaly.timeRange;
      }
    }

    // Add to the top of the list (most recent first) keyed by id
    this.anomalies.set(anomaly.id, anomaly);

    // Always show new real-time anomalies in the table
    // They are fresh data that just arrived, so they should be visible
    this.dataSource.data = Array.from(this.anomalies.values());

    // console.log(
    //   `[Anomalies] Added new anomaly to table at ${anomaly.creationDate}. Total: ${this.dataSource.data.length}`
    // );

    // Optional: Limit the list size to prevent memory issues
    const maxAnomalies = 500;
    if (this.anomalies.size > maxAnomalies) {
      const excess = this.anomalies.size - maxAnomalies;
      const keysToRemove = Array.from(this.anomalies.keys()).slice(0, excess);
      keysToRemove.forEach((key) => this.anomalies.delete(key));
      // console.log(`[Anomalies] Trimmed anomaly list to ${maxAnomalies} items`);
    }

    // Optional: Show notification for critical anomalies
    if (anomaly.severity === 'Critical') {
      // console.warn(
      //   `[Anomalies] CRITICAL: ${anomaly.errorName} - ${anomaly.description}`
      // );
      // TODO: Add toast notification or alert
    }
  }

  /**
   * Refresh table - clears data and reconnects to stream if forecastId present
   */
  refreshTable(): void {
    this.isRefreshing = true;

    // Clear existing data
    this.anomalies.clear();
    this.dataSource.data = [];

    if (this.forecastId) {
      // Disconnect and reconnect to real-time stream
      // this.disconnectFromAnomalyStream();

      // Wait a moment before reconnecting to ensure clean disconnection
      setTimeout(() => {
        // this.connectToAnomalyStream();
      }, 500);
    }

    setTimeout(() => {
      this.isRefreshing = false;
      // console.log("[Anomalies] Table refreshed and data cleared");
    }, 1000);
  }

  /**
   * Get filter datetime combining date and time fields
   */
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

  /**
   * Apply date filter to current data and refresh from server
   */
  applyDateFilter(): void {
    const filterDateTime = this.getFilterDateTime();
    if (!filterDateTime) {
      return;
    }

    // console.log("[Anomalies] Applying date filter from:", filterDateTime);

    // Refresh table to fetch new data with updated time window
    this.refreshTable();
  }

  /**
   * Apply date filter to existing anomalies array (internal filtering)
   */
  private filterAnomalies(): void {
    const filterDateTime = this.getFilterDateTime();
    if (!filterDateTime) {
      // this.dataSource.data = [...this.anomalies];
      return;
    }

    const filterTime = filterDateTime.getTime();
    // const filteredAnomalies = this.anomalies.filter((anomaly) => {
    //   const anomalyDate = new Date(anomaly.creationDate);
    //   return anomalyDate.getTime() >= filterTime;
    // });

    // console.log(
    //   `[Anomalies] Filtered ${filteredAnomalies.length} of ${this.anomalies.length} anomalies`
    // );
    // this.dataSource.data = [...filteredAnomalies];
  }

  /**
   * Clear date filter - resets to default (last 24 hours)
   */
  clearDateFilter(): void {
    // console.log("[Anomalies] Resetting date filter to default (last 24 hours)");

    // Reset to default: last 24 hours with current time
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    this.filterStartDate = yesterday;
    this.filterHour = yesterday.getHours();
    this.filterMinute = yesterday.getMinutes();
    this.filterSecond = yesterday.getSeconds();

    // Apply the default filter
    this.applyDateFilter();
  }
}
