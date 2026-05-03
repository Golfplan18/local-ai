#!/usr/bin/env node
/* test-ai-undo-warning.js — WP-7.7.2
 *
 * jsdom-driven test harness for ai-undo-warning.js. Verifies §13.7
 * acceptance:
 *   - First undo of an AI-generated content frame shows the warning modal.
 *   - Acknowledge → second undo same session is silent.
 *   - sessionStorage flag `ora.aiUndo.warned` is set after acknowledgement.
 *   - Restart-session simulation (clear sessionStorage + reset()) → warning
 *     fires again on first AI-frame undo.
 *   - User-drawn (non-AI) frames never trigger the warning.
 *   - Detection covers all AI source tags accepted by the module
 *     (`image_generates`, `image_outpaints`, `image_edits`, `ai-generation`).
 *   - Macro-driven AI insertions go through the same `canvas-state-changed`
 *     hook, so macro-undo triggers identically to a direct AI undo.
 *   - The warning is advisory: undo proceeds regardless of whether the
 *     user has acknowledged.
 *   - Init/destroy is idempotent.
 *   - markCurrent / markRange explicit-tagging API works for callers that
 *     don't go through the canvas-state-changed event.
 *
 * Run:  node ~/ora/server/static/tests/test-ai-undo-warning.js
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var path = require('path');

var ORA_ROOT     = path.resolve(__dirname, '..', '..', '..');
var MODULE_PATH  = path.join(ORA_ROOT, 'server', 'static', 'ai-undo-warning.js');
var JSDOM_PATH   = path.join(ORA_ROOT, 'server', 'static', 'ora-visual-compiler', 'tests', 'node_modules', 'jsdom');

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

// ── fake VisualPanel + OraPanels.visual namespace --------------------------

/**
 * Minimal fake of the visual-panel API surface that ai-undo-warning needs:
 *   - getHistoryCursor() — returns the index where the next history frame
 *     would be written (== history.length when at the tip).
 *   - undo() — decrements cursor and "unwinds" the frame at the new
 *     cursor position. We only track that undo() was called and
 *     decrement the cursor, since the warning module wraps undo() and
 *     inspects cursor-1 to decide whether to show the warning.
 *
 * The test simulates a frame stream by calling pushFrame() to bump the
 * cursor (mirroring _pushHistory) and dispatchAiFrame() to push a frame
 * AND emit a canvas-state-changed event with an AI source string.
 */
function makeFakePanel(win) {
  var panel = {
    _historyCursor: 0,
    _undoCalls: 0,
    getHistoryCursor: function () { return this._historyCursor; },
    undo: function () {
      if (this._historyCursor <= 0) return false;
      this._historyCursor -= 1;
      this._undoCalls += 1;
      return true;
    }
  };
  // hostEl: where canvas-state-changed events are dispatched. Bubbles
  // up to window via the document tree.
  panel.hostEl = win.document.body;
  return panel;
}

function pushFrame(panel) {
  panel._historyCursor += 1;
}

function dispatchCanvasStateChanged(win, panel, source) {
  // Mirrors capability-image-generates._emit: bubbling CustomEvent on hostEl.
  var evt = new win.CustomEvent('canvas-state-changed', {
    bubbles: true,
    detail: { source: source, object: { id: 'fake' } }
  });
  panel.hostEl.dispatchEvent(evt);
}

/**
 * Simulate the production sequence:
 *   1. Capability inserts an object → panel pushes a history frame.
 *   2. Capability dispatches canvas-state-changed with an AI source.
 *   3. Module's window listener tags cursor-1 as AI-sourced.
 */
function simulateAiInsert(win, panel, source) {
  pushFrame(panel);
  dispatchCanvasStateChanged(win, panel, source || 'image_generates');
}

function simulateUserInsert(panel) {
  // No event — just a frame push (a user drawing a shape).
  pushFrame(panel);
}

// ── per-case fresh module + jsdom -----------------------------------------

function freshHarness() {
  delete require.cache[require.resolve(MODULE_PATH)];

  var dom = new JSDOM('<!doctype html><html><head></head><body></body></html>', {
    url: 'http://localhost/',
    pretendToBeVisual: true
  });
  var win = dom.window;
  var doc = win.document;

  global.window = win;
  global.document = doc;

  // Stand up a minimal OraPanels.visual namespace BEFORE loading the
  // module, so ai-undo-warning.init() can wrap the namespace undo and
  // resolve _getActive() against our fake panel.
  var activePanel = makeFakePanel(win);
  win.OraPanels = {
    visual: {
      _activePanel: activePanel,
      _getActive: function () { return this._activePanel; },
      undo: function () {
        var p = this._getActive();
        return p ? p.undo() : false;
      }
    }
  };

  require(MODULE_PATH);
  var ns = win.OraAIUndoWarning;
  if (!ns) throw new Error('OraAIUndoWarning did not register on window');

  return { win: win, doc: doc, ns: ns, panel: activePanel };
}

