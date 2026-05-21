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
    free: false,
    open_weights: false,
    pick: false,
    intelligence_pct: 0,    // 0 = show all; 50 = show top 50%; 100 = show nothing
    search: '',
    sort_by: 'alpha_desc',  // alphabetical descending — newest releases bubble up by version-string convention
  };

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
      vision: false, free: false, open_weights: false, pick: false,
      intelligence_pct: 0, search: '', sort_by: 'alpha_desc',
    };
    _expandedVendors = new Set();
    _activeSlotPick = null;
    _fallbackPopoutFor = null;
    _hardware = null;
  }

  // ── data load ───────────────────────────────────────────────────────────

  function _loadAll() {
    Promise.all([
      fetch('/api/model-registry').then(_json),
      fetch('/api/model-registry/picks').then(_json),
      fetch('/api/configurations').then(_json),
      fetch('/models').then(_json).catch(function () { return null; }),
    ]).then(function (resp) {
      _registry = resp[0] || {};
      var picksPayload = resp[1] || {};
      _picksSet = new Set(picksPayload.picks || []);
      _configs = resp[2] || {presets: {}, customs: [],
                             active_name: '', active_toggles: {}};
      _hardware = resp[3] || null;
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

  // Slot pick: clicking a slot row sets _activeSlotPick. The next
  // inventory row click commits the pick. Clicking the same slot
  // again (or pressing Escape) cancels.
  function _wireSlotPickHandlers(section) {
    Array.from(section.querySelectorAll('[data-pick-slot]')).forEach(function (row) {
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
    return ''
      + '<div class="ora-models-card ora-models-card-preset'
      +   (isActive ? ' ora-models-card-active' : '') + '"'
      +   ' data-preset="' + presetName + '"'
      +   ' data-config-name="' + _esc(summary.name) + '">'
      +   '<header class="ora-models-card-header">'
      +     '<span class="ora-models-card-title">' + _esc(label) + '</span>'
      +     (isActive ? '<span class="ora-models-card-active-flag">active</span>' : '')
      +   '</header>'
      +   '<div class="ora-models-card-body">'
      +     _slotRowHTML('big 1', summary.big1, {omitCost: omitCost, configName: summary.name})
      +     (adversarial
        ? _slotRowHTML('big 2', summary.big2, {omitCost: omitCost, configName: summary.name})
        : '')
      +     _slotRowHTML('small', summary.small, {omitCost: omitCost, configName: summary.name})
      +     _expandSlotsHTML(summary, {omitCost: omitCost})
      +   '</div>'
      +   '<div class="ora-models-card-actions">'
      +     '<button type="button" class="ora-models-card-btn" data-action="more">'
      +       _moreLabelFor(summary.name) + '</button>'
      +     '<button type="button" class="ora-models-card-btn" data-action="customize">Customize</button>'
      +   '</div>'
      +   '<div class="ora-models-card-footer">'
      +     chips
      +   '</div>'
      + '</div>';
  }

  // Renders the 4 extra rows below big 1 / big 2 / small when the
  // card is in the expanded state (▸ More clicked). Visual fallback +
  // consolidator + verifier + formatter — each its own slot-pickable
  // row that breaks the default "post-analysis inherits big 1" rule.
  function _expandSlotsHTML(summary, opts) {
    if (_fallbackPopoutFor !== summary.name) return '';
    var c = {configName: summary.name, omitCost: !!(opts && opts.omitCost)};
    return ''
      + '<div class="ora-models-card-expand">'
      +   _slotRowHTML('visual', summary.visual, c)
      +   _slotRowHTML('consolidator', summary.consolidator, c)
      +   _slotRowHTML('verifier', summary.verifier, c)
      +   _slotRowHTML('formatter', summary.formatter, c)
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
    var clickable = !!configName;  // only rows with a knowable config can be picked
    var classes = 'ora-models-slot-row';
    if (isActiveSlot) classes += ' ora-models-slot-row-picking';
    if (clickable) classes += ' ora-models-slot-row-clickable';

    if (!modelId) {
      return '<div class="' + classes + ' ora-models-slot-empty"'
        + (clickable ? ' data-pick-slot="' + _esc(label) + '"' +
                       ' data-pick-config="' + _esc(configName) + '"' : '')
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
    return '<div class="' + classes + '"'
      + (clickable ? ' data-pick-slot="' + _esc(label) + '"' +
                     ' data-pick-config="' + _esc(configName) + '"' : '')
      + (isDeprecated ? ' title="This model is no longer in the registry. '
                       + 'Pick a replacement."' : '')
      + '>'
      + '<span class="ora-models-slot-label">' + _esc(label) + '</span>'
      + '<span class="ora-models-slot-value" title="' + _esc(modelId) + '">'
      +   _esc(_shortenModelId(modelId))
      +   (isPick ? '<span class="ora-models-pick-chip">PICK</span>' : '')
      +   (isDeprecated ? '<span class="ora-models-deprecated-chip">DEPRECATED</span>' : '')
      +   (meta ? '<span class="ora-models-slot-meta">' + meta + '</span>' : '')
      + '</span>'
      + '</div>';
  }

  // Compact meta line used in BOTH card slot rows and inventory rows.
  // Format: int X · $Y/M · Z t/s — parts dropped when underlying
  // data is null/absent. One intelligence number, scale-normalized
  // so AA and Arena ELO are presented on the same 0-100-ish range
  // (user feedback: don't mix scale labels in the display).
  // opts.omitCost: True for Free-preset cards where cost is always $0.
  function _compactMetaHTML(model, opts) {
    opts = opts || {};
    var parts = [];
    var intel = _normalizedIntelligence(model);
    if (intel != null) {
      parts.push('int ' + intel.toFixed(intel < 10 ? 1 : 0));
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
    return bits.length
      ? '<span class="ora-models-toggle-chip">' + bits.join(' · ') + '</span>'
      : '<span class="ora-models-toggle-chip ora-models-toggle-chip-quiet">—</span>';
  }

  function _shortenModelId(id) {
    // Vendor/model → just the model side for card display. The full
    // id is on the title attr for hover.
    if (!id) return '';
    var slash = id.lastIndexOf('/');
    return slash >= 0 ? id.substring(slash + 1) : id;
  }

  function _activateConfig(name) {
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
    return ''
      + '<div class="ora-models-card ora-models-card-custom'
      +   (isActive ? ' ora-models-card-active' : '') + '"'
      +   ' data-config-name="' + _esc(summary.name) + '">'
      +   '<header class="ora-models-card-header">'
      +     '<span class="ora-models-card-title">' + _esc(summary.name) + '</span>'
      +     (isActive ? '<span class="ora-models-card-active-flag">active</span>' : '')
      +   '</header>'
      +   '<div class="ora-models-card-body">'
      +     _slotRowHTML('big 1', summary.big1, {configName: summary.name})
      +     (adversarial
        ? _slotRowHTML('big 2', summary.big2, {configName: summary.name})
        : '')
      +     _slotRowHTML('small', summary.small, {configName: summary.name})
      +     _expandSlotsHTML(summary, {})
      +   '</div>'
      +   '<div class="ora-models-card-actions">'
      +     '<button type="button" class="ora-models-card-btn" data-action="more">'
      +       _moreLabelFor(summary.name) + '</button>'
      +     '<button type="button" class="ora-models-card-btn" data-action="customize">'
      +       'Customize</button>'
      +     '<button type="button" class="ora-models-card-btn ora-models-card-btn-danger"'
      +       ' data-action="delete" title="Delete">×</button>'
      +   '</div>'
      +   '<div class="ora-models-card-footer">'
      +     _toggleChips(summary.toggles)
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
    var allModels = Object.values(models);

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
    var anyFilterActive = _filters.vision || _filters.free
                          || _filters.open_weights || _filters.pick
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
    var columns = _distributeVendorsToColumns(groupsForDisplay);

    var totalCount = allModels.length;
    var visibleCount = groupsForDisplay.reduce(function (sum, g) {
      return sum + g.models.length;
    }, 0);

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
      +   '</span>'
      + '</header>'
      + pickBanner
      + '<div class="ora-models-inventory-controls">'
      +   _filterChipsHTML()
      +   _sortSelectHTML()
      +   _sliderHTML()
      +   _searchInputHTML()
      + '</div>'
      + '<div class="ora-models-row ora-models-inventory-row">'
      +   columns.map(_columnHTML).join('')
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
    if (_filters.vision && model.vision_capable !== true) return false;
    if (_filters.free) {
      var isFree = (model.id || '').endsWith(':free')
        || model.is_free === true;
      if (!isFree) return false;
    }
    if (_filters.open_weights && model.is_open_weights !== true) return false;
    if (_filters.pick && !(_picksSet && _picksSet.has(model.id))) return false;
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

  function _vendorOf(model) {
    var id = model.id || '';
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
          if (ac == null) ac = Infinity;
          if (bc == null) bc = Infinity;
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

  function _modelRowHTML(model) {
    // Single-line inventory row: name + chips + meta, all inline.
    // Meta is the same compact summary used in card slot rows.
    var displayName = model.display_name || model.id;
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
    if (model.is_open_weights === true) {
      chips.push('<span class="ora-models-chip">open</span>');
    }
    if ((model.id || '').endsWith(':free')) {
      chips.push('<span class="ora-models-chip ora-models-chip-free">:free</span>');
    }
    return chips.join('');
  }

  function _filterChipsHTML() {
    var chips = [
      {key: 'vision', label: 'Vision'},
      {key: 'free', label: 'Free'},
      {key: 'open_weights', label: 'Open-weights'},
      {key: 'pick', label: 'PICK'},
    ];
    return '<div class="ora-models-filter-chips">'
      + chips.map(function (c) {
          var on = _filters[c.key];
          return '<label class="ora-models-filter-chip' + (on ? ' ora-models-filter-chip-on' : '') + '">'
            + '<input type="checkbox" data-filter="' + c.key + '"' + (on ? ' checked' : '') + '>'
            + _esc(c.label)
            + '</label>';
        }).join('')
      + '</div>';
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
    var sortEl = section.querySelector('.ora-models-sort-select');
    if (sortEl) {
      sortEl.addEventListener('change', function () {
        _filters.sort_by = sortEl.value;
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
      return;
    }

    var adversarial = !!(summary.toggles && summary.toggles.adversarial_diversity);
    var sections = [
      _popoutSlotHTML('big 1', summary.big1, summary.big1_fallback),
      adversarial ? _popoutSlotHTML('big 2', summary.big2, summary.big2_fallback) : '',
      _popoutSlotHTML('small', summary.small, summary.small_fallback),
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
