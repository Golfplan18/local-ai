#!/usr/bin/env node
/* Focused jsdom coverage for the Overview Desktop shell and action handoffs. */
'use strict';

var assert = require('assert');
var fs = require('fs');
var path = require('path');
var vm = require('vm');

var nodeModules = process.env.COMPILER_TEST_NODE_MODULES || path.resolve(
  __dirname, '..', '..', 'document-surface', 'node_modules'
);
var jsdom;
try {
  jsdom = require(path.join(nodeModules, 'jsdom'));
} catch (error) {
  console.error('error: jsdom not available at ' + nodeModules + ': ' + error.message);
  process.exit(2);
}

var indexSource = fs.readFileSync(path.resolve(__dirname, '..', '..', 'index-v3.html'), 'utf8');
var launcherMatch = indexSource.match(
  /<button class="sidebar-dash-icon overview-desktop-launcher"[\s\S]*?<\/button>/
);
var mountMatch = indexSource.match(
  /<section class="overview-desktop" id="overviewDesktop"[\s\S]*?<\/section>/
);
var statusMatch = indexSource.match(
  /<p class="overview-desktop__status" id="overviewDesktopStatus"[\s\S]*?<\/p>/
);
assert(launcherMatch, 'index-v3.html carries the permanent Overview launcher');
assert(mountMatch, 'index-v3.html carries the stable Overview mount');
assert(statusMatch, 'index-v3.html carries the Overview-owned workspace status');
assert(indexSource.includes('/static/js/overview-desktop.js'), 'Overview controller is loaded');

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body>'
  + '<div class="ora-shell" data-workspace="unchanged">'
  + launcherMatch[0]
  + '<section id="activeDialogue" data-dialogue-id="dialogue-kept">'
  + '<textarea id="workspaceInput">unfinished draft kept</textarea>'
  + '</section>'
  + '<section id="priorSurface" data-pane-owner="findings-kept" hidden></section>'
  + '<section id="asideSurface" data-pane-owner="aside-kept"></section>'
  + '<section id="exhibitsSurface" data-pane-owner="exhibits-kept"></section>'
  + '</div>'
  + mountMatch[0]
  + statusMatch[0]
  + '</body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
);
var w = dom.window;
var projectOpens = [];
var libraryOpens = [];
var scheduledOpens = [];
var requests = [];
var responses = [];
var readViews = [];
w.OraDocumentSurface = {
  renderRead: function (options) {
    var content = w.document.createElement('article');
    content.textContent = options.markdown;
    content.setAttribute('aria-label', options.ariaLabel);
    options.host.replaceChildren(content);
    var view = {
      mode: 'read', options: options, destroyed: false,
      destroy: function () {
        view.destroyed = true;
        options.host.replaceChildren();
      },
    };
    readViews.push(view);
    return view;
  },
  createEditor: function () { throw new Error('Daily Notes must never enter Edit'); },
};
w.OraProjectModal = {
  open: function (nexus, title) { projectOpens.push([nexus, title]); },
};
w.OraLibraryWorkspace = { open: function (options) {
  assert.strictEqual(w.document.getElementById('overviewDesktop').hidden, true);
  assert.strictEqual(w.document.querySelector('.ora-shell').hasAttribute('inert'), false);
  libraryOpens.push(options);
} };
w.document.addEventListener('ora:scheduled-trigger-open-requested', function (event) {
  scheduledOpens.push(event.detail);
});
w.fetch = function (url, options) {
  requests.push([url, options]);
  var next = responses.shift();
  return next instanceof Error ? Promise.reject(next) : Promise.resolve(next);
};

