#!/usr/bin/env node
/* test-capability-invocation-ui.js — WP-7.3.1
 *
 * End-to-end test for OraCapabilityInvocationUI. Spins up a jsdom host,
 * loads the module against a stub slot, walks the §13.3 happy/sad path:
 *
 *   1. Stub slot requires `prompt` (text). Run button disabled, tooltip
 *      mentions the missing prompt.
 *   2. Type a prompt → button enables.
 *   3. Submit → spinner visible, button locked, dispatch event fires
 *      with the right shape.
 *   4. Mock failure with a known common_errors[] code → error UX shows,
 *      fix-path button surfaces, clicking the configure-fix-path emits
 *      `open-settings`.
 *   5. Async slot → badge text "Sent — will arrive when ready" appears.
 *   6. Mask + image-ref widgets pull from the context provider and gate
 *      the button accordingly.
 *
 * Run:  node ~/ora/server/static/tests/test-capability-invocation-ui.js
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var path = require('path');
var fs = require('fs');

// ── jsdom bootstrap ──────────────────────────────────────────────────────────
//
// The compiler tests already vendor jsdom under
// ora-visual-compiler/tests/node_modules. We reuse that install.

var COMPILER_TEST_NODE_MODULES = path.resolve(
  __dirname, '..', 'ora-visual-compiler', 'tests', 'node_modules'
);
var JSDOM_PATH = path.join(COMPILER_TEST_NODE_MODULES, 'jsdom');

var jsdom;
try {
  jsdom = require(JSDOM_PATH);
} catch (e) {
  console.error('error: jsdom not available at ' + JSDOM_PATH);
  console.error('  install via: cd ' + path.dirname(COMPILER_TEST_NODE_MODULES) + ' && npm install');
  process.exit(2);
}

var dom = new jsdom.JSDOM('<!doctype html><html><body><div id="host"></div></body></html>', {
  pretendToBeVisual: true,
});

var w = dom.window;
global.window = w;
global.document = w.document;
global.HTMLElement = w.HTMLElement;
global.Element = w.Element;
global.Event = w.Event;
global.CustomEvent = w.CustomEvent;
global.requestAnimationFrame = w.requestAnimationFrame || function (fn) { return setTimeout(fn, 0); };
var activeConversationId = 'capability-dialogue';
var privacyCalls = [];
w.OraConversation = {
  getActiveConversationId: function () { return activeConversationId; },
  getActiveTag: function () { return ''; },
  submitAfterPrivacy: function (text, submit) {
    privacyCalls.push(text);
    return Promise.resolve(submit()).then(function () { return true; });
  },
};
// jsdom doesn't ship FileReader by default. We don't exercise file
// inputs in this test, so we leave it undefined.

// ── Module under test ────────────────────────────────────────────────────────

var UI_PATH = path.resolve(__dirname, '..', 'capability-invocation-ui.js');
require(UI_PATH);  // attaches to global.window.OraCapabilityInvocationUI
var UI = w.OraCapabilityInvocationUI;
if (!UI) {
  console.error('error: OraCapabilityInvocationUI did not register on window');
  process.exit(2);
}

// ── Capabilities fixture (subset of capabilities.json) ───────────────────────

var capabilities = JSON.parse(fs.readFileSync(
  path.resolve(__dirname, '..', '..', '..', 'config', 'capabilities.json'),
  'utf8'
));

// Synthesize a stub slot that mirrors the §13.3 test contract: requires
// `prompt`, has a configure-a-model fix path. We append it to the
// fixture so the production capabilities.json passes through unchanged.
capabilities.slots._stub_test = {
  name: '_stub_test',
  summary: 'Stub slot for the WP-7.3.1 UI test.',
  required_inputs: [
    { name: 'prompt', type: 'text', description: 'Test prompt input.' },
  ],
  optional_inputs: [],
  output: { type: 'text', description: 'Stubbed text output.' },
  execution_pattern: 'sync',
  common_errors: [
    {
      code: 'model_unavailable',
      description: 'No provider configured for this slot.',
      fix_path: 'Configure a model in Settings →',
    },
    {
      code: 'transient_failure',
      description: 'Provider hiccup.',
      fix_path: 'Retry',
    },
  ],
};
capabilities.slots._control_test = {
  name: '_control_test',
  summary: 'Non-conversation text control fixture.',
  required_inputs: [
    { name: 'name', type: 'text', description: 'Configuration display name.' },
  ],
  optional_inputs: [],
  output: { type: 'text', description: 'Stubbed control output.' },
  execution_pattern: 'sync',
  common_errors: [],
};

// ── Test harness ─────────────────────────────────────────────────────────────

var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? '  — ' + detail : ''));
}

function summarize() {
  var total = results.length;
  var passed = results.filter(function (r) { return r.ok; }).length;
  console.log('');
  console.log(passed + ' / ' + total + ' tests passed');
  if (passed < total) {
    console.log('FAILURES:');
    results.filter(function (r) { return !r.ok; }).forEach(function (r) {
      console.log('  - ' + r.name + ' :: ' + (r.detail || '(no detail)'));
    });
    process.exit(1);
  }
  process.exit(0);
}

function _resetHost() {
  // Tear down any prior controller and refresh the host element.
  if (UI._getActive()) UI.destroy();
  var host = w.document.getElementById('host');
  while (host.firstChild) host.removeChild(host.firstChild);
  return host;
}

function _flushFrames() {
  // Drain the rAF queue used for coalesced updates inside the module.
  // jsdom's pretendToBeVisual rAF runs at ~16ms intervals; we wait long
  // enough for at least two ticks so chained rAF schedules have settled.
  return new Promise(function (resolve) {
    setTimeout(function () {
      setTimeout(function () {
        setTimeout(resolve, 25);
      }, 25);
    }, 25);
  });
}

// ── Tests ────────────────────────────────────────────────────────────────────

async function testButtonDisabledWhenPromptMissing() {
  var host = _resetHost();
  UI.init({
    hostEl: host,
    capabilities: capabilities,
    slotName: '_stub_test',
  });
  var btn = host.querySelector('.ora-cap-runbtn');
  record('button disabled when no prompt typed',
    btn && btn.disabled === true,
    btn ? ('disabled=' + btn.disabled) : 'btn not found');
  var tooltip = host.querySelector('.ora-cap-tooltip');
  record('disabled-button tooltip names the missing input',
    tooltip && /test prompt input/i.test(tooltip.textContent),
    tooltip ? ('tooltip="' + tooltip.textContent + '"') : 'tooltip not found');
  record('disabled-button has native title attribute too',
    btn && /test prompt input/i.test(btn.getAttribute('title') || ''),
    btn ? ('title="' + btn.getAttribute('title') + '"') : 'btn not found');
}

async function testButtonEnablesWhenPromptTyped() {
  var host = _resetHost();
  UI.init({
    hostEl: host,
    capabilities: capabilities,
    slotName: '_stub_test',
  });
  var input = host.querySelector('textarea[name="prompt"], input[name="prompt"]');
  record('prompt input rendered as textarea',
    input && input.tagName.toLowerCase() === 'textarea',
    input ? input.tagName : 'no input');
  input.value = 'Hello, world.';
  input.dispatchEvent(new w.Event('input', { bubbles: true }));
  await _flushFrames();
  var btn = host.querySelector('.ora-cap-runbtn');
  record('button enables once prompt has text',
    btn && btn.disabled === false,
    btn ? ('disabled=' + btn.disabled) : 'btn not found');
}

async function testSubmitFiresDispatchEventAndShowsSpinner() {
  var host = _resetHost();
  var dispatched = null;
  host.addEventListener('capability-dispatch', function (e) { dispatched = e.detail; });
  var ctl = UI.init({
    hostEl: host,
    capabilities: capabilities,
    slotName: '_stub_test',
  });
  var input = host.querySelector('textarea[name="prompt"], input[name="prompt"]');
  input.value = 'A serene mountain at dawn.';
  input.dispatchEvent(new w.Event('input', { bubbles: true }));
  await _flushFrames();

  ctl.submit();
  record('submit emits capability-dispatch event',
    !!dispatched && dispatched.slot === '_stub_test',
    dispatched ? JSON.stringify(dispatched) : 'no event');
  record('dispatch payload carries the prompt',
    dispatched && dispatched.inputs && dispatched.inputs.prompt === 'A serene mountain at dawn.',
    dispatched ? JSON.stringify(dispatched.inputs) : 'no inputs');
  record('dispatch payload echoes execution_pattern=sync',
    dispatched && dispatched.execution_pattern === 'sync');

  await _flushFrames();
  var status = host.querySelector('.ora-cap-status');
  record('sync UX shows spinner status',
    status && /Working/i.test(status.textContent || ''),
    status ? status.textContent : 'no status');
  var spinnerNode = host.querySelector('.ora-cap-spinner');
  record('spinner element rendered inside status',
    !!spinnerNode);
  var btn = host.querySelector('.ora-cap-runbtn');
  record('button locked while in-flight',
    btn && btn.disabled === true);
}

async function testPromptDispatchWaitsForPrivacyAndBindsChild() {
  var host = _resetHost();
  var dispatched = null;
  var initialDispatchCount = 0;
  var release = null;
  var gateCount = 0;
  host.addEventListener('capability-dispatch', function (e) {
    initialDispatchCount += 1;
    dispatched = e.detail;
  });
  w.OraConversation.submitAfterPrivacy = function (text, submit) {
    gateCount += 1;
    return new Promise(function (resolve) {
      release = function () {
        activeConversationId = 'capability-private-child';
        Promise.resolve(submit()).then(function () { resolve(true); });
      };
    });
  };
  var ctl = UI.init({
    hostEl: host,
    capabilities: capabilities,
    slotName: '_stub_test',
  });
  var input = host.querySelector('textarea[name="prompt"], input[name="prompt"]');
  input.value = 'My medical diagnosis is private.';
  input.dispatchEvent(new w.Event('input', { bubbles: true }));
  await _flushFrames();

  var pending = ctl.submit();
  record('capability prompt dispatch waits before provider event',
    gateCount === 1 && dispatched === null);
  release();
  await pending;
  record('capability prompt dispatches once and binds the selected child',
    initialDispatchCount === 1
      && dispatched && dispatched.conversation_id === 'capability-private-child'
      && dispatched.inputs.prompt === 'My medical diagnosis is private.');

  var dispatchCount = 0;
  host.addEventListener('capability-dispatch', function () { dispatchCount += 1; });
  ctl.renderResult({ output: 'done' });
  w.OraConversation.submitAfterPrivacy = function () { return Promise.resolve(false); };
  await ctl.submit();
  await _flushFrames();
  record('cancelled capability privacy emits no provider event and unlocks form',
    dispatchCount === 0 && host.querySelector('.ora-cap-runbtn').disabled === false);

  w.OraConversation = null;
  await ctl.submit();
  record('missing capability privacy boundary fails closed', dispatchCount === 0);

  var controlHost = _resetHost();
  var controlDispatch = 0;
  controlHost.addEventListener('capability-dispatch', function () { controlDispatch += 1; });
  var control = UI.init({
    hostEl: controlHost,
    capabilities: capabilities,
    slotName: '_control_test',
  });
  var nameInput = controlHost.querySelector('input[name="name"], textarea[name="name"]');
  nameInput.value = 'Local configuration name';
  nameInput.dispatchEvent(new w.Event('input', { bubbles: true }));
  await _flushFrames();
  control.submit();
  record('non-conversation text control is not privacy-gated', controlDispatch === 1);

  activeConversationId = 'capability-dialogue';
  privacyCalls = [];
  w.OraConversation = {
    getActiveConversationId: function () { return activeConversationId; },
    getActiveTag: function () { return ''; },
    submitAfterPrivacy: function (text, submit) {
      privacyCalls.push(text);
      return Promise.resolve(submit()).then(function () { return true; });
    },
  };
}

async function testAllProviderTextFieldsWaitForPrivacy() {
  var host = _resetHost();
  var dispatched = null;
  privacyCalls = [];
  var critique = UI.init({
    hostEl: host,
    capabilities: capabilities,
    slotName: 'image_critique',
    contextProvider: function () {
      return { canvasSelection: { id: 'critique-image', kind: 'image' } };
    },
  });
  host.querySelector('[name="rubric"]').value = 'Assess my private family portrait.';
  host.querySelector('[name="genre"]').value = 'Personal grief memorial.';
  host.querySelector('[name="rubric"]').dispatchEvent(new w.Event('input', { bubbles: true }));
  await _flushFrames();
  host.addEventListener('capability-dispatch', function (event) { dispatched = event.detail; });
  await critique.submit();
  record('rubric and genre pass through the capability privacy boundary',
    privacyCalls[0] === 'Assess my private family portrait.\n\nPersonal grief memorial.'
      && dispatched
      && dispatched.inputs.rubric === 'Assess my private family portrait.'
      && dispatched.inputs.genre === 'Personal grief memorial.');

  host = _resetHost();
  dispatched = null;
  privacyCalls = [];
  var image = UI.init({
    hostEl: host,
    capabilities: capabilities,
    slotName: 'image_generates',
  });
  host.querySelector('[name="prompt"]').value = 'Already approved prompt.';
  host.querySelector('[name="style"]').value = 'Use details from my private diagnosis.';
  host.querySelector('[name="prompt"]').dispatchEvent(new w.Event('input', { bubbles: true }));
  await _flushFrames();
  host.addEventListener('capability-dispatch', function (event) { dispatched = event.detail; });
  await image.submit({ privacyApprovedText: 'Already approved prompt.' });
  record('pre-approved prompt does not let provider-bound style bypass privacy',
    privacyCalls[0] === 'Use details from my private diagnosis.' && dispatched);
}

async function testErrorUxWithFixPath() {
  var host = _resetHost();
  var settingsOpened = 0;
  host.addEventListener('open-settings', function () { settingsOpened++; });
  var ctl = UI.init({
    hostEl: host,
    capabilities: capabilities,
    slotName: '_stub_test',
  });
  var input = host.querySelector('textarea[name="prompt"], input[name="prompt"]');
  input.value = 'A test prompt';
  input.dispatchEvent(new w.Event('input', { bubbles: true }));
  await _flushFrames();
  ctl.submit();

  // Mock the dispatcher's failure callback.
  ctl.renderError({ code: 'model_unavailable' });

  var errorEl = host.querySelector('.ora-cap-error');
  record('error region becomes visible',
    errorEl && errorEl.style.display !== 'none' && /No provider/i.test(errorEl.textContent || ''),
    errorEl ? ('text="' + (errorEl.textContent || '').slice(0, 80) + '"') : 'no error el');
  var codeBadge = host.querySelector('.ora-cap-error__code');
  record('error code badge rendered',
    codeBadge && codeBadge.textContent === 'model_unavailable',
    codeBadge ? codeBadge.textContent : 'no code badge');
  var fixBtn = host.querySelector('.ora-cap-fix-btn');
  record('fix-path action button rendered',
    fixBtn && /Configure a model/i.test(fixBtn.textContent || ''),
    fixBtn ? fixBtn.textContent : 'no fix btn');

  fixBtn.dispatchEvent(new w.Event('click', { bubbles: true }));
  record('clicking configure fix-path emits open-settings',
    settingsOpened === 1, 'opened=' + settingsOpened);

  // Spinner should clear after error
  var status = host.querySelector('.ora-cap-status');
  record('spinner cleared after error',
    !status || !/Working/i.test(status.textContent || ''));

  // Button re-enabled (input still valid)
  await _flushFrames();
  var btn = host.querySelector('.ora-cap-runbtn');
  record('button re-enabled after error so user can retry',
    btn && btn.disabled === false);
}

async function testRetryFixPath() {
  var host = _resetHost();
  var dispatchCount = 0;
  var lastDetail = null;
  host.addEventListener('capability-dispatch', function (e) {
    dispatchCount++;
    lastDetail = e.detail;
  });
  var ctl = UI.init({
    hostEl: host,
    capabilities: capabilities,
    slotName: '_stub_test',
  });
  var input = host.querySelector('textarea[name="prompt"], input[name="prompt"]');
  input.value = 'Retry test prompt';
  input.dispatchEvent(new w.Event('input', { bubbles: true }));
  await _flushFrames();
  ctl.submit();
  record('first submit dispatches (retry test)', dispatchCount === 1);

  ctl.renderError({ code: 'transient_failure' });
  var fixBtn = host.querySelector('.ora-cap-fix-btn');
  record('Retry fix-path button rendered',
    fixBtn && /Retry/i.test(fixBtn.textContent || ''));
  fixBtn.dispatchEvent(new w.Event('click', { bubbles: true }));
  record('Retry click re-dispatches with the same inputs',
    dispatchCount === 2 && lastDetail && lastDetail.retry === true && lastDetail.inputs.prompt === 'Retry test prompt',
    'count=' + dispatchCount + ' retry=' + (lastDetail && lastDetail.retry));
}

async function testAsyncBadge() {
  var host = _resetHost();
  // Use the live video_generates slot — async, requires `prompt`.
  var ctl = UI.init({
    hostEl: host,
    capabilities: capabilities,
    slotName: 'video_generates',
  });
  var btn = host.querySelector('.ora-cap-runbtn');
  record('async slot button labelled "Send"',
    btn && /Send/.test(btn.textContent),
    btn ? btn.textContent : 'no btn');
  var input = host.querySelector('textarea[name="prompt"], input[name="prompt"]');
  input.value = 'A short test video.';
  input.dispatchEvent(new w.Event('input', { bubbles: true }));
  await _flushFrames();
  ctl.submit();
  await _flushFrames();
  var status = host.querySelector('.ora-cap-status');
  record('async UX shows "sent" badge',
    status && /Sent/.test(status.textContent || ''),
    status ? status.textContent : 'no status');
  var badge = host.querySelector('.ora-cap-badge');
  record('async badge element renders',
    badge && /Sent/.test(badge.textContent || ''));
}

async function testImageRefAndMaskUseContext() {
  var host = _resetHost();
  var ctxState = { canvasSelection: null, maskRef: null };
  var ctl = UI.init({
    hostEl: host,
    capabilities: capabilities,
    // image_edits requires image + mask + prompt — all three. The slot
    // contract is the source of truth for this gate: the UI reads
    // `contract.required_inputs` directly (no hardcoded slot list), so the
    // assertions below are derived from the contract rather than restating
    // it. Canonical: vault "Reference — Capability Invocation Contracts"
    // §3.2, mirrored by config/capabilities.json, which is what this test
    // loads. `prompt` was promoted optional → required in 866c8028.
    slotName: 'image_edits',
    contextProvider: function () { return ctxState; },
  });

  // Pin the contract itself. If `prompt` is ever demoted back to optional,
  // this fails here — loudly and by name — instead of silently loosening
  // the gate assertions that follow.
  var editRequireds = capabilities.slots.image_edits.required_inputs || [];
  var requiredNames = editRequireds.map(function (s) { return s.name; });
  record('contract: image_edits requires image + mask + prompt',
    requiredNames.indexOf('image') !== -1
    && requiredNames.indexOf('mask') !== -1
    && requiredNames.indexOf('prompt') !== -1,
    'required_inputs=' + requiredNames.join(','));
  var promptSpec = editRequireds.filter(function (s) { return s.name === 'prompt'; })[0];
  // The tooltip renders each missing input as `description || name`.
  var promptLabel = promptSpec ? (promptSpec.description || promptSpec.name) : 'prompt';

  var btn = host.querySelector('.ora-cap-runbtn');
  record('image_edits button starts disabled (no image, no mask)',
    btn && btn.disabled === true);
  var tooltip = host.querySelector('.ora-cap-tooltip');
  record('disabled tooltip mentions multiple missing inputs',
    tooltip && /Missing inputs/i.test(tooltip.textContent || ''),
    tooltip ? tooltip.textContent : 'no tooltip');

  // Provide a selection + mask via the context provider, refresh via
  // setContextProvider. The prompt is still missing, so the gate must hold.
  ctxState.canvasSelection = { id: 'img_42', kind: 'image' };
  ctxState.maskRef = { kind: 'rect', x: 10, y: 10, w: 100, h: 100 };
  ctl.setContextProvider(function () { return ctxState; });
  await _flushFrames();
  record('button stays disabled with image + mask but no prompt',
    btn && btn.disabled === true,
    'disabled=' + (btn && btn.disabled));

  // Exactly one input is outstanding, and it is `prompt` — not image, not
  // mask. The single-missing tooltip form pins that down by name.
  tooltip = host.querySelector('.ora-cap-tooltip');
  record('disabled tooltip names the missing prompt specifically',
    tooltip && (tooltip.textContent || '') === 'Missing: ' + promptLabel,
    tooltip ? ('tooltip="' + tooltip.textContent + '"') : 'no tooltip');
  record('disabled title attribute names the missing prompt too',
    btn && (btn.getAttribute('title') || '') === 'Missing: ' + promptLabel,
    btn ? ('title="' + btn.getAttribute('title') + '"') : 'no btn');

  var dispatchedBlank = null;
  function onBlank(e) { dispatchedBlank = e.detail; }
  host.addEventListener('capability-dispatch', onBlank);
  var blankResult = ctl.submit();
  record('submit() does not dispatch while the required prompt is missing',
    dispatchedBlank === null && blankResult === null,
    dispatchedBlank ? JSON.stringify(dispatchedBlank.inputs) : 'no dispatch');
  host.removeEventListener('capability-dispatch', onBlank);

  ctl.destroy();
  host = _resetHost();
  ctxState = {
    canvasSelection: { id: 'img_42', kind: 'image' },
    maskRef: { kind: 'rect', x: 10, y: 10, w: 100, h: 100 },
  };
  ctl = UI.init({
    hostEl: host,
    capabilities: capabilities,
    slotName: 'image_edits',
    contextProvider: function () { return ctxState; },
  });
  btn = host.querySelector('.ora-cap-runbtn');
  await _flushFrames();
  record('fresh image_edits form starts disabled until the prompt is typed',
    btn && btn.disabled === true,
    'disabled=' + (btn && btn.disabled));

  // Type a prompt — the last outstanding requirement.
  var promptInput = host.querySelector('textarea[name="prompt"], input[name="prompt"]');
  promptInput.value = 'Replace the masked area with a tree.';
  promptInput.dispatchEvent(new w.Event('input', { bubbles: true }));
  await _flushFrames();
  record('button enables once the required prompt is supplied',
    btn && btn.disabled === false,
    'disabled=' + (btn && btn.disabled));

  var dispatched = null;
  host.addEventListener('capability-dispatch', function (e) { dispatched = e.detail; });
  ctl.submit();
  record('dispatch carries image ref + mask + prompt',
    dispatched
    && dispatched.inputs.image === 'img_42'
    && dispatched.inputs.mask
    && dispatched.inputs.mask.kind === 'rect'
    && dispatched.inputs.prompt === 'Replace the masked area with a tree.',
    dispatched ? JSON.stringify(dispatched.inputs) : 'no dispatch');
}

async function testEnumDirectionAndNumberWidgets() {
  var host = _resetHost();
  // image_outpaints exercises enum (aspect_ratio), direction-list (directions)
  var ctxState = { canvasSelection: { id: 'img_99', kind: 'image' } };
  var ctl = UI.init({
    hostEl: host,
    capabilities: capabilities,
    slotName: 'image_outpaints',
    contextProvider: function () { return ctxState; },
  });
  // Aspect ratio is optional → has empty default option
  var enumSel = host.querySelector('.ora-cap-input--enum');
  record('enum widget rendered as <select>',
    enumSel && enumSel.tagName.toLowerCase() === 'select');
  // direction-list — pick top + right
  var dirCheckTop = host.querySelector('input[type="checkbox"][value="top"]');
  var dirCheckRight = host.querySelector('input[type="checkbox"][value="right"]');
  record('direction-list rendered with top+right checkboxes',
    !!dirCheckTop && !!dirCheckRight);
  dirCheckTop.checked = true;
  dirCheckRight.checked = true;
  dirCheckTop.dispatchEvent(new w.Event('change', { bubbles: true }));
  // Type a prompt
  var promptInput = host.querySelector('textarea[name="prompt"], input[name="prompt"]');
  promptInput.value = 'Continue the meadow upwards and to the right.';
  promptInput.dispatchEvent(new w.Event('input', { bubbles: true }));
  await _flushFrames();
  var btn = host.querySelector('.ora-cap-runbtn');
  record('outpaint button enables once image+directions+prompt are set',
    btn && btn.disabled === false,
    'disabled=' + (btn && btn.disabled));

  var dispatched = null;
  host.addEventListener('capability-dispatch', function (e) { dispatched = e.detail; });
  ctl.submit();
  record('outpaint dispatch carries directions array',
    dispatched && Array.isArray(dispatched.inputs.directions)
    && dispatched.inputs.directions.indexOf('top') !== -1
    && dispatched.inputs.directions.indexOf('right') !== -1
    && dispatched.inputs.directions.length === 2,
    dispatched ? JSON.stringify(dispatched.inputs.directions) : 'no dispatch');
}

async function testNumberWidgetClamps() {
  var host = _resetHost();
  // image_varies: count + variation_strength
  var ctxState = { canvasSelection: { id: 'img_5', kind: 'image' } };
  var ctl = UI.init({
    hostEl: host,
    capabilities: capabilities,
    slotName: 'image_varies',
    contextProvider: function () { return ctxState; },
  });
  // The count input should default to 4 (per spec).
  var countInput = host.querySelector('input[name="count"]');
  record('count widget renders with default value',
    countInput && countInput.value === '4',
    countInput ? ('value=' + countInput.value) : 'no count input');
  // Float widget should have step 0.01
  var strengthInput = host.querySelector('input[name="variation_strength"]');
  record('float widget uses step 0.01',
    strengthInput && strengthInput.step === '0.01',
    strengthInput ? ('step=' + strengthInput.step) : 'no input');
  // Min/max enforced via attributes (browser will clamp on submit; we
  // verify attribute presence)
  record('float widget has min/max attributes',
    strengthInput && strengthInput.min === '0' && strengthInput.max === '1',
    strengthInput ? ('min=' + strengthInput.min + ' max=' + strengthInput.max) : 'no input');

  // submit — image_varies only requires source_image, which the context fills
  await _flushFrames();
  var btn = host.querySelector('.ora-cap-runbtn');
  record('image_varies button enabled when source_image is provided via context',
    btn && btn.disabled === false,
    'disabled=' + (btn && btn.disabled));
  var dispatched = null;
  host.addEventListener('capability-dispatch', function (e) { dispatched = e.detail; });
  ctl.submit();
  record('image_varies dispatch carries count + variation_strength + source_image',
    dispatched
    && dispatched.inputs.source_image === 'img_5'
    && dispatched.inputs.count === 4
    && dispatched.inputs.variation_strength === 0.5,
    dispatched ? JSON.stringify(dispatched.inputs) : 'no dispatch');
}

async function testRenderResultText() {
  var host = _resetHost();
  // image_to_prompt produces text output
  var ctxState = { canvasSelection: { id: 'img_77', kind: 'image' } };
  var ctl = UI.init({
    hostEl: host,
    capabilities: capabilities,
    slotName: 'image_to_prompt',
    contextProvider: function () { return ctxState; },
  });
  await _flushFrames();
  ctl.submit();
  ctl.renderResult({ output: 'A photorealistic mountain at sunrise, …' });
  var resultEl = host.querySelector('.ora-cap-result');
  record('text result region renders',
    resultEl && resultEl.style.display !== 'none' && /photorealistic mountain/.test(resultEl.textContent),
    resultEl ? ('text="' + (resultEl.textContent || '').slice(0, 60) + '"') : 'no result el');
  var typeBadge = host.querySelector('.ora-cap-result__type');
  record('result type badge reflects slot output type',
    typeBadge && typeBadge.textContent === 'text',
    typeBadge ? typeBadge.textContent : 'no type badge');
}

async function testSetSlotSwitch() {
  var host = _resetHost();
  var ctl = UI.init({
    hostEl: host,
    capabilities: capabilities,
    slotName: '_stub_test',
  });
  ctl.setSlot('image_critique');
  // image_critique: requires image, optional rubric / genre / depth (depth is enum)
  var depthSel = host.querySelector('select[name="depth"]');
  record('setSlot re-renders with the new contract',
    depthSel && depthSel.tagName.toLowerCase() === 'select',
    depthSel ? ('options=' + depthSel.options.length) : 'no depth select');
  record('setSlot wipes old form state',
    !host.querySelector('input[name="prompt"], textarea[name="prompt"]'));
}

async function testUnknownSlotThrows() {
  var host = _resetHost();
  var threw = false;
  try {
    UI.init({
      hostEl: host,
      capabilities: capabilities,
      slotName: '_does_not_exist',
    });
  } catch (e) {
    threw = /unknown slot/i.test(e.message);
  }
  record('init throws on unknown slot', threw);
}

async function testDestroyCleansUp() {
  var host = _resetHost();
  var ctl = UI.init({
    hostEl: host,
    capabilities: capabilities,
    slotName: '_stub_test',
  });
  record('host has form before destroy',
    !!host.querySelector('.ora-cap-form'));
  ctl.destroy();
  record('host is empty after destroy',
    host.children.length === 0);
}

// ── Where a failure goes when the popover is gone or belongs elsewhere ───────
//
// Capability modules report failures through the singleton, and by the time
// most failures arrive there is no popover left: v3-pack-toolbars.js closes
// it 250 ms after dispatch and that close calls destroy(). image_generates
// is also dispatched from three places that never open a popover at all.
// A plain delegate therefore threw into the module's swallow-catch (silence),
// or painted one slot's failure into another slot's popover and cleared that
// slot's in-flight state mid-run.
//
// The pane fixture is the real component: visual-panel.js mounts cleanly in
// jsdom without Konva and registers itself as OraPanels.visual._getActive(),
// which is the surface the routing code resolves. A spy would prove the call
// was made; a real panel proves the user can read the result.

require(path.resolve(__dirname, '..', 'visual-panel.js'));

var _paneSeq = 0;

function _mountPane() {
  var el = w.document.createElement('div');
  w.document.body.appendChild(el);
  // Each panel needs its own id — VisualPanel builds element ids from it.
  var panel = new w.VisualPanel(el, { id: 'cap-ui-pane-' + (++_paneSeq) });
  panel.init();
  // A Konva-less init leaves "Konva not loaded …" on the bar. Start clean so
  // every assertion below is about what the routing code wrote.
  panel._errorBar.textContent = '';
  panel._errorBar.hidden = true;
  return panel;
}

function _unmountPane(panel) {
  try { panel.destroy(); } catch (_e) { /* ignore */ }
  if (panel.el && panel.el.parentNode) panel.el.parentNode.removeChild(panel.el);
}

