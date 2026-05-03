#!/usr/bin/env node
/* test-v3-panel-grid.js — VI Phase 7 WP-7.10 (extends 2026-05-01 harness pattern)
 *
 * Coverage for v3-panel-grid.js: adjacency derivation, handle placement,
 * clear/refresh lifecycle, and drag-clamping of the resize logic. Uses the
 * same mocked-Konva strategy as test-v3-canvas-state-codec.js — captures
 * registered event handlers at .on() time so we can invoke "dragmove"
 * deterministically without booting a real Konva-in-Node setup.
 *
 * Real Konva rendering and pointer events are verified by browser smoke per
 * the WP-7.10 procedure doc; this harness catches the regression class
 * where adjacency math, handle positioning, or drag-clamping breaks.
 *
 * Run:
 *   node ~/ora/server/static/tests/test-v3-panel-grid.js
 *
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var fs   = require('fs');
var path = require('path');
var vm   = require('vm');

var SRC = path.resolve(__dirname, '..', 'js', 'v3-panel-grid.js');

// ── Mocked Konva interface ──────────────────────────────────────────────────
//
// Each shape supports the getter/setter idiom Konva uses (call w/ no args =
// read; call w/ one arg = write). on() records handlers into _listeners so
// tests can fire('dragmove') deterministically. Layers track children.

function _gs(self, key) {
  return function (v) {
    if (arguments.length === 0) return self._attrs[key];
    self._attrs[key] = v;
    return self;
  };
}

function makeNode(className, attrs) {
  var self = {
    _className: className,
    _attrs: Object.assign({}, attrs || {}),
    _children: [],
    _listeners: {},
    _parent: null,
    _destroyed: false,
  };
  self.getClassName = function () { return self._className; };
  self.getAttrs = function () { return self._attrs; };
  self.getAttr = function (k) { return self._attrs[k]; };
  self.setAttr = function (k, v) { self._attrs[k] = v; return self; };
  self.id = function (v) {
    if (arguments.length === 0) return self._attrs.id || '';
    self._attrs.id = v; return self;
  };
  self.name = function (v) {
    if (arguments.length === 0) return self._attrs.name || '';
    self._attrs.name = v; return self;
  };
  self.x      = _gs(self, 'x');
  self.y      = _gs(self, 'y');
  self.width  = _gs(self, 'width');
  self.height = _gs(self, 'height');
  self.fill   = _gs(self, 'fill');
  self.getChildren = function () { return self._children.slice(); };
  self.add = function (child) {
    self._children.push(child);
    if (child) child._parent = self;
    return self;
  };
  self.destroy = function () {
    self._destroyed = true;
    if (self._parent && Array.isArray(self._parent._children)) {
      var idx = self._parent._children.indexOf(self);
      if (idx >= 0) self._parent._children.splice(idx, 1);
    }
  };
  self.on = function (eventName, fn) {
    // eventName may be space-separated or have a namespace ".tail".
    eventName.split(/\s+/).forEach(function (e) {
      var bare = e.split('.')[0];
      if (!self._listeners[bare]) self._listeners[bare] = [];
      self._listeners[bare].push(fn);
    });
    return self;
  };
  self.off = function (eventName) {
    if (!eventName) { self._listeners = {}; return self; }
    eventName.split(/\s+/).forEach(function (e) {
      var bare = e.split('.')[0];
      delete self._listeners[bare];
    });
    return self;
  };
  self.fire = function (eventName) {
    var bare = eventName.split('.')[0];
    var handlers = self._listeners[bare] || [];
    handlers.forEach(function (fn) { fn(); });
  };
  self.absolutePosition = function () {
    return { x: self._attrs.x || 0, y: self._attrs.y || 0 };
  };
  self.getAbsolutePosition = self.absolutePosition;
  self.getParent = function () { return self._parent; };
  self.getLayer = function () {
    var n = self._parent;
    while (n && !n._isLayer) n = n._parent;
    return n;
  };
  return self;
}

function ctor(className) {
  return function (attrs) { return makeNode(className, attrs); };
}

function makeLayer() {
  var layer = makeNode('Layer', {});
  layer._isLayer = true;
  // Mirror Konva: layer.find('.name') returns descendants whose name attr matches.
  layer.find = function (selector) {
    var nameMatch = (selector || '').replace(/^\./, '');
    var out = [];
    function walk(n) {
      (n._children || []).forEach(function (c) {
        if (c.getAttr && c.getAttr('name') === nameMatch) out.push(c);
        walk(c);
      });
    }
    walk(layer);
    return out;
  };
  layer.draw = function () { /* no-op */ };
  layer.removeChildren = function () {
    layer._children.forEach(function (c) { c._parent = null; });
    layer._children = [];
  };
  return layer;
}

