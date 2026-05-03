#!/usr/bin/env node
/* test-canvas-share-reminder.js — WP-7.7.6
 *
 * jsdom-driven test harness for canvas-share-reminder.js. Verifies:
 *   - First share triggers the modal.
 *   - Second share in the same session does NOT trigger the modal.
 *   - Confirm runs onConfirm; Cancel runs onCancel.
 *   - Esc cancels; backdrop click cancels.
 *   - reset() clears the session flag — next share triggers the modal again.
 *   - Module is idempotent against double-init.
 *   - Both the requestShare() helper and a raw window.dispatchEvent() of
 *     `ora:canvas-pre-share` flow through identically.
 *
 * Run:  node ~/ora/server/static/tests/test-canvas-share-reminder.js
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var path = require('path');
var fs = require('fs');

var ORA_ROOT = path.resolve(__dirname, '..', '..', '..');
var MODULE_PATH = path.join(ORA_ROOT, 'server', 'static', 'canvas-share-reminder.js');
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

  var dom = new JSDOM('<!doctype html><html><head></head><body></body></html>', {
    url: 'http://localhost/',
    pretendToBeVisual: true
  });
  var win = dom.window;
  var doc = win.document;

  // Map jsdom globals so the IIFE's `typeof window/document` checks succeed.
  global.window = win;
  global.document = doc;
  // CustomEvent + sessionStorage live on jsdom's window already.

  // Load the module — it self-registers on global.window.
  require(MODULE_PATH);
  var ns = win.OraCanvasShareReminder;
  if (!ns) throw new Error('OraCanvasShareReminder did not register on window');
  return { win: win, doc: doc, ns: ns };
}

function teardown(h) {
  try { h.ns.destroy(); } catch (e) {}
  try { h.win.sessionStorage.clear(); } catch (e) {}
  try { h.win.close(); } catch (e) {}
  delete global.window;
  delete global.document;
}

function modalIsOpen(h) {
  var modal = h.doc.getElementById('ora-canvas-share-reminder-modal');
  return !!(modal && modal.hidden === false);
}

function clickAction(h, action) {
  var modal = h.doc.getElementById('ora-canvas-share-reminder-modal');
  if (!modal) throw new Error('modal not mounted');
  var btn = modal.querySelector('[data-action="' + action + '"]');
  if (!btn) throw new Error('button not found: ' + action);
  // Synthesize a bubbling MouseEvent so the delegated click handler fires.
  var evt = new h.win.MouseEvent('click', { bubbles: true, cancelable: true });
  btn.dispatchEvent(evt);
}

function pressEscape(h) {
  var evt = new h.win.KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
  h.doc.dispatchEvent(evt);
}

// ── test cases -------------------------------------------------------------

process.stdout.write('\n--- canvas-share-reminder ---\n');

// Case 1: First share opens the modal; second share in same session doesn't.
(function caseOneTimePerSession() {
  var h = freshHarness();
  try {
    h.ns.init();
    var calls1 = { confirm: 0, cancel: 0 };
    h.ns.requestShare({
      intent: 'share',
      onConfirm: function () { calls1.confirm++; },
      onCancel:  function () { calls1.cancel++; }
    });
    assertTrue('case1: modal opens on first share', modalIsOpen(h));
    assertEqual('case1: confirm not called yet', calls1.confirm, 0);

    clickAction(h, 'confirm');
    assertEqual('case1: confirm called after click', calls1.confirm, 1);
    assertTrue('case1: modal closed after confirm', !modalIsOpen(h));
    assertTrue('case1: hasBeenReminded() is true', h.ns.hasBeenReminded());

    var calls2 = { confirm: 0, cancel: 0 };
    h.ns.requestShare({
      intent: 'share',
      onConfirm: function () { calls2.confirm++; },
      onCancel:  function () { calls2.cancel++; }
    });
    assertTrue('case1: modal does NOT open on second share', !modalIsOpen(h));
    assertEqual('case1: second-share onConfirm fired immediately', calls2.confirm, 1);
    assertEqual('case1: second-share onCancel not fired', calls2.cancel, 0);
  } finally { teardown(h); }
})();

// Case 2: Cancel button calls onCancel and does NOT mark reminded.
(function caseCancelButton() {
  var h = freshHarness();
  try {
    h.ns.init();
    var calls = { confirm: 0, cancel: 0 };
    h.ns.requestShare({
      intent: 'share',
      onConfirm: function () { calls.confirm++; },
      onCancel:  function () { calls.cancel++; }
    });
    assertTrue('case2: modal open before cancel', modalIsOpen(h));
    clickAction(h, 'cancel');
    assertEqual('case2: onCancel called', calls.cancel, 1);
    assertEqual('case2: onConfirm NOT called', calls.confirm, 0);
    assertTrue('case2: modal closed after cancel', !modalIsOpen(h));
    assertTrue('case2: hasBeenReminded() still false', !h.ns.hasBeenReminded());

    // Next share should still trigger the modal because we didn't confirm.
    var calls2 = { confirm: 0, cancel: 0 };
    h.ns.requestShare({
      intent: 'share',
      onConfirm: function () { calls2.confirm++; },
      onCancel:  function () { calls2.cancel++; }
    });
    assertTrue('case2: modal opens on next share since prev was cancelled', modalIsOpen(h));
  } finally { teardown(h); }
})();

// Case 3: Escape key cancels.
(function caseEscapeKey() {
  var h = freshHarness();
  try {
    h.ns.init();
    var calls = { confirm: 0, cancel: 0 };
    h.ns.requestShare({
      onConfirm: function () { calls.confirm++; },
      onCancel:  function () { calls.cancel++; }
    });
    assertTrue('case3: modal open before Escape', modalIsOpen(h));
    pressEscape(h);
    assertEqual('case3: Escape fires onCancel', calls.cancel, 1);
    assertTrue('case3: Escape closes the modal', !modalIsOpen(h));
    assertTrue('case3: Escape does NOT mark reminded', !h.ns.hasBeenReminded());
  } finally { teardown(h); }
})();

// Case 4: Backdrop click cancels.
(function caseBackdropClick() {
  var h = freshHarness();
  try {
    h.ns.init();
    var calls = { confirm: 0, cancel: 0 };
    h.ns.requestShare({
      onConfirm: function () { calls.confirm++; },
      onCancel:  function () { calls.cancel++; }
    });
    assertTrue('case4: modal open before backdrop click', modalIsOpen(h));

    var modal = h.doc.getElementById('ora-canvas-share-reminder-modal');
    var backdrop = modal.querySelector('.ora-canvas-share-reminder__backdrop');
    var evt = new h.win.MouseEvent('click', { bubbles: true, cancelable: true });
    backdrop.dispatchEvent(evt);

    assertEqual('case4: backdrop click fires onCancel', calls.cancel, 1);
    assertTrue('case4: backdrop click closes modal', !modalIsOpen(h));
  } finally { teardown(h); }
})();

// Case 5: reset() clears the session flag.
(function caseReset() {
  var h = freshHarness();
  try {
    h.ns.init();
    h.ns.requestShare({ onConfirm: function () {}, onCancel: function () {} });
    clickAction(h, 'confirm');
    assertTrue('case5: reminded after first confirm', h.ns.hasBeenReminded());
    h.ns.reset();
    assertTrue('case5: reset() clears the flag', !h.ns.hasBeenReminded());

    var seenModal = false;
    h.ns.requestShare({
      onConfirm: function () { seenModal = modalIsOpen(h); }
    });
    assertTrue('case5: modal opens again after reset()', modalIsOpen(h));
  } finally { teardown(h); }
})();

// Case 6: Raw window.dispatchEvent flows through the same path.
(function caseRawDispatch() {
  var h = freshHarness();
  try {
    h.ns.init();
    var confirmed = false;
    var detail = {
      intent: 'export',
      path: '/tmp/test.ora-canvas',
      onConfirm: function () { confirmed = true; }
    };
    var evt;
    try {
      evt = new h.win.CustomEvent('ora:canvas-pre-share', { detail: detail });
    } catch (e) {
      evt = h.doc.createEvent('CustomEvent');
      evt.initCustomEvent('ora:canvas-pre-share', false, false, detail);
    }
    h.win.dispatchEvent(evt);
    assertTrue('case6: modal opens via raw dispatch', modalIsOpen(h));
    clickAction(h, 'confirm');
    assertTrue('case6: raw-dispatch onConfirm runs', confirmed === true);
  } finally { teardown(h); }
})();

// Case 7: Init is idempotent.
(function caseInitIdempotent() {
  var h = freshHarness();
  try {
    h.ns.init();
    h.ns.init();
    h.ns.init();
    var modals = h.doc.querySelectorAll('#ora-canvas-share-reminder-modal');
    assertEqual('case7: only one modal element after triple init', modals.length, 1);
  } finally { teardown(h); }
})();

// Case 8: hasBeenReminded() reads from sessionStorage when available.
(function caseStorageReadback() {
  var h = freshHarness();
  try {
    h.ns.init();
    assertTrue('case8: storage initially empty', !h.ns.hasBeenReminded());
    h.ns.requestShare({ onConfirm: function () {} });
    clickAction(h, 'confirm');
    var raw = h.win.sessionStorage.getItem('ora.canvas.shareReminder.acknowledged');
    assertEqual('case8: sessionStorage flag set after confirm', raw, '1');
  } finally { teardown(h); }
})();

// Case 9: Intent string adapts modal copy.
(function caseIntentLabel() {
  var h = freshHarness();
  try {
    h.ns.init();
    h.ns.requestShare({ intent: 'export', onConfirm: function () {} });
    var label = h.doc.querySelector('.ora-canvas-share-reminder__intent');
    assertTrue('case9: intent label rendered', !!label);
    assertTrue('case9: export label says "export"', label && /export/.test(label.textContent));
    clickAction(h, 'confirm');
  } finally { teardown(h); }
})();

// ── summary ----------------------------------------------------------------

process.stdout.write('\n--- summary ---\n');
process.stdout.write('  pass: ' + passCount + '\n');
process.stdout.write('  fail: ' + failCount + '\n');
if (failCount > 0) {
  process.stdout.write('\nfailures:\n');
  failures.forEach(function (f) {
    process.stdout.write('  - ' + f.name + ': ' + f.message + '\n');
  });
  process.exit(1);
}
process.exit(0);