function ok(payload) {
  return reply(200, payload);
}
function reply(status, payload) {
  return {
    ok: status >= 200 && status < 300,
    status: status,
    json: function () { return Promise.resolve(payload); },
  };
}
function deferred() {
  var resolve;
  var reject;
  var promise = new Promise(function (resolvePromise, rejectPromise) {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise: promise, resolve: resolve, reject: reject };
}
function flush() {
  return new Promise(function (resolve) { w.setTimeout(resolve, 0); });
}
function source(id, title, state, items, error, count) {
  return {
    source_id: id,
    title: title,
    state: state,
    count: Number.isFinite(count) ? count : items.length,
    available: state !== 'unavailable',
    freshness: {
      observed_at: '2026-09-01T12:30:00+00:00',
      last_success_at: state === 'unavailable' ? null : '2026-09-01T12:29:00+00:00',
    },
    error: error || null,
    items: items,
  };
}

var overviewPayload = { sources: [
  source('matrix-tasks', 'Tasks', 'empty', [], null, 0),
  source('daily-note', 'Prior-day Daily Note', 'missing', [{
    source_id: 'daily-note', item_id: 'daily-note:2026-08-31',
    title: '2026-08-31', text: 'No completed Daily Note was found.', state: 'missing',
    time: null, count: null, scope: { path: '/notes/2026-08-31.md' }, actions: ['read_note', 'open_note'],
  }], null, 0),
  source('triggers', 'Scheduled Triggers', 'ready', [{
    source_id: 'triggers', item_id: 'trigger:draft-email', title: 'Draft email',
    text: 'manual · email send', state: 'draft', time: null, count: null,
    scope: null, actions: ['open_scheduled', 'inspect', 'review', 'run', 'retire'],
  }]),
  source('project-priority', 'Project priority', 'ready', [{
    source_id: 'project-priority', item_id: 'project:ora',
    title: 'Ora', text: 'Active', state: 'ready', time: null, count: null,
    scope: { project_nexus: 'ora' }, actions: ['open_project', 'open_project_files', 'open_project_dialogues', 'open_project_knowledge'],
  }]),
  source('oversight', 'Oversight', 'partial', [{
    title: 'Review evidence', text: 'Needs a decision', state: 'paused', time: null,
    count: null, scope: { project_nexus: 'ora' }, actions: ['open_conversation', 'discuss'],
  }], { code: 'operating_unavailable', message: 'Operating work could not be read.' }),
] };
var availableOverviewPayload = JSON.parse(JSON.stringify(overviewPayload));
var availableDaily = availableOverviewPayload.sources.find(function (entry) {
  return entry.source_id === 'daily-note';
});
availableDaily.state = 'ready';
availableDaily.count = 1;
availableDaily.items[0].state = 'available';
availableDaily.items[0].text = 'Dialogues · Overview planning';
availableDaily.items[0].time = '2026-08-31';
responses.push(ok(overviewPayload));

var controllerSource = fs.readFileSync(
  path.resolve(__dirname, '..', 'js', 'overview-desktop.js'), 'utf8'
);
vm.runInContext(controllerSource, dom.getInternalVMContext());

(async function run() {
  var launcher = w.document.getElementById('overviewDesktopOpen');
  var mount = w.document.getElementById('overviewDesktop');
  var workspace = w.document.querySelector('.ora-shell');
  var workspaceInput = w.document.getElementById('workspaceInput');
  var activeDialogue = w.document.getElementById('activeDialogue');
  var priorSurface = w.document.getElementById('priorSurface');
  var asideSurface = w.document.getElementById('asideSurface');
  var exhibitsSurface = w.document.getElementById('exhibitsSurface');
  var status = w.document.getElementById('overviewDesktopStatus');
  var closeControl = mount.querySelector('[data-overview-close]');

  function assertWorkspacePreserved(message) {
    assert.strictEqual(workspace.dataset.workspace, 'unchanged', message + ': workspace identity');
    assert.strictEqual(activeDialogue.dataset.dialogueId, 'dialogue-kept', message + ': Dialogue');
    assert.strictEqual(workspaceInput.value, 'unfinished draft kept', message + ': draft');
    assert.strictEqual(priorSurface.hidden, true, message + ': Findings visibility');
    assert.strictEqual(priorSurface.dataset.paneOwner, 'findings-kept', message + ': Findings owner');
    assert.strictEqual(asideSurface.dataset.paneOwner, 'aside-kept', message + ': Aside owner');
    assert.strictEqual(exhibitsSurface.dataset.paneOwner, 'exhibits-kept', message + ': Exhibits owner');
  }

  workspaceInput.focus();
  launcher.click();
  await flush();
  await flush();

  assert.strictEqual(mount.hidden, false, 'launcher opens the full Overview surface');
  assert.strictEqual(workspace.hasAttribute('inert'), true, 'underlying workspace is inert while open');
  assert.strictEqual(requests.length, 1);
  assert.strictEqual(requests[0][0], '/api/overview');
  assert.strictEqual(requests[0][1].method, 'GET');
  assert.deepStrictEqual(
    Array.from(mount.querySelectorAll('.overview-source')).map(function (card) {
      return [card.dataset.sourceId, card.dataset.state];
    }),
    [
      ['project-priority', 'ready'],
      ['oversight', 'partial'],
      ['triggers', 'ready'],
      ['daily-note', 'missing'],
      ['matrix-tasks', 'empty'],
    ],
    'the five sources render in canonical order with their distinct states'
  );
  assert(mount.textContent.includes('Checked 2026-09-01T12:30:00+00:00'));
  assert(mount.textContent.includes('Last success 2026-09-01T12:29:00+00:00'));
  assert(mount.textContent.includes('Operating work could not be read.'));
  assert.strictEqual(status.getAttribute('role'), 'status');
  assert.strictEqual(status.getAttribute('aria-live'), 'polite');
  assert.strictEqual(mount.contains(status), false, 'status survives closing the dialog');
  assert.strictEqual(status.hidden, false, 'loading and source status is visible while open');

  var actions = Array.from(mount.querySelectorAll('[data-overview-action]'));
  assert.strictEqual(
    actions.length, 6,
    'a missing Daily Note stays non-actionable even when its fixture advertises open_note'
  );
  assert.strictEqual(
    actions.some(function (action) { return action.dataset.overviewAction === 'open_note'; }),
    false
  );
  var scheduledAction = actions.find(function (action) {
    return action.dataset.overviewAction === 'open_scheduled';
  });
  scheduledAction.click();
  assert.strictEqual(scheduledOpens.length, 1);
  assert.strictEqual(scheduledOpens[0].trigger_id, 'draft-email');
  assert.strictEqual(requests.length, 1, 'the handoff makes no Trigger or lifecycle request');
  assert.strictEqual(mount.hidden, true, 'Scheduled handoff closes Overview');
  assert.strictEqual(workspace.hasAttribute('inert'), false, 'workspace inert state is restored');
  assertWorkspacePreserved('Scheduled handoff');
  assert.strictEqual(w.document.activeElement, workspaceInput, 'prior focus is restored before handoff');

  responses.push(ok(overviewPayload));
  launcher.click();
  await flush();
  await flush();
  var projectAction = Array.from(mount.querySelectorAll('[data-overview-action]'))
    .find(function (action) { return action.dataset.overviewAction === 'open_project'; });
  projectAction.click();
  assert.deepStrictEqual(projectOpens, [['ora', 'Ora']]);
  assert.strictEqual(mount.hidden, true, 'project handoff closes Overview');
  assert.strictEqual(workspace.hasAttribute('inert'), false, 'workspace inert state is restored');
  assertWorkspacePreserved('project handoff');
  assert.strictEqual(w.document.activeElement, workspaceInput, 'prior focus is restored');

  responses.push(ok(availableOverviewPayload));
  launcher.click();
  await flush();
  await flush();
  var dailyAction = Array.from(mount.querySelectorAll('[data-overview-action]'))
    .find(function (action) { return action.dataset.overviewAction === 'open_note'; });
  assert(dailyAction, 'an available Daily Note advertising open_note has an external action');
  assert.strictEqual(dailyAction.textContent, 'Open externally');

  var pending = deferred();
  responses.push(pending.promise);
  var pendingRequestIndex = requests.length;
  dailyAction.click();
  dailyAction.click();
  assert.strictEqual(
    requests.length, pendingRequestIndex + 1,
    'the pending button suppresses a duplicate Daily Note dispatch'
  );
  assert.strictEqual(dailyAction.disabled, true);
  assert.strictEqual(dailyAction.textContent, 'Opening…');
  assert(status.textContent.includes('Sending the Daily Note open request'));
  assert.strictEqual(closeControl.disabled, false, 'Close remains enabled while the action is pending');
  Array.from(mount.querySelectorAll('[data-overview-action]')).forEach(function (action) {
    if (action !== dailyAction) assert.strictEqual(action.disabled, false);
  });
  var openRequest = requests[pendingRequestIndex];
  assert.strictEqual(openRequest[0], '/api/overview/daily-note/open');
  assert.strictEqual(openRequest[1].method, 'POST');
  assert.strictEqual(openRequest[1].headers.Accept, 'application/json');
  assert.strictEqual(openRequest[1].headers['Content-Type'], 'application/json');
  assert.deepStrictEqual(Object.keys(openRequest[1].headers).sort(), ['Accept', 'Content-Type']);
  assert.deepStrictEqual(JSON.parse(openRequest[1].body), {
    id: 'daily-note:2026-08-31',
  });
  assert.strictEqual(openRequest[1].body.includes('/notes/'), false, 'no client path is sent');

  pending.resolve(ok({
    ok: true,
    identity: 'daily-note:2026-08-31',
    application: 'obsidian',
    outcome: 'sent',
    message: 'Open request sent to Obsidian.',
  }));
  await flush();
  await flush();
  assert.strictEqual(mount.hidden, true, 'confirmed Obsidian dispatch uses the existing close path');
  assert.strictEqual(status.hidden, false, 'the handoff result stays visibly available after close');
  assert.strictEqual(status.textContent, 'Open request sent to Obsidian.');
  assert.strictEqual(status.textContent.includes('opened'), false, 'dispatch is not described as display');
  assert.strictEqual(workspace.hasAttribute('inert'), false);
  assertWorkspacePreserved('Obsidian handoff');
  assert.strictEqual(w.document.activeElement, workspaceInput, 'Daily Note success restores focus');

  responses.push(ok(availableOverviewPayload));
  launcher.click();
  await flush();
  await flush();
  assert.strictEqual(status.textContent, 'Five sources checked.', 'opening clears prior handoff status');
  dailyAction = mount.querySelector('[data-overview-action="open_note"]');
  responses.push(ok({
    ok: true,
    identity: 'daily-note:2026-08-31',
    application: 'default_markdown',
    outcome: 'fallback_sent',
    message: 'Obsidian could not accept the request. Open request sent to the default Markdown application.',
  }));
  dailyAction.click();
  await flush();
  await flush();
  assert.strictEqual(mount.hidden, true, 'confirmed fallback dispatch also closes Overview');
  assert.strictEqual(status.hidden, false, 'fallback explanation remains visible after close');
  assert(status.textContent.includes('Obsidian could not accept the request'));
  assert(status.textContent.includes('Open request sent to the default Markdown application'));
  assert.strictEqual(status.textContent.includes('opened'), false);
  assertWorkspacePreserved('default Markdown handoff');

  responses.push(ok(availableOverviewPayload));
  launcher.click();
  await flush();
  await flush();
  dailyAction = mount.querySelector('[data-overview-action="open_note"]');
  dailyAction.focus();
  responses.push(reply(502, {
    ok: false,
    identity: 'daily-note:2026-08-31',
    application: 'default_markdown',
    outcome: 'failed',
    message: 'Obsidian and the default Markdown application refused the request.',
  }));
  dailyAction.click();
  await flush();
  await flush();
  assert.strictEqual(mount.hidden, false, 'failure leaves Overview usable and visible');
  assert.strictEqual(mount.querySelectorAll('.overview-source').length, 5, 'failure preserves all cards');
  assert.strictEqual(
    status.textContent,
    'Obsidian and the default Markdown application refused the request.'
  );
  assert.strictEqual(dailyAction.disabled, false, 'failure restores only the pending button');
  assert.strictEqual(w.document.activeElement, dailyAction, 'failure restores action focus');
  assert.strictEqual(workspace.hasAttribute('inert'), true, 'failed action keeps workspace inert');
  var requestsAfterFailure = requests.length;
  await flush();
  assert.strictEqual(requests.length, requestsAfterFailure, 'failure starts no retry timer');

  responses.push(reply(504, {
    ok: false,
    identity: 'daily-note:2026-08-31',
    application: 'obsidian',
    outcome: 'uncertain',
    message: 'Ora cannot tell whether Obsidian received the request. No other application was tried.',
  }));
  dailyAction.click();
  assert(status.textContent.includes('Sending the Daily Note open request'));
  await flush();
  await flush();
  assert.strictEqual(mount.hidden, false, 'uncertain handoff leaves Overview visible');
  assert(status.textContent.includes('cannot tell whether Obsidian received'));
  assert(status.textContent.includes('No other application was tried'));
  assert.strictEqual(dailyAction.disabled, false);
  assert.strictEqual(w.document.activeElement, dailyAction, 'uncertainty restores action focus');
  assert.strictEqual(workspace.hasAttribute('inert'), true, 'uncertain action keeps workspace inert');
  assertWorkspacePreserved('failed and uncertain handoffs');

  responses.push(ok({
    ok: true,
    identity: 'daily-note:2026-08-30',
    application: 'obsidian',
    outcome: 'sent',
    message: 'Open request sent to Obsidian.',
  }));
  dailyAction.click();
  await flush();
  await flush();
  assert.strictEqual(mount.hidden, false, 'a protocol-invalid success cannot close Overview');
  assert.strictEqual(status.textContent, 'Ora returned an invalid Daily Note open response.');
  assert.strictEqual(status.textContent.includes('Open request sent'), false);
  assert.strictEqual(dailyAction.disabled, false);

  responses.push(new Error('private network detail'));
  dailyAction.click();
  await flush();
  await flush();
  assert.strictEqual(mount.hidden, false, 'a network failure leaves Overview usable');
  assert.strictEqual(status.textContent, 'The Daily Note open request could not reach Ora.');
  assert.strictEqual(status.textContent.includes('private network detail'), false);
  assert.strictEqual(dailyAction.disabled, false);

  closeControl.click();
  responses.push(ok(availableOverviewPayload));
  launcher.click();
  await flush();
  await flush();
  dailyAction = mount.querySelector('[data-overview-action="open_note"]');
  var late = deferred();
  responses.push(late.promise);
  dailyAction.click();
  closeControl.click();
  responses.push(ok(availableOverviewPayload));
  launcher.click();
  await flush();
  await flush();
  var reopenedText = mount.textContent;
  assert.strictEqual(mount.hidden, false);
  assert.strictEqual(status.textContent, 'Five sources checked.');
  late.resolve(ok({
    ok: true,
    identity: 'daily-note:2026-08-31',
    application: 'obsidian',
    outcome: 'sent',
    message: 'Open request sent to Obsidian.',
  }));
  await flush();
  await flush();
  assert.strictEqual(mount.hidden, false, 'late success cannot close a reopened Overview');
  assert.strictEqual(mount.textContent, reopenedText, 'late success cannot replace reopened state');
  assert.strictEqual(status.textContent, 'Five sources checked.');

  // The reader is another view inside this same Overview, with the original
  // source cards and prior workspace held intact throughout its lifecycle.
  var cardsHost = w.document.getElementById('overviewDesktopSources');
  var reader = w.document.getElementById('overviewDailyNoteReader');
  var readerHost = w.document.getElementById('overviewDailyNoteDocument');
  var back = mount.querySelector('[data-overview-back]');
  var cards = Array.from(cardsHost.children);
  var readAction = mount.querySelector('[data-overview-action="read_note"]');
  var readPayload = {
    id: 'daily-note:2026-08-31', source: 'daily-note', text: '\n# Daily Note\n\nA synthetic body.\n',
  };
  assert(readAction, 'an available Daily Note advertises Read in Ora');
  assert.strictEqual(readAction.textContent, 'Read in Ora');
  readAction.focus();
  var readPending = deferred();
  responses.push(readPending.promise);
  var readRequestIndex = requests.length;
  readAction.click();
  readAction.click();
  assert.strictEqual(requests.length, readRequestIndex + 1, 'duplicate Read is suppressed');
  var readRequest = requests[readRequestIndex];
  assert.strictEqual(readRequest[0], '/api/overview/daily-note/read?id=daily-note%3A2026-08-31');
  assert.strictEqual(readRequest[1].method, 'GET');
  assert.strictEqual(readRequest[1].headers.Accept, 'application/json');
  assert.strictEqual(readRequest[1].body, undefined, 'the exact Read sends no body or path');
  assert(readRequest[1].signal, 'Read supplies an abort signal');
  assert.strictEqual(readAction.disabled, true);
  assert.strictEqual(cardsHost.hidden, false, 'cards remain usable while Read is pending');
  assert.strictEqual(mount.querySelector('[data-overview-action="open_note"]').disabled, false);
  assert.strictEqual(closeControl.disabled, false);
  readPending.resolve(ok(readPayload));
  await flush();
  await flush();
  assert.strictEqual(reader.hidden, false);
  assert.strictEqual(cardsHost.hidden, true);
  assert.deepStrictEqual(Array.from(cardsHost.children), cards, 'Read never rebuilds the five cards');
  assert.strictEqual(readViews.length, 1);
  assert.strictEqual(readViews[0].options.host, readerHost);
  assert.strictEqual(readViews[0].options.markdown, readPayload.text, 'body is passed unchanged to the shared reader');
  assert.strictEqual(readViews[0].options.ariaLabel, 'Daily Note 2026-08-31');
  assert.strictEqual(reader.querySelector('textarea, .cm-editor, [data-overview-action="edit"]'), null);
  assert.strictEqual(w.document.activeElement, back);
  assertWorkspacePreserved('Daily Note Read');
  back.click();
  assert.strictEqual(readViews[0].destroyed, true);
  assert.strictEqual(readerHost.childNodes.length, 0);
  assert.strictEqual(reader.hidden, true);
  assert.strictEqual(cardsHost.hidden, false);
  assert.strictEqual(w.document.activeElement, readAction, 'Back returns to the initiating action');
  assert.deepStrictEqual(Array.from(cardsHost.children), cards);

  for (var failure of [
    reply(409, { error: 'This Daily Note exceeds Ora\'s safe 4 MiB rendered-document bound. Open externally to read it.' }),
    ok({ id: 'daily-note:2026-08-30', source: 'daily-note', text: 'stale body' }),
    ok({ id: readPayload.id, source: 'file', text: 'wrong source' }),
    ok({ id: readPayload.id, source: 'daily-note', text: null }),
    { ok: true, status: 200, json: function () { return Promise.reject(new Error('private parser detail')); } },
    new Error('private network detail'),
  ]) {
    responses.push(failure);
    readAction.click();
    await flush();
    await flush();
    assert.strictEqual(reader.hidden, true, 'failed Read keeps the cards visible');
    assert.strictEqual(cardsHost.hidden, false);
    assert.strictEqual(readAction.disabled, false);
    assert.strictEqual(w.document.activeElement, readAction);
    assert.strictEqual(status.textContent.includes('private'), false);
    assert.deepStrictEqual(Array.from(cardsHost.children), cards);
    assert.strictEqual(readViews.length, 1, 'failed responses never enter the renderer');
    assert.strictEqual(mount.querySelector('[data-overview-action="open_note"]').disabled, false);
  }

  // Missing/broken bundles preserve an authorized body as inert literal text.
  var sharedSurface = w.OraDocumentSurface;
  for (var surface of [undefined, { renderRead: function () { throw new Error('renderer unavailable'); } }]) {
    w.OraDocumentSurface = surface;
    responses.push(ok(readPayload));
    readAction.click();
    await flush();
    await flush();
    assert.strictEqual(reader.hidden, false);
    assert.strictEqual(reader.querySelector('pre').textContent, readPayload.text);
    assert(reader.textContent.includes('Formatted Read is unavailable'));
    back.click();
  }
  w.OraDocumentSurface = sharedSurface;

  // A document reports only the shadow host for an editor's focused content.
  // Keep both hosts nonfocusable so restoring either host cannot pass this test.
  closeControl.click();
  var editorHost = w.document.createElement('div');
  var editorRoot = editorHost.attachShadow({ mode: 'open' });
  var innerHost = w.document.createElement('div');
  var innerRoot = innerHost.attachShadow({ mode: 'open' });
  var editorInput = w.document.createElement('input');
  editorInput.value = 'unfinished editor draft kept';
  innerRoot.appendChild(editorInput);
  editorRoot.appendChild(innerHost);
  workspace.appendChild(editorHost);
  editorInput.focus();
  editorInput.setSelectionRange(4, 12);
  assert.strictEqual(w.document.activeElement, editorHost);
  assert.strictEqual(editorRoot.activeElement, innerHost);
  responses.push(ok(availableOverviewPayload));
  launcher.click();
  await flush();
  await flush();
  readAction = mount.querySelector('[data-overview-action="read_note"]');

  for (var closeKind of ['button', 'Escape']) {
    responses.push(ok(readPayload));
    readAction.click();
    await flush();
    await flush();
    var view = readViews[readViews.length - 1];
    if (closeKind === 'button') closeControl.click();
    else w.document.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    assert.strictEqual(view.destroyed, true, closeKind + ' destroys the mounted reader');
    assert.strictEqual(reader.hidden, true);
    assert.strictEqual(readerHost.childNodes.length, 0);
    assert.strictEqual(workspace.hasAttribute('inert'), false);
    assert.strictEqual(w.document.activeElement, editorHost);
    assert.strictEqual(editorRoot.activeElement, innerHost);
    assert.strictEqual(innerRoot.activeElement, editorInput, closeKind + ' restores the focused editor content');
    assert.strictEqual(editorInput.value, 'unfinished editor draft kept');
    assert.deepStrictEqual([editorInput.selectionStart, editorInput.selectionEnd], [4, 12]);
    assertWorkspacePreserved('reader ' + closeKind);
    responses.push(ok(availableOverviewPayload));
    launcher.click();
    await flush();
    await flush();
    assert.strictEqual(reader.hidden, true, 'next opening starts with cards');
    assert.strictEqual(cardsHost.hidden, false);
    readAction = mount.querySelector('[data-overview-action="read_note"]');
  }

  var lateRead = deferred();
  responses.push(lateRead.promise);
  readAction.click();
  var lateSignal = requests[requests.length - 1][1].signal;
  closeControl.click();
  assert.strictEqual(lateSignal.aborted, true, 'closing aborts the pending read');
  responses.push(ok(availableOverviewPayload));
  launcher.click();
  await flush();
  await flush();
  readAction = mount.querySelector('[data-overview-action="read_note"]');
  responses.push(ok(readPayload));
  readAction.click();
  await flush();
  await flush();
  var currentRead = readViews[readViews.length - 1];
  var readCount = readViews.length;
  lateRead.resolve(ok({ id: readPayload.id, source: 'daily-note', text: 'late body with same identity' }));
  await flush();
  await flush();
  assert.strictEqual(readViews.length, readCount, 'a late same-identity response cannot enter a newer session');
  assert.strictEqual(currentRead.destroyed, false);
  assert.strictEqual(readerHost.textContent, readPayload.text);
  back.click();

  closeControl.click();
  editorHost.remove();
  responses.push(new Error('source connection failed'));
  launcher.focus();
  launcher.click();
  await flush();
  await flush();
  assert.strictEqual(mount.querySelectorAll('.overview-source').length, 0);
  assert(status.textContent.includes('source connection failed'));
  w.document.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  assert.strictEqual(mount.hidden, true, 'Escape closes Overview');
  assert.strictEqual(w.document.activeElement, launcher, 'launcher focus is restored after close');
  assertWorkspacePreserved('final close');

  for (var size of [0, 1, 8, 9, 25]) {
    var projectsPayload = JSON.parse(JSON.stringify(availableOverviewPayload));
    var projectSource = projectsPayload.sources.find(function (entry) { return entry.source_id === 'project-priority'; });
    var prototype = projectSource.items[0];
    projectSource.items = Array.from({ length: size }, function (_, index) {
      return Object.assign({}, prototype, {
        item_id: 'project:project-' + index, scope: { project_nexus: 'project-' + index },
        title: 'A long project title with complete meaning ' + index, text: 'Priority ' + (index + 1) + ' · active',
        time: '2026-09-01T12:30:00+00:00',
      });
    });
    projectSource.count = size;
    projectSource.state = size ? 'ready' : 'empty';
    responses.push(ok(projectsPayload)); launcher.click(); await flush(); await flush();
    var groups = Array.from(mount.querySelectorAll('.overview-project'));
    assert.strictEqual(groups.length, size, 'all ' + size + ' projects remain native groups');
    assert.deepStrictEqual(groups.map(function (node) { return node.dataset.slot; }), Array.from({ length: size }, function (_, index) { return String(index); }));
    assert.deepStrictEqual(groups.map(function (node) { return node.dataset.projectId; }), projectSource.items.map(function (item) { return item.scope.project_nexus; }));
    groups.forEach(function (node) {
      assert.strictEqual(node.querySelectorAll('button:not(:disabled)').length, 4);
      assert.strictEqual(node.querySelector('h3').title, node.querySelector('h3').textContent);
    });
    assert(mount.querySelector('.overview-projects__heading').textContent.includes(size + ' active project'));
    assert.strictEqual(mount.querySelectorAll('.overview-source').length, 5);
    var identity = mount.querySelector('.overview-projects__identity');
    assert.strictEqual(identity.getAttribute('aria-hidden'), 'true');
    assert.strictEqual(identity.querySelectorAll('[id], [tabindex], [role]').length, 0);
    var slotsBefore = groups.map(function (node) { return node.dataset.slot; });
    w.dispatchEvent(new w.Event('resize'));
    assert.deepStrictEqual(groups.map(function (node) { return node.dataset.slot; }), slotsBefore);
    if (size) {
      groups[0].querySelector('button').focus();
      w.dispatchEvent(new w.Event('resize'));
      assert.strictEqual(w.document.activeElement, groups[0].querySelector('button'), 'reflow preserves focus');
      var last = mount.querySelector('[data-overview-action="open_note"]');
      var disabledField = w.document.createElement('fieldset');
      disabledField.disabled = true;
      disabledField.innerHTML = '<button>Disabled through fieldset</button>';
      mount.appendChild(disabledField);
      last.focus();
      w.document.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }));
      assert.strictEqual(w.document.activeElement, closeControl, 'Tab stays inside Overview');
      w.document.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true }));
      assert.strictEqual(w.document.activeElement, last, 'Shift-Tab stays inside Overview');
      disabledField.remove();
    }
    closeControl.click();
  }

  for (var destination of [['open_project_files', 'files'], ['open_project_dialogues', 'dialogues'], ['open_project_knowledge', 'engrams']]) {
    responses.push(ok(availableOverviewPayload)); launcher.click(); await flush(); await flush();
    mount.querySelector('.overview-project [data-overview-action="' + destination[0] + '"]').click();
    var entrance = libraryOpens[libraryOpens.length - 1];
    assert.strictEqual(entrance.projectId, 'ora');
    assert.deepStrictEqual(Array.from(entrance.sources), [destination[1]]);
    assert.strictEqual(entrance.cleanBrowse, true);
    assert.strictEqual(entrance.returnFocus, launcher, 'return focus is a visible workspace entrance');
    assertWorkspacePreserved('Library handoff');
  }
  responses.push(ok(availableOverviewPayload)); launcher.click(); await flush(); await flush();
  var savedLibrary = w.OraLibraryWorkspace; delete w.OraLibraryWorkspace;
  mount.querySelector('[data-overview-action="open_project_files"]').click();
  assert.strictEqual(mount.hidden, false, 'missing owner leaves Overview open');
  assert(status.textContent.includes('Files is unavailable'));
  w.OraLibraryWorkspace = savedLibrary;
  var savedProjectModal = w.OraProjectModal; delete w.OraProjectModal;
  mount.querySelector('[data-overview-action="open_project"]').click();
  assert.strictEqual(mount.hidden, false);
  assert(status.textContent.includes('Overview is unavailable'));
  w.OraProjectModal = savedProjectModal;
  closeControl.click();
  for (var qualification of ['partial', 'unavailable']) {
    var qualified = JSON.parse(JSON.stringify(availableOverviewPayload));
    var qualifiedSource = qualified.sources.find(function (entry) { return entry.source_id === 'project-priority'; });
    qualifiedSource.state = qualification;
    if (qualification === 'unavailable') qualifiedSource.items = [];
    responses.push(ok(qualified)); launcher.click(); await flush(); await flush();
    assert(mount.querySelector('.overview-projects__heading').textContent.includes(qualification === 'partial' ? 'known active projects · Partial inventory' : 'Project count unavailable'));
    assert(mount.querySelector('[data-overview-action="read_note"]'), 'independent Daily action survives');
    closeControl.click();
  }
  var malformedProjects = JSON.parse(JSON.stringify(availableOverviewPayload));
  var malformedSource = malformedProjects.sources.find(function (entry) { return entry.source_id === 'project-priority'; });
  malformedSource.items = [null, { title: 'Invalid scope', item_id: 'project:ora', scope: { project_nexus: '../ora' }, actions: ['open_project'] }];
  responses.push(ok(malformedProjects)); launcher.click(); await flush(); await flush();
  assert.strictEqual(mount.querySelectorAll('.overview-project button:not(:disabled)').length, 0);
  assert(mount.querySelector('[data-overview-action="read_note"]'), 'malformed project rows leave other sources usable');
  closeControl.click();
  var css = fs.readFileSync(path.resolve(__dirname, '..', 'styles', 'components', 'overview-desktop.css'), 'utf8');
  assert(css.includes('prefers-reduced-motion: reduce') && css.includes('animation: none'), 'motion is settled and reduced-motion is explicit');

  function taskGroup(nexus, revision) {
    var identity = nexus === 'alpha' ? 'a'.repeat(24) : 'b'.repeat(24);
    var digest = String(revision || 1).repeat(64);
    var prefix = identity + ':' + digest + ':';
    var group = {
      nexus: nexus, title: 'Project ' + nexus, source_id: 'matrix-tasks', item_id: 'project:' + nexus,
      scope: { project_nexus: nexus }, state: 'ready', reason: null, editable: true,
      identity: identity, digest: digest, root_ref: prefix + 'root',
      source_text: '- [ ] Duplicate\n  - [ ] Nested\n- [ ] Duplicate\n- [x] Done ✅ 2026-09-01\n<script>never execute</script>',
      counts: { total: 4, completed: 1, incomplete: 3 }, actions: ['open_project', 'refresh_tasks', 'edit_tasks'],
    };
    group.tasks = ['Duplicate', 'Nested', 'Duplicate', 'Done ✅ 2026-09-01'].map(function (text, index) {
      return { ref: prefix + (index * 20), text: text, done: index === 3, depth: index === 1 ? 1 : 0,
        parent_ref: index === 1 ? prefix + '0' : null, completion_date: index === 3 ? '2026-09-01' : null,
        date_ambiguous: false, limitations: index === 0 ? { delete: 'Move or promote children first.' } : {} };
    });
    return group;
  }
  function taskPayload(groups, state, error) {
    var payload = JSON.parse(JSON.stringify(availableOverviewPayload));
    var source = payload.sources.find(function (entry) { return entry.source_id === 'matrix-tasks'; });
    source.items = groups;
    source.state = state || 'ready';
    source.error = error || (['partial', 'unavailable'].includes(source.state)
      ? { code: 'task_source_incomplete', message: 'Known task counts only; some Matrix content or project authority needs attention.' } : null);
    source.count = groups.some(function (group) { return Number.isInteger(group.counts.total); })
      ? groups.reduce(function (sum, group) { return sum + (group.counts.total || 0); }, 0) : null;
    return payload;
  }
  function taskNode(nexus) { return mount.querySelector('[data-task-nexus="' + (nexus || 'alpha') + '"]'); }
  function taskAction(action, nexus) { return taskNode(nexus).querySelector('[data-task-action="' + action + '"]'); }
  function taskInput(name, value, nexus) {
    var input = taskNode(nexus).querySelector('[data-task-focus="' + name + '"]');
    input.value = value;
    input.dispatchEvent(new w.Event('input', { bubbles: true }));
    return input;
  }
  function taskSelect(index, nexus) { taskNode(nexus).querySelectorAll('[data-task-action="select"]')[index].click(); }
  async function openTasks(groups, qualification, error) {
    if (!mount.hidden) {
      for (var cancel of mount.querySelectorAll('[data-task-action="cancel"]')) cancel.click();
      closeControl.click();
    }
    responses.push(ok(taskPayload(groups, qualification, error)));
    launcher.click(); await flush(); await flush();
  }
  function savedTaskGroup(group, operation, fields) {
    var next = taskGroup(group.nexus, 2);
    var correspondence = {};
    group.tasks.forEach(function (task, index) { correspondence[task.ref] = next.tasks[index].ref; });
    var index = group.tasks.findIndex(function (task) { return task.ref === fields.target; });
    if (operation === 'edit') next.tasks[index].text = fields.value;
    if (operation === 'set-date') next.tasks[index].completion_date = fields.value;
    if (operation === 'clear-date') next.tasks[index].completion_date = null;
    if (operation === 'complete') next.tasks[index].done = true;
    if (operation === 'reopen') next.tasks[index].done = false;
    if (operation === 'add') {
      var added = Object.assign({}, next.tasks[2], { ref: next.identity + ':' + next.digest + ':added', text: fields.value });
      next.tasks.push(added);
      correspondence.added = added.ref;
      next.counts.total += 1;
    }
    if (operation === 'delete') {
      delete correspondence[group.tasks[index].ref];
      next.tasks.splice(index, 1);
      next.counts.total -= 1;
    }
    return { ok: true, saved: true, changed: true, group: next, correspondence: correspondence,
      focus_ref: operation === 'add' ? correspondence.added : index >= 0 && operation !== 'delete' ? correspondence[group.tasks[index].ref] : null };
  }
  var alpha = taskGroup('alpha'); var beta = taskGroup('beta');
  await openTasks([alpha, beta]);
  assert.strictEqual(taskNode().querySelector('script'), null, 'opaque Markdown is never executable');
  assert.strictEqual(taskNode().querySelector('pre').textContent, alpha.source_text);
  assert(taskNode().textContent.includes('Level 2') && taskNode().textContent.includes('Child of task 1'));
  assert(taskNode().textContent.includes('Completed'), 'completed tasks stay reachable');
  assert.deepStrictEqual(Array.from(mount.querySelectorAll('[data-task-nexus]')).map(function (node) { return node.dataset.taskNexus; }), ['alpha', 'beta']);

  // Every deliberate action uses one exact service operation and source reference.
  for (var actionCase of [
    ['edit', 'edit', 2, { value: 'Changed duplicate only' }, 'text'],
    ['move-earlier', 'reorder', 2, { destination: alpha.tasks[0].ref, position: 'before' }],
    ['move-later', 'reorder', 2, { destination: alpha.tasks[3].ref, position: 'after' }],
    ['indent', 'indent', 2, {}], ['outdent', 'outdent', 1, {}], ['promote', 'promote', 1, {}],
    ['complete', 'complete', 2, {}], ['reopen', 'reopen', 3, {}],
    ['set-date', 'set-date', 2, { value: '2026-09-03' }, 'date'],
    ['clear-date', 'clear-date', 3, {}], ['delete', 'delete', 2, {}],
  ]) {
    await openTasks([alpha, beta]);
    taskSelect(0, 'beta'); taskInput('text', 'Other group draft', 'beta');
    var otherGroup = taskNode('beta');
    var otherCards = Array.from(cardsHost.children);
    var ring = mount.querySelector('.overview-projects');
    taskSelect(actionCase[2]);
    if (actionCase[4]) taskInput(actionCase[4], actionCase[3].value);
    var fields = Object.assign({ target: alpha.tasks[actionCase[2]].ref }, actionCase[3]);
    var result = savedTaskGroup(alpha, actionCase[1], fields);
    var pendingTask = deferred(); responses.push(pendingTask.promise);
    var before = requests.length;
    var action = taskAction(actionCase[0]); action.focus(); action.click(); action.click();
    taskAction(actionCase[0]).click();
    assert.strictEqual(requests.length, before + 1, actionCase[0] + ' suppresses duplicate requests');
    assert.strictEqual(requests[before][0], '/api/projects/alpha/tasks');
    assert.strictEqual(requests[before][1].method, 'POST');
    assert.deepStrictEqual(JSON.parse(requests[before][1].body), Object.assign({ expected_digest: alpha.digest, operation: actionCase[1] }, fields));
    assert.strictEqual(taskNode('beta'), otherGroup, 'pending work leaves other groups mounted');
    assert.strictEqual(taskAction('edit', 'beta').disabled, false);
    assert.strictEqual(mount.querySelector('[data-overview-action="read_note"]').disabled, false);
    pendingTask.resolve(ok(result)); await flush(); await flush();
    assert.strictEqual(taskNode('beta'), otherGroup, 'success replaces only the changed group');
    assert.strictEqual(taskNode('beta').querySelector('[data-task-focus="text"]').value, 'Other group draft');
    assert.deepStrictEqual(Array.from(cardsHost.children), otherCards, 'success preserves all card identities');
    assert.strictEqual(mount.querySelector('.overview-projects'), ring);
    assert(taskNode().contains(w.document.activeElement), 'success restores focus to the changed group');
    if (actionCase[1] !== 'delete') {
      assert.strictEqual(taskNode().querySelector('[aria-pressed="true"]').dataset.taskFocus, 'select:' + result.correspondence[fields.target]);
    }
    assertWorkspacePreserved('task ' + actionCase[0]);
  }
  for (var position of ['root', 'before', 'after', 'child']) {
    await openTasks([alpha, beta]);
    taskAction('add').click();
    if (position !== 'root') {
      var placement = taskNode().querySelector('[data-task-focus="placement"]');
      // Root is option value 0; each task has before/after/child choices.
      placement.value = String(1 + 2 * 3 + ['before', 'after', 'child'].indexOf(position));
      placement.dispatchEvent(new w.Event('change', { bubbles: true }));
    }
    taskInput('text', 'New task');
    var fields = { destination: position === 'root' ? alpha.root_ref : alpha.tasks[2].ref, position: position, value: 'New task' };
    responses.push(ok(savedTaskGroup(alpha, 'add', fields)));
    var before = requests.length; taskAction('save-add').click(); await flush(); await flush();
    assert.strictEqual(requests.length, before + 1);
    assert.deepStrictEqual(JSON.parse(requests[before][1].body), Object.assign({ expected_digest: alpha.digest, operation: 'add' }, fields));
    assert.strictEqual(taskAction('cancel'), null, 'successful Add clears only its submitted draft');
    assert.strictEqual(w.document.activeElement.dataset.taskFocus, 'select:' + taskGroup('alpha', 2).identity + ':' + taskGroup('alpha', 2).digest + ':added', 'Add focuses its returned new task');
  }

  await openTasks([alpha, beta]); taskSelect(0);
  assert.strictEqual(taskAction('delete').disabled, true);
  assert(taskNode().textContent.includes('Delete task: Move or promote children first.'));
  assert.strictEqual(taskAction('indent').disabled, true, 'first sibling indent is explained locally');
  taskSelect(2); taskInput('text', 'Retained text'); taskInput('date', '2026-09-04');
  responses.push(reply(400, { ok: false, saved: false, code: 'refused', error: 'Keep this original syntax.' }));
  taskAction('edit').click(); await flush(); await flush();
  assert(taskNode().textContent.includes('Keep this original syntax.'));
  assert.strictEqual(taskNode().querySelector('[data-task-focus="text"]').value, 'Retained text');
  assert.strictEqual(taskNode().querySelector('[data-task-focus="date"]').value, '2026-09-04');
  assert.strictEqual(taskAction('edit').disabled, false, 'safe refusal leaves correction usable');
  responses.push(reply(409, { ok: false, saved: false, code: 'conflict', error: 'The Matrix changed.' }));
  taskAction('edit').click(); await flush(); await flush();
  assert(taskNode().textContent.includes('The Matrix changed.'));
  assert.strictEqual(taskAction('edit').disabled, true);
  var refreshed = taskGroup('alpha', 3);
  responses.push(ok({ ok: true, group: refreshed }));
  var refreshIndex = requests.length; taskAction('refresh').click(); await flush(); await flush();
  assert.strictEqual(requests[refreshIndex][0], '/api/projects/alpha/tasks');
  assert.strictEqual(requests[refreshIndex][1].method, 'GET');
  assert.strictEqual(requests[refreshIndex][1].body, undefined);
  assert.strictEqual(taskNode().querySelector('[data-task-focus="text"]').value, 'Retained text');
  assert.strictEqual(taskAction('edit').disabled, true, 'refresh never silently rebinds a duplicate label');
  var retarget = taskNode().querySelector('[data-task-focus="retarget"]');
  retarget.value = refreshed.tasks[2].ref; retarget.dispatchEvent(new w.Event('change', { bubbles: true }));
  assert.strictEqual(taskAction('edit').disabled, false);
  assert.strictEqual(taskNode().querySelector('[data-task-focus="text"]').value, 'Retained text');
  var rebound = savedTaskGroup(refreshed, 'edit', { target: refreshed.tasks[2].ref, value: 'Retained text' });
  responses.push(ok(rebound)); var retargetIndex = requests.length;
  taskAction('edit').click(); await flush(); await flush();
  assert.deepStrictEqual(JSON.parse(requests[retargetIndex][1].body), { expected_digest: refreshed.digest, operation: 'edit', target: refreshed.tasks[2].ref, value: 'Retained text' });
  assert.strictEqual(taskNode().querySelector('[data-task-focus="date"]').value, '2026-09-04', 'saving text preserves an independent date draft');

  for (var failure of [
    new Error('private transport error'),
    { ok: true, status: 200, json: function () { return Promise.reject(new Error('malformed JSON')); } },
    ok({ ok: true, saved: true, changed: true, group: taskGroup('beta'), correspondence: {}, focus_ref: null }),
    ok({ ok: true, saved: true, changed: true, group: taskGroup('alpha', 2), correspondence: {}, focus_ref: null }),
    reply(500, { ok: false, code: 'unknown-outcome', saved: null, error: 'Cannot confirm.' }),
    reply(503, { error: 'An unclassified response is not proof of no write.' }),
  ]) {
    await openTasks([alpha, beta]); taskSelect(2); taskInput('text', 'Keep after uncertainty');
    responses.push(failure); var before = requests.length; taskAction('edit').click(); await flush(); await flush();
    assert.strictEqual(requests.length, before + 1, 'unknown outcomes are never replayed');
    assert(taskNode().textContent.includes('outcome is unknown'));
    assert.strictEqual(taskAction('edit').disabled, true);
    assert.strictEqual(taskNode().querySelector('[data-task-focus="text"]').value, 'Keep after uncertainty');
    assert.strictEqual(taskNode().textContent.includes('private transport'), false);
  }

  await openTasks([alpha, beta]); taskSelect(2); taskInput('text', 'Close and reopen draft'); taskInput('date', '2026-09-05');
  var delayedSave = deferred(); responses.push(delayedSave.promise);
  taskAction('edit').click(); var saveSignal = requests[requests.length - 1][1].signal;
  w.document.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  assert(saveSignal.aborted, 'close aborts the task request without claiming cancellation');
  responses.push(ok(taskPayload([taskGroup('alpha', 3), beta]))); launcher.click(); await flush(); await flush();
  var reopened = taskNode();
  assert.strictEqual(reopened.querySelector('[data-task-focus="text"]').value, 'Close and reopen draft');
  assert.strictEqual(reopened.querySelector('[data-task-focus="date"]').value, '2026-09-05');
  assert.strictEqual(taskAction('edit').disabled, true, 'reopening requires an explicit target selection');
  delayedSave.resolve(ok(savedTaskGroup(alpha, 'edit', { target: alpha.tasks[2].ref, value: 'Late old response' })));
  await flush(); await flush();
  assert.strictEqual(taskNode(), reopened, 'late response cannot replace a reopened group');
  assert.strictEqual(reopened.querySelector('[data-task-focus="text"]').value, 'Close and reopen draft');

  // A retained Add draft needs a deliberate current position, even at root.
  await openTasks([alpha, beta]); taskAction('add').click(); taskInput('text', 'Retained new task');
  closeControl.click();
  responses.push(ok(taskPayload([taskGroup('alpha', 3), beta]))); launcher.click(); await flush(); await flush();
  assert.strictEqual(taskNode().querySelector('[data-task-focus="text"]').value, 'Retained new task');
  assert.strictEqual(taskAction('save-add').disabled, true);
  taskSelect(0);
  assert.strictEqual(taskNode().querySelector('[data-task-focus="text"]').value, 'Retained new task', 'selecting a row cannot replace an unbound Add draft');
  var addPosition = taskNode().querySelector('[data-task-focus="placement"]');
  addPosition.value = '0'; addPosition.dispatchEvent(new w.Event('change', { bubbles: true }));
  assert.strictEqual(taskAction('save-add').disabled, false);
  taskAction('cancel').click();

  await openTasks([alpha, beta]); taskSelect(2);
  var noChangeMap = {}; alpha.tasks.forEach(function (row) { noChangeMap[row.ref] = row.ref; });
  responses.push(ok({ ok: true, saved: false, changed: false, group: alpha, correspondence: noChangeMap, focus_ref: alpha.tasks[2].ref }));
  var noChangeBefore = requests.length; taskAction('edit').click(); await flush(); await flush();
  assert.strictEqual(requests.length, noChangeBefore + 1);
  assert(taskNode().textContent.includes('No change was needed.'));

  // Identity can change on explicit reading; a save cannot claim that rebound identity.
  var changedIdentity = JSON.parse(JSON.stringify(taskGroup('alpha', 3)).replaceAll('a'.repeat(24), 'c'.repeat(24)));
  taskInput('text', 'Retain after storage change');
  responses.push(ok({ ok: true, group: changedIdentity })); taskAction('refresh').click(); await flush(); await flush();
  assert.strictEqual(taskNode().querySelector('[data-task-focus="text"]').value, 'Retain after storage change');
  assert.strictEqual(taskAction('edit').disabled, true);
  retarget = taskNode().querySelector('[data-task-focus="retarget"]');
  retarget.value = changedIdentity.tasks[2].ref; retarget.dispatchEvent(new w.Event('change', { bubbles: true }));
  assert.strictEqual(taskAction('edit').disabled, false, 'explicit selection binds the newly read identity');
  var reboundResult = savedTaskGroup(alpha, 'edit', { target: alpha.tasks[2].ref, value: 'Retain after storage change' });
  responses.push(ok(reboundResult)); taskAction('edit').click(); await flush(); await flush();
  assert(taskNode().textContent.includes('outcome is unknown'), 'a same-nexus wrong-identity save result is discarded');

  // Read hides the same mounted Tasks state, and a save response cannot steal reader focus.
  await openTasks([alpha, beta]); taskSelect(2); taskInput('text', 'Save while reading');
  var whileRead = deferred(); responses.push(whileRead.promise); taskAction('edit').click();
  responses.push(ok(readPayload)); readAction = mount.querySelector('[data-overview-action="read_note"]'); readAction.click();
  await flush(); await flush();
  whileRead.resolve(ok(savedTaskGroup(alpha, 'edit', { target: alpha.tasks[2].ref, value: 'Save while reading' })));
  await flush(); await flush();
  assert.strictEqual(w.document.activeElement, back);
  var mountedTasks = taskNode(); back.click();
  assert.strictEqual(taskNode(), mountedTasks);
  assert.strictEqual(taskNode().querySelector('[data-task-focus="text"]').value, 'Save while reading');
  taskInput('date', '2026-09-06');
  responses.push(ok(readPayload)); readAction.click(); await flush(); await flush(); back.click();
  assert.strictEqual(taskNode(), mountedTasks);
  assert.strictEqual(taskNode().querySelector('[data-task-focus="date"]').value, '2026-09-06');

  var missing = { nexus: 'missing', title: 'Missing Matrix', item_id: 'project:missing', scope: { project_nexus: 'missing' },
    state: 'unavailable', editable: false, reason: 'No Matrix storage is available.', identity: null, digest: null,
    root_ref: null, source_text: null, tasks: [], counts: { total: null, completed: null, incomplete: null }, actions: ['open_project'] };
  await openTasks([missing], 'unavailable');
  assert(mount.querySelector('.overview-tasks .overview-source__meta').textContent.includes('Task count unavailable'));
  assert.strictEqual(taskAction('add', 'missing').disabled, true);
  assert(taskNode('missing').textContent.includes('No Matrix storage is available.'));
  assert.strictEqual(taskNode('missing').querySelector('[data-overview-action="open_project"]').disabled, false);
  var readOnly = taskGroup('alpha'); readOnly.editable = false; readOnly.state = 'read-only'; readOnly.reason = 'Correct the list-form classification.';
  await openTasks([readOnly, beta, missing], 'partial');
  assert(mount.querySelector('.overview-tasks .overview-source__meta').textContent.includes('8 known tasks'));
  taskSelect(2); assert.strictEqual(taskAction('edit').disabled, true);
  assert.strictEqual(taskAction('add', 'beta').disabled, false, 'one bad Matrix does not disable healthy groups');
  var tasksCard = mount.querySelector('.overview-tasks');
  var tasksWarning = tasksCard.querySelector('.overview-tasks__error');
  var healthyGroup = taskNode('beta');
  responses.push(ok({ ok: true, group: alpha })); taskAction('refresh').click(); await flush(); await flush();
  assert.strictEqual(tasksCard.dataset.state, 'partial', 'a still-unavailable group keeps the inventory partial');
  assert.strictEqual(tasksWarning.hidden, false);
  responses.push(ok({ ok: true, group: taskGroup('missing') })); taskAction('refresh', 'missing').click(); await flush(); await flush();
  assert.strictEqual(tasksCard.dataset.state, 'ready', 'repairing every group clears the old partial state');
  assert.strictEqual(tasksCard.querySelector('.overview-source__state').textContent, 'ready');
  assert(tasksCard.querySelector('.overview-source__meta').textContent.includes('12 tasks · Refreshed project results'));
  assert.strictEqual(tasksWarning.hidden, true);
  assert.strictEqual(tasksWarning.textContent, '', 'the obsolete warning is cleared');
  assert.strictEqual(taskNode('beta'), healthyGroup, 'qualification refresh leaves other groups mounted');
  responses.push(ok({ ok: true, group: readOnly })); taskAction('refresh').click(); await flush(); await flush();
  assert.strictEqual(tasksCard.dataset.state, 'partial', 'a new group limitation restores partial qualification');
  assert.strictEqual(tasksWarning.hidden, false);
  assert(tasksWarning.textContent.includes('Known task counts only'));

  var inventoryError = { code: 'project_records_skipped', message: 'Unreadable project records: broken.json' };
  await openTasks([readOnly, beta], 'partial', inventoryError);
  responses.push(ok({ ok: true, group: alpha })); taskAction('refresh').click(); await flush(); await flush();
  tasksCard = mount.querySelector('.overview-tasks');
  assert.strictEqual(tasksCard.dataset.state, 'partial', 'refreshing known groups cannot repair a skipped project record');
  assert(tasksCard.querySelector('.overview-source__meta').textContent.includes('8 known tasks · Partial inventory'));
  assert.strictEqual(tasksCard.querySelector('.overview-tasks__error').hidden, false);
  assert.strictEqual(tasksCard.querySelector('.overview-tasks__error').textContent, inventoryError.message);
  var malformedGroup = taskGroup('alpha'); malformedGroup.scope.project_nexus = '../alpha';
  await openTasks([malformedGroup, beta]);
  assert.strictEqual(taskNode('alpha'), null);
  assert(taskNode('beta'));
  assert(mount.querySelector('[data-overview-action="read_note"]'));
  await openTasks([alpha, beta]); taskSelect(2); taskInput('text', 'Page teardown draft');
  var teardownSave = deferred(); responses.push(teardownSave.promise); taskAction('edit').click();
  var teardownNode = taskNode(); var teardownSignal = requests[requests.length - 1][1].signal;
  w.dispatchEvent(new w.Event('pagehide'));
  assert.strictEqual(teardownSignal.aborted, true);
  teardownSave.resolve(ok(savedTaskGroup(alpha, 'edit', { target: alpha.tasks[2].ref, value: 'Late after teardown' })));
  await flush(); await flush();
  assert.strictEqual(taskNode(), teardownNode, 'page teardown invalidates late mutation responses');
  closeControl.click();

  console.log('overview desktop tests passed');
})().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
}).finally(function () {
  dom.window.close();
});
