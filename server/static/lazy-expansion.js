/**
 * lazy-expansion.js — WP-7.4.6
 *
 * Implements **lazy canvas expansion** per Visual Intelligence Implementation
 * Plan §11.7 ("Canvas Mechanics — Lazy expansion") and §13.4 WP-7.4.6.
 *
 *   Photoshop equivalent:  there is none — Photoshop forces the user into
 *                          Image → Canvas Size manually. Lazy expansion
 *                          mirrors the "infinite canvas" UX of Figma /
 *                          tldraw / Miro: the canvas silently grows when a
 *                          newly placed object lands near (or past) an edge.
 *
 * When a user drops, pastes, draws, or AI-inserts an object whose bounding
 * box approaches within `THRESHOLD_PX` (default 200 px) of any canvas edge,
 * the canvas auto-grows by `GROW_FRACTION` (default 25 %) in the relevant
 * direction(s) — silently, no prompt. The user notices the new room via
 * scroll-bars / minimap (if WP-7.4.5 zoom-to-extents is in scope).
 *
 * ── Architecture ────────────────────────────────────────────────────────────
 *
 * Self-registering IIFE that lives alongside `visual-panel.js` rather than
 * inside it. Per Plan §13 and the WP-7.4.8 precedent, new commands hook in
 * via their own module so the §7.4 / §7.5 / §7.1 WPs running in parallel
 * don't collide on `visual-panel.js` edits. Concretely:
 *
 *   1. Patches `VisualPanel.prototype._createShape` so every newly drawn
 *      shape (rect / ellipse / diamond / line / arrow / text) triggers a
 *      post-placement bounds check.
 *   2. Patches `VisualPanel.prototype._installBackgroundImage` so dropped
 *      / picked / pasted images trigger the same check after the Konva.Image
 *      lands on backgroundLayer.
 *   3. Listens for `canvas-state-changed` on each panel's host element so
 *      capability-image-* AI insertions (image_generates / image_styles /
 *      image_upscales / image_outpaints + the image-edits tool) — which
 *      already emit that event per WP-7.3.x — also feed the expansion check.
 *
 * Each hook calls `_checkAndExpand(panel)` once on the next animation frame
 * (debounced via the panel-scoped `_lazyExpandPending` flag) so a burst of
 * placements collapses into a single expansion.
 *
 * Reuses `window.OraResizeCanvas.apply()` to perform the grow. Anchor is
 * derived from which edge(s) we're growing toward:
 *   - growing the right side  → anchor 'top-left'    (left side stays put)
 *   - growing the bottom side → anchor 'top-left'    (top side stays put)
 *   - growing the left side   → anchor 'top-right'   (right side stays put)
 *   - growing the top side    → anchor 'bottom-left' (bottom side stays put)
 *   - growing right + bottom  → anchor 'top-left'    (covered by top-left)
 *   - growing left + bottom   → anchor 'top-right'
 *   - growing right + top     → anchor 'bottom-left'
 *   - growing left + top      → anchor 'bottom-right'
 *
 * For mixed cases (e.g. an object straddles both right and left edges, which
 * happens only when the canvas is smaller than the object) we grow on both
 * axes by anchoring at the corner farthest from the object's nearest edge.
 *
 * ── Public surface — exposed as `window.OraLazyExpansion` ───────────────────
 *
 *   THRESHOLD_PX_DEFAULT = 200
 *   GROW_FRACTION_DEFAULT = 0.25
 *
 *   init(panel, opts?) → controller
 *     Wire a panel up. `opts` keys:
 *       threshold_px:     number, default 200
 *       grow_fraction:    number, default 0.25 (25 %)
 *       enabled:          boolean, default true
 *     Returns a controller `{ destroy(), setEnabled(b), setThreshold(n) }`.
 *     Calling init() twice on the same panel is idempotent — the prior
 *     controller is destroyed first.
 *
 *   destroy(panel)
 *     Remove all hooks for the panel.
 *
 *   computeExpansion(prior, bounds, threshold, grow_fraction) → { width, height, anchor, grew } | null
 *     Pure helper. `prior` = { width, height } current canvas. `bounds` =
 *     the just-placed object's { x, y, width, height } in stage-local
 *     coordinates. Returns the next canvas dimensions + anchor, or null if
 *     no growth is needed.
 *
 *   checkAndExpand(panel, bounds?) → result | null
 *     Manual entry point. If `bounds` omitted, walks all four layers via
 *     OraResizeCanvas.computeBoundingBox() and uses that union. Returns the
 *     OraResizeCanvas.apply() result, or null if no growth was needed.
 *
 * ── Konva-side invariant ────────────────────────────────────────────────────
 *
 * Lazy expansion does NOT translate any object on its own — it delegates to
 * OraResizeCanvas.apply(), which handles the anchor-translation invariant.
 * Because we always anchor on the side OPPOSITE the growing edge, existing
 * objects do not move. The newly placed object is already inside the new
 * bounds (we grew the canvas to cover it), so nothing needs to be repositioned.
 *
 * ── Test criterion (per §13.4 WP-7.4.6) ─────────────────────────────────────
 *
 *   Place an object with its right edge 50 px from the canvas's right edge
 *   (so within the 200 px threshold). Verify the canvas extends rightward
 *   by 25 %. Existing objects don't move. Test runs in cases/
 *   test-lazy-expansion.js in the visual-compiler harness.
 */

