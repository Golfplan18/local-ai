/* Explicit standalone Programming UI.
 *
 * Ordinary Inquiry is untouched until the user turns Programming on. The
 * browser holds only the current proposal and progress view; repository and
 * Git state remain authoritative.
 */
(() => {
  let active = false;
  let objective = '';
  let proposal = null;
  let questionRound = 0;
  let planningAnswers = [];
  let hooks = null;
  let panel;
  let body;
  let repositoryInput;
  let button;
  let inputPane;

  const escapeHtml = value => String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');

  const setActive = on => {
    active = !!on;
    if (panel) panel.hidden = !active;
    if (button) {
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    }
    if (inputPane) inputPane.classList.toggle('is-programming-active', active);
  };

  const status = (title, detail = '') => {
    if (!body) return;
    body.innerHTML = `<div class="programming-status"><strong>${escapeHtml(title)}</strong>${detail ? `<p>${escapeHtml(detail)}</p>` : ''}</div>`;
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

  const checkPrivacy = async (text, draftText = '', accepted = () => {}) => {
    const privacyText = String(text || '').trim();
    if (!privacyText) {
      accepted();
      return true;
    }
    const conversation = window.OraConversation;
    if (!conversation || typeof conversation.submitAfterPrivacy !== 'function') {
      status('Privacy check unavailable', 'Programming text was not sent.');
      return false;
    }
    return conversation.submitAfterPrivacy(
      privacyText, accepted, { draftText: String(draftText || '') }
    );
  };

  const requestPlan = async (privacyText = '', draftText = '', pendingAnswers = [], accepted = () => {}) => {
    const repositoryPath = (repositoryInput && repositoryInput.value || '').trim();
    if (!repositoryPath) {
      status('Repository required', 'Enter a repository name or Git worktree root before planning.');
      return false;
    }
    if (!(await checkPrivacy(privacyText, draftText, accepted))) return false;
    if (pendingAnswers.length) planningAnswers = planningAnswers.concat(pendingAnswers);
    status('Inspecting repository', 'Reading instructions, implementation, tests, Git state, and live automation.');
    try {
      const result = await post('/api/programming/plan', {
        objective,
        repository_path: repositoryPath,
        question_round: questionRound,
        answers: planningAnswers,
      });
      if (result.kind === 'questions') {
        questionRound = result.question_round;
        renderQuestions(result.questions || []);
      } else {
        proposal = result;
        renderPlan();
      }
    } catch (error) {
      status('Planning stopped', error.message || error);
    }
    return true;
  };

  const renderQuestions = questions => {
    body.innerHTML = `
      <div class="programming-heading">Decision needed</div>
      <div class="programming-copy">Only answers that materially change scope, risk, authority, cost, or effects are requested.</div>
      <div class="programming-questions">
        ${questions.map((question, index) => `
          <label>${escapeHtml(question)}
            <textarea data-programming-answer="${index}" rows="2"></textarea>
          </label>`).join('')}
      </div>
      <button type="button" class="programming-primary" data-programming-continue>Continue planning</button>`;
    body.querySelector('[data-programming-continue]').onclick = async () => {
      const newAnswers = questions.map((question, index) => ({
        question,
        answer: (body.querySelector(`[data-programming-answer="${index}"]`).value || '').trim(),
      }));
      const privacyText = newAnswers.map((item) => item.answer).filter(Boolean).join('\n');
      await requestPlan(privacyText, '', newAnswers);
    };
  };

  const renderPlan = () => {
    body.innerHTML = `
      <div class="programming-heading">Proposed plan</div>
      <pre class="programming-plan">${escapeHtml(proposal.plan)}</pre>
      <div class="programming-actions">
        <button type="button" data-programming-cancel>Cancel</button>
        <button type="button" class="programming-primary" data-programming-approve>Approve and run</button>
      </div>`;
    body.querySelector('[data-programming-cancel]').addEventListener('click', () => {
      proposal = null;
      questionRound = 0;
      planningAnswers = [];
      status('Plan cancelled', 'The repository was not changed.');
    });
    body.querySelector('[data-programming-approve]').addEventListener('click', () => runApprovedPlan());
  };

  const appendProgress = event => {
    const list = body.querySelector('[data-programming-progress]');
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

  const renderDecision = event => {
    const retryable = event.retryable === true;
    body.innerHTML = `
      <div class="programming-heading">${retryable ? 'Finish line paused' : 'Decision needed'}</div>
      <div class="programming-copy">${escapeHtml(event.detail || event.outcome)}</div>
      ${retryable ? '' : '<textarea rows="3" data-programming-continuation></textarea>'}
      <div class="programming-actions">
        <button type="button" class="programming-primary" data-programming-resume>${retryable ? 'Retry finish line' : 'Resume approved plan'}</button>
      </div>`;
    body.querySelector('[data-programming-resume]').addEventListener('click', () => {
      const input = body.querySelector('[data-programming-continuation]');
      const answer = input ? (input.value || '').trim() : '';
      if (!retryable && !answer) {
        status('Decision required', 'Provide the decision before resuming.');
        return;
      }
      runApprovedPlan(event.branch, answer);
    });
  };

  const recoverApprovedPlan = async () => {
    const repositoryPath = (repositoryInput && repositoryInput.value || '').trim();
    if (!repositoryPath) {
      status('Repository required', 'Enter a repository name or Git worktree root before recovery.');
      return;
    }
    status('Recovering approved task', 'Reading the checked-out task branch, commits, and current diff.');
    try {
      const recovered = await post('/api/programming/recover', { repository_path: repositoryPath });
      objective = recovered.objective;
      proposal = recovered.plan;
      const accepted = (recovered.accepted_milestones || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
      body.innerHTML = `
        <div class="programming-heading">Approved task recovered</div>
        <pre class="programming-plan">${escapeHtml(proposal.plan)}</pre>
        ${accepted ? `<div class="programming-copy">Accepted milestones</div><ul>${accepted}</ul>` : ''}
        <div class="programming-copy">${recovered.has_uncommitted_changes ? 'Current uncommitted work will be checked for safe separation.' : 'Git worktree is clean.'}</div>
        <div class="programming-actions">
          <button type="button" class="programming-primary" data-programming-recover-resume>Resume approved plan</button>
        </div>`;
      body.querySelector('[data-programming-recover-resume]').addEventListener('click', () => {
        runApprovedPlan(recovered.branch);
      });
    } catch (error) {
      status('Recovery unavailable', error.message || error);
    }
  };

  const runApprovedPlan = async (resumeBranch = '', continuation = '') => {
    const repositoryPath = (repositoryInput.value || '').trim();
    if (!(await checkPrivacy(continuation))) return false;
    body.innerHTML = `
      <div class="programming-heading">Programming in progress</div>
      <div class="programming-progress" data-programming-progress aria-live="polite"></div>`;
    try {
      const response = await fetch('/api/programming/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          objective,
          repository_path: repositoryPath,
          plan: proposal,
          approved: true,
          resume_branch: resumeBranch || undefined,
          continuation,
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
          appendProgress(event);
          if (event.type === 'result' && hooks && hooks.renderAssistant) {
            hooks.renderAssistant(
              event.outcome === 'DONE'
                ? `Programming completed on ${event.branch}.`
                : `Programming needs a decision: ${event.detail || event.outcome}.`
            );
          }
          if (event.type === 'result' && event.outcome !== 'DONE' && event.branch) {
            renderDecision(event);
          }
        }
        if (done) break;
      }
    } catch (error) {
      appendProgress({ type: 'error', error: error.message || String(error) });
    }
    return true;
  };

  const submit = async (text, submissionHooks = {}) => {
    if (!active) return false;
    const candidateObjective = String(text || '').trim();
    return requestPlan(candidateObjective, candidateObjective, [], () => {
      objective = candidateObjective;
      hooks = submissionHooks;
      proposal = null;
      questionRound = 0;
      planningAnswers = [];
    });
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
        <div class="programming-copy">Enter an objective in Inquiry. Ora will inspect first, propose one plan, and wait for approval.</div>
      </div>`;
    inputPane.appendChild(panel);
    body = panel.querySelector('[data-programming-body]');
    repositoryInput = panel.querySelector('[data-programming-repository]');
    panel.querySelector('[data-programming-recover]').addEventListener('click', recoverApprovedPlan);
    panel.querySelector('[data-programming-close]').addEventListener('click', () => setActive(false));
    document.addEventListener('ora:input-toolbar:programming', () => setActive(!active));
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  window.OraProgramming = { isActive: () => active, setActive, submit, recover: recoverApprovedPlan };
})();
