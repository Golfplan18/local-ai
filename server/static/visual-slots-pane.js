/**
 * visual-slots-pane.js — V3 Visual tab (install Chunk 11).
 *
 * Replaces the classic ConfigPanel embed inside the V3 Settings →
 * Visual tab. The old grid exposed all ten capability slots with full
 * preferred + reorderable-fallback editors — far more surface than
 * anyone actually configures. This pane shows the two slots users
 * really touch (image_generates, video_generates) as first-class
 * cards, and folds the rest into a collapsed Advanced section where
 * they inherit their routing-config defaults silently.
 *
 * Data sources:
 *   GET /config/routing/slots      — current slots block (routing-config.json)
 *   GET /api/capability/providers  — invokable providers per slot
 *                                    (registry-backed: OpenRouter
 *                                    image/video models + local-diffusers
 *                                    + stability / replicate)
 *
 * Edits autosave per slot via POST /config/routing/slots, which merges
 * {preferred, fallback} into the named slot without touching the rest
 * of the slots block (the schema is unchanged — this pane is a UI-only
 * simplification).
 *
 * Public surface:
 *   OraVisualSlotsPane.init(hostEl)  — mount into a container element
 *   OraVisualSlotsPane.destroy()     — clean up DOM + cached fetches
 */
(function (root) {
  'use strict';

  if (typeof document === 'undefined') return;

  // ── module state ─────────────────────────────────────────────────────────

  var _hostEl = null;
  var _slots = null;        // slots block from /config/routing/slots
  var _providers = null;    // per-slot provider lists from /api/capability/providers

  // The two slots users actually configure. Everything else inherits
  // defaults and lives under the Advanced disclosure.
  var PRIMARY_SLOTS = [
    {
      id: 'image_generates',
      label: 'Image generation',
      hint: 'Used whenever Ora generates a picture — news photos, '
          + 'illustrations, data-viz filler. The preferred model is tried '
          + 'first; the fallback chain catches refusals and outages.',
    },
    {
      id: 'video_generates',
      label: 'Video generation',
      hint: 'Video jobs run async — submission returns immediately, '
          + 'generation takes 30s–10min on the provider.',
    },
  ];

  var ADVANCED_SLOTS = [
    { id: 'image_generates_cartoon', label: 'Editorial cartoons' },
    { id: 'image_edits',             label: 'Image edits' },
    { id: 'image_outpaints',         label: 'Image outpaints' },
    { id: 'image_upscales',          label: 'Image upscales' },
    { id: 'image_styles',            label: 'Image styles' },
    { id: 'image_varies',            label: 'Image variations' },
    { id: 'image_to_prompt',         label: 'Image → prompt' },
    { id: 'image_critique',          label: 'Image critique' },
    { id: 'style_trains',            label: 'Style training' },
  ];

  // ── public API ───────────────────────────────────────────────────────────

  function init(hostEl) {
    _hostEl = hostEl;
    _hostEl.classList.add('ora-visual-slots-pane');
    _hostEl.innerHTML = ''
      + '<div data-section="header"></div>'
      + '<div data-section="primary"></div>'
      + '<div data-section="advanced"></div>';
    _renderHeader('Loading…');
    _loadAll();
  }

  function destroy() {
    if (_hostEl) {
      _hostEl.classList.remove('ora-visual-slots-pane');
      _hostEl.innerHTML = '';
    }
    _hostEl = null;
    _slots = null;
    _providers = null;
  }

  // ── data load ────────────────────────────────────────────────────────────

  function _loadAll() {
    Promise.all([
      fetch('/config/routing/slots').then(_json),
      // Provider discovery is best-effort: if the registry can't load
      // (e.g. missing integration deps), still render the pane with
      // the currently-stored values as the only options.
      fetch('/api/capability/providers').then(_json)
        .catch(function () { return { slots: {} }; }),
    ]).then(function (resp) {
      _slots = (resp[0] && resp[0].slots) || {};
      _providers = (resp[1] && resp[1].slots) || {};
      _renderHeader('');
      _renderPrimary();
      _renderAdvanced();
    }).catch(function (err) {
      _renderHeader('Could not load visual routing: '
        + ((err && err.message) || 'unknown error'), true);
    });
  }

  function _json(r) { return r.json(); }

  // ── rendering ────────────────────────────────────────────────────────────

  function _renderHeader(statusText, isError) {
    var header = _hostEl && _hostEl.querySelector('[data-section="header"]');
    if (!header) return;
    header.innerHTML = ''
      + '<div class="ora-vslots-header">'
      +   '<div class="ora-vslots-title">Visual Generation</div>'
      +   '<div class="ora-vslots-hint">'
      +     'Which model handles image and video generation. '
      +     'Changes auto-save and apply to the next generation.'
      +   '</div>'
      +   '<span class="ora-vslots-status'
      +     (isError ? ' ora-vslots-status--error' : '')
      +     '" data-role="status">' + _esc(statusText || '') + '</span>'
      + '</div>';
  }

  function _setStatus(text, isError) {
    var el = _hostEl && _hostEl.querySelector('[data-role="status"]');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('ora-vslots-status--error', !!isError);
  }

  function _renderPrimary() {
    var section = _hostEl.querySelector('[data-section="primary"]');
    if (!section) return;
    section.innerHTML = PRIMARY_SLOTS.map(function (s) {
      var cfg = _slots[s.id] || {};
      var fallback = Array.isArray(cfg.fallback) ? cfg.fallback : [];
      var rest = fallback.slice(1);
      return ''
        + '<section class="ora-vslots-card" data-slot-card="' + _esc(s.id) + '">'
        +   '<div class="ora-vslots-card-title">' + _esc(s.label) + '</div>'
        +   '<div class="ora-vslots-card-hint">' + _esc(s.hint) + '</div>'
        +   '<label class="ora-vslots-field">'
        +     '<span class="ora-vslots-field-label">Preferred model</span>'
        +     _selectHtml(s.id, 'preferred', cfg.preferred || '',
                          '(no preference — use fallback chain)')
        +   '</label>'
        +   '<label class="ora-vslots-field">'
        +     '<span class="ora-vslots-field-label">If unavailable</span>'
        +     _selectHtml(s.id, 'fallback0', fallback[0] || '', '(none)')
        +   '</label>'
        +   (rest.length
              ? '<div class="ora-vslots-chain">Then: '
                + _esc(rest.map(_displayName).join(' → ')) + '</div>'
              : '')
        + '</section>';
    }).join('');
    _bindSelects(section);
  }

  function _renderAdvanced() {
    var section = _hostEl.querySelector('[data-section="advanced"]');
    if (!section) return;
    // Only rows for slots the config or the registry actually knows.
    var rows = ADVANCED_SLOTS.filter(function (s) {
      return _slots[s.id] !== undefined || _providers[s.id] !== undefined;
    });
    if (!rows.length) { section.innerHTML = ''; return; }
    section.innerHTML = ''
      + '<details class="ora-vslots-advanced">'
      +   '<summary>Advanced routing</summary>'
      +   '<div class="ora-vslots-advanced-hint">'
      +     'These slots inherit sensible defaults — most setups never '
      +     'change them. Fallback chains are managed in '
      +     'config/routing-config.json.'
      +   '</div>'
      +   rows.map(function (s) {
            var cfg = _slots[s.id] || {};
            var fallback = Array.isArray(cfg.fallback) ? cfg.fallback : [];
            return ''
              + '<div class="ora-vslots-row">'
              +   '<span class="ora-vslots-row-label">' + _esc(s.label) + '</span>'
              +   _selectHtml(s.id, 'preferred', cfg.preferred || '',
                              '(no preference)')
              +   '<span class="ora-vslots-row-chain">'
              +     (fallback.length
                      ? 'then ' + _esc(fallback.map(_displayName).join(' → '))
                      : '')
              +   '</span>'
              + '</div>';
          }).join('')
      + '</details>';
    _bindSelects(section);
  }

  // One <select> for a slot field. Candidates come from the provider
  // registry; the currently-stored value is always present even when
  // the registry no longer offers it (rendered with a "not in
  // registry" tag so the user sees the staleness rather than a
  // silently-wrong selection).
  function _selectHtml(slotId, field, current, emptyLabel) {
    var candidates = _candidatesFor(slotId, current);
    var options = ['<option value="">' + _esc(emptyLabel) + '</option>']
      .concat(candidates.map(function (p) {
        var label = p.display_name || p.provider_id;
        if (!p.available) {
          label += p.missing ? ' — not in registry' : ' — not configured';
        }
        return '<option value="' + _esc(p.provider_id) + '"'
          + (p.provider_id === current ? ' selected' : '')
          + '>' + _esc(label) + '</option>';
      }));
    return '<select class="ora-vslots-select" data-slot="' + _esc(slotId)
      + '" data-field="' + _esc(field) + '">' + options.join('') + '</select>';
  }

  function _candidatesFor(slotId, current) {
    var list = _providers[slotId] || [];
    if (current && !list.some(function (p) { return p.provider_id === current; })) {
      list = list.concat([{
        provider_id: current,
        display_name: current,
        available: false,
        missing: true,
      }]);
    }
    // Available providers first, then alphabetical by display name.
    return list.slice().sort(function (a, b) {
      if (!!a.available !== !!b.available) return a.available ? -1 : 1;
      var an = (a.display_name || a.provider_id).toLowerCase();
      var bn = (b.display_name || b.provider_id).toLowerCase();
      return an < bn ? -1 : an > bn ? 1 : 0;
    });
  }

  function _displayName(providerId) {
    for (var slot in _providers) {
      var list = _providers[slot] || [];
      for (var i = 0; i < list.length; i++) {
        if (list[i].provider_id === providerId) {
          // Strip the pricing suffix the providers endpoint appends —
          // the chain line is informational, keep it short.
          return (list[i].display_name || providerId).replace(/\s+\(\$.*\)$/, '');
        }
      }
    }
    return providerId;
  }

  // ── edits ────────────────────────────────────────────────────────────────

  function _bindSelects(scope) {
    var selects = scope.querySelectorAll('select[data-slot]');
    Array.prototype.forEach.call(selects, function (sel) {
      sel.addEventListener('change', function () {
        _applyEdit(sel.dataset.slot, sel.dataset.field, sel.value);
      });
    });
  }

  function _applyEdit(slotId, field, value) {
    var cfg = _slots[slotId] || (_slots[slotId] = {});
    var fallback = Array.isArray(cfg.fallback) ? cfg.fallback.slice() : [];

    if (field === 'preferred') {
      cfg.preferred = value || null;
      // The new preferred would be redundant in the fallback chain —
      // drop it there so the chain stays a clean "what to try next".
      if (value) {
        fallback = fallback.filter(function (pid) { return pid !== value; });
      }
      cfg.fallback = fallback;
    } else if (field === 'fallback0') {
      var rest = fallback.slice(1);
      cfg.fallback = value ? [value].concat(rest.filter(function (pid) {
        return pid !== value;
      })) : rest;
    }

    _save(slotId, cfg);
    _renderPrimary();
    _renderAdvanced();
  }

  function _save(slotId, cfg) {
    _setStatus('Saving…');
    var patch = {};
    patch[slotId] = { preferred: cfg.preferred || null, fallback: cfg.fallback || [] };
    fetch('/config/routing/slots', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slots: patch }),
    }).then(_json).then(function (resp) {
      if (resp && resp.ok) {
        _setStatus('Saved ✓');
      } else {
        _setStatus('Save failed: ' + ((resp && resp.error) || 'unknown error'), true);
      }
    }).catch(function (err) {
      _setStatus('Save failed: ' + ((err && err.message) || 'network error'), true);
    });
  }

  // ── utilities ────────────────────────────────────────────────────────────

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

  root.OraVisualSlotsPane = {
    init: init,
    destroy: destroy,
  };
})(typeof window !== 'undefined' ? window : this);
