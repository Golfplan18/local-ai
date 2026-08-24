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
  '<div class="left-column">' +
  '<div class="output-pane">' +
  '  <span id="outputPaneDisplayName">Dialogue</span>' +
  '  <span id="outputPaneModeIcon"></span>' +
  '  <button id="outputPaneActionsBtn" hidden></button>' +
  '  <button id="outputPaneNavFirst" aria-label="First turn">&laquo;</button>' +
  '  <button id="outputPaneNavBack"></button>' +
  '  <button id="outputPaneNavForward"></button>' +
  '  <button id="outputPaneNavLast" aria-label="Last turn">&raquo;</button>' +
  '  <span id="outputPaneTurnPosition"></span>' +
  '  <span id="outputPaneTimestamp"></span>' +
  '  <button id="outputPaneExpandBtn" disabled></button>' +
  '  <div class="output-content"></div>' +
  '</div>' +
  '<div class="input-pane"><textarea></textarea></div>' +
  '<div id="bridgeStrip"></div>' +
  '<div class="prompt-overlay" id="promptOverlay" aria-hidden="true">' +
  '  <button id="promptOverlayCloseBtn"></button>' +
  '  <div id="promptOverlayContent"></div>' +
  '</div>' +
  '</div>' +
  '</body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
);

var w = dom.window;
if (w.HTMLDialogElement && !w.HTMLDialogElement.prototype.showModal) {
  w.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
}
var calls = [];
var confirmations = [];
var alerts = [];
var tagEvents = [];
var lifecycleEvents = [];
var protectionEvents = [];
var reviewQueueOpens = [];
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
  narrowOwner: {
    conversation_id: 'narrow-owner',
    tag: '',
    display_name: 'Narrow owner',
    messages: [
      { role: 'user', content: 'Show the system' },
      {
        role: 'assistant',
        content: 'Analysis before.\n```ora-visual\n'
          + '{"type":"concept_map","title":"Original visual"}\n```\nAnalysis after.',
        visual_outcome: {
          state: 'building',
          stage: 'legibility',
          legibility_attempts: { 0: 'in_progress' },
        },
      },
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
      { role: 'user', content: 'Parent question one' },
      { role: 'assistant', content: 'Parent answer one', timestamp: '2024-03-02T12:34:00Z' },
      { role: 'user', content: 'Parent question two' },
      { role: 'assistant', content: 'Parent answer two', timestamp: '2025-11-09T12:34:00Z' },
    ],
  },
  exitParent: {
    conversation_id: 'exit-parent',
    tag: '',
    display_name: 'Exit parent',
    messages: [
      { role: 'user', content: 'Earlier parent question' },
      { role: 'assistant', content: 'Earlier parent answer' },
      { role: 'user', content: 'Latest parent question' },
      { role: 'assistant', content: 'Latest parent answer' },
    ],
  },
  exitChild: {
    conversation_id: 'exit-child',
    parent_conversation_id: 'exit-parent',
    tag: 'stealth',
    display_name: 'Exit child',
    messages: [
      { role: 'user', content: 'Local child question' },
      { role: 'assistant', content: 'Local child answer' },
    ],
  },
  exitStealthParent: {
    conversation_id: 'exit-stealth-parent',
    tag: 'stealth',
    display_name: 'Stealth parent',
    messages: [
      { role: 'user', content: 'Parent secret' },
      { role: 'assistant', content: 'Parent secret answer' },
    ],
  },
  exitNestedChild: {
    conversation_id: 'exit-nested-child',
    parent_conversation_id: 'exit-stealth-parent',
    tag: 'stealth',
    display_name: 'Nested Stealth child',
    messages: [
      { role: 'user', content: 'Nested secret' },
      { role: 'assistant', content: 'Nested answer' },
    ],
  },
  exitOrphan: {
    conversation_id: 'exit-orphan',
    parent_conversation_id: 'missing-parent',
    tag: 'stealth',
    display_name: 'Orphan Stealth',
    messages: [
      { role: 'user', content: 'Orphan secret' },
      { role: 'assistant', content: 'Orphan answer' },
    ],
  },
  protectionPending: {
    conversation_id: 'protection-pending',
    tag: 'stealth',
    display_name: 'Protected Stealth',
    messages: [
      { role: 'user', content: 'Protected secret' },
      { role: 'assistant', content: 'Protected answer' },
    ],
  },
  displayForkChild: {
    conversation_id: 'display-fork-child',
    parent_conversation_id: 'fork-parent',
    tag: 'stealth',
    display_name: 'Displayed-turn child',
    messages: [],
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
w.OraReviewQueuePanel = {
  open: function (options) { reviewQueueOpens.push(options || {}); },
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
  if (decoded === '/api/conversation/narrow-owner') {
    // A real fetch parse creates fresh message objects on every reload.
    return response(true, JSON.parse(JSON.stringify(envelopes.narrowOwner)));
  }
  if (decoded === '/api/conversation/stealth') return response(true, envelopes.stealth);
  if (decoded === '/api/conversation/fork-parent') return response(true, envelopes.forkParent);
  if (decoded === '/api/conversation/exit-parent') return response(true, envelopes.exitParent);
  if (decoded === '/api/conversation/exit-child') return response(true, envelopes.exitChild);
  if (decoded === '/api/conversation/exit-stealth-parent') return response(true, envelopes.exitStealthParent);
  if (decoded === '/api/conversation/exit-nested-child') return response(true, envelopes.exitNestedChild);
  if (decoded === '/api/conversation/exit-orphan') return response(true, envelopes.exitOrphan);
  if (decoded === '/api/conversation/protection-pending') return response(true, envelopes.protectionPending);
  if (decoded === '/api/conversation/display-fork-child') return response(true, envelopes.displayForkChild);
  if (decoded === '/api/conversation/missing-parent') {
    return response(false, { error: 'Dialogue not found' }, 404);
  }
  if (decoded === '/api/conversation/privacy-child') {
    return response(true, {
      conversation_id: 'privacy-child', tag: 'private', display_name: 'Private fork',
      parent_conversation_id: 'fork-parent', messages: [],
    });
  }
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
  if (decoded === '/api/active-project') {
    return response(true, { ok: true, canonical_nexus: 'commons' });
  }
  if (decoded.indexOf('/api/projects/meta?') === 0) {
    return response(true, { projects: [] });
  }
  if (decoded === '/api/conversations?project_id=') {
    return response(true, {
      pinned: [], errored: [], pending: [], unread: [], active: [],
    });
  }
  if (decoded === '/api/styles/registry') {
    return response(true, { settings: {}, profiles: [], custom: [] });
  }
  if (decoded.indexOf('/api/media-library/') === 0) {
    return response(true, { entries: [] });
  }
  if (decoded.indexOf('/api/canvas/load/') === 0) return response(false, {}, 404);
  if (/\/mark-read$/.test(decoded)) return response(true, { ok: true });
  if (/\/privacy-tag$/.test(decoded)) {
    var privacyBody = JSON.parse(opts.body || '{}');
    envelopes.retained.tag = privacyBody.tag;
    return response(true, { ok: true, tag: privacyBody.tag, errors: [] });
  }
  if (decoded === '/api/conversation/protection-pending/delete-forever') {
    return response(false, {
      status: 'awaiting_system_protection_approval',
      error: 'queued for exact one-shot approval',
      queue_id: 'queue-delete-protected',
      retry_required: true,
    }, 409);
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
  if (decoded === '/chat') return response(true, { status: 'ok' });
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
Object.defineProperty(w.document.querySelector('.input-pane'), 'offsetHeight', {
  configurable: true,
  value: 184,
});
Object.defineProperty(w.document.getElementById('bridgeStrip'), 'offsetHeight', {
  configurable: true,
  value: 37,
});
vm.runInContext(
  fs.readFileSync(path.resolve(__dirname, '..', 'js', 'prompt-overlay.js'), 'utf8'),
  context,
  { filename: 'prompt-overlay.js' }
);
w.document.dispatchEvent(new w.Event('DOMContentLoaded'));
w.document.addEventListener('ora:conversation-tag-changed', function (event) {
  tagEvents.push(event.detail || {});
});
w.document.addEventListener('ora:conversation-lifecycle-completed', function (event) {
  lifecycleEvents.push(event.detail || {});
});
w.document.addEventListener('ora:system-protection-approval-required', function (event) {
  protectionEvents.push(event.detail || {});
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

async function runBootstrapPrivacyTests() {
  var bootstrapDom = new jsdom.JSDOM(
    '<!doctype html><html><body><div class="output-pane"></div></body></html>',
    { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
  );
  var bw = bootstrapDom.window;
  if (bw.HTMLDialogElement && !bw.HTMLDialogElement.prototype.showModal) {
    bw.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  }
  var release = null;
  var fetches = [];
  var privacyText = null;
  bw.OraConversation = {
    submitAfterPrivacy: function (text, submit, options) {
      privacyText = text;
      return new Promise(function (resolve) {
        release = function () {
          bw.document.body.classList.add('private-mode');
          Promise.resolve(submit()).then(function () { resolve(true); });
        };
      });
    },
  };
  bw.fetch = function (url, opts) {
    fetches.push({ url: String(url), body: JSON.parse(opts.body || '{}') });
    return Promise.resolve({
      ok: true,
      status: 200,
      json: function () {
        return Promise.resolve({
          topic: privacyText, summary: 'Private context', match_count: 1,
        });
      },
    });
  };
  var bootstrapContext = bootstrapDom.getInternalVMContext();
  bootstrapContext.console = console;
  bootstrapContext.fetch = bw.fetch;
  vm.runInContext(
    fs.readFileSync(path.resolve(__dirname, '..', 'js', 'v3-bootstrap.js'), 'utf8'),
    bootstrapContext,
    { filename: 'v3-bootstrap.js' }
  );
  bw.OraBootstrap.open();
  var input = bw.document.querySelector('.bootstrap-modal-input');
  input.value = 'My medical diagnosis is private.';
  bw.document.querySelector('.bootstrap-modal-submit').click();
  await new Promise(function (resolve) { bw.setTimeout(resolve, 0); });
  record('bootstrap topic waits at privacy before server POST',
    privacyText === input.value && fetches.length === 0);
  release();
  await new Promise(function (resolve) { bw.setTimeout(resolve, 0); });
  await new Promise(function (resolve) { bw.setTimeout(resolve, 0); });
  record('bootstrap posts exactly once with the post-fork Private tag',
    fetches.length === 1
      && fetches[0].url === '/api/bootstrap'
      && fetches[0].body.tag === 'private');

  bw.OraConversation = null;
  bw.document.body.classList.remove('private-mode');
  bw.OraBootstrap.open();
  input.value = 'My password is private.';
  bw.document.querySelector('.bootstrap-modal-submit').click();
  await new Promise(function (resolve) { bw.setTimeout(resolve, 0); });
  record('bootstrap fails closed when privacy controls are unavailable',
    fetches.length === 1
      && /Privacy check unavailable/.test(
        bw.document.querySelector('.bootstrap-modal-status').textContent
      ));
}

async function runScratchpadPrivacyTests() {
  var indexSource = fs.readFileSync(
    path.resolve(__dirname, '..', '..', 'index-v3.html'), 'utf8'
  );
  var scratchDom = new jsdom.JSDOM(
    '<!doctype html><html><body></body></html>',
    { url: 'http://localhost/', runScripts: 'outside-only' }
  );
  var sw = scratchDom.window;
  var release = null;
  var fetches = [];
  var rendered = [];
  var activeId = 'scratch-parent';
  var draftText = null;
  var rightInputArea = { value: 'My medical diagnosis is private.' };
  var leftInputArea = { value: 'Existing main Inquiry draft' };
  sw.OraConversation = {
    submitAfterPrivacy: function (_text, submit, options) {
      draftText = options && options.draftText;
      return new Promise(function (resolve) {
        release = function () {
          activeId = 'scratch-private-child';
          Promise.resolve(submit()).then(function () { resolve(true); });
        };
      });
    },
  };
  sw.fetch = function (url, opts) {
    fetches.push({
      url: String(url),
      body: JSON.parse(opts.body || '{}'),
      activeId: activeId,
    });
    return Promise.resolve({
      ok: true,
      status: 200,
      json: function () { return Promise.resolve({ answer: 'Private answer' }); },
    });
  };
  var scratchContext = scratchDom.getInternalVMContext();
  scratchContext.console = console;
  scratchContext.fetch = sw.fetch;
  scratchContext.rightInputArea = rightInputArea;
  scratchContext.leftInputArea = leftInputArea;
  scratchContext.renderScratchpadEntry = function (cls, text) {
    rendered.push({ cls: cls, text: text });
    return { remove: function () {} };
  };
  scratchContext.trimScratchpadHistory = function () {};
  var scratchSource = sourceSlice(
    indexSource,
    '  const submitToScratchpad = async',
    '  const submitInput = async'
  );
  vm.runInContext(
    scratchSource
      + '\nglobalThis.__submitScratchpadAfterPrivacy = submitScratchpadAfterPrivacy;',
    scratchContext,
    { filename: 'index-scratchpad-privacy.js' }
  );

  var pending = sw.__submitScratchpadAfterPrivacy(rightInputArea.value);
  await Promise.resolve();
  record('Aside prompt waits at privacy before server POST',
    fetches.length === 0 && rightInputArea.value.indexOf('diagnosis') >= 0);
  release();
  await pending;
  record('Aside posts exactly once after the child is selected',
    fetches.length === 1
      && fetches[0].url === '/api/scratchpad'
      && fetches[0].activeId === 'scratch-private-child'
      && fetches[0].body.prompt === 'My medical diagnosis is private.'
      && rightInputArea.value === ''
      && draftText === 'Existing main Inquiry draft');

  rightInputArea.value = 'My password remains private.';
  sw.OraConversation.submitAfterPrivacy = function () { return Promise.resolve(false); };
  await sw.__submitScratchpadAfterPrivacy(rightInputArea.value);
  record('cancelled Aside privacy sends nothing and preserves its input',
    fetches.length === 1 && rightInputArea.value === 'My password remains private.');

  sw.OraConversation = null;
  await sw.__submitScratchpadAfterPrivacy(rightInputArea.value);
  record('Aside fails closed without privacy controls',
    fetches.length === 1
      && rendered.some(function (entry) {
        return /Privacy check unavailable/.test(entry.text);
      }));
}

async function runIndexPrivacyEgressTests() {
  var indexSource = fs.readFileSync(
    path.resolve(__dirname, '..', '..', 'index-v3.html'), 'utf8'
  );
  var privacyDom = new jsdom.JSDOM(
    '<!doctype html><html><body></body></html>',
    { url: 'http://localhost/', runScripts: 'outside-only' }
  );
  var pw = privacyDom.window;
  var events = [];
  var analyzerCalls = 0;
  var allowPrivacy = true;
  var releasedDrafts = [];
  var frameworkVisualSnapshot = { editor: 'excalidraw', elements: [{ id: 'framework-visual' }] };
  pw.OraInputState = {
    getFramework: function () {
      return { id: 'terrain-mapping', kind: 'framework' };
    },
    clearFramework: function () {},
  };
  pw.OraFrameworkSetupPopup = {
    show: function () {
      return Promise.resolve({
        action: 'continue',
        responses: { context: 'My private key is framework-secret.' },
        on_canvas: {},
      });
    },
  };
  pw.OraConversation = {
    submitAfterPrivacy: async function (text, submit, options) {
      events.push('privacy:' + text);
      if (!allowPrivacy) return false;
      events.push('approved-draft:' + String(options && options.draftText || ''));
      events.push('capture-option:' + String(!!(options && options.captureVisualSnapshot)));
      await submit({ visualSnapshot: frameworkVisualSnapshot });
      return true;
    },
  };
  var privacyContext = privacyDom.getInternalVMContext();
  privacyContext.console = console;
  privacyContext.renderAssistantTurn = function (message) {
    events.push('assistant:' + message);
  };
  privacyContext._reserveInquiryComposition = function (text) {
    events.push('reserve:' + text);
    return {
      inputSnapshot: { framework: { id: 'terrain-mapping', kind: 'framework' } },
      attachmentSnapshot: { entries: [] },
      visualSnapshot: frameworkVisualSnapshot,
      restoreDraftText: text,
    };
  };
  privacyContext._releaseInquiryComposition = function (composition) {
    releasedDrafts.push(composition.restoreDraftText);
    events.push('release');
  };
  privacyContext._rebindReservedComposition = function () { return true; };
  privacyContext._summarizeAttachments = function () { return []; };
  privacyContext._summarizeCanvas = function () { return ''; };
  privacyContext.submitToMainPipeline = async function (
    text, _display, _approved, visualSnapshot, composition
  ) {
    events.push('submit:' + text);
    events.push('submit-visual:' + String(visualSnapshot === frameworkVisualSnapshot));
    if (composition) composition.accepted = true;
    return true;
  };
  privacyContext._analyzeFrameworkInputs = async function (request) {
    analyzerCalls += 1;
    events.push('analyze:' + request.prompt);
    return analyzerCalls === 1
      ? { requirements: [{ name: 'context', status: 'missing' }] }
      : { requirements: [] };
  };
  privacyContext._hasGaps = function (report) {
    return report.requirements.some(function (item) {
      return item.status === 'missing' || item.status === 'unclear';
    });
  };
  privacyContext._augmentPromptWithResponses = function (base, responses) {
    return base + '\n' + responses.context;
  };
  privacyContext._runAnywayNote = function () { return ''; };
  var submitSource = sourceSlice(
    indexSource,
    '  const submitWithFrameworkCheck = async',
    '  let imageGenerateMode = false;'
  );
  vm.runInContext(
    submitSource + '\nglobalThis.__submitWithFrameworkCheck = submitWithFrameworkCheck;',
    privacyContext,
    { filename: 'index-framework-privacy.js' }
  );

  await pw.__submitWithFrameworkCheck('Base prompt', 'Base prompt');
  var privacyIndex = events.indexOf('privacy:My private key is framework-secret.');
  var secondAnalyzeIndex = events.findIndex(function (event, index) {
    return index > privacyIndex && event.indexOf('analyze:') === 0;
  });
  var submits = events.filter(function (event) { return event.indexOf('submit:') === 0; });
  record('framework response is privacy-approved before analyzer and final submission',
    privacyIndex > events.indexOf('analyze:Base prompt')
      && secondAnalyzeIndex > privacyIndex
      && submits.length === 1
      && /framework-secret/.test(submits[0])
      && events[0] === 'reserve:Base prompt'
      && events.includes('capture-option:false')
      && events.includes('submit-visual:true'));
  record('framework privacy fork receives the complete augmented draft',
    events.some(function (event) {
      return event === 'approved-draft:Base prompt\nMy private key is framework-secret.';
    }));

  events = [];
  analyzerCalls = 0;
  allowPrivacy = false;
  await pw.__submitWithFrameworkCheck('Base prompt', 'Base prompt');
  record('cancelled framework-response privacy sends no analyzer or final request',
    analyzerCalls === 1
      && events.some(function (event) { return event.indexOf('privacy:') === 0; })
      && !events.some(function (event) { return event.indexOf('submit:') === 0; })
      && releasedDrafts[releasedDrafts.length - 1]
        === 'Base prompt\nMy private key is framework-secret.');

  events = [];
  analyzerCalls = 0;
  await pw.__submitWithFrameworkCheck('My password is initial-secret.');
  record('cancelled initial framework privacy sends no analyzer request',
    analyzerCalls === 0
      && events.includes('privacy:My password is initial-secret.'));

  var blankDom = new jsdom.JSDOM(
    '<!doctype html><html><body></body></html>',
    { url: 'http://localhost/', runScripts: 'outside-only' }
  );
  var bw = blankDom.window;
  var snapshotCalls = 0;
  var submittedFields = null;
  bw.OraCanvas = {
    hasContent: function () { return false; },
    snapshotForSubmit: function () { snapshotCalls += 1; return {}; },
  };
  bw.fetch = function (_url, options) {
    submittedFields = {};
    options.body.forEach(function (value, key) { submittedFields[key] = value; });
    return Promise.resolve({
      ok: true, status: 200,
      json: function () { return Promise.resolve({ status: 'ok' }); },
    });
  };
  var blankContext = blankDom.getInternalVMContext();
  blankContext.console = console;
  blankContext.fetch = bw.fetch;
  blankContext.currentConversationId = function () { return 'text-only'; };
  blankContext.currentTag = function () { return ''; };
  blankContext.inquiryNavigationRevision = 0;
  blankContext.inquiryDraftRevision = 0;
  blankContext.renderAssistantTurn = function () {};
  blankContext.refreshSidebarAfterSubmit = function () {};
  vm.runInContext(
    sourceSlice(indexSource, '  const mainPipelineSubmissionsInFlight = [];',
      '  const submitToMainPipeline = async')
      + '\nglobalThis.__submitTextOnly = _submitToMainPipeline;'
      + '\nglobalThis.__reserveComposition = _reserveInquiryComposition;'
      + '\nglobalThis.__releaseComposition = _releaseInquiryComposition;',
    blankContext,
    { filename: 'index-text-only-submit.js' }
  );
  await bw.__submitTextOnly('Text only');
  record('text-only Inquiry omits blank visual checkpoint and PNG',
    snapshotCalls === 0
      && submittedFields.message === 'Text only'
      && !Object.prototype.hasOwnProperty.call(submittedFields, 'visual_native')
      && !Object.prototype.hasOwnProperty.call(submittedFields, 'canvas_preview_png'));

  var immediateSubmitFetch = bw.fetch;
  var activeSubmitConversation = 'composition-a';
  var delayedSubmitResolvers = [];
  var delayedSubmitBodies = [];
  var modelState = { value: 'budget-a', revision: 0 };
  var audienceState = { value: 'external', revision: 0 };
  var inputState = {
    revision: 0,
    framework: { id: 'framework-a' },
    analysisMode: null,
    analysisLens: null,
  };
  var attachmentOwner = 'composition-a';
  var attachmentRevision = 0;
  var submittedImageEntry = {
    kind: 'image',
    file: new bw.File(['a'], 'a.png', { type: 'image/png' }),
  };
  var newerImageEntry = {
    kind: 'image',
    file: new bw.File(['b'], 'b.png', { type: 'image/png' }),
  };
  var attachmentEntries = [submittedImageEntry];
  blankContext.currentConversationId = function () { return activeSubmitConversation; };
  bw.OraModelProfiles = {
    snapshotForSubmission: function () {
      return { value: modelState.value, revision: modelState.revision };
    },
    reserveSubmission: function (snapshot) {
      if (snapshot.revision !== modelState.revision || snapshot.value !== modelState.value) return null;
      var token = { value: modelState.value };
      modelState.value = '';
      modelState.revision += 1;
      token.reservedRevision = modelState.revision;
      return token;
    },
    restoreSubmission: function (token) {
      if (!token || token.reservedRevision !== modelState.revision) return false;
      modelState.value = token.value;
      modelState.revision += 1;
      return true;
    },
  };
  bw.OraStyleAudience = {
    snapshotForSubmission: function () {
      return { value: audienceState.value, revision: audienceState.revision };
    },
    reserveSubmission: function (snapshot) {
      if (snapshot.revision !== audienceState.revision
          || snapshot.value !== audienceState.value) return null;
      var token = { value: audienceState.value };
      audienceState.value = 'internal';
      audienceState.revision += 1;
      token.reservedRevision = audienceState.revision;
      return token;
    },
    restoreSubmission: function (token) {
      if (!token || token.reservedRevision !== audienceState.revision) return false;
      audienceState.value = token.value;
      audienceState.revision += 1;
      return true;
    },
  };
  bw.OraInputState = {
    snapshotForSubmission: function () { return Object.assign({}, inputState); },
    reserveSubmission: function (snapshot) {
      if (snapshot.revision !== inputState.revision) return null;
      var token = Object.assign({}, inputState);
      inputState.framework = null;
      inputState.analysisMode = null;
      inputState.analysisLens = null;
      inputState.revision += 1;
      token.reservedRevision = inputState.revision;
      return token;
    },
    restoreSubmission: function (token) {
      if (!token || token.reservedRevision !== inputState.revision) return false;
      inputState.framework = token.framework;
      inputState.analysisMode = token.analysisMode;
      inputState.analysisLens = token.analysisLens;
      inputState.revision += 1;
      return true;
    },
  };
  bw.OraInputAttachments = {
    snapshotForSubmission: function () {
      return {
        conversationId: attachmentOwner,
        revision: attachmentRevision,
        entries: attachmentEntries.slice(),
      };
    },
    reserveSubmission: function (snapshot) {
      if (snapshot.conversationId !== attachmentOwner
          || snapshot.revision !== attachmentRevision) return null;
      var token = { conversationId: attachmentOwner, entries: snapshot.entries.slice() };
      attachmentEntries = attachmentEntries.filter(function (entry) {
        return snapshot.entries.indexOf(entry) === -1;
      });
      attachmentRevision += 1;
      token.reservedRevision = attachmentRevision;
      return token;
    },
    restoreSubmission: function (token) {
      if (!token || token.conversationId !== attachmentOwner
          || token.reservedRevision !== attachmentRevision) return false;
      attachmentEntries = token.entries.concat(attachmentEntries);
      attachmentRevision += 1;
      return true;
    },
  };
  bw.fetch = function (_url, options) {
    var fields = {};
    options.body.forEach(function (value, key) { fields[key] = value; });
    delayedSubmitBodies.push(fields);
    return new Promise(function (resolve) { delayedSubmitResolvers.push(resolve); });
  };
  blankContext.fetch = bw.fetch;

  var exactCompositionSubmit = bw.__submitTextOnly('Composition A');
  var firstTurnReserved = modelState.value === ''
    && audienceState.value === 'internal'
    && inputState.framework === null
    && attachmentEntries.length === 0;
  var duplicateCompositionSubmit = bw.__submitTextOnly('Composition A');
  attachmentEntries.push(newerImageEntry);
  attachmentRevision += 1;
  var nextTurnSubmit = bw.__submitTextOnly('Composition B');
  delayedSubmitResolvers.shift()({
    ok: true, status: 200,
    json: function () { return Promise.resolve({ status: 'ok' }); },
  });
  delayedSubmitResolvers.shift()({
    ok: true, status: 200,
    json: function () { return Promise.resolve({ status: 'ok' }); },
  });
  await Promise.all([exactCompositionSubmit, duplicateCompositionSubmit, nextTurnSubmit]);

  modelState.value = 'budget-retry'; modelState.revision += 1;
  audienceState.value = 'external'; audienceState.revision += 1;
  inputState.framework = { id: 'framework-retry' }; inputState.revision += 1;
  var retryImageEntry = {
    kind: 'image',
    file: new bw.File(['retry'], 'retry.png', { type: 'image/png' }),
  };
  attachmentEntries = [retryImageEntry]; attachmentRevision += 1;
  var failedUntouchedSubmit = bw.__submitTextOnly('Composition retry');
  delayedSubmitResolvers.shift()({ ok: false, status: 503 });
  await failedUntouchedSubmit;
  var failedCompositionRestored = modelState.value === 'budget-retry'
    && audienceState.value === 'external'
    && inputState.framework && inputState.framework.id === 'framework-retry'
    && attachmentEntries[0] === retryImageEntry;

  var failedSupersededSubmit = bw.__submitTextOnly('Composition superseded');
  modelState.value = 'budget-new'; modelState.revision += 1;
  audienceState.value = 'internal'; audienceState.revision += 1;
  inputState.framework = null;
  inputState.analysisMode = { id: 'analysis-new' };
  inputState.revision += 1;
  var newestImageEntry = {
    kind: 'image',
    file: new bw.File(['new'], 'new.png', { type: 'image/png' }),
  };
  attachmentEntries.push(newestImageEntry); attachmentRevision += 1;
  delayedSubmitResolvers.shift()({ ok: false, status: 503 });
  await failedSupersededSubmit;

  delete bw.OraModelProfiles;
  delete bw.OraStyleAudience;
  delete bw.OraInputState;
  delete bw.OraInputAttachments;
  var visualRevision = 1;
  bw.OraCanvas = {
    hasContent: function () { return true; },
    snapshotForSubmit: function () {
      return {
        editor: 'excalidraw',
        elements: [{ id: 'visual-shape', version: visualRevision }],
        appState: {},
        files: {},
      };
    },
  };
  var firstVisualComposition = bw.__reserveComposition('Same visual Inquiry');
  var exactVisualRepeat = bw.__reserveComposition('Same visual Inquiry');
  visualRevision += 1;
  var changedVisualComposition = bw.__reserveComposition('Same visual Inquiry');
  var visualDedupeIsExact = !!firstVisualComposition
    && exactVisualRepeat === null
    && !!changedVisualComposition;
  bw.__releaseComposition(changedVisualComposition);
  bw.__releaseComposition(firstVisualComposition);

  record('one-turn composition is reserved once, isolated from the next turn, and safely restored',
    firstTurnReserved
      && visualDedupeIsExact
      && delayedSubmitBodies.length === 4
      && delayedSubmitBodies[0].config_name === 'budget-a'
      && delayedSubmitBodies[0].framework_selected === 'framework-a'
      && delayedSubmitBodies[0].image && delayedSubmitBodies[0].image.name === 'a.png'
      && !Object.prototype.hasOwnProperty.call(delayedSubmitBodies[1], 'config_name')
      && !Object.prototype.hasOwnProperty.call(delayedSubmitBodies[1], 'framework_selected')
      && delayedSubmitBodies[1].style_audience === 'internal'
      && delayedSubmitBodies[1].image && delayedSubmitBodies[1].image.name === 'b.png'
      && failedCompositionRestored
      && modelState.value === 'budget-new'
      && inputState.analysisMode && inputState.analysisMode.id === 'analysis-new'
      && attachmentEntries.includes(newestImageEntry));
  bw.fetch = immediateSubmitFetch;
  blankContext.fetch = immediateSubmitFetch;
  blankContext.currentConversationId = function () { return 'text-only'; };
  delete bw.OraModelProfiles;
  delete bw.OraStyleAudience;
  delete bw.OraInputState;
  delete bw.OraInputAttachments;

  var backgroundState = {
    objects: [{ id: 'bg-image', kind: 'image', layer: 'background' }],
  };
  bw.OraCanvas = {
    hasContent: function () { return backgroundState.objects.length > 0; },
    snapshotForSubmit: function () {
      snapshotCalls += 1;
      return { editor: 'konva', state: backgroundState };
    },
    materializeSnapshot: function () {
      return Promise.resolve({
        editor: 'konva',
        native: new bw.Blob(['native']),
        preview: new bw.Blob(['png'], { type: 'image/png' }),
        spatial: null,
      });
    },
  };
  submittedFields = null;
  await bw.__submitTextOnly('');
  record('drawing-only Konva handoff submits blank text, native state, and canonical PNG',
    snapshotCalls === 1
      && submittedFields.message === ''
      && submittedFields.visual_editor === 'konva'
      && submittedFields.visual_native instanceof bw.Blob
      && submittedFields.canvas_preview_png instanceof bw.Blob
      && submittedFields.exhibits_submission_intent === 'explicit_send');

  var carriedSnapshot = {
    editor: 'excalidraw', conversationId: 'standard-parent',
    elements: [{ id: 'private-visual' }], appState: {}, files: {},
  };
  var materializedSnapshot = null;
  var persistedSnapshot = null;
  var persistedOwner = null;
  bw.OraCanvas = {
    hasContent: function () { return false; },
    snapshotForSubmit: function () { snapshotCalls += 1; return null; },
    materializeSnapshot: function (snapshot) {
      materializedSnapshot = snapshot;
      return Promise.resolve({
        editor: 'excalidraw',
        native: new bw.Blob(['private-native']),
        preview: new bw.Blob(['private-png'], { type: 'image/png' }),
        spatial: null,
      });
    },
    persistSnapshotDraft: function (snapshot, ownerId) {
      persistedSnapshot = snapshot;
      persistedOwner = ownerId;
      return Promise.resolve();
    },
  };
  blankContext.currentConversationId = function () { return 'private-child'; };
  var capturesBeforeCarriedSubmit = snapshotCalls;
  submittedFields = null;
  await bw.__submitTextOnly('Sensitive visual', carriedSnapshot);
  record('privacy-carried parent snapshot becomes the Private child multipart checkpoint',
    snapshotCalls === capturesBeforeCarriedSubmit
      && materializedSnapshot === carriedSnapshot
      && persistedSnapshot === carriedSnapshot
      && persistedOwner === 'private-child'
      && submittedFields.conversation_id === 'private-child'
      && submittedFields.visual_editor === 'excalidraw'
      && submittedFields.visual_native instanceof bw.Blob
      && submittedFields.canvas_preview_png instanceof bw.Blob);
  bw.OraCanvas = {
    hasContent: function () { return backgroundState.objects.length > 0; },
  };

  var gatedSubmissions = [];
  blankContext.rightInputArea = { value: '' };
  blankContext.leftInputArea = { value: '' };
  blankContext.requireMutableInquiry = function () { return true; };
  blankContext.imageGenerateMode = false;
  blankContext._looksLikeImageGenerationRequest = function () { return false; };
  var selectedFramework = false;
  blankContext.OraInputState = {
    getFramework: function () {
      return selectedFramework ? { id: 'terrain-mapping' } : null;
    },
  };
  blankContext.submitWithFrameworkCheck = function () {
    gatedSubmissions.push(Array.prototype.slice.call(arguments));
  };
  blankContext.renderUserTurn = function () {};
  blankContext.setImageGenerateMode = function () {};
  vm.runInContext(
    sourceSlice(indexSource, '  const submitInput = async',
      '  // V3 Backlog 7 — pulse the O on submit')
      + '\nglobalThis.__submitInput = submitInput;',
    blankContext,
    { filename: 'index-drawing-only-submit.js' }
  );
  backgroundState.objects = [];
  await bw.__submitInput();
  record('blank text and blank canvas remain blocked', gatedSubmissions.length === 0);
  selectedFramework = true;
  await bw.__submitInput();
  record('selected framework allows blank text and blank canvas through the framework path',
    gatedSubmissions.length === 1 && gatedSubmissions[0][0] === '');
  selectedFramework = false;
  backgroundState.objects.push({ id: 'drawn-rect', kind: 'shape', layer: 'user_input' });
  await bw.__submitInput();
  record('drawing-only Inquiry passes the send gate without invented model text',
    gatedSubmissions.length === 2 && gatedSubmissions[1][0] === '');
  backgroundState.objects = [];
  blankContext.leftInputArea.value = 'Create an image of the dependency.';
  blankContext.imageGenerateMode = true;
  await bw.__submitInput();
  record('Image input enters the normal analytical turn with an explicit preference',
    gatedSubmissions.length === 3
      && gatedSubmissions[2][0] === 'Create an image of the dependency.'
      && gatedSubmissions[2][3]
      && gatedSubmissions[2][3].kind === 'image');
  blankDom.window.close();
}

async function runSidebarRetryPrivacyTests() {
  var sidebarSource = fs.readFileSync(
    path.resolve(__dirname, '..', 'js', 'sidebar.js'), 'utf8'
  );
  var retryDom = new jsdom.JSDOM(
    '<!doctype html><html><body></body></html>',
    { url: 'http://localhost/', runScripts: 'outside-only' }
  );
  var rw = retryDom.window;
  var activeId = 'other-dialogue';
  var activeTag = '';
  var allow = true;
  var recovered = [
    'My medical diagnosis is private.',
    'My account password is second-secret.',
  ];
  var privacyCalls = [];
  var loadCalls = [];
  var multipartBodies = [];
  var dismissCalls = [];
  var refreshCalls = 0;
  rw.OraConversation = {
    load: async function (id) {
      loadCalls.push(id);
      activeId = id;
      activeTag = '';
    },
    getActiveConversationId: function () { return activeId; },
    getActiveTag: function () { return activeTag; },
    submitAfterPrivacy: async function (text, submit, options) {
      privacyCalls.push({ text: text, draftText: options && options.draftText });
      if (!allow) return false;
      activeId = 'retry-private-child';
      activeTag = 'private';
      await submit();
      return true;
    },
  };
  var retryIndex = 0;
  rw.fetch = function (url, opts) {
    var target = decodeURIComponent(String(url));
    if (/\/retry$/.test(target)) {
      var prompt = recovered[retryIndex++];
      return Promise.resolve({
        ok: true,
        status: 200,
        json: function () {
          return Promise.resolve({
            ok: true,
            conversation_id: 'errored-parent',
            last_user_prompt: prompt,
            tag: '',
            source: 'interrupted_input',
            visual_checkpoint_id: '20260813T123456123456Z-deadbeef',
            visual_checkpoint_source_conversation_id: 'errored-parent',
          });
        },
      });
    }
    if (target === '/chat/multipart') {
      var fields = {};
      opts.body.forEach(function (value, key) { fields[key] = value; });
      multipartBodies.push(fields);
      return Promise.resolve({
        ok: true,
        status: 200,
        body: {
          getReader: function () {
            return { read: function () { return Promise.resolve({ done: true }); } };
          },
        },
      });
    }
    if (/\/dismiss-error$/.test(target)) {
      dismissCalls.push(target);
      return Promise.resolve({ ok: true, status: 200 });
    }
    throw new Error('unexpected retry fetch: ' + target);
  };
  var retryContext = retryDom.getInternalVMContext();
  retryContext.console = console;
  retryContext.fetch = rw.fetch;
  retryContext.alert = function () {};
  retryContext.fetchList = function () { refreshCalls += 1; };
  var retrySource = sourceSlice(
    sidebarSource,
    '  const onRetryClick = async',
    '  const onDismissErrorClick = async'
  );
  vm.runInContext(
    retrySource + '\nglobalThis.__onRetryClick = onRetryClick;',
    retryContext,
    { filename: 'sidebar-retry-privacy.js' }
  );

  var row = { conversation_id: 'errored-parent', tag: '', last_status: 'errored' };
  await rw.__onRetryClick(row);
  record('retry privacy evaluates the actual recovered prompt and draft',
    privacyCalls.length === 1
      && privacyCalls[0].text === recovered[0]
      && privacyCalls[0].draftText === recovered[0]);
  record('retry privacy loads the errored Dialogue before gating',
    loadCalls.length === 1 && loadCalls[0] === 'errored-parent');
  record('approved retry emits exactly one child-bound multipart POST',
    multipartBodies.length === 1
      && multipartBodies[0].message === recovered[0]
      && multipartBodies[0].conversation_id === 'retry-private-child'
      && multipartBodies[0].panel_id === 'retry-private-child');
  record('approved retry preserves multipart metadata and Private tag',
    multipartBodies[0].is_main_feed === 'true'
      && multipartBodies[0].tag === 'private'
      && multipartBodies[0].retry_visual_checkpoint_id
        === '20260813T123456123456Z-deadbeef'
      && multipartBodies[0].retry_visual_source_conversation_id
        === 'errored-parent'
      && multipartBodies[0].exhibits_submission_intent === 'explicit_send');
  record('child-bound retry dismisses only the original errored row',
    dismissCalls.length === 1
      && dismissCalls[0] === '/api/conversation/errored-parent/dismiss-error');

  allow = false;
  await rw.__onRetryClick(row);
  record('each retry freshly gates its newly recovered prompt',
    privacyCalls.length === 2
      && privacyCalls[1].text === recovered[1]
      && privacyCalls[1].draftText === recovered[1]);
  record('cancelled retry emits no duplicate multipart POST or dismissal',
    multipartBodies.length === 1 && dismissCalls.length === 1);
  record('retry refresh remains single-pass per attempt', refreshCalls === 2);
  retryDom.window.close();
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
      + '<span class="bridge-mode-label" id="bridgeModeLabel"></span>'
      + '<span class="bridge-mode-label" id="bridgeModeLabelRight"></span>'
      + '<span class="mode-bracket" id="modeBracketLeft"></span>'
      + '<span class="mode-bracket" id="modeBracketRight"></span>'
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
  var exitCalls = [];
  var modeAlerts = [];
  mw.OraConversation = {
    getActiveConversationId: function () { return activeId; },
    getActiveTag: function () { return activeTag; },
    isReadOnly: function () { return false; },
    canFork: function () { return true; },
    setPrivacyTag: function () { return Promise.resolve({ ok: true }); },
    exitStealth: function (id) { exitCalls.push(id); return Promise.resolve({ ok: true }); },
    deleteForever: function (id) { deleteCalls.push(id); return Promise.resolve({ ok: true }); },
  };
  mw.alert = function (message) { modeAlerts.push(message); };
  var modeContext = modeDom.getInternalVMContext();
  modeContext.console = console;
  modeContext.bracketLeft = mw.document.getElementById('modeBracketLeft');
  modeContext.bracketRight = mw.document.getElementById('modeBracketRight');
  var modeStyle = mw.document.createElement('style');
  modeStyle.textContent = fs.readFileSync(
    path.resolve(__dirname, '..', 'styles', 'components', 'spine.css'), 'utf8'
  ) + '\n' + fs.readFileSync(
    path.resolve(__dirname, '..', 'styles', 'components', 'modes.css'), 'utf8'
  );
  mw.document.head.appendChild(modeStyle);

  var modeCore = sourceSlice(
    indexSource,
    "  const qaMessage       = document.getElementById('bridgeQAMessage');",
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
  var privateButton = mw.document.getElementById('modeBtnPrivate');
  privateButton.click();
  var menu = mw.document.getElementById('oraModeDropdown');
  var incompatibleFork = menu.querySelector('[data-action="fork"]');
  record('Stealth parent disables the weaker Private fork action',
    incompatibleFork.disabled
      && incompatibleFork.getAttribute('aria-disabled') === 'true'
      && /privacy/.test(incompatibleFork.title));
  incompatibleFork.click();
  record('disabled weaker fork action emits no lifecycle request',
    deleteCalls.length === 0 && exitCalls.length === 0);
  privateButton.click();

  activeTag = 'private';
  stealthButton.click();
  var strongerFork = menu.querySelector('[data-action="fork"]');
  record('Private parent keeps the stronger Stealth fork action enabled',
    !strongerFork.disabled
      && strongerFork.getAttribute('aria-disabled') !== 'true');
  stealthButton.click();
  activeTag = 'stealth';

  stealthButton.click();
  var stealthActions = Array.from(menu.querySelectorAll('[data-action]')).map(function (item) {
    return item.textContent;
  });
  record('Off Record mode menu separates Exit from irreversible deletion',
    stealthActions.indexOf('Exit Off Record') !== -1
      && stealthActions.indexOf('Delete Forever') !== -1
      && stealthActions.indexOf('Close') === -1);
  mw.document.body.classList.add('stealth-mode');
  record('runtime Off Record renders one bracket label without overlapping bridge duplicates',
    mw.getComputedStyle(mw.document.getElementById('bridgeModeLabel')).display === 'none'
      && mw.getComputedStyle(mw.document.getElementById('modeBracketLeft')).opacity !== '0');
  mw.document.body.classList.remove('stealth-mode');
  record('spine mode menu exposes ARIA state and focuses its first item',
    stealthButton.getAttribute('aria-expanded') === 'true'
      && mw.document.activeElement.textContent === 'New Off Record');
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
  menu.querySelector('[data-action="exit-stealth"]').click();
  record('mode Exit Off Record is navigation-only at the bound Dialogue id',
    exitCalls.length === 1
      && exitCalls[0] === 'stealth-a'
      && deleteCalls.length === 0
      && mw.document.activeElement === stealthButton);

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
  activeAttachmentId = 'attach-a';
  aw.document.dispatchEvent(new aw.CustomEvent('ora:conversation-load-failed', {
    detail: {
      conversation_id: 'attach-b',
      active_conversation_id: 'attach-a',
    },
  }));
  record('failed navigation preserves the prior attachment composition',
    aw.OraInputAttachments.list().length === 1
      && !!aw.document.querySelector('[data-document-id="doc-a"]'));
  aw.document.querySelector('[data-document-id="doc-a"] .transcribe-chip__close').click();

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
      && mediaOptionsSeen.conversation_id === 'attach-a'
      && mediaOptionsSeen.tag === ''
      && aw.OraInputAttachments.list()[0].conversation_id === 'attach-a');
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
  var optimisticSelectionPreservedAttachment =
    aw.document.getElementById('inputPaneAttachments').children.length === 1;
  aw.document.dispatchEvent(new aw.CustomEvent('ora:conversation-tag-changed', {
    detail: {
      conversation_id: 'attach-b',
      tag: '',
      source: 'conversation-envelope',
    },
  }));
  record('successful navigation clears attachments only after authoritative selection',
    imageAttachedToA
      && optimisticSelectionPreservedAttachment
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
  w.OraPromptOverlay.show('Overlay sizing prompt');
  record('prompt overlay ends at the Inquiry pane without including the bridge strip',
    w.document.getElementById('promptOverlay').style.height === '184px'
      && w.document.getElementById('bridgeStrip').offsetHeight === 37);
  w.OraPromptOverlay.hide();

  w.OraConversation.startFresh({ conversation_id: 'privacy-external', tag: '' });
  calls = [];
  var externalSubmits = 0;
  await w.OraConversation.submitAfterPrivacy(
    'Draft an email to my doctor about my diagnosis',
    function () { externalSubmits += 1; }
  );
  record('clear external intent suppresses privacy intervention',
    externalSubmits === 1 && calls.length === 0
      && !w.document.querySelector('.ora-privacy-intervention'));

  w.OraConversation.startFresh({ conversation_id: 'privacy-zero', tag: '' });
  calls = [];
  var zeroSubmits = 0;
  var zeroPromise = w.OraConversation.submitAfterPrivacy(
    'My password is hunter2', function () { zeroSubmits += 1; }
  );
  await wait(0);
  w.document.querySelector('.ora-privacy-intervention [data-choice="private"]').click();
  var zeroAllowed = await zeroPromise;
  record('zero-turn sensitive Inquiry retags in place before submission',
    zeroAllowed && zeroSubmits === 1
      && w.OraConversation.getActiveConversationId() === 'privacy-zero'
      && w.OraConversation.getActiveTag() === 'private'
      && calls.filter(function (call) { return /\/privacy-tag$/.test(call.url); }).length === 1
      && !calls.some(function (call) { return /\/fork$/.test(call.url); }));

  w.OraConversation.startFresh({ conversation_id: 'privacy-ask', tag: '' });
  calls = [];
  var askSubmits = 0;
  var askPromise = w.OraConversation.submitAfterPrivacy(
    'I feel lost about my marriage', function () { askSubmits += 1; }
  );
  await wait(0);
  record('ambiguous personal Inquiry waits without posting',
    !!w.document.querySelector('.ora-privacy-intervention') && calls.length === 0);
  w.document.querySelector('.ora-privacy-intervention [data-choice="standard"]').click();
  record('explicit Standard choice wins without privacy mutation',
    (await askPromise) === true && askSubmits === 1 && calls.length === 0);

  await w.OraConversation.load('fork-parent');
  var navFirst = w.document.getElementById('outputPaneNavFirst');
  var navBack = w.document.getElementById('outputPaneNavBack');
  var navForward = w.document.getElementById('outputPaneNavForward');
  var navLast = w.document.getElementById('outputPaneNavLast');
  record('latest turn disables next/last while first/previous remain available',
    !navFirst.disabled && !navBack.disabled && navForward.disabled && navLast.disabled
      && navFirst.getAttribute('aria-label') === 'First turn' && navFirst.textContent === '\u00ab'
      && navLast.getAttribute('aria-label') === 'Last turn' && navLast.textContent === '\u00bb');
  navFirst.click();
  record('first-turn control jumps to the first turn and flips boundary states',
    w.OraConversation.getCurrentTurn().assistant.content === 'Parent answer one'
      && w.document.querySelector('.output-content').textContent === 'Parent answer one'
      && w.document.getElementById('outputPaneTurnPosition').textContent === '1 of 2'
      && navFirst.disabled && navBack.disabled && !navForward.disabled && !navLast.disabled);
  var expectedFirstDate = new Date('2024-03-02T12:34:00Z').toLocaleDateString(
    undefined, { month: 'short', day: 'numeric', year: '2-digit' }
  );
  record('turn timestamp is a locale-aware short date without a time',
    w.document.getElementById('outputPaneTimestamp').textContent === expectedFirstDate
      && w.document.getElementById('outputPaneTimestamp').textContent.indexOf(':') === -1);
  navLast.click();
  record('last-turn control jumps to the final turn and restores final boundary states',
    w.OraConversation.getCurrentTurn().assistant.content === 'Parent answer two'
      && w.document.querySelector('.output-content').textContent === 'Parent answer two'
      && w.document.getElementById('outputPaneTurnPosition').textContent === '2 of 2'
      && !navFirst.disabled && !navBack.disabled && navForward.disabled && navLast.disabled);

  // A slow narrower-subject callback owns the assistant object that started
  // it. If the user navigates away and reloads that Dialogue before synthesis
  // completes, the callback must also update the fresh same-Dialogue object.
  var priorVisualDispatch = w.OraV3VisualDispatch;
  var originalNarrowCallback = null;
  w.OraV3VisualDispatch = {
    setActiveKey: function () {},
    resetDedupe: function () {},
    persistOutcome: function (_meta, outcome) {
      return Promise.resolve({ ok: true, visual_outcome: outcome });
    },
    stripBlocks: function (content) { return content; },
    replaceBlocksWithEnvelope: function (content, envelope, targetIndex) {
      var fencePattern = /```ora-visual[ \t]*\n((?:(?![ \t]*```)[^\n]*\n)*?)[ \t]*```+[ \t]*(?=\n|$)/g;
      var blockIndex = 0;
      return String(content || '').replace(fencePattern, function (match) {
        if (blockIndex++ !== targetIndex) return match;
        return '```ora-visual\n' + JSON.stringify(envelope, null, 2) + '\n```';
      });
    },
    dispatch: function (content, key, meta) {
      if (key === 'narrow-owner#0' && !originalNarrowCallback) {
        originalNarrowCallback = meta.onNarrowedEnvelopePersisted;
      }
      return String(content || '').indexOf('ora-visual') === -1 ? 0 : 1;
    },
  };
  await w.OraConversation.load('narrow-owner');
  var originatingNarrowAssistant = w.OraConversation.getCurrentTurn().assistant;
  await w.OraConversation.load('retained');
  var otherDialogueAssistant = w.OraConversation.getCurrentTurn().assistant;
  await w.OraConversation.load('narrow-owner');
  var reloadedNarrowAssistant = w.OraConversation.getCurrentTurn().assistant;
  var narrowedOutcome = {
    state: 'building',
    stage: 'legibility',
    reason: 'A narrower visual was saved and is awaiting insertion.',
    legibility_attempts: { 0: 'exhausted' },
  };
  originalNarrowCallback({
    type: 'concept_map', title: 'Narrowed visual', spec: {},
  }, narrowedOutcome, 0);
  var failedNarrowOutcome = {
    state: 'failed',
    stage: 'legibility',
    reason: 'The narrower visual could not be synthesized.',
    legibility_attempts: { 0: 'exhausted' },
  };
  originalNarrowCallback(null, failedNarrowOutcome);
  record('away-and-back narrower callback updates success and failure on same-Dialogue snapshots only',
    originatingNarrowAssistant !== reloadedNarrowAssistant
      && originatingNarrowAssistant.content.indexOf('Narrowed visual') !== -1
      && reloadedNarrowAssistant.content.indexOf('Narrowed visual') !== -1
      && originatingNarrowAssistant.visual_outcome.state === 'failed'
      && reloadedNarrowAssistant.visual_outcome.state === 'failed'
      && originatingNarrowAssistant.visual_outcome.legibility_attempts['0'] === 'exhausted'
      && otherDialogueAssistant.content === 'Answer'
      && otherDialogueAssistant.visual_outcome === undefined);
  w.OraV3VisualDispatch = priorVisualDispatch;
  await w.OraConversation.load('fork-parent');

  var privacyInput = w.document.querySelector('.input-pane textarea');
  privacyInput.value = 'My secret key is abc';
  w.localStorage.setItem('ora-v3-draft-fork-parent', privacyInput.value);
  var parentVisualSnapshot = {
    editor: 'excalidraw', conversationId: 'fork-parent', elements: [{ id: 'parent-visual' }],
  };
  var carriedVisualSnapshot = null;
  var visualCapturedBeforeFork = false;
  w.OraCanvas = {
    hasContent: function () { return true; },
    snapshotForSubmit: function () {
      visualCapturedBeforeFork = !calls.some(function (call) {
        return /\/fork$/.test(call.url);
      });
      return parentVisualSnapshot;
    },
    flushDraft: function () { return Promise.resolve(); },
    setConversationContext: function () {},
    loadCheckpoint: function () { return Promise.resolve(false); },
    clear: function () {},
  };
  calls = [];
  var forkPromise = w.OraConversation.submitAfterPrivacy(
    privacyInput.value,
    function (submissionContext) {
      carriedVisualSnapshot = submissionContext.visualSnapshot;
      return w.fetch('/chat', {
        method: 'POST',
        body: JSON.stringify({
          conversation_id: w.OraConversation.getActiveConversationId(),
          prompt: privacyInput.value,
        }),
      });
    },
    { captureVisualSnapshot: true }
  );
  await wait(0);
  w.document.querySelector('.ora-privacy-intervention [data-choice="private"]').click();
  await wait(0);
  var parentPostsBeforeFork = calls.filter(function (call) {
    return call.url === '/chat';
  }).length;
  forkResolve({
    ok: true, status: 200,
    json: function () { return Promise.resolve({
      new_conversation_id: 'privacy-child', tag: 'private',
    }); },
  });
  var forkAllowed = await forkPromise;
  var finalPosts = calls.filter(function (call) { return call.url === '/chat'; });
  record('final sensitive submit posts zero times to parent and exactly once to Private child',
    forkAllowed
      && parentPostsBeforeFork === 0
      && finalPosts.length === 1
      && JSON.parse(finalPosts[0].opts.body).conversation_id === 'privacy-child'
      && w.OraConversation.getActiveConversationId() === 'privacy-child'
      && w.OraConversation.getActiveTag() === 'private'
      && privacyInput.value === 'My secret key is abc'
      && visualCapturedBeforeFork
      && carriedVisualSnapshot === parentVisualSnapshot
      && w.localStorage.getItem('ora-v3-draft-privacy-child') === 'My secret key is abc'
      && w.localStorage.getItem('ora-v3-draft-fork-parent') === null
      && calls.filter(function (call) { return /\/fork$/.test(call.url); }).length === 1);
  delete w.OraCanvas;

  await w.OraConversation.load('fork-parent');
  calls = [];
  var auxiliaryPromise = w.OraConversation.submitChatTurn({
    message: 'Investigate this trace.',
    conversation_id: 'fork-parent',
    panel_id: 'fork-parent',
    trace_debug: {
      trace_ref: 'fork-parent/turn-a',
      symptom: 'My secret key appeared in the wrong output.',
    },
  }, { privacyText: 'My secret key appeared in the wrong output.' });
  await wait(0);
  w.document.querySelector('.ora-privacy-intervention [data-choice="private"]').click();
  await wait(0);
  var auxiliaryParentPosts = calls.filter(function (call) {
    return call.url === '/chat';
  }).length;
  forkResolve({
    ok: true, status: 200,
    json: function () { return Promise.resolve({
      new_conversation_id: 'privacy-child', tag: 'private',
    }); },
  });
  var auxiliaryConversationId = await auxiliaryPromise;
  var auxiliaryPosts = calls.filter(function (call) { return call.url === '/chat'; });
  var auxiliaryBody = JSON.parse(auxiliaryPosts[0].opts.body);
  record('auxiliary user text shares privacy gate and posts exactly once to the child',
    auxiliaryParentPosts === 0
      && auxiliaryConversationId === 'privacy-child'
      && auxiliaryPosts.length === 1
      && auxiliaryBody.conversation_id === 'privacy-child'
      && auxiliaryBody.panel_id === 'privacy-child'
      && /secret key/.test(auxiliaryBody.trace_debug.symptom));

  await w.OraConversation.load('fork-parent');
  calls = [];
  var cancelledAuxiliary = w.OraConversation.submitChatTurn({
    message: 'My password should not leave this Dialogue.',
    conversation_id: 'fork-parent',
  }, { privacyText: 'My password should not leave this Dialogue.' });
  await wait(0);
  w.document.querySelector('.ora-privacy-intervention [data-choice="cancel"]').click();
  record('cancelled auxiliary privacy sends no parent or child chat post',
    (await cancelledAuxiliary) === null
      && !calls.some(function (call) { return call.url === '/chat'; })
      && !calls.some(function (call) { return /\/fork$/.test(call.url); }));

  calls = [];
  var internalConversationId = await w.OraConversation.submitChatTurn({
    message: '2', conversation_id: 'fork-parent', panel_id: 'fork-parent',
  });
  record('non-user internal chat command preserves its direct exact-once path',
    internalConversationId === 'fork-parent'
      && calls.filter(function (call) { return call.url === '/chat'; }).length === 1
      && !w.document.querySelector('.ora-privacy-intervention'));

  await w.OraConversation.load('fork-parent');
  privacyInput.value = 'My private key must survive navigation';
  w.localStorage.setItem('ora-v3-draft-fork-parent', privacyInput.value);
  calls = [];
  var racedSubmitCount = 0;
  var racedFork = w.OraConversation.submitAfterPrivacy(
    privacyInput.value,
    function () { racedSubmitCount += 1; }
  );
  await wait(0);
  w.document.querySelector('.ora-privacy-intervention [data-choice="private"]').click();
  await wait(0);
  w.OraConversation.startFresh({ conversation_id: 'newer-selection', tag: '' });
  forkResolve({
    ok: true, status: 200,
    json: function () { return Promise.resolve({
      new_conversation_id: 'privacy-race-child', tag: 'private',
    }); },
  });
  var racedAllowed = await racedFork;
  record('successful privacy fork saves child draft before navigation can clear parent',
    racedAllowed === false
      && racedSubmitCount === 0
      && w.OraConversation.getActiveConversationId() === 'newer-selection'
      && w.localStorage.getItem('ora-v3-draft-privacy-race-child') ===
        'My private key must survive navigation'
      && w.localStorage.getItem('ora-v3-draft-fork-parent') === null);

  await w.OraConversation.load('privacy-child');
  calls = [];
  var privateSubmits = 0;
  record('explicit Private state bypasses the classifier and sends no lifecycle request',
    (await w.OraConversation.submitAfterPrivacy(
      'My password is still private', function () { privateSubmits += 1; }
    )) === true
      && privateSubmits === 1
      && calls.length === 0
      && !w.document.querySelector('.ora-privacy-intervention'));

  await w.OraConversation.load('stealth');
  calls = [];
  alerts = [];
  var invalidForkResult = await w.OraConversation.forkActive({
    tag: 'private', source: 'privacy-lattice-test',
  });
  record('programmatic Stealth-to-Private fork is blocked before fetch',
    invalidForkResult === null
      && !w.OraConversation.canForkAs('private')
      && w.OraConversation.canForkAs('stealth')
      && calls.filter(function (call) { return /\/fork$/.test(call.url); }).length === 0
      && alerts.some(function (message) { return /weaker privacy/.test(message); }));

  var turnCanvasLoads = [];
  w.OraCanvas = {
    flushDraft: function () { return Promise.resolve(); },
    setConversationContext: function () {},
    loadCheckpoint: function (conversationId, checkpointId, turnIndex, visualState, options) {
      turnCanvasLoads.push({
        conversationId: conversationId,
        checkpointId: checkpointId,
        turnIndex: turnIndex,
        options: options,
      });
      return Promise.resolve(true);
    },
  };
  await w.OraConversation.load('fork-parent');
  turnCanvasLoads = [];
  w.OraConversation.showTurn(0);
  await wait(0);
  w.OraConversation.showTurn(1);
  await wait(0);
  var historicalCanvasLoad = turnCanvasLoads[0];
  var latestCanvasLoad = turnCanvasLoads[1];
  record('turn navigation keeps historical visuals transient and restores the latest draft',
    historicalCanvasLoad
      && historicalCanvasLoad.options.currentDialogue === false
      && historicalCanvasLoad.options.preferDraft === false
      && latestCanvasLoad
      && latestCanvasLoad.options.currentDialogue === true
      && latestCanvasLoad.options.preferDraft === true);
  w.OraConversation.showTurn(0);
  await wait(0);
  delete w.OraCanvas;
  calls = [];
  var displayedFork = w.OraConversation.forkActive({
    tag: 'stealth', source: 'displayed-turn-test', await_selection: true,
  });
  await wait(0);
  var displayedForkCall = calls.find(function (call) {
    return /\/fork-parent\/fork$/.test(call.url);
  });
  var displayedForkBody = JSON.parse(displayedForkCall.opts.body || '{}');
  forkResolve({
    ok: true, status: 200,
    json: function () { return Promise.resolve({
      new_conversation_id: 'display-fork-child', tag: 'stealth',
    }); },
  });
  var displayedForkResult = await displayedFork;
  record('fork payload uses the zero-based turn currently displayed',
    displayedForkBody.fork_point_turn_index === 0
      && displayedForkBody.tag === 'stealth');
  record('selected fork starts as a true child with no copied parent turns',
    displayedForkResult && displayedForkResult.selected === true
      && w.OraConversation.getActiveConversationId() === 'display-fork-child'
      && w.OraConversation.getTurnCount() === 0
      && w.document.getElementById('outputPaneTurnPosition').textContent === '\u2014');
  w.OraConversation.appendUser('First local child question');
  w.OraConversation.appendAssistant('First local child answer');
  record('first child exchange is numbered locally as 1 of 1',
    w.OraConversation.getTurnCount() === 1
      && w.document.getElementById('outputPaneTurnPosition').textContent === '1 of 1');
  await w.OraConversation.load('fork-parent');
  record('fork leaves the parent transcript unchanged at its latest turn',
    envelopes.forkParent.messages.length === 4
      && w.OraConversation.getTurnCount() === 2
      && w.OraConversation.getCurrentTurn().assistant.content === 'Parent answer two');

  var visualHost = w.document.createElement('div');
  visualHost.className = 'visual-panel';
  w.document.body.appendChild(visualHost);
  var indexSource = fs.readFileSync(
    path.resolve(__dirname, '..', '..', 'index-v3.html'), 'utf8'
  );
  context.closeModeDropdown = function () {};
  vm.runInContext(sourceSlice(
    indexSource,
    '  const currentPaneMode = () => {',
    '  // Close dropdown on outside click or Escape.'
  ), context, { filename: 'index-pane-mode-navigation.js' });
  vm.runInContext(
    fs.readFileSync(path.resolve(__dirname, '..', 'js', 'sidebar.js'), 'utf8'),
    context,
    { filename: 'sidebar-exit-navigation.js' }
  );
  vm.runInContext(
    fs.readFileSync(path.resolve(__dirname, '..', 'media-library.js'), 'utf8'),
    context,
    { filename: 'media-library-exit-navigation.js' }
  );
  w.OraMediaLibrary.init();

  var exitSelections = [];
  var onExitSelection = function (event) {
    exitSelections.push(Object.assign({}, event.detail || {}));
  };
  w.document.addEventListener('ora:conversation-selected', onExitSelection);
  var childSelection = {
    conversation_id: 'exit-child', tag: 'stealth', await_selection: true,
  };
  w.document.dispatchEvent(new w.CustomEvent('ora:conversation-selected', {
    detail: childSelection,
  }));
  await childSelection.selection_promise;
  w.OraPaneMode.set('video');
  await wait(0);
  calls = [];
  var exitChildMessages = JSON.stringify(envelopes.exitChild.messages);
  var exitedToParent = await w.OraConversation.exitStealth('exit-child');
  w.document.removeEventListener('ora:conversation-selected', onExitSelection);
  record('Exit Stealth loads the readable direct parent at its latest turn',
    exitedToParent && exitedToParent.destination === 'parent'
      && w.OraConversation.getActiveConversationId() === 'exit-parent'
      && w.OraConversation.getCurrentTurn().assistant.content === 'Latest parent answer'
      && w.document.getElementById('outputPaneTurnPosition').textContent === '2 of 2');
  record('Exit Stealth completes the normal selection transition from video state',
    exitSelections.length === 2
      && exitSelections[1].conversation_id === 'exit-parent'
      && exitSelections[1].source === 'exit-stealth'
      && !w.document.body.classList.contains('pane-mode-video')
      && w.OraMediaLibrary.getState().conversationId === 'exit-parent'
      && w.OraSidebar.getActiveConversation() === 'exit-parent'
      && calls.filter(function (call) {
        return call.url === '/api/conversation/exit-parent';
      }).length === 1);
  record('Exit Stealth neither closes nor purges the child',
    JSON.stringify(envelopes.exitChild.messages) === exitChildMessages
      && !calls.some(function (call) { return /\/(?:close|delete-forever)$/.test(call.url); }));

  await w.OraConversation.load('exit-nested-child');
  calls = [];
  var exitedToStealthParent = await w.OraConversation.exitStealth('exit-nested-child');
  record('Exit Stealth may navigate to a direct parent that is also Stealth',
    exitedToStealthParent && exitedToStealthParent.destination === 'parent'
      && w.OraConversation.getActiveConversationId() === 'exit-stealth-parent'
      && w.OraConversation.getActiveTag() === 'stealth'
      && !calls.some(function (call) { return /\/(?:close|delete-forever)$/.test(call.url); }));

  await w.OraConversation.load('exit-orphan');
  calls = [];
  var exitedOrphan = await w.OraConversation.exitStealth('exit-orphan');
  record('missing Exit parent falls back to a fresh Standard Dialogue',
    exitedOrphan && exitedOrphan.destination === 'fresh-standard'
      && w.OraConversation.getActiveConversationId() !== 'exit-orphan'
      && w.OraConversation.getActiveTag() === ''
      && calls.some(function (call) { return call.url === '/api/conversation/missing-parent'; })
      && !calls.some(function (call) { return /\/(?:close|delete-forever)$/.test(call.url); }));

  await w.OraConversation.load('protection-pending');
  var protectedActionsButton = w.document.getElementById('outputPaneActionsBtn');
  protectedActionsButton.click();
  var protectedActionLabels = Array.from(
    w.document.querySelectorAll('#outputPaneActionsMenu .mode-dropdown-item')
  ).map(function (item) { return item.textContent; });
  record('Off Record output actions use Exit and Delete Forever, never Close',
    protectedActionLabels.indexOf('Exit Off Record') !== -1
      && protectedActionLabels.indexOf('Delete Forever') !== -1
      && protectedActionLabels.indexOf('Close') === -1);
  protectedActionsButton.click();
  w.localStorage.setItem('ora-v3-draft-protection-pending', 'keep this draft');
  calls = [];
  protectionEvents = [];
  reviewQueueOpens = [];
  var lifecycleCountBeforeProtection = lifecycleEvents.length;
  var pulseCountBeforeProtection = lifecycleChannelMessages.length;
  var pendingDelete = await w.OraConversation.deleteForever('protection-pending');
  record('System Protection hold opens the existing approval workflow and requires retry',
    pendingDelete && pendingDelete.ok === false
      && pendingDelete.pending_approval === true
      && pendingDelete.retry_required === true
      && pendingDelete.queue_id === 'queue-delete-protected'
      && reviewQueueOpens.length === 1
      && reviewQueueOpens[0].tab === 'paused'
      && protectionEvents.length === 1);
  record('protection-pending deletion does not pretend success or clear local state',
    w.OraConversation.getActiveConversationId() === 'protection-pending'
      && w.localStorage.getItem('ora-v3-draft-protection-pending') === 'keep this draft'
      && lifecycleEvents.length === lifecycleCountBeforeProtection
      && lifecycleChannelMessages.length === pulseCountBeforeProtection);

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
  record('fresh live Dialogue exposes its lifecycle action menu',
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
  var standardActionLabels = Array.from(
    actionsMenu.querySelectorAll('.mode-dropdown-item')
  ).map(function (item) { return item.textContent; });
  record('Standard output actions use Close and do not expose irreversible deletion',
    standardActionLabels.indexOf('Close') !== -1
      && standardActionLabels.indexOf('Delete Forever') === -1
      && standardActionLabels.indexOf('Exit Off Record') === -1);
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
  actionsButton.click();
  var privateActionLabels = Array.from(
    actionsMenu.querySelectorAll('.mode-dropdown-item')
  ).map(function (item) { return item.textContent; });
  record('Private output actions use the same reversible Close lifecycle',
    privateActionLabels.indexOf('Close') !== -1
      && privateActionLabels.indexOf('Delete Forever') === -1
      && privateActionLabels.indexOf('Exit Off Record') === -1);
  actionsButton.click();

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

  await runIndexPrivacyEgressTests();
  await runBootstrapPrivacyTests();
  await runScratchpadPrivacyTests();
  await runSidebarRetryPrivacyTests();
  await runIndexLifecycleControlsTests();

  var passed = results.filter(function (result) { return result.ok; }).length;
  console.log('\n' + passed + ' / ' + results.length + ' tests passed');
  process.exit(passed === results.length ? 0 : 1);
}

run().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
