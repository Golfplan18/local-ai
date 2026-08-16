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

summarize();
