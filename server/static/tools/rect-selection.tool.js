/* rect-selection.tool.js — WP-7.5.1a
 *
 * Rectangle selection tool. The user picks an image on the canvas, activates
 * this tool, and click-drags a rectangle inside (or overlapping) the image.
 * The rectangle defines a selection region that is emitted as a SelectionMask
 * — the unified mask format consumed by `image_edits` (WP-7.3.3b, stubbed
 * here) and shared with WP-7.5.1b (brush) and WP-7.5.1c (lasso).
 *
 * Authoring contract (per Reference — Visual Pane Extension Points §B.4):
 *   exports default { id, label, defaultIcon,
 *                     init(panel, ctx),
 *                     activate(ctx),
 *                     deactivate(ctx),
 *                     serializeState(state) }
 *
 * Layer rules:
 *   - Drag preview + marching-ants outline are drawn on `panel.selectionLayer`.
 *   - The selection layer is deliberately re-listening-enabled while this
 *     tool is active so the in-flight drag can attach to stage events without
 *     mutating user-input geometry. Original `listening` value is restored on
 *     deactivate.
 *
 * Mask output (the shared schema referenced by §13.5 WP-7.5.1):
 *
 *   {
 *     schema_version: '1.0',
 *     kind:           'rectangle' | 'brush' | 'lasso',
 *     image_ref: {
 *       image_id:        string,   // canvas-file-format §objects[].id
 *       natural_width:   number,   // pixels of the source image
 *       natural_height:  number,
 *       source_name:     string    // best-effort filename
 *     },
 *     geometry: {                  // shape-specific; rectangle case here
 *       x:      number,            // image-natural pixel space
 *       y:      number,
 *       width:  number,
 *       height: number
 *     },
 *     bbox: { x, y, width, height }, // always present, image-natural pixels.
 *                                    // For 'rectangle' it equals geometry;
 *                                    // for 'brush'/'lasso' it is the AABB
 *                                    // of the painted region / polygon.
 *     created_at: ISO-8601 string
 *   }
 *
 * The brush + lasso tools (WP-7.5.1b/c) MUST emit the same envelope so a
 * single image_edits dispatch path handles all three. They differ only in
 * `kind` and the contents of `geometry` (`{ pixels: [...] }` for brush,
 * `{ points: [{x,y},...] }` for lasso) — `image_ref` and `bbox` are uniform.
 */

'use strict';

