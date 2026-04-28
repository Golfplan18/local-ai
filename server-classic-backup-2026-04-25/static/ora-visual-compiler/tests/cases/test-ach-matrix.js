/**
 * tests/cases/test-ach-matrix.js — WP-1.3f regression suite.
 *
 * Standalone: runs directly under Node with jsdom. Loads the compiler
 * core, the vendored Vega + Vega-Lite bundles, the ach-matrix renderer,
 * and the palettes module; then exercises:
 *
 *   ≥ 5 valid ACH specs:
 *     - simple 3×3 with one dominant hypothesis
 *     - 4×4 with credibility weights and weighted scoring
 *     - 3×3 where one evidence row is all NA (mostly NAs elsewhere)
 *     - 3-hypothesis tie after scoring
 *     - high-cardinality evidence set exercising all 6 cell values
 *
 *   ≥ 3 invalid specs:
 *     - missing cell → E_SCHEMA_INVALID with spec.matrix[...] path
 *     - non-diagnostic row → W_ACH_NONDIAGNOSTIC warning (not an error)
 *     - invalid cell value → E_SCHEMA_INVALID
 *
 * Dual-mode: also exports { label, run(ctx, record) } so the shared
 * run.js harness can invoke it, and provides a standalone main that
 * boots its own jsdom when launched as `node test-ach-matrix.js`.
 *
 * Exits non-zero on any failure when run standalone.
 */

'use strict';

const fs   = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

// ── Paths ──────────────────────────────────────────────────────────────────
const COMPILER_DIR = path.resolve(__dirname, '..', '..');
const VENDOR_VEGA  = path.join(COMPILER_DIR, 'vendor', 'vega', 'vega.min.js');
const VENDOR_VL    = path.join(COMPILER_DIR, 'vendor', 'vega-lite', 'vega-lite.min.js');

const read = (p) => fs.readFileSync(p, 'utf-8');

// ── Fixture factory ────────────────────────────────────────────────────────
function envelope(spec, overrides) {
  const base = {
    schema_version: '0.2',
    id: 'fig-test-ach-matrix',
    type: 'ach_matrix',
    mode_context: 'competing_hypotheses',
    relation_to_prose: 'visually_native',
    spec: spec,
    semantic_description: {
      level_1_elemental: 'Test ACH matrix fixture.',
      level_2_statistical: null,
      level_3_perceptual: null,
      level_4_contextual: null,
      short_alt: 'Test ACH matrix.',
      data_table_fallback: null,
    },
    title: 'Test ACH matrix',
  };
  return Object.assign(base, overrides || {});
}

