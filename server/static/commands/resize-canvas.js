/**
 * resize-canvas.js — WP-7.4.1
 *
 * Implements the **Resize canvas** command per Visual Intelligence Implementation
 * Plan §11.7 ("Canvas Mechanics — Resize canvas") and §13.4 WP-7.4.1.
 *
 *   Photoshop equivalent:  Image → Canvas Size
 *
 * Manually set the nominal canvas dimensions, with a 9-point anchor grid that
 * controls which side(s) extend or shrink. Existing objects move only by the
 * anchor offset (not relative to one another), preserving their layout. When
 * shrinking would crop an object outside the new bounds, the user is warned
 * and must confirm before the destructive action proceeds.
 *
 * ── Architecture ────────────────────────────────────────────────────────────
 *
 * Self-registering IIFE that lives alongside `visual-panel.js` rather than
 * inside it (Plan §13 recommends new commands hook in via their own module so
 * the §7.4 / §7.5 / §7.1 WPs running in parallel don't collide on
 * `visual-panel.js` edits). The module reads the four-layer Konva model that
 * VisualPanel exposes (`backgroundLayer` / `annotationLayer` / `userInputLayer`
 * / `selectionLayer`) plus the persisted canvas-state metadata.
 *
 * It does NOT depend on:
 *   - WP-7.4.4 (pan/zoom keyboard shortcuts) — viewport transform is preserved
 *     but never adjusted by this command.
 *   - WP-7.4.6 (lazy expansion) — explicit dimensions only; auto-grow is a
 *     separate command.
 *   - WP-7.4.5 (zoom-to-extents) — independent.
 *
 * It DOES depend on:
 *   - WP-7.0.2 (canvas-file-format.js) — `metadata.canvas_size` schema field.
 *
 * ── Public surface — exposed as `window.OraResizeCanvas` ────────────────────
 *
 *   POLICIES = ['enlarge', 'shrink', 'mixed', 'unchanged']
 *
 *   ANCHORS — 9-point grid, named per Photoshop's anchor square:
 *     'top-left'      'top-center'      'top-right'
 *     'middle-left'   'center'          'middle-right'
 *     'bottom-left'   'bottom-center'   'bottom-right'
 *
 *   open(panel, opts) → Promise<{ status, params }>
 *     Show the modal dialog over the panel. The promise resolves once the
 *     user clicks Apply (status='applied'), Cancel (status='cancelled'), or
 *     dismisses a crop confirmation (status='cancelled').
 *
 *   apply(panel, params) → { changed, prior, next, translation, cropping, cropped_objects }
 *     Non-UI command application. Used by the dialog after Apply is clicked,
 *     and directly by tests. `params` shape:
 *       {
 *         width:  number,    // target canvas width (px), > 0
 *         height: number,    // target canvas height (px), > 0
 *         anchor: string,    // one of ANCHORS
 *         confirm_crop: boolean  // required true if cropping would discard objects
 *       }
 *     Throws if confirm_crop is false and the resize would crop. The caller
 *     (dialog or test) is responsible for the confirmation flow.
 *
 *   computeAnchorOffset(prior, next, anchor) → { dx, dy }
 *     Pure helper. Given prior {width, height} and next {width, height},
 *     returns the (dx, dy) translation that should be applied to every
 *     existing object so the anchored side stays put.
 *
 *   computeBoundingBox(panel) → { x, y, width, height } | null
 *     Walks all four layers and returns the union of every drawable's
 *     getClientRect() in stage-local coordinates. Returns null if the
 *     panel has no objects.
 *
 *   computeCropping(prior, next, anchor, bbox) → { will_crop, count }
 *     Pure helper. Given prior and next sizes, the chosen anchor, and the
 *     pre-translation bounding box, returns whether any object would fall
 *     outside the next canvas bounds after translation. `count` is set when
 *     the caller passes a panel-derived `bbox` *array* of per-object boxes.
 *
 *   ANCHOR_FRACTIONS — { '<anchor>': [fx, fy] }
 *     fx, fy ∈ {0, 0.5, 1} — fraction of dW (resp. dH) added to each
 *     object's x (resp. y) so the anchored side stays anchored.
 *       fx=0   anchored-left   →  dx = 0     (right side moves)
 *       fx=0.5 anchored-center →  dx = dW/2  (both sides move equally)
 *       fx=1   anchored-right  →  dx = dW    (left side moves)
 *     dW = next.width - prior.width   (positive when enlarging)
 *
 * ── Konva-side translation invariant ────────────────────────────────────────
 *
 * Every node in the four layers gets its (x, y) shifted by (dx, dy) — once.
 * Nested groups have their own (x, y) shifted; their children are NOT walked
 * recursively because Konva applies the parent transform automatically. The
 * sentinel group on backgroundLayer is exempt (it carries no rendered SVG;
 * the SVG lives in the DOM overlay).
 *
 * The DOM SVG overlay (`panel._svgHost`) is NOT translated here — the artifact
 * is positioned by `_applyTransform()` (the viewport transform), which is left
 * alone. After resize, the artifact occupies the same viewport region as
 * before (its stage-local x/y are 0/0 by VisualPanel convention). That matches
 * Photoshop's behavior: the existing background image stays put under its
 * anchor; only the canvas frame around it moves.
 *
 * ── Canvas state mutation ───────────────────────────────────────────────────
 *
 * The command updates `panel._canvasState.metadata.canvas_size` if a
 * `_canvasState` object is present on the panel (set by save/load plumbing
 * to be wired in WP-7.4.7 / WP-7.4.8). If absent, a minimal stub is created
 * via `OraCanvasFileFormat.newCanvasState({ canvas_size })` so subsequent
 * save logic has somewhere to read the dimensions from. This is additive —
 * it does not stomp on any other persisted fields.
 *
 * ── Test criterion (per §13.4 WP-7.4.1) ─────────────────────────────────────
 *
 *   1. Enlarge with center anchor; verify all sides grow equally.
 *   2. Shrink with top-left anchor when objects are outside new bounds;
 *      verify warning + user-confirm flow.
 *
 * Both pass via cases/test-resize-canvas.js in the visual-compiler harness.
 */

