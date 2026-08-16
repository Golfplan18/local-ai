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

  // Null-prototype, so an inherited Object.prototype key cannot be read as a
  // position. As a plain literal, POSITIONS['constructor'] (and '__proto__',
  // 'hasOwnProperty', 'toString', 'valueOf') was truthy: _validate passed the
  // entry through and _build then reported "no container for position
  // constructor" — sending a plugin author to hunt for a container that was
  // never the problem. Nothing mounted either way; the log was the defect.
  var POSITIONS = Object.assign(Object.create(null), {
    inquiry:  { container: '.bridge-toolbar--left',       buttonClass: 'input-pane-toolbar__btn' },
    exhibits: { container: '.bridge-toolbar--right',      buttonClass: 'input-pane-toolbar__btn' },
    spine:    { container: '.spine-bottom',               buttonClass: 'spine-button' },
    sidebar:  { container: '.sidebar-collapsed-dashboard', buttonClass: 'sidebar-dash-icon' }
  });

  // id → { entry, el }
  var _mounted = Object.create(null);
  // { id, entry } for registrations made before the shell exists, flushed on
  // DOM ready. The id is the one captured at registration, so the queue, the
  // mounted map, the button's own data-ora-mount attribute and the unregister
  // handle all agree on it even if a plugin mutates entry.id afterwards.
  var _pending = [];
  var _domReady = false;

  function _warn(message) {
    if (root.console && typeof root.console.warn === 'function') {
      root.console.warn('[v3-mount-points] ' + message);
    }
  }

  function _isFn(v) { return typeof v === 'function'; }
  function _isStr(v) { return typeof v === 'string' && v.length > 0; }

  // Never throws — for real, on every path. Anything a queued plugin object
  // holds can end up in a diagnostic, and some values refuse to become text:
  // '' + aSymbol throws, and String(x) throws for an object with no usable
  // toString/valueOf. Object.prototype.toString is not a floor either — it
  // READS Symbol.toStringTag off the value, so a throwing getter throws from
  // inside the rescue, and a revoked Proxy refuses that read (and every other
  // operation) outright.
  //
  // That matters because _describe runs inside _flush's catch: a throw there
  // originates inside the catch, so it escapes the catch, escapes the flush
  // loop, and escapes _flush — with _pending already drained and _domReady
  // already true. Every plugin queued behind the bad one is lost permanently,
  // silently, since the DOM event dispatcher swallows a listener error. The
  // last resort is therefore a literal: a placeholder diagnostic is worth
  // strictly more than a lost queue.
  var UNDESCRIBABLE = '(a value that cannot be converted to text)';

  function _describe(v) {
    try { return String(v); } catch (e) { /* try the next one */ }
    try { return Object.prototype.toString.call(v); } catch (e) { /* give up */ }
    return UNDESCRIBABLE;
  }

  // The reason a thrown value carries is plugin-controlled too, and reading it
  // is itself an operation that can throw: err.message may be a throwing
  // getter, and a revoked Proxy refuses the property read. Reach for it
  // defensively, then describe whatever came back.
  function _reason(err) {
    var message = null;
    try { message = err && err.message; } catch (e) { /* fall back to err */ }
    return _describe(message || err);
  }

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

  function _unknownPosition(position) {
    return 'unknown position "' + _describe(position) + '" (expected one of: '
      + Object.keys(POSITIONS).join(', ') + ')';
  }

  function _validate(entry) {
    if (!entry || typeof entry !== 'object') return 'entry must be an object';
    if (!_isStr(entry.id)) return 'entry.id is required';
    if (!_isStr(entry.position)) return 'entry.position is required';
    if (!POSITIONS[entry.position]) return _unknownPosition(entry.position);
    if (!_isStr(entry.label)) return 'entry.label is required';
    if (!_isStr(entry.icon)) return 'entry.icon is required';
    if (!_isFn(entry.onSelect)) return 'entry.onSelect must be a function';
    if (_mounted[entry.id]) return 'id "' + entry.id + '" is already registered';
    return null;
  }

  // `id` is the id captured at registration — never entry.id read again here.
  // A queued entry is a live plugin object that can rename itself before
  // _flush reaches it, and the mounted map is keyed by the captured id. If the
  // button advertised the live one instead, the two would name different
  // things and unregister(<the id the DOM advertises>) would stop working.
  function _build(entry, id) {
    // Read the position once, and check its TYPE before the lookup. A property
    // read coerces its key, so a position that cannot become one — a Symbol,
    // an object with no usable toString — throws inside POSITIONS[...] before
    // any guard below it can run. An unusable position is an unknown position;
    // it gets the same diagnostic as a misspelt one.
    //
    // _validate rejects an unknown position at registration, but a queued
    // entry's position can change before the flush that builds it. Say what is
    // actually wrong instead of dereferencing a missing spec (or blaming an
    // absent container).
    var position = entry.position;
    var spec = _isStr(position) ? POSITIONS[position] : null;
    if (!spec) {
      _warn(_unknownPosition(position) + '; button "' + id + '" not mounted');
      return null;
    }
    var container = root.document && root.document.querySelector(spec.container);
    if (!container) {
      _warn('no container for position "' + position + '" ('
        + spec.container + '); button "' + id + '" not mounted');
      return null;
    }

    var btn = root.document.createElement('button');
    btn.type = 'button';
    btn.className = spec.buttonClass;
    btn.setAttribute('data-ora-mount', id);
    btn.setAttribute('aria-label', entry.label);
    btn.setAttribute('title', entry.label);
    if (entry.active) btn.setAttribute('aria-pressed', 'true');

    _renderIcon(btn, entry.icon);

    btn.addEventListener('click', function (e) {
      try {
        entry.onSelect(e);
      } catch (err) {
        // A plugin's handler must never break the shell.
        _warn('handler for "' + id + '" threw: ' + _reason(err));
      }
    });

    container.appendChild(btn);
    return btn;
  }

  // The handle register() hands back, bound to THIS registration rather than
  // to the id. A handle kept past its own removal must not unmount a different
  // button someone later registered under the same id. The entry object is the
  // identity that spans both paths: a queued entry is the same object once
  // _flush mounts it, so one handle covers pending and mounted alike. The id
  // is captured at registration, and _build stamps that same captured id onto
  // the button, so a plugin mutating entry.id afterwards cannot make its own
  // button unreachable — by this handle or by unregister().
  function _removeRegistration(id, entry) {
    var rec = _mounted[id];
    if (rec && rec.entry === entry) {
      if (rec.el && rec.el.parentNode) rec.el.parentNode.removeChild(rec.el);
      delete _mounted[id];
      return true;
    }
    // May still be queued if the shell never finished booting.
    for (var i = 0; i < _pending.length; i++) {
      if (_pending[i].entry === entry) { _pending.splice(i, 1); return true; }
    }
    return false;
  }

  function register(entry) {
    var problem = _validate(entry);
    if (problem) {
      _warn('register rejected: ' + problem);
      return function () { return false; };
    }

    var id = entry.id;

    if (!_domReady) {
      _pending.push({ id: id, entry: entry });
      return function () { return _removeRegistration(id, entry); };
    }

    var el = _build(entry, id);
    if (!el) return function () { return false; };
    _mounted[id] = { entry: entry, el: el };
    return function () { return _removeRegistration(id, entry); };
  }

  // Public and deliberately id-bound: removes whatever currently holds the id.
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
    queued.forEach(function (rec) {
      if (_mounted[rec.id]) return;
      // The queue is drained before the first mount runs, so an exception
      // escaping this callback would abandon every entry behind it — and
      // permanently, since _domReady is already true and _pending is already
      // empty: nothing would retry them and nothing would say so. A queued
      // entry is a live plugin object, so ANY of it can have turned
      // unusable by now (a position that will not coerce, a label that will
      // not, an icon getter that throws). One bad plugin costs its own button
      // and nothing else.
      try {
        var el = _build(rec.entry, rec.id);
        if (el) _mounted[rec.id] = { entry: rec.entry, el: el };
      } catch (err) {
        _warn('button "' + rec.id + '" could not be mounted: ' + _describe(err));
      }
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
