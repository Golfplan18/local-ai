#!/usr/bin/env node
/**
 * test-shape-with-text.js — WP-7.0.7 self-test
 *
 * Boots Konva inside jsdom (with the same canvas-context mock that run.js
 * uses for the rest of the visual-compiler suite), then exercises the
 * shape-with-text primitive against the three behavior policies plus a
 * round-trip.
 *
 * Test coverage maps to the §13.0 WP-7.0.7 acceptance criterion:
 *   1. Insert text in a rectangle with `wrap` policy; verify text wraps
 *      inside bounds.
 *   2. Insert text in a circle with `grow` policy and long text; verify
 *      circle grows to fit.
 *   plus a `shrink-text` policy test, plus a toJSON / fromGroup round trip.
 *
 * Run:
 *   cd ~/ora/server/static/ora-visual-compiler/tests
 *   node test-shape-with-text.js
 */

'use strict';

const fs   = require('fs');
const vm   = require('vm');
const path = require('path');
const { JSDOM } = require('jsdom');

const ORA_STATIC = path.resolve(__dirname, '..', '..');
const KONVA_PATH = path.join(ORA_STATIC, 'vendor', 'konva', 'konva.min.js');
const SHAPE_PATH = path.join(ORA_STATIC, 'shape-with-text.js');

let pass = 0, fail = 0;
function assert(cond, label) {
  if (cond) { pass++; console.log('  PASS', label); }
  else      { fail++; console.log('  FAIL', label); }
}
function assertNear(actual, expected, tol, label) {
  const ok = Math.abs(actual - expected) <= tol;
  if (ok) { pass++; console.log('  PASS', label, `(actual=${actual}, expected≈${expected})`); }
  else    { fail++; console.log('  FAIL', label, `(actual=${actual}, expected≈${expected}, tol=${tol})`); }
}
function group(label, fn) {
  console.log('\n--', label);
  try { fn(); }
  catch (err) { fail++; console.log('  FAIL', label, '(threw)'); console.error(err); }
}

// ── jsdom + canvas-mock + Konva boot ────────────────────────────────────────
const dom = new JSDOM(
  '<!DOCTYPE html><html><head></head><body><div id="stage"></div></body></html>',
  { url: 'http://localhost/', runScripts: 'outside-only', pretendToBeVisual: true }
);
const win = dom.window;
win.globalThis = win;
win.console = console;
if (!win.requestAnimationFrame) {
  win.requestAnimationFrame = (cb) => setTimeout(cb, 16);
}
// Same canvas mock as run.js — Konva.Text uses measureText for width(); we
// approximate 6 px per character which makes word-wrap deterministic.
win.HTMLCanvasElement.prototype.getContext = function () {
  // Stub 2D context — Konva's renderer calls many methods during draw;
  // they all no-op for our structural tests. measureText is the only one
  // whose return value matters (text measurement → wrap layout).
  const noop = () => {};
  return new Proxy({
    measureText: (t) => ({ width: (t || '').length * 6 }),
    getImageData: () => ({ data: new Uint8ClampedArray(4) }),
    createImageData: () => ({ data: new Uint8ClampedArray(4) }),
    canvas: this,
  }, {
    get(target, prop) {
      if (prop in target) return target[prop];
      // All other 2D-context methods are no-ops.
      return noop;
    },
  });
};

const ctx = dom.getInternalVMContext();
function loadScript(absPath) {
  vm.runInContext(fs.readFileSync(absPath, 'utf-8'), ctx, { filename: absPath });
}

console.log('=== WP-7.0.7 shape-with-text self-test ===');
console.log('Loading Konva from', KONVA_PATH);
loadScript(KONVA_PATH);
console.log('Loading shape-with-text from', SHAPE_PATH);
loadScript(SHAPE_PATH);

const Konva = win.Konva;
const OraShapeWithText = win.OraShapeWithText;