function makePanel() {
  var layer = makeLayer();
  var panel = {
    userInputLayer: layer,
    stage: { on: function () {}, off: function () {} },
    el: {
      querySelector: function () { return null; },
    },
    _konvaEl: null,
  };
  return panel;
}

// ── Boot v3-panel-grid.js into a sandbox ───────────────────────────────────

function bootModule() {
  var sandbox = {
    window: {
      Konva: {
        Rect:    ctor('Rect'),
        Line:    ctor('Line'),
        Ellipse: ctor('Ellipse'),
        Circle:  ctor('Circle'),
        Text:    ctor('Text'),
        Group:   ctor('Group'),
      },
    },
    document: {
      addEventListener: function () {},
      removeEventListener: function () {},
    },
    setTimeout: function (fn) { return 0; },
    clearTimeout: function () {},
    console: { log: function () {}, info: function () {}, warn: function () {}, error: function () {} },
    Math: Math, Object: Object, Array: Array, JSON: JSON,
    isFinite: isFinite, parseInt: parseInt, parseFloat: parseFloat,
    Infinity: Infinity, WeakMap: WeakMap,
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(SRC, 'utf8'), sandbox);
  return {
    OraV3PanelGrid: sandbox.window.OraV3PanelGrid,
    Konva: sandbox.window.Konva,
  };
}

// ── Test framework ─────────────────────────────────────────────────────────

var pass = 0, fail = 0;
function test(name, fn) {
  try { fn(); pass++; console.log('  ✓ ' + name); }
  catch (e) {
    fail++;
    console.log('  ✗ ' + name);
    console.log('    ' + (e && e.stack ? e.stack : e));
  }
}
function assertEqual(a, b, msg) {
  var ok = (a === b) || (a && b && JSON.stringify(a) === JSON.stringify(b));
  if (!ok) throw new Error((msg || 'assertion')
                           + ': expected ' + JSON.stringify(b)
                           + ', got ' + JSON.stringify(a));
}
function assertTrue(c, m) { if (!c) throw new Error(m || 'expected truthy'); }
function assertFalse(c, m) { if (c) throw new Error(m || 'expected falsy'); }

// ── Helpers ────────────────────────────────────────────────────────────────

function panelRect(K, x, y, w, h) {
  var r = K.Rect({ x: x, y: y, width: w, height: h });
  r.setAttr('panel', true);
  return r;
}

function nonPanelRect(K, x, y, w, h) {
  return K.Rect({ x: x, y: y, width: w, height: h });
}

function findHandles(panel) {
  return panel.userInputLayer.getChildren().filter(function (n) {
    return n.getAttr && n.getAttr('name') === 'panel-grid-handle';
  });
}

// ─────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────

console.log('test-v3-panel-grid.js — adjacency derivation + handle lifecycle');

var booted = bootModule();
var Grid = booted.OraV3PanelGrid;
var Konva = booted.Konva;

// ── module surface ────────────────────────────────────────────────────────

test('exports refresh + clear', function () {
  assertTrue(typeof Grid.refresh === 'function', 'refresh missing');
  assertTrue(typeof Grid.clear === 'function', 'clear missing');
});

// ── refresh on degenerate layouts ────────────────────────────────────────

test('refresh on empty panel adds no handles', function () {
  var panel = makePanel();
  Grid.refresh(panel);
  assertEqual(findHandles(panel).length, 0);
});

test('refresh on a single panel-rect adds no handles (need two adjacent)', function () {
  var panel = makePanel();
  panel.userInputLayer.add(panelRect(Konva, 0, 0, 200, 200));
  Grid.refresh(panel);
  assertEqual(findHandles(panel).length, 0);
});