// What the user can actually read off the pane right now.
function _paneText(panel) {
  var bar = panel && panel._errorBar;
  if (!bar || bar.hidden) return null;
  return (bar.textContent || '') || null;
}

function _noPaneMounted() {
  var active = w.OraPanels && w.OraPanels.visual && w.OraPanels.visual._getActive();
  if (active) _unmountPane(active);
  return !(w.OraPanels && w.OraPanels.visual && w.OraPanels.visual._getActive());
}

async function testErrorRendersInLivePopoverForItsOwnSlot() {
  var host = _resetHost();
  var pane = _mountPane();
  UI.init({ hostEl: host, capabilities: capabilities, slotName: '_stub_test' });

  UI.renderError({
    slot: '_stub_test',
    code: 'model_unavailable',
    message: 'No provider configured for this slot.',
  });

  var errorEl = host.querySelector('.ora-cap-error');
  record('live popover for the failing slot renders the error itself',
    errorEl && errorEl.style.display !== 'none'
      && /No provider configured/i.test(errorEl.textContent || ''),
    errorEl ? ('text="' + (errorEl.textContent || '').slice(0, 60) + '"') : 'no error el');
  record('the popover path still surfaces the fix-path button',
    !!host.querySelector('.ora-cap-fix-btn'));
  record('nothing is written to the pane when the popover took it',
    _paneText(pane) === null,
    'pane=' + JSON.stringify(_paneText(pane)));

  _unmountPane(pane);
}

