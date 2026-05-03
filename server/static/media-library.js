/**
 * media-library.js — Audio/Video Phase 3
 *
 * Per-conversation media library panel that lives inside the visual
 * pane when `body.pane-mode-video` is active. Refreshes from
 * /api/media-library/<conv_id>:
 *
 *   - on init, conversation switch, mode entry, or after a successful
 *     drop / capture-complete.
 *
 * Renders a grid: thumbnail (video) or generic glyph (audio/image),
 * display name, duration. Operations (Phase 3 scope):
 *
 *   - Drop a file on the visual canvas while in video mode → POSTs
 *     multipart to /api/media-library/<conv>/add. Library refreshes.
 *   - (Phase 5) drag entry onto timeline.
 *   - (Phase 5+) rename, remove from menu.
 *
 * Works alongside capture-controls.js: when a capture completes, the
 * server-side _media_library_capture_hook adds the file automatically;
 * capture-controls dispatches an `ora:capture-state` CustomEvent on
 * document with `state === 'complete'` after its terminal poll, which
 * we listen for and refresh on. (The earlier /api/capture/stream SSE
 * subscription was retired 2026-04-30; the SSE endpoint itself was
 * retired 2026-05-01.)
 *
 * Public namespace: window.OraMediaLibrary
 *   .init()                   → call once at page load
 *   .setConversationId(id)    → external override
 *   .refresh()                → re-fetch and re-render
 *   .acceptDrop(file)         → external entry point (used by canvas
 *                               drop interceptor)
 *   .getState()               → {entries, conversationId} for tests
 */
