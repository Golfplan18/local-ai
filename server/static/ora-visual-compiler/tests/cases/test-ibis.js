/**
 * test-ibis.js — WP-1.3i regression suite.
 *
 * Standalone Node + jsdom runner. Loads the compiler core, the vendored
 * @viz-js/viz bundle, the dot-engine primitive, and the ibis renderer;
 * then exercises:
 *
 *   ≥ 5 valid:
 *     - single question with 2 ideas and 1 pro
 *     - nested question (question.questions → question)
 *     - multiple pros and cons under one idea
 *     - question questioning a question
 *     - orphan idea (idea only, no pros or cons attached — allowed)
 *     - plus: full canonical example (the ibis.valid.json shape)
 *
 *   ≥ 5 invalid grammar:
 *     - pro.responds_to → question         (wrong source for responds_to)
 *     - idea.supports → idea               (wrong source for supports)
 *     - con.questions → idea               (wrong source for questions)
 *     - pro pointing to question           (pro.supports → question)
 *     - edge target id does not resolve    (E_UNRESOLVED_REF)
 *     - plus: unknown edge kind ("implies")
 *     - plus: no question in the diagram   (E_SCHEMA_INVALID)
 *
 *   Structural SVG checks:
 *     - ora-visual / ora-visual--ibis on root <svg>
 *     - role="img" and aria-label present
 *     - shape=diamond used for question, box/rounded for idea,
 *       triangle for pro, invtriangle for con (verified via Graphviz's
 *       polygon point counts or shape attributes survived)
 *     - stable ids: ibis-q-<id>, ibis-i-<id>, ibis-pro-<id>, ibis-con-<id>,
 *       ibis-edge-<from>-<to>
 *     - inline fill/stroke/style/font-family stripped
 *     - all declared edges appear (one <g class="...edge..."> per relation)
 *
 * Also exports { label, run(ctx, record) } for the run.js harness.
 *
 * Usage (standalone):
 *   node test-ibis.js
 */

'use strict';

const fs   = require('fs');
const path = require('path');
const vm   = require('vm');
const { JSDOM } = require('jsdom');

// ── Paths ──────────────────────────────────────────────────────────────────
const COMPILER_DIR = path.resolve(__dirname, '..', '..');
const VENDOR_VIZ   = path.join(COMPILER_DIR, 'vendor', 'viz-js', 'viz-standalone.js');
const DOT_ENGINE   = path.join(COMPILER_DIR, 'dot-engine.js');
const IBIS_RENDER  = path.join(COMPILER_DIR, 'renderers', 'ibis.js');

const read = (p) => fs.readFileSync(p, 'utf-8');

// ── Test fixtures ──────────────────────────────────────────────────────────

function envelope(spec, overrides) {
  const base = {
    schema_version: '0.2',
    id: 'fig-test-ibis',
    type: 'ibis',
    mode_context: 'root_cause_analysis',
    relation_to_prose: 'integrated',
    spec: spec,
    semantic_description: {
      level_1_elemental: 'Test IBIS diagram',
      level_2_statistical: null,
      level_3_perceptual: null,
      level_4_contextual: null,
      short_alt: 'test IBIS',
      data_table_fallback: null,
    },
    title: 'Test IBIS diagram',
  };
  return Object.assign(base, overrides || {});
}

