/**
 * export-svg.js — WP-7.4.9b
 *
 * Implements the **Export → SVG** command per Visual Intelligence
 * Implementation Plan §11.7 ("Canvas Mechanics — Export") + §13.4 WP-7.4.9b.
 *
 *   Photoshop equivalent:  File → Export → Export As… → SVG
 *
 * ── Architecture ────────────────────────────────────────────────────────────
 *
 * Self-registering IIFE that lives alongside `save-canvas.js` (WP-7.4.8) and
 * `export-png.js` (WP-7.4.9a, sibling). Per Plan §13 each export sub-WP gets
 * its own module so parallel work doesn't collide on `visual-panel.js`.
 *
 * The module walks the live Konva 4-layer model that VisualPanel exposes
 * (`backgroundLayer` / `annotationLayer` / `userInputLayer` /
 * `selectionLayer`), emits SVG primitives for each shape, embeds raster
 * images as `<image href="data:..."/>`, and triggers a browser download via
 * an anchor + `download` attr.
 *
 * ── Bounding (Plan §11.7) ──────────────────────────────────────────────────
 *
 * Like Save, Export bounds the output to:
 *
 *     bbox(all rendered objects) + 100 px margin on each side
 *
 * Reuses `OraSaveCanvas.computeContentExtent` so the bound scope is identical
 * — a Save and an Export of the same scene cover the same region. Empty
 * canvases produce a minimal 200×200 SVG (just the margin pad).
 *
 * ── Konva → SVG translation ─────────────────────────────────────────────────
 *
 * Per shape kind:
 *
 *   rect          → <rect x y width height fill stroke stroke-width/>
 *   ellipse       → <ellipse cx cy rx ry .../>
 *   diamond       → <polygon points=".../>" (Konva diamond is a closed Line)
 *   line          → <polyline points=".../>" (or <line> for 2-point)
 *   arrow         → <line .../> + <polygon> arrowhead marker
 *   text          → <text x y font-size font-family fill>...</text>
 *
 * Annotations (annotationKind):
 *   callout       → <g> with rect background + text + arrow tail
 *   highlight     → <rect fill-opacity=0.3/>
 *   strikethrough → <line stroke-width=2/>
 *   sticky        → <g> with rect + text
 *   pen           → <polyline fill=none/>
 *
 * Background:
 *   SVG host      → embedded inline (the source SVG markup is already SVG;
 *                   we wrap the inner contents in a <g transform=".../>")
 *   raster image  → <image href="data:image/...;base64,..." width height/>
 *
 * Image-heavy scenes inflate fast: each base64 raster doubles its byte
 * count. Module header recommends PNG (WP-7.4.9a) for those. Diagrammatic
 * content (shapes + text + thin annotations) stays compact and crisp at any
 * zoom — that's where SVG wins.
 *
 * ── Public surface — exposed as `window.OraExportSVG` ──────────────────────
 *
 *   buildSvgString(panel, opts?) → string
 *     Pure helper. Walks panel layers and returns a complete SVG document
 *     string (xmlns + viewBox + content). Bounds to content extent + margin.
 *     `opts`:
 *       {
 *         marginPx?: number,         // default 100
 *         pretty?:   boolean,        // emit newlines + indents (debug)
 *         includeBackground?: bool,  // default true
 *         includeAnnotations?: bool, // default true
 *       }
 *
 *   exportNow(panel, opts?) → Promise<{ ok, bytes, filename, extent }>
 *     Build SVG, dispatch `ora:canvas-pre-share` with intent='export', then
 *     trigger a download via anchor + `download` attr. Returns Promise that
 *     resolves AFTER the download click was synthesized (the browser then
 *     handles the file picker / save dialog asynchronously). When
 *     `opts.dryRun=true` the click is suppressed and bytes are returned.
 *     `opts`:
 *       {
 *         marginPx?: number,         // default 100
 *         filename?: string,         // default '<conversation>-canvas.svg'
 *         dryRun?:   boolean,        // tests
 *         includeBackground?: bool,
 *         includeAnnotations?: bool,
 *       }
 *
 *   init() → void
 *     Idempotent boot wiring. Currently a no-op (no panel hook required —
 *     export is invoked on demand from the command bar / chat panel).
 *     Reserved for future menu binding.
 *
 * ── Constraints ─────────────────────────────────────────────────────────────
 *
 *   * Pure, stateless module (no per-panel state).
 *   * Touches no other module — only reads Konva nodes and calls
 *     `OraSaveCanvas.computeContentExtent` (when available; falls back to
 *     a local copy if the save module isn't loaded).
 *   * Test mode: `opts.dryRun=true` returns bytes without touching DOM
 *     (no anchor click, no URL.createObjectURL).
 *
 * ── Caveat documented per WP brief ─────────────────────────────────────────
 *
 *   Image-heavy compositions (multi-megapixel raster backdrops, photo-stuffed
 *   collages) emit a giant SVG full of base64 image strings — file sizes can
 *   easily exceed an equivalent PNG by 3–4×. For those scenes, prefer the
 *   PNG export (WP-7.4.9a). SVG export is best-suited to diagrammatic
 *   content: shapes, text, annotations, thin connectors.
 */

