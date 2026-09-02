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
  const dashProject  = sidebar.querySelector('#sidebarDashProject');
  const dashModel    = sidebar.querySelector('#sidebarDashModel');
  const dashStyle    = sidebar.querySelector('#sidebarDashOutputStyle');
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
  const outputStyleBtn  = sidebar.querySelector('#sidebarOutputStyleBtn');
  const outputStyleName = sidebar.querySelector('#sidebarOutputStyleName');
  const modelSettingsBtn = sidebar.querySelector('#sidebarModelSettingsBtn');
  const resizeHandle = sidebar.querySelector('#sidebarResizeHandle');

  const SIDEBAR_WIDTH_KEY = 'ora-sidebar-width';
  const MIN_SIDEBAR_WIDTH = 280;
  let expandedSidebarWidth = MIN_SIDEBAR_WIDTH;
  const maxSidebarWidth = () => Math.max(
    MIN_SIDEBAR_WIDTH,
    Math.min(520, Math.floor(window.innerWidth * 0.45))
  );
  const applySidebarWidth = (value, persist) => {
    const width = Math.max(MIN_SIDEBAR_WIDTH, Math.min(maxSidebarWidth(), Number(value) || MIN_SIDEBAR_WIDTH));
    sidebar.style.setProperty('--ora-sidebar-expanded-w', width + 'px');
    expandedSidebarWidth = width;
    if (resizeHandle) resizeHandle.setAttribute('aria-valuenow', String(width));
    if (persist) {
      try { localStorage.setItem(SIDEBAR_WIDTH_KEY, String(width)); } catch (_) {}
    }
    return width;
  };
  try { applySidebarWidth(localStorage.getItem(SIDEBAR_WIDTH_KEY), false); }
  catch (_) { applySidebarWidth(MIN_SIDEBAR_WIDTH, false); }

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
  let projectManagerEl = null;
  let projectManagerStatus = 'active';
  let activeProjectSyncGeneration = 0;
  let activeProjectMutationInFlight = false;
  let pendingActiveProjectSelection = null;
  let activeProjectSelectionSequence = 0;

  let lastSnapshot = { pinned: [], errored: [], pending: [], unread: [], active: [] };
  let lastServerSnapshot = lastSnapshot;
  let conversationsEtag = '';
  let fetchListInFlight = null;
  let fetchListTrailing = false;
  let pollHandle = null;
  let activeConvId = null;
  let creationOverlay = null;
  let creationTitle = null;
  let creationDescription = null;
  let creationResults = null;
  let creationStatus = null;
  let creationReviewCheck = null;
  let creationCommit = null;
  let creationRows = [];
  let creationSelectedRefs = new Set();
  let creationReviewToken = '';
  let creationContractToken = '';
  let creationContractDigest = '';
  let creationContractFingerprint = '';
  let creationReviewedDescription = '';
  let creationTag = '';
  let creationDiscoveryProjectId = '';
  let creationIncludedRefs = [];
  let creationUnsupportedContext = [];
  let creationReturnFocus = null;
  let creationBusy = false;
  let creationOpenGeneration = 0;
  const lifecycleBusyIds = new Set();

  const setExpanded = (on) => {
    const changed = isExpanded() !== !!on;
    sidebar.classList.toggle('expanded', !!on);
    document.body.classList.toggle('sidebar-expanded', !!on);
    if (!changed) return;
    if (on) startSidebarPolling(true);
    else stopSidebarPolling();
  };

  if (resizeHandle) {
    resizeHandle.setAttribute('aria-valuemin', String(MIN_SIDEBAR_WIDTH));
    resizeHandle.setAttribute('aria-valuemax', String(maxSidebarWidth()));
    let resizeStartX = 0;
    let resizeStartWidth = MIN_SIDEBAR_WIDTH;
    const moveResize = (event) => applySidebarWidth(resizeStartWidth + event.clientX - resizeStartX, false);
    const finishResize = () => {
      document.removeEventListener('pointermove', moveResize);
      document.removeEventListener('pointerup', finishResize);
      applySidebarWidth(sidebar.getBoundingClientRect().width, true);
      document.body.classList.remove('sidebar-resizing');
    };
    resizeHandle.addEventListener('pointerdown', (event) => {
      resizeStartX = event.clientX;
      resizeStartWidth = sidebar.getBoundingClientRect().width;
      document.body.classList.add('sidebar-resizing');
      resizeHandle.setPointerCapture && resizeHandle.setPointerCapture(event.pointerId);
      document.addEventListener('pointermove', moveResize);
      document.addEventListener('pointerup', finishResize);
      event.preventDefault();
      event.stopPropagation();
    });
    resizeHandle.addEventListener('keydown', (event) => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      const delta = event.key === 'ArrowRight' ? 16 : -16;
      applySidebarWidth(sidebar.getBoundingClientRect().width + delta, true);
      event.preventDefault();
    });
    window.addEventListener('resize', () => applySidebarWidth(expandedSidebarWidth, false));
  }

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

  const updateWordmarkAttention = () => {
    const logoA = document.getElementById('logo-a');
    if (!logoA) return;
    const hasAttention = sidebar.dataset.dialogueAttention === 'true';
    logoA.classList.toggle('wordmark-attract', hasAttention);
  };

  const filterDialogueSnapshot = (snapshot) => {
    const data = snapshot || {};
    const visible = (row) => {
      if (!row) return false;
      if (row.tag === 'stealth') return row.conversation_id === activeConvId;
      if (activeProjectId === 'commons') return true;
      return Array.isArray(row.project_ids)
        && row.project_ids.indexOf(activeProjectId) !== -1;
    };
    const filtered = Object.assign({}, data);
    ['pinned', 'errored', 'pending', 'unread', 'active'].forEach((group) => {
      filtered[group] = Array.isArray(data[group])
        ? data[group].filter(visible)
        : [];
    });
    return filtered;
  };

  const render = (data) => {
    lastServerSnapshot = data || lastServerSnapshot;
    data = filterDialogueSnapshot(data);
    lastSnapshot = data;

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
    const hasDialogueAttention = (data.unread  || []).length > 0
      || (data.errored || []).length > 0
      || (data.pending || []).length > 0;
    sidebar.dataset.dialogueAttention = hasDialogueAttention ? 'true' : 'false';
    updateWordmarkAttention();

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
      const closeLabel = row.tag === 'stealth' ? 'Delete Forever' : 'Close';
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

    // The shared tooltip renderer handles the full conversation title.
    el.setAttribute('data-tooltip', row.title || '(untitled)');

    el.addEventListener('click', () => onRowClick(row));
    return el;
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

  const fetchListOnce = async () => {
    try {
      // Fetch the active universe, then apply the project rule locally. A
      // server-scoped response cannot include the currently displayed
      // Stealth Dialogue after the user switches to a different project.
      const headers = conversationsEtag ? { 'If-None-Match': conversationsEtag } : {};
      const r = await fetch('/api/conversations?project_id=', { headers });
      if (r.status === 304) {
        return;
      }
      if (!r.ok) return;
      if (r.headers && typeof r.headers.get === 'function') {
        conversationsEtag = r.headers.get('ETag') || conversationsEtag;
      }
      const data = await r.json();
      render(data);
    } catch (e) {
      // Network failure during polling — render the last snapshot we had.
    }
  };

  const fetchList = () => {
    if (fetchListInFlight) {
      fetchListTrailing = true;
      return fetchListInFlight;
    }
    fetchListTrailing = false;
    fetchListInFlight = Promise.resolve().then(async () => {
      await fetchListOnce();
      while (fetchListTrailing) {
        fetchListTrailing = false;
        await fetchListOnce();
      }
    }).finally(() => {
      fetchListInFlight = null;
    });
    return fetchListInFlight;
  };

  // ── G1.33 project switcher ──────────────────────────────────────────────
  const projectDisplayName = (nexus) =>
    canonicalProjectId(nexus) === 'commons' ? 'Commons' : nexus;

  const renderProjects = () => {
    if (!projectListEl) return;
    const q = ((projectSearch && projectSearch.value) || '').trim().toLowerCase();
    projectListEl.innerHTML = '';
    const visible = projectsCache
      .filter(p => !q || String(p.name || p.nexus).toLowerCase().includes(q))
      .filter(p => p && (p.is_default || p.status === 'active'));
    if (!visible.length) {
      const empty = document.createElement('div');
      empty.className = 'sidebar-group-empty';
      empty.textContent = q ? 'No matching projects.' : 'No projects in this view.';
      projectListEl.appendChild(empty);
      return;
    }
    visible.forEach(p => {
        const row = document.createElement('div');
        const rowId = canonicalProjectRecordId(p);
        row.className = 'sidebar-project-row'
          + (rowId === activeProjectId ? ' is-active' : '');
        row.setAttribute('role', 'option');
        row.tabIndex = 0;
        const name = document.createElement('span');
        name.className = 'sidebar-project-row-name';
        name.textContent = p.name || p.nexus;
        row.appendChild(name);
        const badge = document.createElement('span');
        badge.className = 'sidebar-project-badge';
        const unread = p.unread_count || 0;
        badge.textContent = String(unread);
        badge.setAttribute('data-zero', unread ? '0' : '1');
        row.appendChild(badge);
        row.addEventListener('click', () => setActiveProject(rowId, p.name || p.nexus));
        row.addEventListener('keydown', (ev) => {
          if (ev.key === 'Enter' || ev.key === ' ') {
            ev.preventDefault();
            setActiveProject(rowId, p.name || p.nexus);
          }
        });
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

  const updateProjectStatus = async (nexus, status) => {
    try {
      const r = await fetch('/api/projects/' + encodeURIComponent(canonicalProjectId(nexus)) + '/status', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
      if (!r.ok) return;
      await reconcileActiveProject();
      await fetchProjects();
      if (projectManagerEl) await renderProjectManager();
      await fetchList();
    } catch (e) {}
  };

  const resolveProjectActionIcon = (iconRef) => {
    if (window.OraIconResolver && typeof window.OraIconResolver.resolve === 'function') {
      return window.OraIconResolver.resolve(iconRef);
    }
    const safe = String(iconRef == null ? '' : iconRef)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
      + 'data-icon-fallback="no-resolver" data-icon="' + safe + '"></svg>';
  };

  // ── Priority ordering ─────────────────────────────────────────────────
  // The Active list is the user's ranked work queue: top is most important.
  // A drag sends the WHOLE resulting order, so ranks stay contiguous and what
  // is on disk always matches what is on screen.
  const persistProjectOrder = async (rowsEl) => {
    const order = [...rowsEl.querySelectorAll('.project-manager-row')]
      .map(r => r.dataset.projectId)
      .filter(Boolean);
    if (!order.length) return;
    try {
      await fetch('/api/projects/order', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order }),
      });
    } catch (e) { /* order is advisory; a failed save just leaves it as-was */ }
    await fetchProjects();
    await renderProjectManager();
  };

  const attachRowDragHandlers = (row, rowsEl) => {
    row.addEventListener('dragstart', (ev) => {
      row.classList.add('is-dragging');
      // Firefox will not start a drag without payload.
      try { ev.dataTransfer.setData('text/plain', row.dataset.projectId || ''); } catch (e) {}
      ev.dataTransfer.effectAllowed = 'move';
    });
    row.addEventListener('dragend', async () => {
      row.classList.remove('is-dragging');
      await persistProjectOrder(rowsEl);
    });
    row.addEventListener('dragover', (ev) => {
      ev.preventDefault();
      const dragging = rowsEl.querySelector('.is-dragging');
      if (!dragging || dragging === row) return;
      const box = row.getBoundingClientRect();
      // In a multi-column grid, reading order runs across before it runs down,
      // so the drop side is decided horizontally when the pointer is level
      // with the row and vertically otherwise. A single column has no
      // horizontal axis to speak of and always uses the vertical midpoint.
      const after = isMultiColumn(rowsEl)
        ? (ev.clientY >= box.top && ev.clientY <= box.bottom
            ? ev.clientX > box.left + box.width / 2
            : ev.clientY > box.top + box.height / 2)
        : ev.clientY > box.top + box.height / 2;
      rowsEl.insertBefore(dragging, after ? row.nextSibling : row);
      renumberProjectRanks(rowsEl);
    });
  };

  const isMultiColumn = (rowsEl) => {
    try {
      const tracks = getComputedStyle(rowsEl).gridTemplateColumns || '';
      return tracks.trim().split(/\s+/).filter(Boolean).length > 1;
    } catch (e) {
      return false;
    }
  };

  const renumberProjectRanks = (rowsEl) => {
    [...rowsEl.querySelectorAll('.project-manager-row')].forEach((r, i) => {
      const rank = r.querySelector('.project-manager-rank');
      if (rank) rank.textContent = String(i + 1);
    });
  };

  const ensureProjectManager = () => {
    if (projectManagerEl) return projectManagerEl;
    projectManagerEl = document.createElement('div');
    projectManagerEl.className = 'project-manager-overlay';
    projectManagerEl.innerHTML = `
      <div class="project-manager-card" role="dialog" aria-label="Manage projects">
        <div class="project-manager-head">
          <div>
            <div class="project-manager-kicker">Projects</div>
            <div class="project-manager-title">Manage projects</div>
          </div>
          <button class="project-manager-close" type="button" aria-label="Close">×</button>
        </div>
        <input class="project-manager-search" type="text" placeholder="Search projects…" autocomplete="off" spellcheck="false" />
        <div class="project-manager-tabs">
          <button class="project-manager-tab is-active" type="button" data-project-manager-status="active">Active</button>
          <button class="project-manager-tab" type="button" data-project-manager-status="inactive">Inactive</button>
          <button class="project-manager-tab" type="button" data-project-manager-status="archived">Archived</button>
        </div>
        <div class="project-manager-rows"></div>
      </div>`;
    document.body.appendChild(projectManagerEl);
    projectManagerEl.querySelector('.project-manager-close').addEventListener('click', () => {
      projectManagerEl.classList.remove('is-open');
    });
    projectManagerEl.addEventListener('click', (ev) => {
      if (ev.target === projectManagerEl) projectManagerEl.classList.remove('is-open');
    });
    projectManagerEl.querySelector('.project-manager-search').addEventListener('input', renderProjectManager);
    projectManagerEl.querySelectorAll('[data-project-manager-status]').forEach(tab => {
      tab.addEventListener('click', () => {
        projectManagerStatus = tab.dataset.projectManagerStatus || 'active';
        renderProjectManager();
      });
    });
    return projectManagerEl;
  };

  const renderProjectManager = async () => {
    const modal = ensureProjectManager();
    const rowsEl = modal.querySelector('.project-manager-rows');
    const q = (modal.querySelector('.project-manager-search').value || '').trim().toLowerCase();
    modal.querySelectorAll('[data-project-manager-status]').forEach(tab => {
      tab.classList.toggle('is-active', tab.dataset.projectManagerStatus === projectManagerStatus);
    });
    rowsEl.innerHTML = '';
    let rows = [];
    try {
      const r = await fetch('/api/projects/meta?status=' + encodeURIComponent(projectManagerStatus));
      const data = await r.json();
      rows = (data && data.projects) || [];
    } catch (e) {}
    rows = rows
      .filter(p => !p.is_default)
      .filter(p => !q || String(p.name || p.nexus).toLowerCase().includes(q));
    if (!rows.length) {
      const empty = document.createElement('div');
      empty.className = 'project-manager-empty';
      empty.textContent = q ? 'No matching projects.' : 'No projects in this view.';
      rowsEl.appendChild(empty);
      return;
    }
    // Priority order is only meaningful for the Active list — a paused or
    // archived project is not competing for attention.
    const orderable = projectManagerStatus === 'active' && !q && rows.length > 1;
    rowsEl.classList.toggle('is-orderable', orderable);
    rows.forEach((p, index) => {
      const row = document.createElement('div');
      row.className = 'project-manager-row';
      const id = canonicalProjectRecordId(p);
      if (orderable) {
        row.draggable = true;
        row.dataset.projectId = id;
        const grip = document.createElement('span');
        grip.className = 'project-manager-grip';
        grip.setAttribute('aria-hidden', 'true');
        grip.innerHTML = resolveProjectActionIcon('grip-vertical');
        row.appendChild(grip);
        const rank = document.createElement('span');
        rank.className = 'project-manager-rank';
        rank.textContent = String(index + 1);
        row.appendChild(rank);
        attachRowDragHandlers(row, rowsEl);
      }
      const main = document.createElement('div');
      main.className = 'project-manager-row-main';
      main.innerHTML = `<div class="project-manager-row-name"></div><div class="project-manager-row-meta"></div>`;
      main.querySelector('.project-manager-row-name').textContent = p.name || p.nexus;
      main.querySelector('.project-manager-row-meta').textContent = id;
      row.appendChild(main);
      const actions = document.createElement('div');
      actions.className = 'project-manager-actions';
      const add = (label, nextStatus, icon) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'project-manager-action';
        btn.title = label;
        btn.setAttribute('aria-label', label);
        btn.innerHTML = resolveProjectActionIcon(icon);
        btn.addEventListener('click', (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          updateProjectStatus(id, nextStatus);
        });
        btn.addEventListener('keydown', (ev) => ev.stopPropagation());
        actions.appendChild(btn);
      };
      if (projectManagerStatus === 'active') {
        add('Pause project', 'inactive', 'pause');
        add('Archive project', 'archived', 'archive');
      } else if (projectManagerStatus === 'inactive') {
        add('Reactivate project', 'active', 'check');
        add('Archive project', 'archived', 'archive');
      } else {
        add('Restore project to inactive', 'inactive', 'rotate-ccw');
        add('Reactivate project', 'active', 'check');
      }
      row.appendChild(actions);
      rowsEl.appendChild(row);
    });
  };

  const openProjectManager = async () => {
    closeProjectMenu();
    const modal = ensureProjectManager();
    projectManagerStatus = 'active';
    modal.classList.add('is-open');
    modal.querySelector('.project-manager-search').value = '';
    await renderProjectManager();
    if (!modal.classList.contains('is-open')) return;
    modal.querySelector('.project-manager-search').focus();
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
      const previousProjectId = activeProjectId;
      activeProjectId = canonicalProjectId(supplied);
      persistActiveProjectId(activeProjectId);
      const cur = projectsCache.find(p => canonicalProjectRecordId(p) === activeProjectId);
      if (projectNameEl) {
        projectNameEl.textContent = cur ? (cur.name || cur.nexus) : projectDisplayName(activeProjectId);
      }
      renderProjects();
      if (activeProjectId !== previousProjectId) {
        render(lastServerSnapshot);
        document.dispatchEvent(new CustomEvent('ora:active-project-changed', {
          detail: { nexus: activeProjectId },
        }));
      }
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
      const previousProjectId = activeProjectId;
      activeProjectId = confirmedId;
      persistActiveProjectId(activeProjectId);
      if (projectNameEl) {
        projectNameEl.textContent = activeProjectId === requestedId
          ? (selection.name || projectDisplayName(activeProjectId))
          : projectDisplayName(activeProjectId);
      }
      closeProjectMenu();
      if (activeProjectId !== previousProjectId) render(lastServerSnapshot);
      fetchList();      // refetch the sidebar filtered to this project
      renderProjects(); // refresh the active highlight
      document.dispatchEvent(new CustomEvent('ora:active-project-changed', {
        detail: { nexus: activeProjectId },
      }));
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
    return result;
  };

  // Backlog 11 — retry an errored conversation. Server returns the
  // last user prompt; the conversation privacy boundary freshly evaluates
  // that recovered text before /chat/multipart. A privacy fork rebinds the
  // retry to the selected child. The errored flag is cleared on success.
  const onRetryClick = async (row) => {
    let prompt = '';
    let tag = row.tag || '';
    let visualCheckpointId = '';
    let visualCheckpointSourceId = '';
    try {
      const r = await fetch(`/api/conversation/${encodeURIComponent(row.conversation_id)}/retry`, { method: 'POST' });
      if (!r.ok) {
        alert('Retry could not be staged: HTTP ' + r.status);
        return;
      }
      const data = await r.json();
      prompt = data.last_user_prompt || '';
      tag = data.tag || tag;
      visualCheckpointId = data.visual_checkpoint_id || '';
      visualCheckpointSourceId = data.visual_checkpoint_source_conversation_id || '';
    } catch (e) {
      alert('Retry failed: ' + (e.message || e));
      return;
    }
    if (!prompt) {
      alert('Nothing to retry — no user prompt found in this Dialogue.');
      return;
    }
    const lifecycle = window.OraConversation;
    if (!lifecycle || typeof lifecycle.submitAfterPrivacy !== 'function'
        || typeof lifecycle.getActiveConversationId !== 'function') {
      alert('Dialogue privacy controls are unavailable.');
      return;
    }
    try {
      if (lifecycle.getActiveConversationId() !== row.conversation_id) {
        await lifecycle.load(row.conversation_id);
      }
      if (lifecycle.getActiveConversationId() !== row.conversation_id) return;

      await lifecycle.submitAfterPrivacy(prompt, async () => {
        const targetId = lifecycle.getActiveConversationId();
        if (!targetId) return;
        const targetTag = typeof lifecycle.getActiveTag === 'function'
          ? lifecycle.getActiveTag() : tag;
        const body = new FormData();
        body.append('message', prompt);
        body.append('conversation_id', targetId);
        body.append('panel_id',        targetId);
        body.append('is_main_feed',    'true');
        body.append('tag',             targetTag || tag);
        if (visualCheckpointId) {
          body.append('retry_visual_checkpoint_id', visualCheckpointId);
          body.append(
            'retry_visual_source_conversation_id',
            visualCheckpointSourceId || row.conversation_id
          );
          body.append('exhibits_submission_intent', 'explicit_send');
        }

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
          // Clear the original row's errored flag after its retry succeeds,
          // even when the retried turn was submitted to a Private child.
          try {
            await fetch(`/api/conversation/${encodeURIComponent(row.conversation_id)}/dismiss-error`, { method: 'POST' });
          } catch (e) {}
        }
      }, { draftText: prompt });
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

  const creationDescriptionReady = () => {
    const text = creationDescription ? creationDescription.value.trim() : '';
    const terms = text.match(/[A-Za-z0-9][A-Za-z0-9_-]+/g) || [];
    return text.length >= 20 && text.length <= 4000 && terms.length >= 3;
  };

  const currentCreationContractFingerprint = () => JSON.stringify({
    title: creationTitle ? creationTitle.value.trim().replace(/\s+/g, ' ') : '',
    description: creationDescription ? creationDescription.value.trim() : '',
    review_token: creationReviewToken,
    contributors: Array.from(creationSelectedRefs),
    tag: creationTag,
    acknowledged: true,
  });

  const invalidateCreationAcceptance = () => {
    creationContractToken = '';
    creationContractDigest = '';
    creationContractFingerprint = '';
    if (creationReviewCheck) creationReviewCheck.checked = false;
    updateCreationCommitState();
  };

  const resetCreationReview = () => {
    creationReviewToken = '';
    creationReviewedDescription = '';
    creationRows = [];
    creationSelectedRefs = new Set();
    creationContractToken = '';
    creationContractDigest = '';
    creationContractFingerprint = '';
    if (creationReviewCheck) {
      creationReviewCheck.checked = false;
      creationReviewCheck.disabled = true;
    }
    if (creationResults) creationResults.innerHTML = '';
    updateCreationCommitState();
  };

  const updateCreationCommitState = () => {
    if (!creationCommit) return;
    const titleReady = !!(creationTitle && creationTitle.value.trim()
      && creationTitle.value.trim().length <= 200);
    const exactReview = !!creationReviewToken
      && creationDescription
      && creationReviewedDescription === creationDescription.value.trim();
    const exactAcceptance = !!creationContractToken
      && creationContractFingerprint === currentCreationContractFingerprint();
    creationCommit.disabled = creationBusy || !titleReady || !creationDescriptionReady()
      || !exactReview || !exactAcceptance
      || !creationReviewCheck || !creationReviewCheck.checked;
  };

  const closeCreation = () => {
    const wasOpen = !!(creationOverlay && creationOverlay.classList.contains('is-open'));
    if (creationOverlay) creationOverlay.classList.remove('is-open');
    if (!wasOpen) return;
    const target = creationReturnFocus && creationReturnFocus.isConnected
      ? creationReturnFocus
      : newThreadCmd;
    creationReturnFocus = null;
    if (target && typeof target.focus === 'function') {
      try { target.focus(); } catch (e) {}
    }
  };

  const continueFromCreation = (row) => {
    if (!row || row.source_kind !== 'live') return;
    const draft = creationDescription ? creationDescription.value.trim() : '';
    closeCreation();
    document.dispatchEvent(new CustomEvent('ora:conversation-selected', {
      detail: {
        conversation_id: row.conversation_id,
        tag: row.tag || '',
        title: row.title,
        draft_message: draft,
        source: 'creation-discovery-continue',
      },
    }));
  };

  const forkDiscoveredRow = async (row, draftMessage, tag, source) => {
    if (!row || row.source_kind !== 'live' || !row.conversation_id) return;
    try {
      const requestBody = {};
      if (typeof tag === 'string') requestBody.tag = tag;
      const resp = await fetch(`/api/conversation/${encodeURIComponent(row.conversation_id)}/fork`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });
      const data = await resp.json();
      if (!resp.ok || !data.new_conversation_id) {
        throw new Error(data.error || `HTTP ${resp.status}`);
      }
      closeCreation();
      document.dispatchEvent(new CustomEvent('ora:library-close-requested'));
      document.dispatchEvent(new CustomEvent('ora:conversation-selected', {
        detail: {
          conversation_id: data.new_conversation_id,
          tag: data.tag || (typeof tag === 'string' ? tag : ''),
          title: data.new_conversation_id,
          draft_message: draftMessage || '',
          source: source || 'library-fork',
        },
      }));
      fetchList();
    } catch (e) {
      if (creationStatus && creationOverlay && creationOverlay.classList.contains('is-open')) {
        creationStatus.textContent = 'Fork failed: ' + (e.message || e);
      } else {
        window.alert('Fork failed: ' + (e.message || e));
      }
    }
  };

  const renderCreationRows = () => {
    if (!creationResults) return;
    creationResults.innerHTML = '';
    creationRows.forEach((row) => {
      const item = document.createElement('div');
      item.className = 'conversation-create-result';
      item.dataset.conversationId = row.conversation_id || '';

      const copy = document.createElement('div');
      copy.className = 'conversation-create-result-copy';
      const kind = document.createElement('span');
      kind.className = 'conversation-create-result-kind';
      kind.textContent = row.source_kind === 'engram' ? 'Atomic note' : 'Dialogue';
      const title = document.createElement('strong');
      title.textContent = row.title || row.conversation_id || '(untitled)';
      const snippet = document.createElement('span');
      snippet.className = 'conversation-create-result-snippet';
      snippet.textContent = row.snippet || '';
      copy.append(kind, title, snippet);
      item.appendChild(copy);

      const actions = document.createElement('div');
      actions.className = 'conversation-create-result-actions';
      const add = document.createElement('button');
      add.type = 'button';
      add.className = 'conversation-create-add';
      const selected = creationSelectedRefs.has(row.conversation_id);
      add.textContent = selected ? 'Added' : 'Add contributor';
      add.setAttribute('aria-pressed', selected ? 'true' : 'false');
      add.addEventListener('click', () => {
        if (creationSelectedRefs.has(row.conversation_id)) {
          creationSelectedRefs.delete(row.conversation_id);
        } else {
          creationSelectedRefs.add(row.conversation_id);
        }
        invalidateCreationAcceptance();
        renderCreationRows();
      });
      actions.appendChild(add);
      if (row.source_kind === 'live') {
        const continueButton = document.createElement('button');
        continueButton.type = 'button';
        continueButton.className = 'conversation-create-continue';
        continueButton.textContent = 'Continue';
        continueButton.addEventListener('click', () => continueFromCreation(row));
        const forkButton = document.createElement('button');
        forkButton.type = 'button';
        forkButton.className = 'conversation-create-fork';
        forkButton.textContent = 'Fork';
        forkButton.addEventListener('click', () => forkDiscoveredRow(
          row,
          creationDescription ? creationDescription.value.trim() : '',
          creationTag,
          'creation-discovery-fork'
        ));
        actions.append(continueButton, forkButton);
      }
      item.appendChild(actions);
      creationResults.appendChild(item);
    });
  };

  const discoverForCreation = async () => {
    if (!creationDescriptionReady()) {
      creationStatus.textContent = 'Describe the intended subject in at least 20 characters and 3 terms.';
      resetCreationReview();
      return;
    }
    creationBusy = true;
    updateCreationCommitState();
    creationStatus.textContent = 'Searching Dialogues and atomic notes…';
    const description = creationDescription.value.trim();
    const openGeneration = creationOpenGeneration;
    try {
      const params = new URLSearchParams({
        q: description,
        purpose: 'creation',
        conversations: '1',
        engrams: '1',
        show_archived: '0',
        sort: 'relevance',
        limit: '40',
      });
      params.set('target_tag', creationTag);
      if (creationDiscoveryProjectId) params.set('project_id', creationDiscoveryProjectId);
      creationIncludedRefs.forEach((ref) => params.append('include_ref', ref));
      const resp = await fetch('/api/conversations/browser?' + params.toString());
      const data = await resp.json();
      if (openGeneration !== creationOpenGeneration) return;
      if (!resp.ok || !data.review_token) {
        throw new Error(data.error || `HTTP ${resp.status}`);
      }
      creationRows = data.rows || [];
      creationReviewToken = data.review_token;
      creationReviewedDescription = description;
      creationContractToken = '';
      creationContractDigest = '';
      creationContractFingerprint = '';
      creationSelectedRefs = new Set(
        Array.from(creationSelectedRefs).filter(ref =>
          creationRows.some(row => row.conversation_id === ref))
      );
      creationIncludedRefs.forEach((ref) => {
        if (creationRows.some(row => row.conversation_id === ref)) creationSelectedRefs.add(ref);
      });
      renderCreationRows();
      creationReviewCheck.disabled = false;
      creationReviewCheck.checked = false;
      const unsupported = creationUnsupportedContext.length
        ? ` Unsupported Library context: ${creationUnsupportedContext.join('; ')}.`
        : '';
      creationStatus.textContent = (creationRows.length
        ? `${creationRows.length} related item${creationRows.length === 1 ? '' : 's'} found. Review them before creating.`
        : 'No related Dialogues or atomic notes found. Confirm that result before creating.') + unsupported;
    } catch (e) {
      if (openGeneration !== creationOpenGeneration) return;
      resetCreationReview();
      creationStatus.textContent = 'Discovery failed: ' + (e.message || e);
    } finally {
      if (openGeneration === creationOpenGeneration) {
        creationBusy = false;
        updateCreationCommitState();
      }
    }
  };

  const acknowledgeCreationReview = async () => {
    if (!creationReviewCheck || !creationReviewCheck.checked) {
      invalidateCreationAcceptance();
      return;
    }
    const fingerprint = currentCreationContractFingerprint();
    creationBusy = true;
    creationContractToken = '';
    creationContractDigest = '';
    creationContractFingerprint = '';
    updateCreationCommitState();
    creationStatus.textContent = 'Binding your review to this exact creation contract…';
    try {
      const resp = await fetch('/api/conversations/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: creationTitle.value.trim(),
          description: creationDescription.value.trim(),
          review_token: creationReviewToken,
          contributors: Array.from(creationSelectedRefs),
          tag: creationTag,
          acknowledged: true,
        }),
      });
      const data = await resp.json();
      if (!resp.ok || !data.creation_token || !data.contract_digest) {
        throw new Error(data.error || `HTTP ${resp.status}`);
      }
      if (!creationReviewCheck.checked || currentCreationContractFingerprint() !== fingerprint) {
        return;
      }
      creationContractToken = data.creation_token;
      creationContractDigest = data.contract_digest;
      creationContractFingerprint = fingerprint;
      creationStatus.textContent = 'Review confirmed for this exact title, description, privacy, and contributor set.';
    } catch (e) {
      invalidateCreationAcceptance();
      creationStatus.textContent = 'Review confirmation failed: ' + (e.message || e);
    } finally {
      creationBusy = false;
      updateCreationCommitState();
    }
  };

  const commitCreation = async () => {
    if (!creationCommit || creationCommit.disabled) return;
    creationBusy = true;
    updateCreationCommitState();
    creationStatus.textContent = 'Creating Dialogue…';
    const description = creationDescription.value.trim();
    try {
      const resp = await fetch('/api/conversations/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          review_token: creationReviewToken,
          creation_token: creationContractToken,
        }),
      });
      const data = await resp.json();
      if (!resp.ok || !data.conversation_id) {
        throw new Error(data.error || `HTTP ${resp.status}`);
      }
      closeCreation();
      document.dispatchEvent(new CustomEvent('ora:conversation-selected', {
        detail: {
          conversation_id: data.conversation_id,
          tag: data.tag || '',
          title: data.display_name,
          draft_message: description,
          source: 'reviewed-dialogue-creation',
        },
      }));
      fetchList();
    } catch (e) {
      const message = e.message || String(e);
      if (/missing or expired|changed after discovery/i.test(message)) {
        resetCreationReview();
      }
      creationStatus.textContent = 'Creation failed: ' + message;
    } finally {
      creationBusy = false;
      updateCreationCommitState();
    }
  };

  const ensureCreation = () => {
    if (creationOverlay) return creationOverlay;
    creationOverlay = document.createElement('div');
    creationOverlay.className = 'conversation-create-overlay';
    creationOverlay.setAttribute('role', 'dialog');
    creationOverlay.setAttribute('aria-modal', 'true');
    creationOverlay.setAttribute('aria-labelledby', 'conversationCreateHeading');
    creationOverlay.innerHTML = `
      <div class="conversation-create-panel">
        <div class="conversation-create-header">
          <div>
            <h2 id="conversationCreateHeading">New Dialogue</h2>
            <p>Describe the work, review related material, then choose whether to create, continue, or fork.</p>
          </div>
          <button class="conversation-create-close" type="button" aria-label="Cancel new Dialogue">×</button>
        </div>
        <label class="conversation-create-field">
          <span>Title</span>
          <input class="conversation-create-title" maxlength="200" autocomplete="off" />
        </label>
        <label class="conversation-create-field">
          <span>Expanded description</span>
          <textarea class="conversation-create-description" minlength="20" maxlength="4000" rows="5"
            placeholder="What do you want to explore or accomplish, and what should related material be about?"></textarea>
        </label>
        <div class="conversation-create-discovery-row">
          <button class="conversation-create-discover" type="button">Find related material</button>
          <span class="conversation-create-status" aria-live="polite">Nothing is created until you confirm.</span>
        </div>
        <div class="conversation-create-results" aria-label="Related Dialogues and atomic notes"></div>
        <div class="conversation-create-footer">
          <label class="conversation-create-reviewed">
            <input type="checkbox" disabled>
            <span>I reviewed these suggestions and they match my intended subject.</span>
          </label>
          <div class="conversation-create-footer-actions">
            <button class="conversation-create-cancel" type="button">Cancel</button>
            <button class="conversation-create-commit" type="button" disabled>Create Dialogue</button>
          </div>
        </div>
      </div>`;
    document.body.appendChild(creationOverlay);
    creationTitle = creationOverlay.querySelector('.conversation-create-title');
    creationDescription = creationOverlay.querySelector('.conversation-create-description');
    creationResults = creationOverlay.querySelector('.conversation-create-results');
    creationStatus = creationOverlay.querySelector('.conversation-create-status');
    creationReviewCheck = creationOverlay.querySelector('.conversation-create-reviewed input');
    creationCommit = creationOverlay.querySelector('.conversation-create-commit');
    creationOverlay.querySelector('.conversation-create-close').addEventListener('click', closeCreation);
    creationOverlay.querySelector('.conversation-create-cancel').addEventListener('click', closeCreation);
    creationOverlay.querySelector('.conversation-create-discover').addEventListener('click', discoverForCreation);
    creationCommit.addEventListener('click', commitCreation);
    creationTitle.addEventListener('input', () => {
      invalidateCreationAcceptance();
      updateCreationCommitState();
    });
    creationDescription.addEventListener('input', () => {
      if (creationDescription.value.trim() !== creationReviewedDescription) resetCreationReview();
      updateCreationCommitState();
    });
    creationReviewCheck.addEventListener('change', acknowledgeCreationReview);
    creationOverlay.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeCreation();
        return;
      }
      if (event.key === 'Tab') {
        const focusable = Array.from(creationOverlay.querySelectorAll(
          'button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])'
        )).filter(el => el.offsetParent !== null || el === document.activeElement);
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    });
    return creationOverlay;
  };

  const openCreation = (detail = {}) => {
    creationOpenGeneration += 1;
    creationBusy = false;
    ensureCreation();
    document.dispatchEvent(new CustomEvent('ora:library-close-requested'));
    const active = document.activeElement;
    creationReturnFocus = active && active !== document.body && typeof active.focus === 'function'
      ? active
      : newThreadCmd;
    creationTag = detail.tag === 'private' || detail.tag === 'stealth' ? detail.tag : '';
    creationDiscoveryProjectId = compatibleProjectId(detail.discovery_project_id);
    const prefillRows = Array.isArray(detail.prefill_rows)
      ? detail.prefill_rows
      : (detail.prefill_row ? [detail.prefill_row] : []);
    creationIncludedRefs = Array.from(new Set(prefillRows
      .map(row => row && row.conversation_id ? String(row.conversation_id) : '')
      .filter(Boolean)));
    creationUnsupportedContext = Array.isArray(detail.unsupported_context)
      ? detail.unsupported_context.map(String).filter(Boolean)
      : [];
    creationTitle.value = '';
    creationDescription.value = detail.description || '';
    creationStatus.textContent = creationUnsupportedContext.length
      ? `Nothing is created until you confirm. Unsupported Library context: ${creationUnsupportedContext.join('; ')}.`
      : 'Nothing is created until you confirm.';
    resetCreationReview();
    creationOverlay.classList.add('is-open');
    const heading = creationOverlay.querySelector('#conversationCreateHeading');
    heading.textContent = `New ${creationTag === 'private' ? 'Private ' : creationTag === 'stealth' ? 'Off Record ' : ''}Dialogue`;
    setTimeout(() => creationTitle.focus(), 0);
  };

  // The Knowledge Library owns its workspace and request state. Sidebar keeps
  // only the existing Dialogue mutations so Library actions follow the same
  // lifecycle, creation, project, and selection seams as ordinary sidebar rows.
  const libraryDialogueRow = (row) => {
    const locator = row && row.preview && row.preview.locator;
    const conversationId = locator && locator.dialogue_id
      ? String(locator.dialogue_id)
      : '';
    if (!conversationId) return null;
    const privacy = String((row.metadata && row.metadata.privacy) || '').toLowerCase();
    const tag = privacy === 'private' ? 'private'
      : (privacy === 'stealth' || privacy === 'off_record') ? 'stealth' : '';
    return {
      conversation_id: conversationId,
      title: row.title || conversationId,
      tag,
      source_kind: 'live',
      result_type: 'dialogue',
    };
  };

  const openLibrary = () => {
    closeCreation();
    document.dispatchEvent(new CustomEvent('ora:library-open-requested', {
      detail: { returnFocus: browseCmd },
    }));
  };

  const continueLibraryDialogue = (row) => {
    const dialogue = libraryDialogueRow(row);
    if (!dialogue) throw new Error('This Dialogue is metadata-only and cannot be opened.');
    document.dispatchEvent(new CustomEvent('ora:library-close-requested'));
    activeConvId = dialogue.conversation_id;
    document.dispatchEvent(new CustomEvent('ora:conversation-selected', {
      detail: {
        conversation_id: dialogue.conversation_id,
        tag: dialogue.tag,
        title: dialogue.title,
        source_kind: dialogue.source_kind,
        result_type: dialogue.result_type,
        source: 'knowledge-library-continue',
      },
    }));
  };

  const forkLibraryDialogue = async (row) => {
    const dialogue = libraryDialogueRow(row);
    if (!dialogue) throw new Error('This Dialogue is metadata-only and cannot be forked.');
    // Omit tag so the server inherits the authoritative parent privacy. A
    // Library aggregate such as contains_private is not fork-write authority.
    await forkDiscoveredRow(dialogue, '', undefined, 'knowledge-library-fork');
  };

  const createFromLibraryDialogue = (row) => {
    const dialogue = libraryDialogueRow(row);
    if (!dialogue) throw new Error('This Dialogue is metadata-only and cannot be a contributor.');
    openCreation({ prefill_row: dialogue });
  };

  const libraryContextPrivacyTag = (rows) => {
    let privateContext = false;
    for (const row of rows) {
      const metadata = row && row.metadata && typeof row.metadata === 'object'
        ? row.metadata : {};
      const privacy = String(metadata.privacy || '').toLowerCase();
      const tags = Array.isArray(metadata.tags)
        ? metadata.tags.map(tag => String(tag).toLowerCase()) : [];
      if (privacy === 'stealth' || privacy === 'off_record'
          || tags.includes('stealth') || tags.includes('off_record')) return 'stealth';
      if (privacy === 'private' || privacy === 'contains_private'
          || tags.includes('private') || tags.includes('contains_private')) privateContext = true;
    }
    return privateContext ? 'private' : '';
  };

  const createFromLibrarySelection = (rows, discoveryProjectId) => {
    const selected = Array.isArray(rows) ? rows.filter(Boolean) : [];
    const contributors = [];
    const unsupported = [];
    selected.forEach((row) => {
      if (row.source === 'dialogues') {
        const dialogue = libraryDialogueRow(row);
        if (dialogue) contributors.push(dialogue);
        else unsupported.push(`${row.title || row.id || 'Dialogue'} (metadata-only Dialogue)`);
        return;
      }
      if (row.source === 'engrams') {
        const metadata = row.metadata && typeof row.metadata === 'object'
          ? row.metadata : {};
        const tags = Array.isArray(metadata.tags)
          ? metadata.tags.map(tag => String(tag).toLowerCase()) : [];
        if (String(row.id || '').startsWith('engrams:') && tags.includes('atomic')) {
          contributors.push({
            conversation_id: `engram:${String(row.id).slice('engrams:'.length)}`,
            source_kind: 'engram',
            result_type: 'engram',
            title: row.title || row.id,
          });
        } else {
          unsupported.push(`${row.title || row.id || 'Engram'} (non-atomic Engram)`);
        }
        return;
      }
      unsupported.push(`${row.title || row.id || 'Item'} (${row.source === 'files' ? 'File' : 'unsupported source'})`);
    });
    if (!contributors.length) {
      throw new Error(`No checked item can be used as Dialogue context. Unsupported Library context: ${unsupported.join('; ') || 'none'}.`);
    }
    openCreation({
      prefill_rows: contributors,
      unsupported_context: unsupported,
      tag: libraryContextPrivacyTag(selected),
      discovery_project_id: discoveryProjectId,
    });
    return { contributors: contributors.map(row => row.conversation_id), unsupported };
  };

  const setLibraryDialogueArchived = async (row, archived) => {
    const dialogue = libraryDialogueRow(row);
    if (!dialogue) throw new Error('This Dialogue is metadata-only and has no lifecycle action.');
    if (archived) {
      const result = await onCloseClick(dialogue);
      if (!result || result.ok !== true) return false;
    } else {
      const response = await fetch(
        `/api/conversation/${encodeURIComponent(dialogue.conversation_id)}/restore`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        }
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      await fetchList();
    }
    if (row.metadata) row.metadata.lifecycle = archived ? 'inactive' : 'active';
    if (window.OraLibraryWorkspace && window.OraLibraryWorkspace.isOpen()) {
      await window.OraLibraryWorkspace.refresh();
    }
    return true;
  };

  const addLibrarySelectionToActiveProject = async (rows) => {
    const projectId = canonicalProjectId(activeProjectId);
    if (!projectId || projectId === 'commons') {
      throw new Error('Choose a named active project before adding selected Dialogues.');
    }
    const dialogues = (rows || []).map((libraryRow) => ({
      libraryId: libraryRow.id,
      dialogue: libraryDialogueRow(libraryRow),
    })).filter((item) => Boolean(item.dialogue));
    if (!dialogues.length) throw new Error('The selection contains no readable Dialogues.');
    const successfulIds = [];
    const failures = [];
    for (const item of dialogues) {
      const row = item.dialogue;
      try {
        const response = await fetch(
          `/api/conversation/${encodeURIComponent(row.conversation_id)}/projects`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ add_project_id: projectId }),
          }
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
        successfulIds.push(item.libraryId);
      } catch (error) {
        failures.push(`${row.title}: ${error && error.message ? error.message : error}`);
      }
    }
    await fetchList();
    if (window.OraLibraryWorkspace && window.OraLibraryWorkspace.isOpen()) {
      await window.OraLibraryWorkspace.refresh();
    }
    return { successfulIds, failures };
  };
  // ── Wire-up ─────────────────────────────────────────────────────────
  if (expandIcon)  expandIcon.addEventListener('click',  () => setExpanded(true));
  if (dashProject) dashProject.addEventListener('click', openProjectManager);
  if (dashModel) dashModel.addEventListener('click', () => {
    if (window.OraSettingsPanel && typeof window.OraSettingsPanel.open === 'function') {
      window.OraSettingsPanel.open({ tab: 'models' });
    }
  });
  if (dashStyle) dashStyle.addEventListener('click', () => {
    if (window.OraSettingsPanel && typeof window.OraSettingsPanel.open === 'function') {
      window.OraSettingsPanel.open({ tab: 'styles' });
    }
  });
  if (modelSettingsBtn) modelSettingsBtn.addEventListener('click', (event) => {
    event.stopPropagation();
    if (window.OraSettingsPanel && typeof window.OraSettingsPanel.open === 'function') {
      window.OraSettingsPanel.open({ tab: 'models' });
    }
  });
  if (newChatIcon) newChatIcon.addEventListener('click', onNewThread);
  if (newThreadCmd) newThreadCmd.addEventListener('click', onNewThread);
  if (forkThreadCmd) forkThreadCmd.addEventListener('click', onForkThread);
  if (browseCmd) browseCmd.addEventListener('click', openLibrary);
  if (dash) {
    dash.addEventListener('click', (event) => {
      if (event.target === dash) setExpanded(true);
    });
  }

  document.addEventListener('ora:conversation-selected', (e) => {
    const id = e && e.detail && e.detail.conversation_id;
    if (!id) return;
    activeConvId = id;
    [...sidebar.querySelectorAll('.sidebar-row')].forEach((el) => {
      el.classList.toggle('is-active', el.dataset.conversationId === activeConvId);
    });
  });

  document.addEventListener('ora:fresh-conversation-started', (e) => {
    const id = e.detail && e.detail.conversation_id;
    activeConvId = id || null;
    [...sidebar.querySelectorAll('.sidebar-row')].forEach(el => {
      el.classList.remove('is-active');
    });
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
    const lifecycle = window.OraConversation;
    if (lifecycle && typeof lifecycle.getActiveConversationId === 'function'
        && lifecycle.getActiveConversationId() === detail.conversation_id) {
      activeConvId = detail.conversation_id;
    }
    const rowEl = Array.from(sidebar.querySelectorAll('.sidebar-row'))
      .find((candidate) => candidate.dataset.conversationId === detail.conversation_id);
    if (rowEl) {
      const tag = detail.tag || '';
      rowEl.dataset.tag = tag;
      const prefix = rowEl.querySelector('.sidebar-row-prefix');
      if (prefix) prefix.textContent = prefixForTag(tag);
      const close = rowEl.querySelector('.sidebar-row-close');
      if (close) {
        const label = tag === 'stealth' ? 'Delete Forever' : 'Close';
        close.setAttribute('aria-label', label);
        close.title = label;
      }
    }
    if (detail.source !== 'conversation-envelope') fetchList();
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
    if (e.key === 'Escape'
        && creationOverlay
        && creationOverlay.classList.contains('is-open')) {
      e.preventDefault();
      closeCreation();
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
    e.stopPropagation(); openProjectManager();
  });

  // ── Output-style default selector. Preset management remains in Settings;
  // this compact surface selects the same account default directly. ───────
  let outputStyleRegistry = null;
  let outputStyleMenu = null;
  const fetchOutputStyle = async () => {
    try {
      const r = await fetch('/api/styles/registry');
      if (!r.ok) return;
      const d = await r.json();
      outputStyleRegistry = d || {};
      const id = d && d.settings && d.settings.default_id;
      let name = 'None';
      if (id) {
        const all = (d.profiles || []).concat(d.custom || []);
        const p = all.find(x => x && x.id === id);
        name = p ? p.display_name : id;
      }
      if (outputStyleName) outputStyleName.textContent = name;
      return d;
    } catch (e) {}
  };
  const closeOutputStyleMenu = () => {
    if (outputStyleMenu) outputStyleMenu.hidden = true;
    if (outputStyleBtn) outputStyleBtn.setAttribute('aria-expanded', 'false');
  };
  const chooseOutputStyle = async (id, name) => {
    const response = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ updates: { styles: { default_id: id } } }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    if (outputStyleName) outputStyleName.textContent = name || 'None';
    if (outputStyleRegistry) {
      outputStyleRegistry.settings = Object.assign({}, outputStyleRegistry.settings, {
        default_id: id,
      });
    }
    closeOutputStyleMenu();
    document.dispatchEvent(new CustomEvent('ora:settings-saved', {
      detail: data.settings || {},
    }));
  };
  const openOutputStyleMenu = async () => {
    if (outputStyleMenu && !outputStyleMenu.hidden) {
      closeOutputStyleMenu();
      return;
    }
    const registry = outputStyleRegistry || await fetchOutputStyle() || {};
    if (!outputStyleMenu) {
      outputStyleMenu = document.createElement('div');
      outputStyleMenu.className = 'sidebar-outputstyle-menu';
      outputStyleMenu.setAttribute('role', 'listbox');
      outputStyleBtn.parentElement.appendChild(outputStyleMenu);
    }
    outputStyleMenu.innerHTML = '';
    const profiles = [{ id: '', display_name: 'None' }]
      .concat(registry.profiles || [], registry.custom || []);
    profiles.forEach(profile => {
      if (!profile || typeof profile.id !== 'string') return;
      const option = document.createElement('button');
      option.type = 'button';
      option.setAttribute('role', 'option');
      option.textContent = profile.display_name || profile.id || 'None';
      option.setAttribute(
        'aria-selected',
        registry.settings && registry.settings.default_id === profile.id ? 'true' : 'false'
      );
      option.addEventListener('click', () => {
        chooseOutputStyle(profile.id, option.textContent).catch(error => {
          window.alert('Output Style was not changed: ' + (error.message || error));
        });
      });
      outputStyleMenu.appendChild(option);
    });
    outputStyleMenu.hidden = false;
    outputStyleBtn.setAttribute('aria-expanded', 'true');
  };
  if (outputStyleBtn) {
    outputStyleBtn.setAttribute('aria-haspopup', 'listbox');
    outputStyleBtn.setAttribute('aria-expanded', 'false');
    outputStyleBtn.addEventListener('click', (event) => {
      event.stopPropagation();
      openOutputStyleMenu();
    });
  }
  document.addEventListener('click', (event) => {
    if (outputStyleMenu && !outputStyleMenu.hidden
        && !outputStyleMenu.contains(event.target)
        && event.target !== outputStyleBtn) closeOutputStyleMenu();
  });
  fetchOutputStyle();

  // ── Polling ─────────────────────────────────────────────────────────
  function stopSidebarPolling() {
    if (!pollHandle) return;
    window.clearInterval(pollHandle);
    pollHandle = null;
  }

  function startSidebarPolling(refreshNow) {
    if (!isExpanded() || document.visibilityState !== 'visible') {
      stopSidebarPolling();
      return;
    }
    if (refreshNow) refreshProjectScopedList();
    if (!pollHandle) {
      pollHandle = window.setInterval(refreshProjectScopedList, REFRESH_INTERVAL_MS);
    }
  }

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      startSidebarPolling(true);
    } else {
      stopSidebarPolling();
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
    openCreation,
    closeCreation,
    continueLibraryDialogue,
    forkLibraryDialogue,
    createFromLibraryDialogue,
    createFromLibrarySelection,
    setLibraryDialogueArchived,
    addLibrarySelectionToActiveProject,
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
