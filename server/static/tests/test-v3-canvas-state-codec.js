#!/usr/bin/env node
/* test-v3-canvas-state-codec.js — VI Phase 7 WP-7.10 (partial)
 *
 * Round-trip tests for v3-canvas-state-codec.js against a mocked
 * Konva interface. Verifies the data-flow contract without booting
 * a real Konva-in-Node setup (which is its own engineering project).
 * Real Konva rendering correctness is verified by browser smoke per
 * the WP-7.10 procedure doc; this harness catches the regression
 * class where codec changes break the schema or drop attrs.
 *
 * Run:
 *   node ~/ora/server/static/tests/test-v3-canvas-state-codec.js
 *
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var fs   = require('fs');
var path = require('path');

var ROOT = path.resolve(__dirname, '..');
var CODEC_PATH = path.join(ROOT, 'js', 'v3-canvas-state-codec.js');

// ── Mocked Konva interface ──────────────────────────────────────────────────

/* MockNode: implements the read surface (getClassName, getAttrs, id, name,
 * getChildren) plus the destroy() the deserializer cleanup path calls.
 * Construct via a constructor function so window.Konva.<Class> can call
 * `new Konva.Class(attrs)` and get back something the codec recognizes. */
function makeNodeClass(className) {
  function NodeCtor(attrs) {
    this._className = className;
    this._attrs = Object.assign({}, attrs || {});
    this._children = [];
    this._destroyed = false;
    this._parent = null;
  }
  NodeCtor.prototype.getClassName = function () { return this._className; };
  NodeCtor.prototype.getAttrs = function () { return this._attrs; };
  NodeCtor.prototype.id = function () { return this._attrs.id || ''; };
  NodeCtor.prototype.name = function () { return this._attrs.name || ''; };
  NodeCtor.prototype.getChildren = function () { return this._children.slice(); };
  NodeCtor.prototype.add = function (child) {
    this._children.push(child);
    if (child) child._parent = this;
    return this;
  };
  // Real Konva's destroy() removes the node from its parent. The codec's
  // _ensureLayerCleared relies on this — calling destroy() in a loop and
  // expecting the layer to end up empty.
  NodeCtor.prototype.destroy = function () {
    this._destroyed = true;
    if (this._parent && Array.isArray(this._parent._children)) {
      var idx = this._parent._children.indexOf(this);
      if (idx >= 0) this._parent._children.splice(idx, 1);
    }
  };
  return NodeCtor;
}

function makeLayer() {
  var layer = {
    _children: [],
    getChildren: function () { return this._children.slice(); },
    removeChildren: function () {
      // Mirror Konva semantics: detach each child from its parent ref.
      this._children.forEach(function (c) { c._parent = null; });
      this._children = [];
    },
    add: function (n) {
      this._children.push(n);
      if (n) n._parent = this;
      return this;
    },
    draw: function () { /* no-op */ },
  };
  return layer;
}

function makePanel() {
  return {
    userInputLayer: makeLayer(),
    annotationLayer: makeLayer(),
    selectionLayer: makeLayer(),
    backgroundLayer: makeLayer(),
    _zoom: 1,
  };
}

// Mock Image constructor for image-data round-trip. The codec uses
// `new Image()` and reads .src; jsdom would provide this, but we keep
// the harness pure-Node by stubbing.
function MockImage() { this.src = ''; }

// Boot the codec module against a global window stub.
function bootCodec() {
  var KonvaStub = {
    Rect:  makeNodeClass('Rect'),
    Text:  makeNodeClass('Text'),
    Image: makeNodeClass('Image'),
    Group: makeNodeClass('Group'),
    Line:  makeNodeClass('Line'),
    Arrow: makeNodeClass('Arrow'),
    Ellipse: makeNodeClass('Ellipse'),
    Circle: makeNodeClass('Circle'),
    Path:  makeNodeClass('Path'),
  };
  var sandbox = {
    window: {
      Konva: KonvaStub,
      OraV3CanvasStateCodec: null,
    },
    document: {
      createElement: function () {
        // Used only for the offscreen-canvas image-bytes path; we never
        // hit this in tests because we always use data: URLs as input.
        return { width: 0, height: 0, getContext: function () { return null; } };
      },
      addEventListener: function () { /* no-op for tests */ },
      removeEventListener: function () { /* no-op for tests */ },
    },
    Image: MockImage,
    console: console,
    Date: Date,
    Object: Object,
    Math: Math,
    Array: Array,
    JSON: JSON,
  };
  // The codec is an IIFE that closes over `window`. Run it in our sandbox.
  var src = fs.readFileSync(CODEC_PATH, 'utf8');
  var vm = require('vm');
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  var codec = sandbox.window.OraV3CanvasStateCodec;
  if (!codec) {
    throw new Error('codec did not register on window after eval');
  }
  return { codec: codec, Konva: KonvaStub, panelCtor: makePanel };
}

