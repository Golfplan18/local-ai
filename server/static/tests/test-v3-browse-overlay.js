#!/usr/bin/env node
/* Focused jsdom tests for the plugin browse-overlay seam.
 *
 * Run:
 *   node ~/ora/server/static/tests/test-v3-browse-overlay.js
 *
 * The shipped stylesheet is loaded into the document, so "non-modal" and "the
 * pointer-events split survives" are checked against COMPUTED style and the
 * module's real rendered DOM — not against a regex over the CSS file, which a
 * module that turned itself into a full-viewport modal would pass untouched.
 */

'use strict';

var path = require('path');
var fs = require('fs');

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

var MODULE_PATH = path.resolve(__dirname, '..', 'js', 'v3-browse-overlay.js');
var CSS_PATH = path.resolve(__dirname, '..', 'styles', 'components', 'v3-spec-conform.css');
var css = fs.readFileSync(CSS_PATH, 'utf8');

// The real shell elements the dock geometry reads, in their real nesting.
var dom = new jsdom.JSDOM(
  '<!doctype html><html><head></head><body>'
  + '<button id="opener" type="button">Browse</button>'
  + '<input id="typing" type="text" />'
  + '<div class="ora-shell">'
  +   '<div class="left-column"><div class="pane input-pane"></div></div>'
  +   '<div class="right-column"></div>'
  + '</div>'
  + '</body></html>',
  { url: 'http://localhost/' }
);

var w = dom.window;
var doc = w.document;
global.window = w;
global.document = doc;

// The page under test ships this stylesheet. The TEST installs it so computed
// style is real; the MODULE is separately proved to install nothing.
var pageStyle = doc.createElement('style');
pageStyle.textContent = css;
doc.head.appendChild(pageStyle);

var warnings = [];      // cleared per test group
var allWarnings = [];   // never cleared; the async phase reads this
w.console = Object.assign({}, console, {
  warn: function (m) { warnings.push(String(m)); allWarnings.push(String(m)); }
});

// ---- instrumentation: real counts, not a flag the module sets ---------------
// Every listener the module attaches, of EVERY type, on BOTH window and
// document. Scoping this to window/'resize' would wave through a capturing
// document-level keydown that swallows Tab — a focus trap by another name, and
// the exact thing a non-modal surface must never install.

var liveWindow = [];        // { type, fn } still attached to window
var liveDocument = [];      // { type, fn } still attached to document
var everWindowTypes = [];   // every type ever attached to window
var everDocumentTypes = []; // every type ever attached to document

function census(target, live, everTypes) {
  var nativeAdd = target.addEventListener.bind(target);
  var nativeRemove = target.removeEventListener.bind(target);
  target.addEventListener = function (type, fn, opts) {
    live.push({ type: type, fn: fn });
    if (everTypes.indexOf(type) < 0) everTypes.push(type);
    return nativeAdd(type, fn, opts);
  };
  target.removeEventListener = function (type, fn, opts) {
    for (var i = 0; i < live.length; i++) {
      if (live[i].type === type && live[i].fn === fn) { live.splice(i, 1); break; }
    }
    return nativeRemove(type, fn, opts);
  };
}
census(w, liveWindow, everWindowTypes);
census(doc, liveDocument, everDocumentTypes);

function liveResize() {
  return liveWindow.filter(function (r) { return r.type === 'resize'; });
}
function typeList(live) {
  return live.map(function (r) { return r.type; }).sort().join(',') || '(none)';
}

var observers = [];    // every ResizeObserver the module has constructed
w.ResizeObserver = function (cb) {
  var self = this;
  self.callback = cb;
  self.observed = [];
  self.disconnected = false;
  self.observe = function (el) { self.observed.push(el); };
  self.unobserve = function (el) {
    var i = self.observed.indexOf(el);
    if (i >= 0) self.observed.splice(i, 1);
  };
  self.disconnect = function () { self.disconnected = true; self.observed = []; };
  observers.push(self);
};
function liveObservers() {
  return observers.filter(function (o) { return !o.disconnected; });
}

var unhandled = [];
process.on('unhandledRejection', function (reason) { unhandled.push(String(reason)); });

// ---- stubbed geometry -------------------------------------------------------

var RECTS = {
  '.ora-shell':    { top: 10,  bottom: 900, left: 5,   right: 1200 },
  '.left-column':  { top: 10,  bottom: 900, left: 40,  right: 700 },
  '.right-column': { top: 10,  bottom: 900, left: 700, right: 1160 },
  '.input-pane':   { top: 300, bottom: 800, left: 40,  right: 700 }
};
function applyRects() {
  Object.keys(RECTS).forEach(function (sel) {
    var el = doc.querySelector(sel);
    if (el) el.getBoundingClientRect = function () { return RECTS[sel]; };
  });
}
applyRects();
// pad = 8 → left 48, top max(18, 308) = 308, height 800-8-308 = 484,
//           right max(288, 1152) = 1152 → width 1152-48 = 1104.
var EXPECT = { left: '48px', top: '308px', width: '1104px', height: '484px' };

// Snapshot the document element BEFORE the module can touch it, so the
// non-modal proof compares against a real baseline rather than a guess.
var HTML_STYLE_BEFORE = doc.documentElement.style.cssText;
var HTML_CLASS_BEFORE = doc.documentElement.className;

