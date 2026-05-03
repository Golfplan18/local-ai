/* v3-panel-grid.js — Cartoon Studio panel-grid interior-border dragging
 * (§7.9, 2026-04-30)
 *
 * The cartoon-studio composition templates ship rectangular panels marked
 * with `panel: true` in attrs. This module turns those panels into a
 * connected grid: it detects shared edges (right of A ≈ left of B; bottom
 * of A ≈ top of B) and overlays a thin draggable handle on each interior
 * border. Dragging the handle resizes BOTH adjacent panels — the rest of
 * the layout stays put.
 *
 * Triggered by:
 *   ora:canvas-loaded — fires after a template applies. We re-derive
 *                        adjacencies + handles from scratch each load.
 *   ora:canvas-mounted — kick the first scan once the panel mounts.
 *
 * Handles are NOT serialized — they're transient overlays that re-derive
 * on next load. Panel rects (which ARE serialized via the codec) carry
 * the position/size changes the user makes by dragging.
 *
 * Public API: window.OraV3PanelGrid
 *   refresh(panel) — manually re-derive adjacencies + handles
 *   clear(panel)   — remove all handles
 *
 * Detection rules
 *   • Two rects share a vertical edge if  |right(A) - left(B)| ≤ TOL
 *     AND their y-ranges overlap by ≥ MIN_OVERLAP px
 *   • Two rects share a horizontal edge if  |bottom(A) - top(B)| ≤ TOL
 *     AND their x-ranges overlap by ≥ MIN_OVERLAP px
 *
 * Snapping
 *   • A handle's drag is constrained to ±MAX_DRAG px from initial position
 *   • Each adjacent panel is constrained to remain ≥ MIN_PANEL_SIZE wide/tall
 */
