/**
 * capability-video-generates.js — WP-7.3.4a
 *
 * Slot wiring for the `video_generates` capability. Bridges the generic
 * UX layer (capability-invocation-ui.js, WP-7.3.1) with the server-side
 * provider chain (replicate.py::dispatch_video_generates from WP-7.3.2c)
 * and the async job-queue plumbing (WP-7.6.1 + WP-7.6.2 + WP-7.6.3) that
 * lands the eventual video result in the chat output stream.
 *
 * The contract differs from WP-7.3.3a (`image_generates`) in one
 * load-bearing way: this slot is **async**. The server's POST handler
 * does not return image bytes — it enqueues a job, returns the queue's
 * job dict (`{id, status: 'queued', ...}`), and the polling thread
 * later transitions the job to ``in_progress`` → ``complete``/``failed``.
 * Result delivery is owned by WP-7.6.2 (chat output stream entry) +
 * job-queue.js (queue strip + canvas placeholder).
 *
 * What this module does:
 *
 *   1. Listen for `capability-dispatch` events whose `slot` is
 *      `video_generates`.
 *   2. Optionally compute a `placeholder_anchor` from the visual panel's
 *      current selection so the canvas placeholder lands at the user's
 *      intent point.
 *   3. POST { slot, inputs, placeholder_anchor? } to the server endpoint
 *      that wraps `capability_registry.invoke('video_generates', ...)`.
 *   4. On a 200 response (a serialized job dict), emit an immediate
 *      `capability-result` carrying the job + a "queued" status flag so
 *      the invocation UI can flip out of the "Sending…" state into the
 *      "Sent — will arrive when ready" badge.
 *   5. Synthesise a synthetic `ora:job_status` event with the freshly
 *      dispatched job so OraJobQueue can render the strip row +
 *      placeholder *immediately* — without waiting for the SSE bridge to
 *      relay the server-side `job_dispatched` event back. The real SSE
 *      frame arrives microseconds later and is idempotent (job-queue.js
 *      keys on job.id).
 *   6. Errors from the dispatch path translate to the slot's declared
 *      `common_errors` taxonomy (`prompt_rejected`, `quota_exceeded`,
 *      `model_unavailable`).
 *
 * What this module does **not** do:
 *
 *   - It does not insert a video element on the canvas at completion
 *     time. Per §13.3 / WP-7.6.2, completion handling lives in
 *     chat-panel.js's job-result renderer, which already handles the
 *     `result_ref = { video_url }` / `{ url }` shapes for video
 *     completion. Layering a duplicate insert here would race the SSE
 *     bridge.
 *   - It does not insert a real Konva video object. The persistent
 *     placeholder rendered by job-queue.js *is* the canvas-state video
 *     placeholder per the WP brief, and it transitions colour as the
 *     status advances. We do, however, emit a `canvas-state-changed`
 *     event tagged `source: 'video_generates_pending'` carrying a
 *     pending-video canvas object so autosave (WP-7.4.8) can persist
 *     the placeholder across reloads if needed. The object's
 *     `kind` is `video` and its `pending: true` flag distinguishes it
 *     from a fully-loaded video object that future WP-7.x will land.
 *
 * ── Public API ─────────────────────────────────────────────────────────
 *
 *   window.OraCapabilityVideoGenerates
 *
 *     .init({ hostEl, visualPanel, fetchImpl, endpoint, ui })
 *       Mount on `hostEl` (the same host the invocation UI runs on,
 *       since `capability-dispatch` bubbles). `visualPanel` is the
 *       VisualPanel instance used purely for selection-anchor
 *       resolution. `fetchImpl` defaults to `window.fetch` and exists
 *       so tests can inject mocks. `endpoint` defaults to
 *       `/api/capability/video_generates`. `ui` defaults to
 *       `window.OraCapabilityInvocationUI` so the invocation UI's
 *       `renderResult` / `renderError` hooks fire.
 *
 *     .destroy()           — detach listener.
 *     .handleDispatch(detail)
 *                          — programmatic entry point (test introspection
 *                            and integration with hosts that prefer
 *                            method calls over events).
 *     .buildPendingCanvasObject({ jobId, anchor, canvasSize, duration, resolution })
 *                          — pure helper. Returns a canvas-state video
 *                            object with `pending: true`, mirroring the
 *                            shape WP-7.0.2's schema-extension for
 *                            video objects will land. Exposed for tests.
 *     .resolvePlaceholderAnchor(visualPanel)
 *                          — pure helper. Returns the
 *                            `placeholder_anchor` rect derived from the
 *                            panel's selection (or the canvas centre).
 *
 * ── Coordinated with WP-7.3.4b ─────────────────────────────────────────
 *
 * `style_trains` (the parallel WP) shares this async-result-insertion
 * pattern. To keep both wirings symmetrical, the synthetic
 * `ora:job_status` emit + the placeholder anchor convention are stable
 * here so WP-7.3.4b can lift the same scaffold without divergence.
 */
