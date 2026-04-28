/**
 * tests/cases/test-pro-con.js — WP-1.3j regression suite.
 *
 * Dual-mode: compatible with run.js's `{ label, run(ctx, record) }` convention
 * AND directly runnable via `node test-pro-con.js` (which boots its own jsdom
 * and loads the compiler + pro-con renderer independently).
 *
 * Covers:
 *   - ≥ 5 valid: simple, deep-nesting, weighted, one-sided (all pros), mixed
 *     with source + decision.
 *   - ≥ 3 invalid: missing claim, child with no text, weight out of range
 *     (the schema layer catches this; the renderer layer also enforces it so
 *     Layer-1-only runs still report a usable error).
 *   - SVG checks: claim rect at top centre, stable ids (pc-claim, pc-pro-<path>,
 *     pc-con-<path>, pc-decision), weight badges when weights present.
 */

'use strict';

const fs   = require('fs');
const path = require('path');

// ── Helpers shared by both harness and standalone modes. ────────────────────
function envelope(spec, overrides) {
  const base = {
    schema_version: '0.2',
    id: 'fig-test-pro_con',
    type: 'pro_con',
    mode_context: 'constraint_mapping',
    relation_to_prose: 'integrated',
    spec: spec,
    semantic_description: {
      level_1_elemental: 'Pro-con tree with pros on the left and cons on the right.',
      level_2_statistical: 'Claim with several pros and several cons; optional weights.',
      level_3_perceptual: 'Two columns under a claim rectangle; children indented.',
      level_4_contextual: null,
      short_alt: 'pro-con tree',
      data_table_fallback: null,
    },
    title: 'Test pro_con',
  };
  return Object.assign(base, overrides || {});
}

// Assertion sugar.
const hasSvgRoot    = (s) => typeof s === 'string' && /<svg\b/i.test(s);
const hasClass      = (s, c) => new RegExp('class="[^"]*\\b' + c.replace(/-/g, '\\-') + '\\b').test(s);
const hasAriaImg    = (s) => /role="img"/.test(s);
const hasAriaLabel  = (s) => /aria-label="[^"]+"/.test(s);
const hasId         = (s, id) => new RegExp('id="' + id.replace(/[-.]/g, '\\$&') + '"').test(s);
const countMatches  = (s, re) => { const m = s.match(re); return m ? m.length : 0; };

// Top-of-SVG claim check. Searches for the <rect id="pc-claim" ... y="N"/>
// and verifies N is within the top third of the viewBox.
function claimAtTop(svg) {
  const m = svg.match(/<svg\b[^>]*viewBox="0 0 (\d+(?:\.\d+)?) (\d+(?:\.\d+)?)"/);
  if (!m) return false;
  const height = parseFloat(m[2]);
  const c = svg.match(/<rect id="pc-claim"[^>]*y="(\d+(?:\.\d+)?)"/);
  if (!c) return false;
  return parseFloat(c[1]) < height / 3;
}

// ── Fixtures ────────────────────────────────────────────────────────────────
const validCases = [
  {
    label: 'simple 2-pro 2-con',
    env: envelope({
      claim: 'Adopt a four-day work week',
      pros: [
        { text: 'Retention' },
        { text: 'Focus hours' },
      ],
      cons: [
        { text: 'Coverage gaps' },
        { text: 'Payroll accounting' },
      ],
    }),
    expectIds: ['pc-claim', 'pc-pro-0', 'pc-pro-1', 'pc-con-0', 'pc-con-1'],
    expectNoId: ['pc-decision'],
  },
  {
    label: 'deep tree (3 levels of nesting)',
    env: envelope({
      claim: 'Migrate the platform to a new tech stack',
      pros: [
        {
          text: 'Maintainability',
          children: [
            {
              text: 'Fewer dead deps',
              children: [
                { text: 'Dep A removed' },
                { text: 'Dep B removed' },
              ],
            },
          ],
        },
      ],
      cons: [
        { text: 'Transition cost' },
      ],
    }),
    // Expect 3-level nesting paths are used.
    expectIds: ['pc-pro-0', 'pc-pro-0.0', 'pc-pro-0.0.0', 'pc-pro-0.0.1'],
  },
  {
    label: 'weighted pros and cons (weight 1..5)',
    env: envelope({
      claim: 'Open-source the SDK',
      pros: [
        { text: 'Developer goodwill', weight: 5 },
        { text: 'External contributors', weight: 3 },
      ],
      cons: [
        { text: 'Support load', weight: 4 },
        { text: 'IP leakage risk', weight: 2 },
      ],
    }),
    expectIds: ['pc-claim', 'pc-pro-0', 'pc-pro-1', 'pc-con-0', 'pc-con-1'],
    expectWeightBadges: 4,
  },
  {
    label: 'one-sided (all pros, no cons)',
    env: envelope({
      claim: 'Commit to deterministic builds',
      pros: [
        { text: 'Reproducibility' },
        { text: 'Easier triage' },
        { text: 'Supply-chain hygiene' },
      ],
      cons: [],
    }),
    expectIds: ['pc-claim', 'pc-pro-0', 'pc-pro-1', 'pc-pro-2'],
    expectNoId: ['pc-con-0'],
  },
  {
    label: 'with decision + mixed weights + source',
    env: envelope({
      claim: 'Adopt a four-day work week',
      pros: [
        { text: 'Retention', weight: 4, source: 'HR report 2025' },
        { text: 'Focus hours', weight: 3 },
      ],
      cons: [
        { text: 'Coverage gaps', weight: 3, children: [
          { text: 'Monday on-call', weight: 2 },
        ] },
      ],
      decision: 'Pilot for one quarter',
    }),
    expectIds: ['pc-claim', 'pc-pro-0', 'pc-pro-1', 'pc-con-0', 'pc-con-0.0', 'pc-decision'],
    expectWeightBadges: 4,
  },
];

