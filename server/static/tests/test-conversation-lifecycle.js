#!/usr/bin/env node
/* Focused jsdom coverage for live Dialogue lifecycle controls. */
'use strict';

var fs = require('fs');
var path = require('path');
var vm = require('vm');

var modules = path.resolve(
  __dirname, '..', 'ora-visual-compiler', 'tests', 'node_modules'
);
var jsdom;
try {
  jsdom = require(path.join(modules, 'jsdom'));
} catch (e) {
  console.error('error: jsdom not available at ' + modules);
  process.exit(2);
}

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body>' +
  '<div class="left-sidebar"><button class="sidebar-fork-thread-cmd" disabled>Fork</button></div>' +
  '<div class="output-pane">' +
  '  <span id="outputPaneDisplayName">Dialogue</span>' +
  '  <span id="outputPaneModeIcon"></span>' +
  '  <button id="outputPaneActionsBtn" hidden></button>' +
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
var calls = [];
var confirmations = [];
var alerts = [];
var tagEvents = [];
var lifecycleEvents = [];
var lifecycleChannelMessages = [];
var lifecycleChannels = [];
var lateResolve = null;
var pendingBResolve = null;
var forkResolve = null;
var slowCloseResolve = null;
var concurrentDeleteResolve = null;
var envelopes = {
  retained: {
    conversation_id: 'retained',
    tag: '',
    display_name: 'Retained',
    messages: [
      { role: 'user', content: 'Question' },
      { role: 'assistant', content: 'Answer' },
    ],
  },
  stealth: {
    conversation_id: 'stealth',
    tag: 'stealth',
    display_name: 'Stealth',
    messages: [
      { role: 'user', content: 'Secret' },
      { role: 'assistant', content: 'Response' },
    ],
  },
  forkParent: {
    conversation_id: 'fork-parent',
    tag: '',
    display_name: 'Fork parent',
    messages: [
      { role: 'user', content: 'Parent question' },
      { role: 'assistant', content: 'Parent answer' },
    ],
  },
  slowClose: {
    conversation_id: 'slow-close',
    tag: '',
    display_name: 'Slow close',
    messages: [
      { role: 'user', content: 'Wait for this close' },
      { role: 'assistant', content: 'Waiting' },
    ],
  },
  archive: {
    conversation_id: 'archive-source',
    archived_source: true,
    tag: '',
    display_name: 'Archived source',
    messages: [
      { role: 'user', content: 'Archived question' },
      { role: 'assistant', content: 'Archived answer' },
    ],
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

w.confirm = function (message) {
  confirmations.push(message);
  return true;
};
w.BroadcastChannel = function FakeBroadcastChannel(name) {
  this.name = name;
  this.onmessage = null;
  this.closed = false;
  lifecycleChannels.push(this);
};
w.BroadcastChannel.prototype.postMessage = function (payload) {
  lifecycleChannelMessages.push({ channel: this.name, payload: payload });
};
w.BroadcastChannel.prototype.close = function () {
  this.closed = true;
};
w.alert = function (message) {
  alerts.push(String(message));
};
w.fetch = function (url, opts) {
  var decoded = decodeURIComponent(String(url));
  opts = opts || {};
  calls.push({ url: decoded, opts: opts });

  if (decoded === '/api/conversation/late') {
    return new Promise(function (resolve) { lateResolve = resolve; });
  }
  if (decoded === '/api/conversation/pending-b') {
    return new Promise(function (resolve) { pendingBResolve = resolve; });
  }
  if (decoded === '/api/conversation/fork-parent/fork') {
    return new Promise(function (resolve) { forkResolve = resolve; });
  }
  if (decoded === '/api/conversation/slow-close/close') {
    return new Promise(function (resolve) { slowCloseResolve = resolve; });
  }
  if (decoded === '/api/conversation/concurrent-delete/delete-forever') {
    return new Promise(function (resolve) { concurrentDeleteResolve = resolve; });
  }
  if (decoded === '/api/conversation/retained') return response(true, envelopes.retained);
  if (decoded === '/api/conversation/stealth') return response(true, envelopes.stealth);
  if (decoded === '/api/conversation/fork-parent') return response(true, envelopes.forkParent);
  if (decoded === '/api/conversation/slow-close') return response(true, envelopes.slowClose);
  if (decoded === '/api/conversation/archive-source') return response(true, envelopes.archive);
  if (decoded === '/api/conversation/other-row') {
    return response(true, { conversation_id: 'other-row', tag: '', messages: [] });
  }
  if (decoded === '/api/conversation/stealth-row') {
    return response(true, { conversation_id: 'stealth-row', tag: 'stealth', messages: [] });
  }
  if (decoded === '/api/conversation/timer-a') {
    return response(true, { conversation_id: 'timer-a', tag: '', messages: [] });
  }
  if (decoded.indexOf('/api/canvas/load/') === 0) return response(false, {}, 404);
  if (/\/mark-read$/.test(decoded)) return response(true, { ok: true });
  if (/\/privacy-tag$/.test(decoded)) {
    var privacyBody = JSON.parse(opts.body || '{}');
    envelopes.retained.tag = privacyBody.tag;
    return response(true, { ok: true, tag: privacyBody.tag, errors: [] });
  }
  if (/\/delete-forever$/.test(decoded)) {
    var disclosure = /\/fresh-delete\/delete-forever$/.test(decoded) ? {
      external_provider_retention: 'Remote provider copies follow provider retention.',
      repository_history: 'Git and backup history is not rewritten.',
    } : undefined;
    return response(true, {
      action: 'delete_forever', errors: [], limitations: disclosure,
    });
  }
  if (/\/close$/.test(decoded)) {
    return response(true, { action: 'close', errors: [] });
  }
  return Promise.reject(new Error('unexpected fetch: ' + decoded));
};

var context = dom.getInternalVMContext();
context.fetch = w.fetch;
context.confirm = w.confirm;
context.alert = w.alert;
context.console = console;
vm.runInContext(
  fs.readFileSync(path.resolve(__dirname, '..', 'js', 'v3-conversation.js'), 'utf8'),
  context,
  { filename: 'v3-conversation.js' }
);
w.document.dispatchEvent(new w.Event('DOMContentLoaded'));
w.document.addEventListener('ora:conversation-tag-changed', function (event) {
  tagEvents.push(event.detail || {});
});
w.document.addEventListener('ora:conversation-lifecycle-completed', function (event) {
  lifecycleEvents.push(event.detail || {});
});

var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? ' - ' + detail : ''));
}
function wait(ms) {
  return new Promise(function (resolve) { w.setTimeout(resolve, ms || 0); });
}

