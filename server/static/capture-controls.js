/**
 * capture-controls.js — Audio/Video Phase 1
 *
 * Capture controls toolbar that lives inside the visual pane when
 * `body.pane-mode-video` is active. Mirrors the existing image/art
 * toolbar pattern (uses the shared `ora-toolbar` class so it inherits
 * the WP-7.1.4 chrome-hidden behavior). Wires up:
 *
 *   - Source selector (video device + audio device dropdowns) — Phase 1
 *     populates from /api/capture/devices.
 *   - Start / Pause / Stop buttons — call /api/capture/{start,
 *     <id>/pause, <id>/resume, <id>/stop}.
 *   - Live duration counter (HH:MM:SS, 100ms granularity).
 *   - Audio level meter (single bar driven by the lavfi.astats RMS
 *     dB stream from FFmpeg).
 *
 * Events consumed
 * ---------------
 * - `ora:pane-mode-toggle` (CustomEvent on document, detail.current ===
 *   'video' or null) — show/hide the toolbar.
 * - `ora:conversation-selected` (CustomEvent on document,
 *   detail.conversation_id) — track which conversation a Start should
 *   bind to.
 *
 * Polling
 * -------
 * While a capture is in-flight we poll /api/capture/<id>/state every
 * 500 ms (frame-rate display, audio meter, lifecycle transitions). On
 * each terminal transition (complete / failed / cancelled) we dispatch
 * a `ora:capture-state` CustomEvent on document so other modules
 * (media-library, etc.) can react without owning a polling loop.
 *
 * Earlier (Backlog 2A migration, 2026-04-30) the same lifecycle was
 * delivered via an SSE stream at /api/capture/stream; that endpoint
 * was retired 2026-05-01 along with the other zero-traffic streams.
 *
 * Public namespace: window.OraCaptureControls
 *   .init()                      → call once at page load
 *   .setConversationId(id)       → external override (chat-panel calls
 *                                  this when the active conversation
 *                                  changes through some non-standard path)
 *   .getState()                  → snapshot for tests
 */
