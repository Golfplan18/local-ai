/**
 * VisualPanel — WP-2.1 + WP-3.1
 *
 * Dual-pane Konva-based panel that renders `ora-visual` envelopes into a
 * zoomable, pannable, keyboard-navigable canvas. The panel follows the
 * standard Ora panel contract:
 *   init(el, config), destroy(), onBridgeUpdate(state)
 *
 * It also registers a public surface on `window.OraPanels.visual` with
 * renderSpec(envelope) and clearArtifact() for external callers.
 *
 * ── Architecture ──────────────────────────────────────────────────────────
 * Konva draws four layers inside a Stage that sits above a DOM-overlay SVG
 * host. The layers (bottom → top) are:
 *
 *   backgroundLayer  — the currently-rendered SVG artifact. Kept as a live
 *                      DOM node (NOT rasterized) so semantic element IDs,
 *                      aria attrs, and native SVG hit testing remain intact.
 *                      A Konva.Group in this layer is used only as a sentinel
 *                      that tracks transform metadata.
 *   annotationLayer  — empty scaffold for WP-2.4 / Phase 5 Ora-added overlays.
 *   userInputLayer   — WP-3.1 user drawings (rects, ellipses, diamonds, lines,
 *                      arrows, text). Every shape carries the shared attribute
 *                      convention documented below so WP-3.2's serializer and
 *                      future WP-5 annotation consumers can walk the layer
 *                      without knowing VisualPanel's internals.
 *   selectionLayer   — highlight rectangle drawn around the currently
 *                      selected semantic element OR a user-drawn shape.
 *
 * ── SVG-into-Konva choice (tradeoff summary) ─────────────────────────────
 * We use a DOM-overlay approach rather than rasterizing the SVG into a
 * Konva.Image. The SVG lives in an absolutely-positioned <div class=
 * "visual-panel__svg-host"> sibling to the Konva container, and we mirror
 * the stage transform onto its CSS `transform` via a single Konva "pan/
 * zoom" event. Tradeoff:
 *   + preserves semantic DOM, hover/focus/aria behaviour, crisp vector
 *     rendering at every zoom level, and tab-chain interaction
 *   + works in jsdom (no canvas rasterization required) — makes tests
 *     trivial
 *   - the "background" isn't on a Konva layer per se; we keep a sentinel
 *     Konva.Group there so the layer remains a first-class citizen and
 *     annotations rendered later can be hit-tested against Konva's hit
 *     graph without conflict
 * This matches the hybrid pattern used by production Konva apps that want
 * rich DOM content (pdf.js, rich-text, embedded video) — Konva's own docs
 * recommend it (konvajs.org: "Konva + DOM overlay").
 *
 * ── Shared shape-attribute convention (WP-3.1 + WP-3.2 pact) ─────────────
 * Every Konva node appended to `userInputLayer` via the drawing tools MUST
 * carry the following attrs so WP-3.2 (canvas-serializer.js) and future
 * WP-5 annotation parsers can reconstruct the user's intent without having
 * to inspect the Konva class hierarchy. The attrs round-trip through
 * `Konva.Node.toJSON()` so `userInputLayer.toJSON()` is a complete
 * serialization pivot.
 *
 *   name:               'user-shape'             (Konva name for .find())
 *   userShapeType:      'rect' | 'ellipse' | 'diamond' | 'line' | 'arrow' | 'text'
 *   userShapeId:        '<stable unique id>'     (auto-generated — u-<type>-<n>)
 *   userLabel:          '<string>'               (text content for text tool;
 *                                                 empty string otherwise)
 *   userCluster:        '<cluster id>' | null    (WP-3.2 computes; we leave null)
 *   connEndpointStart:  '<userShapeId>' | null   (line/arrow: id of shape at
 *                                                 the start endpoint if anchored
 *                                                 within the snap threshold)
 *   connEndpointEnd:    '<userShapeId>' | null   (as above, for end endpoint)
 *
 * The snap threshold for endpoint anchoring is CONN_SNAP_PX (10 px).
 *
 * Note: Konva 9's `setAttrs` strips null-valued entries from its attrs map,
 * so null-valued convention keys are written directly to `node.attrs` to
 * preserve null semantics. Consumers should read via `getAttr(key)` which
 * returns null for a null stored value and undefined for a genuinely
 * missing key — both should be treated as "no endpoint anchor" / "no
 * cluster" by WP-3.2. `Konva.Node.toJSON()` drops both null and default
 * values; serialization consumers should treat a missing attr as null.
 *
 * ── Bridge contract ──────────────────────────────────────────────────────
 * onBridgeUpdate(state) inspects state.ora_visual_blocks. If the array
 * contains at least one block, the panel delegates the MOST RECENT entry
 * to the canvas_action state machine (WP-2.4).
 *
 * ── Canvas-action state machine (WP-2.4) ─────────────────────────────────
 * State: { _currentEnvelope, _conversationTurn, _hasPriorVisual }.
 *
 * The four Protocol §canvas_action values map to layer mutations:
 *
 *   replace   clear(backgroundLayer ∪ annotationLayer ∪ userInputLayer ∪
 *                   selectionLayer) then render the new envelope. DEFAULT
 *                   for the first visual in a conversation thread.
 *   update    clear(backgroundLayer ∪ selectionLayer) then render the new
 *                   envelope. annotationLayer + userInputLayer are preserved.
 *                   DEFAULT for subsequent visuals.
 *   annotate  preserve backgroundLayer. Read envelope.annotations (or
 *                   envelope.spec.annotations) and draw callout/highlight
 *                   overlays on annotationLayer. If no annotations content
 *                   is present, emit W_ANNOTATE_NO_CONTENT and no-op.
 *   clear     clear all four layers, reset state, emit no render.
 *
 * When canvas_action is omitted, the turn-position default applies:
 * first-visual → replace, subsequent → update.
 *
 * INVARIANT: userInputLayer is NEVER touched by update or annotate.
 * The user's drawings survive every Ora follow-up unless the envelope
 * explicitly says canvas_action:"clear" or canvas_action:"replace".
 *
 * ── WP-5.1 user annotations ──────────────────────────────────────────────
 * The user can author five kinds of annotation on top of the rendered
 * artifact: callout, highlight, strikethrough, sticky, pen. They live on
 * annotationLayer alongside model-emitted overlays from WP-2.4, but every
 * user-authored node carries `annotationSource="user"` so WP-5.2's
 * translator can filter them out. The shared attribute convention is:
 *
 *   annotationSource:    'user' | 'model'   (distinguishes authorship)
 *   annotationKind:      'callout' | 'highlight' | 'strikethrough' |
 *                        'sticky' | 'pen'
 *   userAnnotationId:    'ua-<kind>-<n>'    (monotonic, unique per panel)
 *   targetId:            '<svg id>' | null  (the semantic element the
 *                                            annotation anchors to, or
 *                                            null for free annotations)
 *   text:                '<string>'         (callout/sticky only)
 *   position:            {x, y}             (sticky free-position)
 *   points:              [x1,y1, x2,y2,...] (pen stroke)
 *
 * INVARIANT (preservation): canvas_action="update" and
 * canvas_action="annotate" preserve BOTH user annotations AND model
 * annotations on annotationLayer. canvas_action="clear" and
 * canvas_action="replace" clear everything. User annotations are thus
 * durable across Ora's follow-up rendering.
 */

