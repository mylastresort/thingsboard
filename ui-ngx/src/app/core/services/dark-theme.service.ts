// src/app/core/services/dark-theme.service.ts
import { Injectable } from '@angular/core';

// Minimal type shim — avoids importing darkreader's CJS-style `export =` typings,
// which break ESM builds (TS1203). DarkReader itself is loaded at runtime via CDN.
interface DarkReaderTheme {
  brightness: number;
  contrast: number;
  sepia: number;
  darkSchemeBackgroundColor?: string;
  darkSchemeTextColor?: string;
  lightSchemeBackgroundColor?: string;
  lightSchemeTextColor?: string;
  fontFamily?: string;
  grayscale?: number;
  mode?: number;
  textStroke?: number;
  useFont?: boolean;
  scrollbarColor?: string;
  selectionColor?: string;
  styleSystemControls?: boolean;
}

interface DarkReaderFix {
  invert?: string[];
  css?: string;
  ignoreInlineStyle?: string[];
  ignoreImageAnalysis?: string[];
  disableStyleSheetsProxy?: boolean;
  ignoreCSSUrl?: string[];
}

// Teach TypeScript about the CDN-loaded global
declare global {
  interface Window {
    DarkReader: {
      enable(theme: DarkReaderTheme, fixes?: DarkReaderFix): void;
      disable(): void;
      exportGeneratedCSS(): Promise<string>;
      isEnabled(): boolean;
    };
  }
}

@Injectable({ providedIn: 'root' })
export class DarkThemeService {

  private styleSheet: CSSStyleSheet | null = null;

  readonly theme: DarkReaderTheme = {
    brightness: 100,
    contrast: 110,
    sepia: 0,
    // darkSchemeBackgroundColor: '#080808',
    // darkSchemeTextColor: '#cdd6f4',
    // lightSchemeBackgroundColor: '#ffffff',
    // lightSchemeTextColor: '#000000',
    // fontFamily: 'inherit',
    // grayscale: 0,
    // mode: 1,
    // textStroke: 0,
    // useFont: false,
    // scrollbarColor: 'auto',
    // selectionColor: 'rgba(0, 0, 0, 0.2)',
    // styleSystemControls: false,
  };

  readonly fixes: DarkReaderFix = {
    // invert: [],
    // css: `
    //   .mat-mdc-table,
    //   .mat-mdc-cell,
    //   .mat-mdc-header-cell {
    //     color: #cdd6f4 !important;
    //   }
    // `,
    // ignoreInlineStyle: [
    // ],
    // ignoreImageAnalysis: [
    // ],
    // disableStyleSheetsProxy: false,
    // ignoreCSSUrl: [],
  };

  // ─── Public API ────────────────────────────────────────────────────────────

  async enable(): Promise<void> {
    if (this.isEnabled()) return;

    await this.load();

    window.DarkReader.enable(this.theme, this.fixes);

    document.documentElement.style.colorScheme = 'dark';

    // if (!document.querySelector('meta[name="darkreader-lock"]')) {
    //   const meta = document.createElement('meta');
    //   meta.name = 'darkreader-lock';
    //   document.head.appendChild(meta);
    // }

    localStorage.setItem('theme', 'dark');
  }

  async load(): Promise<void> {
    if ((window as any).DarkReader) {
      return;
    }

    return new Promise<void>((resolve, reject) => {
      const script = document.createElement('script');

      script.src = 'assets/lib/darkreader.js';

      script.onload = () => resolve();

      script.onerror = () =>
        reject(new Error('Failed to load darkreader.js'));

      document.head.appendChild(script);
    });
  }

  disable(): void {
    this.eject();
    if (!window.DarkReader) return;
    window.DarkReader.disable();
    document.documentElement.style.colorScheme = 'light';
    localStorage.setItem('theme', 'light');
  }

  isEnabled(): boolean {
    const a = !!window.DarkReader && window.DarkReader.isEnabled();
    // console.log('DarkThemeService.isEnabled():', a);
    return a;
  }

  toggle(): Promise<void> | void {
    return this.isEnabled() ? this.disable() : this.enable();
  }

  async restore(): Promise<void> {
    if (localStorage.getItem('theme') === 'dark') await this.enable();
  }

  private eject(): void {
    if (!this.styleSheet) return;
    document.adoptedStyleSheets = document.adoptedStyleSheets
      .filter(s => s !== this.styleSheet);
    this.styleSheet = null;
  }
}