/**
 * models-pane.js — V3 Models pane (install Chunk 10).
 *
 * Replaces the classic ConfigPanel embed inside the V3 Settings →
 * Models tab. The pane is configuration-driven: users pick or build a
 * named configuration (Premium / Optimum / Budget / Free / Custom),
 * the configuration's slot assignments drive the runtime pipeline,
 * and the registry-backed inventory lets users swap individual models
 * per slot when they want to customize.
 *
 * Layout (top-to-bottom):
 *   1. Header strip       — active config name + Adversarial / Vision toggles
 *   2. Presets row        — 4 cards (Free → Premium left-to-right)
 *   3. Custom row         — Custom-New + Previous grid
 *   4. Inventory grid     — 4 vendor columns, filter chips, intelligence slider
 *   5. Local hardware     — RAM accounting + installed local models (legacy
 *                            ConfigPanel section embedded verbatim)
 *
 * Built across multiple commits — see install Chunk 10 plan.
 * Subsequent commits fill the presets / custom / inventory / hardware
 * sections in turn.
 *
 * Public surface:
 *   OraModelsPane.init(hostEl)  — mount into a container element
 *   OraModelsPane.destroy()      — clean up DOM + cached fetches
 */
(function (root) {
  'use strict';

  if (typeof document === 'undefined') return;

  // ── module state ─────────────────────────────────────────────────────────

  var _hostEl = null;
  var _registry = null;          // /api/model-registry payload
  var _peakIntelByCategory = null; // {category: peakValue} memo, built lazily
  var _picksSet = null;          // Set of model ids from /api/model-registry/picks
  var _configs = null;           // /api/configurations payload — presets + customs + active

  // Order matches the user-locked Free→Premium left-to-right layout.
  var PRESET_ORDER = ['free', 'budget', 'optimum', 'premium'];
  var PRESET_LABELS = {
    free:    'Free',
    budget:  'Budget',
    optimum: 'Optimum',
    premium: 'Premium',
  };

  // Inventory filter + sort state. Persists across renders within a
  // single mount; reset to defaults on every fresh init().
  var _filters = {
    vision: false,
    free_filter: 'any',     // 'any' (default) | 'only' (only free) | 'hide' (drop free) — was previously two mutually-exclusive chips
    pick: false,
    intelligence_pct: 0,    // 0 = show all; 50 = show top 50%; 100 = show nothing
    search: '',
    sort_by: 'alpha_desc',  // alphabetical descending — newest releases bubble up by version-string convention
    category: 'chat',       // inventory category: chat | image_generation | image_editing | text_to_video. Slot-pick mode overrides to the slot's category.
    grouping: 'vendor',     // 'vendor' (default — vendor blocks, collapsible) or 'flat' (no grouping, one sorted list)
  };

  var CATEGORY_OPTIONS = [
    {id: 'chat',             label: 'Chat'},
    {id: 'image_generation', label: 'Image gen'},
    {id: 'image_editing',    label: 'Image edit'},
    {id: 'text_to_video',    label: 'Video'},
  ];

  var SORT_OPTIONS = [
    {id: 'alpha_desc',         label: 'Alphabetical'},
    {id: 'intelligence_desc',  label: 'Intelligence'},
    {id: 'latency_asc',        label: 'Latency'},
    {id: 'speed_desc',         label: 'Tokens/sec'},
    {id: 'cost_asc',           label: 'Cost'},
  ];

  // Vendor expansion state. Vendors are collapsed by default — the
  // inventory shows just vendor names + model counts so the user gets
  // a directory overview. Clicking a vendor header expands its model
  // list; clicking again collapses. Set of vendor names currently
  // expanded.
  var _expandedVendors = new Set();

  // Slot-pick state. When the user clicks a slot value in any card,
  // _activeSlotPick is set to {configName, slotLabel}. The next
  // inventory row click assigns that model to the slot and clears
  // the state. Escape or clicking the slot again cancels.
  var _activeSlotPick = null;

  // Right-side fallback popout state. ▸ More click on any card sets
  // _fallbackPopoutFor = <configName>. Close button or Escape clears.
  var _fallbackPopoutFor = null;

  // Hardware data from /models — system_ram_gb / overhead_gb /
  // available_budget_gb / local_models[]. Used by the bottom
  // hardware analysis section.
  var _hardware = null;

  // ── public API ───────────────────────────────────────────────────────────

  function _onKeydown(evt) {
    if (evt.key !== 'Escape') return;
    if (_fallbackPopoutFor) {
      _fallbackPopoutFor = null;
      _renderPopout();
      _renderPresets();
      _renderCustom();
    } else if (_activeSlotPick) {
      _activeSlotPick = null;
      _renderHeader();
      _renderPresets();
      _renderCustom();
      _renderInventory();
    }
  }

  function init(host) {
    if (!host) return;
    destroy();
    _hostEl = host;
    _hostEl.classList.add('ora-models-pane-host');
    document.addEventListener('keydown', _onKeydown);
    _hostEl.innerHTML = ''
      + '<div class="ora-models-pane">'
      +   '<section class="ora-models-header" data-section="header">'
      +     '<p class="ora-models-loading">Loading model registry…</p>'
      +   '</section>'
      +   '<section class="ora-models-presets" data-section="presets"></section>'
      +   '<section class="ora-models-custom" data-section="custom"></section>'
      +   '<section class="ora-models-inventory" data-section="inventory"></section>'
      +   '<section class="ora-models-hardware" data-section="hardware"></section>'
      +   '<aside class="ora-models-fallback-popout" data-section="popout" hidden></aside>'
      + '</div>';

    _loadAll();
  }

  function destroy() {
    document.removeEventListener('keydown', _onKeydown);
    if (_hostEl) {
      _hostEl.classList.remove('ora-models-pane-host');
      _hostEl.innerHTML = '';
      _hostEl = null;
    }
    _registry = null;
    _picksSet = null;
    _configs = null;
    _filters = {
      vision: false, free_filter: 'any', pick: false,
      intelligence_pct: 0, search: '', sort_by: 'alpha_desc',
      category: 'chat', grouping: 'vendor',
    };
    _expandedVendors = new Set();
    _activeSlotPick = null;
    _fallbackPopoutFor = null;
    _hardware = null;
  }

  // ── data load ───────────────────────────────────────────────────────────

  function _loadAll() {
    // Chunk 11 step 4: fetch ALL categories so slot-row lookups can
    // resolve image-gen / image-edit / text-to-video model ids in the
    // registry. The inventory grid filters down to chat-only at render
    // time (see _renderInventory) until step 5 wires the
    // click-slot-then-swap-inventory gesture.
    Promise.all([
      fetch('/api/model-registry?categories=all').then(_json),
      fetch('/api/model-registry/picks').then(_json),
      fetch('/api/configurations').then(_json),
      fetch('/models').then(_json).catch(function () { return null; }),
    ]).then(function (resp) {
      _registry = resp[0] || {};
      _peakIntelByCategory = null;  // recomputed lazily on first call
      var picksPayload = resp[1] || {};
      _picksSet = new Set(picksPayload.picks || []);
      _configs = resp[2] || {presets: {}, customs: [],
                             active_name: '', active_toggles: {}};
      _hardware = resp[3] || null;
      // Sync the inventory's Vision filter chip to the active
      // Vision-capable toggle. Without this, page reload while the
      // toggle is on leaves the chip off — the toggle/chip sync code
      // in _setToggle only fires on user click, not initial load.
      var activeToggles = _configs.active_toggles || {};
      if (activeToggles.vision_only) _filters.vision = true;
      _renderHeader();
      _renderPresets();
      _renderCustom();
      _renderInventory();
      _renderPopout();
      _renderHardware();
      _renderRemainingSkeleton();
      _maybeAutoRefresh();
    }).catch(function (err) {
      _showHeaderError(err);
    });
  }

  // Refresh just the active-config indicator + toggles without
  // refetching the registry. Cheap; used after a toggle change or an
  // active-card switch.
  function _refreshActive() {
    fetch('/api/configurations').then(_json).then(function (configs) {
      _configs = configs || _configs;
      _renderHeader();
      _renderPresets();
      _renderCustom();
    });
  }

  function _json(r) { return r.json(); }

  function _showHeaderError(err) {
    var header = _hostEl && _hostEl.querySelector('[data-section="header"]');
    if (header) {
      header.innerHTML = '<p class="ora-models-error">'
        + 'Could not load model configuration: '
        + ((err && err.message) || 'unknown error')
        + '</p>';
    }
  }

  // ── header strip ────────────────────────────────────────────────────────

  function _renderHeader() {
    if (!_hostEl) return;
    var header = _hostEl.querySelector('[data-section="header"]');
    if (!header) return;
    var name = (_configs && _configs.active_name) || '(none)';
    var missing = _configs && _configs.active_missing;
    var t = (_configs && _configs.active_toggles) || {};
    var adv = !!t.adversarial_diversity;
    var vis = !!t.vision_only;
    var refreshedAt = _registry && _registry.generated_at;
    var refreshLabel = refreshedAt
      ? 'Refreshed ' + refreshedAt.substring(0, 10)
      : 'Never refreshed';

    // AA source badge: which path the last sync used for Artificial
    // Analysis intelligence + pricing data. Set under Settings →
    // External APIs → "AA intelligence data source". Older registries
    // (synced before the API path landed) don't carry the field;
    // default to "scrape" since that was the only path then.
    var aaSource = (_registry && _registry.aa_source) || (refreshedAt ? 'scrape' : null);
    var aaBadgeLabel = null;
    var aaBadgeTitle = null;
    if (aaSource === 'api') {
      aaBadgeLabel = 'AA: API';
      aaBadgeTitle = 'AA data came from the official REST API. Switch in Settings → External APIs.';
    } else if (aaSource === 'mixed') {
      aaBadgeLabel = 'AA: Mixed';
      aaBadgeTitle = 'API was selected but one or more endpoints fell back to the scrape on this run.';
    } else if (aaSource === 'scrape') {
      aaBadgeLabel = 'AA: Scrape';
      aaBadgeTitle = 'AA data came from the public /models page (no API key needed). Switch in Settings → External APIs.';
    }

    header.innerHTML = ''
      + '<div class="ora-models-header-strip">'
      +   '<div class="ora-models-active">'
      +     '<span class="ora-models-active-label">Active:</span> '
      +     '<strong class="ora-models-active-name">' + _esc(name) + '</strong>'
      +     (missing
        ? ' <span class="ora-models-warn">(missing — pick another)</span>'
        : '')
      +   '</div>'
      +   _toggleHTML('adversarial_diversity', adv,
                     'Adversarial Diversity',
                     'two workhorses cross-check — doubles cost, catches blind spots')
      +   _toggleHTML('vision_only', vis,
                     'Vision-capable only',
                     'restrict picks to models that see images directly')
      +   '<div class="ora-models-refresh-wrap" title="Re-fetch the model registry from OpenRouter + AA + LiteLLM (~15-30s, no tokens). Auto-runs on pane open when the data is more than 24h old.">'
      +     '<span class="ora-models-refresh-label">' + _esc(refreshLabel) + '</span>'
      +     (aaBadgeLabel
        ? '<span class="ora-models-aa-source-badge" title="' + _esc(aaBadgeTitle) + '">' + _esc(aaBadgeLabel) + '</span>'
        : '')
      +     '<button type="button" class="ora-models-refresh-btn" data-action="refresh">↻</button>'
      +   '</div>'
      + '</div>';

    // Wire change handlers
    Array.from(header.querySelectorAll('.ora-models-toggle input')).forEach(function (el) {
      el.addEventListener('change', function () {
        _setToggle(el.dataset.toggle, el.checked);
      });
    });
    var refreshBtn = header.querySelector('[data-action="refresh"]');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', function () {
        _refreshRegistry(true);
      });
    }
  }

  // Refresh the registry. ``manual=true`` forces it even if the
  // registry's generated_at is recent; otherwise the server's TTL
  // guard skips the actual sync. Either way, we re-fetch
  // /api/model-registry after the call returns so the pane shows
  // whatever's current.
  function _refreshRegistry(manual) {
    var btn = _hostEl && _hostEl.querySelector('[data-action="refresh"]');
    if (btn) {
      btn.classList.add('ora-models-refresh-btn-spinning');
      btn.disabled = true;
    }
    fetch('/api/model-registry/refresh', {method: 'POST'})
      .then(_json)
      .then(function () {
        return _loadAll();  // re-fetch everything, re-render
      })
      .catch(function (err) {
        console.warn('[models-pane] refresh failed:', err);
        if (manual) alert('Refresh failed: ' + (err && err.message));
      })
      .then(function () {
        if (btn) {
          btn.classList.remove('ora-models-refresh-btn-spinning');
          btn.disabled = false;
        }
      });
  }

  // Auto-refresh check fired on init: if the registry's generated_at
  // is more than 24h ago, kick off a refresh. The server-side TTL
  // guard collapses concurrent refresh requests to one, so this is
  // safe even if multiple settings opens stack up.
  function _maybeAutoRefresh() {
    if (!_registry) return;
    var gen = _registry.generated_at;
    if (!gen) {
      // Never refreshed — fire one
      _refreshRegistry(false);
      return;
    }
    var genMs = Date.parse(gen);
    if (isNaN(genMs)) return;
    var ageHours = (Date.now() - genMs) / (1000 * 60 * 60);
    if (ageHours > 24) _refreshRegistry(false);
  }

  function _toggleHTML(name, checked, label, helpText) {
    // Compact inline layout: knob · bold-label · muted-help — all on
    // one row so two toggles + active-config name fit on a single
    // horizontal line at typical settings-modal widths.
    return ''
      + '<label class="ora-models-toggle">'
      +   '<input type="checkbox" data-toggle="' + name + '"' + (checked ? ' checked' : '') + '>'
      +   '<span class="ora-models-toggle-knob"></span>'
      +   '<span class="ora-models-toggle-label">' + _esc(label) + '</span>'
      +   '<span class="ora-models-toggle-help">' + _esc(helpText) + '</span>'
      + '</label>';
  }

  function _setToggle(name, value) {
    var payload = {};
    payload[name] = value;
    // Vision-capable toggle auto-syncs the inventory's Vision filter
    // chip: if you say "I only want vision-capable models" globally,
    // the inventory should hide text-only models too without a
    // separate click. Reverse on toggle-off: turn off the chip so
    // the inventory returns to showing everything.
    if (name === 'vision_only') {
      _filters.vision = !!value;
    }
    fetch('/api/configurations/active/toggles', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    }).then(_json).then(function (resp) {
      if (resp && resp.toggles) {
        if (_configs) _configs.active_toggles = resp.toggles;
        // Refresh both header + presets — the active preset card may
        // change its toggle-chip footer when the active toggles flip.
        _refreshActive();
        _renderInventory();  // pick up the auto-synced filter
      }
    }).catch(function (err) {
      // Toggle didn't persist — revert the checkbox state by reloading
      // header from current cached state. The user sees their click
      // "bounce back," which signals failure without a modal.
      _renderHeader();
      console.warn('[models-pane] toggle save failed:', err);
    });
  }

  // ── presets row ─────────────────────────────────────────────────────────

  function _renderPresets() {
    if (!_hostEl) return;
    var section = _hostEl.querySelector('[data-section="presets"]');
    if (!section) return;
    var presets = (_configs && _configs.presets) || {};
    var activeName = (_configs && _configs.active_name) || '';
    var cards = PRESET_ORDER.map(function (preset) {
      return _presetCardHTML(preset, presets[preset], activeName);
    });
    section.innerHTML = ''
      + '<header class="ora-models-section-header">'
      +   '<h3>Presets</h3>'
      +   '<span class="ora-models-section-hint">Auto-picked from the model registry. '
      +     'Click a card to activate; Customize to fork into a new configuration.</span>'
      + '</header>'
      + '<div class="ora-models-row ora-models-preset-row">'
      +   cards.join('')
      + '</div>';

    // Wire activate + customize per card
    Array.from(section.querySelectorAll('.ora-models-card')).forEach(function (card) {
      var configName = card.dataset.configName;
      if (!configName) return;
      card.addEventListener('click', function (evt) {
        // Ignore clicks on buttons or slot rows inside the card —
        // slot rows have their own data-pick-slot handler wired below.
        if (evt.target.closest('button')) return;
        if (evt.target.closest('[data-pick-slot]')) return;
        // Red (incomplete) or yellow (deprecated-model) cards are
        // not eligible for activation. The user has to either
        // finish filling the red one or update the deprecated
        // entry first. The currently-active config keeps running
        // even if it goes yellow — the fallback chain catches.
        if (card.classList.contains('ora-models-card-incomplete')) {
          _flashCardMessage(card, 'Fill every slot before activating.');
          return;
        }
        // Yellow (deprecated) cards DO activate — the user has to be
        // able to edit them to fix the deprecation. Red still blocks
        // because incomplete configs can't run at all. Yellow's whole
        // point is "runs but needs attention"; activating it is how
        // you replace the deprecated picks.
        _activateConfig(configName);
      });
      var customizeBtn = card.querySelector('[data-action="customize"]');
      if (customizeBtn) {
        customizeBtn.addEventListener('click', function () {
          _customizeFrom(configName);
        });
      }
      var moreBtn = card.querySelector('[data-action="more"]');
      if (moreBtn) {
        moreBtn.addEventListener('click', function () {
          // Toggle: click ▸ More opens; click ▾ Less closes.
          _fallbackPopoutFor = (_fallbackPopoutFor === configName) ? null : configName;
          // Re-render cards so the More/Less label flips and the
          // bottom expand-rows show/hide on this card.
          _renderPresets();
          _renderCustom();
          _renderPopout();
        });
      }
    });
    _wireSlotPickHandlers(section);
  }

  // Briefly show a status message anchored to a card. Used when a click
  // on a red/yellow card is refused so the user sees why nothing
  // happened. Auto-clears after ~2.5s.
  function _flashCardMessage(card, msg) {
    var existing = card.querySelector('.ora-models-card-flash');
    if (existing) existing.remove();
    var el = document.createElement('div');
    el.className = 'ora-models-card-flash';
    el.textContent = msg;
    card.appendChild(el);
    setTimeout(function () {
      if (el.parentElement === card) el.remove();
    }, 2500);
  }

  // Slot pick: clicking a slot row sets _activeSlotPick. The next
  // inventory row click commits the pick. Clicking the same slot
  // again (or pressing Escape) cancels.
  function _wireSlotPickHandlers(section) {
    Array.from(section.querySelectorAll('[data-pick-slot]')).forEach(function (row) {
      // Skip rows on read-only (non-active) cards — they keep the
      // data-pick-slot attribute so the card-level activate handler
      // still ignores their clicks, but no pick gesture is wired.
      if (row.dataset.pickDisabled === 'true') {
        row.addEventListener('click', function (evt) {
          // Eat the click on the row itself so it doesn't bubble up
          // to the card-level activate handler.
          if (evt.target.closest('button')) return;
          evt.stopPropagation();
        });
        return;
      }
      row.addEventListener('click', function (evt) {
        if (evt.target.closest('button')) return;
        evt.stopPropagation();
        var slotLabel = row.dataset.pickSlot;
        var configName = row.dataset.pickConfig;
        if (_activeSlotPick
            && _activeSlotPick.configName === configName
            && _activeSlotPick.slotLabel === slotLabel) {
          _activeSlotPick = null;
        } else {
          _activeSlotPick = {configName: configName, slotLabel: slotLabel};
        }
        _renderHeader();
        _renderPresets();
        _renderCustom();
        _renderInventory();
      });
    });
  }

  function _presetCardHTML(presetName, summary, activeName) {
    var label = PRESET_LABELS[presetName] || presetName;

    if (!summary) {
      // Preset hasn't been baked yet — show a placeholder card with
      // the same dimensions as a real one so the row stays aligned.
      return ''
        + '<div class="ora-models-card ora-models-card-empty" data-preset="' + presetName + '">'
        +   '<header class="ora-models-card-header">'
        +     '<span class="ora-models-card-title">' + _esc(label) + '</span>'
        +   '</header>'
        +   '<div class="ora-models-card-body">'
        +     '<p class="ora-models-empty-msg">Not yet generated. The next '
        +       'registry refresh bakes this preset; refresh now from the '
        +       'header (coming in step 14).</p>'
        +   '</div>'
        + '</div>';
    }

    var isActive = (summary.name === activeName);
    var chips = _toggleChips(summary.toggles);
    var adversarial = !!(summary.toggles && summary.toggles.adversarial_diversity);
    // Free preset's slots always cost $0 — drop the cost component
    // from the slot meta so the line stays tight.
    var omitCost = (presetName === 'free');
    var incomplete = !!summary.incomplete;
    var deprecatedList = _deprecatedPrimaries(summary);
    var deprecated = deprecatedList.length > 0;
    var depTitle = deprecated ? _deprecatedTooltip(deprecatedList) : '';
    return ''
      + '<div class="ora-models-card ora-models-card-preset'
      +   (isActive ? ' ora-models-card-active' : '')
      +   (incomplete ? ' ora-models-card-incomplete' : '')
      +   (deprecated && !incomplete ? ' ora-models-card-deprecated' : '') + '"'
      +   (depTitle ? ' title="' + _esc(depTitle) + '"' : '')
      +   ' data-preset="' + presetName + '"'
      +   ' data-config-name="' + _esc(summary.name) + '">'
      +   '<header class="ora-models-card-header">'
      +     '<span class="ora-models-card-title">' + _esc(label) + '</span>'
      +     chips
      +     (isActive ? '<span class="ora-models-card-active-flag">active</span>'
                      : '<span class="ora-models-card-active-flag" aria-hidden="true"></span>')
      +   '</header>'
      +   '<div class="ora-models-card-body">'
      +     _slotRowHTML('big 1', summary.big1, {omitCost: omitCost, configName: summary.name, isActive: isActive})
      +     (adversarial
        ? _slotRowHTML('big 2', summary.big2, {omitCost: omitCost, configName: summary.name, isActive: isActive})
        : '')
      +     _slotRowHTML('small', summary.small, {omitCost: omitCost, configName: summary.name, isActive: isActive})
      +     _slotRowHTML('image gen', summary.image_generation,
            {omitCost: omitCost, configName: summary.name, isActive: isActive})
      +     _expandSlotsHTML(summary, {omitCost: omitCost, isActive: isActive})
      +   '</div>'
      +   '<div class="ora-models-card-actions">'
      +     '<button type="button" class="ora-models-card-btn" data-action="more">'
      +       _moreLabelFor(summary.name) + '</button>'
      +     '<button type="button" class="ora-models-card-btn" data-action="customize">Customize</button>'
      +   '</div>'
      + '</div>';
  }

  // Renders the 4 extra rows below big 1 / big 2 / small when the
  // card is in the expanded state (▸ More clicked). Visual fallback +
  // consolidator + verifier + formatter — each its own slot-pickable
  // row that breaks the default "post-analysis inherits big 1" rule.
  function _expandSlotsHTML(summary, opts) {
    if (_fallbackPopoutFor !== summary.name) return '';
    var c = {
      configName: summary.name,
      omitCost: !!(opts && opts.omitCost),
      isActive: !!(opts && opts.isActive),
    };
    // 2026-05-22 reshape: visual + the three single-cell overrides
    // the publisher specified. Order matches the four-row spec from
    // the items 1-7 list ("visual model is right, but the others
    // should be utility, Consolidate, and Verify"). Formatter is
    // gone from the expand view — the pipeline still runs that step
    // internally but always uses the inherited big-1 model.
    return ''
      + '<div class="ora-models-card-expand">'
      +   _slotRowHTML('visual', summary.visual, c)
      +   _slotRowHTML('utility', summary.utility, c)
      +   _slotRowHTML('consolidate', summary.consolidate, c)
      +   _slotRowHTML('verify', summary.verify, c)
      + '</div>';
  }

  function _moreLabelFor(configName) {
    return _fallbackPopoutFor === configName ? '▾ Less' : '▸ More';
  }

  function _slotRowHTML(label, modelId, opts) {
    opts = opts || {};
    var configName = opts.configName || '';
    var isActiveSlot = _activeSlotPick
      && _activeSlotPick.configName === configName
      && _activeSlotPick.slotLabel === label;
    // Slot edits are only allowed on the currently-active configuration.
    // Presets and inactive customs are read-only — the user has to
    // Customize first to fork into an editable copy.
    // ``opts.isActive`` (set by the card builder) drives whether the row
    // is editable; ``opts.nonClickable`` is the legacy escape hatch for
    // individual rows whose pick gesture isn't wired yet.
    // Note: the ``data-pick-slot`` attribute is emitted regardless of
    // active state so the card-level activate handler can recognise
    // slot-row clicks and skip the activation path; the click HANDLER
    // is only attached in _wireSlotPickHandlers when the row's owning
    // card is active.
    var clickable = !!configName && !!opts.isActive && !opts.nonClickable;
    var rowEditable = !!configName && !opts.nonClickable;
    var classes = 'ora-models-slot-row';
    if (isActiveSlot) classes += ' ora-models-slot-row-picking';
    if (clickable) classes += ' ora-models-slot-row-clickable';
    if (opts.nonClickable) classes += ' ora-models-slot-row-readonly';

    if (!modelId) {
      return '<div class="' + classes + ' ora-models-slot-empty"'
        + (rowEditable ? ' data-pick-slot="' + _esc(label) + '"' +
                         ' data-pick-config="' + _esc(configName) + '"' : '')
        + (clickable ? '' : ' data-pick-disabled="true"')
        + '>'
        + '<span class="ora-models-slot-label">' + _esc(label) + '</span>'
        + '<span class="ora-models-slot-value">—</span>'
        + '</div>';
    }
    var isPick = _picksSet && _picksSet.has(modelId);
    var registry = (_registry && _registry.models) || {};
    var model = registry[modelId];
    var isDeprecated = !model;  // referenced model isn't in the registry
    if (isDeprecated) classes += ' ora-models-slot-row-deprecated';
    var meta = model ? _compactMetaHTML(model, opts) : '';
    // Display name preference: media models (aa-img/aa-edit/aa-vid keys)
    // have UUID-style ids that shorten to garbage, so use display_name
    // when present. Chat-model ids like ``openai/gpt-5.5`` keep their
    // existing terse rendering.
    var isMediaId = /^aa-(img|edit|vid):/.test(modelId);
    var rowValue = (isMediaId && model && model.display_name)
      ? model.display_name : _shortenModelId(modelId);
    // Capability chip distinguishing image/video from chat models in
    // the inventory and on cards.
    var capChip = '';
    if (model && model.category === 'image_generation')
      capChip = '<span class="ora-models-cap-chip ora-models-cap-image">IMAGE</span>';
    else if (model && model.category === 'image_editing')
      capChip = '<span class="ora-models-cap-chip ora-models-cap-image">IMAGE EDIT</span>';
    else if (model && model.category === 'text_to_video')
      capChip = '<span class="ora-models-cap-chip ora-models-cap-video">VIDEO</span>';
    return '<div class="' + classes + '"'
      + (rowEditable ? ' data-pick-slot="' + _esc(label) + '"' +
                       ' data-pick-config="' + _esc(configName) + '"' : '')
      + (clickable ? '' : ' data-pick-disabled="true"')
      + (isDeprecated ? ' title="This model is no longer in the registry. '
                       + 'Pick a replacement."' : '')
      + '>'
      + '<span class="ora-models-slot-label">' + _esc(label) + '</span>'
      + '<span class="ora-models-slot-value" title="' + _esc(modelId) + '">'
      +   _esc(rowValue)
      +   capChip
      +   (isPick ? '<span class="ora-models-pick-chip">PICK</span>' : '')
      +   (isDeprecated ? '<span class="ora-models-deprecated-chip">DEPRECATED</span>' : '')
      +   (meta ? '<span class="ora-models-slot-meta">' + meta + '</span>' : '')
      + '</span>'
      + '</div>';
  }

  // Compact meta line used in BOTH card slot rows and inventory rows.
  // Format: X% peak · $Y/M · Z t/s — parts dropped when underlying
  // data is null/absent. Intelligence shown as a percentage of the
  // top-rated model in the same category (chat-max for chat models,
  // image-arena-Elo-max for image models, etc.) so users get a
  // relative valuation rather than a raw score on a scale they
  // don't know the bounds of. Recomputes when the registry reloads.
  // opts.omitCost: True for Free-preset cards where cost is always $0.
  function _compactMetaHTML(model, opts) {
    opts = opts || {};
    var parts = [];
    var isMedia = (model.category && model.category !== 'chat');
    var pct = _intelligencePeakPercent(model);
    if (pct != null) parts.push(pct + '% peak');
    if (isMedia) {
      if (!opts.omitCost) {
        var pricing = model.pricing || {};
        var per1k = pricing.per_1k_images;
        if (per1k != null) {
          var unit = (model.category === 'text_to_video') ? '/1k clips' : '/1k imgs';
          parts.push('$' + per1k.toFixed(0) + unit);
        }
      }
      return parts.join(' · ');
    }
    if (!opts.omitCost) {
      var blended = _blendedCostPerM(model);
      if (blended != null) {
        parts.push('$' + blended.toFixed(2) + '/M');
      }
    }
    if (model.output_tokens_per_second != null) {
      parts.push(model.output_tokens_per_second.toFixed(0) + ' t/s');
    }
    return parts.join(' · ');
  }

  // Intelligence as percent of the per-category peak. 100% = the
  // highest-rated model in this model's category; everything else
  // scales down. Returns null when the model has no intelligence
  // score recorded. Lazy memoization across renders; reset on
  // registry reload.
  function _intelligencePeakPercent(model) {
    if (!model || model.category === undefined) {
      // Defensive: callers pass full registry entries
    }
    var category = (model && model.category) || 'chat';
    var raw = _rawIntelligence(model);
    if (raw == null) return null;
    if (!_peakIntelByCategory) _peakIntelByCategory = _computePeakIntelByCategory();
    var peak = _peakIntelByCategory[category];
    if (!peak || peak <= 0) return null;
    return Math.round((raw / peak) * 100);
  }

  function _computePeakIntelByCategory() {
    var peaks = {};
    var models = (_registry && _registry.models) || {};
    Object.keys(models).forEach(function (id) {
      var m = models[id];
      var cat = (m && m.category) || 'chat';
      var v = _rawIntelligence(m);
      if (v == null) return;
      if (!peaks[cat] || v > peaks[cat]) peaks[cat] = v;
    });
    return peaks;
  }

  // True if any primary in the configuration references a model that
  // is no longer in the live registry. Backed by ``summary.all_primaries``
  // (a flat list of every primary across every cell). Surfaces as the
  // yellow card border + the per-row deprecated chip already in place;
  // the yellow card itself signals "fix me when you have time" — the
  // config keeps running because the fallback chain catches the missing
  // primary in flight.
  function _hasDeprecatedModel(summary) {
    return _deprecatedPrimaries(summary).length > 0;
  }

  // List of every primary id in the config that's no longer in the
  // registry. Used by the card tooltip to tell the user WHICH cell is
  // the deprecation source — useful when the bad primary lives in a
  // cell that doesn't render anywhere on the card (e.g. utility's
  // classification cell, which fans out from SMALL but has no row
  // of its own).
  function _deprecatedPrimaries(summary) {
    var all = (summary && summary.all_primaries) || [];
    if (!Array.isArray(all) || !all.length) return [];
    var models = (_registry && _registry.models) || {};
    return all.filter(function (id) { return !models[id]; });
  }

  // Tooltip text listing the deprecated primary ids on a yellow card.
  // The custom tooltip CSS uses `white-space: nowrap` so this has to
  // fit on one line. One model: name the id directly. Multiple: name
  // the count and the first id, suffix "(+N more)" — enough for the
  // user to know which cell to inspect after activating.
  function _deprecatedTooltip(ids) {
    var n = ids.length;
    if (n === 1) return 'Deprecated model: ' + ids[0] + ' — activate to fix';
    return n + ' deprecated models (' + ids[0]
      + (n > 1 ? ' + ' + (n - 1) + ' more' : '')
      + ') — activate to fix';
  }

  // Raw intelligence per category, used to compute the % peak.
  //   Chat models       → AA's 0-100 intelligence index. (Chat models
  //                       also carry an Arena Elo in intelligence_score,
  //                       but those two are different scales and can't
  //                       be mixed in the same peak comparison.)
  //   Image/video       → AA's head-to-head Arena Elo, stored in
  //                       intelligence_score. aa_intelligence_index is
  //                       null for media.
  // Each category compares within its own units. Cross-category
  // % peak comparisons are not meaningful and not surfaced anywhere.
  function _rawIntelligence(model) {
    if (!model) return null;
    var category = model.category || 'chat';
    if (category === 'chat') {
      return model.aa_intelligence_index != null ? model.aa_intelligence_index : null;
    }
    // image_generation, image_editing, text_to_video, etc.
    return model.intelligence_score != null ? model.intelligence_score : null;
  }

  // Single intelligence number for display + sort. Prefers AA index
  // (already on a 0-100 scale). Falls back to Arena ELO normalized
  // via (elo - 800) / 7 so 800 ELO → 0, 1500 ELO → 100 — roughly
  // co-scaled with AA. The normalization isn't perfect across the
  // population but it's better than mixing two scale labels in the
  // UI. Used by both the meta display and the intelligence-slider
  // percentile filter.
  function _normalizedIntelligence(model) {
    if (model.aa_intelligence_index != null) {
      return model.aa_intelligence_index;
    }
    if (model.intelligence_score != null) {
      return Math.max(0, Math.min(100, (model.intelligence_score - 800) / 7));
    }
    return null;
  }

  function _blendedCostPerM(model) {
    // AA blended convention: 3:1 input:output. So:
    //   blended_per_token = 0.75 * input + 0.25 * output
    //   blended_per_M     = blended_per_token * 1_000_000
    var pricing = model.pricing || {};
    var inp = pricing.input_per_token;
    var out = pricing.output_per_token;
    if (inp == null && out == null) return null;
    // Free-tier rows have both at 0 — show $0.00/M (rather than null).
    var i = inp != null ? inp : 0;
    var o = out != null ? out : 0;
    return (0.75 * i + 0.25 * o) * 1e6;
  }

  function _toggleChips(toggles) {
    toggles = toggles || {};
    var bits = [];
    if (toggles.adversarial_diversity) bits.push('Adversarial');
    if (toggles.vision_only) bits.push('Vision-only');
    // Empty span (no "—" placeholder) when neither toggle is on, so
    // the header's center column collapses and the title / active
    // flag space without competing with a visible dash.
    if (!bits.length) return '<span class="ora-models-card-header-chips"></span>';
    return '<span class="ora-models-card-header-chips ora-models-toggle-chip">'
      + bits.join(' · ')
      + '</span>';
  }

  function _shortenModelId(id) {
    // Vendor/model → just the model side for card display. The full
    // id is on the title attr for hover.
    if (!id) return '';
    var slash = id.lastIndexOf('/');
    return slash >= 0 ? id.substring(slash + 1) : id;
  }

  function _activateConfig(name) {
    // First-time Free pick gets a one-time acknowledgment modal that
    // explains the rate-limit / queueing / inconsistency tradeoffs.
    // Acknowledgment persists in localStorage.
    if (name === 'free' && !_freeAcknowledged()) {
      _showFreeThrottlingModal(function () {
        _markFreeAcknowledged();
        _doActivate(name);
      });
      return;
    }
    _doActivate(name);
  }

  function _doActivate(name) {
    fetch('/api/configurations/active', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: name}),
    }).then(_json).then(function (resp) {
      if (resp && resp.error) {
        console.warn('[models-pane] activate failed:', resp.error);
        return;
      }
      _refreshActive();
    }).catch(function (err) {
      console.warn('[models-pane] activate failed:', err);
    });
  }

  var FREE_ACK_KEY = 'ora_free_throttling_ack_v1';

  function _freeAcknowledged() {
    try { return localStorage.getItem(FREE_ACK_KEY) === '1'; }
    catch (_) { return false; }
  }
  function _markFreeAcknowledged() {
    try { localStorage.setItem(FREE_ACK_KEY, '1'); } catch (_) {}
  }

  function _showFreeThrottlingModal(onConfirm) {
    // Build a one-shot modal overlaid on the pane.
    var backdrop = document.createElement('div');
    backdrop.className = 'ora-models-free-modal-backdrop';
    backdrop.innerHTML = ''
      + '<div class="ora-models-free-modal" role="dialog" aria-labelledby="ora-free-modal-title">'
      +   '<h3 id="ora-free-modal-title">Before you pick Free</h3>'
      +   '<p>Free models work, but the tradeoffs are real:</p>'
      +   '<ul>'
      +     '<li><strong>Rate limits.</strong> Free providers cap requests-per-minute '
      +       'and per-day. Ora\'s deep fallback chain walks across providers to '
      +       'work around this, but during busy hours your request may queue.</li>'
      +     '<li><strong>Inconsistent results.</strong> Because the chain may '
      +       'fall through several models per request, two runs of the same '
      +       'prompt can come back from different models — output style and '
      +       'depth will vary.</li>'
      +     '<li><strong>Models change.</strong> Free providers add and pull '
      +       'models without notice. Ora auto-refreshes the registry, but '
      +       'your saved picks may go deprecated.</li>'
      +     '<li><strong>Quick fix if Free isn\'t enough:</strong> add a small '
      +       'amount of OpenRouter credit or set up direct provider keys '
      +       '(External APIs tab). Even a cheap-tier paid configuration like '
      +       'Budget gets you consistent results.</li>'
      +   '</ul>'
      +   '<div class="ora-models-free-modal-actions">'
      +     '<button type="button" class="ora-models-card-btn" data-action="cancel">Cancel</button>'
      +     '<button type="button" class="ora-models-card-btn ora-models-card-btn-primary" data-action="ack">I understand — use Free</button>'
      +   '</div>'
      + '</div>';

    document.body.appendChild(backdrop);

    function close() { backdrop.remove(); }
    backdrop.querySelector('[data-action="cancel"]').addEventListener('click', close);
    backdrop.querySelector('[data-action="ack"]').addEventListener('click', function () {
      close();
      if (typeof onConfirm === 'function') onConfirm();
    });
    backdrop.addEventListener('click', function (evt) {
      if (evt.target === backdrop) close();
    });
  }

  function _customizeFrom(name) {
    // Prompt for a name; default to auto-incremented Configuration NN.
    var suggested = prompt(
      'Name for the new configuration?\n\nLeave blank to use the next '
      + 'auto-numbered name (Configuration 01, 02, …).',
      ''
    );
    if (suggested === null) return;  // user cancelled
    fetch('/api/configurations/duplicate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({source: name, new_name: suggested || null}),
    }).then(_json).then(function (resp) {
      if (resp && resp.error) {
        alert('Could not duplicate: ' + resp.error);
        return;
      }
      _loadAll();
    }).catch(function (err) {
      alert('Could not duplicate: ' + (err && err.message));
    });
  }

  function _createNew() {
    fetch('/api/configurations/new', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({}),
    }).then(_json).then(function (resp) {
      if (resp && resp.error) {
        alert('Could not create: ' + resp.error);
        return;
      }
      _loadAll();
    }).catch(function (err) {
      alert('Could not create: ' + (err && err.message));
    });
  }

  function _commitSlotPick(modelId) {
    if (!_activeSlotPick || !modelId) return;
    var pick = _activeSlotPick;
    _activeSlotPick = null;
    fetch('/api/configurations/' + encodeURIComponent(pick.configName) + '/slot', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({slot: pick.slotLabel, model_id: modelId}),
    }).then(_json).then(function (resp) {
      if (resp && resp.error) {
        alert('Could not assign model: ' + resp.error);
        return;
      }
      _loadAll();
    }).catch(function (err) {
      alert('Could not assign model: ' + (err && err.message));
    });
  }

  function _deleteCustom(name) {
    if (!confirm('Delete configuration "' + name + '"?\n\nThis is permanent.')) {
      return;
    }
    fetch('/api/configurations/' + encodeURIComponent(name), {
      method: 'DELETE',
    }).then(_json).then(function (resp) {
      if (resp && resp.error) {
        alert('Could not delete: ' + resp.error);
        return;
      }
      _loadAll();
    }).catch(function (err) {
      alert('Could not delete: ' + (err && err.message));
    });
  }

  // ── custom row (Custom-New + Previous grid) ─────────────────────────────

  function _renderCustom() {
    if (!_hostEl) return;
    var section = _hostEl.querySelector('[data-section="custom"]');
    if (!section) return;
    var customs = (_configs && _configs.customs) || [];
    var activeName = (_configs && _configs.active_name) || '';

    // Single grid: "+ New configuration" pinned to the leftmost
    // column, then saved customs follow. The earlier "Custom-New"
    // workspace column was retired in step 6g — + New owns that
    // role now. Editing an existing custom happens in-place on its
    // card via the slot-pick gesture (step 8).
    var cards = [_newConfigCardHTML()];
    customs.forEach(function (c) {
      cards.push(_customCardHTML(c, c.name === activeName));
    });

    section.innerHTML = ''
      + '<header class="ora-models-section-header">'
      +   '<h3>Custom configurations</h3>'
      +   '<span class="ora-models-section-hint">'
      +     'Click any card to activate. Customize copies a card into a new entry. '
      +     '+ New starts a blank configuration.'
      +   '</span>'
      + '</header>'
      + '<div class="ora-models-row ora-models-custom-row">'
      +   cards.join('')
      + '</div>';

    // Wire interactions for the grid cards.
    Array.from(section.querySelectorAll('.ora-models-card-custom')).forEach(function (card) {
      var configName = card.dataset.configName;
      card.addEventListener('click', function (evt) {
        if (evt.target.closest('button')) return;
        if (evt.target.closest('[data-pick-slot]')) return;
        if (card.classList.contains('ora-models-card-incomplete')) {
          _flashCardMessage(card, 'Fill every slot before activating.');
          return;
        }
        // Yellow (deprecated) activates — see _wirePresetCard for the
        // rationale. Red still blocks.
        _activateConfig(configName);
      });
      var customizeBtn = card.querySelector('[data-action="customize"]');
      if (customizeBtn) {
        customizeBtn.addEventListener('click', function () { _customizeFrom(configName); });
      }
      var moreBtn = card.querySelector('[data-action="more"]');
      if (moreBtn) {
        moreBtn.addEventListener('click', function () {
          // Toggle: click ▸ More opens; click ▾ Less closes.
          _fallbackPopoutFor = (_fallbackPopoutFor === configName) ? null : configName;
          // Re-render cards so the More/Less label flips and the
          // bottom expand-rows show/hide on this card.
          _renderPresets();
          _renderCustom();
          _renderPopout();
        });
      }
      var deleteBtn = card.querySelector('[data-action="delete"]');
      if (deleteBtn) {
        deleteBtn.addEventListener('click', function () { _deleteCustom(configName); });
      }
    });
    var newBtn = section.querySelector('[data-action="new"]');
    if (newBtn) {
      newBtn.addEventListener('click', _createNew);
    }
    _wireSlotPickHandlers(section);
  }

  function _customCardHTML(summary, isActive) {
    var adversarial = !!(summary.toggles && summary.toggles.adversarial_diversity);
    // Read the incomplete flag straight from the summary — set by the
    // backend when create_blank_configuration runs (via + New) and
    // cleared the moment the four baselines all fill. Legacy customs
    // that happen to be missing image_generation are NOT flagged,
    // because the flag tracks "started from scratch, not yet finished"
    // intent, not a live completeness check.
    var incomplete = !!summary.incomplete;
    var deprecatedList = _deprecatedPrimaries(summary);
    var deprecated = deprecatedList.length > 0;
    var depTitle = deprecated ? _deprecatedTooltip(deprecatedList) : '';
    return ''
      + '<div class="ora-models-card ora-models-card-custom'
      +   (isActive ? ' ora-models-card-active' : '')
      +   (incomplete ? ' ora-models-card-incomplete' : '')
      +   (deprecated && !incomplete ? ' ora-models-card-deprecated' : '') + '"'
      +   (depTitle ? ' title="' + _esc(depTitle) + '"' : '')
      +   ' data-config-name="' + _esc(summary.name) + '">'
      +   '<header class="ora-models-card-header">'
      +     '<span class="ora-models-card-title">' + _esc(summary.name) + '</span>'
      +     _toggleChips(summary.toggles)
      +     (isActive ? '<span class="ora-models-card-active-flag">active</span>'
                      : '<span class="ora-models-card-active-flag" aria-hidden="true"></span>')
      +   '</header>'
      +   '<div class="ora-models-card-body">'
      +     _slotRowHTML('big 1', summary.big1, {configName: summary.name, isActive: isActive})
      +     (adversarial
        ? _slotRowHTML('big 2', summary.big2, {configName: summary.name, isActive: isActive})
        : '')
      +     _slotRowHTML('small', summary.small, {configName: summary.name, isActive: isActive})
      +     _slotRowHTML('image gen', summary.image_generation,
            {configName: summary.name, isActive: isActive})
      +     _expandSlotsHTML(summary, {isActive: isActive})
      +   '</div>'
      +   '<div class="ora-models-card-actions">'
      +     '<button type="button" class="ora-models-card-btn" data-action="more">'
      +       _moreLabelFor(summary.name) + '</button>'
      +     '<button type="button" class="ora-models-card-btn" data-action="customize">'
      +       'Customize</button>'
      +     '<button type="button" class="ora-models-card-btn ora-models-card-btn-danger"'
      +       ' data-action="delete" title="Delete">×</button>'
      +   '</div>'
      + '</div>';
  }

  function _newConfigCardHTML() {
    return ''
      + '<div class="ora-models-card ora-models-card-new-slot">'
      +   '<button type="button" class="ora-models-new-config-btn" data-action="new">'
      +     '<span class="ora-models-new-plus">+</span>'
      +     '<span>New configuration</span>'
      +   '</button>'
      + '</div>';
  }

  // ── inventory grid ──────────────────────────────────────────────────────

  function _renderInventory() {
    if (!_hostEl) return;
    var section = _hostEl.querySelector('[data-section="inventory"]');
    if (!section) return;
    var models = (_registry && _registry.models) || {};
    // Inventory category resolution: a slot pick on the active card
    // forces the matching category (so picking IMAGE GEN swaps the
    // inventory to image models). With no slot picking in progress,
    // the user's category dropdown drives — defaults to Chat. The
    // Models pane only edits image_generation today, but Image edit
    // and Video are surfaced in the dropdown so the user can browse
    // them and see what's available even before the Visual tab lands.
    var SLOT_TO_CATEGORY = {
      'image gen': 'image_generation',
    };
    var slotPickLabel = _activeSlotPick ? _activeSlotPick.slotLabel : null;
    var wantCategory = (slotPickLabel && SLOT_TO_CATEGORY[slotPickLabel])
      || _filters.category
      || 'chat';
    var allModels = Object.values(models).filter(function (m) {
      var c = (m && m.category) || 'chat';
      return c === wantCategory;
    });

    // Compute the intelligence cutoff once (used by both the filter
    // and shown in the header). Combined score normalises Arena ELO
    // (typical 800-1500) and AA Index (0-100) into a single 0-1
    // ranking so the slider works regardless of which source covers
    // a given model.
    var scoredModels = allModels.map(function (m) {
      return {model: m, score: _combinedScore(m)};
    });
    var ranked = scoredModels.filter(function (s) { return s.score != null; })
                             .sort(function (a, b) { return b.score - a.score; });
    var keepRanked = Math.ceil(ranked.length * (1 - _filters.intelligence_pct / 100));
    var rankedKeptIds = new Set(ranked.slice(0, keepRanked).map(function (s) {
      return s.model.id;
    }));

    // Group ALL models by vendor first (so each vendor knows its
    // total). Filter within each vendor's list afterwards so the
    // vendor header can report "matching of total". Vendors with
    // zero matches are HIDDEN when any filter is active — they
    // become noise (the user knows they exist, just doesn't want to
    // see them right now). When no filters are active, every vendor
    // shows even at zero (which never happens for unfiltered counts
    // anyway).
    var anyFilterActive = _filters.vision
                          || (_filters.free_filter && _filters.free_filter !== 'any')
                          || _filters.pick
                          || _filters.intelligence_pct > 0
                          || !!_filters.search;
    var allByVendor = _groupByVendor(allModels);
    var groupsForDisplay = Object.keys(allByVendor).sort().map(function (vendor) {
      var vendorAll = allByVendor[vendor];
      var vendorMatches = vendorAll.filter(function (m) {
        return _matchesFilters(m, rankedKeptIds);
      });
      return {
        vendor: vendor,
        total: vendorAll.length,
        models: vendorMatches,
      };
    }).filter(function (g) {
      return !anyFilterActive || g.models.length > 0;
    });
    var totalCount = allModels.length;
    var visibleCount = groupsForDisplay.reduce(function (sum, g) {
      return sum + g.models.length;
    }, 0);

    // Build the rendered inventory body. Two layouts:
    //   vendor  — collapsible vendor blocks distributed across 4 columns
    //   flat    — all matching models in one sorted list, no vendor
    //             headers; rows distributed column-major across 4 columns
    //             so the cheapest (or smartest) bubbles up to the top
    //             of column 1.
    var inventoryBody;
    if (_filters.grouping === 'flat') {
      var flatModels = [];
      groupsForDisplay.forEach(function (g) {
        flatModels = flatModels.concat(g.models);
      });
      flatModels = _sortModels(flatModels, _filters.sort_by);
      inventoryBody = _flatColumnsHTML(flatModels);
    } else {
      var columns = _distributeVendorsToColumns(groupsForDisplay);
      inventoryBody = columns.map(_columnHTML).join('');
    }

    var pickBanner = '';
    if (_activeSlotPick) {
      pickBanner = ''
        + '<div class="ora-models-pick-banner">'
        +   'Picking <strong>' + _esc(_activeSlotPick.slotLabel)
        +   '</strong> for <strong>' + _esc(_activeSlotPick.configName)
        +   '</strong> — click a model below, or press Esc to cancel.'
        + '</div>';
    }
    section.innerHTML = ''
      + '<header class="ora-models-section-header">'
      +   '<h3>Model inventory</h3>'
      +   '<span class="ora-models-section-hint">'
      +     '<span class="ora-models-inventory-count">'
      +       _esc(String(visibleCount)) + ' of ' + _esc(String(totalCount)) + ' models'
      +     '</span>'
      +     ' · vendors alphabetical by column · local pinned to top of column 1'
      +     ' · <span class="ora-models-inventory-hint-peak">% peak</span> = intelligence relative to the top-rated model in its category'
      +   '</span>'
      + '</header>'
      + pickBanner
      + '<div class="ora-models-inventory-controls">'
      +   _categorySelectHTML()
      +   _filterChipsHTML()
      +   _sortSelectHTML()
      +   _groupingControlsHTML()
      +   _sliderHTML()
      +   _searchInputHTML()
      + '</div>'
      + '<div class="ora-models-row ora-models-inventory-row">'
      +   inventoryBody
      + '</div>';

    _wireInventoryControls(section);
  }

  function _combinedScore(model) {
    // Use the same normalization the meta display uses (see
    // _normalizedIntelligence) so the slider's filter and the row's
    // visible "int X" number agree.
    var intel = _normalizedIntelligence(model);
    return intel != null ? intel / 100 : null;
  }

  function _matchesFilters(model, rankedKeptIds) {
    // Chat-only filter chips (Vision, Free, Hide free) are skipped for
    // media models — vision_capable=false on every image-gen entry
    // (they OUTPUT images), and the free/paid distinction doesn't apply
    // to image_generation today (pricing-based, surfaced as $/1k imgs
    // on the row meta). The PICK chip and intelligence slider DO apply.
    var isMedia = (model.category && model.category !== 'chat');
    if (!isMedia && _filters.vision && model.vision_capable !== true) return false;
    var isFree = (model.id || '').endsWith(':free') || model.is_free === true;
    if (!isMedia && _filters.free_filter === 'only' && !isFree) return false;
    if (!isMedia && _filters.free_filter === 'hide' && isFree) return false;
    if (_filters.pick && !(_picksSet && _picksSet.has(model.id))) return false;
    // Slot-pick size gate. When picking BIG 1 / BIG 2, restrict to
    // large-bucket models; SMALL / utility to small-bucket. Models
    // with no size_bucket are excluded — most of them are "~latest"
    // mirror aliases (where the route picks whatever the vendor's
    // current latest is, so size is undefined) and showing them as
    // candidates for a sized slot misleads the user. The size_bucket
    // field is enriched by /api/model-registry from model-catalog.json.
    var sizeFilter = _activeSlotPickSizeBucket();
    if (sizeFilter) {
      if (!model.size_bucket || model.size_bucket !== sizeFilter) return false;
    }
    // Slot-pick capability gate. The VISUAL slot is the vision
    // substitute — the model that handles image input when the
    // analyst chain can't see it directly. It must be vision-capable
    // regardless of whether the Vision filter chip is on. Other
    // slots have no per-slot capability requirement today.
    if (_activeSlotPick && _activeSlotPick.slotLabel === 'visual'
        && model.vision_capable !== true) {
      return false;
    }
    // Intelligence filter: when slider is at 0 (default), show all
    // including unranked. When > 0, drop everything not in the top X%.
    if (_filters.intelligence_pct > 0) {
      if (!rankedKeptIds.has(model.id)) return false;
    }
    if (_filters.search) {
      var s = _filters.search.toLowerCase();
      var name = (model.display_name || '').toLowerCase();
      var id = (model.id || '').toLowerCase();
      if (name.indexOf(s) === -1 && id.indexOf(s) === -1) return false;
    }
    return true;
  }

  // Each card-visible slot maps to an expected size bucket. When a slot
  // is in picking mode, the inventory restricts to that bucket so the
  // user doesn't see small models as candidates for a big-1 slot or
  // large models for a small slot. Returns null when no slot pick is
  // active or when the slot's category swap (image gen) handles the
  // restriction differently.
  var SLOT_TO_SIZE_BUCKET = {
    'big 1':       'large',
    'big 2':       'large',
    'small':       'small',
    'visual':      'large',
    'utility':     'small',
    'consolidate': 'large',
    'verify':      'large',
    // 'image gen' intentionally absent — category swap handles it,
    // image-gen models don't carry size_bucket.
  };

  function _activeSlotPickSizeBucket() {
    if (!_activeSlotPick) return null;
    return SLOT_TO_SIZE_BUCKET[_activeSlotPick.slotLabel] || null;
  }

  function _vendorOf(model) {
    var id = model.id || '';
    // Media entries (aa-img:UUID / aa-edit:UUID / aa-vid:UUID) carry
    // a normalized ``vendor`` field set from AA's creator name —
    // their UUID-style ids don't have a slash-prefix vendor segment.
    // Lowercase so "OpenAI" from media groups with "openai" from
    // OpenRouter ids when both categories are surfaced.
    if (model.vendor) return String(model.vendor).toLowerCase();
    if (id.indexOf('/') === -1) {
      // Local-MLX style ids (no slash) — bucket as Local.
      return 'Local';
    }
    return id.substring(0, id.indexOf('/'));
  }

  function _groupByVendor(models) {
    var groups = {};
    models.forEach(function (m) {
      var v = _vendorOf(m);
      if (!groups[v]) groups[v] = [];
      groups[v].push(m);
    });
    // Sort each vendor's models per the active Sort dropdown choice.
    Object.keys(groups).forEach(function (v) {
      groups[v] = _sortModels(groups[v], _filters.sort_by);
    });
    return groups;
  }

  function _sortModels(models, by) {
    var arr = models.slice();
    switch (by) {
      case 'intelligence_desc':
        return arr.sort(function (a, b) {
          var ai = _normalizedIntelligence(a);
          var bi = _normalizedIntelligence(b);
          if (ai == null) ai = -1;
          if (bi == null) bi = -1;
          return bi - ai;
        });
      case 'cost_asc':
        return arr.sort(function (a, b) {
          var ac = _blendedCostPerM(a);
          var bc = _blendedCostPerM(b);
          // Negative blended cost is a sentinel for "no real pricing"
          // emitted by OpenRouter's auto-routing meta-models (Auto
          // Router, Pareto Code Router, etc.). Push them to the
          // bottom alongside genuine no-price rows so the user sees
          // priced models first when sorting by cost ascending.
          if (ac == null || ac < 0) ac = Infinity;
          if (bc == null || bc < 0) bc = Infinity;
          return ac - bc;
        });
      case 'latency_asc':
        return arr.sort(function (a, b) {
          var al = a.latency_ttft_seconds;
          var bl = b.latency_ttft_seconds;
          if (al == null) al = Infinity;
          if (bl == null) bl = Infinity;
          return al - bl;
        });
      case 'speed_desc':
        return arr.sort(function (a, b) {
          var as = a.output_tokens_per_second;
          var bs = b.output_tokens_per_second;
          if (as == null) as = -1;
          if (bs == null) bs = -1;
          return bs - as;
        });
      case 'alpha_desc':
      default:
        return arr.sort(function (a, b) {
          var ai = (a.id || '').toLowerCase();
          var bi = (b.id || '').toLowerCase();
          if (ai > bi) return -1;
          if (ai < bi) return 1;
          return 0;
        });
    }
  }

  function _distributeVendorsToColumns(groups) {
    // 4 equal columns. Local pinned to the top of column 1; remaining
    // vendors split alphabetical-by-column so the user reads down-
    // then-right. Each group is already {vendor, total, models}.
    var columns = [[], [], [], []];
    var localGroup = groups.find(function (g) { return g.vendor === 'Local'; });
    if (localGroup && localGroup.total > 0) {
      columns[0].push(localGroup);
    }
    var otherGroups = groups.filter(function (g) { return g.vendor !== 'Local'; });
    var perCol = Math.ceil(otherGroups.length / 4);
    otherGroups.forEach(function (group, i) {
      var colIdx = Math.min(3, Math.floor(i / perCol));
      columns[colIdx].push(group);
    });
    return columns;
  }

  function _columnHTML(column) {
    if (!column.length) {
      return '<div class="ora-models-inventory-column"></div>';
    }
    return '<div class="ora-models-inventory-column">'
      + column.map(_vendorBlockHTML).join('')
      + '</div>';
  }

  function _vendorBlockHTML(group) {
    // Vendors stay COLLAPSED regardless of active filters — the user
    // explicitly rejected auto-expand because it caused sideways
    // scroll across vendor columns. Instead, the count in the vendor
    // header updates to show how many models match the active
    // filters: "moonshotai (3 of 14)" when 3 of moonshotai's 14
    // models pass the filters. User clicks to expand and sees the
    // matching rows. Manually-expanded vendors stay expanded across
    // filter changes (their visible rows just shrink to matches).
    var isExpanded = _expandedVendors.has(group.vendor);
    var caret = isExpanded ? '▾' : '▸';
    var total = group.total;
    var matching = group.models.length;
    var countText = (matching < total)
      ? '(' + matching + ' of ' + total + ')'
      : '(' + total + ')';
    return ''
      + '<div class="ora-models-vendor-block' + (isExpanded ? ' ora-models-vendor-expanded' : '') + '">'
      +   '<h4 class="ora-models-vendor-name" data-vendor="' + _esc(group.vendor) + '">'
      +     '<span class="ora-models-vendor-caret">' + caret + '</span>'
      +     ' ' + _esc(group.vendor)
      +     ' <span class="ora-models-vendor-count">' + countText + '</span>'
      +   '</h4>'
      +   (isExpanded
        ? '<ul class="ora-models-model-list">' + group.models.map(_modelRowHTML).join('') + '</ul>'
        : '')
      + '</div>';
  }

  // Strip the leading "Vendor: " prefix from a display name. The
  // inventory groups by vendor already, so the prefix is redundant
  // and makes rows wider than they need to be. e.g.
  // "OpenAI: GPT-5.5" → "GPT-5.5", "Google: Gemini 3.5 Flash" →
  // "Gemini 3.5 Flash". Image-model names like "GPT Image 2 (high)"
  // have no colon and pass through unchanged. Tilde-prefixed
  // mirror-vendors (e.g. "~OpenAI: Foo") also strip cleanly.
  function _stripVendorPrefix(name) {
    if (typeof name !== 'string') return name;
    var idx = name.indexOf(': ');
    if (idx <= 0) return name;
    // Don't strip if the right side is empty
    var right = name.slice(idx + 2).trim();
    if (!right) return name;
    return right;
  }

  function _modelRowHTML(model) {
    // Single-line inventory row: name + chips + meta, all inline.
    // Meta is the same compact summary used in card slot rows.
    var displayName = _stripVendorPrefix(model.display_name || model.id);
    return ''
      + '<li class="ora-models-model-row" title="' + _esc(model.id) + '"'
      +   ' data-model-id="' + _esc(model.id) + '">'
      +   '<span class="ora-models-model-name">' + _esc(displayName) + '</span>'
      +   _modelChipsHTML(model)
      +   '<span class="ora-models-model-meta">' + _compactMetaHTML(model) + '</span>'
      + '</li>';
  }

  function _modelChipsHTML(model) {
    var chips = [];
    if (_picksSet && _picksSet.has(model.id)) {
      chips.push('<span class="ora-models-pick-chip">PICK</span>');
    }
    if (model.vision_capable === true) {
      chips.push('<span class="ora-models-chip ora-models-chip-vision">vision</span>');
    }
    if ((model.id || '').endsWith(':free')) {
      chips.push('<span class="ora-models-chip ora-models-chip-free">:free</span>');
    }
    // Reachability chips. Set by the registry's reachability probe (see
    // sync_model_registry.py::reach_probe_one). The probe records
    // reachable: true/false/null + rate_limited boolean. We surface three
    // states: rate-limited (yellow — endpoint exists, throttled), unreachable
    // (red — 404 / 410 / 400-other), unverified (grey — no probe data yet).
    if (model.reachable === false) {
      chips.push('<span class="ora-models-chip ora-models-chip-unreachable" title="Reachability probe failed — this model returned 404 / 410 / 400 (not bad-request). Auto-populate skips it.">UNREACHABLE</span>');
    } else if (model.reachable === true && model.reachable_rate_limited) {
      chips.push('<span class="ora-models-chip ora-models-chip-rate-limited" title="Endpoint exists, but the probe hit a rate limit. Common on free-tier models; the fallback chain catches it at runtime.">RATE-LIMITED</span>');
    } else if (model.reachable !== true) {
      // null / undefined — never probed, or last probe was inconclusive.
      chips.push('<span class="ora-models-chip ora-models-chip-unverified" title="No recent reachability probe data. Run scripts/sync_model_registry.py reach to verify.">UNVERIFIED</span>');
    }
    // Vendor audit chip. vendor_listed=false means the vendor's own
    // /v1/models endpoint doesn't include this id. Could be a true
    // phantom (AA invented it), or a real model that ships only via
    // OpenRouter / third-parties (e.g. open-source models like
    // gpt-oss-120b). Surface the signal but don't treat it as a hard
    // failure — reachable=true + vendor_listed=false is still
    // deployable. Only audited for openai / anthropic / google ids;
    // other vendors have no checked endpoint so the chip stays off.
    if (model.vendor_listed === false) {
      chips.push('<span class="ora-models-chip ora-models-chip-vendor-phantom" title="Vendor\'s own /v1/models endpoint does not list this id. May be an AA-only phantom, or a real model that only routes via OpenRouter (open-source / third-party). Combine with the UNREACHABLE chip to identify true phantoms.">NOT IN VENDOR LIST</span>');
    }
    return chips.join('');
  }

  function _filterChipsHTML() {
    var chips = [
      {key: 'vision', label: 'Vision'},
      {key: 'pick',   label: 'PICK'},
    ];
    var freeOptions = [
      {id: 'any',  label: 'Any cost'},
      {id: 'only', label: 'Free only'},
      {id: 'hide', label: 'Hide free'},
    ];
    var freeSel = _filters.free_filter || 'any';
    var freeSelectHTML = ''
      + '<label class="ora-models-sort-wrap" title="Free-tier filter">'
      +   '<select class="ora-models-sort-select" data-filter="free_filter">'
      +     freeOptions.map(function (o) {
            var sel = o.id === freeSel ? ' selected' : '';
            return '<option value="' + o.id + '"' + sel + '>' + _esc(o.label) + '</option>';
          }).join('')
      +   '</select>'
      + '</label>';
    return '<div class="ora-models-filter-chips">'
      + chips.map(function (c) {
          var on = _filters[c.key];
          return '<label class="ora-models-filter-chip' + (on ? ' ora-models-filter-chip-on' : '') + '">'
            + '<input type="checkbox" data-filter="' + c.key + '"' + (on ? ' checked' : '') + '>'
            + _esc(c.label)
            + '</label>';
        }).join('')
      + freeSelectHTML
      + '</div>';
  }

  // Vendor list for the currently-displayed category — used by the
  // Expand-all action to know which vendor names to add to the
  // expanded set. Walks the registry once; cheap relative to a render.
  function _collectAllVendorsForCurrentCategory() {
    var models = (_registry && _registry.models) || {};
    var SLOT_TO_CATEGORY = {'image gen': 'image_generation'};
    var slotPickLabel = _activeSlotPick ? _activeSlotPick.slotLabel : null;
    var wantCategory = (slotPickLabel && SLOT_TO_CATEGORY[slotPickLabel])
      || _filters.category || 'chat';
    var vendors = new Set();
    Object.keys(models).forEach(function (id) {
      var m = models[id];
      var cat = (m && m.category) || 'chat';
      if (cat !== wantCategory) return;
      vendors.add(_vendorOf(m));
    });
    return Array.from(vendors);
  }

  // Grouping controls: single toggle between vendor-grouped (default)
  // and flat list, plus expand-all / collapse-all buttons that only
  // matter in vendor mode (disabled in flat).
  function _groupingControlsHTML() {
    var isFlat = (_filters.grouping || 'vendor') === 'flat';
    // The toggle reads as a checkbox-shaped button: pressed/active when
    // flat mode is on, unpressed when grouped by vendor. The label
    // names the OFF state's destination ("Flat list") so the user sees
    // what clicking will do, consistent with the standard toggle idiom.
    var toggleBtn = '<button type="button" class="ora-models-grouping-btn ora-models-grouping-toggle'
      + (isFlat ? ' ora-models-grouping-btn-active' : '') + '"'
      + ' data-grouping-toggle="1"'
      + ' aria-pressed="' + (isFlat ? 'true' : 'false') + '"'
      + ' title="Toggle: vendor groups (default) vs flat sorted list">'
      + (isFlat ? '✓ Flat list' : 'Flat list')
      + '</button>';
    var expandBtn = '<button type="button" class="ora-models-grouping-btn"'
      + (isFlat ? ' disabled' : '')
      + ' data-grouping-action="expand-all"'
      + ' title="Expand every vendor block">'
      + 'Expand all</button>';
    var collapseBtn = '<button type="button" class="ora-models-grouping-btn"'
      + (isFlat ? ' disabled' : '')
      + ' data-grouping-action="collapse-all"'
      + ' title="Collapse every vendor block">'
      + 'Collapse all</button>';
    return ''
      + '<div class="ora-models-grouping-wrap">'
      +   toggleBtn + expandBtn + collapseBtn
      + '</div>';
  }

  // Flat-list layout: distribute matching models column-major across 4
  // columns. The user sorted by Cost (or whatever) sees the top of
  // column 1 first; column 2 picks up where 1 left off.
  function _flatColumnsHTML(models) {
    if (!models.length) {
      return '<div class="ora-models-inventory-column">'
        + '<p class="ora-models-empty-msg">No models match the current filters.</p>'
        + '</div>';
    }
    var perCol = Math.ceil(models.length / 4);
    var cols = [[], [], [], []];
    models.forEach(function (m, i) {
      var idx = Math.min(3, Math.floor(i / perCol));
      cols[idx].push(m);
    });
    return cols.map(function (col) {
      if (!col.length) return '<div class="ora-models-inventory-column"></div>';
      return '<div class="ora-models-inventory-column">'
        + '<ul class="ora-models-model-list ora-models-model-list-flat">'
        +   col.map(_modelRowHTML).join('')
        + '</ul>'
        + '</div>';
    }).join('');
  }

  function _categorySelectHTML() {
    // Active slot-pick locks the category to match the slot — show the
    // dropdown disabled so the user sees why their click can't change it.
    var slotPickLabel = _activeSlotPick ? _activeSlotPick.slotLabel : null;
    var SLOT_TO_CATEGORY = {'image gen': 'image_generation'};
    var locked = !!(slotPickLabel && SLOT_TO_CATEGORY[slotPickLabel]);
    var effectiveCategory = locked
      ? SLOT_TO_CATEGORY[slotPickLabel]
      : (_filters.category || 'chat');
    var options = CATEGORY_OPTIONS.map(function (opt) {
      var sel = opt.id === effectiveCategory ? ' selected' : '';
      return '<option value="' + opt.id + '"' + sel + '>' + _esc(opt.label) + '</option>';
    }).join('');
    return ''
      + '<label class="ora-models-sort-wrap" title="Browse inventory by category">'
      +   '<span class="ora-models-sort-label">Category</span>'
      +   '<select class="ora-models-sort-select" data-filter="category"'
      +     (locked ? ' disabled' : '') + '>'
      +     options
      +   '</select>'
      + '</label>';
  }

  function _sortSelectHTML() {
    var options = SORT_OPTIONS.map(function (opt) {
      var sel = opt.id === _filters.sort_by ? ' selected' : '';
      return '<option value="' + opt.id + '"' + sel + '>' + _esc(opt.label) + '</option>';
    }).join('');
    return ''
      + '<label class="ora-models-sort-wrap" title="Sort within each vendor">'
      +   '<span class="ora-models-sort-label">Sort</span>'
      +   '<select class="ora-models-sort-select" data-filter="sort_by">'
      +     options
      +   '</select>'
      + '</label>';
  }

  function _sliderHTML() {
    return ''
      + '<div class="ora-models-slider-wrap" title="Intelligence floor — slide right to keep only top-ranked models">'
      +   '<span class="ora-models-slider-label">Intel</span>'
      +   '<input type="range" min="0" max="95" step="5" value="'
      +     String(_filters.intelligence_pct) + '" class="ora-models-slider" data-filter="intelligence_pct">'
      + '</div>';
  }

  function _searchInputHTML() {
    return ''
      + '<input type="search" class="ora-models-search" placeholder="filter…"'
      + ' value="' + _esc(_filters.search) + '" data-filter="search">';
  }

  function _wireInventoryControls(section) {
    Array.from(section.querySelectorAll('.ora-models-filter-chip input')).forEach(function (el) {
      el.addEventListener('change', function () {
        _filters[el.dataset.filter] = el.checked;
        _renderInventory();
      });
    });
    var slider = section.querySelector('.ora-models-slider');
    if (slider) {
      slider.addEventListener('input', function () {
        _filters.intelligence_pct = parseInt(slider.value, 10) || 0;
        _renderInventory();
      });
    }
    var searchEl = section.querySelector('.ora-models-search');
    if (searchEl) {
      searchEl.addEventListener('input', function () {
        _filters.search = searchEl.value || '';
        _renderInventory();
      });
    }
    // Dispatch every select (sort + category) on its data-filter key.
    Array.from(section.querySelectorAll('.ora-models-sort-select')).forEach(function (el) {
      el.addEventListener('change', function () {
        var key = el.dataset.filter;
        if (!key) return;
        _filters[key] = el.value;
        _renderInventory();
      });
    });
    // Grouping toggle (vendor ⇆ flat). Single button flips state on each
    // click. Expand-all / Collapse-all affect _expandedVendors and only
    // matter in vendor mode (disabled in flat).
    var groupingToggle = section.querySelector('[data-grouping-toggle]');
    if (groupingToggle) {
      groupingToggle.addEventListener('click', function () {
        _filters.grouping = (_filters.grouping === 'flat') ? 'vendor' : 'flat';
        _renderInventory();
      });
    }
    var expandAll = section.querySelector('[data-grouping-action="expand-all"]');
    if (expandAll) {
      expandAll.addEventListener('click', function () {
        if (expandAll.disabled) return;
        var allVendors = _collectAllVendorsForCurrentCategory();
        _expandedVendors = new Set(allVendors);
        _renderInventory();
      });
    }
    var collapseAll = section.querySelector('[data-grouping-action="collapse-all"]');
    if (collapseAll) {
      collapseAll.addEventListener('click', function () {
        if (collapseAll.disabled) return;
        _expandedVendors = new Set();
        _renderInventory();
      });
    }
    // Inventory row clicks commit a slot pick when one is active.
    Array.from(section.querySelectorAll('.ora-models-model-row')).forEach(function (row) {
      row.addEventListener('click', function () {
        if (!_activeSlotPick) return;
        var modelId = row.dataset.modelId;
        _commitSlotPick(modelId);
      });
    });
    // Click a vendor header to toggle its expansion. Auto-expanded
    // vendors (from active filters) can still be manually collapsed,
    // but they auto-expand again on the next render — that's fine,
    // active filters mean "I want to see what matches" and collapsing
    // hides that signal.
    Array.from(section.querySelectorAll('.ora-models-vendor-name')).forEach(function (el) {
      el.addEventListener('click', function () {
        var v = el.dataset.vendor;
        if (_expandedVendors.has(v)) {
          _expandedVendors.delete(v);
        } else {
          _expandedVendors.add(v);
        }
        _renderInventory();
      });
    });
  }

  // ── Right-side fallback popout ──────────────────────────────────────────

  function _renderPopout() {
    if (!_hostEl) return;
    var popout = _hostEl.querySelector('[data-section="popout"]');
    if (!popout) return;
    if (!_fallbackPopoutFor) {
      popout.hidden = true;
      popout.innerHTML = '';
      _detachPopoutFromRow(popout);
      return;
    }
    // Look up the config summary (presets + customs).
    var presets = (_configs && _configs.presets) || {};
    var customs = (_configs && _configs.customs) || [];
    var summary = null;
    Object.keys(presets).forEach(function (k) {
      if (presets[k] && presets[k].name === _fallbackPopoutFor) summary = presets[k];
    });
    if (!summary) {
      summary = customs.find(function (c) { return c.name === _fallbackPopoutFor; });
    }
    if (!summary) {
      _fallbackPopoutFor = null;
      popout.hidden = true;
      popout.innerHTML = '';
      _detachPopoutFromRow(popout);
      return;
    }

    // Three sections, fixed shape regardless of adversarial toggle:
    //   large — 4 rows (gear4.depth: 1 primary + 3 fallbacks)
    //   small — 2 rows (utility: 1 primary + 1 fallback)
    //   image — 2 rows (image_generation: 1 primary + 1 fallback)
    // big2 (gear4.breadth) is intentionally not surfaced here — the spec
    // is one large chain, and the diversity-vs-fallback distinction lives
    // on the card body (BIG 1 / BIG 2 rows) rather than the popout.
    var sections = [
      _popoutSlotHTML('large', summary.big1, summary.big1_fallback),
      _popoutSlotHTML('small', summary.small, summary.small_fallback),
      _popoutSlotHTML('image', summary.image_generation, summary.image_generation_fallback),
    ];

    popout.hidden = false;
    popout.innerHTML = ''
      + '<header class="ora-models-popout-header">'
      +   '<span class="ora-models-popout-title">Fallback chains · '
      +     '<strong>' + _esc(summary.name) + '</strong></span>'
      +   '<button type="button" class="ora-models-popout-close" aria-label="Close">×</button>'
      + '</header>'
      + '<div class="ora-models-popout-body">'
      +   '<p class="ora-models-popout-hint">'
      +     'Tried in order until one responds. Free chains run deeper because '
      +     'rate-limit churn cycles through them fast.'
      +   '</p>'
      +   sections.join('')
      + '</div>';

    popout.querySelector('.ora-models-popout-close')
      .addEventListener('click', function () {
        _fallbackPopoutFor = null;
        _renderPopout();
        _renderPresets();
        _renderCustom();
      });

    _attachPopoutToActiveCard(popout);
  }

  // Bifold-wallet positioning: when a popout is open, move the popout
  // element out of the pane root and into the preset/custom row, right
  // after the active card. The row reflows via CSS (slim siblings, wide
  // active + popout pair). Closing detaches it back to the pane root.
  function _attachPopoutToActiveCard(popout) {
    if (!_hostEl || !_fallbackPopoutFor) return;
    var activeCard = _hostEl.querySelector(
      '.ora-models-card[data-config-name="' + _cssEscape(_fallbackPopoutFor) + '"]'
    );
    if (!activeCard) return;
    var row = activeCard.parentElement;
    if (!row) return;

    // Clear any stale popout-open state on other rows / cards
    Array.from(_hostEl.querySelectorAll('.ora-models-row--popout-open'))
      .forEach(function (r) {
        if (r !== row) r.classList.remove('ora-models-row--popout-open');
      });
    Array.from(_hostEl.querySelectorAll('.ora-models-card-popout-open'))
      .forEach(function (c) {
        if (c !== activeCard) c.classList.remove('ora-models-card-popout-open');
      });

    row.classList.add('ora-models-row--popout-open');
    activeCard.classList.add('ora-models-card-popout-open');
    if (popout.parentElement !== row || activeCard.nextElementSibling !== popout) {
      activeCard.insertAdjacentElement('afterend', popout);
    }
  }

  function _detachPopoutFromRow(popout) {
    if (!_hostEl) return;
    Array.from(_hostEl.querySelectorAll('.ora-models-row--popout-open'))
      .forEach(function (r) { r.classList.remove('ora-models-row--popout-open'); });
    Array.from(_hostEl.querySelectorAll('.ora-models-card-popout-open'))
      .forEach(function (c) { c.classList.remove('ora-models-card-popout-open'); });
    // Re-park popout under the pane root so a future open doesn't have to
    // hunt for it across the DOM.
    var pane = _hostEl.querySelector('.ora-models-pane');
    if (pane && popout.parentElement !== pane) {
      pane.appendChild(popout);
    }
  }

  function _cssEscape(s) {
    if (typeof CSS !== 'undefined' && CSS.escape) return CSS.escape(s);
    return String(s).replace(/(["\\'\\]])/g, '\\\\$1');
  }

  function _popoutSlotHTML(label, primary, fallbackList) {
    fallbackList = fallbackList || [];
    var registry = (_registry && _registry.models) || {};
    var rows = [];
    if (primary) {
      rows.push(_popoutRowHTML(primary, registry[primary], 'primary'));
    }
    fallbackList.forEach(function (fb, i) {
      rows.push(_popoutRowHTML(fb, registry[fb], 'fallback ' + (i + 1)));
    });
    if (!rows.length) {
      rows.push('<div class="ora-models-popout-empty">No entries — slot is empty.</div>');
    }
    return ''
      + '<div class="ora-models-popout-slot">'
      +   '<h4 class="ora-models-popout-slot-label">' + _esc(label) + '</h4>'
      +   rows.join('')
      + '</div>';
  }

  function _popoutRowHTML(modelId, model, rank) {
    var displayName = (model && model.display_name) || modelId;
    var chips = model ? _modelChipsHTML(model) : '';
    var meta = model ? _compactMetaHTML(model) : '';
    return ''
      + '<div class="ora-models-popout-row">'
      +   '<span class="ora-models-popout-rank">' + _esc(rank) + '</span>'
      +   '<span class="ora-models-popout-name" title="' + _esc(modelId) + '">'
      +     _esc(displayName) + '</span>'
      +   chips
      +   '<span class="ora-models-popout-meta">' + meta + '</span>'
      + '</div>';
  }

  // ── Local hardware section ──────────────────────────────────────────────

  function _renderHardware() {
    if (!_hostEl) return;
    var section = _hostEl.querySelector('[data-section="hardware"]');
    if (!section) return;
    var h = _hardware;
    if (!h) {
      section.innerHTML = '<p class="ora-models-placeholder">'
        + 'Local model data unavailable (/models endpoint failed).</p>';
      return;
    }
    var locals = h.local_models || [];
    var totalRam = locals.reduce(function (sum, m) {
      return sum + (m.ram_gb || 0);
    }, 0);
    var headroom = (h.available_budget_gb || 0) - totalRam;

    var rows = locals.map(function (m) {
      var size = m.ram_gb != null ? m.ram_gb + ' GB' : '?';
      var fits = (m.ram_gb || 0) <= (h.available_budget_gb || Infinity);
      return ''
        + '<li class="ora-models-hw-row">'
        +   '<span class="ora-models-hw-name">' + _esc(m.display_name || m.id) + '</span>'
        +   '<span class="ora-models-hw-size">' + _esc(size) + '</span>'
        +   '<span class="ora-models-hw-fit'
        +     (fits ? ' ora-models-hw-fit-ok' : ' ora-models-hw-fit-no') + '">'
        +     (fits ? '✓ fits' : '✗ too large')
        +   '</span>'
        + '</li>';
    });

    section.innerHTML = ''
      + '<header class="ora-models-section-header">'
      +   '<h3>Local model hardware</h3>'
      +   '<span class="ora-models-section-hint">'
      +     'Local models run on your hardware; capability and speed are bounded '
      +     'by available RAM.'
      +   '</span>'
      + '</header>'
      + '<div class="ora-models-hw-body">'
      +   '<div class="ora-models-hw-totals">'
      +     '<div><span class="ora-models-hw-label">System RAM</span>'
      +       '<span class="ora-models-hw-value">' + _esc(String(h.system_ram_gb || '?')) + ' GB</span></div>'
      +     '<div><span class="ora-models-hw-label">Overhead</span>'
      +       '<span class="ora-models-hw-value">' + _esc(String(h.overhead_gb || '?')) + ' GB</span></div>'
      +     '<div><span class="ora-models-hw-label">Available</span>'
      +       '<span class="ora-models-hw-value">' + _esc(String(h.available_budget_gb || '?')) + ' GB</span></div>'
      +     '<div><span class="ora-models-hw-label">Installed total</span>'
      +       '<span class="ora-models-hw-value">' + _esc(totalRam.toFixed(0)) + ' GB</span></div>'
      +     '<div><span class="ora-models-hw-label">Headroom</span>'
      +       '<span class="ora-models-hw-value' + (headroom < 0 ? ' ora-models-hw-headroom-low' : '') + '">'
      +         _esc(headroom.toFixed(0)) + ' GB</span></div>'
      +   '</div>'
      +   (locals.length
        ? '<ul class="ora-models-hw-list">' + rows.join('') + '</ul>'
        : '<p class="ora-models-placeholder">No local models installed.</p>')
      + '</div>';
  }

  // (No more sections needing placeholder skeleton — step 13 was the last.)
  function _renderRemainingSkeleton() {}

  // ── utilities ───────────────────────────────────────────────────────────

  function _esc(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // ── expose ───────────────────────────────────────────────────────────────

  root.OraModelsPane = {
    init: init,
    destroy: destroy,
  };
})(typeof window !== 'undefined' ? window : this);
