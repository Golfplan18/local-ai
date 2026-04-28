/**
 * test-concept-map.js — WP-1.3k regression suite.
 *
 * Standalone: runs directly under Node with jsdom. Loads the compiler
 * core, the vendored @viz-js/viz standalone bundle, the dot-engine
 * primitive, and the concept-map renderer; then exercises:
 *
 *   - ≥ 5 valid concept maps:
 *       * simple 3-concept map
 *       * concept hierarchy (parent/child levels)
 *       * cross-links present
 *       * many linking phrases shared across concepts
 *       * single-concept degenerate (no propositions)
 *   - ≥ 3 invalid concept maps:
 *       * unresolved concept id in proposition   (E_UNRESOLVED_REF)
 *       * unresolved phrase id in proposition    (E_UNRESOLVED_REF)
 *       * empty concepts array                   (E_SCHEMA_INVALID)
 *   - Soft-warning case: map with no cross-links → W_NO_CROSS_LINKS
 *   - SVG checks: ellipses for concepts, plaintext phrases, dashed cross-
 *     link edges, stable semantic IDs.
 *
 * Usage:
 *   node test-concept-map.js
 *
 * Exits non-zero on any failure.
 *
 * Mirrors the structure of test-causal-dag.js (same harness conventions).
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

// ── Load concept-map renderer ──────────────────────────────────────────────
const RENDERER = path.join(COMPILER_DIR, 'renderers', 'concept-map.js');
vm.runInContext(read(RENDERER), ctx, { filename: RENDERER });

const OVC = window.OraVisualCompiler;
if (!OVC._renderers || !OVC._renderers.conceptMap) {
  console.error('FAIL: OraVisualCompiler._renderers.conceptMap not exposed');
  process.exit(1);
}

// ── Envelope factory ───────────────────────────────────────────────────────
function envelope(spec, overrides) {
  const base = {
    schema_version: '0.2',
    id: 'fig-test-concept-map',
    type: 'concept_map',
    mode_context: 'relationship_mapping',
    relation_to_prose: 'integrated',
    spec: spec,
    semantic_description: {
      level_1_elemental: 'Test concept map',
      level_2_statistical: null,
      level_3_perceptual: null,
      level_4_contextual: null,
      short_alt: 'test concept map',
      data_table_fallback: null,
    },
    title: 'Test concept map',
  };
  return Object.assign(base, overrides || {});
}

// ── Valid fixtures ─────────────────────────────────────────────────────────
const validCases = [
  {
    label: 'simple 3-concept map',
    env: envelope({
      focus_question: 'What does a plant need?',
      concepts: [
        { id: 'plant', label: 'Plant', hierarchy_level: 0 },
        { id: 'water', label: 'Water', hierarchy_level: 1 },
        { id: 'sun',   label: 'Sunlight', hierarchy_level: 1 },
      ],
      linking_phrases: [
        { id: 'needs', text: 'needs' },
      ],
      propositions: [
        { from_concept: 'plant', via_phrase: 'needs', to_concept: 'water', is_cross_link: true },
        { from_concept: 'plant', via_phrase: 'needs', to_concept: 'sun' },
      ],
    }),
    expectConcepts: 3,
    expectPropositions: 2,
    expectCrossLinks: 1,
  },
  {
    label: 'concept hierarchy (3 levels, parent/child)',
    env: envelope({
      focus_question: 'How do systems break down?',
      concepts: [
        { id: 'sys',    label: 'System',       hierarchy_level: 0 },
        { id: 'sub1',   label: 'Subsystem A',  hierarchy_level: 1 },
        { id: 'sub2',   label: 'Subsystem B',  hierarchy_level: 1 },
        { id: 'part1',  label: 'Part A1',      hierarchy_level: 2 },
        { id: 'part2',  label: 'Part A2',      hierarchy_level: 2 },
        { id: 'part3',  label: 'Part B1',      hierarchy_level: 2 },
      ],
      linking_phrases: [
        { id: 'contains', text: 'contains' },
        { id: 'related',  text: 'is related to' },
      ],
      propositions: [
        { from_concept: 'sys',  via_phrase: 'contains', to_concept: 'sub1' },
        { from_concept: 'sys',  via_phrase: 'contains', to_concept: 'sub2' },
        { from_concept: 'sub1', via_phrase: 'contains', to_concept: 'part1' },
        { from_concept: 'sub1', via_phrase: 'contains', to_concept: 'part2' },
        { from_concept: 'sub2', via_phrase: 'contains', to_concept: 'part3' },
        { from_concept: 'part2', via_phrase: 'related',  to_concept: 'part3', is_cross_link: true },
      ],
    }),
    expectConcepts: 6,
    expectPropositions: 6,
    expectCrossLinks: 1,
  },
  {
    label: 'multiple cross-links present',
    env: envelope({
      focus_question: 'How does velocity interact with tech debt?',
      concepts: [
        { id: 'V', label: 'Velocity',  hierarchy_level: 0 },
        { id: 'T', label: 'Tech debt', hierarchy_level: 1 },
        { id: 'F', label: 'Fires',     hierarchy_level: 2 },
      ],
      linking_phrases: [
        { id: 'L1', text: 'produces' },
        { id: 'L2', text: 'causes' },
        { id: 'L3', text: 'slows' },
      ],
      propositions: [
        { from_concept: 'V', via_phrase: 'L1', to_concept: 'T' },
        { from_concept: 'T', via_phrase: 'L2', to_concept: 'F' },
        { from_concept: 'F', via_phrase: 'L3', to_concept: 'V', is_cross_link: true },
        { from_concept: 'T', via_phrase: 'L1', to_concept: 'F', is_cross_link: true },
      ],
    }),
    expectConcepts: 3,
    expectPropositions: 4,
    expectCrossLinks: 2,
  },
  {
    label: 'many linking phrases shared across concepts',
    env: envelope({
      focus_question: 'What behaviours shape learning?',
      concepts: [
        { id: 'learn',    label: 'Learning',    hierarchy_level: 0 },
        { id: 'practice', label: 'Practice',    hierarchy_level: 1 },
        { id: 'fdbk',     label: 'Feedback',    hierarchy_level: 1 },
        { id: 'reflect',  label: 'Reflection',  hierarchy_level: 1 },
        { id: 'mastery',  label: 'Mastery',     hierarchy_level: 2 },
      ],
      linking_phrases: [
        { id: 'req',   text: 'requires' },
        { id: 'emer',  text: 'emerges from' },
        { id: 'info',  text: 'informs' },
      ],
      propositions: [
        { from_concept: 'learn',    via_phrase: 'req',  to_concept: 'practice' },
        { from_concept: 'learn',    via_phrase: 'req',  to_concept: 'fdbk' },
        { from_concept: 'learn',    via_phrase: 'req',  to_concept: 'reflect' },
        { from_concept: 'practice', via_phrase: 'info', to_concept: 'reflect', is_cross_link: true },
        { from_concept: 'fdbk',     via_phrase: 'info', to_concept: 'reflect', is_cross_link: true },
        { from_concept: 'mastery',  via_phrase: 'emer', to_concept: 'learn',   is_cross_link: true },
      ],
    }),
    expectConcepts: 5,
    expectPropositions: 6,
    expectCrossLinks: 3,
  },
  {
    label: 'single-concept degenerate (no propositions)',
    env: envelope({
      focus_question: 'What is the isolated concept?',
      concepts: [
        { id: 'solo', label: 'Lonely concept', hierarchy_level: 0 },
      ],
      linking_phrases: [],
      propositions: [],
    }),
    expectConcepts: 1,
    expectPropositions: 0,
    expectCrossLinks: 0,
    // No propositions → no cross-links check triggered (by design: warning
    // only fires when propositions.length > 0). This case verifies the
    // degenerate path doesn't crash and produces valid SVG.
    expectNoCrossLinkWarning: true,
  },
];

// Separate fixture for the soft-warning assertion.
const noCrossLinkCase = {
  label: 'propositions present, none cross-linked → W_NO_CROSS_LINKS',
  env: envelope({
    focus_question: 'Linear map with no integrative links',
    concepts: [
      { id: 'a', label: 'A', hierarchy_level: 0 },
      { id: 'b', label: 'B', hierarchy_level: 1 },
      { id: 'c', label: 'C', hierarchy_level: 2 },
    ],
    linking_phrases: [
      { id: 'p', text: 'leads to' },
    ],
    propositions: [
      { from_concept: 'a', via_phrase: 'p', to_concept: 'b' },
      { from_concept: 'b', via_phrase: 'p', to_concept: 'c' },
    ],
  }),
  expectWarningCode: 'W_NO_CROSS_LINKS',
};

// ── Invalid fixtures ───────────────────────────────────────────────────────
const invalidCases = [
  {
    label: 'unresolved concept id in proposition',
    env: envelope({
      focus_question: 'unresolved concept',
      concepts: [
        { id: 'a', label: 'A', hierarchy_level: 0 },
        { id: 'b', label: 'B', hierarchy_level: 1 },
      ],
      linking_phrases: [
        { id: 'p', text: 'relates to' },
      ],
      propositions: [
        // 'missing' is not a declared concept id.
        { from_concept: 'a', via_phrase: 'p', to_concept: 'missing' },
      ],
    }),
    expectCode: 'E_UNRESOLVED_REF',
  },
  {
    label: 'unresolved phrase id in proposition',
    env: envelope({
      focus_question: 'unresolved phrase',
      concepts: [
        { id: 'a', label: 'A', hierarchy_level: 0 },
        { id: 'b', label: 'B', hierarchy_level: 1 },
      ],
      linking_phrases: [
        { id: 'p', text: 'relates to' },
      ],
      propositions: [
        // 'nonesuch' is not a declared linking_phrase id.
        { from_concept: 'a', via_phrase: 'nonesuch', to_concept: 'b' },
      ],
    }),
    expectCode: 'E_UNRESOLVED_REF',
  },
  {
    label: 'empty concepts array (no propositions)',
    env: envelope({
      focus_question: 'nothing here',
      concepts: [],
      linking_phrases: [],
      propositions: [],
    }),
    expectCode: 'E_SCHEMA_INVALID',
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
const hasConceptId = (s, id) => new RegExp('id="cm\\-concept\\-' + id + '"').test(s);
const hasInlineStyle = (s) => /\sstyle="/.test(s) || /\sfill="/.test(s) ||
                              /\sstroke="/.test(s) || /\sfont-family="/.test(s);

// ── Unit tests: internal helpers ──────────────────────────────────────────
function unitValidateAndDot() {
  const internals = OVC._renderers.conceptMap;

  // validateReferences: all-resolved case → no errors.
  const okSpec = {
    focus_question: 'q',
    concepts: [{ id: 'a', label: 'A', hierarchy_level: 0 },
               { id: 'b', label: 'B', hierarchy_level: 1 }],
    linking_phrases: [{ id: 'p', text: 'is' }],
    propositions: [{ from_concept: 'a', via_phrase: 'p', to_concept: 'b',
                     is_cross_link: true }],
  };
  const ok = internals._validateReferences(okSpec);
  report(
    'unit(validateRefs): clean spec yields no errors',
    ok.errors.length === 0,
    JSON.stringify(ok.errors)
  );
  report(
    'unit(validateRefs): cross-link present suppresses W_NO_CROSS_LINKS',
    ok.warnings.every((w) => w.code !== 'W_NO_CROSS_LINKS'),
    JSON.stringify(ok.warnings)
  );

  // validateReferences: missing concept → E_UNRESOLVED_REF.
  const bad = internals._validateReferences({
    focus_question: 'q',
    concepts: [{ id: 'a', label: 'A', hierarchy_level: 0 }],
    linking_phrases: [{ id: 'p', text: 'is' }],
    propositions: [{ from_concept: 'a', via_phrase: 'p', to_concept: 'z' }],
  });
  report(
    'unit(validateRefs): unresolved to_concept yields E_UNRESOLVED_REF',
    bad.errors.length === 1 && bad.errors[0].code === 'E_UNRESOLVED_REF',
    JSON.stringify(bad.errors)
  );

  // validateReferences: no cross-links → W_NO_CROSS_LINKS warning.
  const nocl = internals._validateReferences({
    focus_question: 'q',
    concepts: [{ id: 'a', label: 'A', hierarchy_level: 0 },
               { id: 'b', label: 'B', hierarchy_level: 1 }],
    linking_phrases: [{ id: 'p', text: 'is' }],
    propositions: [{ from_concept: 'a', via_phrase: 'p', to_concept: 'b' }],
  });
  report(
    'unit(validateRefs): no cross-links yields W_NO_CROSS_LINKS warning',
    nocl.warnings.length === 1 &&
      nocl.warnings[0].code === 'W_NO_CROSS_LINKS',
    JSON.stringify(nocl.warnings)
  );

  // specToDot: emits the CXL-style intermediate phrase node.
  const dot = internals._specToDot(okSpec, { title: 'Test' });
  report(
    'unit(specToDot): concept ellipse emitted',
    /shape=ellipse/.test(dot),
    'shape=ellipse not found'
  );
  report(
    'unit(specToDot): linking phrase emitted as plaintext',
    /shape=plaintext/.test(dot),
    'shape=plaintext not found'
  );
  report(
    'unit(specToDot): concept semantic id emitted',
    /id="cm\-concept\-a"/.test(dot),
    'cm-concept-a id not found'
  );
  report(
    'unit(specToDot): proposition semantic id emitted',
    /id="cm\-prop\-a\-p\-b"/.test(dot),
    'cm-prop-a-p-b id not found'
  );
  report(
    'unit(specToDot): cross-link edge has dashed style',
    /style=dashed/.test(dot),
    'style=dashed not present'
  );
  report(
    'unit(specToDot): cross-link edge has cross-link class',
    /ora\-visual__cm\-edge\-\-cross\-link/.test(dot),
    'cross-link class not emitted'
  );
  report(
    'unit(specToDot): concept→phrase edge uses dir=none',
    /dir=none/.test(dot),
    'dir=none not found on first-half edge'
  );
}

// ── Valid runner ───────────────────────────────────────────────────────────
async function runValid() {
  for (const tc of validCases) {
    const label = 'valid ' + tc.label;
    try {
      const result = await OVC._renderers.conceptMap.render(tc.env);
      if (!result || result.errors.length) {
        report(label, false, 'unexpected errors: ' +
          JSON.stringify((result && result.errors) || []));
        continue;
      }
      if (!hasSvgRoot(result.svg)) {
        report(label, false, 'no <svg> root in output');
        continue;
      }
      if (!hasClass(result.svg, 'ora-visual--concept_map')) {
        report(label, false, 'missing ora-visual--concept_map class on root');
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

      // Every declared concept should carry id="cm-concept-<id>".
      let missing = [];
      for (const c of tc.env.spec.concepts) {
        if (!hasConceptId(result.svg, c.id)) missing.push(c.id);
      }
      if (missing.length) {
        report(label, false,
          'missing semantic concept IDs for: ' + missing.join(', '));
        continue;
      }

      // Concept count via semantic class.
      const conceptCount = countMatches(
        result.svg,
        /class="[^"]*\bora-visual__cm-concept\b[^"]*"/g
      );
      if (conceptCount !== tc.expectConcepts) {
        report(label, false, 'concept count mismatch: expected ' +
          tc.expectConcepts + ', got ' + conceptCount);
        continue;
      }

      // Proposition count: each proposition emits an <out> edge with
      // class ora-visual__cm-prop (we match the half-edge that carries the
      // canonical cm-prop-<from>-<via>-<to> id; the in-edge has --in suffix).
      // Negative lookbehind excludes the --in half-edge.
      const propCount = countMatches(
        result.svg,
        /id="cm-prop-[^"]*(?<!--in)"/g
      );
      if (propCount !== tc.expectPropositions) {
        report(label, false, 'proposition count mismatch: expected ' +
          tc.expectPropositions + ', got ' + propCount);
        continue;
      }

      // Cross-link class count: each cross-link proposition emits both a
      // concept→phrase and phrase→concept edge with the cross-link class,
      // so the count should be 2 × expectCrossLinks in the SVG (bi-half).
      if (typeof tc.expectCrossLinks === 'number') {
        const crossLinkClassCount = countMatches(
          result.svg,
          /class="[^"]*\bora-visual__cm-edge--cross-link\b[^"]*"/g
        );
        const expected = tc.expectCrossLinks * 2;
        if (crossLinkClassCount !== expected) {
          report(label, false, 'cross-link class count mismatch: expected ' +
            expected + ' (2 halves per cross-link prop), got ' +
            crossLinkClassCount);
          continue;
        }
      }

      // Plaintext phrase node check: every proposition emits one.
      if (tc.expectPropositions > 0) {
        const phraseCount = countMatches(
          result.svg,
          /class="[^"]*\bora-visual__cm-phrase\b[^"]*"/g
        );
        if (phraseCount !== tc.expectPropositions) {
          report(label, false, 'phrase-node count mismatch: expected ' +
            tc.expectPropositions + ', got ' + phraseCount);
          continue;
        }
      }

      // W_NO_CROSS_LINKS warning gating:
      //   - expectNoCrossLinkWarning:true  → must NOT be present (no props).
      //   - tc.expectCrossLinks > 0        → must NOT be present.
      //   - tc.expectCrossLinks === 0 with propositions → expected.
      const hasNoClWarning = result.warnings.some(
        (w) => w.code === 'W_NO_CROSS_LINKS');
      if (tc.expectNoCrossLinkWarning === true && hasNoClWarning) {
        report(label, false,
          'unexpected W_NO_CROSS_LINKS warning on degenerate no-prop case');
        continue;
      }
      if (tc.expectCrossLinks > 0 && hasNoClWarning) {
        report(label, false,
          'unexpected W_NO_CROSS_LINKS when cross-links are present');
        continue;
      }

      report(label, true);
    } catch (err) {
      report(label, false, 'threw: ' + (err && err.stack ? err.stack : err));
    }
  }
}

// ── Soft-warning runner ────────────────────────────────────────────────────
async function runSoftWarning() {
  const label = 'warning ' + noCrossLinkCase.label;
  try {
    const result = await OVC._renderers.conceptMap.render(noCrossLinkCase.env);
    if (!result) {
      report(label, false, 'no result object');
      return;
    }
    if (result.errors.length) {
      report(label, false, 'unexpected errors: ' +
        JSON.stringify(result.errors));
      return;
    }
    const has = result.warnings.some(
      (w) => w.code === noCrossLinkCase.expectWarningCode);
    if (!has) {
      report(label, false, 'W_NO_CROSS_LINKS not present; got warnings: ' +
        JSON.stringify(result.warnings.map((w) => w.code)));
      return;
    }
    if (!hasSvgRoot(result.svg)) {
      report(label, false, 'no <svg> root in output despite soft warning');
      return;
    }
    report(label, true);
  } catch (err) {
    report(label, false, 'threw: ' + (err && err.stack ? err.stack : err));
  }
}

// ── Invalid runner ─────────────────────────────────────────────────────────
async function runInvalid() {
  for (const tc of invalidCases) {
    const label = 'invalid ' + tc.label;
    try {
      const result = await OVC._renderers.conceptMap.render(tc.env);
      if (!result) {
        report(label, false, 'no result object');
        continue;
      }
      if (!result.errors.length) {
        report(label, false,
          'expected errors but got none; svg length=' + result.svg.length);
        continue;
      }
      const codes = result.errors.map((e) => e.code);
      if (!codes.includes(tc.expectCode)) {
        report(label, false, 'expected ' + tc.expectCode +
          ' but got ' + JSON.stringify(codes));
        continue;
      }
      if (result.svg !== '') {
        report(label, false, 'expected empty svg on error, got length=' +
          result.svg.length);
        continue;
      }
      report(label, true);
    } catch (err) {
      report(label, false, 'threw: ' + (err && err.stack ? err.stack : err));
    }
  }
}

// ── Dispatcher integration ────────────────────────────────────────────────
async function runDispatcherIntegration() {
  const label = 'dispatcher: concept_map type no longer on stub';
  const { isStub } = OVC._dispatcher;
  report(label, isStub('concept_map') === false,
    'concept_map still wired to stub after renderer load');
}

// ── Main ──────────────────────────────────────────────────────────────────
(async function main() {
  console.log('test-concept-map.js — WP-1.3k');
  try {
    const ver = read(path.join(COMPILER_DIR, 'vendor', 'viz-js', 'VERSION')).trim();
    console.log('@viz-js/viz version: ' + ver);
  } catch (_) { /* VERSION file optional */ }
  console.log('jsdom version: ' + require('jsdom/package.json').version);
  console.log('----------------------------------------');

  unitValidateAndDot();
  await runValid();
  await runSoftWarning();
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
