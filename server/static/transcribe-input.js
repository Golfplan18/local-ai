/**
 * transcribe-input.js — Audio/Video Phase 2
 *
 * Routes audio/video files dropped on the input pane through the
 * transcription pipeline:
 *
 *   1. POST the file to /api/transcribe (multipart). Server stages,
 *      spawns whisper-cli, returns a transcription_id.
 *   2. Poll /api/transcribe/<id>/state at 1.5 s while the job is active.
 *      Lifecycle: queued → extracting → transcribing → progress(N%) →
 *      complete. Polling stops when the state reaches a terminal value.
 *      (The earlier /api/transcribe/stream SSE feed was retired
 *      2026-05-01.)
 *   3. Render a chip in the chat-panel attachment row showing live
 *      status. On `complete`, the chip becomes a link to the vault
 *      note the server wrote, so the user can open it directly.
 *
 * Public namespace: window.OraTranscribeInput
 *   .init()                          → call once at page load
 *   .acceptFile(file, hostEl)        → start transcription; renders a
 *                                       chip into hostEl
 *   .isMediaFile(file)               → boolean: matches audio/video MIME
 *   .getJobs()                       → snapshot for tests
 */
(function (root) {
  'use strict';

  if (typeof document === 'undefined') return;  // jsdom guard

  // ── module state ─────────────────────────────────────────────────────────

  var _eventSource = null;
  var _jobs = Object.create(null);  // transcription_id → job state

  // ── helpers ──────────────────────────────────────────────────────────────

  function isMediaFile(file) {
    if (!file || !file.type) return false;
    return /^audio\//.test(file.type) || /^video\//.test(file.type);
  }

  function _formatBytes(bytes) {
    if (!bytes && bytes !== 0) return '';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
  }

  function _ensureChip(transcriptionId, file, hostEl) {
    var chip = document.querySelector('[data-transcribe-id="' + transcriptionId + '"]');
    if (chip) return chip;
    chip = document.createElement('div');
    chip.className = 'transcribe-chip';
    chip.dataset.transcribeId = transcriptionId;
    chip.dataset.state = 'queued';
    chip.innerHTML = ''
      + '<span class="transcribe-chip__icon" aria-hidden="true">'
      +   '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" '
      +   'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
      +   '<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>'
      +   '<path d="M19 10v2a7 7 0 0 1-14 0v-2"/>'
      +   '<line x1="12" y1="19" x2="12" y2="23"/>'
      +   '<line x1="8" y1="23" x2="16" y2="23"/>'
      +   '</svg>'
      + '</span>'
      + '<div class="transcribe-chip__body">'
      +   '<div class="transcribe-chip__name">' + (file ? file.name : transcriptionId) + '</div>'
      +   '<div class="transcribe-chip__status">Queued (' + _formatBytes(file ? file.size : 0) + ')</div>'
      +   '<div class="transcribe-chip__bar"><div class="transcribe-chip__fill"></div></div>'
      + '</div>'
      + '<button type="button" class="transcribe-chip__close" aria-label="Dismiss">×</button>';
    chip.querySelector('.transcribe-chip__close').addEventListener('click', function () {
      try { chip.remove(); } catch (e) { /* ignore */ }
    });
    if (hostEl) hostEl.appendChild(chip);
    return chip;
  }

  function _setChipStatus(chip, label, kind) {
    if (!chip) return;
    var statusEl = chip.querySelector('.transcribe-chip__status');
    if (statusEl) statusEl.textContent = label;
    if (kind) chip.dataset.state = kind;
  }

  function _setChipProgress(chip, pct) {
    if (!chip) return;
    var fill = chip.querySelector('.transcribe-chip__fill');
    if (fill) {
      var bounded = Math.max(0, Math.min(100, pct));
      fill.style.width = bounded.toFixed(1) + '%';
    }
  }

  function _setChipComplete(chip, vaultPath) {
    if (!chip) return;
    chip.dataset.state = 'complete';
    var nameEl = chip.querySelector('.transcribe-chip__name');
    var statusEl = chip.querySelector('.transcribe-chip__status');
    var bodyEl = chip.querySelector('.transcribe-chip__body');
    var bar = chip.querySelector('.transcribe-chip__bar');
    if (bar) bar.remove();
    if (statusEl && vaultPath) {
      statusEl.innerHTML = '';
      var link = document.createElement('span');
      link.className = 'transcribe-chip__vault-path';
      link.textContent = 'Saved → ' + vaultPath.replace(/^.*\/vault\//, 'vault/');
      link.title = vaultPath;
      statusEl.appendChild(link);
    } else if (statusEl) {
      statusEl.textContent = 'Saved';
    }
  }

  function _setChipFailed(chip, error) {
    if (!chip) return;
    chip.dataset.state = 'failed';
    var statusEl = chip.querySelector('.transcribe-chip__status');
    if (statusEl) statusEl.textContent = 'Failed: ' + (error || 'unknown error');
  }

  // ── lifecycle ────────────────────────────────────────────────────────────

  function acceptFile(file, hostEl) {
    if (!isMediaFile(file)) return Promise.reject(new Error('not an audio/video file'));

    var fd = new FormData();
    fd.append('file', file, file.name);

    return fetch('/api/transcribe', { method: 'POST', body: fd })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (j) { throw new Error(j.error || ('HTTP ' + r.status)); });
        return r.json();
      })
      .then(function (j) {
        _jobs[j.transcription_id] = {
          file: file,
          hostEl: hostEl,
          state: 'queued',
          chip: _ensureChip(j.transcription_id, file, hostEl),
        };
        // V3 Backlog 2A Chunk 5 — kick the poller now that there's an
        // active job to watch.
        _ensurePolling();
        return j.transcription_id;
      })
      .catch(function (err) {
        // Build a chip ourselves to surface the failure even when the
        // server didn't accept the upload.
        var chip = _ensureChip('local-' + Date.now(), file, hostEl);
        _setChipFailed(chip, err.message);
        throw err;
      });
  }

  // ── State polling (V3 Backlog 2A Chunk 5 follow-up, 2026-04-30) ─────────
  //
  // SSE retired. We poll /api/transcribe/<id>/state at 1.5 s while a
  // job is active. The poller starts when acceptFile() registers a new
  // transcription_id and stops when the state goes complete / failed.

  var _pollInterval = null;
  var _pollLastSeen = {};   // transcription_id → last seen status

  function _connectSSE() { _ensurePolling(); }

  function _ensurePolling() {
    if (_pollInterval) return;
    if (typeof window === 'undefined' || typeof fetch !== 'function') return;
    _pollInterval = window.setInterval(_pollAll, 1500);
    _pollAll();
  }

  function _stopPollingIfIdle() {
    var anyActive = false;
    for (var tid in _jobs) {
      if (Object.prototype.hasOwnProperty.call(_jobs, tid)) {
        var s = _jobs[tid] && _jobs[tid].state;
        if (s !== 'complete' && s !== 'failed') { anyActive = true; break; }
      }
    }
    if (!anyActive && _pollInterval) {
      try { window.clearInterval(_pollInterval); } catch (_e) {}
      _pollInterval = null;
    }
  }

  function _pollAll() {
    var ids = Object.keys(_jobs).filter(function (tid) {
      var s = _jobs[tid] && _jobs[tid].state;
      return s !== 'complete' && s !== 'failed';
    });
    if (!ids.length) { _stopPollingIfIdle(); return; }
    ids.forEach(function (tid) {
      fetch('/api/transcribe/' + encodeURIComponent(tid) + '/state')
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (state) {
          if (!state) return;
          // Skip duplicate dispatches when nothing changed.
          var key = state.type + ':' + (state.progress_pct || 0);
          if (_pollLastSeen[tid] === key) return;
          _pollLastSeen[tid] = key;
          state.transcription_id = tid;
          _handleEvent(state);
        })
        .catch(function () { /* network blip — keep polling */ });
    });
  }

  function _handleEvent(ev) {
    var tid = ev.transcription_id;
    if (!tid) return;
    var job = _jobs[tid];
    var chip = job && job.chip ? job.chip : document.querySelector('[data-transcribe-id="' + tid + '"]');
    if (!chip) return;

    switch (ev.type) {
      case 'queued':
        _setChipStatus(chip, 'Queued', 'queued');
        break;
      case 'extracting':
        _setChipStatus(chip, 'Extracting audio…', 'extracting');
        _setChipProgress(chip, 5);
        break;
      case 'transcribing':
        _setChipStatus(chip, 'Transcribing…', 'transcribing');
        _setChipProgress(chip, 10);
        break;
      case 'progress':
        if (typeof ev.progress_pct === 'number') {
          _setChipProgress(chip, ev.progress_pct);
          _setChipStatus(chip, 'Transcribing… ' + Math.round(ev.progress_pct) + '%', 'transcribing');
        }
        break;
      case 'complete':
        _setChipComplete(chip, ev.vault_path || '');
        if (job) job.state = 'complete';
        break;
      case 'failed':
        _setChipFailed(chip, ev.error || '');
        if (job) job.state = 'failed';
        break;
      default:
        break;
    }
  }

  // ── init ─────────────────────────────────────────────────────────────────

  function init() {
    _connectSSE();
  }

  root.OraTranscribeInput = {
    init: init,
    acceptFile: acceptFile,
    isMediaFile: isMediaFile,
    getJobs: function () { return Object.assign({}, _jobs); },
  };
})(typeof window !== 'undefined' ? window : this);
