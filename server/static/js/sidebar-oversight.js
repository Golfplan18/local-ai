/* V3 sidebar — Paused + Operating panels (oversight).
 *
 * Three-supergroup accordion: Conversations / Paused / Operating. Mutually
 * exclusive expansion. Clicking a header collapses the others. Conversations
 * starts expanded; the oversight panels expand on demand.
 *
 * Data:
 *   GET /api/oversight/paused    — Paused entries for resolution
 *   GET /api/oversight/operating — Operating items (read-only in v1)
 *
 * Actions on a Paused card:
 *   - Click name → enter rename mode
 *   - Click anywhere else → expand detail (reasoning + Approve / Deny / Discuss)
 *   - Approve   → POST /api/oversight/paused/<id>/discuss isn't needed here;
 *                 the slash-command flow is reused via /resolve text input;
 *                 for the immediate-action buttons we POST a small commit
 *                 endpoint /api/oversight/resolve below (or fall back to
 *                 the existing /approve / /deny slash commands by routing
 *                 through chat). For v1 we use the slash-command path so we
 *                 share machinery with the chat resolution chain — the
 *                 sidebar opens the conversation and types "1" or "2".
 *   - Discuss   → POST /api/oversight/paused/<id>/discuss; opens the
 *                 returned conversation_id in the chat pane.
 *
 * Refresh: poll every 12s, same cadence as the conversations sidebar.
 */
