/**
 * job-queue.js — WP-7.6.1 + WP-7.6.3
 *
 * Client-side companion to ~/ora/orchestrator/job_queue.py.
 *
 * Two responsibilities:
 *   1. **Queue chrome** — a compact "Jobs in flight" strip above the
 *      chat panel, listing every non-terminal async job for the current
 *      conversation. Each entry shows the capability, a status pill,
 *      and (since WP-7.6.3) a Cancel button on in-progress entries.
 *   2. **Persistent placeholder** on the visual canvas — a Konva node
 *      drawn at the result-landing position the dispatch caller chose,
 *      showing the job's status. Updates live as the server emits
 *      ``job_status`` SSE frames.
 *
 * ── Placement decision ──────────────────────────────────────────────────
 * Per §11.6 of the Visual Intelligence plan, the queue area can live
 * "in pane chrome OR in the chat bridge". We mount it in the **chat
 * bridge** (above the chat input row) for two reasons:
 *
 *   (a) §12 Q12 already locked the design that async results "are
 *       outputs like any other" — they land in the same chat stream as
 *       sync results. The queue strip belongs near that stream.
 *   (b) Async jobs are conversation-scoped, not pane-scoped. If a user
 *       has the visual pane closed at completion time, they still want
 *       to see the result land. The chat panel is the always-visible
 *       surface.
 *
 * Placeholders on the canvas remain in the visual pane — they're
 * spatial markers tied to the result-landing position the user chose
 * when dispatching. The queue strip + the placeholder cross-reference
 * each other via job id.
 *
 * ── Bridge contract ────────────────────────────────────────────────────
 * The server emits ``job_status`` SSE frames carrying the queue-event
 * dicts from ``job_queue.py`` verbatim. The chat panel's existing SSE
 * stream forwards them as DOM ``CustomEvent`` of type
 * ``ora:job_status`` on ``window``; we listen for that here. Tests can
 * dispatch synthetic events directly without an SSE plumbing.
 *
 * Exposed namespace: window.OraJobQueue
 *
 *   OraJobQueue.init(opts)
 *     opts: { chatHostEl, visualPanel, conversationId, fetchJobs }
 *     - chatHostEl: container the queue strip mounts above
 *     - visualPanel: VisualPanel instance for placeholder rendering (optional)
 *     - conversationId: string, scopes which jobs we display
 *     - fetchJobs: optional async fn returning [job, ...] for hydration
 *
 *   OraJobQueue.handleEvent(event)
 *     Idempotently apply a queue event dict (from server). Public so
 *     tests can drive transitions without an SSE simulator.
 *
 *   OraJobQueue.getKnownJobs()
 *     Return the local job map keyed by id (test introspection).
 *
 *   OraJobQueue.destroy()
 *     Tear down DOM + Konva nodes. Used by tests.
 *
 * ── WP-7.6.3 — async cancellation with billing warning ────────────────
 * In-progress entries get a Cancel button. First click opens a modal:
 *   "Cancellation may not stop the provider from billing for work
 *    already done. Continue?"
 * Confirm posts to ``POST /api/jobs/<job_id>/cancel`` (the server hands
 * off to ``JobQueue.request_cancel``, which sets ``cancel_requested`` on
 * the in-flight record so the provider polling thread exits at next poll
 * and — for Replicate — issues the provider-side cancel call). The job
 * row gets a "Cancelling…" pill until the next ``ora:job_status`` SSE
 * frame transitions it to ``cancelled``.
 *
 * Tests can override the network call via ``init({ cancelTransport })``;
 * the default uses ``window.fetch``.
 */
