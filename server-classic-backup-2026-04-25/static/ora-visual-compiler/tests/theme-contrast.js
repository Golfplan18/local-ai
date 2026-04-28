#!/usr/bin/env node
/**
 * tests/theme-contrast.js
 *
 * Reads ../ora-visual-theme.css, extracts the color-related CSS custom
 * properties (light mode + dark mode overrides), and asserts WCAG 2.2
 * contrast ratios using the WCAG relative-luminance formula.
 *
 * Thresholds per WCAG 2.2:
 *   - Body text on background (SC 1.4.3 AA):       ≥ 4.5:1
 *   - Gridline on background (SC 1.4.11 AA):       ≥ 3:1  (intentionally just-over)
 *   - Categorical palette colours (SC 1.4.11 AA):  ≥ 3:1  each slot vs background
 *   - Highlight colour (SC 1.4.11 AA):             ≥ 3:1
 *
 * Usage:
 *   node theme-contrast.js
 *
 * Exits 0 on all-pass, 1 on any failure. One line per check.
 *
 * Run from:    ~/ora/server/static/ora-visual-compiler/tests
 * README blurb:
 *
 *   $ cd ~/ora/server/static/ora-visual-compiler/tests
 *   $ node theme-contrast.js
 *   PASS  light  body text  #1A1E24 on #FCFCFA    ratio 15.92 ≥ 4.5
 *   ...
 *
 * This test has no dependencies outside Node's standard library.
 */

'use strict';

const fs   = require('fs');
const path = require('path');

// ───────────────────────────────────────────────────────────────────────────
// WCAG relative luminance + contrast
// Formula: https://www.w3.org/TR/WCAG22/#dfn-relative-luminance
// ───────────────────────────────────────────────────────────────────────────

function hexToRgb(hex) {
  const h = hex.replace('#', '').trim();
  if (h.length !== 6) throw new Error(`Bad hex color: ${hex}`);
  return {
    r: parseInt(h.substring(0, 2), 16),
    g: parseInt(h.substring(2, 4), 16),
    b: parseInt(h.substring(4, 6), 16),
  };
}

function srgbToLinear(c8) {
  const c = c8 / 255;
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

function relativeLuminance(hex) {
  const { r, g, b } = hexToRgb(hex);
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b);
}

function contrastRatio(hexA, hexB) {
  const la = relativeLuminance(hexA);
  const lb = relativeLuminance(hexB);
  const lighter = Math.max(la, lb);
  const darker  = Math.min(la, lb);
  return (lighter + 0.05) / (darker + 0.05);
}

// ───────────────────────────────────────────────────────────────────────────
// CSS custom-property extraction
// ───────────────────────────────────────────────────────────────────────────

const CSS_PATH = path.join(__dirname, '..', 'ora-visual-theme.css');
const cssText  = fs.readFileSync(CSS_PATH, 'utf8');

/**
 * Parse a :root { ... } block. Returns a map of {propertyName: value}.
 * Start index is the position of the opening '{'.
 */
function parseBlockAt(src, openBraceIdx) {
  let depth = 0;
  let start = openBraceIdx;
  for (let i = openBraceIdx; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') {
      depth--;
      if (depth === 0) {
        const body = src.substring(start + 1, i);
        return { body, endIdx: i };
      }
    }
  }
  throw new Error('Unterminated block in CSS');
}

function parseCustomProperties(body) {
  const props = {};
  const re = /(--[a-z0-9-]+)\s*:\s*([^;]+);/gi;
  let m;
  while ((m = re.exec(body)) !== null) {
    props[m[1]] = m[2].trim();
  }
  return props;
}

