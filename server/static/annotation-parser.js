/**
 * annotation-parser.js — WP-5.2
 *
 * Translates user annotations (authored on annotationLayer in WP-5.1) into
 * structured instruction JSON that the analytical pipeline can consume per
 * Implementation Specification §5.1.
 *
 * Exposed namespace: window.OraAnnotationParser.
 *
 *   OraAnnotationParser.parse(userAnnotations)   → {annotations: [...]}
 *   OraAnnotationParser.captureFromPanel(panel)  → {annotations: [...]} | {annotations: []}
 *
 * ── Input shape (from VisualPanel.getUserAnnotations() — WP-5.1) ─────────────
 *
 *   [{id, kind, targetId, text, position, points}, ...]
 *
 *   kind ∈ {'callout', 'highlight', 'strikethrough', 'sticky', 'pen'}
 *   targetId:  string (svg element id) | null
 *   text:      string | null
 *   position:  {x, y} | null
 *   points:    [[x,y], ...] | null (pen only)
 *
 * ── Output shape (pipeline instruction schema) ──────────────────────────────
 *
 *   {
 *     annotations: [
 *       {
 *         annotation_id: "ua-callout-3",
 *         kind: "callout"|"highlight"|"strikethrough"|"sticky"|"pen",
 *         action: "expand"|"add_relationship"|"remove"|"add_element"
 *               | "modify_cluster"|"suggest_cluster"|"note",
 *         target_id: "<svg-id>" | null,
 *         text: "<user text>" | "",
 *         position: [x, y] | null,
 *         points: [[x, y], ...] | null,
 *         warning: "<optional warning message>"        // only when degraded
 *       }
 *     ]
 *   }
 *
 * ── Mapping table (kind + targetId → action) ────────────────────────────────
 *
 *   callout + targetId        → "expand"              (detail on this element)
 *   callout + null target     → "note"                (free observation)
 *   highlight + targetId      → "expand"              (deeper analysis on elem)
 *   highlight + null target   → "note"   (WARN: free highlight is unusual)
 *   strikethrough + targetId  → "remove"              (edge/node flagged)
 *   strikethrough + null      → "note"   (WARN: free strikethrough = unusual)
 *   sticky                    → "add_element"         (always free; new concept)
 *   pen                       → "suggest_cluster"     (freehand circle heuristic)
 *
 * Pen is conservative — the model may ignore it. Documented here and in the
 * prompt-injection format so the analytical model knows not to over-commit.
 *
 * Order is preserved: output follows input array index exactly.
 */

