#!/usr/bin/env node
/* G1.1 Phase 2.5/2.6 — Run Inspector and lifecycle DOM boundary tests. */

'use strict';

var fs = require('fs');
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
  '<!doctype html><html><body><button id="origin">Inspect run</button></body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true }
);
var w = dom.window;
global.window = w;
global.document = w.document;
global.Event = w.Event;
global.KeyboardEvent = w.KeyboardEvent;
global.CustomEvent = w.CustomEvent;

var order = [
  'overview', 'plan', 'current_state', 'decisions', 'changes',
  'evidence', 'permissions', 'artifacts', 'technical',
];
var RUN_ID = 'run/grouped-result';
var snapshot = {
  schema_version: 'ora.process-run-inspector/1.0',
  generated_at: '2026-07-18T12:00:00Z',
  run_id: RUN_ID,
  dialogue_ref: 'dialogue-ui-proof',
  definition_ref: {
    definition_id: 'ora/programming', version: '2.0.1', digest: 'sha256:definition',
  },
  view_order: order,
  snapshot_digest: 'sha256:snapshot',
  views: {
    overview: {
      objective: 'Repair the report safely', title: 'Repair the report safely',
      run_state: 'running', visible_status: 'Waiting for You',
      current_phase: { node_id: 'authority', label: 'Authority decision', kind: 'human_checkpoint' },
      credible_next_actions: [{ condition: 'approved', target_node_id: 'execute-step' }],
      required_human_decision: 'Approve the exact target mutation.',
      definition_ref: { definition_id: 'ora/programming', version: '2.0.1', digest: 'sha256:definition' },
      invoked_capabilities: [{ definition_id: 'ora/check', version: '1.0', digest: 'sha256:check' }],
      capabilities_created_or_modified: [{ definition_id: 'cash/report', version: '1.0', digest: 'sha256:cash' }],
      result_artifacts: [{ artifact_id: 'report-result', identity_digest: 'sha256:result' }],
      external_effects: [{ action: 'execute_approved_programming_step', receipt_artifact_id: 'receipt-1' }],
      trigger: { entrypoint: 'prg_run', bindings: { trigger_binding: 'manual' } },
      evidence_current: false,
    },
    plan: { status: 'approved', approved_contract: { plan_id: 'plan-1' } },
    current_state: { state: 'waiting_for_authority', timeline: [{ sequence: 1, kind: 'run_created' }] },
    decisions: {
      required_human_decision: 'Approve the exact target mutation.',
      transitions: [],
      decision_events: [{ record_id: 'decision-plan-approval', event: { event_type: 'node_advanced' } }],
      governed_decisions: [{
        record_id: 'decision-plan-approval', decision_kind: 'human_checkpoint',
        source_node_id: 'plan-approval', target_node_id: 'post-plan-mode',
        outcome: 'approved', decision_by: 'principal:user',
        authority_request_type: 'plan_approval',
        route: { outcome: 'approved', decision_by: 'principal:user', authority_request_type: 'plan_approval' },
      }],
    },
    changes: {
      repository: {
        state: 'external_change_detected', current: false,
        reason: 'Live target changed.', locator: { kind: 'git_ref', ref: '/tmp/repository' },
      },
      external_effects: [{ action: 'execute_approved_programming_step' }],
    },
    evidence: {
      acceptance_supported_now: false,
      unresolved: [{ evidence_id: 'ev-check', outcome: 'STALE' }],
    },
    permissions: { principal_id: 'principal:user', reserved_actions: ['publish'] },
    artifacts: { items: [{ artifact_id: 'report-result', role: 'result' }] },
    technical: {
      files: [{ locator: { kind: 'git_ref', ref: '/tmp/repository' } }],
      diff: { counts: { modified: 1 } },
      tests: ['Run focused tests'], logs: [{ kind: 'attempt_completed' }],
      records: [{ record_id: 'event-1' }],
    },
  },
};

