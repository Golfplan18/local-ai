/* Project management modal — G1.33 sub-step 5.
 *
 * Full-cover tabbed modal (same shell as the bootstrap "new conversation"
 * popup). Opened from the ⚙ on the sidebar Active-Project row and the
 * "Manage current project" item in the switcher dropdown.
 *
 * Public API
 * ----------
 *   OraProjectModal.open(nexus, name)  — open for a project.
 *   OraProjectModal.close()
 *
 * Tabs:
 *   Overview        — name, status, private + inert model/style/persona slots.
 *   Mission & Goals — MOM read/write against the vault Operation-Matrix.
 *   Files           — placeholder (wired in the next step).
 *   Conversations   — placeholder (membership + restore, next step).
 *
 * Endpoints: GET /api/projects/meta, POST /api/projects/<nexus>,
 *   GET/POST /api/projects/<nexus>/mom.
 */
(() => {
  let modal = null;
  let els = {};
  let current = { nexus: 'general', name: 'General' };
  let momRawMode = false;
  let momCache = null;

  const isGeneral = () => (current.nexus || '').toLowerCase() === 'general';

  const TABS = [
    { id: 'overview', label: 'Overview' },
    { id: 'mom',      label: 'Mission & Goals' },
    { id: 'files',    label: 'Files' },
    { id: 'convos',   label: 'Conversations' },
  ];

  // ── Build (once) ────────────────────────────────────────────────────────
  function build() {
    if (modal) return;
    modal = document.createElement('div');
    modal.className = 'project-modal';
    modal.id = 'projectModal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', 'Manage project');

    const rail = TABS.map((t, i) =>
      `<button type="button" class="project-modal__tab${i === 0 ? ' is-active' : ''}" data-tab="${t.id}">${t.label}</button>`
    ).join('');

    modal.innerHTML = `
      <div class="project-modal__backdrop"></div>
      <div class="project-modal__card">
        <div class="project-modal__header">
          <div class="project-modal__title">
            <span class="project-modal__title-kicker">Manage</span>
            <span class="project-modal__title-name"></span>
          </div>
          <button type="button" class="project-modal__close" aria-label="Close">×</button>
        </div>
        <div class="project-modal__body">
          <div class="project-modal__rail">${rail}</div>
          <div class="project-modal__content">
            ${overviewPanel()}
            ${momPanel()}
            ${placeholderPanel('files', 'A clickable index of the project vault files — open in Obsidian or reveal in Finder — lands in the next step.')}
            ${placeholderPanel('convos', 'Multi-project membership and restoring closed conversations land in the next step.')}
          </div>
        </div>
      </div>`;
    document.body.appendChild(modal);

    els = {
      titleName: modal.querySelector('.project-modal__title-name'),
      tabs:      [...modal.querySelectorAll('.project-modal__tab')],
      panels:    [...modal.querySelectorAll('.project-modal__panel')],
      // overview
      name:      modal.querySelector('#pmName'),
      status:    modal.querySelector('#pmStatus'),
      priv:      modal.querySelector('#pmPrivate'),
      ovSave:    modal.querySelector('#pmOverviewSave'),
      ovMsg:     modal.querySelector('#pmOverviewMsg'),
      // mom
      mission:   modal.querySelector('#pmMission'),
      objectives:modal.querySelector('#pmObjectives'),
      milestones:modal.querySelector('#pmMilestones'),
      momRawWrap:modal.querySelector('#pmMomRawWrap'),
      momRaw:    modal.querySelector('#pmMomRaw'),
      momRawToggle: modal.querySelector('#pmMomRawToggle'),
      momAddBtn: modal.querySelector('#pmMilestoneAdd'),
      momSave:   modal.querySelector('#pmMomSave'),
      momMsg:    modal.querySelector('#pmMomMsg'),
      momNote:   modal.querySelector('#pmMomNote'),
    };

    // Wiring
    modal.querySelector('.project-modal__close').addEventListener('click', close);
    modal.querySelector('.project-modal__backdrop').addEventListener('click', close);
    els.tabs.forEach(t => t.addEventListener('click', () => selectTab(t.dataset.tab)));
    els.ovSave.addEventListener('click', saveOverview);
    els.momSave.addEventListener('click', saveMom);
    els.momAddBtn.addEventListener('click', () => { addMilestoneRow({ text: '', done: false, indent: 0 }); });
    els.momRawToggle.addEventListener('change', toggleMomRaw);

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && modal.classList.contains('show')) {
        e.stopPropagation();
        close();
      }
    }, true);
  }

  function overviewPanel() {
    return `
      <div class="project-modal__panel is-active" data-panel="overview">
        <div class="project-modal__field">
          <label class="project-modal__label" for="pmName">Name</label>
          <input class="project-modal__input" id="pmName" type="text" spellcheck="false" />
          <div class="project-modal__hint">The display label. The internal id (nexus) and vault folder don't change here.</div>
        </div>
        <div class="project-modal__row">
          <div class="project-modal__field">
            <label class="project-modal__label" for="pmStatus">Status</label>
            <select class="project-modal__select" id="pmStatus">
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="archived">Archived</option>
            </select>
            <div class="project-modal__hint">The switcher lists Active projects; Archived are hidden but kept.</div>
          </div>
          <div class="project-modal__field">
            <label class="project-modal__label">Privacy</label>
            <label class="project-modal__checkbox-field">
              <input type="checkbox" id="pmPrivate" />
              Private — files &amp; conversations excluded from retrieval
            </label>
          </div>
        </div>

        <div class="project-modal__fieldset-legend">Defaults</div>
        <div class="project-modal__row">
          <div class="project-modal__field">
            <label class="project-modal__label">Model profile <span class="project-modal__inert-badge">(coming soon)</span></label>
            <select class="project-modal__select" disabled><option>—</option></select>
          </div>
          <div class="project-modal__field">
            <label class="project-modal__label">Persona <span class="project-modal__inert-badge">(coming soon)</span></label>
            <select class="project-modal__select" disabled><option>—</option></select>
          </div>
        </div>
        <div class="project-modal__row">
          <div class="project-modal__field">
            <label class="project-modal__label">Interaction style <span class="project-modal__inert-badge">(coming soon)</span></label>
            <select class="project-modal__select" disabled><option>—</option></select>
          </div>
          <div class="project-modal__field">
            <label class="project-modal__label">Output style <span class="project-modal__inert-badge">(coming soon)</span></label>
            <select class="project-modal__select" disabled><option>—</option></select>
          </div>
        </div>

        <div class="project-modal__actions">
          <div class="project-modal__status" id="pmOverviewMsg"></div>
          <button type="button" class="project-modal__btn project-modal__btn--primary" id="pmOverviewSave">Save</button>
        </div>
      </div>`;
  }

  function momPanel() {
    return `
      <div class="project-modal__panel" data-panel="mom">
        <div class="project-modal__hint" id="pmMomNote" style="margin-bottom:14px"></div>
        <div class="project-modal__field">
          <label class="project-modal__label" for="pmMission">Mission</label>
          <textarea class="project-modal__textarea" id="pmMission" rows="3"
            placeholder="Why this project exists — the durable purpose."></textarea>
        </div>
        <div class="project-modal__field">
          <label class="project-modal__label" for="pmObjectives">Objectives</label>
          <textarea class="project-modal__textarea" id="pmObjectives" rows="3"
            placeholder="What success looks like — the outcomes you're driving toward."></textarea>
        </div>
        <div class="project-modal__field">
          <label class="project-modal__label">
            Milestones
            <label class="project-modal__checkbox-field" style="display:inline-flex;float:right;font-weight:400">
              <input type="checkbox" id="pmMomRawToggle" /> Edit as raw markdown
            </label>
          </label>
          <div class="project-modal__milestones" id="pmMilestones"></div>
          <button type="button" class="project-modal__milestone-add" id="pmMilestoneAdd">+ Add milestone</button>
          <div id="pmMomRawWrap" style="display:none">
            <textarea class="project-modal__textarea" id="pmMomRaw" rows="6"
              placeholder="- [ ] A task&#10;  - [ ] A sub-task&#10;- [x] A done task"></textarea>
            <div class="project-modal__hint">Markdown task lines (<code>- [ ]</code> / <code>- [x]</code>). Use this to keep nested or non-task content the checkboxes can't represent.</div>
          </div>
        </div>
        <div class="project-modal__actions">
          <div class="project-modal__status" id="pmMomMsg"></div>
          <button type="button" class="project-modal__btn project-modal__btn--primary" id="pmMomSave">Save</button>
        </div>
      </div>`;
  }

  function placeholderPanel(id, text) {
    return `<div class="project-modal__panel" data-panel="${id}">
      <div class="project-modal__placeholder">${text}</div>
    </div>`;
  }

  // ── Tabs ────────────────────────────────────────────────────────────────
  function selectTab(id) {
    els.tabs.forEach(t => t.classList.toggle('is-active', t.dataset.tab === id));
    els.panels.forEach(p => p.classList.toggle('is-active', p.dataset.panel === id));
    if (id === 'mom' && momCache === null) loadMom();
  }

  // ── Open / close ─────────────────────────────────────────────────────────
  function setStatus(el, msg, kind) {
    if (!el) return;
    el.textContent = msg || '';
    el.classList.toggle('is-error', kind === 'error');
    el.classList.toggle('is-ok', kind === 'ok');
  }

  async function open(nexus, name) {
    build();
    current = { nexus: nexus || 'general', name: name || nexus || 'General' };
    momRawMode = false; momCache = null;
    els.titleName.textContent = current.name;
    selectTab('overview');
    if (els.momRawToggle) els.momRawToggle.checked = false;
    toggleMomRaw();
    setStatus(els.ovMsg, ''); setStatus(els.momMsg, '');
    modal.classList.add('show');
    await loadOverview();
  }

  function close() {
    if (modal) modal.classList.remove('show');
  }

  // ── Overview ─────────────────────────────────────────────────────────────
  async function loadOverview() {
    const general = isGeneral();
    els.name.value = current.name;
    els.name.disabled = general;
    els.status.disabled = general;
    els.priv.disabled = general;
    els.ovSave.disabled = general;
    if (general) {
      setStatus(els.ovMsg, 'General is the built-in default project and can\'t be configured.');
      return;
    }
    try {
      const r = await fetch('/api/projects/meta');
      const data = await r.json();
      const rec = (data.projects || []).find(p => p.nexus === current.nexus);
      if (rec) {
        els.name.value = rec.name || current.nexus;
        els.status.value = rec.status || 'active';
        els.priv.checked = !!rec.private;
        current.name = els.name.value;
        els.titleName.textContent = current.name;
      }
    } catch (e) {
      setStatus(els.ovMsg, 'Could not load project details.', 'error');
    }
  }

  async function saveOverview() {
    if (isGeneral()) return;
    const body = {
      name: (els.name.value || '').trim(),
      status: els.status.value,
      private: !!els.priv.checked,
    };
    if (!body.name) { setStatus(els.ovMsg, 'Name can\'t be empty.', 'error'); return; }
    els.ovSave.disabled = true;
    setStatus(els.ovMsg, 'Saving…');
    try {
      const r = await fetch('/api/projects/' + encodeURIComponent(current.nexus), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (data && data.ok) {
        current.name = data.project.name;
        els.titleName.textContent = current.name;
        setStatus(els.ovMsg, 'Saved.', 'ok');
        // Refresh the sidebar switcher so the new name/status/badges show.
        try { window.OraSidebar && window.OraSidebar.refreshProjects && window.OraSidebar.refreshProjects(); } catch (e) {}
      } else {
        setStatus(els.ovMsg, (data && data.error) || 'Save failed.', 'error');
      }
    } catch (e) {
      setStatus(els.ovMsg, 'Save failed: ' + (e.message || e), 'error');
    } finally {
      els.ovSave.disabled = isGeneral();
    }
  }

  // ── Mission / Objectives / Milestones ─────────────────────────────────────
  function addMilestoneRow(m) {
    const row = document.createElement('div');
    row.className = 'project-modal__milestone';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = !!m.done;
    const text = document.createElement('input');
    text.type = 'text';
    text.className = 'project-modal__milestone-text' + (m.done ? ' is-done' : '');
    text.value = m.text || '';
    text.placeholder = 'A milestone…';
    text.style.marginLeft = (Math.max(0, m.indent || 0) * 16) + 'px';
    cb.addEventListener('change', () => text.classList.toggle('is-done', cb.checked));
    const rm = document.createElement('button');
    rm.type = 'button';
    rm.className = 'project-modal__milestone-remove';
    rm.textContent = '×';
    rm.setAttribute('aria-label', 'Remove milestone');
    rm.addEventListener('click', () => row.remove());
    row.appendChild(cb);
    row.appendChild(text);
    row.appendChild(rm);
    row._indent = Math.max(0, m.indent || 0);
    els.milestones.appendChild(row);
    return row;
  }

  function renderMilestones(list) {
    els.milestones.innerHTML = '';
    (list || []).forEach(addMilestoneRow);
  }

  function collectMilestones() {
    return [...els.milestones.querySelectorAll('.project-modal__milestone')]
      .map(row => ({
        text: row.querySelector('.project-modal__milestone-text').value.trim(),
        done: row.querySelector('input[type="checkbox"]').checked,
        indent: row._indent || 0,
      }))
      .filter(m => m.text);
  }

  function toggleMomRaw() {
    momRawMode = !!(els.momRawToggle && els.momRawToggle.checked);
    if (els.momRawWrap) els.momRawWrap.style.display = momRawMode ? '' : 'none';
    if (els.milestones) els.milestones.style.display = momRawMode ? 'none' : '';
    if (els.momAddBtn) els.momAddBtn.style.display = momRawMode ? 'none' : '';
    // When switching INTO raw mode, seed the textarea from the checkboxes.
    if (momRawMode && els.momRaw && !els.momRaw.value.trim()) {
      els.momRaw.value = collectMilestones()
        .map(m => `${'  '.repeat(m.indent)}- [${m.done ? 'x' : ' '}] ${m.text}`)
        .join('\n');
    }
  }

  async function loadMom() {
    if (isGeneral()) {
      momCache = {};
      setStatus(els.momNote, '');
      els.momNote.textContent = 'General has no Operation-Matrix. Create a project to set a Mission, Objectives, and Milestones.';
      [els.mission, els.objectives, els.momRaw].forEach(e => { if (e) { e.value = ''; e.disabled = true; } });
      if (els.momSave) els.momSave.disabled = true;
      if (els.momAddBtn) els.momAddBtn.disabled = true;
      renderMilestones([]);
      return;
    }
    [els.mission, els.objectives, els.momRaw].forEach(e => { if (e) e.disabled = false; });
    if (els.momSave) els.momSave.disabled = false;
    if (els.momAddBtn) els.momAddBtn.disabled = false;
    setStatus(els.momMsg, 'Loading…');
    try {
      const r = await fetch('/api/projects/' + encodeURIComponent(current.nexus)
        + '/mom?name=' + encodeURIComponent(current.name));
      const data = await r.json();
      const mom = (data && data.mom) || {};
      momCache = mom;
      els.mission.value = mom.mission || '';
      els.objectives.value = mom.objectives || '';
      renderMilestones(mom.milestones || []);
      els.momNote.textContent = mom.exists
        ? ''
        : 'No Operation-Matrix file yet — saving creates Matrix/Project Matrix ' + current.name + '.md in the vault.';
      setStatus(els.momMsg, '');
    } catch (e) {
      momCache = {};
      setStatus(els.momMsg, 'Could not load Mission/Objectives/Milestones.', 'error');
    }
  }

  async function saveMom() {
    if (isGeneral()) return;
    const body = {
      name: current.name,
      mission: els.mission.value,
      objectives: els.objectives.value,
    };
    if (momRawMode) body.milestones_raw = els.momRaw.value;
    else body.milestones = collectMilestones();
    els.momSave.disabled = true;
    setStatus(els.momMsg, 'Saving…');
    try {
      const r = await fetch('/api/projects/' + encodeURIComponent(current.nexus) + '/mom', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (data && data.ok) {
        momCache = data.mom;
        // Re-render from the canonical re-read so checkbox/raw stay in sync.
        if (!momRawMode) renderMilestones(data.mom.milestones || []);
        els.momNote.textContent = '';
        setStatus(els.momMsg, 'Saved to the vault Operation-Matrix.', 'ok');
      } else {
        setStatus(els.momMsg, (data && data.error) || 'Save failed.', 'error');
      }
    } catch (e) {
      setStatus(els.momMsg, 'Save failed: ' + (e.message || e), 'error');
    } finally {
      els.momSave.disabled = false;
    }
  }

  window.OraProjectModal = { open, close };
})();
