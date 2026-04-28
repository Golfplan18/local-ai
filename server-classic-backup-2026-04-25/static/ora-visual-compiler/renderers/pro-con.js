/**
 * ora-visual-compiler / renderers/pro-con.js
 * WP-1.3j — renderer for the `pro_con` visual type.
 *
 * Per Protocol §3.13 (ARGUMENT family, pro-con tree). A degenerate argument
 * map: a single `claim` at the top, with `pros` on the left and `cons` on
 * the right, each a recursive tree of arguments (`text`, optional `weight`
 * in 1..5, optional `source`, optional `children`). Optional `decision`
 * summary below the tree.
 *
 * Layout: top-centred claim rectangle, two columns below (pros left, cons
 * right). Children indented under their parent; connecting branches drawn
 * as orthogonal elbows. Deterministic, hand-rolled SVG — no external
 * layout library. Synchronous; never throws.
 *
 * Invariants enforced here (beyond what the JSON Schema already does):
 *   - spec.claim present and non-empty                → E_SCHEMA_INVALID
 *   - pros/cons (and their children) are arrays       → E_SCHEMA_INVALID
 *   - every argument node has a non-empty `text`      → E_SCHEMA_INVALID
 *   - weight, if present, is an integer in [1, 5]     → E_SCHEMA_INVALID
 *     (the schema enforces this under Ajv; we enforce it again here so
 *      Layer-1 runs catch it as well)
 *
 * Stable semantic IDs (targetable by Phase 5 annotations):
 *   - <rect id="pc-claim">
 *   - <g id="pc-pro-<path>">  where <path> is a dot-separated index chain
 *                             (e.g. "0" = first top-level pro,
 *                                   "0.1" = second child of first pro)
 *   - <g id="pc-con-<path>">
 *   - <text id="pc-decision">
 *
 * Stable semantic classes (styled via ora-visual-theme.css):
 *   - ora-visual  ora-visual--pro_con                  (root)
 *   - ora-visual__claim                                 (claim rect + label)
 *   - ora-visual__pro                                   (pro arg rect)
 *   - ora-visual__con                                   (con arg rect)
 *   - ora-visual__pc-branch                             (connector line)
 *   - ora-visual__weight-indicator                      (weight badge text)
 *   - ora-visual__annotation                            (decision label)
 *
 * Layout direction: vertical (top-to-bottom), claim at top centre, two
 * columns below. Chosen over horizontal because readers scan pros-versus-
 * cons as side-by-side columns in every natural-language rendering of the
 * technique (Ben Franklin's 1772 letter, modern decision literature).
 *
 * Depends on:
 *   errors.js
 *   dispatcher.js  (via OraVisualCompiler.registerRenderer)
 *
 * Load order:
 *   errors.js → validator.js → renderers/stub.js → dispatcher.js → index.js
 *   renderers/pro-con.js                                   ← this file
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};
window.OraVisualCompiler._renderers = window.OraVisualCompiler._renderers || {};

window.OraVisualCompiler._renderers.proCon = (function () {

  const { CODES, make } = window.OraVisualCompiler.errors;

  // ── XML-safe escape for attribute values and text content. ────────────────
  function _esc(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Geometry constants (all px, honoured by the semantic CSS). ────────────
  const WIDTH             = 720;           // nominal viewBox width
  const MARGIN_X          = 24;
  const MARGIN_TOP        = 28;
  const CLAIM_Y           = 40;            // claim baseline
  const CLAIM_HEIGHT      = 56;
  const CLAIM_MAX_WIDTH   = 520;
  const ROW_HEIGHT        = 54;            // vertical spacing per arg row
  const ARG_HEIGHT        = 38;
  const ARG_MIN_WIDTH     = 120;
  const ARG_MAX_WIDTH     = 280;
  const INDENT_PX         = 22;            // horizontal offset per depth level
  const CHAR_WIDTH        = 7.0;           // conservative monospaced estimate
  const COLUMN_GAP        = 60;            // space between pros and cons columns
  const COLUMN_TOP_Y      = CLAIM_Y + CLAIM_HEIGHT + 32;
  const BRANCH_FROM_CLAIM_Y = CLAIM_Y + CLAIM_HEIGHT;
  const WEIGHT_BADGE_W    = 22;
  const WEIGHT_BADGE_H    = 16;

  // ── Structural validation (semantic invariants beyond Ajv). ───────────────
  /**
   * _validateSpec(spec) → { errors: Array<Error> }
   * Emits one error per independent violation. Returns early on the
   * top-level shape failure because subsequent checks presuppose the shape.
   */
  function _validateSpec(spec) {
    const errors = [];

    if (!spec || typeof spec !== 'object') {
      errors.push(make(CODES.E_NO_SPEC,
        'pro_con: spec must be a non-null object', 'spec'));
      return { errors };
    }

    if (typeof spec.claim !== 'string' || spec.claim.trim().length === 0) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'pro_con: spec.claim must be a non-empty string',
        'spec.claim'));
    }

    if (!Array.isArray(spec.pros)) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'pro_con: spec.pros must be an array (possibly empty)',
        'spec.pros'));
    }
    if (!Array.isArray(spec.cons)) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'pro_con: spec.cons must be an array (possibly empty)',
        'spec.cons'));
    }
    if (errors.length) return { errors };

    // Recursively verify every argument node.
    _walkArgs(spec.pros, 'spec.pros', errors);
    _walkArgs(spec.cons, 'spec.cons', errors);

    return { errors };
  }

  function _walkArgs(arr, pathBase, errors) {
    for (let i = 0; i < arr.length; i++) {
      const a = arr[i];
      const p = pathBase + '[' + i + ']';
      if (!a || typeof a !== 'object' || Array.isArray(a)) {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'pro_con: argument at ' + p + ' must be an object', p));
        continue;
      }
      if (typeof a.text !== 'string' || a.text.trim().length === 0) {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'pro_con: argument at ' + p + ' must have a non-empty text',
          p + '.text'));
      }
      if ('weight' in a && a.weight !== undefined && a.weight !== null) {
        const w = a.weight;
        const okInt = typeof w === 'number' && Number.isInteger(w);
        if (!okInt || w < 1 || w > 5) {
          errors.push(make(CODES.E_SCHEMA_INVALID,
            'pro_con: argument at ' + p + ' weight must be an integer in [1, 5] (got ' +
            JSON.stringify(w) + ')',
            p + '.weight'));
        }
      }
      if ('source' in a && a.source !== undefined && a.source !== null &&
          typeof a.source !== 'string') {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          'pro_con: argument at ' + p + ' source must be a string when present',
          p + '.source'));
      }
      if ('children' in a && a.children !== undefined && a.children !== null) {
        if (!Array.isArray(a.children)) {
          errors.push(make(CODES.E_SCHEMA_INVALID,
            'pro_con: argument at ' + p + ' children must be an array when present',
            p + '.children'));
        } else {
          _walkArgs(a.children, p + '.children', errors);
        }
      }
    }
  }

  // ── Layout: flatten a side's tree into a linear sequence of rows. ─────────
  /**
   * Each row carries: { text, depth, path, weight, source, isLast, parentPath }.
   * Rows are emitted in pre-order so the SVG reads top-to-bottom naturally.
   * path is a dot-separated index chain, e.g. "0.1" for the second child of
   * the first top-level item.
   */
  function _flatten(items, side) {
    const rows = [];
    function walk(arr, depth, parentPath) {
      if (!Array.isArray(arr)) return;
      for (let i = 0; i < arr.length; i++) {
        const a = arr[i];
        const p = parentPath === '' ? String(i) : parentPath + '.' + i;
        rows.push({
          text: a.text || '',
          depth: depth,
          path: p,
          weight: (typeof a.weight === 'number') ? a.weight : null,
          source: (typeof a.source === 'string') ? a.source : null,
          parentPath: parentPath,  // '' for top-level
          side: side,
        });
        if (Array.isArray(a.children) && a.children.length) {
          walk(a.children, depth + 1, p);
        }
      }
    }
    walk(items, 0, '');
    return rows;
  }

  // ── Width estimation. Caps long labels; CSS governs final typography. ────
  function _labelWidth(text) {
    const w = Math.max(ARG_MIN_WIDTH, (text.length * CHAR_WIDTH) + 24);
    return Math.min(w, ARG_MAX_WIDTH);
  }

  function _claimWidth(text) {
    const w = Math.max(260, (text.length * (CHAR_WIDTH + 0.5)) + 40);
    return Math.min(w, CLAIM_MAX_WIDTH);
  }

  // ── Truncation with ellipsis (SVG text does not wrap; we keep one line). ─
  function _truncate(text, maxChars) {
    if (!text) return '';
    if (text.length <= maxChars) return text;
    return text.slice(0, Math.max(1, maxChars - 1)) + '\u2026';
  }
  function _maxCharsFor(widthPx) {
    // Inverse of _labelWidth, accounting for padding.
    return Math.max(6, Math.floor((widthPx - 24) / CHAR_WIDTH));
  }

  // ── SVG emission. ─────────────────────────────────────────────────────────
  /**
   * _emitSvg(envelope, prosRows, consRows) → string
   * Pure string construction — no DOM required.
   */
  function _emitSvg(envelope, prosRows, consRows) {
    const spec = envelope.spec;

    const claimText  = spec.claim;
    const title      = envelope.title || '';
    const shortAlt   = (envelope.semantic_description &&
                        envelope.semantic_description.short_alt) || '';
    const typeLab    = envelope.type || 'pro_con';
    const ariaLab    = (title || typeLab) + (shortAlt ? ' \u2014 ' + shortAlt : '');

    // Column geometry.
    const colWidth  = (WIDTH - MARGIN_X * 2 - COLUMN_GAP) / 2;
    const leftColX  = MARGIN_X;
    const rightColX = MARGIN_X + colWidth + COLUMN_GAP;

    // Row counts → total height.
    const rows = Math.max(prosRows.length, consRows.length, 1);
    const columnsBlockHeight = rows * ROW_HEIGHT + 20;
    let   totalHeight = COLUMN_TOP_Y + columnsBlockHeight + 24;

    // Decision line, if any.
    const decision = (typeof spec.decision === 'string' && spec.decision.length)
      ? spec.decision
      : null;
    if (decision) totalHeight += 30;

    // Caption adjustment.
    const hasCaption = envelope.caption && typeof envelope.caption === 'object';
    if (hasCaption) totalHeight += 24;

    // Build.
    const parts = [];
    parts.push(
      '<svg xmlns="http://www.w3.org/2000/svg" ' +
      'viewBox="0 0 ' + WIDTH + ' ' + totalHeight.toFixed(0) + '" ' +
      'class="ora-visual ora-visual--pro_con" ' +
      'role="img" aria-label="' + _esc(ariaLab) + '">'
    );
    parts.push(
      '<title class="ora-visual__accessible-title">' + _esc(ariaLab) + '</title>'
    );

    // ── Decorative title (SVG <title> is accessibility-only). ──────────────
    if (title) {
      parts.push(
        '<text class="ora-visual__title" ' +
          'x="' + (WIDTH / 2) + '" y="' + MARGIN_TOP + '" ' +
          'text-anchor="middle">' + _esc(title) + '</text>'
      );
    }

    // ── Claim rectangle (top-centre). ───────────────────────────────────────
    const cw = _claimWidth(claimText);
    const cx = (WIDTH - cw) / 2;
    const cy = CLAIM_Y;
    const claimMax = _maxCharsFor(cw + 40);
    parts.push(
      '<g class="ora-visual__pc-claim-group" ' +
        'transform="translate(0,0)">' +
      '<rect id="pc-claim" class="ora-visual__claim" ' +
        'x="' + cx.toFixed(2) + '" y="' + cy + '" ' +
        'width="' + cw.toFixed(2) + '" height="' + CLAIM_HEIGHT + '" ' +
        'rx="6" ry="6"/>' +
      '<text class="ora-visual__claim-label ora-visual__label" ' +
        'x="' + (WIDTH / 2).toFixed(2) + '" ' +
        'y="' + (cy + CLAIM_HEIGHT / 2).toFixed(2) + '" ' +
        'text-anchor="middle" dominant-baseline="central">' +
        _esc(_truncate(claimText, claimMax)) +
      '</text>' +
      '</g>'
    );

    // ── Column header glyphs (+ / −). Decorative only. ──────────────────────
    const prosHeaderX = leftColX + colWidth / 2;
    const consHeaderX = rightColX + colWidth / 2;
    const headerY = COLUMN_TOP_Y - 10;
    parts.push(
      '<text class="ora-visual__label ora-visual__label--mono ora-visual__pc-column-header" ' +
        'x="' + prosHeaderX.toFixed(2) + '" y="' + headerY + '" ' +
        'text-anchor="middle" dominant-baseline="central">+ Pros</text>'
    );
    parts.push(
      '<text class="ora-visual__label ora-visual__label--mono ora-visual__pc-column-header" ' +
        'x="' + consHeaderX.toFixed(2) + '" y="' + headerY + '" ' +
        'text-anchor="middle" dominant-baseline="central">\u2212 Cons</text>'
    );

    // ── Branches from claim bottom to first item of each side. ─────────────
    // Drawn before the argument rectangles so the rects overlay the lines.
    const claimBottomX = WIDTH / 2;
    const claimBottomY = BRANCH_FROM_CLAIM_Y;

    parts.push('<g class="ora-visual__pc-branches">');

    function _emitBranches(rowsSide, side) {
      const colX = (side === 'pro') ? leftColX : rightColX;
      // Map depth+parentPath → {y, x} of parent row start (for children).
      const parentByPath = new Map();
      for (let i = 0; i < rowsSide.length; i++) {
        const r = rowsSide[i];
        const rowX = colX + r.depth * INDENT_PX;
        const rowY = COLUMN_TOP_Y + i * ROW_HEIGHT + ARG_HEIGHT / 2;
        parentByPath.set(r.path, { x: rowX, y: rowY, rowTop: rowY - ARG_HEIGHT / 2 });

        if (r.depth === 0) {
          // Branch from claim bottom-centre down then over to the first row
          // of this column at an elbow.
          const midY = claimBottomY + 16;
          const endX = rowX + 8;
          const endY = rowY;
          const d =
            'M ' + claimBottomX.toFixed(2) + ' ' + claimBottomY.toFixed(2) +
            ' L ' + claimBottomX.toFixed(2) + ' ' + midY.toFixed(2) +
            ' L ' + endX.toFixed(2) + ' ' + midY.toFixed(2) +
            ' L ' + endX.toFixed(2) + ' ' + endY.toFixed(2);
          // Only draw the top-of-column branch once per column (from the
          // first row). For deeper top-level siblings, use a short stub from
          // the column header line.
          if (i === 0 || rowsSide[i - 1].depth !== 0) {
            parts.push(
              '<path class="ora-visual__pc-branch" d="' + d + '" fill="none"/>'
            );
          } else {
            // Sibling at depth 0: short vertical tick from column header line.
            const tickX = rowX + 8;
            const tickYTop = COLUMN_TOP_Y + (i - 1) * ROW_HEIGHT + ARG_HEIGHT / 2;
            const tickYBot = rowY;
            parts.push(
              '<path class="ora-visual__pc-branch" d="M ' +
                tickX.toFixed(2) + ' ' + tickYTop.toFixed(2) +
                ' L ' + tickX.toFixed(2) + ' ' + tickYBot.toFixed(2) +
                '" fill="none"/>'
            );
          }
        } else {
          // Child branch: elbow from parent's left edge down to this row.
          const parent = parentByPath.get(r.parentPath);
          if (parent) {
            const parentX = parent.x + 14;  // short offset inside parent rect
            const elbowX = rowX + 8;
            const d =
              'M ' + parentX.toFixed(2) + ' ' + parent.y.toFixed(2) +
              ' L ' + parentX.toFixed(2) + ' ' + (rowY).toFixed(2) +
              ' L ' + elbowX.toFixed(2) + ' ' + (rowY).toFixed(2);
            parts.push(
              '<path class="ora-visual__pc-branch" d="' + d + '" fill="none"/>'
            );
          }
        }
      }
    }
    _emitBranches(prosRows, 'pro');
    _emitBranches(consRows, 'con');
    parts.push('</g>');

    // ── Argument rectangles ────────────────────────────────────────────────
    function _emitSide(rowsSide, side) {
      const colX = (side === 'pro') ? leftColX : rightColX;
      const idPrefix = (side === 'pro') ? 'pc-pro-' : 'pc-con-';
      const classMain = (side === 'pro')
        ? 'ora-visual__pro'
        : 'ora-visual__con';

      for (let i = 0; i < rowsSide.length; i++) {
        const r = rowsSide[i];
        const rowX = colX + r.depth * INDENT_PX;
        const rowY = COLUMN_TOP_Y + i * ROW_HEIGHT;
        const maxW = Math.max(ARG_MIN_WIDTH, colWidth - r.depth * INDENT_PX - 8);
        const w = Math.min(_labelWidth(r.text), maxW);
        const textMax = _maxCharsFor(w);
        const truncated = _truncate(r.text, textMax);

        parts.push(
          '<g id="' + idPrefix + _esc(r.path) + '" class="ora-visual__pc-arg-group" ' +
            'data-side="' + side + '" data-depth="' + r.depth + '">'
        );
        parts.push(
          '<rect class="' + classMain + '" ' +
            'x="' + rowX.toFixed(2) + '" y="' + rowY.toFixed(2) + '" ' +
            'width="' + w.toFixed(2) + '" height="' + ARG_HEIGHT + '" ' +
            'rx="4" ry="4"/>'
        );
        parts.push(
          '<text class="ora-visual__label ora-visual__pc-arg-label" ' +
            'x="' + (rowX + 12).toFixed(2) + '" ' +
            'y="' + (rowY + ARG_HEIGHT / 2).toFixed(2) + '" ' +
            'dominant-baseline="central">' +
            _esc(truncated) +
          '</text>'
        );

        // Weight badge. Small rounded pill on the right inside-edge.
        if (r.weight !== null && r.weight !== undefined) {
          const bx = rowX + w - WEIGHT_BADGE_W - 6;
          const by = rowY + (ARG_HEIGHT - WEIGHT_BADGE_H) / 2;
          parts.push(
            '<g class="ora-visual__pc-weight">' +
            '<rect class="ora-visual__pc-weight-box" ' +
              'x="' + bx.toFixed(2) + '" y="' + by.toFixed(2) + '" ' +
              'width="' + WEIGHT_BADGE_W + '" height="' + WEIGHT_BADGE_H + '" ' +
              'rx="3" ry="3"/>' +
            '<text class="ora-visual__weight-indicator" ' +
              'x="' + (bx + WEIGHT_BADGE_W / 2).toFixed(2) + '" ' +
              'y="' + (by + WEIGHT_BADGE_H / 2).toFixed(2) + '" ' +
              'text-anchor="middle" dominant-baseline="central">' +
              _esc(String(r.weight)) +
            '</text>' +
            '</g>'
          );
        }

        // Source attribution (tiny annotation under the rect, if present).
        if (r.source) {
          parts.push(
            '<text class="ora-visual__annotation ora-visual__pc-source" ' +
              'x="' + (rowX + 4).toFixed(2) + '" ' +
              'y="' + (rowY + ARG_HEIGHT + 10).toFixed(2) + '">' +
              _esc(_truncate('[' + r.source + ']', 48)) +
            '</text>'
          );
        }

        parts.push('</g>');
      }
    }

    _emitSide(prosRows, 'pro');
    _emitSide(consRows, 'con');

    // ── Decision summary. ──────────────────────────────────────────────────
    if (decision) {
      const dy = COLUMN_TOP_Y + columnsBlockHeight + 16;
      parts.push(
        '<text id="pc-decision" class="ora-visual__annotation ora-visual__pc-decision" ' +
          'x="' + (WIDTH / 2).toFixed(2) + '" y="' + dy.toFixed(2) + '" ' +
          'text-anchor="middle" dominant-baseline="central">' +
          _esc('Decision: ' + _truncate(decision, 96)) +
        '</text>'
      );
    }

    // ── Caption (Tufte T15). ───────────────────────────────────────────────
    if (hasCaption) {
      const c = envelope.caption;
      const bits = [];
      if (c.source)            bits.push('Source: ' + c.source);
      if (c.period)            bits.push('Period: ' + c.period);
      if (typeof c.n === 'number') bits.push('n=' + c.n);
      if (c.units)             bits.push('Units: ' + c.units);
      if (bits.length) {
        parts.push(
          '<text class="ora-visual__caption" ' +
            'x="' + (MARGIN_X).toFixed(2) + '" ' +
            'y="' + (totalHeight - 12).toFixed(2) + '">' +
            _esc(bits.join(' \u00b7 ')) +
          '</text>'
        );
      }
    }

    parts.push('</svg>');
    return parts.join('');
  }

  // ── Public render() ───────────────────────────────────────────────────────
  /**
   * render(envelope) → { svg, errors, warnings }
   * Never throws. Synchronous (no I/O, no async layout).
   */
  function render(envelope) {
    const errors = [];
    const warnings = [];

    const spec = envelope && envelope.spec ? envelope.spec : null;
    if (!spec) {
      errors.push(make(CODES.E_NO_SPEC,
        'pro_con: spec field missing', 'spec'));
      return { svg: '', errors, warnings };
    }

    // Validate shape + invariants.
    const v = _validateSpec(spec);
    if (v.errors.length) {
      return { svg: '', errors: v.errors, warnings };
    }

    // Flatten both sides.
    const prosRows = _flatten(spec.pros, 'pro');
    const consRows = _flatten(spec.cons, 'con');

    // Emit SVG. Never throws in normal use; catch to honour the contract.
    let svg;
    try {
      svg = _emitSvg(envelope, prosRows, consRows);
    } catch (err) {
      errors.push(make(CODES.E_RENDERER_THREW,
        'pro_con: SVG emission threw \u2014 ' +
        (err && err.message ? err.message : String(err))));
      return { svg: '', errors, warnings };
    }

    return { svg: svg, errors: [], warnings: warnings };
  }

  // Register with the dispatcher on load.
  if (window.OraVisualCompiler &&
      typeof window.OraVisualCompiler.registerRenderer === 'function') {
    window.OraVisualCompiler.registerRenderer('pro_con', { render: render });
  }

  // Expose internals for unit tests.
  return {
    render: render,
    _validateSpec: _validateSpec,
    _flatten: _flatten,
    _emitSvg: _emitSvg,
  };
}());