// ── Test framework ──────────────────────────────────────────────────────────

var pass = 0;
var fail = 0;

function test(name, fn) {
  try {
    fn();
    pass++;
    console.log('  ✓ ' + name);
  } catch (e) {
    fail++;
    console.log('  ✗ ' + name);
    console.log('    ' + (e && e.stack ? e.stack : e));
  }
}

function assertEqual(actual, expected, msg) {
  var ok = (actual === expected) ||
           (actual && expected && JSON.stringify(actual) === JSON.stringify(expected));
  if (!ok) {
    throw new Error((msg || 'assertion') + ': expected ' + JSON.stringify(expected)
      + ', got ' + JSON.stringify(actual));
  }
}

function assertTrue(cond, msg) {
  if (!cond) throw new Error(msg || 'expected truthy');
}

// ── Tests ───────────────────────────────────────────────────────────────────

console.log('test-v3-canvas-state-codec.js');

var ctx = bootCodec();
var codec = ctx.codec;
var Konva = ctx.Konva;
var makePanelLocal = ctx.panelCtor;

test('serializeFromPanel produces valid envelope', function () {
  var panel = makePanelLocal();
  var rect = new Konva.Rect({ id: 'r1', x: 10, y: 20, width: 100, height: 50, fill: '#ff0000' });
  panel.userInputLayer.add(rect);

  var state = codec.serializeFromPanel(panel, { title: 'Test' });
  assertEqual(state.format_id, 'ora-canvas');
  assertEqual(state.schema_version, '0.1');
  assertEqual(state.metadata.title, 'Test');
  assertTrue(Array.isArray(state.objects), 'objects must be an array');
  assertEqual(state.objects.length, 1);
  assertEqual(state.objects[0].konva_class, 'Rect');
  assertEqual(state.objects[0].layer, 'user_input');
  assertEqual(state.objects[0].x, 10);
  assertEqual(state.objects[0].width, 100);
});

test('round-trip preserves shape attrs', function () {
  var panel = makePanelLocal();
  panel.userInputLayer.add(new Konva.Rect({
    id: 'r1', x: 10, y: 20, width: 100, height: 50,
    fill: '#ff0000', stroke: '#000000', strokeWidth: 2,
  }));
  panel.userInputLayer.add(new Konva.Text({
    id: 't1', x: 50, y: 60, text: 'Hello',
    fontSize: 18, fontFamily: 'Arial', fill: '#222',
  }));

  var state = codec.serializeFromPanel(panel);

  // Clear and reload.
  var panel2 = makePanelLocal();
  codec.deserializeIntoPanel(panel2, state);

  var nodes = panel2.userInputLayer.getChildren();
  assertEqual(nodes.length, 2);
  // Rectangle attrs preserved.
  var rect = nodes.find(function (n) { return n.getClassName() === 'Rect'; });
  assertTrue(rect, 'rect survived round-trip');
  assertEqual(rect.getAttrs().fill, '#ff0000');
  assertEqual(rect.getAttrs().width, 100);
  assertEqual(rect.id(), 'r1');
  // Text attrs preserved.
  var text = nodes.find(function (n) { return n.getClassName() === 'Text'; });
  assertTrue(text, 'text survived round-trip');
  assertEqual(text.getAttrs().text, 'Hello');
  assertEqual(text.getAttrs().fontSize, 18);
});

test('group children round-trip', function () {
  var panel = makePanelLocal();
  var group = new Konva.Group({ id: 'g1', x: 0, y: 0, name: 'speech' });
  group.add(new Konva.Rect({ id: 'g1-bg', width: 200, height: 100, fill: '#ffffff' }));
  group.add(new Konva.Text({ id: 'g1-txt', text: 'Hi', name: 'bubble-text' }));
  panel.userInputLayer.add(group);

  var state = codec.serializeFromPanel(panel);
  assertEqual(state.objects.length, 1);
  assertEqual(state.objects[0].konva_class, 'Group');
  assertTrue(Array.isArray(state.objects[0].children), 'group must have children array');
  assertEqual(state.objects[0].children.length, 2);

  // Round-trip.
  var panel2 = makePanelLocal();
  codec.deserializeIntoPanel(panel2, state);
  var nodes = panel2.userInputLayer.getChildren();
  assertEqual(nodes.length, 1);
  assertEqual(nodes[0].getClassName(), 'Group');
  assertEqual(nodes[0].getChildren().length, 2);
});

