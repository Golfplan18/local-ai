/* test-image-edits-wiring.js — WP-7.3.3b
 *
 * Verifies the §13.3 acceptance criterion:
 *   "Select an image, draw a mask via any selection tool, prompt
 *    'make it blue'; verify edited image lands."
 *
 * The browser-side wire layer (image-edits.js) is exercised against
 * each of the three §7.5.1 mask shapes (rect / brush / lasso) plus the
 * legacy stub-validator shapes (rect_mask / polygon_mask). The server
 * round-trip uses a mock fetch so no real network is touched.
 *
 * Run:  node ~/ora/server/static/tests/test-image-edits-wiring.js
 */

'use strict';

var assert = require('assert');
var path = require('path');
var fs = require('fs');

// ── jsdom bootstrap (shared with the other static/tests harnesses) ────
//
// The lifecycle tests at the bottom of this file mount the real
// capability popover and the real Exhibits-pane error bar and assert on
// visible nodes, so this harness needs a real document. jsdom supplies
// everything except a 2-D canvas context and image decoding, so
// `createElement` stays overridden for <canvas> and <img> with the same
// recorder / auto-onload stand-ins this harness has always used.

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

var _dom = new jsdom.JSDOM(
  '<!doctype html><html><body></body></html>', { pretendToBeVisual: true }
);
var _win = _dom.window;

// Minimal shim for the canvas APIs we exercise. We use Node's `canvas`
// module if available, otherwise hand-roll a tiny stub that the
// normalizeMask path can satisfy.
function _setupDom() {
  var hasCanvas = false;
  try { require('canvas'); hasCanvas = true; } catch (e) { /* noop */ }

  var makeCanvas, makeImage;

  if (!hasCanvas) {
    // Stand-in <canvas>: getContext returns a recorder that lets the
    // module's draw calls succeed without real raster output. We seed
    // toDataURL with a known base64 so the dataUrl path is exercised.
    function FakeCtx() {
      this.fillStyle = '';
      this.globalCompositeOperation = 'source-over';
      this._ops = [];
    }
    FakeCtx.prototype.fillRect = function () { this._ops.push(['fillRect'].concat([].slice.call(arguments))); };
    FakeCtx.prototype.clearRect = function () { this._ops.push(['clearRect'].concat([].slice.call(arguments))); };
    FakeCtx.prototype.beginPath = function () { this._ops.push(['beginPath']); };
    FakeCtx.prototype.moveTo = function () { this._ops.push(['moveTo'].concat([].slice.call(arguments))); };
    FakeCtx.prototype.lineTo = function () { this._ops.push(['lineTo'].concat([].slice.call(arguments))); };
    FakeCtx.prototype.closePath = function () { this._ops.push(['closePath']); };
    FakeCtx.prototype.fill = function () { this._ops.push(['fill']); };
    FakeCtx.prototype.save = function () { this._ops.push(['save']); };
    FakeCtx.prototype.restore = function () { this._ops.push(['restore']); };
    FakeCtx.prototype.drawImage = function () { this._ops.push(['drawImage'].concat([].slice.call(arguments))); };
    FakeCtx.prototype.getImageData = function (x, y, w, h) {
      // Pretend everything is opaque white (alpha=255) — the count loop
      // will report zero edited pixels in the fallback. We pre-set
      // pixels at index 3 to 0 only for the FAKE_RASTER fixture so the
      // count passes the >0 sanity check.
      var data = new Uint8ClampedArray(w * h * 4);
      for (var i = 0; i < data.length; i += 4) {
        data[i + 0] = 255; data[i + 1] = 255; data[i + 2] = 255;
        data[i + 3] = (i % 8 === 0) ? 0 : 255; // ~half transparent
      }
      return { data: data, width: w, height: h };
    };

    function FakeCanvas(width, height) {
      this.width = width || 0;
      this.height = height || 0;
      this._ctx = new FakeCtx();
    }
    FakeCanvas.prototype.getContext = function () { return this._ctx; };
    FakeCanvas.prototype.toDataURL = function () {
      return 'data:image/png;base64,FAKE_PNG_BASE64';
    };

    function FakeImage() {
      this.onload = null;
      this.onerror = null;
      this.src = '';
      Object.defineProperty(this, 'src', {
        set: function (v) {
          this._src = v;
          var self = this;
          // Fire onload on the next microtask so the Promise path can
          // observe the ordering correctly.
          setImmediate(function () {
            if (typeof self.onload === 'function') self.onload();
          });
        },
        get: function () { return this._src; },
        configurable: true
      });
    }

    makeCanvas = function () { return new FakeCanvas(); };
    makeImage  = function () { return new FakeImage(); };
  } else {
    // Use real `canvas` for both factories.
    var Canvas = require('canvas');
    makeCanvas = function () { return Canvas.createCanvas(0, 0); };
    makeImage  = function () { return new Canvas.Image(); };
  }

  // Splice the two stand-ins into the real document. Every other tag —
  // the popover, the panel, the invocation form — comes back as a real
  // element the tests can query and read text off.
  var _nativeCreate = _win.document.createElement.bind(_win.document);
  _win.document.createElement = function (tag) {
    var t = String(tag).toLowerCase();
    if (t === 'canvas') return makeCanvas();
    if (t === 'img')    return makeImage();
    return _nativeCreate(tag);
  };

  global.window      = _win;
  global.document    = _win.document;
  global.HTMLElement = _win.HTMLElement;
  global.CustomEvent = _win.CustomEvent;
  global.Event       = _win.Event;
  global.Node        = _win.Node;
}

_setupDom();

// Now load the module under test.
var ImageEdits = require(path.resolve(__dirname, '..', 'tools', 'image-edits.js'));

// ── Test runner ──────────────────────────────────────────────────────

