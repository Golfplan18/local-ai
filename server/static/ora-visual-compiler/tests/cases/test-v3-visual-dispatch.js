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
 *  10. Mermaid HTML-label retries run once per raw fence, preserve source
 *      order and siblings, stay single-flight across navigation, and close
 *      cold-reload orphans.
 *  11. dispatch with no panel registry still returns the block count.
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

function confirmedOutcomeResponse(options, canonicalOverride) {
  const requested = JSON.parse(options.body);
  delete requested.assistant_index;
  return {
    ok: true,
    status: 200,
    json: function () { return Promise.resolve({
      ok: true,
      visual_outcome: canonicalOverride || requested,
    }); },
  };
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
    record('extract: malformed fence skipped but advances raw fence index',
           mixed.length === 1
             && mixed[0].envelope.type === 'concept_map'
             && mixed[0].raw_fence_index === 1,
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
      showError: function (message) { errorBar.push(String(message)); },
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

    // 10. Mermaid's foreignObject labels participate in the viewport check.
    // Two unreadable siblings each receive their own one narrowing attempt,
    // keyed to raw fence indexes 1 and 2 around a malformed fence at index 0.
    // Fence 1's authoritative synthesis failure is superseded on disk when
    // fence 2 saves and inserts a narrower replacement, so the assistant-wide
    // failure must be saved once instead of treating fence 1 as terminal disk
    // truth.
    const priorNarrowFetch = win.fetch;
    const narrowPanelCalls = [];
    const narrowRequests = [];
    const narrowOutcomes = [];
    const confirmedOutcomesBeforeTerminal = [];
    let latestConfirmedStoredOutcome = null;
    const secondEnvelope = JSON.stringify({
      type: 'pro_con',
      title: 'Unreadable second visual',
      spec: { pros: [{ text: 'One' }], cons: [{ text: 'Two' }] },
    });
    const narrowedEnvelope = {
      type: 'pro_con',
      title: 'Narrowed second visual',
      spec: { pros: [{ text: 'One load-bearing subject' }], cons: [] },
    };
    const firstSiblingFailureOutcome = {
      state: 'failed',
      stage: 'legibility',
      reason: 'The first visual could not be narrowed.',
      legibility_attempts: { 1: 'exhausted' },
    };
    const secondSiblingSavedOutcome = {
      state: 'failed',
      stage: 'legibility',
      reason: 'A narrower visual was saved, but insertion has not been confirmed.',
      legibility_attempts: { 1: 'exhausted', 2: 'exhausted' },
    };
    const malformedFence = fenced('{not json');
    const multiVisualText = 'Lead prose.\n' + malformedFence
      + '\nMalformed fence stays visible.\n' + fenced(ENVELOPE)
      + '\nMiddle prose.\n' + fenced(secondEnvelope) + '\nTail prose.';
    let narrowedCachedText = multiVisualText;
    const narrowedCachedIndexes = [];
    let reloadedNarrowedCachedText = multiVisualText;
    const reloadedNarrowedCachedIndexes = [];
    const resolvedNarrowResponses = {};
    const legibilityFinding = D.reviewLegibility({
      svg: '<svg viewBox="0 0 1000 1000">'
        + '<foreignObject width="300" height="100">'
        + '<div xmlns="http://www.w3.org/1999/xhtml" style="font-size:12px">'
        + 'Mermaid HTML label</div></foreignObject></svg>',
      errors: [], warnings: [],
    }, { clientWidth: 300, clientHeight: 200 });
    const narrowPanel = {
      showError: function (message) { errorBar.push(String(message)); },
      onBridgeUpdate: function (state) {
        narrowPanelCalls.push(state);
        if (String(state.ora_visual_dispatch_key || '').indexOf(':narrowed:') === -1) {
          return Promise.resolve([{
            needs_narrower_subject: true,
            legibility_finding: legibilityFinding,
          }]);
        }
        return Promise.resolve([{ svg: '<svg/>', errors: [], warnings: [] }]);
      },
    };
    win.OraPanels = { visual: narrowPanel };
    win.fetch = function (url, options) {
      if (String(url) === '/api/visual/regenerate') {
        const request = JSON.parse(options.body);
        narrowRequests.push(request);
        const isFirstSibling = request.visual_block_index === 1;
        return new Promise(function (resolve) {
          resolvedNarrowResponses[request.visual_block_index] = function () {
            latestConfirmedStoredOutcome = isFirstSibling
              ? firstSiblingFailureOutcome : secondSiblingSavedOutcome;
            resolve({
              ok: !isFirstSibling,
              status: isFirstSibling ? 422 : 200,
              json: function () { return Promise.resolve({
                  ok: !isFirstSibling,
                  persisted: !isFirstSibling,
                  reason: isFirstSibling
                    ? firstSiblingFailureOutcome.reason : undefined,
                  visual_outcome_persisted: true,
                  envelope: isFirstSibling ? undefined : narrowedEnvelope,
                  visual_outcome: latestConfirmedStoredOutcome,
                }); },
            });
          };
        });
      }
      if (String(url).indexOf('/visual-outcome') !== -1) {
        confirmedOutcomesBeforeTerminal.push(latestConfirmedStoredOutcome);
        const requestedOutcome = JSON.parse(options.body);
        narrowOutcomes.push(requestedOutcome);
        latestConfirmedStoredOutcome = requestedOutcome;
        return Promise.resolve(confirmedOutcomeResponse(options));
      }
      return Promise.reject(new Error('unexpected fetch ' + url));
    };
    D.resetDedupe();
    const narrowMeta = {
      conversationId: 'conv-legibility',
      assistantIndex: 0,
      onNarrowedEnvelopePersisted: function (envelope, outcome, visualBlockIndex) {
        narrowMeta.visualOutcome = outcome;
        if (envelope) {
          narrowedCachedIndexes.push(visualBlockIndex);
          narrowedCachedText = D.replaceBlocksWithEnvelope(
            narrowedCachedText, envelope, visualBlockIndex,
          );
        }
      },
    };
    D.dispatch(multiVisualText, 'conv-legibility#0', narrowMeta);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    D.setActiveKey('conv-away#0');
    D.resetDedupe();
    const reloadedNarrowMeta = {
      conversationId: 'conv-legibility',
      assistantIndex: 0,
      visualOutcome: {
        state: 'building',
        stage: 'legibility',
        reason: 'A narrower visual is being synthesized.',
        legibility_attempts: { 1: 'in_progress' },
      },
      onNarrowedEnvelopePersisted: function (envelope, outcome, visualBlockIndex) {
        reloadedNarrowMeta.visualOutcome = outcome;
        if (envelope) {
          reloadedNarrowedCachedIndexes.push(visualBlockIndex);
          reloadedNarrowedCachedText = D.replaceBlocksWithEnvelope(
            reloadedNarrowedCachedText, envelope, visualBlockIndex,
          );
        }
      },
    };
    D.dispatch(multiVisualText, 'conv-legibility#0', reloadedNarrowMeta);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    const firstSiblingStayedSingleFlight = narrowRequests.length === 1
      && typeof resolvedNarrowResponses[1] === 'function';
    if (resolvedNarrowResponses[1]) resolvedNarrowResponses[1]();
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    const secondSiblingStayedSingleFlight = narrowRequests.length === 2
      && typeof resolvedNarrowResponses[2] === 'function';
    if (resolvedNarrowResponses[2]) resolvedNarrowResponses[2]();
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    const oneFullSequenceApplied = narrowPanelCalls.length === 3
      && new Set(narrowPanelCalls.map((call) => (
        String(call.ora_visual_dispatch_key || '')
      ))).size === 3;
    record('dispatch: overlapping contexts share one complete assistant source sequence',
           legibilityFinding && legibilityFinding.code === 'W_VIEWPORT_TEXT_LEGIBILITY'
           && firstSiblingStayedSingleFlight
           && secondSiblingStayedSingleFlight
           && oneFullSequenceApplied
           && narrowRequests.length === 2
           && narrowRequests[0].narrow_subject === true
           && narrowRequests[0].conversation_id === 'conv-legibility'
           && narrowRequests[0].assistant_index === 0
           && narrowRequests[0].visual_block_index === 1
           && narrowRequests[0].manual_visual_type === 'concept_map'
           && narrowRequests[1].visual_block_index === 2
           && narrowRequests[1].manual_visual_type === 'pro_con'
           && narrowOutcomes.length === 1
           && confirmedOutcomesBeforeTerminal.length === 1
           && confirmedOutcomesBeforeTerminal[0].reason
             === secondSiblingSavedOutcome.reason
           && narrowOutcomes.every((outcome) => (
             outcome.state === 'failed'
               && outcome.stage === 'legibility'
               && outcome.reason === firstSiblingFailureOutcome.reason
               && outcome.legibility_attempts['1'] === 'exhausted'
               && outcome.legibility_attempts['2'] === 'exhausted'
           ))
           && narrowMeta.visualOutcome.state === 'failed'
           && narrowMeta.visualOutcome.reason === firstSiblingFailureOutcome.reason
           && reloadedNarrowMeta.visualOutcome.state === 'failed'
           && reloadedNarrowMeta.visualOutcome.reason
             === firstSiblingFailureOutcome.reason
           && latestConfirmedStoredOutcome.reason
             === firstSiblingFailureOutcome.reason
           && narrowedCachedIndexes.join(',') === '2',
           'finding=' + JSON.stringify(legibilityFinding)
             + ' renders=' + narrowPanelCalls.length
             + ' keys=' + JSON.stringify(narrowPanelCalls.map((call) => (
               call.ora_visual_dispatch_key
             )))
             + ' requests=' + narrowRequests.length
             + ' outcomes=' + JSON.stringify(narrowOutcomes));
    const expectedNarrowedText = 'Lead prose.\n' + malformedFence
      + '\nMalformed fence stays visible.\n'
      + fenced(ENVELOPE)
      + '\nMiddle prose.\n' + fenced(JSON.stringify(narrowedEnvelope, null, 2))
      + '\nTail prose.';
    record('dispatch: sibling retries preserve malformed fence and surrounding prose',
           narrowedCachedText === expectedNarrowedText
           && reloadedNarrowedCachedText === expectedNarrowedText
           && reloadedNarrowedCachedIndexes.join(',') === '2'
           && narrowedCachedText.indexOf(malformedFence) !== -1
           && D.extractBlocks(narrowedCachedText).length === 2
           && D.extractBlocks(narrowedCachedText)[0].envelope.title === 'Dispatch test'
           && D.extractBlocks(narrowedCachedText)[1].envelope.title === 'Narrowed second visual',
           narrowedCachedText);

    // An earlier unreadable replace must finish its one narrowed replacement
    // before a later order-sensitive clear is applied. The clear is not safe
    // to replay: batching originals and retrying afterward would leave the
    // narrowed replacement visible and reverse the authored source order.
    const orderedEvents = [];
    const orderedDispatchKeys = [];
    const orderedOutcomes = [];
    let orderedVisible = null;
    const orderedOriginal = Object.assign(JSON.parse(ENVELOPE), {
      title: 'Unreadable ordered replace',
      canvas_action: 'replace',
    });
    const orderedNarrowed = Object.assign(JSON.parse(ENVELOPE), {
      title: 'Narrowed ordered replace',
      canvas_action: 'replace',
    });
    const orderedClear = Object.assign(JSON.parse(ENVELOPE), {
      title: 'Later source clear',
      canvas_action: 'clear',
    });
    const orderedText = fenced(JSON.stringify(orderedOriginal))
      + '\n' + fenced(JSON.stringify(orderedClear));
    win.OraPanels = { visual: {
      showError: function (message) { errorBar.push(String(message)); },
      onBridgeUpdate: function (state) {
        const dispatchKey = String(state.ora_visual_dispatch_key || '');
        const envelope = state.ora_visual_blocks[0].envelope;
        orderedDispatchKeys.push(dispatchKey);
        if (dispatchKey.indexOf(':narrowed:') !== -1) {
          orderedEvents.push('narrowed-replace');
          orderedVisible = envelope.title;
          return Promise.resolve([{ svg: '<svg/>', errors: [], warnings: [] }]);
        }
        if (envelope.canvas_action === 'clear') {
          orderedEvents.push('clear');
          orderedVisible = null;
          return Promise.resolve([{ action: 'clear', applied: true }]);
        }
        orderedEvents.push('original-replace');
        return Promise.resolve([{
          needs_narrower_subject: true,
          legibility_finding: legibilityFinding,
        }]);
      },
    } };
    win.fetch = function (url, options) {
      if (String(url) === '/api/visual/regenerate') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: function () { return Promise.resolve({
            ok: true,
            persisted: true,
            visual_outcome_persisted: true,
            envelope: orderedNarrowed,
            visual_outcome: {
              state: 'failed',
              stage: 'legibility',
              reason: 'A narrower visual was saved, but insertion has not been confirmed.',
              legibility_attempts: { 0: 'exhausted' },
            },
          }); },
        });
      }
      if (String(url).indexOf('/visual-outcome') !== -1) {
        orderedOutcomes.push(JSON.parse(options.body));
        return Promise.resolve(confirmedOutcomeResponse(options));
      }
      return Promise.reject(new Error('unexpected fetch ' + url));
    };
    const orderedMeta = {
      conversationId: 'conv-source-order',
      assistantIndex: 0,
      onNarrowedEnvelopePersisted: function (_envelope, outcome) {
        orderedMeta.visualOutcome = outcome;
      },
    };
    D.resetDedupe();
    D.dispatch(orderedText, 'conv-source-order#0', orderedMeta);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    record('dispatch: unreadable replacement settles before later clear in source order',
           orderedEvents.join(',') === 'original-replace,narrowed-replace,clear'
           && orderedEvents.filter((event) => event === 'clear').length === 1
           && orderedVisible === null
           && new Set(orderedDispatchKeys).size === orderedDispatchKeys.length
           && orderedOutcomes.length === 1
           && orderedOutcomes[0].state === 'ready'
           && orderedOutcomes[0].legibility_attempts['0'] === 'exhausted',
           'events=' + JSON.stringify(orderedEvents)
             + ' keys=' + JSON.stringify(orderedDispatchKeys)
             + ' visible=' + orderedVisible
             + ' outcomes=' + JSON.stringify(orderedOutcomes));
    win.OraPanels = { visual: narrowPanel };

    // A reloaded multi-visual turn carries exact exhaustion. Fence 1 stays
    // exhausted while the independently unreadable fence 2 still gets its
    // one attempt; the assistant-wide legibility stage suppresses neither.
    const reloadRequests = [];
    const reloadOutcomes = [];
    const reloadMeta = {
      conversationId: 'conv-legibility-reload',
      assistantIndex: 0,
      visualOutcome: {
        state: 'failed',
        stage: 'legibility',
        reason: 'The first visual remained unreadable.',
        legibility_attempts: { 1: 'exhausted' },
      },
      onNarrowedEnvelopePersisted: function (_envelope, outcome) {
        reloadMeta.visualOutcome = outcome;
      },
    };
    win.fetch = function (url, options) {
      if (String(url) === '/api/visual/regenerate') {
        const request = JSON.parse(options.body);
        reloadRequests.push(request);
        return Promise.resolve({
          ok: true,
          status: 200,
          json: function () { return Promise.resolve({
            ok: true,
            persisted: true,
            visual_outcome_persisted: true,
            envelope: narrowedEnvelope,
            visual_outcome: {
              state: 'failed',
              stage: 'legibility',
              reason: 'A narrower visual was saved, but insertion has not been confirmed.',
              legibility_attempts: { 1: 'exhausted', 2: 'exhausted' },
            },
          }); },
        });
      }
      if (String(url).indexOf('/visual-outcome') !== -1) {
        reloadOutcomes.push(JSON.parse(options.body));
        return Promise.resolve(confirmedOutcomeResponse(options));
      }
      return Promise.reject(new Error('unexpected fetch ' + url));
    };
    D.resetDedupe();
    D.dispatch(multiVisualText, 'conv-legibility-reload#0', reloadMeta);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    record('dispatch: reload exhaustion is per raw fence, not assistant-wide',
           reloadRequests.length === 1
           && reloadRequests[0].visual_block_index === 2
           && reloadOutcomes.length === 1
           && reloadOutcomes[0].state === 'failed'
           && reloadOutcomes[0].legibility_attempts['1'] === 'exhausted'
           && reloadOutcomes[0].legibility_attempts['2'] === 'exhausted',
           'requests=' + JSON.stringify(reloadRequests)
             + ' outcomes=' + JSON.stringify(reloadOutcomes));

    // A true cold context has no shared-operation map entry. Its durable
    // in-progress claim is terminally reconciled without a second request or
    // an error leaking into whichever Dialogue is now active.
    const coldErrorsBefore = errorBar.length;
    const coldRequests = [];
    const coldOutcomes = [];
    let coldCachedOutcome = null;
    const coldMeta = {
      conversationId: 'conv-cold-orphan',
      assistantIndex: 0,
      visualOutcome: {
        state: 'building',
        stage: 'legibility',
        reason: 'A narrower visual is being synthesized.',
        legibility_attempts: { 0: 'in_progress' },
      },
      onNarrowedEnvelopePersisted: function (_envelope, outcome) {
        coldCachedOutcome = outcome;
        coldMeta.visualOutcome = outcome;
      },
    };
    win.OraPanels = { visual: {
      showError: function (message) { errorBar.push(String(message)); },
      onBridgeUpdate: function () {
        return Promise.resolve([{
          needs_narrower_subject: true,
          legibility_finding: legibilityFinding,
        }]);
      },
    } };
    win.fetch = function (url, options) {
      if (String(url) === '/api/visual/regenerate') {
        coldRequests.push(JSON.parse(options.body));
        return Promise.reject(new Error('cold orphan started a second synthesis'));
      }
      if (String(url).indexOf('/visual-outcome') !== -1) {
        coldOutcomes.push(JSON.parse(options.body));
        return Promise.resolve(confirmedOutcomeResponse(options));
      }
      return Promise.reject(new Error('unexpected fetch ' + url));
    };
    D.resetDedupe();
    D.dispatch(fenced(ENVELOPE), 'conv-cold-orphan#0', coldMeta);
    D.setActiveKey('conv-other#0');
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    record('dispatch: cold orphaned attempt fails quietly without resynthesis',
           coldRequests.length === 0
           && coldOutcomes.length === 1
           && coldOutcomes[0].state === 'failed'
           && coldOutcomes[0].stage === 'legibility'
           && coldOutcomes[0].reason.indexOf('could not be confirmed after reopening') !== -1
           && coldOutcomes[0].legibility_attempts['0'] === 'exhausted'
           && coldCachedOutcome === coldMeta.visualOutcome
           && coldCachedOutcome.state === 'failed'
           && coldCachedOutcome.legibility_attempts['0'] === 'exhausted'
           && errorBar.length === coldErrorsBefore,
           'requests=' + JSON.stringify(coldRequests)
             + ' outcomes=' + JSON.stringify(coldOutcomes)
             + ' errors=' + JSON.stringify(errorBar));

    // A late failure still belongs to its originating Dialogue. The retry
    // endpoint already persisted that exact terminal object, so the client
    // caches it without posting a prefixed replacement. Returning with that
    // failed legibility outcome must not synthesize or publish it again.
    const lateFailureErrorsBefore = errorBar.length;
    const lateFailureRequests = [];
    const lateFailureOutcomes = [];
    let resolveLateFailure = null;
    let lateFailureCachedOutcome = null;
    const lateFailureMeta = {
      conversationId: 'conv-late-failure',
      assistantIndex: 0,
      onNarrowedEnvelopePersisted: function (envelope, outcome) {
        if (!envelope) {
          lateFailureCachedOutcome = outcome;
          lateFailureMeta.visualOutcome = outcome;
        }
      },
    };
    win.OraPanels = { visual: {
      showError: function (message) { errorBar.push(String(message)); },
      onBridgeUpdate: function () {
        return Promise.resolve([{
          needs_narrower_subject: true,
          legibility_finding: legibilityFinding,
        }]);
      },
    } };
    win.fetch = function (url, options) {
      if (String(url) === '/api/visual/regenerate') {
        lateFailureRequests.push(JSON.parse(options.body));
        return new Promise(function (resolve) {
          resolveLateFailure = function () { resolve({
            ok: true,
            status: 200,
            json: function () { return Promise.resolve({
              ok: false,
              reason: 'synthesis failed after 3 attempt(s)',
              visual_outcome_persisted: true,
              visual_outcome: {
                state: 'failed',
                stage: 'legibility',
                reason: 'synthesis failed after 3 attempt(s)',
                legibility_attempts: { 0: 'exhausted' },
              },
            }); },
          }); };
        });
      }
      if (String(url).indexOf('/visual-outcome') !== -1) {
        lateFailureOutcomes.push(JSON.parse(options.body));
        return Promise.resolve(confirmedOutcomeResponse(options));
      }
      return Promise.reject(new Error('unexpected fetch ' + url));
    };
    D.resetDedupe();
    D.dispatch(fenced(ENVELOPE), 'conv-late-failure#0', lateFailureMeta);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    D.setActiveKey('conv-other#0');
    D.resetDedupe();
    D.dispatch(fenced(ENVELOPE), 'conv-late-failure#0', lateFailureMeta);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    const sameFenceRaceGuarded = lateFailureRequests.length === 1;
    D.setActiveKey('conv-other#0');
    if (resolveLateFailure) resolveLateFailure();
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    const lateFailureStayedOffOtherDialogue = errorBar.length === lateFailureErrorsBefore;
    const originalLateFailureCachedOutcome = lateFailureCachedOutcome;
    D.resetDedupe();
    D.dispatch(fenced(ENVELOPE), 'conv-late-failure#0', lateFailureMeta);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    record('dispatch: late retry failure stays identity-bound and is not retried on return',
           lateFailureStayedOffOtherDialogue
           && sameFenceRaceGuarded
           && lateFailureRequests.length === 1
           && lateFailureOutcomes.length === 0
           && originalLateFailureCachedOutcome === lateFailureCachedOutcome
           && lateFailureCachedOutcome === lateFailureMeta.visualOutcome
           && lateFailureCachedOutcome.state === 'failed'
           && lateFailureCachedOutcome.reason === 'synthesis failed after 3 attempt(s)'
           && lateFailureCachedOutcome.legibility_attempts['0'] === 'exhausted'
           && errorBar.length === lateFailureErrorsBefore + 1,
           'errors=' + JSON.stringify(errorBar)
             + ' requests=' + lateFailureRequests.length
             + ' outcomes=' + JSON.stringify(lateFailureOutcomes));

    // A successful synthesis that completes after navigation has still not
    // inserted anything. Cache the durable replacement against its origin,
    // terminate that origin's building outcome without surfacing it in the
    // other Dialogue, then let reopening insert the saved fence without a
    // second synthesis attempt.
    const lateSuccessErrorsBefore = errorBar.length;
    const lateSuccessRequests = [];
    const lateSuccessOutcomes = [];
    const lateSuccessEnvelope = {
      type: 'concept_map',
      title: 'Saved narrower visual',
      spec: { nodes: [{ id: 'a', label: 'One load-bearing subject' }], edges: [] },
    };
    let lateSuccessCachedText = fenced(ENVELOPE);
    let resolveLateSuccess = null;
    const lateSuccessMeta = {
      conversationId: 'conv-late-success',
      assistantIndex: 0,
      onNarrowedEnvelopePersisted: function (envelope, outcome, visualBlockIndex) {
        lateSuccessMeta.visualOutcome = outcome;
        if (envelope) {
          lateSuccessCachedText = D.replaceBlocksWithEnvelope(
            lateSuccessCachedText, envelope, visualBlockIndex,
          );
        }
      },
    };
    win.OraPanels = { visual: {
      showError: function (message) { errorBar.push(String(message)); },
      onBridgeUpdate: function (state) {
        const envelope = state.ora_visual_blocks[0].envelope;
        if (envelope.title === lateSuccessEnvelope.title) {
          return Promise.resolve([{ svg: '<svg/>', errors: [], warnings: [] }]);
        }
        return Promise.resolve([{
          needs_narrower_subject: true,
          legibility_finding: legibilityFinding,
        }]);
      },
    } };
    win.fetch = function (url, options) {
      if (String(url) === '/api/visual/regenerate') {
        lateSuccessRequests.push(JSON.parse(options.body));
        return new Promise(function (resolve) {
          resolveLateSuccess = function () { resolve({
            ok: true,
            status: 200,
            json: function () { return Promise.resolve({
              ok: true,
              persisted: true,
              visual_outcome_persisted: true,
              envelope: lateSuccessEnvelope,
              visual_outcome: {
                state: 'failed',
                stage: 'legibility',
                reason: 'A narrower visual was saved, but insertion has not been confirmed.',
                legibility_attempts: { 0: 'exhausted' },
              },
            }); },
          }); };
        });
      }
      if (String(url).indexOf('/visual-outcome') !== -1) {
        lateSuccessOutcomes.push(JSON.parse(options.body));
        return Promise.resolve(confirmedOutcomeResponse(options));
      }
      return Promise.reject(new Error('unexpected fetch ' + url));
    };
    D.resetDedupe();
    D.dispatch(fenced(ENVELOPE), 'conv-late-success#0', lateSuccessMeta);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    D.setActiveKey('conv-other#0');
    if (resolveLateSuccess) resolveLateSuccess();
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    const lateSuccessStayedOffOtherDialogue = errorBar.length === lateSuccessErrorsBefore;
    const lateSuccessFailedAtOrigin = lateSuccessOutcomes.length === 1
      && lateSuccessOutcomes[0].state === 'failed'
      && lateSuccessOutcomes[0].stage === 'legibility'
      && lateSuccessOutcomes[0].reason.indexOf('insertion did not occur') !== -1
      && lateSuccessOutcomes[0].reason.indexOf('originating Dialogue was no longer active') !== -1
      && lateSuccessMeta.visualOutcome.state === 'failed'
      && D.extractBlocks(lateSuccessCachedText)[0].envelope.title
        === lateSuccessEnvelope.title;
    D.resetDedupe();
    D.dispatch(lateSuccessCachedText, 'conv-late-success#0', lateSuccessMeta);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    record('dispatch: late retry success terminates origin and reopens from saved envelope',
           lateSuccessStayedOffOtherDialogue
           && lateSuccessFailedAtOrigin
           && lateSuccessRequests.length === 1
           && lateSuccessOutcomes.length === 2
           && lateSuccessOutcomes[1].state === 'ready'
           && lateSuccessOutcomes[1].stage === 'legibility'
           && lateSuccessMeta.visualOutcome.state === 'ready'
           && lateSuccessMeta.visualOutcome.legibility_attempts['0'] === 'exhausted',
           'errors=' + JSON.stringify(errorBar)
             + ' requests=' + JSON.stringify(lateSuccessRequests)
             + ' outcomes=' + JSON.stringify(lateSuccessOutcomes)
             + ' cached=' + lateSuccessCachedText);

    // A narrower retry is ready only when the active editor returns the
    // compiler's real success shape. Excalidraw adds action/native metadata;
    // Konva returns the compiler result itself. Resolved failure shapes from
    // Konva's fallback renderer must remain terminal failures, including when
    // their originating Dialogue is no longer active.
    const narrowedRenderCases = [
      { name: 'undefined', result: undefined, fails: true, navigateAway: true },
      { name: 'null', result: null, fails: true },
      { name: 'empty result', result: [], fails: true },
      { name: 'empty object', result: {}, fails: true },
      { name: 'empty SVG', result: { svg: '', errors: [], warnings: [] }, fails: true },
      {
        name: 'renderer errors',
        result: {
          svg: '<svg/>',
          errors: [{ code: 'E_RENDERER_FAILURE', message: 'renderer failed' }],
          warnings: [],
        },
        fails: true,
      },
      {
        name: 'Konva success',
        result: { svg: '<svg/>', errors: [], warnings: [] },
        fails: false,
      },
      {
        name: 'Excalidraw success',
        result: {
          svg: '<svg/>', errors: [], warnings: [], action: 'replace', native: true,
        },
        fails: false,
      },
    ];
    const narrowedRenderResults = [];
    for (let caseIndex = 0; caseIndex < narrowedRenderCases.length; caseIndex += 1) {
      const renderCase = narrowedRenderCases[caseIndex];
      const conversationId = 'conv-narrowed-render-' + caseIndex;
      const dispatchKey = conversationId + '#0';
      const outcomes = [];
      const errorsBefore = errorBar.length;
      const meta = {
        conversationId: conversationId,
        assistantIndex: 0,
        onNarrowedEnvelopePersisted: function (_envelope, outcome) {
          meta.visualOutcome = outcome;
        },
      };
      win.OraPanels = { visual: {
        showError: function (message) { errorBar.push(String(message)); },
        onBridgeUpdate: function (state) {
          if (String(state.ora_visual_dispatch_key || '').indexOf(':narrowed:') === -1) {
            return Promise.resolve([{
              needs_narrower_subject: true,
              legibility_finding: legibilityFinding,
            }]);
          }
          if (renderCase.navigateAway) {
            D.setActiveKey('conv-other#0');
          }
          return Promise.resolve(renderCase.result);
        },
      } };
      win.fetch = function (url, options) {
        if (String(url) === '/api/visual/regenerate') {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: function () { return Promise.resolve({
              ok: true,
              persisted: true,
              visual_outcome_persisted: true,
              envelope: narrowedEnvelope,
              visual_outcome: {
                state: 'failed',
                stage: 'legibility',
                reason: 'A narrower visual was saved, but insertion has not been confirmed.',
                legibility_attempts: { 0: 'exhausted' },
              },
            }); },
          });
        }
        if (String(url).indexOf('/visual-outcome') !== -1) {
          outcomes.push(JSON.parse(options.body));
          return Promise.resolve(confirmedOutcomeResponse(options));
        }
        return Promise.reject(new Error('unexpected fetch ' + url));
      };
      D.resetDedupe();
      D.dispatch(fenced(ENVELOPE), dispatchKey, meta);
      await new Promise((resolve) => setTimeout(resolve, 0));
      await new Promise((resolve) => setTimeout(resolve, 0));
      await new Promise((resolve) => setTimeout(resolve, 0));
      await new Promise((resolve) => setTimeout(resolve, 0));
      await new Promise((resolve) => setTimeout(resolve, 0));
      narrowedRenderResults.push({
        name: renderCase.name,
        fails: renderCase.fails,
        outcome: outcomes[outcomes.length - 1] || null,
        cached: meta.visualOutcome || null,
        surfacedErrors: errorBar.length - errorsBefore,
      });
    }
    record('dispatch: narrowed render requires an affirmative editor success result',
           narrowedRenderResults.every((entry) => {
             if (entry.fails) {
               return entry.outcome && entry.outcome.state === 'failed'
                 && entry.outcome.stage === 'legibility'
                 && entry.outcome.reason.indexOf('narrowed visual could not be applied') !== -1
                 && entry.cached && entry.cached.state === 'failed'
                 && (entry.name === 'undefined'
                   ? entry.surfacedErrors === 0 : entry.surfacedErrors === 1);
             }
             return entry.outcome && entry.outcome.state === 'ready'
               && entry.cached && entry.cached.state === 'ready'
               && entry.surfacedErrors === 0;
           }),
           JSON.stringify(narrowedRenderResults));

    // Terminal memory is published only from the canonical response. While
    // the save is unresolved, an overlapping observer shares the same owner
    // and both retain their last confirmed durable outcome.
    const confirmationErrors = [];
    let confirmationPanelCalls = 0;
    let resolveConfirmation = null;
    let confirmationOptions = null;
    const canonicalReady = {
      state: 'ready',
      stage: 'canonical-server-stage',
      reason: 'Canonical normalized outcome from storage.',
    };
    win.OraPanels = { visual: {
      showError: function (message) { confirmationErrors.push(String(message)); },
      onBridgeUpdate: function () {
        confirmationPanelCalls += 1;
        return Promise.resolve([{ svg: '<svg/>', errors: [], warnings: [] }]);
      },
    } };
    win.fetch = function (url, options) {
      if (String(url).indexOf('/visual-outcome') !== -1) {
        confirmationOptions = options;
        return new Promise(function (resolve) { resolveConfirmation = resolve; });
      }
      return Promise.reject(new Error('unexpected fetch ' + url));
    };
    const ownerConfirmed = { state: 'building', reason: 'Durable owner state.' };
    const observerConfirmed = { state: 'building', reason: 'Durable observer state.' };
    const ownerMeta = {
      conversationId: 'conv-save-confirmation',
      assistantIndex: 0,
      visualOutcome: ownerConfirmed,
    };
    const observerMeta = {
      conversationId: 'conv-save-confirmation',
      assistantIndex: 0,
      visualOutcome: observerConfirmed,
    };
    D.resetDedupe();
    D.dispatch(fenced(ENVELOPE), 'conv-save-confirmation#0', ownerMeta);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    D.dispatch(fenced(ENVELOPE), 'conv-save-confirmation#0', observerMeta);
    await new Promise((resolve) => setTimeout(resolve, 0));
    const memoryHeldForConfirmation = confirmationPanelCalls === 1
      && typeof resolveConfirmation === 'function'
      && ownerMeta.visualOutcome === ownerConfirmed
      && observerMeta.visualOutcome === observerConfirmed;
    resolveConfirmation(confirmedOutcomeResponse(
      confirmationOptions, canonicalReady,
    ));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    record('dispatch: owner and observer publish only the canonical stored outcome',
           memoryHeldForConfirmation
           && ownerMeta.visualOutcome === canonicalReady
           && observerMeta.visualOutcome === canonicalReady
           && confirmationErrors.length === 0,
           'calls=' + confirmationPanelCalls
             + ' owner=' + JSON.stringify(ownerMeta.visualOutcome)
             + ' observer=' + JSON.stringify(observerMeta.visualOutcome));

    // A failed terminal save is caught, retains the last confirmed state,
    // surfaces only in the active origin, releases cleanly, and can retry on
    // reopen without publishing the rejected candidate.
    const saveFailureErrors = [];
    let saveFailurePanelCalls = 0;
    let saveFailurePosts = 0;
    win.OraPanels = { visual: {
      showError: function (message) { saveFailureErrors.push(String(message)); },
      onBridgeUpdate: function () {
        saveFailurePanelCalls += 1;
        return Promise.resolve([{ svg: '<svg/>', errors: [], warnings: [] }]);
      },
    } };
    win.fetch = function (url, options) {
      if (String(url).indexOf('/visual-outcome') !== -1) {
        saveFailurePosts += 1;
        if (saveFailurePosts === 1) {
          return Promise.resolve({
            ok: false,
            status: 500,
            json: function () { return Promise.resolve({
              ok: false, error: 'durable write failed',
            }); },
          });
        }
        return Promise.resolve(confirmedOutcomeResponse(options, canonicalReady));
      }
      return Promise.reject(new Error('unexpected fetch ' + url));
    };
    const retainedOutcome = { state: 'building', reason: 'Last confirmed state.' };
    const failedSaveMeta = {
      conversationId: 'conv-save-failure',
      assistantIndex: 0,
      visualOutcome: retainedOutcome,
    };
    D.resetDedupe();
    D.dispatch(fenced(ENVELOPE), 'conv-save-failure#0', failedSaveMeta);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    const retainedAfterFailure = failedSaveMeta.visualOutcome === retainedOutcome
      && saveFailureErrors.length === 1;
    D.resetDedupe();
    D.dispatch(fenced(ENVELOPE), 'conv-save-failure#0', failedSaveMeta);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    record('dispatch: failed terminal save retains truth and reopen retries safely',
           retainedAfterFailure
           && saveFailurePanelCalls === 2
           && saveFailurePosts === 2
           && failedSaveMeta.visualOutcome === canonicalReady,
           'panelCalls=' + saveFailurePanelCalls
             + ' posts=' + saveFailurePosts
             + ' errors=' + JSON.stringify(saveFailureErrors));

    win.fetch = function () { return Promise.reject(new Error('network down')); };
    const caughtNetworkFailure = await D.persistOutcome(
      { conversationId: 'conv-network-rejection', assistantIndex: 0 },
      { state: 'ready' },
    );
    record('persist outcome: network rejection is a caught structured failure',
           caughtNetworkFailure.ok === false
           && caughtNetworkFailure.visual_outcome === null
           && caughtNetworkFailure.error === 'network down',
           JSON.stringify(caughtNetworkFailure));
    win.fetch = priorNarrowFetch;

    // 11. No registry → still counts, no throw
    win.OraPanels = undefined;
    D.resetDedupe();
    let threw = false, n3 = 0;
    try { n3 = D.dispatch(text, 'conv2#0'); } catch (e) { threw = true; }
    record('dispatch: registry absent is safe', !threw && n3 === 1, 'threw=' + threw + ' n=' + n3);

    // A durable generated-image descriptor fetches the stored artifact and
    // never re-enters the image provider route, including on replay/dedupe.
    const priorFetch = win.fetch;
    const priorCanvas = win.OraCanvas;
    const fetched = [];
    const inserted = [];
    const savedOutcomes = [];
    let resolveImageOutcome = null;
    win.fetch = function (url, options) {
      fetched.push(String(url));
      if (String(url).indexOf('/visual-outcome') !== -1) {
        savedOutcomes.push(JSON.parse(options.body));
        return new Promise(function (resolve) {
          resolveImageOutcome = function () {
            resolve(confirmedOutcomeResponse(options));
          };
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        blob: function () {
          return Promise.resolve(new win.Blob(['stored-image'], { type: 'image/png' }));
        },
      });
    };
    win.OraCanvas = {
      insertAssistantImage: function (file, artifact) {
        inserted.push({ file, artifact });
        return Promise.resolve({ id: 'assistant-image' });
      },
    };
    const imageArtifact = {
      schema_version: 'ora.image-artifact/1.0',
      url: '/api/conversation/image-turn/visual-artifacts/generated-0123456789abcdef01234567.png',
      mime_type: 'image/png',
      filename: 'generated-0123456789abcdef01234567.png',
      assistant_visual_id: 'assistant-image-test',
    };
    const imageText = 'Prose.\n```ora-image\n'
      + JSON.stringify(imageArtifact) + '\n```';
    D.resetDedupe();
    const imageCount = D.dispatch(imageText, 'image-turn#0', {
      conversationId: 'image-turn',
      assistantIndex: 0,
      visualOutcome: {
        state: 'building',
        stage: 'image_generation',
        reason: 'Generated; awaiting insertion.',
      },
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    D.setActiveKey('image-other#0');
    D.resetDedupe();
    D.dispatch(imageText, 'image-turn#0', {
      conversationId: 'image-turn', assistantIndex: 0,
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    const publicationKeptSequenceOwned = typeof resolveImageOutcome === 'function'
      && inserted.length === 1
      && fetched.filter((url) => url.indexOf('/visual-artifacts/') !== -1).length === 1;
    if (resolveImageOutcome) resolveImageOutcome();
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    const artifactFetches = fetched.filter((url) => url.indexOf('/visual-artifacts/') !== -1);
    record('dispatch: stored generated image inserts once without provider replay',
           imageCount === 1 && publicationKeptSequenceOwned
           && inserted.length === 1 && artifactFetches.length === 1
           && fetched.every((url) => url.indexOf('/api/capability/image_generates') === -1)
           && savedOutcomes.length === 1
           && savedOutcomes[0].state === 'ready'
           && savedOutcomes[0].stage === 'image_generation'
           && D.stripBlocks(imageText).indexOf('ora-image') === -1,
           'fetched=' + JSON.stringify(fetched) + ' inserted=' + inserted.length);

    win.OraPanels = priorRegistry;
    win.alert = priorAlert;
    win.fetch = priorFetch;
    win.OraCanvas = priorCanvas;
  },
};
