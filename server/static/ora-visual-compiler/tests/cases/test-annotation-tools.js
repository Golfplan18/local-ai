/**
 * tests/cases/test-annotation-tools.js — WP-5.1 regression suite.
 *
 * Exports { label, run(ctx, record) } per the run.js case-file convention.
 *
 * The user authors annotations on top of a rendered artifact via five
 * tools (callout / highlight / strikethrough / sticky / pen). All
 * annotations land on annotationLayer alongside WP-2.4's model-emitted
 * overlays, but carry `annotationSource="user"` so WP-5.2's translator
 * can filter them.
 *
 * Coverage (structural — jsdom can't drive real Konva pointer handlers
 * through the SVG overlay, so we exercise programmatic _createUserAnnotation
 * everywhere; DOM-walking resolution is tested via a synthetic SVG mount):
 *
 *   1.  Toolbar contains all 5 annotation tool buttons (callout, highlight,
 *       strikethrough, sticky, pen).
 *   2.  Default state — annotation tool aria-pressed="false"; select stays
 *       pressed.
 *   3.  setActiveTool('callout') updates active tool + ARIA.
 *   4.  Keyboard shortcuts — C, H, X, N, P each set the corresponding tool.
 *   5.  Shortcuts suppressed inside typing targets (textarea).
 *   6.  _createUserAnnotation('callout') attaches to annotationLayer with
 *       full attr convention (annotationSource='user', annotationKind,
 *       userAnnotationId, targetId, text).
 *   7.  _createUserAnnotation('highlight') with targetId populates targetId.
 *   8.  _createUserAnnotation('strikethrough') populates targetId + kind.
 *   9.  _createUserAnnotation('sticky') with text + position — targetId null.
 *   10. _createUserAnnotation('pen') with points — points array non-empty.
 *   11. Callout targeting — resolved targetId from a real SVG element id in
 *       the overlay.
 *   12. Callout on empty area — targetId is null; position set.
 *   13. Highlight on empty space → no-op + inline hint.
 *   14. Strikethrough on non-edge target → no-op + inline hint.
 *   15. Monotonic unique userAnnotationIds across all 5 kinds.
 *   16. Select mode — clicking a user annotation selects it.
 *   17. Del/Backspace deletes the selected annotation via keyboard.
 *   18. deleteSelectedAnnotations deletes every selected annotation.
 *   19. Undo of create removes the annotation.
 *   20. Redo after undo re-adds the annotation.
 *   21. Undo of delete restores the annotation.
 *   22. getUserAnnotations() shape check — matches WP-5.2 contract.
 *   23. Preservation — model-emitted annotation (WP-2.4 path) does NOT clear
 *       user annotations; the two are distinguishable via annotationSource.
 *   24. canvas_action='update' preserves user annotations.
 *   25. canvas_action='clear' removes user annotations.
 *   26. OraPanels.visual.getUserAnnotations routes to active instance.
 *   27. toJSON round-trips the attr convention (required for undo + WP-5.2
 *       consumers that serialize the annotation layer).
 *   28. setActiveTool cancels in-flight pen stroke.
 */

'use strict';

// ── Helpers ─────────────────────────────────────────────────────────────────
function mkDiv(win) {
  var d = win.document.createElement('div');
  d.style.cssText = 'width:600px;height:400px;';
  win.document.body.appendChild(d);
  return d;
}

function countUserAnnotations(panel) {
  return panel.getUserAnnotations().length;
}

function countLayerChildren(panel) {
  return panel.annotationLayer ? panel.annotationLayer.getChildren().length : 0;
}

/**
 * Install a synthetic SVG element in the panel's _svgHost so the
 * DOM-resolution logic (_resolveSvgTarget) has something to walk. The
 * jsdom shim for getBBox returns predictable dimensions, which
 * _computeTargetBox relies on for placement.
 */