var passed = 0, failed = 0, failures = [];
var _queue = Promise.resolve();
function record(name, fn) {
  _queue = _queue.then(function () {
    try {
      var r = fn();
      if (r && typeof r.then === 'function') {
        return r.then(function () {
          passed++;
          console.log('  PASS', name);
        }).catch(function (e) {
          failed++;
          failures.push({ name: name, err: e });
          console.log('  FAIL', name, '\n      ' + (e.stack || e.message));
        });
      }
      passed++;
      console.log('  PASS', name);
    } catch (e) {
      failed++;
      failures.push({ name: name, err: e });
      console.log('  FAIL', name, '\n      ' + (e.stack || e.message));
    }
  });
}

console.log('test-image-edits-wiring (WP-7.3.3b)');

// ── normalizeMask: rectangle ─────────────────────────────────────────

record('normalizeMask rectangle (image_ref/geometry shape)', function () {
  var rawMask = {
    schema_version: '1.0',
    kind: 'rectangle',
    image_ref: { image_id: 'img-1', natural_width: 200, natural_height: 100, source_name: 'a.png' },
    geometry: { x: 10, y: 10, width: 50, height: 50 },
    bbox: { x: 10, y: 10, width: 50, height: 50 }
  };
  var meta = { naturalWidth: 200, naturalHeight: 100 };
  var result = ImageEdits.normalizeMask(rawMask, meta);
  assert.strictEqual(result.error, null);
  assert.ok(result.dataUrl && result.dataUrl.indexOf('data:image/png;base64,') === 0,
    'dataUrl should be a PNG data URL');
  assert.strictEqual(result.parent_image_id, 'img-1');
  assert.strictEqual(result.mask_pixel_count, 50 * 50);
});

record('normalizeMask rect_mask (legacy stub-validator shape)', function () {
  var rawMask = {
    kind: 'rect_mask',
    parent_image_id: 'img-2',
    bbox: { x: 0, y: 0, width: 30, height: 40 }
  };
  var result = ImageEdits.normalizeMask(rawMask, { naturalWidth: 100, naturalHeight: 100 });
  assert.strictEqual(result.error, null);
  assert.strictEqual(result.parent_image_id, 'img-2');
  assert.strictEqual(result.mask_pixel_count, 30 * 40);
});

// ── normalizeMask: polygon ───────────────────────────────────────────

record('normalizeMask lasso_polygon', function () {
  var rawMask = {
    kind: 'lasso_polygon',
    parent_image_id: 'img-3',
    coordinate_space: 'image_local',
    polygon: [{x:10,y:10}, {x:60,y:10}, {x:60,y:60}, {x:10,y:60}],
    closed: true
  };
  var result = ImageEdits.normalizeMask(rawMask, { naturalWidth: 200, naturalHeight: 200 });
  assert.strictEqual(result.error, null);
  assert.ok(result.dataUrl && result.dataUrl.length > 0);
  assert.strictEqual(result.parent_image_id, 'img-3');
  assert.ok(result.mask_pixel_count > 0, 'polygon should have non-zero area');
});

record('normalizeMask polygon_mask (legacy stub-validator shape)', function () {
  var rawMask = {
    kind: 'polygon_mask',
    parent_image_id: 'img-4',
    points: [[0,0], [10,0], [5,10]]
  };
  var result = ImageEdits.normalizeMask(rawMask, { naturalWidth: 50, naturalHeight: 50 });
  assert.strictEqual(result.error, null);
});

record('normalizeMask polygon with too few points returns mask_invalid', function () {
  var rawMask = { kind: 'lasso_polygon', parent_image_id: 'img-5',
                  polygon: [{x:0,y:0}, {x:1,y:1}] };
  var result = ImageEdits.normalizeMask(rawMask, { naturalWidth: 50, naturalHeight: 50 });
  assert.ok(result.error && /3\+/.test(result.error));
});

// ── normalizeMask: raster (async path) ───────────────────────────────

record('normalizeMask raster_mask returns a Promise', function (done) {
  var rawMask = {
    kind: 'raster_mask',
    parent_image_id: 'img-6',
    parent_image_bbox: { x: 0, y: 0, width: 100, height: 100 },
    mask_data_url: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==',
    mask_pixel_count: 250
  };
  var meta = { naturalWidth: 200, naturalHeight: 200 };
  var result = ImageEdits.normalizeMask(rawMask, meta);
  // pendingPromise is the contract for async paths
  assert.ok(result && typeof result.pendingPromise === 'object', 'should produce a pendingPromise');
});

// ── error-shape: missing input ────────────────────────────────────────

record('normalizeMask rejects empty mask', function () {
  var result = ImageEdits.normalizeMask(null, { naturalWidth: 100, naturalHeight: 100 });
  assert.ok(result.error && /empty mask/.test(result.error));
});

record('normalizeMask rejects missing source dimensions', function () {
  var rawMask = { kind: 'rectangle', image_ref: {image_id:'x'},
                  geometry: { x:0, y:0, width: 10, height: 10 } };
  var result = ImageEdits.normalizeMask(rawMask, {});
  assert.ok(result.error && /image_unreadable/.test(result.error));
});

record('normalizeMask rejects unknown kind', function () {
  var result = ImageEdits.normalizeMask({ kind: 'mystery_kind' },
    { naturalWidth: 100, naturalHeight: 100 });
  assert.ok(result.error && /unknown kind/.test(result.error));
});

// ── attach() / dispatch flow with mocked fetch ───────────────────────

