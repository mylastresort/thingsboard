// Shadows node_modules/darkreader/index.d.ts which uses `export = DarkReader`
// (CJS-style), causing TS1203 in ESM builds. Named exports are ESM-compatible.
declare module 'darkreader' {
  export function enable(theme: object, fixes?: object): void;
  export function disable(): void;
  export function exportGeneratedCSS(): Promise<string>;
}