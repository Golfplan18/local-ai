/**
 * capability-image-styles.js — WP-7.3.3e
 *
 * Slot wiring for the `image_styles` capability (Reference — Capability
 * Invocation Contracts §3.5). Bridges the generic UX layer
 * (capability-invocation-ui.js, WP-7.3.1) with the server-side provider
 * chain (replicate.dispatch_image_styles, WP-7.3.2c) and lands the
 * resulting image on the visual canvas.
 *
 * Mirrors the WP-7.3.3a `capability-image-generates.js` structure so the
 * two slot-wiring modules read the same. Notable deltas vs §3.1:
 *   - Two image-ref inputs (`source_image`, `style_reference`) instead of
 *     a text prompt.
 *   - Numeric `strength` in [0, 1], default 0.75.
 *   - Output is a NEW image — does not replace the source image (per
 *     contract §3.5 "new image (does not replace source)").
 *   - Slot-specific error code: `references_incompatible`.
 *
 * The module is intentionally narrow:
 *   1. Listen for `capability-dispatch` events whose `slot` is
 *      `image_styles`.
 *   2. POST the inputs to `/api/capability/image_styles`.
 *   3. Convert the server's response into a canonical canvas-state image
 *      object per WP-7.0.2's schema.
 *   4. Hand the image to the active VisualPanel for display.
 *   5. Emit `capability-result` and `canvas-state-changed` events.
 *
 * ── Public API ─────────────────────────────────────────────────────────
 *
 *   window.OraCapabilityImageStyles
 *
 *     .init({ hostEl, visualPanel, fetchImpl, endpoint })
 *     .destroy()
 *     .handleDispatch(detail)
 *     .buildCanvasObject({ base64, mimeType, anchor, canvasSize, width, height })
 */
