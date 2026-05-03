/**
 * save-canvas.js — WP-7.4.8
 *
 * Implements the **Save** + **Autosave** commands per Visual Intelligence
 * Implementation Plan §11.7 ("Canvas Mechanics — Save scope" + "Autosave")
 * and §13.4 WP-7.4.8.
 *
 *   Photoshop equivalent:  File → Save / autosave timer
 *
 * ── Architecture ────────────────────────────────────────────────────────────
 *
 * Self-registering IIFE that lives alongside `visual-panel.js` rather than
 * inside it (Plan §13 recommends new commands hook in via their own module so
 * the §7.4 / §7.5 / §7.1 WPs running in parallel don't collide on
 * `visual-panel.js` edits).
 *
 * The module reads the four-layer Konva model that VisualPanel exposes
 * (`backgroundLayer` / `annotationLayer` / `userInputLayer` /
 * `selectionLayer`) plus the persisted canvas-state metadata, builds a
 * canvas-state object via `OraCanvasFileFormat`, and either:
 *
 *   * Writes via fetch POST `/api/canvas/save` (default) — server persists
 *     under `~/ora/sessions/<conversation_id>/canvas/`.
 *   * Returns the bytes synchronously (test-mode hook) so the harness can
 *     verify the round-trip without a server.
 *
 * ── Save scope (Plan §11.7) ─────────────────────────────────────────────────
 *
 * The canvas is logically up to 10000×10000 px, but most edits use only a
 * fraction of that space. Saving the full canvas wastes bytes and pushes
 * cross-machine sync over a cliff. So Save bounds the persisted file to:
 *
 *     bbox(all rendered objects) + 100 px margin on each side
 *
 * The bbox is computed from the same union the resize-canvas command uses
 * (`computeBoundingBox()` walks the four Konva layers and the SVG host).
 * Empty space outside that extent is dropped — the saved file's
 * `metadata.canvas_size` reflects the bounded extent, and
 * `metadata.content_extent` records the original bbox pre-margin so a load
 * can place objects back at their world coordinates.
 *
 * For an empty canvas (no objects on any layer), Save falls back to the
 * default 10000×10000 nominal size with no extent metadata — there's no
 * content to bound. This is the "pristine new file" case.
 *
 * ── Autosave (Plan §11.7) ───────────────────────────────────────────────────
 *
 * A 30-second timer fires whenever there are pending changes since the last
 * save. The dirty flag is set by `markDirty(panel)` (called from
 * `_pushHistory` via the hook installed at boot — see `_installPanelHook`).
 *
 * Major operations (AI generation, large paste, image upload) call
 * `saveImmediate(panel, reason)` directly — those bypass the 30 s window.
 *
 * Three artifacts per autosave (per WP brief):
 *   1. `<timestamp>.ora-canvas`           — gzip canvas state via canvas-file-format
 *   2. embedded image data                 — already inline in the JSON state
 *   3. `<timestamp>.preview.png`          — raster preview of current view
 *                                            via Konva stage.toDataURL().
 *
 * Plus a stable `latest.ora-canvas` symlink-equivalent (the server overwrites
 * a copy at `latest.ora-canvas` on every save) so callers that want "the
 * current state" without a directory listing have a known path.
 *
 * ── Public surface — exposed as `window.OraSaveCanvas` ─────────────────────
 *
 *   buildCanvasState(panel) → state
 *     Walk the four Konva layers + SVG host and assemble a canvas-state
 *     object that conforms to canvas-state.schema.json. Includes the current
 *     view (zoom + pan) via `panel.getViewState()`.
 *
 *   computeContentExtent(state, marginPx?) → { x, y, width, height } | null
 *     Pure helper. Walks `state.objects` and returns the union bbox plus the
 *     specified margin (default 100). Returns null when there are no objects.
 *
 *   boundStateToContent(state, marginPx?) → { state, extent }
 *     Mutates a state object so its canvas_size matches the bounded extent
 *     (content + margin) and translates every object's (x, y) to make the
 *     bounded region origin (0, 0). Stores the original (pre-translation)
 *     bbox in `metadata.content_extent`. Returns a NEW state object (does
 *     not mutate input). When the canvas is empty, returns the input state
 *     unmodified with extent=null.
 *
 *   saveNow(panel, opts) → Promise<{ ok, path?, bytes?, extent }>
 *     Manual save command. Computes content extent, builds bounded state,
 *     gzips via canvas-file-format, POSTs to `/api/canvas/save`. Returns
 *     the server's accepted path or a structured error.
 *     `opts` shape:
 *       {
 *         conversation_id?: string,    // overrides panel.config.conversation_id
 *         reason?:          string,    // 'manual' | 'autosave' | 'immediate' | …
 *         intent?:          string,    // 'save' | 'export' | 'save-as' (share gate)
 *         dryRun?:          boolean,   // skip POST; return bytes for tests
 *       }
 *
 *   saveImmediate(panel, reason) → Promise<{ ok, path?, extent }>
 *     Bypass the autosave timer. Used by chat-panel after AI generation,
 *     by paste handlers when paste-size > threshold, etc.
 *
 *   startAutosave(panel, opts?) → void
 *   stopAutosave(panel) → void
 *     Lifecycle hooks. `init()` calls `startAutosave(panel)` once at boot
 *     for each VisualPanel instance. `panel.destroy()` calls `stopAutosave`.
 *
 *   markDirty(panel) → void
 *   isDirty(panel) → boolean
 *     Dirty-flag accessors. `_installPanelHook` wraps `_pushHistory` so any
 *     change that records an undo frame also marks the panel dirty.
 *
 *   init() → void
 *     Idempotent boot wiring. (1) Calls `OraCanvasFileFormat._setAjv` with
 *     the compiler's compiled validator (closes the WP-7.0.2 follow-up).
 *     (2) Installs the panel hook on every VisualPanel that mounts. Safe to
 *     call multiple times; only the first call wires.
 *
 * ── Constraints ─────────────────────────────────────────────────────────────
 *
 *   * Pure, stateless module modulo the per-panel autosave timer + dirty flag
 *     (which live ON the panel as `_autosaveTimer` and `_dirty`).
 *   * Touches visual-panel.js only via a single override of `_pushHistory`
 *     installed at boot. Does NOT add new fields to VisualPanel.prototype
 *     (per the .bak<N> coordination note in CLAUDE.md).
 *   * Test mode: when `opts.dryRun=true`, returns bytes + state directly
 *     without touching fetch / DOM / disk.
 */

