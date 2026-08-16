#!/usr/bin/env node
/* Focused jsdom tests for plugin ownership of a workspace pane.
 *
 * Run:
 *   node ~/ora/server/static/tests/test-v3-pane-ownership.js
 */

'use strict';

var path = require('path');

var COMPILER_TEST_NODE_MODULES = path.resolve(
  __dirname, '..', 'ora-visual-compiler', 'tests', 'node_modules'
);
var JSDOM_PATH = path.join(COMPILER_TEST_NODE_MODULES, 'jsdom');

var jsdom;
try {
  jsdom = require(JSDOM_PATH);
} catch (e) {
  console.error('error: jsdom not available at ' + JSDOM_PATH);
  process.exit(2);
}

var MODULE_PATH = path.resolve(__dirname, '..', 'js', 'v3-pane-ownership.js');

// The real video pane-mode button, copied from index-v3.html:1162-1164 — the
// aria-pressed sync in the stand-in below only means anything against markup
// the shell actually queries for.
var dom = new jsdom.JSDOM(
  '<!doctype html><html><body>'
  + '<div class="input-pane-toolbar bridge-toolbar bridge-toolbar--right">'
  +   '<button class="input-pane-toolbar__btn" type="button"'
  +          ' aria-label="Video editing" data-pane-mode-button="video"'
  +          ' id="spineVideoMode"></button>'
  + '</div>'
  + '<div class="visual-panel"></div>'
  + '</body></html>',
  { url: 'http://localhost/' }
);

var w = dom.window;
global.window = w;
global.document = w.document;

var warnings = [];
w.console = Object.assign({}, console, {
  warn: function (m) { warnings.push(String(m)); }
});

// A rejected callback that escaped would surface here rather than as a warning.
var unhandled = [];
process.on('unhandledRejection', function (err) {
  unhandled.push(String((err && err.message) || err));
});

var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? '  - ' + detail : ''));
}

function summarize() {
  var total = results.length;
  var passed = results.filter(function (r) { return r.ok; }).length;
  console.log('');
  console.log(passed + ' / ' + total + ' tests passed');
  if (passed < total) {
    console.log('FAILURES:');
    results.filter(function (r) { return !r.ok; }).forEach(function (r) {
      console.log('  - ' + r.name + ' :: ' + (r.detail || '(no detail)'));
    });
    process.exit(1);
  }
  process.exit(0);
}

function warned(re) {
  return warnings.some(function (m) { return re.test(m); });
}

function paneModeClasses() {
  return Array.prototype.slice.call(w.document.body.classList)
    .filter(function (c) { return c.indexOf('pane-mode-') === 0; });
}

// ═══════════════════════════════════════════════════════════════════════════
// The shell stand-in.
//
// This mirrors server/index-v3.html lines 1812-1843 — currentPaneMode(),
// setPaneMode(mode), and the [data-pane-mode-button] click wiring — keeping
// the semantics that matter: replace ANY existing pane-mode-* class rather
// than toggling one, sync aria-pressed on every pane-mode button (true only
// for the one whose mode is now current), dispatch ora:pane-mode-toggle on
// document with { previous, current }, and expose { current, set } as
// window.OraPaneMode. Click toggles: clicking the button for the mode that is
// already current exits it; clicking it from a DIFFERENT mode switches
// straight to it.
//
// The implicit exits at index-v3.html:1859-1871 are mirrored too, INCLUDING
// their literal `=== 'video'` test — they are video-specific in the real
// shell, and a stand-in that generalised them would prove a behaviour the
// shell does not have.
// ═══════════════════════════════════════════════════════════════════════════
var document = w.document;

var currentPaneMode = function () {
  var list = document.body.classList;
  for (var i = 0; i < list.length; i++) {
    if (list[i].indexOf('pane-mode-') === 0) return list[i].slice('pane-mode-'.length);
  }
  return null;
};

var setPaneMode = function (mode) {
  var prev = currentPaneMode();
  Array.prototype.slice.call(document.body.classList)
    .filter(function (c) { return c.indexOf('pane-mode-') === 0; })
    .forEach(function (c) { document.body.classList.remove(c); });
  if (mode) document.body.classList.add('pane-mode-' + mode);
  Array.prototype.forEach.call(
    document.querySelectorAll('[data-pane-mode-button]'),
    function (b) {
      b.setAttribute('aria-pressed', b.dataset.paneModeButton === mode ? 'true' : 'false');
    }
  );
  document.dispatchEvent(new w.CustomEvent('ora:pane-mode-toggle', {
    detail: { previous: prev, current: mode || null }
  }));
};

Array.prototype.forEach.call(
  document.querySelectorAll('[data-pane-mode-button]'),
  function (btn) {
    btn.setAttribute('aria-pressed', 'false');
    var mode = btn.dataset.paneModeButton;
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var cur = currentPaneMode();
      setPaneMode(cur === mode ? null : mode);
    });
  }
);

w.OraPaneMode = { current: currentPaneMode, set: setPaneMode };

var _lastSelectedConvForPaneExit = null;
document.addEventListener('ora:new-thread-requested', function () {
  if (currentPaneMode() === 'video') setPaneMode(null);
});
document.addEventListener('ora:conversation-selected', function (e) {
  var d = (e && e.detail) || {};
  var cid = d.conversation_id || d.id || null;
  if (currentPaneMode() === 'video'
      && cid && _lastSelectedConvForPaneExit
      && cid !== _lastSelectedConvForPaneExit) {
    setPaneMode(null);
  }
  _lastSelectedConvForPaneExit = cid;
});

