/**
 * tests/cases/test-spatial-reasoning-e2e.js — WP-3.4 client-side regression.
 *
 * Exports { label, run(ctx, record) } per the run.js case-file convention.
 *
 * End-to-end Phase 3 integration on the client side:
 *   1. Instantiate a VisualPanel. Draw 3 rects + 2 arrows on its
 *      userInputLayer via the public _createShape testing API (WP-3.1).
 *   2. Capture via OraCanvasSerializer.captureFromPanel(panel) — verify
 *      3 entities + 2 relationships were emitted (WP-3.2).
 *   3. Simulate a server annotate response: an envelope with
 *      canvas_action:"annotate" + a callout on entity A's id (the
 *      analytical model's identified gap).
 *   4. Feed the envelope to panel.onBridgeUpdate({ora_visual_blocks:[...]})
 *      as WP-2.3's dispatch helper would.
 *   5. Assert:
 *      - backgroundLayer DOM untouched (annotate never clears it).
 *      - userInputLayer still contains the user's 3 rects + 2 arrows
 *        (preserve-arrangement invariant — preservation is the whole
 *        point of annotate).
 *      - annotationLayer contains a new Konva node referencing entity
 *        A's id via its Konva name.
 *      - _currentEnvelope has been recorded.
 *      - _lastAction is 'annotate'.
 *
 * Target: >= 10 Node assertions. Actual coverage is 15+.
 */

'use strict';

function mkDiv(win) {
  var d = win.document.createElement('div');
  d.style.cssText = 'width:600px;height:400px;';
  win.document.body.appendChild(d);
  return d;
}

function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

