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
 * `dispatch(text, key)` whenever it renders an assistant turn; every
 * envelope in the text is applied to the active visual panel through
 * `OraPanels.visual.onBridgeUpdate`, which runs the active editor's
 * canvas_action state machine. `stripBlocks` swaps the raw JSON fences for
 * a neutral handoff marker; completion or rejection is reported separately
 * so the transcript never claims an unsupported action rendered.
 *
 * The `key` argument deduplicates: renderAll() re-renders the same turn
 * on header refreshes and the same envelope must not re-fire (it would
 * bump the panel's conversation-turn counter and flip update semantics).
 * Navigating away and back produces a fresh render of that turn's
 * diagram by design — the key tracks (conversation, turn), not content.
 */
(() => {
  'use strict';

  // Opening fence tagged ora-visual, JSON payload, closing fence on its own
  // line. The payload may not contain a fence line: an ora-visual body is
  // JSON, so a run of backticks inside it always means the opening fence was
  // never terminated. Without that guard the non-greedy body runs on to the
  // next unrelated block's fence, and `stripBlocks` then replaces all of the
  // prose in between with the handoff placeholder. Mirrors
  // `visual_recovery.ORA_VISUAL_FENCE_RE` on the server side.
  const FENCE_RE = /```ora-visual[ \t]*\n((?:(?![ \t]*```)[^\n]*\n)*?)[ \t]*```+[ \t]*(?=\n|$)/g;
  const IMAGE_FENCE_RE = /```ora-image[ \t]*\n((?:(?![ \t]*```)[^\n]*\n)*?)[ \t]*```+[ \t]*(?=\n|$)/g;

  const PLACEHOLDER = '*\u{1F4CA} Visual request sent to the Exhibits pane.*';

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

  function extractImageBlocks(text) {
    if (typeof text !== 'string' || text.indexOf('ora-image') === -1) return [];
    const blocks = [];
    let m;
    IMAGE_FENCE_RE.lastIndex = 0;
    while ((m = IMAGE_FENCE_RE.exec(text)) !== null) {
      try {
        const artifact = JSON.parse(m[1]);
        if (artifact
            && artifact.schema_version === 'ora.image-artifact/1.0'
            && typeof artifact.url === 'string'
            && artifact.url.startsWith('/api/conversation/')
            && typeof artifact.mime_type === 'string'
            && artifact.mime_type.startsWith('image/')) {
          blocks.push({ artifact, raw_json: m[1] });
        }
      } catch (e) { /* leave malformed fence visible */ }
    }
    return blocks;
  }

  /** Replace each PARSEABLE ora-visual fence with the placeholder line.
   *  Malformed fences are left untouched. */
  function stripBlocks(text) {
    if (typeof text !== 'string') return text;
    let stripped = text.replace(FENCE_RE, (full, payload) => {
      try {
        JSON.parse(payload);
        return PLACEHOLDER;
      } catch (e) {
        return full;
      }
    });
    stripped = stripped.replace(IMAGE_FENCE_RE, (full, payload) => {
      try {
        const artifact = JSON.parse(payload);
        return artifact && artifact.schema_version === 'ora.image-artifact/1.0'
          ? PLACEHOLDER : full;
      } catch (e) {
        return full;
      }
    });
    return stripped;
  }

  function persistOutcome(meta, outcome) {
    if (!meta || !meta.conversationId || typeof window.fetch !== 'function') return;
    const body = Object.assign({}, outcome, {
      assistant_index: Number.isInteger(meta.assistantIndex)
        ? meta.assistantIndex : undefined,
    });
    Object.keys(body).forEach((key) => body[key] === undefined && delete body[key]);
    try {
      window.fetch(`/api/conversation/${encodeURIComponent(meta.conversationId)}/visual-outcome`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }).catch((error) => console.warn('[v3-visual-dispatch] outcome save failed:', error));
    } catch (error) {
      console.warn('[v3-visual-dispatch] outcome save failed:', error);
    }
  }

  function surfaceDispatchFailure(message, meta) {
    const detail = message || 'The visual request could not be applied.';
    console.warn('[v3-visual-dispatch] ' + detail);
    const panel = window.OraPanels && window.OraPanels.visual;
    if (panel && typeof panel.showError === 'function') {
      panel.showError('Visual failed: ' + detail);
    }
    persistOutcome(meta, {
      state: 'failed',
      stage: 'dispatch',
      reason: detail,
    });
  }

  function surfaceDispatchResult(result, meta) {
    const results = Array.isArray(result) ? result : [result];
    const unsupported = results.filter((item) => item && item.unsupported === true);
    if (unsupported.length === 0) {
      const ready = { state: 'ready' };
      const prior = meta && meta.visualOutcome;
      ['stage', 'reason', 'origin', 'trace_ref'].forEach((key) => {
        if (prior && typeof prior[key] === 'string' && prior[key]) ready[key] = prior[key];
      });
      persistOutcome(meta, ready);
      return;
    }
    const warnings = [];
    unsupported.forEach((item) => {
      (Array.isArray(item.warnings) ? item.warnings : []).forEach((warning) => {
        if (typeof warning === 'string' && warning && !warnings.includes(warning)) {
          warnings.push(warning);
        }
      });
    });
    surfaceDispatchFailure(
      warnings.join('\n') || 'This visual action is not supported by the active editor.'
      , meta
    );
  }

  async function insertImageArtifacts(blocks) {
    if (!window.OraCanvas
        || typeof window.OraCanvas.insertAssistantImage !== 'function') {
      throw new Error('The Exhibits image inserter is unavailable.');
    }
    const inserted = [];
    for (const block of blocks) {
      const artifact = block.artifact;
      const response = await window.fetch(artifact.url, {
        method: 'GET', credentials: 'same-origin',
      });
      if (!response.ok) {
        throw new Error(`Stored image could not be loaded (HTTP ${response.status}).`);
      }
      const blob = await response.blob();
      if (!blob || !String(blob.type || artifact.mime_type).startsWith('image/')) {
        throw new Error('Stored image response was not an image.');
      }
      const file = new File(
        [blob], artifact.filename || 'generated-image',
        { type: blob.type || artifact.mime_type },
      );
      const placed = await window.OraCanvas.insertAssistantImage(file, artifact);
      if (!placed) throw new Error('The Exhibits pane rejected the generated image.');
      inserted.push(placed);
    }
    return inserted;
  }

  /** Extract + hand off to the visual panel. Returns the number of blocks
   *  found (0 = nothing to do). Same key twice in a row is a no-op. */
  function dispatch(text, key, meta) {
    const blocks = extractBlocks(text);
    const imageBlocks = extractImageBlocks(text);
    const blockCount = blocks.length + imageBlocks.length;
    if (blockCount === 0) return 0;
    if (key != null && key === _lastKey) return blockCount;
    const panel = window.OraPanels && window.OraPanels.visual;
    if (blocks.length && (!panel || typeof panel.onBridgeUpdate !== 'function')) {
      surfaceDispatchFailure('The Exhibits pane is unavailable.', meta);
      return blockCount;
    }
    _lastKey = key != null ? key : null;
    if (imageBlocks.length) {
      const operations = [insertImageArtifacts(imageBlocks)];
      if (blocks.length) {
        try {
          operations.push(Promise.resolve(panel.onBridgeUpdate({
            ora_visual_blocks: blocks,
            ora_visual_dispatch_key: key != null ? String(key) : null,
          })));
        } catch (error) {
          operations.push(Promise.reject(error));
        }
      }
      Promise.all(operations).then((values) => {
        surfaceDispatchResult(values.flat(), meta);
      }).catch((error) => {
        surfaceDispatchFailure(
          'The visual request could not be applied: ' + (error && error.message || error),
          meta,
        );
      });
      return blockCount;
    }
    try {
      const result = panel.onBridgeUpdate({
        ora_visual_blocks: blocks,
        ora_visual_dispatch_key: key != null ? String(key) : null,
      });
      if (result && typeof result.then === 'function') {
        Promise.resolve(result).then((value) => surfaceDispatchResult(value, meta)).catch((error) => {
          surfaceDispatchFailure(
            'The visual request could not be applied: ' + (error && error.message || error),
            meta,
          );
        });
      } else {
        surfaceDispatchResult(result, meta);
      }
    } catch (e) {
      surfaceDispatchFailure(
        'The visual request could not be applied: ' + (e && e.message || e),
        meta,
      );
    }
    return blockCount;
  }

  /** Test hook: forget the dedupe key. */
  function resetDedupe() { _lastKey = null; }

  window.OraV3VisualDispatch = {
    extractBlocks: extractBlocks,
    extractImageBlocks: extractImageBlocks,
    stripBlocks: stripBlocks,
    dispatch: dispatch,
    persistOutcome: persistOutcome,
    resetDedupe: resetDedupe,
    PLACEHOLDER: PLACEHOLDER,
  };
})();
