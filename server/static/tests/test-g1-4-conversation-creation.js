#!/usr/bin/env node
/* DOM contract for G1.4 reviewed Dialogue creation and Library actions. */
'use strict';

var fs = require('fs');
var path = require('path');
var vm = require('vm');
var JSDOM_PATH = path.join(
  __dirname, '..', 'ora-visual-compiler', 'tests', 'node_modules', 'jsdom'
);
var jsdom;
try { jsdom = require(JSDOM_PATH); }
catch (e) { console.error('error: jsdom not available'); process.exit(2); }

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body>' +
  '<div class="left-sidebar">' +
  ' <button class="sidebar-new-thread-cmd">New Dialogue</button>' +
  ' <button class="sidebar-fork-thread-cmd" disabled>Fork</button>' +
  ' <button class="sidebar-browse-cmd">Library</button>' +
  '</div>' +
  '<div class="output-pane">' +
  ' <span id="outputPaneDisplayName"></span><span id="outputPaneModeIcon"></span>' +
  ' <button id="outputPaneNavBack"></button><button id="outputPaneNavForward"></button>' +
  ' <span id="outputPaneTurnPosition"></span><span id="outputPaneTimestamp"></span>' +
  ' <div class="output-content"></div>' +
  '</div>' +
  '<div class="input-pane"><textarea></textarea></div>' +
  '</body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
);

var w = dom.window;
var createRequests = [];
var reviewRequests = [];
var browserUrls = [];
var forkRequests = 0;
var envelopeRequests = [];
var failNextCreate = false;
var acceptedReview = null;
var description = 'Explore cash-flow exception patterns and decide a reusable response.';
var envelopes = {
  'source-live': {
    conversation_id: 'source-live', display_name: 'Prior cash-flow work', tag: '',
    messages: [{ role: 'user', content: 'Prior prompt' }, { role: 'assistant', content: 'Prior response' }],
  },
  'created-live': {
    conversation_id: 'created-live', display_name: 'Cash-flow review', tag: '',
    description: description, contributors: [], messages: [],
  },
  'forked-live': {
    conversation_id: 'forked-live', display_name: 'Prior cash-flow work (fork)', tag: '',
    messages: [{ role: 'user', content: 'Prior prompt' }, { role: 'assistant', content: 'Prior response' }],
  },
};

function result(ok, payload, status) {
  return Promise.resolve({
    ok: ok, status: status || (ok ? 200 : 400),
    json: function () { return Promise.resolve(payload || {}); },
    arrayBuffer: function () { return Promise.resolve(new ArrayBuffer(0)); },
  });
}

