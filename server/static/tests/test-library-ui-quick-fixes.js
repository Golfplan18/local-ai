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

var COMPILER_TEST_NODE_MODULES = process.env.COMPILER_TEST_NODE_MODULES || path.resolve(
  __dirname, '..', 'ora-visual-compiler', 'tests', 'node_modules'
);
var JSDOM_PATH = path.join(COMPILER_TEST_NODE_MODULES, 'jsdom');
var jsdom;
try {
  jsdom = require(JSDOM_PATH);
} catch (e) {
  console.error('error: jsdom not available at ' + JSDOM_PATH + ': ' + e.message);
  process.exit(2);
}

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body>' +
  '<div class="left-sidebar">' +
  '  <div class="sidebar-collapsed-dashboard">' +
  '    <button id="sidebarDashProject">Projects</button>' +
  '    <button id="sidebarDashModel">Model</button>' +
  '    <button id="sidebarDashOutputStyle">Output Style</button>' +
  '  </div>' +
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
var browserRequestUrls = [];
var relatedRequestUrls = [];
var queuedBrowserResponses = [];
var sidebarListRequests = 0;
var envelopeRequests = 0;
var projectWrites = [];
var bulkFailIds = new Set();
var settingsTabs = [];
var envelopes = {
  'named-live': {
    conversation_id: 'named-live',
    display_name: 'Saved Dialogue Name',
    tag: '',
    project_ids: ['existing-project'],
    messages: [
      { role: 'user', content: 'This text must not replace the saved name.' },
      { role: 'assistant', content: 'Response.' },
    ],
  },
  'second-live': {
    conversation_id: 'second-live',
    project_ids: [],
  },
  'third-live': {
    conversation_id: 'third-live',
    project_ids: [],
  },
  'empty-live': {
    conversation_id: 'empty-live',
    display_name: 'Empty Dialogue',
    tag: '',
    messages: [],
  },
  'engram:claim': {
    conversation_id: 'engram:claim',
    display_name: 'Atomic Claim Title',
    tag: '',
    archived_source: true,
    result_type: 'engram',
    messages: [{ role: 'assistant', content: '# Atomic Claim Title\nBody' }],
  },
};

function responseObject(ok, payload, status, headerValues) {
  var values = headerValues || {};
  return {
    ok: ok,
    status: status || (ok ? 200 : 404),
    headers: {
      get: function (name) { return values[name] || values[String(name).toLowerCase()] || null; },
    },
    json: function () { return Promise.resolve(payload || {}); },
    arrayBuffer: function () { return Promise.resolve(new ArrayBuffer(0)); },
  };
}

function response(ok, payload, status, headerValues) {
  return Promise.resolve(responseObject(ok, payload, status, headerValues));
}

function deferredResponse() {
  var resolve;
  var item = {
    promise: new Promise(function (done) { resolve = done; }),
    options: null,
    resolve: function (payload) { resolve(responseObject(true, payload)); },
  };
  return item;
}

