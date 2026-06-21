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
  var _lastSyncedActiveConfig = null; // active-config name we last vision-synced
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
  var FAST_MIN_TOKENS_PER_SECOND = 80;

  // Inventory filter + sort state. Persists across renders within a
  // single mount; reset to defaults on every fresh init().
  var _filters = {
    vision: false,
    free_filter: 'any',     // 'any' (default) | 'only' (only free) | 'hide' (drop free) — was previously two mutually-exclusive chips
    pick: false,
    intelligence_pct: 0,    // 0 = show all; 50 = show top 50%; 100 = show nothing
    search: '',
    sort_by: 'intelligence_desc',  // highest-intelligence first so the strongest models surface by default (Phase 5; was 'alpha_desc')
    category: 'chat',       // inventory category. Chat-only since 2026-06-11: image/video model selection lives on the Visual tab (routing-config slots chain), not in chat configurations.
    grouping: 'vendor',     // 'vendor' (default — vendor blocks, collapsible) or 'flat' (no grouping, one sorted list)
    include_unsized: true,  // during a sized slot pick, SHOW models with no size_bucket by default. 392/422 cloud flagships ship ids without a parameter count (gpt-5.4, claude-opus-4-8, gemini-3.5-flash), so a strict large/small gate would hide nearly the whole catalog — "unknown size" is not "wrong size". The banner notes when unsized models are shown; family classification fills real buckets going forward.
  };

  var CATEGORY_OPTIONS = [
    {id: 'chat',             label: 'Chat'},
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

  function _setActiveSlotPick(pick) {
    _activeSlotPick = pick;
    // Open Local once when a pick starts so installed local models are
    // discoverable. After that, respect the user's collapse click.
    if (pick && _slotPickInventoryCategory(pick) === 'chat') {
      _expandedVendors.add('Local');
    }
  }

  // Right-side fallback popout state. ▸ More click on any card sets
  // _fallbackPopoutFor = <configName>. Close button or Escape clears.
  var _fallbackPopoutFor = null;

  // Loosening-footnote expansion state. Clicking the "N picks
  // loosened" footnote on a preset card sets _looseningOpenFor =
  // <configName> and the card grows a per-cell detail list below the
  // footnote. Clicking again (or expanding another card's footnote)
  // collapses it.
  var _looseningOpenFor = null;

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
      _setActiveSlotPick(null);
      _renderHeader();
      _renderPresets();
      _renderCustom();
      _renderInventory();
    } else if (_looseningOpenFor) {
      _looseningOpenFor = null;
      _renderPresets();
      _renderPopout();
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
      +   '<section class="ora-models-maintenance" data-section="maintenance"></section>'
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
      intelligence_pct: 0, search: '', sort_by: 'intelligence_desc',
      category: 'chat', grouping: 'vendor', include_unsized: false,
    };
    _expandedVendors = new Set();
    _setActiveSlotPick(null);
    _fallbackPopoutFor = null;
    _hardware = null;
  }

  // ── data load ───────────────────────────────────────────────────────────

  function _loadAll() {
    var scrollState = _capturePaneScroll();
    // categories=all is kept for forward-compat: the registry is
    // chat-only today (media entries left 2026-06-11 with the
    // image_generation slot), and the inventory renders whatever
    // categories the response carries.
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
      // Vision-capable toggle ONLY on the first load of this session
      // (or after the active config genuinely changes). Re-applying it
      // on every _loadAll wiped the user's manual "turn off Vision
      // filter" click after each slot pick — picking a local then
      // committing would re-hide the local rows immediately because
      // the next render forced Vision back on. Track the active
      // config so we only re-sync when it actually changes.
      var activeToggles = _configs.active_toggles || {};
      var activeName = _configs.active_name || '';
      if (_lastSyncedActiveConfig !== activeName) {
        _filters.vision = !!activeToggles.vision_only;
        _lastSyncedActiveConfig = activeName;
      }
      _renderHeader();
      _renderPresets();
      _renderCustom();
      _renderInventory();
      _renderPopout();
      _renderHardware();
      _renderMaintenance();
      _renderRemainingSkeleton();
      _restorePaneScroll(scrollState);
      _maybeAutoRefresh();
    }).catch(function (err) {
      _showHeaderError(err);
    });
  }

  // Refresh just the active-config indicator + toggles without
  // refetching the registry. Cheap; used after a toggle change or an
  // active-card switch. Hardware re-render included because the
  // IN USE BY ACTIVE / IN ACTIVE CONFIG calc walks active_name.
  function _refreshActive() {
    var scrollState = _capturePaneScroll();
    fetch('/api/configurations').then(_json).then(function (configs) {
      _configs = configs || _configs;
      _renderHeader();
      _renderPresets();
      _renderCustom();
      _renderHardware();
      _restorePaneScroll(scrollState);
    });
  }

  function _json(r) { return r.json(); }

  function _scrollParentForModelsPane() {
    if (!_hostEl) return null;
    var el = _hostEl.parentElement;
    while (el && el !== document.body && el !== document.documentElement) {
      var style = window.getComputedStyle ? window.getComputedStyle(el) : null;
      var overflowY = style ? style.overflowY : '';
      if ((overflowY === 'auto' || overflowY === 'scroll')
          && el.scrollHeight > el.clientHeight) {
        return el;
      }
      el = el.parentElement;
    }
    return null;
  }

  function _capturePaneScroll() {
    var scrollEl = _scrollParentForModelsPane();
    var customRow = _hostEl && _hostEl.querySelector('.ora-models-custom-row');
    return {
      scrollEl: scrollEl,
      scrollTop: scrollEl ? scrollEl.scrollTop : null,
      customScrollTop: customRow ? customRow.scrollTop : null,
    };
  }

  function _restorePaneScroll(state) {
    if (!state) return;
    if (state.scrollEl && state.scrollTop != null) {
      state.scrollEl.scrollTop = state.scrollTop;
    }
    var customRow = _hostEl && _hostEl.querySelector('.ora-models-custom-row');
    if (customRow && state.customScrollTop != null) {
      customRow.scrollTop = state.customScrollTop;
    }
    if (typeof requestAnimationFrame === 'function') {
      requestAnimationFrame(function () {
        if (state.scrollEl && state.scrollTop != null) {
          state.scrollEl.scrollTop = state.scrollTop;
        }
        var row = _hostEl && _hostEl.querySelector('.ora-models-custom-row');
        if (row && state.customScrollTop != null) {
          row.scrollTop = state.customScrollTop;
        }
      });
    }
  }

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
      +   '<div class="ora-models-refresh-wrap" title="Re-sync the model registry (OpenRouter + AA + LiteLLM) and rebuild the picker\'s model catalog from it, so the two stay in lockstep (~20-40s, no tokens). Auto-runs on pane open when the data is more than 24h old.">'
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
    // Park the popout back at the pane root before wiping the section's
    // innerHTML — otherwise the bifold-wallet attach has the popout
    // living INSIDE this section's row and we'd destroy it. _renderPopout
    // (called later in _loadAll) re-attaches once the rebuilt row exists.
    _parkPopoutAtPaneRoot();
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
          var scrollState = _capturePaneScroll();
          // Toggle: click ▸ More opens; click ▾ Less closes.
          _fallbackPopoutFor = (_fallbackPopoutFor === configName) ? null : configName;
          // Re-render cards so the More/Less label flips and the
          // bottom expand-rows show/hide on this card.
          _renderPresets();
          _renderCustom();
          _renderPopout();
          _restorePaneScroll(scrollState);
        });
      }
      var looseningBtn = card.querySelector('[data-action="loosening"]');
      if (looseningBtn) {
        looseningBtn.addEventListener('click', function (evt) {
          evt.stopPropagation();
          _looseningOpenFor = (_looseningOpenFor === configName) ? null : configName;
          _renderPresets();
          // _renderPresets parked the popout at the pane root;
          // re-attach it if a ▸ More expansion is open on some card.
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
        var scrollState = _capturePaneScroll();
        var slotLabel = row.dataset.pickSlot;
        var configName = row.dataset.pickConfig;
        if (_activeSlotPick
            && _activeSlotPick.configName === configName
            && _activeSlotPick.slotLabel === slotLabel) {
          _setActiveSlotPick(null);
        } else {
          _setActiveSlotPick({configName: configName, slotLabel: slotLabel});
          // Fast slot activates the speed sort so the actually-fast
          // candidates surface first. The filter below also requires
          // measured throughput, so unknown-speed models do not masquerade
          // as fast picks.
          if (slotLabel === 'fast 1' || slotLabel === 'fast 2') {
            _filters.sort_by = 'speed_desc';
          }
        }
        _renderHeader();
        _renderPresets();
        _renderCustom();
        // _renderPresets/_renderCustom parked the fallback popout at the pane
        // root before rebuilding the cards; re-attach it to the active card so
        // it doesn't sit orphaned at the root overlapping the inventory's right
        // column. No-op (hides) when no popout is open.
        _renderPopout();
        _renderInventory();
        _restorePaneScroll(scrollState);
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
    // Free preset's slots always cost $0 — drop the cost component
    // from the slot meta so the line stays tight.
    var omitCost = (presetName === 'free');
    var incomplete = !!summary.incomplete;
    var deprecatedList = _deprecatedPrimaries(summary);
    var deprecated = deprecatedList.length > 0;
    var depTitle = deprecated ? _deprecatedTooltip(deprecatedList, summary) : '';
    // A card's slot rows are editable when it's the active config (the
    // normal edit path) OR when it's incomplete (red — has to be
    // editable so the user can fill it before activation). Without this,
    // a newly-created blank config has no editable rows and the user
    // can never finish it.
    var editable = isActive || incomplete;
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
      +     (isActive ? '<span class="ora-models-card-active-flag">active</span>'
                      : '<span class="ora-models-card-active-flag" aria-hidden="true"></span>')
      +   '</header>'
      +   '<div class="ora-models-card-body">'
      +     _slotRowHTML('big 1', summary.big1, {omitCost: omitCost, configName: summary.name, isActive: editable})
      +     _slotRowHTML('big 2', summary.big2, {omitCost: omitCost, configName: summary.name, isActive: editable})
      +     _slotRowHTML('fast 1', summary.fast1, {omitCost: omitCost, configName: summary.name, isActive: editable, displayLabel: 'fast'})
      +     _slotRowHTML('small', summary.small, {omitCost: omitCost, configName: summary.name, isActive: editable})
      +     _expandSlotsHTML(summary, {omitCost: omitCost, isActive: editable})
      +     _looseningFootnoteHTML(summary)
      +   '</div>'
      +   '<div class="ora-models-card-actions">'
      +     '<span class="ora-models-card-action-buttons">'
      +       '<button type="button" class="ora-models-card-btn" data-action="more">'
      +         _moreLabelFor(summary.name) + '</button>'
      +       '<button type="button" class="ora-models-card-btn" data-action="customize">Customize</button>'
      +     '</span>'
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
    var c = {
      configName: summary.name,
      omitCost: !!(opts && opts.omitCost),
      isActive: !!(opts && opts.isActive),
    };
    // Single-cell overrides shown in the expand view. The vision/image-input
    // model moved OUT of here (2026-06-14): it's a global capability now, edited
    // in Settings → Visual → Advanced routing ("Vision input"), not a per-config
    // row. Formatter is gone too — the pipeline still runs that step internally
    // but always uses the inherited big-1 model.
    return ''
      + '<div class="ora-models-card-expand">'
      +   _slotRowHTML('utility', summary.utility, c)
      +   _slotRowHTML('consolidate', summary.consolidate, c)
      +   _slotRowHTML('verify', summary.verify, c)
      + '</div>';
  }

  function _moreLabelFor(configName) {
    return _fallbackPopoutFor === configName ? '▾ Less' : '▸ More';
  }

  // Footnote line for auto-populated presets whose bake had to relax a
  // constraint (vision_only, budget ceiling, …) for some cells — the
  // per-cell notes live in _auto_populate_metadata.loosening_log and
  // arrive on the summary as summary.loosening_log. Without this the
  // user sees e.g. a non-vision model in a Free-preset slot while the
  // Vision toggle reads on, with no explanation. Click toggles an
  // expandable per-cell detail list below the footnote.
  function _looseningFootnoteHTML(summary) {
    var log = summary.loosening_log || {};
    var cells = Object.keys(log);
    if (!cells.length) return '';
    var open = (_looseningOpenFor === summary.name);
    var n = cells.length;
    var html = ''
      + '<button type="button" class="ora-models-loosening-note"'
      +   ' data-action="loosening"'
      +   ' title="Auto-populate relaxed a constraint (e.g. Vision) for '
      +     n + ' slot' + (n === 1 ? '' : 's') + ' — no eligible model matched. '
      +     'Click for per-slot notes.">'
      +   (open ? '▾' : '▸') + ' ' + n + ' pick' + (n === 1 ? '' : 's')
      +   ' loosened'
      + '</button>';
    if (!open) return html;
    var items = cells.map(function (cell) {
      var notes = log[cell];
      if (!Array.isArray(notes)) notes = [String(notes)];
      return '<li><code>' + _esc(cell) + '</code> — '
        + _esc(notes.join('; ')) + '</li>';
    });
    return html
      + '<ul class="ora-models-loosening-detail">' + items.join('') + '</ul>';
  }

  function _slotRowHTML(label, modelId, opts) {
    opts = opts || {};
    var configName = opts.configName || '';
    var displayLabel = opts.displayLabel || label;
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
        + '<span class="ora-models-slot-label">' + _esc(displayLabel) + '</span>'
        + '<span class="ora-models-slot-value">—</span>'
        + '</div>';
    }
    var isPick = _picksSet && _picksSet.has(modelId);
    var model = _resolveRegistryModel(modelId);  // honors the id-alias map
    var isDeprecated = !model;  // not in the registry (and no alias) → retired
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
    var titleText = modelId + (meta ? ' — ' + meta : '');
    return '<div class="' + classes + '"'
      + (rowEditable ? ' data-pick-slot="' + _esc(label) + '"' +
                       ' data-pick-config="' + _esc(configName) + '"' : '')
      + (clickable ? '' : ' data-pick-disabled="true"')
      + (isDeprecated ? ' title="This model is no longer in the registry. '
                       + 'Pick a replacement."' : '')
      + '>'
      + '<span class="ora-models-slot-label">' + _esc(displayLabel) + '</span>'
      + '<span class="ora-models-slot-value" title="' + _esc(titleText) + '">'
      +   '<span class="ora-models-slot-model-name">' + _esc(rowValue) + '</span>'
      +   capChip
      +   (isPick ? '<span class="ora-models-pick-chip">PICK</span>' : '')
      +   (isDeprecated ? '<span class="ora-models-deprecated-chip">DEPRECATED</span>' : '')
      +   (meta ? '<span class="ora-models-slot-meta">' + meta + '</span>' : '')
      + '</span>'
      + '</div>';
  }

  // Compact meta line used in BOTH card slot rows and inventory rows.
  // Format: X% peak · $Y/M · Z t/s — parts dropped when underlying
  // data is null/absent. Intelligence is shown as a percentage of the
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
    var speedText = model.output_tokens_per_second != null
      ? model.output_tokens_per_second.toFixed(0) + ' t/s'
      : null;
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
    if (speedText) parts.push(speedText);
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
  // Resolve a config/preset model id to its registry entry, honoring the
  // build-time alias map. The vendor-catalogue-authoritative inversion changed
  // the id namespace (google/→gemini/, x-ai/→xai/, minimax/minimax-m3→
  // minimax/MiniMax-M3, dotted→hyphen, dated forms), so saved picks reference
  // ids the registry no longer keys by. The alias map (built from each entry's
  // also_known_as, exact forms only — no fuzzy matching) maps those old ids to
  // the current native entry. A genuinely-retired id (e.g. openai/gpt-oss-120b,
  // dropped from OpenAI's catalogue) resolves to nothing and correctly stays
  // DEPRECATED. Returns the model object or null.
  function _resolveRegistryModel(id) {
    var models = (_registry && _registry.models) || {};
    if (models[id]) return models[id];
    var aliases = (_registry && _registry.aliases) || {};
    var canonical = aliases[id];
    return canonical ? (models[canonical] || null) : null;
  }

  function _deprecatedPrimaries(summary) {
    var all = (summary && summary.all_primaries) || [];
    if (!Array.isArray(all) || !all.length) return [];
    return all.filter(function (id) { return !_resolveRegistryModel(id); });
  }

  // Tooltip text listing the deprecated primary ids on a yellow card,
  // plus a hint at which card-row to click to fix it. The custom tooltip
  // CSS uses `white-space: nowrap`, so this has to fit on one line.
  //
  // The hint matters because some deprecated cells (utility.classification,
  // utility.rag_planner, analysis.gear3.depth, post_analysis.*) have no
  // visible row on the card — they're fan-out targets from the BIG 1 /
  // SMALL card-body rows. Without the hint, the user replaces the wrong
  // slot and the yellow doesn't clear.
  function _deprecatedTooltip(ids, summary) {
    var n = ids.length;
    var fixHint = _fixHintForDeprecated(ids, summary);
    var head = (n === 1)
      ? 'Deprecated: ' + ids[0]
      : n + ' deprecated (' + ids[0] + (n > 1 ? ' + ' + (n - 1) + ' more' : '') + ')';
    return head + ' — ' + fixHint;
  }

  // Map deprecated primary ids to a one-line "click row X" hint by
  // walking the active config's cells (via summary) and matching each
  // deprecated id to the visible row whose fan-out covers it.
  function _fixHintForDeprecated(ids, summary) {
    if (!summary) return 'activate the card and re-pick the affected slot';
    var SMALL_FANOUT = ['small', 'utility.classification', 'utility.rag_planner', 'utility.step1_cleanup'];
    // gear3.depth + utility.gear2_rag_lookup moved to Fast 1's fan-out
    // (2026-05-23); BIG 1 now covers only post_analysis cells beyond
    // its own gear4.depth.
    var BIG1_FANOUT = ['big 1', 'post_analysis.consolidation',
                       'post_analysis.verification', 'post_analysis.formatter'];
    var FAST1_FANOUT = ['fast 1', 'analysis.gear3.depth', 'utility.gear2_rag_lookup'];
    var hits = {small: false, big1: false, big2: false, fast1: false, fast2: false, visual: false, other: false};
    // We don't have the cell paths surfaced per id in the summary —
    // so we infer by checking which visible fields the bad id lives in.
    var fields = {
      'small': summary.small,
      'big 1': summary.big1, 'big 2': summary.big2,
      'fast 1': summary.fast1, 'fast 2': summary.fast2,
      'visual': summary.visual, 'utility': summary.utility,
      'consolidate': summary.consolidate, 'verify': summary.verify,
    };
    ids.forEach(function (id) {
      var matched = false;
      Object.keys(fields).forEach(function (label) {
        if (fields[label] === id) {
          if (label === 'small' || label === 'utility') hits.small = true;
          else if (label === 'big 1' || label === 'consolidate' || label === 'verify') hits.big1 = true;
          else if (label === 'big 2') hits.big2 = true;
          else if (label === 'fast 1') hits.fast1 = true;
          else if (label === 'fast 2') hits.fast2 = true;
          else if (label === 'visual') hits.visual = true;
          matched = true;
        }
      });
      // No visible-row match: the deprecated cell is one of the
      // hidden fan-out targets (classification / rag_planner /
      // gear2_rag_lookup / post_analysis cells). Map to the row whose
      // pick re-writes it via SLOT_LABEL_TO_PATHS fan-out.
      if (!matched) hits.other = true;
    });
    var labels = [];
    if (hits.small) labels.push('SMALL');
    if (hits.big1) labels.push('BIG 1');
    if (hits.big2) labels.push('BIG 2');
    if (hits.fast1) labels.push('FAST 1');
    if (hits.fast2) labels.push('FAST 2');
    if (hits.visual) labels.push('VISUAL');
    if (hits.other) labels.push('SMALL or BIG 1 or FAST 1');
    return 'click ' + labels.join(' or ') + ' to repick';
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
    if (!bits.length) return '';
    return '<span class="ora-models-card-action-status ora-models-toggle-chip">'
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
    _setActiveSlotPick(null);
    // Popout fallback edit → write to the cell's fallback[index]
    // (single-cell, no fan-out). Primary picks continue to use the
    // legacy /slot endpoint with SLOT_LABEL_TO_PATHS fan-out.
    var isFallbackEdit = (pick.popoutSection != null
                          && pick.fallbackIndex != null
                          && pick.fallbackIndex >= 0);
    var url, body;
    if (isFallbackEdit) {
      url = '/api/configurations/' + encodeURIComponent(pick.configName) + '/fallback';
      body = {section: pick.popoutSection, index: pick.fallbackIndex, model_id: modelId};
    } else {
      url = '/api/configurations/' + encodeURIComponent(pick.configName) + '/slot';
      body = {slot: pick.slotLabel, model_id: modelId};
    }
    fetch(url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
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
    // Same parking dance as _renderPresets — see comment there.
    _parkPopoutAtPaneRoot();
    var customs = (_configs && _configs.customs) || [];
    var activeName = (_configs && _configs.active_name) || '';
    var scrollState = _capturePaneScroll();

    // "+ New configuration" now lives as a button in the section
    // header (was previously a tile in the first column of the row,
    // which caused the row to reflow every time a new config was
    // added). Cards are fixed-width grid cells; the row caps its
    // height and scrolls when full.
    var cards = customs.map(function (c) {
      return _customCardHTML(c, c.name === activeName);
    });

    section.innerHTML = ''
      + '<header class="ora-models-section-header">'
      +   '<h3>Custom configurations</h3>'
      +   '<button type="button" class="ora-models-section-btn"'
      +     ' data-action="new" title="Create a new blank configuration">'
      +     '+ New configuration</button>'
      +   '<span class="ora-models-section-hint">'
      +     'Click any card to activate. Customize copies a card into a new entry.'
      +   '</span>'
      + '</header>'
      + '<div class="ora-models-row ora-models-custom-row">'
      +   (cards.length ? cards.join('') : '<p class="ora-models-empty-msg">'
      +     'No saved configurations yet. Use “+ New configuration” above or '
      +     '“Customize” on any preset card to start one.</p>')
      + '</div>';
    _restorePaneScroll(scrollState);

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
          var scrollState = _capturePaneScroll();
          // Toggle: click ▸ More opens; click ▾ Less closes.
          _fallbackPopoutFor = (_fallbackPopoutFor === configName) ? null : configName;
          // Re-render cards so the More/Less label flips and the
          // bottom expand-rows show/hide on this card.
          _renderPresets();
          _renderCustom();
          _renderPopout();
          _restorePaneScroll(scrollState);
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
    // Read the incomplete flag straight from the summary — set by the
    // backend when create_blank_configuration runs (via + New) and
    // cleared the moment the four baselines all fill. Legacy customs
    // that happen to be missing image_generation are NOT flagged,
    // because the flag tracks "started from scratch, not yet finished"
    // intent, not a live completeness check.
    var incomplete = !!summary.incomplete;
    var deprecatedList = _deprecatedPrimaries(summary);
    var deprecated = deprecatedList.length > 0;
    var depTitle = deprecated ? _deprecatedTooltip(deprecatedList, summary) : '';
    // Editable on active OR incomplete — see preset card builder. A
    // blank "+ New configuration" lands here with isActive=false and
    // incomplete=true; without the second branch it would have no
    // editable rows and the user couldn't fill it.
    var editable = isActive || incomplete;
    return ''
      + '<div class="ora-models-card ora-models-card-custom'
      +   (isActive ? ' ora-models-card-active' : '')
      +   (incomplete ? ' ora-models-card-incomplete' : '')
      +   (deprecated && !incomplete ? ' ora-models-card-deprecated' : '') + '"'
      +   (depTitle ? ' title="' + _esc(depTitle) + '"' : '')
      +   ' data-config-name="' + _esc(summary.name) + '">'
      +   '<header class="ora-models-card-header">'
      +     '<span class="ora-models-card-title">' + _esc(summary.name) + '</span>'
      +     (isActive ? '<span class="ora-models-card-active-flag">active</span>'
                      : '<span class="ora-models-card-active-flag" aria-hidden="true"></span>')
      +   '</header>'
      +   '<div class="ora-models-card-body">'
      +     _slotRowHTML('big 1', summary.big1, {configName: summary.name, isActive: editable})
      +     _slotRowHTML('big 2', summary.big2, {configName: summary.name, isActive: editable})
      +     _slotRowHTML('fast 1', summary.fast1, {configName: summary.name, isActive: editable, displayLabel: 'fast'})
      +     _slotRowHTML('small', summary.small, {configName: summary.name, isActive: editable})
      +     _expandSlotsHTML(summary, {isActive: editable})
      +   '</div>'
      +   '<div class="ora-models-card-actions">'
      +     '<span class="ora-models-card-action-buttons">'
      +       '<button type="button" class="ora-models-card-btn" data-action="more">'
      +         _moreLabelFor(summary.name) + '</button>'
      +       '<button type="button" class="ora-models-card-btn" data-action="customize">'
      +         'Customize</button>'
      +       '<button type="button" class="ora-models-card-btn ora-models-card-btn-danger"'
      +         ' data-action="delete" title="Delete">×</button>'
      +     '</span>'
      +     _toggleChips(summary.toggles)
      +   '</div>'
      + '</div>';
  }

  // _newConfigCardHTML retired: "+ New configuration" moved to the
  // section header so the custom row stays uniform-grid and doesn't
  // reflow every time a config is added.

  // ── inventory grid ──────────────────────────────────────────────────────

  function _renderInventory() {
    if (!_hostEl) return;
    var section = _hostEl.querySelector('[data-section="inventory"]');
    if (!section) return;
    var models = (_registry && _registry.models) || {};
    // Inventory category resolution: a slot pick on the active card
    // forces the matching category (so picking IMAGE GEN swaps the
    // inventory to image models). With no slot picking in progress,
    // the user's category dropdown drives — defaults to Chat.
    var slotPickLabel = _activeSlotPick ? _activeSlotPick.slotLabel : null;
    var wantCategory = (slotPickLabel && SLOT_TO_CATEGORY[slotPickLabel])
      || _filters.category
      || 'chat';
    var allModels = Object.values(models).filter(function (m) {
      var c = (m && m.category) || 'chat';
      if (c !== wantCategory) return false;
      // OpenRouter media-output models (text+image→image / →video)
      // ride along in the registry with no category field, so they
      // defaulted into chat. They're vision_capable (image INPUT) and
      // often carry an Arena Elo fuzzy-borrowed from their text base
      // model (gpt-5-image ← gpt-5), which leaked them into the
      // vision-filtered chat inventory near the top of the
      // intelligence sort. Image/video generation lives on the Visual
      // tab — not here.
      if (wantCategory === 'chat') {
        var outs = m.output_modalities || [];
        for (var i = 0; i < outs.length; i++) {
          if (outs[i] === 'image' || outs[i] === 'video') return false;
        }
      }
      return true;
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
      // Surface active filters in the banner so users can see why
      // candidates they expected to be available aren't showing.
      // Most common case: Vision chip on hides locals (none of which
      // are vision-capable).
      var activeFilters = [];
      var clearables = [];
      var sizeFilter = _activeSlotPickSizeBucket();
      if (sizeFilter) activeFilters.push(sizeFilter + ' size');
      // Count candidates hidden ONLY because their size_bucket is
      // unknown (newly released models the family rules haven't
      // classified yet). Surfaced with a one-click include so a
      // strict size gate never silently buries a brand-new model
      // the user is specifically looking for.
      if (sizeFilter && sizeFilter !== 'midsize' && !_filters.include_unsized) {
        _filters.include_unsized = true;
        var unsizedHidden = allModels.filter(function (m) {
          return !m.size_bucket && _matchesFilters(m, rankedKeptIds);
        }).length;
        _filters.include_unsized = false;
        if (unsizedHidden > 0) {
          activeFilters.push(unsizedHidden + ' unknown-size models hidden (not yet classified — often the newest releases)');
          clearables.push('<button type="button" class="ora-models-pick-banner-clear" data-clear-filter="include_unsized">show unknown-size models</button>');
        }
      } else if (sizeFilter && _filters.include_unsized) {
        activeFilters.push('including unknown-size models');
      }
      if (_filters.vision) {
        activeFilters.push('vision-capable');
        if (!_activeSlotPickRequiresVision()) {
          clearables.push('<button type="button" class="ora-models-pick-banner-clear" data-clear-filter="vision">turn off Vision filter</button>');
        }
      }
      if (_activeSlotPickRequiresVision()) {
        activeFilters.push('vision required');
      }
      if (_activeSlotPickIsFast()) {
        activeFilters.push(FAST_MIN_TOKENS_PER_SECOND + '+ t/s');
      }
      if (_filters.free_filter === 'only') {
        activeFilters.push('free only');
        clearables.push('<button type="button" class="ora-models-pick-banner-clear" data-clear-filter="free_filter">reset cost filter</button>');
      } else if (_filters.free_filter === 'hide') {
        activeFilters.push('paid only (free hidden)');
        clearables.push('<button type="button" class="ora-models-pick-banner-clear" data-clear-filter="free_filter">reset cost filter</button>');
      }
      if (_filters.pick) {
        activeFilters.push('PICK only');
        clearables.push('<button type="button" class="ora-models-pick-banner-clear" data-clear-filter="pick">turn off PICK filter</button>');
      }
      if (_filters.intelligence_pct > 0) {
        activeFilters.push('top ' + (100 - _filters.intelligence_pct) + '% intelligence');
        clearables.push('<button type="button" class="ora-models-pick-banner-clear" data-clear-filter="intelligence_pct">reset Intel slider</button>');
      }
      var filterText = activeFilters.length
        ? ' · Filtered: ' + activeFilters.join(' + ')
        : '';
      var clearLinks = clearables.length
        ? '<div class="ora-models-pick-banner-clears">' + clearables.join(' · ') + '</div>'
        : '';
      pickBanner = ''
        + '<div class="ora-models-pick-banner">'
        +   '<div>Picking <strong>' + _esc(_activeSlotPick.slotLabel)
        +     '</strong> for <strong>' + _esc(_activeSlotPick.configName)
        +     '</strong> — click a model below, or press Esc to cancel.'
        +     filterText
        +   '</div>'
        +   clearLinks
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
    if (!isMedia && _activeSlotPickRequiresVision() && model.vision_capable !== true) return false;
    // Vision chip is LENIENT: hide only models PROVEN text-only
    // (vision_capable === false). Unknown/unenriched (null) passes —
    // most native ids-only flagships are vision-capable but unclassified
    // until enrichment/family rules land, and a strict !== true gate
    // wrongly buried ~225 of them. The VISUAL slot gate below stays
    // strict-true (a false positive there silently breaks image input).
    if (!isMedia && _filters.vision && model.vision_capable === false) return false;
    var isFree = (model.id || '').endsWith(':free') || model.is_free === true;
    if (!isMedia && _filters.free_filter === 'only' && !isFree) return false;
    if (!isMedia && _filters.free_filter === 'hide' && isFree) return false;
    if (_filters.pick && !(_picksSet && _picksSet.has(model.id))) return false;
    // Slot-pick size gate. When picking BIG 1 / BIG 2, restrict to
    // large-bucket models; SMALL / utility to small-bucket. Models
    // with no size_bucket are hidden by default — some are "~latest"
    // mirror aliases (where the route picks whatever the vendor's
    // current latest is, so size is undefined) — but they're NOT
    // excluded outright: a third of the catalog is unsized (newly
    // released models the family rules haven't classified yet, e.g.
    // Qwen 3.7 Plus the week it shipped), so the pick banner counts
    // the hidden ones and offers a one-click include
    // (_filters.include_unsized). The size_bucket field is enriched
    // by /api/model-registry from model-catalog.json.
    var sizeFilter = _activeSlotPickSizeBucket();
    if (sizeFilter) {
      // 'midsize' is permissive: midsize-bucket models pass exactly,
      // null-bucket models also pass (most cloud fast models have
      // undisclosed parameters_b → null). large/small are strict
      // exact-match. See the Fast slot rationale in SLOT_TO_SIZE_BUCKET.
      if (sizeFilter === 'midsize') {
        if (model.size_bucket === 'large' || model.size_bucket === 'small') return false;
      } else if (model.size_bucket) {
        if (model.size_bucket !== sizeFilter) return false;
      } else if (!_filters.include_unsized) {
        return false;
      }
    }
    if (_activeSlotPickIsFast()) {
      var tps = model.output_tokens_per_second;
      if (tps == null || tps < FAST_MIN_TOKENS_PER_SECOND) return false;
    }
    // (The vision/image-input model is no longer a Models-tab slot — it moved
    // to Settings → Visual → Advanced routing as the global "Vision input"
    // capability. No per-slot capability gate remains here.)
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

  function _activeSlotPickRequiresVision() {
    if (!_activeSlotPick) return false;
    if (_activeSlotPick.slotLabel === 'fast 1') return true;
    return _activeSlotPick.popoutSection === 'fast'
      && _activeSlotPick.fallbackIndex === 0;
  }

  function _activeSlotPickIsFast() {
    if (!_activeSlotPick) return false;
    return _activeSlotPick.slotLabel === 'fast 1'
      || _activeSlotPick.slotLabel === 'fast 2'
      || _activeSlotPick.slotLabel === 'fast'
      || _activeSlotPick.popoutSection === 'fast';
  }

  // Each card-visible slot maps to an expected size bucket. When a slot
  // is in picking mode, the inventory restricts to that bucket so the
  // user doesn't see small models as candidates for a big-1 slot or
  // large models for a small slot. Returns null when no slot pick is
  // active.
  var SLOT_TO_SIZE_BUCKET = {
    'big 1':       'large',
    'big 2':       'large',
    'small':       'small',
    'utility':     'small',
    'consolidate': 'large',
    'verify':      'large',
    // Popout fallback-section labels — same bucket as the primary
    // they fall back from, so a SMALL fallback chain only sees small
    // models and a LARGE chain only sees large ones.
    'large':       'large',
  };

  // Slot label → inventory category. Empty since 2026-06-11: the
  // image_generation slot left the configuration schema (image-model
  // selection lives on the Visual tab / routing-config slots chain),
  // so no slot pick swaps the inventory away from chat. Kept as a
  // table so a future media slot can re-register here.
  var SLOT_TO_CATEGORY = {};

  function _slotPickInventoryCategory(pick) {
    pick = pick || _activeSlotPick;
    var label = pick ? pick.slotLabel : null;
    return (label && SLOT_TO_CATEGORY[label])
      || _filters.category
      || 'chat';
  }

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
    if (model.vendor) {
      var v = String(model.vendor).toLowerCase();
      // Local is the one vendor we keep capitalized — the
      // column-0 pinning, auto-expand-during-pick, and LOCAL chip
      // logic all key on the exact string 'Local'. No other vendor
      // collides with 'local' so the dedup intent above still holds.
      if (v === 'local') return 'Local';
      return v;
    }
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
          // Use the same raw-intelligence helper the % peak chip uses
          // so the visible chip and the sort order agree. Arena-Elo-
          // only chat models deliberately rank in the labeled
          // unranked tail rather than via the (elo-800)/7
          // normalisation: most chat Elos without AA coverage are
          // fuzzy-borrowed from a base model (kimi-k2.7-code ←
          // kimi-k2.x, o3-deep-research ← o3), and surfacing them
          // sorted the borrowed scores ABOVE genuinely-measured
          // models (publisher report 2026-06-12).
          var ai = _rawIntelligence(a);
          var bi = _rawIntelligence(b);
          if (ai == null) ai = -Infinity;
          if (bi == null) bi = -Infinity;
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
    if (model.vendor === 'Local' || model._local_endpoint === true) {
      chips.push('<span class="ora-models-chip ora-models-chip-local" title="Runs on this Mac via MLX. Free, no remote vendor, no rate limits.">LOCAL</span>');
    }
    if (_picksSet && _picksSet.has(model.id)) {
      chips.push('<span class="ora-models-pick-chip">PICK</span>');
    }
    // Subscription chip. Merged server-side from routing-config endpoints
    // with service=claude-code: executes through the user's Claude
    // subscription via the local Claude Code CLI — zero marginal API
    // cost. These ids are NOT registry models, which previously made any
    // configuration using them read DEPRECATED (and invited re-picking
    // onto the metered API — the wrong fix).
    if (model._subscription_endpoint === true) {
      chips.push('<span class="ora-models-chip ora-models-chip-subscription" title="Executes through your Claude subscription via the local Claude Code CLI. Zero marginal API cost; campaign cost tables price its tokens at the API-equivalent rate.">SUBSCRIPTION</span>');
    }
    // Direct-dispatch chip. Stamped server-side from routing-config
    // endpoints with dispatch=direct: the user holds this vendor's API
    // key, so calls go straight to the vendor (cheaper than OpenRouter);
    // OpenRouter remains the per-call fallback.
    if (model.direct_dispatch === true) {
      chips.push('<span class="ora-models-chip ora-models-chip-direct" title="Dispatches via your '
        + _esc(model.direct_service || 'vendor')
        + ' API key (direct vendor API, no OpenRouter premium). OpenRouter is the per-call fallback.">DIRECT</span>');
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
      chips.push('<span class="ora-models-chip ora-models-chip-unverified" title="No conclusive reachability probe verdict yet. Probes now run automatically after every registry refresh; this clears once the model answers a probe. Unverified models are never auto-picked.">UNVERIFIED</span>');
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
      // Label kept to one word — the previous "NOT IN VENDOR LIST"
      // crowded the model name out of narrow inventory columns.
      chips.push('<span class="ora-models-chip ora-models-chip-vendor-phantom" title="Not in the vendor\'s own /v1/models catalog. May be an AA-only phantom, or a real model that only routes via OpenRouter (open-source / third-party). Combine with the UNREACHABLE chip to identify true phantoms.">UNLISTED</span>');
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

  // Which models can't be ranked under the active sort, and what to call
  // the labeled tail section they go into. Mirrors the missing-key
  // sentinels in _sortModels (null intelligence → -Infinity etc.) so the
  // partition and the comparator can never disagree.
  function _flatUnrankedSpec(by) {
    switch (by) {
      case 'intelligence_desc':
        return {
          label: 'No intelligence score',
          pred: function (m) { return _rawIntelligence(m) == null; },
        };
      case 'cost_asc':
        return {
          label: 'No pricing data',
          pred: function (m) {
            var c = _blendedCostPerM(m);
            return c == null || c < 0;
          },
        };
      case 'latency_asc':
        return {
          label: 'No latency data',
          pred: function (m) { return m.latency_ttft_seconds == null; },
        };
      case 'speed_desc':
        return {
          label: 'No throughput data',
          pred: function (m) { return m.output_tokens_per_second == null; },
        };
      default:
        return null; // alphabetical — every model is rankable
    }
  }

  // Flat-list layout: distribute matching models column-major across 4
  // columns. The user sorted by Cost (or whatever) sees the top of
  // column 1 first; column 2 picks up where 1 left off. Models missing
  // the active sort's key can't be ranked — they used to sink silently
  // to the tail columns and read as a mystery group; now they render
  // under an explicit divider, alphabetized.
  function _flatColumnsHTML(models) {
    if (!models.length) {
      return '<div class="ora-models-inventory-column">'
        + '<p class="ora-models-empty-msg">No models match the current filters.</p>'
        + '</div>';
    }
    var spec = _flatUnrankedSpec(_filters.sort_by);
    var ranked = models;
    var unranked = [];
    if (spec) {
      ranked = models.filter(function (m) { return !spec.pred(m); });
      unranked = models.filter(spec.pred);
      // The active sort key says nothing about these — alphabetize so
      // the tail's internal order is self-explanatory.
      unranked.sort(function (a, b) {
        return (a.id || '').localeCompare(b.id || '');
      });
    }
    var html = '<div class="ora-models-flat-stack">' + _flatBandHTML(ranked);
    if (unranked.length) {
      html += '<div class="ora-models-flat-divider" title="These models are missing the data the active sort ranks by (usually no Artificial Analysis coverage yet). They are fully usable — just unrankable on this axis.">'
        + _esc(spec.label) + ' — unranked, A→Z (' + unranked.length + ')'
        + '</div>'
        + _flatBandHTML(unranked);
    }
    return html + '</div>';
  }

  // One 4-column column-major band of flat rows.
  function _flatBandHTML(models) {
    if (!models.length) return '';
    var perCol = Math.ceil(models.length / 4);
    var cols = [[], [], [], []];
    models.forEach(function (m, i) {
      var idx = Math.min(3, Math.floor(i / perCol));
      cols[idx].push(m);
    });
    return '<div class="ora-models-flat-band">'
      + cols.map(function (col) {
          if (!col.length) return '<div class="ora-models-inventory-column"></div>';
          return '<div class="ora-models-inventory-column">'
            + '<ul class="ora-models-model-list ora-models-model-list-flat">'
            +   col.map(_modelRowHTML).join('')
            + '</ul>'
            + '</div>';
        }).join('')
      + '</div>';
  }

  function _categorySelectHTML() {
    // A one-entry category list (chat-only, the state since the media
    // categories left with the image_generation slot) makes the
    // dropdown pure noise — render nothing.
    if (CATEGORY_OPTIONS.length < 2) return '';
    // Active slot-pick locks the category to match the slot — show the
    // dropdown disabled so the user sees why their click can't change it.
    var slotPickLabel = _activeSlotPick ? _activeSlotPick.slotLabel : null;
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
    // Pick-banner clear-filter buttons. One-click reset for whichever
    // filter is currently restricting candidates the user expected to
    // see (typically Vision hiding locals).
    Array.from(section.querySelectorAll('[data-clear-filter]')).forEach(function (btn) {
      btn.addEventListener('click', function () {
        var key = btn.dataset.clearFilter;
        if (key === 'free_filter') _filters.free_filter = 'any';
        else if (key === 'intelligence_pct') _filters.intelligence_pct = 0;
        // include_unsized is an opt-IN (the button widens the result
        // set rather than clearing a restriction), so it sets true.
        else if (key === 'include_unsized') _filters.include_unsized = true;
        else _filters[key] = false;
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

    // Three sections, fixed shape regardless of adversarial toggle.
    // Each section's first row uses the section label (LARGE / FAST / SMALL)
    // as the rank, displaying the primary inline with the label
    // — no separate h4. Remaining rows are FALLBACK N. Each section is
    // capped: large/fast/small each show at most 2 fallbacks in the UI.
    // Extra saved fallback data can still exist behind the scenes. Empty
    // fallback positions render as clickable placeholders so the user can
    // fill them in place.
    var sections = [
      _popoutSlotHTML('large', summary.big1, summary.big1_fallback, summary.name, 2),
      _popoutSlotHTML('fast', summary.fast1, summary.fast1_fallback, summary.name, 2),
      _popoutSlotHTML('small', summary.small, summary.small_fallback, summary.name, 2),
    ];

    popout.hidden = false;
    popout.innerHTML = ''
      + '<header class="ora-models-popout-header">'
      +   '<span class="ora-models-popout-title">Fallback chains · '
      +     '<strong>' + _esc(summary.name) + '</strong>'
      +     ' <span class="ora-models-popout-subtitle">— tried in order; free tiers cycle deeper</span>'
      +   '</span>'
      +   '<button type="button" class="ora-models-popout-close" aria-label="Close">×</button>'
      + '</header>'
      + '<div class="ora-models-popout-body">'
      +   sections.join('')
      + '</div>';

    popout.querySelector('.ora-models-popout-close')
      .addEventListener('click', function () {
        _fallbackPopoutFor = null;
        _renderPopout();
        _renderPresets();
        _renderCustom();
      });

    // Wire fallback-row clicks: each fallback row enters picking mode
    // for the specific (section, index) position. Inventory click then
    // writes through /api/configurations/<name>/fallback rather than
    // the primary /slot path so SLOT_LABEL_TO_PATHS fan-out doesn't
    // fire (fallback chains live per-cell).
    Array.from(popout.querySelectorAll('.ora-models-popout-row-clickable'))
      .forEach(function (row) {
        row.addEventListener('click', function (evt) {
          if (evt.target.closest('button')) return;
          evt.stopPropagation();
          var section = row.dataset.popoutSection;
          var index = parseInt(row.dataset.popoutFallbackIndex, 10);
          var configName = row.dataset.popoutConfig;
          if (!section || isNaN(index) || !configName) return;
          // Toggle off when re-clicking the active pick
          if (_activeSlotPick
              && _activeSlotPick.popoutSection === section
              && _activeSlotPick.fallbackIndex === index
              && _activeSlotPick.configName === configName) {
            _setActiveSlotPick(null);
          } else {
            _setActiveSlotPick({
              configName: configName,
              slotLabel: section,            // category dispatch uses this
              popoutSection: section,        // identifies fallback intent
              fallbackIndex: index,
            });
            if (section === 'fast') {
              _filters.sort_by = 'speed_desc';
            }
          }
          _renderHeader();
          _renderPopout();
          _renderInventory();
        });
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

  // Move the popout element back under the pane root without changing
  // _fallbackPopoutFor or the popout-open row/card classes (those get
  // re-applied by _attachPopoutToActiveCard on the next render). Used
  // before any section that might re-wipe innerHTML — protects the
  // popout from being destroyed mid-flow.
  function _parkPopoutAtPaneRoot() {
    if (!_hostEl) return;
    var popout = _hostEl.querySelector('[data-section="popout"]');
    if (!popout) return;
    var pane = _hostEl.querySelector('.ora-models-pane');
    if (pane && popout.parentElement !== pane) {
      pane.appendChild(popout);
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

  function _popoutSlotHTML(label, primary, fallbackList, configName, maxFallbacks) {
    fallbackList = fallbackList || [];
    if (typeof maxFallbacks !== 'number') maxFallbacks = fallbackList.length;
    var rows = [];
    // First row: the section label IS the rank. Primary inline with label.
    rows.push(_popoutRowHTML(primary, _resolveRegistryModel(primary), label.toUpperCase(),
      {section: label, fallbackIndex: -1, configName: configName, sectionHeader: true}));
    // Fallback rows, capped at maxFallbacks. Empty positions render as
    // clickable placeholders so the user can pick into them in place.
    for (var i = 0; i < maxFallbacks; i++) {
      var fbId = fallbackList[i] || null;
      rows.push(_popoutRowHTML(fbId, fbId ? _resolveRegistryModel(fbId) : null,
        'fallback ' + (i + 1),
        {section: label, fallbackIndex: i, configName: configName}));
    }
    return rows.join('');
  }

  function _popoutRowHTML(modelId, model, rank, opts) {
    opts = opts || {};
    var displayName = modelId
      ? ((model && model.display_name) || modelId)
      : '— click to pick a fallback —';
    var chips = (model && modelId) ? _modelChipsHTML(model) : '';
    var meta = (model && modelId) ? _compactMetaHTML(model) : '';
    var isFallback = (opts.fallbackIndex != null && opts.fallbackIndex >= 0);
    var isActivePick = isFallback && _activeSlotPick
      && _activeSlotPick.popoutSection === opts.section
      && _activeSlotPick.fallbackIndex === opts.fallbackIndex
      && _activeSlotPick.configName === opts.configName;
    var classes = 'ora-models-popout-row';
    if (opts.sectionHeader) classes += ' ora-models-popout-row-section-header';
    if (isFallback) classes += ' ora-models-popout-row-clickable';
    if (isActivePick) classes += ' ora-models-popout-row-picking';
    if (!modelId && isFallback) classes += ' ora-models-popout-row-empty-fallback';
    var dataAttrs = '';
    if (isFallback && opts.configName) {
      dataAttrs = ' data-popout-section="' + _esc(opts.section) + '"'
        + ' data-popout-fallback-index="' + opts.fallbackIndex + '"'
        + ' data-popout-config="' + _esc(opts.configName) + '"';
    }
    return ''
      + '<div class="' + classes + '"' + dataAttrs + '>'
      +   '<span class="ora-models-popout-rank">' + _esc(rank) + '</span>'
      +   '<span class="ora-models-popout-name"'
      +     (modelId ? ' title="' + _esc(modelId) + '"' : '') + '>'
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
    // Two totals to surface:
    //   INSTALLED — every model downloaded to disk. Sum of ram_gb across
    //   the install set. Not all of these are loaded at once.
    //   IN USE    — only the locals referenced as primary in the active
    //   configuration. This is what's actually resident in RAM when the
    //   pipeline runs. Headroom = available − IN USE.
    var installedTotal = locals.reduce(function (sum, m) {
      return sum + (m.ram_gb || 0);
    }, 0);
    var inUseIds = _localsReferencedByActiveConfig();
    var inUseTotal = locals.reduce(function (sum, m) {
      return inUseIds.has(m.id) ? sum + (m.ram_gb || 0) : sum;
    }, 0);
    var available = h.available_budget_gb || 0;
    var headroom = available - inUseTotal;

    var rows = locals.map(function (m) {
      var size = m.ram_gb != null ? m.ram_gb + ' GB' : '?';
      var fits = (m.ram_gb || 0) <= (h.available_budget_gb || Infinity);
      var inUse = inUseIds.has(m.id);
      var classes = 'ora-models-hw-row' + (inUse ? ' ora-models-hw-row-in-use' : '');
      return ''
        + '<li class="' + classes + '">'
        +   '<span class="ora-models-hw-name">' + _esc(m.display_name || m.id) + '</span>'
        +   (inUse ? '<span class="ora-models-hw-in-use-chip">IN ACTIVE CONFIG</span>' : '')
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
      +     'RAM math reflects what the active configuration actually loads. '
      +     'Installed-but-not-referenced models cost zero RAM.'
      +   '</span>'
      + '</header>'
      + '<div class="ora-models-hw-body">'
      +   '<div class="ora-models-hw-totals">'
      +     '<div><span class="ora-models-hw-label">System RAM</span>'
      +       '<span class="ora-models-hw-value">' + _esc(String(h.system_ram_gb || '?')) + ' GB</span></div>'
      +     '<div><span class="ora-models-hw-label">Overhead</span>'
      +       '<span class="ora-models-hw-value">' + _esc(String(h.overhead_gb || '?')) + ' GB</span></div>'
      +     '<div><span class="ora-models-hw-label">Available</span>'
      +       '<span class="ora-models-hw-value">' + _esc(String(available || '?')) + ' GB</span></div>'
      +     '<div><span class="ora-models-hw-label">Installed</span>'
      +       '<span class="ora-models-hw-value">' + _esc(installedTotal.toFixed(0)) + ' GB</span></div>'
      +     '<div><span class="ora-models-hw-label">In use by active</span>'
      +       '<span class="ora-models-hw-value">' + _esc(inUseTotal.toFixed(0)) + ' GB</span></div>'
      +     '<div><span class="ora-models-hw-label">Headroom</span>'
      +       '<span class="ora-models-hw-value' + (headroom < 0 ? ' ora-models-hw-headroom-low' : '') + '">'
      +         _esc(headroom.toFixed(0)) + ' GB</span></div>'
      +   '</div>'
      +   '<p class="ora-models-hw-note">Select local models from Model Inventory above.</p>'
      +   (locals.length
        ? '<ul class="ora-models-hw-list">' + rows.join('') + '</ul>'
        : '<p class="ora-models-placeholder">No local models installed.</p>')
      + '</div>';
  }

  // Collect the set of local-* model ids referenced as a primary
  // anywhere in the active configuration. Used to compute "in use"
  // RAM accounting in the hardware section. Walks summary.all_primaries
  // (already a flat list across every cell).
  function _localsReferencedByActiveConfig() {
    var ids = new Set();
    if (!_configs) return ids;
    var activeName = _configs.active_name;
    if (!activeName) return ids;
    var summary = null;
    Object.keys(_configs.presets || {}).forEach(function (k) {
      var p = _configs.presets[k];
      if (p && p.name === activeName) summary = p;
    });
    if (!summary) {
      summary = (_configs.customs || []).find(function (c) { return c.name === activeName; });
    }
    if (!summary || !Array.isArray(summary.all_primaries)) return ids;
    summary.all_primaries.forEach(function (pid) {
      if (typeof pid === 'string' && pid.indexOf('/') === -1) {
        // No-slash id == local (registry convention)
        ids.add(pid);
      }
    });
    return ids;
  }

  // ── Maintenance section (bottom of pane) ─────────────────────────────
  //
  // Houses the manual reachability-probe trigger. The probe is opt-in
  // because it costs ~15 minutes of wall time and a few cents of
  // OpenRouter tokens. Surfaces the prior probe's date + per-verdict
  // counts so the user knows the freshness picture before deciding
  // whether to re-run.

  function _renderMaintenance() {
    if (!_hostEl) return;
    var section = _hostEl.querySelector('[data-section="maintenance"]');
    if (!section) return;

    // Walk the registry once to compute reach + vendor verdict counts.
    var models = (_registry && _registry.models) || {};
    var counts = {
      total: 0, reach_true: 0, reach_rate: 0,
      reach_false: 0, reach_null: 0,
      vendor_true: 0, vendor_false: 0, vendor_null: 0,
      last_probe: null,
    };
    Object.values(models).forEach(function (m) {
      var cat = (m && m.category) || 'chat';
      if (cat !== 'chat') return;
      counts.total += 1;
      if (m.reachable === true) {
        counts.reach_true += 1;
        if (m.reachable_rate_limited) counts.reach_rate += 1;
      } else if (m.reachable === false) {
        counts.reach_false += 1;
      } else {
        counts.reach_null += 1;
      }
      if (m.vendor_listed === true) counts.vendor_true += 1;
      else if (m.vendor_listed === false) counts.vendor_false += 1;
      else counts.vendor_null += 1;
      var d = m.reachable_probed_at;
      if (d && (!counts.last_probe || d > counts.last_probe)) counts.last_probe = d;
    });

    var lastProbeStr = counts.last_probe
      ? counts.last_probe.slice(0, 10)
      : 'never run';
    section.innerHTML = ''
      + '<header class="ora-models-section-header">'
      +   '<h3>Reachability probe</h3>'
      +   '<span class="ora-models-section-hint">'
      +     'Last full probe: <strong>' + _esc(lastProbeStr) + '</strong>'
      +   '</span>'
      + '</header>'
      + '<div class="ora-models-maintenance-body">'
      +   '<div class="ora-models-maintenance-stats">'
      +     '<div><span class="ora-models-hw-label">Reachable</span>'
      +       '<span class="ora-models-hw-value">' + counts.reach_true
      +         (counts.reach_rate ? ' <em>(' + counts.reach_rate + ' rate-limited)</em>' : '')
      +       '</span></div>'
      +     '<div><span class="ora-models-hw-label">Unreachable</span>'
      +       '<span class="ora-models-hw-value">' + counts.reach_false + '</span></div>'
      +     '<div><span class="ora-models-hw-label">Unverified</span>'
      +       '<span class="ora-models-hw-value">' + counts.reach_null
      +         ' of ' + counts.total + '</span></div>'
      +     '<div><span class="ora-models-hw-label">Vendor-listed</span>'
      +       '<span class="ora-models-hw-value">' + counts.vendor_true
      +         ' confirmed · ' + counts.vendor_false + ' phantom · '
      +         counts.vendor_null + ' not audited</span></div>'
      +   '</div>'
      +   '<p class="ora-models-maintenance-explainer">'
      +     'A reachability probe sends a 16-token "hi" completion to '
      +     'every chat model in the registry and watches the HTTP status:'
      +     '<br><br>'
      +     '<strong>200</strong> → reachable. <strong>429</strong> → reachable but rate-limited '
      +     '(common on free tiers; the fallback chain handles it at runtime). '
      +     '<strong>404 / 410 / 400</strong> → unreachable; auto-populate '
      +     'will skip these. Vendor audit (free) runs alongside and confirms '
      +     'whether Anthropic / OpenAI / Google list the id in their own '
      +     'catalog.'
      +     '<br><br>'
      +     '<strong>Cost:</strong> roughly $0.05–$0.20 of OpenRouter tokens '
      +     'against the full ' + counts.total + '-chat-model catalog. '
      +     '<strong>Time:</strong> ~15 minutes (1–3s per model). Runs in the '
      +     'background; you can keep using Ora during the probe.'
      +     '<br><br>'
      +     'Re-run if your auto-populated picks have started failing, if '
      +     'OpenRouter announces a model deprecation, or if you want to verify '
      +     'a freshly-added vendor key.'
      +   '</p>'
      +   '<div class="ora-models-maintenance-actions">'
      +     '<button type="button" class="ora-models-card-btn ora-models-card-btn-primary"'
      +       ' data-action="reach-probe-start">'
      +       'Probe ' + counts.total + ' models</button>'
      +     '<button type="button" class="ora-models-card-btn"'
      +       ' data-action="reach-probe-only-unknown">'
      +       'Probe ' + counts.reach_null + ' unverified only</button>'
      +     '<span class="ora-models-maintenance-status" data-role="reach-status"></span>'
      +   '</div>'
      + '</div>';

    section.querySelector('[data-action="reach-probe-start"]')
      .addEventListener('click', function () { _startReachProbe({revalidate: true}); });
    section.querySelector('[data-action="reach-probe-only-unknown"]')
      .addEventListener('click', function () { _startReachProbe({only_unknown: true}); });

    // If a probe is already running (started in a prior pane open),
    // resume polling now so the user sees status immediately.
    _pollReachStatusOnce();
  }

  var _reachPollTimer = null;

  function _startReachProbe(opts) {
    var btnAll = _hostEl.querySelector('[data-action="reach-probe-start"]');
    var btnUnk = _hostEl.querySelector('[data-action="reach-probe-only-unknown"]');
    if (btnAll) btnAll.disabled = true;
    if (btnUnk) btnUnk.disabled = true;
    fetch('/api/model-registry/reach/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(opts || {}),
    }).then(_json).then(function () {
      _pollReachStatus();
    }).catch(function (err) {
      _setReachStatus('Failed to start: ' + (err && err.message));
      if (btnAll) btnAll.disabled = false;
      if (btnUnk) btnUnk.disabled = false;
    });
  }

  function _pollReachStatus() {
    if (_reachPollTimer) return;
    _reachPollTimer = setInterval(function () {
      fetch('/api/model-registry/reach/status').then(_json).then(function (s) {
        if (s.in_progress) {
          var idx = s.current_index || 0, total = s.total || 0;
          _setReachStatus('Probing ' + idx + ' / ' + total
            + (s.current_model ? ' — ' + s.current_model : ''));
        } else {
          clearInterval(_reachPollTimer);
          _reachPollTimer = null;
          var summary = s.last_summary || {};
          if (summary.error) {
            _setReachStatus('Failed: ' + summary.error);
          } else if (summary.reachable !== undefined) {
            _setReachStatus('Done: ' + summary.reachable + ' reachable, '
              + summary.unreachable + ' unreachable, ' + summary.rate_limited
              + ' rate-limited, ' + summary.inconclusive + ' inconclusive.');
            // Refresh registry data + re-render so chips and counts update.
            _loadAll();
          }
          var btnAll = _hostEl.querySelector('[data-action="reach-probe-start"]');
          var btnUnk = _hostEl.querySelector('[data-action="reach-probe-only-unknown"]');
          if (btnAll) btnAll.disabled = false;
          if (btnUnk) btnUnk.disabled = false;
        }
      });
    }, 2000);
  }

  function _pollReachStatusOnce() {
    fetch('/api/model-registry/reach/status').then(_json).then(function (s) {
      if (s.in_progress) {
        var btnAll = _hostEl.querySelector('[data-action="reach-probe-start"]');
        var btnUnk = _hostEl.querySelector('[data-action="reach-probe-only-unknown"]');
        if (btnAll) btnAll.disabled = true;
        if (btnUnk) btnUnk.disabled = true;
        _pollReachStatus();
      }
    });
  }

  function _setReachStatus(text) {
    var el = _hostEl.querySelector('[data-role="reach-status"]');
    if (el) el.textContent = text || '';
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
