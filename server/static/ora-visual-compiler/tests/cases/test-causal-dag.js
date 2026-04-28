/**
 * test-causal-dag.js — WP-1.2c regression suite.
 *
 * Standalone: runs directly under Node with jsdom. Loads the compiler
 * core, the vendored @viz-js/viz standalone bundle, the dot-engine
 * primitive, and the causal-dag renderer; then exercises:
 *
 *   - ≥ 5 valid DAGs (X→Y; confounder U→X, U→Y; mediator; bidirected
 *     edge; latent variable)
 *   - invalid cycle          (expect E_GRAPH_CYCLE)
 *   - missing focal node     (expect E_UNRESOLVED_REF)
 *   - malformed DAGitty DSL  (expect E_DSL_PARSE)
 *   - internal DAGitty-parser unit tests (tokenise / cycle detector)
 *
 * Usage:
 *   node test-causal-dag.js
 *
 * Exits non-zero on any failure.
 */

'use strict';

const fs   = require('fs');
const path = require('path');
const vm   = require('vm');
const { JSDOM } = require('jsdom');

// ── Paths ──────────────────────────────────────────────────────────────────
const COMPILER_DIR = path.resolve(__dirname, '..', '..');
const VENDOR_VIZ   = path.join(COMPILER_DIR, 'vendor', 'viz-js', 'viz-standalone.js');

const read = (p) => fs.readFileSync(p, 'utf-8');

// ── jsdom bootstrap ────────────────────────────────────────────────────────
const dom = new JSDOM(
  '<!doctype html><html><head></head><body></body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
);
const { window } = dom;
window.globalThis = window;
window.console    = console;

// Patch minimal browser APIs viz-js touches. The standalone bundle is
// almost self-contained but may reach for fetch on first init.
if (!window.fetch) window.fetch = globalThis.fetch;
if (!window.getComputedStyle)
  window.getComputedStyle = () => ({ getPropertyValue: () => '' });
if (!window.matchMedia)
  window.matchMedia = () => ({ matches: false, addListener: () => {}, removeListener: () => {} });
if (!window.requestAnimationFrame)
  window.requestAnimationFrame = (cb) => setTimeout(cb, 16);

const ctx = dom.getInternalVMContext();

// ── Load compiler core into the jsdom context ─────────────────────────────
const coreFiles = [
  path.join(COMPILER_DIR, 'errors.js'),
  path.join(COMPILER_DIR, 'validator.js'),
  path.join(COMPILER_DIR, 'renderers', 'stub.js'),
  path.join(COMPILER_DIR, 'dispatcher.js'),
  path.join(COMPILER_DIR, 'index.js'),
];
for (const f of coreFiles) {
  vm.runInContext(read(f), ctx, { filename: f });
}

// ── Load vendored viz-js ───────────────────────────────────────────────────
vm.runInContext(read(VENDOR_VIZ), ctx, { filename: VENDOR_VIZ });

if (typeof window.Viz === 'undefined' || typeof window.Viz.instance !== 'function') {
  console.error('FAIL: window.Viz not exposed after loading viz-standalone.js');
  process.exit(1);
}

// ── Load dot-engine primitive ──────────────────────────────────────────────
const DOT_ENGINE = path.join(COMPILER_DIR, 'dot-engine.js');
vm.runInContext(read(DOT_ENGINE), ctx, { filename: DOT_ENGINE });

if (!window.OraVisualCompiler ||
    !window.OraVisualCompiler._dotEngine ||
    typeof window.OraVisualCompiler._dotEngine.dotToSvg !== 'function') {
  console.error('FAIL: _dotEngine.dotToSvg not exposed after loading dot-engine.js');
  process.exit(1);
}

// ── Load causal-dag renderer ───────────────────────────────────────────────
const RENDERER = path.join(COMPILER_DIR, 'renderers', 'causal-dag.js');
vm.runInContext(read(RENDERER), ctx, { filename: RENDERER });

const OVC = window.OraVisualCompiler;
if (!OVC._renderers || !OVC._renderers.causalDag) {
  console.error('FAIL: OraVisualCompiler._renderers.causalDag not exposed');
  process.exit(1);
}

