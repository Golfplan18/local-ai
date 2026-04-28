/**
 * tests/cases/test-fishbone.js — WP-1.3c regression suite.
 *
 * Dual-mode module:
 *
 *   (a) Imported by the shared tests/run.js harness when it adds fishbone
 *       to its case list — exports `{ label, run(ctx, record) }`.
 *   (b) Run standalone via `node tests/cases/test-fishbone.js` — boots a
 *       minimal jsdom, loads errors.js → validator.js → stub → dispatcher →
 *       index → renderers/fishbone.js, then exercises every fixture.
 *
 * Coverage (Deliverables checklist):
 *   ≥ 5 valid: 6M framework, 4P framework, custom framework, depth-2 tree,
 *     depth-3 tree.
 *   ≥ 3 invalid: depth > 3 (E_SCHEMA_INVALID), non-canonical 6M category
 *     (E_SCHEMA_INVALID), solution-phrased effect
 *     (warning W_EFFECT_SOLUTION_PHRASED asserted).
 *
 * SVG structural checks per case:
 *   - root classes `ora-visual` + `ora-visual--fishbone`
 *   - role="img", aria-label="..."
 *   - stable IDs: fb-effect, fb-category-<slug>, fb-cause-<...>
 *   - exactly one arrowhead marker on the spine (marker-end="url(#fb-arrow)")
 *   - category count matches spec.categories.length
 *   - flat sub-cause count matches spec depth (recursive)
 *   - no inline style/fill/stroke on the root <svg>
 */

'use strict';

const CASES = (function buildCases() {

  function env(spec, overrides) {
    const base = {
      schema_version: '0.2',
      id: 'fig-test-fishbone',
      type: 'fishbone',
      mode_context: 'root_cause_analysis',
      relation_to_prose: 'integrated',
      spec: spec,
      semantic_description: {
        level_1_elemental:  'Fishbone test fixture.',
        level_2_statistical: 'Three categories, one to five causes per category.',
        level_3_perceptual:  'Branches alternate above and below the spine.',
        level_4_contextual:  null,
        short_alt: 'Test fishbone.',
        data_table_fallback: null,
      },
      title: 'Test fishbone',
    };
    return Object.assign(base, overrides || {});
  }

  const valid = [
    {
      label: '6M framework with single-cause categories',
      env: env({
        effect: 'Deploys fail intermittently',
        framework: '6M',
        categories: [
          { name: 'Machine', causes: [{ text: 'Build server low memory' }] },
          { name: 'Method',  causes: [{ text: 'No canary stage' }] },
          { name: 'Man',     causes: [{ text: 'Reviewer fatigue' }] },
        ],
      }),
      expectCategories: 3,
      expectCauseCount: 3,
    },
    {
      label: '4P framework mixing sub-causes',
      env: env({
        effect: 'Customer churn too high this quarter',
        framework: '4P',
        categories: [
          { name: 'People',  causes: [{ text: 'Support staffing low' }] },
          { name: 'Process', causes: [
            { text: 'Onboarding is slow',
              sub_causes: [{ text: 'Docs scattered' }] },
          ] },
          { name: 'Policy',  causes: [{ text: 'Refund rules unclear' }] },
          { name: 'Place',   causes: [{ text: 'In-app help hidden' }] },
        ],
      }),
      expectCategories: 4,
      expectCauseCount: 5,
    },
    {
      label: 'custom framework allows arbitrary category names',
      env: env({
        effect: 'Not enough latte art classes booked',
        framework: 'custom',
        categories: [
          { name: 'Teachers',   causes: [{ text: 'Only two on payroll' }] },
          { name: 'Marketing',  causes: [{ text: 'No social reach' }] },
          { name: 'Schedule',   causes: [{ text: 'Evenings only' }] },
        ],
      }),
      expectCategories: 3,
      expectCauseCount: 3,
    },
    {
      label: 'depth-2 cause tree (cause → sub-cause)',
      env: env({
        effect: 'Throughput too low on CI workers',
        framework: '6M',
        categories: [
          { name: 'Machine', causes: [
            { text: 'Disk contention',
              sub_causes: [
                { text: 'Shared NVMe' },
                { text: 'Noisy neighbour tenant' },
              ] },
          ] },
          { name: 'Measurement', causes: [
            { text: 'Timers undersampled',
              sub_causes: [{ text: 'Reporter rate low' }] },
          ] },
        ],
      }),
      expectCategories: 2,
      expectCauseCount: 5,  // 2 top + 3 subs
    },
    {
      label: 'depth-3 cause tree (cause → sub → sub-sub)',
      env: env({
        effect: 'Error rate not returning to baseline',
        framework: '6M',
        categories: [
          { name: 'Method', causes: [
            { text: 'Retry policy unclear',
              sub_causes: [
                { text: 'Budget not enforced',
                  sub_causes: [
                    { text: 'Counter resets too fast' },
                    { text: 'Timeout too generous' },
                  ] },
              ] },
          ] },
        ],
      }),
      expectCategories: 1,
      expectCauseCount: 4,  // 1 + 1 + 2
    },
  ];

  const invalid = [
    {
      label: 'depth > 3 rejected with E_SCHEMA_INVALID',
      env: env({
        effect: 'System fails under load',
        framework: '6M',
        categories: [
          { name: 'Method', causes: [
            { text: 'L1',
              sub_causes: [
                { text: 'L2',
                  sub_causes: [
                    { text: 'L3',
                      sub_causes: [
                        { text: 'L4 — too deep' },
                      ] },
                  ] },
              ] },
          ] },
        ],
      }),
      expectCode: 'E_SCHEMA_INVALID',
      expectPathIncludes: 'sub_causes',
    },
    {
      label: 'non-canonical 6M category rejected with E_SCHEMA_INVALID',
      env: env({
        effect: 'Builds fail randomly',
        framework: '6M',
        categories: [
          { name: 'Machine',   causes: [{ text: 'OK' }] },
          { name: 'Politics',  causes: [{ text: 'Not a 6M category' }] },
        ],
      }),
      expectCode: 'E_SCHEMA_INVALID',
      expectMessageIncludes: 'canonical',
    },
    {
      label: 'solution-phrased effect emits W_EFFECT_SOLUTION_PHRASED',
      env: env({
        effect: 'Improve customer checkout speed',
        framework: 'custom',
        categories: [
          { name: 'Frontend', causes: [{ text: 'Bundle size' }] },
          { name: 'Backend',  causes: [{ text: 'DB index missing' }] },
        ],
      }),
      expectWarning: 'W_EFFECT_SOLUTION_PHRASED',
    },
  ];

  return { valid: valid, invalid: invalid };
}());

