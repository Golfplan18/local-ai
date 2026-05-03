#!/usr/bin/env node
/* test-overlay-drag-position.js — A/V Phase 6 follow-up (2026-05-01)
 *
 * Coverage for drag-to-position overlay support:
 *   • OraTimelineEditor.setOverlayPosition (clamping, validation,
 *     accept on lower-third, reject on title-card / unknown clip).
 *   • OraPreviewMonitor's pure-math hooks: _pixelToPercent (pixel
 *     coords → normalized fractions, clamped) and _handleRect
 *     (normalized position → stage-local pixel rect).
 *
 * Strategy: vm-sandbox both modules with a mocked DOM (mirrors the
 * existing test-v3-toolbar-selector pattern) and exercise the public
 * API surface. The drag interaction itself (pointerdown → pointermove
 * → pointerup) is browser smoke per the WP-7.10 procedure doc — too
 * many DOM hooks to replicate fully under jsdom-substitute.
 */

'use strict';

var fs   = require('fs');
var path = require('path');
var vm   = require('vm');

var TIMELINE_SRC = path.resolve(__dirname, '..', 'timeline-editor.js');
var PREVIEW_SRC  = path.resolve(__dirname, '..', 'preview-monitor.js');

// ── Minimal DOM mock (lifted from prior harnesses) ─────────────────────────

function makeEl(tagName) {
  var el = {
    tagName: (tagName || 'DIV').toUpperCase(),
    children: [], childNodes: [], style: {}, dataset: {},
    _attrs: {}, _listeners: {}, parentNode: null,
    isContentEditable: false, hidden: false,
  };
  Object.defineProperty(el, 'id', {
    get: function () { return el._attrs.id || ''; },
    set: function (v) { el._attrs.id = String(v); }
  });
  Object.defineProperty(el, 'className', {
    get: function () { return el._attrs['class'] || ''; },
    set: function (v) { el._attrs['class'] = String(v); }
  });
  el.setAttribute = function (k, v) { el._attrs[k] = String(v); };
  el.getAttribute = function (k) { return el._attrs.hasOwnProperty(k) ? el._attrs[k] : null; };
  el.removeAttribute = function (k) { delete el._attrs[k]; };
  el.appendChild = function (child) {
    el.children.push(child); el.childNodes.push(child);
    if (child) child.parentNode = el;
    return child;
  };
  el.removeChild = function (child) {
    var i = el.children.indexOf(child);
    if (i >= 0) { el.children.splice(i, 1); el.childNodes.splice(i, 1); }
    if (child) child.parentNode = null;
    return child;
  };
  el.querySelector = function () { return null; };
  el.querySelectorAll = function () { return []; };
  el.addEventListener = function (ev, fn) {
    if (!el._listeners[ev]) el._listeners[ev] = [];
    el._listeners[ev].push(fn);
  };
  el.removeEventListener = function (ev, fn) {
    var arr = el._listeners[ev]; if (!arr) return;
    var i = arr.indexOf(fn); if (i >= 0) arr.splice(i, 1);
  };
  el.dispatchEvent = function () { return true; };
  el.classList = {
    _set: {},
    add:    function (c) { this._set[c] = true; },
    remove: function (c) { delete this._set[c]; },
    contains: function (c) { return !!this._set[c]; },
    toggle: function (c, v) {
      if (v === true) this._set[c] = true;
      else if (v === false) delete this._set[c];
      else if (this._set[c]) delete this._set[c];
      else this._set[c] = true;
    }
  };
  return el;
}

function makeDoc() {
  var listeners = {};
  var body = makeEl('body');
  return {
    body: body,
    readyState: 'complete',
    createElement: function (tag) { return makeEl(tag); },
    getElementById: function () { return null; },
    addEventListener: function (ev, fn) {
      if (!listeners[ev]) listeners[ev] = [];
      listeners[ev].push(fn);
    },
    removeEventListener: function (ev, fn) {
      var arr = listeners[ev]; if (!arr) return;
      var i = arr.indexOf(fn); if (i >= 0) arr.splice(i, 1);
    },
    dispatchEvent: function (e) {
      var arr = (listeners[e.type] || []).slice();
      arr.forEach(function (fn) { fn(e); });
      return true;
    },
    _listeners: listeners,
  };
}

// ── Boot timeline-editor + preview-monitor in shared sandbox ───────────────

