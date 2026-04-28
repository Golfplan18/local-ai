/**
 * tests/cases/test-quadrant-matrix.js — WP-1.3g regression suite.
 *
 * Exercises the quadrant_matrix renderer across:
 *
 *   Valid (≥ 5):
 *     1. strategic_2x2 impact-effort (classic 2×2, 4 items across all quadrants)
 *     2. scenario_planning with 4 non-empty narratives
 *     3. simple 3-item strategic_2x2 (no-narrative subtype)
 *     4. item placed on the exact axis (x=0.5, y=0.5)
 *     5. edge items at (0,0) and (1,1) — corner extremes
 *
 *   Invalid (≥ 3):
 *     1. scenario_planning missing a quadrant narrative → E_SCHEMA_INVALID
 *     2. item with x > 1 → E_SCHEMA_INVALID
 *     3. highly correlated items (Pearson |r|>0.7) → W_AXES_DEPENDENT
 *        warning assertion (still renders; not a blocker)
 *
 *   Unit checks on the exported internals:
 *     - pearson returns null when n<3 / zero variance
 *     - pearson computes to textbook values on a known pair
 *
 *   SVG structural assertions:
 *     - Four quadrant groups with id="q-quadrant-{TL,TR,BL,BR}"
 *     - Two axis lines with arrowhead markers
 *     - Correct item count (one <g class="ora-visual__item"> per item)
 *     - Root carries class="ora-visual ora-visual--quadrant_matrix …"
 *     - Root has role="img" + aria-label
 */

'use strict';

const fs   = require('fs');
const path = require('path');

// ── Envelope builder ──────────────────────────────────────────────────────
function envelope(spec, overrides) {
  const base = {
    schema_version: '0.2',
    id: 'fig-test-quadrant-matrix',
    type: 'quadrant_matrix',
    mode_context: 'root_cause_analysis',
    relation_to_prose: 'integrated',
    spec: spec,
    semantic_description: {
      level_1_elemental:  'Test quadrant_matrix fixture.',
      level_2_statistical: 'Synthetic items.',
      level_3_perceptual:  'Four quadrants.',
      level_4_contextual:  null,
      short_alt: 'Test 2×2 matrix.',
      data_table_fallback: null,
    },
    title: 'Test quadrant matrix',
  };
  return Object.assign(base, overrides || {});
}

function baseQuadrants(withNarrative) {
  const n = (s) => withNarrative ? s : '';
  return {
    TL: { name: 'Top Left',     narrative: n('Low x, high y — slow burn.') },
    TR: { name: 'Top Right',    narrative: n('High x, high y — flagship bets.') },
    BL: { name: 'Bottom Left',  narrative: n('Low x, low y — graveyard.') },
    BR: { name: 'Bottom Right', narrative: n('High x, low y — quick wins.') },
  };
}

const RATIONALE = 'x and y are drawn from independent domains: effort reflects engineering cost, impact reflects ' +
                  'customer outcome; no mechanical coupling in the process by which each is estimated.';

