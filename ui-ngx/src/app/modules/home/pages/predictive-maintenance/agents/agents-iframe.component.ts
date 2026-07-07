import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'tb-pdm-agents-iframe',
  standalone: true,
  imports: [CommonModule, MatIconModule],
  templateUrl: './agents-iframe.component.html',
  styleUrls: ['./agents-iframe.component.scss'],
})
export class AgentsIframeComponent {
  readonly runtimeUrl: SafeResourceUrl;

  constructor(sanitizer: DomSanitizer) {
    this.runtimeUrl = sanitizer.bypassSecurityTrustResourceUrl('http://localhost:8300');
  }
}
