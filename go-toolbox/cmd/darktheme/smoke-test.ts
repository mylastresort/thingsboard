// smoke-test.ts
import { parseColorWithCache } from './color';
import { modifyBackgroundColor, modifyForegroundColor } from './modify-colors';
import type { Theme } from './types';

const THEME: Theme = {
    mode: 1, brightness: 100, contrast: 100, grayscale: 0, sepia: 0,
    darkSchemeBackgroundColor: '#181a1b', darkSchemeTextColor: '#e8e6e3',
    lightSchemeBackgroundColor: '#dcdad7', lightSchemeTextColor: '#161311',
};

console.log('white bg →', modifyBackgroundColor(parseColorWithCache('#ffffff')!, THEME, false)); // expect ~#181a1b
console.log('black fg →', modifyForegroundColor(parseColorWithCache('#000000')!, THEME, false)); // expect ~#e8e6e3