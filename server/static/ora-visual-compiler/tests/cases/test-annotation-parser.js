/**
 * tests/cases/test-annotation-parser.js — WP-5.2 regression suite.
 *
 * Exports { label, run(ctx, record) } per the run.js case-file convention.
 *
 * annotation-parser.js translates the output of VisualPanel.getUserAnnotations()
 * (WP-5.1) into a structured instruction JSON the pipeline consumes per
 * Implementation Spec §5.1.
 *
 * Coverage:
 *   1.  parse([]) returns {annotations: []}.
 *   2.  parse(null) / parse(undefined) / parse({}) returns {annotations: []}.
 *   3.  callout with targetId → action="expand".
 *   4.  callout with null target → action="note".
 *   5.  highlight with targetId → action="expand".
 *   6.  highlight with null target → action="note" + warning.
 *   7.  strikethrough on edge target_id → action="remove".
 *   8.  strikethrough on node target_id → action="remove".
 *   9.  strikethrough with null target → action="note" + warning.
 *   10. sticky → action="add_element".
 *   11. pen → action="suggest_cluster".
 *   12. Unknown kind is silently dropped.
 *   13. Multiple annotations preserve input order.
 *   14. Output carries annotation_id, kind, action, target_id, text, position, points.
 *   15. position {x,y} normalizes to [x, y].
 *   16. position [x, y] preserved.
 *   17. points [{x,y},...] normalized to [[x,y],...].
 *   18. points flat [x1,y1,x2,y2,...] normalized.
 *   19. captureFromPanel() returns {annotations:[]} for a panel with no user annotations.
 *   20. captureFromPanel() with null panel returns empty.
 *   21. captureFromPanel() routes through getUserAnnotations().
 *   22. Missing text field → text defaults to "".
 *   23. Malformed entry (non-object) is dropped.
 *   24. _mapAction exposed for direct table testing.
 *   25. KNOWN_KINDS enumerates the 5 kinds.
 */

'use strict';

function mkDiv(win) {
  var d = win.document.createElement('div');
  d.style.cssText = 'width:600px;height:400px;';
  win.document.body.appendChild(d);
  return d;
}

