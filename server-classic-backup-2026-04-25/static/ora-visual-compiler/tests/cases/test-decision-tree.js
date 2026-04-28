/**
 * tests/cases/test-decision-tree.js — WP-1.3d regression suite.
 *
 * Exports { label, run(ctx, record) } for run.js integration, AND runs
 * standalone under `node tests/cases/test-decision-tree.js` with its own
 * jsdom bootstrap (mirrors test-causal-dag.js).
 *
 * Coverage:
 *   ≥ 5 valid cases:
 *     1. simple decision → chance → terminal
 *     2. 2-stage decision with probabilities summing correctly
 *     3. probability-only mode (no payoffs)
 *     4. decision mode with computed EV
 *     5. unbalanced tree (mixed depth branches)
 *   ≥ 3 invalid cases:
 *     1. probability sum ≠ 1          → E_PROB_SUM
 *     2. decision-node edge w/ prob   → E_SCHEMA_INVALID
 *     3. missing payoff (decision)    → E_SCHEMA_INVALID
 *   SVG structural checks:
 *     - correct shape per node kind (rect / circle / polygon)
 *     - EV annotation present when mode=decision
 *     - ora-visual__dt-edge--optimal applied to the chosen branch
 *     - root <svg> carries ora-visual and ora-visual--decision_tree classes,
 *       role="img", aria-label
 *     - stable semantic IDs: dt-node-* and dt-edge-*
 */

'use strict';

const fs = require('fs');
const path = require('path');

// ── Envelope helper ─────────────────────────────────────────────────────────
function envelope(spec, overrides) {
  const base = {
    schema_version: '0.2',
    id: 'fig-decision-tree-test',
    type: 'decision_tree',
    mode_context: 'root_cause_analysis',
    relation_to_prose: 'integrated',
    spec: spec,
    semantic_description: {
      level_1_elemental: 'Test decision tree.',
      level_2_statistical: null,
      level_3_perceptual: null,
      level_4_contextual: null,
      short_alt: 'test decision tree',
      data_table_fallback: null,
    },
    title: 'Test decision tree',
  };
  return Object.assign(base, overrides || {});
}

// ── Fixture builders ────────────────────────────────────────────────────────
// (1) simple decision → chance → terminal
function simpleDecisionChanceTerminal() {
  return envelope({
    mode: 'decision',
    utility_units: 'USD',
    root: {
      kind: 'decision',
      label: 'Invest?',
      children: [
        {
          edge_label: 'Yes',
          node: {
            kind: 'chance',
            label: 'Market',
            children: [
              { edge_label: 'Up',   probability: 0.6,
                node: { kind: 'terminal', label: 'Win',  payoff: 1000 } },
              { edge_label: 'Down', probability: 0.4,
                node: { kind: 'terminal', label: 'Lose', payoff: -500 } },
            ],
          },
        },
        {
          edge_label: 'No',
          node: { kind: 'terminal', label: 'Status quo', payoff: 0 },
        },
      ],
    },
  });
}

// (2) 2-stage decision — decision → chance → decision → terminals
function twoStageDecision() {
  return envelope({
    mode: 'decision',
    utility_units: 'utility',
    root: {
      kind: 'decision',
      label: 'Drug trial?',
      children: [
        {
          edge_label: 'Conduct trial',
          node: {
            kind: 'chance',
            label: 'Result',
            children: [
              {
                edge_label: 'Positive',
                probability: 0.3,
                node: {
                  kind: 'decision',
                  label: 'Launch?',
                  children: [
                    { edge_label: 'Launch',
                      node: { kind: 'terminal', label: 'Success', payoff: 1000 } },
                    { edge_label: 'Don\'t launch',
                      node: { kind: 'terminal', label: 'Safe',    payoff: 100 } },
                  ],
                },
              },
              {
                edge_label: 'Negative',
                probability: 0.7,
                node: { kind: 'terminal', label: 'Abandon', payoff: -200 },
              },
            ],
          },
        },
        {
          edge_label: 'Skip trial',
          node: { kind: 'terminal', label: 'No trial', payoff: 0 },
        },
      ],
    },
  });
}

