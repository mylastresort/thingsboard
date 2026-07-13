import { CommonModule } from "@angular/common";
import { Component, Inject } from "@angular/core";
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from "@angular/forms";
import { MatButtonModule } from "@angular/material/button";
import { MatButtonToggleModule } from "@angular/material/button-toggle";
import { MatCheckboxModule } from "@angular/material/checkbox";
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from "@angular/material/dialog";
import { MatFormFieldModule } from "@angular/material/form-field";
import { MatIconModule } from "@angular/material/icon";
import { MatInputModule } from "@angular/material/input";
import { MatSelectModule } from "@angular/material/select";
import type {
  PdmSeedMachineDefaults,
  PdmSeedMachineOptions,
  PdmSeedMachineRequest,
  PdmSeedMachineSelection,
} from "@app/core/api-client";

type SeedMode = "maxMachines" | "selectedMachines";

@Component({
  selector: "tb-seed-machine-dialog",
  standalone: true,
  imports: [
    CommonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatButtonToggleModule,
    MatIconModule,
    MatCheckboxModule,
    MatSelectModule,
    ReactiveFormsModule,
  ],
  templateUrl: "./seed-machine-dialog.component.html",
  styleUrls: ["./seed-machine-dialog.component.scss"],
})
export class SeedMachineDialogComponent {
  machineOptions: PdmSeedMachineOptions["machines"] = [];
  selectedMachineNameControls = new Map<number, FormControl<string>>();

  form = new FormGroup({
    mode: new FormControl<SeedMode>("maxMachines", { nonNullable: true }),
    machinePrefix: new FormControl("PdM-Machine", Validators.maxLength(255)),
    selectedMachineIds: new FormControl<number[]>([]),
    maxMachines: new FormControl(1, [Validators.required, Validators.min(1)]),
    shiftToNow: new FormControl(true),
    workers: new FormControl(1, [Validators.required, Validators.min(1)]),
  });

  constructor(
    private dialogRef: MatDialogRef<SeedMachineDialogComponent, PdmSeedMachineRequest>,
    @Inject(MAT_DIALOG_DATA) public data: PdmSeedMachineOptions | null
  ) {
    this.machineOptions = data?.machines || [];
    const defaults: PdmSeedMachineDefaults = data?.defaults ?? { mode: "maxMachines" };
    this.form.patchValue({
      mode: (defaults.mode as SeedMode) || "maxMachines",
      machinePrefix: defaults.machinePrefix || "PdM-Machine",
      selectedMachineIds: (defaults.machines || []).map((machine) => machine.machineId),
      maxMachines: defaults.maxMachines || 1,
      shiftToNow: defaults.shiftToNow ?? true,
      workers: defaults.workers || 1,
    });
    for (const machine of defaults.machines || []) {
      this.machineNameControl(machine.machineId).setValue(machine.machineName || this.defaultMachineName(machine.machineId));
    }
  }

  seed(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const value = this.form.getRawValue();
    let request: PdmSeedMachineRequest;
    if (value.mode === "selectedMachines") {
      const machines: PdmSeedMachineSelection[] = this.selectedMachines().map((machineId) => ({
        machineId,
        machineName: this.machineNameControl(machineId).value.trim(),
      }));
      if (machines.length === 0 || machines.some((machine) => !machine.machineName)) {
        this.form.controls.selectedMachineIds.setErrors({ required: true });
        for (const machineId of this.selectedMachines()) {
          this.machineNameControl(machineId).markAsTouched();
        }
        return;
      }
      request = {
        mode: "selectedMachines",
        machines,
        shiftToNow: !!value.shiftToNow,
        workers: Number(value.workers || 1),
      };
    } else {
      request = {
        mode: "maxMachines",
        machinePrefix: value.machinePrefix?.trim() || undefined,
        maxMachines: Number(value.maxMachines || 1),
        shiftToNow: !!value.shiftToNow,
        workers: Number(value.workers || 1),
      };
    }
    this.dialogRef.close(request);
  }

  selectedMachines(): number[] {
    return this.form.controls.selectedMachineIds.value || [];
  }

  onSelectedMachineIdsChange(machineIds: number[]): void {
    this.form.controls.selectedMachineIds.setErrors(null);
    for (const machineId of machineIds || []) {
      this.machineNameControl(machineId);
    }
  }

  machineNameControl(machineId: number): FormControl<string> {
    let control = this.selectedMachineNameControls.get(machineId);
    if (!control) {
      control = new FormControl(this.defaultMachineName(machineId), {
        nonNullable: true,
        validators: [Validators.required, Validators.maxLength(255)],
      });
      this.selectedMachineNameControls.set(machineId, control);
    }
    return control;
  }

  machineLabel(machineId: number): string {
    const machine = this.machineOptions.find((option) => option.machineId === machineId);
    return machine?.label || this.defaultMachineName(machineId);
  }

  private defaultMachineName(machineId: number): string {
    return `PdM-Machine-${machineId}`;
  }
}
