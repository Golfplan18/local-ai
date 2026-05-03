#!/usr/bin/env node
/* test-hide-on-blur.js — WP-7.1.4
 *
 * jsdom-driven test harness for VisualPanel hide-on-blur chrome.
 * Verifies the contract from §13.1 of the Visual Intelligence Plan:
 *   - mouseleave triggers a hide after the 200 ms grace timer.
 *   - mouseenter cancels the pending hide and shows the chrome.
 *   - focusin shows the chrome (cancels pending hide).
 *   - mid-draw the panel does NOT hide (drawContext guard).
 *   - mid-text-entry the panel does NOT hide (textInputEl / annotInputEl guard).
 *   - mid-pan the panel does NOT hide (panning guard).
 *   - destroy() removes the chrome-hidden class and clears the timer.
 *
 * Run:  node ~/ora/server/static/tests/test-hide-on-blur.js
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var path = require('path');
var fs = require('fs');

var ORA_ROOT = path.resolve(__dirname, '..', '..', '..');
var MODULE_PATH = path.join(ORA_ROOT, 'server', 'static', 'visual-panel.js');
var JSDOM_PATH = path.join(ORA_ROOT, 'server', 'static', 'ora-visual-compiler', 'tests', 'node_modules', 'jsdom');

var jsdom = require(JSDOM_PATH);
var JSDOM = jsdom.JSDOM;

// ── runner -----------------------------------------------------------------

var passCount = 0;
var failCount = 0;
var failures = [];

function pass(name) {
  passCount++;
  process.stdout.write('  PASS  ' + name + '\n');
}

function fail(name, message) {
  failCount++;
  failures.push({ name: name, message: message });
  process.stdout.write('  FAIL  ' + name + ' — ' + message + '\n');
}

function assertEqual(name, actual, expected) {
  if (actual === expected) pass(name);
  else fail(name, 'expected ' + JSON.stringify(expected) + ', got ' + JSON.stringify(actual));
}

function assertTrue(name, cond, detail) {
  if (cond) pass(name);
  else fail(name, 'condition false' + (detail ? ' — ' + detail : ''));
}

// ── per-case fresh module + jsdom -----------------------------------------

function freshHarness() {
  // Drop any cached module so the IIFE re-binds to the new window.
  delete require.cache[require.resolve(MODULE_PATH)];

  var dom = new JSDOM('<!doctype html><html><head></head><body><div id="host"></div></body></html>', {
    url: 'http://localhost/',
    pretendToBeVisual: true
  });
  var win = dom.window;
  var doc = win.document;

  // Map jsdom globals so the IIFE's `typeof window/document` checks succeed.
  // Note: we deliberately do NOT remap setTimeout/clearTimeout — Node's are
  // already on globalThis and the module references them globally.
  global.window = win;
  global.document = doc;

  // Load the module — it self-registers VisualPanel on global.window.
  require(MODULE_PATH);
  var Cls = win.VisualPanel;
  if (!Cls) throw new Error('VisualPanel did not register on window');

  // Construct a panel against a host div. Konva is not loaded in jsdom; the
  // module handles that gracefully (shows an error bar). We don't need a
  // stage for the chrome-blur tests — they only exercise this.el listeners.
  var host = doc.getElementById('host');
  var panel = new Cls(host, { id: 'test' });
  panel.init();

  return { win: win, doc: doc, panel: panel, host: host };
}

function teardown(h) {
  try { h.panel.destroy(); } catch (e) {}
  try { h.win.close(); } catch (e) {}
  delete global.window;
  delete global.document;
}

function dispatchMouseEvent(el, type) {
  var win = el.ownerDocument.defaultView;
  var evt = new win.MouseEvent(type, { bubbles: false, cancelable: true });
  el.dispatchEvent(evt);
}

function dispatchFocusEvent(el, type) {
  var win = el.ownerDocument.defaultView;
  var evt = new win.FocusEvent(type, { bubbles: true, cancelable: true });
  el.dispatchEvent(evt);
}

// Wait n ms by spinning the jsdom timer queue. jsdom's setTimeout is
// real-time, so we just delay via Promise.
function wait(ms) {
  return new Promise(function (resolve) { setTimeout(resolve, ms); });
}

// ── test cases -------------------------------------------------------------

process.stdout.write('\n--- visual-panel hide-on-blur (WP-7.1.4) ---\n');

async function run() {

  // Case 1: mouseleave hides after the 200 ms grace.
  await (async function caseMouseLeaveHides() {
    var h = freshHarness();
    try {
      assertEqual('initial: chrome-hidden absent', h.host.classList.contains('chrome-hidden'), false);

      dispatchMouseEvent(h.host, 'mouseleave');
      // Right after the event the class should still be absent (debounce).
      assertEqual('immediately after mouseleave: still visible', h.host.classList.contains('chrome-hidden'), false);

      await wait(260);
      assertEqual('after 260 ms: chrome-hidden applied', h.host.classList.contains('chrome-hidden'), true);
      assertEqual('panel._chromeHidden tracks state', h.panel._chromeHidden, true);
    } finally { teardown(h); }
  })();

  // Case 2: mouseenter cancels the pending hide.
  await (async function caseMouseEnterCancels() {
    var h = freshHarness();
    try {
      dispatchMouseEvent(h.host, 'mouseleave');
      // Re-enter before grace elapses.
      await wait(50);
      dispatchMouseEvent(h.host, 'mouseenter');
      await wait(260);
      assertEqual('mouseenter cancelled hide', h.host.classList.contains('chrome-hidden'), false);
    } finally { teardown(h); }
  })();

  // Case 3: hide first, then mouseenter restores chrome.
  await (async function caseMouseEnterRestores() {
    var h = freshHarness();
    try {
      dispatchMouseEvent(h.host, 'mouseleave');
      await wait(260);
      assertEqual('hidden after mouseleave', h.host.classList.contains('chrome-hidden'), true);

      dispatchMouseEvent(h.host, 'mouseenter');
      assertEqual('mouseenter restores chrome immediately', h.host.classList.contains('chrome-hidden'), false);
    } finally { teardown(h); }
  })();

  // Case 4: focusin while hidden restores chrome.
  await (async function caseFocusInShows() {
    var h = freshHarness();
    try {
      dispatchMouseEvent(h.host, 'mouseleave');
      await wait(260);
      assertEqual('hidden after mouseleave', h.host.classList.contains('chrome-hidden'), true);

      dispatchFocusEvent(h.host, 'focusin');
      assertEqual('focusin restores chrome', h.host.classList.contains('chrome-hidden'), false);
    } finally { teardown(h); }
  })();

  // Case 5: mid-draw the panel does NOT hide.
  await (async function caseMidDrawNoHide() {
    var h = freshHarness();
    try {
      h.panel._drawContext = { type: 'rect', start: { x: 0, y: 0 } };
      dispatchMouseEvent(h.host, 'mouseleave');
      await wait(260);
      assertEqual('drawContext guard: still visible', h.host.classList.contains('chrome-hidden'), false);
      h.panel._drawContext = null;
    } finally { teardown(h); }
  })();

  // Case 6: mid-pen-stroke the panel does NOT hide.
  await (async function caseMidPenNoHide() {
    var h = freshHarness();
    try {
      h.panel._penContext = { line: {} };
      dispatchMouseEvent(h.host, 'mouseleave');
      await wait(260);
      assertEqual('penContext guard: still visible', h.host.classList.contains('chrome-hidden'), false);
      h.panel._penContext = null;
    } finally { teardown(h); }
  })();

  // Case 7: mid-text-entry (text tool) does NOT hide.
  await (async function caseMidTextNoHide() {
    var h = freshHarness();
    try {
      h.panel._textInputEl = h.doc.createElement('input');
      dispatchMouseEvent(h.host, 'mouseleave');
      await wait(260);
      assertEqual('textInputEl guard: still visible', h.host.classList.contains('chrome-hidden'), false);
      h.panel._textInputEl = null;
    } finally { teardown(h); }
  })();

  // Case 8: mid-annotation-text-entry (callout/sticky) does NOT hide.
  await (async function caseMidAnnotInputNoHide() {
    var h = freshHarness();
    try {
      h.panel._annotInputEl = h.doc.createElement('input');
      dispatchMouseEvent(h.host, 'mouseleave');
      await wait(260);
      assertEqual('annotInputEl guard: still visible', h.host.classList.contains('chrome-hidden'), false);
      h.panel._annotInputEl = null;
    } finally { teardown(h); }
  })();

  // Case 9: mid-pan does NOT hide.
  await (async function caseMidPanNoHide() {
    var h = freshHarness();
    try {
      h.panel._panning = true;
      dispatchMouseEvent(h.host, 'mouseleave');
      await wait(260);
      assertEqual('panning guard: still visible', h.host.classList.contains('chrome-hidden'), false);
      h.panel._panning = false;
    } finally { teardown(h); }
  })();

  // Case 10: destroy() restores chrome and clears the timer.
  await (async function caseDestroyClearsState() {
    var h = freshHarness();
    try {
      dispatchMouseEvent(h.host, 'mouseleave');
      await wait(260);
      assertEqual('hidden before destroy', h.host.classList.contains('chrome-hidden'), true);

      h.panel.destroy();
      assertEqual('destroy clears chrome-hidden', h.host.classList.contains('chrome-hidden'), false);
      assertEqual('destroy clears _chromeHidden', h.panel._chromeHidden, false);
      assertEqual('destroy nulls handler refs (mouseenter)', h.panel._onChromeMouseEnter, null);
      assertEqual('destroy nulls handler refs (mouseleave)', h.panel._onChromeMouseLeave, null);
      assertEqual('destroy nulls handler refs (focusin)',    h.panel._onChromeFocusIn,    null);
      assertEqual('destroy nulls handler refs (focusout)',   h.panel._onChromeFocusOut,   null);
    } finally {
      // Avoid double-destroy in teardown.
      try { h.win.close(); } catch (e) {}
      delete global.window;
      delete global.document;
    }
  })();

  // Case 11: re-enter cancels even after multiple consecutive leave events.
  await (async function caseRapidToggleConverges() {
    var h = freshHarness();
    try {
      for (var i = 0; i < 5; i++) {
        dispatchMouseEvent(h.host, 'mouseleave');
        dispatchMouseEvent(h.host, 'mouseenter');
      }
      // After settling, chrome should be visible.
      await wait(260);
      assertEqual('rapid toggle settles visible', h.host.classList.contains('chrome-hidden'), false);
    } finally { teardown(h); }
  })();

  // ── summary ----------------------------------------------------------------

  process.stdout.write('\n');
  process.stdout.write('  ' + passCount + ' passed\n');
  if (failCount > 0) {
    process.stdout.write('  ' + failCount + ' FAILED\n');
    failures.forEach(function (f) {
      process.stdout.write('    - ' + f.name + ': ' + f.message + '\n');
    });
    process.exit(1);
  } else {
    process.stdout.write('  all green\n');
    process.exit(0);
  }
}

run().catch(function (err) {
  process.stderr.write('\n  HARNESS ERROR: ' + (err && err.stack ? err.stack : err) + '\n');
  process.exit(1);
});