// ────────────────────────────────────────────────────────────────────────────
// Assertions (pure string-level; no DOM dependency, works in jsdom or plain).
// ────────────────────────────────────────────────────────────────────────────
function hasRootClass(svg, cls) {
  const m = svg.match(/<svg\b[^>]*\sclass="([^"]*)"/);
  if (!m) return false;
  return m[1].split(/\s+/).indexOf(cls) >= 0;
}
function hasRoleImg(svg)    { return /<svg\b[^>]*\srole="img"/.test(svg); }
function hasAriaLabel(svg)  { return /<svg\b[^>]*\saria-label="[^"]+"/.test(svg); }
function hasArrowheadMarker(svg) {
  // Exactly one marker-end="url(#fb-arrow)" on the spine.
  const matches = svg.match(/marker-end="url\(#fb-arrow\)"/g);
  return matches && matches.length === 1;
}
function hasId(svg, id) {
  return new RegExp('id="' + id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '"').test(svg);
}
function countCategoryGroups(svg) {
  const m = svg.match(/id="fb-category-[^"]+"/g);
  return m ? m.length : 0;
}
function countCauseGroups(svg) {
  const m = svg.match(/id="fb-cause-[^"]+"/g);
  return m ? m.length : 0;
}
function rootHasInlineStyle(svg) {
  const m = svg.match(/<svg\b[^>]*>/);
  if (!m) return false;
  const tag = m[0];
  return /\sstyle="/.test(tag) || /\sfill="/.test(tag) ||
         /\sstroke="/.test(tag) || /\sfont-family="/.test(tag);
}

