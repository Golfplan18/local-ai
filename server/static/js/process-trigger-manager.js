/* G1.19 Trigger Manager.
 *
 * Trigger specs are immutable drafts. Activation is a separate exact Principal
 * decision; registration alone never deploys work. Every firing enters the
 * generic Process Automation / Run Inspector path. Inbound activation remains
 * unavailable until G1.21 supplies an authenticated channel.
 */
(() => {
  const openButton = document.getElementById('sidebarTriggerManagerOpen');
  if (!openButton) return;

  const state = { triggers: [], library: [], selected: null };

  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const dialog = document.createElement('dialog');
  dialog.id = 'processTriggerManager';
  dialog.className = 'process-trigger-manager';
  dialog.setAttribute('aria-labelledby', 'processTriggerManagerTitle');
  dialog.innerHTML = `
    <form method="dialog" class="process-trigger-shell">
      <header>
        <div><h2 id="processTriggerManagerTitle">Trigger Manager</h2>
        <p>Deploy an exact Process for a manual, event, inbound, or justified calendar cause.</p></div>
        <button type="submit" aria-label="Close Trigger Manager">Close</button>
      </header>
      <div class="process-trigger-status" role="status" aria-live="polite"></div>
      <div class="process-trigger-layout">
        <aside>
          <button type="button" data-trigger-new>New Trigger</button>
          <div data-trigger-list aria-label="Configured Triggers"></div>
        </aside>
        <section data-trigger-detail></section>
      </div>
    </form>`;
  document.body.appendChild(dialog);

  const status = dialog.querySelector('.process-trigger-status');
  const list = dialog.querySelector('[data-trigger-list]');
  const detail = dialog.querySelector('[data-trigger-detail]');

  const setStatus = (message, isError = false) => {
    status.textContent = message || '';
    status.dataset.error = isError ? 'true' : 'false';
  };

  const api = async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok || body.ok === false) {
      const error = new Error(body.error || `Request failed (${response.status})`);
      error.status = response.status;
      throw error;
    }
    return body;
  };

  const nonce = prefix => {
    const raw = globalThis.crypto && crypto.randomUUID
      ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
    return `${prefix}:${raw}`.toLowerCase().replace(/[^a-z0-9._:-]/g, '-').slice(0, 240);
  };

  const load = async () => {
    const [triggerBody, libraryBody] = await Promise.all([
      api('/api/process-triggers'),
      api('/api/process-library/entries'),
    ]);
    state.triggers = triggerBody.triggers || [];
    state.library = (libraryBody.entries || []).filter(row => (
      row.automated_execution_available === true && row.lifecycle_status === 'available'
    ));
    if (state.selected) {
      state.selected = state.triggers.find(row => (
        row.spec.trigger_id === state.selected.spec.trigger_id
      )) || null;
    }
    render();
  };

  const renderList = () => {
    list.replaceChildren();
    if (!state.triggers.length) {
      list.appendChild(element('p', 'process-trigger-empty', 'No Trigger deployments yet.'));
      return;
    }
    state.triggers.forEach(row => {
      const button = element('button', 'process-trigger-row');
      button.type = 'button';
      button.dataset.triggerId = row.spec.trigger_id;
      button.appendChild(element('strong', '', row.spec.name));
      button.appendChild(element('span', '', `${row.spec.kind} · ${row.status}`));
      button.addEventListener('click', () => { state.selected = row; render(); });
      list.appendChild(button);
    });
  };

  const labelledInput = (label, input) => {
    const wrapper = element('label', 'process-trigger-field');
    wrapper.appendChild(element('span', '', label));
    wrapper.appendChild(input);
    return wrapper;
  };

  const createForm = () => {
    const form = element('div', 'process-trigger-create');
    form.appendChild(element('h3', '', 'New immutable Trigger draft'));
    const fields = {};
    const input = (name, type = 'text') => {
      const node = document.createElement('input');
      node.type = type; node.name = name; fields[name] = node; return node;
    };
    fields.name = input('name');
    fields.name.required = true;
    form.appendChild(labelledInput('Name', fields.name));
    fields.trigger_id = input('trigger_id');
    fields.trigger_id.required = true;
    fields.trigger_id.pattern = '[a-z0-9][a-z0-9._:-]{0,255}';
    form.appendChild(labelledInput('Stable ID', fields.trigger_id));
    fields.project_ref = input('project_ref'); fields.project_ref.value = 'ora';
    form.appendChild(labelledInput('Project', fields.project_ref));

    fields.definition_ref = document.createElement('select');
    state.library.forEach(row => {
      const option = document.createElement('option');
      option.value = JSON.stringify(row.definition_ref);
      option.textContent = `${row.display_name} · ${row.definition_ref.version}`;
      fields.definition_ref.appendChild(option);
    });
    form.appendChild(labelledInput('Exact Process', fields.definition_ref));

    fields.kind = document.createElement('select');
    ['manual', 'event', 'time', 'inbound'].forEach(value => {
      const option = element('option', '', value === 'time' ? 'Time (justification required)' : value);
      option.value = value; fields.kind.appendChild(option);
    });
    form.appendChild(labelledInput('Cause', fields.kind));

    const conditional = element('div', 'process-trigger-conditional');
    form.appendChild(conditional);
    const renderCondition = () => {
      conditional.replaceChildren();
      const kind = fields.kind.value;
      if (kind === 'event') {
        fields.event_type = document.createElement('select');
        [['file_change', 'File change'], ['framework_completion', 'Framework completion']].forEach(([value, text]) => {
          const option = element('option', '', text); option.value = value; fields.event_type.appendChild(option);
        });
        conditional.appendChild(labelledInput('Event', fields.event_type));
        fields.event_value = input('event_value');
        conditional.appendChild(labelledInput(
          'Absolute watched path, or exact source definition JSON', fields.event_value
        ));
      } else if (kind === 'time') {
        fields.event_type = document.createElement('select');
        [['time', 'Calendar Process'], ['milestone_check_in', 'Project milestone check-in']].forEach(([value, text]) => {
          const option = element('option', '', text); option.value = value; fields.event_type.appendChild(option);
        });
        conditional.appendChild(labelledInput('Purpose', fields.event_type));
        for (const [name, label, value] of [
          ['timezone', 'IANA timezone', Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'],
          ['local_time', 'Local time', '09:00'], ['start_date', 'Start date', new Date().toISOString().slice(0, 10)],
        ]) {
          fields[name] = input(name); fields[name].value = value;
          conditional.appendChild(labelledInput(label, fields[name]));
        }
        fields.cadence = document.createElement('select');
        for (const value of ['daily', 'weekly']) {
          const option = element('option', '', value); option.value = value; fields.cadence.appendChild(option);
        }
        conditional.appendChild(labelledInput('Cadence', fields.cadence));
        fields.weekdays = input('weekdays'); fields.weekdays.placeholder = '0,1,2,3,4 (weekly only)';
        conditional.appendChild(labelledInput('Weekdays (Monday = 0)', fields.weekdays));
        fields.missed_policy = document.createElement('select');
        [['run_once', 'Run once after Ora returns'], ['skip', 'Skip missed window']].forEach(([value, text]) => {
          const option = element('option', '', text); option.value = value; fields.missed_policy.appendChild(option);
        });
        conditional.appendChild(labelledInput('Intermittency policy', fields.missed_policy));
        fields.runtime_reason = document.createElement('textarea');
        fields.runtime_reason.required = true;
        fields.runtime_reason.placeholder = 'Why no file, framework, inbound, or other runtime event can represent this calendar cause.';
        conditional.appendChild(labelledInput('Runtime-Principle justification', fields.runtime_reason));
        conditional.appendChild(element(
          'p', 'process-trigger-disclosure',
          'Runs only while Ora is open. One recalculated in-app wake; no polling loop, cron, launchd, deferred sweep, or 24/7 promise.'
        ));
      } else if (kind === 'inbound') {
        fields.channel = document.createElement('select');
        for (const value of ['email', 'telegram']) {
          const option = element('option', '', value); option.value = value; fields.channel.appendChild(option);
        }
        conditional.appendChild(labelledInput('Channel', fields.channel));
        fields.source_scope = input('source_scope');
        conditional.appendChild(labelledInput('Authenticated source scope', fields.source_scope));
        conditional.appendChild(element(
          'p', 'process-trigger-disclosure',
          'May be drafted now; activation is unavailable until G1.21 authenticates this channel.'
        ));
      }
    };
    fields.kind.addEventListener('change', renderCondition);
    renderCondition();

    fields.bindings = document.createElement('textarea');
    fields.bindings.value = '{}';
    fields.bindings.spellcheck = false;
    form.appendChild(labelledInput(
      'Input bindings JSON (literal, changed_paths, source_path, source_run_id, source_result, project_snapshot)',
      fields.bindings
    ));
    const submit = element('button', '', 'Save draft'); submit.type = 'button';
    submit.disabled = state.library.length === 0;
    submit.addEventListener('click', async () => {
      try {
        let condition = {};
        let runtimePrinciple;
        if (fields.kind.value === 'event') {
          condition = fields.event_type.value === 'file_change'
            ? { event_type: 'file_change', path_selectors: [fields.event_value.value] }
            : { event_type: 'framework_completion', source_definition_ref: JSON.parse(fields.event_value.value) };
        } else if (fields.kind.value === 'time') {
          const weekdays = fields.weekdays.value.trim()
            ? fields.weekdays.value.split(',').map(value => Number(value.trim())) : [];
          condition = {
            event_type: fields.event_type.value,
            schedule: {
              timezone: fields.timezone.value, local_time: fields.local_time.value,
              cadence: fields.cadence.value, weekdays,
              start_date: fields.start_date.value, missed_policy: fields.missed_policy.value,
              grace_seconds: 300,
            },
          };
          runtimePrinciple = {
            declared_cause: 'passage of time is the declared input',
            runtime_impossibility: fields.runtime_reason.value,
            runtime_alternative: 'no runtime event can represent passage of time',
            availability_boundary: 'only while ora is running',
            no_clock_fallback: 'no cron, launchd, or deferred sweep fallback',
          };
        } else if (fields.kind.value === 'inbound') {
          condition = { channel: fields.channel.value, source_scope: fields.source_scope.value };
        }
        const spec = {
          trigger_id: fields.trigger_id.value,
          name: fields.name.value,
          definition_ref: JSON.parse(fields.definition_ref.value),
          project_ref: fields.project_ref.value,
          kind: fields.kind.value,
          condition,
          input_bindings: JSON.parse(fields.bindings.value),
          principal_id: 'principal:user',
        };
        if (runtimePrinciple) spec.runtime_principle = runtimePrinciple;
        const body = await api('/api/process-triggers', {
          method: 'POST', body: JSON.stringify({ spec }),
        });
        state.selected = body.trigger;
        setStatus('Trigger draft saved. Review the exact contract before activation.');
        await load();
      } catch (error) { setStatus(error.message, true); }
    });
    form.appendChild(submit);
    return form;
  };

  const renderDetail = () => {
    detail.replaceChildren();
    if (!state.selected) { detail.appendChild(createForm()); return; }
    const row = state.selected;
    detail.appendChild(element('h3', '', row.spec.name));
    detail.appendChild(element('p', '', `${row.spec.kind} · ${row.status}`));
    const contract = element('pre', 'process-trigger-contract');
    contract.textContent = JSON.stringify({
      spec_digest: row.spec_digest,
      definition_ref: row.spec.definition_ref,
      project_ref: row.spec.project_ref,
      condition: row.spec.condition,
      input_bindings: row.spec.input_bindings,
      runtime_principle: row.spec.runtime_principle,
    }, null, 2);
    detail.appendChild(contract);
    const controls = element('div', 'process-trigger-controls');
    if (row.status === 'draft') {
      const confirmLabel = element('label', 'process-trigger-review');
      const confirm = document.createElement('input'); confirm.type = 'checkbox';
      confirmLabel.append(confirm, document.createTextNode(
        ' I reviewed this exact Process, project, condition, input binding, and Runtime-Principle record.'
      ));
      controls.appendChild(confirmLabel);
      const activate = element('button', '', 'Approve and activate'); activate.type = 'button';
      activate.addEventListener('click', async () => {
        if (!confirm.checked) { setStatus('Explicit review is required before activation.', true); return; }
        try {
          const request = row.activation_request;
          const body = await api(`/api/process-triggers/${encodeURIComponent(row.spec.trigger_id)}`, {
            method: 'POST', body: JSON.stringify({
              action: 'activate', expected_spec_digest: row.spec_digest,
              approval: {
                decision: 'approve_activation', principal_id: 'principal:user',
                request_digest: request.request_digest,
              },
              idempotency_key: nonce('trigger-activate'),
            }),
          });
          state.selected = body.trigger; setStatus('Trigger activated.'); await load();
        } catch (error) { setStatus(error.message, true); await load(); }
      });
      controls.appendChild(activate);
    }
    if (row.status === 'active' && row.spec.kind === 'manual') {
      const fire = element('button', '', 'Run now'); fire.type = 'button';
      fire.addEventListener('click', async () => {
        try {
          const body = await api(`/api/process-triggers/${encodeURIComponent(row.spec.trigger_id)}`, {
            method: 'POST', body: JSON.stringify({ action: 'fire', request_id: nonce('manual') }),
          });
          state.selected = body.trigger; setStatus('Process Run created through the governed runtime.'); await load();
        } catch (error) { setStatus(error.message, true); await load(); }
      });
      controls.appendChild(fire);
    }
    const action = row.status === 'active' ? 'pause' : (row.status === 'paused' ? 'resume' : null);
    if (action) {
      const button = element('button', '', action === 'pause' ? 'Pause Trigger' : 'Resume Trigger');
      button.type = 'button';
      button.addEventListener('click', async () => {
        try {
          const body = await api(`/api/process-triggers/${encodeURIComponent(row.spec.trigger_id)}`, {
            method: 'POST', body: JSON.stringify({
              action, expected_state_digest: row.state_digest,
              idempotency_key: nonce(`trigger-${action}`),
            }),
          });
          state.selected = body.trigger; setStatus(`Trigger ${action}d.`); await load();
        } catch (error) { setStatus(error.message, true); await load(); }
      });
      controls.appendChild(button);
    }
    if (row.status !== 'retired') {
      const retire = element('button', '', 'Retire'); retire.type = 'button';
      retire.addEventListener('click', async () => {
        try {
          const body = await api(`/api/process-triggers/${encodeURIComponent(row.spec.trigger_id)}`, {
            method: 'POST', body: JSON.stringify({
              action: 'retire', expected_state_digest: row.state_digest,
              idempotency_key: nonce('trigger-retire'),
            }),
          });
          state.selected = body.trigger; setStatus('Trigger retired.'); await load();
        } catch (error) { setStatus(error.message, true); await load(); }
      });
      controls.appendChild(retire);
    }
    detail.appendChild(controls);
    const history = element('div', 'process-trigger-history');
    history.appendChild(element('h4', '', 'Authenticated firing history'));
    if (!row.firings.length) history.appendChild(element('p', '', 'No firings.'));
    row.firings.forEach(firing => {
      const item = element('button', 'process-trigger-firing', `${firing.status} · ${firing.run_id || firing.firing_id}`);
      item.type = 'button';
      if (firing.run_id) item.addEventListener('click', () => {
        document.dispatchEvent(new CustomEvent('ora:process-run-inspector:open', {
          detail: { run_id: firing.run_id, trigger: item },
        }));
      });
      history.appendChild(item);
    });
    detail.appendChild(history);
  };

  const render = () => { renderList(); renderDetail(); };
  dialog.querySelector('[data-trigger-new]').addEventListener('click', () => {
    state.selected = null; setStatus(''); render();
  });
  openButton.addEventListener('click', async () => {
    dialog.showModal(); setStatus('Loading Trigger contracts…');
    try { await load(); setStatus(''); }
    catch (error) { setStatus(error.message, true); }
  });

  window.OraProcessTriggerManager = {
    open: async triggerId => {
      dialog.showModal();
      try {
        await load();
        state.selected = state.triggers.find(row => row.spec.trigger_id === triggerId) || null;
        render();
      } catch (error) { setStatus(error.message, true); }
    },
    refresh: load,
  };
})();