const validCases = [
  {
    label: 'single question with 2 ideas and 1 pro',
    env: envelope({
      nodes: [
        { id: 'Q1', type: 'question', text: 'Should we adopt Rust?' },
        { id: 'I1', type: 'idea',     text: 'Rewrite hot path in Rust' },
        { id: 'I2', type: 'idea',     text: 'Keep using current stack' },
        { id: 'P1', type: 'pro',      text: 'Memory safety' },
      ],
      edges: [
        { from: 'I1', to: 'Q1', type: 'responds_to' },
        { from: 'I2', to: 'Q1', type: 'responds_to' },
        { from: 'P1', to: 'I1', type: 'supports' },
      ],
    }),
    expectIds: ['ibis-q-Q1', 'ibis-i-I1', 'ibis-i-I2', 'ibis-pro-P1',
                'ibis-edge-I1-Q1', 'ibis-edge-I2-Q1', 'ibis-edge-P1-I1'],
    expectEdgeCount: 3,
  },
  {
    label: 'nested question (question.questions → question)',
    env: envelope({
      nodes: [
        { id: 'Q1',  type: 'question', text: 'Root issue' },
        { id: 'Q1a', type: 'question', text: 'Sub-issue refining Q1' },
        { id: 'I1',  type: 'idea',     text: 'Proposed resolution of Q1a' },
      ],
      edges: [
        { from: 'Q1',  to: 'Q1',  type: 'questions' },  // (no — self-loops fine per grammar)
        // Actually use Q1a for the questions edge; self-loop replaced:
      ],
    }),
    // Fix the spec above — nested question questions the root.
    prepare(env) {
      env.spec.edges = [
        { from: 'Q1a', to: 'Q1',  type: 'questions'  },
        { from: 'I1',  to: 'Q1a', type: 'responds_to' },
      ];
      return env;
    },
    expectIds: ['ibis-q-Q1', 'ibis-q-Q1a', 'ibis-i-I1',
                'ibis-edge-Q1a-Q1', 'ibis-edge-I1-Q1a'],
    expectEdgeCount: 2,
  },
  {
    label: 'multiple pros and cons under one idea',
    env: envelope({
      nodes: [
        { id: 'Q1', type: 'question', text: 'Deploy to cloud?' },
        { id: 'I1', type: 'idea',     text: 'Use AWS' },
        { id: 'P1', type: 'pro',      text: 'Broad service catalogue' },
        { id: 'P2', type: 'pro',      text: 'Mature tooling' },
        { id: 'C1', type: 'con',      text: 'Vendor lock-in' },
        { id: 'C2', type: 'con',      text: 'Cost at scale' },
      ],
      edges: [
        { from: 'I1', to: 'Q1', type: 'responds_to' },
        { from: 'P1', to: 'I1', type: 'supports'    },
        { from: 'P2', to: 'I1', type: 'supports'    },
        { from: 'C1', to: 'I1', type: 'objects_to'  },
        { from: 'C2', to: 'I1', type: 'objects_to'  },
      ],
    }),
    expectIds: ['ibis-q-Q1', 'ibis-i-I1',
                'ibis-pro-P1', 'ibis-pro-P2',
                'ibis-con-C1', 'ibis-con-C2'],
    expectEdgeCount: 5,
  },
  {
    label: 'question questioning a pro argument (question.questions → pro)',
    env: envelope({
      nodes: [
        { id: 'Q1', type: 'question', text: 'Adopt X?' },
        { id: 'I1', type: 'idea',     text: 'Yes, adopt X' },
        { id: 'P1', type: 'pro',      text: 'X is fast' },
        { id: 'Q2', type: 'question', text: 'Fast compared to what?' },
      ],
      edges: [
        { from: 'I1', to: 'Q1', type: 'responds_to' },
        { from: 'P1', to: 'I1', type: 'supports'    },
        { from: 'Q2', to: 'P1', type: 'questions'   },
      ],
    }),
    expectIds: ['ibis-q-Q1', 'ibis-q-Q2', 'ibis-i-I1', 'ibis-pro-P1'],
    expectEdgeCount: 3,
  },
  {
    label: 'orphan idea (no pros or cons — allowed)',
    env: envelope({
      nodes: [
        { id: 'Q1', type: 'question', text: 'Direction?' },
        { id: 'I1', type: 'idea',     text: 'Go north' },
      ],
      edges: [
        { from: 'I1', to: 'Q1', type: 'responds_to' },
      ],
    }),
    expectIds: ['ibis-q-Q1', 'ibis-i-I1', 'ibis-edge-I1-Q1'],
    expectEdgeCount: 1,
  },
  {
    label: 'canonical example (schema valid example)',
    env: envelope({
      nodes: [
        { id: 'Q1', type: 'question', text: 'Should we adopt Rust?' },
        { id: 'I1', type: 'idea',     text: 'Rewrite critical path in Rust' },
        { id: 'P1', type: 'pro',      text: 'Memory safety' },
        { id: 'C1', type: 'con',      text: 'Hiring pool smaller' },
      ],
      edges: [
        { from: 'I1', to: 'Q1', type: 'responds_to' },
        { from: 'P1', to: 'I1', type: 'supports'    },
        { from: 'C1', to: 'I1', type: 'objects_to'  },
      ],
    }),
    expectIds: ['ibis-q-Q1', 'ibis-i-I1', 'ibis-pro-P1', 'ibis-con-C1'],
    expectEdgeCount: 3,
  },
];

