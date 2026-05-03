/* ──────────────────────────────────────────────────────────────────────────
 * image-edits.js — WP-7.3.3b — `image_edits` slot wiring (replaces stub)
 *
 * The browser-side glue between three independent pieces:
 *
 *   1. capability-invocation-ui.js (WP-7.3.1)
 *        — emits a `capability-dispatch` CustomEvent on its host element
 *          when the user clicks Run. Payload: { slot, inputs, ... }.
 *
 *   2. The §7.5.1 selection tools (rect / brush / lasso)
 *        — each emits its own selection event with a `mask` envelope.
 *          Different tools use slightly different envelope shapes; this
 *          module normalizes them.
 *
 *   3. orchestrator/integrations/openai_images.py::dispatch_image_edits
 *        — server-side handler. Calls DALL-E 2's edits endpoint with
 *          a PNG image + a PNG alpha mask (transparent = edit, opaque =
 *          preserve, per OpenAI's contract).
 *
 * The conversion of the §7.5.1 polygon / rect / raster envelopes into the
 * single PNG-alpha shape OpenAI requires is the core of this WP. We do it
 * in the browser (not the server) because:
 *   (a) the source image is already mounted on the canvas — we have the
 *       Konva.Image natural dimensions and bbox without round-tripping;
 *   (b) the brush mask is already a PNG data URL; rasterizing rect/polygon
 *       to PNG is a 10-line canvas operation;
 *   (c) it keeps the server endpoint provider-agnostic — the alpha PNG is
 *       the lingua franca of every inpaint API on the planet.
 *
 * ── Mask normalization ─────────────────────────────────────────────────
 *
 * Real-world emitter shapes (cross-checked against rect-selection.tool.js,
 * brush-mask.tool.js, lasso-selection.tool.js as of 2026-04-29):
 *
 *   • rect-selection.tool.js  → {
 *       schema_version: '1.0',
 *       kind: 'rectangle',
 *       image_ref: { image_id, natural_width, natural_height, source_name },
 *       geometry: { x, y, width, height },        // image-natural pixels
 *       bbox: { x, y, width, height },
 *       created_at: ISO
 *     }
 *
 *   • brush-mask.tool.js     → {
 *       kind: 'raster_mask',
 *       parent_image_id,
 *       parent_image_bbox: { x, y, width, height },  // STAGE pixels
 *       mask_data_url: 'data:image/png;base64,...',  // white-on-transparent
 *       mask_pixel_count,
 *       created_at: ISO
 *     }
 *
 *   • lasso-selection.tool.js → {
 *       kind: 'lasso_polygon',
 *       parent_image_id,
 *       coordinate_space: 'image_local',
 *       polygon: [{x,y}, ...],       // ≥ 3 vertices, image-local pixels
 *       closed: true,
 *       authored_at: ISO
 *     }
 *
 * All three are rasterized into a single output:
 *
 *   {
 *     dataUrl: 'data:image/png;base64,...',  // alpha-PNG, naturalW × naturalH
 *     parent_image_id: string,
 *     mask_pixel_count: number
 *   }
 *
 * In the alpha PNG: PIXELS WE WANT EDITED ARE TRANSPARENT (alpha=0); the
 * rest are opaque white. This is the OpenAI / DALL-E 2 inpaint contract.
 * Note that brush-mask.tool.js paints the OPPOSITE convention (opaque =
 * masked area) so we invert it when normalizing. Rect / polygon are
 * rasterized directly with the inside transparent.
 *
 * ── Result handling ────────────────────────────────────────────────────
 *
 * Server returns a base64 PNG of the edited image. Two modes per the
 * §7.3.3b spec:
 *
 *   • `replace` (default) — substitute the source Konva.Image's bitmap
 *     with the result. Bbox unchanged.
 *   • `new_layer` — add a fresh Konva.Image alongside the source.
 *
 * The mode is read from `window.OraSettings.imageEditsResultMode` (Phase
 * 8 settings panel will write this; default is 'replace'). After the
 * insert, we fire a `canvas-state-changed` CustomEvent on the panel so
 * the §7.5.5 history / save layer picks the new state up.
 *
 * ── Error mapping ──────────────────────────────────────────────────────
 *
 * Server errors come back as { error: { code, message } }. We re-emit
 * them as `capability-error` events on the host so the WP-7.3.1 UI
 * surfaces the slot's declared fix-paths.
 *
 * ── Public API ─────────────────────────────────────────────────────────
 *
 *   window.OraImageEdits.normalizeMask(rawMask, sourceImageMeta)
 *       — unit-testable mask conversion (pure, no DOM).
 *   window.OraImageEdits.attach(opts)
 *       — wire a host element. opts: { hostEl, panel, endpointUrl, fetch }.
 *   window.OraImageEdits.detach()
 *       — tear down listeners.
 *
 * ────────────────────────────────────────────────────────────────────── */

