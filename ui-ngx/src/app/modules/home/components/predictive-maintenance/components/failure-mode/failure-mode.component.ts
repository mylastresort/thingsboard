import { CommonModule } from '@angular/common';
import { Component, Input, OnChanges, SimpleChanges } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTableDataSource, MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import {
  FailureModeHistoryResponse,
  PredictiveModelsService,
} from '@app/core/http/forecast.service';

type FailureModeView = 'maintenance' | 'errors' | 'failures';

interface FailureModeTableFilter {
  search: string;
  device: string;
}

interface FailureModeDeviceOption {
  id: string;
  name: string;
}

interface FailureModeBaseRow {
  datetime: string;
  deviceId: string;
  deviceName: string;
  deviceType: string;
}

interface FailureModeMaintenanceRow extends FailureModeBaseRow {
  description: string;
  partsReplaced: string;
}

interface FailureModeErrorRow extends FailureModeBaseRow {
  errorCode: string;
}

interface FailureModeFailureRow extends FailureModeBaseRow {
  rootCause: string;
}

@Component({
  selector: 'tb-failure-mode',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatTabsModule,
    MatTableModule,
    MatTooltipModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './failure-mode.component.html',
  styleUrls: ['./failure-mode.component.scss'],
})
export class FailureModeComponent implements OnChanges {
  @Input() modelId = '';
  @Input() deviceId = '';
  @Input() allDevicesMode = false;

  readonly allDevicesFilter = '__all__';

  isLoading = false;
  errorMessage = '';

  maintenanceRows: FailureModeMaintenanceRow[] = [];
  errorRows: FailureModeErrorRow[] = [];
  failureRows: FailureModeFailureRow[] = [];

  maintenanceDataSource = new MatTableDataSource<FailureModeMaintenanceRow>([]);
  errorDataSource = new MatTableDataSource<FailureModeErrorRow>([]);
  failureDataSource = new MatTableDataSource<FailureModeFailureRow>([]);

  maintenanceSearch = '';
  errorSearch = '';
  failureSearch = '';

  maintenanceDeviceFilter = this.allDevicesFilter;
  errorDeviceFilter = this.allDevicesFilter;
  failureDeviceFilter = this.allDevicesFilter;

  maintenanceDeviceOptions: FailureModeDeviceOption[] = [];
  errorDeviceOptions: FailureModeDeviceOption[] = [];
  failureDeviceOptions: FailureModeDeviceOption[] = [];

  maintenanceColumns = ['datetime', 'deviceName', 'description', 'partsReplaced'];
  errorColumns = ['datetime', 'deviceName', 'errorCode'];
  failureColumns = ['datetime', 'deviceName', 'rootCause'];

