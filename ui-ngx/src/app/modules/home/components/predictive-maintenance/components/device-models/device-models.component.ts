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
import { MatPaginator, MatPaginatorModule } from '@angular/material/paginator';
import { MatSort, MatSortModule } from '@angular/material/sort';
import { MatTableDataSource, MatTableModule } from '@angular/material/table';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { SelectionModel } from '@angular/cdk/collections';
import { ActivatedRoute, Router } from '@angular/router';
import { PredictiveModelsService } from '@app/core/http/forecast.service';
import { DeviceService, DialogService } from '@app/core/public-api';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { Order } from '@app/modules/home/models/predictive-maintenance.models';
import { AddModelDialogComponent } from '../model/add-model-dialog/add-model-dialog.component';

@Component({
  selector: 'tb-device-models',
  templateUrl: './device-models.component.html',
  styleUrls: ['./device-models.component.scss'],
  standalone: true,
  imports: [
    CommonModule,
    MatTableModule,
    MatPaginatorModule,
    MatSortModule,
    MatIconModule,
    MatButtonModule,
    MatCardModule,
    MatTooltipModule,
    MatToolbarModule,
    MatInputModule,
    MatFormFieldModule,
    MatCheckboxModule,
    TranslateModule,
    ReactiveFormsModule,
  ],
})
export class DeviceModelsComponent implements OnInit {
  displayedColumns: string[] = [
    'select',
    'createdTime',
    'deviceName',
    'deviceLabel',
    'deviceType',
    'modelName',
    'modelsCount',
    'actions',
  ];

  dataSource = new MatTableDataSource<Order>();

  selection = new SelectionModel<Order>(true, []);

  deviceId = '';

  deviceName = 'Device';

  deviceLabel = '';

  deviceType = '';

  isLoading = false;

  totalElements = 0;

  pageSizeOptions = [5, 10, 25, 50];

  textSearch = new FormControl();

  textSearchMode = false;

  @ViewChild(MatPaginator) paginator!: MatPaginator;

  @ViewChild(MatSort) sort!: MatSort;

