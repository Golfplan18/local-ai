/**
 * tests/cases/test-bow-tie.js — WP-1.3h regression suite.
 *
 * Exports:
 *   module.exports = { label, run(ctx, record), CASES }
 *
 * Two invocation modes:
 *
 *   1. Harness mode — run.js (or any sibling harness) can `require` this
 *      module and call `run(ctx, record)` with a shared jsdom context.
 *      In harness mode the bow-tie renderer is loaded into ctx.win on
 *      first call so the suite is self-sufficient even when run.js hasn't
 *      been updated to load renderers/bow-tie.js explicitly.
 *
 *   2. Standalone mode — `node test-bow-tie.js` spins up its own jsdom,
 *      loads the compiler core + bow-tie renderer, and runs the same
 *      suite. Exits non-zero on any failure.
 *
 * Coverage:
 *   ≥ 5 valid envelopes:
 *     - 1 threat / 1 consequence / no controls (minimal)
 *     - multi-threat / multi-consequence
 *     - full preventive enum (eliminate/reduce/detect)
 *     - full mitigative enum (reduce/recover/contain)
 *     - asymmetric threat vs consequence count (2 threats, 3 consequences)
 *     - escalation_factors present
 *   ≥ 3 invalid envelopes (all must return E_SCHEMA_INVALID):
 *     - preventive control type declared as 'recover' (mitigative-only)
 *     - mitigative control type declared as 'detect' (preventive-only)
 *     - zero threats
 *     - zero consequences (bonus)
 *   SVG structural checks on every valid case:
 *     - Root svg has class 'ora-visual ora-visual--bow_tie' and role=img
 *     - Root svg has no inline style/fill/stroke/font-* attrs
 *     - Stable IDs for event / each threat / each consequence / each control
 *     - Left/right symmetry around x = viewBox.width / 2:
 *         all threat x-coords equal 15% of viewBox width
 *         all consequence x-coords equal 85% of viewBox width
 *         threat-x + consequence-x sums to viewBox width exactly
 *     - Control classes correctly encode side + kind
 */

'use strict';

const fs   = require('fs');
const path = require('path');
const vm   = require('vm');

// ── Paths ──────────────────────────────────────────────────────────────────
const COMPILER_DIR = path.resolve(__dirname, '..', '..');

// ── Envelope helper ────────────────────────────────────────────────────────
function envelope(spec, overrides) {
  return Object.assign({
    schema_version: '0.2',
    id: 'fig-bow-tie-test',
    type: 'bow_tie',
    mode_context: 'test_harness',
    relation_to_prose: 'integrated',
    spec: spec,
    semantic_description: {
      level_1_elemental:  'Bow-tie test fixture.',
      level_2_statistical: 'Synthetic structure.',
      level_3_perceptual:  'Symmetric layout.',
      level_4_contextual:  null,
      short_alt: 'Test bow-tie.',
      data_table_fallback: null,
    },
    title: 'Test bow-tie',
  }, overrides || {});
}

