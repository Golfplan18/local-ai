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

  const NARROWING_FINDING_CODES = new Set([
    'E_ARTIFACT_OVERLAP',
    'W_ARTIFACT_TEXT_TRUNCATED',
    'W_ARTIFACT_LABEL_OVERLAP',
  ]);
  const MIN_EFFECTIVE_TEXT_PX = 10;

  let _lastKey = null;
  let _activeKey = null;

  function setActiveKey(key) {
    const normalized = key != null ? String(key) : null;
    if (normalized !== _activeKey) {
      _activeKey = normalized;
      _lastKey = null;
    }
  }

  function replaceBlocksWithEnvelope(text, envelope) {
    const block = '```ora-visual\n' + JSON.stringify(envelope, null, 2) + '\n```';
    let installed = false;
    const next = String(text || '').replace(FENCE_RE, () => {
      if (installed) return '';
      installed = true;
      return block;
    });
    if (installed) return next;
    return next + (next && !next.endsWith('\n') ? '\n\n' : '') + block;
  }

  function _viewportSize(viewport) {
    if (!viewport) return null;
    let width = Number(viewport.clientWidth || viewport.width) || 0;
    let height = Number(viewport.clientHeight || viewport.height) || 0;
    if ((!width || !height) && typeof viewport.getBoundingClientRect === 'function') {
      const bounds = viewport.getBoundingClientRect();
      width = width || Number(bounds && bounds.width) || 0;
      height = height || Number(bounds && bounds.height) || 0;
    }
    return width > 0 && height > 0 ? { width, height } : null;
  }

  /** Return the one class of finding allowed to request a narrower subject.
   *  Artifact-review overlap/truncation findings are already mechanical. The
   *  additional browser measurement fits the complete SVG into the actual
   *  Exhibits viewport and checks the smallest visible text at that scale.
   *  This deliberately measures the whole diagram instead of imposing a node
   *  quota. */
  function reviewLegibility(result, viewport) {
    if (!result || typeof result !== 'object') return null;
    const findings = [];
    [result.errors, result.warnings].forEach((items) => {
      (Array.isArray(items) ? items : []).forEach((item) => {
        if (item && NARROWING_FINDING_CODES.has(item.code)) findings.push(item);
      });
    });
    if (findings.length) {
      const finding = findings[0];
      return {
        code: finding.code,
        message: finding.message || 'The artifact review found an unreadable layout.',
      };
    }

    const size = _viewportSize(viewport);
    if (!size || typeof result.svg !== 'string' || !result.svg) return null;
    if (!window.DOMParser || !window.document) return null;

    let holder = null;
    try {
      holder = window.document.createElement('div');
      holder.setAttribute('aria-hidden', 'true');
      holder.style.cssText = 'position:fixed;left:-100000px;top:-100000px;opacity:0;pointer-events:none;';
      holder.innerHTML = result.svg;
      const svg = holder.querySelector('svg');
      if (!svg) return null;
      if (window.document.body) window.document.body.appendChild(holder);

      let viewWidth = 0;
      let viewHeight = 0;
      const viewBox = (svg.getAttribute('viewBox') || '').trim()
        .split(/[\s,]+/).map(Number);
      if (viewBox.length === 4 && viewBox.every(Number.isFinite)) {
        viewWidth = viewBox[2];
        viewHeight = viewBox[3];
      }
      viewWidth = viewWidth || parseFloat(svg.getAttribute('width')) || 0;
      viewHeight = viewHeight || parseFloat(svg.getAttribute('height')) || 0;
      if (viewWidth <= 0 || viewHeight <= 0) return null;

      let minFont = Infinity;
      Array.from(svg.querySelectorAll('text')).forEach((textNode) => {
        if (textNode.getAttribute('aria-hidden') === 'true'
            || !(textNode.textContent || '').trim()) return;
        let fontSize = parseFloat(textNode.getAttribute('font-size')) || 0;
        if (typeof window.getComputedStyle === 'function') {
          const computed = window.getComputedStyle(textNode);
          if (computed && computed.display !== 'none' && computed.visibility !== 'hidden') {
            fontSize = parseFloat(computed.fontSize) || fontSize;
          } else if (computed) {
            return;
          }
        }
        if (!fontSize) fontSize = 12;
        minFont = Math.min(minFont, fontSize);
      });
      if (!Number.isFinite(minFont)) return null;

      const fitScale = Math.min(
        Math.max(1, size.width - 32) / viewWidth,
        Math.max(1, size.height - 32) / viewHeight,
      );
      const effectiveFont = minFont * fitScale;
      if (effectiveFont >= MIN_EFFECTIVE_TEXT_PX) return null;
      return {
        code: 'W_VIEWPORT_TEXT_LEGIBILITY',
        message: `Smallest fitted text is ${effectiveFont.toFixed(1)}px in a `
          + `${Math.round(size.width)}\u00d7${Math.round(size.height)}px viewport.`,
        viewport: { width: size.width, height: size.height },
        effective_text_px: Number(effectiveFont.toFixed(2)),
      };
    } catch (error) {
      console.warn('[v3-visual-dispatch] viewport legibility measurement failed:', error);
      return null;
    } finally {
      if (holder && holder.parentNode) holder.parentNode.removeChild(holder);
    }
  }

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

  function surfaceDispatchFailure(message, meta, stage) {
    const detail = message || 'The visual request could not be applied.';
    console.warn('[v3-visual-dispatch] ' + detail);
    const panel = window.OraPanels && window.OraPanels.visual;
    if (panel && typeof panel.showError === 'function') {
      panel.showError('Visual failed: ' + detail);
    }
    persistOutcome(meta, {
      state: 'failed',
      stage: stage || 'dispatch',
      reason: detail,
    });
  }

  function _flattenResults(value) {
    const flattened = [];
    (function collect(item) {
      if (Array.isArray(item)) item.forEach(collect);
      else flattened.push(item);
    })(value);
    return flattened;
  }

  function surfaceDispatchResult(result, meta) {
    const results = _flattenResults(result);
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

  function _narrowingResult(result) {
    const results = _flattenResults(result);
    for (let index = 0; index < results.length; index += 1) {
      const item = results[index];
      if (item && item.needs_narrower_subject === true && item.legibility_finding) {
        return { index, finding: item.legibility_finding };
      }
    }
    return null;
  }

  async function requestNarrowerSubject(context, narrowing) {
    const meta = context.meta || {};
    if (!meta.conversationId || !Number.isInteger(meta.assistantIndex)) {
      throw new Error('The narrower visual could not be saved because its assistant turn is unavailable.');
    }
    if (typeof window.fetch !== 'function') {
      throw new Error('The narrower visual request is unavailable.');
    }
    const original = context.blocks[Math.min(narrowing.index, context.blocks.length - 1)];
    const envelope = original && original.envelope;
    const response = await window.fetch('/api/visual/regenerate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prose: context.text,
        mode: meta.mode || '',
        manual_visual_type: envelope && envelope.type || undefined,
        narrow_subject: true,
        legibility_finding: narrowing.finding,
        conversation_id: meta.conversationId,
        assistant_index: meta.assistantIndex,
      }),
    });
    let data = null;
    try { data = await response.json(); } catch (_) { data = null; }
    if (!response.ok || !data || !data.ok || !data.envelope || data.persisted !== true) {
      throw new Error((data && (data.reason || data.error))
        || `The narrower visual request failed (HTTP ${response.status}).`);
    }
    if (typeof meta.onNarrowedEnvelopePersisted === 'function') {
      try {
        meta.onNarrowedEnvelopePersisted(data.envelope, {
          state: 'building',
          stage: 'legibility',
          reason: 'A narrower visual was saved and is awaiting insertion.',
        });
      } catch (error) {
        console.warn('[v3-visual-dispatch] saved envelope cache update failed:', error);
      }
    }
    // Synthesis is slower than compilation. If navigation moved to another
    // turn while it ran, the new envelope is already durable in its own turn;
    // leave it building so reopening that turn performs the insertion instead
    // of drawing it onto the newly active conversation.
    if (context.key != null && _activeKey !== String(context.key)) {
      return { deferred_narrowed_insertion: true };
    }
    return Promise.resolve(context.panel.onBridgeUpdate({
      ora_visual_blocks: [{ envelope: data.envelope }],
      ora_visual_dispatch_key: context.key != null ? `${String(context.key)}:narrowed` : null,
    }));
  }

  async function settleDispatchResult(result, context, narrowed) {
    if (_flattenResults(result).some((item) => (
      item && item.deferred_narrowed_insertion === true
    ))) return;
    const narrowing = _narrowingResult(result);
    if (!narrowing) {
      surfaceDispatchResult(result, context.meta);
      return;
    }
    if (narrowed) {
      surfaceDispatchFailure(
        'The visual remained unreadable after one narrower-subject attempt: '
          + (narrowing.finding.message || narrowing.finding.code),
        context.meta,
        'legibility',
      );
      return;
    }
    try {
      const secondResult = await requestNarrowerSubject(context, narrowing);
      const secondMeta = Object.assign({}, context.meta, {
        visualOutcome: {
          state: 'building',
          stage: 'legibility',
          reason: 'A narrower visual was saved and is awaiting insertion.',
        },
      });
      await settleDispatchResult(secondResult, Object.assign({}, context, {
        meta: secondMeta,
      }), true);
    } catch (error) {
      surfaceDispatchFailure(
        'The visual could not be narrowed: ' + (error && error.message || error),
        context.meta,
        'legibility',
      );
    }
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
    setActiveKey(key);
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
    const context = { text, key, meta, blocks, panel };
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
        return settleDispatchResult(values.flat(), context, !!(
          meta && meta.visualOutcome && meta.visualOutcome.stage === 'legibility'
        ));
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
        Promise.resolve(result).then((value) => (
          settleDispatchResult(value, context, !!(
            meta && meta.visualOutcome && meta.visualOutcome.stage === 'legibility'
          ))
        )).catch((error) => {
          surfaceDispatchFailure(
            'The visual request could not be applied: ' + (error && error.message || error),
            meta,
          );
        });
      } else {
        settleDispatchResult(result, context, !!(
          meta && meta.visualOutcome && meta.visualOutcome.stage === 'legibility'
        )).catch((error) => {
          surfaceDispatchFailure(
            'The visual request could not be applied: ' + (error && error.message || error),
            meta,
          );
        });
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
    reviewLegibility: reviewLegibility,
    replaceBlocksWithEnvelope: replaceBlocksWithEnvelope,
    setActiveKey: setActiveKey,
    resetDedupe: resetDedupe,
    PLACEHOLDER: PLACEHOLDER,
  };
})();
