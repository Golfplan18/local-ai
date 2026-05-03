/**
 * tests/cases/test-lazy-expansion.js — WP-7.4.6 regression suite.
 *
 * Exports { label, run(ctx, record) } per the run.js case-file convention.
 *
 * Coverage of the lazy canvas expansion module
 * (server/static/lazy-expansion.js):
 *
 *   1. Namespace exists on window.OraLazyExpansion with the documented surface
 *      (init, destroy, checkAndExpand, computeExpansion, THRESHOLD_PX_DEFAULT,
 *      GROW_FRACTION_DEFAULT).
 *   2. computeExpansion() returns null when the bbox is comfortably inside.
 *   3. computeExpansion() detects right-edge proximity and returns
 *      anchor='top-left' (left side stays, right side grows).
 *   4. computeExpansion() detects bottom-edge proximity and returns
 *      anchor='top-left' (top side stays, bottom side grows).
 *   5. computeExpansion() detects left-edge proximity and returns
 *      anchor='top-right' (right side stays, left side grows).
 *   6. computeExpansion() detects top-edge proximity and returns
 *      anchor='bottom-left' (bottom side stays, top side grows).
 *   7. computeExpansion() handles right + bottom corner proximity →
 *      anchor='top-left', both axes grow.
 *   8. Grows by 25 % of prior dimension along the affected axis (default).
 *   9. Configurable threshold: setThreshold(50) makes a 100-px-margin object
 *      stop triggering expansion.
 *  10. Configurable grow_fraction: 0.5 grows by 50 %, not 25 %.
 *  11. Test criterion (WP-7.4.6): place an object whose right edge is 50 px
 *      from canvas right edge → canvas extends rightward by 25 %.
 *  12. Existing objects don't move (top-left anchor preserves left + top
 *      coords of every prior shape).
 *  13. Drawing a shape via panel._createShape near the right edge auto-
 *      triggers expansion (prototype-patch hook fires).
 *  14. Shape drawn comfortably inside the canvas does NOT trigger
 *      expansion.
 *  15. Disabling lazy expansion (setEnabled(false)) suppresses growth.
 *  16. checkAndExpand() with explicit bounds returns the apply() result.
 *  17. checkAndExpand() with bounds entirely inside returns null.
 *  18. canvas-state-changed event from a capability-image-* dispatch
 *      triggers expansion when the inserted object lands near an edge.
 *  19. Far-out placement (object overruns the right edge by 1500 px) grows
 *      by enough to cover the overrun + threshold, not just 25 %.
 *  20. canvas-lazy-expanded event fires with the prior + next dimensions.
 *  21. Idempotent init: calling init() twice destroys the prior controller.
 *  22. destroy() removes the listener and stops further expansion.
 */

'use strict';

function mkDiv(win) {
  var d = win.document.createElement('div');
  d.style.cssText = 'width:600px;height:400px;';
  win.document.body.appendChild(d);
  return d;
}

function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

// rAF in jsdom runs out of band — drain a couple ticks so debounced checks fire.
function flushFrames() {
  return new Promise(function (resolve) {
    if (typeof setImmediate === 'function') {
      setImmediate(function () { setTimeout(resolve, 5); });
    } else {
      setTimeout(resolve, 10);
    }
  });
}

// Set the panel's prior canvas size to a known starting point (1000 × 1000)
// so percentage-based growth is easy to reason about.
function seedSize(panel, w, h) {
  panel._priorCanvasSize = { width: w, height: h };
  if (panel._canvasState && panel._canvasState.metadata) {
    panel._canvasState.metadata.canvas_size = { width: w, height: h };
  }
}