// ── Valid fixtures ────────────────────────────────────────────────────────
function validFixtures() {
  return [
    {
      label: 'strategic_2x2 impact-effort (one item per quadrant)',
      env: envelope({
        subtype: 'strategic_2x2',
        x_axis: { label: 'Effort',  low_label: 'Low', high_label: 'High' },
        y_axis: { label: 'Impact',  low_label: 'Low', high_label: 'High' },
        quadrants: baseQuadrants(false),
        items: [
          { label: 'A', x: 0.2, y: 0.8 },  // TL (low effort, high impact — quick win)
          { label: 'B', x: 0.8, y: 0.8 },  // TR (high effort, high impact — flagship)
          { label: 'C', x: 0.2, y: 0.2 },  // BL (low effort, low impact — fill-in)
          { label: 'D', x: 0.8, y: 0.2 },  // BR (high effort, low impact — avoid)
        ],
        axes_independence_rationale: RATIONALE,
      }),
      expectItemCount: 4,
      expectClasses: ['ora-visual--quadrant_matrix--strategic_2x2'],
    },
    {
      label: 'scenario_planning with 4 non-empty narratives',
      env: envelope({
        subtype: 'scenario_planning',
        x_axis: { label: 'AI capability growth', low_label: 'Stalls', high_label: 'Accelerates' },
        y_axis: { label: 'Regulatory posture',   low_label: 'Laissez-faire', high_label: 'Strict' },
        quadrants: {
          TL: { name: 'Soft landing',    narrative: 'Slow cap growth with strict regulation.' },
          TR: { name: 'Constrained boom', narrative: 'Fast cap growth with strict regulation.' },
          BL: { name: 'Stall',           narrative: 'Slow cap growth with open rules.' },
          BR: { name: 'Wild west',       narrative: 'Fast cap growth with open rules.' },
        },
        items: [
          { label: 'EU trajectory', x: 0.3, y: 0.8 },
        ],
        axes_independence_rationale: RATIONALE,
      }),
      expectItemCount: 1,
      expectClasses: ['ora-visual--quadrant_matrix--scenario_planning'],
      expectNarrativeLines: true,
    },
    {
      label: 'simple 3-item strategic_2x2',
      env: envelope({
        subtype: 'strategic_2x2',
        x_axis: { label: 'Cost',  low_label: 'Low', high_label: 'High' },
        y_axis: { label: 'Value', low_label: 'Low', high_label: 'High' },
        quadrants: baseQuadrants(false),
        items: [
          { label: 'Alpha', x: 0.25, y: 0.75 },
          { label: 'Beta',  x: 0.60, y: 0.20 },
          { label: 'Gamma', x: 0.40, y: 0.55 },
        ],
        axes_independence_rationale: RATIONALE,
      }),
      expectItemCount: 3,
    },
    {
      label: 'item on exact axis (x=0.5, y=0.5)',
      env: envelope({
        subtype: 'strategic_2x2',
        x_axis: { label: 'X',  low_label: 'lo', high_label: 'hi' },
        y_axis: { label: 'Y',  low_label: 'lo', high_label: 'hi' },
        quadrants: baseQuadrants(false),
        items: [
          { label: 'Centered', x: 0.5, y: 0.5 },
        ],
        axes_independence_rationale: RATIONALE,
      }),
      expectItemCount: 1,
    },
    {
      label: 'edge items at (0,0) and (1,1)',
      env: envelope({
        subtype: 'strategic_2x2',
        x_axis: { label: 'X',  low_label: 'lo', high_label: 'hi' },
        y_axis: { label: 'Y',  low_label: 'lo', high_label: 'hi' },
        quadrants: baseQuadrants(false),
        items: [
          { label: 'Origin', x: 0.0, y: 0.0 },
          { label: 'Apex',   x: 1.0, y: 1.0 },
        ],
        axes_independence_rationale: RATIONALE,
      }),
      expectItemCount: 2,
    },
  ];
}

// ── Invalid / warning fixtures ────────────────────────────────────────────
function invalidFixtures() {
  return [
    {
      label: 'scenario_planning missing a quadrant narrative',
      env: envelope({
        subtype: 'scenario_planning',
        x_axis: { label: 'X',  low_label: 'lo', high_label: 'hi' },
        y_axis: { label: 'Y',  low_label: 'lo', high_label: 'hi' },
        quadrants: {
          TL: { name: 'Q-TL',   narrative: 'has narrative' },
          TR: { name: 'Q-TR',   narrative: '' },            // offender
          BL: { name: 'Q-BL',   narrative: 'has narrative' },
          BR: { name: 'Q-BR',   narrative: 'has narrative' },
        },
        items: [{ label: 'x', x: 0.5, y: 0.5 }],
        axes_independence_rationale: RATIONALE,
      }),
      expectCode: 'E_SCHEMA_INVALID',
      expectMessageContains: 'TR',
    },
    {
      label: 'item with x > 1 (defensive check; schema layer would also catch)',
      env: envelope({
        subtype: 'strategic_2x2',
        x_axis: { label: 'X',  low_label: 'lo', high_label: 'hi' },
        y_axis: { label: 'Y',  low_label: 'lo', high_label: 'hi' },
        quadrants: baseQuadrants(false),
        items: [
          { label: 'OOB', x: 1.4, y: 0.5 },   // out of bounds
        ],
        axes_independence_rationale: RATIONALE,
      }),
      expectCode: 'E_SCHEMA_INVALID',
    },
  ];
}

// A fixture where the renderer should SUCCEED but emit W_AXES_DEPENDENT. A
// perfectly-correlated diagonal cluster is the cleanest forcing function
// for |r| ≈ 1.
function axesDependentFixture() {
  return envelope({
    subtype: 'strategic_2x2',
    x_axis: { label: 'X',  low_label: 'lo', high_label: 'hi' },
    y_axis: { label: 'Y',  low_label: 'lo', high_label: 'hi' },
    quadrants: baseQuadrants(false),
    items: [
      { label: 'p1', x: 0.10, y: 0.12 },
      { label: 'p2', x: 0.30, y: 0.31 },
      { label: 'p3', x: 0.55, y: 0.56 },
      { label: 'p4', x: 0.75, y: 0.74 },
      { label: 'p5', x: 0.90, y: 0.91 },
    ],
    axes_independence_rationale: RATIONALE,
  });
}

