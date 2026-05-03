/**
 * capability-image-generates.js — WP-7.3.3a
 *
 * Slot wiring for the `image_generates` capability. Bridges the generic
 * UX layer (capability-invocation-ui.js, WP-7.3.1) with the server-side
 * provider chain (openai_images.py / stability.py / replicate.py from
 * WP-7.3.2 a/b/c) and lands the result on the visual canvas.
 *
 * The module is intentionally narrow:
 *   1. Listen for `capability-dispatch` events whose `slot` is
 *      `image_generates`.
 *   2. POST the inputs to the server endpoint that wraps
 *      `capability_registry.invoke('image_generates', ...)`.
 *   3. Convert the server's response (raw image bytes or base64) into
 *      a canonical canvas-state image object per WP-7.0.2's schema.
 *   4. Hand the image to the active VisualPanel for display, default
 *      placement at canvas center OR — if the panel reports a selected
 *      anchor — at the anchor's position.
 *   5. Emit a `capability-result` event so the invocation UI flips out
 *      of the spinner state, and a `canvas-state-changed` event so
 *      autosave (WP-7.4.8, in flight) can persist the new object.
 *
 * Errors flowing back from the server are translated into the
 * `capability-error` shape `{ code, message, fix_path }` so the
 * invocation UI's error renderer can hang the right fix-path button on
 * them. Codes match the slot's declared `common_errors` taxonomy
 * (`model_unavailable`, `prompt_rejected`, `quota_exceeded`).
 *
 * ── Public API ─────────────────────────────────────────────────────────
 *
 *   window.OraCapabilityImageGenerates
 *
 *     .init({ hostEl, visualPanel, fetchImpl, endpoint })
 *       Mount on `hostEl` (the same host the invocation UI runs on,
 *       since `capability-dispatch` bubbles). `visualPanel` is the
 *       VisualPanel instance to land images on. `fetchImpl` defaults to
 *       `window.fetch` and exists so tests can inject mocks. `endpoint`
 *       defaults to `/api/capability/image_generates`.
 *
 *     .destroy()           — detach listener.
 *     .handleDispatch(detail)
 *                          — programmatic entry point (test introspection
 *                            and integration with hosts that prefer
 *                            method calls over events).
 *     .buildCanvasObject({ base64, mimeType, aspectRatio, anchor, canvasSize })
 *                          — pure helper, exposed for tests. Returns the
 *                            canvas-state image object that
 *                            `handleDispatch` would build from the same
 *                            inputs.
 *
 * ── Result delivery ────────────────────────────────────────────────────
 *
 * The visual panel can opt into a richer integration by exposing an
 * `insertImageObject(canvasObject)` method. When present, we call it and
 * trust the panel to mount the image and update its internal canvas
 * object list. When absent (current panel state), we fall back to
 * `attachImage(blob)` so the bytes still reach the screen via the
 * existing background-image upload pathway. Either way, we emit
 * `canvas-state-changed` carrying `{ object, anchor, source: 'image_generates' }`
 * so the autosave layer (WP-7.4.8) can persist canonical canvas-state.
 *
 * Note on `attachImage` fallback: the upload pathway lands the image on
 * Konva's backgroundLayer, not on the user_input layer where WP-7.0.2's
 * canvas-state image objects live. This is acceptable for WP-7.3.3a's
 * test criterion ("verify image arrives, lands on canvas, has correct
 * image data") because the downstream autosave layer reads the canonical
 * canvas object from our `canvas-state-changed` event, not from the
 * Konva layer. Once WP-7.4.x adds `insertImageObject` to the panel, that
 * code path supersedes the fallback automatically.
 */