// A listener shaped exactly like server/static/capture-controls.js:842 — the
// pattern all six video modules share. It shows on 'video' and hides on
// anything else, and it never writes back.
var videoToolbarVisible = false;
var videoToolbarShows = 0;
document.addEventListener('ora:pane-mode-toggle', function (e) {
  var cur = e.detail && e.detail.current;
  if (cur === 'video') { videoToolbarVisible = true; videoToolbarShows++; }
  else { videoToolbarVisible = false; }
});

// Every ora:pane-mode-toggle the shell produces, so plugin transitions can be
// compared against what video's own machinery emits.
var events = [];
document.addEventListener('ora:pane-mode-toggle', function (e) {
  // The shell always sends a detail; a stray CustomEvent of the same name need
  // not, and a recorder that threw on one would only obscure what happened.
  var d = e.detail || { previous: null, current: null };
  events.push({ previous: d.previous, current: d.current });
});

// ── two ordinary modules whose script tags precede the seam ─────────────────
//
// Both are registered here, BEFORE the module under test, because that is the
// only way to be ahead of the registry's own listener — and both behaviours
// below are things a module ahead of it can really do.

// One that re-enters the shell during an announcement, the way any listener
// that reacts to a pane-mode change by choosing a different one would. Armed
// one transition at a time.
var reenter = { armed: false, target: null };
document.addEventListener('ora:pane-mode-toggle', function () {
  if (!reenter.armed) return;
  reenter.armed = false;
  setPaneMode(reenter.target);
});

// One that stops an announcement reaching the listeners after it —
// v3-canvas-mount.js:390 does exactly this for its own events. This is the one
// way the shell can move without the registry hearing, which is the state
// release()'s stale-record guard exists for.
var swallowNextToggle = false;
document.addEventListener('ora:pane-mode-toggle', function (e) {
  if (!swallowNextToggle) return;
  swallowNextToggle = false;
  e.stopImmediatePropagation();
});

function clickVideoButton() {
  document.getElementById('spineVideoMode')
    .dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
}

// ═══════════════════════════════════════════════════════════════════════════
// Reference transition: what video's own machinery produces. Everything the
// plugin seam does is compared against this rather than against hand-written
// expectations.
// ═══════════════════════════════════════════════════════════════════════════
events.length = 0;
clickVideoButton();
var VIDEO_ENTER = {
  classes: paneModeClasses().join(','),
  pressed: document.getElementById('spineVideoMode').getAttribute('aria-pressed'),
  event: JSON.stringify(events[events.length - 1])
};
clickVideoButton();
var VIDEO_EXIT = {
  classes: paneModeClasses().join(','),
  pressed: document.getElementById('spineVideoMode').getAttribute('aria-pressed'),
  event: JSON.stringify(events[events.length - 1])
};
videoToolbarShows = 0;
videoToolbarVisible = false;

require(MODULE_PATH);
var P = w.OraPanes;

// ---- shape ----------------------------------------------------------------

record('OraPanes is exposed with exactly one pane, named for what it means',
  !!P && P.panes().join(',') === 'exhibits',
  P ? P.panes().join(',') : 'absent');

// ---- happy path: register → take ------------------------------------------

var demo = {
  pane: 'exhibits',
  mode: 'demo',
  label: 'Demo workspace',
  takes: 0,
  releases: 0,
  takeCtx: null,
  releaseCtx: null,
  onTake: function (ctx) { this.takes++; this.takeCtx = ctx; },
  onRelease: function (ctx) { this.releases++; this.releaseCtx = ctx; }
};
var demoHandle = P.register(demo);

record('register accepts a well-formed entry and get() hands back the entry itself',
  P.has('demo') && P.get('demo') === demo && P.list('exhibits').length === 1);

events.length = 0;
var took = P.take('demo');

record('take() returns true and the shell owns the body class',
  took === true && paneModeClasses().join(',') === 'pane-mode-demo',
  paneModeClasses().join(','));

record('the class the plugin gets is shaped like the one video gets',
  paneModeClasses().length === 1
    && VIDEO_ENTER.classes === 'pane-mode-video'
    && paneModeClasses()[0] === 'pane-mode-demo',
  'video=' + VIDEO_ENTER.classes + ' plugin=' + paneModeClasses().join(','));

record('the event the plugin causes is shaped like the one video causes',
  events.length === 1
    && JSON.stringify(events[0]) === '{"previous":null,"current":"demo"}'
    && VIDEO_ENTER.event === '{"previous":null,"current":"video"}',
  'video=' + VIDEO_ENTER.event + ' plugin=' + JSON.stringify(events[0]));

record('the shell syncs the video button off, as it does for any other mode',
  document.getElementById('spineVideoMode').getAttribute('aria-pressed') === 'false'
    && VIDEO_ENTER.pressed === 'true');

record('onTake ran exactly once, told which pane it got, and that it asked for it',
  demo.takes === 1 && demo.takeCtx && demo.takeCtx.pane === 'exhibits'
    && demo.takeCtx.mode === 'demo' && demo.takeCtx.requested === true,
  'takes=' + demo.takes);

