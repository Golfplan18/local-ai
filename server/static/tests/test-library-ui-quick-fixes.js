#!/usr/bin/env node
/* Focused jsdom coverage for the Library/UI quick-fix bundle.
 *
 * Run:
 *   node ~/ora/server/static/tests/test-library-ui-quick-fixes.js
 */

'use strict';

var fs = require('fs');
var path = require('path');
var vm = require('vm');

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
  '<div class="left-sidebar">' +
  '  <button class="sidebar-fork-thread-cmd" disabled>Fork</button>' +
  '  <button class="sidebar-browse-cmd">Library</button>' +
  '</div>' +
  '<div class="output-pane">' +
  '  <span id="outputPaneDisplayName" class="output-pane-display-name">Dialogue</span>' +
  '  <span id="outputPaneModeIcon"></span>' +
  '  <button id="outputPaneNavBack"></button>' +
  '  <button id="outputPaneNavForward"></button>' +
  '  <span id="outputPaneTurnPosition"></span>' +
  '  <span id="outputPaneTimestamp"></span>' +
  '  <div class="output-content"></div>' +
  '</div>' +
  '<div class="input-pane"><textarea></textarea></div>' +
  '</body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
);

var w = dom.window;
var forkRequests = 0;
var browserRequests = 0;
var envelopeRequests = 0;
var envelopes = {
  'named-live': {
    conversation_id: 'named-live',
    display_name: 'Saved Dialogue Name',
    messages: [
      { role: 'user', content: 'This text must not replace the saved name.' },
      { role: 'assistant', content: 'Response.' },
    ],
  },
  'empty-live': {
    conversation_id: 'empty-live',
    display_name: 'Empty Dialogue',
    messages: [],
  },
  'engram:claim': {
    conversation_id: 'engram:claim',
    display_name: 'Atomic Claim Title',
    archived_source: true,
    result_type: 'engram',
    messages: [{ role: 'assistant', content: '# Atomic Claim Title\nBody' }],
  },
};

function response(ok, payload, status) {
  return Promise.resolve({
    ok: ok,
    status: status || (ok ? 200 : 404),
    json: function () { return Promise.resolve(payload || {}); },
    arrayBuffer: function () { return Promise.resolve(new ArrayBuffer(0)); },
  });
}

w.fetch = function (url, opts) {
  var decoded = decodeURIComponent(String(url));
  if (decoded.indexOf('/api/conversations/browser?') === 0) {
    browserRequests += 1;
    return response(true, {
      rows: [{
        conversation_id: 'named-live',
        source_kind: 'live',
        title: 'Saved Dialogue Name',
        snippet: 'This second line must not be rendered.',
      }],
      total: 1,
    });
  }
  if (decoded.indexOf('/api/conversations?') === 0) {
    return response(true, { pinned: [], errored: [], pending: [], unread: [], active: [] });
  }
  if (/\/api\/conversation\/[^/]+\/fork$/.test(decoded)) {
    forkRequests += 1;
    return response(true, { new_conversation_id: 'forked-live' });
  }
  if (/\/api\/conversation\/[^/]+\/mark-read$/.test(decoded)) return response(true, { ok: true });
  if (decoded.indexOf('/api/canvas/load/') === 0) return response(false, {}, 404);
  var match = decoded.match(/^\/api\/conversation\/(.+)$/);
  if (match && !opts) {
    envelopeRequests += 1;
    return response(!!envelopes[match[1]], envelopes[match[1]], envelopes[match[1]] ? 200 : 404);
  }
  return response(false, {}, 404);
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

function loadScript(rel) {
  var abs = path.resolve(__dirname, '..', rel);
  vm.runInContext(fs.readFileSync(abs, 'utf8'), context, { filename: abs });
}

loadScript('js/sidebar.js');
loadScript('js/v3-conversation.js');
w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));

var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? '  - ' + detail : ''));
}
function flush() {
  return new Promise(function (resolve) { w.setTimeout(resolve, 0); });
}