w.fetch = function (url, opts) {
  var decoded = decodeURIComponent(String(url));
  if (decoded.indexOf('/api/conversations/browser?') === 0) {
    browserUrls.push(decoded);
    if (decoded.indexOf('purpose=creation') !== -1) {
      return result(true, {
        review_token: 'review-token-' + browserUrls.length,
        rows: [{
          conversation_id: 'source-live', source_kind: 'live', tag: '',
          title: 'Prior cash-flow work', snippet: 'Prior response',
        }, {
          conversation_id: 'engram:atomic', source_kind: 'engram',
          title: 'Atomic cash-flow claim', snippet: 'A durable observation', tags: ['atomic'],
        }],
        total: 2,
      });
    }
    return result(true, {
      rows: [{
        conversation_id: 'source-live', source_kind: 'live', tag: '',
        title: 'Prior cash-flow work', snippet: 'Prior response',
      }],
      total: 1,
    });
  }
  if (decoded === '/api/conversations/create') {
    var body = JSON.parse(opts.body);
    createRequests.push(body);
    if (failNextCreate) {
      failNextCreate = false;
      return result(false, { error: 'discovery review is missing or expired' }, 409);
    }
    return result(true, {
      conversation_id: 'created-live', display_name: acceptedReview.title,
      description: acceptedReview.description, tag: acceptedReview.tag,
      contributors: acceptedReview.contributors, contract_digest: 'sha256:contract',
    }, 201);
  }
  if (decoded === '/api/conversations/review') {
    var reviewBody = JSON.parse(opts.body);
    reviewRequests.push(reviewBody);
    if (reviewBody.acknowledged !== true) {
      return result(false, { error: 'explicit review acknowledgment is required' }, 400);
    }
    acceptedReview = reviewBody;
    return result(true, {
      creation_token: 'creation-token-' + reviewRequests.length,
      contract_digest: 'sha256:contract',
      conversation_id: 'created-live',
    });
  }
  if (/^\/api\/conversation\/[^/]+\/fork$/.test(decoded)) {
    forkRequests += 1;
    return result(true, { new_conversation_id: 'forked-live', tag: '' });
  }
  if (decoded.indexOf('/api/conversations?') === 0) {
    return result(true, { pinned: [], errored: [], pending: [], unread: [], active: [] });
  }
  if (decoded === '/api/active-project') return result(true, { nexus: 'commons' });
  if (decoded.indexOf('/api/projects') === 0) return result(true, { projects: [] });
  if (decoded === '/api/configurations/active') return result(true, {});
  if (decoded === '/api/styles/registry') return result(true, { settings: {}, profiles: [], custom: [] });
  if (/\/mark-read$/.test(decoded)) return result(true, { ok: true });
  if (decoded.indexOf('/api/canvas/load/') === 0) return result(false, {}, 404);
  var envelopeMatch = decoded.match(/^\/api\/conversation\/(.+)$/);
  if (envelopeMatch && !opts) {
    envelopeRequests.push(envelopeMatch[1]);
    return result(!!envelopes[envelopeMatch[1]], envelopes[envelopeMatch[1]], 200);
  }
  return result(false, {}, 404);
};

w.alert = function () {};
w.ResizeObserver = function () { this.observe = function () {}; this.disconnect = function () {}; };
w.setInterval = function () { return 0; };
w.clearInterval = function () {};
var context = dom.getInternalVMContext();
context.console = console;
context.fetch = w.fetch;
context.alert = w.alert;
context.ResizeObserver = w.ResizeObserver;
context.setInterval = w.setInterval;
context.clearInterval = w.clearInterval;

function load(rel) {
  var abs = path.resolve(__dirname, '..', rel);
  vm.runInContext(fs.readFileSync(abs, 'utf8'), context, { filename: abs });
}
load('js/sidebar.js');
load('js/v3-conversation.js');
w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));

var checks = [];
function record(name, ok, detail) {
  checks.push(!!ok);
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? ' - ' + detail : ''));
}
function flush() { return new Promise(function (resolve) { w.setTimeout(resolve, 0); }); }
function input(selector, value) {
  var el = w.document.querySelector(selector);
  el.value = value;
  el.dispatchEvent(new w.Event('input', { bubbles: true }));
  return el;
}
async function openAndDiscover() {
  w.document.querySelector('.sidebar-new-thread-cmd').click();
  input('.conversation-create-title', 'Cash-flow review');
  input('.conversation-create-description', description);
  w.document.querySelector('.conversation-create-discover').click();
  await flush(); await flush();
}

