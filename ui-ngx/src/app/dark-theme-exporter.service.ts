// src/app/dark-theme-exporter.service.ts
import { Injectable } from '@angular/core';

// declare global {
//   interface Window {
//     DarkReader: {
//       enable(theme: object): void;
//       disable(): void;
//       exportGeneratedCSS(): Promise<string>;
//       isEnabled(): boolean;
//     };
//   }
// }

@Injectable({ providedIn: 'root' })
export class DarkThemeExporterService {
  readonly defaultTheme = { brightness: 100, contrast: 90, sepia: 10 };

  private async load(): Promise<void> {
    if (window.DarkReader) return;
    await new Promise<void>((resolve, reject) => {
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/darkreader/darkreader.min.js';
      s.onload = () => resolve();
      s.onerror = () => reject(new Error('Failed to load Dark Reader'));
      document.head.appendChild(s);
    });
  }

  async enable(theme = this.defaultTheme): Promise<void> {
    await this.load();
    window.DarkReader.enable(theme);
  }

  disable(): void {
    window.DarkReader?.disable();
  }

  isEnabled(): boolean {
    return window.DarkReader?.isEnabled() ?? false;
  }

  async exportCSS(): Promise<string> {
    const css = await window.DarkReader.exportGeneratedCSS();
    if (!css) throw new Error('Empty CSS — enable Dark Reader first.');
    return css;
  }

  downloadCSS(css: string, filename = 'dark-theme.css'): void {
    const a = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(new Blob([css], { type: 'text/css' })),
      download: filename,
    });
    a.click();
    URL.revokeObjectURL(a.href);
  }
}