#!/usr/bin/env node
/* Focused jsdom tests for plugin-contributed Settings sections.
 *
 * Run:
 *   node ~/ora/server/static/tests/test-v3-settings-sections.js
 */

'use strict';

var fs = require('fs');
var path = require('path');
var vm = require('vm');

var COMPILER_TEST_NODE_MODULES = path.resolve(
  __dirname, '..', 'ora-visual-compiler', 'tests', 'node_modules'
);
var JSDOM_PATH = path.join(COMPILER_TEST_NODE_MODULES, 'jsdom');

var jsdom;
try {
  jsdom = require(JSDOM_PATH);
} catch (e) {
  console.error('error: jsdom not available at ' + JSDOM_PATH);
  process.exit(2);
}

var dom = new jsdom.JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://localhost/',
  pretendToBeVisual: true,
  runScripts: 'outside-only',
});
var w = dom.window;

// settings-panel.js only reaches the network through _fetchState. Every tab
// this file visits is fetch-free (the Visual / Output Styles panes degrade to
// a message when their pane script isn't loaded), so one stub is the whole
// surface — anything else is a surprise and should fail loudly.
//
// The first opens deliberately run against a dead backend: reservation, the
// tab strip and plugin sections all have to work before _settings exists, and
// that is the only window in which the "plugin page paints without Ora's own
// settings state" guarantee can be pinned at all.
var settingsFetchFails = true;
// open() calls _fetchState() AFTER painting the strip, so this counter is the
// direct evidence that a bad entry did not abort open() half-way through.
var settingsFetches = 0;

w.fetch = function (url, opts) {
  if (url === '/api/settings' && (!opts || !opts.method)) {
    settingsFetches++;
    if (settingsFetchFails) return Promise.reject(new Error('backend down'));
    return Promise.resolve({ json: function () { return Promise.resolve({
      settings: { interface: { tooltips_enabled: true } },
      api_keys: [], provider_groups: [],
    }); } });
  }
  return Promise.reject(new Error('unexpected fetch: ' + url));
};

var warnings = [];
var context = dom.getInternalVMContext();
context.fetch = w.fetch;
context.console = Object.assign({}, console, {
  warn: function () {
    warnings.push(Array.prototype.map.call(arguments, function (a) {
      return (a && a.message) ? String(a.message) : String(a);
    }).join(' '));
  },
});

// The Models tab renders through OraModelsPane, and degrades to a "not
// loaded" message when that script is absent. Stub it so the core-tab
// assertions here exercise the real branch: written against the degraded
// message, they would pass just as happily with core rendering broken.
var modelsPaneInits = 0;
context.OraModelsPane = {
  init: function (host) {
    modelsPaneInits++;
    var p = w.document.createElement('p');
    p.id = 'models-pane-content';
    p.textContent = 'Model Profiles';
    host.appendChild(p);
  },
};

var SECTIONS_FILE = path.resolve(__dirname, '..', 'js',
  'v3-settings-sections.js');
var PANEL_FILE = path.resolve(__dirname, '..', 'settings-panel.js');

function load(file) {
  vm.runInContext(
    fs.readFileSync(file, 'utf8'), context, { filename: path.basename(file) }
  );
}

load(SECTIONS_FILE);
load(PANEL_FILE);

var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? '  - ' + detail : ''));
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

function wait(ms) {
  return new Promise(function (resolve) { w.setTimeout(resolve, ms || 0); });
}
// _fetchState resolves through two promise hops before _renderTabContent runs.
function settle() {
  return wait(0).then(function () { return wait(0); })
    .then(function () { return wait(0); });
}

var S = w.OraSettingsSections;
var P = w.OraSettingsPanel;

function warnedAbout(re) {
  return warnings.some(function (m) { return re.test(m); });
}
function tabButtons() {
  return Array.prototype.slice.call(
    w.document.querySelectorAll('.ora-settings-tabs [data-tab]'));
}
function tabIds() {
  return tabButtons().map(function (b) { return b.dataset.tab; });
}
function stripOrder() {
  return Array.prototype.slice.call(
    w.document.querySelectorAll('.ora-settings-tabs > *')
  ).map(function (el) {
    return el.dataset && el.dataset.tab
      ? el.dataset.tab : '|' + el.textContent + '|';
  });
}
function clickTab(id) {
  var btn = w.document.querySelector('.ora-settings-tabs [data-tab="' + id + '"]');
  if (!btn) return false;
  btn.dispatchEvent(new w.Event('click'));
  return true;
}
function sectionEl(id) {
  return w.document.querySelector(
    '.ora-settings-tab-content [data-settings-section="' + id + '"]');
}
function sectionBody(id) {
  var sec = sectionEl(id);
  return sec ? sec.querySelector('.ora-settings-group-body').textContent : null;
}
function tabContentText() {
  var el = w.document.querySelector('.ora-settings-tab-content');
  return el ? el.textContent : '';
}
function pressEscape() {
  w.document.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Escape' }));
}
function coreTabsAllPainted() {
  var ids = tabIds();
  return CORE_IDS.every(function (id) { return ids.indexOf(id) >= 0; });
}

