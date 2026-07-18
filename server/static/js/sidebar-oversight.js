/* V3 sidebar — governed Process attention plus legacy oversight panels.
 *
 * Two-supergroup accordion: Dialogues / Processes. The Process surface projects
 * durable governed state into Unread, Pending, and Automated Processes. The
 * pre-existing Paused/Operating queues remain below as explicitly legacy views.
 *
 * Data:
 *   GET /api/process-attention     — authenticated Phase 2.4 projection
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
  const attentionUnreadList = sidebar.querySelector('#processAttentionUnreadList');
  const attentionPendingList = sidebar.querySelector('#processAttentionPendingList');
  const attentionAutomatedList = sidebar.querySelector('#processAttentionAutomatedList');
  const pausedCount    = sidebar.querySelector('#sidebarPausedCount');
  const operatingCount = sidebar.querySelector('#sidebarOperatingCount');
  const attentionUnreadCount = sidebar.querySelector('#processAttentionUnreadCount');
  const attentionPendingCount = sidebar.querySelector('#processAttentionPendingCount');
  const attentionAutomatedCount = sidebar.querySelector('#processAttentionAutomatedCount');
  const processesCount = sidebar.querySelector('#sidebarProcessesCount');

  const state = {
    paused:    [],
    operating: [],
    attention: { unread: [], pending: [], automated_processes: [] },
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
    // Expanding Processes refreshes the governed projection and legacy queues.
    if (name === 'processes') {
      refreshAll();
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

  const fetchProcessAttention = async () => {
    try {
      const r = await fetch('/api/process-attention');
      if (!r.ok) return;
      const data = await r.json();
      if (!data.ok) return;
      state.attention = {
        unread: data.unread || [],
        pending: data.pending || [],
        automated_processes: data.automated_processes || [],
      };
      renderProcessAttention();
      updateAttentionCounts();
      const needsAttention = state.attention.unread.length > 0
        || state.attention.pending.some(item => item.needs_attention === true);
      sidebar.dataset.processAttention = needsAttention ? 'true' : 'false';
      document.dispatchEvent(new CustomEvent('ora:process-attention-changed', {
        detail: { needs_attention: needsAttention },
      }));
    } catch (e) {}
  };

  const refreshAll = async () => {
    await Promise.all([fetchProcessAttention(), fetchPaused(), fetchOperating()]);
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
    const runIds = new Set();
    state.attention.pending.forEach(item => runIds.add(item.run_id));
    state.attention.unread.forEach(item => runIds.add(item.run_id));
    const total = runIds.size + state.attention.automated_processes.length
      + state.paused.length + state.operating.length;
    processesCount.textContent = String(total);
    processesCount.dataset.count = String(total);
  };

  const setCount = (element, value) => {
    if (!element) return;
    element.textContent = String(value);
    element.dataset.count = String(value);
  };

  const updateAttentionCounts = () => {
    setCount(attentionUnreadCount, state.attention.unread.length);
    setCount(attentionPendingCount, state.attention.pending.length);
    setCount(attentionAutomatedCount, state.attention.automated_processes.length);
    updateProcessesCount();
  };

  // ── Render: governed Process attention ──────────────────────────────

  const renderProcessAttention = () => {
    renderProcessRows(attentionUnreadList, state.attention.unread, 'unread');
    renderProcessRows(attentionPendingList, state.attention.pending, 'pending');
    renderAutomatedRows();
  };

  const renderProcessRows = (container, rows, surface) => {
    if (!container) return;
    container.innerHTML = '';
    rows.forEach(row => container.appendChild(buildProcessRunCard(row, surface)));
  };

  const appendBadge = (container, value, extraClass) => {
    if (!value) return;
    const badge = document.createElement('span');
    badge.className = `badge${extraClass ? ' ' + extraClass : ''}`;
    badge.textContent = value;
    container.appendChild(badge);
  };

  const buildProcessRunCard = (row, surface) => {
    const card = document.createElement('div');
    card.className = 'oversight-card process-attention-card';
    card.dataset.runId = row.run_id || '';
    card.dataset.surface = surface;
    card.dataset.needsAttention = row.needs_attention ? 'true' : 'false';
    card.dataset.engagement = surface === 'unread' ? 'unseen' : 'seen';

    const name = document.createElement('div');
    name.className = 'oversight-card-name';
    name.textContent = row.title || row.run_id || '(untitled Process Run)';
    card.appendChild(name);

    const meta = document.createElement('div');
    meta.className = 'oversight-card-meta';
    appendBadge(meta, row.visible_status || row.run_state,
      row.needs_attention ? 'attention' : '');
    appendBadge(meta, row.project_ref || '');
    if (row.current_step) {
      const step = document.createElement('span');
      step.textContent = row.current_step;
      meta.appendChild(step);
    }
    card.appendChild(meta);

    if (row.attention) {
      const detail = document.createElement('div');
      detail.className = 'process-attention-detail';
      const condition = document.createElement('div');
      condition.textContent = row.attention.condition || '';
      detail.appendChild(condition);
      const decision = document.createElement('div');
      decision.className = 'process-attention-required';
      decision.textContent = typeof row.attention.required_decision === 'string'
        ? row.attention.required_decision
        : JSON.stringify(row.attention.required_decision || {});
      detail.appendChild(decision);
      const evidenceRefs = row.attention.evidence_refs || [];
      if (evidenceRefs.length) {
        const evidence = document.createElement('div');
        evidence.className = 'process-attention-evidence';
        evidence.textContent = 'Evidence: ' + evidenceRefs.map(ref => (
          typeof ref === 'string' ? ref : JSON.stringify(ref)
        )).join('; ');
        detail.appendChild(evidence);
      }
      const results = row.attention.result_artifacts || [];
      if (results.length) {
        const artifacts = document.createElement('div');
        artifacts.className = 'process-attention-results';
        artifacts.textContent = 'Results: ' + results.map(item => (
          `${item.artifact_id} (${item.identity_digest})`
        )).join('; ');
        detail.appendChild(artifacts);
      }
      card.appendChild(detail);
    }

    if (row.dialogue_ref) {
      card.tabIndex = 0;
      card.setAttribute('role', 'button');
      card.title = 'Open the governing Dialogue';
      const open = () => openProcessDialogue(row);
      card.addEventListener('click', open);
      card.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          open();
        }
      });
    }
    return card;
  };

  const openProcessDialogue = async (row) => {
    if (!row.dialogue_ref) return;
    if (row.needs_attention) {
      try {
        await fetch(`/api/conversation/${encodeURIComponent(row.dialogue_ref)}/mark-read`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
        });
      } catch (e) {}
    }
    document.dispatchEvent(new CustomEvent('ora:conversation-selected', {
      detail: {
        conversation_id: row.dialogue_ref,
        title: row.title || 'Process',
        tag: '',
      },
    }));
    fetchProcessAttention();
  };

  const renderAutomatedRows = () => {
    if (!attentionAutomatedList) return;
    attentionAutomatedList.innerHTML = '';
    state.attention.automated_processes.forEach(row => {
      const card = document.createElement('div');
      card.className = 'oversight-card process-attention-card';
      card.dataset.surface = 'automated';
      card.dataset.engagement = 'seen';
      card.dataset.needsAttention = 'false';
      const name = document.createElement('div');
      name.className = 'oversight-card-name';
      name.textContent = row.title || row.definition_ref.definition_id;
      card.appendChild(name);
      const meta = document.createElement('div');
      meta.className = 'oversight-card-meta';
      appendBadge(meta, row.status || 'Deployed');
      appendBadge(meta, `trigger: ${row.trigger_binding}`);
      appendBadge(meta, `authority: ${row.authority_binding}`);
      card.appendChild(meta);
      attentionAutomatedList.appendChild(card);
    });
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

    if (entry.trace_ref) {
      const traceBtn = document.createElement('button');
      traceBtn.type = 'button';
      traceBtn.textContent = 'Open trace';
      traceBtn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        if (window.OraTraceWalk && typeof window.OraTraceWalk.open === 'function') {
          window.OraTraceWalk.open({
            trace_ref: entry.trace_ref,
            step: entry.trace_step || '',
          });
        }
      });
      actions.appendChild(traceBtn);
      const investigateBtn = document.createElement('button');
      investigateBtn.type = 'button';
      investigateBtn.textContent = 'Investigate trace';
      investigateBtn.addEventListener('click', async (ev) => {
        ev.stopPropagation();
        const ref = String(entry.trace_ref || '');
        const conv = ref.split('/')[0] || entry.conversation_id || '';
        const original = investigateBtn.textContent;
        investigateBtn.disabled = true;
        investigateBtn.textContent = 'Submitting...';
        try {
          await sendChatTurn(conv, 'Investigate this trace.', { trace_ref: ref, step_hint: entry.trace_step || '', symptom: '', source: 'paused-card' });
          investigateBtn.textContent = 'Investigation submitted';
        } catch (e) {
          investigateBtn.textContent = (e && e.message) || 'Investigation failed';
          window.setTimeout(() => { investigateBtn.textContent = original; investigateBtn.disabled = false; }, 2500);
        }
      });
      actions.appendChild(investigateBtn);
    }

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

  const sendChatTurn = async (conversationId, text, traceDebug) => {
    try {
      const body = { message: text, conversation_id: conversationId, panel_id: conversationId };
      if (traceDebug) body.trace_debug = traceDebug;
      const response = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        let msg = `Chat request failed (${response.status})`;
        try {
          const payload = await response.json();
          msg = payload.error || payload.message || msg;
        } catch (_) {}
        throw new Error(msg);
      }
    } catch (e) {
      throw e;
    }
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
      card.title = 'Click to open the elicitation Dialogue';
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
