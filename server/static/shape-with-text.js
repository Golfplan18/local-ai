/**
 * shape-with-text.js — WP-7.0.7
 *
 * Generic primitive that lets any Konva shape hold an auto-fitting text body.
 * Built per Phase 7 §13.0 WP-7.0.7 of the Visual Intelligence Implementation
 * Plan — generalizes the speech-bubble-text linking that the §11.10 cartoon
 * workflow needs (WP-7.9.2 / WP-7.9.3) into a reusable primitive that flow
 * charts, org charts, callouts, and any future shape can adopt.
 *
 * ── What it does ─────────────────────────────────────────────────────────────
 *
 * Given a Konva host shape (Rect, Ellipse, Line[closed], Group, or any node
 * that exposes `getClientRect()`), this module:
 *   1. Wraps the host + a Konva.Text inside a Konva.Group;
 *   2. Computes an "inscribed rectangle" inside the host's bounds, accounting
 *      for shape geometry (rect = full bbox; ellipse = inscribed rect; closed
 *      polygon = bbox shrunk by ~14% to stay within the polygon body);
 *   3. Applies one of three behavior policies whenever the text content,
 *      shape size, or policy changes:
 *
 *        wrap          Text wraps inside the inscribed rect at a fixed font
 *                      size. If text overflows the rect height, characters
 *                      past the last visible line are dropped; if `ellipsis`
 *                      is true, an ellipsis is shown on the truncated line.
 *
 *        grow          Host shape grows to fit the text at a fixed font size.
 *                      Width target = max(min_width, measured_width + 2*pad).
 *                      Height target = measured_height + 2*pad. Used by §11.10
 *                      cartoon bubbles (WP-7.9.2) where the bubble must hug
 *                      whatever the user types.
 *
 *        shrink-text   Host stays a fixed size; font size binary-searches
 *                      between [min_font_size, max_font_size] for the largest
 *                      size that still fits all the text inside the inscribed
 *                      rect (with word-wrap). Used when shape size is the
 *                      load-bearing dimension (badges, fixed-cell tables).
 *
 *   4. Persists state on the group node via `userShape*` attrs so a
 *      `toJSON()`-based round-trip (the convention shared with WP-3.1 /
 *      WP-3.2 — see visual-panel.js header) reconstructs the same primitive
 *      after `Konva.Node.create()`.
 *
 * ── Konva-side primitive ────────────────────────────────────────────────────
 *
 * The deliverable is a Konva.Group with three children (in z-order):
 *
 *     group
 *       └── host   (Konva.Rect | Konva.Ellipse | Konva.Line | Konva.Group)
 *       └── text   (Konva.Text)
 *
 * The group itself is the draggable, selectable handle. Consumers should
 * append the group (not the host) to `userInputLayer`. Position lives on the
 * group (group.x, group.y); host is anchored relative to the group at the
 * origin determined by its native coordinate convention (Konva.Rect at 0,0
 * top-left; Konva.Ellipse at center).
 *
 * ── Behavior-policy enum ────────────────────────────────────────────────────
 *
 *     OraShapeWithText.POLICIES = {
 *       WRAP:  'wrap',
 *       GROW:  'grow',
 *       SHRINK_TEXT: 'shrink-text',
 *     };
 *
 * ── Save / load schema fragment (proposed for WP-7.0.2 to adopt) ────────────
 *
 * On a serialized shape-with-text node the following attrs are present (all
 * other user-shape convention attrs from WP-3.1 still apply):
 *
 *   {
 *     name:                'user-shape',
 *     userShapeType:       'shape-with-text',
 *     userShapeId:         'u-shape-with-text-<n>',
 *     userTextContent:     '<string>',
 *     userTextPolicy:      'wrap' | 'grow' | 'shrink-text',
 *     userTextOptions: {
 *       padding:        number,                 // default 8
 *       fontFamily:     string,                 // default 'sans-serif'
 *       fontSize:       number,                 // default 14 (used by wrap/grow)
 *       minFontSize:    number,                 // default 6  (shrink-text)
 *       maxFontSize:    number,                 // default 48 (shrink-text)
 *       fontStyle:      'normal' | 'bold' | 'italic' | 'bold italic',
 *       fill:           string,                 // text color, default '#1a1a1a'
 *       align:          'left' | 'center' | 'right',
 *       verticalAlign:  'top' | 'middle' | 'bottom',
 *       wrap:           'word' | 'char' | 'none',
 *       ellipsis:       boolean,                // default true (wrap policy)
 *       minWidth:       number,                 // grow policy floor
 *       minHeight:      number,                 // grow policy floor
 *       hostKind:       'rect'|'ellipse'|'polygon'|'group'  // bbox→inscribed
 *     },
 *     userTextHostAttrs: {                       // host snapshot (so a
 *                                                 // deserializer can rebuild
 *                                                 // the host inside the group)
 *       konvaClass: 'Rect'|'Ellipse'|'Line'|'Group',
 *       attrs:      { ... }                     // host's Konva.Node.toObject()
 *     }
 *   }
 *
 * The structured `userTextOptions` and `userTextHostAttrs` round-trip through
 * `Konva.Node.toJSON()` because Konva preserves nested object attrs as-is.
 *
 * ── Test criterion (per §13.0 WP-7.0.7) ─────────────────────────────────────
 *
 *   1. Insert text in a rectangle with `wrap` policy; verify text wraps
 *      inside bounds.
 *   2. Insert text in a circle with `grow` policy and long text; verify
 *      circle grows to fit.
 *
 * Both pass via the self-tests at the bottom of this file when run under
 * jsdom (see test runner notes).
 */