// An entry whose label reads fine for the first `n` reads and throws after.
// A lazily-computed label is an ordinary plugin shape and every paint re-reads
// it, so `n` picks which paint blows up: register() validates the entry (read
// 1), the tab strip paints it (read 2), the section title paints it (read 3).
function throwingLabel(entry, text, n) {
  var reads = 0;
  Object.defineProperty(entry, 'label', {
    enumerable: true,
    get: function () {
      reads++;
      if (reads > n) throw new Error('label getter exploded');
      return text;
    },
  });
  return entry;
}

// The group twin of throwingLabel, and the read points differ: group is read
// while an entry is ORDERED, not while it is painted. register() validates it
// (read 1), list() sorts it around the Advanced divider (read 2), and the
// panel resolves it again while ordering the strip (read 3, once per paint).
// `n` picks which read blows up, so the non-deterministic shape — a getter
// that survives its first read and throws on a later one — is expressible.
function throwingGroup(entry, value, n) {
  var reads = 0;
  Object.defineProperty(entry, 'group', {
    enumerable: true,
    get: function () {
      reads++;
      if (reads > n) throw new Error('group getter exploded');
      return value;
    },
  });
  return entry;
}

// A second, independent evaluation of the registry module bound to a fake
// global: what the panel sees when the same file is served under a second URL
// or a plugin bundles its own copy — an object it has never reserved into.
function freshRegistryCopy() {
  var make = vm.runInContext(
    '(function (window) {\n' + fs.readFileSync(SECTIONS_FILE, 'utf8')
      + '\nreturn window.OraSettingsSections; })',
    context, { filename: 'v3-settings-sections.js#copy' });
  return make({ console: context.console });
}

// A registry stand-in with a caller-chosen list() return value, for the
// "the registry answered with rubbish" paths.
function standInRegistry(listValue, entries) {
  return {
    reserveIds: function () { return 0; },
    list: function () { return listValue; },
    get: function (id) {
      var found = null;
      (entries || []).forEach(function (e) { if (e && e.id === id) found = e; });
      return found;
    },
    has: function (id) { return !!this.get(id); },
  };
}

var CORE_IDS = ['models', 'visual', 'styles', 'audio', 'general',
                'shortcuts', 'apis', 'projects'];
var ALIAS_IDS = ['transcription', 'speech', 'whisper',
                 'retrieval', 'aside', 'interface'];
var FAILED_TEXT = 'This section could not be displayed.';

