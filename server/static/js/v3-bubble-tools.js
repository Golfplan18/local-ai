/* v3-bubble-tools.js — Cartoon Studio shape tools (§7.9, 2026-04-30)
 *
 * Comic-book bubble + caption shapes built as Konva.Group composites:
 *
 *   speech_bubble  — rounded rect + triangular tail + inner text
 *   thought_bubble — ellipse + small ellipse trail + inner text
 *   shout_bubble   — jagged star polygon + inner text
 *   caption_box    — bordered rect with title-bar tab + inner text
 *
 * Each tool registers a click-to-place handler: user clicks an empty spot,
 * a default-sized bubble appears with a text editor focused so they can
 * type immediately. Click outside or Escape commits; the bubble persists
 * as a single selectable group on userInputLayer.
 *
 * Dispatched via the extended pack-toolbar action registry in
 * v3-pack-toolbars.js (which routes tool:speech_bubble etc. here).
 *
 * Public API: window.OraV3BubbleTools
 *   placeAt(panel, kind, x, y, opts)
 *     kind: 'speech' | 'thought' | 'shout' | 'caption'
 *     x, y: canvas-space coordinates
 *     opts.text: initial text (defaults to a per-kind placeholder)
 *
 *   activateTool(panel, kind)
 *     Arms a click-to-place mode. Next pointer-down on the stage places
 *     a bubble at that point, then deactivates the mode.
 *
 * The tools deliberately do NOT use shape-with-text (which expects a
 * specific host-shape geometry). Bubbles need a tail or trail siblings,
 * so a Group with a parent shape + tail + Konva.Text child is simpler.
 */