// (3) probability_only mode — no payoffs on terminals
function probabilityOnly() {
  return envelope({
    mode: 'probability',
    root: {
      kind: 'chance',
      label: 'Coin',
      children: [
        { edge_label: 'Heads', probability: 0.5,
          node: {
            kind: 'chance',
            label: 'Die',
            children: [
              { edge_label: 'Even', probability: 0.5,
                node: { kind: 'terminal', label: 'HE' } },
              { edge_label: 'Odd',  probability: 0.5,
                node: { kind: 'terminal', label: 'HO' } },
            ],
          }},
        { edge_label: 'Tails', probability: 0.5,
          node: { kind: 'terminal', label: 'T' } },
      ],
    },
  });
}

// (4) Decision mode with computed EV — simple chance node
function decisionEvKnown() {
  return envelope({
    mode: 'decision',
    utility_units: 'USD',
    root: {
      kind: 'decision',
      label: 'Bet?',
      children: [
        {
          edge_label: 'Bet',
          node: {
            kind: 'chance',
            label: 'Roll',
            children: [
              { edge_label: 'Win',  probability: 0.5,
                node: { kind: 'terminal', label: 'W', payoff: 200 } },
              { edge_label: 'Lose', probability: 0.5,
                node: { kind: 'terminal', label: 'L', payoff: -100 } },
            ],
          },
        },
        {
          edge_label: 'Fold',
          node: { kind: 'terminal', label: 'F', payoff: 0 },
        },
      ],
    },
  });
}

// (5) unbalanced tree — one branch deep, others shallow
function unbalancedTree() {
  return envelope({
    mode: 'decision',
    utility_units: 'USD',
    root: {
      kind: 'decision',
      label: 'Route?',
      children: [
        { edge_label: 'A', node: { kind: 'terminal', label: 'A-end', payoff: 10 } },
        { edge_label: 'B', node: { kind: 'terminal', label: 'B-end', payoff: 5 } },
        {
          edge_label: 'C',
          node: {
            kind: 'chance',
            label: 'C-gate',
            children: [
              { edge_label: 'hit',  probability: 0.25,
                node: {
                  kind: 'chance',
                  label: 'C-hit',
                  children: [
                    { edge_label: 'big', probability: 0.5,
                      node: { kind: 'terminal', label: 'C-big', payoff: 200 } },
                    { edge_label: 'med', probability: 0.5,
                      node: { kind: 'terminal', label: 'C-med', payoff: 80 } },
                  ],
                }},
              { edge_label: 'miss', probability: 0.75,
                node: { kind: 'terminal', label: 'C-0', payoff: -20 } },
            ],
          },
        },
      ],
    },
  });
}

// ── Invalid fixtures ────────────────────────────────────────────────────────

// (I-1) probability sum ≠ 1
function invalidProbSum() {
  return envelope({
    mode: 'decision',
    utility_units: 'USD',
    root: {
      kind: 'chance',
      label: 'Wrong',
      children: [
        { edge_label: 'a', probability: 0.6,
          node: { kind: 'terminal', label: 'a', payoff: 10 } },
        { edge_label: 'b', probability: 0.5,
          node: { kind: 'terminal', label: 'b', payoff: 20 } },
      ],
    },
  });
}

// (I-2) decision-node outgoing edge carrying probability
function invalidDecisionEdgeProb() {
  return envelope({
    mode: 'decision',
    utility_units: 'USD',
    root: {
      kind: 'decision',
      label: 'Bad',
      children: [
        { edge_label: 'Yes', probability: 0.5,
          node: { kind: 'terminal', label: 'y', payoff: 1 } },
        { edge_label: 'No',  probability: 0.5,
          node: { kind: 'terminal', label: 'n', payoff: 0 } },
      ],
    },
  });
}

// (I-3) missing payoff on terminal in decision mode
function invalidMissingPayoff() {
  return envelope({
    mode: 'decision',
    utility_units: 'USD',
    root: {
      kind: 'decision',
      label: 'Pick',
      children: [
        { edge_label: 'A',
          node: { kind: 'terminal', label: 'A' } },
        { edge_label: 'B',
          node: { kind: 'terminal', label: 'B', payoff: 5 } },
      ],
    },
  });
}

// ── Assertion primitives ────────────────────────────────────────────────────
const hasSvgRoot  = (s) => typeof s === 'string' && /<svg\b/i.test(s);
const hasRootClass = (s) => /<svg\b[^>]*\sclass="[^"]*\bora-visual\b[^"]*\bora-visual--decision_tree\b[^"]*"/.test(s);
const hasRoleImg   = (s) => /<svg\b[^>]*\srole="img"/.test(s);
const hasAriaLabel = (s) => /<svg\b[^>]*\saria-label="[^"]+"/.test(s);
const hasRect      = (s) => /<rect\b[^>]*\bora-visual__dt-decision\b/.test(s);
const hasCircle    = (s) => /<circle\b[^>]*\bora-visual__dt-chance\b/.test(s);
const hasTriangle  = (s) => /<polygon\b[^>]*\bora-visual__dt-terminal\b/.test(s);
const hasEvText    = (s) => /class="[^"]*\bora-visual__dt-ev\b/.test(s);
const hasOptimal   = (s) => /class="[^"]*\bora-visual__dt-edge--optimal\b/.test(s);