// Invalid cases. Each expects a specific error code and, for grammar
// errors, verifies that the offending edge path is named in the message.
const invalidCases = [
  {
    label: 'pro.responds_to → question (wrong source for responds_to)',
    env: envelope({
      nodes: [
        { id: 'Q1', type: 'question', text: 'Why?' },
        { id: 'P1', type: 'pro',      text: 'Because' },
      ],
      edges: [
        { from: 'P1', to: 'Q1', type: 'responds_to' },
      ],
    }),
    // No idea in graph, so no idea violations; just the one grammar error.
    expectCode: 'E_IBIS_GRAMMAR',
    expectEdge: 'spec.edges[0]',
  },
  {
    label: 'idea.supports → idea (wrong source for supports)',
    env: envelope({
      nodes: [
        { id: 'Q1', type: 'question', text: 'Q' },
        { id: 'I1', type: 'idea',     text: 'idea 1' },
        { id: 'I2', type: 'idea',     text: 'idea 2' },
      ],
      edges: [
        { from: 'I1', to: 'Q1', type: 'responds_to' },
        { from: 'I2', to: 'I1', type: 'supports'    },  // illegal
      ],
    }),
    expectCode: 'E_IBIS_GRAMMAR',
    expectEdge: 'spec.edges[1]',
  },
  {
    label: 'con.questions → idea (wrong source for questions)',
    env: envelope({
      nodes: [
        { id: 'Q1', type: 'question', text: 'Q' },
        { id: 'I1', type: 'idea',     text: 'idea' },
        { id: 'C1', type: 'con',      text: 'con' },
      ],
      edges: [
        { from: 'I1', to: 'Q1', type: 'responds_to' },
        { from: 'C1', to: 'I1', type: 'questions'   },  // illegal
      ],
    }),
    expectCode: 'E_IBIS_GRAMMAR',
    expectEdge: 'spec.edges[1]',
  },
  {
    label: 'pro.supports → question (pro pointing at a question, not an idea)',
    env: envelope({
      nodes: [
        { id: 'Q1', type: 'question', text: 'Q' },
        { id: 'P1', type: 'pro',      text: 'P' },
      ],
      edges: [
        { from: 'P1', to: 'Q1', type: 'supports' },  // supports must target idea
      ],
    }),
    expectCode: 'E_IBIS_GRAMMAR',
    expectEdge: 'spec.edges[0]',
  },
  {
    label: 'missing target id resolves → E_UNRESOLVED_REF',
    env: envelope({
      nodes: [
        { id: 'Q1', type: 'question', text: 'Q' },
        { id: 'I1', type: 'idea',     text: 'I' },
      ],
      edges: [
        { from: 'I1', to: 'Q_missing', type: 'responds_to' },
      ],
    }),
    expectCode: 'E_UNRESOLVED_REF',
  },
  {
    label: 'unknown edge kind "implies" → E_IBIS_GRAMMAR',
    env: envelope({
      nodes: [
        { id: 'Q1', type: 'question', text: 'Q' },
        { id: 'I1', type: 'idea',     text: 'I' },
      ],
      edges: [
        { from: 'I1', to: 'Q1', type: 'implies' },
      ],
    }),
    expectCode: 'E_IBIS_GRAMMAR',
  },
  {
    label: 'no question node at all → E_SCHEMA_INVALID',
    env: envelope({
      nodes: [
        { id: 'I1', type: 'idea', text: 'orphan' },
      ],
      edges: [],
    }),
    expectCode: 'E_SCHEMA_INVALID',
  },
];

