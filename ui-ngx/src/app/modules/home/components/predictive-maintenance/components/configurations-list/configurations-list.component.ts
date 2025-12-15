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
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatMenuModule } from '@angular/material/menu';
import { MatPaginator, MatPaginatorModule } from '@angular/material/paginator';
import { MatSort, MatSortModule } from '@angular/material/sort';
import { MatTableDataSource, MatTableModule } from '@angular/material/table';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { SelectionModel } from '@angular/cdk/collections';
import { Router } from '@angular/router';
import { PredictiveModelsService } from '@app/core/http/forecast.service';
import { DeviceService } from '@app/core/public-api';
import { Direction, PageLink, TemplateAutocompleteComponent } from '@app/shared/public-api';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { FlexLayoutModule } from '@angular/flex-layout';
import { AddModelDialogComponent } from '../model/add-model-dialog/add-model-dialog.component';
import { ModelSelectionDialogComponent } from '@app/modules/home/pages/predictive-maintenance/model/model-selection-dialog/model-selection-dialog.component';
import { HttpClient } from '@angular/common/http';

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
    MatTableModule,
    MatPaginatorModule,
    MatSortModule,
    MatInputModule,
    MatIconModule,
    MatButtonModule,
    MatCardModule,
    MatTooltipModule,
    MatToolbarModule,
    MatFormFieldModule,
    MatCheckboxModule,
    TranslateModule,
    ReactiveFormsModule,
    FlexLayoutModule,
    MatMenuModule,
  ],
})
export class ConfigurationsListComponent implements OnInit {
  displayedColumns: string[] = [
    'select',
    'createdTime',
    'name',
    'deviceName',
    'deviceLabel',
    'forecastAlgorithm',
    'anomalyAlgorithm',
    'actions',
  ];

  dataSource = new MatTableDataSource<Configuration>();

  selection = new SelectionModel<Configuration>(true, []);

  textSearch = new FormControl();

  textSearchMode = false;

  selectionMode = false;

  isLoading = false;

  totalElements = 0;

  pageSizeOptions = [10, 25, 50, 100];

  @ViewChild(MatPaginator) paginator!: MatPaginator;

  @ViewChild(MatSort) sort!: MatSort;

  @ViewChild('searchInput') searchInputField!: ElementRef;

  constructor(
    public dialog: MatDialog,
    private forecastService: PredictiveModelsService,
    private deviceService: DeviceService,
    private translate: TranslateService,
    private router: Router,
    private httpClient: HttpClient
  ) {}

  ngOnInit() {}

  // eslint-disable-next-line @angular-eslint/use-lifecycle-interface
  ngAfterViewInit() {
    this.dataSource.paginator = this.paginator;
    this.dataSource.sort = this.sort;

    // Set default sort to createdTime descending
    this.sort.active = 'createdTime';
    this.sort.direction = 'desc';

    this.fetchConfigurations(
      this.paginator?.pageIndex || 0,
      this.paginator?.pageSize || 10
    );
    this.paginator?.page.subscribe(() => {
      this.fetchConfigurations(
        this.paginator.pageIndex,
        this.paginator.pageSize
      );
    });
  }

