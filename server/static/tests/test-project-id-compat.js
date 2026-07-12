#!/usr/bin/env node
/* Focused browser compatibility coverage for the Commons sentinel rename.
 *
 * Run:
 *   node ~/ora/server/static/tests/test-project-id-compat.js
 */

'use strict';

var fs = require('fs');
var path = require('path');
var vm = require('vm');

var JSDOM_PATH = path.join(
  __dirname, '..', 'ora-visual-compiler', 'tests', 'node_modules', 'jsdom'
);
var jsdom;
try {
  jsdom = require(JSDOM_PATH);
} catch (e) {
  try {
    jsdom = require('jsdom');
  } catch (fallbackError) {
    console.error('error: jsdom not available at ' + JSDOM_PATH);
    process.exit(2);
  }
}

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body>' +
  '<div class="left-sidebar">' +
  '  <div id="sidebarProjectSwitcher">' +
  '    <button id="sidebarProjectBtn"></button>' +
  '    <span id="sidebarProjectName"></span>' +
  '    <div id="sidebarProjectMenu" hidden>' +
  '      <input id="sidebarProjectSearch">' +
  '      <div id="sidebarProjectList"></div>' +
  '    </div>' +
  '  </div>' +
  '</div>' +
  '</body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
);

var w = dom.window;
var activePosts = [];
var conversationUrls = [];
var projectPathUrls = [];
var intervalCallbacks = [];
var failNextActivePost = false;
var holdNextActivePost = false;
var releaseHeldActivePost = null;
var activeGetPayload = { ok: true, nexus: 'general', canonical_nexus: 'commons' };
var projectRows = [{
  nexus: 'general', canonical_nexus: 'commons', name: 'Commons', unread_count: 0,
}];

function response(payload, ok, status) {
  return Promise.resolve({
    ok: ok !== false,
    status: status || (ok === false ? 500 : 200),
    json: function () { return Promise.resolve(payload || {}); },
  });
}

w.fetch = function (url, opts) {
  var target = String(url);
  if (target === '/api/projects/meta?status=active') {
    return response({ projects: projectRows });
  }
  if (target === '/api/projects/meta') {
    return response({ projects: projectRows });
  }
  if (target === '/api/active-project' && (!opts || !opts.method)) {
    return response(activeGetPayload);
  }
  if (target === '/api/active-project' && opts && opts.method === 'POST') {
    var posted = JSON.parse(opts.body).nexus;
    activePosts.push(posted);
    var shouldFail = failNextActivePost;
    failNextActivePost = false;
    var finishPost = function () {
      if (shouldFail) {
        return response({ ok: false, error: 'write failed' }, false, 500);
      }
      if (!posted || posted.toLowerCase() === 'general') {
        activeGetPayload = { ok: true, nexus: 'general', canonical_nexus: 'commons' };
        return response(activeGetPayload);
      }
      activeGetPayload = { ok: true, nexus: posted, canonical_nexus: posted };
      return response(activeGetPayload);
    };
    if (holdNextActivePost) {
      holdNextActivePost = false;
      return new Promise(function (resolve) {
        releaseHeldActivePost = function () {
          releaseHeldActivePost = null;
          resolve(finishPost());
        };
      });
    }
    return finishPost();
  }
  if (target.indexOf('/api/conversations?project_id=') === 0) {
    conversationUrls.push(target);
    return response({ pinned: [], errored: [], pending: [], unread: [], active: [] });
  }
  if (target.indexOf('/api/projects/') === 0) {
    projectPathUrls.push(target);
    if (target.indexOf('/conversations?') !== -1) {
      return response({ ok: true, conversations: [] });
    }
    if (target.indexOf('/files?') !== -1) {
      return response({ ok: true, exists: false, files: [] });
    }
  }
  return response({});
};
w.setInterval = function (callback) {
  intervalCallbacks.push(callback);
  return intervalCallbacks.length;
};
w.clearInterval = function () {};
w.localStorage.setItem('ora-sidebar-project', 'general');

var context = dom.getInternalVMContext();
context.console = console;
context.fetch = w.fetch;
context.setInterval = w.setInterval;
context.clearInterval = w.clearInterval;

var sidebarPath = path.resolve(__dirname, '..', 'js', 'sidebar.js');
vm.runInContext(fs.readFileSync(sidebarPath, 'utf8'), context, { filename: sidebarPath });
var projectModalPath = path.resolve(__dirname, '..', 'js', 'project-modal.js');
vm.runInContext(fs.readFileSync(projectModalPath, 'utf8'), context, { filename: projectModalPath });

