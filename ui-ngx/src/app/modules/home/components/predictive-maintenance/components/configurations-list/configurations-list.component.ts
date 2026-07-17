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

import { CommonModule } from '@angular/common';
import { Component, OnInit, ViewChild, ElementRef } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatDialog } from '@angular/material/dialog';
import { Router } from '@angular/router';
import type { PdmSeedMachineRequest, PdmSeedMachineResult } from '@app/core/api-client';
import { PredictiveModelsService } from '@app/core/http/forecast.service';
import { DeviceService } from '@app/core/public-api';
import { Direction, PageLink, TemplateAutocompleteComponent } from '@app/shared/public-api';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { AddModelDialogComponent } from '../model/add-model-dialog/add-model-dialog.component';
import { ModelSelectionDialogComponent } from '@app/modules/home/pages/predictive-maintenance/model/model-selection-dialog/model-selection-dialog.component';
import { SeedMachineDialogComponent } from '@app/modules/home/pages/predictive-maintenance/model/seed-machine-dialog/seed-machine-dialog.component';
import { SeedMachineResultDialogComponent } from '@app/modules/home/pages/predictive-maintenance/model/seed-machine-result-dialog/seed-machine-result-dialog.component';
import { HttpClient } from '@angular/common/http';
import { ModelWebSocketService, EModelType } from '@app/core/http/model-websocket.service';
import { SelectionModel } from '@angular/cdk/collections';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { ToolbarModule } from 'primeng/toolbar';
import { MenuModule } from 'primeng/menu';
import { TooltipModule } from 'primeng/tooltip';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { ConfirmationService } from 'primeng/api';
import { IconFieldModule } from 'primeng/iconfield';
import { InputIconModule } from 'primeng/inputicon';
import { TagModule } from 'primeng/tag';
import { MenuItem } from 'primeng/api';

export interface Configuration {
  id: string;
  name: string;
  deviceId: string;
  deviceName: string;
  deviceLabel: string;
  deviceType: string;
  createdTime: number;
  forecastAlgorithm: string;
  anomalyAlgorithm: string;
}

@Component({
  selector: 'tb-configurations-list',
  templateUrl: './configurations-list.component.html',
  styleUrls: ['./configurations-list.component.scss'],
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    TranslateModule,
    MatSnackBarModule,
    TableModule,
    ButtonModule,
    InputTextModule,
    ToolbarModule,
    MenuModule,
    TooltipModule,
    ConfirmDialogModule,
    IconFieldModule,
    InputIconModule,
    TagModule,
  ],
  providers: [ConfirmationService],
})
export class ConfigurationsListComponent implements OnInit {
  configurations: Configuration[] = [];

  selection = new SelectionModel<Configuration>(true, []);

  textSearch = new FormControl();

  textSearchMode = false;

  selectionMode = false;

  isLoading = false;

  isSeedingMachine = false;

  totalElements = 0;

  pageSizeOptions = [10, 25, 50, 100];

  first = 0;

  rows = 10;

  addMenuItems: MenuItem[] = [];

  globalFilter = '';

  @ViewChild('searchInput') searchInputField!: ElementRef;

  constructor(
    public dialog: MatDialog,
    private forecastService: PredictiveModelsService,
    private deviceService: DeviceService,
    private translate: TranslateService,
    private router: Router,
    private httpClient: HttpClient,
    private snackBar: MatSnackBar,
    private modelWebSocketService: ModelWebSocketService,
    private confirmationService: ConfirmationService
  ) {}

  ngOnInit() {
    this.addMenuItems = [
      {
        label: 'Load Model',
        icon: 'pi pi-file-import',
        command: () => this.openLoadModelDialog()
      },
      {
        label: 'Add New Model',
        icon: 'pi pi-plus',
        command: () => this.openAddModelDialog()
      }
    ];

    this.fetchConfigurations(0, this.rows);
  }

