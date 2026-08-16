/* v3-browse-overlay.js — docked, non-modal browse surfaces for plugins.
 *
 * Ora already has exactly one surface of this shape: the conversation Library,
 * built by hand inside sidebar.js. It is a panel that docks over the workspace,
 * lists things, and — this is the whole point — leaves the rest of Ora usable
 * while it is up. A plugin that wants to browse its own files or outputs has
 * nowhere to put that surface without editing Ora's shell. This module is that
 * seam.
 *
 * NON-MODAL IS THE POINT
 * ----------------------
 * The overlay is `role="dialog"` with `aria-modal="false"`, exactly as the
 * Library sets it. Nothing outside the overlay is made inert: no aria-hidden on
 * the shell, no focus trap, no click-swallowing backdrop. The CSS carries the
 * mechanism — `.conversation-browser-overlay` is `pointer-events: none` and
 * only `.conversation-browser-panel` is `pointer-events: auto`, so clicks
 * outside the panel land on Ora, not on the overlay.
 *
 * NO NEW CSS
 * ----------
 * Every class emitted here already exists in
 * styles/components/v3-spec-conform.css: conversation-browser-overlay /
 * -panel / -top / -status / -close / -rows. A plugin's surface is therefore
 * styled natively. Rows painted into the body should use the existing
 * `conversation-browser-row` class for the same reason.
 *
 * Public API (window.OraBrowseOverlays)
 * ------------------------------------
 *   .register(entry) → unregister function
 *       entry.id       unique string                                (required)
 *       entry.label    accessible name AND the visible title        (required)
 *       entry.render   function(body, ctx) — paints the plugin's rows (required)
 *       entry.onOpen   function(ctx)                                (optional)
 *       entry.onClose  function(ctx)                                (optional)
 *
 *   .open(id) / .close(id?) / .isOpen(id?) / .has(id) / .get(id) / .list()
 *
 *   ctx = { id, label, root, body, close() } — `root` is the dialog element,
 *   `body` the rows container, `close()` closes this overlay only.
 *
 * Escape closes. Focus returns to whatever held it when the overlay opened —
 * the Library's `browserReturnFocus` idea — but only when the overlay still
 * holds focus, or nobody does. A docked surface shares the app with a live
 * user, so a close never takes focus away from an input the user moved to, or
 * from a surface a plugin opened out of its own `onClose`. One plugin overlay
 * is open at a time — they occupy the same dock, so opening a second closes the
 * first. The core Library is layered below and is never reached into from here.
 *
 * Nothing is mounted at registration (unlike the button mount points), so there
 * is no pending queue: the DOM is built on first open, by which time the shell
 * exists.
 *
 * Failure behaviour is fail-open with loud logging, per Ora's standing rule.
 * Every call into plugin code — render, onOpen, onClose, and even reading
 * entry fields, which may be getters — is wrapped, including the calls made
 * from event handlers. A plugin cannot take the shell down.
 */