async function testErrorRoutesToPaneWhenPopoverWasDestroyed() {
  var host = _resetHost();
  var pane = _mountPane();
  var ctl = UI.init({ hostEl: host, capabilities: capabilities, slotName: '_stub_test' });
  ctl.destroy();   // exactly what v3-pack-toolbars.js does 250 ms after dispatch

  var threw = null;
  var ret;
  try {
    ret = UI.renderError({
      slot: '_stub_test',
      code: 'quota_exceeded',
      message: 'Provider rate limit hit.',
    });
  } catch (e) { threw = e; }

  record('a late failure does not throw into the module swallow-catch',
    !threw, threw ? String(threw.message) : '');
  record('a destroyed popover routes the failure to the Exhibits pane bar',
    /_stub_test failed \[quota_exceeded\]/.test(_paneText(pane) || '')
      && /rate limit/i.test(_paneText(pane) || ''),
    'pane=' + JSON.stringify(_paneText(pane)));
  record('the reporter reports that a surface took the error',
    ret === true, 'ret=' + ret);

  _unmountPane(pane);
}

async function testLateFailureCannotContaminateAnotherSlotsPopover() {
  var host = _resetHost();
  var pane = _mountPane();

  // Slot A ran; its popover has since auto-closed.
  var a = UI.init({ hostEl: host, capabilities: capabilities, slotName: '_stub_test' });
  a.destroy();

  // The user has opened slot B's popover and started a run there. B is the
  // non-privacy control fixture, so its submit dispatches straight through
  // and leaves it genuinely in flight.
  var hostB = w.document.createElement('div');
  w.document.body.appendChild(hostB);
  var b = UI.init({ hostEl: hostB, capabilities: capabilities, slotName: '_control_test' });
  var nameInput = hostB.querySelector('input[name="name"], textarea[name="name"]');
  nameInput.value = 'Premium';
  nameInput.dispatchEvent(new w.Event('input', { bubbles: true }));
  await _flushFrames();
  b.submit();
  record('slot B is genuinely in flight before the sibling failure arrives',
    b._state.inFlight === true, 'inFlight=' + b._state.inFlight);

  // Slot A's request now fails, long after A's popover is gone.
  UI.renderError({
    slot: '_stub_test',
    code: 'quota_exceeded',
    message: 'Provider rate limit hit.',
  });

  record("slot A's late failure lands on the pane, not on slot B's popover",
    /_stub_test failed \[quota_exceeded\]/.test(_paneText(pane) || ''),
    'pane=' + JSON.stringify(_paneText(pane)));
  var bError = hostB.querySelector('.ora-cap-error');
  record("slot B's popover shows no error that was never slot B's",
    !bError || bError.style.display === 'none' || !(bError.textContent || '').trim(),
    bError ? ('B error="' + (bError.textContent || '').slice(0, 60) + '"') : 'no error el');
  record("slot B's in-flight state survives its sibling's failure",
    b._state.inFlight === true, 'inFlight=' + b._state.inFlight);
  var bStatus = hostB.querySelector('.ora-cap-status');
  record("slot B's spinner keeps running for slot B's own request",
    bStatus && /Working/i.test(bStatus.textContent || ''),
    bStatus ? ('status="' + bStatus.textContent + '"') : 'no status');

  b.destroy();
  hostB.parentNode.removeChild(hostB);
  _unmountPane(pane);
}

