#!/usr/bin/env node
/**
 * find-fx-directives.js
 *
 * Recursively scans a directory for Angular flex-layout directive usages
 * (fxLayout, fxLayoutGap, fxFlex, fxLayoutAlign, fxHide, fxShow, including
 * breakpoint suffixes like .xs / .gt-sm / .lt-lg) and prints every match
 * with its file and line number, plus a summary count per directive.
 *
 * Usage:
 *   node find-fx-directives.js [rootDir] [prefix]
 *
 *   rootDir  defaults to "src"
 *   prefix   defaults to "fx"  (e.g. pass "ng" to hunt for something else)
 *
 * Examples:
 *   node find-fx-directives.js
 *   node find-fx-directives.js src/app/modules/home/components/predictive-maintenance
 */

"use strict";

const fs = require("fs");
const path = require("path");

const SKIP_DIRS = new Set([
  "node_modules",
  ".git",
  "dist",
  "build",
  ".angular",
  "coverage",
]);
const EXTENSIONS = new Set([".html", ".ts"]);

const root = process.argv[2] || "src";
const prefix = process.argv[3] || "fx";

function escapeRegExp(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const FX_PATTERN = new RegExp(
  `\\b${escapeRegExp(prefix)}[A-Z][A-Za-z]*(?:\\.[a-zA-Z0-9-]+)?(?:\\s*=\\s*"[^"]*")?`,
  "g",
);

const results = []; // { file, line, text }
const counts = new Map();

function walk(dir) {
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch (err) {
    console.error(`Could not read directory "${dir}": ${err.message}`);
    return;
  }
  for (const entry of entries) {
    if (entry.isDirectory()) {
      if (!SKIP_DIRS.has(entry.name)) {
        walk(path.join(dir, entry.name));
      }
      continue;
    }
    const ext = path.extname(entry.name);
    if (!EXTENSIONS.has(ext)) continue;
    scanFile(path.join(dir, entry.name));
  }
}

function scanFile(filePath) {
  let content;
  try {
    content = fs.readFileSync(filePath, "utf8");
  } catch (err) {
    return;
  }
  const lines = content.split("\n");
  lines.forEach((lineText, idx) => {
    const matches = lineText.match(FX_PATTERN);
    if (!matches) return;
    for (const match of matches) {
      const trimmed = match.trim();
      results.push({ file: filePath, line: idx + 1, text: trimmed });
      const name = trimmed.split(/[.=]/)[0];
      counts.set(name, (counts.get(name) || 0) + 1);
      if (results.length > 10) {
        break;
      }
    }
  });
}

if (!fs.existsSync(root)) {
  console.error(`Root path "${root}" does not exist.`);
  process.exit(1);
}

walk(root);

if (results.length === 0) {
  console.log(`No "${prefix}*" directives found under "${root}".`);
  process.exit(0);
}

console.log(
  `Found ${results.length} "${prefix}*" directive usages under "${root}":\n`,
);
for (const r of results) {
  console.log(`${r.file}:${r.line}: ${r.text}`);
}

console.log("\n--- Summary by directive ---");
const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]);
const widest = Math.max(...sorted.map(([name]) => name.length));
for (const [name, count] of sorted) {
  console.log(`${name.padEnd(widest)}  ${count}`);
}

console.log(`\nFiles affected: ${new Set(results.map((r) => r.file)).size}`);
