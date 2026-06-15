/**
 * visual-slots-pane.js — V3 Visual tab (install Chunk 11).
 *
 * Replaces the classic ConfigPanel embed inside the V3 Settings →
 * Visual tab. The old grid exposed all ten capability slots with full
 * preferred + reorderable-fallback editors — far more surface than
 * anyone actually configures. This pane is a two-column layout: the
 * two slots users really touch (image_generates, video_generates) as
 * first-class cards on the left, and the remaining specialized slots
 * exposed in an Advanced routing column on the right (the modal is
 * wide — space is not the constraint; comprehension is).
 *
 * Data sources:
 *   GET /config/routing/slots            — current slots block (routing-config.json)
 *   GET /api/capability/providers        — invokable providers per slot
 *                                          (registry-backed: OpenRouter
 *                                          image/video models + local-diffusers
 *                                          + stability / replicate)
 *   GET /static/config/capabilities.json — slot contracts; the `summary`
 *                                          field captions each Advanced row
 *
 * Edits autosave per slot via POST /config/routing/slots, which merges
 * {preferred, fallback} into the named slot without touching the rest
 * of the slots block (the schema is unchanged — this pane is a UI-only
 * simplification).
 *
 * Every slot (primary cards and Advanced rows alike) gets the same
 * editing surface: a preferred-model select plus a fallback-chain
 * editor (removable chips + an "add fallback" select). When the
 * selected provider isn't usable yet, the row explains why (the
 * provider registry's `reason` string) and, for API-key problems,
 * offers a jump to Settings → External APIs.
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
  var _summaries = null;    // slot → one-line summary from capabilities.json

  // The two slots users actually configure. Everything else inherits
  // defaults and lives in the Advanced routing column.
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
          + 'generation takes 30s–10min on the provider. OpenRouter bills '
          + 'video per output second and does not publish those rates '
          + 'through its API, so no price tag is shown here — check '
          + 'openrouter.ai for current per-video costs.',
    },
  ];

  var ADVANCED_SLOTS = [
    { id: 'vision_input',            label: 'Vision input (image reading)' },
    // Editorial cartoons (image_generates_cartoon) is deliberately NOT exposed
    // here — it's an MSI-specific capability, not something a general user
    // configures. The slot still exists in routing-config and its pipeline runs;
    // it's just not a UI control on this tab.
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
    _summaries = null;
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
      // Slot contracts caption the Advanced rows; absence is cosmetic.
      fetch('/static/config/capabilities.json').then(_json)
        .catch(function () { return { slots: {} }; }),
    ]).then(function (resp) {
      _slots = (resp[0] && resp[0].slots) || {};
      _providers = (resp[1] && resp[1].slots) || {};
      _summaries = {};
      var contracts = (resp[2] && resp[2].slots) || {};
      Object.keys(contracts).forEach(function (name) {
        if (contracts[name] && contracts[name].summary) {
          _summaries[name] = contracts[name].summary;
        }
      });
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
      return ''
        + '<section class="ora-vslots-card" data-slot-card="' + _esc(s.id) + '">'
        +   '<div class="ora-vslots-card-title">' + _esc(s.label) + '</div>'
        +   '<div class="ora-vslots-card-hint">' + _esc(s.hint) + '</div>'
        +   '<label class="ora-vslots-field">'
        +     '<span class="ora-vslots-field-label">Preferred model</span>'
        +     _selectHtml(s.id, 'preferred', cfg.preferred || '',
                          '(no preference — use fallback chain)')
        +   '</label>'
        +   '<div class="ora-vslots-field">'
        +     '<span class="ora-vslots-field-label">If unavailable, try in order</span>'
        +     _chainEditorHtml(s.id, cfg.preferred || '', fallback)
        +   '</div>'
        +   _providerNoticeHtml(s.id, cfg.preferred || '')
        + '</section>';
    }).join('');
    _bindEditors(section);
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
      + '<section class="ora-vslots-advanced">'
      +   '<div class="ora-vslots-advanced-title">Advanced routing</div>'
      +   '<div class="ora-vslots-advanced-hint">'
      +     'Specialized image operations. Each one picks its own provider '
      +     'because not every model supports every operation — these '
      +     'inherit working defaults, so change them only if you want a '
      +     'specific capability handled by a specific provider.'
      +   '</div>'
      +   rows.map(function (s) {
            var cfg = _slots[s.id] || {};
            var fallback = Array.isArray(cfg.fallback) ? cfg.fallback : [];
            var off = !cfg.preferred && !fallback.length;
            return ''
              + '<div class="ora-vslots-row" data-adv-row="' + _esc(s.id) + '">'
              +   '<div class="ora-vslots-row-top">'
              +     '<span class="ora-vslots-row-label">' + _esc(s.label) + '</span>'
              +     _selectHtml(s.id, 'preferred', cfg.preferred || '', '(none)')
              +     '<span class="ora-vslots-row-chain">'
              +       (off
                        ? '<span class="ora-vslots-off">off — no provider set</span>'
                        : _chainEditorHtml(s.id, cfg.preferred || '', fallback, true))
              +     '</span>'
              +   '</div>'
              +   (_summaries[s.id]
                    ? '<div class="ora-vslots-row-hint">' + _esc(_summaries[s.id]) + '</div>'
                    : '')
              +   _providerNoticeHtml(s.id, cfg.preferred || '')
              + '</div>';
          }).join('')
      + '</section>';
    _bindEditors(section);
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
          label += p.missing ? ' — not in registry' : ' — needs setup';
        }
        return '<option value="' + _esc(p.provider_id) + '"'
          + (p.provider_id === current ? ' selected' : '')
          + '>' + _esc(label) + '</option>';
      }));
    return '<select class="ora-vslots-select" data-slot="' + _esc(slotId)
      + '" data-field="' + _esc(field) + '">' + options.join('') + '</select>';
  }

  // The fallback-chain editor: one removable chip per chain entry plus
  // an "add" select offering every provider not already in use. This is
  // how users extend routing beyond preferred + first fallback.
  function _chainEditorHtml(slotId, preferred, fallback, compact) {
    var used = {};
    if (preferred) used[preferred] = true;
    fallback.forEach(function (pid) { used[pid] = true; });
    var addable = _candidatesFor(slotId, '').filter(function (p) {
      return !used[p.provider_id] && !p.missing;
    });

    var chips = fallback.map(function (pid, i) {
      var entry = _providerEntry(slotId, pid);
      var stale = !entry;
      return '<span class="ora-vslots-chip'
        + (stale ? ' ora-vslots-chip--stale' : '') + '"'
        + (stale ? ' title="not in registry"' : '') + '>'
        + _esc(_displayName(pid))
        + '<button type="button" class="ora-vslots-chip-x" '
        +   'data-action="chain-remove" data-slot="' + _esc(slotId) + '" '
        +   'data-index="' + i + '" aria-label="Remove fallback">×</button>'
        + '</span>';
    });

    var addSelect = '';
    if (addable.length) {
      addSelect = '<select class="ora-vslots-select ora-vslots-select--add" '
        + 'data-slot="' + _esc(slotId) + '" data-field="chain-add">'
        + '<option value="">+ add fallback</option>'
        + addable.map(function (p) {
            var label = p.display_name || p.provider_id;
            if (!p.available) label += ' — needs setup';
            return '<option value="' + _esc(p.provider_id) + '">'
              + _esc(label) + '</option>';
          }).join('')
        + '</select>';
    }

    return '<span class="ora-vslots-chainedit'
      + (compact ? ' ora-vslots-chainedit--compact' : '') + '">'
      + (chips.length ? chips.join('<span class="ora-vslots-chain-sep">→</span>') : '')
      + addSelect
      + '</span>';
  }

  // Inline notice under a slot's editors when the chosen preferred
  // provider needs attention: either setup guidance (API key missing,
  // package not installed) with a jump to the External APIs tab when
  // a key is the problem, or an informational note (e.g. video runs
  // async and needs OpenRouter credits).
  function _providerNoticeHtml(slotId, preferred) {
    if (!preferred) return '';
    var entry = _providerEntry(slotId, preferred);
    if (!entry || !entry.reason) return '';
    var needsKey = /External APIs/i.test(entry.reason);
    var cls = entry.available ? 'ora-vslots-notice' : 'ora-vslots-notice ora-vslots-notice--warn';
    return '<div class="' + cls + '">'
      + (entry.available ? '' : '⚠ ')
      + _esc(entry.reason)
      + (needsKey
          ? ' <button type="button" class="ora-vslots-link" '
            + 'data-action="open-apis" data-reason="' + _esc(entry.reason) + '"'
            + '>Open External APIs →</button>'
          : '')
      + '</div>';
  }

  function _providerEntry(slotId, providerId) {
    var list = _providers[slotId] || [];
    for (var i = 0; i < list.length; i++) {
      if (list[i].provider_id === providerId) return list[i];
    }
    return null;
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
          // the chain chips are informational, keep them short.
          return (list[i].display_name || providerId).replace(/\s+\(\$.*\)$/, '');
        }
      }
    }
    return providerId;
  }

  // ── edits ────────────────────────────────────────────────────────────────

  function _bindEditors(scope) {
    var selects = scope.querySelectorAll('select[data-slot]');
    Array.prototype.forEach.call(selects, function (sel) {
      sel.addEventListener('change', function () {
        _applyEdit(sel.dataset.slot, sel.dataset.field, sel.value);
      });
    });
    var removes = scope.querySelectorAll('[data-action="chain-remove"]');
    Array.prototype.forEach.call(removes, function (btn) {
      btn.addEventListener('click', function () {
        _removeFromChain(btn.dataset.slot, parseInt(btn.dataset.index, 10));
      });
    });
    var apiLinks = scope.querySelectorAll('[data-action="open-apis"]');
    Array.prototype.forEach.call(apiLinks, function (btn) {
      btn.addEventListener('click', function () {
        // The settings panel listens for this event (deferrals row 52):
        // it switches to the External APIs tab and highlights the key
        // row for whichever provider it can extract from the message.
        document.dispatchEvent(new CustomEvent('open-settings', {
          detail: { message: btn.dataset.reason || '' },
        }));
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
    } else if (field === 'chain-add') {
      if (!value) return;
      if (fallback.indexOf(value) === -1) fallback.push(value);
      cfg.fallback = fallback;
    } else {
      return;
    }

    _save(slotId, cfg);
    _renderPrimary();
    _renderAdvanced();
  }

  function _removeFromChain(slotId, index) {
    var cfg = _slots[slotId];
    if (!cfg || !Array.isArray(cfg.fallback)) return;
    var fallback = cfg.fallback.slice();
    if (index < 0 || index >= fallback.length) return;
    fallback.splice(index, 1);
    cfg.fallback = fallback;
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
