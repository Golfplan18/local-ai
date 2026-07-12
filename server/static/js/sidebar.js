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
 *   POST /api/conversation/<id>/delete-forever
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
  const forkThreadCmd = sidebar.querySelector('.sidebar-fork-thread-cmd');
  const browseCmd    = sidebar.querySelector('.sidebar-browse-cmd');
  const groupPinned  = sidebar.querySelector('[data-group="pinned"]  .sidebar-group-rows');
  const groupPinnedShell = sidebar.querySelector('[data-group="pinned"]');
  const groupErrored = sidebar.querySelector('[data-group="errored"] .sidebar-group-rows');
  const groupErroredShell = sidebar.querySelector('[data-group="errored"]');
  const groupUnread  = sidebar.querySelector('[data-group="unread"]  .sidebar-group-rows');
  const groupActive  = sidebar.querySelector('[data-group="active"]  .sidebar-group-rows');
  const groupPending = sidebar.querySelector('[data-group="pending"] .sidebar-group-rows');

  // G1.33 — project switcher (top of sidebar).
  const projectSwitcher = sidebar.querySelector('#sidebarProjectSwitcher');
  const projectBtn      = sidebar.querySelector('#sidebarProjectBtn');
  const projectNameEl   = sidebar.querySelector('#sidebarProjectName');
  const projectMenu     = sidebar.querySelector('#sidebarProjectMenu');
  const projectSearch   = sidebar.querySelector('#sidebarProjectSearch');
  const projectListEl   = sidebar.querySelector('#sidebarProjectList');
  const projectNewBtn   = sidebar.querySelector('#sidebarProjectNew');
  const projectManageBtn  = sidebar.querySelector('#sidebarProjectManage');
  const projectManageItem = sidebar.querySelector('#sidebarProjectManageItem');
  const modelConfigBtn  = sidebar.querySelector('#sidebarModelConfigBtn');
  const modelConfigName = sidebar.querySelector('#sidebarModelConfigName');
  const outputStyleBtn  = sidebar.querySelector('#sidebarOutputStyleBtn');
  const outputStyleName = sidebar.querySelector('#sidebarOutputStyleName');

  const ACTIVE_PROJECT_KEY = 'ora-sidebar-project';
  const canonicalProjectId = (nexus) => {
    const slug = String(nexus || '').trim();
    return (!slug || ['commons', 'general'].includes(slug.toLowerCase())) ? 'commons' : slug;
  };
  const canonicalProjectRecordId = (project) =>
    canonicalProjectId(project && (project.canonical_nexus || project.nexus));
  const compatibleProjectId = (nexus) =>
    canonicalProjectId(nexus) === 'commons' ? '' : canonicalProjectId(nexus);
  // "general" was the pre-2026-07-11 id. Canonicalize and lazily heal a
  // browser that stored it before the rename.
  let activeProjectId = 'commons';
  try {
    const storedProjectId = localStorage.getItem(ACTIVE_PROJECT_KEY);
    activeProjectId = canonicalProjectId(storedProjectId);
    const compatibleStoredId = compatibleProjectId(activeProjectId);
    if (storedProjectId !== compatibleStoredId) {
      localStorage.setItem(ACTIVE_PROJECT_KEY, compatibleStoredId);
    }
  } catch (e) {}
  let projectsCache = [];
  let activeProjectSyncGeneration = 0;
  let activeProjectMutationInFlight = false;
  let pendingActiveProjectSelection = null;
  let activeProjectSelectionSequence = 0;

  let lastSnapshot = { pinned: [], errored: [], pending: [], unread: [], active: [] };
  let activeConvId = null;
  let browserOverlay = null;
  let browserSearch = null;
  let browserSort = null;
  let browserRows = null;
  let browserStatus = null;
  let browserConversationsToggle = null;
  let browserEngramsToggle = null;
  let browserTagsInput = null;
  let browserShowArchivedToggle = null;
  let browserRelevanceSlider = null;
  let browserRelevanceValue = null;
  let browserResizeObserver = null;
  let browserDismissedIds = new Set();
  let browserRowsCache = [];
  let browserLastData = null;
  let browserIncludeConversations = true;
  let browserIncludeEngrams = true;
  let browserTags = '';
  let browserShowArchived = false;
  let browserMinRelevance = 0;
  let browserFetchTimer = null;
  let browserFilterTimer = null;
  let browserReturnFocus = null;
  const lifecycleBusyIds = new Set();

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

    // The shared hover tooltip is anchored to a row; if that row is
    // removed by a re-render while the cursor is over it, mouseleave
    // never fires and the tooltip lingers. Dismiss it on every render
    // so it can't outlive its anchor.
    const tip = document.getElementById('ora-sidebar-row-tooltip');
    if (tip) tip.style.display = 'none';
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
      const closeLabel = row.tag === 'stealth' ? 'Delete Dialogue forever' : 'Close Dialogue';
      close.setAttribute('aria-label', closeLabel);
      close.title = closeLabel;
      close.textContent = '×';
      close.disabled = lifecycleBusyIds.has(row.conversation_id);
      close.setAttribute('aria-disabled', close.disabled ? 'true' : 'false');
      close.addEventListener('click', (ev) => {
        ev.stopPropagation();
        onCloseClick(Object.assign({}, row, { tag: el.dataset.tag || '' }));
      });
      el.appendChild(close);
      if (!row.is_welcome) {
        const pin = document.createElement('button');
        pin.type = 'button';
        pin.className = 'sidebar-row-pin';
        pin.setAttribute('aria-label', row.pinned ? 'Unpin Dialogue' : 'Pin Dialogue');
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
      const r = await fetch('/api/conversations?project_id=' + encodeURIComponent(compatibleProjectId(activeProjectId)));
      if (!r.ok) return;
      const data = await r.json();
      render(data);
    } catch (e) {
      // Network failure during polling — render the last snapshot we had.
    }
  };

  // ── G1.33 project switcher ──────────────────────────────────────────────
  const projectDisplayName = (nexus) =>
    canonicalProjectId(nexus) === 'commons' ? 'Commons' : nexus;

  const renderProjects = () => {
    if (!projectListEl) return;
    const q = ((projectSearch && projectSearch.value) || '').trim().toLowerCase();
    projectListEl.innerHTML = '';
    projectsCache
      .filter(p => !q || String(p.name || p.nexus).toLowerCase().includes(q))
      .forEach(p => {
        const row = document.createElement('button');
        row.type = 'button';
        row.className = 'sidebar-project-row' + (canonicalProjectRecordId(p) === activeProjectId ? ' is-active' : '');
        row.setAttribute('role', 'option');
        const name = document.createElement('span');
        name.className = 'sidebar-project-row-name';
        name.textContent = p.name || p.nexus;
        const badge = document.createElement('span');
        badge.className = 'sidebar-project-badge';
        const unread = p.unread_count || 0;
        badge.textContent = String(unread);
        badge.setAttribute('data-zero', unread ? '0' : '1');
        row.appendChild(name);
        row.appendChild(badge);
        row.addEventListener('click', () => setActiveProject(canonicalProjectRecordId(p), p.name || p.nexus));
        projectListEl.appendChild(row);
      });
  };

  const fetchProjects = async () => {
    try {
      const r = await fetch('/api/projects/meta?status=active');
      if (!r.ok) return;
      const data = await r.json();
      projectsCache = (data && data.projects) || [];
      const cur = projectsCache.find(p => canonicalProjectRecordId(p) === activeProjectId);
      if (projectNameEl) {
        projectNameEl.textContent = cur ? (cur.name || cur.nexus) : projectDisplayName(activeProjectId);
      }
      renderProjects();
    } catch (e) {}
  };

  const persistActiveProjectId = (nexus) => {
    try { localStorage.setItem(ACTIVE_PROJECT_KEY, compatibleProjectId(nexus)); } catch (e) {}
  };

  const reconcileActiveProject = async () => {
    if (activeProjectMutationInFlight) return false;
    const generation = ++activeProjectSyncGeneration;
    try {
      const r = await fetch('/api/active-project');
      if (!r.ok) return false;
      const data = await r.json();
      if (!data || data.ok === false) return false;
      const supplied = (typeof data.canonical_nexus === 'string' && data.canonical_nexus.trim())
        ? data.canonical_nexus
        : data.nexus;
      if (typeof supplied !== 'string') return false;
      if (activeProjectMutationInFlight || generation !== activeProjectSyncGeneration) return false;
      activeProjectId = canonicalProjectId(supplied);
      persistActiveProjectId(activeProjectId);
      const cur = projectsCache.find(p => canonicalProjectRecordId(p) === activeProjectId);
      if (projectNameEl) {
        projectNameEl.textContent = cur ? (cur.name || cur.nexus) : projectDisplayName(activeProjectId);
      }
      renderProjects();
      return true;
    } catch (e) {
      return false;
    }
  };

  const closeProjectMenu = () => {
    if (!projectMenu) return;
    projectMenu.hidden = true;
    if (projectBtn) projectBtn.setAttribute('aria-expanded', 'false');
  };
  const openProjectMenu = () => {
    if (!projectMenu) return;
    projectMenu.hidden = false;
    if (projectBtn) projectBtn.setAttribute('aria-expanded', 'true');
    if (projectSearch) { projectSearch.value = ''; projectSearch.focus(); }
    fetchProjects(); // refresh badges when the user looks
  };
  const toggleProjectMenu = () => {
    if (projectMenu && projectMenu.hidden) openProjectMenu();
    else closeProjectMenu();
  };

  const drainActiveProjectSelections = async () => {
    if (activeProjectMutationInFlight || !pendingActiveProjectSelection) return;
    const selection = pendingActiveProjectSelection;
    pendingActiveProjectSelection = null;
    activeProjectMutationInFlight = true;
    ++activeProjectSyncGeneration; // invalidate any GET that began before this selection
    const requestedId = selection.nexus;
    const compatibleId = compatibleProjectId(requestedId);
    let confirmedId = null;
    let succeeded = false;
    // The server pointer is authoritative for NEW-Dialogue membership. Do not
    // commit browser/UI state until it confirms the write.
    try {
      const r = await fetch('/api/active-project', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nexus: compatibleId }),
      });
      if (!r.ok) throw new Error('active-project write failed');
      const data = await r.json();
      if (!data || data.ok === false) throw new Error('active-project write rejected');
      const supplied = (typeof data.canonical_nexus === 'string' && data.canonical_nexus.trim())
        ? data.canonical_nexus
        : data.nexus;
      if (typeof supplied !== 'string') throw new Error('active-project response missing nexus');
      confirmedId = canonicalProjectId(supplied);
      succeeded = true;
    } catch (e) {
      succeeded = false;
    } finally {
      activeProjectMutationInFlight = false;
    }

    // A later click supersedes this result. The server may briefly hold the
    // earlier value, but the browser must not paint it or lose the last intent;
    // immediately drain the newest queued selection instead.
    const superseded = !!(
      pendingActiveProjectSelection
      && pendingActiveProjectSelection.sequence > selection.sequence
    );
    if (succeeded && !superseded) {
      activeProjectId = confirmedId;
      persistActiveProjectId(activeProjectId);
      if (projectNameEl) {
        projectNameEl.textContent = activeProjectId === requestedId
          ? (selection.name || projectDisplayName(activeProjectId))
          : projectDisplayName(activeProjectId);
      }
      closeProjectMenu();
      fetchList();      // refetch the sidebar filtered to this project
      renderProjects(); // refresh the active highlight
    } else if (!succeeded && !superseded) {
      // A superseded write may already have changed the server before the
      // latest write failed. Re-read authority now so UI/localStorage cannot
      // remain on the pre-queue project until the next poll.
      await reconcileActiveProject();
      await fetchList();
    }
    selection.resolve(succeeded && !superseded);
    if (pendingActiveProjectSelection) drainActiveProjectSelections();
  };

  const setActiveProject = (nexus, name) => {
    const selection = {
      nexus: canonicalProjectId(nexus),
      name,
      sequence: ++activeProjectSelectionSequence,
      resolve: null,
    };
    const promise = new Promise((resolve) => { selection.resolve = resolve; });
    // Only the newest not-yet-started choice matters. Resolve an older queued
    // promise as superseded so callers never hang.
    if (pendingActiveProjectSelection) {
      pendingActiveProjectSelection.resolve(false);
    }
    pendingActiveProjectSelection = selection;
    drainActiveProjectSelections();
    return promise;
  };

  const refreshProjectScopedList = async () => {
    await reconcileActiveProject();
    await fetchList();
  };

  const onRowClick = async (row) => {
    activeConvId = row.conversation_id;
    [...sidebar.querySelectorAll('.sidebar-row')].forEach(el => {
      el.classList.toggle('is-active', el.dataset.conversationId === activeConvId);
    });
    // Select immediately. Mark-read must not delay output state activation:
    // the row's Close/Delete action can otherwise race ahead of load and a
    // late response could reactivate an unavailable Dialogue.
    document.dispatchEvent(new CustomEvent('ora:conversation-selected', {
      detail: { conversation_id: row.conversation_id, tag: row.tag, title: row.title },
    }));
    // Mark as read (best-effort) after selection is in flight.
    try {
      await fetch(`/api/conversation/${encodeURIComponent(row.conversation_id)}/mark-read`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
    } catch (e) {}
    // Refresh the list so the unread → active migration shows up.
    fetchList();
    // Backlog 3E — temporary mode collapses on row selection; pinned
    // mode keeps the sidebar open so the user can scan multiple rows.
    if (!isPinned()) setExpanded(false);
  };

  const onCloseClick = async (row) => {
    // The conversation module owns response/body validation, draft cleanup,
    // destructive confirmation, partial-error surfacing, and active-state
    // reset. Drafts are deliberately not removed until the request succeeds.
    const lifecycle = window.OraConversation;
    const method = row.tag === 'stealth' ? 'deleteForever' : 'closeConversation';
    if (!lifecycle || typeof lifecycle[method] !== 'function') {
      console.error(`[sidebar] ${method} unavailable for ${row.conversation_id}`);
      window.alert('Dialogue lifecycle controls are unavailable.');
      return;
    }
    const result = await lifecycle[method](row.conversation_id, {
      tag: row.tag || '',
      source: 'sidebar-row',
    });
    if (!result || result.ok !== true) return;
    if (row.conversation_id === activeConvId
        && typeof lifecycle.getActiveConversationId === 'function') {
      activeConvId = lifecycle.getActiveConversationId() || null;
    }
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
      alert('Nothing to retry — no user prompt found in this Dialogue.');
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
    document.dispatchEvent(new CustomEvent('ora:new-thread-requested', {
      // Generic New is always Standard. Tagged creation belongs to the
      // explicit Private/Stealth spine-menu actions.
      detail: { tag: '', source: 'sidebar' },
    }));
  };

  const onForkThread = () => {
    document.dispatchEvent(new CustomEvent('ora:fork-conversation-requested', {
      detail: { source: 'sidebar' },
    }));
  };

  const ensureBrowser = () => {
    if (browserOverlay) return browserOverlay;
    browserOverlay = document.createElement('div');
    browserOverlay.className = 'conversation-browser-overlay';
    browserOverlay.setAttribute('role', 'dialog');
    // The Library is docked beside the workspace and intentionally leaves the
    // rest of Ora interactive, so it must not claim modal semantics.
    browserOverlay.setAttribute('aria-modal', 'false');
    browserOverlay.setAttribute('aria-label', 'Library');
    browserOverlay.innerHTML = `
      <div class="conversation-browser-panel">
        <div class="conversation-browser-top">
          <input class="conversation-browser-search" type="text"
                 placeholder="Search Dialogues..."
                 aria-label="Search Dialogues"
                 spellcheck="true"
                 autocorrect="on"
                 autocapitalize="sentences"
                 autocomplete="off" />
          <select class="conversation-browser-sort" aria-label="Sort results">
            <option value="relevance">Relevance</option>
            <option value="recency">Recency</option>
          </select>
          <button class="conversation-browser-search-btn" type="button">Search</button>
          <button class="conversation-browser-close" type="button" aria-label="Close Library">×</button>
        </div>
        <div class="conversation-browser-summary">
          <div class="conversation-browser-status" aria-live="polite"></div>
          <div class="conversation-browser-filters">
            <label class="conversation-browser-tags"
                   title="Comma-separated tags; all selected tags must match">
              <span class="conversation-browser-tags-label">Tags</span>
              <input class="conversation-browser-tags-input" type="text"
                     placeholder="atomic, framework/instruction"
                     aria-label="Filter by tags (all selected tags must match)"
                     spellcheck="false"
                     autocorrect="off"
                     autocapitalize="none"
                     autocomplete="off" />
            </label>
            <label class="conversation-browser-filter-chip conversation-browser-filter-chip-on">
              <input class="conversation-browser-filter-conversations" type="checkbox" checked>
              Dialogues
            </label>
            <label class="conversation-browser-filter-chip conversation-browser-filter-chip-on">
              <input class="conversation-browser-filter-engrams" type="checkbox" checked>
              Engrams
            </label>
            <label class="conversation-browser-filter-chip">
              <input class="conversation-browser-filter-archived" type="checkbox">
              Show archived
            </label>
            <label class="conversation-browser-relevance" title="Minimum relevance for searched results">
              <span class="conversation-browser-relevance-label">Relevance</span>
              <input class="conversation-browser-relevance-slider" type="range"
                     min="0" max="95" step="5" value="0"
                     aria-label="Minimum relevance">
              <span class="conversation-browser-relevance-value">0+</span>
            </label>
          </div>
        </div>
        <div class="conversation-browser-rows"></div>
      </div>`;
    document.body.appendChild(browserOverlay);
    browserSearch = browserOverlay.querySelector('.conversation-browser-search');
    browserSort = browserOverlay.querySelector('.conversation-browser-sort');
    browserConversationsToggle = browserOverlay.querySelector('.conversation-browser-filter-conversations');
    browserEngramsToggle = browserOverlay.querySelector('.conversation-browser-filter-engrams');
    browserTagsInput = browserOverlay.querySelector('.conversation-browser-tags-input');
    browserShowArchivedToggle = browserOverlay.querySelector('.conversation-browser-filter-archived');
    browserRelevanceSlider = browserOverlay.querySelector('.conversation-browser-relevance-slider');
    browserRelevanceValue = browserOverlay.querySelector('.conversation-browser-relevance-value');
    browserRows = browserOverlay.querySelector('.conversation-browser-rows');
    browserStatus = browserOverlay.querySelector('.conversation-browser-status');
    browserOverlay.querySelector('.conversation-browser-close')
      .addEventListener('click', closeBrowser);
    browserOverlay.querySelector('.conversation-browser-search-btn')
      .addEventListener('click', () => fetchBrowser(browserSearch.value));
    browserOverlay.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      e.preventDefault();
      e.stopPropagation();
      closeBrowser();
    });
    if (browserSort) {
      browserSort.addEventListener('change', () => fetchBrowser(browserSearch.value));
    }
    [browserConversationsToggle, browserEngramsToggle, browserShowArchivedToggle].forEach((toggle) => {
      if (!toggle) return;
      toggle.addEventListener('change', scheduleBrowserFilterRefresh);
      const chip = toggle.closest('.conversation-browser-filter-chip');
      if (chip) chip.addEventListener('click', scheduleBrowserFilterRefresh);
    });
    if (browserRelevanceSlider) {
      browserRelevanceSlider.addEventListener('input', () => {
        browserMinRelevance = parseInt(browserRelevanceSlider.value, 10) || 0;
        updateBrowserFilterUI();
        scheduleBrowserFetch();
      });
    }
    if (browserTagsInput) {
      browserTagsInput.addEventListener('input', scheduleBrowserFetch);
      browserTagsInput.addEventListener('change', scheduleBrowserFilterRefresh);
      browserTagsInput.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter') return;
        e.preventDefault();
        if (browserFetchTimer) clearTimeout(browserFetchTimer);
        browserFetchTimer = null;
        fetchBrowser(browserSearch ? browserSearch.value : '');
      });
    }
    browserSearch.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        fetchBrowser(browserSearch.value);
      }
    });
    return browserOverlay;
  };

  const updateBrowserFilterUI = () => {
    if (browserConversationsToggle) {
      const chip = browserConversationsToggle.closest('.conversation-browser-filter-chip');
      if (chip) chip.classList.toggle('conversation-browser-filter-chip-on', !!browserConversationsToggle.checked);
    }
    if (browserEngramsToggle) {
      const chip = browserEngramsToggle.closest('.conversation-browser-filter-chip');
      if (chip) chip.classList.toggle('conversation-browser-filter-chip-on', !!browserEngramsToggle.checked);
    }
    if (browserShowArchivedToggle) {
      const chip = browserShowArchivedToggle.closest('.conversation-browser-filter-chip');
      if (chip) chip.classList.toggle(
        'conversation-browser-filter-chip-on', !!browserShowArchivedToggle.checked);
    }
    if (browserRelevanceValue) {
      browserRelevanceValue.textContent = `${browserMinRelevance}+`;
    }
  };

  const syncBrowserFilterState = () => {
    browserIncludeConversations = !!(browserConversationsToggle && browserConversationsToggle.checked);
    browserIncludeEngrams = !!(browserEngramsToggle && browserEngramsToggle.checked);
    browserTags = browserTagsInput ? browserTagsInput.value : '';
    browserShowArchived = !!(browserShowArchivedToggle && browserShowArchivedToggle.checked);
  };

  const scheduleBrowserFilterRefresh = () => {
    if (browserFilterTimer) clearTimeout(browserFilterTimer);
    browserFilterTimer = setTimeout(() => {
      browserFilterTimer = null;
      syncBrowserFilterState();
      updateBrowserFilterUI();
      fetchBrowser(browserSearch ? browserSearch.value : '');
    }, 0);
  };

  const scheduleBrowserFetch = () => {
    if (browserFetchTimer) clearTimeout(browserFetchTimer);
    browserFetchTimer = setTimeout(() => {
      browserFetchTimer = null;
      fetchBrowser(browserSearch ? browserSearch.value : '');
    }, 180);
  };

  const applyBrowserRequestFilters = (params) => {
    syncBrowserFilterState();
    params.set('conversations', browserIncludeConversations ? '1' : '0');
    params.set('engrams', browserIncludeEngrams ? '1' : '0');
    const tags = String(browserTags || '')
      .split(',')
      .map(tag => tag.trim().toLowerCase())
      .filter((tag, index, all) => tag && all.indexOf(tag) === index)
      .join(',');
    if (tags) params.set('tags', tags);
    params.set('show_archived', browserShowArchived ? '1' : '0');
    params.set('min_relevance', String(browserMinRelevance || 0));
    if (browserSort && browserSort.value) params.set('sort', browserSort.value);
  };

  const positionBrowser = () => {
    if (!browserOverlay || !browserOverlay.classList.contains('is-open')) return;
    const shell = document.querySelector('.ora-shell');
    const leftColumn = document.querySelector('.left-column');
    const rightColumn = document.querySelector('.right-column');
    const inputPane = document.querySelector('.input-pane');
    if (!shell || !inputPane) return;
    const shellRect = shell.getBoundingClientRect();
    const leftRect = leftColumn ? leftColumn.getBoundingClientRect() : shellRect;
    const rightRect = rightColumn ? rightColumn.getBoundingClientRect() : shellRect;
    const inputRect = inputPane.getBoundingClientRect();
    const pad = 8;
    const top = Math.max(shellRect.top + pad, inputRect.top + pad);
    const height = Math.max(24, inputRect.bottom - pad - top);
    const left = leftRect.left + pad;
    const right = Math.max(left + 240, rightRect.right - pad);
    browserOverlay.style.setProperty('--conversation-browser-left', `${left}px`);
    browserOverlay.style.setProperty('--conversation-browser-top', `${top}px`);
    browserOverlay.style.setProperty('--conversation-browser-width', `${Math.max(240, right - left)}px`);
    browserOverlay.style.setProperty('--conversation-browser-height', `${height}px`);
  };

  const startBrowserPositioning = () => {
    window.addEventListener('resize', positionBrowser);
    if (!browserResizeObserver && 'ResizeObserver' in window) {
      browserResizeObserver = new ResizeObserver(positionBrowser);
      const shell = document.querySelector('.ora-shell');
      const leftColumn = document.querySelector('.left-column');
      const rightColumn = document.querySelector('.right-column');
      const inputPane = document.querySelector('.input-pane');
      if (shell) browserResizeObserver.observe(shell);
      if (leftColumn) browserResizeObserver.observe(leftColumn);
      if (rightColumn) browserResizeObserver.observe(rightColumn);
      if (inputPane) browserResizeObserver.observe(inputPane);
    }
    positionBrowser();
  };

  const stopBrowserPositioning = () => {
    window.removeEventListener('resize', positionBrowser);
    if (browserResizeObserver) {
      browserResizeObserver.disconnect();
      browserResizeObserver = null;
    }
  };

  const openBrowser = () => {
    ensureBrowser();
    if (!browserOverlay.classList.contains('is-open')) {
      browserDismissedIds = new Set();
      const active = document.activeElement;
      browserReturnFocus = active && active !== document.body && typeof active.focus === 'function'
        ? active
        : browseCmd;
    }
    browserOverlay.classList.add('is-open');
    updateBrowserFilterUI();
    startBrowserPositioning();
    fetchBrowser('');
    setTimeout(() => {
      positionBrowser();
      try { browserSearch.focus(); } catch (e) {}
    }, 0);
  };

  const closeBrowser = () => {
    const wasOpen = !!(browserOverlay && browserOverlay.classList.contains('is-open'));
    if (browserOverlay) browserOverlay.classList.remove('is-open');
    stopBrowserPositioning();
    if (!wasOpen) return;
    const focusTarget = browserReturnFocus && browserReturnFocus.isConnected
      ? browserReturnFocus
      : browseCmd;
    browserReturnFocus = null;
    if (focusTarget && typeof focusTarget.focus === 'function') {
      try { focusTarget.focus(); } catch (e) {}
    }
  };

  const fetchBrowser = async (query) => {
    ensureBrowser();
    browserStatus.textContent = 'Loading...';
    try {
      const params = new URLSearchParams();
      if ((query || '').trim()) params.set('q', query.trim());
      applyBrowserRequestFilters(params);
      params.set('limit', '200');
      const requestUrl = '/api/conversations/browser?' + params.toString();
      const r = await fetch(requestUrl);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const data = await r.json();
      browserLastData = data;
      browserRowsCache = data.rows || [];
      renderBrowserRows(browserRowsCache, data.query || '');
      updateBrowserStatus();
    } catch (e) {
      browserStatus.textContent = 'Search failed: ' + (e.message || e);
      browserRows.innerHTML = '';
    }
  };

  const browserVisibleRows = () => (
    (browserRowsCache || []).filter(row => !browserDismissedIds.has(row.conversation_id))
  );

  const browserVisibleCounts = (rows) => {
    const counts = { live: 0, archive: 0, engram: 0 };
    (rows || []).forEach((row) => {
      const kind = row.source_kind || 'live';
      if (counts[kind] !== undefined) counts[kind] += 1;
    });
    return counts;
  };

  const updateBrowserStatus = () => {
    if (!browserStatus) return;
    const visible = browserVisibleRows();
    const counts = browserVisibleCounts(visible);
    const parts = [];
    if (counts.live) parts.push(`${counts.live} live`);
    if (counts.archive) parts.push(`${counts.archive} archived`);
    if (counts.engram) parts.push(`${counts.engram} engram${counts.engram === 1 ? '' : 's'}`);
    const removed = Math.max(0, (browserRowsCache || []).length - visible.length);
    const total = browserLastData && browserLastData.total;
    if (visible.length) {
      const shown = total && total !== visible.length
        ? `${visible.length} shown of ${total}`
        : `${visible.length}`;
      const floor = browserMinRelevance > 0 ? `, ≥${browserMinRelevance} relevance` : '';
      browserStatus.textContent = `${shown} result${visible.length === 1 ? '' : 's'}`
        + `${parts.length ? ` (${parts.join(', ')})` : ''}`
        + floor
        + `${removed ? `, ${removed} removed` : ''}`;
    } else {
      browserStatus.textContent = removed
        ? `No visible results, ${removed} removed`
        : 'No matching enabled Dialogues or engrams';
    }
  };

  const renderBrowserRows = (rows, query) => {
    browserRows.innerHTML = '';
    browserVisibleRows().forEach((row) => {
      const item = document.createElement('div');
      item.className = 'conversation-browser-row';
      if (row.conversation_id === activeConvId) item.classList.add('is-active');
      if (row.closed) item.classList.add('is-closed');
      if (row.source_kind) item.classList.add(`is-${row.source_kind}`);
      item.dataset.conversationId = row.conversation_id;
      item.dataset.sourceKind = row.source_kind || 'live';

      const rowTitle = row.title || row.conversation_id || '(untitled)';
      const rowKind = row.source_kind === 'engram' ? 'Engram' : 'Dialogue';
      item.setAttribute('role', 'group');
      item.setAttribute('aria-label', `${rowKind}: ${rowTitle}`);

      const check = document.createElement('input');
      check.type = 'checkbox';
      check.className = 'conversation-browser-check';
      check.checked = false;
      check.setAttribute('aria-label', `Select ${rowKind}: ${rowTitle}`);
      check.addEventListener('click', (e) => e.stopPropagation());
      item.appendChild(check);

      const title = document.createElement('button');
      title.type = 'button';
      title.className = 'conversation-browser-title';
      title.textContent = rowTitle;
      title.title = title.textContent;
      title.setAttribute('aria-label', `Open ${rowKind}: ${rowTitle}`);
      title.addEventListener('click', (e) => {
        e.stopPropagation();
        activateBrowserRow(row);
      });
      item.appendChild(title);

      const related = document.createElement('button');
      related.type = 'button';
      related.className = 'conversation-browser-related';
      related.textContent = 'Related';
      related.setAttribute('aria-label', `Show items related to ${rowTitle}`);
      related.addEventListener('click', (e) => {
        e.stopPropagation();
        fetchRelated(row.conversation_id);
      });
      item.appendChild(related);

      const dismiss = document.createElement('button');
      dismiss.type = 'button';
      dismiss.className = 'conversation-browser-dismiss';
      dismiss.textContent = '×';
      dismiss.title = 'Remove from these results';
      dismiss.setAttribute('aria-label', `Remove ${rowTitle} from these results`);
      dismiss.addEventListener('click', (e) => {
        e.stopPropagation();
        browserDismissedIds.add(row.conversation_id);
        renderBrowserRows(browserRowsCache, query);
        updateBrowserStatus();
      });
      item.appendChild(dismiss);

      item.addEventListener('click', () => activateBrowserRow(row));
      browserRows.appendChild(item);
    });
  };

  const fetchRelated = async (conversationId) => {
    if (!conversationId) return;
    browserStatus.textContent = 'Loading related Dialogues...';
    try {
      const params = new URLSearchParams();
      applyBrowserRequestFilters(params);
      const requestUrl = `/api/conversation/${encodeURIComponent(conversationId)}/related?${params.toString()}`;
      const r = await fetch(requestUrl);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const data = await r.json();
      browserLastData = data;
      browserRowsCache = data.rows || [];
      renderBrowserRows(browserRowsCache, '');
      updateBrowserStatus();
    } catch (e) {
      browserStatus.textContent = 'Related lookup failed: ' + (e.message || e);
    }
  };

  const activateBrowserRow = async (row) => {
    if (!row || !row.conversation_id) return;
    activeConvId = row.conversation_id;
    document.dispatchEvent(new CustomEvent('ora:conversation-selected', {
      detail: {
        conversation_id: row.conversation_id,
        tag: row.tag,
        title: row.title,
        source_kind: row.source_kind,
        result_type: row.result_type,
        source_conversation_id: row.source_conversation_id,
        matched_chunk_id: row.matched_chunk_id,
        matched_turn_index: row.matched_turn_index,
      },
    }));
    fetchList();
    positionBrowser();
  };

  // ── Wire-up ─────────────────────────────────────────────────────────
  if (expandIcon)  expandIcon.addEventListener('click',  () => setExpanded(true));
  if (newChatIcon) newChatIcon.addEventListener('click', onNewThread);
  if (newThreadCmd) newThreadCmd.addEventListener('click', onNewThread);
  if (forkThreadCmd) forkThreadCmd.addEventListener('click', onForkThread);
  if (browseCmd) browseCmd.addEventListener('click', openBrowser);

  document.addEventListener('ora:fresh-conversation-started', (e) => {
    const id = e.detail && e.detail.conversation_id;
    activeConvId = id || null;
    [...sidebar.querySelectorAll('.sidebar-row')].forEach(el => {
      el.classList.remove('is-active');
    });
    closeBrowser();
    if (!isPinned()) setExpanded(false);
  });

  document.addEventListener('ora:conversation-load-failed', (e) => {
    const detail = (e && e.detail) || {};
    activeConvId = detail.active_conversation_id || null;
    [...sidebar.querySelectorAll('.sidebar-row')].forEach(el => {
      el.classList.toggle('is-active', el.dataset.conversationId === activeConvId);
    });
    fetchList();
  });

  document.addEventListener('ora:conversation-lifecycle-state', (e) => {
    const detail = (e && e.detail) || {};
    const conversationId = detail.conversation_id;
    if (!conversationId) return;
    if (detail.active) lifecycleBusyIds.add(conversationId);
    else lifecycleBusyIds.delete(conversationId);
    Array.from(sidebar.querySelectorAll('.sidebar-row')).forEach((rowEl) => {
      if (rowEl.dataset.conversationId !== conversationId) return;
      rowEl.classList.toggle('is-lifecycle-busy', !!detail.active);
      const close = rowEl.querySelector('.sidebar-row-close');
      if (close) {
        close.disabled = !!detail.active;
        close.setAttribute('aria-disabled', detail.active ? 'true' : 'false');
      }
    });
  });

  // Privacy mutations are authoritative at runtime. Update any visible row
  // immediately, then refresh from the server so grouped snapshots and the
  // Library view converge on the same tag.
  document.addEventListener('ora:conversation-tag-changed', (e) => {
    const detail = (e && e.detail) || {};
    if (!detail.conversation_id) return;
    const rowEl = Array.from(sidebar.querySelectorAll('.sidebar-row'))
      .find((candidate) => candidate.dataset.conversationId === detail.conversation_id);
    if (rowEl) {
      const tag = detail.tag || '';
      rowEl.dataset.tag = tag;
      const prefix = rowEl.querySelector('.sidebar-row-prefix');
      if (prefix) prefix.textContent = prefixForTag(tag);
      const close = rowEl.querySelector('.sidebar-row-close');
      if (close) {
        const label = tag === 'stealth' ? 'Delete Dialogue forever' : 'Close Dialogue';
        close.setAttribute('aria-label', label);
        close.title = label;
      }
    }
    fetchList();
  });

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
      // Toggle behavior:
      //   * sidebar closed → open
      //   * sidebar open + pinned → no-op (pin keeps it open)
      //   * sidebar open + unpinned → close
      if (isExpanded()) {
        if (isPinned()) return;
        setExpanded(false);
      } else {
        setExpanded(true);
      }
      // Drop focus after a mouse click so the SVG group's :focus outline
      // doesn't linger as a "box" around the A. Keyboard users (Tab) still
      // get focus-visible indication via the existing CSS.
      try { e.currentTarget.blur(); } catch (_) { /* SVGElement.blur may
        not be implemented on every browser version — ignore */ }
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
    // The Library is non-modal, so focus may legitimately be elsewhere in
    // the workspace. Escape still closes it before any sidebar shortcut runs.
    if (e.key === 'Escape'
        && browserOverlay
        && browserOverlay.classList.contains('is-open')) {
      e.preventDefault();
      closeBrowser();
      return;
    }

    const shortcuts = window.OraKeyboardShortcuts;
    const cmd = e.metaKey || e.ctrlKey;
    const k   = e.key.toLowerCase();

    // Cmd+K / Ctrl+K — open the conversation sidebar.
    // See Reference — Ora Keyboard Shortcuts (vault).
    if ((shortcuts && shortcuts.matches('app_open_sidebar', e))
        || (!shortcuts && cmd && k === 'k' && !e.shiftKey && !e.altKey)) {
      e.preventDefault();
      setExpanded(true);
      return;
    }
    // Cmd+J / Ctrl+J — start a new conversation.
    if ((shortcuts && shortcuts.matches('app_new_conversation', e))
        || (!shortcuts && cmd && k === 'j' && !e.shiftKey && !e.altKey)) {
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

  // ── G1.33 project switcher wiring ────────────────────────────────────
  if (projectNameEl) projectNameEl.textContent = projectDisplayName(activeProjectId);
  if (projectBtn) projectBtn.addEventListener('click', (e) => { e.stopPropagation(); toggleProjectMenu(); });
  if (projectSearch) projectSearch.addEventListener('input', renderProjects);
  if (projectNewBtn) projectNewBtn.addEventListener('click', () => {
    // MOM-guided creation (graceful): the modal collects the name, creates the
    // record + vault folder, then invites the user into Mission & Goals. Falls
    // back to a name-only prompt if the modal module isn't present.
    closeProjectMenu();
    if (window.OraProjectModal && typeof window.OraProjectModal.openCreate === 'function') {
      window.OraProjectModal.openCreate();
      return;
    }
    (async () => {
      const name = (window.prompt('New project name:') || '').trim();
      if (!name) return;
      try {
        const r = await fetch('/api/projects/create', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name }),
        });
        const data = await r.json();
        if (data && data.ok && data.project) {
          await fetchProjects();
          setActiveProject(data.project.nexus, data.project.name);
          if (data.storage_available === false) {
            window.alert(data.storage_warning
              || 'Project created, but vault storage is unavailable. No project folder was created.');
          }
        } else {
          window.alert('Could not create project: ' + ((data && data.error) || 'unknown error'));
        }
      } catch (e) {}
    })();
  });
  document.addEventListener('click', (e) => {
    if (projectMenu && !projectMenu.hidden && projectSwitcher && !projectSwitcher.contains(e.target)) {
      closeProjectMenu();
    }
  });

  // G1.33 sub-step 5 — open the project management modal for the active
  // project (⚙ on the Active-Project row + 'Manage current project' in the
  // switcher dropdown).
  const openProjectModal = () => {
    const cur = projectsCache.find(p => canonicalProjectRecordId(p) === activeProjectId);
    const name = cur ? (cur.name || cur.nexus) : projectDisplayName(activeProjectId);
    try {
      if (window.OraProjectModal && typeof window.OraProjectModal.open === 'function') {
        window.OraProjectModal.open(activeProjectId, name);
      }
    } catch (e) {}
  };
  if (projectManageBtn) projectManageBtn.addEventListener('click', (e) => {
    e.stopPropagation(); openProjectModal();
  });
  if (projectManageItem) projectManageItem.addEventListener('click', (e) => {
    e.stopPropagation(); closeProjectMenu(); openProjectModal();
  });

  // ── G1.33 model-configuration section ────────────────────────────────
  // Shows the active configuration name; the per-project / per-run selector
  // is a later sub-step (G1.35). Clicking opens Settings → Models for now.
  const fetchModelConfig = async () => {
    try {
      const r = await fetch('/api/configurations');
      if (!r.ok) return;
      const d = await r.json();
      if (modelConfigName && d && d.active_name) modelConfigName.textContent = d.active_name;
    } catch (e) {}
  };
  if (modelConfigBtn) modelConfigBtn.addEventListener('click', () => {
    try {
      const sp = window.OraSettingsPanel;
      if (sp && typeof sp.open === 'function') sp.open({ tab: 'models' });
    } catch (e) {}
  });
  fetchModelConfig();

  // ── Output-style section — mirrors model configuration. Shows the active
  // Output Style; clicking opens Settings → Output Styles. ────────────────
  const fetchOutputStyle = async () => {
    try {
      const r = await fetch('/api/styles/registry');
      if (!r.ok) return;
      const d = await r.json();
      const id = d && d.settings && d.settings.default_id;
      let name = 'None';
      if (id) {
        const all = (d.profiles || []).concat(d.custom || []);
        const p = all.find(x => x && x.id === id);
        name = p ? p.display_name : id;
      }
      if (outputStyleName) outputStyleName.textContent = name;
    } catch (e) {}
  };
  if (outputStyleBtn) outputStyleBtn.addEventListener('click', () => {
    try {
      const sp = window.OraSettingsPanel;
      if (sp && typeof sp.open === 'function') sp.open({ tab: 'styles' });
    } catch (e) {}
  });
  fetchOutputStyle();

  // ── Polling ─────────────────────────────────────────────────────────
  let pollHandle = window.setInterval(refreshProjectScopedList, REFRESH_INTERVAL_MS);

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      refreshProjectScopedList();
      if (!pollHandle) {
        pollHandle = window.setInterval(refreshProjectScopedList, REFRESH_INTERVAL_MS);
      }
    } else {
      if (pollHandle) {
        window.clearInterval(pollHandle);
        pollHandle = null;
      }
    }
  });
  window.addEventListener('storage', (event) => {
    if (event && event.key === ACTIVE_PROJECT_KEY) {
      refreshProjectScopedList();
    }
  });

  // Expose minimal API for other modules + DevTools.
  window.OraSidebar = {
    refresh: fetchList,
    setExpanded,
    isExpanded,
    getActiveConversation: () => activeConvId,
    getActiveProject: () => activeProjectId,
    syncActiveProject: reconcileActiveProject,
    refreshProjectScope: refreshProjectScopedList,
    refreshProjects: fetchProjects,
    setActiveProject: (nexus, name) => setActiveProject(nexus, name),
  };

  // The server pointer determines where NEW Dialogues are stamped. Reconcile
  // it before the first project/list paint so localStorage cannot present a
  // stale project as authoritative.
  (async () => {
    await reconcileActiveProject();
    await fetchProjects();
    await fetchList();
  })();
})();
