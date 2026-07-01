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
  var _convFor = null;           // profile id whose conversational popout is open
  var _mind = null;              // GET /api/mind summary (null until loaded)
  var _mindEditorOpen = false;   // mind.md view/edit expander state
  var _mindChoiceOpen = false;   // "no mind.md yet" create/interview panel

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
    _data = null; _expanded = new Set(); _editingSlot = null; _openLib = new Set();
    _fictionOpen = false; _convFor = null;
    _mind = null; _mindEditorOpen = false; _mindChoiceOpen = false;
  }
  function _reload() {
    var host = _host;
    return Promise.all([
      _get(),
      // mind.md state drives the personal-values panel; absence of the
      // endpoint (older server) degrades to the pre-panel behavior.
      fetch('/api/mind').then(_json).catch(function () { return null; }),
    ]).then(function (resp) {
      if (_host !== host) return;          // a later mount/destroy superseded us
      _data = resp[0] || { profiles: [], custom: [], library: {}, settings: {} };
      _mind = resp[1];
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
      + _popoutHTML()
      + '</div>';
    _wire();
  }

  function _headerHTML() {
    var s = (_data && _data.settings) || {};
    var active = _profileById(s.default_id);
    var activeName = active ? active.display_name : 'None';
    // Switch copy states what the toggle DOES: it swaps the VALUES layer
    // of the system prompt (mind.md vs the built-in Mind Seeds). It does
    // not compose voice/style — presets do that (the old copy promised
    // voice composition that never happened).
    return ''
      + '<section class="ora-styles-header">'
      +   '<div class="ora-styles-active">'
      +     '<span class="ora-styles-active-label">Active:</span> '
      +     '<strong class="ora-styles-active-name">' + _esc(activeName) + '</strong>'
      +   '</div>'
      +   _switchHTML('use_custom_values', !!s.use_custom_values,
                      'personal values', '(mind.md)',
                      'inject your mind.md as the authoritative values layer, '
                      + 'replacing the built-in defaults')
      + '</section>'
      + _mindHTML(!!s.use_custom_values);
  }

  // The personal-values panel under the header. States:
  //   choice panel — toggle flipped ON with no (or stock) mind.md;
  //   summary card — toggle ON and mind.md exists;
  //   one-line off note — toggle OFF.
  // Style presets set tone/arrangement/diction; mind.md sets values and
  // posture. Precedence: values floor > completeness > craft > substance
  // > style.
  function _mindHTML(on) {
    if (_mindChoiceOpen) {
      var stock = _mind && _mind.exists && _mind.is_default_template;
      return ''
        + '<section class="ora-styles-mind ora-styles-mind--choice">'
        +   '<div class="ora-styles-mind-title">'
        +     (stock ? 'Your mind.md is still the stock template'
                     : 'No mind.md yet')
        +   '</div>'
        +   '<div class="ora-styles-mind-body">'
        +     'mind.md is your personal values file — communication '
        +     'preferences, intellectual posture, ethical boundaries. '
        +     'Turning on personal values injects it into every prompt '
        +     'as the authoritative values layer. How do you want to '
        +     (stock ? 'make it yours?' : 'create it?')
        +   '</div>'
        +   '<div class="ora-styles-mind-actions">'
        +     (stock ? ''
              : '<button type="button" class="ora-styles-btn" data-action="mind-create">'
                + 'Create from the default template</button>')
        +     '<button type="button" class="ora-styles-btn" data-action="mind-interview">'
        +       'Run the MindSpec interview</button>'
        +     (stock
              ? '<button type="button" class="ora-styles-btn" data-action="mind-edit-from-choice">'
                + 'Edit it now</button>'
              : '')
        +     '<button type="button" class="ora-styles-btn ora-styles-btn--ghost" '
        +       'data-action="mind-choice-cancel">Cancel</button>'
        +   '</div>'
        + '</section>';
    }
    if (!on) {
      return ''
        + '<p class="ora-styles-mind-off">'
        +   'Off — the engine’s built-in Mind Seeds apply. Turn on '
        +   'personal values to inject your own mind.md instead.'
        + '</p>';
    }
    if (!_mind) return '';  // endpoint unavailable — degrade silently
    if (!_mind.exists) {
      return ''
        + '<section class="ora-styles-mind ora-styles-mind--warn">'
        +   '<div class="ora-styles-mind-body">'
        +     '⚠ Personal values is ON but no mind.md exists — '
        +     'the built-in defaults still apply. '
        +     '<button type="button" class="ora-styles-btn" data-action="mind-create">'
        +       'Create from the default template</button> '
        +     '<button type="button" class="ora-styles-btn" data-action="mind-interview">'
        +       'Run the MindSpec interview</button>'
        +   '</div>'
        + '</section>';
    }
    var secs = _mind.sections || [];
    var chips = secs.map(function (name) {
      return '<span class="ora-styles-mind-chip">' + _esc(name) + '</span>';
    }).join('');
    return ''
      + '<section class="ora-styles-mind">'
      +   '<div class="ora-styles-mind-row">'
      +     '<span class="ora-styles-mind-name">mind.md</span>'
      +     '<span class="ora-styles-mind-meta">'
      +       secs.length + ' section' + (secs.length === 1 ? '' : 's')
      +       (_mind.mtime ? ' · last edited ' + _esc(String(_mind.mtime).slice(0, 10)) : '')
      +     '</span>'
      +     chips
      +     '<button type="button" class="ora-styles-btn ora-styles-btn--ghost" '
      +       'data-action="mind-edit">'
      +       (_mindEditorOpen ? 'close editor' : 'view / edit') + '</button>'
      +   '</div>'
      +   (_mind.is_default_template
          ? '<div class="ora-styles-mind-stock">This is still the stock '
            + 'template — run the MindSpec interview '
            + '(<button type="button" class="ora-styles-btn ora-styles-btn--ghost" '
            + 'data-action="mind-interview">start</button>) or edit it to '
            + 'make it yours.</div>'
          : '')
      +   '<div class="ora-styles-mind-hint">'
      +     'Injected into every prompt as the authoritative values layer. '
      +     'Style presets set tone and arrangement; mind.md sets values '
      +     'and posture — precedence: values floor &gt; completeness '
      +     '&gt; craft &gt; substance &gt; style.'
      +   '</div>'
      +   (_mindEditorOpen
          ? '<div class="ora-styles-mind-editor">'
            + '<textarea class="ora-styles-mind-textarea" data-role="mind-content" '
            +   'rows="16" spellcheck="false">' + _esc(_mind.content || '') + '</textarea>'
            + '<div class="ora-styles-mind-actions">'
            +   '<button type="button" class="ora-styles-btn" data-action="mind-save">Save</button>'
            +   '<button type="button" class="ora-styles-btn ora-styles-btn--ghost" '
            +     'data-action="mind-cancel">Cancel</button>'
            + '</div>'
            + '</div>'
          : '')
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
      +     _slotHTML(p, 'elaboration', 'elaboration', p.elaboration_label, isCustom)
      +   '</div>'
      +   _demeanorFPHTML(p, isCustom)
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

  // One headline slot row (arrangement / elaboration). ``slot`` is the display
  // label; ``field`` the logical field. Custom cards single-pick from an inline
  // list; presets are read-only. (Demeanor is its own bottom block; register is
  // determined by the pipeline path, not a slot.)
  function _slotHTML(p, slot, field, value, isCustom) {
    var key = p.id + '::' + field;
    var act = isCustom
      ? ' data-action="edit-slot" data-id="' + _esc(p.id) + '" data-slot="' + _esc(field) + '"'
      : '';
    var picking = (_editingSlot === key);
    var row = ''
      + '<div class="ora-styles-slot' + (isCustom ? ' ora-styles-slot-editable' : '')
      +   (picking ? ' ora-styles-slot-picking' : '') + '"' + act + '>'
      +   '<span class="ora-styles-slot-label">' + _esc(slot) + '</span>'
      +   '<span class="ora-styles-slot-value">' + _esc(value || '—') + '</span>'
      + '</div>';
    if (picking) row += _pickerHTML(p, field);
    return row;
  }

  // Inline option list for a single-pick slot (arrangement / elaboration).
  function _pickerHTML(p, field) {
    var lib = (_data && _data.library) || {};
    var opts = [];
    if (field === 'arrangement') {
      opts = (lib.schemas || []).map(function (s) { return { value: s.id, label: s.label || s.id }; });
    } else if (field === 'elaboration') {
      opts = (lib.elaboration_scale || []).map(function (e) { return { value: e.value, label: e.label }; });
    }
    var cur = p[field];
    var items = opts.map(function (o) {
      var on = (String(o.value) === String(cur));
      return '<button type="button" class="ora-styles-opt' + (on ? ' ora-styles-opt-on' : '') + '"'
        + ' data-action="pick" data-id="' + _esc(p.id) + '" data-slot="' + _esc(field) + '"'
        + ' data-value="' + _esc(o.value) + '">' + _esc(o.label) + '</button>';
    }).join('');
    return '<div class="ora-styles-picker">' + items + '</div>';
  }

  function _axisOrder() {
    var axes = (_data && _data.library && _data.library.axes) || [];
    return axes.length ? axes.map(function (a) { return a.id; })
      : ['warmth', 'force', 'energy', 'outlook', 'playfulness', 'directness', 'agreeableness'];
  }

  // The demeanor "fingerprint" at the bottom of the card: all seven axis values,
  // right-justified three-over-four (no lossy 2-axis summary), labeled
  // "written demeanor". Two lines below it, EVERY card carries a
  // "chat demeanor (gears 1–2)" entry so the gear-1/2 rule is visible on
  // presets too (it used to appear only after customizing, which read as
  // if presets had some other hidden default): presets and un-overridden
  // customs show "same as written"; a custom with an override lists the
  // changed axes. On customs the entry is the click target that opens the
  // override popout. Each value carries its axis name on hover; a custom
  // card's block opens "more" to edit.
  function _demeanorFPHTML(p, isCustom) {
    var order = _axisOrder();
    var picks = p.demeanor || {};
    function val(axis) {
      return '<span class="ora-styles-fp-val" title="' + _esc(axis) + '">'
        + _esc(picks[axis] || '—') + '</span>';
    }
    function vals(ids) {
      return '<span class="ora-styles-fp-vals">'
        + ids.map(val).join('<span class="ora-styles-fp-sep">·</span>') + '</span>';
    }
    var conv = (p.conversational && p.conversational.demeanor) || {};
    var overridden = order.filter(function (ax) {
      return conv[ax] != null && conv[ax] !== picks[ax];
    });
    var hasConv = !!(p.conversational && (p.conversational.demeanor || p.conversational.devices));

    var presetTip = 'Quick chat replies (gears 1–2) use this same demeanor; '
      + 'arrangement, elaboration and glossary apply only to produced '
      + 'output (gears 3–4). Customize the preset to set a separate '
      + 'chat demeanor.';
    var customTip = 'Set a different demeanor for quick chat replies '
      + '(gears 1–2). Unset axes inherit the written demeanor.';

    // Label line: a button on customs (opens the override popout), a
    // tooltip-bearing span on presets.
    var chatLabel = isCustom
      ? '<button type="button" class="ora-styles-conv-link' + (hasConv ? ' ora-styles-conv-set' : '') + '"'
        + ' data-action="conv" data-id="' + _esc(p.id) + '"'
        + ' title="' + _esc(customTip) + '">'
        + 'chat demeanor (gears 1–2)' + (hasConv ? ' •' : '') + '</button>'
      : '<span class="ora-styles-fp-label" title="' + _esc(presetTip) + '">'
        + 'chat demeanor (gears 1–2)</span>';

    // Value line: the override diff when one is set, else the rule.
    var chatValue = overridden.length
      ? overridden.map(function (ax) {
          return '<span class="ora-styles-fp-val" title="' + _esc(ax) + '">'
            + _esc(ax) + ': ' + _esc(conv[ax]) + '</span>';
        }).join('<span class="ora-styles-fp-sep">·</span>')
      : '<span class="ora-styles-fp-same">same as written</span>';

    var editAttr = isCustom ? ' data-action="more" data-id="' + _esc(p.id) + '"' : '';
    return '<div class="ora-styles-fp' + (isCustom ? ' ora-styles-fp-editable' : '') + '"' + editAttr + '>'
      + '<div class="ora-styles-fp-row">'
      +   '<span class="ora-styles-fp-label">written demeanor</span>' + vals(order.slice(0, 3))
      + '</div>'
      + '<div class="ora-styles-fp-row ora-styles-fp-row2"><span></span>' + vals(order.slice(3, 7)) + '</div>'
      + '<div class="ora-styles-fp-row ora-styles-fp-chat">' + chatLabel + '</div>'
      + '<div class="ora-styles-fp-row ora-styles-fp-chat-val">'
      +   '<span></span><span class="ora-styles-fp-vals">' + chatValue + '</span>'
      + '</div>'
      + '</div>';
  }

  // Side popout: the conversational-register override. Same seven axes as rung
  // chips; an unset axis inherits the written demeanor (shown but not marked).
  // The only place conversational is edited — nothing else about it is separate.
  function _popoutHTML() {
    if (!_convFor) return '';
    var p = _profileById(_convFor);
    if (!p) return '';
    var axes = (_data && _data.library && _data.library.axes) || [];
    var conv = (p.conversational && p.conversational.demeanor) || {};
    var written = p.demeanor || {};
    var hasConv = !!(p.conversational && (p.conversational.demeanor || p.conversational.devices));
    var rows = axes.map(function (ax) {
      var overridden = (conv[ax.id] != null && conv[ax.id] !== written[ax.id]);
      var cur = (conv[ax.id] != null) ? conv[ax.id] : written[ax.id];
      var chips = (ax.rungs || []).map(function (r) {
        var on = (r.id === cur);
        return '<button type="button" class="ora-styles-rung' + (on ? ' ora-styles-rung-on' : '') + '"'
          + ' data-action="conv-axis" data-id="' + _esc(p.id) + '" data-axis="' + _esc(ax.id) + '"'
          + ' data-rung="' + _esc(r.id) + '" title="' + _esc(r.text) + '">' + _esc(r.id) + '</button>';
      }).join('');
      return '<div class="ora-styles-axis-row">'
        + '<span class="ora-styles-axis-name">' + _esc(AXIS_LABELS[ax.id] || ax.id)
        + (overridden ? ' <span class="ora-styles-conv-dot">•</span>' : '') + '</span>'
        + '<span class="ora-styles-axis-rungs">' + chips + '</span></div>';
    }).join('');
    return ''
      + '<div class="ora-styles-popout-backdrop" data-action="conv-close"></div>'
      + '<aside class="ora-styles-popout" role="dialog" aria-label="Chat demeanor (gears 1–2)">'
      +   '<header class="ora-styles-popout-head">'
      +     '<span class="ora-styles-popout-title">Chat demeanor (gears 1–2) — ' + _esc(p.display_name) + '</span>'
      +     '<button type="button" class="ora-styles-popout-x" data-action="conv-close">×</button>'
      +   '</header>'
      +   '<p class="ora-styles-popout-note">Used only for quick chat replies (gears 1–2). '
      +     'Unset axes inherit the written demeanor; a dot marks the ones you\'ve changed. '
      +     'Nothing else about chat replies differs from written output.</p>'
      +   rows
      +   '<div class="ora-styles-popout-actions">'
      +     (hasConv ? '<button type="button" class="ora-styles-link" data-action="conv-reset" data-id="'
                       + _esc(p.id) + '">reset to written</button>' : '')
      +   '</div>'
      + '</aside>';
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
    if (evt.key === 'Escape') {
      if (_convFor) { _convFor = null; _render(); }
      else if (_editingSlot) { _editingSlot = null; _render(); }
    }
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
    else if (a === 'conv')       { _convFor = id; _render(); }
    else if (a === 'conv-close') { _convFor = null; _render(); }
    else if (a === 'conv-axis')  { _convAxis(id, t.dataset.axis, t.dataset.rung); }
    else if (a === 'conv-reset') { _convReset(id); }
    else if (a === 'mind-create')          { _mindCreate(); }
    else if (a === 'mind-interview')       { _mindInterview(); }
    else if (a === 'mind-choice-cancel')   { _mindChoiceOpen = false; _render(); }
    else if (a === 'mind-edit')            { _mindEditorOpen = !_mindEditorOpen; _render(); }
    else if (a === 'mind-edit-from-choice') {
      // "Edit it now" on the stock-template choice panel: commit the
      // toggle (the user chose to proceed with the template as a base)
      // and open the editor.
      _mindChoiceOpen = false;
      _mindEditorOpen = true;
      _status('Saving…');
      _saveSettings({ use_custom_values: true })
        .then(function () { return _reload(); })
        .then(function () {
          _status('Personal values ON — edit mind.md below to make it yours.');
        })
        .catch(function () { _status('Could not save — try again.'); });
    }
    else if (a === 'mind-cancel') { _mindEditorOpen = false; _render(); }
    else if (a === 'mind-save')   { _mindSave(); }
  }

  // ── mind.md actions ───────────────────────────────────────────────────────

  function _mindCreate() {
    _status('Creating mind.md from the template…');
    fetch('/api/mind', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'create_from_template' }),
    }).then(_json).then(function (resp) {
      if (resp && resp.error) throw new Error(resp.error);
      _mindChoiceOpen = false;
      _mindEditorOpen = true;   // land the user in the editor
      return _saveSettings({ use_custom_values: true });
    }).then(function () { return _reload(); })
      .then(function () {
        _status('mind.md created and personal values turned ON — '
          + 'edit it below to make it yours.');
      })
      .catch(function (err) {
        _status('Could not create mind.md: '
          + ((err && err.message) || 'unknown error'));
      });
  }

  function _mindInterview() {
    // Same idiom as External APIs' "+ Add new provider": drop the
    // framework command into the chat input for the user to review and
    // send. The MindSpec interview's MSI-Self mode persists its
    // deliverable to ~/ora/mind.md on completion.
    var input = document.querySelector('.input-pane textarea');
    if (!input) {
      _status('Could not find the chat input — type '
        + '/framework mindspec-interview there yourself.');
      return;
    }
    input.value = '/framework mindspec-interview';
    try {
      input.dispatchEvent(new Event('input', { bubbles: true }));
    } catch (_) { /* old browser fallback — ignore */ }
    _mindChoiceOpen = false;
    _render();
    _status('Prompt dropped into the chat input — close Settings and press '
      + 'Enter to start the interview. Turn personal values on afterwards.');
    try { input.focus(); } catch (_) { /* ignore */ }
  }

  function _mindSave() {
    var ta = _host && _host.querySelector('[data-role="mind-content"]');
    if (!ta) return;
    _status('Saving mind.md…');
    fetch('/api/mind', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: ta.value }),
    }).then(_json).then(function (resp) {
      if (resp && resp.error) throw new Error(resp.error);
      _mindEditorOpen = false;
      return _reload();
    }).then(function () { _status('mind.md saved.'); })
      .catch(function (err) {
        _status('Could not save mind.md: '
          + ((err && err.message) || 'unknown error'));
      });
  }

  function _onChange(evt) {
    var el = evt.target;
    if (el.dataset.toggle === 'use_custom_values') {
      // State check before the silent save: flipping ON with no mind.md
      // (or one that's still the stock template) opens the create/
      // interview choice panel instead of committing a toggle that
      // would change nothing meaningful.
      if (el.checked && _mind
          && (!_mind.exists || _mind.is_default_template)) {
        el.checked = false;           // don't commit until resolved
        _mindChoiceOpen = true;
        _render();
        return;
      }
      var flag = { use_custom_values: el.checked };
      var onMsg = _mind && _mind.exists
        ? 'Personal values ON — mind.md ('
          + ((_mind.sections || []).length) + ' section'
          + (((_mind.sections || []).length) === 1 ? '' : 's')
          + ') is injected as your values layer.'
        : 'Personal values ON.';
      var doneMsg = el.checked
        ? onMsg
        : 'Personal values OFF — the built-in defaults apply.';
      _status('Saving…');
      _saveSettings(flag).then(function () { return _reload(); })
        .then(function () { _status(doneMsg); })
        .catch(function () { _status('Could not save — try again.'); });
    } else if (el.dataset.toggle) {
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

  function _convAxis(id, axis, rung) {
    var dem = {}; dem[axis] = rung;
    _status('Saving…');
    _patch(id, { conversational: { demeanor: dem } }).then(function () { return _reload(); })
      .then(function () { _status(''); })
      .catch(function () { _status('Could not save — try again.'); });
  }

  function _convReset(id) {
    _status('Saving…');
    _patch(id, { conversational: null }).then(function () { return _reload(); })
      .then(function () { _status(''); })
      .catch(function () { _status('Could not save — try again.'); });
  }

  root.OraStylesPane = { init: init, destroy: destroy };
})(typeof window !== 'undefined' ? window : this);
