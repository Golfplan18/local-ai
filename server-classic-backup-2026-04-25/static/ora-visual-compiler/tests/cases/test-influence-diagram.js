/**
 * tests/cases/test-influence-diagram.js — WP-1.3e regression suite.
 *
 * Exports { label, run(ctx, record) } compatible with tests/run.js. Also
 * runnable standalone via `node test-influence-diagram.js` in which case
 * it bootstraps its own jsdom context (modeled on test-causal-dag.js).
 *
 * Coverage:
 *   - 5 valid specs:
 *       1. minimal 1-decision 1-chance 1-value
 *       2. multi-decision with temporal order (C1 → D1 → D2 → V1)
 *       3. deterministic node contributing to value
 *       4. functional arcs only (deterministic influence chain)
 *       5. mixed informational + functional arcs
 *   - 4 invalid specs:
 *       1. zero value nodes         → E_SCHEMA_INVALID
 *       2. two value nodes          → E_SCHEMA_INVALID
 *       3. temporal order violation → E_SCHEMA_INVALID
 *       4. cycle in functional subgraph → E_GRAPH_CYCLE
 *   - SVG assertions on a subset:
 *       exactly one value-node class present
 *       shape-per-kind in DOT emission (via internal _buildDot)
 *       informational arcs rendered with style=dashed (DOT or SVG)
 *       stable ids id-node-<id> and id-edge-<from>-<to> present
 */

'use strict';

const fs   = require('fs');
const path = require('path');

// ── Test fixtures ────────────────────────────────────────────────────────
function envelope(spec, overrides) {
  const base = {
    schema_version: '0.2',
    id: 'fig-test-influence-diagram',
    type: 'influence_diagram',
    mode_context: 'decision_under_uncertainty',
    relation_to_prose: 'integrated',
    spec: spec,
    semantic_description: {
      level_1_elemental: 'Test influence diagram',
      level_2_statistical: 'n/a',
      level_3_perceptual: 'n/a',
      level_4_contextual: null,
      short_alt: 'test ID',
      data_table_fallback: null,
    },
    title: 'Test influence diagram',
  };
  return Object.assign(base, overrides || {});
}

// ── Valid cases ─────────────────────────────────────────────────────────
const validCases = [
  {
    label: 'minimal 1-decision 1-chance 1-value',
    env: envelope({
      nodes: [
        { id: 'D1', label: 'Launch?', kind: 'decision' },
        { id: 'C1', label: 'Demand',  kind: 'chance'   },
        { id: 'V1', label: 'Profit',  kind: 'value'    },
      ],
      arcs: [
        { from: 'C1', to: 'D1', type: 'informational' },
        { from: 'D1', to: 'V1', type: 'functional'    },
        { from: 'C1', to: 'V1', type: 'functional'    },
      ],
    }),
    expectNodeIds: ['id-node-D1', 'id-node-C1', 'id-node-V1'],
    expectEdgeIds: ['id-edge-C1-D1', 'id-edge-D1-V1', 'id-edge-C1-V1'],
  },
  {
    label: 'multi-decision with temporal_order',
    env: envelope({
      nodes: [
        { id: 'C1', label: 'Market signal', kind: 'chance'   },
        { id: 'D1', label: 'R&D invest?',   kind: 'decision' },
        { id: 'C2', label: 'R&D outcome',   kind: 'chance'   },
        { id: 'D2', label: 'Launch?',       kind: 'decision' },
        { id: 'V1', label: 'NPV',           kind: 'value'    },
      ],
      arcs: [
        { from: 'C1', to: 'D1', type: 'informational' },
        { from: 'D1', to: 'C2', type: 'functional'    },
        { from: 'C2', to: 'D2', type: 'informational' },
        { from: 'D1', to: 'D2', type: 'informational' },
        { from: 'D2', to: 'V1', type: 'functional'    },
        { from: 'C2', to: 'V1', type: 'functional'    },
      ],
      temporal_order: ['D1', 'D2'],
    }),
    expectNodeIds: ['id-node-D1', 'id-node-D2', 'id-node-V1'],
    expectRankSubgraphs: 2,
  },
  {
    label: 'deterministic node in chain',
    env: envelope({
      nodes: [
        { id: 'D1', label: 'Price',     kind: 'decision'      },
        { id: 'C1', label: 'Quantity',  kind: 'chance'        },
        { id: 'R1', label: 'Revenue',   kind: 'deterministic' },
        { id: 'V1', label: 'Profit',    kind: 'value'         },
      ],
      arcs: [
        { from: 'D1', to: 'R1', type: 'functional' },
        { from: 'C1', to: 'R1', type: 'functional' },
        { from: 'R1', to: 'V1', type: 'functional' },
      ],
    }),
    expectShape: { 'R1': 'box', peripheries: true },
  },
  {
    label: 'functional arcs only (no informational)',
    env: envelope({
      nodes: [
        { id: 'D1', label: 'Choice', kind: 'decision' },
        { id: 'C1', label: 'Noise',  kind: 'chance'   },
        { id: 'V1', label: 'Util',   kind: 'value'    },
      ],
      arcs: [
        { from: 'D1', to: 'V1', type: 'functional' },
        { from: 'C1', to: 'V1', type: 'functional' },
      ],
    }),
  },
  {
    label: 'mixed informational + functional arcs',
    env: envelope({
      nodes: [
        { id: 'C1', label: 'Forecast',  kind: 'chance'        },
        { id: 'C2', label: 'Outcome',   kind: 'chance'        },
        { id: 'D1', label: 'Bet?',      kind: 'decision'      },
        { id: 'R1', label: 'Cashflow',  kind: 'deterministic' },
        { id: 'V1', label: 'NPV',       kind: 'value'         },
      ],
      arcs: [
        { from: 'C1', to: 'D1', type: 'informational' },
        { from: 'D1', to: 'R1', type: 'functional'    },
        { from: 'C2', to: 'R1', type: 'functional'    },
        { from: 'R1', to: 'V1', type: 'functional'    },
      ],
      temporal_order: ['D1'],
    }),
    expectDashedCount: 1, // exactly one informational arc
  },
];

