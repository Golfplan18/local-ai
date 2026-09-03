#!/usr/bin/env node
/* Focused jsdom coverage for the read-only Overview Desktop shell. */
'use strict';

var assert = require('assert');
var fs = require('fs');
var path = require('path');
var vm = require('vm');

var nodeModules = process.env.COMPILER_TEST_NODE_MODULES || path.resolve(
  __dirname, '..', 'ora-visual-compiler', 'tests', 'node_modules'
);
var jsdom;
try {
  jsdom = require(path.join(nodeModules, 'jsdom'));
} catch (error) {
  console.error('error: jsdom not available at ' + nodeModules + ': ' + error.message);
  process.exit(2);
}

var indexSource = fs.readFileSync(path.resolve(__dirname, '..', '..', 'index-v3.html'), 'utf8');
var launcherMatch = indexSource.match(
  /<button class="sidebar-dash-icon overview-desktop-launcher"[\s\S]*?<\/button>/
);
var mountMatch = indexSource.match(
  /<section class="overview-desktop" id="overviewDesktop"[\s\S]*?<\/section>/
);
assert(launcherMatch, 'index-v3.html carries the permanent Overview launcher');
assert(mountMatch, 'index-v3.html carries the stable Overview mount');
assert(indexSource.includes('/static/js/overview-desktop.js'), 'Overview controller is loaded');

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body>'
  + '<div class="ora-shell" data-workspace="unchanged">'
  + launcherMatch[0]
  + '<input id="workspaceInput" value="kept">'
  + '<section id="priorSurface" hidden></section>'
  + '</div>'
  + mountMatch[0]
  + '</body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
);
var w = dom.window;
var projectOpens = [];
var requests = [];
var responses = [];
w.OraProjectModal = {
  open: function (nexus, title) { projectOpens.push([nexus, title]); },
};
w.fetch = function (url, options) {
  requests.push([url, options]);
  var next = responses.shift();
  return next instanceof Error ? Promise.reject(next) : Promise.resolve(next);
};

function ok(payload) {
  return { ok: true, status: 200, json: function () { return Promise.resolve(payload); } };
}
function flush() {
  return new Promise(function (resolve) { w.setTimeout(resolve, 0); });
}
function source(id, title, state, items, error) {
  return {
    source_id: id,
    title: title,
    state: state,
    count: items.length,
    available: state !== 'unavailable',
    freshness: {
      observed_at: '2026-09-01T12:30:00+00:00',
      last_success_at: state === 'unavailable' ? null : '2026-09-01T12:29:00+00:00',
    },
    error: error || null,
    items: items,
  };
}

responses.push(ok({ sources: [
  source('daily-note', 'Prior-day Daily Note', 'missing', [{
    title: '2026-08-31', text: 'No completed Daily Note was found.', state: 'missing',
    time: null, count: null, scope: { path: '/notes/2026-08-31.md' }, actions: ['open_note'],
  }]),
  source('triggers', 'Scheduled Triggers', 'empty', []),
  source('project-priority', 'Project priority', 'ready', [{
    title: 'Ora', text: 'Active', state: 'ready', time: null, count: null,
    scope: { project_nexus: 'ora' }, actions: ['open_project'],
  }]),
  source('oversight', 'Oversight', 'partial', [{
    title: 'Review evidence', text: 'Needs a decision', state: 'paused', time: null,
    count: null, scope: { project_nexus: 'ora' }, actions: ['open_conversation', 'discuss'],
  }], { code: 'operating_unavailable', message: 'Operating work could not be read.' }),
] }));

var controllerSource = fs.readFileSync(
  path.resolve(__dirname, '..', 'js', 'overview-desktop.js'), 'utf8'
);
vm.runInContext(controllerSource, dom.getInternalVMContext());

(async function run() {
  var launcher = w.document.getElementById('overviewDesktopOpen');
  var mount = w.document.getElementById('overviewDesktop');
  var workspace = w.document.querySelector('.ora-shell');
  var workspaceInput = w.document.getElementById('workspaceInput');
  var priorSurface = w.document.getElementById('priorSurface');
  workspaceInput.focus();
  launcher.click();
  await flush();
  await flush();

  assert.strictEqual(mount.hidden, false, 'launcher opens the full Overview surface');
  assert.strictEqual(workspace.hasAttribute('inert'), true, 'underlying workspace is inert while open');
  assert.strictEqual(requests.length, 1);
  assert.strictEqual(requests[0][0], '/api/overview');
  assert.strictEqual(requests[0][1].method, 'GET');
  assert.deepStrictEqual(
    Array.from(mount.querySelectorAll('.overview-source')).map(function (card) {
      return [card.dataset.sourceId, card.dataset.state];
    }),
    [
      ['project-priority', 'ready'],
      ['oversight', 'partial'],
      ['triggers', 'empty'],
      ['daily-note', 'missing'],
    ],
    'the four sources render in canonical order with their distinct states'
  );
  assert(mount.textContent.includes('Checked 2026-09-01T12:30:00+00:00'));
  assert(mount.textContent.includes('Last success 2026-09-01T12:29:00+00:00'));
  assert(mount.textContent.includes('Operating work could not be read.'));

  var actions = Array.from(mount.querySelectorAll('[data-overview-action]'));
  assert.strictEqual(actions.length, 1, 'actions without a sufficient read-only destination are omitted');
  assert.strictEqual(actions[0].dataset.overviewAction, 'open_project');
  actions[0].click();
  assert.deepStrictEqual(projectOpens, [['ora', 'Ora']]);
  assert.strictEqual(mount.hidden, true, 'project handoff closes Overview');
  assert.strictEqual(workspace.hasAttribute('inert'), false, 'workspace inert state is restored');
  assert.strictEqual(workspaceInput.value, 'kept', 'underlying workspace content is preserved');
  assert.strictEqual(priorSurface.hidden, true, 'underlying workspace visibility is preserved');
  assert.strictEqual(w.document.activeElement, workspaceInput, 'prior focus is restored');

  responses.push(new Error('source connection failed'));
  launcher.focus();
  launcher.click();
  await flush();
  await flush();
  assert.strictEqual(mount.querySelectorAll('.overview-source').length, 0);
  assert(mount.querySelector('#overviewDesktopStatus').textContent.includes('source connection failed'));
  w.document.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  assert.strictEqual(mount.hidden, true, 'Escape closes Overview');
  assert.strictEqual(w.document.activeElement, launcher, 'launcher focus is restored after close');

  console.log('overview desktop tests passed');
})().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
}).finally(function () {
  dom.window.close();
});
