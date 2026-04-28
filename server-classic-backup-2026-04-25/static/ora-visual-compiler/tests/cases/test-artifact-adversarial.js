/**
 * tests/cases/test-artifact-adversarial.js — WP-2.5 regression suite.
 *
 * Exports { label, run(ctx, record) } following the run.js case-file
 * convention used by every other WP-1.x / WP-2.x test suite.
 *
 * Coverage (≥ 20 assertions):
 *   1. Module loaded and exposes review().
 *   2. Clean synthetic envelopes produce no findings.
 *   3. Synthetic overlap SVG → E_ARTIFACT_OVERLAP Critical.
 *   4. Synthetic minor-overlap SVG → W_ARTIFACT_OVERLAP_MINOR warning.
 *   5. Synthetic long-label SVG → W_ARTIFACT_TEXT_TRUNCATED.
 *   6. Primary-label truncation beyond 1.5× → Critical severity.
 *   7. Low-contrast injected SVG → E_ARTIFACT_CONTRAST.
 *   8. Graphical below-3:1 contrast → W_ARTIFACT_CONTRAST_GRAPHICAL.
 *   9. blocks semantics: any Critical → blocks=true; warnings-only → false.
 *  10. WCAG formula numbers (black vs white = 21:1; identical colors = 1:1).
 *  11. Nesting pair skip (quadrant contains items).
 *  12. Parent/child DOM pair skip.
 *  13. Empty/malformed SVG → no findings, no throw.
 *  14. Integration: compile() with overlap-prone synthetic → svg='' +
 *      errors contain E_ARTIFACT_OVERLAP.
 *  15. Baseline regression — every examples/*.valid.json envelope passes
 *      through compile() without any Critical artifact findings.
 *  16. Per-renderer smoke tests: CLD, quadrant_matrix, pro_con, fishbone
 *      produce output that passes adversarial review.
 *  17. Path bbox estimator correctness on a known d-attribute.
 *  18. Backward compatibility: when artifactAdversarial is deleted,
 *      compile() returns SVG unchanged.
 */

'use strict';

const fs   = require('fs');
const path = require('path');

// Shared jsdom-compile skip (Mermaid flowchart routing needs real SVG layout).
const JSDOM_FLOWCHART_SKIP = new Set(['flowchart.valid.json']);

// Build a tiny wrapped SVG with two groups that overlap massively (same
// position, same size). Used for the critical-overlap unit test.
function overlapSvg() {
  return (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400">' +
      '<g id="n1" class="ora-visual__node">' +
        '<rect x="100" y="100" width="80" height="40"/>' +
        '<text x="140" y="122" text-anchor="middle">Alpha</text>' +
      '</g>' +
      '<g id="n2" class="ora-visual__node">' +
        '<rect x="110" y="110" width="80" height="40"/>' +
        '<text x="150" y="132" text-anchor="middle">Beta</text>' +
      '</g>' +
    '</svg>'
  );
}

// Two rectangles touching along one edge — overlap = 0 (they share a line,
// area = 0). Slightly overlapped → should still exceed 5%.
function minorOverlapSvg() {
  return (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400">' +
      '<g id="n1" class="ora-visual__node">' +
        '<rect x="100" y="100" width="100" height="100"/>' +
      '</g>' +
      '<g id="n2" class="ora-visual__node">' +
        // Overlap: x 198..200 × y 100..200 = 2 × 100 = 200 px²;
        // smaller area = 100*100 = 10000; ratio = 0.02 (2%) → minor.
        '<rect x="198" y="100" width="100" height="100"/>' +
      '</g>' +
    '</svg>'
  );
}

// A single node group whose text label is much longer than its bbox
// width allows — expect W_ARTIFACT_TEXT_TRUNCATED.
function truncatedSvg() {
  return (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400">' +
      '<g id="n1" class="ora-visual__node">' +
        '<rect x="50" y="50" width="60" height="30"/>' +
        '<text x="80" y="70" text-anchor="middle" class="ora-visual__node-label">' +
          'This is a very long label that will not fit in the 60px container at all' +
        '</text>' +
      '</g>' +
    '</svg>'
  );
}

// A clean layout with no overlaps — baseline.
function cleanSvg() {
  return (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 200">' +
      '<g id="n1" class="ora-visual__node">' +
        '<rect x="50"  y="80" width="80" height="40"/>' +
        '<text x="90"  y="104" text-anchor="middle">A</text>' +
      '</g>' +
      '<g id="n2" class="ora-visual__node">' +
        '<rect x="250" y="80" width="80" height="40"/>' +
        '<text x="290" y="104" text-anchor="middle">B</text>' +
      '</g>' +
      '<g id="n3" class="ora-visual__node">' +
        '<rect x="450" y="80" width="80" height="40"/>' +
        '<text x="490" y="104" text-anchor="middle">C</text>' +
      '</g>' +
    '</svg>'
  );
}