(function (root) {
  'use strict';

  // ── Constants ─────────────────────────────────────────────────────────

  var DEFAULT_ENDPOINT = '/api/capability/image_styles';

  // Canvas-state schema constants (mirror canvas-file-format.js / .py).
  var DEFAULT_CANVAS_W = 10000;
  var DEFAULT_CANVAS_H = 10000;
  var USER_INPUT_LAYER_ID = 'user_input';

  // Default display dimensions for the resulting styled image. SDXL
  // img2img output dims mirror the source image; we don't know that
  // until the bytes arrive. The schema is dimension-agnostic so we use
  // a square 1024×1024 default and let the panel scale on display.
  var DEFAULT_W = 1024;
  var DEFAULT_H = 1024;

  // Canonical mime type. The mock path returns PNG; Replicate normally
  // returns PNG too. The server tags the response and we trust the tag.
  var DEFAULT_MIME = 'image/png';

  // Default strength from §3.5. The slot accepts [0, 1] and the server
  // clamps; we send through whatever the user provided rather than
  // double-clamping.
  var DEFAULT_STRENGTH = 0.75;

  // Error code translation: HTTP status → slot common_errors code.
  // §3.5 declares only `references_incompatible`. Non-422 statuses
  // collapse to `model_unavailable` so the user always gets a fix-path
  // button.
  function _statusToCode(status) {
    if (status === 422) return 'references_incompatible';
    if (status === 400) return 'references_incompatible';
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
    return 'img_styles_' + stamp + '_' + rand;
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
    } catch (_e) { /* fall through */ }
    return null;
  }

  function _base64ToDataUrl(base64, mimeType) {
    return 'data:' + (mimeType || DEFAULT_MIME) + ';base64,' + base64;
  }

  // Image-ref inputs from the generic UI may arrive as a data URL
  // string, a `{ data_url: ... }` object, or already as raw base64.
  // Normalise to a data URL so the server gets a consistent shape.
  function _normalizeImageRef(ref) {
    if (!ref) return null;
    if (typeof ref === 'string') {
      if (ref.indexOf('data:') === 0) return ref;
      // Treat bare base64 as PNG by default; the server only cares about
      // the bytes.
      return 'data:' + DEFAULT_MIME + ';base64,' + ref;
    }
    if (typeof ref === 'object') {
      if (typeof ref.data_url === 'string') return _normalizeImageRef(ref.data_url);
      if (typeof ref.dataUrl === 'string')  return _normalizeImageRef(ref.dataUrl);
      if (typeof ref.url === 'string')      return ref.url; // remote URL pass-through
      if (typeof ref.base64 === 'string') {
        var mime = ref.mime_type || ref.mimeType || DEFAULT_MIME;
        return 'data:' + mime + ';base64,' + ref.base64;
      }
      if (typeof ref.data === 'string') {
        var mime2 = ref.mime_type || ref.mimeType || DEFAULT_MIME;
        if (ref.data.indexOf('data:') === 0) return ref.data;
        return 'data:' + mime2 + ';base64,' + ref.data;
      }
    }
    return null;
  }

  // ── Canvas-object construction ───────────────────────────────────────

  /**
   * Build a canvas-state image object per WP-7.0.2's schema. Placement:
   *   - If `anchor` is provided, the image is centred on the anchor.
   *   - Otherwise the image is centred on the canvas.
   *
   * Per §3.5, the styled image is a NEW object — the caller does not
   * remove or replace the source image. The new object's id is fresh and
   * its placement is anchor-aware (the user usually selected the source
   * before invoking the slot, so anchoring on that selection lays the
   * styled output near where they were looking).
   */
  function buildCanvasObject(opts) {
    opts = opts || {};
    var base64 = opts.base64 || '';
    var mimeType = opts.mimeType || DEFAULT_MIME;
    var canvasSize = opts.canvasSize || { width: DEFAULT_CANVAS_W, height: DEFAULT_CANVAS_H };

    var w = (typeof opts.width === 'number' && opts.width > 0) ? opts.width : DEFAULT_W;
    var h = (typeof opts.height === 'number' && opts.height > 0) ? opts.height : DEFAULT_H;

    var cx, cy;
    if (opts.anchor && typeof opts.anchor === 'object'
        && typeof opts.anchor.x === 'number' && typeof opts.anchor.y === 'number') {
      cx = opts.anchor.x;
      cy = opts.anchor.y;
    } else {
      cx = canvasSize.width  / 2;
      cy = canvasSize.height / 2;
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

  // ── Anchor resolution ────────────────────────────────────────────────

  function _resolveAnchor(visualPanel) {
    if (!visualPanel) return null;
    if (typeof visualPanel.getSelectionAnchor === 'function') {
      try {
        var a = visualPanel.getSelectionAnchor();
        if (a && typeof a.x === 'number' && typeof a.y === 'number') return a;
      } catch (_e) { /* fall through */ }
    }
    if (typeof visualPanel.getSelectedShapeIds === 'function') {
      try {
        var ids = visualPanel.getSelectedShapeIds() || [];
        if (ids.length && typeof visualPanel._computeSelectionBBox === 'function') {
          var bbox = visualPanel._computeSelectionBBox();
          if (bbox && typeof bbox.x === 'number' && typeof bbox.y === 'number'
              && typeof bbox.width === 'number' && typeof bbox.height === 'number') {
            return { x: bbox.x + bbox.width / 2, y: bbox.y + bbox.height / 2 };
          }
        }
      } catch (_e) { /* fall through */ }
    }
    return null;
  }

  // ── Visual panel delivery ────────────────────────────────────────────

  function _deliverToPanel(visualPanel, canvasObject, blob) {
    if (!visualPanel) return Promise.resolve(null);
    if (typeof visualPanel.insertImageObject === 'function') {
      try {
        var ret = visualPanel.insertImageObject(canvasObject);
        return Promise.resolve(ret);
      } catch (e) {
        return Promise.reject(e);
      }
    }
    if (typeof visualPanel.attachImage === 'function' && blob) {
      try {
        var named = blob;
        try {
          if (typeof File === 'function') {
            named = new File([blob], 'image_styles.png', { type: blob.type || DEFAULT_MIME });
          } else {
            blob.name = 'image_styles.png';
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

  /**
   * POST the dispatch payload to the capability endpoint.
   *
   * Request body:
   *   {
   *     source_image_data_url:    string  (data URL)
   *     style_reference_data_url: string  (data URL)
   *     strength:                 number  (0-1, default 0.75)
   *     provider_override:        string  (optional)
   *     mock:                     boolean (optional)
   *   }
   *
   * Success response:
   *   200 { image_b64, provider_id, mode: 'styles', mocked? }
   *
   * Error response:
   *   non-200 { error: { code, message } }
   */
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

  function _synthError(code, message) {
    var e = new Error(message || code);
    e.code = code;
    return e;
  }

  // ── Result extraction ────────────────────────────────────────────────

  /**
   * Pull the base64 + mime out of the server response. Accepts:
   *   { image_b64: '<b64>', mime_type?: '...' }
   *   { image: { data: '<b64>', mime_type: '...' } }
   *   { data: '<b64>', mime_type: '...' }
   *   { image_data_uri: 'data:image/png;base64,<b64>' }
   */
  function _extractImage(response) {
    if (!response || typeof response !== 'object') return null;
    var base64 = null;
    var mimeType = DEFAULT_MIME;

    if (typeof response.image_b64 === 'string') {
      base64 = response.image_b64;
    } else if (response.image && typeof response.image === 'object') {
      base64 = response.image.data || response.image.b64_json || response.image.base64 || null;
      mimeType = response.image.mime_type || response.image.mimeType || mimeType;
    } else if (typeof response.data === 'string') {
      base64 = response.data;
    } else if (typeof response.image_data_uri === 'string') {
      // data URL — strip header.
      var dat = response.image_data_uri;
      var idx = dat.indexOf('base64,');
      if (idx >= 0) base64 = dat.slice(idx + 7);
      var match = /^data:([^;]+);/.exec(dat);
      if (match) mimeType = match[1];
    }

    if (!base64 || typeof base64 !== 'string') return null;

    if (base64.indexOf('data:') === 0) {
      var idx2 = base64.indexOf('base64,');
      if (idx2 >= 0) base64 = base64.slice(idx2 + 7);
    }

    mimeType = response.mime_type || response.mimeType || mimeType;
    return {
      base64:   base64,
      mimeType: mimeType,
      provider: response.provider_id || response.provider || null,
      metadata: response.metadata || null,
    };
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
      if (!detail || detail.slot !== 'image_styles') return Promise.resolve(null);
      var inputs = detail.inputs || {};

      var sourceUrl = _normalizeImageRef(inputs.source_image);
      var styleUrl  = _normalizeImageRef(inputs.style_reference);
      if (!sourceUrl || !styleUrl) {
        var err = _synthError(
          'references_incompatible',
          !sourceUrl
            ? 'image_styles requires a source_image input.'
            : 'image_styles requires a style_reference input.'
        );
        if (state.ui && typeof state.ui.renderError === 'function') {
          try { state.ui.renderError({ code: err.code, message: err.message }); } catch (_e) { /* swallow */ }
        }
        _emit(state.hostEl, 'capability-error', {
          slot:    'image_styles',
          code:    err.code,
          message: err.message,
        });
        return Promise.reject(err);
      }

      var strength = inputs.strength;
      if (typeof strength !== 'number' || isNaN(strength)) {
        strength = DEFAULT_STRENGTH;
      }

      var payload = {
        source_image_data_url:    sourceUrl,
        style_reference_data_url: styleUrl,
        strength:                 strength,
      };
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
        var anchor = _resolveAnchor(state.visualPanel);
        var canvasObject = buildCanvasObject({
          base64:   extracted.base64,
          mimeType: extracted.mimeType,
          anchor:   anchor,
        });
        var blob = _base64ToBlob(extracted.base64, extracted.mimeType);

        return _deliverToPanel(state.visualPanel, canvasObject, blob)
          .then(function () {
            var dataUrl = _base64ToDataUrl(extracted.base64, extracted.mimeType);
            var resultPayload = {
              output:       canvasObject.id,
              imageDataUrl: dataUrl,
              canvasObject: canvasObject,
              provider:     extracted.provider,
              metadata:     extracted.metadata,
            };
            if (state.ui && typeof state.ui.renderResult === 'function') {
              try { state.ui.renderResult(resultPayload); } catch (_e) { /* swallow */ }
            }
            _emit(state.hostEl, 'capability-result', {
              slot:    'image_styles',
              output:  canvasObject.id,
              canvasObject: canvasObject,
              imageDataUrl: dataUrl,
              provider: extracted.provider,
              metadata: extracted.metadata,
            });
            _emit(state.hostEl, 'canvas-state-changed', {
              source: 'image_styles',
              object: canvasObject,
              anchor: anchor,
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
          slot:    'image_styles',
          code:    code,
          message: message,
        });
        throw err;
      });
    }

    function _onCapabilityDispatch(evt) {
      if (!evt || !evt.detail) return;
      if (evt.detail.slot !== 'image_styles') return;
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
      _state:            state,   // exposed for tests only
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
    _extractImage:      _extractImage,
    _statusToCode:      _statusToCode,
    _resolveAnchor:     _resolveAnchor,
    _base64ToBlob:      _base64ToBlob,
    _base64ToDataUrl:   _base64ToDataUrl,
    _normalizeImageRef: _normalizeImageRef,
    DEFAULT_ENDPOINT:   DEFAULT_ENDPOINT,
    DEFAULT_STRENGTH:   DEFAULT_STRENGTH,
    USER_INPUT_LAYER_ID: USER_INPUT_LAYER_ID,
    _getActive: function () { return _activeController; },
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraCapabilityImageStyles = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
