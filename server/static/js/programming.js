/* Explicit standalone Programming UI.
 *
 * Ordinary Inquiry is untouched until the user turns Programming on. The
 * browser holds only the current proposal and progress view; repository and
 * Git state remain authoritative.
 */
(() => {
  let panel;
  let body;
  let repositoryInput;
  let button;
  let inputPane;
  const workflowsByConversation = new Map();
  let activeConversationId = '';
  let conversationSelectionEpoch = 0;

  const EMPTY_BODY_HTML = '<div class="programming-copy">Enter an objective in Inquiry. Ora will inspect first, propose one plan, and wait for approval.</div>';

  const observedConversationKey = () => {
    if (window.OraConversation
        && typeof window.OraConversation.getActiveConversationId === 'function') {
      return window.OraConversation.getActiveConversationId() || 'main';
    }
    if (window.OraSidebar && typeof window.OraSidebar.getActiveConversation === 'function') {
      return window.OraSidebar.getActiveConversation() || 'main';
    }
    return 'main';
  };

  const normalizeConversationKey = value => String(value || 'main');

  const workflowOwnsObservedDialogue = state => {
    const conversation = window.OraConversation;
    if (conversation && typeof conversation.getActiveConversationId === 'function') {
      return normalizeConversationKey(conversation.getActiveConversationId()) === state.id;
    }
    const sidebar = window.OraSidebar;
    if (sidebar && typeof sidebar.getActiveConversation === 'function') {
      return normalizeConversationKey(sidebar.getActiveConversation()) === state.id;
    }
    return true;
  };

  const createBody = () => {
    const node = document.createElement('div');
    node.className = 'programming-body';
    node.setAttribute('data-programming-body', '');
    node.innerHTML = EMPTY_BODY_HTML;
    return node;
  };

  const workflowFor = conversationId => {
    const key = normalizeConversationKey(conversationId);
    if (!workflowsByConversation.has(key)) {
      workflowsByConversation.set(key, {
        id: key,
        active: false,
        objective: '',
        proposal: null,
        questionRound: 0,
        planningAnswers: [],
        hooks: null,
        pendingAssistantMessages: [],
        repositoryPath: '',
        body: null,
      });
    }
    return workflowsByConversation.get(key);
  };

  activeConversationId = normalizeConversationKey(observedConversationKey());
  const currentWorkflow = () => workflowFor(activeConversationId);

  const escapeHtml = value => String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');

  const applyActiveState = state => {
    const active = !!state.active;
    if (active && document.querySelector('.left-column')?.classList.contains('collapsed')
        && window.OraLayout && typeof window.OraLayout.expandLeft === 'function') {
      window.OraLayout.expandLeft();
    }
    if (active && window.OraInputState
        && typeof window.OraInputState.clearSelection === 'function') {
      window.OraInputState.clearSelection();
    }
    if (panel) panel.hidden = !active;
    if (button) {
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    }
    if (inputPane) inputPane.classList.toggle('is-programming-active', active);
    document.dispatchEvent(new CustomEvent('ora:programming-mode-changed', {
      detail: { active, conversation_id: state.id },
    }));
  };

  const setActive = on => {
    const state = currentWorkflow();
    state.active = !!on;
    applyActiveState(state);
  };

  const mountWorkflow = state => {
    if (!panel || !repositoryInput) return;
    if (!state.body) state.body = createBody();
    if (body !== state.body) {
      if (body && body.parentNode) body.replaceWith(state.body);
      else panel.appendChild(state.body);
      body = state.body;
    }
    repositoryInput.value = state.repositoryPath || '';
    applyActiveState(state);
  };

  const switchConversation = (conversationId, reset = false) => {
    const previous = currentWorkflow();
    if (repositoryInput) previous.repositoryPath = repositoryInput.value || '';
    const nextId = normalizeConversationKey(conversationId || observedConversationKey());
    if (reset) workflowsByConversation.delete(nextId);
    activeConversationId = nextId;
    mountWorkflow(currentWorkflow());
  };

  const repositoryPathFor = state => {
    if (state === currentWorkflow() && repositoryInput) {
      state.repositoryPath = repositoryInput.value || '';
    }
    return String(state.repositoryPath || '').trim();
  };

  const adoptCurrentWorkflow = source => {
    const observedId = normalizeConversationKey(observedConversationKey());
    if (observedId !== activeConversationId) switchConversation(observedId);
    const target = currentWorkflow();
    if (target === source) return target;
    target.active = source.active;
    target.objective = source.objective;
    target.proposal = source.proposal;
    target.questionRound = source.questionRound;
    target.planningAnswers = source.planningAnswers.slice();
    target.hooks = source.hooks;
    target.pendingAssistantMessages = source.pendingAssistantMessages.slice();
    target.repositoryPath = repositoryPathFor(source);
    mountWorkflow(target);
    return target;
  };

  const status = (title, detail = '', state = currentWorkflow()) => {
    if (!state.body) state.body = createBody();
    state.body.innerHTML = `<div class="programming-status"><strong>${escapeHtml(title)}</strong>${detail ? `<p>${escapeHtml(detail)}</p>` : ''}</div>`;
  };

  const flushAssistantMessages = state => {
    if (normalizeConversationKey(observedConversationKey()) !== state.id
        || !state.hooks || typeof state.hooks.renderAssistant !== 'function') return;
    while (state.pendingAssistantMessages.length) {
      state.hooks.renderAssistant(state.pendingAssistantMessages.shift());
    }
  };

  const renderAssistantForWorkflow = (state, message) => {
    if (!state.hooks || typeof state.hooks.renderAssistant !== 'function') return;
    if (normalizeConversationKey(observedConversationKey()) === state.id) {
      state.hooks.renderAssistant(message);
      return;
    }
    state.pendingAssistantMessages.push(message);
  };

  const post = async (url, payload) => {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || `Request failed (${response.status})`);
    return result;
  };

  const checkPrivacy = async (
    text,
    draftText = '',
    accepted = () => {},
    state = currentWorkflow()
  ) => {
    const privacyText = String(text || '').trim();
    if (!privacyText) {
      accepted();
      return true;
    }
    const conversation = window.OraConversation;
    if (!conversation || typeof conversation.submitAfterPrivacy !== 'function') {
      status('Privacy check unavailable', 'Programming text was not sent.', state);
      return false;
    }
    return conversation.submitAfterPrivacy(
      privacyText, accepted, { draftText: String(draftText || '') }
    );
  };

  const requestPlan = async (
    privacyText = '',
    draftText = '',
    pendingAnswers = [],
    accepted = () => {},
    initialState = currentWorkflow()
  ) => {
    let state = initialState;
    const selectionEpoch = conversationSelectionEpoch;
    const hasPrivacyText = !!String(privacyText || '').trim();
    const repositoryPath = repositoryPathFor(state);
    if (!repositoryPath) {
      status('Repository required', 'Enter a repository name or Git worktree root before planning.', state);
      return false;
    }
    if (hasPrivacyText && !workflowOwnsObservedDialogue(initialState)) {
      return false;
    }
    let acceptedForState = false;
    if (!(await checkPrivacy(privacyText, draftText, () => {
      if (conversationSelectionEpoch !== selectionEpoch
          || activeConversationId !== initialState.id) return;
      state = hasPrivacyText ? adoptCurrentWorkflow(initialState) : initialState;
      accepted(state);
      acceptedForState = true;
    }, initialState)) || !acceptedForState) return false;
    if (pendingAnswers.length) {
      state.planningAnswers = state.planningAnswers.concat(pendingAnswers);
    }
    status('Inspecting repository', 'Reading instructions, implementation, tests, Git state, and live automation.', state);
    try {
      const result = await post('/api/programming/plan', {
        objective: state.objective,
        repository_path: repositoryPath,
        question_round: state.questionRound,
        answers: state.planningAnswers,
      });
      if (result.kind === 'questions') {
        state.questionRound = result.question_round;
        renderQuestions(result.questions || [], state);
      } else {
        state.proposal = result;
        renderPlan(state);
      }
    } catch (error) {
      status('Planning stopped', error.message || error, state);
    }
    return true;
  };

  const renderQuestions = (questions, state) => {
    const targetBody = state.body;
    targetBody.innerHTML = `
      <div class="programming-heading">Decision needed</div>
      <div class="programming-copy">Only answers that materially change scope, risk, authority, cost, or effects are requested.</div>
      <div class="programming-questions">
        ${questions.map((question, index) => `
          <label>${escapeHtml(question)}
            <textarea data-programming-answer="${index}" rows="2"></textarea>
          </label>`).join('')}
      </div>
      <button type="button" class="programming-primary" data-programming-continue>Continue planning</button>`;
    targetBody.querySelector('[data-programming-continue]').onclick = async () => {
      const newAnswers = questions.map((question, index) => ({
        question,
        answer: (targetBody.querySelector(`[data-programming-answer="${index}"]`).value || '').trim(),
      }));
      const privacyText = newAnswers.map((item) => item.answer).filter(Boolean).join('\n');
      await requestPlan(privacyText, '', newAnswers, () => {}, state);
    };
  };

  const renderPlan = state => {
    const targetBody = state.body;
    targetBody.innerHTML = `
      <div class="programming-heading">Proposed plan</div>
      <pre class="programming-plan">${escapeHtml(state.proposal.plan)}</pre>
      <div class="programming-actions">
        <button type="button" data-programming-cancel>Cancel</button>
        <button type="button" class="programming-primary" data-programming-approve>Approve and run</button>
      </div>`;
    targetBody.querySelector('[data-programming-cancel]').addEventListener('click', () => {
      state.proposal = null;
      state.questionRound = 0;
      state.planningAnswers = [];
      status('Plan cancelled', 'The repository was not changed.', state);
    });
    targetBody.querySelector('[data-programming-approve]').addEventListener('click', () => {
      runApprovedPlan('', '', state);
    });
  };

  const appendProgress = (event, state) => {
    const list = state.body.querySelector('[data-programming-progress]');
    if (!list) return;
    const row = document.createElement('div');
    row.className = 'programming-progress-row';
    if (event.type === 'review') {
      row.innerHTML = `<strong>${escapeHtml(event.outcome)}</strong> — ${escapeHtml(event.milestone || 'review')}${event.detail ? `<p>${escapeHtml(event.detail)}</p>` : ''}`;
    } else if (event.type === 'milestone') {
      row.textContent = `${event.milestone}: ${event.status}${event.commit ? ` (${event.commit.slice(0, 8)})` : ''}`;
    } else {
      row.textContent = event.message || event.detail || event.error || event.type;
    }
    list.appendChild(row);
    list.scrollTop = list.scrollHeight;
  };

  const renderDecision = (event, state) => {
    const coordinatedCorrection = event.coordinated_correction_required === true;
    if (coordinatedCorrection) {
      state.body.innerHTML = `
        <div class="programming-heading">Coordinated documentation correction required</div>
        <div class="programming-copy">${escapeHtml(event.detail || event.outcome)}</div>
        <div class="programming-copy">The submitted packet is cleared from this panel. Correct the participating task branches through the five-repository coordinator, then recover this task and submit fresh evidence.</div>`;
      return;
    }
    if (event.dcp_evidence_required === true) {
      const targetBody = state.body;
      targetBody.innerHTML = `
        <div class="programming-heading">Final documentation evidence required</div>
        <div class="programming-copy">${escapeHtml(event.detail || event.outcome)}</div>
        <label>Complete five-repository evidence packet (JSON)
          <textarea rows="10" data-programming-documentation-review></textarea>
        </label>
        <div class="programming-copy" data-programming-evidence-error aria-live="polite"></div>
        <div class="programming-actions">
          <button type="button" class="programming-primary" data-programming-resume>Resume final review</button>
        </div>`;
      targetBody.querySelector('[data-programming-resume]').addEventListener('click', () => {
        const input = targetBody.querySelector('[data-programming-documentation-review]');
        const error = targetBody.querySelector('[data-programming-evidence-error]');
        const raw = input ? (input.value || '').trim() : '';
        if (!raw) {
          error.textContent = 'Paste the complete evidence JSON before resuming.';
          return;
        }
        let packet;
        try {
          packet = JSON.parse(raw);
        } catch (_error) {
          error.textContent = 'The evidence packet is not valid JSON.';
          return;
        }
        if (!packet || typeof packet !== 'object' || Array.isArray(packet)) {
          error.textContent = 'The evidence packet must be one JSON object.';
          return;
        }
        runApprovedPlan(event.branch, '', state, packet, raw);
      });
      return;
    }
    const retryable = event.retryable === true;
    const targetBody = state.body;
    targetBody.innerHTML = `
      <div class="programming-heading">${retryable ? 'Finish line paused' : 'Decision needed'}</div>
      <div class="programming-copy">${escapeHtml(event.detail || event.outcome)}</div>
      ${retryable ? '' : '<textarea rows="3" data-programming-continuation></textarea>'}
      <div class="programming-actions">
        <button type="button" class="programming-primary" data-programming-resume>${retryable ? 'Retry finish line' : 'Resume approved plan'}</button>
      </div>`;
    targetBody.querySelector('[data-programming-resume]').addEventListener('click', () => {
      const input = targetBody.querySelector('[data-programming-continuation]');
      const answer = input ? (input.value || '').trim() : '';
      if (!retryable && !answer) {
        status('Decision required', 'Provide the decision before resuming.', state);
        return;
      }
      runApprovedPlan(event.branch, answer, state);
    });
  };

  const recoverApprovedPlan = async (state = currentWorkflow()) => {
    const repositoryPath = repositoryPathFor(state);
    if (!repositoryPath) {
      status('Repository required', 'Enter a repository name or Git worktree root before recovery.', state);
      return;
    }
    status('Recovering approved task', 'Reading the checked-out task branch, commits, and current diff.', state);
    try {
      const recovered = await post('/api/programming/recover', { repository_path: repositoryPath });
      state.objective = recovered.objective;
      state.proposal = recovered.plan;
      const accepted = (recovered.accepted_milestones || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
      state.body.innerHTML = `
        <div class="programming-heading">Approved task recovered</div>
        <pre class="programming-plan">${escapeHtml(state.proposal.plan)}</pre>
        ${accepted ? `<div class="programming-copy">Accepted milestones</div><ul>${accepted}</ul>` : ''}
        <div class="programming-copy">${recovered.has_uncommitted_changes ? 'Current uncommitted work will be checked for safe separation.' : 'Git worktree is clean.'}</div>
        <div class="programming-actions">
          <button type="button" class="programming-primary" data-programming-recover-resume>Resume approved plan</button>
        </div>`;
      state.body.querySelector('[data-programming-recover-resume]').addEventListener('click', () => {
        runApprovedPlan(recovered.branch, '', state);
      });
    } catch (error) {
      status('Recovery unavailable', error.message || error, state);
    }
  };

  const runApprovedPlan = async (
    resumeBranch = '',
    continuation = '',
    initialState = currentWorkflow(),
    documentationReview = null,
    documentationReviewText = ''
  ) => {
    let state = initialState;
    const selectionEpoch = conversationSelectionEpoch;
    const privacyText = String(documentationReviewText || continuation || '').trim();
    const hasPrivateInput = !!privacyText;
    const repositoryPath = repositoryPathFor(state);
    if (hasPrivateInput && !workflowOwnsObservedDialogue(initialState)) {
      return false;
    }
    let acceptedForState = false;
    if (!(await checkPrivacy(privacyText, '', () => {
      if (conversationSelectionEpoch !== selectionEpoch
          || activeConversationId !== initialState.id) return;
      state = hasPrivateInput ? adoptCurrentWorkflow(initialState) : initialState;
      acceptedForState = true;
    }, initialState)) || !acceptedForState) return false;
    state.body.innerHTML = `
      <div class="programming-heading">Programming in progress</div>
      <div class="programming-progress" data-programming-progress aria-live="polite"></div>`;
    try {
      const response = await fetch('/api/programming/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          objective: state.objective,
          repository_path: repositoryPath,
          plan: state.proposal,
          approved: true,
          resume_branch: resumeBranch || undefined,
          continuation,
          documentation_review: documentationReview || undefined,
        }),
      });
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload.error || `Request failed (${response.status})`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let pending = '';
      while (true) {
        const { value, done } = await reader.read();
        pending += decoder.decode(value || new Uint8Array(), { stream: !done });
        const lines = pending.split('\n');
        pending = lines.pop();
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);
          appendProgress(event, state);
          if (event.type === 'result') {
            renderAssistantForWorkflow(
              state,
              event.outcome === 'DONE' && event.reviewed_local_branches
                ? event.coordinated_finish_required === true
                  ? 'Final Documentation-Code Parity review accepted the five current local branches. The approved five-repository coordinator finish may now land only those exact reviewed heads.'
                  : 'Final Documentation-Code Parity review accepted the five current local branches. The approved finish stops locally; no push, pull request, or merge was performed.'
                : event.outcome === 'DONE'
                ? `Programming completed on ${event.branch}.`
                : event.coordinated_correction_required === true
                ? `Programming requires a coordinated five-repository correction before final review can resume: ${event.detail || event.outcome}`
                : event.dcp_evidence_required === true
                ? `Programming needs fresh final Documentation-Code Parity evidence for ${event.branch}.`
                : `Programming needs a decision: ${event.detail || event.outcome}.`
            );
          }
          if (event.type === 'result' && event.outcome !== 'DONE' && event.branch) {
            renderDecision(event, state);
          }
        }
        if (done) break;
      }
    } catch (error) {
      appendProgress({ type: 'error', error: error.message || String(error) }, state);
    }
    return true;
  };

  const submit = async (text, submissionHooks = {}) => {
    const state = currentWorkflow();
    if (!state.active) return false;
    const candidateObjective = String(text || '').trim();
    return requestPlan(candidateObjective, candidateObjective, [], approvedState => {
      approvedState.objective = candidateObjective;
      approvedState.hooks = submissionHooks;
      approvedState.proposal = null;
      approvedState.questionRound = 0;
      approvedState.planningAnswers = [];
      if (typeof approvedState.hooks.renderUser === 'function') {
        approvedState.hooks.renderUser(candidateObjective);
      }
    }, state);
  };

  const init = () => {
    if (panel) return;
    button = document.getElementById('inputToolbarProgramming');
    inputPane = document.querySelector('.input-pane');
    if (!button || !inputPane) return;
    panel = document.createElement('section');
    panel.className = 'programming-panel';
    panel.hidden = true;
    panel.innerHTML = `
      <div class="programming-panel-header">
        <strong>Programming</strong>
        <button type="button" aria-label="Close Programming" data-programming-close>×</button>
      </div>
      <label class="programming-repository">Repository
        <input type="text" placeholder="/absolute/path/to/git-worktree" data-programming-repository>
      </label>
      <button type="button" data-programming-recover>Recover approved task</button>
      <div class="programming-body" data-programming-body>
        ${EMPTY_BODY_HTML}
      </div>`;
    inputPane.appendChild(panel);
    body = panel.querySelector('[data-programming-body]');
    repositoryInput = panel.querySelector('[data-programming-repository]');
    const initialState = currentWorkflow();
    initialState.body = body;
    repositoryInput.value = initialState.repositoryPath;
    applyActiveState(initialState);
    panel.querySelector('[data-programming-recover]').addEventListener('click', () => {
      recoverApprovedPlan(currentWorkflow());
    });
    panel.querySelector('[data-programming-close]').addEventListener('click', () => setActive(false));
    document.addEventListener('ora:input-toolbar:programming', () => {
      setActive(!currentWorkflow().active);
    });
    document.addEventListener('ora:conversation-selected', (event) => {
      const id = event.detail && event.detail.conversation_id;
      conversationSelectionEpoch += 1;
      switchConversation(id || observedConversationKey());
    });
    document.addEventListener('ora:conversation-load-failed', (event) => {
      const id = event.detail && event.detail.active_conversation_id;
      conversationSelectionEpoch += 1;
      switchConversation(id || observedConversationKey());
      flushAssistantMessages(currentWorkflow());
    });
    document.addEventListener('ora:conversation-tag-changed', (event) => {
      const detail = event.detail || {};
      if (detail.source !== 'conversation-envelope') return;
      const state = workflowsByConversation.get(normalizeConversationKey(detail.conversation_id));
      if (state) flushAssistantMessages(state);
    });
    document.addEventListener('ora:fresh-conversation-started', (event) => {
      const id = event.detail && event.detail.conversation_id;
      conversationSelectionEpoch += 1;
      switchConversation(id || observedConversationKey(), true);
      flushAssistantMessages(currentWorkflow());
    });
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  window.OraProgramming = {
    isActive: () => currentWorkflow().active,
    setActive,
    submit,
    recover: () => recoverApprovedPlan(currentWorkflow()),
  };
})();
