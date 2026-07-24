#!/usr/bin/env node
/* G1.1 Phase 2.1/2.6/2.7 — governed entry, Library, and label UI tests. */

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
  scope: { kind: 'project', selector: 'project:ora' },
  lifecycle_status: 'registered',
  package: {
    package_id: 'ora/programming',
    package_version: '2.0.1',
    entry_member_id: 'programming',
    members: [{ member_id: 'programming' }, { member_id: 'verification' }],
  },
  activated: false,
};
var AUTOMATION_REF = {
  definition_id: 'user/email-processing',
  version: '1.0.0',
  digest: 'sha256:' + 'a'.repeat(64),
};
var AUTOMATION = {
  id: 'email-processing',
  kind: 'process_definition',
  display_name: 'Email Processing',
  display_description: 'Prepare an unsent email draft.',
  definition_ref: AUTOMATION_REF,
  scope: { kind: 'project', selector: 'ora' },
  lifecycle_status: 'available',
  automated_execution_available: true,
  manual_invocation_available: false,
  input_schema: {
    type: 'object', additionalProperties: false,
    properties: {
      message_id: { type: 'string' }, sender: { type: 'string' },
      subject: { type: 'string' }, body: { type: 'string' },
    },
    required: ['message_id', 'sender', 'subject', 'body'],
  },
  package: {
    package_id: 'user/email-processing', package_version: '1.0.0',
    entry_member_id: 'definition', members: [{ member_id: 'definition' }],
  },
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
var automationRequests = [];
var libraryDefinitions = [PROGRAMMING];
global.fetch = function (url, options) {
  if (url === '/api/process-entry/construction-label') {
    return Promise.resolve({
      ok: true,
      json: function () {
        return Promise.resolve({
          ok: true,
          gate: {
            current_label: 'Programming', automatic_rename: false,
            decision_available: false, status: 'bridge_trial_incomplete',
            decision: null, qualifying_witnesses: [],
          },
        });
      },
    });
  }
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
  if (url.indexOf('/api/process-library/entries?project_ref=') === 0) {
    return Promise.resolve({
      ok: true,
      json: function () { return Promise.resolve({ ok: true, definitions: libraryDefinitions }); },
    });
  }
  if (url === '/api/process-automation/runs') {
    automationRequests.push(JSON.parse(options.body));
    return Promise.resolve({
      ok: true, status: 201,
      json: function () { return Promise.resolve({ ok: true, run: {
        run_id: 'automated-run-email', definition_ref: AUTOMATION_REF,
        status: 'awaiting_human_checkpoint', run_state: 'pending',
        current_node: {
          node_id: 'draft-approval', kind: 'human_checkpoint',
          label: 'Approve preparation of an unsent draft',
        },
      } }); },
    });
  }
  if (url === '/api/process-automation/runs/automated-run-email') {
    var action = JSON.parse(options.body);
    automationRequests.push(action);
    return Promise.resolve({
      ok: true,
      json: function () { return Promise.resolve({ ok: true, run: {
        run_id: 'automated-run-email', definition_ref: AUTOMATION_REF,
        status: 'completed', run_state: 'completed',
        current_node: { node_id: 'accepted', kind: 'terminal_state', label: 'Accepted' },
        result: {
          artifact_id: 'result-email', identity_digest: 'sha256:' + 'b'.repeat(64),
          content: {
            classification: 'urgent:finance', summary: 'Invoice is overdue.',
            draft: 'UNSENT DRAFT',
          },
        },
      } }); },
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
  record('Library exposes lifecycle, exact scope, digest, and package membership',
    /registered/.test(w.document.querySelector('.process-entry__library-lifecycle').textContent)
      && /project:ora/.test(w.document.querySelector('.process-entry__library-lifecycle').textContent)
      && /sha256:b79d06b401/.test(
        w.document.querySelector('.process-entry__library-lifecycle').textContent
      )
      && /ora\/programming@2.0.1/.test(
        w.document.querySelector('.process-entry__library-lifecycle').textContent
      )
      && /2 members/.test(
        w.document.querySelector('.process-entry__library-lifecycle').textContent
      ));
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

  libraryDefinitions = [AUTOMATION];
  w.document.getElementById('sidebarProcessLibraryOpen').click();
  await flush();
  await flush();
  w.document.querySelector('.process-entry__library-row').click();
  await flush();
  record('available automated Process opens exact input form instead of ordinary chat',
    !!w.document.querySelector('.process-entry__automation-form')
      && w.document.querySelectorAll('[data-automation-input]').length === 4
      && /separate no-tools worker/.test(w.document.querySelector('.process-entry__notice').textContent));
  ['message_id', 'sender', 'subject', 'body'].forEach(function (name) {
    w.document.querySelector('[data-automation-input="' + name + '"]').value = {
      message_id: 'message-1', sender: 'Alex', subject: 'Urgent invoice',
      body: 'Please review the overdue invoice today.',
    }[name];
  });
  w.document.querySelector('.process-entry__automation-form').dispatchEvent(
    new w.Event('submit', { bubbles: true, cancelable: true })
  );
  await flush();
  record('automated Run cannot start before exact project confirmation',
    automationRequests.length === 0
      && /Confirm the exact Project/.test(
        w.document.querySelector('.process-entry__error').textContent
      ));
  w.document.querySelector('[data-automation-project-confirmed]').checked = true;
  w.document.querySelector('.process-entry__automation-form').dispatchEvent(
    new w.Event('submit', { bubbles: true, cancelable: true })
  );
  await flush();
  await flush();
  record('browser starts exact promoted definition with bounded deterministic identity',
    JSON.stringify(automationRequests[0].definition_ref) === JSON.stringify(AUTOMATION_REF)
      && automationRequests[0].project_ref === 'ora'
      && /^process-ui:[0-9a-f]{8}$/.test(automationRequests[0].idempotency_key)
      && !('trigger' in automationRequests[0])
      && !('persona' in automationRequests[0]));
  record('Run stops visibly at exact human checkpoint',
    /awaiting_human_checkpoint/.test(w.document.querySelector('.process-entry__notice').textContent)
      && !!Array.from(w.document.querySelectorAll('.process-entry__button')).find(function (node) {
        return node.textContent === 'Approve checkpoint';
      }));
  Array.from(w.document.querySelectorAll('.process-entry__button')).find(function (node) {
    return node.textContent === 'Approve checkpoint';
  }).click();
  await flush();
  await flush();
  record('checkpoint approval is exact and completed result stays authenticated',
    automationRequests[1].action === 'resolve_checkpoint'
      && automationRequests[1].outcome === 'approved'
      && !Object.prototype.hasOwnProperty.call(automationRequests[1], 'decision_by')
      && /UNSENT DRAFT/.test(w.document.querySelector('.process-entry__body pre').textContent));

  var passed = results.filter(function (result) { return result.ok; }).length;
  console.log('');
  console.log(passed + ' / ' + results.length + ' tests passed');
  if (passed !== results.length) process.exit(1);
}

run().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
