/**
 * tests/cases/test-visual-fallback.js — WP-4.4 regression suite.
 *
 * Exports { label, run(ctx, record) } per the run.js case-file convention.
 *
 * Coverage:
 *   1. showFallbackPrompt(alert) renders an overlay with a heading, body,
 *      and three action buttons.
 *   2. user_message is rendered verbatim in the overlay body.
 *   3. Meta line shows reason + extractor_attempted + first parse error
 *      when those fields are present.
 *   4. Meta line hides when no extractor + no parse_errors are present.
 *   5. Overlay is hidden=false after show, hidden=true after dismiss.
 *   6. Click "Dismiss" → overlay hidden, no side effects (pending image
 *      unchanged, active tool unchanged).
 *   7. Click "Start tracing" → rect tool becomes active + overlay dismissed.
 *   8. Click "Queue for later" → POST to /chat/queue-retry with the right
 *      payload shape + overlay dismissed after success.
 *   9. Queue for later surfaces a "queued" status note before dismissing.
 *  10. OraPanels.visual.showFallbackPrompt routes to the active instance.
 *  11. OraPanels.visual.dismissFallbackPrompt routes to the active instance.
 *  12. Subsequent show calls update the overlay content (not duplicate DOM).
 *  13. Restricted action set hides the buttons that aren't advertised.
 *  14. Defensive: showFallbackPrompt with non-object input is a no-op.
 *  15. Defensive: queue_for_later with no fetch available still dismisses
 *      and surfaces an inline failure note.
 */

'use strict';

function mkDiv(win) {
  var d = win.document.createElement('div');
  d.style.cssText = 'width:640px;height:420px;position:relative;';
  win.document.body.appendChild(d);
  return d;
}

function makeAlert(overrides) {
  var base = {
    reason:              'extraction_failed',
    extractor_attempted: 'api-vision',
    parse_errors:        ['JSON parse failed at col 37'],
    user_message:        "I couldn't extract structure from your image. "
                         + "Please trace the key elements manually "
                         + "using the shape tools.",
    actions:             ['start_tracing', 'queue_for_later', 'dismiss'],
    conversation_id:     'test-convo-1',
  };
  if (overrides) {
    for (var k in overrides) base[k] = overrides[k];
  }
  return base;
}

/**
 * Install a mock fetch implementation on the jsdom window and return the
 * invocations array. Each entry is { url, init, resolvedWith }.
 */
function installMockFetch(win, response) {
  var calls = [];
  win.fetch = function (url, init) {
    var call = { url: url, init: init };
    calls.push(call);
    var body = response && response.body
      ? response.body
      : { queued: true, queue_size: 1, entry: {} };
    return Promise.resolve({
      ok: response && typeof response.ok === 'boolean' ? response.ok : true,
      json: function () { return Promise.resolve(body); },
    });
  };
  return calls;
}

function tick(ms) {
  return new Promise(function (resolve) { setTimeout(resolve, ms || 10); });
}

