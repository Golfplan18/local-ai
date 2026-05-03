/**
 * preview-monitor.js — Audio/Video Phase 7 follow-up
 *
 * Per-conversation preview monitor that lives above the timeline editor in
 * the visual pane when `body.pane-mode-video` is active.
 *
 * Two display modes:
 *   - frame mode (default): static <img> showing the timeline at the
 *     current playhead. Refreshed on playhead change + timeline mutation,
 *     debounced ~200 ms. Single-clip case is sub-second.
 *   - playback mode: <video> playing the cached 360 p proxy. Built on
 *     demand when the user hits Play; invalidated on timeline mutation.
 *
 * Event contract (all dispatched on `document`):
 *   in  : `ora:pane-mode-toggle`        — show/hide
 *         `ora:conversation-selected`   — switch conversation
 *         `ora:timeline-playhead-changed` — refresh frame / sync video
 *         `ora:timeline-mutated`        — invalidate proxy + refresh
 *   out : `ora:preview-playhead-update` — fired during proxy playback so
 *                                          the timeline editor's playhead
 *                                          can follow.
 *
 * Public namespace: window.OraPreviewMonitor
 *   .init()
 *   .setConversationId(id)
 *   .reload()
 *   .getState()
 */
(function (root) {
  'use strict';

  if (typeof document === 'undefined') return;

  // ── module state ─────────────────────────────────────────────────────────

  var _hostEl = null;
  var _rootEl = null;
  var _stageEl = null;
  var _imgEl = null;
  var _videoEl = null;
  var _statusEl = null;
  var _playBtn = null;
  var _stopBtn = null;
  var _timecodeEl = null;
  var _hintEl = null;
  var _overlayEl = null;
  var _overlayTextEl = null;
  var _overlayFillEl = null;
  // Phase 6 follow-up — drag-to-position overlay handle.
  var _dragHandleEl = null;
  var _selectedOverlay = null;   // { trackId, clipId, position: {...} }
  var _dragState = null;         // pointerdown bookkeeping during a drag

  var _conversationId = null;
  var _displayMode = 'frame';        // 'frame' | 'playback'
  var _proxyState = null;            // last fetched /api/preview/<id>/state
  var _activeProxyRenderId = null;
  var _playheadRequestedMs = 0;      // last known playhead from the timeline

  var _frameDebounce = null;
  var _frameInflightController = null;
  var _eventSource = null;                       // legacy (Backlog 2A Chunk 5 retired SSE)
  var _renderEventListenerInstalled = false;     // V3 Backlog 2A Chunk 5

  // ── helpers ──────────────────────────────────────────────────────────────

  function _formatTimecode(ms) {
    if (!isFinite(ms) || ms < 0) ms = 0;
    var totalSec = Math.floor(ms / 1000);
    var h = Math.floor(totalSec / 3600);
    var m = Math.floor((totalSec % 3600) / 60);
    var s = totalSec % 60;
    return String(h).padStart(2, '0') + ':' +
           String(m).padStart(2, '0') + ':' +
           String(s).padStart(2, '0');
  }

  // ── DOM build ────────────────────────────────────────────────────────────

  function _build() {
    if (_rootEl) return _rootEl;
    var el = document.createElement('div');
    el.className = 'preview-monitor';
    el.innerHTML = ''
      + '<div class="preview-monitor__header">'
      +   '<span class="preview-monitor__title">Preview</span>'
      +   '<span class="preview-monitor__status" data-role="status" title=""></span>'
      + '</div>'
      + '<div class="preview-monitor__stage" data-role="stage">'
      +   '<img class="preview-monitor__image" data-role="image" alt="Preview frame"/>'
      +   '<video class="preview-monitor__video" data-role="video" preload="metadata" playsinline></video>'
      +   '<div class="preview-monitor__drag-handle" data-role="drag-handle" hidden>'
      +     '<span class="preview-monitor__drag-handle-label" data-role="drag-handle-label"></span>'
      +   '</div>'
      +   '<div class="preview-monitor__overlay" data-role="overlay">'
      +     '<div class="preview-monitor__overlay-text" data-role="overlay-text">Building preview…</div>'
      +     '<div class="preview-monitor__overlay-bar"><div class="preview-monitor__overlay-fill" data-role="overlay-fill"></div></div>'
      +   '</div>'
      + '</div>'
      + '<div class="preview-monitor__transport">'
      +   '<button type="button" class="preview-monitor__btn" data-role="play" aria-label="Play" title="Play / Pause">'
      +     _playGlyph()
      +   '</button>'
      +   '<button type="button" class="preview-monitor__btn" data-role="stop" aria-label="Stop" title="Stop / Return to frame view">'
      +     _stopGlyph()
      +   '</button>'
      +   '<span class="preview-monitor__timecode" data-role="timecode">00:00:00</span>'
      +   '<span class="preview-monitor__hint" data-role="hint"></span>'
      + '</div>';

    _rootEl = el;
    _stageEl = el.querySelector('[data-role="stage"]');
    _imgEl = el.querySelector('[data-role="image"]');
    _videoEl = el.querySelector('[data-role="video"]');
    _statusEl = el.querySelector('[data-role="status"]');
    _playBtn = el.querySelector('[data-role="play"]');
    _stopBtn = el.querySelector('[data-role="stop"]');
    _timecodeEl = el.querySelector('[data-role="timecode"]');
    _hintEl = el.querySelector('[data-role="hint"]');
    _overlayEl = el.querySelector('[data-role="overlay"]');
    _overlayTextEl = el.querySelector('[data-role="overlay-text"]');
    _overlayFillEl = el.querySelector('[data-role="overlay-fill"]');
    _dragHandleEl = el.querySelector('[data-role="drag-handle"]');

    _wireControls();
    _wireVideoEvents();
    _wireDragHandle();
    return el;
  }

  function _playGlyph() {
    return '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">'
         +   '<polygon points="3,2 13,8 3,14" fill="currentColor"/>'
         + '</svg>';
  }

  function _pauseGlyph() {
    return '<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">'
         +   '<rect x="3" y="2" width="3.5" height="12" fill="currentColor"/>'
         +   '<rect x="9.5" y="2" width="3.5" height="12" fill="currentColor"/>'
         + '</svg>';
  }

  function _stopGlyph() {
    return '<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">'
         +   '<rect x="3" y="3" width="10" height="10" fill="currentColor"/>'
         + '</svg>';
  }

  function _wireControls() {
    _playBtn.addEventListener('click', _onPlayClick);
    _stopBtn.addEventListener('click', _onStopClick);
  }

  function _wireVideoEvents() {
    _videoEl.addEventListener('timeupdate', function () {
      if (_displayMode !== 'playback') return;
      var ms = Math.round(_videoEl.currentTime * 1000);
      _playheadRequestedMs = ms;
      _setTimecode(ms);
      // Tell the timeline editor so its own playhead tracks playback.
      document.dispatchEvent(new CustomEvent('ora:preview-playhead-update', {
        detail: { playhead_ms: ms },
      }));
    });
    _videoEl.addEventListener('play',  function () { _setPlayPauseGlyph('pause'); });
    _videoEl.addEventListener('pause', function () { _setPlayPauseGlyph('play'); });
    _videoEl.addEventListener('ended', function () { _setPlayPauseGlyph('play'); });
    _videoEl.addEventListener('error', function () {
      _setStatus('error', 'Playback failed');
    });
  }

  function _setPlayPauseGlyph(state) {
    if (!_playBtn) return;
    if (state === 'pause') {
      _playBtn.innerHTML = _pauseGlyph();
      _playBtn.setAttribute('aria-label', 'Pause');
    } else {
      _playBtn.innerHTML = _playGlyph();
      _playBtn.setAttribute('aria-label', 'Play');
    }
  }

  function _setTimecode(ms) {
    if (_timecodeEl) _timecodeEl.textContent = _formatTimecode(ms);
  }

  function _setStatus(kind, label) {
    if (!_statusEl) return;
    _statusEl.dataset.kind = kind || 'unknown';
    _statusEl.title = label || '';
    if (_hintEl) _hintEl.textContent = label || '';
  }

  // ── Drag-to-position overlay handle (Phase 6 follow-up, 2026-05-01) ─────
  //
  // When timeline-editor announces a positionable overlay is selected
  // (`ora:overlay-selected` event), we render a small dashed-outline
  // handle on the preview stage at the overlay's normalized position.
  // Dragging the handle calls OraTimelineEditor.setOverlayPosition(...)
  // on pointerup, which schedules a save and triggers a preview reload
  // via `ora:timeline-mutated`. The handle position math is pure (test
  // hooks below) so future renderer-anchor changes can be reflected
  // without touching DOM.

  function _pixelToPercent(clientX, clientY, stageRect) {
    var w = Math.max(1, stageRect.width);
    var h = Math.max(1, stageRect.height);
    var x_pct = (clientX - stageRect.left) / w;
    var y_pct = (clientY - stageRect.top)  / h;
    return {
      x_pct: Math.max(0, Math.min(1, x_pct)),
      y_pct: Math.max(0, Math.min(1, y_pct)),
    };
  }

  // Pure function exposed for tests. Returns the {left, top, width, height}
  // (in pixels relative to the stage) that the drag handle should occupy
  // for an overlay with the given normalized position. Width is computed
  // from `width_pct`; height is a fixed-fraction guess (lower-thirds are
  // ~12% of frame height in practice; the renderer wraps to its own font
  // size so this is a visual-only approximation).
  function _handleRect(position, stageW, stageH) {
    var x_pct     = (position && typeof position.x_pct     === 'number') ? position.x_pct     : 0.5;
    var y_pct     = (position && typeof position.y_pct     === 'number') ? position.y_pct     : 0.85;
    var width_pct = (position && typeof position.width_pct === 'number') ? position.width_pct : 0.5;
    width_pct = Math.max(0.05, Math.min(1.0, width_pct));
    return {
      left:   Math.round(x_pct * stageW),
      top:    Math.round(y_pct * stageH),
      width:  Math.round(width_pct * stageW),
      height: Math.max(20, Math.round(stageH * 0.12)),
    };
  }

  function _setOverlayHandle(detail) {
    _selectedOverlay = detail || null;
    if (!_dragHandleEl) return;
    if (!_selectedOverlay) {
      _dragHandleEl.hidden = true;
      _dragHandleEl.removeAttribute('data-overlay-clip-id');
      return;
    }
    _dragHandleEl.hidden = false;
    _dragHandleEl.dataset.overlayClipId = _selectedOverlay.clipId || '';
    _positionDragHandle();
  }

  function _positionDragHandle() {
    if (!_dragHandleEl || !_stageEl || !_selectedOverlay) return;
    var stageRect = _stageEl.getBoundingClientRect();
    var rect = _handleRect(_selectedOverlay.position,
                           stageRect.width, stageRect.height);
    _dragHandleEl.style.left   = rect.left   + 'px';
    _dragHandleEl.style.top    = rect.top    + 'px';
    _dragHandleEl.style.width  = rect.width  + 'px';
    _dragHandleEl.style.height = rect.height + 'px';
    var labelEl = _dragHandleEl.querySelector('[data-role="drag-handle-label"]');
    if (labelEl) {
      labelEl.textContent =
        Math.round(_selectedOverlay.position.x_pct * 100) + ', ' +
        Math.round(_selectedOverlay.position.y_pct * 100) + '%';
    }
  }

  function _wireDragHandle() {
    if (!_dragHandleEl) return;
    _dragHandleEl.addEventListener('pointerdown', _onHandlePointerDown);
  }

  function _onHandlePointerDown(e) {
    if (!_selectedOverlay || !_stageEl) return;
    e.preventDefault();
    e.stopPropagation();
    var stageRect = _stageEl.getBoundingClientRect();
    var pos0 = _pixelToPercent(e.clientX, e.clientY, stageRect);
    _dragState = {
      stageRect: stageRect,
      // Offset between the click and the handle's anchor (top-left), in
      // normalized units. Lets the user grab the handle anywhere and have
      // it follow the cursor without snapping its anchor under the
      // pointer.
      anchorOffset: {
        x_pct: _selectedOverlay.position.x_pct - pos0.x_pct,
        y_pct: _selectedOverlay.position.y_pct - pos0.y_pct,
      },
    };
    _dragHandleEl.classList.add('is-dragging');
    if (_dragHandleEl.setPointerCapture) {
      try { _dragHandleEl.setPointerCapture(e.pointerId); } catch (err) {}
    }
    _dragHandleEl.addEventListener('pointermove', _onHandlePointerMove);
    _dragHandleEl.addEventListener('pointerup',   _onHandlePointerUp);
    _dragHandleEl.addEventListener('pointercancel', _onHandlePointerUp);
  }

  function _onHandlePointerMove(e) {
    if (!_dragState || !_selectedOverlay) return;
    e.preventDefault();
    var p = _pixelToPercent(e.clientX, e.clientY, _dragState.stageRect);
    var x = Math.max(0, Math.min(1, p.x_pct + _dragState.anchorOffset.x_pct));
    var y = Math.max(0, Math.min(1, p.y_pct + _dragState.anchorOffset.y_pct));
    // Update the live position visually; commit to timeline-editor only on
    // pointerup so we don't spam _scheduleSave during the drag.
    _selectedOverlay.position.x_pct = x;
    _selectedOverlay.position.y_pct = y;
    _positionDragHandle();
  }

  function _onHandlePointerUp(e) {
    if (!_dragState) return;
    e.preventDefault();
    _dragHandleEl.classList.remove('is-dragging');
    if (_dragHandleEl.releasePointerCapture && e.pointerId != null) {
      try { _dragHandleEl.releasePointerCapture(e.pointerId); } catch (err) {}
    }
    _dragHandleEl.removeEventListener('pointermove', _onHandlePointerMove);
    _dragHandleEl.removeEventListener('pointerup',   _onHandlePointerUp);
    _dragHandleEl.removeEventListener('pointercancel', _onHandlePointerUp);
    _dragState = null;

    // Commit the new position to the timeline editor. It schedules a save
    // and fires `ora:timeline-mutated`, which our existing handler picks
    // up to invalidate the proxy and refresh the preview frame.
    var Editor = (typeof window !== 'undefined') && window.OraTimelineEditor;
    if (Editor && typeof Editor.setOverlayPosition === 'function'
        && _selectedOverlay) {
      try {
        Editor.setOverlayPosition(
          _selectedOverlay.trackId,
          _selectedOverlay.clipId,
          _selectedOverlay.position.x_pct,
          _selectedOverlay.position.y_pct
        );
      } catch (err) { /* swallow — editor errors shouldn't kill preview */ }
    }
  }

  function _showOverlay(text, pct) {
    if (!_overlayEl) return;
    _overlayEl.classList.add('preview-monitor__overlay--visible');
    if (_overlayTextEl) _overlayTextEl.textContent = text || '';
    if (_overlayFillEl) {
      var p = (typeof pct === 'number') ? Math.max(0, Math.min(100, pct)) : 0;
      _overlayFillEl.style.width = p + '%';
    }
  }

  function _hideOverlay() {
    if (!_overlayEl) return;
    _overlayEl.classList.remove('preview-monitor__overlay--visible');
  }

  // ── Frame mode ───────────────────────────────────────────────────────────

  function _scheduleFrameRefresh() {
    if (_frameDebounce) {
      try { clearTimeout(_frameDebounce); } catch (e) { /* ignore */ }
    }
    _frameDebounce = setTimeout(_fetchFrameNow, 200);
  }

  function _fetchFrameNow() {
    _frameDebounce = null;
    if (!_conversationId || _displayMode !== 'frame') return;
    if (_frameInflightController) {
      try { _frameInflightController.abort(); } catch (e) { /* ignore */ }
    }
    var ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    _frameInflightController = ctrl;
    var url = '/api/preview/' + encodeURIComponent(_conversationId) +
              '/frame?ms=' + encodeURIComponent(_playheadRequestedMs) +
              '&_=' + Date.now();
    fetch(url, { signal: ctrl ? ctrl.signal : undefined })
      .then(function (r) {
        if (!r.ok) return null;
        return r.blob();
      })
      .then(function (blob) {
        if (!blob || _displayMode !== 'frame' || !_imgEl) return;
        var dataUrl = URL.createObjectURL(blob);
        var prev = _imgEl.dataset.objUrl;
        _imgEl.src = dataUrl;
        _imgEl.dataset.objUrl = dataUrl;
        if (prev) {
          // Defer revoke so the browser doesn't lose the texture mid-paint.
          setTimeout(function () { URL.revokeObjectURL(prev); }, 250);
        }
      })
      .catch(function () { /* aborted or network — ignore */ });
  }

  // ── Playback / proxy lifecycle ───────────────────────────────────────────

  function _enterPlaybackMode() {
    _displayMode = 'playback';
    if (_rootEl) _rootEl.classList.add('preview-monitor--playback');
    _videoEl.src = '/api/preview/' + encodeURIComponent(_conversationId) +
                   '/proxy/file?_=' + Date.now();
    var seekToMs = _playheadRequestedMs;
    _videoEl.addEventListener('loadedmetadata', function _onceMeta() {
      _videoEl.removeEventListener('loadedmetadata', _onceMeta);
      try {
        if (seekToMs > 0) _videoEl.currentTime = seekToMs / 1000;
      } catch (e) { /* not yet seekable */ }
      var p = _videoEl.play();
      if (p && typeof p.then === 'function') {
        p.catch(function () { /* autoplay denied → stays paused, that's fine */ });
      }
    }, { once: true });
  }

  function _exitPlaybackMode() {
    _displayMode = 'frame';
    if (_rootEl) _rootEl.classList.remove('preview-monitor--playback');
    try { _videoEl.pause(); } catch (e) { /* ignore */ }
    try {
      _videoEl.removeAttribute('src');
      _videoEl.load();
    } catch (e) { /* ignore */ }
    _setPlayPauseGlyph('play');
    _scheduleFrameRefresh();
  }

  function _onPlayClick() {
    if (_displayMode === 'playback') {
      // Toggle.
      if (_videoEl.paused) {
        var p = _videoEl.play();
        if (p && typeof p.then === 'function') p.catch(function () {});
      } else {
        try { _videoEl.pause(); } catch (e) { /* ignore */ }
      }
      return;
    }
    // Frame mode → ensure proxy is fresh, then enter playback.
    _refreshProxyState().then(function (st) {
      if (st && st.fresh) {
        _enterPlaybackMode();
      } else {
        _startProxyRender();
      }
    });
  }

  function _onStopClick() {
    if (_displayMode === 'playback') {
      _exitPlaybackMode();
    } else {
      _scheduleFrameRefresh();
    }
  }

  function _refreshProxyState() {
    if (!_conversationId) return Promise.resolve(null);
    return fetch('/api/preview/' + encodeURIComponent(_conversationId) + '/state')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        _proxyState = j || null;
        _updateStatusFromProxyState();
        return j;
      })
      .catch(function () { return null; });
  }

  function _updateStatusFromProxyState() {
    if (!_proxyState) {
      _setStatus('unknown', '');
      return;
    }
    if (_proxyState.fresh) {
      _setStatus('fresh', 'Playback ready');
    } else if (_proxyState.has_proxy) {
      _setStatus('stale', 'Cache stale — Press Play to rebuild');
    } else {
      _setStatus('none', 'Press Play to build playback cache');
    }
  }

  function _startProxyRender() {
    if (!_conversationId) return;
    _showOverlay('Building preview…', 0);
    _setStatus('rendering', 'Rendering proxy…');
    fetch('/api/preview/' + encodeURIComponent(_conversationId) + '/proxy/start',
          { method: 'POST' })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j && j.render_id) {
          _activeProxyRenderId = j.render_id;
          _ensureRenderEventStream();
        } else {
          _hideOverlay();
          _setStatus('error', (j && j.error) || 'Render failed to start');
        }
      })
      .catch(function () {
        _hideOverlay();
        _setStatus('error', 'Render failed to start');
      });
  }

  function _ensureRenderEventStream() {
    if (_renderEventListenerInstalled) return;
    _renderEventListenerInstalled = true;
    // V3 Backlog 2A Chunk 5 follow-up (2026-04-30) — SSE retired.
    // render-controls.js polls /api/render/<id>/state and dispatches
    // `ora:render-state` for each non-duplicate frame; we filter on the
    // current proxy render_id.
    document.addEventListener('ora:render-state', function (e) {
      var msg = e && e.detail;
      if (!msg) return;
      if (msg.render_id !== _activeProxyRenderId) return;
      _onProxyRenderEvent(msg);
    });
  }

  function _onProxyRenderEvent(ev) {
    var t = ev.type;
    if (t === 'progress') {
      var pct = Math.floor(ev.progress_pct || 0);
      _showOverlay('Building preview… ' + pct + '%', ev.progress_pct);
    } else if (t === 'complete') {
      _hideOverlay();
      _activeProxyRenderId = null;
      _refreshProxyState().then(function () { _enterPlaybackMode(); });
    } else if (t === 'failed' || t === 'cancelled') {
      _hideOverlay();
      _activeProxyRenderId = null;
      _setStatus('error', t === 'cancelled' ? 'Render cancelled' : 'Render failed');
    } else if (t === 'rendering' || t === 'queued') {
      _showOverlay('Building preview…', 0);
    }
  }

  // ── Show / hide ──────────────────────────────────────────────────────────

  function _findVisualHost() {
    return document.querySelector('.visual-panel')
        || document.querySelector('.pane.right-pane');
  }

  function _show() {
    var host = _findVisualHost();
    if (!host) return;
    _hostEl = host;
    if (!_rootEl) _build();
    if (!_rootEl.parentNode) host.appendChild(_rootEl);
    _rootEl.classList.add('preview-monitor--visible');
    _setPlayPauseGlyph('play');
    _refreshProxyState();
    _scheduleFrameRefresh();
  }

  function _hide() {
    if (_rootEl) _rootEl.classList.remove('preview-monitor--visible');
    if (_displayMode === 'playback') _exitPlaybackMode();
    if (_eventSource) {
      try { _eventSource.close(); } catch (e) { /* ignore */ }
      _eventSource = null;
    }
  }

  // ── External plumbing ────────────────────────────────────────────────────

  function setConversationId(id) {
    _conversationId = id || null;
    _activeProxyRenderId = null;
    _playheadRequestedMs = 0;
    _setTimecode(0);
    if (_displayMode === 'playback') _exitPlaybackMode();
    if (document.body.classList.contains('pane-mode-video')) {
      _refreshProxyState();
      _scheduleFrameRefresh();
    }
  }

  function reload() {
    _refreshProxyState();
    _scheduleFrameRefresh();
  }

  function init() {
    document.addEventListener('ora:pane-mode-toggle', function (e) {
      var cur = e.detail && e.detail.current;
      if (cur === 'video') _show(); else _hide();
    });
    document.addEventListener('ora:conversation-selected', function (e) {
      var d = e.detail || {};
      var cid = d.conversation_id || d.id || null;
      if (cid) setConversationId(cid);
    });
    document.addEventListener('ora:timeline-playhead-changed', function (e) {
      var d = e.detail || {};
      _playheadRequestedMs = Number(d.playhead_ms) || 0;
      _setTimecode(_playheadRequestedMs);
      if (_displayMode === 'frame') {
        _scheduleFrameRefresh();
      } else if (_displayMode === 'playback' && d.source !== 'preview') {
        // External scrub during playback → seek the video.
        try { _videoEl.currentTime = _playheadRequestedMs / 1000; }
        catch (err) { /* not seekable yet */ }
      }
    });
    document.addEventListener('ora:timeline-mutated', function () {
      // Mutations invalidate the proxy.
      if (_displayMode === 'playback') _exitPlaybackMode();
      if (_conversationId) {
        fetch('/api/preview/' + encodeURIComponent(_conversationId) +
              '/invalidate', { method: 'POST' })
          .catch(function () { /* ignore */ });
      }
      _refreshProxyState();
      _scheduleFrameRefresh();
      // If an overlay handle is showing, its position may have been
      // changed externally (e.g. via the inspector form fields) — re-
      // anchor in case those values diverged from our cached copy.
      _positionDragHandle();
    });
    document.addEventListener('ora:overlay-selected', function (e) {
      _setOverlayHandle(e && e.detail);
    });
    _build();
  }

  // Re-anchor the drag handle on window resize so the percentage-driven
  // placement keeps tracking the stage's actual pixel size.
  if (typeof window !== 'undefined') {
    window.addEventListener('resize', function () {
      if (_selectedOverlay) _positionDragHandle();
    });
  }

  root.OraPreviewMonitor = {
    init: init,
    setConversationId: setConversationId,
    reload: reload,
    getState: function () {
      return {
        displayMode: _displayMode,
        conversationId: _conversationId,
        playheadMs: _playheadRequestedMs,
        proxyState: _proxyState,
        activeProxyRenderId: _activeProxyRenderId,
        selectedOverlay: _selectedOverlay
          ? JSON.parse(JSON.stringify(_selectedOverlay))
          : null,
      };
    },
    // Phase 6 follow-up — pure-math hooks for unit tests.
    _pixelToPercent: _pixelToPercent,
    _handleRect: _handleRect,
  };
})(typeof window !== 'undefined' ? window : this);