async function testPopoverlessDispatchStillReachesTheUser() {
  _resetHost();
  UI.destroy();
  var pane = _mountPane();
  record('no popover is mounted (the image_generates dispatch shape)',
    UI._getActive() === null, 'active=' + UI._getActive());

  var ret = UI.renderError({
    slot: 'image_generates',
    code: 'model_unavailable',
    message: 'No image provider is configured.',
  });

  record('a popover-less dispatch failure reaches the Exhibits pane bar',
    ret === true
      && /image_generates failed \[model_unavailable\]/.test(_paneText(pane) || '')
      && /No image provider/i.test(_paneText(pane) || ''),
    'pane=' + JSON.stringify(_paneText(pane)));

  _unmountPane(pane);
}

async function testNoPopoverAndNoPaneWarnsRatherThanSwallows() {
  _resetHost();
  UI.destroy();
  record('no pane is mounted either', _noPaneMounted());

  var warned = [];
  var realWarn = console.warn;
  console.warn = function () {
    warned.push(Array.prototype.slice.call(arguments).join(' '));
  };
  var threw = null;
  var ret;
  try {
    ret = UI.renderError({
      slot: 'image_generates',
      code: 'model_unavailable',
      message: 'No image provider is configured.',
    });
  } catch (e) {
    threw = e;
  } finally {
    console.warn = realWarn;
  }

  record('reporting with no surface at all does not throw',
    !threw, threw ? String(threw.message) : '');
  record('...it warns loudly instead of failing silently',
    warned.length === 1
      && /image_generates/.test(warned[0])
      && /model_unavailable/.test(warned[0]),
    JSON.stringify(warned));
  record('...and reports that no surface took it',
    ret === false, 'ret=' + ret);
}