(function (root) {
  'use strict';

  // ── Constants ─────────────────────────────────────────────────────────────

  var DEFAULT_MARGIN_PX = 100;          // Plan §11.7
  var SVG_NS            = 'http://www.w3.org/2000/svg';
  var XLINK_NS          = 'http://www.w3.org/1999/xlink';

  // ── Helpers ───────────────────────────────────────────────────────────────

  function _isObj(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }
  function _isFiniteNumber(v) { return typeof v === 'number' && isFinite(v); }
  function _isPositiveNumber(v) { return _isFiniteNumber(v) && v > 0; }

  function _getSave() {
    return (typeof window !== 'undefined' && window.OraSaveCanvas) || null;
  }
  function _getReminder() {
    return (typeof window !== 'undefined' && window.OraCanvasShareReminder) || null;
  }

  /**
   * Escape user text for safe insertion as XML character data.
   * Five-character escape covers what XML 1.0 §2.4 mandates plus the two
   * attribute-quote chars we need for serializing attributes.
   */
  function _xmlEscape(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&apos;');
  }

  /**
   * Format a number for SVG attribute output. Trims trailing zeros and
   * caps precision at 3 decimals to keep file size tight.
   */
  function _fmtNum(n) {
    if (!_isFiniteNumber(n)) return '0';
    if (n === Math.floor(n)) return String(n);
    return (Math.round(n * 1000) / 1000).toString();
  }

  /**
   * Serialize an attribute bag into a space-prefixed string of
   * `key="value"` pairs. Skips null/undefined values.
   */
  function _attrs(bag) {
    var out = '';
    for (var k in bag) {
      if (!Object.prototype.hasOwnProperty.call(bag, k)) continue;
      var v = bag[k];
      if (v == null) continue;
      out += ' ' + k + '="' + _xmlEscape(v) + '"';
    }
    return out;
  }

  // Local copy of computeContentExtent that works against live Konva nodes
  // (rather than serialized canvas-state objects). We prefer to delegate to
  // OraSaveCanvas when it's loaded; this is the fallback.
  function _computeKonvaExtent(panel, marginPx) {
    var margin = _isFiniteNumber(marginPx) ? marginPx : DEFAULT_MARGIN_PX;
    var minX =  Infinity, minY =  Infinity;
    var maxX = -Infinity, maxY = -Infinity;
    var any = false;

    function _absorb(x, y, w, h) {
      if (!_isFiniteNumber(x) || !_isFiniteNumber(y)) return;
      var ww = _isFiniteNumber(w) ? w : 0;
      var hh = _isFiniteNumber(h) ? h : 0;
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x + ww > maxX) maxX = x + ww;
      if (y + hh > maxY) maxY = y + hh;
      any = true;
    }

    function _walk(layer) {
      if (!layer || typeof layer.getChildren !== 'function') return;
      var children = layer.getChildren();
      for (var i = 0; i < children.length; i++) {
        var n = children[i];
        if (!n) continue;
        var x = (typeof n.x === 'function') ? n.x() : 0;
        var y = (typeof n.y === 'function') ? n.y() : 0;
        var w = (typeof n.width === 'function')  ? n.width()  : 0;
        var h = (typeof n.height === 'function') ? n.height() : 0;
        _absorb(x, y, w, h);
      }
    }

    _walk(panel && panel.userInputLayer);
    _walk(panel && panel.annotationLayer);
    _walk(panel && panel.backgroundLayer);
    if (!any) return null;
    return {
      x:      minX - margin,
      y:      minY - margin,
      width:  (maxX - minX) + margin * 2,
      height: (maxY - minY) + margin * 2,
    };
  }

  // ── Konva → SVG primitive emitters ────────────────────────────────────────

  /**
   * Convert a Konva user-input shape into an SVG element string. Returns
   * '' when the shape isn't recognized (silently dropped — preview shapes
   * for drags-in-flight, selection rects, etc.).
   */
  function _userShapeToSvg(node) {
    if (!node) return '';
    var attrs = (node.attrs && _isObj(node.attrs)) ? node.attrs : {};
    var typ = attrs.userShapeType;
    if (!typ) return '';
    if (attrs.name === 'user-shape-preview') return '';

    var x = (typeof node.x === 'function') ? node.x() : 0;
    var y = (typeof node.y === 'function') ? node.y() : 0;
    var w = (typeof node.width  === 'function') ? node.width()  : (attrs.width  || 0);
    var h = (typeof node.height === 'function') ? node.height() : (attrs.height || 0);

    var fill        = (typeof attrs.fill   === 'string') ? attrs.fill   : 'none';
    var stroke      = (typeof attrs.stroke === 'string') ? attrs.stroke : '#000';
    var strokeWidth = _isPositiveNumber(attrs.strokeWidth) ? attrs.strokeWidth : 1;

    if (typ === 'rect') {
      return '<rect' + _attrs({
        x: _fmtNum(x), y: _fmtNum(y),
        width: _fmtNum(w), height: _fmtNum(h),
        fill: fill, stroke: stroke, 'stroke-width': _fmtNum(strokeWidth),
      }) + '/>';
    }
    if (typ === 'ellipse') {
      var rx = w / 2, ry = h / 2;
      return '<ellipse' + _attrs({
        cx: _fmtNum(x + rx), cy: _fmtNum(y + ry),
        rx: _fmtNum(rx),     ry: _fmtNum(ry),
        fill: fill, stroke: stroke, 'stroke-width': _fmtNum(strokeWidth),
      }) + '/>';
    }
    if (typ === 'diamond') {
      // Konva diamond is a closed Line with 4 points (top, right, bottom,
      // left of the bounding box).
      var cx = x + w / 2, cy = y + h / 2;
      var pts = [
        cx + ',' + y,
        (x + w) + ',' + cy,
        cx + ',' + (y + h),
        x + ',' + cy,
      ].join(' ');
      return '<polygon' + _attrs({
        points: pts,
        fill: fill, stroke: stroke, 'stroke-width': _fmtNum(strokeWidth),
      }) + '/>';
    }
    if (typ === 'line') {
      var pts2 = _pointsFromAttrs(attrs, x, y);
      if (!pts2) return '';
      return '<polyline' + _attrs({
        points: pts2, fill: 'none', stroke: stroke,
        'stroke-width': _fmtNum(strokeWidth),
      }) + '/>';
    }
    if (typ === 'arrow') {
      var pts3 = _pointsFromAttrs(attrs, x, y);
      if (!pts3) return '';
      // Render as polyline + a triangle arrowhead at the last segment.
      var raw = (attrs.points || []);
      var n = raw.length;
      var x1 = (raw[n - 4] || 0) + x;
      var y1 = (raw[n - 3] || 0) + y;
      var x2 = (raw[n - 2] || 0) + x;
      var y2 = (raw[n - 1] || 0) + y;
      var head = _arrowHead(x1, y1, x2, y2, strokeWidth * 4, stroke);
      return '<polyline' + _attrs({
        points: pts3, fill: 'none', stroke: stroke,
        'stroke-width': _fmtNum(strokeWidth),
      }) + '/>' + head;
    }
    if (typ === 'text') {
      var t = (typeof attrs.text === 'string') ? attrs.text : '';
      var font = (typeof attrs.fontFamily === 'string') ? attrs.fontFamily : 'sans-serif';
      var size = _isPositiveNumber(attrs.fontSize) ? attrs.fontSize : 16;
      var color = (typeof attrs.fill === 'string') ? attrs.fill : '#000';
      // SVG text y is the baseline — bias by the font size so it visually
      // matches Konva's top-aligned text rendering.
      return '<text' + _attrs({
        x: _fmtNum(x), y: _fmtNum(y + size),
        'font-family': font, 'font-size': _fmtNum(size),
        fill: color,
      }) + '>' + _xmlEscape(t) + '</text>';
    }
    return '';
  }

  /**
   * Convert Konva line points (relative to node x/y) into an SVG points
   * string in absolute coords.
   */
  function _pointsFromAttrs(attrs, x, y) {
    var raw = attrs && attrs.points;
    if (!raw || !raw.length || raw.length < 4) return '';
    if (raw.length % 2 !== 0) return '';
    var parts = [];
    for (var i = 0; i < raw.length; i += 2) {
      parts.push(_fmtNum(raw[i] + x) + ',' + _fmtNum(raw[i + 1] + y));
    }
    return parts.join(' ');
  }

  /**
   * Build a simple triangle arrowhead at (x2, y2), pointing along the
   * (x1, y1) → (x2, y2) vector. Returns an SVG polygon string.
   */
  function _arrowHead(x1, y1, x2, y2, size, stroke) {
    var dx = x2 - x1, dy = y2 - y1;
    var len = Math.sqrt(dx * dx + dy * dy);
    if (len < 1e-6) return '';
    var ux = dx / len, uy = dy / len;
    var px = -uy, py = ux;          // perpendicular unit
    var bx = x2 - ux * size;
    var by = y2 - uy * size;
    var ax = bx + px * (size / 2);
    var ay = by + py * (size / 2);
    var cx = bx - px * (size / 2);
    var cy = by - py * (size / 2);
    var pts = _fmtNum(x2) + ',' + _fmtNum(y2) + ' ' +
              _fmtNum(ax) + ',' + _fmtNum(ay) + ' ' +
              _fmtNum(cx) + ',' + _fmtNum(cy);
    return '<polygon' + _attrs({ points: pts, fill: stroke, stroke: stroke }) + '/>';
  }

  /**
   * Convert a Konva annotation node into an SVG element string. Only emits
   * for user-authored annotations (annotationSource='user').
   */
  function _annotationToSvg(node) {
    if (!node) return '';
    var attrs = (node.attrs && _isObj(node.attrs)) ? node.attrs : {};
    if (attrs.annotationSource !== 'user') return '';
    var kind = attrs.annotationKind;
    if (!kind) return '';

    var x = (typeof node.x === 'function') ? node.x() : 0;
    var y = (typeof node.y === 'function') ? node.y() : 0;
    var w = (typeof node.width  === 'function') ? node.width()  : 0;
    var h = (typeof node.height === 'function') ? node.height() : 0;
    var stroke = (typeof attrs.stroke === 'string') ? attrs.stroke : '#cc4400';
    var fill   = (typeof attrs.fill   === 'string') ? attrs.fill   : '#ffec80';

    if (kind === 'highlight') {
      return '<rect' + _attrs({
        x: _fmtNum(x), y: _fmtNum(y),
        width: _fmtNum(w), height: _fmtNum(h),
        fill: fill, 'fill-opacity': '0.3', stroke: 'none',
      }) + '/>';
    }
    if (kind === 'strikethrough') {
      var pts = _pointsFromAttrs(attrs, x, y);
      if (!pts) return '';
      return '<polyline' + _attrs({
        points: pts, fill: 'none', stroke: stroke, 'stroke-width': '2',
      }) + '/>';
    }
    if (kind === 'pen') {
      var pts2 = _pointsFromAttrs(attrs, x, y);
      if (!pts2) return '';
      return '<polyline' + _attrs({
        points: pts2, fill: 'none', stroke: stroke, 'stroke-width': '2',
      }) + '/>';
    }
    if (kind === 'sticky' || kind === 'callout') {
      var text = (typeof attrs.text === 'string') ? attrs.text : '';
      var sw = _isPositiveNumber(w) ? w : 120;
      var sh = _isPositiveNumber(h) ? h : 60;
      var bg = '<rect' + _attrs({
        x: _fmtNum(x), y: _fmtNum(y),
        width: _fmtNum(sw), height: _fmtNum(sh),
        fill: fill, stroke: stroke, 'stroke-width': '1',
      }) + '/>';
      var tx = '<text' + _attrs({
        x: _fmtNum(x + 6), y: _fmtNum(y + 18),
        'font-family': 'sans-serif', 'font-size': '12', fill: '#222',
      }) + '>' + _xmlEscape(text) + '</text>';
      return '<g>' + bg + tx + '</g>';
    }
    return '';
  }

  /**
   * Emit SVG for the background layer — either an inline SVG host (we wrap
   * its inner contents inside a <g>) or a raster Konva.Image (embedded as
   * <image href="data:..."/>).
   */
  function _backgroundToSvg(panel) {
    if (!panel) return '';
    var out = '';
    // (1) SVG host
    if (panel._svgHost) {
      var hostSvg = panel._svgHost.querySelector('svg');
      if (hostSvg) {
        // Pull the children of the source SVG and wrap in <g>. We avoid
        // nesting <svg> inside <svg> — different viewBoxes bite.
        var inner = '';
        for (var i = 0; i < hostSvg.childNodes.length; i++) {
          var c = hostSvg.childNodes[i];
          if (c.nodeType === 1 /* Element */) {
            try {
              var serializer = (typeof XMLSerializer !== 'undefined') ? new XMLSerializer() : null;
              inner += serializer ? serializer.serializeToString(c) : (c.outerHTML || '');
            } catch (e) { /* skip */ }
          }
        }
        if (inner) out += '<g class="ora-bg-svg">' + inner + '</g>';
      }
    }
    // (2) Raster background
    if (panel._pendingImage && typeof panel._pendingImage.dataUrl === 'string') {
      var url = panel._pendingImage.dataUrl;
      var node = panel._backgroundImageNode;
      var bx = node && typeof node.x === 'function' ? node.x() : 0;
      var by = node && typeof node.y === 'function' ? node.y() : 0;
      var bw = node && typeof node.width  === 'function' ? node.width()  : 0;
      var bh = node && typeof node.height === 'function' ? node.height() : 0;
      var imgAttrs = {
        x: _fmtNum(bx), y: _fmtNum(by),
        width: _fmtNum(bw), height: _fmtNum(bh),
        href: url,
      };
      // SVG 2 uses `href`; SVG 1.1 uses `xlink:href`. Emit both for max
      // viewer compatibility (browsers accept either; vector-graphics
      // editors like Inkscape historically prefer xlink:).
      imgAttrs['xlink:href'] = url;
      out += '<image' + _attrs(imgAttrs) + '/>';
    }
    return out;
  }

  // ── buildSvgString ────────────────────────────────────────────────────────

  /**
   * Build the complete SVG document string for the panel's current scene.
   * Bounded to content + margin. Returns a string ready to drop into a
   * Blob, write to disk, or return from a tool.
   */
  function buildSvgString(panel, opts) {
    opts = opts || {};
    var marginPx = _isFiniteNumber(opts.marginPx) ? opts.marginPx : DEFAULT_MARGIN_PX;
    var includeBg     = (opts.includeBackground  !== false);
    var includeAnnos  = (opts.includeAnnotations !== false);
    var pretty        = !!opts.pretty;
    var nl = pretty ? '\n' : '';
    var indent = pretty ? '  ' : '';

    // Bound to content. Prefer the save module's helper (canonical) but fall
    // back to walking Konva nodes directly when save-canvas isn't loaded.
    var save = _getSave();
    var extent = null;
    if (save && typeof save.computeContentExtent === 'function' &&
        typeof save.buildCanvasState === 'function') {
      try {
        var s = save.buildCanvasState(panel);
        extent = save.computeContentExtent(s, marginPx);
      } catch (e) { extent = null; }
    }
    if (!extent) extent = _computeKonvaExtent(panel, marginPx);

    var w, h, viewX, viewY;
    if (extent) {
      w = extent.width;  h = extent.height;
      viewX = extent.x;  viewY = extent.y;
    } else {
      // Empty canvas — emit a minimal margin-only document so downstream
      // viewers don't choke on width=0.
      w = marginPx * 2; h = marginPx * 2;
      viewX = 0; viewY = 0;
    }

    var headerAttrs = _attrs({
      xmlns:        SVG_NS,
      'xmlns:xlink': XLINK_NS,
      width:        _fmtNum(w),
      height:       _fmtNum(h),
      viewBox:      _fmtNum(viewX) + ' ' + _fmtNum(viewY) + ' ' +
                    _fmtNum(w) + ' ' + _fmtNum(h),
      version:      '1.1',
    });
    var parts = [];
    parts.push('<?xml version="1.0" encoding="UTF-8"?>');
    parts.push('<svg' + headerAttrs + '>');
    parts.push(indent + '<title>Ora Canvas Export</title>');

    // (1) Background
    if (includeBg) {
      var bg = _backgroundToSvg(panel);
      if (bg) parts.push(indent + bg);
    }

    // (2) User input shapes
    if (panel && panel.userInputLayer && typeof panel.userInputLayer.getChildren === 'function') {
      var shapes = panel.userInputLayer.getChildren();
      for (var i = 0; i < shapes.length; i++) {
        var svg = _userShapeToSvg(shapes[i]);
        if (svg) parts.push(indent + svg);
      }
    }

    // (3) User annotations (last so they overlay)
    if (includeAnnos &&
        panel && panel.annotationLayer && typeof panel.annotationLayer.getChildren === 'function') {
      var ann = panel.annotationLayer.getChildren();
      for (var j = 0; j < ann.length; j++) {
        var asvg = _annotationToSvg(ann[j]);
        if (asvg) parts.push(indent + asvg);
      }
    }

    parts.push('</svg>');
    return parts.join(nl);
  }

  // ── exportNow ─────────────────────────────────────────────────────────────

  /**
   * Trigger a browser download of the SVG via anchor + `download` attr.
   * Dispatches `ora:canvas-pre-share` with intent='export' before the click
   * so the share-reminder module (WP-7.7.6) can gate the action when the
   * canvas leaves the per-conversation directory.
   */
  function exportNow(panel, opts) {
    opts = opts || {};
    if (!panel) return Promise.reject(new Error('export-svg: panel is required'));

    var conversationId =
      (panel.config && panel.config.conversation_id) || 'main';
    var filename = (typeof opts.filename === 'string' && opts.filename) ||
                   (conversationId + '-canvas.svg');
    var marginPx = _isFiniteNumber(opts.marginPx) ? opts.marginPx : DEFAULT_MARGIN_PX;

    var bytes = buildSvgString(panel, {
      marginPx:           marginPx,
      pretty:             !!opts.pretty,
      includeBackground:  opts.includeBackground,
      includeAnnotations: opts.includeAnnotations,
    });

    var save = _getSave();
    var extent = null;
    if (save && typeof save.computeContentExtent === 'function' &&
        typeof save.buildCanvasState === 'function') {
      try {
        extent = save.computeContentExtent(save.buildCanvasState(panel), marginPx);
      } catch (e) { extent = null; }
    }

    function _download() {
      if (typeof document === 'undefined' || typeof URL === 'undefined' ||
          typeof URL.createObjectURL !== 'function') {
        return; // headless / test mode without DOM
      }
      var blob = new Blob([bytes], { type: 'image/svg+xml' });
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.style.position = 'fixed';
      a.style.left = '-9999px';
      document.body.appendChild(a);
      try { a.click(); } catch (e) { /* tests / SSR */ }
      // Defer revoke so the browser has time to start the download.
      try {
        setTimeout(function () {
          try { URL.revokeObjectURL(url); } catch (e2) {}
          if (a.parentNode) a.parentNode.removeChild(a);
        }, 1000);
      } catch (e3) {}
    }

    return new Promise(function (resolve) {
      var done = function () {
        if (!opts.dryRun) _download();
        resolve({ ok: true, bytes: bytes, filename: filename, extent: extent });
      };
      var cancelled = function () {
        resolve({ ok: false, cancelled: true, reason: 'share-cancelled' });
      };

      // Share-reminder gate: export → file system always counts as
      // audience-expansion, so route through the reminder when available.
      var reminder = _getReminder();
      if (reminder && typeof reminder.requestShare === 'function') {
        reminder.requestShare({
          intent:    'export',
          path:      filename,
          onConfirm: done,
          onCancel:  cancelled,
        });
        return;
      }

      // Fallback: dispatch the CustomEvent for any non-modal listeners,
      // then proceed. The share-reminder module would normally subscribe
      // and gate; absent it, export proceeds.
      if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
        try {
          var evt = new CustomEvent('ora:canvas-pre-share', {
            detail: {
              path:      filename,
              intent:    'export',
              onConfirm: done,
              onCancel:  cancelled,
            },
          });
          window.dispatchEvent(evt);
          // If nothing handled the event, proceed.
          done();
          return;
        } catch (e) { /* CustomEvent unavailable; fall through */ }
      }
      done();
    });
  }

  // ── Boot wiring ──────────────────────────────────────────────────────────

  var _booted = false;

  function init() {
    if (_booted) return;
    _booted = true;
    // No panel hook needed — export runs on demand. Reserved for future
    // command-bar / menu binding once WP-7.5 ships the command palette.
  }

  if (typeof window !== 'undefined') {
    if (typeof setTimeout === 'function') setTimeout(init, 0);
    else init();
  }

  // ── Module export ────────────────────────────────────────────────────────

  var ns = {
    DEFAULT_MARGIN_PX: DEFAULT_MARGIN_PX,
    buildSvgString:    buildSvgString,
    exportNow:         exportNow,
    init:              init,
    // Internals exposed for tests.
    _userShapeToSvg:    _userShapeToSvg,
    _annotationToSvg:   _annotationToSvg,
    _backgroundToSvg:   _backgroundToSvg,
    _computeKonvaExtent: _computeKonvaExtent,
    _xmlEscape:         _xmlEscape,
    _fmtNum:            _fmtNum,
    _arrowHead:         _arrowHead,
  };

  if (typeof window !== 'undefined') {
    window.OraExportSVG = ns;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = ns;
  }
})(typeof window !== 'undefined' ? window : this);
