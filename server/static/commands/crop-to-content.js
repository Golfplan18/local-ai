/**
 * crop-to-content.js — WP-7.4.2a
 *
 * Implements the **Crop to content** workspace command per Visual Intelligence
 * Implementation Plan §11.7 ("Canvas Mechanics — Crop to content") and §13.4
 * WP-7.4.2 (sub-WP a).
 *
 *   Photoshop equivalent:  Image → Trim
 *
 * Auto-shrink the canvas to the union bounding box of every drawable across
 * all four layers, plus a configurable margin (default 100 px). All objects
 * are translated so their relative alignment is preserved — the artifact that
 * sat at (5000, 5200) on a 10000×10000 canvas with a 200-px margin sits at
 * (200, 200) on the new tight canvas. The canvas-state metadata is updated so
 * subsequent saves emit the new size.
 *
 * Distinct from WP-7.4.2b (crop-to-selection): that command crops to a
 * user-drawn rectangle (potentially smaller than the content); this one is
 * the auto-shrink that bounds the content with a margin.
 *
 * ── Architecture ────────────────────────────────────────────────────────────
 *
 * Self-registering IIFE that lives alongside `resize-canvas.js`. Reuses
 * `OraResizeCanvas.computeBoundingBox`, `_translateLayers`, `_setCanvasSize`,
 * and `getCurrentSize` so the geometry/translation/state-mutation primitives
 * stay in one place. If `OraResizeCanvas` is not yet loaded, the module
 * inlines the same primitives (defensive — both modules typically load
 * together via the universal toolbar wiring).
 *
 * It does NOT depend on:
 *   - WP-7.4.2b (crop-to-selection) — separate command, separate module.
 *   - WP-7.4.4 (pan/zoom shortcuts) — viewport transform is preserved.
 *
 * It DOES depend on:
 *   - WP-7.0.2 (canvas-file-format.js) — `metadata.canvas_size` schema.
 *   - WP-7.4.1 (resize-canvas.js)      — shared geometry/translation helpers.
 *
 * ── Public surface — exposed as `window.OraCropToContent` ──────────────────
 *
 *   DEFAULT_MARGIN = 100   // px, per Plan §11.7
 *   MIN_DIMENSION  = 1     // px; canvas_size schema requires > 0
 *
 *   apply(panel, opts) → { changed, prior, next, translation, bbox, margin,
 *                          nodes_translated, classification }
 *     Compute the union bbox, derive next dimensions = bbox + 2 × margin,
 *     translate every object by (-bbox.x + margin, -bbox.y + margin), and
 *     update canvas-state metadata. Returns a result envelope identical in
 *     shape to OraResizeCanvas.apply() (minus cropping fields — this
 *     command never crops content; it shrinks the frame around it).
 *
 *     `opts` shape (all optional):
 *       {
 *         margin: number,           // px, default 100; clamped to >= 0
 *         min_width:  number,       // px, default MIN_DIMENSION
 *         min_height: number,       // px, default MIN_DIMENSION
 *       }
 *
 *     Throws if the panel has no content (no objects across all four layers).
 *     Caller is expected to gate the toolbar button via the existing
 *     `enabled_when: "canvas_has_content"` predicate in universal.toolbar.json.
 *
 *   computeNext(bbox, opts) → { width, height, dx, dy }
 *     Pure helper. Given a union bbox and margin/min options, returns the
 *     next canvas dimensions and the (dx, dy) translation that should be
 *     applied to every existing object.
 *
 * ── Konva-side translation invariant ────────────────────────────────────────
 *
 * Every node in the four layers gets its (x, y) shifted by (dx, dy) — once.
 * The sentinel group on backgroundLayer is exempt (it carries no rendered
 * SVG; the SVG lives in the DOM overlay). The DOM SVG overlay itself is NOT
 * translated — its position is governed by `_applyTransform()` (the viewport
 * transform), which is preserved.
 *
 * The user-shape-preview node (in-flight draw) is also exempt; cropping
 * during a draw would otherwise stomp the in-progress shape.
 *
 * ── Test criterion (per §13.4) ──────────────────────────────────────────────
 *
 *   "Scattered objects on a 10000×10000 canvas; crop-to-content shrinks to
 *    bbox+margin with objects intact."
 *
 *   The acceptance test verifies:
 *     1. Next canvas size equals bbox dimensions + 2 × margin.
 *     2. Every object's stage-local position is shifted by (-bbox.x + margin,
 *        -bbox.y + margin), preserving relative alignment within ε = 1e-6.
 *     3. `panel._canvasState.metadata.canvas_size` is updated to the new
 *        dimensions.
 *     4. No object falls outside the new bounds (will_crop = false by
 *        construction; tightening the frame around content cannot crop it).
 */

