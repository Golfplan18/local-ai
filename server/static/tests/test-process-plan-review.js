#!/usr/bin/env node
/* G1.1 Phase 3.3 — real browser management interview and plan controls. */

'use strict';

var path = require('path');
var JSDOM_PATH = path.join(
  __dirname, '..', 'ora-visual-compiler', 'tests', 'node_modules', 'jsdom'
);
var jsdom;
try {
  jsdom = require(JSDOM_PATH);
} catch (error) {
  console.error('error: jsdom not available at ' + JSDOM_PATH);
  process.exit(2);
}

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body><textarea id="inquiry"></textarea></body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true }
);
var w = dom.window;
global.window = w;
global.document = w.document;
global.HTMLElement = w.HTMLElement;
global.Event = w.Event;
global.CustomEvent = w.CustomEvent;

w.OraConversation = {
  getActiveConversationId: function () { return 'dialogue-plan'; },
  getActiveTag: function () { return 'private'; },
};
var cleared = { framework: 0, mode: 0, attachments: 0 };
w.OraInputState = {
  clearFramework: function () { cleared.framework += 1; },
  clearAnalysisMode: function () { cleared.mode += 1; },
};
w.OraInputAttachments = {
  clear: function () { cleared.attachments += 1; },
};

var PLAN_REF = {
  plan_id: 'plan:dialogue-plan',
  version: 1,
  digest: 'sha256:' + 'a'.repeat(64),
};

function projection(kind) {
  return {
    plan_ref: PLAN_REF,
    content: kind === 'principal'
      ? {
          outcome: 'A reconciled weekly cash-flow report.',
          users: 'The finance team.',
          scope: ['report.py', 'tests/test_report.py'],
          authority: ['mutate', 'test'],
          risks: ['Incorrect totals.'],
          exceptions: ['Stop on variance.'],
          proof: ['Reconciliation tests pass.'],
          activation: 'Separate approval required.',
        }
      : {
          artifacts: ['report.py', 'tests/test_report.py'],
          architecture: ['Preserve boundaries.'],
          dependencies: ['Existing runtime.'],
          implementation_sequence: [{ step_id: 'step-report', action: 'mutate' }],
          tests: ['Run reconciliation tests.'],
          evidence: ['Exact post-change identity.'],
          versioning: ['New version on material change.'],
          recovery: ['Restore checkpoint.'],
        },
  };
}

function planState(status, extra) {
  var value = {
    status: status,
    run_state: status === 'retained' ? 'blocked' : 'running',
    dialogue_lifecycle: status === 'approved' ? {
      state: 'plan:approved',
      plan_ref: PLAN_REF,
      approval_receipt_digest: 'sha256:' + 'b'.repeat(64),
    } : {
      state: 'plan:in-planning',
      plan_ref: PLAN_REF,
    },
    current_plan: {
      plan_id: PLAN_REF.plan_id,
      version: PLAN_REF.version,
      digest: PLAN_REF.digest,
      repository_artifact_scope: {
        target: {
          locator: { kind: 'filesystem', ref: '/tmp/approved-target' },
          identity: { digest: 'sha256:' + 'c'.repeat(64) },
        },
        declared_scope: ['report.py', 'tests/test_report.py'],
      },
      principal_view: projection('principal'),
      technical_view: projection('technical'),
    },
  };
  return Object.assign(value, extra || {});
}

function interviewState(status) {
  return {
    status: status,
    run_id: 'run-plan',
    binding_digest: 'sha256:' + 'd'.repeat(64),
    answers_digest: 'sha256:' + 'e'.repeat(64),
    project_ref: 'ora',
    dimensions: ['intended_result', 'affected_parties'],
    resolved_dimensions: status === 'ready_for_plan' ? ['intended_result', 'affected_parties'] : [],
    current_question: status === 'ready_for_plan' ? null : {
      question_id: 'question:intended-result:1',
      dimension: 'intended_result',
      prompt: 'What exact result should exist?',
      consequence: 'This result bounds the plan.',
    },
  };
}