function installSyntheticSvg(win, panel) {
  var ns = 'http://www.w3.org/2000/svg';
  var svg = win.document.createElementNS(ns, 'svg');
  svg.setAttribute('width', '200');
  svg.setAttribute('height', '200');
  var rect = win.document.createElementNS(ns, 'rect');
  rect.setAttribute('id', 'node-1');
  rect.setAttribute('class', 'ora-visual__node');
  rect.setAttribute('x', '10');
  rect.setAttribute('y', '20');
  rect.setAttribute('width', '60');
  rect.setAttribute('height', '30');
  svg.appendChild(rect);
  var edge = win.document.createElementNS(ns, 'line');
  edge.setAttribute('id', 'edge-1');
  edge.setAttribute('class', 'ora-visual__edge');
  edge.setAttribute('x1', '10');
  edge.setAttribute('y1', '10');
  edge.setAttribute('x2', '100');
  edge.setAttribute('y2', '100');
  svg.appendChild(edge);
  panel._svgHost.appendChild(svg);
  return { svg: svg, rect: rect, edge: edge };
}

module.exports = {
  label: 'User annotation tools (WP-5.1) — callout / highlight / strike / sticky / pen',
  run: async function run(ctx, record) {
    const { win } = ctx;

    if (typeof win.Konva === 'undefined' || typeof win.VisualPanel === 'undefined') {
      record('annotation-tools: harness bootstrap', false,
        'Konva=' + typeof win.Konva + ' VisualPanel=' + typeof win.VisualPanel);
      return;
    }

    // ── 1. Toolbar contains all 5 annotation buttons ───────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-1' });
      panel.init();
      const toolbar = div.querySelector('.visual-panel__toolbar');
      const wanted = ['callout', 'highlight', 'strikethrough', 'sticky', 'pen'];
      const present = wanted.filter(function (t) {
        return !!toolbar.querySelector('.vp-tool-btn[data-tool="' + t + '"]');
      });
      record('annotation-tools: toolbar contains all 5 annotation tool buttons',
        present.length === 5, present.length + '/5 present');
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: toolbar buttons', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 2. Default state — annotation buttons aria-pressed="false" ─────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-2' });
      panel.init();
      const kinds = ['callout', 'highlight', 'strikethrough', 'sticky', 'pen'];
      let allFalse = true;
      for (const k of kinds) {
        const btn = div.querySelector('.vp-tool-btn[data-tool="' + k + '"]');
        if (!btn || btn.getAttribute('aria-pressed') !== 'false') {
          allFalse = false; break;
        }
      }
      record('annotation-tools: annotation buttons default aria-pressed="false"',
        allFalse, 'all-false=' + allFalse);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: default state', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 3. setActiveTool('callout') transitions state + ARIA ──────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-3' });
      panel.init();
      panel.setActiveTool('callout');
      const calloutBtn = div.querySelector('.vp-tool-btn[data-tool="callout"]');
      const selectBtn = div.querySelector('.vp-tool-btn[data-tool="select"]');
      record('annotation-tools: setActiveTool("callout") updates _activeTool',
        panel.getActiveTool() === 'callout', 'active=' + panel.getActiveTool());
      record('annotation-tools: callout button aria-pressed=true after set',
        calloutBtn.getAttribute('aria-pressed') === 'true',
        'aria-pressed=' + calloutBtn.getAttribute('aria-pressed'));
      record('annotation-tools: select button aria-pressed=false after set',
        selectBtn.getAttribute('aria-pressed') === 'false',
        'select aria-pressed=' + selectBtn.getAttribute('aria-pressed'));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: setActiveTool', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 4. Keyboard shortcuts C/H/X/N/P ────────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-4' });
      panel.init();
      const fire = function (k) {
        div.dispatchEvent(new win.KeyboardEvent('keydown', { key: k, bubbles: true }));
      };
      fire('C');
      record('annotation-tools: C shortcut → callout', panel.getActiveTool() === 'callout',
        'active=' + panel.getActiveTool());
      fire('H');
      record('annotation-tools: H shortcut → highlight', panel.getActiveTool() === 'highlight',
        'active=' + panel.getActiveTool());
      fire('X');
      record('annotation-tools: X shortcut → strikethrough',
        panel.getActiveTool() === 'strikethrough', 'active=' + panel.getActiveTool());
      fire('n');
      record('annotation-tools: n shortcut → sticky', panel.getActiveTool() === 'sticky',
        'active=' + panel.getActiveTool());
      fire('p');
      record('annotation-tools: p shortcut → pen', panel.getActiveTool() === 'pen',
        'active=' + panel.getActiveTool());
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: keyboard shortcuts', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 5. Shortcut ignored when focus is in a TEXTAREA ────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-5' });
      panel.init();
      const ta = win.document.createElement('textarea');
      div.appendChild(ta);
      ta.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'C', bubbles: true }));
      record('annotation-tools: C shortcut ignored when target is a TEXTAREA',
        panel.getActiveTool() === 'select', 'active=' + panel.getActiveTool());
      ta.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'N', bubbles: true }));
      record('annotation-tools: N shortcut ignored when target is a TEXTAREA',
        panel.getActiveTool() === 'select', 'active=' + panel.getActiveTool());
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: shortcut suppressed', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 6. _createUserAnnotation('callout') attr convention ────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-6' });
      panel.init();
      const node = panel._createUserAnnotation('callout', {
        text: 'hi', targetId: null, position: { x: 30, y: 40 },
      });
      record('annotation-tools: _createUserAnnotation("callout") returns a Konva node',
        node && typeof node.getAttr === 'function',
        'class=' + (node && node.getClassName && node.getClassName()));
      record('annotation-tools: callout annotationSource="user"',
        node.getAttr('annotationSource') === 'user',
        'source=' + node.getAttr('annotationSource'));
      record('annotation-tools: callout annotationKind="callout"',
        node.getAttr('annotationKind') === 'callout',
        'kind=' + node.getAttr('annotationKind'));
      const uaid = node.getAttr('userAnnotationId');
      record('annotation-tools: callout userAnnotationId matches ua-<kind>-<n>',
        typeof uaid === 'string' && /^ua-callout-\d+$/.test(uaid), 'id=' + uaid);
      record('annotation-tools: callout text preserved',
        node.getAttr('text') === 'hi', 'text=' + node.getAttr('text'));
      record('annotation-tools: callout targetId=null for free point',
        node.getAttr('targetId') === null,
        'targetId=' + JSON.stringify(node.getAttr('targetId')));
      record('annotation-tools: annotationLayer has 1 user annotation after create',
        countUserAnnotations(panel) === 1, 'count=' + countUserAnnotations(panel));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: callout attrs', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 7. highlight with targetId ─────────────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-7' });
      panel.init();
      installSyntheticSvg(win, panel);
      const node = panel._createUserAnnotation('highlight', { targetId: 'node-1' });
      record('annotation-tools: highlight annotationKind="highlight"',
        node.getAttr('annotationKind') === 'highlight',
        'kind=' + node.getAttr('annotationKind'));
      record('annotation-tools: highlight targetId="node-1"',
        node.getAttr('targetId') === 'node-1',
        'targetId=' + node.getAttr('targetId'));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: highlight attrs', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 8. strikethrough with targetId ─────────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-8' });
      panel.init();
      installSyntheticSvg(win, panel);
      const node = panel._createUserAnnotation('strikethrough', { targetId: 'edge-1' });
      record('annotation-tools: strikethrough annotationKind="strikethrough"',
        node.getAttr('annotationKind') === 'strikethrough',
        'kind=' + node.getAttr('annotationKind'));
      record('annotation-tools: strikethrough targetId="edge-1"',
        node.getAttr('targetId') === 'edge-1',
        'targetId=' + node.getAttr('targetId'));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: strikethrough attrs', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 9. sticky with text + position, targetId null ──────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-9' });
      panel.init();
      const node = panel._createUserAnnotation('sticky', {
        text: 'remember this', position: { x: 100, y: 80 },
      });
      record('annotation-tools: sticky annotationKind="sticky"',
        node.getAttr('annotationKind') === 'sticky',
        'kind=' + node.getAttr('annotationKind'));
      record('annotation-tools: sticky text preserved',
        node.getAttr('text') === 'remember this', 'text=' + node.getAttr('text'));
      record('annotation-tools: sticky targetId=null (free-floating)',
        node.getAttr('targetId') === null,
        'targetId=' + JSON.stringify(node.getAttr('targetId')));
      const pos = node.getAttr('position') || {};
      record('annotation-tools: sticky position set',
        pos.x === 100 && pos.y === 80,
        'position=(' + pos.x + ',' + pos.y + ')');
      record('annotation-tools: sticky is draggable',
        node.draggable && node.draggable() === true,
        'draggable=' + (node.draggable && node.draggable()));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: sticky attrs', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 10. pen with points ────────────────────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-10' });
      panel.init();
      const pts = [10, 10, 20, 25, 30, 22, 45, 30];
      const node = panel._createUserAnnotation('pen', { points: pts });
      record('annotation-tools: pen annotationKind="pen"',
        node.getAttr('annotationKind') === 'pen',
        'kind=' + node.getAttr('annotationKind'));
      const savedPts = node.getAttr('points') || [];
      record('annotation-tools: pen points array non-empty',
        Array.isArray(savedPts) && savedPts.length === pts.length,
        'length=' + savedPts.length);
      record('annotation-tools: pen targetId=null',
        node.getAttr('targetId') === null,
        'targetId=' + JSON.stringify(node.getAttr('targetId')));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: pen attrs', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 11. Callout targeting a real SVG element (DOM walk) ────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-11' });
      panel.init();
      const env = installSyntheticSvg(win, panel);
      // Directly exercise the resolver on the rect element. Fabricate a
      // minimal Konva event with evt.target pointing at the SVG rect.
      const resolved = panel._resolveSvgTarget({
        evt: { target: env.rect, clientX: 25, clientY: 30 },
      });
      record('annotation-tools: _resolveSvgTarget walks to element id',
        resolved && resolved.id === 'node-1',
        'id=' + (resolved && resolved.id));
      record('annotation-tools: _resolveSvgTarget detects element kind',
        resolved && resolved.kind === 'element',
        'kind=' + (resolved && resolved.kind));
      // Edge target
      const resolvedEdge = panel._resolveSvgTarget({
        evt: { target: env.edge, clientX: 50, clientY: 50 },
      });
      record('annotation-tools: _resolveSvgTarget detects edge kind',
        resolvedEdge && resolvedEdge.kind === 'edge',
        'kind=' + (resolvedEdge && resolvedEdge.kind));
      record('annotation-tools: _resolveSvgTarget returns edge id',
        resolvedEdge && resolvedEdge.id === 'edge-1',
        'id=' + (resolvedEdge && resolvedEdge.id));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: DOM walk target resolution', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 12. Callout on empty area — targetId null + position set ───────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-12' });
      panel.init();
      // No SVG installed, or click at a point not over any ora-visual__ elem.
      const node = panel._createUserAnnotation('callout', {
        text: 'free', targetId: null, position: { x: 200, y: 150 },
      });
      record('annotation-tools: callout free-point targetId=null',
        node.getAttr('targetId') === null,
        'targetId=' + JSON.stringify(node.getAttr('targetId')));
      const pos = node.getAttr('position') || {};
      record('annotation-tools: callout free-point position set',
        pos.x === 200 && pos.y === 150,
        'position=(' + pos.x + ',' + pos.y + ')');
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: callout free-point', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 13. Highlight on empty space → inline hint + no-op ─────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-13' });
      panel.init();
      panel.setActiveTool('highlight');
      const before = countUserAnnotations(panel);
      // Simulate a stage mousedown at a point over no SVG element.
      panel._onHighlightDown({ evt: { clientX: 5, clientY: 5, target: null } });
      const after = countUserAnnotations(panel);
      record('annotation-tools: highlight on empty space is a no-op',
        before === 0 && after === 0, 'before=' + before + ' after=' + after);
      const hint = div.querySelector('.visual-panel__annotation-hint');
      record('annotation-tools: highlight empty-space shows inline hint',
        hint && !hint.hidden && /Highlight targets/i.test(hint.textContent),
        'hint=' + (hint && hint.textContent));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: highlight empty hint', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 14. Strikethrough on non-edge target → inline hint + no-op ─────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-14' });
      panel.init();
      const env = installSyntheticSvg(win, panel);
      panel.setActiveTool('strikethrough');
      const before = countUserAnnotations(panel);
      // Fire with a non-edge target (the rect — kind='element' not 'edge').
      panel._onStrikethroughDown({
        evt: { target: env.rect, clientX: 30, clientY: 40 },
      });
      const after = countUserAnnotations(panel);
      record('annotation-tools: strikethrough on non-edge is a no-op',
        before === 0 && after === 0, 'before=' + before + ' after=' + after);
      const hint = div.querySelector('.visual-panel__annotation-hint');
      record('annotation-tools: strikethrough non-edge shows inline hint',
        hint && !hint.hidden && /Strikethrough targets/i.test(hint.textContent),
        'hint=' + (hint && hint.textContent));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: strikethrough non-edge hint', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 15. Monotonic unique userAnnotationIds across kinds ────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-15' });
      panel.init();
      const a = panel._createUserAnnotation('callout', { text: 'a', targetId: null, position: { x: 0, y: 0 } });
      const b = panel._createUserAnnotation('sticky',  { text: 'b', position: { x: 1, y: 1 } });
      const c = panel._createUserAnnotation('pen',     { points: [0, 0, 10, 10] });
      const ids = [a.getAttr('userAnnotationId'), b.getAttr('userAnnotationId'),
                   c.getAttr('userAnnotationId')];
      const unique = new Set(ids).size === 3;
      record('annotation-tools: userAnnotationIds are unique across kinds',
        unique, 'ids=' + ids.join(','));
      record('annotation-tools: all ids match ua-<kind>-<n>',
        ids.every(function (id) { return /^ua-(callout|sticky|pen)-\d+$/.test(id); }),
        'ids=' + ids.join(','));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: unique ids', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 16. Select mode — clicking a user annotation selects it ───────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-16' });
      panel.init();
      const n = panel._createUserAnnotation('sticky', {
        text: 'x', position: { x: 50, y: 50 },
      });
      panel.setActiveTool('select');
      // Fake the Konva "select down" on the sticky node directly. _onSelectDown
      // walks parents looking for annotationSource='user'.
      panel._onSelectDown({ target: n, evt: {} });
      record('annotation-tools: clicking user annotation in select mode selects it',
        panel.getSelectedAnnotationIds().length === 1 &&
        panel.getSelectedAnnotationIds()[0] === n.getAttr('userAnnotationId'),
        'selected=' + panel.getSelectedAnnotationIds().join(','));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: select annotation', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 17. Del/Backspace deletes the selected annotation via keyboard ─────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-17' });
      panel.init();
      const n = panel._createUserAnnotation('callout', {
        text: 'gone soon', targetId: null, position: { x: 20, y: 20 },
      });
      panel._selectedAnnotIds = [n.getAttr('userAnnotationId')];
      div.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'Delete', bubbles: true }));
      record('annotation-tools: Delete key removes selected annotation',
        countUserAnnotations(panel) === 0,
        'count after delete=' + countUserAnnotations(panel));
      // Undo should bring it back.
      panel.undo();
      record('annotation-tools: undo of keyboard-delete restores annotation',
        countUserAnnotations(panel) === 1,
        'count after undo=' + countUserAnnotations(panel));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: keyboard delete', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 18. deleteSelectedAnnotations clears multi-select ──────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-18' });
      panel.init();
      const a = panel._createUserAnnotation('callout', { text: 'a', targetId: null, position: { x: 0, y: 0 } });
      const b = panel._createUserAnnotation('sticky',  { text: 'b', position: { x: 20, y: 20 } });
      const c = panel._createUserAnnotation('pen',     { points: [0, 0, 10, 10] });
      panel._selectedAnnotIds = [a.getAttr('userAnnotationId'), b.getAttr('userAnnotationId')];
      panel.deleteSelectedAnnotations();
      record('annotation-tools: deleteSelectedAnnotations removes all selected',
        countUserAnnotations(panel) === 1,
        'count=' + countUserAnnotations(panel));
      record('annotation-tools: deleteSelectedAnnotations clears selection',
        panel.getSelectedAnnotationIds().length === 0,
        'selected=' + panel.getSelectedAnnotationIds().length);
      // Remaining annotation is the pen — not selected. Use the out to assert.
      const remaining = panel.getUserAnnotations();
      record('annotation-tools: correct annotation survives multi-delete',
        remaining.length === 1 && remaining[0].kind === 'pen',
        'remaining=' + JSON.stringify(remaining.map(function (r) { return r.kind; })));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: multi-delete', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 19-20. Undo / redo of create ──────────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-19' });
      panel.init();
      panel._createUserAnnotation('callout', { text: 'u', targetId: null, position: { x: 5, y: 5 } });
      panel._createUserAnnotation('pen',     { points: [0, 0, 20, 20] });
      const afterCreate = countUserAnnotations(panel);
      panel.undo();
      const afterUndo = countUserAnnotations(panel);
      record('annotation-tools: undo of create removes one annotation',
        afterCreate === 2 && afterUndo === 1,
        'create=' + afterCreate + ' undo=' + afterUndo);
      panel.redo();
      const afterRedo = countUserAnnotations(panel);
      record('annotation-tools: redo of create re-adds annotation',
        afterRedo === 2, 'redo=' + afterRedo);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: undo/redo create', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 21. Undo of delete restores the annotation ─────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-21' });
      panel.init();
      const n = panel._createUserAnnotation('sticky', {
        text: 'survive', position: { x: 80, y: 80 },
      });
      const id = n.getAttr('userAnnotationId');
      panel._deleteAnnotation(id);
      record('annotation-tools: _deleteAnnotation removes node',
        countUserAnnotations(panel) === 0, 'count=' + countUserAnnotations(panel));
      panel.undo();
      record('annotation-tools: undo of delete restores annotation',
        countUserAnnotations(panel) === 1, 'count=' + countUserAnnotations(panel));
      // Verify the restored annotation carries the same id + text.
      const after = panel.getUserAnnotations()[0];
      record('annotation-tools: restored annotation preserves id + text',
        after && after.id === id && after.text === 'survive',
        'id=' + (after && after.id) + ' text=' + (after && after.text));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: undo delete', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 22. getUserAnnotations() shape check (WP-5.2 contract) ─────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-22' });
      panel.init();
      panel._createUserAnnotation('callout', { text: 'c', targetId: 'anchor-a', position: { x: 10, y: 10 } });
      panel._createUserAnnotation('sticky',  { text: 's', position: { x: 40, y: 50 } });
      panel._createUserAnnotation('pen',     { points: [0, 0, 5, 5, 10, 10] });
      const list = panel.getUserAnnotations();
      record('annotation-tools: getUserAnnotations returns array',
        Array.isArray(list) && list.length === 3,
        'len=' + (list && list.length));
      const keys = ['id', 'kind', 'targetId', 'text', 'position', 'points'];
      const allHaveKeys = list.every(function (r) {
        return keys.every(function (k) { return Object.prototype.hasOwnProperty.call(r, k); });
      });
      record('annotation-tools: every record exposes id/kind/targetId/text/position/points',
        allHaveKeys, 'first keys=' + Object.keys(list[0] || {}).join(','));
      const callout = list.find(function (r) { return r.kind === 'callout'; });
      record('annotation-tools: callout record preserves targetId',
        callout && callout.targetId === 'anchor-a',
        'targetId=' + (callout && callout.targetId));
      const pen = list.find(function (r) { return r.kind === 'pen'; });
      record('annotation-tools: pen record exposes non-empty points array',
        pen && Array.isArray(pen.points) && pen.points.length === 6,
        'points=' + (pen && pen.points && pen.points.length));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: getUserAnnotations shape', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 23. Preservation — model annotations coexist with user annotations ─
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-23' });
      panel.init();
      installSyntheticSvg(win, panel);
      // User creates two annotations.
      panel._createUserAnnotation('sticky', { text: 'user', position: { x: 0, y: 0 } });
      panel._createUserAnnotation('callout', { text: 'mine', targetId: null, position: { x: 10, y: 10 } });
      // Ora (model) emits an annotate envelope — WP-2.4's _doAnnotate path.
      panel._applyCanvasAction({
        canvas_action: 'annotate',
        annotations: [{ kind: 'highlight', target_id: 'node-1' }],
      }, 'annotate');
      // User annotations still present?
      const userList = panel.getUserAnnotations();
      record('annotation-tools: model-emitted annotation preserves user annotations',
        userList.length === 2, 'user count=' + userList.length);
      // Model annotation is NOT in the user list.
      record('annotation-tools: model annotation absent from getUserAnnotations',
        userList.every(function (r) { return r.kind !== 'highlight'; }),
        'kinds=' + userList.map(function (r) { return r.kind; }).join(','));
      // Layer total > user count (model annotation landed).
      record('annotation-tools: annotationLayer has both user and model nodes',
        countLayerChildren(panel) > userList.length,
        'layer=' + countLayerChildren(panel) + ' user=' + userList.length);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: preservation invariant', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 24. canvas_action='update' preserves user annotations ──────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-24' });
      panel.init();
      panel._createUserAnnotation('sticky', { text: 'a', position: { x: 0, y: 0 } });
      panel._createUserAnnotation('pen',    { points: [0, 0, 8, 8] });
      const before = countUserAnnotations(panel);
      // _doUpdatePrep is the guts of canvas_action='update' — it wipes
      // backgroundLayer + selectionLayer but MUST preserve annotationLayer.
      panel._doUpdatePrep();
      const after = countUserAnnotations(panel);
      record('annotation-tools: _doUpdatePrep preserves user annotations',
        before === 2 && after === 2, 'before=' + before + ' after=' + after);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: update preservation', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 25. canvas_action='clear' removes user annotations ─────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-25' });
      panel.init();
      panel._createUserAnnotation('callout', { text: 'bye', targetId: null, position: { x: 0, y: 0 } });
      const before = countUserAnnotations(panel);
      panel._doClear();
      const after = countUserAnnotations(panel);
      record('annotation-tools: _doClear removes user annotations',
        before === 1 && after === 0, 'before=' + before + ' after=' + after);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: clear wipes user annotations', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 26. OraPanels.visual routing ───────────────────────────────────────
    try {
      const div = mkDiv(win);
      win.OraPanels.visual.init(div, { id: 'at-26' });
      const active = win.OraPanels.visual._getActive();
      active._createUserAnnotation('sticky', { text: 'routed', position: { x: 0, y: 0 } });
      const list = win.OraPanels.visual.getUserAnnotations();
      record('annotation-tools: OraPanels.visual.getUserAnnotations routes',
        Array.isArray(list) && list.length === 1 && list[0].kind === 'sticky',
        'list=' + JSON.stringify(list.map(function (r) { return r.kind; })));
      // deleteSelectedAnnotations routing.
      active._selectedAnnotIds = [list[0].id];
      win.OraPanels.visual.deleteSelectedAnnotations();
      const after = win.OraPanels.visual.getUserAnnotations();
      record('annotation-tools: OraPanels.visual.deleteSelectedAnnotations routes',
        after.length === 0, 'after=' + after.length);
      win.OraPanels.visual.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: OraPanels.visual surface', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 27. toJSON round-trips annotation attr convention ──────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-27' });
      panel.init();
      panel._createUserAnnotation('pen', { points: [0, 0, 10, 10, 20, 20] });
      const json = panel.annotationLayer.toJSON();
      const parsed = JSON.parse(json);
      const child = parsed.children && parsed.children[0];
      const attrs = child && child.attrs;
      record('annotation-tools: toJSON child has annotationSource="user"',
        attrs && attrs.annotationSource === 'user',
        'source=' + (attrs && attrs.annotationSource));
      record('annotation-tools: toJSON child has annotationKind',
        attrs && attrs.annotationKind === 'pen',
        'kind=' + (attrs && attrs.annotationKind));
      record('annotation-tools: toJSON child has userAnnotationId',
        attrs && typeof attrs.userAnnotationId === 'string' &&
        attrs.userAnnotationId.length > 0,
        'id=' + (attrs && attrs.userAnnotationId));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: toJSON round-trip', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 28. setActiveTool cancels in-flight pen stroke ─────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'at-28' });
      panel.init();
      panel.setActiveTool('pen');
      // Mimic the beginning of a pen stroke by directly invoking the down
      // handler with a synthetic stage point. (Fully simulating Konva's
      // pointer system in jsdom is infeasible; the programmatic hook is
      // sufficient to verify cancellation wiring.)
      panel._penContext = {
        line: new win.Konva.Line({ points: [0, 0, 10, 10], name: 'vp-pen-preview' }),
      };
      panel.annotationLayer.add(panel._penContext.line);
      panel.setActiveTool('select');
      record('annotation-tools: setActiveTool cancels in-flight pen stroke',
        panel._penContext === null, 'penContext=' + panel._penContext);
      // The preview line should have been destroyed; no user annotation
      // should have been created.
      record('annotation-tools: cancelled pen stroke creates no user annotation',
        countUserAnnotations(panel) === 0, 'count=' + countUserAnnotations(panel));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('annotation-tools: pen cancel', false, 'threw: ' + (err.stack || err.message || err));
    }
  },
};
