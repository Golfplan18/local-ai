/**
 * tests/cases/test-shape-tools.js — WP-3.1 regression suite.
 *
 * Exports { label, run(ctx, record) } per the run.js case-file convention.
 *
 * Coverage (structural — jsdom can't simulate real Konva pointer drags,
 * so we call the public testing methods directly where a drag would be
 * required):
 *
 *   - Toolbar markup exists with every WP-3.1 tool button.
 *   - Default active tool is 'select'; ARIA-pressed reflects it.
 *   - setActiveTool('rect') flips active state + ARIA.
 *   - Toolbar button clicks route through the delegated handler and the
 *     selected drawing tool can create a shape through the stage handlers.
 *   - Toolbar-selected line/text tools work through real stage events without
 *     being intercepted by empty-canvas pan.
 *   - Typing inside inline text inputs is not hijacked by fallback tool
 *     shortcuts when the shortcut registry is unavailable.
 *   - Keyboard shortcut 'R' sets rect; 'S' sets select; 'T' sets text.
 *   - Keyboard shortcut is ignored when focus is in a TEXTAREA.
 *   - _createShape('rect') appends a user-shape to userInputLayer with
 *      all required attrs (userShapeType, userShapeId, userLabel,
 *      userCluster, connEndpointStart, connEndpointEnd).
 *   - _createShape yields unique, monotonic userShapeIds.
 *   - _createShape('line') with explicit endpoints preserves connEndpoint*.
 *   - _createShape('text') with a label preserves it in userLabel.
 *   - _deleteShape removes node + drops selection; line/arrow endpoint
 *      anchors pointing at the deleted shape are nulled.
 *   - Undo after create restores shape count to prior state.
 *   - Redo after undo re-adds the shape.
 *   - Undo/redo cursor moves correctly.
 *   - Undo after delete restores the shape AND its inbound anchor refs.
 *   - History depth is capped at HISTORY_CAP (50).
 *   - clearUserInput empties userInputLayer + user annotations while
 *      preserving model annotations.
 *   - clearUserInput is undoable.
 *   - Ctrl+Z triggers undo; Ctrl+Shift+Z triggers redo.
 *   - _moveShape updates position and is undoable.
 *   - Konva.Node.toJSON() on userInputLayer round-trips the attr
 *      convention (what WP-3.2's serializer will consume).
 *   - setActiveTool to unknown name is a no-op.
 *   - OraPanels.visual.setActiveTool/undo/redo route to active instance.
 *   - deleteSelected deletes all selected shapes.
 */

'use strict';

// ── Helpers ─────────────────────────────────────────────────────────────────
function mkDiv(win) {
  var d = win.document.createElement('div');
  d.style.cssText = 'width:600px;height:400px;';
  win.document.body.appendChild(d);
  return d;
}

function countUserShapes(panel) {
  if (!panel.userInputLayer) return 0;
  return panel.userInputLayer.find('.user-shape').length;
}

function userShapesOfType(panel, type) {
  if (!panel.userInputLayer) return [];
  var nodes = panel.userInputLayer.find('.user-shape');
  var out = [];
  for (var i = 0; i < nodes.length; i++) {
    if (nodes[i].getAttr('userShapeType') === type) out.push(nodes[i]);
  }
  return out;
}

