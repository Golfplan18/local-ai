/**
 * tests/cases/test-vega-lite.js
 *
 * Hand-written fixtures exercising the Vega-Lite renderer across all six
 * QUANT types. For each type, at least three distinct envelopes cover
 * variations in mark / encoding / facet / layer. One deliberate parse
 * failure case at the end asserts E_DSL_PARSE.
 *
 * Assertions per case:
 *   - SVG non-empty
 *   - SVG root <svg> carries class "ora-visual ora-visual--<type>"
 *   - SVG root has role="img"
 *   - SVG has no inline style / fill / stroke / font-* attrs on <svg>
 */

'use strict';

const fs   = require('fs');
const path = require('path');

function envelope(type, spec, overrides) {
  return Object.assign({
    schema_version: '0.2',
    id: 'fig-' + type + '-test',
    type: type,
    mode_context: 'test_harness',
    relation_to_prose: 'integrated',
    spec: spec,
    semantic_description: {
      level_1_elemental:  'Test-harness ' + type + ' fixture.',
      level_2_statistical: 'Synthetic values.',
      level_3_perceptual:  'Single pattern.',
      level_4_contextual:  null,
      short_alt: 'Test ' + type + ' chart.',
      data_table_fallback: null,
    },
    title: 'Test ' + type,
  }, overrides || {});
}

const CAPTION = { source: 'test', period: '2026-Q1', n: 3, units: 'units' };
const VL_SCHEMA = 'https://vega.github.io/schema/vega-lite/v5.json';

// ── Fixtures ─────────────────────────────────────────────────────────────────
function comparisonFixtures() {
  return [
    envelope('comparison', {
      $schema: VL_SCHEMA,
      data: { values: [{c:'A', v:10},{c:'B', v:22},{c:'C', v:7}] },
      mark: 'bar',
      encoding: { x:{field:'c', type:'nominal'}, y:{field:'v', type:'quantitative'} },
      caption: CAPTION,
    }),
    envelope('comparison', {
      $schema: VL_SCHEMA,
      data: { values: [{c:'X', v:3},{c:'Y', v:9}] },
      mark: 'point',
      encoding: { x:{field:'c', type:'nominal'}, y:{field:'v', type:'quantitative'} },
      caption: CAPTION,
    }),
    envelope('comparison', {
      $schema: VL_SCHEMA,
      data: { values: [{g:'r', v:5},{g:'b', v:8},{g:'g', v:12}] },
      mark: { type: 'bar' },
      encoding: {
        x: { field:'g', type:'nominal' },
        y: { field:'v', type:'quantitative' },
        color: { field:'g', type:'nominal' },
      },
      caption: CAPTION,
    }),
  ];
}

function timeSeriesFixtures() {
  return [
    envelope('time_series', {
      $schema: VL_SCHEMA,
      data: { values: [{t:'2026-01-01', v:1},{t:'2026-02-01', v:3},{t:'2026-03-01', v:2}] },
      mark: 'line',
      encoding: { x:{field:'t', type:'temporal'}, y:{field:'v', type:'quantitative'} },
      caption: CAPTION,
    }),
    envelope('time_series', {
      $schema: VL_SCHEMA,
      data: { values: [{t:'2026-01-01', v:0},{t:'2026-02-01', v:1},{t:'2026-03-01', v:4}] },
      mark: 'area',
      encoding: { x:{field:'t', type:'temporal'}, y:{field:'v', type:'quantitative'} },
      caption: CAPTION,
    }),
    envelope('time_series', {
      $schema: VL_SCHEMA,
      data: { values: [
        {t:'2026-01-01', v:1, lo:0.5, hi:1.5},
        {t:'2026-02-01', v:2, lo:1.4, hi:2.6},
        {t:'2026-03-01', v:3, lo:2.2, hi:3.8},
      ] },
      mark: 'line',
      encoding: { x:{field:'t', type:'temporal'}, y:{field:'v', type:'quantitative'} },
      layer: [
        { mark: 'errorband', encoding: {
          x:{field:'t', type:'temporal'},
          y:{field:'lo', type:'quantitative'},
          y2:{field:'hi'},
        }},
        { mark: 'line', encoding: {
          x:{field:'t', type:'temporal'},
          y:{field:'v', type:'quantitative'},
        }},
      ],
      caption: CAPTION,
    }),
  ];
}

function distributionFixtures() {
  return [
    envelope('distribution', {
      $schema: VL_SCHEMA,
      data: { values: [{v:1},{v:2},{v:3},{v:4},{v:5}] },
      mark: 'boxplot',
      encoding: { y:{field:'v', type:'quantitative'} },
      caption: CAPTION,
    }),
    envelope('distribution', {
      $schema: VL_SCHEMA,
      data: { values: [{v:1},{v:1.5},{v:2},{v:2.5},{v:3}] },
      mark: 'tick',
      encoding: { x:{field:'v', type:'quantitative'} },
      caption: CAPTION,
    }),
    envelope('distribution', {
      $schema: VL_SCHEMA,
      data: { values: [{v:1},{v:2},{v:2},{v:3},{v:3},{v:3},{v:4},{v:5}] },
      mark: 'bar',
      encoding: {
        x: { bin: true, field:'v', type:'quantitative' },
        y: { aggregate:'count', type:'quantitative' },
      },
      caption: CAPTION,
    }),
  ];
}