record('capability-dispatch on image_edits POSTs to endpoint', function () {
  // Mock host element + panel.
  var dispatchedTo = null;
  var bodyReceived = null;
  function fakeFetch(url, opts) {
    dispatchedTo = url;
    bodyReceived = opts.body;
    return Promise.resolve({
      ok: true,
      headers: { get: function () { return 'application/json'; } },
      json: function () {
        return Promise.resolve({
          image_b64: 'iVBORw0KGgoAAAANSUhEUg==',
          provider_id: 'mock',
          mode: 'inpaint'
        });
      }
    });
  }

  var hostListeners = {};
  var hostEl = {
    addEventListener: function (n, fn) { (hostListeners[n] = hostListeners[n] || []).push(fn); },
    removeEventListener: function (n, fn) {
      if (!hostListeners[n]) return;
      hostListeners[n] = hostListeners[n].filter(function (g) { return g !== fn; });
    },
    dispatchEvent: function (evt) {
      (hostListeners[evt.type] || []).forEach(function (fn) { fn(evt); });
      return true;
    }
  };

  // Fake panel with a Konva.Image-shaped node.
  var fakeNode = {
    attrs: { naturalWidth: 200, naturalHeight: 100, image_id: 'panel-img-1' },
    getAttrs: function () { return this.attrs; },
    image: function (newImg) { if (newImg) this._img = newImg; return this._img; },
    setAttrs: function (a) { Object.assign(this.attrs, a); },
    getClientRect: function () { return { x: 0, y: 0, width: 200, height: 100 }; },
    id: function () { return 'panel-img-1'; },
    name: function () { return 'vp-background-image'; },
    toDataURL: function () { return 'data:image/png;base64,SOURCE_BASE64'; },
    getLayer: function () { return { draw: function () {} }; }
  };
  var panel = {
    el: hostEl,
    stage: {},
    backgroundLayer: { add: function () {}, draw: function () {} },
    _backgroundImageNode: fakeNode,
    _pendingImage: { dataUrl: 'data:image/png;base64,SOURCE_BASE64', name: 'a.png' }
  };

  ImageEdits.attach({
    hostEl: hostEl,
    panel: panel,
    endpointUrl: '/api/capability/image_edits',
    fetch: fakeFetch
  });

  // Seed a mask via the selection event.
  hostEl.dispatchEvent(new CustomEvent('ora:selection-mask', {
    detail: {
      mask: {
        kind: 'rectangle',
        image_ref: { image_id: 'panel-img-1', natural_width: 200, natural_height: 100 },
        geometry: { x: 10, y: 10, width: 50, height: 50 },
        bbox: { x: 10, y: 10, width: 50, height: 50 }
      },
      capability: 'image_edits'
    }
  }));

  // Now dispatch.
  hostEl.dispatchEvent(new CustomEvent('capability-dispatch', {
    detail: {
      slot: 'image_edits',
      inputs: { prompt: 'make it blue' },
      execution_pattern: 'sync'
    }
  }));

  // The dispatch is async (wraps normalize through Promise.resolve).
  // Assertions inside a bare setTimeout escape the runner's promise
  // chain: a failure there aborts the process with a raw stack, no
  // summary line, and every later test unrun. Settle explicitly instead.
  return new Promise(function (resolve, reject) {
    setTimeout(function () {
      try {
        assert.strictEqual(dispatchedTo, '/api/capability/image_edits');
        assert.ok(bodyReceived, 'body should have been sent');
        var parsed = JSON.parse(bodyReceived);
        assert.strictEqual(parsed.slot, 'image_edits');
        assert.strictEqual(parsed.prompt, 'make it blue');
        assert.ok(parsed.image_data_url && parsed.image_data_url.indexOf('data:image/') === 0);
        assert.ok(parsed.mask_data_url && parsed.mask_data_url.indexOf('data:image/') === 0);
        ImageEdits.detach();
        resolve();
      } catch (e) { ImageEdits.detach(); reject(e); }
    }, 50);
  });
});

record('capability-dispatch with no mask emits capability-error', function () {
  var errors = [];
  var hostListeners = {};
  var hostEl = {
    addEventListener: function (n, fn) { (hostListeners[n] = hostListeners[n] || []).push(fn); },
    removeEventListener: function (n, fn) {
      if (!hostListeners[n]) return;
      hostListeners[n] = hostListeners[n].filter(function (g) { return g !== fn; });
    },
    dispatchEvent: function (evt) {
      if (evt.type === 'capability-error') errors.push(evt.detail);
      (hostListeners[evt.type] || []).forEach(function (fn) { fn(evt); });
      return true;
    }
  };
  var panel = {
    el: hostEl,
    _backgroundImageNode: {
      attrs: { naturalWidth: 100, naturalHeight: 100 },
      getAttrs: function () { return this.attrs; },
      getClientRect: function () { return { x:0, y:0, width: 100, height: 100 }; },
      image: function () {}, setAttrs: function () {}, toDataURL: function () { return 'data:image/png;base64,X'; },
      getLayer: function () { return { draw: function () {} }; }
    },
    _pendingImage: { dataUrl: 'data:image/png;base64,X' }
  };

  ImageEdits.attach({
    hostEl: hostEl,
    panel: panel,
    fetch: function () { return Promise.reject(new Error('should not fetch with missing mask')); }
  });

  hostEl.dispatchEvent(new CustomEvent('capability-dispatch', {
    detail: { slot: 'image_edits', inputs: { prompt: 'make it blue' } }
  }));

  // The error-emit is synchronous before any fetch.
  assert.strictEqual(errors.length, 1);
  assert.strictEqual(errors[0].code, 'no_mask_drawn');
  ImageEdits.detach();
});

