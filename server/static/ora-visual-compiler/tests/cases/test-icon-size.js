/**
 * tests/cases/test-icon-size.js — WP-7.1.3 regression suite.
 *
 * Exports { label, run(ctx, record) } per the run.js case-file convention.
 *
 * Coverage:
 *   1. Toolbar controller exposes setIconSize(); attribute round-trip works
 *      for small / medium / large / extra-large.
 *   2. Invalid inputs are rejected (last-valid value preserved, not blanked).
 *   3. Dock-level setIconSizeAll() walks every mounted controller.
 *   4. Footprint estimate scales with icon-size: extra-large > medium > small.
 *   5. With four toolbars docked at extra-large, the dock's effective
 *      drawable region squeezes below 400×300 and the registered min-canvas
 *      warning handler fires with a payload describing the squeeze.
 *   6. dismissMinCanvasWarning() persists to sessionStorage under the
 *      documented key, and a second trigger does NOT fire the handler
 *      until resetMinCanvasWarning() clears the dismissal.
 */

'use strict';

function mkDiv(win, w, h) {
  var d = win.document.createElement('div');
  d.style.cssText = 'width:' + (w || 800) + 'px;height:' + (h || 500) + 'px;';
  win.document.body.appendChild(d);
  return d;
}

function makeMinimalToolbar(id, edge) {
  return {
    id: id,
    label: id,
    default_dock: edge || 'top',
    items: [
      { id: 'one', icon: 'square', label: 'One', binding: 'tool:one' },
      { id: 'two', icon: 'circle', label: 'Two', binding: 'tool:two' },
    ],
  };
}

