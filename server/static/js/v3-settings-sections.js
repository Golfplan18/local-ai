/* v3-settings-sections.js — plugin sections for the Ora Settings modal.
 *
 * Ora Settings is a hand-written tab strip in settings-panel.js: a hardcoded
 * TABS array, a hardcoded if/else render chain, and one hand-written render
 * function per tab. That is fine for core, but it means an add-on cannot give
 * itself a settings page without editing Ora's own panel. This module is the
 * one seam that fixes that.
 *
 * A registered section becomes a real tab in the strip, drawn with the same
 * class and the same click behaviour as a core tab, and its content is painted
 * into the same section chrome core uses (.ora-settings-sections-grid wrapping
 * an .ora-settings-group) — so it is styled natively with no new CSS. Core
 * TABS and every core render branch are untouched; plugin tabs append after
 * the core ones in registration order.
 *
 * Unlike the button mount points, nothing here touches the DOM at register
 * time: the registry is a plain list, and settings-panel.js pulls list() each
 * time it paints the strip. So there is no queue, no DOM-ready flush, and a
 * section may be registered before or after the panel is built.
 *
 * Public API (window.OraSettingsSections)
 * --------------------------------------
 *   .register(entry) → unregister function
 *       entry.id      unique string                                (required)
 *       entry.label   the tab's visible text, also the section title (required)
 *       entry.render  function(body, ctx) — paints the section body (required)
 *       entry.group   'advanced' to place the tab after the "Advanced"
 *                     divider; omit for the main list               (optional)
 *       The returned handle removes THAT entry: calling it twice, or after
 *       something else has claimed the same id, returns false and removes
 *       nothing.
 *
 *   .unregister(id) → boolean   — removes whatever holds the id now
 *   .has(id) / .get(id)
 *   .list()         → entries, main group first, then advanced, registration
 *                     order within each group
 *   .reserveIds(ids) → number of already-registered sections evicted
 *
 * Reserved ids (built-ins win)
 * ----------------------------
 * A plugin must not be able to shadow a core Settings tab, so ids belonging to
 * core are refused. The list is NOT copied into this file: settings-panel.js
 * hands it over via reserveIds() with its own TABS ids and TAB_ALIASES keys.
 * That keeps the dependency one-directional (the panel reads the registry; the
 * registry never reads the panel) and keeps a single copy of the truth — a
 * hardcoded mirror here would drift the first time a core tab is renamed.
 * Because a plugin can load before the panel does, reserveIds() also evicts any
 * already-registered colliding section, with a warning: reserving is retroactive
 * so the guarantee does not depend on script order.
 *
 * Failure behaviour is fail-open with loud logging, per Ora's standing rule:
 * a bad entry, a duplicate id, a reserved id, or a throwing render callback
 * warns and carries on. A plugin cannot take Settings down by registering
 * badly, and it cannot take Settings down by rendering badly either.
 *
 * Entry fields are plugin code when they are getters, so every read of one is
 * guarded and each field is read once per operation: a getter that throws
 * — at register time, or later, on a read that an earlier one survived —
 * rejects or skips that ONE entry with a warning. It never throws back into
 * the caller's stack and never takes the other sections down with it.
 */