record('owner() reports the mode now holding the pane',
  P.owner('exhibits') === 'demo', String(P.owner('exhibits')));

events.length = 0;
record('take() again while already holding is a no-op, not a second transition',
  P.take('demo') === true && demo.takes === 1 && events.length === 0,
  'takes=' + demo.takes + ' events=' + events.length);

// ---- clean release ---------------------------------------------------------

events.length = 0;
var released = P.release();

record('release() returns true, onRelease runs once, and the class is gone',
  released === true && demo.releases === 1 && paneModeClasses().length === 0,
  'releases=' + demo.releases + ' classes=' + paneModeClasses().join(','));

record('a release the owner asked for is reported as requested',
  !!demo.releaseCtx && demo.releaseCtx.requested === true
    && demo.releaseCtx.mode === 'demo' && demo.releaseCtx.current === null);

record('the exit event matches what video\'s own exit produces',
  events.length === 1
    && JSON.stringify(events[0]) === '{"previous":"demo","current":null}'
    && VIDEO_EXIT.event === '{"previous":"video","current":null}',
  'video=' + VIDEO_EXIT.event + ' plugin=' + JSON.stringify(events[0]));

record('owner() reports nobody once the pane is given back',
  P.owner('exhibits') === null);

// ---- the release nobody asked for ------------------------------------------
//
// Two real paths in today's shell move the pane out from under an owner: the
// user clicks the video button while a plugin mode is up (index-v3.html:1834),
// and another module calls window.OraPaneMode.set(null) directly — which
// slash-command-client.js:219-220 does.

P.take('demo');
demo.releases = 0;
demo.releaseCtx = null;
clickVideoButton();

record('the user switching to video releases the plugin exactly once',
  demo.releases === 1 && P.owner('exhibits') === null
    && currentPaneMode() === 'video',
  'releases=' + demo.releases + ' current=' + currentPaneMode());

record('an exit the owner did not ask for is reported as unrequested',
  !!demo.releaseCtx && demo.releaseCtx.requested === false
    && demo.releaseCtx.previous === 'demo' && demo.releaseCtx.current === 'video');

clickVideoButton();   // back to no mode

P.take('demo');
demo.releases = 0;
w.OraPaneMode.set(null);   // another module exits the mode, as the slash client does

record('another module exiting the mode releases the plugin exactly once',
  demo.releases === 1 && P.owner('exhibits') === null && currentPaneMode() === null,
  'releases=' + demo.releases);

// ---- amendment 3: the event handler cannot write back ----------------------
//
// The registry's only route to the shell is window.OraPaneMode.set, so a
// counting wrapper on that property counts every write the registry could
// possibly make. The shell's own internal transitions close over setPaneMode
// directly and correctly bypass the wrapper.

var setCalls = 0;
var realSet = w.OraPaneMode.set;
w.OraPaneMode.set = function (mode) { setCalls++; return realSet(mode); };

// Both directions of the ping-pong, and both are calls that WOULD reach the
// shell if the interlock were not there: answering an enter with an exit
// (inside onTake the mode is current, so release() is a live request), and
// answering an exit with an enter (inside onRelease no mode is current, so
// take() is a live request). Either one reaching OraPaneMode.set would
// announce again and re-enter this same callback.
var loopy = {
  pane: 'exhibits',
  mode: 'loopy',
  takes: 0,
  releases: 0,
  onTake: function () { this.takes++; P.release('loopy'); },
  onRelease: function () { this.releases++; P.take('loopy'); }
};
var loopyHandle = P.register(loopy);

setCalls = 0;
warnings.length = 0;
P.take('loopy');

record('an onTake that answers with release() makes no second write',
  setCalls === 1 && loopy.takes === 1 && currentPaneMode() === 'loopy',
  'setCalls=' + setCalls + ' takes=' + loopy.takes);

record('the re-entrant write is refused loudly, not silently swallowed',
  warned(/inside an ora:pane-mode-toggle handler/));

// The shell exits on its own, through realSet — so the counter below sees
// only writes the registry itself could have made.
setCalls = 0;
warnings.length = 0;
realSet(null);

record('the event handler never calls OraPaneMode.set, however hard the owner tries',
  setCalls === 0, 'setCalls=' + setCalls);

record('an onRelease that answers with take() cannot loop: it runs exactly once',
  loopy.releases === 1 && P.owner('exhibits') === null && currentPaneMode() === null,
  'releases=' + loopy.releases + ' current=' + currentPaneMode());

record('the refusal is warned from the forced-exit path too',
  warned(/inside an ora:pane-mode-toggle handler/));

loopyHandle();
w.OraPaneMode.set = realSet;

// ---- removal ---------------------------------------------------------------

var temp = {
  pane: 'exhibits', mode: 'temp', releases: 0,
  onRelease: function () { this.releases++; }
};
var tempHandle = P.register(temp);
P.take('temp');
var removed = tempHandle();

record('unregistering while holding the pane releases it first, then forgets it',
  removed === true && temp.releases === 1 && paneModeClasses().length === 0
    && P.owner('exhibits') === null && P.has('temp') === false,
  'removed=' + removed + ' releases=' + temp.releases
    + ' classes=' + paneModeClasses().join(','));

record('the handle is spent: calling it twice removes nothing',
  tempHandle() === false);