// ── Valid cases ────────────────────────────────────────────────────────────
const validCases = [
  {
    label: 'simple 3×3, dominant H2',
    env: envelope({
      hypotheses: [
        { id: 'H1', label: 'Accident' },
        { id: 'H2', label: 'Insider' },
        { id: 'H3', label: 'External attacker' },
      ],
      evidence: [
        { id: 'E1', text: 'Logs show legitimate credentials used',
          credibility: 'H', relevance: 'H' },
        { id: 'E2', text: 'No external intrusion signature in IDS',
          credibility: 'H', relevance: 'H' },
        { id: 'E3', text: 'Data removed during business hours',
          credibility: 'M', relevance: 'M' },
      ],
      cells: {
        E1: { H1: 'I',  H2: 'CC', H3: 'II' },
        E2: { H1: 'N',  H2: 'C',  H3: 'II' },
        E3: { H1: 'C',  H2: 'CC', H3: 'I'  },
      },
      scoring_method: 'heuer_tally',
    }),
    expectLeading: 'H2',
    expectCellCount: 9,
    expectNonDiagnostic: 0,
  },
  {
    label: '4×4 with credibility weights, weighted scoring',
    env: envelope({
      hypotheses: [
        { id: 'A', label: 'Alpha' },
        { id: 'B', label: 'Bravo' },
        { id: 'C', label: 'Charlie' },
        { id: 'D', label: 'Delta' },
      ],
      evidence: [
        { id: 'e1', text: 'Finding 1', credibility: 'H', relevance: 'H' },
        { id: 'e2', text: 'Finding 2', credibility: 'M', relevance: 'H' },
        { id: 'e3', text: 'Finding 3', credibility: 'L', relevance: 'M' },
        { id: 'e4', text: 'Finding 4', credibility: 'H', relevance: 'H' },
      ],
      cells: {
        e1: { A: 'CC', B: 'N',  C: 'I',  D: 'II' },
        e2: { A: 'C',  B: 'C',  C: 'N',  D: 'I'  },
        e3: { A: 'N',  B: 'CC', C: 'II', D: 'N'  },
        e4: { A: 'C',  B: 'N',  C: 'I',  D: 'II' },
      },
      scoring_method: 'weighted',
    }),
    // Expected leading: Alpha (fewest inconsistencies, H-credibility
    // evidence mostly supports A).
    expectLeading: 'A',
    expectCellCount: 16,
    expectNonDiagnostic: 0,
  },
  {
    label: '3×3 with row of mostly NAs',
    env: envelope({
      hypotheses: [
        { id: 'X', label: 'X' },
        { id: 'Y', label: 'Y' },
        { id: 'Z', label: 'Z' },
      ],
      evidence: [
        { id: 'ev1', text: 'Relevant only to X', credibility: 'H', relevance: 'H' },
        { id: 'ev2', text: 'Mostly not applicable', credibility: 'M', relevance: 'L' },
        { id: 'ev3', text: 'Discriminating evidence', credibility: 'H', relevance: 'H' },
      ],
      cells: {
        ev1: { X: 'CC', Y: 'N', Z: 'I' },
        // ev2: two NA and one NA — fully non-diagnostic.
        ev2: { X: 'NA', Y: 'NA', Z: 'N' },
        ev3: { X: 'C',  Y: 'II', Z: 'N' },
      },
      scoring_method: 'heuer_tally',
    }),
    // ev2 is non-diagnostic (all N/NA).
    expectLeading: 'X',   // Y gets -2, Z gets -1, X gets 0 inconsistencies.
    expectCellCount: 9,
    expectNonDiagnostic: 1,
    expectNonDiagnosticIds: ['ev2'],
  },
  {
    label: 'leading-hypothesis tie between two',
    env: envelope({
      hypotheses: [
        { id: 'P', label: 'P' },
        { id: 'Q', label: 'Q' },
        { id: 'R', label: 'R' },
      ],
      evidence: [
        { id: 'fact1', text: 'Fact 1', credibility: 'H', relevance: 'H' },
        { id: 'fact2', text: 'Fact 2', credibility: 'H', relevance: 'H' },
      ],
      cells: {
        // P and Q both have zero inconsistencies; R has two. Tie between P/Q.
        fact1: { P: 'CC', Q: 'CC', R: 'II' },
        fact2: { P: 'C',  Q: 'C',  R: 'II' },
      },
      scoring_method: 'heuer_tally',
    }),
    expectLeading: 'P',        // deterministic tiebreak: first-in-input-order wins.
    expectCellCount: 6,
    expectNonDiagnostic: 0,
    expectTie: true,
    expectTiedWith: ['P', 'Q'],
  },
  {
    label: 'high-cardinality cell value set (all 6 values present)',
    env: envelope({
      hypotheses: [
        { id: 'alpha', label: 'Alpha' },
        { id: 'beta',  label: 'Beta' },
        { id: 'gamma', label: 'Gamma' },
      ],
      evidence: [
        { id: 'E_a', text: 'Strongly supporting / strongly against test',
          credibility: 'H', relevance: 'H' },
        { id: 'E_b', text: 'Mixed support',           credibility: 'M', relevance: 'M' },
        { id: 'E_c', text: 'Has one NA',              credibility: 'L', relevance: 'L' },
      ],
      cells: {
        E_a: { alpha: 'CC', beta: 'II', gamma: 'N' },
        E_b: { alpha: 'C',  beta: 'I',  gamma: 'N' },
        E_c: { alpha: 'NA', beta: 'N',  gamma: 'I' },
      },
      scoring_method: 'bayesian',
    }),
    // With bayesian (rule: highest) — alpha gets +3 (CC+C+NA=0), beta -3, gamma -1.
    expectLeading: 'alpha',
    expectCellCount: 9,
    expectNonDiagnostic: 0,
    expectAllCellClasses: ['CC', 'C', 'N', 'I', 'II', 'NA'],
  },
];

