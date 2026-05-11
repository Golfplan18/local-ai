/* v3-capability-async.js — V3 async-capability subsystem (Row 50)
 *
 * Bridges three pre-existing pieces that were never wired together in V3:
 *
 *   - capability-invocation-ui.js — emits `capability-dispatch` events
 *     on the host element when a user submits a capability popover
 *     (e.g., video_generates).
 *   - capability-video-generates.js / capability-style-trains.js — the
 *     handlers that catch `capability-dispatch`, POST to the slot's
 *     server route, and fire `ora:job_status` events on window so the
 *     queue UI can render the job. They expose .init({hostEl, ...})
 *     which V3 never called — so they sat unmounted and the popover
 *     submits fired into the void.
 *   - job-queue.js (OraJobQueue) — listens for `ora:job_status` events,
 *     manages job state, renders a canvas placeholder via the visual
 *     panel, and owns the cancel-with-billing-warning modal.
 *
 * The V3-specific work (this module):
 *
 *   1. Calls .init() on both async-capability handlers + on OraJobQueue
 *      at DOMContentLoaded so the dispatch chain is live.
 *   2. Hides the OraJobQueue strip UI (V3 puts jobs in the sidebar
 *      Operating tray, not in a chat-stream strip — see B+C hybrid
 *      design 2026-05-11). The canvas placeholder + cancel modal
 *      machinery in OraJobQueue stays active.
 *   3. Polls `/api/jobs/<conversation_id>` every 5s for the active
 *      conversation, diffs against last-seen state, fires
 *      `ora:job_status` events for status changes. Replaces the legacy
 *      chat-panel.js polling loop that V3 doesn't have (chat-panel.js
 *      is dead code in V3).
 *   4. Renders job entries into a `#v3JobsList` section inside the
 *      sidebar Operating tray. The section sits alongside the existing
 *      `#oversightOperatingList` so the two render layers (oversight
 *      Operating items + async jobs) coexist cleanly without one
 *      stomping the other's DOM.
 *   5. Maintains terminal-job grace period (30s) so the user sees a
 *      "Complete" pill before the row vanishes.
 *
 * Public namespace: window.OraV3CapabilityAsync
 *
 *   .init()                 — mount + start polling. Idempotent.
 *   .destroy()              — unmount + stop polling. (For tests.)
 *   .getKnownJobs()         — Map<id, job>. (For tests.)
 *   ._handleEvent(payload)  — feed an event dict directly. (For tests
 *                              and for any module that wants to push
 *                              status without going through SSE.)
 *
 * No SSE; the server's SSE endpoint was retired during the V3 cutover
 * per the chat-panel.js polling comment (line 390). We rely on
 * /api/jobs/<conversation_id> polling instead.
 */
