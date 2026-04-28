/**
 * tests/cases/test-causal-loop-diagram.js — WP-1.3a regression suite.
 *
 * This module follows the run.js case-file convention used by
 * test-vega-lite.js: export `{ label, run(ctx, record) }`. When invoked
 * as a case file, `ctx.win` is a jsdom window that has already loaded the
 * compiler core. We additionally load d3 and the CLD renderer into that
 * window before running fixtures.
 *
 * Standalone usage is also supported: `node test-causal-loop-diagram.js`
 * boots its own jsdom window, wires dependencies, and runs the same
 * fixtures. The standalone path is the primary one for WP-1.3a since the
 * top-level run.js does not yet include this case file in its manifest.
 *
 * Assertions per valid case:
 *   - SVG non-empty
 *   - SVG root <svg> carries class "ora-visual ora-visual--causal_loop_diagram"
 *   - SVG root has role="img" and aria-label
 *   - Every declared variable has a <g id="cld-node-<id>">
 *   - Every declared link has a <path id="cld-edge-<from>-<to>"> with polarity class
 *   - Every link has a polarity label (+ or − glyph) near its midpoint
 *   - Every declared loop has a <g id="cld-loop-<loop.id>"> with R/B annotation
 *   - <defs> contains exactly two markers: one for each polarity
 *
 * Assertions per invalid case:
 *   - errors[] contains the expected E_* code
 *   - svg === ''
 */

'use strict';

const fs   = require('fs');
const path = require('path');

// ── Fixture builder ──────────────────────────────────────────────────────────
function envelope(spec, overrides) {
  const base = {
    schema_version: '0.2',
    id: 'fig-test-cld',
    type: 'causal_loop_diagram',
    mode_context: 'root_cause_analysis',
    relation_to_prose: 'integrated',
    spec: spec,
    semantic_description: {
      level_1_elemental: 'Test CLD fixture',
      level_2_statistical: 'Test CLD with 2 nodes and 1 edge.',
      level_3_perceptual: 'Simple fixture for harness coverage.',
      level_4_contextual: null,
      short_alt: 'test causal loop diagram',
      data_table_fallback: null,
    },
    title: 'Test CLD',
  };
  return Object.assign(base, overrides || {});
}

// ── Valid fixtures (≥ 5) ─────────────────────────────────────────────────────
//
// Five hand-written CLDs covering: simple 2-loop reinforcing, single
// balancing loop, 3-variable circuit, shared-variable loops, allow_isolated.