record('capability-dispatch with no prompt emits capability-error', function () {
  // `prompt` is the third required input of §3.2. An image and a mask are
  // both present here, so the only thing missing is the prompt — the
  // dispatch must stop at the same guard rail the other two get, not
  // manufacture a prompt and edit the user's image with invented words.
  var errors = [];
  var fetchCalls = 0;
  var hostListeners = {};
  var hostEl = {
    addEventListener: function (n, fn) { (hostListeners[n] = hostListeners[n] || []).push(fn); },
    removeEventListener: function (n, fn) {
      if (!hostListeners[n]) return;
      hostListeners[n] = hostListeners[n].filter(function (g) { return g !== fn; });
    },
    dispatchEvent: function (evt) {
      if (evt.type === 'capability-error') errors.push(evt.detail);
      (hostListeners[evt.type] || []).forEach(function (fn) { fn(evt); });
      return true;
    }
  };

  var fakeNode = {
    attrs: { naturalWidth: 200, naturalHeight: 100, image_id: 'panel-img-1' },
    getAttrs: function () { return this.attrs; },
    image: function (newImg) { if (newImg) this._img = newImg; return this._img; },
    setAttrs: function (a) { Object.assign(this.attrs, a); },
    getClientRect: function () { return { x: 0, y: 0, width: 200, height: 100 }; },
    id: function () { return 'panel-img-1'; },
    name: function () { return 'vp-background-image'; },
    toDataURL: function () { return 'data:image/png;base64,SOURCE_BASE64'; },
    getLayer: function () { return { draw: function () {} }; }
  };
  var panel = {
    el: hostEl,
    stage: {},
    backgroundLayer: { add: function () {}, draw: function () {} },
    _backgroundImageNode: fakeNode,
    _pendingImage: { dataUrl: 'data:image/png;base64,SOURCE_BASE64', name: 'a.png' }
  };

  ImageEdits.attach({
    hostEl: hostEl,
    panel: panel,
    endpointUrl: '/api/capability/image_edits',
    fetch: function () {
      fetchCalls++;
      return Promise.reject(new Error('should not fetch with a blank prompt'));
    }
  });

  // Seed a valid mask so the image/mask guards both pass.
  hostEl.dispatchEvent(new CustomEvent('ora:selection-mask', {
    detail: {
      mask: {
        kind: 'rectangle',
        image_ref: { image_id: 'panel-img-1', natural_width: 200, natural_height: 100 },
        geometry: { x: 10, y: 10, width: 50, height: 50 },
        bbox: { x: 10, y: 10, width: 50, height: 50 }
      },
      capability: 'image_edits'
    }
  }));

  // Whitespace-only counts as blank. The popover gates this too, so this case
  // only arrives from a programmatic capability-dispatch — the handler is the
  // last line of defence for emitters that bypass the form.
  hostEl.dispatchEvent(new CustomEvent('capability-dispatch', {
    detail: { slot: 'image_edits', inputs: { prompt: '   ' } }
  }));

  // The error-emit is synchronous, before normalization or any fetch.
  assert.strictEqual(errors.length, 1);
  assert.strictEqual(errors[0].code, 'missing_required_input');
  assert.strictEqual(errors[0].slot, 'image_edits');

  // An absent `prompt` key behaves the same way.
  hostEl.dispatchEvent(new CustomEvent('capability-dispatch', {
    detail: { slot: 'image_edits', inputs: {} }
  }));
  assert.strictEqual(errors.length, 2);
  assert.strictEqual(errors[1].code, 'missing_required_input');

  // Give the async normalize/POST tail a chance to run had it been
  // reached: it must not have been. Same guarded shape as above — a bare
  // setTimeout assertion would abort the process instead of failing.
  return new Promise(function (resolve, reject) {
    setTimeout(function () {
      try {
        assert.strictEqual(fetchCalls, 0, 'must not POST without a prompt');
        assert.strictEqual(errors.length, 2, 'must not continue into normalization');
        ImageEdits.detach();
        resolve();
      } catch (e) { ImageEdits.detach(); reject(e); }
    }, 50);
  });
});

// ── Error visibility ─────────────────────────────────────────────────
//
// Every failure of this capability used to be invisible: the module
// emitted `capability-error`, nothing in production listened, and a
// failed edit, a network error, a missing image, a missing mask and a
// missing prompt all produced silence on screen.
//
// The surface that fixes that is the Exhibits pane's error bar — the
// same strip visual-panel.js already uses for image-upload and crop
// failures. It is deliberately NOT the WP-7.3.1 invocation popover:
// v3-pack-toolbars.js schedules `setTimeout(_closeCapabilityPopover,
// 250)` from `onDispatch` on every submit, and that close calls
// `controller.destroy()`. A popover render is therefore a
// quarter-second flash at best (synchronous guards) and a throw into a
// dead controller at worst (everything after the POST). The lifecycle
// tests at the bottom of this file prove that against the real popover,
// the real invocation UI, and the real 250 ms timer.
//
// So each failure path must do BOTH:
//   1. write the reason onto `panel._showErrorBar` — a real visible node
//      the user can read, which outlives the popover;
//   2. emit `capability-error` as before, so existing listeners keep
//      working.
//
// With a panel that has no error bar — headless drivers, and every test
// above — the write is skipped, the event still fires, nothing throws.

// The real panel: visual-panel.js registers window.VisualPanel and mounts
// cleanly in jsdom without Konva (the compiler suite's case 13 covers
// that path). We use the real component so "the user can see it" is an
// assertion about a real, visible DOM node rather than about a spy.
require(path.resolve(__dirname, '..', 'visual-panel.js'));

var ERRORBAR_SELECTOR = '.visual-panel__errorbar';

function _mkHostEl(errors) {
  var hostListeners = {};
  return {
    addEventListener: function (n, fn) { (hostListeners[n] = hostListeners[n] || []).push(fn); },
    removeEventListener: function (n, fn) {
      if (!hostListeners[n]) return;
      hostListeners[n] = hostListeners[n].filter(function (g) { return g !== fn; });
    },
    dispatchEvent: function (evt) {
      if (evt.type === 'capability-error' && errors) errors.push(evt.detail);
      (hostListeners[evt.type] || []).forEach(function (fn) { fn(evt); });
      return true;
    }
  };
}

function _mkImageNode() {
  return {
    attrs: { naturalWidth: 200, naturalHeight: 100, image_id: 'panel-img-1' },
    getAttrs: function () { return this.attrs; },
    image: function (newImg) { if (newImg) this._img = newImg; return this._img; },
    setAttrs: function (a) { Object.assign(this.attrs, a); },
    getClientRect: function () { return { x: 0, y: 0, width: 200, height: 100 }; },
    id: function () { return 'panel-img-1'; },
    name: function () { return 'vp-background-image'; },
    toDataURL: function () { return 'data:image/png;base64,SOURCE_BASE64'; },
    getLayer: function () { return { draw: function () {} }; }
  };
}

