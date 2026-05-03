#!/usr/bin/env node
/* test-rect-selection.js — WP-7.5.1a
 *
 * Standalone Node test for the rectangle selection tool. Covers:
 *   1. buildRectangleMask: pure stage→image-natural conversion + clipping.
 *   2. Outside-image + zero-area edge cases return null.
 *   3. Tool lifecycle (init/activate/begin/update/commit/deactivate) drives
 *      the mask dispatch and produces a SelectionMask matching the
 *      drawn shape.
 *   4. Escape + tool-switch deactivation clears selection state.
 *   5. Schema-shape regression: `image_ref`, `geometry`, `bbox`, `kind`
 *      all present, `kind === 'rectangle'`, `bbox` matches geometry.
 *
 * Run:  node ~/ora/server/static/tests/tools/test-rect-selection.js
 * Exit: 0 on full pass, 1 on any failure.
 */

'use strict';

var path = require('path');
var TOOL_PATH = path.resolve(__dirname, '..', '..', 'tools', 'rect-selection.tool.js');
var Tool = require(TOOL_PATH);

// ── tiny test harness ─────────────────────────────────────────────────────

var passed = 0;
var failed = 0;
var failures = [];

function ok(cond, label) {
  if (cond) { passed++; console.log('  pass  ' + label); }
  else      { failed++; failures.push(label); console.log('  FAIL  ' + label); }
}

function eq(a, b, label) {
  ok(a === b, label + '  (expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a) + ')');
}

function near(a, b, tol, label) {
  ok(Math.abs(a - b) <= tol, label + '  (expected ~' + b + ' ±' + tol + ', got ' + a + ')');
}

function section(name) { console.log('\n[' + name + ']'); }

// ── fakes for Konva stage / image / layer ─────────────────────────────────

function fakeImage(opts) {
  // Konva.Image-like duck. Supports the function-style accessors used by
  // buildRectangleMask + the tool's drag flow.
  var x = opts.x, y = opts.y, w = opts.width, h = opts.height;
  return {
    x:      function () { return x; },
    y:      function () { return y; },
    width:  function () { return w; },
    height: function () { return h; },
    id:     function () { return opts.id || ''; },
    name:   function () { return opts.name || ''; },
    attrs: {
      naturalWidth:  opts.naturalWidth,
      naturalHeight: opts.naturalHeight,
      sourceName:    opts.sourceName || 'fake.png',
      image_id:      opts.image_id || null,
    },
  };
}

function fakeLayer() {
  var listening = true;
  var children = [];
  return {
    listening: function (val) {
      if (arguments.length === 0) return listening;
      listening = val;
      return this;
    },
    add: function (node) { children.push(node); return this; },
    draw: function () { /* no-op */ },
    batchDraw: function () { /* no-op */ },
    destroyChildren: function () { children.length = 0; },
    _children: children,
  };
}

function fakeStage() {
  // Konva uses dot-namespaced event names (`mousedown.rect-selection`); when
  // a generic `mousedown` is fired, all handlers registered under any
  // namespace of the same base event should fire. Mirror that here.
  var handlers = {};   // base-event -> [{ fullName, fn }]
  var pointer  = { x: 0, y: 0 };
  function baseOf(name) { return String(name).split('.')[0]; }
  return {
    on: function (eventNames, fn) {
      String(eventNames).split(/\s+/).forEach(function (name) {
        var base = baseOf(name);
        if (!handlers[base]) handlers[base] = [];
        handlers[base].push({ fullName: name, fn: fn });
      });
    },
    off: function (eventNames) {
      String(eventNames).split(/\s+/).forEach(function (name) {
        var base = baseOf(name);
        if (!handlers[base]) return;
        if (name.indexOf('.') === -1) {
          delete handlers[base];
        } else {
          handlers[base] = handlers[base].filter(function (h) { return h.fullName !== name; });
        }
      });
    },
    fire: function (name, evt) {
      var base = baseOf(name);
      var arr = handlers[base];
      if (!arr) return;
      for (var i = 0; i < arr.length; i++) arr[i].fn(evt || {});
    },
    setPointer: function (x, y) { pointer.x = x; pointer.y = y; },
    getPointerPosition: function () { return { x: pointer.x, y: pointer.y }; },
  };
}