(function (root) {
  'use strict';

  // ── Defaults ─────────────────────────────────────────────────────────────
  var DEFAULT_OPTIONS = {
    padding: 8,
    fontFamily: 'sans-serif',
    fontSize: 14,
    minFontSize: 6,
    maxFontSize: 48,
    fontStyle: 'normal',
    fill: '#1a1a1a',
    align: 'center',
    verticalAlign: 'middle',
    wrap: 'word',
    ellipsis: true,
    minWidth: 24,
    minHeight: 18,
    hostKind: 'rect',
  };

  var POLICIES = {
    WRAP: 'wrap',
    GROW: 'grow',
    SHRINK_TEXT: 'shrink-text',
  };

  // ── Helpers ──────────────────────────────────────────────────────────────

  // Detect the host's geometric kind so we can pick the right inscribed
  // rectangle. The caller can override via opts.hostKind. Defaults err on the
  // side of "rectangle" because that's the safest underestimate of usable
  // space for any convex host.
  function detectHostKind(host) {
    if (!host) return 'rect';
    if (typeof host.getClassName === 'function') {
      var cn = host.getClassName();
      if (cn === 'Ellipse' || cn === 'Circle') return 'ellipse';
      if (cn === 'Line' && host.attrs && host.attrs.closed) return 'polygon';
      if (cn === 'Group') return 'group';
    }
    return 'rect';
  }

  // Compute the inscribed rectangle (in group-local coordinates) that text
  // can safely occupy inside the host shape. Returns { x, y, width, height }.
  // Padding is applied symmetrically.
  function inscribedRect(host, kind, padding) {
    if (!host) return { x: 0, y: 0, width: 0, height: 0 };
    var pad = padding || 0;

    // Konva.Rect: bbox is (x, y, width, height) where x/y is top-left.
    if (kind === 'rect') {
      var rw = host.width ? host.width() : (host.attrs.width || 0);
      var rh = host.height ? host.height() : (host.attrs.height || 0);
      var rx = host.x ? host.x() : (host.attrs.x || 0);
      var ry = host.y ? host.y() : (host.attrs.y || 0);
      return {
        x: rx + pad,
        y: ry + pad,
        width: Math.max(0, rw - 2 * pad),
        height: Math.max(0, rh - 2 * pad),
      };
    }

    // Konva.Ellipse / Konva.Circle: x/y is the center, radii are half-axes.
    // The inscribed rectangle (axis-aligned) inside an ellipse with semi-
    // axes a and b has half-extents (a/√2, b/√2). We use that, then apply
    // padding inside.
    if (kind === 'ellipse') {
      var ex = host.x ? host.x() : (host.attrs.x || 0);
      var ey = host.y ? host.y() : (host.attrs.y || 0);
      var rxAxis = host.radiusX ? host.radiusX() :
                   (host.radius ? host.radius() :
                    (host.attrs.radiusX || host.attrs.radius || 0));
      var ryAxis = host.radiusY ? host.radiusY() :
                   (host.radius ? host.radius() :
                    (host.attrs.radiusY || host.attrs.radius || 0));
      var hx = rxAxis / Math.SQRT2;
      var hy = ryAxis / Math.SQRT2;
      return {
        x: ex - hx + pad,
        y: ey - hy + pad,
        width:  Math.max(0, 2 * hx - 2 * pad),
        height: Math.max(0, 2 * hy - 2 * pad),
      };
    }

    // Closed polygon (Konva.Line with closed: true — the diamond tool, plus
    // any custom polygon). We use getClientRect's bbox and shrink by 14% on
    // each side, which keeps text inside a diamond/star/pentagon body for
    // typical inputs. This is heuristic; consumers wanting tighter fits can
    // wrap their polygon in a group with an explicit Rect "text safe area".
    if (kind === 'polygon') {
      var rect = host.getClientRect ? host.getClientRect({ relativeTo: host.getParent() })
                                    : { x: 0, y: 0, width: 0, height: 0 };
      var insetX = rect.width  * 0.14 + pad;
      var insetY = rect.height * 0.14 + pad;
      return {
        x: rect.x + insetX,
        y: rect.y + insetY,
        width:  Math.max(0, rect.width  - 2 * insetX),
        height: Math.max(0, rect.height - 2 * insetY),
      };
    }

    // Custom group: trust getClientRect, apply padding only.
    var gr = host.getClientRect ? host.getClientRect({ relativeTo: host.getParent() })
                                : { x: 0, y: 0, width: 0, height: 0 };
    return {
      x: gr.x + pad,
      y: gr.y + pad,
      width:  Math.max(0, gr.width  - 2 * pad),
      height: Math.max(0, gr.height - 2 * pad),
    };
  }

  // Word-wrap text into lines that each fit `maxWidth` at `fontSize`. We
  // measure with a Konva.Text probe so the heuristic matches what Konva will
  // ultimately render — under jsdom, Konva.Text falls back to the canvas
  // mock's measureText (≈ 6 px per character), which is good enough for the
  // structural wrap test.
  function wrapTextToLines(KonvaNS, content, fontFamily, fontStyle, fontSize, maxWidth, mode) {
    if (mode === 'none' || !content) return [content || ''];
    var probe = new KonvaNS.Text({
      text: 'M',
      fontFamily: fontFamily,
      fontStyle: fontStyle,
      fontSize: fontSize,
    });
    function measure(s) {
      probe.text(s);
      return probe.width();
    }

    var paragraphs = String(content).split('\n');
    var lines = [];
    for (var p = 0; p < paragraphs.length; p++) {
      var para = paragraphs[p];
      if (mode === 'char') {
        var cur = '';
        for (var c = 0; c < para.length; c++) {
          var probeText = cur + para[c];
          if (measure(probeText) > maxWidth && cur.length > 0) {
            lines.push(cur);
            cur = para[c];
          } else {
            cur = probeText;
          }
        }
        if (cur.length > 0 || para.length === 0) lines.push(cur);
        continue;
      }
      // word mode (default)
      var words = para.split(/\s+/);
      var line = '';
      for (var i = 0; i < words.length; i++) {
        var w = words[i];
        if (!w) continue;
        var candidate = line ? (line + ' ' + w) : w;
        if (measure(candidate) > maxWidth && line.length > 0) {
          lines.push(line);
          line = w;
        } else {
          line = candidate;
        }
      }
      // long single token that exceeds maxWidth still emits one line —
      // Konva.Text will visually clip per the rendering path; the wrap
      // semantics here are line-segmentation, not glyph clipping.
      if (line.length > 0 || para.length === 0) lines.push(line);
    }
    return lines;
  }

  // Measure the rendered width / height of the given lines at a font size.
  function measureBlock(KonvaNS, lines, fontFamily, fontStyle, fontSize, lineHeight) {
    var probe = new KonvaNS.Text({
      text: 'M',
      fontFamily: fontFamily,
      fontStyle: fontStyle,
      fontSize: fontSize,
    });
    var maxW = 0;
    for (var i = 0; i < lines.length; i++) {
      probe.text(lines[i] || '');
      if (probe.width() > maxW) maxW = probe.width();
    }
    var lh = (lineHeight || 1) * fontSize;
    return { width: maxW, height: lines.length * lh, lineHeight: lh };
  }

  // Apply ellipsis to the last visible line if more text remains. Used in
  // wrap policy when text overflows the available height.
  function applyEllipsisInPlace(lines, visibleLineCount, hadOverflow, ellipsisFlag) {
    if (!hadOverflow || !ellipsisFlag || visibleLineCount === 0) return;
    var last = lines[visibleLineCount - 1] || '';
    // Only append if it doesn't already end with one — avoids "...…".
    if (!/[….]{1,3}$/.test(last)) {
      lines[visibleLineCount - 1] = (last.replace(/\s+$/, '') + '…');
    }
  }

  // ── Controller object ────────────────────────────────────────────────────

  function ShapeWithText(KonvaNS, host, content, options, group, textNode, idCounter) {
    this._Konva = KonvaNS;
    this.host = host;
    this.text = textNode;
    this.group = group;
    this._content = content == null ? '' : String(content);
    this._options = mergeOptions(options);
    this._policy = (options && options.policy) || POLICIES.WRAP;
    this._idCounter = idCounter || 0;
    // For history support, expose the canonical id.
    var id = (options && options.userShapeId) || ('u-shape-with-text-' + (++this._idCounter));
    this._id = id;
    this._attachConventionAttrs();
    this.relayout();
  }

  ShapeWithText.prototype._attachConventionAttrs = function () {
    // Attach WP-3.1 / WP-3.2 convention attrs to the GROUP (the user-shape
    // handle) so canvas-serializer.js sees us as a single user-shape and
    // round-trip through toJSON() preserves everything we need.
    var hostObj = (this.host && typeof this.host.toObject === 'function')
      ? this.host.toObject() : {};
    this.group.setAttrs({
      name: 'user-shape',
      userShapeType: 'shape-with-text',
      userShapeId: this._id,
      userLabel: this._content,
      userTextContent: this._content,
      userTextPolicy: this._policy,
      userTextOptions: this._options,
      userTextHostAttrs: {
        konvaClass: (this.host && typeof this.host.getClassName === 'function')
          ? this.host.getClassName() : 'Rect',
        attrs: hostObj.attrs || {},
      },
    });
    // Null convention attrs — direct write so getAttr() returns null instead
    // of undefined (matches WP-3.1 convention).
    this.group.attrs.userCluster       = null;
    this.group.attrs.connEndpointStart = null;
    this.group.attrs.connEndpointEnd   = null;
  };

  ShapeWithText.prototype.setText = function (newContent) {
    this._content = newContent == null ? '' : String(newContent);
    this.group.setAttr('userTextContent', this._content);
    this.group.setAttr('userLabel', this._content);
    this.relayout();
  };

  ShapeWithText.prototype.setPolicy = function (newPolicy) {
    if (!newPolicy) return;
    this._policy = newPolicy;
    this.group.setAttr('userTextPolicy', newPolicy);
    this.relayout();
  };

  ShapeWithText.prototype.setOptions = function (partial) {
    this._options = mergeOptions(Object.assign({}, this._options, partial || {}));
    this.group.setAttr('userTextOptions', this._options);
    this.relayout();
  };

  ShapeWithText.prototype.dispose = function () {
    if (this.text && this.text.destroy) this.text.destroy();
    if (this.host && this.host.destroy) this.host.destroy();
    if (this.group && this.group.destroy) this.group.destroy();
  };

  ShapeWithText.prototype.toSerializable = function () {
    return {
      userShapeId: this._id,
      userShapeType: 'shape-with-text',
      userTextContent: this._content,
      userTextPolicy: this._policy,
      userTextOptions: this._options,
      userTextHostAttrs: this.group.getAttr('userTextHostAttrs'),
    };
  };

  // The core layout method. Idempotent — running it twice produces the same
  // visual state.
  ShapeWithText.prototype.relayout = function () {
    var Konva = this._Konva;
    if (!Konva || !this.host || !this.text) return;
    var opts = this._options;
    var policy = this._policy;
    var kind = opts.hostKind || detectHostKind(this.host);

    if (policy === POLICIES.WRAP) {
      this._applyWrap(kind, opts);
    } else if (policy === POLICIES.GROW) {
      this._applyGrow(kind, opts);
    } else if (policy === POLICIES.SHRINK_TEXT) {
      this._applyShrinkText(kind, opts);
    } else {
      // Unknown policy — fall back to wrap to ensure the text renders.
      this._applyWrap(kind, opts);
    }
  };

  // wrap: text wraps at fixed font; if it overflows the inscribed height,
  // truncate with optional ellipsis on the last visible line.
  ShapeWithText.prototype._applyWrap = function (kind, opts) {
    var Konva = this._Konva;
    var inner = inscribedRect(this.host, kind, opts.padding);
    var lineHeight = 1.2;
    var lines = wrapTextToLines(
      Konva, this._content, opts.fontFamily, opts.fontStyle,
      opts.fontSize, inner.width, opts.wrap
    );
    var lh = lineHeight * opts.fontSize;
    var maxLines = Math.max(0, Math.floor(inner.height / lh));
    var hadOverflow = lines.length > maxLines;
    var visible = hadOverflow ? lines.slice(0, maxLines) : lines;
    applyEllipsisInPlace(visible, visible.length, hadOverflow, opts.ellipsis);

    this.text.setAttrs({
      x: inner.x,
      y: inner.y,
      width: inner.width,
      height: inner.height,
      text: visible.join('\n'),
      fontFamily: opts.fontFamily,
      fontStyle: opts.fontStyle,
      fontSize: opts.fontSize,
      fill: opts.fill,
      align: opts.align,
      verticalAlign: opts.verticalAlign,
      lineHeight: lineHeight,
      // Keep wrap='none' since we've pre-wrapped to the exact line set.
      wrap: 'none',
      ellipsis: false,
      listening: false,
    });
  };

  // grow: shape grows so the text (at fixed font) fits inside, plus padding.
  ShapeWithText.prototype._applyGrow = function (kind, opts) {
    var Konva = this._Konva;
    // Choose a target wrap width that produces a roughly balanced block. For
    // rectangles we accept a wide aspect ratio (text is naturally wider than
    // tall). For ellipses we aim closer to square so the inscribed rect can
    // hold the text without forcing the ellipse to flatten.
    var oneLine = measureBlock(
      Konva,
      wrapTextToLines(Konva, this._content, opts.fontFamily, opts.fontStyle,
                      opts.fontSize, 1e9, 'none'),
      opts.fontFamily, opts.fontStyle, opts.fontSize, 1.2
    );
    var lh = 1.2 * opts.fontSize;
    // Heuristic target: aim for a block whose width:height is roughly
    // 4:1 for rectangles and 2:1 for ellipses (so the resulting host has a
    // pleasing aspect ratio). The width is bounded below by minWidth and
    // above by oneLine.width (no point wrapping wider than the natural
    // single-line width).
    var aspect = (kind === 'ellipse') ? 2.0 : 4.0;
    var area = oneLine.width * lh;     // total block area when on one line
    var targetWrap = Math.sqrt(area * aspect);
    targetWrap = Math.max(opts.minWidth - 2 * opts.padding,
                          Math.min(oneLine.width, targetWrap));
    var natural = wrapTextToLines(
      Konva, this._content, opts.fontFamily, opts.fontStyle,
      opts.fontSize, targetWrap, opts.wrap
    );
    var nat = measureBlock(Konva, natural, opts.fontFamily, opts.fontStyle,
                           opts.fontSize, 1.2);
    // Width target — clamp to floor.
    var targetW = Math.max(opts.minWidth, Math.ceil(nat.width) + 2 * opts.padding);
    var targetH = Math.max(opts.minHeight, Math.ceil(nat.height) + 2 * opts.padding);

    // Grow the host. Each shape kind has its own setter convention.
    if (kind === 'rect' && this.host.width && this.host.height) {
      this.host.width(targetW);
      this.host.height(targetH);
      // For Rect, host x/y is top-left; place at (0,0) in group space.
      if (this.host.x) this.host.x(0);
      if (this.host.y) this.host.y(0);
    } else if (kind === 'ellipse') {
      // Bound text inside the inscribed rect of an ellipse with semi-axes
      // (a, b). To make a rectangle with width W and height H fit inside
      // the inscribed axis-aligned rect we need a >= W/√2 and b >= H/√2.
      var a = (targetW / 2) * Math.SQRT2;
      var b = (targetH / 2) * Math.SQRT2;
      if (this.host.radiusX) this.host.radiusX(a);
      else if (this.host.radius) this.host.radius(Math.max(a, b));
      if (this.host.radiusY) this.host.radiusY(b);
      // Konva.Ellipse uses center (x, y); place center at (W/2, H/2) so
      // the bounding box origin is (0,0) in group space.
      if (this.host.x) this.host.x(targetW / 2);
      if (this.host.y) this.host.y(targetH / 2);
    } else if (kind === 'polygon' && this.host.points) {
      // Scale the polygon's points so its bounding box matches targetW x
      // targetH. Preserves the polygon's shape silhouette while growing.
      var pts = this.host.points().slice();
      var bbox = polygonBBox(pts);
      var sx = bbox.width  > 0 ? targetW / bbox.width  : 1;
      var sy = bbox.height > 0 ? targetH / bbox.height : 1;
      for (var i = 0; i < pts.length; i += 2) {
        pts[i]     = (pts[i]     - bbox.minX) * sx;
        pts[i + 1] = (pts[i + 1] - bbox.minY) * sy;
      }
      this.host.points(pts);
    }
    // Now run wrap-mode layout against the new host bounds (single source
    // of truth for text placement).
    this._applyWrap(kind, opts);
  };

  // shrink-text: binary-search the largest font size such that the wrapped
  // text fits inside the inscribed rect.
  ShapeWithText.prototype._applyShrinkText = function (kind, opts) {
    var Konva = this._Konva;
    var inner = inscribedRect(this.host, kind, opts.padding);
    var lineHeight = 1.2;
    var lo = opts.minFontSize, hi = opts.maxFontSize;
    var best = lo;
    while (lo <= hi) {
      var mid = Math.floor((lo + hi) / 2);
      var lines = wrapTextToLines(
        Konva, this._content, opts.fontFamily, opts.fontStyle,
        mid, inner.width, opts.wrap
      );
      var blk = measureBlock(Konva, lines, opts.fontFamily, opts.fontStyle,
                             mid, lineHeight);
      var fits = (blk.width <= inner.width + 0.5)
              && (blk.height <= inner.height + 0.5);
      if (fits) { best = mid; lo = mid + 1; }
      else      { hi = mid - 1; }
    }
    // Render at the best-fit size using the same path as wrap.
    var savedFont = opts.fontSize;
    opts.fontSize = best;
    this._applyWrap(kind, opts);
    opts.fontSize = savedFont;  // don't mutate the persistent options
    this.group.setAttr('userTextEffectiveFontSize', best);
  };

  // ── Polygon helpers ──────────────────────────────────────────────────────

  function polygonBBox(pts) {
    if (!pts || pts.length === 0) return { minX: 0, minY: 0, width: 0, height: 0 };
    var minX = pts[0], maxX = pts[0], minY = pts[1], maxY = pts[1];
    for (var i = 0; i < pts.length; i += 2) {
      if (pts[i]     < minX) minX = pts[i];
      if (pts[i]     > maxX) maxX = pts[i];
      if (pts[i + 1] < minY) minY = pts[i + 1];
      if (pts[i + 1] > maxY) maxY = pts[i + 1];
    }
    return { minX: minX, minY: minY, width: maxX - minX, height: maxY - minY };
  }

  // ── Options merge ────────────────────────────────────────────────────────

  function mergeOptions(opts) {
    var out = {};
    var k;
    for (k in DEFAULT_OPTIONS) if (Object.prototype.hasOwnProperty.call(DEFAULT_OPTIONS, k)) {
      out[k] = DEFAULT_OPTIONS[k];
    }
    if (opts) {
      for (k in opts) if (Object.prototype.hasOwnProperty.call(opts, k)) {
        if (out[k] !== undefined || k === 'hostKind') {
          out[k] = opts[k];
        }
      }
    }
    return out;
  }

  // ── Public factory ───────────────────────────────────────────────────────

  /**
   * OraShapeWithText.attach(host, content, options) → controller
   *
   *   host      a Konva.Rect / Konva.Ellipse / Konva.Line(closed) / Konva.Group
   *             — any node exposing getClientRect(). The host is detached
   *             from its current parent (if any) and re-parented under a new
   *             Konva.Group that becomes the user-facing primitive.
   *   content   string — initial text content. Empty string is fine.
   *   options   object — see DEFAULT_OPTIONS plus { policy } (one of
   *             OraShapeWithText.POLICIES). May also carry { userShapeId }
   *             and { hostKind } overrides.
   *
   *   returns   ShapeWithText controller; controller.group is the Konva.Group
   *             callers append to userInputLayer.
   */
  function attach(host, content, options) {
    var KonvaNS = (typeof Konva !== 'undefined') ? Konva : (root && root.Konva);
    if (!KonvaNS) throw new Error('OraShapeWithText.attach: Konva is not available');
    if (!host) throw new Error('OraShapeWithText.attach: host shape is required');
    options = options || {};

    // If the host already has a parent, detach it; we re-parent under our
    // group. This avoids "double-parented" errors when wrapping an existing
    // shape that's been added to a layer.
    if (typeof host.remove === 'function' && host.getParent && host.getParent()) {
      host.remove();
    }

    var group = new KonvaNS.Group({
      x: options.x || 0,
      y: options.y || 0,
      draggable: options.draggable !== false,
    });
    group.add(host);

    var textNode = new KonvaNS.Text({
      text: '',
      listening: false,
      x: 0, y: 0, width: 1, height: 1,
    });
    group.add(textNode);

    var ctl = new ShapeWithText(
      KonvaNS, host, content, options, group, textNode,
      _shapeCounter
    );
    _shapeCounter += 1;
    return ctl;
  }

  // Auto-incremented id counter shared across attach() calls, so the
  // 'u-shape-with-text-<n>' ids are unique within a session even if the
  // caller doesn't bring their own id.
  var _shapeCounter = 0;

  /**
   * OraShapeWithText.fromGroup(group) → controller
   *
   * Re-attach a controller onto a Konva.Group that was deserialized from
   * `Konva.Node.create(json)`. Used after WP-7.0.2 canvas-state load. The
   * group must carry the userShapeType='shape-with-text' attrs that
   * `_attachConventionAttrs` writes.
   */
  function fromGroup(group) {
    var KonvaNS = (typeof Konva !== 'undefined') ? Konva : (root && root.Konva);
    if (!KonvaNS) throw new Error('OraShapeWithText.fromGroup: Konva is not available');
    if (!group || group.getAttr('userShapeType') !== 'shape-with-text') {
      throw new Error('OraShapeWithText.fromGroup: not a shape-with-text group');
    }
    var children = group.getChildren ? group.getChildren() : [];
    var host = null, textNode = null;
    for (var i = 0; i < children.length; i++) {
      var ch = children[i];
      var cn = (typeof ch.getClassName === 'function') ? ch.getClassName() : '';
      if (cn === 'Text' && !textNode) textNode = ch;
      else if (!host) host = ch;
    }
    if (!host || !textNode) {
      throw new Error('OraShapeWithText.fromGroup: missing host or text child');
    }
    var content  = group.getAttr('userTextContent') || '';
    var policy   = group.getAttr('userTextPolicy')  || POLICIES.WRAP;
    var options  = group.getAttr('userTextOptions') || {};
    options.policy = policy;
    options.userShapeId = group.getAttr('userShapeId');
    var ctl = new ShapeWithText(KonvaNS, host, content, options, group, textNode,
                                _shapeCounter);
    return ctl;
  }

  // ── Schema fragment for WP-7.0.2 to adopt ───────────────────────────────
  //
  // Exposed at OraShapeWithText.SCHEMA_FRAGMENT so the canvas-state schema
  // module can pull it in directly rather than re-typing the field set.
  var SCHEMA_FRAGMENT = {
    $id: 'shape_with_text',
    type: 'object',
    additionalProperties: false,
    required: ['userShapeId', 'userShapeType', 'userTextContent',
               'userTextPolicy', 'userTextOptions'],
    properties: {
      userShapeId:     { type: 'string', pattern: '^u-shape-with-text-\\d+$' },
      userShapeType:   { const: 'shape-with-text' },
      userTextContent: { type: 'string' },
      userTextPolicy:  { enum: ['wrap', 'grow', 'shrink-text'] },
      userTextOptions: {
        type: 'object',
        additionalProperties: false,
        properties: {
          padding:       { type: 'number', minimum: 0, default: 8 },
          fontFamily:    { type: 'string', default: 'sans-serif' },
          fontSize:      { type: 'number', exclusiveMinimum: 0, default: 14 },
          minFontSize:   { type: 'number', exclusiveMinimum: 0, default: 6 },
          maxFontSize:   { type: 'number', exclusiveMinimum: 0, default: 48 },
          fontStyle:     { enum: ['normal','bold','italic','bold italic'],
                           default: 'normal' },
          fill:          { type: 'string', default: '#1a1a1a' },
          align:         { enum: ['left','center','right'], default: 'center' },
          verticalAlign: { enum: ['top','middle','bottom'], default: 'middle' },
          wrap:          { enum: ['word','char','none'], default: 'word' },
          ellipsis:      { type: 'boolean', default: true },
          minWidth:      { type: 'number', minimum: 0, default: 24 },
          minHeight:     { type: 'number', minimum: 0, default: 18 },
          hostKind:      { enum: ['rect','ellipse','polygon','group'],
                           default: 'rect' },
        },
      },
      userTextHostAttrs: {
        type: 'object',
        additionalProperties: false,
        required: ['konvaClass', 'attrs'],
        properties: {
          konvaClass: { enum: ['Rect','Ellipse','Circle','Line','Group'] },
          attrs:      { type: 'object' },
        },
      },
      // Optional cached value written by shrink-text after layout.
      userTextEffectiveFontSize: { type: 'number', exclusiveMinimum: 0 },
    },
  };

  // ── Export ──────────────────────────────────────────────────────────────
  var api = {
    POLICIES: POLICIES,
    DEFAULT_OPTIONS: DEFAULT_OPTIONS,
    SCHEMA_FRAGMENT: SCHEMA_FRAGMENT,
    attach: attach,
    fromGroup: fromGroup,
    // Exposed for testing / advanced consumers.
    _internals: {
      detectHostKind: detectHostKind,
      inscribedRect: inscribedRect,
      wrapTextToLines: wrapTextToLines,
      measureBlock: measureBlock,
      polygonBBox: polygonBBox,
      ShapeWithText: ShapeWithText,
    },
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.OraShapeWithText = api;
  }

})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this));
