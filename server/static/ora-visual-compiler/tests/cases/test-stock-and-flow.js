/**
 * tests/cases/test-stock-and-flow.js
 *
 * WP-1.3b regression suite for the stock-and-flow renderer.
 *
 * Covers:
 *   - 5 valid specs: single stock in/out with clouds, two-stock inter-stock
 *     flow, three-stock chain, auxiliary+info-link into a flow, and a stock
 *     with bidirectional flow endpoints (in from cloud + out to cloud).
 *   - 3 invalid specs: info-link cycle, unresolved flow endpoint,
 *     dimensionally inconsistent units (warning-only — expects the warning
 *     to be present but render to succeed).
 *   - Dispatcher integration: stock_and_flow no longer on the stub.
 *   - Structural SVG checks: root classes, stable IDs, per-element IDs,
 *     every stock has attached flows (warning surfaced when it doesn't),
 *     every declared cloud rendered.
 *
 * Exports { label, run(ctx, record) } — the standard harness contract from
 * tests/run.js.
 */

'use strict';

const fs   = require('fs');
const path = require('path');

// ── Fixtures ─────────────────────────────────────────────────────────────
function envelope(spec, overrides) {
  const base = {
    schema_version: '0.2',
    id: 'fig-test-stock-and-flow',
    type: 'stock_and_flow',
    mode_context: 'root_cause_analysis',
    relation_to_prose: 'integrated',
    spec: spec,
    semantic_description: {
      level_1_elemental: 'Test stock-and-flow diagram',
      level_2_statistical: null,
      level_3_perceptual: null,
      level_4_contextual: null,
      short_alt: 'test SAF',
      data_table_fallback: null,
    },
    title: 'Test Stock-and-Flow',
    caption: 'Source: test; Period: synthetic; n=na',
  };
  return Object.assign(base, overrides || {});
}

// ── Valid cases ─────────────────────────────────────────────────────────
const VALID_CASES = [
  {
    label: 'single stock with inflow from cloud',
    env: envelope({
      stocks: [{ id: 'pop', label: 'Population', initial: 100, unit: 'people' }],
      flows: [{ id: 'birth', label: 'Births', from: 'src', to: 'pop', unit: 'people/year' }],
      clouds: [{ id: 'src' }],
    }),
    expectIds: ['saf-stock-pop', 'saf-flow-birth', 'saf-cloud-src'],
  },
  {
    label: 'in-out with clouds on both ends',
    env: envelope({
      stocks: [{ id: 'inv', label: 'Inventory', initial: 0, unit: 'units' }],
      flows: [
        { id: 'rcv', label: 'Receive', from: 'src', to: 'inv', unit: 'units/day' },
        { id: 'shp', label: 'Ship',    from: 'inv', to: 'snk', unit: 'units/day' },
      ],
      clouds: [{ id: 'src' }, { id: 'snk' }],
    }),
    expectIds: [
      'saf-stock-inv',
      'saf-flow-rcv',
      'saf-flow-shp',
      'saf-cloud-src',
      'saf-cloud-snk',
    ],
  },
  {
    label: 'two stocks with inter-stock flow',
    env: envelope({
      stocks: [
        { id: 'upstream',   label: 'Upstream',   unit: 'widgets' },
        { id: 'downstream', label: 'Downstream', unit: 'widgets' },
      ],
      flows: [
        { id: 'transfer', label: 'Transfer',
          from: 'upstream', to: 'downstream',
          unit: 'widgets/hour' },
      ],
    }),
    expectIds: ['saf-stock-upstream', 'saf-stock-downstream', 'saf-flow-transfer'],
  },
  {
    label: 'chain of three stocks',
    env: envelope({
      stocks: [
        { id: 'a', label: 'A' },
        { id: 'b', label: 'B' },
        { id: 'c', label: 'C' },
      ],
      flows: [
        { id: 'ab', label: 'A→B', from: 'a', to: 'b' },
        { id: 'bc', label: 'B→C', from: 'b', to: 'c' },
      ],
    }),
    expectIds: [
      'saf-stock-a', 'saf-stock-b', 'saf-stock-c',
      'saf-flow-ab', 'saf-flow-bc',
    ],
  },
  {
    label: 'auxiliary with info link to flow',
    env: envelope({
      stocks: [{ id: 'pop', label: 'Population', unit: 'people' }],
      flows: [{ id: 'birth', label: 'Births', from: 'src', to: 'pop', unit: 'people/year' }],
      clouds: [{ id: 'src' }],
      auxiliaries: [{ id: 'rate', label: 'Birth rate' }],
      info_links: [
        { from: 'pop',  to: 'birth' },
        { from: 'rate', to: 'birth' },
      ],
    }),
    expectIds: [
      'saf-stock-pop',
      'saf-flow-birth',
      'saf-cloud-src',
      'saf-aux-rate',
    ],
  },
];

