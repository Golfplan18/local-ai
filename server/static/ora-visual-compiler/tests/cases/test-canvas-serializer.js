/**
 * tests/cases/test-canvas-serializer.js — WP-3.2 regression suite.
 *
 * Exports { label, run(ctx, record) } per the run.js case-file convention.
 *
 * Coverage of the canvas → spatial_representation serializer
 * (canvas-serializer.js):
 *
 *   1.  Namespace exists on window.OraCanvasSerializer.
 *   2.  Empty userInputLayer → null (per "Empty-layer behavior").
 *   3.  Three rects + two arrows → 3 entities + 2 relationships.
 *   4.  Anchored line emits a relationship.
 *   5.  Unanchored line → warning, no relationship.
 *   6.  Arrow defaults to 'causal'.
 *   7.  Plain line defaults to 'associative'.
 *   8.  Text shape → entity with text content as label.
 *   9.  Position normalization: rect centre at pixel (100,200) on 500×400 → [0.2,0.5]
 *       (rect is 0×0 centred at (100,200) for a clean assertion).
 *  10.  Enclosure cluster (Method 1): outer rect + 3 inner rects → 1 cluster
 *       with 3 members, outer removed from entities.
 *  11.  Proximity cluster (Method 2): two proximity-groups of 2 rects each
 *       (no enclosures) → 2 clusters.
 *  12.  Emitted spatial_rep validates against the authoritative schema
 *       (Ajv if bootstrapped; structural otherwise).
 *  13.  Unique-id assertion: two shapes sharing userShapeId → serialize throws.
 *  14.  Missing userShapeId → serialize throws.
 *  15.  Unknown userShapeType silently skipped (no crash).
 *  16.  No-label shape falls back to "(unlabeled)" placeholder.
 *  17.  Edge referencing unknown entity id → warning, no relationship.
 *  18.  serialize result has NO hierarchy field (deferred).
 *  19.  detectClusters exposed and returns [] for empty input.
 *  20.  validate({entities: []}) returns {valid:false} with a required-field
 *       style error (schema mandates minItems=1).
 *  21.  captureFromPanel reads panel.userInputLayer and serializes it.
 *  22.  Relationship `strength` propagates when userStrength is set on shape.
 *  23.  captureFromPanel: no selection → snapshot has no _activeSelection
 *       (WP-7.1.5 image-ref auto-fill source).
 *  24.  captureFromPanel: shape selection → snapshot._activeSelection is the
 *       shape id.
 *  25.  captureFromPanel: attached background image → snapshot._activeSelection
 *       is the synthetic 'canvas-image' sentinel even when no shapes are drawn.
 *  26.  captureFromPanel: image priority — when both an image and a shape are
 *       selected/present, the image wins.
 *  27.  captureFromPanel: empty canvas with no selection still returns null
 *       (no spurious envelope).
 */

'use strict';

// ── Mock shape helpers ──────────────────────────────────────────────────────
// We hand-roll plain JS mocks rather than spinning up Konva for each test.
// The serializer duck-types the layer/node API (see canvas-serializer.js
// _getAttrs / _children / _bbox). This keeps the suite fast and keeps the
// assertions tightly focused on serializer behavior, not Konva internals.

function mkRect(attrs) {
  // A duck-typed "Konva.Rect" for canvas-serializer: exposes attrs +
  // getClientRect (axis-aligned, no rotation). attrs.{x,y,width,height}
  // are the geometry; the serializer reads {name, userShapeType,
  // userShapeId, userLabel} plus optional endpoint attrs.
  var a = Object.assign({
    name: 'user-shape',
    userShapeType: 'rect',
    userLabel: '',
  }, attrs || {});
  return {
    attrs: a,
    getClientRect: function () {
      return { x: a.x, y: a.y, width: a.width, height: a.height };
    },
  };
}

function mkEllipse(attrs) {
  var a = Object.assign({
    name: 'user-shape',
    userShapeType: 'ellipse',
    userLabel: '',
  }, attrs || {});
  return {
    attrs: a,
    getClientRect: function () {
      var rx = typeof a.radiusX === 'number' ? a.radiusX : 0;
      var ry = typeof a.radiusY === 'number' ? a.radiusY : 0;
      return { x: a.x - rx, y: a.y - ry, width: rx * 2, height: ry * 2 };
    },
  };
}