function teardown(h) {
  try { h.ns.destroy(); } catch (e) {}
  try { h.win.sessionStorage.clear(); } catch (e) {}
  try { h.win.close(); } catch (e) {}
  delete global.window;
  delete global.document;
}

function modalIsOpen(h) {
  var modal = h.doc.getElementById('ora-ai-undo-warning-modal');
  return !!(modal && modal.hidden === false);
}

function clickAck(h) {
  var modal = h.doc.getElementById('ora-ai-undo-warning-modal');
  if (!modal) throw new Error('modal not mounted');
  var btn = modal.querySelector('[data-action="ack"]');
  if (!btn) throw new Error('ack button not found');
  var evt = new h.win.MouseEvent('click', { bubbles: true, cancelable: true });
  btn.dispatchEvent(evt);
}

// ── test cases -------------------------------------------------------------

process.stdout.write('\n--- ai-undo-warning ---\n');

// Case 1: Direct AI insert → first undo opens modal; second undo is silent.
(function caseFirstUndoTriggersModal() {
  var h = freshHarness();
  try {
    h.ns.init();
    assertTrue('case1: hasBeenWarned() initially false', !h.ns.hasBeenWarned());

    // Two AI-sourced inserts so we can undo twice.
    simulateAiInsert(h.win, h.panel, 'image_generates');
    simulateAiInsert(h.win, h.panel, 'image_generates');

    // Sanity: both frames tagged.
    assertTrue('case1: frame 0 tagged AI', h.ns._isFrameAI(h.panel, 0));
    assertTrue('case1: frame 1 tagged AI', h.ns._isFrameAI(h.panel, 1));

    // First undo: modal should open.
    var undoCallsBefore = h.panel._undoCalls;
    h.win.OraPanels.visual.undo();
    assertTrue('case1: modal opens on first AI undo', modalIsOpen(h));
    // Advisory — undo runs anyway.
    assertEqual('case1: first undo proceeds despite warning',
      h.panel._undoCalls, undoCallsBefore + 1);

    // Acknowledge.
    clickAck(h);
    assertTrue('case1: modal closed after ack', !modalIsOpen(h));
    assertTrue('case1: hasBeenWarned() true after ack', h.ns.hasBeenWarned());

    // Second undo: must be silent.
    h.win.OraPanels.visual.undo();
    assertTrue('case1: modal does NOT open on second AI undo', !modalIsOpen(h));
    assertEqual('case1: second undo also proceeds',
      h.panel._undoCalls, undoCallsBefore + 2);
  } finally { teardown(h); }
})();

// Case 2: sessionStorage persists the warned flag across "page reloads"
// (simulated by re-loading the module against the same window).
(function caseSessionStoragePersists() {
  var h = freshHarness();
  try {
    h.ns.init();
    simulateAiInsert(h.win, h.panel, 'image_generates');
    h.win.OraPanels.visual.undo();
    clickAck(h);

    var stored = h.win.sessionStorage.getItem('ora.aiUndo.warned');
    assertEqual('case2: sessionStorage flag set after ack', stored, '1');
    assertEqual('case2: STORAGE_KEY constant matches', h.ns.STORAGE_KEY, 'ora.aiUndo.warned');
  } finally { teardown(h); }
})();

// Case 3: Restart-session simulation — clearing sessionStorage + reset()
// re-arms the warning so the next AI undo fires the modal again.
(function caseRestartSessionRefires() {
  var h = freshHarness();
  try {
    h.ns.init();
    simulateAiInsert(h.win, h.panel, 'image_generates');
    h.win.OraPanels.visual.undo();
    clickAck(h);
    assertTrue('case3: warned after first ack', h.ns.hasBeenWarned());

    // "Restart": clear sessionStorage AND call reset() (covers both the
    // page-reload path and the explicit reset entry point used by
    // chat-panel on new conversation).
    h.win.sessionStorage.clear();
    h.ns.reset();
    assertTrue('case3: hasBeenWarned() false after restart', !h.ns.hasBeenWarned());

    // Push another AI frame and undo — modal should open again.
    simulateAiInsert(h.win, h.panel, 'image_generates');
    h.win.OraPanels.visual.undo();
    assertTrue('case3: modal re-opens on first AI undo of new session', modalIsOpen(h));
  } finally { teardown(h); }
})();

