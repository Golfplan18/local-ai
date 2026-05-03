/* document-input.js — V3 Input Handling Phase 8
 *
 * Frontend counterpart to orchestrator/document_input.py. Mirrors the
 * shape of transcribe-input.js (the audio/video module) so the
 * file-drop dispatcher can route to either with the same
 * acceptFile(file, hostEl) call. Routes a dropped or attached document
 * file through:
 *
 *   1. POST the file to /api/document/process (multipart). Server
 *      stages, returns a processing_id.
 *   2. Listen on /api/document/stream (SSE) for that id's lifecycle:
 *      queued → converting → writing → complete (with vault_path)
 *      or failed (with error).
 *   3. Render a chip in the host element showing live status. On
 *      complete, the chip carries the vault path so the user can open
 *      the staged note from Obsidian.
 *
 * Public namespace: window.OraDocumentInput
 *   .init()                          → call once at page load
 *   .acceptFile(file, hostEl)        → start processing; renders a chip
 *   .isDocumentFile(file)            → boolean: matches supported MIME
 *   .getJobs()                       → snapshot for tests
 */
(function (root) {
  'use strict';
  if (typeof document === 'undefined') return;

  // Supported types map onto orchestrator/tools/format_convert.py's
  // accepted formats.
  var DOC_MIME_PREFIXES = [
    'text/',                                   // plain text + markdown
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/vnd.ms-powerpoint',
    'application/rtf',
    'application/x-rtf',
    'application/json',
  ];
  var DOC_EXT_FALLBACK = [
    '.pdf', '.docx', '.doc', '.pptx', '.ppt',
    '.html', '.htm', '.rtf', '.txt', '.md', '.markdown',
  ];

  function isDocumentFile(file) {
    if (!file) return false;
    var mime = (file.type || '').toLowerCase();
    if (mime) {
      for (var i = 0; i < DOC_MIME_PREFIXES.length; i += 1) {
        if (mime === DOC_MIME_PREFIXES[i] || mime.indexOf(DOC_MIME_PREFIXES[i]) === 0) {
          return true;
        }
      }
    }
    // Some browsers leave .md / .rtf / .docx as ``''`` MIME — fall back
    // to the extension whitelist.
    var name = (file.name || '').toLowerCase();
    for (var j = 0; j < DOC_EXT_FALLBACK.length; j += 1) {
      if (name.endsWith(DOC_EXT_FALLBACK[j])) return true;
    }
    return false;
  }

  // ── module state ─────────────────────────────────────────────────────────

  var _eventSource = null;
  var _jobs = Object.create(null);

  function _formatBytes(bytes) {
    if (!bytes && bytes !== 0) return '';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
  }

  // ── Chip rendering ───────────────────────────────────────────────────────
  // Reuses the .transcribe-chip class from transcribe.css — the visual
  // treatment is identical and we don't need a parallel stylesheet.

  function _ensureChip(processingId, file, hostEl) {
    var chip = document.querySelector('[data-document-id="' + processingId + '"]');
    if (chip) return chip;
    chip = document.createElement('div');
    chip.className = 'transcribe-chip';
    chip.dataset.documentId = processingId;
    chip.dataset.state = 'queued';
    chip.innerHTML = ''
      + '<span class="transcribe-chip__icon" aria-hidden="true">'
      +   '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" '
      +   'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
      +   '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
      +   '<polyline points="14 2 14 8 20 8"/>'
      +   '<line x1="9" y1="13" x2="15" y2="13"/>'
      +   '<line x1="9" y1="17" x2="15" y2="17"/>'
      +   '</svg>'
      + '</span>'
      + '<div class="transcribe-chip__body">'
      +   '<div class="transcribe-chip__name">' + (file ? file.name : processingId) + '</div>'
      +   '<div class="transcribe-chip__status">Queued (' + _formatBytes(file ? file.size : 0) + ')</div>'
      +   '<div class="transcribe-chip__bar"><div class="transcribe-chip__fill"></div></div>'
      + '</div>'
      + '<button type="button" class="transcribe-chip__close" aria-label="Dismiss">×</button>';
    chip.querySelector('.transcribe-chip__close').addEventListener('click', function () {
      chip.remove();
    });
    if (hostEl) hostEl.appendChild(chip);
    return chip;
  }

  function _setStatus(chip, text) {
    var statusEl = chip.querySelector('.transcribe-chip__status');
    if (statusEl) statusEl.textContent = text;
  }

  function _setComplete(chip, vaultPath) {
    chip.dataset.state = 'complete';
    var statusEl = chip.querySelector('.transcribe-chip__status');
    if (statusEl) {
      statusEl.innerHTML = '';
      var label = document.createElement('span');
      label.textContent = 'Saved to vault';
      statusEl.appendChild(label);
      if (vaultPath) {
        statusEl.appendChild(document.createTextNode(' · '));
        var link = document.createElement('span');
        link.className = 'transcribe-chip__path';
        link.textContent = vaultPath.split('/').pop();
        link.title = vaultPath;
        statusEl.appendChild(link);
      }
    }
    var fill = chip.querySelector('.transcribe-chip__fill');
    if (fill) fill.style.width = '100%';
  }

  function _setFailed(chip, errorMessage) {
    chip.dataset.state = 'failed';
    _setStatus(chip, 'Failed: ' + (errorMessage || 'unknown error'));
  }

  // ── lifecycle ────────────────────────────────────────────────────────────

  function acceptFile(file, hostEl, options) {
    if (!isDocumentFile(file)) {
      return Promise.reject(new Error('not a supported document file'));
    }
    options = options || {};
    var fd = new FormData();
    fd.append('file', file, file.name);
    if (options.conversation_id) fd.append('conversation_id', options.conversation_id);
    if (options.tag) fd.append('tag', options.tag);

    return fetch('/api/document/process', { method: 'POST', body: fd })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (j) {
          throw new Error(j.error || ('HTTP ' + r.status));
        });
        return r.json();
      })
      .then(function (j) {
        var chip = _ensureChip(j.processing_id, file, hostEl);
        _jobs[j.processing_id] = {
          file: file,
          hostEl: hostEl,
          state: 'queued',
          chip: chip,
        };
        // Race fix: format_convert on a markdown passthrough completes
        // in milliseconds, so all SSE state events can fire before our
        // EventSource is connected. One-shot poll catches the terminal
        // state if we missed it. SSE continues to handle slower jobs
        // (PDFs, .docx, etc.) where the events arrive in time.
        setTimeout(function () {
          fetch('/api/document/' + j.processing_id + '/state')
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (state) {
              if (!state) return;
              if (chip.dataset.state !== state.state) {
                chip.dataset.state = state.state;
                if (state.state === 'complete') {
                  _setComplete(chip, state.vault_path || '');
                  if (_jobs[j.processing_id]) _jobs[j.processing_id].state = 'complete';
                } else if (state.state === 'failed') {
                  _setFailed(chip, state.error || '');
                  if (_jobs[j.processing_id]) _jobs[j.processing_id].state = 'failed';
                } else {
                  // Intermediate state we missed — set the status text
                  // so the chip isn't stuck on "Queued".
                  var label = state.state.charAt(0).toUpperCase() + state.state.slice(1) + '…';
                  _setStatus(chip, label);
                }
              }
            })
            .catch(function () { /* silent — SSE may still arrive */ });
        }, 350);
        return j.processing_id;
      })
      .catch(function (err) {
        var chip = _ensureChip('local-' + Date.now(), file, hostEl);
        _setFailed(chip, err.message);
        throw err;
      });
  }

  // ── SSE consumer ─────────────────────────────────────────────────────────

  function _connectSSE() {
    if (typeof EventSource === 'undefined') return;
    if (_eventSource) return;
    try {
      _eventSource = new EventSource('/api/document/stream');
    } catch (e) {
      console.warn('[document-input] SSE connect failed:', e);
      return;
    }
    _eventSource.addEventListener('state', _handleEvent);
    _eventSource.addEventListener('message', _handleEvent);
    _eventSource.addEventListener('error', function (e) {
      // EventSource auto-reconnects; just log and move on.
    });
  }

  function _handleEvent(rawEvent) {
    if (!rawEvent || !rawEvent.data) return;
    var ev;
    try { ev = JSON.parse(rawEvent.data); } catch (e) { return; }
    var pid = ev.processing_id;
    if (!pid) return;
    var job = _jobs[pid];
    var chip = (job && job.chip) || document.querySelector('[data-document-id="' + pid + '"]');
    if (!chip) return;
    chip.dataset.state = ev.state || 'unknown';
    switch (ev.state) {
      case 'queued':
        _setStatus(chip, 'Queued');
        break;
      case 'converting':
        _setStatus(chip, 'Converting…');
        break;
      case 'writing':
        _setStatus(chip, 'Saving to vault…');
        break;
      case 'complete':
        _setComplete(chip, ev.vault_path || '');
        if (job) job.state = 'complete';
        break;
      case 'failed':
        _setFailed(chip, ev.error || '');
        if (job) job.state = 'failed';
        break;
      default:
        break;
    }
  }

  function init() {
    _connectSSE();
  }

  root.OraDocumentInput = {
    init: init,
    acceptFile: acceptFile,
    isDocumentFile: isDocumentFile,
    getJobs: function () { return Object.assign({}, _jobs); },
  };
})(typeof window !== 'undefined' ? window : this);
