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
var privacyCalls = [];
var privacyAllowed = true;
var activeConversationId = 'dialogue-a';
var navigateDuringNextPlan = false;
var holdNextPrivacy = false;
var releaseHeldPrivacy = null;

w.OraConversation = {
  getActiveConversationId: function () { return activeConversationId; },
  submitAfterPrivacy: async function (text, submit, options) {
    privacyCalls.push({ text: text, draftText: options && options.draftText });
    if (!privacyAllowed) return false;
    if (holdNextPrivacy) {
      holdNextPrivacy = false;
      return new Promise(function (resolve) {
        releaseHeldPrivacy = async function () {
          await submit();
          resolve(true);
        };
      });
    }
    await submit();
    return true;
  },
};

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
    if (navigateDuringNextPlan) {
      navigateDuringNextPlan = false;
      activeConversationId = 'dialogue-b';
      w.document.dispatchEvent(new w.CustomEvent('ora:conversation-selected', {
        detail: { conversation_id: activeConversationId },
      }));
    }
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
  record('recovery and text-free resume reuse approved text without another privacy gate',
    privacyCalls.length === 0);

  var assistantMessages = [];
  var userMessages = [];
  navigateDuringNextPlan = true;
  await w.OraProgramming.submit('Implement the requested change.', {
    renderUser: function (message) {
      userMessages.push({ message: message, conversationId: activeConversationId });
    },
    renderAssistant: function (message) { assistantMessages.push(message); },
  });
  var navigationKeptDialogueBBlank = !w.document.querySelector('.programming-plan')
    && !w.document.querySelector('[data-programming-answer]');
  activeConversationId = 'dialogue-a';
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-selected', {
    detail: { conversation_id: activeConversationId },
  }));
  record('planning navigation renders the objective only in its originating Dialogue',
    navigationKeptDialogueBBlank
      && userMessages.length === 1
      && userMessages[0].conversationId === 'dialogue-a'
      && userMessages[0].message === 'Implement the requested change.'
      && !!w.document.querySelector('[data-programming-answer]'));
  record('submission begins repository-specific planning',
    requests.length === 4
      && requests[3].url === '/api/programming/plan'
      && requests[3].payload.repository_path === '/tmp/example-repo');
  record('initial objective crosses privacy exactly once before planning',
    privacyCalls.length === 1
      && privacyCalls[0].text === 'Implement the requested change.'
      && privacyCalls[0].draftText === 'Implement the requested change.');
  w.document.querySelector('[data-programming-answer="0"]').value = 'Only app.py';
  w.document.querySelector('[data-programming-continue]').onclick();
  await waitForRequests(2);
  await flush();
  record('second question round retains the first answer',
    requests[4].payload.question_round === 1
      && requests[4].payload.answers[0].answer === 'Only app.py');
  record('first planning answer crosses privacy once without regating the objective',
    privacyCalls.length === 2
      && privacyCalls[1].text === 'Only app.py'
      && privacyCalls[1].draftText === '');
  w.document.querySelector('[data-programming-answer="0"]').value = 'No deployment';
  w.document.querySelector('[data-programming-continue]').onclick();
  await waitForRequests(3);
  await flush();
  record('planning pass three receives both question rounds',
    requests[5].payload.question_round === 2
      && requests[5].payload.answers.length === 2
      && requests[5].payload.answers[1].answer === 'No deployment');
  record('follow-up planning answer crosses the same privacy boundary once',
    privacyCalls.length === 3
      && privacyCalls[2].text === 'No deployment');
  record('plan is shown before execution',
    /Implement the requested behavior/.test(w.document.querySelector('.programming-plan').textContent));
  record('repository has not run before approval',
    requests.slice(3).every(function (request) { return request.url !== '/api/programming/run'; }));

  activeConversationId = 'dialogue-b';
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-selected', {
    detail: { conversation_id: activeConversationId },
  }));
  record('a different Dialogue starts with independent Programming state',
    !w.OraProgramming.isActive()
      && w.document.querySelector('[data-programming-repository]').value === ''
      && !w.document.querySelector('.programming-plan'));
  w.OraProgramming.setActive(true);
  w.document.querySelector('[data-programming-repository]').value = '/tmp/other-repo';

  activeConversationId = 'dialogue-a';
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-selected', {
    detail: { conversation_id: activeConversationId },
  }));
  var dialogueARestored = w.OraProgramming.isActive()
    && w.document.querySelector('[data-programming-repository]').value === '/tmp/example-repo'
    && /Implement the requested behavior/.test(
      w.document.querySelector('.programming-plan').textContent
    );
  activeConversationId = 'dialogue-b';
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-selected', {
    detail: { conversation_id: activeConversationId },
  }));
  var dialogueBRestored = w.OraProgramming.isActive()
    && w.document.querySelector('[data-programming-repository]').value === '/tmp/other-repo'
    && !w.document.querySelector('.programming-plan');
  record('each Dialogue restores its own active Programming workflow',
    dialogueARestored && dialogueBRestored);
  activeConversationId = 'dialogue-a';
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-selected', {
    detail: { conversation_id: activeConversationId },
  }));
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-selected', {
    detail: { conversation_id: 'dialogue-b' },
  }));
  var beforePendingObjectiveRequests = requests.length;
  var beforePendingObjectivePrivacy = privacyCalls.length;
  var pendingObjectiveResult = await w.OraProgramming.submit('Do not cross this pending load.');
  record('text-bearing planning is blocked while its Dialogue selection is pending',
    pendingObjectiveResult === false
      && requests.length === beforePendingObjectiveRequests
      && privacyCalls.length === beforePendingObjectivePrivacy);
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-load-failed', {
    detail: {
      conversation_id: 'dialogue-b',
      active_conversation_id: activeConversationId,
    },
  }));
  record('failed Dialogue selection restores the actual Programming workflow',
    w.OraProgramming.isActive()
      && w.document.querySelector('[data-programming-repository]').value === '/tmp/example-repo'
      && /Implement the requested behavior/.test(
        w.document.querySelector('.programming-plan').textContent
      ));

  privacyAllowed = false;
  var beforeCancelledObjective = requests.length;
  var cancelledObjectiveResult = await w.OraProgramming.submit('Run an unapproved objective.');
  record('cancelled objective privacy retains the prior plan without posting',
    cancelledObjectiveResult === false
      && requests.length === beforeCancelledObjective
      && privacyCalls.length === 4
      && privacyCalls[3].text === 'Run an unapproved objective.'
      && /Implement the requested behavior/.test(w.document.querySelector('.programming-plan').textContent)
      && !!w.document.querySelector('[data-programming-approve]'));
  privacyAllowed = true;
  w.document.querySelector('[data-programming-approve]').click();
  activeConversationId = 'dialogue-b';
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-selected', {
    detail: { conversation_id: activeConversationId },
  }));
  await waitForRequests(7);
  await flush();
  var completionDidNotLeak = assistantMessages.length === 0;
  activeConversationId = 'dialogue-a';
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-selected', {
    detail: { conversation_id: activeConversationId },
  }));
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-tag-changed', {
    detail: {
      conversation_id: activeConversationId,
      source: 'conversation-envelope',
    },
  }));
  record('in-flight Programming result is delivered only to its owning Dialogue',
    completionDidNotLeak
      && assistantMessages.length === 1
      && /needs a decision/.test(assistantMessages[0]));
  record('approval is explicit in the run request',
    requests.length === 7
      && requests[6].url === '/api/programming/run'
      && requests[6].payload.approved === true);
  record('retained approval cannot run the cancelled objective or a cleared plan',
    requests[6].payload.objective === 'Implement the requested change.'
      && requests[6].payload.plan
      && /Implement the requested behavior/.test(requests[6].payload.plan.plan));
  record('approval reuses the already-approved objective and plan without another gate',
    privacyCalls.length === 4);
  record('ASK USER exposes an explicit continuation control',
    !!w.document.querySelector('[data-programming-resume]'));
  activeConversationId = 'dialogue-b';
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-selected', {
    detail: { conversation_id: activeConversationId },
  }));
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-selected', {
    detail: { conversation_id: 'dialogue-a' },
  }));
  w.document.querySelector('[data-programming-continuation]').value = 'Do not cross this pending load';
  var beforePendingResumeRequests = requests.length;
  var beforePendingResumePrivacy = privacyCalls.length;
  w.document.querySelector('[data-programming-resume]').click();
  await flush();
  record('text-bearing resume is blocked while its Dialogue selection is pending',
    requests.length === beforePendingResumeRequests
      && privacyCalls.length === beforePendingResumePrivacy);
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-load-failed', {
    detail: {
      conversation_id: 'dialogue-a',
      active_conversation_id: activeConversationId,
    },
  }));
  activeConversationId = 'dialogue-a';
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-selected', {
    detail: { conversation_id: activeConversationId },
  }));
  w.document.querySelector('[data-programming-continuation]').value = 'Continue safely';
  w.document.querySelector('[data-programming-resume]').click();
  await waitForRequests(8);
  await flush();
  record('resume sends the task branch and user continuation',
    requests[7].payload.resume_branch === 'ora/example-1234567'
      && requests[7].payload.continuation === 'Continue safely');
  record('new continuation text crosses privacy exactly once before resume',
    privacyCalls.length === 5
      && privacyCalls[4].text === 'Continue safely'
      && privacyCalls[4].draftText === '');
  record('resumed milestone and final review are visible',
    /Implement: accepted/.test(w.document.querySelector('[data-programming-progress]').textContent)
      && /DONE/.test(w.document.querySelector('[data-programming-progress]').textContent));
  record('terminal result returns a concise message to the conversation',
    assistantMessages.length === 2 && /completed/.test(assistantMessages[1]));

  w.OraProgramming.setActive(false);
  record('closing Programming restores ordinary Inquiry mode', !w.OraProgramming.isActive());

  w.OraProgramming.setActive(true);
  planCalls = 0;
  await w.OraProgramming.submit('Plan another change.');
  w.document.querySelector('[data-programming-answer="0"]').value = 'Only this file';
  privacyAllowed = false;
  var beforeCancelledAnswer = requests.length;
  w.document.querySelector('[data-programming-continue]').onclick();
  await flush();
  record('cancelled answer privacy neither posts nor mutates the planning request',
    requests.length === beforeCancelledAnswer);
  privacyAllowed = true;
  w.document.querySelector('[data-programming-continue]').onclick();
  await waitForRequests(beforeCancelledAnswer + 1);
  await flush();
  record('answer retry is retained once after privacy approval',
    requests[beforeCancelledAnswer].payload.answers.length === 1
      && requests[beforeCancelledAnswer].payload.answers[0].answer === 'Only this file');

  holdNextPrivacy = true;
  var beforeRoundTripRequests = requests.length;
  var roundTripUserMessages = [];
  var roundTripSubmission = w.OraProgramming.submit('Do not survive a navigation round trip.', {
    renderUser: function (message) { roundTripUserMessages.push(message); },
  });
  await flush();
  activeConversationId = 'dialogue-b';
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-selected', {
    detail: { conversation_id: activeConversationId },
  }));
  activeConversationId = 'dialogue-a';
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-selected', {
    detail: { conversation_id: activeConversationId },
  }));
  await releaseHeldPrivacy();
  var roundTripResult = await roundTripSubmission;
  record('delayed privacy acceptance is invalidated by a Dialogue navigation round trip',
    roundTripResult === false
      && requests.length === beforeRoundTripRequests
      && roundTripUserMessages.length === 0);

  w.OraConversation = null;
  var beforeFailedPrivacy = requests.length;
  var missingPrivacyResult = await w.OraProgramming.submit('My password is secret.');
  record('Programming fails closed when the existing privacy boundary is unavailable',
    missingPrivacyResult === false
      && requests.length === beforeFailedPrivacy
      && /Privacy check unavailable/.test(w.document.querySelector('.programming-status').textContent));

  activeConversationId = 'fresh-dialogue';
  w.document.dispatchEvent(new w.CustomEvent('ora:fresh-conversation-started', {
    detail: { conversation_id: activeConversationId },
  }));
  record('a fresh Dialogue starts with reset Programming state',
    !w.OraProgramming.isActive()
      && w.document.querySelector('[data-programming-repository]').value === ''
      && !w.document.querySelector('.programming-plan')
      && /Enter an objective in Inquiry/.test(
        w.document.querySelector('[data-programming-body]').textContent
      ));

  if (failures) process.exit(1);
}

run().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