var successor = { pane: 'exhibits', mode: 'temp' };
P.register(successor);
record('a stale handle cannot evict a later owner registered under the same mode',
  tempHandle() === false && P.get('temp') === successor);
P.register({ pane: 'exhibits', mode: 'temp' });   // rejected below; keeps successor
record('the successor survives its predecessor\'s handle', P.get('temp') === successor);

// ---- fail-open paths -------------------------------------------------------

warnings.length = 0;
P.register({ pane: 'inquiry', mode: 'wrong-pane' });
record('an unknown pane is rejected with a warning',
  !P.has('wrong-pane') && warned(/unknown pane "inquiry"/));

warnings.length = 0;
P.register({ pane: '__proto__', mode: 'proto-pane' });
P.register({ pane: 'constructor', mode: 'ctor-pane' });
record('a __proto__ / constructor pane name is unknown, not an inherited member',
  !P.has('proto-pane') && !P.has('ctor-pane')
    && warned(/unknown pane "__proto__"/) && warned(/unknown pane "constructor"/));

warnings.length = 0;
P.register({ pane: 'exhibits', mode: 'temp' });
record('a duplicate mode is rejected with a warning',
  warned(/mode "temp" is already registered/) && P.get('temp') === successor);

warnings.length = 0;
P.take('temp');
var intruder = { pane: 'exhibits', mode: 'intruder' };
P.register(intruder);
record('a second owner for a pane someone is holding is refused; the incumbent keeps it',
  !P.has('intruder') && P.owner('exhibits') === 'temp'
    && warned(/is currently held by pane mode "temp"/));
P.release('temp');

warnings.length = 0;
record('a missing entry is rejected and hands back a no-op handle',
  P.register(null)() === false && P.register('exhibits')() === false
    && warned(/entry must be an object/));

warnings.length = 0;
P.register({ mode: 'no-pane' });
P.register({ pane: 'exhibits' });
record('a missing pane or mode is rejected with a warning',
  !P.has('no-pane') && warned(/entry\.pane is required/) && warned(/entry\.mode is required/));

warnings.length = 0;
P.register({ pane: 'exhibits', mode: 'two words' });
record('a mode that would break classList.add is refused before it reaches the shell',
  !P.has('two words') && warned(/not a valid class token/));

warnings.length = 0;
P.register({ pane: 'exhibits', mode: 'bad-cb', onTake: 'nope' });
record('a non-function callback is rejected with a warning',
  !P.has('bad-cb') && warned(/entry\.onTake must be a function/));

warnings.length = 0;
P.register({
  pane: 'exhibits',
  get mode() { throw new Error('hostile getter'); }
});
record('an entry whose getter throws is rejected, and the throw never escapes',
  warned(/reading entry fields threw: hostile getter/));

warnings.length = 0;
record('take() on an unregistered mode is refused with a warning',
  P.take('never-registered') === false
    && warned(/no plugin is registered for that pane mode/));

warnings.length = 0;
record('release() with nothing held is refused with a warning',
  P.release() === false && warned(/no registered pane mode is currently held/));

// window.OraPaneMode absent — the shell may not have booted, or may be gone.
warnings.length = 0;
var savedShell = w.OraPaneMode;
delete w.OraPaneMode;
var tookWithoutShell = P.take('temp');
var classesWithoutShell = paneModeClasses().length;
w.OraPaneMode = savedShell;
record('with window.OraPaneMode absent, take() fails open and sets no class itself',
  tookWithoutShell === false && classesWithoutShell === 0
    && warned(/window\.OraPaneMode is not available/),
  'took=' + tookWithoutShell + ' classes=' + classesWithoutShell);

warnings.length = 0;
w.OraPaneMode = { current: function () { return null; } };   // no .set
var tookHalfShell = P.take('temp');
w.OraPaneMode = savedShell;
record('a half-built OraPaneMode counts as absent',
  tookHalfShell === false && warned(/window\.OraPaneMode is not available/));

// A shell setter that throws.
warnings.length = 0;
w.OraPaneMode = {
  current: currentPaneMode,
  set: function () { throw new Error('shell exploded'); }
};
var tookThrowingShell = P.take('temp');
w.OraPaneMode = savedShell;
record('a throwing OraPaneMode.set is contained and warned',
  tookThrowingShell === false && paneModeClasses().length === 0
    && warned(/OraPaneMode\.set\("temp"\) threw: shell exploded/));

warnings.length = 0;
w.OraPaneMode = {
  current: function () { throw new Error('current exploded'); },
  set: setPaneMode
};
var tookBlindShell = P.take('temp');
w.OraPaneMode = savedShell;
record('a throwing OraPaneMode.current is contained; the registry does not guess',
  tookBlindShell === false && paneModeClasses().length === 0
    && warned(/OraPaneMode\.current\(\) threw: current exploded/));

// Callbacks that throw.
warnings.length = 0;
var thrower = {
  pane: 'exhibits',
  mode: 'thrower',
  label: 'Throwing plugin',
  onTake: function () { throw new Error('take bug'); },
  onRelease: function () { throw new Error('release bug'); }
};
P.register(thrower);
var tookThrower = P.take('thrower');
record('an onTake that throws is contained, and ownership still reflects the shell',
  tookThrower === true && P.owner('exhibits') === 'thrower'
    && currentPaneMode() === 'thrower'
    && warned(/pane mode "thrower" \(Throwing plugin\): onTake threw: take bug/));