function countMatches(s, re) {
  const m = s.match(re);
  return m ? m.length : 0;
}

function nodeShapesCount(svg, cls) {
  return countMatches(svg, new RegExp('class="[^"]*\\b' + cls + '\\b[^"]*"', 'g'));
}

// ── Core test function (works against any jsdom window with compiler loaded)
async function runAll(win, record) {
  const OVC = win.OraVisualCompiler;
  if (!OVC._renderers.decisionTree) {
    record('decision_tree renderer registered', false,
      '_renderers.decisionTree missing — vendor/dagre or renderers/decision-tree.js did not load');
    return;
  }
  record('decision_tree renderer registered', true);

  // Dispatcher should now route the type away from the stub.
  record('dispatcher: decision_tree not on stub',
    OVC._dispatcher.isStub('decision_tree') === false,
    'still on stub after load');

  // ── Valid cases ─────────────────────────────────────────────────────────
  const valid = [
    { label: 'valid simple decision→chance→terminal', env: simpleDecisionChanceTerminal(),
      assertions: (svg) => {
        const problems = [];
        if (!hasRect(svg))      problems.push('no decision square');
        if (!hasCircle(svg))    problems.push('no chance circle');
        if (!hasTriangle(svg))  problems.push('no terminal triangle');
        if (!hasEvText(svg))    problems.push('no EV annotation (mode=decision)');
        if (!hasOptimal(svg))   problems.push('no ora-visual__dt-edge--optimal');
        // Expected node/edge IDs (dagre-agnostic paths).
        // Root is "r"; "Yes" branch is r-0; "No" branch is r-1.
        if (!/id="dt-node-r"/.test(svg))   problems.push('missing dt-node-r id');
        if (!/id="dt-node-r-0"/.test(svg)) problems.push('missing dt-node-r-0 id');
        if (!/id="dt-edge-r-r-0"/.test(svg)) problems.push('missing dt-edge-r-r-0 id');
        return problems;
      }},
    { label: 'valid 2-stage decision with correct probs', env: twoStageDecision(),
      assertions: (svg) => {
        const problems = [];
        if (!hasRect(svg))     problems.push('no decision square');
        if (!hasCircle(svg))   problems.push('no chance circle');
        if (!hasTriangle(svg)) problems.push('no terminal triangle');
        if (!hasEvText(svg))   problems.push('no EV annotation');
        // Should have probability labels on chance edges.
        if (!/p=0\.3/.test(svg) || !/p=0\.7/.test(svg)) {
          problems.push('probability labels p=0.3 / p=0.7 not emitted');
        }
        return problems;
      }},
    { label: 'valid probability-only (no payoffs)', env: probabilityOnly(),
      assertions: (svg) => {
        const problems = [];
        if (!hasCircle(svg))   problems.push('no chance circle');
        if (!hasTriangle(svg)) problems.push('no terminal triangle');
        // In probability mode, no EV annotation.
        if (hasEvText(svg))    problems.push('unexpected EV annotation in probability mode');
        // No optimal-edge highlighting in probability mode.
        if (hasOptimal(svg))   problems.push('unexpected optimal-edge class in probability mode');
        return problems;
      }},
    { label: 'valid decision mode EV computed (check data-rollback-ev)',
      env: decisionEvKnown(),
      assertions: (svg) => {
        const problems = [];
        // root EV should be 50 ("Bet": 0.5*200 + 0.5*-100 = 50; "Fold": 0; max 50).
        if (!/data-rollback-ev="50"/.test(svg)) {
          problems.push('root data-rollback-ev="50" not present (got EV not computed correctly)');
        }
        if (!hasOptimal(svg)) problems.push('no optimal-branch class on chosen edge');
        return problems;
      }},
    { label: 'valid unbalanced tree (mixed depths)', env: unbalancedTree(),
      assertions: (svg) => {
        const problems = [];
        if (!hasRect(svg))     problems.push('no decision square');
        if (!hasCircle(svg))   problems.push('no chance circle');
        if (!hasTriangle(svg)) problems.push('no terminal triangle');
        // At least 4 terminals (A-end, B-end, C-big, C-med, C-0 = 5).
        const terms = nodeShapesCount(svg, 'ora-visual__dt-terminal');
        if (terms < 4) problems.push('expected ≥4 terminal triangles, got ' + terms);
        if (!hasEvText(svg)) problems.push('no EV annotation');
        return problems;
      }},
  ];

  for (const tc of valid) {
    try {
      let result = OVC._renderers.decisionTree.render(tc.env);
      if (result && typeof result.then === 'function') result = await result;
      if (!result) {
        record(tc.label, false, 'no result object');
        continue;
      }
      if (result.errors && result.errors.length) {
        record(tc.label, false, 'unexpected errors: ' +
          result.errors.map((e) => e.code + ':' + e.message).join('; '));
        continue;
      }
      if (!hasSvgRoot(result.svg))  { record(tc.label, false, 'no <svg> root'); continue; }
      if (!hasRootClass(result.svg)) { record(tc.label, false, 'root missing ora-visual / ora-visual--decision_tree classes'); continue; }
      if (!hasRoleImg(result.svg))   { record(tc.label, false, 'missing role="img"'); continue; }
      if (!hasAriaLabel(result.svg)) { record(tc.label, false, 'missing aria-label'); continue; }
      const problems = tc.assertions(result.svg);
      if (problems.length) { record(tc.label, false, problems.join('; ')); continue; }
      record(tc.label, true, 'svg ' + result.svg.length + ' chars');
    } catch (err) {
      record(tc.label, false, 'threw: ' + (err && err.stack ? err.stack : err));
    }
  }

  // ── Invalid cases ───────────────────────────────────────────────────────
  const invalid = [
    { label: 'invalid prob sum ≠ 1 → E_PROB_SUM',
      env: invalidProbSum(), expect: 'E_PROB_SUM' },
    { label: 'invalid decision-edge probability → E_SCHEMA_INVALID',
      env: invalidDecisionEdgeProb(), expect: 'E_SCHEMA_INVALID' },
    { label: 'invalid missing payoff in decision mode → E_SCHEMA_INVALID',
      env: invalidMissingPayoff(), expect: 'E_SCHEMA_INVALID' },
  ];

  for (const tc of invalid) {
    try {
      let result = OVC._renderers.decisionTree.render(tc.env);
      if (result && typeof result.then === 'function') result = await result;
      if (!result)           { record(tc.label, false, 'no result object'); continue; }
      if (!result.errors || result.errors.length === 0) {
        record(tc.label, false, 'expected errors but got none; svg.length=' + (result.svg || '').length);
        continue;
      }
      const codes = result.errors.map((e) => e.code);
      if (codes.indexOf(tc.expect) === -1) {
        record(tc.label, false, 'expected ' + tc.expect + ' but got [' + codes.join(',') + ']');
        continue;
      }
      if (result.svg !== '') {
        record(tc.label, false, 'expected empty svg on error, got length=' + result.svg.length);
        continue;
      }
      record(tc.label, true, 'codes=' + codes.join(','));
    } catch (err) {
      record(tc.label, false, 'threw: ' + (err && err.stack ? err.stack : err));
    }
  }

  // ── Rollback-EV unit tests against the exposed internals ────────────────
  try {
    const internals = OVC._renderers.decisionTree;
    // Known case: decision { Bet: 0.5*200+0.5*(-100)=50; Fold: 0 } → root EV=50.
    const ev = (() => {
      const errs = [];
      const w = internals._walk(decisionEvKnown().spec.root, 'decision', errs);
      internals._rollback(w.tree);
      return w.tree.ev;
    })();
    record('unit(rollback): root EV=50 for decisionEvKnown', Math.abs(ev - 50) < 1e-9,
      'got EV=' + ev);

    // prob-only mode still walks cleanly (no EV needed, but walker runs).
    const errsProb = [];
    const walkedProb = internals._walk(probabilityOnly().spec.root, 'probability', errsProb);
    record('unit(walk): probability-only mode accepts missing payoffs',
      errsProb.length === 0 && walkedProb.tree !== null,
      errsProb.map((e) => e.code).join(','));

    // Floating-point prob sum at the edge of tolerance: 0.333333 * 3 should pass.
    const edge = {
      kind: 'chance', label: 'fp',
      children: [
        { edge_label: 'a', probability: 0.333333,
          node: { kind: 'terminal', label: 'a', payoff: 1 } },
        { edge_label: 'b', probability: 0.333333,
          node: { kind: 'terminal', label: 'b', payoff: 2 } },
        { edge_label: 'c', probability: 0.333334,
          node: { kind: 'terminal', label: 'c', payoff: 3 } },
      ],
    };
    const errsFp = [];
    internals._walk(edge, 'decision', errsFp);
    record('unit(walk): floating-point probabilities within 1e-6 of 1.0 accepted',
      errsFp.length === 0, errsFp.map((e) => e.code + ':' + e.message).join(','));
  } catch (err) {
    record('unit(rollback + walk)', false, 'threw: ' + (err && err.stack ? err.stack : err));
  }
}

