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

import { Component, Inject, OnDestroy, OnInit, ViewChild } from '@angular/core';
import {
  FormControl,
  FormsModule,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { AttributeService, DeviceService } from '@app/core/public-api';
import { DevicesDataSource } from '@app/modules/home/models/datasource/device-datasource';
import { DeviceInfo } from '@shared/models/device.models';
import { PageLink } from '@shared/models/page/page-link';
import { Observable, of, Subject } from 'rxjs';
import { AvailableModelsResponse, PredictiveModelsService } from '@app/core/http/forecast.service';
import { map, startWith, takeUntil } from 'rxjs/operators';

// Import necessary Angular Material modules
import { CommonModule } from '@angular/common';
import { MatAutocompleteModule, MatAutocompleteTrigger } from '@angular/material/autocomplete';
import { MatButtonModule } from '@angular/material/button';
import { MatNativeDateModule } from '@angular/material/core';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import {
  MatDatetimepickerModule,
  MatNativeDatetimeModule,
} from '@mat-datetimepicker/core';
import { Direction, EntityType } from '@app/shared/public-api';
import { ForecastField } from '@app/modules/home/models/predictive-maintenance.models';
import { Forecast, ForecastCreate } from '@app/shared/models/forecast.models';
import { startCase } from 'lodash';

@Component({
  selector: 'app-add-model-dialog',
  templateUrl: './add-model-dialog.component.html',
  styleUrls: ['./add-model-dialog.component.scss'],
  standalone: true,
  imports: [
    CommonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatIconModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatDatetimepickerModule,
    MatNativeDatetimeModule,
    FormsModule,
    ReactiveFormsModule, // For reactive form
    MatAutocompleteModule, // For autocomplete
  ],
})
export class AddModelDialogComponent implements OnInit, OnDestroy {
  private destroy$ = new Subject<void>();

  devicesDataSource: DevicesDataSource;

  selectedDevice: DeviceInfo | null = null;

  fields: ForecastField[] = []; // Array for field type, start, and end dates

  availableTelemetry: string[] = []; // Available telemetry keys as an observable

  myControl = new FormControl<string | DeviceInfo>('', Validators.required); // Control for autocomplete

  forecastNameControl = new FormControl('', Validators.required);

  filteredDevices: Observable<DeviceInfo[]>; // For filtered options in autocomplete

  devicesList: DeviceInfo[] = []; // To store the fetched devices

  noTelemetryMessage: string | null = null; // Message to show if no telemetry is available

  isDevicesPrefetched = false; // Track if devices have been prefetched

  @ViewChild(MatAutocompleteTrigger, { static: false }) autocompleteTrigger: MatAutocompleteTrigger;

  // Add mode vs edit mode
  isEditMode = false;

  editingForecast: any = null;

  // Track original values for change detection in edit mode
  originalAttributes: string[] = [];

  originalForecastAlgorithm = '';

  originalAnomalyAlgorithm = '';

  // Step navigation properties
  currentStep = 1;

  totalSteps = 3;

  // Global date range properties (renamed for forecast)
  globalStartDate: Date | null = null;

  globalEndDate: Date | null = null;

  // Anomalies date range properties
  anomaliesStartDate: Date | null = null;

  anomaliesEndDate: Date | null = null;

  // Algorithm form controls
  forecastAlgorithmControl = new FormControl('', Validators.required);

  anomaliesAlgorithmControl = new FormControl('', Validators.required);

  // Aggregation options for per-sensor data aggregation
  aggregationOptions = [
    { value: 'average', label: 'Average' },
    { value: 'min', label: 'Minimum' },
    { value: 'max', label: 'Maximum' },
  ];

  // Group by interval options (in milliseconds)
  groupByOptions = [
    { value: 5000, label: '5 Seconds' },           // 5 sec
    { value: 30000, label: '30 Seconds' },         // 30 sec
    { value: 60000, label: '1 Minute' },           // 1 min
    { value: 300000, label: '5 Minutes' },         // 5 min
    { value: 900000, label: '15 Minutes' },        // 15 min
    { value: 1800000, label: '30 Minutes' },       // 30 min
    { value: 3600000, label: '1 Hour' },           // 1 hr (default)
    { value: 7200000, label: '2 Hours' },          // 2 hr
    { value: 21600000, label: '6 Hours' },         // 6 hr
    { value: 43200000, label: '12 Hours' },        // 12 hr
    { value: 86400000, label: '24 Hours' },        // 24 hr
  ];

  // Track which fields are using custom time input
  customTimeFields: { [key: number]: { hours: number; minutes: number; seconds: number } } = {};

  // Algorithm options
  forecastAlgorithmOptions: { value: string; label: string }[] = [];

  anomaliesAlgorithmOptions: { value: string; label: string }[] = [];

  constructor(
    public dialogRef: MatDialogRef<AddModelDialogComponent, any>,
    @Inject(MAT_DIALOG_DATA) public data: any,
    private deviceService: DeviceService,
    private attributeService: AttributeService,
    private predictiveModelsService: PredictiveModelsService
  ) {
    this.devicesDataSource = new DevicesDataSource(this.deviceService);

    // Check if we're in edit mode
    if (data && data.isEdit) {
      this.isEditMode = true;
      this.editingForecast = data.forecastData;

      // Add CSS class for edit mode styling
      setTimeout(() => {
        const dialogContainer = document.querySelector(
          '.mat-mdc-dialog-container'
        );
        if (dialogContainer) {
          dialogContainer.classList.add('edit-mode');
        }
      }, 0);
    }
  }

  ngOnInit(): void {
    // Fetch available models from backend
    this.predictiveModelsService.getAvailableModels().subscribe((res: AvailableModelsResponse) => {
      // ForecastModel
      if (res.ForecastModel && Array.isArray(res.ForecastModel)) {
        this.forecastAlgorithmOptions = res.ForecastModel.map((item: any) => ({
          value: item.model_name,
          label: startCase(item.model_name)
        }));
      }
      // AnomalyPredictor
      if (res.AnomalyPredictor && Array.isArray(res.AnomalyPredictor)) {
        this.anomaliesAlgorithmOptions = res.AnomalyPredictor.map((item: any) => ({
          value: item.model_name,
          label: startCase(item.model_name)
        }));
      }
    });
    // Initialize forecast dates with default values (last 30 days) and set specific times
    this.globalEndDate = new Date();
    this.globalEndDate.setHours(23, 59, 59, 999); // Set to end of day

    this.globalStartDate = new Date();
    this.globalStartDate.setDate(this.globalStartDate.getDate() - 30);
    this.globalStartDate.setHours(0, 0, 0, 0); // Set to start of day

    // Initialize anomalies dates with default values (last 60 days) and set specific times
    this.anomaliesEndDate = new Date();
    this.anomaliesEndDate.setHours(23, 59, 59, 999); // Set to end of day

    this.anomaliesStartDate = new Date();
    this.anomaliesStartDate.setDate(this.anomaliesStartDate.getDate() - 60);
    this.anomaliesStartDate.setHours(0, 0, 0, 0); // Set to start of day

    // Subscribe to the devices$ observable to populate devicesList
    this.devicesDataSource.devices$.subscribe((devices) => {
      this.devicesList = devices;

      // keep only devices with name like 'PdM-Machine%'
      this.devicesList = this.devicesList.filter(device => device.name && device.name.startsWith('PdM-Machine'));

      // If in edit mode, populate the form after devices are loaded
      if (this.isEditMode && this.editingForecast) {
        this.populateFormForEdit();
      }
    });

    // Load first page of devices immediately on dialog open
    this.prefetchFirstPage();

    // If in edit mode, load all devices immediately
    if (this.isEditMode) {
      this.prefetchAllDevices();
    }

    // Set up filtered devices observable based on user input
    this.filteredDevices = this.myControl.valueChanges.pipe(
      startWith(''),
      map((value) => (typeof value === 'string' ? value : value?.name)),
      map((name) =>
        name ? this._filterDevices(name) : this.devicesList.slice()
      )
    );

    // Clear fields when device changes (only in add mode)
    this.myControl.valueChanges.subscribe((device) => {
      if (!this.isEditMode) {
        this.fields = []; // Clear fields when a new device is selected
      }
      this.selectedDevice = typeof device === 'object' ? device : null;
      this.noTelemetryMessage = null; // Reset the message
      if (this.selectedDevice && !this.isEditMode) {
        this.onDeviceSelected(this.selectedDevice);
      }
    });
  }

  // Prefetch first page of devices when input is focused
  onDeviceInputFocus(): void {
    console.log('Device input focused, prefetched:', this.isDevicesPrefetched);
    // Don't auto-open in edit mode
    if (!this.isDevicesPrefetched && !this.isEditMode) {
      this.prefetchFirstPage();
    }
  }

  // Handle click event to ensure autocomplete opens
  onDeviceInputClick(event: Event): void {
    console.log('Device input clicked');
    // In edit mode, don't auto-open - let user manually trigger it
    if (this.isEditMode) {
      return;
    }

    if (!this.isDevicesPrefetched) {
      this.prefetchFirstPage();
    } else {
      // If already prefetched, just open the panel
      setTimeout(() => {
        if (this.autocompleteTrigger) {
          console.log('Opening panel on click');
          this.autocompleteTrigger.openPanel();
        }
      }, 0);
    }
  }

  // Event when autocomplete is opened
  onAutocompleteOpened(): void {
    console.log('Autocomplete panel opened');
    // If not prefetched yet, fetch devices
    if (!this.isDevicesPrefetched) {
      this.prefetchFirstPage();
    }
  }

  // Handle arrow down key to prefetch and open autocomplete
  onArrowDown(event: KeyboardEvent): void {
    console.log('Arrow down pressed');
    if (!this.isDevicesPrefetched) {
      this.prefetchFirstPage();
    }
    // Don't prevent default - let autocomplete handle it naturally
  }

  // Prefetch first page of devices (10 devices)
  private prefetchFirstPage(): void {
    console.log('Prefetching first page of devices...');
    console.log('Autocomplete trigger available:', !!this.autocompleteTrigger);

    const firstPageLink = new PageLink(10, 0, null, {
      property: 'createdTime',
      direction: Direction.DESC,
    });

    this.devicesDataSource.loadDevices(firstPageLink);
    this.isDevicesPrefetched = true;

    // Don't auto-open the panel in edit mode
    if (this.isEditMode) {
      console.log('Edit mode: skipping auto-open of autocomplete panel');
      return;
    }

    // Wait for devices to load, then open panel
    const subscription = this.devicesDataSource.devices$.subscribe((devices) => {
      console.log('Devices loaded:', devices.length);
      if (devices.length > 0) {
        // Try multiple times with increasing delays to ensure trigger is available
        const attempts = [100, 200, 300];
        attempts.forEach((delay) => {
          setTimeout(() => {
            if (this.autocompleteTrigger) {
              console.log('Opening autocomplete panel (attempt at ' + delay + 'ms)');
              try {
                this.autocompleteTrigger.openPanel();
              } catch (error) {
                console.error('Error opening panel:', error);
              }
            } else {
              console.warn('Autocomplete trigger not available yet at ' + delay + 'ms');
            }
          }, delay);
        });
        subscription.unsubscribe();
      }
    });
  }

  // Prefetch all devices (used in edit mode or when user starts typing)
  private prefetchAllDevices(): void {
    // Load the first page with only one device to get the total count
    const firstPageLink = new PageLink(1, 0, null, {
      property: 'createdTime',
      direction: Direction.DESC,
    });

    // Load the first page of devices
    this.devicesDataSource.fetchTotalElements(firstPageLink);

    // Subscribe to the total number of devices once the first request completes
    this.devicesDataSource.totalElements$.pipe(
      takeUntil(this.destroy$)
    ).subscribe((totalElements) => {
      console.log('Total number of devices:', totalElements);

      // Once we know the total number of devices, fetch all of them
      const fullPageLink = new PageLink(totalElements, 0, null, {
        property: 'createdTime',
        direction: Direction.DESC,
      });

      // Fetch the full list of devices
      this.devicesDataSource.loadDevices(fullPageLink);
    });
  }

  // Function to filter devices based on user input
  private _filterDevices(name: string): DeviceInfo[] {
    const filterValue = name.toLowerCase();

    // If user starts typing and we only have first page, load all devices
    if (this.isDevicesPrefetched && !this.isEditMode && this.devicesList.length <= 10) {
      this.prefetchAllDevices();
    }

    return this.devicesList.filter((option) =>
      option.name.toLowerCase().includes(filterValue)
    );
  }

  // Get hint text showing device names
  getDeviceNamesHint(): string {
    if (this.devicesList.length === 0) {
      return '';
    }
    // take first 3 device names for hint
    const deviceNames = this.devicesList.slice(0, 3).map(device => device.name).join(', ');
    return `Hint: ${deviceNames}`;
  }

  // Display function for showing device name
  displayFn(device: DeviceInfo): string {
    return device && device.name ? device.name : '';
  }

  // When the user selects a device, fetch the telemetry for that device
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
          console.log(
            'Available telemetry (ts_kv) for the selected device:',
            telemetryKeys
          );

          // Set available telemetry keys
          this.availableTelemetry = telemetryKeys;

          // If no telemetry available, show message
          if (telemetryKeys.length === 0) {
            this.noTelemetryMessage =
              'No time-series keys (ts_kv) found for this device. Please ensure the device has telemetry data in the database.';
          } else {
            this.noTelemetryMessage = null; // Reset if telemetry is available
          }
        },
        (error) => {
          console.error('Error fetching telemetry data:', error);
          this.noTelemetryMessage =
            'Error loading telemetry keys from database.';
        }
      );
  }

  //  && this.selectedDevice != null
  get canAddField(): boolean {
    if (!this.selectedDevice) {
      return false; // Cannot add fields without a selected device
    }

    // Only allow adding fields if there are available telemetry keys
    if (this.availableTelemetry.length === 0) {
      return false; // No telemetry keys available
    }

    // Limit to available telemetry count (only allow selection from database keys)
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

    // Validate telemetry attributes - must have valid keys from database
    const areAttributesValid =
      this.fields.length === 0 ||
      this.fields.every(
        (field) =>
          field.key &&
          field.key.trim() !== '' &&
          this.availableTelemetry.includes(field.key) // Ensure selected key is from database
      );

    return (
      this.forecastNameControl.valid &&
      this.selectedDevice != null && // Ensure a device is selected
      isForecastDateRangeValid && // Ensure valid forecast date range
      isAnomaliesDateRangeValid && // Ensure valid anomalies date range
      this.forecastAlgorithmControl.valid && // Ensure forecast algorithm is selected
      this.anomaliesAlgorithmControl.valid && // Ensure anomalies algorithm is selected
      areAttributesValid // Validate attributes are from database
    );
  }

  // Step-specific validation
  isCurrentStepValid(): boolean {
    switch (this.currentStep) {
      case 1:
        // Step 1: Model name and device selection
        return (
          this.forecastNameControl.valid &&
          this.selectedDevice != null
        );
      case 2:
        // Step 2: Telemetry attributes - must be from database if present
        const areAttributesValid =
          this.fields.length === 0 ||
          this.fields.every(
            (field) =>
              field.key &&
              field.key.trim() !== '' &&
              this.availableTelemetry.includes(field.key) // Must be from database
          );

        return areAttributesValid; // Attributes are optional but must be valid database keys if present
      case 3:
        // Step 3: Algorithm and date ranges
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

  // Step navigation methods
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

  // Add a new field with telemetry autocomplete
  addField(): void {
    if (this.canAddField) {
      // Default to 5 second grouping (5000 ms)
      const groupByMs = 5000;

      this.fields.push({
        key: '',
        startDate: null,
        endDate: null,
        aggregation: 'average', // Default aggregation
        groupByMs, // Default grouping
      });
    }
  }

  // Get telemetry options excluding already selected ones
  getFilteredTelemetry(index: number): string[] {
    // Filter out telemetry keys that are already selected in other fields
    return this.availableTelemetry.filter(
      (telemetry) =>
        !this.fields.some((field, i) => field.key === telemetry && i !== index)
    );
  }

  removeField(index: number): void {
    this.fields.splice(index, 1);
    // Clean up custom time fields tracking
    delete this.customTimeFields[index];
  }

  // Check if field is using custom time
  isCustomTime(index: number): boolean {
    return this.customTimeFields[index] !== undefined;
  }

  // Toggle between preset and custom time input
  toggleCustomTime(index: number): void {
    if (this.isCustomTime(index)) {
      // Switch back to preset - use current groupByMs or default to 1 hour
      const currentMs = this.fields[index].groupByMs;
      // Check if current value matches a preset
      const matchingPreset = this.groupByOptions.find(opt => opt.value === currentMs);
      if (!matchingPreset) {
        // If no match, default to 1 hour
        this.fields[index].groupByMs = 3600000;
      }
      delete this.customTimeFields[index];
    } else {
      // Switch to custom time - initialize from current groupByMs
      const currentMs = this.fields[index].groupByMs || 3600000;
      const hours = Math.floor(currentMs / 3600000);
      const minutes = Math.floor((currentMs % 3600000) / 60000);
      const seconds = Math.floor((currentMs % 60000) / 1000);
      this.customTimeFields[index] = { hours, minutes, seconds };
    }
  }

  // Update groupByMs when custom time inputs change
  updateCustomTime(index: number): void {
    const custom = this.customTimeFields[index];
    if (custom) {
      const hours = Math.max(0, Math.min(23, custom.hours || 0));
      const minutes = Math.max(0, Math.min(59, custom.minutes || 0));
      const seconds = Math.max(0, Math.min(59, custom.seconds || 0));

      // Update the actual values to clamped values
      this.customTimeFields[index] = { hours, minutes, seconds };

      // Calculate total milliseconds
      this.fields[index].groupByMs =
        (hours * 3600000) +
        (minutes * 60000) +
        (seconds * 1000);
    }
  }

  onCancel(): void {
    this.dialogRef.close();
  }

  /**
   * Check if telemetry attributes or algorithms have changed in edit mode
   */
  private hasSignificantChanges(): boolean {
    if (!this.isEditMode) {
      return false;
    }

    // Get current attributes
    let currentAttributes: string[] = [];
    if (this.availableTelemetry && this.availableTelemetry.length > 0) {
      currentAttributes = this.availableTelemetry.sort();
    } else {
      currentAttributes = this.fields
        .filter((field) => field.key && field.key.trim() !== '')
        .map((el) => el.key)
        .sort();
    }

    // Compare attributes
    const attributesChanged = JSON.stringify(this.originalAttributes.sort()) !== JSON.stringify(currentAttributes);

    // Compare algorithms
    const forecastAlgorithmChanged = this.originalForecastAlgorithm !== this.forecastAlgorithmControl.value;
    const anomalyAlgorithmChanged = this.originalAnomalyAlgorithm !== this.anomaliesAlgorithmControl.value;

    console.log('Change detection:', {
      attributesChanged,
      forecastAlgorithmChanged,
      anomalyAlgorithmChanged,
      originalAttributes: this.originalAttributes,
      currentAttributes,
      originalForecastAlgorithm: this.originalForecastAlgorithm,
      currentForecastAlgorithm: this.forecastAlgorithmControl.value,
      originalAnomalyAlgorithm: this.originalAnomalyAlgorithm,
      currentAnomalyAlgorithm: this.anomaliesAlgorithmControl.value,
    });

    return attributesChanged || forecastAlgorithmChanged || anomalyAlgorithmChanged;
  }

  onConfirm(): void {
    if (!this.isFormValid) {
      console.log('Form is invalid. Please complete all required fields.');
      return;
    }
    const deviceId = this.selectedDevice.id;

    // Only use manually added fields (sensors) - no auto-detection
    const attributes: { key: string; aggregation: string; groupByMs: number }[] = this.fields
      .filter((field) => field.key && field.key.trim() !== '')
      .map((el) => ({
        key: el.key,
        aggregation: el.aggregation || 'average',
        groupByMs: el.groupByMs || 5000, // Use field-specific grouping or default to 5 seconds
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

    // If in edit mode, include the ID and other necessary fields
    if (this.isEditMode) {
      // Use the full ForecastId object instead of plain string UUID
      (forecastData as Forecast).id = this.editingForecast.id;
      // @ts-ignore
      (forecastData as Forecast).trueId = this.editingForecast.trueId;
    }

    // In edit mode, check if there are significant changes that require rebuild
    if (this.isEditMode) {
      const needsRebuild = this.hasSignificantChanges();
      // Return both the forecast data and rebuild flag for edit mode
      this.dialogRef.close({
        forecastData,
        needsRebuild
      });
    } else {
      // In add mode, just return the forecast data directly
      this.dialogRef.close(forecastData);
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();

    // Clean up edit-mode class if it was added
    if (this.isEditMode) {
      const dialogContainer = document.querySelector(
        '.mat-mdc-dialog-container.edit-mode'
      );
      if (dialogContainer) {
        dialogContainer.classList.remove('edit-mode');
      }
    }
  }

  private populateFormForEdit(): void {
    if (!this.editingForecast) {return;}

    console.log('Editing forecast data:', this.editingForecast);

    // Set forecast name
    this.forecastNameControl.setValue(this.editingForecast.modelName || '');

    // Find and set the device
    // Since we have device name in 'device' field, let's find by name first
    let selectedDevice: DeviceInfo | null = null;

    // Try to find by device name
    if (this.editingForecast.device) {
      selectedDevice = this.devicesList.find(
        (d) => d.name === this.editingForecast.device
      );
    }

    // If not found by name and we have a device ID, try by ID
    if (!selectedDevice && this.editingForecast.deviceId) {
      const deviceId =
        typeof this.editingForecast.deviceId === 'string'
          ? this.editingForecast.deviceId
          : this.editingForecast.deviceId.id;
      selectedDevice = this.devicesList.find((d) => d.id.id === deviceId);
    }

    // If still not found, try using the trueId (forecast ID) to match with device
    // This might not work directly, but let's try
    if (!selectedDevice && this.editingForecast.trueId) {
      // This is likely not the right approach, but let's keep it as fallback
      console.warn(
        'Could not find device by name or deviceId, forecast data:',
        this.editingForecast
      );
    }

    if (selectedDevice) {
      this.selectedDevice = selectedDevice;
      this.myControl.setValue(selectedDevice);

      // Load telemetry for the selected device
      this.onDeviceSelected(selectedDevice);
    } else {
      console.warn(
        'Device not found for editing forecast:',
        this.editingForecast
      );
    }

    // Set attributes/fields if they exist - parse from attributesText
    if (this.editingForecast.attributesText) {
      const attributeKeys = this.editingForecast.attributesText
        .split(', ')
        .filter((key) => key.trim());
      this.fields = attributeKeys.map((key, index: number) => {
        const groupByMs = 3600000; // Default to hourly for legacy models
        return {
          key: key.trim(),
          startDate: null,
          endDate: null,
          aggregation: 'average', // Default aggregation for existing models
          groupByMs, // Default to hourly
        };
      });
      // Store original attributes for change detection
      this.originalAttributes = attributeKeys.map((key) => key.trim());
    } else if (
      this.editingForecast.attributes &&
      Array.isArray(this.editingForecast.attributes)
    ) {
      this.fields = this.editingForecast.attributes.map((attr: any, index: number) => {
        const groupByMs = attr.groupByMs || 3600000;
        // Check if this groupByMs is in the preset options
        const isPresetOption = this.groupByOptions.some(opt => opt.value === groupByMs && opt.value !== -1);
        const fieldData = {
          key: attr.key || attr,
          startDate: null,
          endDate: null,
          aggregation: attr.aggregation || 'average',
          groupByMs, // Keep the actual value
        };
        if (!isPresetOption) {
          // Initialize custom time for this field
          const hours = Math.floor(groupByMs / 3600000);
          const minutes = Math.floor((groupByMs % 3600000) / 60000);
          const seconds = Math.floor((groupByMs % 60000) / 1000);
          this.customTimeFields[index] = { hours, minutes, seconds };
        }
        return fieldData;
      });
      // Store original attributes for change detection
      this.originalAttributes = this.editingForecast.attributes.map((attr: any) => attr.key || attr);
    }

    // Set forecast dates if they exist
    if (this.editingForecast.forecastStartDate) {
      this.globalStartDate = new Date(this.editingForecast.forecastStartDate);
    }
    if (this.editingForecast.forecastEndDate) {
      this.globalEndDate = new Date(this.editingForecast.forecastEndDate);
    }

    // Set anomalies dates if they exist
    if (
      this.editingForecast.anomalyStartDate ||
      this.editingForecast.anomaliesStartDate
    ) {
      this.anomaliesStartDate = new Date(
        this.editingForecast.anomalyStartDate ||
          this.editingForecast.anomaliesStartDate
      );
    }
    if (
      this.editingForecast.anomalyEndDate ||
      this.editingForecast.anomaliesEndDate
    ) {
      this.anomaliesEndDate = new Date(
        this.editingForecast.anomalyEndDate ||
          this.editingForecast.anomaliesEndDate
      );
    }

    // Set algorithms if they exist (use setTimeout to ensure form controls are ready)
    setTimeout(() => {
      console.log('Setting algorithms from edit data:', {
        forecastAlgorithm: this.editingForecast.forecastAlgorithm,
        anomalyAlgorithm:
          this.editingForecast.anomalyAlgorithm ||
          this.editingForecast.anomaliesAlgorithm,
        availableForecastOptions: this.forecastAlgorithmOptions.map(
          (opt) => opt.value
        ),
        availableAnomalyOptions: this.anomaliesAlgorithmOptions.map(
          (opt) => opt.value
        ),
      });

      if (this.editingForecast.forecastAlgorithm) {
        const forecastAlg = this.editingForecast.forecastAlgorithm;
        // Check if the algorithm exists in our options
        const forecastExists = this.forecastAlgorithmOptions.some(
          (opt) => opt.value === forecastAlg
        );
        console.log(
          `Forecast algorithm '${forecastAlg}' exists in options:`,
          forecastExists
        );

        this.forecastAlgorithmControl.setValue(forecastAlg);
        // Store original value for change detection
        this.originalForecastAlgorithm = forecastAlg;
        console.log(
          'Forecast algorithm control value after setting:',
          this.forecastAlgorithmControl.value
        );
      }

      const anomalyAlg =
        this.editingForecast.anomalyAlgorithm ||
        this.editingForecast.anomaliesAlgorithm;
      if (anomalyAlg) {
        // Check if the algorithm exists in our options
        const anomalyExists = this.anomaliesAlgorithmOptions.some(
          (opt) => opt.value === anomalyAlg
        );
        console.log(
          `Anomaly algorithm '${anomalyAlg}' exists in options:`,
          anomalyExists
        );

        this.anomaliesAlgorithmControl.setValue(anomalyAlg);
        // Store original value for change detection
        this.originalAnomalyAlgorithm = anomalyAlg;
        console.log(
          'Anomaly algorithm control value after setting:',
          this.anomaliesAlgorithmControl.value
        );
      }
    }, 100);

    console.log('Form populated for edit mode:', {
      forecastName: this.forecastNameControl.value,
      device: this.selectedDevice?.name,
      attributes: this.fields,
      forecastAlgorithm: this.forecastAlgorithmControl.value,
      anomaliesAlgorithm: this.anomaliesAlgorithmControl.value,
      forecastStartDate: this.globalStartDate,
      forecastEndDate: this.globalEndDate,
      anomaliesStartDate: this.anomaliesStartDate,
      anomaliesEndDate: this.anomaliesEndDate,
    });
  }
}