var requests = [];
var remotePlan = null;
var remoteInterview = null;
var remoteDelegation = null;
var remoteAuthoring = null;
var failNext = false;

function authoringState(status) {
  var definitionRef = {
    definition_id: 'user/email-processing',
    version: '1.0.0',
    digest: 'sha256:' + 'f'.repeat(64),
  };
  return {
    status: status,
    proposal: status === 'ready_to_author' ? null : {
      proposal_id: 'proposal-email',
      proposal_digest: 'sha256:' + '9'.repeat(64),
      definition_ref: definitionRef,
      definition: {
        title: 'Email Processing',
        purpose: 'Classify, summarize, and prepare an unsent draft.',
        graph: { nodes: [
          { node_id: 'classify', kind: 'action', label: 'Classify email' },
          { node_id: 'draft-approval', kind: 'human_checkpoint', label: 'Approve draft' },
          { node_id: 'draft', kind: 'action', label: 'Prepare unsent draft' },
          { node_id: 'review', kind: 'verification_boundary', label: 'Verify' },
          { node_id: 'accepted', kind: 'terminal_state', label: 'Accepted' },
        ] },
      },
    },
  };
}

function jsonResponse(payload, status) {
  return Promise.resolve({
    ok: !status || status < 400,
    status: status || 200,
    json: function () { return Promise.resolve(payload); },
  });
}

global.fetch = function (url, options) {
  if (url === '/chat') {
    var request = JSON.parse(options.body);
    requests.push(request);
    if (failNext) {
      failNext = false;
      return jsonResponse({ error: 'stale plan identity' }, 409);
    }
    if (request.process_entry_request) {
      remoteInterview = interviewState('interviewing');
      return jsonResponse({ status: 'ok', management_interview: remoteInterview });
    }
    if (request.management_interview_answer) {
      remoteInterview = interviewState('ready_for_plan');
      return jsonResponse({ status: 'ok', management_interview: remoteInterview });
    }
    var action = request.management_plan && request.management_plan.action;
    if (action === 'propose') {
      remotePlan = planState('awaiting_approval');
    } else if (action === 'approve_and_start') {
      remoteDelegation = { status: 'delegated', run_id: 'run-plan' };
      remotePlan = planState('approved', { delegation: remoteDelegation });
    } else if (action === 'approve_without_start') {
      remoteDelegation = null;
      remotePlan = planState('approved');
    } else if (action === 'delegate') {
      remoteDelegation = { status: 'delegated', run_id: 'run-plan' };
      remotePlan = planState('approved', { delegation: remoteDelegation });
    } else if (action === 'request_changes' || action === 'change_scope_or_permissions') {
      remotePlan = planState('revision_requested');
    } else if (action === 'stop_and_retain') {
      remotePlan = planState('retained');
    } else {
      return jsonResponse({ error: 'unexpected management action' }, 400);
    }
    return jsonResponse({ status: 'ok', process_plan: remotePlan });
  }
  if (url === '/api/process-plan-context/dialogue-plan') {
    return jsonResponse({
      ok: true,
      planning_context: {
        dialogue_ref: 'dialogue-plan',
        project_ref: 'ora',
        suggested_target_path: '/tmp/approved-target',
      },
    });
  }
  if (url === '/api/process-plan/dialogue-plan') {
    return remotePlan
      ? jsonResponse({ ok: true, plan: remotePlan })
      : jsonResponse({ error: 'process_plan_not_found' }, 404);
  }
  if (url === '/api/process-interview/dialogue-plan') {
    return remoteInterview
      ? jsonResponse({ ok: true, interview: remoteInterview })
      : jsonResponse({ error: 'management_interview_not_found' }, 404);
  }
  if (url === '/api/process-delegation/dialogue-plan') {
    return remoteDelegation
      ? jsonResponse({ ok: true, delegation: remoteDelegation })
      : jsonResponse({ error: 'delegation_not_found' }, 404);
  }
  if (url === '/api/process-authoring/dialogue-plan') {
    if (options && options.method === 'POST') {
      var authoringRequest = JSON.parse(options.body);
      requests.push({ process_authoring: authoringRequest });
      if (authoringRequest.action === 'propose') {
        remoteAuthoring = authoringState('awaiting_definition_approval');
      } else if (authoringRequest.action === 'approve_and_register') {
        remoteAuthoring = authoringState('available');
      } else if (authoringRequest.action === 'request_revision') {
        remoteAuthoring = authoringState('revision_requested');
      } else {
        return jsonResponse({ error: 'unexpected authoring action' }, 400);
      }
    }
    return jsonResponse({
      ok: true,
      authoring: remoteAuthoring || authoringState('ready_to_author'),
    });
  }
  return Promise.reject(new Error('unexpected fetch: ' + url));
};

