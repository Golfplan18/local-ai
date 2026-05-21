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
  var _activeTab = 'models';
  var _settings = null;
  var _apiKeys = [];
  var _dirty = {};       // pending changes, applied on Save

  // Models tab hosts the classic ConfigPanel verbatim. _modelsConfigPanel
  // is the one live instance for the open settings modal (see _renderModelsTab).
  var _modelsConfigPanel = null;

  // Tabs declared in display order. The Buckets tab was retired with
  // install Chunk 10 step 2 — the bucket abstraction has been dissolved
  // by the configuration architecture (Premium / Optimum / Budget /
  // Free + named customs replace bucket-based slot assignment). The
  // Models tab now hosts the new OraModelsPane (server/static/models-pane.js);
  // Visual stays on the classic ConfigPanel until Chunk 11 rebuilds it.
  var TABS = [
    { id: 'models',         label: 'Models' },
    { id: 'visual',         label: 'Visual' },
    { id: 'transcription',  label: 'Transcription' },
    { id: 'speech',         label: 'Speech' },
    { id: 'interface',      label: 'Interface' },
    { id: 'capture',        label: 'Capture' },
    { id: 'apis',           label: 'External APIs' },
    { id: 'export',         label: 'Export' },
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
      +   '<button type="button" class="ora-settings-btn ora-settings-btn--primary" '
      +           'data-role="done">Done</button>'
      + '</div>';
    _backdropEl.appendChild(_modalEl);

    _tabsEl = _modalEl.querySelector('[data-role="tabs"]');
    _tabContentEl = _modalEl.querySelector('[data-role="tab-content"]');
    _statusEl = _modalEl.querySelector('[data-role="status"]');

    _modalEl.querySelector('.ora-settings-close')
      .addEventListener('click', close);
    _modalEl.querySelector('[data-role="done"]')
      .addEventListener('click', close);

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
    // The Models tab hosts the new OraModelsPane (install Chunk 10).
    // Visual stays on the classic ConfigPanel until Chunk 11 rebuilds
    // it; Buckets was retired (see the TABS comment above).
    if (_activeTab === 'models')  { _renderModelsPane();                         return; }
    if (_activeTab === 'visual')  { _renderConfigTab('visual', 'settings-visual'); return; }
    if (!_settings) {
      _tabContentEl.textContent = 'Loading…';
      return;
    }
    if (_activeTab === 'capture') _renderCaptureTab();
    else if (_activeTab === 'interface') _renderInterfaceTab();
    else if (_activeTab === 'transcription') _renderTranscriptionTab();
    else if (_activeTab === 'speech') _renderSpeechTab();
    else if (_activeTab === 'apis') _renderAPIsTab();
    else if (_activeTab === 'export') _renderExportTab();
  }

  function _renderInterfaceTab() {
    var iface = (_dirty.interface || _settings.interface || {});
    var src = _settings.interface || {};
    var enabled = iface.tooltips_enabled !== undefined
      ? iface.tooltips_enabled
      : (src.tooltips_enabled !== false);
    _appendField('Show themed hover tooltips',
      _checkboxInput('interface.tooltips_enabled', enabled));
    _appendNote(
      'When on, hovering over any button, icon, or list row for half a second '
      + 'shows a small description that matches the active theme. When off, '
      + 'your operating system\'s default tooltip is used instead — same '
      + 'information, plain styling.'
    );
  }

  // ── Models tab ───────────────────────────────────────────────────────────
  // The Models tab hosts OraModelsPane (server/static/models-pane.js),
  // a configuration-driven picker that replaces the classic ConfigPanel
  // embed (install Chunk 10). The pane fetches /api/model-registry and
  // /api/model-registry/picks on mount and renders preset cards, a
  // custom-new + previous grid, the vendor-organized inventory, and a
  // local-hardware section.
  //
  // The classic ConfigPanel is still loaded (server/static/config-panel.js
  // remains in index-v3.html's script list) — it powers the Visual tab
  // until Chunk 11 rebuilds that one too.

  function _renderModelsPane() {
    if (typeof OraModelsPane === 'undefined') {
      _tabContentEl.textContent =
        'models-pane.js is not loaded. Reload the page or check the network tab.';
      return;
    }
    _tabContentEl.innerHTML = '';
    var host = document.createElement('div');
    host.className = 'ora-settings-models-host';
    _tabContentEl.appendChild(host);
    try {
      OraModelsPane.init(host);
    } catch (err) {
      host.textContent = 'Could not load model configuration: '
        + ((err && err.message) || 'unknown error');
    }
  }

  // The classic ConfigPanel mount used by the Visual tab (until Chunk 11
  // rebuilds it). Pre-Chunk-10 the Models + Buckets tabs also used this.

  function _renderConfigTab(view, id) {
    if (typeof ConfigPanel === 'undefined') {
      _tabContentEl.textContent =
        'config-panel.js is not loaded. Reload the page or check the network tab.';
      return;
    }
    // Mount fresh on each tab open. Cheap (a single fetch + render) and
    // means the user always sees current routing/status without a stale
    // snapshot from a previous open.
    _tabContentEl.innerHTML = '';
    var host = document.createElement('div');
    host.className = 'ora-settings-config-host';
    _tabContentEl.appendChild(host);
    try {
      _modelsConfigPanel = new ConfigPanel(host, { id: id, view: view });
      _modelsConfigPanel.init();
    } catch (err) {
      host.textContent = 'Could not load model configuration: ' + (err && err.message);
    }
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

  // Transcription tab — replaces the former "Whisper" tab. Adds a
  // provider selector at the top so the user can route uploaded audio
  // through either the local Whisper binary or one of OpenRouter's
  // transcription models. The local-only fields (model size, language)
  // remain visible regardless; the OpenRouter model picker appears only
  // when that provider is selected.
  function _renderTranscriptionTab() {
    var wh = (_dirty.whisper || _settings.whisper || {});
    var src = _settings.whisper || {};
    var provider = wh.provider || src.provider || 'whisper_local';

    var providerSel = _selectInput('whisper.provider', [
        { id: 'whisper_local',    label: 'Local Whisper (free, runs on your hardware)' },
        { id: 'openrouter',       label: 'OpenRouter transcription (paid; bigger STT model selection)' },
        { id: 'openrouter_audio', label: 'OpenRouter audio understanding (ask questions about the audio)' },
      ], provider);
    _appendField('Transcription provider', providerSel);
    // Re-render the tab when the provider changes so the conditional
    // sub-fields (local model size vs OpenRouter picker) switch in place.
    providerSel.addEventListener('change', function () { _renderTabContent(); });

    _appendField('Default language',
      _selectInput('whisper.default_language', WHISPER_LANGUAGES,
                   wh.default_language || src.default_language));

    if (provider === 'whisper_local') {
      _appendField('Local Whisper model size',
        _selectInput('whisper.model_size', WHISPER_MODELS,
                     wh.model_size || src.model_size));
      _appendNote(
        'The local Whisper binary uses the model files under ~/.whisper/models/. '
        + 'Larger models are slower but more accurate. "tiny" runs near real-time '
        + 'on Apple Silicon; "large-v3" runs at roughly 1× real-time.'
      );
    } else if (provider === 'openrouter') {
      _appendOpenRouterTranscriptionPicker(
        wh.openrouter_model || src.openrouter_model || '');
      _appendNote(
        'OpenRouter relays your audio to one of the listed providers. '
        + 'Pricing varies — see the model row. The OpenRouter API key '
        + 'must be set under External APIs.'
      );
    } else if (provider === 'openrouter_audio') {
      _appendOpenRouterAudioUnderstandingPicker(
        wh.openrouter_audio_model || src.openrouter_audio_model || '');
      _appendField('Default question',
        _textInput('whisper.openrouter_audio_question',
                   wh.openrouter_audio_question || src.openrouter_audio_question
                     || 'Transcribe this audio verbatim. Return only the transcript.',
                   'what to ask the model about the uploaded audio'));
      _appendNote(
        'Audio-understanding models accept audio + a text question and return a text answer. '
        + 'They can transcribe, summarize, translate, identify speakers, or answer questions '
        + 'about content. The "Default question" field controls what gets asked when audio '
        + 'is uploaded. Change it to e.g. "Summarize the key points." for podcasts.'
      );
    }
  }

  function _appendOpenRouterAudioUnderstandingPicker(currentModelId) {
    var row = document.createElement('div');
    row.className = 'ora-settings-row';
    var labelEl = document.createElement('label');
    labelEl.className = 'ora-settings-row-label';
    labelEl.textContent = 'OpenRouter audio model';
    row.appendChild(labelEl);
    var sel = document.createElement('select');
    sel.className = 'ora-settings-row-input';
    sel.dataset.key = 'whisper.openrouter_audio_model';
    sel.innerHTML = '<option value="">Loading catalog…</option>';
    sel.addEventListener('change', function (e) {
      _setDirty('whisper.openrouter_audio_model', e.target.value);
    });
    row.appendChild(sel);
    _tabContentEl.appendChild(row);

    fetch('/config/openrouter/catalog')
      .then(function (r) { return r.json(); })
      .then(function (catalog) {
        var ids = (catalog && catalog.by_modality && catalog.by_modality.audio) || [];
        var lookup = {};
        (catalog.models || []).forEach(function (m) { lookup[m.id] = m; });
        if (!ids.length) {
          sel.innerHTML = '<option value="">No audio-understanding models in catalog</option>';
          return;
        }
        var options = ['<option value="">(pick a model)</option>'];
        ids.forEach(function (id) {
          var m = lookup[id] || {};
          var p = m.pricing_per_million || {};
          var price = (p.prompt != null && p.completion != null)
                       ? ' — $' + p.prompt + '/$' + p.completion + '/M tokens'
                       : '';
          var sel_attr = (id === currentModelId) ? ' selected' : '';
          options.push('<option value="' + id + '"' + sel_attr + '>'
                       + (m.display_name || id) + price + '</option>');
        });
        sel.innerHTML = options.join('');
      })
      .catch(function () {
        sel.innerHTML = '<option value="">(catalog fetch failed)</option>';
      });
  }

  // Speech (TTS) tab — controls the speaker button on assistant
  // messages. Provider options:
  //   local_say   — macOS `say` (free, instant, no network)
  //   openrouter  — OpenRouter speech endpoint (paid; better voices)
  function _renderSpeechTab() {
    var sp  = (_dirty.speech || _settings.speech || {});
    var src = _settings.speech || {};
    var provider = sp.provider || src.provider || 'local_say';

    var providerSel = _selectInput('speech.provider', [
        { id: 'local_say',  label: 'macOS say (free, instant)' },
        { id: 'openrouter', label: 'OpenRouter (paid; better voices)' },
      ], provider);
    _appendField('Speech provider', providerSel);
    providerSel.addEventListener('change', function () { _renderTabContent(); });

    if (provider === 'local_say') {
      _appendSayVoicePicker(sp.local_voice || src.local_voice || 'Samantha');
      _appendNote(
        'The "say" binary ships with macOS. Voices are managed in '
        + 'System Settings → Accessibility → Spoken Content → System Voice. '
        + 'New voices download on first use.'
      );
    } else if (provider === 'openrouter') {
      _appendOpenRouterSpeechPicker(sp.openrouter_model || src.openrouter_model || '');
      _appendField('Voice (optional)',
        _textInput('speech.openrouter_voice',
                   sp.openrouter_voice || src.openrouter_voice || '',
                   'leave blank for the model default'));
      _appendNote(
        'OpenRouter forwards to whichever upstream the chosen model lives on. '
        + 'Some models honor a voice id ("alloy", "echo", "shimmer" for OpenAI; '
        + 'voice names for ElevenLabs). Leave blank if unsure.'
      );
    }
  }

  function _appendSayVoicePicker(currentVoice) {
    var row = document.createElement('div');
    row.className = 'ora-settings-row';
    var labelEl = document.createElement('label');
    labelEl.className = 'ora-settings-row-label';
    labelEl.textContent = 'Voice';
    row.appendChild(labelEl);
    var sel = document.createElement('select');
    sel.className = 'ora-settings-row-input';
    sel.dataset.key = 'speech.local_voice';
    sel.innerHTML = '<option value="">Loading voices…</option>';
    sel.addEventListener('change', function (e) {
      _setDirty('speech.local_voice', e.target.value);
    });
    row.appendChild(sel);
    _tabContentEl.appendChild(row);

    fetch('/api/tts/voices')
      .then(function (r) { return r.json(); })
      .then(function (resp) {
        var voices = (resp && resp.voices) || [];
        if (!voices.length) {
          sel.innerHTML = '<option value="">(no voices found)</option>';
          return;
        }
        var opts = voices.map(function (v) {
          var sel_attr = (v.name === currentVoice) ? ' selected' : '';
          var label = v.name + (v.language ? ' — ' + v.language : '');
          return '<option value="' + v.name + '"' + sel_attr + '>' + label + '</option>';
        });
        sel.innerHTML = opts.join('');
      })
      .catch(function () {
        sel.innerHTML = '<option value="">(voice list failed)</option>';
      });
  }

  function _appendOpenRouterSpeechPicker(currentModelId) {
    var row = document.createElement('div');
    row.className = 'ora-settings-row';
    var labelEl = document.createElement('label');
    labelEl.className = 'ora-settings-row-label';
    labelEl.textContent = 'OpenRouter speech model';
    row.appendChild(labelEl);
    var sel = document.createElement('select');
    sel.className = 'ora-settings-row-input';
    sel.dataset.key = 'speech.openrouter_model';
    sel.innerHTML = '<option value="">Loading catalog…</option>';
    sel.addEventListener('change', function (e) {
      _setDirty('speech.openrouter_model', e.target.value);
    });
    row.appendChild(sel);
    _tabContentEl.appendChild(row);

    fetch('/config/openrouter/catalog')
      .then(function (r) { return r.json(); })
      .then(function (catalog) {
        var ids = (catalog && catalog.by_modality && catalog.by_modality.speech) || [];
        var lookup = {};
        (catalog.models || []).forEach(function (m) { lookup[m.id] = m; });
        if (!ids.length) {
          sel.innerHTML = '<option value="">No speech models in catalog</option>';
          return;
        }
        var options = ['<option value="">(pick a model)</option>'];
        ids.forEach(function (id) {
          var m = lookup[id] || {};
          var p = m.pricing_per_million || {};
          var price = (p.prompt != null) ? ' — $' + p.prompt + '/M chars' : '';
          var sel_attr = (id === currentModelId) ? ' selected' : '';
          options.push('<option value="' + id + '"' + sel_attr + '>'
                       + (m.display_name || id) + price + '</option>');
        });
        sel.innerHTML = options.join('');
      })
      .catch(function () {
        sel.innerHTML = '<option value="">(catalog fetch failed)</option>';
      });
  }

  // Populate the OpenRouter transcription-model dropdown from the
  // cached catalog. Falls back to a single "(loading…)" option if the
  // catalog fetch fails or is empty.
  function _appendOpenRouterTranscriptionPicker(currentModelId) {
    var row = document.createElement('div');
    row.className = 'ora-settings-row';
    var labelEl = document.createElement('label');
    labelEl.className = 'ora-settings-row-label';
    labelEl.textContent = 'OpenRouter transcription model';
    row.appendChild(labelEl);
    var sel = document.createElement('select');
    sel.className = 'ora-settings-row-input';
    sel.dataset.key = 'whisper.openrouter_model';
    sel.innerHTML = '<option value="">Loading catalog…</option>';
    sel.addEventListener('change', function (e) {
      _setDirty('whisper.openrouter_model', e.target.value);
    });
    row.appendChild(sel);
    _tabContentEl.appendChild(row);

    fetch('/config/openrouter/catalog')
      .then(function (r) { return r.json(); })
      .then(function (catalog) {
        var ids = (catalog && catalog.by_modality && catalog.by_modality.transcription) || [];
        var lookup = {};
        (catalog.models || []).forEach(function (m) { lookup[m.id] = m; });
        if (!ids.length) {
          sel.innerHTML = '<option value="">No transcription models in catalog</option>';
          return;
        }
        var options = ['<option value="">(pick a model)</option>'];
        ids.forEach(function (id) {
          var m = lookup[id] || {};
          var p = m.pricing_per_million || {};
          var price = (p.prompt != null) ? ' — $' + p.prompt + '/M input' : '';
          var sel_attr = (id === currentModelId) ? ' selected' : '';
          options.push('<option value="' + id + '"' + sel_attr + '>'
                       + (m.display_name || id) + price + '</option>');
        });
        sel.innerHTML = options.join('');
      })
      .catch(function () {
        sel.innerHTML = '<option value="">(catalog fetch failed)</option>';
      });
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
      + 'shown back in the browser; if you need to update one, type a new '
      + 'value and click the Save button on that row.';
    _tabContentEl.appendChild(keysHint);

    _apiKeys.forEach(function (row) {
      _appendApiKeyRow(row);
    });

    // If a previous open({highlight:...}) call queued a row to
    // emphasize (e.g., from the open-settings event listener wired
    // below), apply it now that rows exist in the DOM.
    if (_pendingHighlight) {
      _applyApiKeyHighlight(_pendingHighlight);
      _pendingHighlight = null;
    }

    // ── Add new provider ───────────────────────────────────────────────
    // The user already has Framework — API Key Acquisition for end-to-end
    // provider setup (key elicitation, keychain storage, endpoint
    // registration). Rather than duplicate that flow inline, surface a
    // button that drops the slash-command into the input pane, closes the
    // settings modal, and lets the framework run as a normal interaction.
    var addWrap = document.createElement('div');
    addWrap.className = 'ora-settings-add-provider';
    var addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'ora-settings-btn ora-settings-btn--ghost';
    addBtn.textContent = '+ Add new provider';
    addBtn.title = 'Run Framework — API Key Acquisition to register a new provider';
    addBtn.addEventListener('click', function () {
      var input = document.querySelector('.input-pane textarea');
      if (!input) {
        _setStatus('Could not find the input pane', 'error');
        return;
      }
      input.value = '/framework api-key-setup';
      // Trigger an input event so any draft-tracking listeners pick up the
      // new value. The user reviews and presses Enter (or edits the prompt
      // first, e.g. to specify a particular provider as an argument).
      try {
        input.dispatchEvent(new Event('input', { bubbles: true }));
      } catch (_) { /* old browser fallback — ignore */ }
      close();
      try { input.focus(); } catch (_) { /* ignore */ }
    });
    addWrap.appendChild(addBtn);
    var addHint = document.createElement('span');
    addHint.className = 'ora-settings-note';
    addHint.style.marginLeft = '10px';
    addHint.textContent =
      'Drops /framework api-key-setup into the input. Review and press Enter to start.';
    addWrap.appendChild(addHint);
    _tabContentEl.appendChild(addWrap);
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
    // Tag with the provider id so `open({highlight: <id>})` can find
    // the row to scroll-into-view + flash. Used by the `open-settings`
    // CustomEvent listener wired at module load (deferrals row 52).
    if (row.provider) wrap.dataset.provider = row.provider;

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

  // ── dirty tracking + autosave ────────────────────────────────────────────

  var _autosaveTimer = null;
  var AUTOSAVE_DELAY_MS = 600;

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
    // Debounced autosave. All inputs end up here on commit (selects /
    // checkboxes fire 'change' immediately; text/number inputs fire 'change'
    // on blur). The 600ms delay is a no-op for those events but coalesces
    // multi-field bursts (e.g. user changes 3 selects in a row → one POST).
    if (_autosaveTimer) clearTimeout(_autosaveTimer);
    _autosaveTimer = setTimeout(function () {
      _autosaveTimer = null;
      _onSave();
    }, AUTOSAVE_DELAY_MS);
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

  // _onSave is now driven by autosave (debounced from _setDirty); no manual
  // Save button. Silent no-op when nothing's dirty so a stray click or
  // timer race doesn't paint "Nothing to save."
  function _onSave() {
    if (!_settings) return;
    if (!Object.keys(_dirty).length) return;
    _setStatus('Saving…');
    var pending = _dirty;
    _dirty = {};
    fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ updates: pending }),
    })
      .then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, data: j }; });
      })
      .then(function (res) {
        if (!res.ok) {
          throw new Error((res.data && res.data.error) || 'save failed');
        }
        _settings = res.data.settings || _settings;
        _setStatus('Saved ✓', 'success');
        setTimeout(function () { _setStatus(''); }, 1400);
        // Broadcast so live UI helpers (tooltip toggle, etc.) can
        // react without a page reload.
        try {
          document.dispatchEvent(new CustomEvent('ora:settings-saved',
            { detail: _settings }));
        } catch (_) { /* old browser fallback — ignore */ }
      })
      .catch(function (err) {
        // Restore the dirty payload so the next change triggers a retry.
        Object.keys(pending).forEach(function (k) { _dirty[k] = pending[k]; });
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

  // Provider ids the rendered API-key rows tag themselves with.
  // Substring-matched against `open-settings` event detail
  // (fix_path + message) to extract a provider to highlight. Order
  // matters only for tie-breaks: longer / more specific names first,
  // so "tensorart" wins before "anthropic" (no actual overlap today,
  // but defensive).
  var KNOWN_PROVIDERS = [
    'anthropic', 'openai', 'gemini', 'stability', 'replicate',
    'civitai', 'tensorart', 'assemblyai', 'deepgram', 'elevenlabs',
  ];

  // Queued row id to highlight after the next _renderAPIsTab pass.
  // Set by open({highlight: ...}); consumed + cleared by the
  // _renderAPIsTab body when rows render.
  var _pendingHighlight = null;

  function open(opts) {
    opts = opts || {};
    if (!_backdropEl) _build();
    if (!_backdropEl.parentNode) document.body.appendChild(_backdropEl);
    _backdropEl.classList.add('ora-settings-backdrop--visible');
    // Optional tab switch — caller passes a TABS entry id
    // ('models', 'interface', 'capture', 'whisper', 'apis', 'export').
    // Unknown tab ids are silently ignored (defensive against future
    // tab additions / removals).
    if (opts.tab && _isValidTabId(opts.tab)) {
      _activeTab = opts.tab;
      // _renderTabs reflects the new active tab in the tab strip;
      // _renderTabContent is called by _fetchState below for the
      // models tab and runs synchronously for the others.
      if (_tabsEl) _renderTabs();
    }
    if (opts.highlight) {
      _pendingHighlight = String(opts.highlight).toLowerCase();
    }
    _fetchState();
    document.addEventListener('keydown', _onKeydown);
  }

  function _isValidTabId(id) {
    for (var i = 0; i < TABS.length; i++) {
      if (TABS[i].id === id) return true;
    }
    return false;
  }

  // Find the API-key row tagged with data-provider=<id> and apply a
  // brief highlight + scroll it into view. Called from _renderAPIsTab
  // after rows are appended. No-op when the row doesn't exist (the
  // requested provider isn't in the API-keys list, or the DOM hasn't
  // built yet — the caller's responsibility is to set
  // _pendingHighlight before rendering happens, not to time the call).
  function _applyApiKeyHighlight(providerId) {
    if (!providerId || !_tabContentEl) return;
    var row = _tabContentEl.querySelector(
      '.ora-settings-apikey-row[data-provider="' + providerId + '"]'
    );
    if (!row) return;
    row.classList.add('ora-settings-apikey-row--highlight');
    try {
      row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } catch (_) {
      // Older browsers without smooth-scroll options: ignore.
    }
    // Auto-clear the highlight class after the animation completes so
    // the next render starts from a clean slate.
    setTimeout(function () {
      row.classList.remove('ora-settings-apikey-row--highlight');
    }, 3000);
  }

  // Heuristic provider extraction from a fix-path / error-message
  // pair. Used when an `open-settings` CustomEvent doesn't carry an
  // explicit provider id. Walks KNOWN_PROVIDERS in order, returns the
  // first substring hit. Returns null when no known provider name
  // appears in either string — the listener then opens the External
  // APIs tab with no highlight, and the user finds the row manually.
  function _extractProviderFromHint(fixPath, message) {
    var corpus = (String(fixPath || '') + ' ' + String(message || '')).toLowerCase();
    for (var i = 0; i < KNOWN_PROVIDERS.length; i++) {
      if (corpus.indexOf(KNOWN_PROVIDERS[i]) !== -1) {
        return KNOWN_PROVIDERS[i];
      }
    }
    return null;
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

  // ── open-settings event handler (deferrals row 52) ───────────────────────
  //
  // `capability-invocation-ui.js` emits an `open-settings` CustomEvent
  // on the host element when a user clicks a "Configure a model …"
  // fix-path button in a slot-error popover. The event bubbles to
  // document — this listener catches it, opens the Settings modal on
  // the External APIs tab, and (when a provider name can be extracted
  // from the event detail) flashes that provider's row.
  //
  // The destination tab id is hard-coded to 'apis' for "Configure a"
  // fix paths because the emitter (capability-invocation-ui.js:840)
  // already gates on FIX_PATH_CONFIGURE_PREFIX — only API-key
  // configuration errors reach this listener. Other fix-paths
  // (`activate-mask-tool`, `retry`) fire different events.
  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('open-settings', function (e) {
      var detail = (e && e.detail) || {};
      // Caller can pass an explicit provider via detail.provider;
      // otherwise we substring-match KNOWN_PROVIDERS against the
      // human-readable fix_path + message strings.
      var providerHint = detail.provider
        || _extractProviderFromHint(detail.fix_path, detail.message);
      open({ tab: 'apis', highlight: providerHint || null });
    });
  }

  root.OraSettingsPanel = {
    init: init,
    open: open,
    close: close,
    toggle: toggle,
    getState: getState,
    // Exposed for tests + for future programmatic callers that want
    // to drive the highlight without going through the event.
    _extractProviderFromHint: _extractProviderFromHint,
  };
})(typeof window !== 'undefined' ? window : this);