const invalidCases = [
  {
    label: 'missing claim',
    env: envelope({
      claim: '',
      pros: [{ text: 'Reason 1' }],
      cons: [{ text: 'Reason 2' }],
    }),
    expectCode: 'E_SCHEMA_INVALID',
  },
  {
    label: 'child with no text',
    env: envelope({
      claim: 'Valid claim',
      pros: [{ text: 'Parent', children: [{ text: '' }] }],
      cons: [],
    }),
    expectCode: 'E_SCHEMA_INVALID',
  },
  {
    label: 'negative weight (out of [1, 5])',
    env: envelope({
      claim: 'Valid claim',
      pros: [{ text: 'Reason', weight: -3 }],
      cons: [],
    }),
    expectCode: 'E_SCHEMA_INVALID',
  },
  {
    label: 'weight = 9 exceeds max 5',
    env: envelope({
      claim: 'Valid claim',
      pros: [{ text: 'Reason', weight: 9 }],
      cons: [],
    }),
    expectCode: 'E_SCHEMA_INVALID',
  },
];

// ── Assertion core used by both modes ───────────────────────────────────────
/**
 * runCases(render, record) — feeds every valid and invalid case through the
 * given render(envelope) function and reports via record(name, ok, detail).
 * render may return a plain object (the pro-con renderer does).
 */
function runCases(render, record) {
  for (const tc of validCases) {
    const label = 'valid ' + tc.label;
    try {
      const result = render(tc.env);
      if (!result || (result.errors && result.errors.length)) {
        record(label, false, 'unexpected errors: ' +
          JSON.stringify((result && result.errors) || []));
        continue;
      }
      if (!hasSvgRoot(result.svg)) {
        record(label, false, 'no <svg> root');
        continue;
      }
      if (!hasClass(result.svg, 'ora-visual--pro_con')) {
        record(label, false, 'missing ora-visual--pro_con root class');
        continue;
      }
      if (!hasAriaImg(result.svg) || !hasAriaLabel(result.svg)) {
        record(label, false, 'missing role="img" / aria-label');
        continue;
      }
      if (!claimAtTop(result.svg)) {
        record(label, false, 'claim rect not in top third of viewBox');
        continue;
      }
      // Stable IDs.
      const missing = (tc.expectIds || []).filter((id) => !hasId(result.svg, id));
      if (missing.length) {
        record(label, false, 'missing stable ids: ' + missing.join(', '));
        continue;
      }
      const extras = (tc.expectNoId || []).filter((id) => hasId(result.svg, id));
      if (extras.length) {
        record(label, false, 'unexpected ids present: ' + extras.join(', '));
        continue;
      }
      // Weight badges, if expected.
      if (typeof tc.expectWeightBadges === 'number') {
        const got = countMatches(
          result.svg,
          /class="[^"]*\bora-visual__weight-indicator\b[^"]*"/g
        );
        if (got !== tc.expectWeightBadges) {
          record(label, false,
            'weight-indicator count mismatch: expected ' +
            tc.expectWeightBadges + ', got ' + got);
          continue;
        }
      }
      record(label, true, 'svg ' + result.svg.length + ' chars');
    } catch (err) {
      record(label, false, 'threw: ' + (err && err.stack ? err.stack : err));
    }
  }

  for (const tc of invalidCases) {
    const label = 'invalid ' + tc.label;
    try {
      const result = render(tc.env);
      if (!result) {
        record(label, false, 'no result object');
        continue;
      }
      if (!result.errors || !result.errors.length) {
        record(label, false, 'expected errors but got none; svg length=' +
          (result.svg || '').length);
        continue;
      }
      const codes = result.errors.map((e) => e.code);
      if (!codes.includes(tc.expectCode)) {
        record(label, false, 'expected ' + tc.expectCode + ' but got ' +
          JSON.stringify(codes));
        continue;
      }
      if (result.svg !== '') {
        record(label, false, 'expected empty svg on error, got length=' +
          result.svg.length);
        continue;
      }
      record(label, true);
    } catch (err) {
      record(label, false, 'threw: ' + (err && err.stack ? err.stack : err));
    }
  }
}