(function (root) {
  'use strict';

  // ── Constants ─────────────────────────────────────────────────────────────

  var DEFAULT_AUTOSAVE_INTERVAL_MS = 30 * 1000;   // 30 s per Plan §11.7
  var DEFAULT_MARGIN_PX            = 100;          // 100 px per Plan §11.7
  var DEFAULT_PREVIEW_PIXEL_RATIO  = 1;            // 1× raster preview

  // gzip magic bytes — matches canvas-file-format.js sniff helper.
  var GZIP_MAGIC_0 = 0x1F;
  var GZIP_MAGIC_1 = 0x8B;

  // Reasons that trigger an immediate (bypass-timer) save.
  var IMMEDIATE_REASONS = {
    'ai-generation':   1,
    'large-paste':     1,
    'image-upload':    1,
    'manual':          1,  // explicit Save command
  };

  // ── Helpers ───────────────────────────────────────────────────────────────

  function _isObj(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }
  function _isArr(v) { return Array.isArray(v); }
  function _isFiniteNumber(v) { return typeof v === 'number' && isFinite(v); }
  function _isPositiveNumber(v) { return _isFiniteNumber(v) && v > 0; }

  function _getFmt() {
    return (typeof window !== 'undefined' && window.OraCanvasFileFormat) || null;
  }
  function _getCompiler() {
    return (typeof window !== 'undefined' && window.OraVisualCompiler) || null;
  }
  function _getReminder() {
    return (typeof window !== 'undefined' && window.OraCanvasShareReminder) || null;
  }
  function _now() {
    return new Date().toISOString();
  }

  // ── Konva → canvas-state object translation ──────────────────────────────

  /**
   * Convert a Konva user-input shape node into a canvas-state object. Maps
   * the userShapeType attr to the schema's `kind` enum:
   *   rect / ellipse / diamond / text → kind: 'shape' (or 'text' for text)
   *   line / arrow                    → kind: 'shape' (carries endpoints in attrs)
   *
   * The schema accepts arbitrary `attrs` per object kind, so we round-trip
   * the userShape attrs verbatim and let load-side replay reconstruct the
   * Konva node from the same attrs.
   */
  function _shapeToObject(node) {
    if (!node) return null;
    var attrs = (node.attrs && _isObj(node.attrs)) ? node.attrs : {};
    var typ   = attrs.userShapeType;
    if (!typ) return null;
    var id    = attrs.userShapeId || ('u-shape-' + Math.random().toString(36).slice(2, 8));
    // Konva coordinates: prefer live x()/y() over attr cache.
    var x = (typeof node.x === 'function') ? node.x() : (attrs.x || 0);
    var y = (typeof node.y === 'function') ? node.y() : (attrs.y || 0);
    var w = (typeof node.width === 'function')  ? node.width()  : (attrs.width  || 0);
    var h = (typeof node.height === 'function') ? node.height() : (attrs.height || 0);
    var kind = (typ === 'text') ? 'text' : 'shape';
    // Konva class hint per type — lets the load-side replay pick the right
    // constructor without re-deriving from userShapeType.
    var konvaClass = ({
      rect:    'Rect',
      ellipse: 'Ellipse',
      diamond: 'Line',     // diamond is a closed polygon line in Konva
      line:    'Line',
      arrow:   'Arrow',
      text:    'Text',
    })[typ] || 'Shape';
    var out = {
      id:          String(id),
      kind:        kind,
      layer:       'user_input',
      x:           _isFiniteNumber(x) ? x : 0,
      y:           _isFiniteNumber(y) ? y : 0,
      konva_class: konvaClass,
    };
    if (_isPositiveNumber(w)) out.width  = w;
    if (_isPositiveNumber(h)) out.height = h;
    // Round-trip everything else through `attrs` — schema explicitly leaves
    // attrs free-form so Konva owns its own attribute surface.
    var bag = {
      userShapeType:    typ,
      userShapeId:      String(id),
    };
    if (typeof attrs.userLabel === 'string' && attrs.userLabel.length) bag.userLabel = attrs.userLabel;
    if (attrs.points)              bag.points = attrs.points.slice ? attrs.points.slice() : attrs.points;
    if (attrs.connEndpointStart)   bag.connEndpointStart = attrs.connEndpointStart;
    if (attrs.connEndpointEnd)     bag.connEndpointEnd   = attrs.connEndpointEnd;
    if (typeof attrs.fill === 'string')   bag.fill   = attrs.fill;
    if (typeof attrs.stroke === 'string') bag.stroke = attrs.stroke;
    if (_isPositiveNumber(attrs.strokeWidth)) bag.strokeWidth = attrs.strokeWidth;
    out.attrs = bag;
    return out;
  }

  /**
   * Convert a Konva annotation node into a canvas-state object. Annotations
   * are kind 'shape' with a discriminator attr `annotation_kind`. We only
   * persist user-authored annotations (annotationSource='user').
   */
  function _annotationToObject(node) {
    if (!node) return null;
    var attrs = (node.attrs && _isObj(node.attrs)) ? node.attrs : {};
    if (attrs.annotationSource !== 'user') return null;
    var id  = attrs.userAnnotationId || ('ua-' + Math.random().toString(36).slice(2, 8));
    var kind = attrs.annotationKind;
    if (!kind) return null;
    var x = (typeof node.x === 'function') ? node.x() : (attrs.x || 0);
    var y = (typeof node.y === 'function') ? node.y() : (attrs.y || 0);
    // Annotations come in five flavors per WP-5.1; each maps to a different
    // Konva shape on replay.
    var konvaClass = ({
      callout:       'Group',
      highlight:     'Rect',
      strikethrough: 'Line',
      sticky:        'Group',
      pen:           'Line',
    })[kind] || 'Shape';
    var out = {
      id:          String(id),
      kind:        'shape',
      layer:       'annotation',
      x:           _isFiniteNumber(x) ? x : 0,
      y:           _isFiniteNumber(y) ? y : 0,
      konva_class: konvaClass,
    };
    var bag = {
      annotationSource:  'user',
      annotationKind:    kind,
      userAnnotationId:  String(id),
    };
    if (typeof attrs.text === 'string')  bag.text = attrs.text;
    if (attrs.targetId != null)          bag.targetId = attrs.targetId;
    if (attrs.points)                    bag.points = attrs.points.slice ? attrs.points.slice() : attrs.points;
    if (attrs.position && _isObj(attrs.position)) bag.position = { x: attrs.position.x, y: attrs.position.y };
    out.attrs = bag;
    return out;
  }

  /**
   * Capture the SVG-host artifact (background) as an image object. The SVG
   * markup is serialized to a base64 data string so it can round-trip
   * through canvas-state.objects (which only carries embedded data, no
   * external file refs). A future load command can restore the SVG by
   * decoding image_data.data.
   */
  function _backgroundSvgToObject(panel) {
    if (!panel || !panel._svgHost) return null;
    var svg = panel._svgHost.querySelector('svg');
    if (!svg) return null;
    var serializer = (typeof XMLSerializer !== 'undefined') ? new XMLSerializer() : null;
    var markup = serializer ? serializer.serializeToString(svg) : svg.outerHTML;
    if (!markup) return null;
    var b64;
    try {
      // Use TextEncoder + btoa over UTF-8 bytes when available; fall back
      // to direct btoa (browsers handle latin1-safe markup).
      if (typeof TextEncoder !== 'undefined' && typeof btoa === 'function') {
        var bytes = new TextEncoder().encode(markup);
        var binary = '';
        for (var i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
        b64 = btoa(binary);
      } else if (typeof btoa === 'function') {
        b64 = btoa(unescape(encodeURIComponent(markup)));
      } else {
        return null;
      }
    } catch (e) {
      return null;
    }
    var w = parseFloat(svg.getAttribute('width'));
    var h = parseFloat(svg.getAttribute('height'));
    var out = {
      id:    'bg-svg',
      kind:  'image',
      layer: 'background',
      x:     0,
      y:     0,
      image_data: {
        mime_type: 'image/svg+xml',
        encoding:  'base64',
        data:      b64,
      },
    };
    if (_isPositiveNumber(w)) out.width  = w;
    if (_isPositiveNumber(h)) out.height = h;
    return out;
  }

  /**
   * Capture an attached background raster image (Konva.Image on
   * backgroundLayer, set by WP-4.1) as a canvas-state image object. Reads
   * from the panel's `_pendingImage.dataUrl` when present (highest fidelity
   * — we still have the original blob's encoded form).
   */
  function _backgroundRasterToObject(panel) {
    if (!panel || !panel._pendingImage) return null;
    var pi = panel._pendingImage;
    if (!pi.dataUrl || typeof pi.dataUrl !== 'string') return null;
    var m = /^data:([^;,]+);base64,(.*)$/.exec(pi.dataUrl);
    if (!m) return null;
    var mime = m[1];
    var b64  = m[2];
    if (!/^image\//.test(mime) || !b64) return null;
    var node = panel._backgroundImageNode;
    var x = node && typeof node.x === 'function' ? node.x() : 0;
    var y = node && typeof node.y === 'function' ? node.y() : 0;
    var w = node && typeof node.width === 'function'  ? node.width()  : 0;
    var h = node && typeof node.height === 'function' ? node.height() : 0;
    var out = {
      id:    'bg-image',
      kind:  'image',
      layer: 'background',
      x:     _isFiniteNumber(x) ? x : 0,
      y:     _isFiniteNumber(y) ? y : 0,
      image_data: {
        mime_type: mime,
        encoding:  'base64',
        data:      b64,
      },
    };
    if (_isPositiveNumber(w)) out.width  = w;
    if (_isPositiveNumber(h)) out.height = h;
    return out;
  }

  /**
   * Build a canvas-state object from the panel's current Konva scene. Uses
   * `OraCanvasFileFormat.newCanvasState` when available so the structural
   * skeleton (layers, view, schema_version, format_id) is canonical;
   * fills in `objects[]` from the live Konva nodes.
   *
   * The current view (zoom + pan) is captured via `panel.getViewState()`
   * (added by WP-7.4.7).
   */
  function buildCanvasState(panel) {
    var fmt = _getFmt();
    var canvasSize = (panel && panel._canvasState && panel._canvasState.metadata
                      && panel._canvasState.metadata.canvas_size)
      ? { width:  panel._canvasState.metadata.canvas_size.width,
          height: panel._canvasState.metadata.canvas_size.height }
      : (fmt
          ? { width: fmt.DEFAULT_CANVAS_W, height: fmt.DEFAULT_CANVAS_H }
          : { width: 10000, height: 10000 });

    var conversationId = (panel && panel.config && panel.config.conversation_id) || null;
    var state;
    if (fmt && typeof fmt.newCanvasState === 'function') {
      state = fmt.newCanvasState({
        canvas_size:     canvasSize,
        conversation_id: conversationId || undefined,
      });
    } else {
      state = {
        schema_version: '0.1.0',
        format_id:      'ora-canvas',
        metadata:       {
          canvas_size: canvasSize,
          created_at:  _now(),
          modified_at: _now(),
        },
        view:    { zoom: 1, pan: { x: 0, y: 0 } },
        layers:  [
          { id: 'background', kind: 'background', visible: true, locked: false, opacity: 1 },
          { id: 'annotation', kind: 'annotation', visible: true, locked: false, opacity: 1 },
          { id: 'user_input', kind: 'user_input', visible: true, locked: false, opacity: 1 },
          { id: 'selection',  kind: 'selection',  visible: true, locked: false, opacity: 1 },
        ],
        objects: [],
      };
      if (conversationId) state.metadata.conversation_id = conversationId;
    }

    // Capture the live view state — WP-7.4.7 entry point.
    if (panel && typeof panel.getViewState === 'function') {
      try {
        var v = panel.getViewState();
        if (_isObj(v)) state.view = v;
      } catch (e) { /* fall through to default */ }
    }
    state.metadata.modified_at = _now();

    var objects = [];

    // Background — SVG artifact (priority) OR raster image. Mutually
    // exclusive in practice (panel renders one at a time).
    var bgSvg = _backgroundSvgToObject(panel);
    if (bgSvg) objects.push(bgSvg);
    else {
      var bgRaster = _backgroundRasterToObject(panel);
      if (bgRaster) objects.push(bgRaster);
    }

    // userInput — every user-drawn shape.
    if (panel && panel.userInputLayer && typeof panel.userInputLayer.getChildren === 'function') {
      var shapes = panel.userInputLayer.getChildren();
      for (var i = 0; i < shapes.length; i++) {
        var s = shapes[i];
        if (!s) continue;
        if (s.getAttr && s.getAttr('name') === 'user-shape-preview') continue;  // in-flight
        var obj = _shapeToObject(s);
        if (obj) objects.push(obj);
      }
    }

    // annotation — user-authored annotations only.
    if (panel && panel.annotationLayer && typeof panel.annotationLayer.getChildren === 'function') {
      var ann = panel.annotationLayer.getChildren();
      for (var j = 0; j < ann.length; j++) {
        var a = ann[j];
        if (!a) continue;
        var aobj = _annotationToObject(a);
        if (aobj) objects.push(aobj);
      }
    }

    state.objects = objects;
    return state;
  }

  // ── Content extent + bounded save scope ──────────────────────────────────

  /**
   * Compute the union bbox of every object in `state.objects` and pad it
   * by `marginPx` on each side. Width/height fall back to 0 when an object
   * doesn't carry them (point-like text, etc.). Returns null when objects
   * is empty.
   */
  function computeContentExtent(state, marginPx) {
    if (!_isObj(state) || !_isArr(state.objects) || state.objects.length === 0) return null;
    var margin = _isFiniteNumber(marginPx) ? marginPx : DEFAULT_MARGIN_PX;
    var minX =  Infinity, minY =  Infinity;
    var maxX = -Infinity, maxY = -Infinity;
    for (var i = 0; i < state.objects.length; i++) {
      var o = state.objects[i];
      if (!_isObj(o)) continue;
      var x = _isFiniteNumber(o.x) ? o.x : 0;
      var y = _isFiniteNumber(o.y) ? o.y : 0;
      var w = _isFiniteNumber(o.width)  ? o.width  : 0;
      var h = _isFiniteNumber(o.height) ? o.height : 0;
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x + w > maxX) maxX = x + w;
      if (y + h > maxY) maxY = y + h;
    }
    if (!isFinite(minX) || !isFinite(minY)) return null;
    return {
      x:      minX - margin,
      y:      minY - margin,
      width:  (maxX - minX) + margin * 2,
      height: (maxY - minY) + margin * 2,
    };
  }

  /**
   * Bound `state` to its content + margin. Returns a new state with:
   *   * metadata.canvas_size set to the bounded extent
   *   * metadata.content_extent recording the original (pre-translation) bbox
   *   * every object's (x, y) translated so the bounded region origin is (0, 0)
   *
   * The bbox-only translation matches the resize-canvas anchor='top-left'
   * convention (no other knobs needed — Save always anchors top-left of the
   * bounded region). View state is preserved as-is (pan/zoom is a viewport
   * concept, not a content one).
   *
   * For empty canvases, returns the input state unchanged with extent=null.
   */
  function boundStateToContent(state, marginPx) {
    if (!_isObj(state)) return { state: state, extent: null };
    var extent = computeContentExtent(state, marginPx);
    if (!extent) return { state: state, extent: null };
    var dx = -extent.x;
    var dy = -extent.y;
    // Deep clone (canonical-ish: we only need depth-1 + objects array).
    var next = {};
    for (var k in state) {
      if (Object.prototype.hasOwnProperty.call(state, k)) next[k] = state[k];
    }
    next.metadata = {};
    if (_isObj(state.metadata)) {
      for (var mk in state.metadata) {
        if (Object.prototype.hasOwnProperty.call(state.metadata, mk)) {
          next.metadata[mk] = state.metadata[mk];
        }
      }
    }
    next.metadata.canvas_size = { width: extent.width, height: extent.height };
    // Record the original content bbox (pre-margin). This is the WP-7.0.2
    // metadata.content_extent follow-up flag.
    next.metadata.content_extent = {
      x:      extent.x + marginPx_or_default(marginPx),
      y:      extent.y + marginPx_or_default(marginPx),
      width:  extent.width  - marginPx_or_default(marginPx) * 2,
      height: extent.height - marginPx_or_default(marginPx) * 2,
    };
    next.metadata.modified_at = _now();

    // Translate every object.
    next.objects = (state.objects || []).map(function (o) {
      if (!_isObj(o)) return o;
      var clone = {};
      for (var ok in o) {
        if (Object.prototype.hasOwnProperty.call(o, ok)) clone[ok] = o[ok];
      }
      if (_isFiniteNumber(o.x)) clone.x = o.x + dx;
      if (_isFiniteNumber(o.y)) clone.y = o.y + dy;
      return clone;
    });

    return { state: next, extent: extent };
  }

  function marginPx_or_default(m) {
    return _isFiniteNumber(m) ? m : DEFAULT_MARGIN_PX;
  }

  // ── Raster preview ────────────────────────────────────────────────────────

  /**
   * Capture the current Konva stage as a PNG data URL. Used to ship a
   * thumbnail with each autosave for the file browser / picker. Returns
   * null when the panel has no stage (test mode) or the call throws.
   */
  function _capturePreview(panel, opts) {
    if (!panel || !panel.stage || typeof panel.stage.toDataURL !== 'function') return null;
    opts = opts || {};
    try {
      return panel.stage.toDataURL({
        mimeType:    'image/png',
        pixelRatio:  opts.pixelRatio || DEFAULT_PREVIEW_PIXEL_RATIO,
      });
    } catch (e) {
      return null;
    }
  }

  // ── Save dispatch (server POST) ───────────────────────────────────────────

  /**
   * POST the gzipped canvas-state bytes + preview to `/api/canvas/save`.
   * The server persists under `~/ora/sessions/<conversation_id>/canvas/`
   * and returns the accepted file paths.
   *
   * Multipart form-encoded so we can ship a binary body alongside metadata
   * without base64-doubling.
   */
  function _postSave(conversationId, bytes, previewDataUrl, reason) {
    if (typeof fetch !== 'function') {
      return Promise.reject(new Error('save-canvas: fetch not available'));
    }
    var fd = new FormData();
    fd.append('conversation_id', conversationId || 'main');
    fd.append('reason', reason || 'autosave');
    // Gzip bytes as a Blob so multer/Werkzeug treat it as a file.
    var blob = new Blob([bytes], { type: 'application/gzip' });
    fd.append('canvas', blob, 'canvas.ora-canvas');
    if (previewDataUrl) fd.append('preview', previewDataUrl);
    return fetch('/api/canvas/save', { method: 'POST', body: fd })
      .then(function (resp) {
        if (!resp.ok) {
          return resp.text().then(function (text) {
            throw new Error('save-canvas: server returned ' + resp.status + ' — ' + text);
          });
        }
        return resp.json();
      });
  }

  // ── Public: saveNow / saveImmediate ──────────────────────────────────────

  /**
   * Manual save — full pipeline:
   *   1. buildCanvasState(panel)
   *   2. boundStateToContent(state, 100)
   *   3. canvas-file-format.write(boundedState, { compressed: true })
   *   4. capturePreview(panel)
   *   5. POST /api/canvas/save (or return bytes when dryRun=true)
   *   6. dispatch ora:canvas-pre-share when intent is 'export' or 'save-as'
   *
   * Returns Promise<{ ok, path?, bytes?, extent, reason }>.
   */
  function saveNow(panel, opts) {
    opts = opts || {};
    var fmt = _getFmt();
    if (!fmt) return Promise.reject(new Error('save-canvas: OraCanvasFileFormat not loaded'));
    if (!panel) return Promise.reject(new Error('save-canvas: panel is required'));

    var conversationId =
      opts.conversation_id ||
      (panel.config && panel.config.conversation_id) ||
      'main';
    var reason = opts.reason || 'manual';
    var intent = opts.intent || 'save';
    var marginPx = _isFiniteNumber(opts.marginPx) ? opts.marginPx : DEFAULT_MARGIN_PX;

    var state = buildCanvasState(panel);
    var bound = boundStateToContent(state, marginPx);

    // Mirror back onto the panel so subsequent commands (resize, etc.) read
    // the latest state. We keep the unbounded state for in-memory use; the
    // bounded form is what we persist.
    panel._canvasState = state;

    return fmt.write(bound.state, { compressed: true }).then(function (bytes) {
      var preview = _capturePreview(panel, opts);

      // Mark clean — even if the POST fails downstream the bytes are
      // captured and we don't want to thrash the autosave timer in a tight
      // loop. A subsequent edit will re-mark dirty.
      panel._dirty = false;

      if (opts.dryRun) {
        return { ok: true, bytes: bytes, preview: preview, extent: bound.extent, reason: reason };
      }

      // Share-reminder gate: only fires when the user is explicitly
      // exporting or save-as'ing OUTSIDE the per-conversation canvas dir.
      // Plain autosave / manual save into the session dir is local-only,
      // so we skip the reminder for those (no audience expansion).
      var reminder = _getReminder();
      var needsShareGate = (intent === 'export' || intent === 'save-as');
      var dispatch = function () {
        return _postSave(conversationId, bytes, preview, reason).then(function (resp) {
          return {
            ok: true, path: resp && resp.path, latest: resp && resp.latest,
            preview_path: resp && resp.preview_path,
            extent: bound.extent, reason: reason,
          };
        }, function (err) {
          panel._dirty = true;   // POST failed → keep dirty so the next tick retries.
          throw err;
        });
      };

      if (needsShareGate && reminder && typeof reminder.requestShare === 'function') {
        return new Promise(function (resolve, reject) {
          reminder.requestShare({
            intent:    intent,
            path:      opts.path || ('~/ora/sessions/' + conversationId + '/canvas/'),
            onConfirm: function () {
              dispatch().then(resolve, reject);
            },
            onCancel:  function () {
              resolve({ ok: false, cancelled: true, reason: 'share-cancelled' });
            },
          });
        });
      }
      // No reminder gate, but still notify any other listeners that a save
      // is happening (e.g. analytics-style hooks). The CustomEvent itself
      // doesn't block — we dispatch and continue.
      if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
        try {
          var evt = new CustomEvent('ora:canvas-pre-share', {
            detail: {
              path:     opts.path || ('~/ora/sessions/' + conversationId + '/canvas/'),
              intent:   intent,
              onConfirm: function () { /* already executing */ },
              onCancel:  function () { /* no-op for non-shareable */ },
            },
          });
          // For non-shareable intents the reminder module's listener will
          // fast-path to onConfirm — no UI gate. Plain CustomEvent fallback
          // when CustomEvent constructor isn't available is silent.
          if (!needsShareGate) {
            // Skip dispatch when not shareable — avoids stale modals from
            // older session state. Only "export"/"save-as" should ever
            // surface the reminder. We keep this branch as documentation.
          } else {
            window.dispatchEvent(evt);
          }
        } catch (e) { /* no CustomEvent in this runtime; ignore */ }
      }
      return dispatch();
    });
  }

  /**
   * Bypass the autosave timer: trigger an immediate save now. Reasons come
   * from the IMMEDIATE_REASONS allowlist; others fall back to 'manual'.
   */
  function saveImmediate(panel, reason) {
    var r = (reason && IMMEDIATE_REASONS[reason]) ? reason : 'manual';
    return saveNow(panel, { reason: r, intent: 'save' });
  }

  // ── Autosave timer ────────────────────────────────────────────────────────

  function startAutosave(panel, opts) {
    if (!panel) return;
    if (panel._autosaveTimer) return;     // idempotent
    opts = opts || {};
    var interval = _isFiniteNumber(opts.intervalMs) ? opts.intervalMs : DEFAULT_AUTOSAVE_INTERVAL_MS;
    panel._autosaveTimer = setInterval(function () {
      if (!panel || panel._destroyed) return;
      if (!panel._dirty) return;
      // Fire-and-log; an autosave failure should not throw or block the UI.
      saveNow(panel, { reason: 'autosave', intent: 'save' }).then(
        function () { /* ok */ },
        function (err) {
          if (typeof console !== 'undefined' && console.warn) {
            console.warn('[save-canvas] autosave failed: ' + (err && err.message ? err.message : err));
          }
        }
      );
    }, interval);
  }

  function stopAutosave(panel) {
    if (!panel || !panel._autosaveTimer) return;
    try { clearInterval(panel._autosaveTimer); } catch (e) { /* ignore */ }
    panel._autosaveTimer = null;
  }

  // ── Dirty flag ────────────────────────────────────────────────────────────

  function markDirty(panel) {
    if (panel) panel._dirty = true;
  }
  function isDirty(panel) {
    return !!(panel && panel._dirty);
  }

  // ── Boot wiring ──────────────────────────────────────────────────────────

  var _booted = false;

  /**
   * Attach the dirty-tracking hook to a VisualPanel. Wraps `_pushHistory`
   * so any change that records an undo frame also marks dirty. Idempotent
   * per-panel.
   */
  function _installPanelHook(panel) {
    if (!panel || panel._saveCanvasHookInstalled) return;
    panel._saveCanvasHookInstalled = true;
    var orig = panel._pushHistory;
    if (typeof orig !== 'function') return;
    panel._pushHistory = function (frame) {
      var ret = orig.call(this, frame);
      // Suppressed pushes (replays during undo/redo) don't dirty the canvas
      // — undo is by definition a return to a prior saved state.
      if (!this._suppressHistory) this._dirty = true;
      return ret;
    };
  }

  /**
   * Idempotent boot wiring. Safe to call multiple times.
   *
   *   1. Wires OraVisualCompiler._ajv into OraCanvasFileFormat._setAjv —
   *      closes the WP-7.0.2 follow-up flag so canvas-state validate()
   *      uses the compiled JSON Schema instead of the structural fallback.
   *   2. Patches VisualPanel.prototype.init / .destroy to install the
   *      dirty-tracking hook + start/stop the autosave timer per instance.
   */
  function init() {
    if (_booted) return;
    _booted = true;

    // (1) Bootstrap Ajv into canvas-file-format.
    var fmt = _getFmt();
    var compiler = _getCompiler();
    if (fmt && typeof fmt._setAjv === 'function' && compiler && compiler._ajv) {
      try { fmt._setAjv(compiler._ajv); } catch (e) { /* ignore */ }
    }

    // (2) Patch VisualPanel lifecycle.
    var VP = (typeof window !== 'undefined' && window.VisualPanel) || null;
    if (!VP || typeof VP !== 'function') return;
    var origInit    = VP.prototype.init;
    var origDestroy = VP.prototype.destroy;
    if (typeof origInit === 'function') {
      VP.prototype.init = function () {
        var ret = origInit.apply(this, arguments);
        try {
          _installPanelHook(this);
          startAutosave(this);
        } catch (e) { /* never block init on autosave wiring */ }
        return ret;
      };
    }
    if (typeof origDestroy === 'function') {
      VP.prototype.destroy = function () {
        try { stopAutosave(this); } catch (e) { /* ignore */ }
        return origDestroy.apply(this, arguments);
      };
    }
  }

  // Auto-boot on script load. Defers Ajv bootstrap until the compiler
  // bootstrapAjv() promise resolves (canvas-file-format._setAjv is also
  // called by a later poll, below).
  if (typeof window !== 'undefined') {
    // Defer one tick so VisualPanel + OraCanvasFileFormat scripts have a
    // chance to register their globals first (load order in index.html
    // puts visual-panel.js before this command).
    if (typeof setTimeout === 'function') {
      setTimeout(init, 0);
    } else {
      init();
    }
    // Re-attempt Ajv hookup after bootstrapAjv() completes. We poll a
    // bounded number of times to avoid leaking a long-lived timer when
    // bootstrapAjv() never resolves (e.g. headless test).
    var _ajvAttempts = 0;
    var _ajvPoll = setInterval(function () {
      _ajvAttempts++;
      var fmt2 = _getFmt(), c2 = _getCompiler();
      if (fmt2 && typeof fmt2._setAjv === 'function' && c2 && c2._ajv) {
        try { fmt2._setAjv(c2._ajv); } catch (e) { /* ignore */ }
        clearInterval(_ajvPoll);
      } else if (_ajvAttempts > 50) {
        clearInterval(_ajvPoll);
      }
    }, 200);
  }

  // ── Module export ────────────────────────────────────────────────────────

  var ns = {
    DEFAULT_AUTOSAVE_INTERVAL_MS: DEFAULT_AUTOSAVE_INTERVAL_MS,
    DEFAULT_MARGIN_PX:            DEFAULT_MARGIN_PX,
    IMMEDIATE_REASONS:            IMMEDIATE_REASONS,
    buildCanvasState:             buildCanvasState,
    computeContentExtent:         computeContentExtent,
    boundStateToContent:          boundStateToContent,
    saveNow:                      saveNow,
    saveImmediate:                saveImmediate,
    startAutosave:                startAutosave,
    stopAutosave:                 stopAutosave,
    markDirty:                    markDirty,
    isDirty:                      isDirty,
    init:                         init,
    // Internals exposed for tests.
    _shapeToObject:               _shapeToObject,
    _annotationToObject:          _annotationToObject,
    _backgroundSvgToObject:       _backgroundSvgToObject,
    _backgroundRasterToObject:    _backgroundRasterToObject,
    _capturePreview:              _capturePreview,
    _installPanelHook:            _installPanelHook,
  };

  if (typeof window !== 'undefined') {
    window.OraSaveCanvas = ns;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = ns;
  }
})(typeof window !== 'undefined' ? window : this);