// ── Invalid / warning cases ──────────────────────────────────────────────
const INVALID_CASES = [
  {
    label: 'info-link cycle across two auxiliaries',
    env: envelope({
      stocks: [{ id: 'pop', label: 'Pop' }],
      flows: [{ id: 'f1', label: 'F1', from: 'cloud', to: 'pop' }],
      auxiliaries: [
        { id: 'a1', label: 'A1' },
        { id: 'a2', label: 'A2' },
      ],
      info_links: [
        { from: 'a1', to: 'a2' },
        { from: 'a2', to: 'a1' },
      ],
    }),
    expectCode: 'E_GRAPH_CYCLE',
  },
  {
    label: 'unresolved flow endpoint',
    env: envelope({
      stocks: [{ id: 'pop', label: 'Pop' }],
      flows: [{ id: 'f1', label: 'F1', from: 'nowhere', to: 'pop' }],
    }),
    expectCode: 'E_UNRESOLVED_REF',
  },
];

// ── Dense-layout regression case ─────────────────────────────────────────
// A single stock with many auxiliaries used to collapse several aux boxes
// onto the same point (the fixed ≤40px stagger could not separate them),
// driving the artifact-adversarial overlap check past its 5% Critical
// threshold (46–72% measured) and suppressing the entire render to 0 bytes.
// The aux grid-packing layout must keep every aux bounding box clear.
// Spec mirrors the cash-dynamics "premium" snapshot: 1 stock, 4 flows, 2
// declared clouds, 3 chained feedback auxiliaries.
const DENSE_SPEC = {
  stocks: [{ id: 'cash', label: 'Cash on Hand', initial: 0, unit: '$' }],
  flows: [
    { id: 'revenue',     label: 'Revenue',              from: 'src',  to: 'cash', unit: '$/month' },
    { id: 'fundraising', label: 'Fundraising proceeds', from: 'src',  to: 'cash', unit: '$' },
    { id: 'payroll',     label: 'Payroll',              from: 'cash', to: 'sink', unit: '$/month' },
    { id: 'opex',        label: 'OpEx',                 from: 'cash', to: 'sink', unit: '$/month' },
  ],
  clouds: [{ id: 'src' }, { id: 'sink' }],
  auxiliaries: [
    { id: 'headcount',           label: 'Headcount' },
    { id: 'investor_confidence', label: 'Investor confidence' },
    { id: 'fundraising_effort',  label: 'Fundraising effort' },
  ],
  info_links: [
    { from: 'cash',                to: 'headcount' },
    { from: 'headcount',           to: 'revenue' },
    { from: 'headcount',           to: 'payroll' },
    { from: 'revenue',             to: 'investor_confidence' },
    { from: 'investor_confidence', to: 'fundraising' },
    { from: 'cash',                to: 'fundraising_effort' },
    { from: 'fundraising_effort',  to: 'fundraising' },
  ],
};

// Dimensionally inconsistent units is a warning, NOT a blocking error.
const WARNING_CASES = [
  {
    label: 'units mismatch: flow unit is not a rate against stock unit',
    env: envelope({
      stocks: [{ id: 'tank', label: 'Tank', unit: 'liters' }],
      flows: [{ id: 'inflow', label: 'Inflow',
               from: 'src', to: 'tank', unit: 'gallons/minute' }],
      clouds: [{ id: 'src' }],
    }),
    expectWarn: 'W_UNITS_MISMATCH',
  },
];

// ── Structural assertion helpers ─────────────────────────────────────────
const hasSvgRoot = (s) => typeof s === 'string' && /<svg\b/i.test(s);
const hasRootClass = (s) =>
  /class="[^"]*\bora-visual\b[^"]*"/.test(s) &&
  /class="[^"]*\bora-visual--stock_and_flow\b[^"]*"/.test(s);
const hasRoleImg    = (s) => /role="img"/.test(s);
const hasAriaLabel  = (s) => /aria-label="[^"]+"/.test(s);
const hasAccessibleTitle = (s) =>
  /<title class="ora-visual__accessible-title">[^<]+<\/title>/.test(s);