// ── Invalid cases ────────────────────────────────────────────────────────
const invalidCases = [
  {
    label: 'zero value nodes',
    env: envelope({
      nodes: [
        { id: 'D1', label: 'Decide', kind: 'decision' },
        { id: 'C1', label: 'Chance', kind: 'chance'   },
      ],
      arcs: [
        { from: 'C1', to: 'D1', type: 'informational' },
      ],
    }),
    expectCode: 'E_SCHEMA_INVALID',
    expectMessageIncludes: 'exactly one value node',
  },
  {
    label: 'two value nodes',
    env: envelope({
      nodes: [
        { id: 'D1', label: 'Decide',   kind: 'decision' },
        { id: 'V1', label: 'Profit',   kind: 'value'    },
        { id: 'V2', label: 'Goodwill', kind: 'value'    },
      ],
      arcs: [
        { from: 'D1', to: 'V1', type: 'functional' },
        { from: 'D1', to: 'V2', type: 'functional' },
      ],
    }),
    expectCode: 'E_SCHEMA_INVALID',
    expectMessageIncludes: 'exactly one value node',
  },
  {
    label: 'temporal order violation (later decision informs earlier)',
    env: envelope({
      nodes: [
        { id: 'D1', label: 'First',  kind: 'decision' },
        { id: 'D2', label: 'Second', kind: 'decision' },
        { id: 'V1', label: 'Value',  kind: 'value'    },
      ],
      arcs: [
        { from: 'D2', to: 'D1', type: 'informational' }, // D2 informs D1 but D1 is earlier
        { from: 'D1', to: 'V1', type: 'functional'    },
        { from: 'D2', to: 'V1', type: 'functional'    },
      ],
      temporal_order: ['D1', 'D2'],
    }),
    expectCode: 'E_SCHEMA_INVALID',
    expectMessageIncludes: 'temporal order',
  },
  {
    label: 'cycle in functional subgraph',
    env: envelope({
      nodes: [
        { id: 'A',  label: 'A',      kind: 'deterministic' },
        { id: 'B',  label: 'B',      kind: 'deterministic' },
        { id: 'C',  label: 'C',      kind: 'deterministic' },
        { id: 'V1', label: 'Value',  kind: 'value'         },
      ],
      arcs: [
        { from: 'A', to: 'B',  type: 'functional' },
        { from: 'B', to: 'C',  type: 'functional' },
        { from: 'C', to: 'A',  type: 'functional' },  // cycle
        { from: 'C', to: 'V1', type: 'functional' },
      ],
    }),
    expectCode: 'E_GRAPH_CYCLE',
  },
];

