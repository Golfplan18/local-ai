/* Full Review Queue panel for Ora oversight items.
 *
 * The sidebar keeps its compact Paused / Operating trays. This modal is the
 * larger work surface for reading queue entries and taking action without
 * using slash commands.
 */
(() => {
  'use strict';

  const POLL_MS = 12000;

  let _backdrop = null;
  let _activeTab = 'paused';
  let _paused = [];
  let _operating = [];
  let _selectedId = null;
  let _poll = null;

  const esc = (value) => String(value == null ? '' : value);

  function build() {
    if (_backdrop) return _backdrop;
    _backdrop = document.createElement('div');
    _backdrop.className = 'ora-review-backdrop';
    _backdrop.innerHTML = `
      <div class="ora-review-modal" role="dialog" aria-modal="true" aria-labelledby="oraReviewTitle">
        <div class="ora-review-header">
          <h2 id="oraReviewTitle">Review Queue</h2>
          <button type="button" class="ora-review-close" aria-label="Close review queue">&times;</button>
        </div>
        <div class="ora-review-tabs" role="tablist">
          <button type="button" class="ora-review-tab" data-tab="paused">Paused <span data-count="paused">0</span></button>
          <button type="button" class="ora-review-tab" data-tab="operating">Operating <span data-count="operating">0</span></button>
        </div>
        <div class="ora-review-body">
          <div class="ora-review-list" data-role="list"></div>
          <div class="ora-review-detail" data-role="detail"></div>
        </div>
        <div class="ora-review-footer">
          <span class="ora-review-status" data-role="status"></span>
          <button type="button" class="ora-settings-btn" data-role="refresh">Refresh</button>
        </div>
      </div>`;

    _backdrop.addEventListener('click', (e) => {
      if (e.target === _backdrop) close();
    });
    _backdrop.querySelector('.ora-review-close').addEventListener('click', close);
    _backdrop.querySelector('[data-role="refresh"]').addEventListener('click', refresh);
    _backdrop.querySelectorAll('.ora-review-tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        _activeTab = tab.dataset.tab || 'paused';
        _selectedId = null;
        render();
      });
    });
    return _backdrop;
  }

  function open(opts = {}) {
    build();
    if (!_backdrop.parentNode) document.body.appendChild(_backdrop);
    _activeTab = opts.tab || _activeTab || 'paused';
    _backdrop.classList.add('ora-review-backdrop--visible');
    document.addEventListener('keydown', onKeydown);
    refresh();
    startPoll();
  }

  function close() {
    if (_backdrop) _backdrop.classList.remove('ora-review-backdrop--visible');
    document.removeEventListener('keydown', onKeydown);
    stopPoll();
  }

  function toggle(opts = {}) {
    build();
    if (_backdrop.classList.contains('ora-review-backdrop--visible')) close();
    else open(opts);
  }

  function onKeydown(e) {
    if (e.key === 'Escape') close();
  }

  function startPoll() {
    if (_poll) return;
    _poll = window.setInterval(refresh, POLL_MS);
  }

  function stopPoll() {
    if (_poll) {
      window.clearInterval(_poll);
      _poll = null;
    }
  }

  function setStatus(text, kind = '') {
    const el = _backdrop && _backdrop.querySelector('[data-role="status"]');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'ora-review-status' + (kind ? ' ora-review-status--' + kind : '');
  }

  async function refresh() {
    if (!_backdrop) return;
    setStatus('Refreshing...');
    try {
      const [pausedRes, operatingRes] = await Promise.all([
        fetch('/api/oversight/paused'),
        fetch('/api/oversight/operating'),
      ]);
      const paused = pausedRes.ok ? await pausedRes.json() : { entries: [] };
      const operating = operatingRes.ok ? await operatingRes.json() : { entries: [] };
      _paused = Array.isArray(paused.entries) ? paused.entries : [];
      _operating = Array.isArray(operating.entries) ? operating.entries : [];
      if (_selectedId && !currentRows().some((row) => row.id === _selectedId)) {
        _selectedId = null;
      }
      setStatus('');
      render();
    } catch (err) {
      setStatus((err && err.message) || String(err), 'error');
    }
  }

  function currentRows() {
    return _activeTab === 'operating' ? _operating : _paused;
  }

  function render() {
    if (!_backdrop) return;
    _backdrop.querySelectorAll('.ora-review-tab').forEach((tab) => {
      tab.classList.toggle('is-active', tab.dataset.tab === _activeTab);
    });
    const pausedCount = _backdrop.querySelector('[data-count="paused"]');
    const operatingCount = _backdrop.querySelector('[data-count="operating"]');
    if (pausedCount) pausedCount.textContent = String(_paused.length);
    if (operatingCount) operatingCount.textContent = String(_operating.length);

    const list = _backdrop.querySelector('[data-role="list"]');
    const detail = _backdrop.querySelector('[data-role="detail"]');
    list.innerHTML = '';
    const rows = currentRows();
    if (!rows.length) {
      const empty = document.createElement('div');
      empty.className = 'ora-review-empty';
      empty.textContent = _activeTab === 'paused'
        ? 'No paused review items.'
        : 'No operating items.';
      list.appendChild(empty);
    } else {
      rows.forEach((row) => list.appendChild(buildRow(row)));
    }
    const selected = rows.find((row) => row.id === _selectedId) || rows[0] || null;
    if (selected && !_selectedId) _selectedId = selected.id;
    detail.innerHTML = '';
    detail.appendChild(
      selected
        ? (_activeTab === 'operating' ? buildOperatingDetail(selected) : buildPausedDetail(selected))
        : buildEmptyDetail(),
    );
  }

  function buildRow(row) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'ora-review-row';
    btn.classList.toggle('is-selected', row.id === _selectedId);
    btn.dataset.entryId = row.id || '';
    const title = document.createElement('span');
    title.className = 'ora-review-row-title';
    title.textContent = row.name || row.id || '(unnamed)';
    btn.appendChild(title);
    const meta = document.createElement('span');
    meta.className = 'ora-review-row-meta';
    meta.textContent = [
      row.project_nexus,
      row.event_type || row.kind,
      row.queued_at || row.started_at ? ageOf(row.queued_at || row.started_at) : '',
    ].filter(Boolean).join(' · ');
    btn.appendChild(meta);
    btn.addEventListener('click', () => {
      _selectedId = row.id;
      render();
      if (_activeTab === 'paused' && row.engagement === 'unseen') {
        markEngagement(row.id, 'seen');
      }
    });
    return btn;
  }

  function buildEmptyDetail() {
    const empty = document.createElement('div');
    empty.className = 'ora-review-empty';
    empty.textContent = 'Select a queue item.';
    return empty;
  }

  function buildPausedDetail(entry) {
    const wrap = document.createElement('div');
    const h = document.createElement('h3');
    h.textContent = entry.name || '(unnamed)';
    wrap.appendChild(h);
    wrap.appendChild(metaLine([
      entry.project_nexus,
      entry.event_type,
      entry.redefinition ? 'redefinition' : '',
      entry.queued_at ? ageOf(entry.queued_at) : '',
    ]));

    const reasoning = document.createElement('pre');
    reasoning.className = 'ora-review-reasoning';
    reasoning.textContent = entry.reasoning_excerpt || '(no reasoning recorded)';
    wrap.appendChild(reasoning);

    const actions = document.createElement('div');
    actions.className = 'ora-review-actions';
    actions.appendChild(actionButton('Discuss', () => startDiscussion(entry)));
    actions.appendChild(actionButton('Approve', () => quickAction(entry, 'approve'), 'primary'));
    actions.appendChild(actionButton('Deny', () => {
      const reason = window.prompt('Reason for denial (optional):', '') || '';
      quickAction(entry, 'deny', { reason });
    }));
    actions.appendChild(actionButton('Rename', () => renameEntry(entry)));
    wrap.appendChild(actions);

    if (entry.discussion_conversation_id) {
      const open = document.createElement('button');
      open.type = 'button';
      open.className = 'ora-review-link';
      open.textContent = 'Open discussion conversation';
      open.addEventListener('click', () => {
        openDiscussionConversation(entry.discussion_conversation_id, entry);
      });
      wrap.appendChild(open);
    }
    return wrap;
  }

  function buildOperatingDetail(entry) {
    const wrap = document.createElement('div');
    const h = document.createElement('h3');
    h.textContent = entry.name || '(unnamed task)';
    wrap.appendChild(h);
    wrap.appendChild(metaLine([
      entry.kind,
      entry.project_nexus,
      entry.framework_id,
      entry.mode,
      entry.started_at ? ageOf(entry.started_at) : '',
    ]));
    const pre = document.createElement('pre');
    pre.className = 'ora-review-reasoning';
    pre.textContent = JSON.stringify(entry.detail || {}, null, 2);
    wrap.appendChild(pre);
    if (entry.conversation_id) {
      const open = actionButton('Open conversation', () => {
        document.dispatchEvent(new CustomEvent('ora:conversation-selected', {
          detail: { conversation_id: entry.conversation_id, title: entry.name, tag: '' },
        }));
        close();
      }, 'primary');
      const actions = document.createElement('div');
      actions.className = 'ora-review-actions';
      actions.appendChild(open);
      wrap.appendChild(actions);
    }
    return wrap;
  }

  function metaLine(items) {
    const meta = document.createElement('div');
    meta.className = 'ora-review-detail-meta';
    meta.textContent = items.filter(Boolean).join(' · ');
    return meta;
  }

  function actionButton(label, fn, kind = '') {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'ora-settings-btn' + (kind === 'primary' ? ' ora-settings-btn--primary' : '');
    btn.textContent = label;
    btn.addEventListener('click', fn);
    return btn;
  }

  async function markEngagement(entryId, stateName) {
    try {
      await fetch(`/api/oversight/paused/${encodeURIComponent(entryId)}/engagement`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state: stateName }),
      });
    } catch (_) {}
  }

  async function renameEntry(entry) {
    const next = window.prompt('Queue item name:', entry.name || '') || '';
    const trimmed = next.trim();
    if (!trimmed) return;
    try {
      const r = await fetch(`/api/oversight/paused/${encodeURIComponent(entry.id)}/name`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: trimmed }),
      });
      if (!r.ok) throw new Error('Rename failed');
      await refresh();
    } catch (err) {
      setStatus((err && err.message) || String(err), 'error');
    }
  }

  async function quickAction(entry, action, opts = {}) {
    let convId = entry.discussion_conversation_id;
    if (!convId) {
      const created = await createDiscussion(entry.id);
      if (!created) return;
      convId = created.conversation_id;
    }
    if (action === 'deny' && opts.reason) {
      await sendChatTurn(convId, opts.reason);
    }
    await sendChatTurn(convId, action === 'approve' ? '1' : '2');
    await refresh();
  }

  async function createDiscussion(entryId) {
    try {
      const r = await fetch(`/api/oversight/paused/${encodeURIComponent(entryId)}/discuss`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      if (!r.ok) throw new Error('Discussion could not be opened');
      return await r.json();
    } catch (err) {
      setStatus((err && err.message) || String(err), 'error');
      return null;
    }
  }

  async function startDiscussion(entry) {
    const created = await createDiscussion(entry.id);
    if (!created) return;
    openDiscussionConversation(created.conversation_id, entry);
    await refresh();
    close();
  }

  function openDiscussionConversation(conversationId, entry) {
    document.dispatchEvent(new CustomEvent('ora:conversation-selected', {
      detail: {
        conversation_id: conversationId,
        title: entry ? `Resolve: ${esc(entry.name)}` : 'Resolution',
        tag: '',
      },
    }));
  }

  async function sendChatTurn(conversationId, text) {
    await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, conversation_id: conversationId }),
    });
  }

  function ageOf(isoTimestamp) {
    if (!isoTimestamp) return '';
    try {
      const t = new Date(isoTimestamp).getTime();
      const ms = Date.now() - t;
      if (Number.isNaN(ms) || ms < 0) return '';
      const m = Math.floor(ms / 60000);
      if (m < 1) return 'just now';
      if (m < 60) return `${m}m`;
      const h = Math.floor(m / 60);
      if (h < 24) return `${h}h`;
      return `${Math.floor(h / 24)}d`;
    } catch (_) {
      return '';
    }
  }

  function init() {
    const openBtn = document.getElementById('sidebarReviewQueueOpen');
    if (openBtn) openBtn.addEventListener('click', () => open({ tab: 'paused' }));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.OraReviewQueuePanel = { open, close, toggle, refresh };
})();