require(MODULE_PATH);

// ---- harness ----------------------------------------------------------------

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

var API = w.OraBrowseOverlays;
var opener = doc.getElementById('opener');
var typing = doc.getElementById('typing');

// Never interpolate an id into a selector — read the attribute back instead.
function overlayNodes() {
  return Array.prototype.slice.call(doc.querySelectorAll('.conversation-browser-overlay'));
}
function nodeFor(id) {
  return overlayNodes().filter(function (n) {
    return n.getAttribute('data-ora-browse-overlay') === id;
  })[0] || null;
}
function openNodes() {
  return overlayNodes().filter(function (n) { return n.classList.contains('is-open'); });
}
function props(el) {
  return {
    left: el.style.getPropertyValue('--conversation-browser-left'),
    top: el.style.getPropertyValue('--conversation-browser-top'),
    width: el.style.getPropertyValue('--conversation-browser-width'),
    height: el.style.getPropertyValue('--conversation-browser-height')
  };
}
function inlineProps(el) {
  var out = [];
  for (var i = 0; i < el.style.length; i++) out.push(el.style.item(i));
  return out;
}
function computed(el, prop) {
  try { return w.getComputedStyle(el).getPropertyValue(prop); } catch (e) { return '(unavailable)'; }
}
function cssBlock(selector) {
  var i = css.indexOf(selector + ' {');
  if (i < 0) return '';
  return css.slice(i, css.indexOf('}', i));
}
function trackCount(template) {
  return String(template).replace(/minmax\([^)]*\)/g, 'minmax')
    .trim().split(/\s+/).filter(Boolean).length;
}
function warned(re) {
  return warnings.some(function (m) { return re.test(m); });
}
function noop() {}

// ---- module surface + double-evaluation guard -------------------------------

record('OraBrowseOverlays exposes the documented surface',
  !!API && ['register', 'open', 'close', 'isOpen', 'has', 'get', 'list']
    .every(function (k) { return typeof API[k] === 'function'; }));

var guardOff = API.register({ id: 'guard', label: 'Guard', render: noop });
delete require.cache[require.resolve(MODULE_PATH)];
require(MODULE_PATH);
record('evaluating the module twice keeps one registry rather than two copies',
  w.OraBrowseOverlays === API && API.has('guard'));
guardOff();

record('a null-prototype registry means no id is "already taken" by Object.prototype',
  API.has('constructor') === false && API.has('toString') === false
    && API.get('valueOf') === null);

// ---- happy path -------------------------------------------------------------

var painted = 0;
var openedCount = 0;
var closedCount = 0;
var lastCtx = null;

var filesOff = API.register({
  id: 'plugin-files',
  label: 'Plugin Files',
  render: function (body, ctx) {
    painted++;
    lastCtx = ctx;
    var row = doc.createElement('div');
    row.className = 'conversation-browser-row';
    row.textContent = 'draft-01.md';
    body.appendChild(row);
  },
  onOpen: function () { openedCount++; },
  onClose: function () { closedCount++; }
});

var bodyChildrenBefore = doc.body.children.length;
opener.focus();
var openResult = API.open('plugin-files');
var el = nodeFor('plugin-files');
var panel = el && el.querySelector('.conversation-browser-panel');
var header = el && el.querySelector('.conversation-browser-top');
var rows = el && el.querySelector('.conversation-browser-rows');

record('open() mounts the overlay and reports success',
  openResult === true && !!el && el.classList.contains('is-open'));

record('the overlay reuses the Library\'s class names so it is styled natively',
  !!panel && !!header && !!el.querySelector('.conversation-browser-close') && !!rows,
  el ? el.innerHTML.slice(0, 80) : 'absent');

record('the surface is a non-modal dialog, exactly as the Library declares it',
  el.getAttribute('role') === 'dialog' && el.getAttribute('aria-modal') === 'false',
  el.getAttribute('role') + '/' + el.getAttribute('aria-modal'));

record('label supplies both the accessible name and the visible title',
  el.getAttribute('aria-label') === 'Plugin Files'
    && el.querySelector('.conversation-browser-status').textContent === 'Plugin Files');

record('the plugin\'s rows are painted into the rows body',
  painted === 1 && rows.children.length === 1
    && rows.children[0].textContent === 'draft-01.md'
    && rows.children[0].className === 'conversation-browser-row');

record('the four dock custom properties are set from the shell rects',
  JSON.stringify(props(el)) === JSON.stringify(EXPECT),
  JSON.stringify(props(el)));

record('onOpen fired and isOpen reports the surface both ways',
  openedCount === 1 && API.isOpen('plugin-files') === true && API.isOpen() === true);

record('ctx carries the id, label, dialog root, rows body and a close function',
  !!lastCtx && lastCtx.id === 'plugin-files' && lastCtx.label === 'Plugin Files'
    && lastCtx.root === el && lastCtx.body === rows
    && typeof lastCtx.close === 'function');

// ---- non-modal proof: the module's real DOM, not a regex over the CSS -------

record('nothing anywhere in the document was made inert or aria-hidden',
  doc.querySelectorAll('[aria-hidden]').length === 0
    && doc.querySelectorAll('[inert]').length === 0);