// ── SVG structural assertions ─────────────────────────────────────────────
function structuralChecks(svg, expectItemCount, expectClasses) {
  if (!svg || svg.length === 0) return 'empty svg';

  // Root class check
  const rootMatch = svg.match(/<svg\b[^>]*>/);
  if (!rootMatch) return 'no <svg> root tag';
  const rootTag = rootMatch[0];

  const classMatch = rootTag.match(/\sclass="([^"]*)"/);
  if (!classMatch) return 'no class attribute on root';
  const classes = classMatch[1].split(/\s+/);
  if (classes.indexOf('ora-visual') === -1)
    return 'missing ora-visual class on root';
  if (classes.indexOf('ora-visual--quadrant_matrix') === -1)
    return 'missing ora-visual--quadrant_matrix class on root';

  for (const c of (expectClasses || [])) {
    if (classes.indexOf(c) === -1) return 'missing expected root class: ' + c;
  }

  if (!/\srole="img"/.test(rootTag))
    return 'missing role="img" on root';
  if (!/\saria-label="[^"]+"/.test(rootTag))
    return 'missing aria-label on root';

  // Banned inline-style attrs on root
  for (const b of ['style=', 'fill=', 'stroke=', 'font-family=', 'font-size=']) {
    if (rootTag.indexOf(' ' + b) !== -1)
      return 'root <svg> carries banned inline attribute: ' + b;
  }

  // Four quadrant groups with stable IDs
  for (const k of ['TL', 'TR', 'BL', 'BR']) {
    if (!new RegExp('id="q-quadrant-' + k + '"').test(svg))
      return 'missing quadrant group id="q-quadrant-' + k + '"';
  }

  // Two axis <line> elements and two arrowhead markers.
  const axisLineCount = (svg.match(/class="[^"]*\bora-visual__axis\b/g) || []).length;
  if (axisLineCount < 2)
    return 'expected ≥ 2 axis lines, got ' + axisLineCount;
  if (!/<marker\b[^>]*id="q-arrow-x"/.test(svg))
    return 'missing x-axis arrowhead marker <marker id="q-arrow-x">';
  if (!/<marker\b[^>]*id="q-arrow-y"/.test(svg))
    return 'missing y-axis arrowhead marker <marker id="q-arrow-y">';
  if (!/marker-end="url\(#q-arrow-x\)"/.test(svg))
    return 'x-axis line missing marker-end reference';
  if (!/marker-end="url\(#q-arrow-y\)"/.test(svg))
    return 'y-axis line missing marker-end reference';

  // Item count — every item emits <g class="ora-visual__item">.
  const itemGroupCount =
    (svg.match(/class="ora-visual__item"/g) || []).length;
  if (expectItemCount !== undefined && itemGroupCount !== expectItemCount) {
    return 'item group count mismatch: expected ' + expectItemCount + ', got ' + itemGroupCount;
  }

  // Every item group must carry an id starting with "q-item-".
  const itemIdCount = (svg.match(/id="q-item-[^"]+"/g) || []).length;
  if (expectItemCount !== undefined && itemIdCount !== expectItemCount) {
    return 'item id count mismatch: expected ' + expectItemCount + ', got ' + itemIdCount;
  }

  return null;
}