(function (root) {
  'use strict';

  // ── Constants ─────────────────────────────────────────────────────────

  var SLOT = 'video_generates';
  var DEFAULT_ENDPOINT = '/api/capability/video_generates';

  // Canvas-state schema constants (mirror canvas-file-format.js / .py).
  // The video kind is a forward-compatible extension; placeholder
  // dimensions match WP-7.6.1's job-queue.js placeholder defaults so the
  // pending object and the queue placeholder occupy the same rect.
  var DEFAULT_CANVAS_W = 10000;
  var DEFAULT_CANVAS_H = 10000;
  var USER_INPUT_LAYER_ID = 'user_input';

  // Resolution → canvas-pixel size mapping for the pending placeholder.
  // The canvas placeholder is a visual affordance, not authoritative
  // pixel geometry; defaults match a 16:9 framing per common video
  // resolutions. 1:1 placeholder if resolution is unrecognised.
  var RESOLUTION_TO_DIMS = {
    '480p':  { w:  854, h:  480 },
    '720p':  { w: 1280, h:  720 },
    '1080p': { w: 1920, h: 1080 },
    '4k':    { w: 3840, h: 2160 },
  };

  var DEFAULT_PLACEHOLDER_DIMS = { w: 768, h: 432 };  // 16:9 fallback

  // Error code translation: HTTP status → slot common_errors code.
  // §3.9 declares two: `quota_exceeded` (429) and `prompt_rejected`
  // (400/403/422). Anything else collapses to `model_unavailable`.
  function _statusToCode(status) {
    if (status === 400) return 'prompt_rejected';
    if (status === 403) return 'prompt_rejected';
    if (status === 422) return 'prompt_rejected';
    if (status === 429) return 'quota_exceeded';
    return 'model_unavailable';
  }

  // ── DOM / event helpers ──────────────────────────────────────────────

  function _emit(targetEl, name, detail) {
    if (!targetEl || typeof CustomEvent !== 'function') return;
    var evt = new CustomEvent(name, { detail: detail, bubbles: true });
    targetEl.dispatchEvent(evt);
  }

  /**
   * Emit a synthetic `ora:job_status` window-level CustomEvent so
   * OraJobQueue renders the strip + placeholder without waiting for the
   * SSE round-trip. job-queue.js's `_handleEvent` is idempotent — when
   * the real SSE frame arrives, it updates the same entry in place.
   */
  function _emitJobStatusToWindow(job, conversationId) {
    if (typeof window === 'undefined' || typeof CustomEvent !== 'function') return;
    try {
      var detail = {
        type: 'job_dispatched',
        conversation_id: conversationId || null,
        job: job,
      };
      var evt = new CustomEvent('ora:job_status', { detail: detail });
      window.dispatchEvent(evt);
    } catch (_e) { /* swallow — non-critical hint to OraJobQueue */ }
  }

  function _genId() {
    var stamp = Date.now().toString(36);
    var rand = Math.random().toString(36).slice(2, 8);
    return 'vid_pending_' + stamp + '_' + rand;
  }

  function _synthError(code, message) {
    var e = new Error(message || code);
    e.code = code;
    return e;
  }

  // ── Anchor resolution ────────────────────────────────────────────────

  /**
   * Derive a `placeholder_anchor` rect ({x, y, width, height}) the
   * server stores on the job and job-queue.js renders against. We pick
   * panel selection over canvas centre so the placeholder lands where
   * the user is focused. Returns null when no panel/anchor is available
   * — the server treats that as "no canvas placeholder requested".
   */
  function resolvePlaceholderAnchor(visualPanel, dims) {
    if (!visualPanel) return null;
    dims = dims || DEFAULT_PLACEHOLDER_DIMS;
    var w = (dims && typeof dims.w === 'number' && dims.w > 0) ? dims.w : DEFAULT_PLACEHOLDER_DIMS.w;
    var h = (dims && typeof dims.h === 'number' && dims.h > 0) ? dims.h : DEFAULT_PLACEHOLDER_DIMS.h;

    // Preferred API: explicit anchor in canvas coords.
    if (typeof visualPanel.getSelectionAnchor === 'function') {
      try {
        var a = visualPanel.getSelectionAnchor();
        if (a && typeof a.x === 'number' && typeof a.y === 'number') {
          return {
            x: Math.round(a.x - w / 2),
            y: Math.round(a.y - h / 2),
            width: w,
            height: h,
          };
        }
      } catch (_e) { /* fall through */ }
    }
    // Legacy fallback: derive from selected-shape bbox centre.
    if (typeof visualPanel.getSelectedShapeIds === 'function') {
      try {
        var ids = visualPanel.getSelectedShapeIds() || [];
        if (ids.length && typeof visualPanel._computeSelectionBBox === 'function') {
          var bbox = visualPanel._computeSelectionBBox();
          if (bbox && typeof bbox.x === 'number' && typeof bbox.y === 'number'
              && typeof bbox.width === 'number' && typeof bbox.height === 'number') {
            var cx = bbox.x + bbox.width / 2;
            var cy = bbox.y + bbox.height / 2;
            return {
              x: Math.round(cx - w / 2),
              y: Math.round(cy - h / 2),
              width: w,
              height: h,
            };
          }
        }
      } catch (_e) { /* fall through */ }
    }
    // No selection — centre on the canvas (canvas size from panel if it
    // exposes one, otherwise the default 10000×10000 canvas).
    var canvasW = DEFAULT_CANVAS_W;
    var canvasH = DEFAULT_CANVAS_H;
    if (typeof visualPanel.getCanvasSize === 'function') {
      try {
        var sz = visualPanel.getCanvasSize();
        if (sz && typeof sz.width === 'number' && typeof sz.height === 'number') {
          canvasW = sz.width;
          canvasH = sz.height;
        }
      } catch (_e) { /* default */ }
    }
    return {
      x: Math.round(canvasW / 2 - w / 2),
      y: Math.round(canvasH / 2 - h / 2),
      width: w,
      height: h,
    };
  }

  // ── Pending canvas-object construction ───────────────────────────────

  /**
   * Build a canvas-state pending-video object. Schema:
   *
   *   {
   *     id:        string,
   *     kind:      'video',
   *     layer:     'user_input',
   *     pending:   true,
   *     job_id:    string,            // links to the queue job
   *     x, y, width, height,
   *     metadata:  { duration?, resolution?, style? }
   *   }
   *
   * Once the job completes, WP-7.6.2 lands the result_ref (a video URL
   * or video bytes) in the chat output stream. A future WP will lift
   * the resolved video onto the canvas in place of the pending object;
   * for now the pending object is a marker for autosave so the user's
   * canvas state survives a reload while the job is in flight.
   */
  function buildPendingCanvasObject(opts) {
    opts = opts || {};
    var resolution = opts.resolution || null;
    var dims = (resolution && RESOLUTION_TO_DIMS[resolution])
      ? RESOLUTION_TO_DIMS[resolution]
      : DEFAULT_PLACEHOLDER_DIMS;
    var w = (typeof opts.width === 'number' && opts.width > 0) ? opts.width : dims.w;
    var h = (typeof opts.height === 'number' && opts.height > 0) ? opts.height : dims.h;
    var canvasSize = opts.canvasSize || { width: DEFAULT_CANVAS_W, height: DEFAULT_CANVAS_H };

    var cx, cy;
    if (opts.anchor && typeof opts.anchor === 'object'
        && typeof opts.anchor.x === 'number' && typeof opts.anchor.y === 'number') {
      // anchor here is a placeholder_anchor rect ({x,y,width,height} —
      // top-left). Centre derived from rect centre.
      var ax = opts.anchor.x;
      var ay = opts.anchor.y;
      var aw = (typeof opts.anchor.width  === 'number') ? opts.anchor.width  : w;
      var ah = (typeof opts.anchor.height === 'number') ? opts.anchor.height : h;
      cx = ax + aw / 2;
      cy = ay + ah / 2;
    } else {
      cx = canvasSize.width  / 2;
      cy = canvasSize.height / 2;
    }
    var x = Math.round(cx - w / 2);
    var y = Math.round(cy - h / 2);

    var metadata = {};
    if (typeof opts.duration === 'number')        metadata.duration   = opts.duration;
    if (typeof opts.resolution === 'string')      metadata.resolution = opts.resolution;
    if (typeof opts.style === 'string' && opts.style) metadata.style  = opts.style;

    return {
      id:      opts.id || _genId(),
      kind:    'video',
      layer:   USER_INPUT_LAYER_ID,
      pending: true,
      job_id:  opts.jobId || null,
      x:       x,
      y:       y,
      width:   w,
      height:  h,
      metadata: metadata,
    };
  }

  // ── Server call ──────────────────────────────────────────────────────

  /**
   * POST the dispatch payload to the capability endpoint and parse the
   * response. The server's response shape is the contract:
   *
   *   200 OK
   *   {
   *     "job": {
   *       "id": "<uuid>",
   *       "status": "queued",
   *       "capability": "video_generates",
   *       "parameters": { ... },
   *       "placeholder_anchor": { ... } | null,
   *       "dispatched_at": <epoch>,
   *       ...
   *     },
   *     "conversation_id": "<id>" | null
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
    var fn = fetchImpl
      || (typeof root !== 'undefined' && root.fetch)
      || (typeof fetch !== 'undefined' ? fetch : null);
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

  /**
   * Pull the job dict out of the server response. Accepts two shapes:
   *
   *   { job: { id, status, ... }, conversation_id }
   *   { id, status, capability, ... }   // direct job dict
   *
   * Returns { job, conversationId } or null on miss.
   */
  function _extractJob(response) {
    if (!response || typeof response !== 'object') return null;
    var job = (response.job && typeof response.job === 'object')
      ? response.job
      : response;
    if (!job || typeof job.id !== 'string' || !job.id) return null;
    return {
      job: job,
      conversationId: response.conversation_id || job.conversation_id || null,
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
      if (!detail || detail.slot !== SLOT) return Promise.resolve(null);
      var inputs = detail.inputs || {};

      // Compute a placeholder anchor sized to the requested resolution
      // (or the 16:9 default). Server stores it on the job; job-queue.js
      // renders the live placeholder against it.
      var resolution = inputs.resolution || null;
      var phDims = (resolution && RESOLUTION_TO_DIMS[resolution])
        ? RESOLUTION_TO_DIMS[resolution]
        : DEFAULT_PLACEHOLDER_DIMS;
      var anchor = resolvePlaceholderAnchor(state.visualPanel, phDims);

      var payload = {
        slot:    SLOT,
        inputs:  inputs,
      };
      if (anchor) payload.placeholder_anchor = anchor;
      if (detail.provider_override || inputs.provider_override) {
        payload.provider_override = detail.provider_override || inputs.provider_override;
      }
      if (detail.conversation_id) {
        payload.conversation_id = detail.conversation_id;
      }

      return _callServer(state.endpoint, payload, state.fetchImpl).then(function (response) {
        var extracted = _extractJob(response);
        if (!extracted) {
          throw _synthError('model_unavailable',
            'Server returned no job descriptor for video_generates.');
        }
        var job = extracted.job;

        // Build the pending canvas object so autosave can persist the
        // user's intent across a reload while the job is in flight.
        var pendingObj = buildPendingCanvasObject({
          jobId:      job.id,
          anchor:     anchor,
          duration:   inputs.duration,
          resolution: resolution,
          style:      inputs.style,
        });

        // Render the queue strip + canvas placeholder immediately.
        // Synthesises the same job_dispatched event the SSE bridge
        // would deliver; the real SSE frame arrives microseconds later
        // and updates the same entry idempotently (job-queue.js keys
        // on job.id).
        _emitJobStatusToWindow(job, extracted.conversationId);

        // Surface the queued state to the invocation UI so it flips out
        // of the spinner into the "Sent — will arrive when ready" badge.
        var resultPayload = {
          slot:           SLOT,
          execution:      'async',
          status:         job.status || 'queued',
          jobId:          job.id,
          job:            job,
          pendingObject:  pendingObj,
          conversationId: extracted.conversationId,
        };
        if (state.ui && typeof state.ui.renderResult === 'function') {
          try { state.ui.renderResult(resultPayload); } catch (_e) { /* swallow */ }
        }
        _emit(state.hostEl, 'capability-result', {
          slot:          SLOT,
          execution:     'async',
          status:        job.status || 'queued',
          jobId:         job.id,
          job:           job,
          pendingObject: pendingObj,
        });
        // Notify autosave so the pending object survives reload. Tag
        // source so consumers can distinguish a synced sync-result
        // insert from an async-pending placeholder.
        _emit(state.hostEl, 'canvas-state-changed', {
          source: 'video_generates_pending',
          object: pendingObj,
          anchor: anchor,
          jobId:  job.id,
        });
        return resultPayload;
      }).catch(function (err) {
        var code = (err && err.code) || 'model_unavailable';
        var message = (err && err.message) || String(err);
        if (state.ui && typeof state.ui.renderError === 'function') {
          try {
            state.ui.renderError({ code: code, message: message });
          } catch (_e) { /* swallow */ }
        }
        _emit(state.hostEl, 'capability-error', {
          slot:    SLOT,
          code:    code,
          message: message,
        });
        throw err;
      });
    }

    function _onCapabilityDispatch(evt) {
      if (!evt || !evt.detail) return;
      if (evt.detail.slot !== SLOT) return;
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
      handleDispatch:           handleDispatch,
      destroy:                  destroy,
      setVisualPanel:           setVisualPanel,
      setUI:                    setUI,
      setEndpoint:              setEndpoint,
      setFetchImpl:             setFetchImpl,
      buildPendingCanvasObject: buildPendingCanvasObject,
      resolvePlaceholderAnchor: resolvePlaceholderAnchor,
      _state:                   state,   // exposed for tests only
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
    init:                     init,
    handleDispatch:           _delegate('handleDispatch'),
    setVisualPanel:           _delegate('setVisualPanel'),
    setUI:                    _delegate('setUI'),
    setEndpoint:              _delegate('setEndpoint'),
    setFetchImpl:             _delegate('setFetchImpl'),
    destroy: function () {
      if (_activeController) _activeController.destroy();
      _activeController = null;
    },
    buildPendingCanvasObject: buildPendingCanvasObject,
    resolvePlaceholderAnchor: resolvePlaceholderAnchor,
    // Test hooks
    _extractJob:              _extractJob,
    _statusToCode:            _statusToCode,
    DEFAULT_ENDPOINT:         DEFAULT_ENDPOINT,
    RESOLUTION_TO_DIMS:       RESOLUTION_TO_DIMS,
    DEFAULT_PLACEHOLDER_DIMS: DEFAULT_PLACEHOLDER_DIMS,
    USER_INPUT_LAYER_ID:      USER_INPUT_LAYER_ID,
    SLOT:                     SLOT,
    _getActive: function () { return _activeController; },
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraCapabilityVideoGenerates = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