// ── Invalid cases ──────────────────────────────────────────────────────────
const invalidCases = [
  {
    label: 'missing cell — E_SCHEMA_INVALID',
    env: envelope({
      hypotheses: [
        { id: 'H1', label: 'H1' },
        { id: 'H2', label: 'H2' },
      ],
      evidence: [
        { id: 'e1', text: 'E1', credibility: 'H', relevance: 'H' },
      ],
      cells: {
        // Missing H2 cell for e1.
        e1: { H1: 'CC' },
      },
      scoring_method: 'heuer_tally',
    }),
    expectCode: 'E_SCHEMA_INVALID',
    expectPathContains: 'spec.matrix',
  },
  {
    label: 'non-diagnostic row — W_ACH_NONDIAGNOSTIC warning (render succeeds)',
    env: envelope({
      hypotheses: [
        { id: 'A', label: 'A' },
        { id: 'B', label: 'B' },
      ],
      evidence: [
        { id: 'e_diag', text: 'Diagnostic evidence', credibility: 'H', relevance: 'H' },
        { id: 'e_same', text: 'Same across hypotheses', credibility: 'H', relevance: 'H' },
      ],
      cells: {
        e_diag: { A: 'CC', B: 'II' },
        // Every cell is the same → non-diagnostic.
        e_same: { A: 'C', B: 'C' },
      },
      scoring_method: 'heuer_tally',
    }),
    expectWarning: 'W_ACH_NONDIAGNOSTIC',
    expectSuccess: true,  // Render proceeds; warning attached.
  },
  {
    label: 'invalid cell value "??" — E_SCHEMA_INVALID',
    env: envelope({
      hypotheses: [
        { id: 'H1', label: 'H1' },
        { id: 'H2', label: 'H2' },
      ],
      evidence: [
        { id: 'e1', text: 'E1', credibility: 'H', relevance: 'H' },
      ],
      cells: {
        e1: { H1: 'CC', H2: '??' },
      },
      scoring_method: 'heuer_tally',
    }),
    expectCode: 'E_SCHEMA_INVALID',
    expectPathContains: 'spec.matrix',
  },
];