(function () {
  'use strict';

  var KNOWN_KINDS = {
    callout:        true,
    highlight:      true,
    strikethrough:  true,
    sticky:         true,
    pen:            true,
  };

  /**
   * Normalize a position value from {x, y} or [x, y] into [x, y]. null-in
   * → null-out. Non-numeric components → null.
   */
  function _normalizePos(pos) {
    if (pos == null) return null;
    if (Array.isArray(pos) && pos.length === 2
        && typeof pos[0] === 'number' && typeof pos[1] === 'number') {
      return [pos[0], pos[1]];
    }
    if (typeof pos === 'object'
        && typeof pos.x === 'number' && typeof pos.y === 'number') {
      return [pos.x, pos.y];
    }
    return null;
  }

  /**
   * Normalize points to a flat [[x,y], ...] shape. Accepts:
   *   [[x, y], ...]                       — canonical
   *   [{x, y}, ...]                       — from Konva node attrs
   *   [x1, y1, x2, y2, ...]               — Konva.Line flat form
   */
  function _normalizePoints(points) {
    if (!Array.isArray(points) || points.length === 0) return null;
    var out = [];
    if (Array.isArray(points[0]) && points[0].length === 2) {
      // Already canonical shape
      for (var i = 0; i < points.length; i++) {
        var p = points[i];
        if (typeof p[0] === 'number' && typeof p[1] === 'number') {
          out.push([p[0], p[1]]);
        }
      }
    } else if (typeof points[0] === 'object' && points[0] != null
               && typeof points[0].x === 'number') {
      for (var j = 0; j < points.length; j++) {
        var pj = points[j];
        if (typeof pj.x === 'number' && typeof pj.y === 'number') {
          out.push([pj.x, pj.y]);
        }
      }
    } else if (typeof points[0] === 'number') {
      // Flat form: [x1, y1, x2, y2, ...]
      for (var k = 0; k + 1 < points.length; k += 2) {
        if (typeof points[k] === 'number' && typeof points[k + 1] === 'number') {
          out.push([points[k], points[k + 1]]);
        }
      }
    }
    return out.length > 0 ? out : null;
  }

  /**
   * Core mapping table — kind + targetId → action. Isolated so tests can
   * exercise the table directly and so the rationale stays visible in one
   * place.
   */
  function _mapAction(kind, targetId) {
    switch (kind) {
      case 'callout':
        return targetId ? 'expand' : 'note';
      case 'highlight':
        return targetId ? 'expand' : 'note';
      case 'strikethrough':
        // Strikethrough makes sense only when pointed at a specific element.
        // A free-position strikethrough degrades gracefully to a note with a
        // warning downstream.
        return targetId ? 'remove' : 'note';
      case 'sticky':
        // Sticky is always free-positioned (no target_id anchor) and proposes
        // a new concept to add to the diagram.
        return 'add_element';
      case 'pen':
        // Freehand pen stroke — conservative heuristic: "user circled these
        // nodes, maybe a grouping is implied." Pipeline is free to ignore.
        return 'suggest_cluster';
      default:
        return 'note';
    }
  }

  /**
   * Translate a list of user annotations into the pipeline instruction
   * schema. Pure function; no DOM access.
   *
   * @param {Array} userAnnotations - output of VisualPanel.getUserAnnotations()
   * @returns {{annotations: Array}}
   */
  function parse(userAnnotations) {
    if (!Array.isArray(userAnnotations)) return { annotations: [] };

    var out = [];
    for (var i = 0; i < userAnnotations.length; i++) {
      var src = userAnnotations[i];
      if (!src || typeof src !== 'object') continue;
      var kind = src.kind;
      if (!KNOWN_KINDS[kind]) continue;   // silently drop unknown kinds

      var targetId = (typeof src.targetId === 'string' && src.targetId)
                   ? src.targetId : null;
      var action = _mapAction(kind, targetId);

      var record = {
        annotation_id: (typeof src.id === 'string' && src.id)
                        ? src.id : ('ua-' + kind + '-' + i),
        kind:       kind,
        action:     action,
        target_id:  targetId,
        text:       (typeof src.text === 'string') ? src.text : '',
        position:   _normalizePos(src.position),
        points:     _normalizePoints(src.points),
      };

      // Attach warnings for degraded mappings (strikethrough/highlight on a
      // null target were downgraded to "note"; downstream model sees the
      // context and can handle it but knows the authoring was unusual).
      if (kind === 'strikethrough' && !targetId) {
        record.warning = 'free-position strikethrough: no target to remove; '
                       + 'treating as note';
      } else if (kind === 'highlight' && !targetId) {
        record.warning = 'free-position highlight: no target to emphasize; '
                       + 'treating as note';
      }

      out.push(record);
    }
    return { annotations: out };
  }

  /**
   * Pull user annotations off a mounted VisualPanel instance and parse them.
   * Safe against missing panels / missing API — returns
   * {annotations: []} on any shape mismatch.
   *
   * @param {VisualPanel|null} panel
   * @returns {{annotations: Array}}
   */
  function captureFromPanel(panel) {
    if (!panel) return { annotations: [] };
    if (typeof panel.getUserAnnotations !== 'function') return { annotations: [] };
    var raw;
    try {
      raw = panel.getUserAnnotations();
    } catch (e) {
      try { console.warn('[annotation-parser] getUserAnnotations threw:', e); }
      catch (e2) {}
      return { annotations: [] };
    }
    return parse(raw);
  }

  // Expose on window under a stable namespace. Defensive re-export so
  // loaders that run multiple times don't clobber prior state.
  var api = {
    parse:            parse,
    captureFromPanel: captureFromPanel,
    _mapAction:       _mapAction,   // exposed for testing; underscored = private
    _normalizePos:    _normalizePos,
    _normalizePoints: _normalizePoints,
    KNOWN_KINDS:      KNOWN_KINDS,
  };

  if (typeof window !== 'undefined') {
    window.OraAnnotationParser = api;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})();
