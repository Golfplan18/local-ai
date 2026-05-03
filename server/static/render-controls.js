/**
 * render-controls.js — Audio/Video Phase 7
 *
 * Render UI:
 *   - "Render" button + preset picker in the timeline editor's ruler row.
 *   - Progress modal (cancel-able) that follows the render via polling.
 *   - On success: success card with the output path + "Reveal" / "Open"
 *     hooks (delegated to a future settings-driven file-opener).
 *   - On failure: pop-up overlay with Dismiss / Retry / Get AI help.
 *
 * Polling: while a render is active we poll /api/render/<render_id>/state
 * at 1.5 s and stop when the render reaches a terminal status. Each
 * lifecycle transition is dispatched as an `ora:render-state` CustomEvent
 * on document so preview-monitor.js (and any other listener) can react
 * without owning its own polling loop.
 *
 * (The earlier /api/render/stream SSE feed was retired 2026-05-01.)
 *
 * Public namespace: window.OraRenderControls
 *   .init()
 *   .setConversationId(id)
 *   .openRenderPicker()       — programmatic open of the preset menu
 *   .getState()               — snapshot for tests
 */
(function (root) {
  'use strict';

  if (typeof document === 'undefined') return;

  // ── module state ─────────────────────────────────────────────────────────

  var _conversationId = null;
  var _presets = [];
  var _eventSource = null;
  var _activeRenderId = null;
  var _activePreset = null;          // preset key for the current render
  var _lastUsedPreset = 'standard';  // sticky default for the keyboard shortcut
  var _userDefaultPreset = null;     // from /api/settings (Phase 9 wiring)
  var _backgroundThresholdSeconds = 90;  // auto-background renders longer than this; 0 disables modal entirely
  var _autoBackgroundChecked = false;     // one-shot per render
  var _modalEl = null;
  var _errorPopupEl = null;
  var _renderBtnEl = null;           // the Render button in the timeline ruler row
  var _ctxMenuEl = null;
  var _backgroundPillEl = null;      // mini pill shown when modal is dismissed mid-render

  // ── helpers ──────────────────────────────────────────────────────────────

  function _esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function _findVisualHost() {
    return document.querySelector('.visual-panel')
        || document.querySelector('.pane.right-pane');
  }

  // ── render button — mounted into the timeline editor's ruler row ────────

  function _ensureRenderButton() {
    if (_renderBtnEl) return _renderBtnEl;
    var editor = document.querySelector('.timeline-editor');
    if (!editor) return null;
    var rulerRow = editor.querySelector('.timeline-editor__ruler-row');
    if (!rulerRow) return null;

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'render-controls__btn';
    btn.dataset.role = 'render';
    btn.setAttribute('aria-label', 'Render');
    btn.title = 'Render the timeline to a file';
    btn.innerHTML = ''
      + '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" '
      +   'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
      +   '<polygon points="5 3 19 12 5 21 5 3"/>'
      + '</svg>'
      + '<span>Render</span>';
    btn.addEventListener('click', openRenderPicker);
    rulerRow.appendChild(btn);
    _renderBtnEl = btn;
    return btn;
  }

  function _removeRenderButton() {
    if (_renderBtnEl) {
      try { _renderBtnEl.remove(); } catch (e) { /* ignore */ }
      _renderBtnEl = null;
    }
  }

  function openRenderPicker() {
    if (_ctxMenuEl) { _ctxMenuEl.remove(); _ctxMenuEl = null; }
    if (!_presets.length) {
      _showError('Render presets unavailable. Server may have failed to load the render module.');
      return;
    }
    var menu = document.createElement('div');
    menu.className = 'render-controls__menu';
    menu.innerHTML = '<div class="render-controls__menu-title">Render preset</div>'
      + _presets.map(function (p) {
          var isDefault = (p.key === _userDefaultPreset);
          var suffix = isDefault ? ' <span class="render-controls__menu-default">(default)</span>' : '';
          var dataAttr = isDefault ? ' data-default="true"' : '';
          return '<button type="button" data-preset="' + p.key + '"'
                 + dataAttr + '>' + _esc(p.label) + suffix + '</button>';
        }).join('');
    document.body.appendChild(menu);
    _ctxMenuEl = menu;

    if (_renderBtnEl) {
      var rect = _renderBtnEl.getBoundingClientRect();
      menu.style.left = rect.left + 'px';
      menu.style.top  = (rect.bottom + 4) + 'px';
    } else {
      menu.style.left = '50%';
      menu.style.top  = '50%';
    }

    Array.from(menu.querySelectorAll('button[data-preset]')).forEach(function (b) {
      b.addEventListener('click', function () {
        var key = b.dataset.preset;
        _closeMenu();
        _startRender(key);
      });
    });

    setTimeout(function () {
      document.addEventListener('click', _closeMenuOnOutsideClick, true);
    }, 0);
  }

  function _closeMenu() {
    document.removeEventListener('click', _closeMenuOnOutsideClick, true);
    if (_ctxMenuEl) {
      try { _ctxMenuEl.remove(); } catch (e) { /* ignore */ }
      _ctxMenuEl = null;
    }
  }

  function _closeMenuOnOutsideClick(e) {
    if (_ctxMenuEl && !e.target.closest('.render-controls__menu')) {
      _closeMenu();
    }
  }

  // ── lifecycle ────────────────────────────────────────────────────────────

  function _startRender(presetKey) {
    if (!_conversationId) {
      _showError('Open a conversation before rendering.');
      return;
    }
    _activePreset = presetKey;
    _lastUsedPreset = presetKey;
    _autoBackgroundChecked = false;
    _showProgressModal(presetKey);
    fetch('/api/render/' + encodeURIComponent(_conversationId), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preset: presetKey }),
    })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (j) { throw new Error(j.error || ('HTTP ' + r.status)); });
        return r.json();
      })
      .then(function (j) {
        _activeRenderId = j.render_id;
        _setModalStatus('Preparing…', 'preparing');
        // V3 Backlog 2A Chunk 5 — start polling now that we have an id.
        _ensurePolling();
      })
      .catch(function (err) {
        _setModalStatus('Failed to start: ' + err.message, 'failed');
        _showError('Failed to start render: ' + err.message);
        _hideProgressModal();
      });
  }

  function _cancelActiveRender() {
    if (!_activeRenderId) {
      _hideProgressModal();
      return;
    }
    fetch('/api/render/' + encodeURIComponent(_activeRenderId) + '/cancel',
      { method: 'POST' })
      .catch(function () { /* ignore */ });
  }

  // ── progress modal ───────────────────────────────────────────────────────

  function _showProgressModal(presetKey) {
    _hideProgressModal();
    var modal = document.createElement('div');
    modal.className = 'render-controls__modal';
    var presetLabel = ((_presets.find(function (p) { return p.key === presetKey; }) || {}).label) || presetKey;
    modal.innerHTML = ''
      + '<div class="render-controls__modal-card">'
      +   '<div class="render-controls__modal-head">'
      +     '<span class="render-controls__modal-title">Rendering…</span>'
      +     '<button type="button" class="render-controls__modal-close" aria-label="Close" title="Run in background">×</button>'
      +   '</div>'
      +   '<div class="render-controls__modal-body">'
      +     '<div class="render-controls__modal-preset">' + _esc(presetLabel) + '</div>'
      +     '<div class="render-controls__modal-bar"><div class="render-controls__modal-bar-fill" data-role="bar-fill" style="width:0%"></div></div>'
      +     '<div class="render-controls__modal-status" data-role="status" aria-live="polite">Starting…</div>'
      +     '<div class="render-controls__modal-output" data-role="output"></div>'
      +   '</div>'
      +   '<div class="render-controls__modal-foot">'
      +     '<button type="button" class="render-controls__modal-action" data-role="background">Run in background</button>'
      +     '<button type="button" class="render-controls__modal-action render-controls__modal-action--danger" data-role="cancel">Cancel</button>'
      +   '</div>'
      + '</div>';
    document.body.appendChild(modal);
    _modalEl = modal;
    // Close (X) and "Run in background" both dismiss the modal but keep
    // the render running. Cancel actually stops the render.
    modal.querySelector('.render-controls__modal-close').addEventListener('click', _detachToBackground);
    modal.querySelector('[data-role="background"]').addEventListener('click', _detachToBackground);
    modal.querySelector('[data-role="cancel"]').addEventListener('click', _cancelActiveRender);
  }

  function _setModalStatus(text, kind) {
    if (!_modalEl) return;
    var statusEl = _modalEl.querySelector('[data-role="status"]');
    if (statusEl) statusEl.textContent = text;
    if (kind) _modalEl.dataset.state = kind;
  }

  function _setModalProgress(pct) {
    if (!_modalEl) return;
    var fill = _modalEl.querySelector('[data-role="bar-fill"]');
    if (fill) fill.style.width = Math.max(0, Math.min(100, pct)).toFixed(1) + '%';
  }

  function _setModalComplete(outputPath) {
    if (!_modalEl) return;
    _setModalProgress(100);
    _setModalStatus('Render complete.', 'complete');
    var outEl = _modalEl.querySelector('[data-role="output"]');
    if (outEl) {
      outEl.innerHTML = ''
        + '<span class="render-controls__modal-output-label">Saved to</span>'
        + '<code>' + _esc(outputPath) + '</code>';
    }
    var foot = _modalEl.querySelector('.render-controls__modal-foot');
    if (foot) {
      foot.innerHTML = ''
        + '<button type="button" class="render-controls__modal-action" data-role="dismiss">Dismiss</button>';
      foot.querySelector('[data-role="dismiss"]').addEventListener('click', _hideProgressModal);
    }
  }

  function _hideProgressModal() {
    if (!_modalEl) return;
    try { _modalEl.remove(); } catch (e) { /* ignore */ }
    _modalEl = null;
    _activeRenderId = null;
  }

  // Modal-X / "Run in background": close the modal but keep the render
  // running. A small pill in the timeline editor's ruler row tracks
  // progress; clicking it brings the modal back.
  function _detachToBackground() {
    if (!_modalEl) return;
    try { _modalEl.remove(); } catch (e) { /* ignore */ }
    _modalEl = null;
    if (_activeRenderId) _ensureBackgroundPill();
  }

  function _ensureBackgroundPill() {
    if (_backgroundPillEl) return _backgroundPillEl;
    var rulerRow = document.querySelector('.timeline-editor__ruler-row');
    if (!rulerRow) return null;
    var pill = document.createElement('button');
    pill.type = 'button';
    pill.className = 'render-controls__bg-pill';
    pill.dataset.role = 'bg-pill';
    pill.title = 'Click to view render progress';
    pill.innerHTML = ''
      + '<span class="render-controls__bg-pill-spinner"></span>'
      + '<span class="render-controls__bg-pill-text" data-role="bg-text">Rendering…</span>';
    pill.addEventListener('click', _reattachBackground);
    rulerRow.appendChild(pill);
    _backgroundPillEl = pill;
    return pill;
  }

  function _updateBackgroundPill(pct, kind) {
    if (!_backgroundPillEl) return;
    var text = _backgroundPillEl.querySelector('[data-role="bg-text"]');
    if (text) {
      if (kind === 'rendering') {
        text.textContent = 'Rendering ' + Math.round(pct || 0) + '%';
      } else if (kind === 'queued') {
        text.textContent = 'Queued…';
      } else if (kind === 'preparing') {
        text.textContent = 'Preparing…';
      }
    }
    _backgroundPillEl.dataset.state = kind;
  }

  function _removeBackgroundPill() {
    if (!_backgroundPillEl) return;
    try { _backgroundPillEl.remove(); } catch (e) { /* ignore */ }
    _backgroundPillEl = null;
  }

  function _reattachBackground() {
    if (!_activeRenderId) {
      _removeBackgroundPill();
      return;
    }
    _showProgressModal(_activePreset);
    // Pull current state once so the modal isn't stuck at 0% until the
    // next SSE progress frame.
    fetch('/api/render/' + encodeURIComponent(_activeRenderId) + '/state')
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (typeof j.progress_pct === 'number') _setModalProgress(j.progress_pct);
        if (j.state === 'rendering') {
          _setModalStatus('Rendering… ' + Math.round(j.progress_pct) + '%', 'rendering');
        }
      })
      .catch(function () { /* ignore */ });
    _removeBackgroundPill();
  }

  // ── error pop-up + integrated background-monitor errored-state ──────────

  function _showError(message) {
    _hideErrorPopup();
    var popup = document.createElement('div');
    popup.className = 'render-controls__error';
    popup.innerHTML = ''
      + '<div class="render-controls__error-card">'
      +   '<div class="render-controls__error-head">'
      +     '<span class="render-controls__error-title">Render failed</span>'
      +     '<button type="button" class="render-controls__error-close" aria-label="Close">×</button>'
      +   '</div>'
      +   '<div class="render-controls__error-body">' + _esc(message) + '</div>'
      +   '<div class="render-controls__error-foot">'
      +     '<button type="button" data-role="dismiss">Dismiss</button>'
      +     '<button type="button" data-role="retry">Retry</button>'
      +     '<button type="button" data-role="ai-help">Get AI help</button>'
      +   '</div>'
      + '</div>';
    document.body.appendChild(popup);
    _errorPopupEl = popup;
    popup.querySelector('.render-controls__error-close').addEventListener('click', _hideErrorPopup);
    popup.querySelector('[data-role="dismiss"]').addEventListener('click', _hideErrorPopup);
    popup.querySelector('[data-role="retry"]').addEventListener('click', function () {
      _hideErrorPopup();
      if (_activePreset) _startRender(_activePreset);
    });
    popup.querySelector('[data-role="ai-help"]').addEventListener('click', function () {
      _hideErrorPopup();
      _routeToAiHelp(message);
    });
  }

  function _hideErrorPopup() {
    if (!_errorPopupEl) return;
    try { _errorPopupEl.remove(); } catch (e) { /* ignore */ }
    _errorPopupEl = null;
  }

  function _routeToAiHelp(message) {
    // Submit the failure summary into the input pane as a draft prompt
    // and dispatch an event so the main pipeline picks it up. Phase 7
    // doesn't run the pipeline directly — the user reviews and submits.
    var ta = document.querySelector('.input-pane textarea');
    if (!ta) return;
    var draft = 'My video render failed. Please help me debug.\n\n'
      + 'Preset: ' + (_activePreset || 'unknown') + '\n'
      + 'Error:\n' + message;
    ta.value = draft;
    ta.dispatchEvent(new Event('input', {bubbles: true}));
    ta.focus();
  }

  // ── State polling (V3 Backlog 2A Chunk 5 follow-up, 2026-04-30) ─────────
  //
  // SSE retired. We poll /api/render/<render_id>/state at 1.5 s while a
  // render is active, and dispatch an `ora:render-state` event so other
  // listeners (preview-monitor.js) can react without subscribing to an
  // SSE stream. Polling stops when the render goes terminal.

  var _pollTimer = null;
  var _pollLastSeen = '';

  function _connectSSE() { /* poller starts when a render begins */ }

  function _ensurePolling() {
    if (_pollTimer) return;
    if (!_activeRenderId) return;
    _pollTimer = setInterval(_pollOnce, 1500);
    _pollOnce();
  }

  function _stopPolling() {
    if (_pollTimer) {
      try { clearInterval(_pollTimer); } catch (_e) {}
      _pollTimer = null;
    }
    _pollLastSeen = '';
  }

  function _pollOnce() {
    if (!_activeRenderId) { _stopPolling(); return; }
    fetch('/api/render/' + encodeURIComponent(_activeRenderId) + '/state')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (state) {
        if (!state) return;
        var key = state.type + ':' + (state.progress_pct || 0);
        if (_pollLastSeen === key) return;
        _pollLastSeen = key;
        state.render_id = _activeRenderId;
        _handleEvent(state);
        // Notify preview-monitor.js (which used to listen on the SSE
        // stream directly) so it can refresh proxy frames on render
        // events without its own polling loop.
        try {
          document.dispatchEvent(new CustomEvent('ora:render-state', { detail: state }));
        } catch (_e) {}
        if (state.type === 'complete' || state.type === 'failed' || state.type === 'cancelled') {
          _stopPolling();
        }
      })
      .catch(function () { /* network blip — keep polling */ });
  }

  // Phase 9 wiring — rough estimate (in seconds) of how long a render
  // will take given timeline duration and preset. Numbers are tuned
  // against M-series Apple Silicon; real wall-clock varies a lot. We
  // only need a rough cut-off for the auto-background decision.
  var _PRESET_SPEED_FACTOR = {
    'standard':   1.0,
    'high':       3.0,
    'web':        1.0,
    'mov':        1.0,
    'webm':       5.0,
    'audio_only': 0.1,
  };

  function _maybeAutoBackground(durationMs) {
    if (_autoBackgroundChecked) return;
    _autoBackgroundChecked = true;
    if (!_modalEl) return;            // modal already dismissed manually
    if (_backgroundThresholdSeconds <= 0) {
      // 0 means "always render in the background" — surface the pill,
      // close the modal immediately.
      _detachToBackground();
      return;
    }
    if (!isFinite(durationMs) || durationMs <= 0) return;
    var factor = _PRESET_SPEED_FACTOR[_activePreset] || 1.0;
    var estSeconds = (durationMs / 1000) * factor;
    if (estSeconds > _backgroundThresholdSeconds) {
      _detachToBackground();
    }
  }

  function _handleEvent(ev) {
    switch (ev.type) {
      case 'queued':
        _setModalStatus('Queued…', 'queued');
        _updateBackgroundPill(0, 'queued');
        _maybeAutoBackground(ev.duration_ms);
        break;
      case 'rendering':
        _setModalStatus('Rendering…', 'rendering');
        _updateBackgroundPill(0, 'rendering');
        _maybeAutoBackground(ev.duration_ms);
        break;
      case 'progress':
        if (typeof ev.progress_pct === 'number') {
          _setModalProgress(ev.progress_pct);
          _setModalStatus('Rendering… ' + Math.round(ev.progress_pct) + '%', 'rendering');
          _updateBackgroundPill(ev.progress_pct, 'rendering');
        }
        break;
      case 'complete':
        _setModalComplete(ev.output_path || '');
        _activeRenderId = null;
        if (_backgroundPillEl) {
          // If the user dismissed to background, surface a brief
          // success state on the pill before retiring it.
          _backgroundPillEl.dataset.state = 'complete';
          var bgText = _backgroundPillEl.querySelector('[data-role="bg-text"]');
          if (bgText) bgText.textContent = 'Render saved';
          setTimeout(_removeBackgroundPill, 4000);
        }
        break;
      case 'failed':
        _hideProgressModal();
        _removeBackgroundPill();
        _showError(ev.error || 'Unknown render error');
        _activeRenderId = null;
        break;
      case 'cancelled':
        _setModalStatus('Cancelled.', 'cancelled');
        setTimeout(_hideProgressModal, 800);
        _removeBackgroundPill();
        _activeRenderId = null;
        break;
      default:
        break;
    }
  }

  // ── show / hide on pane-mode-toggle ──────────────────────────────────────

  function _onPaneModeToggle(e) {
    var cur = e.detail && e.detail.current;
    if (cur === 'video') {
      _ensureRenderButton();
      // If a render was running when video mode last closed, the pill
      // should reappear when we re-enter.
      if (_activeRenderId && !_modalEl) _ensureBackgroundPill();
    } else {
      _removeRenderButton();
      _hideProgressModal();
      _hideErrorPopup();
      _closeMenu();
      // Keep the pill mounted while video mode is hidden? No — it lives
      // in the timeline ruler row which gets unmounted. The render
      // continues server-side and the pill re-mounts on re-entry.
      _removeBackgroundPill();
    }
  }

  // ── external plumbing ────────────────────────────────────────────────────

  function setConversationId(id) {
    _conversationId = id || null;
  }

  // Cmd+Shift+E (E for export). In-page only — same constraint as the
  // capture shortcut from Phase 4. Triggers a render with the last-used
  // preset (or "standard" on first use).
  function _onKeydown(e) {
    if (!document.body.classList.contains('pane-mode-video')) return;
    var key = (e.key || '').toLowerCase();
    if (key !== 'e') return;
    var meta = e.metaKey || e.ctrlKey;
    if (!meta || !e.shiftKey) return;
    if (_activeRenderId) return;  // already rendering — ignore the chord
    e.preventDefault();
    e.stopPropagation();
    _startRender(_lastUsedPreset || 'standard');
  }

  function init() {
    document.addEventListener('ora:pane-mode-toggle', _onPaneModeToggle);
    document.addEventListener('ora:conversation-selected', function (e) {
      var d = e.detail || {};
      var cid = d.conversation_id || d.id || null;
      if (cid) setConversationId(cid);
    });
    document.addEventListener('keydown', _onKeydown, true);

    fetch('/api/render/presets').then(function (r) { return r.json(); }).then(function (j) {
      _presets = (j && j.presets) || [];
    }).catch(function () { _presets = []; });

    // Phase 9 wiring — fetch user's default render preset so the picker
    // can mark it and the keyboard-shortcut path can default to it on
    // first use of the session. Also load the background-render
    // threshold for the auto-background check below.
    fetch('/api/settings').then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        var exp = data && data.settings && data.settings.export;
        if (exp && exp.default_render_preset) {
          _userDefaultPreset = exp.default_render_preset;
          _lastUsedPreset = exp.default_render_preset;
        }
        if (exp && typeof exp.background_render_threshold_seconds === 'number') {
          _backgroundThresholdSeconds = exp.background_render_threshold_seconds;
        }
      })
      .catch(function () { /* fall back to hardcoded defaults */ });

    _connectSSE();
  }

  root.OraRenderControls = {
    init: init,
    setConversationId: setConversationId,
    openRenderPicker: openRenderPicker,
    getState: function () {
      return {
        conversationId: _conversationId,
        activeRenderId: _activeRenderId,
        activePreset: _activePreset,
        presetCount: _presets.length,
      };
    },
  };
})(typeof window !== 'undefined' ? window : this);