// ── Standalone runner (mirrors test-causal-dag.js) ──────────────────────────
async function standaloneMain() {
  const vm = require('vm');
  const { JSDOM } = require('jsdom');

  const COMPILER_DIR = path.resolve(__dirname, '..', '..');
  const VENDOR_DAGRE = path.join(COMPILER_DIR, 'vendor', 'dagre', 'dagre.min.js');

  const read = (p) => fs.readFileSync(p, 'utf-8');

  const dom = new JSDOM(
    '<!doctype html><html><head></head><body></body></html>',
    { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
  );
  const ctx = dom.getInternalVMContext();

  const coreFiles = [
    path.join(COMPILER_DIR, 'errors.js'),
    path.join(COMPILER_DIR, 'validator.js'),
    path.join(COMPILER_DIR, 'renderers', 'stub.js'),
    path.join(COMPILER_DIR, 'dispatcher.js'),
    path.join(COMPILER_DIR, 'index.js'),
  ];
  for (const f of coreFiles) vm.runInContext(read(f), ctx, { filename: f });
  vm.runInContext(read(VENDOR_DAGRE), ctx, { filename: VENDOR_DAGRE });
  vm.runInContext(read(path.join(COMPILER_DIR, 'renderers', 'decision-tree.js')), ctx,
    { filename: 'decision-tree.js' });

  let passed = 0, failed = 0;
  const failures = [];
  function record(name, ok, detail) {
    if (ok) { passed += 1; console.log('PASS  ' + name + (detail ? '  (' + detail + ')' : '')); }
    else    { failed += 1; failures.push({ name, detail });
              console.log('FAIL  ' + name + '  :: ' + (detail || '')); }
  }

  console.log('test-decision-tree.js — WP-1.3d');
  console.log('dagre version: ' + read(path.join(COMPILER_DIR, 'vendor', 'dagre', 'VERSION')).trim());
  console.log('-----------------------------------------');
  await runAll(dom.window, record);
  console.log('-----------------------------------------');
  console.log('Result: ' + passed + ' passed / ' + (passed + failed) + ' total (' + failed + ' failed)');
  if (failed > 0) {
    console.log('\nFailures:');
    for (const f of failures) console.log('  - ' + f.name + ' :: ' + f.detail);
    process.exit(1);
  }
  process.exit(0);
}

// ── run.js integration export ───────────────────────────────────────────────
module.exports = {
  label: 'Decision tree renderer (WP-1.3d)',
  run: async function run(ctx, record) {
    // run.js's bootCompiler does not load the dagre vendor bundle or the
    // decision-tree renderer — load them here before exercising.
    const fsMod = require('fs');
    const COMPILER_DIR = path.resolve(__dirname, '..', '..');
    const VENDOR_DAGRE = path.join(COMPILER_DIR, 'vendor', 'dagre', 'dagre.min.js');
    const RENDERER    = path.join(COMPILER_DIR, 'renderers', 'decision-tree.js');
    try {
      if (!ctx.win.dagre) {
        ctx.win.eval(fsMod.readFileSync(VENDOR_DAGRE, 'utf-8'));
      }
      if (!ctx.win.OraVisualCompiler._renderers.decisionTree) {
        ctx.win.eval(fsMod.readFileSync(RENDERER, 'utf-8'));
      }
    } catch (err) {
      record('decision_tree bootstrap', false,
        'failed to load vendor/renderer: ' + (err && err.message ? err.message : err));
      return;
    }
    await runAll(ctx.win, record);
  },
};

// Allow standalone execution: `node tests/cases/test-decision-tree.js`.
if (require.main === module) {
  standaloneMain().catch((err) => {
    console.error('Harness crashed:', err && err.stack ? err.stack : err);
    process.exit(2);
  });
}