// ── Standalone bootstrap (when run as `node test-ach-matrix.js`) ──────────
// Mirrors the approach in run.js: jsdom with runScripts: 'outside-only' and
// win.eval to drop sources into the window's global scope. This path avoids
// the UMD module-detection branch in vega-lite.min.js, which otherwise tries
// to `require('vega')` when the context has `exports`/`module` defined (as
// dom.getInternalVMContext() does).
function bootStandalone() {
  const dom = new JSDOM(
    '<!DOCTYPE html><html><head></head><body></body></html>',
    { runScripts: 'outside-only' }
  );
  const win = dom.window;

  win.structuredClone = globalThis.structuredClone ||
    ((v) => JSON.parse(JSON.stringify(v)));

  // Canvas mock so Vega's text measurement doesn't require the `canvas` npm pkg.
  win.HTMLCanvasElement.prototype.getContext = function () {
    return {
      measureText: (t) => ({ width: (t || '').length * 6 }),
      fillText: () => {}, save: () => {}, restore: () => {},
      scale: () => {}, translate: () => {}, rotate: () => {},
      beginPath: () => {}, closePath: () => {}, fillRect: () => {},
      strokeRect: () => {}, clearRect: () => {}, moveTo: () => {},
      lineTo: () => {}, stroke: () => {}, fill: () => {},
      arc: () => {}, rect: () => {},
      getImageData: () => ({ data: new Uint8ClampedArray(4) }),
      putImageData: () => {}, createImageData: () => ({ data: new Uint8ClampedArray(4) }),
      setTransform: () => {}, canvas: this,
    };
  };

  function loadScript(absPath) {
    win.eval(read(absPath));
  }

  loadScript(path.join(COMPILER_DIR, 'errors.js'));
  loadScript(path.join(COMPILER_DIR, 'validator.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'stub.js'));
  loadScript(path.join(COMPILER_DIR, 'dispatcher.js'));
  loadScript(path.join(COMPILER_DIR, 'index.js'));
  loadScript(path.join(COMPILER_DIR, 'palettes.js'));
  loadScript(VENDOR_VEGA);
  loadScript(VENDOR_VL);
  loadScript(path.join(COMPILER_DIR, 'renderers', 'vega-lite.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'ach-matrix.js'));

  return win;
}

// ── Assertion helpers (shared) ─────────────────────────────────────────────
const hasSvgRoot      = (s) => typeof s === 'string' && /<svg\b/i.test(s);
const hasClass        = (s, c) =>
  new RegExp('class="[^"]*\\b' + c.replace(/-/g, '\\-') + '\\b').test(s);
const hasAriaImg      = (s) => /role="img"/.test(s);
const hasAriaLabel    = (s) => /aria-label="[^"]+"/.test(s);
const hasInlineStyle  = (s) => /\sstyle="/.test(s) || /\sfill="/.test(s) ||
                               /\sstroke="/.test(s) || /\sfont-family="/.test(s);
const hasDataLeading  = (s, hid) =>
  new RegExp('data-ach-leading-hypothesis="' + hid + '"').test(s);
const hasCellId       = (s, eid, hid) =>
  new RegExp('id="ach-cell-' + eid + '-' + hid + '"').test(s);
const countMatches    = (s, re) => { const m = s.match(re); return m ? m.length : 0; };

// ── Runner ────────────────────────────────────────────────────────────────
async function runAll(win, record) {
  const OVC = win.OraVisualCompiler;

  if (!OVC._renderers || !OVC._renderers.achMatrix) {
    record('setup: ach-matrix renderer registered', false,
      'OraVisualCompiler._renderers.achMatrix missing');
    return;
  }
  record('setup: ach-matrix renderer registered', true);
  record('setup: ach_matrix dispatch off stub',
    OVC._dispatcher.isStub('ach_matrix') === false,
    'still on stub after load');

  // ── Unit tests: scoring + validation internals ─────────────────────────
  const internals = OVC._renderers.achMatrix._internals;

  // Heuer tally on a tiny matrix.
  {
    const spec = validCases[0].env.spec;
    const scoring = internals._scoreHypotheses(spec, 'heuer_tally');
    record('unit(scoring): heuer_tally identifies H2 as leading',
      scoring.leadingId === 'H2',
      'got ' + scoring.leadingId);
  }

  // Weighted scoring with credibility weights.
  {
    const spec = validCases[1].env.spec;
    const sW = internals._scoreHypotheses(spec, 'weighted');
    const sH = internals._scoreHypotheses(spec, 'heuer_tally');
    record('unit(scoring): weighted differs from heuer_tally on same matrix',
      JSON.stringify(sW.scores) !== JSON.stringify(sH.scores),
      'weighted=' + JSON.stringify(sW.scores) + ' heuer=' + JSON.stringify(sH.scores));
  }

  // Bayesian scoring — rule is "highest".
  {
    const spec = validCases[4].env.spec;
    const sB = internals._scoreHypotheses(spec, 'bayesian');
    record('unit(scoring): bayesian rule is highest',
      sB.rule === 'highest',
      'got rule=' + sB.rule);
    record('unit(scoring): bayesian leading is alpha on all-6-values fixture',
      sB.leadingId === 'alpha',
      'got ' + sB.leadingId);
  }

  // Diagnosticity: row of all-N/NA.
  {
    const nd = internals._validateInvariants(validCases[2].env.spec);
    record('unit(invariants): identifies ev2 as non-diagnostic',
      nd.nondiagnosticEvidenceIds.indexOf('ev2') !== -1,
      'ids=' + JSON.stringify(nd.nondiagnosticEvidenceIds));
  }

  // Missing cell detection.
  {
    const v = internals._validateInvariants(invalidCases[0].env.spec);
    const hasMissing = v.errors.some((e) =>
      e.code === 'E_SCHEMA_INVALID' && /missing/i.test(e.message) && /spec.matrix/.test(e.path));
    record('unit(invariants): missing cell → E_SCHEMA_INVALID with spec.matrix path',
      hasMissing,
      'errs=' + JSON.stringify(v.errors.map((e) => e.code + ':' + e.path)));
  }

  // Default scoring method when absent.
  {
    const spec = Object.assign({}, validCases[0].env.spec);
    delete spec.scoring_method;
    const s = internals._scoreHypotheses(spec, spec.scoring_method);
    record('unit(scoring): missing scoring_method falls back to heuer_tally',
      s.method === 'heuer_tally',
      'got ' + s.method);
  }

  // ── Valid-render tests ─────────────────────────────────────────────────
  for (const tc of validCases) {
    const label = 'valid ' + tc.label;
    try {
      const result = await OVC._renderers.achMatrix.render(tc.env);
      if (!result) {
        record(label, false, 'no result'); continue;
      }
      if (result.errors.length) {
        record(label, false, 'unexpected errors: ' +
          JSON.stringify(result.errors.map((e) => e.code + ':' + e.message)));
        continue;
      }
      if (!hasSvgRoot(result.svg)) {
        record(label, false, 'no <svg> root'); continue;
      }
      if (!hasClass(result.svg, 'ora-visual--ach_matrix')) {
        record(label, false, 'missing ora-visual--ach_matrix class'); continue;
      }
      if (!hasAriaImg(result.svg) || !hasAriaLabel(result.svg)) {
        record(label, false, 'missing role="img" / aria-label on root'); continue;
      }

      // Root <svg> tag itself must not carry inline appearance attrs.
      const rootTag = result.svg.match(/<svg\b[^>]*>/)[0];
      const bannedOnRoot = ['style=', 'fill=', 'stroke=', 'font-family=', 'font-size='];
      let rootFail = null;
      for (const b of bannedOnRoot) {
        if (rootTag.indexOf(b) !== -1) { rootFail = b; break; }
      }
      if (rootFail) {
        record(label, false, 'root <svg> still carries ' + rootFail);
        continue;
      }

      // Leading hypothesis carried on root as data attribute.
      if (!hasDataLeading(result.svg, tc.expectLeading)) {
        if (tc.expectTie) {
          // Leading may be either of the tied — check that at least one tied
          // hypothesis is marked leading.
          const someTiedLeads = tc.expectTiedWith.some(
            (h) => hasDataLeading(result.svg, h));
          if (!someTiedLeads) {
            record(label, false, 'no tied hypothesis marked leading; tied=' +
              tc.expectTiedWith.join(','));
            continue;
          }
        } else {
          record(label, false, 'missing data-ach-leading-hypothesis="' +
            tc.expectLeading + '"');
          continue;
        }
      }

      // Cell id presence check: each (evidence × hypothesis) pair has a
      // stable id in the SVG.
      const spec = tc.env.spec;
      let missingIds = [];
      for (let i = 0; i < spec.evidence.length; i++) {
        for (let j = 0; j < spec.hypotheses.length; j++) {
          const eId = spec.evidence[i].id;
          const hId = spec.hypotheses[j].id;
          if (!hasCellId(result.svg, eId, hId)) {
            missingIds.push(eId + '×' + hId);
          }
        }
      }
      if (missingIds.length) {
        record(label, false, 'missing cell ids: ' + missingIds.join(', '));
        continue;
      }

      // Count unique cell IDs — must equal expectCellCount and all be distinct.
      const cellIdMatches = result.svg.match(/id="ach-cell-[^"]+"/g) || [];
      const distinctIds = new Set(cellIdMatches);
      if (cellIdMatches.length !== tc.expectCellCount) {
        record(label, false, 'cell id count mismatch: expected ' +
          tc.expectCellCount + ', got ' + cellIdMatches.length);
        continue;
      }
      if (distinctIds.size !== cellIdMatches.length) {
        record(label, false, 'cell ids not unique: ' + cellIdMatches.length +
          ' total but only ' + distinctIds.size + ' distinct');
        continue;
      }

      // Non-diagnostic warning count.
      const ndWarnings = result.warnings.filter(
        (w) => w.code === 'W_ACH_NONDIAGNOSTIC');
      if (ndWarnings.length !== tc.expectNonDiagnostic) {
        record(label, false, 'non-diagnostic count mismatch: expected ' +
          tc.expectNonDiagnostic + ', got ' + ndWarnings.length);
        continue;
      }
      if (tc.expectNonDiagnosticIds) {
        for (const eid of tc.expectNonDiagnosticIds) {
          const found = ndWarnings.some((w) => w.path.indexOf(eid) !== -1);
          if (!found) {
            record(label, false, 'no non-diagnostic warning for ' + eid);
            continue;
          }
        }
      }

      // All-6-values cell class check.
      if (tc.expectAllCellClasses) {
        const missing = tc.expectAllCellClasses.filter(
          (v) => !hasClass(result.svg, 'ora-visual__ach-cell--' + v));
        if (missing.length) {
          record(label, false, 'missing cell value classes: ' + missing.join(', '));
          continue;
        }
      }

      record(label, true,
        'svg ' + result.svg.length + ' chars, warnings=' + result.warnings.length);
    } catch (err) {
      record(label, false, 'threw: ' + (err.stack || err.message || err));
    }
  }

  // ── Invalid-render tests ───────────────────────────────────────────────
  for (const tc of invalidCases) {
    const label = 'invalid ' + tc.label;
    try {
      const result = await OVC._renderers.achMatrix.render(tc.env);
      if (!result) {
        record(label, false, 'no result'); continue;
      }

      if (tc.expectSuccess) {
        // Expected: render proceeds + warning attached.
        if (result.errors.length) {
          record(label, false, 'unexpected errors: ' +
            JSON.stringify(result.errors.map((e) => e.code)));
          continue;
        }
        const hasWarning = result.warnings.some((w) => w.code === tc.expectWarning);
        if (!hasWarning) {
          record(label, false, 'expected warning ' + tc.expectWarning +
            ' not found; got ' + JSON.stringify(result.warnings.map((w) => w.code)));
          continue;
        }
        if (!hasSvgRoot(result.svg)) {
          record(label, false, 'expected non-empty svg on warning-only path');
          continue;
        }
        record(label, true, 'warning=' + tc.expectWarning);
        continue;
      }

      // Expected: error + empty svg.
      if (!result.errors.length) {
        record(label, false, 'expected errors but got none'); continue;
      }
      const codes = result.errors.map((e) => e.code);
      if (codes.indexOf(tc.expectCode) === -1) {
        record(label, false, 'expected ' + tc.expectCode + ' got ' + JSON.stringify(codes));
        continue;
      }
      if (tc.expectPathContains) {
        const hasPath = result.errors.some((e) =>
          e.path && e.path.indexOf(tc.expectPathContains) !== -1);
        if (!hasPath) {
          record(label, false, 'expected path containing "' + tc.expectPathContains +
            '" not found; got paths ' + JSON.stringify(result.errors.map((e) => e.path)));
          continue;
        }
      }
      if (result.svg !== '') {
        record(label, false, 'expected empty svg on error, got length=' + result.svg.length);
        continue;
      }
      record(label, true, 'code=' + tc.expectCode);
    } catch (err) {
      record(label, false, 'threw: ' + (err.stack || err.message || err));
    }
  }

  // ── Palette-module usage assertion ─────────────────────────────────────
  // The renderer must call palettes.diverging(n). We exercise this by
  // spy-patching the module and re-invoking the fixture that should trigger it.
  {
    const origDiverging = win.OraVisualCompiler.palettes.diverging;
    let calledWith = null;
    win.OraVisualCompiler.palettes.diverging = function (n, opts) {
      calledWith = { n, opts };
      return origDiverging.call(this, n, opts);
    };
    try {
      await OVC._renderers.achMatrix.render(validCases[0].env);
      record('palette: diverging(n) called with n>=5 for cell ramp',
        calledWith && calledWith.n >= 5,
        'calledWith=' + JSON.stringify(calledWith));
    } finally {
      win.OraVisualCompiler.palettes.diverging = origDiverging;
    }
  }
}

// ── Exports for run.js harness (when invoked as a case module) ────────────
module.exports = {
  label: 'ACH matrix renderer — 5 valid + 3 invalid + scoring unit tests',
  run: async function run(ctx, record) {
    // ctx.win may or may not have ach-matrix.js loaded; run.js currently
    // doesn't load high-tier renderers. Load it on demand into ctx.win.
    const win = ctx.win;
    if (!win.OraVisualCompiler._renderers ||
        !win.OraVisualCompiler._renderers.achMatrix) {
      try {
        win.eval(read(path.join(COMPILER_DIR, 'palettes.js')));
        win.eval(read(path.join(COMPILER_DIR, 'renderers', 'ach-matrix.js')));
      } catch (err) {
        record('setup: load ach-matrix renderer', false,
          'eval threw: ' + (err.message || err));
        return;
      }
    }
    await runAll(win, record);
  },
};

// ── Standalone main ───────────────────────────────────────────────────────
if (require.main === module) {
  (async function main() {
    console.log('test-ach-matrix.js — WP-1.3f');
    console.log('jsdom version: ' + require('jsdom/package.json').version);
    console.log('----------------------------------------');

    const win = bootStandalone();

    let passed = 0, failed = 0;
    const failures = [];
    function record(label, ok, detail) {
      if (ok) {
        passed += 1;
        console.log('PASS  ' + label + (detail ? '  (' + detail + ')' : ''));
      } else {
        failed += 1;
        failures.push({ label, detail });
        console.log('FAIL  ' + label + '  :: ' + (detail || ''));
      }
    }

    await runAll(win, record);

    console.log('----------------------------------------');
    console.log('passed: ' + passed);
    console.log('failed: ' + failed);
    if (failed > 0) {
      console.log('\nFailures:');
      failures.forEach((f) => console.log('  - ' + f.label + ': ' + f.detail));
      process.exit(1);
    }
    process.exit(0);
  })().catch((err) => {
    console.error('FATAL:', err);
    process.exit(2);
  });
}
