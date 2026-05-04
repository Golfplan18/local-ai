/* V3 Phase 4.1–4.4 — Left sidebar.
 *
 * Two states:
 *   .left-sidebar             → collapsed (icon-width dashboard)
 *   .left-sidebar.expanded    → expanded (full conversation list)
 *
 * Expand triggers:
 *   - Hamburger button on spine (id: spineSidebarToggle)
 *   - Expand icon on the collapsed dashboard (id: sidebarDashExpand)
 *   - "A" character at the bottom of the ORA wordmark (id: logo-a)
 *
 * Data:
 *   GET /api/conversations           list grouped (pinned/errored/pending/unread/active)
 *   GET /api/conversation/<id>       load one conversation
 *   POST /api/conversation/<id>/mark-read
 *   POST /api/conversation/<id>/pin
 *   POST /api/conversation/<id>/close
 *
 * Refresh: poll every 12s while the page is visible. Page-visibility
 * change triggers an immediate refresh on resume.
 */
(() => {
  const sidebar = document.querySelector('.left-sidebar');
  if (!sidebar) return;

  const REFRESH_INTERVAL_MS = 12000;

  const dash         = sidebar.querySelector('.sidebar-collapsed-dashboard');
  const expandIcon   = sidebar.querySelector('#sidebarDashExpand');
  const newChatIcon  = sidebar.querySelector('#sidebarDashNewChat');
  const dashUnread   = sidebar.querySelector('#sidebarDashUnread');
  const dashActive   = sidebar.querySelector('#sidebarDashActive');
  const dashPending  = sidebar.querySelector('#sidebarDashPending');

  const newThreadCmd = sidebar.querySelector('.sidebar-new-thread-cmd');
  const groupPinned  = sidebar.querySelector('[data-group="pinned"]  .sidebar-group-rows');
  const groupPinnedShell = sidebar.querySelector('[data-group="pinned"]');
  const groupErrored = sidebar.querySelector('[data-group="errored"] .sidebar-group-rows');
  const groupErroredShell = sidebar.querySelector('[data-group="errored"]');
  const groupUnread  = sidebar.querySelector('[data-group="unread"]  .sidebar-group-rows');
  const groupActive  = sidebar.querySelector('[data-group="active"]  .sidebar-group-rows');
  const groupPending = sidebar.querySelector('[data-group="pending"] .sidebar-group-rows');

  let lastSnapshot = { pinned: [], errored: [], pending: [], unread: [], active: [] };
  let activeConvId = null;

  const setExpanded = (on) => {
    sidebar.classList.toggle('expanded', !!on);
    document.body.classList.toggle('sidebar-expanded', !!on);
  };

  const isExpanded = () => sidebar.classList.contains('expanded');

  // Backlog 3E — pin-in-place toggle. When pinned, the sidebar stays
  // open: outside clicks, Esc, and row-click navigation no longer
  // dismiss it. When not pinned (the default), any of those actions
  // collapses the sidebar back to the icon-width dashboard.
  const PIN_KEY = 'ora-sidebar-pinned';
  const isPinned = () => document.body.classList.contains('sidebar-pinned');
  const setPinned = (on) => {
    document.body.classList.toggle('sidebar-pinned', !!on);
    if (sidebarPinBtn) {
      sidebarPinBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
      sidebarPinBtn.title = on ? 'Unpin sidebar' : 'Pin sidebar open';
    }
    try {
      if (on) localStorage.setItem(PIN_KEY, '1');
      else    localStorage.removeItem(PIN_KEY);
    } catch (e) {}
  };
  const togglePin = () => setPinned(!isPinned());
  let sidebarPinBtn = null;

  const render = (data) => {
    lastSnapshot = data || { pinned: [], pending: [], unread: [], active: [] };

    // Counts on collapsed dashboard. The pinned group (e.g. WELCOME) is
    // always-present orientation content, not a count the user needs to
    // monitor, so it is excluded from the dashboard numbers.
    if (dashUnread)  dashUnread.textContent  = String((data.unread  || []).length);
    if (dashActive)  dashActive.textContent  = String((data.active || []).length);
    if (dashPending) {
      const n = (data.pending || []).length;
      dashPending.textContent = String(n);
      dashPending.dataset.count = String(n);
    }
    if (dashUnread)  dashUnread.dataset.count  = String((data.unread  || []).length);
    if (dashActive)  dashActive.dataset.count  = String((data.active || []).length);

    // V3 Backlog 7 — A glyph "attract" state. While the sidebar is
    // collapsed, pulse the A subtly if there's something the user
    // might want to look at (any unread, errored, or pending). The
    // CSS gates the animation on body:not(.sidebar-expanded) so the
    // pulse only fires when the affordance actually matters.
    const logoA = document.getElementById('logo-a');
    if (logoA) {
      const hasAttention = (data.unread  || []).length > 0
                        || (data.errored || []).length > 0
                        || (data.pending || []).length > 0;
      if (hasAttention) logoA.classList.add('wordmark-attract');
      else              logoA.classList.remove('wordmark-attract');
    }

    // Expanded group lists. Hide the pinned / errored groups entirely
    // when empty so their section headers don't show as orphans.
    const pinnedRows  = data.pinned  || [];
    const erroredRows = data.errored || [];
    if (groupPinnedShell) {
      groupPinnedShell.style.display = pinnedRows.length ? '' : 'none';
    }
    if (groupErroredShell) {
      groupErroredShell.style.display = erroredRows.length ? '' : 'none';
    }
    renderGroup(groupPinned,  pinnedRows);
    renderGroup(groupErrored, erroredRows);
    renderGroup(groupUnread,  data.unread  || []);
    renderGroup(groupActive,  data.active  || []);
    renderGroup(groupPending, data.pending || []);
  };

  const renderGroup = (container, rows) => {
    if (!container) return;
    container.innerHTML = '';
    if (rows.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'sidebar-group-empty';
      empty.textContent = '—';
      container.appendChild(empty);
      return;
    }
    for (const row of rows) {
      container.appendChild(buildRow(row));
    }
  };

  const buildRow = (row) => {
    const el = document.createElement('div');
    el.className = 'sidebar-row';
    el.dataset.conversationId = row.conversation_id;
    el.dataset.tag = row.tag || '';
    el.dataset.pending = row.pending ? 'true' : 'false';
    if (row.conversation_id === activeConvId) el.classList.add('is-active');
    // V3 Backlog 3C — make rows keyboard-navigable. Pending rows aren't
    // actionable, so they're tabindex="-1" and skipped by ArrowUp /
    // ArrowDown. role="button" exposes the click semantic to assistive
    // tech without making the row an actual <button> (the row contains
    // buttons of its own — close, retry, dismiss, pin — which aren't
    // valid as nested children of a button).
    el.setAttribute('role', 'button');
    el.tabIndex = row.pending ? -1 : 0;

    const prefix = document.createElement('span');
    prefix.className = 'sidebar-row-prefix';
    prefix.textContent = prefixForTag(row.tag);
    el.appendChild(prefix);

    // Action buttons (X / pin, or Retry / Dismiss for errored rows) live on
    // the LEFT side of the row, between the mode prefix and the title, so
    // the title can have unconstrained width to show on hover.
    if (row.last_status === 'errored') {
      el.classList.add('is-errored');
      const actions = document.createElement('div');
      actions.className = 'sidebar-row-actions';
      const retryBtn = document.createElement('button');
      retryBtn.type = 'button';
      retryBtn.className = 'sidebar-row-action sidebar-row-retry';
      retryBtn.textContent = 'Retry';
      retryBtn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        onRetryClick(row);
      });
      actions.appendChild(retryBtn);
      const dismissBtn = document.createElement('button');
      dismissBtn.type = 'button';
      dismissBtn.className = 'sidebar-row-action sidebar-row-dismiss';
      dismissBtn.textContent = 'Dismiss';
      dismissBtn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        onDismissErrorClick(row);
      });
      actions.appendChild(dismissBtn);
      el.appendChild(actions);
    } else {
      // Pin (always visible) + close (visible on hover) — both on the left.
      const close = document.createElement('button');
      close.type = 'button';
      close.className = 'sidebar-row-close';
      close.setAttribute('aria-label', 'Close conversation');
      close.textContent = '×';
      close.addEventListener('click', (ev) => {
        ev.stopPropagation();
        onCloseClick(row);
      });
      el.appendChild(close);
      if (!row.is_welcome) {
        const pin = document.createElement('button');
        pin.type = 'button';
        pin.className = 'sidebar-row-pin';
        pin.setAttribute('aria-label', row.pinned ? 'Unpin conversation' : 'Pin conversation');
        if (row.pinned) pin.classList.add('is-pinned');
        pin.textContent = row.pinned ? '\u{1F4CC}' : '\u{1F4CD}';
        pin.addEventListener('click', (ev) => {
          ev.stopPropagation();
          onPinClick(row);
        });
        el.appendChild(pin);
      }
    }

    const titleWrap = document.createElement('div');
    titleWrap.className = 'sidebar-row-title';
    titleWrap.textContent = row.title || '(untitled)';
    if (row.last_activity_at) {
      const meta = document.createElement('span');
      meta.className = 'sidebar-row-meta';
      meta.textContent = formatTimestamp(row.last_activity_at);
      titleWrap.appendChild(meta);
    }
    el.appendChild(titleWrap);

    if (row.last_status === 'errored' && row.last_error_summary) {
      const errLine = document.createElement('div');
      errLine.className = 'sidebar-row-error-summary';
      errLine.textContent = row.last_error_summary;
      el.appendChild(errLine);
    }

    // Hover tooltip with the full title, extending past the sidebar's right
    // edge over the output pane. Stored as a data attribute and rendered by
    // a single shared overlay element (set up in attachHoverTooltip below)
    // so we don't pile per-row DOM nodes.
    el.dataset.fullTitle = row.title || '(untitled)';
    attachHoverTooltip(el);

    el.addEventListener('click', () => onRowClick(row));
    return el;
  };

  // Shared hover-tooltip overlay. Lives once on the body and is positioned
  // per-row on mouseenter, hidden on mouseleave. Position: fixed so it can
  // escape the sidebar's overflow:hidden and visually extend over the
  // output pane to the right.
  const ensureTooltipNode = () => {
    let n = document.getElementById('ora-sidebar-row-tooltip');
    if (n) return n;
    n = document.createElement('div');
    n.id = 'ora-sidebar-row-tooltip';
    n.className = 'sidebar-row-tooltip';
    n.style.display = 'none';
    document.body.appendChild(n);
    return n;
  };
  const attachHoverTooltip = (rowEl) => {
    rowEl.addEventListener('mouseenter', () => {
      const t = ensureTooltipNode();
      t.textContent = rowEl.dataset.fullTitle || '';
      const rect = rowEl.getBoundingClientRect();
      const sidebar = document.querySelector('.left-sidebar');
      const sidebarRight = sidebar
        ? sidebar.getBoundingClientRect().right
        : rect.right;
      // Place tooltip just past the sidebar's right edge, vertically aligned
      // to the row.
      t.style.left = (sidebarRight + 8) + 'px';
      t.style.top  = rect.top + 'px';
      t.style.display = 'block';
    });
    rowEl.addEventListener('mouseleave', () => {
      const t = document.getElementById('ora-sidebar-row-tooltip');
      if (t) t.style.display = 'none';
    });
  };

  const onPinClick = async (row) => {
    const next = !row.pinned;
    try {
      await fetch(`/api/conversation/${encodeURIComponent(row.conversation_id)}/pin`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pinned: next }),
      });
    } catch (e) {}
    fetchList();
  };

  const prefixForTag = (tag) => {
    if (tag === 'stealth') return '⊘';
    if (tag === 'private') return '◎';
    return '';
  };

  const formatTimestamp = (iso) => {
    try {
      const d = new Date(iso);
      const now = new Date();
      const sameDay = d.toDateString() === now.toDateString();
      if (sameDay) {
        return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
      }
      return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    } catch (e) {
      return '';
    }
  };

  const fetchList = async () => {
    try {
      const r = await fetch('/api/conversations');
      if (!r.ok) return;
      const data = await r.json();
      render(data);
    } catch (e) {
      // Network failure during polling — render the last snapshot we had.
    }
  };

  const onRowClick = async (row) => {
    activeConvId = row.conversation_id;
    [...sidebar.querySelectorAll('.sidebar-row')].forEach(el => {
      el.classList.toggle('is-active', el.dataset.conversationId === activeConvId);
    });
    // Mark as read (best-effort) and emit a custom event so the output
    // pane can swap to this conversation. Output-pane integration is
    // Phase 4 / Phase 5 territory; the event is a hook for that wiring.
    try {
      await fetch(`/api/conversation/${encodeURIComponent(row.conversation_id)}/mark-read`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
    } catch (e) {}
    document.dispatchEvent(new CustomEvent('ora:conversation-selected', {
      detail: { conversation_id: row.conversation_id, tag: row.tag, title: row.title },
    }));
    // Refresh the list so the unread → active migration shows up.
    fetchList();
    // Backlog 3E — temporary mode collapses on row selection; pinned
    // mode keeps the sidebar open so the user can scan multiple rows.
    if (!isPinned()) setExpanded(false);
  };

  const onCloseClick = async (row) => {
    // Backlog 11 — unsent-input close confirmation. If there's a saved
    // draft for this conversation, confirm before close so we don't
    // silently lose the user's in-progress text.
    let hasDraft = false;
    try {
      hasDraft = !!localStorage.getItem('ora-v3-draft-' + row.conversation_id);
    } catch (e) {}
    if (hasDraft) {
      if (!confirm('This conversation has an unsent message in the input area. Close anyway?')) return;
      try { localStorage.removeItem('ora-v3-draft-' + row.conversation_id); } catch (e) {}
    }
    if (row.tag === 'stealth') {
      if (!confirm('This stealth conversation will be permanently deleted. This cannot be undone. Confirm?')) return;
    }
    try {
      await fetch(`/api/conversation/${encodeURIComponent(row.conversation_id)}/close`, {
        method: 'POST',
      });
    } catch (e) {}
    if (row.conversation_id === activeConvId) activeConvId = null;
    fetchList();
  };

  // Backlog 11 — retry an errored conversation. Server returns the
  // last user prompt; we re-submit it through /chat/multipart with the
  // conversation's id and tag, mirroring what the original submit
  // would have looked like. The errored flag is cleared on success.
  const onRetryClick = async (row) => {
    let prompt = '';
    let tag = row.tag || '';
    try {
      const r = await fetch(`/api/conversation/${encodeURIComponent(row.conversation_id)}/retry`, { method: 'POST' });
      if (!r.ok) {
        alert('Retry could not be staged: HTTP ' + r.status);
        return;
      }
      const data = await r.json();
      prompt = data.last_user_prompt || '';
      tag = data.tag || tag;
    } catch (e) {
      alert('Retry failed: ' + (e.message || e));
      return;
    }
    if (!prompt) {
      alert('Nothing to retry — no user prompt found in this conversation.');
      return;
    }
    // Re-submit through /chat/multipart. We don't await SSE here;
    // we just fire and refresh the list when done.
    const body = new FormData();
    body.append('message', prompt);
    body.append('conversation_id', row.conversation_id);
    body.append('panel_id',        row.conversation_id);
    body.append('is_main_feed',    'true');
    body.append('tag',             tag);
    try {
      const resp = await fetch('/chat/multipart', { method: 'POST', body });
      if (resp.ok) {
        // Drain the SSE so the connection closes cleanly. We don't
        // surface the response into the output pane here — the user
        // can click the row to view it.
        if (resp.body && resp.body.getReader) {
          const reader = resp.body.getReader();
          while (true) {
            const { done } = await reader.read();
            if (done) break;
          }
        }
        // Clear the errored flag now that the resubmit completed.
        try {
          await fetch(`/api/conversation/${encodeURIComponent(row.conversation_id)}/dismiss-error`, { method: 'POST' });
        } catch (e) {}
      }
    } catch (e) {
      // Leave the errored flag set; user can retry again.
    }
    fetchList();
  };

  const onDismissErrorClick = async (row) => {
    try {
      await fetch(`/api/conversation/${encodeURIComponent(row.conversation_id)}/dismiss-error`, { method: 'POST' });
    } catch (e) {}
    fetchList();
  };

  const onNewThread = () => {
    // Phase 6 wires this through to /api/bootstrap. For now it just emits
    // a custom event so the input area or a bootstrap modal can hook in.
    document.dispatchEvent(new CustomEvent('ora:new-thread-requested'));
  };

  // ── Wire-up ─────────────────────────────────────────────────────────
  if (expandIcon)  expandIcon.addEventListener('click',  () => setExpanded(true));
  if (newChatIcon) newChatIcon.addEventListener('click', onNewThread);
  if (newThreadCmd) newThreadCmd.addEventListener('click', onNewThread);

  // Backlog 3E — pin-in-place button at the top of the expanded panel.
  sidebarPinBtn = sidebar.querySelector('#sidebarPinToggle');
  if (sidebarPinBtn) {
    sidebarPinBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      togglePin();
    });
  }
  // Restore last session's pin state.
  try {
    if (localStorage.getItem(PIN_KEY) === '1') setPinned(true);
    else                                       setPinned(false);
  } catch (e) { setPinned(false); }

  const hamburger = document.getElementById('spineSidebarToggle');
  if (hamburger) hamburger.addEventListener('click', () => setExpanded(!isExpanded()));

  const logoA = document.getElementById('logo-a');
  if (logoA) {
    logoA.addEventListener('click', (e) => {
      // Prevent the existing "output menu" handler from firing alongside us.
      e.stopPropagation();
      // Per spec 3E: clicking the A while pinned does nothing (sidebar
      // is already open). Otherwise expand.
      if (isPinned() && isExpanded()) return;
      setExpanded(true);
    });
  }

  // Plus on spine — duplicate entry point for new thread (Phase 6 hook).
  const plusBtn = document.getElementById('spineNewThread');
  if (plusBtn) plusBtn.addEventListener('click', onNewThread);

  // Backlog 3E — temporary-mode dismissal: outside-click and Esc collapse
  // the sidebar when not pinned. Clicks inside the sidebar are ignored.
  document.addEventListener('click', (e) => {
    if (!isExpanded() || isPinned()) return;
    if (sidebar.contains(e.target)) return;
    // Don't dismiss when clicking the spine controls that drive the
    // sidebar (toggle, A glyph) — those have their own handlers.
    if (e.target.closest('#spineSidebarToggle, #logo-a')) return;
    setExpanded(false);
  });
  document.addEventListener('keydown', (e) => {
    const cmd = e.metaKey || e.ctrlKey;
    const k   = e.key.toLowerCase();

    // Cmd+K / Ctrl+K — open the conversation sidebar.
    // See Reference — Ora Keyboard Shortcuts (vault).
    if (cmd && k === 'k' && !e.shiftKey && !e.altKey) {
      e.preventDefault();
      setExpanded(true);
      return;
    }
    // Cmd+J / Ctrl+J — start a new conversation.
    if (cmd && k === 'j' && !e.shiftKey && !e.altKey) {
      e.preventDefault();
      onNewThread();
      return;
    }

    // V3 Backlog 3C — sidebar row navigation. Only fires while the
    // sidebar is expanded. ArrowUp / ArrowDown walk through focusable
    // rows (pending rows have tabindex="-1" and are skipped). Enter
    // activates the focused row; Backspace / Delete invokes the row's
    // close / dismiss affordance.
    if (isExpanded()) {
      const rows = sidebar.querySelectorAll('.sidebar-row[tabindex="0"]');
      if (rows.length > 0) {
        const focusedRow = (document.activeElement && document.activeElement.closest)
          ? document.activeElement.closest('.sidebar-row[tabindex="0"]')
          : null;
        const idx = focusedRow ? Array.prototype.indexOf.call(rows, focusedRow) : -1;

        if (e.key === 'ArrowDown') {
          e.preventDefault();
          const next = idx < 0 ? 0 : (idx + 1) % rows.length;
          rows[next].focus();
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          const prev = idx <= 0 ? rows.length - 1 : idx - 1;
          rows[prev].focus();
          return;
        }
        if (focusedRow) {
          if (e.key === 'Enter') {
            e.preventDefault();
            focusedRow.click();
            return;
          }
          if (e.key === 'Backspace' || e.key === 'Delete') {
            e.preventDefault();
            const closeBtn = focusedRow.querySelector(
              '.sidebar-row-close, .sidebar-row-dismiss'
            );
            if (closeBtn) closeBtn.click();
            return;
          }
        }
      }
    }

    // Esc — dismiss the sidebar (when expanded and not pinned).
    if (e.key !== 'Escape') return;
    if (!isExpanded() || isPinned()) return;
    setExpanded(false);
  });

  // ── Polling ─────────────────────────────────────────────────────────
  fetchList();
  let pollHandle = window.setInterval(fetchList, REFRESH_INTERVAL_MS);

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      fetchList();
      if (!pollHandle) {
        pollHandle = window.setInterval(fetchList, REFRESH_INTERVAL_MS);
      }
    } else {
      if (pollHandle) {
        window.clearInterval(pollHandle);
        pollHandle = null;
      }
    }
  });

  // Expose minimal API for other modules + DevTools.
  window.OraSidebar = {
    refresh: fetchList,
    setExpanded,
    isExpanded,
    getActiveConversation: () => activeConvId,
  };
})();
