import { CommonModule } from "@angular/common";
import { Component, Inject } from "@angular/core";
import { MatButtonModule } from "@angular/material/button";
import { MAT_DIALOG_DATA, MatDialogModule } from "@angular/material/dialog";
import { MatIconModule } from "@angular/material/icon";
import type { PdmSeedMachineResult } from "@app/core/api-client";

interface SeededMachineSummary {
  machineId: string;
  deviceId: string;
}

@Component({
  selector: "tb-seed-machine-result-dialog",
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
  ],
  templateUrl: "./seed-machine-result-dialog.component.html",
  styleUrls: ["./seed-machine-result-dialog.component.scss"],
})
export class SeedMachineResultDialogComponent {
  readonly machines: SeededMachineSummary[];

  constructor(
    @Inject(MAT_DIALOG_DATA) public result: PdmSeedMachineResult
  ) {
    this.machines = Object.entries(result.machineToDevice || {})
      .map(([machineId, deviceId]) => ({ machineId, deviceId }))
      .sort((left, right) => Number(left.machineId) - Number(right.machineId));
  }

  get failureModeRecords(): number | null {
    return (this.result as PdmSeedMachineResult & { failureModeRecords?: number }).failureModeRecords ?? null;
  }
}