function fakePanel() {
  var listeners = {};
  return {
    el: {
      ownerDocument: { addEventListener: function () {}, removeEventListener: function () {} },
      dispatchEvent: function (evt) {
        var arr = listeners[evt.type] || [];
        arr.forEach(function (fn) { fn(evt); });
        return true;
      },
      addEventListener: function (type, fn) {
        if (!listeners[type]) listeners[type] = [];
        listeners[type].push(fn);
      },
    },
    stage:           fakeStage(),
    selectionLayer:  fakeLayer(),
    _backgroundImageNode: null,
    _activeImageNode:     null,
    _lastSelectionMask:   null,
  };
}

// Stub Konva so the tool's preview/committed rectangle paths run without
// the real library. We only need .Rect with attrs + .Animation.start/stop.
global.Konva = {
  Rect: function (attrs) {
    var self = this;
    self._attrs = Object.assign({}, attrs);
    self.x      = function () { return self._attrs.x; };
    self.y      = function () { return self._attrs.y; };
    self.width  = function () { return self._attrs.width;  };
    self.height = function () { return self._attrs.height; };
    self.dashOffset = function (v) { if (arguments.length) self._attrs.dashOffset = v; return self._attrs.dashOffset; };
    self.setAttrs = function (a) { Object.assign(self._attrs, a); return self; };
    self.destroy  = function () { self._destroyed = true; };
    return self;
  },
  Animation: function (cb, layer) {
    this._cb = cb; this._layer = layer;
    this.start = function () { this._running = true; };
    this.stop  = function () { this._running = false; };
  },
};

// ── 1. buildRectangleMask: pure conversion ────────────────────────────────

section('buildRectangleMask: pure stage→natural conversion');

var img1 = fakeImage({
  x: 50, y: 30, width: 200, height: 150,
  naturalWidth: 800, naturalHeight: 600,
  sourceName: 'photo.png', image_id: 'img-1',
});

// Selection rect inside the image: stage (60, 40) → (160, 90), i.e.
// from image-local (10, 10) to (110, 60) at stage scale, which maps to
// natural (40, 40) → (440, 240).
var mask1 = Tool.buildRectangleMask({
  imageNode: img1,
  stageRect: { x: 60, y: 40, width: 100, height: 50 },
});

ok(mask1 !== null, 'mask returned (not null)');
eq(mask1.kind, 'rectangle', 'kind === rectangle');
eq(mask1.schema_version, '1.0', 'schema_version === 1.0');
eq(mask1.image_ref.image_id, 'img-1', 'image_ref.image_id propagated');
eq(mask1.image_ref.natural_width,  800, 'image_ref.natural_width');
eq(mask1.image_ref.natural_height, 600, 'image_ref.natural_height');
eq(mask1.image_ref.source_name, 'photo.png', 'image_ref.source_name');

near(mask1.geometry.x,      40,  0.001, 'geometry.x in natural pixels');
near(mask1.geometry.y,      40,  0.001, 'geometry.y in natural pixels');
near(mask1.geometry.width,  400, 0.001, 'geometry.width in natural pixels');
near(mask1.geometry.height, 200, 0.001, 'geometry.height in natural pixels');

eq(mask1.bbox.x,      mask1.geometry.x,      'bbox.x mirrors geometry.x');
eq(mask1.bbox.y,      mask1.geometry.y,      'bbox.y mirrors geometry.y');
eq(mask1.bbox.width,  mask1.geometry.width,  'bbox.width mirrors geometry');
eq(mask1.bbox.height, mask1.geometry.height, 'bbox.height mirrors geometry');

ok(typeof mask1.created_at === 'string' && mask1.created_at.length > 10, 'created_at is ISO string');

// ── 2. Edge cases: clipping + outside + zero-area ──────────────────────────

section('buildRectangleMask: clipping + edge cases');

// Selection that overlaps the right edge: stage (200, 50) → (300, 100).
// Image AABB is (50..250, 30..180). Clipped to (200..250, 50..100).
// In image-local stage coords: (150..200, 20..70) → natural (600..800, 80..280).
var mask2 = Tool.buildRectangleMask({
  imageNode: img1,
  stageRect: { x: 200, y: 50, width: 100, height: 50 },
});
ok(mask2 !== null, 'partial overlap → non-null mask');
near(mask2.geometry.x, 600, 0.001, 'clipped geometry.x = 600');
near(mask2.geometry.width, 200, 0.001, 'clipped geometry.width = 200');

// Selection fully outside the image returns null.
var mask3 = Tool.buildRectangleMask({
  imageNode: img1,
  stageRect: { x: 500, y: 500, width: 50, height: 50 },
});
eq(mask3, null, 'fully-outside selection → null');