warnings.length = 0;
var releasedThrower = P.release('thrower');
record('an onRelease that throws is contained, and the pane is still given back',
  releasedThrower === true && P.owner('exhibits') === null
    && paneModeClasses().length === 0
    && warned(/onRelease threw: release bug/));

// A label getter that throws must not break the warning path itself.
warnings.length = 0;
var hostileLabel = {
  pane: 'exhibits',
  mode: 'hostile-label',
  get label() { throw new Error('label bug'); },
  onTake: function () { throw new Error('take bug'); }
};
P.register(hostileLabel);
P.take('hostile-label');
record('a label getter that throws does not escape while logging a callback fault',
  warned(/pane mode "hostile-label": onTake threw: take bug/)
    && P.owner('exhibits') === 'hostile-label');
P.release('hostile-label');

// A callback that returns a rejected promise.
warnings.length = 0;
var asyncBad = {
  pane: 'exhibits',
  mode: 'async-bad',
  onTake: function () { return Promise.reject(new Error('async take bug')); },
  onRelease: function () { return Promise.reject(new Error('async release bug')); }
};
P.register(asyncBad);
P.take('async-bad');
P.release('async-bad');

// A thenable whose .then throws outright.
warnings.length = 0;
var brokenThenable = {
  pane: 'exhibits',
  mode: 'broken-thenable',
  onTake: function () {
    return { then: function () { throw new Error('thenable bug'); } };
  }
};
P.register(brokenThenable);
var tookBrokenThenable = P.take('broken-thenable');
record('a callback returning a broken thenable is contained',
  tookBrokenThenable === true
    && warned(/returned a broken thenable: thenable bug/));
P.release('broken-thenable');

// A mode name that is an Object.prototype member, end to end.
warnings.length = 0;
var protoMode = {
  pane: 'exhibits', mode: '__proto__', takes: 0, releases: 0,
  onTake: function () { this.takes++; },
  onRelease: function () { this.releases++; }
};
P.register(protoMode);
var tookProto = P.take('__proto__');
record('a __proto__ mode name works end to end rather than corrupting the registry',
  tookProto === true && P.has('__proto__') && P.get('__proto__') === protoMode
    && protoMode.takes === 1 && P.owner('exhibits') === '__proto__'
    && paneModeClasses().join(',') === 'pane-mode-__proto__',
  paneModeClasses().join(','));
record('and releases cleanly',
  P.release() === true && protoMode.releases === 1
    && P.owner('exhibits') === null && paneModeClasses().length === 0);
record('an unregistered Object.prototype member is not a registered mode',
  P.has('constructor') === false && P.has('hasOwnProperty') === false
    && P.get('toString') === null);

warnings.length = 0;
record('owner() on an unknown pane warns rather than answering null quietly',
  P.owner('exihbits') === null && warned(/owner\("exihbits"\).*unknown pane/));

// ---- video is unaffected ---------------------------------------------------

var showsBefore = videoToolbarShows;
warnings.length = 0;

// The shell drives a video session on its own, exactly as the user would.
clickVideoButton();
record('the shell can still drive a video session with the registry loaded',
  currentPaneMode() === 'video' && videoToolbarVisible === true
    && document.getElementById('spineVideoMode').getAttribute('aria-pressed') === 'true'
    && videoToolbarShows === showsBefore + 1);

warnings.length = 0;
var tookDuringVideo = P.take('demo');
record('a plugin cannot displace a live video session',
  tookDuringVideo === false && currentPaneMode() === 'video'
    && videoToolbarVisible === true && P.owner('exhibits') === null
    && warned(/pane mode "video" is already active/));

warnings.length = 0;
var releasedVideo = P.release('video');
record('a plugin cannot use the registry to exit video: video is not registered',
  releasedVideo === false && currentPaneMode() === 'video'
    && videoToolbarVisible === true
    && warned(/this registry only releases modes it owns/));

clickVideoButton();   // the user leaves video
record('the video toolbar hides when the user leaves, as it always did',
  videoToolbarVisible === false && currentPaneMode() === null);

// A whole plugin session must never show video's toolbar.
showsBefore = videoToolbarShows;
P.take('demo');
var toolbarDuringPlugin = videoToolbarVisible;
var pressedDuringPlugin = document.getElementById('spineVideoMode').getAttribute('aria-pressed');
P.release('demo');
record('taking and releasing a plugin mode never shows video\'s toolbar',
  toolbarDuringPlugin === false && videoToolbarVisible === false
    && videoToolbarShows === showsBefore && pressedDuringPlugin === 'false',
  'shows=' + videoToolbarShows + ' expected=' + showsBefore);

// The shell's implicit exits are literally video-specific (index-v3.html:1861,
// 1866). Pinning that here so the stand-in cannot quietly drift into the more
// convenient generalised version.
P.take('demo');
demo.releases = 0;
document.dispatchEvent(new w.CustomEvent('ora:new-thread-requested'));
record('the shell\'s new-thread exit is video-only, so a plugin mode survives it',
  currentPaneMode() === 'demo' && demo.releases === 0
    && P.owner('exhibits') === 'demo',
  'current=' + currentPaneMode() + ' releases=' + demo.releases);
P.release('demo');

