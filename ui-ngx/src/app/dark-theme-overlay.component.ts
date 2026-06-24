import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DarkThemeExporterService } from './dark-theme-exporter.service';

@Component({
  selector: 'app-dark-theme-overlay',
  standalone: true,
  imports: [CommonModule],
  styles: [`
    :host {
      z-index: -100;
    }
    .dr-fab {
      position: fixed; bottom: 24px; right: 24px; z-index: 99999;
      display: flex; flex-direction: column; align-items: flex-end; gap: 8px;
    }
    .dr-panel {
      background: #1e1e1e; color: #fff; border-radius: 10px;
      padding: 16px; width: 260px; font-size: 13px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.5);
    }
    .dr-panel h4 { margin: 0 0 12px; font-size: 14px; }
    .dr-panel p  { margin: 8px 0 0; color: #aaa; font-size: 11px; line-height: 1.4; }
    .dr-btn {
      width: 100%; margin-top: 8px; padding: 8px;
      border: none; border-radius: 6px; cursor: pointer;
      font-size: 12px; font-weight: 600;
    }
    .dr-btn-enable  { background: #4caf50; color: #fff; }
    .dr-btn-disable { background: #f44336; color: #fff; }
    .dr-btn-export  { background: #2196f3; color: #fff; }
    .dr-btn-export:disabled { opacity: 0.5; cursor: not-allowed; }
    .dr-toggle {
      width: 48px; height: 48px; border-radius: 50%;
      background: #1e1e1e; color: #fff; border: none;
      font-size: 20px; cursor: pointer;
      box-shadow: 0 2px 12px rgba(0,0,0,0.4);
    }
    .dr-status { font-size: 11px; color: #aaa; margin-top: 8px; word-break: break-word; }
  `],
  template: `
    <div class="dr-fab">
      @if (open()) {
        <div class="dr-panel">
          <h4>🌙 Dark Reader Export</h4>

          @if (!enabled()) {
            <button class="dr-btn dr-btn-enable" (click)="enable()">
              Enable Dark Mode
            </button>
            <p>Enable, then navigate to every page you want covered.</p>
          } @else {
            <button class="dr-btn dr-btn-disable" (click)="disable()">
              Disable Dark Mode
            </button>
            <p>✅ Active — navigate around to load all stylesheets, then export.</p>
            <button class="dr-btn dr-btn-export" (click)="exportCSS()" [disabled]="exporting()">
              {{ exporting() ? 'Exporting…' : 'Export & Download CSS' }}
            </button>
          }

          @if (status()) {
            <div class="dr-status">{{ status() }}</div>
          }
        </div>
      }
      <button class="dr-toggle" (click)="open.set(!open())" title="Dark Reader Export">
        🌙
      </button>
    </div>
  `
})
export class DarkThemeOverlayComponent {
  open     = signal(false);
  enabled  = signal(false);
  exporting = signal(false);
  status   = signal('');

  constructor(private svc: DarkThemeExporterService) {}

  async enable() {
    this.status.set('Loading Dark Reader…');
    await this.svc.enable();
    this.enabled.set(true);
    this.status.set('Navigate to all pages, then export.');
  }

  disable() {
    this.svc.disable();
    this.enabled.set(false);
    this.status.set('');
  }

  async exportCSS() {
    this.exporting.set(true);
    this.status.set('Exporting…');
    try {
      const css = await this.svc.exportCSS();
      this.svc.downloadCSS(css);
      this.status.set(`✅ ${(css.length / 1024).toFixed(1)} KB downloaded.`);
    } catch (e: any) {
      this.status.set(`❌ ${e.message}`);
    } finally {
      this.exporting.set(false);
    }
  }
}