/**
 * crop-to-selection.js — WP-7.4.2b
 *
 * Implements the **Crop to selection** workspace command per Visual Intelligence
 * Implementation Plan §11.7 ("Canvas Mechanics — Crop to selection") and §13.4
 * WP-7.4.2 (sub-WP b).
 *
 *   Photoshop equivalent:  Image → Crop (with marquee active)
 *
 * The user draws a rectangle on the canvas with the rect-selection tool
 * (WP-7.5.1a), then invokes this command. The rectangle becomes the new
 * canvas bounds: every drawable whose stage-local bbox falls fully outside
 * the rectangle is permanently discarded (with a confirmation prompt), every
 * surviving drawable is translated so the rectangle's top-left lands at
 * (0, 0), and `metadata.canvas_size` is set to the rectangle dimensions.
 *
 * Distinct from WP-7.4.2a (crop-to-content): that command auto-shrinks the
 * canvas to the union bounding box of all content (plus a margin) and never
 * discards anything. This command honours the user's hand-drawn rectangle
 * and IS destructive — anything outside the rectangle is gone.
 *
 * ── Architecture ────────────────────────────────────────────────────────────
 *
 * Self-registering IIFE that lives alongside `resize-canvas.js` and
 * `crop-to-content.js`. Reuses `OraResizeCanvas.computeBoundingBox`,
 * `_translateLayers`, `_setCanvasSize`, and `getCurrentSize` so the
 * geometry/translation/state-mutation primitives stay in one place. If
 * `OraResizeCanvas` is not yet loaded (defensive — the universal toolbar
 * wiring loads them together), inline fallbacks mirror the same logic.
 *
 * Rectangle resolution order (first hit wins):
 *   1. `opts.rect`                                 — explicit caller rect
 *   2. `panel._cropToSelectionRect`                — caller-deposited rect
 *   3. `panel._rectSelectionTool._committedRect`   — the marching-ants Konva.Rect
 *   4. Throws E_NO_SELECTION                       — no rectangle available
 *
 * The rectangle is interpreted in stage-local coordinates, matching the
 * coordinate system used by `computeBoundingBox`. Negative widths/heights
 * are normalised. Rectangles smaller than `MIN_DIMENSION` on either side are
 * rejected with E_DEGENERATE_RECT.
 *
 * It does NOT depend on:
 *   - WP-7.4.4 (pan/zoom shortcuts) — viewport transform is preserved.
 *   - WP-7.4.5 (zoom-to-extents) — independent.
 *
 * It DOES depend on:
 *   - WP-7.0.2 (canvas-file-format.js)  — `metadata.canvas_size` schema.
 *   - WP-7.4.1 (resize-canvas.js)       — shared geometry/translation helpers.
 *   - WP-7.5.1a (rect-selection.tool.js) — source of the user-drawn rectangle.
 *
 * ── Public surface — exposed as `window.OraCropToSelection` ────────────────
 *
 *   MIN_DIMENSION = 1   // px; canvas_size schema requires > 0
 *
 *   apply(panel, opts) → {
 *     changed, prior, next, translation, rect,
 *     discarded_ids, discarded_count, kept_count,
 *     classification
 *   }
 *     Resolve the rectangle, classify every object as inside/outside, prompt
 *     for destructive confirmation when objects would be discarded, destroy
 *     the outside objects, translate the survivors so the rect's top-left
 *     lands at (0, 0), and update canvas-state metadata to the rect's
 *     dimensions.
 *
 *     `opts` shape (all optional):
 *       {
 *         rect:         { x, y, width, height }, // stage-local; overrides panel state
 *         confirm:      boolean,                 // pre-supplied destruction confirmation
 *         confirmFn:    function(count) → bool,  // injectable confirm() (test-friendly)
 *         min_width:    number,                  // px, default MIN_DIMENSION
 *         min_height:   number,                  // px, default MIN_DIMENSION
 *       }
 *
 *     Throws:
 *       - E_NO_SELECTION     — no rectangle could be resolved
 *       - E_DEGENERATE_RECT  — rect width or height < min dimension
 *       - E_NOT_CONFIRMED    — discards needed and confirmation withheld
 *
 *   computeOutsideObjects(boxes, rect) → { outside_ids, kept_ids }
 *     Pure helper. Given a list of per-object boxes (from
 *     computeBoundingBox().boxes) and a normalised rect, returns the ids
 *     that fall fully outside the rectangle (and would therefore be
 *     discarded). Boxes that overlap the rectangle's edge are KEPT — only
 *     fully-outside boxes are discarded, mirroring Photoshop's marquee crop.
 *
 *   normaliseRect(rect) → { x, y, width, height }
 *     Pure helper. Normalises negative widths/heights and rounds to finite
 *     numbers. Throws on non-finite input.
 *
 * ── Konva-side translation invariant ────────────────────────────────────────
 *
 * Surviving nodes get their (x, y) shifted by (-rect.x, -rect.y) — once. The
 * sentinel group on backgroundLayer and the user-shape-preview node are
 * exempt (same exemptions as WP-7.4.1 / WP-7.4.2a). Discarded nodes are
 * destroyed via Konva's `destroy()` so their listeners and tweens are
 * collected. The DOM SVG overlay is NOT translated — the viewport transform
 * (`_applyTransform()`) governs that and is preserved.
 *
 * ── Test criterion (per §13.4) ──────────────────────────────────────────────
 *
 *   "Draw rectangle around 3 of 5 objects; run command; verify 2 objects
 *    discarded after confirmation, canvas matches rectangle."
 *
 *   The acceptance test verifies:
 *     1. Next canvas size equals rect dimensions (within ε = 1e-6).
 *     2. Surviving object count equals N(inside the rect); discarded count
 *        equals N(fully outside the rect).
 *     3. Every surviving object's stage-local position is shifted by
 *        (-rect.x, -rect.y); the rect's top-left maps to (0, 0).
 *     4. `panel._canvasState.metadata.canvas_size` equals the rect dimensions.
 *     5. confirmFn returning false aborts the destructive path with
 *        E_NOT_CONFIRMED and leaves the panel untouched.
 */

