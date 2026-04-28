/**
 * tests/cases/test-visual-panel.js — WP-2.1 regression suite.
 *
 * Exports { label, run(ctx, record) } per the run.js case-file convention.
 *
 * Coverage (structural — jsdom doesn't pixel-render Konva):
 *   1. Panel init/destroy lifecycle is clean
 *   2. renderSpec(valid envelope) populates backgroundLayer (SVG host)
 *   3. renderSpec(invalid envelope) triggers fallback + error bar
 *   4. onBridgeUpdate(state with ora_visual_blocks) renders most recent
 *   5. canvas_action=clear on bridge clears artifact
 *   6. Keyboard: ArrowDown advances sibling in Olli tree
 *   7. Keyboard: ArrowUp returns to previous sibling
 *   8. Keyboard: Enter descends into first child
 *   9. Keyboard: Escape ascends to parent
 *  10. clearArtifact keeps userInputLayer intact
 *  11. Click on semantic <g> selects it + sets aria-activedescendant
 *  12. Resetting view resets transform to identity
 *  13. Konva-unavailable path still shows error (no crash)
 *  14. window.OraPanels.visual surface is populated
 *  15. renderSpec(null) shows fallback
 *  16. destroy() stops responding to onBridgeUpdate
 *
 * The suite mounts the panel into a fresh <div> inside ctx.win.document,
 * exercises the lifecycle against hand-built envelopes, and asserts on
 * DOM/SVG state plus ariaDescription-driven focus moves.
 */

'use strict';

// ── Helpers ─────────────────────────────────────────────────────────────────
function mkDiv(win) {
  var d = win.document.createElement('div');
  d.style.cssText = 'width:600px;height:400px;';
  win.document.body.appendChild(d);
  return d;
}

function makeBridgeState(envelope) {
  return {
    ora_visual_blocks: [
      { envelope: envelope, source_message_id: 'msg-001' },
    ],
  };
}

function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

// A small, renderer-happy envelope. We reuse the bow_tie fixture
// (loaded from disk) because it is deterministic, validates cleanly
// under Ajv, and the bow_tie renderer produces semantic <g>s in
// jsdom without any of the layout gotchas (no SVG getBBox reliance).
const fs   = require('fs');
const path = require('path');
function smallValidEnvelope(ctx) {
  var examplesDir = (ctx && ctx.EXAMPLES_DIR) || path.resolve(__dirname, '..', '..', '..', '..', '..', 'config', 'visual-schemas', 'examples');
  var p = path.join(examplesDir, 'bow_tie.valid.json');
  return JSON.parse(fs.readFileSync(p, 'utf-8'));
}

function smallInvalidEnvelope() {
  // Missing required top-level fields — triggers validator errors.
  return {
    schema_version: '0.2',
    id: 'fig-vp-bad',
    type: 'not_a_real_type',
    spec: {},
  };
}

