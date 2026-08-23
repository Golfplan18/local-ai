/**
 * tests/cases/test-v3-visual-dispatch.js — V3 envelope→panel dispatch suite.
 *
 * Exports { label, run(ctx, record) } per the run.js case-file convention.
 *
 * Covers server/static/js/v3-visual-dispatch.js, the V3 replacement for the
 * retired classic-UI extraction path (the old WP-2.3 e2e suite was removed
 * with chat-panel.js on 2026-06-11):
 *   1. extractBlocks finds a single fenced envelope.
 *   2. extractBlocks finds multiple fences in order.
 *   3. Malformed-JSON fence is skipped by extractBlocks.
 *   4. Text with no fences → empty array, untouched by stripBlocks.
 *   5. stripBlocks replaces parseable fences with a neutral handoff marker.
 *   6. stripBlocks leaves malformed fences in place.
 *   7. dispatch hands {ora_visual_blocks} to OraPanels.visual.onBridgeUpdate.
 *   8. dispatch dedupes on repeated key; new key re-dispatches.
 *   9. an unsupported asynchronous result is surfaced visibly.
 *  10. dispatch with no panel registry still returns the block count.
 */

'use strict';

const fs   = require('fs');
const path = require('path');

const ENVELOPE = JSON.stringify({
  type: 'concept_map',
  title: 'Dispatch test',
  spec: { nodes: [{ id: 'a', label: 'A' }], edges: [] },
});

function fenced(json) {
  return '```ora-visual\n' + json + '\n```';
}

module.exports = {
  label: 'V3 visual dispatch (envelope extraction + panel hand-off)',

  run: async function (ctx, record) {
    const win = ctx.win;

    // Load the module under test into the jsdom window. Plain IIFE —
    // win.eval is sufficient (same pattern as test-lazy-expansion.js).
    const modPath = path.join(__dirname, '..', '..', '..', 'js', 'v3-visual-dispatch.js');
    win.eval(fs.readFileSync(modPath, 'utf-8'));

    const D = win.OraV3VisualDispatch;
    record('dispatch: module exposed on window', !!D && typeof D.dispatch === 'function');
    if (!D) return;

    // 1. Single fence
    const one = D.extractBlocks('Intro text.\n' + fenced(ENVELOPE) + '\nOutro.');
    record('extract: single fence found', one.length === 1 && one[0].envelope.type === 'concept_map',
           'count=' + one.length);

    // 2. Multiple fences, in order
    const second = JSON.stringify({ type: 'pro_con', title: 'Second', spec: { pros: [], cons: [] } });
    const two = D.extractBlocks(fenced(ENVELOPE) + '\nmiddle\n' + fenced(second));
    record('extract: two fences in order',
           two.length === 2 && two[0].envelope.type === 'concept_map' && two[1].envelope.type === 'pro_con',
           'count=' + two.length);

    // 3. Malformed JSON skipped
    const mixed = D.extractBlocks(fenced('{not json') + '\n' + fenced(ENVELOPE));
    record('extract: malformed fence skipped', mixed.length === 1 && mixed[0].envelope.type === 'concept_map',
           'count=' + mixed.length);

    // 4. No fences
    const none = D.extractBlocks('Plain prose with `inline code` and ```js\nx\n```.');
    const untouched = 'Plain text, no envelopes.';
    record('extract: no fences → empty', none.length === 0, 'count=' + none.length);
    record('strip: fence-free text untouched', D.stripBlocks(untouched) === untouched);

    // 5. Strip replaces parseable fences without claiming render success.
    const stripped = D.stripBlocks('Before.\n' + fenced(ENVELOPE) + '\nAfter.');
    record('strip: parseable fence → neutral handoff marker',
           stripped.indexOf(D.PLACEHOLDER) !== -1 && stripped.indexOf('ora-visual') === -1,
           stripped.slice(0, 80));
    record('strip: marker does not claim rendered success',
           D.PLACEHOLDER.indexOf('rendered') === -1,
           D.PLACEHOLDER);

    // 6. Strip leaves malformed fences alone
    const keptRaw = D.stripBlocks(fenced('{broken'));
    record('strip: malformed fence kept', keptRaw.indexOf('{broken') !== -1);

    // 7-8. Dispatch hand-off + dedupe. Install a counting stub registry.
    const calls = [];
    const priorRegistry = win.OraPanels;
    win.OraPanels = { visual: { onBridgeUpdate: function (state) { calls.push(state); } } };
    D.resetDedupe();

    const text = 'Reply.\n' + fenced(ENVELOPE);
    const n1 = D.dispatch(text, 'conv1#0');
    record('dispatch: hand-off fired with blocks',
           n1 === 1 && calls.length === 1 &&
           Array.isArray(calls[0].ora_visual_blocks) && calls[0].ora_visual_blocks.length === 1,
           'calls=' + calls.length);

    const n2 = D.dispatch(text, 'conv1#0');
    record('dispatch: same key deduped', n2 === 1 && calls.length === 1, 'calls=' + calls.length);

    D.dispatch(text, 'conv1#1');
    record('dispatch: new key re-dispatches', calls.length === 2, 'calls=' + calls.length);

    // 9. The controller's asynchronous unsupported result reaches an existing
    // visible UI surface instead of disappearing into the console.
    const alerts = [];
    const errorBar = [];
    const priorAlert = win.alert;
    win.alert = function (message) { alerts.push(String(message)); };
    win.OraPanels = { visual: {
      _showErrorBar: function (message) { errorBar.push(String(message)); },
      onBridgeUpdate: function () {
      return Promise.resolve([{
        action: 'annotate',
        unsupported: true,
        warnings: [
          'Excalidraw cannot apply semantic canvas annotations. '
          + 'The scene was preserved; switch to Konva to apply this annotation.'
        ],
      }]);
      },
    } };
    D.resetDedupe();
    const nUnsupported = D.dispatch(text, 'conv-annotate#0');
    await new Promise((resolve) => setTimeout(resolve, 0));
    record('dispatch: unsupported result is visible without a blocking modal',
           nUnsupported === 1 && alerts.length === 0 && errorBar.length === 1
           && errorBar[0].indexOf('Excalidraw cannot apply') !== -1
           && errorBar[0].indexOf('scene was preserved') !== -1
           && errorBar[0].indexOf('switch to Konva') !== -1,
           'alerts=' + JSON.stringify(alerts) + ' errorBar=' + JSON.stringify(errorBar));

    // 10. No registry → still counts, no throw
    win.OraPanels = undefined;
    D.resetDedupe();
    let threw = false, n3 = 0;
    try { n3 = D.dispatch(text, 'conv2#0'); } catch (e) { threw = true; }
    record('dispatch: registry absent is safe', !threw && n3 === 1, 'threw=' + threw + ' n=' + n3);

    win.OraPanels = priorRegistry;
    win.alert = priorAlert;
  },
};
