/**
 * capability-style-trains.js — WP-7.3.4b
 *
 * Slot wiring for the async ``style_trains`` capability. Bridges the
 * generic UX layer (capability-invocation-ui.js, WP-7.3.1) with the
 * server-side dispatcher (replicate.dispatch_style_trains, WP-7.3.2c)
 * and — crucially for §3.10 — registers the resulting style adapter so
 * the ``image_styles`` slot's ``style_reference`` picker can offer it.
 *
 * The slot's contract per ``~/ora/config/capabilities.json``:
 *
 *   required_inputs:  reference_images (images-list, min 3),
 *                     name (text)
 *   optional_inputs:  training_depth (enum: quick / standard / deep)
 *   output:           style-adapter-id  — registered for use in image_styles
 *   execution_pattern: async
 *   common_errors:    insufficient_examples, training_failed
 *
 * ── Async lifecycle ────────────────────────────────────────────────────
 *
 *  1. UI submit → ``capability-dispatch`` event with slot=``style_trains``.
 *     We POST inputs to ``/api/capability/style_trains``; the server
 *     calls ``capability_registry.invoke('style_trains', ...)`` which
 *     hits the Replicate dispatcher and files a job through the
 *     WP-7.6.1 queue. The endpoint returns the job dict
 *     (``{id, status, capability, ...}``).
 *  2. The WP-7.6.1 queue UI (job-queue.js) + WP-7.6.2 chat-stream
 *     entry (chat-panel.js) drive status visualization off the
 *     ``ora:job_status`` window event the SSE bridge dispatches.
 *     We don't reproduce that chrome here — we just listen to the
 *     same event so we can act when our slot's job reaches ``complete``.
 *  3. On terminal ``complete`` for capability=``style_trains``, we:
 *       a) read ``job.result_ref`` (string adapter/version id, or
 *          object { url } / { version } depending on Replicate's
 *          output shape — see ``_extractAdapterId`` for the cascade)
 *       b) compose a registry record from the ``parameters`` we filed
 *          (name, reference image data) plus the resolved adapter id
 *       c) call ``OraStyleAdapterRegistry.add(record)`` so future
 *          ``image_styles`` invocations see it as an option
 *       d) fire ``capability-result`` so the invocation UI can render
 *          the adapter card (output type ``style-adapter-id``)
 *
 * ── Pending / longer-than-typical timeline ─────────────────────────────
 *
 * Training is minutes-to-hours. The generic invocation UI shows the
 * standard async badge ("Sent — will arrive when ready") on submit;
 * we layer a longer-form status note in the form's status area
 * because — unlike video_generates which finishes in tens of seconds —
 * users need a clear cue that this is a multi-minute operation. The
 * note disappears when the job reaches a terminal state.
 *
 * ── Style-adapter registry ─────────────────────────────────────────────
 *
 * ``window.OraStyleAdapterRegistry`` is created lazily (also exported
 * here so the registry is guaranteed present when this module loads).
 * Surface:
 *
 *   .add(record)                    — register a new adapter; emits
 *                                     ``ora:style-adapter-registered``
 *                                     on window.
 *   .remove(adapterId)              — drop an adapter from the registry.
 *   .list()                         — return an array of records.
 *   .get(adapterId)                 — return a single record or null.
 *   .clear()                        — wipe the registry (test hook).
 *   .subscribe(handler)             — register a listener; returns
 *                                     unsubscribe fn. Handler receives
 *                                     ``{type, record|adapterId}``.
 *
 * Record shape:
 *   { id, name, created_at, swatches[], capability_metadata? }
 *     - id           string (adapter / version id)
 *     - name         string (user-supplied display name)
 *     - created_at   epoch seconds
 *     - swatches[]   array of dataURLs sourced from the reference
 *                    images the user supplied (top-N, defaults to 3)
 *     - capability_metadata  arbitrary blob from the dispatcher
 *                    (training_depth, etc.) — opaque to the registry.
 *
 * The image_styles slot's style_reference picker is wired by
 * the WP-7.3.3-family handler for that slot (when it lands).
 * Until then, we expose ``getStyleReferenceOptions()`` which the
 * picker can read.
 *
 * ── Adapter selection bridge ───────────────────────────────────────────
 *
 * Clicking an adapter swatch on the result card emits
 * ``ora:style-adapter-selected`` with detail ``{adapterId}`` and, as
 * a convenience, sets the value on the active invocation UI's
 * ``style_reference`` input if and only if the active slot is
 * ``image_styles``. This avoids tight coupling — listeners can plumb
 * the id wherever they want — while making the common case (user
 * has image_styles open) work without ceremony.
 *
 * ── Public API ─────────────────────────────────────────────────────────
 *
 *   window.OraCapabilityStyleTrains
 *
 *     .init({ hostEl, fetchImpl, endpoint, ui })
 *       Mount on ``hostEl`` (same host the invocation UI runs on).
 *       ``fetchImpl`` defaults to ``window.fetch`` (test injection).
 *       ``endpoint`` defaults to ``/api/capability/style_trains``.
 *       ``ui`` defaults to ``window.OraCapabilityInvocationUI`` so we
 *       can call ``renderResult`` / ``renderError`` on it directly.
 *
 *     .destroy()
 *     .handleDispatch(detail)              — programmatic entry point.
 *     .registerCompletedJob(job, params)   — exposed for the WP-7.6.1
 *                                             rehydration path: when a
 *                                             job already-complete on
 *                                             page load is hydrated,
 *                                             this re-registers its
 *                                             adapter without re-running
 *                                             the dispatch.
 *
 *   window.OraStyleAdapterRegistry  — see above.
 *
 * ── Errors ─────────────────────────────────────────────────────────────
 *
 * Sync errors from the POST (the registry refused to dispatch, the
 * server crashed, etc.) translate to the slot's common_errors taxonomy:
 *   400 → insufficient_examples (when message indicates so) /
 *          training_failed (otherwise)
 *   429 → training_failed
 *   anything else → training_failed
 *
 * Async failures (the job transitioned to ``failed``) are surfaced
 * here as a ``capability-error`` event with code ``training_failed``
 * once the chat-stream entry's ``failed`` final state is observed.
 */