module.exports = {
  label: 'Lazy canvas expansion (WP-7.4.6) — auto-grow on near-edge placement',
  run: async function run(ctx, record) {
    const { win } = ctx;

    if (typeof win.Konva === 'undefined' || typeof win.VisualPanel === 'undefined') {
      record('lazy-expansion: harness bootstrap', false,
        'Konva=' + typeof win.Konva + ' VisualPanel=' + typeof win.VisualPanel);
      return;
    }
    if (typeof win.OraResizeCanvas === 'undefined') {
      record('lazy-expansion: OraResizeCanvas required', false,
        'OraResizeCanvas=' + typeof win.OraResizeCanvas);
      return;
    }

    // Lazy-load lazy-expansion.js into the same window the harness uses.
    if (typeof win.OraLazyExpansion === 'undefined') {
      const path = require('path');
      const fs   = require('fs');
      const src  = fs.readFileSync(path.join(__dirname, '..', '..', '..', 'lazy-expansion.js'), 'utf-8');
      // Run inside the jsdom window so `window.OraResizeCanvas` resolves and
      // window.VisualPanel is the right class to patch.
      win.eval(src);
    }

    // ── 1. Namespace surface ───────────────────────────────────────────────
    try {
      const ns = win.OraLazyExpansion;
      const ok = ns && typeof ns.init === 'function'
                    && typeof ns.destroy === 'function'
                    && typeof ns.checkAndExpand === 'function'
                    && typeof ns.computeExpansion === 'function'
                    && typeof ns.THRESHOLD_PX_DEFAULT === 'number'
                    && typeof ns.GROW_FRACTION_DEFAULT === 'number';
      record('lazy-expansion #1: window.OraLazyExpansion has documented surface',
        !!ok,
        'present keys=' + (ns ? Object.keys(ns).join(',') : 'none'));
    } catch (e) {
      record('lazy-expansion #1', false, 'threw: ' + (e.stack || e.message || e));
    }

    const LE = win.OraLazyExpansion;

    // ── 2. Comfortably inside → null ───────────────────────────────────────
    try {
      const r = LE.computeExpansion(
        { width: 1000, height: 1000 },
        { x: 400, y: 400, width: 100, height: 100 },   // margins all 400 px
        200, 0.25);
      record('lazy-expansion #2: bbox comfortably inside returns null',
        r === null, 'r=' + JSON.stringify(r));
    } catch (e) {
      record('lazy-expansion #2', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 3. Right edge ──────────────────────────────────────────────────────
    try {
      const r = LE.computeExpansion(
        { width: 1000, height: 1000 },
        { x: 850, y: 400, width: 100, height: 100 },   // right margin = 50; vert margins = 400/500
        200, 0.25);
      const ok = r && r.anchor === 'top-left' && r.grew && r.grew.right === true && r.grew.left === false
                   && r.width === 1250 && r.height === 1000;
      record('lazy-expansion #3: right-edge proximity grows right by 25 %, anchor=top-left',
        !!ok, 'r=' + JSON.stringify(r));
    } catch (e) {
      record('lazy-expansion #3', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 4. Bottom edge ─────────────────────────────────────────────────────
    try {
      const r = LE.computeExpansion(
        { width: 1000, height: 1000 },
        { x: 400, y: 850, width: 100, height: 100 },   // bottom margin = 50; horiz margins = 400/500
        200, 0.25);
      const ok = r && r.anchor === 'top-left' && r.grew.bottom === true && r.grew.top === false
                   && r.width === 1000 && r.height === 1250;
      record('lazy-expansion #4: bottom-edge proximity grows bottom by 25 %, anchor=top-left',
        !!ok, 'r=' + JSON.stringify(r));
    } catch (e) {
      record('lazy-expansion #4', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 5. Left edge ───────────────────────────────────────────────────────
    try {
      const r = LE.computeExpansion(
        { width: 1000, height: 1000 },
        { x: 50, y: 400, width: 100, height: 100 },     // left margin = 50
        200, 0.25);
      const ok = r && r.anchor === 'top-right' && r.grew.left === true && r.grew.right === false
                   && r.width === 1250 && r.height === 1000;
      record('lazy-expansion #5: left-edge proximity grows left by 25 %, anchor=top-right',
        !!ok, 'r=' + JSON.stringify(r));
    } catch (e) {
      record('lazy-expansion #5', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 6. Top edge ────────────────────────────────────────────────────────
    try {
      const r = LE.computeExpansion(
        { width: 1000, height: 1000 },
        { x: 400, y: 50, width: 100, height: 100 },     // top margin = 50
        200, 0.25);
      const ok = r && r.anchor === 'bottom-left' && r.grew.top === true && r.grew.bottom === false
                   && r.width === 1000 && r.height === 1250;
      record('lazy-expansion #6: top-edge proximity grows top by 25 %, anchor=bottom-left',
        !!ok, 'r=' + JSON.stringify(r));
    } catch (e) {
      record('lazy-expansion #6', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 7. Right + bottom corner ───────────────────────────────────────────
    try {
      const r = LE.computeExpansion(
        { width: 1000, height: 1000 },
        { x: 850, y: 850, width: 100, height: 100 },   // both margins = 50
        200, 0.25);
      const ok = r && r.anchor === 'top-left' && r.grew.right && r.grew.bottom
                   && r.width === 1250 && r.height === 1250;
      record('lazy-expansion #7: right+bottom corner grows both axes, anchor=top-left',
        !!ok, 'r=' + JSON.stringify(r));
    } catch (e) {
      record('lazy-expansion #7', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 8. 25 % grow (default) ─────────────────────────────────────────────
    try {
      const r = LE.computeExpansion(
        { width: 800, height: 800 },
        { x: 700, y: 350, width: 50, height: 50 },     // right margin = 50, vert margins clear
        200, 0.25);
      record('lazy-expansion #8: default 25 % grow on 800-wide canvas → 1000',
        r && r.width === 1000 && r.height === 800, 'r=' + JSON.stringify(r));
    } catch (e) {
      record('lazy-expansion #8', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 9. Threshold = 50 → 100 px margin no longer triggers ───────────────
    try {
      const r = LE.computeExpansion(
        { width: 1000, height: 1000 },
        { x: 800, y: 400, width: 100, height: 100 },   // right margin = 100, vert clear
        50, 0.25);
      record('lazy-expansion #9: threshold=50 → bbox 100 px from edge does NOT trigger',
        r === null, 'r=' + JSON.stringify(r));
    } catch (e) {
      record('lazy-expansion #9', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 10. grow_fraction = 0.5 → 50 % grow ────────────────────────────────
    try {
      const r = LE.computeExpansion(
        { width: 1000, height: 1000 },
        { x: 850, y: 400, width: 100, height: 100 },   // right margin = 50, vert clear
        200, 0.5);
      record('lazy-expansion #10: grow_fraction=0.5 grows by 50 %, not 25 %',
        r && r.width === 1500, 'r=' + JSON.stringify(r));
    } catch (e) {
      record('lazy-expansion #10', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 11. WP-7.4.6 test criterion: object 50 px from right edge ──────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'le-11' });
      panel.init();
      seedSize(panel, 1000, 1000);
      LE.init(panel);
      // Place a rect whose right edge is 50 px from the canvas right edge.
      // x=850, width=100 → right edge at 950, margin = 50.
      panel._createShape('rect', { x: 850, y: 400, width: 100, height: 100 });
      await flushFrames();
      const next = win.OraResizeCanvas.getCurrentSize(panel);
      record('lazy-expansion #11: WP-7.4.6 test — rect 50 px from right edge triggers grow',
        next.width === 1250 && next.height === 1000,
        'next=' + JSON.stringify(next));
      LE.destroy(panel);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('lazy-expansion #11', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 12. Existing objects don't move (top-left anchor) ──────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'le-12' });
      panel.init();
      seedSize(panel, 1000, 1000);
      // Pre-existing shape at (50, 50).
      const existing = panel._createShape('rect', { x: 50, y: 50, width: 60, height: 60 });
      const xBefore = existing.x();
      const yBefore = existing.y();
      LE.init(panel);
      // Now drop a near-right-edge shape that triggers a grow.
      panel._createShape('rect', { x: 850, y: 400, width: 100, height: 100 });
      await flushFrames();
      record('lazy-expansion #12: existing shape doesn\'t move when growing right',
        existing.x() === xBefore && existing.y() === yBefore,
        'before=(' + xBefore + ',' + yBefore + ') after=(' + existing.x() + ',' + existing.y() + ')');
      LE.destroy(panel);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('lazy-expansion #12', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 13. Auto-trigger via _createShape near right edge ──────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'le-13' });
      panel.init();
      seedSize(panel, 1000, 1000);
      LE.init(panel);
      const before = win.OraResizeCanvas.getCurrentSize(panel);
      panel._createShape('rect', { x: 820, y: 100, width: 100, height: 100 }); // right margin = 80
      await flushFrames();
      const after = win.OraResizeCanvas.getCurrentSize(panel);
      record('lazy-expansion #13: _createShape near right edge auto-grows canvas',
        after.width > before.width,
        'before=' + JSON.stringify(before) + ' after=' + JSON.stringify(after));
      LE.destroy(panel);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('lazy-expansion #13', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 14. Comfortably inside → no auto-expand ────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'le-14' });
      panel.init();
      seedSize(panel, 1000, 1000);
      LE.init(panel);
      const before = win.OraResizeCanvas.getCurrentSize(panel);
      panel._createShape('rect', { x: 400, y: 400, width: 100, height: 100 });
      await flushFrames();
      const after = win.OraResizeCanvas.getCurrentSize(panel);
      record('lazy-expansion #14: shape inside canvas does NOT trigger expansion',
        after.width === before.width && after.height === before.height,
        'before=' + JSON.stringify(before) + ' after=' + JSON.stringify(after));
      LE.destroy(panel);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('lazy-expansion #14', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 15. setEnabled(false) suppresses growth ────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'le-15' });
      panel.init();
      seedSize(panel, 1000, 1000);
      const ctrl = LE.init(panel);
      ctrl.setEnabled(false);
      const before = win.OraResizeCanvas.getCurrentSize(panel);
      panel._createShape('rect', { x: 850, y: 400, width: 100, height: 100 });
      await flushFrames();
      const after = win.OraResizeCanvas.getCurrentSize(panel);
      record('lazy-expansion #15: setEnabled(false) suppresses growth',
        after.width === before.width,
        'before=' + JSON.stringify(before) + ' after=' + JSON.stringify(after));
      LE.destroy(panel);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('lazy-expansion #15', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 16. checkAndExpand with explicit bounds ────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'le-16' });
      panel.init();
      seedSize(panel, 1000, 1000);
      LE.init(panel);
      const r = LE.checkAndExpand(panel, { x: 850, y: 400, width: 100, height: 100 });
      record('lazy-expansion #16: checkAndExpand with explicit bbox returns apply() result',
        r && r.next && r.next.width === 1250,
        'r=' + JSON.stringify(r && r.next));
      LE.destroy(panel);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('lazy-expansion #16', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 17. checkAndExpand inside → null ───────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'le-17' });
      panel.init();
      seedSize(panel, 1000, 1000);
      LE.init(panel);
      const r = LE.checkAndExpand(panel, { x: 400, y: 400, width: 100, height: 100 });
      record('lazy-expansion #17: checkAndExpand inside canvas returns null',
        r === null, 'r=' + JSON.stringify(r));
      LE.destroy(panel);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('lazy-expansion #17', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 18. canvas-state-changed (AI insertion) triggers expansion ─────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'le-18' });
      panel.init();
      seedSize(panel, 1000, 1000);
      LE.init(panel);
      const before = win.OraResizeCanvas.getCurrentSize(panel);
      // Fire canvas-state-changed with an object near the right edge.
      const ev = new win.CustomEvent('canvas-state-changed', {
        bubbles: true,
        detail: {
          source: 'image_generates',
          object: { x: 850, y: 400, width: 100, height: 100, id: 'img-1' },
        },
      });
      panel.el.dispatchEvent(ev);
      await flushFrames();
      const after = win.OraResizeCanvas.getCurrentSize(panel);
      record('lazy-expansion #18: canvas-state-changed event triggers expansion',
        after.width > before.width,
        'before=' + JSON.stringify(before) + ' after=' + JSON.stringify(after));
      LE.destroy(panel);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('lazy-expansion #18', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 19. Far-out placement grows enough to cover overrun + threshold ────
    try {
      // Object overruns right edge by 1500 px on a 1000-wide canvas. 25 %
      // would only buy 250 px — not enough. Module should grow by at least
      // overrun + threshold = 1500 + 200 = 1700.
      const r = LE.computeExpansion(
        { width: 1000, height: 1000 },
        { x: 800, y: 400, width: 1700, height: 100 },   // right edge at 2500 → overrun 1500
        200, 0.25);
      record('lazy-expansion #19: far-out placement grows by enough to cover overrun + threshold',
        r && r.width >= 1000 + 1700,    // i.e. >= 2700
        'r.width=' + (r && r.width));
    } catch (e) {
      record('lazy-expansion #19', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 20. canvas-lazy-expanded event fires ───────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'le-20' });
      panel.init();
      seedSize(panel, 1000, 1000);
      LE.init(panel);
      let captured = null;
      const handler = function (e) { captured = e.detail; };
      panel.el.addEventListener('canvas-lazy-expanded', handler);
      panel._createShape('rect', { x: 850, y: 400, width: 100, height: 100 });
      await flushFrames();
      panel.el.removeEventListener('canvas-lazy-expanded', handler);
      record('lazy-expansion #20: canvas-lazy-expanded event fires with prior + next dims',
        captured && captured.prior && captured.next && captured.next.width === 1250,
        'detail=' + JSON.stringify(captured && { prior: captured.prior, next: captured.next, anchor: captured.anchor }));
      LE.destroy(panel);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('lazy-expansion #20', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 21. Idempotent init ────────────────────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'le-21' });
      panel.init();
      seedSize(panel, 1000, 1000);
      const c1 = LE.init(panel);
      const c2 = LE.init(panel);   // should destroy c1 internally
      record('lazy-expansion #21: init() twice yields a fresh controller, no error',
        c1 && c2 && c1 !== c2,
        'c1===c2: ' + (c1 === c2));
      LE.destroy(panel);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('lazy-expansion #21', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 22. destroy() removes listener & stops further expansion ───────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'le-22' });
      panel.init();
      seedSize(panel, 1000, 1000);
      LE.init(panel);
      LE.destroy(panel);
      const before = win.OraResizeCanvas.getCurrentSize(panel);
      panel._createShape('rect', { x: 850, y: 400, width: 100, height: 100 });
      await flushFrames();
      const after = win.OraResizeCanvas.getCurrentSize(panel);
      record('lazy-expansion #22: destroy() prevents further auto-growth',
        after.width === before.width,
        'before=' + JSON.stringify(before) + ' after=' + JSON.stringify(after));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('lazy-expansion #22', false, 'threw: ' + (e.stack || e.message || e));
    }
  },
};
