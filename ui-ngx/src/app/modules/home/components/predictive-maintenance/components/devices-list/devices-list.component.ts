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
import {
  MatPaginator,
  MatPaginatorModule,
  PageEvent,
} from '@angular/material/paginator';
import { MatSort, MatSortModule } from '@angular/material/sort';
import { MatTableDataSource, MatTableModule } from '@angular/material/table';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { SelectionModel } from '@angular/cdk/collections';
import { Router } from '@angular/router';
import { PredictiveModelsService } from '@app/core/http/forecast.service';
import { DeviceService } from '@app/core/public-api';
import { Direction, PageLink } from '@app/shared/public-api';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import {
  animate,
  state,
  style,
  transition,
  trigger,
} from '@angular/animations';
import { AddModelDialogComponent } from '../model/add-model-dialog/add-model-dialog.component';

export interface DeviceWithModels {
  id: string;
  name: string;
  label: string;
  type: string;
  createdTime: number;
  modelsCount: number;
  models?: any[];
  expanded?: boolean;
}

@Component({
  selector: 'tb-devices-list',
  templateUrl: './devices-list.component.html',
  styleUrls: ['./devices-list.component.scss'],
  standalone: true,
  animations: [
    trigger('detailExpand', [
      state('collapsed', style({ height: '0px', minHeight: '0' })),
      state('expanded', style({ height: '*' })),
      transition(
        'expanded <=> collapsed',
        animate('225ms cubic-bezier(0.4, 0.0, 0.2, 1)')
      ),
    ]),
  ],
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
  ],
})
export class DevicesListComponent implements OnInit {
  displayedColumns: string[] = [
    'select',
    'createdTime',
    'name',
    'label',
    'type',
    'modelsCount',
    'actions',
  ];

  dataSource = new MatTableDataSource<DeviceWithModels>();

  selection = new SelectionModel<DeviceWithModels>(true, []);

  expandedElement: DeviceWithModels | null = null;

  textSearch = new FormControl();

  textSearchMode = false;

  hideDevicesWithNoModels = true; // Default: show only devices with at least one model

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
    private router: Router
  ) {}

  ngOnInit() {}

  // eslint-disable-next-line @angular-eslint/use-lifecycle-interface
  ngAfterViewInit() {
    this.dataSource.paginator = this.paginator;
    this.dataSource.sort = this.sort;

    // Set default sort to modelsCount descending
    this.sort.active = 'modelsCount';
    this.sort.direction = 'desc';

    this.fetchDevicesWithModels(
      this.paginator?.pageIndex || 0,
      this.paginator?.pageSize || 10
    );
    this.paginator?.page.subscribe(() => {
      this.fetchDevicesWithModels(
        this.paginator.pageIndex,
        this.paginator.pageSize
      );
    });
  }

  fetchDevicesWithModels(pageIndex: number, pageSize: number): void {
    this.isLoading = true;

    const pageLink = new PageLink(pageSize, pageIndex, null, {
      property: 'createdTime',
      direction: Direction.DESC,
    });

    // Use the new endpoint that returns devices with models count in one query
    // Pass the hideDevicesWithNoModels flag to filter on backend
    this.forecastService
      .getDevicesWithModelsCount(pageLink, this.hideDevicesWithNoModels)
      .subscribe(
        (devicesWithModelsPage) => {
          console.log(
            'Devices with models API response:',
            devicesWithModelsPage
          );

          if (devicesWithModelsPage.data.length === 0) {
            this.dataSource.data = [];
            this.totalElements = devicesWithModelsPage.totalElements;
            this.isLoading = false;
            return;
          }

          const devicesWithModels: DeviceWithModels[] =
            devicesWithModelsPage.data.map((item) => {
              const device = item.device;
              return {
                id: device.id.id,
                name: device.name,
                label: device.label || 'No label',
                type: device.type || 'Unknown',
                createdTime: device.createdTime,
                modelsCount: item.modelsCount || 0,
                models: [],
                expanded: false,
              };
            });

          // No need to filter on frontend anymore, backend handles it
          this.dataSource.data = devicesWithModels;
          this.totalElements = devicesWithModelsPage.totalElements;
          this.isLoading = false;
        },
        (error) => {
          console.error('Error fetching devices with models:', error);
          this.isLoading = false;
        }
      );
  }

  toggleRow(element: DeviceWithModels): void {
    if (this.expandedElement === element) {
      this.expandedElement = null;
      element.expanded = false;
    } else {
      // Collapse previous expanded row
      if (this.expandedElement) {
        this.expandedElement.expanded = false;
      }

      this.expandedElement = element;
      element.expanded = true;

      // Load models for this device if not already loaded
      if (!element.models || element.models.length === 0) {
        this.loadDeviceModels(element);
      }
    }
  }

  loadDeviceModels(device: DeviceWithModels): void {
    this.forecastService.getForecastsByDeviceId(device.id).subscribe(
      (response) => {
        device.models = response.data.map((forecast: any) => ({
          id: forecast.id.id,
          modelName:
            forecast.name ||
            forecast.modelName ||
            `Model_${forecast.id.id.split('-')[0]}`,
          createdTime: forecast.createdTime,
          attributesText:
            forecast.attributes && forecast.attributes.length > 0
              ? forecast.attributes.map((attr: any) => attr.key).join(', ')
              : 'No attributes',
          forecastAlgorithm: forecast.forecastAlgorithm || 'N/A',
          anomalyAlgorithm: forecast.anomalyAlgorithm || 'N/A',
        }));
      },
      (error) => {
        console.error(`Error loading models for device ${device.id}:`, error);
        device.models = [];
      }
    );
  }

  viewDeviceModels(event: Event, device: DeviceWithModels): void {
    if (event) {
      event.stopPropagation();
    }
    this.router.navigate([
      '/predictive-maintenance/device',
      device.id,
      'models',
    ]);
  }

  openModel(event: Event, deviceId: string, modelId: string): void {
    if (event) {
      event.stopPropagation();
    }
    this.router.navigate(['/predictive-maintenance/forecast', modelId]);
  }

  applyFilter(event: Event): void {
    const filterValue = (event.target as HTMLInputElement).value;
    this.dataSource.filter = filterValue.trim().toLowerCase();

    if (this.dataSource.paginator) {
      this.dataSource.paginator.firstPage();
    }
  }

  refreshDevices(): void {
    this.fetchDevicesWithModels(
      this.paginator.pageIndex,
      this.paginator.pageSize
    );
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

  addConfiguration(config: any): void {
    this.forecastService.addPredictiveModelConfig(config).subscribe(
      () => {
        // Add a small delay to ensure backend has updated the count
        setTimeout(() => {
          this.refreshDevices();
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

  toggleDevicesWithNoModels(): void {
    this.hideDevicesWithNoModels = !this.hideDevicesWithNoModels;
    this.refreshDevices();
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
  checkboxLabel(row?: DeviceWithModels): string {
    if (!row) {
      return `${this.isAllSelected() ? 'deselect' : 'select'} all`;
    }
    return `${this.selection.isSelected(row) ? 'deselect' : 'select'} row ${
      row.name
    }`;
  }
}
