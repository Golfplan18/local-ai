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
 *   Mission & Goals — MOM read/write against the vault Operation-Matrix (+ AI draft).
 *   Files           — read-only index of the project vault folder → Obsidian / OS file manager.
 *   Conversations   — membership (add/remove), restore closed.
 *
 * Endpoints: GET /api/projects/meta, POST /api/projects/<nexus>,
 *   GET/POST /api/projects/<nexus>/mom, POST /api/projects/<nexus>/mom-assist,
 *   GET /api/projects/<nexus>/files, POST /api/fs/reveal,
 *   GET /api/projects/<nexus>/conversations[?candidates&q&include_closed],
 *   POST /api/conversation/<id>/projects, POST /api/conversation/<id>/restore.
 */
(() => {
  let modal = null;
  let els = {};
  let current = { nexus: 'commons', name: 'Commons' };
  let momRawMode = false;
  let momCache = null;
  let filesCache = null;
  let convosCache = null;
  let candidateSearchTimer = null;
  let configsCache = null;   // /api/configurations profile names
  let stylesCache = null;    // /api/styles/registry profiles
  let mode = 'edit';  // 'edit' | 'create'
  let pendingNexus = null;  // a previewed nexus rename awaiting Apply

  const canonicalProjectId = (nexus) => {
    const slug = String(nexus || '').trim();
    return (!slug || ['commons', 'general'].includes(slug.toLowerCase())) ? 'commons' : slug;
  };
  // Project ids embedded in URL path segments cannot use the version-neutral
  // blank representation. Both current and pre-rename servers recognize the
  // legacy default id, so use `general` for Commons on the wire.
  const compatibleProjectPathId = (nexus) =>
    canonicalProjectId(nexus) === 'commons' ? 'general' : canonicalProjectId(nexus);
  const canonicalProjectRecordId = (project) =>
    canonicalProjectId(project && (project.canonical_nexus || project.nexus));
  // "general" was the pre-2026-07-11 id; still recognized permanently.
  const isCommons = () => canonicalProjectId(current.nexus) === 'commons';

  const TABS = [
    { id: 'overview', label: 'Overview' },
    { id: 'mom',      label: 'Mission & Goals' },
    { id: 'files',    label: 'Files' },
    { id: 'convos',   label: 'Dialogues' },
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
            ${filesPanel()}
            ${convosPanel()}
          </div>
        </div>
      </div>`;
    document.body.appendChild(modal);

    els = {
      titleKicker: modal.querySelector('.project-modal__title-kicker'),
      titleName: modal.querySelector('.project-modal__title-name'),
      tabs:      [...modal.querySelectorAll('.project-modal__tab')],
      panels:    [...modal.querySelectorAll('.project-modal__panel')],
      // overview
      name:      modal.querySelector('#pmName'),
      status:    modal.querySelector('#pmStatus'),
      priv:      modal.querySelector('#pmPrivate'),
      ovSave:    modal.querySelector('#pmOverviewSave'),
      ovMsg:     modal.querySelector('#pmOverviewMsg'),
      modelProfile: modal.querySelector('#pmModelProfile'),
      outputStyle:  modal.querySelector('#pmOutputStyle'),
      interactionStyle: modal.querySelector('#pmInteractionStyle'),
      advanced:  modal.querySelector('#pmAdvanced'),
      nexus:     modal.querySelector('#pmNexus'),
      nexusPreview: modal.querySelector('#pmNexusPreview'),
      nexusApply: modal.querySelector('#pmNexusApply'),
      nexusMsg:  modal.querySelector('#pmNexusMsg'),
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
      momAssist: modal.querySelector('#pmMomAssist'),
      momIntent: modal.querySelector('#pmMomIntent'),
      // files
      filesNote: modal.querySelector('#pmFilesNote'),
      fileList:  modal.querySelector('#pmFileList'),
      filesRefresh: modal.querySelector('#pmFilesRefresh'),
      // conversations
      convosClosed: modal.querySelector('#pmConvosClosed'),
      convosMsg: modal.querySelector('#pmConvosMsg'),
      convoList: modal.querySelector('#pmConvoList'),
      convoAddWrap: modal.querySelector('#pmConvoAddWrap'),
      convoSearch: modal.querySelector('#pmConvoSearch'),
      convoAddList: modal.querySelector('#pmConvoAddList'),
    };

    // Wiring
    modal.querySelector('.project-modal__close').addEventListener('click', close);
    modal.querySelector('.project-modal__backdrop').addEventListener('click', close);
    els.tabs.forEach(t => t.addEventListener('click', () => selectTab(t.dataset.tab)));
    els.ovSave.addEventListener('click', saveOverview);
    if (els.nexusPreview) els.nexusPreview.addEventListener('click', previewNexus);
    if (els.nexusApply) els.nexusApply.addEventListener('click', applyNexus);
    if (els.nexus) els.nexus.addEventListener('input', () => {
      pendingNexus = null;
      if (els.nexusApply) els.nexusApply.style.display = 'none';
    });
    els.momSave.addEventListener('click', saveMom);
    els.momAddBtn.addEventListener('click', () => { addMilestoneRow({ text: '', done: false, indent: 0 }); });
    els.momRawToggle.addEventListener('change', toggleMomRaw);
    els.momAssist.addEventListener('click', assistMom);
    if (els.filesRefresh) els.filesRefresh.addEventListener('click', () => { filesCache = null; loadFiles(); });
    if (els.convosClosed) els.convosClosed.addEventListener('change', () => { convosCache = null; loadConvos(); });
    if (els.convoSearch) els.convoSearch.addEventListener('input', scheduleCandidateSearch);

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
              Private — files &amp; Dialogues excluded from retrieval
            </label>
          </div>
        </div>

        <div class="project-modal__fieldset-legend">Defaults</div>
        <div class="project-modal__row">
          <div class="project-modal__field">
            <label class="project-modal__label" for="pmModelProfile">Model profile</label>
            <select class="project-modal__select" id="pmModelProfile"></select>
            <div class="project-modal__hint">The default execution profile for this project's runs (a per-run pick still overrides it).</div>
          </div>
          <div class="project-modal__field">
            <label class="project-modal__label">Persona <span class="project-modal__inert-badge">(coming soon)</span></label>
            <select class="project-modal__select" disabled><option>—</option></select>
          </div>
        </div>
        <div class="project-modal__row">
          <div class="project-modal__field">
            <label class="project-modal__label" for="pmOutputStyle">Output style</label>
            <select class="project-modal__select" id="pmOutputStyle"></select>
            <div class="project-modal__hint">How this project's deliverables read to the world.</div>
          </div>
          <div class="project-modal__field">
            <label class="project-modal__label" for="pmInteractionStyle">Interaction style <span class="project-modal__inert-badge">(stored; not yet applied)</span></label>
            <select class="project-modal__select" id="pmInteractionStyle"></select>
            <div class="project-modal__hint">How Ora talks to you here (the honne/tatemae split lands with the persona work).</div>
          </div>
        </div>

        <div class="project-modal__actions">
          <div class="project-modal__status" id="pmOverviewMsg"></div>
          <button type="button" class="project-modal__btn project-modal__btn--primary" id="pmOverviewSave">Save</button>
        </div>

        <details class="project-modal__advanced" id="pmAdvanced">
          <summary>Advanced</summary>
          <div class="project-modal__field" style="margin-top:12px">
            <label class="project-modal__label" for="pmNexus">Internal id (nexus)</label>
            <div class="project-modal__assist-row">
              <div class="project-modal__assist-input">
                <input class="project-modal__input" id="pmNexus" type="text" spellcheck="false" autocomplete="off" />
              </div>
              <button type="button" class="project-modal__btn" id="pmNexusPreview">Preview impact</button>
            </div>
            <div class="project-modal__hint">Renaming the nexus rewrites it in every vault file's frontmatter and in Dialogue memberships. Preview the impact first; this cannot be auto-undone (the vault's git auto-commit is the safety net).</div>
            <div class="project-modal__status" id="pmNexusMsg"></div>
            <button type="button" class="project-modal__btn project-modal__btn--danger" id="pmNexusApply" style="display:none;margin-top:8px">Apply rename</button>
          </div>
        </details>
      </div>`;
  }

  function momPanel() {
    return `
      <div class="project-modal__panel" data-panel="mom">
        <div class="project-modal__hint" id="pmMomNote" style="margin-bottom:14px"></div>
        <div class="project-modal__field">
          <div class="project-modal__assist-row">
            <div class="project-modal__assist-input">
              <label class="project-modal__label" for="pmMomIntent">Draft with AI <span style="font-weight:400;color:var(--text-faint)">(optional hint)</span></label>
              <input class="project-modal__input" id="pmMomIntent" type="text"
                placeholder="e.g. a weekly solo-builder podcast, ships Mondays" />
            </div>
            <button type="button" class="project-modal__btn project-modal__btn--assist" id="pmMomAssist">Draft with AI</button>
          </div>
          <div class="project-modal__hint">Fills Mission, Objectives, and Milestones below for you to review and edit. Nothing is saved until you click Save.</div>
        </div>
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

  function filesPanel() {
    return `
      <div class="project-modal__panel" data-panel="files">
        <div class="project-modal__listhead">
          <div class="project-modal__hint" id="pmFilesNote"></div>
          <button type="button" class="project-modal__btn" id="pmFilesRefresh">Refresh</button>
        </div>
        <div class="project-modal__filelist" id="pmFileList"></div>
      </div>`;
  }

  function convosPanel() {
    return `
      <div class="project-modal__panel" data-panel="convos">
        <div class="project-modal__listhead">
          <label class="project-modal__checkbox-field"><input type="checkbox" id="pmConvosClosed"> Show closed</label>
          <div class="project-modal__status" id="pmConvosMsg"></div>
        </div>
        <div class="project-modal__convo-section-label">In this project</div>
        <div class="project-modal__convolist" id="pmConvoList"></div>
        <div id="pmConvoAddWrap">
          <div class="project-modal__convo-section-label">Add a Dialogue</div>
          <input class="project-modal__input" id="pmConvoSearch" type="text"
            placeholder="Search Dialogues by title to add…" autocomplete="off" spellcheck="false" />
          <div class="project-modal__convolist" id="pmConvoAddList"></div>
        </div>
      </div>`;
  }

  // ── Tabs ────────────────────────────────────────────────────────────────
  function showTab(id) {
    els.tabs.forEach(t => t.classList.toggle('is-active', t.dataset.tab === id));
    els.panels.forEach(p => p.classList.toggle('is-active', p.dataset.panel === id));
  }

  function selectTab(id) {
    // In create mode only Overview is reachable until the project exists.
    if (mode === 'create' && id !== 'overview') return;
    showTab(id);
    if (id === 'mom' && momCache === null) loadMom();
    if (id === 'files' && filesCache === null) loadFiles();
    if (id === 'convos' && convosCache === null) loadConvos();
  }

  // Reflect create-vs-edit mode in the header, the Overview primary button,
  // and which tabs are reachable.
  function applyMode() {
    const creating = mode === 'create';
    if (els.titleKicker) els.titleKicker.textContent = creating ? 'New' : 'Manage';
    if (els.ovSave) els.ovSave.textContent = creating ? 'Create project' : 'Save';
    els.tabs.forEach(t => {
      if (t.dataset.tab === 'overview') return;
      t.classList.toggle('is-disabled', creating);
      t.disabled = creating;
    });
  }

  // ── Open / close ─────────────────────────────────────────────────────────
  function setStatus(el, msg, kind) {
    if (!el) return;
    el.textContent = msg || '';
    el.classList.toggle('is-error', kind === 'error');
    el.classList.toggle('is-ok', kind === 'ok');
  }

  function resetTransient() {
    momRawMode = false; momCache = null; filesCache = null; convosCache = null;
    if (els.momIntent) els.momIntent.value = '';
    if (els.convoSearch) els.convoSearch.value = '';
    if (els.convosClosed) els.convosClosed.checked = false;
    if (els.convoAddList) els.convoAddList.innerHTML = '';
    if (els.momRawToggle) els.momRawToggle.checked = false;
  }

  // MOM-guided creation (graceful): name the project, create the record +
  // vault folder, then land on Mission & Goals so the user is invited — never
  // forced — to author MOM (with the AI assist). Closing anytime is fine.
  async function openCreate() {
    build();
    mode = 'create';
    current = { nexus: null, name: '' };
    resetTransient();
    applyMode();
    showTab('overview');
    els.name.value = '';
    els.name.disabled = false;
    els.status.value = 'active';
    els.status.disabled = true;   // new projects start active
    els.priv.checked = false;
    els.priv.disabled = false;
    els.ovSave.disabled = false;
    if (els.advanced) els.advanced.style.display = 'none';  // no nexus until created
    [els.modelProfile, els.outputStyle, els.interactionStyle].forEach(s => { if (s) s.disabled = false; });
    populateDefaults({});  // empty registries selection for a fresh project
    toggleMomRaw();
    setStatus(els.ovMsg, 'Name your project. You can set Mission, Objectives & Milestones next — or skip it.');
    setStatus(els.momMsg, '');
    els.titleName.textContent = 'project';
    modal.classList.add('show');
    setTimeout(() => { try { els.name.focus(); } catch (e) {} }, 0);
  }

  async function open(nexus, name) {
    build();
    mode = 'edit';
    const canonicalNexus = canonicalProjectId(nexus);
    current = { nexus: canonicalNexus, name: name || (canonicalNexus === 'commons' ? 'Commons' : canonicalNexus) };
    resetTransient();
    applyMode();
    els.titleName.textContent = current.name;
    selectTab('overview');
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
    const general = isCommons();
    els.name.value = current.name;
    els.name.disabled = general;
    els.status.disabled = general;
    els.priv.disabled = general;
    els.ovSave.disabled = general;
    // Advanced (nexus rename) — edit mode, real projects only.
    pendingNexus = null;
    if (els.nexusApply) els.nexusApply.style.display = 'none';
    setStatus(els.nexusMsg, '');
    if (els.advanced) {
      els.advanced.style.display = general ? 'none' : '';
      els.advanced.open = false;
    }
    if (els.nexus) els.nexus.value = general ? '' : current.nexus;
    [els.modelProfile, els.outputStyle, els.interactionStyle].forEach(s => { if (s) s.disabled = general; });
    if (general) {
      setStatus(els.ovMsg, 'Commons is the built-in default project and can\'t be configured.');
      return;
    }
    try {
      const r = await fetch('/api/projects/meta');
      const data = await r.json();
      const rec = (data.projects || []).find(p => canonicalProjectRecordId(p) === current.nexus);
      if (rec) {
        els.name.value = rec.name || current.nexus;
        els.status.value = rec.status || 'active';
        els.priv.checked = !!rec.private;
        current.name = els.name.value;
        els.titleName.textContent = current.name;
      }
      await populateDefaults(rec || {});
    } catch (e) {
      setStatus(els.ovMsg, 'Could not load project details.', 'error');
    }
  }

  // ── Execution defaults (model profile + styles) ──────────────────────────
  function _fillSelect(sel, items, currentValue, emptyLabel) {
    if (!sel) return;
    sel.innerHTML = '';
    const none = document.createElement('option');
    none.value = '';
    none.textContent = emptyLabel;
    sel.appendChild(none);
    items.forEach(it => {
      const o = document.createElement('option');
      o.value = it.value;
      o.textContent = it.label;
      sel.appendChild(o);
    });
    sel.value = currentValue || '';
    // If the stored value is no longer available, keep it visible so a Save
    // doesn't silently drop it.
    if ((currentValue || '') && sel.value !== currentValue) {
      const o = document.createElement('option');
      o.value = currentValue;
      o.textContent = currentValue + ' (unavailable)';
      sel.appendChild(o);
      sel.value = currentValue;
    }
  }

  async function _ensureRegistries() {
    if (configsCache === null) {
      try {
        const d = await (await fetch('/api/configurations')).json();
        const names = [
          ...Object.keys((d && d.presets) || {}),
          ...Object.keys((d && d.customs) || {}),
        ];
        configsCache = names.map(n => ({ value: n, label: n }));
      } catch (e) { configsCache = []; }
    }
    if (stylesCache === null) {
      try {
        const d = await (await fetch('/api/styles/registry')).json();
        const profiles = (d && d.profiles) || [];
        stylesCache = profiles.map(p => ({
          value: p.id, label: p.display_name || p.id,
        }));
      } catch (e) { stylesCache = []; }
    }
  }

  async function populateDefaults(rec) {
    await _ensureRegistries();
    _fillSelect(els.modelProfile, configsCache, rec.default_model_profile, '— Global default —');
    _fillSelect(els.outputStyle, stylesCache, rec.output_style, '— None —');
    _fillSelect(els.interactionStyle, stylesCache, rec.interaction_style, '— None —');
  }

  async function saveOverview() {
    if (mode === 'create') { createProject(); return; }
    if (isCommons()) return;
    const body = {
      name: (els.name.value || '').trim(),
      status: els.status.value,
      private: !!els.priv.checked,
      default_model_profile: (els.modelProfile && els.modelProfile.value) || '',
      output_style: (els.outputStyle && els.outputStyle.value) || '',
      interaction_style: (els.interactionStyle && els.interactionStyle.value) || '',
    };
    if (!body.name) { setStatus(els.ovMsg, 'Name can\'t be empty.', 'error'); return; }
    els.ovSave.disabled = true;
    setStatus(els.ovMsg, 'Saving…');
    try {
      const r = await fetch('/api/projects/' + encodeURIComponent(compatibleProjectPathId(current.nexus)), {
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
      els.ovSave.disabled = isCommons();
    }
  }

  async function createProject() {
    const name = (els.name.value || '').trim();
    if (!name) { setStatus(els.ovMsg, 'Give the project a name.', 'error'); return; }
    els.ovSave.disabled = true;
    setStatus(els.ovMsg, 'Creating…');
    try {
      const r = await fetch('/api/projects/create', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      const data = await r.json();
      if (!(data && data.ok && data.project)) {
        setStatus(els.ovMsg, (data && data.error) || 'Could not create the project.', 'error');
        els.ovSave.disabled = false;
        return;
      }
      current = { nexus: data.project.nexus, name: data.project.name };
      // Apply the private flag if the user set it at creation.
      if (els.priv.checked) {
        try {
          await fetch('/api/projects/' + encodeURIComponent(compatibleProjectPathId(current.nexus)), {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ private: true }),
          });
        } catch (e) {}
      }
      // Transition to edit mode and make this the active project.
      mode = 'edit';
      applyMode();
      els.status.disabled = false;
      // Advanced (nexus rename) was hidden during create — reveal it now that
      // the project exists, seeded with its new nexus.
      if (els.advanced) els.advanced.style.display = '';
      if (els.nexus) els.nexus.value = current.nexus;
      els.titleName.textContent = current.name;
      setStatus(els.ovMsg, 'Project created' + (data.vault_folder ? ' — folder added to the vault.' : '.'), 'ok');
      try { window.OraSidebar && window.OraSidebar.refreshProjects && window.OraSidebar.refreshProjects(); } catch (e) {}
      try { window.OraSidebar && window.OraSidebar.setActiveProject && window.OraSidebar.setActiveProject(current.nexus, current.name); } catch (e) {}
      // Guide (don't force) the user into MOM — the graceful creation flow.
      showTab('mom');
      momCache = null;
      await loadMom();
      setStatus(els.momMsg, 'Optional: draft your Mission, Objectives & Milestones now — or just close. You can edit anytime.');
    } catch (e) {
      setStatus(els.ovMsg, 'Could not create the project: ' + (e.message || e), 'error');
      els.ovSave.disabled = false;
    }
  }

  // ── Advanced: rename the nexus (bulk-YAML cascade, preview → apply) ───────
  async function previewNexus() {
    if (isCommons() || mode === 'create') return;
    const next = (els.nexus.value || '').trim().toLowerCase();
    if (els.nexusApply) els.nexusApply.style.display = 'none';
    pendingNexus = null;
    if (!next || next === current.nexus) {
      setStatus(els.nexusMsg, 'Enter a different id to preview.', 'error');
      return;
    }
    els.nexusPreview.disabled = true;
    setStatus(els.nexusMsg, 'Checking impact…');
    try {
      const r = await fetch('/api/projects/' + encodeURIComponent(compatibleProjectPathId(current.nexus)) + '/rename-nexus', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_nexus: next, dry_run: true }),
      });
      const data = await r.json();
      if (!(data && data.ok)) {
        setStatus(els.nexusMsg, (data && data.error) || 'Preview failed.', 'error');
        return;
      }
      const rep = data.report;
      pendingNexus = next;
      setStatus(els.nexusMsg,
        `Will rewrite ${rep.vault_file_count} vault file${rep.vault_file_count === 1 ? '' : 's'} `
        + `and ${rep.conversation_count} Dialogue${rep.conversation_count === 1 ? '' : 's'}.`);
      if (els.nexusApply) {
        els.nexusApply.style.display = '';
        els.nexusApply.textContent = `Apply rename → ${next}`;
      }
    } catch (e) {
      setStatus(els.nexusMsg, 'Preview failed: ' + (e.message || e), 'error');
    } finally {
      els.nexusPreview.disabled = false;
    }
  }

  async function applyNexus() {
    if (!pendingNexus || isCommons()) return;
    const from = current.nexus, to = pendingNexus;
    if (!confirm(`Rename the internal id from "${from}" to "${to}"? This rewrites the nexus across the vault and Dialogue memberships and cannot be auto-undone.`)) {
      return;
    }
    els.nexusApply.disabled = true;
    setStatus(els.nexusMsg, 'Renaming…');
    try {
      const r = await fetch('/api/projects/' + encodeURIComponent(from) + '/rename-nexus', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_nexus: to, dry_run: false }),
      });
      const data = await r.json();
      if (!(data && data.ok)) {
        setStatus(els.nexusMsg, (data && data.error) || 'Rename failed.', 'error');
        return;
      }
      const rep = data.report;
      current.nexus = to;
      pendingNexus = null;
      els.nexusApply.style.display = 'none';
      const errs = (rep.errors || []).length;
      setStatus(els.nexusMsg,
        `Renamed — ${rep.vault_file_count} file${rep.vault_file_count === 1 ? '' : 's'}, `
        + `${rep.conversation_count} Dialogue${rep.conversation_count === 1 ? '' : 's'}`
        + (errs ? `, ${errs} error${errs === 1 ? '' : 's'}.` : '.'),
        errs ? 'error' : 'ok');
      // Re-point everything at the new id.
      try { window.OraSidebar && window.OraSidebar.setActiveProject && window.OraSidebar.setActiveProject(to, current.name); } catch (e) {}
      try { window.OraSidebar && window.OraSidebar.refreshProjects && window.OraSidebar.refreshProjects(); } catch (e) {}
      try { window.OraSidebar && window.OraSidebar.refresh && window.OraSidebar.refresh(); } catch (e) {}
      // Force the other tabs to reload against the new nexus next time.
      momCache = null; filesCache = null; convosCache = null;
    } catch (e) {
      setStatus(els.nexusMsg, 'Rename failed: ' + (e.message || e), 'error');
    } finally {
      els.nexusApply.disabled = false;
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
    if (isCommons()) {
      momCache = {};
      setStatus(els.momNote, '');
      els.momNote.textContent = 'Commons has no Operation-Matrix. Create a project to set a Mission, Objectives, and Milestones.';
      [els.mission, els.objectives, els.momRaw, els.momIntent].forEach(e => { if (e) { e.value = ''; e.disabled = true; } });
      if (els.momSave) els.momSave.disabled = true;
      if (els.momAddBtn) els.momAddBtn.disabled = true;
      if (els.momAssist) els.momAssist.disabled = true;
      renderMilestones([]);
      return;
    }
    [els.mission, els.objectives, els.momRaw, els.momIntent].forEach(e => { if (e) e.disabled = false; });
    if (els.momSave) els.momSave.disabled = false;
    if (els.momAddBtn) els.momAddBtn.disabled = false;
    if (els.momAssist) els.momAssist.disabled = false;
    setStatus(els.momMsg, 'Loading…');
    try {
      const r = await fetch('/api/projects/' + encodeURIComponent(compatibleProjectPathId(current.nexus))
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

  async function assistMom() {
    if (isCommons()) return;
    // Clobber guard — the assist DRAFTS into the fields; confirm before
    // overwriting existing content (checked against the SAME sources saveMom
    // reads, so raw vs checkbox mode is honored).
    const hasContent = els.mission.value.trim() || els.objectives.value.trim()
      || (momRawMode ? els.momRaw.value.trim() : collectMilestones().length);
    if (hasContent && !confirm(
      'Replace the current Mission, Objectives, and Milestones with an AI draft? Your unsaved edits will be overwritten.')) {
      return;
    }
    const prev = els.momAssist.textContent;
    els.momAssist.disabled = true;
    els.momSave.disabled = true;
    els.momAssist.textContent = 'Drafting…';
    setStatus(els.momMsg, 'Drafting with AI…');
    try {
      const r = await fetch('/api/projects/' + encodeURIComponent(compatibleProjectPathId(current.nexus)) + '/mom-assist', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: current.name,
          intent: (els.momIntent.value || '').trim(),
          fields: {
            mission: els.mission.value,
            objectives: els.objectives.value,
            milestones_raw: momRawMode ? els.momRaw.value
              : collectMilestones().map(m => `${'  '.repeat(m.indent)}- [${m.done ? 'x' : ' '}] ${m.text}`).join('\n'),
          },
        }),
      });
      const data = await r.json();
      if (data && data.ok && data.suggestions) {
        const s = data.suggestions;
        els.mission.value = s.mission || '';
        els.objectives.value = s.objectives || '';
        // Honor the current editing mode — fill exactly one of the two views.
        if (momRawMode) els.momRaw.value = s.milestones_raw || '';
        else renderMilestones(s.milestones || []);
        setStatus(els.momMsg, 'Drafted — review and edit, then Save.', 'ok');
      } else {
        setStatus(els.momMsg, (data && data.error) || 'Drafting failed.', 'error');
      }
    } catch (e) {
      setStatus(els.momMsg, 'Drafting failed: ' + (e.message || e), 'error');
    } finally {
      els.momAssist.disabled = false;
      els.momSave.disabled = false;
      els.momAssist.textContent = prev;
    }
  }

  async function saveMom() {
    if (isCommons()) return;
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
      const r = await fetch('/api/projects/' + encodeURIComponent(compatibleProjectPathId(current.nexus)) + '/mom', {
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

  // ── Files (read-only index → Obsidian / OS file manager) ─────────────────
  const fmtBytes = (n) => {
    if (!n && n !== 0) return '';
    if (n < 1024) return n + ' B';
    if (n < 1048576) return (n / 1024).toFixed(0) + ' KB';
    return (n / 1048576).toFixed(1) + ' MB';
  };
  const fmtDate = (iso) => {
    try { return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' }); }
    catch (e) { return ''; }
  };

  function fileRow(f, isMatrix) {
    const row = document.createElement('div');
    row.className = 'project-modal__file' + (isMatrix ? ' is-matrix' : '');
    const main = document.createElement('div');
    main.className = 'project-modal__file-main';
    const name = document.createElement('div');
    name.className = 'project-modal__file-name';
    name.textContent = (isMatrix ? '📋 ' : '') + (f.name || f.rel_path || '(file)');
    name.title = f.rel_path || f.name || '';
    main.appendChild(name);
    const meta = document.createElement('div');
    meta.className = 'project-modal__file-meta';
    const bits = [];
    if (!isMatrix && f.rel_path && f.rel_path !== f.name) bits.push(f.rel_path);
    if (f.mtime) bits.push(fmtDate(f.mtime));
    if (f.size != null) bits.push(fmtBytes(f.size));
    meta.textContent = bits.join('  ·  ');
    main.appendChild(meta);
    row.appendChild(main);

    const actions = document.createElement('div');
    actions.className = 'project-modal__file-actions';
    if (f.obsidian_uri) {
      const a = document.createElement('a');
      a.className = 'project-modal__btn project-modal__btn--mini';
      a.href = f.obsidian_uri;
      a.textContent = 'Obsidian';
      a.title = 'Open in Obsidian';
      actions.appendChild(a);
    }
    if (f.abs_path) {
      const rev = document.createElement('button');
      rev.type = 'button';
      rev.className = 'project-modal__btn project-modal__btn--mini';
      rev.textContent = 'Folder';
      rev.title = 'Show in folder';
      rev.addEventListener('click', () => revealFile(f.abs_path, rev));
      actions.appendChild(rev);
    }
    row.appendChild(actions);
    return row;
  }

  async function loadFiles() {
    filesCache = {};
    els.fileList.innerHTML = '';
    els.filesNote.textContent = 'Loading…';
    try {
      const r = await fetch('/api/projects/' + encodeURIComponent(compatibleProjectPathId(current.nexus))
        + '/files?name=' + encodeURIComponent(current.name));
      const data = await r.json();
      filesCache = data;
      const frag = document.createDocumentFragment();
      if (data.matrix) frag.appendChild(fileRow(data.matrix, true));
      (data.files || []).forEach(f => frag.appendChild(fileRow(f, false)));
      els.fileList.appendChild(frag);
      if (!data.exists) {
        els.filesNote.textContent = 'No project folder yet — outputs saved to this project land in '
          + (data.folder || 'the project folder') + '.';
      } else if (!(data.files || []).length && !data.matrix) {
        els.filesNote.textContent = 'No files yet in ' + (data.folder || 'the project folder') + '.';
      } else {
        els.filesNote.textContent = (data.folder || '') + (data.truncated ? '  (showing the most recent files)' : '');
      }
    } catch (e) {
      els.filesNote.textContent = 'Could not load files.';
    }
  }

  async function revealFile(absPath, btn) {
    const prev = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = '…'; }
    try {
      const r = await fetch('/api/fs/reveal', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: absPath }),
      });
      const data = await r.json();
      if (!(data && data.ok)) {
        els.filesNote.textContent = (data && data.error) || 'Could not reveal the file.';
      }
    } catch (e) {
      els.filesNote.textContent = 'Reveal failed: ' + (e.message || e);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = prev; }
    }
  }

  // ── Conversations (membership + restore + add) ───────────────────────────
  function convoRow(c, kind) {
    // kind: 'member' | 'candidate'
    const row = document.createElement('div');
    row.className = 'project-modal__convo' + (c.closed ? ' is-closed' : '');
    const main = document.createElement('div');
    main.className = 'project-modal__convo-main';
    const title = document.createElement('div');
    title.className = 'project-modal__convo-title';
    title.textContent = c.title || '(untitled)';
    title.title = c.title || '';
    main.appendChild(title);
    const meta = document.createElement('div');
    meta.className = 'project-modal__convo-meta';
    const bits = [];
    if (c.closed) bits.push('closed');
    if (c.last_activity_at) bits.push(fmtDate(c.last_activity_at));
    const others = (c.project_ids || []).filter(p => p !== current.nexus);
    if (others.length) bits.push('also in: ' + others.join(', '));
    meta.textContent = bits.join('  ·  ');
    main.appendChild(meta);
    row.appendChild(main);

    const actions = document.createElement('div');
    actions.className = 'project-modal__convo-actions';
    if (kind === 'member') {
      if (c.closed) {
        const restore = document.createElement('button');
        restore.type = 'button';
        restore.className = 'project-modal__btn project-modal__btn--mini';
        restore.textContent = 'Restore';
        restore.title = 'Restore this closed Dialogue to the sidebar';
        restore.addEventListener('click', () => restoreConvo(c.conversation_id));
        actions.appendChild(restore);
      }
      if (!isCommons()) {
        const rm = document.createElement('button');
        rm.type = 'button';
        rm.className = 'project-modal__btn project-modal__btn--mini project-modal__btn--danger';
        rm.textContent = 'Remove';
        rm.title = 'Remove from this project (the Dialogue is kept)';
        rm.addEventListener('click', () => setMembership(c, current.nexus, false));
        actions.appendChild(rm);
      }
    } else {
      const add = document.createElement('button');
      add.type = 'button';
      add.className = 'project-modal__btn project-modal__btn--mini';
      add.textContent = 'Add';
      add.title = 'Add this Dialogue to the project';
      add.addEventListener('click', () => setMembership(c, current.nexus, true));
      actions.appendChild(add);
    }
    row.appendChild(actions);
    return row;
  }

  async function loadConvos() {
    convosCache = {};
    els.convoList.innerHTML = '';
    setStatus(els.convosMsg, 'Loading…');
    // The "add" section is meaningless for Commons (it contains everything).
    if (els.convoAddWrap) els.convoAddWrap.style.display = isCommons() ? 'none' : '';
    const includeClosed = !!(els.convosClosed && els.convosClosed.checked);
    try {
      const r = await fetch('/api/projects/' + encodeURIComponent(compatibleProjectPathId(current.nexus))
        + '/conversations?include_closed=' + (includeClosed ? '1' : '0'));
      const data = await r.json();
      const rows = (data && data.conversations) || [];
      const frag = document.createDocumentFragment();
      rows.forEach(c => frag.appendChild(convoRow(c, 'member')));
      els.convoList.appendChild(frag);
      if (!rows.length) {
        setStatus(els.convosMsg, isCommons()
          ? 'No Dialogues yet.'
          : 'No Dialogues in this project yet — add some below.');
      } else {
        setStatus(els.convosMsg, rows.length + (rows.length === 1 ? ' Dialogue' : ' Dialogues'));
      }
    } catch (e) {
      setStatus(els.convosMsg, 'Could not load Dialogues.', 'error');
    }
  }

  function scheduleCandidateSearch() {
    if (candidateSearchTimer) clearTimeout(candidateSearchTimer);
    candidateSearchTimer = setTimeout(runCandidateSearch, 220);
  }

  async function runCandidateSearch() {
    if (isCommons()) return;
    const q = (els.convoSearch.value || '').trim();
    if (!q) { els.convoAddList.innerHTML = ''; return; }
    els.convoAddList.innerHTML = '<div class="project-modal__hint" style="padding:6px 2px">Searching…</div>';
    try {
      const r = await fetch('/api/projects/' + encodeURIComponent(compatibleProjectPathId(current.nexus))
        + '/conversations?candidates=1&limit=40&q=' + encodeURIComponent(q));
      const data = await r.json();
      const rows = (data && data.conversations) || [];
      els.convoAddList.innerHTML = '';
      if (!rows.length) {
        els.convoAddList.innerHTML = '<div class="project-modal__hint" style="padding:6px 2px">No matching Dialogues to add.</div>';
        return;
      }
      const frag = document.createDocumentFragment();
      rows.forEach(c => frag.appendChild(convoRow(c, 'candidate')));
      els.convoAddList.appendChild(frag);
    } catch (e) {
      els.convoAddList.innerHTML = '<div class="project-modal__hint" style="padding:6px 2px">Search failed.</div>';
    }
  }

  async function setMembership(c, nexus, add) {
    const existing = (c.project_ids || []).filter(p => canonicalProjectId(p) !== 'commons');
    let next;
    if (add) next = existing.includes(nexus) ? existing : [...existing, nexus];
    else next = existing.filter(p => p !== nexus);
    setStatus(els.convosMsg, add ? 'Adding…' : 'Removing…');
    try {
      const r = await fetch('/api/conversation/' + encodeURIComponent(c.conversation_id) + '/projects', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_ids: next }),
      });
      const data = await r.json();
      if (!(data && data.ok)) {
        setStatus(els.convosMsg, (data && data.error) || 'Update failed.', 'error');
        return;
      }
      // Refresh the member list; re-run the add search so the moved row leaves it.
      convosCache = null;
      await loadConvos();
      if (!add && els.convoSearch && els.convoSearch.value.trim()) runCandidateSearch();
      else if (add) runCandidateSearch();
      try { window.OraSidebar && window.OraSidebar.refresh && window.OraSidebar.refresh(); } catch (e) {}
      try { window.OraSidebar && window.OraSidebar.refreshProjects && window.OraSidebar.refreshProjects(); } catch (e) {}
    } catch (e) {
      setStatus(els.convosMsg, 'Update failed: ' + (e.message || e), 'error');
    }
  }

  async function restoreConvo(id) {
    setStatus(els.convosMsg, 'Restoring…');
    try {
      const r = await fetch('/api/conversation/' + encodeURIComponent(id) + '/restore', { method: 'POST' });
      const data = await r.json();
      if (!(data && data.ok)) {
        setStatus(els.convosMsg, (data && data.error) || 'Restore failed.', 'error');
        return;
      }
      convosCache = null;
      await loadConvos();
      try { window.OraSidebar && window.OraSidebar.refresh && window.OraSidebar.refresh(); } catch (e) {}
    } catch (e) {
      setStatus(els.convosMsg, 'Restore failed: ' + (e.message || e), 'error');
    }
  }

  window.OraProjectModal = { open, openCreate, close };
})();