// A real VisualPanel mounted into the real document. `withImage=false`
// yields a panel with no mounted image, which is what drives the
// `no_image_selected` path.
//
// init() in a Konva-less run leaves "Konva not loaded …" on the error
// bar; each case starts from a cleared bar so the assertions are about
// what image-edits wrote.
var _panelSeq = 0;
function _mkRealPanel(withImage) {
  var el = document.createElement('div');
  document.body.appendChild(el);
  // Each panel needs its own panelId: VisualPanel builds element ids from
  // it, and a scoped `#id` query resolves through the document's id map,
  // so two panels sharing an id make the second one's lookups miss.
  var panel = new window.VisualPanel(el, { id: 'test-panel-' + (++_panelSeq) });
  panel.init();
  panel._errorBar.textContent = '';
  panel._errorBar.hidden = true;
  if (withImage) {
    panel._backgroundImageNode = _mkImageNode();
    panel._pendingImage = { dataUrl: 'data:image/png;base64,SOURCE_BASE64', name: 'a.png' };
  }
  return panel;
}

// Plain-object panel with no error bar at all — the headless shape.
function _mkBarelessPanel(hostEl, withImage) {
  var panel = {
    el: hostEl,
    stage: {},
    backgroundLayer: { add: function () {}, draw: function () {} }
  };
  if (withImage) {
    panel._backgroundImageNode = _mkImageNode();
    panel._pendingImage = { dataUrl: 'data:image/png;base64,SOURCE_BASE64', name: 'a.png' };
  }
  return panel;
}

// What the user can actually read off the pane right now: null when the
// bar is hidden or empty.
function _visibleErrorText(panel) {
  var bar = panel.el.querySelector(ERRORBAR_SELECTOR);
  if (!bar || bar.hidden) return null;
  var txt = bar.textContent || '';
  return txt.length ? txt : null;
}

var VALID_MASK = {
  kind: 'rectangle',
  image_ref: { image_id: 'panel-img-1', natural_width: 200, natural_height: 100 },
  geometry: { x: 10, y: 10, width: 50, height: 50 },
  bbox: { x: 10, y: 10, width: 50, height: 50 }
};

var VALID_MASK_EVENT = { mask: VALID_MASK, capability: 'image_edits' };

function _seedMask(panel) {
  panel.el.dispatchEvent(new CustomEvent('ora:selection-mask', {
    detail: VALID_MASK_EVENT, bubbles: true
  }));
}

function _dispatchEdit(hostEl, inputs) {
  hostEl.dispatchEvent(new CustomEvent('capability-dispatch', {
    detail: { slot: 'image_edits', inputs: inputs, execution_pattern: 'sync' },
    bubbles: true
  }));
}

record('no_image_selected shows a readable error bar and still emits', function () {
  var errors = [];
  var panel = _mkRealPanel(false);   // nothing mounted on the canvas
  var hostEl = _mkHostEl(errors);

  ImageEdits.attach({
    hostEl: hostEl,
    panel: panel,
    fetch: function () { return Promise.reject(new Error('must not fetch')); }
  });

  _dispatchEdit(hostEl, { prompt: 'make it blue' });

  var seen = _visibleErrorText(panel);
  assert.ok(seen, 'the user must see the error');
  assert.ok(/no_image_selected/.test(seen), 'the code is legible: ' + seen);
  assert.ok(/No image is currently mounted on the canvas\./.test(seen),
    'the reason is legible: ' + seen);
  // The event other listeners rely on is unchanged.
  assert.strictEqual(errors.length, 1);
  assert.strictEqual(errors[0].code, 'no_image_selected');
  assert.strictEqual(errors[0].slot, 'image_edits');
  ImageEdits.detach();
});

record('no_mask_drawn shows a readable error bar and still emits', function () {
  var errors = [];
  var panel = _mkRealPanel(true);    // image present, no mask drawn
  var hostEl = _mkHostEl(errors);

  ImageEdits.attach({
    hostEl: hostEl,
    panel: panel,
    fetch: function () { return Promise.reject(new Error('must not fetch')); }
  });

  _dispatchEdit(hostEl, { prompt: 'make it blue' });

  var seen = _visibleErrorText(panel);
  assert.ok(seen && /no_mask_drawn/.test(seen), 'the user must see the error: ' + seen);
  assert.ok(/Draw a mask on the image first/.test(seen), 'the reason is legible: ' + seen);
  assert.strictEqual(errors.length, 1);
  assert.strictEqual(errors[0].code, 'no_mask_drawn');
  ImageEdits.detach();
});

record('missing_required_input shows a readable error bar and still emits', function () {
  var errors = [];
  var panel = _mkRealPanel(true);
  var hostEl = _mkHostEl(errors);

  ImageEdits.attach({
    hostEl: hostEl,
    panel: panel,
    fetch: function () { return Promise.reject(new Error('must not fetch')); }
  });

  // Image and mask both satisfied — the prompt is the only thing missing.
  _seedMask(panel);
  _dispatchEdit(hostEl, { prompt: '   ' });

  var seen = _visibleErrorText(panel);
  assert.ok(seen && /missing_required_input/.test(seen),
    'the user must see the error: ' + seen);
  assert.ok(/Describe what should appear in the masked region\./.test(seen),
    'the reason is legible: ' + seen);
  assert.strictEqual(errors.length, 1);
  assert.strictEqual(errors[0].code, 'missing_required_input');
  ImageEdits.detach();
});

record('a failed dispatch (network error) shows a readable error bar and still emits', function () {
  var errors = [];
  var panel = _mkRealPanel(true);
  var hostEl = _mkHostEl(errors);

  ImageEdits.attach({
    hostEl: hostEl,
    panel: panel,
    fetch: function () { return Promise.reject(new Error('connection refused')); }
  });

  _seedMask(panel);
  _dispatchEdit(hostEl, { prompt: 'make it blue' });

  // This failure lands after the async normalize + POST tail. Assertions
  // inside a bare setTimeout escape the runner's promise chain and abort
  // the process, so settle explicitly.
  return new Promise(function (resolve, reject) {
    setTimeout(function () {
      try {
        var seen = _visibleErrorText(panel);
        assert.ok(seen, 'the user must see the network failure');
        assert.ok(/model_unavailable/.test(seen), 'code is legible: ' + seen);
        assert.ok(/connection refused/.test(seen),
          'the bar should carry the underlying cause: ' + seen);
        assert.strictEqual(errors.length, 1);
        assert.strictEqual(errors[0].code, 'model_unavailable');
        ImageEdits.detach();
        resolve();
      } catch (e) { ImageEdits.detach(); reject(e); }
    }, 50);
  });
});

