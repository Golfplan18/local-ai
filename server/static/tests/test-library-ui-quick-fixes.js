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
var DOCUMENT_TEST_NODE_MODULES = path.resolve(__dirname, '..', '..', 'document-surface', 'node_modules');
var JSDOM_PATH = path.join(process.env.COMPILER_TEST_NODE_MODULES
  || (fs.existsSync(path.join(DOCUMENT_TEST_NODE_MODULES, 'jsdom'))
    ? DOCUMENT_TEST_NODE_MODULES : COMPILER_TEST_NODE_MODULES), 'jsdom');
var jsdom;
try {
  jsdom = require(JSDOM_PATH);
} catch (e) {
  console.error('error: jsdom not available at ' + JSDOM_PATH + ': ' + e.message);
  process.exit(2);
}

var indexSource = fs.readFileSync(path.resolve(__dirname, '..', '..', 'index-v3.html'), 'utf8');
var libraryMountMatch = indexSource.match(
  /<section id="libraryWorkspace"[\s\S]*?<\/section>/
);
if (!libraryMountMatch) {
  console.error('error: stable Knowledge Library mount is missing from index-v3.html');
  process.exit(2);
}
var libraryMountMarkup = libraryMountMatch[0];
var overviewLauncherMarkup = indexSource.match(
  /<button class="sidebar-dash-icon overview-desktop-launcher"[\s\S]*?<\/button>/
)[0];
var overviewMountMarkup = indexSource.match(
  /<section class="overview-desktop" id="overviewDesktop"[\s\S]*?<\/section>/
)[0];
var overviewStatusMarkup = indexSource.match(
  /<p class="overview-desktop__status" id="overviewDesktopStatus"[\s\S]*?<\/p>/
)[0];

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body>' +
  '<div class="left-sidebar">' +
  '  <div class="sidebar-collapsed-dashboard">' +
  '    <button id="sidebarDashExpand" aria-label="Expand Dialogues sidebar">Expand</button>' +
  '    <button id="sidebarDashProject">Projects</button>' +
  '    <button id="sidebarDashModel">Model</button>' +
  '    <button id="sidebarDashOutputStyle">Output Style</button>' +
  overviewLauncherMarkup +
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
  overviewMountMarkup + overviewStatusMarkup +
  '</body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
);

var w = dom.window;
w.TextEncoder = require('node:util').TextEncoder;
w.TextDecoder = require('node:util').TextDecoder;
w.ShadowRoot.prototype.getSelection = function () { return w.getSelection(); };
// jsdom does not implement the browser's contenteditable inheritance getter.
Object.defineProperty(w.HTMLElement.prototype, 'isContentEditable', { get: function () {
  var editable = this.closest('[contenteditable]');
  return !!editable && editable.getAttribute('contenteditable') !== 'false';
} });
w.document.execCommand = function () { return false; };
w.Range.prototype.getClientRects = function () { return []; };
w.Range.prototype.getBoundingClientRect = function () {
  return { left: 0, right: 0, top: 0, bottom: 0, width: 0, height: 0 };
};
var EditorView = require(path.join(DOCUMENT_TEST_NODE_MODULES, '@codemirror/view')).EditorView;
function draftView(host) {
  var shell = host && host.querySelector('.ora-document-editor');
  return shell && EditorView.findFromDOM(shell.shadowRoot.querySelector('.cm-content'));
}
function replaceDraft(host, text) {
  var view = draftView(host);
  view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text }, userEvent: 'input.type' });
}
var nativeAnchorHandoffs = [];
w.HTMLAnchorElement.prototype.click = function () {
  nativeAnchorHandoffs.push({
    tagName: this.tagName,
    href: this.getAttribute('href'),
  });
};
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
var previewRequestUrls = [];
var queuedEditResponses = [];
var editRequests = [];
var queuedRevealResponses = [];
var revealRequests = [];
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
    provenance: options.provenance || {
      available: true, kind: source, identity: id, reason: null,
    },
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
  var reject;
  var item = {
    promise: new Promise(function (done, fail) { resolve = done; reject = fail; }),
    options: null,
    resolve: function (payload, status, headerValues) {
      resolve(responseObject(true, payload, status || 200, headerValues));
    },
    resolveError: function (payload, status) {
      resolve(responseObject(false, payload, status || 500));
    },
    reject: function (error) { reject(error); },
  };
  return item;
}