// ── Test fixtures ──────────────────────────────────────────────────────────
function envelope(spec, overrides) {
  const base = {
    schema_version: '0.2',
    id: 'fig-test-causal-dag',
    type: 'causal_dag',
    mode_context: 'root_cause_analysis',
    relation_to_prose: 'integrated',
    spec: spec,
    semantic_description: {
      level_1_elemental: 'Test causal DAG',
      level_2_statistical: null,
      level_3_perceptual: null,
      level_4_contextual: null,
      short_alt: 'test DAG',
      data_table_fallback: null,
    },
    title: 'Test causal DAG',
  };
  return Object.assign(base, overrides || {});
}

// Five hand-written valid DAGs covering the canonical graph shapes.
const validCases = [
  {
    label: 'simple X → Y',
    env: envelope({
      dsl: 'dag { x [exposure]; y [outcome]; x -> y }',
      focal_exposure: 'x',
      focal_outcome: 'y',
    }),
    expectNodes: 2,
    expectClasses: ['ora-visual__node--exposure', 'ora-visual__node--outcome'],
  },
  {
    label: 'confounder U → X, U → Y',
    env: envelope({
      dsl: 'dag { x [exposure]; y [outcome]; u; x -> y; u -> x; u -> y }',
      focal_exposure: 'x',
      focal_outcome: 'y',
    }),
    expectNodes: 3,
    expectClasses: ['ora-visual__node--exposure', 'ora-visual__node--outcome'],
  },
  {
    label: 'mediator X → M → Y',
    env: envelope({
      dsl: 'dag { x [exposure]; m; y [outcome]; x -> m; m -> y; x -> y }',
      focal_exposure: 'x',
      focal_outcome: 'y',
    }),
    expectNodes: 3,
  },
  {
    label: 'bidirected edge (unobserved common cause) x <-> y',
    env: envelope({
      dsl: 'dag { x [exposure]; y [outcome]; z; x -> z; y -> z; x <-> y }',
      focal_exposure: 'x',
      focal_outcome: 'y',
    }),
    expectNodes: 3,
    expectClasses: ['ora-visual__edge--bidirected'],
  },
  {
    label: 'latent variable u (unobserved) with observed x, y, w',
    env: envelope({
      dsl: 'dag { x [exposure]; y [outcome]; u [latent]; w [adjusted]; u -> x; u -> y; w -> x; w -> y; x -> y }',
      focal_exposure: 'x',
      focal_outcome: 'y',
    }),
    expectNodes: 4,
    expectClasses: [
      'ora-visual__node--exposure',
      'ora-visual__node--outcome',
      'ora-visual__node--latent',
      'ora-visual__node--adjusted',
    ],
  },
];

const invalidCases = [
  {
    label: 'cycle x → y → z → x',
    env: envelope({
      dsl: 'dag { x [exposure]; y [outcome]; z; x -> y; y -> z; z -> x }',
      focal_exposure: 'x',
      focal_outcome: 'y',
    }),
    expectCode: 'E_GRAPH_CYCLE',
  },
  {
    label: 'missing focal_outcome node',
    env: envelope({
      dsl: 'dag { x [exposure]; y [outcome]; x -> y }',
      focal_exposure: 'x',
      focal_outcome: 'nowhere',
    }),
    expectCode: 'E_UNRESOLVED_REF',
  },
  {
    label: 'malformed DAGitty DSL',
    env: envelope({
      dsl: 'dag { $$$ this is not the dsl you are looking for !!! }',
      focal_exposure: 'x',
      focal_outcome: 'y',
    }),
    expectCode: 'E_DSL_PARSE',
  },
];

// ── Assertion helpers ──────────────────────────────────────────────────────
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

const hasSvgRoot   = (s) => typeof s === 'string' && /<svg\b/i.test(s);
const hasClass     = (s, c) => new RegExp('class="[^"]*\\b' + c.replace(/-/g, '\\-') + '\\b').test(s);
const hasAriaImg   = (s) => /role="img"/.test(s);
const hasAriaLabel = (s) => /aria-label="[^"]+"/.test(s);
const countMatches = (s, re) => {
  const m = s.match(re);
  return m ? m.length : 0;
};
const hasNodeId = (s, id) => new RegExp('id="node_' + id + '"').test(s);
const hasInlineStyle = (s) => /\sstyle="/.test(s) || /\sfill="/.test(s) ||
                              /\sstroke="/.test(s) || /\sfont-family="/.test(s);