(function (root) {
  'use strict';

  // ── Constants ─────────────────────────────────────────────────────────────

  var MIN_DIMENSION = 1;   // canvas_size schema requires > 0

  // ── Type guards ───────────────────────────────────────────────────────────

  function _isObj(v)            { return v !== null && typeof v === 'object' && !Array.isArray(v); }
  function _isFiniteNumber(v)   { return typeof v === 'number' && isFinite(v); }
  function _isPositiveNumber(v) { return _isFiniteNumber(v) && v > 0; }

  // ── Resolved helpers (prefer OraResizeCanvas; fall back to OraCropToContent
  //    or inline) ──────────────────────────────────────────────────────────

  function _resize() {
    return (typeof window !== 'undefined' && window.OraResizeCanvas) || null;
  }
  function _cropToContent() {
    return (typeof window !== 'undefined' && window.OraCropToContent) || null;
  }

  /**
   * Walk the four Konva layers and return the union bbox + per-object boxes.
   * Delegates to OraResizeCanvas / OraCropToContent when present, falls back
   * to an inline walker that matches their behaviour exactly.
   */
  function computeBoundingBox(panel) {
    var rc = _resize();
    if (rc && typeof rc.computeBoundingBox === 'function') {
      return rc.computeBoundingBox(panel);
    }
    var cc = _cropToContent();
    if (cc && typeof cc.computeBoundingBox === 'function') {
      return cc.computeBoundingBox(panel);
    }
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
        var node = children[ci]; if (!node) continue;
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

  /** Translate every direct child of the four layers by (dx, dy). */
  function _translateLayers(panel, dx, dy) {
    var rc = _resize();
    if (rc && typeof rc._translateLayers === 'function') {
      return rc._translateLayers(panel, dx, dy);
    }
    var cc = _cropToContent();
    if (cc && typeof cc._translateLayers === 'function') {
      return cc._translateLayers(panel, dx, dy);
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

  /** Update / create canvas-state metadata.canvas_size. */
  function _setCanvasSize(panel, next) {
    var rc = _resize();
    if (rc && typeof rc._setCanvasSize === 'function') {
      return rc._setCanvasSize(panel, next);
    }
    var cc = _cropToContent();
    if (cc && typeof cc._setCanvasSize === 'function') {
      return cc._setCanvasSize(panel, next);
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

  /** Read current canvas size. */
  function getCurrentSize(panel) {
    var rc = _resize();
    if (rc && typeof rc.getCurrentSize === 'function') {
      return rc.getCurrentSize(panel);
    }
    var cc = _cropToContent();
    if (cc && typeof cc.getCurrentSize === 'function') {
      return cc.getCurrentSize(panel);
    }
    if (panel && _isObj(panel._canvasState)
            && _isObj(panel._canvasState.metadata)
            && _isObj(panel._canvasState.metadata.canvas_size)) {
      var cs = panel._canvasState.metadata.canvas_size;
      if (_isPositiveNumber(cs.width) && _isPositiveNumber(cs.height)) {
        return { width: cs.width, height: cs.height };
      }
    }
    var fmt = (typeof window !== 'undefined' && window.OraCanvasFileFormat) || null;
    if (fmt && _isPositiveNumber(fmt.DEFAULT_CANVAS_W) && _isPositiveNumber(fmt.DEFAULT_CANVAS_H)) {
      return { width: fmt.DEFAULT_CANVAS_W, height: fmt.DEFAULT_CANVAS_H };
    }
    return { width: 10000, height: 10000 };
  }

  // ── Pure geometry helpers ─────────────────────────────────────────────────

  /**
   * Normalise a rect: convert negative widths/heights to positive, with the
   * top-left corner adjusted accordingly. Throws if x/y/width/height are
   * non-finite.
   */
  function normaliseRect(rect) {
    if (!_isObj(rect)) {
      var err = new Error('crop-to-selection: rect object required');
      err.code = 'E_BAD_RECT';
      throw err;
    }
    if (!_isFiniteNumber(rect.x) || !_isFiniteNumber(rect.y)
        || !_isFiniteNumber(rect.width) || !_isFiniteNumber(rect.height)) {
      var err2 = new Error('crop-to-selection: rect.x/y/width/height must be finite numbers');
      err2.code = 'E_BAD_RECT';
      throw err2;
    }
    var x = Math.min(rect.x, rect.x + rect.width);
    var y = Math.min(rect.y, rect.y + rect.height);
    var w = Math.abs(rect.width);
    var h = Math.abs(rect.height);
    return { x: x, y: y, width: w, height: h };
  }

  /**
   * Partition the per-object boxes by inside/outside the (normalised) rect.
   *
   *   - "outside" = the box lies fully outside the rect on at least one
   *                 side. These are discarded.
   *   - "inside"  = the box lies fully inside OR overlaps the rect's edge.
   *                 These are kept and translated.
   *
   * Mirrors Photoshop's marquee crop: anything touching the rectangle
   * survives (clipping at the new edges is handled by the canvas frame, not
   * by destroying the object).
   */
  function computeOutsideObjects(boxes, rect) {
    var r = normaliseRect(rect);
    var outsideIds = [];
    var keptIds    = [];
    if (!Array.isArray(boxes)) return { outside_ids: outsideIds, kept_ids: keptIds };
    var rx0 = r.x;
    var ry0 = r.y;
    var rx1 = r.x + r.width;
    var ry1 = r.y + r.height;
    for (var i = 0; i < boxes.length; i++) {
      var b = boxes[i]; if (!b) continue;
      var bx0 = b.x;
      var by0 = b.y;
      var bx1 = b.x + b.width;
      var by1 = b.y + b.height;
      // Fully outside iff the box's AABB does not intersect the rect AABB.
      var disjoint = (bx1 <= rx0) || (bx0 >= rx1) || (by1 <= ry0) || (by0 >= ry1);
      if (disjoint) outsideIds.push(b.id);
      else          keptIds.push(b.id);
    }
    return { outside_ids: outsideIds, kept_ids: keptIds };
  }

  // ── Rectangle resolution ──────────────────────────────────────────────────

  /**
   * Resolve the selection rectangle from caller opts → panel state →
   * rect-selection tool's committed Konva.Rect. Returns the (un-normalised)
   * stage-space rect, or null if no source produced one.
   */
  function _resolveRect(panel, opts) {
    if (_isObj(opts) && _isObj(opts.rect)) return opts.rect;
    if (panel && _isObj(panel._cropToSelectionRect)) return panel._cropToSelectionRect;
    // The rect-selection tool stashes its committed Konva.Rect on the tool
    // instance. visual-panel.js mounts the tool and exposes it via
    // panel._tools[id].instance — defensive walkthrough:
    var tool = null;
    if (panel && _isObj(panel._rectSelectionTool)) {
      tool = panel._rectSelectionTool;
    } else if (panel && _isObj(panel._tools) && _isObj(panel._tools['rect-selection'])) {
      tool = panel._tools['rect-selection'].instance || panel._tools['rect-selection'];
    }
    if (tool && tool._committedRect) {
      var k = tool._committedRect;
      var x = (typeof k.x === 'function') ? k.x() : (k.attrs && k.attrs.x);
      var y = (typeof k.y === 'function') ? k.y() : (k.attrs && k.attrs.y);
      var w = (typeof k.width  === 'function') ? k.width()  : (k.attrs && k.attrs.width);
      var h = (typeof k.height === 'function') ? k.height() : (k.attrs && k.attrs.height);
      if (_isFiniteNumber(x) && _isFiniteNumber(y) && _isFiniteNumber(w) && _isFiniteNumber(h)) {
        return { x: x, y: y, width: w, height: h };
      }
    }
    return null;
  }

  /**
   * Destroy a list of Konva nodes by id, walking the four layers. Returns
   * the count of nodes actually destroyed (may be less than ids.length if
   * some ids did not match — defensive against id collisions).
   */
  function _destroyNodesByIds(panel, ids) {
    if (!panel || !Array.isArray(ids) || ids.length === 0) return 0;
    var idSet = {};
    for (var k = 0; k < ids.length; k++) idSet[String(ids[k])] = true;
    var layerNames = ['backgroundLayer', 'annotationLayer', 'userInputLayer', 'selectionLayer'];
    var destroyed = 0;
    for (var li = 0; li < layerNames.length; li++) {
      var lname = layerNames[li];
      var layer = panel[lname];
      if (!layer || typeof layer.getChildren !== 'function') continue;
      // Snapshot the children list — destroy() mutates getChildren() in-place.
      var children = layer.getChildren().slice();
      for (var ci = 0; ci < children.length; ci++) {
        var node = children[ci]; if (!node) continue;
        if (node.getAttr && node.getAttr('name') === 'svg-sentinel') continue;
        if (node.getAttr && node.getAttr('name') === 'user-shape-preview') continue;
        var idGuess = (node.getAttr && (
          node.getAttr('userShapeId') ||
          node.getAttr('userAnnotationId') ||
          node.id && node.id()
        )) || ('node-' + lname + '-' + ci);
        if (idSet[String(idGuess)] && typeof node.destroy === 'function') {
          try { node.destroy(); destroyed++; } catch (e) { /* ignore */ }
        }
      }
      try { if (typeof layer.batchDraw === 'function') layer.batchDraw(); } catch (e) { /* ignore */ }
    }
    return destroyed;
  }

  // ── Public command API ───────────────────────────────────────────────────

  /**
   * Apply crop-to-selection. See module header for full contract.
   */
  function apply(panel, opts) {
    opts = _isObj(opts) ? opts : {};

    // 1. Resolve the rectangle.
    var raw = _resolveRect(panel, opts);
    if (!raw) {
      var e1 = new Error('crop-to-selection: no selection rectangle available; '
                       + 'draw a rectangle with the rect-selection tool first.');
      e1.code = 'E_NO_SELECTION';
      throw e1;
    }
    var rect = normaliseRect(raw);
    var minW = _isPositiveNumber(opts.min_width)  ? opts.min_width  : MIN_DIMENSION;
    var minH = _isPositiveNumber(opts.min_height) ? opts.min_height : MIN_DIMENSION;
    if (rect.width < minW || rect.height < minH) {
      var e2 = new Error('crop-to-selection: rectangle is degenerate (' + rect.width
                       + '×' + rect.height + ' < ' + minW + '×' + minH + ').');
      e2.code = 'E_DEGENERATE_RECT';
      throw e2;
    }

    // 2. Snapshot prior state and classify objects.
    var prior   = getCurrentSize(panel);
    var bb      = computeBoundingBox(panel);
    var split   = computeOutsideObjects(bb.boxes, rect);
    var discard = split.outside_ids;
    var keep    = split.kept_ids;

    // 3. Confirmation flow — only required if discards would happen.
    if (discard.length > 0) {
      var confirmed = (opts.confirm === true);
      if (!confirmed) {
        var confirmFn = (typeof opts.confirmFn === 'function')
          ? opts.confirmFn
          : (function (count) {
              var msg = 'This will permanently discard ' + count
                      + ' object' + (count === 1 ? '' : 's')
                      + ' outside the selection. Continue?';
              if (typeof window !== 'undefined' && typeof window.confirm === 'function') {
                return window.confirm(msg);
              }
              // Headless contexts have no UI; treat absence of confirmFn as a
              // hard refusal so destructive ops never silently proceed.
              return false;
            });
        confirmed = !!confirmFn(discard.length);
      }
      if (!confirmed) {
        var e3 = new Error('crop-to-selection: destruction not confirmed; '
                         + discard.length + ' object(s) would be discarded.');
        e3.code = 'E_NOT_CONFIRMED';
        e3.discarded_ids = discard.slice();
        throw e3;
      }
    }

    // 4. Destroy outside objects.
    var destroyed = _destroyNodesByIds(panel, discard);

    // 5. Translate survivors so rect's top-left lands at (0, 0).
    var dx = -rect.x;
    var dy = -rect.y;
    var moved = _translateLayers(panel, dx, dy);

    // 6. Set the new canvas size.
    var next = { width: rect.width, height: rect.height };
    _setCanvasSize(panel, next);

    // 7. Clear any lingering selection visuals — the rectangle's frame is
    //    now the canvas frame; the marching ants would be misleading.
    if (panel && _isObj(panel._rectSelectionTool)
            && typeof panel._rectSelectionTool.clearSelection === 'function') {
      try { panel._rectSelectionTool.clearSelection(); } catch (e) { /* ignore */ }
    }
    if (panel && _isObj(panel._cropToSelectionRect)) panel._cropToSelectionRect = null;

    // 8. Classify the dimension change for parity with WP-7.4.1 / WP-7.4.2a.
    var classification;
    if (next.width === prior.width && next.height === prior.height)            classification = 'unchanged';
    else if (next.width <= prior.width && next.height <= prior.height)         classification = 'shrink';
    else if (next.width >= prior.width && next.height >= prior.height)         classification = 'enlarge';
    else                                                                       classification = 'mixed';

    var changed = (prior.width !== next.width)
               || (prior.height !== next.height)
               || (dx !== 0)
               || (dy !== 0)
               || destroyed > 0
               || moved > 0;

    return {
      changed:          changed,
      prior:            prior,
      next:             next,
      translation:      { dx: dx, dy: dy },
      rect:             rect,
      discarded_ids:    discard,
      discarded_count:  destroyed,
      kept_ids:         keep,
      kept_count:       keep.length,
      nodes_translated: moved,
      classification:   classification,
      object_count:     bb.boxes.length,
    };
  }

  // ── Module export ────────────────────────────────────────────────────────

  var ns = {
    MIN_DIMENSION:        MIN_DIMENSION,
    apply:                apply,
    computeOutsideObjects: computeOutsideObjects,
    normaliseRect:        normaliseRect,
    computeBoundingBox:   computeBoundingBox,
    getCurrentSize:       getCurrentSize,
    // Internals exposed for tests.
    _translateLayers:     _translateLayers,
    _setCanvasSize:       _setCanvasSize,
    _resolveRect:         _resolveRect,
    _destroyNodesByIds:   _destroyNodesByIds,
  };

  if (typeof window !== 'undefined') {
    window.OraCropToSelection = ns;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = ns;
  }
})(typeof window !== 'undefined' ? window : this);