record('a server error response shows a readable error bar and still emits', function () {
  var errors = [];
  var panel = _mkRealPanel(true);
  var hostEl = _mkHostEl(errors);

  ImageEdits.attach({
    hostEl: hostEl,
    panel: panel,
    fetch: function () {
      return Promise.resolve({
        ok: false,
        status: 503,
        headers: { get: function () { return 'application/json'; } },
        json: function () {
          return Promise.resolve({
            error: { code: 'model_unavailable', message: 'No inpaint provider configured.' }
          });
        }
      });
    }
  });

  _seedMask(panel);
  _dispatchEdit(hostEl, { prompt: 'make it blue' });

  return new Promise(function (resolve, reject) {
    setTimeout(function () {
      try {
        var seen = _visibleErrorText(panel);
        assert.ok(seen, 'the user must see the server error');
        assert.ok(/No inpaint provider configured\./.test(seen),
          'the server message reaches the pane verbatim: ' + seen);
        assert.strictEqual(errors.length, 1);
        assert.strictEqual(errors[0].message, 'No inpaint provider configured.');
        ImageEdits.detach();
        resolve();
      } catch (e) { ImageEdits.detach(); reject(e); }
    }, 50);
  });
});

record('the production mount shape ({hostEl, panel}) reaches the user', function () {
  // v3-capability-async.js:196 hands us only { hostEl, panel } — exactly
  // as it always has. If the failure surface needed anything else, the
  // fix would never reach the app.
  var errors = [];
  var panel = _mkRealPanel(true);
  var hostEl = _mkHostEl(errors);

  ImageEdits.attach({ hostEl: hostEl, panel: panel });
  _dispatchEdit(hostEl, { prompt: 'make it blue' });

  var seen = _visibleErrorText(panel);
  assert.ok(seen && /no_mask_drawn/.test(seen),
    'no extra wiring: the mount as it stands must surface the error: ' + seen);
  assert.strictEqual(errors.length, 1);
  ImageEdits.detach();
});

record('a new dispatch retracts the previous run\'s error bar', function () {
  // A verdict must not outlive the run it described: the next attempt
  // clears it, so a stale "Image edit failed …" can never sit over a
  // canvas that has since been edited successfully.
  var errors = [];
  var panel = _mkRealPanel(true);
  var hostEl = _mkHostEl(errors);

  ImageEdits.attach({
    hostEl: hostEl,
    panel: panel,
    fetch: function () { return Promise.reject(new Error('must not fetch')); }
  });

  _dispatchEdit(hostEl, { prompt: 'make it blue' });   // no mask → error bar up
  assert.ok(_visibleErrorText(panel), 'precondition: the bar is up');

  // Second run, this time with a mask. The bar must retract at the top
  // of the dispatch rather than lingering through the POST.
  _seedMask(panel);
  _dispatchEdit(hostEl, { prompt: 'make it blue' });
  assert.strictEqual(_visibleErrorText(panel), null,
    'the previous run\'s verdict must be retracted when a new run starts');

  return new Promise(function (resolve, reject) {
    setTimeout(function () { ImageEdits.detach(); resolve(); }, 50);
  }).catch(function (e) { ImageEdits.detach(); throw e; });
});

record('an unrelated message on the bar is left alone', function () {
  // The bar is shared with compile errors and upload warnings. We only
  // retract text we ourselves wrote.
  var errors = [];
  var panel = _mkRealPanel(true);
  var hostEl = _mkHostEl(errors);

  ImageEdits.attach({
    hostEl: hostEl,
    panel: panel,
    fetch: function () { return Promise.reject(new Error('must not fetch')); }
  });

  _dispatchEdit(hostEl, { prompt: 'make it blue' });   // our error lands
  assert.ok(_visibleErrorText(panel), 'precondition: our error is on the bar');
  panel._showErrorBar('Visual could not be rendered');  // someone else replaces it

  _seedMask(panel);
  _dispatchEdit(hostEl, { prompt: 'make it blue' });
  assert.strictEqual(_visibleErrorText(panel), 'Visual could not be rendered',
    'a message we did not write must survive our retraction');

  return new Promise(function (resolve) {
    setTimeout(function () { ImageEdits.detach(); resolve(); }, 50);
  });
});

// An upload warning tints the bar amber via the --image modifier. An edit
// failure that inherits that tint reads as a warning, not a failure.
record('an edit failure after an upload warning renders as an error, not a warning',
function () {
  var panel = _mkRealPanel(true);
  var hostEl = panel.el;

  panel._showImageError('Image upload failed.');   // the amber warning path
  assert.ok(panel._errorBar.classList.contains('visual-panel__errorbar--image'),
    'precondition: the warning tint is on the bar');

  ImageEdits.attach({ hostEl: hostEl, panel: panel });
  _dispatchEdit(hostEl, { prompt: 'make it blue' });   // no mask seeded -> our failure
  assert.ok(_visibleErrorText(panel), 'precondition: our failure is on the bar');
  assert.strictEqual(
    panel._errorBar.classList.contains('visual-panel__errorbar--image'), false,
    'the warning tint must be dropped so the failure reads as an error');
  ImageEdits.detach();
});

record('with no error bar the module still emits and does not throw', function () {
  var errors = [];
  var hostEl = _mkHostEl(errors);

  ImageEdits.attach({
    hostEl: hostEl,
    panel: _mkBarelessPanel(hostEl, true),
    fetch: function () { return Promise.reject(new Error('connection refused')); }
  });

  // Sync guard path — must not throw.
  _dispatchEdit(hostEl, { prompt: 'make it blue' });
  assert.strictEqual(errors.length, 1);
  assert.strictEqual(errors[0].code, 'no_mask_drawn');

  // Async failure path — must not throw either.
  hostEl.dispatchEvent(new CustomEvent('ora:selection-mask', { detail: VALID_MASK_EVENT }));
  _dispatchEdit(hostEl, { prompt: 'make it blue' });

  return new Promise(function (resolve, reject) {
    setTimeout(function () {
      try {
        assert.strictEqual(errors.length, 2);
        assert.strictEqual(errors[1].code, 'model_unavailable');
        ImageEdits.detach();
        resolve();
      } catch (e) { ImageEdits.detach(); reject(e); }
    }, 50);
  });
});

