#!/usr/bin/env node
/* Focused jsdom coverage for the Knowledge Library workspace and the remaining
 * independent UI quick fixes that share its Sidebar/Dialogue seams.
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

var indexSource = fs.readFileSync(path.resolve(__dirname, '..', '..', 'index-v3.html'), 'utf8');
var libraryMountMatch = indexSource.match(
  /<section id="libraryWorkspace"[\s\S]*?<\/section>\s*\n\s*<\/div>\s*\n\s*<script>/
);
if (!libraryMountMatch) {
  console.error('error: stable Knowledge Library mount is missing from index-v3.html');
  process.exit(2);
}
var libraryMountMarkup = libraryMountMatch[0]
  .replace(/\s*<\/div>\s*\n\s*<script>[\s\S]*$/, '');

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body>' +
  '<div class="left-sidebar">' +
  '  <div class="sidebar-collapsed-dashboard">' +
  '    <button id="sidebarDashExpand" aria-label="Expand Dialogues sidebar">Expand</button>' +
  '    <button id="sidebarDashProject">Projects</button>' +
  '    <button id="sidebarDashModel">Model</button>' +
  '    <button id="sidebarDashOutputStyle">Output Style</button>' +
  '  </div>' +
  '  <button class="sidebar-fork-thread-cmd" disabled>Fork</button>' +
  '  <button class="sidebar-browse-cmd">Library</button>' +
  '  <div data-group="pinned"><div class="sidebar-group-rows"></div></div>' +
  '  <div data-group="errored"><div class="sidebar-group-rows"></div></div>' +
  '  <div data-group="unread"><div class="sidebar-group-rows"></div></div>' +
  '  <div data-group="active"><div class="sidebar-group-rows"></div></div>' +
  '  <div data-group="pending"><div class="sidebar-group-rows"></div></div>' +
  '</div>' +
  '<div class="ora-shell"></div>' +
  '<div class="output-pane">' +
  '  <div class="output-pane-header"></div>' +
  '  <span id="outputPaneDisplayName" class="output-pane-display-name">Dialogue</span>' +
  '  <span id="outputPaneModeIcon"></span>' +
  '  <button id="outputPaneNavBack"></button>' +
  '  <button id="outputPaneNavForward"></button>' +
  '  <span id="outputPaneTurnPosition"></span>' +
  '  <span id="outputPaneTimestamp"></span>' +
  '  <div class="output-content"><p id="preservedFinding">Preserved finding</p></div>' +
  '</div>' +
  '<div class="input-pane"><textarea></textarea></div>' +
  '<div id="bridgeStrip"><div class="bridge-toolbar"></div></div>' +
  '<div id="chatZone"><div class="chat-input-pane"><textarea></textarea></div></div>' +
  '<div id="bridgeStripRight"><div class="bridge-toolbar"></div></div>' +
  '<section class="visual-pane-shell"><div class="visual-pane-header"></div>' +
  '  <div class="right-pane"><span id="preservedExhibit">Preserved exhibit</span></div>' +
  '  <div class="visual-pane-footer"></div>' +
  '</section>' +
  '<svg class="spine-wordmark"><g id="logo-o" role="button" tabindex="0" aria-label="Submit">' +
  '  <text class="library-o-type"></text><text class="library-o-state"></text>' +
  '</g><g id="logo-r" aria-hidden="true"></g>' +
  '<g id="logo-a" role="button" tabindex="0" aria-label="Open Dialogues sidebar"></g></svg>' +
  libraryMountMarkup +
  '</body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
);

var w = dom.window;
var libraryCssSource = fs.readFileSync(path.resolve(
  __dirname, '..', 'styles', 'components', 'library-workspace.css'
), 'utf8');
var libraryStyle = w.document.createElement('style');
libraryStyle.textContent = libraryCssSource;
w.document.head.appendChild(libraryStyle);
var measuredWidth = 1024;
var unequalBridgeGeometry = true;
function measuredRect(left, top, width, height) {
  return {
    left: left, top: top, width: width, height: height,
    right: left + width, bottom: top + height,
    x: left, y: top, toJSON: function () { return this; },
  };
}
function rectsIntersect(a, b) {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
}
function sameRect(a, b) {
  return a.left === b.left && a.top === b.top
    && a.width === b.width && a.height === b.height;
}
w.HTMLElement.prototype.getBoundingClientRect = function () {
  if (this.classList && this.classList.contains('library-bridge-bank')) {
    var bankSide = this.classList.contains('library-bridge-bank--left') ? 'left' : 'right';
    var bankMount = w.document.getElementById('libraryWorkspace');
    return measuredRect(
      80 + (parseFloat(bankMount.style.getPropertyValue('--library-' + bankSide + '-bank-left')) || 0),
      16 + (parseFloat(bankMount.style.getPropertyValue('--library-' + bankSide + '-bank-top')) || 0),
      parseFloat(bankMount.style.getPropertyValue('--library-' + bankSide + '-bank-width')) || 0,
      parseFloat(bankMount.style.getPropertyValue('--library-' + bankSide + '-bank-height')) || 0
    );
  }
  if (this.tagName === 'BUTTON' && this.parentElement
      && this.parentElement.classList.contains('library-bridge-bank')) {
    var parentRect = this.parentElement.getBoundingClientRect();
    var siblings = Array.from(this.parentElement.children).filter(function (child) {
      return child.tagName === 'BUTTON';
    });
    var buttonIndex = siblings.indexOf(this);
    var isLeftBank = this.parentElement.classList.contains('library-bridge-bank--left');
    var buttonWidth = isLeftBank ? 64 : (measuredWidth === 702 ? 72 : 48);
    var buttonGap = 5;
    var buttonRun = siblings.length * buttonWidth + Math.max(0, siblings.length - 1) * buttonGap;
    var buttonLeft = isLeftBank || w.getComputedStyle(this.parentElement).justifyContent === 'flex-start'
      ? parentRect.left + 6 + buttonIndex * (buttonWidth + buttonGap)
      : parentRect.right - 6 - buttonRun + buttonIndex * (buttonWidth + buttonGap);
    return measuredRect(buttonLeft, parentRect.top + Math.max(0, (parentRect.height - 28) / 2), buttonWidth, 28);
  }
  if (this.classList && this.classList.contains('library-visual-map')) {
    return measuredRect(80, 90, measuredWidth, 188);
  }
  if (this.classList && this.classList.contains('library-visual-node')) {
    return measuredRect(
      80 + (parseFloat(this.style.left) || 0),
      90 + (parseFloat(this.style.top) || 0),
      this.classList.contains('library-visual-node--related') ? 112 : 124,
      50
    );
  }
  return measuredRect(0, 0, 0, 0);
};
function installMeasuredGeometry() {
  var left = 80;
  var spine = 56;
  var column = (measuredWidth - spine) / 2;
  var library = w.document.getElementById('libraryWorkspace');
  function leftUpperHeight() { return unequalBridgeGeometry ? 137 : 260; }
  function rightUpperHeight() { return unequalBridgeGeometry ? 40 : 260; }
  function rightBridgeHeight() { return unequalBridgeGeometry ? 40 : 48; }
  w.document.querySelector('.input-pane').getBoundingClientRect = function () {
    return measuredRect(left, 16, column, leftUpperHeight());
  };
  w.document.getElementById('bridgeStrip').getBoundingClientRect = function () {
    return measuredRect(left, 16 + leftUpperHeight(), column, 48);
  };
  w.document.getElementById('chatZone').getBoundingClientRect = function () {
    return measuredRect(left + column + spine, 16, column, rightUpperHeight());
  };
  w.document.getElementById('bridgeStripRight').getBoundingClientRect = function () {
    return measuredRect(
      left + column + spine,
      unequalBridgeGeometry ? 16 : 16 + rightUpperHeight(),
      column,
      rightBridgeHeight()
    );
  };
  w.document.getElementById('logo-o').getBoundingClientRect = function () {
    return measuredRect(left + column + 7, 16 + leftUpperHeight() - 21, 42, 42);
  };
  w.document.getElementById('libraryWorkspace').getBoundingClientRect = function () {
    var leftBottom = 16 + leftUpperHeight() + 48;
    var rightBottom = (unequalBridgeGeometry ? 16 : 16 + rightUpperHeight())
      + rightBridgeHeight();
    return measuredRect(left, 16, measuredWidth, Math.max(leftBottom, rightBottom) - 16);
  };
  w.document.getElementById('libraryWorkspaceResults').getBoundingClientRect = function () {
    var mountRect = w.document.getElementById('libraryWorkspace').getBoundingClientRect();
    return measuredRect(left, 90, measuredWidth, Math.max(1, mountRect.bottom - 90 - 48));
  };
  w.document.getElementById('librarySearchInput').getBoundingClientRect = function () {
    var searchLeft = parseFloat(library.style.getPropertyValue('--library-search-left')) || 0;
    var searchRight = parseFloat(library.style.getPropertyValue('--library-search-right')) || 0;
    return measuredRect(
      left + 12 + searchLeft,
      42,
      Math.max(1, measuredWidth - 24 - searchLeft - searchRight),
      38
    );
  };
}
installMeasuredGeometry();
var forkRequests = 0;
var forkRequestBodies = [];
var browserRequests = 0;
var browserRequestUrls = [];
var relatedRequestUrls = [];
var queuedRelatedResponses = [];
var queuedBrowserResponses = [];
var libraryRequestUrls = [];
var queuedLibraryResponses = [];
var queuedPreviewResponses = [];
var queuedEditResponses = [];
var editRequests = [];
var sidebarListRequests = 0;
var queuedSidebarListResponses = [];
var sidebarListInFlight = 0;
var sidebarListMaxInFlight = 0;
var envelopeRequests = 0;
var projectWrites = [];
var bulkFailIds = new Set();
var activeProject = 'commons';
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

function libraryRow(id, source, title, options) {
  options = options || {};
  return {
    id: id,
    source: source,
    title: title,
    metadata: Object.assign({
      project_ids: ['ora'],
      tags: ['library'],
      lifecycle: 'active',
      privacy: 'standard',
      modified_at: '2026-09-01T12:00:00Z',
      content_type: 'text/markdown',
      item_type: source === 'dialogues' ? 'Dialogue' : 'note',
    }, options.metadata || {}),
    unavailable_fields: options.unavailable_fields || [],
    provenance: { available: true, kind: source, identity: id, reason: null },
    relationships: options.relationships || {
      state: 'fresh',
      updated_at: '2026-08-31T10:00:00Z',
      reason: null,
      summaries: [{ type: 'supports', direction: 'outgoing', count: 1, confidence: 'recorded' }],
    },
    preview: options.preview || {
      kind: 'text', route: 'text-pane', available: true, reason: null,
      locator: source === 'dialogues' ? { dialogue_id: id.replace(/^dialogues:/, '') } : {},
    },
    editability: { available: true, editable: true, descriptor_only: true, reason: null },
  };
}

function libraryPayload(rows, options) {
  options = options || {};
  var total = options.total === undefined ? rows.length : options.total;
  var complete = options.complete !== false;
  return {
    sources: options.sources || ['dialogues', 'engrams', 'files'],
    rows: rows,
    total: total,
    source_counts: options.source_counts || { dialogues: total, engrams: 0, files: 0 },
    facets: {
      projects: { counts: { ora: total }, unavailable: 0, complete: complete },
      item_type: {
        counts: options.item_type_counts || { Dialogue: total },
        unavailable: 0,
        complete: complete,
      },
      content_type: { counts: { 'text/markdown': total }, unavailable: 0, complete: complete },
    },
    universe: {
      complete: complete,
      providers: {},
      unavailable_sources: complete ? [] : [{ source: 'files', reason: 'file inventory unavailable' }],
    },
    pagination: {
      offset: options.offset || 0,
      limit: 100,
      returned: rows.length,
      has_more: Boolean(options.has_more),
      next_offset: options.has_more ? (options.next_offset || rows.length) : null,
    },
  };
}

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
    resolve: function (payload, status, headerValues) {
      resolve(responseObject(true, payload, status || 200, headerValues));
    },
    resolveError: function (payload, status) {
      resolve(responseObject(false, payload, status || 500));
    },
  };
  return item;
}

w.fetch = function (url, opts) {
  var decoded = decodeURIComponent(String(url));
  if (decoded.indexOf('/api/library/edit') === 0) {
    editRequests.push({
      url: decoded,
      method: (opts && opts.method) || 'GET',
      body: opts && opts.body ? JSON.parse(opts.body) : null,
    });
    var queuedEdit = queuedEditResponses.shift() || {};
    if (queuedEdit.promise) {
      queuedEdit.options = opts || {};
      return queuedEdit.promise;
    }
    if (queuedEdit.ok === false) {
      return response(false, queuedEdit.payload, queuedEdit.status);
    }
    return response(true, queuedEdit.payload || queuedEdit, queuedEdit.status);
  }
  if (decoded.indexOf('/api/library/preview?') === 0) {
    if (queuedPreviewResponses.length) {
      var queuedPreview = queuedPreviewResponses.shift();
      if (queuedPreview && queuedPreview.promise) {
        queuedPreview.options = opts || {};
        return queuedPreview.promise;
      }
      if (queuedPreview && queuedPreview.ok === false) {
        return response(false, queuedPreview.payload, queuedPreview.status);
      }
      return response(true, queuedPreview);
    }
    var previewId = new w.URL(decoded, w.location.href).searchParams.get('id');
    return response(true, {
      id: previewId,
      source: String(previewId || '').indexOf('files:') === 0 ? 'files' : 'engrams',
      text: 'Current body for ' + previewId,
    });
  }
  if (decoded.indexOf('/api/library/browser?') === 0) {
    libraryRequestUrls.push(decoded);
    if (queuedLibraryResponses.length) {
      var queuedLibrary = queuedLibraryResponses.shift();
      if (queuedLibrary && queuedLibrary.promise) {
        queuedLibrary.options = opts || {};
        return queuedLibrary.promise;
      }
      return response(true, queuedLibrary);
    }
    return response(true, libraryPayload([
      libraryRow('dialogues:named-live', 'dialogues', 'Saved Dialogue Name'),
      libraryRow('engrams:claim', 'engrams', 'Atomic Claim Title'),
    ], { sources: ['dialogues', 'engrams'], source_counts: {
      dialogues: 1, engrams: 1, files: 0,
    } }));
  }
  if (decoded.indexOf('/api/conversations/browser?') === 0) {
    browserRequests += 1;
    browserRequestUrls.push(decoded);
    if (queuedBrowserResponses.length) {
      var queued = queuedBrowserResponses.shift();
      queued.options = opts || {};
      return queued.promise;
    }
    var browserPayload = {
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
    };
    if (new w.URL(decoded, w.location.href).searchParams.get('purpose') === 'creation') {
      browserPayload.review_token = 'library-context-review-token';
    }
    return response(true, browserPayload);
  }
  if (decoded === '/api/projects/meta?status=active') {
    return response(true, {
      projects: [
        { nexus: 'commons', name: 'Commons' },
        { nexus: 'project-a', name: 'Project A' },
      ],
    });
  }
  if (decoded === '/api/active-project') {
    if (opts && opts.method === 'POST') {
      activeProject = JSON.parse(opts.body || '{}').nexus || 'commons';
    }
    return response(true, {
      ok: true,
      nexus: activeProject,
      canonical_nexus: activeProject,
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
    if (queuedRelatedResponses.length) {
      var queuedRelated = queuedRelatedResponses.shift();
      if (queuedRelated && queuedRelated.promise) {
        queuedRelated.options = opts || {};
        return queuedRelated.promise;
      }
      return response(true, queuedRelated);
    }
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
    sidebarListInFlight += 1;
    sidebarListMaxInFlight = Math.max(
      sidebarListMaxInFlight, sidebarListInFlight,
    );
    var sidebarResponse;
    if (queuedSidebarListResponses.length) {
      var queuedSidebarList = queuedSidebarListResponses.shift();
      queuedSidebarList.options = opts || {};
      sidebarResponse = queuedSidebarList.promise;
    } else if (opts && opts.headers && opts.headers['If-None-Match'] === '"sidebar-v1"') {
      sidebarResponse = response(false, {}, 304);
    } else {
      sidebarResponse = response(true, {
        pinned: [],
        errored: [],
        pending: [],
        unread: [],
        active: [{ conversation_id: 'sidebar-stable', title: 'Stable row', tag: '' }],
      }, 200, { ETag: '"sidebar-v1"' });
    }
    return sidebarResponse.then(function (result) {
      sidebarListInFlight -= 1;
      return result;
    }, function (error) {
      sidebarListInFlight -= 1;
      throw error;
    });
  }
  if (/\/api\/conversation\/[^/]+\/fork$/.test(decoded)) {
    forkRequests += 1;
    forkRequestBodies.push(JSON.parse((opts && opts.body) || '{}'));
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
loadScript('js/library-workspace.js');
w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));

var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? '  - ' + detail : ''));
}
function flush() {
  return new Promise(function (resolve) { w.setTimeout(resolve, 0); });
}

function visualPlacementIsSafe() {
  var map = w.document.querySelector('.library-visual-map');
  if (!map) return false;
  var mapRect = map.getBoundingClientRect();
  var nodes = Array.from(map.querySelectorAll('.library-visual-node:not([hidden])'));
  if (!nodes.length) return false;
  var boxes = nodes.map(function (node) { return node.getBoundingClientRect(); });
  var contained = boxes.every(function (box) {
    return box.left >= mapRect.left
      && box.top >= mapRect.top
      && box.right <= mapRect.right
      && box.bottom <= mapRect.bottom;
  });
  var nonOverlapping = boxes.every(function (box, index) {
    return boxes.slice(index + 1).every(function (other) {
      return box.right <= other.left
        || other.right <= box.left
        || box.bottom <= other.top
        || other.bottom <= box.top;
    });
  });
  return contained && nonOverlapping;
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

  var firstSidebarResponse = deferredResponse();
  var trailingSidebarResponse = deferredResponse();
  queuedSidebarListResponses.push(firstSidebarResponse, trailingSidebarResponse);
  var listBeforeCoalescing = sidebarListRequests;
  sidebarListMaxInFlight = sidebarListInFlight;
  var firstSidebarRefresh = w.OraSidebar.refresh();
  var overlappingSidebarRefresh = w.OraSidebar.refresh();
  var thirdSidebarRefresh = w.OraSidebar.refresh();
  var sharedSidebarCompletions = 0;
  [firstSidebarRefresh, overlappingSidebarRefresh, thirdSidebarRefresh].forEach(
    function (pending) {
      pending.then(function () { sharedSidebarCompletions += 1; });
    }
  );
  await flush();
  record('overlapping sidebar refreshes share one in-flight request',
    firstSidebarRefresh === overlappingSidebarRefresh
      && firstSidebarRefresh === thirdSidebarRefresh
      && sidebarListRequests === listBeforeCoalescing + 1
      && sidebarListInFlight === 1
      && sidebarListMaxInFlight === 1,
    'requests=' + (sidebarListRequests - listBeforeCoalescing)
      + ', in-flight=' + sidebarListInFlight
      + ', max=' + sidebarListMaxInFlight);

  firstSidebarResponse.resolve({
    pinned: [], errored: [], pending: [], unread: [],
    active: [{ conversation_id: 'sidebar-intermediate', title: 'Intermediate row', tag: '' }],
  }, 200, { ETag: '"sidebar-v2"' });
  await flush();
  await flush();
  record('overlap coalesces to exactly one trailing ETag request',
    sidebarListRequests === listBeforeCoalescing + 2
      && sidebarListInFlight === 1
      && sidebarListMaxInFlight === 1
      && sharedSidebarCompletions === 0
      && queuedSidebarListResponses.length === 0
      && firstSidebarResponse.options.headers['If-None-Match'] === '"sidebar-v1"'
      && trailingSidebarResponse.options.headers['If-None-Match'] === '"sidebar-v2"',
    'requests=' + (sidebarListRequests - listBeforeCoalescing)
      + ', completions=' + sharedSidebarCompletions
      + ', max=' + sidebarListMaxInFlight);

  trailingSidebarResponse.resolve({
    pinned: [], errored: [], pending: [], unread: [],
    active: [{ conversation_id: 'sidebar-final', title: 'Final row', tag: '' }],
  }, 200, { ETag: '"sidebar-v3"' });
  await Promise.all([
    firstSidebarRefresh, overlappingSidebarRefresh, thirdSidebarRefresh,
  ]);
  await flush();
  record('shared sidebar refresh completion exposes only the final trailing state',
    sidebarListRequests === listBeforeCoalescing + 2
      && sidebarListInFlight === 0
      && sidebarListMaxInFlight === 1
      && sharedSidebarCompletions === 3
      && !!w.document.querySelector(
        '[data-group="active"] .sidebar-row[data-conversation-id="sidebar-final"]'
      )
      && !w.document.querySelector(
        '[data-group="active"] .sidebar-row[data-conversation-id="sidebar-intermediate"]'
      ),
    'requests=' + (sidebarListRequests - listBeforeCoalescing)
      + ', completions=' + sharedSidebarCompletions
      + ', in-flight=' + sidebarListInFlight);
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

  // Knowledge Library: inventory/paging truth, mixed sources, one shared
  // List/Visual state, native O semantics, and lower-pane preservation.
  var visibleDialogue = libraryRow(
    'dialogues:named-live', 'dialogues', 'Saved Dialogue Name'
  );
  var metadataDialogue = libraryRow(
    'dialogues:metadata-only', 'dialogues', 'Private Dialogue', {
      metadata: { privacy: 'metadata_only' },
      unavailable_fields: ['content_type'],
      preview: {
        kind: 'unsupported', route: 'metadata-only', available: false,
        reason: 'No admitted exchanges are readable.',
      },
      relationships: {
        state: 'stale', reason: 'Relationship snapshot is stale.',
        summaries: [{ type: 'supports', direction: 'outgoing', count: 2, confidence: 'recorded' }],
      },
    }
  );
  var secondDialogue = libraryRow(
    'dialogues:second-live', 'dialogues', 'Second Dialogue'
  );
  var contextEngram = libraryRow(
    'engrams:claim', 'engrams', 'Atomic Claim Title', {
      metadata: { item_type: 'Engram', tags: ['atomic'] },
    }
  );
  var nonAtomicEngram = libraryRow(
    'engrams:reference', 'engrams', 'Reference Engram', {
      metadata: { item_type: 'Engram', tags: ['reference'] },
    }
  );
  var contextFile = libraryRow(
    'files:project-image', 'files', 'Project image.png', {
      metadata: { item_type: 'File', privacy: 'private', content_type: 'image/png' },
      preview: {
        kind: 'visual', route: 'visual-pane', available: true, reason: null,
        locator: {},
      },
    }
  );
  queuedLibraryResponses.push(libraryPayload([visibleDialogue], {
    total: 2, complete: true, has_more: true, next_offset: 1,
  }));

  var preservedFinding = w.document.createElement('p');
  preservedFinding.textContent = 'Preserved finding';
  var preservedExhibit = w.document.createElement('span');
  preservedExhibit.textContent = 'Preserved exhibit';
  w.document.querySelector('.output-content').appendChild(preservedFinding);
  w.document.querySelector('.right-pane').appendChild(preservedExhibit);
  var logoR = w.document.getElementById('logo-r');
  var logoA = w.document.getElementById('logo-a');
  var logoPresentationBefore = {
    rVisibility: w.getComputedStyle(logoR).visibility,
    rPointerEvents: w.getComputedStyle(logoR).pointerEvents,
    aVisibility: w.getComputedStyle(logoA).visibility,
    aPointerEvents: w.getComputedStyle(logoA).pointerEvents,
  };
  var browseButton = w.document.querySelector('.sidebar-browse-cmd');
  browseButton.focus();
  browseButton.click();
  await flush();
  await flush();
  var library = w.document.getElementById('libraryWorkspace');
  var librarySearch = w.document.getElementById('librarySearchInput');
  var initialLibraryParams = new w.URL(
    libraryRequestUrls[libraryRequestUrls.length - 1], w.location.href
  ).searchParams;
  record('Library opens the stable production mount with all independent sources',
    !library.hidden
      && initialLibraryParams.getAll('source').join(',') === 'dialogues,engrams,files'
      && librarySearch.getAttribute('aria-label') === 'Search readable Dialogue and Engram text');
  record('Library takes the upper workspace inert without destroying it',
    w.document.querySelector('.input-pane').hasAttribute('inert')
      && w.document.getElementById('chatZone').hasAttribute('inert')
      && w.document.body.classList.contains('library-workspace-open'));
  record('Library geometry is measured from the live 1024px upper workspace and bridge',
    library.style.width === '1024px'
      && library.style.getPropertyValue('--library-bridge-height') === '48px',
    'width=' + library.style.width);
  var leftBridgeRect = w.document.getElementById('bridgeStrip').getBoundingClientRect();
  var rightBridgeRect = w.document.getElementById('bridgeStripRight').getBoundingClientRect();
  var leftBankRect = w.document.querySelector('.library-bridge-bank--left').getBoundingClientRect();
  var rightBankRect = w.document.querySelector('.library-bridge-bank--right').getBoundingClientRect();
  var liveSearchRect = librarySearch.getBoundingClientRect();
  var nativeORect = w.document.getElementById('logo-o').getBoundingClientRect();
  var bridgeButtons = Array.from(w.document.querySelectorAll('.library-bridge-bank > button'));
  record('unequal control banks align with their own physical bridge rectangles',
    sameRect(leftBankRect, leftBridgeRect)
      && sameRect(rightBankRect, rightBridgeRect)
      && leftBankRect.top !== rightBankRect.top
      && leftBankRect.height !== rightBankRect.height,
    'left=' + JSON.stringify(leftBankRect) + ', right=' + JSON.stringify(rightBankRect));
  record('bridge buttons clear the Library search and native O in the unequal layout',
    bridgeButtons.every(function (button) {
      var buttonRect = button.getBoundingClientRect();
      return !rectsIntersect(buttonRect, liveSearchRect)
        && !rectsIntersect(buttonRect, nativeORect);
    })
      && liveSearchRect.right <= rightBridgeRect.left,
    'search=' + JSON.stringify(liveSearchRect) + ', O=' + JSON.stringify(nativeORect));
  record('Library raises only the native O and suppresses decorative r/a while open',
    w.getComputedStyle(w.document.getElementById('logo-o')).visibility !== 'hidden'
      && w.getComputedStyle(logoR).visibility === 'hidden'
      && w.getComputedStyle(logoR).pointerEvents === 'none'
      && w.getComputedStyle(logoA).visibility === 'hidden'
      && w.getComputedStyle(logoA).pointerEvents === 'none');

  unequalBridgeGeometry = false;
  w.dispatchEvent(new w.Event('resize'));
  var equalLeftBankRect = w.document.querySelector('.library-bridge-bank--left').getBoundingClientRect();
  var equalRightBankRect = w.document.querySelector('.library-bridge-bank--right').getBoundingClientRect();
  record('equal-height bridge geometry remains aligned without reserving search width',
    equalLeftBankRect.top === equalRightBankRect.top
      && equalLeftBankRect.height === equalRightBankRect.height
      && library.style.getPropertyValue('--library-search-left') === '0px'
      && library.style.getPropertyValue('--library-search-right') === '0px');
  unequalBridgeGeometry = true;
  w.dispatchEvent(new w.Event('resize'));
  record('server total and pagination remain authoritative',
    w.OraLibraryWorkspace.getState().loaded === 1
      && w.OraLibraryWorkspace.getState().total === 2
      && w.OraLibraryWorkspace.getState().pagination.has_more === true);

  var partialGroupSelect = w.document.querySelector('[data-library-group]');
  partialGroupSelect.value = 'source';
  partialGroupSelect.dispatchEvent(new w.Event('change', { bubbles: true }));
  var partialListIsUngrouped = w.document.querySelectorAll('.library-result-group').length === 0
    && w.document.getElementById('libraryWorkspaceNotice').textContent
      .indexOf('grouping') !== -1;
  w.document.querySelector('[data-library-view="visual"]').click();
  var partialVisualIsUngrouped = w.document.querySelector('.library-visual-group-state').textContent
    .indexOf('unavailable until every') !== -1
    && w.document.querySelectorAll('.library-visual-node__group').length === 0;
  w.document.querySelector('[data-library-view="list"]').click();
  record('partial inventory keeps shared grouping visibly unavailable in List and Visual',
    partialListIsUngrouped && partialVisualIsUngrouped);

  var supersededLoadAll = deferredResponse();
  queuedLibraryResponses.push(supersededLoadAll);
  w.document.querySelector('[data-library-command="load-all"]').click();
  await flush();

  queuedLibraryResponses.push(libraryPayload([visibleDialogue], {
    total: 1, complete: false,
    source_counts: { dialogues: 1, engrams: 0, files: 0 },
  }));
  librarySearch.value = 'hidden body term';
  librarySearch.dispatchEvent(new w.Event('input', { bubbles: true }));
  await flush();
  await flush();
  var queryParams = new w.URL(
    libraryRequestUrls[libraryRequestUrls.length - 1], w.location.href
  ).searchParams;
  record('keyword search is server-side over readable Dialogue and indexed Engram text',
    queryParams.get('q') === 'hidden body term'
      && w.document.querySelector('.library-list-row__pin').textContent.indexOf('Saved Dialogue Name') !== -1
      && w.OraLibraryWorkspace.getState().total === 1
      && w.OraLibraryWorkspace.getState().loadingAll === false
      && supersededLoadAll.options.signal.aborted
      && w.document.getElementById('libraryWorkspaceNotice').textContent
        .indexOf('file inventory unavailable') !== -1);
  supersededLoadAll.resolve(libraryPayload([metadataDialogue], {
    total: 2, complete: true, offset: 1,
  }));
  await flush();
  await flush();
  record('replacement query supersedes generation-owned Load all and ignores its late page',
    w.OraLibraryWorkspace.getState().query === 'hidden body term'
      && w.OraLibraryWorkspace.getState().loaded === 1
      && !w.document.querySelector('[data-library-row-id="dialogues:metadata-only"]'));

  var failedReplacement = deferredResponse();
  queuedLibraryResponses.push(failedReplacement);
  var failedReplacementPromise = w.OraLibraryWorkspace.refresh();
  failedReplacement.resolveError({ error: 'replacement failed' }, 503);
  await failedReplacementPromise;
  await flush();
  var failedReplacementParams = new w.URL(
    libraryRequestUrls[libraryRequestUrls.length - 1], w.location.href
  ).searchParams;
  record('failed replacement keeps old rows and exposes replacement retry',
    failedReplacementParams.get('offset') === '0'
      && w.document.querySelector('[data-library-row-id="dialogues:named-live"]')
      && !!w.document.querySelector('[data-library-command="retry"]'));
  queuedLibraryResponses.push(libraryPayload([visibleDialogue], {
    total: 1, complete: false,
    source_counts: { dialogues: 1, engrams: 0, files: 0 },
  }));
  w.document.querySelector('[data-library-command="retry"]').click();
  await flush();
  await flush();
  var replacementRetryParams = new w.URL(
    libraryRequestUrls[libraryRequestUrls.length - 1], w.location.href
  ).searchParams;
  record('replacement retry restarts at offset zero without appending stale rows',
    replacementRetryParams.get('offset') === '0'
      && w.OraLibraryWorkspace.getState().loaded === 1
      && w.document.querySelectorAll('.library-list-row').length === 1);

  partialGroupSelect.value = 'none';
  partialGroupSelect.dispatchEvent(new w.Event('change', { bubbles: true }));

  queuedLibraryResponses.push(libraryPayload([visibleDialogue], {
    total: 5, complete: true, has_more: true, next_offset: 1,
  }));
  w.document.querySelector('[data-library-command="clear-search"]').click();
  await flush();
  await flush();
  record('clearing keyword search restores authoritative inventory paging',
    !new w.URL(libraryRequestUrls[libraryRequestUrls.length - 1], w.location.href).searchParams.has('q')
      && w.OraLibraryWorkspace.getState().total === 5
      && w.OraLibraryWorkspace.getState().pagination.has_more === true);

  queuedLibraryResponses.push(libraryPayload([
    visibleDialogue, metadataDialogue, contextEngram, nonAtomicEngram, contextFile,
  ], {
    total: 5, complete: true, offset: 1,
    source_counts: { dialogues: 2, engrams: 2, files: 1 },
    item_type_counts: { Dialogue: 2, Engram: 2, File: 1 },
  }));
  w.document.querySelector('[data-library-command="load-more"]').click();
  await flush();
  await flush();
  record('stable-ID append deduplicates authoritative pages',
    w.OraLibraryWorkspace.getState().loaded === 5
      && w.document.querySelectorAll('.library-list-row').length === 5);
  var libraryTypeFilter = w.document.querySelector('[data-library-filter="type"]');
  var typeOptions = Array.from(libraryTypeFilter.options).map(function (option) { return option.value; });
  libraryTypeFilter.value = 'Dialogue';
  libraryTypeFilter.dispatchEvent(new w.Event('change', { bubbles: true }));
  record('Type filter exposes and positively matches authoritative item_type values only',
    typeOptions.indexOf('Dialogue') !== -1
      && typeOptions.indexOf('text/markdown') === -1
      && w.document.querySelectorAll('.library-list-row').length === 2);
  queuedLibraryResponses.push(libraryPayload([contextEngram], {
    total: 1,
    source_counts: { dialogues: 0, engrams: 1, files: 0 },
    item_type_counts: { Engram: 1 },
  }));
  await w.OraLibraryWorkspace.refresh();
  await flush();
  var zeroDialogueOption = Array.from(libraryTypeFilter.options).find(function (option) {
    return option.value === 'Dialogue';
  });
  record('selected Type survives a facet rebuild as an honest zero-count filter',
    w.OraLibraryWorkspace.getState().filters.type === 'Dialogue'
      && !!zeroDialogueOption
      && zeroDialogueOption.textContent === 'Dialogue (0)'
      && zeroDialogueOption.dataset.zeroCount === 'true'
      && w.document.querySelectorAll('.library-list-row').length === 0);
  queuedLibraryResponses.push(libraryPayload([
    visibleDialogue, metadataDialogue, contextEngram, nonAtomicEngram, contextFile,
  ], {
    total: 5,
    source_counts: { dialogues: 2, engrams: 2, files: 1 },
    item_type_counts: { Dialogue: 2, Engram: 2, File: 1 },
  }));
  await w.OraLibraryWorkspace.refresh();
  await flush();
  w.document.querySelector('[data-library-command="clear-filters"]').click();

  var scopeAllRows = [
    visibleDialogue, metadataDialogue, contextEngram, nonAtomicEngram, contextFile,
  ];
  var scopeMixedRows = scopeAllRows.slice(0, 4);
  var scopeFilesToggle = w.document.querySelector('[data-library-source][value="files"]');
  queuedLibraryResponses.push(libraryPayload(scopeMixedRows, {
    sources: ['dialogues', 'engrams'], total: 4,
    source_counts: { dialogues: 2, engrams: 2, files: 0 },
    item_type_counts: { Dialogue: 2, Engram: 2 },
  }));
  scopeFilesToggle.checked = false;
  scopeFilesToggle.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush();
  await flush();
  queuedLibraryResponses.push(libraryPayload(scopeMixedRows, {
    sources: ['dialogues', 'engrams'], total: 4,
    source_counts: { dialogues: 2, engrams: 2, files: 0 },
    item_type_counts: { Dialogue: 2, Engram: 2 },
  }));
  librarySearch.value = 'preserve this scoped query';
  librarySearch.dispatchEvent(new w.Event('input', { bubbles: true }));
  await flush();
  await flush();
  libraryTypeFilter.value = 'Dialogue';
  libraryTypeFilter.dispatchEvent(new w.Event('change', { bubbles: true }));
  partialGroupSelect.value = 'source';
  partialGroupSelect.dispatchEvent(new w.Event('change', { bubbles: true }));
  var scopeSort = w.document.querySelector('[data-library-sort]');
  scopeSort.value = 'title';
  scopeSort.dispatchEvent(new w.Event('change', { bubbles: true }));

  var scopeRelated = deferredResponse();
  queuedRelatedResponses.push(scopeRelated);
  var scopePinnedRow = Array.from(w.document.querySelectorAll('.library-list-row')).find(function (item) {
    return item.textContent.indexOf('Saved Dialogue Name') !== -1;
  });
  scopePinnedRow.querySelector('.library-list-row__pin').click();
  var scopeSelectedCheck = scopePinnedRow.querySelector('input[type="checkbox"]');
  scopeSelectedCheck.checked = true;
  scopeSelectedCheck.dispatchEvent(new w.Event('change', { bubbles: true }));
  var namedScopeReplacement = deferredResponse();
  queuedLibraryResponses.push(namedScopeReplacement);
  var projectScope = w.document.querySelector('[data-library-project]');
  projectScope.value = 'ora';
  projectScope.dispatchEvent(new w.Event('change', { bubbles: true }));
  var clearedScopeState = w.OraLibraryWorkspace.getState();
  var namedLibraryScopeParams = new w.URL(
    libraryRequestUrls[libraryRequestUrls.length - 1], w.location.href
  ).searchParams;
  record('named project change clears old identity-bound Library state before its delayed response',
    clearedScopeState.projectId === 'ora'
      && clearedScopeState.loaded === 0
      && clearedScopeState.indexed === 0
      && clearedScopeState.selectedIds.length === 0
      && clearedScopeState.pinnedId === null
      && clearedScopeState.related.anchorId === null
      && clearedScopeState.related.loading === false
      && clearedScopeState.related.returned === 0
      && clearedScopeState.related.drawable === 0
      && scopeRelated.options.signal.aborted
      && !w.document.querySelector('[data-library-row-id="dialogues:named-live"]')
      && w.document.querySelector('.library-preview-layer--findings').textContent
        .indexOf('Pin a Library item') !== -1
      && w.document.querySelector('[data-library-popover="actions"]').disabled
      && !w.document.querySelector('[data-library-action]'));
  record('named project scope preserves independent browse controls and additive sources',
    namedLibraryScopeParams.get('project_id') === 'ora'
      && namedLibraryScopeParams.getAll('source').join(',') === 'dialogues,engrams'
      && namedLibraryScopeParams.get('q') === 'preserve this scoped query'
      && clearedScopeState.sources.join(',') === 'dialogues,engrams'
      && clearedScopeState.query === 'preserve this scoped query'
      && clearedScopeState.filters.type === 'Dialogue'
      && clearedScopeState.group === 'source'
      && clearedScopeState.sort === 'title');
  scopeRelated.resolve({ rows: [], total: 0 });
  namedScopeReplacement.resolve(libraryPayload(scopeMixedRows, {
    sources: ['dialogues', 'engrams'], total: 4,
    source_counts: { dialogues: 2, engrams: 2, files: 0 },
    item_type_counts: { Dialogue: 2, Engram: 2 },
  }));
  await flush();
  await flush();
  queuedLibraryResponses.push(libraryPayload(scopeMixedRows, {
    sources: ['dialogues', 'engrams'], total: 4,
    source_counts: { dialogues: 2, engrams: 2, files: 0 },
    item_type_counts: { Dialogue: 2, Engram: 2 },
  }));
  librarySearch.value = '';
  librarySearch.dispatchEvent(new w.Event('input', { bubbles: true }));
  await flush();
  await flush();
  w.document.querySelector('[data-library-command="clear-filters"]').click();
  partialGroupSelect.value = 'none';
  partialGroupSelect.dispatchEvent(new w.Event('change', { bubbles: true }));
  scopeSort.value = 'recent';
  scopeSort.dispatchEvent(new w.Event('change', { bubbles: true }));
  queuedLibraryResponses.push(libraryPayload(scopeAllRows, {
    total: 5,
    source_counts: { dialogues: 2, engrams: 2, files: 1 },
    item_type_counts: { Dialogue: 2, Engram: 2, File: 1 },
  }));
  scopeFilesToggle.checked = true;
  scopeFilesToggle.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush();
  await flush();

  Array.from(w.document.querySelectorAll('.library-list-row')).forEach(function (item) {
    var checkbox = item.querySelector('input[type="checkbox"]');
    checkbox.checked = true;
    checkbox.dispatchEvent(new w.Event('change', { bubbles: true }));
  });
  record('checked-context action is reachable through Actions without a pinned item',
    w.OraLibraryWorkspace.getState().pinnedId === null
      && !w.document.querySelector('[data-library-popover="actions"]').disabled
      && !!w.document.querySelector('[data-library-action="new-dialogue"]'));
  var namedDiscoveryMembershipBefore = {
    projectWrites: projectWrites.length,
    activeProject: activeProject,
    projectIds: envelopes['named-live'].project_ids.slice(),
  };
  w.document.querySelector('[data-library-action="new-dialogue"]').click();
  await flush();
  record('New Dialogue names unsupported checked context before review',
    w.document.querySelector('.conversation-create-overlay').classList.contains('is-open')
      && w.document.querySelector('#conversationCreateHeading').textContent === 'New Private Dialogue'
      && w.document.querySelector('.conversation-create-status').textContent.indexOf('metadata-only Dialogue') !== -1
      && w.document.querySelector('.conversation-create-status').textContent.indexOf('Project image.png (File)') !== -1
      && w.document.querySelector('.conversation-create-status').textContent.indexOf('Reference Engram (non-atomic Engram)') !== -1);
  var creationDescription = w.document.querySelector('.conversation-create-description');
  creationDescription.value = 'Use the checked grounded context to plan this new dialogue.';
  creationDescription.dispatchEvent(new w.Event('input', { bubbles: true }));
  w.document.querySelector('.conversation-create-discover').click();
  await flush();
  await flush();
  var creationParams = new w.URL(
    browserRequestUrls[browserRequestUrls.length - 1], w.location.href
  ).searchParams;
  record('named checked-context discovery sends project scope and every repeated admitted ref',
    creationParams.getAll('include_ref').sort().join(',') === 'engram:claim,named-live'
      && creationParams.getAll('include_ref').length === 2
      && creationParams.get('project_id') === 'ora'
      && creationParams.get('target_tag') === 'private'
      && !creationParams.getAll('include_ref').includes('engram:reference')
      && Array.from(w.document.querySelectorAll('.conversation-create-add'))
        .filter(function (button) { return button.textContent === 'Added'; }).length === 2);
  record('named checked-context discovery does not mutate stored project membership',
    projectWrites.length === namedDiscoveryMembershipBefore.projectWrites
      && activeProject === namedDiscoveryMembershipBefore.activeProject
      && envelopes['named-live'].project_ids.join(',')
        === namedDiscoveryMembershipBefore.projectIds.join(','));
  w.document.querySelector('.conversation-create-close').click();

  var staleNamedDiscovery = deferredResponse();
  queuedBrowserResponses.push(staleNamedDiscovery);
  w.OraSidebar.createFromLibrarySelection([visibleDialogue, contextEngram], 'ora');
  creationDescription = w.document.querySelector('.conversation-create-description');
  creationDescription.value = 'Delay this named discovery until another creation opens.';
  creationDescription.dispatchEvent(new w.Event('input', { bubbles: true }));
  w.document.querySelector('.conversation-create-discover').click();
  await flush();
  var staleNamedDiscoveryParams = new w.URL(
    browserRequestUrls[browserRequestUrls.length - 1], w.location.href
  ).searchParams;
  w.OraSidebar.openCreation();
  creationDescription = w.document.querySelector('.conversation-create-description');
  staleNamedDiscovery.resolve({
    review_token: 'stale-named-review-token',
    rows: [{
      conversation_id: 'stale-named-row', source_kind: 'live', title: 'Stale named result',
    }],
    total: 1,
  });
  await flush();
  await flush();
  record('ordinary creation ignores a delayed named-scope discovery response',
    staleNamedDiscoveryParams.get('project_id') === 'ora'
      && creationDescription.value === ''
      && w.document.querySelectorAll('.conversation-create-result').length === 0
      && w.document.querySelector('.conversation-create-reviewed input').disabled
      && w.document.querySelector('.conversation-create-status').textContent
        === 'Nothing is created until you confirm.');
  creationDescription.value = 'Find ordinary material without a Library project scope.';
  creationDescription.dispatchEvent(new w.Event('input', { bubbles: true }));
  w.document.querySelector('.conversation-create-discover').click();
  await flush();
  await flush();
  var ordinaryCreationParams = new w.URL(
    browserRequestUrls[browserRequestUrls.length - 1], w.location.href
  ).searchParams;
  w.document.querySelector('.conversation-create-close').click();
  w.OraSidebar.createFromLibraryDialogue(visibleDialogue);
  creationDescription = w.document.querySelector('.conversation-create-description');
  creationDescription.value = 'Find material for one contributor without leaked scope.';
  creationDescription.dispatchEvent(new w.Event('input', { bubbles: true }));
  w.document.querySelector('.conversation-create-discover').click();
  await flush();
  await flush();
  var singleContributorParams = new w.URL(
    browserRequestUrls[browserRequestUrls.length - 1], w.location.href
  ).searchParams;
  w.document.querySelector('.conversation-create-close').click();
  w.OraSidebar.createFromLibrarySelection([visibleDialogue, contextEngram], 'general');
  creationDescription = w.document.querySelector('.conversation-create-description');
  creationDescription.value = 'Treat legacy General as Commons during contributor discovery.';
  creationDescription.dispatchEvent(new w.Event('input', { bubbles: true }));
  w.document.querySelector('.conversation-create-discover').click();
  await flush();
  await flush();
  var generalCreationParams = new w.URL(
    browserRequestUrls[browserRequestUrls.length - 1], w.location.href
  ).searchParams;
  record('every creation open resets Library discovery scope outside checked-context flow',
    !ordinaryCreationParams.has('project_id')
      && ordinaryCreationParams.getAll('include_ref').length === 0
      && !singleContributorParams.has('project_id')
      && singleContributorParams.getAll('include_ref').join(',') === 'named-live'
      && !generalCreationParams.has('project_id')
      && generalCreationParams.getAll('include_ref').sort().join(',')
        === 'engram:claim,named-live');
  w.document.querySelector('.conversation-create-close').click();
  queuedLibraryResponses.push(libraryPayload([
    visibleDialogue, metadataDialogue, contextEngram, nonAtomicEngram, contextFile,
  ], {
    total: 5, source_counts: { dialogues: 2, engrams: 2, files: 1 },
  }));
  browseButton.click();
  await flush();
  await flush();
  Array.from(w.document.querySelectorAll('.library-list-row input[type="checkbox"]')).forEach(function (checkbox) {
    if (!checkbox.checked) return;
    checkbox.checked = false;
    checkbox.dispatchEvent(new w.Event('change', { bubbles: true }));
  });

  var inquiryDraft = w.document.querySelector('.input-pane textarea');
  inquiryDraft.value = 'Composer draft survives Library preview';
  var activeDialogueBeforePreview = w.OraConversation.getActiveConversationId();
  var visibleBody = '# Atomic Claim Title\n**older pin preview**\n<em>literal HTML</em>';
  queuedPreviewResponses.push({
    id: contextEngram.id,
    source: 'engrams',
    text: visibleBody,
  });
  Array.from(w.document.querySelectorAll('.library-list-row__pin')).find(function (button) {
    return button.textContent.indexOf('Atomic Claim Title') !== -1;
  }).click();
  await flush();
  await flush();
  var renderedPreviewBody = w.document.querySelector('.library-preview-body');
  record('text body preview is literal and preserves active Dialogue, draft, and lower owners',
    !!renderedPreviewBody
      && renderedPreviewBody.textContent === visibleBody
      && renderedPreviewBody.querySelector('em') === null
      && w.getComputedStyle(renderedPreviewBody).whiteSpace === 'pre-wrap'
      && w.OraConversation.getActiveConversationId() === activeDialogueBeforePreview
      && inquiryDraft.value === 'Composer draft survives Library preview'
      && preservedFinding.parentElement === w.document.querySelector('.output-content')
      && preservedExhibit.parentElement === w.document.querySelector('.right-pane'));

  var currentBody = '# Atomic Claim Title\n**newer current Markdown**\n<em>literal HTML</em>';
  var rawMarkdownLf = '---\ntype: engram\ntags:\n  - atomic\n---\n' + currentBody;
  var rawMarkdown = rawMarkdownLf.replace(/\n/g, '\r\n');
  var editDigest = 'a'.repeat(64);
  queuedEditResponses.push({
    id: contextEngram.id, source: 'engrams', text: rawMarkdown, digest: editDigest,
  });
  w.document.querySelector('[data-library-edit="start"]').click();
  await flush();
  await flush();
  var editDraft = w.document.querySelector('[data-library-edit-draft]');
  var putsBeforeCancel = editRequests.filter(function (item) { return item.method === 'PUT'; }).length;
  record('eligible Markdown preview exposes Edit and a plain textarea with Save and Cancel',
    !!editDraft
      && editDraft.tagName === 'TEXTAREA'
      && editDraft.value === rawMarkdownLf
      && !!w.document.querySelector('[data-library-edit="save"]')
      && !!w.document.querySelector('[data-library-edit="cancel"]')
      && new w.URL(editRequests[editRequests.length - 1].url, w.location.href)
        .searchParams.get('id') === contextEngram.id);
  editDraft.value = 'Cancelled draft';
  editDraft.dispatchEvent(new w.Event('input', { bubbles: true }));
  queuedPreviewResponses.push({
    id: contextEngram.id, source: 'engrams', text: currentBody,
  });
  w.document.querySelector('[data-library-edit="cancel"]').click();
  await flush();
  await flush();
  record('Cancel refetches the current preview without writing or restoring the older pin text',
    !w.document.querySelector('[data-library-edit-draft]')
      && w.document.querySelector('.library-preview-body').textContent === currentBody
      && queuedPreviewResponses.length === 0
      && editRequests.filter(function (item) { return item.method === 'PUT'; }).length
        === putsBeforeCancel);

  queuedEditResponses.push({
    id: contextEngram.id, source: 'engrams', text: rawMarkdown, digest: editDigest,
  });
  w.document.querySelector('[data-library-edit="start"]').click();
  await flush();
  await flush();
  editDraft = w.document.querySelector('[data-library-edit-draft]');
  var savedRawMarkdown = rawMarkdownLf.replace('newer current Markdown', 'edited Markdown');
  editDraft.value = savedRawMarkdown;
  editDraft.dispatchEvent(new w.Event('input', { bubbles: true }));
  queuedEditResponses.push({
    ok: false,
    status: 409,
    payload: { error: 'The Markdown item changed after editing began', code: 'conflict', saved: false },
  });
  w.document.querySelector('[data-library-edit="save"]').click();
  await flush();
  await flush();
  var conflictedDraft = w.document.querySelector('[data-library-edit-draft]');
  var conflictRequest = editRequests[editRequests.length - 1];
  record('a save conflict retains the complete draft and exact digest contract',
    !!conflictedDraft
      && conflictedDraft.value === savedRawMarkdown
      && w.document.querySelector('[data-library-edit-status]').textContent
        .indexOf('draft is still here') !== -1
      && Object.keys(conflictRequest.body).sort().join(',') === 'expected_digest,id,text'
      && conflictRequest.body.id === contextEngram.id
      && conflictRequest.body.expected_digest === editDigest
      && conflictRequest.body.text
        === savedRawMarkdown.replace(/\n/g, '\r\n'));

  var savedBody = currentBody.replace('newer current Markdown', 'edited Markdown');
  queuedEditResponses.push({
    id: contextEngram.id,
    source: 'engrams',
    saved: true,
    index_refreshed: false,
    index_error: 'simulated refresh failure',
  });
  queuedPreviewResponses.push({
    ok: false,
    status: 404,
    payload: { error: 'the failed reindex left no current preview row' },
  });
  w.document.querySelector('[data-library-edit="save"]').click();
  await flush();
  await flush();
  var savedStatus = w.document.querySelector('[data-library-edit-status]');
  record('a completed file save reports a failed Engram index refresh separately',
    !w.document.querySelector('[data-library-edit-draft]')
      && !!savedStatus
      && savedStatus.textContent.indexOf('File saved') !== -1
      && savedStatus.textContent.indexOf('index refresh failed') !== -1
      && w.document.querySelector('.library-preview-layer--findings').textContent
        .indexOf('failed reindex left no current preview row') !== -1);
  visibleBody = savedBody;
  queuedPreviewResponses.push({ id: contextEngram.id, source: 'engrams', text: savedBody });
  Array.from(w.document.querySelectorAll('.library-list-row__pin')).find(function (button) {
    return button.textContent.indexOf('Atomic Claim Title') !== -1;
  }).click();
  await flush();
  await flush();

  var failedBodyRefresh = deferredResponse();
  queuedLibraryResponses.push(failedBodyRefresh);
  var failedBodyRefreshPromise = w.OraLibraryWorkspace.refresh();
  var bodyWhileRefreshPending = w.document.querySelector('.library-preview-body');
  record('same-scope replacement keeps a settled text body visible while pending',
    !!bodyWhileRefreshPending
      && bodyWhileRefreshPending.textContent === visibleBody
      && !!failedBodyRefresh.options
      && failedBodyRefresh.options.signal.aborted === false);
  failedBodyRefresh.resolveError({ error: 'replacement failed' }, 503);
  await failedBodyRefreshPromise;
  await flush();
  var bodyAfterRefreshFailure = w.document.querySelector('.library-preview-body');
  record('failed same-scope replacement keeps the settled text body visible',
    !!bodyAfterRefreshFailure
      && bodyAfterRefreshFailure.textContent === visibleBody
      && w.document.getElementById('libraryWorkspaceNotice').textContent
        .indexOf('replacement failed') !== -1);

  var freshBody = 'Fresh body after replacement';
  var successfulBodyRefresh = deferredResponse();
  var revalidatedBodyPreview = deferredResponse();
  queuedLibraryResponses.push(successfulBodyRefresh);
  queuedPreviewResponses.push(revalidatedBodyPreview);
  var successfulBodyRefreshPromise = w.OraLibraryWorkspace.refresh();
  successfulBodyRefresh.resolve(libraryPayload([
    visibleDialogue, metadataDialogue, contextEngram, nonAtomicEngram, contextFile,
  ], {
    total: 5, source_counts: { dialogues: 2, engrams: 2, files: 1 },
  }));
  await successfulBodyRefreshPromise;
  await flush();
  revalidatedBodyPreview.resolve({
    id: contextEngram.id,
    source: 'engrams',
    text: freshBody,
  });
  await flush();
  await flush();
  var bodyAfterRefreshSuccess = w.document.querySelector('.library-preview-body');
  record('successful same-scope replacement revalidates the matching pinned body',
    !!revalidatedBodyPreview.options
      && !!bodyAfterRefreshSuccess
      && bodyAfterRefreshSuccess.textContent === freshBody);

  var staleBodyPreview = deferredResponse();
  queuedPreviewResponses.push(staleBodyPreview);
  w.document.querySelector(
    '[data-library-row-id="engrams:reference"] .library-list-row__pin'
  ).click();
  await flush();
  w.document.querySelector(
    '[data-library-row-id="dialogues:metadata-only"] .library-list-row__pin'
  ).click();
  staleBodyPreview.resolve({
    id: nonAtomicEngram.id,
    source: 'engrams',
    text: 'STALE BODY MUST NOT APPEAR',
  });
  await flush();
  await flush();
  var unavailablePreviewText = w.document.querySelector(
    '.library-preview-layer--findings'
  ).textContent;
  record('newer pin aborts and generation-discards a late text body into an honest unavailable state',
    staleBodyPreview.options.signal.aborted
      && w.OraLibraryWorkspace.getState().pinnedId === metadataDialogue.id
      && unavailablePreviewText.indexOf('cannot be read here') !== -1
      && unavailablePreviewText.indexOf('STALE BODY MUST NOT APPEAR') === -1
      && !w.document.querySelector('.library-preview-body'));

  var imageRow = w.document.querySelector('[data-library-row-id="files:project-image"]');
  var imageCheck = imageRow.querySelector('input[type="checkbox"]');
  imageCheck.checked = true;
  imageCheck.dispatchEvent(new w.Event('change', { bubbles: true }));
  queuedPreviewResponses.push({
    id: contextFile.id,
    source: 'files',
    image: { mime_type: 'image/png', data: 'AQID' },
  });
  w.document.querySelector(
    '[data-library-row-id="files:project-image"] .library-list-row__pin'
  ).click();
  await flush();
  await flush();
  var exhibitImage = w.document.querySelector(
    '.library-preview-layer--exhibits .library-preview-image'
  );
  record('an admitted project image renders only in the Library Exhibits layer without changing state or owners',
    !!exhibitImage
      && exhibitImage.tagName === 'IMG'
      && exhibitImage.alt === 'Project image.png'
      && exhibitImage.src === 'data:image/png;base64,AQID'
      && !w.document.querySelector('.library-preview-layer--findings img')
      && w.document.querySelector('.library-preview-layer--findings').textContent
        .indexOf('Metadata and relationships remain in Findings') !== -1
      && w.OraLibraryWorkspace.getState().pinnedId === contextFile.id
      && w.OraLibraryWorkspace.getState().selectedIds.includes(contextFile.id)
      && w.OraConversation.getActiveConversationId() === activeDialogueBeforePreview
      && inquiryDraft.value === 'Composer draft survives Library preview'
      && preservedFinding.parentElement === w.document.querySelector('.output-content')
      && preservedExhibit.parentElement === w.document.querySelector('.right-pane'));

  exhibitImage.dispatchEvent(new w.Event('error'));
  record('a browser decoder rejection becomes the current image preview\'s honest unavailable state',
    w.OraLibraryWorkspace.getState().pinnedId === contextFile.id
      && !w.document.querySelector('.library-preview-image')
      && w.document.querySelector('.library-preview-layer--findings').textContent
        .indexOf('The browser could not decode the current image.') !== -1
      && w.document.querySelector('.library-preview-layer--exhibits').textContent
        .indexOf('Image preview unavailable.') !== -1);

  var staleImagePreview = deferredResponse();
  queuedPreviewResponses.push(staleImagePreview);
  w.document.querySelector(
    '[data-library-row-id="files:project-image"] .library-list-row__pin'
  ).click();
  await flush();
  w.document.querySelector(
    '[data-library-row-id="dialogues:metadata-only"] .library-list-row__pin'
  ).click();
  staleImagePreview.resolve({
    id: contextFile.id,
    source: 'files',
    image: { mime_type: 'image/png', data: 'U1RBTEU=' },
  });
  await flush();
  await flush();
  record('a newer pin aborts and generation-discards a late Exhibits image',
    staleImagePreview.options.signal.aborted
      && w.OraLibraryWorkspace.getState().pinnedId === metadataDialogue.id
      && !w.document.querySelector('.library-preview-image'));
  imageCheck = w.document.querySelector(
    '[data-library-row-id="files:project-image"] input[type="checkbox"]'
  );
  imageCheck.checked = false;
  imageCheck.dispatchEvent(new w.Event('change', { bubbles: true }));

  var extensionActionRuns = 0;
  w.document.addEventListener('ora:library-actions-requested', function appendProofAction(event) {
    event.detail.actions.push({
      id: 'proof-extension', label: 'Extension proof action',
      run: function () { extensionActionRuns += 1; },
    });
  });
  Array.from(w.document.querySelectorAll('.library-list-row__pin')).find(function (button) {
    return button.textContent.indexOf('Private Dialogue') !== -1;
  }).click();
  record('metadata-only Dialogues stay visible but unreadable',
    w.document.querySelector('.library-preview-layer--findings').textContent
      .indexOf('intentionally metadata-only') !== -1
      && !Array.from(w.document.querySelectorAll('[data-library-action]')).some(function (button) {
        return ['Continue Dialogue', 'Fork Dialogue', 'New Dialogue with contributor', 'Archive Dialogue']
          .includes(button.textContent);
      }));
  record('relationship disclosure is native keyboard-readable and exposes missing family truthfully',
    w.document.querySelector('.library-relationships summary').tagName === 'SUMMARY'
      && w.document.querySelector('.library-relationships').textContent.indexOf('family unavailable') !== -1
      && w.document.querySelector('.library-relationships').textContent.indexOf('snapshot is stale') !== -1
      && w.document.querySelector('.library-relationships summary').textContent
        .indexOf('Relationships (count unavailable) — state stale; updated time unavailable') !== -1);
  record('G1.27-style contextual actions extend rather than replace built-ins',
    !!w.document.querySelector('[data-library-action="proof-extension"]')
      && !!w.document.querySelector('[data-library-action="related"]'));
  w.document.querySelector('[data-library-action="proof-extension"]').click();
  await flush();
  record('extension contextual action remains callable', extensionActionRuns === 1);
  record('native O becomes the selected-item anchor with compact state only',
    w.document.getElementById('logo-o').getAttribute('aria-label').indexOf('Private Dialogue') !== -1
      && w.document.querySelector('.library-o-type').textContent === 'Dialogues'
      && w.document.querySelector('.library-o-state').textContent === 'metadata');
  w.OraLibraryWorkspace.activatePinned();
  record('O activation hands keyboard focus to relationship disclosure',
    w.document.activeElement === w.document.querySelector('.library-relationships summary'));

  w.document.querySelector('[data-library-view="visual"]').click();
  record('List and Visual share the pinned result through the native O without duplicating it',
    w.OraLibraryWorkspace.getState().view === 'visual'
      && w.document.querySelectorAll('.library-visual-node').length === 4
      && !w.document.querySelector('[data-library-node-id="dialogues:metadata-only"]')
      && w.document.getElementById('logo-o').getAttribute('aria-label').indexOf('Private Dialogue') !== -1);
  record('Visual invents no connector from relationship summaries without endpoints',
    w.document.querySelectorAll('.library-visual-connectors line').length === 0
      && w.document.querySelector('.library-visual-edge-state').textContent
        .indexOf('privacy-safe Related locator') !== -1);

  w.document.querySelector('[data-library-view="list"]').click();
  queuedRelatedResponses.push({
    rows: [
      {
        conversation_id: 'named-live', source_kind: 'live', title: 'Saved Dialogue Name',
        relationship: { available: true, kinds: [] }, relation: 'self',
      },
      {
        conversation_id: 'second-live', source_kind: 'live', title: 'Second Dialogue', score: 90,
        relationship: { available: true, kinds: ['direct-child', 'shared-project'] },
        relation: 'direct-child',
      },
      {
        conversation_id: 'semantic-only', source_kind: 'engram', title: 'Semantic suggestion', score: 0.81,
        relationship: { available: false, kinds: [] }, relation: 'semantic',
      },
    ],
    total: 3,
    source_counts: { live: 2, archive: 0, engram: 1 },
    facets: {},
  });
  Array.from(w.document.querySelectorAll('.library-list-row__pin')).find(function (button) {
    return button.textContent.indexOf('Saved Dialogue Name') !== -1;
  }).click();
  record('fresh numeric relationship summaries expose their exact count while endpoint detail loads',
    w.document.querySelector('.library-relationships summary').textContent
      .indexOf('Relationships (1) — state fresh') !== -1);
  await flush();
  await flush();
  record('readable Dialogue keeps its existing contextual actions',
    ['related', 'continue', 'fork', 'contributor', 'archive'].every(function (id) {
      return !!w.document.querySelector('[data-library-action="' + id + '"]');
    }));
  w.document.querySelector('[data-library-view="visual"]').click();
  await new Promise(function (resolve) { w.requestAnimationFrame(resolve); });
  var relatedParams = new w.URL(
    relatedRequestUrls[relatedRequestUrls.length - 1], w.location.href
  );
  record('pinned readable Dialogue uses Related only as relationship detail with active source filters',
    relatedParams.pathname === '/api/conversation/named-live/related'
      && relatedParams.searchParams.get('conversations') === '1'
      && relatedParams.searchParams.get('engrams') === '1'
      && !relatedParams.searchParams.has('q'));
  record('explicit Related endpoint authority draws from the live O and withholds semantic suggestions',
    w.document.querySelectorAll('.library-visual-connectors line').length === 1
      && w.document.querySelector('.library-visual-connectors line').dataset.relationshipType
        .indexOf('direct-child') !== -1
      && w.document.querySelectorAll('.library-visual-node--related').length === 1
      && w.document.querySelector('.library-visual-edge-state').textContent
        .indexOf('lacked edge authority') !== -1
      && visualPlacementIsSafe());
  w.document.querySelector('.library-visual-node--related').click();
  record('related nodes are keyboard buttons with equivalent typed relationship disclosure',
    w.document.querySelector('.library-visual-node--related').tagName === 'BUTTON'
      && w.document.activeElement.dataset.relatedEndpointId === 'second-live'
      && w.document.querySelector('.library-relationships').textContent.indexOf('outgoing direct-child') !== -1
      && w.document.querySelector('.library-relationships').textContent.indexOf('peer shared-project') !== -1
      && w.document.querySelector('.library-relationships').textContent.indexOf('family unavailable') !== -1
      && w.document.querySelector('.library-relationships').textContent.indexOf('confidence unavailable') !== -1
      && w.document.querySelector('.library-relationships').textContent.indexOf('freshness unavailable') !== -1
      && w.document.querySelector('.library-relationships summary').textContent
        .indexOf('Relationships (1) — state fresh; updated 2026-08-31T10:00:00Z') !== -1);

  await w.OraSidebar.setActiveProject('project-a', 'Project A');
  w.document.querySelector('[data-library-view="list"]').click();
  var savedDialogueListRow = Array.from(w.document.querySelectorAll('.library-list-row')).find(function (item) {
    return item.textContent.indexOf('Saved Dialogue Name') !== -1;
  });
  var savedDialogueCheck = savedDialogueListRow.querySelector('input[type="checkbox"]');
  savedDialogueCheck.checked = true;
  savedDialogueCheck.dispatchEvent(new w.Event('change', { bubbles: true }));
  var stableRefresh = deferredResponse();
  queuedLibraryResponses.push(stableRefresh);
  var stableRefreshPromise = w.OraLibraryWorkspace.refresh();
  record('replacement refresh keeps the prior pin and selection until its response commits',
    w.OraLibraryWorkspace.getState().pinnedId === 'dialogues:named-live'
      && w.OraLibraryWorkspace.getState().selectedIds.includes('dialogues:named-live')
      && w.document.querySelector('.library-list-row__pin').textContent.indexOf('Saved Dialogue Name') !== -1);
  stableRefresh.resolve(libraryPayload([visibleDialogue, secondDialogue, metadataDialogue], {
    total: 3, complete: true,
  }));
  await stableRefreshPromise;
  await flush();
  record('replacement refresh preserves pin and selection by stable ID after atomic commit',
    w.OraLibraryWorkspace.getState().pinnedId === 'dialogues:named-live'
      && w.OraLibraryWorkspace.getState().selectedIds.includes('dialogues:named-live')
      && w.OraLibraryWorkspace.getState().loaded === 3);

  var secondDialogueListRow = Array.from(w.document.querySelectorAll('.library-list-row')).find(function (item) {
    return item.textContent.indexOf('Second Dialogue') !== -1;
  });
  var secondDialogueCheck = secondDialogueListRow.querySelector('input[type="checkbox"]');
  secondDialogueCheck.checked = true;
  secondDialogueCheck.dispatchEvent(new w.Event('change', { bubbles: true }));
  bulkFailIds.add('second-live');
  envelopes['named-live'].project_ids = ['existing-project', 'late-project'];
  queuedLibraryResponses.push(libraryPayload([visibleDialogue, secondDialogue, metadataDialogue], {
    total: 3, complete: true,
  }));
  w.document.querySelector('[data-library-action="project"]').click();
  await flush();
  await flush();
  await flush();
  await flush();
  bulkFailIds.delete('second-live');
  var namedWrite = projectWrites.find(function (write) { return write.id === 'named-live'; });
  var failedWrite = projectWrites.find(function (write) { return write.id === 'second-live'; });
  record('project action clears successful selections, retains failed rows, and preserves newer membership',
    !!namedWrite
      && !!failedWrite
      && namedWrite.body.add_project_id === 'project-a'
      && !Object.prototype.hasOwnProperty.call(namedWrite.body, 'project_ids')
      && envelopes['named-live'].project_ids.join(',') === 'existing-project,late-project,project-a'
      && w.OraLibraryWorkspace.getState().selectedIds.join(',') === 'dialogues:second-live'
      && w.document.getElementById('libraryWorkspaceNotice').textContent.indexOf('1 added; 1 failed') !== -1);

  var staleRelated = deferredResponse();
  queuedRelatedResponses.push(staleRelated);
  Array.from(w.document.querySelectorAll('.library-list-row__pin')).find(function (button) {
    return button.textContent.indexOf('Saved Dialogue Name') !== -1;
  }).click();
  Array.from(w.document.querySelectorAll('.library-list-row__pin')).find(function (button) {
    return button.textContent.indexOf('Private Dialogue') !== -1;
  }).click();
  record('a newer pin aborts the older relationship generation',
    !!(staleRelated.options && staleRelated.options.signal && staleRelated.options.signal.aborted));
  staleRelated.resolve({
    rows: [{
      conversation_id: 'third-live', source_kind: 'live', title: 'Stale endpoint',
      relationship: { available: true, kinds: ['direct-child'] },
    }],
    total: 1,
  });
  await flush();
  await flush();
  w.document.querySelector('[data-library-view="visual"]').click();
  await flush();
  record('late Related completion cannot attach endpoints to a metadata-only pin',
    w.OraLibraryWorkspace.getState().pinnedId === 'dialogues:metadata-only'
      && w.OraLibraryWorkspace.getState().related.drawable === 0
      && w.document.querySelectorAll('.library-visual-connectors line').length === 0);

  var measuredCases = [];
  var measuredPlacementSafety = [];
  [736, 360].forEach(function (width) {
    measuredWidth = width;
    installMeasuredGeometry();
    w.dispatchEvent(new w.Event('resize'));
    measuredCases.push(library.style.width + ':' + library.dataset.layout);
    measuredPlacementSafety.push(visualPlacementIsSafe());
  });
  record('live geometry remeasures at 736px and 360px with contained, non-overlapping nodes',
    measuredCases.join(',') === '736px:wide,360px:narrow'
      && measuredPlacementSafety.every(Boolean), measuredCases.join(','));

  measuredWidth = 702;
  installMeasuredGeometry();
  w.dispatchEvent(new w.Event('resize'));
  var measuredNarrowRightBank = w.document.querySelector('.library-bridge-bank--right');
  var measuredNarrowRightRect = measuredNarrowRightBank.getBoundingClientRect();
  var measuredNarrowButtons = Array.from(measuredNarrowRightBank.querySelectorAll('button'))
    .map(function (button) { return button.getBoundingClientRect(); });
  var measuredNarrowRun = measuredNarrowButtons[measuredNarrowButtons.length - 1].right
    - measuredNarrowButtons[0].left;
  record('a narrow Library inside a 1024px viewport keeps every overflowing right-bank control reachable',
    w.innerWidth === 1024
      && library.style.width === '702px'
      && library.dataset.layout === 'narrow'
      && measuredNarrowRightRect.width === 323
      && measuredNarrowRun > measuredNarrowRightRect.width
      && w.getComputedStyle(measuredNarrowRightBank).justifyContent === 'flex-start'
      && w.getComputedStyle(measuredNarrowRightBank).overflowX === 'auto');

  measuredWidth = 360;
  installMeasuredGeometry();
  w.dispatchEvent(new w.Event('resize'));

  var groupLauncher = w.document.querySelector('[data-library-popover="group"]');
  var filterLauncher = w.document.querySelector('[data-library-popover="filters"]');
  var groupSelect = w.document.querySelector('[data-library-group]');
  groupSelect.value = 'source';
  groupSelect.dispatchEvent(new w.Event('change', { bubbles: true }));
  libraryTypeFilter.value = 'Dialogue';
  libraryTypeFilter.dispatchEvent(new w.Event('change', { bubbles: true }));
  groupLauncher.focus();
  groupLauncher.click();
  var groupReachable = !w.document.querySelector('[data-library-panel="group"]').hidden
    && w.document.activeElement === groupSelect;
  groupLauncher.click();
  filterLauncher.focus();
  filterLauncher.click();
  record('narrow Group and Filters launchers retain state, counts, and keyboard reachability',
    library.dataset.layout === 'narrow'
      && groupLauncher.tagName === 'BUTTON'
      && filterLauncher.tagName === 'BUTTON'
      && groupLauncher.textContent.indexOf('Source') !== -1
      && filterLauncher.textContent.indexOf('Scope: ora · 1') !== -1
      && groupReachable
      && !w.document.querySelector('[data-library-panel="filters"]').hidden
      && w.document.activeElement === libraryTypeFilter);
  filterLauncher.click();
  groupSelect.value = 'none';
  groupSelect.dispatchEvent(new w.Event('change', { bubbles: true }));
  w.document.querySelector('[data-library-command="clear-filters"]').click();

  var denseRows = Array.from({ length: 100 }, function (_, index) {
    return libraryRow('dialogues:dense-' + index, 'dialogues', 'Dense row ' + index);
  });
  queuedLibraryResponses.push(libraryPayload(denseRows, { total: 100 }));
  await w.OraLibraryWorkspace.refresh();
  await new Promise(function (resolve) { w.requestAnimationFrame(resolve); });
  var visibleDenseNodes = w.document.querySelectorAll(
    '.library-visual-node:not(.library-visual-node--related):not([hidden])'
  ).length;
  record('dense Visual uses truthful measured capacity while retaining every row in List',
    visibleDenseNodes > 0
      && visibleDenseNodes < 100
      && visualPlacementIsSafe()
      && w.document.querySelector('.library-visual-capacity-state').textContent
        .indexOf('All current result rows remain available in List') !== -1);
  w.document.querySelector('[data-library-view="list"]').click();
  record('dense Visual consolidation does not remove canonical List rows',
    w.document.querySelectorAll('.library-list-row').length === 100);

  // Return to List before source changes.
  var filesToggle = w.document.querySelector('[data-library-source][value="files"]');
  queuedLibraryResponses.push(libraryPayload([visibleDialogue, metadataDialogue], {
    sources: ['dialogues', 'engrams'], total: 2,
  }));
  filesToggle.checked = false;
  filesToggle.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush();
  await flush();
  var mixedParams = new w.URL(
    libraryRequestUrls[libraryRequestUrls.length - 1], w.location.href
  ).searchParams;
  record('Dialogues plus Engrams is a first-class mixed source request',
    mixedParams.getAll('source').join(',') === 'dialogues,engrams'
      && !mixedParams.getAll('source').includes('files'));

  queuedLibraryResponses.push(libraryPayload([visibleDialogue, metadataDialogue], {
    sources: ['dialogues', 'engrams'], total: 2,
  }));
  projectScope.value = 'ora';
  projectScope.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush();
  await flush();
  var namedScopeParams = new w.URL(
    libraryRequestUrls[libraryRequestUrls.length - 1], w.location.href
  ).searchParams;
  record('one named project scopes the complete mixed-source request server-side',
    projectScope.tagName === 'SELECT'
      && !projectScope.parentElement.querySelector('input[type="checkbox"]')
      && w.OraLibraryWorkspace.getState().projectId === 'ora'
      && namedScopeParams.get('project_id') === 'ora'
      && namedScopeParams.getAll('source').join(',') === 'dialogues,engrams');
  queuedLibraryResponses.push(libraryPayload([visibleDialogue, contextEngram], {
    sources: ['dialogues', 'engrams'], total: 2,
  }));
  projectScope.value = 'commons';
  projectScope.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush();
  await flush();
  var commonsScopeParams = new w.URL(
    libraryRequestUrls[libraryRequestUrls.length - 1], w.location.href
  ).searchParams;
  record('Commons is the universal scope sentinel and is not sent as ordinary membership',
    w.OraLibraryWorkspace.getState().projectId === 'commons'
      && !commonsScopeParams.has('project_id')
      && commonsScopeParams.getAll('source').join(',') === 'dialogues,engrams');

  Array.from(w.document.querySelectorAll('.library-list-row input[type="checkbox"]')).forEach(function (checkbox) {
    checkbox.checked = true;
    checkbox.dispatchEvent(new w.Event('change', { bubbles: true }));
  });
  w.document.querySelector('[data-library-action="new-dialogue"]').click();
  await flush();
  creationDescription = w.document.querySelector('.conversation-create-description');
  creationDescription.value = 'Use checked Commons context without a project filter.';
  creationDescription.dispatchEvent(new w.Event('input', { bubbles: true }));
  w.document.querySelector('.conversation-create-discover').click();
  await flush();
  await flush();
  var commonsCreationParams = new w.URL(
    browserRequestUrls[browserRequestUrls.length - 1], w.location.href
  ).searchParams;
  record('Commons checked-context discovery omits project_id while retaining repeated refs',
    !commonsCreationParams.has('project_id')
      && commonsCreationParams.getAll('include_ref').sort().join(',') === 'engram:claim,named-live');
  w.document.querySelector('.conversation-create-close').click();
  browseButton.click();
  await flush();
  await flush();

  var older = deferredResponse();
  var newer = deferredResponse();
  queuedLibraryResponses.push(older, newer);
  var olderPromise = w.OraLibraryWorkspace.refresh();
  var newerPromise = w.OraLibraryWorkspace.refresh();
  record('a newer Library request aborts the older generation',
    !!(older.options && older.options.signal && older.options.signal.aborted));
  newer.resolve(libraryPayload([
    libraryRow('dialogues:newer', 'dialogues', 'Newer authoritative row'),
  ], { sources: ['dialogues', 'engrams'] }));
  await newerPromise;
  older.resolve(libraryPayload([
    libraryRow('dialogues:older', 'dialogues', 'Older stale row'),
  ], { sources: ['dialogues', 'engrams'] }));
  await olderPromise;
  await flush();
  record('late request completion cannot overwrite newer canonical results',
    w.document.querySelector('.library-list-row__pin').textContent
      .indexOf('Newer authoritative row') !== -1
      && w.OraLibraryWorkspace.getState().requestGeneration > 0
      && w.OraLibraryWorkspace.getState().renderGeneration > 0);

  var dialogueToggle = w.document.querySelector('[data-library-source][value="dialogues"]');
  var engramToggle = w.document.querySelector('[data-library-source][value="engrams"]');
  queuedLibraryResponses.push(libraryPayload([
    libraryRow('engrams:only', 'engrams', 'Engram only'),
  ], { sources: ['engrams'], source_counts: { dialogues: 0, engrams: 1, files: 0 } }));
  dialogueToggle.checked = false;
  dialogueToggle.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush();
  var requestsBeforeZero = libraryRequestUrls.length;
  engramToggle.checked = false;
  engramToggle.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush();
  record('zero sources is a local honest empty state and never falls through to server default-all',
    libraryRequestUrls.length === requestsBeforeZero
      && w.OraLibraryWorkspace.getState().sources.length === 0
      && w.document.querySelector('.library-empty-state').textContent.indexOf('No sources') !== -1);

  w.document.querySelector('.left-sidebar').classList.add('expanded');
  w.document.body.classList.add('sidebar-expanded');
  browseButton.focus();
  w.document.querySelector('[data-library-command="close"]').click();
  browseButton.click();
  await flush();
  await w.OraLibraryWorkspace.refresh();
  record('close, reopen, and refresh remain local when zero sources are selected',
    !library.hidden
      && libraryRequestUrls.length === requestsBeforeZero
      && w.OraLibraryWorkspace.getState().sources.length === 0
      && w.document.querySelector('.library-empty-state').textContent.indexOf('No sources') !== -1);
  w.document.querySelector('.left-sidebar').classList.add('expanded');
  w.document.body.classList.add('sidebar-expanded');
  browseButton.focus();
  w.document.querySelector('[data-library-command="close"]').click();
  record('close restores Submit semantics, exact upper ownership, and opener focus',
    library.hidden
      && w.document.getElementById('logo-o').getAttribute('aria-label') === 'Submit'
      && !w.document.querySelector('.input-pane').hasAttribute('inert')
      && !w.document.getElementById('chatZone').hasAttribute('inert')
      && w.document.activeElement === browseButton);
  browseButton.click();
  await flush();
  w.document.querySelector('.left-sidebar').classList.remove('expanded');
  w.document.body.classList.remove('sidebar-expanded');
  browseButton.hidden = true;
  w.document.querySelector('[data-library-command="close"]').click();
  record('close hands focus to the visible sidebar opener when the original Library button collapsed',
    library.hidden
      && w.document.activeElement === w.document.getElementById('sidebarDashExpand'));
  browseButton.hidden = false;
  record('close restores the decorative wordmark letters exactly',
    w.getComputedStyle(logoR).visibility === logoPresentationBefore.rVisibility
      && w.getComputedStyle(logoR).pointerEvents === logoPresentationBefore.rPointerEvents
      && w.getComputedStyle(logoA).visibility === logoPresentationBefore.aVisibility
      && w.getComputedStyle(logoA).pointerEvents === logoPresentationBefore.aPointerEvents);
  record('lower Findings and Exhibits DOM survives Library preview ownership unchanged',
    preservedFinding.isConnected
      && preservedFinding.parentElement === w.document.querySelector('.output-content')
      && preservedFinding.textContent === 'Preserved finding'
      && preservedExhibit.isConnected
      && preservedExhibit.parentElement === w.document.querySelector('.right-pane')
      && preservedExhibit.textContent === 'Preserved exhibit'
      && !w.document.querySelector('.library-preview-layer'));

  var containsPrivateDialogue = Object.assign({}, visibleDialogue, {
    metadata: Object.assign({}, visibleDialogue.metadata, { privacy: 'contains_private' }),
  });
  await w.OraSidebar.forkLibraryDialogue(containsPrivateDialogue);
  record('Library Fork omits tag so the server inherits authoritative parent privacy',
    forkRequestBodies.length > 0
      && !Object.prototype.hasOwnProperty.call(forkRequestBodies[forkRequestBodies.length - 1], 'tag'));

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