// ── Internal unit tests: parser + cycle detector ──────────────────────────
function unitParserAndCycle() {
  const internals = OVC._renderers.causalDag;

  // Parser: ids, kinds, edges.
  const p = internals._parseDagitty(
    'dag { x [exposure]; y [outcome]; u [latent]; x -> y; u -> x; u -> y }'
  );
  report(
    'unit(parser): 3 nodes parsed',
    p.nodes.size === 3,
    'got ' + p.nodes.size
  );
  report(
    'unit(parser): exposure kind on x',
    p.nodes.get('x') && p.nodes.get('x').kinds.has('exposure'),
    'x kinds: ' + JSON.stringify([...(p.nodes.get('x') || {kinds:new Set()}).kinds])
  );
  report(
    'unit(parser): 3 edges',
    p.edges.length === 3,
    'got ' + p.edges.length
  );

  // <-> normalization
  const p2 = internals._parseDagitty('dag { a; b; a <-> b }');
  report(
    'unit(parser): <-> preserved as op',
    p2.edges.length === 1 && p2.edges[0].op === '<->',
    JSON.stringify(p2.edges)
  );

  // <- reversal
  const p3 = internals._parseDagitty('dag { a; b; a <- b }');
  report(
    'unit(parser): <- reversed into b -> a',
    p3.edges.length === 1 && p3.edges[0].from === 'b' && p3.edges[0].to === 'a' &&
    p3.edges[0].op === '->',
    JSON.stringify(p3.edges)
  );

  // Cycle detector: acyclic case returns null.
  const acyc = internals._parseDagitty('dag { a; b; c; a -> b; b -> c }');
  report(
    'unit(cycle): acyclic returns null',
    internals._hasCycle(acyc.nodes, acyc.edges) === null,
    'non-null'
  );

  // Cycle detector: cyclic case returns the cycle path.
  const cyc = internals._parseDagitty('dag { a; b; c; a -> b; b -> c; c -> a }');
  const foundCycle = internals._hasCycle(cyc.nodes, cyc.edges);
  report(
    'unit(cycle): detects a cycle',
    Array.isArray(foundCycle) && foundCycle.length >= 3,
    'got ' + JSON.stringify(foundCycle)
  );

  // Bidirected edge alone does NOT create a cycle.
  const bidi = internals._parseDagitty('dag { a; b; a <-> b }');
  report(
    'unit(cycle): bidirected edge is not a directed cycle',
    internals._hasCycle(bidi.nodes, bidi.edges) === null,
    'unexpectedly flagged'
  );

  // Self-loop IS a cycle (directed).
  const self = internals._parseDagitty('dag { a; a -> a }');
  report(
    'unit(cycle): self-loop detected as cycle',
    Array.isArray(internals._hasCycle(self.nodes, self.edges)),
    'not detected'
  );
}

// ── Valid DAG runner ───────────────────────────────────────────────────────
async function runValid() {
  for (const tc of validCases) {
    const label = 'valid ' + tc.label;
    try {
      const result = await OVC._renderers.causalDag.render(tc.env);
      if (!result || result.errors.length) {
        report(label, false, 'unexpected errors: ' +
          JSON.stringify((result && result.errors) || []));
        continue;
      }
      if (!hasSvgRoot(result.svg)) {
        report(label, false, 'no <svg> root in output');
        continue;
      }
      if (!hasClass(result.svg, 'ora-visual--causal_dag')) {
        report(label, false, 'missing ora-visual--causal_dag class on root');
        continue;
      }
      if (!hasAriaImg(result.svg) || !hasAriaLabel(result.svg)) {
        report(label, false, 'missing role="img" / aria-label on root');
        continue;
      }
      if (hasInlineStyle(result.svg)) {
        report(label, false, 'inline fill/stroke/style/font-family not stripped');
        continue;
      }

      // Semantic node ID checks — every declared node gets id="node-<name>".
      const parsed = OVC._renderers.causalDag._parseDagitty(tc.env.spec.dsl);
      let missing = [];
      for (const id of parsed.nodes.keys()) {
        if (!hasNodeId(result.svg, id)) missing.push(id);
      }
      if (missing.length) {
        report(label, false, 'missing semantic node IDs for: ' + missing.join(', '));
        continue;
      }

      // Node count check (we expect one <g class="...ora-visual__node..."> per node).
      const nodeCount = countMatches(
        result.svg,
        /class="[^"]*\bora-visual__node\b[^"]*"/g
      );
      if (nodeCount !== tc.expectNodes) {
        report(label, false, 'node count mismatch: expected ' +
          tc.expectNodes + ', got ' + nodeCount);
        continue;
      }

      // Expected semantic classes if declared.
      if (tc.expectClasses) {
        const missingClass = tc.expectClasses.filter((c) => !hasClass(result.svg, c));
        if (missingClass.length) {
          report(label, false, 'missing expected classes: ' + missingClass.join(', '));
          continue;
        }
      }

      if (result.warnings.length) {
        // Warnings are allowed on valid inputs (e.g. from dot-engine). We
        // only complain on errors.
      }

      report(label, true);
    } catch (err) {
      report(label, false, 'threw: ' + (err && err.stack ? err.stack : err));
    }
  }
}