(function (root) {
  'use strict';

  // ── Constants ─────────────────────────────────────────────────────────

  var DEFAULT_ENDPOINT = '/api/capability/image_generates';

  // Canvas-state schema constants (mirror canvas-file-format.js / .py).
  var DEFAULT_CANVAS_W = 10000;
  var DEFAULT_CANVAS_H = 10000;
  var USER_INPUT_LAYER_ID = 'user_input';

  // Per the slot contract §3.1, default aspect_ratio is "1:1". For the
  // pixel size of the inserted canvas object we mirror DALL-E 3's
  // longest-edge defaults (per openai_images._ASPECT_TO_DALLE3_SIZE) so
  // the canvas object's width × height match the actual generated image
  // when the OpenAI provider answers. Stability + Replicate may produce
  // different native dimensions; the schema is dimension-agnostic so a
  // mismatch doesn't break round-trip — width/height are display hints,
  // not authoritative pixel counts.
  var ASPECT_TO_DIMS = {
    '1:1':  { w: 1024, h: 1024 },
    '16:9': { w: 1792, h: 1024 },
    '9:16': { w: 1024, h: 1792 },
    '4:3':  { w: 1792, h: 1024 },
    '3:4':  { w: 1024, h: 1792 },
  };

  // Canonical mime types per the canvas-state schema's `image/<subtype>`
  // pattern. OpenAI returns PNG; we don't probe the bytes — the server
  // tags the response, and we trust the tag.
  var DEFAULT_MIME = 'image/png';

  // Error code translation: HTTP status → slot common_errors code.
  // Matches the §3.1 taxonomy. Anything unrecognised collapses to
  // `model_unavailable` so the user always gets a fix-path button.
  function _statusToCode(status) {
    if (status === 400) return 'prompt_rejected';
    if (status === 403) return 'prompt_rejected';
    if (status === 429) return 'quota_exceeded';
    if (status === 422) return 'prompt_rejected';
    return 'model_unavailable';
  }

  // ── DOM / event helpers ──────────────────────────────────────────────

  function _emit(targetEl, name, detail) {
    if (!targetEl || typeof CustomEvent !== 'function') return;
    var evt = new CustomEvent(name, { detail: detail, bubbles: true });
    targetEl.dispatchEvent(evt);
  }

  function _genId() {
    // Object ids in the canvas-state schema are non-empty strings; the
    // schema doesn't constrain shape, but we keep them inspector-friendly.
    var stamp = Date.now().toString(36);
    var rand = Math.random().toString(36).slice(2, 8);
    return 'img_gen_' + stamp + '_' + rand;
  }

  // ── Base64 / Blob helpers ────────────────────────────────────────────

  function _base64ToBlob(base64, mimeType) {
    // Decode → byte array → Blob. atob is universally available in
    // browser + jsdom; tests that don't exercise the Blob path still
    // get a synchronous canvas object.
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
      // Fall through — we still emit canvas-state, just no Blob fallback.
    }
    return null;
  }

  function _base64ToDataUrl(base64, mimeType) {
    return 'data:' + (mimeType || DEFAULT_MIME) + ';base64,' + base64;
  }

  // ── Canvas-object construction ───────────────────────────────────────

  /**
   * Build a canvas-state image object per WP-7.0.2's schema:
   *
   *   {
   *     id:    string,
   *     kind:  'image',
   *     layer: 'user_input',
   *     x, y, width, height,
   *     image_data: { mime_type, encoding: 'base64', data }
   *   }
   *
   * Placement:
   *   - If `anchor` is provided ({ x, y } in canvas coords), the image
   *     is centred on the anchor.
   *   - Otherwise the image is centred on the canvas (canvasSize.width / 2,
   *     canvasSize.height / 2).
   *
   * Default size derives from `aspectRatio` per ASPECT_TO_DIMS; falls
   * through to the 1:1 1024×1024 default for unrecognised ratios.
   */
  function buildCanvasObject(opts) {
    opts = opts || {};
    var base64 = opts.base64 || '';
    var mimeType = opts.mimeType || DEFAULT_MIME;
    var aspect = opts.aspectRatio || '1:1';
    var dims = ASPECT_TO_DIMS[aspect] || ASPECT_TO_DIMS['1:1'];
    var canvasSize = opts.canvasSize || { width: DEFAULT_CANVAS_W, height: DEFAULT_CANVAS_H };

    var w = (typeof opts.width === 'number' && opts.width > 0) ? opts.width : dims.w;
    var h = (typeof opts.height === 'number' && opts.height > 0) ? opts.height : dims.h;

    var cx, cy;
    if (opts.anchor && typeof opts.anchor === 'object'
        && typeof opts.anchor.x === 'number' && typeof opts.anchor.y === 'number') {
      cx = opts.anchor.x;
      cy = opts.anchor.y;
    } else {
      cx = canvasSize.width  / 2;
      cy = canvasSize.height / 2;
    }
    // Top-left origin of the image. Round to integers — the schema
    // accepts numbers but consumers prefer pixel-aligned values.
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

  /**
   * Pull a usable anchor out of the visual panel's selection state, if
   * any. Returns null when no anchor is selected or the panel doesn't
   * expose the API. The anchor is in canvas coordinates so the image
   * lands where the user is looking.
   */
  function _resolveAnchor(visualPanel) {
    if (!visualPanel) return null;
    // Preferred API (added alongside this WP or later): an explicit
    // method that returns { x, y } in canvas coords.
    if (typeof visualPanel.getSelectionAnchor === 'function') {
      try {
        var a = visualPanel.getSelectionAnchor();
        if (a && typeof a.x === 'number' && typeof a.y === 'number') return a;
      } catch (_e) { /* fall through */ }
    }
    // Fallback: derive from the existing selected-shape API. We pick the
    // first selected shape's bounding-box centre as the anchor when
    // available; this lets users land an image on a placeholder rect
    // without the panel needing a new method first.
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

  /**
   * Deliver the image to the panel. Prefers `insertImageObject` (the
   * canvas-state-aware path); falls back to `attachImage` (the existing
   * upload path) so the user still sees their image even when the panel
   * hasn't been upgraded yet.
   *
   * Returns a Promise that resolves to the panel's interpretation of
   * the insert (or null if the panel was absent / both paths missed).
   */
  function _deliverToPanel(visualPanel, canvasObject, blob) {
    if (!visualPanel) return Promise.resolve(null);
    if (typeof visualPanel.insertImageObject === 'function') {
      try {
        var ret = visualPanel.insertImageObject(canvasObject);
        // Method may return a Promise or a plain value.
        return Promise.resolve(ret);
      } catch (e) {
        return Promise.reject(e);
      }
    }
    // Fallback: legacy upload path. We synthesise a File-like blob so
    // attachImage's File-typed code path accepts it.
    if (typeof visualPanel.attachImage === 'function' && blob) {
      // Tag the blob with a name so the panel's indicator UI shows
      // something meaningful instead of "upload.png".
      try {
        // Some browsers expose File; in jsdom we may need to fall back
        // to setting `.name` on the blob. The panel's attachImage reads
        // `file.name` and `file.type` — a Blob with both works in
        // practice across modern browsers and jsdom.
        var named = blob;
        try {
          if (typeof File === 'function') {
            named = new File([blob], 'image_generates.png', { type: blob.type || DEFAULT_MIME });
          } else {
            // Best-effort: tag the blob with a name property.
            blob.name = 'image_generates.png';
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
   * POST the dispatch payload to the capability endpoint and parse the
   * response. The server's response shape is the contract:
   *
   *   200 OK
   *   {
   *     "image": { "data": "<base64>", "mime_type": "image/png" },
   *     "provider": "openai" | "stability" | "replicate",
   *     "metadata": { ... }   // optional
   *   }
   *
   *   Non-200
   *   {
   *     "error": { "code": "prompt_rejected" | ..., "message": "..." }
   *   }
   *
   * On HTTP failure we map the status to a slot common_errors code so
   * the invocation UI can surface a fix-path button.
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
      // Some fetch shims return a plain object (test mocks); guard
      // every accessor.
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
   * Pull the base64 + mime out of the server response. Accepts two
   * shapes for forward compatibility with whatever endpoint lands:
   *
   *   { image: { data: '<b64>', mime_type: 'image/png' } }
   *   { data: '<b64>', mime_type: 'image/png' }
   *
   * Returns { base64, mimeType, provider, metadata } or null on miss.
   */
  function _extractImage(response) {
    if (!response || typeof response !== 'object') return null;
    var img = (response.image && typeof response.image === 'object')
      ? response.image
      : response;
    var base64 = img.data || img.b64_json || img.base64 || null;
    if (!base64 || typeof base64 !== 'string') return null;
    // Strip a data: URL prefix if the server hands one over — the
    // canvas-state schema requires raw base64 (validator explicitly
    // rejects "data:" prefixes).
    if (base64.indexOf('data:') === 0) {
      var idx = base64.indexOf('base64,');
      if (idx >= 0) base64 = base64.slice(idx + 7);
    }
    var mimeType = img.mime_type || img.mimeType || response.mime_type || DEFAULT_MIME;
    return {
      base64:   base64,
      mimeType: mimeType,
      provider: response.provider || null,
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
      if (!detail || detail.slot !== 'image_generates') return Promise.resolve(null);
      var inputs = detail.inputs || {};
      var aspect = inputs.aspect_ratio || '1:1';

      var payload = {
        slot:    'image_generates',
        inputs:  inputs,
      };
      if (detail.provider_override || inputs.provider_override) {
        payload.provider_override = detail.provider_override || inputs.provider_override;
      }

      return _callServer(state.endpoint, payload, state.fetchImpl).then(function (response) {
        var extracted = _extractImage(response);
        if (!extracted) {
          throw _synthError('model_unavailable',
            'Provider returned a response with no image data.');
        }
        var anchor = _resolveAnchor(state.visualPanel);
        var canvasObject = buildCanvasObject({
          base64:       extracted.base64,
          mimeType:     extracted.mimeType,
          aspectRatio:  aspect,
          anchor:       anchor,
        });
        var blob = _base64ToBlob(extracted.base64, extracted.mimeType);

        return _deliverToPanel(state.visualPanel, canvasObject, blob)
          .then(function () {
            // Surface result to the invocation UI so the spinner clears.
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
              slot:    'image_generates',
              output:  canvasObject.id,
              canvasObject: canvasObject,
              imageDataUrl: dataUrl,
              provider: extracted.provider,
              metadata: extracted.metadata,
            });
            // Notify autosave (WP-7.4.8). The detail carries everything
            // needed to drop the object into a canvas-state file without
            // re-querying the panel.
            _emit(state.hostEl, 'canvas-state-changed', {
              source: 'image_generates',
              object: canvasObject,
              anchor: anchor,
            });
            return resultPayload;
          });
      }).catch(function (err) {
        var code = (err && err.code) || 'model_unavailable';
        var message = (err && err.message) || String(err);
        // Surface to the invocation UI's error renderer so the slot
        // contract's fix-path button shows up.
        if (state.ui && typeof state.ui.renderError === 'function') {
          try {
            state.ui.renderError({ code: code, message: message });
          } catch (_e) { /* swallow */ }
        }
        _emit(state.hostEl, 'capability-error', {
          slot:    'image_generates',
          code:    code,
          message: message,
        });
        // Re-raise so callers awaiting handleDispatch see the failure.
        throw err;
      });
    }

    function _onCapabilityDispatch(evt) {
      if (!evt || !evt.detail) return;
      // Don't let unrelated slots slip through — other wirings handle
      // image_edits / image_outpaints / etc. in their own modules.
      if (evt.detail.slot !== 'image_generates') return;
      // Fire-and-forget: the listener doesn't wait. Promise rejections
      // are swallowed here — handleDispatch already surfaced them via
      // the UI / capability-error event.
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
      handleDispatch:  handleDispatch,
      destroy:         destroy,
      setVisualPanel:  setVisualPanel,
      setUI:           setUI,
      setEndpoint:     setEndpoint,
      setFetchImpl:    setFetchImpl,
      buildCanvasObject: buildCanvasObject,
      _state:          state,   // exposed for tests only
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
    DEFAULT_ENDPOINT:   DEFAULT_ENDPOINT,
    ASPECT_TO_DIMS:     ASPECT_TO_DIMS,
    USER_INPUT_LAYER_ID: USER_INPUT_LAYER_ID,
    _getActive: function () { return _activeController; },
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraCapabilityImageGenerates = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