function mkText(attrs) {
  var a = Object.assign({
    name: 'user-shape',
    userShapeType: 'text',
    userLabel: '',
    text: '',
  }, attrs || {});
  return {
    attrs: a,
    getClientRect: function () { return { x: a.x, y: a.y, width: 0, height: 0 }; },
  };
}

function mkEdge(shapeType, attrs) {
  var a = Object.assign({
    name: 'user-shape',
    userShapeType: shapeType,
    userLabel: '',
    connEndpointStart: null,
    connEndpointEnd: null,
    x: 0, y: 0,
  }, attrs || {});
  return {
    attrs: a,
    // Edges don't need a meaningful bbox for clustering; return a degenerate.
    getClientRect: function () { return { x: a.x, y: a.y, width: 0, height: 0 }; },
  };
}

/**
 * Build a duck-typed "userInputLayer" with a given set of children and a
 * fixed stage size. The serializer reads _canvasDims as a mock override.
 */
function mkLayer(children, width, height) {
  return {
    _canvasDims: { width: width, height: height },
    children: children,
    getChildren: function () { return children; },
  };
}

// ── Main suite ──────────────────────────────────────────────────────────────

module.exports = {
  label: 'Canvas serializer (WP-3.2) — Konva → spatial_representation JSON',
  run: async function run(ctx, record) {
    const { win } = ctx;

    if (typeof win.OraCanvasSerializer === 'undefined') {
      record('canvas-serializer: namespace present', false, 'window.OraCanvasSerializer undefined');
      return;
    }
    const S = win.OraCanvasSerializer;

    // 1. Namespace present.
    record('canvas-serializer #1: namespace on window',
      typeof S === 'object' &&
      typeof S.serialize === 'function' &&
      typeof S.detectClusters === 'function' &&
      typeof S.validate === 'function' &&
      typeof S.captureFromPanel === 'function',
      'keys=' + Object.keys(S).join(','));

    // 2. Empty layer → null.
    try {
      const empty = mkLayer([], 500, 400);
      const r = S.serialize(empty);
      record('canvas-serializer #2: empty layer returns null', r === null, 'got=' + JSON.stringify(r));
    } catch (e) {
      record('canvas-serializer #2', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 3. Three rects + two arrows connecting them.
    try {
      const kids = [
        mkRect({ userShapeId: 'u-rect-0', userLabel: 'A', x: 50,  y: 50,  width: 40, height: 40 }),
        mkRect({ userShapeId: 'u-rect-1', userLabel: 'B', x: 250, y: 50,  width: 40, height: 40 }),
        mkRect({ userShapeId: 'u-rect-2', userLabel: 'C', x: 450, y: 50,  width: 40, height: 40 }),
        mkEdge('arrow', { userShapeId: 'u-arr-0', connEndpointStart: 'u-rect-0', connEndpointEnd: 'u-rect-1' }),
        mkEdge('arrow', { userShapeId: 'u-arr-1', connEndpointStart: 'u-rect-1', connEndpointEnd: 'u-rect-2' }),
      ];
      const r = S.serialize(mkLayer(kids, 500, 400));
      record('canvas-serializer #3: 3 rects + 2 arrows → entities/relationships',
        r && r.entities.length === 3 && r.relationships && r.relationships.length === 2,
        'got e=' + (r && r.entities.length) + ' r=' + (r && r.relationships && r.relationships.length));
    } catch (e) {
      record('canvas-serializer #3', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 4. Anchored line → relationship.
    try {
      const kids = [
        mkRect({ userShapeId: 'u-rect-0', userLabel: 'A', x: 10, y: 10, width: 10, height: 10 }),
        mkRect({ userShapeId: 'u-rect-1', userLabel: 'B', x: 60, y: 10, width: 10, height: 10 }),
        mkEdge('line', { userShapeId: 'u-line-0', connEndpointStart: 'u-rect-0', connEndpointEnd: 'u-rect-1' }),
      ];
      const r = S.serialize(mkLayer(kids, 500, 400));
      record('canvas-serializer #4: anchored line → 1 relationship',
        r && r.relationships && r.relationships.length === 1 &&
        r.relationships[0].source === 'u-rect-0' && r.relationships[0].target === 'u-rect-1',
        'rels=' + JSON.stringify(r && r.relationships));
    } catch (e) {
      record('canvas-serializer #4', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 5. Unanchored line → warning, no relationship.
    try {
      const kids = [
        mkRect({ userShapeId: 'u-rect-0', userLabel: 'A', x: 10, y: 10, width: 10, height: 10 }),
        mkEdge('line', { userShapeId: 'u-line-bad' }),  // no endpoints
      ];
      const r = S.serialize(mkLayer(kids, 500, 400));
      const warns = S.getLastWarnings();
      const hasWarn = warns.some(function (w) { return w.code === 'W_UNANCHORED_EDGE'; });
      record('canvas-serializer #5: unanchored line → warning + no relationship',
        (!r || !r.relationships || r.relationships.length === 0) && hasWarn,
        'rels=' + (r && r.relationships && r.relationships.length) + ' warns=' + warns.map(function(w){return w.code;}).join(','));
    } catch (e) {
      record('canvas-serializer #5', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 6. Arrow → 'causal'.
    try {
      const kids = [
        mkRect({ userShapeId: 'a', userLabel: 'A', x: 10, y: 10, width: 10, height: 10 }),
        mkRect({ userShapeId: 'b', userLabel: 'B', x: 60, y: 10, width: 10, height: 10 }),
        mkEdge('arrow', { userShapeId: 'e', connEndpointStart: 'a', connEndpointEnd: 'b' }),
      ];
      const r = S.serialize(mkLayer(kids, 500, 400));
      record('canvas-serializer #6: arrow → relationship.type === "causal"',
        r && r.relationships && r.relationships[0].type === 'causal',
        'type=' + (r && r.relationships && r.relationships[0].type));
    } catch (e) {
      record('canvas-serializer #6', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 7. Line → 'associative'.
    try {
      const kids = [
        mkRect({ userShapeId: 'a', userLabel: 'A', x: 10, y: 10, width: 10, height: 10 }),
        mkRect({ userShapeId: 'b', userLabel: 'B', x: 60, y: 10, width: 10, height: 10 }),
        mkEdge('line', { userShapeId: 'e', connEndpointStart: 'a', connEndpointEnd: 'b' }),
      ];
      const r = S.serialize(mkLayer(kids, 500, 400));
      record('canvas-serializer #7: line → relationship.type === "associative"',
        r && r.relationships && r.relationships[0].type === 'associative',
        'type=' + (r && r.relationships && r.relationships[0].type));
    } catch (e) {
      record('canvas-serializer #7', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 8. Text shape → label from text content.
    try {
      const kids = [
        mkText({ userShapeId: 'u-t-0', x: 10, y: 20, text: 'Hello world' }),
      ];
      const r = S.serialize(mkLayer(kids, 500, 400));
      record('canvas-serializer #8: text shape uses text content as label',
        r && r.entities.length === 1 && r.entities[0].label === 'Hello world',
        'label=' + (r && r.entities[0] && r.entities[0].label));
    } catch (e) {
      record('canvas-serializer #8', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 9. Position normalization. A 0×0 rect at (100, 200) on 500×400 should
    //    normalize to [0.2, 0.5] — centre === top-left for a zero-size rect.
    try {
      const kids = [
        mkRect({ userShapeId: 'u-pos', userLabel: 'P', x: 100, y: 200, width: 0, height: 0 }),
      ];
      const r = S.serialize(mkLayer(kids, 500, 400));
      const p = r && r.entities[0] && r.entities[0].position;
      const nearly = function (a, b) { return Math.abs(a - b) < 1e-9; };
      record('canvas-serializer #9: position normalized to [0.2, 0.5]',
        !!p && nearly(p[0], 0.2) && nearly(p[1], 0.5),
        'pos=' + JSON.stringify(p));
    } catch (e) {
      record('canvas-serializer #9', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 10. Enclosure cluster: one big rect labeled "G" with 3 small rects inside.
    try {
      const kids = [
        // Big outer labeled rect — should become the cluster boundary.
        mkRect({ userShapeId: 'u-outer', userLabel: 'Group-1', x: 50, y: 50, width: 300, height: 200 }),
        // Three inner rects strictly inside the outer bbox.
        mkRect({ userShapeId: 'u-i-0', userLabel: 'a', x: 70,  y: 70,  width: 20, height: 20 }),
        mkRect({ userShapeId: 'u-i-1', userLabel: 'b', x: 150, y: 90,  width: 20, height: 20 }),
        mkRect({ userShapeId: 'u-i-2', userLabel: 'c', x: 250, y: 150, width: 20, height: 20 }),
      ];
      const r = S.serialize(mkLayer(kids, 500, 400));
      const outerInEntities = r && r.entities.some(function (e) { return e.id === 'u-outer'; });
      record('canvas-serializer #10a: enclosure cluster emitted with 3 members',
        r && r.clusters && r.clusters.length === 1 &&
        r.clusters[0].members.length === 3 &&
        r.clusters[0].label === 'Group-1',
        'clusters=' + JSON.stringify(r && r.clusters));
      record('canvas-serializer #10b: enclosure cluster removes outer rect from entities',
        !outerInEntities && r && r.entities.length === 3,
        'entities=' + (r && r.entities.map(function(e){return e.id;}).join(',')));
    } catch (e) {
      record('canvas-serializer #10', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 11. Proximity clusters: two groups of 2 rects each, far apart.
    try {
      // Two tight pairs. Canvas width 500, threshold = 15% = 75px.
      // Pair A at x≈50; Pair B at x≈450. Intra-pair distance < 75, inter-pair > 75.
      const kids = [
        mkRect({ userShapeId: 'a1', userLabel: 'a1', x: 40,  y: 40,  width: 20, height: 20 }),
        mkRect({ userShapeId: 'a2', userLabel: 'a2', x: 80,  y: 40,  width: 20, height: 20 }),
        mkRect({ userShapeId: 'b1', userLabel: 'b1', x: 420, y: 40,  width: 20, height: 20 }),
        mkRect({ userShapeId: 'b2', userLabel: 'b2', x: 460, y: 40,  width: 20, height: 20 }),
      ];
      const r = S.serialize(mkLayer(kids, 500, 400));
      record('canvas-serializer #11: proximity clusters (Method 2) → 2 clusters of 2',
        r && r.clusters && r.clusters.length === 2 &&
        r.clusters.every(function (c) { return c.members.length === 2; }),
        'clusters=' + JSON.stringify(r && r.clusters));
    } catch (e) {
      record('canvas-serializer #11', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 12. Validate emitted JSON against the schema.
    try {
      const kids = [
        mkRect({ userShapeId: 'v1', userLabel: 'V1', x: 50,  y: 50,  width: 20, height: 20 }),
        mkRect({ userShapeId: 'v2', userLabel: 'V2', x: 150, y: 50,  width: 20, height: 20 }),
        mkEdge('arrow', { userShapeId: 'v-e', connEndpointStart: 'v1', connEndpointEnd: 'v2' }),
      ];
      const r = S.serialize(mkLayer(kids, 500, 400));
      const vr = S.validate(r);
      record('canvas-serializer #12: emitted spatial_rep passes validate()',
        vr.valid === true && vr.errors.length === 0,
        'valid=' + vr.valid + ' errs=' + vr.errors.map(function(e){return e.code;}).join(','));
    } catch (e) {
      record('canvas-serializer #12', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 13. Duplicate userShapeId → throw.
    try {
      const kids = [
        mkRect({ userShapeId: 'dup', userLabel: 'A', x: 10, y: 10, width: 10, height: 10 }),
        mkRect({ userShapeId: 'dup', userLabel: 'B', x: 50, y: 10, width: 10, height: 10 }),
      ];
      let threw = false, msg = '';
      try { S.serialize(mkLayer(kids, 500, 400)); }
      catch (e) { threw = true; msg = e.message || String(e); }
      record('canvas-serializer #13: duplicate userShapeId throws',
        threw && /duplicate userShapeId/.test(msg),
        'threw=' + threw + ' msg=' + msg);
    } catch (e) {
      record('canvas-serializer #13', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 14. Missing userShapeId → throw.
    try {
      const kids = [
        mkRect({ userLabel: 'X', x: 10, y: 10, width: 10, height: 10 }),  // no id
      ];
      let threw = false, msg = '';
      try { S.serialize(mkLayer(kids, 500, 400)); }
      catch (e) { threw = true; msg = e.message || String(e); }
      record('canvas-serializer #14: missing userShapeId throws',
        threw && /missing userShapeId/.test(msg),
        'threw=' + threw + ' msg=' + msg);
    } catch (e) {
      record('canvas-serializer #14', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 15. Unknown userShapeType silently skipped.
    try {
      const kids = [
        mkRect({ userShapeId: 'ok', userLabel: 'ok', x: 10, y: 10, width: 10, height: 10 }),
        // Unknown type — should be silently ignored.
        {
          attrs: { name: 'user-shape', userShapeType: 'blob', userShapeId: 'bad', x: 5, y: 5 },
          getClientRect: function () { return { x: 5, y: 5, width: 0, height: 0 }; },
        },
      ];
      const r = S.serialize(mkLayer(kids, 500, 400));
      record('canvas-serializer #15: unknown userShapeType silently skipped',
        r && r.entities.length === 1 && r.entities[0].id === 'ok',
        'entities=' + (r && r.entities.map(function(e){return e.id;}).join(',')));
    } catch (e) {
      record('canvas-serializer #15', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 16. No-label shape falls back to "(unlabeled)".
    try {
      const kids = [
        mkRect({ userShapeId: 'nolabel', x: 10, y: 10, width: 10, height: 10 }),  // userLabel=''
      ];
      const r = S.serialize(mkLayer(kids, 500, 400));
      record('canvas-serializer #16: missing label → "(unlabeled)" placeholder',
        r && r.entities[0].label === '(unlabeled)',
        'label=' + (r && r.entities[0] && r.entities[0].label));
    } catch (e) {
      record('canvas-serializer #16', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 17. Edge with unknown endpoint id → warning, no relationship.
    try {
      const kids = [
        mkRect({ userShapeId: 'a', userLabel: 'A', x: 10, y: 10, width: 10, height: 10 }),
        mkEdge('arrow', { userShapeId: 'e-bad', connEndpointStart: 'a', connEndpointEnd: 'ghost' }),
      ];
      const r = S.serialize(mkLayer(kids, 500, 400));
      const warns = S.getLastWarnings();
      const hasWarn = warns.some(function (w) { return w.code === 'W_EDGE_ENDPOINT_UNRESOLVED'; });
      record('canvas-serializer #17: edge with unknown endpoint → warning, no relationship',
        (!r.relationships || r.relationships.length === 0) && hasWarn,
        'rels=' + (r && r.relationships && r.relationships.length) + ' warns=' + warns.map(function(w){return w.code;}).join(','));
    } catch (e) {
      record('canvas-serializer #17', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 18. No hierarchy field emitted (deferred).
    try {
      const kids = [
        mkRect({ userShapeId: 'a', userLabel: 'A', x: 10, y: 10, width: 10, height: 10 }),
      ];
      const r = S.serialize(mkLayer(kids, 500, 400));
      record('canvas-serializer #18: no hierarchy field in emitted object',
        r && !('hierarchy' in r),
        'keys=' + (r && Object.keys(r).join(',')));
    } catch (e) {
      record('canvas-serializer #18', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 19. detectClusters([], []) → [].
    try {
      const out = S.detectClusters([], []);
      record('canvas-serializer #19: detectClusters empty → []',
        Array.isArray(out) && out.length === 0, 'out=' + JSON.stringify(out));
    } catch (e) {
      record('canvas-serializer #19', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 20. validate({entities: []}) → invalid (schema minItems=1).
    try {
      const vr = S.validate({ entities: [] });
      record('canvas-serializer #20: validate empty entities → invalid',
        vr.valid === false && vr.errors.length > 0,
        'valid=' + vr.valid + ' errs=' + vr.errors.length);
    } catch (e) {
      record('canvas-serializer #20', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 21. captureFromPanel: build a minimal fake panel with userInputLayer.
    try {
      const kids = [
        mkRect({ userShapeId: 'c1', userLabel: 'C', x: 30, y: 30, width: 10, height: 10 }),
      ];
      const panel = { userInputLayer: mkLayer(kids, 500, 400) };
      const r = S.captureFromPanel(panel);
      record('canvas-serializer #21: captureFromPanel reads userInputLayer',
        r && r.entities.length === 1 && r.entities[0].id === 'c1',
        'got=' + JSON.stringify(r && r.entities));
    } catch (e) {
      record('canvas-serializer #21', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 22. Relationship `strength` propagates.
    try {
      const kids = [
        mkRect({ userShapeId: 'a', userLabel: 'A', x: 10, y: 10, width: 10, height: 10 }),
        mkRect({ userShapeId: 'b', userLabel: 'B', x: 60, y: 10, width: 10, height: 10 }),
        mkEdge('arrow', {
          userShapeId: 'e', connEndpointStart: 'a', connEndpointEnd: 'b', userStrength: 0.7,
        }),
      ];
      const r = S.serialize(mkLayer(kids, 500, 400));
      record('canvas-serializer #22: userStrength → relationship.strength',
        r && r.relationships && r.relationships[0].strength === 0.7,
        'strength=' + (r && r.relationships && r.relationships[0].strength));
    } catch (e) {
      record('canvas-serializer #22', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── _activeSelection surfacing (WP-7.1.5 image-ref auto-fill source) ──
    //
    // The Ask Ora bindings auto-fill required `image-ref` capability inputs
    // from `snapshot._activeSelection` (with a `_selectionId` fallback).
    // captureFromPanel must populate `_activeSelection` when the panel has
    // a selection — image first (most useful for AI tools), then shapes,
    // then annotations, then SVG nodes.

    // 23. No selection → no _activeSelection.
    try {
      const kids = [
        mkRect({ userShapeId: 'r1', userLabel: 'R', x: 10, y: 10, width: 10, height: 10 }),
      ];
      const panel = {
        userInputLayer: mkLayer(kids, 500, 400),
        _selectedShapeIds: [],
        _selectedAnnotIds: [],
        _selectedNodeId:   null,
        _backgroundImageNode: null,
      };
      const r = S.captureFromPanel(panel);
      record('canvas-serializer #23: no selection → no _activeSelection',
        r && r._activeSelection == null,
        'activeSelection=' + (r && JSON.stringify(r._activeSelection)));
    } catch (e) {
      record('canvas-serializer #23', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 24. Shape selection → _activeSelection carries the shape id.
    try {
      const kids = [
        mkRect({ userShapeId: 'r1', userLabel: 'R', x: 10, y: 10, width: 10, height: 10 }),
        mkRect({ userShapeId: 'r2', userLabel: 'S', x: 60, y: 10, width: 10, height: 10 }),
      ];
      const panel = {
        userInputLayer: mkLayer(kids, 500, 400),
        _selectedShapeIds: ['r2'],
        _selectedAnnotIds: [],
        _selectedNodeId:   null,
        _backgroundImageNode: null,
      };
      const r = S.captureFromPanel(panel);
      record('canvas-serializer #24: shape selected → _activeSelection is shape id',
        r && r._activeSelection === 'r2',
        'activeSelection=' + (r && JSON.stringify(r._activeSelection)));
    } catch (e) {
      record('canvas-serializer #24', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 25. Image attached, no shapes → snapshot returns 'canvas-image' sentinel
    //     even on an otherwise-empty layer (a stub envelope is synthesized so
    //     the auto-fill path can still read _activeSelection). The envelope
    //     also carries `_stubEnvelope: true` so server-bound senders can skip
    //     transmitting a synthesized spatial_representation.
    try {
      const panel = {
        userInputLayer: mkLayer([], 500, 400),
        _selectedShapeIds: [],
        _selectedAnnotIds: [],
        _selectedNodeId:   null,
        _backgroundImageNode: { name: 'vp-background-image' },  // truthy stand-in
      };
      const r = S.captureFromPanel(panel);
      record('canvas-serializer #25: attached image → _activeSelection = canvas-image',
        r && r._activeSelection === 'canvas-image' && Array.isArray(r.entities) && r.entities.length === 1
          && r._stubEnvelope === true,
        'r=' + JSON.stringify(r));
    } catch (e) {
      record('canvas-serializer #25', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 26. Image priority — image present + shape selected → image wins.
    try {
      const kids = [
        mkRect({ userShapeId: 'r1', userLabel: 'R', x: 10, y: 10, width: 10, height: 10 }),
      ];
      const panel = {
        userInputLayer: mkLayer(kids, 500, 400),
        _selectedShapeIds: ['r1'],
        _selectedAnnotIds: [],
        _selectedNodeId:   null,
        _backgroundImageNode: { name: 'vp-background-image' },
      };
      const r = S.captureFromPanel(panel);
      record('canvas-serializer #26: image present beats shape selection',
        r && r._activeSelection === 'canvas-image',
        'activeSelection=' + (r && JSON.stringify(r._activeSelection)));
    } catch (e) {
      record('canvas-serializer #26', false, 'threw: ' + (e.stack || e.message || e));
    }

    // 27. Empty canvas + no selection → null (no spurious envelope).
    try {
      const panel = {
        userInputLayer: mkLayer([], 500, 400),
        _selectedShapeIds: [],
        _selectedAnnotIds: [],
        _selectedNodeId:   null,
        _backgroundImageNode: null,
      };
      const r = S.captureFromPanel(panel);
      record('canvas-serializer #27: empty + no selection → null',
        r === null,
        'r=' + JSON.stringify(r));
    } catch (e) {
      record('canvas-serializer #27', false, 'threw: ' + (e.stack || e.message || e));
    }
  },
};