// ── Invalid DAG runner ─────────────────────────────────────────────────────
async function runInvalid() {
  for (const tc of invalidCases) {
    const label = 'invalid ' + tc.label;
    try {
      const result = await OVC._renderers.causalDag.render(tc.env);
      if (!result) {
        report(label, false, 'no result object');
        continue;
      }
      if (!result.errors.length) {
        report(label, false, 'expected errors but got none; svg length=' + result.svg.length);
        continue;
      }
      const codes = result.errors.map((e) => e.code);
      if (!codes.includes(tc.expectCode)) {
        report(label, false, 'expected ' + tc.expectCode +
          ' but got ' + JSON.stringify(codes));
        continue;
      }
      if (result.svg !== '') {
        report(label, false, 'expected empty svg on error, got length=' + result.svg.length);
        continue;
      }
      report(label, true);
    } catch (err) {
      report(label, false, 'threw: ' + (err && err.stack ? err.stack : err));
    }
  }
}

// ── dot-engine direct-call sanity test ────────────────────────────────────
async function runDotEngineSanity() {
  const label = 'dot-engine: basic DOT renders and styles are stripped';
  try {
    const { svg, errors, warnings } =
      await OVC._dotEngine.dotToSvg('digraph G { a -> b; b -> c }');
    if (errors.length) {
      report(label, false, 'errors: ' + JSON.stringify(errors));
      return;
    }
    if (!hasSvgRoot(svg)) {
      report(label, false, 'no <svg> root');
      return;
    }
    if (!/class="[^"]*\bora-visual\b/.test(svg)) {
      report(label, false, 'ora-visual class not added to root');
      return;
    }
    if (hasInlineStyle(svg)) {
      report(label, false, 'inline styles not stripped');
      return;
    }
    report(label, true);
  } catch (err) {
    report(label, false, 'threw: ' + (err && err.stack ? err.stack : err));
  }

  // Parse-failure contract.
  const label2 = 'dot-engine: garbage DOT returns E_DSL_PARSE';
  try {
    const r = await OVC._dotEngine.dotToSvg('!!! not a valid dot string !!!');
    const ok = r.svg === '' &&
               r.errors.length === 1 &&
               r.errors[0].code === 'E_DSL_PARSE';
    report(label2, ok, ok ? '' : JSON.stringify({ svg: r.svg.length, errors: r.errors }));
  } catch (err) {
    report(label2, false, 'threw: ' + (err && err.stack ? err.stack : err));
  }

  // Empty input contract.
  const label3 = 'dot-engine: empty input returns E_DSL_PARSE';
  try {
    const r = await OVC._dotEngine.dotToSvg('');
    const ok = r.errors.length === 1 && r.errors[0].code === 'E_DSL_PARSE';
    report(label3, ok, ok ? '' : JSON.stringify(r));
  } catch (err) {
    report(label3, false, 'threw: ' + (err && err.stack ? err.stack : err));
  }
}

// ── Dispatcher integration ────────────────────────────────────────────────
async function runDispatcherIntegration() {
  const label = 'dispatcher: causal_dag type no longer on stub';
  const { isStub } = OVC._dispatcher;
  report(label, isStub('causal_dag') === false,
    'causal_dag still wired to stub after renderer load');
}

// ── Main ──────────────────────────────────────────────────────────────────
(async function main() {
  console.log('test-causal-dag.js — WP-1.2c');
  const ver = read(path.join(COMPILER_DIR, 'vendor', 'viz-js', 'VERSION')).trim();
  console.log('@viz-js/viz version: ' + ver);
  console.log('jsdom version: ' + require('jsdom/package.json').version);
  console.log('----------------------------------------');

  unitParserAndCycle();
  await runDotEngineSanity();
  await runValid();
  await runInvalid();
  await runDispatcherIntegration();

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