  @ViewChild('searchInput') searchInputField!: ElementRef;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    public dialog: MatDialog,
    private forecastService: PredictiveModelsService,
    private deviceService: DeviceService,
    private translate: TranslateService,
    private dialogService: DialogService
  ) {}

  ngOnInit() {
    this.deviceId = this.route.snapshot.paramMap.get('deviceId') || '';
    if (this.deviceId) {
      this.loadDeviceInfo();
      this.loadDeviceModels();
    }
  }

  // eslint-disable-next-line @angular-eslint/use-lifecycle-interface
  ngAfterViewInit() {
    this.dataSource.paginator = this.paginator;
    this.dataSource.sort = this.sort;

    // Set default sort to createdTime descending
    this.sort.active = 'createdTime';
    this.sort.direction = 'desc';
  }

  loadDeviceInfo(): void {
    this.deviceService.getDevice(this.deviceId).subscribe(
      (device) => {
        this.deviceName = device.name;
        this.deviceLabel = device.label || '';
        this.deviceType = device.type || '';
      },
      (error) => {
        console.error('Error loading device info:', error);
      }
    );
  }

  loadDeviceModels(): void {
    this.isLoading = true;
    this.forecastService.getForecastsByDeviceId(this.deviceId).subscribe(
      (response) => {
        const models = response.data.map((forecast: any) => ({
          id: forecast.id.id.split('-')[0],
          trueId: forecast.id.id,
          device: this.deviceName,
          deviceLabel: this.deviceLabel,
          deviceType: this.deviceType,
          modelName:
            forecast.name ||
            forecast.modelName ||
            `Model_${forecast.id.id.split('-')[0]}`,
          date: new Date(forecast.createdTime).toISOString().split('T')[0],
          attributesText:
            forecast.attributes && forecast.attributes.length > 0
              ? forecast.attributes.map((attr: any) => attr.key).join(', ')
              : 'No attributes',
          forecastAlgorithm: forecast.forecastAlgorithm || 'N/A',
          anomalyAlgorithm: forecast.anomalyAlgorithm || 'N/A',
          modelsCount: 1, // Each row represents one model
        }));

        this.dataSource.data = models;
        this.totalElements = response.totalElements || models.length;
        this.isLoading = false;
      },
      (error) => {
        console.error('Error loading device models:', error);
        this.isLoading = false;
      }
    );
  }

  openModel(model: Order): void {
    this.router.navigate(['/predictive-maintenance/forecast', model.trueId]);
  }

  editForecast(event: Event, forecast: Order): void {
    if (event) {
      event.stopPropagation();
    }

    this.forecastService.getPredictiveModel(forecast.trueId).subscribe(
      (fullForecastData) => {
        const editData = {
          ...forecast,
          ...fullForecastData,
          modelName: forecast.modelName,
          trueId: forecast.trueId,
        };

        const dialogRef = this.dialog.open(AddModelDialogComponent, {
          width: '600px',
          data: editData,
        });

        dialogRef.afterClosed().subscribe((updatedForecast) => {
          if (updatedForecast) {
            this.updateForecast(updatedForecast);
          }
        });
      },
      (error) => {
        console.error('Error fetching forecast details for editing:', error);
      }
    );
  }

  updateForecast(forecast: Order): void {
    this.forecastService.updatePredictiveModel(forecast).subscribe(
      () => {
        this.loadDeviceModels();
      },
      (error) => {
        console.error('Error updating forecast:', error);
      }
    );
  }

  confirmDeleteForecast(event: Event, forecast: Order): void {
    if (event) {
      event.stopPropagation();
    }
    const modelName = forecast.modelName || forecast.id || 'Unknown Model';
    const title = this.translate.instant('forecast.delete-model-title');
    const content = this.translate.instant('forecast.delete-model-text', {
      modelName,
    });
    this.dialogService
      .confirm(
        title,
        content,
        this.translate.instant('action.no'),
        this.translate.instant('action.yes')
      )
      .subscribe((result) => {
        if (result) {
          this.deleteForecast(forecast.trueId);
        }
      });
  }

  deleteForecast(forecastId: string): void {
    this.forecastService.deletePredictiveModel(forecastId).subscribe(
      () => {
        this.loadDeviceModels();
      },
      (error) => {
        console.error('Error deleting forecast:', error);
      }
    );
  }

  openAddModelDialog(): void {
    const dialogRef = this.dialog.open(AddModelDialogComponent, {
      width: '600px',
      data: { deviceId: this.deviceId },
    });

    dialogRef.afterClosed().subscribe((result) => {
      if (result) {
        this.addForecast(result);
      }
    });
  }

  addForecast(forecast: any): void {
    this.forecastService.addPredictiveModelConfig(forecast).subscribe(
      () => {
        this.loadDeviceModels();
      },
      (error) => {
        console.error('Error adding forecast:', error);
      }
    );
  }

  refreshModels(): void {
    this.loadDeviceModels();
  }

  goBack(): void {
    this.router.navigate(['/predictive-maintenance']);
  }

  applyFilter(event: Event): void {
    const filterValue = (event.target as HTMLInputElement).value;
    this.dataSource.filter = filterValue.trim().toLowerCase();

    if (this.dataSource.paginator) {
      this.dataSource.paginator.firstPage();
    }
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
      return;
    }
    this.selection.select(...this.dataSource.data);
  }

  /** The label for the checkbox on the passed row */
  checkboxLabel(row?: Order): string {
    if (!row) {
      return `${this.isAllSelected() ? 'deselect' : 'select'} all`;
    }
    return `${this.selection.isSelected(row) ? 'deselect' : 'select'} row ${
      row.modelName
    }`;
  }
}