(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    var TOOL = factory();
    root.OraRectSelectionTool = TOOL;
    // Also register in the unified window.OraTools registry so visual-panel
    // and pack-toolbars can pick it up by id, mirroring brush-mask and
    // image-crop. Mixed registration patterns predate this fix.
    if (TOOL && TOOL.id) {
      root.OraTools = root.OraTools || {};
      root.OraTools[TOOL.id] = TOOL;
    }
  }
}(typeof self !== 'undefined' ? self : this, function () {

  // ── shared mask schema -----------------------------------------------------
  // Exported so 7.5.1b/c can `require()` it via this file rather than re-
  // declaring. CommonJS-only (the panel auto-loader is happy with that).

  var MASK_SCHEMA_VERSION = '1.0';

  /**
   * Build a SelectionMask envelope from a rectangle in stage coordinates.
   * Stage → image-natural conversion uses the Konva.Image's draw width/height
   * and stored naturalWidth/naturalHeight attrs (set by visual-panel.js when
   * the upload mounts).
   *
   * @param {Object} args
   * @param {Konva.Image} args.imageNode  — the target image
   * @param {{x,y,width,height}} args.stageRect — selection rect in stage coords
   * @returns {Object} SelectionMask envelope, or null if the rect lies fully
   *                   outside the image (callers should treat null as "no-op").
   */
  function buildRectangleMask(args) {
    var imageNode = args.imageNode;
    var stageRect = args.stageRect;
    if (!imageNode || !stageRect) return null;

    // Image AABB in stage space.
    var imgX = (typeof imageNode.x === 'function') ? imageNode.x() : imageNode.x;
    var imgY = (typeof imageNode.y === 'function') ? imageNode.y() : imageNode.y;
    var imgW = (typeof imageNode.width  === 'function') ? imageNode.width()  : imageNode.width;
    var imgH = (typeof imageNode.height === 'function') ? imageNode.height() : imageNode.height;

    // Clip selection rect against image AABB. Negative widths normalised.
    var sx = Math.min(stageRect.x, stageRect.x + stageRect.width);
    var sy = Math.min(stageRect.y, stageRect.y + stageRect.height);
    var sw = Math.abs(stageRect.width);
    var sh = Math.abs(stageRect.height);

    var clipX = Math.max(sx, imgX);
    var clipY = Math.max(sy, imgY);
    var clipR = Math.min(sx + sw, imgX + imgW);
    var clipB = Math.min(sy + sh, imgY + imgH);
    var clipW = clipR - clipX;
    var clipH = clipB - clipY;

    if (clipW <= 0 || clipH <= 0) return null;  // fully outside

    // Stage → image-natural conversion. Konva.Image drawn dimensions are
    // (imgW, imgH); naturalWidth/Height live on the node attrs.
    var attrs = (imageNode.attrs) || {};
    var naturalW = attrs.naturalWidth  || imgW;
    var naturalH = attrs.naturalHeight || imgH;
    var sxScale = (imgW > 0) ? (naturalW / imgW) : 1;
    var syScale = (imgH > 0) ? (naturalH / imgH) : 1;

    var localX = (clipX - imgX) * sxScale;
    var localY = (clipY - imgY) * syScale;
    var localW = clipW * sxScale;
    var localH = clipH * syScale;

    // Resolve image_id. Prefer an explicit attrs.image_id (set by Phase 7 wire
    // up when canvas-file-format objects are mounted), fall back to Konva
    // node id() / name().
    var imageId = attrs.image_id
      || (typeof imageNode.id === 'function' ? imageNode.id() : imageNode.id)
      || (typeof imageNode.name === 'function' ? imageNode.name() : imageNode.name)
      || 'background-image';

    var geom = {
      x:      localX,
      y:      localY,
      width:  localW,
      height: localH,
    };

    return {
      schema_version: MASK_SCHEMA_VERSION,
      kind:     'rectangle',
      image_ref: {
        image_id:       imageId,
        natural_width:  naturalW,
        natural_height: naturalH,
        source_name:    attrs.sourceName || '',
      },
      geometry: geom,
      bbox:     { x: geom.x, y: geom.y, width: geom.width, height: geom.height },
      created_at: new Date().toISOString(),
    };
  }

  // ── stub dispatcher for image_edits ---------------------------------------
  // WP-7.3.3b is not in flight. We honour the contract by emitting a
  // CustomEvent on the panel root and stashing the most recent mask on the
  // panel for inspection / Phase 7.6 wire-up.

  function dispatchImageEditsStub(panel, mask) {
    panel._lastSelectionMask = mask;
    if (panel.el && typeof CustomEvent === 'function') {
      try {
        var evt = new CustomEvent('ora:selection-mask', {
          detail: { mask: mask, capability: 'image_edits' },
          bubbles: false,
        });
        panel.el.dispatchEvent(evt);
      } catch (e) { /* CustomEvent unsupported — silently no-op */ }
    }
    if (typeof panel._onSelectionMask === 'function') {
      try { panel._onSelectionMask(mask); } catch (e) { /* never throw */ }
    }
  }

  // ── tool primitive --------------------------------------------------------

  var TOOL = {
    id:          'rect-selection',
    label:       'Rectangle selection',
    defaultIcon: 'square-dashed',     // Lucide name (canonical names.json)

    /** Runs once on registration. Stash the panel + capture defaults. */
    init: function (panel /*, ctx */) {
      this.panel = panel;
      this._defaultSelectionListening = null;  // restored on deactivate
      this._previewRect  = null;     // Konva.Rect during drag
      this._committedRect = null;    // Konva.Rect after mouseup, with marching ants
      this._marchingAnim = null;     // Konva.Animation
      this._dragStart    = null;     // {x,y} in stage coords
      this._activeImage  = null;     // resolved Konva.Image for this drag
      this._mouseDown    = null;
      this._mouseMove    = null;
      this._mouseUp      = null;
      this._escListener  = null;
    },

    /** Called when the user activates this tool. */
    activate: function (/* ctx */) {
      var panel = this.panel;
      if (!panel || !panel.stage) return;

      // Make selectionLayer interactive while this tool owns the stage.
      var selLayer = panel.selectionLayer;
      if (selLayer && typeof selLayer.listening === 'function') {
        this._defaultSelectionListening = selLayer.listening();
        selLayer.listening(true);
      }

      var self = this;

      this._mouseDown = function (e) { self._beginDrag(e); };
      this._mouseMove = function (e) { self._updateDrag(e); };
      this._mouseUp   = function (e) { self._commitDrag(e); };
      panel.stage.on('mousedown.rect-selection touchstart.rect-selection', this._mouseDown);
      panel.stage.on('mousemove.rect-selection touchmove.rect-selection', this._mouseMove);
      panel.stage.on('mouseup.rect-selection touchend.rect-selection',   this._mouseUp);

      // Escape clears selection.
      this._escListener = function (e) {
        if (e.key === 'Escape') self.clearSelection();
      };
      var doc = (panel.el && panel.el.ownerDocument) || (typeof document !== 'undefined' ? document : null);
      if (doc && doc.addEventListener) doc.addEventListener('keydown', this._escListener);
    },

    /** Called when the user switches to a different tool. */
    deactivate: function (/* ctx */) {
      var panel = this.panel;
      if (!panel) return;

      if (panel.stage) {
        panel.stage.off('mousedown.rect-selection touchstart.rect-selection');
        panel.stage.off('mousemove.rect-selection touchmove.rect-selection');
        panel.stage.off('mouseup.rect-selection touchend.rect-selection');
      }

      var doc = (panel.el && panel.el.ownerDocument) || (typeof document !== 'undefined' ? document : null);
      if (doc && doc.removeEventListener && this._escListener) {
        doc.removeEventListener('keydown', this._escListener);
      }

      // Switching tools clears the selection (per spec: "selection clears on
      // ... new tool activation").
      this.clearSelection();

      // Restore selectionLayer.listening to its prior value.
      if (panel.selectionLayer && this._defaultSelectionListening !== null
          && typeof panel.selectionLayer.listening === 'function') {
        panel.selectionLayer.listening(this._defaultSelectionListening);
      }
      this._defaultSelectionListening = null;

      this._mouseDown = this._mouseMove = this._mouseUp = null;
      this._escListener = null;
    },

    /**
     * In-progress tool state for autosave. The committed selection (if any)
     * is captured as a SelectionMask, so reload can restore the marching
     * ants. In-flight drags are not persisted — they're transient by design.
     */
    serializeState: function (/* state */) {
      var mask = this.panel && this.panel._lastSelectionMask;
      return {
        in_progress: false,
        last_mask:   mask || null,
      };
    },

    // ── internals ------------------------------------------------------------

    /** Resolve the target image for this selection: explicit > background. */
    _resolveTargetImage: function () {
      var panel = this.panel;
      if (!panel) return null;
      // 1. Explicit hand-off via panel state (set by §B.6 selection-of-images
      //    flow, future Phase 7 wire-up).
      if (panel._activeImageNode) return panel._activeImageNode;
      // 2. The currently uploaded background image (the only image the
      //    canvas hosts today).
      if (panel._backgroundImageNode) return panel._backgroundImageNode;
      return null;
    },

    _beginDrag: function (e) {
      var panel = this.panel;
      var stage = panel && panel.stage;
      if (!stage) return;

      var img = this._resolveTargetImage();
      if (!img) {
        // No image → no-op. The tool stays armed; the user just wasted a
        // click. Mirrors the diamond-tool "do nothing if click is invalid"
        // pattern.
        return;
      }
      this._activeImage = img;

      var pos = stage.getPointerPosition && stage.getPointerPosition();
      if (!pos) return;

      // Clear any prior preview / committed visuals.
      this.clearSelection();

      this._dragStart = { x: pos.x, y: pos.y };

      // Konva-only — gracefully no-op in headless tests with no Konva.
      if (typeof Konva === 'undefined') return;

      this._previewRect = new Konva.Rect({
        x:      pos.x,
        y:      pos.y,
        width:  0,
        height: 0,
        stroke: '#0072B2',
        strokeWidth: 1.5,
        dash:   [6, 4],
        fill:   'rgba(0, 114, 178, 0.10)',
        listening: false,
        name: 'vp-rect-selection-preview',
      });
      panel.selectionLayer.add(this._previewRect);
      panel.selectionLayer.draw();
    },

    _updateDrag: function (/* e */) {
      var panel = this.panel;
      if (!this._dragStart || !this._previewRect || !panel || !panel.stage) return;

      var pos = panel.stage.getPointerPosition && panel.stage.getPointerPosition();
      if (!pos) return;

      var x = Math.min(this._dragStart.x, pos.x);
      var y = Math.min(this._dragStart.y, pos.y);
      var w = Math.abs(pos.x - this._dragStart.x);
      var h = Math.abs(pos.y - this._dragStart.y);

      this._previewRect.setAttrs({ x: x, y: y, width: w, height: h });
      panel.selectionLayer.batchDraw ? panel.selectionLayer.batchDraw() : panel.selectionLayer.draw();
    },

    _commitDrag: function (/* e */) {
      var panel = this.panel;
      if (!this._dragStart) return;

      var preview = this._previewRect;
      var imgNode = this._activeImage;
      this._dragStart = null;
      this._previewRect = null;
      this._activeImage = null;

      if (!preview || !imgNode) {
        if (preview && preview.destroy) preview.destroy();
        return;
      }

      var stageRect = {
        x:      preview.x(),
        y:      preview.y(),
        width:  preview.width(),
        height: preview.height(),
      };

      // Trivial click without a drag → discard.
      if (Math.abs(stageRect.width) < 2 || Math.abs(stageRect.height) < 2) {
        try { preview.destroy(); } catch (e) {}
        if (panel.selectionLayer) panel.selectionLayer.draw();
        return;
      }

      var mask = buildRectangleMask({ imageNode: imgNode, stageRect: stageRect });
      if (!mask) {
        // Fully outside the image → discard.
        try { preview.destroy(); } catch (e) {}
        if (panel.selectionLayer) panel.selectionLayer.draw();
        return;
      }

      // Promote preview to the committed marching-ants outline.
      try { preview.destroy(); } catch (e) {}
      this._committedRect = this._renderCommittedOutline(stageRect);
      this._startMarchingAnts();

      // Stash + dispatch.
      panel._lastSelectionMask = mask;
      dispatchImageEditsStub(panel, mask);
    },

    _renderCommittedOutline: function (stageRect) {
      var panel = this.panel;
      if (typeof Konva === 'undefined' || !panel || !panel.selectionLayer) return null;

      // Normalise to non-negative width/height so the dashOffset animation
      // travels the perimeter cleanly.
      var x = Math.min(stageRect.x, stageRect.x + stageRect.width);
      var y = Math.min(stageRect.y, stageRect.y + stageRect.height);
      var w = Math.abs(stageRect.width);
      var h = Math.abs(stageRect.height);

      var rect = new Konva.Rect({
        x: x, y: y, width: w, height: h,
        stroke: '#0072B2',
        strokeWidth: 1.5,
        dash: [6, 4],
        listening: false,
        name: 'vp-rect-selection-committed',
      });
      panel.selectionLayer.add(rect);
      panel.selectionLayer.draw();
      return rect;
    },

    _startMarchingAnts: function () {
      var panel = this.panel;
      var rect  = this._committedRect;
      if (!rect || !panel || typeof Konva === 'undefined' || !Konva.Animation) return;

      var anim = new Konva.Animation(function (frame) {
        // Cycle dashOffset every ~600ms so the dashes appear to march.
        var period = 600;
        var step   = (frame.time % period) / period;  // 0 → 1
        rect.dashOffset(-step * 10);                  // 6+4 dash sums to 10
      }, panel.selectionLayer);

      this._marchingAnim = anim;
      anim.start();
    },

    /** Public — clear the current selection (called on Escape + tool switch). */
    clearSelection: function () {
      var panel = this.panel;
      if (!panel) return;

      if (this._marchingAnim && typeof this._marchingAnim.stop === 'function') {
        try { this._marchingAnim.stop(); } catch (e) {}
        this._marchingAnim = null;
      }
      if (this._previewRect && this._previewRect.destroy) {
        try { this._previewRect.destroy(); } catch (e) {}
        this._previewRect = null;
      }
      if (this._committedRect && this._committedRect.destroy) {
        try { this._committedRect.destroy(); } catch (e) {}
        this._committedRect = null;
      }
      if (panel.selectionLayer) {
        try { panel.selectionLayer.draw(); } catch (e) {}
      }
      panel._lastSelectionMask = null;
    },

  };

  // Attach helpers as named exports for the brush + lasso siblings to import.
  TOOL.MASK_SCHEMA_VERSION = MASK_SCHEMA_VERSION;
  TOOL.buildRectangleMask  = buildRectangleMask;
  TOOL.dispatchImageEditsStub = dispatchImageEditsStub;

  return TOOL;
}));
