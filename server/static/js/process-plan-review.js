/* G1.1 Phase 3.3 — browser management interview and canonical plan review.
 *
 * Governed construction uses /chat's authenticated management contracts. The
 * client never constructs a canonical plan or trusts a rendered projection as
 * authority: it submits exact question/action identities, then renders only
 * the server-returned interview, plan, approval, and delegation state.
 */
(function () {
  'use strict';

  const CHAT_URL = '/chat';
  let overlay = null;
  let origin = null;
  let selectedView = 'principal';
  let pendingReasonAction = null;
  let state = {
    dialogueId: null,
    interview: null,
    plan: null,
    delegation: null,
    planningContext: null,
    busy: false,
    error: '',
  };

  function activeDialogueId() {
    return window.OraConversation
      && typeof window.OraConversation.getActiveConversationId === 'function'
      ? window.OraConversation.getActiveConversationId() : null;
  }

  function activeTag() {
    return window.OraConversation
      && typeof window.OraConversation.getActiveTag === 'function'
      ? window.OraConversation.getActiveTag() : '';
  }

  function hashText(value) {
    let hash = 2166136261;
    const text = String(value || '');
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(16).padStart(8, '0');
  }

  function planRef(plan) {
    return {
      plan_id: plan.plan_id,
      version: plan.version,
      digest: plan.digest,
    };
  }

  function idempotency(action, identity, extra) {
    return `plan-ui:${action}:${hashText(JSON.stringify(identity || {}) + '|' + String(extra || ''))}`;
  }

  function reset(nextDialogueId) {
    state = {
      dialogueId: nextDialogueId || null,
      interview: null,
      plan: null,
      delegation: null,
      planningContext: null,
      busy: false,
      error: '',
    };
    selectedView = 'principal';
    pendingReasonAction = null;
  }

  function ensureOverlay() {
    if (overlay) return;
    overlay = document.createElement('div');
    overlay.className = 'process-plan-review';
    overlay.hidden = true;
    overlay.innerHTML = [
      '<div class="process-plan-review__backdrop" data-plan-review-close></div>',
      '<section class="process-plan-review__dialog" role="dialog" aria-modal="true" aria-labelledby="processPlanReviewTitle">',
      '  <header class="process-plan-review__header">',
      '    <div>',
      '      <div class="process-plan-review__kicker">Governed Process</div>',
      '      <h2 id="processPlanReviewTitle">Management review</h2>',
      '    </div>',
      '    <button class="process-plan-review__close" type="button" aria-label="Close management review" data-plan-review-close>×</button>',
      '  </header>',
      '  <div class="process-plan-review__status" aria-live="polite"></div>',
      '  <div class="process-plan-review__error" role="alert" hidden></div>',
      '  <div class="process-plan-review__body"></div>',
      '</section>',
    ].join('');
    document.body.appendChild(overlay);
    overlay.querySelectorAll('[data-plan-review-close]').forEach((node) => {
      node.addEventListener('click', close);
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && overlay && !overlay.hidden) {
        event.preventDefault();
        close();
      }
    });
  }

  function open(nextOrigin) {
    ensureOverlay();
    origin = nextOrigin || document.activeElement || origin;
    render();
    overlay.hidden = false;
    const focusable = overlay.querySelector('textarea, input, button:not(:disabled)');
    if (focusable) setTimeout(() => focusable.focus(), 0);
  }

  function close() {
    if (!overlay) return;
    overlay.hidden = true;
    if (origin && typeof origin.focus === 'function') origin.focus();
  }

  function setError(message) {
    state.error = String(message || '');
    if (!overlay) return;
    const node = overlay.querySelector('.process-plan-review__error');
    node.textContent = state.error;
    node.hidden = !state.error;
  }

  async function responseJson(response) {
    let payload = null;
    try { payload = await response.json(); } catch (_) { payload = {}; }
    if (!response.ok) {
      const error = new Error(
        payload.error || payload.failure_summary || `Request failed (HTTP ${response.status})`
      );
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  async function fetchJson(url, options) {
    return responseJson(await fetch(url, options));
  }

  function clearPerInputState() {
    if (window.OraInputState) {
      if (typeof window.OraInputState.clearFramework === 'function') {
        window.OraInputState.clearFramework();
      }
      if (typeof window.OraInputState.clearAnalysisMode === 'function') {
        window.OraInputState.clearAnalysisMode();
      }
    }
    if (window.OraInputAttachments
        && typeof window.OraInputAttachments.clear === 'function') {
      window.OraInputAttachments.clear();
    }
  }

  async function chat(message, contract) {
    if (!state.dialogueId) throw new Error('No active Dialogue is bound to management review.');
    const request = {
      message: String(message || '').trim() || 'Continue governed management review.',
      conversation_id: state.dialogueId,
      panel_id: state.dialogueId,
      is_main_feed: true,
      tag: activeTag(),
      history: [],
    };
    Object.keys(contract || {}).forEach((key) => { request[key] = contract[key]; });
    state.busy = true;
    state.error = '';
    render();
    try {
      const payload = await fetchJson(CHAT_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });
      if (payload.management_interview) {
        state.interview = payload.management_interview;
        state.plan = null;
        state.delegation = null;
      }
      if (payload.process_plan) {
        state.plan = payload.process_plan;
        state.interview = null;
        state.delegation = payload.process_plan.delegation || null;
      }
      if (state.interview && state.interview.status === 'ready_for_plan') {
        await loadPlanningContext();
      }
      return payload;
    } catch (error) {
      setError(error.message || error);
      throw error;
    } finally {
      state.busy = false;
      render();
    }
  }

  async function begin(objective, request, routeContract, nextOrigin) {
    if (!routeContract || routeContract.intent !== 'capability_construction') {
      return false;
    }
    const dialogueId = activeDialogueId();
    if (!dialogueId) throw new Error('A Dialogue is required for governed construction.');
    reset(dialogueId);
    origin = nextOrigin || document.activeElement || null;
    clearPerInputState();
    try {
      await chat(objective, { process_entry_request: request });
      open(origin);
      return true;
    } catch (error) {
      open(origin);
      return true;
    }
  }

  async function submitInterviewAnswer(answer) {
    const interview = state.interview;
    const question = interview && interview.current_question;
    const normalized = String(answer || '').trim();
    if (!question || !normalized) {
      setError('Answer the current management question before continuing.');
      return;
    }
    const answerIdentity = `${question.question_id}|${normalized}`;
    try {
      await chat(normalized, {
        management_interview_answer: {
          question_id: question.question_id,
          idempotency_key: `interview-ui:${hashText(answerIdentity)}`,
        },
      });
    } catch (_) {}
  }

  async function loadPlanningContext() {
    if (!state.dialogueId) return;
    try {
      const payload = await fetchJson(
        `/api/process-plan-context/${encodeURIComponent(state.dialogueId)}`
      );
      state.planningContext = payload.planning_context || null;
    } catch (error) {
      state.planningContext = null;
      setError(error.message || error);
    }
  }

  function currentPlan() {
    return state.plan && state.plan.current_plan;
  }

  function currentTargetPath() {
    const plan = currentPlan();
    if (plan && plan.repository_artifact_scope && plan.repository_artifact_scope.target) {
      return ((plan.repository_artifact_scope.target.locator || {}).ref) || '';
    }
    return (state.planningContext && state.planningContext.suggested_target_path) || '';
  }

  function currentSelectors() {
    const plan = currentPlan();
    return plan && plan.repository_artifact_scope
      ? (plan.repository_artifact_scope.declared_scope || []) : [];
  }

  async function propose(targetPath, selectors) {
    const identity = {
      dialogue: state.dialogueId,
      target_path: targetPath,
      artifact_selectors: selectors,
      prior_plan: currentPlan() ? planRef(currentPlan()) : null,
    };
    try {
      await chat('Prepare the exact canonical plan for review.', {
        management_plan: {
          action: 'propose',
          target_path: targetPath,
          artifact_selectors: selectors,
          planner_id: 'planner:programming',
          idempotency_key: idempotency('propose', identity),
        },
      });
    } catch (_) {}
  }

  function reasonLabel(action) {
    if (action === 'request_changes') return 'What material plan change is required?';
    if (action === 'change_scope_or_permissions') return 'What scope or permission must change?';
    return 'Why should this Run stop while retaining the plan?';
  }

  async function applyPlanAction(action, reason) {
    const plan = currentPlan();
    if (!plan) {
      setError('The authoritative current plan is unavailable. Reload before deciding.');
      return;
    }
    const ref = planRef(plan);
    const payload = {
      action,
      plan_ref: ref,
      idempotency_key: idempotency(action, ref, reason || ''),
    };
    let message = '';
    if (action === 'approve_and_start' || action === 'approve_without_start') {
      payload.baseline_digest = plan.repository_artifact_scope.target.identity.digest;
      payload.decision_by = 'principal:user';
      message = action === 'approve_and_start'
        ? 'Approve this exact plan and start.' : 'Approve this exact plan without starting.';
    } else if (action === 'delegate') {
      const lifecycle = state.plan && state.plan.dialogue_lifecycle;
      payload.approval_receipt_digest = lifecycle && lifecycle.approval_receipt_digest;
      payload.requested_by = 'principal:user';
      message = 'Start the exact approved plan.';
    } else {
      payload.reason = String(reason || '').trim();
      if (!payload.reason) {
        setError(reasonLabel(action));
        return;
      }
      if (action === 'stop_and_retain') payload.decision_by = 'principal:user';
      message = action === 'request_changes'
        ? 'Request plan changes.'
        : (action === 'change_scope_or_permissions'
          ? 'Change scope or permissions.' : 'Stop and retain the plan.');
    }
    try {
      await chat(message, { management_plan: payload });
      pendingReasonAction = null;
    } catch (_) {}
  }

  function appendValue(container, value) {
    if (Array.isArray(value)) {
      const list = document.createElement('ul');
      value.forEach((item) => {
        const row = document.createElement('li');
        if (item && typeof item === 'object') {
          const pre = document.createElement('pre');
          pre.textContent = JSON.stringify(item, null, 2);
          row.appendChild(pre);
        } else {
          row.textContent = String(item);
        }
        list.appendChild(row);
      });
      container.appendChild(list);
      return;
    }
    if (value && typeof value === 'object') {
      const pre = document.createElement('pre');
      pre.textContent = JSON.stringify(value, null, 2);
      container.appendChild(pre);
      return;
    }
    const text = document.createElement('p');
    text.textContent = String(value == null ? '' : value);
    container.appendChild(text);
  }

  function renderProjection(container, projection) {
    const content = (projection && projection.content) || {};
    Object.keys(content).forEach((key) => {
      const section = document.createElement('section');
      section.className = 'process-plan-review__field';
      const heading = document.createElement('h3');
      heading.textContent = key.replace(/_/g, ' ').replace(/^./, (char) => char.toUpperCase());
      section.appendChild(heading);
      appendValue(section, content[key]);
      container.appendChild(section);
    });
  }

  function button(label, action, className) {
    const node = document.createElement('button');
    node.type = 'button';
    node.textContent = label;
    node.dataset.planAction = action;
    node.className = `process-plan-review__button ${className || ''}`.trim();
    node.disabled = state.busy;
    return node;
  }

  function renderInterview(body) {
    const interview = state.interview;
    overlay.querySelector('#processPlanReviewTitle').textContent = 'Management interview';
    if (interview.status === 'ready_for_plan') {
      renderPreparation(body);
      return;
    }
    const question = interview.current_question;
    if (!question) {
      const empty = document.createElement('p');
      empty.textContent = 'Ora is reconstructing the current management question.';
      body.appendChild(empty);
      return;
    }
    const progress = document.createElement('p');
    progress.className = 'process-plan-review__progress';
    progress.textContent = `${interview.resolved_dimensions.length} of ${interview.dimensions.length} management dimensions resolved`;
    body.appendChild(progress);
    const prompt = document.createElement('h3');
    prompt.textContent = question.prompt;
    body.appendChild(prompt);
    const consequence = document.createElement('p');
    consequence.textContent = question.consequence;
    body.appendChild(consequence);
    if (interview.input_required) {
      const notice = document.createElement('p');
      notice.className = 'process-plan-review__notice';
      notice.textContent = interview.input_required.reason;
      body.appendChild(notice);
    }
    const answer = document.createElement('textarea');
    answer.className = 'process-plan-review__answer';
    answer.rows = 5;
    answer.placeholder = 'Give a concrete management answer…';
    answer.disabled = state.busy;
    body.appendChild(answer);
    const actions = document.createElement('div');
    actions.className = 'process-plan-review__actions';
    const submit = button('Continue interview', 'answer', 'process-plan-review__button--primary');
    submit.addEventListener('click', () => submitInterviewAnswer(answer.value));
    actions.appendChild(submit);
    body.appendChild(actions);
  }

  function renderPreparation(body) {
    overlay.querySelector('#processPlanReviewTitle').textContent = currentPlan()
      ? 'Prepare revised plan' : 'Prepare canonical plan';
    const intro = document.createElement('p');
    intro.textContent = (
      'Confirm the exact target folder and target-relative items. Ora derives the '
      + 'canonical plan from the persisted management interview, authenticates the '
      + 'current target, and then shows both review projections before any approval.'
    );
    body.appendChild(intro);
    const targetLabel = document.createElement('label');
    targetLabel.textContent = 'Exact target folder';
    const target = document.createElement('input');
    target.type = 'text';
    target.className = 'process-plan-review__target';
    target.value = currentTargetPath();
    target.placeholder = '/absolute/path/to/target';
    target.disabled = state.busy;
    targetLabel.appendChild(target);
    body.appendChild(targetLabel);
    const scopeLabel = document.createElement('label');
    scopeLabel.textContent = 'Exact target items (one relative path per line)';
    const scope = document.createElement('textarea');
    scope.className = 'process-plan-review__scope';
    scope.rows = 5;
    scope.value = currentSelectors().join('\n');
    scope.placeholder = 'src/example.py\ntests/test_example.py';
    scope.disabled = state.busy;
    scopeLabel.appendChild(scope);
    body.appendChild(scopeLabel);
    const actions = document.createElement('div');
    actions.className = 'process-plan-review__actions';
    const prepare = button('Prepare plan', 'propose', 'process-plan-review__button--primary');
    prepare.addEventListener('click', () => {
      const selectors = scope.value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
      if (!target.value.trim() || !selectors.length) {
        setError('Confirm an exact target folder and at least one target-relative item.');
        return;
      }
      propose(target.value.trim(), selectors);
    });
    actions.appendChild(prepare);
    body.appendChild(actions);
  }

  function renderReasonPanel(body) {
    const panel = document.createElement('div');
    panel.className = 'process-plan-review__reason-panel';
    const label = document.createElement('label');
    label.textContent = reasonLabel(pendingReasonAction);
    const input = document.createElement('textarea');
    input.rows = 4;
    input.disabled = state.busy;
    label.appendChild(input);
    panel.appendChild(label);
    const actions = document.createElement('div');
    actions.className = 'process-plan-review__actions';
    const confirm = button('Submit decision', 'submit-reason', 'process-plan-review__button--primary');
    const cancel = button('Cancel', 'cancel-reason', '');
    confirm.addEventListener('click', () => applyPlanAction(pendingReasonAction, input.value));
    cancel.addEventListener('click', () => {
      pendingReasonAction = null;
      render();
    });
    actions.append(confirm, cancel);
    panel.appendChild(actions);
    body.appendChild(panel);
  }

  function renderPlan(body) {
    const planState = state.plan;
    const plan = currentPlan();
    overlay.querySelector('#processPlanReviewTitle').textContent = 'Plan review';
    if (!plan) {
      const message = document.createElement('p');
      message.textContent = 'The authoritative plan is unavailable.';
      body.appendChild(message);
      return;
    }
    const identity = document.createElement('p');
    identity.className = 'process-plan-review__identity';
    identity.textContent = `${plan.plan_id} · version ${plan.version} · ${plan.digest}`;
    body.appendChild(identity);

    if (planState.status === 'revision_requested' || planState.status === 'stale') {
      const notice = document.createElement('div');
      notice.className = 'process-plan-review__notice';
      const requests = planState.revision_requests || [];
      const latestRequest = requests.length ? requests[requests.length - 1] : null;
      notice.textContent = planState.status === 'stale'
        ? 'This plan is stale because the authenticated target or instructions changed. Approval is withheld.'
        : (
          'Your requested change is recorded. Prepare a new plan version before approval.'
          + (latestRequest && latestRequest.reason ? ` Required change: ${latestRequest.reason}` : '')
        );
      body.appendChild(notice);
      renderPreparation(body);
      return;
    }

    const tabs = document.createElement('div');
    tabs.className = 'process-plan-review__tabs';
    ['principal', 'technical'].forEach((name) => {
      const tab = document.createElement('button');
      tab.type = 'button';
      tab.textContent = name === 'principal' ? 'Principal view' : 'Technical view';
      tab.dataset.planView = name;
      tab.setAttribute('aria-selected', selectedView === name ? 'true' : 'false');
      tab.addEventListener('click', () => {
        selectedView = name;
        render();
      });
      tabs.appendChild(tab);
    });
    body.appendChild(tabs);
    const projection = document.createElement('div');
    projection.className = 'process-plan-review__projection';
    renderProjection(
      projection,
      selectedView === 'technical' ? plan.technical_view : plan.principal_view
    );
    body.appendChild(projection);

    if (planState.status === 'awaiting_approval') {
      const actions = document.createElement('div');
      actions.className = 'process-plan-review__actions process-plan-review__actions--decision';
      const definitions = [
        ['Approve and start', 'approve_and_start', 'process-plan-review__button--primary'],
        ['Approve without starting', 'approve_without_start', ''],
        ['Request plan changes', 'request_changes', ''],
        ['Change scope or permissions', 'change_scope_or_permissions', ''],
        ['Stop and retain the plan', 'stop_and_retain', 'process-plan-review__button--danger'],
      ];
      definitions.forEach(([label, action, className]) => {
        const node = button(label, action, className);
        node.addEventListener('click', () => {
          if (['request_changes', 'change_scope_or_permissions', 'stop_and_retain'].includes(action)) {
            pendingReasonAction = action;
            render();
          } else {
            applyPlanAction(action);
          }
        });
        actions.appendChild(node);
      });
      body.appendChild(actions);
      if (pendingReasonAction) renderReasonPanel(body);
      return;
    }

    if (planState.status === 'approved') {
      const delegation = state.delegation || planState.delegation;
      const notice = document.createElement('div');
      notice.className = 'process-plan-review__notice';
      notice.textContent = delegation && delegation.status === 'delegated'
        ? 'The exact approved plan is delegated and positioned at execution preflight.'
        : 'The plan is approved. Execution remains withheld until you start this exact approval.';
      body.appendChild(notice);
      if (!delegation || delegation.status !== 'delegated') {
        const actions = document.createElement('div');
        actions.className = 'process-plan-review__actions';
        const start = button('Start approved plan', 'delegate', 'process-plan-review__button--primary');
        start.addEventListener('click', () => applyPlanAction('delegate'));
        actions.appendChild(start);
        body.appendChild(actions);
      }
      return;
    }

    if (planState.status === 'retained') {
      const retained = document.createElement('div');
      retained.className = 'process-plan-review__notice';
      retained.textContent = 'The Run stopped without execution and retained this reviewed plan.';
      body.appendChild(retained);
    }
  }

  function render() {
    if (!overlay) return;
    const status = overlay.querySelector('.process-plan-review__status');
    const body = overlay.querySelector('.process-plan-review__body');
    status.textContent = state.busy ? 'Recording exact governed state…' : '';
    body.innerHTML = '';
    setError(state.error);
    if (state.plan) renderPlan(body);
    else if (state.interview) renderInterview(body);
    else {
      overlay.querySelector('#processPlanReviewTitle').textContent = 'Management review';
      const empty = document.createElement('p');
      empty.textContent = 'No active governed management state is bound to this Dialogue.';
      body.appendChild(empty);
    }
  }

  function activeState() {
    if (state.interview) return true;
    if (!state.plan) return false;
    return !['retained'].includes(state.plan.status)
      && !['completed', 'blocked'].includes(state.plan.run_state);
  }

  async function hydrate(dialogueId, options) {
    const id = String(dialogueId || '').trim();
    if (!id) return false;
    if (state.dialogueId !== id) reset(id);
    state.error = '';
    try {
      const planPayload = await fetchJson(`/api/process-plan/${encodeURIComponent(id)}`);
      state.plan = planPayload.plan;
      state.interview = null;
      state.delegation = null;
      if (state.plan && state.plan.status === 'approved') {
        try {
          const delegationPayload = await fetchJson(
            `/api/process-delegation/${encodeURIComponent(id)}`
          );
          state.delegation = delegationPayload.delegation || null;
        } catch (error) {
          if (error.status !== 404) throw error;
        }
      }
    } catch (planError) {
      if (planError.status !== 404) {
        state.error = planError.message;
        if (options && options.open) open(options.origin);
        return false;
      }
      try {
        const interviewPayload = await fetchJson(
          `/api/process-interview/${encodeURIComponent(id)}`
        );
        state.interview = interviewPayload.interview;
        state.plan = null;
        if (state.interview.status === 'ready_for_plan') await loadPlanningContext();
      } catch (interviewError) {
        if (interviewError.status !== 404) state.error = interviewError.message;
        else reset(id);
      }
    }
    if (options && options.open && (activeState() || state.error)) {
      open(options.origin);
    }
    return activeState();
  }

  async function ensureActive(dialogueId) {
    const id = String(dialogueId || '').trim();
    if (!id) return false;
    if (state.dialogueId === id && activeState()) return true;
    return hydrate(id, { open: false });
  }

  function init() {
    ensureOverlay();
    document.addEventListener('ora:fresh-conversation-started', (event) => {
      reset((event.detail || {}).conversation_id || null);
      close();
    });
    document.addEventListener('ora:conversation-tag-changed', (event) => {
      const detail = event.detail || {};
      if (detail.source !== 'conversation-envelope' || !detail.conversation_id) return;
      hydrate(detail.conversation_id, { open: true });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.OraProcessPlanReview = {
    begin,
    ensureActive,
    hydrate,
    open,
    close,
    isActive: activeState,
    _state: () => state,
  };
}());