(function () {
  'use strict';

  // ── Utilities ─────────────────────────────────────────────────────────────

  function _esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  /**
   * Render a fallback data table from a semantic_description.data_table_fallback
   * object: { columns: [...], rows: [[...], ...] }. Returns HTML string.
   */
  function _renderFallbackTable(table) {
    if (!table || !Array.isArray(table.columns) || !Array.isArray(table.rows)) {
      return '';
    }
    var thead = '<tr>' + table.columns.map(function (c) { return '<th>' + _esc(c) + '</th>'; }).join('') + '</tr>';
    var tbody = table.rows.map(function (row) {
      return '<tr>' + row.map(function (cell) { return '<td>' + _esc(cell) + '</td>'; }).join('') + '</tr>';
    }).join('');
    return '<table class="visual-panel__fallback-table">' +
           '<thead>' + thead + '</thead>' +
           '<tbody>' + tbody + '</tbody>' +
           '</table>';
  }

  /**
   * Extract the first `ora-visual` fenced JSON block from a chat-message text
   * payload. Returns the parsed object or null. Kept here so renderSpec()
   * can accept either an already-parsed envelope or a raw bridge string.
   */
  function _extractOraVisualBlock(text) {
    if (typeof text !== 'string' || text.length === 0) return null;
    var re = /```ora-visual\s*\n([\s\S]*?)```/g;
    var m, last = null;
    while ((m = re.exec(text)) !== null) last = m[1];
    if (!last) return null;
    try { return JSON.parse(last); } catch (e) { return null; }
  }

  // ── VisualPanel class ─────────────────────────────────────────────────────

  // ── WP-3.1 constants ──────────────────────────────────────────────────────

  // Shape tool types. 'select' and 'delete'/'undo'/'redo'/'clear-user-input'
  // are commands, not shape types.
  var SHAPE_TOOLS = { rect: 1, ellipse: 1, diamond: 1, line: 1, arrow: 1, text: 1 };

  // WP-5.1 — annotation tool types. Each is a mode that overrides the
  // stage click pattern. 'select' remains the universal selection tool.
  var ANNOTATION_TOOLS = {
    callout: 1, highlight: 1, strikethrough: 1, sticky: 1, pen: 1,
  };

  // Auto-hide delay for inline annotation hints (e.g. "Highlight targets
  // must be on a diagram element."). Short enough to feel ephemeral, long
  // enough to read.
  var ANNOTATION_HINT_AUTOHIDE_MS = 3000;

  // Snap threshold (px) for line/arrow endpoint anchoring onto existing
  // user shapes. Chosen to match typical pointer precision on trackpads
  // without requiring unnatural user accuracy.
  var CONN_SNAP_PX = 10;

  // Minimum rect/ellipse/diamond size — rejects accidental sub-pixel drags.
  var MIN_SHAPE_PX = 20;

  // Undo/redo stack depth cap — bounds memory in long sessions.
  var HISTORY_CAP = 50;

  // ── WP-4.1 constants ──────────────────────────────────────────────────────
  // Max image upload size — configurable. Chosen to align with typical
  // vision-model input limits and avoid memory pressure when the data URL is
  // decoded onto the Konva backgroundLayer.
  var MAX_IMAGE_BYTES = 10 * 1024 * 1024; // 10 MB

  // Accepted image MIME types (used for drag-drop validation).
  var IMAGE_MIME_RE = /^image\//;

  // How long an image-upload error message remains visible (ms). The bar
  // persists until the user takes another action; this autohide is a
  // convenience for recoverable failures like "wrong file type".
  var IMAGE_ERROR_AUTOHIDE_MS = 6000;

  function VisualPanel(el, config) {
    this.el       = el;
    this.config   = config || {};
    this.panelId  = (config && config.id) || 'visual';

    // Konva scene
    this.stage            = null;
    this.backgroundLayer  = null;   // SVG artifact sentinel
    this.annotationLayer  = null;   // WP-2.4 reserved
    this.userInputLayer   = null;   // WP-3 user drawings
    this.selectionLayer   = null;

    // DOM overlay (the actual SVG artifact lives here)
    this._svgHost         = null;
    this._currentEnvelope = null;
    this._ariaDescription = null;   // Olli tree from compileWithNav
    this._selectedNodeId  = null;

    // Canvas-action state machine (WP-2.4)
    this._conversationTurn = 0;    // increments on each onBridgeUpdate with an envelope
    this._hasPriorVisual   = false; // becomes true after first successful replace/update
    this._lastAction       = null; // most recent action applied ("replace"/"update"/"annotate"/"clear")

    // Transform state (tracks wheel zoom + drag pan)
    this._transform = { x: 0, y: 0, scale: 1 };

    // WP-3.1 — drawing/tool state
    this._activeTool        = 'select';     // default
    this._shapeCounter      = 0;            // monotonic id source
    this._history           = [];           // action frames: {undoFn, redoFn, label}
    this._historyCursor     = 0;            // next-write index (== length when at tip)
    this._drawContext       = null;         // in-flight draw: {type, start, preview}
    this._selectedShapeIds  = [];           // currently selected user-shape ids
    this._textInputEl       = null;         // inline <input> for text tool
    this._suppressHistory   = false;        // true during undo/redo replays

    // WP-5.1 — user annotation authoring state
    this._userAnnotCounter  = 0;            // monotonic source for userAnnotationId
    this._selectedAnnotIds  = [];           // currently selected user-annotation ids
    this._annotInputEl      = null;         // inline <input> for callout/sticky text
    this._annotHintEl       = null;         // inline hint surface
    this._annotHintTimeout  = null;
    this._penContext        = null;         // in-flight pen stroke

    // WP-4.1 — image upload state
    // `_pendingImage` is the contract read by chat-panel.js at send time.
    // Shape: { blob: File|Blob, name: string, type: string, dataUrl: string }
    // or null when no image is attached. chat-panel reads `.blob` and `.name`.
    this._pendingImage        = null;
    this._backgroundImageNode = null;   // Konva.Image currently on backgroundLayer
    this._imageErrorTimeout   = null;
    this._imageIndicatorOpen  = false;  // whether the remove button is visible

    // Event listener refs for destroy()
    this._onKeyDown       = null;
    this._onWindowResize  = null;
    this._onToolbarClick  = null;
    this._onDragOver      = null;
    this._onDragLeave     = null;
    this._onDrop          = null;
    this._onFileInputChange   = null;
    this._onCameraInputChange = null;
    this._onImageIndicatorClick = null;
    this._destroyed       = false;
  }

  // ── init / destroy ────────────────────────────────────────────────────────

  VisualPanel.prototype.init = function () {
    var id = this.panelId;
    this.el.classList.add('visual-panel');
    this.el.setAttribute('tabindex', '0');
    this.el.setAttribute('role', 'application');
    this.el.setAttribute('aria-label', 'Visual canvas');

    // WP-4.1 — camera capture is included in the toolbar when the browser is
    // mobile (UA test). Desktop browsers get the file-picker only. The
    // `capture="environment"` attribute on the hidden camera input steers
    // mobile browsers to open the rear camera; it is ignored on desktop.
    var ua = (typeof navigator !== 'undefined' && navigator.userAgent) ? navigator.userAgent : '';
    var isMobile = /Mobi/i.test(ua);
    var cameraBtnHtml = isMobile
      ? '<button class="vp-tool-btn" data-tool="camera"   aria-label="Camera capture" title="Camera capture">\u25A3</button>'
      : '';
    var cameraInputHtml = isMobile
      ? '<input type="file" class="vp-hidden-file" id="vp-camera-input-' + id + '" accept="image/*" capture="environment" hidden>'
      : '';

    this.el.innerHTML =
      '<div class="visual-panel__toolbar" id="vp-toolbar-' + id + '" role="toolbar" aria-label="Drawing tools">' +
        '<button class="vp-tool-btn" data-tool="select"   aria-pressed="true"  aria-label="Select (S)"   title="Select (S)">\u2316</button>' +
        '<button class="vp-tool-btn" data-tool="rect"     aria-pressed="false" aria-label="Rectangle (R)" title="Rectangle (R)">\u25AD</button>' +
        '<button class="vp-tool-btn" data-tool="ellipse"  aria-pressed="false" aria-label="Ellipse (E)"   title="Ellipse (E)">\u25EF</button>' +
        '<button class="vp-tool-btn" data-tool="diamond"  aria-pressed="false" aria-label="Diamond (D)"   title="Diamond (D)">\u25C7</button>' +
        '<button class="vp-tool-btn" data-tool="line"     aria-pressed="false" aria-label="Line (L)"      title="Line (L)">\u2500</button>' +
        '<button class="vp-tool-btn" data-tool="arrow"    aria-pressed="false" aria-label="Arrow (A)"     title="Arrow (A)">\u2192</button>' +
        '<button class="vp-tool-btn" data-tool="text"     aria-pressed="false" aria-label="Text (T)"      title="Text (T)">T</button>' +
        '<span class="vp-tool-divider" aria-hidden="true"></span>' +
        '<button class="vp-tool-btn" data-tool="callout"       aria-pressed="false" aria-label="Callout (C)"        title="Callout (C)">\u{1F4AC}</button>' +
        '<button class="vp-tool-btn" data-tool="highlight"     aria-pressed="false" aria-label="Highlight (H)"      title="Highlight (H)">\u25A2</button>' +
        '<button class="vp-tool-btn" data-tool="strikethrough" aria-pressed="false" aria-label="Strikethrough (X)"  title="Strikethrough (X)">\u2571</button>' +
        '<button class="vp-tool-btn" data-tool="sticky"        aria-pressed="false" aria-label="Sticky note (N)"    title="Sticky note (N)">\u{1F5D2}</button>' +
        '<button class="vp-tool-btn" data-tool="pen"           aria-pressed="false" aria-label="Pen (P)"            title="Pen (P)">\u270E</button>' +
        '<span class="vp-tool-divider" aria-hidden="true"></span>' +
        '<button class="vp-tool-btn" data-tool="delete"   aria-label="Delete selected (Del)" title="Delete selected (Del)">\u2716</button>' +
        '<button class="vp-tool-btn" data-tool="undo"     aria-label="Undo (Ctrl+Z)"         title="Undo (Ctrl+Z)">\u21B6</button>' +
        '<button class="vp-tool-btn" data-tool="redo"     aria-label="Redo (Ctrl+Shift+Z)"    title="Redo (Ctrl+Shift+Z)">\u21B7</button>' +
        '<button class="vp-tool-btn" data-tool="clear-user-input" aria-label="Clear user drawings" title="Clear user drawings">\u2327</button>' +
        '<span class="vp-tool-divider" aria-hidden="true"></span>' +
        '<button class="vp-tool-btn" data-tool="upload-image" aria-label="Upload image" title="Upload image">\u{1F4C4}</button>' +
        cameraBtnHtml +
        '<span class="vp-tool-spacer"></span>' +
        '<button class="vp-tool-btn" data-tool="reset"    aria-label="Reset view"             title="Reset view">\u27F2</button>' +
      '</div>' +
      '<input type="file" class="vp-hidden-file" id="vp-file-input-' + id + '" accept="image/*" hidden>' +
      cameraInputHtml +
      '<div class="visual-panel__viewport" id="vp-viewport-' + id + '">' +
        '<div class="visual-panel__svg-host" id="vp-svg-' + id + '"></div>' +
        '<div class="visual-panel__konva" id="vp-konva-' + id + '"></div>' +
        '<div class="visual-panel__drop-hint" id="vp-drop-hint-' + id + '" aria-hidden="true">Drop image to attach</div>' +
      '</div>' +
      '<div class="visual-panel__errorbar" id="vp-errorbar-' + id + '" hidden></div>' +
      '<div class="visual-panel__zoom-indicator" id="vp-zoom-' + id + '" aria-hidden="true">100%</div>' +
      '<div class="visual-panel__annotation-hint" id="vp-annot-hint-' + id + '" role="status" aria-live="polite" hidden></div>' +
      '<div class="visual-panel__image-indicator" id="vp-image-indicator-' + id + '" hidden>' +
        '<span class="vp-image-thumb-wrap" aria-hidden="true"></span>' +
        '<span class="vp-image-label"></span>' +
        '<button type="button" class="vp-image-remove" aria-label="Remove image">\u00D7</button>' +
      '</div>' +
      '<div class="visual-panel__fallback" id="vp-fallback-' + id + '" hidden></div>';

    this._toolbarEl   = this.el.querySelector('#vp-toolbar-' + id);
    this._viewportEl  = this.el.querySelector('#vp-viewport-' + id);
    this._svgHost     = this.el.querySelector('#vp-svg-' + id);
    this._konvaEl     = this.el.querySelector('#vp-konva-' + id);
    this._errorBar    = this.el.querySelector('#vp-errorbar-' + id);
    this._zoomInd     = this.el.querySelector('#vp-zoom-' + id);
    this._fallbackEl  = this.el.querySelector('#vp-fallback-' + id);
    this._annotHintEl = this.el.querySelector('#vp-annot-hint-' + id);

    // WP-4.1 — image upload hooks
    this._fileInputEl    = this.el.querySelector('#vp-file-input-' + id);
    this._cameraInputEl  = this.el.querySelector('#vp-camera-input-' + id);
    this._dropHintEl     = this.el.querySelector('#vp-drop-hint-' + id);
    this._imageIndicator = this.el.querySelector('#vp-image-indicator-' + id);

    // Wire toolbar (event delegation on the toolbar root — one listener)
    var self = this;
    this._onToolbarClick = function (e) {
      var btn = e.target.closest && e.target.closest('.vp-tool-btn');
      if (!btn || !self._toolbarEl.contains(btn)) return;
      var tool = btn.dataset.tool;
      if (!tool) return;
      self._handleToolbarAction(tool);
    };
    this._toolbarEl.addEventListener('click', this._onToolbarClick);

    this._initStage();
    this._wireKeyboard();
    this._wireMouse();
    this._wireDrawing();
    this._wireResize();
    this._wireImageUpload();   // WP-4.1
    this._applyCursor();

    // Optional: auto-render an initial_spec from config.
    if (this.config.initial_spec) {
      try {
        var env = typeof this.config.initial_spec === 'string'
          ? JSON.parse(this.config.initial_spec)
          : this.config.initial_spec;
        this.renderSpec(env);
      } catch (e) { /* silent — bad config shouldn't break init */ }
    }
  };

  VisualPanel.prototype.destroy = function () {
    this._destroyed = true;
    if (this._onKeyDown) this.el.removeEventListener('keydown', this._onKeyDown);
    if (this._onWindowResize) window.removeEventListener('resize', this._onWindowResize);
    if (this._onToolbarClick && this._toolbarEl) {
      this._toolbarEl.removeEventListener('click', this._onToolbarClick);
    }
    // WP-4.1 — tear down upload listeners
    if (this._onDragOver && this.el)    this.el.removeEventListener('dragover',  this._onDragOver);
    if (this._onDragLeave && this.el)   this.el.removeEventListener('dragleave', this._onDragLeave);
    if (this._onDrop && this.el)        this.el.removeEventListener('drop',      this._onDrop);
    if (this._onFileInputChange && this._fileInputEl) {
      this._fileInputEl.removeEventListener('change', this._onFileInputChange);
    }
    if (this._onCameraInputChange && this._cameraInputEl) {
      this._cameraInputEl.removeEventListener('change', this._onCameraInputChange);
    }
    if (this._onImageIndicatorClick && this._imageIndicator) {
      this._imageIndicator.removeEventListener('click', this._onImageIndicatorClick);
    }
    if (this._imageErrorTimeout) {
      try { clearTimeout(this._imageErrorTimeout); } catch (e) { /* ignore */ }
      this._imageErrorTimeout = null;
    }
    // WP-4.4 — tear down overlay listener
    if (this._onFallbackAction && this._fallbackActionsEl) {
      this._fallbackActionsEl.removeEventListener('click', this._onFallbackAction);
    }

    if (this._textInputEl && this._textInputEl.parentNode) {
      this._textInputEl.parentNode.removeChild(this._textInputEl);
    }
    this._textInputEl = null;

    // WP-5.1 — tear down annotation authoring state
    if (this._annotInputEl && this._annotInputEl.parentNode) {
      try { this._annotInputEl.parentNode.removeChild(this._annotInputEl); }
      catch (e) { /* ignore */ }
    }
    this._annotInputEl = null;
    if (this._annotHintTimeout) {
      try { clearTimeout(this._annotHintTimeout); } catch (e) { /* ignore */ }
      this._annotHintTimeout = null;
    }
    this._penContext = null;
    if (this.stage) {
      try { this.stage.destroy(); } catch (e) { /* ignore */ }
    }
    this.stage = null;
    this.backgroundLayer = null;
    this.annotationLayer = null;
    this.userInputLayer = null;
    this.selectionLayer = null;
    this._pendingImage = null;
    this._backgroundImageNode = null;
  };

  // ── Bridge ────────────────────────────────────────────────────────────────

  VisualPanel.prototype.onBridgeUpdate = function (state) {
    if (!state || typeof state !== 'object') return;
    // WP-5.3 client hydration — TODO (deferred).
    // On fresh page-load, the server's conversation.json may carry a persisted
    // spatial_representation from a prior user turn. Rendering that back onto
    // backgroundLayer here would give the user continuity on reload. Deferred
    // for now because:
    //   (1) The continuity-critical surface is the ANALYTICAL model's view of
    //       prior state; WP-5.3 threads that through build_system_prompt_for_gear
    //       server-side, so reasoning is already preserved.
    //   (2) When the model emits an annotate/replace envelope post-reload, the
    //       existing canvas_action state machine renders the response onto a
    //       clean canvas — the user sees Ora's updated view immediately.
    //   (3) Rehydrating userInputLayer from a persisted spatial_representation
    //       requires an inverse of canvas-serializer.js (JSON → Konva shapes).
    //       That's a non-trivial module to author; the spec asks us to avoid
    //       touching canvas-serializer.js.
    // Future hydration would live here: read state.persisted_spatial and call
    // a new _hydrateFromSpatialRepresentation(state.persisted_spatial) method.
    var blocks = state.ora_visual_blocks;
    if (!Array.isArray(blocks) || blocks.length === 0) return;

    var block = blocks[blocks.length - 1];
    var envelope = null;
    if (block && block.envelope) envelope = block.envelope;
    else if (block && block.raw_json) {
      try { envelope = JSON.parse(block.raw_json); } catch (e) { envelope = null; }
    } else if (typeof block === 'string') {
      envelope = _extractOraVisualBlock(block);
    }

    if (!envelope) return;

    // Bump the conversation turn counter BEFORE dispatching so the state
    // machine sees the new turn. _applyCanvasAction also uses this to
    // decide whether to treat an omitted canvas_action as replace or update.
    this._conversationTurn += 1;

    return this._applyCanvasAction(envelope, envelope.canvas_action);
  };

  // ── Public/internal: canvas-action state machine (WP-2.4) ─────────────────

  /**
   * Apply a canvas_action to the stage per Protocol §canvas_action.
   *
   * Resolution:
   *   - explicit action: honor it verbatim ("replace" | "update" | "annotate" | "clear")
   *   - omitted action: replace on first-ever visual, update on subsequent
   *
   * INVARIANT: update + annotate never touch userInputLayer. User drawings
   * survive every Ora follow-up unless the envelope explicitly says replace
   * or clear.
   *
   * Returns the promise produced by renderSpec() for replace/update paths,
   * or Promise.resolve() for annotate/clear (which are synchronous).
   */
  VisualPanel.prototype._applyCanvasAction = function (envelope, explicitAction) {
    if (this._destroyed) return Promise.resolve();
    if (!envelope || typeof envelope !== 'object') return Promise.resolve();

    var action = explicitAction;
    if (!action) {
      action = this._hasPriorVisual ? 'update' : 'replace';
    }
    // Guard against bogus values surfaced past the schema (defense in depth).
    if (action !== 'replace' && action !== 'update' && action !== 'annotate' && action !== 'clear') {
      action = this._hasPriorVisual ? 'update' : 'replace';
    }
    this._lastAction = action;

    if (action === 'clear') {
      this._doClear();
      return Promise.resolve();
    }
    if (action === 'annotate') {
      this._doAnnotate(envelope);
      return Promise.resolve();
    }
    if (action === 'replace') {
      this._doReplacePrep();
      var self0 = this;
      return this.renderSpec(envelope).then(function (r) {
        self0._hasPriorVisual = true;
        return r;
      });
    }
    // action === 'update'
    this._doUpdatePrep();
    var self = this;
    return this.renderSpec(envelope).then(function (r) {
      self._hasPriorVisual = true;
      return r;
    });
  };

  /**
   * replace: empty all four layers (+ DOM overlay + selection + fallback).
   * Used BEFORE renderSpec() so that renderSpec() lands the new artifact
   * onto a fresh stage. userInputLayer + annotationLayer are wiped.
   */
  VisualPanel.prototype._doReplacePrep = function () {
    if (this._svgHost) this._svgHost.innerHTML = '';
    if (this.backgroundLayer) {
      try {
        this.backgroundLayer.destroyChildren();
        if (typeof Konva !== 'undefined') {
          this._bgSentinel = new Konva.Group({ name: 'svg-sentinel' });
          this.backgroundLayer.add(this._bgSentinel);
        }
        this.backgroundLayer.draw();
      } catch (e) { /* ignore */ }
    }
    if (this.annotationLayer) { this.annotationLayer.destroyChildren(); this.annotationLayer.draw(); }
    if (this.userInputLayer)  { this.userInputLayer.destroyChildren();  this.userInputLayer.draw(); }
    if (this.selectionLayer)  { this.selectionLayer.destroyChildren();  this.selectionLayer.draw(); }
    this._selectedNodeId = null;
    if (this._fallbackEl) { this._fallbackEl.hidden = true; this._fallbackEl.innerHTML = ''; }
    if (this._errorBar) { this._errorBar.hidden = true; this._errorBar.innerHTML = ''; }
  };

  /**
   * update: empty backgroundLayer + selectionLayer only. annotationLayer
   * + userInputLayer are preserved. Used BEFORE renderSpec() so the new
   * artifact replaces the old background without disturbing user drawings
   * or prior Ora overlays.
   */
  VisualPanel.prototype._doUpdatePrep = function () {
    if (this._svgHost) this._svgHost.innerHTML = '';
    if (this.backgroundLayer) {
      try {
        this.backgroundLayer.destroyChildren();
        if (typeof Konva !== 'undefined') {
          this._bgSentinel = new Konva.Group({ name: 'svg-sentinel' });
          this.backgroundLayer.add(this._bgSentinel);
        }
        this.backgroundLayer.draw();
      } catch (e) { /* ignore */ }
    }
    if (this.selectionLayer) { this.selectionLayer.destroyChildren(); this.selectionLayer.draw(); }
    this._selectedNodeId = null;
    if (this._fallbackEl) { this._fallbackEl.hidden = true; this._fallbackEl.innerHTML = ''; }
    if (this._errorBar) { this._errorBar.hidden = true; this._errorBar.innerHTML = ''; }
    // annotationLayer + userInputLayer explicitly untouched.
  };

  /**
   * annotate: do not touch backgroundLayer. Read envelope.annotations (or
   * envelope.spec.annotations) and render callout/highlight overlays onto
   * annotationLayer. If no annotations content is present, emit
   * W_ANNOTATE_NO_CONTENT and no-op. arrow + badge emit
   * W_ANNOTATION_KIND_DEFERRED (WP-5.1 scope).
   */
  VisualPanel.prototype._doAnnotate = function (envelope) {
    var annots = null;
    if (envelope && Array.isArray(envelope.annotations)) {
      annots = envelope.annotations;
    } else if (envelope && envelope.spec && Array.isArray(envelope.spec.annotations)) {
      annots = envelope.spec.annotations;
    }
    if (!annots || annots.length === 0) {
      this._annotationWarnings = [{
        code: 'W_ANNOTATE_NO_CONTENT',
        severity: 'warning',
        message: 'canvas_action="annotate" but envelope has no annotations array.',
      }];
      return;
    }

    var warnings = [];
    var layer = this.annotationLayer;
    if (!layer) return;

    for (var i = 0; i < annots.length; i++) {
      var a = annots[i];
      if (!a || typeof a !== 'object') continue;
      if (a.kind === 'callout') {
        this._renderCallout(a, warnings);
      } else if (a.kind === 'highlight') {
        this._renderHighlight(a, warnings);
      } else if (a.kind === 'arrow' || a.kind === 'badge') {
        warnings.push({
          code: 'W_ANNOTATION_KIND_DEFERRED',
          severity: 'warning',
          message: 'Annotation kind "' + a.kind + '" deferred to WP-5.1.',
          path: 'annotations[' + i + '].kind',
        });
      } else {
        warnings.push({
          code: 'W_ANNOTATION_KIND_DEFERRED',
          severity: 'warning',
          message: 'Unknown annotation kind "' + a.kind + '".',
          path: 'annotations[' + i + '].kind',
        });
      }
    }
    layer.draw();
    this._annotationWarnings = warnings;
  };

  /**
   * clear: empty ALL four layers + reset state. Emits no render.
   */
  VisualPanel.prototype._doClear = function () {
    if (this._svgHost) this._svgHost.innerHTML = '';
    if (this.backgroundLayer) {
      try {
        this.backgroundLayer.destroyChildren();
        if (typeof Konva !== 'undefined') {
          this._bgSentinel = new Konva.Group({ name: 'svg-sentinel' });
          this.backgroundLayer.add(this._bgSentinel);
        }
        this.backgroundLayer.draw();
      } catch (e) { /* ignore */ }
    }
    if (this.annotationLayer) { this.annotationLayer.destroyChildren(); this.annotationLayer.draw(); }
    if (this.userInputLayer)  { this.userInputLayer.destroyChildren();  this.userInputLayer.draw(); }
    if (this.selectionLayer)  { this.selectionLayer.destroyChildren();  this.selectionLayer.draw(); }
    this._currentEnvelope = null;
    this._ariaDescription = null;
    this._selectedNodeId  = null;
    this._hasPriorVisual  = false;
    if (this._fallbackEl) { this._fallbackEl.hidden = true; this._fallbackEl.innerHTML = ''; }
    if (this._errorBar) { this._errorBar.hidden = true; this._errorBar.innerHTML = ''; }
  };

  /**
   * Compute the viewport-relative bounding box of an SVG target by walking
   * from _svgHost origin. Returns {x, y, width, height} in stage coords
   * (i.e. already accounting for this._transform). Returns null when the
   * target cannot be located.
   */
  VisualPanel.prototype._computeTargetBox = function (targetId) {
    if (!this._svgHost || !targetId) return null;
    var node = this._svgHost.querySelector('[id="' + (window.CSS && CSS.escape ? CSS.escape(targetId) : targetId) + '"]');
    if (!node) return null;
    var bbox = null;
    try { bbox = node.getBBox ? node.getBBox() : null; } catch (e) { bbox = null; }
    if (!bbox) return null;
    var t = this._transform || { x: 0, y: 0, scale: 1 };
    return {
      x: (bbox.x * t.scale) + t.x,
      y: (bbox.y * t.scale) + t.y,
      width:  bbox.width  * t.scale,
      height: bbox.height * t.scale,
    };
  };

  /**
   * Callout: small label bubble anchored near the target element. The
   * bubble consists of a rounded rectangle + text; positioned just above
   * the target bbox's top-right corner by default.
   */
  VisualPanel.prototype._renderCallout = function (annotation, warnings) {
    if (typeof Konva === 'undefined' || !this.annotationLayer) return;
    var box = this._computeTargetBox(annotation.target_id);
    if (!box) {
      warnings.push({
        code: 'W_ANNOTATION_TARGET_MISSING',
        severity: 'warning',
        message: 'Callout target "' + annotation.target_id + '" not found.',
      });
      return;
    }
    var text = annotation.text || '';
    var padding = 6;
    var approxW = Math.max(40, text.length * 7 + padding * 2);
    var approxH = 22;
    var x = box.x + box.width + 8;
    var y = box.y - approxH - 4;
    if (y < 0) y = box.y + box.height + 4;

    var group = new Konva.Group({ name: 'vp-callout-' + annotation.target_id });
    group.add(new Konva.Rect({
      x: x, y: y, width: approxW, height: approxH,
      fill: annotation.color || '#FFF4A3',
      stroke: '#333', strokeWidth: 1,
      cornerRadius: 4,
    }));
    group.add(new Konva.Text({
      x: x + padding, y: y + padding,
      text: text,
      fontSize: 11,
      fill: '#000',
    }));
    this.annotationLayer.add(group);
  };

  /**
   * Highlight: animated pulsing ring around the target element. Uses a
   * Konva.Animation to drive opacity oscillation on a stroked rectangle.
   */
  VisualPanel.prototype._renderHighlight = function (annotation, warnings) {
    if (typeof Konva === 'undefined' || !this.annotationLayer) return;
    var box = this._computeTargetBox(annotation.target_id);
    if (!box) {
      warnings.push({
        code: 'W_ANNOTATION_TARGET_MISSING',
        severity: 'warning',
        message: 'Highlight target "' + annotation.target_id + '" not found.',
      });
      return;
    }
    var pad = 4;
    var ring = new Konva.Rect({
      x: box.x - pad, y: box.y - pad,
      width: box.width + pad * 2,
      height: box.height + pad * 2,
      stroke: annotation.color || '#FF5722',
      strokeWidth: 3,
      dash: [6, 4],
      listening: false,
      opacity: 0.8,
      name: 'vp-highlight-' + annotation.target_id,
    });
    this.annotationLayer.add(ring);

    // Subtle pulse via Konva.Animation. In jsdom this is effectively a no-op
    // (no RAF-driven redraw), so the static ring is what tests see.
    try {
      var anim = new Konva.Animation(function (frame) {
        var t = (frame && frame.time) || 0;
        ring.opacity(0.5 + 0.4 * Math.abs(Math.sin(t / 350)));
      }, this.annotationLayer);
      ring._vpAnimation = anim;
      if (anim.start) anim.start();
    } catch (e) { /* animations disabled (jsdom) — static ring is fine */ }
  };

  // ── Public: renderSpec ────────────────────────────────────────────────────

  VisualPanel.prototype.renderSpec = function (envelope) {
    if (this._destroyed) return Promise.resolve();
    if (!envelope || typeof envelope !== 'object') {
      this._showFallback(null, [{ code: 'E_NO_ENVELOPE', message: 'No envelope provided.' }]);
      return Promise.resolve();
    }

    var self = this;
    var compilerApi = (window.OraVisualCompiler && window.OraVisualCompiler.compileWithNav)
      ? window.OraVisualCompiler
      : null;

    if (!compilerApi) {
      this._showFallback(envelope, [{
        code: 'E_COMPILER_UNAVAILABLE',
        message: 'Ora visual compiler not loaded.',
      }]);
      return Promise.resolve();
    }

    var result;
    try {
      result = compilerApi.compileWithNav(envelope);
    } catch (e) {
      this._showFallback(envelope, [{
        code: 'E_COMPILER_THREW',
        message: 'Compiler threw: ' + (e && e.message ? e.message : String(e)),
      }]);
      return Promise.resolve();
    }

    // compileWithNav may return a Promise (Vega-Lite, Mermaid) or a plain object.
    var thenable = (result && typeof result.then === 'function') ? result : Promise.resolve(result);
    return thenable.then(function (r) {
      if (self._destroyed) return;
      if (!r) {
        self._showFallback(envelope, [{ code: 'E_COMPILER_NULL', message: 'Compiler returned null.' }]);
        return;
      }
      if (r.errors && r.errors.length > 0) {
        self._showFallback(envelope, r.errors);
        return;
      }
      if (!r.svg || r.svg.length === 0) {
        self._showFallback(envelope, [{ code: 'E_EMPTY_SVG', message: 'Compiler produced empty SVG.' }]);
        return;
      }
      self._installSvg(r.svg, envelope, r.ariaDescription);
    }, function (err) {
      self._showFallback(envelope, [{
        code: 'E_COMPILER_REJECTED',
        message: 'Compile rejected: ' + (err && err.message ? err.message : String(err)),
      }]);
    });
  };

  // ── Public: clearArtifact ─────────────────────────────────────────────────

  VisualPanel.prototype.clearArtifact = function () {
    this._currentEnvelope = null;
    this._ariaDescription = null;
    this._selectedNodeId  = null;
    if (this._svgHost) this._svgHost.innerHTML = '';
    if (this.selectionLayer) { this.selectionLayer.destroyChildren(); this.selectionLayer.draw(); }
    if (this._fallbackEl) { this._fallbackEl.hidden = true; this._fallbackEl.innerHTML = ''; }
    if (this._errorBar) { this._errorBar.hidden = true; this._errorBar.innerHTML = ''; }
    // userInputLayer and annotationLayer are explicitly preserved.
  };

  // ── Public: resetView ─────────────────────────────────────────────────────

  VisualPanel.prototype.resetView = function () {
    this._transform = { x: 0, y: 0, scale: 1 };
    this._applyTransform();
  };

  // ── Internal: stage init ──────────────────────────────────────────────────

  VisualPanel.prototype._initStage = function () {
    if (typeof Konva === 'undefined') {
      // Konva not available — display a hard error (but don't throw).
      this._showErrorBar('Konva not loaded — canvas interactions disabled.');
      return;
    }
    var w = Math.max(300, this._viewportEl.clientWidth || 600);
    var h = Math.max(200, this._viewportEl.clientHeight || 400);

    this.stage = new Konva.Stage({
      container: this._konvaEl,
      width:  w,
      height: h,
    });

    this.backgroundLayer = new Konva.Layer({ listening: false });
    this.annotationLayer = new Konva.Layer();
    this.userInputLayer  = new Konva.Layer();
    this.selectionLayer  = new Konva.Layer({ listening: false });

    // Sentinel group on background so the layer has a Konva child. This
    // group does NOT render the SVG (the SVG is in the DOM overlay); it
    // exists so pan/zoom transform tracking can be applied uniformly.
    this._bgSentinel = new Konva.Group({ name: 'svg-sentinel' });
    this.backgroundLayer.add(this._bgSentinel);

    this.stage.add(this.backgroundLayer);
    this.stage.add(this.annotationLayer);
    this.stage.add(this.userInputLayer);
    this.stage.add(this.selectionLayer);
  };

  // ── Internal: install SVG into DOM overlay ────────────────────────────────

  VisualPanel.prototype._installSvg = function (svgString, envelope, ariaDescription) {
    // Clear previous artifact + error state
    this._svgHost.innerHTML = '';
    if (this._fallbackEl) { this._fallbackEl.hidden = true; this._fallbackEl.innerHTML = ''; }
    if (this._errorBar) { this._errorBar.hidden = true; this._errorBar.innerHTML = ''; }

    // Parse and inject. Using DOMParser ensures namespace correctness.
    try {
      var parser = new DOMParser();
      var doc = parser.parseFromString(svgString, 'image/svg+xml');
      var svgEl = doc.documentElement;
      if (!svgEl || svgEl.nodeName.toLowerCase() !== 'svg') {
        // Fall back: direct innerHTML (browsers accept <svg> in HTML5).
        this._svgHost.innerHTML = svgString;
      } else {
        this._svgHost.appendChild(document.importNode(svgEl, true));
      }
    } catch (e) {
      this._svgHost.innerHTML = svgString;
    }

    this._currentEnvelope = envelope;
    this._ariaDescription = ariaDescription || null;
    this._selectedNodeId  = null;

    // Wire click + hover on semantic elements.
    this._wireSemanticInteractions();

    // Ensure root svg has tabindex so focus can land on it.
    var rootSvg = this._svgHost.querySelector('svg');
    if (rootSvg) {
      if (!rootSvg.hasAttribute('tabindex')) rootSvg.setAttribute('tabindex', '0');
      // Update aria-activedescendant on panel root
      if (ariaDescription && ariaDescription.root_id) {
        this.el.setAttribute('aria-activedescendant', ariaDescription.root_id);
      }
    }

    this._applyTransform();
  };

  // ── Internal: fallback rendering (Protocol §8.5) ──────────────────────────

  VisualPanel.prototype._showFallback = function (envelope, errors) {
    // Clear background
    if (this._svgHost) this._svgHost.innerHTML = '';

    // Show error bar
    this._showErrorBar(this._summarizeErrors(errors));

    if (!this._fallbackEl) return;
    var html = '';
    var sd = envelope && envelope.semantic_description;
    if (sd && sd.data_table_fallback) {
      html += '<div class="visual-panel__fallback-title">Data table fallback</div>';
      html += _renderFallbackTable(sd.data_table_fallback);
    } else if (sd && sd.short_alt) {
      html += '<div class="visual-panel__fallback-title">Description</div>';
      html += '<div class="visual-panel__fallback-prose">' + _esc(sd.short_alt) + '</div>';
    } else {
      html += '<div class="visual-panel__fallback-title">Visual could not be rendered</div>';
      html += '<div class="visual-panel__fallback-prose">No fallback data available.</div>';
    }
    this._fallbackEl.innerHTML = html;
    this._fallbackEl.hidden = false;
  };

  VisualPanel.prototype._summarizeErrors = function (errors) {
    if (!errors || errors.length === 0) return 'Unknown error.';
    return errors.map(function (e) {
      var code = e.code ? '[' + e.code + '] ' : '';
      return code + (e.message || 'unspecified');
    }).join('; ');
  };

  VisualPanel.prototype._showErrorBar = function (msg) {
    if (!this._errorBar) return;
    this._errorBar.textContent = msg;
    this._errorBar.hidden = false;
  };

  // ── Internal: semantic interactions (hover/click) ─────────────────────────

  VisualPanel.prototype._wireSemanticInteractions = function () {
    var self = this;
    // Delegate rather than per-element (SVG mutations during animations etc.)
    if (this._semanticClickHandler) {
      this._svgHost.removeEventListener('click', this._semanticClickHandler);
    }
    if (this._semanticHoverHandler) {
      this._svgHost.removeEventListener('mouseover', this._semanticHoverHandler);
    }

    this._semanticClickHandler = function (e) {
      var target = e.target;
      // Walk up to find the nearest semantic element with an id.
      var node = target;
      while (node && node !== self._svgHost) {
        if (node.nodeType === 1 && node.hasAttribute && node.hasAttribute('id')) {
          var cls = node.getAttribute('class') || '';
          var role = node.getAttribute('role') || '';
          if (/ora-visual__/.test(cls) ||
              role === 'graphics-symbol' ||
              role === 'graphics-datapoint') {
            self._selectElement(node);
            return;
          }
        }
        node = node.parentNode;
      }
    };

    this._semanticHoverHandler = function (e) {
      var target = e.target;
      if (!target || target.nodeType !== 1) return;
      var label = (target.getAttribute && target.getAttribute('aria-label')) || '';
      if (!label && target.querySelector) {
        var titleEl = target.querySelector('title');
        if (titleEl) label = titleEl.textContent || '';
      }
      if (label) target.setAttribute('data-tooltip', label);
    };

    this._svgHost.addEventListener('click', this._semanticClickHandler);
    this._svgHost.addEventListener('mouseover', this._semanticHoverHandler);
  };

  VisualPanel.prototype._selectElement = function (node) {
    if (!node) return;
    var id = node.getAttribute('id');
    this._selectedNodeId = id;

    // Clear previous selection visuals
    if (this.selectionLayer) {
      this.selectionLayer.destroyChildren();
    }

    // Draw a highlight box in selectionLayer, matching the element's BBox
    // (best-effort; jsdom returns our mocked 6/14 from getBBox but real
    // browsers return actual geometry).
    var bbox = null;
    try { bbox = node.getBBox ? node.getBBox() : null; } catch (e) { bbox = null; }

    if (bbox && this.selectionLayer && typeof Konva !== 'undefined') {
      // Map SVG-local coords to stage coords. Our DOM overlay uses the same
      // transform as backgroundLayer, so we can apply the current transform
      // to the bbox corners. Getting the SVG root position in viewport is
      // handled by CSS transform (mirrored from _transform).
      var rect = new Konva.Rect({
        x: (bbox.x * this._transform.scale) + this._transform.x,
        y: (bbox.y * this._transform.scale) + this._transform.y,
        width:  bbox.width  * this._transform.scale,
        height: bbox.height * this._transform.scale,
        stroke: '#0072B2',
        strokeWidth: 2,
        dash: [6, 4],
        listening: false,
        name: 'vp-selection-' + id,
      });
      this.selectionLayer.add(rect);
      this.selectionLayer.draw();
    }

    // Update aria-activedescendant on panel root
    if (id) this.el.setAttribute('aria-activedescendant', id);

    // Focus the element (only if focus is within the panel already).
    if (node.focus && this.el.contains(document.activeElement)) {
      try { node.focus({ preventScroll: true }); } catch (e) { try { node.focus(); } catch (e2) {} }
    }
  };

  // ── Internal: keyboard nav (Olli-style) ───────────────────────────────────

  VisualPanel.prototype._wireKeyboard = function () {
    var self = this;
    this._onKeyDown = function (e) {
      var key = e.key;

      // ── WP-3.1 shortcuts ──────────────────────────────────────────────
      // Ignore shortcuts when focus is in a text input / textarea / the
      // chat composer / our own inline text-tool input. Shortcuts should
      // never hijack typing in form fields.
      if (!self._isTypingTarget(e.target)) {
        // Tool shortcuts (single-letter, no modifier except delete).
        if (!e.ctrlKey && !e.metaKey && !e.altKey) {
          var toolByKey = {
            's': 'select', 'S': 'select',
            'r': 'rect',   'R': 'rect',
            'e': 'ellipse','E': 'ellipse',
            'd': 'diamond','D': 'diamond',
            'l': 'line',   'L': 'line',
            'a': 'arrow',  'A': 'arrow',
            't': 'text',   'T': 'text',
            // WP-5.1 — annotation tool shortcuts
            'c': 'callout',       'C': 'callout',
            'h': 'highlight',     'H': 'highlight',
            'x': 'strikethrough', 'X': 'strikethrough',
            'n': 'sticky',        'N': 'sticky',
            'p': 'pen',           'P': 'pen',
          };
          if (toolByKey[key]) {
            e.preventDefault();
            self.setActiveTool(toolByKey[key]);
            return;
          }
          if (key === 'Delete' || key === 'Backspace') {
            // Only intercept Backspace when we have a selection — otherwise
            // pass it through so form-element back-nav isn't broken.
            if (self._selectedShapeIds && self._selectedShapeIds.length > 0) {
              e.preventDefault();
              self.deleteSelected();
              return;
            }
            // WP-5.1 — delete selected user annotations.
            if (self._selectedAnnotIds && self._selectedAnnotIds.length > 0) {
              e.preventDefault();
              self.deleteSelectedAnnotations();
              return;
            }
          }
        }
        // Undo / Redo
        if ((e.ctrlKey || e.metaKey) && !e.altKey) {
          if (key === 'z' || key === 'Z') {
            e.preventDefault();
            if (e.shiftKey) self.redo(); else self.undo();
            return;
          }
          if (key === 'y' || key === 'Y') {
            e.preventDefault();
            self.redo();
            return;
          }
        }
      }

      // ── Olli-style nav (unchanged) ───────────────────────────────────
      if (!self._ariaDescription || !Array.isArray(self._ariaDescription.nodes) ||
          self._ariaDescription.nodes.length === 0) {
        return;
      }
      var nodes = self._ariaDescription.nodes;
      var currentId = self._selectedNodeId || self._ariaDescription.root_id;
      var current = nodes.find(function (n) { return n.id === currentId; });

      if (key === 'ArrowDown' || key === 'ArrowRight') {
        e.preventDefault();
        var nextId = self._siblingOrFirstLevel1(current, 1);
        if (nextId) self._focusNavId(nextId);
      } else if (key === 'ArrowUp' || key === 'ArrowLeft') {
        e.preventDefault();
        var prevId = self._siblingOrFirstLevel1(current, -1);
        if (prevId) self._focusNavId(prevId);
      } else if (key === 'Enter' || key === ' ') {
        e.preventDefault();
        if (current && current.children_ids && current.children_ids.length > 0) {
          self._focusNavId(current.children_ids[0]);
        }
      } else if (key === 'Escape') {
        e.preventDefault();
        if (current && current.parent_id) {
          self._focusNavId(current.parent_id);
        } else {
          // Ascend to root: clear selection.
          self._selectedNodeId = null;
          if (self.selectionLayer) { self.selectionLayer.destroyChildren(); self.selectionLayer.draw(); }
          self.el.setAttribute('aria-activedescendant', self._ariaDescription.root_id || '');
        }
      }
    };
    this.el.addEventListener('keydown', this._onKeyDown);
  };

  /**
   * Return true if `target` is a text-entry element where single-letter
   * tool shortcuts should NOT fire. Covers:
   *   - <input type="text|search|email|…">
   *   - <textarea>
   *   - contenteditable elements (chat composer)
   *   - our own inline text-tool <input> (id starts with vp-text-input-)
   */
  VisualPanel.prototype._isTypingTarget = function (target) {
    if (!target || target.nodeType !== 1) return false;
    var tag = (target.tagName || '').toUpperCase();
    if (tag === 'TEXTAREA') return true;
    if (tag === 'INPUT') {
      var type = (target.getAttribute('type') || 'text').toLowerCase();
      // Non-text-like input types (button, checkbox) don't count.
      if (type === 'button' || type === 'checkbox' || type === 'radio' ||
          type === 'submit' || type === 'reset' || type === 'range' ||
          type === 'color' || type === 'file') return false;
      return true;
    }
    if (target.isContentEditable) return true;
    return false;
  };

  /**
   * Find the next/previous sibling at the current level. If current is null
   * (no selection yet), return the first level-1 node (or next/prev by
   * signed direction).
   *
   * direction: 1 for next, -1 for prev
   */
  VisualPanel.prototype._siblingOrFirstLevel1 = function (current, direction) {
    var nodes = this._ariaDescription.nodes;
    // No current: anchor on first level-1 node.
    if (!current) {
      var first = nodes.find(function (n) { return n.level === 1; });
      return first ? first.id : null;
    }
    // Locate siblings: nodes with same parent_id AND same level.
    var siblings = nodes.filter(function (n) {
      return n.parent_id === current.parent_id && n.level === current.level;
    });
    var idx = siblings.findIndex(function (n) { return n.id === current.id; });
    if (idx < 0) return null;
    var nextIdx = idx + direction;
    if (nextIdx < 0 || nextIdx >= siblings.length) return null;  // clamp at ends
    return siblings[nextIdx].id;
  };

  VisualPanel.prototype._focusNavId = function (id) {
    this._selectedNodeId = id;
    this.el.setAttribute('aria-activedescendant', id);
    // Find the DOM node and draw highlight + focus it.
    var node = this._svgHost.querySelector('[id="' + (window.CSS && CSS.escape ? CSS.escape(id) : id) + '"]');
    if (node) this._selectElement(node);
  };

  // ── Internal: mouse (wheel zoom, drag pan) ────────────────────────────────

  VisualPanel.prototype._wireMouse = function () {
    var self = this;
    if (!this.stage) return;

    // Wheel zoom centered on pointer
    this.stage.on('wheel', function (e) {
      var evt = e.evt;
      if (!evt) return;
      evt.preventDefault();
      var scaleBy = 1.1;
      var oldScale = self._transform.scale;
      var pointer = self.stage.getPointerPosition() || { x: 0, y: 0 };
      var mousePoint = {
        x: (pointer.x - self._transform.x) / oldScale,
        y: (pointer.y - self._transform.y) / oldScale,
      };
      var direction = evt.deltaY > 0 ? -1 : 1;
      var newScale = direction > 0 ? oldScale * scaleBy : oldScale / scaleBy;
      // Clamp
      newScale = Math.max(0.1, Math.min(10, newScale));
      self._transform.scale = newScale;
      self._transform.x = pointer.x - mousePoint.x * newScale;
      self._transform.y = pointer.y - mousePoint.y * newScale;
      self._applyTransform();
    });

    // Drag pan on empty space
    var panning = false;
    var panStart = { x: 0, y: 0 };
    var transformStart = { x: 0, y: 0 };

    this.stage.on('mousedown touchstart', function (e) {
      // Only pan when the click wasn't on a Konva listening target.
      if (e.target !== self.stage) {
        var name = e.target.name && e.target.name();
        if (name && name.indexOf('vp-selection-') !== 0) return;
      }
      var p = self.stage.getPointerPosition() || { x: 0, y: 0 };
      panning = true;
      panStart = p;
      transformStart = { x: self._transform.x, y: self._transform.y };
    });

    this.stage.on('mousemove touchmove', function () {
      if (!panning) return;
      var p = self.stage.getPointerPosition() || { x: 0, y: 0 };
      self._transform.x = transformStart.x + (p.x - panStart.x);
      self._transform.y = transformStart.y + (p.y - panStart.y);
      self._applyTransform();
    });

    this.stage.on('mouseup touchend mouseleave', function () {
      panning = false;
    });
  };

  VisualPanel.prototype._applyTransform = function () {
    var t = this._transform;
    // Apply transform to Konva stage (annotation + user input layers move with it)
    if (this.stage) {
      this.stage.position({ x: t.x, y: t.y });
      this.stage.scale({ x: t.scale, y: t.scale });
      this.stage.batchDraw();
    }
    // Mirror to SVG host via CSS transform.
    if (this._svgHost) {
      this._svgHost.style.transformOrigin = '0 0';
      this._svgHost.style.transform = 'translate(' + t.x + 'px, ' + t.y + 'px) scale(' + t.scale + ')';
    }
    if (this._zoomInd) {
      this._zoomInd.textContent = Math.round(t.scale * 100) + '%';
    }
  };

  // ── Internal: resize observer ─────────────────────────────────────────────

  VisualPanel.prototype._wireResize = function () {
    var self = this;
    this._onWindowResize = function () {
      if (!self.stage || !self._viewportEl) return;
      var w = self._viewportEl.clientWidth  || 600;
      var h = self._viewportEl.clientHeight || 400;
      self.stage.width(w);
      self.stage.height(h);
      self.stage.batchDraw();
    };
    window.addEventListener('resize', this._onWindowResize);
  };

  // ══════════════════════════════════════════════════════════════════════════
  // WP-3.1 — Toolbar, drawing tools, selection, undo/redo
  // ══════════════════════════════════════════════════════════════════════════

  /**
   * Toolbar click router. Command tools (delete/undo/redo/clear-user-input/
   * reset) dispatch immediately; shape tools + select toggle the active
   * tool and update ARIA pressed state.
   */
  VisualPanel.prototype._handleToolbarAction = function (tool) {
    if (tool === 'reset')             { this.resetView();              return; }
    if (tool === 'delete')            { this.deleteSelected();         return; }
    if (tool === 'undo')              { this.undo();                   return; }
    if (tool === 'redo')              { this.redo();                   return; }
    if (tool === 'clear-user-input')  { this.clearUserInput();         return; }
    // WP-4.1 — image upload pickers
    if (tool === 'upload-image')      { this._openFilePicker('file');  return; }
    if (tool === 'camera')            { this._openFilePicker('camera');return; }
    // Mode tools: select + every SHAPE_TOOLS + ANNOTATION_TOOLS entry.
    if (tool === 'select' || SHAPE_TOOLS[tool] || ANNOTATION_TOOLS[tool]) {
      this.setActiveTool(tool);
      return;
    }
  };

  /**
   * Set the active drawing tool. Updates `_activeTool`, `aria-pressed` on
   * every toolbar button, and the stage cursor. No-op if the tool is
   * unrecognized.
   */
  VisualPanel.prototype.setActiveTool = function (tool) {
    if (tool !== 'select' && !SHAPE_TOOLS[tool] && !ANNOTATION_TOOLS[tool]) return;
    this._activeTool = tool;
    // Cancel any in-flight draw / text input when the tool changes.
    this._cancelDraw();
    this._dismissTextInput();
    this._dismissAnnotationInput();
    this._cancelPenStroke();
    // Clearing the annotation hint on tool change matches user expectation:
    // the last hint targeted the prior tool and no longer applies.
    this._hideAnnotationHint();
    // Update ARIA pressed on toolbar buttons.
    if (this._toolbarEl) {
      var btns = this._toolbarEl.querySelectorAll('.vp-tool-btn[data-tool]');
      for (var i = 0; i < btns.length; i++) {
        var t = btns[i].dataset.tool;
        if (t === 'select' || SHAPE_TOOLS[t] || ANNOTATION_TOOLS[t]) {
          btns[i].setAttribute('aria-pressed', t === tool ? 'true' : 'false');
        }
      }
    }
    this._applyCursor();
  };

  VisualPanel.prototype.getActiveTool = function () { return this._activeTool; };

  /**
   * Apply a CSS cursor to the stage container that matches the active tool.
   * Uses CSS classes so styling lives in visual-panel.css.
   */
  VisualPanel.prototype._applyCursor = function () {
    if (!this._konvaEl) return;
    this._konvaEl.classList.remove(
      'vp-cursor-select', 'vp-cursor-draw', 'vp-cursor-text',
      'vp-cursor-callout', 'vp-cursor-highlight', 'vp-cursor-strikethrough',
      'vp-cursor-sticky', 'vp-cursor-pen'
    );
    if (this._activeTool === 'select') {
      this._konvaEl.classList.add('vp-cursor-select');
    } else if (this._activeTool === 'text') {
      this._konvaEl.classList.add('vp-cursor-text');
    } else if (ANNOTATION_TOOLS[this._activeTool]) {
      this._konvaEl.classList.add('vp-cursor-' + this._activeTool);
    } else {
      this._konvaEl.classList.add('vp-cursor-draw');
    }
  };

  // ── Drawing handlers (Konva pointer events on the stage) ─────────────────

  /**
   * Wire pointer handlers on the stage for drawing + selection. When the
   * active tool is 'select', the existing pan handlers (wired in
   * _wireMouse) take over on empty space; shape-click is handled below.
   */
  VisualPanel.prototype._wireDrawing = function () {
    if (!this.stage) return;
    var self = this;

    this.stage.on('mousedown.vp3', function (e) { self._onStageDown(e); });
    this.stage.on('mousemove.vp3', function (e) { self._onStageMove(e); });
    this.stage.on('mouseup.vp3',   function (e) { self._onStageUp(e);   });
    this.stage.on('touchstart.vp3',function (e) { self._onStageDown(e); });
    this.stage.on('touchmove.vp3', function (e) { self._onStageMove(e); });
    this.stage.on('touchend.vp3',  function (e) { self._onStageUp(e);   });
  };

  /**
   * Convert stage-pointer coords into userInputLayer-local coords.
   * With the current transform applied to the stage, the local layer
   * coordinates equal the "canvas" space that shape coords should use.
   */
  VisualPanel.prototype._stagePoint = function () {
    if (!this.stage) return { x: 0, y: 0 };
    var p = this.stage.getPointerPosition() || { x: 0, y: 0 };
    var t = this._transform || { x: 0, y: 0, scale: 1 };
    return {
      x: (p.x - t.x) / (t.scale || 1),
      y: (p.y - t.y) / (t.scale || 1),
    };
  };

  VisualPanel.prototype._onStageDown = function (e) {
    if (this._activeTool === 'select') {
      this._onSelectDown(e);
      return;
    }
    if (this._activeTool === 'text') {
      // Text tool: single click places anchor, opens inline input.
      var p = this._stagePoint();
      this._openTextInput(p.x, p.y);
      return;
    }
    // WP-5.1 — annotation tools take precedence over shape tools when
    // the active tool is one of ANNOTATION_TOOLS.
    if (ANNOTATION_TOOLS[this._activeTool]) {
      this._onAnnotationDown(e);
      return;
    }
    if (!SHAPE_TOOLS[this._activeTool]) return;
    // Rect/ellipse/diamond/line/arrow — begin draw.
    var start = this._stagePoint();
    this._drawContext = {
      type:   this._activeTool,
      start:  start,
      preview: null,
      // For line/arrow: snap start to nearby shape.
      startAnchor: (this._activeTool === 'line' || this._activeTool === 'arrow')
        ? this._snapToShape(start, null)
        : null,
    };
    this._createDrawPreview();
  };

  VisualPanel.prototype._onStageMove = function (e) {
    if (this._drawContext) {
      var end = this._stagePoint();
      this._updateDrawPreview(end);
      return;
    }
    // WP-5.1 — pen stroke extension (drag after mousedown).
    if (this._penContext) {
      this._extendPenStroke();
      return;
    }
  };

  VisualPanel.prototype._onStageUp = function (e) {
    if (this._drawContext) {
      var end = this._stagePoint();
      this._finalizeDraw(end);
      return;
    }
    if (this._penContext) {
      this._commitPenStroke();
      return;
    }
  };

  VisualPanel.prototype._cancelDraw = function () {
    if (this._drawContext && this._drawContext.preview) {
      try { this._drawContext.preview.destroy(); } catch (err) { /* ignore */ }
      if (this.userInputLayer) this.userInputLayer.draw();
    }
    this._drawContext = null;
  };

  VisualPanel.prototype._createDrawPreview = function () {
    if (typeof Konva === 'undefined' || !this.userInputLayer || !this._drawContext) return;
    var ctx = this._drawContext;
    var node;
    var baseAttrs = {
      name: 'user-shape-preview',
      stroke: '#0072B2',
      strokeWidth: 2,
      dash: [4, 4],
      listening: false,
      opacity: 0.8,
    };
    if (ctx.type === 'rect') {
      node = new Konva.Rect(Object.assign({
        x: ctx.start.x, y: ctx.start.y, width: 0, height: 0,
        fill: 'rgba(0,114,178,0.05)',
      }, baseAttrs));
    } else if (ctx.type === 'ellipse') {
      node = new Konva.Ellipse(Object.assign({
        x: ctx.start.x, y: ctx.start.y, radiusX: 0, radiusY: 0,
        fill: 'rgba(0,114,178,0.05)',
      }, baseAttrs));
    } else if (ctx.type === 'diamond') {
      node = new Konva.Line(Object.assign({
        points: [ctx.start.x, ctx.start.y, ctx.start.x, ctx.start.y,
                 ctx.start.x, ctx.start.y, ctx.start.x, ctx.start.y],
        closed: true,
        fill: 'rgba(0,114,178,0.05)',
      }, baseAttrs));
    } else if (ctx.type === 'line') {
      node = new Konva.Line(Object.assign({
        points: [ctx.start.x, ctx.start.y, ctx.start.x, ctx.start.y],
      }, baseAttrs));
    } else if (ctx.type === 'arrow') {
      node = new Konva.Arrow(Object.assign({
        points: [ctx.start.x, ctx.start.y, ctx.start.x, ctx.start.y],
        pointerLength: 8, pointerWidth: 8, fill: '#0072B2',
      }, baseAttrs));
    } else {
      return;
    }
    ctx.preview = node;
    this.userInputLayer.add(node);
    this.userInputLayer.batchDraw();
  };

  VisualPanel.prototype._updateDrawPreview = function (end) {
    var ctx = this._drawContext;
    if (!ctx || !ctx.preview) return;
    var s = ctx.start;
    if (ctx.type === 'rect') {
      var x = Math.min(s.x, end.x), y = Math.min(s.y, end.y);
      var w = Math.abs(end.x - s.x), h = Math.abs(end.y - s.y);
      ctx.preview.setAttrs({ x: x, y: y, width: w, height: h });
    } else if (ctx.type === 'ellipse') {
      var cx = (s.x + end.x) / 2, cy = (s.y + end.y) / 2;
      var rx = Math.abs(end.x - s.x) / 2, ry = Math.abs(end.y - s.y) / 2;
      ctx.preview.setAttrs({ x: cx, y: cy, radiusX: rx, radiusY: ry });
    } else if (ctx.type === 'diamond') {
      // Diamond = polygon with 4 vertices at the midpoints of the bbox edges.
      var dx = (s.x + end.x) / 2, dy = (s.y + end.y) / 2;
      ctx.preview.setAttrs({
        points: [dx, Math.min(s.y, end.y),
                 Math.max(s.x, end.x), dy,
                 dx, Math.max(s.y, end.y),
                 Math.min(s.x, end.x), dy],
      });
    } else if (ctx.type === 'line' || ctx.type === 'arrow') {
      ctx.preview.setAttrs({ points: [s.x, s.y, end.x, end.y] });
    }
    this.userInputLayer.batchDraw();
  };

  VisualPanel.prototype._finalizeDraw = function (end) {
    var ctx = this._drawContext;
    this._drawContext = null;
    if (!ctx || !ctx.preview) return;
    // Always remove the preview; we add a finalized shape in its place.
    try { ctx.preview.destroy(); } catch (err) { /* ignore */ }

    var s = ctx.start;
    if (ctx.type === 'rect' || ctx.type === 'ellipse' || ctx.type === 'diamond') {
      var w = Math.abs(end.x - s.x);
      var h = Math.abs(end.y - s.y);
      // Reject accidental sub-minimum drags.
      if (w < MIN_SHAPE_PX || h < MIN_SHAPE_PX) {
        this.userInputLayer.draw();
        return;
      }
      var geom;
      if (ctx.type === 'rect') {
        geom = { x: Math.min(s.x, end.x), y: Math.min(s.y, end.y), width: w, height: h };
      } else if (ctx.type === 'ellipse') {
        geom = {
          x: (s.x + end.x) / 2, y: (s.y + end.y) / 2,
          radiusX: w / 2, radiusY: h / 2,
        };
      } else { // diamond
        var dx = (s.x + end.x) / 2, dy = (s.y + end.y) / 2;
        geom = {
          points: [dx, Math.min(s.y, end.y),
                   Math.max(s.x, end.x), dy,
                   dx, Math.max(s.y, end.y),
                   Math.min(s.x, end.x), dy],
        };
      }
      this._createShape(ctx.type, geom);
    } else if (ctx.type === 'line' || ctx.type === 'arrow') {
      // Snap endpoints to any shape within CONN_SNAP_PX.
      var startAnchor = ctx.startAnchor;
      var endAnchor   = this._snapToShape(end, null);
      this._createShape(ctx.type, {
        points: [s.x, s.y, end.x, end.y],
        connEndpointStart: startAnchor,
        connEndpointEnd:   endAnchor,
      });
    }
    this.userInputLayer.draw();
  };

  /**
   * Snap `point` to the nearest user shape within CONN_SNAP_PX and return
   * that shape's userShapeId, else null. `excludeId` skips a specific shape
   * (useful when rerouting a moved shape's own connections).
   */
  VisualPanel.prototype._snapToShape = function (point, excludeId) {
    if (!this.userInputLayer) return null;
    var shapes = this.userInputLayer.find('.user-shape');
    var best = null, bestDist = CONN_SNAP_PX;
    for (var i = 0; i < shapes.length; i++) {
      var s = shapes[i];
      var sid = s.getAttr('userShapeId');
      if (!sid) continue;
      if (excludeId && sid === excludeId) continue;
      var box;
      try { box = s.getClientRect({ relativeTo: this.userInputLayer }); }
      catch (err) { box = null; }
      if (!box) continue;
      // Distance from point to the rect: 0 if inside, else distance to edge.
      var cx = box.x + box.width / 2, cy = box.y + box.height / 2;
      var d = Math.hypot(point.x - cx, point.y - cy);
      // Count as "on shape" if within threshold of the center OR inside the box.
      var inside = point.x >= box.x && point.x <= box.x + box.width &&
                   point.y >= box.y && point.y <= box.y + box.height;
      if (inside || d <= bestDist) {
        if (d < bestDist || inside) {
          bestDist = d;
          best = sid;
        }
      }
    }
    return best;
  };

  // ── Text tool: inline input ──────────────────────────────────────────────

  VisualPanel.prototype._openTextInput = function (x, y) {
    if (!this._viewportEl) return;
    this._dismissTextInput();
    var doc = this.el.ownerDocument || document;
    var input = doc.createElement('input');
    input.type = 'text';
    input.className = 'vp-text-input';
    input.id = 'vp-text-input-' + this.panelId;
    // Place input at the pointer's viewport-space position.
    var t = this._transform || { x: 0, y: 0, scale: 1 };
    var vx = x * t.scale + t.x;
    var vy = y * t.scale + t.y;
    input.style.position = 'absolute';
    input.style.left = vx + 'px';
    input.style.top  = vy + 'px';
    this._viewportEl.appendChild(input);
    this._textInputEl = input;
    this._textInputAnchor = { x: x, y: y };
    var self = this;
    var commit = function () {
      var value = (self._textInputEl && self._textInputEl.value) || '';
      var anchor = self._textInputAnchor || { x: 0, y: 0 };
      self._dismissTextInput();
      if (value.length > 0) {
        self._createShape('text', { x: anchor.x, y: anchor.y, text: value });
      }
    };
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); commit(); }
      else if (e.key === 'Escape') { e.preventDefault(); self._dismissTextInput(); }
    });
    input.addEventListener('blur', commit);
    try { input.focus(); } catch (err) { /* jsdom sometimes rejects focus */ }
  };

  VisualPanel.prototype._dismissTextInput = function () {
    if (this._textInputEl && this._textInputEl.parentNode) {
      try { this._textInputEl.parentNode.removeChild(this._textInputEl); }
      catch (err) { /* ignore */ }
    }
    this._textInputEl = null;
    this._textInputAnchor = null;
  };

  // ── Shape creation / deletion / movement (public for testing) ────────────

  /**
   * Create a user shape on userInputLayer. `type` is one of the
   * SHAPE_TOOLS keys. `params` is the geometry + (optionally)
   * connEndpointStart/End for line/arrow.
   *
   * Returns the Konva node. Pushes an undo frame unless _suppressHistory
   * is set (internal during undo/redo replays).
   */
  VisualPanel.prototype._createShape = function (type, params) {
    if (typeof Konva === 'undefined' || !this.userInputLayer) return null;
    if (!SHAPE_TOOLS[type]) return null;
    params = params || {};
    var id = 'u-' + type + '-' + (++this._shapeCounter);
    var node;
    var stroke = '#0072B2';
    var fill   = 'rgba(0,114,178,0.08)';

    if (type === 'rect') {
      node = new Konva.Rect({
        x: params.x || 0, y: params.y || 0,
        width:  params.width  || MIN_SHAPE_PX,
        height: params.height || MIN_SHAPE_PX,
        stroke: stroke, strokeWidth: 2, fill: fill,
        draggable: true,
      });
    } else if (type === 'ellipse') {
      node = new Konva.Ellipse({
        x: params.x || 0, y: params.y || 0,
        radiusX: params.radiusX || MIN_SHAPE_PX / 2,
        radiusY: params.radiusY || MIN_SHAPE_PX / 2,
        stroke: stroke, strokeWidth: 2, fill: fill,
        draggable: true,
      });
    } else if (type === 'diamond') {
      node = new Konva.Line({
        points: params.points || [0, 0, MIN_SHAPE_PX, MIN_SHAPE_PX / 2,
                                  0, MIN_SHAPE_PX, -MIN_SHAPE_PX, MIN_SHAPE_PX / 2],
        closed: true,
        stroke: stroke, strokeWidth: 2, fill: fill,
        draggable: true,
      });
    } else if (type === 'line') {
      node = new Konva.Line({
        points: params.points || [0, 0, MIN_SHAPE_PX, 0],
        stroke: stroke, strokeWidth: 2,
        draggable: true,
      });
    } else if (type === 'arrow') {
      node = new Konva.Arrow({
        points: params.points || [0, 0, MIN_SHAPE_PX, 0],
        stroke: stroke, strokeWidth: 2, fill: stroke,
        pointerLength: 8, pointerWidth: 8,
        draggable: true,
      });
    } else if (type === 'text') {
      node = new Konva.Text({
        x: params.x || 0, y: params.y || 0,
        text: params.text || '',
        fontSize: 14, fill: '#1a1a1a',
        draggable: true,
      });
    } else {
      return null;
    }

    // Konva's setAttrs filters out null/undefined values from its attrs map.
    // To honor the shared WP-3.1/WP-3.2 convention that every user-shape
    // carries a readable value (including null) for every convention key,
    // we write non-null keys via setAttrs and splash null keys directly
    // onto node.attrs so getAttr() returns null instead of undefined.
    node.setAttrs({
      name: 'user-shape',
      userShapeType: type,
      userShapeId:   id,
      userLabel:     (type === 'text') ? (params.text || '') : (params.userLabel || ''),
    });
    // Null-valued convention keys — direct write preserves null semantics.
    node.attrs.userCluster       = null;
    node.attrs.connEndpointStart = (type === 'line' || type === 'arrow')
      ? (params.connEndpointStart != null ? params.connEndpointStart : null)
      : null;
    node.attrs.connEndpointEnd   = (type === 'line' || type === 'arrow')
      ? (params.connEndpointEnd   != null ? params.connEndpointEnd   : null)
      : null;

    // Wire drag-end to push a move history frame + reroute connections.
    var self = this;
    node.on('dragend.vp3', function () {
      if (self._suppressHistory) return;
      // We record position delta via the node's current pos vs. last-known.
      var prev = node._vpPrevPos || { x: 0, y: 0 };
      var curr = { x: node.x(), y: node.y() };
      var nid = node.getAttr('userShapeId');
      self._pushHistory({
        label: 'move',
        undoFn: function () { self._setShapePos(nid, prev.x, prev.y); },
        redoFn: function () { self._setShapePos(nid, curr.x, curr.y); },
      });
      node._vpPrevPos = curr;
    });
    node.on('dragstart.vp3', function () {
      node._vpPrevPos = { x: node.x(), y: node.y() };
    });

    this.userInputLayer.add(node);
    this.userInputLayer.draw();

    if (!this._suppressHistory) {
      var serialized = node.toJSON();
      this._pushHistory({
        label: 'create:' + type,
        undoFn: function () { self._removeShapeById(id); },
        redoFn: function () { self._reinsertShapeJSON(serialized); },
      });
    }
    return node;
  };

  /**
   * Move a shape by delta. Returns true on success.
   */
  VisualPanel.prototype._moveShape = function (id, dx, dy) {
    var node = this._findShapeById(id);
    if (!node) return false;
    var prev = { x: node.x(), y: node.y() };
    var curr = { x: prev.x + dx, y: prev.y + dy };
    node.position(curr);
    this.userInputLayer.draw();
    if (!this._suppressHistory) {
      var self = this;
      this._pushHistory({
        label: 'move',
        undoFn: function () { self._setShapePos(id, prev.x, prev.y); },
        redoFn: function () { self._setShapePos(id, curr.x, curr.y); },
      });
    }
    return true;
  };

  VisualPanel.prototype._setShapePos = function (id, x, y) {
    var node = this._findShapeById(id);
    if (!node) return;
    node.position({ x: x, y: y });
    this.userInputLayer.draw();
  };

  VisualPanel.prototype._findShapeById = function (id) {
    if (!this.userInputLayer) return null;
    var shapes = this.userInputLayer.find('.user-shape');
    for (var i = 0; i < shapes.length; i++) {
      if (shapes[i].getAttr('userShapeId') === id) return shapes[i];
    }
    return null;
  };

  /**
   * Delete a shape by id. Any line/arrow whose endpoint was anchored to
   * this shape has its endpoint set to null (leaving the line in place).
   */
  VisualPanel.prototype._deleteShape = function (id) {
    var node = this._findShapeById(id);
    if (!node) return false;
    var serialized = node.toJSON();
    // Gather endpoint-anchor backrefs so we can repair on undo.
    var brokenAnchors = [];
    if (this.userInputLayer) {
      var shapes = this.userInputLayer.find('.user-shape');
      for (var i = 0; i < shapes.length; i++) {
        var s = shapes[i];
        if (s.getAttr('connEndpointStart') === id) {
          brokenAnchors.push({ sid: s.getAttr('userShapeId'), which: 'start' });
          s.attrs.connEndpointStart = null;  // direct write preserves null
        }
        if (s.getAttr('connEndpointEnd') === id) {
          brokenAnchors.push({ sid: s.getAttr('userShapeId'), which: 'end' });
          s.attrs.connEndpointEnd = null;   // direct write preserves null
        }
      }
    }
    node.destroy();
    // Clear this shape from selection set if present.
    this._selectedShapeIds = this._selectedShapeIds.filter(function (x) { return x !== id; });
    this._redrawSelection();
    this.userInputLayer.draw();

    if (!this._suppressHistory) {
      var self = this;
      this._pushHistory({
        label: 'delete',
        undoFn: function () {
          self._reinsertShapeJSON(serialized);
          // Restore broken anchors
          for (var j = 0; j < brokenAnchors.length; j++) {
            var ba = brokenAnchors[j];
            var peer = self._findShapeById(ba.sid);
            if (peer) {
              if (ba.which === 'start') peer.attrs.connEndpointStart = id;
              else                      peer.attrs.connEndpointEnd   = id;
            }
          }
          if (self.userInputLayer) self.userInputLayer.draw();
        },
        redoFn: function () { self._removeShapeById(id); },
      });
    }
    return true;
  };

  VisualPanel.prototype._removeShapeById = function (id) {
    var node = this._findShapeById(id);
    if (node) node.destroy();
    this._selectedShapeIds = this._selectedShapeIds.filter(function (x) { return x !== id; });
    this._redrawSelection();
    if (this.userInputLayer) this.userInputLayer.draw();
  };

  /**
   * Rehydrate a previously-destroyed shape from its JSON blob. Required
   * for undo on delete — we must preserve id and attr convention.
   */
  VisualPanel.prototype._reinsertShapeJSON = function (json) {
    if (typeof Konva === 'undefined' || !this.userInputLayer) return null;
    var node;
    try {
      node = Konva.Node.create(json);
    } catch (err) { return null; }
    if (!node) return null;
    // Rewire drag handlers (Konva serialization doesn't carry them).
    var self = this;
    node.draggable(true);
    node.on('dragstart.vp3', function () { node._vpPrevPos = { x: node.x(), y: node.y() }; });
    node.on('dragend.vp3', function () {
      if (self._suppressHistory) return;
      var prev = node._vpPrevPos || { x: 0, y: 0 };
      var curr = { x: node.x(), y: node.y() };
      var nid = node.getAttr('userShapeId');
      self._pushHistory({
        label: 'move',
        undoFn: function () { self._setShapePos(nid, prev.x, prev.y); },
        redoFn: function () { self._setShapePos(nid, curr.x, curr.y); },
      });
      node._vpPrevPos = curr;
    });
    this.userInputLayer.add(node);
    this.userInputLayer.draw();
    return node;
  };

  // ── Selection (select tool) ──────────────────────────────────────────────

  VisualPanel.prototype._onSelectDown = function (e) {
    if (!e || !e.target) return;
    var target = e.target;
    // Walk up to find a node named 'user-shape' OR a user-annotation group
    // (annotationSource='user'). Annotations sit on annotationLayer; shapes
    // sit on userInputLayer. Both are selectable.
    var shapeNode = null;
    var annotNode = null;
    var cursor = target;
    while (cursor && cursor !== this.stage) {
      if (typeof cursor.name === 'function' && cursor.name() === 'user-shape') {
        shapeNode = cursor; break;
      }
      if (cursor.getAttr && cursor.getAttr('annotationSource') === 'user') {
        annotNode = cursor; break;
      }
      cursor = cursor.getParent && cursor.getParent();
    }

    if (annotNode) {
      var aid = annotNode.getAttr('userAnnotationId');
      if (!aid) return;
      var amulti = e.evt && (e.evt.shiftKey || e.evt.metaKey);
      if (amulti) {
        var aidx = this._selectedAnnotIds.indexOf(aid);
        if (aidx >= 0) this._selectedAnnotIds.splice(aidx, 1);
        else this._selectedAnnotIds.push(aid);
      } else {
        this._selectedAnnotIds = [aid];
        this._selectedShapeIds = [];
      }
      this._redrawSelection();
      this._redrawAnnotationSelection();
      return;
    }

    if (!shapeNode) {
      // Empty space click in select mode — clear both selection sets.
      this._selectedShapeIds = [];
      this._selectedAnnotIds = [];
      this._redrawSelection();
      this._redrawAnnotationSelection();
      return;
    }
    var id = shapeNode.getAttr('userShapeId');
    if (!id) return;
    var multi = e.evt && (e.evt.shiftKey || e.evt.metaKey);
    if (multi) {
      var idx = this._selectedShapeIds.indexOf(id);
      if (idx >= 0) this._selectedShapeIds.splice(idx, 1);
      else this._selectedShapeIds.push(id);
    } else {
      this._selectedShapeIds = [id];
      this._selectedAnnotIds = [];
    }
    this._redrawSelection();
    this._redrawAnnotationSelection();
  };

  VisualPanel.prototype._redrawSelection = function () {
    if (!this.selectionLayer || typeof Konva === 'undefined') return;
    // Only clear user-shape selection rings; semantic selection handled elsewhere.
    var rings = this.selectionLayer.find('.vp-user-selection');
    for (var i = 0; i < rings.length; i++) rings[i].destroy();

    for (var j = 0; j < this._selectedShapeIds.length; j++) {
      var id = this._selectedShapeIds[j];
      var node = this._findShapeById(id);
      if (!node) continue;
      var box;
      try { box = node.getClientRect({ relativeTo: this.userInputLayer }); }
      catch (err) { box = null; }
      if (!box) continue;
      var ring = new Konva.Rect({
        x: box.x - 4, y: box.y - 4,
        width: box.width + 8, height: box.height + 8,
        stroke: '#E69F00', strokeWidth: 2, dash: [4, 3],
        listening: false,
        name: 'vp-user-selection',
      });
      this.selectionLayer.add(ring);
    }
    this.selectionLayer.draw();
  };

  VisualPanel.prototype.getSelectedShapeIds = function () {
    return this._selectedShapeIds.slice();
  };

  VisualPanel.prototype.deleteSelected = function () {
    if (this._selectedShapeIds.length === 0) return;
    var ids = this._selectedShapeIds.slice();
    // Delete pushes one history frame per shape. For multi-delete this is
    // N frames; acceptable given current scope. (Batching is a future improvement.)
    for (var i = 0; i < ids.length; i++) this._deleteShape(ids[i]);
    this._selectedShapeIds = [];
    this._redrawSelection();
  };

  // ── Undo/redo ────────────────────────────────────────────────────────────

  /**
   * Push a history frame. Truncates any forward history (standard undo
   * stack semantics) and caps depth at HISTORY_CAP.
   */
  VisualPanel.prototype._pushHistory = function (frame) {
    if (this._suppressHistory) return;
    // Truncate forward history.
    if (this._historyCursor < this._history.length) {
      this._history.length = this._historyCursor;
    }
    this._history.push(frame);
    // Cap depth (drop oldest).
    if (this._history.length > HISTORY_CAP) {
      this._history.shift();
    }
    this._historyCursor = this._history.length;
  };

  VisualPanel.prototype.undo = function () {
    if (this._historyCursor <= 0) return false;
    this._historyCursor -= 1;
    var frame = this._history[this._historyCursor];
    this._suppressHistory = true;
    try { frame.undoFn(); } finally { this._suppressHistory = false; }
    return true;
  };

  VisualPanel.prototype.redo = function () {
    if (this._historyCursor >= this._history.length) return false;
    var frame = this._history[this._historyCursor];
    this._historyCursor += 1;
    this._suppressHistory = true;
    try { frame.redoFn(); } finally { this._suppressHistory = false; }
    return true;
  };

  VisualPanel.prototype.getHistoryCursor = function () { return this._historyCursor; };
  VisualPanel.prototype.getHistoryLength = function () { return this._history.length; };

  // ── clear-user-input ─────────────────────────────────────────────────────

  /**
   * Wipe userInputLayer only. backgroundLayer + annotationLayer +
   * selectionLayer (semantic highlights) are preserved. Pushes a single
   * undo frame that restores the entire layer.
   */
  VisualPanel.prototype.clearUserInput = function () {
    if (!this.userInputLayer) return;
    // WP-4.1 — also release any pending image. Rationale: the Clear User
    // Drawings affordance is the user's explicit "reset my attachments"
    // gesture; we don't want a stale image from an earlier draft to ride
    // along on the next message.
    this.clearPendingImage();

    var shapes = this.userInputLayer.find('.user-shape');
    if (shapes.length === 0) return;
    var snapshots = [];
    for (var i = 0; i < shapes.length; i++) snapshots.push(shapes[i].toJSON());
    for (var j = 0; j < shapes.length; j++) shapes[j].destroy();
    this._selectedShapeIds = [];
    this._redrawSelection();
    this.userInputLayer.draw();

    var self = this;
    this._pushHistory({
      label: 'clear-user-input',
      undoFn: function () {
        for (var k = 0; k < snapshots.length; k++) self._reinsertShapeJSON(snapshots[k]);
      },
      redoFn: function () {
        var all = self.userInputLayer.find('.user-shape');
        for (var k = 0; k < all.length; k++) all[k].destroy();
        self.userInputLayer.draw();
      },
    });
  };

  // ══════════════════════════════════════════════════════════════════════════
  // WP-4.1 — Image upload UI (drag-drop + file picker + camera capture)
  // ══════════════════════════════════════════════════════════════════════════
  //
  // Three input affordances populate `this._pendingImage` which chat-panel.js
  // reads at send time (WP-3.3 contract):
  //   1. Drag-and-drop anywhere on the panel container.
  //   2. Hidden `<input type="file" accept="image/*">` invoked by toolbar btn.
  //   3. Optional camera capture (mobile only — `capture="environment"`).
  //
  // The uploaded image lands on the Konva `backgroundLayer` beneath the
  // DOM-overlay SVG artifact host. When both exist (rare — e.g. an annotate
  // envelope targets a user-uploaded sketch), the artifact renders on top per
  // the layer-ordering invariant in the file-level doc comment.
  //
  // The pending-image contract matches the shape chat-panel already reads:
  //   _pendingImage = { blob: File|Blob, name: string, type: string, dataUrl: string }

  /**
   * Wire drag-and-drop on the panel root, file-input change events, and the
   * thumbnail indicator's click-to-reveal-remove toggle. Idempotent (no-op
   * when called twice on the same instance).
   */
  VisualPanel.prototype._wireImageUpload = function () {
    if (!this.el) return;
    var self = this;

    // ── Drag-and-drop ──────────────────────────────────────────────────────
    this._onDragOver = function (e) {
      // Only accept drags that carry files (ignore text/selection drags).
      var dt = e.dataTransfer;
      if (!dt) return;
      var types = dt.types;
      var hasFiles = false;
      if (types) {
        // types is a DOMStringList (Array-like) in real browsers; jsdom
        // returns a plain array. Support both by iterating.
        for (var i = 0; i < types.length; i++) {
          if (types[i] === 'Files') { hasFiles = true; break; }
        }
      }
      if (!hasFiles) return;
      e.preventDefault();
      if (dt.dropEffect !== undefined) dt.dropEffect = 'copy';
      self._setDropHighlight(true);
    };
    this._onDragLeave = function (e) {
      // Only hide the highlight when the drag actually exits the panel —
      // `dragleave` also fires when the cursor crosses a child element.
      // Compare relatedTarget: if it's inside the panel, ignore.
      var rt = e.relatedTarget;
      if (rt && self.el.contains && self.el.contains(rt)) return;
      self._setDropHighlight(false);
    };
    this._onDrop = function (e) {
      var dt = e.dataTransfer;
      if (!dt) return;
      e.preventDefault();
      self._setDropHighlight(false);
      var files = dt.files || [];
      if (!files || files.length === 0) return;
      // Find the first image file; ignore non-images silently unless NOTHING
      // in the drop set is an image, in which case surface the error.
      var imageFile = null;
      for (var i = 0; i < files.length; i++) {
        if (files[i] && files[i].type && IMAGE_MIME_RE.test(files[i].type)) {
          imageFile = files[i];
          break;
        }
      }
      if (!imageFile) {
        self._showImageError('Only image files are supported (JPG, PNG, GIF, WebP).');
        return;
      }
      self.attachImage(imageFile);
    };

    this.el.addEventListener('dragover',  this._onDragOver);
    this.el.addEventListener('dragleave', this._onDragLeave);
    this.el.addEventListener('drop',      this._onDrop);

    // ── File input (toolbar button) ───────────────────────────────────────
    if (this._fileInputEl) {
      this._onFileInputChange = function () {
        var f = self._fileInputEl.files && self._fileInputEl.files[0];
        if (f) self.attachImage(f);
        // Reset so selecting the same file twice in a row still fires change.
        self._fileInputEl.value = '';
      };
      this._fileInputEl.addEventListener('change', this._onFileInputChange);
    }

    // ── Camera input (mobile) ─────────────────────────────────────────────
    if (this._cameraInputEl) {
      this._onCameraInputChange = function () {
        var f = self._cameraInputEl.files && self._cameraInputEl.files[0];
        if (f) self.attachImage(f);
        self._cameraInputEl.value = '';
      };
      this._cameraInputEl.addEventListener('change', this._onCameraInputChange);
    }

    // ── Image indicator: click to toggle the remove button ────────────────
    if (this._imageIndicator) {
      this._onImageIndicatorClick = function (e) {
        var removeBtn = e.target && e.target.closest && e.target.closest('.vp-image-remove');
        if (removeBtn) {
          // Explicit remove.
          self.clearPendingImage();
          return;
        }
        // Toggle the visible state of the remove button (purely cosmetic —
        // the button is always in the DOM).
        self._imageIndicatorOpen = !self._imageIndicatorOpen;
        self._updateImageIndicator();
      };
      this._imageIndicator.addEventListener('click', this._onImageIndicatorClick);
    }
  };

  /**
   * Toggle the drop-zone highlight. Applies a class on the panel root so
   * CSS can paint the dashed border + tint.
   */
  VisualPanel.prototype._setDropHighlight = function (on) {
    if (!this.el) return;
    if (on) this.el.classList.add('visual-panel--dropzone-active');
    else    this.el.classList.remove('visual-panel--dropzone-active');
  };

  /**
   * Open the hidden file picker (file or camera variant). Safe to call even
   * when the camera input isn't present (desktop); falls back to file.
   */
  VisualPanel.prototype._openFilePicker = function (which) {
    var target = (which === 'camera' && this._cameraInputEl)
      ? this._cameraInputEl
      : this._fileInputEl;
    if (!target) return;
    try { target.click(); } catch (e) { /* jsdom sometimes rejects click() */ }
  };

  /**
   * Public API — programmatic image attach. Validates MIME + size, reads as
   * data URL, mounts a Konva.Image on backgroundLayer, and populates
   * `_pendingImage`. Returns a Promise that resolves to the shape
   * { blob, name, type, dataUrl } on success, or null on rejection.
   *
   * Second-image behavior: replaces the first without a modal confirm (the
   * thumbnail indicator already provides explicit removal; a dialog is noise
   * for a replaceable attachment).
   */
  VisualPanel.prototype.attachImage = function (file) {
    var self = this;
    return new Promise(function (resolve) {
      if (!file || typeof file !== 'object') {
        resolve(null);
        return;
      }
      var type = file.type || '';
      if (!IMAGE_MIME_RE.test(type)) {
        self._showImageError('Only image files are supported (JPG, PNG, GIF, WebP).');
        resolve(null);
        return;
      }
      var size = typeof file.size === 'number' ? file.size : 0;
      if (size > MAX_IMAGE_BYTES) {
        var mb = (MAX_IMAGE_BYTES / (1024 * 1024)).toFixed(0);
        self._showImageError('Image must be \u2264 ' + mb + ' MB. Please resize or use a smaller image.');
        resolve(null);
        return;
      }

      var reader;
      try {
        reader = new FileReader();
      } catch (e) {
        self._showImageError('Couldn\u2019t read image. Please try again.');
        resolve(null);
        return;
      }
      reader.onload = function () {
        var dataUrl = reader.result;
        if (typeof dataUrl !== 'string' || dataUrl.length === 0) {
          self._showImageError('Couldn\u2019t read image. Please try again.');
          resolve(null);
          return;
        }
        self._installBackgroundImage(dataUrl, file, function () {
          self._pendingImage = {
            blob: file,
            name: file.name || 'upload.png',
            type: type,
            dataUrl: dataUrl,
          };
          self._imageIndicatorOpen = false;
          self._updateImageIndicator();
          // Auto-clear any stale error bar (e.g. a prior "too large").
          self._hideImageError();
          resolve(self._pendingImage);
        });
      };
      reader.onerror = function () {
        self._showImageError('Couldn\u2019t read image. Please try again.');
        resolve(null);
      };
      try {
        reader.readAsDataURL(file);
      } catch (e) {
        self._showImageError('Couldn\u2019t read image. Please try again.');
        resolve(null);
      }
    });
  };

  /**
   * Mount a Konva.Image on backgroundLayer at a scale that fits the stage
   * while preserving aspect ratio. Clears any prior uploaded image (but
   * leaves the DOM-overlay SVG artifact untouched — artifacts ride above).
   *
   * The `onReady` callback fires once the underlying HTMLImageElement has
   * loaded (or failed to load, in which case we still resolve — the
   * `_pendingImage` contract only requires the file blob, not a successful
   * bitmap decode).
   */
  VisualPanel.prototype._installBackgroundImage = function (dataUrl, file, onReady) {
    var self = this;
    // Remove prior uploaded image (if any). Do NOT touch the sentinel group
    // used for transform tracking or the SVG overlay — those belong to the
    // artifact pipeline.
    if (this._backgroundImageNode) {
      try { this._backgroundImageNode.destroy(); } catch (e) { /* ignore */ }
      this._backgroundImageNode = null;
    }

    // In jsdom HTMLImageElement may not implement proper onload semantics;
    // we still construct it so `naturalWidth`/`naturalHeight` are available
    // if possible. For jsdom we fall back to a default size so the Konva.Image
    // still lands with sensible geometry.
    var doc = (this.el && this.el.ownerDocument) || (typeof document !== 'undefined' ? document : null);
    if (!doc || typeof Konva === 'undefined' || !this.backgroundLayer) {
      if (typeof onReady === 'function') onReady();
      return;
    }
    var img = doc.createElement('img');

    var finalize = function () {
      var stageW = (self.stage && self.stage.width && self.stage.width())  || 600;
      var stageH = (self.stage && self.stage.height && self.stage.height()) || 400;
      var naturalW = img.naturalWidth  || img.width  || 0;
      var naturalH = img.naturalHeight || img.height || 0;
      if (!naturalW || !naturalH) {
        // jsdom / decode failure — pick a safe default so Konva still
        // produces a placeholder. Real browsers always populate these.
        naturalW = 400;
        naturalH = 300;
      }
      // Fit scale (preserve aspect ratio; no upscaling past native size).
      var scale = Math.min(stageW / naturalW, stageH / naturalH, 1);
      var drawW = naturalW * scale;
      var drawH = naturalH * scale;
      var x = (stageW - drawW) / 2;
      var y = (stageH - drawH) / 2;

      try {
        self._backgroundImageNode = new Konva.Image({
          image: img,
          x: x, y: y,
          width:  drawW,
          height: drawH,
          name: 'vp-background-image',
          listening: false,
        });
        // Store natural dimensions + source URL for inspection / debug.
        self._backgroundImageNode.setAttrs({
          naturalWidth:  naturalW,
          naturalHeight: naturalH,
          sourceName:    (file && file.name) || '',
          sourceType:    (file && file.type) || '',
        });
        self.backgroundLayer.add(self._backgroundImageNode);
        try { self.backgroundLayer.draw(); } catch (e) { /* ignore */ }
      } catch (e) {
        // Never throw — the pending image contract is what matters.
      }
      if (typeof onReady === 'function') onReady();
    };

    // Register handlers before setting src to catch already-cached loads.
    img.onload  = finalize;
    img.onerror = finalize;   // still resolve with placeholder geometry
    try { img.src = dataUrl; } catch (e) { finalize(); return; }
    // In jsdom, onload may never fire; if so, resolve after a microtask so
    // the caller's Promise resolves in a bounded time. We detect "no fire"
    // via a small RAF/setTimeout race. Safe in both environments.
    if (typeof window !== 'undefined' && typeof window.setTimeout === 'function') {
      setTimeout(function () {
        if (!self._backgroundImageNode && !self._destroyed) finalize();
      }, 0);
    }
  };

  /**
   * Public API — returns the pending image (or null). Matches the WP-3.3
   * chat-panel contract: callers typically access `.blob` and `.name`.
   */
  VisualPanel.prototype.getPendingImage = function () {
    return this._pendingImage || null;
  };

  /**
   * Public API — release the pending image + remove its Konva.Image from
   * backgroundLayer. Called by chat-panel after a successful send; also
   * called from the thumbnail indicator's remove button and from
   * `clearUserInput()`.
   *
   * Does NOT touch the DOM-overlay SVG host or any other layers.
   */
  VisualPanel.prototype.clearPendingImage = function () {
    this._pendingImage = null;
    this._imageIndicatorOpen = false;
    if (this._backgroundImageNode) {
      try { this._backgroundImageNode.destroy(); } catch (e) { /* ignore */ }
      this._backgroundImageNode = null;
      try { if (this.backgroundLayer) this.backgroundLayer.draw(); } catch (e) { /* ignore */ }
    }
    this._updateImageIndicator();
  };

  /**
   * Refresh the thumbnail indicator chrome: show when there's a pending
   * image, hide when not. Label shows the file name (truncated); the
   * remove button appears when `_imageIndicatorOpen` is true.
   */
  VisualPanel.prototype._updateImageIndicator = function () {
    if (!this._imageIndicator) return;
    if (!this._pendingImage) {
      this._imageIndicator.hidden = true;
      this._imageIndicator.classList.remove('visual-panel__image-indicator--open');
      // Clear content so a stale thumbnail doesn't flash on next attach.
      var wrap = this._imageIndicator.querySelector('.vp-image-thumb-wrap');
      if (wrap) wrap.innerHTML = '';
      var label = this._imageIndicator.querySelector('.vp-image-label');
      if (label) label.textContent = '';
      return;
    }
    this._imageIndicator.hidden = false;
    this._imageIndicator.classList.toggle(
      'visual-panel__image-indicator--open',
      !!this._imageIndicatorOpen
    );
    var wrapEl = this._imageIndicator.querySelector('.vp-image-thumb-wrap');
    if (wrapEl) {
      // Single <img> child; reuse on update to avoid DOM churn.
      var thumb = wrapEl.querySelector('img.vp-image-thumb');
      if (!thumb) {
        var doc = this.el.ownerDocument || document;
        thumb = doc.createElement('img');
        thumb.className = 'vp-image-thumb';
        thumb.alt = '';
        wrapEl.appendChild(thumb);
      }
      thumb.src = this._pendingImage.dataUrl || '';
    }
    var labelEl = this._imageIndicator.querySelector('.vp-image-label');
    if (labelEl) {
      var name = this._pendingImage.name || 'image';
      if (name.length > 28) name = name.slice(0, 25) + '\u2026';
      labelEl.textContent = name;
    }
  };

  /**
   * Surface a non-blocking inline error for image-upload failures via the
   * existing panel error bar. Auto-hides after IMAGE_ERROR_AUTOHIDE_MS.
   */
  VisualPanel.prototype._showImageError = function (msg) {
    if (!this._errorBar) return;
    this._errorBar.textContent = msg || 'Image upload failed.';
    this._errorBar.classList.add('visual-panel__errorbar--image');
    this._errorBar.hidden = false;
    if (this._imageErrorTimeout) {
      try { clearTimeout(this._imageErrorTimeout); } catch (e) { /* ignore */ }
    }
    var self = this;
    this._imageErrorTimeout = setTimeout(function () {
      self._hideImageError();
    }, IMAGE_ERROR_AUTOHIDE_MS);
  };

  VisualPanel.prototype._hideImageError = function () {
    if (!this._errorBar) return;
    // Only hide when the bar is still owned by the image subsystem — don't
    // clobber a compile-error message the rendering pipeline is showing.
    if (!this._errorBar.classList.contains('visual-panel__errorbar--image')) return;
    this._errorBar.hidden = true;
    this._errorBar.textContent = '';
    this._errorBar.classList.remove('visual-panel__errorbar--image');
    if (this._imageErrorTimeout) {
      try { clearTimeout(this._imageErrorTimeout); } catch (e) { /* ignore */ }
      this._imageErrorTimeout = null;
    }
  };

  // ══════════════════════════════════════════════════════════════════════════
  // WP-4.4 — Text-only fallback UX (manual-trace prompt)
  // ══════════════════════════════════════════════════════════════════════════
  //
  // The server emits a `visual_fallback` SSE frame BEFORE the first model
  // token when an image upload couldn't be extracted structurally:
  //   * reason: 'no_vision_available' — no vision model exists in any bucket
  //   * reason: 'extraction_failed'   — an extractor ran but parsing failed
  //
  // chat-panel.js routes the event to `showFallbackPrompt(alert)`, which
  // renders a self-contained HTML overlay with three buttons:
  //   * Start tracing   → select the rect tool + focus stage + dismiss
  //   * Queue for later → POST /chat/queue-retry + dismiss
  //   * Dismiss         → hide overlay (no side effects)
  //
  // Overlay is a single DOM node lazy-created on first use, reused on
  // subsequent prompts. Styled via visual-panel.css — no inline colors.

  /**
   * Public API: render the manual-trace overlay.
   *
   * @param {object} alert - The SSE `visual_fallback` frame payload.
   *   {
   *     reason:              'no_vision_available' | 'extraction_failed',
   *     extractor_attempted: string|null,
   *     parse_errors:        string[],
   *     user_message:        string,
   *     actions:             string[],
   *     conversation_id:     string  (added by the chat-panel dispatch)
   *   }
   */
  VisualPanel.prototype.showFallbackPrompt = function (alert) {
    if (!alert || typeof alert !== 'object') return;
    this._fallbackAlert = alert;
    this._ensureFallbackOverlay();
    this._populateFallbackOverlay(alert);
    this._fallbackOverlayEl.hidden = false;
  };

  /**
   * Public API: hide the overlay. No-op when not shown.
   */
  VisualPanel.prototype.dismissFallbackPrompt = function () {
    if (this._fallbackOverlayEl) {
      this._fallbackOverlayEl.hidden = true;
    }
    // Clear the inline success/pending note so a subsequent prompt starts clean.
    if (this._fallbackNoteEl) {
      this._fallbackNoteEl.textContent = '';
      this._fallbackNoteEl.hidden = true;
    }
  };

  /**
   * Lazy-create the overlay DOM. Idempotent — subsequent calls are no-ops.
   * Overlay lives inside the panel's root `<div>` so it's positioned
   * relative to the panel, not the document. Three buttons wire to
   * handlers that close over `this` via the _fallbackAlert stash.
   */
  VisualPanel.prototype._ensureFallbackOverlay = function () {
    if (this._fallbackOverlayEl) return;
    var doc = (this.el && this.el.ownerDocument) || (typeof document !== 'undefined' ? document : null);
    if (!doc) return;

    var overlay = doc.createElement('div');
    overlay.className = 'visual-panel__fallback-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'false');
    overlay.setAttribute('aria-labelledby', 'vp-fallback-overlay-heading-' + this.panelId);
    overlay.hidden = true;

    var card = doc.createElement('div');
    card.className = 'visual-panel__fallback-overlay-card';

    var heading = doc.createElement('div');
    heading.className = 'visual-panel__fallback-heading';
    heading.id = 'vp-fallback-overlay-heading-' + this.panelId;
    heading.textContent = "Couldn't read this image";

    var body = doc.createElement('div');
    body.className = 'visual-panel__fallback-body';

    var meta = doc.createElement('div');
    meta.className = 'visual-panel__fallback-meta';
    meta.hidden = true;

    var note = doc.createElement('div');
    note.className = 'visual-panel__fallback-note';
    note.hidden = true;
    note.setAttribute('role', 'status');
    note.setAttribute('aria-live', 'polite');

    var actions = doc.createElement('div');
    actions.className = 'visual-panel__fallback-actions';

    var startBtn = doc.createElement('button');
    startBtn.type = 'button';
    startBtn.className = 'visual-panel__fallback-btn visual-panel__fallback-btn--primary';
    startBtn.setAttribute('data-action', 'start_tracing');
    startBtn.textContent = 'Start tracing';

    var queueBtn = doc.createElement('button');
    queueBtn.type = 'button';
    queueBtn.className = 'visual-panel__fallback-btn';
    queueBtn.setAttribute('data-action', 'queue_for_later');
    queueBtn.textContent = 'Queue for later';

    var dismissBtn = doc.createElement('button');
    dismissBtn.type = 'button';
    dismissBtn.className = 'visual-panel__fallback-btn visual-panel__fallback-btn--muted';
    dismissBtn.setAttribute('data-action', 'dismiss');
    dismissBtn.textContent = 'Dismiss';

    actions.appendChild(startBtn);
    actions.appendChild(queueBtn);
    actions.appendChild(dismissBtn);

    card.appendChild(heading);
    card.appendChild(body);
    card.appendChild(meta);
    card.appendChild(note);
    card.appendChild(actions);
    overlay.appendChild(card);
    this.el.appendChild(overlay);

    this._fallbackOverlayEl = overlay;
    this._fallbackBodyEl    = body;
    this._fallbackMetaEl    = meta;
    this._fallbackNoteEl    = note;
    this._fallbackActionsEl = actions;
    this._fallbackStartBtn  = startBtn;
    this._fallbackQueueBtn  = queueBtn;
    this._fallbackDismissBtn = dismissBtn;

    var self = this;
    this._onFallbackAction = function (e) {
      var btn = e.target && e.target.closest && e.target.closest('.visual-panel__fallback-btn');
      if (!btn || !actions.contains(btn)) return;
      var action = btn.getAttribute('data-action');
      self._handleFallbackAction(action);
    };
    actions.addEventListener('click', this._onFallbackAction);
  };

  /**
   * Write the alert payload's user-facing fields into the overlay DOM.
   * Called each time showFallbackPrompt() runs so a new alert replaces the
   * previous content (if any).
   */
  VisualPanel.prototype._populateFallbackOverlay = function (alert) {
    if (!this._fallbackOverlayEl) return;
    // Body — the user-facing prompt from the server (fallback to a local
    // default so the overlay is always intelligible).
    var msg = (alert && alert.user_message)
      ? alert.user_message
      : "I couldn't extract structure from your image. Trace the key "
        + "elements manually, or queue for a vision-capable model.";
    this._fallbackBodyEl.textContent = msg;

    // Meta — only shown when we have something useful to show.
    var metaBits = [];
    if (alert && alert.reason) {
      metaBits.push('Reason: ' + String(alert.reason).replace(/_/g, ' '));
    }
    if (alert && alert.extractor_attempted) {
      metaBits.push('Tried: ' + String(alert.extractor_attempted));
    }
    if (alert && Array.isArray(alert.parse_errors) && alert.parse_errors.length > 0) {
      var first = String(alert.parse_errors[0] || '').slice(0, 120);
      if (first) metaBits.push('Parse error: ' + first);
    }
    if (metaBits.length > 0) {
      this._fallbackMetaEl.textContent = metaBits.join('  \u2022  ');
      this._fallbackMetaEl.hidden = false;
    } else {
      this._fallbackMetaEl.textContent = '';
      this._fallbackMetaEl.hidden = true;
    }

    // Reset any stale status note from a prior interaction.
    if (this._fallbackNoteEl) {
      this._fallbackNoteEl.textContent = '';
      this._fallbackNoteEl.hidden = true;
    }

    // Hide irrelevant buttons when the server advertises a restricted action
    // set. Default (all three) is the expected path.
    var actionSet = (alert && Array.isArray(alert.actions) && alert.actions.length > 0)
      ? alert.actions
      : ['start_tracing', 'queue_for_later', 'dismiss'];
    this._fallbackStartBtn.hidden   = actionSet.indexOf('start_tracing') < 0;
    this._fallbackQueueBtn.hidden   = actionSet.indexOf('queue_for_later') < 0;
    this._fallbackDismissBtn.hidden = actionSet.indexOf('dismiss') < 0;
  };

  /**
   * Route a clicked action to the correct handler.
   */
  VisualPanel.prototype._handleFallbackAction = function (action) {
    if (action === 'start_tracing') {
      // Select the rect tool (the canonical "trace something" affordance
      // from WP-3.1) and focus the stage so the user can start drawing
      // immediately. Dismiss overlay.
      if (typeof this.setActiveTool === 'function') {
        this.setActiveTool('rect');
      }
      try { this.el.focus(); } catch (e) { /* ignore */ }
      this.dismissFallbackPrompt();
    } else if (action === 'queue_for_later') {
      this._queueForRetry(this._fallbackAlert);
    } else if (action === 'dismiss') {
      this.dismissFallbackPrompt();
    }
  };

  /**
   * POST {conversation_id, image_path, attempt_reason} to /chat/queue-retry.
   * The image_path is resolved from either (a) the alert payload (if set by
   * a future server extension) or (b) the currently-attached pending image.
   * Fail-open: network errors surface a small inline note in the overlay,
   * they do NOT re-open the overlay or lose user state elsewhere.
   */
  VisualPanel.prototype._queueForRetry = function (alert) {
    var self = this;
    var conversationId = (alert && alert.conversation_id)
      ? alert.conversation_id
      : (this.panelId || 'main');
    var attemptReason = (alert && alert.reason) ? alert.reason : 'extraction_failed';

    // Pull an image_path reference. Server-side the signal is the image
    // we uploaded; the client's pending image is the closest reference.
    // For the multipart pipeline the server already stashed the file under
    // ~/ora/sessions/<convo>/uploads/, but the client doesn't see that
    // path — so we send the pending image's name and the server's handler
    // can match by conversation_id + name, OR accept whatever path the
    // retry daemon chooses to resolve it into.
    var imagePath = null;
    if (alert && alert.image_path) {
      imagePath = alert.image_path;
    } else if (this._pendingImage && this._pendingImage.name) {
      // Prefix with the conversation slug so the daemon can locate the file
      // without a filesystem scan. The server accepts any non-empty string.
      imagePath = this._pendingImage.name;
    } else {
      imagePath = 'unknown';
    }

    var payload = {
      conversation_id: conversationId,
      image_path: imagePath,
      attempt_reason: attemptReason,
    };

    // Show a pending note while the POST is in flight.
    if (this._fallbackNoteEl) {
      this._fallbackNoteEl.textContent = 'Queueing\u2026';
      this._fallbackNoteEl.hidden = false;
    }

    var fetchFn = (typeof window !== 'undefined' && window.fetch)
      ? window.fetch.bind(window)
      : (typeof fetch === 'function' ? fetch : null);

    if (!fetchFn) {
      // No fetch available (exotic jsdom). Surface an inline failure and
      // dismiss so the user isn't stuck.
      if (self._fallbackNoteEl) {
        self._fallbackNoteEl.textContent = 'Queue unavailable (no fetch).';
      }
      setTimeout(function () { self.dismissFallbackPrompt(); }, 600);
      return null;
    }

    return fetchFn('/chat/queue-retry', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(function (resp) {
      return resp.json().catch(function () { return null; }).then(function (body) {
        return { ok: resp.ok, body: body };
      });
    }).then(function (outcome) {
      if (outcome && outcome.ok && outcome.body && outcome.body.queued) {
        var size = outcome.body.queue_size;
        if (self._fallbackNoteEl) {
          self._fallbackNoteEl.textContent = 'Queued. ' + size + ' pending.';
        }
        // Brief inline success note; dismiss after a short delay so the user
        // can read it. Keeps the overlay non-sticky.
        setTimeout(function () { self.dismissFallbackPrompt(); }, 900);
      } else {
        if (self._fallbackNoteEl) {
          self._fallbackNoteEl.textContent = 'Queue failed. Please try again.';
        }
      }
      return outcome;
    }).catch(function (err) {
      if (self._fallbackNoteEl) {
        self._fallbackNoteEl.textContent = 'Queue request failed: '
          + (err && err.message ? err.message : 'network error');
      }
      return null;
    });
  };

  // ══════════════════════════════════════════════════════════════════════════
  // WP-5.1 — User annotation tools (callout / highlight / strikethrough /
  //          sticky / pen)
  // ══════════════════════════════════════════════════════════════════════════
  //
  // These tools let the USER author annotations onto a rendered artifact,
  // distinct from the model-emitted overlays of WP-2.4. Every user
  // annotation is a Konva.Group (or line) on annotationLayer, carrying:
  //
  //   annotationSource:    'user'               (filter discriminator)
  //   annotationKind:      'callout'|'highlight'|'strikethrough'|'sticky'|'pen'
  //   userAnnotationId:    'ua-<kind>-<n>'      (monotonic per panel)
  //   targetId:            '<svg id>' | null    (anchor, or null for free)
  //   text:                '<string>'           (callout / sticky)
  //   position:            {x, y}               (sticky free-position)
  //   points:              [x1,y1,x2,y2,...]    (pen)
  //
  // WP-5.2 consumes via getUserAnnotations() → returns a flat array.

  /**
   * Route a Konva mousedown on the stage to the correct per-tool handler.
   * Called from _onStageDown when the active tool is in ANNOTATION_TOOLS.
   */
  VisualPanel.prototype._onAnnotationDown = function (e) {
    var tool = this._activeTool;
    if (tool === 'callout')       { this._onCalloutDown(e);       return; }
    if (tool === 'highlight')     { this._onHighlightDown(e);     return; }
    if (tool === 'strikethrough') { this._onStrikethroughDown(e); return; }
    if (tool === 'sticky')        { this._onStickyDown(e);        return; }
    if (tool === 'pen')           { this._onPenDown(e);           return; }
  };

  /**
   * Given a Konva event, walk the underlying SVG DOM at the pointer's
   * viewport position to resolve the semantic element id, if any. Returns
   * { id, kind } where `kind` is 'element' | 'edge' | null.
   *
   * Why this approach: the Konva stage sits ABOVE the SVG host (WP-2.1
   * DOM-overlay architecture). A Konva event doesn't carry the SVG DOM
   * target — we re-walk from the page-coordinate mouse position through
   * `document.elementFromPoint` (or via _svgHost.querySelector if that
   * API is unavailable in the environment). The returned id is the
   * nearest ancestor with an id attribute and a class starting with
   * `ora-visual__`.
   */
  VisualPanel.prototype._resolveSvgTarget = function (e) {
    if (!this._svgHost) return { id: null, kind: null };
    var evt = e && e.evt;
    var doc = this.el && this.el.ownerDocument;
    // Prefer document.elementFromPoint (pointer-at-coord). Fall back to
    // the Konva event's original DOM target when the stage event carries
    // it. In jsdom elementFromPoint often returns null — tests can exercise
    // the programmatic _createUserAnnotation path to bypass DOM walking.
    var domTarget = null;
    if (evt && typeof evt.clientX === 'number' && doc && doc.elementFromPoint) {
      try { domTarget = doc.elementFromPoint(evt.clientX, evt.clientY); }
      catch (ex) { domTarget = null; }
    }
    if (!domTarget && evt && evt.target && evt.target.nodeType === 1) {
      domTarget = evt.target;
    }
    if (!domTarget) return { id: null, kind: null };

    // Walk up to find an element with an id AND a class starting with
    // "ora-visual__" (the renderer convention). Also track whether any
    // ancestor is an edge/line element so strikethrough can validate.
    var node = domTarget;
    var kind = null;
    var id = null;
    while (node && node !== this._svgHost && node.nodeType === 1) {
      var cls = (node.getAttribute && node.getAttribute('class')) || '';
      var tag = (node.tagName || '').toLowerCase();
      // Edge detection: class contains "__edge" or tag is line/path under
      // an __edge ancestor.
      if (!kind) {
        if (/__edge/.test(cls)) kind = 'edge';
        else if (tag === 'line') kind = 'edge';
      }
      if (!id && node.hasAttribute && node.hasAttribute('id') &&
          /ora-visual__/.test(cls)) {
        id = node.getAttribute('id');
        if (!kind) kind = 'element';
      }
      node = node.parentNode;
    }
    return { id: id, kind: kind };
  };

  /**
   * Callout mousedown: open inline input near the pointer. On commit (Enter
   * or blur with a non-empty value), create a callout group anchored to the
   * resolved SVG target (if any) or to the free click point.
   */
  VisualPanel.prototype._onCalloutDown = function (e) {
    var p = this._stagePoint();
    var resolved = this._resolveSvgTarget(e);
    var self = this;
    this._openAnnotationInput(p.x, p.y, function (value) {
      self._createUserAnnotation('callout', {
        text: value,
        targetId: resolved.id || null,
        position: { x: p.x, y: p.y },
      });
    });
  };

  /**
   * Highlight mousedown: target MUST be a semantic element. Empty-space
   * clicks yield an inline hint and no-op.
   */
  VisualPanel.prototype._onHighlightDown = function (e) {
    var resolved = this._resolveSvgTarget(e);
    if (!resolved.id) {
      this._showAnnotationHint('Highlight targets must be on a diagram element.');
      return;
    }
    this._createUserAnnotation('highlight', { targetId: resolved.id });
  };

  /**
   * Strikethrough mousedown: target MUST be an edge/line element.
   * Non-edge clicks yield an inline hint and no-op.
   */
  VisualPanel.prototype._onStrikethroughDown = function (e) {
    var resolved = this._resolveSvgTarget(e);
    if (!resolved.id || resolved.kind !== 'edge') {
      this._showAnnotationHint('Strikethrough targets must be an edge or line.');
      return;
    }
    this._createUserAnnotation('strikethrough', { targetId: resolved.id });
  };

  /**
   * Sticky mousedown: open inline input; on commit, create a free-floating
   * yellow sticky at the click point. Never anchors to an element.
   */
  VisualPanel.prototype._onStickyDown = function (e) {
    var p = this._stagePoint();
    var self = this;
    this._openAnnotationInput(p.x, p.y, function (value) {
      self._createUserAnnotation('sticky', {
        text: value,
        position: { x: p.x, y: p.y },
      });
    });
  };

  /**
   * Pen mousedown: start a freehand stroke. Subsequent mousemoves extend
   * the line's points; mouseup commits.
   */
  VisualPanel.prototype._onPenDown = function (e) {
    if (typeof Konva === 'undefined' || !this.annotationLayer) return;
    var p = this._stagePoint();
    var line = new Konva.Line({
      points: [p.x, p.y],
      stroke: '#1a1a1a',
      strokeWidth: 2,
      lineCap: 'round',
      lineJoin: 'round',
      listening: false,
      name: 'vp-pen-preview',
    });
    this.annotationLayer.add(line);
    this.annotationLayer.batchDraw();
    this._penContext = { line: line };
  };

  VisualPanel.prototype._extendPenStroke = function () {
    var ctx = this._penContext;
    if (!ctx || !ctx.line) return;
    var p = this._stagePoint();
    var pts = ctx.line.points().slice();
    pts.push(p.x, p.y);
    ctx.line.points(pts);
    this.annotationLayer.batchDraw();
  };

  VisualPanel.prototype._commitPenStroke = function () {
    var ctx = this._penContext;
    this._penContext = null;
    if (!ctx || !ctx.line) return;
    var pts = ctx.line.points().slice();
    try { ctx.line.destroy(); } catch (err) { /* ignore */ }
    if (pts.length < 4) {
      // Too short to keep — single point tap is not a stroke.
      if (this.annotationLayer) this.annotationLayer.draw();
      return;
    }
    this._createUserAnnotation('pen', { points: pts });
  };

  VisualPanel.prototype._cancelPenStroke = function () {
    var ctx = this._penContext;
    this._penContext = null;
    if (ctx && ctx.line) {
      try { ctx.line.destroy(); } catch (err) { /* ignore */ }
      if (this.annotationLayer) this.annotationLayer.draw();
    }
  };

  /**
   * Open the inline input used by callout + sticky tools. Positioned in
   * viewport coords at the given stage-space point. Invokes `onCommit(value)`
   * with the typed text when the user presses Enter or blurs with a
   * non-empty value. Escape dismisses without committing.
   */
  VisualPanel.prototype._openAnnotationInput = function (x, y, onCommit) {
    if (!this._viewportEl) return;
    this._dismissAnnotationInput();
    var doc = this.el.ownerDocument || document;
    var input = doc.createElement('input');
    input.type = 'text';
    input.className = 'vp-annotation-input';
    input.id = 'vp-annotation-input-' + this.panelId;
    var t = this._transform || { x: 0, y: 0, scale: 1 };
    var vx = x * t.scale + t.x;
    var vy = y * t.scale + t.y;
    input.style.position = 'absolute';
    input.style.left = vx + 'px';
    input.style.top  = vy + 'px';
    this._viewportEl.appendChild(input);
    this._annotInputEl = input;
    var self = this;
    var committed = false;
    var commit = function () {
      if (committed) return;
      committed = true;
      var value = (self._annotInputEl && self._annotInputEl.value) || '';
      self._dismissAnnotationInput();
      if (value.length > 0 && typeof onCommit === 'function') {
        onCommit(value);
      }
    };
    input.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') { ev.preventDefault(); commit(); }
      else if (ev.key === 'Escape') { ev.preventDefault(); self._dismissAnnotationInput(); }
    });
    input.addEventListener('blur', commit);
    try { input.focus(); } catch (ex) { /* jsdom may reject */ }
  };

  VisualPanel.prototype._dismissAnnotationInput = function () {
    if (this._annotInputEl && this._annotInputEl.parentNode) {
      try { this._annotInputEl.parentNode.removeChild(this._annotInputEl); }
      catch (err) { /* ignore */ }
    }
    this._annotInputEl = null;
  };

  /**
   * Show a non-blocking inline hint (e.g. "Highlight targets must be on a
   * diagram element."). Auto-hides after ANNOTATION_HINT_AUTOHIDE_MS.
   */
  VisualPanel.prototype._showAnnotationHint = function (msg) {
    if (!this._annotHintEl) return;
    this._annotHintEl.textContent = msg || '';
    this._annotHintEl.hidden = false;
    if (this._annotHintTimeout) {
      try { clearTimeout(this._annotHintTimeout); } catch (e) { /* ignore */ }
    }
    var self = this;
    this._annotHintTimeout = setTimeout(function () {
      self._hideAnnotationHint();
    }, ANNOTATION_HINT_AUTOHIDE_MS);
  };

  VisualPanel.prototype._hideAnnotationHint = function () {
    if (!this._annotHintEl) return;
    this._annotHintEl.hidden = true;
    this._annotHintEl.textContent = '';
    if (this._annotHintTimeout) {
      try { clearTimeout(this._annotHintTimeout); } catch (e) { /* ignore */ }
      this._annotHintTimeout = null;
    }
  };

  /**
   * Programmatically create a user annotation. The public API for tests
   * and for WP-5.2 replay. Returns the created Konva node (Group or Line).
   *
   * @param {string} kind   'callout' | 'highlight' | 'strikethrough' |
   *                        'sticky' | 'pen'
   * @param {object} params Kind-specific:
   *   callout:       { text, targetId?, position? {x,y} }
   *   highlight:     { targetId }
   *   strikethrough: { targetId }
   *   sticky:        { text, position {x,y} }
   *   pen:           { points: [x1,y1,...] }
   */
  VisualPanel.prototype._createUserAnnotation = function (kind, params) {
    if (typeof Konva === 'undefined' || !this.annotationLayer) return null;
    if (!ANNOTATION_TOOLS[kind]) return null;
    params = params || {};
    var id = 'ua-' + kind + '-' + (++this._userAnnotCounter);
    var node = null;

    if (kind === 'callout') {
      node = this._buildCalloutNode(id, params);
    } else if (kind === 'highlight') {
      node = this._buildHighlightNode(id, params);
    } else if (kind === 'strikethrough') {
      node = this._buildStrikethroughNode(id, params);
    } else if (kind === 'sticky') {
      node = this._buildStickyNode(id, params);
    } else if (kind === 'pen') {
      node = this._buildPenNode(id, params);
    }
    if (!node) return null;

    // Universal attrs (preserved by toJSON; null keys written direct).
    node.setAttrs({
      annotationSource:   'user',
      annotationKind:     kind,
      userAnnotationId:   id,
    });
    node.attrs.targetId = (params.targetId != null) ? params.targetId : null;
    if (kind === 'callout' || kind === 'sticky') {
      node.attrs.text = (params.text != null) ? params.text : '';
    }
    if (kind === 'sticky' || kind === 'callout') {
      var pos = params.position || null;
      node.attrs.position = pos ? { x: pos.x, y: pos.y } : null;
    }
    if (kind === 'pen') {
      node.attrs.points = (params.points || []).slice();
    }

    this.annotationLayer.add(node);
    this.annotationLayer.draw();

    // Wire drag-end history for draggable annotations (sticky, callout).
    if (node.draggable && node.draggable()) {
      var self = this;
      node.on('dragstart.vp5', function () {
        node._vpPrevPos = { x: node.x(), y: node.y() };
      });
      node.on('dragend.vp5', function () {
        if (self._suppressHistory) return;
        var prev = node._vpPrevPos || { x: 0, y: 0 };
        var curr = { x: node.x(), y: node.y() };
        var nid = node.getAttr('userAnnotationId');
        // Update stored position attr to the new location.
        node.attrs.position = { x: curr.x, y: curr.y };
        self._pushHistory({
          label: 'annot-move',
          undoFn: function () { self._setAnnotationPos(nid, prev.x, prev.y); },
          redoFn: function () { self._setAnnotationPos(nid, curr.x, curr.y); },
        });
        node._vpPrevPos = curr;
      });
    }

    if (!this._suppressHistory) {
      var serialized = node.toJSON();
      var selfH = this;
      this._pushHistory({
        label: 'annot-create:' + kind,
        undoFn: function () { selfH._removeAnnotationById(id); },
        redoFn: function () { selfH._reinsertAnnotationJSON(serialized); },
      });
    }
    return node;
  };

  /**
   * Build a callout Konva.Group: rounded rect + text + optional stem to
   * the anchor. Group is draggable if there's no targetId.
   */
  VisualPanel.prototype._buildCalloutNode = function (id, params) {
    var text = (params.text || '');
    var padding = 6;
    var approxW = Math.max(60, text.length * 7 + padding * 2);
    var approxH = 22;

    // Anchor: if a targetId resolves to a bbox, anchor the bubble near it;
    // otherwise, use params.position (the free-click point).
    var anchor = null;
    if (params.targetId) {
      var box = this._computeTargetBox(params.targetId);
      if (box) {
        anchor = { x: box.x + box.width + 8, y: box.y - approxH - 4 };
        if (anchor.y < 0) anchor.y = box.y + box.height + 4;
      }
    }
    if (!anchor) {
      var pos = params.position || { x: 0, y: 0 };
      anchor = { x: pos.x, y: pos.y };
    }

    var group = new Konva.Group({
      x: anchor.x,
      y: anchor.y,
      draggable: params.targetId ? false : true,
      name: 'vp-user-callout-' + id,
    });
    group.add(new Konva.Rect({
      x: 0, y: 0, width: approxW, height: approxH,
      fill: '#ffffff',
      stroke: '#b0a8a0',
      strokeWidth: 1,
      cornerRadius: 4,
      shadowColor: 'rgba(0,0,0,0.15)',
      shadowBlur: 4,
      shadowOffset: { x: 0, y: 1 },
      name: 'ora-visual__user-callout',
    }));
    group.add(new Konva.Text({
      x: padding, y: padding,
      text: text,
      fontSize: 11,
      fill: '#1a1a1a',
      name: 'ora-visual__user-callout-text',
    }));
    // Stem: if anchored, draw a short line from the bubble corner toward
    // the target's bbox top-left.
    if (params.targetId) {
      var tbox = this._computeTargetBox(params.targetId);
      if (tbox) {
        // group coords are absolute; stem points are relative to the group.
        var stemEndX = (tbox.x + tbox.width / 2) - anchor.x;
        var stemEndY = (tbox.y + tbox.height / 2) - anchor.y;
        group.add(new Konva.Line({
          points: [0, approxH, stemEndX, stemEndY],
          stroke: '#b0a8a0',
          strokeWidth: 1,
          dash: [3, 3],
          name: 'ora-visual__user-callout-stem',
        }));
      }
    }
    return group;
  };

  /**
   * Build a highlight: dashed stroke rect around a target bbox, with a
   * pulsing animation.
   */
  VisualPanel.prototype._buildHighlightNode = function (id, params) {
    var box = this._computeTargetBox(params.targetId);
    if (!box) {
      // Still create a placeholder so tests/consumers can observe the
      // attribute contract. Use a tiny rect at (0,0). The annotation will
      // not be visible until the target resolves, which is acceptable —
      // this is a defensive fallback for test environments.
      box = { x: 0, y: 0, width: 40, height: 20 };
    }
    var pad = 4;
    var ring = new Konva.Rect({
      x: box.x - pad, y: box.y - pad,
      width: box.width + pad * 2,
      height: box.height + pad * 2,
      stroke: '#0072B2',
      strokeWidth: 3,
      dash: [6, 4],
      listening: true,
      opacity: 0.8,
      name: 'ora-visual__user-highlight vp-user-highlight-' + id,
    });
    // Subtle pulse — a no-op in jsdom (no RAF-driven redraw), so tests
    // observe a static ring.
    try {
      var anim = new Konva.Animation(function (frame) {
        var t = (frame && frame.time) || 0;
        ring.opacity(0.5 + 0.4 * Math.abs(Math.sin(t / 350)));
      }, this.annotationLayer);
      ring._vpAnimation = anim;
      if (anim.start) anim.start();
    } catch (e) { /* animations disabled (jsdom) */ }
    return ring;
  };

  /**
   * Build a strikethrough: a thick diagonal line across the target bbox.
   */
  VisualPanel.prototype._buildStrikethroughNode = function (id, params) {
    var box = this._computeTargetBox(params.targetId);
    if (!box) {
      // Placeholder geometry for test environments (target may not resolve
      // via jsdom's getBBox when the renderer hasn't actually emitted SVG).
      box = { x: 0, y: 0, width: 60, height: 30 };
    }
    var line = new Konva.Line({
      points: [box.x, box.y, box.x + box.width, box.y + box.height],
      stroke: '#a12c14',
      strokeWidth: 3,
      lineCap: 'round',
      listening: true,
      name: 'ora-visual__user-strikethrough vp-user-strike-' + id,
    });
    return line;
  };

  /**
   * Build a sticky note: yellow rect + text, free-position, draggable.
   */
  VisualPanel.prototype._buildStickyNode = function (id, params) {
    var text = params.text || '';
    var pos  = params.position || { x: 0, y: 0 };
    var approxW = Math.max(100, Math.min(220, text.length * 7 + 20));
    var approxH = Math.max(60, Math.ceil(text.length / 24) * 16 + 24);
    var group = new Konva.Group({
      x: pos.x,
      y: pos.y,
      draggable: true,
      name: 'vp-user-sticky-' + id,
    });
    group.add(new Konva.Rect({
      x: 0, y: 0, width: approxW, height: approxH,
      fill: '#fff6a8',
      stroke: '#c5b87a',
      strokeWidth: 1,
      cornerRadius: 2,
      shadowColor: 'rgba(0,0,0,0.18)',
      shadowBlur: 6,
      shadowOffset: { x: 1, y: 2 },
      name: 'ora-visual__user-sticky',
    }));
    group.add(new Konva.Text({
      x: 8, y: 8,
      width: approxW - 16,
      text: text,
      fontSize: 12,
      fill: '#3a3200',
      name: 'ora-visual__user-sticky-text',
    }));
    return group;
  };

  /**
   * Build a pen stroke: Konva.Line with rounded joins.
   */
  VisualPanel.prototype._buildPenNode = function (id, params) {
    var pts = (params.points && params.points.length >= 2) ? params.points.slice() : [0, 0];
    var line = new Konva.Line({
      points: pts,
      stroke: '#1a1a1a',
      strokeWidth: 2,
      lineCap: 'round',
      lineJoin: 'round',
      listening: true,
      name: 'ora-visual__user-pen vp-user-pen-' + id,
    });
    return line;
  };

  /**
   * Locate a user annotation by id.
   */
  VisualPanel.prototype._findAnnotationById = function (id) {
    if (!this.annotationLayer) return null;
    var children = this.annotationLayer.getChildren();
    for (var i = 0; i < children.length; i++) {
      if (children[i].getAttr('userAnnotationId') === id) return children[i];
    }
    return null;
  };

  VisualPanel.prototype._setAnnotationPos = function (id, x, y) {
    var node = this._findAnnotationById(id);
    if (!node) return;
    node.position({ x: x, y: y });
    node.attrs.position = { x: x, y: y };
    if (this.annotationLayer) this.annotationLayer.draw();
  };

  VisualPanel.prototype._removeAnnotationById = function (id) {
    var node = this._findAnnotationById(id);
    if (node) {
      try {
        if (node._vpAnimation && node._vpAnimation.stop) node._vpAnimation.stop();
      } catch (e) { /* ignore */ }
      try { node.destroy(); } catch (e) { /* ignore */ }
    }
    this._selectedAnnotIds = this._selectedAnnotIds.filter(function (x) { return x !== id; });
    this._redrawAnnotationSelection();
    if (this.annotationLayer) this.annotationLayer.draw();
  };

  /**
   * Rehydrate a user annotation from its toJSON blob (used by undo of
   * delete). We rewire the drag + animation hooks that Konva doesn't
   * serialize.
   */
  VisualPanel.prototype._reinsertAnnotationJSON = function (json) {
    if (typeof Konva === 'undefined' || !this.annotationLayer) return null;
    var node;
    try { node = Konva.Node.create(json); }
    catch (err) { return null; }
    if (!node) return null;
    this.annotationLayer.add(node);
    // Re-wire drag + animation where appropriate.
    var kind = node.getAttr('annotationKind');
    if (kind === 'sticky' || (kind === 'callout' && node.draggable && node.draggable())) {
      var self = this;
      node.draggable(true);
      node.on('dragstart.vp5', function () { node._vpPrevPos = { x: node.x(), y: node.y() }; });
      node.on('dragend.vp5', function () {
        if (self._suppressHistory) return;
        var prev = node._vpPrevPos || { x: 0, y: 0 };
        var curr = { x: node.x(), y: node.y() };
        var nid = node.getAttr('userAnnotationId');
        node.attrs.position = { x: curr.x, y: curr.y };
        self._pushHistory({
          label: 'annot-move',
          undoFn: function () { self._setAnnotationPos(nid, prev.x, prev.y); },
          redoFn: function () { self._setAnnotationPos(nid, curr.x, curr.y); },
        });
        node._vpPrevPos = curr;
      });
    }
    if (kind === 'highlight') {
      try {
        var anim = new Konva.Animation(function (frame) {
          var t = (frame && frame.time) || 0;
          node.opacity(0.5 + 0.4 * Math.abs(Math.sin(t / 350)));
        }, this.annotationLayer);
        node._vpAnimation = anim;
        if (anim.start) anim.start();
      } catch (e) { /* ignore */ }
    }
    this.annotationLayer.draw();
    return node;
  };

  /**
   * Delete a user annotation by id, with history.
   */
  VisualPanel.prototype._deleteAnnotation = function (id) {
    var node = this._findAnnotationById(id);
    if (!node) return false;
    var serialized = node.toJSON();
    try {
      if (node._vpAnimation && node._vpAnimation.stop) node._vpAnimation.stop();
    } catch (e) { /* ignore */ }
    try { node.destroy(); } catch (e) { /* ignore */ }
    this._selectedAnnotIds = this._selectedAnnotIds.filter(function (x) { return x !== id; });
    this._redrawAnnotationSelection();
    if (this.annotationLayer) this.annotationLayer.draw();

    if (!this._suppressHistory) {
      var self = this;
      this._pushHistory({
        label: 'annot-delete',
        undoFn: function () { self._reinsertAnnotationJSON(serialized); },
        redoFn: function () { self._removeAnnotationById(id); },
      });
    }
    return true;
  };

  /**
   * Redraw the selection rings for selected user annotations onto
   * selectionLayer. Pairs with _redrawSelection (user shapes).
   */
  VisualPanel.prototype._redrawAnnotationSelection = function () {
    if (!this.selectionLayer || typeof Konva === 'undefined') return;
    var rings = this.selectionLayer.find('.vp-annot-selection');
    for (var i = 0; i < rings.length; i++) rings[i].destroy();

    for (var j = 0; j < this._selectedAnnotIds.length; j++) {
      var id = this._selectedAnnotIds[j];
      var node = this._findAnnotationById(id);
      if (!node) continue;
      var box;
      try { box = node.getClientRect({ relativeTo: this.annotationLayer }); }
      catch (err) { box = null; }
      if (!box) continue;
      var ring = new Konva.Rect({
        x: box.x - 4, y: box.y - 4,
        width: box.width + 8, height: box.height + 8,
        stroke: '#E69F00', strokeWidth: 2, dash: [4, 3],
        listening: false,
        name: 'vp-annot-selection',
      });
      this.selectionLayer.add(ring);
    }
    this.selectionLayer.draw();
  };

  /**
   * Public API: delete every currently-selected user annotation.
   */
  VisualPanel.prototype.deleteSelectedAnnotations = function () {
    if (!this._selectedAnnotIds || this._selectedAnnotIds.length === 0) return;
    var ids = this._selectedAnnotIds.slice();
    for (var i = 0; i < ids.length; i++) this._deleteAnnotation(ids[i]);
    this._selectedAnnotIds = [];
    this._redrawAnnotationSelection();
  };

  /**
   * Public API: return the list of user annotations currently on
   * annotationLayer. Filters by annotationSource='user' so model-emitted
   * annotations (WP-2.4) are excluded. Shape matches WP-5.2's contract.
   *
   * @returns {Array<{id, kind, targetId, text, position, points}>}
   */
  VisualPanel.prototype.getUserAnnotations = function () {
    var out = [];
    if (!this.annotationLayer) return out;
    var children = this.annotationLayer.getChildren();
    for (var i = 0; i < children.length; i++) {
      var c = children[i];
      if (c.getAttr('annotationSource') !== 'user') continue;
      var record = {
        id:        c.getAttr('userAnnotationId') || null,
        kind:      c.getAttr('annotationKind')    || null,
        targetId:  (c.getAttr('targetId') != null) ? c.getAttr('targetId') : null,
        text:      (c.getAttr('text') != null) ? c.getAttr('text') : null,
        position:  c.getAttr('position') || null,
        points:    c.getAttr('points')   || null,
      };
      // Sticky/callout carry live position from the Konva node (a
      // free-dragged sticky's position attr is updated on dragend, but be
      // defensive for environments that don't fire drag events).
      if (record.kind === 'sticky' || record.kind === 'callout') {
        var livePos = { x: c.x(), y: c.y() };
        if (!record.position || (record.position.x !== livePos.x || record.position.y !== livePos.y)) {
          record.position = livePos;
        }
      }
      out.push(record);
    }
    return out;
  };

  /**
   * Public API: return the ids of currently-selected user annotations.
   */
  VisualPanel.prototype.getSelectedAnnotationIds = function () {
    return (this._selectedAnnotIds || []).slice();
  };

  // ── Exports ───────────────────────────────────────────────────────────────

  // Class export for the PANEL_CLASSES registry (index.html).
  window.VisualPanel = VisualPanel;

  // OraPanels registry (spec-requested surface) — exposes renderSpec /
  // clearArtifact against the most-recently-initialized instance so callers
  // that don't hold a direct class reference can interact with the panel.
  window.OraPanels = window.OraPanels || {};

  var _active = null;
  function _registerActive(instance) { _active = instance; }

  var origInit = VisualPanel.prototype.init;
  VisualPanel.prototype.init = function () {
    _registerActive(this);
    return origInit.apply(this, arguments);
  };
  var origDestroy = VisualPanel.prototype.destroy;
  VisualPanel.prototype.destroy = function () {
    if (_active === this) _active = null;
    return origDestroy.apply(this, arguments);
  };

  window.OraPanels.visual = {
    Class: VisualPanel,
    init: function (el, config) {
      var inst = new VisualPanel(el, config || {});
      inst.init();
      return inst;
    },
    // Dispatch helpers on the active instance. No-ops if no instance is mounted.
    destroy: function () { if (_active) _active.destroy(); },
    onBridgeUpdate: function (state) { if (_active) _active.onBridgeUpdate(state); },
    renderSpec: function (envelope) { return _active ? _active.renderSpec(envelope) : Promise.resolve(); },
    clearArtifact: function () { if (_active) _active.clearArtifact(); },
    // WP-3.1 surface
    setActiveTool: function (tool) { if (_active) _active.setActiveTool(tool); },
    getActiveTool: function () { return _active ? _active.getActiveTool() : null; },
    undo: function () { if (_active) _active.undo(); },
    redo: function () { if (_active) _active.redo(); },
    clearUserInput: function () { if (_active) _active.clearUserInput(); },
    // WP-4.1 surface
    attachImage:        function (file) { return _active ? _active.attachImage(file) : Promise.resolve(null); },
    getPendingImage:    function () { return _active ? _active.getPendingImage() : null; },
    clearPendingImage:  function () { if (_active) _active.clearPendingImage(); },
    // WP-4.4 surface
    showFallbackPrompt:    function (alert) { if (_active) _active.showFallbackPrompt(alert); },
    dismissFallbackPrompt: function () { if (_active) _active.dismissFallbackPrompt(); },
    // WP-5.1 surface — user annotations
    getUserAnnotations:          function () { return _active ? _active.getUserAnnotations() : []; },
    deleteSelectedAnnotations:   function () { if (_active) _active.deleteSelectedAnnotations(); },
    _getActive: function () { return _active; },
  };
})();