function sourceSlice(source, startMarker, endMarker) {
  var start = source.indexOf(startMarker);
  var end = source.indexOf(endMarker, start + startMarker.length);
  if (start < 0 || end < 0) {
    throw new Error('could not extract index lifecycle source: ' + startMarker);
  }
  return source.slice(start, end);
}

async function runIndexLifecycleControlsTests() {
  var indexSource = fs.readFileSync(
    path.resolve(__dirname, '..', '..', 'index-v3.html'), 'utf8'
  );
  var parsedIndex = new jsdom.JSDOM(indexSource).window.document;
  var parsedStealthTrigger = parsedIndex.getElementById('modeBtnStealth');
  var parsedOutputTrigger = parsedIndex.getElementById('outputPaneActionsBtn');
  record('menu triggers declare their controlled menu semantics',
    parsedStealthTrigger.getAttribute('aria-haspopup') === 'menu'
      && parsedStealthTrigger.getAttribute('aria-controls') === 'oraModeDropdown'
      && parsedOutputTrigger.getAttribute('aria-controls') === 'outputPaneActionsMenu');
  var modeDom = new jsdom.JSDOM(
    '<!doctype html><html><body>'
      + '<button class="spine-button" data-mode-button="stealth" '
      + 'id="modeBtnStealth" aria-expanded="false"></button>'
      + '<button class="spine-button" data-mode-button="private" '
      + 'id="modeBtnPrivate" aria-expanded="false"></button>'
      + '<span id="bridgeModeLabel"></span><span id="bridgeModeLabelRight"></span>'
      + '<span id="bridgeQAMessage"></span>'
      + '<div class="input-pane"><textarea></textarea></div>'
      + '<div class="chat-input-pane"><textarea></textarea></div>'
      + '<button id="outputPaneActionsBtn" aria-expanded="false"></button>'
      + '</body></html>',
    { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
  );
  var mw = modeDom.window;
  var activeId = 'stealth-a';
  var activeTag = 'stealth';
  var deleteCalls = [];
  var modeAlerts = [];
  mw.OraConversation = {
    getActiveConversationId: function () { return activeId; },
    getActiveTag: function () { return activeTag; },
    isReadOnly: function () { return false; },
    canFork: function () { return true; },
    setPrivacyTag: function () { return Promise.resolve({ ok: true }); },
    deleteForever: function (id) { deleteCalls.push(id); return Promise.resolve({ ok: true }); },
  };
  mw.alert = function (message) { modeAlerts.push(message); };
  var modeContext = modeDom.getInternalVMContext();
  modeContext.console = console;
  modeContext.bracketLeft = mw.document.createElement('span');
  modeContext.bracketRight = mw.document.createElement('span');

  var modeCore = sourceSlice(
    indexSource,
    "  const modeLabel       = document.getElementById('bridgeModeLabel');",
    '  // ─── Pane-mode buttons (Audio/Video Phase 1)'
  );
  var modeLifecycle = sourceSlice(
    indexSource,
    '  // Close dropdown on outside click or Escape.',
    "  rightInputArea.addEventListener('focus', updateQAMessage);"
  );
  vm.runInContext(modeCore, modeContext, { filename: 'index-mode-core.js' });
  vm.runInContext(modeLifecycle, modeContext, { filename: 'index-mode-lifecycle.js' });

  var stealthButton = mw.document.getElementById('modeBtnStealth');
  stealthButton.click();
  var menu = mw.document.getElementById('oraModeDropdown');
  record('spine mode menu exposes ARIA state and focuses its first item',
    stealthButton.getAttribute('aria-expanded') === 'true'
      && mw.document.activeElement.textContent === 'New stealth');
  mw.document.activeElement.dispatchEvent(new mw.KeyboardEvent('keydown', {
    key: 'End', bubbles: true,
  }));
  record('spine mode menu supports keyboard navigation',
    mw.document.activeElement.dataset.action === 'delete-forever');
  mw.document.activeElement.dispatchEvent(new mw.KeyboardEvent('keydown', {
    key: 'Escape', bubbles: true,
  }));
  record('spine mode menu Escape restores trigger focus',
    !mw.OraModeMenu.isOpen()
      && stealthButton.getAttribute('aria-expanded') === 'false'
      && mw.document.activeElement === stealthButton);

  stealthButton.click();
  mw.document.activeElement.dispatchEvent(new mw.KeyboardEvent('keydown', {
    key: 'Tab', bubbles: true,
  }));
  record('spine mode menu Tab closes and advances from its trigger',
    !mw.OraModeMenu.isOpen()
      && mw.document.activeElement === mw.document.getElementById('modeBtnPrivate'));

  stealthButton.click();
  mw.document.getElementById('modeBtnPrivate').focus();
  record('spine mode menu closes when focus leaves the popup',
    !mw.OraModeMenu.isOpen());

  stealthButton.click();
  activeId = 'newer-dialogue';
  menu.querySelector('[data-action="delete-forever"]').click();
  record('stale destructive mode action cannot target a newer Dialogue',
    deleteCalls.length === 0
      && modeAlerts.length === 1
      && mw.document.activeElement === stealthButton);

  activeId = 'stealth-a';
  stealthButton.click();
  menu.querySelector('[data-action="delete-forever"]').click();
  record('mode Delete Forever is bound to the opening Dialogue id',
    deleteCalls.length === 1
      && deleteCalls[0] === 'stealth-a'
      && mw.document.activeElement === stealthButton);

  stealthButton.click();
  mw.document.dispatchEvent(new mw.CustomEvent('ora:fresh-conversation-started', {
    detail: { conversation_id: 'fresh-standard', tag: '' },
  }));
  record('programmatic navigation closes a stale mode menu',
    !mw.OraModeMenu.isOpen() && stealthButton.getAttribute('aria-expanded') === 'false');

  var inquiryDom = new jsdom.JSDOM(
    '<!doctype html><html><body><div class="input-pane">'
      + '<button id="inputToolbarAttach"></button>'
      + '<input id="inputToolbarAttachFile" type="file">'
      + '</div></body></html>',
    { url: 'http://localhost/', runScripts: 'outside-only' }
  );
  var iw = inquiryDom.window;
  var inquiryAlerts = [];
  var inquiryBusy = false;
  iw.OraConversation = {
    isReadOnly: function () { return true; },
    isLoading: function () { return false; },
    isLifecycleBusy: function () { return inquiryBusy; },
  };
  iw.alert = function (message) { inquiryAlerts.push(message); };
  var inquiryContext = inquiryDom.getInternalVMContext();
  var inquirySource = sourceSlice(
    indexSource,
    '  const inquiryMutationBlockMessage = () => {',
    '  // V3 Backlog 8 — turn rendering goes through OraConversation now'
  );
  vm.runInContext(inquirySource, inquiryContext, { filename: 'index-inquiry-lifecycle.js' });
  iw.OraInquiryLifecycle.syncAttachmentSurface();
  record('read-only Inquiry disables the attachment surface',
    iw.document.getElementById('inputToolbarAttach').disabled
      && iw.document.getElementById('inputToolbarAttachFile').disabled
      && iw.document.querySelector('.input-pane').classList.contains('is-attachment-read-only'));
  record('read-only Inquiry mutation guard explains the block',
    iw.OraInquiryLifecycle.requireMutable() === false
      && inquiryAlerts[0].indexOf('read-only') !== -1);
  inquiryBusy = true;
  record('in-flight lifecycle mutation gets a distinct Inquiry guard',
    iw.OraInquiryLifecycle.blockMessage().indexOf('lifecycle change') !== -1);

  record('file batches are guarded before attachment dispatch',
    /const dispatchFiles = \(files\) => \{[\s\S]*?!requireMutableInquiry\(\)/
      .test(indexSource));

  var attachmentDom = new jsdom.JSDOM(
    '<!doctype html><html><body>'
      + '<div class="input-pane"><div id="inputPaneAttachments"></div></div>'
      + '</body></html>',
    { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
  );
  var aw = attachmentDom.window;
  var activeAttachmentId = 'attach-a';
  var pendingDocumentResolve = null;
  aw.OraDocumentInput = {
    isDocumentFile: function (file) { return /\.pdf$/i.test(file.name || ''); },
    acceptFile: function (file, host) {
      return new Promise(function (resolve) {
        pendingDocumentResolve = function () {
          var chip = aw.document.createElement('div');
          chip.dataset.documentId = 'doc-a';
          var close = aw.document.createElement('button');
          close.className = 'transcribe-chip__close';
          close.addEventListener('click', function () { chip.remove(); });
          chip.appendChild(close);
          host.appendChild(chip);
          resolve('doc-a');
        };
      });
    },
  };
  var attachmentContext = attachmentDom.getInternalVMContext();
  attachmentContext.console = console;
  attachmentContext.currentConversationId = function () { return activeAttachmentId; };
  attachmentContext.currentTag = function () { return ''; };
  attachmentContext.requireMutableInquiry = function () { return true; };
  attachmentContext.inquiryMutationBlockMessage = function () { return ''; };
  attachmentContext.syncAttachmentSurfaceAvailability = function () {};
  var attachmentSource = sourceSlice(
    indexSource,
    "  const _attachmentRow = document.getElementById('inputPaneAttachments');",
    '  // ─── V3 Input Handling Phase 5 — bridge selection label'
  );
  vm.runInContext(attachmentSource, attachmentContext, {
    filename: 'index-attachment-lifecycle.js',
  });

  aw.OraInputAttachments.addFiles([
    { name: 'queued.pdf', type: 'application/pdf', size: 12 },
  ]);
  activeAttachmentId = 'attach-b';
  aw.document.dispatchEvent(new aw.CustomEvent('ora:conversation-selected', {
    detail: { conversation_id: 'attach-b' },
  }));
  pendingDocumentResolve();
  await new Promise(function (resolve) { setTimeout(resolve, 0); });
  record('delayed attachment completion cannot land in a newer Dialogue',
    aw.OraInputAttachments.list().length === 0
      && !aw.document.querySelector('[data-document-id="doc-a"]'));

  aw.OraInputAttachments.addFiles([
    { name: 'current.pdf', type: 'application/pdf', size: 14 },
  ]);
  pendingDocumentResolve();
  await new Promise(function (resolve) { setTimeout(resolve, 0); });
  var currentDocumentClose = aw.document.querySelector(
    '[data-document-id="doc-a"] .transcribe-chip__close'
  );
  var currentDocumentWasTracked = aw.OraInputAttachments.list().length === 1;
  currentDocumentClose.click();
  record('dismissing an async attachment removes its pending composition entry',
    currentDocumentWasTracked
      && aw.OraInputAttachments.list().length === 0
      && !aw.document.querySelector('[data-document-id="doc-a"]'));

  var mediaOptionsSeen = null;
  aw.OraTranscribeInput = {
    isMediaFile: function (file) { return /^audio\//.test(file.type || ''); },
    acceptFile: function (file, host, options) {
      mediaOptionsSeen = options;
      var chip = aw.document.createElement('div');
      chip.dataset.transcribeId = 'audio-a';
      var close = aw.document.createElement('button');
      close.className = 'transcribe-chip__close';
      close.addEventListener('click', function () { chip.remove(); });
      chip.appendChild(close);
      host.appendChild(chip);
      return Promise.resolve('audio-a');
    },
  };
  aw.OraInputAttachments.addFiles([
    { name: 'voice.mp3', type: 'audio/mpeg', size: 18 },
  ]);
  await new Promise(function (resolve) { setTimeout(resolve, 0); });
  record('media attachment dispatch carries its owning Dialogue identity',
    mediaOptionsSeen
      && mediaOptionsSeen.conversation_id === 'attach-b'
      && mediaOptionsSeen.tag === ''
      && aw.OraInputAttachments.list()[0].conversation_id === 'attach-b');
  aw.document.querySelector('[data-transcribe-id="audio-a"] .transcribe-chip__close').click();

  activeAttachmentId = 'attach-a';
  aw.document.dispatchEvent(new aw.CustomEvent('ora:fresh-conversation-started', {
    detail: { conversation_id: 'attach-a', tag: '' },
  }));
  aw.OraInputAttachments.addFiles([
    { name: 'image.png', type: 'image/png', size: 20 },
  ]);
  var imageAttachedToA = aw.OraInputAttachments.list().length === 1;
  activeAttachmentId = 'attach-b';
  aw.document.dispatchEvent(new aw.CustomEvent('ora:conversation-selected', {
    detail: { conversation_id: 'attach-b' },
  }));
  record('navigation clears the prior Dialogue attachment composition',
    imageAttachedToA
      && aw.OraInputAttachments.list().length === 0
      && aw.document.getElementById('inputPaneAttachments').children.length === 0);

  var hostileUnsupportedName = '<img src=x onerror=alert(1)>.bin';
  aw.OraInputAttachments.addFiles([
    { name: hostileUnsupportedName, type: 'application/octet-stream', size: 3 },
  ]);
  var unsupportedName = aw.document.querySelector('.transcribe-chip__name');
  record('unsupported attachment filename is rendered as text, not markup',
    unsupportedName
      && unsupportedName.textContent === hostileUnsupportedName
      && !unsupportedName.querySelector('img'));
  aw.OraInputAttachments.clear();

  var documentInputSource = fs.readFileSync(
    path.resolve(__dirname, '..', 'js', 'document-input.js'), 'utf8'
  );
  record('document processing reports durable envelope ownership',
    documentInputSource.indexOf('ora:conversation-envelope-created') !== -1
      && documentInputSource.indexOf('envelope_created') !== -1);
  var transcribeInputSource = fs.readFileSync(
    path.resolve(__dirname, '..', 'transcribe-input.js'), 'utf8'
  );
  record('transcription upload forwards correlation and reports envelope ownership',
    transcribeInputSource.indexOf("fd.append('conversation_id'") !== -1
      && transcribeInputSource.indexOf("fd.append('tag'") !== -1
      && transcribeInputSource.indexOf('ora:conversation-envelope-created') !== -1);

  var transcribeDom = new jsdom.JSDOM(
    '<!doctype html><html><body><div id="transcribeHost"></div></body></html>',
    { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
  );
  var tw = transcribeDom.window;
  var transcribeForm = null;
  var transcribeEnvelopeEvent = null;
  var transcribeEnvelopeEventCount = 0;
  var transcribeShouldFail = false;
  tw.setInterval = function () { return 1; };
  tw.clearInterval = function () {};
  tw.fetch = function (url, options) {
    if (String(url) === '/api/transcribe') {
      transcribeForm = options.body;
      if (transcribeShouldFail) {
        return response(false, {
          error: 'start failed',
          conversation_id: 'audio-owner',
          envelope_created: true,
          envelope_available: true,
        }, 500);
      }
      return response(true, {
        transcription_id: 'audio-server',
        conversation_id: 'audio-owner',
        envelope_created: true,
        envelope_available: true,
      });
    }
    if (String(url) === '/api/transcribe/audio-server/state') {
      return response(true, { type: 'complete', vault_path: '' });
    }
    return response(false, {}, 404);
  };
  tw.document.addEventListener('ora:conversation-envelope-created', function (event) {
    transcribeEnvelopeEventCount += 1;
    transcribeEnvelopeEvent = event.detail || {};
  });
  var transcribeContext = transcribeDom.getInternalVMContext();
  transcribeContext.console = console;
  transcribeContext.fetch = tw.fetch;
  vm.runInContext(transcribeInputSource, transcribeContext, {
    filename: 'transcribe-input-lifecycle.js',
  });
  var hostileMediaName = 'voice<img src=x>.mp3';
  await tw.OraTranscribeInput.acceptFile(
    new tw.File(['audio'], hostileMediaName, { type: 'audio/mpeg' }),
    tw.document.getElementById('transcribeHost'),
    { conversation_id: 'audio-owner', tag: 'private' }
  );
  record('transcription client sends multipart identity and emits its envelope event',
    transcribeForm.get('conversation_id') === 'audio-owner'
      && transcribeForm.get('tag') === 'private'
      && transcribeEnvelopeEvent
      && transcribeEnvelopeEvent.conversation_id === 'audio-owner'
      && transcribeEnvelopeEvent.envelope_available === true);
  record('media attachment filename is rendered as text, not markup',
    tw.document.querySelector('.transcribe-chip__name').textContent === hostileMediaName
      && !tw.document.querySelector('.transcribe-chip__name img'));
  var liveTranscriptionJob = tw.OraTranscribeInput.getJobs()['audio-server'];
  record('transcription client does not retain the uploaded File copy',
    liveTranscriptionJob
      && liveTranscriptionJob.file === null
      && liveTranscriptionJob.conversation_id === 'audio-owner');
  transcribeShouldFail = true;
  var eventCountBeforeFailedStart = transcribeEnvelopeEventCount;
  try {
    await tw.OraTranscribeInput.acceptFile(
      new tw.File(['audio'], 'failed.mp3', { type: 'audio/mpeg' }),
      tw.document.getElementById('transcribeHost'),
      { conversation_id: 'audio-owner', tag: 'private' }
    );
  } catch (e) {}
  record('failed transcription start preserves reported envelope ownership',
    transcribeEnvelopeEventCount === eventCountBeforeFailedStart + 1
      && transcribeEnvelopeEvent.conversation_id === 'audio-owner');
  tw.document.dispatchEvent(new tw.CustomEvent('ora:conversation-lifecycle-completed', {
    detail: { conversation_id: 'audio-owner', action: 'delete-forever' },
  }));
  record('Delete Forever removes correlated transcription polling state',
    !Object.keys(tw.OraTranscribeInput.getJobs()).length);

  transcribeShouldFail = false;
  await tw.OraTranscribeInput.acceptFile(
    new tw.File(['audio'], 'dismissed.mp3', { type: 'audio/mpeg' }),
    tw.document.getElementById('transcribeHost'),
    { conversation_id: 'audio-owner', tag: 'private' }
  );
  tw.document.querySelector(
    '[data-transcribe-id="audio-server"] .transcribe-chip__close'
  ).click();
  record('dismissing transcription UI drops its browser polling correlation',
    !Object.keys(tw.OraTranscribeInput.getJobs()).length);
}

async function run() {
  w.document.body.classList.add('stealth-mode');
  w.OraConversation.startFresh({ conversation_id: 'generic-standard' });
  record('generic New ignores the loaded mode and creates Standard',
    w.OraConversation.getActiveTag() === '');
  w.OraConversation.startFresh({ conversation_id: 'explicit-private', tag: 'private' });
  record('explicit tagged New preserves its requested creation tag',
    w.OraConversation.getActiveTag() === 'private');
  calls = [];
  await w.OraConversation.setPrivacyTag('');
  record('fresh privacy mutation still invokes the durable server endpoint',
    calls.some(function (call) {
      return /\/explicit-private\/privacy-tag$/.test(call.url)
        && JSON.parse(call.opts.body || '{}').tag === '';
    }) && w.OraConversation.getActiveTag() === '');
  w.document.body.classList.remove('stealth-mode');

  w.OraConversation.startFresh({ conversation_id: 'fresh-close', tag: '' });
  record('fresh live Dialogue exposes Close/Delete lifecycle actions',
    !w.document.getElementById('outputPaneActionsBtn').hidden);
  calls = [];
  var freshCloseResult = await w.OraConversation.closeConversation('fresh-close');
  record('zero-turn Close delegates local-only detection to the server',
    calls.some(function (call) { return /\/fresh-close\/close$/.test(call.url); })
      && freshCloseResult && freshCloseResult.local_only !== true);

  w.OraConversation.startFresh({ conversation_id: 'fresh-delete', tag: 'stealth' });
  calls = [];
  confirmations = [];
  var freshDeleteResult = await w.OraConversation.deleteForever('fresh-delete');
  record('zero-turn Delete Forever still invokes the server purge',
    calls.some(function (call) {
      return /\/fresh-delete\/delete-forever$/.test(call.url);
    }) && freshDeleteResult && freshDeleteResult.local_only !== true);
  record('Delete Forever surfaces provider and history retention boundaries',
    alerts.some(function (message) {
      return message.indexOf('Remote provider copies') >= 0
        && message.indexOf('Git and backup history') >= 0;
    }));
  var freshDeletePulse = lifecycleChannelMessages[lifecycleChannelMessages.length - 1];
  record('successful Delete Forever emits an ephemeral cross-tab pulse',
    freshDeletePulse
      && freshDeletePulse.channel === 'ora-v3-conversation-lifecycle'
      && freshDeletePulse.payload.action === 'delete-forever'
      && freshDeletePulse.payload.conversation_id === 'fresh-delete'
      && w.localStorage.getItem('ora-v3-conversation-lifecycle-pulse') === null);

  w.localStorage.setItem('ora-v3-draft-archive-source', 'stale archive draft');
  await w.OraConversation.load('archive-source');
  var archiveInput = w.document.querySelector('.input-pane textarea');
  record('archive Inquiry is blank, read-only, and discards stale drafts',
    archiveInput.readOnly
      && archiveInput.value === ''
      && w.localStorage.getItem('ora-v3-draft-archive-source') === null);
  archiveInput.value = 'must not become an archive draft';
  archiveInput.dispatchEvent(new w.Event('input', { bubbles: true }));
  await wait(450);
  w.OraConversation.startFresh({ conversation_id: 'archive-exit', tag: '' });
  record('archive Inquiry cannot save a draft during input or navigation',
    w.localStorage.getItem('ora-v3-draft-archive-source') === null);

  w.OraConversation.startFresh({ conversation_id: 'artifact-owner', tag: '' });
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-envelope-created', {
    detail: { conversation_id: 'other-owner', source: 'document-process' },
  }));
  w.OraConversation.beginRename();
  var staleArtifactIgnored = !w.document.querySelector('.output-pane-display-name-input');
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-envelope-created', {
    detail: { conversation_id: 'artifact-owner', source: 'document-process' },
  }));
  var artifactHeaderUnlocked = w.document.getElementById('outputPaneDisplayName')
    .classList.contains('is-clickable');
  w.OraConversation.beginRename();
  var artifactRenameInput = w.document.querySelector('.output-pane-display-name-input');
  record('durable artifact response upgrades only its owning Dialogue envelope',
    staleArtifactIgnored && artifactHeaderUnlocked && !!artifactRenameInput);
  w.OraConversation.startFresh({ conversation_id: 'rename-destination', tag: '' });
  record('navigation during Rename cannot leak its editor into the next Dialogue',
    !w.document.querySelector('.output-pane-display-name-input')
      && w.document.getElementById('outputPaneDisplayName').textContent === 'New Dialogue');

  await w.OraConversation.load('retained');
  var actionsButton = w.document.getElementById('outputPaneActionsBtn');
  actionsButton.click();
  var actionsMenu = w.document.getElementById('outputPaneActionsMenu');
  record('output actions menu moves focus to its first item',
    !!actionsMenu
      && actionsButton.getAttribute('aria-expanded') === 'true'
      && w.document.activeElement.textContent === 'Rename');
  w.document.activeElement.dispatchEvent(new w.KeyboardEvent('keydown', {
    key: 'ArrowDown', bubbles: true,
  }));
  record('output actions menu supports arrow-key navigation',
    w.document.activeElement.textContent === 'Close');
  w.document.activeElement.dispatchEvent(new w.KeyboardEvent('keydown', {
    key: 'Escape', bubbles: true,
  }));
  record('output actions Escape closes and restores trigger focus',
    actionsButton.getAttribute('aria-expanded') === 'false'
      && w.document.activeElement === actionsButton);
  actionsButton.click();
  w.document.activeElement.dispatchEvent(new w.KeyboardEvent('keydown', {
    key: 'End', bubbles: true,
  }));
  w.document.activeElement.dispatchEvent(new w.KeyboardEvent('keydown', {
    key: 'Tab', bubbles: true,
  }));
  record('output actions Tab closes and advances from its trigger',
    actionsButton.getAttribute('aria-expanded') === 'false'
      && w.document.activeElement === w.document.querySelector('.input-pane textarea'));
  actionsButton.click();
  w.document.querySelector('.input-pane textarea').focus();
  record('output actions menu closes when focus leaves the popup',
    actionsButton.getAttribute('aria-expanded') === 'false');
  actionsButton.click();
  actionsMenu.querySelector('.mode-dropdown-item').click();
  var renameFromMenu = w.document.querySelector('.output-pane-display-name-input');
  record('output menu activation restores or intentionally transfers focus',
    !!renameFromMenu && w.document.activeElement === renameFromMenu);
  if (renameFromMenu) {
    renameFromMenu.dispatchEvent(new w.KeyboardEvent('keydown', {
      key: 'Escape', bubbles: true,
    }));
  }

  calls = [];
  tagEvents = [];
  await w.OraConversation.setPrivacyTag('private');
  var privacyCall = calls.find(function (call) { return /\/privacy-tag$/.test(call.url); });
  record('privacy mutation uses the dedicated endpoint',
    !!privacyCall && JSON.parse(privacyCall.opts.body).tag === 'private');
  record('privacy response updates active state and emits authority event',
    w.OraConversation.getActiveTag() === 'private'
      && tagEvents.some(function (event) {
        return event.conversation_id === 'retained' && event.tag === 'private';
      }));

  calls = [];
  await w.OraConversation.closeConversation('retained', { tag: 'private' });
  record('retained Dialogue Close uses close endpoint',
    calls.some(function (call) { return /\/retained\/close$/.test(call.url); })
      && !calls.some(function (call) { return /\/delete-forever$/.test(call.url); }));
  record('active Close starts a fresh Standard Dialogue',
    w.OraConversation.getActiveConversationId() !== 'retained'
      && w.OraConversation.getActiveTag() === '');

  await w.OraConversation.load('slow-close');
  calls = [];
  var slowClosePromise = w.OraConversation.closeConversation('slow-close', { tag: '' });
  await wait(0);
  var slowCloseInput = w.document.querySelector('.input-pane textarea');
  var duplicateSlowClose = await w.OraConversation.closeConversation('slow-close', { tag: '' });
  record('active Close freezes Inquiry while the request is in flight',
    slowCloseInput.readOnly
      && w.OraConversation.isLifecycleBusy()
      && actionsButton.disabled
      && w.document.querySelector('.sidebar-fork-thread-cmd').disabled);
  record('busy lifecycle guard deduplicates a second Close request',
    duplicateSlowClose === null
      && calls.filter(function (call) {
        return /\/slow-close\/close$/.test(call.url);
      }).length === 1);
  slowCloseInput.value = 'late programmatic draft';
  slowCloseInput.dispatchEvent(new w.Event('input', { bubbles: true }));
  slowCloseResolve({
    ok: true,
    status: 200,
    json: function () { return Promise.resolve({ action: 'close', errors: [] }); },
  });
  await slowClosePromise;
  await wait(450);
  record('successful active Close cannot resurrect input typed during the request',
    w.localStorage.getItem('ora-v3-draft-slow-close') === null
      && w.OraConversation.getActiveConversationId() !== 'slow-close'
      && !w.OraConversation.isLifecycleBusy());

  await w.OraConversation.load('stealth');
  calls = [];
  confirmations = [];
  await w.OraConversation.closeConversation('stealth', { tag: '' });
  var exactWarning =
    'Permanently delete this Dialogue and all Ora-managed copies? This cannot be undone. Files you explicitly exported to the vault will remain.';
  record('authoritative Stealth tag overrides stale row metadata',
    calls.some(function (call) { return /\/stealth\/delete-forever$/.test(call.url); })
      && !calls.some(function (call) { return /\/stealth\/close$/.test(call.url); }));
  record('Delete Forever uses the exact export-retention warning',
    confirmations.length === 1 && confirmations[0] === exactWarning,
    confirmations[0] || 'none');

  calls = [];
  confirmations = [];
  await w.OraConversation.closeConversation('stealth-row', { tag: '' });
  record('non-active row resolves envelope privacy before Close',
    calls.some(function (call) { return call.url === '/api/conversation/stealth-row'; })
      && calls.some(function (call) { return /\/stealth-row\/delete-forever$/.test(call.url); })
      && !calls.some(function (call) { return /\/stealth-row\/close$/.test(call.url); })
      && confirmations[0] === exactWarning);

  w.OraConversation.startFresh({ conversation_id: 'draft-owner', tag: '' });
  var input = w.document.querySelector('.input-pane textarea');
  input.value = 'keep this draft';
  input.dispatchEvent(new w.Event('input', { bubbles: true }));
  await w.OraConversation.closeConversation('other-row', { tag: '' });
  await wait(450);
  record('closing a non-active row preserves the active draft timer',
    w.localStorage.getItem('ora-v3-draft-draft-owner') === 'keep this draft');

  w.OraConversation.startFresh({ conversation_id: 'timer-a', tag: '' });
  input.value = 'must not resurrect';
  input.dispatchEvent(new w.Event('input', { bubbles: true }));
  w.OraConversation.startFresh({ conversation_id: 'timer-b', tag: '' });
  await w.OraConversation.deleteForever('timer-a', { tag: '' });
  await wait(450);
  record('Delete Forever cancels the target draft timer permanently',
    w.localStorage.getItem('ora-v3-draft-timer-a') === null);

  w.OraConversation.startFresh({ conversation_id: 'remote-draft-race', tag: '' });
  input.value = 'remote tab must not resurrect this';
  input.dispatchEvent(new w.Event('input', { bubbles: true }));
  var eventCountBeforeRemote = lifecycleEvents.length;
  var remotePulse = {
    action: 'delete-forever',
    conversation_id: 'remote-draft-race',
    nonce: 'remote-pulse-one',
    source: 'another-tab',
  };
  lifecycleChannels[0].onmessage({ data: remotePulse });
  // Browsers can deliver the same logical pulse through BroadcastChannel and
  // the storage fallback. The receiver must retire it exactly once.
  w.dispatchEvent(new w.StorageEvent('storage', {
    key: 'ora-v3-conversation-lifecycle-pulse',
    newValue: JSON.stringify(remotePulse),
  }));
  await wait(450);
  record('remote Delete Forever cancels a pending local draft and resets its tab',
    w.localStorage.getItem('ora-v3-draft-remote-draft-race') === null
      && w.OraConversation.getActiveConversationId() !== 'remote-draft-race');
  record('BroadcastChannel and storage delivery of one pulse are deduplicated',
    lifecycleEvents.length === eventCountBeforeRemote + 1);

  w.OraConversation.startFresh({ conversation_id: 'unrelated-active', tag: '' });
  w.localStorage.setItem('ora-v3-draft-deleted-elsewhere', 'stale draft');
  var activeBeforeUnrelatedPulse = w.OraConversation.getActiveConversationId();
  w.dispatchEvent(new w.StorageEvent('storage', {
    key: 'ora-v3-conversation-lifecycle-pulse',
    newValue: JSON.stringify({
      action: 'delete-forever',
      conversation_id: 'deleted-elsewhere',
      nonce: 'remote-pulse-two',
      source: 'another-tab',
    }),
  }));
  record('remote deletion clears only the exact Dialogue browser state',
    w.OraConversation.getActiveConversationId() === activeBeforeUnrelatedPulse
      && w.localStorage.getItem('ora-v3-draft-deleted-elsewhere') === null);

  w.OraConversation.startFresh({ conversation_id: 'concurrent-delete', tag: '' });
  var messagesBeforeConcurrentDelete = lifecycleChannelMessages.length;
  var concurrentDelete = w.OraConversation.deleteForever('concurrent-delete');
  await wait(0);
  lifecycleChannels[0].onmessage({ data: {
    action: 'delete-forever',
    conversation_id: 'concurrent-delete',
    nonce: 'remote-pulse-three',
    source: 'winning-tab',
  } });
  concurrentDeleteResolve({
    ok: false,
    status: 410,
    json: function () { return Promise.resolve({ error: 'already deleted' }); },
  });
  var concurrentDeleteResult = await concurrentDelete;
  record('a remote winning delete suppresses a contradictory local failure',
    concurrentDeleteResult
      && concurrentDeleteResult.ok === true
      && concurrentDeleteResult.cross_tab === true);
  record('concurrent delete completion does not rebroadcast a second pulse',
    lifecycleChannelMessages.length === messagesBeforeConcurrentDelete);

  await w.OraConversation.load('retained');
  var pendingBLoad = w.OraConversation.load('pending-b');
  await wait(0);
  await w.OraConversation.deleteForever('retained', { tag: '' });
  pendingBResolve({
    ok: true,
    status: 200,
    json: function () {
      return Promise.resolve({
        conversation_id: 'pending-b', tag: 'private', messages: [],
      });
    },
  });
  await pendingBLoad;
  record('deleting rendered Dialogue preserves newer pending selection',
    w.OraConversation.getActiveConversationId() === 'pending-b');

  await w.OraConversation.load('fork-parent');
  calls = [];
  var selectedForkIds = [];
  var onForkSelection = function (event) {
    var detail = event.detail || {};
    if (detail.source === 'mode-dropdown') {
      selectedForkIds.push(detail.conversation_id);
    }
  };
  w.document.addEventListener('ora:conversation-selected', onForkSelection);
  var delayedFork = w.OraConversation.forkActive({
    tag: 'private', source: 'mode-dropdown',
  });
  await wait(0);
  w.OraConversation.startFresh({ conversation_id: 'newer-navigation', tag: '' });
  forkResolve({
    ok: true,
    status: 200,
    json: function () {
      return Promise.resolve({
        new_conversation_id: 'fork-child', tag: 'private',
      });
    },
  });
  var delayedForkResult = await delayedFork;
  w.document.removeEventListener('ora:conversation-selected', onForkSelection);
  var forkCall = calls.find(function (call) {
    return /\/fork-parent\/fork$/.test(call.url);
  });
  record('fork request preserves the explicit creation tag',
    !!forkCall && JSON.parse(forkCall.opts.body || '{}').tag === 'private');
  record('delayed fork creation does not override newer navigation',
    delayedForkResult && delayedForkResult.selected === false
      && w.OraConversation.getActiveConversationId() === 'newer-navigation'
      && selectedForkIds.indexOf('fork-child') === -1);

  var pendingLoad = w.OraConversation.load('late');
  await wait(0);
  record('pending selection is exposed as read-only/loading',
    w.OraConversation.isLoading() && w.OraConversation.isReadOnly());
  await w.OraConversation.deleteForever('late', { tag: 'stealth' });
  var replacementId = w.OraConversation.getActiveConversationId();
  lateResolve({
    ok: true,
    status: 200,
    json: function () {
      return Promise.resolve({ conversation_id: 'late', tag: 'stealth', messages: [] });
    },
  });
  await pendingLoad;
  await wait(0);
  record('late load response cannot reactivate a deleted Dialogue',
    replacementId !== 'late' && w.OraConversation.getActiveConversationId() === replacementId,
    w.OraConversation.getActiveConversationId());

  await runIndexLifecycleControlsTests();

  var passed = results.filter(function (result) { return result.ok; }).length;
  console.log('\n' + passed + ' / ' + results.length + ' tests passed');
  process.exit(passed === results.length ? 0 : 1);
}

run().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