var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? '  - ' + detail : ''));
}
function flush() {
  return new Promise(function (resolve) { w.setTimeout(resolve, 0); });
}

async function run() {
  record('legacy localStorage id is canonicalized in memory',
    w.OraSidebar.getActiveProject() === 'commons', w.OraSidebar.getActiveProject());
  record('legacy localStorage id is healed to version-neutral blank',
    w.localStorage.getItem('ora-sidebar-project') === '',
    w.localStorage.getItem('ora-sidebar-project'));
  record('old browser interprets blank localStorage as General',
    (w.localStorage.getItem('ora-sidebar-project') || 'general') === 'general');

  await flush();
  await flush();
  await flush();
  var defaultRow = w.document.querySelector('.sidebar-project-row');
  record('dual API default row joins canonical active project',
    !!defaultRow && defaultRow.classList.contains('is-active'));
  record('old reader sees the dual API row as General', projectRows[0].nexus === 'general');
  record('dual API default row displays as Commons',
    !!defaultRow && defaultRow.textContent.indexOf('Commons') !== -1);
  record('Commons filter is posted as version-neutral blank',
    conversationUrls.some(function (url) { return url === '/api/conversations?project_id='; }),
    JSON.stringify(conversationUrls));

  await w.OraSidebar.setActiveProject(' General ', 'Commons');
  record('Commons selection stores version-neutral blank',
    w.localStorage.getItem('ora-sidebar-project') === '');
  record('Commons selection posts version-neutral blank',
    activePosts.length === 1 && activePosts[0] === '', JSON.stringify(activePosts));

  // The current frontend must also tolerate an old server row that has no
  // canonical_nexus yet.
  projectRows = [{ nexus: 'general', name: 'Commons', unread_count: 0 }];
  await w.OraSidebar.refreshProjects();
  await flush();
  defaultRow = w.document.querySelector('.sidebar-project-row');
  record('legacy-only API row still joins canonical active project',
    !!defaultRow && defaultRow.classList.contains('is-active'));

  // GET is authoritative on startup/reconciliation; stale browser state must
  // not determine where a new Dialogue is stamped.
  projectRows = [
    { nexus: 'general', name: 'Commons', unread_count: 0 },
    { nexus: 'book', name: 'Book', unread_count: 0 },
  ];
  activeGetPayload = { ok: true, nexus: 'book' }; // pre-218 response shape
  await w.OraSidebar.syncActiveProject();
  await w.OraSidebar.refreshProjects();
  await w.OraSidebar.refresh();
  record('server GET authority replaces stale browser project',
    w.OraSidebar.getActiveProject() === 'book', w.OraSidebar.getActiveProject());
  record('GET reconciliation persists the confirmed real project',
    w.localStorage.getItem('ora-sidebar-project') === 'book',
    w.localStorage.getItem('ora-sidebar-project'));
  record('reconciled project drives the Dialogue filter',
    conversationUrls.some(function (url) { return url === '/api/conversations?project_id=book'; }),
    JSON.stringify(conversationUrls));

  // A failed pointer write must leave both UI and localStorage on the prior
  // confirmed project.
  failNextActivePost = true;
  var changed = await w.OraSidebar.setActiveProject('law', 'Law');
  record('failed active-project POST reports no selection change', changed === false);
  record('failed active-project POST keeps confirmed in-memory project',
    w.OraSidebar.getActiveProject() === 'book', w.OraSidebar.getActiveProject());
  record('failed active-project POST keeps confirmed localStorage project',
    w.localStorage.getItem('ora-sidebar-project') === 'book',
    w.localStorage.getItem('ora-sidebar-project'));
  record('failed active-project POST never applies the rejected filter',
    !conversationUrls.some(function (url) { return url === '/api/conversations?project_id=law'; }),
    JSON.stringify(conversationUrls));

  // On a slow first write, a second click is the user's latest intent. It must
  // queue behind the in-flight POST instead of being silently discarded.
  var postsBeforeOverlap = activePosts.length;
  holdNextActivePost = true;
  var firstSelection = w.OraSidebar.setActiveProject('book', 'Book');
  await flush();
  var secondSelection = w.OraSidebar.setActiveProject('law', 'Law');
  record('overlapping selection queues instead of issuing a concurrent POST',
    activePosts.slice(postsBeforeOverlap).join(',') === 'book',
    JSON.stringify(activePosts.slice(postsBeforeOverlap)));
  releaseHeldActivePost();
  var selectionResults = await Promise.all([firstSelection, secondSelection]);
  await flush();
  record('superseded selection resolves false and latest intent succeeds',
    selectionResults[0] === false && selectionResults[1] === true,
    JSON.stringify(selectionResults));
  record('overlapping selections serialize both POSTs in intent order',
    activePosts.slice(postsBeforeOverlap).join(',') === 'book,law',
    JSON.stringify(activePosts.slice(postsBeforeOverlap)));
  record('latest overlapping selection owns UI and localStorage',
    w.OraSidebar.getActiveProject() === 'law' &&
    w.localStorage.getItem('ora-sidebar-project') === 'law');

  // If A reaches the server and superseding B fails, the pointer remains A.
  // The browser must reconcile immediately instead of retaining its pre-A UI.
  var postsBeforeFailedLatest = activePosts.length;
  holdNextActivePost = true;
  var supersededSuccess = w.OraSidebar.setActiveProject('book', 'Book');
  await flush();
  failNextActivePost = true;
  var failedLatest = w.OraSidebar.setActiveProject('law', 'Law');
  releaseHeldActivePost();
  var failedLatestResults = await Promise.all([supersededSuccess, failedLatest]);
  await flush();
  record('superseded success plus latest failure reports neither intent committed',
    failedLatestResults[0] === false && failedLatestResults[1] === false,
    JSON.stringify(failedLatestResults));
  record('latest failure reconciles UI to server value written by superseded POST',
    activePosts.slice(postsBeforeFailedLatest).join(',') === 'book,law' &&
    w.OraSidebar.getActiveProject() === 'book' &&
    w.localStorage.getItem('ora-sidebar-project') === 'book',
    JSON.stringify(activePosts.slice(postsBeforeFailedLatest)));

  // Another tab/client can change the global pointer after startup. The
  // storage signal (and the same periodic/visibility refresh path) must pull
  // server authority before this tab continues filtering.
  projectRows.push({ nexus: 'law', name: 'Law', unread_count: 0 });
  activeGetPayload = { ok: true, nexus: 'law' };
  w.dispatchEvent(new w.StorageEvent('storage', {
    key: 'ora-sidebar-project', newValue: 'law', storageArea: w.localStorage,
  }));
  await flush();
  await flush();
  record('cross-tab storage signal reconciles the global server pointer',
    w.OraSidebar.getActiveProject() === 'law', w.OraSidebar.getActiveProject());
  record('post-startup reconciliation persists the new authority',
    w.localStorage.getItem('ora-sidebar-project') === 'law',
    w.localStorage.getItem('ora-sidebar-project'));
  record('post-startup reconciliation refreshes the project filter',
    conversationUrls.some(function (url) { return url === '/api/conversations?project_id=law'; }),
    JSON.stringify(conversationUrls));

  activeGetPayload = { ok: true, nexus: 'book' };
  await intervalCallbacks[0]();
  record('periodic refresh reconciles pointer changes without a storage event',
    w.OraSidebar.getActiveProject() === 'book', w.OraSidebar.getActiveProject());
  record('periodic reconciliation refreshes the confirmed project filter',
    conversationUrls.filter(function (url) { return url === '/api/conversations?project_id=book'; }).length >= 2,
    JSON.stringify(conversationUrls));

  // Path parameters cannot be blank. The current modal must use `general`,
  // which both server generations understand, rather than canonical
  // `commons`, which a pre-218 server treats as a real project.
  await w.OraProjectModal.open('general', 'Commons');
  var dialogueTab = w.document.querySelector('.project-modal__tab[data-tab="convos"]');
  dialogueTab.click();
  await flush();
  var filesTab = w.document.querySelector('.project-modal__tab[data-tab="files"]');
  filesTab.click();
  await flush();
  record('Commons modal conversations use legacy-safe path id',
    projectPathUrls.some(function (url) { return url.indexOf('/api/projects/general/conversations?') === 0; }),
    JSON.stringify(projectPathUrls));
  record('Commons modal files use legacy-safe path id',
    projectPathUrls.some(function (url) { return url.indexOf('/api/projects/general/files?') === 0; }),
    JSON.stringify(projectPathUrls));
  record('Commons modal never sends canonical sentinel to old path routes',
    !projectPathUrls.some(function (url) { return url.indexOf('/api/projects/commons/') === 0; }),
    JSON.stringify(projectPathUrls));

  var passed = results.filter(function (r) { return r.ok; }).length;
  console.log('\n' + passed + ' / ' + results.length + ' tests passed');
  if (passed !== results.length) process.exit(1);
  process.exit(0);
}

run().catch(function (err) {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
