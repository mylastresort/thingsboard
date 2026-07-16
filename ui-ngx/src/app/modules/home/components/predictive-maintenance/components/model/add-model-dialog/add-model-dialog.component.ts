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

import { Component, Inject, OnDestroy, OnInit } from '@angular/core';
import {
  FormControl,
  FormsModule,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { AttributeService, DeviceService } from '@app/core/public-api';
import { DeviceInfo } from '@shared/models/device.models';
import { PageLink } from '@shared/models/page/page-link';
import { BehaviorSubject, Observable, of, Subject } from 'rxjs';
import { AvailableModelsResponse, PredictiveModelsService } from '@app/core/http/forecast.service';
import { catchError, debounceTime, distinctUntilChanged, map, startWith, switchMap, takeUntil } from 'rxjs/operators';

import { CommonModule } from '@angular/common';
import { MatDialogModule } from '@angular/material/dialog';
import { Direction, EntityType } from '@app/shared/public-api';
import { ForecastField } from '@app/modules/home/models/predictive-maintenance.models';
import { Forecast, ForecastCreate } from '@app/shared/models/forecast.models';
import { startCase } from 'lodash';

import { StepperModule } from 'primeng/stepper';
import { InputTextModule } from 'primeng/inputtext';
import { AutoCompleteModule } from 'primeng/autocomplete';
import { SelectModule } from 'primeng/select';
import { CalendarModule } from 'primeng/calendar';
import { ButtonModule } from 'primeng/button';
import { TextareaModule } from 'primeng/textarea';
import { FloatLabelModule } from 'primeng/floatlabel';
import { IconFieldModule } from 'primeng/iconfield';
import { InputIconModule } from 'primeng/inputicon';

@Component({
  selector: 'app-add-model-dialog',
  templateUrl: './add-model-dialog.component.html',
  styleUrls: ['./add-model-dialog.component.scss'],
  standalone: true,
  imports: [
    CommonModule,
    MatDialogModule,
    FormsModule,
    ReactiveFormsModule,
    StepperModule,
    InputTextModule,
    AutoCompleteModule,
    SelectModule,
    CalendarModule,
    ButtonModule,
    TextareaModule,
    FloatLabelModule,
    IconFieldModule,
    InputIconModule,
  ],
})
export class AddModelDialogComponent implements OnInit, OnDestroy {
  private destroy$ = new Subject<void>();

  private readonly deviceSearchPageSize = 10;

  private devicesSubject = new BehaviorSubject<DeviceInfo[]>([]);

  selectedDevice: DeviceInfo | null = null;

  fields: ForecastField[] = [];

  availableTelemetry: string[] = [];

  myControl = new FormControl<string | DeviceInfo>('', Validators.required);

  forecastNameControl = new FormControl('', Validators.required);

  filteredDevices: DeviceInfo[] = [];

  devicesList: DeviceInfo[] = [];

  noTelemetryMessage: string | null = null;

  isDevicesPrefetched = false;

  isLoadingDevices = false;

  isEditMode = false;

  editingForecast: any = null;

  originalAttributes: string[] = [];

  originalForecastAlgorithm = '';

  originalAnomalyAlgorithm = '';

  currentStep = 1;

  totalSteps = 3;

  globalStartDate: Date | null = null;

  globalEndDate: Date | null = null;

  anomaliesStartDate: Date | null = null;

  anomaliesEndDate: Date | null = null;

  forecastAlgorithmControl = new FormControl('', Validators.required);

  anomaliesAlgorithmControl = new FormControl('', Validators.required);

  aggregationOptions = [
    { value: 'average', label: 'Average' },
    { value: 'min', label: 'Minimum' },
    { value: 'max', label: 'Maximum' },
  ];

  groupByOptions = [
    { value: 5000, label: '5 Seconds' },
    { value: 30000, label: '30 Seconds' },
    { value: 60000, label: '1 Minute' },
    { value: 300000, label: '5 Minutes' },
    { value: 900000, label: '15 Minutes' },
    { value: 1800000, label: '30 Minutes' },
    { value: 3600000, label: '1 Hour' },
    { value: 7200000, label: '2 Hours' },
    { value: 21600000, label: '6 Hours' },
    { value: 43200000, label: '12 Hours' },
    { value: 86400000, label: '24 Hours' },
  ];

  customTimeFields: { [key: number]: { hours: number; minutes: number; seconds: number } } = {};

  forecastAlgorithmOptions: { value: string; label: string }[] = [];

  anomaliesAlgorithmOptions: { value: string; label: string }[] = [];

  constructor(
    public dialogRef: MatDialogRef<AddModelDialogComponent, any>,
    @Inject(MAT_DIALOG_DATA) public data: any,
    private deviceService: DeviceService,
    private attributeService: AttributeService,
    private predictiveModelsService: PredictiveModelsService
  ) {
    if (data && data.isEdit) {
      this.isEditMode = true;
      this.editingForecast = data.forecastData;
    }
  }

  ngOnInit(): void {
    this.predictiveModelsService.getAvailableModels().subscribe((res: AvailableModelsResponse) => {
      if (res.ForecastModel && Array.isArray(res.ForecastModel)) {
        this.forecastAlgorithmOptions = res.ForecastModel.map((item: any) => ({
          value: item.model_name,
          label: startCase(item.model_name)
        }));
      }
      if (res.AnomalyPredictor && Array.isArray(res.AnomalyPredictor)) {
        this.anomaliesAlgorithmOptions = res.AnomalyPredictor.map((item: any) => ({
          value: item.model_name,
          label: startCase(item.model_name)
        }));
      }
    });

    this.globalEndDate = new Date();
    this.globalEndDate.setHours(23, 59, 59, 999);

    this.globalStartDate = new Date();
    this.globalStartDate.setDate(this.globalStartDate.getDate() - 30);
    this.globalStartDate.setHours(0, 0, 0, 0);

    this.anomaliesEndDate = new Date();
    this.anomaliesEndDate.setHours(23, 59, 59, 999);

    this.anomaliesStartDate = new Date();
    this.anomaliesStartDate.setDate(this.anomaliesStartDate.getDate() - 60);
    this.anomaliesStartDate.setHours(0, 0, 0, 0);

    this.myControl.valueChanges.pipe(
      startWith(''),
      debounceTime(250),
      map((value) => (typeof value === 'string' ? value : value?.name || '')),
      distinctUntilChanged(),
      switchMap((searchText) => this.fetchTenantDevices(searchText)),
      takeUntil(this.destroy$)
    ).subscribe((devices) => {
      this.devicesList = devices;
      this.devicesSubject.next(devices);
      this.isDevicesPrefetched = true;

      const currentValue = this.myControl.value;
      const exactDevice = this.findDeviceByName(currentValue);
      if (exactDevice && typeof currentValue === 'string') {
        this.myControl.setValue(exactDevice);
      }

      if (this.isEditMode && this.editingForecast && !this.selectedDevice) {
        this.populateFormForEdit();
      }
    });

    this.myControl.valueChanges.pipe(takeUntil(this.destroy$)).subscribe((device) => {
      const selectedDevice = typeof device === 'object' ? device : this.findDeviceByName(device);
      const didDeviceChange = selectedDevice?.id?.id !== this.selectedDevice?.id?.id;

      if (!this.isEditMode && didDeviceChange) {
        this.fields = [];
      }

      this.selectedDevice = selectedDevice || null;
      this.noTelemetryMessage = null;

      if (this.selectedDevice && didDeviceChange) {
        this.onDeviceSelected(this.selectedDevice);
      }
    });
  }

  onDeviceInputFocus(): void {
    if (this.isEditMode) { return; }
    if (!this.isDevicesPrefetched) {
      this.loadTenantDevices();
    }
  }

  onDeviceComplete(event: any): void {
    if (this.isEditMode) { return; }
    const query = event.query || '';
    if (!this.isDevicesPrefetched) {
      this.loadTenantDevices(query, true);
    } else {
      this.filteredDevices = this.devicesList.filter(d =>
        d.name.toLowerCase().includes(query.toLowerCase())
      );
    }
  }

  onDeviceSelected(selectedDevice: DeviceInfo): void {
    this.selectedDevice = selectedDevice;

    this.attributeService
      .getEntityTimeseriesLatest({
        entityType: EntityType.DEVICE,
        id: selectedDevice.id.id,
      })
      .subscribe(
        (telemetryData) => {
          const telemetryKeys = Object.keys(telemetryData);
          this.availableTelemetry = telemetryKeys;
          if (telemetryKeys.length === 0) {
            this.noTelemetryMessage =
              'No time-series keys (ts_kv) found for this device. Please ensure the device has telemetry data in the database.';
          } else {
            this.noTelemetryMessage = null;
          }
        },
        (error) => {
          console.error('Error fetching telemetry data:', error);
          this.noTelemetryMessage = 'Error loading telemetry keys from database.';
        }
      );
  }

  private loadTenantDevices(searchText = '', openPanel = false): void {
    this.fetchTenantDevices(searchText).pipe(takeUntil(this.destroy$)).subscribe((devices) => {
      this.devicesList = devices;
      this.devicesSubject.next(devices);
      this.isDevicesPrefetched = true;
      this.filteredDevices = devices;

      if (this.isEditMode && this.editingForecast && !this.selectedDevice) {
        this.populateFormForEdit();
      }
    });
  }

  private fetchTenantDevices(searchText = ''): Observable<DeviceInfo[]> {
    this.isLoadingDevices = true;

    const pageLink = new PageLink(this.deviceSearchPageSize, 0, searchText || null, {
      property: 'name',
      direction: Direction.ASC,
    });

    return this.deviceService.getTenantDeviceInfos(pageLink).pipe(
      map((pageData) => pageData.data || []),
      catchError((error) => {
        console.error('Error fetching devices:', error);
        return of([]);
      }),
      map((devices) => {
        this.isLoadingDevices = false;
        return devices;
      })
    );
  }

  private findDeviceByName(value: string | DeviceInfo | null): DeviceInfo | null {
    if (!value || typeof value !== 'string') { return null; }
    const normalizedName = value.trim().toLowerCase();
    if (!normalizedName) { return null; }
    return this.devicesList.find((device) => device.name.toLowerCase() === normalizedName) || null;
  }

  private getEditingDeviceId(): string {
    const deviceId = this.editingForecast?.deviceId;
    return typeof deviceId === 'string' ? deviceId : deviceId?.id || '';
  }

  private createEditingDeviceFallback(): DeviceInfo | null {
    const deviceId = this.getEditingDeviceId();
    if (!deviceId) { return null; }
    return {
      id: { entityType: EntityType.DEVICE, id: deviceId },
      name: this.editingForecast?.device || deviceId,
    } as DeviceInfo;
  }

  private lockDeviceControlForEdit(): void {
    if (this.isEditMode && this.myControl.enabled) {
      this.myControl.disable({ emitEvent: false });
    }
  }

  getDeviceNamesHint(): string {
    if (this.devicesList.length === 0) { return ''; }
    const deviceNames = this.devicesList.slice(0, 3).map(device => device.name).join(', ');
    return `Hint: ${deviceNames}`;
  }

  displayFn(device: DeviceInfo): string {
    return device && device.name ? device.name : '';
  }

  get canAddField(): boolean {
    if (!this.selectedDevice) { return false; }
    if (this.availableTelemetry.length === 0) { return false; }
    return this.fields.length < this.availableTelemetry.length;
  }

  get isFormValid(): boolean {
    const isForecastDateRangeValid =
      this.globalStartDate != null &&
      this.globalEndDate != null &&
      this.globalStartDate < this.globalEndDate;

    const isAnomaliesDateRangeValid =
      this.anomaliesStartDate != null &&
      this.anomaliesEndDate != null &&
      this.anomaliesStartDate < this.anomaliesEndDate;

    const areAttributesValid =
      this.fields.length === 0 ||
      this.fields.every(
        (field) =>
          field.key &&
          field.key.trim() !== '' &&
          this.availableTelemetry.includes(field.key)
      );

    return (
      this.forecastNameControl.valid &&
      this.selectedDevice != null &&
      isForecastDateRangeValid &&
      isAnomaliesDateRangeValid &&
      this.forecastAlgorithmControl.valid &&
      this.anomaliesAlgorithmControl.valid &&
      areAttributesValid
    );
  }

  isCurrentStepValid(): boolean {
    switch (this.currentStep) {
      case 1:
        return this.forecastNameControl.valid && this.selectedDevice != null;
      case 2:
        const areAttributesValid =
          this.fields.length === 0 ||
          this.fields.every(
            (field) =>
              field.key &&
              field.key.trim() !== '' &&
              this.availableTelemetry.includes(field.key)
          );
        return areAttributesValid;
      case 3:
        const isForecastDateRangeValid =
          this.globalStartDate != null &&
          this.globalEndDate != null &&
          this.globalStartDate < this.globalEndDate;
        const isAnomaliesDateRangeValid =
          this.anomaliesStartDate != null &&
          this.anomaliesEndDate != null &&
          this.anomaliesStartDate < this.anomaliesEndDate;
        return (
          isForecastDateRangeValid &&
          isAnomaliesDateRangeValid &&
          this.forecastAlgorithmControl.valid &&
          this.anomaliesAlgorithmControl.valid
        );
      default:
        return false;
    }
  }

  nextStep(): void {
    if (this.currentStep < this.totalSteps && this.isCurrentStepValid()) {
      this.currentStep++;
    }
  }

  previousStep(): void {
    if (this.currentStep > 1) {
      this.currentStep--;
    }
  }

  addField(): void {
    if (this.canAddField) {
      this.fields.push({
        key: '',
        startDate: null,
        endDate: null,
        aggregation: 'average',
        groupByMs: 5000,
      });
    }
  }

  getFilteredTelemetry(index: number): { label: string; value: string }[] {
    return this.availableTelemetry
      .filter(telemetry => !this.fields.some((field, i) => field.key === telemetry && i !== index))
      .map(telemetry => ({ label: telemetry, value: telemetry }));
  }

  getAggregationLabel(value: string): string {
    return this.aggregationOptions.find(o => o.value === value)?.label || value;
  }

  getGroupByLabel(value: number): string {
    return this.groupByOptions.find(o => o.value === value)?.label || `${value}ms`;
  }

  removeField(index: number): void {
    this.fields.splice(index, 1);
    delete this.customTimeFields[index];
  }

  isCustomTime(index: number): boolean {
    return this.customTimeFields[index] !== undefined;
  }

  toggleCustomTime(index: number): void {
    if (this.isCustomTime(index)) {
      const currentMs = this.fields[index].groupByMs;
      const matchingPreset = this.groupByOptions.find(opt => opt.value === currentMs);
      if (!matchingPreset) {
        this.fields[index].groupByMs = 3600000;
      }
      delete this.customTimeFields[index];
    } else {
      const currentMs = this.fields[index].groupByMs || 3600000;
      const hours = Math.floor(currentMs / 3600000);
      const minutes = Math.floor((currentMs % 3600000) / 60000);
      const seconds = Math.floor((currentMs % 60000) / 1000);
      this.customTimeFields[index] = { hours, minutes, seconds };
    }
  }

  updateCustomTime(index: number): void {
    const custom = this.customTimeFields[index];
    if (custom) {
      const hours = Math.max(0, Math.min(23, custom.hours || 0));
      const minutes = Math.max(0, Math.min(59, custom.minutes || 0));
      const seconds = Math.max(0, Math.min(59, custom.seconds || 0));
      this.customTimeFields[index] = { hours, minutes, seconds };
      this.fields[index].groupByMs =
        (hours * 3600000) + (minutes * 60000) + (seconds * 1000);
    }
  }

  onCancel(): void {
    this.dialogRef.close();
  }

  private hasSignificantChanges(): boolean {
    if (!this.isEditMode) { return false; }

    let currentAttributes: string[] = [];
    if (this.availableTelemetry && this.availableTelemetry.length > 0) {
      currentAttributes = this.availableTelemetry.sort();
    } else {
      currentAttributes = this.fields
        .filter((field) => field.key && field.key.trim() !== '')
        .map((el) => el.key)
        .sort();
    }

    const attributesChanged = JSON.stringify(this.originalAttributes.sort()) !== JSON.stringify(currentAttributes);
    const forecastAlgorithmChanged = this.originalForecastAlgorithm !== this.forecastAlgorithmControl.value;
    const anomalyAlgorithmChanged = this.originalAnomalyAlgorithm !== this.anomaliesAlgorithmControl.value;

    return attributesChanged || forecastAlgorithmChanged || anomalyAlgorithmChanged;
  }

  onConfirm(): void {
    if (!this.isFormValid) { return; }
    const deviceId = this.selectedDevice.id;

    const attributes: { key: string; aggregation: string; groupByMs: number }[] = this.fields
      .filter((field) => field.key && field.key.trim() !== '')
      .map((el) => ({
        key: el.key,
        aggregation: el.aggregation || 'average',
        groupByMs: el.groupByMs || 5000,
      }));

    const forecastData: ForecastCreate = {
      name: this.forecastNameControl.value,
      deviceId,
      attributes,
      forecastAlgorithm: this.forecastAlgorithmControl.value,
      additionalData: JSON.stringify({}),
      anomalyAlgorithm: this.anomaliesAlgorithmControl.value,
      forecastStartDate: this.globalStartDate.getTime(),
      forecastEndDate: this.globalEndDate.getTime(),
      anomalyStartDate: this.anomaliesStartDate.getTime(),
      anomalyEndDate: this.anomaliesEndDate.getTime(),
    };

    if (this.isEditMode) {
      (forecastData as Forecast).id = this.editingForecast.id;
      // @ts-ignore
      (forecastData as Forecast).trueId = this.editingForecast.trueId;
    }

    if (this.isEditMode) {
      const needsRebuild = this.hasSignificantChanges();
      this.dialogRef.close({ forecastData, needsRebuild });
    } else {
      this.dialogRef.close(forecastData);
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  private populateFormForEdit(): void {
    if (!this.editingForecast) { return; }

    this.forecastNameControl.setValue(this.editingForecast.modelName || '');

    let selectedDevice: DeviceInfo | null = null;

    if (this.editingForecast.device) {
      selectedDevice = this.devicesList.find(
        (d) => d.name === this.editingForecast.device
      );
    }

    if (!selectedDevice && this.editingForecast.deviceId) {
      const deviceId = this.getEditingDeviceId();
      selectedDevice = this.devicesList.find((d) => d.id.id === deviceId);
    }

    if (!selectedDevice) {
      selectedDevice = this.createEditingDeviceFallback();
    }

    if (selectedDevice) {
      this.selectedDevice = selectedDevice;
      this.myControl.setValue(selectedDevice, { emitEvent: false });
      this.lockDeviceControlForEdit();
      this.onDeviceSelected(selectedDevice);
    }

    if (this.editingForecast.attributesText) {
      const attributeKeys = this.editingForecast.attributesText
        .split(', ')
        .filter((key) => key.trim());
      this.fields = attributeKeys.map((key) => {
        return {
          key: key.trim(),
          startDate: null,
          endDate: null,
          aggregation: 'average',
          groupByMs: 3600000,
        };
      });
      this.originalAttributes = attributeKeys.map((key) => key.trim());
    } else if (
      this.editingForecast.attributes &&
      Array.isArray(this.editingForecast.attributes)
    ) {
      this.fields = this.editingForecast.attributes.map((attr: any, index: number) => {
        const groupByMs = attr.groupByMs || 3600000;
        const isPresetOption = this.groupByOptions.some(opt => opt.value === groupByMs && opt.value !== -1);
        const fieldData = {
          key: attr.key || attr,
          startDate: null,
          endDate: null,
          aggregation: attr.aggregation || 'average',
          groupByMs,
        };
        if (!isPresetOption) {
          const hours = Math.floor(groupByMs / 3600000);
          const minutes = Math.floor((groupByMs % 3600000) / 60000);
          const seconds = Math.floor((groupByMs % 60000) / 1000);
          this.customTimeFields[index] = { hours, minutes, seconds };
        }
        return fieldData;
      });
      this.originalAttributes = this.editingForecast.attributes.map((attr: any) => attr.key || attr);
    }

    if (this.editingForecast.forecastStartDate) {
      this.globalStartDate = new Date(this.editingForecast.forecastStartDate);
    }
    if (this.editingForecast.forecastEndDate) {
      this.globalEndDate = new Date(this.editingForecast.forecastEndDate);
    }
    if (this.editingForecast.anomalyStartDate || this.editingForecast.anomaliesStartDate) {
      this.anomaliesStartDate = new Date(
        this.editingForecast.anomalyStartDate || this.editingForecast.anomaliesStartDate
      );
    }
    if (this.editingForecast.anomalyEndDate || this.editingForecast.anomaliesEndDate) {
      this.anomaliesEndDate = new Date(
        this.editingForecast.anomalyEndDate || this.editingForecast.anomaliesEndDate
      );
    }

    setTimeout(() => {
      if (this.editingForecast.forecastAlgorithm) {
        this.forecastAlgorithmControl.setValue(this.editingForecast.forecastAlgorithm);
        this.originalForecastAlgorithm = this.editingForecast.forecastAlgorithm;
      }

      const anomalyAlg =
        this.editingForecast.anomalyAlgorithm ||
        this.editingForecast.anomaliesAlgorithm;
      if (anomalyAlg) {
        this.anomaliesAlgorithmControl.setValue(anomalyAlg);
        this.originalAnomalyAlgorithm = anomalyAlg;
      }
    }, 100);
  }
}