clickVideoButton();
document.dispatchEvent(new w.CustomEvent('ora:new-thread-requested'));
record('and a video session still exits on new-thread exactly as before',
  currentPaneMode() === null && videoToolbarVisible === false);

// ---- the shell's own mode names are reserved -------------------------------
//
// The shell declares its pane modes in markup, one [data-pane-mode-button] per
// mode. The registry reads that markup instead of carrying a list of built-in
// names, so a plugin cannot register one — registering the built-in's name
// would hand the plugin the user's own session: onTake it never asked for,
// owner() reporting it, release() ending a live session under the user, take()
// switching the built-in on, and the pane held for the session's duration.

warnings.length = 0;
var hijack = {
  pane: 'exhibits', mode: 'video', takes: 0, releases: 0,
  onTake: function () { this.takes++; },
  onRelease: function () { this.releases++; }
};
var hijackHandle = P.register(hijack);
record('a mode name the shell claims in its own markup is refused',
  P.has('video') === false && hijackHandle() === false
    && warned(/\[data-pane-mode-button="video"\]/),
  'has=' + P.has('video'));

showsBefore = videoToolbarShows;
warnings.length = 0;
clickVideoButton();
record('the user\'s own video session reaches no plugin and no ownership record',
  hijack.takes === 0 && P.owner('exhibits') === null
    && currentPaneMode() === 'video' && videoToolbarVisible === true
    && videoToolbarShows === showsBefore + 1
    && document.getElementById('spineVideoMode').getAttribute('aria-pressed') === 'true',
  'takes=' + hijack.takes + ' owner=' + P.owner('exhibits'));

var coexist = { pane: 'exhibits', mode: 'coexist' };
var coexistHandle = P.register(coexist);
record('a built-in holding the pane does not block other plugins from registering',
  P.has('coexist') === true && P.owner('exhibits') === null);
coexistHandle();

record('and nothing in the registry can end the user\'s live session',
  P.release('video') === false && P.take('video') === false
    && currentPaneMode() === 'video' && videoToolbarVisible === true
    && document.getElementById('spineVideoMode').getAttribute('aria-pressed') === 'true'
    && hijack.releases === 0);
clickVideoButton();   // the user leaves, as always

// The shell may not have rendered when a plugin registers — script order. A
// reservation that is not in the DOM yet cannot be read, and refusing every
// registration on that account would strand plugins over a collision that
// probably is not there. So registration fails open, and the check runs again
// at the two points that imply a live shell.
warnings.length = 0;
var videoBtn = document.getElementById('spineVideoMode');
var toolbarHost = videoBtn.parentNode;
toolbarHost.removeChild(videoBtn);                    // the shell has not rendered
var early = {
  pane: 'exhibits', mode: 'video', takes: 0, releases: 0,
  onTake: function () { this.takes++; },
  onRelease: function () { this.releases++; }
};
var earlyHandle = P.register(early);
var acceptedEarly = P.has('video');
toolbarHost.appendChild(videoBtn);                    // the shell renders
record('with no shell markup to read, registration fails open rather than stranding it',
  acceptedEarly === true && warnings.length === 0,
  'accepted=' + acceptedEarly + ' warnings=' + warnings.length);

warnings.length = 0;
record('the reserved name is refused at take(), where a live shell exists',
  P.take('video') === false && currentPaneMode() === null
    && warned(/the shell claims that pane mode in its own markup/));

showsBefore = videoToolbarShows;
warnings.length = 0;
clickVideoButton();
record('and a record that predates the markup is never handed the shell\'s session',
  early.takes === 0 && P.owner('exhibits') === null
    && currentPaneMode() === 'video' && videoToolbarVisible === true
    && videoToolbarShows === showsBefore + 1
    && warned(/registered under that name/),
  'takes=' + early.takes + ' owner=' + P.owner('exhibits'));

clickVideoButton();
record('nor its onRelease when the user leaves',
  early.releases === 0 && currentPaneMode() === null && videoToolbarVisible === false);
record('and the inert record can still be unregistered',
  earlyHandle() === true && P.has('video') === false);

// ---- the announcement is reconciled against the shell ----------------------
//
// What the event says and what the body class is can differ: an earlier
// listener re-enters the shell mid-dispatch, an owner hands the pane back from
// inside its own onTake, or an ora:pane-mode-toggle arrives from somewhere
// else entirely. Ownership follows the body class.

var handback = {
  pane: 'exhibits', mode: 'handback', takes: 0, releases: 0, releaseCtx: null,
  // window.OraPaneMode.set is the handle this module's own header points at,
  // and the one an author is pushed toward, because release() from inside the
  // event is refused.
  onTake: function () { this.takes++; if (this.takes === 1) w.OraPaneMode.set(null); },
  onRelease: function (ctx) { this.releases++; this.releaseCtx = ctx; }
};
var handbackHandle = P.register(handback);
P.take('handback');
record('an owner that hands the pane back from inside onTake still gets its onRelease',
  handback.releases === 1 && P.owner('exhibits') === null && currentPaneMode() === null,
  'releases=' + handback.releases + ' owner=' + P.owner('exhibits'));
record('a hand-back through the shell is not reported as a transition the registry asked for',
  !!handback.releaseCtx && handback.releaseCtx.requested === false
    && handback.releaseCtx.mode === 'handback' && handback.releaseCtx.current === null);