// ── Valid fixtures ─────────────────────────────────────────────────────────
const VALID = [
  {
    name: 'minimal-1t-1c-no-controls',
    env: envelope({
      hazard_event: { label: 'DB outage' },
      threats: [
        { id: 'T1', label: 'Disk failure', preventive_controls: [] },
      ],
      consequences: [
        { id: 'C1', label: 'Downtime', mitigative_controls: [] },
      ],
    }),
    expectThreats: 1,
    expectConseqs: 1,
    expectPrevControls: 0,
    expectMitControls: 0,
  },
  {
    name: 'multi-threat-multi-consequence',
    env: envelope({
      hazard_event: { label: 'Data breach' },
      threats: [
        { id: 'T1', label: 'Credential theft', preventive_controls: [
          { id: 'PC1', label: 'MFA', type: 'reduce' },
        ] },
        { id: 'T2', label: 'SQL injection', preventive_controls: [
          { id: 'PC2', label: 'Input validation', type: 'eliminate' },
        ] },
        { id: 'T3', label: 'Insider abuse', preventive_controls: [
          { id: 'PC3', label: 'Audit logging', type: 'detect' },
        ] },
      ],
      consequences: [
        { id: 'C1', label: 'PII exfil', mitigative_controls: [
          { id: 'MC1', label: 'DLP', type: 'contain' },
        ] },
        { id: 'C2', label: 'Reputational damage', mitigative_controls: [
          { id: 'MC2', label: 'PR response', type: 'reduce' },
        ] },
      ],
    }),
    expectThreats: 3,
    expectConseqs: 2,
    expectPrevControls: 3,
    expectMitControls: 2,
  },
  {
    name: 'full-preventive-enum',
    env: envelope({
      hazard_event: { label: 'Fire' },
      threats: [
        { id: 'T1', label: 'Ignition source', preventive_controls: [
          { id: 'PC1', label: 'Remove flammables', type: 'eliminate', effectiveness: 'H' },
          { id: 'PC2', label: 'Flame arrestor',   type: 'reduce',    effectiveness: 'M' },
          { id: 'PC3', label: 'Smoke detector',   type: 'detect',    effectiveness: 'H' },
        ] },
      ],
      consequences: [
        { id: 'C1', label: 'Property loss', mitigative_controls: [
          { id: 'MC1', label: 'Sprinklers', type: 'contain' },
        ] },
      ],
    }),
    expectThreats: 1,
    expectConseqs: 1,
    expectPrevControls: 3,
    expectMitControls: 1,
    expectPrevKinds: ['eliminate', 'reduce', 'detect'],
  },
  {
    name: 'full-mitigative-enum',
    env: envelope({
      hazard_event: { label: 'Chemical spill' },
      threats: [
        { id: 'T1', label: 'Valve failure', preventive_controls: [
          { id: 'PC1', label: 'Redundant valves', type: 'reduce' },
        ] },
      ],
      consequences: [
        { id: 'C1', label: 'Environmental release', mitigative_controls: [
          { id: 'MC1', label: 'Bund wall',      type: 'reduce',  effectiveness: 'H' },
          { id: 'MC2', label: 'Spill response', type: 'recover', effectiveness: 'M' },
          { id: 'MC3', label: 'Isolation',      type: 'contain', effectiveness: 'H' },
        ] },
      ],
    }),
    expectThreats: 1,
    expectConseqs: 1,
    expectPrevControls: 1,
    expectMitControls: 3,
    expectMitKinds: ['reduce', 'recover', 'contain'],
  },
  {
    name: 'asymmetric-2-threats-3-consequences',
    env: envelope({
      hazard_event: { label: 'Production outage' },
      threats: [
        { id: 'T1', label: 'Disk fail',    preventive_controls: [] },
        { id: 'T2', label: 'Network fail', preventive_controls: [] },
      ],
      consequences: [
        { id: 'C1', label: 'SLA breach',     mitigative_controls: [] },
        { id: 'C2', label: 'Support load',   mitigative_controls: [] },
        { id: 'C3', label: 'Revenue impact', mitigative_controls: [] },
      ],
    }),
    expectThreats: 2,
    expectConseqs: 3,
    expectPrevControls: 0,
    expectMitControls: 0,
  },
  {
    name: 'with-escalation-factors',
    env: envelope({
      hazard_event: { label: 'Cyber incident' },
      threats: [
        { id: 'T1', label: 'Phishing', preventive_controls: [
          { id: 'PC1', label: 'Email filter', type: 'detect' },
        ] },
      ],
      consequences: [
        { id: 'C1', label: 'Data loss', mitigative_controls: [
          { id: 'MC1', label: 'Backup', type: 'recover' },
        ] },
      ],
      escalation_factors: [
        { from_control_id: 'PC1',
          label: 'Filter bypassed by zero-day',
          escalation_control: { id: 'EC1', label: 'Threat intel feed' } },
        { from_control_id: 'MC1',
          label: 'Backup encryption key compromised' },
      ],
    }),
    expectThreats: 1,
    expectConseqs: 1,
    expectPrevControls: 1,
    expectMitControls: 1,
    expectEscalations: 2,
  },
];