(function () {
  'use strict';

  var DEFAULT_W = 220;
  var DEFAULT_H = 110;
  var BUBBLE_FILL    = '#ffffff';
  var BUBBLE_STROKE  = '#1a1a1a';
  var BUBBLE_STROKE_W = 3;
  var TEXT_COLOR     = '#1a1a1a';
  var TEXT_PADDING   = 14;
  var FONT_FAMILY    = 'Inter, system-ui, sans-serif';
  var FONT_SIZE      = 16;

  function _newId(prefix) {
    return (prefix || 'bubble') + '-' + Date.now().toString(36) + '-'
      + Math.floor(Math.random() * 1e6).toString(36);
  }

  // ── bubble factories ──────────────────────────────────────────────────

  function _buildSpeech(K, x, y, w, h, text) {
    var group = new K.Group({ x: x, y: y, draggable: true, name: 'user-shape', id: _newId('speech') });
    group.setAttr('bubbleKind', 'speech');

    var body = new K.Rect({
      x: 0, y: 0, width: w, height: h,
      cornerRadius: Math.min(28, h * 0.4),
      fill: BUBBLE_FILL, stroke: BUBBLE_STROKE, strokeWidth: BUBBLE_STROKE_W
    });
    body.setAttr('name', 'bubble-body');

    // Triangular tail at bottom-left.
    var tailX = w * 0.25;
    var tail = new K.Line({
      points: [tailX, h - 1, tailX - 14, h + 22, tailX + 18, h - 1],
      closed: true, fill: BUBBLE_FILL, stroke: BUBBLE_STROKE, strokeWidth: BUBBLE_STROKE_W
    });
    tail.setAttr('name', 'bubble-tail');

    var label = new K.Text({
      x: TEXT_PADDING, y: TEXT_PADDING,
      width: w - TEXT_PADDING * 2, height: h - TEXT_PADDING * 2,
      text: text, fontFamily: FONT_FAMILY, fontSize: FONT_SIZE,
      fill: TEXT_COLOR, align: 'center', verticalAlign: 'middle', wrap: 'word'
    });
    label.setAttr('name', 'bubble-text');

    group.add(body); group.add(tail); group.add(label);
    return group;
  }

  function _buildThought(K, x, y, w, h, text) {
    var group = new K.Group({ x: x, y: y, draggable: true, name: 'user-shape', id: _newId('thought') });
    group.setAttr('bubbleKind', 'thought');

    var body = new K.Ellipse({
      x: w / 2, y: h / 2, radiusX: w / 2, radiusY: h / 2,
      fill: BUBBLE_FILL, stroke: BUBBLE_STROKE, strokeWidth: BUBBLE_STROKE_W
    });
    body.setAttr('name', 'bubble-body');

    // Three small trail ellipses, decreasing in size, going down-left.
    var trail1 = new K.Ellipse({ x: w * 0.20, y: h + 18, radiusX: 16, radiusY: 11,
                                  fill: BUBBLE_FILL, stroke: BUBBLE_STROKE, strokeWidth: BUBBLE_STROKE_W });
    var trail2 = new K.Ellipse({ x: w * 0.10, y: h + 38, radiusX: 9,  radiusY: 6,
                                  fill: BUBBLE_FILL, stroke: BUBBLE_STROKE, strokeWidth: BUBBLE_STROKE_W });
    var trail3 = new K.Ellipse({ x: w * 0.04, y: h + 50, radiusX: 4,  radiusY: 3,
                                  fill: BUBBLE_FILL, stroke: BUBBLE_STROKE, strokeWidth: BUBBLE_STROKE_W });
    [trail1, trail2, trail3].forEach(function (t) { t.setAttr('name', 'bubble-tail'); });

    var label = new K.Text({
      x: TEXT_PADDING, y: TEXT_PADDING,
      width: w - TEXT_PADDING * 2, height: h - TEXT_PADDING * 2,
      text: text, fontFamily: FONT_FAMILY, fontSize: FONT_SIZE,
      fill: TEXT_COLOR, align: 'center', verticalAlign: 'middle', wrap: 'word',
      fontStyle: 'italic'
    });
    label.setAttr('name', 'bubble-text');

    group.add(body); group.add(trail1); group.add(trail2); group.add(trail3); group.add(label);
    return group;
  }

  function _buildShout(K, x, y, w, h, text) {
    var group = new K.Group({ x: x, y: y, draggable: true, name: 'user-shape', id: _newId('shout') });
    group.setAttr('bubbleKind', 'shout');

    // Jagged starburst shape — alternating outer + inner radii around the centre.
    var cx = w / 2, cy = h / 2;
    var outerRX = w / 2, outerRY = h / 2;
    var innerRX = outerRX * 0.78, innerRY = outerRY * 0.78;
    var spikes = 14;
    var pts = [];
    for (var i = 0; i < spikes * 2; i++) {
      var ang = (Math.PI / spikes) * i - Math.PI / 2;
      var rX = (i % 2 === 0) ? outerRX : innerRX;
      var rY = (i % 2 === 0) ? outerRY : innerRY;
      pts.push(cx + Math.cos(ang) * rX, cy + Math.sin(ang) * rY);
    }
    var body = new K.Line({
      points: pts, closed: true,
      fill: BUBBLE_FILL, stroke: BUBBLE_STROKE, strokeWidth: BUBBLE_STROKE_W,
      lineJoin: 'miter'
    });
    body.setAttr('name', 'bubble-body');

    var label = new K.Text({
      x: TEXT_PADDING + 8, y: TEXT_PADDING + 4,
      width: w - (TEXT_PADDING + 8) * 2, height: h - (TEXT_PADDING + 4) * 2,
      text: text, fontFamily: FONT_FAMILY, fontSize: FONT_SIZE + 2, fontStyle: 'bold',
      fill: TEXT_COLOR, align: 'center', verticalAlign: 'middle', wrap: 'word'
    });
    label.setAttr('name', 'bubble-text');

    group.add(body); group.add(label);
    return group;
  }

  function _buildCaption(K, x, y, w, h, text) {
    var group = new K.Group({ x: x, y: y, draggable: true, name: 'user-shape', id: _newId('caption') });
    group.setAttr('bubbleKind', 'caption');

    // Title-bar tab on top.
    var tab = new K.Rect({
      x: 0, y: 0, width: 90, height: 16,
      fill: '#fffbe6', stroke: BUBBLE_STROKE, strokeWidth: 2
    });
    tab.setAttr('name', 'caption-tab');

    var body = new K.Rect({
      x: 0, y: 16, width: w, height: h - 16,
      fill: '#fffbe6', stroke: BUBBLE_STROKE, strokeWidth: BUBBLE_STROKE_W
    });
    body.setAttr('name', 'bubble-body');

    var label = new K.Text({
      x: TEXT_PADDING, y: 16 + TEXT_PADDING - 4,
      width: w - TEXT_PADDING * 2, height: h - 16 - (TEXT_PADDING - 4) * 2,
      text: text, fontFamily: FONT_FAMILY, fontSize: FONT_SIZE,
      fill: TEXT_COLOR, align: 'left', verticalAlign: 'top', wrap: 'word'
    });
    label.setAttr('name', 'bubble-text');

    group.add(body); group.add(tab); group.add(label);
    return group;
  }

  function _build(kind, K, x, y, opts) {
    opts = opts || {};
    var w = opts.width  || DEFAULT_W;
    var h = opts.height || DEFAULT_H;
    var text = (typeof opts.text === 'string') ? opts.text : _placeholderFor(kind);
    switch (kind) {
      case 'speech':  return _buildSpeech(K, x, y, w, h, text);
      case 'thought': return _buildThought(K, x, y, w, h, text);
      case 'shout':   return _buildShout(K, x, y, w, h, text);
      case 'caption': return _buildCaption(K, x, y, w, h, text);
      default:        return null;
    }
  }

  function _placeholderFor(kind) {
    if (kind === 'shout')   return 'POW!';
    if (kind === 'caption') return 'Meanwhile…';
    if (kind === 'thought') return 'Hmm.';
    return 'Hello!';
  }

  // ── placement ─────────────────────────────────────────────────────────

  function placeAt(panel, kind, x, y, opts) {
    var K = window.Konva;
    if (!K || !panel || !panel.userInputLayer) return null;
    var node = _build(kind, K, x, y, opts);
    if (!node) return null;
    panel.userInputLayer.add(node);

    // Tail-anchor handle for bubbles that have a tail. Caption boxes
    // skip — they're narrator boxes with no speaker.
    if (kind !== 'caption') {
      _attachTailAnchor(node, panel);
    }

    panel.userInputLayer.draw();

    if (typeof panel.setActiveTool === 'function') {
      try { panel.setActiveTool('select'); } catch (e) {}
    }
    if (typeof panel._selectShape === 'function') {
      try { panel._selectShape(node); } catch (e) {}
    } else if (panel._selectedShapeIds && typeof panel._selectedShapeIds.push === 'function') {
      panel._selectedShapeIds.push(node.id());
    }

    return node;
  }

  // ── tail anchor + bubble↔target linking ───────────────────────────────
  //
  // Tailed bubbles (speech and thought) get a draggable golden handle
  // at the tail tip. Shout bubbles are intentionally tail-less — the
  // jagged starburst body itself indicates the speaker, so no anchor
  // is attached and they don't participate in bubble↔target linking.
  // Caption boxes are narrator text without a speaker, also no anchor.
  //
  // The user drags the handle to re-aim the tail. If the drag ends ON
  // another canvas object, the bubble becomes LINKED to that object —
  // the tail tip then tracks the target's centre as either node moves.
  //
  // Storage: `linkedTarget` attr on the bubble group (target node id),
  // serialized via the codec automatically. On canvas reload, the
  // codec restores the attr; we re-wire follow-update via the
  // ora:canvas-loaded event listener at the bottom of this module.

  var ANCHOR_NAME = 'tail-anchor';
  var ANCHOR_RADIUS = 7;
  var ANCHOR_FILL   = '#ffd700';
  var ANCHOR_STROKE = '#1a1a1a';

  function _findChild(group, nameAttr) {
    if (!group || typeof group.getChildren !== 'function') return null;
    var kids = group.getChildren();
    for (var i = 0; i < kids.length; i++) {
      var n = kids[i];
      if (n && typeof n.getAttr === 'function' && n.getAttr('name') === nameAttr) return n;
    }
    return null;
  }

  function _findFirstTail(group) {
    if (!group || typeof group.getChildren !== 'function') return null;
    var kids = group.getChildren();
    for (var i = 0; i < kids.length; i++) {
      var n = kids[i];
      if (n && typeof n.getAttr === 'function' && n.getAttr('name') === 'bubble-tail') return n;
    }
    return null;
  }

  function _attachTailAnchor(group, panel) {
    var K = window.Konva;
    if (!K) return null;
    if (_findChild(group, ANCHOR_NAME)) return null;
    var tail = _findFirstTail(group);
    if (!tail) return null;

    // Tail-tip is the middle point of the 3-point Line for speech/shout.
    // Thought-bubble's first trail ellipse position works as the tip.
    var tipLocal;
    if (typeof tail.points === 'function' && Array.isArray(tail.points()) && tail.points().length >= 4) {
      var pts = tail.points();
      tipLocal = { x: pts[2] || 0, y: pts[3] || 0 };
    } else if (typeof tail.x === 'function') {
      tipLocal = { x: tail.x(), y: tail.y() };
    } else {
      tipLocal = { x: 20, y: 100 };
    }

    var handle = new K.Circle({
      x: tipLocal.x, y: tipLocal.y, radius: ANCHOR_RADIUS,
      fill: ANCHOR_FILL, stroke: ANCHOR_STROKE, strokeWidth: 1.5,
      draggable: true, name: ANCHOR_NAME, opacity: 0.85
    });
    group.add(handle);

    handle.on('dragmove.tail', function () { _redrawTailFromAnchor(group); });
    handle.on('dragend.tail',  function () { _tryLinkAfterDrag(group, panel); });

    // When the bubble itself is dragged, if linked, update tail to keep
    // pointing at the target.
    group.on('dragmove.tail-link', function () {
      var linkId = group.getAttr('linkedTarget');
      if (linkId) _refreshLinkedTail(group, panel);
    });

    return handle;
  }

  function _redrawTailFromAnchor(group) {
    var anchor = _findChild(group, ANCHOR_NAME);
    var body = _findChild(group, 'bubble-body');
    if (!anchor || !body) return;

    var ax = anchor.x();
    var ay = anchor.y();

    // Speech / shout: tail is a Konva.Line with 3 points.
    var tail = _findFirstTail(group);
    if (tail && typeof tail.points === 'function' && Array.isArray(tail.points()) && tail.points().length >= 6) {
      var bw = (typeof body.width === 'function') ? body.width() : 200;
      var bh = (typeof body.height === 'function') ? body.height() : 100;
      // Base anchored at the body edge nearest to the tip — bottom by default
      // since tails usually point down. If tip is above the body, anchor on top.
      var baseY = (ay > bh / 2) ? bh - 1 : 1;
      var baseX = Math.max(24, Math.min(bw - 24, ax));
      tail.points([baseX - 12, baseY, ax, ay, baseX + 12, baseY]);
    }

    // Thought-bubble: re-position the trail ellipses along the line from
    // body centre to anchor.
    var trails = group.find('.bubble-tail');
    if (trails && trails.length > 1 && typeof trails[0].radiusX === 'function') {
      // Treat trails as a chain of ellipses interpolating body→tip.
      var bw2 = (typeof body.width === 'function') ? body.width() : 200;
      var bh2 = (typeof body.height === 'function') ? body.height() : 100;
      var startX = bw2 / 2, startY = bh2;
      var n = trails.length;
      for (var i = 0; i < n; i++) {
        var t = (i + 1) / (n + 1);
        var nodeT = trails[i];
        if (typeof nodeT.x === 'function') {
          nodeT.x(startX + (ax - startX) * t);
          nodeT.y(startY + (ay - startY) * t);
        }
      }
    }

    var layer = group.getLayer && group.getLayer();
    if (layer && typeof layer.draw === 'function') layer.draw();
  }

  function _tryLinkAfterDrag(group, panel) {
    var anchor = _findChild(group, ANCHOR_NAME);
    if (!anchor) return;

    var anchorAbs = anchor.getAbsolutePosition();
    // Manual bbox hit-test against every user-shape on the panel layer.
    // We don't use stage.getIntersection because it's rendering-based —
    // shapes outside the visible stage region (large canvases viewed at
    // less than 1× zoom) wouldn't register. Bbox hit-test is layout-pure.
    var target = _hitTestUserShape(panel, anchorAbs, group);

    if (!target) {
      _unlink(group, panel);
      return;
    }

    group.setAttr('linkedTarget', target.id());
    _wireLinkFollow(group, target, panel);
    _refreshLinkedTail(group, panel);
  }

  function _hitTestUserShape(panel, abs, sourceGroup) {
    if (!panel || !panel.userInputLayer) return null;
    var kids = panel.userInputLayer.getChildren();
    // Iterate top-down (last drawn = on top).
    for (var i = kids.length - 1; i >= 0; i--) {
      var n = kids[i];
      if (!n || n === sourceGroup) continue;
      // Only user-shape candidates — skip selection layers, transformers,
      // and any handle overlays (which are on userInputLayer too).
      var name = (typeof n.getAttr === 'function') ? n.getAttr('name') : null;
      if (name === 'panel-grid-handle') continue;
      // Compute absolute bounding box of the candidate.
      var nodeAbs = n.getAbsolutePosition();
      var w = (typeof n.width  === 'function') ? n.width()  : 0;
      var h = (typeof n.height === 'function') ? n.height() : 0;
      // For Groups (e.g., other bubbles), use getClientRect for a tighter fit.
      if (typeof n.getClientRect === 'function' && (w === 0 || h === 0 || (n.getClassName && n.getClassName() === 'Group'))) {
        try {
          var cr = n.getClientRect({ skipTransform: false });
          if (abs.x >= cr.x && abs.x <= cr.x + cr.width
              && abs.y >= cr.y && abs.y <= cr.y + cr.height) {
            return n;
          }
        } catch (e) { /* fall through to width/height test */ }
      }
      if (w > 0 && h > 0
          && abs.x >= nodeAbs.x && abs.x <= nodeAbs.x + w
          && abs.y >= nodeAbs.y && abs.y <= nodeAbs.y + h) {
        return n;
      }
    }
    return null;
  }

  function _resolveLinkTarget(hit, sourceGroup) {
    if (!hit) return null;
    if (hit === sourceGroup) return null;
    var n = hit;
    while (n && typeof n.getParent === 'function') {
      if (n === sourceGroup) return null;
      var name = (typeof n.getAttr === 'function') ? n.getAttr('name') : null;
      if (name === 'user-shape') return n;
      n = n.getParent();
    }
    return null;
  }

  function _unlink(group, panel) {
    group.setAttr('linkedTarget', null);
    var stored = group._oraLinkedRef;
    if (stored && typeof stored.off === 'function') {
      try { stored.off('dragmove.tail-link'); } catch (e) {}
    }
    group._oraLinkedRef = null;
  }

  function _wireLinkFollow(group, target, panel) {
    // Detach any prior listener first.
    if (group._oraLinkedRef && typeof group._oraLinkedRef.off === 'function') {
      try { group._oraLinkedRef.off('dragmove.tail-link'); } catch (e) {}
    }
    target.on('dragmove.tail-link', function () {
      var link = group.getAttr('linkedTarget');
      if (link !== target.id()) {
        target.off('dragmove.tail-link');
        return;
      }
      _refreshLinkedTail(group, panel);
    });
    group._oraLinkedRef = target;
  }

  function _refreshLinkedTail(group, panel) {
    var linkId = group.getAttr('linkedTarget');
    if (!linkId) return;
    var stage = group.getStage && group.getStage();
    if (!stage) return;

    var target = (typeof stage.findOne === 'function') ? stage.findOne('#' + linkId) : null;
    if (!target) {
      // Target gone — unlink quietly.
      _unlink(group, panel);
      return;
    }

    var targetAbs = target.getAbsolutePosition();
    var targetW = (typeof target.width === 'function') ? target.width() : 0;
    var targetH = (typeof target.height === 'function') ? target.height() : 0;
    var groupAbs = group.getAbsolutePosition();
    var localTip = {
      x: targetAbs.x + targetW / 2 - groupAbs.x,
      y: targetAbs.y + targetH / 2 - groupAbs.y
    };

    var anchor = _findChild(group, ANCHOR_NAME);
    if (anchor) {
      anchor.x(localTip.x);
      anchor.y(localTip.y);
    }
    _redrawTailFromAnchor(group);
  }

  // ── re-wire on canvas reload ──────────────────────────────────────────
  // The codec serializes the linkedTarget attr but listeners don't survive
  // a reload. Walk the user layer, attach anchor handles to bubbles, and
  // re-arm follow-update for any with a linkedTarget.
  function _rewireOnReload() {
    var panel = window.OraCanvas && window.OraCanvas.panel;
    if (!panel || !panel.userInputLayer) return;
    var kids = panel.userInputLayer.getChildren();
    for (var i = 0; i < kids.length; i++) {
      var n = kids[i];
      if (!n || typeof n.getClassName !== 'function' || n.getClassName() !== 'Group') continue;
      var kind = n.getAttr && n.getAttr('bubbleKind');
      if (!kind || kind === 'caption') continue;
      _attachTailAnchor(n, panel);
      var linkId = n.getAttr && n.getAttr('linkedTarget');
      if (linkId) {
        var stage = n.getStage && n.getStage();
        var target = stage && typeof stage.findOne === 'function' && stage.findOne('#' + linkId);
        if (target) {
          _wireLinkFollow(n, target, panel);
          _refreshLinkedTail(n, panel);
        }
      }
    }
  }

  if (typeof document !== 'undefined') {
    document.addEventListener('ora:canvas-loaded', _rewireOnReload);
    document.addEventListener('ora:canvas-mounted', function () {
      // Some bubble placement happens before this event listener exists; rewire
      // once on mount to catch any pre-existing bubbles.
      setTimeout(_rewireOnReload, 100);
    });
  }

  // ── activate-then-place mode ──────────────────────────────────────────

  var _armed = null; // { panel, kind, off: cleanup }

  function _disarm() {
    if (!_armed) return;
    if (typeof _armed.off === 'function') _armed.off();
    _armed = null;
  }

  function activateTool(panel, kind) {
    if (!panel || !panel.stage) return;
    _disarm();

    // Visual hint: change cursor to crosshair while armed.
    var konvaEl = panel._konvaEl || (panel.el && panel.el.querySelector && panel.el.querySelector('.konvajs-content'));
    if (konvaEl) konvaEl.style.cursor = 'crosshair';

    function onPointerDown(e) {
      // Use stage-relative coordinates corrected for current zoom/pan.
      var pos;
      try {
        var ptr = panel.stage.getPointerPosition();
        if (panel._stagePoint) {
          pos = panel._stagePoint(ptr);
        } else {
          // Fallback — assume layer-local space matches pointer.
          pos = ptr;
        }
      } catch (err) { pos = { x: 100, y: 100 }; }

      // Center the bubble on the click point.
      placeAt(panel, kind, pos.x - DEFAULT_W / 2, pos.y - DEFAULT_H / 2);
      _disarm();
    }

    function onEsc(e) {
      if (e.key === 'Escape') _disarm();
    }

    panel.stage.on('mousedown.bubble touchstart.bubble', onPointerDown);
    document.addEventListener('keydown', onEsc);

    _armed = {
      panel: panel,
      kind:  kind,
      off:   function () {
        try { panel.stage.off('mousedown.bubble touchstart.bubble'); } catch (e) {}
        document.removeEventListener('keydown', onEsc);
        if (konvaEl) konvaEl.style.cursor = '';
      }
    };
  }

  window.OraV3BubbleTools = {
    placeAt: placeAt,
    activateTool: activateTool,
    _disarm: _disarm
  };
})();
