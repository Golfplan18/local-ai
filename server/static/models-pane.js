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
  };

  // ── public API ───────────────────────────────────────────────────────────

  function init(host) {
    if (!host) return;
    destroy();
    _hostEl = host;
    _hostEl.classList.add('ora-models-pane-host');
    _hostEl.innerHTML = ''
      + '<div class="ora-models-pane">'
      +   '<section class="ora-models-header" data-section="header">'
      +     '<p class="ora-models-loading">Loading model registry…</p>'
      +   '</section>'
      +   '<section class="ora-models-presets" data-section="presets"></section>'
      +   '<section class="ora-models-custom" data-section="custom"></section>'
      +   '<section class="ora-models-inventory" data-section="inventory"></section>'
      +   '<section class="ora-models-hardware" data-section="hardware"></section>'
      + '</div>';

    _loadAll();
  }

  function destroy() {
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
      intelligence_pct: 0, search: '',
    };
  }

  // ── data load ───────────────────────────────────────────────────────────

  function _loadAll() {
    Promise.all([
      fetch('/api/model-registry').then(_json),
      fetch('/api/model-registry/picks').then(_json),
      fetch('/api/configurations').then(_json),
    ]).then(function (resp) {
      _registry = resp[0] || {};
      var picksPayload = resp[1] || {};
      _picksSet = new Set(picksPayload.picks || []);
      _configs = resp[2] || {presets: {}, customs: [],
                             active_name: '', active_toggles: {}};
      _renderHeader();
      _renderPresets();
      _renderCustom();
      _renderInventory();
      _renderRemainingSkeleton();
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

    header.innerHTML = ''
      + '<div class="ora-models-header-strip">'
      +   '<div class="ora-models-active">'
      +     '<span class="ora-models-active-label">Active configuration:</span> '
      +     '<strong class="ora-models-active-name">' + _esc(name) + '</strong>'
      +     (missing
        ? ' <span class="ora-models-warn">(missing — pick another)</span>'
        : '')
      +   '</div>'
      +   '<div class="ora-models-toggles">'
      +     _toggleHTML('adversarial_diversity', adv,
                       'Adversarial Diversity',
                       'Two workhorse models run in parallel and cross-check '
                       + 'each other. Doubles cost; catches blind spots a '
                       + 'single model would miss.')
      +     _toggleHTML('vision_only', vis,
                       'Vision-capable only',
                       'Restrict picks to models that can see images directly. '
                       + 'Off lets text-only models in, with a per-slot visual '
                       + 'fallback that converts images to text descriptions.')
      +   '</div>'
      + '</div>';

    // Wire change handlers
    Array.from(header.querySelectorAll('.ora-models-toggle input')).forEach(function (el) {
      el.addEventListener('change', function () {
        _setToggle(el.dataset.toggle, el.checked);
      });
    });
  }

  function _toggleHTML(name, checked, label, helpText) {
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
      var presetName = card.dataset.preset;
      var configName = card.dataset.configName;
      if (!configName) return;
      card.addEventListener('click', function (evt) {
        // Ignore clicks on buttons inside the card
        if (evt.target.closest('button')) return;
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
          // Step 10 wires the fallback popout. For now, a console hint
          // so reviewers can confirm the button is reachable.
          console.info('[models-pane] More clicked for ' + configName
                       + ' (popout wires in step 10)');
        });
      }
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
      +     _slotRowHTML('big 1', summary.big1)
      +     _slotRowHTML('big 2', summary.big2)
      +     _slotRowHTML('small', summary.small)
      +   '</div>'
      +   '<div class="ora-models-card-actions">'
      +     '<button type="button" class="ora-models-card-btn" data-action="more">▸ More</button>'
      +     '<button type="button" class="ora-models-card-btn" data-action="customize">Customize</button>'
      +   '</div>'
      +   '<div class="ora-models-card-footer">'
      +     chips
      +   '</div>'
      + '</div>';
  }

  function _slotRowHTML(label, modelId) {
    if (!modelId) {
      return '<div class="ora-models-slot-row ora-models-slot-empty">'
        + '<span class="ora-models-slot-label">' + _esc(label) + '</span>'
        + '<span class="ora-models-slot-value">—</span>'
        + '</div>';
    }
    var isPick = _picksSet && _picksSet.has(modelId);
    return '<div class="ora-models-slot-row">'
      + '<span class="ora-models-slot-label">' + _esc(label) + '</span>'
      + '<span class="ora-models-slot-value" title="' + _esc(modelId) + '">'
      +   _esc(_shortenModelId(modelId))
      +   (isPick ? '<span class="ora-models-pick-chip">PICK</span>' : '')
      + '</span>'
      + '</div>';
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

    // Custom-New is a pure workspace for starting a new configuration.
    // It NEVER carries the active green flag — that lives only on
    // saved cards (presets or customs in the Previous grid). The rule
    // is "exactly one green box, ever, around a saved configuration."
    // Mirroring the active custom into Custom-New violated that rule.
    var newCardHTML = _customNewEmptyHTML();

    // Previous grid: 3 columns × however many rows of customs. Each
    // card is a smaller version of the preset card with click-to-
    // activate + Customize + delete affordances. A trailing "+ New"
    // card at the end opens the create-blank flow.
    var previousCards = customs.map(function (c) {
      return _customCardHTML(c, c.name === activeName);
    });
    previousCards.push(_newConfigCardHTML());

    section.innerHTML = ''
      + '<header class="ora-models-section-header">'
      +   '<h3>Custom configurations</h3>'
      +   '<span class="ora-models-section-hint">'
      +     'Custom-New on the left is your active custom; the grid on the right '
      +     'holds your saved configurations. Click any card to activate.'
      +   '</span>'
      + '</header>'
      + '<div class="ora-models-row ora-models-custom-row">'
      +   '<div class="ora-models-custom-new">' + newCardHTML + '</div>'
      +   '<div class="ora-models-custom-previous">'
      +     '<div class="ora-models-previous-grid">'
      +       previousCards.join('')
      +     '</div>'
      +   '</div>'
      + '</div>';

    // Wire interactions for previous-grid cards
    var grid = section.querySelector('.ora-models-previous-grid');
    Array.from(grid.querySelectorAll('.ora-models-card-custom')).forEach(function (card) {
      var configName = card.dataset.configName;
      card.addEventListener('click', function (evt) {
        if (evt.target.closest('button')) return;
        _activateConfig(configName);
      });
      var customizeBtn = card.querySelector('[data-action="customize"]');
      if (customizeBtn) {
        customizeBtn.addEventListener('click', function () { _customizeFrom(configName); });
      }
      var deleteBtn = card.querySelector('[data-action="delete"]');
      if (deleteBtn) {
        deleteBtn.addEventListener('click', function () { _deleteCustom(configName); });
      }
    });
    var newBtn = grid.querySelector('[data-action="new"]');
    if (newBtn) {
      newBtn.addEventListener('click', _createNew);
    }
  }

  function _customNewEmptyHTML() {
    return ''
      + '<div class="ora-models-card ora-models-card-custom-new ora-models-card-empty-state">'
      +   '<header class="ora-models-card-header">'
      +     '<span class="ora-models-card-title">Custom new</span>'
      +     '<span class="ora-models-incomplete-flag">empty</span>'
      +   '</header>'
      +   '<div class="ora-models-card-body">'
      +     '<p class="ora-models-empty-msg">'
      +       'No custom configuration active. Click ▾ + New on the right '
      +       'to start a blank one, or Customize on any preset / saved '
      +       'card to fork it.'
      +     '</p>'
      +   '</div>'
      + '</div>';
  }

  function _customCardHTML(summary, isActive) {
    return ''
      + '<div class="ora-models-card ora-models-card-custom'
      +   (isActive ? ' ora-models-card-active' : '') + '"'
      +   ' data-config-name="' + _esc(summary.name) + '">'
      +   '<header class="ora-models-card-header">'
      +     '<span class="ora-models-card-title">' + _esc(summary.name) + '</span>'
      +     (isActive ? '<span class="ora-models-card-active-flag">active</span>' : '')
      +   '</header>'
      +   '<div class="ora-models-card-body">'
      +     _slotRowHTML('big 1', summary.big1)
      +     _slotRowHTML('big 2', summary.big2)
      +     _slotRowHTML('small', summary.small)
      +   '</div>'
      +   '<div class="ora-models-card-actions">'
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

    var filtered = allModels.filter(function (m) {
      return _matchesFilters(m, rankedKeptIds);
    });

    var grouped = _groupByVendor(filtered);
    var columns = _distributeVendorsToColumns(grouped);

    var visibleCount = filtered.length;
    var totalCount = allModels.length;

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
      + '<div class="ora-models-inventory-controls">'
      +   _filterChipsHTML()
      +   _sliderHTML()
      +   _searchInputHTML()
      + '</div>'
      + '<div class="ora-models-row ora-models-inventory-row">'
      +   columns.map(_columnHTML).join('')
      + '</div>';

    _wireInventoryControls(section);
  }

  function _combinedScore(model) {
    // AA Index is 0-100; Arena ELO is typically 800-1500. Normalise
    // both to 0-1 so the slider works against either-or coverage.
    if (model.aa_intelligence_index != null) {
      return Math.max(0, Math.min(1, model.aa_intelligence_index / 100));
    }
    if (model.intelligence_score != null) {
      return Math.max(0, Math.min(1, (model.intelligence_score - 800) / 700));
    }
    return null;
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
    // Sort each vendor's models alphabetical-descending (per the
    // user-locked decision — most recent releases tend to bubble up
    // because their version numbers come last alphabetically).
    Object.keys(groups).forEach(function (v) {
      groups[v].sort(function (a, b) {
        var ai = (a.id || '').toLowerCase();
        var bi = (b.id || '').toLowerCase();
        if (ai > bi) return -1;
        if (ai < bi) return 1;
        return 0;
      });
    });
    return groups;
  }

  function _distributeVendorsToColumns(grouped) {
    // 4 equal columns. Local is always pinned to the top of column 1.
    // Remaining vendors are sorted alphabetically and split across
    // columns in alphabetical-by-column order (column 1 carries the
    // first chunk of names, column 2 the next chunk, etc.) so the
    // user's read-down-then-right pattern works.
    var columns = [[], [], [], []];
    if (grouped.Local && grouped.Local.length) {
      columns[0].push({vendor: 'Local', models: grouped.Local});
    }
    var otherVendors = Object.keys(grouped)
      .filter(function (v) { return v !== 'Local'; })
      .sort();
    var perCol = Math.ceil(otherVendors.length / 4);
    otherVendors.forEach(function (vendor, i) {
      var colIdx = Math.min(3, Math.floor(i / perCol));
      columns[colIdx].push({vendor: vendor, models: grouped[vendor]});
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
    return ''
      + '<div class="ora-models-vendor-block">'
      +   '<h4 class="ora-models-vendor-name">' + _esc(group.vendor)
      +     ' <span class="ora-models-vendor-count">(' + group.models.length + ')</span>'
      +   '</h4>'
      +   '<ul class="ora-models-model-list">'
      +     group.models.map(_modelRowHTML).join('')
      +   '</ul>'
      + '</div>';
  }

  function _modelRowHTML(model) {
    var displayName = model.display_name || model.id;
    var chips = _modelChipsHTML(model);
    return ''
      + '<li class="ora-models-model-row" title="' + _esc(model.id) + '">'
      +   '<div class="ora-models-model-name">' + _esc(displayName) + '</div>'
      +   '<div class="ora-models-model-meta">'
      +     _modelMetaHTML(model)
      +   '</div>'
      +   (chips ? '<div class="ora-models-model-chips">' + chips + '</div>' : '')
      + '</li>';
  }

  function _modelMetaHTML(model) {
    var parts = [];
    if (model.aa_intelligence_index != null) {
      parts.push('AA ' + model.aa_intelligence_index.toFixed(1));
    } else if (model.intelligence_score != null) {
      parts.push('Arena ' + model.intelligence_score.toFixed(0));
    }
    var pricing = model.pricing || {};
    if (pricing.input_per_token != null || pricing.output_per_token != null) {
      var ip = pricing.input_per_token != null
        ? '$' + (pricing.input_per_token * 1e6).toFixed(2) : '?';
      var op = pricing.output_per_token != null
        ? '$' + (pricing.output_per_token * 1e6).toFixed(2) : '?';
      parts.push(ip + '/' + op + '/M');
    }
    if (model.output_tokens_per_second != null) {
      parts.push(model.output_tokens_per_second.toFixed(0) + ' t/s');
    }
    if (model.latency_ttft_seconds != null) {
      parts.push(model.latency_ttft_seconds.toFixed(1) + 's TTFT');
    }
    return parts.join(' · ');
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
  }

  // ── placeholder sections (filled by subsequent commits) ─────────────────

  function _renderRemainingSkeleton() {
    if (!_hostEl) return;
    var sections = [
      ['hardware',
       'Local model hardware analysis (commit step 13).'],
    ];
    sections.forEach(function (s) {
      var el = _hostEl.querySelector('[data-section="' + s[0] + '"]');
      if (el) {
        el.innerHTML = '<p class="ora-models-placeholder">' + _esc(s[1]) + '</p>';
      }
    });
  }

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