// Negative width: rect drawn right-to-left should normalise.
var mask4 = Tool.buildRectangleMask({
  imageNode: img1,
  stageRect: { x: 160, y: 90, width: -100, height: -50 },
});
ok(mask4 !== null, 'negative-width rect → non-null mask');
near(mask4.geometry.x,      40,  0.001, 'negative-width: geometry.x = 40');
near(mask4.geometry.width,  400, 0.001, 'negative-width: geometry.width = 400');

// ── 3. Tool lifecycle: drag → commit → mask dispatched ─────────────────────

section('Tool lifecycle: begin → update → commit');

var panel = fakePanel();
panel._backgroundImageNode = img1;

// Subscribe to the dispatch event before activating.
var receivedMask = null;
panel.el.addEventListener('ora:selection-mask', function (evt) {
  receivedMask = evt.detail.mask;
});

Tool.init(panel, {});
ok(Tool.panel === panel, 'init stashed panel');

Tool.activate({});
// Before any drag, no mask.
ok(panel._lastSelectionMask === null, 'no mask before drag');

// Begin drag at stage (60, 40).
panel.stage.setPointer(60, 40);
panel.stage.fire('mousedown', {});
ok(Tool._previewRect !== null, 'preview rect created on mousedown');
ok(Tool._dragStart && Tool._dragStart.x === 60, 'drag start recorded');

// Move to (160, 90).
panel.stage.setPointer(160, 90);
panel.stage.fire('mousemove', {});
eq(Tool._previewRect._attrs.width,  100, 'preview width updated to 100');
eq(Tool._previewRect._attrs.height,  50, 'preview height updated to 50');

// Commit at (160, 90).
panel.stage.fire('mouseup', {});
ok(panel._lastSelectionMask !== null, 'mask stashed on panel after mouseup');
ok(receivedMask !== null, 'CustomEvent fired with mask payload');
eq(receivedMask.kind, 'rectangle', 'dispatched mask kind === rectangle');
near(receivedMask.geometry.x,      40,  0.001, 'dispatched mask geometry.x');
near(receivedMask.geometry.width,  400, 0.001, 'dispatched mask geometry.width');
near(receivedMask.geometry.height, 200, 0.001, 'dispatched mask geometry.height');

// Mask shape matches drawn rectangle (per §13.5 test criterion).
near(receivedMask.bbox.x, receivedMask.geometry.x, 0.001, 'bbox matches selection shape (x)');
near(receivedMask.bbox.width, receivedMask.geometry.width, 0.001, 'bbox matches selection shape (width)');

// Marching ants animation should have started.
ok(Tool._marchingAnim && Tool._marchingAnim._running === true, 'marching ants animation running');

// ── 4. Escape clears, deactivate clears ────────────────────────────────────

section('Escape + deactivate clear selection');

// Manually invoke the escape listener (we registered it with the fake doc,
// which doesn't actually dispatch — call the captured listener directly).
ok(typeof Tool._escListener === 'function', 'escape listener registered');
Tool._escListener({ key: 'Escape' });
ok(panel._lastSelectionMask === null, 'Escape cleared mask');
ok(Tool._committedRect === null, 'Escape destroyed committed rect');
ok(Tool._marchingAnim === null, 'Escape stopped marching animation');

// Re-commit a selection, then deactivate the tool.
panel.stage.setPointer(60, 40); panel.stage.fire('mousedown', {});
panel.stage.setPointer(160, 90); panel.stage.fire('mousemove', {});
panel.stage.fire('mouseup', {});
ok(panel._lastSelectionMask !== null, 're-committed selection after Escape');

Tool.deactivate({});
ok(panel._lastSelectionMask === null, 'deactivate cleared mask');
ok(Tool._committedRect === null, 'deactivate destroyed committed rect');

// ── 5. Outside-image click is a no-op (tool stays armed) ───────────────────

section('Outside-image click is a no-op');

Tool.activate({});
panel.stage.setPointer(500, 500);  // beyond the image AABB
panel.stage.fire('mousedown', {});
panel.stage.setPointer(550, 550);
panel.stage.fire('mouseup', {});
// We won't crash; but mask dispatch should have been suppressed because
// the rect is fully outside the image (returns null in builder).
ok(panel._lastSelectionMask === null, 'outside-image drag does not commit a mask');

Tool.deactivate({});

// ── exit ───────────────────────────────────────────────────────────────────

console.log('\n' + passed + ' passed, ' + failed + ' failed');
if (failed > 0) {
  console.log('FAILURES:');
  failures.forEach(function (f) { console.log('  - ' + f); });
  process.exit(1);
}
process.exit(0);