(function (root) {
  'use strict';

  // Evaluating this file twice must not produce a second copy of the registry.
  if (root.OraBrowseOverlays) return;

  // id → { id, entry, label, el, body, titleEl, closeEl, open, onResize,
  //        observer, returnFocus, geometryWarned }.  Null-prototype so ids
  //        like "__proto__", "constructor" and "hasOwnProperty" behave as
  //        ordinary keys.
  var _overlays = Object.create(null);
  var _openId = null;

  // The four shell elements the dock geometry reads.
  var GEOMETRY_SELECTORS = ['.ora-shell', '.left-column', '.right-column', '.input-pane'];

  function _warn(message) {
    if (root.console && typeof root.console.warn === 'function') {
      root.console.warn('[v3-browse-overlay] ' + message);
    }
  }

  function _isFn(v) { return typeof v === 'function'; }
  function _isStr(v) { return typeof v === 'string' && v.length > 0; }
  function _msg(err) { return (err && err.message) || String(err); }

  function _own(id) {
    return Object.prototype.hasOwnProperty.call(_overlays, id) ? _overlays[id] : null;
  }

  function _activeElement() {
    var doc = root.document;
    if (!doc) return null;
    try { return doc.activeElement || null; } catch (e) { return null; }
  }

  // `contains` counts the container itself, which is what we want: the dialog
  // root is the element the overlay focuses.
  function _contains(container, node) {
    if (!container || !node) return false;
    if (container === node) return true;
    try { return _isFn(container.contains) && !!container.contains(node); }
    catch (e) { return false; }
  }

  // Undefined means "an environment without isConnected", which is treated as
  // still in the document — the same tolerance the focus restore has always had.
  function _detached(node) {
    if (!node) return true;
    try { return node.isConnected === false; } catch (e) { return false; }
  }

  // True when the node lives inside an overlay this module owns and has
  // already closed. Hiding a root does not blur it in every environment, so
  // whatever runs next can see a dead root sitting in document.activeElement.
  function _inClosedOverlay(node) {
    if (!node) return false;
    return Object.keys(_overlays).some(function (id) {
      var other = _overlays[id];
      return !!(other && !other.open && _contains(other.el, node));
    });
  }

  function _anyOtherOpen(keepId) {
    return Object.keys(_overlays).some(function (id) {
      var other = _overlays[id];
      return !!(other && other.id !== keepId && other.open);
    });
  }

  // Entry fields are read at USE time, not cached at registration, so a plugin
  // can change its own label. That means any field may be a getter that throws.
  function _read(entry, field) {
    try {
      return entry[field];
    } catch (e) {
      _warn('reading entry.' + field + ' threw: ' + _msg(e));
      return undefined;
    }
  }

  // The label as it should be used right now, with the registered value as the
  // fallback when the live read is unusable.
  function _label(rec) {
    var live = _read(rec.entry, 'label');
    if (_isStr(live)) return live;
    _warn('entry.label for "' + rec.id + '" is not a usable string; '
      + 'falling back to the registered label');
    return rec.label;
  }

  // One place where plugin code is entered. A synchronous throw and a rejected
  // thenable both land in the same warn path; neither escapes into the shell.
  function _callPlugin(what, id, fn, args) {
    if (!_isFn(fn)) return undefined;
    var out;
    try {
      out = fn.apply(null, args || []);
    } catch (err) {
      _warn(what + ' for "' + id + '" threw: ' + _msg(err));
      return undefined;
    }
    var thenable = false;
    try { thenable = !!out && _isFn(out.then); } catch (e) { thenable = false; }
    if (thenable) {
      try {
        out.then(null, function (err) {
          _warn(what + ' for "' + id + '" rejected: ' + _msg(err));
        });
      } catch (err) {
        _warn(what + ' for "' + id + '" threw: ' + _msg(err));
      }
    }
    return out;
  }

  function _ctx(rec) {
    return {
      id: rec.id,
      label: _label(rec),
      root: rec.el,
      body: rec.body,
      close: function () {
        return _own(rec.id) === rec ? _closeRecord(rec) : false;
      }
    };
  }

  // ---- dock geometry --------------------------------------------------------

  // MIRRORS server/static/js/sidebar.js::positionBrowser — the Library's dock
  // geometry, duplicated deliberately rather than refactoring working code to
  // share a positioner. Same four CSS custom properties, same shell inputs,
  // same padding and clamping, same early return when the shell is missing.
  // THE TWO MUST MOVE TOGETHER: if the Library's dock changes, change this too.
  // The Library degrades the same way — it simply returns and lets the CSS
  // defaults stand. Matching that degradation is right; being silent about it
  // is not, because the defaults are `left: 0; top: 0; width: 100vw;
  // height: 160px` and the panel inside is `pointer-events: auto`. Said once
  // per open, not once per resize tick.
  function _geometryUnavailable(rec, reason) {
    if (rec.geometryWarned) return;
    rec.geometryWarned = true;
    _warn('the dock geometry for "' + rec.id + '" cannot be computed (' + reason
      + '), so the overlay keeps the stylesheet defaults: left 0, top 0, '
      + 'width 100vw, height 160px. That lays its interactive panel across the '
      + 'full width of the top of the app. Nothing is made inert and the rest '
      + 'of Ora still works, but the surface is not where it belongs.');
  }

  function _position(rec) {
    if (!rec || !rec.el || !rec.el.classList.contains('is-open')) return;
    var doc = root.document;
    if (!doc) { _geometryUnavailable(rec, 'there is no document'); return; }
    var shell = doc.querySelector('.ora-shell');
    var leftColumn = doc.querySelector('.left-column');
    var rightColumn = doc.querySelector('.right-column');
    var inputPane = doc.querySelector('.input-pane');
    if (!shell || !inputPane) {
      _geometryUnavailable(rec, [!shell ? '.ora-shell' : null,
        !inputPane ? '.input-pane' : null].filter(Boolean).join(' and ')
        + ' missing from the document');
      return;
    }
    rec.geometryWarned = false;
    var shellRect = shell.getBoundingClientRect();
    var leftRect = leftColumn ? leftColumn.getBoundingClientRect() : shellRect;
    var rightRect = rightColumn ? rightColumn.getBoundingClientRect() : shellRect;
    var inputRect = inputPane.getBoundingClientRect();
    var pad = 8;
    var top = Math.max(shellRect.top + pad, inputRect.top + pad);
    var height = Math.max(24, inputRect.bottom - pad - top);
    var left = leftRect.left + pad;
    var right = Math.max(left + 240, rightRect.right - pad);
    rec.el.style.setProperty('--conversation-browser-left', left + 'px');
    rec.el.style.setProperty('--conversation-browser-top', top + 'px');
    rec.el.style.setProperty('--conversation-browser-width', Math.max(240, right - left) + 'px');
    rec.el.style.setProperty('--conversation-browser-height', height + 'px');
  }

  function _startPositioning(rec) {
    // Never stack a second listener across repeat opens.
    _stopPositioning(rec);
    // One geometry warning per open, not one per resize tick.
    rec.geometryWarned = false;
    rec.onResize = function () { _position(rec); };
    if (_isFn(root.addEventListener)) root.addEventListener('resize', rec.onResize);
    if (_isFn(root.ResizeObserver)) {
      try {
        var obs = new root.ResizeObserver(function () { _position(rec); });
        var doc = root.document;
        GEOMETRY_SELECTORS.forEach(function (sel) {
          var el = doc && doc.querySelector(sel);
          if (!el) return;
          try { obs.observe(el); } catch (e) { /* one bad target must not stop the rest */ }
        });
        rec.observer = obs;
      } catch (e) {
        _warn('ResizeObserver could not be started for "' + rec.id + '": ' + _msg(e));
      }
    }
    _position(rec);
  }

  // Symmetric with _startPositioning and safe to call twice. A listener this
  // module attaches is a listener this module removes — on close AND on
  // unregister — so nothing survives the surface that needed it.
  function _stopPositioning(rec) {
    if (rec.onResize) {
      if (_isFn(root.removeEventListener)) root.removeEventListener('resize', rec.onResize);
      rec.onResize = null;
    }
    if (rec.observer) {
      try { rec.observer.disconnect(); } catch (e) { /* already gone */ }
      rec.observer = null;
    }
  }

  // ---- DOM ------------------------------------------------------------------

  function _build(rec) {
    var doc = root.document;
    if (!doc || !doc.body) {
      _warn('no document body; overlay "' + rec.id + '" cannot be mounted');
      return null;
    }

    var el = doc.createElement('div');
    el.className = 'conversation-browser-overlay';
    el.setAttribute('role', 'dialog');
    // Docked beside the workspace, deliberately leaving the rest of Ora
    // interactive — so it must not claim modal semantics.
    el.setAttribute('aria-modal', 'false');
    el.setAttribute('tabindex', '-1');
    // An attribute value, never a selector and never markup: an id may contain
    // quotes or angle brackets and must stay inert.
    el.setAttribute('data-ora-browse-overlay', rec.id);

    var panel = doc.createElement('div');
    panel.className = 'conversation-browser-panel';

    var top = doc.createElement('div');
    top.className = 'conversation-browser-top';
    // The shared `.conversation-browser-top` rule is sized for the Library's
    // FOUR header children (search / sort / search button / close) — its
    // template is `minmax(240px, 1fr) auto auto auto` with a 6px gap. This
    // header has two. The two surplus tracks resolve to 0px but their gutters
    // do not, leaving 12px of dead space right of the ×; and the 240px floor
    // on the first track gives the header a minimum of ~283.6px, wider than
    // the 240px minimum `_position` clamps the dock to — at which width
    // `.conversation-browser-panel`'s `overflow: hidden` clips the close
    // button out of existence, unclickable as well as invisible. Two tracks,
    // the first allowed to shrink, is the same layout with neither fault.
    // An inline style on an element this module owns — not a stylesheet.
    top.style.gridTemplateColumns = 'minmax(0, 1fr) auto';

    var title = doc.createElement('div');
    title.className = 'conversation-browser-status';

    var closeBtn = doc.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'conversation-browser-close';
    closeBtn.textContent = '×';

    var body = doc.createElement('div');
    body.className = 'conversation-browser-rows';

    top.appendChild(title);
    top.appendChild(closeBtn);
    panel.appendChild(top);
    panel.appendChild(body);
    el.appendChild(panel);
    doc.body.appendChild(el);

    closeBtn.addEventListener('click', function () {
      try {
        _closeRecord(rec);
      } catch (e) {
        _warn('closing "' + rec.id + '" from its close button failed: ' + _msg(e));
      }
    });

    el.addEventListener('keydown', function (e) {
      if (!e || e.key !== 'Escape') return;
      if (_isFn(e.preventDefault)) e.preventDefault();
      if (_isFn(e.stopPropagation)) e.stopPropagation();
      try {
        _closeRecord(rec);
      } catch (err) {
        _warn('closing "' + rec.id + '" from Escape failed: ' + _msg(err));
      }
    });

    rec.el = el;
    rec.body = body;
    rec.titleEl = title;
    rec.closeEl = closeBtn;
    return el;
  }

  // Everything this module put into the document for a record, taken back out.
  // One place, so the rebuild path and unregister cannot drift apart.
  function _discardDom(rec) {
    _stopPositioning(rec);
    if (rec.el && rec.el.parentNode) rec.el.parentNode.removeChild(rec.el);
    rec.el = null;
    rec.body = null;
    rec.titleEl = null;
    rec.closeEl = null;
  }

  // ---- open / close ---------------------------------------------------------

  // A docked surface hands focus back only when it still has focus to hand
  // back. `onClose` runs first and is entitled to move focus — opening another
  // surface from inside it is legitimate — and the rest of Ora is live the
  // whole time the overlay is up, so at any close somebody else may hold focus
  // for reasons that have nothing to do with this overlay.
  function _focusIsOursToHandBack(rec, focusBefore) {
    var doc = root.document;
    var body = doc ? doc.body : null;
    var now = _activeElement();
    // This overlay still holds it — including its own now-hidden root, which
    // is exactly the case focus restoration exists for.
    if (_contains(rec.el, now)) return true;
    // Somebody else holds it: the user's own input, or a surface a plugin
    // opened from inside this very onClose. Taking it would be a theft, and
    // for a second overlay it would also strand Escape, which only reaches
    // the dialog through the focus the open path gave it.
    if (now && now !== body) return false;
    // Nobody holds it. Claim it back only if this overlay — or nobody — held
    // it when the close began. Focus that some third element merely lost is
    // not ours to take.
    return _contains(rec.el, focusBefore) || !focusBefore || focusBefore === body;
  }

  function _closeRecord(rec) {
    var wasOpen = !!rec.open;
    rec.open = false;
    if (_openId === rec.id) _openId = null;
    if (rec.el) rec.el.classList.remove('is-open');
    _stopPositioning(rec);
    if (!wasOpen) return false;

    // Read BEFORE entering plugin code: hiding the root can already have sent
    // focus to the body, and onClose can send it anywhere at all.
    var focusBefore = _activeElement();

    var ctx = _ctx(rec);
    _callPlugin('onClose', rec.id, _read(rec.entry, 'onClose'), [ctx]);

    var target = rec.returnFocus;
    rec.returnFocus = null;
    if (target && _isFn(target.focus) && !_detached(target)
        && _focusIsOursToHandBack(rec, focusBefore)) {
      try { target.focus(); } catch (e) { /* the shell survives a dead focus target */ }
    }
    return true;
  }

  // One dock, one surface. Loops over every record rather than trusting
  // _openId alone, and contains each close so a throw from one entry cannot
  // abandon the rest.
  function _closeOthers(keepId) {
    Object.keys(_overlays).forEach(function (id) {
      var rec = _overlays[id];
      if (!rec || rec.id === keepId || !rec.open) return;
      try {
        _closeRecord(rec);
      } catch (e) {
        _warn('closing "' + rec.id + '" failed: ' + _msg(e));
      }
    });
  }

  function open(id) {
    var rec = _own(id);
    if (!rec) {
      _warn('open("' + id + '") — no overlay is registered under that id');
      return false;
    }
    if (rec.open) { _position(rec); return true; }

    // _closeOthers enters plugin code, and an onClose may open a surface of
    // its own. One dock holds one surface, so settle the dock before claiming
    // it rather than assuming a single pass emptied it.
    var settled = false;
    for (var pass = 0; pass < 4 && !settled; pass++) {
      _closeOthers(rec.id);
      // An onClose opened THIS overlay. That inner call ran the whole open
      // path — built, painted, fired onOpen. Carrying on here would clear the
      // body it just filled and run the plugin's render and onOpen a second
      // time for one open().
      if (rec.open) { _position(rec); return true; }
      settled = !_anyOtherOpen(rec.id);
    }
    if (!settled) {
      _warn('an onClose keeps opening another surface, so "' + rec.id
        + '" is opening with another overlay still on the dock');
    }

    // A plugin holds ctx.root and ctx.body for as long as it likes and can
    // take either out of the document — a render that rebuilds the panel, a
    // teardown that overreaches. rec.el stays truthy either way, so without
    // this the surface "reopens" into nothing: open() returns true, isOpen()
    // agrees, and there is neither a panel on screen nor a word about it.
    if (rec.el && (_detached(rec.el) || _detached(rec.body))) {
      _warn('the DOM for "' + rec.id + '" is no longer in the document — '
        + (_detached(rec.el) ? 'its root was removed' : 'its rows body was removed')
        + ' by something outside this module; rebuilding the surface');
      _discardDom(rec);
    }

    if (!rec.el && !_build(rec)) return false;

    var doc = root.document;
    var active = doc && doc.activeElement;
    // A surface opened from inside another surface's onClose would otherwise
    // capture that closing overlay's own hidden root and, on its own close,
    // hand focus to something nobody can see.
    if (_inClosedOverlay(active) || _detached(active)) active = null;
    rec.returnFocus = (active && active !== doc.body && _isFn(active.focus)) ? active : null;

    var label = _label(rec);
    rec.el.setAttribute('aria-label', label);
    rec.titleEl.textContent = label;
    rec.closeEl.setAttribute('aria-label', 'Close ' + label);

    // The plugin owns the body: repaint it from scratch on every open.
    while (rec.body.firstChild) rec.body.removeChild(rec.body.firstChild);

    rec.el.classList.add('is-open');
    rec.open = true;
    _openId = rec.id;
    _startPositioning(rec);

    var ctx = _ctx(rec);
    var render = _read(rec.entry, 'render');
    if (!_isFn(render)) {
      _warn('entry.render for "' + rec.id + '" is no longer a function; '
        + 'the surface opens empty');
    } else {
      _callPlugin('render', rec.id, render, [rec.body, ctx]);
    }
    // The plugin may have closed itself from inside render.
    if (!rec.open) return true;

    _callPlugin('onOpen', rec.id, _read(rec.entry, 'onOpen'), [ctx]);
    if (!rec.open) return true;

    // Focus the dialog itself: Escape has to reach the overlay's keydown
    // handler, and a screen reader should announce the surface it just opened.
    try { rec.el.focus(); } catch (e) { /* non-focusable environments */ }
    return true;
  }

  function close(id) {
    if (id === undefined || id === null) {
      if (!_openId) return false;
      var current = _own(_openId);
      if (!current) { _openId = null; return false; }
      return _closeRecord(current);
    }
    var rec = _own(id);
    if (!rec || !rec.open) return false;
    return _closeRecord(rec);
  }

  // ---- registration ---------------------------------------------------------

  function _validate(entry, id) {
    if (!entry || typeof entry !== 'object') return 'entry must be an object';
    if (!_isStr(id)) return 'entry.id is required';
    if (!_isStr(_read(entry, 'label'))) return 'entry.label is required';
    if (!_isFn(_read(entry, 'render'))) return 'entry.render must be a function';
    var onOpen = _read(entry, 'onOpen');
    if (onOpen !== undefined && onOpen !== null && !_isFn(onOpen)) {
      return 'entry.onOpen must be a function when present';
    }
    var onClose = _read(entry, 'onClose');
    if (onClose !== undefined && onClose !== null && !_isFn(onClose)) {
      return 'entry.onClose must be a function when present';
    }
    if (_own(id)) return 'id "' + id + '" is already registered';
    return null;
  }

  function register(entry) {
    // Read the id exactly once: everything downstream uses the record's copy,
    // so a mutating getter cannot make a record unreachable.
    var id = (entry && typeof entry === 'object') ? _read(entry, 'id') : undefined;
    var problem = _validate(entry, id);
    if (problem) {
      _warn('register rejected: ' + problem);
      return function () { return false; };
    }

    var rec = {
      id: id,
      entry: entry,
      label: _read(entry, 'label'),
      el: null,
      body: null,
      titleEl: null,
      closeEl: null,
      open: false,
      onResize: null,
      observer: null,
      returnFocus: null,
      geometryWarned: false
    };
    _overlays[id] = rec;

    // Bound to the RECORD, not the id: a stale handle from an earlier
    // registration must not evict a different overlay later registered under
    // the same id.
    return function () { return _remove(rec); };
  }

  function _remove(rec) {
    if (!rec || _own(rec.id) !== rec) return false;
    _closeRecord(rec);
    // Belt and braces: nothing may outlive the surface, open or not.
    _discardDom(rec);
    delete _overlays[rec.id];
    return true;
  }

  function isOpen(id) {
    if (id === undefined || id === null) return !!_openId;
    var rec = _own(id);
    return !!(rec && rec.open);
  }

  function has(id) { return !!_own(id); }
  function get(id) { var rec = _own(id); return rec ? rec.entry : null; }

  function list() {
    var out = [];
    Object.keys(_overlays).forEach(function (id) {
      var rec = _overlays[id];
      if (rec) out.push(rec.entry);
    });
    return out;
  }

  root.OraBrowseOverlays = {
    register: register,
    open:     open,
    close:    close,
    isOpen:   isOpen,
    has:      has,
    get:      get,
    list:     list
  };
})(typeof window !== 'undefined' ? window : globalThis);
