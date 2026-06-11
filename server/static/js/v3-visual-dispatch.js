/**
 * v3-visual-dispatch.js — model-emitted ora-visual envelopes → visual pane.
 *
 * The classic UI's chat panel owned this job: spot ```ora-visual fenced
 * JSON blocks in assistant replies, parse them, and hand them to the
 * visual panel. V3 retired that module without a replacement, so envelopes
 * rendered as raw JSON code blocks in the transcript and the panel's
 * renderSpec path never fired (2026-06-11 audit finding).
 *
 * This module is the V3 replacement. v3-conversation.js calls
 * `dispatch(text, key)` whenever it renders an assistant turn; the last
 * envelope in the text is applied to the active visual panel through
 * `OraPanels.visual.onBridgeUpdate`, which runs the canvas_action state
 * machine (replace / update / annotate / clear — user drawings survive
 * everything except an explicit replace/clear). `stripBlocks` swaps the
 * raw JSON fences for a one-line marker so the transcript stays readable.
 *
 * The `key` argument deduplicates: renderAll() re-renders the same turn
 * on header refreshes and the same envelope must not re-fire (it would
 * bump the panel's conversation-turn counter and flip update semantics).
 * Navigating away and back produces a fresh render of that turn's
 * diagram by design — the key tracks (conversation, turn), not content.
 */
(() => {
  'use strict';

  // Same fence grammar the classic extractor used (WP-2.3): opening fence
  // tagged ora-visual, JSON payload, closing fence on its own line.
  const FENCE_RE = /```ora-visual\s*\n([\s\S]*?)\n[ \t]*```/g;

  const PLACEHOLDER = '*\u{1F4CA} Diagram rendered in the visual pane.*';

  let _lastKey = null;

  /** Extract every parseable ora-visual block. Unparseable JSON is
   *  skipped (the raw fence stays visible in the transcript so the
   *  failure is inspectable rather than silently swallowed). */
  function extractBlocks(text) {
    if (typeof text !== 'string' || text.indexOf('ora-visual') === -1) return [];
    const blocks = [];
    let m;
    FENCE_RE.lastIndex = 0;
    while ((m = FENCE_RE.exec(text)) !== null) {
      try {
        const envelope = JSON.parse(m[1]);
        if (envelope && typeof envelope === 'object') {
          blocks.push({ envelope: envelope, raw_json: m[1] });
        }
      } catch (e) { /* leave malformed fence in place */ }
    }
    return blocks;
  }

  /** Replace each PARSEABLE ora-visual fence with the placeholder line.
   *  Malformed fences are left untouched. */
  function stripBlocks(text) {
    if (typeof text !== 'string' || text.indexOf('ora-visual') === -1) return text;
    return text.replace(FENCE_RE, (full, payload) => {
      try {
        JSON.parse(payload);
        return PLACEHOLDER;
      } catch (e) {
        return full;
      }
    });
  }

  /** Extract + hand off to the visual panel. Returns the number of blocks
   *  found (0 = nothing to do). Same key twice in a row is a no-op. */
  function dispatch(text, key) {
    const blocks = extractBlocks(text);
    if (blocks.length === 0) return 0;
    if (key != null && key === _lastKey) return blocks.length;
    const panel = window.OraPanels && window.OraPanels.visual;
    if (!panel || typeof panel.onBridgeUpdate !== 'function') return blocks.length;
    _lastKey = key != null ? key : null;
    try {
      panel.onBridgeUpdate({ ora_visual_blocks: blocks });
    } catch (e) {
      console.warn('[v3-visual-dispatch] panel dispatch failed:', e);
    }
    return blocks.length;
  }

  /** Test hook: forget the dedupe key. */
  function resetDedupe() { _lastKey = null; }

  window.OraV3VisualDispatch = {
    extractBlocks: extractBlocks,
    stripBlocks: stripBlocks,
    dispatch: dispatch,
    resetDedupe: resetDedupe,
    PLACEHOLDER: PLACEHOLDER,
  };
})();
