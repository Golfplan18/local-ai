/**
 * test-mermaid.js — WP-1.2b regression suite.
 *
 * Standalone: runs directly under Node with jsdom. Does not depend on a
 * WP-1.2a harness. If a harness is supplied later this file still runs
 * (it will simply duplicate bootstrap that the harness also does).
 *
 * Usage:
 *   node test-mermaid.js
 *
 * Exits non-zero on any failure.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { JSDOM } = require('jsdom');

// ── Paths ──────────────────────────────────────────────────────────────────
const COMPILER_DIR = path.resolve(__dirname, '..', '..');
const VENDOR_DIR   = path.join(COMPILER_DIR, 'vendor', 'mermaid');

function readFile(p) {
  return fs.readFileSync(p, 'utf-8');
}

// ── jsdom bootstrap ────────────────────────────────────────────────────────
// We need: window, document, DOMParser, XMLSerializer, Promise timers.
const dom = new JSDOM('<!doctype html><html><head></head><body></body></html>', {
  url: 'http://localhost/',
  pretendToBeVisual: true,
  runScripts: 'outside-only',
});

const { window } = dom;

// Expose a minimal globalThis proxy so Mermaid's UMD (which assigns
// globalThis.mermaid) lands on the jsdom window.
window.globalThis = window;
window.console = console;

// Patch missing browser APIs Mermaid expects.
if (!window.getComputedStyle) {
  window.getComputedStyle = () => ({ getPropertyValue: () => '' });
}
if (!window.matchMedia) {
  window.matchMedia = () => ({ matches: false, addListener: () => {}, removeListener: () => {} });
}
// Mermaid calls requestAnimationFrame in some diagram types.
if (!window.requestAnimationFrame) {
  window.requestAnimationFrame = (cb) => setTimeout(cb, 16);
}

// ── Load the compiler scripts into the jsdom window ────────────────────────
const files = [
  path.join(COMPILER_DIR, 'errors.js'),
  path.join(COMPILER_DIR, 'validator.js'),
  path.join(COMPILER_DIR, 'renderers', 'stub.js'),
  path.join(COMPILER_DIR, 'dispatcher.js'),
  path.join(COMPILER_DIR, 'index.js'),
];

const ctx = dom.getInternalVMContext();
for (const f of files) {
  const code = readFile(f);
  vm.runInContext(code, ctx, { filename: f });
}

// ── Load the vendored Mermaid into the same context ────────────────────────
// mermaid.min.js is large; it assigns globalThis.mermaid at the end.
const mermaidCode = readFile(path.join(VENDOR_DIR, 'mermaid.min.js'));
vm.runInContext(mermaidCode, ctx, { filename: path.join(VENDOR_DIR, 'mermaid.min.js') });

if (typeof window.mermaid === 'undefined') {
  console.error('FAIL: mermaid did not attach to window after loading vendor bundle.');
  process.exit(1);
}

// ── Load the renderer ──────────────────────────────────────────────────────
const rendererCode = readFile(path.join(COMPILER_DIR, 'renderers', 'mermaid.js'));
vm.runInContext(rendererCode, ctx, { filename: path.join(COMPILER_DIR, 'renderers', 'mermaid.js') });

const OVC = window.OraVisualCompiler;
if (!OVC || !OVC._renderers || !OVC._renderers.mermaid) {
  console.error('FAIL: OraVisualCompiler._renderers.mermaid is not exposed after loading renderer.');
  process.exit(1);
}

// ── Test cases ─────────────────────────────────────────────────────────────
function envelope(type, dsl, title) {
  return {
    schema_version: '0.2',
    id: 'fig-test-' + type,
    type: type,
    mode_context: 'test',
    relation_to_prose: 'integrated',
    spec: { dialect: type, dsl: dsl },
    semantic_description: {
      level_1_elemental: 'test fixture',
      level_2_statistical: null,
      level_3_perceptual: null,
      level_4_contextual: null,
      short_alt: 'test fixture',
      data_table_fallback: null,
    },
    title: title || ('Test ' + type),
  };
}

// Three valid specs per dialect — 9 valid total.
const validCases = [
  // sequence
  envelope('sequence', 'sequenceDiagram\n  Alice->>Bob: Hello\n  Bob-->>Alice: Hi'),
  envelope('sequence',
    'sequenceDiagram\n  participant C as Client\n  participant S as Server\n' +
    '  C->>S: GET /users\n  S-->>C: 200 OK'),
  envelope('sequence',
    'sequenceDiagram\n  User->>API: login\n  API->>DB: query\n  DB-->>API: rows\n  API-->>User: token'),

  // flowchart
  envelope('flowchart', 'flowchart TD\n  A[Start] --> B{OK?}\n  B -->|yes| C[End]\n  B -->|no| A'),
  envelope('flowchart', 'flowchart LR\n  A --> B --> C\n  C --> D'),
  envelope('flowchart',
    'flowchart TD\n  subgraph lane1\n    X1 --> X2\n  end\n  subgraph lane2\n    Y1 --> Y2\n  end\n  X2 --> Y1'),

  // state
  envelope('state', 'stateDiagram-v2\n  [*] --> Idle\n  Idle --> Running\n  Running --> [*]'),
  envelope('state',
    'stateDiagram-v2\n  [*] --> S1\n  S1 --> S2 : event\n  S2 --> S3\n  S3 --> [*]'),
  envelope('state',
    'stateDiagram-v2\n  [*] --> Off\n  Off --> On : power\n  On --> Off : power\n  On --> Error : fault\n  Error --> [*]'),
];

// Parse-failure cases that the repair loop should fix.
const repairableCases = [
  {
    label: 'flowchart with reserved word "end" as label',
    env: envelope('flowchart', 'flowchart TD\n  A[Start] --> B[end]\n  B --> C[Done]'),
  },
  {
    label: 'flowchart with unescaped < in label',
    env: envelope('flowchart', 'flowchart TD\n  A[Count<10] --> B[Increment]\n  B --> A'),
  },
  {
    label: 'flowchart with malformed long arrow ---->',
    env: envelope('flowchart', 'flowchart TD\n  A[Start] ----> B[End]'),
  },
  {
    label: 'flowchart with label containing spaces (no quotes)',
    env: envelope('flowchart', 'flowchart TD\n  A[Start of pipeline] --> B[End of pipeline]'),
  },
];

// Unfixable case — garbage that no repair can rescue.
const unfixableCases = [
  {
    label: 'random garbage DSL',
    env: envelope('flowchart', '$$$ !!! @@@ this is not mermaid at all ???'),
  },
];

// ── Runner ─────────────────────────────────────────────────────────────────
let passed = 0;
let failed = 0;
const failures = [];

function report(label, ok, detail) {
  if (ok) {
    passed += 1;
    console.log('PASS  ' + label);
  } else {
    failed += 1;
    failures.push({ label, detail });
    console.log('FAIL  ' + label + '  :: ' + detail);
  }
}

function looksLikeSvg(s) {
  if (typeof s !== 'string' || s.length === 0) return false;
  // Must contain an <svg ... > root.
  return /<svg[\s>]/i.test(s);
}

function hasOraClass(svg, type) {
  return /class="[^"]*\bora-visual\b[^"]*"/.test(svg)
      && new RegExp('class="[^"]*\\bora-visual--' + type + '\\b[^"]*"').test(svg);
}

function hasInlineStyle(svg) {
  // Our post-processor should strip style="..." attributes.
  return /\sstyle="/.test(svg);
}

async function runValid() {
  for (const env of validCases) {
    const label = 'valid ' + env.type + ' #' + env.id;
    try {
      const result = await OVC._renderers.mermaid.render(env);
      if (!result || result.errors.length > 0) {
        report(label, false, 'unexpected errors: ' + JSON.stringify(result && result.errors));
        continue;
      }
      if (!looksLikeSvg(result.svg)) {
        report(label, false, 'no <svg> in output');
        continue;
      }
      if (!hasOraClass(result.svg, env.type)) {
        report(label, false, 'missing ora-visual / ora-visual--' + env.type + ' class on root');
        continue;
      }
      if (hasInlineStyle(result.svg)) {
        report(label, false, 'inline style= attribute not stripped');
        continue;
      }
      if (result.warnings.length > 0) {
        report(label, false, 'unexpected warnings on valid input: ' +
          JSON.stringify(result.warnings.map((w) => w.code)));
        continue;
      }
      report(label, true);
    } catch (err) {
      report(label, false, 'threw: ' + (err && err.stack ? err.stack : err));
    }
  }
}

async function runRepairable() {
  for (const tc of repairableCases) {
    const label = 'repair ' + tc.label;
    try {
      const result = await OVC._renderers.mermaid.render(tc.env);
      if (!result) { report(label, false, 'no result object'); continue; }
      if (result.errors.length > 0) {
        // If errors, confirm the repair loop TRIED (warnings should include repair failure).
        // For these cases we EXPECT success, so errors are a failure.
        report(label, false, 'repair should have succeeded; got errors: ' +
          JSON.stringify(result.errors.map((e) => e.code)));
        continue;
      }
      if (!looksLikeSvg(result.svg)) {
        report(label, false, 'no <svg> in repaired output');
        continue;
      }
      const hasRepairWarning = result.warnings.some((w) => w.code === 'W_DSL_REPAIRED');
      if (!hasRepairWarning) {
        report(label, false, 'missing W_DSL_REPAIRED warning (repair may not have engaged)');
        continue;
      }
      report(label, true);
    } catch (err) {
      report(label, false, 'threw: ' + (err && err.stack ? err.stack : err));
    }
  }
}

async function runUnfixable() {
  for (const tc of unfixableCases) {
    const label = 'unfixable ' + tc.label;
    try {
      const result = await OVC._renderers.mermaid.render(tc.env);
      if (!result) { report(label, false, 'no result object'); continue; }
      if (result.errors.length === 0) {
        report(label, false, 'expected errors but got none');
        continue;
      }
      const hasParseErr = result.errors.some((e) => e.code === 'E_DSL_PARSE');
      if (!hasParseErr) {
        report(label, false, 'expected E_DSL_PARSE, got ' +
          JSON.stringify(result.errors.map((e) => e.code)));
        continue;
      }
      if (result.svg !== '') {
        report(label, false, 'expected empty svg on unfixable failure, got length=' + result.svg.length);
        continue;
      }
      const hasRepairFailedWarning = result.warnings.some((w) => w.code === 'W_DSL_REPAIR_FAILED');
      if (!hasRepairFailedWarning) {
        report(label, false, 'missing W_DSL_REPAIR_FAILED warning');
        continue;
      }
      report(label, true);
    } catch (err) {
      report(label, false, 'threw: ' + (err && err.stack ? err.stack : err));
    }
  }
}

// Smoke check on the mechanical-fix helper (doesn't need Mermaid).
function runMechanicalUnit() {
  const fix = OVC._renderers.mermaid._internals._mechanicalFixes;

  const cases = [
    {
      label: 'reserved word "end" in brackets is quoted',
      input: 'flowchart TD\n  A --> B[end]',
      check: (out) => /B\["end"\]/.test(out),
    },
    {
      label: 'spaces inside brackets are quoted',
      input: 'flowchart TD\n  A[Hello world] --> B',
      check: (out) => /A\["Hello world"\]/.test(out),
    },
    {
      label: '< inside already-quoted label is escaped',
      input: 'flowchart TD\n  A["Count < 10"] --> B',
      check: (out) => /Count &lt; 10/.test(out),
    },
    {
      label: 'long arrow ----> normalized to -->',
      input: 'flowchart TD\n  A ----> B',
      check: (out) => /A --> B/.test(out) && !/---->/.test(out),
    },
  ];
  for (const c of cases) {
    const out = fix(c.input);
    const ok = c.check(out);
    report('unit(fixes): ' + c.label, ok, ok ? '' : 'got: ' + JSON.stringify(out));
  }
}

// ── Go ────────────────────────────────────────────────────────────────────
(async function main() {
  console.log('test-mermaid.js — WP-1.2b');
  console.log('Mermaid version:', readFile(path.join(VENDOR_DIR, 'VERSION')).trim());
  console.log('----------------------------------------');

  runMechanicalUnit();
  await runValid();
  await runRepairable();
  await runUnfixable();

  console.log('----------------------------------------');
  console.log('Result: ' + passed + ' passed / ' + (passed + failed) + ' total  (' + failed + ' failed)');
  if (failed > 0) {
    console.log('\nFailures:');
    for (const f of failures) console.log('  - ' + f.label + ' :: ' + f.detail);
    process.exit(1);
  }
  process.exit(0);
})().catch((e) => {
  console.error('Harness crashed:', e && e.stack ? e.stack : e);
  process.exit(2);
});