  fetchConfigurations(pageIndex: number, pageSize: number): void {
    this.isLoading = true;

    const pageLink = new PageLink(pageSize, pageIndex, this.globalFilter || null, {
      property: 'createdTime',
      direction: Direction.DESC,
    });

    this.forecastService.getPredictiveModelsByPage(pageLink).subscribe(
      (configurationsPage) => {
        const visibleConfigs = (configurationsPage.data || []).filter((forecast: any) => {
          let hidden = false;
          try {
            if (forecast.viewPreferences) {
              const prefs = JSON.parse(forecast.viewPreferences);
              hidden = !!prefs.hidden;
            }
          } catch {}
          return !hidden;
        });

        if (visibleConfigs.length === 0) {
          this.configurations = [];
          this.totalElements = configurationsPage.totalElements;
          this.isLoading = false;
          return;
        }

        const configPromises = visibleConfigs.map((forecast: any) => new Promise<Configuration>((resolve) => {
          this.deviceService.getDevice(forecast.deviceId.id).subscribe(
            (device) => {
              resolve({
                id: forecast.id.id,
                name: forecast.name || `Model_${forecast.id.id.split('-')[0]}`,
                deviceId: forecast.deviceId.id,
                deviceName: device.name,
                deviceLabel: device.label || 'N/A',
                deviceType: device.type || 'Unknown',
                createdTime: forecast.createdTime,
                forecastAlgorithm: forecast.forecastAlgorithm || 'N/A',
                anomalyAlgorithm: forecast.anomalyAlgorithm || 'N/A',
              });
            },
            (error) => {
              console.error('Error loading device:', error);
              resolve({
                id: forecast.id.id,
                name: forecast.name || `Model_${forecast.id.id.split('-')[0]}`,
                deviceId: forecast.deviceId.id,
                deviceName: 'Unknown',
                deviceLabel: 'N/A',
                deviceType: 'Unknown',
                createdTime: forecast.createdTime,
                forecastAlgorithm: forecast.forecastAlgorithm || 'N/A',
                anomalyAlgorithm: forecast.anomalyAlgorithm || 'N/A',
              });
            }
          );
        }));

        Promise.all(configPromises).then((configurations) => {
          this.configurations = configurations;
          this.totalElements = configurationsPage.totalElements;
          this.isLoading = false;
        });
      },
      (error) => {
        console.error('Error fetching configurations:', error);
        this.isLoading = false;
      }
    );
  }

  onPageChange(event: any): void {
    this.first = event.first;
    this.rows = event.rows;
    this.fetchConfigurations(event.first / event.rows, event.rows);
  }

  viewConfiguration(config: Configuration): void {
    const pageLink = new PageLink(1000, 0, null, {
      property: 'createdTime',
      direction: Direction.DESC,
    });

    this.forecastService.getPredictiveModelsByPage(pageLink).subscribe(
      (configurationsPage) => {
        const forecastPromises = configurationsPage.data.map(
          (forecast: any) => new Promise<any>((resolve) => {
            this.deviceService.getDevice(forecast.deviceId.id).subscribe(
              (device) => {
                resolve({
                  trueId: forecast.id.id,
                  id: forecast.name || `Model_${forecast.id.id.split('-')[0]}`,
                  device: device.name,
                  date: new Date(forecast.createdTime).toLocaleDateString(),
                });
              },
              (error) => {
                console.error('Error loading device:', error);
                resolve({
                  trueId: forecast.id.id,
                  id: forecast.name || `Model_${forecast.id.id.split('-')[0]}`,
                  device: forecast.deviceId.id,
                  date: new Date(forecast.createdTime).toLocaleDateString(),
                });
              }
            );
          })
        );

        Promise.all(forecastPromises).then((forecastData) => {
          this.router.navigate(['/predictive-maintenance/model', config.id], {
            state: { forecastData },
          });
        });
      },
      (error) => {
        console.error('Error fetching forecasts for navigation:', error);
        this.router.navigate(['/predictive-maintenance/model', config.id]);
      }
    );
  }

  onGlobalFilter(event: Event): void {
    const filterValue = (event.target as HTMLInputElement).value;
    this.globalFilter = filterValue;
    this.first = 0;
    this.fetchConfigurations(0, this.rows);
  }

  refreshConfigurations(): void {
    this.globalFilter = '';
    this.first = 0;
    this.fetchConfigurations(0, this.rows);
  }

  openAddModelDialog(): void {
    const dialogRef = this.dialog.open(AddModelDialogComponent, {
      width: '600px',
    });

    dialogRef.afterClosed().subscribe((result) => {
      if (result) {
        this.addConfiguration(result);
      }
    });
  }