(function () {
  'use strict';

  // Async capability slots that have init-based handler modules.
  var ASYNC_SLOT_MODULES = [
    { name: 'video_generates', global: 'OraCapabilityVideoGenerates' },
    { name: 'style_trains',    global: 'OraCapabilityStyleTrains' },
  ];

  var POLL_INTERVAL_MS    = 5000;
  var TERMINAL_GRACE_MS   = 30000;  // keep completed rows visible 30s

  var TERMINAL_STATUSES = { complete: 1, cancelled: 1, failed: 1 };

  var STATUS_LABELS = {
    queued:       'Queued',
    in_progress:  'Working',
    complete:     'Complete',
    cancelled:    'Cancelled',
    failed:       'Failed',
  };

  // ── Module state ───────────────────────────────────────────────────────

  var state = {
    initialised: false,
    pollTimer:   null,
    lastSeen:    new Map(),   // job_id -> status
    jobs:        new Map(),   // job_id -> { job, terminalAt? }
    listenerBound: false,
    activeListener: null,
    convChangeListener: null,
    pruneTimer:   null,
  };

  // ── Helpers ────────────────────────────────────────────────────────────

  function _getVisualPanel() {
    try {
      if (window.OraPanels && window.OraPanels.visual
          && typeof window.OraPanels.visual._getActive === 'function') {
        return window.OraPanels.visual._getActive();
      }
    } catch (_) { /* fall through */ }
    return null;
  }

  function _getActiveConversation() {
    try {
      if (window.OraSidebar
          && typeof window.OraSidebar.getActiveConversation === 'function') {
        return window.OraSidebar.getActiveConversation();
      }
    } catch (_) { /* fall through */ }
    return null;
  }

  function _capabilityLabel(cap) {
    if (!cap) return 'Job';
    return String(cap)
      .replace(/_/g, ' ')
      .replace(/^./, function (c) { return c.toUpperCase(); });
  }

  function _formatElapsed(secs) {
    if (!isFinite(secs) || secs < 0) return '';
    if (secs < 60) return Math.round(secs) + 's';
    if (secs < 3600) return Math.round(secs / 60) + 'm';
    return (secs / 3600).toFixed(1) + 'h';
  }

  // ── Init sub-modules ───────────────────────────────────────────────────

  function _initCapabilityHandlers() {
    var panel = _getVisualPanel();
    ASYNC_SLOT_MODULES.forEach(function (entry) {
      var mod = window[entry.global];
      if (!mod || typeof mod.init !== 'function') {
        console.warn('[v3-capability-async] ' + entry.global + ' missing or has no init()');
        return;
      }
      // Already initialised? Some modules expose _getActive() so we can
      // detect a prior init and skip re-mounting. Others just no-op a
      // second init via internal state — both are fine.
      try {
        if (typeof mod._getActive === 'function' && mod._getActive()) {
          return;
        }
      } catch (_) { /* not all modules expose _getActive — fine */ }
      try {
        mod.init({
          hostEl: document.body,
          visualPanel: panel,
        });
        console.info('[v3-capability-async] initialised ' + entry.global);
      } catch (e) {
        console.warn('[v3-capability-async] ' + entry.global + ' init failed:', e && e.message);
      }
    });
  }

  function _initJobQueue() {
    if (!window.OraJobQueue || typeof window.OraJobQueue.init !== 'function') {
      console.warn('[v3-capability-async] OraJobQueue missing or has no init()');
      return;
    }
    try {
      // chatHostEl: null → strip mounts on document.body and is hidden
      // by CSS in V3 (.ora-job-queue { display: none } added in
      // sidebar.css). The placeholder + cancel-modal machinery still
      // works because they don't depend on the strip's visibility.
      window.OraJobQueue.init({
        chatHostEl:     null,
        visualPanel:    _getVisualPanel(),
        conversationId: _getActiveConversation(),
      });
      console.info('[v3-capability-async] initialised OraJobQueue (strip hidden in V3)');
    } catch (e) {
      console.warn('[v3-capability-async] OraJobQueue init failed:', e && e.message);
    }
  }

  // ── Operating-tray rendering ──────────────────────────────────────────

  function _ensureTraySection() {
    var operatingList = document.getElementById('oversightOperatingList');
    if (!operatingList) return null;
    var jobsList = document.getElementById('v3JobsList');
    if (jobsList) return jobsList;
    jobsList = document.createElement('div');
    jobsList.id = 'v3JobsList';
    jobsList.className = 'v3-jobs-list';
    // Insert AFTER the operating list so async-jobs render below the
    // re-eval queue + active elicitations. Same visual style (uses
    // .oversight-card via class composition) so the user sees a
    // coherent tray.
    if (operatingList.parentNode) {
      operatingList.parentNode.insertBefore(jobsList, operatingList.nextSibling);
    }
    return jobsList;
  }

  function _renderJobsList() {
    var list = _ensureTraySection();
    if (!list) return;
    list.innerHTML = '';
    // Sort: in-flight first (oldest first), terminal last.
    var rows = Array.from(state.jobs.values()).sort(function (a, b) {
      var aTerm = TERMINAL_STATUSES[a.job.status] ? 1 : 0;
      var bTerm = TERMINAL_STATUSES[b.job.status] ? 1 : 0;
      if (aTerm !== bTerm) return aTerm - bTerm;
      return (a.job.dispatched_at || 0) - (b.job.dispatched_at || 0);
    });
    rows.forEach(function (entry) {
      list.appendChild(_buildJobCard(entry.job));
    });
  }

  function _buildJobCard(job) {
    var card = document.createElement('div');
    card.className = 'oversight-card v3-job-card v3-job-card--' + (job.status || 'queued');
    card.dataset.engagement = 'seen';
    card.dataset.jobId = job.id;

    var name = document.createElement('div');
    name.className = 'oversight-card-name';
    name.textContent = _capabilityLabel(job.capability);
    card.appendChild(name);

    var meta = document.createElement('div');
    meta.className = 'oversight-card-meta';

    var statusPill = document.createElement('span');
    statusPill.className = 'badge v3-job-status v3-job-status--' + (job.status || 'queued');
    statusPill.textContent = STATUS_LABELS[job.status] || job.status || 'queued';
    meta.appendChild(statusPill);

    if (job.metadata && job.metadata.provider) {
      var providerTag = document.createElement('span');
      providerTag.className = 'badge';
      providerTag.textContent = job.metadata.provider;
      meta.appendChild(providerTag);
    }

    if (job.dispatched_at) {
      var elapsedTag = document.createElement('span');
      var elapsed = (Date.now() / 1000) - job.dispatched_at;
      elapsedTag.textContent = _formatElapsed(elapsed);
      meta.appendChild(elapsedTag);
    }

    // Cancel button for non-terminal jobs. Delegates to OraJobQueue's
    // existing cancel modal (with billing warning) so behavior is
    // consistent with the legacy strip UI.
    if (!TERMINAL_STATUSES[job.status]) {
      var cancelBtn = document.createElement('button');
      cancelBtn.type = 'button';
      cancelBtn.className = 'badge v3-job-cancel';
      cancelBtn.textContent = '×';
      cancelBtn.title = 'Cancel this job';
      cancelBtn.addEventListener('click', function (ev) {
        ev.stopPropagation();
        if (window.OraJobQueue && typeof window.OraJobQueue._testRequestCancel === 'function') {
          window.OraJobQueue._testRequestCancel(job.id);
        } else {
          // Fallback if OraJobQueue isn't loaded — direct POST.
          fetch('/api/jobs/' + encodeURIComponent(job.id) + '/cancel',
                { method: 'POST' }).catch(function () {});
        }
      });
      meta.appendChild(cancelBtn);
    }

    card.appendChild(meta);

    return card;
  }

  // ── Status-event handling ─────────────────────────────────────────────

  function _handleEvent(payload) {
    if (!payload || !payload.job) return;
    var job = payload.job;
    if (!job.id) return;

    var existing = state.jobs.get(job.id);
    var nowTerminal = !!TERMINAL_STATUSES[job.status];
    var entry = existing ? existing : {};
    entry.job = job;
    if (nowTerminal && !entry.terminalAt) {
      entry.terminalAt = Date.now();
    }
    state.jobs.set(job.id, entry);

    _renderJobsList();
  }

  function _pruneTerminal() {
    var now = Date.now();
    var anyRemoved = false;
    state.jobs.forEach(function (entry, id) {
      if (entry.terminalAt && (now - entry.terminalAt) >= TERMINAL_GRACE_MS) {
        state.jobs.delete(id);
        anyRemoved = true;
      }
    });
    if (anyRemoved) _renderJobsList();
  }

  // ── Polling loop ──────────────────────────────────────────────────────

  function _poll() {
    if (!state.initialised) return;
    var convId = _getActiveConversation() || 'default';
    fetch('/api/jobs/' + encodeURIComponent(convId))
      .then(function (r) { return r && r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !Array.isArray(data.jobs)) return;
        data.jobs.forEach(function (job) {
          // /api/jobs returns the queue's serialized job dicts; the
          // status field is at top level (`job.status`). The polling
          // contract from the legacy chat-panel.js used `job_id` for
          // the id; we support both shapes since the server has
          // evolved.
          var id = job.id || job.job_id;
          if (!id) return;
          var lastStatus = state.lastSeen.get(id);
          if (lastStatus === job.status) return;
          state.lastSeen.set(id, job.status);
          // Normalise to the same payload shape OraJobQueue expects.
          var payload = {
            type: lastStatus ? 'job_status' : 'job_dispatched',
            conversation_id: convId,
            job: Object.assign({}, job, { id: id }),
          };
          try {
            window.dispatchEvent(new CustomEvent('ora:job_status', { detail: payload }));
          } catch (_) {
            if (window.OraJobQueue && typeof window.OraJobQueue.handleEvent === 'function') {
              try { window.OraJobQueue.handleEvent(payload); } catch (_) { /* swallow */ }
            }
          }
          // Also feed our local tray-renderer directly. The window
          // event listener route would also catch it, but going direct
          // avoids any race where the event fires before our listener
          // is attached on first poll.
          _handleEvent(payload);
        });
      })
      .catch(function () { /* network blip — next tick will retry */ });
  }

  function _startPolling() {
    if (state.pollTimer) return;
    state.pollTimer = window.setInterval(_poll, POLL_INTERVAL_MS);
    // Fire one immediately so a fresh load picks up in-flight jobs
    // without waiting POLL_INTERVAL_MS.
    _poll();
  }

  function _stopPolling() {
    if (state.pollTimer) {
      window.clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  // ── Conversation switch ───────────────────────────────────────────────

  function _onConversationSelected() {
    // Reset lastSeen so the new conversation's jobs (if any) re-fire
    // dispatched events. Don't clear state.jobs — the tray shows
    // jobs across conversations during the session (useful when the
    // user switches and wants to see the prior conversation's running
    // jobs still in flight). Polling now hits the new conversation's
    // endpoint.
    state.lastSeen = new Map();
    _poll();
  }

  // ── Public API ────────────────────────────────────────────────────────

  function init() {
    if (state.initialised) return;
    state.initialised = true;

    _initCapabilityHandlers();
    _initJobQueue();

    // Tray section: pre-render so the empty <div> is in the DOM and the
    // sidebar's mutually-exclusive accordion logic doesn't get
    // confused by appearing/disappearing siblings.
    _ensureTraySection();

    // Subscribe to window-level job_status events. Our own _poll()
    // fires these too; this listener also catches synthetic events
    // from capability-video-generates.js immediately after a POST
    // (the "queued" status arrives microseconds after dispatch via
    // _emitJobStatusToWindow, before the next poll tick).
    state.activeListener = function (e) {
      if (e && e.detail) _handleEvent(e.detail);
    };
    window.addEventListener('ora:job_status', state.activeListener);

    state.convChangeListener = function () { _onConversationSelected(); };
    document.addEventListener('ora:conversation-selected', state.convChangeListener);

    _startPolling();

    // Prune terminal entries every 5s.
    state.pruneTimer = window.setInterval(_pruneTerminal, 5000);

    console.info('[v3-capability-async] subsystem online');
  }

  function destroy() {
    _stopPolling();
    if (state.pruneTimer) {
      window.clearInterval(state.pruneTimer);
      state.pruneTimer = null;
    }
    if (state.activeListener) {
      window.removeEventListener('ora:job_status', state.activeListener);
      state.activeListener = null;
    }
    if (state.convChangeListener) {
      document.removeEventListener('ora:conversation-selected', state.convChangeListener);
      state.convChangeListener = null;
    }
    var list = document.getElementById('v3JobsList');
    if (list && list.parentNode) list.parentNode.removeChild(list);
    state.jobs = new Map();
    state.lastSeen = new Map();
    state.initialised = false;
  }

  function getKnownJobs() {
    var out = new Map();
    state.jobs.forEach(function (entry, id) { out.set(id, entry.job); });
    return out;
  }

  window.OraV3CapabilityAsync = {
    init:           init,
    destroy:        destroy,
    getKnownJobs:   getKnownJobs,
    _handleEvent:   _handleEvent,  // test hook
    _poll:          _poll,         // test hook
    _ensureTraySection: _ensureTraySection,  // test hook
  };
})();