if (!Konva) { console.error('FATAL: Konva did not load'); process.exit(2); }
if (!OraShapeWithText) { console.error('FATAL: OraShapeWithText did not export'); process.exit(2); }

// Build a stage so getClientRect returns sensible values.
function freshStage() {
  // Fresh container per test so old layers don't accumulate.
  const div = win.document.createElement('div');
  div.id = 'stage-' + Math.random().toString(36).slice(2);
  win.document.body.appendChild(div);
  const stage = new Konva.Stage({ container: div, width: 800, height: 600 });
  const layer = new Konva.Layer();
  stage.add(layer);
  return { stage, layer };
}

// ── Test 1 — wrap policy in a rectangle ─────────────────────────────────────
group('Test 1 — wrap in rectangle', () => {
  const { layer } = freshStage();
  const rect = new Konva.Rect({ x: 0, y: 0, width: 120, height: 60, fill: '#fff' });
  const longText = 'This is a long sentence that should wrap onto multiple lines inside a small rectangle.';
  const ctl = OraShapeWithText.attach(rect, longText, {
    policy: OraShapeWithText.POLICIES.WRAP,
    fontSize: 14, padding: 8, ellipsis: true,
  });
  layer.add(ctl.group);
  layer.draw();

  // Rect bounds 120x60, padding 8 → inscribed rect is 104 x 44, line height ≈ 16.8.
  // Wrap should produce ≥ 2 lines for that input string.
  const rendered = ctl.text.text();
  const lines = rendered.split('\n');
  assert(lines.length >= 2, 'wraps text into ≥ 2 lines (got ' + lines.length + ')');
  // No single line should exceed inscribed width (104 px → 17 chars at 6 px).
  // One char of slack to absorb word-boundary measurement quirks.
  const overlong = lines.find(L => L.length > 19);
  assert(!overlong, 'no rendered line wider than inscribed rect (max line len ' +
                    Math.max(0, ...lines.map(L => L.length)) + ')');
  // Text node geometry must be inside the rect bounds.
  assert(ctl.text.x() >= 0 && ctl.text.y() >= 0, 'text origin inside rect padding box');
  assert(ctl.text.width() <= 120 && ctl.text.height() <= 60,
         'text bounds within rect bounds (w=' + ctl.text.width() + ', h=' + ctl.text.height() + ')');
  // Group should still be 0,0 (caller positions it).
  assert(ctl.group.x() === 0 && ctl.group.y() === 0, 'group origin unchanged by relayout');
});

// ── Test 2 — grow policy with circle (Konva.Ellipse) and long text ──────────
group('Test 2 — grow in circle with long text', () => {
  const { layer } = freshStage();
  // Start with a small circle; long text should make it grow.
  const circle = new Konva.Ellipse({ x: 30, y: 30, radiusX: 30, radiusY: 30, fill: '#fff' });
  const initialRx = circle.radiusX();
  const initialRy = circle.radiusY();
  const longText = 'This is a fairly long bubble-style text that should force the circle to grow.';
  const ctl = OraShapeWithText.attach(circle, longText, {
    policy: OraShapeWithText.POLICIES.GROW,
    fontSize: 14, padding: 8, hostKind: 'ellipse',
  });
  layer.add(ctl.group);
  layer.draw();

  const newRx = circle.radiusX();
  const newRy = circle.radiusY();
  assert(newRx > initialRx, 'radiusX grew (was ' + initialRx + ', now ' + newRx + ')');
  assert(newRy >= initialRy, 'radiusY grew or stayed (was ' + initialRy + ', now ' + newRy + ')');
  // Sanity: text must still fit in the inscribed rect after the grow.
  const inner = OraShapeWithText._internals.inscribedRect(circle, 'ellipse', 8);
  const lines = ctl.text.text().split('\n');
  const lh = 14 * 1.2;
  assert(lines.length * lh <= inner.height + 1,
         'text height fits inscribed rect (lines=' + lines.length +
         ', inner.h=' + inner.height.toFixed(1) + ')');
  // No truncation (grow policy guarantees full text shows). Compare the
  // rendered text against the source after collapsing whitespace — word
  // wrap legitimately drops the space at each line break, so we compare
  // word-by-word rather than character-counting.
  const renderedWords = lines.join(' ').trim().split(/\s+/);
  const sourceWords = longText.trim().split(/\s+/);
  assert(renderedWords.length === sourceWords.length,
         'all words preserved by grow policy (rendered ' + renderedWords.length +
         ' words / source ' + sourceWords.length + ')');
});