function bootBoth() {
  var doc = makeDoc();
  var sandbox = {
    window: { OraTimelineEditor: null, OraPreviewMonitor: null,
              addEventListener: function () {} },
    document: doc,
    console: { log: function () {}, info: function () {}, warn: function () {}, error: function () {} },
    setTimeout: function () { return 0; },
    clearTimeout: function () {},
    fetch: function () { return new Promise(function () {}); },
    AbortController: function () { return { abort: function () {}, signal: {} }; },
    CustomEvent: function (name, opts) {
      this.type = name;
      this.detail = opts && opts.detail;
      this.preventDefault = function () {};
    },
    Promise: Promise,
    Map: Map, WeakMap: WeakMap, Set: Set,
    Date: Date, Math: Math, Object: Object, Array: Array, JSON: JSON,
    isFinite: isFinite, parseInt: parseInt, parseFloat: parseFloat,
    Infinity: Infinity, encodeURIComponent: encodeURIComponent,
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(TIMELINE_SRC, 'utf8'), sandbox);
  vm.runInContext(fs.readFileSync(PREVIEW_SRC,  'utf8'), sandbox);
  return {
    Editor: sandbox.window.OraTimelineEditor,
    Preview: sandbox.window.OraPreviewMonitor,
    sandbox: sandbox,
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
function assertClose(a, b, eps, msg) {
  eps = eps || 0.001;
  if (Math.abs(a - b) > eps) {
    throw new Error((msg || 'close')
                    + ': expected ≈ ' + b + ', got ' + a);
  }
}
function assertTrue(c, m) { if (!c) throw new Error(m || 'expected truthy'); }
function assertFalse(c, m) { if (c) throw new Error(m || 'expected falsy'); }

// ── Fixtures ───────────────────────────────────────────────────────────────

function stateWithLowerThird() {
  return {
    duration_ms: 10000,
    playhead_ms: 0,
    tracks: [
      {
        id: 'overlay-track',
        kind: 'overlay',
        clips: [
          {
            id: 'lt-1',
            overlay_type: 'lower-third',
            track_position_ms: 0,
            in_point_ms: 0, out_point_ms: 2000,
            overlay_content: {
              text: 'Hello',
              position: { x_pct: 0.5, y_pct: 0.85, width_pct: 0.5 },
            },
          },
          {
            id: 'tc-1',
            overlay_type: 'title-card',
            track_position_ms: 2000,
            in_point_ms: 0, out_point_ms: 2000,
            overlay_content: { text: 'Chapter 1' },
          },
        ],
      },
    ],
  };
}

// ─────────────────────────────────────────────────────────────────────────
// OraTimelineEditor.setOverlayPosition
// ─────────────────────────────────────────────────────────────────────────

console.log('test-overlay-drag-position.js — drag-to-position overlay handling');

var booted = bootBoth();
var Editor = booted.Editor;
var Preview = booted.Preview;

test('setOverlayPosition exists on Editor', function () {
  assertTrue(typeof Editor.setOverlayPosition === 'function');
});

test('setOverlayPosition updates a lower-third clip in place', function () {
  Editor._setStateForTests(stateWithLowerThird());
  var r = Editor.setOverlayPosition('overlay-track', 'lt-1', 0.10, 0.90,
                                    { skipSave: true });
  assertEqual(r.ok, true);
  assertClose(r.x_pct, 0.10);
  assertClose(r.y_pct, 0.90);
  var s = Editor.getState();
  var clip = s.tracks[0].clips[0];
  assertClose(clip.overlay_content.position.x_pct, 0.10);
  assertClose(clip.overlay_content.position.y_pct, 0.90);
});

test('setOverlayPosition clamps x_pct < 0 to 0', function () {
  Editor._setStateForTests(stateWithLowerThird());
  var r = Editor.setOverlayPosition('overlay-track', 'lt-1', -2.5, 0.5,
                                    { skipSave: true });
  assertEqual(r.ok, true);
  assertEqual(r.x_pct, 0);
});

test('setOverlayPosition clamps y_pct > 1 to 1', function () {
  Editor._setStateForTests(stateWithLowerThird());
  var r = Editor.setOverlayPosition('overlay-track', 'lt-1', 0.5, 99,
                                    { skipSave: true });
  assertEqual(r.ok, true);
  assertEqual(r.y_pct, 1);
});

test('setOverlayPosition rejects title-card clips', function () {
  Editor._setStateForTests(stateWithLowerThird());
  var r = Editor.setOverlayPosition('overlay-track', 'tc-1', 0.1, 0.1,
                                    { skipSave: true });
  assertEqual(r.ok, false);
  assertTrue(/positioning/.test(r.reason),
             'reason should mention positioning support');
});

test('setOverlayPosition rejects unknown clip ids', function () {
  Editor._setStateForTests(stateWithLowerThird());
  var r = Editor.setOverlayPosition('overlay-track', 'nope', 0.1, 0.1,
                                    { skipSave: true });
  assertEqual(r.ok, false);
  assertEqual(r.reason, 'clip not found');
});

test('setOverlayPosition rejects non-finite numbers', function () {
  Editor._setStateForTests(stateWithLowerThird());
  var r = Editor.setOverlayPosition('overlay-track', 'lt-1', NaN, 0.5,
                                    { skipSave: true });
  assertEqual(r.ok, false);
  var r2 = Editor.setOverlayPosition('overlay-track', 'lt-1', 0.5, Infinity,
                                     { skipSave: true });
  assertEqual(r2.ok, false);
});

test('setOverlayPosition does not mutate state on rejection', function () {
  Editor._setStateForTests(stateWithLowerThird());
  Editor.setOverlayPosition('overlay-track', 'tc-1', 0.99, 0.99,
                            { skipSave: true });
  var s = Editor.getState();
  // Title-card content shouldn't have grown a position field.
  assertEqual(s.tracks[0].clips[1].overlay_content.position, undefined);
});

// ─────────────────────────────────────────────────────────────────────────
// OraPreviewMonitor pure-math hooks
// ─────────────────────────────────────────────────────────────────────────

test('_pixelToPercent exists on Preview', function () {
  assertTrue(typeof Preview._pixelToPercent === 'function');
});

test('_handleRect exists on Preview', function () {
  assertTrue(typeof Preview._handleRect === 'function');
});

test('_pixelToPercent computes basic fractions', function () {
  var rect = { left: 100, top: 50, width: 800, height: 400 };
  // Pointer at (500, 250) → halfway across both axes from the rect origin.
  var r = Preview._pixelToPercent(500, 250, rect);
  assertClose(r.x_pct, 0.5);
  assertClose(r.y_pct, 0.5);
});

test('_pixelToPercent clamps left of rect to 0', function () {
  var rect = { left: 100, top: 50, width: 800, height: 400 };
  var r = Preview._pixelToPercent(0, 30, rect);
  assertEqual(r.x_pct, 0);
  assertEqual(r.y_pct, 0);
});

test('_pixelToPercent clamps right/below rect to 1', function () {
  var rect = { left: 100, top: 50, width: 800, height: 400 };
  var r = Preview._pixelToPercent(2000, 1000, rect);
  assertEqual(r.x_pct, 1);
  assertEqual(r.y_pct, 1);
});

test('_pixelToPercent handles zero-size rects without dividing by zero', function () {
  var rect = { left: 100, top: 50, width: 0, height: 0 };
  var r = Preview._pixelToPercent(500, 250, rect);
  assertTrue(isFinite(r.x_pct));
  assertTrue(isFinite(r.y_pct));
});

test('_handleRect maps normalized position to stage-local pixels', function () {
  var r = Preview._handleRect(
    { x_pct: 0.25, y_pct: 0.5, width_pct: 0.5 }, 1000, 800);
  assertEqual(r.left, 250);
  assertEqual(r.top, 400);
  assertEqual(r.width, 500);
  // height heuristic: max(20, stageH * 0.12) = max(20, 96) = 96
  assertEqual(r.height, 96);
});

test('_handleRect floors the height heuristic at 20px', function () {
  var r = Preview._handleRect(
    { x_pct: 0, y_pct: 0, width_pct: 0.5 }, 1000, 50);
  assertEqual(r.height, 20, 'tiny stages still get a usable handle');
});

test('_handleRect clamps width_pct below 0.05', function () {
  var r = Preview._handleRect(
    { x_pct: 0, y_pct: 0, width_pct: 0.001 }, 1000, 800);
  // 0.001 < 0.05 → clamped to 0.05 → 50px wide.
  assertEqual(r.width, 50);
});

test('_handleRect clamps width_pct above 1.0', function () {
  var r = Preview._handleRect(
    { x_pct: 0, y_pct: 0, width_pct: 99 }, 1000, 800);
  assertEqual(r.width, 1000);
});

test('_handleRect uses defaults for missing fields', function () {
  var r = Preview._handleRect({}, 1000, 800);
  // x_pct=0.5, y_pct=0.85, width_pct=0.5
  assertEqual(r.left, 500);
  assertEqual(r.top, 680);
  assertEqual(r.width, 500);
});

// ─────────────────────────────────────────────────────────────────────────
// Drag-end commit math: pixelToPercent + offset → setOverlayPosition
// ─────────────────────────────────────────────────────────────────────────

test('drag commit: pointerup percentage + offset is what gets persisted', function () {
  // Lower-third initially at (0.5, 0.85). User pointer-down at the
  // handle's center (call that 0.5, 0.85 in normalized space — close
  // enough for this stub since the handle anchor is x_pct,y_pct). Drag
  // ends with pointer at (0.2, 0.5). Expected commit: (0.2, 0.5).
  Editor._setStateForTests(stateWithLowerThird());

  var stageRect = { left: 0, top: 0, width: 1000, height: 800 };
  var pos0 = Preview._pixelToPercent(500, 680, stageRect);
  var anchorOffset = {
    x_pct: 0.5 - pos0.x_pct,   // ≈ 0
    y_pct: 0.85 - pos0.y_pct,  // ≈ 0
  };
  var endPx = { x: 200, y: 400 };
  var endPct = Preview._pixelToPercent(endPx.x, endPx.y, stageRect);
  var x = Math.max(0, Math.min(1, endPct.x_pct + anchorOffset.x_pct));
  var y = Math.max(0, Math.min(1, endPct.y_pct + anchorOffset.y_pct));

  var r = Editor.setOverlayPosition('overlay-track', 'lt-1', x, y,
                                    { skipSave: true });
  assertEqual(r.ok, true);
  assertClose(r.x_pct, 0.2);
  assertClose(r.y_pct, 0.5);
});

console.log('\n  ' + pass + ' passed, ' + fail + ' failed');
process.exit(fail === 0 ? 0 : 1);