var afterHandback = { pane: 'exhibits', mode: 'after-handback' };
var afterHandle = P.register(afterHandback);
record('and the pane is not left held against every later plugin',
  P.has('after-handback') === true && P.owner('exhibits') === null);
afterHandle();
handbackHandle();

var ghost = {
  pane: 'exhibits', mode: 'ghost', takes: 0, releases: 0,
  onTake: function () { this.takes++; },
  onRelease: function () { this.releases++; }
};
var ghostHandle = P.register(ghost);
reenter.target = null;
reenter.armed = true;
P.take('ghost');
record('a module re-entering the shell mid-announcement cannot hand a plugin a mode the shell is not in',
  ghost.takes === 0 && P.owner('exhibits') === null && currentPaneMode() === null,
  'takes=' + ghost.takes + ' owner=' + P.owner('exhibits')
    + ' classes=' + paneModeClasses().join(','));

var substitute = {
  pane: 'exhibits', mode: 'substitute', takes: 0, takeCtx: null, releases: 0,
  onTake: function (ctx) { this.takes++; this.takeCtx = ctx; },
  onRelease: function () { this.releases++; }
};
var substituteHandle = P.register(substitute);
reenter.target = 'substitute';
reenter.armed = true;
P.take('ghost');
record('a plugin handed a mode the registry never asked for is told it was not requested',
  substitute.takes === 1 && !!substitute.takeCtx && substitute.takeCtx.requested === false
    && P.owner('exhibits') === 'substitute' && currentPaneMode() === 'substitute'
    && ghost.takes === 0,
  'requested=' + (substitute.takeCtx && substitute.takeCtx.requested)
    + ' owner=' + P.owner('exhibits'));
P.release('substitute');
substituteHandle();
ghostHandle();

var pinned = {
  pane: 'exhibits', mode: 'pinned', takes: 0, releases: 0,
  onTake: function () { this.takes++; },
  onRelease: function () { this.releases++; }
};
var pinnedHandle = P.register(pinned);
P.take('pinned');
warnings.length = 0;
document.dispatchEvent(new w.CustomEvent('ora:pane-mode-toggle'));
document.dispatchEvent(new w.CustomEvent('ora:pane-mode-toggle', {
  detail: { previous: 'pinned', current: null }
}));
record('a toggle event that does not describe the body class cannot evict the owner',
  pinned.releases === 0 && P.owner('exhibits') === 'pinned'
    && currentPaneMode() === 'pinned',
  'releases=' + pinned.releases + ' owner=' + P.owner('exhibits'));
record('and the owner can still hand the pane back afterwards',
  P.release('pinned') === true && pinned.releases === 1
    && paneModeClasses().length === 0 && P.owner('exhibits') === null);
pinnedHandle();

// ---- the guards, each pinned by the failure it prevents ---------------------

// release()'s stale-record check. A record goes stale without the registry
// doing anything wrong: any listener may stop an announcement reaching the
// ones after it, and the registry's is not the first on the document. What it
// must not do with a stale record is ask the shell to leave whatever is there.
var stale = {
  pane: 'exhibits', mode: 'stale', takes: 0, releases: 0,
  onTake: function () { this.takes++; },
  onRelease: function () { this.releases++; }
};
var staleHandle = P.register(stale);
P.take('stale');
swallowNextToggle = true;            // the registry will not hear the next one
showsBefore = videoToolbarShows;
clickVideoButton();                  // a real video session: class, button, toolbar
record('a swallowed announcement leaves the registry holding a record the shell has left',
  P.owner('exhibits') === 'stale' && currentPaneMode() === 'video'
    && videoToolbarVisible === true && videoToolbarShows === showsBefore + 1,
  'owner=' + P.owner('exhibits') + ' current=' + currentPaneMode());

warnings.length = 0;
var releasedStale = P.release();
record('release() on a stale record drops the record instead of ending the live video session',
  releasedStale === false && currentPaneMode() === 'video'
    && videoToolbarVisible === true
    && document.getElementById('spineVideoMode').getAttribute('aria-pressed') === 'true'
    && P.owner('exhibits') === null && stale.releases === 1
    && warned(/dropping the stale ownership record/),
  'returned=' + releasedStale + ' current=' + currentPaneMode()
    + ' toolbar=' + videoToolbarVisible + ' releases=' + stale.releases);
clickVideoButton();                  // the user leaves video
staleHandle();

// _dropHolder clears ownership BEFORE onRelease. Cleared after, the re-entrant
// release() below would find the record it is already leaving and release it a
// second time.
var reentrantRelease = {
  pane: 'exhibits', mode: 'reentrant-release', releases: 0, inner: null,
  onRelease: function () {
    this.releases++;
    if (this.releases === 1) this.inner = P.release();
  }
};
var reentrantHandle = P.register(reentrantRelease);
P.take('reentrant-release');
warnings.length = 0;
w.OraPaneMode.set(null);             // the shell exits on its own
record('onRelease runs exactly once even when it calls release() again',
  reentrantRelease.releases === 1 && reentrantRelease.inner === false
    && P.owner('exhibits') === null
    && warned(/no registered pane mode is currently held/),
  'releases=' + reentrantRelease.releases + ' inner=' + reentrantRelease.inner);
reentrantHandle();