module.exports = {
  label: 'Shape and line tools (WP-3.1) — toolbar + drawing + undo/redo',
  run: async function run(ctx, record) {
    const { win } = ctx;

    if (typeof win.Konva === 'undefined' || typeof win.VisualPanel === 'undefined') {
      record('shape-tools: harness bootstrap', false,
        'Konva=' + typeof win.Konva + ' VisualPanel=' + typeof win.VisualPanel);
      return;
    }

    // ── 1. Toolbar markup ──────────────────────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-1' });
      panel.init();
      const toolbar = div.querySelector('.visual-panel__toolbar');
      const wantedTools = ['select', 'rect', 'ellipse', 'diamond', 'line',
                           'arrow', 'text', 'delete', 'undo', 'redo',
                           'clear-user-input'];
      const present = wantedTools.filter(function (t) {
        return !!toolbar.querySelector('.vp-tool-btn[data-tool="' + t + '"]');
      });
      record('shape-tools: toolbar contains every WP-3.1 tool button',
        present.length === wantedTools.length,
        present.length + '/' + wantedTools.length + ' present');
      record('shape-tools: toolbar has role="toolbar"',
        toolbar && toolbar.getAttribute('role') === 'toolbar',
        'role=' + (toolbar && toolbar.getAttribute('role')));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: toolbar markup', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 2. Default active tool is 'select' + ARIA pressed ───────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-2' });
      panel.init();
      record('shape-tools: default active tool is select',
        panel.getActiveTool() === 'select',
        'active=' + panel.getActiveTool());
      const selectBtn = div.querySelector('.vp-tool-btn[data-tool="select"]');
      record('shape-tools: select button has aria-pressed="true" by default',
        selectBtn && selectBtn.getAttribute('aria-pressed') === 'true',
        'aria-pressed=' + (selectBtn && selectBtn.getAttribute('aria-pressed')));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: default state', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 3. setActiveTool('rect') transitions state ──────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-3' });
      panel.init();
      panel.setActiveTool('rect');
      const rectBtn = div.querySelector('.vp-tool-btn[data-tool="rect"]');
      const selectBtn = div.querySelector('.vp-tool-btn[data-tool="select"]');
      record('shape-tools: setActiveTool("rect") updates _activeTool',
        panel.getActiveTool() === 'rect',
        'active=' + panel.getActiveTool());
      record('shape-tools: rect button aria-pressed flips to true',
        rectBtn.getAttribute('aria-pressed') === 'true',
        'rect aria-pressed=' + rectBtn.getAttribute('aria-pressed'));
      record('shape-tools: select button aria-pressed flips back to false',
        selectBtn.getAttribute('aria-pressed') === 'false',
        'select aria-pressed=' + selectBtn.getAttribute('aria-pressed'));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: setActiveTool', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 3b. Toolbar click delegation ───────────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-3b' });
      panel.init();
      const rectBtn = div.querySelector('.vp-tool-btn[data-tool="rect"]');
      const selectBtn = div.querySelector('.vp-tool-btn[data-tool="select"]');
      rectBtn.dispatchEvent(new win.MouseEvent('click', { bubbles: true, cancelable: true }));
      record('shape-tools: toolbar click sets active tool to rect',
        panel.getActiveTool() === 'rect',
        'active=' + panel.getActiveTool());
      let pointer = { x: 20, y: 20 };
      panel.stage.getPointerPosition = function () { return pointer; };
      panel._onStageDown({ target: panel.stage });
      pointer = { x: 90, y: 70 };
      panel._onStageMove({});
      panel._onStageUp({});
      record('shape-tools: toolbar-selected rect tool draws a shape',
        countUserShapes(panel) === 1,
        'count=' + countUserShapes(panel));
      selectBtn.dispatchEvent(new win.MouseEvent('click', { bubbles: true, cancelable: true }));
      record('shape-tools: toolbar click returns active tool to select',
        panel.getActiveTool() === 'select',
        'active=' + panel.getActiveTool());
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: toolbar click delegation', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 3c. Live stage-event path does not get swallowed by pan ─────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-3c' });
      panel.init();
      const lineBtn = div.querySelector('.vp-tool-btn[data-tool="line"]');
      const textBtn = div.querySelector('.vp-tool-btn[data-tool="text"]');
      const selectBtn = div.querySelector('.vp-tool-btn[data-tool="select"]');
      let pointer = { x: 30, y: 30 };
      panel.stage.getPointerPosition = function () { return pointer; };

      lineBtn.dispatchEvent(new win.MouseEvent('click', { bubbles: true, cancelable: true }));
      panel.stage.fire('mousedown', {
        target: panel.stage,
        evt: { preventDefault: function () {} },
      });
      const lineStartedPan = panel._panning;
      pointer = { x: 140, y: 85 };
      panel.stage.fire('mousemove', { target: panel.stage, evt: {} });
      panel.stage.fire('mouseup', { target: panel.stage, evt: {} });
      const lines = userShapesOfType(panel, 'line');
      record('shape-tools: toolbar-selected line draws via live stage events',
        !lineStartedPan && lines.length === 1,
        'panning=' + lineStartedPan + ' lines=' + lines.length);

      textBtn.dispatchEvent(new win.MouseEvent('click', { bubbles: true, cancelable: true }));
      pointer = { x: 80, y: 55 };
      panel.stage.fire('mousedown', {
        target: panel.stage,
        evt: { preventDefault: function () {} },
      });
      const textStartedPan = panel._panning;
      const input = div.querySelector('.vp-text-input');
      if (input) {
        input.value = 'Live text';
        input.dispatchEvent(new win.KeyboardEvent('keydown', {
          key: 'Enter',
          bubbles: true,
          cancelable: true,
        }));
      }
      const texts = userShapesOfType(panel, 'text');
      record('shape-tools: toolbar-selected text inserts via live stage events',
        !textStartedPan && !!input && texts.length === 1 &&
          texts[0].getAttr('userLabel') === 'Live text',
        'panning=' + textStartedPan + ' input=' + !!input + ' texts=' + texts.length);

      selectBtn.dispatchEvent(new win.MouseEvent('click', { bubbles: true, cancelable: true }));
      pointer = { x: 20, y: 20 };
      panel.stage.fire('mousedown', {
        target: panel.stage,
        evt: { preventDefault: function () {} },
      });
      const selectStartedPan = panel._panning;
      pointer = { x: 45, y: 35 };
      panel.stage.fire('mousemove', { target: panel.stage, evt: {} });
      panel.stage.fire('mouseup', { target: panel.stage, evt: {} });
      record('shape-tools: select tool still pans empty canvas',
        selectStartedPan && panel._panning === false,
        'started=' + selectStartedPan + ' ended=' + panel._panning);

      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: live stage-event drawing path', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── 3d. Inline text typing is not hijacked by fallback shortcuts ────────
    var prevShortcuts3d = win.OraKeyboardShortcuts;
    try {
      const div = mkDiv(win);
      win.OraKeyboardShortcuts = null;
      const panel = new win.VisualPanel(div, { id: 'st-3d' });
      panel.init();
      panel.setActiveTool('text');
      let pointer = { x: 65, y: 45 };
      panel.stage.getPointerPosition = function () { return pointer; };
      panel.stage.fire('mousedown', {
        target: panel.stage,
        evt: { preventDefault: function () {} },
      });
      const input = div.querySelector('.vp-text-input');
      if (input) {
        input.dispatchEvent(new win.KeyboardEvent('keydown', {
          key: 't',
          bubbles: true,
          cancelable: true,
        }));
      }
      record('shape-tools: typing t in text input does not dismiss input',
        !!input && !!div.querySelector('.vp-text-input'),
        'input=' + !!input + ' stillThere=' + !!div.querySelector('.vp-text-input'));
      if (input) {
        input.value = 'typed text';
        input.dispatchEvent(new win.KeyboardEvent('keydown', {
          key: 'Enter',
          bubbles: true,
          cancelable: true,
        }));
      }
      const texts = userShapesOfType(panel, 'text');
      record('shape-tools: text input commits after ordinary typing',
        texts.length === 1 && texts[0].getAttr('userLabel') === 'typed text',
        'texts=' + texts.length + ' label=' + (texts[0] && texts[0].getAttr('userLabel')));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: inline text typing target', false,
        'threw: ' + (err.stack || err.message || err));
    } finally {
      win.OraKeyboardShortcuts = prevShortcuts3d;
    }

    // ── 4. Keyboard shortcuts R/S/T ────────────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-4' });
      panel.init();
      const fire = function (k) {
        div.dispatchEvent(new win.KeyboardEvent('keydown', { key: k, bubbles: true }));
      };
      fire('R');
      record('shape-tools: R shortcut sets active tool to rect',
        panel.getActiveTool() === 'rect', 'active=' + panel.getActiveTool());
      fire('t');
      record('shape-tools: t shortcut sets active tool to text',
        panel.getActiveTool() === 'text', 'active=' + panel.getActiveTool());
      fire('S');
      record('shape-tools: S shortcut returns to select',
        panel.getActiveTool() === 'select', 'active=' + panel.getActiveTool());
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: keyboard shortcuts', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 5. Shortcut ignored when focus is in a TEXTAREA ────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-5' });
      panel.init();
      // Install a textarea inside the panel and fire a KeyboardEvent at it.
      const ta = win.document.createElement('textarea');
      div.appendChild(ta);
      // Dispatch directly on the textarea — it bubbles up to the panel root.
      ta.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'R', bubbles: true }));
      record('shape-tools: R shortcut ignored when target is a TEXTAREA',
        panel.getActiveTool() === 'select', 'active=' + panel.getActiveTool());
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: shortcut suppressed in text input', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 6. _createShape('rect') with full attr convention ──────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-6' });
      panel.init();
      const node = panel._createShape('rect', { x: 10, y: 20, width: 80, height: 50 });
      record('shape-tools: _createShape("rect") returns a Konva node',
        node && typeof node.getAttr === 'function',
        'node type=' + (node && node.getClassName && node.getClassName()));
      record('shape-tools: shape has Konva name "user-shape"',
        node.name() === 'user-shape', 'name=' + node.name());
      record('shape-tools: userShapeType="rect" set',
        node.getAttr('userShapeType') === 'rect',
        'type=' + node.getAttr('userShapeType'));
      const id = node.getAttr('userShapeId');
      record('shape-tools: userShapeId is a non-empty string matching u-<type>-<n>',
        typeof id === 'string' && /^u-rect-\d+$/.test(id),
        'id=' + id);
      record('shape-tools: userLabel defaults to empty string',
        node.getAttr('userLabel') === '',
        'label=' + JSON.stringify(node.getAttr('userLabel')));
      record('shape-tools: userCluster defaults to null',
        node.getAttr('userCluster') === null,
        'cluster=' + JSON.stringify(node.getAttr('userCluster')));
      record('shape-tools: connEndpointStart defaults to null on rect',
        node.getAttr('connEndpointStart') === null,
        'start=' + JSON.stringify(node.getAttr('connEndpointStart')));
      record('shape-tools: connEndpointEnd defaults to null on rect',
        node.getAttr('connEndpointEnd') === null,
        'end=' + JSON.stringify(node.getAttr('connEndpointEnd')));
      record('shape-tools: userInputLayer has exactly 1 user-shape after create',
        countUserShapes(panel) === 1,
        'count=' + countUserShapes(panel));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: _createShape attr convention', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 7. Monotonic unique ids ─────────────────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-7' });
      panel.init();
      const ids = [];
      for (var i = 0; i < 5; i++) {
        ids.push(panel._createShape('rect', { x: 0, y: 0, width: 30, height: 30 }).getAttr('userShapeId'));
      }
      const unique = new Set(ids).size === ids.length;
      record('shape-tools: 5 consecutive _createShape calls yield unique ids',
        unique && ids.length === 5,
        'ids=' + ids.join(','));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: unique ids', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 8. line with explicit connEndpoint anchors ─────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-8' });
      panel.init();
      const r1 = panel._createShape('rect', { x: 0, y: 0, width: 40, height: 40 });
      const r2 = panel._createShape('rect', { x: 100, y: 0, width: 40, height: 40 });
      const line = panel._createShape('line', {
        points: [20, 20, 120, 20],
        connEndpointStart: r1.getAttr('userShapeId'),
        connEndpointEnd:   r2.getAttr('userShapeId'),
      });
      record('shape-tools: line connEndpointStart preserved',
        line.getAttr('connEndpointStart') === r1.getAttr('userShapeId'),
        'start=' + line.getAttr('connEndpointStart'));
      record('shape-tools: line connEndpointEnd preserved',
        line.getAttr('connEndpointEnd') === r2.getAttr('userShapeId'),
        'end=' + line.getAttr('connEndpointEnd'));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: line endpoints', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 9. Text tool: userLabel preserved ──────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-9' });
      panel.init();
      const t = panel._createShape('text', { x: 50, y: 50, text: 'Hello World' });
      record('shape-tools: text shape userLabel equals typed content',
        t.getAttr('userLabel') === 'Hello World',
        'label=' + t.getAttr('userLabel'));
      record('shape-tools: text shape userShapeType="text"',
        t.getAttr('userShapeType') === 'text',
        'type=' + t.getAttr('userShapeType'));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: text tool', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 10. _deleteShape nulls inbound anchor refs ─────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-10' });
      panel.init();
      const r = panel._createShape('rect', { x: 0, y: 0, width: 40, height: 40 });
      const rid = r.getAttr('userShapeId');
      const arrow = panel._createShape('arrow', {
        points: [20, 20, 100, 20],
        connEndpointStart: rid,
        connEndpointEnd: null,
      });
      panel._deleteShape(rid);
      record('shape-tools: _deleteShape removes the shape',
        countUserShapes(panel) === 1, // arrow remains
        'count=' + countUserShapes(panel));
      record('shape-tools: inbound connEndpointStart nulled after target delete',
        arrow.getAttr('connEndpointStart') === null,
        'start=' + JSON.stringify(arrow.getAttr('connEndpointStart')));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: delete nulls anchors', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 11–13. Undo / redo after create ────────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-11' });
      panel.init();
      panel._createShape('rect', { x: 0, y: 0, width: 30, height: 30 });
      panel._createShape('ellipse', { x: 50, y: 50, radiusX: 20, radiusY: 15 });
      const afterCreate = countUserShapes(panel);
      const cursorAfter = panel.getHistoryCursor();
      panel.undo();
      const afterUndo = countUserShapes(panel);
      record('shape-tools: undo after create removes one shape',
        afterCreate === 2 && afterUndo === 1,
        'create=' + afterCreate + ' undo=' + afterUndo);
      record('shape-tools: history cursor decremented after undo',
        panel.getHistoryCursor() === cursorAfter - 1,
        'cursor=' + panel.getHistoryCursor() + ' expected=' + (cursorAfter - 1));
      panel.redo();
      const afterRedo = countUserShapes(panel);
      record('shape-tools: redo after undo restores shape count',
        afterRedo === 2,
        'redo=' + afterRedo);
      record('shape-tools: cursor advances to tip after redo',
        panel.getHistoryCursor() === cursorAfter,
        'cursor=' + panel.getHistoryCursor() + ' expected=' + cursorAfter);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: undo/redo create', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 14. Undo of delete restores anchor refs ────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-14' });
      panel.init();
      const r = panel._createShape('rect', { x: 0, y: 0, width: 40, height: 40 });
      const rid = r.getAttr('userShapeId');
      const arrow = panel._createShape('arrow', {
        points: [0, 0, 100, 0],
        connEndpointStart: rid,
      });
      panel._deleteShape(rid);
      record('shape-tools: pre-undo, arrow connEndpointStart is null',
        arrow.getAttr('connEndpointStart') === null,
        'start=' + JSON.stringify(arrow.getAttr('connEndpointStart')));
      panel.undo(); // undoes the delete
      record('shape-tools: undo of delete restores shape count',
        countUserShapes(panel) === 2,
        'count=' + countUserShapes(panel));
      // Arrow's anchor ref should be restored.
      const arrowAfter = panel.userInputLayer.find('.user-shape').filter(function (n) {
        return n.getAttr('userShapeType') === 'arrow';
      })[0];
      record('shape-tools: undo of delete restores inbound anchor ref',
        arrowAfter && arrowAfter.getAttr('connEndpointStart') === rid,
        'start=' + JSON.stringify(arrowAfter && arrowAfter.getAttr('connEndpointStart')));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: undo delete restores anchors', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 15. History depth cap ──────────────────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-15' });
      panel.init();
      for (var i = 0; i < 60; i++) {
        panel._createShape('rect', { x: i, y: i, width: 30, height: 30 });
      }
      record('shape-tools: history length capped at 50 after 60 creates',
        panel.getHistoryLength() === 50,
        'length=' + panel.getHistoryLength());
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: history cap', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 16–17. clearUserInput ──────────────────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-16' });
      panel.init();
      // Seed a model annotation so we can verify clearUserInput removes only
      // user-authored annotations from annotationLayer.
      panel.annotationLayer.add(new win.Konva.Rect({
        x: 1, y: 1, width: 2, height: 2,
        annotationSource: 'model',
        name: 'annot-seed',
      }));
      panel._createUserAnnotation('callout', {
        text: 'clear me',
        targetId: null,
        position: { x: 20, y: 20 },
      });
      panel._createShape('rect', { x: 0, y: 0, width: 30, height: 30 });
      panel._createShape('ellipse', { x: 50, y: 50, radiusX: 20, radiusY: 20 });
      const userBefore = countUserShapes(panel);
      const annotBefore = panel.annotationLayer.getChildren().length;
      const userAnnotBefore = panel.getUserAnnotations().length;
      panel.clearUserInput();
      const userAfter = countUserShapes(panel);
      const annotAfter = panel.annotationLayer.getChildren().length;
      const userAnnotAfter = panel.getUserAnnotations().length;
      record('shape-tools: clearUserInput empties userInputLayer',
        userBefore === 2 && userAfter === 0,
        'user before=' + userBefore + ' after=' + userAfter);
      record('shape-tools: clearUserInput removes user annotations only',
        annotBefore === 2 && userAnnotBefore === 1 &&
          annotAfter === 1 && userAnnotAfter === 0,
        'annot before=' + annotBefore + ' userAnnotBefore=' + userAnnotBefore +
          ' annot after=' + annotAfter + ' userAnnotAfter=' + userAnnotAfter);
      panel.undo();
      record('shape-tools: clearUserInput is undoable',
        countUserShapes(panel) === 2 && panel.getUserAnnotations().length === 1,
        'after undo shapes=' + countUserShapes(panel) +
          ' annotations=' + panel.getUserAnnotations().length);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: clearUserInput', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 18. Ctrl+Z / Ctrl+Shift+Z ──────────────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-18' });
      panel.init();
      panel._createShape('rect', { x: 0, y: 0, width: 30, height: 30 });
      div.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'z', ctrlKey: true, bubbles: true }));
      record('shape-tools: Ctrl+Z triggers undo',
        countUserShapes(panel) === 0,
        'count after undo=' + countUserShapes(panel));
      div.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'Z', ctrlKey: true, shiftKey: true, bubbles: true }));
      record('shape-tools: Ctrl+Shift+Z triggers redo',
        countUserShapes(panel) === 1,
        'count after redo=' + countUserShapes(panel));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: Ctrl+Z shortcuts', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 19. _moveShape ──────────────────────────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-19' });
      panel.init();
      const r = panel._createShape('rect', { x: 10, y: 20, width: 30, height: 30 });
      const id = r.getAttr('userShapeId');
      panel._moveShape(id, 5, 7);
      record('shape-tools: _moveShape updates x+y',
        r.x() === 15 && r.y() === 27,
        'pos=(' + r.x() + ',' + r.y() + ')');
      panel.undo();
      record('shape-tools: _moveShape undo restores original position',
        r.x() === 10 && r.y() === 20,
        'pos=(' + r.x() + ',' + r.y() + ')');
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: _moveShape', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 20. toJSON round-trips attr convention ─────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-20' });
      panel.init();
      panel._createShape('rect', { x: 0, y: 0, width: 40, height: 40 });
      const json = panel.userInputLayer.toJSON();
      // toJSON yields a JSON string — parse and inspect children[].attrs.
      const parsed = JSON.parse(json);
      const child = parsed.children && parsed.children[0];
      const attrs = child && child.attrs;
      record('shape-tools: toJSON child has userShapeType',
        attrs && attrs.userShapeType === 'rect',
        'type=' + (attrs && attrs.userShapeType));
      record('shape-tools: toJSON child has userShapeId',
        attrs && typeof attrs.userShapeId === 'string' && attrs.userShapeId.length > 0,
        'id=' + (attrs && attrs.userShapeId));
      record('shape-tools: toJSON child has name=user-shape',
        attrs && attrs.name === 'user-shape',
        'name=' + (attrs && attrs.name));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: toJSON round-trip', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 21. setActiveTool unknown name is a no-op ──────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-21' });
      panel.init();
      panel.setActiveTool('rect');
      panel.setActiveTool('not-a-tool');
      record('shape-tools: setActiveTool("not-a-tool") is a no-op',
        panel.getActiveTool() === 'rect',
        'active=' + panel.getActiveTool());
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: setActiveTool unknown', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 22. OraPanels.visual surface routing ───────────────────────────────
    try {
      const div = mkDiv(win);
      win.OraPanels.visual.init(div, { id: 'st-22' });
      win.OraPanels.visual.setActiveTool('ellipse');
      record('shape-tools: OraPanels.visual.setActiveTool routes',
        win.OraPanels.visual.getActiveTool() === 'ellipse',
        'active=' + win.OraPanels.visual.getActiveTool());
      const active = win.OraPanels.visual._getActive();
      active._createShape('rect', { x: 0, y: 0, width: 30, height: 30 });
      win.OraPanels.visual.undo();
      record('shape-tools: OraPanels.visual.undo routes',
        countUserShapes(active) === 0,
        'count=' + countUserShapes(active));
      win.OraPanels.visual.redo();
      record('shape-tools: OraPanels.visual.redo routes',
        countUserShapes(active) === 1,
        'count=' + countUserShapes(active));
      win.OraPanels.visual.clearUserInput();
      record('shape-tools: OraPanels.visual.clearUserInput routes',
        countUserShapes(active) === 0,
        'count=' + countUserShapes(active));
      win.OraPanels.visual.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: OraPanels.visual surface', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 23. deleteSelected deletes every selected shape ────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'st-23' });
      panel.init();
      const a = panel._createShape('rect',    { x: 0, y: 0,   width: 30, height: 30 });
      const b = panel._createShape('ellipse', { x: 50, y: 0,  radiusX: 20, radiusY: 20 });
      const c = panel._createShape('diamond', { points: [0, 0, 20, 20, 0, 40, -20, 20] });
      panel._selectedShapeIds = [a.getAttr('userShapeId'), b.getAttr('userShapeId')];
      panel.deleteSelected();
      record('shape-tools: deleteSelected removes all selected shapes',
        countUserShapes(panel) === 1,
        'count=' + countUserShapes(panel));
      record('shape-tools: deleteSelected clears selection state',
        panel.getSelectedShapeIds().length === 0,
        'selected=' + panel.getSelectedShapeIds().length);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('shape-tools: deleteSelected', false, 'threw: ' + (err.stack || err.message || err));
    }
  },
};