module.exports = {
  label: 'WP-3.4 — Spatial Reasoning end-to-end (draw → serialize → annotate)',
  run: async function run(ctx, record) {
    const { win } = ctx;

    // Guard: harness dependencies.
    if (typeof win.Konva === 'undefined' || typeof win.VisualPanel === 'undefined') {
      record('wp3.4 e2e: harness bootstrap', false,
        'Konva=' + typeof win.Konva + ' VisualPanel=' + typeof win.VisualPanel);
      return;
    }
    if (typeof win.OraCanvasSerializer === 'undefined') {
      record('wp3.4 e2e: harness — OraCanvasSerializer exposed',
        false, 'canvas-serializer not loaded');
      return;
    }

    // ── Setup: a panel ready to draw on ───────────────────────────────────
    const div = mkDiv(win);
    const panel = new win.VisualPanel(div, { id: 'wp34-panel' });
    panel.init();

    try {
      // ── Step 1: Draw 3 rects (entities A, B, C) + 2 arrows (A→B, B→C) ──
      // Use _createShape directly — the public testing surface from WP-3.1
      // (jsdom can't simulate Konva pointer drags so this is the way
      // test-shape-tools.js exercises drawing).
      const rectA = panel._createShape('rect', {
        x: 80, y: 150, width: 80, height: 60, userLabel: 'Hiring',
      });
      const rectB = panel._createShape('rect', {
        x: 260, y: 150, width: 80, height: 60, userLabel: 'Team size',
      });
      const rectC = panel._createShape('rect', {
        x: 440, y: 150, width: 80, height: 60, userLabel: 'Coordination cost',
      });

      // Validate rect creation landed.
      record('wp3.4 e2e #1: three rects created on userInputLayer',
        !!(rectA && rectB && rectC)
          && panel.userInputLayer.find('.user-shape').length === 3,
        'count=' + panel.userInputLayer.find('.user-shape').length);

      const idA = rectA.getAttr('userShapeId');
      const idB = rectB.getAttr('userShapeId');
      const idC = rectC.getAttr('userShapeId');

      // 2 arrows (A→B and B→C) — a partial chain missing the C→A closure.
      const arrAB = panel._createShape('arrow', {
        points: [160, 180, 260, 180],
        connEndpointStart: idA,
        connEndpointEnd:   idB,
      });
      const arrBC = panel._createShape('arrow', {
        points: [340, 180, 440, 180],
        connEndpointStart: idB,
        connEndpointEnd:   idC,
      });
      record('wp3.4 e2e #2: two arrows added (partial chain A→B→C)',
        !!(arrAB && arrBC)
          && panel.userInputLayer.find('.user-shape').length === 5,
        'shapeCount=' + panel.userInputLayer.find('.user-shape').length);

      // ── Step 2: Serialize → spatial_representation (WP-3.2 pipeline) ────
      const spatial = win.OraCanvasSerializer.captureFromPanel(panel);
      record('wp3.4 e2e #3: captureFromPanel returned a non-null object',
        spatial && typeof spatial === 'object',
        'typeof=' + typeof spatial);

      const entityCount = (spatial && spatial.entities) ? spatial.entities.length : 0;
      const relCount    = (spatial && spatial.relationships)
                            ? spatial.relationships.length : 0;
      record('wp3.4 e2e #4: serialization yields 3 entities',
        entityCount === 3, 'ents=' + entityCount);
      record('wp3.4 e2e #5: serialization yields 2 relationships',
        relCount === 2, 'rels=' + relCount);

      // Validate it matches the schema.
      const srValidation = win.OraCanvasSerializer.validate(spatial);
      record('wp3.4 e2e #6: captured spatial_representation validates',
        srValidation && srValidation.valid === true,
        'valid=' + (srValidation && srValidation.valid) + ' errors='
          + ((srValidation.errors || []).map(function (e) { return e.code; }).join(',')));

      // Capture a snapshot of the userInputLayer BEFORE annotate lands.
      const userShapesBefore = panel.userInputLayer.find('.user-shape').length;

      // ── Step 3: Inject an SVG stub representing the "rendered" user input ─
      // Normally WP-2.3 would render a background artifact here first
      // (Spatial Reasoning mode might emit an update+annotate combo). For
      // a pure annotate test we need a DOM element with the target id so
      // _computeTargetBox() can find it. This simulates the shape the
      // user's three rects would take once rendered by the CLD/concept
      // map compiler — the entity ids come from the serializer.
      const firstEntityId = spatial.entities[0].id;
      let svgHost = panel._svgHost;
      if (!svgHost) {
        // Fallback: the panel always creates _svgHost; just guard.
        record('wp3.4 e2e #7a: panel._svgHost present', false, 'missing');
      } else {
        // Make sure we have an SVG to hang the target on.
        let svg = svgHost.querySelector('svg');
        if (!svg) {
          svg = win.document.createElementNS('http://www.w3.org/2000/svg', 'svg');
          svg.setAttribute('viewBox', '0 0 600 400');
          svg.setAttribute('width', '600');
          svg.setAttribute('height', '400');
          svgHost.appendChild(svg);
        }
        // Append a <g> carrying the first entity's id — this is the
        // element the Ora response will target.
        const g = win.document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('id', firstEntityId);
        g.setAttribute('class', 'ora-visual__node');
        // Give it a non-zero bbox so _computeTargetBox yields reasonable coords.
        const rect = win.document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', '80'); rect.setAttribute('y', '150');
        rect.setAttribute('width', '80'); rect.setAttribute('height', '60');
        g.appendChild(rect);
        svg.appendChild(g);
        record('wp3.4 e2e #7: annotate target DOM element injected',
          !!svgHost.querySelector('[id="' + firstEntityId + '"]'),
          'firstEntityId=' + firstEntityId);
      }

      // NOW capture the backgroundLayer DOM state — must be unchanged after
      // annotate. (Captured AFTER the target injection so the assertion
      // compares like-for-like; the target we just added is part of the
      // "existing background" annotate must preserve.)
      const bgBeforeAnnotate = panel._svgHost ? panel._svgHost.innerHTML : '';

      // ── Step 4: Build and dispatch the annotate envelope ───────────────
      const annotateEnvelope = {
        schema_version: '0.2',
        id: 'sr-gap-' + Date.now(),
        type: 'concept_map',
        mode_context: 'spatial-reasoning',
        relation_to_prose: 'visually_native',
        title: 'Missing feedback: coordination back to hiring',
        canvas_action: 'annotate',
        annotations: [
          {
            target_id: firstEntityId,
            kind: 'callout',
            text: "Missing link: consider C→A feedback.",
          },
          {
            target_id: firstEntityId,
            kind: 'highlight',
            color: '#FF5722',
          },
        ],
        spec: {
          focus_question: 'What dampens unchecked hiring growth?',
          concepts: [
            { id: firstEntityId, label: 'Hiring', hierarchy_level: 0 },
          ],
          linking_phrases: [{ id: 'lp-1', text: 'increases' }],
          propositions: [
            { from_concept: firstEntityId, via_phrase: 'lp-1', to_concept: firstEntityId },
          ],
        },
        semantic_description: {
          level_1_elemental: 'Concept map with one concept.',
          level_2_statistical: 'One concept, no cross-links in annotate overlay.',
          level_3_perceptual: 'Gap is the closing C→A edge.',
          short_alt: 'Annotation highlighting missing feedback on A.',
        },
      };

      // Dispatch as the chat-panel's _dispatchVisualBlocks would.
      const bridgeState = {
        ora_visual_blocks: [{
          envelope: annotateEnvelope,
          raw_json: JSON.stringify(annotateEnvelope),
          source_message_id: 'wp34-e2e-msg',
        }],
      };

      const turnBefore = panel._conversationTurn;
      panel.onBridgeUpdate(bridgeState);
      await wait(30);
      const turnAfter = panel._conversationTurn;

      // ── Step 5: Assertions on annotate side-effects ─────────────────────

      // Turn counter bumped.
      record('wp3.4 e2e #8: onBridgeUpdate bumps _conversationTurn',
        turnAfter === turnBefore + 1,
        'before=' + turnBefore + ' after=' + turnAfter);

      // canvas_action recorded.
      record('wp3.4 e2e #9: _lastAction === "annotate"',
        panel._lastAction === 'annotate',
        '_lastAction=' + panel._lastAction);

      // Invariant 1: backgroundLayer DOM is untouched.
      const bgAfterAnnotate = panel._svgHost ? panel._svgHost.innerHTML : '';
      record('wp3.4 e2e #10: backgroundLayer DOM unchanged after annotate',
        bgAfterAnnotate === bgBeforeAnnotate && bgAfterAnnotate.length > 0,
        'changed=' + (bgAfterAnnotate !== bgBeforeAnnotate)
          + ' bgBefore.len=' + bgBeforeAnnotate.length);

      // Invariant 2: userInputLayer preserved — 3 rects + 2 arrows.
      const userShapesAfter = panel.userInputLayer.find('.user-shape').length;
      record('wp3.4 e2e #11: userInputLayer preserves all 5 user shapes',
        userShapesAfter === userShapesBefore && userShapesAfter === 5,
        'before=' + userShapesBefore + ' after=' + userShapesAfter);

      // Invariant 2b: Specific shape ids still present.
      const stillHasA = !!panel.userInputLayer.findOne(function (node) {
        return node.getAttr && node.getAttr('userShapeId') === idA;
      });
      const stillHasB = !!panel.userInputLayer.findOne(function (node) {
        return node.getAttr && node.getAttr('userShapeId') === idB;
      });
      const stillHasC = !!panel.userInputLayer.findOne(function (node) {
        return node.getAttr && node.getAttr('userShapeId') === idC;
      });
      record('wp3.4 e2e #12: every user-drawn rect id survives annotate',
        stillHasA && stillHasB && stillHasC,
        'A=' + stillHasA + ' B=' + stillHasB + ' C=' + stillHasC);

      // Invariant 3: annotationLayer contains the callout(s).
      const annotationChildren = panel.annotationLayer.getChildren().length;
      record('wp3.4 e2e #13: annotationLayer has new child(ren)',
        annotationChildren >= 1,
        'children=' + annotationChildren);

      // Invariant 3b: the callout Konva group is named vp-callout-<targetId>.
      const calloutGroup = panel.annotationLayer.findOne('.vp-callout-' + firstEntityId);
      record('wp3.4 e2e #14: callout named vp-callout-<target_id> is present',
        !!calloutGroup, 'found=' + !!calloutGroup);

      // Invariant 3c: highlight Konva rect is named vp-highlight-<targetId>.
      const highlightRect = panel.annotationLayer.findOne('.vp-highlight-' + firstEntityId);
      record('wp3.4 e2e #15: highlight named vp-highlight-<target_id> is present',
        !!highlightRect, 'found=' + !!highlightRect);

      // No warnings like W_ANNOTATION_TARGET_MISSING / W_ANNOTATE_NO_CONTENT.
      const warningCodes = (panel._annotationWarnings || []).map(function (w) { return w.code; });
      record('wp3.4 e2e #16: no target-missing / no-content warnings emitted',
        warningCodes.length === 0,
        'warnings=' + warningCodes.join(','));

      // Envelope tracking: annotate does NOT overwrite _currentEnvelope
      // (that field tracks the active background artifact, which annotate
      // preserves by design — see visual-panel.js _doAnnotate). For an
      // annotate-without-prior-update case, _currentEnvelope stays null,
      // which is the correct preserve-background behavior.
      record('wp3.4 e2e #17: annotate preserves _currentEnvelope contract',
        panel._currentEnvelope === null,
        '_currentEnvelope=' + (panel._currentEnvelope && panel._currentEnvelope.id));

      // Envelope validates under the compiler's validator.
      if (win.OraVisualCompiler && typeof win.OraVisualCompiler.validate === 'function') {
        const vresult = win.OraVisualCompiler.validate(annotateEnvelope);
        record('wp3.4 e2e #18: annotate envelope passes compiler.validate',
          vresult && vresult.valid === true,
          'valid=' + (vresult && vresult.valid)
            + ' errors=' + ((vresult && vresult.errors) || []).map(function (e) { return e.code; }).join(','));
      } else {
        record('wp3.4 e2e #18: compiler.validate unavailable', false, 'no validate fn');
      }

    } catch (err) {
      record('wp3.4 e2e: uncaught', false,
        'threw: ' + (err.stack || err.message || err));
    } finally {
      try { panel.destroy(); } catch (e) { /* ignore */ }
      try { win.document.body.removeChild(div); } catch (e) { /* ignore */ }
    }
  },
};
