import { CommonModule } from '@angular/common';
import { Component, Inject, OnInit } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatToolbarModule } from '@angular/material/toolbar';
import { PredictiveModelsService, AgenticBenchmarkRow, AgenticBenchmarkSubset } from '@app/core/http/forecast.service';

@Component({
  selector: 'tb-pdm-agents-benchmark',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatPaginatorModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTableModule,
    MatTooltipModule,
    MatToolbarModule,
  ],
  templateUrl: './agents-benchmark.component.html',
  styleUrls: ['./agents-benchmark.component.scss'],
})
export class AgentsBenchmarkComponent implements OnInit {
  subsets: AgenticBenchmarkSubset[] = [];
  rows: AgenticBenchmarkRow[] = [];
  displayedColumns = ['subsetName', 'datasetRecordId', 'assetName', 'subject', 'question', 'answer', 'actions'];
  selectedSubset = '';
  textSearch = '';
  pageIndex = 0;
  pageSize = 25;
  totalElements = 0;
  isLoading = false;

  constructor(
    private predictiveModelsService: PredictiveModelsService,
    private dialog: MatDialog,
    private snackBar: MatSnackBar
  ) {}

  ngOnInit(): void {
    this.loadSubsets();
  }

  loadSubsets(): void {
    this.predictiveModelsService.getAgenticBenchmarkSubsets().subscribe({
      next: (subsets) => {
        this.subsets = subsets;
        this.selectedSubset = this.selectedSubset || subsets[0]?.name || '';
        this.loadRows();
      },
      error: () => this.snackBar.open('Unable to load benchmark subsets', 'Close', { duration: 4000 }),
    });
  }

  loadRows(): void {
    this.isLoading = true;
    this.predictiveModelsService
      .getAgenticBenchmarkRows(this.pageSize, this.pageIndex, this.selectedSubset, this.textSearch)
      .subscribe({
        next: (page) => {
          this.rows = page.data || [];
          this.totalElements = page.totalElements || 0;
          this.isLoading = false;
        },
        error: () => {
          this.isLoading = false;
          this.snackBar.open('Unable to load benchmark rows', 'Close', { duration: 4000 });
        },
      });
  }

  importDataset(): void {
    this.isLoading = true;
    this.predictiveModelsService.importAgenticBenchmarkRows().subscribe({
      next: () => {
        this.snackBar.open('AssetOpsBench rows imported', undefined, { duration: 3000 });
        this.loadSubsets();
      },
      error: () => {
        this.isLoading = false;
        this.snackBar.open('Unable to import AssetOpsBench rows', 'Close', { duration: 4000 });
      },
    });
  }

  applySubset(subset: string): void {
    this.selectedSubset = subset;
    this.pageIndex = 0;
    this.loadRows();
  }

  applySearch(value: string): void {
    this.textSearch = value;
    this.pageIndex = 0;
    this.loadRows();
  }

  pageChanged(event: PageEvent): void {
    this.pageIndex = event.pageIndex;
    this.pageSize = event.pageSize;
    this.loadRows();
  }

  openCreateDialog(): void {
    this.openDialog();
  }

  openEditDialog(row: AgenticBenchmarkRow): void {
    this.openDialog(row);
  }

  deleteRow(row: AgenticBenchmarkRow): void {
    this.predictiveModelsService.deleteAgenticBenchmarkRow(row.id).subscribe({
      next: () => {
        this.snackBar.open('Benchmark row deleted', undefined, { duration: 2500 });
        this.loadRows();
      },
      error: () => this.snackBar.open('Unable to delete benchmark row', 'Close', { duration: 4000 }),
    });
  }

  answer(row: AgenticBenchmarkRow): string {
    const correct = row.correct || [];
    return (row.options || [])
      .filter((_, index) => correct[index])
      .join(', ') || 'N/A';
  }

  private openDialog(row?: AgenticBenchmarkRow): void {
    const dialogRef = this.dialog.open(AgenticBenchmarkRowDialogComponent, {
      width: '720px',
      data: { row, subsetName: this.selectedSubset || this.subsets[0]?.name || 'custom' },
    });
    dialogRef.afterClosed().subscribe((result?: AgenticBenchmarkRow) => {
      if (!result) {
        return;
      }
      const request$ = row?.id
        ? this.predictiveModelsService.updateAgenticBenchmarkRow(row.id, result)
        : this.predictiveModelsService.createAgenticBenchmarkRow(result);
      request$.subscribe({
        next: () => this.loadRows(),
        error: () => this.snackBar.open('Unable to save benchmark row', 'Close', { duration: 4000 }),
      });
    });
  }
}

@Component({
  selector: 'tb-pdm-agents-benchmark-row-dialog',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, MatButtonModule, MatDialogModule, MatFormFieldModule, MatInputModule],
  template: `
    <h2 mat-dialog-title>{{ data.row ? 'Edit Benchmark Row' : 'Add Benchmark Row' }}</h2>
    <form [formGroup]="form" (ngSubmit)="save()">
      <mat-dialog-content class="benchmark-dialog-content">
        <mat-form-field appearance="outline">
          <mat-label>Subset</mat-label>
          <input matInput formControlName="subsetName" />
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Dataset Record ID</mat-label>
          <input matInput type="number" formControlName="datasetRecordId" />
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Asset</mat-label>
          <input matInput formControlName="assetName" />
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Subject</mat-label>
          <input matInput formControlName="subject" />
        </mat-form-field>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Question</mat-label>
          <textarea matInput rows="4" formControlName="question"></textarea>
        </mat-form-field>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Options JSON array</mat-label>
          <textarea matInput rows="3" formControlName="optionsJson"></textarea>
        </mat-form-field>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Correct JSON array</mat-label>
          <textarea matInput rows="2" formControlName="correctJson"></textarea>
        </mat-form-field>
      </mat-dialog-content>
      <mat-dialog-actions align="end">
        <button mat-button type="button" mat-dialog-close>Cancel</button>
        <button mat-flat-button color="primary" type="submit" [disabled]="form.invalid">Save</button>
      </mat-dialog-actions>
    </form>
  `,
  styles: [`
    .benchmark-dialog-content {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .full-width {
      grid-column: 1 / -1;
    }
  `],
})
export class AgenticBenchmarkRowDialogComponent {
  form = this.fb.group({
    subsetName: [this.data.row?.subsetName || this.data.subsetName, Validators.required],
    datasetRecordId: [this.data.row?.datasetRecordId ?? null],
    assetName: [this.data.row?.assetName || ''],
    subject: [this.data.row?.subject || ''],
    question: [this.data.row?.question || '', Validators.required],
    optionsJson: [JSON.stringify(this.data.row?.options || [], null, 2)],
    correctJson: [JSON.stringify(this.data.row?.correct || [], null, 2)],
  });

  constructor(
    private fb: FormBuilder,
    private dialogRef: MatDialogRef<AgenticBenchmarkRowDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { row?: AgenticBenchmarkRow; subsetName: string }
  ) {}

  save(): void {
    const value = this.form.value;
    this.dialogRef.close({
      ...this.data.row,
      subsetName: value.subsetName,
      datasetRecordId: value.datasetRecordId,
      assetName: value.assetName,
      subject: value.subject,
      question: value.question,
      options: this.parseJsonArray(value.optionsJson),
      correct: this.parseJsonArray(value.correctJson),
    });
  }

  private parseJsonArray(value: string): any[] {
    try {
      const parsed = JSON.parse(value || '[]');
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
}