(function (root) {
  'use strict';

  if (typeof document === 'undefined') return;  // jsdom guard

  // ── module state ─────────────────────────────────────────────────────────

  var _toolbarEl = null;        // the <div class="ora-toolbar capture-controls">
  var _hostEl = null;           // the visual-panel root we mounted into
  var _conversationId = null;   // current active conversation
  var _captureId = null;        // current in-flight capture, or null
  var _captureState = 'idle';   // idle|recording|paused|stopping|complete|failed
  var _devices = { video: [], audio: [] };
  var _selectedVideo = '3';     // primary screen on the dev box; updated from device probe
  var _selectedAudio = null;    // null = no audio capture; '0', '1', etc = audio device index
  var _selectedWebcam = null;   // null = no PiP; otherwise device index
  var _userSettings = null;     // Phase 9 wiring — populated from /api/settings on init
  var _selectedCorner = 'bottom-right'; // top-left / top-right / bottom-left / bottom-right
  var _selectedCrop = null;     // null = full-screen; otherwise {x,y,w,h} in source pixels
  var _eventSource = null;       // legacy, no longer assigned (Backlog 2A Chunk 5)
  var _pollTimer = null;         // V3 Backlog 2A Chunk 5 — replaces _eventSource
  var _durationMs = 0;
  var _localTickHandle = null;  // setInterval handle for sub-stat-line UI smoothness
  var _lastDurationStamp = 0;   // wall-clock ms when _durationMs was last touched by SSE
  var _rmsDb = null;            // last seen RMS level dB
  var _regionOverlay = null;    // region-selection overlay element when active

  // ── DOM build ────────────────────────────────────────────────────────────

  function _formatDuration(ms) {
    if (!isFinite(ms) || ms < 0) ms = 0;
    var totalSec = Math.floor(ms / 1000);
    var h = Math.floor(totalSec / 3600);
    var m = Math.floor((totalSec % 3600) / 60);
    var s = totalSec % 60;
    var hh = (h < 10 ? '0' : '') + h;
    var mm = (m < 10 ? '0' : '') + m;
    var ss = (s < 10 ? '0' : '') + s;
    return hh + ':' + mm + ':' + ss;
  }

  function _build() {
    if (_toolbarEl) return _toolbarEl;
    var el = document.createElement('div');
    el.className = 'ora-toolbar capture-controls';
    el.setAttribute('role', 'toolbar');
    el.setAttribute('aria-label', 'Video capture controls');
    el.innerHTML = ''
      + '<div class="capture-controls__sources">'
      +   '<label class="capture-controls__source-label">Screen'
      +     '<select class="capture-controls__select" data-role="video-device" aria-label="Video source"></select>'
      +   '</label>'
      +   '<label class="capture-controls__source-label">Audio'
      +     '<select class="capture-controls__select" data-role="audio-device" aria-label="Audio source">'
      +       '<option value="">None</option>'
      +     '</select>'
      +   '</label>'
      +   '<label class="capture-controls__source-label">Webcam'
      +     '<select class="capture-controls__select" data-role="webcam-device" aria-label="Webcam (picture-in-picture)">'
      +       '<option value="">Off</option>'
      +     '</select>'
      +   '</label>'
      + '</div>'
      // Webcam corner picker — 2x2 grid mirroring the 4 PiP positions.
      // Hidden when webcam is "Off"; reveals when a webcam device is picked.
      + '<div class="capture-controls__corner-picker" data-role="corner-picker" aria-label="PiP corner" hidden>'
      +   '<button type="button" data-corner="top-left" class="capture-controls__corner" aria-label="Top-left">⌜</button>'
      +   '<button type="button" data-corner="top-right" class="capture-controls__corner" aria-label="Top-right">⌝</button>'
      +   '<button type="button" data-corner="bottom-left" class="capture-controls__corner" aria-label="Bottom-left">⌞</button>'
      +   '<button type="button" data-corner="bottom-right" class="capture-controls__corner" aria-label="Bottom-right" data-active="true">⌟</button>'
      + '</div>'
      // Region selection trigger.
      + '<button type="button" class="ora-toolbar__item capture-controls__btn capture-controls__btn-region" data-role="select-region" aria-label="Select region" title="Pick a rectangular region of the screen to capture">'
      +   '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
      +     '<rect x="3" y="3" width="18" height="18" rx="2" stroke-dasharray="3 3"/>'
      +     '<rect x="7" y="7" width="10" height="10" fill="currentColor" fill-opacity="0.25"/>'
      +   '</svg>'
      +   '<span class="capture-controls__btn-label" data-role="region-btn-label">Region</span>'
      + '</button>'
      + '<button type="button" class="ora-toolbar__item capture-controls__btn capture-controls__start" data-role="start" aria-label="Start recording" title="Start recording (⌘⇧R)">'
      +   '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true"><circle cx="12" cy="12" r="6"/></svg>'
      +   '<span class="capture-controls__btn-label">Start</span>'
      + '</button>'
      + '<button type="button" class="ora-toolbar__item capture-controls__btn capture-controls__pause" data-role="pause" aria-label="Pause recording" title="Pause recording (⌘⇧R while recording)" disabled>'
      +   '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true"><rect x="6" y="5" width="4" height="14"/><rect x="14" y="5" width="4" height="14"/></svg>'
      +   '<span class="capture-controls__btn-label">Pause</span>'
      + '</button>'
      + '<button type="button" class="ora-toolbar__item capture-controls__btn capture-controls__stop" data-role="stop" aria-label="Stop recording" title="Stop recording" disabled>'
      +   '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12"/></svg>'
      +   '<span class="capture-controls__btn-label">Stop</span>'
      + '</button>'
      + '<div class="capture-controls__duration" data-role="duration" aria-live="polite">00:00:00</div>'
      + '<div class="capture-controls__meter" data-role="meter" aria-label="Audio level">'
      +   '<div class="capture-controls__meter-fill" data-role="meter-fill"></div>'
      + '</div>'
      + '<div class="capture-controls__status" data-role="status" aria-live="polite"></div>';
    _toolbarEl = el;
    _wire();
    return el;
  }

  function _wire() {
    var btnStart = _toolbarEl.querySelector('[data-role="start"]');
    var btnPause = _toolbarEl.querySelector('[data-role="pause"]');
    var btnStop  = _toolbarEl.querySelector('[data-role="stop"]');
    btnStart.addEventListener('click', function () {
      if (_captureState === 'recording') return;  // safety
      if (_captureState === 'paused') { _resumeCapture(); return; }
      _startCapture();
    });
    btnPause.addEventListener('click', _pauseCapture);
    btnStop.addEventListener('click',  _stopCapture);

    var selVid = _toolbarEl.querySelector('[data-role="video-device"]');
    var selAud = _toolbarEl.querySelector('[data-role="audio-device"]');
    var selWeb = _toolbarEl.querySelector('[data-role="webcam-device"]');
    selVid.addEventListener('change', function () {
      _selectedVideo = selVid.value;
      // Picking a different screen invalidates any existing region — the
      // crop coordinates are in the prior source's pixel space.
      if (_selectedCrop) {
        _selectedCrop = null;
        _refreshRegionIndicator();
      }
    });
    selAud.addEventListener('change', function () {
      _selectedAudio = selAud.value === '' ? null : selAud.value;
    });
    selWeb.addEventListener('change', function () {
      _selectedWebcam = selWeb.value === '' ? null : selWeb.value;
      var picker = _toolbarEl.querySelector('[data-role="corner-picker"]');
      if (picker) picker.hidden = (_selectedWebcam === null);
    });

    // Webcam corner picker
    Array.from(_toolbarEl.querySelectorAll('.capture-controls__corner')).forEach(function (b) {
      b.addEventListener('click', function () {
        _selectedCorner = b.dataset.corner;
        Array.from(_toolbarEl.querySelectorAll('.capture-controls__corner')).forEach(function (other) {
          if (other === b) other.dataset.active = 'true';
          else delete other.dataset.active;
        });
      });
    });

    // Region selection
    var btnRegion = _toolbarEl.querySelector('[data-role="select-region"]');
    btnRegion.addEventListener('click', function () {
      if (_selectedCrop) {
        // If a region is already set, this button clears it.
        _selectedCrop = null;
        _refreshRegionIndicator();
        return;
      }
      _openRegionOverlay();
    });
  }

  function _refreshRegionIndicator() {
    if (!_toolbarEl) return;
    var label = _toolbarEl.querySelector('[data-role="region-btn-label"]');
    if (!label) return;
    if (_selectedCrop) {
      label.textContent = _selectedCrop.w + '×' + _selectedCrop.h + ' ✕';
    } else {
      label.textContent = 'Region';
    }
  }

  function _friendlyScreenLabel(rawName, ordinal) {
    // FFmpeg labels them "Capture screen 0", "Capture screen 1", … —
    // remap to the user's mental model.
    if (ordinal === 0) return 'Primary Display';
    if (ordinal === 1) return 'Secondary Display';
    if (ordinal === 2) return 'Tertiary Display';
    return 'Display ' + (ordinal + 1);
  }

  // Phase 9 wiring — apply the user's saved capture defaults to the
  // already-populated dropdowns. Called after both the device probe
  // and the /api/settings fetch have landed; either order is fine
  // since both call paths converge here.
  function _applyUserCaptureDefaults() {
    if (!_userSettings || !_toolbarEl) return;
    var cap = _userSettings.capture || {};
    var selAud = _toolbarEl.querySelector('[data-role="audio-device"]');
    var selWeb = _toolbarEl.querySelector('[data-role="webcam-device"]');
    if (selAud && cap.default_audio_device) {
      // Match by exact display name from /api/capture/devices.
      var aud = (_devices.audio || []).find(function (d) {
        return d.name === cap.default_audio_device;
      });
      if (aud) {
        selAud.value = String(aud.index);
        _selectedAudio = String(aud.index);
      }
    }
    if (selWeb && cap.default_webcam_device) {
      var allVideo = _devices.video || [];
      var webcams = allVideo.filter(function (d) { return !/screen/i.test(d.name); });
      var web = webcams.find(function (d) {
        return d.name === cap.default_webcam_device;
      });
      if (web) {
        selWeb.value = String(web.index);
        _selectedWebcam = String(web.index);
        var picker = _toolbarEl.querySelector('[data-role="corner-picker"]');
        if (picker) picker.hidden = false;
      }
    }
  }

  function _populateDevices() {
    if (!_toolbarEl) return;
    var selVid = _toolbarEl.querySelector('[data-role="video-device"]');
    var selAud = _toolbarEl.querySelector('[data-role="audio-device"]');
    var selWeb = _toolbarEl.querySelector('[data-role="webcam-device"]');

    var allVideo = _devices.video || [];
    var screens = allVideo.filter(function (d) { return /screen/i.test(d.name); });
    var cameras = allVideo.filter(function (d) { return !/screen/i.test(d.name); });
    if (!screens.length) screens = allVideo;

    // Screen dropdown — friendly labels.
    selVid.innerHTML = '';
    screens.forEach(function (d, i) {
      var opt = document.createElement('option');
      opt.value = String(d.index);
      opt.textContent = _friendlyScreenLabel(d.name, i);
      opt.title = d.name;
      selVid.appendChild(opt);
    });
    if (screens.length) {
      _selectedVideo = String(screens[0].index);
      selVid.value = _selectedVideo;
    }

    // Audio dropdown — None + raw device names (audio names already are
    // user-recognizable, e.g. "iPhone Microphone", "BlackHole 2ch").
    selAud.innerHTML = '<option value="">None</option>';
    (_devices.audio || []).forEach(function (d) {
      var opt = document.createElement('option');
      opt.value = String(d.index);
      opt.textContent = d.name;
      selAud.appendChild(opt);
    });
    selAud.value = '';
    _selectedAudio = null;

    // Webcam dropdown — Off + non-screen video devices.
    selWeb.innerHTML = '<option value="">Off</option>';
    cameras.forEach(function (d) {
      var opt = document.createElement('option');
      opt.value = String(d.index);
      opt.textContent = d.name;
      selWeb.appendChild(opt);
    });
    selWeb.value = '';
    _selectedWebcam = null;
    var picker = _toolbarEl.querySelector('[data-role="corner-picker"]');
    if (picker) picker.hidden = true;

    // Phase 9 wiring — apply user defaults if they've already loaded.
    _applyUserCaptureDefaults();
  }

  // ── Show / hide on pane-mode toggle ──────────────────────────────────────

  function _findVisualHost() {
    return document.querySelector('.visual-panel')
        || document.querySelector('.pane.right-pane')
        || document.querySelector('.pane.visual-pane');
  }

  function _show() {
    var host = _findVisualHost();
    if (!host) return;
    _hostEl = host;
    if (!_toolbarEl) _build();
    if (!_toolbarEl.parentNode) host.appendChild(_toolbarEl);
    _toolbarEl.classList.add('capture-controls--visible');
  }

  function _hide() {
    if (_toolbarEl) {
      _toolbarEl.classList.remove('capture-controls--visible');
    }
    _closeRegionOverlay();
  }

  // ── Region selection overlay (Phase 4 option B) ──────────────────────────
  //
  // Pulls a single still frame of the currently-selected screen, paints it
  // inside the visual pane, and lets the user drag a rectangle. Coordinates
  // are translated from displayed pixels to source pixels and stored as
  // `_selectedCrop` (consumed by `_startCapture`).

  function _openRegionOverlay() {
    var host = _findVisualHost();
    if (!host) return;
    if (_regionOverlay) _closeRegionOverlay();

    var overlay = document.createElement('div');
    overlay.className = 'capture-region-overlay';
    overlay.innerHTML = ''
      + '<div class="capture-region-overlay__chrome">'
      +   '<div class="capture-region-overlay__hint">Click and drag on the snapshot to select a region.</div>'
      +   '<button type="button" class="capture-region-overlay__btn" data-role="confirm" disabled>Confirm</button>'
      +   '<button type="button" class="capture-region-overlay__btn" data-role="cancel">Cancel</button>'
      + '</div>'
      + '<div class="capture-region-overlay__stage" data-role="stage">'
      +   '<div class="capture-region-overlay__loading">Capturing snapshot…</div>'
      + '</div>';
    host.appendChild(overlay);
    _regionOverlay = overlay;

    var stage = overlay.querySelector('[data-role="stage"]');
    var btnConfirm = overlay.querySelector('[data-role="confirm"]');
    var btnCancel = overlay.querySelector('[data-role="cancel"]');
    btnCancel.addEventListener('click', _closeRegionOverlay);

    fetch('/api/capture/region-snapshot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_device: _selectedVideo }),
    })
      .then(function (r) {
        if (!r.ok) return r.text().then(function (t) { throw new Error(t || ('HTTP ' + r.status)); });
        return r.blob();
      })
      .then(function (blob) {
        var url = URL.createObjectURL(blob);
        stage.innerHTML = '';
        var img = document.createElement('img');
        img.className = 'capture-region-overlay__image';
        img.src = url;
        img.draggable = false;
        img.alt = 'Region selection snapshot';
        img.onload = function () {
          stage.dataset.naturalWidth = img.naturalWidth;
          stage.dataset.naturalHeight = img.naturalHeight;
          _wireRegionDrag(stage, img, btnConfirm);
        };
        stage.appendChild(img);
      })
      .catch(function (err) {
        stage.innerHTML = '<div class="capture-region-overlay__error">Snapshot failed: '
          + (err.message || 'unknown error') + '</div>';
      });
  }

  function _closeRegionOverlay() {
    if (!_regionOverlay) return;
    try { _regionOverlay.remove(); } catch (e) { /* ignore */ }
    _regionOverlay = null;
  }

  function _wireRegionDrag(stage, img, btnConfirm) {
    var rect = null;             // {x, y, w, h} in DISPLAYED pixels
    var dragStart = null;        // {x, y}
    var rectEl = document.createElement('div');
    rectEl.className = 'capture-region-overlay__rect';
    rectEl.style.display = 'none';
    stage.appendChild(rectEl);

    function drawRect() {
      if (!rect) {
        rectEl.style.display = 'none';
        btnConfirm.disabled = true;
        return;
      }
      rectEl.style.display = '';
      rectEl.style.left = rect.x + 'px';
      rectEl.style.top = rect.y + 'px';
      rectEl.style.width = rect.w + 'px';
      rectEl.style.height = rect.h + 'px';
      btnConfirm.disabled = (rect.w < 10 || rect.h < 10);
    }

    function localXY(e) {
      var b = stage.getBoundingClientRect();
      var imgB = img.getBoundingClientRect();
      // Coordinates relative to the displayed image, clamped.
      var x = Math.max(0, Math.min(imgB.width,  e.clientX - imgB.left));
      var y = Math.max(0, Math.min(imgB.height, e.clientY - imgB.top));
      // Express in stage coords (so position with absolute matches image position).
      return { x: x + (imgB.left - b.left), y: y + (imgB.top - b.top) };
    }

    stage.addEventListener('mousedown', function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      var p = localXY(e);
      dragStart = p;
      rect = { x: p.x, y: p.y, w: 0, h: 0 };
      drawRect();
    });
    document.addEventListener('mousemove', function (e) {
      if (!dragStart) return;
      var p = localXY(e);
      rect = {
        x: Math.min(dragStart.x, p.x),
        y: Math.min(dragStart.y, p.y),
        w: Math.abs(p.x - dragStart.x),
        h: Math.abs(p.y - dragStart.y),
      };
      drawRect();
    });
    document.addEventListener('mouseup', function () {
      if (!dragStart) return;
      dragStart = null;
    });

    btnConfirm.addEventListener('click', function () {
      if (!rect) return;
      // Translate displayed pixels → source pixels.
      var imgB = img.getBoundingClientRect();
      var stageB = stage.getBoundingClientRect();
      var displayLeft = imgB.left - stageB.left;
      var displayTop = imgB.top - stageB.top;
      var scaleX = parseFloat(stage.dataset.naturalWidth)  / imgB.width;
      var scaleY = parseFloat(stage.dataset.naturalHeight) / imgB.height;
      var sourceX = Math.round((rect.x - displayLeft) * scaleX);
      var sourceY = Math.round((rect.y - displayTop)  * scaleY);
      var sourceW = Math.round(rect.w * scaleX);
      var sourceH = Math.round(rect.h * scaleY);
      // FFmpeg crop demands even values for yuv420p. Round to even.
      sourceX -= sourceX % 2;
      sourceY -= sourceY % 2;
      sourceW -= sourceW % 2;
      sourceH -= sourceH % 2;
      _selectedCrop = { x: Math.max(0, sourceX),
                        y: Math.max(0, sourceY),
                        w: sourceW, h: sourceH };
      _refreshRegionIndicator();
      _closeRegionOverlay();
    });
  }

  // ── Capture lifecycle (network) ──────────────────────────────────────────

  function _setStatus(text, kind) {
    if (!_toolbarEl) return;
    var el = _toolbarEl.querySelector('[data-role="status"]');
    if (el) {
      el.textContent = text || '';
      el.dataset.kind = kind || '';
    }
  }

  function _refreshButtons() {
    if (!_toolbarEl) return;
    var s = _captureState;
    var btnStart = _toolbarEl.querySelector('[data-role="start"]');
    var btnPause = _toolbarEl.querySelector('[data-role="pause"]');
    var btnStop  = _toolbarEl.querySelector('[data-role="stop"]');
    btnStart.disabled = (s === 'recording' || s === 'stopping');
    btnPause.disabled = (s !== 'recording');
    btnStop.disabled  = (s !== 'recording' && s !== 'paused');
    btnStart.querySelector('.capture-controls__btn-label').textContent =
      (s === 'paused') ? 'Resume' : 'Start';
    _toolbarEl.dataset.state = s;
  }

  function _startCapture() {
    if (!_conversationId) {
      _setStatus('Open a conversation before starting a capture.', 'warn');
      return;
    }
    _setStatus('Starting…', 'info');
    var fr = (_userSettings && _userSettings.capture
              && _userSettings.capture.frame_rate) || 30;
    var captureOpts = {
      video_device: _selectedVideo,
      audio_device: _selectedAudio,
      frame_rate: fr,
    };
    if (_selectedWebcam !== null) {
      captureOpts.webcam_device = _selectedWebcam;
      captureOpts.webcam_corner = _selectedCorner;
    }
    if (_selectedCrop) {
      captureOpts.crop = _selectedCrop;
    }
    var body = {
      conversation_id: _conversationId,
      options: captureOpts,
    };
    fetch('/api/capture/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(function (r) {
      if (!r.ok) return r.json().then(function (j) { throw new Error(j.error || ('HTTP ' + r.status)); });
      return r.json();
    }).then(function (j) {
      _captureId = j.capture_id;
      _captureState = (j.state && j.state.state) || 'recording';
      _durationMs = 0;
      _lastDurationStamp = Date.now();
      _refreshButtons();
      _setStatus('', '');
      _ensureLocalTick();
      // V3 Backlog 2A Chunk 5 — start polling once we have a capture id.
      _ensurePollTimer();
    }).catch(function (e) {
      _setStatus('Start failed: ' + e.message, 'error');
    });
  }

  function _pauseCapture() {
    if (!_captureId) return;
    fetch('/api/capture/' + _captureId + '/pause', { method: 'POST' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function () { _captureState = 'paused'; _refreshButtons(); })
      .catch(function (e) { _setStatus('Pause failed: ' + e.message, 'error'); });
  }

  function _resumeCapture() {
    if (!_captureId) return;
    fetch('/api/capture/' + _captureId + '/resume', { method: 'POST' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function () {
        _captureState = 'recording';
        _lastDurationStamp = Date.now();
        _refreshButtons();
        _ensureLocalTick();
      })
      .catch(function (e) { _setStatus('Resume failed: ' + e.message, 'error'); });
  }

  function _stopCapture() {
    if (!_captureId) return;
    _captureState = 'stopping';
    _refreshButtons();
    _setStatus('Finalizing…', 'info');
    fetch('/api/capture/' + _captureId + '/stop', { method: 'POST' })
      .then(function (r) { if (!r.ok) return r.json().then(function (j) { throw new Error(j.error || ('HTTP ' + r.status)); }); return r.json(); })
      .then(function (j) {
        _captureState = 'complete';
        _refreshButtons();
        _setStatus('Saved: ' + (j.file_path || ''), 'success');
        // Hold _captureId until next start so the SSE 'complete' frame
        // can match. New start will overwrite.
      })
      .catch(function (e) {
        _captureState = 'failed';
        _refreshButtons();
        _setStatus('Stop failed: ' + e.message, 'error');
      });
  }

  // ── State polling (V3 Backlog 2A Chunk 5, 2026-04-30) ──────────────────
  //
  // SSE retired in favor of polling /api/capture/<id>/state at 500 ms
  // while a capture is active. Live audio meters and duration counter
  // remain responsive enough; the cost is one HTTP round-trip per tick
  // for a single user, which is negligible. The poller starts when a
  // capture begins (handled in start/resume paths) and stops when the
  // state goes terminal (complete / failed) or the user navigates away.

  function _connectSSE() {
    // Compatibility shim — older callers expect _connectSSE() to set up
    // event ingestion. Polling uses the same _handleCaptureEvent path,
    // started lazily once a capture id exists.
    _ensurePollTimer();
  }

  function _ensurePollTimer() {
    if (_pollTimer) return;
    if (!_captureId) return; // nothing to poll yet
    _pollTimer = setInterval(_pollOnce, 500);
    _pollOnce();
  }

  function _stopPollTimer() {
    if (_pollTimer) {
      try { clearInterval(_pollTimer); } catch (_e) {}
      _pollTimer = null;
    }
  }

  function _pollOnce() {
    if (!_captureId) { _stopPollTimer(); return; }
    fetch('/api/capture/' + encodeURIComponent(_captureId) + '/state')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (state) {
        if (!state) return;
        // Server's /state returns { type, duration_ms, rms_db, ... }
        // matching the shape the SSE handler used to consume.
        _handleCaptureEvent(state);
        if (state.type === 'complete' || state.type === 'failed') {
          // Notify other modules (media-library refresh, etc.) so they
          // can react to capture lifecycle without subscribing to SSE.
          try {
            document.dispatchEvent(new CustomEvent('ora:capture-state', {
              detail: { capture_id: _captureId, state: state },
            }));
          } catch (_e) {}
          _stopPollTimer();
        }
      })
      .catch(function () { /* network blip — keep polling */ });
  }

  function _handleCaptureEvent(ev) {
    switch (ev.type) {
      case 'started':
        _captureState = 'recording';
        _lastDurationStamp = Date.now();
        break;
      case 'duration':
        if (typeof ev.duration_ms === 'number') {
          _durationMs = ev.duration_ms;
          _lastDurationStamp = Date.now();
          _renderDuration();
        }
        break;
      case 'level':
        if (typeof ev.rms_db === 'number') {
          _rmsDb = ev.rms_db;
          _renderLevel();
        }
        break;
      case 'paused':
        _captureState = 'paused';
        if (typeof ev.duration_ms === 'number') {
          _durationMs = ev.duration_ms;
          _renderDuration();
        }
        break;
      case 'resumed':
        _captureState = 'recording';
        _lastDurationStamp = Date.now();
        break;
      case 'complete':
        _captureState = 'complete';
        if (typeof ev.duration_ms === 'number') {
          _durationMs = ev.duration_ms;
          _renderDuration();
        }
        break;
      case 'failed':
        _captureState = 'failed';
        _setStatus('Capture failed: ' + (ev.error || 'unknown'), 'error');
        break;
      default:
        break;
    }
    _refreshButtons();
  }

  function _renderDuration() {
    if (!_toolbarEl) return;
    var el = _toolbarEl.querySelector('[data-role="duration"]');
    if (el) el.textContent = _formatDuration(_durationMs);
  }

  function _renderLevel() {
    if (!_toolbarEl) return;
    var fill = _toolbarEl.querySelector('[data-role="meter-fill"]');
    if (!fill) return;
    if (_rmsDb === null || !isFinite(_rmsDb)) {
      fill.style.width = '0%';
      return;
    }
    // Map -60 dB → 0%, 0 dB → 100% (linear in dB).
    var pct = Math.max(0, Math.min(100, ((_rmsDb + 60) / 60) * 100));
    fill.style.width = pct.toFixed(1) + '%';
  }

  function _ensureLocalTick() {
    // Smooth the duration display between FFmpeg `-stats` updates (which
    // typically arrive every ~500 ms). We extrapolate locally so the
    // counter ticks at 100 ms.
    if (_localTickHandle) return;
    _localTickHandle = setInterval(function () {
      if (_captureState !== 'recording') {
        clearInterval(_localTickHandle);
        _localTickHandle = null;
        return;
      }
      var now = Date.now();
      var delta = now - _lastDurationStamp;
      _renderDurationLocalExtrapolated(delta);
    }, 100);
  }

  function _renderDurationLocalExtrapolated(deltaMs) {
    if (!_toolbarEl) return;
    var el = _toolbarEl.querySelector('[data-role="duration"]');
    if (el) el.textContent = _formatDuration(_durationMs + Math.max(0, deltaMs));
  }

  // ── External plumbing ────────────────────────────────────────────────────

  function setConversationId(id) {
    _conversationId = id || null;
  }

  // ── Keyboard shortcut (in-page only — Phase 4) ───────────────────────────
  //
  // Cmd+Shift+R on macOS / Ctrl+Shift+R on Windows toggles the capture
  // lifecycle. The browser's hard-reload shortcut is also bound to that
  // chord; preventDefault() does NOT reliably override it in all
  // browsers. As a safety net we also bind Cmd+Option+R / Ctrl+Alt+R
  // which are unclaimed.
  function _matchShortcut(e) {
    var key = (e.key || '').toLowerCase();
    if (key !== 'r') return false;
    var meta = e.metaKey || e.ctrlKey;
    if (!meta) return false;
    if (e.shiftKey) return true;   // Cmd/Ctrl+Shift+R
    if (e.altKey)   return true;   // Cmd/Ctrl+Alt+R fallback
    return false;
  }

  function _onKeydown(e) {
    if (!_matchShortcut(e)) return;
    // Only intercept when video pane mode is active so we don't shadow
    // the browser's reload chord during normal editing.
    if (!document.body.classList.contains('pane-mode-video')) return;
    e.preventDefault();
    e.stopPropagation();
    if (_captureState === 'recording') {
      _stopCapture();
    } else if (_captureState === 'paused') {
      _resumeCapture();
    } else {
      _startCapture();
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
      if (cid) _conversationId = cid;
    });
    document.addEventListener('keydown', _onKeydown, true);

    fetch('/api/capture/devices').then(function (r) { return r.json(); }).then(function (d) {
      _devices = { video: d.video || [], audio: d.audio || [] };
      if (_toolbarEl) _populateDevices();
    }).catch(function () { /* ignore — devices stay empty until user retries */ });

    // Phase 9 wiring — fetch user-configured capture defaults.
    fetch('/api/settings').then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (data && data.settings) {
          _userSettings = data.settings;
          if (_toolbarEl && _devices.video) _applyUserCaptureDefaults();
        }
      })
      .catch(function () { /* defaults stay hardcoded if fetch fails */ });

    _connectSSE();

    // Pre-build so _populateDevices can fire as soon as devices arrive.
    _build();
    _refreshButtons();
  }

  root.OraCaptureControls = {
    init: init,
    setConversationId: setConversationId,
    getState: function () {
      return {
        captureId: _captureId,
        captureState: _captureState,
        conversationId: _conversationId,
        durationMs: _durationMs,
        rmsDb: _rmsDb,
        devices: _devices,
      };
    },
  };
})(typeof window !== 'undefined' ? window : this);