// ── run.js integration surface ──────────────────────────────────────────────
module.exports = {
  label: 'Pro-con tree (WP-1.3j) — hand-rolled SVG',
  validCases: validCases,
  invalidCases: invalidCases,
  run: async function run(ctx, record) {
    const { win } = ctx;

    // Lazy-load the renderer into the harness's window if it isn't already
    // there (run.js's core load sequence stops at vega-lite.js). Idempotent.
    if (!win.OraVisualCompiler._renderers.proCon) {
      const COMPILER_DIR = path.resolve(__dirname, '..', '..');
      const src = fs.readFileSync(
        path.join(COMPILER_DIR, 'renderers', 'pro-con.js'), 'utf-8');
      win.eval(src);
    }

    const render = win.OraVisualCompiler._renderers.proCon.render;
    // Harness renderer drives compile() internally for some suites, but for
    // this WP we exercise the renderer directly so invariant-level errors
    // surface even without Ajv Layer-2. The dispatcher path is also asserted.
    runCases(render, record);

    // Dispatcher integration: the pro_con type should no longer be on stub.
    const isStub = win.OraVisualCompiler._dispatcher.isStub;
    record(
      'dispatcher: pro_con type no longer on stub',
      isStub('pro_con') === false,
      'pro_con still wired to stub after renderer load'
    );

    // End-to-end compile() path on a valid envelope.
    try {
      const e = envelope({
        claim: 'Adopt a four-day work week',
        pros: [{ text: 'Retention', weight: 4 }],
        cons: [{ text: 'Coverage gaps', weight: 3 }],
        decision: 'Pilot for one quarter',
      });
      let r = win.OraVisualCompiler.compile(e);
      if (r && typeof r.then === 'function') r = await r;
      record(
        'compile(): e2e valid envelope renders',
        !!r && (r.errors || []).length === 0 && hasSvgRoot(r.svg),
        JSON.stringify((r && r.errors) || []).slice(0, 160)
      );
    } catch (err) {
      record('compile(): e2e valid envelope renders', false,
        'threw: ' + (err && err.stack ? err.stack : err));
    }
  },
};

// ── Standalone mode (invoked via `node test-pro-con.js`) ────────────────────
if (require.main === module) {
  const { JSDOM } = require('jsdom');
  const COMPILER_DIR = path.resolve(__dirname, '..', '..');

  const dom = new JSDOM(
    '<!doctype html><html><head></head><body></body></html>',
    { runScripts: 'outside-only' }
  );
  const win = dom.window;
  win.structuredClone = globalThis.structuredClone ||
    ((v) => JSON.parse(JSON.stringify(v)));

  const loadScript = (p) => win.eval(fs.readFileSync(p, 'utf-8'));
  loadScript(path.join(COMPILER_DIR, 'errors.js'));
  loadScript(path.join(COMPILER_DIR, 'validator.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'stub.js'));
  loadScript(path.join(COMPILER_DIR, 'dispatcher.js'));
  loadScript(path.join(COMPILER_DIR, 'index.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'pro-con.js'));

  let passed = 0, failed = 0;
  const failures = [];
  function record(name, ok, detail) {
    if (ok) { passed += 1; console.log('PASS  ' + name); }
    else    {
      failed += 1;
      failures.push({ name, detail });
      console.log('FAIL  ' + name + '  :: ' + (detail || ''));
    }
  }

  console.log('test-pro-con.js — WP-1.3j standalone harness');
  console.log('----------------------------------------');
  const render = win.OraVisualCompiler._renderers.proCon.render;
  runCases(render, record);

  // Dispatcher integration.
  const isStub = win.OraVisualCompiler._dispatcher.isStub;
  record('dispatcher: pro_con type no longer on stub',
    isStub('pro_con') === false);

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