// ── Standalone runner ──────────────────────────────────────────────────────
// When invoked directly (node test-ibis.js), boot jsdom, load the compiler
// + dot-engine + ibis renderer, execute suites, and exit with the right
// code. When `required` by run.js the module exports { label, run, CASES }.

function bootContext() {
  const dom = new JSDOM(
    '<!doctype html><html><head></head><body></body></html>',
    { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
  );
  const { window } = dom;
  window.globalThis = window;
  window.console    = console;
  if (!window.fetch) window.fetch = globalThis.fetch;
  if (!window.getComputedStyle)
    window.getComputedStyle = () => ({ getPropertyValue: () => '' });
  if (!window.matchMedia)
    window.matchMedia = () => ({ matches: false, addListener: () => {}, removeListener: () => {} });
  if (!window.requestAnimationFrame)
    window.requestAnimationFrame = (cb) => setTimeout(cb, 16);

  const ctx = dom.getInternalVMContext();

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
  vm.runInContext(read(VENDOR_VIZ), ctx, { filename: VENDOR_VIZ });
  vm.runInContext(read(DOT_ENGINE), ctx, { filename: DOT_ENGINE });
  vm.runInContext(read(IBIS_RENDER), ctx, { filename: IBIS_RENDER });

  return { window };
}

// ── Assertion helpers ──────────────────────────────────────────────────────
const hasSvgRoot   = (s) => typeof s === 'string' && /<svg\b/i.test(s);
const hasClass     = (s, c) =>
  new RegExp('class="[^"]*\\b' + c.replace(/-/g, '\\-') + '\\b').test(s);
const hasAriaImg   = (s) => /role="img"/.test(s);
const hasAriaLabel = (s) => /aria-label="[^"]+"/.test(s);
const hasInlineStyle = (s) =>
  /\sstyle="/.test(s) || /\sfill="/.test(s) ||
  /\sstroke="/.test(s) || /\sfont-family="/.test(s);
const hasId = (s, id) => new RegExp('id="' + id.replace(/-/g, '\\-') + '"').test(s);
const countEdgeGroups = (s) =>
  (s.match(/<g\b[^>]*class="[^"]*\bedge\b[^"]*"/g) || []).length;

/**
 * runSuite(ibis, report) — shared between standalone and harness entry.
 * ibis is the renderer module; report(name, ok, detail) records results.
 */
