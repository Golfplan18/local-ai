#!/usr/bin/env node
/* G1.19 Trigger Manager DOM/server contract boundary. */
'use strict';

var path = require('path');
var JSDOM_PATH = path.join(
  __dirname, '..', 'ora-visual-compiler', 'tests', 'node_modules', 'jsdom'
);
var jsdom;
try { jsdom = require(JSDOM_PATH); }
catch (error) { console.error('error: jsdom unavailable'); process.exit(2); }

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body><button id="sidebarTriggerManagerOpen">Trigger Manager</button></body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true }
);
var w = dom.window;
global.window = w; global.document = w.document;
global.CustomEvent = w.CustomEvent; global.Event = w.Event;
w.HTMLDialogElement.prototype.showModal = function () { this.open = true; };

var ref = { definition_id: 'user/email-processing', version: '1.0.0', digest: 'sha256:' + 'a'.repeat(64) };
var requestDigest = 'sha256:' + 'b'.repeat(64);
var draft = {
  spec: {
    trigger_id: 'manual-email', name: 'Manual email', definition_ref: ref,
    project_ref: 'ora', kind: 'manual', condition: {}, input_bindings: {},
    principal_id: 'principal:user', runtime_principle: null,
  },
  spec_digest: 'sha256:' + 'c'.repeat(64), status: 'draft', firings: [],
  state_digest: 'sha256:' + 'd'.repeat(64),
  activation_request: {
    trigger_id: 'manual-email', spec_digest: 'sha256:' + 'c'.repeat(64),
    principal_id: 'principal:user', request_digest: requestDigest,
  },
};
var triggerRows = [draft];
var posts = [];
var staleNext = false;
var fetches = [];
global.fetch = function (url, options) {
  fetches.push(url);
  if (url === '/api/process-library/entries') {
    return Promise.resolve({ ok: true, json: () => Promise.resolve({
      ok: true, entries: [{
        display_name: 'Email processing', definition_ref: ref,
        lifecycle_status: 'available', automated_execution_available: true,
      }],
    }) });
  }
  if (url === '/api/process-triggers' && (!options || options.method !== 'POST')) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve({
      ok: true, triggers: triggerRows, projection_digest: 'sha256:projection',
    }) });
  }
  if (options && options.method === 'POST') {
    var body = JSON.parse(options.body); posts.push({ url: url, body: body });
    if (staleNext) {
      staleNext = false;
      return Promise.resolve({ ok: false, status: 409, json: () => Promise.resolve({
        ok: false, error: 'Trigger state changed before lifecycle action',
      }) });
    }
    if (body.action === 'activate') {
      triggerRows = [{ ...draft, status: 'active', state_digest: 'sha256:' + 'e'.repeat(64) }];
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true, trigger: triggerRows[0] }) });
    }
    if (body.action === 'fire') {
      triggerRows[0] = { ...triggerRows[0], firings: [{
        firing_id: 'firing-1', status: 'waiting', run_id: 'automated-run-1',
      }] };
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true, trigger: triggerRows[0] }) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true, trigger: triggerRows[0] }) });
  }
  return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: 'not found' }) });
};

require('../js/process-trigger-manager.js');

function tick() { return new Promise(resolve => setTimeout(resolve, 0)); }
var checkCount = 0;
function assert(value, message) {
  checkCount += 1;
  if (!value) throw new Error(message);
}

(async function () {
  document.getElementById('sidebarTriggerManagerOpen').click();
  await tick(); await tick();
  var dialog = document.getElementById('processTriggerManager');
  assert(dialog && dialog.open, 'Trigger Manager must open from Processes toolbar');
  assert(fetches.includes('/api/process-triggers'), 'manager must reload persisted Trigger state');
  assert(fetches.includes('/api/process-library/entries'), 'manager must bind an active exact Process');

  var row = dialog.querySelector('[data-trigger-id="manual-email"]');
  assert(row, 'persisted Trigger must render'); row.click();
  var activate = Array.from(dialog.querySelectorAll('button')).find(button => button.textContent === 'Approve and activate');
  activate.click(); await tick();
  assert(posts.length === 0, 'activation must not occur without explicit exact review');
  assert(dialog.querySelector('[role="status"]').textContent.includes('Explicit review'), 'missing review must be visible');

  dialog.querySelector('.process-trigger-review input').checked = true;
  activate.click(); await tick(); await tick();
  assert(posts.length === 1, 'reviewed activation must submit once');
  assert(posts[0].body.expected_spec_digest === draft.spec_digest, 'activation must bind exact spec digest');
  assert(posts[0].body.approval.request_digest === requestDigest, 'activation must bind exact review request');
  assert(posts[0].body.approval.principal_id === 'principal:user', 'activation must bind Principal');

  var fire = Array.from(dialog.querySelectorAll('button')).find(button => button.textContent === 'Run now');
  assert(fire, 'active manual Trigger must expose Run now'); fire.click();
  await tick(); await tick();
  assert(posts.some(item => item.body.action === 'fire'), 'Run now must use authenticated firing endpoint');
  assert(dialog.textContent.includes('automated-run-1'), 'firing Run must remain visible and inspectable');

  // Reload must reconstruct from the server, not local optimistic state.
  triggerRows[0] = { ...triggerRows[0], status: 'paused', state_digest: 'sha256:' + 'f'.repeat(64) };
  await w.OraProcessTriggerManager.refresh();
  assert(dialog.textContent.includes('paused'), 'reload must show persisted lifecycle state');

  // Stale-state rejection remains visible and forces a readback.
  var resume = Array.from(dialog.querySelectorAll('button')).find(button => button.textContent === 'Resume Trigger');
  staleNext = true; resume.click(); await tick(); await tick();
  assert(dialog.querySelector('[role="status"]').textContent.includes('state changed'), 'stale failure must be visible');

  // New-draft controls disclose both time intermittency and inbound boundary.
  dialog.querySelector('[data-trigger-new]').click();
  var selects = Array.from(dialog.querySelectorAll('.process-trigger-create select'));
  var kind = selects.find(select => Array.from(select.options).some(option => option.value === 'inbound'));
  kind.value = 'time'; kind.dispatchEvent(new w.Event('change'));
  assert(dialog.textContent.includes('no polling loop, cron, launchd, deferred sweep, or 24/7 promise'), 'time boundary must be disclosed');
  assert(dialog.querySelector('textarea[placeholder*="Why no file"]'), 'time Trigger needs written Runtime-Principle reason');
  kind.value = 'inbound'; kind.dispatchEvent(new w.Event('change'));
  assert(dialog.textContent.includes('activation is unavailable until G1.21'), 'inbound channel boundary must be disclosed');

  console.log(checkCount + ' / ' + checkCount + ' process-trigger-manager DOM tests passed');
})().catch(error => { console.error(error.stack || error); process.exit(1); });