async function testPaneRetractionOnlyClearsThisLayersOwnMessage() {
  var host = _resetHost();
  UI.destroy();
  var pane = _mountPane();

  // This layer writes a failure to the pane (no popover to take it).
  UI.renderError({
    slot: 'image_generates',
    code: 'model_unavailable',
    message: 'No image provider is configured.',
  });
  record('the pane carries this layer\'s failure',
    /image_generates failed/.test(_paneText(pane) || ''),
    'pane=' + JSON.stringify(_paneText(pane)));

  // Someone else — the compiler's fallback path — replaces it.
  pane._showErrorBar('Visual could not be rendered');

  var ctl = UI.init({ hostEl: host, capabilities: capabilities, slotName: '_stub_test' });
  var input = host.querySelector('textarea[name="prompt"], input[name="prompt"]');
  input.value = 'A new run.';
  input.dispatchEvent(new w.Event('input', { bubbles: true }));
  await _flushFrames();
  ctl.submit();

  record('a new run does not retract a message this layer did not write',
    _paneText(pane) === 'Visual could not be rendered',
    'pane=' + JSON.stringify(_paneText(pane)));

  // Same again, but with this layer's own message still on the bar.
  ctl.destroy();
  UI.destroy();
  UI.renderError({
    slot: 'image_generates',
    code: 'model_unavailable',
    message: 'No image provider is configured.',
  });
  record('this layer\'s message is back on the bar',
    /image_generates failed/.test(_paneText(pane) || ''),
    'pane=' + JSON.stringify(_paneText(pane)));

  var ctl2 = UI.init({ hostEl: host, capabilities: capabilities, slotName: '_stub_test' });
  var input2 = host.querySelector('textarea[name="prompt"], input[name="prompt"]');
  input2.value = 'A newer run.';
  input2.dispatchEvent(new w.Event('input', { bubbles: true }));
  await _flushFrames();
  ctl2.submit();

  record('a new run does retract this layer\'s own previous message',
    _paneText(pane) === null,
    'pane=' + JSON.stringify(_paneText(pane)));

  ctl2.destroy();
  _unmountPane(pane);
}

