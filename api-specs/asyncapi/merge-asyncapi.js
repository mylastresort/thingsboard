#!/usr/bin/env node
/**
 * Merges split AsyncAPI files into a single monolithic YAML document,
 * preserving $ref to named components (unlike `asyncapi bundle` which
 * inlines everything and produces anonymous schemas).
 *
 * Zero external dependencies — uses only Node.js built-ins.
 *
 * Usage: node merge-asyncapi.js <root.yaml> [output.yaml]
 *   If output is omitted, prints to stdout.
 */
const fs = require('fs');
const path = require('path');

const ROOT = process.argv[2];
const OUTPUT = process.argv[3];

if (!ROOT) {
  process.stderr.write('Usage: merge-asyncapi.js <root.yaml> [output.yaml]\n');
  process.exit(1);
}

const rootDir = path.dirname(path.resolve(ROOT));

// Parse an _index.yaml file: returns { Name: './Relative.yaml', ... }
function parseIndex(filePath) {
  const content = fs.readFileSync(filePath, 'utf8');
  const index = {};
  const re = /^(\S+):\s*\$ref:\s*['"]?(\.\/[^'"]+)['"]?\s*$/gm;
  let m;
  while ((m = re.exec(content)) !== null) {
    index[m[1]] = m[2];
  }
  return index;
}

// Build a map: absoluteFilePath → componentName
function buildFileToNameMap(indexFile, nameToRef) {
  const map = {};
  const baseDir = path.dirname(indexFile);
  for (const [name, ref] of Object.entries(nameToRef)) {
    const abs = path.resolve(baseDir, ref);
    map[abs] = name;
  }
  return map;
}

// Rewrite external $ref strings in text to internal $ref.
// Handles both inline: { $ref: '../schemas/Foo.yaml' } and array: - $ref: ...
function rewriteRefsInText(text, currentFile, schemaFileToName, messageFileToName) {
  return text.replace(
    /\$ref:\s*['"]?([^'"\s#][^'"]*\.yaml)['"]?/g,
    (match, refPath) => {
      const abs = path.resolve(path.dirname(currentFile), refPath);
      if (schemaFileToName[abs]) {
        return `$ref: '#/components/schemas/${schemaFileToName[abs]}'`;
      }
      if (messageFileToName[abs]) {
        return `$ref: '#/components/messages/${messageFileToName[abs]}'`;
      }
      return match;
    }
  );
}

// ── Read schema and message registries ──────────────────────────────────────

const schemasIndex = path.resolve(rootDir, 'schemas', '_index.yaml');
const messagesIndex = path.resolve(rootDir, 'messages', '_index.yaml');

const schemaNameToRef = parseIndex(schemasIndex);
const messageNameToRef = parseIndex(messagesIndex);

const schemaFileToName = buildFileToNameMap(schemasIndex, schemaNameToRef);
const messageFileToName = buildFileToNameMap(messagesIndex, messageNameToRef);

// ── Build components.messages block ─────────────────────────────────────────

const messagesBaseDir = path.dirname(messagesIndex);
const messageEntries = [];
for (const [name, ref] of Object.entries(messageNameToRef)) {
  const filePath = path.resolve(messagesBaseDir, ref);
  let content = fs.readFileSync(filePath, 'utf8');
  content = rewriteRefsInText(content, filePath, schemaFileToName, messageFileToName);
  // Trim trailing newlines then add one
  content = content.replace(/\n+$/, '');
  messageEntries.push(`    ${name}:\n${indent(content, 6)}`);
}

// ── Build components.schemas block ──────────────────────────────────────────

const schemasBaseDir = path.dirname(schemasIndex);
const schemaEntries = [];
for (const [name, ref] of Object.entries(schemaNameToRef)) {
  const filePath = path.resolve(schemasBaseDir, ref);
  let content = fs.readFileSync(filePath, 'utf8');
  content = rewriteRefsInText(content, filePath, schemaFileToName, messageFileToName);
  content = content.replace(/\n+$/, '');
  schemaEntries.push(`    ${name}:\n${indent(content, 6)}`);
}

// ── Read root spec and extract header + channels ────────────────────────────

let rootText = fs.readFileSync(path.resolve(ROOT), 'utf8');

// Remove the components section from root (everything after `components:`)
const componentsIdx = rootText.indexOf('\ncomponents:\n');
if (componentsIdx !== -1) {
  rootText = rootText.substring(0, componentsIdx);
}

// Rewrite $ref in the root (channels → messages)
rootText = rewriteRefsInText(rootText, path.resolve(ROOT), schemaFileToName, messageFileToName);

// Remove the trailing `_index.yaml` refs that were already rewritten to internal refs
// They shouldn't appear in the root since we removed the components section

// ── Assemble ────────────────────────────────────────────────────────────────

const output = rootText
  + '\ncomponents:\n'
  + '  messages:\n'
  + messageEntries.join('\n')
  + '\n'
  + '  schemas:\n'
  + schemaEntries.join('\n')
  + '\n';

if (OUTPUT) {
  fs.writeFileSync(OUTPUT, output, 'utf8');
  process.stderr.write(`Merged AsyncAPI written to ${OUTPUT}\n`);
} else {
  process.stdout.write(output);
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function indent(text, spaces) {
  const pad = ' '.repeat(spaces);
  return text.split('\n').map(line => line.length > 0 ? pad + line : line).join('\n');
}