(function () {
  'use strict';

  var MAX_GUTTER       = 200;        // px gap between adjacent panels (gutters)
  var MIN_OVERLAP      = 30;         // px overlap required for adjacency
  var MIN_PANEL_SIZE   = 60;         // px floor for resized panels
  var HANDLE_THICKNESS = 18;         // hit-area thickness — wider than visual
  var HANDLE_FILL_HOVER = 'rgba(80, 250, 123, 0.35)';

  // Track per-panel handle layer additions so we can clear them.
  // Map: panel → [handleNode, ...]
  var _handlesByPanel = (typeof WeakMap !== 'undefined') ? new WeakMap() : null;

  function _isPanelRect(node) {
    if (!node || typeof node.getClassName !== 'function') return false;
    if (node.getClassName() !== 'Rect') return false;
    var attr = (typeof node.getAttr === 'function') ? node.getAttr('panel') : null;
    return attr === true || attr === 'true';
  }

  function _bbox(rect) {
    return {
      left:   rect.x(),
      top:    rect.y(),
      right:  rect.x() + rect.width(),
      bottom: rect.y() + rect.height(),
      node:   rect
    };
  }

  function _overlapY(a, b) {
    return Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
  }
  function _overlapX(a, b) {
    return Math.min(a.right, b.right) - Math.max(a.left, b.left);
  }

  // ── handle factory ─────────────────────────────────────────────────────

  function _makeVerticalHandle(K, panel, leftRects, rightRects, midX, gutter, y0, y1) {
    var halfGutter = gutter / 2;
    var handle = new K.Rect({
      x: midX - HANDLE_THICKNESS / 2, y: y0,
      width: HANDLE_THICKNESS, height: y1 - y0,
      fill: 'rgba(0,0,0,0)',
      draggable: true,
      name: 'panel-grid-handle',
      dragBoundFunc: function (pos) {
        return { x: pos.x, y: this.absolutePosition().y };
      }
    });
    handle.on('mouseenter', function () {
      handle.fill(HANDLE_FILL_HOVER);
      panel.userInputLayer.draw();
      var konvaEl = panel._konvaEl || (panel.el && panel.el.querySelector && panel.el.querySelector('.konvajs-content'));
      if (konvaEl) konvaEl.style.cursor = 'col-resize';
    });
    handle.on('mouseleave', function () {
      handle.fill('rgba(0,0,0,0)');
      panel.userInputLayer.draw();
      var konvaEl = panel._konvaEl || (panel.el && panel.el.querySelector && panel.el.querySelector('.konvajs-content'));
      if (konvaEl) konvaEl.style.cursor = '';
    });

    // Constrain so neither set of panels shrinks below MIN_PANEL_SIZE.
    // Left panel right-edge = newMidX - halfGutter, so newMidX ≥ leftMin + halfGutter.
    var leftMin   = Math.max.apply(null, leftRects.map(function (r) { return r.x() + MIN_PANEL_SIZE; }));
    var rightMax  = Math.min.apply(null, rightRects.map(function (r) { return r.x() + r.width() - MIN_PANEL_SIZE; }));

    handle.on('dragmove', function () {
      var newMid = handle.x() + HANDLE_THICKNESS / 2;
      // Clamp so resized panels stay ≥ MIN_PANEL_SIZE.
      newMid = Math.max(leftMin + halfGutter, Math.min(rightMax - halfGutter, newMid));
      handle.x(newMid - HANDLE_THICKNESS / 2);

      var leftEdge  = newMid - halfGutter;
      var rightEdge = newMid + halfGutter;

      leftRects.forEach(function (r) {
        var newW = leftEdge - r.x();
        if (newW >= MIN_PANEL_SIZE) r.width(newW);
      });
      rightRects.forEach(function (r) {
        var oldRight = r.x() + r.width();
        var newW = oldRight - rightEdge;
        if (newW >= MIN_PANEL_SIZE) {
          r.x(rightEdge);
          r.width(newW);
        }
      });
      panel.userInputLayer.draw();
    });

    return handle;
  }

  function _makeHorizontalHandle(K, panel, topRects, bottomRects, midY, gutter, x0, x1) {
    var halfGutter = gutter / 2;
    var handle = new K.Rect({
      x: x0, y: midY - HANDLE_THICKNESS / 2,
      width: x1 - x0, height: HANDLE_THICKNESS,
      fill: 'rgba(0,0,0,0)',
      draggable: true,
      name: 'panel-grid-handle',
      dragBoundFunc: function (pos) {
        return { x: this.absolutePosition().x, y: pos.y };
      }
    });
    handle.on('mouseenter', function () {
      handle.fill(HANDLE_FILL_HOVER);
      panel.userInputLayer.draw();
      var konvaEl = panel._konvaEl || (panel.el && panel.el.querySelector && panel.el.querySelector('.konvajs-content'));
      if (konvaEl) konvaEl.style.cursor = 'row-resize';
    });
    handle.on('mouseleave', function () {
      handle.fill('rgba(0,0,0,0)');
      panel.userInputLayer.draw();
      var konvaEl = panel._konvaEl || (panel.el && panel.el.querySelector && panel.el.querySelector('.konvajs-content'));
      if (konvaEl) konvaEl.style.cursor = '';
    });

    var topMin     = Math.max.apply(null, topRects.map(function (r) { return r.y() + MIN_PANEL_SIZE; }));
    var bottomMax  = Math.min.apply(null, bottomRects.map(function (r) { return r.y() + r.height() - MIN_PANEL_SIZE; }));

    handle.on('dragmove', function () {
      var newMid = handle.y() + HANDLE_THICKNESS / 2;
      newMid = Math.max(topMin + halfGutter, Math.min(bottomMax - halfGutter, newMid));
      handle.y(newMid - HANDLE_THICKNESS / 2);

      var topEdge    = newMid - halfGutter;
      var bottomEdge = newMid + halfGutter;

      topRects.forEach(function (r) {
        var newH = topEdge - r.y();
        if (newH >= MIN_PANEL_SIZE) r.height(newH);
      });
      bottomRects.forEach(function (r) {
        var oldBot = r.y() + r.height();
        var newH = oldBot - bottomEdge;
        if (newH >= MIN_PANEL_SIZE) {
          r.y(bottomEdge);
          r.height(newH);
        }
      });
      panel.userInputLayer.draw();
    });

    return handle;
  }

  // ── adjacency derivation ───────────────────────────────────────────────

  function _gatherPanels(panel) {
    if (!panel || !panel.userInputLayer || typeof panel.userInputLayer.getChildren !== 'function') return [];
    return panel.userInputLayer.getChildren().filter(_isPanelRect);
  }

  function _findVerticalSplits(boxes) {
    // Two panels share a vertical split when one's right edge is to the
    // LEFT of the other's left edge by a gutter ≤ MAX_GUTTER, AND they
    // y-overlap by ≥ MIN_OVERLAP. Comic templates use 80px gutters; touch-
    // edge panels (gutter = 0) also count.
    //
    // Bucket by gutter-midpoint-rounded-to-nearest-20px so panels in the
    // same column boundary aggregate. Each split records the gutter so
    // the handle can preserve it when dragged.
    var splits = {};
    boxes.forEach(function (a) {
      boxes.forEach(function (b) {
        if (a === b) return;
        var gutter = b.left - a.right;
        if (gutter < 0 || gutter > MAX_GUTTER) return;
        if (_overlapY(a, b) < MIN_OVERLAP) return;
        var midX = (a.right + b.left) / 2;
        var key = Math.round(midX / 20) * 20; // 20px bucket so wider templates aggregate
        if (!splits[key]) splits[key] = { x: midX, gutter: gutter, leftRects: [], rightRects: [], y0: Infinity, y1: -Infinity };
        if (splits[key].leftRects.indexOf(a.node) < 0)  splits[key].leftRects.push(a.node);
        if (splits[key].rightRects.indexOf(b.node) < 0) splits[key].rightRects.push(b.node);
        splits[key].y0 = Math.min(splits[key].y0, a.top, b.top);
        splits[key].y1 = Math.max(splits[key].y1, a.bottom, b.bottom);
      });
    });
    return Object.keys(splits).map(function (k) { return splits[k]; });
  }

  function _findHorizontalSplits(boxes) {
    var splits = {};
    boxes.forEach(function (a) {
      boxes.forEach(function (b) {
        if (a === b) return;
        var gutter = b.top - a.bottom;
        if (gutter < 0 || gutter > MAX_GUTTER) return;
        if (_overlapX(a, b) < MIN_OVERLAP) return;
        var midY = (a.bottom + b.top) / 2;
        var key = Math.round(midY / 20) * 20;
        if (!splits[key]) splits[key] = { y: midY, gutter: gutter, topRects: [], bottomRects: [], x0: Infinity, x1: -Infinity };
        if (splits[key].topRects.indexOf(a.node) < 0)    splits[key].topRects.push(a.node);
        if (splits[key].bottomRects.indexOf(b.node) < 0) splits[key].bottomRects.push(b.node);
        splits[key].x0 = Math.min(splits[key].x0, a.left, b.left);
        splits[key].x1 = Math.max(splits[key].x1, a.right, b.right);
      });
    });
    return Object.keys(splits).map(function (k) { return splits[k]; });
  }

  // ── public ─────────────────────────────────────────────────────────────

  function clear(panel) {
    if (!panel || !panel.userInputLayer) return;
    var existing = (_handlesByPanel && _handlesByPanel.get(panel)) || [];
    existing.forEach(function (h) {
      try { h.destroy(); } catch (e) {}
    });
    if (_handlesByPanel) _handlesByPanel.set(panel, []);

    // Defensive: also destroy any orphaned handles by name.
    var orphans = panel.userInputLayer.find('.panel-grid-handle');
    if (orphans && orphans.forEach) {
      orphans.forEach(function (h) {
        try { h.destroy(); } catch (e) {}
      });
    }
  }

  function refresh(panel) {
    var K = window.Konva;
    if (!K || !panel || !panel.userInputLayer) return;
    clear(panel);

    var rects = _gatherPanels(panel);
    if (rects.length < 2) return;

    var boxes = rects.map(_bbox);
    var vSplits = _findVerticalSplits(boxes);
    var hSplits = _findHorizontalSplits(boxes);

    var added = [];

    vSplits.forEach(function (s) {
      var h = _makeVerticalHandle(K, panel, s.leftRects, s.rightRects, s.x, s.gutter, s.y0, s.y1);
      panel.userInputLayer.add(h);
      added.push(h);
    });
    hSplits.forEach(function (s) {
      var h = _makeHorizontalHandle(K, panel, s.topRects, s.bottomRects, s.y, s.gutter, s.x0, s.x1);
      panel.userInputLayer.add(h);
      added.push(h);
    });

    if (_handlesByPanel) _handlesByPanel.set(panel, added);
    panel.userInputLayer.draw();

    if (added.length) {
      console.info('[v3-panel-grid] derived ' + added.length + ' interior border handle(s)');
    }
  }

  // ── auto-refresh on canvas events ──────────────────────────────────────

  if (typeof document !== 'undefined') {
    document.addEventListener('ora:canvas-loaded', function () {
      var panel = window.OraCanvas && window.OraCanvas.panel;
      if (panel) setTimeout(function () { refresh(panel); }, 50);
    });
    document.addEventListener('ora:canvas-mounted', function () {
      var panel = window.OraCanvas && window.OraCanvas.panel;
      if (panel) setTimeout(function () { refresh(panel); }, 100);
    });
  }

  window.OraV3PanelGrid = {
    refresh: refresh,
    clear:   clear
  };
})();