function validFixtures() {
  return [
    // 1. Simple 2-node reinforcing loop: A → B → A, both +.
    {
      label: '2-node reinforcing loop (A ⇌ B, both +)',
      env: envelope({
        variables: [
          { id: 'A', label: 'Adoption' },
          { id: 'B', label: 'Network effect' },
        ],
        links: [
          { from: 'A', to: 'B', polarity: '+' },
          { from: 'B', to: 'A', polarity: '+' },
        ],
        loops: [
          { id: 'R1', type: 'R', members: ['A', 'B'], label: 'Network flywheel' },
        ],
      }),
      expectNodes: 2,
      expectEdges: 2,
      expectLoops: 1,
      expectLoopTypes: ['R'],
    },

    // 2. Single balancing loop (3-variable circuit with one '-').
    // V → T (+) → F (+) → V (-): one '-' → odd → B.
    {
      label: '3-variable balancing loop (V→T→F→V, one negative)',
      env: envelope({
        variables: [
          { id: 'V', label: 'Velocity' },
          { id: 'T', label: 'Tech debt' },
          { id: 'F', label: 'Fires' },
        ],
        links: [
          { from: 'V', to: 'T', polarity: '+' },
          { from: 'T', to: 'F', polarity: '+' },
          { from: 'F', to: 'V', polarity: '-' },
        ],
        loops: [
          { id: 'B1', type: 'B', members: ['V', 'T', 'F'], label: 'Debt balances velocity' },
        ],
      }),
      expectNodes: 3,
      expectEdges: 3,
      expectLoops: 1,
      expectLoopTypes: ['B'],
    },

    // 3. 3-variable circuit with all-positive links = reinforcing.
    {
      label: '3-variable reinforcing circuit (all +)',
      env: envelope({
        variables: [
          { id: 'S', label: 'Sales' },
          { id: 'R', label: 'Revenue' },
          { id: 'M', label: 'Marketing spend' },
        ],
        links: [
          { from: 'S', to: 'R', polarity: '+' },
          { from: 'R', to: 'M', polarity: '+' },
          { from: 'M', to: 'S', polarity: '+' },
        ],
        loops: [
          { id: 'R1', type: 'R', members: ['S', 'R', 'M'], label: 'Growth engine' },
        ],
      }),
      expectNodes: 3,
      expectEdges: 3,
      expectLoops: 1,
      expectLoopTypes: ['R'],
    },

    // 4. Shared-variable loops: one node appears in two loops.
    // Loops: R1 = [A,B], B1 = [A,C].
    // Edges: A→B (+), B→A (+)         → R1 (0 negatives, even → R)
    //        A→C (+), C→A (-)         → B1 (1 negative, odd → B)
    {
      label: 'Shared-variable loops (A in both R1 and B1)',
      env: envelope({
        variables: [
          { id: 'A', label: 'Productivity' },
          { id: 'B', label: 'Skills' },
          { id: 'C', label: 'Burnout' },
        ],
        links: [
          { from: 'A', to: 'B', polarity: '+' },
          { from: 'B', to: 'A', polarity: '+' },
          { from: 'A', to: 'C', polarity: '+' },
          { from: 'C', to: 'A', polarity: '-' },
        ],
        loops: [
          { id: 'R1', type: 'R', members: ['A', 'B'], label: 'Skill flywheel' },
          { id: 'B1', type: 'B', members: ['A', 'C'], label: 'Burnout brake' },
        ],
      }),
      expectNodes: 3,
      expectEdges: 4,
      expectLoops: 2,
      expectLoopTypes: ['R', 'B'],
    },

    // 5. allow_isolated=true with an orphan node that should not warn.
    // A → B → A is a 2-node + loop; D is isolated.
    {
      label: 'allow_isolated permits an orphan',
      env: envelope({
        variables: [
          { id: 'A', label: 'Alpha' },
          { id: 'B', label: 'Beta' },
          { id: 'D', label: 'Detached observation' },
        ],
        links: [
          { from: 'A', to: 'B', polarity: '+' },
          { from: 'B', to: 'A', polarity: '+' },
        ],
        loops: [
          { id: 'R1', type: 'R', members: ['A', 'B'], label: 'Alpha/Beta loop' },
        ],
        allow_isolated: true,
      }),
      expectNodes: 3,          // D is still a declared node
      expectEdges: 2,
      expectLoops: 1,
      expectLoopTypes: ['R'],
      expectNoOrphanWarning: true,
    },
  ];
}

// ── Invalid fixtures (≥ 3) ───────────────────────────────────────────────────

function invalidFixtures() {
  return [
    // Declared loop that is not a cycle in the graph: edge C→A missing.
    {
      label: 'declared loop members not connected (missing edge)',
      env: envelope({
        variables: [
          { id: 'A', label: 'A' },
          { id: 'B', label: 'B' },
          { id: 'C', label: 'C' },
        ],
        links: [
          { from: 'A', to: 'B', polarity: '+' },
          { from: 'B', to: 'C', polarity: '+' },
          // missing C → A
        ],
        loops: [
          { id: 'R1', type: 'R', members: ['A', 'B', 'C'], label: 'Fake loop' },
        ],
      }),
      expectCode: 'E_GRAPH_CYCLE',
    },

    // Polarity-parity mismatch: declared as R but has odd number of '-'.
    {
      label: 'parity mismatch: declared R, but 1 negative (should be B)',
      env: envelope({
        variables: [
          { id: 'V', label: 'Velocity' },
          { id: 'T', label: 'Tech debt' },
          { id: 'F', label: 'Fires' },
        ],
        links: [
          { from: 'V', to: 'T', polarity: '+' },
          { from: 'T', to: 'F', polarity: '+' },
          { from: 'F', to: 'V', polarity: '-' },
        ],
        loops: [
          { id: 'R1', type: 'R', members: ['V', 'T', 'F'], label: 'Mislabeled' },
        ],
      }),
      expectCode: 'E_SCHEMA_INVALID',
    },

    // Undeclared variable reference in a link.
    {
      label: 'link references an undeclared variable',
      env: envelope({
        variables: [
          { id: 'A', label: 'A' },
          { id: 'B', label: 'B' },
        ],
        links: [
          { from: 'A', to: 'B', polarity: '+' },
          { from: 'B', to: 'ZZZ', polarity: '+' },   // ZZZ not declared
        ],
        loops: [],
      }),
      expectCode: 'E_UNRESOLVED_REF',
    },
  ];
}

// ── Assertion helpers ────────────────────────────────────────────────────────
function hasSvgRoot(s)    { return typeof s === 'string' && /<svg\b/i.test(s); }
function hasClass(s, c)   { return new RegExp('class="[^"]*\\b' +
                              c.replace(/-/g, '\\-') + '\\b').test(s); }
