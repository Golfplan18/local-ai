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
    slotName: 'image_edits',  // requires image + mask + prompt
    contextProvider: function () { return ctxState; },
  });
  var btn = host.querySelector('.ora-cap-runbtn');
  record('image_edits button starts disabled (no image, no mask)',
    btn && btn.disabled === true);
  var tooltip = host.querySelector('.ora-cap-tooltip');
  record('disabled tooltip mentions multiple missing inputs',
    tooltip && /Missing inputs/i.test(tooltip.textContent || ''),
    tooltip ? tooltip.textContent : 'no tooltip');

  // Provide a selection + mask via the context provider, refresh via setContextProvider
  ctxState.canvasSelection = { id: 'img_42', kind: 'image' };
  ctxState.maskRef = { kind: 'rect', x: 10, y: 10, w: 100, h: 100 };
  ctl.setContextProvider(function () { return ctxState; });
  // Type a prompt
  var promptInput = host.querySelector('textarea[name="prompt"], input[name="prompt"]');
  promptInput.value = 'Replace the masked area with a tree.';
  promptInput.dispatchEvent(new w.Event('input', { bubbles: true }));
  await _flushFrames();
  record('button enables after selection + mask + prompt',
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

// ── Run ──────────────────────────────────────────────────────────────────────

(async function main() {
  console.log('test-capability-invocation-ui (WP-7.3.1)');
  console.log('---------------------------------------');
  try {
    await testButtonDisabledWhenPromptMissing();
    await testButtonEnablesWhenPromptTyped();
    await testSubmitFiresDispatchEventAndShowsSpinner();
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
  } catch (e) {
    console.error('Unexpected test error: ' + (e && e.stack || e));
    process.exit(2);
  }
  summarize();
})();