// Force low-contrast text: fill "#aaa" on white bg (~2.3:1 against #fdfbf7).
function lowContrastTextSvg() {
  return (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100">' +
      '<g id="n1" class="ora-visual__node">' +
        '<rect x="50" y="20" width="100" height="60"/>' +
        '<text x="100" y="55" text-anchor="middle" fill="#bbbbbb">Low</text>' +
      '</g>' +
    '</svg>'
  );
}

// Force low-contrast graphical object: stroke "#ddd" on white bg (< 3:1).
function lowContrastGraphicalSvg() {
  return (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100">' +
      '<g id="n1" class="ora-visual__node">' +
        '<rect x="50" y="20" width="100" height="60" stroke="#eeeeee" fill="none"/>' +
      '</g>' +
    '</svg>'
  );
}

// Build an envelope that will dispatch to the CLD renderer and produce a
// reasonable artifact. The example test file uses this shape.
function cldEnvelope(id) {
  return {
    schema_version: '0.2',
    id: id || 'fig-test-adv',
    type: 'causal_loop_diagram',
    mode_context: 'root_cause_analysis',
    relation_to_prose: 'integrated',
    spec: {
      variables: [
        { id: 'A', label: 'Alpha' },
        { id: 'B', label: 'Beta'  },
        { id: 'C', label: 'Gamma' },
      ],
      links: [
        { from: 'A', to: 'B', polarity: '+' },
        { from: 'B', to: 'C', polarity: '+' },
        { from: 'C', to: 'A', polarity: '-' },
      ],
      loops: [ { id: 'B1', type: 'B', members: ['A', 'B', 'C'], label: 'Loop' } ],
    },
    semantic_description: {
      level_1_elemental:   'A CLD with three variables and one balancing loop.',
      level_2_statistical: 'Three edges; one negative; one loop.',
      level_3_perceptual:  'Triangle.',
      level_4_contextual:  null,
      short_alt:           'Balancing loop between three variables.',
      data_table_fallback: null,
    },
    title: 'Adversarial test CLD',
  };
}

