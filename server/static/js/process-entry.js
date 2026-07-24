/* G1.1 Phase 2.1/2.6/2.7 — governed entry, Library, and bridge label.
 *
 * This module classifies entry, requires explicit project choice for
 * construction, and selects exact authenticated Process Definitions. G1.18
 * adds a schema-driven manual start surface for promoted automated Processes;
 * the server, not this client, creates and governs their durable Runs.
 */
(() => {
  const ROUTE_URL = '/api/process-entry/route';
  const LIBRARY_URL = '/api/process-library/entries';
  const PROJECTS_URL = '/api/projects/meta?status=active';
  const CONSTRUCTION_LABEL_URL = '/api/process-entry/construction-label';
  const AUTOMATION_RUN_URL = '/api/process-automation/runs';

  let overlay = null;
  let pendingResolve = null;
  let constructionLabel = 'Programming';
  let constructionLabelGate = null;
  let constructionDecisionPromise = null;
  let constructionOpenPromise = null;
  let constructionLabelRequestSequence = 0;
  let constructionLabelAppliedSequence = 0;
  let initialized = false;

  const activeProject = () => {
    if (window.OraSidebar && typeof window.OraSidebar.getActiveProject === 'function') {
      return window.OraSidebar.getActiveProject() || 'commons';
    }
    return 'commons';
  };

  const exactRef = (entry) => {
    const ref = entry && entry.definition_ref;
    return ref ? {
      definition_id: ref.definition_id,
      version: ref.version,
      digest: ref.digest,
    } : null;
  };

  function hashText(value) {
    let hash = 2166136261;
    const text = String(value || '');
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(16).padStart(8, '0');
  }

  function ensureOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.className = 'process-entry';
    overlay.hidden = true;
    overlay.innerHTML = [
      '<div class="process-entry__backdrop" data-process-entry-close></div>',
      '<section class="process-entry__card" role="dialog" aria-modal="true" aria-labelledby="processEntryTitle">',
      '  <header class="process-entry__header">',
      '    <div>',
      '      <div class="process-entry__kicker">Governed Process</div>',
      '      <h2 class="process-entry__title" id="processEntryTitle">Programming</h2>',
      '    </div>',
      '    <button class="process-entry__close" type="button" data-process-entry-close aria-label="Close">×</button>',
      '  </header>',
      '  <div class="process-entry__body"></div>',
      '</section>',
    ].join('');
    document.body.appendChild(overlay);
    overlay.querySelectorAll('[data-process-entry-close]').forEach((button) => {
      button.addEventListener('click', () => close(null));
    });
    overlay.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close(null);
      }
    });
    return overlay;
  }

  function show() {
    ensureOverlay();
    overlay.hidden = false;
    document.body.classList.add('process-entry-open');
  }

  function close(value) {
    if (!overlay || overlay.hidden) return;
    overlay.hidden = true;
    document.body.classList.remove('process-entry-open');
    const resolve = pendingResolve;
    pendingResolve = null;
    if (resolve) resolve(value);
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    let payload = null;
    try { payload = await response.json(); } catch (_) { payload = {}; }
    if (!response.ok || !payload || payload.ok === false) {
      throw new Error((payload && payload.error) || `HTTP ${response.status}`);
    }
    return payload;
  }

  async function route(request) {
    const payload = await fetchJson(ROUTE_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    return payload.entry;
  }

  function applyConstructionLabel(gate) {
    const label = gate && gate.current_label === 'Build' ? 'Build' : 'Programming';
    constructionLabel = label;
    constructionLabelGate = gate || null;
    const button = document.getElementById('inputToolbarProgramming');
    if (button) {
      button.setAttribute('aria-label', label);
      button.setAttribute('title', label);
      button.dataset.constructionEntryLabel = label.toLowerCase();
    }
    return label;
  }

  async function refreshConstructionLabel() {
    const requestSequence = ++constructionLabelRequestSequence;
    const payload = await fetchJson(CONSTRUCTION_LABEL_URL);
    if (requestSequence >= constructionLabelAppliedSequence) {
      constructionLabelAppliedSequence = requestSequence;
      applyConstructionLabel(payload.gate);
    }
    return payload.gate;
  }

  async function showConstructionLabelDecision(gate) {
    ensureOverlay();
    const body = overlay.querySelector('.process-entry__body');
    overlay.querySelector('.process-entry__title').textContent = 'Programming or Build?';
    body.innerHTML = [
      '<p class="process-entry__notice">Ora has now constructed, registered, and invoked a non-Programming Process Definition. Keep the entry label Programming, or use Build. This changes only the label—not the Process Definition, routing, or authority.</p>',
      '<div class="process-entry__actions">',
      '  <button class="process-entry__button process-entry__button--secondary" type="button" data-construction-label="keep_programming">Keep Programming</button>',
      '  <button class="process-entry__button process-entry__button--primary" type="button" data-construction-label="use_build">Use Build</button>',
      '</div>',
    ].join('');
    show();
    const result = new Promise((resolve) => { pendingResolve = resolve; });
    body.querySelectorAll('[data-construction-label]').forEach((button) => {
      button.addEventListener('click', async () => {
        body.querySelectorAll('button').forEach((item) => { item.disabled = true; });
        try {
          const payload = await fetchJson(CONSTRUCTION_LABEL_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              decision: button.dataset.constructionLabel,
              decision_by: 'principal:user',
            }),
          });
          constructionLabelAppliedSequence = ++constructionLabelRequestSequence;
          applyConstructionLabel(payload.gate);
          close(payload.gate);
        } catch (error) {
          body.prepend(errorNode(error.message));
          body.querySelectorAll('button').forEach((item) => { item.disabled = false; });
        }
      });
    });
    return result;
  }

  async function ensureConstructionLabelDecision() {
    if (constructionDecisionPromise) return constructionDecisionPromise;
    let gate = constructionLabelGate;
    try {
      gate = await refreshConstructionLabel();
    } catch (error) {
      console.warn('[process-entry] construction label gate unavailable:', error);
      applyConstructionLabel(null);
      return true;
    }
    if (!gate || !gate.decision_available) return true;
    constructionDecisionPromise = showConstructionLabelDecision(gate)
      .then((decision) => !!decision)
      .finally(() => { constructionDecisionPromise = null; });
    return constructionDecisionPromise;
  }

  async function loadProjects() {
    const payload = await fetchJson(PROJECTS_URL);
    const projects = Array.isArray(payload.projects) ? payload.projects : [];
    const byId = new Map();
    byId.set('commons', { nexus: 'commons', name: 'Commons' });
    projects.forEach((project) => {
      const id = String(project.canonical_nexus || project.nexus || '').trim();
      if (id) byId.set(id, project);
    });
    return Array.from(byId.values());
  }

  function errorNode(message) {
    const node = document.createElement('div');
    node.className = 'process-entry__error';
    node.setAttribute('role', 'alert');
    node.textContent = message;
    return node;
  }

  async function showEntryForm(options) {
    ensureOverlay();
    const body = overlay.querySelector('.process-entry__body');
    const title = overlay.querySelector('.process-entry__title');
    title.textContent = options.title || 'Programming';
    body.innerHTML = [
      '<form class="process-entry__form">',
      '  <label class="process-entry__label" for="processEntryObjective">What should happen?</label>',
      '  <textarea class="process-entry__objective" id="processEntryObjective" rows="5" required></textarea>',
      '  <label class="process-entry__label" for="processEntryProject">Project</label>',
      '  <select class="process-entry__project" id="processEntryProject" required></select>',
      '  <p class="process-entry__hint">Construction is bound to the project you confirm here. Ora infers the implementation form.</p>',
      '  <div class="process-entry__actions">',
      '    <button class="process-entry__button process-entry__button--secondary" type="button" data-process-entry-cancel>Cancel</button>',
      '    <button class="process-entry__button process-entry__button--primary" type="submit">Continue</button>',
      '  </div>',
      '</form>',
    ].join('');
    const form = body.querySelector('form');
    const objective = body.querySelector('#processEntryObjective');
    const project = body.querySelector('#processEntryProject');
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    objective.value = options.objective || '';
    body.querySelector('[data-process-entry-cancel]').addEventListener('click', () => close(null));

    show();
    try {
      const projects = await loadProjects();
      const selectedId = options.projectRef || activeProject();
      projects.forEach((record) => {
        const id = String(record.canonical_nexus || record.nexus || '').trim() || 'commons';
        const option = document.createElement('option');
        option.value = id;
        option.textContent = record.name || record.display_name || id;
        option.selected = id === selectedId;
        project.appendChild(option);
      });
      submit.disabled = project.options.length === 0;
    } catch (error) {
      form.prepend(errorNode(`Projects could not be loaded: ${error.message}`));
      submit.disabled = true;
    }

    const result = new Promise((resolve) => { pendingResolve = resolve; });
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      form.querySelectorAll('.process-entry__error').forEach((node) => node.remove());
      const request = {
        source: options.source,
        objective: objective.value.trim(),
        project_ref: project.value || 'commons',
        project_confirmed: true,
      };
      if (options.selectedDefinitionRef) {
        request.selected_definition_ref = options.selectedDefinitionRef;
      }
      if (options.selectedFrameworkId) {
        request.selected_framework_id = options.selectedFrameworkId;
      }
      if (!request.objective) {
        form.prepend(errorNode('What should happen? is required.'));
        objective.focus();
        return;
      }
      try {
        const contract = await route(request);
        if (contract.status !== 'ready') {
          const message = contract.status === 'awaiting_activation'
            ? 'This Process Definition is not active. No invocation or Process Run has started; request activation explicitly.'
            : `Entry is not ready: ${contract.status}`;
          form.prepend(errorNode(message));
          return;
        }
        close({ request, contract, objective: request.objective });
      } catch (error) {
        form.prepend(errorNode(error.message));
      }
    });
    setTimeout(() => objective.focus(), 0);
    return result;
  }

  async function chooseFromLibrary() {
    ensureOverlay();
    const body = overlay.querySelector('.process-entry__body');
    overlay.querySelector('.process-entry__title').textContent = 'Process Library';
    body.innerHTML = [
      '<div class="process-entry__library-intro">Choose the exact Process Definition to use.</div>',
      '<div class="process-entry__library" aria-live="polite"></div>',
      '<div class="process-entry__actions">',
      '  <button class="process-entry__button process-entry__button--secondary" type="button" data-process-entry-cancel>Cancel</button>',
      '</div>',
    ].join('');
    const list = body.querySelector('.process-entry__library');
    body.querySelector('[data-process-entry-cancel]').addEventListener('click', () => close(null));
    show();
    const result = new Promise((resolve) => { pendingResolve = resolve; });
    try {
      const payload = await fetchJson(
        `${LIBRARY_URL}?project_ref=${encodeURIComponent(activeProject())}`
      );
      const definitions = Array.isArray(payload.definitions) ? payload.definitions : [];
      if (!definitions.length) {
        list.appendChild(errorNode('No authenticated Process Definitions are available.'));
      }
      definitions.forEach((entry) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'process-entry__library-row';
        const name = document.createElement('span');
        name.className = 'process-entry__library-name';
        name.textContent = entry.display_name || entry.id;
        const description = document.createElement('span');
        description.className = 'process-entry__library-description';
        description.textContent = entry.display_description || '';
        const identity = document.createElement('span');
        identity.className = 'process-entry__library-identity';
        const ref = exactRef(entry);
        identity.textContent = ref
          ? `${ref.definition_id}@${ref.version}`
          : 'Unavailable identity';
        const lifecycle = document.createElement('span');
        lifecycle.className = 'process-entry__library-lifecycle';
        const scope = entry.scope || {};
        const packageInfo = entry.package || {};
        const memberCount = Array.isArray(packageInfo.members)
          ? packageInfo.members.length : 0;
        lifecycle.textContent = [
          entry.lifecycle_status || entry.status || 'unknown',
          ref ? `${String(ref.digest).slice(0, 18)}…` : 'unbound digest',
          `${scope.kind || 'unknown'}:${scope.selector || '?'}`,
          `${packageInfo.package_id || 'unbound package'}@${packageInfo.package_version || '?'} (${memberCount} member${memberCount === 1 ? '' : 's'})`,
        ].join(' · ');
        button.append(name, description, identity, lifecycle);
        button.addEventListener('click', () => close(entry));
        list.appendChild(button);
      });
    } catch (error) {
      list.appendChild(errorNode(`Process Library could not be loaded: ${error.message}`));
    }
    return result;
  }

  function showNotice(titleText, message) {
    ensureOverlay();
    const body = overlay.querySelector('.process-entry__body');
    overlay.querySelector('.process-entry__title').textContent = titleText;
    body.innerHTML = [
      '<p class="process-entry__notice"></p>',
      '<div class="process-entry__actions">',
      '  <button class="process-entry__button process-entry__button--primary" type="button" data-process-entry-notice-close>Close</button>',
      '</div>',
    ].join('');
    body.querySelector('.process-entry__notice').textContent = message;
    body.querySelector('[data-process-entry-notice-close]').addEventListener(
      'click', () => close(null)
    );
    show();
    return new Promise((resolve) => { pendingResolve = resolve; });
  }

  function readAutomationValue(input, schema) {
    const type = schema.type;
    if (type === 'boolean') return !!input.checked;
    if (type === 'integer') return Number.parseInt(input.value, 10);
    if (type === 'number') return Number.parseFloat(input.value);
    if (type === 'object' || type === 'array') return JSON.parse(input.value);
    return input.value;
  }

  function renderAutomationRun(entry, state) {
    const body = overlay.querySelector('.process-entry__body');
    overlay.querySelector('.process-entry__title').textContent = entry.display_name || entry.id;
    body.innerHTML = '';
    const identity = document.createElement('p');
    identity.className = 'process-entry__library-identity';
    identity.textContent = `${state.definition_ref.definition_id}@${state.definition_ref.version} · ${state.definition_ref.digest}`;
    body.appendChild(identity);
    const status = document.createElement('div');
    status.className = 'process-entry__notice';
    status.textContent = `${state.status}: ${state.current_node.label}`;
    body.appendChild(status);
    if (state.status === 'awaiting_human_checkpoint') {
      const boundary = document.createElement('p');
      boundary.textContent = (
        'This is an exact persisted human checkpoint. Approval advances only this '
        + 'Process Run; it does not activate, schedule, send, or widen authority.'
      );
      body.appendChild(boundary);
      const actions = document.createElement('div');
      actions.className = 'process-entry__actions';
      [['Approve checkpoint', 'approved'], ['Deny and stop', 'denied']].forEach(([label, outcome]) => {
        const node = document.createElement('button');
        node.type = 'button';
        node.className = `process-entry__button ${outcome === 'approved' ? 'process-entry__button--primary' : 'process-entry__button--secondary'}`;
        node.textContent = label;
        node.addEventListener('click', async () => {
          actions.querySelectorAll('button').forEach((button) => { button.disabled = true; });
          try {
            const payload = await fetchJson(`${AUTOMATION_RUN_URL}/${encodeURIComponent(state.run_id)}`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                action: 'resolve_checkpoint', outcome,
              }),
            });
            renderAutomationRun(entry, payload.run);
          } catch (error) {
            body.prepend(errorNode(error.message));
            actions.querySelectorAll('button').forEach((button) => { button.disabled = false; });
          }
        });
        actions.appendChild(node);
      });
      body.appendChild(actions);
    } else if (state.status === 'paused_after_failure') {
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.className = 'process-entry__button process-entry__button--primary';
      retry.textContent = 'Retry from checkpoint';
      retry.addEventListener('click', async () => {
        retry.disabled = true;
        try {
          const payload = await fetchJson(`${AUTOMATION_RUN_URL}/${encodeURIComponent(state.run_id)}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'retry' }),
          });
          renderAutomationRun(entry, payload.run);
        } catch (error) {
          body.prepend(errorNode(error.message));
          retry.disabled = false;
        }
      });
      body.appendChild(retry);
    } else if (state.run_state === 'completed' && state.result) {
      const heading = document.createElement('h3');
      heading.textContent = 'Authenticated result';
      body.appendChild(heading);
      const result = document.createElement('pre');
      result.textContent = JSON.stringify(state.result.content, null, 2);
      body.appendChild(result);
    }
    const closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 'process-entry__button process-entry__button--secondary';
    closeButton.textContent = 'Close';
    closeButton.addEventListener('click', () => close(null));
    body.appendChild(closeButton);
    show();
  }

  async function showAutomatedRunForm(entry) {
    ensureOverlay();
    const body = overlay.querySelector('.process-entry__body');
    overlay.querySelector('.process-entry__title').textContent = entry.display_name || entry.id;
    body.innerHTML = '';
    const intro = document.createElement('p');
    intro.className = 'process-entry__notice';
    intro.textContent = (
      'Enter this Run\'s exact inputs. Ora executes the registered version in a '
      + 'separate no-tools worker and stops at every human checkpoint.'
    );
    body.appendChild(intro);
    const projectConfirmation = document.createElement('label');
    projectConfirmation.className = 'process-entry__label process-entry__project-confirmation';
    const projectCheckbox = document.createElement('input');
    projectCheckbox.type = 'checkbox';
    projectCheckbox.dataset.automationProjectConfirmed = 'true';
    projectConfirmation.appendChild(projectCheckbox);
    projectConfirmation.appendChild(document.createTextNode(
      ` I confirm this Run belongs to Project: ${activeProject()}`
    ));
    body.appendChild(projectConfirmation);
    const form = document.createElement('form');
    form.className = 'process-entry__form process-entry__automation-form';
    const schema = entry.input_schema || {};
    const properties = schema.properties || {};
    const required = new Set(schema.required || []);
    Object.keys(properties).forEach((name) => {
      const fieldSchema = properties[name] || {};
      const label = document.createElement('label');
      label.className = 'process-entry__label';
      label.textContent = `${name.replace(/_/g, ' ')}${required.has(name) ? ' *' : ''}`;
      let input;
      if (fieldSchema.type === 'boolean') {
        input = document.createElement('input');
        input.type = 'checkbox';
      } else if (name === 'body' || fieldSchema.type === 'object' || fieldSchema.type === 'array') {
        input = document.createElement('textarea');
        input.rows = name === 'body' ? 6 : 4;
        if (fieldSchema.type === 'object') input.placeholder = '{}';
        if (fieldSchema.type === 'array') input.placeholder = '[]';
      } else {
        input = document.createElement('input');
        input.type = ['integer', 'number'].includes(fieldSchema.type) ? 'number' : 'text';
      }
      input.dataset.automationInput = name;
      input.required = required.has(name) && fieldSchema.type !== 'boolean';
      label.appendChild(input);
      form.appendChild(label);
    });
    const actions = document.createElement('div');
    actions.className = 'process-entry__actions';
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'process-entry__button process-entry__button--secondary';
    cancel.textContent = 'Cancel';
    cancel.addEventListener('click', () => close(null));
    const run = document.createElement('button');
    run.type = 'submit';
    run.className = 'process-entry__button process-entry__button--primary';
    run.textContent = 'Start governed Run';
    actions.append(cancel, run);
    form.appendChild(actions);
    body.appendChild(form);
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      form.querySelectorAll('.process-entry__error').forEach((node) => node.remove());
      if (!projectCheckbox.checked) {
        form.prepend(errorNode('Confirm the exact Project before starting this Run.'));
        return;
      }
      const inputs = {};
      try {
        form.querySelectorAll('[data-automation-input]').forEach((input) => {
          const name = input.dataset.automationInput;
          if (!required.has(name) && !input.value && input.type !== 'checkbox') return;
          inputs[name] = readAutomationValue(input, properties[name]);
        });
      } catch (error) {
        form.prepend(errorNode(`Input JSON is invalid: ${error.message}`));
        return;
      }
      run.disabled = true;
      try {
        const ref = exactRef(entry);
        const payload = await fetchJson(AUTOMATION_RUN_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            definition_ref: ref,
            project_ref: activeProject(),
            inputs,
            idempotency_key: `process-ui:${hashText(JSON.stringify({ ref, project: activeProject(), inputs }))}`,
          }),
        });
        renderAutomationRun(entry, payload.run);
      } catch (error) {
        form.prepend(errorNode(error.message));
        run.disabled = false;
      }
    });
    show();
  }

  async function prepareInquiry(objective, selectedFramework) {
    const selectedRef = selectedFramework && selectedFramework.kind === 'process_definition'
      ? exactRef(selectedFramework) : null;
    const selectedFrameworkId = selectedFramework && selectedFramework.id && !selectedRef
      ? selectedFramework.id : null;
    const request = {
      source: (selectedRef || selectedFrameworkId) ? 'shared_picker' : 'inquiry',
      objective: String(objective || '').trim(),
      project_ref: activeProject(),
      project_confirmed: false,
    };
    if (selectedRef) request.selected_definition_ref = selectedRef;
    if (selectedFrameworkId) request.selected_framework_id = selectedFrameworkId;
    const contract = await route(request);
    if (contract.status === 'awaiting_project_confirmation') {
      return showEntryForm({
        source: request.source,
        objective: request.objective,
        projectRef: request.project_ref,
        selectedDefinitionRef: selectedRef,
        selectedFrameworkId,
        title: selectedFramework && selectedFramework.display_name,
      });
    }
    if (contract.status === 'awaiting_definition_selection') {
      const selected = await chooseFromLibrary();
      if (!selected) return null;
      if (selected.automated_execution_available) {
        await showAutomatedRunForm(selected);
        return null;
      }
      const selectedRequest = {
        source: 'process_library',
        objective: request.objective,
        project_ref: request.project_ref,
        project_confirmed: false,
        selected_definition_ref: exactRef(selected),
      };
      const selectedContract = await route(selectedRequest);
      if (selectedContract.status === 'awaiting_project_confirmation') {
        return showEntryForm({
          source: selectedRequest.source,
          objective: selectedRequest.objective,
          projectRef: selectedRequest.project_ref,
          selectedDefinitionRef: selectedRequest.selected_definition_ref,
          title: selected.display_name,
        });
      }
      if (selectedContract.status === 'awaiting_activation') {
        await showNotice(
          selected.display_name || 'Activation required',
          'This Process Definition is not active. No invocation or Process Run has started. Request activation explicitly to continue.'
        );
        return null;
      }
      return {
        request: selectedRequest,
        contract: selectedContract,
        objective: selectedRequest.objective,
      };
    }
    if (contract.status === 'awaiting_activation') {
      await showNotice(
        (selectedFramework && selectedFramework.display_name) || 'Activation required',
        'This Process Definition is not active. No invocation or Process Run has started. Request activation explicitly to continue.'
      );
      return null;
    }
    return { request, contract, objective: request.objective };
  }

  function openConstruction() {
    if (constructionOpenPromise) return constructionOpenPromise;
    constructionOpenPromise = (async () => {
      if (!(await ensureConstructionLabelDecision())) return null;
      const result = await showEntryForm({
        source: 'construction_action',
        objective: '',
        projectRef: activeProject(),
        title: constructionLabel,
      });
      if (result) {
        document.dispatchEvent(new CustomEvent('ora:process-entry:ready', { detail: result }));
      }
      return result;
    })().finally(() => { constructionOpenPromise = null; });
    return constructionOpenPromise;
  }

  async function openLibrary() {
    const selected = await chooseFromLibrary();
    if (!selected) return null;
    if (selected.automated_execution_available) {
      await showAutomatedRunForm(selected);
      return selected;
    }
    const result = await showEntryForm({
      source: 'process_library',
      objective: '',
      projectRef: activeProject(),
      selectedDefinitionRef: exactRef(selected),
      title: selected.display_name || 'Programming',
    });
    if (result) {
      document.dispatchEvent(new CustomEvent('ora:process-entry:ready', { detail: result }));
    }
    return result;
  }

  function init() {
    if (initialized) return;
    initialized = true;
    ensureOverlay();
    refreshConstructionLabel().catch((error) => {
      console.warn('[process-entry] construction label hydration failed:', error);
      applyConstructionLabel(null);
    });
    document.addEventListener('ora:input-toolbar:programming', openConstruction);
    const libraryButton = document.getElementById('sidebarProcessLibraryOpen');
    if (libraryButton) libraryButton.addEventListener('click', openLibrary);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.OraProcessEntry = {
    prepareInquiry,
    openConstruction,
    openLibrary,
    refreshConstructionLabel,
    getConstructionLabel: () => constructionLabel,
    close,
  };
})();