  openSeedMachineDialog(): void {
    this.forecastService.getSeedMachineOptions().subscribe(
      (options) => {
        const dialogRef = this.dialog.open(SeedMachineDialogComponent, {
          width: '680px',
          data: options,
        });

        dialogRef.afterClosed().subscribe((request?: PdmSeedMachineRequest) => {
          if (!request) { return; }
          this.isSeedingMachine = true;
          this.forecastService.seedMachine(request).subscribe(
            (response) => {
              this.isSeedingMachine = false;
              this.openSeedMachineResultDialog(response);
              this.snackBar.open(
                `Seeded ${response.devicesReady} machine with ${response.telemetryPoints} points`,
                undefined,
                { duration: 4000 }
              );
              this.refreshConfigurations();
            },
            (error) => {
              this.isSeedingMachine = false;
              console.error('Error seeding machine:', error);
              this.snackBar.open(
                error?.error?.message || error?.message || 'Unable to seed machine',
                undefined,
                { duration: 5000 }
              );
            }
          );
        });
      },
      (error) => {
        console.error('Error loading seed options:', error);
        this.snackBar.open('Unable to load seed options', undefined, { duration: 5000 });
      }
    );
  }

  private openSeedMachineResultDialog(result: PdmSeedMachineResult): void {
    this.dialog.open(SeedMachineResultDialogComponent, {
      width: '640px',
      data: result,
    });
  }

  openLoadModelDialog(): void {
    try {
      const templates$ = this.forecastService.getLoadModelConfigs();
      const pageLink = new PageLink(1000, 0, null, { property: 'createdTime', direction: Direction.DESC });
      const dbConfigs$ = this.forecastService.getPredictiveModelsByPage(pageLink);

      Promise.all([
        templates$.toPromise(),
        dbConfigs$.toPromise()
      ]).then(([templatesData, dbConfigs]) => {
        const templateKeys = templatesData ? Object.keys(templatesData) : [];
        const templateModels = templateKeys.map((key) => {
          const template = templatesData[key];
          return {
            trueId: key,
            id: key,
            device: template.deviceName || 'Unknown Device',
            date: new Date(template.savedAt).toLocaleDateString(),
            status: 'Template',
            source: 'template'
          };
        });

        const dbModels = (dbConfigs?.data || []).filter((cfg: any) => {
          let hidden = false;
          try {
            if (cfg.viewPreferences) {
              const prefs = JSON.parse(cfg.viewPreferences);
              hidden = !!prefs.hidden;
            }
          } catch {}
          return hidden;
        }).map((cfg: any) => ({
          trueId: cfg.id.id,
          id: cfg.name || `Model_${cfg.id.id.split('-')[0]}`,
          device: cfg.deviceId?.id || 'Unknown Device',
          date: new Date(cfg.createdTime).toLocaleDateString(),
          status: 'Hidden',
          source: 'db',
          dbId: cfg.id.id
        }));

        const models = dbModels;
        if (models.length === 0) {
          alert('No hidden models found.');
          return;
        }

        const panelClass = typeof document !== 'undefined' && document.body.classList.contains('tb-dark') ? 'tb-dark' : undefined;
        const dialogRef = this.dialog.open(ModelSelectionDialogComponent, {
          width: '600px',
          data: {
            models,
            currentModelId: null,
            getModelDisplayName: (m: any) => m.id,
          },
          ...(panelClass ? { panelClass } : {}),
        });

        dialogRef.afterClosed().subscribe((selectedModel: any) => {
          if (selectedModel && selectedModel.source === 'db' && selectedModel.dbId) {
            this.router.navigate(['/predictive-maintenance/model', selectedModel.dbId]);
          }
        });
      }).catch((e) => {
        console.error('Error loading models:', e);
        alert('Failed to load model templates or hidden models');
      });
    } catch (e) {
      console.error('Error loading templates from localStorage:', e);
      alert('Failed to load model templates');
    }
  }

  loadAndCreateModel(template: any): void {
    try {
      if (!template) { alert('Template not found'); return; }
      const payload = template.config;
      payload.name = payload.name.replace('_template', '') + `_${Date.now()}`;
      this.addConfiguration(payload);
    } catch (e) {
      console.error('Error loading template:', e);
      alert('Failed to load template');
    }
  }

  addConfiguration(config: any): void {
    if (!config.viewPreferences) {
      config.viewPreferences = JSON.stringify({ hidden: false });
    } else {
      try {
        const prefs = typeof config.viewPreferences === 'string' ? JSON.parse(config.viewPreferences) : config.viewPreferences;
        prefs.hidden = false;
        config.viewPreferences = JSON.stringify(prefs);
      } catch {
        config.viewPreferences = JSON.stringify({ hidden: false });
      }
    }

    this.forecastService.addPredictiveModelConfig(config).subscribe(
      () => {
        setTimeout(() => { this.refreshConfigurations(); }, 500);
      },
      (error) => { console.error('Error adding configuration:', error); }
    );
  }