var fetched = [];
var lifecycleState = {
  schema_version: 'ora.process-lifecycle-disposition/1.0',
  run_id: RUN_ID, run_state: 'waiting_for_authority',
  principal_id: 'principal:user',
  status: 'not_terminal', available_actions: [], promote_options: [], closure: null,
};
var lifecycleRequests = [];
w.confirm = function () { return true; };
global.fetch = function (url, options) {
  fetched.push(url);
  if (url === '/api/process-runs/run%2Fgrouped-result/lifecycle') {
    if (options && options.method === 'POST') {
      var request = JSON.parse(options.body);
      lifecycleRequests.push(request);
      lifecycleState = {
        schema_version: 'ora.process-lifecycle-disposition/1.0',
        run_id: RUN_ID, run_state: 'completed', status: 'closed',
        principal_id: 'principal:user',
        available_actions: [], promote_options: [],
        closure: {
          record_id: 'event-lifecycle-ui', recorded_at: '2026-07-18T12:10:00Z',
          disposition: request.disposition, decision_by: request.decision_by,
          promoted_definition_ref: request.promoted_definition_ref || null,
          effective_artifacts: [{ artifact_id: 'report-result', lifecycle_status: 'preserved' }],
        },
      };
    }
    return Promise.resolve({
      ok: true,
      json: function () { return Promise.resolve({ ok: true, lifecycle: lifecycleState }); },
    });
  }
  return Promise.resolve({
    ok: true,
    json: function () { return Promise.resolve({ ok: true, inspector: snapshot }); },
  });
};

var selected = [];
w.document.addEventListener('ora:conversation-selected', function (event) {
  selected.push(event.detail);
});

require(path.resolve(__dirname, '..', 'js', 'process-run-inspector.js'));

var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? '  - ' + detail : ''));
}
function flush() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

