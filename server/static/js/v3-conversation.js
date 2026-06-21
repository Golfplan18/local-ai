/* V3 Backlog 2B + 8 + 9 — Conversation loading, output-pane rendering,
 * turn navigation, and per-conversation input drafts.
 *
 * Closes the navigation loop: when the sidebar dispatches
 * `ora:conversation-selected`, this module fetches the conversation,
 * renders its turns into the output pane (one turn at a time, with
 * forward/back navigation), wires the prompt overlay to show that
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
 *   - Forward/back arrows move the turn cursor.
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
 *   getActiveConversationId()
 *   getTurnCount()
 *   getCurrentTurn()
 */
(() => {
  'use strict';

  const DRAFT_KEY_PREFIX = 'ora-v3-draft-';
  const DRAFT_DEBOUNCE   = 400;

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
    activeTag:            '',
    activeTitle:          '',
    messages:             [],   // raw conversation.json messages[]
    turns:                [],   // grouped: [{user, assistant}, ...]
    currentTurnIndex:     0,    // -1 if no turns
  };

  // ── DOM refs (looked up lazily so the module loads before DOM ready) ───
  let outputPane     = null;
  let outputContent  = null;
  let displayName    = null;
  let modeIcon       = null;
  let navBack        = null;
  let navForward     = null;
  let turnPosition   = null;
  let timestampEl    = null;
  let leftInput      = null;

  const refreshDOMRefs = () => {
    outputPane    = document.querySelector('.output-pane');
    outputContent = document.querySelector('.output-content');
    displayName   = document.getElementById('outputPaneDisplayName');
    modeIcon      = document.getElementById('outputPaneModeIcon');
    navBack       = document.getElementById('outputPaneNavBack');
    navForward    = document.getElementById('outputPaneNavForward');
    turnPosition  = document.getElementById('outputPaneTurnPosition');
    timestampEl   = document.getElementById('outputPaneTimestamp');
    leftInput     = document.querySelector('.input-pane textarea');
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
      // Short, locale-aware: Apr 29, 8:14 AM
      return d.toLocaleString(undefined, {
        month: 'short', day: 'numeric',
        hour: 'numeric', minute: '2-digit',
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
    displayName.textContent = state.activeTitle || (state.activeConversationId || 'Conversation');
    if (modeIcon) {
      modeIcon.textContent = modeIconSymbolFor(state.activeTag);
      modeIcon.dataset.tag = state.activeTag || '';
    }
    const total = state.turns.length;
    if (turnPosition) {
      if (total === 0) {
        turnPosition.textContent = 'no turns';
      } else {
        turnPosition.textContent = `turn ${state.currentTurnIndex + 1} of ${total}`;
      }
    }
    if (navBack)    navBack.disabled    = state.currentTurnIndex <= 0;
    if (navForward) navForward.disabled = state.currentTurnIndex >= total - 1;

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

  const renderTurn = () => {
    if (!outputContent) return;
    const t = state.turns[state.currentTurnIndex];
    outputContent.replaceChildren();

    if (!t) {
      const empty = document.createElement('div');
      empty.className = 'output-turn output-turn-empty';
      empty.textContent = '(no content yet)';
      outputContent.appendChild(empty);
      return;
    }

    // Assistant text of the current turn — what the output pane is for.
    if (t.assistant) {
      let content = t.assistant.content || '';
      // Model-emitted ora-visual envelopes: hand the turn's blocks to the
      // visual pane (canvas_action semantics, deduped per conversation+turn)
      // and swap the raw JSON fences for a one-line marker in the transcript.
      if (window.OraV3VisualDispatch) {
        const key = `${state.activeConversationId || ''}#${state.currentTurnIndex}`;
        window.OraV3VisualDispatch.dispatch(content, key);
        content = window.OraV3VisualDispatch.stripBlocks(content);
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
  };

  const renderAll = () => {
    refreshDOMRefs();
    if (outputPane) outputPane.classList.remove('has-content');
    renderHeader();
    renderTurn();
  };

  // ── Conversation loading (Backlog 2B) ──────────────────────────────────
  const load = async (conversation_id, opts = {}) => {
    if (!conversation_id) return;
    refreshDOMRefs();

    // Save draft for the conversation we're leaving.
    if (state.activeConversationId && leftInput) {
      saveDraft(state.activeConversationId, leftInput.value);
    }

    let envelope = null;
    try {
      const r = await fetch(`/api/conversation/${encodeURIComponent(conversation_id)}`);
      if (r.ok) envelope = await r.json();
    } catch (e) {
      console.warn('[v3-conversation] fetch failed:', e);
    }

    // Even if the fetch failed, switch the active id so subsequent
    // submits go to the right place.
    state.activeConversationId = conversation_id;
    state.activeTag            = (envelope && envelope.tag) || '';
    state.messages             = (envelope && envelope.messages) || [];
    state.turns                = groupTurns(state.messages);
    state.currentTurnIndex     = Math.max(0, state.turns.length - 1);
    if (Number.isInteger(opts.turnIndex)
        && opts.turnIndex >= 0
        && opts.turnIndex < state.turns.length) {
      state.currentTurnIndex = opts.turnIndex;
    }

    // Title derivation. The /api/conversation/<id> endpoint returns the
    // raw envelope without a derived title, so we derive it here:
    //   * is_welcome envelopes → fixed "Welcome to Ora"
    //   * otherwise → first user message content, trimmed to 60 chars
    //   * fallback → conversation_id
    if (envelope && envelope.is_welcome) {
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

    // Restore draft for the new conversation.
    if (leftInput) leftInput.value = loadDraft(conversation_id);

    // V3 Input Handling Phase 9 + V3 Backlog 2A canvas inverse — restore
    // the latest turn's canvas snapshot on conversation re-open. The
    // save side writes per-turn .ora-canvas files to
    // ~/ora/sessions/<id>/canvas/ + a stable latest.ora-canvas mirror.
    // Here we fetch the latest, decompress + parse via OraCanvasFileFormat,
    // and rehydrate the active visual panel via the panel.loadCanvasState
    // method patched in by v3-canvas-state-codec.js.
    //
    // Constraints from the design (Item 12 Q4):
    //   * Saved literal values are honored — colors / sizes / positions
    //     are restored exactly as captured. Theme changes do NOT
    //     retroactively repaint prior turns.
    //   * Always go through v3-canvas-state-codec (its deserialize
    //     handles Phase 7 shape types: bubbles, panel grids,
    //     shape-with-text). The older one-way canvas-serializer.js is
    //     left alone.
    //   * Same layer membership as save time (background / annotation /
    //     userInput) — the codec preserves this via the per-object
    //     ``layer`` field.
    //   * Re-hydrate ONLY on conversation load, not on turn navigation.
    //     The visual pane is a continuous workspace; turn arrows in the
    //     output pane do not pull canvas state.
    //   * Selection state is transient (the codec deliberately skips
    //     the selection layer on save), so the canvas opens with no
    //     active selection. Drawn shapes round-trip with full fidelity.
    window._oraLatestCanvasBytes = null;
    try {
      const canvasResp = await fetch(
        `/api/canvas/load/${encodeURIComponent(conversation_id)}`,
      );
      if (canvasResp.ok) {
        const buf = await canvasResp.arrayBuffer();
        window._oraLatestCanvasBytes = new Uint8Array(buf);
        // Parse + rehydrate. Both steps are best-effort; on any failure
        // the canvas opens clean and model-emitted envelopes still
        // render normally.
        if (window.OraCanvasFileFormat
            && typeof window.OraCanvasFileFormat.read === 'function') {
          try {
            const state = await window.OraCanvasFileFormat.read(
              window._oraLatestCanvasBytes,
            );
            const panel = (window.OraPanels && window.OraPanels.visual
                            && typeof window.OraPanels.visual._getActive === 'function')
                          ? window.OraPanels.visual._getActive()
                          : null;
            if (panel && typeof panel.loadCanvasState === 'function') {
              panel.loadCanvasState(state);
              console.info(
                `[v3-conversation] canvas rehydrated for ${conversation_id} `
                + `(${(state.objects || []).length} object(s))`,
              );
            } else {
              console.info(
                `[v3-conversation] canvas snapshot for ${conversation_id} `
                + `parsed but no active panel/loadCanvasState yet; bytes parked on window._oraLatestCanvasBytes`,
              );
            }
          } catch (e) {
            console.warn('[v3-conversation] canvas rehydrate failed:', e);
          }
        }
      }
    } catch (e) {
      console.warn('[v3-conversation] canvas-load fetch failed:', e);
    }

    renderAll();

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
  };

  // ── Turn navigation ────────────────────────────────────────────────────
  // Visual canvas tracks the active turn. Each turn was saved with a
  // timestamped .ora-canvas snapshot at submit time; the N-th snapshot
  // (sorted chronologically) corresponds to the N-th turn. The server's
  // /api/canvas/load endpoint resolves index → file when given ?turn=.
  const loadTurnCanvas = async (turnIndex) => {
    if (!state.activeConversationId) return;
    try {
      const url = `/api/canvas/load/${encodeURIComponent(state.activeConversationId)}?turn=${turnIndex}`;
      const resp = await fetch(url);
      if (!resp.ok) {
        // No canvas for that turn — clear to a blank canvas instead of
        // leaving the prior turn's content. Use the format's read-empty
        // pattern: an empty objects array.
        const panel = (window.OraPanels && window.OraPanels.visual
                        && typeof window.OraPanels.visual._getActive === 'function')
                      ? window.OraPanels.visual._getActive()
                      : null;
        if (panel && typeof panel.loadCanvasState === 'function') {
          try { panel.loadCanvasState({ objects: [] }); } catch (e) { /* non-fatal */ }
        }
        return;
      }
      const buf = await resp.arrayBuffer();
      if (window.OraCanvasFileFormat
          && typeof window.OraCanvasFileFormat.read === 'function') {
        const cs = await window.OraCanvasFileFormat.read(new Uint8Array(buf));
        const panel = (window.OraPanels && window.OraPanels.visual
                        && typeof window.OraPanels.visual._getActive === 'function')
                      ? window.OraPanels.visual._getActive()
                      : null;
        if (panel && typeof panel.loadCanvasState === 'function') {
          panel.loadCanvasState(cs);
        }
      }
    } catch (e) {
      console.warn('[v3-conversation] turn-canvas load failed:', e);
    }
  };

  const showTurn = (index) => {
    const total = state.turns.length;
    if (total === 0) return;
    const clamped = Math.max(0, Math.min(total - 1, index));
    state.currentTurnIndex = clamped;
    renderHeader();
    renderTurn();
    // Pull the canvas snapshot that was saved alongside this turn so the
    // visual pane stays in sync with the text output.
    loadTurnCanvas(clamped);
  };

  const goBack    = () => showTurn(state.currentTurnIndex - 1);
  const goForward = () => showTurn(state.currentTurnIndex + 1);

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

  // Debounced draft saver wired to the left input's input event.
  let draftTimer = null;
  const queueDraftSave = () => {
    if (!state.activeConversationId || !leftInput) return;
    if (draftTimer) clearTimeout(draftTimer);
    draftTimer = setTimeout(() => {
      saveDraft(state.activeConversationId, leftInput.value);
    }, DRAFT_DEBOUNCE);
  };

  // ── Rename UI (Backlog 2C) ─────────────────────────────────────────────
  // Click the display name in the output-pane header to edit it.
  // Enter saves; Esc cancels. Empty save clears the override (UI falls
  // back to the derived title). The conversation_id never changes.
  const beginRenameDisplayName = () => {
    if (!displayName) return;
    if (!state.activeConversationId) return;
    if (displayName.classList.contains('is-renaming')) return;

    const original = state.activeTitle || '';
    displayName.classList.add('is-renaming');

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'output-pane-display-name-input';
    input.value = original;
    input.maxLength = 200;
    input.setAttribute('aria-label', 'Conversation name');

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
      if (next === original) {
        displayName.textContent = original;
        return;
      }
      try {
        const r = await fetch(
          `/api/conversation/${encodeURIComponent(state.activeConversationId)}/rename`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ display_name: next }),
          }
        );
        if (r.ok) {
          const data = await r.json();
          state.activeTitle = data.display_name || next || original;
          displayName.textContent = state.activeTitle;
          // Tell the sidebar to refresh so the row title updates too.
          if (window.OraSidebar && typeof window.OraSidebar.refresh === 'function') {
            window.OraSidebar.refresh();
          }
        } else {
          displayName.textContent = original;
        }
      } catch (e) {
        displayName.textContent = original;
      }
    };

    const abort = () => {
      if (finished) return;
      cleanup();
      displayName.textContent = original;
    };

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter')      { e.preventDefault(); commit(); }
      else if (e.key === 'Escape') { e.preventDefault(); abort();  }
    });
    input.addEventListener('blur', commit);
  };

  // ── Wire everything on DOMContentLoaded ────────────────────────────────
  const init = () => {
    refreshDOMRefs();

    if (navBack)    navBack.addEventListener('click', goBack);
    if (navForward) navForward.addEventListener('click', goForward);

    if (displayName) {
      displayName.addEventListener('click', () => {
        if (!state.activeConversationId) return;
        beginRenameDisplayName();
      });
      displayName.classList.add('is-clickable');
      displayName.title = 'Click to rename';
    }

    if (leftInput) {
      leftInput.addEventListener('input', queueDraftSave);
    }

    // Listen for conversation selections from the sidebar. Mode UI is
    // already activated by the existing handler in the inline script;
    // this loads the actual content.
    document.addEventListener('ora:conversation-selected', (e) => {
      const id = e.detail && e.detail.conversation_id;
      const turnIndex = e.detail && e.detail.matched_turn_index;
      if (id) load(id, { turnIndex });
    });

    // Re-render header on mode-change so the mode icon updates when the
    // user toggles modes via spine buttons (without conversation switch).
    // The body class transitions handled by setMode() in the inline
    // script update CSS state; we just refresh the icon glyph here.
    const modeObserver = new MutationObserver(() => {
      if (state.activeConversationId) {
        // If active conversation has a tag, that's the source of truth.
        // Otherwise, reflect the visual mode the user has clicked into.
        // (Tag is immutable per Phase 1.1, so for tagged conversations
        // we don't change activeTag here.)
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
    saveDraft,
    loadDraft,
    clearDraft,
    getActiveConversationId: () => state.activeConversationId,
    getTurnCount:            () => state.turns.length,
    getCurrentTurn:          () => state.turns[state.currentTurnIndex] || null,
  };
})();