(() => {
  const sidebar = document.querySelector('.left-sidebar');
  if (!sidebar) return;
  const accordion = sidebar.querySelector('.sidebar-accordion');
  if (!accordion) return;

  const POLL_MS = 12000;

  const supers = [...accordion.querySelectorAll('.sidebar-supergroup')];
  const headerByName = name =>
    accordion.querySelector(`.sidebar-supergroup-header[data-super-toggle="${name}"]`);
  const supergroupByName = name =>
    accordion.querySelector(`.sidebar-supergroup[data-super="${name}"]`);

  const pausedList     = sidebar.querySelector('#oversightPausedList');
  const operatingList  = sidebar.querySelector('#oversightOperatingList');
  const pausedCount    = sidebar.querySelector('#sidebarPausedCount');
  const operatingCount = sidebar.querySelector('#sidebarOperatingCount');
  const processesCount = sidebar.querySelector('#sidebarProcessesCount');

  const state = {
    paused:    [],
    operating: [],
    expanded:  null, // detail-expanded entry id within Paused
  };

  // ── Accordion behavior ────────────────────────────────────────────────

  const setActiveSuper = (name) => {
    accordion.dataset.activeSuper = name;
    for (const sg of supers) {
      const isThis = sg.dataset.super === name;
      sg.dataset.expanded = isThis ? 'true' : 'false';
      const header = sg.querySelector('.sidebar-supergroup-header');
      if (header) header.setAttribute('aria-expanded', isThis ? 'true' : 'false');
      const arrow = sg.querySelector('.sidebar-supergroup-arrow');
      if (arrow) arrow.textContent = isThis ? '▾' : '▸';
    }
    // When expanding the Automated Processes super-group, fetch both
    // Paused and Operating in parallel.
    if (name === 'processes') {
      fetchPaused();
      fetchOperating();
    }
  };

  for (const sg of supers) {
    const header = sg.querySelector('.sidebar-supergroup-header');
    if (!header) continue;
    header.addEventListener('click', () => {
      const name = header.dataset.superToggle;
      if (!name) return;
      setActiveSuper(name);
    });
  }

  // ── Polling ───────────────────────────────────────────────────────────

  const fetchPaused = async () => {
    try {
      const r = await fetch('/api/oversight/paused');
      if (!r.ok) return;
      const data = await r.json();
      state.paused = data.entries || [];
      renderPaused();
      updatePausedCount();
    } catch (e) {}
  };

  const fetchOperating = async () => {
    try {
      const r = await fetch('/api/oversight/operating');
      if (!r.ok) return;
      const data = await r.json();
      state.operating = data.entries || [];
      renderOperating();
      updateOperatingCount();
    } catch (e) {}
  };

  const refreshAll = async () => {
    await Promise.all([fetchPaused(), fetchOperating()]);
  };

  // ── Counts ────────────────────────────────────────────────────────────

  const updatePausedCount = () => {
    if (pausedCount) {
      const n = state.paused.length;
      pausedCount.textContent = String(n);
      pausedCount.dataset.count = String(n);
    }
    updateProcessesCount();
  };

  const updateOperatingCount = () => {
    if (operatingCount) {
      const n = state.operating.length;
      operatingCount.textContent = String(n);
      operatingCount.dataset.count = String(n);
    }
    updateProcessesCount();
  };

  const updateProcessesCount = () => {
    if (!processesCount) return;
    const total = state.paused.length + state.operating.length;
    processesCount.textContent = String(total);
    processesCount.dataset.count = String(total);
  };

  // ── Render: Paused ────────────────────────────────────────────────────

  const renderPaused = () => {
    if (!pausedList) return;
    pausedList.innerHTML = '';
    for (const e of state.paused) {
      pausedList.appendChild(buildPausedCard(e));
    }
  };

  const buildPausedCard = (entry) => {
    const card = document.createElement('div');
    card.className = 'oversight-card';
    card.dataset.entryId = entry.id;
    card.dataset.engagement = entry.engagement || 'unseen';

    const nameEl = document.createElement('div');
    nameEl.className = 'oversight-card-name';
    nameEl.textContent = entry.name || '(unnamed)';
    nameEl.title = 'Click to expand · double-click to rename';
    nameEl.addEventListener('dblclick', (ev) => {
      ev.stopPropagation();
      enterRenameMode(entry, nameEl);
    });
    card.appendChild(nameEl);

    const meta = document.createElement('div');
    meta.className = 'oversight-card-meta';
    if (entry.project_nexus) {
      const tag = document.createElement('span');
      tag.className = 'badge';
      tag.textContent = entry.project_nexus;
      meta.appendChild(tag);
    }
    if (entry.event_type) {
      const tag = document.createElement('span');
      tag.className = 'badge';
      tag.textContent = entry.event_type;
      meta.appendChild(tag);
    }
    if (entry.discussion_conversation_id) {
      const tag = document.createElement('span');
      tag.className = 'badge discussing';
      tag.textContent = '📎 discussing';
      tag.title = 'Active discussion — click to open';
      tag.addEventListener('click', (ev) => {
        ev.stopPropagation();
        openDiscussionConversation(entry.discussion_conversation_id, entry);
      });
      meta.appendChild(tag);
    }
    if (entry.queued_at) {
      const tag = document.createElement('span');
      tag.textContent = ageOf(entry.queued_at);
      meta.appendChild(tag);
    }
    card.appendChild(meta);

    if (state.expanded === entry.id) {
      card.appendChild(buildPausedDetail(entry));
    }

    card.addEventListener('click', (ev) => {
      // Don't toggle when clicking the rename input or one of the meta badges
      if (ev.target.closest('.oversight-card-name-edit')) return;
      if (ev.target.closest('.oversight-detail-actions')) return;
      if (ev.target.closest('.badge')) return;
      const wasExpanded = state.expanded === entry.id;
      state.expanded = wasExpanded ? null : entry.id;
      // Mark seen on first expansion
      if (!wasExpanded && entry.engagement === 'unseen') {
        markEngagement(entry.id, 'seen');
      }
      renderPaused();
    });

    return card;
  };

  const buildPausedDetail = (entry) => {
    const det = document.createElement('div');
    det.className = 'oversight-detail';

    const reasoning = document.createElement('div');
    reasoning.className = 'oversight-detail-reasoning';
    reasoning.textContent = entry.reasoning_excerpt || '(no reasoning recorded)';
    det.appendChild(reasoning);

    const actions = document.createElement('div');
    actions.className = 'oversight-detail-actions';

    const approveBtn = document.createElement('button');
    approveBtn.type = 'button';
    approveBtn.className = 'primary';
    approveBtn.textContent = 'Approve';
    approveBtn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      quickAction(entry, 'approve');
    });
    actions.appendChild(approveBtn);

    const denyBtn = document.createElement('button');
    denyBtn.type = 'button';
    denyBtn.textContent = 'Deny';
    denyBtn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const reason = window.prompt('Reason for denial (optional):', '') || '';
      quickAction(entry, 'deny', { reason });
    });
    actions.appendChild(denyBtn);

    const discussBtn = document.createElement('button');
    discussBtn.type = 'button';
    discussBtn.textContent = entry.discussion_conversation_id ? 'Open discussion' : 'Discuss';
    discussBtn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      startDiscussion(entry);
    });
    actions.appendChild(discussBtn);

    det.appendChild(actions);
    return det;
  };

  const enterRenameMode = (entry, nameEl) => {
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'oversight-card-name-edit';
    input.value = entry.name || '';
    input.addEventListener('keydown', async (ev) => {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        await commitRename(entry.id, input.value);
      } else if (ev.key === 'Escape') {
        ev.preventDefault();
        renderPaused();
      }
    });
    input.addEventListener('blur', async () => {
      await commitRename(entry.id, input.value);
    });
    nameEl.replaceWith(input);
    input.focus();
    input.select();
  };

  const commitRename = async (entryId, newName) => {
    const trimmed = (newName || '').trim();
    if (!trimmed) {
      renderPaused();
      return;
    }
    try {
      await fetch(`/api/oversight/paused/${encodeURIComponent(entryId)}/name`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: trimmed }),
      });
    } catch (e) {}
    await fetchPaused();
  };

  const markEngagement = async (entryId, stateName) => {
    try {
      await fetch(`/api/oversight/paused/${encodeURIComponent(entryId)}/engagement`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state: stateName }),
      });
    } catch (e) {}
    // Update local state without a full refetch — keeps the bold→regular
    // transition snappy.
    const local = state.paused.find(e => e.id === entryId);
    if (local) local.engagement = stateName;
    renderPaused();
  };

  // ── Quick approve/deny via the discussion conversation ────────────────
  // Uses the resolution_chain plumbing already wired into the chat pipeline:
  // open (or create) the discussion conversation, send "1" or "2" as a
  // chat turn, the pipeline routes it through resolution_chain.continue.

  const quickAction = async (entry, action, opts = {}) => {
    let convId = entry.discussion_conversation_id;
    if (!convId) {
      const created = await createDiscussion(entry.id);
      if (!created) return;
      convId = created.conversation_id;
    }
    const numericInput = action === 'approve' ? '1' : '2';
    // For "deny with a reason," we send the reason as a normal turn first
    // (so it lands in the conversation), then "2".
    if (action === 'deny' && opts.reason) {
      await sendChatTurn(convId, opts.reason);
    }
    await sendChatTurn(convId, numericInput);
    await fetchPaused();
    state.expanded = null;
    renderPaused();
  };

  const createDiscussion = async (entryId) => {
    try {
      const r = await fetch(
        `/api/oversight/paused/${encodeURIComponent(entryId)}/discuss`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' },
      );
      if (!r.ok) return null;
      return await r.json();
    } catch (e) { return null; }
  };

  const startDiscussion = async (entry) => {
    const created = await createDiscussion(entry.id);
    if (!created) return;
    openDiscussionConversation(created.conversation_id, entry);
    fetchPaused();
  };

  const openDiscussionConversation = (conversationId, entry) => {
    // Notify the rest of the V3 UI that a different conversation should
    // take over the chat pane. Mirrors the conversation-selected event
    // emitted by the conversations sidebar.
    document.dispatchEvent(new CustomEvent('ora:conversation-selected', {
      detail: {
        conversation_id: conversationId,
        title: entry ? `Resolve: ${entry.name}` : 'Resolution',
        tag: '',
      },
    }));
  };

  const sendChatTurn = async (conversationId, text) => {
    try {
      await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          conversation_id: conversationId,
        }),
      });
    } catch (e) {}
  };

  // ── Render: Operating ─────────────────────────────────────────────────

  const renderOperating = () => {
    if (!operatingList) return;
    operatingList.innerHTML = '';
    for (const e of state.operating) {
      operatingList.appendChild(buildOperatingCard(e));
    }
  };

  const buildOperatingCard = (entry) => {
    const card = document.createElement('div');
    card.className = 'oversight-card';
    card.dataset.engagement = 'seen'; // Operating items don't have unread state
    const name = document.createElement('div');
    name.className = 'oversight-card-name';
    name.textContent = entry.name || '(unnamed task)';
    card.appendChild(name);

    const meta = document.createElement('div');
    meta.className = 'oversight-card-meta';
    if (entry.kind) {
      const tag = document.createElement('span');
      tag.className = 'badge';
      tag.textContent = entry.kind;
      meta.appendChild(tag);
    }
    if (entry.project_nexus) {
      const tag = document.createElement('span');
      tag.className = 'badge';
      tag.textContent = entry.project_nexus;
      meta.appendChild(tag);
    }
    if (entry.framework_id) {
      const tag = document.createElement('span');
      tag.className = 'badge';
      tag.textContent = `${entry.framework_id}${entry.mode ? ' / ' + entry.mode : ''}`;
      meta.appendChild(tag);
    }
    if (entry.started_at) {
      const tag = document.createElement('span');
      tag.textContent = ageOf(entry.started_at);
      meta.appendChild(tag);
    }
    card.appendChild(meta);

    // Operating items with a conversation_id (e.g. active elicitations)
    // can be clicked to jump into the conversation.
    if (entry.conversation_id) {
      card.addEventListener('click', () => {
        document.dispatchEvent(new CustomEvent('ora:conversation-selected', {
          detail: {
            conversation_id: entry.conversation_id,
            title: entry.name,
            tag: '',
          },
        }));
      });
      card.title = 'Click to open the elicitation conversation';
    }
    return card;
  };

  // ── Helpers ───────────────────────────────────────────────────────────

  const ageOf = (isoTimestamp) => {
    if (!isoTimestamp) return '';
    try {
      const t = new Date(isoTimestamp).getTime();
      const now = Date.now();
      const ms = now - t;
      if (Number.isNaN(ms) || ms < 0) return '';
      const m = Math.floor(ms / 60000);
      if (m < 1) return 'just now';
      if (m < 60) return `${m}m`;
      const h = Math.floor(m / 60);
      if (h < 24) return `${h}h`;
      const d = Math.floor(h / 24);
      return `${d}d`;
    } catch (e) { return ''; }
  };

  // ── Boot ──────────────────────────────────────────────────────────────

  // Initial fetch even though the panels are collapsed, so the count
  // badges populate.
  refreshAll();

  let pollHandle = null;
  const startPoll = () => {
    if (pollHandle) return;
    pollHandle = setInterval(refreshAll, POLL_MS);
  };
  const stopPoll = () => {
    if (pollHandle) { clearInterval(pollHandle); pollHandle = null; }
  };
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stopPoll();
    else { refreshAll(); startPoll(); }
  });
  if (!document.hidden) startPoll();
})();