async function run() {
  record('OraSettingsSections is exposed with the documented API',
    !!S && typeof S.register === 'function' && typeof S.unregister === 'function'
      && typeof S.has === 'function' && typeof S.get === 'function'
      && typeof S.list === 'function' && typeof S.reserveIds === 'function');

  // ---- built-ins win even when a plugin registers first (amendment 1) ------
  //
  // Nothing is reserved until the panel paints, so a plugin loaded ahead of
  // settings-panel.js can slip a core id in. The panel's first paint must take
  // it back rather than letting a plugin shadow a core tab.
  warnings.length = 0;
  S.register({ id: 'models', label: 'Sneaky Models', render: function () {} });
  record('a core id registered before the panel ever painted is accepted…',
    S.has('models') === true);

  P.open();
  await settle();

  record('…and evicted, loudly, the first time Settings paints',
    S.has('models') === false
      && warnedAbout(/section "models" collides with a core Settings tab id/),
    warnings.join(' | '));
  record('the core Models tab is the only Models tab in the strip',
    w.document.querySelectorAll('[data-tab="models"]').length === 1
      && w.document.querySelector('[data-tab="models"]').textContent === 'Models');

  // ---- a plugin page does not depend on Ora's own settings state ----------
  //
  // Still on the dead backend, and _settings has never been populated. A
  // plugin section reads nothing from it, so it must paint anyway: this is
  // the one moment the ordering can be pinned — a plugin branch sitting below
  // the core chain's `if (!_settings)` gate paints "Loading…" here instead.

  warnings.length = 0;
  var unregEarly = S.register({
    id: 'plugin-early', label: 'Early',
    render: function (body) { body.textContent = 'EARLY BODY'; },
  });
  P.open({ tab: 'plugin-early' });
  await settle();
  record('a plugin section paints when Ora’s own settings fetch fails',
    P.getState().activeTab === 'plugin-early'
      && !!sectionEl('plugin-early')
      && sectionBody('plugin-early') === 'EARLY BODY',
    tabContentText().slice(0, 60));
  record('the failed core fetch is still reported in the status line',
    w.document.querySelector('.ora-settings-status').textContent
      .indexOf('Couldn’t load settings') === 0,
    w.document.querySelector('.ora-settings-status').textContent);
  clickTab('general');
  record('a core tab is unchanged by that path — it still waits for state',
    P.getState().activeTab === 'general' && tabContentText() === 'Loading…',
    tabContentText().slice(0, 60));
  unregEarly();

  // Backend is back for the rest of the file.
  settingsFetchFails = false;
  P.open();
  await settle();

  // ---- reserved ids are refused outright afterwards -----------------------

  var refusedCore = CORE_IDS.every(function (id) {
    warnings.length = 0;
    S.register({ id: id, label: 'Hijack ' + id, render: function () {} });
    return !S.has(id) && warnedAbout(/is reserved by a core Settings tab/);
  });
  record('every core tab id is refused with a warning', refusedCore,
    CORE_IDS.join(','));

  var refusedAlias = ALIAS_IDS.every(function (id) {
    warnings.length = 0;
    S.register({ id: id, label: 'Hijack ' + id, render: function () {} });
    return !S.has(id) && warnedAbout(/is reserved by a core Settings tab/);
  });
  record('every legacy alias id is refused with a warning', refusedAlias,
    ALIAS_IDS.join(','));

  P.open();
  await settle();
  record('no refused id reached the tab strip',
    CORE_IDS.concat(ALIAS_IDS).every(function (id) {
      return w.document.querySelectorAll('[data-tab="' + id + '"]').length
        === (CORE_IDS.indexOf(id) >= 0 ? 1 : 0);
    }), tabIds().join(','));

  // ---- happy path ---------------------------------------------------------

  var painted = 0;
  var seenCtx = null;
  var unregNotes = S.register({
    id: 'plugin-notes',
    label: 'Notes',
    render: function (body, ctx) {
      painted++;
      seenCtx = ctx;
      var p = w.document.createElement('p');
      p.id = 'notes-plugin-content';
      p.textContent = 'Plugin owns this body.';
      body.appendChild(p);
    },
  });

  P.open();
  await settle();

  var notesTab = w.document.querySelector('[data-tab="plugin-notes"]');
  record('a registered section appears in the tab strip', !!notesTab,
    tabIds().join(','));
  record('the plugin tab uses the native tab class and label',
    !!notesTab && notesTab.className === 'ora-settings-tab'
      && notesTab.getAttribute('role') === 'tab'
      && notesTab.textContent === 'Notes',
    notesTab && notesTab.className);

  var order = stripOrder();
  record('a main-group section sits after the core main tabs and before Advanced',
    order.indexOf('plugin-notes') === order.indexOf('apis') + 1
      && order.indexOf('plugin-notes') < order.indexOf('|Advanced|')
      && order.indexOf('|Advanced|') < order.indexOf('projects'),
    order.join(','));

  record('registering does not paint anything on its own', painted === 0,
    'painted=' + painted);

  clickTab('plugin-notes');
  var sec = sectionEl('plugin-notes');
  record('clicking the tab renders the plugin content', painted === 1
    && !!w.document.getElementById('notes-plugin-content'),
    'painted=' + painted);
  record('content lands in native section chrome',
    !!sec && sec.className === 'ora-settings-group'
      && sec.parentNode.className === 'ora-settings-sections-grid'
      && sec.querySelector('.ora-settings-group-title').textContent === 'Notes'
      && sec.querySelector('.ora-settings-group-body #notes-plugin-content')
         !== null,
    sec && sec.className);
  record('the plugin tab is marked active like a core one',
    w.document.querySelector('[data-tab="plugin-notes"]')
      .classList.contains('ora-settings-tab--active')
      && P.getState().activeTab === 'plugin-notes');
  record('ctx carries the section id and a close handle, and nothing else',
    !!seenCtx && seenCtx.id === 'plugin-notes'
      && typeof seenCtx.close === 'function'
      && Object.keys(seenCtx).sort().join(',') === 'close,id',
    seenCtx && Object.keys(seenCtx).join(','));

  // ---- open({tab}) is validated, and a plugin deep link really paints -----
  //
  // Asserting only that getState().activeTab equals what was just passed in
  // proves nothing: a validator that accepts everything satisfies it. Pin
  // both halves — an unknown id is refused, and a known plugin id paints.

  P.open({ tab: 'general' });
  await settle();
  P.open({ tab: 'no-such-tab-anywhere' });
  await settle();
  record('an unknown tab id is refused and the active tab is left alone',
    P.getState().activeTab === 'general'
      && tabIds().indexOf('no-such-tab-anywhere') < 0,
    P.getState().activeTab);

  painted = 0;
  P.open({ tab: 'plugin-notes' });
  await settle();
  record('open({tab: <plugin id>}) lands on the section AND paints it',
    P.getState().activeTab === 'plugin-notes' && painted === 1
      && !!sectionEl('plugin-notes')
      && !!w.document.getElementById('notes-plugin-content'),
    'painted=' + painted + ' activeTab=' + P.getState().activeTab);

  // ---- group: 'advanced' --------------------------------------------------

  var unregLab = S.register({
    id: 'plugin-lab', label: 'Lab', group: 'advanced',
    render: function (body) { body.textContent = 'lab'; },
  });
  P.open();
  await settle();
  order = stripOrder();
  record('group "advanced" places the section after the Advanced divider',
    order.indexOf('|Advanced|') < order.indexOf('plugin-lab')
      && order.indexOf('plugin-lab') === order.indexOf('projects') + 1,
    order.join(','));
  record('there is still exactly one Advanced divider',
    w.document.querySelectorAll('.ora-settings-tab-divider').length === 1);
  record('list() returns main-group entries before advanced ones',
    S.list().map(function (e) { return e.id; }).join(',')
      === 'plugin-notes,plugin-lab',
    S.list().map(function (e) { return e.id; }).join(','));

  // ---- amendment 2: registered late, and the active tab survives ----------

  P.open({ tab: 'visual' });
  await settle();
  var unregLate = S.register({
    id: 'plugin-late', label: 'Late',
    render: function (body) { body.textContent = 'late'; },
  });
  record('a late registration is not in the strip until Settings repaints',
    !w.document.querySelector('[data-tab="plugin-late"]'));

  P.open();
  await settle();
  record('a section registered after first boot appears on the next open',
    !!w.document.querySelector('[data-tab="plugin-late"]'), tabIds().join(','));
  record('re-rendering the strip preserves the active tab',
    P.getState().activeTab === 'visual'
      && w.document.querySelector('[data-tab="visual"]')
         .classList.contains('ora-settings-tab--active'),
    P.getState().activeTab);

  clickTab('plugin-late');
  P.open();
  await settle();
  record('an active plugin tab also survives a repaint',
    P.getState().activeTab === 'plugin-late'
      && w.document.querySelector('[data-tab="plugin-late"]')
         .classList.contains('ora-settings-tab--active'),
    P.getState().activeTab);

  // ---- removal ------------------------------------------------------------

  warnings.length = 0;
  record('unregister returns true and drops the entry', unregLate() === true
    && S.has('plugin-late') === false);

  P.open();
  await settle();
  record('the removed tab and its content are gone, with a fallback warning',
    !w.document.querySelector('[data-tab="plugin-late"]')
      && !sectionEl('plugin-late')
      && P.getState().activeTab === 'models'
      && warnedAbout(/tab "plugin-late" is no longer registered/),
    warnings.join(' | '));
  record('unregister on an unknown id returns false',
    S.unregister('never-existed') === false);
  record('the unregister handle does nothing on a second call',
    unregLate() === false);

  // A handle is bound to ITS entry, not to the id: after the id has been
  // re-registered by someone else, a stale handle must not evict the live
  // section standing in its place.
  var unregDupA = S.register({
    id: 'plugin-dup', label: 'First',
    render: function (body) { body.textContent = 'first'; },
  });
  unregDupA();
  var unregDupB = S.register({
    id: 'plugin-dup', label: 'Second',
    render: function (body) { body.textContent = 'second'; },
  });
  var staleResult = unregDupA();
  record('a stale handle does not remove the live section holding its id',
    staleResult === false && S.has('plugin-dup') === true
      && S.get('plugin-dup').label === 'Second',
    'stale returned ' + staleResult);
  P.open();
  await settle();
  clickTab('plugin-dup');
  record('…and that live section still paints', sectionBody('plugin-dup') === 'second',
    sectionBody('plugin-dup'));
  record('unregister(id) still removes whatever holds the id now',
    unregDupB() === true && S.has('plugin-dup') === false);

  // ---- a section that vanishes between the open and the paint -------------
  //
  // The strip is painted synchronously in open(); the content waits on
  // /api/settings. A section unregistered in that window is resolvable when
  // the strip paints and gone when the content does, so the content path
  // needs its own fallback — without it the modal body is simply empty.

  warnings.length = 0;
  var unregVanish = S.register({
    id: 'plugin-vanish', label: 'Vanish',
    render: function (body) { body.textContent = 'vanish'; },
  });
  P.open({ tab: 'plugin-vanish' });
  unregVanish();
  await settle();
  record('a section unregistered mid-open falls back on the content path too',
    P.getState().activeTab === 'models'
      && !!w.document.getElementById('models-pane-content')
      && warnedAbout(/tab "plugin-vanish" is no longer registered/),
    P.getState().activeTab + ' | ' + tabContentText().slice(0, 60));

  // ---- fail-open paths ----------------------------------------------------

  warnings.length = 0;
  var dupe = S.register({ id: 'plugin-notes', label: 'Clash',
    render: function () {} });
  P.open();
  await settle();
  record('duplicate id is rejected with a warning and does not double the tab',
    warnedAbout(/already registered/) && dupe() === false
      && w.document.querySelectorAll('[data-tab="plugin-notes"]').length === 1
      && S.get('plugin-notes').label === 'Notes',
    warnings.join(' | '));

  warnings.length = 0;
  S.register({ id: 'no-label', render: function () {} });
  record('missing label is rejected', !S.has('no-label')
    && warnedAbout(/entry\.label is required/), warnings.join(' | '));

  warnings.length = 0;
  S.register({ id: 'no-render', label: 'No render' });
  record('missing render is rejected', !S.has('no-render')
    && warnedAbout(/entry\.render must be a function/), warnings.join(' | '));

  warnings.length = 0;
  S.register({ id: 'bad-render', label: 'Bad render', render: 'nope' });
  record('a non-function render is rejected', !S.has('bad-render')
    && warnedAbout(/entry\.render must be a function/), warnings.join(' | '));

  warnings.length = 0;
  S.register({ label: 'No id', render: function () {} });
  record('missing id is rejected', warnedAbout(/entry\.id is required/),
    warnings.join(' | '));

  warnings.length = 0;
  S.register({ id: 'bad-group', label: 'Bad group', group: 'placement',
    render: function () {} });
  record('an unknown group value is rejected',
    !S.has('bad-group') && warnedAbout(/unknown group "placement"/),
    warnings.join(' | '));

  P.open();
  await settle();
  record('no rejected entry ever reached the tab strip',
    ['no-label', 'no-render', 'bad-render', 'bad-group'].every(function (id) {
      return !w.document.querySelector('[data-tab="' + id + '"]');
    }), tabIds().join(','));

  // ---- a throwing render is contained ------------------------------------

  warnings.length = 0;
  var unregThrower = S.register({
    id: 'plugin-thrower', label: 'Thrower',
    render: function () { throw new Error('plugin bug'); },
  });
  P.open();
  await settle();
  clickTab('plugin-thrower');
  var thrown = sectionEl('plugin-thrower');
  record('a throwing render warns and leaves a readable message',
    warnedAbout(/plugin section "plugin-thrower" failed to render/)
      && warnedAbout(/plugin bug/)
      && !!thrown
      && sectionBody('plugin-thrower') === FAILED_TEXT,
    warnings.join(' | '));
  record('the modal survives a throwing render',
    P.getState().open === true && tabIds().length > 0);

  modelsPaneInits = 0;
  clickTab('models');
  record('a core tab still renders after a plugin render threw',
    P.getState().activeTab === 'models' && modelsPaneInits === 1
      && !!w.document.querySelector('.ora-settings-models-host')
      && !!w.document.getElementById('models-pane-content'),
    tabContentText().slice(0, 60));

  clickTab('plugin-notes');
  record('another plugin tab still renders after a sibling threw',
    !!sectionEl('plugin-notes')
      && !!w.document.getElementById('notes-plugin-content'));
  unregThrower();

  // ---- an async render is contained too -----------------------------------
  //
  // A section that loads its own data returns a promise. A rejection nobody
  // catches is an unhandled rejection in the browser and kills the process
  // outright in Node, so the panel has to attach a handler.

  warnings.length = 0;
  var unregAsyncBad = S.register({
    id: 'plugin-async-bad', label: 'Async bad',
    render: function () { return Promise.reject(new Error('async plugin bug')); },
  });
  P.open({ tab: 'plugin-async-bad' });
  await settle();
  await settle();
  record('a rejected async render warns and leaves the same message',
    warnedAbout(/plugin section "plugin-async-bad" failed to render/)
      && warnedAbout(/async plugin bug/)
      && sectionBody('plugin-async-bad') === FAILED_TEXT,
    warnings.join(' | '));

  var unregAsyncOk = S.register({
    id: 'plugin-async-ok', label: 'Async ok',
    render: function (body) {
      return Promise.resolve().then(function () {
        body.textContent = 'LOADED LATE';
      });
    },
  });
  warnings.length = 0;
  P.open({ tab: 'plugin-async-ok' });
  await settle();
  await settle();
  record('a resolving async render paints late and warns about nothing',
    sectionBody('plugin-async-ok') === 'LOADED LATE'
      && !warnedAbout(/failed to render/),
    warnings.join(' | '));
  unregAsyncBad();
  unregAsyncOk();

  // ---- a throwing label is contained, in the strip and in the section -----

  warnings.length = 0;
  var unregStripBoom = S.register(throwingLabel(
    { id: 'plugin-strip-boom', render: function () {} }, 'Strip boom', 1));
  P.open();
  await settle();
  record('a label that throws while the strip paints skips only that tab',
    coreTabsAllPainted()
      && tabIds().indexOf('plugin-strip-boom') < 0
      && tabIds().indexOf('plugin-notes') >= 0
      && warnedAbout(/tab entry could not be painted/),
    tabIds().join(','));
  record('…and the modal is still usable: Escape closes it',
    (function () { pressEscape(); return P.getState().open === false; })());
  unregStripBoom();

  warnings.length = 0;
  var unregTitleBoom = S.register(throwingLabel(
    { id: 'plugin-title-boom', render: function (b) { b.textContent = 'x'; } },
    'Title boom', 2));
  P.open({ tab: 'plugin-title-boom' });
  await settle();
  record('a label that throws while the section title paints is contained',
    warnedAbout(/plugin section "plugin-title-boom" failed to render/)
      && !!sectionEl('plugin-title-boom')
      && sectionBody('plugin-title-boom') === FAILED_TEXT
      && P.getState().open === true,
    warnings.join(' | '));
  modelsPaneInits = 0;
  clickTab('models');
  record('a core tab still renders after a section title threw',
    P.getState().activeTab === 'models' && modelsPaneInits === 1
      && !!w.document.getElementById('models-pane-content'));
  unregTitleBoom();

  // ---- a throwing group is contained on the ORDERING path too -------------
  //
  // group is read one function up from the per-entry paint guard, while the
  // strip is being ordered. Unguarded, a throwing getter escaped _renderTabs
  // → open() after _tabsEl had already been emptied: an empty strip, no
  // warning, no /api/settings fetch, and — because open() installs the keydown
  // handler only after the paint returns — a modal Escape could not close.
  // Every one of those consequences is pinned here.

  var fetchesBefore = settingsFetches;
  warnings.length = 0;
  var unregGroupBoom = S.register(throwingGroup(
    { id: 'plugin-group-boom', label: 'Group boom', render: function () {} },
    'advanced', 2));
  P.open();
  await settle();
  order = stripOrder();
  record('a group that throws while the strip is ordered skips only that tab',
    coreTabsAllPainted()
      && tabIds().indexOf('plugin-group-boom') < 0
      && tabIds().indexOf('plugin-notes') >= 0
      && tabIds().indexOf('plugin-lab') >= 0
      && warnedAbout(/tab entry could not be ordered/),
    tabIds().join(',') + ' | ' + warnings.join(' | '));
  record('…the one Advanced divider is still there and still in the right place',
    w.document.querySelectorAll('.ora-settings-tab-divider').length === 1
      && order.indexOf('|Advanced|') === order.indexOf('plugin-notes') + 1
      && order.indexOf('projects') === order.indexOf('|Advanced|') + 1
      && order.indexOf('plugin-lab') === order.indexOf('projects') + 1,
    order.join(','));
  record('…open() got past the strip, so _fetchState still ran',
    settingsFetches === fetchesBefore + 1,
    'fetches ' + fetchesBefore + ' → ' + settingsFetches);
  record('…and Escape still closes the modal, so the keydown handler landed',
    (function () { pressEscape(); return P.getState().open === false; })());
  unregGroupBoom();

  // The same getter, one read earlier: it validates cleanly at register time
  // and throws on the read list() makes. The registry has to drop that one
  // entry rather than let the throw escape list() — where the panel's guard
  // would catch it, but only by discarding every OTHER plugin's section too.

  fetchesBefore = settingsFetches;
  warnings.length = 0;
  var unregGroupLate = S.register(throwingGroup(
    { id: 'plugin-group-late', label: 'Group late', render: function () {} },
    'advanced', 1));
  var listedLate = S.list().map(function (e) { return e.id; });
  P.open();
  await settle();
  record('a group getter that throws on a LATER read costs only its own entry',
    listedLate.indexOf('plugin-group-late') < 0
      && listedLate.indexOf('plugin-notes') >= 0
      && listedLate.indexOf('plugin-lab') >= 0
      && coreTabsAllPainted()
      && tabIds().indexOf('plugin-group-late') < 0
      && tabIds().indexOf('plugin-notes') >= 0
      && tabIds().indexOf('plugin-lab') >= 0
      && warnedAbout(/left out of list\(\)/)
      && settingsFetches === fetchesBefore + 1,
    listedLate.join(',') + ' || ' + tabIds().join(','));
  record('…and that modal is usable too',
    (function () { pressEscape(); return P.getState().open === false; })());
  unregGroupLate();

  // The foreign-registry route: an object the panel never validated anything
  // into, handing back an entry whose group throws on the very first read.

  P.open({ tab: 'models' });
  await settle();
  var foreignBoom = throwingGroup(
    { id: 'foreign-group-boom', label: 'Foreign boom', render: function () {} },
    'advanced', 0);
  var foreignGood = { id: 'foreign-good', label: 'Foreign good',
    render: function (body) { body.textContent = 'FOREIGN BODY'; } };
  w.OraSettingsSections = standInRegistry([foreignBoom, foreignGood],
    [foreignGood]);
  fetchesBefore = settingsFetches;
  warnings.length = 0;
  P.open();
  await settle();
  clickTab('foreign-good');
  record('a foreign registry entry whose group throws is dropped, not fatal',
    coreTabsAllPainted()
      && tabIds().indexOf('foreign-group-boom') < 0
      && tabIds().indexOf('foreign-good') >= 0
      && sectionBody('foreign-good') === 'FOREIGN BODY'
      && warnedAbout(/tab entry could not be ordered/)
      && settingsFetches === fetchesBefore + 1,
    tabIds().join(',') + ' | ' + warnings.join(' | '));
  record('…and Escape still closes that one as well',
    (function () { pressEscape(); return P.getState().open === false; })());

  // The other half of the rule: read once, not merely guarded. entry.id was
  // read twice while a section painted — once for the section chrome, once for
  // the ctx handed to render() — so a getter that answers differently on
  // successive reads told the plugin it was painting a section other than the
  // body it was actually given.

  var shiftyReads = 0;
  var shiftyCtxId = null;
  var shiftyEntry = {
    label: 'Shifty',
    render: function (body, ctx) {
      shiftyCtxId = ctx.id;
      body.textContent = 'SHIFTY BODY';
    },
  };
  Object.defineProperty(shiftyEntry, 'id', {
    enumerable: true,
    get: function () { shiftyReads++; return 'plugin-shifty-' + shiftyReads; },
  });
  // get() answers with the entry whatever id it is asked for, so resolution
  // survives the moving id and the paint path is the only thing under test.
  w.OraSettingsSections = {
    reserveIds: function () { return 0; },
    list: function () { return [shiftyEntry]; },
    get: function () { return shiftyEntry; },
    has: function () { return true; },
  };
  warnings.length = 0;
  P.open();
  await settle();
  var shiftyTab = w.document.querySelector(
    '.ora-settings-tabs [data-tab^="plugin-shifty-"]');
  if (shiftyTab) shiftyTab.dispatchEvent(new w.Event('click'));
  var shiftySec = w.document.querySelector(
    '.ora-settings-tab-content [data-settings-section^="plugin-shifty-"]');
  record('a section is painted from one read of entry.id, not two',
    !!shiftySec && !!shiftyCtxId
      && shiftySec.dataset.settingsSection === shiftyCtxId,
    (shiftySec && shiftySec.dataset.settingsSection) + ' vs ctx ' + shiftyCtxId);

  w.OraSettingsSections = S;

  // register() itself: reading a field IS plugin code, so a getter that throws
  // during validation is a rejected registration — never an exception thrown
  // back into whatever the registering plugin was in the middle of doing.

  warnings.length = 0;
  var registerThrew = null;
  var groupRejectHandle = null;
  try {
    groupRejectHandle = S.register(throwingGroup(
      { id: 'plugin-group-reject', label: 'Group reject',
        render: function () {} }, 'advanced', 0));
  } catch (err) {
    registerThrew = err;
  }
  record('register() with a group getter that throws does not throw',
    registerThrew === null,
    registerThrew && (registerThrew.message || String(registerThrew)));
  record('…it warns and hands back a working no-op handle',
    typeof groupRejectHandle === 'function'
      && groupRejectHandle() === false
      && S.has('plugin-group-reject') === false
      && warnedAbout(/register rejected: a field on the entry could not be read/),
    warnings.join(' | '));

  P.open({ tab: 'models' });
  await settle();
  record('…and the strip never saw it',
    tabIds().indexOf('plugin-group-reject') < 0, tabIds().join(','));

  // ---- ids that live on Object.prototype ---------------------------------

  var unregCtor = S.register({
    id: 'constructor', label: 'Ctor',
    render: function (body) { body.textContent = 'CTOR BODY'; },
  });
  record('the registry accepts an id that names an Object.prototype member',
    S.has('constructor') === true);
  P.open({ tab: 'general' });
  await settle();
  P.open({ tab: 'constructor' });
  await settle();
  record('open({tab}) resolves aliases by own property, so that id deep-links',
    P.getState().activeTab === 'constructor'
      && sectionBody('constructor') === 'CTOR BODY',
    P.getState().activeTab);
  P.open({ tab: 'general' });
  await settle();
  P.open({ tab: 'toString' });
  await settle();
  record('an inherited key that nothing registered leaves the active tab alone',
    P.getState().activeTab === 'general', P.getState().activeTab);
  unregCtor();

  // ---- the module is only allowed to install itself once ------------------

  var firstInstance = w.OraSettingsSections;
  var keptCount = S.list().length;
  load(SECTIONS_FILE);
  record('a second evaluation keeps the first registry and its sections',
    w.OraSettingsSections === firstInstance
      && S.list().length === keptCount
      && S.has('plugin-notes') === true,
    'sections=' + S.list().map(function (e) { return e.id; }).join(','));

  // ---- a replaced registry is re-reserved ---------------------------------
  //
  // Same file under a second URL, or a plugin with its own copy: the global
  // becomes an object the panel has never reserved into. Its reserved list is
  // empty, so it accepts core ids — and a latch that only remembers "we
  // reserved once" lets those become duplicate core tabs, silently.

  P.open({ tab: 'models' });
  await settle();
  var copyB = freshRegistryCopy();
  copyB.register({ id: 'models', label: 'Sneaky Models',
    render: function () {} });
  copyB.register({ id: 'general', label: 'Sneaky General',
    render: function () {} });
  w.OraSettingsSections = copyB;
  warnings.length = 0;
  P.open();
  await settle();
  var ids = tabIds();
  function countTab(id) {
    return ids.filter(function (x) { return x === id; }).length;
  }
  record('a replaced registry is reserved again, so core tabs stay unique',
    countTab('models') === 1 && countTab('general') === 1
      && copyB.has('models') === false && copyB.has('general') === false
      && warnedAbout(/collides with a core Settings tab id/),
    ids.join(','));

  // ---- a registry that throws or answers with rubbish ---------------------

  var copyC = freshRegistryCopy();
  var realReserve = copyC.reserveIds;
  var reserveThrewOnce = false;
  copyC.reserveIds = function (idList) {
    if (!reserveThrewOnce) {
      reserveThrewOnce = true;
      throw new Error('reserveIds exploded');
    }
    return realReserve.call(copyC, idList);
  };
  w.OraSettingsSections = copyC;
  warnings.length = 0;
  P.open();
  await settle();
  record('a throwing reserveIds cannot stop the modal opening',
    P.getState().open === true && coreTabsAllPainted()
      && warnedAbout(/failed to reserve/),
    tabIds().join(','));
  record('…and Escape still closes it, so the keydown handler was installed',
    (function () { pressEscape(); return P.getState().open === false; })());

  copyC.register({ id: 'general', label: 'Sneaky General',
    render: function () {} });
  warnings.length = 0;
  P.open();
  await settle();
  record('a failed reservation is retried rather than latched away',
    copyC.has('general') === false
      && tabIds().filter(function (x) { return x === 'general'; }).length === 1
      && warnedAbout(/collides with a core Settings tab id/),
    tabIds().join(','));

  w.OraSettingsSections = standInRegistry('not an array', []);
  warnings.length = 0;
  P.open();
  await settle();
  record('a list() that is not an array is ignored, loudly',
    P.getState().open === true && coreTabsAllPainted()
      && warnedAbout(/list\(\) did not return an array/),
    tabIds().join(','));

  var goodEntry = { id: 'good-section', label: 'Good',
    render: function (body) { body.textContent = 'GOOD BODY'; } };
  w.OraSettingsSections = standInRegistry([null, 5, goodEntry], [goodEntry]);
  warnings.length = 0;
  P.open();
  await settle();
  clickTab('good-section');
  record('non-object entries are dropped and the rest of the list still paints',
    coreTabsAllPainted() && tabIds().indexOf('good-section') >= 0
      && sectionBody('good-section') === 'GOOD BODY'
      && warnedAbout(/are not objects/),
    tabIds().join(','));

  // ---- no registry at all: Settings behaves exactly as before -------------

  // Land on a core tab first: the block above left a (now removed) plugin
  // section selected, and falling back from it is a different test's subject.
  P.open({ tab: 'models' });
  await settle();
  delete w.OraSettingsSections;
  warnings.length = 0;
  modelsPaneInits = 0;
  P.open();
  await settle();
  record('with no registry present at all, only core tabs paint',
    tabIds().join(',') === CORE_IDS.join(',')
      && P.getState().activeTab === 'models'
      && modelsPaneInits === 1
      && !!w.document.getElementById('models-pane-content'),
    tabIds().join(','));
  record('…and nothing was warned about', warnings.length === 0,
    warnings.join(' | '));
  P.open({ tab: 'shortcuts' });
  await settle();
  record('…and a core deep link still works without a registry',
    P.getState().activeTab === 'shortcuts', P.getState().activeTab);

  w.OraSettingsSections = S;

  unregNotes();
  unregLab();
  P.open();
  await settle();
  record('with every plugin section gone, the strip is core-only again',
    tabIds().join(',') === CORE_IDS.join(','), tabIds().join(','));
  summarize();
}

run().catch(function (err) {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