function hasAriaImg(s)    { return /role="img"/.test(s); }
function hasAriaLabel(s)  { return /aria-label="[^"]+"/.test(s); }
function hasNodeId(s, id) { return new RegExp('id="cld-node-' + id + '"').test(s); }
function hasEdgeId(s, fr, to) {
  return new RegExp('id="cld-edge-' + fr + '-' + to + '"').test(s);
}
function hasLoopId(s, id) { return new RegExp('id="cld-loop-' + id + '"').test(s); }
function countMatches(s, re) { const m = s.match(re); return m ? m.length : 0; }

function assertValid(result, tc) {
  if (!result) return 'no result returned';
  if (!Array.isArray(result.errors)) return 'result.errors missing';
  const errs = result.errors.filter((e) => e.code && e.code.startsWith('E_'));
  if (errs.length) return 'unexpected errors: ' +
    errs.map((e) => e.code + ':' + e.message).join('; ');

  if (!hasSvgRoot(result.svg)) return 'no <svg> root in output';
  if (!hasClass(result.svg, 'ora-visual')) return 'missing ora-visual class on root';
  if (!hasClass(result.svg, 'ora-visual--causal_loop_diagram'))
    return 'missing ora-visual--causal_loop_diagram class on root';
  if (!hasAriaImg(result.svg)) return 'missing role="img" on root';
  if (!hasAriaLabel(result.svg)) return 'missing aria-label on root';

  // Semantic node IDs for each variable.
  for (const v of tc.env.spec.variables) {
    if (!hasNodeId(result.svg, v.id))
      return 'missing semantic node id cld-node-' + v.id;
  }

  // Semantic edge IDs and polarity classes for each link.
  for (const l of tc.env.spec.links) {
    if (!hasEdgeId(result.svg, l.from, l.to))
      return 'missing edge id cld-edge-' + l.from + '-' + l.to;
    const polClass = l.polarity === '+'
      ? 'ora-visual__edge--pos' : 'ora-visual__edge--neg';
    if (!hasClass(result.svg, polClass))
      return 'missing polarity class ' + polClass + ' on edge ' +
             l.from + '→' + l.to;
  }

  // Loop annotations: one group per declared loop, with R/B text content.
  for (const loop of tc.env.spec.loops) {
    if (!hasLoopId(result.svg, loop.id))
      return 'missing loop id cld-loop-' + loop.id;
    // R or B appears as the loop-label text of this group.
    const loopClass = loop.type === 'R'
      ? 'ora-visual__loop--reinforcing'
      : 'ora-visual__loop--balancing';
    if (!hasClass(result.svg, loopClass))
      return 'missing loop type class ' + loopClass + ' for ' + loop.id;
  }

  // Exactly one marker per polarity in <defs>.
  const posMarker = /<marker\s+id="cld-arrow-pos"/.test(result.svg);
  const negMarker = /<marker\s+id="cld-arrow-neg"/.test(result.svg);
  if (!posMarker || !negMarker)
    return 'missing arrow markers (pos=' + posMarker + ', neg=' + negMarker + ')';

  // Polarity labels: every link should have a glyph near its midpoint.
  // We can't assert exact positions without parsing; the count must
  // match the link count. Glyphs are '+' and U+2212 MINUS SIGN.
  // Count <text ... ora-visual__polarity-indicator ...> occurrences.
  const polLabelCount = countMatches(
    result.svg,
    /class="[^"]*\bora-visual__polarity-indicator\b[^"]*"/g
  );
  if (polLabelCount < tc.env.spec.links.length) {
    return 'polarity label count ' + polLabelCount +
           ' < expected ' + tc.env.spec.links.length;
  }

  // Orphan warning suppression (allow_isolated).
  if (tc.expectNoOrphanWarning) {
    const warn = (result.warnings || []).find((w) => w.code === 'W_ORPHAN_NODE');
    if (warn) return 'unexpected W_ORPHAN_NODE despite allow_isolated=true';
  }

  return null;  // ok
}

function assertInvalid(result, tc) {
  if (!result) return 'no result returned';
  if (!Array.isArray(result.errors) || result.errors.length === 0)
    return 'expected errors but got none; svg length=' +
           (result.svg || '').length;
  const codes = result.errors.map((e) => e.code);
  if (!codes.includes(tc.expectCode))
    return 'expected ' + tc.expectCode + ' but got ' + JSON.stringify(codes);
  if (result.svg !== '')
    return 'expected empty svg on error, got length=' + result.svg.length;
  return null;
}

