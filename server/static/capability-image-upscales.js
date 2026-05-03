/**
 * capability-image-upscales.js — WP-7.3.3d
 *
 * Slot wiring for the `image_upscales` capability. Bridges the generic
 * UX layer (capability-invocation-ui.js, WP-7.3.1) with the server-side
 * provider chain (stability.py from WP-7.3.2b — conservative-tier
 * upscaler — and replicate.py for ESRGAN-style alternates) and lands
 * the higher-resolution result back on the visual canvas, replacing
 * the source object at its original anchor.
 *
 * Sibling of capability-image-generates.js (WP-7.3.3a). Listens for
 * `capability-dispatch` events whose `slot` is `image_upscales`, POSTs
 * the source image bytes + `scale_factor` to
 * `/api/capability/image_upscales`, decodes the returned base64 image,
 * and either:
 *   - calls `visualPanel.replaceImageObject(sourceId, canvasObject)`
 *     when present (preferred — preserves z-order and metadata), or
 *   - falls back to inserting via `insertImageObject` and
 *     hiding/removing the source via `removeObjectById`, or
 *   - falls back to `attachImage(blob)` so the bytes still reach the
 *     canvas via the legacy upload path.
 *
 * The contract surface and result-event taxonomy match WP-7.3.3a so
 * the invocation UI handles result/error rendering identically.
 *
 * ── Public API ─────────────────────────────────────────────────────────
 *
 *   window.OraCapabilityImageUpscales
 *
 *     .init({ hostEl, visualPanel, fetchImpl, endpoint })
 *     .destroy()
 *     .handleDispatch(detail)
 *     .buildCanvasObject({ base64, mimeType, sourceObject, scaleFactor,
 *                          anchor, canvasSize })
 *
 * ── Result delivery ────────────────────────────────────────────────────
 *
 * The slot's contract output is "image bytes; replaces source at higher
 * resolution." So unlike `image_generates`, the canvas object's anchor
 * is taken from the source object — we centre the upscaled image on
 * the source object's centre and grow the bounding box by
 * `scale_factor`. When the source object's pre-upscale dimensions
 * aren't recoverable (panel without `getObjectById`), we centre on the
 * canvas and use the upscaled image's natural dims as inferred from
 * the bytes — failing that, fall through to `2 ×` the WP-7.3.3a
 * defaults so the object still has plausible width/height.
 */