function slugify(s) {
  return String(s || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'x';
}

// Total cause count across the tree (helper matching renderer's flat-count).
function flatCauseCount(causes) {
  if (!Array.isArray(causes)) return 0;
  let n = causes.length;
  for (const c of causes) {
    if (c && Array.isArray(c.sub_causes)) n += flatCauseCount(c.sub_causes);
  }
  return n;
}

// ────────────────────────────────────────────────────────────────────────────
// Module export for shared tests/run.js
// ────────────────────────────────────────────────────────────────────────────
module.exports = {
  label: 'Fishbone renderer — WP-1.3c (≥5 valid, ≥3 invalid)',
  CASES: CASES,
  run: async function run(ctx, record) {
    const { win } = ctx;
    const OVC = win.OraVisualCompiler;

    // Make sure the renderer is loaded in the harness's jsdom.
    if (!OVC._renderers || !OVC._renderers.fishbone) {
      // Attempt lazy load — the standard harness preloads stub/vega-lite
      // but won't know about fishbone until its path is appended.
      try {
        const fs = require('fs');
        const path = require('path');
        const COMPILER_DIR = path.resolve(__dirname, '..', '..');
        const src = fs.readFileSync(
          path.join(COMPILER_DIR, 'renderers', 'fishbone.js'), 'utf-8');
        win.eval(src);
      } catch (err) {
        record('fishbone: renderer load', false,
          'renderer not registered and could not lazy-load: ' + (err.message || err));
        return;
      }
    }

    // ── Valid cases ──
    for (const tc of CASES.valid) {
      const name = 'fishbone valid: ' + tc.label;
      try {
        let result = OVC.compile(tc.env);
        if (result && typeof result.then === 'function') result = await result;

        const errs = (result.errors || []).filter((e) => e.code && e.code.startsWith('E_'));
        if (errs.length) {
          record(name, false, 'unexpected errors: ' +
            errs.map((e) => e.code + ':' + e.message).join('; '));
          continue;
        }
        const svg = result.svg || '';
        const fail = checkValidSvg(svg, tc);
        if (fail) { record(name, false, fail); continue; }
        record(name, true, 'svg ' + svg.length + ' chars');
      } catch (err) {
        record(name, false, 'threw: ' + (err && err.stack ? err.stack : err));
      }
    }

    // ── Invalid cases ──
    for (const tc of CASES.invalid) {
      const name = 'fishbone invalid: ' + tc.label;
      try {
        let result = OVC.compile(tc.env);
        if (result && typeof result.then === 'function') result = await result;

        const errs = result.errors || [];
        const warns = result.warnings || [];

        if (tc.expectWarning) {
          // Warning-only case: should still render successfully with a
          // non-empty SVG and contain the expected warning code.
          const hasW = warns.some((w) => w.code === tc.expectWarning);
          const emptyErr = errs.filter((e) => e.code && e.code.startsWith('E_')).length === 0;
          if (!hasW || !emptyErr) {
            record(name, false,
              'expected warning ' + tc.expectWarning + ' + no errors; got errors=' +
              JSON.stringify(errs.map((e) => e.code)) + ' warnings=' +
              JSON.stringify(warns.map((w) => w.code)));
            continue;
          }
          if (!result.svg || result.svg.length === 0) {
            record(name, false, 'warning case produced empty svg (should still render)');
            continue;
          }
          record(name, true, 'warning ' + tc.expectWarning + ' emitted');
          continue;
        }

        const codes = errs.map((e) => e.code);
        if (codes.indexOf(tc.expectCode) < 0) {
          record(name, false, 'expected ' + tc.expectCode +
            ' but got ' + JSON.stringify(codes));
          continue;
        }
        if (tc.expectPathIncludes) {
          const matched = errs.some((e) => e.code === tc.expectCode &&
            typeof e.path === 'string' && e.path.indexOf(tc.expectPathIncludes) >= 0);
          if (!matched) {
            record(name, false, 'expected path including ' +
              JSON.stringify(tc.expectPathIncludes) + '; got paths=' +
              JSON.stringify(errs.map((e) => e.path)));
            continue;
          }
        }
        if (tc.expectMessageIncludes) {
          const matched = errs.some((e) => e.code === tc.expectCode &&
            typeof e.message === 'string' &&
            e.message.toLowerCase().indexOf(tc.expectMessageIncludes.toLowerCase()) >= 0);
          if (!matched) {
            record(name, false, 'expected message including ' +
              JSON.stringify(tc.expectMessageIncludes));
            continue;
          }
        }
        if (result.svg && result.svg.length > 0) {
          record(name, false, 'expected empty svg on error, got length=' + result.svg.length);
          continue;
        }
        record(name, true, 'rejected with ' + tc.expectCode);
      } catch (err) {
        record(name, false, 'threw: ' + (err && err.stack ? err.stack : err));
      }
    }

    // ── Dispatcher wiring sanity ──
    const disp = OVC._dispatcher;
    if (disp && typeof disp.isStub === 'function') {
      record('fishbone: renderer replaces stub',
        disp.isStub('fishbone') === false,
        'fishbone still on stub after renderer load');
    }
  },
};

// Per-case validator for valid SVGs.
function checkValidSvg(svg, tc) {
  if (!svg || svg.length === 0) return 'empty svg';
  if (!hasRootClass(svg, 'ora-visual')) return 'missing ora-visual class on root';
  if (!hasRootClass(svg, 'ora-visual--fishbone')) return 'missing ora-visual--fishbone class on root';
  if (!hasRoleImg(svg))    return 'missing role="img" on root';
  if (!hasAriaLabel(svg))  return 'missing aria-label on root';
  if (rootHasInlineStyle(svg)) return 'root <svg> carries inline style/fill/stroke/font-family';
  if (!hasArrowheadMarker(svg)) return 'expected exactly one marker-end="url(#fb-arrow)" on the spine';
  if (!hasId(svg, 'fb-effect')) return 'missing id="fb-effect"';
  for (const cat of tc.env.spec.categories) {
    const slug = slugify(cat.name);
    if (!hasId(svg, 'fb-category-' + slug)) {
      return 'missing id="fb-category-' + slug + '" for category ' + cat.name;
    }
  }
  const catGroups = countCategoryGroups(svg);
  if (catGroups !== tc.expectCategories) {
    return 'category count mismatch: expected ' + tc.expectCategories +
      ', got ' + catGroups;
  }
  const causeGroups = countCauseGroups(svg);
  if (causeGroups !== tc.expectCauseCount) {
    return 'cause count mismatch: expected ' + tc.expectCauseCount +
      ', got ' + causeGroups;
  }
  return null;
}

// ────────────────────────────────────────────────────────────────────────────
// Standalone entrypoint (node tests/cases/test-fishbone.js)
// ────────────────────────────────────────────────────────────────────────────
if (require.main === module) {
  (async function standalone() {
    const fs = require('fs');
    const path = require('path');
    const { JSDOM } = require('jsdom');

    const COMPILER_DIR = path.resolve(__dirname, '..', '..');
    const read = (p) => fs.readFileSync(p, 'utf-8');

    const dom = new JSDOM(
      '<!DOCTYPE html><html><head></head><body></body></html>',
      { runScripts: 'outside-only' }
    );
    const win = dom.window;
    win.structuredClone = globalThis.structuredClone ||
      ((v) => JSON.parse(JSON.stringify(v)));

    const loadScript = (abs) => win.eval(read(abs));

    loadScript(path.join(COMPILER_DIR, 'errors.js'));
    loadScript(path.join(COMPILER_DIR, 'validator.js'));
    loadScript(path.join(COMPILER_DIR, 'renderers', 'stub.js'));
    loadScript(path.join(COMPILER_DIR, 'dispatcher.js'));
    loadScript(path.join(COMPILER_DIR, 'index.js'));
    loadScript(path.join(COMPILER_DIR, 'palettes.js'));
    loadScript(path.join(COMPILER_DIR, 'renderers', 'fishbone.js'));

    let passed = 0;
    let failed = 0;
    const fails = [];
    const record = (name, ok, detail) => {
      if (ok) { passed += 1; console.log('  PASS  ' + name + (detail ? ' — ' + detail : '')); }
      else    { failed += 1; fails.push({ name, detail });
                console.log('  FAIL  ' + name + '  :: ' + (detail || '(no detail)')); }
    };

    console.log('test-fishbone.js — WP-1.3c standalone');
    console.log('----------------------------------------');
    await module.exports.run({ win: win }, record);
    console.log('----------------------------------------');
    console.log('Results: ' + passed + ' passed / ' + (passed + failed) + ' total (' +
      failed + ' failed)');
    if (failed > 0) {
      console.log('\nFailures:');
      for (const f of fails) console.log('  - ' + f.name + ' :: ' + f.detail);
      process.exit(1);
    }
    process.exit(0);
  }()).catch((err) => {
    console.error('Harness crashed:', err && err.stack ? err.stack : err);
    process.exit(2);
  });
}
