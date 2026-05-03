/* lasso-selection.tool.js — WP-7.5.1c
 *
 * Free-form lasso selection tool for the visual pane. Conforms to the
 * tool-primitive contract from `Reference — Visual Pane Extension Points` §B.4:
 *
 *     { id, label, defaultIcon, init(panel, ctx),
 *       activate(ctx), deactivate(ctx), serializeState(state) }
 *
 * Behavior
 * --------
 * The user picks an image, activates the lasso, then traces a polygon using
 * either input style (auto-detected per stroke):
 *
 *   • Click points  — each mousedown/mouseup pair within a small movement
 *                     threshold counts as a vertex click. The polygon closes
 *                     when the user (a) double-clicks, or (b) clicks within
 *                     CLOSE_RADIUS of the first vertex.
 *   • Click-drag    — a continuous mousedown→drag→mouseup stroke produces a
 *                     freehand path. Vertices are sampled along the drag at
 *                     ≥ MIN_DRAG_SPACING px apart. Release closes the polygon.
 *
 * The two modes are NOT user-selectable; the tool decides on the fly. A press
 * that moves more than CLICK_DRAG_THRESHOLD pixels before release is a drag;
 * anything less is treated as a vertex click.
 *
 * Visual feedback
 * ---------------
 * Marching-ants outline drawn on `panel.selectionLayer`. Group name
 * `lasso-selection` so sibling WP-7.5.1a (rect) / WP-7.5.1b (brush) can
 * coexist — they should use their own named groups. Animation runs while
 * the tool is active and stops on deactivate / Escape / new-tool.
 *
 * Output
 * ------
 * On polygon close, dispatches a `user-input` CustomEvent on `panel.el` with
 * detail:
 *
 *   {
 *     source: 'lasso-selection',
 *     mask: {
 *       kind:                 'lasso_polygon',
 *       parent_image_id:      '<image id>',
 *       coordinate_space:     'image_local',  // origin = top-left of the image
 *       polygon:              [{x, y}, ...],   // ≥ 3 vertices, no duplicate
 *                                              //  consecutive points
 *       closed:               true,
 *       authored_at:          '<ISO 8601>'
 *     }
 *   }
 *
 * The mask is consumable by `image_edits` (WP-7.3.3b). The provider can
 * rasterize the polygon to a binary mask if its API requires that format
 * (the polygon is sufficient — image-local coords + the polygon-fill rule
 * uniquely determine the bitmap).
 *
 * The `kind` discriminator was chosen so rect (WP-7.5.1a) and brush
 * (WP-7.5.1b) can use the same envelope shape with different `kind` values
 * (`rect_bounds` and `raster_mask` respectively) — `image_edits` then
 * dispatches on `kind` to produce its provider-specific mask.
 *
 * Empty-selection behavior
 * ------------------------
 * Activating the lasso when no image is currently selected dispatches a
 * `tool-activation-error` CustomEvent and returns false (per the WP-7.5.1
 * "empty selection is an error state, not silent" constraint). Consumers
 * are expected to surface this to the user (e.g., toast / status bar).
 *
 * Foundation
 * ----------
 *   • visual-panel.js layers      (`stage`, `selectionLayer`, etc.)
 *   • visual-panel.js coords      (`_stagePoint`, `_transform`)
 *   • canvas-file-format.js       (`kind: 'image'` objects with `id`)
 *
 * The tool does NOT modify visual-panel.js. It self-registers on import via
 * the singleton's `register(panel, ctx)` helper, or can be wired into the
 * eventual auto-loader described in the §B.4 contract.
 */

'use strict';

