/**
 * ora-visual-compiler / artifact-adversarial.js
 *
 * WP-2.5 — Artifact-level adversarial review (client-side, post-render).
 *
 * Runs after a renderer produces SVG but before the caller installs it into
 * the DOM. Complements the server-side spec-level review in
 * ``orchestrator/visual_adversarial.py``: that module inspects the ENVELOPE
 * (Tufte T-rules, LLM-prior inversions). THIS module inspects the RENDERED
 * SVG — catching layout failures Python cannot predict.
 *
 * Three checks (per Protocol §8.5 — "never render a degraded visual because
 * a slot was allocated"):
 *
 *   1. Overlap detection — bounding-box intersection between every pair of
 *      semantic elements (nodes, cells, items, labels). Overlap above 5% of
 *      the smaller element's area → E_ARTIFACT_OVERLAP (Critical; forces
 *      fallback). Overlap ≤ 5% → W_ARTIFACT_OVERLAP_MINOR (render anyway).
 *      Parent/child pairs are skipped (a <text> inside a <g class="node"> is
 *      not an overlap).
 *
 *   2. Text truncation — estimated text width (chars × 6.5 px/char at our
 *      default theme font size 13 px) compared to the containing semantic
 *      group's bbox width. Above 1.10× → W_ARTIFACT_TEXT_TRUNCATED. When the
 *      text is a semantic primary label (ora-visual__node-label,
 *      ora-visual__concept-label, etc.) and truncated beyond 1.5× the
 *      container → Critical (loses the node's meaning if truncated).
 *
 *   3. WCAG 2.1 contrast — samples the root SVG's background (resolved from
 *      the --ora-vis-surface custom property when getComputedStyle is
 *      available, else the light-mode default #fdfbf7). For every <text>
 *      element, compute text-fg vs background contrast ratio using the
 *      WCAG 2.1 relative-luminance formula. Text below 4.5:1 →
 *      E_ARTIFACT_CONTRAST (blocks). For graphical data-encoding elements
 *      (edges, node fills), below 3:1 → W_ARTIFACT_CONTRAST_GRAPHICAL.
 *
 * jsdom note: getBBox() on the jsdom polyfill returns (0, 0, textlen*6, 14)
 * and does NOT reflect the renderer's actual layout (transforms, node
 * positions). We therefore compute bboxes by parsing SVG geometry attributes
 * directly (x, y, cx, cy, width, height, transform translate, path d "M x,y"
 * first moveto). This is renderer-agnostic and works both in jsdom and in a
 * real browser. When `element.getBBox()` is available AND returns a non-
 * degenerate bbox (width > 0 AND either x != 0 OR y != 0), we prefer it;
 * otherwise we fall back to attribute parsing.
 *
 * Public API:
 *
 *   OraVisualCompiler.artifactAdversarial.review(svg, envelope)
 *     → { findings: [{ code, severity, message, path?, element_id? }], blocks: bool }
 *
 *   findings: flat list built via errors.make().
 *   blocks:   true iff any finding has severity === 'error'.
 *
 * Integration: see index.js compile() — when the module is loaded, findings
 * from a Critical run replace result.svg with '' and append to result.errors;
 * non-Critical findings attach to result.warnings. Backward compatible —
 * when artifactAdversarial is absent, compile() behaves as before.
 *
 * Load order: after the accessibility modules (alt-text-generator,
 * aria-annotator, keyboard-nav). This module reads SVG output; it does not
 * modify the SVG.
 *
 * Depends on: errors.js (for errors.make), palettes.js (optional; for light/
 * dark surface constants). No vendor dependencies.
 */