// _remove re-reads the record's index after releasing. A callback above may
// have unregistered other records, and an index read before that would splice
// out whichever record had shifted into the slot.
var neighbourA = { pane: 'exhibits', mode: 'neighbour-a' };
var neighbourAHandle = P.register(neighbourA);
var shedder = {
  pane: 'exhibits', mode: 'shedder', releases: 0,
  onRelease: function () { this.releases++; neighbourAHandle(); }
};
var shedderHandle = P.register(shedder);
var neighbourB = { pane: 'exhibits', mode: 'neighbour-b' };
var neighbourBHandle = P.register(neighbourB);   // sits directly after shedder
P.take('shedder');
var shedderRemoved = shedderHandle();
record('unregistering a record whose onRelease unregisters another removes exactly those two',
  shedderRemoved === true && shedder.releases === 1
    && P.has('shedder') === false && P.has('neighbour-a') === false
    && P.has('neighbour-b') === true && P.get('neighbour-b') === neighbourB,
  'removed=' + shedderRemoved + ' shedder=' + P.has('shedder')
    + ' a=' + P.has('neighbour-a') + ' b=' + P.has('neighbour-b'));
neighbourBHandle();

// The no-write-back interlock counts announcements rather than flagging one.
// An announcement nested inside another — an owner handing the pane back from
// inside its own onTake — must not unlock write-back for the rest of the outer
// pass, which is what a boolean does when the inner pass finishes.
var nestedWriter = {
  pane: 'exhibits', mode: 'nested-writer', takes: 0, releases: 0, afterNested: null,
  onTake: function () {
    this.takes++;
    if (this.takes > 1) return;
    w.OraPaneMode.set(null);                       // a whole nested announcement
    this.afterNested = P.take('nested-writer');    // still inside the outer one
  },
  onRelease: function () { this.releases++; }
};
var nestedHandle = P.register(nestedWriter);
w.OraPaneMode.set = function (mode) { setCalls++; return realSet(mode); };
setCalls = 0;
warnings.length = 0;
P.take('nested-writer');
w.OraPaneMode.set = realSet;
record('a nested announcement does not unlock write-back for the rest of the outer one',
  nestedWriter.afterNested === false && nestedWriter.takes === 1
    && nestedWriter.releases === 1 && setCalls === 2
    && P.owner('exhibits') === null && currentPaneMode() === null
    && warned(/inside an ora:pane-mode-toggle handler/),
  'afterNested=' + nestedWriter.afterNested + ' setCalls=' + setCalls
    + ' takes=' + nestedWriter.takes + ' current=' + currentPaneMode());
nestedHandle();

// Two more shapes of the same attack, counted the same way.
w.OraPaneMode.set = function (mode) { setCalls++; return realSet(mode); };
var deep = {
  pane: 'exhibits', mode: 'deep', takes: 0,
  onTake: function () {
    this.takes++;
    (function l1() { (function l2() { (function l3() { P.release('deep'); })(); })(); })();
  }
};
var deepHandle = P.register(deep);
setCalls = 0;
warnings.length = 0;
P.take('deep');
record('a callback reaching the registry through its own helper chain still makes one write',
  setCalls === 1 && deep.takes === 1 && currentPaneMode() === 'deep'
    && warned(/inside an ora:pane-mode-toggle handler/),
  'setCalls=' + setCalls + ' current=' + currentPaneMode());
realSet(null);
deepHandle();

var pong = {
  pane: 'exhibits', mode: 'pong', takes: 0,
  onTake: function () { this.takes++; P.take('ping'); }
};
var ping = {
  pane: 'exhibits', mode: 'ping', takes: 0,
  onTake: function () { this.takes++; P.take('pong'); }
};
var pongHandle = P.register(pong);
var pingHandle = P.register(ping);
setCalls = 0;
warnings.length = 0;
P.take('ping');
record('two plugins answering each other make one write between them',
  setCalls === 1 && ping.takes === 1 && pong.takes === 0
    && currentPaneMode() === 'ping' && P.owner('exhibits') === 'ping',
  'setCalls=' + setCalls + ' ping=' + ping.takes + ' pong=' + pong.takes);
realSet(null);
w.OraPaneMode.set = realSet;
pingHandle();
pongHandle();

// ---- evaluated twice -------------------------------------------------------

var beforeSecondEval = P;
delete require.cache[require.resolve(MODULE_PATH)];
require(MODULE_PATH);

record('a second evaluation is a no-op: same registry object, same entries',
  w.OraPanes === beforeSecondEval && w.OraPanes.has('demo')
    && w.OraPanes.get('demo') === demo);

demo.takes = 0;
demo.releases = 0;
P.take('demo');
P.release('demo');
record('and no duplicate document listener: callbacks still run exactly once',
  demo.takes === 1 && demo.releases === 1,
  'takes=' + demo.takes + ' releases=' + demo.releases);

demoHandle();

// ---- async tail ------------------------------------------------------------
//
// The rejected-callback assertions have to wait for a microtask turn.

setTimeout(function () {
  record('a callback that returns a rejected promise warns instead of escaping',
    warnings.some(function (m) { return /onTake rejected: async take bug/.test(m); })
      && warnings.some(function (m) { return /onRelease rejected: async release bug/.test(m); }));

  record('no unhandled rejection reaches the page',
    unhandled.length === 0, unhandled.join(' | '));

  summarize();
}, 30);
