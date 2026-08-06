#!/usr/bin/env node
/* Explicit standalone Programming browser-surface tests. */

'use strict';

var path = require('path');
var JSDOM_PATH = path.join(
  __dirname, '..', 'ora-visual-compiler', 'tests', 'node_modules', 'jsdom'
);
var jsdom;
try {
  jsdom = require(JSDOM_PATH);
} catch (error) {
  try {
    jsdom = require('jsdom');
  } catch (fallbackError) {
    console.error('error: jsdom not available at ' + JSDOM_PATH);
    process.exit(2);
  }
}

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body><div class="input-pane"></div>' +
  '<button id="inputToolbarProgramming" type="button">Programming</button></body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true }
);
var w = dom.window;
global.window = w;
global.document = w.document;
global.Event = w.Event;
global.CustomEvent = w.CustomEvent;
global.TextDecoder = global.TextDecoder || require('util').TextDecoder;

var requests = [];
var planCalls = 0;
var runCalls = 0;

global.fetch = function (url, options) {
  var payload = JSON.parse(options.body);
  requests.push({ url: url, payload: payload });
  if (url === '/api/programming/recover') {
    return Promise.resolve({
      ok: true,
      json: function () { return Promise.resolve({
        ok: true,
        objective: 'Recovered objective',
        plan: {
          kind: 'plan',
          plan: 'Recovered approved plan.',
          milestones: ['Implement'],
          git_finish_line: 'push',
        },
        branch: 'ora/recovered-1234567',
        accepted_milestones: ['Implement'],
        pending_milestones: [],
        has_uncommitted_changes: true,
      }); },
    });
  }
  if (url === '/api/programming/plan') {
    planCalls += 1;
    return Promise.resolve({
      ok: true,
      json: function () {
        if (planCalls < 3) return Promise.resolve({
          ok: true,
          kind: 'questions',
          questions: [planCalls === 1 ? 'Which scope?' : 'Which risk?'],
          question_round: planCalls,
        });
        return Promise.resolve({
          ok: true,
          kind: 'plan',
          plan: '1. Implement the requested behavior.\n2. Run the focused tests.',
          milestones: [{ name: 'Implement', acceptance: 'Focused tests pass.' }],
          git_finish: { push: false, pull_request: false, merge: false },
        });
      },
    });
  }
  if (url === '/api/programming/run') {
    runCalls += 1;
    var streamEvents = runCalls === 1 ? [
      { type: 'review', outcome: 'DONE', milestone: 'FINAL' },
      { type: 'result', outcome: 'ASK USER', detail: 'Git finish line failed.', branch: 'ora/recovered-1234567', retryable: true },
    ] : runCalls === 2 ? [
      { type: 'result', outcome: 'DONE', branch: 'ora/recovered-1234567' },
    ] : runCalls === 3 ? [
      { type: 'review', outcome: 'ASK USER', milestone: 'Implement', detail: 'Choose safely.' },
      { type: 'result', outcome: 'ASK USER', detail: 'Choose safely.', branch: 'ora/example-1234567' },
    ] : [
      { type: 'milestone', milestone: 'Implement', status: 'accepted', commit: '1234567890' },
      { type: 'review', outcome: 'DONE', milestone: 'FINAL' },
      { type: 'result', outcome: 'DONE', branch: 'ora/example-1234567' },
    ];
    var encoded = Buffer.from(streamEvents.map(function (event) {
      return JSON.stringify(event) + '\n';
    }).join(''));
    var read = false;
    return Promise.resolve({
      ok: true,
      body: {
        getReader: function () {
          return {
            read: function () {
              if (read) return Promise.resolve({ done: true, value: new Uint8Array() });
              read = true;
              return Promise.resolve({ done: false, value: new Uint8Array(encoded) });
            },
          };
        },
      },
    });
  }
  return Promise.reject(new Error('unexpected fetch: ' + url));
};

require(path.resolve(__dirname, '..', 'js', 'programming.js'));
w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));

var failures = 0;
function record(name, ok) {
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name);
  if (!ok) failures += 1;
}
function flush() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}
async function waitForRequests(count) {
  for (var i = 0; i < 10 && requests.length < count; i += 1) await flush();
}

