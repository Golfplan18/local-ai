#!/usr/bin/env node
/* Focused jsdom tests for the plugin button mount points.
 *
 * Run:
 *   node ~/ora/server/static/tests/test-v3-mount-points.js
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

// The four real containers, matching index-v3.html's structure.
var dom = new jsdom.JSDOM(
  '<!doctype html><html><body>'
  + '<div class="input-pane-toolbar bridge-toolbar bridge-toolbar--left">'
  +   '<button class="input-pane-toolbar__btn" id="coreAttach"></button>'
  + '</div>'
  + '<div class="spine-bottom"><button class="spine-button" id="coreSettings"></button></div>'
  + '<div class="input-pane-toolbar bridge-toolbar bridge-toolbar--right">'
  +   '<button class="input-pane-toolbar__btn" id="coreImport"></button>'
  + '</div>'
  + '<div class="sidebar-collapsed-dashboard">'
  +   '<button class="sidebar-dash-icon" id="coreExpand"></button>'
  + '</div>'
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

require(path.resolve(__dirname, '..', 'js', 'v3-mount-points.js'));

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

var M = w.OraMounts;
var SVG = '<svg viewBox="0 0 24 24"><path d="M4 4h16v16H4z"/></svg>';

// jsdom is still in readyState 'loading' when this file runs, so the module is
// correctly queueing rather than mounting. Flush the queue explicitly — the
// same thing DOMContentLoaded does in the browser.
var queuedBeforeFlush = M.register(entryProbe());
M._flush();
record('registrations made before the DOM is ready are flushed, not dropped',
  !!w.document.querySelector('[data-ora-mount="probe"]'));
queuedBeforeFlush();

function entryProbe() {
  return {
    position: 'spine', id: 'probe', label: 'Probe', icon: SVG,
    onSelect: function () {}
  };
}

function entry(over) {
  return Object.assign({
    position: 'exhibits',
    id: 'test-btn',
    label: 'Test Button',
    icon: SVG,
    onSelect: function () {}
  }, over || {});
}

record('OraMounts is exposed with four positions',
  !!M && M.positions().join(',') === 'inquiry,exhibits,spine,sidebar',
  M ? M.positions().join(',') : 'absent');

// ---- mounting into each real container ------------------------------------

var clicked = 0;
M.register(entry({ id: 'vid', label: 'Video editing', onSelect: function () { clicked++; } }));

var mounted = w.document.querySelector('[data-ora-mount="vid"]');
record('button mounts into the exhibits container',
  !!mounted && mounted.parentNode.className.indexOf('bridge-toolbar--right') >= 0);

record('button appends AFTER the core button, not before',
  !!mounted && mounted.previousElementSibling
    && mounted.previousElementSibling.id === 'coreImport');

record('button uses the position\'s native class so it is styled like core',
  !!mounted && mounted.className === 'input-pane-toolbar__btn',
  mounted && mounted.className);

record('accessible name and tooltip are set from label',
  !!mounted && mounted.getAttribute('aria-label') === 'Video editing'
    && mounted.getAttribute('title') === 'Video editing');

record('inline SVG icon is rendered',
  !!mounted && mounted.innerHTML.indexOf('<svg') === 0);

mounted.dispatchEvent(new w.Event('click'));
record('click reaches the plugin handler', clicked === 1, 'clicked=' + clicked);

// ---- each position resolves to its own container ---------------------------

['inquiry', 'spine', 'sidebar'].forEach(function (pos) {
  M.register(entry({ id: 'p-' + pos, position: pos }));
});
var expectedClass = {
  inquiry: 'input-pane-toolbar__btn',
  spine: 'spine-button',
  sidebar: 'sidebar-dash-icon'
};
var allPlaced = ['inquiry', 'spine', 'sidebar'].every(function (pos) {
  var el = w.document.querySelector('[data-ora-mount="p-' + pos + '"]');
  return el && el.className === expectedClass[pos];
});
record('every position mounts into its own container with its own class', allPlaced);

// ---- toggle state ----------------------------------------------------------

record('setActive marks a toggle button pressed',
  M.setActive('vid', true) === true
    && w.document.querySelector('[data-ora-mount="vid"]').getAttribute('aria-pressed') === 'true');
record('setActive(false) clears it',
  M.setActive('vid', false) === true
    && !w.document.querySelector('[data-ora-mount="vid"]').hasAttribute('aria-pressed'));

// ---- removal ---------------------------------------------------------------

var unreg = M.register(entry({ id: 'temp' }));
record('register returns an unregister function that removes the button',
  unreg() === true && !w.document.querySelector('[data-ora-mount="temp"]'));

// ---- fail-open behaviour ---------------------------------------------------

warnings.length = 0;
M.register(entry({ id: 'bad-pos', position: 'nowhere' }));
record('unknown position warns and does not mount',
  !w.document.querySelector('[data-ora-mount="bad-pos"]')
    && warnings.some(function (m) { return /unknown position/.test(m); }));

warnings.length = 0;
M.register(entry({ id: 'vid' }));
record('duplicate id is rejected with a warning',
  warnings.some(function (m) { return /already registered/.test(m); })
    && w.document.querySelectorAll('[data-ora-mount="vid"]').length === 1);

warnings.length = 0;
M.register(entry({ id: 'no-handler', onSelect: null }));
record('missing handler is rejected rather than mounting a dead button',
  !w.document.querySelector('[data-ora-mount="no-handler"]')
    && warnings.some(function (m) { return /onSelect/.test(m); }));

warnings.length = 0;
M.register(entry({ id: 'thrower', onSelect: function () { throw new Error('plugin bug'); } }));
w.document.querySelector('[data-ora-mount="thrower"]').dispatchEvent(new w.Event('click'));
record('a throwing plugin handler is contained and warns',
  warnings.some(function (m) { return /threw: plugin bug/.test(m); }));

warnings.length = 0;
M.register(entry({ id: 'bad-icon', icon: 'not-a-real-lucide-name' }));
record('unresolvable icon still mounts a working button, with a warning',
  !!w.document.querySelector('[data-ora-mount="bad-icon"]')
    && warnings.some(function (m) { return /could not be resolved/.test(m); }));

// ---- core markup is never rewritten ---------------------------------------

record('core buttons are untouched',
  !!w.document.getElementById('coreImport')
    && !!w.document.getElementById('coreSettings')
    && !!w.document.getElementById('coreAttach')
    && !!w.document.getElementById('coreExpand'));

// Survivors on 'exhibits': vid, thrower, bad-icon. 'temp' was unregistered and
// bad-pos / duplicate-vid / no-handler were all rejected.
record('list() reports only the buttons that actually mounted',
  M.list('exhibits').length === 3
    && M.list('exhibits').map(function (e) { return e.id; }).sort().join(',')
       === 'bad-icon,thrower,vid',
  M.list('exhibits').map(function (e) { return e.id; }).join(','));

// ---- an unregister handle belongs to its own registration ------------------
// Two add-ons can pick the same id, and one of them can outlive its own button
// while still holding the handle it was given. That handle must never reach
// past its own registration into whatever now sits under the id.

var staleHandle = M.register(entry({ id: 'seat', label: 'Plugin A button' }));
staleHandle();
M.register(entry({ id: 'seat', label: 'Plugin B button' }));
var seatBefore = w.document.querySelector('[data-ora-mount="seat"]');
var staleReturn = staleHandle();
var seatAfter = w.document.querySelector('[data-ora-mount="seat"]');
record('a stale unregister handle leaves a later button with the same id alone',
  staleReturn === false && !!seatAfter && seatAfter === seatBefore
    && seatAfter.getAttribute('aria-label') === 'Plugin B button',
  'handle returned ' + staleReturn + '; Plugin B\'s button '
    + (seatAfter ? 'survived' : 'was unmounted'));

record('unregister(id) still removes whatever currently holds that id',
  M.unregister('seat') === true
    && !w.document.querySelector('[data-ora-mount="seat"]'));

// ---- inherited Object.prototype keys are not positions ---------------------
// A plain object literal answers to 'constructor', '__proto__' and friends, so
// a typo or a hostile value used to pass validation and be reported as a
// missing container — which is what a plugin author would then go and look for.

var protoFailures = [];
['constructor', '__proto__', 'hasOwnProperty', 'toString', 'valueOf'].forEach(function (key) {
  warnings.length = 0;
  M.register(entry({ id: 'proto-' + key, position: key }));
  var said = warnings.join(' | ');
  if (w.document.querySelector('[data-ora-mount="proto-' + key + '"]')) {
    protoFailures.push(key + ': mounted a button');
  }
  if (!/unknown position/.test(said)) {
    protoFailures.push(key + ': wrong diagnostic — ' + (said || 'no warning at all'));
  }
  if (said.indexOf('inquiry, exhibits, spine, sidebar') === -1) {
    protoFailures.push(key + ': warning does not list the four real positions');
  }
});
record('Object.prototype keys are rejected as unknown positions, with the right warning',
  protoFailures.length === 0, protoFailures.join('; '));

// ---- the same two guarantees on the pending queue --------------------------
// The queue is a second removal path, and _flush is a second caller of _build.
// Both need a module whose document is still loading, which this file's own
// window stopped being at the first _flush() above — so use a fresh window and
// a fresh copy of the module.

var pendingDom = new jsdom.JSDOM(
  '<!doctype html><html><body>'
  + '<div class="input-pane-toolbar bridge-toolbar bridge-toolbar--right"></div>'
  + '<div class="spine-bottom"></div>'
  + '</body></html>',
  { url: 'http://localhost/' }
);
var pw = pendingDom.window;
Object.defineProperty(pw.document, 'readyState', { value: 'loading', configurable: true });
var pendingWarnings = [];
pw.console = Object.assign({}, console, {
  warn: function (m) { pendingWarnings.push(String(m)); }
});
global.window = pw;
global.document = pw.document;
var MODULE = path.resolve(__dirname, '..', 'js', 'v3-mount-points.js');
delete require.cache[require.resolve(MODULE)];
require(MODULE);
var PM = pw.OraMounts;

function queued(over) {
  return Object.assign({
    position: 'exhibits', id: 'queued', label: 'Queued', icon: SVG,
    onSelect: function () {}
  }, over || {});
}

var staleQueuedHandle = PM.register(queued({ label: 'Queued A' }));
record('a registration made while the document is loading is queued, not mounted',
  !pw.document.querySelector('[data-ora-mount="queued"]'));
staleQueuedHandle();
PM.register(queued({ label: 'Queued B' }));

// A queued entry is a live plugin object: its position can change before the
// flush that builds it, which is the one way _build sees a position validate
// never saw.
var mutant = queued({ id: 'mutant', position: 'spine' });
PM.register(mutant);
mutant.position = 'constructor';

var stalePendingReturn = staleQueuedHandle();
pendingWarnings.length = 0;
PM._flush();

var queuedEl = pw.document.querySelector('[data-ora-mount="queued"]');
record('a stale handle does not evict a later queued entry with the same id',
  stalePendingReturn === false && !!queuedEl
    && queuedEl.getAttribute('aria-label') === 'Queued B',
  'handle returned ' + stalePendingReturn + '; flushed label '
    + (queuedEl ? queuedEl.getAttribute('aria-label') : 'nothing mounted'));

var mutantSaid = pendingWarnings.join(' | ');
record('a queued entry whose position became an Object.prototype key is reported as unknown',
  !pw.document.querySelector('[data-ora-mount="mutant"]')
    && /unknown position "constructor"/.test(mutantSaid)
    && !/no container/.test(mutantSaid),
  mutantSaid || 'no warning at all');

// Each remaining case needs its own still-loading document and its own copy of
// the module, because a module instance is one-way: the first flush sets
// _domReady and every later registration mounts immediately.
function freshLoadingModule(html) {
  var d = new jsdom.JSDOM(
    '<!doctype html><html><body>' + html + '</body></html>',
    { url: 'http://localhost/' }
  );
  var win = d.window;
  Object.defineProperty(win.document, 'readyState', { value: 'loading', configurable: true });
  var said = [];
  win.console = Object.assign({}, console, { warn: function (m) { said.push(String(m)); } });
  global.window = win;
  global.document = win.document;
  delete require.cache[require.resolve(MODULE)];
  require(MODULE);
  return { win: win, M: win.OraMounts, warnings: said };
}

function spineEntry(id) {
  return {
    position: 'spine', id: id, label: id, icon: SVG, onSelect: function () {}
  };
}

// ---- one id, named the same way by everything ------------------------------
// A queued entry is a live plugin object, so it can rename itself between
// register() and the flush that builds it. Whichever id wins, all three ways
// of naming the button must pick the SAME one: the key it is filed under, the
// data-ora-mount attribute it advertises to the DOM, and the id unregister()
// answers to. Any disagreement strands the button — mounted, visible, and
// impossible to remove by the only id anyone can read off it.

var renameEnv = freshLoadingModule('<div class="spine-bottom"></div>');
var renamer = spineEntry('panel');
renameEnv.M.register(renamer);
renamer.id = 'panel-v2';
renameEnv.M._flush();

var renamedEl = renameEnv.win.document.querySelector('[data-ora-mount]');
var advertised = renamedEl && renamedEl.getAttribute('data-ora-mount');
var keyedAsAdvertised = !!advertised && renameEnv.M.has(advertised) === true;
var removedByAdvertised = keyedAsAdvertised
  && renameEnv.M.unregister(advertised) === true;
var goneFromDom = removedByAdvertised
  && !renameEnv.win.document.querySelector('[data-ora-mount="' + advertised + '"]');
record('after a rename before the flush, the map key, data-ora-mount and unregister still name one id',
  !!advertised && keyedAsAdvertised && removedByAdvertised && goneFromDom,
  'button advertises ' + JSON.stringify(advertised) + '; has()=' + keyedAsAdvertised
    + '; unregister()=' + removedByAdvertised + '; left the DOM=' + goneFromDom);

var handleEnv = freshLoadingModule('<div class="spine-bottom"></div>');
var handleRenamer = spineEntry('panel');
var renamedHandle = handleEnv.M.register(handleRenamer);
handleRenamer.id = 'panel-v2';
handleEnv.M._flush();
var handleReturn = renamedHandle();
record('the handle register() returned still removes the button after a rename',
  handleReturn === true
    && !handleEnv.win.document.querySelector('[data-ora-mount]'),
  'handle returned ' + handleReturn + '; button '
    + (handleEnv.win.document.querySelector('[data-ora-mount]') ? 'survived' : 'removed'));

// ---- a position that cannot become a property key --------------------------
// POSITIONS[entry.position] coerces its key, so a Symbol or an object with no
// usable toString throws in the lookup itself — before any guard downstream of
// it can run. That throw escapes _build, escapes the flush loop, and escapes
// the DOMContentLoaded listener, with the queue already drained.

var hostileEnv = freshLoadingModule('<div class="spine-bottom"></div>');
var symBad = spineEntry('sym-bad');
var objBad = spineEntry('obj-bad');
[spineEntry('good-before'), symBad, spineEntry('good-middle'), objBad,
  spineEntry('good-after')].forEach(function (p) { hostileEnv.M.register(p); });
symBad.position = Symbol('spine');
objBad.position = { toString: null };

var hostileThrew = null;
try {
  hostileEnv.win.document.dispatchEvent(new hostileEnv.win.Event('DOMContentLoaded'));
} catch (err) { hostileThrew = (err && err.message) || String(err); }

var hostileSaid = hostileEnv.warnings.join(' | ');
var hostileMounted = [].slice.call(
  hostileEnv.win.document.querySelectorAll('[data-ora-mount]')
).map(function (el) { return el.getAttribute('data-ora-mount'); });
record('a position that cannot be coerced to a string is reported as unknown, not thrown',
  hostileThrew === null
    && hostileMounted.indexOf('sym-bad') === -1
    && hostileMounted.indexOf('obj-bad') === -1
    && (hostileSaid.match(/unknown position/g) || []).length === 2
    && /button "sym-bad" not mounted/.test(hostileSaid)
    && /button "obj-bad" not mounted/.test(hostileSaid),
  hostileThrew ? 'flush threw: ' + hostileThrew : (hostileSaid || 'no warning at all'));

record('one unmountable queued entry does not cost the plugins queued behind it',
  hostileMounted.join(',') === 'good-before,good-middle,good-after',
  'mounted: ' + (hostileMounted.join(',') || '(nothing)'));

// ---- containment is not specific to the position ---------------------------
// Everything _build reads off a queued entry is read late, so anything on it
// can be unusable by flush time. The label below throws where the DOM coerces
// it, well past the position guard. The entry behind it must still mount.

var lateEnv = freshLoadingModule('<div class="spine-bottom"></div>');
var badLabel = spineEntry('bad-label');
[spineEntry('before-bad'), badLabel, spineEntry('after-bad')]
  .forEach(function (p) { lateEnv.M.register(p); });
badLabel.label = { toString: null };
var lateThrew = null;
try {
  lateEnv.M._flush();
} catch (err) { lateThrew = (err && err.message) || String(err); }
var lateMounted = [].slice.call(
  lateEnv.win.document.querySelectorAll('[data-ora-mount]')
).map(function (el) { return el.getAttribute('data-ora-mount'); });
record('a queued entry that throws for any other reason is contained, warns, and the queue continues',
  lateThrew === null
    && lateMounted.join(',') === 'before-bad,after-bad'
    && /button "bad-label" could not be mounted/.test(lateEnv.warnings.join(' | ')),
  lateThrew ? 'flush threw: ' + lateThrew
    : 'mounted: ' + (lateMounted.join(',') || '(nothing)')
      + '; said: ' + (lateEnv.warnings.join(' | ') || 'nothing'));

// ---- a thrown value that refuses to become text ----------------------------
// Describing the thrown value is the last thing standing between one bad
// plugin and the whole queue, and it runs INSIDE _flush's catch — so if the
// description throws, the throw originates inside the catch, escapes it,
// escapes the flush loop, and escapes _flush, with _pending already drained
// and _domReady already true. Nothing retries the abandoned entries and
// nothing says so, because the DOM event dispatcher swallows a listener error.
//
// Two values refuse every ordinary description. The obvious fallback,
// Object.prototype.toString, READS Symbol.toStringTag off the value, so a
// throwing getter defeats it; and a revoked Proxy refuses that read — and
// every other operation — outright.

var UNDESCRIBABLE = [
  {
    what: 'an object with no toString or valueOf and a throwing Symbol.toStringTag',
    make: function () {
      var v = { toString: null, valueOf: null };
      Object.defineProperty(v, Symbol.toStringTag, {
        get: function () { throw new Error('toStringTag getter'); }
      });
      return v;
    }
  },
  {
    what: 'a revoked Proxy',
    make: function () {
      var revocable = Proxy.revocable({}, {});
      revocable.revoke();
      return revocable.proxy;
    }
  }
];

UNDESCRIBABLE.forEach(function (kind, i) {
  var env = freshLoadingModule('<div class="spine-bottom"></div>');
  var badId = 'undescribable-' + i;
  var bad = spineEntry(badId);
  [spineEntry('first-' + i), bad, spineEntry('third-' + i), spineEntry('fourth-' + i)]
    .forEach(function (p) { env.M.register(p); });
  // The plugin turns bad only after queueing. The label is read late, at
  // setAttribute, well past every guard _build applies.
  Object.defineProperty(bad, 'label', {
    get: function () { throw kind.make(); }
  });

  var escaped = null;
  try {
    env.M._flush();
  } catch (err) { escaped = 'flush threw: ' + _safely(err); }

  var stillMounted = [].slice.call(
    env.win.document.querySelectorAll('[data-ora-mount]')
  ).map(function (el) { return el.getAttribute('data-ora-mount'); });
  var said = env.warnings.join(' | ');

  record('a queued entry that throws ' + kind.what
    + ' costs its own button and nothing else',
    escaped === null
      && stillMounted.join(',') === ['first-' + i, 'third-' + i, 'fourth-' + i].join(',')
      && said.indexOf('button "' + badId + '" could not be mounted') >= 0,
    escaped || ('mounted: ' + (stillMounted.join(',') || '(nothing)')
      + '; said: ' + (said || 'nothing at all')));
});

// Describing the thrown value must not be how the test itself blows up.
function _safely(v) {
  try { return String(v); } catch (e) { return '(indescribable)'; }
}

global.window = w;
global.document = w.document;

// ---- the same value thrown by a click handler ------------------------------
// Same root cause, inside the click listener's own catch. The handler's error
// is read for a .message — a property read a revoked Proxy refuses — and then
// described. If either step throws, the throw leaves the listener uncaught,
// breaking "a plugin's handler must never break the shell", and no warning is
// emitted to say a handler failed at all.

UNDESCRIBABLE.forEach(function (kind, i) {
  warnings.length = 0;
  var id = 'hostile-thrower-' + i;
  M.register(entry({ id: id, onSelect: function () { throw kind.make(); } }));
  w.document.querySelector('[data-ora-mount="' + id + '"]')
    .dispatchEvent(new w.Event('click'));

  // The shell is still working: a button registered after the bad one still
  // mounts, and its handler still runs.
  var neighbourRan = 0;
  M.register(entry({
    id: id + '-neighbour', onSelect: function () { neighbourRan++; }
  }));
  var neighbour = w.document.querySelector('[data-ora-mount="' + id + '-neighbour"]');
  if (neighbour) neighbour.dispatchEvent(new w.Event('click'));

  record('a click handler that throws ' + kind.what + ' warns and the shell survives',
    warnings.some(function (m) {
      return m.indexOf('handler for "' + id + '" threw') >= 0;
    }) && neighbourRan === 1,
    'neighbour handler ran ' + neighbourRan + ' time(s); said: '
      + (warnings.join(' | ') || 'nothing at all'));
});

summarize();
