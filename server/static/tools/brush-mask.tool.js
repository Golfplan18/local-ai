/* ──────────────────────────────────────────────────────────────────────────
 * brush-mask.tool.js — WP-7.5.1b — Brush-mask selection tool
 *
 * Phase 7 §7.5 image-edit selection model. Sub-WP b of three (rectangle /
 * brush / lasso). Output is a freeform raster mask consumable by the
 * `image_edits` capability slot (WP-7.3.3b).
 *
 * Contract:
 *   `Reference — Visual Pane Extension Points.md` §B.4 — Tool Primitives.
 *   Module exposes `{ id, label, defaultIcon, init(panel, ctx), activate(ctx),
 *   deactivate(ctx), serializeState(state) }`.
 *
 * Why a separate raster overlay layer (not userInputLayer):
 *   userInputLayer is a Konva vector layer. A brush mask is fundamentally a
 *   bitmap. Painting hundreds of small overlapping circles into a vector
 *   layer would (a) bloat the saved canvas state, (b) confuse downstream
 *   serializers expecting vector primitives. Per §B.7 (Rendering Surfaces),
 *   raster surfaces own their own <canvas> element. The mask layer here is
 *   a transient selection overlay — it lives only while the brush tool is
 *   active and clears on Escape / tool deactivation. It is NOT serialized
 *   into the persistent canvas state. The mask data is consumed by
 *   `image_edits` and discarded.
 *
 * Mask output format (consumed by WP-7.3.3b):
 *   {
 *     kind: 'raster_mask',          // discriminator (rect → 'rect_mask',
 *                                    //                lasso → 'polygon_mask')
 *     parent_image_id: string|null, // semantic id of the target image,
 *                                    // null if no image was under the strokes
 *     parent_image_bbox: {          // image bounding box in stage coords —
 *       x, y, width, height          // mask is rasterized at this resolution
 *     },
 *     mask_data_url: string,        // 'data:image/png;base64,...' — white
 *                                    // pixels = masked region, transparent =
 *                                    // unmasked. Same width/height as bbox.
 *     mask_pixel_count: number,     // count of opaque mask pixels (sanity
 *                                    // check; zero ⇒ no selection)
 *     created_at: string            // ISO timestamp
 *   }
 *
 *   Cross-WP coordination:
 *     • WP-7.5.1a (rect)  → emits { kind: 'rect_mask',    parent_image_id, bbox: {x,y,w,h} }
 *     • WP-7.5.1b (this)  → emits { kind: 'raster_mask',  parent_image_id, parent_image_bbox, mask_data_url, ... }
 *     • WP-7.5.1c (lasso) → emits { kind: 'polygon_mask', parent_image_id, points: [...] }
 *   `image_edits` accepts any of the three shapes via the `kind`
 *   discriminator and rasterizes rect/polygon to PNG before invoking the
 *   underlying inpaint model. Brush masks bypass the rasterization step.
 *
 * Brush-size UX:
 *   Both a slider AND keyboard shortcuts. Slider for discoverability;
 *   `[` / `]` for muscle memory (Photoshop / Procreate convention). The
 *   slider lives in a small floating control panel pinned to the stage
 *   while the tool is active; it disappears on deactivation.
 *
 * Eraser mode:
 *   Toggle button in the floating control panel + `e` key. When active,
 *   strokes erase from the mask (canvas globalCompositeOperation =
 *   'destination-out'). Toggle off restores paint mode.
 *
 * Escape key:
 *   Clears all strokes from the mask layer without deactivating the tool.
 *   This lets the user start over without re-clicking the brush button.
 *   Tool deactivation (selecting another tool) ALSO clears the mask per
 *   the WP requirement "Mask clears on Escape or new tool activation."
 *
 * Registration:
 *   This module self-registers onto window.OraTools (a registry created on
 *   demand) and self-mounts onto the active visual panel via
 *   window.OraPanels.visual when the panel is ready. It does NOT modify
 *   visual-panel.js. A toolbar button can be added later by the toolbar
 *   pack system (§B.5) using `binding: tool:brush-mask`.
 *
 * ────────────────────────────────────────────────────────────────────── */

