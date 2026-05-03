#!/usr/bin/env node
/* test-v3-bubble-tools.js — VI Phase 7 WP-7.10 (extends 2026-05-01 harness pattern)
 *
 * Coverage for v3-bubble-tools.js: 4 bubble builders (speech / thought /
 * shout / caption), placeAt placement, tail-anchor attachment, and the
 * bubble↔target linking flow (drag tail-anchor over another shape →
 * linkedTarget attr set; drag over empty space → unlinked).
 *
 * Strategy: mocked Konva captures registered handlers at .on() time so we
 * can simulate dragend deterministically. Mock supports:
 *   - getter/setter idiom (x(), x(v))
 *   - getChildren, add, destroy
 *   - getAbsolutePosition for hit-testing
 *   - Stage.findOne via id index
 *   - on/off/fire with namespace stripping
 *
 * Real Konva rendering and pointer events are verified by browser smoke per
 * the WP-7.10 procedure doc; this harness catches the regression class
 * where builder structure, anchor wiring, or link state mutation breaks.
 *
 * Run:
 *   node ~/ora/server/static/tests/test-v3-bubble-tools.js
 *
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var fs   = require('fs');
var path = require('path');
var vm   = require('vm');

var SRC = path.resolve(__dirname, '..', 'js', 'v3-bubble-tools.js');

// ── Mocked Konva interface ──────────────────────────────────────────────────

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
  self.x        = _gs(self, 'x');
  self.y        = _gs(self, 'y');
  self.width    = _gs(self, 'width');
  self.height   = _gs(self, 'height');
  self.fill     = _gs(self, 'fill');
  self.opacity  = _gs(self, 'opacity');
  self.points   = _gs(self, 'points');
  self.radiusX  = _gs(self, 'radiusX');
  self.radiusY  = _gs(self, 'radiusY');
  self.text     = _gs(self, 'text');
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
    var handlers = (self._listeners[bare] || []).slice();
    handlers.forEach(function (fn) { fn(); });
  };
  self.absolutePosition = function () {
    // Walk parents accumulating x/y. Approximate (no rotation/scale).
    var ax = 0, ay = 0, n = self;
    while (n) {
      ax += (n._attrs && typeof n._attrs.x === 'number') ? n._attrs.x : 0;
      ay += (n._attrs && typeof n._attrs.y === 'number') ? n._attrs.y : 0;
      n = n._parent;
      if (n && n._isLayer) break;
    }
    return { x: ax, y: ay };
  };
  self.getAbsolutePosition = self.absolutePosition;
  self.getParent = function () { return self._parent; };
  self.getLayer = function () {
    var n = self._parent;
    while (n && !n._isLayer) n = n._parent;
    return n;
  };
  self.getStage = function () {
    var layer = self.getLayer();
    return layer ? layer._stage : null;
  };
  self.getClientRect = function () {
    var pos = self.getAbsolutePosition();
    return {
      x: pos.x, y: pos.y,
      width:  self._attrs.width || 0,
      height: self._attrs.height || 0
    };
  };
  // Konva nodes (Group/Layer) support find('.name') to walk descendants.
  // Some bubble code paths call group.find('.bubble-tail') so the mock
  // needs find on every node, not just the layer.
  self.find = function (selector) {
    var nameMatch = (selector || '').replace(/^\./, '');
    var out = [];
    function walk(n) {
      (n._children || []).forEach(function (c) {
        if (c.getAttr && c.getAttr('name') === nameMatch) out.push(c);
        walk(c);
      });
    }
    walk(self);
    return out;
  };
  return self;
}

function ctor(className) {
  return function (attrs) { return makeNode(className, attrs); };
}

function makeLayer(stage) {
  var layer = makeNode('Layer', {});
  layer._isLayer = true;
  layer._stage = stage;
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
  return layer;
}

function makeStage(panel) {
  var stage = {
    _panel: panel,
    on: function () {}, off: function () {},
    findOne: function (selector) {
      // Support '#id' lookups against the layer's user-shape children.
      var idMatch = (selector || '').replace(/^#/, '');
      var found = null;
      function walk(n) {
        if (found) return;
        if (n.id && n.id() === idMatch) { found = n; return; }
        (n._children || []).forEach(walk);
      }
      walk(panel.userInputLayer);
      return found;
    },
    getPointerPosition: function () { return { x: 0, y: 0 }; },
  };
  return stage;
}

function makePanel() {
  var panel = {};
  panel.userInputLayer = makeLayer(null);
  panel.stage = makeStage(panel);
  panel.userInputLayer._stage = panel.stage;
  panel.el = { querySelector: function () { return null; } };
  panel._konvaEl = null;
  return panel;
}

// ── Boot v3-bubble-tools.js into a sandbox ─────────────────────────────────

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
      OraCanvas: null,
    },
    document: {
      addEventListener: function () {},
      removeEventListener: function () {},
    },
    setTimeout: function () { return 0; },
    clearTimeout: function () {},
    console: { log: function () {}, info: function () {}, warn: function () {}, error: function () {} },
    Date: Date,
    Math: Math, Object: Object, Array: Array, JSON: JSON,
    isFinite: isFinite, parseInt: parseInt, parseFloat: parseFloat,
    Infinity: Infinity,
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(SRC, 'utf8'), sandbox);
  return {
    OraV3BubbleTools: sandbox.window.OraV3BubbleTools,
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

// ── helpers ────────────────────────────────────────────────────────────────

function findChildByName(group, name) {
  var kids = group.getChildren();
  for (var i = 0; i < kids.length; i++) {
    if (kids[i].getAttr && kids[i].getAttr('name') === name) return kids[i];
  }
  return null;
}

function findChildByClass(group, className) {
  var kids = group.getChildren();
  for (var i = 0; i < kids.length; i++) {
    if (kids[i].getClassName && kids[i].getClassName() === className) return kids[i];
  }
  return null;
}

function findChildrenByClass(group, className) {
  return group.getChildren().filter(function (k) {
    return k.getClassName && k.getClassName() === className;
  });
}

// ─────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────

console.log('test-v3-bubble-tools.js — builders + placement + bubble↔target linking');

var booted = bootModule();
var Bubbles = booted.OraV3BubbleTools;
var Konva = booted.Konva;

// ── module surface ────────────────────────────────────────────────────────

test('exports placeAt + activateTool + _disarm', function () {
  assertTrue(typeof Bubbles.placeAt === 'function');
  assertTrue(typeof Bubbles.activateTool === 'function');
  assertTrue(typeof Bubbles._disarm === 'function');
});

// ── placeAt validation ───────────────────────────────────────────────────

test('placeAt with null panel returns null', function () {
  assertEqual(Bubbles.placeAt(null, 'speech', 0, 0), null);
});

test('placeAt with unknown kind returns null', function () {
  var panel = makePanel();
  assertEqual(Bubbles.placeAt(panel, 'unknown-kind', 0, 0), null);
});

// ── speech bubble ────────────────────────────────────────────────────────

test('speech: Group with bubble-body Rect + bubble-tail Line + bubble-text Text', function () {
  var panel = makePanel();
  var node = Bubbles.placeAt(panel, 'speech', 100, 200);
  assertTrue(node !== null, 'placeAt should return a node');
  assertEqual(node.getClassName(), 'Group');
  assertEqual(node.getAttr('bubbleKind'), 'speech');
  assertEqual(node.getAttr('name'), 'user-shape');
  assertEqual(node.getAttr('draggable'), true);
  assertEqual(node.x(), 100);
  assertEqual(node.y(), 200);

  var body = findChildByName(node, 'bubble-body');
  var tail = findChildByName(node, 'bubble-tail');
  var label = findChildByName(node, 'bubble-text');
  assertTrue(body !== null && body.getClassName() === 'Rect', 'bubble-body Rect missing');
  assertTrue(tail !== null && tail.getClassName() === 'Line', 'bubble-tail Line missing');
  assertTrue(label !== null && label.getClassName() === 'Text', 'bubble-text Text missing');

  // Speech tail: closed Line w/ 3 points (6 numbers).
  assertEqual(tail.points().length, 6, 'speech tail should have 6 point-numbers');
});

test('speech: default placeholder text is "Hello!"', function () {
  var panel = makePanel();
  var node = Bubbles.placeAt(panel, 'speech', 0, 0);
  assertEqual(findChildByName(node, 'bubble-text').text(), 'Hello!');
});

test('speech: opts.text overrides placeholder', function () {
  var panel = makePanel();
  var node = Bubbles.placeAt(panel, 'speech', 0, 0, { text: 'WHO ME?' });
  assertEqual(findChildByName(node, 'bubble-text').text(), 'WHO ME?');
});

// ── thought bubble ───────────────────────────────────────────────────────

test('thought: Ellipse body + 3 trail ellipses + bubble-text', function () {
  var panel = makePanel();
  var node = Bubbles.placeAt(panel, 'thought', 0, 0);
  assertEqual(node.getAttr('bubbleKind'), 'thought');

  var body = findChildByName(node, 'bubble-body');
  assertTrue(body && body.getClassName() === 'Ellipse', 'bubble-body Ellipse missing');

  var ellipses = findChildrenByClass(node, 'Ellipse');
  // body + 3 trail = 4 ellipses.
  assertEqual(ellipses.length, 4, 'expected 4 ellipses (body + 3 trail)');

  var label = findChildByName(node, 'bubble-text');
  assertTrue(label !== null);
  assertEqual(label.getAttr('fontStyle'), 'italic', 'thought label should be italic');
});

test('thought: default placeholder is "Hmm."', function () {
  var panel = makePanel();
  var node = Bubbles.placeAt(panel, 'thought', 0, 0);
  assertEqual(findChildByName(node, 'bubble-text').text(), 'Hmm.');
});

// ── shout bubble ─────────────────────────────────────────────────────────

test('shout: Line starburst body + bold bubble-text', function () {
  var panel = makePanel();
  var node = Bubbles.placeAt(panel, 'shout', 0, 0);
  assertEqual(node.getAttr('bubbleKind'), 'shout');

  var body = findChildByName(node, 'bubble-body');
  assertTrue(body && body.getClassName() === 'Line', 'bubble-body Line (starburst) missing');
  // 14 spikes × 2 (outer+inner) × 2 (x,y) = 56 numbers.
  assertEqual(body.points().length, 56, 'shout body should have 56 point-numbers');

  var label = findChildByName(node, 'bubble-text');
  assertEqual(label.getAttr('fontStyle'), 'bold');
});

test('shout: default placeholder is "POW!"', function () {
  var panel = makePanel();
  var node = Bubbles.placeAt(panel, 'shout', 0, 0);
  assertEqual(findChildByName(node, 'bubble-text').text(), 'POW!');
});

// ── caption box ──────────────────────────────────────────────────────────

test('caption: tab + body + label, no tail', function () {
  var panel = makePanel();
  var node = Bubbles.placeAt(panel, 'caption', 0, 0);
  assertEqual(node.getAttr('bubbleKind'), 'caption');

  assertTrue(findChildByName(node, 'caption-tab') !== null, 'caption-tab missing');
  assertTrue(findChildByName(node, 'bubble-body') !== null);
  assertTrue(findChildByName(node, 'bubble-text') !== null);

  // Captions are narrator boxes — no tail.
  assertEqual(findChildByName(node, 'bubble-tail'), null,
              'caption should NOT have a bubble-tail');
});

test('caption: default placeholder is "Meanwhile…"', function () {
  var panel = makePanel();
  var node = Bubbles.placeAt(panel, 'caption', 0, 0);
  assertEqual(findChildByName(node, 'bubble-text').text(), 'Meanwhile…');
});

test('caption: NO tail-anchor handle attached (no speaker to point at)', function () {
  var panel = makePanel();
  var node = Bubbles.placeAt(panel, 'caption', 0, 0);
  assertEqual(findChildByName(node, 'tail-anchor'), null,
              'caption should not get a tail-anchor');
});

// ── tail-anchor on tailed bubbles ────────────────────────────────────────

test('speech: tail-anchor Circle attached at tail tip', function () {
  var panel = makePanel();
  var node = Bubbles.placeAt(panel, 'speech', 0, 0);
  var anchor = findChildByName(node, 'tail-anchor');
  assertTrue(anchor !== null, 'speech bubble should get a tail-anchor handle');
  assertEqual(anchor.getClassName(), 'Circle');
  assertEqual(anchor.getAttr('draggable'), true);
});

test('thought also gets a tail-anchor (trail ellipses are named bubble-tail)', function () {
  var panel = makePanel();
  var thoughtNode = Bubbles.placeAt(panel, 'thought', 0, 0);
  assertTrue(findChildByName(thoughtNode, 'tail-anchor') !== null,
             'thought bubble should get a tail-anchor');
});

test('shout does NOT get a tail-anchor (starburst body indicates speaker)', function () {
  // Shout bubbles are intentionally tail-less per the source comment:
  // the jagged starburst body itself indicates the speaker. No tail
  // anchor → no bubble↔target linking.
  var panel = makePanel();
  var shoutNode = Bubbles.placeAt(panel, 'shout', 0, 0);
  assertEqual(findChildByName(shoutNode, 'tail-anchor'), null);
});

// ── placement side-effects ───────────────────────────────────────────────

test('placeAt adds the bubble to userInputLayer', function () {
  var panel = makePanel();
  Bubbles.placeAt(panel, 'speech', 0, 0);
  var kids = panel.userInputLayer.getChildren();
  assertEqual(kids.length, 1, 'one bubble Group on user layer');
  assertEqual(kids[0].getClassName(), 'Group');
});

test('placeAt assigns a unique id', function () {
  var panel = makePanel();
  var a = Bubbles.placeAt(panel, 'speech', 0, 0);
  var b = Bubbles.placeAt(panel, 'speech', 100, 100);
  assertTrue(a.id() !== '', 'first id should be non-empty');
  assertTrue(b.id() !== '', 'second id should be non-empty');
  assertTrue(a.id() !== b.id(), 'ids should differ');
});

// ── tail-anchor drag → relink behavior ───────────────────────────────────
//
// Drag the tail anchor over another user-shape and fire dragend → linkedTarget
// attr should be set to the target's id. Drag over empty space → no link.

test('dragend with no overlapping target: linkedTarget stays null', function () {
  var panel = makePanel();
  var bubble = Bubbles.placeAt(panel, 'speech', 0, 0);
  var anchor = findChildByName(bubble, 'tail-anchor');

  // Move anchor to absolute position (1000, 1000) — no targets there.
  anchor.x(1000); anchor.y(1000);
  anchor.fire('dragend');

  assertEqual(bubble.getAttr('linkedTarget'), null,
              'should remain unlinked after dragend over empty space');
});

test('dragend over a user-shape rectangle: linkedTarget = target id', function () {
  var panel = makePanel();

  // Add an explicit target rect (user-shape) at (300,300) 100×100.
  var target = Konva.Rect({ x: 300, y: 300, width: 100, height: 100, id: 'tgt-1' });
  target.setAttr('name', 'user-shape');
  panel.userInputLayer.add(target);

  var bubble = Bubbles.placeAt(panel, 'speech', 0, 0);
  var anchor = findChildByName(bubble, 'tail-anchor');

  // Bubble itself is at (0,0); anchor in local coords = (350, 350) puts the
  // anchor's absolute position inside the target rect.
  anchor.x(350); anchor.y(350);
  anchor.fire('dragend');

  assertEqual(bubble.getAttr('linkedTarget'), 'tgt-1',
              'linkedTarget should be the target id');
});

test('previously linked bubble unlinks when anchor is dragged off-target', function () {
  var panel = makePanel();
  var target = Konva.Rect({ x: 300, y: 300, width: 100, height: 100, id: 'tgt-2' });
  target.setAttr('name', 'user-shape');
  panel.userInputLayer.add(target);

  var bubble = Bubbles.placeAt(panel, 'speech', 0, 0);
  var anchor = findChildByName(bubble, 'tail-anchor');

  // First link.
  anchor.x(350); anchor.y(350);
  anchor.fire('dragend');
  assertEqual(bubble.getAttr('linkedTarget'), 'tgt-2');

  // Then drag away.
  anchor.x(2000); anchor.y(2000);
  anchor.fire('dragend');
  assertEqual(bubble.getAttr('linkedTarget'), null);
});

test('panel-grid-handle is excluded from hit-testing', function () {
  var panel = makePanel();

  // Add a panel-grid-handle directly under the bubble's anchor — must be
  // skipped during hit-test (it's a UI overlay, not a link target).
  var handle = Konva.Rect({ x: 300, y: 300, width: 100, height: 100, id: 'pgh-1' });
  handle.setAttr('name', 'panel-grid-handle');
  panel.userInputLayer.add(handle);

  var bubble = Bubbles.placeAt(panel, 'speech', 0, 0);
  var anchor = findChildByName(bubble, 'tail-anchor');
  anchor.x(350); anchor.y(350);
  anchor.fire('dragend');

  assertEqual(bubble.getAttr('linkedTarget'), null,
              'should not link to a panel-grid-handle');
});

test('bubble cannot link to itself', function () {
  var panel = makePanel();
  var bubble = Bubbles.placeAt(panel, 'speech', 0, 0);
  var anchor = findChildByName(bubble, 'tail-anchor');

  // The bubble's body Rect IS at x=0,y=0 inside the bubble; anchor inside
  // the bubble's own bounds. Hit-test must skip the source group.
  anchor.x(50); anchor.y(50);
  anchor.fire('dragend');

  assertEqual(bubble.getAttr('linkedTarget'), null,
              'bubble must never link to itself');
});

// ── result ────────────────────────────────────────────────────────────────

console.log('\n  ' + pass + ' passed, ' + fail + ' failed');
process.exit(fail === 0 ? 0 : 1);
