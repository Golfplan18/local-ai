#!/usr/bin/env node
/* G1.1 Phase 2.1 — governed Process entry UI tests. */

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

var PROGRAMMING_REF = {
  definition_id: 'ora/programming',
  version: '2.0.1',
  digest: 'sha256:b79d06b401ca54ec62588ab9cd64393fc049d4cf599298a5b057d93aa4e2a927',
};
var PROGRAMMING = {
  id: 'programming',
  kind: 'process_definition',
  display_name: 'Programming',
  display_description: 'Governed programming work.',
  definition_ref: PROGRAMMING_REF,
  activated: false,
};

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body>' +
  '<button id="sidebarProcessLibraryOpen" type="button">Process Library</button>' +
  '<button id="inputToolbarProgramming" type="button">Programming</button>' +
  '</body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true }
);
var w = dom.window;
global.window = w;
global.document = w.document;
global.HTMLElement = w.HTMLElement;
global.Event = w.Event;
global.CustomEvent = w.CustomEvent;

w.OraSidebar = { getActiveProject: function () { return 'ora'; } };

var routeRequests = [];
global.fetch = function (url, options) {
  if (url === '/api/projects/meta?status=active') {
    return Promise.resolve({
      ok: true,
      json: function () {
        return Promise.resolve({
          ok: true,
          projects: [
            { nexus: 'commons', canonical_nexus: 'commons', name: 'Commons' },
            { nexus: 'ora', canonical_nexus: 'ora', name: 'Ora' },
          ],
        });
      },
    });
  }
  if (url === '/api/process-library/entries') {
    return Promise.resolve({
      ok: true,
      json: function () { return Promise.resolve({ ok: true, definitions: [PROGRAMMING] }); },
    });
  }
  if (url === '/api/process-entry/route') {
    var request = JSON.parse(options.body);
    routeRequests.push(request);
    var construction = request.source === 'construction_action'
      || /\b(build|modify|reusable|automate)\b/i.test(request.objective);
    var activation = /\bactivate\b/i.test(request.objective);
    var unknownInvocation = /deployment workflow/i.test(request.objective)
      && !request.selected_definition_ref;
    var status = construction && !request.project_confirmed
      ? 'awaiting_project_confirmation'
      : (unknownInvocation ? 'awaiting_definition_selection'
        : (request.selected_definition_ref && !activation && !construction
          ? 'awaiting_activation' : 'ready'));
    var intent = 'ordinary_generation';
    if (request.selected_definition_ref || request.selected_framework_id) {
      intent = 'capability_invocation';
    }
    if (activation) intent = 'capability_activation';
    if (construction) intent = 'capability_construction';
    return Promise.resolve({
      ok: true,
      json: function () {
        return Promise.resolve({
          ok: true,
          entry: {
            source: request.source,
            objective: request.objective,
            project_ref: request.project_ref,
            project_confirmed: request.project_confirmed,
            definition_ref: request.selected_definition_ref || null,
            status: status,
            intent: intent,
            authority_effects: [],
            creates_process_run: false,
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
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? '  - ' + detail : ''));
}
function flush() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}
function submitVisibleForm(objective) {
  var textarea = w.document.querySelector('.process-entry__objective');
  textarea.value = objective;
  w.document.querySelector('.process-entry__form').dispatchEvent(
    new w.Event('submit', { bubbles: true, cancelable: true })
  );
}

async function run() {
  record('public Process entry API is registered',
    !!w.OraProcessEntry
      && typeof w.OraProcessEntry.prepareInquiry === 'function'
      && typeof w.OraProcessEntry.openConstruction === 'function'
      && typeof w.OraProcessEntry.openLibrary === 'function');

  var readyEvents = [];
  w.document.addEventListener('ora:process-entry:ready', function (event) {
    readyEvents.push(event.detail);
  });

  w.document.dispatchEvent(new w.CustomEvent('ora:input-toolbar:programming'));
  await flush();
  await flush();
  record('Programming action opens governed entry modal',
    w.document.querySelector('.process-entry').hidden === false);
  record('construction starts with the ordinary-language question',
    w.document.querySelector('.process-entry__label').textContent.trim() === 'What should happen?');
  record('construction presents a project chooser',
    w.document.querySelector('.process-entry__project').value === 'ora');
  record('entry UI never asks for a technical implementation form',
    w.document.querySelectorAll('.process-entry__form input[type="radio"]').length === 0
      && !/choose (?:an )?(?:app|script|automation|agent|spreadsheet)/i.test(
        w.document.querySelector('.process-entry__form').textContent
      ));
  submitVisibleForm('Build a reusable automation for reports.');
  await flush();
  await flush();
  record('explicit construction dispatches only after confirmation',
    readyEvents.length === 1
      && readyEvents[0].request.project_confirmed === true
      && readyEvents[0].request.project_ref === 'ora');
  record('confirmed construction carries no authority or Run effect',
    readyEvents[0].contract.creates_process_run === false
      && readyEvents[0].contract.authority_effects.length === 0);

  var ordinary = await w.OraProcessEntry.prepareInquiry('Create a short summary.', null);
  record('ordinary Inquiry routes without a technical chooser',
    ordinary.contract.intent === 'ordinary_generation'
      && ordinary.contract.status === 'ready');
  record('ordinary Inquiry preserves Inquiry source', ordinary.request.source === 'inquiry');

  var constructionPromise = w.OraProcessEntry.prepareInquiry(
    'Automate my weekly cash-flow report.', null
  );
  await flush();
  await flush();
  record('inferred construction also opens project chooser',
    w.document.querySelector('.process-entry').hidden === false
      && w.document.querySelector('.process-entry__project').value === 'ora');
  submitVisibleForm('Automate my weekly cash-flow report.');
  var inferredConstruction = await constructionPromise;
  record('inferred construction returns confirmed request',
    inferredConstruction.request.project_confirmed === true
      && inferredConstruction.contract.status === 'ready');

  var unknownPromise = w.OraProcessEntry.prepareInquiry(
    'Run the deployment workflow now.', null
  );
  await flush();
  await flush();
  record('unknown invocation opens entry-only Process Library',
    w.document.querySelector('.process-entry__title').textContent === 'Process Library'
      && w.document.querySelectorAll('.process-entry__library-row').length === 1);
  record('Library exposes exact issued version',
    w.document.querySelector('.process-entry__library-identity').textContent
      === 'ora/programming@2.0.1');
  w.document.querySelector('.process-entry__library-row').click();
  await flush();
  record('inactive definition invocation stops at activation boundary',
    /not active/i.test(w.document.querySelector('.process-entry__notice').textContent)
      && /No invocation or Process Run has started/.test(
        w.document.querySelector('.process-entry__notice').textContent
      ));
  w.document.querySelector('[data-process-entry-notice-close]').click();
  var selectedInvocation = await unknownPromise;
  record('inactive definition does not produce a ready submission',
    selectedInvocation === null);

  w.document.getElementById('sidebarProcessLibraryOpen').click();
  await flush();
  await flush();
  w.document.querySelector('.process-entry__library-row').click();
  await flush();
  await flush();
  record('Process Library entry asks what should happen before submission',
    w.document.querySelector('.process-entry__label').textContent.trim() === 'What should happen?');
  submitVisibleForm('Activate Programming for this project.');
  await flush();
  await flush();
  record('Process Library action converges on ready event',
    readyEvents.length === 2
      && readyEvents[1].request.source === 'process_library'
      && JSON.stringify(readyEvents[1].request.selected_definition_ref)
        === JSON.stringify(PROGRAMMING_REF));

  var shared = await w.OraProcessEntry.prepareInquiry(
    'Activate Programming for this project.', PROGRAMMING
  );
  record('shared picker routes explicit activation by exact identity',
    shared.request.source === 'shared_picker'
      && JSON.stringify(shared.request.selected_definition_ref) === JSON.stringify(PROGRAMMING_REF)
      && shared.contract.intent === 'capability_activation');
  var framework = await w.OraProcessEntry.prepareInquiry(
    'Map the terrain for this decision.',
    { id: 'terrain-mapping', kind: 'framework', display_name: 'Terrain Mapping' }
  );
  record('shared framework picker routes curated framework invocation',
    framework.request.source === 'shared_picker'
      && framework.request.selected_framework_id === 'terrain-mapping'
      && framework.contract.intent === 'capability_invocation');
  record('every routing decision was server-previewed', routeRequests.length >= 7,
    'requests=' + routeRequests.length);

  var passed = results.filter(function (result) { return result.ok; }).length;
  console.log('');
  console.log(passed + ' / ' + results.length + ' tests passed');
  if (passed !== results.length) process.exit(1);
}

run().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
