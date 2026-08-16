/* v3-mount-points.js — plugin button mount points for the V3 shell.
 *
 * Ora's four toolbars are hand-written HTML in index-v3.html, and every core
 * button carries its own hand-written listener. That is fine for core, but it
 * means an add-on cannot contribute a button without editing Ora's own shell.
 * This module is the one seam that fixes that.
 *
 * Four positions, named for what the button ACTS ON rather than where it sits,
 * because that is the choice a plugin author actually has to make:
 *
 *   inquiry   — acts on the writing side (Inquiry / Findings). Left cluster.
 *   exhibits  — acts on the Exhibits pane (canvas, media). Right cluster.
 *   spine     — belongs to neither side; global to the workspace. Spine bottom.
 *   sidebar   — a general feature, not tied to the workspace. Sidebar rail.
 *
 * Each position maps to an existing container AND to the button class that
 * position already uses, so a registered button is styled natively with no new
 * CSS. Plugin buttons append after the core buttons in registration order;
 * core markup is never rewritten.
 *
 * Public API (window.OraMounts)
 * ----------------------------
 *   .register(entry) → unregister function
 *       entry.position  'inquiry' | 'exhibits' | 'spine' | 'sidebar'  (required)
 *       entry.id        unique string                                 (required)
 *       entry.label     accessible name, also the tooltip             (required)
 *       entry.icon      inline SVG string, or a Lucide icon name      (required)
 *       entry.onSelect  function(event) called on click               (required)
 *       entry.active    initial pressed state for toggle buttons      (optional)
 *
 *   .unregister(id)      → boolean
 *   .setActive(id, bool) → boolean   — for toggles (e.g. a pane mode)
 *   .has(id) / .get(id) / .list(position?)
 *   .positions()         → the four position names
 *
 * Failure behaviour is fail-open with loud logging, per Ora's standing rule:
 * an unknown position, a missing container, or a throwing handler warns and
 * carries on. A plugin cannot take the shell down by registering badly.
 */