record('the shell is left alone: one element added to body, no backdrop, no body class',
  doc.body.children.length === bodyChildrenBefore + 1
    && doc.body.className === ''
    && !doc.body.hasAttribute('style')
    && overlayNodes().length === 1,
  'body children ' + doc.body.children.length + ' vs ' + bodyChildrenBefore);

record('the document element is untouched — no scroll lock, no class, no inline style',
  doc.documentElement.style.cssText === HTML_STYLE_BEFORE
    && doc.documentElement.className === HTML_CLASS_BEFORE
    && doc.documentElement.style.getPropertyValue('overflow') === ''
    && !doc.documentElement.hasAttribute('aria-hidden')
    && !doc.documentElement.hasAttribute('inert'),
  'html style "' + doc.documentElement.style.cssText
    + '" class "' + doc.documentElement.className + '"');

record('the overlay root carries nothing inline but the four dock custom properties',
  inlineProps(el).length === 4
    && inlineProps(el).every(function (p) {
      return p.indexOf('--conversation-browser-') === 0;
    }),
  'inline on root: ' + (inlineProps(el).join(', ') || '(none)'));

record('the root is given no inline geometry or pointer-events that could turn it into a modal',
  ['pointer-events', 'position', 'inset', 'left', 'top', 'right', 'bottom',
   'width', 'height', 'z-index', 'background']
    .every(function (p) { return el.style.getPropertyValue(p) === ''; }),
  'root inline cssText: "' + el.style.cssText + '"');

record('the panel is given no inline style at all',
  panel.style.length === 0, 'panel inline cssText: "' + panel.style.cssText + '"');

record('computed: the root takes no pointer events and only the panel does, so Ora stays clickable',
  computed(el, 'pointer-events') === 'none'
    && computed(panel, 'pointer-events') === 'auto',
  'root ' + computed(el, 'pointer-events') + ' / panel ' + computed(panel, 'pointer-events'));

record('computed: the root is not stretched over the viewport',
  computed(el, 'width') !== '100vw' && computed(el, 'height') !== '100vh',
  'computed width ' + computed(el, 'width') + ', height ' + computed(el, 'height'));

record('the overlay root/panel keep the pointer-events split that leaves Ora clickable',
  el.classList.contains('conversation-browser-overlay')
    && panel.classList.contains('conversation-browser-panel')
    && /pointer-events:\s*none/.test(cssBlock('.conversation-browser-overlay'))
    && /pointer-events:\s*auto/.test(cssBlock('.conversation-browser-panel')),
  el.className + ' / ' + panel.className);

var EMITTED = [
  'conversation-browser-overlay', 'conversation-browser-panel',
  'conversation-browser-top', 'conversation-browser-status',
  'conversation-browser-close', 'conversation-browser-rows'
];
record('every class the overlay emits already exists in the shipped CSS',
  EMITTED.every(function (c) { return css.indexOf('.' + c) >= 0; }));