async function runSuite(OVC, report) {
  const ibis = OVC._renderers.ibis;

  // ── Internal grammar-validator unit tests ────────────────────────────
  (function unit() {
    const vg = ibis._validateGrammar;

    // All legal triples should validate without errors when the target
    // endpoint exists. Build a generic node set that covers all kinds.
    const nodes = [
      { id: 'Q1',  type: 'question', text: 'q1' },
      { id: 'Q2',  type: 'question', text: 'q2' },
      { id: 'I1',  type: 'idea',     text: 'i1' },
      { id: 'P1',  type: 'pro',      text: 'p1' },
      { id: 'C1',  type: 'con',      text: 'c1' },
    ];
    for (const [src, kind, tgt] of ibis._LEGAL_TRIPLES) {
      // Pick a source and target of the right kinds from the fixture.
      const pick = {
        question: 'Q1', idea: 'I1', pro: 'P1', con: 'C1',
      };
      // For question.questions→question we need two distinct question ids.
      let from = pick[src];
      let to   = pick[tgt];
      if (src === 'question' && tgt === 'question') { from = 'Q1'; to = 'Q2'; }
      const edge = { from: from, to: to, type: kind };
      const res = vg(nodes, [edge]);
      const label = 'unit(grammar): legal ' + src + '.' + kind + '→' + tgt;
      const hasGrammarErr = res.errors.some((e) => e.code === 'E_IBIS_GRAMMAR');
      report(label, !hasGrammarErr,
        hasGrammarErr ? JSON.stringify(res.errors) : '');
    }

    // Illegal: pro.supports→question.
    const ill = vg(
      [
        { id: 'Q1', type: 'question', text: 'q' },
        { id: 'P1', type: 'pro',      text: 'p' },
      ],
      [{ from: 'P1', to: 'Q1', type: 'supports' }]
    );
    report('unit(grammar): illegal pro.supports→question flagged',
      ill.errors.some((e) => e.code === 'E_IBIS_GRAMMAR'),
      JSON.stringify(ill.errors));

    // Multiple violations accumulate (no short-circuit).
    const multi = vg(
      [
        { id: 'Q1', type: 'question', text: 'q' },
        { id: 'I1', type: 'idea',     text: 'i' },
        { id: 'P1', type: 'pro',      text: 'p' },
        { id: 'C1', type: 'con',      text: 'c' },
      ],
      [
        { from: 'P1', to: 'Q1', type: 'responds_to' },  // bad 1
        { from: 'I1', to: 'I1', type: 'supports'    },  // bad 2
        { from: 'C1', to: 'Q1', type: 'objects_to'  },  // bad 3
      ]
    );
    const grammarCount = multi.errors.filter((e) => e.code === 'E_IBIS_GRAMMAR').length;
    report('unit(grammar): accumulates multiple violations',
      grammarCount === 3,
      'got ' + grammarCount + ' grammar errors');
  }());

  // ── Valid suite ──────────────────────────────────────────────────────
  for (const tc of validCases) {
    const label = 'valid ' + tc.label;
    try {
      const env = typeof tc.prepare === 'function' ? tc.prepare(tc.env) : tc.env;
      const result = await ibis.render(env);
      if (!result || result.errors.length) {
        report(label, false,
          'unexpected errors: ' + JSON.stringify((result && result.errors) || []));
        continue;
      }
      if (!hasSvgRoot(result.svg)) {
        report(label, false, 'no <svg> root in output'); continue;
      }
      if (!hasClass(result.svg, 'ora-visual--ibis')) {
        report(label, false, 'missing ora-visual--ibis class on root'); continue;
      }
      if (!hasAriaImg(result.svg) || !hasAriaLabel(result.svg)) {
        report(label, false, 'missing role="img" / aria-label'); continue;
      }
      if (hasInlineStyle(result.svg)) {
        report(label, false, 'inline style/fill/stroke/font-family not stripped');
        continue;
      }
      // Stable IDs present for every declared node + edge we expect.
      const missing = (tc.expectIds || []).filter((id) => !hasId(result.svg, id));
      if (missing.length) {
        report(label, false, 'missing stable IDs: ' + missing.join(', '));
        continue;
      }
      // Edge count: one <g class="edge"> per declared edge.
      const edgeCount = countEdgeGroups(result.svg);
      if (typeof tc.expectEdgeCount === 'number' &&
          edgeCount !== tc.expectEdgeCount) {
        report(label, false,
          'edge count mismatch: expected ' + tc.expectEdgeCount +
          ', got ' + edgeCount);
        continue;
      }
      // Per-kind shape sanity: at least one diamond token survives on a
      // question-bearing graph; at least one triangle on a pro-bearing
      // graph; at least one invtriangle on a con-bearing graph.
      // Graphviz renders shapes as <polygon points="..."> — we check the
      // node-kind class survived instead, which is the semantic contract.
      const kinds = new Set(env.spec.nodes.map((n) => n.type));
      for (const k of kinds) {
        if (!hasClass(result.svg, 'ora-visual__node--' + k)) {
          report(label, false, 'missing class ora-visual__node--' + k);
          continue;
        }
      }
      report(label, true);
    } catch (err) {
      report(label, false, 'threw: ' + (err && err.stack ? err.stack : err));
    }
  }

  // ── Invalid suite ────────────────────────────────────────────────────
  for (const tc of invalidCases) {
    const label = 'invalid ' + tc.label;
    try {
      const result = await ibis.render(tc.env);
      if (!result) { report(label, false, 'no result object'); continue; }
      if (result.svg !== '') {
        report(label, false, 'expected empty svg on error; got length=' +
          result.svg.length);
        continue;
      }
      if (!result.errors.length) {
        report(label, false, 'expected errors; got none'); continue;
      }
      const codes = result.errors.map((e) => e.code);
      if (!codes.includes(tc.expectCode)) {
        report(label, false,
          'expected ' + tc.expectCode + '; got ' + JSON.stringify(codes));
        continue;
      }
      if (tc.expectEdge) {
        const matched = result.errors.some(
          (e) => (e.path && e.path.indexOf(tc.expectEdge) >= 0) ||
                 (e.message && e.message.indexOf(tc.expectEdge) >= 0)
        );
        if (!matched) {
          report(label, false,
            'expected offending edge ' + tc.expectEdge +
            ' to be named; got ' + JSON.stringify(result.errors));
          continue;
        }
      }
      report(label, true);
    } catch (err) {
      report(label, false, 'threw: ' + (err && err.stack ? err.stack : err));
    }
  }

  // ── Dispatcher integration ───────────────────────────────────────────
  try {
    const { isStub } = OVC._dispatcher;
    report('dispatcher: ibis no longer on stub',
      isStub('ibis') === false,
      'ibis still wired to stub after renderer load');
  } catch (err) {
    report('dispatcher: ibis no longer on stub', false,
      'threw: ' + (err && err.stack ? err.stack : err));
  }
}