w.fetch = function (url, opts) {
  var decoded = decodeURIComponent(String(url));
  if (decoded === '/api/overview') {
    return response(true, { sources: ['project-priority', 'oversight', 'triggers'].map(function (sourceId) {
      return { source_id: sourceId, title: sourceId, state: 'empty', available: true, count: 0, items: [] };
    }).concat([{
      source_id: 'daily-note', title: 'Prior-day Daily Note', state: 'ready', available: true,
      count: 1, items: [{
        source_id: 'daily-note', item_id: 'daily-note:2026-08-31', title: '2026-08-31',
        state: 'available', text: 'Daily fixture preview', actions: ['read_note', 'open_note'],
      }],
    }]) });
  }
  if (decoded === '/api/overview/daily-note/read?id=daily-note:2026-08-31') {
    return response(true, { id: 'daily-note:2026-08-31', source: 'daily-note', text: '# Daily fixture' });
  }
  if (decoded === '/api/fs/reveal') {
    revealRequests.push({ url: decoded, method: opts.method, body: JSON.parse(opts.body) });
    var queuedReveal = queuedRevealResponses.shift() || { payload: { ok: true } };
    return response(queuedReveal.ok !== false,
      queuedReveal.payload || queuedReveal, queuedReveal.status);
  }
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
    previewRequestUrls.push(decoded);
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
      if (queuedLibrary && queuedLibrary.stream) return Promise.resolve(queuedLibrary.stream);
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

loadScript('keyboard-shortcuts.js');
loadScript('js/sidebar.js');
loadScript('js/v3-state.js');
loadScript('js/v3-conversation.js');
loadScript('vendor/document-surface/ora-document-surface.js');
loadScript('js/library-workspace.js');
loadScript('js/overview-desktop.js');
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
  var contextFileObsidianUri = 'obsidian://open?vault=Wisdom%20Nexus&file=Projects%2FOra%2FProject%20image.png';
  var contextEngram = libraryRow(
    'engrams:claim', 'engrams', 'Atomic Claim Title', {
      metadata: { item_type: 'Engram', tags: ['atomic'] },
      preview: {
        kind: 'text', route: 'text-pane', available: true, reason: null,
        locator: { obsidian_uri: contextFileObsidianUri },
      },
    }
  );
  var nonAtomicEngram = libraryRow(
    'engrams:reference', 'engrams', 'Reference Engram', {
      metadata: { item_type: 'Engram', tags: ['reference'] },
    }
  );
  var contextFilePath = '/Users/oracle/Documents/vault/Projects/Ora/Project image.png';
  var contextFile = libraryRow(
    'files:project-image', 'files', 'Project image.png', {
      metadata: { item_type: 'File', privacy: 'private', content_type: 'image/png' },
      preview: {
        kind: 'visual', route: 'visual-pane', available: true, reason: null,
        locator: {},
      },
    }
  );
  var nestedFolderFile = libraryRow(
    'files:research-brief', 'files', 'Research brief.md', {
      metadata: { item_type: 'File' },
      provenance: {
        available: true, kind: 'files', identity: 'files:research-brief', reason: null,
        details: { relative_path: 'Research/2026/Research brief.md' },
      },
    }
  );
  var windowsFolderFile = libraryRow(
    'files:archive-memo', 'files', 'Archive memo.md', {
      metadata: { item_type: 'File', content_type: '' },
      provenance: {
        available: true, kind: 'files', identity: 'files:archive-memo', reason: null,
        details: { relative_path: 'Notes\\Archive\\Archive memo.md' },
      },
    }
  );
  var projectRootFile = libraryRow(
    'files:readme', 'files', 'README.md', {
      metadata: { item_type: 'File' },
      provenance: {
        available: true, kind: 'files', identity: 'files:readme', reason: null,
        details: { relative_path: 'README.md' },
      },
    }
  );
  delete projectRootFile.metadata.content_type;
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
  queuedLibraryResponses.push(libraryPayload([visibleDialogue, metadataDialogue], { item_type_counts: { Dialogue: 2 } }));
  libraryTypeFilter.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush(); await flush();
  record('Type refinement asks the server to qualify the full universe before paging',
    typeOptions.indexOf('Dialogue') !== -1
      && typeOptions.indexOf('text/markdown') === -1
      && new w.URL(libraryRequestUrls[libraryRequestUrls.length - 1], w.location.href).searchParams.get('item_type') === 'Dialogue'
      && w.document.querySelectorAll('.library-list-row').length === 2);
  queuedLibraryResponses.push(libraryPayload([], {
    total: 0,
    source_counts: { dialogues: 0, engrams: 0, files: 0 },
    item_type_counts: {},
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
  queuedLibraryResponses.push(libraryPayload([visibleDialogue, metadataDialogue, contextEngram, nonAtomicEngram, contextFile], {
    item_type_counts: { Dialogue: 2, Engram: 2, File: 1 },
  }));
  w.document.querySelector('[data-library-command="clear-filters"]').click();
  await flush(); await flush();

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
  queuedLibraryResponses.push(libraryPayload(scopeMixedRows, { item_type_counts: { Dialogue: 2, Engram: 2 } }));
  libraryTypeFilter.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush(); await flush();
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
  record('text body Read renders Markdown safely and preserves active Dialogue, draft, and lower owners',
    !!renderedPreviewBody
      && renderedPreviewBody.querySelector('h1').textContent === 'Atomic Claim Title'
      && renderedPreviewBody.querySelector('strong').textContent === 'older pin preview'
      && renderedPreviewBody.textContent.includes('<em>literal HTML</em>')
      && renderedPreviewBody.querySelector('em') === null
      && w.OraConversation.getActiveConversationId() === activeDialogueBeforePreview
      && inquiryDraft.value === 'Composer draft survives Library preview'
      && preservedFinding.parentElement === w.document.querySelector('.output-content')
      && preservedExhibit.parentElement === w.document.querySelector('.right-pane'));
  record('a non-File row exposes no Open in Obsidian action even if its locator carries a URI',
    !w.document.querySelector('[data-library-action="open-obsidian"]'));

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
  record('eligible Markdown Edit mounts the real CodeMirror with complete text, Save and Cancel',
    !!editDraft
      && editDraft.querySelector('textarea') === null
      && draftView(editDraft).state.doc.toString() === rawMarkdownLf
      && !!w.document.querySelector('[data-library-edit="save"]')
      && !!w.document.querySelector('[data-library-edit="cancel"]')
      && new w.URL(editRequests[editRequests.length - 1].url, w.location.href)
        .searchParams.get('id') === contextEngram.id);
  var cancelledShell = editDraft.querySelector('.ora-document-editor');

  // Exercise the delivered global handlers, including Settings' capture
  // listener, with events that actually cross CodeMirror's shadow boundary.
  var settingsStub = w.OraSettingsPanel;
  loadScript('settings-panel.js');
  w.OraSettingsPanel.init();
  loadScript('js/v3-toolbar-selector.js');
  function keyOn(target, key, modifiers) {
    var event = new w.KeyboardEvent('keydown', Object.assign({
      key: key, bubbles: true, composed: true, cancelable: true,
    }, modifiers || {}));
    target.dispatchEvent(event);
    return event;
  }
  var keyboardView = draftView(editDraft);
  keyboardView.focus();
  var helpKey = keyOn(keyboardView.contentDOM, '?', { code: 'Slash', shiftKey: true });
  var toolbarKey = keyOn(keyboardView.contentDOM, 'T', { code: 'KeyT', shiftKey: true });
  var newDialogueKey = keyOn(keyboardView.contentDOM, 'j', { code: 'KeyJ', ctrlKey: true });
  record('composed typing keys cannot open Settings, toolbars, or New Dialogue through delivered handlers',
    !helpKey.defaultPrevented && !toolbarKey.defaultPrevented && !newDialogueKey.defaultPrevented
      && !w.OraSettingsPanel.getState().open && !w.OraV3ToolbarSelector.isOpen()
      && !w.document.querySelector('.conversation-create-overlay.is-open')
      && w.OraLibraryWorkspace.isOpen() && draftView(editDraft) === keyboardView
      && keyboardView.root.activeElement === keyboardView.contentDOM
      && keyboardView.state.doc.toString() === rawMarkdownLf);
  // Verify the same installed handlers remain functional away from typing.
  var helpOutside = keyOn(browseButton, '?', { code: 'Slash', shiftKey: true });
  record('delivered Settings capture shortcut still opens shortcut help outside the editor',
    helpOutside.defaultPrevented && w.OraSettingsPanel.getState().open
      && w.OraSettingsPanel.getState().activeTab === 'shortcuts');
  w.OraSettingsPanel.close();
  var toolbarOutside = keyOn(browseButton, 'T', { code: 'KeyT', shiftKey: true });
  record('delivered toolbar shortcut still opens outside the editor',
    toolbarOutside.defaultPrevented && w.OraV3ToolbarSelector.isOpen());
  w.OraV3ToolbarSelector.close();
  w.OraSettingsPanel = settingsStub;

  replaceDraft(editDraft, 'Cancelled draft');
  queuedPreviewResponses.push({
    id: contextEngram.id, source: 'engrams', text: currentBody,
  });
  w.document.querySelector('[data-library-edit="cancel"]').click();
  await flush();
  await flush();
  record('Cancel refetches the current preview without writing or restoring the older pin text',
    !w.document.querySelector('[data-library-edit-draft]')
      && !cancelledShell.isConnected
      && w.document.querySelector('.library-preview-body strong').textContent === 'newer current Markdown'
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
  replaceDraft(editDraft, savedRawMarkdown);
  var originalView = draftView(editDraft);
  originalView.dispatch({ selection: { anchor: 7 } });
  originalView.focus();
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
      && conflictedDraft === editDraft
      && draftView(conflictedDraft) === originalView
      && originalView.state.doc.toString() === savedRawMarkdown
      && originalView.state.selection.main.anchor === 7
      && originalView.root.activeElement === originalView.contentDOM
      && w.document.querySelector('[data-library-edit-status]').textContent
        .indexOf('draft is still here') !== -1
      && Object.keys(conflictRequest.body).sort().join(',') === 'expected_digest,id,text'
      && conflictRequest.body.id === contextEngram.id
      && conflictRequest.body.expected_digest === editDigest
      && conflictRequest.body.text
        === savedRawMarkdown.replace(/\n/g, '\r\n'));

  var saveButton = w.document.querySelector('[data-library-edit="save"]');
  var cancelButton = w.document.querySelector('[data-library-edit="cancel"]');
  for (var focusTarget of [originalView.contentDOM, saveButton, cancelButton]) {
    focusTarget.focus();
    var focusLabel = focusTarget === originalView.contentDOM ? 'editor' : focusTarget.textContent;
    var editorRefresh = deferredResponse();
    var editorPreview = deferredResponse();
    var editorRelated = deferredResponse();
    queuedLibraryResponses.push(editorRefresh);
    queuedPreviewResponses.push(editorPreview);
    queuedRelatedResponses.push(editorRelated);
    var editorRefreshPromise = w.OraLibraryWorkspace.refresh();
    record('starting a same-row refresh preserves focused ' + focusLabel,
      focusTarget.isConnected && focusTarget.getRootNode().activeElement === focusTarget);
    editorRefresh.resolve(libraryPayload([
      visibleDialogue, metadataDialogue, contextEngram, nonAtomicEngram, contextFile,
    ], { total: 5, source_counts: { dialogues: 2, engrams: 2, files: 1 } }));
    await editorRefreshPromise;
    editorPreview.resolve({ id: contextEngram.id, source: 'engrams', text: 'New canonical preview must not replace the draft' });
    editorRelated.resolve({ rows: [], total: 0 });
    await flush(); await flush();
    record('same-row refresh and relationship/status updates preserve the draft and focused ' + focusLabel,
      draftView(editDraft) === originalView
        && originalView.state.doc.toString() === savedRawMarkdown
        && originalView.state.selection.main.anchor === 7
        && saveButton === w.document.querySelector('[data-library-edit="save"]')
        && cancelButton === w.document.querySelector('[data-library-edit="cancel"]')
        && focusTarget.getRootNode().activeElement === focusTarget);
  }

  var pendingSave = deferredResponse();
  queuedEditResponses.push(pendingSave);
  var beforeDuplicate = editRequests.length;
  saveButton.focus();
  saveButton.click();
  saveButton.click();
  w.document.querySelector('[data-library-edit="save"]').click();
  record('pending Save preserves its focused control, disables the same editor and prevents duplicate PUTs',
    editRequests.length === beforeDuplicate + 1
      && editRequests[editRequests.length - 1].method === 'PUT'
      && draftView(editDraft) === originalView
      && saveButton === w.document.querySelector('[data-library-edit="save"]')
      && saveButton.getAttribute('aria-disabled') === 'true' && !saveButton.disabled
      && saveButton.textContent === 'Saving…' && w.document.activeElement === saveButton
      && originalView.contentDOM.getAttribute('contenteditable') === 'false');
  pendingSave.resolve({ id: contextEngram.id, source: 'engrams', saved: true });
  await flush(); await flush();
  record('malformed save success preserves Save focus, leaves the draft usable and reports an unknown outcome',
    draftView(editDraft) === originalView
      && originalView.state.doc.toString() === savedRawMarkdown
      && saveButton.getAttribute('aria-disabled') === 'false' && saveButton.textContent === 'Save'
      && w.document.activeElement === saveButton
      && originalView.contentDOM.getAttribute('contenteditable') === 'true'
      && w.document.querySelector('[data-library-edit-status]').textContent.includes('outcome is unknown'));

  var transportSave = deferredResponse();
  queuedEditResponses.push(transportSave);
  w.document.querySelector('[data-library-edit="save"]').click();
  cancelButton.focus();
  transportSave.reject(new Error('simulated connection loss'));
  await flush(); await flush();
  record('transport failure preserves newer Cancel focus, the draft and digest without claiming no write',
    draftView(editDraft) === originalView
      && originalView.state.doc.toString() === savedRawMarkdown
      && w.document.activeElement === cancelButton && cancelButton.isConnected
      && editRequests[editRequests.length - 1].body.expected_digest === editDigest
      && w.document.querySelector('[data-library-edit-status]').textContent.includes('outcome is unknown')
      && !w.document.querySelector('[data-library-edit-status]').textContent.includes('Nothing was written'));

  var timeoutSave = deferredResponse();
  queuedEditResponses.push(timeoutSave);
  var normalSetTimeout = w.setTimeout;
  var saveTimeout;
  w.setTimeout = function (callback, delay) {
    if (delay === 30000) { saveTimeout = callback; return -1; }
    return normalSetTimeout.apply(w, arguments);
  };
  w.document.querySelector('[data-library-edit="save"]').click();
  w.setTimeout = normalSetTimeout;
  saveTimeout();
  timeoutSave.reject(new w.DOMException('Aborted', 'AbortError'));
  await flush(); await flush();
  record('save timeout aborts the request while retaining the editor and an honest unknown outcome',
    timeoutSave.options.signal.aborted
      && draftView(editDraft) === originalView
      && w.document.activeElement === cancelButton
      && originalView.state.doc.toString() === savedRawMarkdown
      && w.document.querySelector('[data-library-edit-status]').textContent.includes('timed out')
      && w.document.querySelector('[data-library-edit-status]').textContent.includes('outcome is unknown'));

  queuedEditResponses.push({ ok: false, status: 409, payload: { error: 'Current source is no longer editable', saved: false } });
  saveButton.focus();
  w.document.querySelector('[data-library-edit="save"]').click();
  await flush(); await flush();
  originalView.contentDOM.dispatchEvent(new w.KeyboardEvent('keydown', {
    key: 'z', code: 'KeyZ', ctrlKey: true, bubbles: true, cancelable: true,
  }));
  record('authority refusal retains undo history and complete original text in the same editor',
    draftView(editDraft) === originalView
      && w.document.activeElement === saveButton
      && originalView.state.doc.toString() === rawMarkdownLf
      && w.document.querySelector('[data-library-edit-status]').textContent.includes('Nothing was written'));
  replaceDraft(editDraft, savedRawMarkdown);

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
      && bodyWhileRefreshPending.querySelector('strong').textContent === 'edited Markdown'
      && !!failedBodyRefresh.options
      && failedBodyRefresh.options.signal.aborted === false);
  failedBodyRefresh.resolveError({ error: 'replacement failed' }, 503);
  await failedBodyRefreshPromise;
  await flush();
  var bodyAfterRefreshFailure = w.document.querySelector('.library-preview-body');
  record('failed same-scope replacement keeps the settled text body visible',
    !!bodyAfterRefreshFailure
      && bodyAfterRefreshFailure.querySelector('strong').textContent === 'edited Markdown'
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
      && bodyAfterRefreshSuccess.textContent.trim() === freshBody);

  async function pinCurrentEngram() {
    queuedPreviewResponses.push({ id: contextEngram.id, source: 'engrams', text: freshBody });
    Array.from(w.document.querySelectorAll('.library-list-row__pin')).find(function (button) {
      return button.textContent.includes('Atomic Claim Title');
    }).click();
    await flush(); await flush();
  }
  async function openCurrentEngram() {
    await pinCurrentEngram();
    queuedEditResponses.push({ id: contextEngram.id, source: 'engrams', text: rawMarkdown, digest: editDigest });
    w.document.querySelector('[data-library-edit="start"]').click();
    await flush(); await flush();
    return w.document.querySelector('.ora-document-editor');
  }
  var savedSurface = w.OraDocumentSurface;
  w.OraDocumentSurface = undefined;
  var normalConsoleError = console.error;
  console.error = function () {};
  await pinCurrentEngram();
  console.error = normalConsoleError;
  record('a missing bundle retains the complete literal preview and visibly disables Edit',
    w.document.querySelector('.ora-document-literal').textContent === freshBody
      && w.document.querySelector('[data-library-edit="start"]').disabled
      && !w.document.querySelector('[data-library-edit-draft]'));
  w.OraDocumentSurface = savedSurface;
  var innerHtmlDescriptor = Object.getOwnPropertyDescriptor(w.Element.prototype, 'innerHTML');
  Object.defineProperty(w.Element.prototype, 'innerHTML', { configurable: true,
    get: innerHtmlDescriptor.get, set: function (value) {
      if (this.className === 'ora-document-read') throw new Error('simulated rendered Read failure');
      return innerHtmlDescriptor.set.call(this, value);
    } });
  console.error = function () {};
  await pinCurrentEngram();
  console.error = normalConsoleError;
  Object.defineProperty(w.Element.prototype, 'innerHTML', innerHtmlDescriptor);
  record('a renderer failure leaves literal Read available and disables Edit without a textarea fallback',
    w.document.querySelector('.ora-document-literal').textContent === freshBody
      && w.document.querySelector('[data-library-edit="start"]').disabled
      && !w.document.querySelector('.library-preview-document textarea'));

  var indexedShell = await openCurrentEngram();
  var overviewDraftHost = w.document.querySelector('[data-library-edit-draft]');
  var overviewDraft = draftView(overviewDraftHost);
  replaceDraft(overviewDraftHost, 'Unsaved Library draft beneath Overview');
  overviewDraft.dispatch({ selection: { anchor: 8 } });
  var returnControl = w.document.querySelector('[data-library-edit="save"]');
  for (var returnCase of [
    { target: returnControl, close: 'Escape' },
    { target: overviewDraft.contentDOM, close: 'Close' },
    { target: overviewDraft.contentDOM, close: 'Escape' },
  ]) {
    returnCase.target.focus();
    var returnLabel = returnCase.target === returnControl ? 'Save' : 'CodeMirror content';
    w.document.getElementById('overviewDesktopOpen').click();
    await flush(); await flush();
    w.document.querySelector('[data-overview-action="read_note"]').click();
    await flush(); await flush();
    var backControl = w.document.querySelector('[data-overview-back]');
    record('Daily reader entered from ' + returnLabel + ' preserves the real Library editor',
      w.document.activeElement === backControl
        && !w.document.getElementById('overviewDailyNoteReader').hidden
        && w.document.getElementById('overviewDailyNoteDocument').querySelector('h1').textContent === 'Daily fixture'
        && draftView(overviewDraftHost) === overviewDraft
        && overviewDraft.state.doc.toString() === 'Unsaved Library draft beneath Overview');
    if (returnCase.close === 'Escape') keyOn(backControl, 'Escape', { code: 'Escape' });
    else w.document.querySelector('[data-overview-close]').click();
    record(returnCase.close + ' returns focus to ' + returnLabel + ' and preserves Library draft, selection and panes',
      w.document.getElementById('overviewDesktop').hidden
        && w.document.getElementById('overviewDailyNoteDocument').childNodes.length === 0
        && w.OraLibraryWorkspace.isOpen() && draftView(overviewDraftHost) === overviewDraft
        && overviewDraft.state.doc.toString() === 'Unsaved Library draft beneath Overview'
        && overviewDraft.state.selection.main.anchor === 8
        && returnCase.target.getRootNode().activeElement === returnCase.target
        && !w.document.querySelector('.ora-shell').hasAttribute('inert')
        && inquiryDraft.value === 'Composer draft survives Library preview'
        && w.OraConversation.getActiveConversationId() === activeDialogueBeforePreview
        && preservedFinding.isConnected && preservedExhibit.isConnected);
  }
  overviewDraft.focus();
  keyOn(overviewDraft.contentDOM, 'z', { code: 'KeyZ', ctrlKey: true });
  record('Library undo history survives the complete Daily-reader Escape lifecycle',
    overviewDraft.state.doc.toString() === rawMarkdownLf);
  queuedEditResponses.push({ id: contextEngram.id, source: 'engrams', saved: true, index_refreshed: true });
  queuedPreviewResponses.push({ id: contextEngram.id, source: 'engrams', text: '# Saved canonical' });
  w.document.querySelector('[data-library-edit="save"]').click();
  await flush(); await flush();
  record('successful saved-and-indexed outcome destroys the editor and returns to a freshly rendered Read',
    !indexedShell.isConnected
      && !w.document.querySelector('[data-library-edit-draft]')
      && w.document.querySelector('.library-preview-body h1').textContent === 'Saved canonical'
      && w.document.querySelector('[data-library-edit-status]').textContent.includes('index refreshed'));

  var repinnedShell = await openCurrentEngram();
  var lateSave = deferredResponse();
  queuedEditResponses.push(lateSave);
  w.document.querySelector('[data-library-edit="save"]').click();
  w.document.querySelector('[data-library-row-id="dialogues:metadata-only"] .library-list-row__pin').click();
  lateSave.resolve({ id: contextEngram.id, source: 'engrams', saved: true, index_refreshed: true });
  await flush(); await flush();
  record('repinning destroys the editor and ignores a late dispatched Save response',
    !repinnedShell.isConnected && lateSave.options.signal.aborted
      && w.OraLibraryWorkspace.getState().pinnedId === metadataDialogue.id
      && !w.document.querySelector('[data-library-edit-draft]')
      && !w.document.querySelector('[data-library-edit-status]'));

  await pinCurrentEngram();
  var lateEdit = deferredResponse();
  queuedEditResponses.push(lateEdit);
  w.document.querySelector('[data-library-edit="start"]').click();
  w.document.querySelector('[data-library-row-id="dialogues:metadata-only"] .library-list-row__pin').click();
  lateEdit.resolve({ id: contextEngram.id, source: 'engrams', text: 'Late edit body', digest: editDigest });
  await flush(); await flush();
  record('repinning aborts and rejects a late authoritative Edit response',
    lateEdit.options.signal.aborted
      && w.OraLibraryWorkspace.getState().pinnedId === metadataDialogue.id
      && !w.document.querySelector('[data-library-edit-draft]'));

  var closedShell = await openCurrentEngram();
  var closeSave = deferredResponse();
  queuedEditResponses.push(closeSave);
  w.document.querySelector('[data-library-edit="save"]').click();
  w.OraLibraryWorkspace.close();
  closeSave.resolve({ id: contextEngram.id, source: 'engrams', saved: true, index_refreshed: true });
  await flush(); await flush();
  record('close destroys the editor, rejects late Save and restores Dialogue, draft and lower panes',
    !closedShell.isConnected && closeSave.options.signal.aborted
      && !w.document.querySelector('.library-preview-layer')
      && !w.document.querySelector('.input-pane').hasAttribute('inert')
      && inquiryDraft.value === 'Composer draft survives Library preview'
      && w.OraConversation.getActiveConversationId() === activeDialogueBeforePreview
      && preservedFinding.isConnected && preservedExhibit.isConnected);
  queuedLibraryResponses.push(libraryPayload([
    visibleDialogue, metadataDialogue, contextEngram, nonAtomicEngram, contextFile,
  ], { total: 5, source_counts: { dialogues: 2, engrams: 2, files: 1 } }));
  w.OraLibraryWorkspace.open({ returnFocus: browseButton });
  await flush(); await flush();

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

  record('a File without a provider locator exposes neither physical action',
    !w.document.querySelector('[data-library-action="reveal"]')
      && !w.document.querySelector('[data-library-action="open-obsidian"]'));
  contextFile.preview.locator = { path: contextFilePath };
  imageCheck.dispatchEvent(new w.Event('change', { bubbles: true }));
  var fileRevealAction = w.document.querySelector('[data-library-action="reveal"]');
  record('Reveal remains available independently when a File has a path but no Obsidian URI',
    !!fileRevealAction
      && !w.document.querySelector('[data-library-action="open-obsidian"]'));
  contextFile.preview.locator.obsidian_uri = contextFileObsidianUri;
  imageCheck.dispatchEvent(new w.Event('change', { bubbles: true }));
  fileRevealAction = w.document.querySelector('[data-library-action="reveal"]');
  var fileObsidianAction = w.document.querySelector('[data-library-action="open-obsidian"]');
  var stateBeforeObsidian = w.OraLibraryWorkspace.getState();
  var noticeBeforeObsidian = {
    hidden: w.document.getElementById('libraryWorkspaceNotice').hidden,
    text: w.document.getElementById('libraryWorkspaceNotice').textContent,
    tone: w.document.getElementById('libraryWorkspaceNotice').getAttribute('data-tone'),
  };
  fileObsidianAction.click();
  await flush();
  var stateAfterObsidian = w.OraLibraryWorkspace.getState();
  var obsidianHandoff = nativeAnchorHandoffs[nativeAnchorHandoffs.length - 1];
  record('Open in Obsidian hands the exact provider URI to a native anchor without claiming acceptance or changing workspace state',
    fileObsidianAction.textContent === 'Open in Obsidian'
      && !!obsidianHandoff
      && obsidianHandoff.tagName === 'A'
      && obsidianHandoff.href === contextFileObsidianUri
      && JSON.stringify(stateAfterObsidian) === JSON.stringify(stateBeforeObsidian)
      && w.document.getElementById('libraryWorkspaceNotice').hidden === noticeBeforeObsidian.hidden
      && w.document.getElementById('libraryWorkspaceNotice').textContent === noticeBeforeObsidian.text
      && w.document.getElementById('libraryWorkspaceNotice').getAttribute('data-tone') === noticeBeforeObsidian.tone
      && w.document.querySelector('.library-preview-image') === exhibitImage
      && w.OraConversation.getActiveConversationId() === activeDialogueBeforePreview
      && inquiryDraft.value === 'Composer draft survives Library preview'
      && preservedFinding.parentElement === w.document.querySelector('.output-content')
      && preservedExhibit.parentElement === w.document.querySelector('.right-pane'));
  var stateBeforeReveal = w.OraLibraryWorkspace.getState();
  queuedRevealResponses.push({ payload: { ok: true, path: contextFilePath } });
  fileRevealAction.click();
  await flush();
  await flush();
  var revealRequest = revealRequests[revealRequests.length - 1];
  var stateAfterReveal = w.OraLibraryWorkspace.getState();
  record('Reveal posts only the authoritative File locator and reports success without changing Library state',
    fileRevealAction.textContent === 'Reveal in Finder'
      && revealRequest.url === '/api/fs/reveal'
      && revealRequest.method === 'POST'
      && Object.keys(revealRequest.body).join(',') === 'path'
      && revealRequest.body.path === contextFilePath
      && w.document.getElementById('libraryWorkspaceNotice').textContent === 'Revealed in Finder.'
      && w.document.getElementById('libraryWorkspaceNotice').dataset.tone === 'success'
      && stateAfterReveal.projectId === stateBeforeReveal.projectId
      && stateAfterReveal.selectedIds.join(',') === stateBeforeReveal.selectedIds.join(',')
      && stateAfterReveal.pinnedId === stateBeforeReveal.pinnedId
      && w.document.querySelector('.library-preview-image') === exhibitImage
      && w.OraConversation.getActiveConversationId() === activeDialogueBeforePreview
      && inquiryDraft.value === 'Composer draft survives Library preview'
      && preservedFinding.parentElement === w.document.querySelector('.output-content')
      && preservedExhibit.parentElement === w.document.querySelector('.right-pane'));

  queuedRevealResponses.push({
    ok: false,
    status: 403,
    payload: { ok: false, error: 'path is outside the allowed folders' },
  });
  fileRevealAction.click();
  await flush();
  await flush();
  record('Reveal surfaces the endpoint refusal through the current Library notice',
    w.document.getElementById('libraryWorkspaceNotice').textContent
      .indexOf('path is outside the allowed folders') !== -1
      && w.document.getElementById('libraryWorkspaceNotice').dataset.tone === 'error');

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
  record('List and Visual retain the pinned inventory node while the native O identifies it',
    w.OraLibraryWorkspace.getState().view === 'visual'
      && w.document.querySelectorAll('.library-visual-node').length === 5
      && !!w.document.querySelector('[data-library-node-id="dialogues:metadata-only"]')
      && w.document.getElementById('logo-o').getAttribute('aria-label').indexOf('Private Dialogue') !== -1);
  record('Visual invents no connector from relationship summaries without endpoints',
    w.document.querySelectorAll('.library-visual-connectors line').length === 0
      && w.document.querySelector('.library-visual-edge-state').textContent
        .indexOf('Related discovery stays below') !== -1);

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
    }) && !w.document.querySelector('[data-library-action="reveal"]'));
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
  record('Related arrival remains in disclosure without replacing inventory or acquiring graph connectors',
    w.document.querySelectorAll('.library-visual-connectors line').length === 0
      && w.document.querySelectorAll('.library-visual-node--related').length === 0
      && w.document.querySelectorAll('.library-visual-node').length === 5
      && visualPlacementIsSafe());
  w.OraLibraryWorkspace.activatePinned();
  record('Related disclosure retains directional labels and keyboard access without graph admission',
    w.document.activeElement.tagName === 'SUMMARY'
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

  var dialogueToggle = w.document.querySelector('[data-library-source][value="dialogues"]');
  var engramToggle = w.document.querySelector('[data-library-source][value="engrams"]');
  var filesToggle = w.document.querySelector('[data-library-source][value="files"]');
  var folderOption = groupSelect.querySelector('option[value="folder"]');
  var contentTypeOption = groupSelect.querySelector('option[value="content-type"]');
  var fileGroupsWereInitiallyUnavailable = folderOption.hidden && folderOption.disabled
    && contentTypeOption.hidden && contentTypeOption.disabled;

  queuedLibraryResponses.push(libraryPayload([contextEngram, nestedFolderFile], {
    sources: ['engrams', 'files'], total: 2,
    source_counts: { dialogues: 0, engrams: 1, files: 1 },
    item_type_counts: { Engram: 1, File: 1 },
  }));
  dialogueToggle.checked = false;
  dialogueToggle.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush();
  await flush();
  queuedLibraryResponses.push(libraryPayload([
    nestedFolderFile, windowsFolderFile, projectRootFile,
  ], {
    sources: ['files'], total: 4, has_more: true, next_offset: 3,
    source_counts: { dialogues: 0, engrams: 0, files: 4 },
    item_type_counts: { File: 4 },
  }));
  engramToggle.checked = false;
  engramToggle.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush();
  await flush();
  groupSelect.value = 'content-type';
  groupSelect.dispatchEvent(new w.Event('change', { bubbles: true }));
  var partialContentTypeList = w.document.querySelectorAll('.library-result-group').length === 0
    && w.document.getElementById('libraryWorkspaceNotice').textContent.indexOf('grouping') !== -1;
  w.document.querySelector('[data-library-view="visual"]').click();
  var partialContentTypeVisual = w.document.querySelector('.library-visual-group-state').textContent
    .indexOf('unavailable until every') !== -1
    && w.document.querySelectorAll('.library-visual-node__group').length === 0;
  w.document.querySelector('[data-library-view="list"]').click();
  record('Files-only groups become available but Content type waits for every page',
    fileGroupsWereInitiallyUnavailable
      && !folderOption.hidden && !folderOption.disabled
      && !contentTypeOption.hidden && !contentTypeOption.disabled
      && w.OraLibraryWorkspace.getState().sources.join(',') === 'files'
      && w.OraLibraryWorkspace.getState().group === 'content-type'
      && partialContentTypeList && partialContentTypeVisual);

  queuedLibraryResponses.push(libraryPayload([contextFile], {
    sources: ['files'], total: 4, offset: 3,
    source_counts: { dialogues: 0, engrams: 0, files: 4 },
    item_type_counts: { File: 4 },
  }));
  w.document.querySelector('[data-library-command="load-all"]').click();
  await flush();
  await flush();
  var contentTypeHeadings = Array.from(w.document.querySelectorAll('.library-result-group h2'))
    .map(function (heading) { return heading.textContent; }).sort();
  w.document.querySelector('[data-library-view="visual"]').click();
  var contentTypeVisualLabels = Array.from(w.document.querySelectorAll('.library-visual-node__group'))
    .map(function (label) { return label.textContent; }).sort();
  record('Content type uses exact File metadata in both views and labels missing values Unavailable',
    contentTypeHeadings.join('|') === ['Unavailable (2)', 'image/png (1)', 'text/markdown (1)'].sort().join('|')
      && contentTypeVisualLabels.join('|') === ['Unavailable', 'Unavailable', 'image/png', 'text/markdown'].sort().join('|')
      && groupLauncher.textContent.indexOf('Content type') !== -1,
    contentTypeHeadings.join(', '));

  w.document.querySelector('[data-library-view="list"]').click();
  groupSelect.value = 'folder';
  groupSelect.dispatchEvent(new w.Event('change', { bubbles: true }));
  var folderHeadings = Array.from(w.document.querySelectorAll('.library-result-group h2'))
    .map(function (heading) { return heading.textContent; });
  var folderListIds = Array.from(w.document.querySelectorAll('.library-list-row'))
    .map(function (row) { return row.dataset.libraryRowId; }).sort();
  w.document.querySelector('[data-library-view="visual"]').click();
  var folderVisualIds = Array.from(w.document.querySelectorAll(
    '.library-visual-node:not(.library-visual-node--related)'
  )).map(function (row) { return row.dataset.libraryNodeId; }).sort();
  var folderVisualLabels = Array.from(w.document.querySelectorAll('.library-visual-node__group'))
    .map(function (label) { return label.textContent; });
  record('Files-only Folder grouping shares full relative and root labels across List and Visual',
    !folderOption.hidden
      && !folderOption.disabled
      && w.OraLibraryWorkspace.getState().sources.join(',') === 'files'
      && w.OraLibraryWorkspace.getState().group === 'folder'
      && groupLauncher.textContent.indexOf('Folder') !== -1
      && folderHeadings.indexOf('Research/2026 (1)') !== -1
      && folderHeadings.indexOf('Notes/Archive (1)') !== -1
      && folderHeadings.indexOf('Project root (1)') !== -1
      && folderVisualIds.join(',') === folderListIds.join(',')
      && folderVisualLabels.indexOf('Research/2026') !== -1
      && folderVisualLabels.indexOf('Notes/Archive') !== -1
      && folderVisualLabels.indexOf('Project root') !== -1,
    folderHeadings.join(', '));

  groupSelect.value = 'content-type';
  groupSelect.dispatchEvent(new w.Event('change', { bubbles: true }));
  libraryTypeFilter.value = 'File';
  libraryTypeFilter.dispatchEvent(new w.Event('change', { bubbles: true }));
  scopeSort.value = 'title';
  scopeSort.dispatchEvent(new w.Event('change', { bubbles: true }));
  queuedLibraryResponses.push(
    libraryPayload([], { sources: ['files'], total: 0 }),
    libraryPayload([
      visibleDialogue, nestedFolderFile, windowsFolderFile, projectRootFile, contextFile,
    ], {
      sources: ['dialogues', 'files'], total: 5,
      source_counts: { dialogues: 1, engrams: 0, files: 4 },
      item_type_counts: { Dialogue: 1, File: 4 },
    })
  );
  librarySearch.value = 'preserve file controls';
  librarySearch.dispatchEvent(new w.Event('input', { bubbles: true }));
  dialogueToggle.checked = true;
  dialogueToggle.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush();
  await flush();
  var repairedGroupState = w.OraLibraryWorkspace.getState();
  record('mixed sources repair Content type to None without resetting other browse controls',
    folderOption.hidden
      && folderOption.disabled
      && contentTypeOption.hidden
      && contentTypeOption.disabled
      && repairedGroupState.group === 'none'
      && repairedGroupState.query === 'preserve file controls'
      && repairedGroupState.filters.type === 'File'
      && repairedGroupState.sort === 'title'
      && new w.URL(libraryRequestUrls[libraryRequestUrls.length - 1], w.location.href)
        .searchParams.get('q') === 'preserve file controls'
      && groupSelect.value === 'none'
      && groupLauncher.textContent.indexOf('None') !== -1);

  queuedLibraryResponses.push(
    libraryPayload([], { sources: ['dialogues', 'files'], total: 0 }),
    libraryPayload([visibleDialogue, contextEngram, contextFile], {
      sources: ['dialogues', 'engrams', 'files'], total: 3,
      source_counts: { dialogues: 1, engrams: 1, files: 1 },
      item_type_counts: { Dialogue: 1, Engram: 1, File: 1 },
    })
  );
  librarySearch.value = '';
  librarySearch.dispatchEvent(new w.Event('input', { bubbles: true }));
  w.document.querySelector('[data-library-command="clear-filters"]').click();
  scopeSort.value = 'recent';
  scopeSort.dispatchEvent(new w.Event('change', { bubbles: true }));
  engramToggle.checked = true;
  engramToggle.dispatchEvent(new w.Event('change', { bubbles: true }));
  await flush();
  await flush();
  w.document.querySelector('[data-library-view="list"]').click();

  // Return to List before source changes.
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

  // L1 completion: the same production controller consumes finite server snapshots.
  function streamFixture() {
    var controller;
    var cancelled = false;
    var body = new ReadableStream({ start(c) { controller = c; }, cancel() { cancelled = true; } });
    return { stream: { ok: true, status: 200, headers: { get() { return 'application/x-ndjson'; } }, body: body },
      send(frame) { controller.enqueue(new TextEncoder().encode(typeof frame === 'string' ? frame : JSON.stringify(frame) + '\n')); },
      end() { controller.close(); }, cancelled() { return cancelled; } };
  }
  function frame(rows, final, options) {
    var data = libraryPayload(rows, options);
    data.progress = { final: final, pending_sources: final ? [] : ['files'], failed_sources: [] };
    return { event: 'snapshot', stage: final ? 'final' : 'engrams', final: final, data: data };
  }
  var traceAnchor = libraryRow('engrams:TjA', 'engrams', 'Trace anchor', { metadata: { item_type: 'engram' } });
  var traceNeighbor = libraryRow('engrams:TjE', 'engrams', 'Trace neighbor', { metadata: { item_type: 'engram' } });
  var progressive = streamFixture();
  queuedLibraryResponses.push(progressive);
  var l1Requests = libraryRequestUrls.length;
  w.OraLibraryWorkspace.open({ sources: ['engrams'], projectId: 'commons' });
  await flush();
  progressive.send(frame([traceAnchor], false));
  await flush(); await flush();
  record('a qualified progressive stage renders before final accounting and disables paging',
    w.OraLibraryWorkspace.getState().loaded === 1 && !w.OraLibraryWorkspace.getState().universeComplete
      && !w.OraLibraryWorkspace.getState().progressFinal && !w.document.querySelector('[data-library-command="load-more"]'));
  w.document.querySelector('[data-library-view="visual"]').click();
  await new Promise(function (resolve) { w.requestAnimationFrame(resolve); });
  var earlyNode = w.document.querySelector('[data-library-node-id="' + traceAnchor.id + '"]');
  var initialPosition = [earlyNode.style.left, earlyNode.style.top].join(':');
  earlyNode.querySelector('input').checked = true;
  earlyNode.querySelector('input').dispatchEvent(new w.Event('change', { bubbles: true }));
  w.document.querySelector('[data-library-node-id="' + traceAnchor.id + '"] .library-visual-node__pin').click();
  await flush(); await flush();
  progressive.send(frame([traceNeighbor, traceAnchor], true));
  progressive.end();
  await flush(); await flush();
  await new Promise(function (resolve) { w.requestAnimationFrame(resolve); });
  var stableNode = w.document.querySelector('[data-library-node-id="' + traceAnchor.id + '"]');
  record('pin, bulk selection and later snapshots retain the original Visual slot',
    initialPosition === [stableNode.style.left, stableNode.style.top].join(':')
      && w.OraLibraryWorkspace.getState().pinnedId === traceAnchor.id
      && w.OraLibraryWorkspace.getState().selectedIds.includes(traceAnchor.id)
      && w.OraLibraryWorkspace.getState().progressFinal);
  w.OraLibraryWorkspace.open();
  record('Sidebar focus-only open makes no duplicate request', libraryRequestUrls.length === l1Requests + 1);
  var traceRows = [traceAnchor];
  for (var neighborIndex = 1; neighborIndex <= 51; neighborIndex += 1) traceRows.push(libraryRow('engrams:T' + neighborIndex, 'engrams', 'Neighbor ' + neighborIndex, { metadata: { item_type: 'engram' } }));
  var traceEdges = traceRows.slice(1, 51).map(function (row, index) { return {
    source: traceAnchor.id, target: row.id, type: index % 2 ? 'requires' : 'supports', family: index % 2 ? 'causal' : 'evidence', confidence: index % 2 ? '0.7' : 'high',
  }; });
  var tracePayload = libraryPayload([traceAnchor, traceNeighbor]);
  tracePayload.trace = { selected_id: traceAnchor.id, rows: traceRows.slice(0, 51), edges: traceEdges, total_neighbors: 51, remaining: 1, state: 'fresh', reason: null };
  queuedLibraryResponses.push(tracePayload);
  w.document.querySelector('[data-library-action="trace"]').click();
  await flush(); await flush();
  record('Trace exposes fifty distinct neighbors, direction, confidence and explicit remainder expansion',
    w.document.querySelectorAll('[data-library-trace-neighbor]').length === 51
      && w.document.querySelector('[data-library-trace-expand]').textContent.includes('1 more')
      && w.document.querySelector('.library-trace').textContent.includes('confidence high')
      && new w.URL(libraryRequestUrls[libraryRequestUrls.length - 1], w.location.href).searchParams.get('trace_limit') === '50');
  var tracedFrom = w.OraLibraryWorkspace.getState().traceId;
  w.document.querySelectorAll('[data-library-trace-neighbor]')[1].click();
  await flush();
  record('reading a neighbor preserves the current Trace context', w.OraLibraryWorkspace.getState().traceId === tracedFrom
    && w.OraLibraryWorkspace.getState().pinnedId === traceRows[1].id);
  var expandedPayload = libraryPayload([traceAnchor]);
  expandedPayload.trace = Object.assign({}, tracePayload.trace, { rows: traceRows, remaining: 0 });
  queuedLibraryResponses.push(expandedPayload);
  w.document.querySelector('[data-library-trace-expand]').click();
  await flush(); await flush();
  record('Trace expansion requests the next fifty and retains the selected neighbor',
    new w.URL(libraryRequestUrls[libraryRequestUrls.length - 1], w.location.href).searchParams.get('trace_limit') === '100'
      && w.document.querySelectorAll('[data-library-trace-neighbor]').length === 52
      && w.OraLibraryWorkspace.getState().pinnedId === traceRows[1].id);
  var premature = streamFixture(); queuedLibraryResponses.push(premature);
  var prematurePromise = w.OraLibraryWorkspace.refresh(); await flush();
  premature.send(frame([traceAnchor], false)); premature.end(); await prematurePromise; await flush();
  record('premature EOF keeps safe results and pin while making incompleteness and retry explicit',
    w.OraLibraryWorkspace.getState().loaded > 0 && !w.OraLibraryWorkspace.getState().universeComplete
      && w.OraLibraryWorkspace.getState().pinnedId === traceRows[1].id
      && w.document.getElementById('libraryWorkspaceNotice').textContent.includes('without final accounting')
      && !!w.document.querySelector('[data-library-command="retry"]'));
  var malformedStream = streamFixture(); queuedLibraryResponses.push(malformedStream);
  var malformedPromise = w.OraLibraryWorkspace.refresh(); await flush();
  malformedStream.send('not JSON\n'); await malformedPromise; await flush();
  record('malformed progress cancels its reader and retains safe rows', malformedStream.cancelled()
    && w.OraLibraryWorkspace.getState().loaded > 0 && !w.OraLibraryWorkspace.getState().progressFinal);
  var archiveDialogue = libraryRow('dialogues:aGlzdG9yeQ', 'dialogues', 'Historical Dialogue', {
    metadata: { lifecycle: 'indexed_archive', item_type: 'dialogue', content_type: 'application/x-ora-dialogue' },
  });
  queuedLibraryResponses.push(libraryPayload([archiveDialogue]));
  w.OraLibraryWorkspace.open({ sources: ['dialogues'], projectId: 'commons' });
  await flush(); await flush();
  var archiveToggle = w.document.querySelector('[data-library-archived]');
  queuedLibraryResponses.push(libraryPayload([archiveDialogue])); archiveToggle.checked = true;
  archiveToggle.dispatchEvent(new w.Event('change', { bubbles: true })); await flush(); await flush();
  queuedPreviewResponses.push({ id: archiveDialogue.id, source: 'dialogues', turns: [
    { role: 'user', content: '# Pretend Ora\n\nUser **source** text' }, { role: 'assistant', content: '# Pretend You\n\nAssistant source text' },
  ] });
  w.document.querySelector('[data-library-view="list"]').click();
  w.document.querySelector('.library-list-row__pin').click(); await flush(); await flush();
  record('Dialogue preview uses fixed external speaker labels and never turns archive reading into Edit or activation',
    Array.from(w.document.querySelectorAll('[data-library-speaker]')).map(function (node) { return node.textContent; }).join(',') === 'You,Ora'
      && w.document.querySelectorAll('.library-dialogue-turn').length === 2
      && !w.document.querySelector('[data-library-edit="start"]')
      && !w.document.querySelector('[data-library-action="continue"]')
      && new w.URL(previewRequestUrls[previewRequestUrls.length - 1], w.location.href).searchParams.get('show_archived') === '1'
      && w.document.querySelector('.library-preview-layer--findings').textContent.includes('read-only'));
  var largeDialogueSource = '## Complete literal source\n' + 'x'.repeat(2 * 1024 * 1024) + '\nFinal source line';
  var originalDialogueSurface = w.OraDocumentSurface;
  var largeDialogueRenderCalls = 0;
  w.OraDocumentSurface = Object.assign({}, originalDialogueSurface, { renderRead: function (options) {
      largeDialogueRenderCalls += 1;
      return originalDialogueSurface.renderRead(options);
    } });
  queuedPreviewResponses.push({ id: archiveDialogue.id, source: 'dialogues', turns: [
    { role: 'user', content: largeDialogueSource }, { role: 'assistant', content: largeDialogueSource },
  ] });
  queuedLibraryResponses.push(libraryPayload([archiveDialogue]));
  await w.OraLibraryWorkspace.refresh(); await flush(); await flush();
  w.OraDocumentSurface = originalDialogueSurface;
  var largeLiteralTurns = Array.from(w.document.querySelectorAll('.library-dialogue-turn .ora-document-literal'));
  record('the aggregate Dialogue formatting bound preserves every turn as speaker-labelled literal source',
    largeDialogueRenderCalls === 0 && largeLiteralTurns.length === 2
      && largeLiteralTurns.every(function (node) { return node.textContent === largeDialogueSource; })
      && Array.from(w.document.querySelectorAll('[data-library-speaker]')).map(function (node) { return node.textContent; }).join(',') === 'You,Ora'
      && largeLiteralTurns.every(function (node) { return node.parentElement.textContent.includes('source text is shown literally'); })
      && !w.document.querySelector('[data-library-edit="start"]'));
  queuedLibraryResponses.push(libraryPayload([]));
  var derivedRequests = libraryRequestUrls.length;
  w.document.querySelector('[data-library-action="derived"]').click(); await flush(); await flush();
  record('derived entry changes one controller scope exactly once and reports absent derivation honestly',
    libraryRequestUrls.length === derivedRequests + 1
      && w.OraLibraryWorkspace.getState().sources.join(',') === 'engrams'
      && w.OraLibraryWorkspace.getState().filters.provenance_id === archiveDialogue.id
      && !w.OraLibraryWorkspace.getState().pinnedId
      && w.document.querySelector('.library-empty-state').textContent.includes('No admitted indexed derivation'));
  queuedLibraryResponses.push(libraryPayload([traceAnchor]));
  var chipRequests = libraryRequestUrls.length;
  w.document.querySelector('[data-library-chip="provenance_id"]').click(); await flush(); await flush();
  record('removing a refinement chip refreshes exactly once', libraryRequestUrls.length === chipRequests + 1
    && !w.OraLibraryWorkspace.getState().filters.provenance_id);
  var invalidEntryRejected = false;
  try { w.OraLibraryWorkspace.open({ sources: ['not-a-source'] }); } catch (error) { invalidEntryRejected = true; }
  record('invalid derived-source entry is rejected without a request or scope mutation', invalidEntryRejected
    && libraryRequestUrls.length === chipRequests + 1);
  queuedLibraryResponses.push(libraryPayload([contextEngram]));
  await w.OraLibraryWorkspace.refresh(); await flush(); await flush();
  w.document.querySelector('.library-list-row__pin').click(); await flush(); await flush();
  queuedEditResponses.push({ id: contextEngram.id, source: 'engrams', text: rawMarkdown, digest: editDigest });
  w.document.querySelector('[data-library-edit="start"]').click(); await flush(); await flush();
  var archiveScopeEditParams = new w.URL(editRequests[editRequests.length - 1].url, w.location.href).searchParams;
  record('archive inclusion preserves eligible current Markdown editing without sending archive read admission to Edit',
    w.OraLibraryWorkspace.getState().showArchived && !!w.document.querySelector('[data-library-edit-draft]')
      && Array.from(archiveScopeEditParams.keys()).join(',') === 'id'
      && archiveScopeEditParams.get('id') === contextEngram.id
      && new w.URL(previewRequestUrls[previewRequestUrls.length - 1], w.location.href).searchParams.get('show_archived') === '1');
  w.document.querySelector('[data-library-edit="cancel"]').click(); await flush(); await flush();
  w.document.querySelector('[data-library-view="visual"]').click();
  record('only the last view is stored, with no source text, filters or history', w.localStorage.getItem('ora.library.last-view') === 'visual');

  // D1 destinations explicitly start a clean browse, including repeated scope.
  var beforeInvalidClean = JSON.stringify(w.OraLibraryWorkspace.getState());
  var requestsBeforeInvalidClean = libraryRequestUrls.length;
  var invalidCleanCount = 0;
  [{ cleanBrowse: 'true' }, { cleanBrowse: true, provenanceId: 'files:c291cmNl' },
    { cleanBrowse: true, projectId: '../ora' }, { cleanBrowse: true, sources: ['missing'] }].forEach(function (options) {
    try { w.OraLibraryWorkspace.open(options); } catch (error) { invalidCleanCount += 1; }
  });
  record('clean entry validates the whole destination before any state or request change', invalidCleanCount === 4
    && JSON.stringify(w.OraLibraryWorkspace.getState()) === beforeInvalidClean
    && libraryRequestUrls.length === requestsBeforeInvalidClean);

  queuedLibraryResponses.push(libraryPayload([contextEngram]));
  w.OraLibraryWorkspace.open({ projectId: 'ora', sources: ['engrams'], provenanceId: 'files:c291cmNl' });
  await flush(); await flush();
  queuedLibraryResponses.push(libraryPayload([contextEngram]));
  librarySearch.value = 'old restriction'; librarySearch.dispatchEvent(new w.Event('input', { bubbles: true }));
  await flush(); await flush();
  w.document.querySelector('[data-library-view="list"]').click();
  var oldSort = w.document.querySelector('[data-library-sort]');
  oldSort.value = 'title'; oldSort.dispatchEvent(new w.Event('change', { bubbles: true }));
  w.document.querySelector('.library-list-row__pin').click(); await flush(); await flush();
  queuedEditResponses.push({ id: contextEngram.id, source: 'engrams', text: rawMarkdown, digest: editDigest });
  w.document.querySelector('[data-library-edit="start"]').click(); await flush(); await flush();
  var cleanSamePending = deferredResponse(); queuedLibraryResponses.push(cleanSamePending);
  var cleanSameRequests = libraryRequestUrls.length;
  w.OraLibraryWorkspace.open({ projectId: 'ora', sources: ['engrams'], cleanBrowse: true });
  var sameClean = w.OraLibraryWorkspace.getState();
  var cleanParams = new w.URL(libraryRequestUrls[libraryRequestUrls.length - 1], w.location.href).searchParams;
  record('same-scope clean browse clears query, provenance, archive, selection, reader and editor before one request',
    libraryRequestUrls.length === cleanSameRequests + 1 && sameClean.query === ''
    && !Object.values(sameClean.filters).some(Boolean) && !sameClean.showArchived && sameClean.group === 'provenance'
    && !sameClean.pinnedId && !sameClean.selectedIds.length && !sameClean.loaded && !sameClean.indexed
    && !sameClean.traceId && !w.document.querySelector('[data-library-edit-draft]')
    && librarySearch.value === '' && !w.document.querySelector('[data-library-chip]')
    && !cleanParams.has('q') && !cleanParams.has('provenance_id') && !cleanParams.has('show_archived')
    && cleanParams.get('project_id') === 'ora' && cleanParams.getAll('source').join(',') === 'engrams'
    && sameClean.view === 'list' && sameClean.sort === 'title');
  cleanSamePending.resolve(libraryPayload([contextEngram])); await flush(); await flush();

  queuedLibraryResponses.push(libraryPayload([visibleDialogue]));
  w.OraLibraryWorkspace.open({ projectId: 'ora', sources: ['dialogues'], cleanBrowse: true });
  await flush(); await flush();
  var oldList = deferredResponse(); queuedLibraryResponses.push(oldList);
  var oldListPromise = w.OraLibraryWorkspace.refresh(); await flush();
  var oldPreview = deferredResponse(), oldRelated = deferredResponse();
  queuedPreviewResponses.push(oldPreview); queuedRelatedResponses.push(oldRelated);
  w.document.querySelector('.library-list-row__pin').click(); await flush();
  var oldCheckbox = w.document.querySelector('.library-list-row input[type="checkbox"]');
  oldCheckbox.checked = true; oldCheckbox.dispatchEvent(new w.Event('change', { bubbles: true }));
  w.document.querySelector('[data-library-view="visual"]').click();
  var newBrowse = deferredResponse(); queuedLibraryResponses.push(newBrowse);
  var changedCleanRequests = libraryRequestUrls.length;
  w.OraLibraryWorkspace.open({ projectId: 'project-a', sources: ['files'], cleanBrowse: true, returnFocus: browseButton });
  var changedClean = w.OraLibraryWorkspace.getState();
  record('changed clean browse aborts list, preview and relationship owners and invalidates old result identity',
    libraryRequestUrls.length === changedCleanRequests + 1
    && oldList.options.signal.aborted && oldPreview.options.signal.aborted && oldRelated.options.signal.aborted
    && changedClean.projectId === 'project-a' && changedClean.sources.join(',') === 'files'
    && !changedClean.pinnedId && !changedClean.selectedIds.length && !changedClean.loaded
    && changedClean.view === 'visual' && changedClean.sort === 'title'
    && w.document.querySelector('[data-library-source-count]').textContent === '1');
  newBrowse.resolve(libraryPayload([contextFile])); await flush(); await flush();
  oldList.resolve(libraryPayload([visibleDialogue]));
  oldPreview.resolve({ id: visibleDialogue.id, source: 'dialogues', text: 'Forbidden old body' });
  oldRelated.resolve({ conversations: [{ id: 'old-related', name: 'Forbidden old relationship' }], engrams: [] });
  await oldListPromise; await flush(); await flush();
  record('late clean-entry responses cannot restore old rows, bodies or relationships',
    w.OraLibraryWorkspace.getState().projectId === 'project-a' && w.OraLibraryWorkspace.getState().loaded === 1
    && !w.OraLibraryWorkspace.getState().pinnedId && !w.OraLibraryWorkspace.getState().related.anchorId
    && !w.document.getElementById('libraryWorkspaceResults').textContent.includes(visibleDialogue.title)
    && !w.document.body.textContent.includes('Forbidden old'));
  var cleanFocusRequests = libraryRequestUrls.length;
  w.OraLibraryWorkspace.open({ returnFocus: browseButton });
  record('Sidebar re-entry after a clean destination preserves scope without a second fetch',
    libraryRequestUrls.length === cleanFocusRequests && w.OraLibraryWorkspace.getState().projectId === 'project-a');
  var cleanGroup = w.document.querySelector('[data-library-group]');
  cleanGroup.value = 'folder'; cleanGroup.dispatchEvent(new w.Event('change', { bubbles: true }));
  queuedLibraryResponses.push(libraryPayload([]));
  w.OraLibraryWorkspace.close({ focus: false });
  w.OraLibraryWorkspace.open({ projectId: 'ora', sources: ['dialogues'], cleanBrowse: true });
  await flush(); await flush();
  record('closed clean entrance uses one fetch and repairs an incompatible grouping with synchronized controls',
    libraryRequestUrls.length === cleanFocusRequests + 1 && w.OraLibraryWorkspace.getState().group === 'none'
    && cleanGroup.value === 'none' && cleanGroup.querySelector('option[value="folder"]').disabled
    && w.OraLibraryWorkspace.getState().view === 'visual'
    && Array.from(w.document.querySelectorAll('[data-library-source]:checked')).map(function (input) { return input.value; }).join(',') === 'dialogues');
  w.OraLibraryWorkspace.close({ focus: false });
  var reload = new jsdom.JSDOM('<!doctype html><body>' + libraryMountMarkup + '</body>', { url: 'http://localhost/', runScripts: 'outside-only' });
  reload.window.localStorage.setItem('ora.library.last-view', 'visual');
  vm.runInContext(fs.readFileSync(path.resolve(__dirname, '..', 'js/library-workspace.js'), 'utf8'), reload.getInternalVMContext());
  record('page reload restores Visual without persisting filters or grouping', reload.window.OraLibraryWorkspace.getState().view === 'visual'
    && reload.window.OraLibraryWorkspace.getState().group === 'none');
  reload.window.close();
  var storageFailure = new jsdom.JSDOM('<!doctype html><body>' + libraryMountMarkup + '</body>', { url: 'http://localhost/', runScripts: 'outside-only', pretendToBeVisual: true });
  Object.defineProperty(storageFailure.window, 'localStorage', { get() { throw new Error('blocked'); } });
  storageFailure.window.fetch = function () { return Promise.resolve({ ok: true, json() { return Promise.resolve(libraryPayload([])); } }); };
  vm.runInContext(fs.readFileSync(path.resolve(__dirname, '..', 'js/library-workspace.js'), 'utf8'), storageFailure.getInternalVMContext());
  storageFailure.window.OraLibraryWorkspace.open(); await flush(); await flush();
  record('unavailable view storage falls back visibly to List', storageFailure.window.OraLibraryWorkspace.getState().view === 'list'
    && storageFailure.window.document.getElementById('libraryWorkspaceNotice').textContent.includes('storage is unavailable'));
  storageFailure.window.OraLibraryWorkspace.close({ focus: false }); storageFailure.window.close();

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