// submit() is the start-of-run retraction, but the three popover-less
// dispatch paths (index-v3.html, js/slash-command-client.js,
// prompt-template-runtime.js) never call it. Without an end-of-run
// retraction a failed run's verdict outlived the next SUCCESSFUL run and
// sat pinned over the image that run had just produced — indefinitely,
// since the panel's own auto-clear (_hideImageError) early-returns on a
// bar _showErrorBar has stripped the --image class from.
async function testPopoverlessSuccessRetractsThePreviousFailure() {
  var host = _resetHost();
  UI.destroy();                       // the popover-less dispatch shape
  var pane = _mountPane();

  var Generates = require(path.resolve(__dirname, '..', 'capability-image-generates.js'));

  var mode = 'fail';
  function scriptedFetch() {
    if (mode === 'fail') {
      return Promise.resolve({
        ok: false,
        status: 503,
        json: function () {
          return Promise.resolve({
            error: { code: 'model_unavailable', message: 'Provider is down.' },
          });
        },
      });
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: function () {
        return Promise.resolve({ image: { data: 'QUJD', mime_type: 'image/png' } });
      },
    });
  }

  // visualPanel is left null: where the bytes land is a separate concern
  // (covered in test-capability-image-generates.js), and the module calls
  // renderResult on success either way.
  Generates.init({ hostEl: host, visualPanel: null, fetchImpl: scriptedFetch });

  try {
    await Generates.handleDispatch({ slot: 'image_generates', inputs: { prompt: 'a serene mountain' } });
  } catch (_e) { /* reported on the pane, then re-raised */ }
  await _flushFrames();

  record('a popover-less failure is on the pane before the next run',
    /image_generates failed \[model_unavailable\]/.test(_paneText(pane) || ''),
    'pane=' + JSON.stringify(_paneText(pane)));

  mode = 'ok';
  await Generates.handleDispatch({ slot: 'image_generates', inputs: { prompt: 'a serene mountain' } });
  await _flushFrames();

  record('a SUCCESSFUL popover-less run retracts the previous failure',
    _paneText(pane) === null,
    'pane=' + JSON.stringify(_paneText(pane)));

  // The end-of-run retraction is ownership-scoped exactly as the
  // start-of-run one is: a message this layer did not write survives.
  mode = 'fail';
  try {
    await Generates.handleDispatch({ slot: 'image_generates', inputs: { prompt: 'a serene mountain' } });
  } catch (_e) { /* reported on the pane, then re-raised */ }
  await _flushFrames();
  pane._showErrorBar('Visual could not be rendered');

  mode = 'ok';
  await Generates.handleDispatch({ slot: 'image_generates', inputs: { prompt: 'a serene mountain' } });
  await _flushFrames();

  record('a success does not retract a pane message this layer did not write',
    _paneText(pane) === 'Visual could not be rendered',
    'pane=' + JSON.stringify(_paneText(pane)));

  if (typeof Generates.destroy === 'function') {
    try { Generates.destroy(); } catch (_e) { /* ignore */ }
  }
  _unmountPane(pane);
}

