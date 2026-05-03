#!/usr/bin/env node
/* test-opt-in-tutorial.js — WP-7.7.3
 *
 * jsdom-driven test harness for opt-in-tutorial.js. Verifies §13.7 acceptance:
 *   - First open with no localStorage flags surfaces the "Show me around" button.
 *   - Clicking the button starts the walkthrough (backdrop + first step card).
 *   - Each Next advances through the STEPS sequence; final Next sets `completed`.
 *   - Skip dismisses the whole sequence and sets `dismissed`.
 *   - Re-mounting after dismissal does NOT surface the button (flag honoured).
 *   - Re-mounting after completion does NOT surface the button (flag honoured).
 *   - OraTutorial.reset() clears both flags so the button reappears next mount.
 *   - The lifecycle hook patches VisualPanel.prototype.init exactly once.
 *   - The launcher's "x" close button dismisses without running the tour.
 *   - Escape during the tour aborts and sets `dismissed`.
 *
 * Run:  node ~/ora/server/static/tests/test-opt-in-tutorial.js
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var path = require('path');

var ORA_ROOT = path.resolve(__dirname, '..', '..', '..');
var MODULE_PATH = path.join(ORA_ROOT, 'server', 'static', 'opt-in-tutorial.js');
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

// ── mock VisualPanel + harness --------------------------------------------
//
// The module patches `window.VisualPanel.prototype.init`, so the harness needs
// a constructor on the window before the IIFE runs. We install a minimal stub
// that mimics the production panel surface the tutorial actually touches:
//   - `panel.el`               : the host element used as positioning context.
//   - `panel.init()`           : returns `this`; the module wraps this to mount.
//   - `panel._oraTutorialMounted` flag: written by the module; we read it.
//
// We deliberately drive `requestAnimationFrame` synchronously so the launcher
// is in the DOM by the time `init()` returns (the module schedules the mount
// inside an raf callback).

function installMockVisualPanel(win) {
  function VisualPanel(host, opts) {
    this.el = host;
    this.opts = opts || {};
  }
  VisualPanel.prototype.init = function () {
    // No-op original; the tutorial's patch wraps this.
    return this;
  };
  win.VisualPanel = VisualPanel;

  // Flush rAF synchronously so the launcher mount completes before init() returns.
  win.requestAnimationFrame = function (fn) {
    try { fn(0); } catch (_) {}
    return 0;
  };
}

function freshHarness() {
  // Drop any cached module so the IIFE re-binds to the new window.
  delete require.cache[require.resolve(MODULE_PATH)];

  var dom = new JSDOM(
    '<!doctype html><html><head></head><body><div id="host" style="width:800px;height:600px;"></div></body></html>',
    { url: 'http://localhost/', pretendToBeVisual: true }
  );
  var win = dom.window;
  var doc = win.document;

  // Map jsdom globals so the IIFE's `typeof window/document` checks succeed.
  global.window = win;
  global.document = doc;

  // Mock VisualPanel BEFORE requiring the module so the lifecycle hook lands.
  installMockVisualPanel(win);

  // Load the module — it self-registers OraTutorial on global.window.
  require(MODULE_PATH);

  if (!win.OraTutorial) throw new Error('OraTutorial did not register on window');
  if (!win.VisualPanel.prototype.__oraTutorialPatched) {
    throw new Error('VisualPanel.prototype.init was not patched by the module');
  }

  var host = doc.getElementById('host');
  var panel = new win.VisualPanel(host, { id: 'test' });
  panel.init();

  return { win: win, doc: doc, panel: panel, host: host, ns: win.OraTutorial };
}

function teardown(h) {
  try { h.win.localStorage.clear(); } catch (_) {}
  try { h.win.close(); } catch (_) {}
  delete global.window;
  delete global.document;
}

// ── DOM helpers ------------------------------------------------------------

function launcherEl(h) {
  return h.host.querySelector('.ora-tutorial-launcher');
}

function cardEl(h) {
  return h.doc.querySelector('.ora-tutorial-card');
}

function backdropEl(h) {
  return h.doc.querySelector('.ora-tutorial-backdrop');
}

function ringEl(h) {
  return h.doc.querySelector('.ora-tutorial-ring');
}

function clickEl(h, el) {
  var evt = new h.win.MouseEvent('click', { bubbles: true, cancelable: true });
  el.dispatchEvent(evt);
}

function pressKey(h, key) {
  var evt = new h.win.KeyboardEvent('keydown', { key: key, bubbles: true, cancelable: true });
  h.win.dispatchEvent(evt);
}

function clickNext(h) {
  var card = cardEl(h);
  if (!card) throw new Error('no card mounted');
  var btn = card.querySelector('.ora-tutorial-next');
  if (!btn) throw new Error('next button not found');
  clickEl(h, btn);
}

function clickSkip(h) {
  var card = cardEl(h);
  if (!card) throw new Error('no card mounted');
  var btn = card.querySelector('.ora-tutorial-skip');
  if (!btn) throw new Error('skip button not found');
  clickEl(h, btn);
}

function clickLauncherBody(h) {
  var btn = launcherEl(h);
  if (!btn) throw new Error('launcher not mounted');
  // The launcher delegates: clicking the .ora-tutorial-launcher__close span
  // triggers dismissal; clicking elsewhere triggers launch. Click the label.
  var label = btn.querySelector('.ora-tutorial-launcher__label');
  if (!label) throw new Error('launcher label not found');
  clickEl(h, label);
}

function clickLauncherClose(h) {
  var btn = launcherEl(h);
  if (!btn) throw new Error('launcher not mounted');
  var x = btn.querySelector('.ora-tutorial-launcher__close');
  if (!x) throw new Error('launcher close span not found');
  clickEl(h, x);
}

// Re-mount: the tutorial mounts once per panel instance (idempotent guard via
// `_oraTutorialMounted`). To simulate a fresh "reopen", we construct a NEW
// panel against the same host; the module's mount path runs again because
// each panel has its own `_oraTutorialMounted` flag.
function reopenPanel(h) {
  // Clear any DOM left from a previous mount so we can detect (or not) the
  // launcher cleanly on the new panel.
  var existing = launcherEl(h);
  if (existing && existing.parentNode) existing.parentNode.removeChild(existing);

  var panel = new h.win.VisualPanel(h.host, { id: 'reopen' });
  panel.init();
  h.panel = panel;
  return panel;
}

// ── test cases -------------------------------------------------------------

process.stdout.write('\n--- opt-in-tutorial ---\n');

// Case 1: First open with empty localStorage → launcher visible.
(function caseFirstOpenLauncher() {
  var h = freshHarness();
  try {
    var btn = launcherEl(h);
    assertTrue('case1: launcher mounted on first open', !!btn);
    assertTrue('case1: launcher labelled "Show me around"',
      btn && /Show me around/.test(btn.textContent));
    assertTrue('case1: isFirstOpen() reports true', h.ns.isFirstOpen() === true);
    assertEqual('case1: no card yet (tour not started)', cardEl(h), null);
    assertEqual('case1: no backdrop yet', backdropEl(h), null);
  } finally { teardown(h); }
})();

// Case 2: Click launcher → walkthrough starts (backdrop + first step card).
(function caseClickStartsWalkthrough() {
  var h = freshHarness();
  try {
    clickLauncherBody(h);
    assertTrue('case2: backdrop appears after click', !!backdropEl(h));
    assertTrue('case2: card appears after click', !!cardEl(h));

    var card = cardEl(h);
    var title = card.querySelector('#ora-tutorial-title');
    assertTrue('case2: first step title rendered',
      title && title.textContent === h.ns._STEPS[0].title);

    // Counter shows "Step 1 of N".
    var counter = card.querySelector('div');  // counter is first child div
    assertTrue('case2: step counter says "Step 1 of N"',
      counter && /Step 1 of \d+/.test(counter.textContent));

    // Launcher is removed once the tour starts.
    assertEqual('case2: launcher removed once tour starts', launcherEl(h), null);
  } finally { teardown(h); }
})();

// Case 3: Each Next advances through every STEP; final Next sets `completed`.
(function caseNextAdvancesThroughAllSteps() {
  var h = freshHarness();
  try {
    var totalSteps = h.ns._STEPS.length;
    assertTrue('case3: STEPS array non-empty', totalSteps > 1);

    clickLauncherBody(h);
    // Click Next (totalSteps - 1) times → we should be on the last step.
    for (var i = 0; i < totalSteps - 1; i++) {
      var card = cardEl(h);
      var titleEl = card.querySelector('#ora-tutorial-title');
      assertEqual('case3: step ' + (i + 1) + ' title matches',
        titleEl && titleEl.textContent, h.ns._STEPS[i].title);
      clickNext(h);
    }
    // Now on final step.
    var finalCard = cardEl(h);
    var finalTitle = finalCard.querySelector('#ora-tutorial-title');
    assertEqual('case3: final step title matches',
      finalTitle && finalTitle.textContent, h.ns._STEPS[totalSteps - 1].title);
    var finalNext = finalCard.querySelector('.ora-tutorial-next');
    assertEqual('case3: final-step button labelled "Done"',
      finalNext && finalNext.textContent, 'Done');

    // Click Done → tour ends, completed flag set, no dismissed flag.
    clickEl(h, finalNext);
    assertEqual('case3: card removed after Done', cardEl(h), null);
    assertEqual('case3: backdrop removed after Done', backdropEl(h), null);
    assertEqual('case3: tutorial_completed flag set',
      h.win.localStorage.getItem(h.ns._KEY_COMPLETED), '1');
    assertEqual('case3: tutorial_dismissed flag NOT set',
      h.win.localStorage.getItem(h.ns._KEY_DISMISSED), null);
  } finally { teardown(h); }
})();

// Case 4: Skip dismisses the whole sequence (regardless of step).
(function caseSkipDismisses() {
  var h = freshHarness();
  try {
    clickLauncherBody(h);
    clickNext(h);  // advance to step 2
    clickNext(h);  // advance to step 3
    var card = cardEl(h);
    assertTrue('case4: card present mid-tour', !!card);

    clickSkip(h);
    assertEqual('case4: card removed after Skip', cardEl(h), null);
    assertEqual('case4: backdrop removed after Skip', backdropEl(h), null);
    assertEqual('case4: ring removed after Skip', ringEl(h), null);
    assertEqual('case4: tutorial_dismissed flag set',
      h.win.localStorage.getItem(h.ns._KEY_DISMISSED), '1');
    assertEqual('case4: tutorial_completed flag NOT set',
      h.win.localStorage.getItem(h.ns._KEY_COMPLETED), null);
  } finally { teardown(h); }
})();

// Case 5: After dismissal, re-mounting a panel does NOT surface the launcher.
(function caseLauncherAbsentAfterDismiss() {
  var h = freshHarness();
  try {
    clickLauncherBody(h);
    clickSkip(h);
    assertEqual('case5: dismissed flag set after skip',
      h.win.localStorage.getItem(h.ns._KEY_DISMISSED), '1');
    assertTrue('case5: isFirstOpen() reports false after dismiss',
      h.ns.isFirstOpen() === false);

    reopenPanel(h);
    assertEqual('case5: launcher absent on re-mount after dismiss',
      launcherEl(h), null);
  } finally { teardown(h); }
})();

// Case 6: After completion, re-mounting a panel does NOT surface the launcher.
(function caseLauncherAbsentAfterComplete() {
  var h = freshHarness();
  try {
    clickLauncherBody(h);
    var totalSteps = h.ns._STEPS.length;
    for (var i = 0; i < totalSteps; i++) clickNext(h);
    assertEqual('case6: completed flag set after full tour',
      h.win.localStorage.getItem(h.ns._KEY_COMPLETED), '1');
    assertTrue('case6: isFirstOpen() reports false after complete',
      h.ns.isFirstOpen() === false);

    reopenPanel(h);
    assertEqual('case6: launcher absent on re-mount after complete',
      launcherEl(h), null);
  } finally { teardown(h); }
})();

// Case 7: OraTutorial.reset() clears both flags; launcher reappears next mount.
(function caseResetClearsFlags() {
  var h = freshHarness();
  try {
    clickLauncherBody(h);
    clickSkip(h);
    assertEqual('case7: dismissed flag set',
      h.win.localStorage.getItem(h.ns._KEY_DISMISSED), '1');

    h.ns.reset();
    assertEqual('case7: dismissed flag cleared by reset()',
      h.win.localStorage.getItem(h.ns._KEY_DISMISSED), null);
    assertEqual('case7: completed flag cleared by reset()',
      h.win.localStorage.getItem(h.ns._KEY_COMPLETED), null);
    assertTrue('case7: isFirstOpen() reports true after reset()',
      h.ns.isFirstOpen() === true);

    reopenPanel(h);
    assertTrue('case7: launcher reappears on re-mount after reset',
      !!launcherEl(h));
  } finally { teardown(h); }
})();

// Case 8: Lifecycle hook is idempotent — patching is one-shot.
(function caseLifecycleHookIdempotent() {
  var h = freshHarness();
  try {
    assertEqual('case8: __oraTutorialPatched flag set',
      h.win.VisualPanel.prototype.__oraTutorialPatched, true);

    // Re-loading the module on the SAME window should not re-wrap init.
    var initBefore = h.win.VisualPanel.prototype.init;
    delete require.cache[require.resolve(MODULE_PATH)];
    require(MODULE_PATH);
    var initAfter = h.win.VisualPanel.prototype.init;
    assertEqual('case8: init not re-wrapped on second load', initAfter, initBefore);
  } finally { teardown(h); }
})();

// Case 9: Launcher's close (×) span dismisses without launching the tour.
(function caseLauncherCloseSpan() {
  var h = freshHarness();
  try {
    clickLauncherClose(h);
    assertEqual('case9: launcher removed after × click',
      launcherEl(h), null);
    assertEqual('case9: card NOT mounted (tour did not start)',
      cardEl(h), null);
    assertEqual('case9: dismissed flag set by × click',
      h.win.localStorage.getItem(h.ns._KEY_DISMISSED), '1');

    reopenPanel(h);
    assertEqual('case9: launcher absent on re-mount after × dismiss',
      launcherEl(h), null);
  } finally { teardown(h); }
})();

// Case 10: Escape during the tour aborts and sets `dismissed`.
(function caseEscapeAbortsTour() {
  var h = freshHarness();
  try {
    clickLauncherBody(h);
    clickNext(h);  // advance past first step so we know mid-tour Esc works
    assertTrue('case10: card present before Escape', !!cardEl(h));

    pressKey(h, 'Escape');
    assertEqual('case10: card removed after Escape', cardEl(h), null);
    assertEqual('case10: backdrop removed after Escape', backdropEl(h), null);
    assertEqual('case10: dismissed flag set by Escape',
      h.win.localStorage.getItem(h.ns._KEY_DISMISSED), '1');
    assertEqual('case10: completed flag NOT set by Escape',
      h.win.localStorage.getItem(h.ns._KEY_COMPLETED), null);
  } finally { teardown(h); }
})();

// Case 11: OraTutorial public surface exposes the documented API.
(function casePublicSurface() {
  var h = freshHarness();
  try {
    assertTrue('case11: OraTutorial.reset is a function',
      typeof h.ns.reset === 'function');
    assertTrue('case11: OraTutorial.run is a function',
      typeof h.ns.run === 'function');
    assertTrue('case11: OraTutorial.isFirstOpen is a function',
      typeof h.ns.isFirstOpen === 'function');
    assertTrue('case11: OraTutorial._STEPS is an array',
      Array.isArray(h.ns._STEPS));
    assertEqual('case11: KEY_DISMISSED matches documented value',
      h.ns._KEY_DISMISSED, 'ora.tutorial.dismissed');
    assertEqual('case11: KEY_COMPLETED matches documented value',
      h.ns._KEY_COMPLETED, 'ora.tutorial.completed');
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