test('refresh ignores non-panel rects', function () {
  var panel = makePanel();
  panel.userInputLayer.add(nonPanelRect(Konva, 0, 0, 200, 200));
  panel.userInputLayer.add(nonPanelRect(Konva, 220, 0, 200, 200));
  Grid.refresh(panel);
  assertEqual(findHandles(panel).length, 0);
});

// ── horizontal-split (vertical handle) detection ─────────────────────────

test('two panels side-by-side with 20px gutter → 1 vertical handle', function () {
  var panel = makePanel();
  panel.userInputLayer.add(panelRect(Konva, 0,   0, 200, 200));
  panel.userInputLayer.add(panelRect(Konva, 220, 0, 200, 200));
  Grid.refresh(panel);
  var handles = findHandles(panel);
  assertEqual(handles.length, 1, 'expected exactly 1 vertical handle');
  // Vertical handle: width = HANDLE_THICKNESS (18), height = y1 - y0.
  assertEqual(handles[0].width(), 18);
  assertEqual(handles[0].height(), 200);
});

test('two panels side-by-side touching (0 gutter) → 1 vertical handle', function () {
  var panel = makePanel();
  panel.userInputLayer.add(panelRect(Konva, 0,   0, 200, 200));
  panel.userInputLayer.add(panelRect(Konva, 200, 0, 200, 200));
  Grid.refresh(panel);
  assertEqual(findHandles(panel).length, 1);
});

test('two panels with gutter > MAX_GUTTER (200) → no handle', function () {
  var panel = makePanel();
  panel.userInputLayer.add(panelRect(Konva, 0,   0, 200, 200));
  panel.userInputLayer.add(panelRect(Konva, 410, 0, 200, 200));
  Grid.refresh(panel);
  assertEqual(findHandles(panel).length, 0);
});

test('two panels with insufficient Y-overlap (< MIN_OVERLAP) → no handle', function () {
  var panel = makePanel();
  panel.userInputLayer.add(panelRect(Konva, 0,   0,  200, 100));
  // Second panel starts at y=120 (only 0px overlap with first).
  panel.userInputLayer.add(panelRect(Konva, 220, 120, 200, 100));
  Grid.refresh(panel);
  assertEqual(findHandles(panel).length, 0);
});

// ── vertical-split (horizontal handle) detection ─────────────────────────

test('two panels stacked with 20px gutter → 1 horizontal handle', function () {
  var panel = makePanel();
  panel.userInputLayer.add(panelRect(Konva, 0, 0,   200, 200));
  panel.userInputLayer.add(panelRect(Konva, 0, 220, 200, 200));
  Grid.refresh(panel);
  var handles = findHandles(panel);
  assertEqual(handles.length, 1, 'expected exactly 1 horizontal handle');
  assertEqual(handles[0].height(), 18);
  assertEqual(handles[0].width(), 200);
});

// ── 2x2 grid ─────────────────────────────────────────────────────────────

test('2x2 grid → 2 handles (1 vertical + 1 horizontal)', function () {
  var panel = makePanel();
  panel.userInputLayer.add(panelRect(Konva, 0,   0,   200, 200));
  panel.userInputLayer.add(panelRect(Konva, 220, 0,   200, 200));
  panel.userInputLayer.add(panelRect(Konva, 0,   220, 200, 200));
  panel.userInputLayer.add(panelRect(Konva, 220, 220, 200, 200));
  Grid.refresh(panel);
  var handles = findHandles(panel);
  assertEqual(handles.length, 2, 'expected 2 handles in 2×2 grid');
});

// ── clear() ──────────────────────────────────────────────────────────────

test('clear removes handles tracked from prior refresh', function () {
  var panel = makePanel();
  panel.userInputLayer.add(panelRect(Konva, 0,   0, 200, 200));
  panel.userInputLayer.add(panelRect(Konva, 220, 0, 200, 200));
  Grid.refresh(panel);
  assertEqual(findHandles(panel).length, 1);
  Grid.clear(panel);
  assertEqual(findHandles(panel).length, 0);
});

test('clear is idempotent on a panel with no handles', function () {
  var panel = makePanel();
  Grid.clear(panel); // no-op, must not throw
  assertEqual(findHandles(panel).length, 0);
});