// VisualPanel.prototype._showErrorBar opens `if (!this._errorBar) return;`
// — a silent no-op. Reading "it didn't throw" as "the user can read it"
// made the reporter claim success, skip the console.warn arm, and display
// the failure nowhere at all: the exact swallow this routing exists to stop.
async function testPaneWithNoErrorBarFallsThroughToTheConsole() {
  _resetHost();
  UI.destroy();
  var pane = _mountPane();
  var realBar = pane._errorBar;
  pane._errorBar = null;              // the state _showErrorBar no-ops in

  var warned = [];
  var realWarn = console.warn;
  console.warn = function () {
    warned.push(Array.prototype.slice.call(arguments).join(' '));
  };
  var ret;
  try {
    ret = UI.renderError({
      slot: 'image_generates',
      code: 'model_unavailable',
      message: 'No image provider is configured.',
    });
  } finally {
    console.warn = realWarn;
  }

  record('a pane with no error bar does not get reported as having taken it',
    ret === false, 'ret=' + ret);
  record('...so the failure falls through to the console rather than nowhere',
    warned.length === 1
      && /image_generates/.test(warned[0])
      && /model_unavailable/.test(warned[0]),
    JSON.stringify(warned));

  pane._errorBar = realBar;
  _unmountPane(pane);
}

// Four renderError sites fire before any request is made — a missing
// required input, or a critique with neither rubric nor genre. The popover
// gates required inputs, but the popover-less dispatch paths (pack
// templates, slash commands) do not, so a dispatch can and does arrive
// short an input. The round-trip cases below run on valid fixtures and
// never reach any of them.
async function testSynchronousPreflightFailuresNameTheirSlot() {
  var host = _resetHost();
  UI.destroy();
  var pane = _mountPane();

  function unreachableFetch() {
    return Promise.reject(new Error(
      'pre-flight refused too late — a request was made'));
  }

  var CASES = [
    ['image_critique', 'capability-image-critique.js', 'OraCapabilityImageCritique',
      { rubric: 'composition' }, 'no_specific_guidance', /requires an image input/i],
    ['image_critique', 'capability-image-critique.js', 'OraCapabilityImageCritique',
      { image: 'data:image/png;base64,AA' }, 'no_specific_guidance', /rubric or a genre/i],
    ['image_styles', 'capability-image-styles.js', 'OraCapabilityImageStyles',
      { source_image: 'data:image/png;base64,AA' }, 'references_incompatible', /style_reference/],
    ['image_varies', 'capability-image-varies.js', 'OraCapabilityImageVaries',
      {}, 'source_ambiguous', /non-empty source_image/],
  ];

  for (var i = 0; i < CASES.length; i++) {
    var slot = CASES[i][0];
    var file = CASES[i][1];
    var globalName = CASES[i][2];
    var inputs = CASES[i][3];
    var code = CASES[i][4];
    var msgRe = CASES[i][5];

    require(path.resolve(__dirname, '..', file));
    var mod = w[globalName];
    mod.init({ hostEl: host, visualPanel: null, fetchImpl: unreachableFetch });

    // The popover was opened and then auto-closed, as on every dispatch.
    var ctl = UI.init({ hostEl: host, capabilities: capabilities, slotName: slot });
    ctl.destroy();

    pane._errorBar.textContent = '';
    pane._errorBar.hidden = true;

    try {
      await mod.handleDispatch({ slot: slot, inputs: inputs });
    } catch (_e) { /* the guard rejects; the failure is reported on the pane */ }
    await _flushFrames();

    var text = _paneText(pane) || '';
    record(slot + ' names its own slot for a pre-flight ' + code + ' failure',
      text.indexOf(slot + ' failed [' + code + ']') === 0 && msgRe.test(text),
      'pane=' + JSON.stringify(text));

    if (typeof mod.destroy === 'function') {
      try { mod.destroy(); } catch (_e) { /* ignore */ }
    }
  }

  UI.destroy();
  _unmountPane(pane);
}