(function (global) {

  // ── Tunables ──────────────────────────────────────────────────────────────

  // A stroke that travels less than this many pixels (Manhattan) between
  // mousedown and mouseup is a click, not a drag. Stroke deltas above the
  // threshold flip the stroke into freehand mode.
  var CLICK_DRAG_THRESHOLD = 6;

  // In freehand mode, sample a new vertex only when the pointer has moved
  // at least this many pixels from the last sampled point. Prevents bloated
  // polygons (one vertex per mousemove → thousands of vertices).
  var MIN_DRAG_SPACING = 4;

  // In click mode, a click within this many image-local pixels of the first
  // vertex closes the polygon. Generous so users don't have to land exactly.
  var CLOSE_RADIUS = 10;

  // Marching-ants visuals.
  var DASH_PATTERN  = [6, 4];
  var DASH_STROKE_PRIMARY   = '#ffffff';
  var DASH_STROKE_SECONDARY = '#0072B2';   // Ora primary blue
  var DASH_STROKE_WIDTH     = 1.5;
  var ANTS_SPEED_PX_PER_SEC = 30;          // dashOffset per second

  // ── Helpers ───────────────────────────────────────────────────────────────

  function manhattan(a, b) {
    return Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
  }

  function euclidean(a, b) {
    var dx = a.x - b.x, dy = a.y - b.y;
    return Math.sqrt(dx * dx + dy * dy);
  }

  function pointsToFlatArray(pts, closed) {
    var out = new Array(pts.length * 2 + (closed ? 2 : 0));
    for (var i = 0; i < pts.length; i++) {
      out[i * 2]     = pts[i].x;
      out[i * 2 + 1] = pts[i].y;
    }
    if (closed && pts.length > 0) {
      out[pts.length * 2]     = pts[0].x;
      out[pts.length * 2 + 1] = pts[0].y;
    }
    return out;
  }

  /**
   * Resolve which image the lasso should mask. Probes (in order):
   *   1) panel.getSelectedImageNode() — forward-compat hook.
   *   2) panel._selectedShapeIds → first id whose Konva node is an Image.
   *   3) panel._backgroundImageNode IF tagged with an `imageId` attr.
   * Returns { node, imageId, originX, originY } in stage/canvas coords, or
   * null when no image is selected.
   */
  function resolveSelectedImage(panel) {
    if (!panel) return null;

    // (1) Forward-compat hook.
    if (typeof panel.getSelectedImageNode === 'function') {
      try {
        var probe = panel.getSelectedImageNode();
        if (probe && probe.node) return probe;
      } catch (e) { /* fall through */ }
    }

    // (2) Selected-shapes path.
    var selIds = (panel._selectedShapeIds || []).slice();
    if (panel.userInputLayer && selIds.length > 0) {
      for (var i = 0; i < selIds.length; i++) {
        var id = selIds[i];
        var nodes;
        try {
          nodes = panel.userInputLayer.find('#' + id);
        } catch (e) {
          nodes = null;
        }
        if (nodes && nodes.length > 0) {
          var n = nodes[0];
          if (n && n.className === 'Image') {
            return {
              node:    n,
              imageId: id,
              originX: n.x() || 0,
              originY: n.y() || 0,
              width:   n.width()  || 0,
              height:  n.height() || 0,
            };
          }
        }
      }
    }

    // (3) Background image — only if it carries an imageId attr (i.e., the
    // background is a user image, not the SVG sentinel from the artifact).
    var bg = panel._backgroundImageNode;
    if (bg && typeof bg.getAttr === 'function') {
      var bgId = bg.getAttr('imageId');
      if (bgId) {
        return {
          node:    bg,
          imageId: bgId,
          originX: bg.x() || 0,
          originY: bg.y() || 0,
          width:   bg.width()  || 0,
          height:  bg.height() || 0,
        };
      }
    }

    return null;
  }

  /**
   * Convert a stage-space point to image-local space.
   */
  function stageToImageLocal(stagePt, image) {
    return {
      x: stagePt.x - image.originX,
      y: stagePt.y - image.originY,
    };
  }

  /**
   * Best-effort getter for a stage-space pointer position. Uses the panel's
   * own helper when available; otherwise falls back to Konva pointer +
   * panel transform.
   */
  function getStagePoint(panel) {
    if (typeof panel._stagePoint === 'function') {
      try { return panel._stagePoint(); } catch (e) { /* fall through */ }
    }
    if (!panel.stage) return { x: 0, y: 0 };
    var p = panel.stage.getPointerPosition() || { x: 0, y: 0 };
    var t = panel._transform || { x: 0, y: 0, scale: 1 };
    return {
      x: (p.x - t.x) / (t.scale || 1),
      y: (p.y - t.y) / (t.scale || 1),
    };
  }

  function nowIso() {
    try { return new Date().toISOString(); }
    catch (e) { return ''; }
  }

  function emit(panel, type, detail) {
    if (!panel || !panel.el || typeof panel.el.dispatchEvent !== 'function') return;
    try {
      var Ctor = (typeof CustomEvent === 'function') ? CustomEvent : null;
      var ev   = Ctor
        ? new Ctor(type, { detail: detail, bubbles: true })
        : { type: type, detail: detail };
      panel.el.dispatchEvent(ev);
    } catch (e) { /* swallow — event dispatch is best-effort */ }
  }

  // ── Tool implementation ───────────────────────────────────────────────────

  var Tool = {
    id:          'lasso-selection',
    label:       'Lasso',
    defaultIcon: 'lasso',  // Lucide icon name

    // ── Lifecycle ───────────────────────────────────────────────────────────

    init: function (panel, ctx) {
      this.panel = panel;
      this.ctx   = ctx || {};

      // Per-stroke state.
      this._image           = null;   // resolved selected image (resolveSelectedImage)
      this._vertices        = [];     // image-local vertices [{x, y}, ...]
      this._mode            = null;   // 'click' | 'drag' | null
      this._pressDown       = null;   // {x, y} stage-space at mousedown
      this._lastDragSample  = null;   // image-local last sampled point in drag mode
      this._isDragging      = false;  // drag in progress between down/up

      // Konva visual nodes (lazy).
      this._group           = null;
      this._lineWhite       = null;
      this._lineBlue        = null;
      this._anim            = null;

      // Bound event handlers (set on activate, cleared on deactivate).
      this._handlers        = null;

      this._active          = false;
    },

    /**
     * Activate the lasso. Returns true on success, false when no image is
     * selected (emits `tool-activation-error` so the host can surface it).
     */
    activate: function (ctx) {
      if (this._active) return true;
      var panel = this.panel;
      if (!panel || !panel.stage || !panel.selectionLayer) {
        emit(panel, 'tool-activation-error', {
          source: this.id,
          reason: 'panel-not-ready',
          message: 'Visual pane not initialised; cannot activate lasso.',
        });
        return false;
      }

      var image = resolveSelectedImage(panel);
      if (!image) {
        emit(panel, 'tool-activation-error', {
          source: this.id,
          reason: 'no-image-selected',
          message: 'Select an image before using the lasso.',
        });
        return false;
      }

      this._image = image;
      this._resetStrokeState();
      this._installListeners();
      this._ensureVisualGroup();
      this._startMarchingAnts();
      this._active = true;

      emit(panel, 'tool-activated', {
        source: this.id,
        parent_image_id: image.imageId,
      });
      return true;
    },

    deactivate: function (ctx) {
      if (!this._active) return;
      this._removeListeners();
      this._stopMarchingAnts();
      this._destroyVisualGroup();
      this._resetStrokeState();
      this._image  = null;
      this._active = false;

      emit(this.panel, 'tool-deactivated', { source: this.id });
    },

    /**
     * Snapshot of in-progress polygon state. Conforms to the §B.4 contract.
     * If a polygon is mid-draw, we report it as `in_progress: true` with the
     * vertices captured so far.
     */
    serializeState: function (state) {
      var inProgress = this._active && this._vertices.length > 0;
      return {
        in_progress: inProgress,
        parent_image_id: this._image ? this._image.imageId : null,
        partial_polygon: inProgress ? this._vertices.slice() : [],
        mode: this._mode,
      };
    },

    // ── Stroke state ────────────────────────────────────────────────────────

    _resetStrokeState: function () {
      this._vertices       = [];
      this._mode           = null;
      this._pressDown      = null;
      this._lastDragSample = null;
      this._isDragging     = false;
    },

    // ── Listeners ───────────────────────────────────────────────────────────

    _installListeners: function () {
      var self = this;
      var stage = this.panel.stage;
      var rootEl = (this.panel.el || (typeof document !== 'undefined' ? document : null));

      // We namespace stage events with `.lasso-selection` so deactivate can
      // remove them without touching siblings' listeners.
      var ns = '.' + this.id;

      this._handlers = {
        ns: ns,
        onDown: function (e) { self._onDown(e); },
        onMove: function (e) { self._onMove(e); },
        onUp:   function (e) { self._onUp(e);   },
        onDbl:  function (e) { self._onDoubleClick(e); },
        onKey:  function (e) { self._onKeyDown(e); },
      };

      stage.on('mousedown' + ns,  this._handlers.onDown);
      stage.on('touchstart' + ns, this._handlers.onDown);
      stage.on('mousemove' + ns,  this._handlers.onMove);
      stage.on('touchmove' + ns,  this._handlers.onMove);
      stage.on('mouseup' + ns,    this._handlers.onUp);
      stage.on('touchend' + ns,   this._handlers.onUp);
      stage.on('dblclick' + ns,   this._handlers.onDbl);
      stage.on('dbltap' + ns,     this._handlers.onDbl);

      if (rootEl && typeof rootEl.addEventListener === 'function') {
        rootEl.addEventListener('keydown', this._handlers.onKey);
      }
    },

    _removeListeners: function () {
      if (!this._handlers) return;
      var stage = this.panel && this.panel.stage;
      var rootEl = (this.panel && this.panel.el) ||
                   (typeof document !== 'undefined' ? document : null);
      var ns = this._handlers.ns;
      if (stage) stage.off(ns);
      if (rootEl && typeof rootEl.removeEventListener === 'function') {
        rootEl.removeEventListener('keydown', this._handlers.onKey);
      }
      this._handlers = null;
    },

    // ── Pointer handlers ───────────────────────────────────────────────────

    _onDown: function (e) {
      if (!this._active || !this._image) return;
      var stagePt = getStagePoint(this.panel);
      this._pressDown      = stagePt;
      this._isDragging     = true;
      this._lastDragSample = null;
      // We don't push a vertex yet — wait to see if this is a click or a
      // drag. (For freehand drag, the first vertex is added on the first
      // _onMove sample with sufficient travel; for clicks, on _onUp.)
    },

    _onMove: function (e) {
      if (!this._active || !this._image || !this._isDragging) return;
      var stagePt = getStagePoint(this.panel);
      var pressDown = this._pressDown;
      if (!pressDown) return;

      // Detect mode: once travel exceeds CLICK_DRAG_THRESHOLD, lock in 'drag'.
      if (this._mode == null) {
        if (manhattan(pressDown, stagePt) >= CLICK_DRAG_THRESHOLD) {
          this._mode = 'drag';
          // Seed the freehand polygon with the press-down point.
          var seed = stageToImageLocal(pressDown, this._image);
          this._vertices.push(seed);
          this._lastDragSample = seed;
          this._refreshPolyline();
        } else {
          // Still inside the click threshold; ignore the move.
          return;
        }
      }

      if (this._mode === 'drag') {
        var localPt = stageToImageLocal(stagePt, this._image);
        if (!this._lastDragSample ||
            euclidean(this._lastDragSample, localPt) >= MIN_DRAG_SPACING) {
          this._vertices.push(localPt);
          this._lastDragSample = localPt;
          this._refreshPolyline();
        }
      }
    },

    _onUp: function (e) {
      if (!this._active || !this._image) return;
      var stagePt = getStagePoint(this.panel);
      var pressDown = this._pressDown;
      this._isDragging = false;
      this._pressDown  = null;

      if (this._mode === 'drag') {
        // Freehand stroke complete. Append the final point if it isn't
        // already there, then close.
        var endLocal = stageToImageLocal(stagePt, this._image);
        if (!this._lastDragSample ||
            euclidean(this._lastDragSample, endLocal) > 0.5) {
          this._vertices.push(endLocal);
        }
        this._closePolygonIfValid();
        return;
      }

      // Otherwise this was a click (no drag detected). Treat as a vertex
      // click. _mode may still be null — lock it to 'click' on the first
      // such event.
      if (this._mode == null) this._mode = 'click';

      if (this._mode !== 'click') return;
      if (!pressDown) return;

      var clickLocal = stageToImageLocal(stagePt, this._image);

      // If we already have ≥ 3 vertices and this click is near the first
      // vertex, close the polygon.
      if (this._vertices.length >= 3 &&
          euclidean(this._vertices[0], clickLocal) <= CLOSE_RADIUS) {
        this._closePolygonIfValid();
        return;
      }

      // Otherwise add a new vertex (deduplicating consecutive identicals).
      var last = this._vertices[this._vertices.length - 1];
      if (!last || euclidean(last, clickLocal) > 0.001) {
        this._vertices.push(clickLocal);
        this._refreshPolyline();
      }
    },

    _onDoubleClick: function (e) {
      if (!this._active || !this._image) return;
      if (this._mode !== 'click') return;
      // The dblclick fires after two singleclicks → the second click already
      // pushed a vertex. Close if we have enough.
      this._closePolygonIfValid();
    },

    _onKeyDown: function (e) {
      if (!this._active) return;
      var key = e && (e.key || e.code);
      if (key === 'Escape' || key === 'Esc') {
        this._cancelStroke();
        if (e.preventDefault) e.preventDefault();
      }
    },

    // ── Polygon close + emit ───────────────────────────────────────────────

    _closePolygonIfValid: function () {
      if (this._vertices.length < 3) {
        // Not enough to form a polygon. Cancel and let the user start over.
        this._cancelStroke();
        return;
      }

      var polygon = this._vertices.slice();
      var imageId = this._image.imageId;

      // Emit the user-input event with the mask payload.
      emit(this.panel, 'user-input', {
        source: this.id,
        mask: {
          kind:             'lasso_polygon',
          parent_image_id:  imageId,
          coordinate_space: 'image_local',
          polygon:          polygon,
          closed:           true,
          authored_at:      nowIso(),
        },
      });

      // Visual: render the closed polygon briefly, then clear the in-progress
      // line. The mask itself is the consumer's responsibility from here
      // (e.g., image_edits redraws its own overlay).
      this._refreshPolyline(/* closed */ true);
      this._resetStrokeState();
    },

    _cancelStroke: function () {
      this._resetStrokeState();
      this._refreshPolyline();
    },

    // ── Visual feedback ────────────────────────────────────────────────────

    _ensureVisualGroup: function () {
      if (typeof Konva === 'undefined') return;
      if (this._group && !this._group.isDestroyed && !this._group.isDestroyed()) return;
      var panel = this.panel;
      if (!panel.selectionLayer) return;

      var imageOriginX = (this._image && this._image.originX) || 0;
      var imageOriginY = (this._image && this._image.originY) || 0;

      this._group = new Konva.Group({
        name: 'lasso-selection',
        x: imageOriginX,
        y: imageOriginY,
        listening: false,
      });

      // Two stacked dashed lines of contrasting colour give the marching-ants
      // effect visibility on any background. White on bottom, blue on top
      // with phase-offset dash so the two interleave.
      this._lineWhite = new Konva.Line({
        points: [],
        stroke: DASH_STROKE_PRIMARY,
        strokeWidth: DASH_STROKE_WIDTH,
        dash: DASH_PATTERN,
        listening: false,
        perfectDrawEnabled: false,
      });
      this._lineBlue = new Konva.Line({
        points: [],
        stroke: DASH_STROKE_SECONDARY,
        strokeWidth: DASH_STROKE_WIDTH,
        dash: DASH_PATTERN,
        dashOffset: DASH_PATTERN[0],
        listening: false,
        perfectDrawEnabled: false,
      });

      this._group.add(this._lineWhite);
      this._group.add(this._lineBlue);
      panel.selectionLayer.add(this._group);
      panel.selectionLayer.batchDraw();
    },

    _destroyVisualGroup: function () {
      if (this._group) {
        try { this._group.destroy(); } catch (e) { /* ignore */ }
      }
      this._group     = null;
      this._lineWhite = null;
      this._lineBlue  = null;
      if (this.panel && this.panel.selectionLayer) {
        try { this.panel.selectionLayer.batchDraw(); } catch (e) { /* ignore */ }
      }
    },

    _refreshPolyline: function (forceClosed) {
      this._ensureVisualGroup();
      if (!this._lineWhite || !this._lineBlue) return;
      var closed = !!forceClosed;
      var pts = pointsToFlatArray(this._vertices, closed);
      this._lineWhite.points(pts);
      this._lineBlue.points(pts);
      this._lineWhite.closed(closed);
      this._lineBlue.closed(closed);
      if (this.panel && this.panel.selectionLayer) {
        this.panel.selectionLayer.batchDraw();
      }
    },

    _startMarchingAnts: function () {
      if (typeof Konva === 'undefined') return;
      if (!this.panel || !this.panel.selectionLayer) return;
      if (this._anim) return;
      var self = this;
      var totalDash = DASH_PATTERN[0] + DASH_PATTERN[1];
      this._anim = new Konva.Animation(function (frame) {
        if (!self._lineWhite || !self._lineBlue) return false;
        var t = (frame.time / 1000) * ANTS_SPEED_PX_PER_SEC;
        var phase = t % totalDash;
        self._lineWhite.dashOffset(-phase);
        self._lineBlue.dashOffset(DASH_PATTERN[0] - phase);
      }, this.panel.selectionLayer);
      this._anim.start();
    },

    _stopMarchingAnts: function () {
      if (this._anim) {
        try { this._anim.stop(); } catch (e) { /* ignore */ }
      }
      this._anim = null;
    },
  };

  // ── Registration helper ────────────────────────────────────────────────

  /**
   * Register the lasso tool with a visual-panel instance. Idempotent.
   *
   *   var panel = window.__visualPanel;
   *   var lasso = OraLassoSelectionTool.register(panel);
   *   lasso.activate({});
   *
   * Returns the singleton tool instance so callers can wire activate /
   * deactivate to a toolbar button (binding `tool:lasso-selection`).
   */
  function register(panel, ctx) {
    if (!panel) throw new Error('OraLassoSelectionTool.register: panel required');
    if (!Tool._initialized || Tool.panel !== panel) {
      Tool.init(panel, ctx);
      Tool._initialized = true;
    }
    return Tool;
  }

  // ── Export ─────────────────────────────────────────────────────────────

  var api = {
    tool:     Tool,
    register: register,
    // Exposed for test harnesses.
    _internals: {
      resolveSelectedImage: resolveSelectedImage,
      stageToImageLocal:    stageToImageLocal,
      pointsToFlatArray:    pointsToFlatArray,
      manhattan:            manhattan,
      euclidean:            euclidean,
      CLICK_DRAG_THRESHOLD: CLICK_DRAG_THRESHOLD,
      MIN_DRAG_SPACING:     MIN_DRAG_SPACING,
      CLOSE_RADIUS:         CLOSE_RADIUS,
    },
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (global) {
    global.OraLassoSelectionTool = api;
    // Mirror brush-mask + image-crop by registering in the unified
    // window.OraTools registry too. The actual tool primitive lives at
    // api.tool (api itself is the wrapper exposing register/tool/_internals).
    if (api && api.tool && api.tool.id) {
      global.OraTools = global.OraTools || {};
      global.OraTools[api.tool.id] = api.tool;
    }
  }

})(typeof window !== 'undefined' ? window : (typeof global !== 'undefined' ? global : this));