function scatterFixtures() {
  return [
    envelope('scatter', {
      $schema: VL_SCHEMA,
      data: { values: [{x:1,y:2},{x:3,y:4},{x:5,y:1}] },
      mark: 'point',
      encoding: { x:{field:'x', type:'quantitative'}, y:{field:'y', type:'quantitative'} },
      caption: CAPTION,
    }),
    envelope('scatter', {
      $schema: VL_SCHEMA,
      data: { values: [{x:1,y:2,g:'a'},{x:3,y:4,g:'b'},{x:5,y:1,g:'a'}] },
      mark: 'circle',
      encoding: {
        x:{field:'x', type:'quantitative'},
        y:{field:'y', type:'quantitative'},
        color: {field:'g', type:'nominal'},
      },
      caption: CAPTION,
    }),
    envelope('scatter', {
      $schema: VL_SCHEMA,
      data: { values: [{x:10,y:20,sz:50},{x:20,y:35,sz:120},{x:30,y:25,sz:80}] },
      mark: 'point',
      encoding: {
        x:{field:'x', type:'quantitative'},
        y:{field:'y', type:'quantitative'},
        size:{field:'sz', type:'quantitative'},
      },
      caption: CAPTION,
    }),
  ];
}

function heatmapFixtures() {
  return [
    envelope('heatmap', {
      $schema: VL_SCHEMA,
      data: { values: [
        {r:'a', c:'x', v:1},{r:'a', c:'y', v:2},
        {r:'b', c:'x', v:3},{r:'b', c:'y', v:4},
      ] },
      mark: 'rect',
      encoding: {
        x:{field:'c', type:'nominal'},
        y:{field:'r', type:'nominal'},
        color:{field:'v', type:'quantitative'},
      },
      caption: CAPTION,
    }),
    envelope('heatmap', {
      $schema: VL_SCHEMA,
      data: { values: [
        {r:'a', c:'x', v:1},{r:'a', c:'y', v:5},
        {r:'b', c:'x', v:3},{r:'b', c:'y', v:9},
      ] },
      mark: { type: 'rect' },
      encoding: {
        x:{field:'c', type:'nominal'},
        y:{field:'r', type:'nominal'},
        color:{field:'v', type:'quantitative', scale:{scheme:'viridis'}},
      },
      caption: CAPTION,
    }),
    envelope('heatmap', {
      $schema: VL_SCHEMA,
      data: { values: [
        {r:1, c:1, v:1},{r:1, c:2, v:2},{r:1, c:3, v:1},
        {r:2, c:1, v:3},{r:2, c:2, v:4},{r:2, c:3, v:2},
        {r:3, c:1, v:5},{r:3, c:2, v:6},{r:3, c:3, v:4},
      ] },
      mark: 'square',
      encoding: {
        x:{field:'c', type:'ordinal'},
        y:{field:'r', type:'ordinal'},
        color:{field:'v', type:'quantitative'},
      },
      caption: CAPTION,
    }),
  ];
}

function tornadoFixtures() {
  return [
    envelope('tornado', {
      base_case_label:  'NPV base',
      base_case_value:  100,
      outcome_variable: 'NPV',
      outcome_units:    'USD M',
      parameters: [
        { label:'Price',  low_value:80, high_value:120, outcome_at_low:60, outcome_at_high:140 },
        { label:'COGS',   low_value:50, high_value:70,  outcome_at_low:110, outcome_at_high:85 },
      ],
      sort_by: 'swing',
    }),
    envelope('tornado', {
      base_case_label:  'Base revenue',
      base_case_value:  50,
      outcome_variable: 'Revenue',
      outcome_units:    'USD M',
      parameters: [
        { label:'Adoption', low_value:0.3, high_value:0.7, outcome_at_low:30, outcome_at_high:80 },
        { label:'ARPU',     low_value:10, high_value:20,   outcome_at_low:40, outcome_at_high:65 },
        { label:'Churn',    low_value:0.02, high_value:0.08, outcome_at_low:55, outcome_at_high:42 },
      ],
      sort_by: 'swing',
    }),
    envelope('tornado', {
      base_case_label:  'Baseline IRR',
      base_case_value:  0.12,
      outcome_variable: 'IRR',
      outcome_units:    'pct',
      parameters: [
        { label:'Capex',  low_value:100, high_value:140, outcome_at_low:0.16, outcome_at_high:0.08 },
        { label:'Demand', low_value:0.9, high_value:1.1, outcome_at_low:0.09, outcome_at_high:0.15 },
      ],
      sort_by: 'custom',
    }),
  ];
}

