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
  var _active = null;            // {name, toggles, missing} from /api/configurations/active

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
    _active = null;
  }

  // ── data load ───────────────────────────────────────────────────────────

  function _loadAll() {
    Promise.all([
      fetch('/api/model-registry').then(_json),
      fetch('/api/model-registry/picks').then(_json),
      fetch('/api/configurations/active').then(_json),
    ]).then(function (resp) {
      _registry = resp[0] || {};
      var picksPayload = resp[1] || {};
      _picksSet = new Set(picksPayload.picks || []);
      _active = resp[2] || {name: '', toggles: {}, missing: true};
      _renderHeader();
      _renderRemainingSkeleton();
    }).catch(function (err) {
      _showHeaderError(err);
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
    var name = (_active && _active.name) || '(none)';
    var missing = _active && _active.missing;
    var t = (_active && _active.toggles) || {};
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
        _active.toggles = resp.toggles;
        // Re-render the header to reflect the canonical server-side
        // state (in case the server adjusted anything). Cheap.
        _renderHeader();
      }
    }).catch(function (err) {
      // Toggle didn't persist — revert the checkbox state by reloading
      // header from current cached state. The user sees their click
      // "bounce back," which signals failure without a modal.
      _renderHeader();
      console.warn('[models-pane] toggle save failed:', err);
    });
  }

  // ── placeholder sections (filled by subsequent commits) ─────────────────

  function _renderRemainingSkeleton() {
    if (!_hostEl) return;
    var sections = [
      ['presets',
       'Presets row — Free / Budget / Optimum / Premium cards (commit step 4).'],
      ['custom',
       'Custom-New + Previous grid (commit step 5).'],
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