// ── Assertion helpers ────────────────────────────────────────────────────
const hasSvgRoot   = (s) => typeof s === 'string' && /<svg\b/i.test(s);
const hasClass     = (s, c) => new RegExp('class="[^"]*\\b' + c.replace(/-/g, '\\-') + '\\b').test(s);
const hasAriaImg   = (s) => /role="img"/.test(s);
const hasAriaLabel = (s) => /aria-label="[^"]+"/.test(s);
const hasId        = (s, id) => new RegExp('id="' + id.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&') + '"').test(s);
const hasInlineStyle = (s) => /\sstyle="/.test(s) || /\sfill="/.test(s) ||
                              /\sstroke="/.test(s) || /\sfont-family="/.test(s);
const countMatches = (s, re) => {
  const m = s.match(re);
  return m ? m.length : 0;
};

// ── Suite body ───────────────────────────────────────────────────────────
async function runSuite(ctx, record) {
  const OVC = ctx.win.OraVisualCompiler;
  const renderer = OVC._renderers && OVC._renderers.influenceDiagram;

  if (!renderer) {
    record('influence_diagram: renderer registered', false,
      'OraVisualCompiler._renderers.influenceDiagram missing');
    return;
  }

  // Dispatcher integration — type no longer on stub after renderer load.
  record(
    'influence_diagram: dispatcher no longer on stub',
    OVC._dispatcher.isStub('influence_diagram') === false,
    OVC._dispatcher.isStub('influence_diagram') ? 'still on stub' : ''
  );

  // Internal unit tests of invariant helpers.
  const int = renderer;
  const vcCount = int._countValueNodes([
    { id: 'a', kind: 'decision' },
    { id: 'b', kind: 'value' },
    { id: 'c', kind: 'chance' },
  ]);
  record(
    'unit(count value nodes): one value',
    vcCount === 1,
    'got ' + vcCount
  );

  const tcOk = int._checkTemporalConsistency(
    [
      { id: 'D1', kind: 'decision' },
      { id: 'D2', kind: 'decision' },
      { id: 'V1', kind: 'value' },
    ],
    [
      { from: 'D1', to: 'D2', type: 'informational' },
    ],
    ['D1', 'D2']
  );
  record(
    'unit(temporal): earlier-decided info-arc ok',
    tcOk.ok === true,
    JSON.stringify(tcOk)
  );

  const tcBad = int._checkTemporalConsistency(
    [
      { id: 'D1', kind: 'decision' },
      { id: 'D2', kind: 'decision' },
    ],
    [
      { from: 'D2', to: 'D1', type: 'informational' },
    ],
    ['D1', 'D2']
  );
  record(
    'unit(temporal): later-decided info-arc flagged',
    tcBad.ok === false,
    JSON.stringify(tcBad)
  );

  const noCyc = int._functionalSubgraphCycle(
    [
      { id: 'A', kind: 'deterministic' },
      { id: 'V', kind: 'value' },
    ],
    [{ from: 'A', to: 'V', type: 'functional' }],
    'V'
  );
  record(
    'unit(func-cycle): acyclic returns null',
    noCyc === null,
    'got ' + JSON.stringify(noCyc)
  );

  const withCyc = int._functionalSubgraphCycle(
    [
      { id: 'A', kind: 'deterministic' },
      { id: 'B', kind: 'deterministic' },
      { id: 'V', kind: 'value' },
    ],
    [
      { from: 'A', to: 'B', type: 'functional' },
      { from: 'B', to: 'A', type: 'functional' },
      { from: 'B', to: 'V', type: 'functional' },
    ],
    'V'
  );
  record(
    'unit(func-cycle): cycle detected',
    Array.isArray(withCyc) && withCyc.length >= 2,
    'got ' + JSON.stringify(withCyc)
  );

  // _buildDot sanity check: shapes per kind.
  const dotSpec = {
    nodes: [
      { id: 'D', label: 'D', kind: 'decision' },
      { id: 'C', label: 'C', kind: 'chance' },
      { id: 'V', label: 'V', kind: 'value' },
      { id: 'R', label: 'R', kind: 'deterministic' },
    ],
    arcs: [
      { from: 'C', to: 'D', type: 'informational' },
      { from: 'D', to: 'R', type: 'functional' },
      { from: 'C', to: 'R', type: 'functional' },
      { from: 'R', to: 'V', type: 'functional' },
    ],
    temporal_order: null,
    nodeIds: new Set(['D', 'C', 'V', 'R']),
  };
  const dotStr = int._buildDot({ title: '' }, dotSpec);
  record(
    'unit(buildDot): decision → shape=box',
    /"D"[^\]]*shape=box/.test(dotStr),
    dotStr.slice(0, 300)
  );
  record(
    'unit(buildDot): chance → shape=ellipse',
    /"C"[^\]]*shape=ellipse/.test(dotStr),
    ''
  );
  record(
    'unit(buildDot): value → shape=octagon',
    /"V"[^\]]*shape=octagon/.test(dotStr),
    ''
  );
  record(
    'unit(buildDot): deterministic → peripheries=2',
    /"R"[^\]]*peripheries=2/.test(dotStr),
    ''
  );
  record(
    'unit(buildDot): informational arc → style=dashed',
    /"C"\s*->\s*"D"[^\]]*style=dashed/.test(dotStr),
    ''
  );
  record(
    'unit(buildDot): functional arc has no style=dashed',
    !/"D"\s*->\s*"R"[^\]]*style=dashed/.test(dotStr),
    ''
  );

  // ── Valid cases: render and inspect ────────────────────────────────
  for (const tc of validCases) {
    const label = 'valid: ' + tc.label;
    try {
      const result = await renderer.render(tc.env);
      if (!result || result.errors.length) {
        record(label, false, 'unexpected errors: ' +
          JSON.stringify((result && result.errors) || []));
        continue;
      }
      if (!hasSvgRoot(result.svg)) {
        record(label, false, 'no <svg> root in output');
        continue;
      }
      if (!hasClass(result.svg, 'ora-visual--influence_diagram')) {
        record(label, false, 'missing ora-visual--influence_diagram class');
        continue;
      }
      if (!hasAriaImg(result.svg) || !hasAriaLabel(result.svg)) {
        record(label, false, 'missing role="img" / aria-label on root');
        continue;
      }
      if (hasInlineStyle(result.svg)) {
        record(label, false, 'inline styles (fill/stroke/style/font-family) not stripped');
        continue;
      }

      // Exactly one value-node class present in the SVG.
      const valueCount = countMatches(
        result.svg,
        /class="[^"]*\bora-visual__id\-value\b[^"]*"/g
      );
      if (valueCount !== 1) {
        record(label, false,
          'expected exactly one value-node class instance; got ' + valueCount);
        continue;
      }

      // Stable IDs present on the expected nodes / edges.
      if (tc.expectNodeIds) {
        const missing = tc.expectNodeIds.filter((id) => !hasId(result.svg, id));
        if (missing.length) {
          record(label, false,
            'missing stable node ids: ' + missing.join(', '));
          continue;
        }
      }
      if (tc.expectEdgeIds) {
        const missing = tc.expectEdgeIds.filter((id) => !hasId(result.svg, id));
        if (missing.length) {
          record(label, false,
            'missing stable edge ids: ' + missing.join(', '));
          continue;
        }
      }

      record(label, true, 'svg ' + result.svg.length + ' chars');
    } catch (err) {
      record(label, false, 'threw: ' + (err && err.stack ? err.stack : err));
    }
  }

  // ── Invalid cases: expect structured errors, empty svg ─────────────
  for (const tc of invalidCases) {
    const label = 'invalid: ' + tc.label;
    try {
      const result = await renderer.render(tc.env);
      if (!result) {
        record(label, false, 'no result object');
        continue;
      }
      if (!result.errors.length) {
        record(label, false, 'expected errors but got none; svg len=' + result.svg.length);
        continue;
      }
      const codes = result.errors.map((e) => e.code);
      if (!codes.includes(tc.expectCode)) {
        record(label, false,
          'expected ' + tc.expectCode + ' but got ' + JSON.stringify(codes));
        continue;
      }
      if (tc.expectMessageIncludes) {
        const matched = result.errors.some((e) =>
          typeof e.message === 'string' &&
          e.message.indexOf(tc.expectMessageIncludes) >= 0);
        if (!matched) {
          record(label, false,
            'error message did not include ' + JSON.stringify(tc.expectMessageIncludes) +
            '; got ' + JSON.stringify(result.errors.map((e) => e.message)));
          continue;
        }
      }
      if (result.svg !== '') {
        record(label, false, 'expected empty svg on error, got length=' + result.svg.length);
        continue;
      }
      record(label, true, 'rejected with ' + codes.join(','));
    } catch (err) {
      record(label, false, 'threw: ' + (err && err.stack ? err.stack : err));
    }
  }

  // ── Informational-arc dashed rendering: structural SVG check ───────
  // Dashed is carried via `stroke-dasharray` on a <path> OR via our own
  // `ora-visual__arc--informational` class + theme CSS. The SVG output
  // from Graphviz has `stroke-dasharray` stripped by dot-engine (it's in
  // STRIP_ATTRS). So the only surface check that works after strip is
  // the semantic class. We verify the informational class appears on
  // exactly as many edges as we have informational arcs.
  for (const tc of validCases) {
    if (!tc.expectDashedCount) continue;
    const label = 'svg: ' + tc.label + ' — ' +
      tc.expectDashedCount + ' informational arc class(es) present';
    try {
      const result = await renderer.render(tc.env);
      if (!result || result.errors.length) {
        record(label, false, 'render errored unexpectedly');
        continue;
      }
      const count = countMatches(
        result.svg,
        /class="[^"]*\bora-visual__arc\-\-informational\b[^"]*"/g
      );
      record(label, count === tc.expectDashedCount,
        'expected ' + tc.expectDashedCount + ', got ' + count);
    } catch (err) {
      record(label, false, 'threw: ' + (err && err.stack ? err.stack : err));
    }
  }
}