// ── Shared fixture runner (works against any ctx with .win loaded) ──────────
async function runAgainst(ctx, record) {
  const win = ctx.win;
  const OVC = win.OraVisualCompiler;
  if (!OVC || !OVC._renderers || !OVC._renderers.causalLoopDiagram) {
    record('causal_loop_diagram renderer registered', false,
      'OraVisualCompiler._renderers.causalLoopDiagram not found');
    return;
  }

  // dispatcher integration: type no longer on stub.
  const isStub = OVC._dispatcher && OVC._dispatcher.isStub;
  if (typeof isStub === 'function') {
    record(
      'dispatcher: causal_loop_diagram no longer stubbed',
      isStub('causal_loop_diagram') === false,
      isStub('causal_loop_diagram') ? 'still stubbed' : ''
    );
  }

  // ── Valid fixtures ─────────────────────────────────────────────────────
  const valids = validFixtures();
  if (valids.length < 5) {
    record('valid fixture count >= 5', false,
      'only ' + valids.length + ' fixtures');
  }
  for (let i = 0; i < valids.length; i++) {
    const tc = valids[i];
    const name = 'valid CLD #' + (i + 1) + ' — ' + tc.label;
    try {
      let r = OVC._renderers.causalLoopDiagram.render(tc.env);
      if (r && typeof r.then === 'function') r = await r;
      const fail = assertValid(r, tc);
      if (fail) record(name, false, fail);
      else      record(name, true, 'svg ' + r.svg.length + ' chars');
    } catch (err) {
      record(name, false, 'threw: ' + (err && err.stack ? err.stack : err));
    }
  }

  // ── Invalid fixtures ───────────────────────────────────────────────────
  const invalids = invalidFixtures();
  if (invalids.length < 3) {
    record('invalid fixture count >= 3', false,
      'only ' + invalids.length + ' fixtures');
  }
  for (let i = 0; i < invalids.length; i++) {
    const tc = invalids[i];
    const name = 'invalid CLD #' + (i + 1) + ' — ' + tc.label;
    try {
      let r = OVC._renderers.causalLoopDiagram.render(tc.env);
      if (r && typeof r.then === 'function') r = await r;
      const fail = assertInvalid(r, tc);
      if (fail) record(name, false, fail);
      else      record(name, true, 'code ' + tc.expectCode);
    } catch (err) {
      record(name, false, 'threw: ' + (err && err.stack ? err.stack : err));
    }
  }

  // ── Compile-path integration (through OraVisualCompiler.compile) ──────
  // Confirm the renderer is wired and the envelope-level validation path
  // does not reject a well-formed valid fixture. Uses the first valid
  // fixture as a smoke test.
  try {
    const smoke = validFixtures()[0];
    let r = win.OraVisualCompiler.compile(smoke.env);
    if (r && typeof r.then === 'function') r = await r;
    const ok = r.errors.length === 0 &&
               /<svg\b/.test(r.svg) &&
               /ora-visual--causal_loop_diagram/.test(r.svg);
    record('compile(): CLD envelope round-trip', ok,
      ok ? '' : 'errors: ' + JSON.stringify(r.errors));
  } catch (err) {
    record('compile(): CLD envelope round-trip', false,
      'threw: ' + (err && err.stack ? err.stack : err));
  }

  // ── Layout determinism check: same input → identical SVG on repeat run.
  try {
    const tc = validFixtures()[1];
    let r1 = OVC._renderers.causalLoopDiagram.render(tc.env);
    if (r1 && typeof r1.then === 'function') r1 = await r1;
    let r2 = OVC._renderers.causalLoopDiagram.render(tc.env);
    if (r2 && typeof r2.then === 'function') r2 = await r2;
    const ok = r1.svg === r2.svg && r1.svg.length > 0;
    record('layout determinism: identical input → identical SVG', ok,
      ok ? '' : 'svg differed between runs (len1=' + r1.svg.length +
                ', len2=' + r2.svg.length + ')');
  } catch (err) {
    record('layout determinism', false,
      'threw: ' + (err && err.stack ? err.stack : err));
  }

  // ── Unit: seed derivation is order-insensitive. ────────────────────────
  try {
    const seedFor = OVC._renderers.causalLoopDiagram._seedFor;
    const specA = {
      variables: [{id:'A',label:'A'},{id:'B',label:'B'}],
      links: [
        {from:'A', to:'B', polarity:'+'},
        {from:'B', to:'A', polarity:'+'},
      ],
      loops: [],
    };
    const specB = {
      variables: [{id:'B',label:'B'},{id:'A',label:'A'}],   // reversed
      links: [
        {from:'B', to:'A', polarity:'+'},                   // reversed order
        {from:'A', to:'B', polarity:'+'},
      ],
      loops: [],
    };
    const ok = seedFor(specA) === seedFor(specB);
    record('unit: _seedFor ignores array order', ok,
      ok ? '' : 'seeds differ: A=' + seedFor(specA) + ' B=' + seedFor(specB));
  } catch (err) {
    record('unit: _seedFor ignores array order', false,
      'threw: ' + (err && err.stack ? err.stack : err));
  }
}