(function (root) {
  'use strict';

  // ── Constants ─────────────────────────────────────────────────────────────

  var THRESHOLD_PX_DEFAULT  = 200;
  var GROW_FRACTION_DEFAULT = 0.25;
  // Hard ceiling so a runaway loop can't grow the canvas to infinity. Mirrors
  // OraResizeCanvas.MIN_DIMENSION's complement; the canvas-state schema's
  // upper bound is enforced by the schema, not by us.
  var MAX_DIMENSION         = 1e6;

  // Map a (grow_left, grow_top) pair to the anchor name the resize command
  // expects. The anchor is the side that STAYS PUT, so the grow direction
  // is the OPPOSITE side.
  //   grow right (left stays) + grow bottom (top stays) → 'top-left'
  //   grow left (right stays) + grow bottom (top stays) → 'top-right'
  //   grow right (left stays) + grow top (bottom stays) → 'bottom-left'
  //   grow left (right stays) + grow top (bottom stays) → 'bottom-right'
  // Single-axis growth uses an edge-anchor: e.g. growing only on the right
  // anchors 'top-left' (which is equivalent to anchoring on the left side
  // for x and the top side for y, but since we don't grow vertically the
  // y-anchor doesn't move objects). A pure single-axis anchor like
  // 'middle-left' would also work, but corners are equally correct and
  // simpler to reason about.
  function _anchorFor(growLeft, growTop) {
    if (growLeft && growTop)   return 'bottom-right';
    if (growLeft && !growTop)  return 'top-right';
    if (!growLeft && growTop)  return 'bottom-left';
    return 'top-left';                     // grow right and/or bottom (default)
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  function _isObj(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }
  function _isPositiveNumber(v) { return typeof v === 'number' && isFinite(v) && v > 0; }
  function _isNumber(v) { return typeof v === 'number' && isFinite(v); }
  function _clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  // ── Pure expansion math ──────────────────────────────────────────────────

  /**
   * Decide whether the placed object's bounding box is close enough to (or
   * past) any canvas edge to trigger expansion. If so, return the next
   * canvas dimensions + anchor. Otherwise return null.
   *
   *   prior  = { width, height }
   *   bounds = { x, y, width, height }   in stage-local coords
   *   threshold     = px from edge that triggers grow (default 200)
   *   grow_fraction = how much to grow as a fraction of the prior dimension
   *                   on the affected axis (default 0.25)
   *
   * Returns:
   *   {
   *     width:   nextWidth,
   *     height:  nextHeight,
   *     anchor:  'top-left' | 'top-right' | 'bottom-left' | 'bottom-right',
   *     grew:    { left: bool, right: bool, top: bool, bottom: bool },
   *     reason:  short string for diagnostics
   *   }
   *
   * Or null if no edge is within `threshold`.
   *
   * Edge proximity rules:
   *   - left edge:   (bounds.x) < threshold              → grow leftward
   *   - top edge:    (bounds.y) < threshold              → grow upward
   *   - right edge:  (prior.width  - (bounds.x + bounds.width))  < threshold → grow rightward
   *   - bottom edge: (prior.height - (bounds.y + bounds.height)) < threshold → grow downward
   *
   * If both right AND left trigger (object wider than canvas), we grow on
   * the side with the smaller margin — but in practice, an object that wide
   * is already partially outside, so we grow rightward (default) and leave
   * any left-side overlap to a subsequent placement event to expand.
   */
  function computeExpansion(prior, bounds, threshold, growFraction) {
    if (!_isObj(prior) || !_isObj(bounds)) return null;
    if (!_isPositiveNumber(prior.width) || !_isPositiveNumber(prior.height)) return null;
    if (!_isNumber(bounds.x) || !_isNumber(bounds.y)) return null;
    if (!_isPositiveNumber(bounds.width) || !_isPositiveNumber(bounds.height)) return null;
    var T = _isPositiveNumber(threshold)    ? threshold    : THRESHOLD_PX_DEFAULT;
    var F = _isPositiveNumber(growFraction) ? growFraction : GROW_FRACTION_DEFAULT;

    var leftMargin   = bounds.x;
    var topMargin    = bounds.y;
    var rightMargin  = prior.width  - (bounds.x + bounds.width);
    var bottomMargin = prior.height - (bounds.y + bounds.height);

    var growLeft   = leftMargin   < T;
    var growTop    = topMargin    < T;
    var growRight  = rightMargin  < T;
    var growBottom = bottomMargin < T;

    if (!(growLeft || growTop || growRight || growBottom)) return null;

    // Resolve conflicting both-sides-trigger cases by preferring the smaller
    // margin (object closer to that side wins). This keeps the anchor map
    // simple and avoids growing on both x-axes simultaneously.
    if (growLeft && growRight) {
      if (rightMargin <= leftMargin) growLeft = false;
      else                            growRight = false;
    }
    if (growTop && growBottom) {
      if (bottomMargin <= topMargin) growTop = false;
      else                            growBottom = false;
    }

    var dW = (growLeft || growRight) ? Math.ceil(prior.width  * F) : 0;
    var dH = (growTop  || growBottom) ? Math.ceil(prior.height * F) : 0;

    // If the object overruns the edge by more than the grow amount, grow
    // by however much covers the overrun + threshold. Without this, a single
    // far-out placement (e.g. AI insertion at x = canvasWidth + 500) would
    // leave the canvas still too small after the 25 % grow.
    if (growRight) {
      var rightOverrun = (bounds.x + bounds.width) - prior.width;
      if (rightOverrun > 0) dW = Math.max(dW, Math.ceil(rightOverrun + T));
    }
    if (growLeft) {
      var leftOverrun = -bounds.x;
      if (leftOverrun > 0) dW = Math.max(dW, Math.ceil(leftOverrun + T));
    }
    if (growBottom) {
      var bottomOverrun = (bounds.y + bounds.height) - prior.height;
      if (bottomOverrun > 0) dH = Math.max(dH, Math.ceil(bottomOverrun + T));
    }
    if (growTop) {
      var topOverrun = -bounds.y;
      if (topOverrun > 0) dH = Math.max(dH, Math.ceil(topOverrun + T));
    }

    var nextW = _clamp(prior.width  + dW, prior.width,  MAX_DIMENSION);
    var nextH = _clamp(prior.height + dH, prior.height, MAX_DIMENSION);

    return {
      width:  nextW,
      height: nextH,
      anchor: _anchorFor(growLeft, growTop),
      grew:   { left: !!growLeft, right: !!growRight, top: !!growTop, bottom: !!growBottom },
      reason: 'edge_proximity',
    };
  }

  // ── Bounds extraction ────────────────────────────────────────────────────

  /**
   * Return the bounding box of a single Konva node in stage-local coords,
   * or null if it can't be computed. Mirrors the convention in
   * OraResizeCanvas.computeBoundingBox().
   */
  function _nodeBounds(node, layer) {
    if (!node || typeof node.getClientRect !== 'function') return null;
    var rect;
    try {
      rect = node.getClientRect({ relativeTo: layer || node.getLayer && node.getLayer() });
    } catch (e) { rect = null; }
    if (!rect) return null;
    if (rect.width <= 0 && rect.height <= 0) return null;
    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
  }

  /**
   * Walk all four layers and return the union bbox, falling back to a
   * `OraResizeCanvas.computeBoundingBox()` call if the namespace is loaded.
   */
  function _panelUnionBounds(panel) {
    var rc = (typeof window !== 'undefined' && window.OraResizeCanvas) || null;
    if (rc && typeof rc.computeBoundingBox === 'function') {
      var bb = rc.computeBoundingBox(panel);
      return bb ? bb.union : null;
    }
    // Fallback: minimal local walk if OraResizeCanvas hasn't loaded.
    var layerNames = ['backgroundLayer', 'annotationLayer', 'userInputLayer', 'selectionLayer'];
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity, count = 0;
    for (var li = 0; li < layerNames.length; li++) {
      var layer = panel[layerNames[li]];
      if (!layer || typeof layer.getChildren !== 'function') continue;
      var children = layer.getChildren();
      for (var ci = 0; ci < children.length; ci++) {
        var node = children[ci];
        if (!node) continue;
        if (node.getAttr && node.getAttr('name') === 'svg-sentinel') continue;
        var b = _nodeBounds(node, layer);
        if (!b) continue;
        if (b.x < minX) minX = b.x;
        if (b.y < minY) minY = b.y;
        if (b.x + b.width  > maxX) maxX = b.x + b.width;
        if (b.y + b.height > maxY) maxY = b.y + b.height;
        count++;
      }
    }
    if (count === 0) return null;
    return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
  }

  // ── Apply the grow ───────────────────────────────────────────────────────

  /**
   * Compute and (if needed) apply a lazy expansion. Returns the
   * OraResizeCanvas.apply() result, or null if no growth was triggered.
   *
   *   bounds — explicit object bbox (preferred, lets us avoid walking the
   *            entire layer tree on every placement). If omitted, the union
   *            of all layers is used.
   */
  function checkAndExpand(panel, bounds) {
    if (!panel) return null;
    var rc = (typeof window !== 'undefined' && window.OraResizeCanvas) || null;
    if (!rc || typeof rc.apply !== 'function' || typeof rc.getCurrentSize !== 'function') {
      // OraResizeCanvas missing (e.g. test boot order) — silently no-op.
      return null;
    }
    var prior = rc.getCurrentSize(panel);
    var bbox = bounds && _isObj(bounds) ? bounds : _panelUnionBounds(panel);
    if (!bbox) return null;

    var cfg = panel._lazyExpansionConfig || {};
    var T = _isPositiveNumber(cfg.threshold_px)  ? cfg.threshold_px  : THRESHOLD_PX_DEFAULT;
    var F = _isPositiveNumber(cfg.grow_fraction) ? cfg.grow_fraction : GROW_FRACTION_DEFAULT;

    var plan = computeExpansion(prior, bbox, T, F);
    if (!plan) return null;

    try {
      var res = rc.apply(panel, {
        width:        plan.width,
        height:       plan.height,
        anchor:       plan.anchor,
        confirm_crop: true,    // we never shrink, so this is moot, but harmless
      });
      // Notify observers (autosave, telemetry).
      try {
        var doc = (panel && panel.el && panel.el.ownerDocument) || (typeof document !== 'undefined' ? document : null);
        var host = (panel && panel.el) || (doc && doc.body);
        if (host && typeof host.dispatchEvent === 'function' && typeof CustomEvent !== 'undefined') {
          host.dispatchEvent(new CustomEvent('canvas-lazy-expanded', {
            bubbles: true,
            detail: {
              prior:  prior,
              next:   { width: plan.width, height: plan.height },
              anchor: plan.anchor,
              grew:   plan.grew,
              reason: plan.reason,
            },
          }));
        }
      } catch (_e) { /* swallow */ }
      return res;
    } catch (e) {
      // Resize threw (cropping confirm failure shouldn't happen since we
      // only enlarge, but be defensive). Don't propagate — lazy expansion
      // is best-effort.
      return null;
    }
  }

  // ── Schedule a check on next frame (debounced) ───────────────────────────

  function _scheduleCheck(panel, getBounds) {
    if (!panel) return;
    if (panel._lazyExpansionDestroyed) return;
    if (panel._lazyExpandPending) return;     // already scheduled — coalesce
    panel._lazyExpandPending = true;
    var run = function () {
      panel._lazyExpandPending = false;
      if (panel._lazyExpansionDestroyed) return;
      if (panel._lazyExpansionConfig && panel._lazyExpansionConfig.enabled === false) return;
      var bounds = null;
      try { bounds = getBounds && getBounds(); } catch (_e) { bounds = null; }
      checkAndExpand(panel, bounds);
    };
    if (typeof requestAnimationFrame === 'function') {
      try { requestAnimationFrame(run); return; } catch (_e) { /* fall through */ }
    }
    setTimeout(run, 0);
  }

  // ── Panel hookup (prototype-patching pattern, per WP-7.4.8 precedent) ────

  // Patch the prototype ONCE; per-panel enable/disable lives on
  // panel._lazyExpansionConfig.enabled.
  function _patchPrototypeOnce(VisualPanelClass) {
    if (!VisualPanelClass || !VisualPanelClass.prototype) return;
    if (VisualPanelClass.prototype.__oraLazyExpandPatched) return;

    // _createShape — every drawn / pasted shape goes through this seam.
    var _origCreateShape = VisualPanelClass.prototype._createShape;
    if (typeof _origCreateShape === 'function') {
      VisualPanelClass.prototype._createShape = function _patchedCreateShape(type, params) {
        var node = _origCreateShape.apply(this, arguments);
        if (node && this._lazyExpansionConfig) {
          var self = this;
          var layer = this.userInputLayer;
          _scheduleCheck(this, function () { return _nodeBounds(node, layer); });
        }
        return node;
      };
    }

    // _installBackgroundImage — drag-drop, file picker, camera, paste all
    // funnel through here via attachImage() → _installBackgroundImage().
    var _origInstall = VisualPanelClass.prototype._installBackgroundImage;
    if (typeof _origInstall === 'function') {
      VisualPanelClass.prototype._installBackgroundImage = function _patchedInstallBg(dataUrl, file, onReady) {
        var self = this;
        var wrapped = onReady;
        if (this._lazyExpansionConfig) {
          wrapped = function () {
            try { if (typeof onReady === 'function') onReady(); }
            finally {
              _scheduleCheck(self, function () {
                return self._backgroundImageNode
                  ? _nodeBounds(self._backgroundImageNode, self.backgroundLayer)
                  : null;
              });
            }
          };
        }
        return _origInstall.call(this, dataUrl, file, wrapped);
      };
    }

    VisualPanelClass.prototype.__oraLazyExpandPatched = true;
  }

  // ── Public init / destroy ────────────────────────────────────────────────

  /**
   * Mount lazy expansion on a panel. Idempotent: calling twice destroys
   * the previous wiring first.
   */
  function init(panel, opts) {
    if (!panel) throw new Error('lazy-expansion: panel is required');
    opts = _isObj(opts) ? opts : {};

    // Patch the prototype the first time we see any panel of this class.
    if (typeof window !== 'undefined' && window.VisualPanel) {
      _patchPrototypeOnce(window.VisualPanel);
    } else if (panel.constructor) {
      _patchPrototypeOnce(panel.constructor);
    }

    // Idempotent: tear down any prior wiring on this panel.
    destroy(panel);

    panel._lazyExpansionConfig = {
      threshold_px:  _isPositiveNumber(opts.threshold_px)  ? opts.threshold_px  : THRESHOLD_PX_DEFAULT,
      grow_fraction: _isPositiveNumber(opts.grow_fraction) ? opts.grow_fraction : GROW_FRACTION_DEFAULT,
      enabled:       opts.enabled === false ? false : true,
    };
    panel._lazyExpansionDestroyed = false;

    // ── Listen for capability-image-* AI insertions on the panel host ────
    var hostEl = panel.el || null;
    var listener = function (evt) {
      if (!panel._lazyExpansionConfig) return;
      if (panel._lazyExpansionConfig.enabled === false) return;
      // Skip our own re-emission to avoid feedback loops.
      if (evt && evt.detail && evt.detail.source === 'lazy-expansion') return;
      _scheduleCheck(panel, function () {
        // Prefer the canvas object's geometry when present; fall back to
        // the panel's union (covers cases where the AI delivered the image
        // through the attachImage/_installBackgroundImage path, which the
        // _installBackgroundImage hook already handled).
        var detail = evt && evt.detail;
        var obj = detail && detail.object;
        if (obj && _isPositiveNumber(obj.width) && _isPositiveNumber(obj.height)) {
          var ax = (obj.x != null) ? obj.x : (detail.anchor && detail.anchor.x) || 0;
          var ay = (obj.y != null) ? obj.y : (detail.anchor && detail.anchor.y) || 0;
          return { x: ax, y: ay, width: obj.width, height: obj.height };
        }
        return null;
      });
    };
    if (hostEl && typeof hostEl.addEventListener === 'function') {
      hostEl.addEventListener('canvas-state-changed', listener);
    }
    panel._lazyExpansionListener = { host: hostEl, fn: listener };

    var controller = {
      destroy:      function () { destroy(panel); },
      setEnabled:   function (b) {
        if (panel._lazyExpansionConfig) panel._lazyExpansionConfig.enabled = !!b;
      },
      setThreshold: function (px) {
        if (panel._lazyExpansionConfig && _isPositiveNumber(px)) {
          panel._lazyExpansionConfig.threshold_px = px;
        }
      },
      setGrowFraction: function (f) {
        if (panel._lazyExpansionConfig && _isPositiveNumber(f)) {
          panel._lazyExpansionConfig.grow_fraction = f;
        }
      },
      checkNow: function (bounds) { return checkAndExpand(panel, bounds); },
      // Internals exposed for tests.
      _config: function () { return panel._lazyExpansionConfig; },
    };
    panel._lazyExpansionController = controller;
    return controller;
  }

  /**
   * Tear down the per-panel wiring. The prototype patch stays — it's
   * gated on `panel._lazyExpansionConfig` existing, so a destroyed panel
   * silently no-ops. Safe to call repeatedly.
   */
  function destroy(panel) {
    if (!panel) return;
    panel._lazyExpansionDestroyed = true;
    if (panel._lazyExpansionListener) {
      var L = panel._lazyExpansionListener;
      try {
        if (L.host && typeof L.host.removeEventListener === 'function') {
          L.host.removeEventListener('canvas-state-changed', L.fn);
        }
      } catch (_e) { /* ignore */ }
      panel._lazyExpansionListener = null;
    }
    panel._lazyExpansionConfig = null;
    panel._lazyExpansionController = null;
    panel._lazyExpandPending = false;
  }

  // ── Module export ────────────────────────────────────────────────────────

  var ns = {
    THRESHOLD_PX_DEFAULT:  THRESHOLD_PX_DEFAULT,
    GROW_FRACTION_DEFAULT: GROW_FRACTION_DEFAULT,
    MAX_DIMENSION:         MAX_DIMENSION,
    init:                  init,
    destroy:               destroy,
    checkAndExpand:        checkAndExpand,
    computeExpansion:      computeExpansion,
    // Internals exposed for tests.
    _anchorFor:            _anchorFor,
    _nodeBounds:           _nodeBounds,
    _panelUnionBounds:     _panelUnionBounds,
    _scheduleCheck:        _scheduleCheck,
    _patchPrototypeOnce:   _patchPrototypeOnce,
  };

  if (typeof window !== 'undefined') {
    window.OraLazyExpansion = ns;
    // Auto-wire any panels that come into existence after this script loads,
    // unless the host has set `window.OraLazyExpansionAutoWire = false` to
    // opt out (useful for tests).
    if (window.OraLazyExpansionAutoWire !== false && window.VisualPanel) {
      _patchPrototypeOnce(window.VisualPanel);
    }
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = ns;
  }
})(typeof window !== 'undefined' ? window : this);