module.exports = {
  label: 'Visual fallback UX (WP-4.4) — overlay + actions + queue-retry',
  run: async function run(ctx, record) {
    var win = ctx.win;

    if (typeof win.Konva === 'undefined' || typeof win.VisualPanel === 'undefined') {
      record('visual-fallback: harness bootstrap', false,
        'Konva=' + typeof win.Konva + ' VisualPanel=' + typeof win.VisualPanel);
      return;
    }

    // ── 1. Overlay renders with heading, body, three buttons ─────────────
    try {
      var div = mkDiv(win);
      var panel = new win.VisualPanel(div, { id: 'vf-1' });
      panel.init();
      panel.showFallbackPrompt(makeAlert());
      var overlay = div.querySelector('.visual-panel__fallback-overlay');
      record('visual-fallback: overlay element renders',
        !!overlay && overlay.hidden === false,
        'overlay=' + !!overlay + ' hidden=' + (overlay && overlay.hidden));
      var heading = div.querySelector('.visual-panel__fallback-heading');
      record('visual-fallback: overlay heading is present',
        !!heading && (heading.textContent || '').length > 0,
        'heading=' + (heading && heading.textContent));
      var btns = div.querySelectorAll('.visual-panel__fallback-btn');
      record('visual-fallback: overlay has 3 action buttons',
        btns.length === 3, 'count=' + btns.length);
      var startBtn = div.querySelector('.visual-panel__fallback-btn[data-action="start_tracing"]');
      var queueBtn = div.querySelector('.visual-panel__fallback-btn[data-action="queue_for_later"]');
      var dismissBtn = div.querySelector('.visual-panel__fallback-btn[data-action="dismiss"]');
      record('visual-fallback: start_tracing button present',
        !!startBtn, 'btn=' + !!startBtn);
      record('visual-fallback: queue_for_later button present',
        !!queueBtn, 'btn=' + !!queueBtn);
      record('visual-fallback: dismiss button present',
        !!dismissBtn, 'btn=' + !!dismissBtn);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-fallback: overlay markup', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── 2. user_message rendered verbatim ────────────────────────────────
    try {
      var div = mkDiv(win);
      var panel = new win.VisualPanel(div, { id: 'vf-2' });
      panel.init();
      var custom = 'Custom fallback prompt for test vf-2.';
      panel.showFallbackPrompt(makeAlert({ user_message: custom }));
      var body = div.querySelector('.visual-panel__fallback-body');
      record('visual-fallback: user_message lands in body',
        body && body.textContent === custom,
        'body=' + (body && body.textContent));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-fallback: user_message', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── 3. Meta line shows parse_errors + extractor ──────────────────────
    try {
      var div = mkDiv(win);
      var panel = new win.VisualPanel(div, { id: 'vf-3' });
      panel.init();
      panel.showFallbackPrompt(makeAlert({
        extractor_attempted: 'api-claude',
        parse_errors: ['unexpected eof'],
      }));
      var meta = div.querySelector('.visual-panel__fallback-meta');
      record('visual-fallback: meta line visible when fields present',
        meta && !meta.hidden, 'hidden=' + (meta && meta.hidden));
      var metaText = meta ? meta.textContent : '';
      record('visual-fallback: meta line mentions api-claude',
        metaText.indexOf('api-claude') >= 0, 'meta=' + metaText);
      record('visual-fallback: meta line mentions unexpected eof',
        metaText.indexOf('unexpected eof') >= 0, 'meta=' + metaText);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-fallback: meta line', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── 4. Meta line hides when no extractor + no parse_errors ──────────
    try {
      var div = mkDiv(win);
      var panel = new win.VisualPanel(div, { id: 'vf-4' });
      panel.init();
      panel.showFallbackPrompt(makeAlert({
        reason: 'no_vision_available',
        extractor_attempted: null,
        parse_errors: [],
      }));
      var meta = div.querySelector('.visual-panel__fallback-meta');
      // Meta may still render with `reason` (we include it), but should not
      // reference a tried extractor or parse error.
      var text = meta ? meta.textContent : '';
      record('visual-fallback: meta omits Tried when extractor is null',
        text.indexOf('Tried:') < 0, 'meta=' + text);
      record('visual-fallback: meta omits Parse error when none present',
        text.indexOf('Parse error:') < 0, 'meta=' + text);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-fallback: meta hidden path', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── 5. Overlay hides after dismiss ───────────────────────────────────
    try {
      var div = mkDiv(win);
      var panel = new win.VisualPanel(div, { id: 'vf-5' });
      panel.init();
      panel.showFallbackPrompt(makeAlert());
      var overlay = div.querySelector('.visual-panel__fallback-overlay');
      record('visual-fallback: overlay visible after show',
        overlay && overlay.hidden === false,
        'hidden=' + (overlay && overlay.hidden));
      panel.dismissFallbackPrompt();
      record('visual-fallback: overlay hidden after dismiss',
        overlay && overlay.hidden === true,
        'hidden=' + (overlay && overlay.hidden));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-fallback: dismiss hide', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── 6. Dismiss button click — no side effects ────────────────────────
    try {
      var div = mkDiv(win);
      var panel = new win.VisualPanel(div, { id: 'vf-6' });
      panel.init();
      var toolBefore = panel.getActiveTool();
      panel.showFallbackPrompt(makeAlert());
      var dismissBtn = div.querySelector('.visual-panel__fallback-btn[data-action="dismiss"]');
      dismissBtn.click();
      var overlay = div.querySelector('.visual-panel__fallback-overlay');
      record('visual-fallback: dismiss button hides overlay',
        overlay.hidden === true, 'hidden=' + overlay.hidden);
      record('visual-fallback: dismiss button does not change active tool',
        panel.getActiveTool() === toolBefore,
        'before=' + toolBefore + ' after=' + panel.getActiveTool());
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-fallback: dismiss click', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── 7. Start tracing — selects rect tool + dismisses ─────────────────
    try {
      var div = mkDiv(win);
      var panel = new win.VisualPanel(div, { id: 'vf-7' });
      panel.init();
      // Default active tool is 'select'.
      record('visual-fallback: pre-state is select tool',
        panel.getActiveTool() === 'select',
        'active=' + panel.getActiveTool());
      panel.showFallbackPrompt(makeAlert());
      var startBtn = div.querySelector('.visual-panel__fallback-btn[data-action="start_tracing"]');
      startBtn.click();
      record('visual-fallback: start_tracing switches to rect tool',
        panel.getActiveTool() === 'rect',
        'active=' + panel.getActiveTool());
      var overlay = div.querySelector('.visual-panel__fallback-overlay');
      record('visual-fallback: start_tracing dismisses overlay',
        overlay.hidden === true, 'hidden=' + overlay.hidden);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-fallback: start_tracing click', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── 8. Queue for later — POSTs to /chat/queue-retry ──────────────────
    try {
      var div = mkDiv(win);
      var panel = new win.VisualPanel(div, { id: 'vf-8' });
      panel.init();
      var calls = installMockFetch(win, { ok: true, body: { queued: true, queue_size: 3 } });
      panel.showFallbackPrompt(makeAlert({ conversation_id: 'c-8' }));
      var queueBtn = div.querySelector('.visual-panel__fallback-btn[data-action="queue_for_later"]');
      queueBtn.click();
      // Wait for fetch promise chain to settle + dismiss setTimeout.
      await tick(30);
      record('visual-fallback: queue_for_later called fetch once',
        calls.length === 1, 'calls=' + calls.length);
      var call = calls[0] || {};
      record('visual-fallback: fetch target is /chat/queue-retry',
        call.url === '/chat/queue-retry', 'url=' + call.url);
      record('visual-fallback: fetch method is POST',
        call.init && call.init.method === 'POST',
        'method=' + (call.init && call.init.method));
      var bodyObj = {};
      try { bodyObj = JSON.parse(call.init && call.init.body || '{}'); } catch (e) {}
      record('visual-fallback: body carries conversation_id',
        bodyObj.conversation_id === 'c-8',
        'cid=' + bodyObj.conversation_id);
      record('visual-fallback: body carries attempt_reason from alert.reason',
        bodyObj.attempt_reason === 'extraction_failed',
        'reason=' + bodyObj.attempt_reason);
      record('visual-fallback: body carries a non-empty image_path',
        typeof bodyObj.image_path === 'string' && bodyObj.image_path.length > 0,
        'image_path=' + bodyObj.image_path);
      // After the success note timeout (900ms), overlay should be dismissed.
      // Wait long enough.
      await tick(1100);
      var overlay = div.querySelector('.visual-panel__fallback-overlay');
      record('visual-fallback: queue_for_later dismisses overlay on success',
        overlay.hidden === true, 'hidden=' + overlay.hidden);
      panel.destroy();
      win.document.body.removeChild(div);
      delete win.fetch;
    } catch (err) {
      record('visual-fallback: queue_for_later click', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── 9. Queue-for-later surfaces status note before dismissing ────────
    try {
      var div = mkDiv(win);
      var panel = new win.VisualPanel(div, { id: 'vf-9' });
      panel.init();
      installMockFetch(win, { ok: true, body: { queued: true, queue_size: 7 } });
      panel.showFallbackPrompt(makeAlert({ conversation_id: 'c-9' }));
      var queueBtn = div.querySelector('.visual-panel__fallback-btn[data-action="queue_for_later"]');
      queueBtn.click();
      // Immediately after click: note shows "Queueing…".
      var note = div.querySelector('.visual-panel__fallback-note');
      record('visual-fallback: note shows Queueing text immediately',
        note && note.textContent.indexOf('Queueing') >= 0,
        'note=' + (note && note.textContent));
      // After fetch promise settles: note updates to the queued message.
      await tick(30);
      record('visual-fallback: note updates to queued count',
        note && note.textContent.indexOf('Queued') >= 0
             && note.textContent.indexOf('7') >= 0,
        'note=' + (note && note.textContent));
      panel.destroy();
      win.document.body.removeChild(div);
      delete win.fetch;
    } catch (err) {
      record('visual-fallback: queue status note', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── 10-11. OraPanels.visual routes to active instance ────────────────
    try {
      var div = mkDiv(win);
      var panel = new win.VisualPanel(div, { id: 'vf-10' });
      panel.init();
      // The class-level init hook registers the active instance.
      record('visual-fallback: OraPanels.visual.showFallbackPrompt is a fn',
        typeof win.OraPanels.visual.showFallbackPrompt === 'function',
        'type=' + typeof win.OraPanels.visual.showFallbackPrompt);
      record('visual-fallback: OraPanels.visual.dismissFallbackPrompt is a fn',
        typeof win.OraPanels.visual.dismissFallbackPrompt === 'function',
        'type=' + typeof win.OraPanels.visual.dismissFallbackPrompt);
      win.OraPanels.visual.showFallbackPrompt(makeAlert());
      var overlay = div.querySelector('.visual-panel__fallback-overlay');
      record('visual-fallback: OraPanels.visual.showFallbackPrompt shows overlay',
        overlay && overlay.hidden === false, 'hidden=' + (overlay && overlay.hidden));
      win.OraPanels.visual.dismissFallbackPrompt();
      record('visual-fallback: OraPanels.visual.dismissFallbackPrompt hides overlay',
        overlay && overlay.hidden === true, 'hidden=' + (overlay && overlay.hidden));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-fallback: OraPanels.visual surface', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── 12. Subsequent show calls update in place ───────────────────────
    try {
      var div = mkDiv(win);
      var panel = new win.VisualPanel(div, { id: 'vf-12' });
      panel.init();
      panel.showFallbackPrompt(makeAlert({ user_message: 'First call' }));
      panel.showFallbackPrompt(makeAlert({ user_message: 'Second call' }));
      var overlays = div.querySelectorAll('.visual-panel__fallback-overlay');
      record('visual-fallback: second show does not duplicate overlay DOM',
        overlays.length === 1, 'count=' + overlays.length);
      var body = div.querySelector('.visual-panel__fallback-body');
      record('visual-fallback: second show updates body text',
        body && body.textContent === 'Second call',
        'body=' + (body && body.textContent));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-fallback: subsequent show', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── 13. Restricted action set hides unadvertised buttons ─────────────
    try {
      var div = mkDiv(win);
      var panel = new win.VisualPanel(div, { id: 'vf-13' });
      panel.init();
      panel.showFallbackPrompt(makeAlert({ actions: ['dismiss'] }));
      var startBtn = div.querySelector('.visual-panel__fallback-btn[data-action="start_tracing"]');
      var queueBtn = div.querySelector('.visual-panel__fallback-btn[data-action="queue_for_later"]');
      var dismissBtn = div.querySelector('.visual-panel__fallback-btn[data-action="dismiss"]');
      record('visual-fallback: start button hidden when not advertised',
        startBtn && startBtn.hidden === true,
        'hidden=' + (startBtn && startBtn.hidden));
      record('visual-fallback: queue button hidden when not advertised',
        queueBtn && queueBtn.hidden === true,
        'hidden=' + (queueBtn && queueBtn.hidden));
      record('visual-fallback: dismiss button visible when advertised',
        dismissBtn && dismissBtn.hidden === false,
        'hidden=' + (dismissBtn && dismissBtn.hidden));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-fallback: restricted actions', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── 14. Defensive no-op on bad input ─────────────────────────────────
    try {
      var div = mkDiv(win);
      var panel = new win.VisualPanel(div, { id: 'vf-14' });
      panel.init();
      // Nothing rendered yet.
      record('visual-fallback: no overlay before any show',
        !div.querySelector('.visual-panel__fallback-overlay'),
        'pre=' + !!div.querySelector('.visual-panel__fallback-overlay'));
      // Non-object inputs must be silently ignored.
      panel.showFallbackPrompt(null);
      panel.showFallbackPrompt(undefined);
      panel.showFallbackPrompt('nope');
      panel.showFallbackPrompt(42);
      var overlay = div.querySelector('.visual-panel__fallback-overlay');
      record('visual-fallback: bad inputs do not render overlay',
        !overlay, 'overlay=' + !!overlay);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('visual-fallback: defensive no-op', false,
        'threw: ' + (err.stack || err.message || err));
    }

    // ── 15. queue_for_later with no fetch surfaces failure + dismisses ──
    try {
      var div = mkDiv(win);
      var panel = new win.VisualPanel(div, { id: 'vf-15' });
      panel.init();
      // Remove fetch on the jsdom window + global scope so _queueForRetry
      // can't find one. Our implementation checks window.fetch, then
      // global fetch — stub both.
      var savedFetch = win.fetch;
      win.fetch = undefined;
      var savedGlobal = global.fetch;
      global.fetch = undefined;
      panel.showFallbackPrompt(makeAlert({ conversation_id: 'c-15' }));
      var queueBtn = div.querySelector('.visual-panel__fallback-btn[data-action="queue_for_later"]');
      queueBtn.click();
      var note = div.querySelector('.visual-panel__fallback-note');
      record('visual-fallback: no-fetch path sets failure note',
        note && /Queue unavailable|Queue request failed/.test(note.textContent || ''),
        'note=' + (note && note.textContent));
      // After the 600ms setTimeout: overlay dismissed.
      await tick(800);
      var overlay = div.querySelector('.visual-panel__fallback-overlay');
      record('visual-fallback: no-fetch path dismisses overlay',
        overlay && overlay.hidden === true,
        'hidden=' + (overlay && overlay.hidden));
      panel.destroy();
      win.document.body.removeChild(div);
      win.fetch = savedFetch;
      global.fetch = savedGlobal;
    } catch (err) {
      record('visual-fallback: no-fetch path', false,
        'threw: ' + (err.stack || err.message || err));
    }
  },
};