// ── Case-file export (consumed by run.js) ────────────────────────────────────
module.exports = {
  label: 'Causal loop diagram renderer (WP-1.3a) — ≥5 valid + ≥3 invalid',
  run: async function run(ctx, record) {
    // When invoked under run.js, ctx.win is the jsdom window that has
    // loaded the compiler core (errors/validator/stub/dispatcher/index).
    // run.js does not load d3 or the CLD renderer — do that now.
    const win = ctx.win;
    if (!win) {
      record('ctx.win present', false, 'no jsdom window');
      return;
    }

    const COMPILER_DIR = path.resolve(__dirname, '..', '..');
    const D3_PATH = path.join(COMPILER_DIR, 'vendor', 'd3', 'd3.min.js');
    const RENDERER = path.join(COMPILER_DIR, 'renderers', 'causal-loop-diagram.js');
    const PALETTES = path.join(COMPILER_DIR, 'palettes.js');

    // palettes.js is safe to load multiple times (idempotent IIFE). Only
    // load if not already on window.
    if (!win.OraVisualCompiler.palettes) {
      win.eval(fs.readFileSync(PALETTES, 'utf-8'));
    }
    if (typeof win.d3 === 'undefined') {
      win.eval(fs.readFileSync(D3_PATH, 'utf-8'));
    }
    if (!win.OraVisualCompiler._renderers ||
        !win.OraVisualCompiler._renderers.causalLoopDiagram) {
      win.eval(fs.readFileSync(RENDERER, 'utf-8'));
    }

    await runAgainst({ win: win }, record);
  },
};

// ── Standalone harness: `node test-causal-loop-diagram.js` ──────────────────
if (require.main === module) {
  const vm = require('vm');
  const { JSDOM } = require('jsdom');

  const COMPILER_DIR = path.resolve(__dirname, '..', '..');

  const dom = new JSDOM(
    '<!doctype html><html><head></head><body></body></html>',
    { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
  );
  const win = dom.window;
  win.globalThis = win;
  win.console = console;

  const ctx = dom.getInternalVMContext();
  const load = (p) => vm.runInContext(
    fs.readFileSync(p, 'utf-8'), ctx, { filename: p });

  load(path.join(COMPILER_DIR, 'errors.js'));
  load(path.join(COMPILER_DIR, 'validator.js'));
  load(path.join(COMPILER_DIR, 'renderers', 'stub.js'));
  load(path.join(COMPILER_DIR, 'dispatcher.js'));
  load(path.join(COMPILER_DIR, 'index.js'));
  load(path.join(COMPILER_DIR, 'palettes.js'));
  load(path.join(COMPILER_DIR, 'vendor', 'd3', 'd3.min.js'));
  load(path.join(COMPILER_DIR, 'renderers', 'causal-loop-diagram.js'));

  const results = [];
  function record(name, ok, detail) {
    results.push({ name: name, ok: !!ok, detail: detail || '' });
    const sigil = ok ? 'PASS' : 'FAIL';
    console.log('  ' + sigil + '  ' + name + (detail ? '  — ' + detail : ''));
  }

  (async function main() {
    console.log('test-causal-loop-diagram.js — WP-1.3a');
    const ver = fs.readFileSync(
      path.join(COMPILER_DIR, 'vendor', 'd3', 'VERSION'), 'utf-8')
      .split('\n')[0].trim();
    console.log('d3 version: ' + ver);
    console.log('jsdom version: ' + require('jsdom/package.json').version);
    console.log('----------------------------------------');

    await runAgainst({ win: win }, record);

    console.log('----------------------------------------');
    const pass = results.filter((r) => r.ok).length;
    const fail = results.length - pass;
    console.log('Result: ' + pass + ' passed / ' + results.length +
                ' total  (' + fail + ' failed)');
    if (fail > 0) {
      console.log('\nFailures:');
      for (const r of results) if (!r.ok)
        console.log('  - ' + r.name + ' :: ' + r.detail);
      process.exit(1);
    }
    process.exit(0);
  })().catch((e) => {
    console.error('Harness crashed:', e && e.stack ? e.stack : e);
    process.exit(2);
  });
}