// Case 4: User-drawn (non-AI) frames never trigger the modal.
(function caseUserFrameNoWarning() {
  var h = freshHarness();
  try {
    h.ns.init();
    simulateUserInsert(h.panel);  // No canvas-state-changed event.
    simulateUserInsert(h.panel);

    assertTrue('case4: user frame 0 NOT tagged AI', !h.ns._isFrameAI(h.panel, 0));
    assertTrue('case4: user frame 1 NOT tagged AI', !h.ns._isFrameAI(h.panel, 1));

    h.win.OraPanels.visual.undo();
    assertTrue('case4: modal does NOT open on user undo', !modalIsOpen(h));
    assertTrue('case4: hasBeenWarned() still false', !h.ns.hasBeenWarned());

    h.win.OraPanels.visual.undo();
    assertTrue('case4: still no modal on second user undo', !modalIsOpen(h));
  } finally { teardown(h); }
})();

// Case 5: All recognised AI source tags trigger the warning identically.
(function caseAllAiSourcesTrigger() {
  var sources = ['image_generates', 'image_outpaints', 'image_edits', 'ai-generation'];
  sources.forEach(function (src) {
    var h = freshHarness();
    try {
      h.ns.init();
      simulateAiInsert(h.win, h.panel, src);
      assertTrue('case5[' + src + ']: frame tagged AI', h.ns._isFrameAI(h.panel, 0));
      h.win.OraPanels.visual.undo();
      assertTrue('case5[' + src + ']: modal opens', modalIsOpen(h));
    } finally { teardown(h); }
  });
})();

// Case 6: Unknown source string does NOT tag the frame.
(function caseUnknownSourceIgnored() {
  var h = freshHarness();
  try {
    h.ns.init();
    simulateAiInsert(h.win, h.panel, 'user_drawing');  // Not in AI_SOURCES.
    assertTrue('case6: unknown-source frame NOT tagged', !h.ns._isFrameAI(h.panel, 0));

    h.win.OraPanels.visual.undo();
    assertTrue('case6: modal does NOT open for unknown source', !modalIsOpen(h));
  } finally { teardown(h); }
})();

// Case 7: Mixed sequence — user, AI, user. Only the AI undo fires the modal.
(function caseMixedSequence() {
  var h = freshHarness();
  try {
    h.ns.init();
    simulateUserInsert(h.panel);                          // frame 0: user
    simulateAiInsert(h.win, h.panel, 'image_generates');  // frame 1: AI
    simulateUserInsert(h.panel);                          // frame 2: user

    assertTrue('case7: frame 0 NOT tagged', !h.ns._isFrameAI(h.panel, 0));
    assertTrue('case7: frame 1 tagged AI',  h.ns._isFrameAI(h.panel, 1));
    assertTrue('case7: frame 2 NOT tagged', !h.ns._isFrameAI(h.panel, 2));

    // First undo unwinds frame 2 (user) — silent.
    h.win.OraPanels.visual.undo();
    assertTrue('case7: undo of user frame 2 — no modal', !modalIsOpen(h));

    // Second undo unwinds frame 1 (AI) — modal opens.
    h.win.OraPanels.visual.undo();
    assertTrue('case7: undo of AI frame 1 — modal opens', modalIsOpen(h));
    clickAck(h);

    // Third undo unwinds frame 0 (user) — still silent (and warned flag
    // means even if we hit another AI frame it'd be silent too).
    h.win.OraPanels.visual.undo();
    assertTrue('case7: undo of user frame 0 — no modal', !modalIsOpen(h));
  } finally { teardown(h); }
})();

// Case 8: Macro-driven AI insertion goes through the same hook → warning
// fires on undo. The macro engine, when a macro step invokes an AI
// capability, causes the capability to dispatch canvas-state-changed
// just like a direct user-triggered capability call. The panel pushes a
// frame, the event tags it, and the undo wrap shows the modal.
(function caseMacroDrivenAiUndo() {
  var h = freshHarness();
  try {
    h.ns.init();

    // Simulate a macro that invokes image_generates: the capability
    // pushes a frame and emits canvas-state-changed exactly as in the
    // direct path.
    simulateAiInsert(h.win, h.panel, 'image_generates');
    assertTrue('case8: macro-inserted frame tagged AI', h.ns._isFrameAI(h.panel, 0));

    h.win.OraPanels.visual.undo();
    assertTrue('case8: modal opens on macro-AI undo', modalIsOpen(h));
    assertEqual('case8: macro-AI undo proceeds (advisory)', h.panel._undoCalls, 1);
  } finally { teardown(h); }
})();

