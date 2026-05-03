#!/usr/bin/env node
/* test-capability-image-generates.js — WP-7.3.3a
 *
 * End-to-end test for OraCapabilityImageGenerates. Spins up jsdom,
 * loads the slot wiring against a stub VisualPanel and a mocked
 * fetch implementation, and walks the §13.3 test criterion:
 *
 *   "Live call (or mocked) with prompt 'a red square'; verify image
 *    arrives, lands on canvas, has correct image data."
 *
 * Coverage:
 *   1. capability-dispatch for image_generates triggers a POST to the
 *      configured endpoint with the slot inputs in the body.
 *   2. Server's base64 image lands as a canvas-state image object with
 *      the correct mime_type, encoding, raw base64 data, and
 *      schema-valid kind/layer.
 *   3. Visual panel's insertImageObject is invoked with the canvas
 *      object (preferred path).
 *   4. canvas-state-changed fires with the new object so autosave
 *      (WP-7.4.8) can persist it.
 *   5. capability-result fires so the invocation UI clears its
 *      spinner.
 *   6. Selected-anchor placement: when the panel reports a selection,
 *      the image is centred there instead of canvas centre.
 *   7. Aspect-ratio routing: a 16:9 input produces a wider object.
 *   8. Error mapping: HTTP 429 lands as quota_exceeded with a
 *      capability-error event and a renderError call on the UI.
 *   9. Slot filter: image_edits dispatches do not trigger this module.
 *  10. buildCanvasObject schema invariants (id, kind, layer,
 *      image_data shape).
 *
 * Run:  node ~/ora/server/static/tests/test-capability-image-generates.js
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var path = require('path');
var fs = require('fs');

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
  console.error('  install via: cd ' + path.dirname(COMPILER_TEST_NODE_MODULES) + ' && npm install');
  process.exit(2);
}

var dom = new jsdom.JSDOM('<!doctype html><html><body><div id="host"></div></body></html>', {
  pretendToBeVisual: true,
});

var w = dom.window;
global.window = w;
global.document = w.document;
global.HTMLElement = w.HTMLElement;
global.Element = w.Element;
global.Event = w.Event;
global.CustomEvent = w.CustomEvent;
global.requestAnimationFrame = w.requestAnimationFrame || function (fn) { return setTimeout(fn, 0); };
// Polyfill atob / Blob from the jsdom window if Node doesn't expose them
// at the global scope (Node ≥ 18 exposes both globally; jsdom defines them
// on window).
if (typeof global.atob === 'undefined' && typeof w.atob === 'function') global.atob = w.atob.bind(w);
if (typeof global.Blob === 'undefined' && typeof w.Blob === 'function') global.Blob = w.Blob;
if (typeof global.File === 'undefined' && typeof w.File === 'function') global.File = w.File;

// ── Module under test ────────────────────────────────────────────────────────

var WIRING_PATH = path.resolve(__dirname, '..', 'capability-image-generates.js');
require(WIRING_PATH);  // attaches to global.window.OraCapabilityImageGenerates
var WIRING = w.OraCapabilityImageGenerates;
if (!WIRING) {
  console.error('error: OraCapabilityImageGenerates did not register on window');
  process.exit(2);
}

// ── Test harness ─────────────────────────────────────────────────────────────

var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? '  — ' + detail : ''));
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

function _resetHost() {
  if (WIRING._getActive()) WIRING.destroy();
  var host = w.document.getElementById('host');
  while (host.firstChild) host.removeChild(host.firstChild);
  return host;
}

// A 1×1 red PNG, base64-encoded. Standing in for the "red square" image
// the §13.3 test brief asks for.
var RED_SQUARE_B64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=';

function _stubVisualPanel(opts) {
  opts = opts || {};
  var stub = {
    inserted: [],
    attached: [],
    selectedAnchor: opts.selectedAnchor || null,
    selectedShapeIds: opts.selectedShapeIds || [],
    selectionBBox: opts.selectionBBox || null,
  };
  if (opts.expose !== false) {
    stub.insertImageObject = function (obj) { stub.inserted.push(obj); return true; };
  }
  if (opts.exposeAttach) {
    stub.attachImage = function (file) { stub.attached.push(file); return Promise.resolve(file); };
  }
  if (opts.selectedAnchor) {
    stub.getSelectionAnchor = function () { return opts.selectedAnchor; };
  }
  if (opts.selectedShapeIds) {
    stub.getSelectedShapeIds = function () { return opts.selectedShapeIds; };
    if (opts.selectionBBox) {
      stub._computeSelectionBBox = function () { return opts.selectionBBox; };
    }
  }
  return stub;
}

function _mockFetchOk(base64, mimeType, provider) {
  var calls = [];
  var fn = function (url, init) {
    calls.push({ url: url, init: init });
    var bodyPayload = init && init.body ? JSON.parse(init.body) : null;
    return Promise.resolve({
      status: 200,
      ok: true,
      json: function () {
        return Promise.resolve({
          image: {
            data: base64,
            mime_type: mimeType || 'image/png',
          },
          provider: provider || 'openai',
          metadata: { _echo: bodyPayload },
        });
      },
    });
  };
  fn.calls = calls;
  return fn;
}

function _mockFetchErr(status, code, message) {
  var calls = [];
  var fn = function (url, init) {
    calls.push({ url: url, init: init });
    return Promise.resolve({
      status: status,
      ok: false,
      json: function () {
        return Promise.resolve({
          error: { code: code, message: message },
        });
      },
    });
  };
  fn.calls = calls;
  return fn;
}

// ── Tests ────────────────────────────────────────────────────────────────────

async function testHappyPath_RedSquare() {
  var host = _resetHost();
  var panel = _stubVisualPanel();
  var fetchImpl = _mockFetchOk(RED_SQUARE_B64, 'image/png', 'openai');

  var ui = { renderResult: function (p) { ui._lastResult = p; }, renderError: function (p) { ui._lastError = p; } };

  var resultEvent = null;
  var stateEvent = null;
  host.addEventListener('capability-result', function (e) { resultEvent = e.detail; });
  host.addEventListener('canvas-state-changed', function (e) { stateEvent = e.detail; });

  var ctl = WIRING.init({
    hostEl:      host,
    visualPanel: panel,
    fetchImpl:   fetchImpl,
    ui:          ui,
  });

  var detail = {
    slot:    'image_generates',
    inputs:  { prompt: 'a red square', aspect_ratio: '1:1' },
    execution_pattern: 'sync',
  };

  await ctl.handleDispatch(detail);

  record('fetch was POSTed to the default endpoint',
    fetchImpl.calls.length === 1
    && fetchImpl.calls[0].url === WIRING.DEFAULT_ENDPOINT
    && fetchImpl.calls[0].init && fetchImpl.calls[0].init.method === 'POST',
    fetchImpl.calls.length ? JSON.stringify(fetchImpl.calls[0].url) : 'no calls');

  var sentBody = fetchImpl.calls[0] ? JSON.parse(fetchImpl.calls[0].init.body) : null;
  record('request body carries slot + inputs',
    sentBody && sentBody.slot === 'image_generates' && sentBody.inputs && sentBody.inputs.prompt === 'a red square',
    sentBody ? JSON.stringify(sentBody) : 'no body');

  record('image landed on canvas via insertImageObject',
    panel.inserted.length === 1,
    'inserted=' + panel.inserted.length);

  var obj = panel.inserted[0];
  record('canvas object has kind=image',
    obj && obj.kind === 'image',
    obj ? obj.kind : 'no obj');
  record('canvas object lives on user_input layer',
    obj && obj.layer === WIRING.USER_INPUT_LAYER_ID,
    obj ? obj.layer : 'no obj');
  record('canvas object has non-empty id',
    obj && typeof obj.id === 'string' && obj.id.length > 0,
    obj ? obj.id : 'no obj');
  record('image_data carries the raw base64 (matches red square)',
    obj && obj.image_data && obj.image_data.data === RED_SQUARE_B64,
    obj && obj.image_data ? (obj.image_data.data || '').slice(0, 12) + '…' : 'no image_data');
  record('image_data.mime_type matches schema pattern',
    obj && obj.image_data && /^image\//.test(obj.image_data.mime_type),
    obj && obj.image_data ? obj.image_data.mime_type : 'no mime');
  record('image_data.encoding is base64',
    obj && obj.image_data && obj.image_data.encoding === 'base64',
    obj && obj.image_data ? obj.image_data.encoding : 'no encoding');
  record('canvas object width/height match 1:1 default (1024×1024)',
    obj && obj.width === 1024 && obj.height === 1024,
    obj ? (obj.width + 'x' + obj.height) : 'no obj');

  record('capability-result event fired with canvasObject',
    resultEvent && resultEvent.canvasObject && resultEvent.canvasObject.id === obj.id,
    resultEvent ? JSON.stringify(Object.keys(resultEvent)) : 'no event');
  record('capability-result includes a data: URL preview',
    resultEvent && typeof resultEvent.imageDataUrl === 'string'
      && resultEvent.imageDataUrl.indexOf('data:image/') === 0,
    resultEvent ? (resultEvent.imageDataUrl || '').slice(0, 22) + '…' : 'no event');

  record('UI.renderResult was invoked',
    ui._lastResult && ui._lastResult.canvasObject && ui._lastResult.canvasObject.id === obj.id,
    ui._lastResult ? 'ok' : 'not invoked');

  record('canvas-state-changed event fired with the new object',
    stateEvent && stateEvent.source === 'image_generates' && stateEvent.object && stateEvent.object.id === obj.id,
    stateEvent ? JSON.stringify(Object.keys(stateEvent)) : 'no event');
}

async function testAnchorPlacement() {
  var host = _resetHost();
  // Panel reports an explicit anchor at (3000, 4500) in canvas coords.
  var panel = _stubVisualPanel({
    selectedAnchor: { x: 3000, y: 4500 },
  });
  var fetchImpl = _mockFetchOk(RED_SQUARE_B64, 'image/png', 'openai');

  var ctl = WIRING.init({
    hostEl: host,
    visualPanel: panel,
    fetchImpl: fetchImpl,
  });

  await ctl.handleDispatch({
    slot:   'image_generates',
    inputs: { prompt: 'a red square', aspect_ratio: '1:1' },
  });

  var obj = panel.inserted[0];
  // 1024×1024 centred on (3000, 4500) → top-left at (3000-512, 4500-512).
  record('selected anchor centres the image (x)',
    obj && obj.x === 3000 - 512,
    obj ? obj.x : 'no obj');
  record('selected anchor centres the image (y)',
    obj && obj.y === 4500 - 512,
    obj ? obj.y : 'no obj');
}

async function testAnchorFromSelectionBBox() {
  var host = _resetHost();
  // Panel exposes the legacy selected-shapes API (no getSelectionAnchor).
  var panel = _stubVisualPanel({
    selectedShapeIds: ['rect-1'],
    selectionBBox: { x: 100, y: 200, width: 300, height: 400 },
  });
  // Strip the explicit-anchor method so we exercise the fallback path.
  delete panel.getSelectionAnchor;

  var fetchImpl = _mockFetchOk(RED_SQUARE_B64, 'image/png', 'openai');
  var ctl = WIRING.init({ hostEl: host, visualPanel: panel, fetchImpl: fetchImpl });
  await ctl.handleDispatch({
    slot:   'image_generates',
    inputs: { prompt: 'a red square', aspect_ratio: '1:1' },
  });

  // BBox centre = (250, 400). 1024×1024 → top-left at (250-512, 400-512).
  var obj = panel.inserted[0];
  record('legacy selection bbox falls back to centre as anchor',
    obj && obj.x === 250 - 512 && obj.y === 400 - 512,
    obj ? (obj.x + ',' + obj.y) : 'no obj');
}

async function testAspectRatioRouting() {
  var host = _resetHost();
  var panel = _stubVisualPanel();
  var fetchImpl = _mockFetchOk(RED_SQUARE_B64, 'image/png', 'openai');
  var ctl = WIRING.init({ hostEl: host, visualPanel: panel, fetchImpl: fetchImpl });

  await ctl.handleDispatch({
    slot:   'image_generates',
    inputs: { prompt: 'a wide vista', aspect_ratio: '16:9' },
  });

  var obj = panel.inserted[0];
  record('16:9 aspect produces 1792×1024 default dims',
    obj && obj.width === 1792 && obj.height === 1024,
    obj ? (obj.width + 'x' + obj.height) : 'no obj');
}

async function testFallbackToAttachImage() {
  // Panel only exposes attachImage — the legacy upload path. The wiring
  // should still call it so the user sees their image.
  var host = _resetHost();
  var panel = _stubVisualPanel({ expose: false, exposeAttach: true });
  var fetchImpl = _mockFetchOk(RED_SQUARE_B64, 'image/png', 'openai');

  var stateEvent = null;
  host.addEventListener('canvas-state-changed', function (e) { stateEvent = e.detail; });

  var ctl = WIRING.init({ hostEl: host, visualPanel: panel, fetchImpl: fetchImpl });
  await ctl.handleDispatch({
    slot:   'image_generates',
    inputs: { prompt: 'a red square' },
  });

  record('attachImage was used as the fallback delivery path',
    panel.attached.length === 1,
    'attached=' + panel.attached.length);
  record('canvas-state-changed still fires on the fallback path',
    stateEvent && stateEvent.object && stateEvent.object.kind === 'image',
    stateEvent ? 'ok' : 'no event');
}

async function testQuotaExceededError() {
  var host = _resetHost();
  var panel = _stubVisualPanel();
  var fetchImpl = _mockFetchErr(429, 'quota_exceeded', 'Provider rate limit hit.');

  var ui = { renderResult: function () {}, renderError: function (p) { ui._err = p; } };
  var errorEvent = null;
  host.addEventListener('capability-error', function (e) { errorEvent = e.detail; });

  var ctl = WIRING.init({
    hostEl: host, visualPanel: panel, fetchImpl: fetchImpl, ui: ui,
  });

  var threw = null;
  try {
    await ctl.handleDispatch({
      slot:   'image_generates',
      inputs: { prompt: 'will be rate limited' },
    });
  } catch (e) {
    threw = e;
  }

  record('handleDispatch rejected on HTTP error',
    threw && threw.code === 'quota_exceeded',
    threw ? threw.code : 'no throw');
  record('capability-error event fired',
    errorEvent && errorEvent.code === 'quota_exceeded',
    errorEvent ? errorEvent.code : 'no event');
  record('UI.renderError was invoked with the slot code',
    ui._err && ui._err.code === 'quota_exceeded',
    ui._err ? ui._err.code : 'not invoked');
  record('no canvas object was inserted on error',
    panel.inserted.length === 0,
    'inserted=' + panel.inserted.length);
}

async function testSlotFilter() {
  // image_edits dispatches must not be intercepted by this wiring.
  var host = _resetHost();
  var panel = _stubVisualPanel();
  var fetchImpl = _mockFetchOk(RED_SQUARE_B64, 'image/png', 'openai');
  WIRING.init({
    hostEl: host, visualPanel: panel, fetchImpl: fetchImpl,
  });

  // Fire an image_edits event.
  var evt = new w.CustomEvent('capability-dispatch', {
    detail: { slot: 'image_edits', inputs: { prompt: 'inpaint' } },
    bubbles: true,
  });
  host.dispatchEvent(evt);

  // Microtask drain — handler is synchronous up to fetch dispatch.
  await new Promise(function (r) { setTimeout(r, 5); });

  record('image_edits dispatch did not trigger fetch',
    fetchImpl.calls.length === 0,
    'calls=' + fetchImpl.calls.length);
}

async function testBuildCanvasObjectInvariants() {
  var obj = WIRING.buildCanvasObject({
    base64: 'AAAA', mimeType: 'image/png', aspectRatio: '1:1',
  });
  record('buildCanvasObject returns kind=image',
    obj.kind === 'image', obj.kind);
  record('buildCanvasObject returns layer=user_input',
    obj.layer === 'user_input', obj.layer);
  record('buildCanvasObject id is non-empty',
    typeof obj.id === 'string' && obj.id.length > 0, obj.id);
  record('buildCanvasObject image_data is well-formed',
    obj.image_data && obj.image_data.encoding === 'base64'
      && obj.image_data.data === 'AAAA' && obj.image_data.mime_type === 'image/png',
    JSON.stringify(obj.image_data));
  record('buildCanvasObject rejects data: URL prefix downstream (extractor strips it)',
    typeof WIRING._extractImage({ image: { data: 'data:image/png;base64,AAAA' } }).base64 === 'string'
      && WIRING._extractImage({ image: { data: 'data:image/png;base64,AAAA' } }).base64 === 'AAAA',
    'ok');
}

// ── Run ──────────────────────────────────────────────────────────────────────

(async function () {
  console.log('test-capability-image-generates (WP-7.3.3a)');
  console.log('--------------------------------------------');

  try { await testHappyPath_RedSquare(); }            catch (e) { record('happy path threw', false, e.message); }
  try { await testAnchorPlacement(); }                catch (e) { record('anchor placement threw', false, e.message); }
  try { await testAnchorFromSelectionBBox(); }        catch (e) { record('legacy bbox anchor threw', false, e.message); }
  try { await testAspectRatioRouting(); }             catch (e) { record('aspect ratio threw', false, e.message); }
  try { await testFallbackToAttachImage(); }          catch (e) { record('attachImage fallback threw', false, e.message); }
  try { await testQuotaExceededError(); }             catch (e) { record('quota exceeded threw', false, e.message); }
  try { await testSlotFilter(); }                     catch (e) { record('slot filter threw', false, e.message); }
  try { await testBuildCanvasObjectInvariants(); }    catch (e) { record('canvas object invariants threw', false, e.message); }

  summarize();
})();