(function (root) {
  'use strict';

  var POSITIONS = {
    inquiry:  { container: '.bridge-toolbar--left',       buttonClass: 'input-pane-toolbar__btn' },
    exhibits: { container: '.bridge-toolbar--right',      buttonClass: 'input-pane-toolbar__btn' },
    spine:    { container: '.spine-bottom',               buttonClass: 'spine-button' },
    sidebar:  { container: '.sidebar-collapsed-dashboard', buttonClass: 'sidebar-dash-icon' }
  };

  // id → { entry, el }
  var _mounted = Object.create(null);
  // Entries registered before the shell exists, flushed on DOM ready.
  var _pending = [];
  var _domReady = false;

  function _warn(message) {
    if (root.console && typeof root.console.warn === 'function') {
      root.console.warn('[v3-mount-points] ' + message);
    }
  }

  function _isFn(v) { return typeof v === 'function'; }
  function _isStr(v) { return typeof v === 'string' && v.length > 0; }

  // Icon: inline SVG passes through; anything else is treated as a Lucide name
  // and handed to the existing resolver. Same rule the pack format uses — this
  // deliberately does not invent a third icon convention.
  function _renderIcon(el, icon) {
    var trimmed = String(icon).trim();
    if (trimmed.slice(0, 4).toLowerCase() === '<svg') {
      el.innerHTML = trimmed;
      return true;
    }
    var resolver = root.OraIconResolver;
    if (resolver && _isFn(resolver.toSvg)) {
      try {
        var svg = resolver.toSvg(trimmed);
        if (_isStr(svg)) { el.innerHTML = svg; return true; }
      } catch (e) { /* fall through to the text fallback */ }
    }
    // Loud, visible, and harmless: the button still works, it just looks plain.
    _warn('icon "' + trimmed + '" could not be resolved; rendering label text');
    el.textContent = trimmed.slice(0, 2);
    return false;
  }

  function _validate(entry) {
    if (!entry || typeof entry !== 'object') return 'entry must be an object';
    if (!_isStr(entry.id)) return 'entry.id is required';
    if (!_isStr(entry.position)) return 'entry.position is required';
    if (!POSITIONS[entry.position]) {
      return 'unknown position "' + entry.position + '" (expected one of: '
        + Object.keys(POSITIONS).join(', ') + ')';
    }
    if (!_isStr(entry.label)) return 'entry.label is required';
    if (!_isStr(entry.icon)) return 'entry.icon is required';
    if (!_isFn(entry.onSelect)) return 'entry.onSelect must be a function';
    if (_mounted[entry.id]) return 'id "' + entry.id + '" is already registered';
    return null;
  }

  function _build(entry) {
    var spec = POSITIONS[entry.position];
    var container = root.document && root.document.querySelector(spec.container);
    if (!container) {
      _warn('no container for position "' + entry.position + '" ('
        + spec.container + '); button "' + entry.id + '" not mounted');
      return null;
    }

    var btn = root.document.createElement('button');
    btn.type = 'button';
    btn.className = spec.buttonClass;
    btn.setAttribute('data-ora-mount', entry.id);
    btn.setAttribute('aria-label', entry.label);
    btn.setAttribute('title', entry.label);
    if (entry.active) btn.setAttribute('aria-pressed', 'true');

    _renderIcon(btn, entry.icon);

    btn.addEventListener('click', function (e) {
      try {
        entry.onSelect(e);
      } catch (err) {
        // A plugin's handler must never break the shell.
        _warn('handler for "' + entry.id + '" threw: '
          + ((err && err.message) || err));
      }
    });

    container.appendChild(btn);
    return btn;
  }

  function register(entry) {
    var problem = _validate(entry);
    if (problem) {
      _warn('register rejected: ' + problem);
      return function () { return false; };
    }

    if (!_domReady) {
      _pending.push(entry);
      return function () { return unregister(entry.id); };
    }

    var el = _build(entry);
    if (!el) return function () { return false; };
    _mounted[entry.id] = { entry: entry, el: el };
    return function () { return unregister(entry.id); };
  }

  function unregister(id) {
    var rec = _mounted[id];
    if (rec) {
      if (rec.el && rec.el.parentNode) rec.el.parentNode.removeChild(rec.el);
      delete _mounted[id];
      return true;
    }
    // May still be queued if the shell never finished booting.
    for (var i = 0; i < _pending.length; i++) {
      if (_pending[i].id === id) { _pending.splice(i, 1); return true; }
    }
    return false;
  }

  function setActive(id, on) {
    var rec = _mounted[id];
    if (!rec || !rec.el) return false;
    if (on) rec.el.setAttribute('aria-pressed', 'true');
    else rec.el.removeAttribute('aria-pressed');
    return true;
  }

  function has(id) { return !!_mounted[id]; }
  function get(id) { return _mounted[id] ? _mounted[id].entry : null; }

  function list(position) {
    var out = [];
    Object.keys(_mounted).forEach(function (id) {
      var e = _mounted[id].entry;
      if (!position || e.position === position) out.push(e);
    });
    return out;
  }

  function positions() { return Object.keys(POSITIONS); }

  function _flush() {
    _domReady = true;
    var queued = _pending.splice(0, _pending.length);
    queued.forEach(function (entry) {
      if (_mounted[entry.id]) return;
      var el = _build(entry);
      if (el) _mounted[entry.id] = { entry: entry, el: el };
    });
  }

  if (root.document) {
    if (root.document.readyState === 'loading') {
      root.document.addEventListener('DOMContentLoaded', _flush);
    } else {
      _flush();
    }
  }

  root.OraMounts = {
    register:   register,
    unregister: unregister,
    setActive:  setActive,
    has:        has,
    get:        get,
    list:       list,
    positions:  positions,
    // Test seam: lets a headless harness flush the queue without a real
    // DOMContentLoaded event.
    _flush:     _flush
  };
})(typeof window !== 'undefined' ? window : globalThis);