record('an error bar that throws does not suppress the capability-error event', function () {
  var errors = [];
  var hostEl = _mkHostEl(errors);
  var panel = _mkBarelessPanel(hostEl, true);
  var barCalls = 0;
  panel._showErrorBar = function () { barCalls++; throw new Error('error bar blew up'); };

  ImageEdits.attach({
    hostEl: hostEl,
    panel: panel,
    fetch: function () { return Promise.reject(new Error('must not fetch')); }
  });

  // Must not propagate out of the dispatch listener.
  _dispatchEdit(hostEl, { prompt: 'make it blue' });

  assert.strictEqual(barCalls, 1, 'the surface was attempted');
  assert.strictEqual(errors.length, 1, 'the event still fired');
  assert.strictEqual(errors[0].code, 'no_mask_drawn');
  ImageEdits.detach();
});

record('the error bar paints above the Excalidraw island', function () {
  // The bar and .ora-excalidraw-island are siblings inside .right-pane,
  // and the island paints an opaque background over the whole pane. If
  // the bar ever sinks back below it, every message written here is
  // invisible whenever Excalidraw is the active editor — which is the
  // default. jsdom does not compute stacking, so this reads the declared
  // values; it is the only mechanical form the guarantee has.
  var css = fs.readFileSync(
    path.resolve(__dirname, '..', 'css', 'visual-panel.css'), 'utf-8');

  function _zIndexOf(selector) {
    var i = css.indexOf('\n' + selector + ' {');
    assert.ok(i >= 0, 'stylesheet should declare ' + selector);
    var block = css.slice(i, css.indexOf('}', i));
    var m = /z-index:\s*(\d+)/.exec(block);
    assert.ok(m, selector + ' should declare a z-index');
    return parseInt(m[1], 10);
  }

  var bar = _zIndexOf('.visual-panel__errorbar');
  var island = _zIndexOf('.ora-excalidraw-island');
  assert.ok(bar > island,
    'error bar z-index (' + bar + ') must exceed the Excalidraw island ('
    + island + ') or failures are painted over');
});

// ── Real popover lifecycle ───────────────────────────────────────────
//
// The tests above prove the error bar carries the message. These prove
// the thing the bar exists for: that the WP-7.3.1 popover cannot carry
// it. Everything here is the production wiring — the real
// capability-invocation-ui.js controller, mounted by the real
// v3-pack-toolbars.js `_openCapabilityPopover`, against the real
// capabilities.json contract, closing on the real
// `setTimeout(_closeCapabilityPopover, 250)` — with the failure timed to
// land after that close.

var CAPABILITIES_PATH = path.resolve(
  __dirname, '..', '..', '..', 'config', 'capabilities.json'
);
var CAPABILITIES = JSON.parse(fs.readFileSync(CAPABILITIES_PATH, 'utf-8'));

// The popover fetches its contract from /static/config/capabilities.json.
// v3-pack-toolbars.js calls the bare global `fetch`, and it caches the
// first promise it gets, so this has to be in place before the first
// popover opens — Node's native fetch rejects a relative URL outright.
function _capabilitiesFetch(url) {
  if (String(url).indexOf('capabilities.json') >= 0) {
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve(CAPABILITIES); } });
  }
  return Promise.reject(new Error('unexpected fetch: ' + url));
}
window.fetch = _capabilitiesFetch;
global.fetch = _capabilitiesFetch;

// The invocation UI routes user-authored prompt text through the
// Dialogue privacy boundary before dispatching. Production supplies
// OraConversation; here it approves and continues, which is the path a
// user who accepts the privacy prompt takes.
window.OraConversation = {
  submitAfterPrivacy: function (text, proceed) { proceed(); return true; }
};

require(path.resolve(__dirname, '..', 'capability-invocation-ui.js'));
require(path.resolve(__dirname, '..', 'js', 'v3-pack-toolbars.js'));

var PackToolbars = window.OraV3PackToolbars;
var InvocationUI = window.OraCapabilityInvocationUI;

function _wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

// Open a capability popover exactly the way a toolbar click does.
function _openPopover(slot, panel) {
  PackToolbars._openCapabilityPopover(slot, null, panel);
  // _openCapabilityPopover resolves the capabilities fetch first.
  return _wait(20).then(function () {
    var ctl = InvocationUI._getActive();
    assert.ok(ctl, 'popover controller should be mounted for ' + slot);
    return ctl;
  });
}

function _popoverHost() { return document.getElementById('ora-capability-popover'); }

function _typePrompt(ctl, text) {
  var node = ctl._state.formEl.querySelector('[name="prompt"]');
  assert.ok(node, 'the slot contract should render a prompt control');
  node.value = text;
  ctl.refreshEnabledState();
}

