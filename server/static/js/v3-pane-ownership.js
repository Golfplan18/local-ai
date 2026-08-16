/* v3-pane-ownership.js — plugin ownership of a workspace pane in the V3 shell.
 *
 * Ora already lets one feature take a whole pane for the duration of a mode:
 * body class `pane-mode-video` hands the Exhibits pane to the video editor, and
 * six modules (capture-controls, media-library, transcript-panel,
 * preview-monitor, timeline-editor, render-controls) show themselves when the
 * shell announces it. That mechanism is hand-written in index-v3.html and every
 * participant names 'video' literally, so an add-on cannot take a pane without
 * editing Ora's own shell. This module is the one seam that fixes that.
 *
 * One pane exists:
 *
 *   exhibits — the canvas and media pane. The only pane the shell's CSS can
 *              actually surrender today (body.pane-mode-* rules target
 *              .visual-panel and the panels stacked over it).
 *
 * Named for what the pane MEANS rather than where it sits, matching the button
 * mount points. An unknown pane name is rejected, exactly as an unknown button
 * position is: a plugin does not get to invent a pane the CSS has never heard
 * of and then wonder why nothing moved.
 *
 * The shell stays the single writer
 * ---------------------------------
 * This registry never touches a `pane-mode-*` class and never dispatches
 * `ora:pane-mode-toggle`. It asks `window.OraPaneMode.set(...)` — the same
 * handle the slash-command client and the video button already use — and then
 * waits to be told. A mode is "held" only once the shell is in it.
 *
 * "Is in it", not "said so": every announcement is reconciled against
 * `OraPaneMode.current()` and the event's own `detail` is used only as a
 * fallback when the shell cannot be asked. An announcement can be stale by the
 * time this listener sees it — an earlier listener re-entered the shell and
 * moved it somewhere else mid-dispatch — and a `CustomEvent` of that name can
 * arrive from anywhere carrying no detail at all. Neither may be allowed to
 * move ownership somewhere the body class isn't. The body class decides; the
 * event is only the prompt to go and look.
 *
 * The registry listens because an exit can arrive that the owner never asked
 * for: the user clicks the video button while a plugin mode is up, or another
 * module calls `OraPaneMode.set(null)` directly (slash-command-client does
 * exactly that, and so does an owner handing its own pane back from inside
 * `onTake`). The owner still gets its `onRelease`.
 *
 * Shell-owned mode names are reserved
 * -----------------------------------
 * The shell declares its own pane modes in markup, one `[data-pane-mode-button]`
 * per mode (index-v3.html:1163). Registration reads that markup and refuses a
 * name the shell has already claimed — otherwise a plugin could register the
 * built-in's name and be handed the user's own session: `onTake` for a mode it
 * never asked for, `owner()` reporting it, `release()` ending a live session
 * out from under the user, `take()` switching the built-in on, and the pane
 * held against every other plugin for the session's duration.
 *
 * The reservation is READ, never listed. No built-in's name appears in this
 * file, so a shell that gains or renames a pane mode needs no edit here and
 * cannot drift from a copy kept alongside it.
 *
 * When the markup cannot be read — no document, or the shell has not rendered
 * yet when a plugin registers — the registry cannot know what is reserved, and
 * refusing every registration would strand plugins for a collision that
 * probably isn't there. So it fails open at registration and checks again at
 * the two points where the name would actually take effect: adopting an
 * announcement, and asking the shell to enter a mode. Both of those imply a
 * live shell, so the reservation is enforced where it bites even when it could
 * not be read where it was declared.
 *
 * No write-back, structurally
 * ---------------------------
 * Listening and writing in the same module is how you get a ping-pong: the
 * shell announces, a listener answers by setting the mode again, which
 * announces again. The six existing listeners are all safe because none of
 * them writes back — a property of their code, not of the event.
 *
 * Here it is a property of the code too, but enforced in one place rather than
 * remembered at each call site: `_askShell` is the ONLY function in this file
 * that calls `OraPaneMode.set`, and it refuses outright while any
 * `ora:pane-mode-toggle` handler is on the stack. `take()`, `release()` and
 * unregistering all funnel through it, so a plugin callback that calls back
 * into the registry from inside the event — including one whose `onRelease`
 * calls `release()` again — cannot reach the shell. It gets a warning instead.
 *
 * The guarantee is exactly that: no announcement can be answered while it is
 * still being announced, however deep the synchronous call chain and however
 * many nested announcements it contains. It is not a rate limit. A callback
 * that defers — `setTimeout`, `queueMicrotask`, a promise tail — runs after the
 * announcement is off the stack, and is then an ordinary caller like any other
 * module, free to ask the shell for a mode as often as it schedules itself to.
 * Ora's shell arbitrates that, as it does for every other caller; this seam
 * does not add a gate of its own.
 *
 * Public API (window.OraPanes)
 * ---------------------------
 *   .register(entry) → unregister function
 *       entry.pane       'exhibits'                                  (required)
 *       entry.mode       unique string; becomes the shell's body class
 *                        `pane-mode-<mode>`                          (required)
 *       entry.onTake     function(ctx) — the shell entered your mode (optional)
 *       entry.onRelease  function(ctx) — the shell left your mode    (optional)
 *       entry.label      human name, used in warnings                (optional)
 *       ctx is { pane, mode, previous, current, requested } — `requested` is
 *       true only when the shell landed in exactly the mode this registry had
 *       just asked for. Anything else reads false: the user, another module,
 *       or the plugin itself calling `OraPaneMode.set` — including a module
 *       that answers our ask by sending the shell somewhere else instead.
 *       The returned handle removes THAT entry, releasing the pane first if it
 *       is still held. Calling it twice, or after something else has claimed
 *       the same mode name, returns false and removes nothing.
 *
 *   .take(mode)     → boolean — ask the shell to enter that mode
 *   .release(mode?) → boolean — ask the shell to leave a mode this registry
 *                     owns; with no argument, whichever it currently holds
 *   .owner(pane)    → the mode currently holding that pane, or null
 *   .has(mode) / .get(mode) / .list(pane?) / .panes()
 *
 * Video is deliberately NOT registered here, and the word 'video' appears in
 * this file only in prose. Video's mode name travels through the shared event
 * as data and is read back out of the shell's markup as data; it is never a
 * case in this code. Three consequences fall out of that and are load-bearing:
 * a built-in's name cannot be registered at all (above), `release('video')` is
 * refused (a plugin cannot evict a built-in through the registry), and `take()`
 * is refused while any other pane mode is live (a plugin cannot displace video,
 * or another plugin, mid-session — the incumbent keeps the pane until the user
 * or the shell lets go).
 *
 * Failure behaviour is fail-open with loud logging, per Ora's standing rule:
 * an unknown pane, a duplicate mode, a missing `window.OraPaneMode`, a shell
 * setter that throws, a callback that throws or rejects — each warns and Ora
 * carries on. A plugin cannot take the shell down through this seam.
 */
