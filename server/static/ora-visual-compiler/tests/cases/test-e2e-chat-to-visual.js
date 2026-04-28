/**
 * tests/cases/test-e2e-chat-to-visual.js — WP-2.3 end-to-end integration.
 *
 * Exercises the full ora-visual path on the client side:
 *
 *   fake SSE response
 *        │
 *        ▼
 *   extractVisualBlocks(text)           ─ chat-panel.js helper
 *        │
 *        ▼
 *   visual panel .onBridgeUpdate(...)   ─ visual-panel.js contract
 *        │  (state.ora_visual_blocks = [{ envelope, raw_json, source_message_id }])
 *        ▼
 *   compileWithNav(envelope)            ─ ora-visual-compiler public API
 *        │
 *        ▼
 *   installed SVG in panel._svgHost     ─ assert type class present + non-empty
 *
 * Asserts are framed to isolate each stage so regressions can be pinpointed.
 */

'use strict';

const fs   = require('fs');
const path = require('path');
const vm   = require('vm');

function mkDiv(win) {
  const d = win.document.createElement('div');
  d.style.cssText = 'width:600px;height:400px;';
  win.document.body.appendChild(d);
  return d;
}

function wait(ms) { return new Promise((r) => setTimeout(r, ms)); }

/**
 * Build a fake SSE-response text payload containing a Systems Dynamics style
 * CLD fenced block. Mirrors the shape the orchestrator emits when routing
 * through Systems Dynamics mode.
 */
function fakeSsePayload(ctx, { extraPrefix = '', extraSuffix = '', id = 'fig-e2e-cld' } = {}) {
  const examplesDir = (ctx && ctx.EXAMPLES_DIR) ||
    path.resolve(__dirname, '..', '..', '..', '..', '..', 'config', 'visual-schemas', 'examples');
  const envPath = path.join(examplesDir, 'causal_loop_diagram.valid.json');
  const env = JSON.parse(fs.readFileSync(envPath, 'utf-8'));
  env.id = id;
  const json = JSON.stringify(env, null, 2);
  const prose =
    'Here is the causal loop diagram for the velocity / tech debt / fires system:\n\n' +
    extraPrefix +
    '```ora-visual\n' + json + '\n```\n\n' +
    extraSuffix +
    'The B1 loop balances short-term velocity against accumulated tech debt. ' +
    'When velocity rises, tech debt accumulates (positive link), which causes ' +
    'more fires (positive link), which forces velocity down (negative link) — ' +
    'a classic limits-to-growth archetype.';
  return { envelope: env, prose };
}

/**
 * Port of chat-panel._dispatchVisualBlocks minus DOM side-effects — just the
 * block packaging + bridge-style object construction. We exercise the
 * browser's extractor through window.extractVisualBlocks so we're testing
 * the actual exported surface, not a local copy.
 */
function packageBlocks(win, text, panelId) {
  const raw = win.extractVisualBlocks(text);
  const sourceId = panelId + '-msg-e2e';
  const blocks = [];
  const errors = [];
  for (const entry of raw) {
    if (entry.envelope) {
      blocks.push({
        envelope: entry.envelope,
        raw_json: entry.raw_json,
        source_message_id: sourceId,
      });
    } else {
      errors.push(entry.parse_error || 'Malformed ora-visual JSON');
    }
  }
  return { blocks, errors };
}