test('clear removes orphan panel-grid-handles even if not in WeakMap', function () {
  var panel = makePanel();
  // Manually add an "orphan" handle (not from refresh, not in _handlesByPanel).
  var orphan = Konva.Rect({ x: 0, y: 0, width: 18, height: 100 });
  orphan.setAttr('name', 'panel-grid-handle');
  panel.userInputLayer.add(orphan);
  Grid.clear(panel);
  assertEqual(findHandles(panel).length, 0, 'orphan handle should be destroyed');
});

test('refresh re-derives handles cleanly after layout change', function () {
  var panel = makePanel();
  var leftP  = panelRect(Konva, 0,   0, 200, 200);
  var rightP = panelRect(Konva, 220, 0, 200, 200);
  panel.userInputLayer.add(leftP);
  panel.userInputLayer.add(rightP);
  Grid.refresh(panel);
  assertEqual(findHandles(panel).length, 1);

  // Move right panel beyond MAX_GUTTER → next refresh should drop the handle.
  rightP.x(500);
  Grid.refresh(panel);
  assertEqual(findHandles(panel).length, 0);
});

// ── drag-resize math via simulated dragmove ──────────────────────────────
//
// We capture the dragmove handler at .on() time and invoke it after moving
// the handle's x. The clamping logic + panel-resize delta should fire.

test('vertical handle dragmove resizes both adjacent panels', function () {
  var panel = makePanel();
  var L = panelRect(Konva, 0,   0, 200, 200);
  var R = panelRect(Konva, 220, 0, 200, 200);
  panel.userInputLayer.add(L);
  panel.userInputLayer.add(R);
  Grid.refresh(panel);
  var handle = findHandles(panel)[0];

  // Simulate dragging right by 30px. Initial midX = 210, halfGutter = 10.
  // newMidX = 240 → leftEdge = 230, rightEdge = 250.
  // L.width = 230 - 0 = 230. R.x = 250, R.width = 420 - 250 = 170.
  handle.x(240 - 18 / 2); // handle.x stores top-left, so subtract HANDLE_THICKNESS/2
  handle.fire('dragmove');

  assertEqual(L.width(), 230, 'left panel should grow to 230');
  assertEqual(R.x(), 250, 'right panel x should shift to 250');
  assertEqual(R.width(), 170, 'right panel width should shrink to 170');
});

test('vertical handle dragmove clamps to MIN_PANEL_SIZE', function () {
  var panel = makePanel();
  var L = panelRect(Konva, 0,   0, 200, 200);
  var R = panelRect(Konva, 220, 0, 200, 200);
  panel.userInputLayer.add(L);
  panel.userInputLayer.add(R);
  Grid.refresh(panel);
  var handle = findHandles(panel)[0];

  // Try to drag the handle WAY left (would crush the left panel). Clamp
  // should prevent left panel's width from going below MIN_PANEL_SIZE (60).
  handle.x(-500);
  handle.fire('dragmove');

  assertTrue(L.width() >= 60, 'left panel should be ≥ MIN_PANEL_SIZE; got ' + L.width());
});

test('horizontal handle dragmove resizes top + bottom panels', function () {
  var panel = makePanel();
  var T = panelRect(Konva, 0, 0,   200, 200);
  var B = panelRect(Konva, 0, 220, 200, 200);
  panel.userInputLayer.add(T);
  panel.userInputLayer.add(B);
  Grid.refresh(panel);
  var handle = findHandles(panel)[0];

  // Drag down 30px. Initial midY = 210, halfGutter = 10. newMidY = 240.
  // topEdge = 230, bottomEdge = 250. T.height = 230, B.y = 250, B.height = 170.
  handle.y(240 - 18 / 2);
  handle.fire('dragmove');

  assertEqual(T.height(), 230, 'top panel should grow to 230');
  assertEqual(B.y(), 250, 'bottom panel y should shift to 250');
  assertEqual(B.height(), 170, 'bottom panel height should shrink to 170');
});

// ── result ────────────────────────────────────────────────────────────────

console.log('\n  ' + pass + ' passed, ' + fail + ' failed');
process.exit(fail === 0 ? 0 : 1);
