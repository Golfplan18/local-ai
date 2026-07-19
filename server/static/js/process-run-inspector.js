/* G1.1 Phase 2.5/2.6 — Run Inspector with explicit terminal disposition. */
(function () {
  'use strict';

  const VIEW_ORDER = [
    'overview', 'plan', 'current_state', 'decisions', 'changes',
    'evidence', 'permissions', 'artifacts', 'technical',
  ];
  const LABELS = {
    overview: 'Overview', plan: 'Plan', current_state: 'Current State',
    decisions: 'Decisions', changes: 'Changes', evidence: 'Evidence',
    permissions: 'Permissions', artifacts: 'Artifacts', technical: 'Technical',
  };

  let root = null;
  let snapshot = null;
  let lifecycle = null;
  let activeView = 'overview';
  let returnFocus = null;

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  };

  const pretty = value => JSON.stringify(value, null, 2);

  const fetchJson = async (url, options) => {
    const response = await fetch(url, options);
    let payload = null;
    try { payload = await response.json(); } catch (_) { payload = {}; }
    if (!response.ok || !payload || payload.ok === false) {
      throw new Error((payload && payload.error) || `HTTP ${response.status}`);
    }
    return payload;
  };

  const ensureRoot = () => {
    if (root) return root;
    root = el('div', 'process-run-inspector');
    root.hidden = true;
    root.dataset.processRunInspector = 'true';
    root.innerHTML = [
      '<div class="process-run-inspector__backdrop" data-inspector-close></div>',
      '<section class="process-run-inspector__shell" role="dialog" aria-modal="true" aria-labelledby="processRunInspectorTitle">',
      '  <header class="process-run-inspector__header">',
      '    <div><h2 id="processRunInspectorTitle">Process Run</h2><div class="process-run-inspector__identity" data-inspector-identity></div></div>',
      '    <button type="button" class="process-run-inspector__close" data-inspector-close aria-label="Close Run Inspector">×</button>',
      '  </header>',
      '  <div class="process-run-inspector__status" data-inspector-status aria-live="polite"></div>',
      '  <nav class="process-run-inspector__tabs" role="tablist" aria-label="Run Inspector views"></nav>',
      '  <main class="process-run-inspector__content" data-inspector-content></main>',
      '  <footer class="process-run-inspector__footer">',
      '    <button type="button" data-inspector-dialogue hidden>Open Dialogue</button>',
      '    <button type="button" data-inspector-copy hidden>Copy target path</button>',
      '    <span data-inspector-digest></span>',
      '  </footer>',
      '</section>',
    ].join('');
    document.body.appendChild(root);
    root.querySelectorAll('[data-inspector-close]').forEach(node => {
      node.addEventListener('click', close);
    });
    root.querySelector('[data-inspector-dialogue]').addEventListener('click', () => {
      if (!snapshot || !snapshot.dialogue_ref) return;
      document.dispatchEvent(new CustomEvent('ora:conversation-selected', {
        detail: {
          conversation_id: snapshot.dialogue_ref,
          title: snapshot.views.overview.title || 'Process',
          tag: '',
        },
      }));
      close();
    });
    root.querySelector('[data-inspector-copy]').addEventListener('click', async () => {
      const repository = snapshot && snapshot.views.changes.repository;
      const ref = repository && repository.locator && repository.locator.ref;
      if (!ref || !navigator.clipboard || !navigator.clipboard.writeText) return;
      await navigator.clipboard.writeText(ref);
      root.querySelector('[data-inspector-status]').textContent = 'Target path copied.';
    });
    return root;
  };

  const close = () => {
    if (!root) return;
    root.hidden = true;
    document.body.classList.remove('process-run-inspector-open');
    if (returnFocus && typeof returnFocus.focus === 'function') returnFocus.focus();
  };

  const appendValue = (container, label, value, technical) => {
    if (value === null || value === undefined || value === '') return;
    const section = technical ? el('details', 'process-run-inspector__details')
      : el('section', 'process-run-inspector__section');
    if (technical) {
      section.appendChild(el('summary', '', label));
    } else {
      section.appendChild(el('h3', '', label));
    }
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      section.appendChild(el('p', '', value));
    } else if (Array.isArray(value) && value.length === 0) {
      section.appendChild(el('p', 'process-run-inspector__empty', 'None recorded.'));
    } else {
      const pre = el('pre', 'process-run-inspector__data');
      pre.textContent = pretty(value);
      section.appendChild(pre);
    }
    container.appendChild(section);
  };

  const lifecycleRequest = async (disposition, option) => {
    if (!snapshot) return;
    const consequential = disposition === 'archive' || disposition === 'discard';
    if (consequential && typeof window.confirm === 'function') {
      const consequence = disposition === 'discard'
        ? 'Discard marks the Run outputs discarded. It does not delete source files.'
        : 'Archive marks the Run outputs archived without deleting them.';
      if (!window.confirm(`${consequence} Continue?`)) return;
    }
    const ref = option && option.definition_ref;
    const body = {
      disposition,
      decision_by: lifecycle.principal_id,
    };
    if (disposition === 'promote' && option) {
      body.promoted_definition_ref = option.definition_ref;
      body.capability_artifact_id = option.capability_artifact_id;
    }
    const status = root.querySelector('[data-inspector-status]');
    status.textContent = `Recording ${disposition} disposition…`;
    try {
      const payload = await fetchJson(
        `/api/process-runs/${encodeURIComponent(snapshot.run_id)}/lifecycle`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }
      );
      lifecycle = payload.lifecycle;
      status.textContent = `Run closed: ${disposition}.`;
      renderView();
    } catch (error) {
      status.textContent = `Run lifecycle failed: ${error.message}`;
    }
  };

  const renderLifecycle = (container) => {
    if (!lifecycle || lifecycle.status === 'not_terminal') return;
    const section = el(
      'section',
      'process-run-inspector__section process-run-inspector__lifecycle'
    );
    section.appendChild(el('h3', '', 'Run lifecycle'));
    if (lifecycle.status === 'closed') {
      const closure = lifecycle.closure || {};
      section.appendChild(el(
        'p', '', `Closed with ${closure.disposition || 'an exact disposition'}.`
      ));
      appendValue(section, 'Lifecycle receipt', {
        record_id: closure.record_id,
        recorded_at: closure.recorded_at,
        decision_by: closure.decision_by,
        promoted_definition_ref: closure.promoted_definition_ref,
        effective_artifacts: closure.effective_artifacts,
      }, false);
      container.appendChild(section);
      return;
    }
    section.appendChild(el(
      'p',
      'process-run-inspector__lifecycle-help',
      'Choose exactly what should happen to this Run’s outputs. No choice activates standing automation or deletes repository files.'
    ));
    const options = Array.isArray(lifecycle.promote_options)
      ? lifecycle.promote_options : [];
    let selector = null;
    if (options.length) {
      selector = el('select', 'process-run-inspector__lifecycle-select');
      selector.setAttribute('aria-label', 'Capability to promote');
      options.forEach((option, index) => {
        const choice = el(
          'option', '',
          `${option.display_name} · ${option.definition_ref.definition_id}@${option.definition_ref.version}`
        );
        choice.value = String(index);
        selector.appendChild(choice);
      });
      section.appendChild(selector);
    }
    const actions = el('div', 'process-run-inspector__lifecycle-actions');
    (lifecycle.available_actions || []).forEach((action) => {
      const button = el(
        'button',
        `process-run-inspector__lifecycle-${action}`,
        action.charAt(0).toUpperCase() + action.slice(1)
      );
      button.type = 'button';
      button.addEventListener('click', () => {
        const option = action === 'promote' && selector
          ? options[Number(selector.value)] : null;
        lifecycleRequest(action, option);
      });
      actions.appendChild(button);
    });
    section.appendChild(actions);
    container.appendChild(section);
  };

  const renderOverview = (container, view) => {
    const questions = el('div', 'process-run-inspector__questions');
    [
      ['Outcome', view.objective],
      ['State', `${view.visible_status} · ${view.current_phase.label}`],
      ['Next', (view.credible_next_actions || []).length
        ? view.credible_next_actions.map(item => `${item.condition} → ${item.target_node_id}`).join(', ')
        : 'No declared next route'],
      ['You', view.required_human_decision
        ? (typeof view.required_human_decision === 'string'
          ? view.required_human_decision : pretty(view.required_human_decision))
        : 'No action required'],
    ].forEach(([label, value]) => {
      const card = el('section', 'process-run-inspector__question');
      card.appendChild(el('h3', '', label));
      card.appendChild(el('p', '', value));
      questions.appendChild(card);
    });
    container.appendChild(questions);
    const evidence = el('div', `process-run-inspector__evidence-state ${view.evidence_current ? 'is-current' : 'is-stale'}`,
      view.evidence_current ? 'Current evidence supports the result.' : 'Current evidence does not yet support acceptance.');
    evidence.setAttribute('role', 'status');
    container.appendChild(evidence);
    appendValue(container, 'Invoked capability', view.definition_ref, false);
    appendValue(container, 'Capabilities invoked by this Run', view.invoked_capabilities, false);
    appendValue(container, 'Capability created or modified', view.capabilities_created_or_modified, false);
    appendValue(container, 'Result artifacts', view.result_artifacts, false);
    appendValue(container, 'External effects', view.external_effects, false);
    appendValue(container, 'Trigger', view.trigger, false);
    renderLifecycle(container);
  };

  const renderView = () => {
    if (!root || !snapshot) return;
    const content = root.querySelector('[data-inspector-content]');
    content.innerHTML = '';
    content.dataset.view = activeView;
    const view = snapshot.views[activeView];
    if (activeView === 'overview') {
      renderOverview(content, view);
    } else {
      if (activeView === 'changes' && view.repository && !view.repository.current) {
        content.appendChild(el('div', 'process-run-inspector__warning',
          `External-editor state: ${view.repository.state}. ${view.repository.reason}`));
      }
      if (activeView === 'evidence' && !view.acceptance_supported_now) {
        content.appendChild(el('div', 'process-run-inspector__warning',
          'Stale, missing, or failing evidence cannot authorize current acceptance.'));
      }
      Object.keys(view || {}).forEach(key => {
        const label = key.replace(/_/g, ' ').replace(/^./, char => char.toUpperCase());
        appendValue(content, label, view[key], activeView === 'technical');
      });
    }
    root.querySelectorAll('[role="tab"]').forEach(tab => {
      const selected = tab.dataset.view === activeView;
      tab.setAttribute('aria-selected', selected ? 'true' : 'false');
      tab.tabIndex = selected ? 0 : -1;
    });
  };

  const renderTabs = () => {
    const tabs = root.querySelector('[role="tablist"]');
    tabs.innerHTML = '';
    VIEW_ORDER.forEach(name => {
      const button = el('button', 'process-run-inspector__tab', LABELS[name]);
      button.type = 'button';
      button.dataset.view = name;
      button.setAttribute('role', 'tab');
      button.setAttribute('aria-selected', name === activeView ? 'true' : 'false');
      button.addEventListener('click', () => {
        activeView = name;
        renderView();
      });
      button.addEventListener('keydown', event => {
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
        event.preventDefault();
        const offset = event.key === 'ArrowRight' ? 1 : -1;
        const next = (VIEW_ORDER.indexOf(name) + offset + VIEW_ORDER.length) % VIEW_ORDER.length;
        activeView = VIEW_ORDER[next];
        renderView();
        tabs.querySelector(`[data-view="${activeView}"]`).focus();
      });
      tabs.appendChild(button);
    });
  };

  const renderSnapshot = value => {
    snapshot = value;
    lifecycle = null;
    activeView = 'overview';
    const overview = value.views.overview;
    root.querySelector('#processRunInspectorTitle').textContent = overview.title || 'Process Run';
    root.querySelector('[data-inspector-identity]').textContent = [
      value.run_id,
      `${value.definition_ref.definition_id}@${value.definition_ref.version}`,
      overview.visible_status,
    ].join(' · ');
    root.querySelector('[data-inspector-status]').textContent = '';
    root.querySelector('[data-inspector-digest]').textContent = `Snapshot ${value.snapshot_digest}`;
    root.querySelector('[data-inspector-dialogue]').hidden = !value.dialogue_ref;
    const repository = value.views.changes.repository;
    root.querySelector('[data-inspector-copy]').hidden = !(repository && repository.locator && repository.locator.ref);
    root.dataset.evidenceCurrent = overview.evidence_current ? 'true' : 'false';
    renderTabs();
    renderView();
  };

  const open = async (runId, trigger) => {
    const modal = ensureRoot();
    if (!runId) return;
    returnFocus = trigger || document.activeElement;
    modal.hidden = false;
    document.body.classList.add('process-run-inspector-open');
    modal.querySelector('[data-inspector-status]').textContent = 'Loading authenticated Run state…';
    modal.querySelector('[data-inspector-content]').innerHTML = '';
    try {
      const payload = await fetchJson(
        `/api/process-runs/${encodeURIComponent(runId)}/inspector`
      );
      const value = payload.inspector;
      if (!value || pretty(value.view_order) !== pretty(VIEW_ORDER)) {
        throw new Error('Run Inspector view contract is incomplete');
      }
      renderSnapshot(value);
      try {
        const lifecyclePayload = await fetchJson(
          `/api/process-runs/${encodeURIComponent(runId)}/lifecycle`
        );
        lifecycle = lifecyclePayload.lifecycle;
        renderView();
      } catch (error) {
        modal.querySelector('[data-inspector-status]').textContent =
          `Run lifecycle unavailable: ${error.message}`;
      }
      modal.querySelector('.process-run-inspector__close').focus();
    } catch (error) {
      modal.querySelector('[data-inspector-status]').textContent = error.message || String(error);
    }
  };

  document.addEventListener('keydown', event => {
    if (!root || root.hidden) return;
    if (event.key === 'Escape') {
      close();
      return;
    }
    if (event.key === 'Tab') {
      const focusable = Array.from(root.querySelectorAll('button, summary, [tabindex]'))
        .filter(node => !node.hidden && node.tabIndex >= 0);
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
  document.addEventListener('ora:process-run-inspector:open', event => {
    const detail = (event && event.detail) || {};
    open(detail.run_id, detail.trigger || null);
  });

  window.OraProcessRunInspector = { open, close, viewOrder: VIEW_ORDER.slice() };
})();