  fetchConfigurations(pageIndex: number, pageSize: number): void {
    this.isLoading = true;

    const pageLink = new PageLink(pageSize, pageIndex, null, {
      property: 'createdTime',
      direction: Direction.DESC,
    });

    // Fetch configurations directly from predictive_maintenance_config table
    this.forecastService.getPredictiveModelsByPage(pageLink).subscribe(
      (configurationsPage) => {
        console.log('Configurations API response:', configurationsPage);

        if (configurationsPage.data.length === 0) {
          this.dataSource.data = [];
          this.totalElements = configurationsPage.totalElements;
          this.isLoading = false;
          return;
        }

        // Load device details for each configuration
        const configPromises = configurationsPage.data.map((forecast: any) => new Promise<Configuration>((resolve) => {
            this.deviceService.getDevice(forecast.deviceId.id).subscribe(
              (device) => {
                resolve({
                  id: forecast.id.id,
                  name:
                    forecast.name || `Model_${forecast.id.id.split('-')[0]}`,
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
                  name:
                    forecast.name || `Model_${forecast.id.id.split('-')[0]}`,
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
          // All configs from database are active models (templates are in localStorage)
          this.dataSource.data = configurations;
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

  viewConfiguration(event: Event, config: Configuration): void {
    // Fetch all forecasts to pass as state to the model page
    const pageLink = new PageLink(1000, 0, null, {
      property: 'createdTime',
      direction: Direction.DESC,
    });

    this.forecastService.getPredictiveModelsByPage(pageLink).subscribe(
      (configurationsPage) => {
        // Load device details for each forecast to get device names
        const forecastPromises = configurationsPage.data.map(
          (forecast: any) => new Promise<any>((resolve) => {
              this.deviceService.getDevice(forecast.deviceId.id).subscribe(
                (device) => {
                  resolve({
                    trueId: forecast.id.id,
                    id:
                      forecast.name || `Model_${forecast.id.id.split('-')[0]}`,
                    device: device.name,
                    date: new Date(forecast.createdTime).toLocaleDateString(),
                  });
                },
                (error) => {
                  console.error('Error loading device:', error);
                  resolve({
                    trueId: forecast.id.id,
                    id:
                      forecast.name || `Model_${forecast.id.id.split('-')[0]}`,
                    device: forecast.deviceId.id, // Fallback to device ID
                    date: new Date(forecast.createdTime).toLocaleDateString(),
                  });
                }
              );
            })
        );

        Promise.all(forecastPromises).then((forecastData) => {
          this.router.navigate(['/predictiveMaintenance/model', config.id], {
            state: { forecastData },
          });
        });
      },
      (error) => {
        console.error('Error fetching forecasts for navigation:', error);
        // Navigate anyway without the full list
        this.router.navigate(['/predictiveMaintenance/model', config.id]);
      }
    );
  }

  applyFilter(event: Event): void {
    const filterValue = (event.target as HTMLInputElement).value;
    this.dataSource.filter = filterValue.trim().toLowerCase();

    if (this.dataSource.paginator) {
      this.dataSource.paginator.firstPage();
    }
  }

  refreshConfigurations(): void {
    this.fetchConfigurations(this.paginator.pageIndex, this.paginator.pageSize);
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

  openAddMenu(): void {
    // kept for compatibility; menu handles actions in template
  }

  openLoadModelDialog(): void {
    // Load templates from localStorage
    try {

      // fetch from /models/saveLoadConfig api endpoint
      const templates = this.forecastService.getLoadModelConfigs();
      templates.subscribe((templatesData) => {
        // const templates
        console.log('Loaded templates from localStorage:', templatesData);

      if (!templatesData) {
        alert('No saved model templatesData found. Save a model config first.');
        return;
      }

      const templateKeys = Object.keys(templatesData);

      if (templateKeys.length === 0) {
        alert('No saved model templatesData found. Save a model config first.');
        return;
      }

      // Build list from localStorage templatesData
      const models = templateKeys.map((key) => {
        const template = templatesData[key];
        return {
          trueId: key, // Use the template key as ID
          id: key,
          device: template.deviceName || 'Unknown Device',
          date: new Date(template.savedAt).toLocaleDateString(),
          status: 'Template', // Mark as template status
        };
      });

      // Preserve dark theme on overlay dialogs by applying panelClass when body has tb-dark
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
        if (selectedModel) {
          // Fetch the actual template from templatesData using the selected model's ID
          const template = templatesData[selectedModel.id];
          this.loadAndCreateModel(template);
        }
      });
      });
    } catch (e) {
      console.error('Error loading templates from localStorage:', e);
      alert('Failed to load model templates');
    }
  }

  loadAndCreateModel(template: any): void {
    try {
      if (!template) {
        alert('Template not found');
        return;
      }

      // Deep clone the config
      const payload = template.config;

      // Remove template suffix and make unique name
      payload.name = payload.name.replace('_template', '') + `_${Date.now()}`;

      // Save as a new predictive model config
      this.addConfiguration(payload);
    } catch (e) {
      console.error('Error loading template:', e);
      alert('Failed to load template');
    }
  }

  addConfiguration(config: any): void {
    this.forecastService.addPredictiveModelConfig(config).subscribe(
      () => {
        // Add a small delay to ensure backend has updated
        setTimeout(() => {
          this.refreshConfigurations();
        }, 500);
      },
      (error) => {
        console.error('Error adding configuration:', error);
      }
    );
  }

  enterFilterMode(): void {
    this.textSearchMode = true;
    setTimeout(() => {
      this.searchInputField.nativeElement.focus();
      this.searchInputField.nativeElement.setSelectionRange(0, 0);
    }, 10);
  }

  exitFilterMode(): void {
    this.textSearchMode = false;
    this.textSearch.reset();
    this.dataSource.filter = '';
  }

  deleteConfiguration(config: Configuration): void {
    if (confirm(`Are you sure you want to delete model "${config.name}"?`)) {
      this.forecastService.deletePredictiveModel(config.id).subscribe(
        () => {
          // Refresh the list after successful deletion
          setTimeout(() => {
            this.refreshConfigurations();
          }, 500);
        },
        (error) => {
          console.error('Error deleting configuration:', error);
          alert('Failed to delete model. Please try again.');
        }
      );
    }
  }

  onRowSelectionChange(event: any, row: Configuration): void {
    this.selection.toggle(row);
    this.updateSelectionMode();
  }

  updateSelectionMode(): void {
    this.selectionMode = this.selection.hasValue();
  }

  exitSelectionMode(): void {
    this.selection.clear();
    this.selectionMode = false;
  }

  deleteSelected(): void {
    const selectedCount = this.selection.selected.length;
    if (selectedCount === 0) {return;}

    const message = selectedCount === 1
      ? `Are you sure you want to delete the selected model?`
      : `Are you sure you want to delete ${selectedCount} selected models?`;

    if (confirm(message)) {
      const deletePromises = this.selection.selected.map(config =>
        this.forecastService.deletePredictiveModel(config.id).toPromise()
      );

      Promise.all(deletePromises)
        .then(() => {
          this.exitSelectionMode();
          setTimeout(() => {
            this.refreshConfigurations();
          }, 500);
        })
        .catch((error) => {
          console.error('Error deleting configurations:', error);
          alert('Failed to delete some models. Please try again.');
        });
    }
  }

  /** Whether the number of selected elements matches the total number of rows. */
  isAllSelected() {
    const numSelected = this.selection.selected.length;
    const numRows = this.dataSource.data.length;
    return numSelected === numRows;
  }

  /** Selects all rows if they are not all selected; otherwise clear selection. */
  toggleAllRows() {
    if (this.isAllSelected()) {
      this.selection.clear();
    } else {
      this.selection.select(...this.dataSource.data);
    }
    this.updateSelectionMode();
  }

  /** The label for the checkbox on the passed row */
  checkboxLabel(row?: Configuration): string {
    if (!row) {
      return `${this.isAllSelected() ? 'deselect' : 'select'} all`;
    }
    return `${this.selection.isSelected(row) ? 'deselect' : 'select'} row ${
      row.name
    }`;
  }
}