// The slot tag on the payload is what lets the reporter tell "this
// popover's failure" from "some other slot's failure". Asserting it at the
// singleton proves the routing; only a real dispatch through each module
// proves the modules actually send it. Every module here is driven through
// a genuine failing round-trip, with the popover closed first — the state
// every post-network failure actually arrives in.
async function testEveryModuleNamesItsOwnSlotOnThePane() {
  var host = _resetHost();
  UI.destroy();
  var pane = _mountPane();

  function failingFetch() {
    return Promise.resolve({
      ok: false,
      status: 503,
      json: function () {
        return Promise.resolve({
          error: { code: 'model_unavailable', message: 'Provider is down.' },
        });
      },
      text: function () { return Promise.resolve('Provider is down.'); },
    });
  }

  // image_outpaints is attach-style with different inputs; it has its own
  // case below.
  var MODULES = [
    ['image_generates', 'capability-image-generates.js', 'OraCapabilityImageGenerates',
      { prompt: 'a serene mountain' }],
    ['image_upscales', 'capability-image-upscales.js', 'OraCapabilityImageUpscales',
      { image: 'img_1' }],
    ['image_styles', 'capability-image-styles.js', 'OraCapabilityImageStyles',
      { source_image: 'data:image/png;base64,AA', style_reference: 'data:image/png;base64,BB' }],
    ['image_varies', 'capability-image-varies.js', 'OraCapabilityImageVaries',
      { source_image: 'img_1' }],
    ['image_to_prompt', 'capability-image-to-prompt.js', 'OraCapabilityImageToPrompt',
      { image: 'img_1' }],
    ['image_critique', 'capability-image-critique.js', 'OraCapabilityImageCritique',
      { image: 'data:image/png;base64,AA', rubric: 'composition' }],
    ['video_generates', 'capability-video-generates.js', 'OraCapabilityVideoGenerates',
      { prompt: 'a cat' }],
    ['style_trains', 'capability-style-trains.js', 'OraCapabilityStyleTrains',
      { name: 'my-style', reference_images: ['a', 'b', 'c'] }],
  ];

  for (var i = 0; i < MODULES.length; i++) {
    var slot = MODULES[i][0];
    var file = MODULES[i][1];
    var globalName = MODULES[i][2];
    var inputs = MODULES[i][3];

    require(path.resolve(__dirname, '..', file));
    var mod = w[globalName];
    mod.init({ hostEl: host, visualPanel: null, fetchImpl: failingFetch });

    // The popover was opened and then auto-closed, as it is on every
    // dispatch (v3-pack-toolbars.js, 250 ms).
    var ctl = UI.init({ hostEl: host, capabilities: capabilities, slotName: slot });
    ctl.destroy();

    pane._errorBar.textContent = '';
    pane._errorBar.hidden = true;

    try {
      await mod.handleDispatch({ slot: slot, inputs: inputs });
    } catch (_e) { /* the failure is reported, not thrown to the caller */ }
    await _flushFrames();

    var text = _paneText(pane) || '';
    record(slot + ' names itself on the pane when it fails',
      text.indexOf(slot + ' failed [') === 0,
      'pane=' + JSON.stringify(text));

    if (typeof mod.destroy === 'function') {
      try { mod.destroy(); } catch (_e) { /* ignore */ }
    }
  }

  UI.destroy();
  _unmountPane(pane);
}

// image_outpaints never called renderError at all — it only emitted
// `capability-error`, an event with zero production listeners, so every
// outpaint failure was silent end to end.
function _stubImageNode() {
  return {
    attrs: { naturalWidth: 200, naturalHeight: 100, image_id: 'pane-img-1' },
    getAttrs: function () { return this.attrs; },
    image: function (img) { if (img) this._img = img; return this._img; },
    setAttrs: function (a) { Object.assign(this.attrs, a); },
    getClientRect: function () { return { x: 0, y: 0, width: 200, height: 100 }; },
    id: function () { return 'pane-img-1'; },
    toDataURL: function () { return 'data:image/png;base64,SOURCE'; },
    getLayer: function () { return { draw: function () {} }; },
  };
}

async function testOutpaintsReportsInsteadOfSayingNothing() {
  var host = _resetHost();
  UI.destroy();                       // outpaints dispatches with no popover left
  var pane = _mountPane();
  var Outpaints = require(path.resolve(__dirname, '..', 'capability-image-outpaints.js'));

  var events = [];
  host.addEventListener('capability-error', function (e) { events.push(e.detail); });

  // 1. A failure caught before the POST.
  Outpaints.attach({ hostEl: host, panel: pane });
  await Outpaints.handleDispatch({
    slot: 'image_outpaints',
    inputs: { prompt: 'extend the sky', directions: ['top'] },
  });
  record('outpaints surfaces a pre-request failure the user can read',
    /image_outpaints failed \[handler_failed\]/.test(_paneText(pane) || '')
      && /no image is currently mounted/i.test(_paneText(pane) || ''),
    'pane=' + JSON.stringify(_paneText(pane)));

  // 2. A failure that arrives from the server, long after dispatch.
  pane._errorBar.textContent = '';
  pane._errorBar.hidden = true;
  pane._backgroundImageNode = _stubImageNode();
  Outpaints.attach({
    hostEl: host,
    panel: pane,
    fetch: function () {
      return Promise.resolve({
        status: 503,
        json: function () {
          return Promise.resolve({
            error: { code: 'model_unavailable', message: 'Stability is unreachable.' },
          });
        },
      });
    },
  });
  await Outpaints.handleDispatch({
    slot: 'image_outpaints',
    inputs: { prompt: 'extend the sky', directions: ['top'] },
  });
  record('outpaints surfaces a post-request failure the user can read',
    /image_outpaints failed \[model_unavailable\]/.test(_paneText(pane) || '')
      && /Stability is unreachable/.test(_paneText(pane) || ''),
    'pane=' + JSON.stringify(_paneText(pane)));
  record('outpaints still emits capability-error for existing listeners',
    events.length === 2
      && events.every(function (d) { return d.slot === 'image_outpaints'; }),
    'events=' + JSON.stringify(events.map(function (d) { return d.code; })));

  Outpaints.detach();
  _unmountPane(pane);
}

// ── Run ──────────────────────────────────────────────────────────────────────

(async function main() {
  console.log('test-capability-invocation-ui (WP-7.3.1)');
  console.log('---------------------------------------');
  try {
    await testButtonDisabledWhenPromptMissing();
    await testButtonEnablesWhenPromptTyped();
    await testSubmitFiresDispatchEventAndShowsSpinner();
    await testPromptDispatchWaitsForPrivacyAndBindsChild();
    await testAllProviderTextFieldsWaitForPrivacy();
    await testErrorUxWithFixPath();
    await testRetryFixPath();
    await testAsyncBadge();
    await testImageRefAndMaskUseContext();
    await testEnumDirectionAndNumberWidgets();
    await testNumberWidgetClamps();
    await testRenderResultText();
    await testSetSlotSwitch();
    await testUnknownSlotThrows();
    await testDestroyCleansUp();
    await testErrorRendersInLivePopoverForItsOwnSlot();
    await testErrorRoutesToPaneWhenPopoverWasDestroyed();
    await testLateFailureCannotContaminateAnotherSlotsPopover();
    await testPopoverlessDispatchStillReachesTheUser();
    await testNoPopoverAndNoPaneWarnsRatherThanSwallows();
    await testPaneRetractionOnlyClearsThisLayersOwnMessage();
    await testPopoverlessSuccessRetractsThePreviousFailure();
    await testPaneWithNoErrorBarFallsThroughToTheConsole();
    await testSynchronousPreflightFailuresNameTheirSlot();
    await testEveryModuleNamesItsOwnSlotOnThePane();
    await testOutpaintsReportsInsteadOfSayingNothing();
  } catch (e) {
    console.error('Unexpected test error: ' + (e && e.stack || e));
    process.exit(2);
  }
  summarize();
})();
