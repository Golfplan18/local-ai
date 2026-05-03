#!/usr/bin/env node
/* test-ask-ora.js — WP-7.1.5
 *
 * jsdom-driven tests for the Ask Ora trio:
 *   1. ask-ora-router.js — keyword classifier
 *   2. ask-ora-prompt.js — floating prompt panel
 *   3. visual-toolbar-bindings.js — wires tool:ask_ora to the panel and
 *      routes submits to either capability-invocation-ui or /chat.
 *
 * Run:  node ~/ora/server/static/tests/test-ask-ora.js
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var path = require('path');
var fs = require('fs');

var ORA_ROOT = path.resolve(__dirname, '..', '..', '..');
var STATIC_DIR = path.join(ORA_ROOT, 'server', 'static');
var ROUTER_PATH = path.join(STATIC_DIR, 'ask-ora-router.js');
var PROMPT_PATH = path.join(STATIC_DIR, 'ask-ora-prompt.js');
var BINDINGS_PATH = path.join(STATIC_DIR, 'visual-toolbar-bindings.js');
var INVOCATION_UI_PATH = path.join(STATIC_DIR, 'capability-invocation-ui.js');
var CAPABILITIES_PATH = path.join(ORA_ROOT, 'config', 'capabilities.json');
var TOOLBAR_PATH = path.join(STATIC_DIR, 'visual-toolbar.js');
var ICON_RESOLVER_PATH = path.join(STATIC_DIR, 'icon-resolver.js');
var UNIVERSAL_TOOLBAR_PATH = path.join(ORA_ROOT, 'config', 'toolbars', 'universal.toolbar.json');

var JSDOM_PATH = path.join(STATIC_DIR, 'ora-visual-compiler', 'tests', 'node_modules', 'jsdom');
var jsdom;
try {
  jsdom = require(JSDOM_PATH);
} catch (e) {
  console.error('error: jsdom not available at ' + JSDOM_PATH);
  process.exit(2);
}
var JSDOM = jsdom.JSDOM;

// ── runner ──────────────────────────────────────────────────────────────

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
function assertNull(name, val) {
  if (val === null) pass(name);
  else fail(name, 'expected null, got ' + JSON.stringify(val));
}
function assertNotNull(name, val) {
  if (val !== null && val !== undefined) pass(name);
  else fail(name, 'expected non-null, got ' + JSON.stringify(val));
}

// ── per-case fresh harness ──────────────────────────────────────────────

function freshHarness(opts) {
  opts = opts || {};
  // Drop any cached modules so each IIFE re-binds to its own window.
  [ROUTER_PATH, PROMPT_PATH, BINDINGS_PATH, INVOCATION_UI_PATH,
   TOOLBAR_PATH, ICON_RESOLVER_PATH].forEach(function (p) {
    try { delete require.cache[require.resolve(p)]; } catch (e) {}
  });

  var dom = new JSDOM('<!doctype html><html><head></head><body></body></html>', {
    url: 'http://localhost/',
    pretendToBeVisual: true
  });
  var win = dom.window;
  var doc = win.document;

  global.window = win;
  global.document = doc;
  global.HTMLElement = win.HTMLElement;
  global.Element = win.Element;
  global.Event = win.Event;
  global.CustomEvent = win.CustomEvent;
  global.MouseEvent = win.MouseEvent;
  global.KeyboardEvent = win.KeyboardEvent;
  global.requestAnimationFrame = win.requestAnimationFrame || function (fn) { return setTimeout(fn, 0); };

  // Load modules. Order matters: router, capability UI, prompt, bindings.
  if (opts.includeInvocationUI !== false) {
    require(INVOCATION_UI_PATH);
  }
  require(ROUTER_PATH);
  require(PROMPT_PATH);
  require(BINDINGS_PATH);

  return {
    win: win,
    doc: doc,
    Router: win.OraAskOraRouter,
    Prompt: win.OraAskOraPrompt,
    Bindings: win.OraVisualToolbarBindings,
    InvocationUI: win.OraCapabilityInvocationUI || null
  };
}

function teardown(h) {
  try { h.Prompt && h.Prompt.close(); } catch (e) {}
  try { h.win.close(); } catch (e) {}
  delete global.window;
  delete global.document;
  delete global.HTMLElement;
  delete global.Element;
  delete global.Event;
  delete global.CustomEvent;
  delete global.MouseEvent;
  delete global.KeyboardEvent;
}

// ──────────────────────────────────────────────────────────────────────────
// Router tests
// ──────────────────────────────────────────────────────────────────────────

process.stdout.write('\n--- ask-ora router ---\n');

(function caseRouterMappings() {
  var h = freshHarness();
  try {
    var R = h.Router;

    // The plan-stated example.
    var r1 = R.classify("describe what's on the canvas");
    assertNotNull('router: describe → result', r1);
    if (r1) {
      assertEqual('router: describe → image_to_prompt', r1.slot, 'image_to_prompt');
      assertEqual('router: describe → prompt prefilled', r1.prefilled_inputs.prompt,
                  "describe what's on the canvas");
    }

    // critique → image_critique
    var r2 = R.classify('please critique this layout');
    assertEqual('router: critique → image_critique', r2 && r2.slot, 'image_critique');

    // review → image_critique
    var r3 = R.classify('can you review what I drew');
    assertEqual('router: review → image_critique', r3 && r3.slot, 'image_critique');

    // feedback → image_critique
    var r4 = R.classify('I want feedback on the canvas');
    assertEqual('router: feedback → image_critique', r4 && r4.slot, 'image_critique');

    // restyle → image_styles
    var r5 = R.classify('restyle this in watercolor');
    assertEqual('router: restyle → image_styles', r5 && r5.slot, 'image_styles');

    // "in the style of" → image_styles
    var r6 = R.classify('redo it in the style of Monet');
    assertEqual('router: in the style of → image_styles', r6 && r6.slot, 'image_styles');

    // upscale → image_upscales
    var r7 = R.classify('upscale to 4k');
    assertEqual('router: upscale → image_upscales', r7 && r7.slot, 'image_upscales');

    // sharpen → image_upscales
    var r8 = R.classify('sharpen the result');
    assertEqual('router: sharpen → image_upscales', r8 && r8.slot, 'image_upscales');

    // edit → image_edits
    var r9 = R.classify('edit the background');
    assertEqual('router: edit → image_edits', r9 && r9.slot, 'image_edits');

    // change → image_edits
    var r10 = R.classify('change the colors');
    assertEqual('router: change → image_edits', r10 && r10.slot, 'image_edits');

    // remove → image_edits
    var r11 = R.classify('remove the box on the left');
    assertEqual('router: remove → image_edits', r11 && r11.slot, 'image_edits');

    // generate → image_generates
    var r12 = R.classify('generate a sunset');
    assertEqual('router: generate → image_generates', r12 && r12.slot, 'image_generates');

    // create → image_generates
    var r13 = R.classify('create a logo');
    assertEqual('router: create → image_generates', r13 && r13.slot, 'image_generates');

    // draw → image_generates
    var r14 = R.classify('draw a tree');
    assertEqual('router: draw → image_generates', r14 && r14.slot, 'image_generates');

    // Unmapped string → null (prose path)
    var rNone = R.classify('this is just a chat question with no triggers');
    assertNull('router: unmapped → null', rNone);

    // Empty / whitespace → null
    assertNull('router: empty string → null', R.classify(''));
    assertNull('router: whitespace → null', R.classify('   '));
    assertNull('router: non-string → null', R.classify(null));
    assertNull('router: undefined → null', R.classify(undefined));

    // Specific-first ordering: "generate a critique of the canvas" → critique,
    // not generate. The critique rule is declared before generate.
    var rOrder = R.classify('generate a critique of the canvas');
    assertEqual('router: specific-first ordering favors critique', rOrder && rOrder.slot, 'image_critique');
  } finally { teardown(h); }
})();

// ──────────────────────────────────────────────────────────────────────────
// Prompt panel tests
// ──────────────────────────────────────────────────────────────────────────

process.stdout.write('\n--- ask-ora prompt panel ---\n');

(function casePromptMountAndDismiss() {
  var h = freshHarness();
  try {
    var hostEl = h.doc.createElement('button');
    hostEl.id = 'ask-ora-host';
    hostEl.textContent = 'Ask Ora';
    h.doc.body.appendChild(hostEl);

    var submitted = null;
    var ctl = h.Prompt.open({
      hostEl: hostEl,
      onSubmit: function (detail) { submitted = detail; }
    });

    assertTrue('prompt: open returns controller', !!ctl);
    assertTrue('prompt: panel mounted in DOM',
               !!h.doc.querySelector('.ora-ask-ora-prompt'));
    assertTrue('prompt: isOpen() true after open', h.Prompt.isOpen());
    assertTrue('prompt: input present', !!ctl.input);
    assertTrue('prompt: submit button present', !!ctl.submitBtn);

    ctl.destroy();
    assertTrue('prompt: panel removed from DOM after destroy',
               !h.doc.querySelector('.ora-ask-ora-prompt'));
    assertTrue('prompt: isOpen() false after destroy', !h.Prompt.isOpen());
    assertNull('prompt: no submit when destroyed without typing', submitted);
  } finally { teardown(h); }
})();

(function casePromptSubmitDispatch() {
  var h = freshHarness();
  try {
    var hostEl = h.doc.createElement('button');
    h.doc.body.appendChild(hostEl);

    var got = null;
    var ctl = h.Prompt.open({
      hostEl: hostEl,
      onSubmit: function (detail) { got = detail; }
    });

    ctl.input.value = 'describe what is on the canvas';
    var detail = ctl.submit();

    assertNotNull('prompt: submit returns detail', detail);
    if (detail) {
      assertEqual('prompt: submit text matches', detail.text, 'describe what is on the canvas');
    }
    assertNotNull('prompt: onSubmit called with detail', got);
    if (got) {
      assertEqual('prompt: onSubmit text matches', got.text, 'describe what is on the canvas');
    }

    // Panel should auto-close after a successful submit.
    assertTrue('prompt: closed after submit', !h.Prompt.isOpen());
  } finally { teardown(h); }
})();

(function casePromptEmptySubmit() {
  var h = freshHarness();
  try {
    var hostEl = h.doc.createElement('button');
    h.doc.body.appendChild(hostEl);

    var got = null;
    var ctl = h.Prompt.open({
      hostEl: hostEl,
      onSubmit: function (detail) { got = detail; }
    });
    ctl.input.value = '   ';
    var detail = ctl.submit();
    assertNull('prompt: empty submit returns null', detail);
    assertNull('prompt: empty submit does not invoke onSubmit', got);
    assertTrue('prompt: panel still open after empty submit', h.Prompt.isOpen());

    ctl.destroy();
  } finally { teardown(h); }
})();

(function casePromptSnapshotCapture() {
  var h = freshHarness();
  try {
    // Stub OraCanvasSerializer with a deterministic captureFromPanel.
    var fakeSnapshot = { entities: [{ id: 'e1', label: 'box' }], relationships: [] };
    h.win.OraCanvasSerializer = {
      captureFromPanel: function (panel) { return panel ? fakeSnapshot : null; }
    };
    var fakePanel = { userInputLayer: {} };

    var hostEl = h.doc.createElement('button');
    h.doc.body.appendChild(hostEl);

    var got = null;
    var ctl = h.Prompt.open({
      hostEl: hostEl,
      getCanvasPanel: function () { return fakePanel; },
      onSubmit: function (detail) { got = detail; }
    });
    ctl.input.value = 'describe this';
    ctl.submit();

    assertNotNull('prompt: snapshot capture invoked', got);
    if (got) {
      assertEqual('prompt: snapshot text matches', got.text, 'describe this');
      assertTrue('prompt: snapshot is the captured object', got.snapshot === fakeSnapshot);
    }
  } finally { teardown(h); }
})();

// ──────────────────────────────────────────────────────────────────────────
// Bindings tests
// ──────────────────────────────────────────────────────────────────────────

process.stdout.write('\n--- ask-ora toolbar bindings ---\n');

(function caseBindingsAttach() {
  var h = freshHarness();
  try {
    var registry = {};
    h.Bindings.attach(registry, { getHostElement: function () { return h.doc.body; } });
    assertTrue('bindings: tool:ask_ora handler registered',
               typeof registry['tool:ask_ora'] === 'function');
    assertEqual('bindings: ASK_ORA_BINDING constant',
                h.Bindings.ASK_ORA_BINDING, 'tool:ask_ora');
  } finally { teardown(h); }
})();

(function caseBindingsClassifiedSlotPath() {
  var h = freshHarness();
  try {
    var capabilities = JSON.parse(fs.readFileSync(CAPABILITIES_PATH, 'utf8'));
    var dispatchedDetail = null;
    var hostBtn = h.doc.createElement('button');
    h.doc.body.appendChild(hostBtn);

    var fetchCalls = [];
    var fakeFetch = function (url, init) {
      fetchCalls.push({ url: url, init: init });
      return Promise.resolve({ ok: true });
    };

    // Stub the canvas serializer so the snapshot carries an active
    // selection. The bindings auto-fill required image-ref inputs from
    // this; without it, the slot's Run button stays disabled and submit()
    // is a no-op (which would itself be the right UX, but isn't what we're
    // verifying here).
    h.win.OraCanvasSerializer = {
      captureFromPanel: function () {
        return {
          entities: [{ id: 'canvas', label: 'canvas' }],
          relationships: [],
          _activeSelection: 'canvas-bg-1'
        };
      }
    };
    var fakePanel = { userInputLayer: {} };

    var registry = {};
    h.Bindings.attach(registry, {
      getHostElement: function () { return hostBtn; },
      getCanvasPanel: function () { return fakePanel; },
      getCapabilities: function () { return capabilities; },
      fetchFn: fakeFetch,
      onCapabilityDispatch: function (detail) { dispatchedDetail = detail; }
    });

    var handler = registry['tool:ask_ora'];
    assertTrue('bindings: handler is callable', typeof handler === 'function');

    // Simulate the toolbar click that opens the panel.
    handler({}, {}, { currentTarget: hostBtn });
    assertTrue('bindings: prompt panel opened on click', h.Prompt.isOpen());

    var ctl = h.Prompt._getActive();
    assertNotNull('bindings: active controller', ctl);

    // Type a classified prompt and submit. "describe …" should hit
    // image_to_prompt, which is sync. The capability-invocation-ui dispatches
    // a `capability-dispatch` CustomEvent on its host AND calls onDispatch.
    ctl.input.value = 'describe what is on the canvas';
    ctl.submit();

    assertNotNull('bindings: capability dispatch fired', dispatchedDetail);
    if (dispatchedDetail) {
      assertEqual('bindings: dispatched slot is image_to_prompt',
                  dispatchedDetail.slot, 'image_to_prompt');
      // `image_to_prompt` requires an image-ref (the canvas object id);
      // the bindings auto-fill that from snapshot._activeSelection. The
      // slot has no free-text `prompt` field (only target_style), so the
      // user's text doesn't ride along here — the dispatched payload
      // should reflect the slot contract, not the prompt.
      assertTrue('bindings: dispatched inputs include the resolved image ref',
                 dispatchedDetail.inputs && dispatchedDetail.inputs.image === 'canvas-bg-1');
    }
    assertEqual('bindings: classified path did NOT fall through to /chat',
                fetchCalls.length, 0);
  } finally { teardown(h); }
})();

(function caseBindingsProseFallback() {
  var h = freshHarness();
  try {
    var capabilities = JSON.parse(fs.readFileSync(CAPABILITIES_PATH, 'utf8'));
    var hostBtn = h.doc.createElement('button');
    h.doc.body.appendChild(hostBtn);

    var fetchCalls = [];
    var fakeFetch = function (url, init) {
      fetchCalls.push({ url: url, init: init });
      return Promise.resolve({ ok: true });
    };
    var dispatchedDetail = null;

    var registry = {};
    h.Bindings.attach(registry, {
      getHostElement: function () { return hostBtn; },
      getCapabilities: function () { return capabilities; },
      fetchFn: fakeFetch,
      onCapabilityDispatch: function (detail) { dispatchedDetail = detail; }
    });

    registry['tool:ask_ora']({}, {}, { currentTarget: hostBtn });
    var ctl = h.Prompt._getActive();
    ctl.input.value = 'tell me a joke about turtles';  // no trigger words
    ctl.submit();

    // No classification → /chat fallback fires once.
    assertEqual('bindings: prose path fired one /chat request', fetchCalls.length, 1);
    if (fetchCalls.length === 1) {
      assertEqual('bindings: prose URL is /chat', fetchCalls[0].url, '/chat');
      assertEqual('bindings: prose method is POST',
                  fetchCalls[0].init && fetchCalls[0].init.method, 'POST');
      var body = JSON.parse(fetchCalls[0].init.body);
      assertEqual('bindings: prose body.message matches user text',
                  body.message, 'tell me a joke about turtles');
    }
    assertNull('bindings: prose path did NOT fire a slot dispatch', dispatchedDetail);
  } finally { teardown(h); }
})();

(function caseBindingsToggleClose() {
  var h = freshHarness();
  try {
    var hostBtn = h.doc.createElement('button');
    h.doc.body.appendChild(hostBtn);

    var registry = {};
    h.Bindings.attach(registry, {
      getHostElement: function () { return hostBtn; },
      getCapabilities: function () { return { slots: {} }; },
      fetchFn: function () { return Promise.resolve({ ok: true }); }
    });

    var handler = registry['tool:ask_ora'];
    handler({}, {}, { currentTarget: hostBtn });
    assertTrue('bindings: first click opens panel', h.Prompt.isOpen());
    handler({}, {}, { currentTarget: hostBtn });
    assertTrue('bindings: second click closes panel', !h.Prompt.isOpen());
  } finally { teardown(h); }
})();

(function caseBindingsCapabilitiesAbsentFallsBackToProse() {
  var h = freshHarness();
  try {
    var hostBtn = h.doc.createElement('button');
    h.doc.body.appendChild(hostBtn);

    var fetchCalls = [];
    var registry = {};
    h.Bindings.attach(registry, {
      getHostElement: function () { return hostBtn; },
      getCapabilities: function () { return null; },
      fetchFn: function (url, init) { fetchCalls.push({ url: url, init: init }); return Promise.resolve({ ok: true }); }
    });

    registry['tool:ask_ora']({}, {}, { currentTarget: hostBtn });
    var ctl = h.Prompt._getActive();
    ctl.input.value = 'describe the canvas';
    ctl.submit();

    // Even though "describe" classifies to a slot, capabilities is null so
    // we fall back to /chat.
    assertEqual('bindings: missing capabilities → prose fallback fires',
                fetchCalls.length, 1);
  } finally { teardown(h); }
})();

// ── Universal toolbar end-to-end (the binding via the action registry) ──

process.stdout.write('\n--- ask-ora end-to-end via universal toolbar ---\n');

(function caseEndToEndViaToolbar() {
  // Verifies that the universal toolbar's `ask-ora` item, when clicked,
  // resolves through the action registry our bindings populated and
  // opens the prompt panel.
  var h = freshHarness();
  try {
    // Load the toolbar + icon resolver. The toolbar requires icon
    // resolution but we don't need real Lucide icons in jsdom — the
    // resolver's fallback path is fine.
    require(ICON_RESOLVER_PATH);
    require(TOOLBAR_PATH);
    var Toolbar = h.win.OraVisualToolbar;
    assertTrue('e2e: OraVisualToolbar registered', !!Toolbar);

    var toolbarDef = JSON.parse(fs.readFileSync(UNIVERSAL_TOOLBAR_PATH, 'utf8'));
    Toolbar.register(toolbarDef);
    assertTrue('e2e: universal toolbar registered', Toolbar.has('ora-universal'));

    var actionRegistry = {};
    var hostBtnRef = null;  // populated when render mounts the items
    h.Bindings.attach(actionRegistry, {
      getHostElement: function (item, ctx, evt) {
        return (evt && evt.currentTarget) || hostBtnRef;
      },
      getCapabilities: function () { return { slots: {} }; },
      fetchFn: function () { return Promise.resolve({ ok: true }); }
    });

    var ctl = Toolbar.render('ora-universal', {
      doc: h.doc,
      actionRegistry: actionRegistry,
      predicateRegistry: {
        history_has_undo: false,
        history_has_redo: false,
        canvas_has_content: false,
        selection_active: false
      }
    });
    h.doc.body.appendChild(ctl.el);

    // Find the ask-ora button and click it.
    var askOraBtn = ctl.itemEls['ask-ora'];
    assertTrue('e2e: ask-ora button rendered', !!askOraBtn);
    hostBtnRef = askOraBtn;
    var clickEvt = new h.win.MouseEvent('click', { bubbles: true, cancelable: true });
    askOraBtn.dispatchEvent(clickEvt);

    assertTrue('e2e: click on ask-ora opens the prompt panel', h.Prompt.isOpen());
  } finally { teardown(h); }
})();

// ── summary ─────────────────────────────────────────────────────────────

process.stdout.write('\n--- summary ---\n');
process.stdout.write('  ' + passCount + ' passed, ' + failCount + ' failed\n');
if (failCount > 0) {
  process.stdout.write('\nfailures:\n');
  failures.forEach(function (f) {
    process.stdout.write('  - ' + f.name + ': ' + f.message + '\n');
  });
  process.exit(1);
}
process.exit(0);