// Extract the first :root { ... } (light mode)
const lightRootIdx = cssText.search(/:root\s*\{/);
if (lightRootIdx < 0) { console.error('no :root block found'); process.exit(2); }
const lightOpen = cssText.indexOf('{', lightRootIdx);
const lightBlock = parseBlockAt(cssText, lightOpen);
const lightProps = parseCustomProperties(lightBlock.body);

// Extract the dark-mode :root (inside the prefers-color-scheme rule)
const darkMediaIdx = cssText.indexOf('@media (prefers-color-scheme: dark)');
let darkProps = {};
if (darkMediaIdx >= 0) {
  // Find the nested :root inside the media block
  const nestedRoot = cssText.indexOf(':root', darkMediaIdx);
  if (nestedRoot >= 0) {
    const nestedOpen = cssText.indexOf('{', nestedRoot);
    darkProps = parseCustomProperties(parseBlockAt(cssText, nestedOpen).body);
  }
}

// ───────────────────────────────────────────────────────────────────────────
// Hex validation — we only verify swatches that are literal hex values.
// (A theme could reference another var via var(--x); we skip those cleanly.)
// ───────────────────────────────────────────────────────────────────────────

function isHex(v) {
  return /^#[0-9a-fA-F]{6}$/.test(v);
}

function resolve(props, key) {
  const v = props[key];
  if (v === undefined) return undefined;
  if (isHex(v)) return v;
  // Fall back: no var() resolution; if the value isn't a hex, skip check.
  return undefined;
}

// ───────────────────────────────────────────────────────────────────────────
// Contrast checks
// ───────────────────────────────────────────────────────────────────────────

const CATEGORICAL_KEYS = [
  '--ora-vis-cat-1', '--ora-vis-cat-2', '--ora-vis-cat-3', '--ora-vis-cat-4',
  '--ora-vis-cat-5', '--ora-vis-cat-6', '--ora-vis-cat-7', '--ora-vis-cat-8',
];

const CHECKS = [
  // label,               fgKey,                      bgKey,              threshold
  ['body text',           '--ora-vis-text',           '--ora-vis-bg',     4.5],
  ['body text (surface)', '--ora-vis-text',           '--ora-vis-surface',4.5],
  ['secondary text',      '--ora-vis-text-secondary', '--ora-vis-bg',     4.5],
  ['axis',                '--ora-vis-axis',           '--ora-vis-bg',     3.0],
  ['gridline',            '--ora-vis-gridline',       '--ora-vis-bg',     3.0],
  ['highlight',           '--ora-vis-highlight',      '--ora-vis-bg',     3.0],
  ['muted',               '--ora-vis-muted',          '--ora-vis-bg',     3.0],
];

for (const k of CATEGORICAL_KEYS) {
  CHECKS.push([`categorical ${k.replace('--ora-vis-', '')}`, k, '--ora-vis-bg', 3.0]);
}

let failures = 0;
let total    = 0;

function runCheckSet(modeName, props) {
  for (const [label, fgKey, bgKey, threshold] of CHECKS) {
    const fg = resolve(props, fgKey);
    const bg = resolve(props, bgKey);
    total++;
    if (!fg || !bg) {
      console.log(`SKIP  ${modeName.padEnd(5)}  ${label.padEnd(20)}  ` +
        `(missing or var-referenced: fg=${props[fgKey] || '?'}, bg=${props[bgKey] || '?'})`);
      continue;
    }
    const ratio = contrastRatio(fg, bg);
    const pass  = ratio >= threshold;
    if (!pass) failures++;
    console.log(
      `${pass ? 'PASS' : 'FAIL'}  ${modeName.padEnd(5)}  ${label.padEnd(20)}  ` +
      `${fg} on ${bg}  ratio ${ratio.toFixed(2)} ${pass ? '≥' : '<'} ${threshold}`
    );
  }
}

// For dark mode we need to fall back to light values for keys not overridden.
const darkMerged = Object.assign({}, lightProps, darkProps);

console.log('─ ora-visual-theme.css WCAG 2.2 AA contrast check ─');
console.log('');
console.log('── LIGHT MODE ──');
runCheckSet('light', lightProps);
console.log('');
console.log('── DARK MODE ──');
runCheckSet('dark', darkMerged);

console.log('');
console.log(`Result: ${total - failures}/${total} checks passed, ${failures} failed.`);

process.exit(failures === 0 ? 0 : 1);