// ── Invalid fixtures ───────────────────────────────────────────────────────
// Each one must be rejected with at least one E_SCHEMA_INVALID error by the
// renderer's defensive invariant check. The tests invoke the renderer
// directly (not the full compile() pipeline) to isolate renderer-level
// enforcement — the envelope-level schema also rejects these through Ajv,
// which we separately verify via test-envelope-invalid.js.
const INVALID = [
  {
    name: 'preventive-with-recover-type',
    note: "preventive control type='recover' — recover is mitigative-only",
    env: envelope({
      hazard_event: { label: 'Outage' },
      threats: [
        { id: 'T1', label: 'Threat', preventive_controls: [
          { id: 'PC1', label: 'Bad', type: 'recover' },
        ] },
      ],
      consequences: [
        { id: 'C1', label: 'Cons', mitigative_controls: [] },
      ],
    }),
    expectCode: 'E_SCHEMA_INVALID',
  },
  {
    name: 'mitigative-with-detect-type',
    note: "mitigative control type='detect' — detect is preventive-only",
    env: envelope({
      hazard_event: { label: 'Outage' },
      threats: [
        { id: 'T1', label: 'Threat', preventive_controls: [] },
      ],
      consequences: [
        { id: 'C1', label: 'Cons', mitigative_controls: [
          { id: 'MC1', label: 'Bad', type: 'detect' },
        ] },
      ],
    }),
    expectCode: 'E_SCHEMA_INVALID',
  },
  {
    name: 'zero-threats',
    note: 'threats array empty',
    env: envelope({
      hazard_event: { label: 'Outage' },
      threats: [],
      consequences: [
        { id: 'C1', label: 'Cons', mitigative_controls: [] },
      ],
    }),
    expectCode: 'E_SCHEMA_INVALID',
  },
  {
    name: 'zero-consequences',
    note: 'consequences array empty',
    env: envelope({
      hazard_event: { label: 'Outage' },
      threats: [
        { id: 'T1', label: 'Threat', preventive_controls: [] },
      ],
      consequences: [],
    }),
    expectCode: 'E_SCHEMA_INVALID',
  },
];

// ── Assertions on compiled SVG ─────────────────────────────────────────────
function assertStructuralSvg(svg) {
  if (!svg || svg.length === 0) return 'empty svg';
  const classMatch = svg.match(/<svg\b[^>]*\sclass="([^"]*)"/);
  if (!classMatch) return 'no class attribute on root <svg>';
  const classes = classMatch[1].split(/\s+/);
  if (classes.indexOf('ora-visual') === -1) return 'missing "ora-visual" class';
  if (classes.indexOf('ora-visual--bow_tie') === -1)
    return 'missing "ora-visual--bow_tie" class';
  if (!/<svg\b[^>]*\srole="img"/.test(svg)) return 'missing role="img"';
  const rootTag = svg.match(/<svg\b[^>]*>/)[0];
  const banned = ['style=', ' fill="', ' stroke="', 'font-family=', 'font-size='];
  for (const b of banned) {
    if (rootTag.indexOf(b) !== -1) return 'root <svg> still carries ' + b;
  }
  return null;
}

// Extract viewBox width from the SVG.
function viewBoxWidth(svg) {
  const m = svg.match(/viewBox="0 0 (\d+) (\d+)"/);
  return m ? parseInt(m[1], 10) : null;
}

// Extract all threat triangle centers (cx) from the SVG.
// Threat polygons use points of the form "baseX,topY tipX,cy baseX,botY".
// cx is derived from (tipX + baseX) / 2. We read the first polygon in each
// bt-threat-<i> group.
function threatCenters(svg) {
  const out = [];
  const re = /<g\s+id="bt-threat-(\d+)"[\s\S]*?<polygon[^>]*points="([^"]+)"/g;
  let m;
  while ((m = re.exec(svg)) !== null) {
    const pts = m[2].trim().split(/\s+/);
    // pts[0] = baseX,topY  pts[1] = tipX,cy  pts[2] = baseX,botY
    const baseX = parseFloat(pts[0].split(',')[0]);
    const tipX  = parseFloat(pts[1].split(',')[0]);
    const cy    = parseFloat(pts[1].split(',')[1]);
    out.push({ i: parseInt(m[1], 10), cx: (baseX + tipX) / 2, cy: cy });
  }
  return out;
}

function consequenceCenters(svg) {
  const out = [];
  const re = /<g\s+id="bt-consequence-(\d+)"[\s\S]*?<polygon[^>]*points="([^"]+)"/g;
  let m;
  while ((m = re.exec(svg)) !== null) {
    const pts = m[2].trim().split(/\s+/);
    const baseX = parseFloat(pts[0].split(',')[0]);
    const tipX  = parseFloat(pts[1].split(',')[0]);
    const cy    = parseFloat(pts[1].split(',')[1]);
    out.push({ i: parseInt(m[1], 10), cx: (baseX + tipX) / 2, cy: cy });
  }
  return out;
}