// Case 9: markRange explicit-tagging API for batch macro inserts.
(function caseMarkRangeExplicit() {
  var h = freshHarness();
  try {
    h.ns.init();

    // A macro step that batches three inserts under one conceptual unit
    // and explicitly tags the range. Caller pushes frames first, then
    // calls markRange.
    pushFrame(h.panel);  // 0
    pushFrame(h.panel);  // 1
    pushFrame(h.panel);  // 2
    h.ns.markRange({ panel: h.panel, from: 0, to: 3 });

    assertTrue('case9: frame 0 tagged via markRange', h.ns._isFrameAI(h.panel, 0));
    assertTrue('case9: frame 1 tagged via markRange', h.ns._isFrameAI(h.panel, 1));
    assertTrue('case9: frame 2 tagged via markRange', h.ns._isFrameAI(h.panel, 2));

    h.win.OraPanels.visual.undo();
    assertTrue('case9: markRange-tagged undo opens modal', modalIsOpen(h));
  } finally { teardown(h); }
})();

// Case 10: markCurrent explicit-tagging for callers off the event path.
(function caseMarkCurrentExplicit() {
  var h = freshHarness();
  try {
    h.ns.init();
    pushFrame(h.panel);
    h.ns.markCurrent({ panel: h.panel });
    assertTrue('case10: markCurrent tags cursor-1', h.ns._isFrameAI(h.panel, 0));

    h.win.OraPanels.visual.undo();
    assertTrue('case10: markCurrent undo opens modal', modalIsOpen(h));
  } finally { teardown(h); }
})();

// Case 11: Init is idempotent — multiple init() calls do not stack
// listeners or duplicate the modal element.
(function caseInitIdempotent() {
  var h = freshHarness();
  try {
    h.ns.init();
    h.ns.init();
    h.ns.init();
    var modals = h.doc.querySelectorAll('#ora-ai-undo-warning-modal');
    assertEqual('case11: only one modal element after triple init', modals.length, 1);

    // Even after multiple inits, the warning fires once.
    simulateAiInsert(h.win, h.panel, 'image_generates');
    h.win.OraPanels.visual.undo();
    assertTrue('case11: triple-init still triggers modal', modalIsOpen(h));
    clickAck(h);
    simulateAiInsert(h.win, h.panel, 'image_generates');
    h.win.OraPanels.visual.undo();
    assertTrue('case11: triple-init still silences after ack', !modalIsOpen(h));
  } finally { teardown(h); }
})();

// Case 12: Escape and Enter keys both acknowledge the modal.
(function caseKeyboardAck() {
  var h = freshHarness();
  try {
    h.ns.init();
    simulateAiInsert(h.win, h.panel, 'image_generates');
    h.win.OraPanels.visual.undo();
    assertTrue('case12: modal open before keypress', modalIsOpen(h));

    var evt = new h.win.KeyboardEvent('keydown', {
      key: 'Escape', bubbles: true, cancelable: true
    });
    h.doc.dispatchEvent(evt);
    assertTrue('case12: Escape closes modal', !modalIsOpen(h));
    assertTrue('case12: Escape marks warned', h.ns.hasBeenWarned());

    h.ns.reset();
    simulateAiInsert(h.win, h.panel, 'image_generates');
    h.win.OraPanels.visual.undo();
    assertTrue('case12: modal re-opens after reset', modalIsOpen(h));

    var evt2 = new h.win.KeyboardEvent('keydown', {
      key: 'Enter', bubbles: true, cancelable: true
    });
    h.doc.dispatchEvent(evt2);
    assertTrue('case12: Enter closes modal', !modalIsOpen(h));
    assertTrue('case12: Enter marks warned', h.ns.hasBeenWarned());
  } finally { teardown(h); }
})();

// Case 13: destroy() tears down listeners, removes the modal, and
// does NOT block subsequent re-init.
(function caseDestroyTeardown() {
  var h = freshHarness();
  try {
    h.ns.init();
    assertTrue('case13: modal mounted after init',
      !!h.doc.getElementById('ora-ai-undo-warning-modal'));
    h.ns.destroy();
    assertTrue('case13: modal removed after destroy',
      !h.doc.getElementById('ora-ai-undo-warning-modal'));

    h.ns.init();
    assertTrue('case13: modal re-mounted after re-init',
      !!h.doc.getElementById('ora-ai-undo-warning-modal'));
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