// ── Case-file export ────────────────────────────────────────────────────
module.exports = {
  label: 'Artifact-level adversarial review (WP-2.5)',
  run: async function run(ctx, record) {
    const { win, EXAMPLES_DIR } = ctx;
    const adv = win.OraVisualCompiler.artifactAdversarial;

    // ── 1. Module presence ───────────────────────────────────────────
    record('module loaded',
      !!(adv && typeof adv.review === 'function'),
      adv ? 'review() present' : 'missing');

    if (!adv) return;

    // ── 2. Clean SVG → no findings ───────────────────────────────────
    {
      const r = adv.review(cleanSvg(), { id: 'fig-clean' });
      const ok = Array.isArray(r.findings) && r.findings.length === 0 && r.blocks === false;
      record('clean SVG → zero findings, blocks=false', ok,
        'findings=' + (r.findings && r.findings.length) + ' blocks=' + r.blocks);
    }

    // ── 3. Overlap SVG → critical ────────────────────────────────────
    {
      const r = adv.review(overlapSvg(), { id: 'fig-overlap' });
      const hasCritical = r.findings.some(f =>
        f.code === 'E_ARTIFACT_OVERLAP' && f.severity === 'error');
      record('overlapping bboxes → E_ARTIFACT_OVERLAP Critical',
        hasCritical && r.blocks === true,
        'blocks=' + r.blocks + ' codes=' + r.findings.map(f => f.code).join(','));
    }

    // ── 4. Minor overlap SVG → warning only ──────────────────────────
    {
      const r = adv.review(minorOverlapSvg(), { id: 'fig-minor' });
      const hasMinor = r.findings.some(f =>
        f.code === 'W_ARTIFACT_OVERLAP_MINOR' && f.severity === 'warning');
      const noCritical = !r.findings.some(f => f.severity === 'error');
      record('minor overlap → W_ARTIFACT_OVERLAP_MINOR (no block)',
        hasMinor && noCritical && r.blocks === false,
        'blocks=' + r.blocks + ' codes=' + r.findings.map(f => f.code).join(','));
    }

    // ── 5. Long label SVG → truncation warning ───────────────────────
    {
      const r = adv.review(truncatedSvg(), { id: 'fig-trunc' });
      const hasTrunc = r.findings.some(f => f.code === 'W_ARTIFACT_TEXT_TRUNCATED');
      record('long label → W_ARTIFACT_TEXT_TRUNCATED',
        hasTrunc,
        'codes=' + r.findings.map(f => f.code).join(','));
    }

    // ── 6. Primary-label truncated beyond 1.5× → Critical ────────────
    {
      // 77 chars × 6.5 = ~500px vs 60px container = 8.3× → Critical.
      const r = adv.review(truncatedSvg(), { id: 'fig-trunc-crit' });
      const crit = r.findings.find(f =>
        f.code === 'W_ARTIFACT_TEXT_TRUNCATED' && f.severity === 'error');
      record('primary label truncated > 1.5× → severity=error, blocks=true',
        !!crit && r.blocks === true,
        crit ? 'found crit trunc' : 'no crit trunc');
    }

    // ── 7. Low-contrast text → Critical ──────────────────────────────
    {
      const r = adv.review(lowContrastTextSvg(), { id: 'fig-contrast-t' });
      const hasContrast = r.findings.some(f =>
        f.code === 'E_ARTIFACT_CONTRAST' && f.severity === 'error');
      record('low-contrast text → E_ARTIFACT_CONTRAST Critical',
        hasContrast && r.blocks === true,
        'codes=' + r.findings.map(f => f.code).join(','));
    }

    // ── 8. Low-contrast graphical object → warning ───────────────────
    {
      const r = adv.review(lowContrastGraphicalSvg(), { id: 'fig-contrast-g' });
      const hasGraph = r.findings.some(f => f.code === 'W_ARTIFACT_CONTRAST_GRAPHICAL');
      record('low-contrast stroke → W_ARTIFACT_CONTRAST_GRAPHICAL warning',
        hasGraph,
        'codes=' + r.findings.map(f => f.code).join(','));
    }

    // ── 9. blocks semantics ──────────────────────────────────────────
    {
      const clean = adv.review(cleanSvg(), { id: 'fig-clean-2' });
      const dirty = adv.review(overlapSvg(), { id: 'fig-dirty' });
      record('blocks=false when no Critical findings',
        clean.blocks === false, 'blocks=' + clean.blocks);
      record('blocks=true when any Critical finding',
        dirty.blocks === true, 'blocks=' + dirty.blocks);
    }

    // ── 10. WCAG formula numeric sanity ──────────────────────────────
    {
      const white = { r: 255, g: 255, b: 255 };
      const black = { r: 0,   g: 0,   b: 0   };
      const r1 = adv._contrast(black, white);
      const r2 = adv._contrast(white, white);
      record('WCAG contrast: black vs white ≈ 21:1',
        Math.abs(r1 - 21.0) < 0.01, 'ratio=' + r1.toFixed(2));
      record('WCAG contrast: identical colors = 1:1',
        Math.abs(r2 - 1.0) < 0.001, 'ratio=' + r2.toFixed(4));
    }

    // ── 11. Nesting pair skip (quadrant + item) ──────────────────────
    {
      // quadrant-TL fully contains a quadrant-item — no findings expected.
      const svg =
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400">' +
          '<g id="q-TL" class="ora-visual__quadrant">' +
            '<rect x="0" y="0" width="200" height="200"/>' +
          '</g>' +
          '<g id="q-item-1" class="ora-visual__item">' +
            '<circle cx="50" cy="50" r="10"/>' +
            '<text x="50" y="50" text-anchor="middle">X</text>' +
          '</g>' +
        '</svg>';
      const r = adv.review(svg, { id: 'fig-nest' });
      const noOverlap = !r.findings.some(f => f.code === 'E_ARTIFACT_OVERLAP');
      record('quadrant+item nesting → not flagged as overlap',
        noOverlap,
        'codes=' + r.findings.map(f => f.code).join(','));
    }

    // ── 12. Parent/child DOM pair skipped ────────────────────────────
    {
      // Outer node wrapper contains inner cell; they're parent/child so
      // they must NOT trigger overlap.
      const svg =
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400">' +
          '<g id="outer" class="ora-visual__node">' +
            '<rect x="0" y="0" width="200" height="200"/>' +
            '<g id="inner" class="ora-visual__cell">' +
              '<rect x="50" y="50" width="80" height="80"/>' +
            '</g>' +
          '</g>' +
        '</svg>';
      const r = adv.review(svg, { id: 'fig-pchild' });
      const noOverlap = !r.findings.some(f => f.code === 'E_ARTIFACT_OVERLAP');
      record('parent/child DOM pair → not flagged as overlap',
        noOverlap,
        'codes=' + r.findings.map(f => f.code).join(','));
    }

    // ── 13. Empty / malformed → no throw, no findings ────────────────
    {
      let threw = null;
      try {
        const r1 = adv.review('', {});
        const r2 = adv.review(null, {});
        const r3 = adv.review('<not really svg', {});
        record('empty svg → 0 findings', r1.findings.length === 0, '');
        record('null svg → 0 findings', r2.findings.length === 0, '');
        record('malformed svg → 0 findings', r3.findings.length === 0, '');
      } catch (e) { threw = e; }
      record('no throw on degenerate input',
        threw === null, threw ? String(threw) : '');
    }

    // ── 14. Integration: compile() with overlap-prone envelope ───────
    // We post-hack the SVG here by synthesizing an envelope whose renderer
    // will emit overlapping groups. Simplest path: create a CLD with two
    // variables that collapse onto the same force-layout point — but force
    // simulations avoid that. So instead: use our synthetic SVG + run it
    // through the compile pipeline artifact stage indirectly by calling
    // _applyArtifactAdversarial via compile(). Easier: assert blocking
    // behavior via an artifactAdversarial.review on real compile output
    // after manual SVG manipulation. We craft a pathological dispatch:
    // substitute a renderer that returns the overlap svg.
    {
      const C = win.OraVisualCompiler;
      const origDispatcher = C._dispatcher;
      // Register a temporary "bad" renderer on an unused type by registering
      // directly via internal _dispatcher.register (idempotent for this
      // test-only slot).
      const TEST_TYPE = '__adv_test_overlap__';
      const badRenderer = {
        render: function () {
          return { svg: overlapSvg(), errors: [], warnings: [] };
        },
      };
      try {
        C._dispatcher.register(TEST_TYPE, badRenderer);
        // Also teach validator about this synthetic type so structural
        // validation doesn't reject it. We do so by adding it to the
        // KNOWN_TYPES set used by validator.
        C.KNOWN_TYPES && C.KNOWN_TYPES.add && C.KNOWN_TYPES.add(TEST_TYPE);

        const env = {
          schema_version: '0.2',
          id: 'fig-adv-compile',
          type: TEST_TYPE,
          spec: { sentinel: true },
          mode_context: 'test',
          relation_to_prose: 'integrated',
          semantic_description: {
            level_1_elemental:   'Test',
            level_2_statistical: 'Test',
            level_3_perceptual:  'Test',
            level_4_contextual:  null,
            short_alt:           'Test',
            data_table_fallback: null,
          },
          title: 'Test',
        };

        // Temporarily mark _ajvReady=false so full Ajv validation (which
        // would reject the synthetic type) is bypassed in favor of
        // structural validation against KNOWN_TYPES.
        const savedAjv = C._ajvReady;
        C._ajvReady = false;

        let result = C.compile(env);
        if (result && typeof result.then === 'function') result = await result;
        const svgEmpty = (result.svg === '');
        const hasCritical = (result.errors || []).some(e =>
          e.code === 'E_ARTIFACT_OVERLAP' && e.severity === 'error');
        record('compile(): overlap-prone synthetic → svg="" + E_ARTIFACT_OVERLAP',
          svgEmpty && hasCritical,
          'svg.len=' + (result.svg || '').length +
          ' codes=' + (result.errors || []).map(e => e.code).join(','));

        C._ajvReady = savedAjv;
      } finally {
        // Restore: delete temp renderer from the registry. (No public
        // unregister; delete the property directly.)
        try { delete C._dispatcher._registry[TEST_TYPE]; } catch (e) {}
        C.KNOWN_TYPES && C.KNOWN_TYPES.delete && C.KNOWN_TYPES.delete(TEST_TYPE);
      }
    }

    // ── 15. Baseline regression — real envelopes must not trigger any
    //        Critical artifact findings. Warning-level findings are OK.
    {
      const files = fs.readdirSync(EXAMPLES_DIR)
        .filter(f => f.endsWith('.valid.json')).sort();
      let criticals = 0;
      const offenders = [];
      for (const f of files) {
        if (JSDOM_FLOWCHART_SKIP.has(f)) continue;
        const env = JSON.parse(fs.readFileSync(path.join(EXAMPLES_DIR, f), 'utf-8'));
        let result = win.OraVisualCompiler.compile(env);
        if (result && typeof result.then === 'function') result = await result;
        const advErrors = (result.errors || []).filter(e =>
          e.code && (e.code.indexOf('ARTIFACT') >= 0));
        if (advErrors.length > 0) {
          criticals += advErrors.length;
          offenders.push(f + '=' + advErrors.map(e => e.code).join(','));
        }
      }
      record('baseline: every valid example compiles with 0 artifact errors',
        criticals === 0,
        criticals === 0 ? ('scanned ' + files.length + ' envelopes')
                        : ('offenders=' + offenders.join('; ')));
    }

    // ── 16. Per-renderer smoke tests (4 representatives) ─────────────
    {
      const types = [
        'causal_loop_diagram.valid.json',
        'quadrant_matrix.valid.json',
        'pro_con.valid.json',
        'fishbone.valid.json',
      ];
      for (const f of types) {
        const env = JSON.parse(fs.readFileSync(path.join(EXAMPLES_DIR, f), 'utf-8'));
        let result = win.OraVisualCompiler.compile(env);
        if (result && typeof result.then === 'function') result = await result;
        const nonEmpty = (result.svg || '').length > 0;
        const advErrs = (result.errors || []).filter(e =>
          e.code && e.code.indexOf('ARTIFACT') >= 0);
        record('smoke:' + f + ' compile + adversarial clean',
          nonEmpty && advErrs.length === 0,
          'svg.len=' + (result.svg || '').length +
          ' advErrs=' + advErrs.map(e => e.code).join(','));
      }
    }

    // ── 17. Path bbox estimator correctness ──────────────────────────
    {
      // A path with known extent "M 10,20 L 40,50 L 10,50 Z".
      // Min x=10, max x=40; min y=20, max y=50.
      const b = adv._pathBBox('M 10,20 L 40,50 L 10,50 Z');
      const ok = b && Math.abs(b.x - 10) < 0.001 && Math.abs(b.y - 20) < 0.001 &&
                 Math.abs(b.width - 30) < 0.001 && Math.abs(b.height - 30) < 0.001;
      record('_pathBBox handles simple absolute path', ok,
        b ? ('x=' + b.x + ' y=' + b.y + ' w=' + b.width + ' h=' + b.height) : 'null');
    }

    // ── 18. Backward compatibility: compile() without the reviewer ───
    {
      const C = win.OraVisualCompiler;
      const saved = C.artifactAdversarial;
      C.artifactAdversarial = undefined;
      try {
        const env = cldEnvelope('fig-adv-backcompat');
        let r = C.compile(env);
        if (r && typeof r.then === 'function') r = await r;
        // With reviewer absent, compile() should behave as before
        // (non-empty svg, no ARTIFACT findings on errors/warnings).
        const svgOk = (r.svg || '').length > 0;
        const noArt = !(r.errors || []).some(e =>
          e.code && e.code.indexOf('ARTIFACT') >= 0) &&
          !(r.warnings || []).some(e =>
          e.code && e.code.indexOf('ARTIFACT') >= 0);
        record('compile() without artifactAdversarial → unchanged behavior',
          svgOk && noArt,
          'svg.len=' + (r.svg || '').length);
      } finally {
        C.artifactAdversarial = saved;
      }
    }

    // ── 19. Additional unit: _parseTransform / _intersectArea ────────
    {
      const t = adv._parseTransform('translate(10,20) scale(2)');
      record('_parseTransform: translate + scale',
        t.tx === 10 && t.ty === 20 && t.scale === 2,
        'tx=' + t.tx + ' ty=' + t.ty + ' s=' + t.scale);

      const iA = adv._intersectArea(
        { x: 0, y: 0, width: 10, height: 10 },
        { x: 5, y: 5, width: 10, height: 10 });
      record('_intersectArea: 10×10 boxes offset (5,5) → 25 px²',
        iA === 25,
        'got ' + iA);

      const iB = adv._intersectArea(
        { x: 0, y: 0, width: 10, height: 10 },
        { x: 50, y: 50, width: 10, height: 10 });
      record('_intersectArea: disjoint → 0',
        iB === 0,
        'got ' + iB);
    }

    // ── 20. Color parser sanity ──────────────────────────────────────
    {
      const a = adv._parseColor('#abc');       // 3-char shorthand
      const b = adv._parseColor('rgb(1,2,3)');
      const c = adv._parseColor('rgba(0,0,0,0)'); // transparent → null
      const d = adv._parseColor('none');          // none → null
      record('_parseColor: #abc → aabbcc rgb',
        a && a.r === 170 && a.g === 187 && a.b === 204,
        JSON.stringify(a));
      record('_parseColor: rgb(1,2,3)',
        b && b.r === 1 && b.g === 2 && b.b === 3, JSON.stringify(b));
      record('_parseColor: rgba alpha=0 → null', c === null, JSON.stringify(c));
      record('_parseColor: "none" → null', d === null, JSON.stringify(d));
    }
  },
};