function countMatches(svg, re) {
  const m = svg.match(re);
  return m ? m.length : 0;
}

// ── Case runner ────────────────────────────────────────────────────────────
function runCases(win, record) {
  const OVC = win.OraVisualCompiler;

  // Confirm bow-tie renderer is registered.
  const isStub = OVC._dispatcher && OVC._dispatcher.isStub &&
    OVC._dispatcher.isStub('bow_tie');
  if (isStub) {
    record('bow_tie renderer registered', false,
      'bow_tie type is still on the stub — renderers/bow-tie.js did not load');
    return;
  }
  record('bow_tie renderer registered', true, 'real renderer active');

  // ── Valid cases ────────────────────────────────────────────────────────
  VALID.forEach((c) => {
    let result;
    try {
      result = OVC.compile(c.env);
    } catch (err) {
      record('valid: ' + c.name, false, 'compile threw: ' + (err.message || err));
      return;
    }

    // compile() is sync for bow-tie (hand-rolled SVG), no Promise handling.
    if (result && typeof result.then === 'function') {
      record('valid: ' + c.name, false,
        'compile returned a Promise — bow-tie should be synchronous');
      return;
    }

    const errs = result.errors || [];
    if (errs.length > 0) {
      record('valid: ' + c.name, false,
        'unexpected errors: ' + errs.map((e) => e.code + ':' + (e.message || '')).join('; '));
      return;
    }

    const svg = result.svg || '';
    const structErr = assertStructuralSvg(svg);
    if (structErr) {
      record('valid: ' + c.name + ' — structural', false, structErr);
      return;
    }
    record('valid: ' + c.name + ' — structural', true,
      'svg ' + svg.length + ' chars');

    // Stable IDs: event
    if (svg.indexOf('id="bt-event"') === -1) {
      record('valid: ' + c.name + ' — bt-event id', false, 'missing bt-event id');
    } else {
      record('valid: ' + c.name + ' — bt-event id', true, '');
    }

    // Stable IDs: threats
    let threatIdOk = true;
    for (let i = 0; i < c.expectThreats; i++) {
      if (svg.indexOf('id="bt-threat-' + i + '"') === -1) {
        threatIdOk = false;
        break;
      }
    }
    record('valid: ' + c.name + ' — threat IDs', threatIdOk,
      threatIdOk ? (c.expectThreats + ' threats') : 'threat id missing');

    // Stable IDs: consequences
    let consIdOk = true;
    for (let i = 0; i < c.expectConseqs; i++) {
      if (svg.indexOf('id="bt-consequence-' + i + '"') === -1) {
        consIdOk = false;
        break;
      }
    }
    record('valid: ' + c.name + ' — consequence IDs', consIdOk,
      consIdOk ? (c.expectConseqs + ' consequences') : 'consequence id missing');

    // Preventive control count + IDs + classes
    const prevCount = countMatches(svg, /id="bt-control-prev-\d+-\d+"/g);
    const prevClsCount = countMatches(svg,
      /ora-visual__bt-control--preventive/g);
    const prevOk = (prevCount === c.expectPrevControls) &&
      (prevClsCount >= c.expectPrevControls);
    record('valid: ' + c.name + ' — preventive controls', prevOk,
      'expected ' + c.expectPrevControls + ', found ' + prevCount +
      ' ids / ' + prevClsCount + ' side-cls');

    // Mitigative control count + IDs + classes
    const mitCount = countMatches(svg, /id="bt-control-mit-\d+-\d+"/g);
    const mitClsCount = countMatches(svg,
      /ora-visual__bt-control--mitigative/g);
    const mitOk = (mitCount === c.expectMitControls) &&
      (mitClsCount >= c.expectMitControls);
    record('valid: ' + c.name + ' — mitigative controls', mitOk,
      'expected ' + c.expectMitControls + ', found ' + mitCount +
      ' ids / ' + mitClsCount + ' side-cls');

    // Kind-specific class checks (when declared).
    if (c.expectPrevKinds) {
      let allKindsPresent = true;
      for (const k of c.expectPrevKinds) {
        if (svg.indexOf('ora-visual__bt-control--preventive-' + k) === -1) {
          allKindsPresent = false;
          break;
        }
      }
      record('valid: ' + c.name + ' — preventive kind classes',
        allKindsPresent,
        'all of ' + c.expectPrevKinds.join('/') + ' present');
    }
    if (c.expectMitKinds) {
      let allKindsPresent = true;
      for (const k of c.expectMitKinds) {
        if (svg.indexOf('ora-visual__bt-control--mitigative-' + k) === -1) {
          allKindsPresent = false;
          break;
        }
      }
      record('valid: ' + c.name + ' — mitigative kind classes',
        allKindsPresent,
        'all of ' + c.expectMitKinds.join('/') + ' present');
    }

    // Escalation checks.
    if (c.expectEscalations) {
      const escCount = countMatches(svg, /id="bt-escalation-\d+"/g);
      record('valid: ' + c.name + ' — escalations',
        escCount === c.expectEscalations,
        'expected ' + c.expectEscalations + ', found ' + escCount);
    }

    // Symmetry: every threat center must have x = 15% of viewBox width and
    // every consequence center must have x = 85% of viewBox width, so
    // threat_cx + consequence_cx === viewBox width exactly. Within each
    // side all cx values must be identical (column alignment on the pivot).
    const vbW = viewBoxWidth(svg);
    const threatC = threatCenters(svg);
    const consC   = consequenceCenters(svg);

    let symOk = true;
    let symDetail = '';
    if (vbW == null) {
      symOk = false; symDetail = 'no viewBox width parsed';
    } else if (threatC.length !== c.expectThreats) {
      symOk = false;
      symDetail = 'expected ' + c.expectThreats + ' threats, parsed ' + threatC.length;
    } else if (consC.length !== c.expectConseqs) {
      symOk = false;
      symDetail = 'expected ' + c.expectConseqs + ' consequences, parsed ' + consC.length;
    } else {
      // All threats on the same vertical line.
      const firstTx = threatC[0].cx;
      for (const t of threatC) {
        if (Math.abs(t.cx - firstTx) > 0.001) {
          symOk = false;
          symDetail = 'threat x-coords not aligned: ' +
            threatC.map((z) => z.cx).join(',');
          break;
        }
      }
      // All consequences on the same vertical line.
      if (symOk) {
        const firstCx = consC[0].cx;
        for (const cc of consC) {
          if (Math.abs(cc.cx - firstCx) > 0.001) {
            symOk = false;
            symDetail = 'consequence x-coords not aligned: ' +
              consC.map((z) => z.cx).join(',');
            break;
          }
        }
      }
      // Mirror around center: threat_cx + consequence_cx === viewBox width.
      if (symOk) {
        const sum = firstTx + consC[0].cx;
        if (Math.abs(sum - vbW) > 0.001) {
          symOk = false;
          symDetail = 'mirror asymmetric: threat_cx (' + firstTx +
            ') + cons_cx (' + consC[0].cx + ') = ' + sum +
            ', expected ' + vbW;
        }
      }
      // 15% / 85% location exactly (±1 px for integer rounding).
      if (symOk) {
        const expTx = Math.round(vbW * 0.15);
        const expCx = Math.round(vbW * 0.85);
        if (Math.abs(firstTx - expTx) > 1) {
          symOk = false;
          symDetail = 'threat x=' + firstTx + ' not ≈ 15% (' + expTx + ')';
        } else if (Math.abs(consC[0].cx - expCx) > 1) {
          symOk = false;
          symDetail = 'consequence x=' + consC[0].cx +
            ' not ≈ 85% (' + expCx + ')';
        }
      }
    }
    record('valid: ' + c.name + ' — symmetry', symOk,
      symOk ? ('threat_cx=' + threatC[0].cx + ', cons_cx=' + consC[0].cx +
        ', sum=' + (threatC[0].cx + consC[0].cx) + '=vbW')
        : symDetail);
  });

  // ── Invalid cases ──────────────────────────────────────────────────────
  // We invoke the bow-tie renderer directly so Ajv's envelope-level
  // checks don't pre-empt the renderer's defensive invariant checks.
  INVALID.forEach((c) => {
    const renderer = win.OraVisualCompiler._renderers &&
      win.OraVisualCompiler._renderers.bowTie;
    if (!renderer) {
      record('invalid: ' + c.name, false, 'bow-tie renderer not exposed');
      return;
    }

    let r;
    try {
      r = renderer.render(c.env);
    } catch (err) {
      record('invalid: ' + c.name, false,
        'renderer threw: ' + (err.message || err));
      return;
    }

    const errs = r.errors || [];
    const hasExpected = errs.some(
      (e) => e.code === c.expectCode);
    const emptySvg = !r.svg || r.svg.length === 0;
    const ok = hasExpected && emptySvg;
    record('invalid: ' + c.name, ok,
      ok
        ? ('rejected with ' + c.expectCode + ' — ' + c.note)
        : ('expected ' + c.expectCode + '; got ' +
            (errs.length ? errs.map((e) => e.code).join(',') : 'no errors') +
            (emptySvg ? '' : '; svg non-empty')));
  });
}

