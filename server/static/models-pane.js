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
 * Built across multiple commits — this file lands as a skeleton that
 * confirms the mount and pulls the registry + picks data. Subsequent
 * commits in the same Chunk-10 sequence fill each section.
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

    // Fetch the registry + picks together. The screen can't render
    // anything substantive without both, so we wait for both before
    // calling out of the loading state.
    Promise.all([
      fetch('/api/model-registry').then(function (r) { return r.json(); }),
      fetch('/api/model-registry/picks').then(function (r) { return r.json(); }),
    ]).then(function (resp) {
      _registry = resp[0] || {};
      var picksPayload = resp[1] || {};
      _picksSet = new Set(picksPayload.picks || []);
      _renderSkeletonReport();
    }).catch(function (err) {
      var header = _hostEl && _hostEl.querySelector('[data-section="header"]');
      if (header) {
        header.innerHTML = '<p class="ora-models-error">'
          + 'Could not load model registry: '
          + ((err && err.message) || 'unknown error')
          + '</p>';
      }
    });
  }

  function destroy() {
    if (_hostEl) {
      _hostEl.classList.remove('ora-models-pane-host');
      _hostEl.innerHTML = '';
      _hostEl = null;
    }
    _registry = null;
    _picksSet = null;
  }

  // ── private rendering ────────────────────────────────────────────────────

  // Placeholder header rendering until subsequent commits in the same
  // chunk install the real layout. Confirms the data fetch worked and
  // gives the user (and reviewers) something concrete to verify the
  // mount against in the browser.
  function _renderSkeletonReport() {
    if (!_hostEl) return;
    var stats = (_registry && _registry.stats) || {};
    var picksCount = _picksSet ? _picksSet.size : 0;
    var header = _hostEl.querySelector('[data-section="header"]');
    if (!header) return;
    header.innerHTML = ''
      + '<div class="ora-models-skeleton">'
      +   '<h3>Model Configuration</h3>'
      +   '<p>'
      +     '<strong>' + (stats.model_count || 0) + '</strong> models in registry · '
      +     '<strong>' + picksCount + '</strong> PICK winners'
      +   '</p>'
      +   '<p class="ora-models-note">'
      +     'This pane is under construction (install Chunk 10). '
      +     'Subsequent commits add: preset cards, custom configurations, '
      +     'inventory grid with filters + intelligence slider, fallback '
      +     'chain popout, and the local hardware section at the bottom.'
      +   '</p>'
      + '</div>';
  }

  // ── expose ───────────────────────────────────────────────────────────────

  root.OraModelsPane = {
    init: init,
    destroy: destroy,
  };
})(typeof window !== 'undefined' ? window : this);
