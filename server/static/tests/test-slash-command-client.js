#!/usr/bin/env node
/* Focused jsdom tests for browser-side slash commands.
 *
 * Run:
 *   node ~/ora/server/static/tests/test-slash-command-client.js
 */

'use strict';

var path = require('path');

var COMPILER_TEST_NODE_MODULES = path.resolve(
  __dirname, '..', 'ora-visual-compiler', 'tests', 'node_modules'
);
var JSDOM_PATH = path.join(COMPILER_TEST_NODE_MODULES, 'jsdom');

var jsdom;
try {
  jsdom = require(JSDOM_PATH);
} catch (e) {
  console.error('error: jsdom not available at ' + JSDOM_PATH);
  process.exit(2);
}

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body>' +
  '<button id="inputToolbarImageGenerate" type="button"></button>' +
  '<button id="sidebarReviewQueueOpen" type="button"></button>' +
  '</body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true }
);

var w = dom.window;
global.window = w;
global.document = w.document;
global.HTMLElement = w.HTMLElement;
global.Event = w.Event;
global.CustomEvent = w.CustomEvent;

var alerts = [];
w.alert = function (msg) { alerts.push(msg); };
global.alert = w.alert;

var fetches = [];
global.fetch = w.fetch = function (url) {
  fetches.push(url);
  if (url === '/api/frameworks/picker') {
    return Promise.resolve({
      ok: true,
      json: function () {
        return Promise.resolve({
          frameworks: [
            {
              id: 'corpus-formalization',
              display_name: 'Corpus Formalization',
              display_description: 'CFF',
              category: 'standard',
            },
          ],
        });
      },
    });
  }
  if (url === '/api/analyses/picker') {
    return Promise.resolve({
      ok: true,
      json: function () {
        return Promise.resolve({
          modes: [
            {
              id: 'root-cause-analysis',
              display_name: 'Root Cause Analysis',
              display_description: 'find causes',
              educational_name: 'root cause',
              territory: 'T4',
              territory_name: 'Causal Investigation',
              territory_order: 4,
            },
          ],
        });
      },
    });
  }
  return Promise.reject(new Error('unexpected fetch: ' + url));
};

var reviewOpens = [];
w.OraReviewQueuePanel = {
  open: function (opts) { reviewOpens.push(opts || {}); },
};

var settingsOpens = [];
w.OraSettingsPanel = {
  open: function (opts) { settingsOpens.push(opts || {}); },
};

var newThreadEvents = 0;
w.document.addEventListener('ora:new-thread-requested', function () {
  newThreadEvents += 1;
});

var imageDispatches = [];
var imagePrivacyText = null;
var releaseImagePrivacy = null;
var activeConversationId = 'image-parent';
w.document.body.addEventListener('capability-dispatch', function (event) {
  imageDispatches.push(event.detail || {});
});
w.OraConversation = {
  getActiveConversationId: function () { return activeConversationId; },
  getActiveTag: function () { return activeConversationId === 'image-child' ? 'private' : ''; },
  submitAfterPrivacy: function (text, submit) {
    imagePrivacyText = text;
    return new Promise(function (resolve) {
      releaseImagePrivacy = function () {
        activeConversationId = 'image-child';
        Promise.resolve(submit()).then(function () { resolve(true); });
      };
    });
  },
};

require(path.resolve(__dirname, '..', 'js', 'input-state.js'));
require(path.resolve(__dirname, '..', 'js', 'slash-command-client.js'));

var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? '  - ' + detail : ''));
}

function summarize() {
  var total = results.length;
  var passed = results.filter(function (r) { return r.ok; }).length;
  console.log('');
  console.log(passed + ' / ' + total + ' tests passed');
  if (passed < total) {
    console.log('FAILURES:');
    results.filter(function (r) { return !r.ok; }).forEach(function (r) {
      console.log('  - ' + r.name + ' :: ' + (r.detail || '(no detail)'));
    });
    process.exit(1);
  }
  process.exit(0);
}

function flush() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

async function run() {
  record('OraSlashCommands registered',
    !!w.OraSlashCommands && typeof w.OraSlashCommands.handleClientCommand === 'function');

  record('/frameworks cff handled',
    w.OraSlashCommands.handleClientCommand('/frameworks cff') === true);
  await flush();
  await flush();
  record('/frameworks cff stages CFF',
    w.OraInputState.getFramework()
      && w.OraInputState.getFramework().id === 'corpus-formalization',
    JSON.stringify(w.OraInputState.getFramework()));

  record('/modes root-cause-analysis handled',
    w.OraSlashCommands.handleClientCommand('/modes root-cause-analysis') === true);
  await flush();
  await flush();
  record('/modes root-cause-analysis stages mode',
    w.OraInputState.getAnalysisMode()
      && w.OraInputState.getAnalysisMode().id === 'root-cause-analysis',
    JSON.stringify(w.OraInputState.getAnalysisMode()));
  record('staging a mode clears staged framework',
    w.OraInputState.getFramework() === null);

  record('/review opens review panel',
    w.OraSlashCommands.handleClientCommand('/review') === true
      && reviewOpens.length === 1
      && reviewOpens[0].tab === 'paused',
    JSON.stringify(reviewOpens));

  record('/review operating opens operating tab',
    w.OraSlashCommands.handleClientCommand('/review operating') === true
      && reviewOpens.length === 2
      && reviewOpens[1].tab === 'operating',
    JSON.stringify(reviewOpens));

  record('/settings projects opens Projects tab',
    w.OraSlashCommands.handleClientCommand('/settings projects') === true
      && settingsOpens.length === 1
      && settingsOpens[0].tab === 'projects',
    JSON.stringify(settingsOpens));

  record('/new dispatches new thread event',
    w.OraSlashCommands.handleClientCommand('/new') === true && newThreadEvents === 1,
    'events=' + newThreadEvents);

  record('/image prompt is handled but waits at privacy before dispatch',
    w.OraSlashCommands.handleClientCommand('/image My medical scan') === true
      && imagePrivacyText === 'My medical scan'
      && imageDispatches.length === 0);
  releaseImagePrivacy();
  await flush();
  record('/image dispatches exactly once to the post-fork child',
    imageDispatches.length === 1
      && imageDispatches[0].conversation_id === 'image-child'
      && imageDispatches[0].tag === 'private'
      && imageDispatches[0].inputs.prompt === 'My medical scan');

  w.OraConversation = null;
  record('/image fails closed without privacy controls',
    w.OraSlashCommands.handleClientCommand('/image My password') === true
      && imageDispatches.length === 1
      && alerts.some(function (message) {
        return /Privacy check unavailable/.test(message);
      }));

  record('only the expected privacy failure alert was shown',
    alerts.length === 1, alerts.join('; '));
  record('picker APIs were fetched',
    fetches.indexOf('/api/frameworks/picker') >= 0
      && fetches.indexOf('/api/analyses/picker') >= 0,
    fetches.join(', '));

  summarize();
}

run().catch(function (err) {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