async function run() {
  var fork = w.document.querySelector('.sidebar-fork-thread-cmd');
  var title = w.document.getElementById('outputPaneDisplayName');

  record('Fork starts disabled', fork.disabled === true);

  await w.OraConversation.load('named-live');
  await flush();
  record('stored display_name wins over first user text',
    title.textContent === 'Saved Dialogue Name', title.textContent);
  record('live Dialogue keeps rename affordance',
    title.classList.contains('is-clickable') && title.title === 'Click to rename');
  record('Dialogue with a turn enables Fork', fork.disabled === false);

  await w.OraConversation.load('empty-live');
  await flush();
  record('zero-turn Dialogue disables Fork', fork.disabled === true);
  await w.OraConversation.forkActive();
  record('guard prevents zero-turn fork request', forkRequests === 0, 'requests=' + forkRequests);

  await w.OraConversation.load('engram:claim');
  await flush();
  record('engram display_name replaces encoded id',
    title.textContent === 'Atomic Claim Title', title.textContent);
  record('engram has no rename affordance',
    !title.classList.contains('is-clickable') && !title.hasAttribute('title'));
  title.click();
  record('clicking engram title does not create rename input',
    title.querySelector('input') === null);
  record('read-only engram keeps Fork disabled', fork.disabled === true);

  w.OraConversation.startFresh({ conversation_id: 'fresh-live' });
  record('fresh zero-turn Dialogue disables Fork', fork.disabled === true);
  w.OraConversation.appendUser('First prompt');
  record('first turn enables Fork', fork.disabled === false);

  w.document.querySelector('.sidebar-browse-cmd').click();
  await flush();
  await flush();
  record('Library fetched rows', browserRequests > 0, 'requests=' + browserRequests);
  record('Library row renders title',
    !!w.document.querySelector('.conversation-browser-row .conversation-browser-title'));
  record('Library row omits snippet element',
    w.document.querySelector('.conversation-browser-snippet') === null);

  var library = w.document.querySelector('.conversation-browser-overlay');
  var search = w.document.querySelector('.conversation-browser-search');
  var row = w.document.querySelector('.conversation-browser-row');
  var check = row.querySelector('.conversation-browser-check');
  var related = row.querySelector('.conversation-browser-related');
  var dismiss = row.querySelector('.conversation-browser-dismiss');
  record('Library dialog has an accessible name',
    library.getAttribute('aria-label') === 'Library');
  record('Library exposes non-modal dialog semantics',
    library.getAttribute('role') === 'dialog' &&
    library.getAttribute('aria-modal') === 'false');
  record('Library search has a programmatic label',
    search.getAttribute('aria-label') === 'Search Dialogues');
  var titleButton = row.querySelector('.conversation-browser-title');
  record('Library row exposes a labelled group',
    row.getAttribute('role') === 'group' &&
    row.getAttribute('aria-label') === 'Dialogue: Saved Dialogue Name');
  record('Library title is a keyboard-focusable open control',
    titleButton.tagName === 'BUTTON' &&
    titleButton.getAttribute('aria-label') === 'Open Dialogue: Saved Dialogue Name');
  record('Library row controls have specific accessible names',
    check.getAttribute('aria-label') === 'Select Dialogue: Saved Dialogue Name' &&
    related.getAttribute('aria-label') === 'Show items related to Saved Dialogue Name' &&
    dismiss.getAttribute('aria-label') === 'Remove Saved Dialogue Name from these results');

  var requestsBeforeTitleOpen = envelopeRequests;
  titleButton.click();
  await flush();
  record('Library title control opens its row',
    envelopeRequests > requestsBeforeTitleOpen,
    'requests=' + envelopeRequests);

  var browseButton = w.document.querySelector('.sidebar-browse-cmd');
  var escapeTargets = [
    ['search', '.conversation-browser-search'],
    ['sort', '.conversation-browser-sort'],
    ['Search button', '.conversation-browser-search-btn'],
    ['Close button', '.conversation-browser-close'],
    ['Dialogue filter', '.conversation-browser-filter-conversations'],
    ['Engram filter', '.conversation-browser-filter-engrams'],
    ['relevance slider', '.conversation-browser-relevance-slider'],
    ['row checkbox', '.conversation-browser-check'],
    ['row title', '.conversation-browser-title'],
    ['Related button', '.conversation-browser-related'],
    ['row dismiss button', '.conversation-browser-dismiss'],
  ];
  var escapeFailures = [];
  for (var i = 0; i < escapeTargets.length; i += 1) {
    browseButton.focus();
    browseButton.click();
    await flush();
    await flush();
    var escapeTarget = w.document.querySelector(escapeTargets[i][1]);
    if (!escapeTarget) {
      escapeFailures.push(escapeTargets[i][0] + ': missing control');
      continue;
    }
    escapeTarget.focus();
    escapeTarget.dispatchEvent(new w.KeyboardEvent('keydown', {
      key: 'Escape', bubbles: true, cancelable: true,
    }));
    if (library.classList.contains('is-open')) {
      escapeFailures.push(escapeTargets[i][0] + ': Library stayed open');
    } else if (w.document.activeElement !== browseButton) {
      escapeFailures.push(escapeTargets[i][0] + ': focus was not restored');
    }
  }
  record('Escape closes Library from every control and restores focus',
    escapeFailures.length === 0, escapeFailures.join('; '));

  browseButton.focus();
  browseButton.click();
  await flush();
  var workspaceInput = w.document.querySelector('.input-pane textarea');
  workspaceInput.focus();
  workspaceInput.dispatchEvent(new w.KeyboardEvent('keydown', {
    key: 'Escape', bubbles: true, cancelable: true,
  }));
  record('Escape closes non-modal Library when focus is elsewhere',
    !library.classList.contains('is-open') && w.document.activeElement === browseButton);

  var passed = results.filter(function (r) { return r.ok; }).length;
  console.log('\n' + passed + ' / ' + results.length + ' tests passed');
  if (passed !== results.length) {
    results.filter(function (r) { return !r.ok; }).forEach(function (r) {
      console.log('  - ' + r.name + ': ' + (r.detail || 'failed'));
    });
    process.exit(1);
  }
  process.exit(0);
}

run().catch(function (err) {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