(function (root) {
  'use strict';

  // Evaluating this file twice — two script tags, a plugin bundling its own
  // copy, the same file served under a second URL — would otherwise replace a
  // live registry with a second, empty one: every section registered against
  // the first instance would vanish from the strip, and unregister handles
  // held by plugins would point at a store nobody reads. First evaluation
  // wins; a later one is a no-op.
  if (root.OraSettingsSections) return;

  // The only supported optional group. Named for the divider it sits behind,
  // and deliberately the same field name core TABS entries already use.
  var GROUPS = ['advanced'];

  // Registration order is load-bearing (it decides tab order), so the store is
  // an array rather than a map.
  var _sections = [];
  // id → true. Populated by settings-panel.js at first paint; empty until then.
  // Prototype-free on purpose: on a plain object, ids that happen to name an
  // Object.prototype member ('constructor', 'toString', …) would read back as
  // reserved and be refused.
  var _reserved = Object.create(null);

  function _warn(message) {
    if (root.console && typeof root.console.warn === 'function') {
      root.console.warn('[v3-settings-sections] ' + message);
    }
  }

  function _isFn(v) { return typeof v === 'function'; }
  function _isStr(v) { return typeof v === 'string' && v.length > 0; }

  function _indexOf(id) {
    for (var i = 0; i < _sections.length; i++) {
      if (_sections[i].id === id) return i;
    }
    return -1;
  }

  // Every field is read ONCE, into a local. A plugin may compute any of them
  // lazily, and re-reading gave a getter that answers differently each time
  // the chance to be validated as one value and stored as another.
  function _validate(entry) {
    if (!entry || typeof entry !== 'object') return 'entry must be an object';
    var id = entry.id;
    var label = entry.label;
    var render = entry.render;
    var group = entry.group;
    if (!_isStr(id)) return 'entry.id is required';
    if (!_isStr(label)) return 'entry.label is required';
    if (!_isFn(render)) return 'entry.render must be a function';
    if (group !== undefined && group !== null && GROUPS.indexOf(group) < 0) {
      return 'unknown group "' + group + '" (expected one of: '
        + GROUPS.join(', ') + ')';
    }
    if (_reserved[id]) {
      return 'id "' + id + '" is reserved by a core Settings tab';
    }
    if (_indexOf(id) >= 0) {
      return 'id "' + id + '" is already registered';
    }
    return null;
  }

  function register(entry) {
    var problem;
    // Reading a field is itself plugin code when the field is a getter. The
    // documented contract for a bad registration is a warning plus an inert
    // handle — never an exception thrown back into the registering plugin's
    // stack, which would abort whatever else that plugin was doing.
    try {
      problem = _validate(entry);
    } catch (err) {
      problem = 'a field on the entry could not be read: '
        + ((err && err.message) ? err.message : String(err));
    }
    if (problem) {
      _warn('register rejected: ' + problem);
      return function () { return false; };
    }
    _sections.push(entry);
    // The handle removes THIS entry, not whatever currently holds its id. A
    // handle kept past its own removal is common (a plugin tears down twice,
    // or reloads itself under the same id); keyed by id it would silently
    // remove the live successor instead of doing nothing.
    return function () { return _removeEntry(entry); };
  }

  function _removeEntry(entry) {
    var i = _sections.indexOf(entry);
    if (i < 0) return false;
    _sections.splice(i, 1);
    return true;
  }

  function unregister(id) {
    var i = _indexOf(id);
    if (i < 0) return false;
    _sections.splice(i, 1);
    return true;
  }

  function has(id) { return _indexOf(id) >= 0; }

  function get(id) {
    var i = _indexOf(id);
    return i < 0 ? null : _sections[i];
  }

  // Main group first, then advanced, registration order preserved inside each
  // — the order settings-panel.js draws them in around the Advanced divider.
  //
  // The group read is guarded for the same reason it is guarded in the panel:
  // it is plugin code, it runs on every paint, and a getter that validated
  // cleanly at register time can still throw later. Unguarded it escaped out
  // of list() and the panel dropped EVERY section rather than the one it could
  // not place. An entry whose group cannot be read is not orderable, so it is
  // left out with a warning; it stays registered and get()/has() still find it.
  function list() {
    var main = [];
    var advanced = [];
    _sections.forEach(function (e) {
      var group;
      try {
        group = e.group;
      } catch (err) {
        _warn('a section was left out of list(): its group could not be read: '
          + ((err && err.message) ? err.message : String(err)));
        return;
      }
      if (group === 'advanced') advanced.push(e);
      else main.push(e);
    });
    return main.concat(advanced);
  }

  // Called by settings-panel.js with its core tab ids and legacy alias keys.
  // Idempotent, and retroactive: a section that registered before the panel
  // loaded and claimed a core id is evicted here rather than being allowed to
  // shadow it.
  function reserveIds(ids) {
    if (!ids || typeof ids.length !== 'number') {
      _warn('reserveIds expects an array of ids');
      return 0;
    }
    for (var i = 0; i < ids.length; i++) {
      if (_isStr(ids[i])) _reserved[ids[i]] = true;
    }
    var evicted = 0;
    for (var j = _sections.length - 1; j >= 0; j--) {
      if (_reserved[_sections[j].id]) {
        _warn('section "' + _sections[j].id + '" collides with a core Settings '
          + 'tab id and has been removed');
        _sections.splice(j, 1);
        evicted++;
      }
    }
    return evicted;
  }

  root.OraSettingsSections = {
    register:   register,
    unregister: unregister,
    has:        has,
    get:        get,
    list:       list,
    reserveIds: reserveIds
  };
})(typeof window !== 'undefined' ? window : globalThis);
