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
  var _retrieval = null;
  var _apiKeys = [];
  var _providerGroups = [];   // [[category, group label], …] render order
  var _dirty = {};       // pending changes, applied on Save
  var _recordingShortcutId = null;
  var _recordingShortcutButton = null;
  var _globalShortcutHandlerInstalled = false;

  // Tabs declared in display order. The Buckets tab was retired with
  // install Chunk 10 step 2 — the bucket abstraction has been dissolved
  // by the configuration architecture (Premium / Optimum / Budget /
  // Free + named customs replace bucket-based slot assignment). The
  // Models tab hosts OraModelsPane (server/static/models-pane.js); the
  // Visual tab hosts OraVisualSlotsPane (server/static/visual-slots-pane.js)
  // — the classic ConfigPanel embed was retired with install Chunk 11.
  // Only "Project Plugins" (the developer plugin/extension registry — register
  // a folder with an ora-project.json, NOT the sidebar's "+ New project"
  // workspace feature) is grouped at the end behind an "Advanced" divider so a
  // typical user isn't confronted with it. Everything else — including External
  // APIs, which every user sets up on install — stays in the main list.
  var TABS = [
    { id: 'models',    label: 'Models' },
    { id: 'visual',    label: 'Visual' },
    { id: 'styles',    label: 'Output Styles' },
    { id: 'avmedia',   label: 'Audio & Video' },
    { id: 'general',   label: 'General' },
    { id: 'shortcuts', label: 'Shortcuts' },
    { id: 'apis',      label: 'External APIs' },
    { id: 'projects',  label: 'Project Plugins', group: 'advanced' },
  ];

  // 2026-07-01 consolidation: six low-traffic tabs became sections on
  // two pages — Audio & Video (Transcription · Speech · Screen
  // recording · Media export) and General (Retrieval · Interface).
  // Old tab ids stay routable so open({tab}) callers and open-settings
  // deep links keep working; the alias also targets the section anchor.
  var TAB_ALIASES = {
    transcription: { tab: 'avmedia', section: 'transcription' },
    speech:        { tab: 'avmedia', section: 'speech' },
    capture:       { tab: 'avmedia', section: 'capture' },
    export:        { tab: 'avmedia', section: 'export' },
    whisper:       { tab: 'avmedia', section: 'transcription' },  // pre-rename id
    retrieval:     { tab: 'general', section: 'retrieval' },
    interface:     { tab: 'general', section: 'interface' },
  };

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
    var advancedDividerDrawn = false;
    TABS.forEach(function (t) {
      if (t.group === 'advanced' && !advancedDividerDrawn) {
        advancedDividerDrawn = true;
        var sep = document.createElement('span');
        sep.className = 'ora-settings-tab-divider';
        sep.setAttribute('aria-hidden', 'true');
        sep.textContent = 'Advanced';
        _tabsEl.appendChild(sep);
      }
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
    // The Models tab hosts OraModelsPane (install Chunk 10); the Visual
    // tab hosts OraVisualSlotsPane (install Chunk 11). Buckets was
    // retired (see the TABS comment above).
    if (_activeTab === 'models')  { _renderModelsPane();      return; }
    if (_activeTab === 'visual')  { _renderVisualSlotsPane(); return; }
    if (_activeTab === 'projects') { _renderProjectsTab();    return; }
    if (_activeTab === 'styles')  { _renderStylesPane();     return; }
    if (!_settings) {
      _tabContentEl.textContent = 'Loading…';
      return;
    }
    if (_activeTab === 'avmedia') _renderAVMediaTab();
    else if (_activeTab === 'general') _renderGeneralTab();
    else if (_activeTab === 'shortcuts') _renderShortcutsTab();
    else if (_activeTab === 'apis') _renderAPIsTab();
  }

  // ── consolidated tabs (2026-07-01): sections in a two-column grid ────────
  //
  // Each former tab renders as a titled section. The legacy render
  // functions append to the module-level _tabContentEl, so _withTarget
  // swaps it to the section body for the synchronous render pass and
  // restores it after. (Async work inside those functions only mutates
  // elements it already appended, so the swap-window is safe; the one
  // exception was the Retrieval pane, which re-entered _tabContentEl
  // from a fetch callback — it now renders into an explicit container.)

  function _withTarget(el, fn) {
    var saved = _tabContentEl;
    _tabContentEl = el;
    try { fn(); } finally { _tabContentEl = saved; }
  }

  function _sectionInto(grid, id, title, intro) {
    var sec = document.createElement('section');
    sec.className = 'ora-settings-group';
    sec.dataset.settingsSection = id;
    var h = document.createElement('h3');
    h.className = 'ora-settings-group-title';
    h.textContent = title;
    sec.appendChild(h);
    if (intro) {
      var p = document.createElement('p');
      p.className = 'ora-settings-note ora-settings-group-intro';
      p.textContent = intro;
      sec.appendChild(p);
    }
    var body = document.createElement('div');
    body.className = 'ora-settings-group-body';
    sec.appendChild(body);
    grid.appendChild(sec);
    return body;
  }

  function _renderAVMediaTab() {
    var grid = document.createElement('div');
    grid.className = 'ora-settings-sections-grid';
    _tabContentEl.appendChild(grid);

    _withTarget(
      _sectionInto(grid, 'transcription', 'Transcription',
        'Audio in → text out: how uploaded (or recorded) audio becomes '
        + 'transcripts.'),
      _renderTranscriptionTab);
    _renderSpeechSection(
      _sectionInto(grid, 'speech', 'Speech',
        'Text out → audio: the Read-aloud speaker button on scratchpad '
        + 'answers uses this voice.'));
    _renderCaptureSection(
      _sectionInto(grid, 'capture', 'Screen recording',
        'Records your screen as video, with optional microphone audio '
        + 'and a webcam picture-in-picture. Start and stop it from the '
        + 'camera button on the spine — these are the defaults it uses.'));
    _withTarget(
      _sectionInto(grid, 'export', 'Media export',
        'Video and audio renders of the timeline (MP4 · MOV · WebM · '
        + 'M4A).'),
      _renderExportTab);

    _scrollToPendingSection();
  }

  function _renderGeneralTab() {
    var grid = document.createElement('div');
    grid.className = 'ora-settings-sections-grid';
    _tabContentEl.appendChild(grid);

    _renderRetrievalSection(
      _sectionInto(grid, 'retrieval', 'Retrieval (memory search)',
        'How Ora\'s memory is encoded and searched. These two choices '
        + 'shape what context every answer retrieves — they matter more '
        + 'than they look.'));
    _withTarget(
      _sectionInto(grid, 'interface', 'Interface',
        'Small interface preferences.'),
      _renderInterfaceTab);

    _scrollToPendingSection();
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

    var visualHelp = iface.visual_help_enabled !== undefined
      ? iface.visual_help_enabled
      : (src.visual_help_enabled === true);
    _appendField('Show visual pane help button',
      _checkboxInput('interface.visual_help_enabled', visualHelp));
    _appendNote(
      'When on, a small help button appears inside the visual pane and opens '
      + 'the specialty toolbar menu. Leave it off for the uncluttered canvas.'
    );

    var resetBtn = document.createElement('button');
    resetBtn.type = 'button';
    resetBtn.className = 'ora-settings-btn';
    resetBtn.textContent = 'Reset toolbar layout';
    resetBtn.addEventListener('click', function () {
      var Packs = window.OraV3PackToolbars;
      if (!Packs || typeof Packs.resetLayout !== 'function') {
        _setStatus('Visual toolbar reset is not available yet.', 'error');
        return;
      }
      var panel = null;
      try {
        if (window.OraPanels && window.OraPanels.visual
            && typeof window.OraPanels.visual._getActive === 'function') {
          panel = window.OraPanels.visual._getActive();
        } else if (window.OraCanvas && window.OraCanvas.panel) {
          panel = window.OraCanvas.panel;
        }
      } catch (_) { panel = null; }
      Packs.resetLayout(panel);
      _setStatus('Visual toolbar layout reset.', 'success');
      setTimeout(function () { _setStatus(''); }, 1400);
    });
    _appendField('Visual toolbar layout', resetBtn);
  }

  // ── Shortcuts tab ────────────────────────────────────────────────────────

  function _keyboardShortcuts() {
    return (typeof window !== 'undefined' && window.OraKeyboardShortcuts) || null;
  }

  function _renderShortcutsTab() {
    var K = _keyboardShortcuts();
    if (!K) {
      _tabContentEl.textContent =
        'keyboard-shortcuts.js is not loaded. Reload the page or check the network tab.';
      return;
    }
    K.refresh(_settings || {});
    var audit = K.audit(_settings || {});

    var wrap = document.createElement('div');
    wrap.className = 'ora-shortcuts-panel';

    var summary = document.createElement('div');
    summary.className = 'ora-shortcuts-summary';
    summary.innerHTML = ''
      + '<div><strong>' + audit.total + '</strong><span>Total bindings</span></div>'
      + '<div><strong>' + audit.editable + '</strong><span>Remappable</span></div>'
      + '<div><strong>' + audit.fixed + '</strong><span>Fixed access keys</span></div>'
      + '<div class="' + (audit.errors ? 'is-error' : '') + '"><strong>'
      + audit.errors + '</strong><span>Blocking conflicts</span></div>'
      + '<div class="' + (audit.warnings ? 'is-warn' : '') + '"><strong>'
      + audit.warnings + '</strong><span>Warnings</span></div>';
    wrap.appendChild(summary);

    var controls = document.createElement('div');
    controls.className = 'ora-shortcuts-controls';
    var search = document.createElement('input');
    search.type = 'search';
    search.className = 'ora-settings-input ora-shortcuts-search';
    search.placeholder = 'Search shortcuts';
    controls.appendChild(search);
    var resetAll = document.createElement('button');
    resetAll.type = 'button';
    resetAll.className = 'ora-settings-btn ora-settings-btn--ghost';
    resetAll.textContent = 'Reset all';
    resetAll.addEventListener('click', function () {
      if (!confirm('Reset every remappable shortcut to its default?')) return;
      audit.rows.forEach(function (row) {
        if (!row.editable) return;
        _setShortcutOverride(row.id, null, false);
      });
      _renderShortcutsTab();
      _setStatus('Shortcut defaults restored.', 'success');
    });
    controls.appendChild(resetAll);
    wrap.appendChild(controls);

    var list = document.createElement('div');
    list.className = 'ora-shortcuts-list';
    wrap.appendChild(list);

    function renderRows() {
      var q = (search.value || '').trim().toLowerCase();
      list.innerHTML = '';
      var groups = {};
      audit.rows.forEach(function (row) {
        var corpus = [
          row.category, row.label, row.description, row.context,
          row.currentDisplay, row.defaultDisplay
        ].join(' ').toLowerCase();
        if (q && corpus.indexOf(q) === -1) return;
        if (!groups[row.category]) groups[row.category] = [];
        groups[row.category].push(row);
      });
      Object.keys(groups).forEach(function (category) {
        var h = document.createElement('div');
        h.className = 'ora-shortcuts-category';
        h.textContent = category;
        list.appendChild(h);
        groups[category].forEach(function (row) {
          list.appendChild(_shortcutRow(row));
        });
      });
      if (!list.childNodes.length) {
        var empty = document.createElement('p');
        empty.className = 'ora-settings-note';
        empty.textContent = 'No shortcuts match that search.';
        list.appendChild(empty);
      }
    }
    search.addEventListener('input', renderRows);
    renderRows();

    var docs = document.createElement('details');
    docs.className = 'ora-shortcuts-docs';
    docs.innerHTML = ''
      + '<summary>Built-in shortcut documentation</summary>'
      + '<p>Ora now treats shortcuts as runtime settings. Command bindings are remappable; '
      + 'accessibility and text-entry keys stay fixed so ordinary typing, focus movement, '
      + 'and modal dismissal remain predictable.</p>'
      + '<p>Conflict checking blocks overlapping Ora commands and high-risk browser or '
      + 'system shortcuts. Lower-risk browser collisions are shown as warnings because '
      + 'some contextual commands, such as canvas save, intentionally behave like desktop '
      + 'application shortcuts when the canvas is focused.</p>';
    wrap.appendChild(docs);

    var fixed = document.createElement('details');
    fixed.className = 'ora-shortcuts-docs';
    fixed.innerHTML = '<summary>Fixed keyboard behavior</summary>';
    var fixedList = document.createElement('div');
    fixedList.className = 'ora-shortcuts-reserved-list';
    audit.rows.filter(function (row) { return !row.editable; }).forEach(function (row) {
      fixedList.appendChild(_shortcutStaticRow(row.currentDisplay, row.label, row.context));
    });
    fixed.appendChild(fixedList);
    wrap.appendChild(fixed);

    var reserved = document.createElement('details');
    reserved.className = 'ora-shortcuts-docs';
    reserved.innerHTML = '<summary>System and browser shortcuts to avoid</summary>';
    var reservedList = document.createElement('div');
    reservedList.className = 'ora-shortcuts-reserved-list';
    K.reserved().forEach(function (row) {
      var item = _shortcutStaticRow(
        row.display,
        row.label,
        row.source + (row.severity === 'block' ? ' - blocked' : ' - warning')
      );
      if (row.severity === 'block') item.classList.add('is-error');
      else item.classList.add('is-warn');
      reservedList.appendChild(item);
    });
    reserved.appendChild(reservedList);
    wrap.appendChild(reserved);

    _tabContentEl.innerHTML = '';
    _tabContentEl.appendChild(wrap);
  }

  function _shortcutRow(row) {
    var r = document.createElement('div');
    r.className = 'ora-shortcuts-row'
      + (row.errors.length ? ' is-error' : '')
      + (!row.errors.length && row.warnings.length ? ' is-warn' : '');
    r.title = row.description;
    var meta = document.createElement('div');
    meta.className = 'ora-shortcuts-row-meta';
    var title = document.createElement('div');
    title.className = 'ora-shortcuts-row-title';
    title.textContent = row.label;
    var desc = document.createElement('div');
    desc.className = 'ora-shortcuts-row-desc';
    desc.textContent = row.description;
    var ctx = document.createElement('div');
    ctx.className = 'ora-shortcuts-row-context';
    ctx.textContent = row.context;
    meta.appendChild(title);
    meta.appendChild(desc);
    meta.appendChild(ctx);
    r.appendChild(meta);

    var binding = document.createElement('div');
    binding.className = 'ora-shortcuts-binding';
    var kbd = document.createElement('kbd');
    kbd.textContent = row.currentDisplay;
    binding.appendChild(kbd);
    var def = document.createElement('span');
    def.className = 'ora-shortcuts-default';
    if (row.currentDisplay === row.defaultDisplay) {
      def.className += ' ora-shortcuts-default--same';
    }
    def.textContent = 'Default: ' + row.defaultDisplay;
    binding.appendChild(def);
    r.appendChild(binding);

    var actions = document.createElement('div');
    actions.className = 'ora-shortcuts-actions';
    if (row.editable) {
      var record = document.createElement('button');
      record.type = 'button';
      record.className = 'ora-settings-btn ora-settings-btn--small';
      record.textContent = 'Record';
      record.addEventListener('click', function () {
        _beginShortcutRecord(row.id, record);
      });
      actions.appendChild(record);

      var reset = document.createElement('button');
      reset.type = 'button';
      reset.className = 'ora-settings-btn ora-settings-btn--small ora-settings-btn--ghost';
      reset.textContent = 'Reset';
      reset.addEventListener('click', function () {
        _setShortcutOverride(row.id, null, true);
      });
      actions.appendChild(reset);
    } else {
      var fixed = document.createElement('span');
      fixed.className = 'ora-shortcuts-fixed';
      fixed.textContent = 'Fixed';
      actions.appendChild(fixed);
    }
    r.appendChild(actions);

    if (row.errors.length || row.warnings.length) {
      var issues = document.createElement('div');
      issues.className = 'ora-shortcuts-issues';
      row.errors.concat(row.warnings).forEach(function (msg) {
        var line = document.createElement('div');
        line.textContent = msg;
        issues.appendChild(line);
      });
      r.appendChild(issues);
    }
    return r;
  }

  function _shortcutStaticRow(keys, label, note) {
    var row = document.createElement('div');
    row.className = 'ora-shortcuts-static-row';
    var k = document.createElement('kbd');
    k.textContent = keys;
    row.appendChild(k);
    var body = document.createElement('span');
    body.textContent = label + (note ? ' - ' + note : '');
    row.appendChild(body);
    return row;
  }

  function _beginShortcutRecord(id, btn) {
    _endShortcutRecord();
    _recordingShortcutId = id;
    _recordingShortcutButton = btn;
    btn.textContent = 'Press keys...';
    btn.classList.add('is-recording');
    _setStatus('Press the new shortcut. Escape cancels recording.');
    document.addEventListener('keydown', _captureShortcutKey, true);
  }

  function _endShortcutRecord() {
    document.removeEventListener('keydown', _captureShortcutKey, true);
    if (_recordingShortcutButton) {
      _recordingShortcutButton.textContent = 'Record';
      _recordingShortcutButton.classList.remove('is-recording');
    }
    _recordingShortcutId = null;
    _recordingShortcutButton = null;
  }

  function _captureShortcutKey(e) {
    var K = _keyboardShortcuts();
    if (!_recordingShortcutId || !K) return;
    var shortcut = K.eventToShortcut(e);
    if (!shortcut) return;
    e.preventDefault();
    e.stopPropagation();
    if (shortcut === 'Escape') {
      _endShortcutRecord();
      _setStatus('Shortcut recording cancelled.');
      return;
    }
    var result = K.validateShortcut(_recordingShortcutId, shortcut, _settings || {});
    if (!result.ok) {
      _endShortcutRecord();
      _setStatus('Shortcut not saved: ' + result.errors.join(' '), 'error');
      return;
    }
    _setShortcutOverride(_recordingShortcutId, result.normalized, true);
    if (result.warnings.length) {
      _setStatus('Saved with warning: ' + result.warnings.join(' '), 'warn');
    }
    _endShortcutRecord();
  }

  function _setShortcutOverride(id, value, rerender) {
    if (!_settings) _settings = {};
    if (!_settings.keyboard || typeof _settings.keyboard !== 'object') {
      _settings.keyboard = {};
    }
    if (!_settings.keyboard.shortcuts || typeof _settings.keyboard.shortcuts !== 'object') {
      _settings.keyboard.shortcuts = {};
    }
    _settings.keyboard.shortcuts[id] = value;
    var K = _keyboardShortcuts();
    if (K) K.refresh(_settings);
    _setDirty('keyboard.shortcuts.' + id, value);
    if (rerender) {
      _renderShortcutsTab();
      _setStatus(value ? 'Shortcut saved.' : 'Shortcut reset to default.', 'success');
    }
  }

  // ── Models tab ───────────────────────────────────────────────────────────
  // The Models tab hosts OraModelsPane (server/static/models-pane.js),
  // a configuration-driven picker that replaces the classic ConfigPanel
  // embed (install Chunk 10). The pane fetches /api/model-registry and
  // /api/model-registry/picks on mount and renders preset cards, a
  // custom-new + previous grid, the vendor-organized inventory, and a
  // local-hardware section.

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

  // ── Output Styles tab ──────────────────────────────────────────────────
  // Hosts OraStylesPane (server/static/styles-pane.js): lists the built-in
  // Output Style profiles and sets the account-wide default style.
  function _renderStylesPane() {
    if (typeof OraStylesPane === 'undefined') {
      _tabContentEl.textContent =
        'styles-pane.js is not loaded. Reload the page or check the network tab.';
      return;
    }
    _tabContentEl.innerHTML = '';
    var host = document.createElement('div');
    host.className = 'ora-settings-styles-host';
    _tabContentEl.appendChild(host);
    try {
      OraStylesPane.init(host);
    } catch (err) {
      host.textContent = 'Could not load Output Styles: '
        + ((err && err.message) || 'unknown error');
    }
  }

  // ── Visual tab ───────────────────────────────────────────────────────────
  // The Visual tab hosts OraVisualSlotsPane (server/static/
  // visual-slots-pane.js), a compact editor for the routing-config
  // slots block (install Chunk 11). It replaces the classic ConfigPanel
  // ten-slot grid: image_generates + video_generates as first-class
  // selectors, everything else under a collapsed Advanced disclosure.
  // Mounted fresh on each tab open so the user always sees the current
  // routing state.

  function _renderVisualSlotsPane() {
    if (typeof OraVisualSlotsPane === 'undefined') {
      _tabContentEl.textContent =
        'visual-slots-pane.js is not loaded. Reload the page or check the network tab.';
      return;
    }
    _tabContentEl.innerHTML = '';
    var host = document.createElement('div');
    host.className = 'ora-settings-visual-host';
    _tabContentEl.appendChild(host);
    try {
      OraVisualSlotsPane.init(host);
    } catch (err) {
      host.textContent = 'Could not load visual routing: '
        + ((err && err.message) || 'unknown error');
    }
  }

  // ── Projects tab ────────────────────────────────────────────────────────
  // Project plugins are discovered by project_registry through pointer files
  // in ~/ora/data/projects/. The tab is a management surface over that
  // existing runtime registry; it does not copy project files into Ora.

  function _renderProjectsTab() {
    _tabContentEl.innerHTML = '';

    var pane = document.createElement('div');
    pane.className = 'ora-settings-projects';
    _tabContentEl.appendChild(pane);

    // Disambiguate from the sidebar's "+ New project" workspace feature — this
    // is the developer plugin/extension registry.
    var explain = document.createElement('div');
    explain.className = 'ora-settings-projects-explainer';
    explain.innerHTML =
      '<strong>Project plugins</strong> extend Ora with a folder\'s custom tools, '
      + 'slash commands, and configs (a repo containing an <code>ora-project.json</code> '
      + 'manifest). Register the folder path below to load them.<br>'
      + 'Looking to organize your conversations and files instead? Use '
      + '<strong>+ New project</strong> in the sidebar — that\'s a separate feature.';
    pane.appendChild(explain);

    var toolbar = document.createElement('div');
    toolbar.className = 'ora-settings-projects-toolbar';
    pane.appendChild(toolbar);

    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'ora-settings-projects-path';
    input.placeholder = '~/path/to/project';
    toolbar.appendChild(input);

    var registerBtn = document.createElement('button');
    registerBtn.type = 'button';
    registerBtn.className = 'ora-settings-btn ora-settings-btn--primary';
    registerBtn.textContent = 'Register';
    toolbar.appendChild(registerBtn);

    var refreshBtn = document.createElement('button');
    refreshBtn.type = 'button';
    refreshBtn.className = 'ora-settings-btn';
    refreshBtn.textContent = 'Refresh';
    toolbar.appendChild(refreshBtn);

    var status = document.createElement('div');
    status.className = 'ora-settings-projects-status';
    pane.appendChild(status);

    var list = document.createElement('div');
    list.className = 'ora-settings-projects-list';
    pane.appendChild(list);

    function setLocalStatus(text, kind) {
      status.textContent = text || '';
      status.className = 'ora-settings-projects-status'
        + (kind ? ' ora-settings-projects-status--' + kind : '');
    }

    function refreshProjects() {
      list.textContent = 'Loading...';
      setLocalStatus('');
      return fetch('/api/projects')
        .then(function (r) { return r.json().then(function (data) {
          return { ok: r.ok, data: data };
        }); })
        .then(function (res) {
          if (!res.ok || !res.data || res.data.ok === false) {
            throw new Error((res.data && res.data.error) || 'Project list failed');
          }
          renderProjectList(list, res.data.projects || [], setLocalStatus, refreshProjects);
        })
        .catch(function (err) {
          list.innerHTML = '';
          setLocalStatus(err.message || String(err), 'error');
        });
    }

    registerBtn.addEventListener('click', function () {
      var root = (input.value || '').trim();
      if (!root) {
        setLocalStatus('Enter a project root path.', 'error');
        return;
      }
      registerBtn.disabled = true;
      setLocalStatus('Registering...');
      fetch('/api/projects/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ root: root }),
      })
        .then(function (r) { return r.json().then(function (data) {
          return { ok: r.ok, data: data };
        }); })
        .then(function (res) {
          if (!res.ok || !res.data || res.data.ok === false) {
            throw new Error((res.data && res.data.error) || 'Registration failed');
          }
          input.value = '';
          setLocalStatus('Project registered.', 'success');
          return refreshProjects();
        })
        .catch(function (err) {
          setLocalStatus(err.message || String(err), 'error');
        })
        .finally(function () {
          registerBtn.disabled = false;
        });
    });

    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        registerBtn.click();
      }
    });
    refreshBtn.addEventListener('click', refreshProjects);
    refreshProjects();
  }

  function renderProjectList(container, projects, setLocalStatus, refreshProjects) {
    container.innerHTML = '';
    if (!projects.length) {
      var empty = document.createElement('div');
      empty.className = 'ora-settings-projects-empty';
      empty.textContent = 'No projects registered.';
      container.appendChild(empty);
      return;
    }
    projects.forEach(function (project) {
      container.appendChild(buildProjectCard(project, setLocalStatus, refreshProjects));
    });
  }

  function buildProjectCard(project, setLocalStatus, refreshProjects) {
    var card = document.createElement('section');
    card.className = 'ora-settings-project-card';

    var head = document.createElement('div');
    head.className = 'ora-settings-project-head';
    card.appendChild(head);

    var titleWrap = document.createElement('div');
    titleWrap.className = 'ora-settings-project-title-wrap';
    head.appendChild(titleWrap);

    var title = document.createElement('h3');
    title.className = 'ora-settings-project-title';
    title.textContent = project.name || project.nexus || 'Project';
    titleWrap.appendChild(title);

    var meta = document.createElement('div');
    meta.className = 'ora-settings-project-meta';
    meta.textContent = (project.nexus || '') + (project.version ? ' · v' + project.version : '');
    titleWrap.appendChild(meta);

    var unregisterBtn = document.createElement('button');
    unregisterBtn.type = 'button';
    unregisterBtn.className = 'ora-settings-btn ora-settings-btn--small ora-settings-btn--danger';
    unregisterBtn.textContent = 'Unregister';
    unregisterBtn.addEventListener('click', function () {
      if (!window.confirm('Unregister "' + (project.name || project.nexus) + '" from Ora?')) return;
      unregisterBtn.disabled = true;
      fetch('/api/projects/' + encodeURIComponent(project.nexus) + '/unregister', {
        method: 'POST',
      })
        .then(function (r) { return r.json().then(function (data) {
          return { ok: r.ok, data: data };
        }); })
        .then(function (res) {
          if (!res.ok || !res.data || res.data.ok === false) {
            throw new Error((res.data && res.data.error) || 'Unregister failed');
          }
          setLocalStatus('Project unregistered.', 'success');
          return refreshProjects();
        })
        .catch(function (err) {
          setLocalStatus(err.message || String(err), 'error');
        })
        .finally(function () {
          unregisterBtn.disabled = false;
        });
    });
    head.appendChild(unregisterBtn);

    if (project.description) {
      var desc = document.createElement('p');
      desc.className = 'ora-settings-project-desc';
      desc.textContent = project.description;
      card.appendChild(desc);
    }

    var root = document.createElement('div');
    root.className = 'ora-settings-project-root';
    root.textContent = project.root || '';
    card.appendChild(root);

    var chips = document.createElement('div');
    chips.className = 'ora-settings-project-chips';
    var counts = project.counts || {};
    [
      ['Tools', counts.tools],
      ['Commands', counts.slash_commands],
      ['Frameworks', counts.frameworks],
      ['PEDs', counts.peds],
      ['Workflows', counts.workflow_specs],
      ['Capabilities', counts.capability_slots],
      ['Themes', counts.themes],
      ['Configs', counts.framework_configurations],
    ].forEach(function (pair) {
      if (!pair[1]) return;
      var chip = document.createElement('span');
      chip.className = 'ora-settings-project-chip';
      chip.textContent = pair[0] + ': ' + pair[1];
      chips.appendChild(chip);
    });
    card.appendChild(chips);

    appendProjectDetailGroup(card, 'Slash commands',
      (project.slash_commands || []).map(function (c) {
        return (c.command || '/' + c.name) + (c.description ? ' - ' + c.description : '');
      }));
    appendProjectDetailGroup(card, 'Tools',
      (project.tools || []).map(function (t) {
        return t.name + (t.description ? ' - ' + t.description : '');
      }));
    appendProjectDetailGroup(card, 'Framework configurations',
      (project.framework_configurations || []).map(function (fc) {
        return fc.framework + ' / ' + fc.profile_name;
      }));
    appendProjectDetailGroup(card, 'Collections',
      project.chromadb_collections || []);

    return card;
  }

  function appendProjectDetailGroup(card, labelText, items) {
    if (!items || !items.length) return;
    var group = document.createElement('div');
    group.className = 'ora-settings-project-detail-group';
    var label = document.createElement('div');
    label.className = 'ora-settings-project-detail-label';
    label.textContent = labelText;
    group.appendChild(label);
    var list = document.createElement('ul');
    list.className = 'ora-settings-project-detail-list';
    items.slice(0, 8).forEach(function (item) {
      var li = document.createElement('li');
      li.textContent = item;
      list.appendChild(li);
    });
    if (items.length > 8) {
      var liMore = document.createElement('li');
      liMore.textContent = '+' + (items.length - 8) + ' more';
      list.appendChild(liMore);
    }
    group.appendChild(list);
    card.appendChild(group);
  }

  // ── tabs ─────────────────────────────────────────────────────────────────

  // Screen-recording section. Device pickers are real dropdowns fed by
  // GET /api/capture/devices (FFmpeg avfoundation enumeration) — the
  // runtime matches devices by EXACT display name, so free-text entry
  // silently failed on any typo. Devices are fetched once per panel
  // lifetime; when enumeration is unavailable (no FFmpeg / non-macOS)
  // the fields degrade back to free text.
  //
  // The old "Capture system audio by default" checkbox is gone: it was
  // wired to nothing (no system-audio path exists in the FFmpeg command
  // builder — capturing system audio requires a loopback device like
  // BlackHole, which then shows up as an ordinary audio device below).
  var _captureDevices = null;  // null = not fetched; {video:[],audio:[]}

  function _renderCaptureSection(container) {
    if (_captureDevices === null) {
      var loading = document.createElement('p');
      loading.className = 'ora-settings-note';
      loading.textContent = 'Detecting capture devices…';
      container.appendChild(loading);
      fetch('/api/capture/devices')
        .then(function (r) { return r.json(); })
        .then(function (resp) {
          _captureDevices = {
            video: (resp && resp.video) || [],
            audio: (resp && resp.audio) || [],
          };
        })
        .catch(function () { _captureDevices = { video: [], audio: [] }; })
        .then(function () { _drawCaptureSection(container); });
      return;
    }
    _drawCaptureSection(container);
  }

  // Device dropdown: empty option + enumerated device names; a stored
  // value the enumeration doesn't list still renders (tagged "not
  // detected") so the user sees the staleness instead of a silently
  // reset selection.
  function _deviceSelect(path, names, current, emptyLabel) {
    var options = [{ id: '', label: emptyLabel }].concat(
      names.map(function (n) { return { id: n, label: n }; }));
    if (current && names.indexOf(current) === -1) {
      options.push({ id: current, label: current + ' — not detected' });
    }
    return _selectInput(path, options, current || '');
  }

  function _drawCaptureSection(container) {
    container.innerHTML = '';
    _withTarget(container, function () {
      var cap = (_dirty.capture || _settings.capture || {});
      var src = _settings.capture || {};
      var audioNames = _captureDevices.audio.map(function (d) { return d.name; });
      var camNames = _captureDevices.video
        .map(function (d) { return d.name; })
        .filter(function (n) { return !/screen/i.test(n); });
      var haveDevices = audioNames.length > 0 || camNames.length > 0;

      _appendField('Save recordings to',
        _textInput('capture.default_directory',
                   cap.default_directory || src.default_directory || ''));
      _appendNote(
        'Where finished recordings land. Applies from the next recording; '
        + 'stealth conversations keep their recordings inside the '
        + 'conversation\'s own folder regardless.'
      );

      _appendField('Frame rate',
        _selectInput('capture.frame_rate',
                     FRAME_RATES.map(function (n) {
                       return { id: n, label: n + ' fps' };
                     }),
                     cap.frame_rate || src.frame_rate));
      _appendNote(
        'Higher = smoother motion but more encoding load; file size '
        + 'barely changes (the bitrate is fixed). 25–30 fps suits screen '
        + 'demos; pick 50–60 only for fast motion.'
      );

      var audioCur = cap.default_audio_device !== undefined
        ? cap.default_audio_device
        : (src.default_audio_device || '');
      _appendField('Microphone / audio device',
        haveDevices
          ? _deviceSelect('capture.default_audio_device', audioNames,
                          audioCur, '(system default)')
          : _textInput('capture.default_audio_device', audioCur,
                       'leave blank for system default'));
      _appendNote(
        'The audio source recorded with the screen. To record SYSTEM '
        + 'audio (what the speakers play), install a loopback device '
        + 'such as BlackHole and pick it here.'
      );

      var camCur = cap.default_webcam_device !== undefined
        ? cap.default_webcam_device
        : (src.default_webcam_device || '');
      _appendField('Webcam picture-in-picture',
        haveDevices
          ? _deviceSelect('capture.default_webcam_device', camNames,
                          camCur, '(off — screen only)')
          : _textInput('capture.default_webcam_device', camCur,
                       'leave blank to disable'));
      _appendNote(
        'When set, the webcam is overlaid in a corner of the recording. '
        + 'The corner is adjustable from the capture toolbar.'
      );

      if (!haveDevices) {
        _appendNote(
          'Device detection is unavailable on this machine (FFmpeg '
          + 'missing or unsupported platform) — device names entered '
          + 'above must match exactly.'
        );
      }
    });
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

  // Speech (TTS) section — controls the Read-aloud speaker button on
  // scratchpad answers. Provider options:
  //   local_say   — macOS `say` (free, instant, no network)
  //   openrouter  — OpenRouter speech endpoint (paid; better voices)
  //
  // Platform-aware: /api/tts/voices returns [] when the `say` binary
  // is missing (Windows / Linux), in which case the "macOS say" option
  // and its System-Settings note would be pure confusion — the section
  // then offers OpenRouter only and says why. Voices are fetched once
  // and cached for the panel's lifetime.
  var _sayVoices = null;  // null = not fetched; [] = no local speech

  function _renderSpeechSection(container) {
    if (_sayVoices === null) {
      var loading = document.createElement('p');
      loading.className = 'ora-settings-note';
      loading.textContent = 'Checking local voices…';
      container.appendChild(loading);
      fetch('/api/tts/voices')
        .then(function (r) { return r.json(); })
        .then(function (resp) { _sayVoices = (resp && resp.voices) || []; })
        .catch(function () { _sayVoices = []; })
        .then(function () { _drawSpeechSection(container); });
      return;
    }
    _drawSpeechSection(container);
  }

  function _drawSpeechSection(container) {
    container.innerHTML = '';
    _withTarget(container, function () {
      var sp  = (_dirty.speech || _settings.speech || {});
      var src = _settings.speech || {};
      var sayAvailable = (_sayVoices || []).length > 0;
      var provider = sp.provider || src.provider
        || (sayAvailable ? 'local_say' : 'openrouter');
      // A stored local_say on a machine without `say` (settings copied
      // from a Mac) would render a dead pane — show OpenRouter instead;
      // the server-side default is platform-aware the same way.
      if (!sayAvailable && provider === 'local_say') provider = 'openrouter';

      var providerOptions = [];
      if (sayAvailable) {
        providerOptions.push({
          id: 'local_say',
          label: 'System speech — macOS say (free, instant)',
        });
      }
      providerOptions.push(
        { id: 'openrouter', label: 'OpenRouter (paid; better voices)' });

      var providerSel = _selectInput('speech.provider', providerOptions, provider);
      _appendField('Speech provider', providerSel);
      providerSel.addEventListener('change', function () {
        _drawSpeechSection(container);
      });

      if (!sayAvailable) {
        _appendNote(
          'Local system speech isn\'t available on this machine, so '
          + 'reading aloud goes through OpenRouter — it needs an '
          + 'OpenRouter key (External APIs tab).'
        );
      }

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
    });
  }

  // Voice picker built from the cached _sayVoices list (fetched by
  // _renderSpeechSection — no per-render refetch).
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
    sel.addEventListener('change', function (e) {
      _setDirty('speech.local_voice', e.target.value);
    });
    var voices = _sayVoices || [];
    if (!voices.length) {
      sel.innerHTML = '<option value="">(no voices found)</option>';
    } else {
      sel.innerHTML = voices.map(function (v) {
        var sel_attr = (v.name === currentVoice) ? ' selected' : '';
        var label = v.name + (v.language ? ' — ' + v.language : '');
        return '<option value="' + v.name + '"' + sel_attr + '>' + label + '</option>';
      }).join('');
    }
    row.appendChild(sel);
    _tabContentEl.appendChild(row);
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

  function _retrievalOptionLabel(opt, retrieval) {
    var label = opt.label || opt.id || opt.model || '';
    var bits = [];
    if (opt.dimensions) bits.push(opt.dimensions + ' dimensions');
    if (opt.provider === 'openrouter') bits.push('OpenRouter');
    if (opt.native) bits.push('local');
    if (opt.requires_api_key && !(retrieval && retrieval.openrouter_key_present)) {
      bits.push('key needed');
    }
    return bits.length ? (label + ' - ' + bits.join(' / ')) : label;
  }

  // Retrieval section — renders into an explicit container (NOT the
  // module-level _tabContentEl) because its fetch callback re-enters
  // after _withTarget has restored the target; writing to _tabContentEl
  // from there would wipe the whole General tab.
  function _renderRetrievalSection(container) {
    container.innerHTML = '';
    var loading = document.createElement('p');
    loading.className = 'ora-settings-note';
    loading.textContent = 'Loading retrieval settings...';
    container.appendChild(loading);

    fetch('/api/retrieval/config')
      .then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, data: j }; });
      })
      .then(function (res) {
        if (!res.ok) {
          throw new Error((res.data && res.data.error) || 'load failed');
        }
        _retrieval = res.data.retrieval || {};
        _drawRetrievalSection(container);
      })
      .catch(function (err) {
        container.innerHTML = '';
        var note = document.createElement('p');
        note.className = 'ora-settings-note';
        note.textContent = 'Could not load retrieval settings: ' + err.message;
        container.appendChild(note);
      });
  }

  function _drawRetrievalSection(container) {
    var retrieval = _retrieval || {};
    container.innerHTML = '';
    _drawRetrievalFields(container, retrieval);
  }

  function _drawRetrievalFields(container, retrieval) {
    var activeEmbedding = retrieval.active_embedding || {};
    var embeddingOptions = retrieval.embedding_options || [];
    var embeddingSel = document.createElement('select');
    embeddingSel.className = 'ora-settings-input';
    embeddingOptions.forEach(function (opt) {
      var o = document.createElement('option');
      o.value = String(opt.id);
      o.textContent = _retrievalOptionLabel(opt, retrieval);
      if (String(opt.id) === String(activeEmbedding.id)) o.selected = true;
      embeddingSel.appendChild(o);
    });
    _fieldInto(container, 'Embedding model', embeddingSel);

    var embeddingNote = document.createElement('p');
    embeddingNote.className = 'ora-settings-note';
    embeddingNote.textContent = 'Active: '
      + (activeEmbedding.label || activeEmbedding.id || 'unknown')
      + '. The embedding model turns every stored document into search '
      + 'vectors — it decides what Ora\'s memory can find. Switching '
      + 'means re-encoding the entire memory database (hundreds of '
      + 'thousands of documents on a mature install). Selecting here '
      + 'only STAGES the choice; nothing is rebuilt or activated yet.';
    container.appendChild(embeddingNote);

    embeddingSel.addEventListener('change', function () {
      var selected = embeddingSel.value;
      _setStatus('Embedding selection staged. Rebuild required before activation.', 'success');
      fetch('/api/retrieval/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ embedding_profile_id: selected }),
      })
        .then(function (r) {
          return r.json().then(function (j) { return { ok: r.ok, data: j }; });
        })
        .then(function (res) {
          if (!res.ok) throw new Error((res.data && res.data.error) || 'save failed');
          var staged = res.data.embedding_staged || {};
          var profile = staged.profile || {};
          embeddingNote.textContent = 'Staged: ' + (profile.label || selected)
            + '. Rebuild required before activation.';
        })
        .catch(function (err) {
          _setStatus('Embedding selection failed: ' + err.message, 'error');
        });
    });

    var activeReranker = retrieval.active_reranker || {};
    var rerankerOptions = retrieval.reranker_options || [];
    var rerankerSel = document.createElement('select');
    rerankerSel.className = 'ora-settings-input';
    rerankerOptions.forEach(function (opt) {
      var o = document.createElement('option');
      o.value = String(opt.id);
      o.textContent = _retrievalOptionLabel(opt, retrieval);
      if (String(opt.id) === String(activeReranker.id)) o.selected = true;
      rerankerSel.appendChild(o);
    });
    _fieldInto(container, 'Reranker', rerankerSel);
    var rerankNote = document.createElement('p');
    rerankNote.className = 'ora-settings-note';
    rerankNote.textContent = 'After a memory search, the reranker '
      + 're-orders the retrieved snippets by true relevance before they '
      + 'enter the prompt. Changes apply immediately — no rebuild. If a '
      + 'reranker is unreachable, Ora falls back to the original search '
      + 'order. Auto uses Cohere Pro through OpenRouter first, then the '
      + 'local Qwen fallback when available.';
    container.appendChild(rerankNote);

    rerankerSel.addEventListener('change', function () {
      _setStatus('Saving reranker...');
      fetch('/api/retrieval/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reranker_id: rerankerSel.value }),
      })
        .then(function (r) {
          return r.json().then(function (j) { return { ok: r.ok, data: j }; });
        })
        .then(function (res) {
          if (!res.ok) throw new Error((res.data && res.data.error) || 'save failed');
          _retrieval = res.data.retrieval || retrieval;
          _setStatus('Reranker saved', 'success');
          setTimeout(function () { _setStatus(''); }, 1400);
        })
        .catch(function (err) {
          _setStatus('Reranker save failed: ' + err.message, 'error');
        });
    });

    var keyNote = document.createElement('p');
    keyNote.className = 'ora-settings-note';
    keyNote.textContent = retrieval.openrouter_key_present
      ? 'OpenRouter key detected.'
      : 'OpenRouter key not detected. OpenRouter embedding and reranking choices need a key.';
    container.appendChild(keyNote);
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
    // Top region: provider selectors on the left, the API-keys description
    // in the otherwise-empty space on the right.
    var top = document.createElement('div');
    top.className = 'ora-settings-apis-top';

    var topL = document.createElement('div');
    topL.className = 'ora-settings-apis-top-left';
    // (The old "Text-to-speech provider" select was removed 2026-07-01:
    // external_apis.tts_provider had zero runtime consumers — the real
    // speech routing lives on Audio & Video → Speech.)
    _fieldInto(topL, 'Transcription provider',
      _selectInput('external_apis.transcription_provider', [
        { id: 'whisper_local', label: 'Whisper (local)' },
        { id: 'assemblyai',    label: 'AssemblyAI' },
        { id: 'deepgram',      label: 'Deepgram' },
      ], api.transcription_provider || src.transcription_provider));
    var lnote = document.createElement('p');
    lnote.className = 'ora-settings-note ora-settings-apis-topnote';
    lnote.textContent = 'Transcription is an explicit choice — local '
      + 'Whisper is free; pick a cloud provider above only to override '
      + '(set its key below). Speech routing lives under Audio & Video.';
    topL.appendChild(lnote);
    top.appendChild(topL);

    var topR = document.createElement('div');
    topR.className = 'ora-settings-apis-top-right';
    var rh = document.createElement('div');
    rh.className = 'ora-settings-section-header ora-settings-apis-topheader';
    rh.textContent = 'API keys';
    topR.appendChild(rh);
    var rdesc = document.createElement('p');
    rdesc.className = 'ora-settings-note ora-settings-apis-topnote';
    rdesc.innerHTML = 'Stored in your system keychain (Credential Manager on '
      + 'Windows, Secret Service on Linux) — never shown back in the browser. '
      + 'Click a provider’s name (<span class="ora-settings-apikey-extlink">↗</span>) '
      + 'to open its key page; hover it for details. <strong>Save</strong> checks the '
      + 'key with the provider and stores it only if it works. <strong>OpenRouter</strong> '
      + 'is the recommended gateway key — one key reaches hundreds of models; adding a '
      + 'vendor’s own key routes that vendor directly, skipping OpenRouter’s ~5.5% '
      + 'markup (same model, automatic fallback). Search & data keys turn on as '
      + 'soon as they’re saved.';
    topR.appendChild(rdesc);
    top.appendChild(topR);

    _tabContentEl.appendChild(top);

    // Dense two-column grid. Categories are merged into a few sections so the
    // headers + odd-sized groups don't waste the second column. Where a
    // provider is located doesn't matter, so all direct vendors share one
    // "AI providers" section.
    var SECTIONS = [
      { label: 'Gateway',        cats: ['gateway'] },
      { label: 'AI providers',   cats: ['llm_us', 'llm_cn'] },
      { label: 'Search & data',  cats: ['search', 'metadata', 'econ'] },
      { label: 'Speech & image', cats: ['transcription', 'tts', 'image'] },
    ];
    var grid = document.createElement('div');
    grid.className = 'ora-settings-apikeys-grid';
    _tabContentEl.appendChild(grid);

    var placed = {};
    SECTIONS.forEach(function (sec) {
      var rows = _apiKeys.filter(function (r) {
        return sec.cats.indexOf(r.category) !== -1;
      });
      if (!rows.length) return;
      var gh = document.createElement('div');
      gh.className = 'ora-settings-apikey-group';
      gh.textContent = sec.label;
      grid.appendChild(gh);
      rows.forEach(function (r) { placed[r.provider] = true; _appendApiKeyCard(grid, r); });
    });
    // Safety net: any provider whose category isn't in a section still renders.
    var orphans = _apiKeys.filter(function (r) { return !placed[r.provider]; });
    if (orphans.length) {
      var oh = document.createElement('div');
      oh.className = 'ora-settings-apikey-group';
      oh.textContent = 'Other';
      grid.appendChild(oh);
      orphans.forEach(function (r) { _appendApiKeyCard(grid, r); });
    }

    // If a previous open({highlight:...}) call queued a row to
    // emphasize (e.g., from the open-settings event listener wired
    // below), apply it now that rows exist in the DOM.
    if (_pendingHighlight) {
      _applyApiKeyHighlight(_pendingHighlight);
      _pendingHighlight = null;
    }

    // ── Add new provider ───────────────────────────────────────────────
    // The user already has Framework — API Key Setup for end-to-end
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
    addBtn.title = 'Run Framework — API Key Setup to register a new provider';
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
    _appendNote(
      'Word and PDF document exports are not configured here — they run '
      + 'from the Export toolbar above the output pane and save to '
      + '~/Documents/Ora Exports.'
    );
  }

  // One provider per row, single line: name (links to its key page) ·
  // key input · Save · Verify · status · Remove. The provider's one-line
  // note + install-critical/Direct hints live in the name's tooltip so the row
  // stays compact. A feedback line wraps underneath only when there's a
  // validation hint or a Save/Verify result. Tagged data-provider so
  // open({highlight:<id>}) can scroll-to + flash it.
  function _appendApiKeyCard(parent, row) {
    var card = document.createElement('div');
    card.className = 'ora-settings-apikey-card';
    if (row.provider) card.dataset.provider = row.provider;

    var line = document.createElement('div');
    line.className = 'ora-settings-apikey-row1';

    // Provider name = link to its key page. Tooltip carries the note +
    // Required-for-install / Direct hints we no longer spend a row on.
    var tip = [];
    if (row.essential) tip.push('Required for install');
    if (row.direct) tip.push('Direct — bypasses OpenRouter markup');
    if (row.note) tip.push(row.note);
    var label;
    if (row.console_url) {
      label = document.createElement('a');
      label.href = row.console_url;
      label.target = '_blank';
      label.rel = 'noopener noreferrer';
    } else {
      label = document.createElement('span');
    }
    label.className = 'ora-settings-apikey-label';
    label.title = tip.join(' · ') || row.label;
    label.appendChild(document.createTextNode(row.label));
    if (row.console_url) {
      var arrow = document.createElement('span');
      arrow.className = 'ora-settings-apikey-extlink';
      arrow.textContent = '↗';
      label.appendChild(arrow);
    }
    line.appendChild(label);

    // Inline feedback line (validation hint / Save + Verify result).
    var msg = document.createElement('div');
    msg.className = 'ora-settings-apikey-msg';

    var input = document.createElement('input');
    input.type = 'password';
    input.placeholder = row.present ? '•••••• replace' : 'paste API key';
    input.className = 'ora-settings-apikey-input';
    input.autocomplete = 'off';
    if (row.key_prefix) {
      input.addEventListener('input', function () {
        var v = input.value.trim();
        if (v.length > 6 && v.indexOf(row.key_prefix) !== 0) {
          msg.textContent = 'Heads up: ' + row.label + ' keys usually start with “'
            + row.key_prefix + '”.';
          msg.className = 'ora-settings-apikey-msg ora-settings-apikey-msg--warn';
        } else if (msg.classList.contains('ora-settings-apikey-msg--warn')) {
          msg.textContent = '';
          msg.className = 'ora-settings-apikey-msg';
        }
      });
    }
    line.appendChild(input);

    var saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.className = 'ora-settings-btn ora-settings-btn--small';
    saveBtn.textContent = 'Save';
    saveBtn.title = 'Checks the key with the provider, then stores it only if it works';
    line.appendChild(saveBtn);

    var status = document.createElement('span');
    status.className = 'ora-settings-apikey-status '
      + (row.present ? 'ora-settings-apikey-status--set'
                     : 'ora-settings-apikey-status--unset');
    status.textContent = row.present ? 'Set' : 'Not set';
    line.appendChild(status);

    var removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'ora-settings-btn ora-settings-btn--small ora-settings-btn--danger';
    removeBtn.textContent = 'Remove';
    removeBtn.disabled = !row.present;
    line.appendChild(removeBtn);

    saveBtn.addEventListener('click', function () {
      _saveApiKey(row.provider, row.label, input.value, status, input, saveBtn, removeBtn, msg);
    });
    removeBtn.addEventListener('click', function () {
      _deleteApiKey(row.provider, status, input, saveBtn, removeBtn, msg);
    });

    card.appendChild(line);
    card.appendChild(msg);
    parent.appendChild(card);
  }

  // ── input builders ───────────────────────────────────────────────────────

  function _appendField(labelText, inputEl) {
    _fieldInto(_tabContentEl, labelText, inputEl);
  }

  // Like _appendField but appends to an explicit parent (used by the
  // External APIs tab to place the selectors in a left-hand column).
  function _fieldInto(parent, labelText, inputEl) {
    var wrap = document.createElement('div');
    wrap.className = 'ora-settings-field';
    var label = document.createElement('label');
    label.className = 'ora-settings-field-label';
    label.textContent = labelText;
    wrap.appendChild(label);
    wrap.appendChild(inputEl);
    parent.appendChild(wrap);
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
        _providerGroups = data.provider_groups || [];
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

  // Single-button flow: check the key with the provider, then store it ONLY
  // if it isn't rejected. A confirmed rejection (the provider says the key is
  // invalid) pops up a notice and stores nothing. A key that verifies — or
  // one we can't check (no free validity probe for that provider, or a
  // transient network error) — is stored, with the status noting which.
  function _saveApiKey(provider, label, value, statusEl, inputEl, saveBtn, removeBtn, msgEl) {
    var v = (value || '').trim();
    if (!v) {
      if (msgEl) {
        msgEl.textContent = 'Enter a value first.';
        msgEl.className = 'ora-settings-apikey-msg ora-settings-apikey-msg--warn';
      }
      return;
    }
    saveBtn.disabled = true;
    var prevLabel = saveBtn.textContent;
    saveBtn.textContent = 'Checking…';
    if (msgEl) { msgEl.textContent = ''; msgEl.className = 'ora-settings-apikey-msg'; }

    function _restore() { saveBtn.disabled = false; saveBtn.textContent = prevLabel; }

    function _store(note) {
      return fetch('/api/settings/api-key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: provider, value: v }),
      })
        .then(function (r) {
          return r.json().then(function (j) { return { ok: r.ok, data: j }; });
        })
        .then(function (res) {
          if (!res.ok) throw new Error((res.data && res.data.error) || 'save failed');
          statusEl.textContent = 'Set';
          statusEl.className = 'ora-settings-apikey-status ora-settings-apikey-status--set';
          inputEl.value = '';
          inputEl.placeholder = '•••••• replace';
          removeBtn.disabled = false;
          if (msgEl) {
            msgEl.textContent = note;
            msgEl.className = 'ora-settings-apikey-msg ora-settings-apikey-msg--ok';
          }
          _apiKeys.forEach(function (row) {
            if (row.provider === provider) row.present = true;
          });
        })
        .catch(function (err) {
          if (msgEl) {
            msgEl.textContent = 'Save failed: ' + err.message;
            msgEl.className = 'ora-settings-apikey-msg ora-settings-apikey-msg--err';
          }
        });
    }

    fetch('/api/settings/api-key/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: provider, value: v }),
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (res && res.ok === false) {
          // Confirmed invalid — do NOT store it.
          var why = res.message || 'The provider rejected this key.';
          window.alert('“' + label + '” key not saved.\n\n' + why
            + '\n\nNothing was stored — double-check the key and try again.');
          if (msgEl) {
            msgEl.textContent = '✗ Not saved — ' + why;
            msgEl.className = 'ora-settings-apikey-msg ora-settings-apikey-msg--err';
          }
          _restore();
          return;
        }
        // Verified working, or no validity check available → store.
        var note = (res && res.ok === true)
          ? 'Saved ✓ — verified working.'
          : 'Saved ✓ — couldn’t auto-verify this provider.';
        return _store(note).then(_restore);
      })
      .catch(function () {
        // The verify request itself failed (network) — can't confirm it's
        // bad, so store it rather than block a possibly-good key.
        _store('Saved ✓ — couldn’t reach the provider to verify.').then(_restore);
      });
  }

  function _deleteApiKey(provider, statusEl, inputEl, saveBtn, removeBtn, msgEl) {
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
        if (msgEl) { msgEl.textContent = ''; msgEl.className = 'ora-settings-apikey-msg'; }
        _apiKeys.forEach(function (row) {
          if (row.provider === provider) row.present = false;
        });
      })
      .catch(function (err) {
        if (msgEl) {
          msgEl.textContent = 'Delete failed: ' + err.message;
          msgEl.className = 'ora-settings-apikey-msg ora-settings-apikey-msg--err';
        }
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
    'openrouter', 'anthropic', 'openai', 'gemini',
    'xai', 'meta', 'nvidia', 'mistral',
    'deepseek', 'qwen', 'moonshot', 'minimax', 'xiaomi',
    'tavily', 'brave', 'exa', 'artificial_analysis', 'fred',
    'stability', 'replicate', 'tensorart',
    'assemblyai', 'deepgram', 'elevenlabs',
  ];

  // Queued row id to highlight after the next _renderAPIsTab pass.
  // Set by open({highlight: ...}); consumed + cleared by the
  // _renderAPIsTab body when rows render.
  var _pendingHighlight = null;

  // Queued section id to scroll to after the next consolidated-tab
  // render (set when open({tab}) resolves a legacy id via TAB_ALIASES;
  // consumed by _scrollToPendingSection).
  var _pendingSection = null;

  function _scrollToPendingSection() {
    if (!_pendingSection || !_tabContentEl) return;
    var sec = _tabContentEl.querySelector(
      '[data-settings-section="' + _pendingSection + '"]');
    _pendingSection = null;
    if (!sec) return;
    try {
      sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (_) { /* older browsers — ignore */ }
  }

  function open(opts) {
    opts = opts || {};
    if (!_backdropEl) _build();
    if (!_backdropEl.parentNode) document.body.appendChild(_backdropEl);
    _backdropEl.classList.add('ora-settings-backdrop--visible');
    // Optional tab switch — caller passes a TABS entry id or a legacy
    // pre-consolidation id ('transcription', 'speech', 'retrieval',
    // 'interface', 'capture', 'export', 'whisper' — see TAB_ALIASES),
    // which resolves to the hosting tab plus a section to scroll to.
    // Unknown tab ids are silently ignored (defensive against future
    // tab additions / removals).
    if (opts.tab) {
      var alias = TAB_ALIASES[opts.tab];
      var wantedTab = alias ? alias.tab : opts.tab;
      if (_isValidTabId(wantedTab)) {
        _activeTab = wantedTab;
        _pendingSection = alias ? alias.section : null;
        // _renderTabs reflects the new active tab in the tab strip;
        // _renderTabContent is called by _fetchState below for the
        // models tab and runs synchronously for the others.
        if (_tabsEl) _renderTabs();
      }
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
      '.ora-settings-apikey-card[data-provider="' + providerId + '"]'
    );
    if (!row) return;
    row.classList.add('ora-settings-apikey-card--highlight');
    try {
      row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } catch (_) {
      // Older browsers without smooth-scroll options: ignore.
    }
    // Auto-clear the highlight class after the animation completes so
    // the next render starts from a clean slate.
    setTimeout(function () {
      row.classList.remove('ora-settings-apikey-card--highlight');
    }, 3000);
  }

  // Heuristic provider extraction from a fix-path / error-message
  // pair. Used when an `open-settings` CustomEvent doesn't carry an
  // explicit provider id. Returns the first whole-word match (longest id
  // first, so specific ids win over short generic ones like 'meta' that
  // would otherwise substring-match 'metadata'). Returns null when no
  // known provider name appears — the listener then opens the External
  // APIs tab with no highlight and the user finds the row manually.
  function _extractProviderFromHint(fixPath, message) {
    var corpus = (String(fixPath || '') + ' ' + String(message || '')).toLowerCase();
    var ids = KNOWN_PROVIDERS.slice().sort(function (a, b) { return b.length - a.length; });
    for (var i = 0; i < ids.length; i++) {
      if (new RegExp('\\b' + ids[i] + '\\b').test(corpus)) {
        return ids[i];
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
    if (_globalShortcutHandlerInstalled) return;
    _globalShortcutHandlerInstalled = true;
    document.addEventListener('keydown', function (e) {
      if (_recordingShortcutId) return;
      var K = _keyboardShortcuts();
      if (!K || !K.matches('app_show_shortcuts', e)) return;
      e.preventDefault();
      open({ tab: 'shortcuts' });
    }, true);
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