(function () {
  'use strict';

  // ── Status presentation ────────────────────────────────────────────────
  var STATUS_LABELS = {
    queued:       'Queued',
    in_progress:  'In progress',
    complete:     'Complete',
    cancelled:    'Cancelled',
    failed:       'Failed',
  };

  // CSS classes per status — kept in lockstep with styles/job-queue.css
  // (added in this WP). Server emits the canonical status strings; we
  // never invent new ones client-side.
  var STATUS_CLASS = {
    queued:       'ora-job--queued',
    in_progress:  'ora-job--in-progress',
    complete:     'ora-job--complete',
    cancelled:    'ora-job--cancelled',
    failed:       'ora-job--failed',
  };

  var TERMINAL = { complete: 1, cancelled: 1, failed: 1 };

  // ── Module state ───────────────────────────────────────────────────────
  // Single-instance UI: one queue strip + one placeholder layer per
  // browser session. The init() guard rebuilds cleanly if init is
  // called twice (e.g. a test reset).
  var state = {
    initialised: false,
    chatHostEl: null,
    visualPanel: null,
    conversationId: null,
    stripEl: null,
    listEl: null,
    countEl: null,
    // job_id -> { job: <serialized>, stripEntryEl, placeholderGroup }
    jobs: Object.create(null),
    // bound handler so we can detach in destroy()
    _eventListener: null,
    // WP-7.6.3 — cancel modal state
    modalEl: null,
    modalConfirmEl: null,
    modalOpenForJobId: null,
    cancelTransport: null,
    _modalKeyHandler: null,
  };

  // ── DOM helpers ────────────────────────────────────────────────────────
  function _el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function _capabilityLabel(cap) {
    // image_generates → "Image generation"; video_generates → "Video generation"
    if (!cap) return 'Job';
    var pretty = String(cap)
      .replace(/_/g, ' ')
      .replace(/^./, function (c) { return c.toUpperCase(); });
    return pretty;
  }

  function _formatElapsed(secs) {
    if (!isFinite(secs) || secs < 0) return '';
    if (secs < 60) return Math.round(secs) + 's';
    if (secs < 3600) return Math.round(secs / 60) + 'm';
    return (secs / 3600).toFixed(1) + 'h';
  }

  // ── Queue strip rendering ─────────────────────────────────────────────
  function _ensureStrip() {
    if (state.stripEl) return state.stripEl;
    var strip = _el('div', 'ora-job-queue');
    strip.setAttribute('role', 'region');
    strip.setAttribute('aria-label', 'Async jobs in flight');

    var header = _el('div', 'ora-job-queue__header');
    var title = _el('span', 'ora-job-queue__title', 'Jobs');
    var count = _el('span', 'ora-job-queue__count', '0');
    header.appendChild(title);
    header.appendChild(count);

    var list = _el('ul', 'ora-job-queue__list');
    list.setAttribute('role', 'list');

    strip.appendChild(header);
    strip.appendChild(list);

    state.stripEl = strip;
    state.listEl = list;
    state.countEl = count;

    // Mount above chat host. The chat host is the panel's body; we
    // insert as the first child of its parent so we sit above the
    // input row regardless of chat-panel internal layout.
    if (state.chatHostEl) {
      var parent = state.chatHostEl.parentNode || state.chatHostEl;
      parent.insertBefore(strip, state.chatHostEl);
    } else {
      // Fallback: append to body (test-friendly).
      document.body.appendChild(strip);
    }

    _refreshVisibility();
    return strip;
  }

  function _refreshVisibility() {
    if (!state.stripEl) return;
    var active = 0;
    for (var id in state.jobs) {
      if (!TERMINAL[state.jobs[id].job.status]) active++;
    }
    state.countEl.textContent = String(active);
    if (active === 0) {
      state.stripEl.classList.add('ora-job-queue--empty');
    } else {
      state.stripEl.classList.remove('ora-job-queue--empty');
    }
  }

  function _renderJobRow(job) {
    var li = _el('li', 'ora-job ' + (STATUS_CLASS[job.status] || ''));
    li.setAttribute('data-job-id', job.id);

    var label = _el('span', 'ora-job__label', _capabilityLabel(job.capability));
    var pill = _el('span', 'ora-job__status', STATUS_LABELS[job.status] || job.status);
    li.appendChild(label);
    li.appendChild(pill);

    if (job.dispatched_at) {
      var elapsed = (Date.now() / 1000) - job.dispatched_at;
      var t = _el('span', 'ora-job__elapsed', _formatElapsed(elapsed));
      li.appendChild(t);
    }

    // WP-7.6.3 — cancel button. Rendered for queued + in_progress; the
    // server's request_cancel handles both (queued = immediate cancel,
    // no billing warning needed in theory, but we show the same modal
    // for consistency — async dispatch to a remote provider may still
    // have triggered a meter even before our poller saw "in_progress").
    if (!TERMINAL[job.status]) {
      var btn = _el('button', 'ora-job__cancel', 'Cancel');
      btn.setAttribute('type', 'button');
      btn.setAttribute('aria-label', 'Cancel ' + _capabilityLabel(job.capability));
      btn.setAttribute('data-job-cancel', job.id);
      btn.addEventListener('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        _onCancelClick(job.id);
      });
      li.appendChild(btn);
    }

    return li;
  }

  function _updateJobRow(entry) {
    var job = entry.job;
    var li = entry.stripEntryEl;
    if (!li) return;
    li.className = 'ora-job ' + (STATUS_CLASS[job.status] || '');
    var pill = li.querySelector('.ora-job__status');
    if (pill) {
      // WP-7.6.3 — show "Cancelling…" once the user confirmed cancel
      // until the next status_changed SSE frame transitions the job.
      if (job.cancel_requested && job.status === 'in_progress') {
        pill.textContent = 'Cancelling…';
      } else {
        pill.textContent = STATUS_LABELS[job.status] || job.status;
      }
    }
    var elapsed = li.querySelector('.ora-job__elapsed');
    if (elapsed && job.dispatched_at) {
      elapsed.textContent = _formatElapsed((Date.now() / 1000) - job.dispatched_at);
    }
    // Drop the cancel button once the job reaches a terminal state or
    // once cancel_requested has flipped (one click only — no double-fire).
    var existingBtn = li.querySelector('.ora-job__cancel');
    if (existingBtn && (TERMINAL[job.status] || job.cancel_requested)) {
      existingBtn.parentNode.removeChild(existingBtn);
    }
    if (TERMINAL[job.status]) {
      // Terminal jobs are kept briefly (so the user sees the
      // transition), then removed from the strip. Result delivery
      // (WP-7.6.2) lands the actual artifact in the chat output
      // stream — we don't need to keep the row alive forever.
      var REMOVE_DELAY_MS = 4000;
      setTimeout(function () {
        if (li.parentNode) li.parentNode.removeChild(li);
        _refreshVisibility();
      }, REMOVE_DELAY_MS);
    }
  }

  // ── Canvas placeholder rendering ──────────────────────────────────────
  // We draw a translucent rectangle + label at the placeholder_anchor
  // the dispatch call recorded. The placeholder lives on the panel's
  // annotationLayer (existing in visual-panel.js) so it sits above the
  // background but below user input — semantically: an Ora-added overlay.
  //
  // If the visual pane wasn't given to init() we no-op gracefully —
  // the strip still works; placeholders just don't appear. This matches
  // §11.6: pane chrome is one valid host for the queue, the chat bridge
  // is the other.
  function _placeholderColor(status) {
    // Status-keyed accent. The full theme palette comes from the cool
    // grey Dracula theme already in use; these are the canonical
    // semantic accents the project uses elsewhere.
    if (status === 'failed')      return '#ff5555';
    if (status === 'cancelled')   return '#6272a4';
    if (status === 'complete')    return '#50fa7b';
    if (status === 'in_progress') return '#8be9fd';
    return '#f1fa8c'; // queued
  }

  function _renderPlaceholder(job) {
    if (!state.visualPanel) return null;
    var anchor = job.placeholder_anchor;
    if (!anchor || typeof anchor !== 'object') return null;
    if (typeof window === 'undefined' || !window.Konva) return null;

    var stage = state.visualPanel._stage;
    var anno = state.visualPanel._annotationLayer;
    if (!stage || !anno) return null;

    var x = +anchor.x || 0;
    var y = +anchor.y || 0;
    var w = +anchor.width  || 256;
    var h = +anchor.height || 256;

    var group = new window.Konva.Group({
      x: x, y: y,
      name: 'job-placeholder',
      jobId: job.id,
    });

    var rect = new window.Konva.Rect({
      x: 0, y: 0, width: w, height: h,
      stroke: _placeholderColor(job.status),
      strokeWidth: 2,
      dash: [8, 6],
      fill: 'rgba(40, 42, 54, 0.35)',
      cornerRadius: 6,
      name: 'job-placeholder__rect',
    });

    var label = new window.Konva.Text({
      x: 8, y: 8, width: w - 16,
      text: _capabilityLabel(job.capability) + '\n' +
            (STATUS_LABELS[job.status] || job.status),
      fontSize: 13,
      fontFamily: 'system-ui, sans-serif',
      fill: '#f8f8f2',
      align: 'left',
      name: 'job-placeholder__label',
    });

    group.add(rect);
    group.add(label);
    anno.add(group);
    anno.batchDraw();
    return group;
  }

  function _updatePlaceholder(entry) {
    var group = entry.placeholderGroup;
    if (!group) return;
    var job = entry.job;
    var rect = group.findOne('.job-placeholder__rect');
    var label = group.findOne('.job-placeholder__label');
    if (rect) rect.stroke(_placeholderColor(job.status));
    if (label) {
      label.text(_capabilityLabel(job.capability) + '\n' +
                 (STATUS_LABELS[job.status] || job.status));
    }
    var layer = group.getLayer && group.getLayer();
    if (layer && layer.batchDraw) layer.batchDraw();

    if (TERMINAL[job.status]) {
      // Terminal: hold briefly (so the user sees the state change),
      // then remove. WP-7.6.2 will land the result content separately —
      // the placeholder is only the "in-flight" affordance.
      var REMOVE_DELAY_MS = 1500;
      setTimeout(function () {
        try {
          group.destroy();
          if (layer && layer.batchDraw) layer.batchDraw();
        } catch (_e) { /* node already gone */ }
      }, REMOVE_DELAY_MS);
    }
  }

  // ── Event ingestion ────────────────────────────────────────────────────
  function _handleEvent(eventOrPayload) {
    if (!state.initialised) return;
    var payload = eventOrPayload;
    if (eventOrPayload && eventOrPayload.detail) payload = eventOrPayload.detail;
    if (!payload || !payload.job) return;

    // Filter on conversation_id — multi-conversation surfaces share the
    // SSE stream but each strip only shows its own.
    if (state.conversationId &&
        payload.conversation_id &&
        payload.conversation_id !== state.conversationId) {
      return;
    }

    var job = payload.job;
    var existing = state.jobs[job.id];

    if (!existing) {
      // First sighting → render strip row + placeholder (if pane present).
      var li = _renderJobRow(job);
      if (state.listEl) state.listEl.appendChild(li);
      var ph = _renderPlaceholder(job);
      state.jobs[job.id] = {
        job: job,
        stripEntryEl: li,
        placeholderGroup: ph,
      };
    } else {
      existing.job = job;
      _updateJobRow(existing);
      _updatePlaceholder(existing);
    }
    _refreshVisibility();
  }

  // ── Hydration on init ──────────────────────────────────────────────────
  function _hydrate(fetchJobs) {
    if (typeof fetchJobs !== 'function') return Promise.resolve();
    var p;
    try { p = fetchJobs(); } catch (e) { return Promise.resolve(); }
    if (!p || typeof p.then !== 'function') {
      // Synchronous fetch shape (used in tests).
      _hydrateApply(p);
      return Promise.resolve();
    }
    return p.then(_hydrateApply, function () { /* swallow */ });
  }

  function _hydrateApply(jobs) {
    if (!Array.isArray(jobs)) return;
    for (var i = 0; i < jobs.length; i++) {
      _handleEvent({ type: 'job_dispatched', job: jobs[i],
                     conversation_id: state.conversationId });
    }
  }

  // ── WP-7.6.3 — Cancel modal + transport ───────────────────────────────
  // The "two-click" flow:
  //   1. user clicks the per-row Cancel button → _onCancelClick opens
  //      the modal with the billing warning.
  //   2. user clicks the modal's "Cancel job" button → _confirmCancel
  //      calls the transport (POST /api/jobs/<id>/cancel by default).
  //   3. server flips ``cancel_requested`` → SSE frame arrives →
  //      _updateJobRow swaps the pill to "Cancelling…".
  //   4. Replicate poll thread sees the flag, calls provider cancel,
  //      transitions job to ``cancelled`` → SSE frame arrives → row
  //      removes from strip after the standard terminal-delay.
  //
  // The modal is its own DOM tree mounted on document.body (not inside
  // the strip) so it can sit above any panel layout. We rely on the
  // CSS in styles/job-queue.css for visual treatment; semantically the
  // modal is role="dialog" with aria-modal="true".

  var CANCEL_WARNING_TEXT =
    'Cancellation may not stop the provider from billing for ' +
    'work already done. Continue?';

  function _defaultCancelTransport(jobId) {
    if (typeof fetch !== 'function') {
      return Promise.reject(new Error('fetch unavailable'));
    }
    return fetch('/api/jobs/' + encodeURIComponent(jobId) + '/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: state.conversationId || null,
      }),
    }).then(function (r) {
      if (!r.ok) throw new Error('cancel failed: ' + r.status);
      return r.json().catch(function () { return {}; });
    });
  }

  function _ensureModal() {
    if (state.modalEl) return state.modalEl;
    var overlay = _el('div', 'ora-job-cancel-modal');
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-labelledby', 'ora-job-cancel-title');
    overlay.style.display = 'none';

    var box = _el('div', 'ora-job-cancel-modal__box');
    var title = _el('h2', 'ora-job-cancel-modal__title', 'Cancel job?');
    title.id = 'ora-job-cancel-title';
    var body = _el('p', 'ora-job-cancel-modal__body', CANCEL_WARNING_TEXT);

    var actions = _el('div', 'ora-job-cancel-modal__actions');
    var keepBtn = _el('button', 'ora-job-cancel-modal__keep', 'Keep running');
    keepBtn.setAttribute('type', 'button');
    var confirmBtn = _el('button', 'ora-job-cancel-modal__confirm', 'Cancel job');
    confirmBtn.setAttribute('type', 'button');
    actions.appendChild(keepBtn);
    actions.appendChild(confirmBtn);

    box.appendChild(title);
    box.appendChild(body);
    box.appendChild(actions);
    overlay.appendChild(box);

    keepBtn.addEventListener('click', _closeModal);
    confirmBtn.addEventListener('click', function () { _confirmCancel(); });
    overlay.addEventListener('click', function (e) {
      // Click outside box dismisses (matches keepBtn).
      if (e.target === overlay) _closeModal();
    });
    // Esc dismisses while modal is open.
    state._modalKeyHandler = function (e) {
      if (state.modalOpenForJobId && e.key === 'Escape') _closeModal();
    };
    document.addEventListener('keydown', state._modalKeyHandler);

    document.body.appendChild(overlay);
    state.modalEl = overlay;
    state.modalConfirmEl = confirmBtn;
    return overlay;
  }

  function _openModal(jobId) {
    _ensureModal();
    state.modalOpenForJobId = jobId;
    state.modalEl.style.display = '';
    // Defer focus so the click that opened us doesn't immediately
    // re-trigger via Enter on the focused button.
    if (state.modalConfirmEl && state.modalConfirmEl.focus) {
      try { state.modalConfirmEl.focus(); } catch (_e) { /* */ }
    }
  }

  function _closeModal() {
    if (!state.modalEl) return;
    state.modalEl.style.display = 'none';
    state.modalOpenForJobId = null;
  }

  function _onCancelClick(jobId) {
    var entry = state.jobs[jobId];
    if (!entry) return;
    if (TERMINAL[entry.job.status]) return;
    if (entry.job.cancel_requested) return; // already mid-cancel
    _openModal(jobId);
  }

  function _confirmCancel() {
    var jobId = state.modalOpenForJobId;
    _closeModal();
    if (!jobId) return;
    var entry = state.jobs[jobId];
    if (!entry) return;
    // Optimistic UI: drop the button + show "Cancelling…" right away.
    // The server's SSE frame will overwrite this once the request lands.
    entry.job.cancel_requested = true;
    _updateJobRow(entry);
    var transport = state.cancelTransport || _defaultCancelTransport;
    var p;
    try { p = transport(jobId); }
    catch (e) { p = Promise.reject(e); }
    if (!p || typeof p.then !== 'function') return;
    p.then(function () { /* SSE will drive the UI */ },
           function (err) {
             // Revert optimistic state on failure so the user can retry.
             entry.job.cancel_requested = false;
             _updateJobRow(entry);
             try { console.warn('[ora-job-queue] cancel failed:', err); }
             catch (_e) { /* */ }
           });
  }

  // ── Public API ─────────────────────────────────────────────────────────
  function init(opts) {
    opts = opts || {};
    if (state.initialised) destroy();

    state.chatHostEl    = opts.chatHostEl || null;
    state.visualPanel   = opts.visualPanel || null;
    state.conversationId = opts.conversationId || null;
    state.cancelTransport = (typeof opts.cancelTransport === 'function')
      ? opts.cancelTransport : null;
    state.jobs = Object.create(null);
    state.initialised = true;

    _ensureStrip();

    // Subscribe to bridged SSE events.
    state._eventListener = function (e) { _handleEvent(e); };
    window.addEventListener('ora:job_status', state._eventListener);

    // Pull existing in-flight jobs from server (server-restart recovery).
    return _hydrate(opts.fetchJobs);
  }

  function destroy() {
    if (state._eventListener) {
      window.removeEventListener('ora:job_status', state._eventListener);
      state._eventListener = null;
    }
    if (state._modalKeyHandler) {
      document.removeEventListener('keydown', state._modalKeyHandler);
      state._modalKeyHandler = null;
    }
    if (state.stripEl && state.stripEl.parentNode) {
      state.stripEl.parentNode.removeChild(state.stripEl);
    }
    if (state.modalEl && state.modalEl.parentNode) {
      state.modalEl.parentNode.removeChild(state.modalEl);
    }
    // Destroy any live placeholders.
    for (var id in state.jobs) {
      var entry = state.jobs[id];
      if (entry.placeholderGroup) {
        try { entry.placeholderGroup.destroy(); } catch (_e) { /* */ }
      }
    }
    state.stripEl = null;
    state.listEl = null;
    state.countEl = null;
    state.modalEl = null;
    state.modalConfirmEl = null;
    state.modalOpenForJobId = null;
    state.cancelTransport = null;
    state.jobs = Object.create(null);
    state.initialised = false;
  }

  function getKnownJobs() {
    var out = Object.create(null);
    for (var id in state.jobs) out[id] = state.jobs[id].job;
    return out;
  }

  // Convenience: feed a fully-formed event dict directly. Used by tests
  // and by the chat-panel SSE bridge.
  function handleEvent(payload) { _handleEvent(payload); }

  // WP-7.6.3 — test hooks. The §13.6 acceptance test drives the
  // two-click flow without an SSE simulator: it calls _testRequestCancel
  // (= the per-row button click) → asserts modal is visible → calls
  // _testConfirmCancel (= confirm button click) → asserts the supplied
  // transport was called with the right job id.
  function _testRequestCancel(jobId) { _onCancelClick(jobId); }
  function _testConfirmCancel() { _confirmCancel(); }
  function _testGetModalState() {
    return {
      visible: !!(state.modalEl && state.modalEl.style.display !== 'none'),
      forJobId: state.modalOpenForJobId,
      warningText: state.modalEl
        ? (state.modalEl.querySelector('.ora-job-cancel-modal__body') || {}).textContent
        : null,
    };
  }

  window.OraJobQueue = {
    init: init,
    destroy: destroy,
    handleEvent: handleEvent,
    getKnownJobs: getKnownJobs,
    // Constants exposed for adversarial tests + future WPs.
    STATUS_LABELS: STATUS_LABELS,
    TERMINAL_STATUSES: Object.keys(TERMINAL),
    CANCEL_WARNING_TEXT: CANCEL_WARNING_TEXT,
    // Test hooks — WP-7.6.3 acceptance criterion drives these.
    _testRequestCancel: _testRequestCancel,
    _testConfirmCancel: _testConfirmCancel,
    _testGetModalState: _testGetModalState,
  };
})();
