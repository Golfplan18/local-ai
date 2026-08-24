/* V3 Backlog 2B + 8 + 9 — Conversation loading, output-pane rendering,
 * turn navigation, and per-conversation input drafts.
 *
 * Closes the navigation loop: when the sidebar dispatches
 * `ora:conversation-selected`, this module fetches the conversation,
 * renders its turns into the output pane (one turn at a time, with
 * first/previous/next/last navigation), wires the prompt overlay to show that
 * turn's user prompt, and restores the saved draft for the
 * conversation's left input area.
 *
 * Operating contract:
 *   - One module-level `state` object tracks the active conversation,
 *     the turn-index cursor, and the current snapshot of messages.
 *   - "Turn" = one user-prompt + one assistant-response pair. Welcome /
 *     bootstrap-only conversations may have a standalone assistant
 *     message; that's still one turn with `user: null`.
 *   - The output pane shows the assistant text of the current turn.
 *   - The prompt overlay shows the user prompt of the current turn.
 *   - First/previous/next/last controls move the turn cursor.
 *   - On submit, the inline script calls OraConversation.appendUser /
 *     appendAssistant to update state + re-render.
 *   - Drafts: keyed by conversation_id in localStorage; saved on input
 *     (debounced), cleared on submit, restored on selection.
 *
 * Public API on window.OraConversation:
 *   load(conversation_id)
 *   showTurn(index)
 *   appendUser(text)         // optimistic; submit just sent
 *   appendAssistant(text)    // pipeline completed
 *   saveDraft(conversation_id, text)
 *   loadDraft(conversation_id)
 *   setPrivacyTag(tag)
 *   closeConversation(conversation_id)
 *   deleteForever(conversation_id)
 *   getActiveConversationId()
 *   getActiveTag()
 *   getTurnCount()
 *   getCurrentTurn()
 */
