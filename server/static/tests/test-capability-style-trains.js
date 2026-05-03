#!/usr/bin/env node
/* test-capability-style-trains.js — WP-7.3.4b
 *
 * End-to-end test for OraCapabilityStyleTrains. Spins up jsdom,
 * loads the slot wiring against a stub invocation UI, a stub
 * registry, and a mocked fetch, and walks the §13.3 test criterion:
 *
 *   "Train style with 3 reference images; verify async; resulting
 *    adapter appears in image_styles options."
 *
 * Coverage:
 *   1. capability-dispatch for style_trains POSTs to the endpoint
 *      with the slot inputs and returns the server's job dict.
 *   2. Pre-dispatch guardrail rejects < 3 reference images locally.
 *   3. Pending timeline note appears on dispatch.
 *   4. ora:job_status terminal "complete" event for our slot
 *      registers the adapter in OraStyleAdapterRegistry.
 *   5. Registered adapter appears in
 *      OraStyleAdapterRegistry.getStyleReferenceOptions().
 *   6. Adapter id extraction handles string, {version}, {url}, and
 *      list shapes.
 *   7. Slot filter: video_generates job_status frames are ignored.
 *   8. Sync error from server lands as a capability-error event with
 *      the matching common_errors code.
 *   9. Async failure (job.status='failed') surfaces capability-error.
 *  10. registerCompletedJob() rehydrates an already-complete job.
 *
 * Run:  node ~/ora/server/static/tests/test-capability-style-trains.js
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var path = require('path');

// ── jsdom bootstrap (vendored under ora-visual-compiler/tests) ───────────────

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

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body><div id="host"></div></body></html>',
  { pretendToBeVisual: true }
);
var w = dom.window;
global.window = w;
global.document = w.document;
global.HTMLElement = w.HTMLElement;
global.Element = w.Element;
global.Event = w.Event;
global.CustomEvent = w.CustomEvent;
global.requestAnimationFrame = w.requestAnimationFrame || function (fn) { return setTimeout(fn, 0); };

// ── Stub invocation UI ───────────────────────────────────────────────────────

var stubUI = (function () {
  var lastResult = null;
  var lastError = null;
  // Active-controller shape: ._state with inputControls map for the
  // image_styles slot. Tests flip slotName to validate the bridge.
  var active = {
    _state: {
      slotName: 'image_styles',
      inputControls: {
        style_reference: (function () {
          var cur = null;
          return {
            getValue: function () { return cur; },
            setValue: function (v) { cur = v; },
            _peek:    function () { return cur; },
          };
        })(),
      },
    },
    refreshEnabledState: function () { active._refreshed = (active._refreshed || 0) + 1; },
    _refreshed: 0,
  };
  return {
    renderResult: function (p) { lastResult = p; },
    renderError:  function (p) { lastError = p; },
    _getActive:   function () { return active; },
    _peek:        function () { return { lastResult: lastResult, lastError: lastError }; },
    _reset:       function () { lastResult = null; lastError = null; },
    _activeRef:   active,
  };
})();

// Install on window so the module finds it during init.
w.OraCapabilityInvocationUI = stubUI;

// ── Module under test ────────────────────────────────────────────────────────

var WIRING_PATH = path.resolve(__dirname, '..', 'capability-style-trains.js');
require(WIRING_PATH); // attaches to global.window.OraCapabilityStyleTrains
var WIRING = w.OraCapabilityStyleTrains;
var REGISTRY = w.OraStyleAdapterRegistry;

if (!WIRING) { console.error('module did not attach to window'); process.exit(1); }
if (!REGISTRY) { console.error('registry did not attach to window'); process.exit(1); }

// ── Tiny test harness ────────────────────────────────────────────────────────

var failures = 0;
var passed = 0;

function test(name, fn) {
  try {
    var p = fn();
    if (p && typeof p.then === 'function') {
      return p.then(
        function () { console.log('  ok  ' + name); passed++; },
        function (e) { console.log('FAIL  ' + name + ' — ' + (e && e.message || e)); failures++; }
      );
    }
    console.log('  ok  ' + name);
    passed++;
  } catch (e) {
    console.log('FAIL  ' + name + ' — ' + (e && e.message || e));
    failures++;
  }
  return Promise.resolve();
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg || 'assertion failed');
}

function deepEq(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

// ── Helper: build mock fetch ────────────────────────────────────────────────

function mockFetch(handler) {
  return function (url, init) {
    return Promise.resolve(handler(url, init));
  };
}

function jsonResponse(status, body) {
  return {
    status: status,
    json: function () { return Promise.resolve(body); },
  };
}

// ── Helper: build sample reference_images ────────────────────────────────────

function sampleRefs(n) {
  var out = [];
  for (var i = 0; i < n; i++) {
    out.push({
      name: 'ref' + i + '.png',
      mime: 'image/png',
      base64: 'AAAA' + i, // not real PNG bytes; the wiring just passes through
    });
  }
  return out;
}

// ── Run sequence ─────────────────────────────────────────────────────────────

function reset() {
  REGISTRY.clear();
  stubUI._reset();
  stubUI._activeRef._state.slotName = 'image_styles';
  stubUI._activeRef._state.inputControls.style_reference.setValue(null);
  WIRING.destroy();
}

(async function run() {

  // 1. Successful dispatch posts to the endpoint with the inputs and
  //    returns the server's job dict.
  await test('dispatch POSTs to endpoint and returns job', async function () {
    reset();
    var hostEl = w.document.getElementById('host');
    var captured = null;
    var ctl = WIRING.init({
      hostEl: hostEl,
      ui: stubUI,
      fetchImpl: mockFetch(function (url, init) {
        captured = { url: url, body: JSON.parse(init.body) };
        return jsonResponse(200, { job: { id: 'job-1', status: 'queued', capability: 'style_trains' } });
      }),
    });
    var result = await ctl.handleDispatch({
      slot: 'style_trains',
      inputs: {
        reference_images: sampleRefs(3),
        name: 'Watercolor',
        training_depth: 'standard',
      },
    });
    assert(captured.url === '/api/capability/style_trains', 'wrong endpoint: ' + captured.url);
    assert(captured.body.slot === 'style_trains', 'slot not in body');
    assert(captured.body.inputs.name === 'Watercolor', 'name not in body');
    assert(captured.body.inputs.reference_images.length === 3, 'refs not in body');
    assert(result && result.id === 'job-1', 'result.id mismatch');
  });

  // 2. Pre-dispatch guardrail
  await test('rejects < 3 reference images locally', async function () {
    reset();
    var hostEl = w.document.getElementById('host');
    var fetchCalled = false;
    var ctl = WIRING.init({
      hostEl: hostEl,
      ui: stubUI,
      fetchImpl: mockFetch(function () { fetchCalled = true; return jsonResponse(200, {}); }),
    });
    var threw = null;
    try {
      await ctl.handleDispatch({
        slot: 'style_trains',
        inputs: { reference_images: sampleRefs(2), name: 'X' },
      });
    } catch (e) { threw = e; }
    assert(threw && threw.code === 'insufficient_examples', 'expected insufficient_examples');
    assert(!fetchCalled, 'fetch should not have been called');
    assert(stubUI._peek().lastError && stubUI._peek().lastError.code === 'insufficient_examples',
      'UI did not see error');
  });

  // 3. Pending timeline note
  await test('shows pending timeline note on dispatch', async function () {
    reset();
    var hostEl = w.document.getElementById('host');
    // The note attaches to .ora-cap-status; pre-create one so the note has a home.
    hostEl.innerHTML = '<div class="ora-cap-status"></div><div class="ora-cap-result"></div>';
    var ctl = WIRING.init({
      hostEl: hostEl,
      ui: stubUI,
      fetchImpl: mockFetch(function () {
        return jsonResponse(200, { job: { id: 'job-2', status: 'queued', capability: 'style_trains' } });
      }),
    });
    await ctl.handleDispatch({
      slot: 'style_trains',
      inputs: { reference_images: sampleRefs(3), name: 'Y' },
    });
    var note = hostEl.querySelector('.ora-style-trains__note');
    assert(!!note, 'pending note missing');
    assert(note.textContent.indexOf('several minutes') >= 0, 'note text wrong');
  });

  // 4 + 5. Terminal complete registers adapter and surfaces in options.
  await test('terminal complete registers adapter; appears in image_styles options', async function () {
    reset();
    var hostEl = w.document.getElementById('host');
    hostEl.innerHTML = '<div class="ora-cap-status"></div><div class="ora-cap-result"></div>';
    var ctl = WIRING.init({
      hostEl: hostEl,
      ui: stubUI,
      fetchImpl: mockFetch(function () {
        return jsonResponse(200, { job: { id: 'job-3', status: 'queued', capability: 'style_trains' } });
      }),
    });
    await ctl.handleDispatch({
      slot: 'style_trains',
      inputs: { reference_images: sampleRefs(3), name: 'Watercolor' },
    });
    // Simulate the SSE bridge dispatching the terminal event.
    w.dispatchEvent(new w.CustomEvent('ora:job_status', {
      detail: {
        type: 'job_status',
        conversation_id: null,
        job: {
          id: 'job-3',
          capability: 'style_trains',
          status: 'complete',
          result_ref: 'flux-lora-watercolor-v1',
          completed_at: 1234567890,
        },
      },
    }));
    var rec = REGISTRY.get('flux-lora-watercolor-v1');
    assert(rec, 'adapter not registered');
    assert(rec.name === 'Watercolor', 'wrong name on record');
    assert(rec.swatches.length === 3, 'wrong swatch count');
    var opts = REGISTRY.getStyleReferenceOptions();
    var found = opts.filter(function (o) { return o.value === 'flux-lora-watercolor-v1'; })[0];
    assert(found, 'adapter not in style_reference options');
    assert(found.label.indexOf('Watercolor') >= 0, 'label missing name');
    assert(found.kind === 'style_adapter', 'wrong kind');
    // Result UI rendered & card attached
    assert(stubUI._peek().lastResult && stubUI._peek().lastResult.adapterId === 'flux-lora-watercolor-v1',
      'UI did not see result');
    var card = hostEl.querySelector('.ora-style-adapter-card');
    assert(!!card, 'result card not attached');
    var note = hostEl.querySelector('.ora-style-trains__note');
    assert(!note, 'pending note should be hidden after terminal');
  });

  // 6. Adapter id extraction shapes
  await test('extractAdapterId handles all known shapes', function () {
    var fn = WIRING._extractAdapterId;
    assert(fn('plain-id') === 'plain-id');
    assert(fn({ version: 'v-id' }) === 'v-id');
    assert(fn({ id: 'i-id' }) === 'i-id');
    assert(fn({ url: 'https://example.com/lora.safetensors' }) === 'https://example.com/lora.safetensors');
    assert(fn({ weights: 'https://example.com/w.tar' }) === 'https://example.com/w.tar');
    assert(fn(['first-id', 'second']) === 'first-id');
    assert(fn(null) === null);
    assert(fn({}) === null);
  });

  // 7. Slot filter: video_generates events ignored
  await test('ignores ora:job_status frames for other slots', async function () {
    reset();
    var hostEl = w.document.getElementById('host');
    hostEl.innerHTML = '<div class="ora-cap-status"></div><div class="ora-cap-result"></div>';
    WIRING.init({ hostEl: hostEl, ui: stubUI,
      fetchImpl: mockFetch(function () { return jsonResponse(200, {}); }) });
    var sizeBefore = REGISTRY.list().length;
    w.dispatchEvent(new w.CustomEvent('ora:job_status', {
      detail: {
        type: 'job_status',
        job: { id: 'video-1', capability: 'video_generates', status: 'complete', result_ref: 'something' },
      },
    }));
    assert(REGISTRY.list().length === sizeBefore, 'should not register from another slot');
  });

  // 8. Sync error from server
  await test('sync server error surfaces with matching code', async function () {
    reset();
    var hostEl = w.document.getElementById('host');
    var ctl = WIRING.init({
      hostEl: hostEl,
      ui: stubUI,
      fetchImpl: mockFetch(function () {
        return jsonResponse(400, {
          error: { code: 'insufficient_examples', message: 'Need at least 3 references.' },
        });
      }),
    });
    var captured = null;
    hostEl.addEventListener('capability-error', function (e) { captured = e.detail; });
    var threw = null;
    try {
      await ctl.handleDispatch({
        slot: 'style_trains',
        inputs: { reference_images: sampleRefs(3), name: 'X' },
      });
    } catch (e) { threw = e; }
    assert(threw, 'should have thrown');
    assert(captured && captured.code === 'insufficient_examples', 'wrong error code surfaced');
  });

  // 9. Async failure (job.status='failed')
  await test('async failure surfaces capability-error', async function () {
    reset();
    var hostEl = w.document.getElementById('host');
    WIRING.init({ hostEl: hostEl, ui: stubUI,
      fetchImpl: mockFetch(function () { return jsonResponse(200, {}); }) });
    var captured = null;
    hostEl.addEventListener('capability-error', function (e) { captured = e.detail; });
    w.dispatchEvent(new w.CustomEvent('ora:job_status', {
      detail: {
        type: 'job_status',
        job: { id: 'failjob', capability: 'style_trains', status: 'failed', error: 'provider error' },
      },
    }));
    assert(captured && captured.code === 'training_failed', 'expected training_failed');
    assert(captured.message.indexOf('provider error') >= 0, 'message lost');
  });

  // 10. registerCompletedJob rehydration
  await test('registerCompletedJob rehydrates an already-complete job', function () {
    reset();
    var hostEl = w.document.getElementById('host');
    var ctl = WIRING.init({ hostEl: hostEl, ui: stubUI,
      fetchImpl: mockFetch(function () { return jsonResponse(200, {}); }) });
    var rec = ctl.registerCompletedJob({
      id: 'rehydrated-1',
      capability: 'style_trains',
      status: 'complete',
      result_ref: 'rehydrated-adapter-v1',
      completed_at: 1700000000,
    }, {
      name: 'Rehydrated',
      referenceImages: sampleRefs(3),
      training_depth: 'deep',
    });
    assert(rec, 'registerCompletedJob returned null');
    assert(REGISTRY.get('rehydrated-adapter-v1'), 'adapter not in registry');
    assert(REGISTRY.get('rehydrated-adapter-v1').name === 'Rehydrated');
  });

  // 11. Adapter selection bridge: clicking "Use" pipes id to active image_styles
  await test('selecting adapter pipes id into active image_styles invocation', function () {
    reset();
    var hostEl = w.document.getElementById('host');
    hostEl.innerHTML = '<div class="ora-cap-status"></div><div class="ora-cap-result"></div>';
    WIRING.init({ hostEl: hostEl, ui: stubUI,
      fetchImpl: mockFetch(function () { return jsonResponse(200, {}); }) });
    // Plant a record + simulate selection via the public helper.
    REGISTRY.add({ id: 'adapter-2', name: 'Pop Art', swatches: [], created_at: 1 });
    WIRING._selectAdapter('adapter-2');
    var ctrl = stubUI._activeRef._state.inputControls.style_reference;
    assert(ctrl._peek() === 'adapter-2', 'image_styles input did not receive adapter id');
  });

  // 12. Selection bridge no-op when active slot != image_styles
  await test('selection bridge does not touch unrelated slots', function () {
    reset();
    var hostEl = w.document.getElementById('host');
    WIRING.init({ hostEl: hostEl, ui: stubUI,
      fetchImpl: mockFetch(function () { return jsonResponse(200, {}); }) });
    stubUI._activeRef._state.slotName = 'image_generates';
    var ctrl = stubUI._activeRef._state.inputControls.style_reference;
    ctrl.setValue('preexisting');
    REGISTRY.add({ id: 'adapter-3', name: 'X', swatches: [], created_at: 1 });
    WIRING._selectAdapter('adapter-3');
    assert(ctrl._peek() === 'preexisting', 'unrelated slot was clobbered');
  });

  // ── Summary ──────────────────────────────────────────────────────────────
  console.log('\n' + passed + ' passed, ' + failures + ' failed');
  process.exit(failures === 0 ? 0 : 1);
})().catch(function (e) {
  console.error('runner error', e);
  process.exit(1);
});