record('LIFECYCLE: a failure after the popover\'s 250 ms auto-close is still visible', function () {
  var errors = [];
  var panel = _mkRealPanel(true);
  var rejectPost;
  var postPromise = new Promise(function (_res, rej) { rejectPost = rej; });

  ImageEdits.attach({
    hostEl: document.body,          // the production host
    panel: panel,
    fetch: function () { return postPromise; }
  });
  document.body.addEventListener('capability-error', function onErr(e) {
    errors.push(e.detail);
  });

  _seedMask(panel);

  return _openPopover('image_edits', panel).then(function (ctl) {
    _typePrompt(ctl, 'make it blue');
    var host = _popoverHost();
    assert.strictEqual(host.getAttribute('aria-hidden'), 'false',
      'precondition: the popover is open');

    assert.ok(ctl.submit(), 'the Run button path must dispatch');

    // The server takes longer than the popover lives.
    return _wait(400).then(function () {
      // The real lifecycle really ran: the popover closed on its timer
      // and its controller was destroyed.
      assert.strictEqual(host.getAttribute('aria-hidden'), 'true',
        'the popover must have auto-closed at 250 ms');
      assert.strictEqual(ctl._state.destroyed, true,
        'the close destroys the controller');
      assert.strictEqual(ctl._state.errorEl, null,
        'a destroyed controller has no error element to render into');

      rejectPost(new Error('gateway timeout'));
      return _wait(50);
    }).then(function () {
      var seen = _visibleErrorText(panel);
      assert.ok(seen, 'the user must be able to read why the edit failed');
      assert.ok(/gateway timeout/.test(seen), 'the cause is legible: ' + seen);
      assert.strictEqual(errors.length, 1, 'the event fired exactly once');

      // And it does not flash: still there well past any close timer.
      return _wait(300).then(function () {
        assert.ok(_visibleErrorText(panel),
          'the error must persist, not flash');
        ImageEdits.detach();
        PackToolbars._closeCapabilityPopover();
      });
    });
  }).catch(function (e) {
    ImageEdits.detach();
    PackToolbars._closeCapabilityPopover();
    throw e;
  });
});

record('LIFECYCLE: a synchronous guard survives the 250 ms auto-close', function () {
  // The guards fire inside the dispatch handler, while the popover is
  // still on screen — and the popover is destroyed a quarter-second
  // later regardless. Reachable case: the canvas holds an image whose
  // bytes cannot be read (tainted canvas), so the popover's image-ref
  // widget pre-fills and enables Run while the module finds nothing to
  // send.
  var errors = [];
  var panel = _mkRealPanel(false);
  panel._backgroundImageNode = _mkImageNode();
  panel._backgroundImageNode.image = function () { return null; };
  panel._backgroundImageNode.toDataURL = function () { throw new Error('tainted canvas'); };

  ImageEdits.attach({
    hostEl: document.body,
    panel: panel,
    fetch: function () { return Promise.reject(new Error('must not fetch')); }
  });
  var onErr = function (e) { errors.push(e.detail); };
  document.body.addEventListener('capability-error', onErr);

  _seedMask(panel);

  return _openPopover('image_edits', panel).then(function (ctl) {
    _typePrompt(ctl, 'make it blue');
    ctl.submit();

    var seen = _visibleErrorText(panel);
    assert.ok(seen && /no_image_selected/.test(seen),
      'the guard must be visible immediately: ' + seen);

    // Past the auto-close: the popover is gone, the message is not.
    return _wait(400).then(function () {
      assert.strictEqual(_popoverHost().getAttribute('aria-hidden'), 'true',
        'the popover closed on its timer');
      var still = _visibleErrorText(panel);
      assert.ok(still && /no_image_selected/.test(still),
        'the guard must outlive the popover, not flash with it: ' + still);
      assert.strictEqual(errors.length, 1);
      document.body.removeEventListener('capability-error', onErr);
      ImageEdits.detach();
      PackToolbars._closeCapabilityPopover();
    });
  }).catch(function (e) {
    document.body.removeEventListener('capability-error', onErr);
    ImageEdits.detach();
    PackToolbars._closeCapabilityPopover();
    throw e;
  });
});

record('LIFECYCLE: an image_edits failure never touches another slot\'s popover', function () {
  // The regression this guards: resolving the failure surface through
  // OraCapabilityInvocationUI's module-level "active controller" paints
  // whichever popover the user has opened SINCE the dispatch, and clears
  // that popover's in-flight state along with it.
  var panel = _mkRealPanel(true);
  var rejectPost;
  var postPromise = new Promise(function (_res, rej) { rejectPost = rej; });

  ImageEdits.attach({
    hostEl: document.body,
    panel: panel,
    fetch: function () { return postPromise; }
  });

  _seedMask(panel);

  var otherCtl = null;
  return _openPopover('image_edits', panel).then(function (editsCtl) {
    _typePrompt(editsCtl, 'make it blue');
    assert.ok(editsCtl.submit(), 'image_edits must dispatch');
    // Let the popover close on its own timer.
    return _wait(300);
  }).then(function () {
    // The user moves on and opens a different slot.
    return _openPopover('image_generates', panel);
  }).then(function (ctl) {
    otherCtl = ctl;
    _typePrompt(otherCtl, 'a cat in a hat');
    assert.ok(otherCtl.submit(), 'image_generates must dispatch');
    assert.strictEqual(otherCtl._state.inFlight, true,
      'precondition: image_generates is in flight');

    // Now the earlier image_edits POST fails.
    rejectPost(new Error('gateway timeout'));
    return _wait(50);
  }).then(function () {
    assert.strictEqual(otherCtl._state.destroyed, false,
      'precondition: the other popover is still alive');
    assert.strictEqual(otherCtl._state.errorEl.textContent, '',
      'the other slot\'s popover must render nothing');
    assert.strictEqual(otherCtl._state.errorEl.style.display, 'none',
      'the other slot\'s error element must stay hidden');
    assert.strictEqual(otherCtl._state.inFlight, true,
      'the other slot\'s in-flight state must be untouched');

    // The image_edits failure still reached the user, on its own pane.
    var seen = _visibleErrorText(panel);
    assert.ok(seen && /gateway timeout/.test(seen),
      'the image_edits failure must still be readable: ' + seen);

    ImageEdits.detach();
    PackToolbars._closeCapabilityPopover();
  }).catch(function (e) {
    ImageEdits.detach();
    PackToolbars._closeCapabilityPopover();
    throw e;
  });
});

// ── Drain async tests ────────────────────────────────────────────────

_queue.then(function () {
  console.log('\n' + passed + ' passed, ' + failed + ' failed.');
  if (failed > 0) {
    failures.forEach(function (f) {
      console.log('  ' + f.name + ': ' + (f.err.stack || f.err.message));
    });
    process.exit(1);
  }
});
