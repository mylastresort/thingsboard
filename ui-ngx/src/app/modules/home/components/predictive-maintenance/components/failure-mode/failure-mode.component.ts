import { CommonModule } from '@angular/common';
import { Component, Inject, Input, OnChanges, SimpleChanges } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import {
  MAT_DIALOG_DATA,
  MatDialog,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTableDataSource, MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { DeviceService } from '@app/core/http/device.service';
import { DialogService } from '@app/core/services/dialog.service';
import { catchError, debounceTime, distinctUntilChanged, forkJoin, map, Observable, of, startWith, switchMap } from 'rxjs';
import {
  FailureModeRecordPayload,
  FailureModeRecordType,
  FailureModeHistoryResponse,
  PredictiveModelsService,
} from '@app/core/http/forecast.service';
import { PageLink } from '@shared/models/page/page-link';
import { Direction } from '@shared/models/page/sort-order';

type FailureModeView = FailureModeRecordType;

interface FailureModeTableFilter {
  search: string;
  device: string;
}

interface FailureModeDeviceOption {
  id: string;
  name: string;
}

interface FailureModeDialogResult {
  records: FailureModeRecordPayload[];
}

interface FailureModeBaseRow {
  id: string;
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
    ReactiveFormsModule,
    MatAutocompleteModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatTabsModule,
    MatTableModule,
    MatTooltipModule,
    MatSnackBarModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './failure-mode.component.html',
  styleUrls: ['./failure-mode.component.scss'],
})
export class FailureModeComponent implements OnChanges {
  @Input() modelId = '';
  @Input() deviceId = '';
  @Input() deviceName = '';
  @Input() allDevicesMode = false;

  readonly allDevicesFilter = '__all__';

  isLoading = false;
  errorMessage = '';
  activeView: FailureModeView = 'maintenance';

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

  maintenanceColumns = ['datetime', 'deviceName', 'description', 'partsReplaced', 'actions'];
  errorColumns = ['datetime', 'deviceName', 'errorCode', 'actions'];
  failureColumns = ['datetime', 'deviceName', 'rootCause', 'actions'];