(function (root) {
  'use strict';

  // ── Constants ─────────────────────────────────────────────────────────────

  var ANCHORS = [
    'top-left',    'top-center',    'top-right',
    'middle-left', 'center',        'middle-right',
    'bottom-left', 'bottom-center', 'bottom-right',
  ];

  // [fx, fy] — fraction of (next - prior) added to each object's (x, y) so
  // the named side stays put. fx=0 anchors LEFT (no x-shift), fx=1 anchors
  // RIGHT (full x-shift), fx=0.5 anchors CENTER (half x-shift). Same for fy
  // along the y-axis.
  var ANCHOR_FRACTIONS = {
    'top-left':       [0,   0  ],
    'top-center':     [0.5, 0  ],
    'top-right':      [1,   0  ],
    'middle-left':    [0,   0.5],
    'center':         [0.5, 0.5],
    'middle-right':   [1,   0.5],
    'bottom-left':    [0,   1  ],
    'bottom-center':  [0.5, 1  ],
    'bottom-right':   [1,   1  ],
  };

  var MIN_DIMENSION = 1;       // px; canvas-state schema requires > 0
  var DEFAULT_DIMENSION = 10000;

  // ── Helpers ───────────────────────────────────────────────────────────────

  function _isObj(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }
  function _isPositiveNumber(v) { return typeof v === 'number' && isFinite(v) && v > 0; }

  function _clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  function _validateParams(params) {
    if (!_isObj(params)) throw new Error('resize-canvas: params object required');
    if (!_isPositiveNumber(params.width))  throw new Error('resize-canvas: params.width must be a positive number');
    if (!_isPositiveNumber(params.height)) throw new Error('resize-canvas: params.height must be a positive number');
    if (typeof params.anchor !== 'string' || !(params.anchor in ANCHOR_FRACTIONS)) {
      throw new Error('resize-canvas: params.anchor must be one of ' + ANCHORS.join(', ') + ' (got ' + params.anchor + ')');
    }
    if (params.width  < MIN_DIMENSION) throw new Error('resize-canvas: width below minimum (' + MIN_DIMENSION + ')');
    if (params.height < MIN_DIMENSION) throw new Error('resize-canvas: height below minimum (' + MIN_DIMENSION + ')');
  }

  // ── Pure geometry helpers ─────────────────────────────────────────────────

  /**
   * Given the prior and next canvas dimensions and the chosen anchor name,
   * return the (dx, dy) translation that should be applied to every existing
   * object. The anchored side stays put; the opposite side moves.
   *
   *   prior = { width, height }
   *   next  = { width, height }
   *   anchor = 'top-left' | ... | 'bottom-right'
   *
   * Examples:
   *   center anchor, enlarging by 200x100 → dx=100, dy=50  (every object
   *     drifts toward the new center; both sides grow equally).
   *   top-left anchor, enlarging by 200x100 → dx=0, dy=0  (right and bottom
   *     sides grow; objects don't move).
   *   top-left anchor, shrinking by 200x100 → dx=0, dy=0  (right and bottom
   *     sides shrink; objects don't move; warning if any object's right or
   *     bottom edge exceeds the new bounds).
   */
  function computeAnchorOffset(prior, next, anchor) {
    if (!_isObj(prior) || !_isObj(next)) {
      throw new Error('resize-canvas: prior and next must be {width, height} objects');
    }
    if (!_isPositiveNumber(prior.width) || !_isPositiveNumber(prior.height)) {
      throw new Error('resize-canvas: prior dimensions must be positive numbers');
    }
    if (!_isPositiveNumber(next.width) || !_isPositiveNumber(next.height)) {
      throw new Error('resize-canvas: next dimensions must be positive numbers');
    }
    var frac = ANCHOR_FRACTIONS[anchor];
    if (!frac) throw new Error('resize-canvas: unknown anchor "' + anchor + '"');
    var dW = next.width  - prior.width;
    var dH = next.height - prior.height;
    return { dx: dW * frac[0], dy: dH * frac[1] };
  }

  /**
   * Diagnostic categorization of a resize for surfacing in the dialog.
   */
  function classifyResize(prior, next) {
    var dW = next.width  - prior.width;
    var dH = next.height - prior.height;
    if (dW === 0 && dH === 0) return 'unchanged';
    if (dW >= 0 && dH >= 0)   return 'enlarge';
    if (dW <= 0 && dH <= 0)   return 'shrink';
    return 'mixed';
  }

  // ── Bounding-box computation across the four layers ──────────────────────

  /**
   * Walk the four Konva layers and return per-object bounding boxes plus the
   * union. Skips the background sentinel group. Coordinates are in stage-
   * local space (i.e. before any pan/zoom transform), so they are directly
   * comparable to the canvas dimensions.
   *
   * Returns:
   *   {
   *     union: { x, y, width, height } | null,
   *     boxes: [{ id, layer, x, y, width, height }, ...]
   *   }
   *
   * `id` is preferred from the node's `userShapeId` / `userAnnotationId` /
   * Konva `id()`; falling back to `_konvaInternalIndex` for the sentinel-
   * exempt nodes.
   */
  function computeBoundingBox(panel) {
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
        // Skip the background sentinel group — it has no SVG children of its
        // own; the SVG artifact lives in the DOM overlay, not on the layer.
        if (node.getAttr && node.getAttr('name') === 'svg-sentinel') continue;
        var rect;
        try {
          rect = node.getClientRect ? node.getClientRect({ relativeTo: layer }) : null;
        } catch (e) { rect = null; }
        if (!rect) continue;
        // Konva returns 0×0 rects for invisible / empty groups; skip them.
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
   * Determine whether the chosen resize would drop any object outside the
   * new canvas bounds AFTER the anchor translation is applied. Returns
   *   { will_crop: boolean, cropped_ids: [...], dx, dy }
   *
   * `boxes` is the array returned by computeBoundingBox(). Each box's
   * (x + dx, y + dy, width, height) is compared against the new bounds
   * [0, 0, next.width, next.height]; any box that would fall fully outside,
   * partially outside, or extend beyond the new edges is considered cropped.
   *
   * Note: a partially-cropped object is still flagged. The user is warning-
   * level material; they can either accept cropping or pick a different
   * anchor / dimensions.
   */
  function computeCropping(prior, next, anchor, boxes) {
    var off = computeAnchorOffset(prior, next, anchor);
    var croppedIds = [];
    if (Array.isArray(boxes)) {
      for (var i = 0; i < boxes.length; i++) {
        var b = boxes[i]; if (!b) continue;
        var x0 = b.x + off.dx;
        var y0 = b.y + off.dy;
        var x1 = x0 + b.width;
        var y1 = y0 + b.height;
        // Crop if any edge lies outside [0, next.width] x [0, next.height].
        if (x0 < 0 || y0 < 0 || x1 > next.width || y1 > next.height) {
          croppedIds.push(b.id);
        }
      }
    }
    return {
      will_crop:   croppedIds.length > 0,
      cropped_ids: croppedIds,
      dx:          off.dx,
      dy:          off.dy,
    };
  }

  // ── Canvas-state read / write ─────────────────────────────────────────────

  /**
   * Read the current canvas dimensions. Order of precedence:
   *   1. panel._canvasState.metadata.canvas_size (set by save/load plumbing)
   *   2. panel._priorCanvasSize (in-memory fallback set by previous resize)
   *   3. OraCanvasFileFormat defaults (DEFAULT_CANVAS_W / DEFAULT_CANVAS_H)
   *   4. Hardcoded module default (DEFAULT_DIMENSION)
   */
  function getCurrentSize(panel) {
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
    return { width: DEFAULT_DIMENSION, height: DEFAULT_DIMENSION };
  }

  /**
   * Update / create the canvas-state metadata so subsequent saves emit the
   * new size. Sets `panel._canvasState` if absent, using OraCanvasFileFormat
   * (when available) for a schema-valid skeleton; falls back to a minimal
   * inline object so this command works even before WP-7.4.8 wires save.
   */
  function _setCanvasSize(panel, next) {
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

  // ── Konva node translation ───────────────────────────────────────────────

  /**
   * Apply (dx, dy) to every direct child of the four layers, with two
   * exceptions:
   *   - The background sentinel group (no rendered children of its own).
   *   - Any node whose `name` is 'user-shape-preview' (in-flight draw).
   *
   * Returns the count of nodes translated, for diagnostics.
   */
  function _translateLayers(panel, dx, dy) {
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

  // ── Public command API ───────────────────────────────────────────────────

  /**
   * Apply a resize directly. Throws on invalid params or on cropping without
   * confirmation. See module header for the params contract.
   *
   * Returns:
   *   {
   *     changed:          boolean,
   *     prior:            { width, height },
   *     next:             { width, height },
   *     translation:      { dx, dy },
   *     cropping:         boolean,         // true iff any object would be cropped
   *     cropped_ids:      [string],        // ids of cropped objects (may be empty)
   *     nodes_translated: integer,
   *     classification:   'enlarge' | 'shrink' | 'mixed' | 'unchanged'
   *   }
   */
  function apply(panel, params) {
    _validateParams(params);
    var prior = getCurrentSize(panel);
    var next  = { width: params.width, height: params.height };
    var off   = computeAnchorOffset(prior, next, params.anchor);
    var bb    = computeBoundingBox(panel);
    var crop  = computeCropping(prior, next, params.anchor, bb.boxes);

    if (crop.will_crop && !params.confirm_crop) {
      var err = new Error('resize-canvas: shrinking would crop ' + crop.cropped_ids.length
                        + ' object(s); set params.confirm_crop=true to proceed.');
      err.code = 'E_CROP_REQUIRES_CONFIRMATION';
      err.cropped_ids = crop.cropped_ids;
      err.translation = { dx: off.dx, dy: off.dy };
      throw err;
    }

    var moved = _translateLayers(panel, off.dx, off.dy);
    _setCanvasSize(panel, next);

    return {
      changed:          (prior.width !== next.width) || (prior.height !== next.height) || moved > 0,
      prior:            prior,
      next:             next,
      translation:      { dx: off.dx, dy: off.dy },
      cropping:         crop.will_crop,
      cropped_ids:      crop.cropped_ids.slice(),
      nodes_translated: moved,
      classification:   classifyResize(prior, next),
    };
  }

  // ── Dialog UI ─────────────────────────────────────────────────────────────

  /**
   * Tear down a previously-opened dialog (if any) for the given panel.
   * Safe to call repeatedly. Used by both the Cancel button and the Apply
   * path so the dialog disappears on either resolution.
   */
  function _disposeDialog(panel) {
    if (!panel || !panel._resizeCanvasDialog) return;
    var dlg = panel._resizeCanvasDialog;
    try {
      if (dlg.onKeyDown) dlg.root.removeEventListener('keydown', dlg.onKeyDown);
      if (dlg.parent && dlg.root.parentNode === dlg.parent) dlg.parent.removeChild(dlg.root);
    } catch (e) { /* ignore */ }
    panel._resizeCanvasDialog = null;
  }

  /**
   * Build (and append) the modal dialog. Returns a `controller` object
   * with `.resolve` / `.reject` keys; the open() Promise wires its
   * resolver into these.
   */
  function _buildDialog(panel, opts, controller) {
    opts = _isObj(opts) ? opts : {};
    var prior = getCurrentSize(panel);
    var doc = (panel && panel.el && panel.el.ownerDocument) || (typeof document !== 'undefined' ? document : null);
    if (!doc) throw new Error('resize-canvas: no document available to mount dialog');

    var root = doc.createElement('div');
    root.className = 'visual-panel__resize-dialog';
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-label', 'Resize canvas');
    root.style.cssText = [
      'position:absolute', 'inset:0',
      'background:rgba(0,0,0,.45)',
      'display:flex', 'align-items:center', 'justify-content:center',
      'z-index:100', 'font-family:var(--font-ui, system-ui, sans-serif)',
    ].join(';');

    var card = doc.createElement('div');
    card.className = 'visual-panel__resize-dialog-card';
    card.style.cssText = [
      'background:var(--bg-panel,#fff)',
      'color:var(--text-primary,#1a1a1a)',
      'padding:18px 22px',
      'border-radius:6px',
      'box-shadow:0 8px 24px rgba(0,0,0,.25)',
      'min-width:320px',
      'max-width:420px',
      'font-size:13px',
      'line-height:1.45',
    ].join(';');

    // Title
    var h2 = doc.createElement('h2');
    h2.textContent = 'Resize canvas';
    h2.style.cssText = 'margin:0 0 12px 0;font-size:15px;font-weight:600;';
    card.appendChild(h2);

    // Current size readout
    var current = doc.createElement('div');
    current.className = 'rcd-current';
    current.style.cssText = 'margin-bottom:10px;color:var(--text-secondary,#555);font-size:12px;';
    current.textContent = 'Current: ' + prior.width + ' × ' + prior.height + ' px';
    card.appendChild(current);

    // Width / height inputs
    function _input(name, label, value) {
      var wrap = doc.createElement('label');
      wrap.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:6px;';
      var lbl = doc.createElement('span');
      lbl.textContent = label;
      lbl.style.cssText = 'min-width:70px;';
      var input = doc.createElement('input');
      input.type = 'number';
      input.min = String(MIN_DIMENSION);
      input.value = String(value);
      input.name = name;
      input.dataset.field = name;
      input.style.cssText = 'flex:1;padding:5px 8px;border:1px solid var(--border,#bbb);border-radius:3px;font:inherit;';
      wrap.appendChild(lbl);
      wrap.appendChild(input);
      return { wrap: wrap, input: input };
    }
    var widthEl  = _input('width',  'Width (px)',  prior.width);
    var heightEl = _input('height', 'Height (px)', prior.height);
    card.appendChild(widthEl.wrap);
    card.appendChild(heightEl.wrap);

    // Anchor grid (3x3 buttons)
    var anchorWrap = doc.createElement('div');
    anchorWrap.style.cssText = 'margin:10px 0 6px 0;';
    var anchorLbl = doc.createElement('div');
    anchorLbl.textContent = 'Anchor';
    anchorLbl.style.cssText = 'margin-bottom:6px;font-weight:500;';
    anchorWrap.appendChild(anchorLbl);
    var grid = doc.createElement('div');
    grid.className = 'rcd-anchor-grid';
    grid.setAttribute('role', 'radiogroup');
    grid.setAttribute('aria-label', 'Resize anchor');
    grid.style.cssText = [
      'display:grid', 'grid-template-columns:repeat(3, 28px)',
      'grid-template-rows:repeat(3, 28px)', 'gap:3px',
      'width:max-content',
    ].join(';');
    var initialAnchor = (typeof opts.initial_anchor === 'string' && opts.initial_anchor in ANCHOR_FRACTIONS)
      ? opts.initial_anchor
      : 'center';
    var anchorBtns = {};
    for (var ai = 0; ai < ANCHORS.length; ai++) {
      var name = ANCHORS[ai];
      var btn = doc.createElement('button');
      btn.type = 'button';
      btn.dataset.anchor = name;
      btn.setAttribute('role', 'radio');
      btn.setAttribute('aria-label', name);
      btn.setAttribute('aria-checked', name === initialAnchor ? 'true' : 'false');
      btn.style.cssText = [
        'width:28px', 'height:28px',
        'border:1px solid var(--border,#bbb)',
        'background:' + (name === initialAnchor ? 'var(--accent,#4a7)' : 'var(--bg-panel,#fff)'),
        'color:' + (name === initialAnchor ? '#fff' : 'inherit'),
        'border-radius:2px', 'cursor:pointer', 'padding:0',
        'font-size:14px',
      ].join(';');
      btn.textContent = '·';   // dot — minimal but visible
      anchorBtns[name] = btn;
      grid.appendChild(btn);
    }
    anchorWrap.appendChild(grid);
    card.appendChild(anchorWrap);

    // Warning slot — populated when shrinking would crop.
    var warning = doc.createElement('div');
    warning.className = 'rcd-warning';
    warning.setAttribute('role', 'alert');
    warning.style.cssText = [
      'margin:8px 0', 'padding:8px 10px', 'border-radius:3px',
      'background:var(--warning-bg,#fff3cd)', 'color:var(--warning-fg,#664d03)',
      'border:1px solid var(--warning-border,#ffe69c)',
      'font-size:12px', 'display:none',
    ].join(';');
    card.appendChild(warning);

    // Buttons
    var btns = doc.createElement('div');
    btns.style.cssText = 'display:flex;gap:8px;justify-content:flex-end;margin-top:12px;';
    var cancelBtn = doc.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.dataset.action = 'cancel';
    cancelBtn.style.cssText = 'padding:6px 14px;border:1px solid var(--border,#bbb);background:var(--bg-panel,#fff);border-radius:3px;cursor:pointer;font:inherit;';
    var applyBtn = doc.createElement('button');
    applyBtn.type = 'button';
    applyBtn.textContent = 'Apply';
    applyBtn.dataset.action = 'apply';
    applyBtn.style.cssText = 'padding:6px 14px;border:1px solid var(--accent,#4a7);background:var(--accent,#4a7);color:#fff;border-radius:3px;cursor:pointer;font:inherit;font-weight:500;';
    btns.appendChild(cancelBtn);
    btns.appendChild(applyBtn);
    card.appendChild(btns);

    root.appendChild(card);

    // Mount target — prefer panel.el so the dialog overlays the visual panel.
    var parent = (panel && panel.el) || doc.body;
    parent.appendChild(root);

    // ── Anchor click handler ─────────────────────────────────────────────
    function _setAnchor(name) {
      if (!(name in ANCHOR_FRACTIONS)) return;
      controller.anchor = name;
      for (var k in anchorBtns) {
        if (!Object.prototype.hasOwnProperty.call(anchorBtns, k)) continue;
        var b = anchorBtns[k];
        var on = (k === name);
        b.setAttribute('aria-checked', on ? 'true' : 'false');
        b.style.background = on ? 'var(--accent,#4a7)' : 'var(--bg-panel,#fff)';
        b.style.color = on ? '#fff' : 'inherit';
      }
      _updateWarning();
    }
    grid.addEventListener('click', function (ev) {
      var t = ev.target;
      while (t && t !== grid) {
        if (t.dataset && t.dataset.anchor) { _setAnchor(t.dataset.anchor); return; }
        t = t.parentNode;
      }
    });

    // ── Live warning (recomputed on every input change) ──────────────────
    var bb = computeBoundingBox(panel);
    function _readParams() {
      var w = parseFloat(widthEl.input.value);
      var h = parseFloat(heightEl.input.value);
      if (!isFinite(w) || w <= 0) w = prior.width;
      if (!isFinite(h) || h <= 0) h = prior.height;
      return { width: w, height: h };
    }
    function _updateWarning() {
      var nxt = _readParams();
      try {
        var crop = computeCropping(prior, nxt, controller.anchor, bb.boxes);
        if (crop.will_crop) {
          warning.style.display = 'block';
          warning.textContent = 'Warning: shrinking with the chosen anchor would crop '
            + crop.cropped_ids.length + ' object(s). Apply will require confirmation.';
        } else {
          warning.style.display = 'none';
          warning.textContent = '';
        }
      } catch (e) {
        warning.style.display = 'none';
      }
    }
    widthEl.input.addEventListener('input', _updateWarning);
    heightEl.input.addEventListener('input', _updateWarning);

    // ── Cancel / Apply handlers ──────────────────────────────────────────
    cancelBtn.addEventListener('click', function () {
      controller.resolve({ status: 'cancelled', reason: 'user-cancelled' });
    });
    applyBtn.addEventListener('click', function () {
      var params = _readParams();
      params.anchor = controller.anchor;
      params.confirm_crop = false;
      try {
        var res = apply(panel, params);
        controller.resolve({ status: 'applied', params: params, result: res });
      } catch (err) {
        if (err && err.code === 'E_CROP_REQUIRES_CONFIRMATION') {
          // Open confirm flow inline. Keep it simple: a confirm() in the
          // browser, falling back to an inline yes/no message in test envs.
          var ok = false;
          try {
            ok = (typeof window !== 'undefined' && typeof window.confirm === 'function')
              ? window.confirm('Shrinking would crop ' + (err.cropped_ids ? err.cropped_ids.length : 'one or more')
                              + ' object(s). Proceed and discard them?')
              : false;
          } catch (e) { ok = false; }
          if (!ok) {
            controller.resolve({ status: 'cancelled', reason: 'crop-not-confirmed', cropped_ids: err.cropped_ids });
            return;
          }
          params.confirm_crop = true;
          try {
            var res2 = apply(panel, params);
            controller.resolve({ status: 'applied', params: params, result: res2, cropped: true });
          } catch (e2) {
            controller.resolve({ status: 'error', error: String(e2 && e2.message || e2) });
          }
        } else {
          controller.resolve({ status: 'error', error: String(err && err.message || err) });
        }
      }
    });

    // ── Keyboard: Esc cancels, Enter applies ─────────────────────────────
    var onKeyDown = function (ev) {
      if (ev.key === 'Escape') { ev.stopPropagation(); cancelBtn.click(); }
      else if (ev.key === 'Enter') { ev.stopPropagation(); applyBtn.click(); }
    };
    root.addEventListener('keydown', onKeyDown);

    // Stash teardown handles on the panel so re-open / disposeDialog work.
    panel._resizeCanvasDialog = {
      root:   root,
      parent: parent,
      onKeyDown: onKeyDown,
    };

    // Initial focus
    try { widthEl.input.focus(); widthEl.input.select(); } catch (e) { /* ignore */ }

    // Prime warning state
    _updateWarning();

    // Return the public hooks the open() Promise needs.
    return {
      root:        root,
      anchor:      initialAnchor,
      readParams:  _readParams,
      setAnchor:   _setAnchor,
      cancel:      function () { cancelBtn.click(); },
      apply:       function () { applyBtn.click(); },
    };
  }

  /**
   * Show the resize dialog over the given panel. Returns a Promise that
   * resolves once the user clicks Apply (success or post-confirm), Cancel
   * (any path), or the dialog is dismissed via Escape / outside-click.
   *
   * Resolution shape:
   *   { status: 'applied',  params, result, cropped? }    on Apply
   *   { status: 'cancelled', reason, cropped_ids? }      on Cancel / Esc
   *   { status: 'error', error }                          on unexpected throw
   */
  function open(panel, opts) {
    if (!panel) return Promise.reject(new Error('resize-canvas: panel is required'));
    _disposeDialog(panel);   // idempotent; collapses any prior dialog
    return new Promise(function (resolve) {
      var controller = {
        anchor: 'center',
        resolve: function (val) {
          _disposeDialog(panel);
          resolve(val);
        },
      };
      try {
        var hooks = _buildDialog(panel, opts, controller);
        controller.anchor = hooks.anchor;
        // Stash hooks on the panel for tests to drive synchronously.
        panel._resizeCanvasDialog.hooks = hooks;
      } catch (e) {
        resolve({ status: 'error', error: String(e && e.message || e) });
      }
    });
  }

  // ── Module export ────────────────────────────────────────────────────────

  var ns = {
    ANCHORS:              ANCHORS.slice(),
    ANCHOR_FRACTIONS:     ANCHOR_FRACTIONS,
    MIN_DIMENSION:        MIN_DIMENSION,
    open:                 open,
    apply:                apply,
    computeAnchorOffset:  computeAnchorOffset,
    computeBoundingBox:   computeBoundingBox,
    computeCropping:      computeCropping,
    classifyResize:       classifyResize,
    getCurrentSize:       getCurrentSize,
    // Internals exposed for tests.
    _validateParams:      _validateParams,
    _translateLayers:     _translateLayers,
    _setCanvasSize:       _setCanvasSize,
    _disposeDialog:       _disposeDialog,
  };

  if (typeof window !== 'undefined') {
    window.OraResizeCanvas = ns;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = ns;
  }
})(typeof window !== 'undefined' ? window : this);
