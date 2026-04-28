/**
 * tests/cases/test-canvas-action.js — WP-2.4 regression suite.
 *
 * Exports { label, run(ctx, record) } per the run.js case-file convention.
 *
 * Coverage of the canvas_action state machine (visual-panel.js):
 *   1. First envelope with no canvas_action → replace applied (fresh stage).
 *   2. Subsequent envelope with no canvas_action → update applied
 *      (backgroundLayer replaced; userInputLayer preserved).
 *   3. Explicit canvas_action:"replace" on subsequent → all four layers cleared.
 *   4. Explicit canvas_action:"update" on first → still behaves like update
 *      (explicit always wins over turn-position default).
 *   5. Explicit canvas_action:"annotate" → backgroundLayer unchanged;
 *      annotationLayer populated.
 *   6. Explicit canvas_action:"clear" → all layers empty; state reset
 *      (_hasPriorVisual back to false).
 *   7. User-input layer preservation under update (inject a mock user shape
 *      first, then update, verify shape still present).
 *   8. User-input layer preservation under annotate.
 *   9. Malformed canvas_action value → validator catches (E_SCHEMA_INVALID).
 *  10. Annotate with unsupported kind ("arrow") → W_ANNOTATION_KIND_DEFERRED.
 *  11. Annotate with unsupported kind ("badge") → W_ANNOTATION_KIND_DEFERRED.
 *  12. _conversationTurn increments correctly across bridge updates.
 *  13. Annotate with no annotations content → W_ANNOTATE_NO_CONTENT.
 *  14. Annotate with missing target_id → W_ANNOTATION_TARGET_MISSING.
 *  15. Callout annotation renders into annotationLayer.
 *  16. Highlight annotation renders into annotationLayer.
 *  17. clear resets _hasPriorVisual to false (next omitted envelope → replace).
 *  18. Schema validates envelope with each of the four canvas_action values.
 */

'use strict';

const fs   = require('fs');
const path = require('path');

function mkDiv(win) {
  var d = win.document.createElement('div');
  d.style.cssText = 'width:600px;height:400px;';
  win.document.body.appendChild(d);
  return d;
}

function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

function loadBowTie(ctx) {
  var examplesDir = (ctx && ctx.EXAMPLES_DIR) || path.resolve(__dirname, '..', '..', '..', '..', '..', 'config', 'visual-schemas', 'examples');
  var p = path.join(examplesDir, 'bow_tie.valid.json');
  return JSON.parse(fs.readFileSync(p, 'utf-8'));
}

function cloneWithId(env, id) {
  var copy = JSON.parse(JSON.stringify(env));
  copy.id = id;
  return copy;
}

function bridgeFor(env) {
  return { ora_visual_blocks: [{ envelope: env, source_message_id: 'msg-' + env.id }] };
}