(function (root) {
  'use strict';

  if (typeof document === 'undefined') return;

  // ── module state ─────────────────────────────────────────────────────────

  var _panelEl = null;        // .media-library panel root
  var _gridEl = null;         // entries grid
  var _emptyEl = null;        // empty state message
  var _hostEl = null;         // visual-panel root we mount into
  var _conversationId = null;
  var _entries = [];
  var _captureSse = null;

  var _AUDIO_GLYPH = ''
    + '<svg viewBox="0 0 24 24" width="32" height="32" fill="none" '
    + 'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    + 'stroke-linejoin="round"><path d="M9 18V5l12-2v13"/>'
    + '<circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>';
  var _IMAGE_GLYPH = ''
    + '<svg viewBox="0 0 24 24" width="32" height="32" fill="none" '
    + 'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    + 'stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/>'
    + '<circle cx="9" cy="9" r="2"/><path d="M21 15l-5-5L5 21"/></svg>';
  var _VIDEO_GLYPH = ''
    + '<svg viewBox="0 0 24 24" width="32" height="32" fill="none" '
    + 'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    + 'stroke-linejoin="round"><polygon points="23 7 16 12 23 17 23 7"/>'
    + '<rect x="1" y="5" width="15" height="14" rx="2"/></svg>';

  // ── helpers ──────────────────────────────────────────────────────────────

  function _findVisualHost() {
    return document.querySelector('.visual-panel')
        || document.querySelector('.pane.right-pane');
  }

  function _formatDuration(ms) {
    if (!ms && ms !== 0) return '';
    var totalSec = Math.floor(ms / 1000);
    var h = Math.floor(totalSec / 3600);
    var m = Math.floor((totalSec % 3600) / 60);
    var s = totalSec % 60;
    if (h > 0) {
      return h + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
    }
    return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
  }

  function _formatBytes(b) {
    if (b == null) return '';
    if (b < 1024) return b + ' B';
    if (b < 1024 * 1024) return (b / 1024).toFixed(0) + ' KB';
    if (b < 1024 * 1024 * 1024) return (b / (1024 * 1024)).toFixed(1) + ' MB';
    return (b / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
  }

  // ── DOM build ────────────────────────────────────────────────────────────

  function _build() {
    if (_panelEl) return _panelEl;
    var el = document.createElement('div');
    el.className = 'media-library';
    el.setAttribute('aria-label', 'Media library');
    el.innerHTML = ''
      + '<div class="media-library__header">'
      +   '<span class="media-library__title">Media library</span>'
      +   '<span class="media-library__count" data-role="count">0</span>'
      + '</div>'
      + '<div class="media-library__import" data-role="import">'
      +   '<input type="url" class="media-library__import-input" '
      +          'data-role="import-url" '
      +          'placeholder="Paste a YouTube / Vimeo / podcast URL…" />'
      +   '<button type="button" class="media-library__import-btn" '
      +           'data-role="import-btn">Import</button>'
      +   '<div class="media-library__import-status" data-role="import-status"></div>'
      + '</div>'
      + '<div class="media-library__grid" data-role="grid"></div>'
      + '<div class="media-library__empty" data-role="empty">'
      +   'Drop audio, video, or image files anywhere in the visual pane to add them here, '
      +   'or paste a URL above to import from YouTube, Vimeo, podcasts, and ~1500 other sites. '
      +   'Captured screen recordings appear automatically.'
      + '</div>';
    _panelEl = el;
    _gridEl = el.querySelector('[data-role="grid"]');
    _emptyEl = el.querySelector('[data-role="empty"]');

    var inputEl = el.querySelector('[data-role="import-url"]');
    var btnEl = el.querySelector('[data-role="import-btn"]');
    var statusEl = el.querySelector('[data-role="import-status"]');
    if (btnEl && inputEl) {
      btnEl.addEventListener('click', function () {
        _onImportSubmit(inputEl, btnEl, statusEl);
      });
      inputEl.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          _onImportSubmit(inputEl, btnEl, statusEl);
        }
      });
    }

    return el;
  }

  // ── URL import (yt-dlp) ──────────────────────────────────────────────────

  var _activeImportPoll = null;

  function _setImportStatus(statusEl, text, kind) {
    if (!statusEl) return;
    statusEl.textContent = text || '';
    statusEl.classList.remove(
      'media-library__import-status--progress',
      'media-library__import-status--error',
      'media-library__import-status--success'
    );
    if (text && kind) {
      statusEl.classList.add('media-library__import-status--' + kind);
    }
  }

  function _onImportSubmit(inputEl, btnEl, statusEl) {
    var url = (inputEl.value || '').trim();
    if (!url) return;
    if (!_conversationId) {
      _setImportStatus(statusEl, 'Open a conversation first.', 'error');
      return;
    }
    if (!/^https?:\/\//i.test(url)) {
      _setImportStatus(statusEl, 'URL must start with http:// or https://', 'error');
      return;
    }
    if (_activeImportPoll) {
      _setImportStatus(statusEl, 'Another import is already running.', 'error');
      return;
    }
    btnEl.disabled = true;
    inputEl.disabled = true;
    _setImportStatus(statusEl, 'Starting…', 'progress');

    var endpoint = '/api/media-library/' + encodeURIComponent(_conversationId)
                 + '/import-url';
    fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: url }),
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, data: j }; }); })
      .then(function (res) {
        if (!res.ok) {
          throw new Error((res.data && res.data.error) || 'import failed');
        }
        var importId = res.data.import_id;
        _pollImport(importId, inputEl, btnEl, statusEl);
      })
      .catch(function (err) {
        btnEl.disabled = false;
        inputEl.disabled = false;
        _setImportStatus(statusEl, 'Import failed: ' + err.message, 'error');
      });
  }

  function _pollImport(importId, inputEl, btnEl, statusEl) {
    var endpoint = '/api/media-library/' + encodeURIComponent(_conversationId)
                 + '/import/' + encodeURIComponent(importId) + '/state';
    var stop = false;
    function _onTick() {
      fetch(endpoint)
        .then(function (r) { return r.json(); })
        .then(function (state) {
          if (stop) return;
          if (!state || state.error) {
            _finishImport(false, state && state.error || 'lost connection',
                          inputEl, btnEl, statusEl);
            return;
          }
          var s = state.state;
          if (s === 'complete') {
            _finishImport(true,
                          'Added: ' + (state.title || 'imported clip'),
                          inputEl, btnEl, statusEl);
            refresh();
            return;
          }
          if (s === 'failed') {
            _finishImport(false,
                          'Import failed: ' + (state.last_error || 'unknown error'),
                          inputEl, btnEl, statusEl);
            return;
          }
          var label = state.title ? ('"' + state.title + '"') : 'video';
          if (s === 'fetching_metadata') {
            _setImportStatus(statusEl, 'Reading ' + label + '…', 'progress');
          } else if (s === 'downloading') {
            var pct = state.progress_pct || 0;
            _setImportStatus(
              statusEl,
              'Downloading ' + label + ' — ' + pct.toFixed(0) + '%',
              'progress'
            );
          } else if (s === 'registering') {
            _setImportStatus(statusEl, 'Adding ' + label + ' to library…', 'progress');
          } else {
            _setImportStatus(statusEl, 'Working… (' + s + ')', 'progress');
          }
          _activeImportPoll = setTimeout(_onTick, 1500);
        })
        .catch(function (err) {
          if (stop) return;
          _finishImport(false, 'Lost connection: ' + err.message,
                        inputEl, btnEl, statusEl);
        });
    }
    _activeImportPoll = setTimeout(_onTick, 100);
    // Track the stopper alongside the poll so _finishImport can clear it.
    _activeImportPoll._stopper = function () { stop = true; };
  }

  function _finishImport(ok, message, inputEl, btnEl, statusEl) {
    if (_activeImportPoll) {
      try { if (_activeImportPoll._stopper) _activeImportPoll._stopper(); } catch (e) { /* */ }
      try { clearTimeout(_activeImportPoll); } catch (e) { /* */ }
      _activeImportPoll = null;
    }
    btnEl.disabled = false;
    inputEl.disabled = false;
    _setImportStatus(statusEl, message, ok ? 'success' : 'error');
    if (ok) {
      inputEl.value = '';
      // Auto-fade the success message after a few seconds.
      setTimeout(function () { _setImportStatus(statusEl, '', null); }, 4000);
    }
  }

  function _renderEntries() {
    if (!_gridEl) return;
    _gridEl.innerHTML = '';
    var countEl = _panelEl && _panelEl.querySelector('[data-role="count"]');
    if (countEl) countEl.textContent = String(_entries.length);
    if (_emptyEl) _emptyEl.style.display = _entries.length === 0 ? '' : 'none';
    if (_entries.length === 0) return;

    _entries.forEach(function (entry) {
      var card = document.createElement('div');
      card.className = 'media-library__entry';
      card.dataset.entryId = entry.id;
      card.dataset.kind = entry.kind || 'other';
      // Phase 5: card is draggable so the user can drop it onto a
      // timeline track lane. The timeline editor reads
      // application/x-ora-media-entry from the dataTransfer.
      card.draggable = true;
      card.addEventListener('dragstart', function (e) {
        if (!e.dataTransfer) return;
        e.dataTransfer.effectAllowed = 'copy';
        e.dataTransfer.setData('application/x-ora-media-entry', entry.id);
        // Plain-text fallback for any future drop target that doesn't
        // recognize our custom MIME.
        e.dataTransfer.setData('text/plain', entry.display_name || entry.id);
      });

      var thumb = document.createElement('div');
      thumb.className = 'media-library__entry-thumb';
      if (entry.kind === 'video' && entry.thumbnail_path) {
        thumb.innerHTML = '<img alt="" loading="lazy" '
          + 'src="/api/media-library/' + encodeURIComponent(_conversationId)
          + '/' + encodeURIComponent(entry.id) + '/thumbnail" />';
      } else if (entry.kind === 'audio') {
        // Lazy-load the waveform PNG; ffmpeg renders it on first hit
        // and the result is cached. If the endpoint 404s (no audio
        // track, render failed, ffmpeg unavailable) the onerror
        // handler swaps the glyph in.
        var waveImg = document.createElement('img');
        waveImg.alt = '';
        waveImg.loading = 'lazy';
        waveImg.className = 'media-library__entry-waveform';
        waveImg.src = '/api/media-library/'
          + encodeURIComponent(_conversationId)
          + '/' + encodeURIComponent(entry.id) + '/waveform';
        waveImg.addEventListener('error', function () {
          thumb.innerHTML = _AUDIO_GLYPH;
          thumb.classList.add('media-library__entry-thumb--glyph');
        });
        thumb.appendChild(waveImg);
      } else if (entry.kind === 'image') {
        thumb.innerHTML = _IMAGE_GLYPH;
        thumb.classList.add('media-library__entry-thumb--glyph');
      } else {
        thumb.innerHTML = _VIDEO_GLYPH;
        thumb.classList.add('media-library__entry-thumb--glyph');
      }
      card.appendChild(thumb);

      var meta = document.createElement('div');
      meta.className = 'media-library__entry-meta';
      var name = document.createElement('div');
      name.className = 'media-library__entry-name';
      name.textContent = entry.display_name || entry.source_path || entry.id;
      name.title = entry.source_path || '';
      meta.appendChild(name);

      var sub = document.createElement('div');
      sub.className = 'media-library__entry-sub';
      var subBits = [];
      if (entry.duration_ms) subBits.push(_formatDuration(entry.duration_ms));
      if (entry.size_bytes) subBits.push(_formatBytes(entry.size_bytes));
      sub.textContent = subBits.join(' · ');
      meta.appendChild(sub);
      card.appendChild(meta);

      var del = document.createElement('button');
      del.type = 'button';
      del.className = 'media-library__entry-remove';
      del.title = 'Remove from library (does not delete the file)';
      del.setAttribute('aria-label', 'Remove ' + (entry.display_name || 'entry'));
      del.textContent = '×';
      del.addEventListener('click', function (e) {
        e.stopPropagation();
        _removeEntry(entry.id);
      });
      card.appendChild(del);

      _gridEl.appendChild(card);
    });
  }

  // ── network ──────────────────────────────────────────────────────────────

  function refresh() {
    if (!_conversationId) {
      _entries = [];
      _renderEntries();
      return Promise.resolve();
    }
    return fetch('/api/media-library/' + encodeURIComponent(_conversationId))
      .then(function (r) { return r.json(); })
      .then(function (j) {
        _entries = j.entries || [];
        _renderEntries();
      })
      .catch(function () { /* silent — empty state will show */ });
  }

  function _removeEntry(entryId) {
    if (!_conversationId) return;
    fetch('/api/media-library/' + encodeURIComponent(_conversationId)
          + '/' + encodeURIComponent(entryId), { method: 'DELETE' })
      .then(function () { return refresh(); });
  }

  function acceptDrop(file) {
    if (!_conversationId) {
      console.warn('[OraMediaLibrary] no active conversation; ignoring drop');
      return Promise.reject(new Error('no conversation'));
    }
    var fd = new FormData();
    fd.append('file', file, file.name);
    return fetch('/api/media-library/' + encodeURIComponent(_conversationId) + '/add',
      { method: 'POST', body: fd })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (j) { throw new Error(j.error || ('HTTP ' + r.status)); });
        return r.json();
      })
      .then(function () { return refresh(); });
  }

  // ── show / hide on pane-mode-toggle ──────────────────────────────────────

  function _show() {
    var host = _findVisualHost();
    if (!host) return;
    _hostEl = host;
    if (!_panelEl) _build();
    if (!_panelEl.parentNode) host.appendChild(_panelEl);
    _panelEl.classList.add('media-library--visible');
    refresh();
    _ensureCanvasDropInterceptor(host);
  }

  function _hide() {
    if (_panelEl) _panelEl.classList.remove('media-library--visible');
  }

  // ── canvas drop interceptor (Phase 3 dispatcher) ─────────────────────────

  var _canvasDropInterceptorAttached = false;

  function _ensureCanvasDropInterceptor(host) {
    if (_canvasDropInterceptorAttached) return;
    _canvasDropInterceptorAttached = true;

    // We listen on capture (true) so we get first crack at the event,
    // before visual-panel.js's image-attach drop handler runs. We only
    // intercept when pane-mode-video is active.
    host.addEventListener('dragover', function (e) {
      if (!document.body.classList.contains('pane-mode-video')) return;
      e.preventDefault();
      e.stopPropagation();
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
    }, true);

    host.addEventListener('drop', function (e) {
      if (!document.body.classList.contains('pane-mode-video')) return;
      if (!e.dataTransfer || !e.dataTransfer.files || !e.dataTransfer.files.length) return;
      e.preventDefault();
      e.stopPropagation();
      var failed = [];
      Array.from(e.dataTransfer.files).forEach(function (f) {
        acceptDrop(f).catch(function (err) { failed.push({name: f.name, err: err.message}); });
      });
      if (failed.length) console.warn('[OraMediaLibrary] some drops failed', failed);
    }, true);
  }

  // ── capture lifecycle subscription (V3 Backlog 2A Chunk 5 follow-up) ─────
  //
  // SSE retired. capture-controls.js polls /api/capture/<id>/state and
  // dispatches `ora:capture-state` on the document when state goes
  // terminal (complete / failed). We listen for that and refresh the
  // library on `complete` — same effect as the prior SSE listener, no
  // EventSource subscription needed.

  function _connectCaptureSSE() {
    document.addEventListener('ora:capture-state', function (ev) {
      var d = ev && ev.detail && ev.detail.state;
      if (d && d.type === 'complete') {
        // The server-side hook just added the file to the library; refresh
        // a beat later so the disk-write completes before our list call.
        setTimeout(refresh, 200);
      }
    });
  }

  // ── external plumbing ────────────────────────────────────────────────────

  function setConversationId(id) {
    _conversationId = id || null;
    if (document.body.classList.contains('pane-mode-video')) {
      refresh();
    }
  }

  function init(opts) {
    if (opts && opts.conversationId) _conversationId = opts.conversationId;

    document.addEventListener('ora:pane-mode-toggle', function (e) {
      var cur = e.detail && e.detail.current;
      if (cur === 'video') _show(); else _hide();
    });
    document.addEventListener('ora:conversation-selected', function (e) {
      var d = e.detail || {};
      var cid = d.conversation_id || d.id || null;
      if (cid) setConversationId(cid);
    });

    _connectCaptureSSE();

    // Pre-build so it's ready when pane-mode flips to video.
    _build();
  }

  root.OraMediaLibrary = {
    init: init,
    setConversationId: setConversationId,
    refresh: refresh,
    acceptDrop: acceptDrop,
    getState: function () {
      return { entries: _entries.slice(), conversationId: _conversationId };
    },
  };
})(typeof window !== 'undefined' ? window : this);