(() => {
  'use strict';

  const DRAFT_KEY_PREFIX = 'ora-v3-draft-';
  const DRAFT_DEBOUNCE   = 400;
  const LIFECYCLE_CHANNEL_NAME = 'ora-v3-conversation-lifecycle';
  const LIFECYCLE_STORAGE_KEY = 'ora-v3-conversation-lifecycle-pulse';
  const LIFECYCLE_PULSE_LIMIT = 100;

  // Markdown → HTML renderer for loaded turn content. The V3 page does not
  // include chat-panel.js, so its _md is unavailable. This version handles
  // headers, lists, code, bold/italic, pipe tables, blockquotes — and
  // crucially strips spurious newlines around block elements so the
  // browser's built-in margins don't get doubled by stray <br>s.
  const _md = (text) => {
    if (typeof text !== 'string') return '';
    let s = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // Fenced code blocks
    s = s.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, _lang, code) =>
      `<pre><code>${code.trimEnd()}</code></pre>`
    );
    // Inline code
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bold and italic
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Pipe tables — a header row, a separator row (---|---|---), then data rows
    s = s.replace(/((?:^\|.+\|[ \t]*\n)+)/gm, (block) => {
      const lines = block.trim().split('\n');
      const sepIdx = lines.findIndex(l => /^\|[\s\-:|]+\|$/.test(l.trim()));
      if (sepIdx < 1) return block; // not a real table — leave alone
      const head = lines[0].trim().slice(1, -1)
        .split('|').map(c => `<th>${c.trim()}</th>`).join('');
      const body = lines.slice(sepIdx + 1).map(row =>
        `<tr>${row.trim().slice(1, -1).split('|').map(c => `<td>${c.trim()}</td>`).join('')}</tr>`
      ).join('');
      return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>\n`;
    });

    // Horizontal rule — a line of three or more dashes (or asterisks/underscores)
    // by itself becomes <hr>
    s = s.replace(/^(---+|\*\*\*+|___+)$/gm, '<hr>');

    // Blockquotes (lines that originally started with > — now &gt;)
    s = s.replace(/^&gt; ?(.*)$/gm, '<blockquote>$1</blockquote>');
    // Merge consecutive blockquote lines into one block
    s = s.replace(/<\/blockquote>\n<blockquote>/g, '<br>');

    // Headers
    s = s.replace(/^###### (.+)$/gm, '<h6>$1</h6>');
    s = s.replace(/^##### (.+)$/gm, '<h5>$1</h5>');
    s = s.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
    s = s.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    s = s.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    s = s.replace(/^# (.+)$/gm, '<h1>$1</h1>');

    // Bullet lists — wrap consecutive `<li>` runs in `<ul>` and strip
    // intervening newlines so the items don't get extra <br>s later.
    s = s.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
    s = s.replace(/(<li>.*<\/li>(\n|$))+/g, m => `<ul>${m.replace(/\n/g, '')}</ul>`);
    // Numbered lists — same pattern. Skip runs already wrapped (no newlines
    // between items means they're already inside a <ul>).
    s = s.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
    s = s.replace(/(<li>.*<\/li>(\n|$))+/g, m => {
      if (!m.includes('\n')) return m; // already wrapped above
      return `<ol>${m.replace(/\n/g, '')}</ol>`;
    });

    // Strip newlines that flank block-level elements — without this, the
    // \n -> <br> pass below would add a redundant <br> on top of the
    // element's own CSS margin, producing the "everything is too spread out"
    // problem. Includes <hr> and <br> so they don't accumulate either.
    s = s.replace(/\n*(<\/?(?:h[1-6]|ul|ol|li|table|thead|tbody|tr|th|td|pre|blockquote|hr|br)[^>]*\/?>)\n*/g, '$1');

    // Remaining newlines: blank-line gap → paragraph break, single → <br>
    s = s.replace(/\n{2,}/g, '<br><br>');
    s = s.replace(/\n/g, '<br>');

    return s;
  };

  // ── Module state ────────────────────────────────────────────────────────
  const state = {
    activeConversationId: null,
    activeParentConversationId: null,
    activeTag:            '',
    activeTitle:          '',
    readOnlySource:       false, // Library-backed engrams/archives are not mutable Dialogues.
    hasEnvelope:          false, // true=persisted, false=fresh client id, null=load unresolved.
    messages:             [],   // raw conversation.json messages[]
    turns:                [],   // grouped: [{user, assistant}, ...]
    currentTurnIndex:     0,    // -1 if no turns
    visualState:          null,
    visualReadyTurnIndex: -1,
  };
  let loadEpoch = 0;
  let pendingLoadId = null;
  const retiredConversationIds = new Set();
  const lifecycleRequestCounts = new Map();
  let lifecycleChannel = null;
  const lifecyclePulseSource = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  const seenLifecyclePulses = new Set();
  const seenLifecyclePulseOrder = [];

  // ── DOM refs (looked up lazily so the module loads before DOM ready) ───
  let outputPane     = null;
  let outputContent  = null;
  let displayName    = null;
  let modeIcon       = null;
  let actionsButton  = null;
  let navFirst       = null;
  let navBack        = null;
  let navForward     = null;
  let navLast        = null;
  let turnPosition   = null;
  let timestampEl    = null;
  let leftInput      = null;

  const refreshDOMRefs = () => {
    outputPane    = document.querySelector('.output-pane');
    outputContent = document.querySelector('.output-content');
    displayName   = document.getElementById('outputPaneDisplayName');
    modeIcon      = document.getElementById('outputPaneModeIcon');
    actionsButton = document.getElementById('outputPaneActionsBtn');
    navFirst      = document.getElementById('outputPaneNavFirst');
    navBack       = document.getElementById('outputPaneNavBack');
    navForward    = document.getElementById('outputPaneNavForward');
    navLast       = document.getElementById('outputPaneNavLast');
    turnPosition  = document.getElementById('outputPaneTurnPosition');
    timestampEl   = document.getElementById('outputPaneTimestamp');
    leftInput     = document.querySelector('.input-pane textarea');
  };

  const lifecycleRequestActive = (conversationId) => (
    !!conversationId && (lifecycleRequestCounts.get(conversationId) || 0) > 0
  );

  const syncInquiryReadOnlyState = () => {
    if (!leftInput) return;
    const readOnly = !!(
      state.readOnlySource
      || pendingLoadId
      || lifecycleRequestActive(state.activeConversationId)
    );
    leftInput.readOnly = readOnly;
    leftInput.setAttribute('aria-readonly', readOnly ? 'true' : 'false');
  };

  const setLifecycleRequestActive = (conversationId, active) => {
    if (!conversationId) return;
    const count = lifecycleRequestCounts.get(conversationId) || 0;
    if (active) lifecycleRequestCounts.set(conversationId, count + 1);
    else if (count > 1) lifecycleRequestCounts.set(conversationId, count - 1);
    else lifecycleRequestCounts.delete(conversationId);
    refreshDOMRefs();
    syncInquiryReadOnlyState();
    if (conversationId === state.activeConversationId) {
      renderHeader();
      updateForkAvailability();
    }
    document.dispatchEvent(new CustomEvent('ora:conversation-lifecycle-state', {
      detail: {
        conversation_id: conversationId,
        active: lifecycleRequestActive(conversationId),
      },
    }));
  };

  // ── Turn grouping ──────────────────────────────────────────────────────
  const groupTurns = (messages) => {
    const turns = [];
    let pendingUser = null;
    if (!Array.isArray(messages)) return turns;
    for (const m of messages) {
      if (!m || typeof m !== 'object') continue;
      if (m.role === 'user') {
        // If we already have a pending user (rare — two user messages
        // in a row), close the previous as a userful turn with no
        // assistant before recording the new pending.
        if (pendingUser) {
          turns.push({ user: pendingUser, assistant: null });
        }
        pendingUser = m;
      } else if (m.role === 'assistant') {
        turns.push({ user: pendingUser, assistant: m });
        pendingUser = null;
      }
    }
    if (pendingUser) {
      turns.push({ user: pendingUser, assistant: null });
    }
    return turns;
  };

  // ── Render ─────────────────────────────────────────────────────────────
  const formatTimestamp = (iso) => {
    if (!iso || typeof iso !== 'string') return '—';
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return iso;
      // Short, locale-aware date with no time: Mar 2, 24 in en-US.
      return d.toLocaleDateString(undefined, {
        month: 'short', day: 'numeric', year: '2-digit',
      });
    } catch (e) {
      return iso;
    }
  };

  const modeIconSymbolFor = (tag) => {
    if (tag === 'stealth') return '⊘';   // prohibited-style indicator
    if (tag === 'private') return '◎';   // private brand symbol
    return '';                            // standard: no icon
  };

  const renderHeader = () => {
    if (!displayName) return;
    const renameInput = displayName.querySelector('.output-pane-display-name-input');
    const preserveRename = !!renameInput
      && displayName.classList.contains('is-renaming')
      && renameInput.dataset.conversationId === state.activeConversationId
      && !pendingLoadId;
    if (!preserveRename) {
      displayName.classList.remove('is-renaming');
      displayName.textContent = state.activeTitle || (state.activeConversationId || 'Dialogue');
    }
    const liveActionable = !!state.activeConversationId
      && !state.readOnlySource
      && !pendingLoadId;
    const lifecycleBusy = lifecycleRequestActive(state.activeConversationId);
    const renameable = liveActionable
      && !lifecycleBusy
      && state.hasEnvelope === true;
    displayName.classList.toggle('is-clickable', renameable);
    // A title too long for the header is unreadable without this; the rename
    // hint rides along rather than replacing it.
    const fullTitle = displayName.textContent || '';
    if (renameable) {
      displayName.title = fullTitle ? fullTitle + '\n(click to rename)' : 'Click to rename';
    } else if (fullTitle) {
      displayName.title = fullTitle;
    } else {
      displayName.removeAttribute('title');
    }
    if (modeIcon) {
      modeIcon.textContent = modeIconSymbolFor(state.activeTag);
      modeIcon.dataset.tag = state.activeTag || '';
    }
    if (actionsButton) {
      // Close/Delete are meaningful even for a fresh zero-turn Dialogue;
      // only Rename requires a known durable envelope. Keeping this trigger
      // visible also avoids stranding artifact-created Dialogues whose
      // producer has not yet reported envelope creation to the browser.
      actionsButton.hidden = !liveActionable;
      actionsButton.disabled = lifecycleBusy;
      actionsButton.setAttribute('aria-disabled', lifecycleBusy ? 'true' : 'false');
      if (!liveActionable || lifecycleBusy) {
        actionsButton.setAttribute('aria-expanded', 'false');
        closeOutputActionsMenu();
      }
    }
    const total = state.turns.length;
    if (turnPosition) {
      // The word "turn" adds nothing beside the arrows that step through
      // them, and the header is the scarcest space in the pane. It stays on
      // the accessible name, where "1 of 12" alone would be ambiguous.
      if (total === 0) {
        turnPosition.textContent = '\u2014';
        turnPosition.setAttribute('aria-label', 'no turns');
      } else {
        turnPosition.textContent = `${state.currentTurnIndex + 1} of ${total}`;
        turnPosition.setAttribute('aria-label', `turn ${state.currentTurnIndex + 1} of ${total}`);
      }
    }
    const atFirst = total === 0 || state.currentTurnIndex <= 0;
    const atLast = total === 0 || state.currentTurnIndex >= total - 1;
    if (navFirst)   navFirst.disabled   = atFirst;
    if (navBack)    navBack.disabled    = atFirst;
    if (navForward) navForward.disabled = atLast;
    if (navLast)    navLast.disabled    = atLast;

    // Timestamp from current turn's assistant message (preferred) or
    // user message if no assistant yet.
    if (timestampEl) {
      const t = state.turns[state.currentTurnIndex];
      let iso = null;
      if (t) {
        if (t.assistant && t.assistant.timestamp) iso = t.assistant.timestamp;
        else if (t.user && t.user.timestamp)       iso = t.user.timestamp;
      }
      timestampEl.textContent = formatTimestamp(iso);
    }
  };

  const updateForkAvailability = () => {
    const forkButton = document.querySelector('.sidebar-fork-thread-cmd');
    if (!forkButton) return;
    const enabled = canForkActive();
    forkButton.disabled = !enabled;
    forkButton.setAttribute('aria-disabled', enabled ? 'false' : 'true');
    forkButton.title = enabled
      ? 'Fork current Dialogue'
      : 'Fork becomes available after the first turn';
  };

  const canForkActive = () => (
    !!state.activeConversationId
      && !state.readOnlySource
      && !pendingLoadId
      && !lifecycleRequestActive(state.activeConversationId)
      && state.turns.length > 0
  );

  const privacyAllowsFork = (sourceTag, targetTag) => {
    if (!['', 'private', 'stealth'].includes(sourceTag)
        || !['', 'private', 'stealth'].includes(targetTag)) return false;
    if (sourceTag === 'stealth') return targetTag === 'stealth';
    if (sourceTag === 'private') {
      return targetTag === 'private' || targetTag === 'stealth';
    }
    return true;
  };

  const canForkAs = (targetTag) => (
    canForkActive() && privacyAllowsFork(state.activeTag, targetTag)
  );

  const emitCurrentTurnChanged = (turn) => {
    document.dispatchEvent(new CustomEvent('ora:current-turn-changed', {
      detail: {
        conversation_id: state.activeConversationId,
        turn_index: state.currentTurnIndex,
        turn_count: state.turns.length,
        turn: turn || null,
      },
    }));
  };

  const renderTurn = () => {
    const visualDispatchKey = `${state.activeConversationId || ''}#${state.currentTurnIndex}`;
    if (window.OraV3VisualDispatch
        && typeof window.OraV3VisualDispatch.setActiveKey === 'function') {
      // Invalidate any slow legibility retry as soon as navigation changes
      // the displayed turn, including pending and visual-free destinations.
      window.OraV3VisualDispatch.setActiveKey(visualDispatchKey);
    }
    if (!outputContent) return;
    const t = state.turns[state.currentTurnIndex];
    outputContent.replaceChildren();

    if (!t) {
      const empty = document.createElement('div');
      empty.className = 'output-turn output-turn-empty';
      empty.textContent = '';
      outputContent.appendChild(empty);
      if (window.OraPromptOverlay && typeof window.OraPromptOverlay.setPrompt === 'function') {
        window.OraPromptOverlay.setPrompt('');
      }
      emitCurrentTurnChanged(null);
      return;
    }

    // Assistant text of the current turn — what the output pane is for.
    if (t.assistant) {
      let content = t.assistant.content || '';
      // Model-emitted ora-visual envelopes: hand the turn's blocks to the
      // visual pane (canvas_action semantics, deduped per conversation+turn)
      // and swap the raw JSON fences for a one-line marker in the transcript.
      if (window.OraV3VisualDispatch
          && state.visualReadyTurnIndex === state.currentTurnIndex) {
        const assistantIndex = state.turns
          .slice(0, state.currentTurnIndex + 1)
          .filter((turn) => turn && turn.assistant).length - 1;
        const persistedOutcome = t.assistant.visual_outcome;
        const blockCount = window.OraV3VisualDispatch.dispatch(content, visualDispatchKey, {
          conversationId: state.activeConversationId,
          assistantIndex,
          visualOutcome: persistedOutcome,
          onNarrowedEnvelopePersisted(envelope, outcome) {
            if (!t.assistant) return;
            t.assistant.content = window.OraV3VisualDispatch.replaceBlocksWithEnvelope(
              t.assistant.content || '', envelope,
            );
            t.assistant.visual_outcome = outcome;
          },
        });
        if (blockCount === 0
            && persistedOutcome
            && persistedOutcome.state === 'building'
            && typeof window.OraV3VisualDispatch.persistOutcome === 'function') {
          // Re-opening a stalled turn is the recovery action. If its durable
          // text has no envelope to insert, resolve the ambiguity visibly
          // instead of leaving an eternal spinner in history.
          window.OraV3VisualDispatch.persistOutcome(
            { conversationId: state.activeConversationId, assistantIndex },
            {
              state: 'failed',
              stage: 'open',
              reason: 'No visual envelope was available when this turn was reopened.',
            },
          );
        }
        content = window.OraV3VisualDispatch.stripBlocks(content);
      }
      const outcome = t.assistant.visual_outcome;
      if (outcome && outcome.state === 'failed'
          && window.OraPanels && window.OraPanels.visual
          && typeof window.OraPanels.visual.showError === 'function') {
        window.OraPanels.visual.showError(
          'Visual failed: ' + (outcome.reason || 'The visual could not be inserted.'),
        );
      }
      const block = document.createElement('div');
      block.className = 'output-turn output-turn-assistant';
      block.innerHTML = _md(content);
      outputContent.appendChild(block);
    } else {
      const pending = document.createElement('div');
      pending.className = 'output-turn output-turn-pending';
      pending.textContent = '…awaiting response';
      outputContent.appendChild(pending);
    }

    // Prompt overlay reflects the SAME turn's user prompt.
    if (window.OraPromptOverlay && typeof window.OraPromptOverlay.setPrompt === 'function') {
      const promptText = t.user ? (t.user.content || '') : '';
      window.OraPromptOverlay.setPrompt(promptText || '(no prompt — bootstrap or welcome content)');
    }
    emitCurrentTurnChanged(t);
  };

  const renderAll = () => {
    refreshDOMRefs();
    syncInquiryReadOnlyState();
    if (outputPane) outputPane.classList.remove('has-content');
    renderHeader();
    renderTurn();
    updateForkAvailability();
  };

  const makeConversationId = () => {
    const stamp = new Date().toISOString()
      .replace(/[-:]/g, '')
      .replace(/\.\d+Z$/, 'Z')
      .replace('T', '-')
      .replace('Z', '');
    const rand = Math.random().toString(36).slice(2, 8);
    return `thread-${stamp}-${rand}`;
  };

  const clearVisualPane = () => {
    try {
      if (window.OraV3VisualDispatch
          && typeof window.OraV3VisualDispatch.resetDedupe === 'function') {
        window.OraV3VisualDispatch.resetDedupe();
      }
      if (window.OraCanvas && typeof window.OraCanvas.reset === 'function') {
        window.OraCanvas.reset();
        return;
      }
      if (window.OraPanels && window.OraPanels.visual) {
        const visual = window.OraPanels.visual;
        if (typeof visual.resetCanvas === 'function') {
          visual.resetCanvas();
        }
      }
    } catch (e) {
      console.warn('[v3-conversation] visual clear failed:', e);
    }
  };

  const clearInputAddOns = () => {
    try {
      if (window.OraInputState) {
        if (typeof window.OraInputState.clearSelection === 'function') {
          window.OraInputState.clearSelection();
        } else {
          if (typeof window.OraInputState.clearFramework === 'function') {
            window.OraInputState.clearFramework();
          }
          if (typeof window.OraInputState.clearAnalysisMode === 'function') {
            window.OraInputState.clearAnalysisMode();
          }
        }
      }
      if (window.OraInputAttachments && typeof window.OraInputAttachments.clear === 'function') {
        window.OraInputAttachments.clear();
      }
    } catch (e) {
      console.warn('[v3-conversation] input reset failed:', e);
    }
  };

  const focusMainInput = () => {
    refreshDOMRefs();
    if (!leftInput) return;
    setTimeout(() => {
      try {
        leftInput.focus();
        const len = leftInput.value.length;
        leftInput.setSelectionRange(len, len);
      } catch (e) {}
    }, 0);
  };

  const startFresh = async (detail = {}) => {
    if (detail.bootstrap === true || detail.dossier === true) return;
    if (!detail.skip_visual_flush
        && window.OraCanvas && typeof window.OraCanvas.flushDraft === 'function') {
      try {
        await window.OraCanvas.flushDraft();
      } catch (e) {
        console.warn('[v3-conversation] new Dialogue draft flush failed:', e);
        return false;
      }
    }
    refreshDOMRefs();
    const cancelledLoadId = pendingLoadId;
    loadEpoch += 1;
    pendingLoadId = null;
    if (cancelledLoadId) {
      document.dispatchEvent(new CustomEvent('ora:conversation-loading-state', {
        detail: { conversation_id: cancelledLoadId, loading: false, cancelled: true },
      }));
    }

    flushDraftTimer();
    if (state.activeConversationId && leftInput && !state.readOnlySource) {
      saveDraft(state.activeConversationId, leftInput.value);
    }

    const requestedId = detail.conversation_id || makeConversationId();
    const id = retiredConversationIds.has(requestedId)
      ? makeConversationId()
      : requestedId;
    // Generic New always means Standard. Private and Stealth creation are
    // explicit actions in their spine menus, so the loaded Dialogue's body
    // class must never leak into a new Dialogue as ambient creation state.
    const requestedTag = Object.prototype.hasOwnProperty.call(detail, 'tag')
      ? detail.tag
      : '';
    const tag = requestedTag === 'stealth' || requestedTag === 'private'
      ? requestedTag
      : '';
    state.activeConversationId = id;
    state.activeParentConversationId = null;
    state.activeTag = tag;
    state.activeTitle = 'New Dialogue';
    state.readOnlySource = false;
    state.hasEnvelope = false;
    state.messages = [];
    state.turns = [];
    state.currentTurnIndex = 0;
    window._oraLatestCanvasBytes = null;

    if (window.OraCanvas && typeof window.OraCanvas.setConversationContext === 'function') {
      window.OraCanvas.setConversationContext(id, tag);
    }

    if (leftInput) leftInput.value = '';
    clearInputAddOns();
    clearVisualPane();
    renderAll();
    document.dispatchEvent(new CustomEvent('ora:fresh-conversation-started', {
      detail: { conversation_id: id, tag, title: state.activeTitle },
    }));
    focusMainInput();
  };

  const forkActive = async (detail = {}) => {
    const parentId = state.activeConversationId;
    const parentTag = state.activeTag;
    const navigationEpoch = loadEpoch;
    if (!canForkActive()) {
      alert('A Dialogue needs at least one turn before it can be forked.');
      return;
    }
    const requestedTag = Object.prototype.hasOwnProperty.call(detail, 'tag')
      ? detail.tag
      : parentTag;
    if (!privacyAllowsFork(parentTag, requestedTag)) {
      alert('A fork cannot make parent content visible at a weaker privacy boundary.');
      return null;
    }
    try {
      const forkBody = {
        fork_point_turn_index: state.currentTurnIndex,
      };
      if (Object.prototype.hasOwnProperty.call(detail, 'tag')) {
        forkBody.tag = detail.tag;
      }
      const resp = await fetch(`/api/conversation/${encodeURIComponent(parentId)}/fork`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(forkBody),
      });
      let data = null;
      try { data = await resp.json(); } catch (e) {}
      if (!resp.ok || !data || !data.new_conversation_id) {
        throw new Error((data && data.error) || `HTTP ${resp.status}`);
      }
      const forkTag = Object.prototype.hasOwnProperty.call(data, 'tag')
        ? data.tag
        : (Object.prototype.hasOwnProperty.call(detail, 'tag')
            ? detail.tag
            : parentTag);
      if (typeof detail.draftMessage === 'string') {
        // Bind a transferred draft to the durable child identity before any
        // selection/load work can lose a navigation race.
        saveDraft(data.new_conversation_id, detail.draftMessage);
      }
      const navigationUnchanged = (
        loadEpoch === navigationEpoch
        && state.activeConversationId === parentId
        && !pendingLoadId
      );
      if (navigationUnchanged) {
        if (detail.await_selection) {
          await load(data.new_conversation_id, {
            draftMessage: typeof detail.draftMessage === 'string'
              ? detail.draftMessage : null,
          });
        } else {
          document.dispatchEvent(new CustomEvent('ora:conversation-selected', {
            detail: {
              conversation_id: data.new_conversation_id,
              tag: forkTag || '',
              title: data.new_conversation_id,
              source: detail.source || 'fork',
            },
          }));
        }
      } else {
        console.info(
          `[v3-conversation] fork ${data.new_conversation_id} created without `
          + 'changing a newer Dialogue selection'
        );
      }
      if (window.OraSidebar && typeof window.OraSidebar.refresh === 'function') {
        window.OraSidebar.refresh();
      }
      const selected = navigationUnchanged
        && (!detail.await_selection
          || state.activeConversationId === data.new_conversation_id);
      if (selected) focusMainInput();
      return Object.assign({}, data, { selected });
    } catch (e) {
      alert('Fork failed: ' + (e.message || e));
    }
  };

  // ── Conversation loading (Backlog 2B) ──────────────────────────────────
  const load = async (conversation_id, opts = {}) => {
    if (!conversation_id) return false;
    if (retiredConversationIds.has(conversation_id)) {
      console.error('[v3-conversation] refused to load retired Dialogue:', conversation_id);
      return false;
    }
    const epoch = ++loadEpoch;
    const previousVisualKey = `${state.activeConversationId || ''}#${state.currentTurnIndex}`;
    if (window.OraV3VisualDispatch
        && typeof window.OraV3VisualDispatch.setActiveKey === 'function') {
      window.OraV3VisualDispatch.setActiveKey(`loading:${conversation_id}:${epoch}`);
    }
    if (window.OraCanvas && typeof window.OraCanvas.flushDraft === 'function') {
      try {
        await window.OraCanvas.flushDraft();
      } catch (e) {
        console.warn('[v3-conversation] Excalidraw draft flush failed:', e);
        if (epoch === loadEpoch
            && window.OraV3VisualDispatch
            && typeof window.OraV3VisualDispatch.setActiveKey === 'function') {
          window.OraV3VisualDispatch.setActiveKey(previousVisualKey);
        }
        return false;
      }
      if (epoch !== loadEpoch) return null;
    }
    pendingLoadId = conversation_id;
    document.dispatchEvent(new CustomEvent('ora:conversation-loading-state', {
      detail: { conversation_id, loading: true },
    }));
    refreshDOMRefs();
    syncInquiryReadOnlyState();
    renderHeader();
    const forkButton = document.querySelector('.sidebar-fork-thread-cmd');
    if (forkButton) forkButton.disabled = true;

    // Save draft for the conversation we're leaving.
    flushDraftTimer();
    if (state.activeConversationId && leftInput && !state.readOnlySource) {
      saveDraft(state.activeConversationId, leftInput.value);
    }
    // Freeze live-only mutations while the target envelope is unresolved;
    // an archived_source result must never briefly inherit the previous
    // Dialogue's action affordances.
    if (displayName) displayName.classList.remove('is-clickable');
    if (actionsButton) actionsButton.hidden = true;
    closeOutputActionsMenu();

    let envelope = null;
    try {
      const r = await fetch(`/api/conversation/${encodeURIComponent(conversation_id)}`);
      if (r.ok) envelope = await r.json();
      else console.error(
        `[v3-conversation] load failed for ${conversation_id}: HTTP ${r.status}`
      );
    } catch (e) {
      console.error(`[v3-conversation] fetch failed for ${conversation_id}:`, e);
    }

    // A newer selection or successful Close/Delete retires this response.
    // Never let a delayed fetch reactivate an unavailable Dialogue.
    if (epoch !== loadEpoch
        || pendingLoadId !== conversation_id
        || retiredConversationIds.has(conversation_id)) return null;
    pendingLoadId = null;
    document.dispatchEvent(new CustomEvent('ora:conversation-loading-state', {
      detail: { conversation_id, loading: false },
    }));

    // A failed load is not a new active identity. Restore the previously
    // rendered Dialogue and tell the sidebar to undo its optimistic row state.
    if (!envelope || typeof envelope !== 'object') {
      renderAll();
      document.dispatchEvent(new CustomEvent('ora:conversation-tag-changed', {
        detail: {
          conversation_id: state.activeConversationId,
          tag: state.activeTag,
          source: 'conversation-load-failed-restore',
        },
      }));
      document.dispatchEvent(new CustomEvent('ora:conversation-load-failed', {
        detail: {
          conversation_id,
          active_conversation_id: state.activeConversationId,
        },
      }));
      return false;
    }

    state.activeConversationId = conversation_id;
    state.activeParentConversationId = (
      typeof envelope.parent_conversation_id === 'string'
      && envelope.parent_conversation_id.trim()
    ) ? envelope.parent_conversation_id.trim() : null;
    state.activeTag            = envelope.tag || '';
    state.readOnlySource       = !!envelope.archived_source;
    state.hasEnvelope          = true;
    state.messages             = envelope.messages || [];
    state.turns                = groupTurns(state.messages);
    state.visualState          = envelope.visual_state || null;
    state.visualReadyTurnIndex = -1;
    state.currentTurnIndex     = Math.max(0, state.turns.length - 1);
    if (Number.isInteger(opts.turnIndex)
        && opts.turnIndex >= 0
        && opts.turnIndex < state.turns.length) {
      state.currentTurnIndex = opts.turnIndex;
    }

    // Title derivation. A persisted display_name is authoritative; otherwise:
    //   * is_welcome envelopes → fixed "Welcome to Ora"
    //   * otherwise → first user message content, trimmed to 60 chars
    //   * fallback → conversation_id
    const storedDisplayName = envelope && typeof envelope.display_name === 'string'
      ? envelope.display_name.trim()
      : '';
    if (storedDisplayName) {
      state.activeTitle = storedDisplayName;
    } else if (envelope && envelope.is_welcome) {
      state.activeTitle = 'Welcome to Ora';
    } else {
      let derived = '';
      for (const m of state.messages) {
        if (m && m.role === 'user' && typeof m.content === 'string' && m.content.trim()) {
          const single = m.content.replace(/\s+/g, ' ').trim();
          derived = single.length > 60 ? single.slice(0, 59) + '…' : single;
          break;
        }
      }
      state.activeTitle = derived || conversation_id;
    }

    // The validated envelope commits the new active identity. Publish that
    // fact before restoring its editable draft or awaiting Exhibits so
    // turn-level controls from the previous Dialogue cannot leak into it.
    document.dispatchEvent(new CustomEvent('ora:conversation-tag-changed', {
      detail: {
        conversation_id,
        tag: state.activeTag,
        source: 'conversation-envelope',
      },
    }));

    // Library sources are genuinely read-only: do not surface or create an
    // unsendable local draft under a synthetic archive/engram id.
    if (state.readOnlySource) clearDraft(conversation_id);
    if (leftInput) {
      const suppliedDraft = typeof opts.draftMessage === 'string'
        ? opts.draftMessage
        : null;
      leftInput.value = state.readOnlySource
        ? ''
        : (suppliedDraft !== null ? suppliedDraft : loadDraft(conversation_id));
      if (!state.readOnlySource && suppliedDraft !== null) {
        saveDraft(conversation_id, suppliedDraft);
      }
    }
    if (window.OraCanvas && typeof window.OraCanvas.setConversationContext === 'function') {
      window.OraCanvas.setConversationContext(conversation_id, state.activeTag);
    }

    // The visual pane must track the turn being shown. Do not clear the
    // Excalidraw scene after changing context: a programmatic empty scene
    // must never become the target Dialogue's recovery draft. The exact load
    // below replaces it, or clears safely on a confirmed miss.
    window._oraLatestCanvasBytes = null;
    renderAll();
    const loadingCurrentDialogue = (
      state.turns.length === 0 || state.currentTurnIndex === state.turns.length - 1
    );
    await loadTurnCanvas(state.currentTurnIndex, {
      currentDialogue: loadingCurrentDialogue,
      preferDraft: !!(
        loadingCurrentDialogue
        && (!state.visualState || state.visualState.active_editor === 'excalidraw')
      ),
    });

    // Mark as read (best effort).
    if (envelope) {
      try {
        await fetch(`/api/conversation/${encodeURIComponent(conversation_id)}/mark-read`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        });
        // Tell the sidebar to refresh so the unread badge clears.
        document.dispatchEvent(new CustomEvent('ora:conversation-read', {
          detail: { conversation_id },
        }));
      } catch (e) {
        // Non-fatal.
      }
    }
    return true;
  };

  // Exit Stealth changes only which Dialogue is displayed. The Stealth
  // child remains intact: navigate to its readable direct parent at that
  // parent's latest turn, or start a fresh Standard Dialogue when lineage
  // is absent or no longer readable.
  const exitStealth = async (conversationId) => {
    const id = conversationId || state.activeConversationId;
    if (!id
        || id !== state.activeConversationId
        || state.activeTag !== 'stealth'
        || state.readOnlySource
        || pendingLoadId
        || lifecycleRequestActive(id)) return null;

    const parentId = state.activeParentConversationId;
    if (parentId && parentId !== id) {
      const selection = {
        conversation_id: parentId,
        tag: '',
        title: parentId,
        source: 'exit-stealth',
        await_selection: true,
      };
      document.dispatchEvent(new CustomEvent('ora:conversation-selected', {
        detail: selection,
      }));
      const loaded = selection.selection_promise
        ? await selection.selection_promise
        : null;
      if (loaded === true
          && state.activeConversationId === parentId
          && !pendingLoadId) {
        refreshSidebar();
        return { ok: true, destination: 'parent', conversation_id: parentId };
      }
      // A newer user navigation supersedes Exit. Only a confirmed missing /
      // unreadable parent while the child is still active gets the fallback.
      if (loaded === null || state.activeConversationId !== id || pendingLoadId) {
        return null;
      }
    }

    if (state.activeConversationId !== id) return null;
    await startFresh({ tag: '', source: 'exit-stealth' });
    return {
      ok: true,
      destination: 'fresh-standard',
      conversation_id: state.activeConversationId,
    };
  };

  // ── Turn navigation ────────────────────────────────────────────────────
  // Visual canvas tracks the active turn. Each turn was saved with a
  // timestamped .ora-canvas snapshot at submit time; the N-th snapshot
  // (sorted chronologically) corresponds to the N-th turn. The server's
  // /api/canvas/load endpoint resolves index → file when given ?turn=.
  const currentTurnHasVisualBlock = () => {
    const turn = state.turns[state.currentTurnIndex];
    const content = turn && turn.assistant && turn.assistant.content;
    return typeof content === 'string' && content.indexOf('ora-visual') !== -1;
  };

  const loadTurnCanvas = async (turnIndex, options = {}) => {
    if (!state.activeConversationId) return;
    const requestedConversationId = state.activeConversationId;
    const requestedTurnIndex = turnIndex;
    try {
      const turn = state.turns[turnIndex];
      const checkpointId = turn && turn.user && turn.user.visual_checkpoint_id;
      let loaded = false;
      if (window.OraCanvas && typeof window.OraCanvas.loadCheckpoint === 'function') {
        loaded = await window.OraCanvas.loadCheckpoint(
          requestedConversationId,
          checkpointId || null,
          checkpointId ? null : turnIndex,
          state.visualState,
          options
        );
      }
      if (requestedConversationId !== state.activeConversationId
          || requestedTurnIndex !== state.currentTurnIndex) return;
      if (!loaded && !currentTurnHasVisualBlock()) clearVisualPane();
    } catch (e) {
      console.warn('[v3-conversation] turn-canvas load failed:', e);
      if (!currentTurnHasVisualBlock()) {
        clearVisualPane();
      }
    } finally {
      if (requestedConversationId === state.activeConversationId
          && requestedTurnIndex === state.currentTurnIndex) {
        state.visualReadyTurnIndex = requestedTurnIndex;
        // Dispatch assistant visuals only after their input checkpoint has
        // settled, so a slow load can never overwrite the inserted PNG.
        renderTurn();
      }
    }
  };

  const showTurn = (index) => {
    const total = state.turns.length;
    if (total === 0) return;
    const clamped = Math.max(0, Math.min(total - 1, index));
    state.currentTurnIndex = clamped;
    state.visualReadyTurnIndex = -1;
    renderHeader();
    renderTurn();
    // Pull the canvas snapshot that was saved alongside this turn so the
    // visual pane stays in sync with the text output.
    const currentDialogue = clamped === total - 1;
    loadTurnCanvas(clamped, {
      currentDialogue,
      preferDraft: !!(
        currentDialogue
        && (!state.visualState || state.visualState.active_editor === 'excalidraw')
      ),
    });
  };

  const goFirst   = () => showTurn(0);
  const goBack    = () => showTurn(state.currentTurnIndex - 1);
  const goForward = () => showTurn(state.currentTurnIndex + 1);
  const goLast    = () => showTurn(state.turns.length - 1);

  // ── Optimistic submit hooks ────────────────────────────────────────────
  // The inline submit handler calls these on send + completion so the
  // output pane updates without a full reload.
  const appendUser = (text) => {
    if (!text) return;
    const turn = {
      user: { role: 'user', content: text, timestamp: new Date().toISOString() },
      assistant: null,
    };
    state.turns.push(turn);
    state.currentTurnIndex = state.turns.length - 1;
    renderAll();
    // Clear draft for this conversation since it was just submitted.
    if (state.activeConversationId) clearDraft(state.activeConversationId);
  };

  const appendAssistant = (text) => {
    if (!text) return;
    // Find the most recent pending turn (no assistant yet) — that's the
    // one we just submitted. If none, append a new turn with no user.
    let turn = state.turns[state.turns.length - 1];
    if (!turn || turn.assistant) {
      turn = {
        user: null,
        assistant: { role: 'assistant', content: text, timestamp: new Date().toISOString() },
      };
      state.turns.push(turn);
    } else {
      turn.assistant = {
        role: 'assistant',
        content: text,
        timestamp: new Date().toISOString(),
      };
    }
    state.hasEnvelope = true;
    state.currentTurnIndex = state.turns.length - 1;
    renderAll();
  };

  // ── Drafts (Backlog 9) ─────────────────────────────────────────────────
  const draftKey = (id) => DRAFT_KEY_PREFIX + id;
  const saveDraft = (id, text) => {
    if (!id) return;
    try {
      if (text && text.length > 0) localStorage.setItem(draftKey(id), text);
      else                          localStorage.removeItem(draftKey(id));
    } catch (e) { /* quota etc. — non-fatal */ }
  };
  const loadDraft = (id) => {
    if (!id) return '';
    try { return localStorage.getItem(draftKey(id)) || ''; }
    catch (e) { return ''; }
  };
  const clearDraft = (id) => {
    try { localStorage.removeItem(draftKey(id)); }
    catch (e) {}
  };

  // ── Lifecycle requests ────────────────────────────────────────────────
  const DELETE_FOREVER_CONFIRMATION =
    'Permanently delete this Dialogue and all Ora-managed copies? This cannot be undone. Files you explicitly exported to the vault will remain.';

  const readResponseBody = async (response) => {
    if (!response) return {};
    try {
      if (typeof response.json === 'function') return await response.json();
    } catch (e) {
      // Fall through to text for non-JSON error responses.
    }
    try {
      if (typeof response.text === 'function') {
        const raw = await response.text();
        if (!raw) return {};
        try { return JSON.parse(raw); }
        catch (e) { return { message: raw }; }
      }
    } catch (e) {}
    return {};
  };

  const requestJson = async (url, options, actionLabel) => {
    const response = await fetch(url, options);
    const data = await readResponseBody(response);
    const bodyError = data && typeof data.error === 'string' ? data.error : '';
    if (!response.ok || bodyError || (data && data.ok === false)) {
      const fallback = response && response.status
        ? `HTTP ${response.status}`
        : `${actionLabel} failed`;
      const error = new Error(bodyError || (data && data.message) || fallback);
      error.status = response && response.status;
      error.responseData = data || {};
      throw error;
    }
    return data || {};
  };

  const protectionPendingFrom = (value) => {
    const data = value && value.responseData ? value.responseData : value;
    return data && data.status === 'awaiting_system_protection_approval'
      ? data : null;
  };

  const surfaceProtectionPending = (actionLabel, conversationId, data) => {
    const detail = {
      action: actionLabel,
      conversation_id: conversationId,
      queue_id: data.queue_id || '',
      retry_required: data.retry_required === true,
    };
    console.warn(
      `[v3-conversation] ${actionLabel} awaits System Protection approval for ${conversationId}:`,
      data
    );
    document.dispatchEvent(new CustomEvent('ora:system-protection-approval-required', {
      detail,
    }));
    if (window.OraReviewQueuePanel
        && typeof window.OraReviewQueuePanel.open === 'function') {
      window.OraReviewQueuePanel.open({ tab: 'paused' });
    }
    window.alert(
      `${actionLabel} is waiting for System Protection approval. `
      + 'The Dialogue has not been deleted. Approve the queued action in Review Queue, then retry Delete Forever.'
    );
    return Object.assign({}, data, {
      ok: false,
      pending_approval: true,
      active_reset: false,
    });
  };

  const partialErrorsFrom = (data) => {
    const errors = [];
    const append = (value) => {
      if (!value) return;
      if (Array.isArray(value)) {
        value.forEach(append);
        return;
      }
      if (typeof value === 'string') {
        if (value.trim()) errors.push(value.trim());
        return;
      }
      if (typeof value === 'object') {
        if (typeof value.error === 'string') {
          errors.push(value.error);
          return;
        }
        if (typeof value.message === 'string') {
          errors.push(value.message);
          return;
        }
        try { errors.push(JSON.stringify(value)); }
        catch (e) { errors.push(String(value)); }
      }
    };
    if (!data || typeof data !== 'object') return errors;
    append(data.errors);
    append(data.cleanup_errors);
    append(data.purge_errors);
    if (data.result) append(data.result.errors);
    if (data.summary) append(data.summary.errors);
    return errors;
  };

  const surfacePartialErrors = (actionLabel, conversationId, data) => {
    const errors = partialErrorsFrom(data);
    if (!errors.length) return errors;
    console.error(
      `[v3-conversation] ${actionLabel} completed with partial errors for ${conversationId}:`,
      errors,
      data
    );
    window.alert(
      `${actionLabel} completed, but some Ora-managed copies could not be updated:\n\n`
      + errors.join('\n')
    );
    return errors;
  };

  const surfaceDeleteLimitations = (data) => {
    const raw = data && data.limitations;
    if (!raw || typeof raw !== 'object') return [];
    const limitations = Object.values(raw).filter((value) => (
      typeof value === 'string' && value.trim()
    ));
    if (!limitations.length) return limitations;
    console.warn(
      '[v3-conversation] Delete Forever retained-boundary disclosure:',
      limitations,
    );
    window.alert(
      'Delete Forever completed. Data outside Ora\'s active local stores may remain:\n\n'
      + limitations.map((value) => `• ${value}`).join('\n')
    );
    return limitations;
  };

  const refreshSidebar = () => {
    if (window.OraSidebar && typeof window.OraSidebar.refresh === 'function') {
      window.OraSidebar.refresh();
    }
  };

  const dispatchTagChanged = (conversationId, tag, source, persisted = true) => {
    document.dispatchEvent(new CustomEvent('ora:conversation-tag-changed', {
      detail: {
        conversation_id: conversationId,
        tag: tag === 'private' ? 'private' : '',
        source,
        persisted,
      },
    }));
  };

  const resetAfterLifecycle = (conversationId, action, data) => {
    const renderedActive = state.activeConversationId === conversationId;
    const pendingActive = pendingLoadId === conversationId;
    const wasActive = renderedActive || pendingActive;
    if (action === 'delete-forever') retiredConversationIds.add(conversationId);

    // Cancel only a timer owned by the lifecycle target. A timer from the
    // previously-rendered Dialogue must not recreate this draft after Delete
    // Forever, and deleting a different row must not cancel the active draft.
    cancelDraftTimerFor(conversationId);
    clearDraft(conversationId);
    const newerPendingSelection = (
      renderedActive
      && pendingLoadId
      && pendingLoadId !== conversationId
    );
    if (newerPendingSelection) {
      // The user has already selected another Dialogue. Remove the deleted
      // rendered identity without calling startFresh(), which would increment
      // loadEpoch and cancel that newer navigation intent.
      state.activeConversationId = null;
      state.activeParentConversationId = null;
      state.activeTag = '';
      state.activeTitle = '';
      state.readOnlySource = false;
      state.hasEnvelope = null;
      state.messages = [];
      state.turns = [];
      state.currentTurnIndex = 0;
      renderAll();
    } else if (wasActive) {
      // Clear the old identity before startFresh so it cannot re-save the
      // just-cleared draft. Explicit tag:"" guarantees Standard mode even
      // when the previous Dialogue was Private or Stealth.
      state.activeConversationId = null;
      state.activeParentConversationId = null;
      state.activeTag = '';
      state.activeTitle = '';
      state.readOnlySource = false;
      state.hasEnvelope = false;
      state.messages = [];
      state.turns = [];
      state.currentTurnIndex = 0;
      startFresh({
        tag: '', source: `${action}-complete`, skip_visual_flush: true,
      });
    }
    document.dispatchEvent(new CustomEvent('ora:conversation-lifecycle-completed', {
      detail: {
        conversation_id: conversationId,
        action,
        active_reset: wasActive,
        result: data || {},
      },
    }));
    refreshSidebar();
    return wasActive;
  };

  const rememberLifecyclePulse = (nonce) => {
    if (!nonce || seenLifecyclePulses.has(nonce)) return false;
    seenLifecyclePulses.add(nonce);
    seenLifecyclePulseOrder.push(nonce);
    while (seenLifecyclePulseOrder.length > LIFECYCLE_PULSE_LIMIT) {
      seenLifecyclePulses.delete(seenLifecyclePulseOrder.shift());
    }
    return true;
  };

  const receiveLifecyclePulse = (payload) => {
    if (!payload || typeof payload !== 'object') return false;
    if (payload.action !== 'delete-forever') return false;
    if (payload.source === lifecyclePulseSource) return false;
    if (typeof payload.conversation_id !== 'string'
        || !payload.conversation_id
        || payload.conversation_id.length > 255) return false;
    if (typeof payload.nonce !== 'string' || !payload.nonce) return false;
    if (!rememberLifecyclePulse(payload.nonce)) return false;

    const conversationId = payload.conversation_id;
    // A remote tab may have a debounced draft timer or a delayed load for the
    // just-deleted identity. Reuse the same local retirement path so those
    // callbacks cannot recreate browser residue or reactivate the Dialogue.
    lifecycleRequestCounts.delete(conversationId);
    resetAfterLifecycle(conversationId, 'delete-forever', {
      cross_tab: true,
      source: payload.source || 'remote-tab',
    });
    return true;
  };

  const broadcastDeleteForever = (conversationId) => {
    if (!conversationId) return;
    const nonce = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    const payload = {
      action: 'delete-forever',
      conversation_id: conversationId,
      nonce,
      source: lifecyclePulseSource,
    };
    rememberLifecyclePulse(nonce);
    if (lifecycleChannel) {
      try { lifecycleChannel.postMessage(payload); }
      catch (e) { /* storage pulse remains available */ }
    }
    // The storage record is deliberately a pulse, not durable lifecycle
    // state: other tabs receive the set event and this tab removes the value
    // immediately so deleted identifiers do not accumulate in localStorage.
    try {
      localStorage.setItem(LIFECYCLE_STORAGE_KEY, JSON.stringify(payload));
    } catch (e) {
      return;
    } finally {
      try { localStorage.removeItem(LIFECYCLE_STORAGE_KEY); } catch (e) {}
    }
  };

  const initLifecycleSync = () => {
    if (typeof window.BroadcastChannel === 'function') {
      try {
        lifecycleChannel = new window.BroadcastChannel(LIFECYCLE_CHANNEL_NAME);
        lifecycleChannel.onmessage = (event) => {
          receiveLifecyclePulse(event && event.data);
        };
      } catch (e) {
        lifecycleChannel = null;
      }
    }
    window.addEventListener('storage', (event) => {
      if (!event || event.key !== LIFECYCLE_STORAGE_KEY || !event.newValue) return;
      try { receiveLifecyclePulse(JSON.parse(event.newValue)); }
      catch (e) { /* ignore malformed/foreign storage values */ }
    });
    window.addEventListener('pagehide', () => {
      if (!lifecycleChannel) return;
      try { lifecycleChannel.close(); } catch (e) {}
      lifecycleChannel = null;
    }, { once: true });
  };

  const isFreshLocalConversation = (conversationId) => (
    conversationId === state.activeConversationId
    && state.hasEnvelope === false
    && state.messages.length === 0
    && state.turns.length === 0
  );

  const performDeleteForever = async (id) => {
    if (!window.confirm(DELETE_FOREVER_CONFIRMATION)) return null;

    try {
      // A zero-turn Dialogue can already own staged documents, background
      // jobs, canvas snapshots, or media artifacts. The browser cannot prove
      // that it is server-empty, so Delete Forever always invokes the
      // idempotent server purge even when no envelope exists yet.
      const data = await requestJson(
        `/api/conversation/${encodeURIComponent(id)}/delete-forever`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' },
        'Delete Forever'
      );
      const protectionPending = protectionPendingFrom(data);
      if (protectionPending) {
        return surfaceProtectionPending('Delete Forever', id, protectionPending);
      }
      surfacePartialErrors('Delete Forever', id, data);
      surfaceDeleteLimitations(data);
      const firstRetirementInThisTab = !retiredConversationIds.has(id);
      const activeReset = resetAfterLifecycle(id, 'delete-forever', data);
      if (firstRetirementInThisTab) broadcastDeleteForever(id);
      return Object.assign({}, data, { ok: true, active_reset: activeReset });
    } catch (e) {
      // Another tab can win the server race and notify this tab while its own
      // request is still in flight. The remote pulse is authoritative success;
      // do not show a contradictory failure or rebroadcast a second pulse.
      if (retiredConversationIds.has(id)) {
        return { ok: true, active_reset: false, cross_tab: true };
      }
      const protectionPending = protectionPendingFrom(e);
      if (protectionPending) {
        return surfaceProtectionPending('Delete Forever', id, protectionPending);
      }
      console.error(`[v3-conversation] Delete Forever failed for ${id}:`, e);
      window.alert('Delete Forever failed: ' + (e.message || e));
      return null;
    }
  };

  const deleteForever = async (conversationId, options = {}) => {
    const id = conversationId || state.activeConversationId;
    if (!id) return null;
    if (id === state.activeConversationId
        && state.readOnlySource
        && pendingLoadId !== id) return null;
    if (lifecycleRequestActive(id)) return null;

    setLifecycleRequestActive(id, true);
    try {
      if (id === state.activeConversationId
          && window.OraCanvas && typeof window.OraCanvas.flushDraft === 'function') {
        await window.OraCanvas.flushDraft();
      }
      return await performDeleteForever(id, options);
    } finally {
      setLifecycleRequestActive(id, false);
    }
  };

  const performCloseConversation = async (id, options = {}) => {

    // The loaded envelope wins over potentially stale sidebar row metadata.
    // For any non-rendered/pending row, read the envelope before deciding:
    // calling /close on a mislabelled Stealth row would otherwise bypass the
    // mandatory irreversible-deletion warning.
    let knownTag;
    const renderedEnvelopeIsAuthoritative = (
      id === state.activeConversationId
      && state.hasEnvelope
      && pendingLoadId !== id
    );
    if (renderedEnvelopeIsAuthoritative || isFreshLocalConversation(id)) {
      knownTag = state.activeTag;
    } else {
      try {
        const envelope = await requestJson(
          `/api/conversation/${encodeURIComponent(id)}`,
          {},
          'Resolve Dialogue privacy'
        );
        knownTag = envelope && envelope.tag || '';
      } catch (e) {
        console.error(`[v3-conversation] privacy resolution failed for ${id}:`, e);
        window.alert('Close failed: could not verify whether this Dialogue is Off Record.');
        return null;
      }
    }
    // Stealth cannot be retained by Close. Route it through the explicit
    // destructive path so the vault-export retention warning is unavoidable.
    if (knownTag === 'stealth') return performDeleteForever(id, options);

    let hasDraft = false;
    try { hasDraft = !!localStorage.getItem(draftKey(id)); }
    catch (e) {}
    if (id === state.activeConversationId && leftInput && leftInput.value) {
      hasDraft = true;
    }
    if (hasDraft && !window.confirm(
      'This Dialogue has an unsent message in the Inquiry pane. Close anyway?'
    )) return null;

    try {
      // A zero-turn Dialogue may already own durable canvas, media, capture,
      // timeline, or document state. The server is the only authority that
      // can distinguish that from a truly local-only Dialogue, so every Close
      // goes through the idempotent endpoint.
      const data = await requestJson(
        `/api/conversation/${encodeURIComponent(id)}/close`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' },
        'Close Dialogue'
      );
      surfacePartialErrors('Close Dialogue', id, data);
      const activeReset = resetAfterLifecycle(id, 'close', data);
      return Object.assign({}, data, { ok: true, active_reset: activeReset });
    } catch (e) {
      console.error(`[v3-conversation] Close failed for ${id}:`, e);
      window.alert('Close failed: ' + (e.message || e));
      return null;
    }
  };

  const closeConversation = async (conversationId, options = {}) => {
    const id = conversationId || state.activeConversationId;
    if (!id) return null;
    if (id === state.activeConversationId
        && state.readOnlySource
        && pendingLoadId !== id) return null;
    if (lifecycleRequestActive(id)) return null;

    setLifecycleRequestActive(id, true);
    try {
      if (id === state.activeConversationId
          && window.OraCanvas && typeof window.OraCanvas.flushDraft === 'function') {
        await window.OraCanvas.flushDraft();
      }
      return await performCloseConversation(id, options);
    } finally {
      setLifecycleRequestActive(id, false);
    }
  };

  const setPrivacyTag = async (tag, conversationId) => {
    const targetTag = tag === 'private' ? 'private' : (tag === '' ? '' : null);
    const id = conversationId || state.activeConversationId;
    if (targetTag === null || !id) {
      window.alert('Only Standard and Private can be applied to an existing Dialogue.');
      return null;
    }
    if (id === state.activeConversationId) {
      if (state.readOnlySource) return null;
      if (state.activeTag === 'stealth') {
        window.alert('An Off Record Dialogue cannot be retagged.');
        return null;
      }
      if (state.activeTag === targetTag) return { ok: true, tag: targetTag };

    }

    if (lifecycleRequestActive(id)) return null;

    setLifecycleRequestActive(id, true);
    try {
      // Always route privacy changes through the server, including zero-turn
      // Dialogues. Artifact-producing endpoints can already have created
      // correlated state, and the server owns minimal-envelope creation plus
      // document/chunk metadata synchronization.
      const data = await requestJson(
        `/api/conversation/${encodeURIComponent(id)}/privacy-tag`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tag: targetTag }),
        },
        'Change Dialogue privacy'
      );
      const authoritativeTag = Object.prototype.hasOwnProperty.call(data, 'tag')
        ? data.tag
        : targetTag;
      if (authoritativeTag !== '' && authoritativeTag !== 'private') {
        throw new Error(`Server returned unsupported privacy tag: ${authoritativeTag}`);
      }
      if (id === state.activeConversationId) state.hasEnvelope = true;
      surfacePartialErrors('Change Dialogue privacy', id, data);
      dispatchTagChanged(id, authoritativeTag, 'privacy-tag-response', true);
      return Object.assign({}, data, { ok: true, tag: authoritativeTag });
    } catch (e) {
      console.error(`[v3-conversation] privacy-tag change failed for ${id}:`, e);
      window.alert('Privacy change failed: ' + (e.message || e));
      return null;
    } finally {
      setLifecycleRequestActive(id, false);
    }
  };

  // Debounced draft saver wired to the left input's input event.
  let draftTimer = null;
  let draftTimerOwner = null;
  let draftTimerText = '';

  const clearDraftTimerState = () => {
    draftTimer = null;
    draftTimerOwner = null;
    draftTimerText = '';
  };

  const flushDraftTimer = () => {
    if (!draftTimer) return;
    clearTimeout(draftTimer);
    if (draftTimerOwner) saveDraft(draftTimerOwner, draftTimerText);
    clearDraftTimerState();
  };

  const cancelDraftTimerFor = (conversationId) => {
    if (!draftTimer || draftTimerOwner !== conversationId) return false;
    clearTimeout(draftTimer);
    clearDraftTimerState();
    return true;
  };

  const queueDraftSave = () => {
    if (!state.activeConversationId || !leftInput) return;
    if (leftInput.readOnly
        || state.readOnlySource
        || pendingLoadId
        || lifecycleRequestActive(state.activeConversationId)) return;
    if (draftTimer) clearTimeout(draftTimer);
    const conversationId = state.activeConversationId;
    const draftText = leftInput.value;
    draftTimerOwner = conversationId;
    draftTimerText = draftText;
    const timer = setTimeout(() => {
      saveDraft(conversationId, draftText);
      if (draftTimer === timer) clearDraftTimerState();
    }, DRAFT_DEBOUNCE);
    draftTimer = timer;
  };

  // ── Turn-head privacy intervention ───────────────────────────────────
  // Deliberately small and deterministic: no model, score, stored label, or
  // diagnosis. Explicit Private/Stealth state wins before this is consulted.
  const classifyPrivacyPrompt = (text) => {
    const value = String(text || '').trim();
    if (!value) return 'stay';
    const clearExternal = (
      /\b(?:email|letter|memo|message|post|press release|proposal|application)\b/i.test(value)
      && /\b(?:to|for|send|publish|share with)\b/i.test(value)
    );
    if (clearExternal) return 'stay';
    const highConfidence = /\b(?:password|passcode|recovery code|api key|secret key|private key|seed phrase|social security|ssn|credit card|card number|bank account|routing number)\b/i;
    if (highConfidence.test(value)) return 'fork';
    const sensitiveHealth = /\b(?:diagnosed with|my diagnosis|my medical|my therapist|my medication|suicidal|self[- ]harm|sexual assault|domestic abuse)\b/i;
    if (sensitiveHealth.test(value)) return 'fork';
    const ambiguousPersonal = /\b(?:my health|my finances|my debt|my salary|my family|my marriage|my relationship|my grief|my trauma|i feel|i'm afraid|i am afraid|i'm ashamed|i am ashamed)\b/i;
    return ambiguousPersonal.test(value) ? 'ask' : 'stay';
  };

  const privacyChoice = (kind) => new Promise((resolve) => {
    const dialog = document.createElement('dialog');
    dialog.className = 'ora-privacy-intervention';
    dialog.setAttribute('aria-labelledby', 'oraPrivacyInterventionTitle');
    const isFork = kind === 'fork';
    dialog.innerHTML = `
      <form method="dialog">
        <h2 id="oraPrivacyInterventionTitle">Sensitive Inquiry</h2>
        <p>${isFork
          ? 'This Inquiry appears to contain highly sensitive information.'
          : 'This Inquiry may be personal. Choose its Dialogue privacy before anything is sent.'}</p>
        <p><strong>Private</strong> excludes this Dialogue from Standard conversational retrieval. Configured AI providers may still process the turn.</p>
        <div class="project-modal__actions">
          <button type="button" class="project-modal__btn project-modal__btn--primary" data-choice="private">Use Private</button>
          ${isFork
            ? '<button type="button" class="project-modal__btn" data-choice="cancel">Cancel submission</button>'
            : '<button type="button" class="project-modal__btn" data-choice="standard">Keep Standard</button>'}
        </div>
      </form>`;
    document.body.appendChild(dialog);
    const finish = (choice) => {
      try { dialog.close(); } catch (e) {}
      dialog.remove();
      resolve(choice);
    };
    dialog.querySelectorAll('[data-choice]').forEach((button) => {
      button.addEventListener('click', () => finish(button.dataset.choice));
    });
    dialog.addEventListener('cancel', (event) => {
      event.preventDefault();
      finish('cancel');
    });
    dialog.showModal();
  });

  const prepareStandardSubmission = async (text, options = {}) => {
    if (state.activeTag === 'private' || state.activeTag === 'stealth') return true;
    if (state.activeTag !== '') return false;
    const decision = classifyPrivacyPrompt(text);
    if (decision === 'stay') return true;
    const choice = await privacyChoice(decision);
    if (choice === 'standard') return true;
    if (choice !== 'private') return false;

    const parentId = state.activeConversationId;
    if (!parentId) return false;
    if (state.turns.length === 0) {
      // The existing endpoint creates/retags the minimal envelope in place;
      // there is no empty Standard parent to leave behind.
      const changed = await setPrivacyTag('private', parentId);
      return !!changed && state.activeConversationId === parentId
        && state.activeTag === 'private';
    }

    // Capture the parent scene before forkActive selects/loads the empty
    // child. The submit callback carries this immutable snapshot across that
    // navigation boundary and persists/posts it under the selected child.
    const submissionContext = options.submissionContext;
    if (options.captureVisualSnapshot && submissionContext && window.OraCanvas
        && (typeof window.OraCanvas.hasContent !== 'function'
            || window.OraCanvas.hasContent())
        && typeof window.OraCanvas.snapshotForSubmit === 'function') {
      try {
        submissionContext.visualSnapshot = window.OraCanvas.snapshotForSubmit();
      } catch (e) {
        console.warn('[v3-conversation] privacy-fork Exhibits capture failed:', e);
        window.alert('Exhibits capture failed; Inquiry was not sent.');
        return false;
      }
    }

    refreshDOMRefs();
    const draft = typeof options.draftText === 'string'
      ? options.draftText
      : (typeof text === 'string' ? text : (leftInput && leftInput.value) || '');
    cancelDraftTimerFor(parentId);
    const forked = await forkActive({
      tag: 'private',
      source: 'privacy-intervention',
      await_selection: true,
      draftMessage: draft,
    });
    if (forked && forked.new_conversation_id) {
      // forkActive saved the draft under the returned child key first. Only
      // now is it safe to remove the Standard parent's copy.
      clearDraft(parentId);
      if (state.activeConversationId === parentId && leftInput) {
        leftInput.value = '';
      }
    }
    if (forked && forked.selected
        && state.activeConversationId === forked.new_conversation_id
        && state.activeTag === 'private') {
      return true;
    }
    // The parent never received a POST. Restore its browser draft if the fork
    // failed or a newer selection won the navigation race.
    if (!forked && state.activeConversationId === parentId) {
      if (leftInput) leftInput.value = draft;
      saveDraft(parentId, draft);
    }
    return false;
  };

  const submitAfterPrivacy = async (text, submit, options = {}) => {
    const submissionContext = {};
    const prepareOptions = Object.assign({}, options, { submissionContext });
    if (!(await prepareStandardSubmission(text, prepareOptions))) return false;
    await submit(submissionContext);
    return true;
  };

  // One Standard /chat boundary for auxiliary UI surfaces. User-authored
  // text supplies privacyText; internal commands omit it and retain their
  // existing direct path. If privacy forks, the POST is rebound to the
  // selected Private child so the Standard parent receives no user text.
  const submitChatTurn = async (body, options = {}) => {
    const requestedId = body.conversation_id || body.panel_id
      || state.activeConversationId;
    const privacyText = typeof options.privacyText === 'string'
      ? options.privacyText.trim()
      : '';
    if (privacyText && requestedId !== state.activeConversationId) {
      await load(requestedId);
      if (state.activeConversationId !== requestedId) return null;
    }

    let submittedId = requestedId;
    const send = async () => {
      if (privacyText) submittedId = state.activeConversationId;
      const payload = Object.assign({}, body);
      if (submittedId) {
        payload.conversation_id = submittedId;
        payload.panel_id = submittedId;
      }
      if (privacyText) payload.tag = state.activeTag;
      const response = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        let message = `Chat request failed (${response.status})`;
        try {
          const error = await response.json();
          message = error.error || error.message || message;
        } catch (_) {}
        throw new Error(message);
      }
    };

    if (privacyText) {
      const submitted = await submitAfterPrivacy(
        privacyText, send, { draftText: privacyText }
      );
      return submitted ? submittedId : null;
    }
    await send();
    return submittedId;
  };

  // ── Rename UI (Backlog 2C) ─────────────────────────────────────────────
  // Click the display name in the output-pane header to edit it.
  // Enter saves; Esc cancels. Empty save clears the override (UI falls
  // back to the derived title). The conversation_id never changes.
  const beginRenameDisplayName = () => {
    if (!displayName) return;
    if (!state.activeConversationId) return;
    if (state.readOnlySource) return;
    if (state.hasEnvelope !== true
        || pendingLoadId
        || lifecycleRequestActive(state.activeConversationId)) return;
    if (displayName.classList.contains('is-renaming')) return;

    const conversationId = state.activeConversationId;
    const original = state.activeTitle || '';
    displayName.classList.add('is-renaming');

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'output-pane-display-name-input';
    input.dataset.conversationId = conversationId;
    input.value = original;
    input.maxLength = 200;
    input.setAttribute('aria-label', 'Dialogue name');

    displayName.replaceChildren(input);
    input.focus();
    input.select();

    let finished = false;
    const cleanup = () => {
      finished = true;
      displayName.classList.remove('is-renaming');
    };

    const commit = async () => {
      if (finished) return;
      const next = (input.value || '').trim();
      cleanup();
      if (state.activeConversationId !== conversationId) {
        renderHeader();
        return;
      }
      if (next === original) {
        displayName.textContent = original;
        return;
      }
      try {
        const data = await requestJson(
          `/api/conversation/${encodeURIComponent(conversationId)}/rename`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ display_name: next }),
          },
          'Rename Dialogue'
        );
        surfacePartialErrors('Rename Dialogue', conversationId, data);
        if (state.activeConversationId === conversationId) {
          state.activeTitle = data.display_name
            || data.conversation_title
            || data.title
            || next
            || original;
          displayName.textContent = state.activeTitle;
        }
        refreshSidebar();
      } catch (e) {
        if (state.activeConversationId === conversationId) {
          displayName.textContent = original;
        }
        console.error(`[v3-conversation] rename failed for ${conversationId}:`, e);
        window.alert('Rename failed: ' + (e.message || e));
      }
    };

    const abort = () => {
      if (finished) return;
      cleanup();
      if (state.activeConversationId === conversationId) {
        displayName.textContent = original;
      } else {
        renderHeader();
      }
    };

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter')      { e.preventDefault(); commit(); }
      else if (e.key === 'Escape') { e.preventDefault(); abort();  }
    });
    input.addEventListener('blur', commit);
  };

  // ── Output-header lifecycle menu ──────────────────────────────────────
  // This is intentionally a small, standalone live-Dialogue affordance.
  // Library-backed archives/engrams set readOnlySource and never expose it.
  let outputActionsMenu = null;

  const pageTabStopsOutsideOutputActions = () => Array.from(document.querySelectorAll(
    'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), '
    + 'textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'
  )).filter((element) => {
    if (outputActionsMenu && outputActionsMenu.contains(element)) return false;
    if (element.hidden || element.getAttribute('aria-hidden') === 'true') return false;
    if (element.closest('[hidden], [aria-hidden="true"]')) return false;
    const closedDropdown = element.closest('.mode-dropdown');
    return !closedDropdown || closedDropdown.classList.contains('show');
  });

  const focusOutputActionsItem = (item) => {
    if (!outputActionsMenu) return;
    outputActionsMenu.querySelectorAll('.mode-dropdown-item:not(:disabled)')
      .forEach((candidate) => {
        candidate.tabIndex = candidate === item ? 0 : -1;
      });
    if (item) item.focus();
  };

  const focusNextToOutputActionsButton = (backwards) => {
    if (!actionsButton) return;
    const tabStops = pageTabStopsOutsideOutputActions();
    const anchorIndex = tabStops.indexOf(actionsButton);
    const nextIndex = anchorIndex + (backwards ? -1 : 1);
    const target = anchorIndex >= 0 ? tabStops[nextIndex] : null;
    if (target) target.focus();
    else if (!actionsButton.hidden) actionsButton.focus();
  };

  const ensureOutputActionsMenu = () => {
    if (outputActionsMenu) return outputActionsMenu;
    outputActionsMenu = document.createElement('div');
    outputActionsMenu.id = 'outputPaneActionsMenu';
    outputActionsMenu.className = 'mode-dropdown output-pane-actions-menu';
    outputActionsMenu.setAttribute('role', 'menu');
    outputActionsMenu.addEventListener('keydown', (event) => {
      const items = Array.from(
        outputActionsMenu.querySelectorAll('.mode-dropdown-item:not(:disabled)')
      );
      if (!items.length) return;
      const index = Math.max(0, items.indexOf(document.activeElement));
      let next = null;
      if (event.key === 'ArrowDown') next = (index + 1) % items.length;
      else if (event.key === 'ArrowUp') next = (index - 1 + items.length) % items.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = items.length - 1;
      else if (event.key === 'Escape') {
        event.preventDefault();
        closeOutputActionsMenu({ restoreFocus: true });
        return;
      } else if (event.key === 'Tab') {
        event.preventDefault();
        closeOutputActionsMenu();
        focusNextToOutputActionsButton(event.shiftKey);
        return;
      }
      if (next !== null) {
        event.preventDefault();
        focusOutputActionsItem(items[next]);
      }
    });
    outputActionsMenu.addEventListener('focusout', (event) => {
      const next = event.relatedTarget;
      if (!next || (!outputActionsMenu.contains(next) && next !== actionsButton)) {
        closeOutputActionsMenu();
      }
    });
    document.body.appendChild(outputActionsMenu);
    return outputActionsMenu;
  };

  const closeOutputActionsMenu = (options = {}) => {
    if (outputActionsMenu) outputActionsMenu.classList.remove('show');
    if (outputActionsMenu) {
      outputActionsMenu.querySelectorAll('.mode-dropdown-item').forEach((item) => {
        item.tabIndex = -1;
      });
    }
    if (actionsButton) actionsButton.setAttribute('aria-expanded', 'false');
    if (options.restoreFocus && actionsButton && !actionsButton.hidden) {
      actionsButton.focus();
    }
  };

  const openOutputActionsMenu = () => {
    if (!actionsButton || actionsButton.hidden) return;
    if (!state.activeConversationId
        || state.readOnlySource
        || pendingLoadId
        || lifecycleRequestActive(state.activeConversationId)) return;
    document.dispatchEvent(new CustomEvent('ora:close-mode-dropdown'));
    const menu = ensureOutputActionsMenu();
    const menuConversationId = state.activeConversationId;
    const menuTag = state.activeTag;
    const items = [];
    if (state.hasEnvelope === true) {
      items.push({ label: 'Rename', action: () => beginRenameDisplayName() });
    }
    if (menuTag === 'stealth') {
      items.push({
        label: 'Exit Off Record',
        action: () => exitStealth(menuConversationId),
      }, {
        label: 'Delete Forever',
        danger: true,
        action: () => deleteForever(menuConversationId, { source: 'output-header' }),
      });
    } else {
      items.push({
        label: 'Close',
        action: () => closeConversation(menuConversationId, { tag: menuTag }),
      });
    }

    menu.replaceChildren();
    items.forEach((item) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'mode-dropdown-item';
      if (item.danger) button.classList.add('is-danger');
      button.setAttribute('role', 'menuitem');
      button.tabIndex = -1;
      button.textContent = item.label;
      button.addEventListener('click', (event) => {
        event.stopPropagation();
        closeOutputActionsMenu({ restoreFocus: true });
        item.action();
      });
      menu.appendChild(button);
    });

    const rect = actionsButton.getBoundingClientRect();
    menu.classList.add('show');
    const menuWidth = menu.offsetWidth || 150;
    const maxLeft = Math.max(8, window.innerWidth - menuWidth - 8);
    menu.style.left = Math.min(maxLeft, Math.max(8, rect.right - menuWidth)) + 'px';
    menu.style.top = (rect.bottom + 6) + 'px';
    actionsButton.setAttribute('aria-expanded', 'true');
    const firstItem = menu.querySelector('.mode-dropdown-item:not(:disabled)');
    if (firstItem) focusOutputActionsItem(firstItem);
  };

  const toggleOutputActionsMenu = () => {
    const menu = ensureOutputActionsMenu();
    if (menu.classList.contains('show')) closeOutputActionsMenu();
    else openOutputActionsMenu();
  };

  // ── Wire everything on DOMContentLoaded ────────────────────────────────
  let initialized = false;
  const init = () => {
    if (initialized) return;
    initialized = true;
    refreshDOMRefs();
    initLifecycleSync();

    if (navFirst)   navFirst.addEventListener('click', goFirst);
    if (navBack)    navBack.addEventListener('click', goBack);
    if (navForward) navForward.addEventListener('click', goForward);
    if (navLast)    navLast.addEventListener('click', goLast);

    if (actionsButton) {
      actionsButton.addEventListener('click', (event) => {
        event.stopPropagation();
        toggleOutputActionsMenu();
      });
    }

    if (displayName) {
      displayName.addEventListener('click', () => {
        if (!state.activeConversationId) return;
        beginRenameDisplayName();
      });
    }

    if (leftInput) {
      leftInput.addEventListener('input', queueDraftSave);
    }

    document.addEventListener('ora:new-thread-requested', (e) => {
      const detail = (e && e.detail) || {};
      if (detail.bootstrap === true || detail.dossier === true) {
        return;
      }
      if (detail.skip_creation_review === true) {
        startFresh(detail);
      } else if (window.OraSidebar && typeof window.OraSidebar.openCreation === 'function') {
        window.OraSidebar.openCreation(detail);
      } else {
        startFresh(detail);
      }
    });
    document.addEventListener('ora:fork-conversation-requested', (e) => {
      forkActive((e && e.detail) || {});
    });

    document.addEventListener('ora:conversation-tag-changed', (e) => {
      const detail = (e && e.detail) || {};
      if (detail.conversation_id
          && detail.conversation_id !== state.activeConversationId) return;
      const tag = detail.tag;
      if (tag !== '' && tag !== 'private' && tag !== 'stealth') {
        console.error('[v3-conversation] ignored unsupported authoritative tag:', detail);
        return;
      }
      state.activeTag = tag || '';
      renderHeader();
    });

    // Artifact-producing endpoints can create the first durable envelope
    // before the first conversational turn. Only upgrade the identity that
    // owned that request; a delayed response must not mutate a newer
    // Dialogue selected while the upload was in flight.
    document.addEventListener('ora:conversation-envelope-created', (e) => {
      const detail = (e && e.detail) || {};
      if (!detail.conversation_id) return;
      if (detail.envelope_available === false) return;
      refreshSidebar();
      if (detail.conversation_id !== state.activeConversationId) return;
      state.hasEnvelope = true;
      renderHeader();
    });

    // Listen for conversation selections from the sidebar. Mode UI is
    // already activated by the existing handler in the inline script;
    // this loads the actual content.
    document.addEventListener('ora:conversation-selected', (e) => {
      const detail = (e && e.detail) || {};
      const id = detail.conversation_id;
      const turnIndex = detail.matched_turn_index;
      const tag = detail.tag;
      const draftMessage = detail.draft_message;
      if (!id) return;
      const selectionPromise = load(id, { turnIndex, tag, draftMessage });
      if (detail.await_selection === true) {
        detail.selection_promise = selectionPromise;
      }
    });

    document.addEventListener('click', (event) => {
      if (!outputActionsMenu || !outputActionsMenu.classList.contains('show')) return;
      if (outputActionsMenu.contains(event.target)) return;
      if (actionsButton && actionsButton.contains(event.target)) return;
      closeOutputActionsMenu();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape'
          && outputActionsMenu
          && outputActionsMenu.classList.contains('show')) {
        event.preventDefault();
        closeOutputActionsMenu({ restoreFocus: true });
      }
    });
    document.addEventListener('ora:close-output-actions-menu', () => {
      closeOutputActionsMenu();
    });

    // Body mode classes control presentation, while activeTag remains the
    // loaded/mutated envelope authority. Re-render only; never infer a tag
    // mutation from a CSS class transition.
    const modeObserver = new MutationObserver(() => {
      if (state.activeConversationId) {
        renderHeader();
      }
    });
    modeObserver.observe(document.body, { attributes: true, attributeFilter: ['class'] });
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.OraConversation = {
    load,
    showTurn,
    appendUser,
    appendAssistant,
    startFresh,
    forkActive,
    exitStealth,
    beginRename: beginRenameDisplayName,
    setPrivacyTag,
    closeConversation,
    closeActive: () => closeConversation(state.activeConversationId, { tag: state.activeTag }),
    deleteForever,
    saveDraft,
    loadDraft,
    clearDraft,
    submitAfterPrivacy,
    submitChatTurn,
    getActiveConversationId: () => state.activeConversationId,
    getActiveTag:            () => state.activeTag,
    isLoading:               () => !!pendingLoadId,
    isLifecycleBusy:         () => lifecycleRequestActive(state.activeConversationId),
    isReadOnly:              () => (
      state.readOnlySource
      || !!pendingLoadId
      || lifecycleRequestActive(state.activeConversationId)
    ),
    canFork:                 canForkActive,
    canForkAs,
    getTurnCount:            () => state.turns.length,
    getCurrentTurn:          () => state.turns[state.currentTurnIndex] || null,
  };
})();