  deleteConfiguration(config: Configuration): void {
    this.confirmationService.confirm({
      message: `Are you sure you want to delete model "${config.name}"?`,
      header: 'Confirm Delete',
      icon: 'pi pi-exclamation-triangle',
      acceptLabel: 'Delete',
      rejectLabel: 'Cancel',
      acceptButtonStyleClass: 'p-button-danger',
      accept: () => {
        this.forecastService.deletePredictiveModel(config.id).subscribe(
          () => { setTimeout(() => { this.refreshConfigurations(); }, 500); },
          (error) => {
            console.error('Error deleting configuration:', error);
            this.snackBar.open('Failed to delete model.', undefined, { duration: 3000 });
          }
        );
      }
    });
  }

  onRowSelect(row: Configuration): void {
    this.selection.toggle(row);
    this.selectionMode = this.selection.hasValue();
  }

  toggleAllRows(): void {
    if (this.isAllSelected()) {
      this.selection.clear();
    } else {
      this.selection.select(...this.configurations);
    }
    this.selectionMode = this.selection.hasValue();
  }

  exitSelectionMode(): void {
    this.selection.clear();
    this.selectionMode = false;
  }

  deleteSelected(): void {
    const selectedCount = this.selection.selected.length;
    if (selectedCount === 0) { return; }

    this.confirmationService.confirm({
      message: selectedCount === 1
        ? 'Are you sure you want to delete the selected model?'
        : `Are you sure you want to delete ${selectedCount} selected models?`,
      header: 'Confirm Delete',
      icon: 'pi pi-exclamation-triangle',
      acceptLabel: 'Delete',
      rejectLabel: 'Cancel',
      acceptButtonStyleClass: 'p-button-danger',
      accept: () => {
        const deletePromises = this.selection.selected.map(config =>
          this.forecastService.deletePredictiveModel(config.id).toPromise()
        );
        Promise.all(deletePromises)
          .then(() => {
            this.exitSelectionMode();
            setTimeout(() => { this.refreshConfigurations(); }, 500);
          })
          .catch((error) => {
            console.error('Error deleting configurations:', error);
            this.snackBar.open('Failed to delete some models.', undefined, { duration: 3000 });
          });
      }
    });
  }

  pauseConfig(config: Configuration): void {
    if (!this.modelWebSocketService.isConnected()) { this.modelWebSocketService.connect(); }
    this.modelWebSocketService.pauseJob(config.id, EModelType.Forecast);
    this.modelWebSocketService.pauseJob(config.id, EModelType.Anomaly);
    this.snackBar.open(`Paused inference for "${config.name}"`, undefined, { duration: 3000 });
  }

  unpauseConfig(config: Configuration): void {
    if (!this.modelWebSocketService.isConnected()) { this.modelWebSocketService.connect(); }
    this.modelWebSocketService.unpauseJob(config.id, EModelType.Forecast);
    this.modelWebSocketService.unpauseJob(config.id, EModelType.Anomaly);
    this.snackBar.open(`Resumed inference for "${config.name}"`, undefined, { duration: 3000 });
  }

  pauseAllSelected(): void {
    const selected = this.selection.selected;
    if (selected.length === 0) { return; }
    if (!this.modelWebSocketService.isConnected()) { this.modelWebSocketService.connect(); }
    selected.forEach(config => {
      this.modelWebSocketService.pauseJob(config.id, EModelType.Forecast);
      this.modelWebSocketService.pauseJob(config.id, EModelType.Anomaly);
    });
    this.snackBar.open(`Paused inference for ${selected.length} model(s)`, undefined, { duration: 3000 });
  }

  unpauseAllSelected(): void {
    const selected = this.selection.selected;
    if (selected.length === 0) { return; }
    if (!this.modelWebSocketService.isConnected()) { this.modelWebSocketService.connect(); }
    selected.forEach(config => {
      this.modelWebSocketService.unpauseJob(config.id, EModelType.Forecast);
      this.modelWebSocketService.unpauseJob(config.id, EModelType.Anomaly);
    });
    this.snackBar.open(`Resumed inference for ${selected.length} model(s)`, undefined, { duration: 3000 });
  }

  isAllSelected(): boolean {
    return this.selection.selected.length === this.configurations.length;
  }

  checkboxLabel(row?: Configuration): string {
    if (!row) {
      return `${this.isAllSelected() ? 'deselect' : 'select'} all`;
    }
    return `${this.selection.isSelected(row) ? 'deselect' : 'select'} row ${row.name}`;
  }
}