module.exports = {
  label: 'Annotation parser (WP-5.2) — user annotations → structured instructions',
  run: async function run(ctx, record) {
    const { win } = ctx;

    if (typeof win.OraAnnotationParser === 'undefined') {
      record('annotation-parser: module loaded', false,
        'window.OraAnnotationParser not defined');
      return;
    }
    const P = win.OraAnnotationParser;

    // ── 1. Empty array ──────────────────────────────────────────────────────
    try {
      var out = P.parse([]);
      record('annotation-parser: parse([]) returns {annotations:[]}',
        out && Array.isArray(out.annotations) && out.annotations.length === 0,
        'out=' + JSON.stringify(out));
    } catch (e) {
      record('annotation-parser: parse([])', false, 'threw: ' + e.message);
    }

    // ── 2. Bad inputs ───────────────────────────────────────────────────────
    try {
      var n1 = P.parse(null);
      var n2 = P.parse(undefined);
      var n3 = P.parse({});
      record('annotation-parser: parse(null)→empty',
        Array.isArray(n1.annotations) && n1.annotations.length === 0, '');
      record('annotation-parser: parse(undefined)→empty',
        Array.isArray(n2.annotations) && n2.annotations.length === 0, '');
      record('annotation-parser: parse({})→empty',
        Array.isArray(n3.annotations) && n3.annotations.length === 0, '');
    } catch (e) {
      record('annotation-parser: bad inputs', false, 'threw: ' + e.message);
    }

    // ── 3. callout with targetId → expand ───────────────────────────────────
    try {
      var out = P.parse([{
        id: 'ua-callout-1', kind: 'callout', targetId: 'node-3',
        text: 'why bottleneck?', position: null, points: null,
      }]);
      record('annotation-parser: callout+target → action=expand',
        out.annotations[0].action === 'expand',
        'action=' + out.annotations[0].action);
      record('annotation-parser: callout preserves target_id',
        out.annotations[0].target_id === 'node-3',
        'target=' + out.annotations[0].target_id);
    } catch (e) {
      record('annotation-parser: callout+target', false, 'threw: ' + e.message);
    }

    // ── 4. callout without target → note ────────────────────────────────────
    try {
      var out = P.parse([{
        id: 'ua-callout-2', kind: 'callout', targetId: null,
        text: 'big picture thought', position: [10, 20], points: null,
      }]);
      record('annotation-parser: callout+null-target → action=note',
        out.annotations[0].action === 'note',
        'action=' + out.annotations[0].action);
    } catch (e) {
      record('annotation-parser: callout+null', false, 'threw: ' + e.message);
    }

    // ── 5. highlight with targetId → expand ─────────────────────────────────
    try {
      var out = P.parse([{
        id: 'ua-hi-1', kind: 'highlight', targetId: 'node-5',
        text: '', position: null, points: null,
      }]);
      record('annotation-parser: highlight+target → action=expand',
        out.annotations[0].action === 'expand',
        'action=' + out.annotations[0].action);
    } catch (e) {
      record('annotation-parser: highlight+target', false, 'threw: ' + e.message);
    }

    // ── 6. highlight without target → note + warning ────────────────────────
    try {
      var out = P.parse([{
        id: 'ua-hi-2', kind: 'highlight', targetId: null,
        text: '', position: null, points: null,
      }]);
      var a = out.annotations[0];
      record('annotation-parser: highlight+null → action=note',
        a.action === 'note', 'action=' + a.action);
      record('annotation-parser: highlight+null carries warning',
        typeof a.warning === 'string' && a.warning.length > 0,
        'warning=' + a.warning);
    } catch (e) {
      record('annotation-parser: highlight+null', false, 'threw: ' + e.message);
    }

    // ── 7/8. strikethrough on edge / node → remove ─────────────────────────
    try {
      var outE = P.parse([{
        id: 'ua-x-1', kind: 'strikethrough', targetId: 'edge-4-5',
        text: 'wrong', position: null, points: null,
      }]);
      var outN = P.parse([{
        id: 'ua-x-2', kind: 'strikethrough', targetId: 'node-7',
        text: '', position: null, points: null,
      }]);
      record('annotation-parser: strikethrough on edge → action=remove',
        outE.annotations[0].action === 'remove',
        'action=' + outE.annotations[0].action);
      record('annotation-parser: strikethrough on node → action=remove',
        outN.annotations[0].action === 'remove',
        'action=' + outN.annotations[0].action);
    } catch (e) {
      record('annotation-parser: strikethrough', false, 'threw: ' + e.message);
    }

    // ── 9. strikethrough without target → note + warning ────────────────────
    try {
      var out = P.parse([{
        id: 'ua-x-3', kind: 'strikethrough', targetId: null,
        text: '', position: [50, 50], points: null,
      }]);
      var a = out.annotations[0];
      record('annotation-parser: strikethrough+null → action=note',
        a.action === 'note', 'action=' + a.action);
      record('annotation-parser: strikethrough+null carries warning',
        typeof a.warning === 'string' && a.warning.length > 0, 'warning=' + a.warning);
    } catch (e) {
      record('annotation-parser: strikethrough+null', false, 'threw: ' + e.message);
    }

    // ── 10. sticky → add_element ────────────────────────────────────────────
    try {
      var out = P.parse([{
        id: 'ua-sticky-1', kind: 'sticky', targetId: null,
        text: 'market volatility', position: [100, 100], points: null,
      }]);
      record('annotation-parser: sticky → action=add_element',
        out.annotations[0].action === 'add_element',
        'action=' + out.annotations[0].action);
    } catch (e) {
      record('annotation-parser: sticky', false, 'threw: ' + e.message);
    }

    // ── 11. pen → suggest_cluster ───────────────────────────────────────────
    try {
      var out = P.parse([{
        id: 'ua-pen-1', kind: 'pen', targetId: null,
        text: null, position: null,
        points: [[10, 10], [20, 15], [25, 25], [15, 30]],
      }]);
      record('annotation-parser: pen → action=suggest_cluster',
        out.annotations[0].action === 'suggest_cluster',
        'action=' + out.annotations[0].action);
    } catch (e) {
      record('annotation-parser: pen', false, 'threw: ' + e.message);
    }

    // ── 12. Unknown kind dropped ────────────────────────────────────────────
    try {
      var out = P.parse([
        { id: 'ua-bogus-1', kind: 'underline', targetId: 'x' },
        { id: 'ua-sticky-1', kind: 'sticky', targetId: null, text: 'ok' },
      ]);
      record('annotation-parser: unknown kind dropped, known kept',
        out.annotations.length === 1 && out.annotations[0].kind === 'sticky',
        'count=' + out.annotations.length);
    } catch (e) {
      record('annotation-parser: unknown kind', false, 'threw: ' + e.message);
    }

    // ── 13. Order preserved ─────────────────────────────────────────────────
    try {
      var out = P.parse([
        { id: 'ua-a', kind: 'callout',       targetId: 'n1' },
        { id: 'ua-b', kind: 'sticky',        targetId: null, text: 's' },
        { id: 'ua-c', kind: 'pen',           targetId: null, points: [[1,1]] },
        { id: 'ua-d', kind: 'strikethrough', targetId: 'e1' },
      ]);
      var ids = out.annotations.map(function (x) { return x.annotation_id; });
      record('annotation-parser: order preserves input index',
        ids.join(',') === 'ua-a,ua-b,ua-c,ua-d', 'ids=' + ids.join(','));
    } catch (e) {
      record('annotation-parser: order', false, 'threw: ' + e.message);
    }

    // ── 14. Shape of output record ──────────────────────────────────────────
    try {
      var out = P.parse([{
        id: 'ua-q-1', kind: 'callout', targetId: 'node-99',
        text: 'detail', position: { x: 1, y: 2 }, points: null,
      }]);
      var a = out.annotations[0];
      var hasAll = 'annotation_id' in a && 'kind' in a && 'action' in a
                && 'target_id' in a && 'text' in a && 'position' in a && 'points' in a;
      record('annotation-parser: output carries all required fields',
        hasAll, 'keys=' + Object.keys(a).join(','));
    } catch (e) {
      record('annotation-parser: shape', false, 'threw: ' + e.message);
    }

    // ── 15. position {x,y} → [x,y] ─────────────────────────────────────────
    try {
      var out = P.parse([{
        id: 'ua-p-1', kind: 'callout', targetId: null,
        text: 't', position: { x: 7, y: 11 }, points: null,
      }]);
      record('annotation-parser: position {x,y} normalized to [x,y]',
        Array.isArray(out.annotations[0].position)
          && out.annotations[0].position[0] === 7
          && out.annotations[0].position[1] === 11,
        'pos=' + JSON.stringify(out.annotations[0].position));
    } catch (e) {
      record('annotation-parser: position {x,y}', false, 'threw: ' + e.message);
    }

    // ── 16. position [x,y] preserved ───────────────────────────────────────
    try {
      var out = P.parse([{
        id: 'ua-p-2', kind: 'sticky', targetId: null,
        text: 't', position: [42, 99], points: null,
      }]);
      record('annotation-parser: position [x,y] preserved',
        out.annotations[0].position[0] === 42
          && out.annotations[0].position[1] === 99,
        'pos=' + JSON.stringify(out.annotations[0].position));
    } catch (e) {
      record('annotation-parser: position [x,y]', false, 'threw: ' + e.message);
    }

    // ── 17. points [{x,y},...] → [[x,y],...] ───────────────────────────────
    try {
      var out = P.parse([{
        id: 'ua-pen-obj', kind: 'pen', targetId: null, text: null,
        points: [{ x: 1, y: 2 }, { x: 3, y: 4 }],
      }]);
      var pts = out.annotations[0].points;
      record('annotation-parser: points [{x,y}] → [[x,y]]',
        Array.isArray(pts) && pts[0][0] === 1 && pts[0][1] === 2
          && pts[1][0] === 3 && pts[1][1] === 4,
        'pts=' + JSON.stringify(pts));
    } catch (e) {
      record('annotation-parser: points obj', false, 'threw: ' + e.message);
    }

    // ── 18. points flat → [[x,y],...] ──────────────────────────────────────
    try {
      var out = P.parse([{
        id: 'ua-pen-flat', kind: 'pen', targetId: null, text: null,
        points: [10, 20, 30, 40, 50, 60],
      }]);
      var pts = out.annotations[0].points;
      record('annotation-parser: points flat form normalized',
        Array.isArray(pts) && pts.length === 3
          && pts[0][0] === 10 && pts[0][1] === 20
          && pts[2][0] === 50 && pts[2][1] === 60,
        'pts=' + JSON.stringify(pts));
    } catch (e) {
      record('annotation-parser: points flat', false, 'threw: ' + e.message);
    }

    // ── 19. captureFromPanel() on empty panel ───────────────────────────────
    try {
      if (typeof win.VisualPanel === 'undefined') {
        record('annotation-parser: captureFromPanel empty', false,
          'VisualPanel undefined');
      } else {
        var div = mkDiv(win);
        var panel = new win.VisualPanel(div, { id: 'ap-19' });
        panel.init();
        var out = P.captureFromPanel(panel);
        record('annotation-parser: captureFromPanel() empty panel → {annotations:[]}',
          Array.isArray(out.annotations) && out.annotations.length === 0,
          'out=' + JSON.stringify(out));
        panel.destroy();
        win.document.body.removeChild(div);
      }
    } catch (e) {
      record('annotation-parser: captureFromPanel empty', false, 'threw: ' + e.message);
    }

    // ── 20. captureFromPanel(null) returns empty ───────────────────────────
    try {
      var out = P.captureFromPanel(null);
      record('annotation-parser: captureFromPanel(null) → empty',
        Array.isArray(out.annotations) && out.annotations.length === 0,
        'out=' + JSON.stringify(out));
    } catch (e) {
      record('annotation-parser: captureFromPanel(null)', false, 'threw: ' + e.message);
    }

    // ── 21. captureFromPanel routes through getUserAnnotations ─────────────
    try {
      var fakePanel = {
        getUserAnnotations: function () {
          return [
            { id: 'ua-call-x', kind: 'callout', targetId: 'n-99', text: 'go' },
            { id: 'ua-stk-x', kind: 'sticky', targetId: null, text: 'new' },
          ];
        },
      };
      var out = P.captureFromPanel(fakePanel);
      record('annotation-parser: captureFromPanel() routes via getUserAnnotations',
        out.annotations.length === 2
          && out.annotations[0].action === 'expand'
          && out.annotations[1].action === 'add_element',
        'out=' + JSON.stringify(out.annotations));
    } catch (e) {
      record('annotation-parser: captureFromPanel routes', false, 'threw: ' + e.message);
    }

    // ── 22. Missing text → "" default ───────────────────────────────────────
    try {
      var out = P.parse([{
        id: 'ua-nt', kind: 'callout', targetId: 'n-1',
      }]);
      record('annotation-parser: missing text → "" default',
        out.annotations[0].text === '',
        'text=' + JSON.stringify(out.annotations[0].text));
    } catch (e) {
      record('annotation-parser: missing text', false, 'threw: ' + e.message);
    }

    // ── 23. Non-object entry dropped ───────────────────────────────────────
    try {
      var out = P.parse([null, 42, 'string', { id: 'ua-x', kind: 'sticky', text: 'ok' }]);
      record('annotation-parser: non-object entries dropped',
        out.annotations.length === 1 && out.annotations[0].kind === 'sticky',
        'count=' + out.annotations.length);
    } catch (e) {
      record('annotation-parser: non-object dropped', false, 'threw: ' + e.message);
    }

    // ── 24. _mapAction exposed ─────────────────────────────────────────────
    try {
      record('annotation-parser: _mapAction("callout", "n-1") → expand',
        P._mapAction('callout', 'n-1') === 'expand', '');
      record('annotation-parser: _mapAction("callout", null) → note',
        P._mapAction('callout', null) === 'note', '');
      record('annotation-parser: _mapAction("sticky", null) → add_element',
        P._mapAction('sticky', null) === 'add_element', '');
      record('annotation-parser: _mapAction("pen", null) → suggest_cluster',
        P._mapAction('pen', null) === 'suggest_cluster', '');
      record('annotation-parser: _mapAction("strikethrough", "e-1") → remove',
        P._mapAction('strikethrough', 'e-1') === 'remove', '');
    } catch (e) {
      record('annotation-parser: _mapAction', false, 'threw: ' + e.message);
    }

    // ── 25. KNOWN_KINDS ────────────────────────────────────────────────────
    try {
      var k = P.KNOWN_KINDS;
      record('annotation-parser: KNOWN_KINDS lists the 5 kinds',
        k.callout && k.highlight && k.strikethrough && k.sticky && k.pen,
        'keys=' + Object.keys(k).join(','));
    } catch (e) {
      record('annotation-parser: KNOWN_KINDS', false, 'threw: ' + e.message);
    }
  },
};