module.exports = {
  label: 'Influence diagram (WP-1.3e)',
  run: runSuite,
};

// ── Standalone runner ────────────────────────────────────────────────────
// If this file is executed directly with `node test-influence-diagram.js`,
// it bootstraps its own jsdom context (mirrors test-causal-dag.js) and
// runs the suite, then exits non-zero on failures.
if (require.main === module) {
  (async function main() {
    const vm = require('vm');
    const { JSDOM } = require('jsdom');

    const COMPILER_DIR = path.resolve(__dirname, '..', '..');
    const VENDOR_VIZ   = path.join(COMPILER_DIR, 'vendor', 'viz-js', 'viz-standalone.js');

    const read = (p) => fs.readFileSync(p, 'utf-8');

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
    vm.runInContext(read(path.join(COMPILER_DIR, 'dot-engine.js')), ctx,
      { filename: path.join(COMPILER_DIR, 'dot-engine.js') });
    vm.runInContext(read(path.join(COMPILER_DIR, 'renderers', 'influence-diagram.js')), ctx,
      { filename: path.join(COMPILER_DIR, 'renderers', 'influence-diagram.js') });

    let passed = 0, failed = 0;
    const failures = [];
    function record(name, ok, detail) {
      if (ok) { passed++; console.log('PASS  ' + name); }
      else    { failed++; failures.push({ name, detail });
                console.log('FAIL  ' + name + '  :: ' + (detail || '')); }
    }

    console.log('test-influence-diagram.js — WP-1.3e');
    console.log('----------------------------------------');
    await runSuite({ win: window }, record);
    console.log('----------------------------------------');
    console.log('Result: ' + passed + ' passed / ' + (passed + failed) + ' total  (' + failed + ' failed)');
    if (failed > 0) {
      console.log('\nFailures:');
      for (const f of failures) console.log('  - ' + f.name + ' :: ' + (f.detail || ''));
      process.exit(1);
    }
    process.exit(0);
  })().catch((e) => {
    console.error('Harness crashed:', e && e.stack ? e.stack : e);
    process.exit(2);
  });
}
