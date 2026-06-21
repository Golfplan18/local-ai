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

// jsdom doesn't implement SVG getBBox / getComputedTextLength / getPointAtLength.
// Mermaid's render() (layout) needs them. Mirror the polyfills used by
// tests/run.js and tools/render-envelope.js — including the minimum-size floor
// (width >= 10) so zero-width nodes don't collapse edge geometry and trip the
// "Could not find a suitable point for the given distance" layout error.
if (window.SVGElement && !window.SVGElement.prototype.getBBox) {
  window.SVGElement.prototype.getBBox = function () {
    const text = (this.textContent || '').length;
    return { x: 0, y: 0, width: Math.max(text * 6, 10), height: 14 };
  };
}
if (window.SVGElement && !window.SVGElement.prototype.getComputedTextLength) {
  window.SVGElement.prototype.getComputedTextLength = function () {
    return Math.max((this.textContent || '').length * 6, 10);
  };
}
if (window.SVGElement && !window.SVGElement.prototype.getScreenCTM) {
  window.SVGElement.prototype.getScreenCTM = function () {
    return { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0, inverse: function () { return this; } };
  };
}
if (window.SVGPathElement && !window.SVGPathElement.prototype.getTotalLength) {
  window.SVGPathElement.prototype.getTotalLength = function () { return 100; };
}
if (window.SVGPathElement && !window.SVGPathElement.prototype.getPointAtLength) {
  window.SVGPathElement.prototype.getPointAtLength = function (dist) {
    return { x: dist || 0, y: 0 };
  };
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

// Parse-failure cases that the repair loop should fix. These use DSL that
// genuinely breaks the Mermaid 11.x parser (a `render()` after `parse()` would
// throw), so the normalization pass must engage and emit W_DSL_REPAIRED.
const repairableCases = [
  {
    // Parens inside an unquoted square-bracket label → lexical 'PS' error.
    label: 'flowchart node label with parens (unquoted)',
    env: envelope('flowchart',
      'flowchart TD\n  A[Friction: Context-collapse (CS uses different UI)] --> B[End]'),
  },
  {
    // <br> + & + ':' + parens combined in one unquoted label.
    label: 'flowchart node label with <br>, &, colon and parens',
    env: envelope('flowchart',
      'flowchart TD\n  D[Create channel & page<br>Friction: queue (waits compound)] --> E[Ack]'),
  },
  {
    // Parens inside an unquoted diamond {..} decision node → parse error.
    label: 'flowchart diamond decision node with parens (unquoted)',
    env: envelope('flowchart',
      'flowchart TD\n  A{Resolvable (on-call alone)?} --> B[Apply fix]'),
  },
  {
    // Parens + ':' inside an unquoted subroutine [[..]] node → parse error.
    label: 'flowchart subroutine node with colon and parens (unquoted)',
    env: envelope('flowchart',
      'flowchart TD\n  A[[WAIT: gated (eng status)]] --> B[Next]'),
  },
  {
    // Malformed inline edge label: 4+ leading dashes before a quoted label.
    label: 'flowchart malformed inline edge label (X ---- "y" --> Z)',
    env: envelope('flowchart',
      'flowchart TD\n  CS2 ---- "Yes, system outage" --> CS3[Verify]'),
  },
  {
    // Semicolon in a sequence message terminates the statement → parse error.
    label: 'sequence message text containing a semicolon',
    env: envelope('sequence',
      'sequenceDiagram\n  AS->>User: Authenticate (skip if SSO session; MFA if policy)'),
  },
  {
    // Hyphenated state ids are invalid Mermaid identifiers.
    label: 'state diagram with hyphenated state ids (Past-Due, Won-Back)',
    env: envelope('state',
      'stateDiagram-v2\n  [*] --> Active\n  Active --> Past-Due : Payment Fail\n' +
      '  Past-Due --> Active : Recovery\n  Active --> Won-Back : Revival'),
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

function hasNativePaint(svg) {
  return /<style\b/i.test(svg) || /\sstyle="/.test(svg) ||
         /\sfill="/.test(svg) || /\sstroke="/.test(svg);
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
      if (!hasNativePaint(result.svg)) {
        report(label, false, 'Mermaid native styling was not preserved');
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

// Unit coverage for the dialect-aware normalization helpers (no Mermaid needed).
function runNormalizeUnit() {
  const I = OVC._renderers.mermaid._internals;
  const norm = I._normalizeDsl;
  const quote = I._quoteNodeLabels;

  const cases = [
    // ── Flowchart: special-char node-label quoting ──────────────────────────
    {
      label: 'parens inside square label get quoted',
      run: () => quote('  A[Friction (CS uses UI)] --> B[End]'),
      check: (o) => /A\["Friction \(CS uses UI\)"\]/.test(o) && /B\["End"\]/.test(o),
    },
    {
      label: '<br> in label is preserved (not HTML-escaped)',
      run: () => quote('  D[Create channel<br>more] --> E[Ack]'),
      check: (o) => /<br>/.test(o) && !/&lt;br&gt;/.test(o) && /D\["Create channel<br>more"\]/.test(o),
    },
    {
      label: '& in label is preserved verbatim inside quotes',
      run: () => quote('  D[page & escalate] --> E'),
      check: (o) => /D\["page & escalate"\]/.test(o),
    },
    {
      label: 'double-circle ((..)) label with colon gets quoted as one unit',
      run: () => quote('  C --> Z((End: Resolved via SLA))'),
      check: (o) => /Z\(\("End: Resolved via SLA"\)\)/.test(o),
    },
    {
      label: 'arrow tokens and pipe edge labels are NOT touched',
      run: () => quote('  B -->|No (P3/P4)| C[Route]'),
      check: (o) => /B -->\|No \(P3\/P4\)\| C\["Route"\]/.test(o),
    },
    {
      label: 'already-valid -- "label" --> edge form is left intact',
      run: () => norm('flowchart TD\n  B -- "No (P3/P4)" --> C[X]', 'flowchart'),
      check: (o) => /B -- "No \(P3\/P4\)" --> C\["X"\]/.test(o),
    },
    {
      label: 'malformed X ---- "label" --> Y normalized to -- "label" -->',
      run: () => norm('flowchart TD\n  CS2 ---- "Yes, outage" --> CS3[V]', 'flowchart'),
      check: (o) => /CS2 -- "Yes, outage" --> CS3/.test(o) && !/----/.test(o),
    },
    {
      label: 'subgraph title with spaces is quoted',
      run: () => norm('flowchart TD\n  subgraph CS [Customer Support]\n    A --> B\n  end', 'flowchart'),
      check: (o) => /subgraph CS \["Customer Support"\]/.test(o),
    },
    {
      label: 'malformed trailing class ... displayName ... line is dropped',
      run: () => norm('flowchart TD\n  A --> B\n  class OCE1N, OCE0 displayName exception', 'flowchart'),
      check: (o) => !/displayName/.test(o),
    },

    // ── Sequence: semicolon → comma in message text ─────────────────────────
    {
      label: 'semicolon in message text becomes a comma',
      run: () => norm('sequenceDiagram\n  AS->>User: skip if SSO; MFA if policy', 'sequence'),
      check: (o) => /skip if SSO, MFA if policy/.test(o) && !/SSO;/.test(o),
    },
    {
      label: 'parens and <br/> in sequence message are preserved',
      run: () => norm('sequenceDiagram\n  C->>B: redirect (302)<br/>to /authorize', 'sequence'),
      check: (o) => /\(302\)<br\/>/.test(o),
    },

    // ── State: hyphen/dot id sanitization + label-alias preservation ────────
    {
      label: 'hyphenated state id sanitized to underscore',
      run: () => norm('stateDiagram-v2\n  Active --> Past-Due : Payment Fail', 'state'),
      check: (o) => /Active --> Past_Due/.test(o) && !/--> Past-Due/.test(o),
    },
    {
      label: 'space+dot+hyphen state id (1.3 Past-Due) sanitized to single id',
      run: () => norm('stateDiagram-v2\n  Active --> 1.3 Past-Due : Payment Fail', 'state'),
      check: (o) => /Active --> S_1_3_Past_Due : Payment Fail/.test(o) &&
                    /state "1.3 Past-Due" as S_1_3_Past_Due/.test(o),
    },
    {
      label: 'sanitized state emits alias decl preserving original display name',
      run: () => norm('stateDiagram-v2\n  Active --> Past-Due : x\n  Past-Due --> Won-Back : y', 'state'),
      check: (o) => /state "Past-Due" as Past_Due/.test(o) && /state "Won-Back" as Won_Back/.test(o),
    },
    {
      label: 'state header (stateDiagram-v2), --> arrows and [*] are untouched',
      run: () => norm('stateDiagram-v2\n  [*] --> Active\n  Active --> Past-Due : x', 'state'),
      check: (o) => /^stateDiagram-v2/m.test(o) && /\[\*\] --> Active/.test(o) && /--> Past_Due/.test(o),
    },
  ];

  for (const c of cases) {
    let out, ok;
    try { out = c.run(); ok = c.check(out); }
    catch (e) { out = 'threw: ' + e; ok = false; }
    report('unit(normalize): ' + c.label, ok, ok ? '' : 'got: ' + JSON.stringify(out));
  }
}

// Render-level assertion: a sanitized state diagram must still SHOW the
// original hyphenated label (via the `state "..." as ..."` alias), not the
// underscore-mangled id.
async function runStateLabelPreservation() {
  const env = envelope('state',
    'stateDiagram-v2\n  [*] --> Active\n  Active --> Past-Due : Payment Fail\n' +
    '  Past-Due --> Won-Back : Revival');
  const label = 'state label preservation (Past-Due rendered, not Past_Due)';
  try {
    const result = await OVC._renderers.mermaid.render(env);
    if (!result || result.errors.length > 0) {
      report(label, false, 'render errored: ' + JSON.stringify(result && result.errors.map((e) => e.code)));
      return;
    }
    if (!looksLikeSvg(result.svg)) { report(label, false, 'no <svg> output'); return; }
    const showsHyphen = /Past-Due/.test(result.svg) && /Won-Back/.test(result.svg);
    if (!showsHyphen) {
      report(label, false, 'expected hyphenated labels in rendered SVG');
      return;
    }
    report(label, true);
  } catch (err) {
    report(label, false, 'threw: ' + (err && err.stack ? err.stack : err));
  }
}

// ── Go ────────────────────────────────────────────────────────────────────
(async function main() {
  console.log('test-mermaid.js — WP-1.2b');
  console.log('Mermaid version:', readFile(path.join(VENDOR_DIR, 'VERSION')).trim());
  console.log('----------------------------------------');

  runMechanicalUnit();
  runNormalizeUnit();
  await runValid();
  await runRepairable();
  await runStateLabelPreservation();
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