require(path.resolve(__dirname, '..', 'js', 'process-plan-review.js'));
w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));

var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? '  - ' + detail : ''));
}
function flush() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}
async function settle() {
  await flush();
  await flush();
}
function button(label) {
  return Array.from(w.document.querySelectorAll('.process-plan-review__button'))
    .find(function (node) { return node.textContent.trim() === label; });
}
function lastAction(name) {
  return requests.slice().reverse().find(function (item) {
    return item.management_plan && item.management_plan.action === name;
  });
}
async function reloadPlan(next) {
  remotePlan = next;
  await w.OraProcessPlanReview.hydrate('dialogue-plan', { open: true });
  await settle();
}
async function submitReason(actionLabel, reason) {
  button(actionLabel).click();
  var input = w.document.querySelector('.process-plan-review__reason-panel textarea');
  input.value = reason;
  button('Submit decision').click();
  await settle();
}

async function run() {
  record('public plan-review API is registered',
    !!w.OraProcessPlanReview
      && typeof w.OraProcessPlanReview.begin === 'function'
      && typeof w.OraProcessPlanReview.hydrate === 'function');

  await w.OraProcessPlanReview.begin(
    'Set up a repeatable weekly report.',
    { source: 'inquiry', objective: 'Set up a repeatable weekly report.', project_ref: 'ora' },
    { intent: 'capability_construction' },
    w.document.getElementById('inquiry')
  );
  record('construction enters a visible management interview',
    !w.document.querySelector('.process-plan-review').hidden
      && /What exact result/.test(w.document.querySelector('.process-plan-review__body').textContent));
  record('per-input selections clear at the governed boundary',
    cleared.framework === 1 && cleared.mode === 1 && cleared.attachments === 1);

  w.document.querySelector('.process-plan-review__answer').value =
    'A reconciled weekly cash-flow report for the finance team.';
  button('Continue interview').click();
  await settle();
  var answer = requests.find(function (item) { return item.management_interview_answer; });
  record('answer binds the exact server question and idempotency identity',
    answer.management_interview_answer.question_id === 'question:intended-result:1'
      && /^interview-ui:[0-9a-f]{8}$/.test(answer.management_interview_answer.idempotency_key));
  record('completed interview opens bounded plan preparation',
    w.document.querySelector('.process-plan-review__target').value === '/tmp/approved-target');

  w.document.querySelector('.process-plan-review__scope').value =
    'report.py\ntests/test_report.py';
  button('Prepare plan').click();
  await settle();
  var proposal = lastAction('propose').management_plan;
  record('proposal submits exact target and item scope to authenticated chat',
    proposal.target_path === '/tmp/approved-target'
      && proposal.artifact_selectors.join('|') === 'report.py|tests/test_report.py');
  record('Principal projection and all five decisions are rendered',
    /A reconciled weekly cash-flow report/.test(w.document.body.textContent)
      && ['Approve and start', 'Approve without starting', 'Request plan changes',
        'Change scope or permissions', 'Stop and retain the plan'].every(function (label) {
          return !!button(label);
        }));

  w.document.querySelector('[data-plan-view="technical"]').click();
  record('Technical projection is a real alternate view',
    /implementation sequence/i.test(w.document.querySelector('.process-plan-review__projection').textContent)
      && /step-report/.test(w.document.querySelector('.process-plan-review__projection').textContent));

  await submitReason('Request plan changes', 'Use a different reconciliation threshold.');
  record('revision action binds exact plan and reason',
    lastAction('request_changes').management_plan.plan_ref.digest === PLAN_REF.digest
      && /threshold/.test(lastAction('request_changes').management_plan.reason));

  await reloadPlan(planState('awaiting_approval'));
  await submitReason('Change scope or permissions', 'Add summary.py to the exact scope.');
  record('scope action remains a revision, not implicit authority',
    lastAction('change_scope_or_permissions').management_plan.action ===
      'change_scope_or_permissions');

  await reloadPlan(planState('awaiting_approval'));
  await submitReason('Stop and retain the plan', 'Retain this plan for next quarter.');
  record('retention is an explicit authenticated decision',
    lastAction('stop_and_retain').management_plan.decision_by === 'principal:user');

  await reloadPlan(planState('awaiting_approval'));
  button('Approve without starting').click();
  await settle();
  record('approve without start uses exact baseline and exposes later start',
    lastAction('approve_without_start').management_plan.baseline_digest ===
      'sha256:' + 'c'.repeat(64)
      && !!button('Start approved plan'));
  button('Start approved plan').click();
  await settle();
  record('later start delegates the exact approval receipt',
    lastAction('delegate').management_plan.approval_receipt_digest ===
      'sha256:' + 'b'.repeat(64)
      && /delegated/.test(w.document.querySelector('.process-plan-review__notice').textContent));

  remoteDelegation = null;
  await reloadPlan(planState('approved'));
  record('reload reconstructs approval and later-start control',
    !!button('Start approved plan')
      && w.OraProcessPlanReview._state().plan.status === 'approved');

  await reloadPlan(planState('stale'));
  record('stale plan fails closed and offers revised preparation',
    /Approval is withheld/.test(w.document.body.textContent)
      && !!button('Prepare plan')
      && !button('Approve and start'));
  failNext = true;
  button('Prepare plan').click();
  await settle();
  record('server failure stays visible without inventing success',
    /stale plan identity/.test(w.document.querySelector('.process-plan-review__error').textContent)
      && w.OraProcessPlanReview._state().plan.status === 'stale');

  remotePlan = null;
  remoteInterview = interviewState('ready_for_plan');
  remoteAuthoring = authoringState('ready_to_author');
  await w.OraProcessPlanReview.hydrate('dialogue-plan', { open: true });
  await settle();
  record('completed management interview offers G1.1-native Process authoring',
    !!button('Author reusable Process')
      && /No Trigger, Persona, scheduling, activation, sending, or external effect/.test(
        w.document.querySelector('.process-plan-review__body').textContent
      ));
  button('Author reusable Process').click();
  await settle();
  var authorRequest = requests.slice().reverse().find(function (item) {
    return item.process_authoring && item.process_authoring.action === 'propose';
  }).process_authoring;
  record('authoring request binds completed interview through deterministic identity',
    /^authoring-ui:[0-9a-f]{8}$/.test(authorRequest.idempotency_key)
      && /Email Processing/.test(w.document.body.textContent)
      && !!button('Approve and register exact definition'));
  button('Approve and register exact definition').click();
  await settle();
  var approvalRequest = requests.slice().reverse().find(function (item) {
    return item.process_authoring
      && item.process_authoring.action === 'approve_and_register';
  }).process_authoring;
  record('browser approval binds exact proposal and does not activate or schedule',
    approvalRequest.proposal_id === 'proposal-email'
      && approvalRequest.proposal_digest === 'sha256:' + '9'.repeat(64)
      && !Object.prototype.hasOwnProperty.call(approvalRequest, 'decision_by')
      && /not scheduled or activated/.test(w.document.body.textContent));

  var failed = results.filter(function (item) { return !item.ok; });
  console.log('\n' + (results.length - failed.length) + '/' + results.length + ' passed');
  if (failed.length) process.exitCode = 1;
}

run().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
});
