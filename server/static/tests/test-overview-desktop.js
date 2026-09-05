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
    title: 'Ora', text: 'Active', state: 'ready', time: null, count: null,
    scope: { project_nexus: 'ora' }, actions: ['open_project'],
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
    ],
    'the four sources render in canonical order with their distinct states'
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
    actions.length, 2,
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
  assert.strictEqual(status.textContent, 'Four sources checked.', 'opening clears prior handoff status');
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
  assert.strictEqual(mount.querySelectorAll('.overview-source').length, 4, 'failure preserves all cards');
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
  assert.strictEqual(status.textContent, 'Four sources checked.');
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
  assert.strictEqual(status.textContent, 'Four sources checked.');

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
  assert.deepStrictEqual(Array.from(cardsHost.children), cards, 'Read never rebuilds the four cards');
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

  console.log('overview desktop tests passed');
})().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
}).finally(function () {
  dom.window.close();
});