(function (root) {
  'use strict';

  // ── Constants ─────────────────────────────────────────────────────────────

  var DEFAULT_MARGIN = 100;   // px, per Plan §11.7
  var MIN_DIMENSION  = 1;     // canvas_size schema requires > 0

  // ── Type guards ───────────────────────────────────────────────────────────

  function _isObj(v)            { return v !== null && typeof v === 'object' && !Array.isArray(v); }
  function _isFiniteNumber(v)   { return typeof v === 'number' && isFinite(v); }
  function _isPositiveNumber(v) { return _isFiniteNumber(v) && v > 0; }
  function _isNonNegNumber(v)   { return _isFiniteNumber(v) && v >= 0; }

  // ── Resolved helpers (prefer OraResizeCanvas; inline fallbacks) ──────────

  function _resize() {
    return (typeof window !== 'undefined' && window.OraResizeCanvas) || null;
  }

  /**
   * Walk the four Konva layers and return the union of every drawable's
   * stage-local getClientRect(). Delegates to OraResizeCanvas when present.
   *
   * Returns:
   *   {
   *     union: { x, y, width, height } | null,
   *     boxes: [{ id, layer, x, y, width, height }, ...]
   *   }
   */
  function computeBoundingBox(panel) {
    var rc = _resize();
    if (rc && typeof rc.computeBoundingBox === 'function') {
      return rc.computeBoundingBox(panel);
    }
    // ── Inline fallback (matches resize-canvas.js exactly) ───────────────
    if (!panel) return { union: null, boxes: [] };
    var layerNames = ['backgroundLayer', 'annotationLayer', 'userInputLayer', 'selectionLayer'];
    var boxes = [];
    var minX =  Infinity, minY =  Infinity;
    var maxX = -Infinity, maxY = -Infinity;
    for (var li = 0; li < layerNames.length; li++) {
      var lname = layerNames[li];
      var layer = panel[lname];
      if (!layer || typeof layer.getChildren !== 'function') continue;
      var children = layer.getChildren();
      for (var ci = 0; ci < children.length; ci++) {
        var node = children[ci];
        if (!node) continue;
        if (node.getAttr && node.getAttr('name') === 'svg-sentinel') continue;
        var rect;
        try {
          rect = node.getClientRect ? node.getClientRect({ relativeTo: layer }) : null;
        } catch (e) { rect = null; }
        if (!rect) continue;
        if (rect.width <= 0 && rect.height <= 0) continue;
        var idGuess = (node.getAttr && (
          node.getAttr('userShapeId') ||
          node.getAttr('userAnnotationId') ||
          node.id && node.id()
        )) || ('node-' + lname + '-' + ci);
        var entry = {
          id:     String(idGuess),
          layer:  lname,
          x:      rect.x,
          y:      rect.y,
          width:  rect.width,
          height: rect.height,
        };
        boxes.push(entry);
        if (entry.x < minX) minX = entry.x;
        if (entry.y < minY) minY = entry.y;
        if (entry.x + entry.width  > maxX) maxX = entry.x + entry.width;
        if (entry.y + entry.height > maxY) maxY = entry.y + entry.height;
      }
    }
    var union = boxes.length === 0
      ? null
      : { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
    return { union: union, boxes: boxes };
  }

  /**
   * Apply (dx, dy) to every direct child of the four layers. Delegates to
   * OraResizeCanvas._translateLayers when present, falls back to inline
   * walker otherwise. Returns the count of nodes translated.
   */
  function _translateLayers(panel, dx, dy) {
    var rc = _resize();
    if (rc && typeof rc._translateLayers === 'function') {
      return rc._translateLayers(panel, dx, dy);
    }
    if (!panel || (dx === 0 && dy === 0)) return 0;
    var layerNames = ['backgroundLayer', 'annotationLayer', 'userInputLayer', 'selectionLayer'];
    var moved = 0;
    for (var li = 0; li < layerNames.length; li++) {
      var layer = panel[layerNames[li]];
      if (!layer || typeof layer.getChildren !== 'function') continue;
      var children = layer.getChildren();
      for (var ci = 0; ci < children.length; ci++) {
        var node = children[ci]; if (!node) continue;
        if (node.getAttr && node.getAttr('name') === 'svg-sentinel') continue;
        if (node.getAttr && node.getAttr('name') === 'user-shape-preview') continue;
        var px = (typeof node.x === 'function') ? node.x() : (node.attrs && node.attrs.x) || 0;
        var py = (typeof node.y === 'function') ? node.y() : (node.attrs && node.attrs.y) || 0;
        if (typeof node.x === 'function') node.x(px + dx);
        if (typeof node.y === 'function') node.y(py + dy);
        moved++;
      }
      try { if (typeof layer.batchDraw === 'function') layer.batchDraw(); } catch (e) { /* ignore */ }
    }
    return moved;
  }

  /**
   * Update / create canvas-state metadata.canvas_size. Delegates to
   * OraResizeCanvas._setCanvasSize when present.
   */
  function _setCanvasSize(panel, next) {
    var rc = _resize();
    if (rc && typeof rc._setCanvasSize === 'function') {
      return rc._setCanvasSize(panel, next);
    }
    if (!panel) return;
    var fmt = (typeof window !== 'undefined' && window.OraCanvasFileFormat) || null;
    if (!_isObj(panel._canvasState)) {
      if (fmt && typeof fmt.newCanvasState === 'function') {
        panel._canvasState = fmt.newCanvasState({ canvas_size: { width: next.width, height: next.height } });
      } else {
        panel._canvasState = {
          schema_version: '0.1.0',
          format_id:      'ora-canvas',
          metadata:       { canvas_size: { width: next.width, height: next.height } },
          view:           { zoom: 1, pan: { x: 0, y: 0 } },
          layers:         [],
          objects:        [],
        };
      }
    } else {
      if (!_isObj(panel._canvasState.metadata)) panel._canvasState.metadata = {};
      panel._canvasState.metadata.canvas_size = { width: next.width, height: next.height };
      panel._canvasState.metadata.modified_at = (new Date()).toISOString();
    }
    panel._priorCanvasSize = { width: next.width, height: next.height };
  }

  /**
   * Read current canvas size. Delegates to OraResizeCanvas.getCurrentSize when
   * present; otherwise falls back to the canvas-file-format defaults.
   */
  function getCurrentSize(panel) {
    var rc = _resize();
    if (rc && typeof rc.getCurrentSize === 'function') {
      return rc.getCurrentSize(panel);
    }
    if (panel && _isObj(panel._canvasState)
            && _isObj(panel._canvasState.metadata)
            && _isObj(panel._canvasState.metadata.canvas_size)) {
      var cs = panel._canvasState.metadata.canvas_size;
      if (_isPositiveNumber(cs.width) && _isPositiveNumber(cs.height)) {
        return { width: cs.width, height: cs.height };
      }
    }
    if (panel && _isObj(panel._priorCanvasSize)
            && _isPositiveNumber(panel._priorCanvasSize.width)
            && _isPositiveNumber(panel._priorCanvasSize.height)) {
      return { width: panel._priorCanvasSize.width, height: panel._priorCanvasSize.height };
    }
    var fmt = (typeof window !== 'undefined' && window.OraCanvasFileFormat) || null;
    if (fmt && _isPositiveNumber(fmt.DEFAULT_CANVAS_W) && _isPositiveNumber(fmt.DEFAULT_CANVAS_H)) {
      return { width: fmt.DEFAULT_CANVAS_W, height: fmt.DEFAULT_CANVAS_H };
    }
    return { width: 10000, height: 10000 };
  }

  // ── Pure geometry helper ─────────────────────────────────────────────────

  /**
   * Given the union bounding box of all content and an options object,
   * compute the next canvas dimensions and the (dx, dy) translation that
   * should be applied to every existing object.
   *
   *   bbox = { x, y, width, height }     // stage-local; from computeBoundingBox().union
   *   opts = { margin, min_width, min_height }
   *
   * Returns:
   *   { width, height, dx, dy }
   *
   * Geometry:
   *   - Next width  = max(bbox.width  + 2*margin, min_width)
   *   - Next height = max(bbox.height + 2*margin, min_height)
   *   - dx = -bbox.x + margin   (shifts content's left edge to x = margin)
   *   - dy = -bbox.y + margin   (shifts content's top  edge to y = margin)
   *
   * The translation is independent of the min-dimension clamp: even if the
   * content is small enough that the clamp expands the canvas, the content
   * is still pinned at (margin, margin), leaving extra space on the right/
   * bottom edges. This matches Photoshop's Trim behavior.
   */
  function computeNext(bbox, opts) {
    if (!_isObj(bbox)) throw new Error('crop-to-content: bbox object required');
    if (!_isFiniteNumber(bbox.x) || !_isFiniteNumber(bbox.y)) {
      throw new Error('crop-to-content: bbox.x/y must be finite numbers');
    }
    if (!_isNonNegNumber(bbox.width) || !_isNonNegNumber(bbox.height)) {
      throw new Error('crop-to-content: bbox.width/height must be non-negative numbers');
    }
    opts = _isObj(opts) ? opts : {};
    var margin = _isNonNegNumber(opts.margin) ? opts.margin : DEFAULT_MARGIN;
    var minW   = _isPositiveNumber(opts.min_width)  ? opts.min_width  : MIN_DIMENSION;
    var minH   = _isPositiveNumber(opts.min_height) ? opts.min_height : MIN_DIMENSION;
    var width  = Math.max(bbox.width  + 2 * margin, minW);
    var height = Math.max(bbox.height + 2 * margin, minH);
    return {
      width:  width,
      height: height,
      dx:     -bbox.x + margin,
      dy:     -bbox.y + margin,
    };
  }

  // ── Public command API ───────────────────────────────────────────────────

  /**
   * Apply crop-to-content. See module header for full contract.
   */
  function apply(panel, opts) {
    opts = _isObj(opts) ? opts : {};
    var prior = getCurrentSize(panel);
    var bb    = computeBoundingBox(panel);
    if (!bb.union) {
      var err = new Error('crop-to-content: panel has no content; nothing to crop to.');
      err.code = 'E_NO_CONTENT';
      throw err;
    }
    var nxt   = computeNext(bb.union, opts);
    var next  = { width: nxt.width, height: nxt.height };
    var moved = _translateLayers(panel, nxt.dx, nxt.dy);
    _setCanvasSize(panel, next);
    var changed = (prior.width !== next.width)
               || (prior.height !== next.height)
               || (nxt.dx !== 0)
               || (nxt.dy !== 0)
               || moved > 0;
    var classification;
    if (next.width === prior.width && next.height === prior.height) classification = 'unchanged';
    else if (next.width <= prior.width && next.height <= prior.height) classification = 'shrink';
    else if (next.width >= prior.width && next.height >= prior.height) classification = 'enlarge';
    else classification = 'mixed';
    return {
      changed:          changed,
      prior:            prior,
      next:             next,
      translation:      { dx: nxt.dx, dy: nxt.dy },
      bbox:             { x: bb.union.x, y: bb.union.y, width: bb.union.width, height: bb.union.height },
      margin:           _isNonNegNumber(opts.margin) ? opts.margin : DEFAULT_MARGIN,
      nodes_translated: moved,
      classification:   classification,
      object_count:     bb.boxes.length,
    };
  }

  // ── Module export ────────────────────────────────────────────────────────

  var ns = {
    DEFAULT_MARGIN:     DEFAULT_MARGIN,
    MIN_DIMENSION:      MIN_DIMENSION,
    apply:              apply,
    computeNext:        computeNext,
    computeBoundingBox: computeBoundingBox,
    getCurrentSize:     getCurrentSize,
    // Internals exposed for tests.
    _translateLayers:   _translateLayers,
    _setCanvasSize:     _setCanvasSize,
  };

  if (typeof window !== 'undefined') {
    window.OraCropToContent = ns;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = ns;
  }
})(typeof window !== 'undefined' ? window : this);