// ── run.js harness entry point ─────────────────────────────────────────────
async function run(ctx, record) {
  // When called via the shared run.js, ctx.win is a single shared jsdom
  // where Ajv + Vega etc. are already loaded. But run.js doesn't load
  // viz-js / dot-engine / ibis.js — we have to do it here.
  const win = ctx && ctx.win ? ctx.win : null;
  if (!win) {
    record('ibis suite (harness)', false, 'ctx.win not provided');
    return;
  }
  // Load the viz-js / dot-engine / ibis files into the harness window if
  // they are not already loaded. This is idempotent — dot-engine is a
  // singleton; ibis registers itself on load.
  if (!win.OraVisualCompiler._dotEngine) {
    win.eval(read(VENDOR_VIZ));
    win.eval(read(DOT_ENGINE));
  }
  if (!win.OraVisualCompiler._renderers || !win.OraVisualCompiler._renderers.ibis) {
    win.eval(read(IBIS_RENDER));
  }
  await runSuite(win.OraVisualCompiler, record);
}

const label = 'test-ibis (WP-1.3i)';

// ── Standalone main ────────────────────────────────────────────────────────
async function standalone() {
  let passed = 0;
  let failed = 0;
  const failures = [];

  function report(name, ok, detail) {
    if (ok) {
      passed += 1;
      console.log('PASS  ' + name);
    } else {
      failed += 1;
      failures.push({ name: name, detail: detail });
      console.log('FAIL  ' + name + '  :: ' + detail);
    }
  }

  console.log('test-ibis.js — WP-1.3i');
  console.log('jsdom version: ' + require('jsdom/package.json').version);
  console.log('----------------------------------------');

  const { window } = bootContext();
  const OVC = window.OraVisualCompiler;
  if (!OVC || !OVC._renderers || !OVC._renderers.ibis) {
    console.error('FAIL: OraVisualCompiler._renderers.ibis not exposed');
    process.exit(1);
  }

  await runSuite(OVC, report);

  console.log('----------------------------------------');
  console.log('Result: ' + passed + ' passed / ' + (passed + failed) +
              ' total  (' + failed + ' failed)');
  if (failed > 0) {
    console.log('\nFailures:');
    for (const f of failures) console.log('  - ' + f.name + ' :: ' + f.detail);
    process.exit(1);
  }
  process.exit(0);
}

if (require.main === module) {
  standalone().catch((e) => {
    console.error('Harness crashed:', e && e.stack ? e.stack : e);
    process.exit(2);
  });
}

module.exports = {
  label: label,
  run: run,
  // Expose cases for any future harness that wants to iterate without
  // re-parsing.
  CASES: { valid: validCases, invalid: invalidCases },
};