module.exports = {
  label: 'Canvas action state machine (WP-2.4) — replace / update / annotate / clear',
  run: async function run(ctx, record) {
    const { win } = ctx;

    if (typeof win.Konva === 'undefined' || typeof win.VisualPanel === 'undefined') {
      record('canvas-action: harness bootstrap', false,
        'Konva=' + typeof win.Konva + ' VisualPanel=' + typeof win.VisualPanel);
      return;
    }

    // ── 1. First envelope with no canvas_action → replace ──────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'ca-1' });
      panel.init();
      // Seed userInputLayer with a mock shape.
      panel.userInputLayer.add(new win.Konva.Rect({ x: 5, y: 5, width: 10, height: 10, name: 'user-seed' }));
      const userBefore = panel.userInputLayer.getChildren().length;
      // First envelope (no canvas_action).
      const env = loadBowTie(ctx);
      delete env.canvas_action;
      panel.onBridgeUpdate(bridgeFor(env));
      await wait(20);
      record('canvas-action #1: first envelope with no canvas_action uses replace',
        panel._lastAction === 'replace',
        '_lastAction=' + panel._lastAction);
      // replace clears userInputLayer — the seed is gone.
      const userAfter = panel.userInputLayer.getChildren().length;
      record('canvas-action #1b: replace clears userInputLayer',
        userBefore > 0 && userAfter === 0,
        'before=' + userBefore + ' after=' + userAfter);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('canvas-action #1', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 2. Subsequent envelope with no canvas_action → update ──────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'ca-2' });
      panel.init();
      const env1 = cloneWithId(loadBowTie(ctx), 'ca2-first');
      delete env1.canvas_action;
      panel.onBridgeUpdate(bridgeFor(env1));
      await wait(20);
      // After first visual lands, stash a user drawing.
      panel.userInputLayer.add(new win.Konva.Rect({ x: 5, y: 5, width: 10, height: 10, name: 'user-seed-2' }));
      const userBefore = panel.userInputLayer.getChildren().length;
      // Second envelope (no canvas_action) should update, not replace.
      const env2 = cloneWithId(loadBowTie(ctx), 'ca2-second');
      delete env2.canvas_action;
      panel.onBridgeUpdate(bridgeFor(env2));
      await wait(20);
      record('canvas-action #2: subsequent with no canvas_action uses update',
        panel._lastAction === 'update',
        '_lastAction=' + panel._lastAction);
      const userAfter = panel.userInputLayer.getChildren().length;
      record('canvas-action #2b: update preserves userInputLayer',
        userBefore === userAfter && userBefore > 0,
        'before=' + userBefore + ' after=' + userAfter);
      record('canvas-action #2c: update replaces _currentEnvelope',
        panel._currentEnvelope && panel._currentEnvelope.id === 'ca2-second',
        'id=' + (panel._currentEnvelope && panel._currentEnvelope.id));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('canvas-action #2', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 3. Explicit "replace" on subsequent → all layers cleared ───────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'ca-3' });
      panel.init();
      const env1 = cloneWithId(loadBowTie(ctx), 'ca3-first');
      panel.onBridgeUpdate(bridgeFor(env1));
      await wait(20);
      panel.userInputLayer.add(new win.Konva.Rect({ x: 0, y: 0, width: 5, height: 5 }));
      panel.annotationLayer.add(new win.Konva.Circle({ radius: 3 }));
      const env2 = cloneWithId(loadBowTie(ctx), 'ca3-second');
      env2.canvas_action = 'replace';
      panel.onBridgeUpdate(bridgeFor(env2));
      await wait(20);
      record('canvas-action #3: explicit replace on subsequent clears userInputLayer',
        panel.userInputLayer.getChildren().length === 0,
        'userInput children=' + panel.userInputLayer.getChildren().length);
      record('canvas-action #3b: explicit replace on subsequent clears annotationLayer',
        panel.annotationLayer.getChildren().length === 0,
        'annotation children=' + panel.annotationLayer.getChildren().length);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('canvas-action #3', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 4. Explicit "update" on first → still update ───────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'ca-4' });
      panel.init();
      const env = loadBowTie(ctx);
      env.canvas_action = 'update';
      panel.onBridgeUpdate(bridgeFor(env));
      await wait(20);
      record('canvas-action #4: explicit "update" on first envelope honored',
        panel._lastAction === 'update',
        '_lastAction=' + panel._lastAction);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('canvas-action #4', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 5. Explicit "annotate" → backgroundLayer unchanged; annotationLayer populated ─
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'ca-5' });
      panel.init();
      // Land a first visual so we have a background + DOM SVG to annotate.
      const env1 = cloneWithId(loadBowTie(ctx), 'ca5-first');
      panel.onBridgeUpdate(bridgeFor(env1));
      await wait(20);
      // Inject a known-id target into the SVG so _computeTargetBox can find it.
      const svg = panel._svgHost.querySelector('svg');
      if (svg) {
        const g = win.document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('id', 'anno-target-1');
        g.setAttribute('class', 'ora-visual__node');
        svg.appendChild(g);
      }
      const svgBefore = panel._svgHost.querySelector('svg');
      const bgBefore = panel._svgHost.innerHTML;
      // Now emit an annotate envelope.
      const annoEnv = cloneWithId(loadBowTie(ctx), 'ca5-anno');
      annoEnv.canvas_action = 'annotate';
      annoEnv.annotations = [
        { target_id: 'anno-target-1', kind: 'callout', text: 'Watch this node' },
      ];
      panel.onBridgeUpdate(bridgeFor(annoEnv));
      await wait(20);
      record('canvas-action #5: annotate preserves backgroundLayer DOM',
        panel._svgHost.innerHTML === bgBefore && !!svgBefore,
        'bg-unchanged=' + (panel._svgHost.innerHTML === bgBefore));
      record('canvas-action #5b: annotate populates annotationLayer',
        panel.annotationLayer.getChildren().length > 0,
        'annotation children=' + panel.annotationLayer.getChildren().length);
      record('canvas-action #5c: annotate does not overwrite _currentEnvelope',
        panel._currentEnvelope && panel._currentEnvelope.id === 'ca5-first',
        'current id=' + (panel._currentEnvelope && panel._currentEnvelope.id));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('canvas-action #5', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 6. Explicit "clear" → all layers empty; state reset ────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'ca-6' });
      panel.init();
      const env1 = cloneWithId(loadBowTie(ctx), 'ca6-first');
      panel.onBridgeUpdate(bridgeFor(env1));
      await wait(20);
      panel.userInputLayer.add(new win.Konva.Rect({ x: 1, y: 1, width: 2, height: 2 }));
      panel.annotationLayer.add(new win.Konva.Rect({ x: 1, y: 1, width: 2, height: 2 }));
      const env2 = cloneWithId(loadBowTie(ctx), 'ca6-clear');
      env2.canvas_action = 'clear';
      panel.onBridgeUpdate(bridgeFor(env2));
      await wait(20);
      record('canvas-action #6: clear empties backgroundLayer (DOM)',
        !panel._svgHost.querySelector('svg'),
        'svg present=' + !!panel._svgHost.querySelector('svg'));
      record('canvas-action #6b: clear empties userInputLayer',
        panel.userInputLayer.getChildren().length === 0,
        'userInput=' + panel.userInputLayer.getChildren().length);
      record('canvas-action #6c: clear empties annotationLayer',
        panel.annotationLayer.getChildren().length === 0,
        'annotation=' + panel.annotationLayer.getChildren().length);
      record('canvas-action #6d: clear resets _hasPriorVisual',
        panel._hasPriorVisual === false,
        '_hasPriorVisual=' + panel._hasPriorVisual);
      record('canvas-action #6e: clear resets _currentEnvelope',
        panel._currentEnvelope === null,
        '_currentEnvelope=' + panel._currentEnvelope);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('canvas-action #6', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 7. userInputLayer preservation under update (seed-before, verify-after) ─
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'ca-7' });
      panel.init();
      const env1 = cloneWithId(loadBowTie(ctx), 'ca7-first');
      panel.onBridgeUpdate(bridgeFor(env1));
      await wait(20);
      const userShape = new win.Konva.Rect({ x: 42, y: 42, width: 7, height: 7, name: 'user-unique-7' });
      panel.userInputLayer.add(userShape);
      const env2 = cloneWithId(loadBowTie(ctx), 'ca7-second');
      env2.canvas_action = 'update';
      panel.onBridgeUpdate(bridgeFor(env2));
      await wait(20);
      const stillThere = panel.userInputLayer.findOne('.user-unique-7');
      record('canvas-action #7: update preserves the exact user shape (by name)',
        !!stillThere,
        'found=' + !!stillThere);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('canvas-action #7', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 8. userInputLayer preservation under annotate ──────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'ca-8' });
      panel.init();
      const env1 = cloneWithId(loadBowTie(ctx), 'ca8-first');
      panel.onBridgeUpdate(bridgeFor(env1));
      await wait(20);
      panel.userInputLayer.add(new win.Konva.Rect({ name: 'user-unique-8', x: 0, y: 0, width: 3, height: 3 }));
      // Inject an annotatable target.
      const svg = panel._svgHost.querySelector('svg');
      if (svg) {
        const g = win.document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('id', 'ca8-target');
        svg.appendChild(g);
      }
      const annoEnv = cloneWithId(loadBowTie(ctx), 'ca8-anno');
      annoEnv.canvas_action = 'annotate';
      annoEnv.annotations = [{ target_id: 'ca8-target', kind: 'highlight' }];
      panel.onBridgeUpdate(bridgeFor(annoEnv));
      await wait(20);
      record('canvas-action #8: annotate preserves userInputLayer',
        !!panel.userInputLayer.findOne('.user-unique-8'),
        'children=' + panel.userInputLayer.getChildren().length);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('canvas-action #8', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 9. Malformed canvas_action value → validator catches ───────────────
    try {
      const compiler = win.OraVisualCompiler;
      const env = cloneWithId(loadBowTie(ctx), 'ca9-bad');
      env.canvas_action = 'flamethrower';
      const vresult = compiler.validate(env);
      const hasSchemaErr = !vresult.valid && vresult.errors.some(function (e) {
        return e.code === 'E_SCHEMA_INVALID';
      });
      record('canvas-action #9: bogus canvas_action fails schema (E_SCHEMA_INVALID)',
        hasSchemaErr,
        'valid=' + vresult.valid + ' codes=' + vresult.errors.map(function (e) { return e.code; }).join(','));
    } catch (e) {
      record('canvas-action #9', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 10. Annotate with unsupported kind ("arrow") → W_ANNOTATION_KIND_DEFERRED ─
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'ca-10' });
      panel.init();
      const env1 = cloneWithId(loadBowTie(ctx), 'ca10-first');
      panel.onBridgeUpdate(bridgeFor(env1));
      await wait(20);
      // Inject target so target resolution doesn't block.
      const svg = panel._svgHost.querySelector('svg');
      if (svg) {
        const g = win.document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('id', 'ca10-t');
        svg.appendChild(g);
      }
      const annoEnv = cloneWithId(loadBowTie(ctx), 'ca10-anno');
      annoEnv.canvas_action = 'annotate';
      annoEnv.annotations = [{ target_id: 'ca10-t', kind: 'arrow', text: 'x' }];
      panel.onBridgeUpdate(bridgeFor(annoEnv));
      await wait(20);
      const warn = (panel._annotationWarnings || []).find(function (w) { return w.code === 'W_ANNOTATION_KIND_DEFERRED'; });
      record('canvas-action #10: arrow kind → W_ANNOTATION_KIND_DEFERRED',
        !!warn,
        'warnings=' + (panel._annotationWarnings || []).map(function (w) { return w.code; }).join(','));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('canvas-action #10', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 11. badge kind → W_ANNOTATION_KIND_DEFERRED ────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'ca-11' });
      panel.init();
      const env1 = cloneWithId(loadBowTie(ctx), 'ca11-first');
      panel.onBridgeUpdate(bridgeFor(env1));
      await wait(20);
      const svg = panel._svgHost.querySelector('svg');
      if (svg) {
        const g = win.document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('id', 'ca11-t');
        svg.appendChild(g);
      }
      const annoEnv = cloneWithId(loadBowTie(ctx), 'ca11-anno');
      annoEnv.canvas_action = 'annotate';
      annoEnv.annotations = [{ target_id: 'ca11-t', kind: 'badge' }];
      panel.onBridgeUpdate(bridgeFor(annoEnv));
      await wait(20);
      const warn = (panel._annotationWarnings || []).find(function (w) { return w.code === 'W_ANNOTATION_KIND_DEFERRED'; });
      record('canvas-action #11: badge kind → W_ANNOTATION_KIND_DEFERRED',
        !!warn,
        'warnings=' + (panel._annotationWarnings || []).map(function (w) { return w.code; }).join(','));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('canvas-action #11', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 12. _conversationTurn increments across bridge updates ─────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'ca-12' });
      panel.init();
      record('canvas-action #12a: _conversationTurn starts at 0',
        panel._conversationTurn === 0,
        'turn=' + panel._conversationTurn);
      panel.onBridgeUpdate(bridgeFor(cloneWithId(loadBowTie(ctx), 'ca12-1')));
      await wait(10);
      const after1 = panel._conversationTurn;
      panel.onBridgeUpdate(bridgeFor(cloneWithId(loadBowTie(ctx), 'ca12-2')));
      await wait(10);
      const after2 = panel._conversationTurn;
      panel.onBridgeUpdate(bridgeFor(cloneWithId(loadBowTie(ctx), 'ca12-3')));
      await wait(10);
      const after3 = panel._conversationTurn;
      record('canvas-action #12b: _conversationTurn increments on each bridge',
        after1 === 1 && after2 === 2 && after3 === 3,
        'after1=' + after1 + ' after2=' + after2 + ' after3=' + after3);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('canvas-action #12', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 13. Annotate with no content → W_ANNOTATE_NO_CONTENT ───────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'ca-13' });
      panel.init();
      const env1 = cloneWithId(loadBowTie(ctx), 'ca13-first');
      panel.onBridgeUpdate(bridgeFor(env1));
      await wait(20);
      const annoEnv = cloneWithId(loadBowTie(ctx), 'ca13-anno');
      annoEnv.canvas_action = 'annotate';
      // Deliberately no annotations array on envelope or spec.
      panel.onBridgeUpdate(bridgeFor(annoEnv));
      await wait(20);
      const warn = (panel._annotationWarnings || []).find(function (w) { return w.code === 'W_ANNOTATE_NO_CONTENT'; });
      record('canvas-action #13: annotate without content → W_ANNOTATE_NO_CONTENT',
        !!warn,
        'warnings=' + (panel._annotationWarnings || []).map(function (w) { return w.code; }).join(','));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('canvas-action #13', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 14. Annotate target missing → W_ANNOTATION_TARGET_MISSING ──────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'ca-14' });
      panel.init();
      const env1 = cloneWithId(loadBowTie(ctx), 'ca14-first');
      panel.onBridgeUpdate(bridgeFor(env1));
      await wait(20);
      const annoEnv = cloneWithId(loadBowTie(ctx), 'ca14-anno');
      annoEnv.canvas_action = 'annotate';
      annoEnv.annotations = [{ target_id: 'no-such-id', kind: 'highlight' }];
      panel.onBridgeUpdate(bridgeFor(annoEnv));
      await wait(20);
      const warn = (panel._annotationWarnings || []).find(function (w) { return w.code === 'W_ANNOTATION_TARGET_MISSING'; });
      record('canvas-action #14: missing target → W_ANNOTATION_TARGET_MISSING',
        !!warn,
        'warnings=' + (panel._annotationWarnings || []).map(function (w) { return w.code; }).join(','));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('canvas-action #14', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 15. Callout renders into annotationLayer ───────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'ca-15' });
      panel.init();
      const env1 = cloneWithId(loadBowTie(ctx), 'ca15-first');
      panel.onBridgeUpdate(bridgeFor(env1));
      await wait(20);
      const svg = panel._svgHost.querySelector('svg');
      if (svg) {
        const g = win.document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('id', 'ca15-t');
        svg.appendChild(g);
      }
      const before = panel.annotationLayer.getChildren().length;
      const annoEnv = cloneWithId(loadBowTie(ctx), 'ca15-anno');
      annoEnv.canvas_action = 'annotate';
      annoEnv.annotations = [{ target_id: 'ca15-t', kind: 'callout', text: 'hello' }];
      panel.onBridgeUpdate(bridgeFor(annoEnv));
      await wait(20);
      const after = panel.annotationLayer.getChildren().length;
      record('canvas-action #15: callout adds a child to annotationLayer',
        after > before,
        'before=' + before + ' after=' + after);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('canvas-action #15', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 16. Highlight renders into annotationLayer ─────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'ca-16' });
      panel.init();
      const env1 = cloneWithId(loadBowTie(ctx), 'ca16-first');
      panel.onBridgeUpdate(bridgeFor(env1));
      await wait(20);
      const svg = panel._svgHost.querySelector('svg');
      if (svg) {
        const g = win.document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('id', 'ca16-t');
        svg.appendChild(g);
      }
      const before = panel.annotationLayer.getChildren().length;
      const annoEnv = cloneWithId(loadBowTie(ctx), 'ca16-anno');
      annoEnv.canvas_action = 'annotate';
      annoEnv.annotations = [{ target_id: 'ca16-t', kind: 'highlight' }];
      panel.onBridgeUpdate(bridgeFor(annoEnv));
      await wait(20);
      const after = panel.annotationLayer.getChildren().length;
      record('canvas-action #16: highlight adds a child to annotationLayer',
        after > before,
        'before=' + before + ' after=' + after);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('canvas-action #16', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 17. clear resets _hasPriorVisual so next omitted envelope → replace ─
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'ca-17' });
      panel.init();
      panel.onBridgeUpdate(bridgeFor(cloneWithId(loadBowTie(ctx), 'ca17-1')));
      await wait(20);
      const env2 = cloneWithId(loadBowTie(ctx), 'ca17-clear');
      env2.canvas_action = 'clear';
      panel.onBridgeUpdate(bridgeFor(env2));
      await wait(20);
      const env3 = cloneWithId(loadBowTie(ctx), 'ca17-3');
      delete env3.canvas_action;
      panel.onBridgeUpdate(bridgeFor(env3));
      await wait(20);
      record('canvas-action #17: after clear, next omitted canvas_action → replace',
        panel._lastAction === 'replace',
        '_lastAction=' + panel._lastAction);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (e) {
      record('canvas-action #17', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── 18. Schema validates each of the four values + rejects an extra ────
    try {
      const compiler = win.OraVisualCompiler;
      const actions = ['replace', 'update', 'annotate', 'clear'];
      let allValid = true;
      for (const a of actions) {
        const env = cloneWithId(loadBowTie(ctx), 'ca18-' + a);
        env.canvas_action = a;
        const r = compiler.validate(env);
        if (!r.valid) allValid = false;
      }
      record('canvas-action #18: envelope validates with each legal canvas_action',
        allValid, 'actions tried=' + actions.join(','));
    } catch (e) {
      record('canvas-action #18', false, 'threw: ' + (e.stack || e.message || e));
    }
  },
};