(function (global) {
  var ns = global.OraVisualCompiler = global.OraVisualCompiler || {};

  // Prefer the errors module if loaded. When the harness loads this module
  // standalone for a unit test, fall back to a compatible make() shim.
  function _make(code, message, path, elementId) {
    var factory = ns.errors && typeof ns.errors.make === 'function'
      ? ns.errors.make : null;
    var f;
    if (factory) {
      f = factory(code, message, path);
    } else {
      f = {
        code: code,
        message: message,
        severity: (code.charAt(0) === 'W') ? 'warning' : 'error',
      };
      if (path !== undefined) f.path = path;
    }
    if (elementId !== undefined && elementId !== null) f.element_id = elementId;
    return f;
  }

  // ── SVG parsing primitives ─────────────────────────────────────────────

  // DOMParser is standard in the browser and in jsdom (since jsdom 15).
  function _parse(svg) {
    if (typeof svg !== 'string' || svg.length === 0) return null;
    var Parser = global.DOMParser;
    if (!Parser) return null;
    try {
      var doc = new Parser().parseFromString(svg, 'image/svg+xml');
      if (!doc || !doc.documentElement) return null;
      // Parsing errors surface as <parsererror> in many DOM implementations.
      if (doc.getElementsByTagName && doc.getElementsByTagName('parsererror').length > 0) {
        return null;
      }
      return doc;
    } catch (e) {
      return null;
    }
  }

  // Translate/scale extracted from a `transform` attribute. We support
  // translate(tx, ty), translate(tx ty), and chained transforms (we sum
  // translates only; scales are captured as a single uniform factor).
  function _parseTransform(str) {
    if (!str) return { tx: 0, ty: 0, scale: 1 };
    var tx = 0, ty = 0, scale = 1;
    var re = /(translate|scale|matrix)\s*\(([^)]+)\)/gi;
    var m;
    while ((m = re.exec(str)) !== null) {
      var op = m[1].toLowerCase();
      var parts = m[2].split(/[\s,]+/).map(parseFloat);
      if (op === 'translate') {
        tx += (parts[0] || 0);
        ty += (parts.length > 1 ? parts[1] : 0) || 0;
      } else if (op === 'scale') {
        var sx = parts[0] || 1;
        var sy = parts.length > 1 ? parts[1] : sx;
        scale *= (Math.abs(sx) + Math.abs(sy)) / 2;
      } else if (op === 'matrix') {
        // matrix(a b c d e f) — translate = (e, f), scale ≈ |det|^(1/2).
        var a = parts[0] || 1, b = parts[1] || 0, c = parts[2] || 0,
            d = parts[3] || 1, e = parts[4] || 0, f = parts[5] || 0;
        tx += e; ty += f;
        var det = Math.abs(a * d - b * c);
        scale *= Math.sqrt(det > 0 ? det : 1);
      }
    }
    return { tx: tx, ty: ty, scale: scale };
  }

  // Compute the cumulative translate/scale for `el` by walking up to the
  // root <svg>, summing translates. Returns { tx, ty, scale }.
  function _cumulativeTransform(el) {
    var tx = 0, ty = 0, scale = 1;
    var cur = el;
    while (cur && cur.nodeType === 1 && cur.tagName && cur.tagName.toLowerCase() !== 'svg') {
      var t = _parseTransform(cur.getAttribute && cur.getAttribute('transform'));
      // translate is applied AFTER ancestor translate in SVG semantics: the
      // screen position of an element is ancestor.tx + this.tx * ancestor.scale.
      tx += t.tx * scale;
      ty += t.ty * scale;
      scale *= t.scale;
      cur = cur.parentNode;
    }
    return { tx: tx, ty: ty, scale: scale };
  }

  // Extract a path's approximate bounding box from its `d` attribute. We
  // only consider moveto/lineto/curveto targets as min/max candidates. Good
  // enough for overlap heuristics; not exact.
  function _pathBBox(d) {
    if (!d) return null;
    var minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    // Match a command letter followed by numeric args, or a bare coordinate pair.
    var re = /([MLCQTSAZHVmlcqtsazhv])|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;
    var m, lastCmd = 'M', pending = [];
    var currentX = 0, currentY = 0;
    function consume() {
      if (!pending.length) return;
      var cmd = lastCmd;
      var isRel = cmd === cmd.toLowerCase() && cmd !== 'z' && cmd !== 'Z';
      var norm = cmd.toUpperCase();
      if (norm === 'H') {
        // horizontal: one coord = x
        var x = pending.shift(); if (isRel) x += currentX;
        currentX = x;
        minX = Math.min(minX, x); maxX = Math.max(maxX, x);
        minY = Math.min(minY, currentY); maxY = Math.max(maxY, currentY);
      } else if (norm === 'V') {
        var y = pending.shift(); if (isRel) y += currentY;
        currentY = y;
        minY = Math.min(minY, y); maxY = Math.max(maxY, y);
        minX = Math.min(minX, currentX); maxX = Math.max(maxX, currentX);
      } else if (norm === 'A') {
        // arc: rx ry x-axis rot large-arc sweep x y — only x,y matter
        if (pending.length >= 7) {
          pending.shift(); pending.shift(); pending.shift();
          pending.shift(); pending.shift();
          var ax = pending.shift(); var ay = pending.shift();
          if (isRel) { ax += currentX; ay += currentY; }
          currentX = ax; currentY = ay;
          minX = Math.min(minX, ax); maxX = Math.max(maxX, ax);
          minY = Math.min(minY, ay); maxY = Math.max(maxY, ay);
        } else { pending.length = 0; }
      } else {
        // M/L/C/Q/S/T: consume pairs and track the last pair as the new "current".
        while (pending.length >= 2) {
          var px = pending.shift();
          var py = pending.shift();
          if (isRel) { px += currentX; py += currentY; }
          currentX = px; currentY = py;
          minX = Math.min(minX, px); maxX = Math.max(maxX, px);
          minY = Math.min(minY, py); maxY = Math.max(maxY, py);
        }
      }
    }
    while ((m = re.exec(d)) !== null) {
      if (m[1]) {
        consume();
        lastCmd = m[1];
        if (lastCmd === 'z' || lastCmd === 'Z') continue;
      } else if (m[2]) {
        pending.push(parseFloat(m[2]));
      }
    }
    consume();
    if (!isFinite(minX) || !isFinite(minY)) return null;
    return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
  }

  // Compute the SCREEN-space bounding box for an SVG element by combining
  // its intrinsic geometry (attributes) with the cumulative transform of
  // itself and all ancestors.
  function _bboxFromAttrs(el) {
    if (!el || el.nodeType !== 1) return null;
    var tag = (el.tagName || '').toLowerCase();
    var selfT = _parseTransform(el.getAttribute && el.getAttribute('transform'));
    var outer = _cumulativeTransform(el.parentNode);
    var tx = outer.tx + selfT.tx * outer.scale;
    var ty = outer.ty + selfT.ty * outer.scale;
    var scale = outer.scale * selfT.scale;

    var x = 0, y = 0, w = 0, h = 0;

    function num(attr, fallback) {
      var v = el.getAttribute && el.getAttribute(attr);
      var n = parseFloat(v);
      return isFinite(n) ? n : (fallback == null ? 0 : fallback);
    }

    if (tag === 'rect') {
      x = num('x'); y = num('y');
      w = num('width'); h = num('height');
    } else if (tag === 'circle') {
      var cx = num('cx'); var cy = num('cy'); var r = num('r');
      x = cx - r; y = cy - r; w = r * 2; h = r * 2;
    } else if (tag === 'ellipse') {
      var ecx = num('cx'); var ecy = num('cy');
      var rx = num('rx'); var ry = num('ry');
      x = ecx - rx; y = ecy - ry; w = rx * 2; h = ry * 2;
    } else if (tag === 'line') {
      var x1 = num('x1'); var y1 = num('y1');
      var x2 = num('x2'); var y2 = num('y2');
      x = Math.min(x1, x2); y = Math.min(y1, y2);
      w = Math.abs(x2 - x1); h = Math.abs(y2 - y1);
    } else if (tag === 'path') {
      var pb = _pathBBox(el.getAttribute && el.getAttribute('d'));
      if (pb) { x = pb.x; y = pb.y; w = pb.width; h = pb.height; }
    } else if (tag === 'text') {
      x = num('x'); y = num('y');
      // height ≈ font-size; we use a conservative 14 when unspecified.
      var fs = parseFloat(el.getAttribute && el.getAttribute('font-size')) || 14;
      h = fs;
      // width ≈ content length × char-width (approximation; text-truncation
      // section below refines this against the containing element).
      var content = (el.textContent || '').trim();
      w = content.length * 6.5;
      // Rough adjustment for text-anchor (middle/end move the anchor point).
      var anchor = el.getAttribute && el.getAttribute('text-anchor');
      if (anchor === 'middle') { x -= w / 2; }
      else if (anchor === 'end') { x -= w; }
      // Rough baseline adjustment (text y is the baseline; ascend ~ 0.8 h).
      y -= fs * 0.8;
    } else if (tag === 'g') {
      // For groups, bbox = union of children bboxes (in parent coords) plus
      // this group's own translate (already in selfT).
      var cs = el.childNodes || [];
      var any = false;
      var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (var i = 0; i < cs.length; i++) {
        var kid = cs[i];
        if (kid.nodeType !== 1) continue;
        var kb = _bboxFromAttrs(kid);
        if (!kb || !isFinite(kb.width) || !isFinite(kb.height)) continue;
        if (kb.width === 0 && kb.height === 0) continue;
        any = true;
        minX = Math.min(minX, kb.x);
        minY = Math.min(minY, kb.y);
        maxX = Math.max(maxX, kb.x + kb.width);
        maxY = Math.max(maxY, kb.y + kb.height);
      }
      if (any) return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
      return null;
    } else {
      return null;
    }

    return {
      x: tx + x * scale,
      y: ty + y * scale,
      width:  w * scale,
      height: h * scale,
    };
  }

  // Try getBBox() first if it returns a non-degenerate layout (real browser).
  // If unavailable or jsdom-degenerate (x=0, y=0, height=14), use attribute math.
  function _bbox(el) {
    if (el && typeof el.getBBox === 'function') {
      try {
        var b = el.getBBox();
        if (b && typeof b.width === 'number' &&
            (b.x !== 0 || b.y !== 0 || b.width > 30)) {
          // jsdom returns x=0,y=0,h=14 with width = textContent.length * 6.
          // Real browsers return real screen-space layout. Real returns are
          // trusted; jsdom stubs fall through.
          // Heuristic: jsdom returns width = content.length * 6, height = 14.
          var content = (el.textContent || '').length;
          var looksLikeStub = b.x === 0 && b.y === 0 && b.height === 14 &&
                              Math.abs(b.width - content * 6) < 1;
          if (!looksLikeStub) {
            // Combine with ancestor transforms so we're in screen space
            // relative to root. Browsers' getBBox is local; we want screen.
            var anc = _cumulativeTransform(el.parentNode);
            var selfT = _parseTransform(el.getAttribute && el.getAttribute('transform'));
            return {
              x: anc.tx + (b.x + selfT.tx) * anc.scale * selfT.scale,
              y: anc.ty + (b.y + selfT.ty) * anc.scale * selfT.scale,
              width:  b.width  * anc.scale * selfT.scale,
              height: b.height * anc.scale * selfT.scale,
            };
          }
        }
      } catch (e) { /* fall through to attribute math */ }
    }
    return _bboxFromAttrs(el);
  }

  // Rectangle intersection area (clamped to non-negative).
  function _intersectArea(a, b) {
    if (!a || !b) return 0;
    var w = Math.min(a.x + a.width,  b.x + b.width)  - Math.max(a.x, b.x);
    var h = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
    if (w <= 0 || h <= 0) return 0;
    return w * h;
  }

  function _area(b) { return b ? Math.max(0, b.width) * Math.max(0, b.height) : 0; }

  // Are `a` and `b` in the same parent/child subtree? Skip such pairs.
  function _isAncestor(a, b) {
    var cur = b.parentNode;
    while (cur) { if (cur === a) return true; cur = cur.parentNode; }
    return false;
  }

  // ── Semantic element collection ─────────────────────────────────────────

  // Collect every element that carries a semantic class we care about
  // (ora-visual__*). We exclude marker/decoration/axis presentation layers,
  // plus any label/text sub-classes (e.g. ora-visual__fb-category-label is
  // a text wrapper, not a semantic node). Use negative lookahead `(?!-)` to
  // reject tokens that continue with another segment (-label, -text, -box,
  // -line, -wrap, -group).
  var SEMANTIC_CLASS_RE =
    /\bora-visual__(?:node|cell|ach-cell|bar|point|datapoint|item|quadrant-item|loop|stock|flow|auxiliary|cloud|concept|proposition|linking-phrase|hypothesis|evidence|quadrant|threat|consequence|control|preventive|mitigative|hazard|escalation|effect|cause|sub-bone|branch|leaf|argument|idea|question|pro|con|pathway|actor|message|state|person|software-system|decision|chance|terminal|fb-effect|fb-category|fb-cause)(?![-_a-z0-9])/i;

  // Labels that lose meaning if truncated (primary labels).
  var PRIMARY_LABEL_CLASS_RE =
    /\bora-visual__(?:node-label|concept-label|stock-label|category-label|effect-label|cause-label|item-label|evidence-label|hypothesis-label|axis-label|pro-label|con-label)\b/;

  function _semanticClassOf(el) {
    var cls = (el.getAttribute && el.getAttribute('class')) || '';
    var m = SEMANTIC_CLASS_RE.exec(cls);
    return m ? m[0] : null;
  }

  function _isPrimaryLabel(el) {
    var cls = (el.getAttribute && el.getAttribute('class')) || '';
    return PRIMARY_LABEL_CLASS_RE.test(cls);
  }

  // ── WCAG 2.1 contrast ─────────────────────────────────────────────────

  function _parseHex(hex) {
    if (!hex) return null;
    hex = String(hex).trim();
    if (hex.indexOf('#') === 0) hex = hex.slice(1);
    if (hex.length === 3) {
      hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
    }
    if (hex.length !== 6) return null;
    var r = parseInt(hex.slice(0, 2), 16);
    var g = parseInt(hex.slice(2, 4), 16);
    var b = parseInt(hex.slice(4, 6), 16);
    if (!isFinite(r) || !isFinite(g) || !isFinite(b)) return null;
    return { r: r, g: g, b: b };
  }

  function _parseRgb(s) {
    if (!s) return null;
    s = String(s).trim();
    // rgba(r,g,b,a) — a==0 means fully transparent → treat as "not set".
    var rgba = /^rgba\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)/.exec(s);
    if (rgba) {
      var aa = parseFloat(rgba[4]);
      if (isFinite(aa) && aa <= 0) return null;
      return {
        r: Math.round(parseFloat(rgba[1])),
        g: Math.round(parseFloat(rgba[2])),
        b: Math.round(parseFloat(rgba[3])),
      };
    }
    var m = /^rgba?\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)/.exec(s);
    if (!m) return null;
    return {
      r: Math.round(parseFloat(m[1])),
      g: Math.round(parseFloat(m[2])),
      b: Math.round(parseFloat(m[3])),
    };
  }

  function _parseColor(val) {
    if (!val) return null;
    val = String(val).trim().toLowerCase();
    if (!val || val === 'none' || val === 'transparent' || val === 'currentcolor') return null;
    if (val.charAt(0) === '#') return _parseHex(val);
    if (val.indexOf('rgb') === 0) return _parseRgb(val);
    // Named color fallback — cover the handful we actually emit.
    var NAMED = {
      black:  { r: 0,   g: 0,   b: 0 },
      white:  { r: 255, g: 255, b: 255 },
      red:    { r: 255, g: 0,   b: 0 },
      blue:   { r: 0,   g: 0,   b: 255 },
      green:  { r: 0,   g: 128, b: 0 },
      gray:   { r: 128, g: 128, b: 128 },
      grey:   { r: 128, g: 128, b: 128 },
      silver: { r: 192, g: 192, b: 192 },
    };
    return NAMED[val] || null;
  }

  // WCAG 2.1 relative luminance.
  function _luminance(rgb) {
    function lin(c) {
      var cs = c / 255;
      return cs <= 0.03928 ? cs / 12.92 : Math.pow((cs + 0.055) / 1.055, 2.4);
    }
    return 0.2126 * lin(rgb.r) + 0.7152 * lin(rgb.g) + 0.0722 * lin(rgb.b);
  }

  // WCAG 2.1 SC 1.4.3 / 1.4.11 contrast ratio.
  function _contrast(fg, bg) {
    if (!fg || !bg) return null;
    var l1 = _luminance(fg);
    var l2 = _luminance(bg);
    var hi = Math.max(l1, l2);
    var lo = Math.min(l1, l2);
    return (hi + 0.05) / (lo + 0.05);
  }

  // Resolve the effective fill for a <text> element. Check inline fill,
  // style="fill: …", computed style, then fall back to theme default (#222).
  function _textFill(el) {
    var fill = el.getAttribute && el.getAttribute('fill');
    var col = _parseColor(fill);
    if (col) return col;
    var style = el.getAttribute && el.getAttribute('style');
    if (style) {
      var m = /fill\s*:\s*([^;]+)/i.exec(style);
      if (m) {
        col = _parseColor(m[1].trim());
        if (col) return col;
      }
    }
    // Computed style (real browser). jsdom returns an empty
    // CSSStyleDeclaration; parseColor handles that gracefully.
    try {
      var win = (el.ownerDocument && el.ownerDocument.defaultView) || global;
      if (win && typeof win.getComputedStyle === 'function') {
        var cs = win.getComputedStyle(el);
        var f = cs && (cs.fill || (cs.getPropertyValue && cs.getPropertyValue('fill')));
        col = _parseColor(f);
        if (col) return col;
      }
    } catch (e) { /* swallow */ }
    // Theme fallback: --ora-vis-text is #111111 in the light palette.
    return { r: 17, g: 17, b: 17 };
  }

  function _strokeFill(el) {
    var stroke = el.getAttribute && el.getAttribute('stroke');
    var col = _parseColor(stroke);
    if (col) return col;
    var style = el.getAttribute && el.getAttribute('style');
    if (style) {
      var m = /stroke\s*:\s*([^;]+)/i.exec(style);
      if (m) {
        col = _parseColor(m[1].trim());
        if (col) return col;
      }
    }
    // Fill-as-visual-color (shapes without stroke).
    var fill = el.getAttribute && el.getAttribute('fill');
    col = _parseColor(fill);
    if (col) return col;
    return null;
  }

  // Background resolution. Prefers the --ora-vis-surface custom property
  // via getComputedStyle; falls back to the light-mode theme default.
  //
  // We deliberately do NOT use the generic `background-color` CSS property
  // here: jsdom (and some browsers, for inline SVG) return 'rgb(0, 0, 0)'
  // or 'rgba(0, 0, 0, 0)' as the SVG root's background regardless of theme,
  // which would make every text contrast fail at 1.00:1 against black. The
  // theme CSS keeps the true surface in --ora-vis-surface; if that custom
  // property resolves we use it; otherwise we use the light palette default.
  function _resolveBackground(svgRoot) {
    var light = { r: 253, g: 251, b: 247 };  // #fdfbf7
    try {
      var win = (svgRoot && svgRoot.ownerDocument && svgRoot.ownerDocument.defaultView) || global;
      if (win && typeof win.getComputedStyle === 'function') {
        var cs = win.getComputedStyle(svgRoot);
        if (cs && cs.getPropertyValue) {
          var surf = cs.getPropertyValue('--ora-vis-surface');
          var col = _parseColor(surf && String(surf).trim());
          if (col) return col;
        }
      }
    } catch (e) { /* fall through to default */ }
    return light;
  }

  // ── Main review ───────────────────────────────────────────────────────

  var OVERLAP_CRITICAL_THRESHOLD = 0.05;   // > 5% of smaller area → Critical
  var TEXT_TRUNC_WARN_THRESHOLD  = 1.10;   // > 110% of container width
  var TEXT_TRUNC_CRIT_THRESHOLD  = 1.50;   // > 150% of container when primary label
  var WCAG_TEXT_MIN              = 4.5;    // SC 1.4.3 body text / normal size
  var WCAG_GRAPHICAL_MIN         = 3.0;    // SC 1.4.11 graphical objects

  function review(svg, envelope) {
    var findings = [];

    // Unparseable input → no review (don't block on our own failure).
    if (typeof svg !== 'string' || svg.length === 0) {
      return { findings: findings, blocks: false };
    }
    var doc = _parse(svg);
    if (!doc || !doc.documentElement) {
      return { findings: findings, blocks: false };
    }
    var root = doc.documentElement;

    // ── 1. Overlap detection ────────────────────────────────────────────
    var semElems = [];
    var all = root.getElementsByTagName ? root.getElementsByTagName('*') : [];
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      if (!el || !el.getAttribute) continue;
      // Skip hidden / decorative.
      if (el.getAttribute('aria-hidden') === 'true') continue;
      var cls = el.getAttribute('class') || '';
      if (/\b(?:ora-visual__decoration|ora-visual__background|ora-visual__frame|ora-visual__gridline|ora-visual__axis(?:-tick|-line|-arrow)?)\b/.test(cls)) continue;
      var semCls = _semanticClassOf(el);
      if (!semCls) continue;
      var bbox = _bbox(el);
      if (!bbox || bbox.width <= 0 || bbox.height <= 0) continue;
      semElems.push({
        el: el,
        id: el.getAttribute('id') || null,
        cls: semCls,
        bbox: bbox,
      });
    }

    // Semantic-class pairs that legitimately tile (share an edge by design)
    // or nest (item in quadrant; cause on a category bone). Those are not
    // overlaps in the adversarial sense — they are the intended layout.
    // The render-as-fallback branch is for TRUE layout bugs (two
    // independent nodes colliding) not for design nesting / tiling.
    function _isNestingPair(clsA, clsB) {
      // Quadrant/item nesting.
      if ((clsA === 'ora-visual__quadrant' && clsB === 'ora-visual__quadrant-item') ||
          (clsB === 'ora-visual__quadrant' && clsA === 'ora-visual__quadrant-item')) return true;
      if ((clsA === 'ora-visual__quadrant' && clsB === 'ora-visual__item') ||
          (clsB === 'ora-visual__quadrant' && clsA === 'ora-visual__item')) return true;
      // Loops enclose their member nodes (CLD).
      if ((clsA === 'ora-visual__loop' && clsB === 'ora-visual__node') ||
          (clsB === 'ora-visual__loop' && clsA === 'ora-visual__node')) return true;
      // Fishbone cause lives on a category bone.
      if ((clsA === 'ora-visual__fb-category' && clsB === 'ora-visual__fb-cause') ||
          (clsB === 'ora-visual__fb-category' && clsA === 'ora-visual__fb-cause')) return true;
      if ((clsA === 'ora-visual__fb-effect' && clsB === 'ora-visual__fb-cause') ||
          (clsB === 'ora-visual__fb-effect' && clsA === 'ora-visual__fb-cause')) return true;
      if (clsA === 'ora-visual__fb-cause' && clsB === 'ora-visual__fb-cause') return true;
      // Quadrant pairs tile the plane — sharing exactly one dividing axis
      // yields ≤ 5% overlap due to stroke-width; flagging is noise.
      if (clsA === 'ora-visual__quadrant' && clsB === 'ora-visual__quadrant') return true;
      // Bow-tie control chains: preventive/mitigative controls stack near
      // the hazard; overlap here is by design (see bow-tie renderer).
      if ((clsA === 'ora-visual__control' && clsB === 'ora-visual__control') ||
          (clsA === 'ora-visual__preventive' && clsB === 'ora-visual__preventive') ||
          (clsA === 'ora-visual__mitigative' && clsB === 'ora-visual__mitigative')) return true;
      if ((clsA === 'ora-visual__control' && clsB === 'ora-visual__escalation') ||
          (clsB === 'ora-visual__control' && clsA === 'ora-visual__escalation')) return true;
      // IBIS position/argument stacks, decision-tree branches.
      if ((clsA === 'ora-visual__branch' && clsB === 'ora-visual__branch')) return true;
      return false;
    }

    // A "contained" small element whose bbox fits inside the larger by ≥90%
    // is nesting, not overlap. This catches item-in-region layouts.
    function _isContainedIn(small, big) {
      var interC = _intersectArea(small.bbox, big.bbox);
      if (interC <= 0) return false;
      var sa = _area(small.bbox);
      return sa > 0 && (interC / sa) >= 0.90;
    }

    for (var a = 0; a < semElems.length; a++) {
      for (var b = a + 1; b < semElems.length; b++) {
        var A = semElems[a], B = semElems[b];
        if (_isAncestor(A.el, B.el) || _isAncestor(B.el, A.el)) continue;
        if (_isNestingPair(A.cls, B.cls)) continue;
        var inter = _intersectArea(A.bbox, B.bbox);
        if (inter <= 0) continue;
        var areaA = _area(A.bbox);
        var areaB = _area(B.bbox);
        var smaller = Math.min(areaA, areaB);
        if (smaller <= 0) continue;
        // Containment (one fully inside the other) is nesting, not overlap.
        var smallerEl = (areaA <= areaB) ? A : B;
        var largerEl  = (areaA <= areaB) ? B : A;
        if (_isContainedIn(smallerEl, largerEl)) continue;
        var ratio = inter / smaller;
        var ids = (A.id || '?') + ' / ' + (B.id || '?');
        if (ratio > OVERLAP_CRITICAL_THRESHOLD) {
          findings.push(_make(
            'E_ARTIFACT_OVERLAP',
            'Semantic elements overlap by ' + (ratio * 100).toFixed(1) +
            '% of the smaller area (' + ids + '). Rendering suppressed; see Protocol §8.5.',
            null,
            A.id || B.id
          ));
        } else {
          findings.push(_make(
            'W_ARTIFACT_OVERLAP_MINOR',
            'Semantic elements touch (' + (ratio * 100).toFixed(1) +
            '% overlap of smaller area; ' + ids + '). Render proceeds.',
            null,
            A.id || B.id
          ));
        }
      }
    }

    // ── 2. Text truncation ─────────────────────────────────────────────
    // Container width for a label = the widest NON-text drawable sibling
    // (rect, circle, ellipse, path) inside the containing semantic group.
    // This matches the designer's intent: text must fit inside the "chrome"
    // the group draws around it — not the text's own overspill, which
    // would make the bbox self-referentially satisfy any check.
    function _containerSlotWidth(group) {
      var maxW = 0;
      var kids = group.getElementsByTagName ? group.getElementsByTagName('*') : [];
      for (var i = 0; i < kids.length; i++) {
        var k = kids[i];
        var tag = (k.tagName || '').toLowerCase();
        if (tag === 'text') continue;
        // Only consider direct visual chrome; skip groups' own nested groups
        // (their width would recurse). The immediate parent group's own
        // rect/circle/ellipse/line/path is the slot.
        if (tag !== 'rect' && tag !== 'circle' && tag !== 'ellipse' &&
            tag !== 'line' && tag !== 'path') continue;
        var kb = _bbox(k);
        if (!kb) continue;
        if (kb.width > maxW) maxW = kb.width;
      }
      return maxW;
    }

    var texts = root.getElementsByTagName ? root.getElementsByTagName('text') : [];
    for (var t = 0; t < texts.length; t++) {
      var tex = texts[t];
      if (!tex || !tex.getAttribute) continue;
      if (tex.getAttribute('aria-hidden') === 'true') continue;
      var txt = (tex.textContent || '').trim();
      if (!txt) continue;

      var estWidth = txt.length * 6.5;

      // Find containing semantic group (nearest ancestor <g> with a
      // semantic class). If none, skip — unwrapped text has no container.
      var container = null;
      var cur = tex.parentNode;
      while (cur && cur.nodeType === 1 && cur.tagName && cur.tagName.toLowerCase() !== 'svg') {
        if (_semanticClassOf(cur)) { container = cur; break; }
        cur = cur.parentNode;
      }
      if (!container) continue;

      // Slot-width heuristic applies only when the text MUST fit inside
      // the group's chrome (node/cell/box-like). For marker+label types
      // (item, quadrant-item, loop, hypothesis, concept dot with floating
      // label), the label anchors outside the marker, so we use the full
      // group bbox. This matches designer intent and avoids false
      // positives on scatter-like layouts where the item IS a tiny glyph.
      var containerCls = _semanticClassOf(container) || '';
      var isBoxLike = /\bora-visual__(?:node|cell|ach-cell|bar|quadrant(?![-_])|stock|flow|threat|consequence|control|preventive|mitigative|hazard|escalation|effect|cause|fb-effect|fb-category|fb-cause|branch|leaf|argument|idea|question|pro|con|decision|chance|terminal|person|software-system|actor|message|state)(?![-_a-z0-9])/i
        .test(containerCls);
      var cbox;
      if (isBoxLike) {
        var slotWidth = _containerSlotWidth(container);
        cbox = slotWidth > 0 ? { width: slotWidth } : _bbox(container);
      } else {
        cbox = _bbox(container);
      }
      if (!cbox || cbox.width <= 0) continue;

      var over = estWidth / cbox.width;
      if (over > TEXT_TRUNC_WARN_THRESHOLD) {
        var primary = _isPrimaryLabel(tex);
        var crit = primary && over > TEXT_TRUNC_CRIT_THRESHOLD;
        var tid = tex.getAttribute('id') || container.getAttribute('id') || null;
        var finding = _make(
          'W_ARTIFACT_TEXT_TRUNCATED',
          (crit ? 'Primary label truncated: ' : 'Text likely truncated: ') +
          '"' + txt.slice(0, 48) + (txt.length > 48 ? '…' : '') + '" ' +
          '(~' + estWidth.toFixed(0) + 'px in ~' + cbox.width.toFixed(0) + 'px container; ' +
          (over * 100).toFixed(0) + '% of container width).',
          null,
          tid
        );
        // Primary-label truncation beyond 1.5× loses node meaning — upgrade
        // severity to error (Protocol §8.5). Per the WP-2.5 spec, we still
        // use the canonical W_ARTIFACT_TEXT_TRUNCATED code but flag severity
        // as error so it blocks the render.
        if (crit) finding.severity = 'error';
        findings.push(finding);
      }
    }

    // ── 3. WCAG contrast ───────────────────────────────────────────────
    var bg = _resolveBackground(root);
    for (var ti = 0; ti < texts.length; ti++) {
      var tx = texts[ti];
      if (!tx || !tx.getAttribute) continue;
      if (tx.getAttribute('aria-hidden') === 'true') continue;
      if (!(tx.textContent || '').trim()) continue;
      var fg = _textFill(tx);
      var ratio2 = _contrast(fg, bg);
      if (ratio2 != null && ratio2 < WCAG_TEXT_MIN) {
        findings.push(_make(
          'E_ARTIFACT_CONTRAST',
          'Text contrast ' + ratio2.toFixed(2) + ':1 is below WCAG 2.1 SC 1.4.3 ' +
          'minimum ' + WCAG_TEXT_MIN + ':1 for "' +
          (tx.textContent || '').trim().slice(0, 48) + '".',
          null,
          tx.getAttribute('id') || null
        ));
      }
    }

    // Graphical contrast — check every data-encoding semantic element's
    // stroke/fill. We skip decorative/presentational groups.
    for (var si = 0; si < semElems.length; si++) {
      var se = semElems[si];
      // For <g> the "color" is on its children (paths, rects). Pull from
      // the first drawable descendant.
      var drawable = null;
      var kids = se.el.getElementsByTagName ? se.el.getElementsByTagName('*') : [];
      for (var ki = 0; ki < kids.length; ki++) {
        var k = kids[ki];
        var kt = (k.tagName || '').toLowerCase();
        if (kt === 'path' || kt === 'rect' || kt === 'circle' ||
            kt === 'ellipse' || kt === 'line' || kt === 'polygon' || kt === 'polyline') {
          drawable = k; break;
        }
      }
      // Also check the element itself if it's drawable.
      if (!drawable) {
        var tag = (se.el.tagName || '').toLowerCase();
        if (tag === 'path' || tag === 'rect' || tag === 'circle' ||
            tag === 'ellipse' || tag === 'line') {
          drawable = se.el;
        }
      }
      if (!drawable) continue;
      var col = _strokeFill(drawable);
      if (!col) continue;
      var r = _contrast(col, bg);
      if (r != null && r < WCAG_GRAPHICAL_MIN) {
        findings.push(_make(
          'W_ARTIFACT_CONTRAST_GRAPHICAL',
          'Graphical element contrast ' + r.toFixed(2) + ':1 is below WCAG 2.1 SC 1.4.11 ' +
          'minimum ' + WCAG_GRAPHICAL_MIN + ':1 (' + se.cls + ').',
          null,
          se.id
        ));
      }
    }

    var blocks = false;
    for (var fi = 0; fi < findings.length; fi++) {
      if (findings[fi].severity === 'error') { blocks = true; break; }
    }
    return { findings: findings, blocks: blocks };
  }

  // ── Public surface ──────────────────────────────────────────────────────
  ns.artifactAdversarial = {
    review: review,

    // Low-level exports for unit tests.
    _parseTransform:  _parseTransform,
    _pathBBox:        _pathBBox,
    _bboxFromAttrs:   _bboxFromAttrs,
    _intersectArea:   _intersectArea,
    _contrast:        _contrast,
    _luminance:       _luminance,
    _parseColor:      _parseColor,
    _resolveBackground: _resolveBackground,

    // Tunable thresholds (reviewers can poke these in tests).
    OVERLAP_CRITICAL_THRESHOLD: OVERLAP_CRITICAL_THRESHOLD,
    TEXT_TRUNC_WARN_THRESHOLD:  TEXT_TRUNC_WARN_THRESHOLD,
    TEXT_TRUNC_CRIT_THRESHOLD:  TEXT_TRUNC_CRIT_THRESHOLD,
    WCAG_TEXT_MIN:              WCAG_TEXT_MIN,
    WCAG_GRAPHICAL_MIN:         WCAG_GRAPHICAL_MIN,
  };

}(typeof window !== 'undefined' ? window : globalThis));