// A deliberately malformed Vega-Lite encoding: unknown channel type plus an
// unresolved field reference forces vega-lite.compile to throw.
function parseFailureFixture() {
  return envelope('scatter', {
    $schema: VL_SCHEMA,
    data: { values: [{x:1, y:2}] },
    // Missing required "type" inside mark object; Vega-Lite throws on compile.
    mark: { cornerRadius: 'not-a-mark' },
    encoding: {
      x: { field:'x', type:'quantitative', scale:{ type:'definitely-not-a-scale' } },
      y: { field:'nope', type:'quantitative' },
    },
    caption: CAPTION,
  });
}

// ── Assertions ───────────────────────────────────────────────────────────────
function assertStructuralSvg(svg, type) {
  if (!svg || svg.length === 0) return 'empty svg';
  // Root <svg> must carry our semantic classes.
  const classMatch = svg.match(/<svg\b[^>]*\sclass="([^"]*)"/);
  if (!classMatch) return 'no class attribute on root <svg>';
  const classes = classMatch[1].split(/\s+/);
  if (classes.indexOf('ora-visual') === -1) return 'missing "ora-visual" class';
  if (classes.indexOf('ora-visual--' + type) === -1) return 'missing "ora-visual--' + type + '" class';
  // Root must have role="img".
  if (!/<svg\b[^>]*\srole="img"/.test(svg)) return 'missing role="img" on root';
  // Root <svg> itself must not carry stripped attributes. Look at the first tag.
  const rootTag = svg.match(/<svg\b[^>]*>/)[0];
  const banned = ['style=', 'fill=', 'stroke=', 'font-family=', 'font-size='];
  for (const b of banned) {
    if (rootTag.indexOf(b) !== -1) return 'root <svg> still carries ' + b;
  }
  return null;  // ok
}

// ── Runner ───────────────────────────────────────────────────────────────────
module.exports = {
  label: 'Vega-Lite renderer — ≥3 fixtures per QUANT type + parse failure',
  run: async function run(ctx, record) {
    const { win } = ctx;

    const suites = [
      ['comparison',  comparisonFixtures()],
      ['time_series', timeSeriesFixtures()],
      ['distribution', distributionFixtures()],
      ['scatter',     scatterFixtures()],
      ['heatmap',     heatmapFixtures()],
      ['tornado',     tornadoFixtures()],
    ];

    for (const [type, fixtures] of suites) {
      if (fixtures.length < 3) {
        record('fixture count for ' + type, false,
          'only ' + fixtures.length + ' fixtures, need >= 3');
        continue;
      }
      for (let i = 0; i < fixtures.length; i++) {
        const name = 'vega-lite ' + type + ' #' + (i + 1);
        try {
          let result = win.OraVisualCompiler.compile(fixtures[i]);
          if (result && typeof result.then === 'function') result = await result;
          const errs = (result.errors || []).filter((e) => e.code && e.code.startsWith('E_'));
          if (errs.length) {
            record(name, false, 'unexpected errors: ' + errs.map((e) => e.code + ':' + e.message).join('; '));
            continue;
          }
          const fail = assertStructuralSvg(result.svg, type);
          if (fail) record(name, false, fail);
          else      record(name, true, 'svg ' + result.svg.length + ' chars');
        } catch (err) {
          record(name, false, 'threw: ' + (err.message || err));
        }
      }
    }

    // Malformed-input case: expect clean rejection (any E_* code + empty svg).
    // Ajv Layer 2 catches most malformed specs at validation (E_SCHEMA_INVALID)
    // before they reach the renderer; anything that slips through surfaces as
    // E_DSL_PARSE from the Vega-Lite compile path. Either is a valid outcome
    // for the behavioral contract "bad input → no degraded visual".
    try {
      let result = win.OraVisualCompiler.compile(parseFailureFixture());
      if (result && typeof result.then === 'function') result = await result;
      const errs = result.errors || [];
      const hasError = errs.some((e) => typeof e.code === 'string' && e.code.startsWith('E_'));
      const emptySvg = !result.svg || result.svg.length === 0;
      if (hasError && emptySvg) {
        const codes = Array.from(new Set(errs.map((e) => e.code))).join(',');
        record('vega-lite malformed input → clean rejection', true, 'codes=' + codes);
      } else {
        record('vega-lite malformed input → clean rejection', false,
          'expected E_* error + empty svg; got svg.length=' + (result.svg || '').length +
          ' distinctCodes=' + Array.from(new Set(errs.map((e) => e.code))).join(','));
      }
    } catch (err) {
      record('vega-lite malformed input → clean rejection', false, 'threw: ' + (err.message || err));
    }
  },
};