w.fetch = function (url, opts) {
  var decoded = decodeURIComponent(String(url));
  if (decoded.indexOf('/api/conversations/browser?') === 0) {
    browserRequests += 1;
    browserRequestUrls.push(decoded);
    if (queuedBrowserResponses.length) {
      var queued = queuedBrowserResponses.shift();
      queued.options = opts || {};
      return queued.promise;
    }
    return response(true, {
      rows: [
        {
          conversation_id: 'named-live',
          source_kind: 'live',
          title: 'Saved Dialogue Name',
          snippet: 'This second line must not be rendered.',
          project_ids: ['existing-project'],
        },
        {
          conversation_id: 'second-live',
          source_kind: 'live',
          title: 'Second Dialogue',
          project_ids: [],
        },
        {
          conversation_id: 'third-live',
          source_kind: 'live',
          title: 'Third Dialogue',
          project_ids: [],
        },
        {
          conversation_id: 'engram:claim',
          source_kind: 'engram',
          title: 'Atomic Claim Title',
          project_ids: [],
        },
      ],
      total: 15,
      source_counts: { live: 10, archive: 3, engram: 2 },
      facets: {
        projects: { available: true, counts: { commons: 3, 'project-a': 12 } },
        dates: { available: true, min: '2026-01-01', max: '2026-08-31' },
        privacy: {
          available: true,
          counts: { standard: 12, contains_private: 2, stealth: 1 },
        },
        lifecycle: {
          available: true,
          counts: { active: 10, inactive: 2, indexed_archive: 3, knowledge: 0 },
        },
        relationships: {
          available: true,
          counts: { parent: 2, 'direct-child': 3, sibling: 1, contributor: 0,
            'direct-related': 0, 'shared-project': 5, none: 4 },
        },
        local_restriction: {
          available: false,
          counts: { restricted: 0, unrestricted: 0 },
          unavailable: 15,
        },
      },
    });
  }
  if (decoded === '/api/projects/meta?status=active') {
    return response(true, {
      projects: [
        { nexus: 'commons', name: 'Commons' },
        { nexus: 'project-a', name: 'Project A' },
      ],
    });
  }
  var projectWrite = decoded.match(/^\/api\/conversation\/([^/]+)\/projects$/);
  if (projectWrite && opts && opts.method === 'POST') {
    var writeId = projectWrite[1];
    var writeBody = JSON.parse(opts.body || '{}');
    projectWrites.push({ id: writeId, body: writeBody });
    if (bulkFailIds.has(writeId)) return response(false, { error: 'simulated failure' }, 500);
    var storedProjects = Array.isArray(envelopes[writeId] && envelopes[writeId].project_ids)
      ? envelopes[writeId].project_ids.slice() : [];
    if (storedProjects.indexOf(writeBody.add_project_id) === -1) {
      storedProjects.push(writeBody.add_project_id);
    }
    if (envelopes[writeId]) envelopes[writeId].project_ids = storedProjects;
    return response(true, { project_ids: storedProjects });
  }
  if (/^\/api\/conversation\/[^/]+\/related\?/.test(decoded)) {
    relatedRequestUrls.push(decoded);
    return response(true, {
      rows: [{
        conversation_id: 'named-live',
        source_kind: 'live',
        title: 'Saved Dialogue Name',
      }],
      total: 1,
      source_counts: { live: 1, archive: 0, engram: 0 },
      facets: { local_restriction: { available: false, counts: {
        restricted: 0, unrestricted: 0,
      } } },
    });
  }
  if (decoded.indexOf('/api/conversations?') === 0) {
    sidebarListRequests += 1;
    if (opts && opts.headers && opts.headers['If-None-Match'] === '"sidebar-v1"') {
      return response(false, {}, 304);
    }
    return response(true, {
      pinned: [],
      errored: [],
      pending: [],
      unread: [],
      active: [{ conversation_id: 'sidebar-stable', title: 'Stable row', tag: '' }],
    }, 200, { ETag: '"sidebar-v1"' });
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
var intervalCalls = 0;
var intervalClears = 0;
var nextIntervalHandle = 1;
w.setInterval = function () { intervalCalls += 1; return nextIntervalHandle++; };
w.clearInterval = function () { intervalClears += 1; };
w.OraSettingsPanel = {
  open: function (options) { settingsTabs.push(options && options.tab); },
};

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
loadScript('js/v3-state.js');
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

  w.document.getElementById('sidebarDashOutputStyle').click();
  record('collapsed Output Style opens Settings without expanding the sidebar',
    settingsTabs.join(',') === 'styles'
      && !w.document.querySelector('.left-sidebar').classList.contains('expanded'));

  w.document.getElementById('sidebarDashProject').click();
  await flush();
  await flush();
  w.document.getElementById('sidebarDashModel').click();
  record('collapsed Project and Model controls open their direct destinations',
    !!w.document.querySelector('.project-manager-overlay.is-open')
      && settingsTabs.join(',') === 'styles,models'
      && !w.document.querySelector('.left-sidebar').classList.contains('expanded'));
  w.document.querySelector('.project-manager-close').click();
  await flush();

  var listBeforeExpansion = sidebarListRequests;
  var intervalsBeforeExpansion = intervalCalls;
  record('collapsed sidebar has no polling interval', intervalsBeforeExpansion === 0,
    'intervals=' + intervalsBeforeExpansion);
  w.OraSidebar.setExpanded(true);
  await flush();
  await flush();
  record('expanding refreshes once and starts polling',
    sidebarListRequests === listBeforeExpansion + 1
      && intervalCalls === intervalsBeforeExpansion + 1,
    'refreshes=' + (sidebarListRequests - listBeforeExpansion)
      + ', intervals=' + (intervalCalls - intervalsBeforeExpansion));
  var rowBeforeUnchangedPoll = w.document.querySelector(
    '[data-group="active"] .sidebar-row[data-conversation-id="sidebar-stable"]'
  );
  w.OraSidebar.setExpanded(false);
  record('collapsing stops sidebar polling', intervalClears === 1,
    'clears=' + intervalClears);

  var listBeforeRestore = sidebarListRequests;
  var intervalsBeforeRestore = intervalCalls;
  w.OraState.apply({ sidebarExpanded: true });
  await flush();
  await flush();
  record('restored expansion keeps polling without rebuilding unchanged rows',
    sidebarListRequests === listBeforeRestore + 1
      && intervalCalls === intervalsBeforeRestore + 1
      && w.document.querySelector(
        '[data-group="active"] .sidebar-row[data-conversation-id="sidebar-stable"]'
      ) === rowBeforeUnchangedPoll,
    'refreshes=' + (sidebarListRequests - listBeforeRestore)
      + ', intervals=' + (intervalCalls - intervalsBeforeRestore));
  w.OraSidebar.setExpanded(false);

  record('Fork starts disabled', fork.disabled === true);

  await w.OraConversation.load('named-live');
  await flush();
  record('stored display_name wins over first user text',
    title.textContent === 'Saved Dialogue Name', title.textContent);
  record('live Dialogue keeps rename affordance',
    title.classList.contains('is-clickable')
      && title.title === 'Saved Dialogue Name\n(click to rename)');
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
    !title.classList.contains('is-clickable') && title.title === 'Atomic Claim Title');
  title.click();
  record('clicking engram title does not create rename input',
    title.querySelector('input') === null);
  record('read-only engram keeps Fork disabled', fork.disabled === true);

  w.OraConversation.startFresh({ conversation_id: 'fresh-live' });
  record('fresh zero-turn Dialogue disables Fork', fork.disabled === true);
  w.OraConversation.appendUser('First prompt');
  record('first turn enables Fork', fork.disabled === false);

  var initialBrowseButton = w.document.querySelector('.sidebar-browse-cmd');
  initialBrowseButton.focus();
  initialBrowseButton.click();
  await flush();
  await flush();
  record('Library fetched rows', browserRequests > 0, 'requests=' + browserRequests);
  record('Library row renders title',
    !!w.document.querySelector('.conversation-browser-row .conversation-browser-title'));
  record('Library row omits snippet element',
    w.document.querySelector('.conversation-browser-snippet') === null);
  record('Library status renders authoritative server totals and source counts',
    w.document.querySelector('.conversation-browser-status').textContent
      .indexOf('4 shown of 15 results (10 live, 3 archived, 2 engrams)') !== -1,
    w.document.querySelector('.conversation-browser-status').textContent);

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
  var tagsInput = w.document.querySelector('.conversation-browser-tags-input');
  var archivedToggle = w.document.querySelector('.conversation-browser-filter-archived');
  var projectFilter = w.document.querySelector('.conversation-browser-project');
  var dateFrom = w.document.querySelector('.conversation-browser-date-from');
  var dateTo = w.document.querySelector('.conversation-browser-date-to');
  var privacyFilter = w.document.querySelector('.conversation-browser-privacy');
  var lifecycleFilter = w.document.querySelector('.conversation-browser-lifecycle');
  var relationshipFilter = w.document.querySelector('.conversation-browser-relationship');
  var localRestrictionFilter = w.document.querySelector('.conversation-browser-local-restriction');
  record('Library tag filter communicates ALL-selected narrowing',
    tagsInput.getAttribute('aria-label') === 'Filter by tags (all selected tags must match)');
  record('Library archived toggle is labelled and opt-in',
    archivedToggle.checked === false &&
    archivedToggle.closest('label').textContent.indexOf('Show archived') !== -1);
  record('Library exposes server-backed browse controls including Commons',
    Array.from(projectFilter.options).some(function (option) { return option.value === 'commons'; })
      && dateFrom.getAttribute('aria-label') === 'Filter from date (inclusive)'
      && dateTo.getAttribute('aria-label') === 'Filter through date (inclusive)'
      && privacyFilter && lifecycleFilter && relationshipFilter && localRestrictionFilter);
  record('Library renders authoritative facet counts and unavailable metadata',
    privacyFilter.options[1].textContent === 'Standard (12)'
      && localRestrictionFilter.dataset.available === 'false'
      && localRestrictionFilter.title === 'Metadata unavailable');
  var initialBrowserParams = new w.URL(browserRequestUrls[browserRequestUrls.length - 1], w.location.href).searchParams;
  record('Library defaults to hiding archived engrams',
    initialBrowserParams.get('show_archived') === '0'
      && !initialBrowserParams.has('tags')
      && initialBrowserParams.get('project_id') === 'commons');

  projectFilter.value = 'project-a';
  dateFrom.value = '2026-08-01';
  dateTo.value = '2026-08-31';
  privacyFilter.value = 'contains_private';
  lifecycleFilter.value = 'inactive';
  relationshipFilter.value = 'direct-child';
  localRestrictionFilter.value = 'unrestricted';
  relationshipFilter.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush();
  await flush();
  var filteredParams = new w.URL(
    browserRequestUrls[browserRequestUrls.length - 1], w.location.href).searchParams;
  record('Library sends project, inclusive dates, privacy, lifecycle, relationship, and local filters',
    filteredParams.get('project_id') === 'project-a'
      && filteredParams.get('date_from') === '2026-08-01'
      && filteredParams.get('date_to') === '2026-08-31'
      && filteredParams.get('privacy') === 'contains_private'
      && filteredParams.get('lifecycle') === 'inactive'
      && filteredParams.get('relationship') === 'direct-child'
      && filteredParams.get('local_restriction') === 'unrestricted');

  tagsInput.value = ' Atomic, framework/instruction, atomic ';
  tagsInput.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush();
  await flush();
  var taggedBrowserParams = new w.URL(browserRequestUrls[browserRequestUrls.length - 1], w.location.href).searchParams;
  record('Library sends normalized unique tags to browser search',
    taggedBrowserParams.get('tags') === 'atomic,framework/instruction');

  archivedToggle.checked = true;
  archivedToggle.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush();
  await flush();
  var archivedBrowserParams = new w.URL(browserRequestUrls[browserRequestUrls.length - 1], w.location.href).searchParams;
  record('Library show-archived toggle updates browser search',
    archivedBrowserParams.get('show_archived') === '1');

  related.click();
  await flush();
  var relatedParams = new w.URL(relatedRequestUrls[relatedRequestUrls.length - 1], w.location.href).searchParams;
  record('Library forwards tags and archived visibility to related lookup',
    relatedParams.get('tags') === 'atomic,framework/instruction' &&
    relatedParams.get('show_archived') === '1');
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

  // Related results above intentionally narrow to one row. Return to the
  // complete Library result set before exercising bulk selection.
  w.document.querySelector('.conversation-browser-search-btn').click();
  await flush();
  await flush();
  var currentRows = Array.from(w.document.querySelectorAll('.conversation-browser-row'));
  var firstCheck = currentRows[0].querySelector('.conversation-browser-check');
  var secondCheck = currentRows[1].querySelector('.conversation-browser-check');
  var thirdCheck = currentRows[2].querySelector('.conversation-browser-check');
  var engramCheck = currentRows[3].querySelector('.conversation-browser-check');
  firstCheck.checked = true;
  firstCheck.dispatchEvent(new w.Event('change', { bubbles: true }));
  secondCheck.checked = true;
  secondCheck.dispatchEvent(new w.Event('change', { bubbles: true }));
  w.document.querySelector('.conversation-browser-search-btn').click();
  await flush();
  await flush();
  currentRows = Array.from(w.document.querySelectorAll('.conversation-browser-row'));
  record('Library keeps live Dialogue selection through rerender',
    currentRows[0].querySelector('.conversation-browser-check').checked === true
      && currentRows[1].querySelector('.conversation-browser-check').checked === true);
  record('Library prevents non-live project association',
    engramCheck.disabled === true);

  var bulkProject = w.document.querySelector('.conversation-browser-bulk-project');
  var bulkAdd = w.document.querySelector('.conversation-browser-bulk-add');
  record('Library bulk target excludes Commons',
    Array.from(bulkProject.options).every(function (option) { return option.value !== 'commons'; })
      && Array.from(bulkProject.options).some(function (option) { return option.value === 'project-a'; }));
  bulkProject.value = 'project-a';
  bulkProject.dispatchEvent(new w.Event('change', { bubbles: true }));
  envelopes['named-live'].project_ids = ['existing-project', 'late-project'];
  bulkAdd.click();
  await flush();
  await flush();
  var namedWrite = projectWrites.find(function (write) { return write.id === 'named-live'; });
  record('Library atomically adds without replacing post-search memberships',
    !!namedWrite
      && namedWrite.body.add_project_id === 'project-a'
      && !Object.prototype.hasOwnProperty.call(namedWrite.body, 'project_ids')
      && envelopes['named-live'].project_ids.join(',') === 'existing-project,late-project,project-a'
      && projectWrites.some(function (write) {
        return write.id === 'second-live'
          && write.body.add_project_id === 'project-a'
          && !Object.prototype.hasOwnProperty.call(write.body, 'project_ids');
      }));
  record('Library clears successful selections',
    w.document.querySelectorAll('.conversation-browser-check:checked').length === 0);

  currentRows = Array.from(w.document.querySelectorAll('.conversation-browser-row'));
  secondCheck = currentRows[1].querySelector('.conversation-browser-check');
  thirdCheck = currentRows[2].querySelector('.conversation-browser-check');
  secondCheck.checked = true;
  secondCheck.dispatchEvent(new w.Event('change', { bubbles: true }));
  thirdCheck.checked = true;
  thirdCheck.dispatchEvent(new w.Event('change', { bubbles: true }));
  bulkFailIds.add('third-live');
  bulkAdd.click();
  await flush();
  await flush();
  currentRows = Array.from(w.document.querySelectorAll('.conversation-browser-row'));
  record('Library reports partial failure and retains only failed selections',
    currentRows[1].querySelector('.conversation-browser-check').checked === false
      && currentRows[2].querySelector('.conversation-browser-check').checked === true
      && w.document.querySelector('.conversation-browser-status').textContent.indexOf('1 failed') !== -1);

  var requestsBeforeTitleOpen = envelopeRequests;
  var listRequestsBeforeTitleOpen = sidebarListRequests;
  titleButton.click();
  await flush();
  record('Library title control opens its row',
    envelopeRequests > requestsBeforeTitleOpen,
    'requests=' + envelopeRequests);
  record('opening a Library row does not rebuild the full sidebar list',
    sidebarListRequests === listRequestsBeforeTitleOpen,
    'sidebar requests=' + sidebarListRequests);

  var older = deferredResponse();
  var newer = deferredResponse();
  queuedBrowserResponses.push(older, newer);
  search.value = 'older';
  w.document.querySelector('.conversation-browser-search-btn').click();
  search.value = 'newer';
  w.document.querySelector('.conversation-browser-search-btn').click();
  record('newer Library request aborts the older request',
    !!(older.options && older.options.signal && older.options.signal.aborted));
  newer.resolve({
    query: 'newer',
    rows: [{ conversation_id: 'newer-row', source_kind: 'live', title: 'Newer Row' }],
    total: 7,
    source_counts: { live: 7, archive: 0, engram: 0 },
    facets: {
      privacy: { available: true, counts: {
        standard: 6, contains_private: 1, stealth: 0,
      } },
      local_restriction: { available: false, counts: {
        restricted: 0, unrestricted: 0,
      } },
    },
  });
  await flush();
  await flush();
  older.resolve({
    query: 'older',
    rows: [{ conversation_id: 'older-row', source_kind: 'live', title: 'Older Row' }],
    total: 99,
    source_counts: { live: 99, archive: 0, engram: 0 },
    facets: { privacy: { available: true, counts: {
      standard: 88, contains_private: 11, stealth: 0,
    } } },
  });
  await flush();
  await flush();
  record('late older Library response cannot overwrite newer rows, status, or facets',
    w.document.querySelector('.conversation-browser-title').textContent === 'Newer Row'
      && w.document.querySelector('.conversation-browser-status').textContent
        .indexOf('1 shown of 7 results (7 live)') !== -1
      && privacyFilter.options[1].textContent === 'Standard (6)',
    w.document.querySelector('.conversation-browser-status').textContent);

  var browseButton = initialBrowseButton;
  var escapeTargets = [
    ['search', '.conversation-browser-search'],
    ['sort', '.conversation-browser-sort'],
    ['Search button', '.conversation-browser-search-btn'],
    ['Close button', '.conversation-browser-close'],
    ['Dialogue filter', '.conversation-browser-filter-conversations'],
    ['Engram filter', '.conversation-browser-filter-engrams'],
    ['project filter', '.conversation-browser-project'],
    ['from-date filter', '.conversation-browser-date-from'],
    ['through-date filter', '.conversation-browser-date-to'],
    ['privacy filter', '.conversation-browser-privacy'],
    ['lifecycle filter', '.conversation-browser-lifecycle'],
    ['relationship filter', '.conversation-browser-relationship'],
    ['local restriction filter', '.conversation-browser-local-restriction'],
    ['tag filter', '.conversation-browser-tags-input'],
    ['show archived filter', '.conversation-browser-filter-archived'],
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
      var activeFocus = w.document.activeElement;
      escapeFailures.push(escapeTargets[i][0] + ': focus was not restored ('
        + (activeFocus && (activeFocus.id || activeFocus.className || activeFocus.tagName)) + ')');
    }
  }
  record('Escape closes Library from every control and restores focus',
    escapeFailures.length === 0, escapeFailures.join('; '));

  function describeFocus(el) {
    if (!el) return 'null';
    return el.id || el.className || el.tagName;
  }

  browseButton.focus();
  browseButton.click();
  await flush();
  var workspaceInput = w.document.querySelector('.input-pane textarea');
  workspaceInput.focus();
  workspaceInput.dispatchEvent(new w.KeyboardEvent('keydown', {
    key: 'Escape', bubbles: true, cancelable: true,
  }));
  record('Escape closes non-modal Library when focus is elsewhere',
    !library.classList.contains('is-open'));
  // The Library is docked, not modal — the user can go on working while it is
  // up. Closing it must not pull the caret out of whatever they moved to.
  record('closing the docked Library leaves focus where the user moved it',
    w.document.activeElement === workspaceInput,
    'activeElement=' + describeFocus(w.document.activeElement));

  browseButton.focus();
  browseButton.click();
  await flush();
  w.document.querySelector('.conversation-browser-search').focus();
  w.document.querySelector('.conversation-browser-close').click();
  record('closing the Library while it still holds focus returns focus to the opener',
    !library.classList.contains('is-open') && w.document.activeElement === browseButton,
    'activeElement=' + describeFocus(w.document.activeElement));

  browseButton.focus();
  browseButton.click();
  await flush();
  w.document.querySelector('.conversation-browser-search').blur();
  w.document.querySelector('.conversation-browser-close').click();
  record('closing the Library when nobody holds focus returns focus to the opener',
    !library.classList.contains('is-open') && w.document.activeElement === browseButton,
    'activeElement=' + describeFocus(w.document.activeElement));

  // Counted from the registrations the module actually makes, not from any
  // flag it sets: the browser collapses an identical (type, listener, capture)
  // triple, so the live DOM listener count reads 1 whether or not the module
  // removes before adding.
  var realAdd = w.addEventListener;
  var realRemove = w.removeEventListener;
  var liveResize = [];
  w.addEventListener = function (type, fn, opts) {
    if (type === 'resize') liveResize.push(fn);
    return realAdd.call(w, type, fn, opts);
  };
  w.removeEventListener = function (type, fn, opts) {
    if (type === 'resize') {
      var at = liveResize.indexOf(fn);
      if (at !== -1) liveResize.splice(at, 1);
    }
    return realRemove.call(w, type, fn, opts);
  };
  for (var openPass = 0; openPass < 3; openPass += 1) {
    browseButton.click();
    await flush();
  }
  var resizeAfterOpens = liveResize.length;
  w.document.querySelector('.conversation-browser-close').click();
  var resizeAfterClose = liveResize.length;
  w.addEventListener = realAdd;
  w.removeEventListener = realRemove;
  record('repeat Library opens keep exactly one live resize listener, and close drops it',
    resizeAfterOpens === 1 && resizeAfterClose === 0,
    'after 3 opens=' + resizeAfterOpens + ', after close=' + resizeAfterClose);

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