async function run() {
  record('Programming API is registered',
    !!w.OraProgramming && typeof w.OraProgramming.submit === 'function');
  record('ordinary Inquiry begins outside Programming', !w.OraProgramming.isActive());
  record('loading the surface does not route or plan automatically', requests.length === 0);

  w.document.dispatchEvent(new w.CustomEvent('ora:input-toolbar:programming'));
  record('explicit toolbar action activates Programming', w.OraProgramming.isActive());
  record('Programming panel is visible after explicit activation',
    w.document.querySelector('.programming-panel').hidden === false);
  record('active Programming panel can paint outside the clipped Inquiry pane',
    w.document.querySelector('.input-pane').classList.contains('is-programming-active'));

  w.document.querySelector('[data-programming-repository]').value = '/tmp/example-repo';
  w.document.querySelector('[data-programming-recover]').click();
  await waitForRequests(1);
  await flush();
  record('fresh surface reconstructs an approved task through the recovery API',
    requests[0].url === '/api/programming/recover'
      && /Recovered approved plan/.test(w.document.querySelector('.programming-plan').textContent));
  w.document.querySelector('[data-programming-recover-resume]').click();
  await waitForRequests(2);
  await flush();
  record('recovered task resumes from its Git branch without a new decision',
    requests[1].payload.resume_branch === 'ora/recovered-1234567'
      && !requests[1].payload.continuation);
  record('finish failure offers a direct retry and no fake decision field',
    /Retry finish line/.test(w.document.querySelector('[data-programming-resume]').textContent)
      && !w.document.querySelector('[data-programming-continuation]'));
  w.document.querySelector('[data-programming-resume]').click();
  await waitForRequests(3);
  await flush();
  record('finish retry preserves the branch and needs no new approval',
    requests[2].payload.resume_branch === 'ora/recovered-1234567'
      && requests[2].payload.approved === true);

  var assistantMessages = [];
  await w.OraProgramming.submit('Implement the requested change.', {
    renderAssistant: function (message) { assistantMessages.push(message); },
  });
  record('submission begins repository-specific planning',
    requests.length === 4
      && requests[3].url === '/api/programming/plan'
      && requests[3].payload.repository_path === '/tmp/example-repo');
  w.document.querySelector('[data-programming-answer="0"]').value = 'Only app.py';
  w.document.querySelector('[data-programming-continue]').onclick();
  await waitForRequests(2);
  await flush();
  record('second question round retains the first answer',
    requests[4].payload.question_round === 1
      && requests[4].payload.answers[0].answer === 'Only app.py');
  w.document.querySelector('[data-programming-answer="0"]').value = 'No deployment';
  w.document.querySelector('[data-programming-continue]').onclick();
  await waitForRequests(3);
  await flush();
  record('planning pass three receives both question rounds',
    requests[5].payload.question_round === 2
      && requests[5].payload.answers.length === 2
      && requests[5].payload.answers[1].answer === 'No deployment');
  record('plan is shown before execution',
    /Implement the requested behavior/.test(w.document.querySelector('.programming-plan').textContent));
  record('repository has not run before approval',
    requests.slice(3).every(function (request) { return request.url !== '/api/programming/run'; }));

  w.document.querySelector('[data-programming-approve]').click();
  await waitForRequests(7);
  await flush();
  record('approval is explicit in the run request',
    requests.length === 7
      && requests[6].url === '/api/programming/run'
      && requests[6].payload.approved === true);
  record('ASK USER exposes an explicit continuation control',
    !!w.document.querySelector('[data-programming-resume]'));
  w.document.querySelector('[data-programming-continuation]').value = 'Continue safely';
  w.document.querySelector('[data-programming-resume]').click();
  await waitForRequests(8);
  await flush();
  record('resume sends the task branch and user continuation',
    requests[7].payload.resume_branch === 'ora/example-1234567'
      && requests[7].payload.continuation === 'Continue safely');
  record('resumed milestone and final review are visible',
    /Implement: accepted/.test(w.document.querySelector('[data-programming-progress]').textContent)
      && /DONE/.test(w.document.querySelector('[data-programming-progress]').textContent));
  record('terminal result returns a concise message to the conversation',
    assistantMessages.length === 2 && /completed/.test(assistantMessages[1]));

  w.OraProgramming.setActive(false);
  record('closing Programming restores ordinary Inquiry mode', !w.OraProgramming.isActive());

  if (failures) process.exit(1);
}

run().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