(function (root) {
  'use strict';

  // ── Constants ────────────────────────────────────────────────────────

  var ENDPOINT_DEFAULT = '/api/capability/image_edits';
  var RESULT_MODE_DEFAULT = 'replace';   // 'replace' | 'new_layer'

  // ── DOM helpers ──────────────────────────────────────────────────────

  function _emit(targetEl, name, detail) {
    if (!targetEl || typeof CustomEvent !== 'function') return;
    var evt = new CustomEvent(name, { detail: detail, bubbles: true });
    targetEl.dispatchEvent(evt);
  }

  function _doc() {
    return (typeof document !== 'undefined') ? document : null;
  }

  // ── Pure mask normalization ──────────────────────────────────────────

  /**
   * Convert any of the three §7.5.1 mask envelope shapes into a single
   * { dataUrl, parent_image_id, mask_pixel_count } record.
   *
   * @param {Object} rawMask — emitter envelope; may be any of the three
   *   shapes documented at module top.
   * @param {Object} sourceImageMeta — { naturalWidth, naturalHeight,
   *   stageBbox: {x,y,width,height} } describing the target image. The
   *   stageBbox is required for raster_mask (which is in stage pixel
   *   space); the natural dimensions are required for all three (the
   *   normalized PNG matches the source's natural resolution so the
   *   edits API gets pixel-perfect alignment).
   * @returns {{dataUrl: string|null, parent_image_id: string|null,
   *   mask_pixel_count: number, error: string|null}}
   */
  function normalizeMask(rawMask, sourceImageMeta) {
    if (!rawMask || typeof rawMask !== 'object') {
      return { dataUrl: null, parent_image_id: null, mask_pixel_count: 0,
               error: 'mask_invalid: empty mask' };
    }

    var meta = sourceImageMeta || {};
    var naturalW = (meta.naturalWidth  | 0) || 0;
    var naturalH = (meta.naturalHeight | 0) || 0;
    if (naturalW <= 0 || naturalH <= 0) {
      return { dataUrl: null, parent_image_id: null, mask_pixel_count: 0,
               error: 'image_unreadable: source dimensions unknown' };
    }

    var doc = _doc();
    if (!doc) {
      return { dataUrl: null, parent_image_id: null, mask_pixel_count: 0,
               error: 'mask_invalid: no document context' };
    }

    var canvas = doc.createElement('canvas');
    canvas.width  = naturalW;
    canvas.height = naturalH;
    var ctx = canvas.getContext('2d');
    if (!ctx) {
      return { dataUrl: null, parent_image_id: null, mask_pixel_count: 0,
               error: 'mask_invalid: 2d context unavailable' };
    }

    // Start with an opaque-white background. We'll punch transparent
    // holes for the edit region.
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, naturalW, naturalH);

    var parentId = null;
    var pixelCount = 0;

    var kind = rawMask.kind;

    if (kind === 'rectangle' || kind === 'rect_mask') {
      // Rectangle-tool envelope. `geometry` is in image-natural pixels
      // already (rect-selection.tool.js handles the stage→natural
      // conversion). The legacy `rect_mask` shape is the stub-validator
      // form — same field via `bbox` instead.
      parentId = (rawMask.image_ref && rawMask.image_ref.image_id)
              || rawMask.parent_image_id || null;
      var geom = rawMask.geometry || rawMask.bbox || null;
      if (!geom || !(geom.width > 0) || !(geom.height > 0)) {
        return { dataUrl: null, parent_image_id: parentId, mask_pixel_count: 0,
                 error: 'mask_invalid: rectangle has no area' };
      }
      ctx.clearRect(geom.x, geom.y, geom.width, geom.height);
      pixelCount = Math.round(geom.width * geom.height);
    }
    else if (kind === 'lasso_polygon' || kind === 'polygon_mask') {
      // Lasso polygon. Points are in image-local pixels per the WP-7.5.1c
      // contract (`coordinate_space: 'image_local'`). The legacy
      // `polygon_mask` form uses array-of-pairs.
      parentId = rawMask.parent_image_id || null;
      var pts = rawMask.polygon || rawMask.points || [];
      if (!Array.isArray(pts) || pts.length < 3) {
        return { dataUrl: null, parent_image_id: parentId, mask_pixel_count: 0,
                 error: 'mask_invalid: polygon needs 3+ points' };
      }
      // Normalize point shape — accept {x,y} or [x,y].
      function _xy(p) {
        if (Array.isArray(p)) return { x: p[0], y: p[1] };
        return { x: p.x, y: p.y };
      }
      ctx.save();
      // We want the polygon interior to be transparent. Easiest path:
      // composite-out a fully-opaque polygon onto our white background.
      ctx.globalCompositeOperation = 'destination-out';
      ctx.beginPath();
      var first = _xy(pts[0]);
      ctx.moveTo(first.x, first.y);
      for (var i = 1; i < pts.length; i++) {
        var p = _xy(pts[i]);
        ctx.lineTo(p.x, p.y);
      }
      ctx.closePath();
      ctx.fill();
      ctx.restore();
      // Approximate area via shoelace formula (sanity check; the API
      // doesn't actually need this).
      var areaSum = 0;
      for (var j = 0; j < pts.length; j++) {
        var a = _xy(pts[j]);
        var b = _xy(pts[(j + 1) % pts.length]);
        areaSum += (a.x * b.y) - (b.x * a.y);
      }
      pixelCount = Math.abs(areaSum) / 2 | 0;
    }
    else if (kind === 'raster_mask') {
      // Brush mask. mask_data_url is the brush-painted region (opaque
      // white = mask; transparent = unmasked) at parent_image_bbox
      // resolution (stage pixels). We must:
      //   (1) scale stage→natural (the Konva.Image is drawn at a fit
      //       scale, but the API needs natural-resolution masks);
      //   (2) INVERT — brush convention is opaque = edit, OpenAI is
      //       transparent = edit.
      parentId = rawMask.parent_image_id || null;
      var maskUrl = rawMask.mask_data_url;
      var stageBbox = rawMask.parent_image_bbox || meta.stageBbox || null;
      if (!maskUrl || typeof maskUrl !== 'string' ||
          maskUrl.indexOf('data:image/png;base64,') !== 0) {
        return { dataUrl: null, parent_image_id: parentId, mask_pixel_count: 0,
                 error: 'mask_invalid: raster_mask missing PNG data URL' };
      }
      if (!stageBbox || !(stageBbox.width > 0) || !(stageBbox.height > 0)) {
        return { dataUrl: null, parent_image_id: parentId, mask_pixel_count: 0,
                 error: 'mask_invalid: raster_mask missing bbox' };
      }
      // Synchronous decode of an embedded PNG via <img> isn't reliable
      // across browsers — Image.decode() is async. We surface a Promise
      // for the raster path and return it as `pendingPromise` so the
      // caller can `await` it. The non-raster paths return synchronously.
      var pending = new Promise(function (resolve) {
        var img = doc.createElement('img');
        img.onload = function () {
          // Source bitmap is opaque-white-on-transparent at stageBbox
          // resolution. Draw it scaled to natural × natural, with
          // composite-out so opaque pixels become transparent in our
          // pre-filled white canvas.
          ctx.save();
          ctx.globalCompositeOperation = 'destination-out';
          ctx.drawImage(img, 0, 0, naturalW, naturalH);
          ctx.restore();

          // Count transparent pixels (= masked / to-edit area) for the
          // sanity report. Skip for very large images to keep the JS
          // path fast; the server still validates.
          var count = (rawMask.mask_pixel_count | 0) || 0;
          if (!count && naturalW * naturalH < 4_000_000) {
            try {
              var imgData = ctx.getImageData(0, 0, naturalW, naturalH);
              var data = imgData.data;
              for (var k = 3; k < data.length; k += 4) {
                if (data[k] === 0) count++;
              }
            } catch (e) { /* CORS / canvas tainted — skip count */ }
          }
          resolve({
            dataUrl: canvas.toDataURL('image/png'),
            parent_image_id: parentId,
            mask_pixel_count: count,
            error: null
          });
        };
        img.onerror = function () {
          resolve({
            dataUrl: null,
            parent_image_id: parentId,
            mask_pixel_count: 0,
            error: 'mask_invalid: raster_mask PNG decode failed'
          });
        };
        img.src = maskUrl;
      });
      return { pendingPromise: pending };
    }
    else {
      return { dataUrl: null, parent_image_id: null, mask_pixel_count: 0,
               error: 'mask_invalid: unknown kind "' + String(kind) + '"' };
    }

    // Sync path (rect / polygon) — produce the data URL now.
    var dataUrl;
    try {
      dataUrl = canvas.toDataURL('image/png');
    } catch (e) {
      return { dataUrl: null, parent_image_id: parentId, mask_pixel_count: 0,
               error: 'mask_invalid: canvas export failed' };
    }
    return {
      dataUrl: dataUrl,
      parent_image_id: parentId,
      mask_pixel_count: pixelCount,
      error: null
    };
  }

  /**
   * Resolve a normalizeMask result that may be sync OR a Promise.
   * Always returns a Promise.
   */
  function _normalizeAsync(rawMask, sourceImageMeta) {
    var result = normalizeMask(rawMask, sourceImageMeta);
    if (result && result.pendingPromise) return result.pendingPromise;
    return Promise.resolve(result);
  }

  // ── Source-image extraction ──────────────────────────────────────────

  /**
   * Pull the source image bytes + metadata off a visual-panel instance.
   * Returns null when no image is mounted.
   *
   * Shape: { dataUrl, naturalWidth, naturalHeight, stageBbox, imageId,
   *          konvaNode } — konvaNode is preserved so the result inserter
   *   can swap the bitmap in place without re-laying-out the canvas.
   */
  function readSourceImageFromPanel(panel) {
    if (!panel) return null;
    var node = panel._backgroundImageNode;
    if (!node) return null;

    var attrs = (typeof node.getAttrs === 'function') ? node.getAttrs() : (node.attrs || {});
    var naturalW = attrs.naturalWidth  | 0;
    var naturalH = attrs.naturalHeight | 0;

    // Pull a data URL from the image. Three sources, in order:
    //   1. panel._pendingImage.dataUrl (set on user upload)
    //   2. konva node's underlying image element src (an HTMLImageElement)
    //   3. node.toDataURL() — fallback that re-encodes from canvas
    var dataUrl = null;
    if (panel._pendingImage && panel._pendingImage.dataUrl) {
      dataUrl = panel._pendingImage.dataUrl;
    } else if (typeof node.image === 'function') {
      var imgEl = node.image();
      if (imgEl && imgEl.src) dataUrl = imgEl.src;
    }
    if (!dataUrl && typeof node.toDataURL === 'function') {
      try { dataUrl = node.toDataURL({ pixelRatio: 1 }); } catch (e) { /* tainted */ }
    }
    if (!dataUrl) return null;

    var stageBbox = null;
    if (typeof node.getClientRect === 'function' && panel.stage) {
      try { stageBbox = node.getClientRect({ relativeTo: panel.stage }); } catch (e) {}
    }

    var imageId = attrs.image_id
                || (typeof node.id === 'function' ? node.id() : null)
                || (typeof node.name === 'function' ? node.name() : null)
                || 'background-image';

    return {
      dataUrl: dataUrl,
      naturalWidth: naturalW || (stageBbox ? Math.round(stageBbox.width)  : 0),
      naturalHeight: naturalH || (stageBbox ? Math.round(stageBbox.height) : 0),
      stageBbox: stageBbox,
      imageId: imageId,
      konvaNode: node
    };
  }

  // ── Result insertion ─────────────────────────────────────────────────

  /**
   * Mount a base64 PNG result back onto the canvas. `mode` is 'replace'
   * (swap the source's bitmap; bbox preserved) or 'new_layer' (add a
   * fresh Konva.Image alongside).
   */
  function insertResult(panel, sourceMeta, base64Png, mode) {
    if (!panel || !sourceMeta || !base64Png) return false;
    var doc = _doc();
    if (!doc) return false;

    var dataUrl = (base64Png.indexOf('data:image/') === 0)
      ? base64Png
      : 'data:image/png;base64,' + base64Png;

    var newImg = doc.createElement('img');
    var Konva = (typeof window !== 'undefined' && window.Konva) || null;

    function _afterLoad() {
      if (mode === 'new_layer') {
        // Add as a peer Konva.Image. Same bbox as the source so the
        // user sees it lined up.
        if (!Konva || !panel.backgroundLayer) return;
        var src = sourceMeta.stageBbox || { x: 0, y: 0, width: 200, height: 200 };
        try {
          var layerImg = new Konva.Image({
            image:  newImg,
            x:      src.x,
            y:      src.y,
            width:  src.width,
            height: src.height,
            name:   'vp-image-edits-result',
            listening: false
          });
          layerImg.setAttrs({
            naturalWidth:  newImg.naturalWidth  || sourceMeta.naturalWidth,
            naturalHeight: newImg.naturalHeight || sourceMeta.naturalHeight,
            sourceName:    'image_edits-result.png'
          });
          panel.backgroundLayer.add(layerImg);
          if (typeof panel.backgroundLayer.draw === 'function') {
            panel.backgroundLayer.draw();
          }
        } catch (e) { /* swallow */ }
      } else {
        // 'replace' — swap the underlying bitmap on the existing Konva.Image.
        var node = sourceMeta.konvaNode;
        if (!node) return;
        try {
          if (typeof node.image === 'function') {
            node.image(newImg);
          }
          if (typeof node.setAttrs === 'function') {
            node.setAttrs({
              naturalWidth:  newImg.naturalWidth  || sourceMeta.naturalWidth,
              naturalHeight: newImg.naturalHeight || sourceMeta.naturalHeight
            });
          }
          var layer = (typeof node.getLayer === 'function') ? node.getLayer() : panel.backgroundLayer;
          if (layer && typeof layer.draw === 'function') layer.draw();
        } catch (e) { /* swallow */ }
      }

      // Surface a canvas-state-changed event so any history / save layer
      // can take a snapshot.
      _emit(panel.el || (typeof document !== 'undefined' ? document : null),
            'canvas-state-changed',
            { source: 'image_edits', mode: mode || RESULT_MODE_DEFAULT });
    }

    newImg.onload = _afterLoad;
    newImg.onerror = function () {
      // Non-fatal; surface as an error event so the UI can show it.
      _emit(panel.el, 'capability-error', {
        slot: 'image_edits',
        code: 'model_unavailable',
        message: 'Result image failed to decode in browser.'
      });
    };
    try { newImg.src = dataUrl; } catch (e) { /* swallow */ }
    return true;
  }

  // ── Wiring ───────────────────────────────────────────────────────────

  var _state = {
    hostEl: null,
    panel: null,
    endpointUrl: ENDPOINT_DEFAULT,
    fetchFn: null,
    onDispatch: null,
    onError: null,
    onResult: null,
    lastMaskByImageId: {},   // tracks the most recent emitted mask
    listeners: []
  };

  function _addListener(target, evt, fn) {
    if (!target || !target.addEventListener) return;
    target.addEventListener(evt, fn);
    _state.listeners.push({ target: target, evt: evt, fn: fn });
  }

  function _removeAllListeners() {
    _state.listeners.forEach(function (l) {
      try { l.target.removeEventListener(l.evt, l.fn); } catch (e) {}
    });
    _state.listeners = [];
  }

  /**
   * Capture incoming mask payloads from any of the three selection
   * tools. We listen for two event types:
   *   - 'ora:selection-mask' (rect / lasso convention via panel.el)
   *   - 'user-input'         (alternate convention; brush + lasso)
   * and keep the most recent mask per parent image. The
   * capability-invocation-ui's mask widget will read this from a
   * contextProvider we install at attach() time.
   */
  function _onSelectionMask(e) {
    if (!e || !e.detail) return;
    var detail = e.detail;
    var mask = detail.mask || detail; // user-input vs ora:selection-mask
    if (!mask || typeof mask !== 'object' || !mask.kind) return;
    var pid = (mask.image_ref && mask.image_ref.image_id)
           || mask.parent_image_id
           || '__last__';
    _state.lastMaskByImageId[pid] = mask;
    _state.lastMaskByImageId.__last__ = mask;
  }

  /**
   * Handle a `capability-dispatch` event whose slot is `image_edits`.
   */
  function _onCapabilityDispatch(e) {
    if (!e || !e.detail) return;
    var detail = e.detail;
    if (detail.slot !== 'image_edits') return;
    if (typeof e.preventDefault === 'function') e.preventDefault();

    var inputs = detail.inputs || {};
    var prompt = (inputs.prompt || '').toString();

    // Resolve the mask. Three lookup paths, in priority order:
    //   1. inputs.mask is already a usable envelope from the UI
    //   2. cached most-recent mask matching inputs.image
    //   3. cached most-recent mask of any kind
    var mask = inputs.mask;
    if (!mask || typeof mask !== 'object' || !mask.kind) {
      mask = _state.lastMaskByImageId[inputs.image]
          || _state.lastMaskByImageId.__last__
          || null;
    }

    var sourceMeta = readSourceImageFromPanel(_state.panel);
    if (!sourceMeta) {
      _emit(_state.hostEl, 'capability-error', {
        slot: 'image_edits',
        code: 'no_image_selected',
        message: 'No image is currently mounted on the canvas.'
      });
      return;
    }
    if (!prompt.trim()) {
      _emit(_state.hostEl, 'capability-error', {
        slot: 'image_edits',
        code: 'missing_required_input',
        message: 'A non-empty prompt is required.'
      });
      return;
    }
    if (!mask) {
      _emit(_state.hostEl, 'capability-error', {
        slot: 'image_edits',
        code: 'no_mask_drawn',
        message: 'Draw a mask on the image first (rectangle, brush, or lasso).'
      });
      return;
    }

    _normalizeAsync(mask, sourceMeta).then(function (normalized) {
      if (!normalized || normalized.error || !normalized.dataUrl) {
        _emit(_state.hostEl, 'capability-error', {
          slot: 'image_edits',
          code: 'mask_invalid',
          message: (normalized && normalized.error) || 'Mask normalization failed.'
        });
        return;
      }
      if (normalized.mask_pixel_count === 0) {
        _emit(_state.hostEl, 'capability-error', {
          slot: 'image_edits',
          code: 'mask_invalid',
          message: 'Mask has zero overlap with the image.'
        });
        return;
      }

      // POST to the server.
      var body = {
        slot: 'image_edits',
        prompt: prompt,
        image_data_url: sourceMeta.dataUrl,
        mask_data_url: normalized.dataUrl,
        parent_image_id: normalized.parent_image_id || sourceMeta.imageId,
        strength: (inputs.strength != null) ? inputs.strength : null,
        provider_override: inputs.provider_override || null
      };

      var fetchFn = _state.fetchFn || (typeof fetch === 'function' ? fetch : null);
      if (!fetchFn) {
        _emit(_state.hostEl, 'capability-error', {
          slot: 'image_edits',
          code: 'model_unavailable',
          message: 'fetch unavailable in this environment.'
        });
        return;
      }

      fetchFn(_state.endpointUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      }).then(function (resp) {
        var contentType = resp.headers && (resp.headers.get
          ? resp.headers.get('content-type') : resp.headers['content-type']) || '';
        if (!resp.ok) {
          return resp.json().then(function (j) {
            var err = (j && j.error) || { code: 'model_unavailable', message: 'Server returned ' + resp.status };
            _emit(_state.hostEl, 'capability-error', {
              slot: 'image_edits',
              code: err.code || 'model_unavailable',
              message: err.message || 'image_edits failed.'
            });
          }).catch(function () {
            _emit(_state.hostEl, 'capability-error', {
              slot: 'image_edits',
              code: 'model_unavailable',
              message: 'Server returned ' + resp.status
            });
          });
        }
        return resp.json().then(function (payload) {
          if (!payload || !payload.image_b64) {
            _emit(_state.hostEl, 'capability-error', {
              slot: 'image_edits',
              code: 'model_unavailable',
              message: 'Server response missing image_b64.'
            });
            return;
          }
          var mode = (root && root.OraSettings && root.OraSettings.imageEditsResultMode)
                   || RESULT_MODE_DEFAULT;
          var ok = insertResult(_state.panel, sourceMeta, payload.image_b64, mode);
          if (ok) {
            _emit(_state.hostEl, 'capability-result', {
              slot: 'image_edits',
              imageDataUrl: 'data:image/png;base64,' + payload.image_b64,
              output: payload.image_b64,
              mode: mode
            });
            if (typeof _state.onResult === 'function') {
              try { _state.onResult({ image_b64: payload.image_b64, mode: mode }); } catch (e) {}
            }
          }
        });
      }).catch(function (err) {
        _emit(_state.hostEl, 'capability-error', {
          slot: 'image_edits',
          code: 'model_unavailable',
          message: 'Network error: ' + (err && err.message ? err.message : String(err))
        });
      });
    });

    if (typeof _state.onDispatch === 'function') {
      try { _state.onDispatch(detail); } catch (e) {}
    }
  }

  /**
   * Build a contextProvider for the capability-invocation-ui mask widget.
   * Returns the most recent mask we've seen, in a shape that the widget's
   * `ctx.maskRef` heuristic accepts.
   */
  function makeContextProvider(panel) {
    return function () {
      var mask = _state.lastMaskByImageId.__last__ || null;
      var sel = panel && panel._backgroundImageNode
        ? {
            id: (panel._backgroundImageNode.attrs && panel._backgroundImageNode.attrs.image_id)
              || (typeof panel._backgroundImageNode.id === 'function'
                    ? panel._backgroundImageNode.id() : null)
              || 'background-image',
            kind: 'image'
          }
        : null;
      return {
        canvasSelection: sel,
        maskRef: mask,
        hasMask: !!mask
      };
    };
  }

  function attach(opts) {
    opts = opts || {};
    detach();   // idempotent re-attach

    _state.hostEl      = opts.hostEl || null;
    _state.panel       = opts.panel || null;
    _state.endpointUrl = opts.endpointUrl || ENDPOINT_DEFAULT;
    _state.fetchFn     = opts.fetch || null;
    _state.onDispatch  = opts.onDispatch || null;
    _state.onError     = opts.onError || null;
    _state.onResult    = opts.onResult || null;

    var panelEl = (_state.panel && _state.panel.el) || null;

    // Selection-tool listeners — both event names are emitted somewhere
    // across the three §7.5.1 tools, so listen for both.
    if (panelEl) {
      _addListener(panelEl, 'ora:selection-mask', _onSelectionMask);
      _addListener(panelEl, 'user-input',         _onSelectionMask);
    }

    // Capability dispatch listener.
    if (_state.hostEl) {
      _addListener(_state.hostEl, 'capability-dispatch', _onCapabilityDispatch);
    }

    return {
      detach: detach,
      contextProvider: makeContextProvider(_state.panel)
    };
  }

  function detach() {
    _removeAllListeners();
    _state.hostEl = null;
    _state.panel = null;
    _state.lastMaskByImageId = {};
  }

  // ── Public API ───────────────────────────────────────────────────────

  var api = {
    attach: attach,
    detach: detach,
    normalizeMask: normalizeMask,
    readSourceImageFromPanel: readSourceImageFromPanel,
    insertResult: insertResult,
    makeContextProvider: makeContextProvider,
    _state: _state,                  // for tests
    ENDPOINT_DEFAULT: ENDPOINT_DEFAULT,
    RESULT_MODE_DEFAULT: RESULT_MODE_DEFAULT
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraImageEdits = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
