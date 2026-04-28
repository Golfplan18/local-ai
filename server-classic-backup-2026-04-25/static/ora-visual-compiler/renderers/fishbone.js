/**
 * ora-visual-compiler / renderers/fishbone.js
 *
 * WP-1.3c — Fishbone / Ishikawa renderer (CAUSAL family).
 *
 * Hand-rolled, deterministic, synchronous SVG emitter. No external library.
 * Classic herringbone layout: horizontal spine → effect box on the right →
 * category branches at a fixed diagonal off the spine → sub-causes as short
 * horizontal stubs off each branch.
 *
 * Load order:
 *   errors.js → validator.js → renderers/stub.js → dispatcher.js → index.js →
 *   palettes.js → renderers/fishbone.js
 *
 * Contract (WP-1.1):
 *   render(envelope) → { svg, errors, warnings }
 *   Synchronous. Never throws. All failure modes convert to structured errors.
 *
 * Error/warning codes used (from errors.js):
 *   E_NO_SPEC
 *   E_SCHEMA_INVALID   (depth > 3, non-canonical framework category)
 *   E_RENDERER_THREW   (defensive; should not fire under normal input)
 *   W_EFFECT_SOLUTION_PHRASED  (soft lint: effect phrased as a solution)
 *
 * Semantic IDs (Phase 5 annotation targets):
 *   id="fb-effect"                         — effect box wrapper
 *   id="fb-category-<slug>"                — category group
 *   id="fb-cause-<cat-slug>-<path>"        — per-cause group; <path> is a
 *                                            dot-joined 1-based index chain
 *                                            from top of the category.
 *
 * Layout angle: category branches rise/fall at a FIXED 30° off the spine
 * (alternating above/below). Chosen over 60° because sub-cause stubs are
 * drawn horizontally and 30° gives the horizontal stubs a natural, wide
 * comb against the spine without crowding. See _BRANCH_ANGLE_DEG.
 *
 * Classes emitted (semantic CSS, zero inline styles):
 *   ora-visual                              — root <svg>
 *   ora-visual--fishbone                    — root modifier
 *   ora-visual__spine                       — spine line (legacy-compatible)
 *   ora-visual__fb-spine                    — spine line (canonical)
 *   ora-visual__fb-effect                   — effect group
 *   ora-visual__fb-category                 — category group
 *   ora-visual__fb-category-label           — category label wrapper
 *   ora-visual__fb-category--cat-<n>        — per-category palette class (1..N)
 *   ora-visual__fb-cause                    — sub-cause group
 *   ora-visual__fb-cause--depth-<d>         — depth modifier on a sub-cause (1..3)
 *
 * Depends on: errors.js, palettes.js (optional; graceful degradation)
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};
window.OraVisualCompiler._renderers = window.OraVisualCompiler._renderers || {};

window.OraVisualCompiler._renderers.fishbone = (function () {

  const { CODES, make } = window.OraVisualCompiler.errors;

  // ────────────────────────────────────────────────────────────────────────
  // Framework canonical sets (Protocol §3.6)
  //
  // Ambiguities resolved on-spec:
  //   - 6M sixth category: accept either "Milieu" OR "Environment"
  //     (Milieu is historically the 6th M in Ishikawa 1968; "Environment"
  //     is the common English gloss). Both canonical.
  //   - Case-insensitive matching: user may write "machine" or "MACHINE".
  //   - Hyphenation/whitespace normalization is NOT applied: "Physical
  //     Evidence" must be exactly two words separated by a single space
  //     (case-insensitive). This matches the canonical 8P list used in
  //     textbooks.
  // ────────────────────────────────────────────────────────────────────────
  const FRAMEWORK_CATEGORIES = {
    '6M': ['Man', 'Machine', 'Method', 'Material', 'Measurement', 'Milieu', 'Environment'],
    '4P': ['People', 'Process', 'Policy', 'Place'],
    '4S': ['Suppliers', 'Systems', 'Skills', 'Surroundings'],
    '8P': ['Product', 'Price', 'Place', 'Promotion', 'People', 'Process',
           'Physical Evidence', 'Performance'],
    'custom': null,
  };

  // Keywords that strongly suggest a phrase describes a *problem* (good)
  // rather than a *solution*. Presence of any of these makes the lint pass.
  // Case-insensitive substring match against the effect string.
  const PROBLEM_HINTS = [
    'too', 'not', 'low', 'high', 'slow', 'fail', 'unable', 'broken',
    'missing', 'late', 'insufficient', 'inadequate', 'over', 'under',
    'cannot', 'can\'t', 'won\'t', 'doesn\'t', 'does not', 'do not',
    'lack', 'poor', 'excess', 'drop', 'decline', 'error', 'defect',
    'shortage', 'delay', 'gap', 'loss',
  ];

  // Phrase-initial verbs that strongly suggest the effect is SOLUTION-phrased
  // ("Improve throughput", "Reduce cost"). First word, case-insensitive.
  const SOLUTION_LEAD_VERBS = [
    'improve', 'increase', 'reduce', 'decrease', 'optimize', 'optimise',
    'enhance', 'fix', 'resolve', 'implement', 'build', 'add', 'deploy',
    'introduce', 'establish', 'launch', 'streamline', 'refactor',
  ];

  // ── Geometry constants ─────────────────────────────────────────────────
  const VIEW_W  = 960;
  const VIEW_H  = 540;
  const PAD_X   = 40;
  const PAD_Y   = 40;
  const SPINE_Y = VIEW_H / 2;

  const SPINE_X0 = PAD_X + 120;                  // leave room for a possible left pad note
  const EFFECT_W = 180;
  const EFFECT_H = 70;
  const SPINE_X1 = VIEW_W - PAD_X - EFFECT_W;    // spine meets the effect box

  const CATEGORY_BOX_W = 130;
  const CATEGORY_BOX_H = 28;

  const _BRANCH_ANGLE_DEG     = 30;              // chosen: 30° off the spine
  const BRANCH_BASE_LEN       = 110;             // base diagonal length
  const BRANCH_PER_CAUSE      = 28;              // extra length per extra cause
  const SUB_CAUSE_STUB        = 90;              // horizontal stub length
  const SUB_CAUSE_MIN_GAP     = 22;              // min spacing along the branch

  // ────────────────────────────────────────────────────────────────────────
  // Small helpers
  // ────────────────────────────────────────────────────────────────────────
  function _esc(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function _slug(str) {
    return String(str || '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'x';
  }

  // Depth of a cause tree. A cause with no sub_causes has depth 1.
  function _causeDepth(cause) {
    if (!cause || !Array.isArray(cause.sub_causes) || cause.sub_causes.length === 0) {
      return 1;
    }
    let max = 0;
    for (const sc of cause.sub_causes) {
      const d = _causeDepth(sc);
      if (d > max) max = d;
    }
    return 1 + max;
  }

  // Find first path (JSON-path style) where depth exceeds `limit`. Returns
  // null if within limit. Used for path-accurate E_SCHEMA_INVALID messages.
  function _findTooDeep(causes, limit, pathPrefix, currentDepth) {
    if (!Array.isArray(causes)) return null;
    for (let i = 0; i < causes.length; i++) {
      const c = causes[i];
      const depth = currentDepth + 1;           // this cause occupies this depth
      const p = pathPrefix + '[' + i + ']';
      if (depth > limit) return p;
      if (c && Array.isArray(c.sub_causes)) {
        const inner = _findTooDeep(c.sub_causes, limit, p + '.sub_causes', depth);
        if (inner) return inner;
      }
    }
    return null;
  }

  // Count total causes in a category subtree (flat).
  function _flatCauseCount(causes) {
    if (!Array.isArray(causes)) return 0;
    let n = causes.length;
    for (const c of causes) {
      if (c && Array.isArray(c.sub_causes)) n += _flatCauseCount(c.sub_causes);
    }
    return n;
  }

  // ────────────────────────────────────────────────────────────────────────
  // Framework validation
  // ────────────────────────────────────────────────────────────────────────
  function _validateFramework(spec, errors) {
    const fw = spec.framework;
    if (fw === 'custom') return;

    const canonical = FRAMEWORK_CATEGORIES[fw];
    if (!canonical) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'fishbone: framework ' + JSON.stringify(fw) +
        ' is not a recognised value. Expected one of: 6M, 4P, 4S, 8P, custom.',
        'spec.framework'));
      return;
    }
    const canonicalLower = canonical.map((c) => c.toLowerCase());

    const cats = Array.isArray(spec.categories) ? spec.categories : [];
    for (let i = 0; i < cats.length; i++) {
      const name = cats[i] && cats[i].name;
      if (typeof name !== 'string') continue;           // schema layer will catch
      if (canonicalLower.indexOf(name.toLowerCase()) < 0) {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'fishbone: category ' + JSON.stringify(name) +
          ' is not in the canonical set for framework ' + fw +
          '. Allowed names: ' + canonical.join(', ') + '.',
          'spec.categories[' + i + '].name'));
      }
    }
  }

  // ────────────────────────────────────────────────────────────────────────
  // Effect-phrasing soft lint
  // ────────────────────────────────────────────────────────────────────────
  function _lintEffect(effect, warnings) {
    if (typeof effect !== 'string' || effect.length === 0) return;
    const trimmed = effect.trim();
    const lower = trimmed.toLowerCase();

    // Tagged as a problem? "(problem)" hint.
    if (/\bproblem\b|\bissue\b|\bdefect\b/.test(lower)) return;

    // Ends with a question mark — phrased as a diagnostic question.
    if (/[?]\s*$/.test(trimmed)) return;

    // Contains a problem-hint keyword? Treat as problem-phrased.
    for (const kw of PROBLEM_HINTS) {
      // Use word-boundary-ish check for whole tokens where possible.
      if (lower.indexOf(kw) >= 0) return;
    }

    // Starts with a solution-lead verb? Emit the warning.
    const firstWord = (lower.match(/^[a-z']+/) || [''])[0];
    if (SOLUTION_LEAD_VERBS.indexOf(firstWord) >= 0) {
      warnings.push(make(CODES.W_EFFECT_SOLUTION_PHRASED,
        'fishbone: effect ' + JSON.stringify(trimmed) +
        ' appears solution-phrased (leads with ' + JSON.stringify(firstWord) +
        '). Ishikawa technique: state the PROBLEM being analysed, not the fix.',
        'spec.effect'));
    }
  }

  // ────────────────────────────────────────────────────────────────────────
  // Layout
  // ────────────────────────────────────────────────────────────────────────
  // For N categories, alternate above/below. We drop spine attach points
  // evenly between SPINE_X0 and SPINE_X1 with a small margin from the effect.
  //
  // Branch direction convention:
  //   Above branches go UP-LEFT from the spine (angle = -30° from spine,
  //   measured as elevation toward the top-left). Below branches go
  //   DOWN-LEFT from the spine.
  //   i.e. branch endpoint is to the left of the attach point. This keeps
  //   the "fish swimming right" feel (effect on the right, branches point
  //   back away from it).
  function _layoutCategories(categories) {
    const n = categories.length;
    if (n === 0) return [];

    const angle = _BRANCH_ANGLE_DEG * Math.PI / 180;
    const cosA = Math.cos(angle);
    const sinA = Math.sin(angle);

    // Distribute attach points along the spine. Reserve ~10% on the left
    // (near SPINE_X0) and stop ~12% short of SPINE_X1 so the last branch
    // never overlaps the effect box.
    const spineStart = SPINE_X0 + 30;
    const spineEnd   = SPINE_X1 - 30;
    const spineSpan  = spineEnd - spineStart;
    const step       = n === 1 ? 0 : spineSpan / (n - 1);

    const out = [];
    for (let i = 0; i < n; i++) {
      const cat = categories[i];
      const above = (i % 2 === 0);
      const attachX = spineStart + step * i;
      const attachY = SPINE_Y;

      const flatCount = _flatCauseCount(cat.causes || []);
      const subs = Array.isArray(cat.causes) ? cat.causes.length : 0;
      const branchLen = BRANCH_BASE_LEN + BRANCH_PER_CAUSE * Math.max(0, subs - 1);

      // Unit vector pointing away from the effect (i.e. to the upper-left
      // for above, lower-left for below).
      const ux = -cosA;
      const uy = above ? -sinA : sinA;

      const endX = attachX + ux * branchLen;
      const endY = attachY + uy * branchLen;

      // Label box placed at the far end of the branch. The label rect sits
      // beyond the endpoint so the branch line doesn't pierce the text.
      const labelCx = endX + ux * (CATEGORY_BOX_W / 2);
      const labelCy = endY + uy * (CATEGORY_BOX_H / 2);

      out.push({
        index: i,
        above: above,
        attachX: attachX,
        attachY: attachY,
        endX: endX,
        endY: endY,
        ux: ux,
        uy: uy,
        branchLen: branchLen,
        labelCx: labelCx,
        labelCy: labelCy,
        name: cat.name,
        causes: cat.causes || [],
        flatCauseCount: flatCount,
      });
    }
    return out;
  }

  // Along a branch from (ax,ay) to (ex,ey), place k evenly-spaced points
  // starting a small distance from the attach and ending a small distance
  // from the label end. Return array of {x,y,t}.
  function _pointsAlongBranch(cat, k) {
    if (k === 0) return [];
    const ax = cat.attachX, ay = cat.attachY;
    const ex = cat.endX,    ey = cat.endY;

    // Leave 18% margin at both ends so stubs cluster near the middle.
    const tStart = 0.18;
    const tEnd   = 0.82;
    const span   = tEnd - tStart;

    const pts = [];
    for (let i = 0; i < k; i++) {
      const t = k === 1
        ? (tStart + span / 2)
        : tStart + span * (i / (k - 1));
      pts.push({
        t: t,
        x: ax + (ex - ax) * t,
        y: ay + (ey - ay) * t,
      });
    }
    return pts;
  }

  // ────────────────────────────────────────────────────────────────────────
  // SVG emission
  // ────────────────────────────────────────────────────────────────────────
  function _emitSvg(envelope, spec, categoriesLayout) {
    const title    = envelope.title || '';
    const sd       = envelope.semantic_description || {};
    const shortAlt = sd.short_alt || sd.level_1_elemental || '';
    const ariaLab  = (title || 'Fishbone diagram') + (shortAlt ? ' — ' + shortAlt : '');

    const parts = [];

    parts.push(
      '<svg xmlns="http://www.w3.org/2000/svg"' +
      ' class="ora-visual ora-visual--fishbone"' +
      ' role="img"' +
      ' aria-label="' + _esc(ariaLab) + '"' +
      ' viewBox="0 0 ' + VIEW_W + ' ' + VIEW_H + '">'
    );

    parts.push('<title class="ora-visual__accessible-title">' + _esc(ariaLab) + '</title>');

    // Arrowhead marker (semantic class; no inline style).
    parts.push(
      '<defs>' +
        '<marker id="fb-arrow" class="ora-visual__fb-arrowhead"' +
        ' viewBox="0 0 10 10" refX="9" refY="5"' +
        ' markerWidth="8" markerHeight="8" orient="auto-start-reverse">' +
          '<path class="ora-visual__fb-arrowhead-path" d="M0,0 L10,5 L0,10 Z"/>' +
        '</marker>' +
      '</defs>'
    );

    // Optional title text (above the diagram area).
    if (title) {
      parts.push(
        '<text class="ora-visual__title" x="' + (VIEW_W / 2) + '" y="' + (PAD_Y - 10) +
        '" text-anchor="middle" dominant-baseline="middle">' + _esc(title) + '</text>'
      );
    }

    // Spine (horizontal line from (SPINE_X0, SPINE_Y) to (SPINE_X1, SPINE_Y)).
    // Dual class: `ora-visual__spine` retained for the existing theme rules
    // in ora-visual-theme.css (lines 510, 516). `ora-visual__fb-spine` is
    // the canonical name per the WP-1.3c contract.
    parts.push(
      '<line class="ora-visual__spine ora-visual__fb-spine"' +
      ' x1="' + SPINE_X0 + '" y1="' + SPINE_Y + '"' +
      ' x2="' + SPINE_X1 + '" y2="' + SPINE_Y + '"' +
      ' marker-end="url(#fb-arrow)" />'
    );

    // Effect box (right terminus).
    const effX = SPINE_X1;
    const effY = SPINE_Y - EFFECT_H / 2;
    parts.push(
      '<g id="fb-effect" class="ora-visual__effect ora-visual__fb-effect">' +
        '<rect class="ora-visual__fb-effect-box"' +
        ' x="' + effX + '" y="' + effY + '"' +
        ' width="' + EFFECT_W + '" height="' + EFFECT_H + '" rx="4"/>' +
        _wrappedTextTspans(
          spec.effect,
          effX + EFFECT_W / 2,
          SPINE_Y,
          EFFECT_W - 16,
          'ora-visual__fb-effect-text'
        ) +
      '</g>'
    );

    // Categories + sub-causes.
    for (const cat of categoriesLayout) {
      parts.push(_emitCategory(cat));
    }

    parts.push('</svg>');
    return parts.join('');
  }

  function _emitCategory(cat) {
    const slug = _slug(cat.name);
    const catClass =
      'ora-visual__category ora-visual__fb-category' +
      ' ora-visual__fb-category--cat-' + ((cat.index % 8) + 1);

    const parts = [];
    parts.push('<g id="fb-category-' + _esc(slug) +
               '" class="' + catClass + '">');

    // Category branch (diagonal line).
    parts.push(
      '<line class="ora-visual__bone ora-visual__fb-bone"' +
      ' x1="' + cat.attachX + '" y1="' + cat.attachY + '"' +
      ' x2="' + cat.endX + '" y2="' + cat.endY + '" />'
    );

    // Category label (rect + text) anchored at branch end.
    const lx = cat.labelCx - CATEGORY_BOX_W / 2;
    const ly = cat.labelCy - CATEGORY_BOX_H / 2;
    parts.push(
      '<g class="ora-visual__fb-category-label">' +
        '<rect class="ora-visual__fb-category-box"' +
        ' x="' + lx + '" y="' + ly + '"' +
        ' width="' + CATEGORY_BOX_W + '" height="' + CATEGORY_BOX_H + '" rx="3"/>' +
        '<text class="ora-visual__fb-category-text"' +
        ' x="' + cat.labelCx + '" y="' + cat.labelCy + '"' +
        ' text-anchor="middle" dominant-baseline="middle">' +
          _esc(cat.name) +
        '</text>' +
      '</g>'
    );

    // Place per-cause stubs along the branch.
    const topCauses = cat.causes || [];
    const points = _pointsAlongBranch(cat, topCauses.length);
    for (let i = 0; i < topCauses.length; i++) {
      const pt = points[i];
      // Sub-cause stub direction: horizontal, pointing away from the effect
      // (i.e. leftwards). Depth-2 and depth-3 stack further left in smaller
      // text.
      parts.push(_emitCauseSubtree(topCauses[i], slug, String(i + 1), pt, 1));
    }

    parts.push('</g>');
    return parts.join('');
  }

  function _emitCauseSubtree(cause, catSlug, pathStr, anchor, depth) {
    // anchor: {x, y} — the starting point for this cause's stub.
    // depth: 1-based cause depth (1 = top cause on the branch).
    const id = 'fb-cause-' + catSlug + '-' + pathStr.replace(/\./g, '-');
    const causeClass =
      'ora-visual__sub-bone-wrap ora-visual__fb-cause' +
      ' ora-visual__fb-cause--depth-' + depth;

    const parts = [];
    parts.push('<g id="' + _esc(id) + '" class="' + causeClass + '">');

    // Horizontal stub, pointing LEFT (away from the effect).
    const stubLen = SUB_CAUSE_STUB * (1 - 0.15 * (depth - 1));  // subtly shorter at deeper levels
    const ex = anchor.x - stubLen;
    const ey = anchor.y;

    parts.push(
      '<line class="ora-visual__sub-bone ora-visual__fb-cause-line"' +
      ' x1="' + anchor.x + '" y1="' + anchor.y + '"' +
      ' x2="' + ex + '" y2="' + ey + '" />'
    );

    parts.push(
      '<text class="ora-visual__fb-cause-text"' +
      ' x="' + (ex - 6) + '" y="' + ey + '"' +
      ' text-anchor="end" dominant-baseline="middle">' +
        _esc(cause.text || '') +
      '</text>'
    );

    if (Array.isArray(cause.sub_causes) && cause.sub_causes.length > 0) {
      // Place sub-sub-causes as short vertical drops off the stub endpoint,
      // evenly spaced along a perpendicular extent. Each child gets its own
      // anchor point at (ex, ey + offset).
      const k = cause.sub_causes.length;
      const gap = SUB_CAUSE_MIN_GAP;
      // Stack below the parent stub; this avoids colliding with the parent text.
      const startY = ey + gap;
      for (let j = 0; j < k; j++) {
        const childAnchor = { x: ex, y: startY + j * gap };
        parts.push(_emitCauseSubtree(
          cause.sub_causes[j],
          catSlug,
          pathStr + '.' + (j + 1),
          childAnchor,
          depth + 1
        ));
      }
    }

    parts.push('</g>');
    return parts.join('');
  }

  // Rudimentary word-wrap into <tspan> rows. Breaks on spaces; each row no
  // wider than the maxWidth budget (estimated at ~7px/char at body size).
  function _wrappedTextTspans(raw, cx, cy, maxWidth, extraClass) {
    const text = String(raw == null ? '' : raw);
    const maxChars = Math.max(10, Math.floor(maxWidth / 7));
    const words = text.split(/\s+/);
    const lines = [];
    let cur = '';
    for (const w of words) {
      if ((cur + ' ' + w).trim().length <= maxChars) {
        cur = (cur ? cur + ' ' : '') + w;
      } else {
        if (cur) lines.push(cur);
        cur = w;
      }
    }
    if (cur) lines.push(cur);
    if (lines.length === 0) lines.push('');

    const lineH = 16;
    const totalH = (lines.length - 1) * lineH;
    const topY = cy - totalH / 2;

    const parts = [];
    parts.push(
      '<text class="' + extraClass + '"' +
      ' x="' + cx + '" y="' + topY + '"' +
      ' text-anchor="middle" dominant-baseline="middle">'
    );
    for (let i = 0; i < lines.length; i++) {
      const dy = (i === 0 ? 0 : lineH);
      parts.push(
        '<tspan x="' + cx + '" dy="' + dy + '">' + _esc(lines[i]) + '</tspan>'
      );
    }
    parts.push('</text>');
    return parts.join('');
  }

  // ────────────────────────────────────────────────────────────────────────
  // Public render()
  // ────────────────────────────────────────────────────────────────────────
  function render(envelope) {
    const errors = [];
    const warnings = [];

    const spec = envelope && envelope.spec ? envelope.spec : null;
    if (!spec) {
      errors.push(make(CODES.E_NO_SPEC,
        'fishbone: spec field missing', 'spec'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    // Defensive checks for required fields (the Ajv layer normally covers
    // these, but the renderer contract guarantees no-throw even when the
    // caller bypasses validation).
    if (typeof spec.effect !== 'string' || spec.effect.length === 0) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'fishbone: spec.effect must be a non-empty string',
        'spec.effect'));
      return { svg: '', errors: errors, warnings: warnings };
    }
    if (typeof spec.framework !== 'string') {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'fishbone: spec.framework must be a string',
        'spec.framework'));
      return { svg: '', errors: errors, warnings: warnings };
    }
    if (!Array.isArray(spec.categories) || spec.categories.length === 0) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'fishbone: spec.categories must be a non-empty array',
        'spec.categories'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    // Invariant: depth ≤ 3. Find a JSON-path-level violator if any exists.
    for (let i = 0; i < spec.categories.length; i++) {
      const cat = spec.categories[i];
      const violator = _findTooDeep(
        (cat && cat.causes) || [],
        3,
        'spec.categories[' + i + '].causes',
        0
      );
      if (violator) {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'fishbone: cause-tree depth exceeds 3 (Protocol §3.6 invariant). ' +
          'A fishbone is cause → sub-cause → sub-sub-cause maximum.',
          violator));
      }
    }
    if (errors.length) return { svg: '', errors: errors, warnings: warnings };

    // Invariant: framework enum categories if not custom.
    _validateFramework(spec, errors);
    if (errors.length) return { svg: '', errors: errors, warnings: warnings };

    // Soft lint on effect phrasing.
    _lintEffect(spec.effect, warnings);

    // Layout + emit. Defensive try/catch — contract forbids throwing.
    let svg;
    try {
      const layout = _layoutCategories(spec.categories);
      svg = _emitSvg(envelope, spec, layout);
    } catch (err) {
      errors.push(make(CODES.E_RENDERER_THREW,
        'fishbone renderer: ' + (err && err.message ? err.message : String(err)),
        'type'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    return { svg: svg, errors: errors, warnings: warnings };
  }

  // Register with the dispatcher (through the public API if it's already
  // attached; else straight to the dispatcher's internal register).
  if (window.OraVisualCompiler &&
      typeof window.OraVisualCompiler.registerRenderer === 'function') {
    window.OraVisualCompiler.registerRenderer('fishbone', { render: render });
  } else if (window.OraVisualCompiler &&
             window.OraVisualCompiler._dispatcher &&
             typeof window.OraVisualCompiler._dispatcher.register === 'function') {
    window.OraVisualCompiler._dispatcher.register('fishbone', { render: render });
  }

  // Expose a few internals for unit tests.
  return {
    render: render,
    _causeDepth: _causeDepth,
    _findTooDeep: _findTooDeep,
    _validateFramework: _validateFramework,
    _lintEffect: _lintEffect,
    _layoutCategories: _layoutCategories,
    _FRAMEWORK_CATEGORIES: FRAMEWORK_CATEGORIES,
    _BRANCH_ANGLE_DEG: _BRANCH_ANGLE_DEG,
  };

}());