test('group skips tail-anchor and panel-grid-handle children', function () {
  var panel = makePanelLocal();
  var group = new Konva.Group({ id: 'b1', name: 'speech' });
  group.add(new Konva.Rect({ id: 'b1-body' }));
  group.add(new Konva.Circle({ id: 'b1-anchor', name: 'tail-anchor' }));
  group.add(new Konva.Rect({ id: 'b1-handle', name: 'panel-grid-handle' }));
  panel.userInputLayer.add(group);

  var state = codec.serializeFromPanel(panel);
  // Transient overlay siblings stripped.
  assertEqual(state.objects[0].children.length, 1);
  assertEqual(state.objects[0].children[0].id, 'b1-body');
});

test('image binaries dedup via content hash', function () {
  var panel = makePanelLocal();
  var fakeImg = { src: 'data:image/png;base64,iVBORw0KGgo=' };
  panel.userInputLayer.add(new Konva.Image({
    id: 'i1', x: 0, y: 0, width: 50, height: 50, image: fakeImg,
  }));
  panel.userInputLayer.add(new Konva.Image({
    id: 'i2', x: 100, y: 0, width: 50, height: 50, image: fakeImg,
  }));

  var state = codec.serializeFromPanel(panel);
  // Both objects should reference the same binary.
  assertEqual(state.objects.length, 2);
  var refs = state.objects.map(function (o) { return o.image_data_ref; }).filter(Boolean);
  assertEqual(refs.length, 2);
  assertEqual(refs[0], refs[1]);
  // The binary appears once in the binaries map.
  assertTrue(state.binaries && state.binaries[refs[0]],
             'binaries map must contain the dedupe target');
  assertEqual(state.binaries[refs[0]].mime_type, 'image/png');
});

test('multiple layers serialize with correct kind tags', function () {
  var panel = makePanelLocal();
  panel.userInputLayer.add(new Konva.Rect({ id: 'u1' }));
  panel.annotationLayer.add(new Konva.Line({ id: 'a1', points: [0,0,10,10] }));

  var state = codec.serializeFromPanel(panel);
  var byLayer = {};
  state.objects.forEach(function (o) { byLayer[o.layer] = o.id; });
  assertEqual(byLayer.user_input, 'u1');
  assertEqual(byLayer.annotation, 'a1');
});

test('deserialize on empty objects is a no-op (defensive)', function () {
  var panel = makePanelLocal();
  panel.userInputLayer.add(new Konva.Rect({ id: 'pre' }));
  // Empty state with no objects should not crash, but does clear layers.
  codec.deserializeIntoPanel(panel, { objects: [] });
  // Empty objects array → all user shapes removed.
  assertEqual(panel.userInputLayer.getChildren().length, 0);
});

test('deserialize ignores entries without konva_class', function () {
  var panel = makePanelLocal();
  codec.deserializeIntoPanel(panel, {
    objects: [
      { id: 'bad' /* no konva_class */ },
      { id: 'good', konva_class: 'Rect', layer: 'user_input', attrs: { x: 5 } },
    ],
  });
  var kids = panel.userInputLayer.getChildren();
  assertEqual(kids.length, 1);
  assertEqual(kids[0].id(), 'good');
});

test('id is mirrored into attrs so node.id() works post-deserialize', function () {
  var panel = makePanelLocal();
  panel.userInputLayer.add(new Konva.Rect({ id: 'orig-id', x: 1 }));
  var state = codec.serializeFromPanel(panel);
  var panel2 = makePanelLocal();
  codec.deserializeIntoPanel(panel2, state);
  var n = panel2.userInputLayer.getChildren()[0];
  assertEqual(n.id(), 'orig-id');
});

// ── summary ─────────────────────────────────────────────────────────────────

console.log('');
console.log('Results: ' + pass + ' passed, ' + fail + ' failed');
process.exit(fail > 0 ? 1 : 0);