// ── Main suite ──────────────────────────────────────────────────────────────
module.exports = {
  label: 'Visual panel (WP-2.1) — lifecycle + bridge + keyboard nav',
  run: async function run(ctx, record) {
    const { win } = ctx;

    // Konva + visual-panel are loaded by run.js bootCompiler() alongside the
    // WP-1.x accessibility modules. If the harness couldn't boot them we
    // record a diagnostic and bail — further asserts would be noise.
    if (typeof win.Konva === 'undefined' || typeof win.VisualPanel === 'undefined') {
      record('visual-panel: harness bootstrap', false,
        'Konva=' + typeof win.Konva + ' VisualPanel=' + typeof win.VisualPanel);
      return;
    }

    // 1) Load check
    record('visual-panel: Konva loaded',
      typeof win.Konva === 'object' && !!win.Konva.Stage,
      typeof win.Konva === 'object' ? ('v' + (win.Konva.version || '?')) : 'missing');
    record('visual-panel: VisualPanel exposed',
      typeof win.VisualPanel === 'function',
      typeof win.VisualPanel);
    record('visual-panel: window.OraPanels.visual surface populated',
      !!(win.OraPanels && win.OraPanels.visual && typeof win.OraPanels.visual.init === 'function' &&
         typeof win.OraPanels.visual.renderSpec === 'function' &&
         typeof win.OraPanels.visual.clearArtifact === 'function' &&
         typeof win.OraPanels.visual.onBridgeUpdate === 'function'),
      win.OraPanels && win.OraPanels.visual ? Object.keys(win.OraPanels.visual).join(',') : '(none)');

    // 2) init/destroy lifecycle
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'test-1' });
      panel.init();
      const hasToolbar = !!div.querySelector('.visual-panel__toolbar');
      const hasViewport = !!div.querySelector('.visual-panel__viewport');
      const hasSvgHost = !!div.querySelector('.visual-panel__svg-host');
      const hasTabindex = div.getAttribute('tabindex') === '0';
      record('visual-panel: init creates required DOM structure',
        hasToolbar && hasViewport && hasSvgHost && hasTabindex,
        (hasToolbar ? '' : 'no toolbar;') + (hasViewport ? '' : 'no viewport;') +
        (hasSvgHost ? '' : 'no svg-host;') + (hasTabindex ? '' : 'no tabindex'));
      record('visual-panel: stage has four layers',
        panel.backgroundLayer && panel.annotationLayer && panel.userInputLayer && panel.selectionLayer,
        [!!panel.backgroundLayer, !!panel.annotationLayer, !!panel.userInputLayer, !!panel.selectionLayer].join(','));
      panel.destroy();
      record('visual-panel: destroy clears stage references',
        panel.stage === null,
        panel.stage === null ? '' : 'stage still ' + typeof panel.stage);
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-panel: init/destroy lifecycle', false, 'threw: ' + (err.stack || err.message || err));
    }

    // 3) renderSpec(valid envelope) — populates SVG host
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'test-2' });
      panel.init();
      let r = panel.renderSpec(smallValidEnvelope(ctx));
      if (r && typeof r.then === 'function') await r;
      const svgHost = div.querySelector('.visual-panel__svg-host');
      const svgEl = svgHost && svgHost.querySelector('svg');
      record('visual-panel: renderSpec(valid) installs <svg> into svg-host',
        !!svgEl,
        svgEl ? ('svg w/ ' + svgEl.querySelectorAll('*').length + ' descendants') : 'no <svg>');
      const fallback = div.querySelector('.visual-panel__fallback');
      record('visual-panel: renderSpec(valid) leaves fallback hidden',
        fallback && fallback.hidden,
        fallback ? ('hidden=' + fallback.hidden) : 'no fallback el');
      const errorBar = div.querySelector('.visual-panel__errorbar');
      record('visual-panel: renderSpec(valid) leaves errorbar hidden',
        errorBar && errorBar.hidden,
        errorBar ? ('hidden=' + errorBar.hidden) : 'no errorbar el');
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-panel: renderSpec(valid)', false, 'threw: ' + (err.stack || err.message || err));
    }

    // 4) renderSpec(invalid envelope) — triggers fallback + error bar
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'test-3' });
      panel.init();
      let r = panel.renderSpec(smallInvalidEnvelope());
      if (r && typeof r.then === 'function') await r;
      const svgHost = div.querySelector('.visual-panel__svg-host');
      const svgEl = svgHost && svgHost.querySelector('svg');
      record('visual-panel: renderSpec(invalid) leaves svg-host empty',
        !svgEl,
        svgEl ? 'svg still present' : '');
      const errorBar = div.querySelector('.visual-panel__errorbar');
      record('visual-panel: renderSpec(invalid) shows error bar',
        errorBar && !errorBar.hidden && errorBar.textContent.length > 0,
        errorBar ? ('hidden=' + errorBar.hidden + ' text="' + errorBar.textContent.slice(0, 60) + '"') : 'no errorbar el');
      const fallback = div.querySelector('.visual-panel__fallback');
      record('visual-panel: renderSpec(invalid) reveals fallback panel',
        fallback && !fallback.hidden,
        fallback ? ('hidden=' + fallback.hidden) : 'no fallback el');
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-panel: renderSpec(invalid)', false, 'threw: ' + (err.stack || err.message || err));
    }

    // 5) renderSpec(null) — fallback
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'test-4' });
      panel.init();
      let r = panel.renderSpec(null);
      if (r && typeof r.then === 'function') await r;
      const errorBar = div.querySelector('.visual-panel__errorbar');
      record('visual-panel: renderSpec(null) shows error bar',
        errorBar && !errorBar.hidden,
        errorBar ? ('hidden=' + errorBar.hidden) : 'no errorbar el');
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-panel: renderSpec(null)', false, 'threw: ' + (err.stack || err.message || err));
    }

    // 6) onBridgeUpdate with ora_visual_blocks — renders
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'test-5' });
      panel.init();
      panel.onBridgeUpdate(makeBridgeState(smallValidEnvelope(ctx)));
      // onBridgeUpdate -> renderSpec returns a Promise internally; we mirror
      // that by awaiting a microtask cycle before asserting.
      await wait(15);
      const svgEl = div.querySelector('.visual-panel__svg-host svg');
      record('visual-panel: onBridgeUpdate(state.ora_visual_blocks) renders most recent',
        !!svgEl,
        svgEl ? 'svg installed' : 'no svg after bridge update');
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-panel: onBridgeUpdate renders', false, 'threw: ' + (err.stack || err.message || err));
    }

    // 7) onBridgeUpdate with MULTIPLE blocks — renders LAST
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'test-6' });
      panel.init();
      const env1 = smallValidEnvelope(ctx); env1.id = 'fig-vp-first';
      const env2 = smallValidEnvelope(ctx); env2.id = 'fig-vp-second';
      panel.onBridgeUpdate({
        ora_visual_blocks: [
          { envelope: env1, source_message_id: 'a' },
          { envelope: env2, source_message_id: 'b' },
        ],
      });
      await wait(15);
      record('visual-panel: onBridgeUpdate picks LAST block when multiple present',
        panel._currentEnvelope && panel._currentEnvelope.id === 'fig-vp-second',
        panel._currentEnvelope ? panel._currentEnvelope.id : 'none');
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-panel: onBridgeUpdate last-wins', false, 'threw: ' + (err.stack || err.message || err));
    }

    // 8) canvas_action=clear clears artifact
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'test-7' });
      panel.init();
      let r = panel.renderSpec(smallValidEnvelope(ctx));
      if (r && typeof r.then === 'function') await r;
      const before = !!div.querySelector('.visual-panel__svg-host svg');
      const env = smallValidEnvelope(ctx);
      env.canvas_action = 'clear';
      panel.onBridgeUpdate({ ora_visual_blocks: [{ envelope: env }] });
      await wait(10);
      const after = !!div.querySelector('.visual-panel__svg-host svg');
      record('visual-panel: canvas_action=clear removes artifact',
        before && !after,
        'before=' + before + ' after=' + after);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-panel: canvas_action=clear', false, 'threw: ' + (err.stack || err.message || err));
    }

    // 9) Keyboard: ArrowDown → next sibling in Olli tree
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'test-8' });
      panel.init();
      // Synthetic ariaDescription: 3 level-1 siblings
      panel._ariaDescription = {
        root_id: 'root',
        nodes: [
          { id: 's1', level: 1, label: 'S1', parent_id: null, children_ids: [] },
          { id: 's2', level: 1, label: 'S2', parent_id: null, children_ids: [] },
          { id: 's3', level: 1, label: 'S3', parent_id: null, children_ids: [] },
        ],
      };
      // Install matching DOM nodes for _focusNavId lookup.
      panel._svgHost.innerHTML =
        '<svg xmlns="http://www.w3.org/2000/svg">' +
        '<g id="s1" class="ora-visual__node" role="graphics-symbol"></g>' +
        '<g id="s2" class="ora-visual__node" role="graphics-symbol"></g>' +
        '<g id="s3" class="ora-visual__node" role="graphics-symbol"></g>' +
        '</svg>';
      panel._selectedNodeId = 's1';
      const evtDown = new win.KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true });
      div.dispatchEvent(evtDown);
      record('visual-panel: ArrowDown advances to next sibling',
        panel._selectedNodeId === 's2',
        'selected=' + panel._selectedNodeId);

      // ArrowUp goes back
      const evtUp = new win.KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true });
      div.dispatchEvent(evtUp);
      record('visual-panel: ArrowUp returns to previous sibling',
        panel._selectedNodeId === 's1',
        'selected=' + panel._selectedNodeId);

      // Arrow at end does nothing
      panel._selectedNodeId = 's3';
      div.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
      record('visual-panel: ArrowDown at end clamps (no wrap)',
        panel._selectedNodeId === 's3',
        'selected=' + panel._selectedNodeId);

      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-panel: keyboard sibling nav', false, 'threw: ' + (err.stack || err.message || err));
    }

    // 10) Keyboard: Enter descends into first child; Escape ascends
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'test-9' });
      panel.init();
      panel._ariaDescription = {
        root_id: 'root',
        nodes: [
          { id: 'p',  level: 1, label: 'P',  parent_id: null, children_ids: ['c1', 'c2'] },
          { id: 'c1', level: 2, label: 'C1', parent_id: 'p',  children_ids: [] },
          { id: 'c2', level: 2, label: 'C2', parent_id: 'p',  children_ids: [] },
        ],
      };
      panel._svgHost.innerHTML =
        '<svg xmlns="http://www.w3.org/2000/svg">' +
        '<g id="p" class="ora-visual__node" role="graphics-symbol">' +
          '<g id="c1" class="ora-visual__node" role="graphics-symbol"></g>' +
          '<g id="c2" class="ora-visual__node" role="graphics-symbol"></g>' +
        '</g>' +
        '</svg>';
      panel._selectedNodeId = 'p';
      div.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
      record('visual-panel: Enter descends to first child',
        panel._selectedNodeId === 'c1',
        'selected=' + panel._selectedNodeId);
      div.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      record('visual-panel: Escape ascends to parent',
        panel._selectedNodeId === 'p',
        'selected=' + panel._selectedNodeId);
      // Escape at root level clears selection
      panel._selectedNodeId = 'p';
      div.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      record('visual-panel: Escape at root clears selection',
        panel._selectedNodeId === null,
        'selected=' + panel._selectedNodeId);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-panel: keyboard Enter/Escape', false, 'threw: ' + (err.stack || err.message || err));
    }

    // 11) clearArtifact preserves userInputLayer
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'test-10' });
      panel.init();
      // Seed userInputLayer with a Konva.Rect
      if (panel.userInputLayer && win.Konva) {
        panel.userInputLayer.add(new win.Konva.Rect({ x: 0, y: 0, width: 10, height: 10 }));
      }
      const before = panel.userInputLayer ? panel.userInputLayer.getChildren().length : -1;
      let r = panel.renderSpec(smallValidEnvelope(ctx));
      if (r && typeof r.then === 'function') await r;
      panel.clearArtifact();
      const after = panel.userInputLayer ? panel.userInputLayer.getChildren().length : -1;
      record('visual-panel: clearArtifact preserves userInputLayer children',
        before === after && before > 0,
        'before=' + before + ' after=' + after);
      // Selection layer is cleared though
      record('visual-panel: clearArtifact wipes selection highlight',
        panel.selectionLayer.getChildren().length === 0,
        'selection children=' + panel.selectionLayer.getChildren().length);
      // SVG host is emptied
      record('visual-panel: clearArtifact empties svg-host',
        panel._svgHost.innerHTML === '' || !panel._svgHost.querySelector('svg'),
        'svg=' + !!panel._svgHost.querySelector('svg'));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-panel: clearArtifact semantics', false, 'threw: ' + (err.stack || err.message || err));
    }

    // 12) Click on semantic <g> → sets _selectedNodeId + aria-activedescendant
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'test-11' });
      panel.init();
      panel._svgHost.innerHTML =
        '<svg xmlns="http://www.w3.org/2000/svg">' +
        '<g id="n1" class="ora-visual__node" role="graphics-symbol" aria-label="N1"></g>' +
        '</svg>';
      panel._wireSemanticInteractions();
      // Simulate click on the <g>
      const gEl = panel._svgHost.querySelector('g');
      if (gEl) {
        const clickEvt = new win.MouseEvent('click', { bubbles: true, cancelable: true });
        gEl.dispatchEvent(clickEvt);
      }
      record('visual-panel: click on semantic <g> sets _selectedNodeId',
        panel._selectedNodeId === 'n1',
        'selected=' + panel._selectedNodeId);
      record('visual-panel: click sets aria-activedescendant on panel root',
        div.getAttribute('aria-activedescendant') === 'n1',
        'aria-activedescendant=' + div.getAttribute('aria-activedescendant'));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-panel: click selection', false, 'threw: ' + (err.stack || err.message || err));
    }

    // 13) resetView restores identity transform
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'test-12' });
      panel.init();
      panel._transform = { x: 100, y: 50, scale: 2 };
      panel._applyTransform();
      panel.resetView();
      record('visual-panel: resetView restores x=0 y=0 scale=1',
        panel._transform.x === 0 && panel._transform.y === 0 && panel._transform.scale === 1,
        JSON.stringify(panel._transform));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-panel: resetView', false, 'threw: ' + (err.stack || err.message || err));
    }

    // 14) destroy() stops responding to bridge updates
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'test-13' });
      panel.init();
      panel.destroy();
      // No throw on bridge update after destroy
      panel.onBridgeUpdate(makeBridgeState(smallValidEnvelope(ctx)));
      await wait(10);
      // renderSpec after destroy returns resolved promise (no-op)
      let r = panel.renderSpec(smallValidEnvelope(ctx));
      if (r && typeof r.then === 'function') await r;
      record('visual-panel: post-destroy renderSpec is a safe no-op',
        true, 'no throw');
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-panel: post-destroy safety', false, 'threw: ' + (err.stack || err.message || err));
    }

    // 15) window.OraPanels.visual.init wires the active instance
    try {
      const div = mkDiv(win);
      const inst = win.OraPanels.visual.init(div, { id: 'test-14' });
      record('visual-panel: OraPanels.visual.init returns an instance',
        inst instanceof win.VisualPanel,
        inst ? inst.constructor.name : 'none');
      // Dispatch via surface
      let r = win.OraPanels.visual.renderSpec(smallValidEnvelope(ctx));
      if (r && typeof r.then === 'function') await r;
      const svgEl = div.querySelector('.visual-panel__svg-host svg');
      record('visual-panel: OraPanels.visual.renderSpec routes to active instance',
        !!svgEl,
        svgEl ? 'svg installed' : 'no svg');
      win.OraPanels.visual.clearArtifact();
      const after = div.querySelector('.visual-panel__svg-host svg');
      record('visual-panel: OraPanels.visual.clearArtifact routes to active instance',
        !after,
        after ? 'svg still present' : '');
      win.OraPanels.visual.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-panel: OraPanels.visual surface routing', false, 'threw: ' + (err.stack || err.message || err));
    }

    // 16) renderSpec throws-safety when compiler API is gone
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'test-15' });
      panel.init();
      const saved = win.OraVisualCompiler;
      win.OraVisualCompiler = undefined;
      let r = panel.renderSpec(smallValidEnvelope(ctx));
      if (r && typeof r.then === 'function') await r;
      const errorBar = div.querySelector('.visual-panel__errorbar');
      record('visual-panel: renderSpec when compiler missing → error bar',
        errorBar && !errorBar.hidden,
        errorBar ? ('hidden=' + errorBar.hidden + ' text="' + errorBar.textContent.slice(0, 40) + '"') : 'no errorbar el');
      win.OraVisualCompiler = saved;
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-panel: compiler-missing safety', false, 'threw: ' + (err.stack || err.message || err));
    }
  },
};