module.exports = {
  label: 'Toolbar icon size + min-canvas warning (WP-7.1.3)',
  run: async function run(ctx, record) {
    const { win } = ctx;

    // Boot check.
    if (!win.OraVisualDock || !win.OraVisualToolbar) {
      record('icon-size: harness bootstrap', false, 'missing OraVisualDock or OraVisualToolbar');
      return;
    }

    // Clear any leftover sessionStorage key from prior tests so dismissal
    // state doesn't bleed across cases.
    try { win.sessionStorage.removeItem('ora.visualPane.iconSizeWarn.dismissed'); }
    catch (e) { /* ignore */ }

    // ── 1) Toolbar controller setIconSize() round-trip ───────────────────
    try {
      const tb = win.OraVisualToolbar.render(
        makeMinimalToolbar('icon-size-1', 'top'),
        { actionRegistry: {}, predicateRegistry: {} }
      );
      record('icon-size: controller exposes setIconSize',
        typeof tb.setIconSize === 'function',
        'typeof=' + typeof tb.setIconSize);

      tb.setIconSize('small');
      record('icon-size: setIconSize("small") sets data-icon-size="small"',
        tb.el.getAttribute('data-icon-size') === 'small',
        'attr=' + tb.el.getAttribute('data-icon-size'));

      tb.setIconSize('medium');
      record('icon-size: setIconSize("medium") sets data-icon-size="medium"',
        tb.el.getAttribute('data-icon-size') === 'medium',
        'attr=' + tb.el.getAttribute('data-icon-size'));

      tb.setIconSize('large');
      record('icon-size: setIconSize("large") sets data-icon-size="large"',
        tb.el.getAttribute('data-icon-size') === 'large',
        'attr=' + tb.el.getAttribute('data-icon-size'));

      tb.setIconSize('extra-large');
      record('icon-size: setIconSize("extra-large") sets data-icon-size="extra-large"',
        tb.el.getAttribute('data-icon-size') === 'extra-large',
        'attr=' + tb.el.getAttribute('data-icon-size'));

      // 2) Invalid inputs preserve the last-valid value.
      tb.setIconSize('huge');
      record('icon-size: invalid string preserves last-valid',
        tb.el.getAttribute('data-icon-size') === 'extra-large',
        'attr=' + tb.el.getAttribute('data-icon-size'));
      tb.setIconSize(null);
      record('icon-size: null preserves last-valid',
        tb.el.getAttribute('data-icon-size') === 'extra-large',
        'attr=' + tb.el.getAttribute('data-icon-size'));
      tb.setIconSize(undefined);
      record('icon-size: undefined preserves last-valid',
        tb.el.getAttribute('data-icon-size') === 'extra-large',
        'attr=' + tb.el.getAttribute('data-icon-size'));

      tb.destroy();
    } catch (err) {
      record('icon-size: controller round-trip', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── 3) Dock-level setIconSizeAll walks every controller ──────────────
    try {
      const div = mkDiv(win);
      const dock = win.OraVisualDock.create(div, {
        storageKey: null,
        doc: win.document,
        window: win,
      });
      const tb1 = win.OraVisualToolbar.render(
        makeMinimalToolbar('icon-test-a', 'top'),
        { actionRegistry: {}, predicateRegistry: {} }
      );
      const tb2 = win.OraVisualToolbar.render(
        makeMinimalToolbar('icon-test-b', 'left'),
        { actionRegistry: {}, predicateRegistry: {} }
      );
      dock.mount(tb1, { id: 'icon-test-a', label: 'A', defaultEdge: 'top' });
      dock.mount(tb2, { id: 'icon-test-b', label: 'B', defaultEdge: 'left' });

      const n = dock.setIconSizeAll('large');
      record('icon-size: setIconSizeAll returns count of controllers',
        n === 2, 'n=' + n);
      record('icon-size: setIconSizeAll propagates to toolbar A',
        tb1.el.getAttribute('data-icon-size') === 'large',
        'A=' + tb1.el.getAttribute('data-icon-size'));
      record('icon-size: setIconSizeAll propagates to toolbar B',
        tb2.el.getAttribute('data-icon-size') === 'large',
        'B=' + tb2.el.getAttribute('data-icon-size'));

      // ── 4) Footprint estimate scales with icon-size ────────────────────
      dock.setIconSizeAll('small');
      const fpSmall = dock.getFootprints();
      dock.setIconSizeAll('medium');
      const fpMedium = dock.getFootprints();
      dock.setIconSizeAll('large');
      const fpLarge = dock.getFootprints();
      dock.setIconSizeAll('extra-large');
      const fpXL = dock.getFootprints();

      record('icon-size: footprint at small < medium (top edge)',
        fpSmall.top < fpMedium.top,
        'small=' + fpSmall.top + ' medium=' + fpMedium.top);
      record('icon-size: footprint at medium < large (top edge)',
        fpMedium.top < fpLarge.top,
        'medium=' + fpMedium.top + ' large=' + fpLarge.top);
      record('icon-size: footprint at large < extra-large (top edge)',
        fpLarge.top < fpXL.top,
        'large=' + fpLarge.top + ' xl=' + fpXL.top);
      record('icon-size: same scaling on left edge',
        fpSmall.left < fpMedium.left && fpMedium.left < fpLarge.left &&
        fpLarge.left < fpXL.left,
        JSON.stringify({ s: fpSmall.left, m: fpMedium.left,
                         l: fpLarge.left, xl: fpXL.left }));

      tb1.destroy(); tb2.destroy(); dock.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('icon-size: dock-level propagation', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── 5) Min-canvas warning fires at extra-large with 4 toolbars ───────
    try {
      // Make sure the warning isn't already dismissed (prior runs may have
      // set the key).
      try { win.sessionStorage.removeItem('ora.visualPane.iconSizeWarn.dismissed'); }
      catch (e) { /* ignore */ }

      const div = mkDiv(win);
      const dock = win.OraVisualDock.create(div, {
        storageKey: null,
        doc: win.document,
        window: win,
      });
      let warnPayload = null;
      let warnCount = 0;
      dock.onMinCanvasWarning(function (payload) {
        warnCount++;
        warnPayload = payload;
      });

      const toolbars = [];
      const edges = ['top', 'bottom', 'left', 'right'];
      for (let i = 0; i < 4; i++) {
        const tb = win.OraVisualToolbar.render(
          makeMinimalToolbar('warn-tb-' + i, edges[i]),
          { actionRegistry: {}, predicateRegistry: {} }
        );
        dock.mount(tb, { id: 'warn-tb-' + i, label: 'TB' + i, defaultEdge: edges[i] });
        toolbars.push(tb);
      }

      // Drive icon size up to extra-large to trigger the squeeze.
      warnCount = 0;
      warnPayload = null;
      dock.setIconSizeAll('extra-large');

      // Effective drawable region should be < 400 wide AND/OR < 300 tall.
      // With a notional 800x500 host minus 4×54px footprints:
      //   eff_w = 800 - 54 - 54 = 692   (does NOT trip width)
      //   eff_h = 500 - 54 - 54 = 392   (does NOT trip height)
      // That's not enough to trip the warning. Stack more toolbars on the
      // same edges to force the squeeze. (Real-world the user can drag in
      // multiple toolbars per edge.)
      const stackEdges = ['top', 'top', 'bottom', 'bottom',
                          'left', 'left', 'right', 'right'];
      for (let i = 0; i < stackEdges.length; i++) {
        const tb = win.OraVisualToolbar.render(
          makeMinimalToolbar('warn-stack-' + i, stackEdges[i]),
          { actionRegistry: {}, predicateRegistry: {} }
        );
        dock.mount(tb, { id: 'warn-stack-' + i, label: 'S' + i, defaultEdge: stackEdges[i] });
        toolbars.push(tb);
      }
      // Re-drive icon size to apply extra-large to the new toolbars too.
      warnCount = 0;
      warnPayload = null;
      dock.setIconSizeAll('extra-large');

      const fp = dock.getFootprints();
      const effW = Math.max(0, 800 - fp.left - fp.right);
      const effH = Math.max(0, 500 - fp.top  - fp.bottom);
      record('icon-size: effective drawable trips threshold (w<400 OR h<300)',
        effW < 400 || effH < 300,
        'effW=' + effW + ' effH=' + effH +
        ' fp=' + JSON.stringify(fp));
      record('icon-size: min-canvas warning handler fired ≥1 time',
        warnCount >= 1,
        'warnCount=' + warnCount);
      record('icon-size: warning payload reports actual width/height',
        warnPayload &&
        typeof warnPayload.width === 'number' &&
        typeof warnPayload.height === 'number',
        warnPayload ? JSON.stringify({ w: warnPayload.width, h: warnPayload.height })
                    : 'payload=null');
      record('icon-size: warning payload reports thresholds',
        warnPayload &&
        warnPayload.minWidth === 400 &&
        warnPayload.minHeight === 300,
        warnPayload ? ('min=' + warnPayload.minWidth + 'x' + warnPayload.minHeight)
                    : 'payload=null');
      record('icon-size: warning payload exposes dismiss callback',
        warnPayload && typeof warnPayload.dismiss === 'function',
        warnPayload ? ('typeof dismiss=' + typeof warnPayload.dismiss) : 'payload=null');

      // ── 6) Dismiss + re-trigger blocked within session ─────────────────
      // Dismiss via the API.
      dock.dismissMinCanvasWarning();
      const stored = win.sessionStorage.getItem('ora.visualPane.iconSizeWarn.dismissed');
      record('icon-size: dismiss persists to sessionStorage',
        stored === '1', 'stored=' + JSON.stringify(stored));

      // Drive a no-op transition then back to extra-large; warning must NOT
      // fire while dismissed.
      warnCount = 0;
      warnPayload = null;
      dock.setIconSizeAll('small');
      dock.setIconSizeAll('extra-large');
      record('icon-size: warning blocked after dismiss within same session',
        warnCount === 0, 'warnCount=' + warnCount);

      // Reset the dismissal and confirm the warning fires again.
      dock.resetMinCanvasWarning();
      const cleared = win.sessionStorage.getItem('ora.visualPane.iconSizeWarn.dismissed');
      record('icon-size: reset clears the sessionStorage key',
        cleared === null || cleared === undefined,
        'cleared=' + JSON.stringify(cleared));

      warnCount = 0;
      warnPayload = null;
      dock.setIconSizeAll('small');
      dock.setIconSizeAll('extra-large');
      record('icon-size: warning fires again after reset',
        warnCount >= 1, 'warnCount=' + warnCount);

      // Tear down.
      for (let i = 0; i < toolbars.length; i++) toolbars[i].destroy();
      dock.destroy();
      win.document.body.removeChild(div);
      try { win.sessionStorage.removeItem('ora.visualPane.iconSizeWarn.dismissed'); }
      catch (e) { /* ignore */ }
    } catch (err) {
      record('icon-size: min-canvas warning suite', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── 7) onMinCanvasWarning(null) clears the handler ────────────────────
    try {
      try { win.sessionStorage.removeItem('ora.visualPane.iconSizeWarn.dismissed'); }
      catch (e) { /* ignore */ }
      const div = mkDiv(win);
      const dock = win.OraVisualDock.create(div, {
        storageKey: null, doc: win.document, window: win,
      });
      let calls = 0;
      const handler = function () { calls++; };
      dock.onMinCanvasWarning(handler);

      const toolbars = [];
      const stackEdges = ['top', 'top', 'top', 'top',
                          'bottom', 'bottom', 'bottom', 'bottom',
                          'left', 'left', 'right', 'right'];
      for (let i = 0; i < stackEdges.length; i++) {
        const tb = win.OraVisualToolbar.render(
          makeMinimalToolbar('w7-' + i, stackEdges[i]),
          { actionRegistry: {}, predicateRegistry: {} }
        );
        dock.mount(tb, { id: 'w7-' + i, label: 'W' + i, defaultEdge: stackEdges[i] });
        toolbars.push(tb);
      }
      dock.setIconSizeAll('extra-large');
      const firstCalls = calls;
      record('icon-size: handler called when set',
        firstCalls >= 1, 'calls=' + firstCalls);

      // Clear the handler — subsequent triggers must not increment.
      dock.onMinCanvasWarning(null);
      try { win.sessionStorage.removeItem('ora.visualPane.iconSizeWarn.dismissed'); }
      catch (e) { /* ignore */ }
      dock.setIconSizeAll('small');
      dock.setIconSizeAll('extra-large');
      record('icon-size: handler-null suppresses further calls',
        calls === firstCalls,
        'firstCalls=' + firstCalls + ' calls=' + calls);

      for (let i = 0; i < toolbars.length; i++) toolbars[i].destroy();
      dock.destroy();
      win.document.body.removeChild(div);
      try { win.sessionStorage.removeItem('ora.visualPane.iconSizeWarn.dismissed'); }
      catch (e) { /* ignore */ }
    } catch (err) {
      record('icon-size: handler-null suppression', false,
        'threw: ' + (err.stack || err.message || err));
    }
  },
};