(function (root) {
  'use strict';

  // ── Constants ─────────────────────────────────────────────────────────

  var DEFAULT_ENDPOINT = '/api/capability/style_trains';
  var SLOT_NAME = 'style_trains';
  var IMAGE_STYLES_SLOT = 'image_styles';

  // The pending status note we layer on top of the generic async badge.
  // §3.10 calls out the multi-minute timeline; the badge alone reads
  // identical to a 30-second video_generates job.
  var PENDING_TIMELINE_NOTE =
    'Style training takes several minutes — you can keep working; ' +
    'the new adapter will appear in image_styles when ready.';

  // Cap on swatches stored per record. The reference set may be 3+ images;
  // we keep the top-N to avoid bloating localStorage when persistence
  // lands later. The result card still shows up to MAX_SWATCH_COUNT.
  var MAX_SWATCH_COUNT = 3;

  // ── Small helpers ─────────────────────────────────────────────────────

  function _emit(targetEl, name, detail) {
    if (!targetEl || typeof CustomEvent !== 'function') return;
    var evt = new CustomEvent(name, { detail: detail, bubbles: true });
    targetEl.dispatchEvent(evt);
  }

  function _windowEmit(name, detail) {
    if (typeof window === 'undefined') return;
    if (typeof CustomEvent !== 'function') return;
    try {
      window.dispatchEvent(new CustomEvent(name, { detail: detail }));
    } catch (_e) { /* ignore */ }
  }

  function _now() {
    return Math.floor(Date.now() / 1000);
  }

  function _synthError(code, message) {
    var e = new Error(message || code);
    e.code = code;
    return e;
  }

  function _statusToCode(status, fallbackMessage) {
    var msg = String(fallbackMessage || '').toLowerCase();
    if (msg.indexOf('insufficient') >= 0 || msg.indexOf('at least 3') >= 0
        || msg.indexOf('< 3') >= 0 || msg.indexOf('3 reference') >= 0) {
      return 'insufficient_examples';
    }
    return 'training_failed';
  }

  function _el(tag, cls, text) {
    if (typeof document === 'undefined') return null;
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function _entriesToSwatches(referenceImages) {
    if (!Array.isArray(referenceImages)) return [];
    var out = [];
    for (var i = 0; i < referenceImages.length && out.length < MAX_SWATCH_COUNT; i++) {
      var ent = referenceImages[i];
      if (!ent) continue;
      // Each entry is { name, mime, base64 } per the images-list widget.
      // We store dataURLs so the result card can <img src="..."> directly.
      if (ent.dataUrl) {
        out.push(ent.dataUrl);
        continue;
      }
      if (ent.base64 && typeof ent.base64 === 'string') {
        var mime = ent.mime || 'image/png';
        out.push('data:' + mime + ';base64,' + ent.base64);
      }
    }
    return out;
  }

  // ── Style-adapter registry ────────────────────────────────────────────

  /**
   * Singleton registry of trained style adapters available to
   * image_styles. Created here so callers don't need to wire boot
   * order between this module, the image_styles wiring, and the
   * picker UI.
   */
  function _makeRegistry() {
    var byId = Object.create(null);
    var subs = [];

    function add(record) {
      if (!record || !record.id) return null;
      if (!record.created_at) record.created_at = _now();
      if (!Array.isArray(record.swatches)) record.swatches = [];
      byId[record.id] = record;
      _notify({ type: 'added', record: record });
      _windowEmit('ora:style-adapter-registered', { record: record });
      return record;
    }

    function remove(adapterId) {
      if (!byId[adapterId]) return false;
      var rec = byId[adapterId];
      delete byId[adapterId];
      _notify({ type: 'removed', record: rec, adapterId: adapterId });
      _windowEmit('ora:style-adapter-removed', { adapterId: adapterId });
      return true;
    }

    function list() {
      var out = [];
      for (var k in byId) out.push(byId[k]);
      // Newest first — UX convention for "recently trained" lists.
      out.sort(function (a, b) { return (b.created_at || 0) - (a.created_at || 0); });
      return out;
    }

    function get(id) { return byId[id] || null; }

    function clear() {
      byId = Object.create(null);
      _notify({ type: 'cleared' });
    }

    function subscribe(handler) {
      if (typeof handler !== 'function') return function () {};
      subs.push(handler);
      return function () {
        var idx = subs.indexOf(handler);
        if (idx >= 0) subs.splice(idx, 1);
      };
    }

    function _notify(evt) {
      for (var i = 0; i < subs.length; i++) {
        try { subs[i](evt); } catch (_e) { /* swallow */ }
      }
    }

    /**
     * Adapter records reshaped as <select>-style options for the
     * image_styles ``style_reference`` picker. The picker accepts
     * canvas-object ids OR adapter ids (per the slot description),
     * so adapter ids are returned as plain strings; the option label
     * carries the human name + a "(style adapter)" suffix.
     */
    function getStyleReferenceOptions() {
      return list().map(function (rec) {
        return {
          value: rec.id,
          label: (rec.name || rec.id) + ' (style adapter)',
          kind: 'style_adapter',
          swatches: rec.swatches.slice(),
          record: rec,
        };
      });
    }

    return {
      add: add,
      remove: remove,
      list: list,
      get: get,
      clear: clear,
      subscribe: subscribe,
      getStyleReferenceOptions: getStyleReferenceOptions,
    };
  }

  var _registry = null;
  function _getRegistry() {
    if (_registry) return _registry;
    if (typeof root !== 'undefined' && root.OraStyleAdapterRegistry) {
      _registry = root.OraStyleAdapterRegistry;
      return _registry;
    }
    _registry = _makeRegistry();
    if (typeof root !== 'undefined') {
      root.OraStyleAdapterRegistry = _registry;
    }
    return _registry;
  }

  // ── Adapter id extraction from result_ref ─────────────────────────────

  /**
   * The Replicate flux-dev-lora-trainer's ``output`` is a model
   * version id (string) per its API; ``_extract_async_result`` in
   * replicate.py passes ``prediction.output`` straight through.
   * We accept several shapes for robustness:
   *
   *   "some-version-id"            → "some-version-id"
   *   { version: "..." }           → "..."
   *   { id: "..." }                → "..."
   *   { url: "https://..." }       → URL (used as-is — image_styles can
   *                                  pass URLs as style_reference too)
   *   { weights: "https://..." }   → URL (LoRA weights archive)
   *   [ "..." ]                    → "..." (first element)
   *
   * Returns null if no usable id could be extracted.
   */
  function _extractAdapterId(resultRef) {
    if (resultRef == null) return null;
    if (typeof resultRef === 'string') {
      return resultRef.trim() || null;
    }
    if (Array.isArray(resultRef)) {
      for (var i = 0; i < resultRef.length; i++) {
        var got = _extractAdapterId(resultRef[i]);
        if (got) return got;
      }
      return null;
    }
    if (typeof resultRef === 'object') {
      var keys = ['version', 'id', 'adapter_id', 'lora', 'weights', 'url'];
      for (var k = 0; k < keys.length; k++) {
        var v = resultRef[keys[k]];
        if (typeof v === 'string' && v.trim()) return v.trim();
      }
    }
    return null;
  }

  // ── Pending parameter map ─────────────────────────────────────────────
  //
  // We need the user-supplied reference images (for swatches) and name
  // (for the registry record) at completion time, but the SSE event
  // only carries server-side fields. Track a per-job map keyed by job
  // id: dispatcher hands us inputs at submit time → server returns the
  // job dict → we cache.
  //
  // The map persists for the lifetime of the page. Records that never
  // see a terminal status get pruned on destroy().

  function _newPendingMap() { return Object.create(null); }

  // ── Server call ───────────────────────────────────────────────────────

  /**
   * POST the dispatch payload to ``/api/capability/style_trains``.
   *
   * The server's contract (mirrors capability_image_edits's shape):
   *
   *   200 OK
   *   {
   *     "job": { "id": "...", "status": "queued", ... },   // the queue
   *                                                       // record
   *     "stub": false                                      // optional
   *   }
   *
   *   4xx
   *   { "error": { "code": "...", "message": "..." } }
   *
   * The payload we send is:
   *   {
   *     slot: "style_trains",
   *     inputs: {
   *       reference_images: [{name, mime, base64}, ...],
   *       name: "...",
   *       training_depth: "quick" | "standard" | "deep" (optional)
   *     },
   *     provider_override: "..." (optional)
   *   }
   *
   * Returns the parsed JSON body of the 200 response.
   */
  function _callServer(endpoint, payload, fetchImpl) {
    var fn = fetchImpl
      || (typeof root !== 'undefined' && root.fetch)
      || (typeof fetch !== 'undefined' ? fetch : null);
    if (typeof fn !== 'function') {
      return Promise.reject(_synthError('training_failed',
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
        var message = errBody.message || ('Server returned HTTP ' + status + '.');
        var code = errBody.code || _statusToCode(status, message);
        throw _synthError(code, message);
      });
    });
  }

  // ── Result card UI ────────────────────────────────────────────────────

  /**
   * Build the result card DOM for a completed adapter. The card
   * shows the adapter's display name, its id (small caption),
   * and up to MAX_SWATCH_COUNT sample swatches. Clicking a swatch
   * (or the "Use in image_styles" button) inserts the adapter id
   * into the active image_styles invocation if the user has it
   * open.
   */
  function _buildResultCard(record) {
    var card = _el('div', 'ora-style-adapter-card');
    if (!card) return null;
    card.setAttribute('data-adapter-id', record.id);

    var head = _el('div', 'ora-style-adapter-card__head');
    head.appendChild(_el('strong', 'ora-style-adapter-card__name', record.name || '(unnamed)'));
    var idLabel = _el('span', 'ora-style-adapter-card__id', record.id);
    idLabel.title = record.id;
    head.appendChild(idLabel);
    card.appendChild(head);

    if (record.swatches && record.swatches.length) {
      var row = _el('div', 'ora-style-adapter-card__swatches');
      for (var i = 0; i < record.swatches.length && i < MAX_SWATCH_COUNT; i++) {
        var img = _el('img', 'ora-style-adapter-card__swatch');
        if (img) {
          img.src = record.swatches[i];
          img.alt = 'Style sample ' + (i + 1);
          img.addEventListener('click', function (adapterId) {
            return function (ev) {
              ev.preventDefault();
              _selectAdapter(adapterId);
            };
          }(record.id));
          row.appendChild(img);
        }
      }
      card.appendChild(row);
    }

    var actions = _el('div', 'ora-style-adapter-card__actions');
    var useBtn = _el('button', 'ora-style-adapter-card__use', 'Use in image_styles');
    useBtn.type = 'button';
    useBtn.addEventListener('click', function (ev) {
      ev.preventDefault();
      _selectAdapter(record.id);
    });
    actions.appendChild(useBtn);
    card.appendChild(actions);

    return card;
  }

  /**
   * Plumb the chosen adapter id into the active image_styles
   * invocation if there is one. Always emits
   * ``ora:style-adapter-selected`` so other listeners (a future
   * style picker, vault export, etc.) can react.
   */
  function _selectAdapter(adapterId) {
    _windowEmit('ora:style-adapter-selected', { adapterId: adapterId });
    if (typeof root === 'undefined') return;
    var ui = root.OraCapabilityInvocationUI;
    if (!ui || typeof ui._getActive !== 'function') return;
    var ctl = ui._getActive();
    if (!ctl || !ctl._state) return;
    if (ctl._state.slotName !== IMAGE_STYLES_SLOT) return;
    var ctrl = ctl._state.inputControls && ctl._state.inputControls.style_reference;
    if (!ctrl || typeof ctrl.setValue !== 'function') return;
    try {
      ctrl.setValue(adapterId);
    } catch (_e) { /* swallow */ }
    if (typeof ctl.refreshEnabledState === 'function') {
      try { ctl.refreshEnabledState(); } catch (_e) { /* swallow */ }
    }
  }

  // ── Module state ──────────────────────────────────────────────────────

  function _makeController(opts) {
    opts = opts || {};
    var state = {
      hostEl:    opts.hostEl || (typeof document !== 'undefined' ? document : null),
      fetchImpl: opts.fetchImpl || null,
      endpoint:  opts.endpoint || DEFAULT_ENDPOINT,
      ui:        opts.ui || (typeof root !== 'undefined' ? root.OraCapabilityInvocationUI : null),
      _dispatchListener: null,
      _jobListener: null,
      _pending: _newPendingMap(),
      _destroyed: false,
    };

    function handleDispatch(detail) {
      if (state._destroyed) return Promise.resolve(null);
      if (!detail || detail.slot !== SLOT_NAME) return Promise.resolve(null);
      var inputs = detail.inputs || {};
      var refs = inputs.reference_images || [];
      // Client-side guardrail mirroring the dispatcher's check. Surface
      // immediately so the user doesn't wait for a round trip.
      if (!Array.isArray(refs) || refs.length < 3) {
        var err = _synthError('insufficient_examples',
          'style_trains requires at least 3 reference images.');
        _surfaceError(err);
        return Promise.reject(err);
      }
      var payload = {
        slot:   SLOT_NAME,
        inputs: inputs,
      };
      if (detail.provider_override || inputs.provider_override) {
        payload.provider_override = detail.provider_override || inputs.provider_override;
      }
      // Layer the timeline note over the generic async badge.
      _showPendingTimelineNote();

      return _callServer(state.endpoint, payload, state.fetchImpl).then(function (response) {
        var job = (response && response.job) ? response.job : response;
        if (!job || !job.id) {
          throw _synthError('training_failed',
            'Server returned no job for style_trains dispatch.');
        }
        // Cache the user-supplied params keyed by job id so the
        // ora:job_status terminal event has enough to build a record.
        state._pending[job.id] = {
          name: inputs.name || '',
          referenceImages: refs.slice(),
          training_depth: inputs.training_depth || null,
          dispatchedAt: _now(),
        };
        return job;
      }).catch(function (err) {
        _hidePendingTimelineNote();
        _surfaceError(err);
        throw err;
      });
    }

    /**
     * Listen for the SSE-bridged ora:job_status events. We consume
     * the same event the queue strip does; ours is purely additive
     * (registry record + result card) so both surfaces co-exist.
     */
    function _onJobStatus(evt) {
      if (state._destroyed) return;
      var payload = evt && evt.detail ? evt.detail : evt;
      if (!payload || !payload.job) return;
      var job = payload.job;
      if (job.capability !== SLOT_NAME) return;

      if (job.status === 'complete') {
        _onJobComplete(job);
        _hidePendingTimelineNote();
      } else if (job.status === 'failed') {
        _onJobFailed(job);
        _hidePendingTimelineNote();
      } else if (job.status === 'cancelled') {
        delete state._pending[job.id];
        _hidePendingTimelineNote();
      }
    }

    function _onJobComplete(job) {
      var adapterId = _extractAdapterId(job.result_ref);
      if (!adapterId) {
        // The dispatcher succeeded but the output shape was unexpected.
        // Surface a typed error so the user has a fix path.
        _surfaceError(_synthError('training_failed',
          'Training completed but no adapter id was returned by the provider.'));
        delete state._pending[job.id];
        return;
      }
      var pending = state._pending[job.id] || {};
      var record = {
        id: adapterId,
        name: pending.name || ('Style ' + adapterId.slice(0, 8)),
        created_at: _now(),
        swatches: _entriesToSwatches(pending.referenceImages),
        capability_metadata: {
          training_depth: pending.training_depth || null,
          job_id: job.id,
          dispatched_at: pending.dispatchedAt || null,
          completed_at: job.completed_at || null,
        },
      };
      _getRegistry().add(record);
      delete state._pending[job.id];

      var resultPayload = {
        output: adapterId,
        adapterId: adapterId,
        record: record,
        provider: job.provider || null,
        metadata: record.capability_metadata,
      };
      // Render the adapter card via the invocation UI's result area.
      // The UI has built-in style-adapter-id rendering ("Style adapter
      // registered: <id>") — we render the richer card on top of it
      // by appending into the same result element after the UI clears
      // its in-flight state.
      if (state.ui && typeof state.ui.renderResult === 'function') {
        try { state.ui.renderResult(resultPayload); } catch (_e) { /* swallow */ }
      }
      _attachResultCard(record);

      _emit(state.hostEl, 'capability-result', {
        slot: SLOT_NAME,
        output: adapterId,
        adapterId: adapterId,
        record: record,
      });
    }

    function _onJobFailed(job) {
      delete state._pending[job.id];
      var msg = (job.error && String(job.error)) || 'Style training failed.';
      _surfaceError(_synthError(_statusToCode(0, msg), msg));
    }

    function _attachResultCard(record) {
      if (!state.hostEl || typeof state.hostEl.querySelector !== 'function') return;
      var resultEl = state.hostEl.querySelector('.ora-cap-result');
      if (!resultEl) return;
      var card = _buildResultCard(record);
      if (card) resultEl.appendChild(card);
    }

    function _surfaceError(err) {
      var code = (err && err.code) || 'training_failed';
      var message = (err && err.message) || String(err);
      if (state.ui && typeof state.ui.renderError === 'function') {
        try { state.ui.renderError({ code: code, message: message }); }
        catch (_e) { /* swallow */ }
      }
      _emit(state.hostEl, 'capability-error', {
        slot: SLOT_NAME,
        code: code,
        message: message,
      });
    }

    function _showPendingTimelineNote() {
      if (!state.hostEl || typeof state.hostEl.querySelector !== 'function') return;
      var statusEl = state.hostEl.querySelector('.ora-cap-status');
      if (!statusEl) return;
      // Don't double-stack notes if dispatch is fired twice.
      if (statusEl.querySelector('.ora-style-trains__note')) return;
      var note = _el('div', 'ora-style-trains__note', PENDING_TIMELINE_NOTE);
      if (note) statusEl.appendChild(note);
    }

    function _hidePendingTimelineNote() {
      if (!state.hostEl || typeof state.hostEl.querySelector !== 'function') return;
      var note = state.hostEl.querySelector('.ora-style-trains__note');
      if (note && note.parentNode) note.parentNode.removeChild(note);
    }

    function _onCapabilityDispatch(evt) {
      if (!evt || !evt.detail) return;
      if (evt.detail.slot !== SLOT_NAME) return;
      handleDispatch(evt.detail).catch(function () { /* surfaced */ });
    }

    /**
     * For the WP-7.6.1 page-load hydration path: the chat-panel /
     * job-queue replays already-active or already-complete jobs from
     * /api/jobs/<conversation_id>. If a style_trains job already
     * completed (e.g. user reloaded after dispatch), this lets us
     * register the adapter without requiring a fresh dispatch.
     *
     * ``params`` is best-effort — when the original reference_images
     * aren't available (page reload destroyed the in-memory map) we
     * register the record with empty swatches; the user still sees
     * the adapter in the picker, just without thumbnails.
     */
    function registerCompletedJob(job, params) {
      if (!job || job.capability !== SLOT_NAME) return null;
      if (job.status !== 'complete') return null;
      var adapterId = _extractAdapterId(job.result_ref);
      if (!adapterId) return null;
      var p = params || {};
      var record = {
        id: adapterId,
        name: p.name || ('Style ' + adapterId.slice(0, 8)),
        created_at: job.completed_at || _now(),
        swatches: _entriesToSwatches(p.referenceImages || []),
        capability_metadata: {
          training_depth: p.training_depth || null,
          job_id: job.id,
          completed_at: job.completed_at || null,
        },
      };
      return _getRegistry().add(record);
    }

    function destroy() {
      if (state._destroyed) return;
      state._destroyed = true;
      if (state.hostEl && state._dispatchListener) {
        state.hostEl.removeEventListener('capability-dispatch', state._dispatchListener);
      }
      if (typeof window !== 'undefined' && state._jobListener) {
        window.removeEventListener('ora:job_status', state._jobListener);
      }
      state._dispatchListener = null;
      state._jobListener = null;
      state._pending = _newPendingMap();
    }

    function setUI(ui)             { state.ui = ui || null; }
    function setEndpoint(ep)       { state.endpoint = ep || DEFAULT_ENDPOINT; }
    function setFetchImpl(fn)      { state.fetchImpl = fn || null; }

    if (state.hostEl && typeof state.hostEl.addEventListener === 'function') {
      state._dispatchListener = _onCapabilityDispatch;
      state.hostEl.addEventListener('capability-dispatch', state._dispatchListener);
    }
    if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
      state._jobListener = _onJobStatus;
      window.addEventListener('ora:job_status', state._jobListener);
    }

    return {
      handleDispatch:       handleDispatch,
      registerCompletedJob: registerCompletedJob,
      destroy:              destroy,
      setUI:                setUI,
      setEndpoint:          setEndpoint,
      setFetchImpl:         setFetchImpl,
      _state:               state, // exposed for tests only
      _onJobStatus:         _onJobStatus,
    };
  }

  // ── Module-level "active" controller ──────────────────────────────────

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

  // Make sure the registry is materialised on module load so consumers
  // that read window.OraStyleAdapterRegistry before init() runs find it.
  _getRegistry();

  var api = {
    init:                 init,
    handleDispatch:       _delegate('handleDispatch'),
    registerCompletedJob: _delegate('registerCompletedJob'),
    setUI:                _delegate('setUI'),
    setEndpoint:          _delegate('setEndpoint'),
    setFetchImpl:         _delegate('setFetchImpl'),
    destroy: function () {
      if (_activeController) _activeController.destroy();
      _activeController = null;
    },
    // Test hooks
    _extractAdapterId:    _extractAdapterId,
    _entriesToSwatches:   _entriesToSwatches,
    _statusToCode:        _statusToCode,
    _selectAdapter:       _selectAdapter,
    _buildResultCard:     _buildResultCard,
    DEFAULT_ENDPOINT:     DEFAULT_ENDPOINT,
    PENDING_TIMELINE_NOTE: PENDING_TIMELINE_NOTE,
    MAX_SWATCH_COUNT:     MAX_SWATCH_COUNT,
    SLOT_NAME:            SLOT_NAME,
    IMAGE_STYLES_SLOT:    IMAGE_STYLES_SLOT,
    _getActive: function () { return _activeController; },
    // Registry surface — exposed both as a sibling global and through
    // this module so callers can pick whichever discovery path they
    // prefer.
    registry: _getRegistry(),
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraCapabilityStyleTrains = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