// ── Test 3 — shrink-text policy in a fixed rectangle with too much text ─────
group('Test 3 — shrink-text in fixed rectangle', () => {
  const { layer } = freshStage();
  const rect = new Konva.Rect({ x: 0, y: 0, width: 100, height: 50, fill: '#fff' });
  const longText = 'The quick brown fox jumps over the lazy dog. ' +
                   'Pack my box with five dozen liquor jugs.';
  const ctl = OraShapeWithText.attach(rect, longText, {
    policy: OraShapeWithText.POLICIES.SHRINK_TEXT,
    minFontSize: 6, maxFontSize: 24, padding: 6,
  });
  layer.add(ctl.group);
  layer.draw();

  const eff = ctl.group.getAttr('userTextEffectiveFontSize');
  assert(typeof eff === 'number' && eff >= 6 && eff <= 24,
         'effective font size in [6,24] (got ' + eff + ')');
  assert(eff < 24, 'shrink-text picked a smaller font than max (got ' + eff + ')');
  // Geometry: rendered text must fit inscribed rect at chosen size.
  assert(ctl.text.height() <= 50 - 2 * 6 + 1, 'text height fits inside rect');
});

// ── Test 4 — toJSON / fromGroup round trip ──────────────────────────────────
group('Test 4 — toJSON / fromGroup round-trip', () => {
  const { layer } = freshStage();
  const rect = new Konva.Rect({ x: 0, y: 0, width: 200, height: 80, fill: '#fff' });
  const ctl = OraShapeWithText.attach(rect, 'Round-trip test text.', {
    policy: OraShapeWithText.POLICIES.WRAP, fontSize: 12, padding: 6,
  });
  layer.add(ctl.group);
  layer.draw();

  const json = ctl.group.toJSON();
  // Should contain the convention attrs.
  assert(json.includes('"userShapeType":"shape-with-text"'),
         'JSON carries userShapeType');
  assert(json.includes('"userTextPolicy":"wrap"'), 'JSON carries userTextPolicy');
  assert(json.includes('"userTextContent":"Round-trip test text."'),
         'JSON carries userTextContent');

  // Create a fresh node from the JSON and rehydrate via fromGroup.
  const restored = Konva.Node.create(json);
  layer.add(restored);
  const ctl2 = OraShapeWithText.fromGroup(restored);
  assert(ctl2._content === 'Round-trip test text.', 'restored text content matches');
  assert(ctl2._policy === 'wrap', 'restored policy matches');
  assert(ctl2.text.text().length > 0, 'restored text node has non-empty content');
});

// ── Schema fragment shape ───────────────────────────────────────────────────
group('Test 5 — schema fragment exposed for WP-7.0.2', () => {
  const sf = OraShapeWithText.SCHEMA_FRAGMENT;
  assert(sf && sf.$id === 'shape_with_text', 'schema fragment has $id=shape_with_text');
  assert(sf.properties.userTextPolicy.enum.length === 3, 'policy enum has all 3 values');
  assert(sf.properties.userTextOptions.properties.padding.default === 8,
         'options.padding default is 8');
  assert(sf.properties.userTextOptions.properties.hostKind.enum.length === 4,
         'hostKind enum has 4 values');
});

// ── Summary ────────────────────────────────────────────────────────────────
console.log('\n=== Summary ===');
console.log(`PASS ${pass}  FAIL ${fail}`);
process.exit(fail === 0 ? 0 : 1);