module.exports = {
  label: 'WP-2.3 — chat SSE → extraction → bridge → visual panel render (end-to-end)',
  run: async function run(ctx, record) {
    const { win } = ctx;

    // Bootstrap check: the chat-panel.js module must have been loaded so
    // window.extractVisualBlocks exists. The harness loads it at boot.
    record(
      'e2e: harness — chat-panel extractVisualBlocks exposed',
      typeof win.extractVisualBlocks === 'function',
      'typeof=' + typeof win.extractVisualBlocks,
    );
    record(
      'e2e: harness — Konva + VisualPanel loaded',
      typeof win.Konva === 'object' && typeof win.VisualPanel === 'function',
      'Konva=' + typeof win.Konva + ' VisualPanel=' + typeof win.VisualPanel,
    );
    record(
      'e2e: harness — OraVisualCompiler.compileWithNav available',
      !!(win.OraVisualCompiler && typeof win.OraVisualCompiler.compileWithNav === 'function'),
      win.OraVisualCompiler ? Object.keys(win.OraVisualCompiler).join(',') : '(missing)',
    );

    if (typeof win.extractVisualBlocks !== 'function' ||
        typeof win.VisualPanel !== 'function' ||
        !win.OraVisualCompiler || typeof win.OraVisualCompiler.compileWithNav !== 'function') {
      record('e2e: unable to run end-to-end suite', false, 'missing harness prerequisites');
      return;
    }

    // ── Test 1: extractVisualBlocks parses a single ora-visual fence ────────
    try {
      const { envelope, prose } = fakeSsePayload(ctx, { id: 'fig-e2e-1' });
      const raw = win.extractVisualBlocks(prose);
      record(
        'e2e: extractVisualBlocks finds exactly one block in CLD-style SSE',
        Array.isArray(raw) && raw.length === 1,
        'found ' + (raw ? raw.length : 'null'),
      );
      record(
        'e2e: extracted envelope round-trips through JSON.parse',
        raw && raw[0] && raw[0].envelope && raw[0].envelope.id === 'fig-e2e-1'
          && raw[0].envelope.type === 'causal_loop_diagram',
        raw && raw[0] && raw[0].envelope ? raw[0].envelope.type : '(no envelope)',
      );
      record(
        'e2e: extracted raw_json preserves source for copy-to-clipboard UX',
        raw && raw[0] && typeof raw[0].raw_json === 'string' && raw[0].raw_json.indexOf('"causal_loop_diagram"') >= 0,
        raw && raw[0] ? 'raw_json length=' + (raw[0].raw_json || '').length : 'no raw_json',
      );
    } catch (err) {
      record('e2e: extract single block', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── Test 2: malformed fence produces parse_error, envelope=null ─────────
    try {
      const badText = 'Prose leading in.\n\n```ora-visual\n{ "type": broken json, }\n```\n\nTrailing.';
      const raw = win.extractVisualBlocks(badText);
      record(
        'e2e: malformed JSON in fence produces a parse_error entry',
        raw.length === 1 && raw[0].envelope === null && typeof raw[0].parse_error === 'string',
        raw.length === 1 ? 'parse_error=' + (raw[0].parse_error || '') : 'len=' + raw.length,
      );
    } catch (err) {
      record('e2e: malformed fence handling', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── Test 3: multiple fences in one message all extract ──────────────────
    try {
      const { envelope: e1, prose: p1 } = fakeSsePayload(ctx, { id: 'fig-e2e-3a' });
      const { envelope: e2 } = fakeSsePayload(ctx, { id: 'fig-e2e-3b' });
      const combined = p1 + '\n\nMore prose.\n\n```ora-visual\n' + JSON.stringify(e2) + '\n```';
      const raw = win.extractVisualBlocks(combined);
      record(
        'e2e: multiple fences each produce an entry in document order',
        raw.length === 2
          && raw[0].envelope.id === 'fig-e2e-3a'
          && raw[1].envelope.id === 'fig-e2e-3b',
        'ids=' + raw.map(function (r) { return r.envelope && r.envelope.id; }).join(','),
      );
    } catch (err) {
      record('e2e: multi-block extract', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── Test 4: bridge dispatch → visual panel onBridgeUpdate ───────────────
    let panel, div;
    try {
      div = mkDiv(win);
      panel = new win.VisualPanel(div, { id: 'e2e-panel' });
      panel.init();

      // Spy on renderSpec so we can confirm it was called with the expected
      // envelope identity.
      const origRenderSpec = panel.renderSpec.bind(panel);
      let lastCalledWith = null;
      let callCount = 0;
      panel.renderSpec = function (env) {
        lastCalledWith = env;
        callCount += 1;
        return origRenderSpec(env);
      };

      const { prose } = fakeSsePayload(ctx, { id: 'fig-e2e-4' });
      const { blocks, errors } = packageBlocks(win, prose, 'e2e-panel');

      record(
        'e2e: packaged block has envelope + raw_json + source_message_id',
        blocks.length === 1
          && blocks[0].envelope && blocks[0].envelope.id === 'fig-e2e-4'
          && typeof blocks[0].raw_json === 'string'
          && typeof blocks[0].source_message_id === 'string',
        'block keys=' + (blocks[0] ? Object.keys(blocks[0]).join(',') : 'n/a'),
      );
      record('e2e: clean extraction produces zero parse_errors', errors.length === 0,
        'errors=' + errors.length);

      // Fire bridge update — visual panel re-reads state.ora_visual_blocks.
      panel.onBridgeUpdate({ ora_visual_blocks: blocks, source_panel_id: 'main' });
      await wait(25); // compileWithNav is async (CLD uses D3 layout)

      record(
        'e2e: onBridgeUpdate dispatches to renderSpec',
        callCount === 1 && lastCalledWith && lastCalledWith.id === 'fig-e2e-4',
        'callCount=' + callCount + ' lastId=' + (lastCalledWith ? lastCalledWith.id : 'null'),
      );

      // Observe the installed SVG.
      const svgEl = div.querySelector('.visual-panel__svg-host svg');
      record(
        'e2e: SVG installed into visual-panel svg-host',
        !!svgEl,
        svgEl ? ('nodeName=' + svgEl.nodeName) : 'no svg',
      );
      record(
        'e2e: SVG has non-empty content (children)',
        !!svgEl && svgEl.childNodes.length > 0,
        svgEl ? ('children=' + svgEl.childNodes.length) : 'no svg',
      );

      // The CLD renderer emits `ora-visual--causal_loop_diagram` on the root.
      // (Registered in ora-visual-theme.css + the renderer adds the class to
      // its root <svg>.) Accept the class anywhere on root or inside.
      let classMatch = false;
      if (svgEl) {
        const rootClasses = svgEl.getAttribute('class') || '';
        if (rootClasses.indexOf('ora-visual--causal_loop_diagram') >= 0
            || rootClasses.indexOf('ora-visual--causal-loop-diagram') >= 0) {
          classMatch = true;
        } else {
          // Fall back: any descendant carrying the type class
          const tagged = svgEl.querySelector('[class*="ora-visual--causal_loop_diagram"],'
                                            + '[class*="ora-visual--causal-loop-diagram"]');
          classMatch = !!tagged;
        }
      }
      record(
        'e2e: installed SVG carries the ora-visual--causal_loop_diagram class',
        classMatch,
        svgEl ? ('root class="' + (svgEl.getAttribute('class') || '') + '"') : 'no svg',
      );

      // Confirm the panel recorded the envelope
      record(
        'e2e: panel._currentEnvelope reflects the rendered envelope',
        panel._currentEnvelope && panel._currentEnvelope.id === 'fig-e2e-4',
        panel._currentEnvelope ? panel._currentEnvelope.id : 'null',
      );
    } catch (err) {
      record('e2e: bridge → panel render', false, 'threw: ' + (err.stack || err.message || err));
    } finally {
      try { if (panel) panel.destroy(); } catch (e) {}
      try { if (div) div.parentNode && div.parentNode.removeChild(div); } catch (e) {}
    }

    // ── Test 5: "last wins" when multiple blocks arrive together ────────────
    try {
      div = mkDiv(win);
      panel = new win.VisualPanel(div, { id: 'e2e-panel-last' });
      panel.init();
      const { envelope: e1 } = fakeSsePayload(ctx, { id: 'fig-e2e-last-a' });
      const { envelope: e2 } = fakeSsePayload(ctx, { id: 'fig-e2e-last-b' });
      const combined = 'Intro.\n\n```ora-visual\n' + JSON.stringify(e1) + '\n```\n\n'
                     + 'Middle.\n\n```ora-visual\n' + JSON.stringify(e2) + '\n```\n\nTail.';
      const raw = win.extractVisualBlocks(combined);
      record('e2e: multi-block extract count = 2', raw.length === 2, 'got ' + raw.length);

      panel.onBridgeUpdate({
        ora_visual_blocks: raw.map(function (r) {
          return { envelope: r.envelope, raw_json: r.raw_json, source_message_id: 'e2e-multi' };
        }),
      });
      await wait(25);

      record(
        'e2e: last block wins when multiple blocks arrive in one update',
        panel._currentEnvelope && panel._currentEnvelope.id === 'fig-e2e-last-b',
        panel._currentEnvelope ? panel._currentEnvelope.id : 'null',
      );
    } catch (err) {
      record('e2e: multi-block last-wins', false, 'threw: ' + (err.stack || err.message || err));
    } finally {
      try { if (panel) panel.destroy(); } catch (e) {}
      try { if (div) div.parentNode && div.parentNode.removeChild(div); } catch (e) {}
    }

    // ── Test 6: empty text → no-op extraction ──────────────────────────────
    try {
      const rawEmpty   = win.extractVisualBlocks('');
      const rawProse   = win.extractVisualBlocks('Just prose, no fences.');
      const rawPartial = win.extractVisualBlocks('```ora-visual\n{ "unterminated"'); // no closing ```
      record(
        'e2e: empty / prose-only / unterminated strings → empty array',
        Array.isArray(rawEmpty) && rawEmpty.length === 0
          && Array.isArray(rawProse) && rawProse.length === 0
          && Array.isArray(rawPartial) && rawPartial.length === 0,
        'lengths=' + [rawEmpty.length, rawProse.length, rawPartial.length].join(','),
      );
    } catch (err) {
      record('e2e: empty extract', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── Test 7: OraPanels.visual.onBridgeUpdate reaches the active panel ───
    try {
      div = mkDiv(win);
      panel = new win.VisualPanel(div, { id: 'e2e-panel-opv' });
      panel.init();
      const { envelope, prose } = fakeSsePayload(ctx, { id: 'fig-e2e-opv' });
      const { blocks } = packageBlocks(win, prose, 'e2e-panel-opv');
      win.OraPanels.visual.onBridgeUpdate({ ora_visual_blocks: blocks });
      await wait(25);
      record(
        'e2e: OraPanels.visual.onBridgeUpdate routes bridge state to active panel',
        panel._currentEnvelope && panel._currentEnvelope.id === 'fig-e2e-opv',
        panel._currentEnvelope ? panel._currentEnvelope.id : 'null',
      );
    } catch (err) {
      record('e2e: OraPanels.visual dispatch', false, 'threw: ' + (err.stack || err.message || err));
    } finally {
      try { if (panel) panel.destroy(); } catch (e) {}
      try { if (div) div.parentNode && div.parentNode.removeChild(div); } catch (e) {}
    }
  },
};
