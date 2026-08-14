#!/usr/bin/env node
/* test-v3-template-gallery.js — VI Phase 7 WP-7.10 (final piece)
 *
 * Behavioral tests for v3-template-gallery.js against jsdom + mocks of the
 * dependencies it pulls off window (OraCompositionTemplateLoader,
 * OraPackLoader, OraV3CanvasStateCodec, OraCanvasFileFormat, OraCanvas).
 *
 * The gallery is mostly DOM glue, so this harness mirrors the jsdom pattern
 * used by test-capability-invocation-ui.js rather than the mocked-Konva
 * pattern used by codec/panel-grid/bubble-tools.
 *
 * Run:
 *   node ~/ora/server/static/tests/test-v3-template-gallery.js
 *
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var path = require('path');

// ── jsdom bootstrap ─────────────────────────────────────────────────────────

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

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body></body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true }
);

var w = dom.window;
global.window = w;
global.document = w.document;
global.HTMLElement = w.HTMLElement;
global.Element = w.Element;
global.Event = w.Event;
global.CustomEvent = w.CustomEvent;
global.localStorage = w.localStorage;

// ── Module under test ───────────────────────────────────────────────────────
// Loading via require() executes the IIFE which attaches OraV3TemplateGallery
// to window. The IIFE also installs a document-level click handler and a
// document-level keydown handler — that one-time wiring is fine because we
// drive the real document throughout the suite.

var GALLERY_PATH = path.resolve(__dirname, '..', 'js', 'v3-template-gallery.js');
require(GALLERY_PATH);
var Gallery = w.OraV3TemplateGallery;
if (!Gallery) {
  console.error('error: OraV3TemplateGallery did not register on window');
  process.exit(2);
}

// ── Test harness ────────────────────────────────────────────────────────────

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

// ── Per-test fixture helpers ────────────────────────────────────────────────

function makePanelSpy() {
  var spy = {
    loadCalls: [],
    loadCanvasState: function (state) { spy.loadCalls.push(state); },
    setZoom: function () {},
  };
  return spy;
}

function setLoaders(opts) {
  // opts: { ctlList, packListInstalled, packListComposition, codecSerializer,
  //         canvasFileFormat }
  if (opts.ctlList === undefined) {
    delete w.OraCompositionTemplateLoader;
  } else {
    w.OraCompositionTemplateLoader = { list: function () { return opts.ctlList; } };
  }
  w.OraPackLoader = {
    listInstalled:           function () { return opts.packListInstalled || []; },
    listCompositionTemplates: function () { return opts.packListComposition || []; },
  };
  if (opts.codecSerializer) {
    w.OraV3CanvasStateCodec = {
      serializeFromPanel: opts.codecSerializer,
      _patchPanel: function () {},
    };
  } else {
    delete w.OraV3CanvasStateCodec;
  }
  w.OraCanvasFileFormat = opts.canvasFileFormat || {
    newCanvasState: function (o) { return { __blank: true, opts: o }; }
  };
}

function resetState() {
  // The module's _modalEls is memoised in closure scope, so we do NOT remove
  // the overlay from the DOM — that would orphan the cached reference and
  // future open() calls would render to a detached overlay. Calling close()
  // is enough; the next open() reuses the existing overlay and _renderModal
  // wipes modal.innerHTML before rebuilding.
  Gallery.close();
  global.localStorage.clear();
  delete w.OraCanvas;
}

// ── Tests ───────────────────────────────────────────────────────────────────

function testPublicApiSurface() {
  resetState();
  record('public API: open exists',
    typeof Gallery.open === 'function');
  record('public API: close exists',
    typeof Gallery.close === 'function');
  record('public API: _readUserTemplates exists',
    typeof Gallery._readUserTemplates === 'function');
  record('public API: _saveCurrentAsTemplate exists',
    typeof Gallery._saveCurrentAsTemplate === 'function');
  record('public API: _deleteUserTemplate exists',
    typeof Gallery._deleteUserTemplate === 'function');
}

function testOpenCreatesOverlay() {
  resetState();
  setLoaders({ ctlList: [], packListInstalled: [] });
  Gallery.open(makePanelSpy());
  var overlay = w.document.getElementById('ora-template-gallery-overlay');
  record('open() creates the overlay element',
    !!overlay,
    overlay ? 'present' : 'missing');
  record('open() shows overlay (display:flex)',
    overlay && overlay.style.display === 'flex',
    overlay ? ('display=' + overlay.style.display) : 'no overlay');
  record('open() sets aria-hidden=false',
    overlay && overlay.getAttribute('aria-hidden') === 'false');
  Gallery.close();
}

function testCloseHidesOverlay() {
  resetState();
  setLoaders({ ctlList: [], packListInstalled: [] });
  Gallery.open(makePanelSpy());
  Gallery.close();
  var overlay = w.document.getElementById('ora-template-gallery-overlay');
  record('close() hides overlay (display:none)',
    overlay && overlay.style.display === 'none',
    overlay ? ('display=' + overlay.style.display) : 'no overlay');
  record('close() sets aria-hidden=true',
    overlay && overlay.getAttribute('aria-hidden') === 'true');
}

function testOpenWithNoPanelDoesNotCrash() {
  resetState();
  setLoaders({ ctlList: [], packListInstalled: [] });
  // No window.OraCanvas, no panel argument — gallery should warn and return.
  var threw = false;
  var origWarn = console.warn;
  console.warn = function () {};
  try {
    Gallery.open();
  } catch (e) {
    threw = true;
  }
  console.warn = origWarn;
  record('open() with no panel does not throw',
    !threw,
    threw ? 'threw' : 'returned cleanly');
  var overlay = w.document.getElementById('ora-template-gallery-overlay');
  // Overlay was never created (we early-returned before _ensureModal).
  record('open() with no panel leaves no visible overlay',
    !overlay || overlay.style.display !== 'flex');
}

function testPackTemplateRendering() {
  resetState();
  setLoaders({
    ctlList: [
      { id: 'tpl-a', label: 'Template A', thumbnail: '<svg/>' },
      { id: 'tpl-b', title: 'Template B' },  // title fallback path
    ],
    packListInstalled: [
      { pack_id: 'p1', pack_name: 'Pack One', registered: { composition_templates: ['tpl-a'] } },
    ],
  });
  Gallery.open(makePanelSpy());
  var modal = w.document.getElementById('ora-template-gallery-modal');
  // Find the pack-section grid (first <section>'s grid div).
  var sections = modal.querySelectorAll('section');
  record('modal contains two sections (pack + user)',
    sections.length === 2,
    'sections=' + sections.length);
  var packGrid = sections[0].querySelector('div:not([style*="margin"])') || sections[0].lastElementChild;
  var packCards = sections[0].querySelectorAll('button');
  // Blank tile + 2 pack tiles = 3 buttons in pack section.
  record('pack section has Blank tile + N pack tiles (3 total)',
    packCards.length === 3,
    'count=' + packCards.length);
  // Verify a label-fallback case: 'Template B' came in via .title.
  var hasB = false;
  packCards.forEach(function (b) {
    if (/Template B/.test(b.textContent)) hasB = true;
  });
  record('pack template falls back from .label to .title',
    hasB);
  // Verify pack name resolution.
  var hasPackOne = false;
  packCards.forEach(function (b) {
    if (/Pack One/.test(b.textContent)) hasPackOne = true;
  });
  record('pack source label resolves via OraPackLoader.listInstalled',
    hasPackOne);
  Gallery.close();
}

function testPackLoaderFallback() {
  resetState();
  // No CompositionTemplateLoader — gallery falls through to PackLoader.
  setLoaders({
    ctlList: undefined,
    packListInstalled: [],
    packListComposition: [
      { id: 'fb-1', label: 'Fallback Template' },
    ],
  });
  Gallery.open(makePanelSpy());
  var modal = w.document.getElementById('ora-template-gallery-modal');
  var packCards = modal.querySelectorAll('section')[0].querySelectorAll('button');
  // Blank + 1 fallback template = 2.
  record('pack-loader fallback path renders templates when CTL absent',
    packCards.length === 2,
    'count=' + packCards.length);
  Gallery.close();
}

function testEmptyUserSectionShowsHint() {
  resetState();
  setLoaders({ ctlList: [], packListInstalled: [] });
  Gallery.open(makePanelSpy());
  var sections = w.document.getElementById('ora-template-gallery-modal').querySelectorAll('section');
  var userSection = sections[1];
  var hint = userSection.querySelector('p');
  record('empty user-templates section renders empty hint',
    hint && /No saved templates yet/.test(hint.textContent),
    hint ? hint.textContent.slice(0, 40) : 'no hint');
  // 1 button: the Save tile.
  record('empty user section has only the Save tile',
    userSection.querySelectorAll('button').length === 1);
  Gallery.close();
}

function testUserTemplatesRenderFromLocalStorage() {
  resetState();
  setLoaders({ ctlList: [], packListInstalled: [] });
  global.localStorage.setItem('ora.userTemplates', JSON.stringify([
    { id: 'u1', label: 'My Saved One', canvas_state: { __empty: true } },
    { id: 'u2', label: 'My Saved Two', canvas_state: { __empty: true } },
  ]));
  Gallery.open(makePanelSpy());
  var sections = w.document.getElementById('ora-template-gallery-modal').querySelectorAll('section');
  var userButtons = sections[1].querySelectorAll('button');
  // 2 user templates + 1 Save tile = 3.
  record('user section renders one card per stored template + Save tile',
    userButtons.length === 3,
    'count=' + userButtons.length);
  Gallery.close();
}

function testReadUserTemplatesEmpty() {
  resetState();
  global.localStorage.clear();
  var arr = Gallery._readUserTemplates();
  record('_readUserTemplates returns [] when storage empty',
    Array.isArray(arr) && arr.length === 0,
    'got=' + JSON.stringify(arr));
}

function testReadUserTemplatesMalformed() {
  resetState();
  global.localStorage.setItem('ora.userTemplates', '{not json');
  var origWarn = console.warn;
  console.warn = function () {};
  var arr = Gallery._readUserTemplates();
  console.warn = origWarn;
  record('_readUserTemplates returns [] on malformed JSON',
    Array.isArray(arr) && arr.length === 0);
}

function testReadUserTemplatesNonArray() {
  resetState();
  global.localStorage.setItem('ora.userTemplates', '{"not":"array"}');
  var arr = Gallery._readUserTemplates();
  record('_readUserTemplates returns [] when stored value is not an array',
    Array.isArray(arr) && arr.length === 0);
}

function testSaveCurrentWithCodec() {
  resetState();
  var serialized = null;
  setLoaders({
    ctlList: [],
    packListInstalled: [],
    codecSerializer: function (panel, opts) {
      serialized = { panel: panel, opts: opts };
      return { schema_version: '0.1', objects: [], __via: 'codec' };
    },
  });
  var panel = makePanelSpy();
  var entry = Gallery._saveCurrentAsTemplate(panel, 'Captured');
  record('_saveCurrentAsTemplate returns a saved entry when codec present',
    entry && entry.label === 'Captured' && entry.canvas_state.__via === 'codec',
    entry ? JSON.stringify(entry).slice(0, 80) : 'null');
  record('_saveCurrentAsTemplate calls the codec serializer with the panel',
    serialized && serialized.panel === panel && serialized.opts.title === 'Captured');
  // Verify it landed in localStorage.
  var stored = JSON.parse(global.localStorage.getItem('ora.userTemplates') || '[]');
  record('_saveCurrentAsTemplate persists entry to localStorage',
    stored.length === 1 && stored[0].label === 'Captured');
}

function testSaveCurrentFallbackWhenNoCodec() {
  resetState();
  setLoaders({ ctlList: [], packListInstalled: [] });
  var entry = Gallery._saveCurrentAsTemplate(makePanelSpy(), 'NoCodec');
  record('_saveCurrentAsTemplate uses fallback shape when codec absent',
    entry && entry.canvas_state && entry.canvas_state.format_id === 'ora-canvas',
    entry && entry.canvas_state ? entry.canvas_state.format_id : 'no entry');
  record('_saveCurrentAsTemplate fallback canvas_state has empty objects array',
    entry && Array.isArray(entry.canvas_state.objects) && entry.canvas_state.objects.length === 0);
}

function testSaveCurrentRejectsEmptyLabel() {
  resetState();
  setLoaders({ ctlList: [], packListInstalled: [] });
  var entry1 = Gallery._saveCurrentAsTemplate(makePanelSpy(), '');
  record('_saveCurrentAsTemplate returns null on empty label',
    entry1 === null,
    'got=' + entry1);
  var entry2 = Gallery._saveCurrentAsTemplate(null, 'X');
  record('_saveCurrentAsTemplate returns null when panel missing',
    entry2 === null);
}

function testDeleteUserTemplateRemoves() {
  resetState();
  global.localStorage.setItem('ora.userTemplates', JSON.stringify([
    { id: 'u1', label: 'A', canvas_state: {} },
    { id: 'u2', label: 'B', canvas_state: {} },
  ]));
  var ok = Gallery._deleteUserTemplate('u1');
  record('_deleteUserTemplate returns true on successful write',
    ok === true,
    'got=' + ok);
  var stored = JSON.parse(global.localStorage.getItem('ora.userTemplates'));
  record('_deleteUserTemplate removes the matching id',
    stored.length === 1 && stored[0].id === 'u2',
    JSON.stringify(stored));
}

function testDeleteUserTemplateNoMatchIsNoOp() {
  resetState();
  global.localStorage.setItem('ora.userTemplates', JSON.stringify([
    { id: 'u1', label: 'A', canvas_state: {} },
  ]));
  Gallery._deleteUserTemplate('u-doesnt-exist');
  var stored = JSON.parse(global.localStorage.getItem('ora.userTemplates'));
  record('_deleteUserTemplate is a no-op when id not found',
    stored.length === 1 && stored[0].id === 'u1');
}

function testApplyBlankCallsLoadCanvasState() {
  resetState();
  setLoaders({
    ctlList: [],
    packListInstalled: [],
    canvasFileFormat: {
      newCanvasState: function () { return { __blank: 'yes' }; }
    },
  });
  var panel = makePanelSpy();
  Gallery.open(panel);
  // Find the Blank tile (first button in pack section).
  var sections = w.document.getElementById('ora-template-gallery-modal').querySelectorAll('section');
  var blankBtn = sections[0].querySelectorAll('button')[0];
  blankBtn.click();
  record('clicking Blank tile calls panel.loadCanvasState',
    panel.loadCalls.length === 1 && panel.loadCalls[0].__blank === 'yes',
    'calls=' + panel.loadCalls.length);
  var overlay = w.document.getElementById('ora-template-gallery-overlay');
  record('clicking Blank tile closes the modal',
    overlay && overlay.style.display === 'none',
    overlay ? overlay.style.display : 'no overlay');
}

function testNewCanvasGuardRunsOnlyOnApply() {
  resetState();
  setLoaders({
    ctlList: [],
    packListInstalled: [],
    canvasFileFormat: {
      newCanvasState: function () { return { __blank: 'guarded' }; }
    },
  });
  var panel = makePanelSpy();
  var guardCalls = 0;
  panel._allowUserMutation = function () { guardCalls += 1; return false; };
  Gallery.open(panel);
  var overlay = w.document.getElementById('ora-template-gallery-overlay');
  var sections = w.document.getElementById('ora-template-gallery-modal').querySelectorAll('section');
  var blankBtn = sections[0].querySelectorAll('button')[0];
  record('opening New canvas does not consume the mutation guard',
    guardCalls === 0,
    'guardCalls=' + guardCalls);
  blankBtn.click();
  record('declining the apply-time guard preserves the canvas and open gallery',
    guardCalls === 1 && panel.loadCalls.length === 0 && overlay.style.display === 'flex',
    'guardCalls=' + guardCalls + ' loadCalls=' + panel.loadCalls.length
      + ' display=' + overlay.style.display);
  Gallery.close();
}

function testApplyPackTemplateCallsLoadCanvasState() {
  resetState();
  setLoaders({
    ctlList: [
      { id: 'p-tpl', label: 'P', canvas_state: { __pack: true } },
    ],
    packListInstalled: [],
  });
  var panel = makePanelSpy();
  Gallery.open(panel);
  var sections = w.document.getElementById('ora-template-gallery-modal').querySelectorAll('section');
  // [Blank, P] — second button is the pack template.
  var tplBtn = sections[0].querySelectorAll('button')[1];
  tplBtn.click();
  record('clicking pack template calls panel.loadCanvasState with template state',
    panel.loadCalls.length === 1 && panel.loadCalls[0].__pack === true,
    'calls=' + panel.loadCalls.length);
}

function testApplyPackTemplateSwallowsThrow() {
  resetState();
  setLoaders({
    ctlList: [{ id: 'p-tpl', label: 'P', canvas_state: { __pack: true } }],
    packListInstalled: [],
  });
  var panel = {
    loadCanvasState: function () { throw new Error('boom'); },
  };
  Gallery.open(panel);
  var sections = w.document.getElementById('ora-template-gallery-modal').querySelectorAll('section');
  var tplBtn = sections[0].querySelectorAll('button')[1];
  var origWarn = console.warn;
  var warned = false;
  console.warn = function () { warned = true; };
  var threw = false;
  try { tplBtn.click(); } catch (e) { threw = true; }
  console.warn = origWarn;
  record('pack-template apply does not propagate panel.loadCanvasState throws',
    !threw,
    threw ? 'propagated' : 'caught');
  record('pack-template apply logs a warning when load throws',
    warned);
}

function testApplyUserTemplateCallsLoadCanvasState() {
  resetState();
  setLoaders({ ctlList: [], packListInstalled: [] });
  global.localStorage.setItem('ora.userTemplates', JSON.stringify([
    { id: 'u1', label: 'Saved', canvas_state: { __user: true } },
  ]));
  var panel = makePanelSpy();
  Gallery.open(panel);
  var sections = w.document.getElementById('ora-template-gallery-modal').querySelectorAll('section');
  // First button in user section is the saved-card; second is the Save tile.
  var userBtn = sections[1].querySelectorAll('button')[0];
  userBtn.click();
  record('clicking user template calls panel.loadCanvasState with stored state',
    panel.loadCalls.length === 1 && panel.loadCalls[0].__user === true,
    'calls=' + panel.loadCalls.length);
}

function testDocumentClickDelegationOpensGallery() {
  resetState();
  setLoaders({ ctlList: [], packListInstalled: [] });
  // Provide a panel via OraCanvas so the document handler has something
  // to pass into open().
  w.OraCanvas = { panel: makePanelSpy() };
  // Build a button with the binding attribute.
  var btn = w.document.createElement('button');
  btn.dataset.binding = 'tool:new_canvas';
  w.document.body.appendChild(btn);
  btn.click();
  var overlay = w.document.getElementById('ora-template-gallery-overlay');
  record('document click on tool:new_canvas binding opens the gallery',
    overlay && overlay.style.display === 'flex',
    overlay ? overlay.style.display : 'no overlay');
  // Cleanup.
  w.document.body.removeChild(btn);
  Gallery.close();
}

function testDocumentClickDelegationFromNestedChild() {
  resetState();
  setLoaders({ ctlList: [], packListInstalled: [] });
  w.OraCanvas = { panel: makePanelSpy() };
  var btn = w.document.createElement('button');
  btn.dataset.binding = 'tool:new_canvas';
  var icon = w.document.createElement('span');
  btn.appendChild(icon);
  w.document.body.appendChild(btn);
  // Click bubbles up from icon → button → document; capture-phase listener
  // walks up parentElement chain and finds the binding.
  icon.click();
  var overlay = w.document.getElementById('ora-template-gallery-overlay');
  record('document click delegation walks up to find binding on ancestor',
    overlay && overlay.style.display === 'flex');
  w.document.body.removeChild(btn);
  Gallery.close();
}

function testDocumentClickIgnoresUnrelatedElements() {
  resetState();
  setLoaders({ ctlList: [], packListInstalled: [] });
  Gallery.close();
  var stray = w.document.createElement('button');
  stray.textContent = 'unrelated';
  w.document.body.appendChild(stray);
  stray.click();
  var overlay = w.document.getElementById('ora-template-gallery-overlay');
  // overlay either doesn't exist or is hidden — both are acceptable.
  var visible = overlay && overlay.style.display === 'flex';
  record('clicks on unrelated elements do not open the gallery',
    !visible);
  w.document.body.removeChild(stray);
}

function testEscapeKeyClosesOverlay() {
  resetState();
  setLoaders({ ctlList: [], packListInstalled: [] });
  Gallery.open(makePanelSpy());
  // Synthesize an Escape keydown on document.
  var ev = new w.KeyboardEvent('keydown', { key: 'Escape', bubbles: true });
  w.document.dispatchEvent(ev);
  var overlay = w.document.getElementById('ora-template-gallery-overlay');
  record('Escape key closes the overlay when visible',
    overlay && overlay.style.display === 'none',
    overlay ? overlay.style.display : 'no overlay');
}

function testBackdropClickClosesOverlay() {
  resetState();
  setLoaders({ ctlList: [], packListInstalled: [] });
  Gallery.open(makePanelSpy());
  var overlay = w.document.getElementById('ora-template-gallery-overlay');
  // Dispatch click whose target is the overlay itself (not the modal).
  var ev = new w.MouseEvent('click', { bubbles: true });
  overlay.dispatchEvent(ev);
  record('backdrop click closes overlay (target === overlay)',
    overlay.style.display === 'none',
    'display=' + overlay.style.display);
}

function testInsideModalClickDoesNotClose() {
  resetState();
  setLoaders({ ctlList: [], packListInstalled: [] });
  Gallery.open(makePanelSpy());
  var overlay = w.document.getElementById('ora-template-gallery-overlay');
  var modal = w.document.getElementById('ora-template-gallery-modal');
  // Click on a child of modal (not the overlay itself).
  var h2 = modal.querySelector('h2');
  var ev = new w.MouseEvent('click', { bubbles: true });
  h2.dispatchEvent(ev);
  record('click inside modal does not close overlay',
    overlay.style.display === 'flex',
    'display=' + overlay.style.display);
  Gallery.close();
}

function testCloseButtonClosesOverlay() {
  resetState();
  setLoaders({ ctlList: [], packListInstalled: [] });
  Gallery.open(makePanelSpy());
  var modal = w.document.getElementById('ora-template-gallery-modal');
  // The close X is the second child of the header (first is h2 title).
  var header = modal.firstElementChild;
  var closeBtn = header.querySelector('button');
  closeBtn.click();
  var overlay = w.document.getElementById('ora-template-gallery-overlay');
  record('header × button closes the overlay',
    overlay.style.display === 'none',
    'display=' + overlay.style.display);
}

// ── Run ─────────────────────────────────────────────────────────────────────

console.log('test-v3-template-gallery.js — VI Phase 7 §7.10 final piece');
console.log('');

testPublicApiSurface();
testOpenCreatesOverlay();
testCloseHidesOverlay();
testOpenWithNoPanelDoesNotCrash();
testPackTemplateRendering();
testPackLoaderFallback();
testEmptyUserSectionShowsHint();
testUserTemplatesRenderFromLocalStorage();
testReadUserTemplatesEmpty();
testReadUserTemplatesMalformed();
testReadUserTemplatesNonArray();
testSaveCurrentWithCodec();
testSaveCurrentFallbackWhenNoCodec();
testSaveCurrentRejectsEmptyLabel();
testDeleteUserTemplateRemoves();
testDeleteUserTemplateNoMatchIsNoOp();
testApplyBlankCallsLoadCanvasState();
testNewCanvasGuardRunsOnlyOnApply();
testApplyPackTemplateCallsLoadCanvasState();
testApplyPackTemplateSwallowsThrow();
testApplyUserTemplateCallsLoadCanvasState();
testDocumentClickDelegationOpensGallery();
testDocumentClickDelegationFromNestedChild();
testDocumentClickIgnoresUnrelatedElements();
testEscapeKeyClosesOverlay();
testBackdropClickClosesOverlay();
testInsideModalClickDoesNotClose();
testCloseButtonClosesOverlay();

summarize();