// ── Runner ────────────────────────────────────────────────────────────────
module.exports = {
  label: 'quadrant_matrix renderer — ≥5 valid + ≥3 invalid + W_AXES_DEPENDENT + unit checks',
  run: async function run(ctx, record) {
    const { win } = ctx;
    const OVC = win.OraVisualCompiler;
    const rendererModule = OVC._renderers && OVC._renderers.quadrantMatrix;

    // Guard: did the renderer get loaded?
    if (!rendererModule) {
      record('quadrant_matrix renderer loaded', false,
        'OraVisualCompiler._renderers.quadrantMatrix is absent — renderer not loaded');
      return;
    }
    record('quadrant_matrix renderer loaded', true);

    // Dispatcher integration: not on stub.
    record(
      'dispatcher: quadrant_matrix no longer on stub',
      OVC._dispatcher.isStub('quadrant_matrix') === false,
      'still wired to stub'
    );

    // ── Unit checks on exported internals ────────────────────────────
    const p = rendererModule._pearson;
    record('unit(pearson): null on n<3',
      p([1, 2], [3, 4]) === null, 'expected null');
    record('unit(pearson): null on zero variance',
      p([1, 1, 1], [2, 3, 4]) === null, 'expected null');

    // Known textbook case: perfect positive correlation.
    const rpos = p([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]);
    record('unit(pearson): perfect positive = 1',
      Math.abs((rpos || 0) - 1) < 1e-9, 'got ' + rpos);

    // Known textbook case: perfect negative correlation.
    const rneg = p([1, 2, 3, 4, 5], [10, 8, 6, 4, 2]);
    record('unit(pearson): perfect negative = -1',
      Math.abs((rneg || 0) + 1) < 1e-9, 'got ' + rneg);

    // Slug helper exists and is deterministic.
    const slug = rendererModule._slug;
    record('unit(slug): ASCII round-trip', slug('Foo Bar 1') === 'foo-bar-1', 'got ' + slug('Foo Bar 1'));
    record('unit(slug): fallback on empty', slug('') === 'item', 'got ' + slug(''));

    // ── Valid fixtures ───────────────────────────────────────────────
    for (const tc of validFixtures()) {
      const name = 'valid: ' + tc.label;
      try {
        let result = rendererModule.render(tc.env);
        if (result && typeof result.then === 'function') result = await result;

        const errs = (result.errors || []).filter((e) => e.code && e.code.startsWith('E_'));
        if (errs.length) {
          record(name, false, 'unexpected errors: ' +
            errs.map((e) => e.code + ':' + e.message).join('; '));
          continue;
        }

        const fail = structuralChecks(result.svg, tc.expectItemCount, tc.expectClasses);
        if (fail) { record(name, false, fail); continue; }

        if (tc.expectNarrativeLines) {
          if (!/ora-visual__quadrant-narrative/.test(result.svg)) {
            record(name, false, 'expected __quadrant-narrative elements for scenario_planning');
            continue;
          }
        }

        record(name, true, 'svg ' + result.svg.length + ' chars');
      } catch (err) {
        record(name, false, 'threw: ' + (err.stack || err.message || err));
      }
    }

    // ── Invalid fixtures ─────────────────────────────────────────────
    for (const tc of invalidFixtures()) {
      const name = 'invalid: ' + tc.label;
      try {
        let result = rendererModule.render(tc.env);
        if (result && typeof result.then === 'function') result = await result;

        const codes = (result.errors || []).map((e) => e.code);
        if (!codes.includes(tc.expectCode)) {
          record(name, false,
            'expected ' + tc.expectCode + '; got codes=' + JSON.stringify(codes));
          continue;
        }
        if (result.svg !== '') {
          record(name, false, 'expected empty svg on error; got length=' + result.svg.length);
          continue;
        }
        if (tc.expectMessageContains) {
          const hit = (result.errors || []).some((e) =>
            e.message && e.message.indexOf(tc.expectMessageContains) >= 0);
          if (!hit) {
            record(name, false, "expected error message to contain '" +
              tc.expectMessageContains + "'; got: " +
              result.errors.map((e) => e.message).join(' | '));
            continue;
          }
        }
        record(name, true, 'rejected with ' + codes.join(','));
      } catch (err) {
        record(name, false, 'threw: ' + (err.stack || err.message || err));
      }
    }

    // ── W_AXES_DEPENDENT warning fixture (non-blocking) ──────────────
    {
      const name = 'warning: highly correlated items emit W_AXES_DEPENDENT';
      try {
        let result = rendererModule.render(axesDependentFixture());
        if (result && typeof result.then === 'function') result = await result;

        const errs = (result.errors || []).filter((e) => e.code && e.code.startsWith('E_'));
        if (errs.length) {
          record(name, false, 'unexpected hard errors: ' +
            errs.map((e) => e.code).join(','));
        } else if (!(result.svg && result.svg.length > 0)) {
          record(name, false, 'expected successful render with non-empty svg');
        } else {
          const warnCodes = (result.warnings || []).map((w) => w.code);
          if (!warnCodes.includes('W_AXES_DEPENDENT')) {
            record(name, false,
              'expected W_AXES_DEPENDENT in warnings; got ' + JSON.stringify(warnCodes));
          } else {
            record(name, true, 'warned with ' + warnCodes.join(','));
          }
        }
      } catch (err) {
        record(name, false, 'threw: ' + (err.stack || err.message || err));
      }
    }

    // ── compile() round-trip for a valid fixture (exercises async-shim) ──
    {
      const name = 'compile(): round-trip a valid scenario_planning envelope';
      try {
        const env = validFixtures()[1].env;     // scenario_planning
        let result = win.OraVisualCompiler.compile(env);
        if (result && typeof result.then === 'function') result = await result;
        const errs = (result.errors || []).filter((e) => e.code && e.code.startsWith('E_'));
        if (errs.length) {
          record(name, false, 'errors: ' + errs.map((e) => e.code + ':' + e.message).join('; '));
        } else if (!result.svg || result.svg.length === 0) {
          record(name, false, 'empty svg from compile()');
        } else {
          record(name, true, 'svg ' + result.svg.length + ' chars');
        }
      } catch (err) {
        record(name, false, 'threw: ' + (err.stack || err.message || err));
      }
    }
  },
};
