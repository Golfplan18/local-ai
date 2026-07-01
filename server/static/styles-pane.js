/* Output Styles configurator — mirrors the Models tab.
 *
 *   OraStylesPane.init(hostEl)  — mount into a container element
 *   OraStylesPane.destroy()      — clean up
 *
 * The Output Styles tab lets you pick a whole style configuration the way the
 * Models tab lets you pick a model configuration: genre PRESETS (click a card to
 * make it your default; Customize forks an editable copy), saved CUSTOM profiles
 * (+ new profile; each line editable), and a component LIBRARY explained beneath.
 * A profile card's four headline slots mirror BIG/FAST/SMALL: Arrangement ·
 * Demeanor · Elaboration · Register. "more" expands the full seven demeanor axes,
 * device overlays, and glossary.
 *
 * Data: GET /api/styles/registry → {profiles, custom, library, settings}.
 * Mutations: POST /api/settings (activate + toggles), POST/PATCH/DELETE
 * /api/styles/custom (fork / edit a line / remove). Any single turn still
 * overrides the default by typing `/style <id>` (or `/style off`) in the chat.
 */
(function (root) {
  'use strict';

  if (typeof document === 'undefined') return;

  // ── module state ──────────────────────────────────────────────────────────
  var _host = null;
  var _data = null;              // last /api/styles/registry payload
  var _expanded = new Set();     // profile ids with "more" open
  var _editingSlot = null;       // "id::field" whose inline picker is open
  var _openLib = new Set();      // library section ids currently expanded
  var _fictionOpen = false;

  var AXIS_LABELS = {
    warmth: 'warmth', force: 'force', energy: 'energy', outlook: 'outlook',
    playfulness: 'playfulness', directness: 'directness', agreeableness: 'agreeableness',
  };
  var DEVICE_LABELS = {
    sarcasm: 'sarcasm', irony: 'irony', hyperbole: 'hyperbole', understatement: 'understatement',
  };
  var LIB_SECTIONS = [
    { id: 'axes',        title: 'demeanor axes',              hint: '7 · three rungs each (pole · neutral · pole)' },
    { id: 'schemas',     title: 'arrangement schemas',        hint: '12 · ordered slot-lists per genre' },
    { id: 'devices',     title: 'device overlays',            hint: 'sarcasm, irony, hyperbole, understatement' },
    { id: 'elaboration', title: 'completeness + elaboration', hint: 'never drop content; dial the examples' },
    { id: 'glossary',    title: 'project glossary',           hint: 'required · forbidden · canonical terms' },
  ];

  // ── small utils ───────────────────────────────────────────────────────────
  function _json(r) { return r.json(); }
  function _esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function _get() {
    return fetch('/api/styles/registry').then(_json)
      .catch(function () { return { profiles: [], custom: [], library: {}, settings: {} }; });
  }
  function _saveSettings(styles) {
    return fetch('/api/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ updates: { styles: styles } }),
    }).then(_json);
  }
  function _fork(fromId) {
    return fetch('/api/styles/custom', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ forked_from: fromId || '' }),
    }).then(_json);
  }
  function _patch(id, patch) {
    return fetch('/api/styles/custom/' + encodeURIComponent(id), {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patch: patch }),
    }).then(_json);
  }
  function _delete(id) {
    return fetch('/api/styles/custom/' + encodeURIComponent(id), { method: 'DELETE' }).then(_json);
  }
  function _status(msg) {
    var el = _host && _host.querySelector('[data-role="status"]');
    if (el) el.textContent = msg || '';
  }
  function _profileById(id) {
    if (!_data || !id) return null;
    var all = (_data.profiles || []).concat(_data.custom || []);
    for (var i = 0; i < all.length; i++) if (all[i].id === id) return all[i];
    return null;
  }

  // ── public API ────────────────────────────────────────────────────────────
  function init(host) {
    if (!host) return;
    _host = host;
    host.classList.add('ora-styles-host-mounted');
    host.innerHTML = '<p class="ora-styles-loading">Loading Output Styles…</p>';
    _reload();
  }
  function destroy() {
    if (_host) { _host.classList.remove('ora-styles-host-mounted'); _host.innerHTML = ''; _host = null; }
    _data = null; _expanded = new Set(); _editingSlot = null; _openLib = new Set(); _fictionOpen = false;
  }
  function _reload() {
    var host = _host;
    return _get().then(function (data) {
      if (_host !== host) return;          // a later mount/destroy superseded us
      _data = data || { profiles: [], custom: [], library: {}, settings: {} };
      _render();
    });
  }

  // ── render ────────────────────────────────────────────────────────────────
  function _render() {
    if (!_host) return;
    var d = _data || {};
    var profiles = d.profiles || [], custom = d.custom || [];
    if (!profiles.length && !custom.length) {
      _host.innerHTML = '<p class="ora-styles-empty">No Output Style profiles found '
        + '(the style registry is unavailable).</p>';
      return;
    }
    _host.innerHTML =
      '<div class="ora-styles-pane">'
      + _headerHTML()
      + _presetsHTML()
      + _customHTML()
      + _libraryHTML()
      + _fictionHTML()
      + '<p class="ora-styles-status" data-role="status" aria-live="polite"></p>'
      + '</div>';
    _wire();
  }

  function _headerHTML() {
    var s = (_data && _data.settings) || {};
    var active = _profileById(s.default_id);
    var activeName = active ? active.display_name : 'None';
    return ''
      + '<section class="ora-styles-header">'
      +   '<div class="ora-styles-active">'
      +     '<span class="ora-styles-active-label">Active:</span> '
      +     '<strong class="ora-styles-active-name">' + _esc(activeName) + '</strong>'
      +   '</div>'
      +   _switchHTML('use_custom_values', !!s.use_custom_values,
                      'custom values', '(mind.md)',
                      'compose the voice from your mind.md, not the default')
      +   _switchHTML('adapt_to_context', s.adapt_to_context !== false,
                      'adapt to context', '',
                      'loosen for chats, tighten for documents')
      + '</section>';
  }

  function _switchHTML(name, on, label, sub, help) {
    return ''
      + '<label class="ora-styles-switch">'
      +   '<input type="checkbox" data-toggle="' + name + '"' + (on ? ' checked' : '') + '>'
      +   '<span class="ora-styles-switch-knob"></span>'
      +   '<span class="ora-styles-switch-label">' + _esc(label)
      +     (sub ? ' <span class="ora-styles-switch-sub">' + _esc(sub) + '</span>' : '')
      +   '</span>'
      +   '<span class="ora-styles-switch-help">— ' + _esc(help) + '</span>'
      + '</label>';
  }

  function _presetsHTML() {
    var profiles = (_data && _data.profiles) || [];
    var cards = profiles.map(function (p) { return _cardHTML(p, false); }).join('');
    return ''
      + '<section class="ora-styles-section" data-section="presets">'
      +   '<header class="ora-styles-section-head">'
      +     '<h3>Presets — genres</h3>'
      +     '<span class="ora-styles-section-hint">click to activate · Customize to fork</span>'
      +   '</header>'
      +   '<div class="ora-styles-grid">' + cards + '</div>'
      + '</section>';
  }

  function _customHTML() {
    var custom = (_data && _data.custom) || [];
    var cards = custom.map(function (p) { return _cardHTML(p, true); }).join('');
    cards += ''
      + '<button type="button" class="ora-styles-card ora-styles-card-new" data-action="new">'
      +   '<span class="ora-styles-card-new-plus">+ new profile</span>'
      + '</button>';
    return ''
      + '<section class="ora-styles-section" data-section="custom">'
      +   '<header class="ora-styles-section-head">'
      +     '<h3>Custom profiles</h3>'
      +     '<span class="ora-styles-section-hint">forked + saved · one active</span>'
      +   '</header>'
      +   '<div class="ora-styles-grid">' + cards + '</div>'
      + '</section>';
  }

  function _cardHTML(p, isCustom) {
    var s = (_data && _data.settings) || {};
    var active = (s.default_id && s.default_id === p.id);
    var sub = isCustom
      ? (p.forked_from ? 'from ' + p.forked_from : 'custom')
      : (p.description || '');
    var cls = 'ora-styles-card' + (active ? ' ora-styles-card-active' : '')
      + (isCustom ? ' ora-styles-card-custom' : '');
    return ''
      + '<div class="' + cls + '" data-id="' + _esc(p.id) + '"'
      +   (isCustom ? ' data-custom="1"' : '') + '>'
      +   '<header class="ora-styles-card-head" data-action="activate" data-id="' + _esc(p.id) + '">'
      +     '<span class="ora-styles-card-title">' + _esc(p.display_name) + '</span>'
      +     (active ? '<span class="ora-styles-card-flag">active</span>' : '')
      +   '</header>'
      +   '<div class="ora-styles-card-sub">' + _esc(sub) + '</div>'
      +   '<div class="ora-styles-card-slots">'
      +     _slotHTML(p, 'arrangement', 'arrangement', p.arrangement_label, isCustom)
      +     _slotHTML(p, 'demeanor', 'demeanor', p.demeanor_label, isCustom)
      +     _slotHTML(p, 'elaboration', 'elaboration', p.elaboration_label, isCustom)
      +     _slotHTML(p, 'register', 'register', p.register, isCustom)
      +   '</div>'
      +   (_expanded.has(p.id) ? _moreHTML(p, isCustom) : '')
      +   '<div class="ora-styles-card-actions">'
      +     '<button type="button" class="ora-styles-link" data-action="more" data-id="' + _esc(p.id) + '">'
      +       (_expanded.has(p.id) ? 'less' : 'more') + '</button>'
      +     (isCustom
        ? '<button type="button" class="ora-styles-link" data-action="delete" data-id="' + _esc(p.id) + '">delete</button>'
        : '<button type="button" class="ora-styles-link" data-action="customize" data-from="' + _esc(p.id) + '">customize</button>')
      +   '</div>'
      + '</div>';
  }

  // One headline slot row. ``slot`` is the display label; ``field`` is the logical
  // field. Custom cards make arrange/elabor/register single-pick (inline list);
  // demeanor opens the "more" editor (seven axes). Presets are read-only.
  function _slotHTML(p, slot, field, value, isCustom) {
    var key = p.id + '::' + field;
    var act = '';
    if (isCustom) act = (field === 'demeanor')
      ? ' data-action="more" data-id="' + _esc(p.id) + '"'
      : ' data-action="edit-slot" data-id="' + _esc(p.id) + '" data-slot="' + _esc(field) + '"';
    var picking = (_editingSlot === key);
    var row = ''
      + '<div class="ora-styles-slot' + (isCustom ? ' ora-styles-slot-editable' : '')
      +   (picking ? ' ora-styles-slot-picking' : '') + '"' + act + '>'
      +   '<span class="ora-styles-slot-label">' + _esc(slot) + '</span>'
      +   '<span class="ora-styles-slot-value">' + _esc(value || '—') + '</span>'
      + '</div>';
    if (picking && field !== 'demeanor') row += _pickerHTML(p, field);
    return row;
  }

  // Inline option list for a single-pick slot (arrangement / register / elaboration).
  function _pickerHTML(p, field) {
    var lib = (_data && _data.library) || {};
    var opts = [];
    if (field === 'arrangement') {
      opts = (lib.schemas || []).map(function (s) { return { value: s.id, label: s.label || s.id }; });
    } else if (field === 'register') {
      opts = (lib.registers || []).map(function (r) { return { value: r.id, label: r.label || r.id }; });
    } else if (field === 'elaboration') {
      opts = (lib.elaboration_scale || []).map(function (e) { return { value: e.value, label: e.label }; });
    }
    var cur = (field === 'register') ? p.register : p[field];
    var items = opts.map(function (o) {
      var on = (String(o.value) === String(cur));
      return '<button type="button" class="ora-styles-opt' + (on ? ' ora-styles-opt-on' : '') + '"'
        + ' data-action="pick" data-id="' + _esc(p.id) + '" data-slot="' + _esc(field) + '"'
        + ' data-value="' + _esc(o.value) + '">' + _esc(o.label) + '</button>';
    }).join('');
    return '<div class="ora-styles-picker">' + items + '</div>';
  }

  // The "more" expand: the seven demeanor axes (rung chips), device overlays,
  // and — on a custom card — editable name / description / glossary.
  function _moreHTML(p, isCustom) {
    var lib = (_data && _data.library) || {};
    var axes = lib.axes || [];
    var devices = lib.devices || [];
    var rows = '';

    if (isCustom) {
      rows += ''
        + '<div class="ora-styles-more-ident">'
        +   '<input type="text" class="ora-styles-input" data-field="display_name" data-id="' + _esc(p.id) + '"'
        +     ' value="' + _esc(p.display_name) + '" placeholder="profile name">'
        +   '<input type="text" class="ora-styles-input" data-field="description" data-id="' + _esc(p.id) + '"'
        +     ' value="' + _esc(p.description) + '" placeholder="one-line description">'
        + '</div>';
    }

    rows += '<div class="ora-styles-more-label">demeanor axes</div>';
    axes.forEach(function (ax) {
      var picks = p.demeanor || {};
      var cur = picks[ax.id];
      var chips = (ax.rungs || []).map(function (r) {
        var on = (r.id === cur);
        var attr = isCustom
          ? ' data-action="pick-axis" data-id="' + _esc(p.id) + '" data-axis="' + _esc(ax.id) + '" data-rung="' + _esc(r.id) + '"'
          : '';
        return '<button type="button" class="ora-styles-rung' + (on ? ' ora-styles-rung-on' : '')
          + (isCustom ? '' : ' ora-styles-rung-ro') + '"' + attr
          + ' title="' + _esc(r.text) + '">' + _esc(r.id) + '</button>';
      }).join('');
      rows += '<div class="ora-styles-axis-row">'
        + '<span class="ora-styles-axis-name">' + _esc(AXIS_LABELS[ax.id] || ax.id) + '</span>'
        + '<span class="ora-styles-axis-rungs">' + chips + '</span>'
        + '</div>';
    });

    if (devices.length) {
      rows += '<div class="ora-styles-more-label">device overlays</div><div class="ora-styles-devices">';
      devices.forEach(function (dv) {
        var on = !!(p.devices && p.devices[dv.id]);
        rows += '<label class="ora-styles-device" title="' + _esc(dv.text) + '">'
          + '<input type="checkbox"' + (on ? ' checked' : '') + (isCustom ? '' : ' disabled')
          + ' data-action="device" data-id="' + _esc(p.id) + '" data-device="' + _esc(dv.id) + '">'
          + _esc(DEVICE_LABELS[dv.id] || dv.id) + '</label>';
      });
      rows += '</div>';
    }

    // Glossary — editable comma lists on a custom card, read-only otherwise.
    var gl = p.glossary || {};
    var forb = (gl.forbidden || []).join(', ');
    var req = (gl.required || []).join(', ');
    rows += '<div class="ora-styles-more-label">project glossary</div>';
    if (isCustom) {
      rows += '<div class="ora-styles-gloss">'
        + '<label>forbidden <input type="text" class="ora-styles-input" data-field="glossary.forbidden" data-id="' + _esc(p.id) + '" value="' + _esc(forb) + '" placeholder="comma, separated"></label>'
        + '<label>required <input type="text" class="ora-styles-input" data-field="glossary.required" data-id="' + _esc(p.id) + '" value="' + _esc(req) + '" placeholder="comma, separated"></label>'
        + '</div>';
    } else {
      rows += '<div class="ora-styles-gloss-ro">'
        + (forb ? 'avoid: ' + _esc(forb) : '')
        + (forb && req ? ' · ' : '')
        + (req ? 'use: ' + _esc(req) : '')
        + (!forb && !req ? '—' : '')
        + '</div>';
    }

    return '<div class="ora-styles-more">' + rows + '</div>';
  }

  function _libraryHTML() {
    var lib = (_data && _data.library) || {};
    var sections = LIB_SECTIONS.map(function (sec) {
      var open = _openLib.has(sec.id);
      return ''
        + '<div class="ora-styles-lib-row">'
        +   '<button type="button" class="ora-styles-lib-head" data-action="lib" data-section="' + sec.id + '">'
        +     '<span class="ora-styles-lib-caret">' + (open ? '▾' : '▸') + '</span> '
        +     '<span class="ora-styles-lib-title">' + _esc(sec.title) + '</span>'
        +     '<span class="ora-styles-lib-hint">' + _esc(sec.hint) + '</span>'
        +   '</button>'
        +   (open ? '<div class="ora-styles-lib-body">' + _libBody(sec.id, lib) + '</div>' : '')
        + '</div>';
    }).join('');
    return ''
      + '<section class="ora-styles-section ora-styles-library">'
      +   '<header class="ora-styles-section-head">'
      +     '<h3>Component library</h3>'
      +     '<span class="ora-styles-section-hint">the building blocks, explained</span>'
      +   '</header>'
      +   sections
      + '</section>';
  }

  function _libBody(id, lib) {
    if (id === 'axes') {
      return (lib.axes || []).map(function (ax) {
        var rungs = (ax.rungs || []).map(function (r) {
          return '<div class="ora-styles-lib-rung"><strong>' + _esc(r.id) + '</strong> — ' + _esc(r.text) + '</div>';
        }).join('');
        return '<div class="ora-styles-lib-axis"><div class="ora-styles-lib-axis-name">'
          + _esc(AXIS_LABELS[ax.id] || ax.id) + '</div>' + rungs + '</div>';
      }).join('');
    }
    if (id === 'schemas') {
      return (lib.schemas || []).map(function (s) {
        return '<div class="ora-styles-lib-item"><strong>' + _esc(s.label || s.id) + '</strong> — '
          + _esc(s.text) + '</div>';
      }).join('');
    }
    if (id === 'devices') {
      return (lib.devices || []).map(function (dv) {
        return '<div class="ora-styles-lib-item"><strong>' + _esc(dv.id) + '</strong> — ' + _esc(dv.text) + '</div>';
      }).join('');
    }
    if (id === 'elaboration') {
      var craft = (lib.craft || []).map(function (c) { return '<li>' + _esc(c) + '</li>'; }).join('');
      var scale = (lib.elaboration_scale || []).map(function (e) {
        return '<span class="ora-styles-scale-pip">' + e.value + ' · ' + _esc(e.label) + '</span>';
      }).join('');
      return '<div class="ora-styles-lib-item"><strong>Craft + completeness floor</strong><ul class="ora-styles-craft">'
        + craft + '</ul></div>'
        + '<div class="ora-styles-lib-item"><strong>Elaboration dial</strong><div class="ora-styles-scale">'
        + scale + '</div></div>';
    }
    if (id === 'glossary') {
      return '<div class="ora-styles-lib-item">A per-profile word list: <strong>forbidden</strong> terms to '
        + 'avoid, <strong>required</strong> terms to use, and <strong>canonical</strong> spellings. The project '
        + 'layer is where house terminology and the AI→AHI discipline live; it persists across situational shifts. '
        + 'Edit a custom profile’s glossary in its “more” view.</div>';
    }
    return '';
  }

  function _fictionHTML() {
    return ''
      + '<section class="ora-styles-fiction' + (_fictionOpen ? ' ora-styles-fiction-open' : '') + '">'
      +   '<button type="button" class="ora-styles-fiction-head" data-action="fiction">'
      +     '<span class="ora-styles-fiction-title">📖 Fiction register (advanced)</span>'
      +     '<span class="ora-styles-fiction-sub">POV · tense · narrator · per-character voices</span>'
      +     '<span class="ora-styles-fiction-flag">overrides values floor · off</span>'
      +     '<span class="ora-styles-fiction-caret">' + (_fictionOpen ? '▾' : '▸') + '</span>'
      +   '</button>'
      +   (_fictionOpen
        ? '<div class="ora-styles-fiction-body">Fiction is a separate skeleton that lifts the values and '
          + 'craft floors for characters inside a story (a character may lie, obscure, or be cruel; the system '
          + 'stays honest that it is fiction). It adds POV, tense, narrator stance, dialogue convention, and a '
          + 'per-character voice table. <strong>Deferred — not built yet.</strong></div>'
        : '')
      + '</section>';
  }

  // ── event wiring ──────────────────────────────────────────────────────────
  function _wire() {
    if (!_host) return;
    var pane = _host.querySelector('.ora-styles-pane');
    if (!pane) return;
    pane.addEventListener('click', _onClick);
    pane.addEventListener('change', _onChange);
    pane.addEventListener('keydown', _onKeydown);
    Array.prototype.forEach.call(pane.querySelectorAll('input[type="text"][data-field]'), function (el) {
      el.addEventListener('blur', function () { _commitField(el); });
    });
  }

  function _onKeydown(evt) {
    var el = evt.target;
    if (el && el.tagName === 'INPUT' && el.type === 'text' && el.dataset.field && evt.key === 'Enter') {
      evt.preventDefault();
      _commitField(el);
      el.blur();
    }
    if (evt.key === 'Escape' && _editingSlot) { _editingSlot = null; _render(); }
  }

  function _onClick(evt) {
    var t = evt.target.closest('[data-action]');
    if (!t) return;
    var a = t.dataset.action, id = t.dataset.id;
    if (a === 'activate')   { _activate(id); }
    else if (a === 'more')  { _toggle(_expanded, id); _editingSlot = null; _render(); }
    else if (a === 'customize') { _doFork(t.dataset.from); }
    else if (a === 'new')   { _doFork(''); }
    else if (a === 'delete') { _doDelete(id); }
    else if (a === 'edit-slot') {
      var key = id + '::' + t.dataset.slot;
      _editingSlot = (_editingSlot === key) ? null : key;
      _render();
    }
    else if (a === 'pick')      { _pickSlot(id, t.dataset.slot, t.dataset.value); }
    else if (a === 'pick-axis') { _pickAxis(id, t.dataset.axis, t.dataset.rung); }
    else if (a === 'lib')       { _toggle(_openLib, t.dataset.section); _render(); }
    else if (a === 'fiction')   { _fictionOpen = !_fictionOpen; _render(); }
  }

  function _onChange(evt) {
    var el = evt.target;
    if (el.dataset.toggle) {
      var styles = {}; styles[el.dataset.toggle] = el.checked;
      _status('Saving…');
      _saveSettings(styles).then(function () { return _reload(); })
        .then(function () { _status(''); })
        .catch(function () { _status('Could not save — try again.'); });
    } else if (el.dataset.action === 'device') {
      var dev = {}; dev[el.dataset.device] = el.checked;
      _status('Saving…');
      _patch(el.dataset.id, { devices: dev }).then(function () { return _reload(); })
        .then(function () { _status(''); })
        .catch(function () { _status('Could not save — try again.'); });
    }
  }

  function _commitField(el) {
    var id = el.dataset.id, field = el.dataset.field, val = el.value;
    var patch = {};
    if (field === 'glossary.forbidden' || field === 'glossary.required') {
      var key = field.split('.')[1];
      var list = val.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
      var g = {}; g[key] = list; patch.glossary = g;
    } else {
      patch[field] = val;
    }
    _status('Saving…');
    _patch(id, patch).then(function () { return _reload(); })
      .then(function () { _status(''); })
      .catch(function () { _status('Could not save — try again.'); });
  }

  // ── actions ───────────────────────────────────────────────────────────────
  function _toggle(set, key) { if (set.has(key)) set.delete(key); else set.add(key); }

  function _activate(id) {
    _status('Saving…');
    _saveSettings({ default_id: id || '' }).then(function () { return _reload(); })
      .then(function () { _status(''); })
      .catch(function () { _status('Could not save — try again.'); });
  }

  function _doFork(fromId) {
    _status('Creating…');
    _fork(fromId).then(function (resp) {
      var np = resp && resp.profile;
      if (np && np.id) _expanded.add(np.id);   // open the new card for editing
      return _reload();
    }).then(function () { _status(''); })
      .catch(function () { _status('Could not create — try again.'); });
  }

  function _doDelete(id) {
    var p = _profileById(id);
    var name = p ? p.display_name : id;
    if (typeof window !== 'undefined' && window.confirm
        && !window.confirm('Delete the custom profile “' + name + '”?')) return;
    _status('Deleting…');
    _delete(id).then(function () { _expanded.delete(id); return _reload(); })
      .then(function () { _status(''); })
      .catch(function () { _status('Could not delete — try again.'); });
  }

  function _pickSlot(id, field, value) {
    var patch = {};
    if (field === 'arrangement') patch.arrangement = value;
    else if (field === 'register') patch.register_default = value;
    else if (field === 'elaboration') patch.elaboration = parseInt(value, 10);
    _editingSlot = null;
    _status('Saving…');
    _patch(id, patch).then(function () { return _reload(); })
      .then(function () { _status(''); })
      .catch(function () { _status('Could not save — try again.'); });
  }

  function _pickAxis(id, axis, rung) {
    var dem = {}; dem[axis] = rung;
    _status('Saving…');
    _patch(id, { demeanor: dem }).then(function () { return _reload(); })
      .then(function () { _status(''); })
      .catch(function () { _status('Could not save — try again.'); });
  }

  root.OraStylesPane = { init: init, destroy: destroy };
})(typeof window !== 'undefined' ? window : this);
