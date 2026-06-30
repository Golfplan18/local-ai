/* Output-pane export toolbar — G1.34 (§2.7).
 *
 * A disappearing lower-right I/O cluster on the output pane: one Export button
 * that expands a submenu (Save output / Save full conversation to Vault;
 * Word/PDF deferred to the bundled-Pandoc step) plus a Print… item → the OS
 * print dialog. Reveal-on-hover, per the Zen toolbar convention.
 *
 * Markdown is canonical: "Save to Vault" writes a markdown note (into the
 * active project's folder when set) via POST /api/export. The current output's
 * raw markdown comes from window.OraConversation.getCurrentTurn().
 */
(() => {
  const mount = () => {
    const pane = document.querySelector('.output-pane');
    if (!pane || pane.querySelector('.export-toolbar')) return;

    const bar = document.createElement('div');
    bar.className = 'export-toolbar';
    bar.innerHTML = `
      <div class="export-toolbar__status" id="exportToolbarStatus" aria-live="polite"></div>
      <button type="button" class="export-toolbar__btn" id="exportPrintBtn" title="Print…">
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <polyline points="6 9 6 2 18 2 18 9"/>
          <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>
          <rect x="6" y="14" width="12" height="8"/>
        </svg>
      </button>
      <div class="export-toolbar__exportwrap">
        <button type="button" class="export-toolbar__btn export-toolbar__export" id="exportMenuBtn"
                aria-haspopup="true" aria-expanded="false" title="Export">
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          <span>Export</span>
        </button>
        <div class="export-toolbar__menu" id="exportMenu" role="menu" hidden>
          <button type="button" class="export-toolbar__item" role="menuitem" data-action="output">Save output to Vault</button>
          <button type="button" class="export-toolbar__item" role="menuitem" data-action="conversation">Save full conversation</button>
          <div class="export-toolbar__sep"></div>
          <button type="button" class="export-toolbar__item is-disabled" role="menuitem" disabled title="Arrives with the bundled Pandoc step">Word (.docx) — soon</button>
          <button type="button" class="export-toolbar__item is-disabled" role="menuitem" disabled title="Arrives with the bundled Pandoc step">PDF — soon</button>
        </div>
      </div>`;
    pane.appendChild(bar);

    const statusEl = bar.querySelector('#exportToolbarStatus');
    const menuBtn  = bar.querySelector('#exportMenuBtn');
    const menu     = bar.querySelector('#exportMenu');
    const printBtn = bar.querySelector('#exportPrintBtn');

    let statusTimer = null;
    const setStatus = (msg, revealPath) => {
      statusEl.innerHTML = '';
      if (!msg) return;
      const span = document.createElement('span');
      span.textContent = msg;
      statusEl.appendChild(span);
      if (revealPath) {
        const a = document.createElement('button');
        a.type = 'button';
        a.className = 'export-toolbar__reveal';
        a.textContent = 'Reveal';
        a.addEventListener('click', () => revealInFinder(revealPath));
        statusEl.appendChild(a);
      }
      if (statusTimer) clearTimeout(statusTimer);
      statusTimer = setTimeout(() => { statusEl.innerHTML = ''; }, 9000);
    };

    const closeMenu = () => { menu.hidden = true; menuBtn.setAttribute('aria-expanded', 'false'); bar.classList.remove('is-open'); };
    const openMenu  = () => { menu.hidden = false; menuBtn.setAttribute('aria-expanded', 'true'); bar.classList.add('is-open'); };
    menuBtn.addEventListener('click', (e) => { e.stopPropagation(); menu.hidden ? openMenu() : closeMenu(); });
    document.addEventListener('click', (e) => { if (!bar.contains(e.target)) closeMenu(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeMenu(); });

    printBtn.addEventListener('click', () => { try { window.print(); } catch (e) {} });

    menu.querySelectorAll('.export-toolbar__item[data-action]').forEach(item => {
      item.addEventListener('click', () => { closeMenu(); runExport(item.dataset.action, setStatus); });
    });
  };

  const firstHeading = (md) => {
    for (const line of (md || '').split('\n')) {
      const s = line.trim().replace(/^#+\s*/, '').trim();
      if (s) return s.slice(0, 80);
    }
    return '';
  };

  async function runExport(action, setStatus) {
    const conv = window.OraConversation;
    if (action === 'output') {
      const turn = conv && typeof conv.getCurrentTurn === 'function' ? conv.getCurrentTurn() : null;
      const content = turn && turn.assistant ? (turn.assistant.content || '') : '';
      if (!content.trim()) { setStatus('Nothing to save in this output.'); return; }
      setStatus('Saving…');
      await postExport({ scope: 'current_output', content, title: firstHeading(content) }, setStatus);
    } else if (action === 'conversation') {
      const cid = conv && typeof conv.getActiveConversationId === 'function' ? conv.getActiveConversationId() : null;
      if (!cid) { setStatus('No conversation to save.'); return; }
      setStatus('Saving conversation…');
      await postExport({ scope: 'full_conversation', conversation_id: cid }, setStatus);
    }
  }

  async function postExport(body, setStatus) {
    try {
      const r = await fetch('/api/export', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (data && data.ok && data.path) {
        const name = data.path.split('/').pop();
        setStatus('Saved ' + name, data.path);
      } else {
        setStatus((data && data.error) || 'Export failed.');
      }
    } catch (e) {
      setStatus('Export failed: ' + (e.message || e));
    }
  }

  async function revealInFinder(path) {
    try {
      await fetch('/api/fs/reveal', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
    } catch (e) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
})();
