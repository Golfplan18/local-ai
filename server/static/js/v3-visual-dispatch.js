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
 * Overlapping away/back or reload renders observe one in-memory owner for
 * the exact conversation + assistant identity. Once that operation and all
 * of its observers finish, a later reopen may apply the durable envelope
 * again; the render key still tracks the displayed conversation + turn.
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
  const _legibilityRetryOperations = new Map();
  const _legibilityDispatchCounts = new Map();
  // One browser-local owner applies an assistant turn's complete source
  // sequence. A second render of the same durable assistant observes that
  // owner instead of replaying its clear/update/annotate operations.
  const _assistantSequenceOperations = new Map();

  function setActiveKey(key) {
    const normalized = key != null ? String(key) : null;
    if (normalized !== _activeKey) {
      _activeKey = normalized;
      _lastKey = null;
    }
  }

  function replaceBlocksWithEnvelope(text, envelope, visualBlockIndex) {
    const source = String(text || '');
    if (!Number.isInteger(visualBlockIndex) || visualBlockIndex < 0) return source;
    const block = '```ora-visual\n' + JSON.stringify(envelope, null, 2) + '\n```';
    let currentBlockIndex = 0;
    let installed = false;
    const next = source.replace(FENCE_RE, (match) => {
      if (currentBlockIndex === visualBlockIndex) {
        installed = true;
        currentBlockIndex += 1;
        return block;
      }
      currentBlockIndex += 1;
      return match;
    });
    return installed ? next : source;
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
      // SVG preserves foreignObject's mixed-case local name, while selector
      // engines operating in an HTML document do not agree on type-selector
      // casing for that foreign-namespace element (notably jsdom). Enumerate
      // descendants without a tag selector, then identify label elements by
      // their namespace-independent local-name/ancestry instead.
      Array.from(svg.querySelectorAll('*')).filter((node) => {
        const localName = String(node.localName || '').toLowerCase();
        if (localName === 'text' || localName === 'tspan') return true;
        let ancestor = node.parentElement;
        while (ancestor && ancestor !== svg) {
          if (String(ancestor.localName || '').toLowerCase() === 'foreignobject') {
            return true;
          }
          ancestor = ancestor.parentElement;
        }
        return false;
      }).forEach((labelNode) => {
        if (labelNode.getAttribute('aria-hidden') === 'true'
            || !(labelNode.textContent || '').trim()) return;
        let fontSize = parseFloat(labelNode.getAttribute('font-size')) || 0;
        if (typeof window.getComputedStyle === 'function') {
          const computed = window.getComputedStyle(labelNode);
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

  /** Extract every parseable ora-visual object. Unparseable/non-object JSON
   *  is skipped (the raw fence stays visible in the transcript so the
   *  failure is inspectable rather than silently swallowed). Each survivor
   *  retains its position among all syntactically fenced blocks. */
  function extractBlocks(text) {
    if (typeof text !== 'string' || text.indexOf('ora-visual') === -1) return [];
    const blocks = [];
    let rawFenceIndex = 0;
    let m;
    FENCE_RE.lastIndex = 0;
    while ((m = FENCE_RE.exec(text)) !== null) {
      const visualBlockIndex = rawFenceIndex;
      rawFenceIndex += 1;
      try {
        const envelope = JSON.parse(m[1]);
        if (envelope && typeof envelope === 'object' && !Array.isArray(envelope)) {
          blocks.push({
            envelope: envelope,
            raw_json: m[1],
            raw_fence_index: visualBlockIndex,
          });
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

  function _canonicalOutcome(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    if (!['building', 'ready', 'failed', 'not_applicable'].includes(value.state)) {
      return null;
    }
    return value;
  }

  function _canonicalJson(value) {
    if (Array.isArray(value)) {
      return '[' + value.map(_canonicalJson).join(',') + ']';
    }
    if (value && typeof value === 'object') {
      return '{' + Object.keys(value).sort().map((key) => (
        JSON.stringify(key) + ':' + _canonicalJson(value[key])
      )).join(',') + '}';
    }
    return JSON.stringify(value);
  }

  function _sameCanonicalOutcome(left, right) {
    const canonicalLeft = _canonicalOutcome(left);
    const canonicalRight = _canonicalOutcome(right);
    return !!canonicalLeft && !!canonicalRight
      && _canonicalJson(canonicalLeft) === _canonicalJson(canonicalRight);
  }

  async function persistOutcome(meta, outcome) {
    if (!meta || !meta.conversationId || typeof window.fetch !== 'function') {
      return {
        ok: false,
        visual_outcome: null,
        error: 'The visual outcome save target is unavailable.',
      };
    }
    const body = Object.assign({}, outcome, {
      assistant_index: Number.isInteger(meta.assistantIndex)
        ? meta.assistantIndex : undefined,
    });
    Object.keys(body).forEach((key) => body[key] === undefined && delete body[key]);
    try {
      const response = await Promise.resolve(window.fetch(
        `/api/conversation/${encodeURIComponent(meta.conversationId)}/visual-outcome`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        },
      ));
      let data = null;
      try { data = await response.json(); } catch (_) { data = null; }
      const canonical = data && data.ok === true
        ? _canonicalOutcome(data.visual_outcome) : null;
      if (!response.ok || !canonical) {
        const detail = data && (data.error || data.reason)
          || `The visual outcome save failed (HTTP ${response.status}).`;
        console.warn('[v3-visual-dispatch] outcome save failed:', detail);
        return {
          ok: false,
          status: response.status,
          visual_outcome: null,
          error: detail,
        };
      }
      return { ok: true, visual_outcome: canonical };
    } catch (error) {
      console.warn('[v3-visual-dispatch] outcome save failed:', error);
      return {
        ok: false,
        visual_outcome: null,
        error: error && error.message || String(error),
      };
    }
  }

  function _persistStandaloneOutcome(meta, outcome, visualBlockIndex) {
    persistOutcome(meta, outcome).then((result) => {
      if (!result.ok || !meta) return;
      meta.visualOutcome = result.visual_outcome;
      _notifyNarrowedOutcome(
        meta, null, result.visual_outcome, visualBlockIndex,
      );
    });
  }

  function _notifyNarrowedOutcome(meta, envelope, outcome, visualBlockIndex) {
    if (!meta || typeof meta.onNarrowedEnvelopePersisted !== 'function') return;
    try {
      meta.onNarrowedEnvelopePersisted(
        envelope || null, outcome, visualBlockIndex,
      );
    } catch (error) {
      console.warn('[v3-visual-dispatch] saved envelope cache update failed:', error);
    }
  }

  function _legibilityAttempts(outcome) {
    const source = outcome && outcome.legibility_attempts;
    if (!source || typeof source !== 'object' || Array.isArray(source)) return {};
    const attempts = {};
    Object.keys(source).forEach((rawIndex) => {
      if (!/^\d+$/.test(rawIndex)) return;
      const status = source[rawIndex];
      if (status === 'in_progress' || status === 'exhausted') {
        attempts[String(Number(rawIndex))] = status;
      }
    });
    return attempts;
  }

  function _withLegibilityAttempts(outcome, updates) {
    const attempts = _legibilityAttempts(outcome);
    let changed = false;
    (updates || []).forEach((update) => {
      if (Number.isInteger(update.index) && update.index >= 0
          && (update.status === 'in_progress' || update.status === 'exhausted')) {
        const key = String(update.index);
        if (attempts[key] !== 'exhausted' && attempts[key] !== update.status) {
          attempts[key] = update.status;
          changed = true;
        }
      }
    });
    if (!changed && outcome && typeof outcome === 'object') return outcome;
    const next = Object.assign({}, outcome || {});
    if (Object.keys(attempts).length) next.legibility_attempts = attempts;
    return next;
  }

  function _applyNarrowingOutcome(meta, envelope, outcome, visualBlockIndex) {
    if (!meta || !outcome || typeof outcome !== 'object') return;
    meta.visualOutcome = outcome;
    _notifyNarrowedOutcome(meta, envelope, outcome, visualBlockIndex);
  }

  function _rememberNarrowingOutcome(meta, envelope, outcome, visualBlockIndex) {
    if (!meta || !outcome || typeof outcome !== 'object') return;
    const operationKey = _legibilityDispatchKey(meta);
    const sequenceOperation = operationKey
      ? _assistantSequenceOperations.get(operationKey) : null;
    if (!sequenceOperation) {
      _applyNarrowingOutcome(meta, envelope, outcome, visualBlockIndex);
      return;
    }
    sequenceOperation.latestConfirmedPersistedOutcome = outcome;
    const update = { envelope, outcome, visualBlockIndex };
    sequenceOperation.narrowingUpdates.push(update);
    const updatedMetas = new Set();
    sequenceOperation.consumers.forEach((consumer) => {
      const targetMeta = consumer && consumer.meta;
      if (!targetMeta || updatedMetas.has(targetMeta)) return;
      updatedMetas.add(targetMeta);
      _applyNarrowingOutcome(targetMeta, envelope, outcome, visualBlockIndex);
    });
  }

  function surfaceDispatchFailure(
    message, meta, stage, originatingKey, visualBlockIndex, controls,
  ) {
    const publishMemory = !!(controls && controls.publishMemory === true);
    const authoritativeOutcome = controls && controls.authoritativeOutcome;
    const preserveAuthoritativeOutcome = !!(
      authoritativeOutcome
      && controls
      && controls.preserveAuthoritativeOutcome === true
    );
    const detail = preserveAuthoritativeOutcome
      ? (authoritativeOutcome.reason || message || 'The visual request could not be applied.')
      : (message || 'The visual request could not be applied.');
    if (!controls || controls.log !== false) {
      console.warn('[v3-visual-dispatch] ' + detail);
    }
    let outcome = preserveAuthoritativeOutcome
      ? authoritativeOutcome
      : Object.assign({}, authoritativeOutcome || {}, {
        state: 'failed',
        stage: stage || (authoritativeOutcome && authoritativeOutcome.stage) || 'dispatch',
        reason: detail,
    });
    if (outcome.stage === 'legibility') {
      const prior = controls && controls.priorOutcome
        || meta && meta.visualOutcome;
      if (!preserveAuthoritativeOutcome) {
        const attempts = _legibilityAttempts(prior);
        outcome = _withLegibilityAttempts(
          outcome,
          Object.keys(attempts).map((rawIndex) => ({
            index: Number(rawIndex),
            status: attempts[rawIndex],
          })),
        );
        ['origin', 'trace_ref'].forEach((key) => {
          if (!outcome[key] && prior && typeof prior[key] === 'string' && prior[key]) {
            outcome[key] = prior[key];
          }
        });
      }
      // The same identity-bound callback that installs a durable narrower
      // envelope also owns its terminal failure. Passing no envelope leaves
      // the assistant content intact while updating its browser outcome.
      if (preserveAuthoritativeOutcome) {
        if (publishMemory && meta) meta.visualOutcome = outcome;
      } else if (publishMemory) {
        _rememberNarrowingOutcome(meta, null, outcome, visualBlockIndex);
      }
    } else if (publishMemory && meta) {
      meta.visualOutcome = outcome;
    }
    const isOriginatingViewActive = originatingKey == null
      || _activeKey === String(originatingKey);
    const panel = window.OraPanels && window.OraPanels.visual;
    if ((!controls || controls.surface !== false)
        && isOriginatingViewActive && panel && typeof panel.showError === 'function') {
      panel.showError('Visual failed: ' + detail);
    }
    // Navigation controls only where status is drawn. The terminal owner
    // writes once; duplicate contexts only mirror the identity-bound cache.
    if (!controls || controls.persist !== false) {
      _persistStandaloneOutcome(meta, outcome, visualBlockIndex);
    }
    return outcome;
  }

  function _flattenResults(value) {
    const flattened = [];
    (function collect(item) {
      if (Array.isArray(item)) item.forEach(collect);
      else flattened.push(item);
    })(value);
    return flattened;
  }

  function surfaceDispatchResult(result, meta, originatingKey, stage, controls) {
    const results = _flattenResults(result);
    const unsupported = results.filter((item) => item && item.unsupported === true);
    if (unsupported.length === 0) {
      const ready = { state: 'ready' };
      const prior = meta && meta.visualOutcome;
      ['stage', 'origin', 'trace_ref'].forEach((key) => {
        if (prior && typeof prior[key] === 'string' && prior[key]) ready[key] = prior[key];
      });
      if (prior && prior.state !== 'failed'
          && typeof prior.reason === 'string' && prior.reason) {
        ready.reason = prior.reason;
      }
      const attempts = _legibilityAttempts(prior);
      if (Object.keys(attempts).length) ready.legibility_attempts = attempts;
      const publishMemory = !!(controls && controls.publishMemory === true);
      if (publishMemory && Object.keys(attempts).length) {
        _rememberNarrowingOutcome(meta, null, ready);
      } else if (publishMemory && meta) {
        meta.visualOutcome = ready;
      }
      if (!controls || controls.persist !== false) {
        _persistStandaloneOutcome(meta, ready, undefined);
      }
      return ready;
    }
    const warnings = [];
    unsupported.forEach((item) => {
      (Array.isArray(item.warnings) ? item.warnings : []).forEach((warning) => {
        if (typeof warning === 'string' && warning && !warnings.includes(warning)) {
          warnings.push(warning);
        }
      });
    });
    return surfaceDispatchFailure(
      warnings.join('\n') || 'This visual action is not supported by the active editor.'
      , meta, stage, originatingKey, undefined, controls
    );
  }

  function _narrowingResults(result, context) {
    const results = _flattenResults(result);
    const narrowings = [];
    for (let index = 0; index < results.length; index += 1) {
      const item = results[index];
      if (item && item.needs_narrower_subject === true && item.legibility_finding) {
        const block = context && context.blocks && context.blocks[index];
        narrowings.push({
          index,
          block,
          raw_fence_index: block && block.raw_fence_index,
          finding: item.legibility_finding,
        });
      }
    }
    return narrowings;
  }

  function _narrowedRenderFailureReason(result) {
    const results = _flattenResults(result);
    if (results.length === 0 || results.some((item) => item == null)) {
      return 'The active editor did not confirm that the narrowed visual was inserted.';
    }
    const errors = [];
    let hasErrors = false;
    results.forEach((item) => {
      if (!item || typeof item !== 'object') return;
      const itemErrors = Array.isArray(item.errors) ? item.errors : [];
      if (itemErrors.length) hasErrors = true;
      itemErrors.forEach((error) => {
        const message = typeof error === 'string'
          ? error : error && (error.message || error.code);
        if (message && !errors.includes(String(message))) errors.push(String(message));
      });
    });
    if (hasErrors) {
      return 'The active editor reported a narrowed-render error'
        + (errors.length ? ': ' + errors.join('; ') : '.');
    }
    const inserted = results.some((item) => (
      item && typeof item === 'object'
      && typeof item.svg === 'string' && item.svg.trim().length > 0
    ));
    if (!inserted) {
      return 'The active editor did not return a rendered SVG for the narrowed visual.';
    }
    return null;
  }

  function _legibilityRetryKey(context, narrowing) {
    const meta = context && context.meta || {};
    const visualBlockIndex = narrowing && narrowing.raw_fence_index;
    if (!meta.conversationId
        || !Number.isInteger(meta.assistantIndex)
        || !Number.isInteger(visualBlockIndex)) return null;
    return JSON.stringify([
      String(meta.conversationId), meta.assistantIndex, visualBlockIndex,
    ]);
  }

  function _legibilityDispatchKey(meta) {
    if (!meta || !meta.conversationId || !Number.isInteger(meta.assistantIndex)) {
      return null;
    }
    return JSON.stringify([String(meta.conversationId), meta.assistantIndex]);
  }

  function _originIsActive(context) {
    return !context || context.key == null
      || _activeKey === String(context.key);
  }

  function _originInactiveOutcome(context, detail) {
    const prior = context && context.meta && context.meta.visualOutcome;
    const outcome = {
      state: 'failed',
      stage: 'dispatch',
      reason: detail || 'The visual sequence stopped because its originating Dialogue was no longer active.',
    };
    ['origin', 'trace_ref'].forEach((key) => {
      if (prior && typeof prior[key] === 'string' && prior[key]) {
        outcome[key] = prior[key];
      }
    });
    const attempts = _legibilityAttempts(prior);
    if (Object.keys(attempts).length) outcome.legibility_attempts = attempts;
    return outcome;
  }

  function _coldOrphanOutcome(context, visualBlockIndex) {
    const prior = context && context.meta && context.meta.visualOutcome;
    const attempts = _legibilityAttempts(prior);
    if (attempts[String(visualBlockIndex)] !== 'in_progress') return null;
    const retryKey = _legibilityRetryKey(context, {
      raw_fence_index: visualBlockIndex,
    });
    if (retryKey && _legibilityRetryOperations.has(retryKey)) return null;
    const outcome = _withLegibilityAttempts({
      state: 'failed',
      stage: 'legibility',
      reason: 'A narrower visual attempt was recorded, but insertion could not '
        + 'be confirmed after reopening.',
      legibility_attempts: attempts,
    }, [{ index: visualBlockIndex, status: 'exhausted' }]);
    ['origin', 'trace_ref'].forEach((key) => {
      if (prior && typeof prior[key] === 'string' && prior[key]) {
        outcome[key] = prior[key];
      }
    });
    return outcome;
  }

  function _retainLegibilityDispatch(context) {
    const dispatchKey = _legibilityDispatchKey(context && context.meta);
    if (!dispatchKey) return;
    context.legibilityDispatchKey = dispatchKey;
    _legibilityDispatchCounts.set(
      dispatchKey, (_legibilityDispatchCounts.get(dispatchKey) || 0) + 1,
    );
  }

  function _releaseLegibilityDispatch(context) {
    const dispatchKey = context && context.legibilityDispatchKey;
    if (!dispatchKey || context.legibilityDispatchReleased === true) return;
    context.legibilityDispatchReleased = true;
    const remaining = Math.max(
      0, (_legibilityDispatchCounts.get(dispatchKey) || 0) - 1,
    );
    if (remaining) _legibilityDispatchCounts.set(dispatchKey, remaining);
    else _legibilityDispatchCounts.delete(dispatchKey);
    for (const [key, operation] of _legibilityRetryOperations) {
      if (operation && operation.dispatchKey === dispatchKey
          && operation.settled === true && remaining === 0) {
        _legibilityRetryOperations.delete(key);
      }
    }
  }

  function _legibilityRetryOperation(context, narrowing) {
    const retryKey = _legibilityRetryKey(context, narrowing);
    if (retryKey && _legibilityRetryOperations.has(retryKey)) {
      const existing = _legibilityRetryOperations.get(retryKey);
      return existing;
    }
    const operation = {
      key: retryKey,
      dispatchKey: context && context.legibilityDispatchKey,
      requestOwnerContext: context,
      renderOwnerContext: null,
      settled: false,
      renderPromise: null,
      promise: null,
    };
    operation.promise = requestNarrowerSubject(context, narrowing);
    operation.promise.then(() => {
      operation.settled = true;
      if (retryKey && operation.dispatchKey
          && !_legibilityDispatchCounts.has(operation.dispatchKey)
          && _legibilityRetryOperations.get(retryKey) === operation) {
        _legibilityRetryOperations.delete(retryKey);
      }
    }, () => {
      operation.settled = true;
      if (retryKey && operation.dispatchKey
          && !_legibilityDispatchCounts.has(operation.dispatchKey)
          && _legibilityRetryOperations.get(retryKey) === operation) {
        _legibilityRetryOperations.delete(retryKey);
      }
    });
    if (retryKey) {
      _legibilityRetryOperations.set(retryKey, operation);
    }
    return operation;
  }

  function _legibilityAttemptState(context, narrowing) {
    const outcome = context && context.meta && context.meta.visualOutcome;
    const attempts = _legibilityAttempts(outcome);
    const rawIndex = narrowing && narrowing.raw_fence_index;
    if (Number.isInteger(rawIndex) && attempts[String(rawIndex)]) {
      return attempts[String(rawIndex)];
    }
    // Old outcomes recorded only the assistant-wide stage. That is enough
    // evidence for the sole fence of a single-visual turn, but it cannot
    // truthfully identify any one sibling in a multi-visual turn.
    if (outcome && outcome.stage === 'legibility'
        && Object.keys(attempts).length === 0
        && context && context.blocks && context.blocks.length === 1) {
      return 'exhausted';
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
    const original = context.blocks[narrowing.index];
    if (!original) {
      throw new Error('The unreadable visual block could not be identified.');
    }
    const visualBlockIndex = original.raw_fence_index;
    if (!Number.isInteger(visualBlockIndex) || visualBlockIndex < 0) {
      throw new Error('The unreadable visual fence could not be identified.');
    }
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
        visual_block_index: visualBlockIndex,
      }),
    });
    let data = null;
    try { data = await response.json(); } catch (_) { data = null; }
    if (data && data.retry_status
        && (data.retry_status === 'in_progress' || data.retry_status === 'exhausted')) {
      return {
        retry_status: data.retry_status,
        visual_outcome: data.visual_outcome_persisted === true
          ? _canonicalOutcome(data.visual_outcome) : null,
        visual_outcome_persisted: data.visual_outcome_persisted === true
          && !!_canonicalOutcome(data.visual_outcome),
        visual_block_index: visualBlockIndex,
      };
    }
    if (!response.ok || !data || !data.ok || !data.envelope || data.persisted !== true) {
      const error = new Error((data && (data.reason || data.error))
        || `The narrower visual request failed (HTTP ${response.status}).`);
      const confirmedFailure = data && data.visual_outcome_persisted === true
        ? _canonicalOutcome(data.visual_outcome) : null;
      if (confirmedFailure) {
        error.visualOutcome = confirmedFailure;
        error.visualOutcomePersisted = true;
      }
      error.visualBlockIndex = visualBlockIndex;
      throw error;
    }
    const savedOutcome = data.visual_outcome_persisted === true
      ? _canonicalOutcome(data.visual_outcome) : null;
    if (!savedOutcome) {
      const error = new Error(
        'The narrower visual replacement was not confirmed by durable storage.'
      );
      error.visualBlockIndex = visualBlockIndex;
      throw error;
    }
    return {
      narrowed_block: {
        envelope: data.envelope,
        raw_fence_index: visualBlockIndex,
      },
      visual_outcome: savedOutcome,
      visual_block_index: visualBlockIndex,
    };
  }

  async function _consumeNarrowingOperation(operation, context, narrowing) {
    const visualBlockIndex = narrowing.raw_fence_index;
    let retry;
    try {
      retry = await operation.promise;
    } catch (error) {
      if (error && error.visualOutcome) {
        _rememberNarrowingOutcome(
          context.meta, null, error.visualOutcome, visualBlockIndex,
        );
      }
      throw error;
    }
    if (retry && retry.visual_outcome) {
      _rememberNarrowingOutcome(
        context.meta,
        retry.narrowed_block && retry.narrowed_block.envelope,
        retry.visual_outcome,
        visualBlockIndex,
      );
    }
    if (retry && retry.retry_status) return retry;
    // Synthesis and exact replacement are shared by fence identity. Rendering
    // is shared too: an away/back duplicate consumes the owner's envelope and
    // result without applying the same pane update a second time.
    if (!_originIsActive(context)) {
      return {
        deferred_narrowed_insertion: true,
        visual_block_index: visualBlockIndex,
      };
    }
    if (!operation.renderPromise) {
      operation.renderOwnerContext = context;
      operation.renderPromise = Promise.resolve().then(() => (
        _originIsActive(context)
          ? context.panel.onBridgeUpdate({
            ora_visual_blocks: [retry.narrowed_block],
            ora_visual_dispatch_key: context.key != null
              ? `${String(context.key)}:narrowed:${visualBlockIndex}` : null,
          })
          : {
            deferred_narrowed_insertion: true,
            visual_block_index: visualBlockIndex,
          }
      ));
    }
    try {
      const renderResult = await operation.renderPromise;
      if (renderResult && renderResult.deferred_narrowed_insertion === true) {
        return renderResult;
      }
      return {
        render_result: renderResult,
        narrowed_block: retry.narrowed_block,
        visual_block_index: visualBlockIndex,
      };
    } catch (error) {
      const narrowedError = error && typeof error === 'object'
        ? error : new Error(String(error || 'The narrowed visual render failed.'));
      narrowedError.narrowedRender = true;
      throw narrowedError;
    }
  }

  async function settleDispatchResult(result, context, controls) {
    const narrowings = _narrowingResults(result, context);
    if (narrowings.length === 0) {
      return {
        pending: false,
        hadNarrowing: false,
        ownsTerminalOutcome: true,
        outcome: surfaceDispatchResult(
          result, context.meta, context.key, undefined, controls,
        ),
        result,
      };
    }
    const settledResults = _flattenResults(result);
    const failures = [];
    let pending = false;
    let ownsTerminalOutcome = false;
    for (const narrowing of narrowings) {
      const visualBlockIndex = narrowing.raw_fence_index;
      if (!Number.isInteger(visualBlockIndex)) {
        ownsTerminalOutcome = true;
        failures.push({
          index: null,
          kind: 'could_not_narrow',
          message: 'The unreadable visual fence could not be identified.',
        });
        continue;
      }
      const retryKey = _legibilityRetryKey(context, narrowing);
      const sharedOperation = retryKey
        ? _legibilityRetryOperations.get(retryKey) : null;
      const priorStatus = _legibilityAttemptState(context, narrowing);
      if (!sharedOperation && priorStatus === 'in_progress') {
        ownsTerminalOutcome = true;
        failures.push({
          index: visualBlockIndex,
          kind: 'orphaned_attempt',
          quiet: true,
          message: 'A narrower visual attempt was recorded, but insertion could not '
            + 'be confirmed after reopening.',
        });
        continue;
      }
      if (!sharedOperation && priorStatus === 'exhausted') {
        ownsTerminalOutcome = true;
        failures.push({
          index: visualBlockIndex,
          kind: 'remained_unreadable',
          message: narrowing.finding.message || narrowing.finding.code,
          authoritativeOutcome: context.meta.visualOutcome,
          authoritativeOutcomePersisted: true,
        });
        continue;
      }
      const operation = _legibilityRetryOperation(context, narrowing);
      try {
        const retry = await _consumeNarrowingOperation(
          operation, context, narrowing,
        );
        if (retry && retry.retry_status === 'in_progress') {
          pending = true;
          continue;
        }
        if (retry && retry.retry_status === 'exhausted') {
          const authoritative = retry.visual_outcome;
          if (authoritative && authoritative.state === 'failed') {
            if (operation.requestOwnerContext === context) ownsTerminalOutcome = true;
            failures.push({
              index: visualBlockIndex,
              kind: 'could_not_narrow',
              message: authoritative.reason
                || 'The authoritative narrower visual attempt failed.',
              authoritativeOutcome: authoritative,
              authoritativeOutcomePersisted: retry.visual_outcome_persisted === true,
            });
          } else {
            // A 409 exhaustion response proves only that another owner used
            // the attempt. It does not prove this stale pre-retry render was
            // the narrowed envelope. Let the identity-bound owner finish.
            pending = true;
          }
          continue;
        }
        if (retry && retry.deferred_narrowed_insertion === true) {
          if (operation.requestOwnerContext === context) ownsTerminalOutcome = true;
          failures.push({
            index: visualBlockIndex,
            kind: 'could_not_apply',
            message: 'The narrower visual was saved, but insertion did not occur because '
              + 'its originating Dialogue was no longer active.',
          });
          continue;
        }
        const retryContext = Object.assign({}, context, {
          blocks: [retry && retry.narrowed_block],
        });
        const remainedUnreadable = _narrowingResults(
          retry && retry.render_result, retryContext,
        );
        if (remainedUnreadable.length) {
          if (operation.renderOwnerContext === context) ownsTerminalOutcome = true;
          failures.push({
            index: visualBlockIndex,
            kind: 'remained_unreadable',
            message: remainedUnreadable[0].finding.message
              || remainedUnreadable[0].finding.code,
          });
        } else {
          const narrowedResults = _flattenResults(retry && retry.render_result);
          const unsupported = narrowedResults.filter((item) => (
            item && item.unsupported === true
          ));
          if (unsupported.length) {
            if (operation.renderOwnerContext === context) ownsTerminalOutcome = true;
            const warnings = [];
            unsupported.forEach((item) => {
              (Array.isArray(item.warnings) ? item.warnings : []).forEach((warning) => {
                if (typeof warning === 'string' && warning
                    && !warnings.includes(warning)) warnings.push(warning);
              });
            });
            failures.push({
              index: visualBlockIndex,
              kind: 'unsupported',
              message: warnings.join('\n')
                || 'The narrowed visual is not supported by the active editor.',
            });
          } else {
            const renderFailure = _narrowedRenderFailureReason(
              retry && retry.render_result,
            );
            if (renderFailure) {
              if (operation.renderOwnerContext === context) ownsTerminalOutcome = true;
              failures.push({
                index: visualBlockIndex,
                kind: 'could_not_apply',
                message: renderFailure,
              });
            } else {
              if (operation.renderOwnerContext === context) ownsTerminalOutcome = true;
              settledResults[narrowing.index] = retry && retry.render_result;
            }
          }
        }
      } catch (error) {
        const failureOwner = error && error.narrowedRender
          ? operation.renderOwnerContext : operation.requestOwnerContext;
        if (failureOwner === context) ownsTerminalOutcome = true;
        if (error && error.visualOutcome) {
          _rememberNarrowingOutcome(
            context.meta, null, error.visualOutcome, visualBlockIndex,
          );
        }
        failures.push({
          index: visualBlockIndex,
          kind: error && error.narrowedRender
            ? 'could_not_apply' : 'could_not_narrow',
          message: error && error.message || error,
          authoritativeOutcome: error && error.visualOutcome || null,
          authoritativeOutcomePersisted: !!(
            error && error.visualOutcome && error.visualOutcomePersisted === true
          ),
        });
      }
    }
    if (failures.length) {
      const failurePrior = _withLegibilityAttempts(
        context.meta && context.meta.visualOutcome,
        failures.filter((failure) => Number.isInteger(failure.index)).map((failure) => ({
          index: failure.index,
          status: 'exhausted',
        })),
      );
      const detail = failures.map((failure) => (
        `${Number.isInteger(failure.index) ? `fence ${failure.index}` : 'visual'}: `
          + failure.message
      )).join('; ');
      const authoritativeFailure = failures.length === 1
        && failures[0].authoritativeOutcomePersisted === true
        && failures[0].authoritativeOutcome
        && failures[0].authoritativeOutcome.state === 'failed'
        ? failures[0] : null;
      let failureReason;
      if (authoritativeFailure) {
        failureReason = authoritativeFailure.authoritativeOutcome.reason
          || authoritativeFailure.message;
      } else if (failures.length === 1) {
        if (failures[0].kind === 'could_not_narrow') {
          failureReason = 'The visual could not be narrowed: ' + failures[0].message;
        } else if (failures[0].kind === 'could_not_apply') {
          failureReason = 'The narrowed visual could not be applied: '
            + failures[0].message;
        } else if (failures[0].kind === 'orphaned_attempt') {
          failureReason = failures[0].message;
        } else if (failures[0].kind === 'unsupported') {
          failureReason = failures[0].message;
        } else {
          failureReason = 'The visual remained unreadable after one narrower-subject attempt: '
            + failures[0].message;
        }
      } else {
        failureReason = 'One or more visuals could not be narrowed: ' + detail;
      }
      const outcome = surfaceDispatchFailure(
        failureReason,
        context.meta,
        'legibility',
        context.key,
        failures.length === 1 ? failures[0].index : undefined,
        {
          persist: !authoritativeFailure
            && ownsTerminalOutcome
            && (!controls || controls.persist !== false),
          surface: ownsTerminalOutcome
            && (!controls || controls.surface !== false)
            && failures.some((failure) => failure.quiet !== true),
          log: (!controls || controls.log !== false)
            && failures.some((failure) => failure.quiet !== true),
          authoritativeOutcome: authoritativeFailure
            && authoritativeFailure.authoritativeOutcome,
          preserveAuthoritativeOutcome: !!authoritativeFailure,
          priorOutcome: failurePrior,
        },
      );
      return {
        pending: false,
        hadNarrowing: true,
        ownsTerminalOutcome,
        terminalPersisted: !!authoritativeFailure,
        quiet: failures.every((failure) => failure.quiet === true),
        outcome,
        result: settledResults,
      };
    }
    if (pending) {
      return {
        pending: true,
        hadNarrowing: true,
        ownsTerminalOutcome: false,
        outcome: null,
        result: settledResults,
      };
    }
    return {
      pending: false,
      hadNarrowing: true,
      ownsTerminalOutcome,
      outcome: surfaceDispatchResult(
        settledResults, context.meta, context.key, 'legibility',
        {
          persist: ownsTerminalOutcome
            && (!controls || controls.persist !== false),
          surface: !controls || controls.surface !== false,
          log: !controls || controls.log !== false,
        },
      ),
      result: settledResults,
    };
  }

  function _visualBlockDispatchKey(context, block, sourceIndex) {
    if (!context || context.key == null) return null;
    const rawIndex = block && block.raw_fence_index;
    const identity = Number.isInteger(rawIndex) && rawIndex >= 0
      ? rawIndex : sourceIndex;
    return `${String(context.key)}:block:${identity}`;
  }

  function _combinedFailureOutcome(failures, meta) {
    if (failures.length === 1) return failures[0].outcome;
    const detail = failures.map((failure) => (
      `fence ${failure.rawIndex}: ${failure.outcome.reason}`
    )).join('; ');
    const outcome = {
      state: 'failed',
      stage: failures.some((failure) => failure.outcome.stage === 'legibility')
        ? 'legibility' : 'dispatch',
      reason: 'One or more visuals could not be applied: ' + detail,
    };
    const prior = meta && meta.visualOutcome;
    ['origin', 'trace_ref'].forEach((key) => {
      if (prior && typeof prior[key] === 'string' && prior[key]) {
        outcome[key] = prior[key];
      }
    });
    const attempts = _legibilityAttempts(prior);
    if (Object.keys(attempts).length) outcome.legibility_attempts = attempts;
    return outcome;
  }

  /** Apply one source fence at a time. A fence's initial bridge result, sole
   *  narrowing retry (when needed), and terminal settlement all finish before
   *  the next fence is allowed to mutate the editor. Later canvas actions are
   *  therefore never replayed and can neither overtake nor be overwritten by
   *  an earlier retry. */
  async function dispatchVisualBlocksInSourceOrder(context) {
    const failures = [];
    const results = [];
    let finalOutcome = null;
    let ownsTerminalOutcome = true;
    let quiet = true;

    for (let sourceIndex = 0; sourceIndex < context.blocks.length; sourceIndex += 1) {
      const block = context.blocks[sourceIndex];
      const rawIndex = Number.isInteger(block && block.raw_fence_index)
        ? block.raw_fence_index : sourceIndex;
      // The pane is shared by every Dialogue. Re-check at the last possible
      // point before each source action so a stale loop can never clear,
      // update, or annotate the view that navigation has since activated.
      if (!_originIsActive(context)) {
        const orphaned = _coldOrphanOutcome(context, rawIndex);
        failures.push({
          rawIndex,
          outcome: orphaned || _originInactiveOutcome(
            context,
            `Visual fence ${rawIndex} was not applied because its originating `
              + 'Dialogue was no longer active.',
          ),
        });
        quiet = quiet && !!orphaned;
        break;
      }
      const blockContext = Object.assign({}, context, { blocks: [block] });
      const result = await Promise.resolve(
        context.panel.onBridgeUpdate({
          ora_visual_blocks: [block],
          ora_visual_dispatch_key: _visualBlockDispatchKey(
            context, block, sourceIndex,
          ),
        }),
      );
      const settlement = await settleDispatchResult(result, blockContext, {
        persist: false,
        surface: false,
        log: false,
        publishMemory: false,
      });
      results.push(settlement && settlement.result);
      if (settlement && settlement.hadNarrowing) {
        ownsTerminalOutcome = ownsTerminalOutcome
          && settlement.ownsTerminalOutcome === true;
      }
      if (settlement && settlement.pending) {
        return {
          pending: true,
          ownsTerminalOutcome: false,
          outcome: null,
          result: results,
        };
      }
      const outcome = settlement && settlement.outcome;
      if (outcome && outcome.state === 'failed') {
        failures.push({
          rawIndex,
          outcome,
          terminalPersisted: settlement.terminalPersisted === true,
        });
        quiet = quiet && settlement.quiet === true;
        if (!_originIsActive(context)) break;
      } else if (outcome) {
        finalOutcome = outcome;
      }
    }

    const terminalOutcome = failures.length
      ? _combinedFailureOutcome(failures, context.meta)
      : (finalOutcome || { state: 'ready' });
    const operationKey = _legibilityDispatchKey(context && context.meta);
    const sequenceOperation = operationKey
      ? _assistantSequenceOperations.get(operationKey) : null;
    const latestConfirmedPersistedOutcome = sequenceOperation
      ? sequenceOperation.latestConfirmedPersistedOutcome
      : _canonicalOutcome(context && context.meta && context.meta.visualOutcome);
    // A fence-local authoritative failure is still terminal disk truth only
    // while no later sibling's confirmed retry has superseded it. Otherwise
    // the assistant-wide publisher must save the combined result once.
    const terminalPersisted = failures.length === 1
      && failures[0].terminalPersisted === true
      && _sameCanonicalOutcome(
        terminalOutcome, latestConfirmedPersistedOutcome,
      );
    return {
      pending: false,
      ownsTerminalOutcome,
      terminalPersisted,
      quiet: failures.length > 0 && quiet,
      outcome: terminalOutcome,
      result: results,
    };
  }

  function _surfaceOutcomeSaveFailure(context, saveResult) {
    if (!context || !context.meta || !context.meta.conversationId) return;
    const detail = saveResult && saveResult.error
      || 'The visual result could not be saved.';
    console.warn('[v3-visual-dispatch] terminal outcome was not published:', detail);
    const panel = window.OraPanels && window.OraPanels.visual;
    if (_originIsActive(context) && panel && typeof panel.showError === 'function') {
      panel.showError('Visual failed: ' + detail);
    }
  }

  function _publishConfirmedTerminal(settlement, context, operation, outcome) {
    settlement.outcome = outcome;
    settlement.canonicalConfirmed = true;
    if (operation) {
      operation.latestConfirmedPersistedOutcome = outcome;
      _broadcastAssistantSequenceTerminal(operation, outcome, true);
      return;
    }
    if (context.meta) {
      context.meta.visualOutcome = outcome;
      _notifyNarrowedOutcome(context.meta, null, outcome, undefined);
    }
  }

  async function publishDispatchSettlement(settlement, context, operation) {
    if (!settlement || settlement.pending
        || settlement.ownsTerminalOutcome === false || !settlement.outcome) return;
    if (operation && operation.published === true) return;
    if (operation) operation.published = true;
    const outcome = settlement.outcome;
    if (outcome.state === 'failed') {
      settlement.outcome = surfaceDispatchFailure(
        outcome.reason,
        context.meta,
        outcome.stage,
        context.key,
        undefined,
        {
          surface: settlement.quiet !== true,
          log: settlement.quiet !== true,
          authoritativeOutcome: outcome,
          preserveAuthoritativeOutcome: settlement.terminalPersisted === true,
          persist: false,
          publishMemory: false,
        },
      );
      if (settlement.terminalPersisted === true) {
        _publishConfirmedTerminal(
          settlement, context, operation, settlement.outcome,
        );
        return;
      }
      const saveResult = await persistOutcome(context.meta, settlement.outcome);
      if (!saveResult.ok) {
        settlement.canonicalConfirmed = false;
        settlement.outcome = context.meta && context.meta.visualOutcome || null;
        _surfaceOutcomeSaveFailure(context, saveResult);
        return;
      }
      _publishConfirmedTerminal(
        settlement, context, operation, saveResult.visual_outcome,
      );
      return;
    }
    const saveResult = await persistOutcome(context.meta, outcome);
    if (!saveResult.ok) {
      settlement.canonicalConfirmed = false;
      settlement.outcome = context.meta && context.meta.visualOutcome || null;
      _surfaceOutcomeSaveFailure(context, saveResult);
      return;
    }
    _publishConfirmedTerminal(
      settlement, context, operation, saveResult.visual_outcome,
    );
  }

  async function insertImageArtifacts(blocks, context) {
    if (!window.OraCanvas
        || typeof window.OraCanvas.insertAssistantImage !== 'function') {
      throw new Error('The Exhibits image inserter is unavailable.');
    }
    const inserted = [];
    for (const block of blocks) {
      if (!_originIsActive(context)) {
        throw new Error(
          'The stored image was not inserted because its originating Dialogue was no longer active.'
        );
      }
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
      if (!_originIsActive(context)) {
        throw new Error(
          'The stored image was not inserted because its originating Dialogue was no longer active.'
        );
      }
      const placed = await window.OraCanvas.insertAssistantImage(file, artifact);
      if (!placed) throw new Error('The Exhibits pane rejected the generated image.');
      inserted.push(placed);
    }
    return inserted;
  }

  async function _runAssistantSequence(context, imageBlocks) {
    if (context.blocks.length
        && (!context.panel || typeof context.panel.onBridgeUpdate !== 'function')) {
      throw new Error('The Exhibits pane is unavailable.');
    }
    const visualOperation = context.blocks.length
      ? dispatchVisualBlocksInSourceOrder(context)
      : Promise.resolve({
        pending: false,
        ownsTerminalOutcome: true,
        outcome: { state: 'ready' },
        result: [],
      });
    // Keep analytical and generated-image work at their established relative
    // timing, but wait for both branches before the assistant-wide outcome is
    // published. Capturing both rejections prevents one branch from settling
    // the operation while the other can still mutate the shared pane.
    const visualCapture = Promise.resolve(visualOperation).then(
      (value) => ({ value }), (error) => ({ error }),
    );
    const imageCapture = (imageBlocks.length
      ? insertImageArtifacts(imageBlocks, context)
      : Promise.resolve([])).then(
      (value) => ({ value }), (error) => ({ error }),
    );
    const captures = await Promise.all([visualCapture, imageCapture]);
    if (captures[0].error) throw captures[0].error;
    if (captures[1].error) throw captures[1].error;
    const settlement = captures[0].value;
    if (!context.blocks.length) {
      settlement.outcome = surfaceDispatchResult(
        captures[1].value, context.meta, context.key, undefined,
        { persist: false, surface: false, log: false, publishMemory: false },
      );
    }
    return settlement;
  }

  function _cleanupAssistantSequence(operation) {
    if (!operation || operation.settled !== true || operation.consumerCount !== 0) return;
    if (_assistantSequenceOperations.get(operation.key) === operation) {
      _assistantSequenceOperations.delete(operation.key);
    }
  }

  function _applyAssistantSequenceTerminal(operation, meta, outcome, notify) {
    if (!operation || !meta || !outcome
        || operation.terminalObservedMetas.has(meta)) return;
    meta.visualOutcome = outcome;
    operation.terminalObservedMetas.add(meta);
    if (notify) _notifyNarrowedOutcome(meta, null, outcome, undefined);
  }

  function _broadcastAssistantSequenceTerminal(operation, outcome, notify) {
    if (!operation || !outcome) return;
    operation.consumers.forEach((consumer) => {
      _applyAssistantSequenceTerminal(
        operation, consumer && consumer.meta, outcome, notify,
      );
    });
  }

  function _observeAssistantSequence(operation, context) {
    if (!operation.latestConfirmedPersistedOutcome) {
      operation.latestConfirmedPersistedOutcome = _canonicalOutcome(
        context && context.meta && context.meta.visualOutcome,
      );
    }
    const metaAlreadyObserved = Array.from(operation.consumers).some((consumer) => (
      consumer && consumer.meta && consumer.meta === context.meta
    ));
    operation.consumers.add(context);
    operation.consumerCount += 1;
    if (!metaAlreadyObserved) {
      operation.narrowingUpdates.forEach((update) => {
        _applyNarrowingOutcome(
          context.meta,
          update.envelope,
          update.outcome,
          update.visualBlockIndex,
        );
      });
    }
    operation.promise.then((settlement) => {
      if (context !== operation.ownerContext
          && context.meta && settlement && settlement.outcome
          && settlement.canonicalConfirmed === true) {
        _applyAssistantSequenceTerminal(
          operation, context.meta, settlement.outcome, true,
        );
      }
    }).finally(() => {
      operation.consumers.delete(context);
      operation.consumerCount = Math.max(0, operation.consumerCount - 1);
      _cleanupAssistantSequence(operation);
    });
  }

  function _startAssistantSequence(context, imageBlocks, operationKey) {
    const operation = {
      key: operationKey,
      ownerContext: context,
      consumers: new Set(),
      consumerCount: 0,
      narrowingUpdates: [],
      latestConfirmedPersistedOutcome: _canonicalOutcome(
        context && context.meta && context.meta.visualOutcome,
      ),
      terminalObservedMetas: new Set(),
      published: false,
      settled: false,
      promise: null,
    };
    _assistantSequenceOperations.set(operationKey, operation);
    if (context.blocks.length) _retainLegibilityDispatch(context);
    operation.promise = Promise.resolve().then(() => (
      _runAssistantSequence(context, imageBlocks)
    )).then(async (settlement) => {
      await publishDispatchSettlement(settlement, context, operation);
      return settlement;
    }, async (error) => {
      const outcome = surfaceDispatchFailure(
        'The visual request could not be applied: ' + (error && error.message || error),
        context.meta,
        undefined,
        context.key,
        undefined,
        {
          persist: false,
          surface: false,
          log: false,
          publishMemory: false,
        },
      );
      const settlement = {
        pending: false,
        ownsTerminalOutcome: true,
        outcome,
        result: [],
      };
      await publishDispatchSettlement(settlement, context, operation);
      return settlement;
    }).finally(() => {
      if (context.blocks.length) _releaseLegibilityDispatch(context);
      operation.settled = true;
      _cleanupAssistantSequence(operation);
    });
    _observeAssistantSequence(operation, context);
    return operation;
  }

  /** Extract + hand off to the visual panel. Returns the number of blocks
   *  found (0 = nothing to do). Same key twice in a row is a no-op. */
  function dispatch(text, key, meta) {
    setActiveKey(key);
    const blocks = extractBlocks(text);
    const imageBlocks = extractImageBlocks(text);
    const blockCount = blocks.length + imageBlocks.length;
    if (blockCount === 0) return 0;
    const operationKey = _legibilityDispatchKey(meta);
    const sharedOperation = operationKey
      ? _assistantSequenceOperations.get(operationKey) : null;
    const panel = window.OraPanels && window.OraPanels.visual;
    const context = { text, key, meta, blocks, panel };
    if (sharedOperation) {
      _lastKey = key != null ? key : null;
      _observeAssistantSequence(sharedOperation, context);
      return blockCount;
    }
    if (!operationKey && blocks.length
        && (!panel || typeof panel.onBridgeUpdate !== 'function')) {
      surfaceDispatchFailure('The Exhibits pane is unavailable.', meta, undefined, key);
      return blockCount;
    }
    if (key != null && key === _lastKey) return blockCount;
    _lastKey = key != null ? key : null;
    if (operationKey) {
      _startAssistantSequence(context, imageBlocks, operationKey);
      return blockCount;
    }

    // Legacy callers without durable assistant identity cannot participate in
    // the shared-operation map, but they retain the same source-order and
    // terminal behavior.
    if (blocks.length) _retainLegibilityDispatch(context);
    _runAssistantSequence(context, imageBlocks).then(async (settlement) => {
      await publishDispatchSettlement(settlement, context);
    }).catch(async (error) => {
      const outcome = surfaceDispatchFailure(
        'The visual request could not be applied: ' + (error && error.message || error),
        meta,
        undefined,
        key,
        undefined,
        {
          persist: false,
          surface: false,
          log: false,
          publishMemory: false,
        },
      );
      await publishDispatchSettlement({
        pending: false,
        ownsTerminalOutcome: true,
        outcome,
        result: [],
      }, context);
    }).finally(() => {
      if (blocks.length) _releaseLegibilityDispatch(context);
    });
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
