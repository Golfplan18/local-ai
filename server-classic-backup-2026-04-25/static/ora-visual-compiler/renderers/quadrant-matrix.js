/**
 * ora-visual-compiler / renderers/quadrant-matrix.js
 *
 * WP-1.3g — renderer for the `quadrant_matrix` visual type (DECISION family).
 *
 * Produces a hand-rolled 600×600 SVG grid with:
 *   - Four equal-sized quadrants separated by a horizontal + vertical axis line
 *   - Axis labels + low/high anchors on each axis, arrowhead markers on the ends
 *   - Quadrant labels at inset corners; optional multi-line narratives for
 *     subtype=scenario_planning
 *   - Items plotted at their normalized (x, y) ∈ [0,1]² positions with labels
 *
 * Per Protocol §3.10 and schema /config/visual-schemas/specs/quadrant_matrix.json:
 *   spec.subtype                    — 'strategic_2x2' | 'scenario_planning'
 *   spec.x_axis / spec.y_axis       — { label, low_label, high_label, description? }
 *   spec.quadrants                  — { TL, TR, BL, BR } each { name, narrative?, action?, indicators? }
 *   spec.items[]                    — { label, x, y, note? }   x,y ∈ [0,1]
 *   spec.axes_independence_rationale — required string
 *
 * Invariants enforced here (JSON Schema cannot express):
 *   - items[].x / items[].y defensive in [0, 1] (schema enforces — we double-check)
 *   - subtype=scenario_planning: each of the 4 quadrants has a non-empty narrative
 *   - Pairwise Pearson correlation between item x / y vectors:
 *       |r| > 0.7 emits W_AXES_DEPENDENT (major warning, non-blocking) — the
 *       two dimensions may not be independent, weakening the 2×2 framing.
 *
 * Axis convention (screen coordinates):
 *   TL = top-left     = low x, high y
 *   TR = top-right    = high x, high y
 *   BL = bottom-left  = low x, low y
 *   BR = bottom-right = high x, low y
 *
 * Sync renderer (no external library). Never throws; all failures surface
 * as structured error codes.
 *
 * Depends on: errors.js, dispatcher.js (via registerRenderer)
 * Load order: errors.js → validator.js → renderers/stub.js → dispatcher.js → index.js → renderers/quadrant-matrix.js
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};
window.OraVisualCompiler._renderers = window.OraVisualCompiler._renderers || {};

window.OraVisualCompiler._renderers.quadrantMatrix = (function () {

  const { CODES, make } = window.OraVisualCompiler.errors;

  // ── Geometry constants ────────────────────────────────────────────────
  // ViewBox 600×600 with a 50-px padding, giving a 500×500 inner area.
  // The axis cross-hair sits at (300, 300).
  const VB = 600;
  const PAD = 50;
  const INNER = VB - 2 * PAD;            // 500
  const AX_MIN = PAD;                     // 50
  const AX_MAX = VB - PAD;                // 550
  const CENTER = VB / 2;                  // 300
  const ITEM_RADIUS = 5;

  // Quadrant corner insets for label placement. Each quadrant gets its label
  // at the inset corner AWAY from the axis cross-hair, pushing the label
  // into the quadrant's interior breathing room.
  const CORNER_INSET = 12;

  // ── Small utilities ───────────────────────────────────────────────────
  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /**
   * Lower-case ASCII slug; non-ASCII-alphanum → hyphen; collapse runs;
   * trim leading/trailing hyphens. Used to derive stable item ids from
   * `label` when `id` is absent (schema does not expose an id field on items).
   */
  function _slug(s) {
    return String(s || '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'item';
  }

  /**
   * Break a string into lines of at most approxCharsPerLine chars on word
   * boundaries. Returns an array of lines (at most maxLines); lines beyond
   * maxLines are dropped and replaced with an ellipsis on the final line.
   */
  function _wrap(s, approxCharsPerLine, maxLines) {
    if (!s) return [];
    const words = String(s).trim().split(/\s+/);
    const lines = [];
    let cur = '';
    for (const w of words) {
      if (cur.length === 0) {
        cur = w;
        continue;
      }
      if (cur.length + 1 + w.length <= approxCharsPerLine) {
        cur += ' ' + w;
      } else {
        lines.push(cur);
        cur = w;
        if (lines.length === maxLines) break;
      }
    }
    if (lines.length < maxLines && cur) lines.push(cur);
    if (lines.length === maxLines) {
      // Ellipsis if any words remain unconsumed.
      const consumed = lines.join(' ').replace(/\s+/g, ' ');
      if (consumed.length < String(s).trim().length) {
        const last = lines[lines.length - 1];
        lines[lines.length - 1] = last.replace(/\s*\S*$/, '') + ' …';
      }
    }
    return lines;
  }

  // ── Pearson correlation for the axes-independence soft check ─────────
  /**
   * Sample Pearson correlation coefficient between two equal-length
   * numeric vectors. Returns null when n < 3 or when either vector has
   * zero variance (correlation undefined).
   *
   * Formula:
   *   r = Σ((x - x̄)(y - ȳ)) / √(Σ(x - x̄)² · Σ(y - ȳ)²)
   */
  function pearson(xs, ys) {
    if (!Array.isArray(xs) || !Array.isArray(ys)) return null;
    const n = xs.length;
    if (n !== ys.length || n < 3) return null;
    let sumX = 0, sumY = 0;
    for (let i = 0; i < n; i++) { sumX += xs[i]; sumY += ys[i]; }
    const meanX = sumX / n;
    const meanY = sumY / n;
    let num = 0, dx2 = 0, dy2 = 0;
    for (let i = 0; i < n; i++) {
      const dx = xs[i] - meanX;
      const dy = ys[i] - meanY;
      num += dx * dy;
      dx2 += dx * dx;
      dy2 += dy * dy;
    }
    if (dx2 === 0 || dy2 === 0) return null;  // zero variance
    const denom = Math.sqrt(dx2 * dy2);
    if (denom === 0) return null;
    return num / denom;
  }

  // ── Coordinate transforms ─────────────────────────────────────────────
  // Items live in normalized [0,1]² with y=0 at the bottom. SVG y-axis
  // points down, so we invert y when mapping to screen coords.
  function xToPx(x) { return AX_MIN + x * INNER; }
  function yToPx(y) { return AX_MAX - y * INNER; }

  // Quadrant screen-space centers (for placing the inset label + narrative).
  const QUAD_RECTS = {
    TL: { xMin: AX_MIN,  yMin: AX_MIN,  xMax: CENTER, yMax: CENTER },
    TR: { xMin: CENTER,  yMin: AX_MIN,  xMax: AX_MAX, yMax: CENTER },
    BL: { xMin: AX_MIN,  yMin: CENTER,  xMax: CENTER, yMax: AX_MAX },
    BR: { xMin: CENTER,  yMin: CENTER,  xMax: AX_MAX, yMax: AX_MAX },
  };

  // ── SVG emission helpers ──────────────────────────────────────────────
  function emitDefs() {
    // Two arrowhead markers: one for the x-axis tip and one for the y-axis
    // tip. Kept as separate ids so future CSS can target each end if needed.
    return [
      '<defs>',
      '  <marker id="q-arrow-x" class="ora-visual__axis-arrow" ',
      'viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" ',
      'orient="auto-start-reverse">',
      '    <path d="M0,0 L10,5 L0,10 Z" />',
      '  </marker>',
      '  <marker id="q-arrow-y" class="ora-visual__axis-arrow" ',
      'viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" ',
      'orient="auto-start-reverse">',
      '    <path d="M0,0 L10,5 L0,10 Z" />',
      '  </marker>',
      '</defs>',
    ].join('\n');
  }

  function emitAxes(xAxis, yAxis) {
    const parts = [];

    // x-axis: horizontal across the middle, arrow on its right end.
    parts.push(
      '<line class="ora-visual__axis ora-visual__axis--x" ' +
      'x1="' + AX_MIN + '" y1="' + CENTER + '" ' +
      'x2="' + AX_MAX + '" y2="' + CENTER + '" ' +
      'marker-end="url(#q-arrow-x)" />'
    );

    // y-axis: vertical through the middle, arrow on its top end.
    parts.push(
      '<line class="ora-visual__axis ora-visual__axis--y" ' +
      'x1="' + CENTER + '" y1="' + AX_MAX + '" ' +
      'x2="' + CENTER + '" y2="' + AX_MIN + '" ' +
      'marker-end="url(#q-arrow-y)" />'
    );

    // Axis master labels: x on right-center below axis, y on top-center
    // left of axis. Semantic class __axis-label.
    if (xAxis) {
      parts.push(
        '<text class="ora-visual__axis-label ora-visual__axis-label--x" ' +
        'x="' + AX_MAX + '" y="' + (CENTER + 28) + '" ' +
        'text-anchor="end">' + _esc(xAxis.label || '') + '</text>'
      );
    }
    if (yAxis) {
      // Y-label sits ABOVE the top tip; written horizontally for legibility.
      parts.push(
        '<text class="ora-visual__axis-label ora-visual__axis-label--y" ' +
        'x="' + CENTER + '" y="' + (AX_MIN - 14) + '" ' +
        'text-anchor="middle">' + _esc(yAxis.label || '') + '</text>'
      );
    }

    // Anchor labels: low/high on each axis, just past the tip.
    if (xAxis) {
      parts.push(
        '<text class="ora-visual__axis-anchor ora-visual__axis-anchor--x-low" ' +
        'x="' + AX_MIN + '" y="' + (CENTER + 14) + '" ' +
        'text-anchor="start">' + _esc(xAxis.low_label || 'low') + '</text>'
      );
      parts.push(
        '<text class="ora-visual__axis-anchor ora-visual__axis-anchor--x-high" ' +
        'x="' + AX_MAX + '" y="' + (CENTER + 14) + '" ' +
        'text-anchor="end">' + _esc(xAxis.high_label || 'high') + '</text>'
      );
    }
    if (yAxis) {
      parts.push(
        '<text class="ora-visual__axis-anchor ora-visual__axis-anchor--y-low" ' +
        'x="' + (CENTER - 6) + '" y="' + AX_MAX + '" ' +
        'text-anchor="end">' + _esc(yAxis.low_label || 'low') + '</text>'
      );
      parts.push(
        '<text class="ora-visual__axis-anchor ora-visual__axis-anchor--y-high" ' +
        'x="' + (CENTER - 6) + '" y="' + (AX_MIN + 10) + '" ' +
        'text-anchor="end">' + _esc(yAxis.high_label || 'high') + '</text>'
      );
    }

    return parts.join('\n');
  }

  function emitQuadrant(key, quadrantSpec, isScenario) {
    const rect = QUAD_RECTS[key];
    const name = quadrantSpec.name || key;
    const narrative = quadrantSpec.narrative || '';

    // Label placement: inset in the interior corner diagonally opposite the
    // cross-hair. This keeps labels away from clustered axis anchors.
    let labelX, labelY, anchor;
    if (key === 'TL') {
      labelX = rect.xMin + CORNER_INSET;
      labelY = rect.yMin + CORNER_INSET + 6;
      anchor = 'start';
    } else if (key === 'TR') {
      labelX = rect.xMax - CORNER_INSET;
      labelY = rect.yMin + CORNER_INSET + 6;
      anchor = 'end';
    } else if (key === 'BL') {
      labelX = rect.xMin + CORNER_INSET;
      labelY = rect.yMax - CORNER_INSET;
      anchor = 'start';
    } else {  // BR
      labelX = rect.xMax - CORNER_INSET;
      labelY = rect.yMax - CORNER_INSET;
      anchor = 'end';
    }

    const parts = [];
    parts.push('<g id="q-quadrant-' + key + '" class="ora-visual__quadrant">');

    // Transparent hit-rect — future annotation targeting (Phase 5).
    parts.push(
      '<rect class="ora-visual__quadrant-hitbox" ' +
      'x="' + rect.xMin + '" y="' + rect.yMin + '" ' +
      'width="' + (rect.xMax - rect.xMin) + '" ' +
      'height="' + (rect.yMax - rect.yMin) + '" ' +
      'fill="transparent" pointer-events="all" />'
    );

    // Quadrant name label.
    parts.push(
      '<text class="ora-visual__quadrant-label" ' +
      'x="' + labelX + '" y="' + labelY + '" ' +
      'text-anchor="' + anchor + '">' + _esc(name) + '</text>'
    );

    // Narrative (scenario_planning) — small multi-line block under the label.
    if (isScenario && narrative) {
      const maxChars = 28;
      const maxLines = 4;
      const lines = _wrap(narrative, maxChars, maxLines);

      // Narrative anchors match label anchor but start one line-height below.
      let startX = labelX;
      let startY = labelY + 20;
      const lineHeight = 14;

      parts.push(
        '<text class="ora-visual__quadrant-narrative" ' +
        'x="' + startX + '" y="' + startY + '" ' +
        'text-anchor="' + anchor + '">' +
        lines.map((ln, i) => {
          const dy = i === 0 ? 0 : lineHeight;
          return '<tspan x="' + startX + '" dy="' + dy + '">' + _esc(ln) + '</tspan>';
        }).join('') +
        '</text>'
      );
    }

    parts.push('</g>');
    return parts.join('\n');
  }

  function emitItem(item, idx) {
    const cx = xToPx(item.x);
    const cy = yToPx(item.y);
    const id = 'q-item-' + _slug(item.label || ('item-' + (idx + 1)));

    // Label placement: to the right of the dot by default; if the item is in
    // the right half of the canvas, flip to the left to keep the label inside.
    const labelLeft = cx >= CENTER;
    const labelX = labelLeft ? (cx - ITEM_RADIUS - 3) : (cx + ITEM_RADIUS + 3);
    const labelAnchor = labelLeft ? 'end' : 'start';
    const labelY = cy + 4;   // small vertical nudge to center on cap-height

    return [
      '<g id="' + _esc(id) + '" class="ora-visual__item">',
      '  <circle class="ora-visual__item-dot" cx="' + cx + '" cy="' + cy + '" r="' + ITEM_RADIUS + '" />',
      '  <text class="ora-visual__item-label" ' +
        'x="' + labelX + '" y="' + labelY + '" ' +
        'text-anchor="' + labelAnchor + '">' + _esc(item.label || '') + '</text>',
      '</g>',
    ].join('\n');
  }

  // ── Main render ───────────────────────────────────────────────────────
  /**
   * render(envelope) → { svg, errors, warnings }
   * Sync. Never throws. Error codes from errors.js only.
   */
  function render(envelope) {
    const errors = [];
    const warnings = [];

    const spec = envelope && envelope.spec ? envelope.spec : null;
    if (!spec) {
      errors.push(make(CODES.E_NO_SPEC,
        'quadrant_matrix renderer: spec field missing', 'spec'));
      return { svg: '', errors, warnings };
    }

    const subtype = spec.subtype;
    const xAxis = spec.x_axis;
    const yAxis = spec.y_axis;
    const quadrants = spec.quadrants;
    const items = Array.isArray(spec.items) ? spec.items : [];
    const isScenario = subtype === 'scenario_planning';

    // Structural spot-checks (schema already enforces these, but we stay
    // defensive — the renderer must never throw and should emit clean errors).
    if (!xAxis || typeof xAxis !== 'object') {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'quadrant_matrix: spec.x_axis missing or not an object', 'spec.x_axis'));
    }
    if (!yAxis || typeof yAxis !== 'object') {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'quadrant_matrix: spec.y_axis missing or not an object', 'spec.y_axis'));
    }
    if (!quadrants || typeof quadrants !== 'object') {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'quadrant_matrix: spec.quadrants missing or not an object', 'spec.quadrants'));
    } else {
      for (const k of ['TL', 'TR', 'BL', 'BR']) {
        if (!quadrants[k] || typeof quadrants[k] !== 'object' ||
            typeof quadrants[k].name !== 'string' || quadrants[k].name.length === 0) {
          errors.push(make(CODES.E_SCHEMA_INVALID,
            'quadrant_matrix: quadrant ' + k + ' missing or has no name',
            'spec.quadrants.' + k));
        }
      }
    }
    if (errors.length) return { svg: '', errors, warnings };

    // Scenario-planning invariant: each quadrant has a non-empty narrative.
    if (isScenario) {
      const missingNarratives = [];
      for (const k of ['TL', 'TR', 'BL', 'BR']) {
        const q = quadrants[k];
        if (!q || typeof q.narrative !== 'string' || q.narrative.trim().length === 0) {
          missingNarratives.push(k);
        }
      }
      if (missingNarratives.length) {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'quadrant_matrix: subtype=scenario_planning requires a non-empty narrative ' +
            'for every quadrant. Missing: ' + missingNarratives.join(', '),
          'spec.quadrants.' + missingNarratives[0] + '.narrative'));
        return { svg: '', errors, warnings };
      }
    }

    // Items: defensive [0, 1] check. Schema already enforces; re-check here
    // because the renderer may be called without Ajv (Layer 1 only).
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      if (!it || typeof it !== 'object' ||
          typeof it.x !== 'number' || typeof it.y !== 'number' ||
          typeof it.label !== 'string' || it.label.length === 0) {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'quadrant_matrix: items[' + i + '] must be {label:string, x:number, y:number}',
          'spec.items[' + i + ']'));
        continue;
      }
      if (!(it.x >= 0 && it.x <= 1)) {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'quadrant_matrix: items[' + i + '].x=' + it.x + ' out of [0, 1]',
          'spec.items[' + i + '].x'));
      }
      if (!(it.y >= 0 && it.y <= 1)) {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'quadrant_matrix: items[' + i + '].y=' + it.y + ' out of [0, 1]',
          'spec.items[' + i + '].y'));
      }
    }
    if (errors.length) return { svg: '', errors, warnings };

    // Soft check: Pearson correlation of items' x/y vectors. If |r| > 0.7,
    // the two dimensions are likely not independent — weakens the 2×2 framing.
    // Needs at least 3 items to say anything meaningful.
    if (items.length >= 3) {
      const xs = items.map((it) => it.x);
      const ys = items.map((it) => it.y);
      const r = pearson(xs, ys);
      if (r !== null && Math.abs(r) > 0.7) {
        warnings.push(make(CODES.W_AXES_DEPENDENT,
          'quadrant_matrix: axes may not be independent (Pearson r=' + r.toFixed(3) +
            ', |r|>0.7 across ' + items.length + ' items). ' +
            'The 2×2 framing is weakened when dimensions correlate; consider ' +
            'reformulating the axes.',
          'spec.items'));
      }
    }

    // ── SVG assembly ──
    const title = envelope.title || '';
    const shortA = envelope.semantic_description && envelope.semantic_description.short_alt
      ? envelope.semantic_description.short_alt
      : '';
    const typeLabel = 'quadrant_matrix';
    const ariaLabel = (title || typeLabel) + (shortA ? ' — ' + shortA : '');

    const rootClasses = [
      'ora-visual',
      'ora-visual--quadrant_matrix',
      'ora-visual--quadrant_matrix--' + _esc(subtype || 'strategic_2x2'),
    ].join(' ');

    const svgParts = [];
    svgParts.push(
      '<svg xmlns="http://www.w3.org/2000/svg" ' +
      'class="' + rootClasses + '" ' +
      'role="img" ' +
      'aria-label="' + _esc(ariaLabel) + '" ' +
      'viewBox="0 0 ' + VB + ' ' + VB + '">'
    );
    svgParts.push('<title class="ora-visual__accessible-title">' + _esc(ariaLabel) + '</title>');

    svgParts.push(emitDefs());

    // Title inside the plot area, above the grid.
    if (title) {
      svgParts.push(
        '<text class="ora-visual__title" x="' + CENTER + '" y="' + (AX_MIN - 30) + '" ' +
        'text-anchor="middle">' + _esc(title) + '</text>'
      );
    }

    // Axes (with arrowheads) and axis labels.
    svgParts.push(emitAxes(xAxis, yAxis));

    // Four quadrants (labels + hitbox + optional narrative).
    for (const k of ['TL', 'TR', 'BL', 'BR']) {
      svgParts.push(emitQuadrant(k, quadrants[k], isScenario));
    }

    // Items last so dots sit on top of quadrant backgrounds.
    for (let i = 0; i < items.length; i++) {
      svgParts.push(emitItem(items[i], i));
    }

    svgParts.push('</svg>');
    const svg = svgParts.join('\n');

    return { svg, errors: [], warnings };
  }

  // Register with the dispatcher.
  if (window.OraVisualCompiler &&
      typeof window.OraVisualCompiler.registerRenderer === 'function') {
    window.OraVisualCompiler.registerRenderer('quadrant_matrix', { render: render });
  }

  // Expose internals for unit testing.
  return {
    render: render,
    _pearson: pearson,
    _slug: _slug,
    _wrap: _wrap,
    _xToPx: xToPx,
    _yToPx: yToPx,
  };
}());
