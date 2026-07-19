#!/usr/bin/env node
/* G1.1 Phase 2.7 — contextual Programming/Build decision DOM proof. */

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
  '<!doctype html><html><body>' +
  '<button id="inputToolbarProgramming" type="button" aria-label="Programming" title="Programming"></button>' +
  '</body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true }
);
var w = dom.window;
global.window = w;
global.document = w.document;
global.Event = w.Event;
global.CustomEvent = w.CustomEvent;
w.OraSidebar = { getActiveProject: function () { return 'ora'; } };

var witness = {
  definition_ref: {
    definition_id: 'business/cash-review', version: '1.0.0', digest: 'sha256:target',
  },
  construction: { run_id: 'run-construct' },
  invocation: { parent_run_id: 'run-invoke', record_id: 'event-invoke', sequence: 4 },
  witness_digest: 'sha256:witness',
};
var gate = {
  current_label: 'Programming', automatic_rename: false,
  decision_available: true, status: 'awaiting_user_decision',
  decision: null, qualifying_witnesses: [witness],
};
var labelPosts = [];
var routeRequests = [];

global.fetch = function (url, options) {
  if (url === '/api/process-entry/construction-label') {
    if (options && options.method === 'POST') {
      var decision = JSON.parse(options.body);
      labelPosts.push(decision);
      gate = {
        current_label: decision.decision === 'use_build' ? 'Build' : 'Programming',
        automatic_rename: false, decision_available: false, status: 'decided',
        decision: decision, qualifying_witnesses: [witness],
      };
    }
    return Promise.resolve({
      ok: true,
      json: function () { return Promise.resolve({ ok: true, gate: gate }); },
    });
  }
  if (url === '/api/projects/meta?status=active') {
    return Promise.resolve({
      ok: true,
      json: function () {
        return Promise.resolve({
          ok: true,
          projects: [{ nexus: 'ora', canonical_nexus: 'ora', name: 'Ora' }],
        });
      },
    });
  }
  if (url === '/api/process-entry/route') {
    var request = JSON.parse(options.body);
    routeRequests.push(request);
    return Promise.resolve({
      ok: true,
      json: function () {
        return Promise.resolve({
          ok: true,
          entry: {
            intent: 'capability_construction', status: 'ready',
            source: request.source, project_ref: request.project_ref,
            project_confirmed: request.project_confirmed,
            authority_effects: [], creates_process_run: false,
          },
        });
      },
    });
  }
  return Promise.reject(new Error('unexpected fetch: ' + url));
};

require(path.resolve(__dirname, '..', 'js', 'process-entry.js'));
w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));

var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? '  - ' + detail : ''));
}
function flush() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

async function run() {
  await flush();
  await flush();
  var button = w.document.getElementById('inputToolbarProgramming');
  record('bridge evidence does not automatically rename Programming',
    button.getAttribute('aria-label') === 'Programming'
      && w.OraProcessEntry.getConstructionLabel() === 'Programming');
  record('eligibility adds no persistent Build control',
    !w.document.getElementById('inputToolbarBuild')
      && !w.document.querySelector('[data-construction-label]'));

  w.document.dispatchEvent(new w.CustomEvent('ora:input-toolbar:programming'));
  w.document.dispatchEvent(new w.CustomEvent('ora:input-toolbar:programming'));
  await flush();
  await flush();
  record('Programming action presents the contextual user decision',
    w.document.querySelector('.process-entry__title').textContent === 'Programming or Build?'
      && w.document.querySelectorAll('[data-construction-label]').length === 2);
  record('repeated activation cannot duplicate or bypass the pending decision',
    w.document.querySelectorAll('.process-entry').length === 1
      && w.document.querySelectorAll('[data-construction-label]').length === 2);
  record('decision explains that identity and authority do not change',
    /not the Process Definition, routing, or authority/i.test(
      w.document.querySelector('.process-entry__notice').textContent
    ));

  w.document.querySelector('[data-construction-label="use_build"]').click();
  await flush();
  await flush();
  await flush();
  record('Build appears only after an explicit principal decision',
    labelPosts.length === 1
      && labelPosts[0].decision === 'use_build'
      && labelPosts[0].decision_by === 'principal:user'
      && button.getAttribute('aria-label') === 'Build'
      && button.getAttribute('title') === 'Build');
  record('the selected label carries into the same construction form',
    w.document.querySelector('.process-entry__title').textContent === 'Build'
      && !!w.document.querySelector('.process-entry__form'));

  var objective = w.document.querySelector('.process-entry__objective');
  objective.value = 'Construct a governed reusable report review.';
  w.document.querySelector('.process-entry__form').dispatchEvent(
    new w.Event('submit', { bubbles: true, cancelable: true })
  );
  await flush();
  await flush();
  record('Build remains the Programming construction route, not a new capability identity',
    routeRequests.length === 1
      && routeRequests[0].source === 'construction_action'
      && !routeRequests[0].selected_definition_ref
      && routeRequests[0].project_confirmed === true);

  var passed = results.filter(function (result) { return result.ok; }).length;
  console.log('');
  console.log(passed + ' / ' + results.length + ' tests passed');
  if (passed !== results.length) process.exit(1);
}

run().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