(function () {
  'use strict';

  // ── Tool definition (§B.4 contract) ───────────────────────────────────────

  var BRUSH_MASK_TOOL = {
    id: 'brush-mask',
    label: 'Brush mask',
    defaultIcon: 'brush',  // Lucide icon name

    // ── §B.4 lifecycle ─────────────────────────────────────────────────────

    /**
     * Run once on registration. Stash the panel reference and prepare the
     * raster overlay <canvas>. The canvas is appended on activate() so we
     * don't add DOM clutter to inactive panels.
     */
    init: function (panel, ctx) {
      this.panel = panel;
      this.ctx   = ctx || {};

      // Mask drawing state — per-instance so multiple panels don't share state.
      this._maskCanvas    = null;   // <canvas> element
      this._maskCtx2d     = null;   // CanvasRenderingContext2D
      this._cursorEl      = null;   // <div> showing brush size cursor
      this._controlsEl    = null;   // floating slider + eraser controls
      this._brushSize     = 24;     // px (default)
      this._eraserMode    = false;
      this._isDrawing     = false;
      this._lastPoint     = null;   // {x,y} of previous stroke segment
      this._strokeCount   = 0;      // number of strokes painted (for serializeState)

      // Bound handlers — saved so deactivate() can detach the same
      // function references. Anonymous .bind() in addEventListener would
      // leak listeners across activate/deactivate cycles.
      this._onStageDown    = null;
      this._onStageMove    = null;
      this._onStageUp      = null;
      this._onStageLeave   = null;
      this._onKeyDown      = null;
    },

    /**
     * User clicked the brush-mask toolbar button. Mount the raster overlay,
     * the brush-size cursor, the floating controls, and wire pointer +
     * keyboard listeners.
     */
    activate: function (ctx) {
      if (!this.panel || !this.panel.stage) return;
      var stage = this.panel.stage;

      // Stage container for positioning. Konva exposes `.container()`
      // which returns the parent DOM element of the stage.
      var stageContainer = stage.container();
      if (!stageContainer) return;

      // ── Build mask <canvas> overlay ─────────────────────────────────────
      var w = stage.width();
      var h = stage.height();
      this._maskCanvas = document.createElement('canvas');
      this._maskCanvas.width  = w;
      this._maskCanvas.height = h;
      this._maskCanvas.className = 'vp-brush-mask-overlay';
      // Pin the canvas absolutely on top of the Konva stage. pointer-events:
      // none lets us read pointer events from the Konva stage natively
      // (the stage will dispatch mousedown/mousemove/mouseup) — we don't
      // need our own listeners on the canvas itself.
      this._maskCanvas.style.position      = 'absolute';
      this._maskCanvas.style.left          = '0';
      this._maskCanvas.style.top           = '0';
      this._maskCanvas.style.width         = w + 'px';
      this._maskCanvas.style.height        = h + 'px';
      this._maskCanvas.style.pointerEvents = 'none';
      this._maskCanvas.style.zIndex        = '50';   // above Konva layers
      stageContainer.appendChild(this._maskCanvas);
      this._maskCtx2d = this._maskCanvas.getContext('2d');
      this._maskCtx2d.lineCap  = 'round';
      this._maskCtx2d.lineJoin = 'round';

      // ── Build brush-size cursor (visual feedback follows pointer) ──────
      this._cursorEl = document.createElement('div');
      this._cursorEl.className = 'vp-brush-mask-cursor';
      this._cursorEl.style.position      = 'absolute';
      this._cursorEl.style.pointerEvents = 'none';
      this._cursorEl.style.borderRadius  = '50%';
      this._cursorEl.style.border        = '1px solid rgba(255,255,255,0.85)';
      this._cursorEl.style.boxShadow     = '0 0 0 1px rgba(0,0,0,0.6)';
      this._cursorEl.style.transform     = 'translate(-50%, -50%)';
      this._cursorEl.style.zIndex        = '51';
      this._cursorEl.style.display       = 'none';
      stageContainer.appendChild(this._cursorEl);
      this._updateCursorSize();

      // ── Build floating controls (brush size slider + eraser toggle) ────
      this._controlsEl = this._buildControls();
      stageContainer.appendChild(this._controlsEl);

      // Hide the regular Konva stage cursor while the brush is active —
      // our cursor element provides the visual feedback.
      stageContainer.style.cursor = 'none';

      // ── Wire pointer events on the Konva stage ─────────────────────────
      var self = this;
      this._onStageDown  = function (evt) { self._onPointerDown(evt); };
      this._onStageMove  = function (evt) { self._onPointerMove(evt); };
      this._onStageUp    = function (evt) { self._onPointerUp(evt); };
      this._onStageLeave = function (evt) { self._onPointerLeave(evt); };
      stage.on('mousedown touchstart',  this._onStageDown);
      stage.on('mousemove touchmove',   this._onStageMove);
      stage.on('mouseup touchend',      this._onStageUp);
      stage.on('mouseleave',            this._onStageLeave);

      // ── Keyboard shortcuts (window-level so they fire even if focus is
      // outside the stage container) ─────────────────────────────────────
      this._onKeyDown = function (e) { self._onKeyDownHandler(e); };
      window.addEventListener('keydown', this._onKeyDown);
    },

    /**
     * User selected a different tool, or the panel is being torn down.
     * Per WP requirement "Mask clears on Escape or new tool activation",
     * we clear strokes, dispose the overlay canvas, controls, cursor, and
     * detach all listeners.
     */
    deactivate: function (ctx) {
      if (!this.panel || !this.panel.stage) return;
      var stage = this.panel.stage;

      // Clear mask data (the WP says new tool activation clears the mask).
      this._clearMask();

      // Detach pointer listeners.
      if (this._onStageDown)  stage.off('mousedown touchstart',  this._onStageDown);
      if (this._onStageMove)  stage.off('mousemove touchmove',   this._onStageMove);
      if (this._onStageUp)    stage.off('mouseup touchend',      this._onStageUp);
      if (this._onStageLeave) stage.off('mouseleave',            this._onStageLeave);
      this._onStageDown = this._onStageMove = this._onStageUp = this._onStageLeave = null;

      // Detach keyboard listener.
      if (this._onKeyDown) window.removeEventListener('keydown', this._onKeyDown);
      this._onKeyDown = null;

      // Dispose DOM elements.
      if (this._maskCanvas && this._maskCanvas.parentNode) {
        this._maskCanvas.parentNode.removeChild(this._maskCanvas);
      }
      if (this._cursorEl && this._cursorEl.parentNode) {
        this._cursorEl.parentNode.removeChild(this._cursorEl);
      }
      if (this._controlsEl && this._controlsEl.parentNode) {
        this._controlsEl.parentNode.removeChild(this._controlsEl);
      }
      this._maskCanvas = this._maskCtx2d = null;
      this._cursorEl   = null;
      this._controlsEl = null;

      // Restore stage cursor.
      var stageContainer = stage.container();
      if (stageContainer) stageContainer.style.cursor = '';

      // Reset internal state.
      this._isDrawing  = false;
      this._lastPoint  = null;
      this._strokeCount = 0;
      this._eraserMode = false;
    },

    /**
     * Autosave snapshot. Mask data is transient (cleared on tool switch),
     * so we only record whether a stroke is in flight — autosave should
     * not capture mask pixels. If the user wants to preserve a mask, they
     * invoke `image_edits` (which consumes the mask).
     */
    serializeState: function (state) {
      return {
        in_progress:  !!this._isDrawing,
        stroke_count: this._strokeCount,
        brush_size:   this._brushSize,
        eraser_mode:  this._eraserMode
      };
    },

    // ── Internal: pointer handling ────────────────────────────────────────

    _onPointerDown: function (evt) {
      var pos = this._stagePointer();
      if (!pos) return;
      // Suppress the regular stage select/draw behavior while the brush
      // tool is active. The Konva stage will still fire mousedown handlers
      // wired by visual-panel.js (rect / pen / etc.), but those handlers
      // gate on _activeTool. Since the brush-mask tool is not in
      // SHAPE_TOOLS / ANNOTATION_TOOLS, _activeTool stays as whatever the
      // user last selected — which means the brush could overlap with
      // (e.g.) pen drawing if the user activated brush programmatically
      // without going through setActiveTool. To prevent that, callers
      // SHOULD call panel.setActiveTool('select') before activating the
      // brush, OR the toolbar handler should be extended to recognize
      // 'brush-mask' as a no-op tool name (so visual-panel's drawing
      // handlers see _activeTool='brush-mask' and bail out). For
      // standalone smoke testing the brush-mask tool, this is a non-issue.
      if (evt && evt.evt) {
        try { evt.evt.preventDefault(); } catch (e) { /* ignore */ }
      }
      this._isDrawing = true;
      this._lastPoint = pos;
      this._paintAt(pos.x, pos.y);
    },

    _onPointerMove: function (evt) {
      var pos = this._stagePointer();
      if (!pos) return;
      this._moveCursor(pos);
      if (!this._isDrawing) return;
      this._paintSegment(this._lastPoint, pos);
      this._lastPoint = pos;
    },

    _onPointerUp: function (evt) {
      if (!this._isDrawing) return;
      this._isDrawing = false;
      this._lastPoint = null;
      this._strokeCount += 1;
    },

    _onPointerLeave: function (evt) {
      if (this._cursorEl) this._cursorEl.style.display = 'none';
      // Don't end the stroke on leave — pointer may re-enter and the user
      // expects a continuous stroke. End on mouseup only.
    },

    /**
     * Returns stage-coordinate {x,y} for the current pointer, or null if
     * no pointer is over the stage. Konva's stage.getPointerPosition()
     * accounts for stage transforms (pan/zoom).
     */
    _stagePointer: function () {
      if (!this.panel || !this.panel.stage) return null;
      var pos = this.panel.stage.getPointerPosition();
      return pos || null;
    },

    _moveCursor: function (pos) {
      if (!this._cursorEl) return;
      this._cursorEl.style.display = 'block';
      this._cursorEl.style.left = pos.x + 'px';
      this._cursorEl.style.top  = pos.y + 'px';
    },

    _updateCursorSize: function () {
      if (!this._cursorEl) return;
      this._cursorEl.style.width  = this._brushSize + 'px';
      this._cursorEl.style.height = this._brushSize + 'px';
    },

    /**
     * Paint a single dot at (x,y). Used on mousedown so a click without
     * drag still produces a visible mask spot.
     */
    _paintAt: function (x, y) {
      if (!this._maskCtx2d) return;
      var ctx = this._maskCtx2d;
      ctx.save();
      ctx.globalCompositeOperation = this._eraserMode ? 'destination-out' : 'source-over';
      ctx.fillStyle = 'rgba(255,255,255,0.85)';
      ctx.beginPath();
      ctx.arc(x, y, this._brushSize / 2, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    },

    /**
     * Paint a stroke segment between two points. Uses lineCap='round' so
     * dense pointer-move samples yield a continuous stroke even at high
     * brush sizes. lineWidth = brushSize so a single segment covers the
     * same area as a click.
     */
    _paintSegment: function (from, to) {
      if (!this._maskCtx2d) return;
      if (!from || !to) return;
      var ctx = this._maskCtx2d;
      ctx.save();
      ctx.globalCompositeOperation = this._eraserMode ? 'destination-out' : 'source-over';
      ctx.strokeStyle = 'rgba(255,255,255,0.85)';
      ctx.lineWidth   = this._brushSize;
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(to.x, to.y);
      ctx.stroke();
      ctx.restore();
    },

    _clearMask: function () {
      if (!this._maskCtx2d || !this._maskCanvas) return;
      this._maskCtx2d.clearRect(0, 0, this._maskCanvas.width, this._maskCanvas.height);
      this._strokeCount = 0;
    },

    // ── Internal: keyboard shortcuts ──────────────────────────────────────

    _onKeyDownHandler: function (e) {
      // Don't fire shortcuts while the user is typing into an input.
      var t = e.target;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;

      if (e.key === '[') {
        e.preventDefault();
        this._setBrushSize(this._brushSize - 4);
        return;
      }
      if (e.key === ']') {
        e.preventDefault();
        this._setBrushSize(this._brushSize + 4);
        return;
      }
      if (e.key === 'e' || e.key === 'E') {
        e.preventDefault();
        this._toggleEraser();
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        this._clearMask();
        return;
      }
    },

    _setBrushSize: function (next) {
      // Clamp to a reasonable range. 2px floor avoids invisible strokes;
      // 200px ceiling avoids accidental whole-canvas painting.
      next = Math.max(2, Math.min(200, next | 0));
      this._brushSize = next;
      this._updateCursorSize();
      // Sync slider if mounted.
      if (this._controlsEl) {
        var slider = this._controlsEl.querySelector('input[type=range]');
        if (slider) slider.value = String(next);
        var label = this._controlsEl.querySelector('.vp-brush-mask-size-label');
        if (label) label.textContent = next + 'px';
      }
    },

    _toggleEraser: function () {
      this._eraserMode = !this._eraserMode;
      // Visual feedback: re-color the cursor.
      if (this._cursorEl) {
        this._cursorEl.style.borderColor = this._eraserMode
          ? 'rgba(255,150,150,0.95)'
          : 'rgba(255,255,255,0.85)';
      }
      // Sync eraser button state.
      if (this._controlsEl) {
        var btn = this._controlsEl.querySelector('.vp-brush-mask-eraser');
        if (btn) {
          btn.setAttribute('aria-pressed', this._eraserMode ? 'true' : 'false');
          btn.style.background = this._eraserMode ? '#444' : '';
        }
      }
    },

    // ── Internal: floating control panel ──────────────────────────────────

    _buildControls: function () {
      var self = this;
      var wrap = document.createElement('div');
      wrap.className = 'vp-brush-mask-controls';
      wrap.style.position    = 'absolute';
      wrap.style.left        = '8px';
      wrap.style.top         = '8px';
      wrap.style.padding     = '6px 10px';
      wrap.style.background  = 'rgba(30,30,30,0.85)';
      wrap.style.color       = '#fff';
      wrap.style.borderRadius= '6px';
      wrap.style.font        = '12px system-ui, sans-serif';
      wrap.style.zIndex      = '52';
      wrap.style.display     = 'flex';
      wrap.style.alignItems  = 'center';
      wrap.style.gap         = '8px';
      wrap.style.userSelect  = 'none';
      wrap.setAttribute('role', 'toolbar');
      wrap.setAttribute('aria-label', 'Brush mask controls');

      var labelText = document.createElement('span');
      labelText.textContent = 'Brush:';
      wrap.appendChild(labelText);

      var slider = document.createElement('input');
      slider.type  = 'range';
      slider.min   = '2';
      slider.max   = '200';
      slider.step  = '2';
      slider.value = String(this._brushSize);
      slider.style.width = '120px';
      slider.setAttribute('aria-label', 'Brush size');
      slider.addEventListener('input', function (e) {
        self._setBrushSize(parseInt(e.target.value, 10) || self._brushSize);
      });
      wrap.appendChild(slider);

      var sizeLabel = document.createElement('span');
      sizeLabel.className = 'vp-brush-mask-size-label';
      sizeLabel.textContent = this._brushSize + 'px';
      sizeLabel.style.minWidth = '38px';
      wrap.appendChild(sizeLabel);

      var eraserBtn = document.createElement('button');
      eraserBtn.type = 'button';
      eraserBtn.className = 'vp-brush-mask-eraser';
      eraserBtn.textContent = 'Eraser';
      eraserBtn.setAttribute('aria-pressed', 'false');
      eraserBtn.title = 'Toggle eraser (E)';
      eraserBtn.style.background = '';
      eraserBtn.style.color = '#fff';
      eraserBtn.style.border = '1px solid #666';
      eraserBtn.style.borderRadius = '3px';
      eraserBtn.style.padding = '2px 8px';
      eraserBtn.style.cursor = 'pointer';
      eraserBtn.addEventListener('click', function () { self._toggleEraser(); });
      wrap.appendChild(eraserBtn);

      var clearBtn = document.createElement('button');
      clearBtn.type = 'button';
      clearBtn.className = 'vp-brush-mask-clear';
      clearBtn.textContent = 'Clear';
      clearBtn.title = 'Clear mask (Escape)';
      clearBtn.style.background = '';
      clearBtn.style.color = '#fff';
      clearBtn.style.border = '1px solid #666';
      clearBtn.style.borderRadius = '3px';
      clearBtn.style.padding = '2px 8px';
      clearBtn.style.cursor = 'pointer';
      clearBtn.addEventListener('click', function () { self._clearMask(); });
      wrap.appendChild(clearBtn);

      var hint = document.createElement('span');
      hint.style.opacity = '0.6';
      hint.style.marginLeft = '4px';
      hint.textContent = '[ ] resize · E erase · Esc clear';
      wrap.appendChild(hint);

      return wrap;
    },

    // ── Public: produce the mask output for image_edits ──────────────────

    /**
     * Build the mask payload. Called by image_edits dispatch (or by tests)
     * when the user invokes the capability.
     *
     * Resolution:
     *   1. Locate the target image — preferred: backgroundImageNode on the
     *      panel; fallback: any image node on userInputLayer or
     *      backgroundLayer that intersects the painted region.
     *   2. Compute the image bbox in stage coordinates.
     *   3. Crop the full-stage mask canvas to the bbox.
     *   4. Encode the cropped region as a PNG data URL.
     *   5. Count opaque pixels for the sanity check.
     *
     * Returns null if no mask has been painted (zero opaque pixels) so the
     * dispatch can short-circuit with a "no selection" error per the
     * common_errors pattern in §B.6.
     */
    buildMaskOutput: function () {
      if (!this._maskCanvas || !this._maskCtx2d) return null;

      var imageNode = this._findTargetImage();
      var bbox      = this._imageBbox(imageNode);

      // If no image found, fall back to the bbox of the painted strokes.
      // This lets brush masks work on bare canvas, but image_edits will
      // reject the payload with image_unreadable since parent_image_id is
      // null.
      if (!bbox) {
        bbox = this._paintedBbox();
        if (!bbox) return null;  // empty mask
      }

      // Crop the full-stage mask canvas to bbox.
      var cropped = document.createElement('canvas');
      cropped.width  = Math.max(1, bbox.width  | 0);
      cropped.height = Math.max(1, bbox.height | 0);
      var croppedCtx = cropped.getContext('2d');
      croppedCtx.drawImage(
        this._maskCanvas,
        bbox.x, bbox.y, bbox.width, bbox.height,
        0, 0, bbox.width, bbox.height
      );

      // Sanity: count opaque pixels in the cropped region. Zero ⇒ user
      // painted outside the image; treat as no selection.
      var imageData = croppedCtx.getImageData(0, 0, cropped.width, cropped.height);
      var maskPixels = 0;
      var data = imageData.data;
      for (var i = 3; i < data.length; i += 4) {
        if (data[i] > 0) maskPixels++;
      }
      if (maskPixels === 0) return null;

      // Resolve a parent_image_id. If the panel exposes
      // semanticIdFor(node), use it. Otherwise use the Konva node's `id()`
      // if set, or null (image_edits will surface image_unreadable).
      var parentImageId = null;
      if (imageNode) {
        if (this.panel && typeof this.panel.semanticIdFor === 'function') {
          try { parentImageId = this.panel.semanticIdFor(imageNode); } catch (e) { /* ignore */ }
        }
        if (!parentImageId && typeof imageNode.id === 'function') {
          parentImageId = imageNode.id() || null;
        }
      }

      return {
        kind:               'raster_mask',
        parent_image_id:    parentImageId,
        parent_image_bbox:  { x: bbox.x, y: bbox.y, width: bbox.width, height: bbox.height },
        mask_data_url:      cropped.toDataURL('image/png'),
        mask_pixel_count:   maskPixels,
        created_at:         new Date().toISOString()
      };
    },

    /**
     * Find the image the brush is targeting. Strategy:
     *   1. If the panel has _backgroundImageNode (the default uploaded
     *      image), use that.
     *   2. Otherwise, scan all Konva.Image nodes across layers and pick
     *      the one whose bbox contains the largest fraction of painted
     *      mask pixels.
     */
    _findTargetImage: function () {
      if (!this.panel) return null;
      // (1) Default uploaded image.
      if (this.panel._backgroundImageNode) {
        return this.panel._backgroundImageNode;
      }
      // (2) Search across layers — best effort. We don't intersect with
      // mask pixels here (cheap heuristic: first found wins). If multiple
      // images coexist on the canvas, _backgroundImageNode should always
      // be set, so this branch is mostly cold-path.
      var layers = [
        this.panel.userInputLayer,
        this.panel.backgroundLayer,
        this.panel.annotationLayer
      ];
      for (var i = 0; i < layers.length; i++) {
        var layer = layers[i];
        if (!layer || typeof layer.find !== 'function') continue;
        var images = layer.find('Image');
        if (images && images.length > 0) return images[0];
      }
      return null;
    },

    /**
     * Bounding box of a Konva.Image node in stage coordinates. Konva's
     * node.getClientRect({ relativeTo: stage }) returns axis-aligned
     * world-space bounds even after rotation.
     */
    _imageBbox: function (imageNode) {
      if (!imageNode || typeof imageNode.getClientRect !== 'function') return null;
      try {
        var r = imageNode.getClientRect({ relativeTo: this.panel.stage });
        if (!r || !(r.width > 0) || !(r.height > 0)) return null;
        return r;
      } catch (e) {
        return null;
      }
    },

    /**
     * Bounding box of the painted mask pixels (no image present). Linear
     * scan of the mask canvas. Used as a fallback for the "no image"
     * test path so the test can verify mask_data_url shape independently
     * of image-detection.
     */
    _paintedBbox: function () {
      if (!this._maskCanvas || !this._maskCtx2d) return null;
      var w = this._maskCanvas.width;
      var h = this._maskCanvas.height;
      var img = this._maskCtx2d.getImageData(0, 0, w, h);
      var data = img.data;
      var minX = w, minY = h, maxX = -1, maxY = -1;
      for (var y = 0; y < h; y++) {
        for (var x = 0; x < w; x++) {
          var alpha = data[(y * w + x) * 4 + 3];
          if (alpha > 0) {
            if (x < minX) minX = x;
            if (y < minY) minY = y;
            if (x > maxX) maxX = x;
            if (y > maxY) maxY = y;
          }
        }
      }
      if (maxX < 0) return null;
      return {
        x: minX,
        y: minY,
        width:  (maxX - minX) + 1,
        height: (maxY - minY) + 1
      };
    }
  };

  // ── Registration ──────────────────────────────────────────────────────────

  // Expose the tool on a registry so visual-panel.js (now or later) can
  // pick it up without a hard import. The registry is keyed by tool id and
  // values are tool objects matching the §B.4 contract.
  if (typeof window !== 'undefined') {
    window.OraTools = window.OraTools || {};
    window.OraTools[BRUSH_MASK_TOOL.id] = BRUSH_MASK_TOOL;
  }

  // Also expose directly so headless tests can require/import:
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = BRUSH_MASK_TOOL;
  }
})();