async function run() {
  var origin = w.document.getElementById('origin');
  origin.focus();
  record('inspector is not persistent before a Run is selected',
    !w.document.querySelector('[data-process-run-inspector]'));
  record('generic inspector API is exposed to Process surfaces',
    !!w.OraProcessRunInspector && order.join('|') === w.OraProcessRunInspector.viewOrder.join('|'));

  w.document.dispatchEvent(new w.CustomEvent('ora:process-run-inspector:open', {
    detail: { run_id: RUN_ID, trigger: origin },
  }));
  await flush();
  await flush();

  var modal = w.document.querySelector('[data-process-run-inspector]');
  var tabs = Array.from(modal.querySelectorAll('[role="tab"]'));
  record('Run selection loads the exact authenticated endpoint',
    fetched[0] === '/api/process-runs/run%2Fgrouped-result/inspector');
  record('inspector opens as a modal structured Process Run view',
    !modal.hidden && modal.querySelector('[role="dialog"]').getAttribute('aria-modal') === 'true');
  record('all nine Phase 2.5 views are present in exact order',
    tabs.map(function (tab) { return tab.dataset.view; }).join('|') === order.join('|'));
  record('Overview alone is selected by default',
    tabs.filter(function (tab) { return tab.getAttribute('aria-selected') === 'true'; }).length === 1
      && tabs[0].getAttribute('aria-selected') === 'true'
      && modal.querySelector('[data-inspector-content]').dataset.view === 'overview');
  record('default view answers outcome, state, next action, and user action',
    modal.textContent.indexOf('Repair the report safely') >= 0
      && modal.textContent.indexOf('Waiting for You · Authority decision') >= 0
      && modal.textContent.indexOf('approved → execute-step') >= 0
      && modal.textContent.indexOf('Approve the exact target mutation.') >= 0);
  record('definition version, trigger, results, capabilities, and effects are visible',
    modal.textContent.indexOf('2.0.1') >= 0
      && modal.textContent.indexOf('prg_run') >= 0
      && modal.textContent.indexOf('report-result') >= 0
      && modal.textContent.indexOf('cash/report') >= 0
      && modal.textContent.indexOf('receipt-1') >= 0);
  record('technical packets are withheld from the default view',
    modal.textContent.indexOf('event-1') < 0 && modal.querySelectorAll('details').length === 0);
  record('stale evidence is stated in text rather than color alone',
    modal.textContent.indexOf('does not yet support acceptance') >= 0
      && modal.dataset.evidenceCurrent === 'false');

  modal.querySelector('[data-view="decisions"]').click();
  record('Decisions exposes authenticated checkpoint outcome, maker, authority, and route',
    modal.querySelector('[data-inspector-content]').dataset.view === 'decisions'
      && modal.textContent.indexOf('human_checkpoint') >= 0
      && modal.textContent.indexOf('principal:user') >= 0
      && modal.textContent.indexOf('plan_approval') >= 0
      && modal.textContent.indexOf('post-plan-mode') >= 0);

  modal.querySelector('[data-view="changes"]').click();
  record('Changes exposes external-editor invalidation and target identity',
    modal.querySelector('[data-inspector-content]').dataset.view === 'changes'
      && modal.textContent.indexOf('external_change_detected') >= 0
      && modal.textContent.indexOf('Live target changed.') >= 0);

  modal.querySelector('[data-view="evidence"]').click();
  record('Evidence refuses to present stale proof as acceptance',
    modal.textContent.indexOf('cannot authorize current acceptance') >= 0
      && modal.textContent.indexOf('STALE') >= 0);

  modal.querySelector('[data-view="technical"]').click();
  var technicalDetails = modal.querySelectorAll('details');
  record('Technical progressively discloses files, diffs, tests, logs, and records',
    technicalDetails.length >= 5
      && Array.from(technicalDetails).every(function (detail) { return !detail.open; })
      && modal.textContent.indexOf('Files') >= 0
      && modal.textContent.indexOf('Diff') >= 0
      && modal.textContent.indexOf('Tests') >= 0
      && modal.textContent.indexOf('Logs') >= 0
      && modal.textContent.indexOf('Records') >= 0);

  var currentTab = modal.querySelector('[data-view="technical"]');
  currentTab.focus();
  currentTab.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  record('tab navigation is keyboard accessible and wraps',
    modal.querySelector('[data-inspector-content]').dataset.view === 'overview'
      && w.document.activeElement.dataset.view === 'overview');

  modal.querySelector('[data-inspector-dialogue]').click();
  record('discussion returns through the exact governing Dialogue',
    selected.length === 1 && selected[0].conversation_id === 'dialogue-ui-proof');
  record('closing returns focus to the invoking control', modal.hidden && w.document.activeElement === origin);

  snapshot.views.overview.run_state = 'completed';
  snapshot.views.overview.visible_status = 'Completed';
  snapshot.views.overview.current_phase = {
    node_id: 'accepted', label: 'Accepted', kind: 'terminal_state',
  };
  snapshot.views.overview.required_human_decision = null;
  snapshot.views.current_state.state = 'completed';
  lifecycleState = {
    schema_version: 'ora.process-lifecycle-disposition/1.0',
    run_id: RUN_ID, run_state: 'completed',
    principal_id: 'principal:user',
    status: 'awaiting_disposition',
    available_actions: ['promote', 'preserve', 'archive', 'discard'],
    promote_options: [{
      display_name: 'Cash Review', capability_artifact_id: 'cash-definition',
      definition_ref: {
        definition_id: 'business/cash-review', version: '1.0.0', digest: 'sha256:cash',
      },
    }],
    closure: null,
  };
  w.document.dispatchEvent(new w.CustomEvent('ora:process-run-inspector:open', {
    detail: { run_id: RUN_ID, trigger: origin },
  }));
  await flush();
  await flush();
  record('terminal Run exposes all four explicit lifecycle choices',
    modal.textContent.indexOf('Run lifecycle') >= 0
      && !!modal.querySelector('.process-run-inspector__lifecycle-promote')
      && !!modal.querySelector('.process-run-inspector__lifecycle-preserve')
      && !!modal.querySelector('.process-run-inspector__lifecycle-archive')
      && !!modal.querySelector('.process-run-inspector__lifecycle-discard')
      && modal.textContent.indexOf('No choice activates standing automation') >= 0);
  modal.querySelector('.process-run-inspector__lifecycle-promote').click();
  await flush();
  await flush();
  record('slash-containing Run IDs never enter a caller-controlled idempotency key',
    fetched.indexOf('/api/process-runs/run%2Fgrouped-result/lifecycle') >= 0
      && lifecycleRequests.length === 1
      && !Object.prototype.hasOwnProperty.call(
        lifecycleRequests[0], 'idempotency_key'
      ));
  record('Promote posts the exact capability identity and renders its receipt',
    lifecycleRequests.length === 1
      && lifecycleRequests[0].disposition === 'promote'
      && lifecycleRequests[0].capability_artifact_id === 'cash-definition'
      && lifecycleRequests[0].promoted_definition_ref.definition_id === 'business/cash-review'
      && modal.textContent.indexOf('Closed with promote') >= 0
      && modal.textContent.indexOf('event-lifecycle-ui') >= 0);
  w.OraProcessRunInspector.close();

  var indexSource = fs.readFileSync(path.resolve(__dirname, '..', '..', 'index-v3.html'), 'utf8');
  var cssSource = fs.readFileSync(path.resolve(__dirname, '..', 'styles', 'ora-default.css'), 'utf8');
  var sidebarSource = fs.readFileSync(path.resolve(__dirname, '..', 'js', 'sidebar-oversight.js'), 'utf8');
  record('live Ora loads the inspector and exposes it from governed Run cards',
    indexSource.indexOf('/static/js/process-run-inspector.js') >= 0
      && cssSource.indexOf('process-run-inspector.css') >= 0
      && sidebarSource.indexOf('ora:process-run-inspector:open') >= 0);

  var passed = results.filter(function (result) { return result.ok; }).length;
  console.log('');
  console.log(passed + ' / ' + results.length + ' tests passed');
  process.exit(passed === results.length ? 0 : 1);
}

run().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