  constructor(
    private predictiveModelsService: PredictiveModelsService,
    private dialog: MatDialog,
    private snackBar: MatSnackBar,
    private dialogService: DialogService,
    private deviceService: DeviceService
  ) {
    this.configureFilters();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['modelId'] || changes['deviceId'] || changes['allDevicesMode']) {
      this.loadFailureModeHistory();
    } else if (changes['deviceName']) {
      this.applyKnownDeviceNameToRows();
    }
  }

  loadFailureModeHistory(): void {
    if (!this.allDevicesMode && !this.deviceId) {
      this.setRows([], [], []);
      return;
    }

    this.isLoading = true;
    this.errorMessage = '';

    const request$ = this.allDevicesMode
      ? this.predictiveModelsService.getAllDevicesFailureModeHistory()
      : this.predictiveModelsService.getFailureModeHistory(this.deviceId);

    request$.subscribe({
      next: (response: FailureModeHistoryResponse) => {
        const maintenanceRows = this.sortRows(
          (response.maintenance || []).map((item) => ({
            id: item.id || '',
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
            id: item.id || '',
            datetime: item.datetime,
            deviceId: item.device_id || response.deviceId || this.deviceId || '',
            deviceName: item.device_name || item.device_id || response.deviceId || this.deviceId || 'N/A',
            deviceType: item.device_type || '',
            errorCode: item.errorID || item.error_code || 'N/A',
          }))
        );
        const failureRows = this.sortRows(
          (response.failures || []).map((item) => ({
            id: item.id || '',
            datetime: item.datetime,
            deviceId: item.device_id || response.deviceId || this.deviceId || '',
            deviceName: item.device_name || item.device_id || response.deviceId || this.deviceId || 'N/A',
            deviceType: item.device_type || '',
            rootCause: item.failure || item.root_cause || 'N/A',
          }))
        );
        this.setRows(maintenanceRows, errorRows, failureRows);
        this.resolveDeviceNames();
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

  setActiveView(index: number): void {
    this.activeView = index === 1 ? 'errors' : index === 2 ? 'failures' : 'maintenance';
  }

  openAddRecordDialog(view: FailureModeView): void {
    this.openRecordDialog(view);
  }

  openEditRecordDialog(view: FailureModeView, row: FailureModeBaseRow): void {
    this.openRecordDialog(view, row);
  }

  deleteRecord(view: FailureModeView, row: FailureModeBaseRow): void {
    if (!row.id) {
      this.showMessage('Unable to delete record without database id.');
      return;
    }

    const label = this.getRecordTypeLabel(view);
    const summary = this.getDeleteRecordSummary(view, row);
    this.dialogService.confirm(
      `Delete ${label} record`,
      `Are you sure you want to delete this ${label} record${summary ? ` (${summary})` : ''}?`,
      'Cancel',
      'Delete',
      true
    ).subscribe((confirmed) => {
      if (!confirmed) {
        return;
      }

      this.predictiveModelsService.deleteFailureModeRecord(view, row.id).subscribe({
        next: () => {
          this.showMessage('Failure mode record deleted.');
          this.loadFailureModeHistory();
        },
        error: (error) => {
          console.error('[FailureMode] Failed to delete record:', error);
          this.showMessage('Unable to delete failure mode record.');
        },
      });
    });
  }

  uploadCsv(view: FailureModeView, event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';

    if (!file) {
      return;
    }

    this.predictiveModelsService.importFailureModeRecords(view, file).subscribe({
      next: (result) => {
        if (result.errors?.length) {
          this.showMessage(`CSV import failed at row ${result.errors[0].row}.`);
          return;
        }
        this.showMessage(`Imported ${result.importedCount} records.`);
        this.loadFailureModeHistory();
      },
      error: (error) => {
        console.error('[FailureMode] Failed to import CSV:', error);
        this.showMessage('Unable to import CSV.');
      },
    });
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

  getCurrentDeviceDisplayName(): string {
    return (
      this.deviceName ||
      [...this.maintenanceRows, ...this.errorRows, ...this.failureRows]
        .find((row) => row.deviceId === this.deviceId && row.deviceName && row.deviceName !== row.deviceId)
        ?.deviceName ||
      this.deviceId
    );
  }

  private configureFilters(): void {
    this.maintenanceDataSource.filterPredicate = (row, filter) =>
      this.matchesFilter(row, filter, [row.description, row.partsReplaced]);
    this.errorDataSource.filterPredicate = (row, filter) =>
      this.matchesFilter(row, filter, [row.errorCode]);
    this.failureDataSource.filterPredicate = (row, filter) =>
      this.matchesFilter(row, filter, [row.rootCause]);
  }

  private openRecordDialog(view: FailureModeView, row?: FailureModeBaseRow): void {
    const dialogRef = this.dialog.open<
      FailureModeRecordDialogComponent,
      FailureModeRecordDialogData,
      FailureModeDialogResult
    >(FailureModeRecordDialogComponent, {
      width: '820px',
      panelClass: ['tb-dialog'],
      data: {
        view,
        row,
        defaultDeviceId: row?.deviceId || this.deviceId || this.getDefaultDeviceId(view),
        defaultDeviceName: row?.deviceName || this.deviceName || '',
        hideDeviceField: !this.allDevicesMode && !!this.deviceId,
      },
    });

    dialogRef.afterClosed().subscribe((result) => {
      if (!result?.records?.length) {
        return;
      }

      const request$ = row?.id
        ? this.predictiveModelsService.updateFailureModeRecord(view, row.id, result.records[0])
        : this.predictiveModelsService.createFailureModeRecords(result.records);

      request$.subscribe({
        next: () => {
          this.showMessage(
            row?.id
              ? 'Failure mode record updated.'
              : `${result.records.length} failure mode record${result.records.length === 1 ? '' : 's'} added.`
          );
          this.loadFailureModeHistory();
        },
        error: (error) => {
          console.error('[FailureMode] Failed to save record:', error);
          this.showMessage('Unable to save failure mode record.');
        },
      });
    });
  }

  private getDefaultDeviceId(view: FailureModeView): string {
    const options = this.getDeviceOptionsForView(view);
    return options.length === 1 ? options[0].id : '';
  }

  private getDeviceOptionsForView(view: FailureModeView): FailureModeDeviceOption[] {
    switch (view) {
      case 'maintenance':
        return this.maintenanceDeviceOptions;
      case 'errors':
        return this.errorDeviceOptions;
      case 'failures':
        return this.failureDeviceOptions;
    }
  }

  private showMessage(message: string): void {
    this.snackBar.open(message, undefined, { duration: 3000 });
  }

  private getRecordTypeLabel(view: FailureModeView): string {
    return view === 'errors' ? 'error' : view === 'failures' ? 'failure' : 'maintenance';
  }

  private getDeleteRecordSummary(view: FailureModeView, row: FailureModeBaseRow): string {
    if (view === 'maintenance') {
      const maintenanceRow = row as FailureModeMaintenanceRow;
      return maintenanceRow.description || maintenanceRow.partsReplaced || row.datetime;
    }
    if (view === 'errors') {
      return (row as FailureModeErrorRow).errorCode || row.datetime;
    }
    return (row as FailureModeFailureRow).rootCause || row.datetime;
  }

  private setRows(
    maintenanceRows: FailureModeMaintenanceRow[],
    errorRows: FailureModeErrorRow[],
    failureRows: FailureModeFailureRow[]
  ): void {
    this.applyKnownDeviceName(maintenanceRows);
    this.applyKnownDeviceName(errorRows);
    this.applyKnownDeviceName(failureRows);

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

  private resolveDeviceNames(): void {
    const deviceIds = Array.from(
      new Set(
        [...this.maintenanceRows, ...this.errorRows, ...this.failureRows]
          .filter((row) => this.needsDeviceName(row))
          .map((row) => row.deviceId)
      )
    );

    if (!deviceIds.length) {
      return;
    }

    forkJoin(
      deviceIds.map((deviceId) =>
        this.deviceService.getDeviceInfo(deviceId).pipe(
          map((device) => ({
            id: deviceId,
            name: device.name || device.label || deviceId,
          })),
          catchError((error) => {
            console.error(`[FailureMode] Failed to resolve device name for ${deviceId}:`, error);
            return of({ id: deviceId, name: deviceId });
          })
        )
      )
    ).subscribe((devices) => {
      const deviceNames = new Map(devices.map((device) => [device.id, device.name]));
      this.setRows(
        this.withResolvedDeviceNames(this.maintenanceRows, deviceNames),
        this.withResolvedDeviceNames(this.errorRows, deviceNames),
        this.withResolvedDeviceNames(this.failureRows, deviceNames)
      );
    });
  }

  private applyKnownDeviceNameToRows(): void {
    this.setRows([...this.maintenanceRows], [...this.errorRows], [...this.failureRows]);
  }

  private applyKnownDeviceName<T extends FailureModeBaseRow>(rows: T[]): void {
    if (!this.deviceName || !this.deviceId) {
      return;
    }
    rows.forEach((row) => {
      if (row.deviceId === this.deviceId && this.needsDeviceName(row)) {
        row.deviceName = this.deviceName;
      }
    });
  }

  private withResolvedDeviceNames<T extends FailureModeBaseRow>(
    rows: T[],
    deviceNames: Map<string, string>
  ): T[] {
    return rows.map((row) => ({
      ...row,
      deviceName: this.needsDeviceName(row)
        ? deviceNames.get(row.deviceId) || row.deviceName
        : row.deviceName,
    }));
  }

  private needsDeviceName(row: FailureModeBaseRow): boolean {
    return !!row.deviceId && (!row.deviceName || row.deviceName === row.deviceId);
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

interface FailureModeRecordDialogData {
  view: FailureModeView;
  row?: FailureModeBaseRow;
  defaultDeviceId: string;
  defaultDeviceName?: string;
  hideDeviceField?: boolean;
}

@Component({
  selector: 'tb-failure-mode-record-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatAutocompleteModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
  ],
  template: `
    <h2 mat-dialog-title>{{ data.row ? 'Edit' : 'Add' }} {{ title }}</h2>
    <mat-dialog-content>
      <form [formGroup]="form" class="failure-mode-record-form">
        <mat-form-field appearance="outline" *ngIf="!data.hideDeviceField">
          <mat-label>Device</mat-label>
          <input
            matInput
            formControlName="device_name"
            required
            [matAutocomplete]="deviceAutocomplete"
            (blur)="resolveTypedDevice()"
          />
          <mat-autocomplete
            #deviceAutocomplete="matAutocomplete"
            (optionSelected)="selectDevice($event.option.value)"
          >
            <mat-option *ngIf="isLoadingDevices" disabled>
              Loading devices...
            </mat-option>
            <mat-option *ngFor="let device of filteredDevices | async" [value]="device.name">
              {{ device.name }}
            </mat-option>
            <mat-option
              *ngIf="!isLoadingDevices && isDevicesPrefetched && deviceOptions.length === 0"
              disabled
            >
              No devices found
            </mat-option>
          </mat-autocomplete>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Time</mat-label>
          <input matInput type="datetime-local" formControlName="datetime" required />
        </mat-form-field>

        <mat-form-field appearance="outline" *ngIf="data.view === 'maintenance'">
          <mat-label>Description</mat-label>
          <input matInput formControlName="description" />
        </mat-form-field>

        <mat-form-field appearance="outline" *ngIf="data.view === 'maintenance'">
          <mat-label>Parts Replaced</mat-label>
          <input matInput formControlName="parts_replaced" />
        </mat-form-field>

        <mat-form-field appearance="outline" *ngIf="data.view === 'errors'">
          <mat-label>Error Code</mat-label>
          <input matInput formControlName="error_code" required />
        </mat-form-field>

        <mat-form-field appearance="outline" *ngIf="data.view === 'failures'">
          <mat-label>Root Cause</mat-label>
          <input matInput formControlName="root_cause" required />
        </mat-form-field>
      </form>

      <div class="queued-records" *ngIf="!data.row && queuedRecords.length">
        <div class="queued-records-header">Records to add</div>
        <div class="queued-record" *ngFor="let record of queuedRecords; let index = index">
          <span>{{ getDeviceName(record.device_id) }}</span>
          <span>{{ record.datetime | date: 'short' }}</span>
          <span>{{ getRecordSummary(record) }}</span>
          <button mat-icon-button type="button" (click)="removeQueuedRecord(index)">
            <mat-icon>close</mat-icon>
          </button>
        </div>
      </div>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" (click)="dialogRef.close()">Cancel</button>
      <button
        *ngIf="!data.row"
        mat-stroked-button
        type="button"
        [disabled]="form.invalid"
        (click)="queueCurrentRecord()"
      >
        <mat-icon>playlist_add</mat-icon>
        <span>Add record</span>
      </button>
      <button
        mat-flat-button
        color="primary"
        type="button"
        [disabled]="data.row ? form.invalid : (form.invalid && !queuedRecords.length)"
        (click)="save()"
      >
        {{ data.row ? 'Save' : 'Add' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [
    `
      .failure-mode-record-form {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 16px;
        min-width: min(640px, 80vw);
        padding-top: 8px;
      }

      .queued-records {
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin-top: 16px;
      }

      .queued-records-header {
        font-weight: 500;
      }

      .queued-record {
        display: grid;
        grid-template-columns: minmax(0, 1fr) 140px minmax(0, 1fr) 40px;
        align-items: center;
        gap: 8px;
        min-height: 40px;
      }

      .queued-record span {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      @media (max-width: 640px) {
        .failure-mode-record-form {
          grid-template-columns: 1fr;
          min-width: 0;
        }
      }
    `,
  ],
})
export class FailureModeRecordDialogComponent {
  private readonly deviceSearchPageSize = 10;

  readonly title: string;
  queuedRecords: FailureModeRecordPayload[] = [];
  filteredDevices: Observable<FailureModeDeviceOption[]>;
  deviceOptions: FailureModeDeviceOption[] = [];
  isLoadingDevices = false;
  isDevicesPrefetched = false;

  readonly form = this.fb.group({
    device_id: ['', Validators.required],
    device_name: ['', Validators.required],
    datetime: ['', Validators.required],
    description: [''],
    parts_replaced: [''],
    error_code: [''],
    root_cause: [''],
  });

  constructor(
    private fb: FormBuilder,
    private deviceService: DeviceService,
    public dialogRef: MatDialogRef<FailureModeRecordDialogComponent, FailureModeDialogResult>,
    @Inject(MAT_DIALOG_DATA) public data: FailureModeRecordDialogData
  ) {
    this.title =
      this.data.view === 'maintenance'
        ? 'Maintenance Record'
        : this.data.view === 'errors'
          ? 'Error Record'
          : 'Failure Record';

    this.form.patchValue({
      device_id: this.data.row?.deviceId || this.data.defaultDeviceId || '',
      device_name:
        this.data.row?.deviceName ||
        this.data.defaultDeviceName ||
        this.getDeviceName(this.data.defaultDeviceId),
      datetime: this.toDateTimeLocal(this.data.row?.datetime),
      description: (this.data.row as FailureModeMaintenanceRow)?.description || '',
      parts_replaced: (this.data.row as FailureModeMaintenanceRow)?.partsReplaced || '',
      error_code: (this.data.row as FailureModeErrorRow)?.errorCode || '',
      root_cause: (this.data.row as FailureModeFailureRow)?.rootCause || '',
    });

    this.filteredDevices = this.form.controls.device_name.valueChanges.pipe(
      startWith(this.form.controls.device_name.value || ''),
      debounceTime(250),
      distinctUntilChanged(),
      switchMap((searchText) => this.fetchDeviceOptions(searchText || ''))
    );

    if (this.data.view === 'errors') {
      this.form.controls.error_code.addValidators(Validators.required);
      this.form.controls.error_code.updateValueAndValidity();
    }
    if (this.data.view === 'failures') {
      this.form.controls.root_cause.addValidators(Validators.required);
      this.form.controls.root_cause.updateValueAndValidity();
    }
  }

  selectDevice(deviceName: string): void {
    const device = this.deviceOptions.find((item) => item.name === deviceName);
    if (device) {
      this.form.patchValue({
        device_id: device.id,
        device_name: device.name,
      });
    }
  }

  resolveTypedDevice(): void {
    if (this.data.hideDeviceField) {
      this.form.patchValue({
        device_id: this.data.defaultDeviceId || '',
        device_name: this.data.defaultDeviceName || this.data.defaultDeviceId || '',
      });
      return;
    }

    const deviceName = (this.form.controls.device_name.value || '').trim();
    const device = this.deviceOptions.find(
      (item) => item.name.toLowerCase() === deviceName.toLowerCase()
    );
    if (device) {
      this.form.patchValue({
        device_id: device.id,
        device_name: device.name,
      });
    } else if (!this.data.row) {
      this.form.controls.device_id.setValue('');
    }
  }

  queueCurrentRecord(): void {
    const record = this.buildRecord();
    if (!record) {
      return;
    }

    this.queuedRecords = [...this.queuedRecords, record];
    this.form.patchValue({
      datetime: '',
      description: '',
      parts_replaced: '',
      error_code: '',
      root_cause: '',
    });
  }

  removeQueuedRecord(index: number): void {
    this.queuedRecords = this.queuedRecords.filter((_, currentIndex) => currentIndex !== index);
  }

  getDeviceName(deviceId: string): string {
    if (deviceId === this.data.defaultDeviceId && this.data.defaultDeviceName) {
      return this.data.defaultDeviceName;
    }
    return this.deviceOptions.find((device) => device.id === deviceId)?.name || deviceId || '';
  }

  getRecordSummary(record: FailureModeRecordPayload): string {
    if (this.data.view === 'maintenance') {
      return record.parts_replaced || record.description || 'Maintenance';
    }
    if (this.data.view === 'errors') {
      return record.error_code || 'Error';
    }
    return record.root_cause || 'Failure';
  }

  save(): void {
    const currentRecord = this.buildRecord();
    if (!currentRecord) {
      if (!this.data.row && this.queuedRecords.length) {
        this.dialogRef.close({ records: this.queuedRecords });
      }
      return;
    }

    this.dialogRef.close({
      records: this.data.row ? [currentRecord] : [...this.queuedRecords, currentRecord],
    });
  }

  private buildRecord(): FailureModeRecordPayload | null {
    this.resolveTypedDevice();

    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return null;
    }

    const value = this.form.getRawValue();
    return {
      type: this.data.view,
      device_id: value.device_id || '',
      datetime: this.fromDateTimeLocal(value.datetime || ''),
      description: value.description || undefined,
      parts_replaced: value.parts_replaced || undefined,
      error_code: value.error_code || undefined,
      root_cause: value.root_cause || undefined,
    };
  }

  private toDateTimeLocal(value?: string): string {
    const date = value ? new Date(value) : new Date();
    if (Number.isNaN(date.getTime())) {
      return '';
    }
    const offsetMs = date.getTimezoneOffset() * 60000;
    return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
  }

  private fromDateTimeLocal(value: string): string {
    return new Date(value).toISOString();
  }

  private fetchDeviceOptions(searchText: string): Observable<FailureModeDeviceOption[]> {
    this.isLoadingDevices = true;

    const pageLink = new PageLink(this.deviceSearchPageSize, 0, searchText || null, {
      property: 'name',
      direction: Direction.ASC,
    });

    return this.deviceService.getTenantDeviceInfos(pageLink).pipe(
      map((pageData) =>
        (pageData.data || []).map((device) => ({
          id: device.id?.id || '',
          name: device.name || device.label || device.id?.id || '',
        }))
      ),
      catchError((error) => {
        console.error('[FailureMode] Failed to search devices:', error);
        return of([]);
      }),
      map((devices) => {
        this.deviceOptions = devices;
        this.isDevicesPrefetched = true;
        this.isLoadingDevices = false;
        const deviceName = (this.form.controls.device_name.value || '').trim().toLowerCase();
        const exactDevice = devices.find((device) => device.name.toLowerCase() === deviceName);
        if (exactDevice && this.form.controls.device_id.value !== exactDevice.id) {
          this.form.patchValue({
            device_id: exactDevice.id,
            device_name: exactDevice.name,
          });
        }
        return devices;
      })
    );
  }
}