  constructor(private predictiveModelsService: PredictiveModelsService) {
    this.configureFilters();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['modelId'] || changes['deviceId'] || changes['allDevicesMode']) {
      this.loadFailureModeHistory();
    }
  }

  loadFailureModeHistory(): void {
    if (!this.modelId && !this.allDevicesMode) {
      this.setRows([], [], []);
      return;
    }

    this.isLoading = true;
    this.errorMessage = '';

    const request$ = this.allDevicesMode
      ? this.predictiveModelsService.getAllDevicesFailureModeHistory()
      : this.predictiveModelsService.getFailureModeHistory(this.modelId);

    request$.subscribe({
      next: (response: FailureModeHistoryResponse) => {
        const maintenanceRows = this.sortRows(
          (response.maintenance || []).map((item) => ({
            datetime: item.datetime,
            deviceId: item.device_id || response.deviceId || this.deviceId || '',
            deviceName: item.device_name || item.device_id || response.deviceId || this.deviceId || 'N/A',
            deviceType: item.device_type || '',
            description: item.description || '',
            partsReplaced: item.parts_replaced || item.comp || 'N/A',
          }))
        );
        const errorRows = this.sortRows(
          (response.errors || []).map((item) => ({
            datetime: item.datetime,
            deviceId: item.device_id || response.deviceId || this.deviceId || '',
            deviceName: item.device_name || item.device_id || response.deviceId || this.deviceId || 'N/A',
            deviceType: item.device_type || '',
            errorCode: item.errorID || item.error_code || 'N/A',
          }))
        );
        const failureRows = this.sortRows(
          (response.failures || []).map((item) => ({
            datetime: item.datetime,
            deviceId: item.device_id || response.deviceId || this.deviceId || '',
            deviceName: item.device_name || item.device_id || response.deviceId || this.deviceId || 'N/A',
            deviceType: item.device_type || '',
            rootCause: item.failure || item.root_cause || 'N/A',
          }))
        );
        this.setRows(maintenanceRows, errorRows, failureRows);
        this.isLoading = false;
      },
      error: (error) => {
        console.error('[FailureMode] Failed to load history:', error);
        this.errorMessage = 'Unable to load failure mode history.';
        this.isLoading = false;
      },
    });
  }

  refresh(): void {
    this.loadFailureModeHistory();
  }

  updateSearch(view: FailureModeView, value: string): void {
    switch (view) {
      case 'maintenance':
        this.maintenanceSearch = value;
        break;
      case 'errors':
        this.errorSearch = value;
        break;
      case 'failures':
        this.failureSearch = value;
        break;
    }
    this.applyFilter(view);
  }

  clearSearch(view: FailureModeView): void {
    this.updateSearch(view, '');
  }

  updateDeviceFilter(view: FailureModeView, value: string): void {
    switch (view) {
      case 'maintenance':
        this.maintenanceDeviceFilter = value;
        break;
      case 'errors':
        this.errorDeviceFilter = value;
        break;
      case 'failures':
        this.failureDeviceFilter = value;
        break;
    }
    this.applyFilter(view);
  }

  getFilteredCount(view: FailureModeView): number {
    return this.getDataSource(view).filteredData.length;
  }

  getEmptyStateMessage(view: FailureModeView): string {
    const label = view === 'errors' ? 'error' : view === 'failures' ? 'failure' : 'maintenance';
    const rowCount = this.getRowCount(view);
    return rowCount === 0
      ? `No ${label} records found.`
      : `No ${label} records match the current filters.`;
  }

  private configureFilters(): void {
    this.maintenanceDataSource.filterPredicate = (row, filter) =>
      this.matchesFilter(row, filter, [row.description, row.partsReplaced]);
    this.errorDataSource.filterPredicate = (row, filter) =>
      this.matchesFilter(row, filter, [row.errorCode]);
    this.failureDataSource.filterPredicate = (row, filter) =>
      this.matchesFilter(row, filter, [row.rootCause]);
  }

  private setRows(
    maintenanceRows: FailureModeMaintenanceRow[],
    errorRows: FailureModeErrorRow[],
    failureRows: FailureModeFailureRow[]
  ): void {
    this.maintenanceRows = maintenanceRows;
    this.errorRows = errorRows;
    this.failureRows = failureRows;

    this.maintenanceDataSource.data = maintenanceRows;
    this.errorDataSource.data = errorRows;
    this.failureDataSource.data = failureRows;

    this.maintenanceDeviceOptions = this.getDeviceOptions(maintenanceRows);
    this.errorDeviceOptions = this.getDeviceOptions(errorRows);
    this.failureDeviceOptions = this.getDeviceOptions(failureRows);

    this.applyFilter('maintenance');
    this.applyFilter('errors');
    this.applyFilter('failures');
  }

  private applyFilter(view: FailureModeView): void {
    const search = this.getSearch(view).trim().toLowerCase();
    const device = this.getDeviceFilter(view);
    this.getDataSource(view).filter = JSON.stringify({ search, device });
  }

  private matchesFilter(
    row: FailureModeBaseRow,
    filter: string,
    searchableValues: Array<string | undefined>
  ): boolean {
    const parsedFilter = this.parseFilter(filter);
    const matchesDevice =
      parsedFilter.device === this.allDevicesFilter ||
      row.deviceId === parsedFilter.device ||
      row.deviceName === parsedFilter.device;

    if (!matchesDevice) {
      return false;
    }

    if (!parsedFilter.search) {
      return true;
    }

    const searchableText = [
      row.datetime,
      row.deviceId,
      row.deviceName,
      row.deviceType,
      ...searchableValues,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();

    return searchableText.includes(parsedFilter.search);
  }

  private parseFilter(filter: string): FailureModeTableFilter {
    try {
      const parsed = JSON.parse(filter) as FailureModeTableFilter;
      return {
        search: parsed.search || '',
        device: parsed.device || this.allDevicesFilter,
      };
    } catch {
      return { search: '', device: this.allDevicesFilter };
    }
  }

  private getDataSource(view: FailureModeView): MatTableDataSource<FailureModeBaseRow> {
    switch (view) {
      case 'maintenance':
        return this.maintenanceDataSource;
      case 'errors':
        return this.errorDataSource;
      case 'failures':
        return this.failureDataSource;
    }
  }

  private getSearch(view: FailureModeView): string {
    switch (view) {
      case 'maintenance':
        return this.maintenanceSearch;
      case 'errors':
        return this.errorSearch;
      case 'failures':
        return this.failureSearch;
    }
  }

  private getDeviceFilter(view: FailureModeView): string {
    switch (view) {
      case 'maintenance':
        return this.maintenanceDeviceFilter;
      case 'errors':
        return this.errorDeviceFilter;
      case 'failures':
        return this.failureDeviceFilter;
    }
  }

  private getRowCount(view: FailureModeView): number {
    switch (view) {
      case 'maintenance':
        return this.maintenanceRows.length;
      case 'errors':
        return this.errorRows.length;
      case 'failures':
        return this.failureRows.length;
    }
  }

  private getDeviceOptions<T extends FailureModeBaseRow>(rows: T[]): FailureModeDeviceOption[] {
    const devices = new Map<string, string>();
    rows.forEach((row) => {
      const id = row.deviceId || row.deviceName;
      if (id && id !== 'N/A') {
        devices.set(id, row.deviceName || id);
      }
    });

    return Array.from(devices.entries())
      .map(([id, name]) => ({ id, name }))
      .sort((left, right) => left.name.localeCompare(right.name));
  }

  private sortRows<T extends { datetime: string }>(rows: T[]): T[] {
    return [...rows].sort(
      (left, right) => new Date(right.datetime).getTime() - new Date(left.datetime).getTime()
    );
  }
}