const hasInlineFillOrStroke = (s) =>
  /\bfill="#/.test(s) ||
  /\bstroke="#/.test(s) ||
  /\sstyle="/.test(s);
const hasId = (s, id) =>
  new RegExp('id="' + id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '"').test(s);
const countOf = (s, regex) => { const m = s.match(regex); return m ? m.length : 0; };

// ── Suite ────────────────────────────────────────────────────────────────
module.exports = {
  label: 'Stock-and-Flow — WP-1.3b renderer suite',
  run: async function run(ctx, record) {
    const { win } = ctx;
    const OVC = win.OraVisualCompiler;

    // Sanity: renderer module must be registered.
    const registered =
      OVC &&
      OVC._renderers &&
      typeof OVC._renderers.stockAndFlow === 'object' &&
      typeof OVC._renderers.stockAndFlow.render === 'function';
    record('renderer module registered', registered,
      registered ? '' : 'OraVisualCompiler._renderers.stockAndFlow absent');
    if (!registered) return;

    // Dispatcher integration: type is off the stub.
    const offStub = OVC._dispatcher.isStub('stock_and_flow') === false;
    record('dispatcher: stock_and_flow off stub', offStub,
      offStub ? '' : 'still wired to stub');

    const render = OVC._renderers.stockAndFlow.render;

    // ── Valid cases ────────────────────────────────────────────────────
    for (const tc of VALID_CASES) {
      const label = 'valid: ' + tc.label;
      try {
        const r = await render(tc.env);
        if (!r) { record(label, false, 'no result object'); continue; }
        if (r.errors && r.errors.length) {
          record(label, false,
            'unexpected errors: ' +
            JSON.stringify(r.errors.map((e) => e.code)));
          continue;
        }
        if (!hasSvgRoot(r.svg))        { record(label, false, 'no <svg> root'); continue; }
        if (!hasRootClass(r.svg))      { record(label, false, 'missing root classes'); continue; }
        if (!hasRoleImg(r.svg))        { record(label, false, 'missing role="img"'); continue; }
        if (!hasAriaLabel(r.svg))      { record(label, false, 'missing aria-label'); continue; }
        if (!hasAccessibleTitle(r.svg)){ record(label, false, 'missing accessible <title>'); continue; }
        if (hasInlineFillOrStroke(r.svg)) {
          record(label, false, 'inline fill/stroke/style not stripped');
          continue;
        }
        let missing = [];
        for (const id of tc.expectIds) {
          if (!hasId(r.svg, id)) missing.push(id);
        }
        if (missing.length) {
          record(label, false, 'missing semantic IDs: ' + missing.join(', '));
          continue;
        }
        record(label, true,
          'svg ' + r.svg.length + ' chars; warnings=' + (r.warnings || []).length);
      } catch (err) {
        record(label, false, 'threw: ' + (err.stack || err.message || err));
      }
    }

    // ── Invalid cases: error codes are blocking ─────────────────────────
    for (const tc of INVALID_CASES) {
      const label = 'invalid: ' + tc.label;
      try {
        const r = await render(tc.env);
        if (!r) { record(label, false, 'no result object'); continue; }
        if (!r.errors || r.errors.length === 0) {
          record(label, false,
            'expected ' + tc.expectCode + ' but got none; svg len=' +
            (r.svg || '').length);
          continue;
        }
        const codes = r.errors.map((e) => e.code);
        if (!codes.includes(tc.expectCode)) {
          record(label, false,
            'expected ' + tc.expectCode + ' but got ' + JSON.stringify(codes));
          continue;
        }
        if (r.svg && r.svg.length > 0) {
          record(label, false, 'expected empty svg on error, got len=' + r.svg.length);
          continue;
        }
        record(label, true, 'blocked with ' + tc.expectCode);
      } catch (err) {
        record(label, false, 'threw: ' + (err.stack || err.message || err));
      }
    }

    // ── Warning-only cases: render succeeds but warning is surfaced ─────
    for (const tc of WARNING_CASES) {
      const label = 'warning: ' + tc.label;
      try {
        const r = await render(tc.env);
        if (!r) { record(label, false, 'no result object'); continue; }
        if (r.errors && r.errors.length) {
          record(label, false,
            'expected success-with-warning; got errors: ' +
            JSON.stringify(r.errors.map((e) => e.code)));
          continue;
        }
        if (!hasSvgRoot(r.svg)) { record(label, false, 'no SVG emitted'); continue; }
        const warns = (r.warnings || []).map((w) => w.code);
        if (!warns.includes(tc.expectWarn)) {
          record(label, false, 'expected ' + tc.expectWarn +
            ' but got ' + JSON.stringify(warns));
          continue;
        }
        record(label, true, 'emitted ' + tc.expectWarn);
      } catch (err) {
        record(label, false, 'threw: ' + (err.stack || err.message || err));
      }
    }

    // ── Structural checks on a canonical envelope (from examples/) ──────
    try {
      const examplePath = path.join(ctx.EXAMPLES_DIR, 'stock_and_flow.valid.json');
      const ex = JSON.parse(fs.readFileSync(examplePath, 'utf-8'));
      const r = await render(ex);
      const ok = r && r.svg && r.errors && r.errors.length === 0;
      record('example: stock_and_flow.valid.json renders', !!ok,
        ok ? '' : 'errors=' + JSON.stringify((r && r.errors) || []));

      if (ok) {
        // Every declared stock has an attached flow (no W_STOCK_ISOLATED).
        const isolatedWarns =
          (r.warnings || []).filter((w) => w.code === 'W_STOCK_ISOLATED');
        record('example: no W_STOCK_ISOLATED',
          isolatedWarns.length === 0,
          'got ' + isolatedWarns.length);

        // Every cloud rendered — at least one saf-cloud-* id in the SVG.
        const cloudCount = countOf(r.svg, /id="saf-cloud-[^"]+"/g);
        record('example: at least one cloud rendered',
          cloudCount >= 1, 'got ' + cloudCount);

        // Every stock rendered.
        const stockCount = countOf(r.svg, /id="saf-stock-[^"]+"/g);
        record('example: every stock rendered',
          stockCount === ex.spec.stocks.length,
          'expected ' + ex.spec.stocks.length + ' got ' + stockCount);

        // Every flow rendered.
        const flowCount = countOf(r.svg, /id="saf-flow-[^"]+"/g);
        record('example: every flow rendered',
          flowCount === ex.spec.flows.length,
          'expected ' + ex.spec.flows.length + ' got ' + flowCount);
      }
    } catch (err) {
      record('example: stock_and_flow.valid.json renders', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── Isolated-stock warning check ────────────────────────────────────
    try {
      const isoEnv = envelope({
        stocks: [
          { id: 'hasflow', label: 'Connected' },
          { id: 'floating', label: 'Isolated' },
        ],
        flows: [{ id: 'f1', label: 'F1', from: 'cloud', to: 'hasflow' }],
      });
      const r = await render(isoEnv);
      const warnCodes = (r.warnings || []).map((w) => w.code);
      const ok = (r.errors || []).length === 0 &&
        warnCodes.includes('W_STOCK_ISOLATED');
      record('isolated stock emits W_STOCK_ISOLATED', ok,
        ok ? '' : ('errors=' + JSON.stringify(r.errors || []) +
                   ' warnings=' + JSON.stringify(warnCodes)));
    } catch (err) {
      record('isolated stock emits W_STOCK_ISOLATED', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── Dense-layout regression: many auxiliaries must not overlap ──────
    // Renders the dense single-stock / many-auxiliary spec and asserts (a)
    // a non-empty SVG and (b) that the artifact-adversarial overlap check
    // does NOT fire E_ARTIFACT_OVERLAP. The collision-free aux grid is what
    // keeps this case from being suppressed to 0 bytes.
    try {
      const r = await render(envelope(DENSE_SPEC));
      const nonEmpty = !!(r && r.svg && r.svg.length > 0) &&
        (!r.errors || r.errors.length === 0);
      record('dense: many-aux spec renders non-empty SVG', nonEmpty,
        nonEmpty ? 'svg ' + r.svg.length + ' chars'
                 : 'errors=' + JSON.stringify((r && r.errors) || []));

      // Every auxiliary must be present in the output.
      if (nonEmpty) {
        const missingAux = DENSE_SPEC.auxiliaries
          .map((a) => 'saf-aux-' + a.id)
          .filter((id) => !hasId(r.svg, id));
        record('dense: every auxiliary rendered', missingAux.length === 0,
          missingAux.length ? 'missing: ' + missingAux.join(', ') : '');
      }

      // Run the real artifact-adversarial review (loaded into the harness
      // window) over the rendered SVG and assert no Critical overlap.
      const AA = OVC.artifactAdversarial;
      if (nonEmpty && AA && typeof AA.review === 'function') {
        const rev = AA.review(r.svg, envelope(DENSE_SPEC));
        const overlaps = (rev.findings || [])
          .filter((f) => f.code === 'E_ARTIFACT_OVERLAP');
        const worst = (rev.findings || [])
          .filter((f) => /OVERLAP/.test(f.code))
          .reduce((m, f) => {
            const pct = parseFloat((f.message.match(/([\d.]+)%/) || [])[1]) || 0;
            return Math.max(m, pct);
          }, 0);
        const clean = !rev.blocks && overlaps.length === 0;
        record('dense: no E_ARTIFACT_OVERLAP from adversarial review', clean,
          clean ? 'worst overlap ' + worst.toFixed(1) + '% of smaller area'
                : 'blocks=' + rev.blocks + ' overlaps=' +
                  JSON.stringify(overlaps.map((f) => f.message)));
      } else if (nonEmpty) {
        record('dense: no E_ARTIFACT_OVERLAP from adversarial review', false,
          'artifactAdversarial.review unavailable in harness window');
      }
    } catch (err) {
      record('dense: many-aux spec renders non-empty SVG', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // Optionally exercise the on-disk "premium" snapshot if present — this
    // is the exact envelope the campaign ships; the inline DENSE_SPEC above
    // is a self-contained stand-in when the snapshot dir is absent.
    try {
      const snapPath = '/tmp/render-fix-cases/stock-and-flow__premium.json';
      if (fs.existsSync(snapPath)) {
        const snap = JSON.parse(fs.readFileSync(snapPath, 'utf-8'));
        const r = await render(snap);
        const nonEmpty = !!(r && r.svg && r.svg.length > 0) &&
          (!r.errors || r.errors.length === 0);
        const AA = OVC.artifactAdversarial;
        let clean = nonEmpty;
        if (nonEmpty && AA && typeof AA.review === 'function') {
          const rev = AA.review(r.svg, snap);
          clean = !rev.blocks &&
            (rev.findings || []).every((f) => f.code !== 'E_ARTIFACT_OVERLAP');
        }
        record('dense: premium snapshot renders without overlap', nonEmpty && clean,
          (nonEmpty && clean) ? 'svg ' + r.svg.length + ' chars'
                              : 'nonEmpty=' + nonEmpty + ' clean=' + clean);
      }
    } catch (err) {
      record('dense: premium snapshot renders without overlap', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── Internals: cycle detector and resolver unit tests ──────────────
    const internals = OVC._renderers.stockAndFlow;
    try {
      const cyclic = internals._detectInfoCycle([
        { from: 'a', to: 'b' },
        { from: 'b', to: 'c' },
        { from: 'c', to: 'a' },
      ]);
      record('unit(cycle): detects triangle',
        Array.isArray(cyclic) && cyclic.length >= 3,
        'got ' + JSON.stringify(cyclic));
    } catch (err) {
      record('unit(cycle): detects triangle', false,
        'threw: ' + (err.stack || err.message || err));
    }
    try {
      const acyc = internals._detectInfoCycle([
        { from: 'a', to: 'b' },
        { from: 'b', to: 'c' },
      ]);
      record('unit(cycle): acyclic returns null',
        acyc === null, 'got ' + JSON.stringify(acyc));
    } catch (err) {
      record('unit(cycle): acyclic returns null', false,
        'threw: ' + (err.stack || err.message || err));
    }
    try {
      const resolved = internals._resolveSpec({
        stocks: [{ id: 's', label: 'S' }],
        flows: [{ id: 'f', label: 'F', from: 'cloud', to: 's' }],
      });
      // "cloud" keyword should synthesize a cloud.
      const synth = [...resolved.clouds.values()].filter((c) => c.synthesized);
      record('unit(resolve): "cloud" keyword synthesizes a cloud',
        synth.length === 1, 'got ' + synth.length);
      record('unit(resolve): no unresolved refs',
        resolved.errors.length === 0,
        'got ' + JSON.stringify(resolved.errors.map((e) => e.code)));
    } catch (err) {
      record('unit(resolve): "cloud" keyword synthesizes a cloud', false,
        'threw: ' + (err.stack || err.message || err));
    }
  },
};
