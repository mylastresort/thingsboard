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
    };
  }
}

@Injectable({ providedIn: 'root' })
export class DarkThemeService {

  private styleSheet: CSSStyleSheet | null = null;

  readonly theme: DarkReaderTheme = {
    brightness: 100,
    contrast: 100,
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
    const css = await this.generateCSS();
    this.inject(css);
    document.documentElement.style.colorScheme = 'dark';
    // add <meta name="darkreader-lock"> to head to prevent Dark Reader extension from overriding our styles
    document.head.appendChild(
      Object.assign(document.createElement('meta'), {
        name: 'darkreader-lock',
      })
    );
    localStorage.setItem('theme', 'dark');
  }

  disable(): void {
    this.eject();
    document.documentElement.style.colorScheme = 'light';
    localStorage.setItem('theme', 'light');
  }

  isEnabled(): boolean {
    return this.styleSheet !== null &&
      document.adoptedStyleSheets.includes(this.styleSheet);
  }

  toggle(): Promise<void> | void {
    return this.isEnabled() ? this.disable() : this.enable();
  }

  async restore(): Promise<void> {
    if (localStorage.getItem('theme') === 'dark') await this.enable();
  }

  // re-generate after changing fixes during dev
  async refresh(): Promise<void> {
    this.eject();
    const css = await this.generateCSS();
    this.inject(css);
  }

  // ─── Internals ─────────────────────────────────────────────────────────────

  private async generateCSS(): Promise<string> {
    await this.load();
    window.DarkReader.enable(this.theme, this.fixes);
    await this.wait(2500);                              // let DR process all stylesheets
    const css = await window.DarkReader.exportGeneratedCSS();
    window.DarkReader.disable();                        // DR done, no active state left
    if (!css) throw new Error('Dark Reader returned empty CSS');
    return css;
  }

  // inject via adoptedStyleSheets — no DOM node, invisible to DR extension
  private inject(css: string): void {
    if (!this.styleSheet) {
      this.styleSheet = new CSSStyleSheet();
      document.adoptedStyleSheets = [...document.adoptedStyleSheets, this.styleSheet];
    }
    this.styleSheet.replaceSync(css);
  }

  private eject(): void {
    if (!this.styleSheet) return;
    document.adoptedStyleSheets = document.adoptedStyleSheets
      .filter(s => s !== this.styleSheet);
    this.styleSheet = null;
  }

  private wait(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  private async load(): Promise<void> {
    if (window.DarkReader) return;
    await new Promise<void>((resolve, reject) => {
      document.head.appendChild(
        Object.assign(document.createElement('script'), {
          src: 'https://cdn.jsdelivr.net/npm/darkreader/darkreader.min.js',
          onload: resolve,
          onerror: () => reject(new Error('Failed to load Dark Reader')),
        })
      );
    });
  }
}