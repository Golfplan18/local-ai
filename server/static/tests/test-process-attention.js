#!/usr/bin/env node
/* G1.1 Phase 2.4 — governed Process management surface tests. */

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

var htmlSource = fs.readFileSync(
  path.resolve(__dirname, '..', '..', 'index-v3.html'), 'utf8'
);
var sidebarMatch = htmlSource.match(/<aside class="left-sidebar"[\s\S]*?<\/aside>/);
if (!sidebarMatch) throw new Error('sidebar markup unavailable');
var dom = new jsdom.JSDOM(
  '<!doctype html><html><body>' + sidebarMatch[0]
    + '<svg><g id="logo-a"></g></svg></body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true }
);
var w = dom.window;
global.window = w;
global.document = w.document;
global.HTMLElement = w.HTMLElement;
global.Event = w.Event;
global.CustomEvent = w.CustomEvent;
global.localStorage = w.localStorage;

var attentionPayload = {
  ok: true,
  pending: [
    {
      run_id: 'run-quiet', dialogue_ref: 'dialogue-quiet', title: 'Quiet work',
      project_ref: 'ora', run_state: 'running', current_step: 'Execute preflight',
      visible_status: 'Operating', quiet: true, needs_attention: false,
      attention: null,
    },
    {
      run_id: 'run-decision', dialogue_ref: 'dialogue-decision',
      title: 'Cash-flow review', project_ref: 'ora', run_state: 'running',
      current_step: 'Approval', visible_status: 'Waiting for You', quiet: false,
      needs_attention: true,
      attention: {
        kind: 'decision', condition: 'approved_baseline_stale',
        required_decision: 'Approve a revised plan.', evidence_refs: ['sha256:old', 'sha256:new'],
      },
    },
  ],
  unread: [
    {
      run_id: 'run-decision', dialogue_ref: 'dialogue-decision',
      title: 'Cash-flow review', project_ref: 'ora', run_state: 'running',
      current_step: 'Approval', visible_status: 'Waiting for You', quiet: false,
      needs_attention: true,
      attention: {
        kind: 'decision', condition: 'approved_baseline_stale',
        required_decision: 'Approve a revised plan.', evidence_refs: ['sha256:old', 'sha256:new'],
      },
    },
    {
      run_id: 'run-completed', dialogue_ref: 'dialogue-completed',
      title: 'Completed report', project_ref: 'ora', run_state: 'completed',
      current_step: 'Accepted', visible_status: 'Completed', quiet: false,
      needs_attention: true,
      attention: {
        kind: 'result', condition: 'Independent review passed.',
        required_decision: 'Review the returned result.',
        evidence_refs: [{ evidence_id: 'final', outcome: 'PASS' }],
        result_artifacts: [{ artifact_id: 'report', identity_digest: 'sha256:result' }],
      },
    },
  ],
  automated_processes: [
    {
      definition_ref: { definition_id: 'cash/weekly', version: '1.0.0', digest: 'sha256:x' },
      title: 'Weekly cash review', status: 'Deployed', trigger_binding: 'weekly',
      authority_binding: 'finance', quiet: true,
    },
  ],
  phase_2_5_authorized: false,
};
var markedRead = [];
global.fetch = function (url) {
  if (url === '/api/process-attention') {
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve(attentionPayload); } });
  }
  if (url === '/api/oversight/paused' || url === '/api/oversight/operating') {
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve({ entries: [] }); } });
  }
  if (url === '/api/conversations') {
    return Promise.resolve({
      ok: true,
      json: function () {
        return Promise.resolve({ pinned: [], errored: [], pending: [], unread: [], active: [] });
      },
    });
  }
  if (/\/api\/conversation\/[^/]+\/mark-read$/.test(url)) {
    markedRead.push(url);
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve({ ok: true }); } });
  }
  if (url === '/api/projects/meta?status=active') {
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve({ projects: [] }); } });
  }
  return Promise.resolve({ ok: false, json: function () { return Promise.resolve({}); } });
};

var selected = [];
w.document.addEventListener('ora:conversation-selected', function (event) {
  selected.push(event.detail);
});

require(path.resolve(__dirname, '..', 'js', 'sidebar.js'));
require(path.resolve(__dirname, '..', 'js', 'sidebar-oversight.js'));

var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? '  - ' + detail : ''));
}
function flush() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

async function run() {
  await flush();
  await flush();
  var pending = w.document.querySelectorAll('#processAttentionPendingList .process-attention-card');
  var unread = w.document.querySelectorAll('#processAttentionUnreadList .process-attention-card');
  var automated = w.document.querySelectorAll('#processAttentionAutomatedList .process-attention-card');
  record('Processes contains the three required management groups',
    !!w.document.querySelector('[data-group="process-unread"]')
      && !!w.document.querySelector('[data-group="process-pending"]')
      && !!w.document.querySelector('[data-group="process-automated"]'));
  record('Pending projects every live Process Run', pending.length === 2);
  record('Unread contains returned decisions and results', unread.length === 2);
  record('Automated Processes contains deployed standing definitions', automated.length === 1);
  record('healthy running work remains visually quiet',
    pending[0].dataset.needsAttention === 'false'
      && !pending[0].querySelector('.process-attention-detail'));
  record('authority requests are conspicuous without relying on color alone',
    pending[1].dataset.needsAttention === 'true'
      && pending[1].textContent.indexOf('Waiting for You') >= 0
      && pending[1].textContent.indexOf('Approve a revised plan.') >= 0
      && pending[1].textContent.indexOf('Evidence: sha256:old; sha256:new') >= 0);
  record('exact projection counts are rendered',
    w.document.getElementById('processAttentionUnreadCount').textContent === '2'
      && w.document.getElementById('processAttentionPendingCount').textContent === '2'
      && w.document.getElementById('processAttentionAutomatedCount').textContent === '1');
  record('deployed row exposes trigger and authority bindings',
    automated[0].textContent.indexOf('trigger: weekly') >= 0
      && automated[0].textContent.indexOf('authority: finance') >= 0);
  record('completed work exposes exact result and acceptance evidence',
    unread[1].textContent.indexOf('report (sha256:result)') >= 0
      && unread[1].textContent.indexOf('"outcome":"PASS"') >= 0);
  record('collapsed wordmark attracts for Process attention',
    w.document.getElementById('logo-a').classList.contains('wordmark-attract'));

  unread[0].click();
  await flush();
  record('opening unread marks the governing Dialogue read',
    markedRead.length === 1 && markedRead[0].indexOf('dialogue-decision') >= 0);
  record('opening a Process row returns through its governing Dialogue',
    selected.length === 1 && selected[0].conversation_id === 'dialogue-decision');

  w.document.dispatchEvent(new w.CustomEvent('ora:process-attention-changed', {
    detail: { needs_attention: false },
  }));
  record('healthy Process state removes process-only wordmark attraction',
    !w.document.getElementById('logo-a').classList.contains('wordmark-attract'));
  record('Run Inspector stays progressively disclosed until selected',
    !w.document.querySelector('[data-process-run-inspector]'));

  var passed = results.filter(function (result) { return result.ok; }).length;
  console.log('');
  console.log(passed + ' / ' + results.length + ' tests passed');
  process.exit(passed === results.length ? 0 : 1);
}

run().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