(function (root) {
  'use strict';

  // Evaluating this file twice — two script tags, a plugin bundling its own
  // copy, the same file served under a second URL — would otherwise leave two
  // registries with two ownership records, and two document listeners firing
  // every callback twice. First evaluation wins; a later one is a no-op.
  if (root.OraPanes) return;

  // A list, not an object-as-map: a pane name of '__proto__' or 'constructor'
  // must be an unknown pane, not an inherited Object.prototype member that
  // reads back as a valid spec.
  var PANES = [
    { name: 'exhibits', label: 'the canvas and media pane' }
  ];

  // Registration order; each record is { entry, pane, mode }. Also a list for
  // the same reason — the mode name is plugin-supplied and lands in a body
  // class, so it must be allowed to be any single token, '__proto__' included.
  var _records = [];

  // The record holding a pane, or null. Written ONLY against a body class the
  // shell is observably in — from a reconciled announcement, from take() when
  // it finds the class already there, or cleared by a local drop when the
  // shell is unreachable. Never from a hopeful ask.
  var _holder = null;

  // How many ora:pane-mode-toggle handlers are on the stack. This is the
  // no-write-back interlock; see _askShell.
  //
  // A counter, not a flag: the shell dispatches synchronously, so one
  // announcement can contain another (an owner hands the pane back from inside
  // its own onTake; a listener re-enters the shell). A flag would be cleared by
  // the inner pass's exit while the outer announcement is still on the stack,
  // and every callback after that point in the outer pass would be free to
  // write back — the loop the interlock exists to make impossible.
  var _shellEventDepth = 0;

  // The mode this module's own OraPaneMode.set call is asking for, or
  // _NOT_ASKING when it is not asking. The shell dispatches synchronously, so
  // the handler reads this to tell a transition we asked for from one we did
  // not — by comparing it with where the shell actually landed, because a
  // module that re-enters mid-ask can send it somewhere we never named.
  var _NOT_ASKING = {};
  var _asked = _NOT_ASKING;

  function _warn(message) {
    if (root.console && typeof root.console.warn === 'function') {
      root.console.warn('[v3-pane-ownership] ' + message);
    }
  }

  function _isFn(v) { return typeof v === 'function'; }
  function _isStr(v) { return typeof v === 'string' && v.length > 0; }
  function _msg(err) { return String((err && err.message) || err); }

  function _paneSpec(name) {
    for (var i = 0; i < PANES.length; i++) {
      if (PANES[i].name === name) return PANES[i];
    }
    return null;
  }

  function _paneNames() {
    return PANES.map(function (p) { return p.name; });
  }

  function _paneLabel(name) {
    var spec = _paneSpec(name);
    return '"' + name + '"' + (spec ? ' (' + spec.label + ')' : '');
  }

  function _lookup(mode) {
    if (!_isStr(mode)) return null;
    for (var i = 0; i < _records.length; i++) {
      if (_records[i].mode === mode) return _records[i];
    }
    return null;
  }

  // Entry fields are read behind a try every time, because the entry belongs
  // to a plugin: `label` may be a getter that throws, and a thrown getter must
  // not escape into the shell through a logging call of all things.
  function _name(rec) {
    var label = null;
    try { label = rec.entry.label; } catch (err) { label = null; }
    return 'pane mode "' + rec.mode + '"' + (_isStr(label) ? ' (' + label + ')' : '');
  }

  // ---- the shell handle -----------------------------------------------------

  /* Has the shell claimed this mode name for itself?
   *
   * The shell declares its own pane modes in markup — one
   * [data-pane-mode-button] per mode (index-v3.html:1163) — so the reservation
   * is read from the DOM at the moment it is needed, not copied into a list
   * here. A list would put the built-ins' names in this file, which is the
   * coupling this seam exists to remove, and it would be wrong the first time
   * the shell gained or renamed one.
   *
   * Unreadable markup answers false, not "reserved": with no document, or
   * before the shell has rendered, refusing everything would strand plugins
   * over a collision that probably is not there. The callers that matter ask
   * again later, when a live shell has necessarily rendered. */
  function _shellClaims(mode) {
    if (!_isStr(mode)) return false;
    var doc = root.document;
    if (!doc || !_isFn(doc.querySelectorAll)) return false;
    var buttons;
    try {
      buttons = doc.querySelectorAll('[data-pane-mode-button]');
    } catch (err) {
      _warn('could not read the shell\'s own pane modes from the DOM: ' + _msg(err));
      return false;
    }
    for (var i = 0; i < buttons.length; i++) {
      var claimed = null;
      // getAttribute rather than dataset: one property read, and a shell that
      // ever renders a non-element match cannot throw its way past the check.
      try { claimed = buttons[i].getAttribute('data-pane-mode-button'); }
      catch (err) { claimed = null; }
      if (claimed === mode) return true;
    }
    return false;
  }

  function _shell() {
    var api = root.OraPaneMode;
    if (!api || !_isFn(api.set) || !_isFn(api.current)) return null;
    return api;
  }

  // Returns the shell's current pane mode, null for none, or undefined when
  // the shell could not be asked — a distinct answer, because "no mode" and
  // "I don't know" must not lead to the same decision.
  function _currentMode(api) {
    var cur;
    try {
      cur = api.current();
    } catch (err) {
      _warn('window.OraPaneMode.current() threw: ' + _msg(err));
      return undefined;
    }
    return _isStr(cur) ? cur : null;
  }

  /* The ONLY call to OraPaneMode.set in this module.
   *
   * Every path that wants a pane-mode change goes through here, so the
   * no-write-back rule is enforced once instead of being remembered at three
   * call sites. While any ora:pane-mode-toggle handler is on the stack this
   * refuses, so an announcement cannot be answered while it is still being
   * announced: plugin callbacks run inside that window, and a callback that
   * calls take() or release() — directly, or through some helper of its own —
   * cannot reach the shell no matter how deep the synchronous call chain is,
   * or how many nested announcements it contains. */
  function _askShell(mode) {
    if (_shellEventDepth > 0) {
      _warn('refused to set pane mode ' + JSON.stringify(mode) + ' from inside an '
        + 'ora:pane-mode-toggle handler — the shell owns the transition it is '
        + 'already announcing, and answering it here would loop');
      return false;
    }
    var api = _shell();
    if (!api) {
      _warn('window.OraPaneMode is not available; the shell owns the body class '
        + 'and this registry will not set one itself');
      return false;
    }
    _asked = mode;
    try {
      api.set(mode);
      return true;
    } catch (err) {
      _warn('window.OraPaneMode.set(' + JSON.stringify(mode) + ') threw: ' + _msg(err));
      return false;
    } finally {
      _asked = _NOT_ASKING;
    }
  }

  // ---- plugin callbacks -----------------------------------------------------

  // Never throws, never lets a rejection escape. A plugin's bug is a warning.
  function _invoke(rec, which, ctx) {
    var fn;
    try {
      fn = rec.entry[which];
    } catch (err) {
      _warn(_name(rec) + ': reading ' + which + ' threw: ' + _msg(err));
      return;
    }
    if (!_isFn(fn)) return;

    var out;
    try {
      out = fn.call(rec.entry, ctx);
    } catch (err) {
      _warn(_name(rec) + ': ' + which + ' threw: ' + _msg(err));
      return;
    }

    // A callback may be async. An unhandled rejection is a browser-level error
    // the user sees; route it into the same warn path as a synchronous throw.
    var then;
    try { then = out ? out.then : null; } catch (err) { then = null; }
    if (!_isFn(then)) return;
    try {
      then.call(out, null, function (err) {
        _warn(_name(rec) + ': ' + which + ' rejected: ' + _msg(err));
      });
    } catch (err) {
      _warn(_name(rec) + ': ' + which + ' returned a broken thenable: ' + _msg(err));
    }
  }

  // Clears ownership BEFORE calling onRelease, so onRelease runs exactly once
  // even if the plugin re-enters, and a re-entrant release() finds nothing to
  // release rather than a record it is already leaving.
  //
  // `previous` is the leaving record's own mode at every call site: that is
  // what the plugin is leaving, and it stays true even when the announcement
  // that triggered the drop described some other transition.
  function _dropHolder(info) {
    var leaving = _holder;
    if (!leaving) return;
    _holder = null;
    _invoke(leaving, 'onRelease', {
      pane: leaving.pane,
      mode: leaving.mode,
      previous: leaving.mode,
      current: info.current,
      requested: !!info.requested
    });
  }

  // The mirror of _dropHolder: ownership is recorded BEFORE onTake, so a
  // plugin that calls back into the registry from inside its own onTake sees
  // the pane it has just been given rather than an unowned one.
  function _adopt(rec, info) {
    _holder = rec;
    _invoke(rec, 'onTake', {
      pane: rec.pane,
      mode: rec.mode,
      previous: info.previous,
      current: info.current,
      requested: !!info.requested
    });
  }

  // ---- the shell's announcement ---------------------------------------------

  function _detail(e) {
    var d = null;
    try { d = e ? e.detail : null; } catch (err) { d = null; }
    var cur = null;
    var prev = null;
    try {
      if (d) { cur = d.current; prev = d.previous; }
    } catch (err) { cur = null; prev = null; }
    return {
      current: _isStr(cur) ? cur : null,
      previous: _isStr(prev) ? prev : null
    };
  }

  function _onPaneModeToggle(e) {
    // Every pass counts, nested ones included. A nested announcement is a real
    // transition — the shell has already moved by the time it is dispatched —
    // and skipping it was how an owner could be stranded: hand the pane back
    // from inside your own onTake and the exit was discarded as "the outer
    // pass's business", leaving onRelease unfired and owner() lying forever.
    _shellEventDepth++;
    try {
      var d = _detail(e);

      // Reconcile against the shell rather than believing the event. By the
      // time this listener runs, the transition the event describes may be two
      // transitions old (an earlier listener re-entered the shell), and an
      // ora:pane-mode-toggle CustomEvent can arrive from anywhere carrying no
      // detail at all — which would otherwise read as "the shell left every
      // mode" and evict a live owner whose class is still on <body>.
      var api = _shell();
      var cur;
      if (api) {
        cur = _currentMode(api);
      } else {
        _warn('window.OraPaneMode is not available while an ora:pane-mode-toggle '
          + 'is being handled; falling back to the event\'s own detail');
        cur = undefined;
      }
      // The shell could not be asked. The event is all there is, so use it —
      // refusing to act would freeze ownership against a shell that has plainly
      // moved, and the next reconcilable announcement corrects it.
      if (cur === undefined) cur = d.current;

      // We asked for this only if the shell landed where we asked it to.
      var requested = (_asked !== _NOT_ASKING && _asked === cur);

      // Left first, so an owner is always released before a successor is told
      // it has the pane, and so the two never both believe they hold it.
      if (_holder && _holder.mode !== cur) {
        _dropHolder({ current: cur, requested: requested });
      }

      if (cur && !_holder) {
        var rec = _lookup(cur);
        if (rec && _shellClaims(rec.mode)) {
          // Registered before the shell's markup could be read (see
          // _shellClaims). The shell owns this mode and this is the user's own
          // session; the record does not get it.
          _warn('the shell announced pane mode ' + JSON.stringify(cur) + ', which it '
            + 'claims in its own markup, and ' + _name(rec) + ' is registered under '
            + 'that name — it was registered before that markup could be read. The '
            + 'shell keeps its own session; the registration is inert');
        } else if (rec) {
          _adopt(rec, {
            // The event's `previous` describes the transition the event
            // announced. When the shell has moved on since, that predecessor
            // is not this one's, and no honest answer is available.
            previous: d.current === cur ? d.previous : null,
            current: cur,
            requested: requested
          });
        }
      }
    } finally {
      _shellEventDepth--;
    }
  }

  // ---- registration ---------------------------------------------------------

  function _validate(entry) {
    if (!entry || typeof entry !== 'object') return { problem: 'entry must be an object' };

    var pane, mode, onTake, onRelease;
    try {
      pane = entry.pane;
      mode = entry.mode;
      onTake = entry.onTake;
      onRelease = entry.onRelease;
    } catch (err) {
      return { problem: 'reading entry fields threw: ' + _msg(err) };
    }

    if (!_isStr(pane)) return { problem: 'entry.pane is required' };
    if (!_paneSpec(pane)) {
      return { problem: 'unknown pane "' + pane + '" (expected one of: '
        + _paneNames().join(', ') + ')' };
    }
    if (!_isStr(mode)) return { problem: 'entry.mode is required' };
    // The shell does classList.add('pane-mode-' + mode) AFTER removing the old
    // class. A mode with whitespace makes that throw mid-transition, leaving
    // the body with no pane-mode class, the buttons unsynced and no event
    // dispatched — so it is refused here rather than half-breaking the shell.
    if (/\s/.test(mode)) {
      return { problem: 'entry.mode "' + mode + '" contains whitespace; the shell '
        + 'turns it into the body class "pane-mode-' + mode + '", which is not a '
        + 'valid class token' };
    }
    // The shell's own pane modes, read from its markup rather than listed here.
    if (_shellClaims(mode)) {
      return { problem: 'mode "' + mode + '" is a pane mode the shell declares in its '
        + 'own markup ([data-pane-mode-button="' + mode + '"]); the shell owns that '
        + 'name, and a plugin holding it would be handed the user\'s own sessions' };
    }
    if (_lookup(mode)) return { problem: 'mode "' + mode + '" is already registered' };
    if (onTake !== undefined && onTake !== null && !_isFn(onTake)) {
      return { problem: 'entry.onTake must be a function when provided' };
    }
    if (onRelease !== undefined && onRelease !== null && !_isFn(onRelease)) {
      return { problem: 'entry.onRelease must be a function when provided' };
    }
    // One owner per pane: a newcomer's idea of the pane's state is already
    // wrong if someone is mid-takeover, so the incumbent keeps it.
    if (_holder && _holder.pane === pane) {
      return { problem: 'pane ' + _paneLabel(pane) + ' is currently held by pane mode "'
        + _holder.mode + '"; the incumbent keeps it' };
    }

    return { pane: pane, mode: mode };
  }

  function register(entry) {
    var v = _validate(entry);
    if (v.problem) {
      _warn('register rejected: ' + v.problem);
      return function () { return false; };
    }
    // pane and mode are snapshotted as plain strings. They decide a body class
    // and an ownership identity, and a plugin getter that answers differently
    // later would leave the registry pointing at a mode the shell never had.
    var rec = { entry: entry, pane: v.pane, mode: v.mode };
    _records.push(rec);
    // The handle removes THIS record, not whatever currently answers to its
    // mode name. A handle kept past its own removal is ordinary (a plugin
    // tears down twice, or reloads itself under the same mode); keyed by name
    // it would silently evict the live successor.
    return function () { return _remove(rec); };
  }

  function _remove(rec) {
    if (_records.indexOf(rec) < 0) return false;

    // Give the pane back before forgetting how to.
    if (_holder === rec) {
      release(rec.mode);
      if (_holder === rec) {
        // The shell could not be asked (absent, throwing, or we are inside its
        // own event). Drop the record so the plugin still gets its onRelease,
        // and say plainly that the body class outlives it.
        _warn(_name(rec) + ' was unregistered while it still held pane '
          + _paneLabel(rec.pane) + ', and the shell could not be asked to leave; '
          + 'the pane-mode class stays until something else exits it');
        _dropHolder({ current: rec.mode, requested: true });
      }
    }

    // Re-read the index: a callback above may have unregistered entries — this
    // one included — while we were releasing. A stale index here would splice
    // out whichever unrelated record had shifted into that slot.
    var i = _records.indexOf(rec);
    if (i < 0) {
      // Gone already: the onRelease above unregistered this very record. That
      // is the removal the caller asked for, so report it rather than deny it.
      return true;
    }
    _records.splice(i, 1);
    return true;
  }

  // ---- the public verbs -----------------------------------------------------

  function take(mode) {
    var rec = _lookup(mode);
    if (!rec) {
      _warn('take(' + JSON.stringify(mode) + ') — no plugin is registered for that pane mode');
      return false;
    }
    if (_shellClaims(rec.mode)) {
      // Registered before the shell's markup could be read (see _shellClaims).
      _warn('take("' + rec.mode + '") — the shell claims that pane mode in its own '
        + 'markup; only the shell enters a mode the shell owns');
      return false;
    }
    var api = _shell();
    if (!api) {
      _warn('take("' + rec.mode + '") — window.OraPaneMode is not available; the '
        + 'shell owns the body class and this registry will not set one itself');
      return false;
    }
    var cur = _currentMode(api);
    if (cur === undefined) return false;
    if (cur === rec.mode) {
      if (_holder === rec) return true;   // already held; asking again is a no-op
      if (_holder) {
        // The class says one mode and the registry's holder says another. That
        // is drift the registry did not cause and cannot safely resolve by
        // guessing which of the two owners to strand.
        _warn('take("' + rec.mode + '") — the shell is in that pane mode, but this '
          + 'registry has pane mode "' + _holder.mode + '" recorded as holding '
          + _paneLabel(rec.pane) + '; not reassigning ownership from here');
        return false;
      }
      // The body class is ground truth and already names this record's mode,
      // yet no announcement of it ever reached this registry: a pane-mode class
      // that was on <body> before this file evaluated, or a previous owner that
      // tore itself down while the shell could not be asked to leave. Adopt
      // what is actually there — reporting success without ownership would
      // leave a mode nothing in the public API could release.
      _warn('take("' + rec.mode + '") — the shell was already in that pane mode and '
        + 'this registry never saw it announced; adopting the live class so the mode '
        + 'can be released rather than sticking to ' + _paneLabel(rec.pane));
      _adopt(rec, { previous: null, current: cur, requested: true });
      return true;
    }
    if (cur !== null) {
      _warn('take("' + rec.mode + '") — pane mode "' + cur + '" is already active; '
        + 'the incumbent keeps pane ' + _paneLabel(rec.pane));
      return false;
    }
    return _askShell(rec.mode);
  }

  function release(mode) {
    var rec;
    if (mode === undefined || mode === null) {
      rec = _holder;
      if (!rec) {
        _warn('release() — no registered pane mode is currently held');
        return false;
      }
    } else {
      rec = _lookup(mode);
      if (!rec) {
        // Includes any built-in mode: this registry only ever releases what it
        // owns, so a plugin cannot use it to exit somebody else's mode.
        _warn('release(' + JSON.stringify(mode) + ') — no plugin is registered for '
          + 'that pane mode; this registry only releases modes it owns');
        return false;
      }
      if (_holder !== rec) {
        _warn('release("' + rec.mode + '") — that mode does not currently hold pane '
          + _paneLabel(rec.pane));
        return false;
      }
    }

    var api = _shell();
    if (!api) {
      _warn('release("' + rec.mode + '") — window.OraPaneMode is not available');
      return false;
    }
    var cur = _currentMode(api);
    if (cur === undefined) return false;
    if (cur !== rec.mode) {
      // The shell moved on without our hearing about it. Asking it to leave
      // now would exit whatever is there instead — possibly a built-in.
      _warn('release("' + rec.mode + '") — the shell is in pane mode '
        + JSON.stringify(cur) + '; dropping the stale ownership record rather '
        + 'than asking the shell to leave a mode this registry does not own');
      _dropHolder({ current: cur, requested: true });
      return false;
    }
    return _askShell(null);
  }

  function owner(pane) {
    // Warns on an unknown pane because null is otherwise indistinguishable
    // from "nobody holds it" — a typo would read as a legitimate answer.
    if (!_isStr(pane) || !_paneSpec(pane)) {
      _warn('owner(' + JSON.stringify(pane) + ') — unknown pane (expected one of: '
        + _paneNames().join(', ') + ')');
      return null;
    }
    return _holder && _holder.pane === pane ? _holder.mode : null;
  }

  function has(mode) { return !!_lookup(mode); }

  function get(mode) {
    var rec = _lookup(mode);
    return rec ? rec.entry : null;
  }

  // An unknown pane yields an empty list rather than a warning: unlike
  // owner(), an empty array is not ambiguous.
  function list(pane) {
    var out = [];
    _records.forEach(function (rec) {
      if (!pane || rec.pane === pane) out.push(rec.entry);
    });
    return out;
  }

  function panes() { return _paneNames(); }

  if (root.document && _isFn(root.document.addEventListener)) {
    root.document.addEventListener('ora:pane-mode-toggle', _onPaneModeToggle);
  }

  root.OraPanes = {
    register: register,
    take:     take,
    release:  release,
    owner:    owner,
    has:      has,
    get:      get,
    list:     list,
    panes:    panes
  };
})(typeof window !== 'undefined' ? window : globalThis);