// ── jsdom bootstrap (shared by harness mode and standalone mode) ───────────
function bootstrapOwnJsdom() {
  const { JSDOM } = require('jsdom');
  const dom = new JSDOM(
    '<!doctype html><html><head></head><body></body></html>',
    { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
  );
  const { window } = dom;
  window.globalThis = window;
  window.console = console;
  const ctx = dom.getInternalVMContext();

  const read = (p) => fs.readFileSync(p, 'utf-8');

  const coreFiles = [
    path.join(COMPILER_DIR, 'errors.js'),
    path.join(COMPILER_DIR, 'validator.js'),
    path.join(COMPILER_DIR, 'renderers', 'stub.js'),
    path.join(COMPILER_DIR, 'dispatcher.js'),
    path.join(COMPILER_DIR, 'index.js'),
    path.join(COMPILER_DIR, 'renderers', 'bow-tie.js'),
  ];
  for (const f of coreFiles) {
    vm.runInContext(read(f), ctx, { filename: f });
  }

  return window;
}

// Lazy-load the bow-tie renderer into an already-bootstrapped ctx.win if
// it's still on the stub. Safe no-op if already registered.
function ensureBowTieRegistered(win) {
  if (!win.OraVisualCompiler) {
    throw new Error('harness ctx.win lacks OraVisualCompiler');
  }
  const isStub = win.OraVisualCompiler._dispatcher &&
    win.OraVisualCompiler._dispatcher.isStub &&
    win.OraVisualCompiler._dispatcher.isStub('bow_tie');
  if (!isStub) return;  // already registered

  const RENDERER = path.join(COMPILER_DIR, 'renderers', 'bow-tie.js');
  const src = fs.readFileSync(RENDERER, 'utf-8');
  // The harness uses win.eval; mirror that for consistency.
  if (typeof win.eval === 'function') {
    win.eval(src);
  } else {
    vm.runInContext(src, win, { filename: RENDERER });
  }
}

// ── Module exports ─────────────────────────────────────────────────────────
module.exports = {
  label: 'Bow-tie renderer — ≥5 valid + ≥3 invalid + symmetry checks',
  run: async function run(ctx, record) {
    try {
      ensureBowTieRegistered(ctx.win);
    } catch (err) {
      record('bow-tie renderer load', false, err.message || String(err));
      return;
    }
    runCases(ctx.win, record);
  },
  CASES: { VALID: VALID, INVALID: INVALID },
};

// ── Standalone execution ───────────────────────────────────────────────────
if (require.main === module) {
  (function main() {
    const results = [];
    function record(name, ok, detail) {
      results.push({ name: name, ok: !!ok, detail: detail || '' });
      const sigil = ok ? 'PASS' : 'FAIL';
      console.log('  ' + sigil + '  ' + name + (detail ? '  — ' + detail : ''));
    }

    console.log('Ora visual compiler — WP-1.3h bow-tie test suite (standalone)');
    let win;
    try {
      win = bootstrapOwnJsdom();
    } catch (err) {
      console.error('FATAL: jsdom bootstrap failed: ' + (err.message || err));
      process.exit(2);
    }

    runCases(win, record);

    const pass = results.filter((r) => r.ok).length;
    const fail = results.length - pass;
    console.log('\n=================================');
    console.log('Results: ' + pass + '/' + results.length +
      ' passed, ' + fail + ' failed.');
    if (fail > 0) {
      console.log('\nFailures:');
      for (const r of results) if (!r.ok) console.log('  - ' + r.name + ': ' + r.detail);
      process.exit(1);
    }
    process.exit(0);
  }());
}
