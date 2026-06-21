#!/usr/bin/env node
/**
 * dark-scss engine — wraps Dark Reader's open-source color logic
 * Reads a SCSS file, appends .dark-theme { ... } block with DR-converted colors.
 *
 * Usage: node engine.js <file.scss> [--selector .dark-theme]
 */
import { readFileSync, writeFileSync, existsSync } from 'fs';
import postcss, { Declaration, Rule, AtRule, ChildNode } from 'postcss';
import postcssScss from 'postcss-scss';
import postcssNested from 'postcss-nested';
import { parseColorWithCache, rgbToHSL } from './color';
import {
    modifyBackgroundColor,
    modifyForegroundColor,
    modifyBorderColor,
} from './modify-colors';
import type { Theme } from './types';


const THEME: Theme = {
    mode: 1,
    brightness: 100,
    contrast: 100,
    grayscale: 0,
    sepia: 0,
    darkSchemeBackgroundColor: '#181a1b',
    darkSchemeTextColor: '#e8e6e3',
    lightSchemeBackgroundColor: '#dcdad7',
    lightSchemeTextColor: '#161311',
};

function roleOf(prop: string): 'bg' | 'fg' | 'border' | null {
    const p = prop.toLowerCase();
    if (p === 'color' || p === 'fill' || p === 'stroke' ||
        p === 'caret-color' || p === 'text-decoration-color') return 'fg';
    if (p.startsWith('border') || p === 'outline' || p === 'outline-color') return 'border';
    if (p === 'background' || p === 'background-color' ||
        p === 'box-shadow' || p === 'text-shadow') return 'bg';
    return null;
}

const COLOR_RE = /#[0-9a-fA-F]{3,8}\b|rgba?\([^)]+\)|hsla?\([^)]+\)/g;

function transformValue(value: string, role: 'bg' | 'fg' | 'border'): string | null {
    let changed = false;
    const result = value.replace(COLOR_RE, (token) => {
        const rgb = parseColorWithCache(token);
        if (!rgb) return token;
        let out: string;
        if (role === 'fg')     out = modifyForegroundColor(rgb, THEME, false);
        else if (role === 'border') out = modifyBorderColor(rgb, THEME, false);
        else                   out = modifyBackgroundColor(rgb, THEME, false);
        if (out !== token) changed = true;
        return out;
    });
    if (!changed) {
        const rgb = parseColorWithCache(value.trim());
        if (rgb) {
            let out: string;
            if (role === 'fg')     out = modifyForegroundColor(rgb, THEME, false);
            else if (role === 'border') out = modifyBorderColor(rgb, THEME, false);
            else                   out = modifyBackgroundColor(rgb, THEME, false);
            if (out !== value.trim()) return out;
        }
    }
    return changed ? result : null;
}

// Skip files where most colors are already dark (lightness < 0.5).
// ponytail: ratio threshold 0.6 — files already dark-schemed don't need conversion
function isAlreadyDark(root: postcss.Root): boolean {
    let dark = 0, total = 0;
    root.walkDecls((decl) => {
        const matches = decl.value.match(COLOR_RE);
        if (!matches) return;
        for (const token of matches) {
            const rgb = parseColorWithCache(token);
            if (!rgb) continue;
            total++;
            if (rgbToHSL(rgb).l < 0.5) dark++;
        }
    });
    return total > 0 && dark / total > 0.6;
}

// splits a selector list on top-level commas only (ignores commas inside :not(), etc.)
function splitSelectors(sel) {
    const parts = [];
    let depth = 0, start = 0;
    for (let i = 0; i < sel.length; i++) {
        if (sel[i] === '(') depth++;
        else if (sel[i] === ')') depth--;
        else if (sel[i] === ',' && depth === 0) {
            parts.push(sel.slice(start, i).trim());
            start = i + 1;
        }
    }
    parts.push(sel.slice(start).trim());
    return parts;
}

function buildDarkBlock(root: postcss.Root, selector: string): string {
    const lines: string[] = [];
    root.walkRules((rule: Rule) => {
        if (rule.parent && (rule.parent as AtRule).name === 'keyframes') return;
        if (rule.selector.includes('#{')) return;
        // unresolved parent selector — happens when a top-level `&` relies on
        // cross-file @import context (this file is a partial meant to be
        // imported inside another file's selector block); can't safely
        // resolve that with file-local info, so skip rather than emit
        // invalid CSS like ".dark-theme &.tb-basic"
        if (rule.selector.includes('&')) {
            console.warn(`  ⚠ skipping unresolved selector: ${rule.selector}`);
            return;
        }

        const darkDecls: string[] = [];
        rule.each((node: ChildNode) => {
            if (node.type !== 'decl') return;
            const decl = node as Declaration;
            const role = roleOf(decl.prop);
            if (!role) return;
            const transformed = transformValue(decl.value, role);
            if (transformed) darkDecls.push(`    ${decl.prop}: ${transformed};`);
        });
        if (darkDecls.length === 0) return;

        const scoped = splitSelectors(rule.selector)
            .map(s => `${selector} ${s}`)
            .join(', ');

        lines.push(`  ${scoped} {`);
        lines.push(...darkDecls);
        lines.push(`  }`);
    });
    if (lines.length === 0) return '';
    return `\n// Auto-generated dark theme — do not edit manually\n${lines.join('\n')}\n`;
}
// CLI
const args = process.argv.slice(2);
const fileArg = args.find(a => !a.startsWith('--'));
const selectorIdx = args.indexOf('--selector');
const selector = selectorIdx >= 0 ? args[selectorIdx + 1] : '.dark-theme';

if (!fileArg || !existsSync(fileArg)) {
    console.error('Usage: dark-engine <file.scss> [--selector .dark-theme]');
    process.exit(1);
}

if (fileArg.includes('node_modules')) {
    console.error('Refusing to process node_modules file');
    process.exit(1);
}

const src = readFileSync(fileArg, 'utf8');

const marker = '// Auto-generated dark theme — do not edit manually';
const markerIdx = src.indexOf(marker);
const cleanSrc = markerIdx >= 0 ? src.slice(0, markerIdx).trimEnd() + '\n' : src;

// flatten SCSS nesting (&, descendant nesting, comma multiplication) into
// real top-level selectors first — walkRules alone never resolves ancestor chains
const { root } = postcss([postcssNested]).process(cleanSrc, { syntax: postcssScss });

if (isAlreadyDark(root)) process.exit(0);

const block = buildDarkBlock(root, selector);
if (block) {
    writeFileSync(fileArg, cleanSrc + block);
    console.log(`✓ ${fileArg}`);
}