(function (root) {
  'use strict';

  // ── Constants ─────────────────────────────────────────────────────────

  var DEFAULT_ENDPOINT = '/api/capability/image_upscales';

  // Canvas-state schema constants (mirror canvas-file-format.js / .py).
  var DEFAULT_CANVAS_W = 10000;
  var DEFAULT_CANVAS_H = 10000;
  var USER_INPUT_LAYER_ID = 'user_input';

  var DEFAULT_MIME = 'image/png';
  var DEFAULT_SCALE = 2.0;

  // Error code translation: HTTP status → slot common_errors code.
  // The `image_upscales` slot's declared codes are `image_too_small`
  // and `image_too_large`. We also surface `model_unavailable` for
  // network/auth failures (consistent with sibling slots) and
  // `handler_failed` for unexpected server errors.
  function _statusToCode(status) {
    if (status === 413) return 'image_too_large';
    if (status === 422) return 'image_too_small';
    if (status === 400) return 'image_too_small';
    if (status === 429) return 'model_unavailable';
    return 'model_unavailable';
  }

  // ── DOM / event helpers ──────────────────────────────────────────────

  function _emit(targetEl, name, detail) {
    if (!targetEl || typeof CustomEvent !== 'function') return;
    var evt = new CustomEvent(name, { detail: detail, bubbles: true });
    targetEl.dispatchEvent(evt);
  }

  function _genId() {
    var stamp = Date.now().toString(36);
    var rand = Math.random().toString(36).slice(2, 8);
    return 'img_ups_' + stamp + '_' + rand;
  }

  // ── Base64 / Blob helpers ────────────────────────────────────────────

  function _base64ToBlob(base64, mimeType) {
    if (typeof atob !== 'function') return null;
    try {
      var bin = atob(base64);
      var len = bin.length;
      var arr = new Uint8Array(len);
      for (var i = 0; i < len; i++) arr[i] = bin.charCodeAt(i);
      if (typeof Blob === 'function') {
        return new Blob([arr], { type: mimeType || DEFAULT_MIME });
      }
    } catch (_e) {
      // Fall through.
    }
    return null;
  }

  function _base64ToDataUrl(base64, mimeType) {
    return 'data:' + (mimeType || DEFAULT_MIME) + ';base64,' + base64;
  }

  function _stripDataUrlPrefix(b64) {
    if (typeof b64 !== 'string') return b64;
    if (b64.indexOf('data:') !== 0) return b64;
    var idx = b64.indexOf('base64,');
    return idx >= 0 ? b64.slice(idx + 7) : b64;
  }

  // ── Source-object resolution ─────────────────────────────────────────

  /**
   * Locate the source canvas object so we can preserve its anchor and
   * grow its bounding box by `scale_factor`. Tolerates missing panel
   * APIs — returns null when nothing's available, leaving the caller
   * to fall back to canvas-centre placement.
   */
  function _resolveSourceObject(visualPanel, sourceId) {
    if (!visualPanel || !sourceId) return null;
    if (typeof visualPanel.getObjectById === 'function') {
      try {
        var obj = visualPanel.getObjectById(sourceId);
        if (obj && typeof obj === 'object') return obj;
      } catch (_e) { /* fall through */ }
    }
    // Best-effort: scan a public objects list if exposed.
    if (typeof visualPanel.getObjects === 'function') {
      try {
        var list = visualPanel.getObjects() || [];
        for (var i = 0; i < list.length; i++) {
          if (list[i] && list[i].id === sourceId) return list[i];
        }
      } catch (_e) { /* fall through */ }
    }
    return null;
  }

  // ── Canvas-object construction ───────────────────────────────────────

  /**
   * Build a canvas-state image object per WP-7.0.2's schema.
   *
   * Sizing strategy:
   *   - If `sourceObject` is available with width/height, the new
   *     object inherits the source's anchor (its centre) and grows
   *     each dimension by `scaleFactor`.
   *   - If only `width`/`height` are passed explicitly, those are used.
   *   - Otherwise we fall back to the WP-7.3.3a 1024×1024 default
   *     scaled by `scaleFactor`, centred on the canvas (or on
   *     `anchor` when supplied).
   */
  function buildCanvasObject(opts) {
    opts = opts || {};
    var base64 = opts.base64 || '';
    var mimeType = opts.mimeType || DEFAULT_MIME;
    var scale = (typeof opts.scaleFactor === 'number' && opts.scaleFactor > 1)
      ? opts.scaleFactor : DEFAULT_SCALE;
    var canvasSize = opts.canvasSize || { width: DEFAULT_CANVAS_W, height: DEFAULT_CANVAS_H };

    var w, h, cx, cy;
    var src = opts.sourceObject;

    if (src && typeof src === 'object'
        && typeof src.width === 'number' && src.width > 0
        && typeof src.height === 'number' && src.height > 0) {
      w = Math.round(src.width * scale);
      h = Math.round(src.height * scale);
      var srcX = (typeof src.x === 'number') ? src.x : (canvasSize.width - src.width) / 2;
      var srcY = (typeof src.y === 'number') ? src.y : (canvasSize.height - src.height) / 2;
      cx = srcX + src.width / 2;
      cy = srcY + src.height / 2;
    } else if (typeof opts.width === 'number' && opts.width > 0
               && typeof opts.height === 'number' && opts.height > 0) {
      w = opts.width;
      h = opts.height;
      if (opts.anchor && typeof opts.anchor.x === 'number' && typeof opts.anchor.y === 'number') {
        cx = opts.anchor.x;
        cy = opts.anchor.y;
      } else {
        cx = canvasSize.width / 2;
        cy = canvasSize.height / 2;
      }
    } else {
      w = Math.round(1024 * scale);
      h = Math.round(1024 * scale);
      if (opts.anchor && typeof opts.anchor.x === 'number' && typeof opts.anchor.y === 'number') {
        cx = opts.anchor.x;
        cy = opts.anchor.y;
      } else {
        cx = canvasSize.width / 2;
        cy = canvasSize.height / 2;
      }
    }

    var x = Math.round(cx - w / 2);
    var y = Math.round(cy - h / 2);

    return {
      id:    opts.id || _genId(),
      kind:  'image',
      layer: USER_INPUT_LAYER_ID,
      x:     x,
      y:     y,
      width: w,
      height: h,
      image_data: {
        mime_type: mimeType,
        encoding:  'base64',
        data:      base64,
      },
    };
  }

  // ── Visual panel delivery ────────────────────────────────────────────

  /**
   * Deliver the upscaled image, preferring a true replace path so the
   * source object's z-order, parent group, and any annotations linked
   * to it stay attached.
   *
   * Resolution order:
   *   1. `replaceImageObject(sourceId, newObject)` — atomic swap.
   *   2. `insertImageObject(newObject)` + `removeObjectById(sourceId)`
   *      — two-step swap for panels lacking the atomic API.
   *   3. `insertImageObject(newObject)` alone — insert without
   *      removing source (visible regression, but image lands).
   *   4. `attachImage(blob)` — legacy upload path, source remains.
   */
  function _deliverToPanel(visualPanel, canvasObject, sourceId, blob) {
    if (!visualPanel) return Promise.resolve(null);

    if (typeof visualPanel.replaceImageObject === 'function' && sourceId) {
      try {
        return Promise.resolve(visualPanel.replaceImageObject(sourceId, canvasObject));
      } catch (e) {
        return Promise.reject(e);
      }
    }

    if (typeof visualPanel.insertImageObject === 'function') {
      try {
        var insertResult = visualPanel.insertImageObject(canvasObject);
        return Promise.resolve(insertResult).then(function (val) {
          if (sourceId && typeof visualPanel.removeObjectById === 'function') {
            try {
              visualPanel.removeObjectById(sourceId);
            } catch (_e) { /* swallow — image at least landed */ }
          }
          return val;
        });
      } catch (e) {
        return Promise.reject(e);
      }
    }

    if (typeof visualPanel.attachImage === 'function' && blob) {
      try {
        var named = blob;
        try {
          if (typeof File === 'function') {
            named = new File([blob], 'image_upscales.png', { type: blob.type || DEFAULT_MIME });
          } else {
            blob.name = 'image_upscales.png';
          }
        } catch (_e) { /* ignore */ }
        return Promise.resolve(visualPanel.attachImage(named));
      } catch (e) {
        return Promise.reject(e);
      }
    }

    return Promise.resolve(null);
  }

  // ── Server call ──────────────────────────────────────────────────────

  function _synthError(code, message) {
    var e = new Error(message || code);
    e.code = code;
    return e;
  }

  function _callServer(endpoint, payload, fetchImpl) {
    var fn = fetchImpl || (typeof root !== 'undefined' && root.fetch) || (typeof fetch !== 'undefined' ? fetch : null);
    if (typeof fn !== 'function') {
      return Promise.reject(_synthError('model_unavailable',
        'fetch is not available in this environment.'));
    }
    var body = JSON.stringify(payload);
    return fn(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body,
    }).then(function (response) {
      var status = (response && typeof response.status === 'number') ? response.status : 0;
      var jsonPromise = (response && typeof response.json === 'function')
        ? response.json()
        : Promise.resolve(response && response.body ? response.body : null);
      return jsonPromise.then(function (data) {
        if (status >= 200 && status < 300) {
          return data;
        }
        var errBody = (data && data.error) || {};
        var code = errBody.code || _statusToCode(status);
        var message = errBody.message
          || ('Provider returned HTTP ' + status + '.');
        throw _synthError(code, message);
      });
    });
  }

  // ── Result extraction ────────────────────────────────────────────────

  /**
   * Pull base64 + mime out of the server response. Accepts the same
   * shapes as WP-7.3.3a plus the `image_b64` field used by the
   * existing `image_edits` server route, so we tolerate both
   * conventions while sibling sub-WPs settle on a single shape.
   */
  function _extractImage(response) {
    if (!response || typeof response !== 'object') return null;
    var img = (response.image && typeof response.image === 'object')
      ? response.image
      : response;
    var base64 = img.data || img.b64_json || img.base64 || img.image_b64 || null;
    if (!base64 || typeof base64 !== 'string') return null;
    base64 = _stripDataUrlPrefix(base64);
    var mimeType = img.mime_type || img.mimeType || response.mime_type || DEFAULT_MIME;
    return {
      base64:   base64,
      mimeType: mimeType,
      provider: response.provider || response.provider_id || null,
      metadata: response.metadata || null,
    };
  }

  // ── Source-image extraction (for the server payload) ────────────────

  /**
   * The slot contract carries `image` as a canvas-object id (image-ref).
   * To call the upscale endpoint we need the actual bytes, encoded as a
   * data URL the server can decode (mirrors the WP-7.3.3b /image_edits
   * approach). Try, in order:
   *   1. inputs.image_data_url — caller already supplied it.
   *   2. visualPanel.getObjectById(id).image_data.{mime_type,data} —
   *      reconstruct from the canvas object.
   *   3. visualPanel.exportImageDataUrl(id) — explicit panel API.
   *   4. Empty string — server will reject with missing_required_input.
   */
  function _extractSourceDataUrl(inputs, visualPanel) {
    if (inputs && typeof inputs.image_data_url === 'string' && inputs.image_data_url) {
      return inputs.image_data_url;
    }
    var src = _resolveSourceObject(visualPanel, inputs && inputs.image);
    if (src && src.image_data && typeof src.image_data.data === 'string' && src.image_data.data) {
      var mime = src.image_data.mime_type || DEFAULT_MIME;
      return 'data:' + mime + ';base64,' + src.image_data.data;
    }
    if (visualPanel && typeof visualPanel.exportImageDataUrl === 'function' && inputs && inputs.image) {
      try {
        var url = visualPanel.exportImageDataUrl(inputs.image);
        if (typeof url === 'string' && url) return url;
      } catch (_e) { /* fall through */ }
    }
    return '';
  }

  // ── Module state ─────────────────────────────────────────────────────

  function _makeController(opts) {
    opts = opts || {};
    var state = {
      hostEl:       opts.hostEl || (typeof document !== 'undefined' ? document : null),
      visualPanel:  opts.visualPanel || null,
      fetchImpl:    opts.fetchImpl || null,
      endpoint:     opts.endpoint || DEFAULT_ENDPOINT,
      ui:           opts.ui || (typeof root !== 'undefined' ? root.OraCapabilityInvocationUI : null),
      _listener:    null,
      _destroyed:   false,
    };

    function handleDispatch(detail) {
      if (state._destroyed) return Promise.resolve(null);
      if (!detail || detail.slot !== 'image_upscales') return Promise.resolve(null);
      var inputs = detail.inputs || {};
      var sourceId = inputs.image || null;
      var scaleFactor = (typeof inputs.scale_factor === 'number' && inputs.scale_factor > 1)
        ? inputs.scale_factor : DEFAULT_SCALE;

      var sourceObject = _resolveSourceObject(state.visualPanel, sourceId);
      var sourceDataUrl = _extractSourceDataUrl(inputs, state.visualPanel);

      var payload = {
        slot:          'image_upscales',
        inputs:        inputs,
        image_data_url: sourceDataUrl,
        scale_factor:  scaleFactor,
      };
      if (sourceId) payload.source_image_id = sourceId;
      if (detail.provider_override || inputs.provider_override) {
        payload.provider_override = detail.provider_override || inputs.provider_override;
      }
      if (detail.mock || inputs.mock) {
        payload.mock = true;
      }

      return _callServer(state.endpoint, payload, state.fetchImpl).then(function (response) {
        var extracted = _extractImage(response);
        if (!extracted) {
          throw _synthError('model_unavailable',
            'Provider returned a response with no image data.');
        }
        var canvasObject = buildCanvasObject({
          base64:        extracted.base64,
          mimeType:      extracted.mimeType,
          scaleFactor:   scaleFactor,
          sourceObject:  sourceObject,
        });
        var blob = _base64ToBlob(extracted.base64, extracted.mimeType);

        return _deliverToPanel(state.visualPanel, canvasObject, sourceId, blob)
          .then(function () {
            var dataUrl = _base64ToDataUrl(extracted.base64, extracted.mimeType);
            var resultPayload = {
              output:        canvasObject.id,
              imageDataUrl:  dataUrl,
              canvasObject:  canvasObject,
              provider:      extracted.provider,
              metadata:      extracted.metadata,
              replacedId:    sourceId,
              scaleFactor:   scaleFactor,
            };
            if (state.ui && typeof state.ui.renderResult === 'function') {
              try { state.ui.renderResult(resultPayload); } catch (_e) { /* swallow */ }
            }
            _emit(state.hostEl, 'capability-result', {
              slot:          'image_upscales',
              output:        canvasObject.id,
              canvasObject:  canvasObject,
              imageDataUrl:  dataUrl,
              provider:      extracted.provider,
              metadata:      extracted.metadata,
              replacedId:    sourceId,
              scaleFactor:   scaleFactor,
            });
            _emit(state.hostEl, 'canvas-state-changed', {
              source:      'image_upscales',
              object:      canvasObject,
              replacedId:  sourceId,
              scaleFactor: scaleFactor,
            });
            return resultPayload;
          });
      }).catch(function (err) {
        var code = (err && err.code) || 'model_unavailable';
        var message = (err && err.message) || String(err);
        if (state.ui && typeof state.ui.renderError === 'function') {
          try {
            state.ui.renderError({ code: code, message: message });
          } catch (_e) { /* swallow */ }
        }
        _emit(state.hostEl, 'capability-error', {
          slot:    'image_upscales',
          code:    code,
          message: message,
        });
        throw err;
      });
    }

    function _onCapabilityDispatch(evt) {
      if (!evt || !evt.detail) return;
      if (evt.detail.slot !== 'image_upscales') return;
      handleDispatch(evt.detail).catch(function () { /* surfaced */ });
    }

    function destroy() {
      if (state._destroyed) return;
      state._destroyed = true;
      if (state.hostEl && state._listener) {
        state.hostEl.removeEventListener('capability-dispatch', state._listener);
      }
      state._listener = null;
    }

    function setVisualPanel(panel) { state.visualPanel = panel || null; }
    function setUI(ui)             { state.ui = ui || null; }
    function setEndpoint(ep)       { state.endpoint = ep || DEFAULT_ENDPOINT; }
    function setFetchImpl(fn)      { state.fetchImpl = fn || null; }

    if (state.hostEl && typeof state.hostEl.addEventListener === 'function') {
      state._listener = _onCapabilityDispatch;
      state.hostEl.addEventListener('capability-dispatch', state._listener);
    }

    return {
      handleDispatch:    handleDispatch,
      destroy:           destroy,
      setVisualPanel:    setVisualPanel,
      setUI:             setUI,
      setEndpoint:       setEndpoint,
      setFetchImpl:      setFetchImpl,
      buildCanvasObject: buildCanvasObject,
      _state:            state,
    };
  }

  // ── Module-level "active" controller ─────────────────────────────────

  var _activeController = null;

  function init(opts) {
    if (_activeController) {
      try { _activeController.destroy(); } catch (_e) { /* ignore */ }
    }
    _activeController = _makeController(opts || {});
    return _activeController;
  }

  function _delegate(method) {
    return function () {
      if (!_activeController) return null;
      return _activeController[method].apply(_activeController, arguments);
    };
  }

  var api = {
    init:               init,
    handleDispatch:     _delegate('handleDispatch'),
    setVisualPanel:     _delegate('setVisualPanel'),
    setUI:              _delegate('setUI'),
    setEndpoint:        _delegate('setEndpoint'),
    setFetchImpl:       _delegate('setFetchImpl'),
    destroy: function () {
      if (_activeController) _activeController.destroy();
      _activeController = null;
    },
    buildCanvasObject:  buildCanvasObject,
    // Test hooks
    _extractImage:         _extractImage,
    _statusToCode:         _statusToCode,
    _resolveSourceObject:  _resolveSourceObject,
    _extractSourceDataUrl: _extractSourceDataUrl,
    _base64ToBlob:         _base64ToBlob,
    _base64ToDataUrl:      _base64ToDataUrl,
    DEFAULT_ENDPOINT:      DEFAULT_ENDPOINT,
    DEFAULT_SCALE:         DEFAULT_SCALE,
    USER_INPUT_LAYER_ID:   USER_INPUT_LAYER_ID,
    _getActive: function () { return _activeController; },
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraCapabilityImageUpscales = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
