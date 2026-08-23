/* V3 sidebar — ordinary oversight panels.
 *
 * Two-supergroup accordion: Dialogues / Oversight. The existing Paused and
 * Operating queues remain available; Programming progress is shown inline in
 * its explicit input-panel session.
 *
 * Data:
 *   GET /api/oversight/paused    — Paused entries for resolution
 *   GET /api/oversight/operating — Operating items (read-only in v1)
 *   GET /api/triggers            — Scheduled Triggers + lane health + the
 *                                  count of deadlines Ora arms for itself
 *
 * Scheduled is the third list rather than a screen of its own because it
 * answers the same question as the other two — what is Ora doing that is not
 * this conversation — and because it shares this file's single poll loop and
 * accordion owner.
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
  const pausedList     = sidebar.querySelector('#oversightPausedList');
  const operatingList  = sidebar.querySelector('#oversightOperatingList');
  const pausedCount    = sidebar.querySelector('#sidebarPausedCount');
  const operatingCount = sidebar.querySelector('#sidebarOperatingCount');
  const processesCount = sidebar.querySelector('#sidebarProcessesCount');
  const triggerList    = sidebar.querySelector('#triggerList');
  const triggerCount   = sidebar.querySelector('#sidebarScheduledCount');
  const triggerNote    = sidebar.querySelector('#triggerInternalNote');
  const triggerWarning = sidebar.querySelector('#triggerLaneWarning');
  const triggerNewBtn  = sidebar.querySelector('#triggerNewButton');

  const state = {
    paused:    [],
    operating: [],
    expanded:  null, // detail-expanded entry id within Paused
    triggers:  [],
    triggerExpanded: null,
    triggerReview:   null, // {trigger_id, …} while an activation is pending
    internalDeadlines: null,
    laneHealth: null,
    actions: null,         // cached /api/triggers/actions for the form
    triggerInspection: null,
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
    // Expanding Oversight refreshes the existing queues.
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

  const fetchTriggers = async () => {
    try {
      const r = await fetch('/api/triggers');
      if (!r.ok) return;
      const data = await r.json();
      state.triggers = data.triggers || [];
      state.internalDeadlines = data.internal_deadlines || null;
      state.laneHealth = data.lane_health || null;
      renderTriggers();
      updateTriggerCount();
    } catch (e) {}
  };

  const refreshAll = async () => {
    await Promise.all([fetchPaused(), fetchOperating(), fetchTriggers()]);
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

  const updateTriggerCount = () => {
    if (triggerCount) {
      // Active Triggers, not every draft: the count answers "how much is
      // armed right now", which a draft is not.
      const n = state.triggers.filter(t => t.status === 'active').length;
      triggerCount.textContent = String(n);
      triggerCount.dataset.count = String(n);
    }
    updateProcessesCount();
  };

  const updateProcessesCount = () => {
    if (!processesCount) return;
    const armed = state.triggers.filter(t => t.status === 'active').length;
    const total = state.paused.length + state.operating.length + armed;
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
      tag.textContent = entry.review_kind === 'execution_review_escalation'
        ? 'Execution Review'
        : entry.event_type;
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

    if (entry.review_kind === 'execution_review_escalation') {
      const explanation = document.createElement('div');
      explanation.className = 'oversight-detail-reasoning execution-review-explanation';
      explanation.textContent = entry.user_explanation
        || 'Ora could not independently verify this turn. Review the evidence before approving.';
      det.appendChild(explanation);

      if (entry.abandoned_attempt_branch) {
        const branch = document.createElement('div');
        branch.className = 'oversight-detail-reasoning execution-review-branch';
        branch.textContent = `Preserved attempt: ${entry.abandoned_attempt_branch}`;
        det.appendChild(branch);
      }
    }

    const reasoning = document.createElement('div');
    reasoning.className = 'oversight-detail-reasoning';
    reasoning.textContent = entry.reasoning_excerpt || '(no reasoning recorded)';
    det.appendChild(reasoning);

    const actions = document.createElement('div');
    actions.className = 'oversight-detail-actions';

    // A spent card's approval request is gone or already consumed, so
    // Approve and Deny would both dead-end at "[Unauthenticated …]" and —
    // worse — would report success while the card survived. Offer the one
    // action that can still work, and say why.
    if (entry.spent) {
      const why = document.createElement('div');
      why.className = 'oversight-detail-reasoning oversight-spent-note';
      why.textContent =
        'This card can no longer approve or deny anything: the approval '
        + 'request behind it is already spent. Dismissing it clears the card '
        + 'and grants nothing.';
      det.appendChild(why);

      const dismissBtn = document.createElement('button');
      dismissBtn.type = 'button';
      dismissBtn.className = 'primary';
      dismissBtn.textContent = 'Dismiss';
      dismissBtn.addEventListener('click', async (ev) => {
        ev.stopPropagation();
        dismissBtn.disabled = true;
        dismissBtn.textContent = 'Dismissing…';
        await dismissEntry(entry, dismissBtn);
      });
      actions.appendChild(dismissBtn);
      det.appendChild(actions);
      return det;
    }

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
      convId = await sendChatTurn(convId, opts.reason, null, opts.reason);
      if (!convId) return;
    }
    await sendChatTurn(convId, numericInput);
    await fetchPaused();
    state.expanded = null;
    renderPaused();
  };

  const dismissEntry = async (entry, button) => {
    try {
      const r = await fetch(
        `/api/oversight/paused/${encodeURIComponent(entry.id)}/dismiss`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' },
      );
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        button.disabled = false;
        button.textContent = 'Dismiss';
        window.alert(data.message || 'The card was not dismissed.');
        return;
      }
      state.expanded = null;
      await fetchPaused();
    } catch (e) {
      button.disabled = false;
      button.textContent = 'Dismiss';
    }
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

  const sendChatTurn = async (conversationId, text, traceDebug, privacyText) => {
    const body = { message: text, conversation_id: conversationId, panel_id: conversationId };
    if (traceDebug) body.trace_debug = traceDebug;
    const conversation = window.OraConversation;
    if (!conversation || typeof conversation.submitChatTurn !== 'function') {
      throw new Error('Dialogue privacy boundary is unavailable');
    }
    return conversation.submitChatTurn(
      body, privacyText ? { privacyText: privacyText } : {}
    );
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

  // ── Render: Scheduled ─────────────────────────────────────────────────

  const CAUSE_LABEL = {
    manual: 'manual only',
    file_change: 'on file change',
    calendar: 'on a schedule',
    trigger_completion: 'after another Trigger',
  };

  const whenOf = (isoTimestamp) => {
    if (!isoTimestamp) return '';
    try {
      const d = new Date(isoTimestamp);
      return Number.isNaN(d.getTime()) ? '' : d.toLocaleString();
    } catch (e) { return ''; }
  };

  const conditionSummary = (spec) => {
    const c = spec.condition || {};
    if (spec.cause === 'calendar') {
      const s = c.schedule || {};
      const days = (s.cadence === 'weekly' && (s.weekdays || []).length)
        ? ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            .filter((_, i) => s.weekdays.includes(i)).join(', ')
        : 'every day';
      return `${days} at ${s.local_time} ${s.timezone} · missed windows: ${s.missed_policy}`;
    }
    if (spec.cause === 'file_change') {
      const paths = c.path_selectors || [];
      return paths.length === 1 ? paths[0] : `${paths.length} watched paths`;
    }
    if (spec.cause === 'trigger_completion') {
      return `when ${c.source_trigger_id} finishes successfully`;
    }
    return 'runs only when you run it';
  };

  const actionSummary = (spec) => {
    const a = spec.action || {};
    if (a.kind === 'project_tool') {
      const args = (a.args || []).join(' ');
      return `${a.nexus}:${a.tool}${args ? ' ' + args : ''}`;
    }
    if (a.kind === 'email_send') {
      return `email via Fastmail to ${(a.to || []).join(', ')}`
        + ` · ${a.subject || '(no subject)'}`;
    }
    return `framework ${a.framework}`;
  };

  const renderTriggers = () => {
    renderLaneWarning();
    renderInternalNote();
    if (!triggerList) return;
    triggerList.innerHTML = '';
    if (!state.triggers.length) {
      const empty = document.createElement('div');
      empty.className = 'oversight-empty';
      empty.textContent = 'Nothing scheduled. Use + to declare a Trigger.';
      triggerList.appendChild(empty);
      return;
    }
    for (const t of state.triggers) triggerList.appendChild(buildTriggerCard(t));
  };

  const renderLaneWarning = () => {
    if (!triggerWarning) return;
    const health = state.laneHealth;
    const armed = state.triggers.some(t => t.status === 'active');
    let message = '';
    if (health && health.available && armed) {
      if (!health.running || !health.deadline_lane) {
        message = 'The lane that fires scheduled Triggers is not running. '
                + 'Nothing here will fire until Ora is restarted.';
      } else if (health.deadline_lane_restarts >= 3) {
        message = `The deadline lane has restarted `
                + `${health.deadline_lane_restarts} times. It is running, but `
                + `work arriving during each outage was lost.`;
      } else if (health.event_lane_restarts >= 3
                 && state.triggers.some(t => t.spec.cause === 'file_change')) {
        message = `The file-event lane has restarted `
                + `${health.event_lane_restarts} times. File changes during `
                + `each outage raised no Trigger.`;
      }
    }
    triggerWarning.textContent = message;
    triggerWarning.hidden = !message;
  };

  const renderInternalNote = () => {
    if (!triggerNote) return;
    const summary = state.internalDeadlines;
    if (!summary || !summary.total) { triggerNote.textContent = ''; return; }
    const kinds = Object.keys(summary.by_event_type || {}).join(', ');
    triggerNote.textContent =
      `Plus ${summary.total.toLocaleString()} maintenance deadlines Ora arms `
      + `for itself${kinds ? ' (' + kinds + ')' : ''}.`;
  };

  const buildTriggerCard = (t) => {
    const spec = t.spec || {};
    const card = document.createElement('div');
    card.className = 'oversight-card trigger-card';
    card.dataset.triggerId = spec.trigger_id;
    card.dataset.status = t.status;

    const name = document.createElement('div');
    name.className = 'oversight-card-name';
    name.textContent = spec.name || spec.trigger_id;
    card.appendChild(name);

    const meta = document.createElement('div');
    meta.className = 'oversight-card-meta';
    const status = document.createElement('span');
    status.className = `badge trigger-status trigger-status--${t.status}`;
    status.textContent = t.status;
    meta.appendChild(status);
    const cause = document.createElement('span');
    cause.className = 'badge';
    cause.textContent = CAUSE_LABEL[spec.cause] || spec.cause;
    meta.appendChild(cause);
    if (t.next_due_at) {
      const due = document.createElement('span');
      due.textContent = `next ${whenOf(t.next_due_at)}`;
      meta.appendChild(due);
    }
    const last = (t.firings || [])[0];
    if (last) {
      const outcome = document.createElement('span');
      outcome.className = `badge trigger-outcome trigger-outcome--${last.outcome || last.status}`;
      outcome.textContent = `last ${last.outcome || last.status}`;
      outcome.title = last.error || '';
      meta.appendChild(outcome);
      const when = document.createElement('span');
      when.textContent = ageOf(last.finished_at || last.claimed_at);
      meta.appendChild(when);
    }
    card.appendChild(meta);

    if (state.triggerExpanded === spec.trigger_id) {
      card.appendChild(buildTriggerDetail(t));
    }

    card.addEventListener('click', (ev) => {
      if (ev.target.closest('.oversight-detail-actions')) return;
      if (ev.target.closest('.trigger-review')) return;
      state.triggerExpanded =
        state.triggerExpanded === spec.trigger_id ? null : spec.trigger_id;
      state.triggerReview = null;
      renderTriggers();
    });
    return card;
  };

  const buildTriggerDetail = (t) => {
    const spec = t.spec || {};
    const det = document.createElement('div');
    det.className = 'oversight-detail';

    const rows = [
      ['Runs', actionSummary(spec)],
      ['Fires', conditionSummary(spec)],
    ];
    if (spec.action && spec.action.kind === 'email_send') {
      const last = (t.firings || [])[0];
      const sent = last && last.receipt && last.receipt.provider_contacted;
      rows.push(['Approval', sent
        ? 'provider contacted; no recall is promised'
        : 'one-shot approval required before provider contact']);
    }
    if (spec.runtime_justification) {
      rows.push(['Why time is the cause', spec.runtime_justification]);
    }
    for (const [label, value] of rows) {
      const row = document.createElement('div');
      row.className = 'oversight-detail-reasoning';
      row.textContent = `${label}: ${value}`;
      det.appendChild(row);
    }
    if (spec.action && spec.action.kind === 'email_send') {
      const inspect = document.createElement('button');
      inspect.type = 'button';
      inspect.textContent = 'Inspect exact message';
      inspect.addEventListener('click', async (ev) => {
        ev.stopPropagation();
        await inspectTrigger(spec.trigger_id);
      });
      det.appendChild(inspect);
      if (state.triggerInspection
          && state.triggerInspection.trigger_id === spec.trigger_id) {
        const pre = document.createElement('pre');
        pre.className = 'trigger-message-inspection';
        pre.textContent = JSON.stringify(state.triggerInspection.message, null, 2);
        det.appendChild(pre);
      }
    }
    if (t.intermittency) {
      const note = document.createElement('div');
      note.className = 'oversight-detail-reasoning trigger-intermittency';
      note.textContent = t.intermittency;
      det.appendChild(note);
    }

    const firings = t.firings || [];
    const history = document.createElement('div');
    history.className = 'oversight-detail-reasoning trigger-history';
    history.textContent = firings.length
      ? `Last firing: ${whenOf(firings[0].finished_at || firings[0].claimed_at)} `
        + `— ${firings[0].outcome || firings[0].status}`
        + (firings[0].error ? ` — ${firings[0].error}` : '')
      : 'Has never fired.';
    det.appendChild(history);

    if (state.triggerReview
        && state.triggerReview.trigger_id === spec.trigger_id) {
      det.appendChild(buildActivationReview(state.triggerReview));
      return det;
    }

    const actions = document.createElement('div');
    actions.className = 'oversight-detail-actions';
    const button = (label, handler, primary) => {
      const b = document.createElement('button');
      b.type = 'button';
      if (primary) b.className = 'primary';
      b.textContent = label;
      b.addEventListener('click', (ev) => { ev.stopPropagation(); handler(b); });
      actions.appendChild(b);
      return b;
    };

    if (t.status !== 'retired') {
      button(spec.action && spec.action.kind === 'email_send'
        ? 'Send exact message' : 'Run now', (b) => runTrigger(spec.trigger_id, b));
    }
    if (t.status === 'draft') {
      button('Review and activate…', () => openReview(spec.trigger_id), true);
    }
    if (t.status === 'active') button('Pause', () => lifecycle(spec.trigger_id, 'pause'));
    if (t.status === 'paused') button('Resume', () => lifecycle(spec.trigger_id, 'resume'));
    if (t.status !== 'retired' && spec.action && spec.action.kind === 'email_send') {
      button('Cancel and retire', () => {
        if (window.confirm(`Cancel unsent email "${spec.name}"?`)) {
          rollbackTrigger(spec.trigger_id);
        }
      });
    } else if (t.status !== 'retired') {
      button('Retire', () => {
        if (window.confirm(`Retire "${spec.name}"? It stops firing and leaves this list.`)) {
          lifecycle(spec.trigger_id, 'retire');
        }
      });
    }
    det.appendChild(actions);
    return det;
  };

  // Activation shows the exact server-derived request and approves its exact
  // digest. Approving a name rather than a specification is what would let an
  // edit slip past the review.
  const buildActivationReview = (review) => {
    const box = document.createElement('div');
    box.className = 'trigger-review';

    const heading = document.createElement('div');
    heading.className = 'trigger-review-heading';
    heading.textContent = 'Approve exactly this before it is deployed';
    box.appendChild(heading);

    const binding = review.action_binding || {};
    const bindingDigest = binding.command_digest
      || binding.message_digest
      || binding.mime_digest;
    const lines = [
      `Will run: ${review.will_run}`,
      `Bound identity: ${bindingDigest}`,
      `Specification: ${review.spec_digest}`,
    ];
    if (review.runtime_justification) {
      lines.push(`Why time is the cause: ${review.runtime_justification}`);
    }
    if (review.intermittency) lines.push(review.intermittency);
    for (const line of lines) {
      const row = document.createElement('div');
      row.className = 'trigger-review-line';
      row.textContent = line;
      box.appendChild(row);
    }

    const actions = document.createElement('div');
    actions.className = 'oversight-detail-actions';
    const approve = document.createElement('button');
    approve.type = 'button';
    approve.className = 'primary';
    approve.textContent = 'Approve and activate';
    approve.addEventListener('click', async (ev) => {
      ev.stopPropagation();
      approve.disabled = true;
      await postTrigger(
        `/api/triggers/${encodeURIComponent(review.trigger_id)}/activate`,
        { spec_digest: review.spec_digest }, approve);
      state.triggerReview = null;
      await fetchTriggers();
    });
    actions.appendChild(approve);
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.textContent = 'Cancel';
    cancel.addEventListener('click', (ev) => {
      ev.stopPropagation();
      state.triggerReview = null;
      renderTriggers();
    });
    actions.appendChild(cancel);
    box.appendChild(actions);
    return box;
  };

  const openReview = async (triggerId) => {
    try {
      const r = await fetch(`/api/triggers/${encodeURIComponent(triggerId)}/review`);
      const data = await r.json();
      if (!r.ok) { window.alert(data.error || 'Could not read the Trigger.'); return; }
      state.triggerReview = data;
      renderTriggers();
    } catch (e) {
      window.alert('Could not read the Trigger.');
    }
  };

  const inspectTrigger = async (triggerId) => {
    try {
      const r = await fetch(`/api/triggers/${encodeURIComponent(triggerId)}/inspect`);
      const data = await r.json();
      if (!r.ok) { window.alert(data.error || 'Could not inspect the message.'); return; }
      state.triggerInspection = { trigger_id: triggerId, message: data };
      renderTriggers();
    } catch (e) { window.alert('Could not inspect the message.'); }
  };

  const rollbackTrigger = async (triggerId) => {
    await postTrigger(
      `/api/triggers/${encodeURIComponent(triggerId)}/rollback`, {}, null);
    state.triggerInspection = null;
    await fetchTriggers();
  };

  const postTrigger = async (url, body, button) => {
    const original = button ? button.textContent : '';
    try {
      const r = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {}),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        if (button) {
          button.textContent = 'Refused';
          button.disabled = false;
          window.setTimeout(() => { button.textContent = original; }, 2500);
        }
        window.alert(data.error || 'The request was refused.');
        return null;
      }
      return data;
    } catch (e) {
      if (button) { button.textContent = original; button.disabled = false; }
      return null;
    }
  };

  const lifecycle = async (triggerId, action) => {
    await postTrigger(
      `/api/triggers/${encodeURIComponent(triggerId)}/lifecycle`, { action });
    await fetchTriggers();
  };

  const runTrigger = async (triggerId, button) => {
    const original = button.textContent;
    button.disabled = true;
    button.textContent = 'Starting…';
    const result = await postTrigger(
      `/api/triggers/${encodeURIComponent(triggerId)}/run`, {}, button);
    button.disabled = false;
    button.textContent = result && result.duplicate ? 'Already running' : original;
    await fetchTriggers();
  };

  // ── The authoring form ────────────────────────────────────────────────

  const loadActions = async () => {
    if (state.actions) return state.actions;
    try {
      const r = await fetch('/api/triggers/actions');
      state.actions = r.ok ? await r.json() : {
        project_tools: [], frameworks: [], channel_actions: [],
      };
    } catch (e) {
      state.actions = { project_tools: [], frameworks: [], channel_actions: [] };
    }
    return state.actions;
  };

  const openTriggerForm = async () => {
    const actions = await loadActions();
    const existing = document.getElementById('triggerFormOverlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.className = 'trigger-form-overlay';
    overlay.id = 'triggerFormOverlay';
    const form = document.createElement('form');
    form.className = 'trigger-form';
    overlay.appendChild(form);

    const field = (labelText, control, hint) => {
      const wrap = document.createElement('label');
      wrap.className = 'trigger-form-field';
      const span = document.createElement('span');
      span.textContent = labelText;
      wrap.appendChild(span);
      wrap.appendChild(control);
      if (hint) {
        const small = document.createElement('small');
        small.textContent = hint;
        wrap.appendChild(small);
      }
      form.appendChild(wrap);
      return wrap;
    };
    const input = (name, placeholder) => {
      const el = document.createElement('input');
      el.type = 'text';
      el.name = name;
      if (placeholder) el.placeholder = placeholder;
      return el;
    };
    const select = (name, options) => {
      const el = document.createElement('select');
      el.name = name;
      for (const [value, label] of options) {
        const opt = document.createElement('option');
        opt.value = value;
        opt.textContent = label;
        el.appendChild(opt);
      }
      return el;
    };

    const title = document.createElement('div');
    title.className = 'trigger-form-title';
    title.textContent = 'New Trigger';
    form.appendChild(title);

    const nameInput = input('name', 'Nightly export');
    field('Name', nameInput);
    const idInput = input('trigger_id', 'nightly-export');
    field('Identifier', idInput, 'Lowercase letters, digits, and - _ . :');

    const toolOptions = actions.project_tools.map(t => [
      `tool:${t.nexus}:${t.tool}`,
      `${t.nexus}:${t.tool}${t.description ? ' — ' + t.description : ''}`,
    ]);
    const frameworkOptions = actions.frameworks.map(f => [`framework:${f}`, f]);
    const channelOptions = (actions.channel_actions || []).map(a => [
      `channel:${a.kind}`, `${a.provider || 'channel'}: ${a.description || a.kind}`,
    ]);
    const actionSelect = select('action',
      toolOptions.concat(frameworkOptions, channelOptions));
    field('Runs', actionSelect,
          toolOptions.length ? '' :
          'No project tools are registered. Declare the script in an '
          + 'ora-project.json manifest, then register it with /project-register.');

    const argsInput = input('args', 'optional arguments or framework input');
    field('Input', argsInput);

    const emailToInput = input('email_to', 'recipient@example.com, other@example.com');
    const emailToField = field('To', emailToInput,
      'Bare addresses only; separate multiple recipients with commas.');
    const emailFromInput = input('email_from', 'sender@example.com');
    const emailFromField = field('From', emailFromInput,
      'The exact Fastmail identity used for this message.');
    const emailSubjectInput = input('email_subject', 'Subject');
    const emailSubjectField = field('Subject', emailSubjectInput);
    const emailBodyInput = document.createElement('textarea');
    emailBodyInput.name = 'email_body';
    emailBodyInput.rows = 7;
    emailBodyInput.placeholder = 'Write the exact message body.';
    const emailBodyField = field('Message', emailBodyInput,
      'Ora adds the Persona disclosure before this exact body.');
    const emailPersonaInput = input('email_persona', 'ora');
    const emailPersonaField = field('Persona', emailPersonaInput,
      'Visible sender/disclosure identity; defaults to Ora.');

    const causeSelect = select('cause', [
      ['manual', 'Only when I run it'],
      ['calendar', 'On a schedule'],
      ['file_change', 'When a watched file changes'],
      ['trigger_completion', 'After another Trigger succeeds'],
    ]);
    field('Fires', causeSelect);

    const timeInput = input('local_time', '07:30');
    const timeField = field('Local time', timeInput);
    const cadenceSelect = select('cadence', [['daily', 'Every day'], ['weekly', 'Chosen weekdays']]);
    const cadenceField = field('Cadence', cadenceSelect);
    const weekdaysInput = input('weekdays', 'mon,thu');
    const weekdaysField = field('Weekdays', weekdaysInput);
    const tzInput = input('timezone', 'America/New_York');
    const tzField = field('Timezone', tzInput, 'A named IANA zone, so DST is handled.');
    const missedSelect = select('missed_policy', [
      ['run_once', 'Run once when Ora comes back'],
      ['skip', 'Skip the missed window'],
    ]);
    const missedField = field('If Ora was not running', missedSelect);
    const becauseInput = document.createElement('textarea');
    becauseInput.name = 'runtime_justification';
    becauseInput.rows = 3;
    becauseInput.placeholder =
      'Why can no runtime event represent this cause? If one can, use it instead.';
    const becauseField = field('Why time is the cause', becauseInput,
                               'Required before a scheduled Trigger can be activated.');

    const pathInput = input('path_selectors', '');
    const pathField = field('Watched path', pathInput,
      `Must be inside: ${(actions.watch_roots || []).join(' · ') || '(no watched root)'}`);

    const sourceSelect = select('source_trigger_id',
      state.triggers.map(t => [t.spec.trigger_id, t.spec.name || t.spec.trigger_id]));
    const sourceField = field('After this Trigger', sourceSelect);

    const calendarFields = [timeField, cadenceField, weekdaysField, tzField,
                            missedField, becauseField];
    const emailFields = [emailToField, emailFromField, emailSubjectField,
      emailBodyField, emailPersonaField];
    const syncCause = () => {
      const cause = causeSelect.value;
      const email = actionSelect.value.startsWith('channel:email_send');
      for (const el of emailFields) el.hidden = !email;
      causeSelect.disabled = email;
      if (email) causeSelect.value = 'manual';
      for (const el of calendarFields) el.hidden = email || cause !== 'calendar';
      weekdaysField.hidden = email || cause !== 'calendar'
        || cadenceSelect.value !== 'weekly';
      pathField.hidden = email || cause !== 'file_change';
      sourceField.hidden = email || cause !== 'trigger_completion';
    };
    actionSelect.addEventListener('change', syncCause);
    causeSelect.addEventListener('change', syncCause);
    cadenceSelect.addEventListener('change', syncCause);
    syncCause();

    const note = document.createElement('div');
    note.className = 'trigger-form-note';
    note.textContent = actions.intermittency || '';
    form.appendChild(note);

    const errorBox = document.createElement('div');
    errorBox.className = 'trigger-form-error';
    errorBox.hidden = true;
    form.appendChild(errorBox);

    const buttons = document.createElement('div');
    buttons.className = 'trigger-form-actions';
    const submit = document.createElement('button');
    submit.type = 'submit';
    submit.className = 'primary';
    submit.textContent = 'Create as draft';
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.textContent = 'Cancel';
    cancel.addEventListener('click', () => overlay.remove());
    buttons.appendChild(submit);
    buttons.appendChild(cancel);
    form.appendChild(buttons);

    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      errorBox.hidden = true;
      submit.disabled = true;
      try {
        const r = await fetch('/api/triggers', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(buildSpecFromForm({
            nameInput, idInput, actionSelect, argsInput, causeSelect,
            timeInput, cadenceSelect, weekdaysInput, tzInput, missedSelect,
            becauseInput, pathInput, sourceSelect,
            emailToInput, emailFromInput, emailSubjectInput, emailBodyInput,
            emailPersonaInput,
          })),
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) {
          errorBox.textContent = data.error || 'The Trigger was refused.';
          errorBox.hidden = false;
          submit.disabled = false;
          return;
        }
        overlay.remove();
        state.triggerExpanded = data.spec && data.spec.trigger_id;
        await fetchTriggers();
      } catch (e) {
        errorBox.textContent = 'Could not reach Ora.';
        errorBox.hidden = false;
        submit.disabled = false;
      }
    });

    overlay.addEventListener('click', (ev) => {
      if (ev.target === overlay) overlay.remove();
    });
    document.body.appendChild(overlay);
    nameInput.focus();
  };

  const WEEKDAY_INDEX = { mon: 0, tue: 1, wed: 2, thu: 3, fri: 4, sat: 5, sun: 6 };

  const buildSpecFromForm = (f) => {
    const [kind, ...rest] = f.actionSelect.value.split(':');
    const action = kind === 'channel' && rest.join(':') === 'email_send'
      ? { kind: 'email_send',
          to: f.emailToInput.value.split(',').map(value => value.trim()).filter(Boolean),
          from_email: f.emailFromInput.value.trim(),
          subject: f.emailSubjectInput.value,
          body: f.emailBodyInput.value,
          persona_id: f.emailPersonaInput.value.trim() || 'ora' }
      : kind === 'tool'
      ? { kind: 'project_tool', nexus: rest[0], tool: rest[1],
          args: f.argsInput.value.trim() ? f.argsInput.value.trim().split(/\s+/) : [] }
      : { kind: 'framework', framework: rest.join(':'),
          input: f.argsInput.value.trim() };

    const spec = {
      trigger_id: f.idInput.value.trim(),
      name: f.nameInput.value.trim(),
      cause: f.causeSelect.value,
      action,
      condition: {},
    };
    if (spec.cause === 'calendar') {
      const weekdays = f.cadenceSelect.value === 'weekly'
        ? f.weekdaysInput.value.split(',')
            .map(s => WEEKDAY_INDEX[s.trim().toLowerCase().slice(0, 3)])
            .filter(n => Number.isInteger(n))
        : [];
      spec.condition = { schedule: {
        timezone: f.tzInput.value.trim(),
        local_time: f.timeInput.value.trim(),
        cadence: f.cadenceSelect.value,
        weekdays,
        start_date: new Date().toISOString().slice(0, 10),
        missed_policy: f.missedSelect.value,
        grace_seconds: 300,
      } };
      spec.runtime_justification = f.becauseInput.value.trim();
    } else if (spec.cause === 'file_change') {
      spec.condition = { path_selectors: [f.pathInput.value.trim()] };
    } else if (spec.cause === 'trigger_completion') {
      spec.condition = { source_trigger_id: f.sourceSelect.value };
    }
    return spec;
  };

  if (triggerNewBtn) {
    triggerNewBtn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      openTriggerForm();
    });
  }

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