var moduleSource = fs.readFileSync(MODULE_PATH, 'utf8');
record('the module injects no stylesheet of its own',
  !/createElement\(\s*['"](style|link)['"]/.test(moduleSource)
    && moduleSource.indexOf('insertRule') < 0
    && moduleSource.indexOf('adoptedStyleSheets') < 0
    && moduleSource.indexOf('document.head') < 0);

record('focus moved to the dialog so Escape can reach it', doc.activeElement === el);

// ---- the header grid matches the header this module actually builds ---------
// The shared rule is sized for the Library's four header children. This one has
// two: left as-is, the two surplus tracks resolve to 0px but still cost their
// 6px gutters, and the first track's 240px floor makes the header wider than
// the 240px minimum the dock clamps to — at which width the panel's
// `overflow: hidden` clips the close button out of existence.

var sharedTop = cssBlock('.conversation-browser-top');
var sharedTracks = (/grid-template-columns:\s*([^;]+)/.exec(sharedTop) || [])[1] || '';
var headerTracks = header.style.getPropertyValue('grid-template-columns');

record('the header declares one grid track per child it actually has',
  header.children.length === 2 && trackCount(headerTracks) === header.children.length,
  header.children.length + ' children, inline template "' + headerTracks
    + '" (' + trackCount(headerTracks) + ' tracks) vs the shared "'
    + sharedTracks.trim() + '" (' + trackCount(sharedTracks) + ' tracks)');

record('the shared rule really does declare more tracks than this header fills',
  trackCount(sharedTracks) === 4 && trackCount(sharedTracks) > header.children.length,
  'shared template "' + sharedTracks.trim() + '"');

record('the override drops the 240px header minimum the dock\'s own 240px floor cannot satisfy',
  /minmax\(\s*240px/.test(sharedTracks) && /minmax\(\s*0\s*,/.test(headerTracks)
    && /overflow:\s*hidden/.test(cssBlock('.conversation-browser-panel')),
  'shared first track "' + sharedTracks.split(',')[0] + ')" vs header first track "'
    + headerTracks.split(',')[0] + ')"; the panel clips overflow');

record('the override is an inline style on the module\'s own element, not a stylesheet',
  header.style.length === 1 && header.style.item(0) === 'grid-template-columns'
    && doc.querySelectorAll('style').length === 1 && doc.querySelectorAll('link').length === 0,
  'header inline "' + header.style.cssText + '"; <style> in document: '
    + doc.querySelectorAll('style').length + ' (the test\'s own page stylesheet)');

// ---- listener census: window AND document, every type ----------------------

record('the module attaches no document-level listener of any type',
  liveDocument.length === 0 && everDocumentTypes.length === 0,
  'attached now: ' + typeList(liveDocument)
    + '; ever attached: ' + (everDocumentTypes.join(',') || '(none)'));

record('the only window listener of any type is the one resize the dock needs',
  liveWindow.length === 1 && liveWindow[0].type === 'resize'
    && everWindowTypes.join(',') === 'resize',
  'attached now: ' + typeList(liveWindow) + '; ever attached: ' + everWindowTypes.join(','));

record('exactly one resize listener and one ResizeObserver exist while open',
  liveResize().length === 1 && liveObservers().length === 1,
  'listeners=' + liveResize().length + ' observers=' + liveObservers().length);

record('the ResizeObserver watches all four shell elements',
  liveObservers()[0].observed.length === 4);

var inputRect = RECTS['.input-pane'];
inputRect.top = 200;
liveObservers()[0].callback([]);
record('the observer callback repositions the dock',
  props(el).top === '208px' && props(el).height === '584px',
  JSON.stringify(props(el)));

inputRect.top = 250;
liveResize()[0].fn();
record('the resize listener repositions the dock',
  props(el).top === '258px' && props(el).height === '534px',
  JSON.stringify(props(el)));
inputRect.top = 300;
liveResize()[0].fn();

// ---- every clamp in _position is load-bearing -------------------------------
// One rect configuration exercises no clamp at all: with the standard shell
// every Math.max picks its un-clamped operand, so deleting the lot changes
// nothing observable. Each configuration below makes one bind.

function withRects(overrides, fn) {
  var saved = {};
  Object.keys(overrides).forEach(function (sel) {
    saved[sel] = {};
    Object.keys(overrides[sel]).forEach(function (k) {
      saved[sel][k] = RECTS[sel][k];
      RECTS[sel][k] = overrides[sel][k];
    });
  });
  try {
    liveResize()[0].fn();
    fn();
  } finally {
    Object.keys(saved).forEach(function (sel) {
      Object.keys(saved[sel]).forEach(function (k) { RECTS[sel][k] = saved[sel][k]; });
    });
    liveResize()[0].fn();
  }
}

withRects({ '.input-pane': { top: 300, bottom: 320 } }, function () {
  record('the 24px height floor binds when the input pane is shorter than the dock needs',
    props(el).height === '24px' && props(el).top === '308px',
    'unclamped height would be ' + (320 - 8 - 308) + 'px → ' + JSON.stringify(props(el)));
});

withRects({ '.right-column': { right: 100 } }, function () {
  record('the left+240 right floor binds when the right column sits too far left',
    props(el).width === '240px' && props(el).left === '48px',
    'unclamped right edge would be ' + (100 - 8) + 'px against left 48px → '
      + JSON.stringify(props(el)));
});

withRects({ '.right-column': { right: 0 }, '.left-column': { left: 400 } }, function () {
  record('the dock is never narrower than 240px however far the shell collapses',
    props(el).width === '240px' && props(el).left === '408px',
    'unclamped width would be ' + (0 - 8 - 408) + 'px → ' + JSON.stringify(props(el)));
});

withRects({ '.input-pane': { top: -100 } }, function () {
  record('the dock top never rises above the top of the shell',
    props(el).top === '18px' && props(el).height === '774px',
    'input pane top -100 against shell top 10 → ' + JSON.stringify(props(el)));
});

record('the standard rects still produce the standard dock once the clamps stop binding',
  JSON.stringify(props(el)) === JSON.stringify(EXPECT), JSON.stringify(props(el)));

// ---- close: button, Escape, API; focus restoration; no leaks ---------------

el.querySelector('.conversation-browser-close').dispatchEvent(new w.Event('click'));
record('the close button closes the surface and fires onClose once',
  API.isOpen('plugin-files') === false && !el.classList.contains('is-open')
    && closedCount === 1);

record('focus returns to the element that held it before opening',
  doc.activeElement === opener,
  doc.activeElement ? doc.activeElement.id || doc.activeElement.className : 'none');

record('after close no resize listener survives and the observer is disconnected',
  liveResize().length === 0 && liveObservers().length === 0,
  'listeners=' + liveResize().length + ' observers=' + liveObservers().length);

record('close leaves nothing at all attached to window or document',
  liveWindow.length === 0 && liveDocument.length === 0,
  'window ' + typeList(liveWindow) + ' / document ' + typeList(liveDocument));

record('the overlay node stays mounted but hidden, ready to reopen',
  el.isConnected === true && !el.classList.contains('is-open')
    && computed(el, 'display') === 'none',
  'computed display ' + computed(el, 'display'));

opener.focus();
API.open('plugin-files');
record('reopening repaints the body from scratch rather than appending',
  painted === 2 && rows.children.length === 1);

record('reopening attaches exactly one listener and one observer, never two',
  liveResize().length === 1 && liveObservers().length === 1,
  'listeners=' + liveResize().length + ' observers=' + liveObservers().length);

el.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
record('Escape closes the surface, restores focus and leaves nothing attached',
  API.isOpen() === false && closedCount === 2 && doc.activeElement === opener
    && liveResize().length === 0 && liveObservers().length === 0);

opener.focus();
API.open('plugin-files');
record('.close() with no id closes whatever is open',
  API.close() === true && API.isOpen() === false && liveResize().length === 0);

record('.close() on an unknown id returns false', API.close('no-such-overlay') === false);
record('.close() on a registered but closed overlay returns false',
  API.close('plugin-files') === false);

warnings.length = 0;
record('open() on an unknown id warns and returns false',
  API.open('no-such-overlay') === false && warned(/no overlay is registered/));

// ---- a docked surface never steals focus from whoever holds it -------------
// The overlay is non-modal, so the rest of Ora is live the whole time it is up.
// A close that hands focus back unconditionally yanks the user out of an input
// they moved to, and strands a surface a plugin opened from inside its onClose.

opener.focus();
API.open('plugin-files');
typing.focus();                       // the user moves on to an input in Ora
API.close('plugin-files');
record('a programmatic close does not take focus off the input the user moved to',
  doc.activeElement === typing,
  'activeElement is ' + (doc.activeElement && doc.activeElement.id || 'none'));

var secondOff = API.register({ id: 'second-surface', label: 'Second', render: noop });
var firstOff = API.register({
  id: 'first-surface', label: 'First', render: noop,
  onClose: function () { API.open('second-surface'); }
});
opener.focus();
API.open('first-surface');
API.close('first-surface');
var secondNode = nodeFor('second-surface');
record('a surface opened from inside another\'s onClose keeps the focus it was given',
  doc.activeElement === secondNode,
  'activeElement is ' + (doc.activeElement === secondNode ? 'the second surface'
    : (doc.activeElement && (doc.activeElement.id || doc.activeElement.className)) || 'none'));

// Escape as a browser delivers it: to whatever holds focus, bubbling upward.
doc.activeElement.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
record('and Escape therefore still reaches it — the surface can be closed at all',
  API.isOpen('second-surface') === false,
  'isOpen after Escape: ' + API.isOpen('second-surface'));

opener.focus();
API.open('first-surface');
API.close('first-surface');           // hides first, opens second from its onClose
API.close('second-surface');
record('focus is never handed to an overlay root that is already hidden',
  doc.activeElement !== nodeFor('first-surface')
    && !nodeFor('first-surface').classList.contains('is-open'),
  'activeElement is ' + (doc.activeElement === nodeFor('first-surface')
    ? 'the hidden first surface' : 'not the hidden surface'));
API.close();
firstOff(); secondOff();

// ---- a detached root or body is rebuilt, loudly ----------------------------
// A plugin holds ctx.root and ctx.body for as long as it likes. If either
// leaves the document, rec.el stays truthy: without a connectedness check
// open() returns true, isOpen() agrees, and there is nothing on screen.

var ghostRoot = null;
var ghostPainted = 0;
var ghostOff = API.register({
  id: 'ghost', label: 'Ghost',
  render: function (body, ctx) {
    ghostPainted++;
    ghostRoot = ctx.root;
    var row = doc.createElement('div');
    row.className = 'conversation-browser-row';
    row.textContent = 'still here';
    body.appendChild(row);
  }
});
API.open('ghost');
ghostRoot.parentNode.removeChild(ghostRoot);   // a render removed its own root
API.close('ghost');
warnings.length = 0;
var ghostReopened = API.open('ghost');
var ghostNode = nodeFor('ghost');
record('a detached root is rebuilt so reopening actually puts a surface on screen',
  ghostReopened === true && !!ghostNode && ghostNode.isConnected === true
    && ghostNode.classList.contains('is-open')
    && ghostNode.querySelector('.conversation-browser-rows').children.length === 1,
  'connected ghost nodes: ' + overlayNodes().filter(function (n) {
    return n.getAttribute('data-ora-browse-overlay') === 'ghost';
  }).length);

record('the rebuild is announced rather than failing open AND silent',
  warned(/no longer in the document/) && warned(/rebuilding the surface/),
  warnings.join(' | ') || '(no warning)');

record('the rebuilt surface positions and cleans up like any other',
  JSON.stringify(props(ghostNode)) === JSON.stringify(EXPECT)
    && liveResize().length === 1 && liveObservers().length === 1,
  JSON.stringify(props(ghostNode)));
API.close('ghost');

// The same class of failure through the body: a render that clears the panel.
API.open('ghost');
nodeFor('ghost').querySelector('.conversation-browser-panel').innerHTML = '';
API.close('ghost');
warnings.length = 0;
API.open('ghost');
var ghostRows = nodeFor('ghost').querySelector('.conversation-browser-rows');
record('a detached rows body is rebuilt too, so renders keep painting somewhere visible',
  !!ghostRows && ghostRows.isConnected === true && ghostRows.children.length === 1
    && warned(/rows body was removed/),
  'rows connected ' + (ghostRows && ghostRows.isConnected)
    + ', children ' + (ghostRows && ghostRows.children.length));
API.close('ghost');
record('rebuilding leaves no listener or observer from the discarded DOM behind',
  liveResize().length === 0 && liveObservers().length === 0
    && liveWindow.length === 0 && liveDocument.length === 0,
  'listeners=' + liveResize().length + ' observers=' + liveObservers().length);
ghostOff();

// ---- one open() runs the open path once ------------------------------------
// _closeOthers enters plugin code. An onClose that opens the very surface being
// opened makes the inner call complete the whole open path; continuing the
// outer one clears the body the inner call just painted and fires the plugin's
// render and onOpen a second time.

var reentrantPainted = 0;
var reentrantOpened = 0;
var firstRow = null;
var reentrantOff = API.register({
  id: 'reentrant', label: 'Reentrant',
  render: function (body) {
    reentrantPainted++;
    var row = doc.createElement('div');
    row.className = 'conversation-browser-row';
    row.textContent = 'row';
    body.appendChild(row);
    if (reentrantPainted === 1) firstRow = row;
  },
  onOpen: function () { reentrantOpened++; }
});
var trampolineOff = API.register({
  id: 'trampoline', label: 'Trampoline', render: noop,
  onClose: function () { API.open('reentrant'); }
});
API.open('trampoline');
reentrantPainted = 0; reentrantOpened = 0; firstRow = null;
var reentrantResult = API.open('reentrant');
var reentrantRows = nodeFor('reentrant').querySelector('.conversation-browser-rows');
record('an onClose that reopens the same surface still runs render and onOpen once each',
  reentrantResult === true && reentrantPainted === 1 && reentrantOpened === 1,
  'render fired ' + reentrantPainted + 'x, onOpen fired ' + reentrantOpened + 'x');

record('and the rows that render painted survive rather than being wiped by the outer call',
  reentrantRows.children.length === 1 && !!firstRow && firstRow.isConnected === true
    && reentrantRows.children[0] === firstRow,
  'rows ' + reentrantRows.children.length + ', first painted row still connected: '
    + (firstRow && firstRow.isConnected));

record('the reentrant open leaves one listener and one observer, not two',
  liveResize().length === 1 && liveObservers().length === 1,
  'listeners=' + liveResize().length + ' observers=' + liveObservers().length);
API.close();

// An onClose that opens a DIFFERENT surface must not leave two on one dock.
var thirdOff = API.register({ id: 'third', label: 'Third', render: noop });
var springOff = API.register({
  id: 'spring', label: 'Spring', render: noop,
  onClose: function () { API.open('third'); }
});
API.open('spring');
API.open('reentrant');
record('one dock holds one surface even when an onClose opens another',
  openNodes().length === 1
    && openNodes()[0].getAttribute('data-ora-browse-overlay') === 'reentrant',
  'open: [' + openNodes().map(function (n) {
    return n.getAttribute('data-ora-browse-overlay');
  }).join(', ') + ']');

record('and only one listener and one observer are live for that one surface',
  liveResize().length === 1 && liveObservers().length === 1,
  'listeners=' + liveResize().length + ' observers=' + liveObservers().length);
API.close();
reentrantOff(); trampolineOff(); thirdOff(); springOff();

record('every one of those surfaces is gone from the registry and the document',
  API.list().map(function (e) { return e.id; }).join(',') === 'plugin-files'
    && liveWindow.length === 0 && liveDocument.length === 0
    && liveObservers().length === 0,
  API.list().map(function (e) { return e.id; }).join(','));

// ---- one dock, one surface --------------------------------------------------

var outputsClosed = 0;
var outputsOff = API.register({
  id: 'plugin-outputs',
  label: 'Plugin Outputs',
  render: function (body) {
    var row = doc.createElement('div');
    row.className = 'conversation-browser-row';
    row.textContent = 'render-04.svg';
    body.appendChild(row);
  },
  onClose: function () { outputsClosed++; }
});

API.open('plugin-files');
API.open('plugin-outputs');
record('opening a second overlay closes the first — they share one dock',
  API.isOpen('plugin-outputs') === true && API.isOpen('plugin-files') === false
    && openNodes().length === 1);

record('the superseded overlay fired its onClose', closedCount === 5,
  'closedCount=' + closedCount);

record('supersession leaves exactly one listener and one observer, not two of each',
  liveResize().length === 1 && liveObservers().length === 1,
  'listeners=' + liveResize().length + ' observers=' + liveObservers().length);

var throwCloseOff = API.register({
  id: 'close-thrower',
  label: 'Close Thrower',
  render: noop,
  onClose: function () { throw new Error('close boom'); }
});
API.open('close-thrower');
warnings.length = 0;
API.open('plugin-outputs');
record('a throwing onClose is contained and the superseding overlay still opens',
  API.isOpen('plugin-outputs') === true && API.isOpen('close-thrower') === false
    && warned(/close boom/) && openNodes().length === 1);
throwCloseOff();
API.close();

// ---- removal ----------------------------------------------------------------

opener.focus();
API.open('plugin-outputs');
var removed = outputsOff();
record('unregistering an open overlay closes it and removes its DOM node',
  removed === true && API.has('plugin-outputs') === false
    && nodeFor('plugin-outputs') === null && API.isOpen() === false
    && outputsClosed === 3);

record('unregistering an open overlay leaves no listener or observer behind',
  liveResize().length === 0 && liveObservers().length === 0
    && liveWindow.length === 0 && liveDocument.length === 0,
  'listeners=' + liveResize().length + ' observers=' + liveObservers().length);

record('unregistering an open overlay still restores focus',
  doc.activeElement === opener);

record('a second call on a spent unregister handle returns false',
  outputsOff() === false);

var staleOff = API.register({ id: 'recycled', label: 'First', render: noop });
staleOff();
var freshOff = API.register({ id: 'recycled', label: 'Second', render: noop });
record('a stale handle cannot evict a later overlay registered under the same id',
  staleOff() === false && API.has('recycled') === true
    && API.get('recycled').label === 'Second');
freshOff();

record('list() reports the entries still registered',
  API.list().map(function (e) { return e.id; }).join(',') === 'plugin-files',
  API.list().map(function (e) { return e.id; }).join(','));

// ---- fail-open: invalid registrations --------------------------------------

warnings.length = 0;
var noopHandle = API.register();
record('a missing entry is rejected with a warning and a no-op handle',
  typeof noopHandle === 'function' && noopHandle() === false
    && warned(/entry must be an object/));

warnings.length = 0;
API.register('not-an-object');
record('a non-object entry is rejected', warned(/entry must be an object/));

warnings.length = 0;
API.register({ label: 'No Id', render: noop });
record('a missing id is rejected', warned(/entry\.id is required/));

warnings.length = 0;
API.register({ id: 'no-label', render: noop });
record('a missing label is rejected',
  warned(/entry\.label is required/) && API.has('no-label') === false);

warnings.length = 0;
API.register({ id: 'no-render', label: 'No Render' });
record('a missing render is rejected rather than mounting an empty surface',
  warned(/entry\.render must be a function/) && API.has('no-render') === false);

warnings.length = 0;
API.register({ id: 'bad-onopen', label: 'Bad onOpen', render: noop, onOpen: 'nope' });
record('a non-function onOpen is rejected', warned(/entry\.onOpen must be a function/));

warnings.length = 0;
API.register({ id: 'bad-onclose', label: 'Bad onClose', render: noop, onClose: 42 });
record('a non-function onClose is rejected', warned(/entry\.onClose must be a function/));

warnings.length = 0;
API.register({
  id: 'label-getter-thrower', render: noop,
  get label() { throw new Error('label boom at registration'); }
});
record('a label getter that throws at registration is contained, not propagated',
  warned(/label boom at registration/) && warned(/entry\.label is required/)
    && API.has('label-getter-thrower') === false);

warnings.length = 0;
API.register({ id: 'plugin-files', label: 'Impostor', render: noop });
record('a duplicate id is rejected and the live overlay is untouched',
  warned(/already registered/) && API.get('plugin-files').label === 'Plugin Files'
    && overlayNodes().length === 1);

// ---- fail-open: throwing / rejecting plugin callbacks ----------------------

warnings.length = 0;
var renderThrowOff = API.register({
  id: 'render-thrower', label: 'Render Thrower',
  render: function () { throw new Error('render boom'); }
});
API.open('render-thrower');
var rtNode = nodeFor('render-thrower');
record('a render that throws is contained and the surface still opens, empty',
  API.isOpen('render-thrower') === true && warned(/render boom/)
    && rtNode.querySelector('.conversation-browser-rows').children.length === 0);
API.close();
renderThrowOff();

warnings.length = 0;
var openThrowOff = API.register({
  id: 'onopen-thrower', label: 'onOpen Thrower', render: noop,
  onOpen: function () { throw new Error('onOpen boom'); }
});
API.open('onopen-thrower');
record('an onOpen that throws is contained and the surface stays open',
  API.isOpen('onopen-thrower') === true && warned(/onOpen boom/));
warnings.length = 0;
API.close();
openThrowOff();

var rejectOff = API.register({
  id: 'render-rejecter', label: 'Render Rejecter',
  render: function () { return Promise.reject(new Error('async boom')); }
});
API.open('render-rejecter');
record('a render returning a rejected thenable still opens the surface',
  API.isOpen('render-rejecter') === true);
API.close();
rejectOff();

// ---- fail-open: a label that starts throwing after registration ------------

var flip = false;
var flipOff = API.register({
  id: 'label-flip', render: noop,
  get label() {
    if (flip) throw new Error('label boom at use');
    return 'Flip Surface';
  }
});
API.open('label-flip');
var flipNode = nodeFor('label-flip');
record('the title and accessible name come from the label read at open time',
  flipNode.querySelector('.conversation-browser-status').textContent === 'Flip Surface'
    && flipNode.getAttribute('aria-label') === 'Flip Surface');
API.close();

flip = true;
warnings.length = 0;
API.open('label-flip');
record('a label getter that starts throwing is contained and falls back',
  API.isOpen('label-flip') === true && warned(/label boom at use/)
    && flipNode.querySelector('.conversation-browser-status').textContent === 'Flip Surface');
API.close();
flip = false;
flipOff();

// ---- hostile ids ------------------------------------------------------------

var protoOff = API.register({ id: '__proto__', label: 'Proto', render: noop });
var ctorOff = API.register({ id: 'constructor', label: 'Ctor', render: noop });
var hopOff = API.register({ id: 'hasOwnProperty', label: 'Hop', render: noop });
API.open('__proto__');
record('prototype-named ids register, open and list like any other id',
  API.has('__proto__') && API.has('constructor') && API.has('hasOwnProperty')
    && API.isOpen('__proto__') === true
    && API.list().map(function (e) { return e.id; }).sort().join(',')
       === '__proto__,constructor,hasOwnProperty,plugin-files',
  API.list().map(function (e) { return e.id; }).join(','));
record('registering "__proto__" did not pollute the registry',
  API.has('toString') === false && API.get('isPrototypeOf') === null
    && Object.getPrototypeOf({}) === Object.prototype);
API.close();
protoOff(); ctorOff(); hopOff();

var nastyId = 'x"><img src=x onerror="boom()">';
var nastyOff = API.register({
  id: nastyId, label: '<b>Bold</b> & "quoted"',
  render: function (body) { body.textContent = 'safe'; }
});
API.open(nastyId);
var nastyNode = nodeFor(nastyId);
record('an id containing markup is stored as an attribute value, never parsed',
  !!nastyNode && doc.querySelectorAll('img').length === 0
    && doc.querySelectorAll('script').length === 0);
record('a label containing markup is rendered as text, never as markup',
  nastyNode.querySelector('.conversation-browser-status').textContent
      === '<b>Bold</b> & "quoted"'
    && nastyNode.querySelectorAll('b').length === 0
    && nastyNode.getAttribute('aria-label') === '<b>Bold</b> & "quoted"');
API.close();
nastyOff();

// ---- the shell is absent entirely ------------------------------------------
// The Library degrades by leaving the CSS defaults standing, and this module
// matches that degradation deliberately. But the defaults are left 0 / top 0 /
// width 100vw / height 160px around a `pointer-events: auto` panel — an
// interactive band across the full width of the top of the app. That is a
// failure worth saying out loud, not a correct outcome.

var shell = doc.querySelector('.ora-shell');
var shellParent = shell.parentNode;
shellParent.removeChild(shell);

var overlayRule = cssBlock('.conversation-browser-overlay');
var fallback = {};
['left', 'top', 'width', 'height'].forEach(function (p) {
  var m = new RegExp(p + ':\\s*var\\(--conversation-browser-' + p + ',\\s*([^)]+)\\)')
    .exec(overlayRule);
  fallback[p] = m ? m[1].trim() : '(not declared)';
});

var bareOff = API.register({ id: 'bare', label: 'Bare', render: noop });
warnings.length = 0;
var bareOpened = API.open('bare');
var bareNode = nodeFor('bare');
var barePanel = bareNode && bareNode.querySelector('.conversation-browser-panel');
record('with no shell at all the surface still opens rather than throwing',
  bareOpened === true && !!bareNode && bareNode.classList.contains('is-open'));

record('the geometry failure is said out loud instead of degrading in silence',
  warned(/dock geometry for "bare" cannot be computed/)
    && warned(/\.ora-shell and \.input-pane missing from the document/),
  warnings.join(' | ') || '(no warning)');

record('and the warning names the consequence: a full-width interactive band across the top',
  warned(/left 0, top 0, width 100vw, height 160px/)
    && warned(/full width of the top of the app/),
  warnings.join(' | ') || '(no warning)');

record('the consequence is real — unset properties hand the dock to exactly those defaults',
  JSON.stringify(props(bareNode)) === JSON.stringify(
    { left: '', top: '', width: '', height: '' })
    && fallback.left === '0' && fallback.top === '0'
    && fallback.width === '100vw' && fallback.height === '160px'
    && computed(barePanel, 'pointer-events') === 'auto',
  'unset → CSS fallbacks left ' + fallback.left + ', top ' + fallback.top
    + ', width ' + fallback.width + ', height ' + fallback.height
    + '; panel pointer-events ' + computed(barePanel, 'pointer-events'));

record('degrading still leaves the rest of Ora alone — nothing inert, no scroll lock',
  doc.querySelectorAll('[aria-hidden]').length === 0
    && doc.querySelectorAll('[inert]').length === 0
    && doc.documentElement.style.cssText === HTML_STYLE_BEFORE
    && liveDocument.length === 0
    && computed(bareNode, 'pointer-events') === 'none');

warnings.length = 0;
liveResize()[0].fn();
record('the warning is said once per open, not once per resize tick',
  warnings.length === 0, warnings.join(' | '));

record('with no shell the observer has nothing to watch but is still created',
  liveObservers().length === 1 && liveObservers()[0].observed.length === 0);
API.close();
record('with no shell the listener and observer still detach cleanly on close',
  liveResize().length === 0 && liveObservers().length === 0
    && liveWindow.length === 0 && liveDocument.length === 0);
bareOff();

shellParent.appendChild(shell);
applyRects();

// ---- teardown of the last survivor ------------------------------------------

filesOff();
record('the registry and the DOM are both empty once everything is unregistered',
  API.list().length === 0 && overlayNodes().length === 0
    && liveResize().length === 0 && liveObservers().length === 0);

record('no listener of any type survives on window or document',
  liveWindow.length === 0 && liveDocument.length === 0
    && everDocumentTypes.length === 0 && everWindowTypes.join(',') === 'resize',
  'window now ' + typeList(liveWindow) + ' (ever: ' + everWindowTypes.join(',') + ')'
    + '; document now ' + typeList(liveDocument)
    + ' (ever: ' + (everDocumentTypes.join(',') || 'none') + ')');

// ---- async phase: the rejected thenable must have landed in the warn path ---

setTimeout(function () {
  record('a render returning a rejected thenable routes into the same warn path',
    allWarnings.some(function (m) { return /async boom/.test(m); }),
    allWarnings.filter(function (m) { return /boom/.test(m); }).join(' | '));
  record('no plugin rejection escapes as an unhandled rejection',
    unhandled.length === 0, unhandled.join(' | '));
  summarize();
}, 30);
