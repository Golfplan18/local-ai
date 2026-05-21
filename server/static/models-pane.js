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

    // Custom-New = the active configuration if it's a custom, else
    // an empty draft scaffold. The active custom shows here AND in
    // the Previous grid (with its green border in both spots) so the
    // user can see "this is what's running" front-and-center while
    // also having the full saved set visible to the right.
    var activeCustom = customs.find(function (c) { return c.name === activeName; });
    var newCardHTML = activeCustom
      ? _customNewActiveHTML(activeCustom)
      : _customNewEmptyHTML();

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

  function _customNewActiveHTML(summary) {
    // Mirror the preset-card body shape so the user can see what's
    // active in the same form as anywhere else. The red/green border
    // reflects completion: red until all 3 minimum slots are picked,
    // green once they are.
    var complete = !!(summary.big1 && summary.small);
    return ''
      + '<div class="ora-models-card ora-models-card-custom-new'
      +   (complete ? ' ora-models-card-active' : ' ora-models-card-incomplete') + '"'
      +   ' data-config-name="' + _esc(summary.name) + '">'
      +   '<header class="ora-models-card-header">'
      +     '<span class="ora-models-card-title">' + _esc(summary.name) + '</span>'
      +     (complete
        ? '<span class="ora-models-card-active-flag">active</span>'
        : '<span class="ora-models-incomplete-flag">incomplete</span>')
      +   '</header>'
      +   '<div class="ora-models-card-body">'
      +     _slotRowHTML('big 1', summary.big1)
      +     _slotRowHTML('big 2', summary.big2)
      +     _slotRowHTML('small', summary.small)
      +   '</div>'
      +   '<div class="ora-models-card-actions">'
      +     '<button type="button" class="ora-models-card-btn" data-action="more">▸ More</button>'
      +   '</div>'
      +   '<div class="ora-models-card-footer">'
      +     _toggleChips(summary.toggles)
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

  // ── placeholder sections (filled by subsequent commits) ─────────────────

  function _renderRemainingSkeleton() {
    if (!_hostEl) return;
    var sections = [
      ['inventory',
       'Vendor-organized model inventory with filter chips and intelligence slider (commit step 6).'],
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
