/**
 * settings-panel.js — Audio/Video Phase 9
 *
 * Standalone centered modal with tabbed sections for user-configurable
 * defaults. Backed by /api/settings (non-secret) and /api/settings/api-key
 * (keyring-backed). API key values are write-only from the browser; the
 * GET endpoint only reports presence.
 *
 * Public namespace: window.OraSettingsPanel
 *   .init()              → call once at page load
 *   .open()              → show modal, fetch fresh state
 *   .close()             → hide
 *   .toggle()
 *   .getState()          → for tests
 */
(function (root) {
  'use strict';

  if (typeof document === 'undefined') return;

  // ── module state ─────────────────────────────────────────────────────────

  var _modalEl = null;
  var _backdropEl = null;
  var _tabsEl = null;
  var _tabContentEl = null;
  var _statusEl = null;
  var _activeTab = 'capture';
  var _settings = null;
  var _apiKeys = [];
  var _dirty = {};       // pending changes, applied on Save

  var TABS = [
    { id: 'capture',  label: 'Capture' },
    { id: 'whisper',  label: 'Whisper' },
    { id: 'apis',     label: 'External APIs' },
    { id: 'export',   label: 'Export' },
  ];

  var WHISPER_MODELS = [
    { id: 'tiny',     label: 'tiny (fastest, lowest accuracy)' },
    { id: 'base',     label: 'base' },
    { id: 'small',    label: 'small' },
    { id: 'medium',   label: 'medium' },
    { id: 'large-v3', label: 'large-v3 (default — most accurate)' },
  ];

  var WHISPER_LANGUAGES = [
    { id: 'auto', label: 'Auto-detect' },
    { id: 'en', label: 'English' },
    { id: 'es', label: 'Spanish' },
    { id: 'fr', label: 'French' },
    { id: 'de', label: 'German' },
    { id: 'it', label: 'Italian' },
    { id: 'pt', label: 'Portuguese' },
    { id: 'nl', label: 'Dutch' },
    { id: 'ru', label: 'Russian' },
    { id: 'ja', label: 'Japanese' },
    { id: 'zh', label: 'Chinese' },
    { id: 'ko', label: 'Korean' },
  ];

  var FRAME_RATES = [24, 25, 30, 50, 60];

  var RENDER_PRESETS = [
    { id: 'standard',   label: 'Standard (1080p · 30 fps · MP4)' },
    { id: 'high',       label: 'High quality (source res · 60 fps · MP4)' },
    { id: 'web',        label: 'Web optimized (1080p · 30 fps · faststart MP4)' },
    { id: 'mov',        label: 'QuickTime (1080p · 30 fps · MOV / H.264)' },
    { id: 'webm',       label: 'WebM (1080p · 30 fps · VP9 / Opus)' },
    { id: 'audio_only', label: 'Audio only (M4A · AAC 192k)' },
  ];

  // ── DOM build ────────────────────────────────────────────────────────────

  function _build() {
    if (_modalEl) return _modalEl;
    _backdropEl = document.createElement('div');
    _backdropEl.className = 'ora-settings-backdrop';
    _backdropEl.addEventListener('click', function (e) {
      if (e.target === _backdropEl) close();
    });

    _modalEl = document.createElement('div');
    _modalEl.className = 'ora-settings-modal';
    _modalEl.setAttribute('role', 'dialog');
    _modalEl.setAttribute('aria-modal', 'true');
    _modalEl.setAttribute('aria-labelledby', 'ora-settings-title');
    _modalEl.innerHTML = ''
      + '<div class="ora-settings-header">'
      +   '<h2 id="ora-settings-title">Ora Settings</h2>'
      +   '<button type="button" class="ora-settings-close" '
      +           'aria-label="Close settings">×</button>'
      + '</div>'
      + '<div class="ora-settings-tabs" role="tablist" data-role="tabs"></div>'
      + '<div class="ora-settings-tab-content" data-role="tab-content"></div>'
      + '<div class="ora-settings-footer">'
      +   '<span class="ora-settings-status" data-role="status"></span>'
      +   '<button type="button" class="ora-settings-btn ora-settings-btn--ghost" '
      +           'data-role="cancel">Cancel</button>'
      +   '<button type="button" class="ora-settings-btn ora-settings-btn--primary" '
      +           'data-role="save">Save</button>'
      + '</div>';
    _backdropEl.appendChild(_modalEl);

    _tabsEl = _modalEl.querySelector('[data-role="tabs"]');
    _tabContentEl = _modalEl.querySelector('[data-role="tab-content"]');
    _statusEl = _modalEl.querySelector('[data-role="status"]');

    _modalEl.querySelector('.ora-settings-close')
      .addEventListener('click', close);
    _modalEl.querySelector('[data-role="cancel"]')
      .addEventListener('click', close);
    _modalEl.querySelector('[data-role="save"]')
      .addEventListener('click', _onSave);

    _renderTabs();
    return _backdropEl;
  }

  function _renderTabs() {
    _tabsEl.innerHTML = '';
    TABS.forEach(function (t) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'ora-settings-tab';
      btn.setAttribute('role', 'tab');
      btn.dataset.tab = t.id;
      btn.textContent = t.label;
      if (t.id === _activeTab) btn.classList.add('ora-settings-tab--active');
      btn.addEventListener('click', function () {
        _activeTab = t.id;
        _renderTabs();
        _renderTabContent();
      });
      _tabsEl.appendChild(btn);
    });
  }

  function _renderTabContent() {
    _tabContentEl.innerHTML = '';
    if (!_settings) {
      _tabContentEl.textContent = 'Loading…';
      return;
    }
    if (_activeTab === 'capture') _renderCaptureTab();
    else if (_activeTab === 'whisper') _renderWhisperTab();
    else if (_activeTab === 'apis') _renderAPIsTab();
    else if (_activeTab === 'export') _renderExportTab();
  }

  // ── tabs ─────────────────────────────────────────────────────────────────

  function _renderCaptureTab() {
    var cap = (_dirty.capture || _settings.capture || {});
    var src = _settings.capture || {};
    _appendField('Default capture directory',
      _textInput('capture.default_directory',
                 cap.default_directory || src.default_directory || ''));
    _appendField('Frame rate',
      _selectInput('capture.frame_rate',
                   FRAME_RATES.map(function (n) {
                     return { id: n, label: n + ' fps' };
                   }),
                   cap.frame_rate || src.frame_rate));
    _appendField('Default audio device',
      _textInput('capture.default_audio_device',
                 cap.default_audio_device || src.default_audio_device || '',
                 'leave blank for system default'));
    _appendField('Capture system audio by default',
      _checkboxInput('capture.default_system_audio',
                     cap.default_system_audio !== undefined
                       ? cap.default_system_audio
                       : src.default_system_audio));
    _appendField('Default webcam device',
      _textInput('capture.default_webcam_device',
                 cap.default_webcam_device || src.default_webcam_device || '',
                 'leave blank to disable'));
  }

  function _renderWhisperTab() {
    var wh = (_dirty.whisper || _settings.whisper || {});
    var src = _settings.whisper || {};
    _appendField('Model size',
      _selectInput('whisper.model_size', WHISPER_MODELS,
                   wh.model_size || src.model_size));
    _appendField('Default language',
      _selectInput('whisper.default_language', WHISPER_LANGUAGES,
                   wh.default_language || src.default_language));
    _appendNote(
      'The local Whisper binary uses the model files under ~/.whisper/models/. '
      + 'Larger models are slower but more accurate. "tiny" runs near real-time '
      + 'on Apple Silicon; "large-v3" runs at roughly 1× real-time.'
    );
  }

  function _renderAPIsTab() {
    var api = (_dirty.external_apis || _settings.external_apis || {});
    var src = _settings.external_apis || {};
    _appendField('Transcription provider',
      _selectInput('external_apis.transcription_provider', [
        { id: 'whisper_local', label: 'Whisper (local)' },
        { id: 'assemblyai',    label: 'AssemblyAI' },
        { id: 'deepgram',      label: 'Deepgram' },
      ], api.transcription_provider || src.transcription_provider));
    _appendField('Text-to-speech provider',
      _selectInput('external_apis.tts_provider', [
        { id: 'openai',     label: 'OpenAI TTS' },
        { id: 'elevenlabs', label: 'ElevenLabs' },
      ], api.tts_provider || src.tts_provider));
    _appendNote(
      'Selecting an external transcription / TTS provider also requires '
      + 'setting that provider\'s API key below.'
    );

    // API key rows
    var keysHeader = document.createElement('h3');
    keysHeader.className = 'ora-settings-section-header';
    keysHeader.textContent = 'API keys';
    _tabContentEl.appendChild(keysHeader);

    var keysHint = document.createElement('p');
    keysHint.className = 'ora-settings-note';
    keysHint.textContent = 'Keys are stored in the macOS keychain. They are never '
      + 'shown back in the browser; if you need to update one, just type a new '
      + 'value and click Save.';
    _tabContentEl.appendChild(keysHint);

    _apiKeys.forEach(function (row) {
      _appendApiKeyRow(row);
    });
  }

  function _renderExportTab() {
    var ex = (_dirty.export || _settings.export || {});
    var src = _settings.export || {};
    _appendField('Default export directory',
      _textInput('export.default_directory',
                 ex.default_directory || src.default_directory || ''));
    _appendField('Default render preset',
      _selectInput('export.default_render_preset', RENDER_PRESETS,
                   ex.default_render_preset || src.default_render_preset));
    _appendField('Background-render threshold (seconds)',
      _numberInput('export.background_render_threshold_seconds',
                   ex.background_render_threshold_seconds !== undefined
                     ? ex.background_render_threshold_seconds
                     : src.background_render_threshold_seconds,
                   0, 7200));
    _appendNote(
      'Renders longer than this estimate run as background jobs '
      + 'with a progress pill instead of a blocking modal. '
      + 'Set to 0 to always render in the background.'
    );
  }

  function _appendApiKeyRow(row) {
    var wrap = document.createElement('div');
    wrap.className = 'ora-settings-apikey-row';

    var label = document.createElement('label');
    label.className = 'ora-settings-apikey-label';
    label.textContent = row.label;

    var status = document.createElement('span');
    status.className = 'ora-settings-apikey-status '
      + (row.present ? 'ora-settings-apikey-status--set'
                     : 'ora-settings-apikey-status--unset');
    status.textContent = row.present ? 'Set' : 'Not set';

    var input = document.createElement('input');
    input.type = 'password';
    input.placeholder = row.present ? '••••••••  (replace by typing new value)'
                                     : 'paste API key here';
    input.className = 'ora-settings-apikey-input';
    input.autocomplete = 'off';

    var saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.className = 'ora-settings-btn ora-settings-btn--small';
    saveBtn.textContent = 'Save key';
    saveBtn.addEventListener('click', function () {
      _saveApiKey(row.provider, input.value, status, input, saveBtn, removeBtn);
    });

    var removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'ora-settings-btn ora-settings-btn--small ora-settings-btn--danger';
    removeBtn.textContent = 'Remove';
    removeBtn.disabled = !row.present;
    removeBtn.addEventListener('click', function () {
      _deleteApiKey(row.provider, status, input, saveBtn, removeBtn);
    });

    wrap.appendChild(label);
    wrap.appendChild(status);
    wrap.appendChild(input);
    wrap.appendChild(saveBtn);
    wrap.appendChild(removeBtn);
    _tabContentEl.appendChild(wrap);
  }

  // ── input builders ───────────────────────────────────────────────────────

  function _appendField(labelText, inputEl) {
    var wrap = document.createElement('div');
    wrap.className = 'ora-settings-field';
    var label = document.createElement('label');
    label.className = 'ora-settings-field-label';
    label.textContent = labelText;
    wrap.appendChild(label);
    wrap.appendChild(inputEl);
    _tabContentEl.appendChild(wrap);
  }

  function _appendNote(text) {
    var note = document.createElement('p');
    note.className = 'ora-settings-note';
    note.textContent = text;
    _tabContentEl.appendChild(note);
  }

  function _textInput(path, value, placeholder) {
    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'ora-settings-input';
    input.value = value || '';
    if (placeholder) input.placeholder = placeholder;
    input.addEventListener('change', function () {
      _setDirty(path, input.value);
    });
    return input;
  }

  function _numberInput(path, value, min, max) {
    var input = document.createElement('input');
    input.type = 'number';
    input.className = 'ora-settings-input';
    input.value = value;
    if (min !== undefined) input.min = min;
    if (max !== undefined) input.max = max;
    input.addEventListener('change', function () {
      var n = parseInt(input.value, 10);
      if (!isFinite(n)) return;
      _setDirty(path, n);
    });
    return input;
  }

  function _selectInput(path, options, current) {
    var sel = document.createElement('select');
    sel.className = 'ora-settings-input';
    options.forEach(function (opt) {
      var o = document.createElement('option');
      o.value = String(opt.id);
      o.textContent = opt.label;
      if (String(opt.id) === String(current)) o.selected = true;
      sel.appendChild(o);
    });
    sel.addEventListener('change', function () {
      var v = sel.value;
      // Frame rate is numeric in our schema.
      if (path === 'capture.frame_rate'
          || path === 'export.background_render_threshold_seconds') {
        v = parseInt(v, 10);
      }
      _setDirty(path, v);
    });
    return sel;
  }

  function _checkboxInput(path, value) {
    var label = document.createElement('label');
    label.className = 'ora-settings-checkbox';
    var input = document.createElement('input');
    input.type = 'checkbox';
    input.checked = !!value;
    input.addEventListener('change', function () {
      _setDirty(path, input.checked);
    });
    label.appendChild(input);
    label.appendChild(document.createTextNode(' enabled'));
    return label;
  }

  // ── dirty tracking ───────────────────────────────────────────────────────

  function _setDirty(path, value) {
    var parts = path.split('.');
    var cur = _dirty;
    for (var i = 0; i < parts.length - 1; i++) {
      if (!cur[parts[i]] || typeof cur[parts[i]] !== 'object') {
        cur[parts[i]] = {};
      }
      cur = cur[parts[i]];
    }
    cur[parts[parts.length - 1]] = value;
  }

  // ── server I/O ───────────────────────────────────────────────────────────

  function _setStatus(msg, kind) {
    if (!_statusEl) return;
    _statusEl.textContent = msg || '';
    _statusEl.className = 'ora-settings-status'
      + (kind ? ' ora-settings-status--' + kind : '');
  }

  function _fetchState() {
    _setStatus('Loading…');
    return fetch('/api/settings')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        _settings = data.settings || {};
        _apiKeys = data.api_keys || [];
        _dirty = {};
        _renderTabContent();
        _setStatus('');
      })
      .catch(function (err) {
        _setStatus('Couldn’t load settings: ' + err.message, 'error');
      });
  }

  function _onSave() {
    if (!_settings) return;
    if (!Object.keys(_dirty).length) {
      _setStatus('Nothing to save.', 'info');
      return;
    }
    _setStatus('Saving…');
    fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ updates: _dirty }),
    })
      .then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, data: j }; });
      })
      .then(function (res) {
        if (!res.ok) {
          throw new Error((res.data && res.data.error) || 'save failed');
        }
        _settings = res.data.settings || _settings;
        _dirty = {};
        _setStatus('Saved.', 'success');
        _renderTabContent();
        setTimeout(function () { _setStatus(''); }, 2000);
      })
      .catch(function (err) {
        _setStatus('Save failed: ' + err.message, 'error');
      });
  }

  function _saveApiKey(provider, value, statusEl, inputEl, saveBtn, removeBtn) {
    var v = (value || '').trim();
    if (!v) {
      statusEl.textContent = 'Enter a value first.';
      return;
    }
    saveBtn.disabled = true;
    fetch('/api/settings/api-key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: provider, value: v }),
    })
      .then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, data: j }; });
      })
      .then(function (res) {
        if (!res.ok) {
          throw new Error((res.data && res.data.error) || 'save failed');
        }
        statusEl.textContent = 'Set';
        statusEl.className = 'ora-settings-apikey-status ora-settings-apikey-status--set';
        inputEl.value = '';
        inputEl.placeholder = '••••••••  (replace by typing new value)';
        removeBtn.disabled = false;
        // Reflect in the cached state for any later open without refetch.
        _apiKeys.forEach(function (row) {
          if (row.provider === provider) row.present = true;
        });
      })
      .catch(function (err) {
        statusEl.textContent = 'Save failed: ' + err.message;
      })
      .then(function () { saveBtn.disabled = false; });
  }

  function _deleteApiKey(provider, statusEl, inputEl, saveBtn, removeBtn) {
    if (!confirm('Remove the ' + provider + ' API key from this machine?\n'
                  + 'You can paste it back in later if you change your mind.')) return;
    removeBtn.disabled = true;
    fetch('/api/settings/api-key/' + encodeURIComponent(provider), {
      method: 'DELETE',
    })
      .then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, data: j }; });
      })
      .then(function (res) {
        if (!res.ok) {
          throw new Error((res.data && res.data.error) || 'delete failed');
        }
        statusEl.textContent = 'Not set';
        statusEl.className = 'ora-settings-apikey-status ora-settings-apikey-status--unset';
        inputEl.placeholder = 'paste API key here';
        _apiKeys.forEach(function (row) {
          if (row.provider === provider) row.present = false;
        });
      })
      .catch(function (err) {
        statusEl.textContent = 'Delete failed: ' + err.message;
        removeBtn.disabled = false;
      });
  }

  // ── show / hide ──────────────────────────────────────────────────────────

  function open() {
    if (!_backdropEl) _build();
    if (!_backdropEl.parentNode) document.body.appendChild(_backdropEl);
    _backdropEl.classList.add('ora-settings-backdrop--visible');
    _fetchState();
    document.addEventListener('keydown', _onKeydown);
  }

  function close() {
    if (_backdropEl) {
      _backdropEl.classList.remove('ora-settings-backdrop--visible');
    }
    document.removeEventListener('keydown', _onKeydown);
  }

  function toggle() {
    if (_backdropEl
        && _backdropEl.classList.contains('ora-settings-backdrop--visible')) {
      close();
    } else {
      open();
    }
  }

  function _onKeydown(e) {
    if (e.key === 'Escape') close();
  }

  function getState() {
    return {
      open: !!(_backdropEl && _backdropEl.classList.contains('ora-settings-backdrop--visible')),
      activeTab: _activeTab,
      hasDirty: Object.keys(_dirty).length > 0,
    };
  }

  function init() {
    // Build lazily on first open. Adding the gear button to the spine
    // is the caller's responsibility (see index-v3.html init block).
  }

  root.OraSettingsPanel = {
    init: init,
    open: open,
    close: close,
    toggle: toggle,
    getState: getState,
  };
})(typeof window !== 'undefined' ? window : this);