async function run() {
  var newButton = w.document.querySelector('.sidebar-new-thread-cmd');
  newButton.click();
  var modal = w.document.querySelector('.conversation-create-overlay');
  record('New opens a modal without creating a Dialogue',
    modal.classList.contains('is-open') && createRequests.length === 0);
  record('modal separates title and expanded description',
    !!modal.querySelector('.conversation-create-title') &&
    !!modal.querySelector('.conversation-create-description'));

  input('.conversation-create-title', 'Cash-flow review');
  input('.conversation-create-description', description);
  record('creation stays disabled before discovery and explicit review',
    modal.querySelector('.conversation-create-commit').disabled === true);
  modal.querySelector('.conversation-create-discover').click();
  await flush(); await flush();
  record('discovery queries the combined creation surface',
    browserUrls.some(function (url) {
      return url.indexOf('purpose=creation') !== -1 &&
        url.indexOf('conversations=1') !== -1 && url.indexOf('engrams=1') !== -1;
    }));
  record('results distinguish Dialogues and atomic notes',
    modal.querySelectorAll('.conversation-create-result').length === 2 &&
    modal.textContent.indexOf('Atomic note') !== -1);
  modal.querySelector('.conversation-create-add').click();
  var reviewed = modal.querySelector('.conversation-create-reviewed input');
  reviewed.checked = true;
  reviewed.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush(); await flush();
  record('explicit review unlocks exact creation',
    modal.querySelector('.conversation-create-commit').disabled === false &&
    reviewRequests.length === 1 && reviewRequests[0].acknowledged === true);
  modal.querySelector('.conversation-create-commit').click();
  await flush(); await flush(); await flush();
  record('accepted contributor identity reaches the create contract',
    createRequests.length === 1 &&
    reviewRequests[0].contributors.length === 1 &&
    reviewRequests[0].contributors[0] === 'source-live' &&
    Object.keys(createRequests[0]).sort().join(',') === 'creation_token,review_token');
  record('created zero-turn Dialogue restores description as an unsent draft',
    envelopeRequests.indexOf('created-live') !== -1 &&
    w.document.querySelector('.input-pane textarea').value === description);

  await openAndDiscover();
  reviewed = modal.querySelector('.conversation-create-reviewed input');
  reviewed.checked = true;
  reviewed.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush(); await flush();
  input('.conversation-create-title', 'Changed after confirmation');
  record('changing a bound creation input invalidates server confirmation',
    modal.querySelector('.conversation-create-commit').disabled === true &&
    reviewed.checked === false);
  modal.querySelector('.conversation-create-cancel').click();

  await openAndDiscover();
  var createsBeforeContinue = createRequests.length;
  modal.querySelector('.conversation-create-continue').click();
  await flush(); await flush();
  record('Continue uses the existing Dialogue and carries the description',
    createRequests.length === createsBeforeContinue &&
    envelopeRequests[envelopeRequests.length - 1] === 'source-live' &&
    w.document.querySelector('.input-pane textarea').value === description);

  await openAndDiscover();
  modal.querySelector('.conversation-create-fork').click();
  await flush(); await flush(); await flush();
  record('Fork creates lineage and carries the description',
    forkRequests === 1 && envelopeRequests.indexOf('forked-live') !== -1 &&
    w.document.querySelector('.input-pane textarea').value === description);

  await openAndDiscover();
  input('.conversation-create-description', description + ' Refined.');
  record('editing the description invalidates the prior review',
    modal.querySelector('.conversation-create-commit').disabled === true &&
    modal.querySelectorAll('.conversation-create-result').length === 0);
  modal.querySelector('.conversation-create-cancel').click();

  w.document.querySelector('.sidebar-browse-cmd').click();
  await flush(); await flush();
  w.document.querySelector('.conversation-browser-add-contributor').click();
  input('.conversation-create-title', 'Library-seeded review');
  input('.conversation-create-description', description);
  modal.querySelector('.conversation-create-discover').click();
  await flush(); await flush();
  var lastDiscovery = browserUrls.filter(function (url) {
    return url.indexOf('purpose=creation') !== -1;
  }).pop();
  record('Library Add binds the exact row into the next reviewed search',
    lastDiscovery.indexOf('include_ref=source-live') !== -1 &&
    modal.querySelector('.conversation-create-add').getAttribute('aria-pressed') === 'true');

  reviewed = modal.querySelector('.conversation-create-reviewed input');
  reviewed.checked = true;
  reviewed.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush(); await flush();
  failNextCreate = true;
  modal.querySelector('.conversation-create-commit').click();
  await flush(); await flush();
  record('stale review failure remains visible and does not navigate',
    modal.classList.contains('is-open') &&
    modal.querySelector('.conversation-create-status').textContent.indexOf('missing or expired') !== -1);

  var passed = checks.filter(Boolean).length;
  console.log('\n' + passed + ' / ' + checks.length + ' tests passed');
  process.exit(passed === checks.length ? 0 : 1);
}

run().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
