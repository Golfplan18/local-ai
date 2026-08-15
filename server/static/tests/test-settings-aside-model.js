#!/usr/bin/env node
/* Settings UI plus Models-pane local RAM allocation coverage. */
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

var dom = new jsdom.JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://localhost/',
  pretendToBeVisual: true,
  runScripts: 'outside-only',
});
var w = dom.window;
var saved = [];
var modelsAllocationAvailable = true;
var connectCalls = 0;
var popupOpenBeforePost = false;
var popupRequest = null;
var popupNavigation = null;

w.open = function (url, target) {
  popupOpenBeforePost = connectCalls === 0;
  popupRequest = { url: url, target: target };
  return {
    closed: false,
    document: { title: '' },
    location: {
      replace: function (next) { popupNavigation = next; },
    },
    close: function () { this.closed = true; },
    opener: w,
  };
};

w.fetch = function (url, opts) {
  if (url === '/api/settings' && (!opts || !opts.method)) {
    return Promise.resolve({ json: function () { return Promise.resolve({
      settings: {
        aside: { model_id: 'gemini/gemini-3.1-flash-lite' },
        interface: { tooltips_enabled: true, visual_help_enabled: false },
      },
      api_keys: [], provider_groups: [],
    }); } });
  }
  if (url === '/api/aside/models') {
    return Promise.resolve({ json: function () { return Promise.resolve({ models: [
      { id: 'gemini/gemini-3.1-flash-lite', display_name: 'Gemini 3.1 Flash Lite' },
      { id: 'local/fast', display_name: 'Local Fast' },
    ] }); } });
  }
  if (url === '/api/retrieval/config') {
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve({
      embedding_profile_id: '', reranker_id: 'off', profiles: [],
    }); } });
  }
  if (url === '/api/retrieval/rebuild/status') {
    return Promise.resolve({ json: function () { return Promise.resolve({ in_progress: false }); } });
  }
  if (url === '/api/settings/chatgpt-subscription' && (!opts || !opts.method)) {
    return Promise.resolve({ json: function () { return Promise.resolve({
      state: 'connecting', connected: false, configured: true,
      message: 'Complete ChatGPT sign-in in the browser.',
      catalog_revision: 0,
    }); } });
  }
  if (url === '/api/settings/chatgpt-subscription/connect'
      && opts && opts.method === 'POST') {
    connectCalls += 1;
    return Promise.resolve({ json: function () { return Promise.resolve({
      state: 'connecting', connected: false, configured: true,
      message: 'Complete ChatGPT sign-in in the browser.',
      catalog_revision: 0,
      auth_url: 'https://auth.openai.test/authorize',
    }); } });
  }
  if (url === '/api/settings' && opts && opts.method === 'POST') {
    var payload = JSON.parse(opts.body || '{}');
    saved.push(payload.updates || {});
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve({
      settings: Object.assign({
        aside: { model_id: 'local/fast' },
        interface: { tooltips_enabled: true, visual_help_enabled: false },
      }, payload.updates || {}),
    }); } });
  }
  if (url === '/api/model-registry?categories=all') {
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve({
      generated_at: new Date().toISOString(),
      models: {},
      reach_counts: {
        total: 0, reach_true: 0, reach_rate: 0, reach_false: 0,
        reach_null: 0, vendor_true: 0, vendor_false: 0, vendor_null: 0,
        newest_probed_at: null,
      },
    }); } });
  }
  if (url === '/api/model-registry/picks') {
    return Promise.resolve({ ok: true, json: function () {
      return Promise.resolve({ picks: [] });
    } });
  }
  if (url === '/api/configurations') {
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve({
      presets: {}, customs: [], active_name: 'active-test', active_toggles: {},
    }); } });
  }
  if (url === '/models') {
    if (!modelsAllocationAvailable) {
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({
        system_ram_gb: 100,
        automatic_target_gb: 80,
        hard_cap_gb: 85,
        active_profile_name: null,
        allocation_error: 'active Model Profile is missing',
        active_local_model_ids: [],
        allocated_local_ram_gb: 0,
        headroom_to_hard_cap_gb: 85,
        local_models: [
          { id: 'local-a', display_name: 'Local A', ram_gb: 30 },
          { id: 'local-b', display_name: 'Local B', ram_gb: 10 },
        ],
        commercial_models: [],
        local_discovery_error: null,
      }); } });
    }
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve({
      system_ram_gb: 100,
      automatic_target_gb: 80,
      hard_cap_gb: 85,
      active_local_model_ids: ['local-a'],
      allocated_local_ram_gb: 30,
      headroom_to_hard_cap_gb: 55,
      local_models: [
        { id: 'local-a', display_name: 'Local A', ram_gb: 30 },
        { id: 'local-b', display_name: 'Local B', ram_gb: 10 },
      ],
      commercial_models: [],
      local_discovery_error: null,
    }); } });
  }
  if (url === '/api/model-registry/reach/status') {
    return Promise.resolve({ ok: true, json: function () {
      return Promise.resolve({ in_progress: false, last_summary: {} });
    } });
  }
  if (url === '/api/configurations/active/toggles') {
    return Promise.resolve({ ok: true, json: function () {
      return Promise.resolve({ toggles: { adversarial_diversity: true } });
    } });
  }
  return Promise.reject(new Error('unexpected fetch: ' + url));
};
w.confirm = function () { return true; };
var context = dom.getInternalVMContext();
context.fetch = w.fetch;
context.confirm = w.confirm;
context.console = console;
vm.runInContext(
  fs.readFileSync(path.resolve(__dirname, '..', 'settings-panel.js'), 'utf8'),
  context,
  { filename: 'settings-panel.js' }
);

function wait(ms) {
  return new Promise(function (resolve) { w.setTimeout(resolve, ms || 0); });
}
var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? ' - ' + detail : ''));
}

async function run() {
  w.OraSettingsPanel.open({ tab: 'apis' });
  await wait(0);
  await wait(0);
  await wait(0);

  var subscriptionCard = w.document.querySelector('[data-chatgpt-subscription="true"]');
  var resume = Array.from(subscriptionCard.querySelectorAll('button')).find(function (button) {
    return button.textContent === 'Resume sign-in';
  });
  record('fresh connecting page offers Resume sign-in without a cached URL', !!resume);
  resume.click();
  record('Resume sign-in opens a popup synchronously before the guarded POST',
    popupOpenBeforePost && connectCalls === 1
      && popupRequest.url === 'about:blank' && popupRequest.target === '_blank');
  await wait(0);
  await wait(0);
  record('Resume sign-in reuses the pending login URL',
    popupNavigation === 'https://auth.openai.test/authorize', popupNavigation);

  w.OraSettingsPanel.open({ tab: 'general' });
  await wait(0);
  await wait(0);
  await wait(0);

  var section = w.document.querySelector('[data-settings-section="aside"]');
  var select = section && section.querySelector('select');
  record('General tab renders an Aside section', !!section);
  record('Aside model selector renders', !!select);
  record('dedicated Gemini default is selected',
    !!select && select.value === 'gemini/gemini-3.1-flash-lite',
    select && select.value);
  record('reachable models are listed',
    !!select && !!select.querySelector('option[value="local/fast"]'));
  record('only resolver-backed choices plus fallback are listed',
    !!select && select.options.length === 3,
    select && select.options.length);

  select.value = 'local/fast';
  select.dispatchEvent(new w.Event('change', { bubbles: true }));
  await wait(700);
  record('Aside choice autosaves independently',
    saved.length === 1
      && saved[0].aside
      && saved[0].aside.model_id === 'local/fast',
    JSON.stringify(saved));

  vm.runInContext(
    fs.readFileSync(path.resolve(__dirname, '..', 'models-pane.js'), 'utf8'),
    context,
    { filename: 'models-pane.js' }
  );
  var modelsHost = w.document.createElement('div');
  w.document.body.appendChild(modelsHost);
  w.OraModelsPane.init(modelsHost);
  await wait(0);
  await wait(0);
  await wait(0);

  var hardware = modelsHost.querySelector('[data-section="hardware"]');
  var hardwareText = hardware ? hardware.textContent.replace(/\s+/g, ' ').trim() : '';
  record('Local hardware renders the server allocation contract',
    hardwareText.indexOf('Automatic target (80%)80.0 GB') >= 0
      && hardwareText.indexOf('Hard maximum (85%)85.0 GB') >= 0
      && hardwareText.indexOf('Allocated to active profile30.0 GB') >= 0
      && hardwareText.indexOf('Headroom to hard maximum55.0 GB') >= 0,
    hardwareText);
  record('active local ids come from the backend whole-profile calculation',
    hardwareText.indexOf('Local AIN ACTIVE PROFILE30 GB') >= 0
      && hardwareText.indexOf('Local BIN ACTIVE PROFILE') < 0,
    hardwareText);
  record('hardware note distinguishes allocation from cache residency',
    hardwareText.indexOf('not a claim about current cache residency') >= 0
      && hardwareText.indexOf('Overhead') < 0
      && hardwareText.indexOf('Available') < 0,
    hardwareText);

  modelsAllocationAvailable = false;
  var adversarialToggle = modelsHost.querySelector(
    'input[data-toggle="adversarial_diversity"]'
  );
  adversarialToggle.checked = true;
  adversarialToggle.dispatchEvent(new w.Event('change', { bubbles: true }));
  await wait(0);
  await wait(0);
  await wait(0);
  hardwareText = hardware.textContent.replace(/\s+/g, ' ').trim();
  record('active refresh replaces stale allocation with explicit zero/error state',
    hardwareText.indexOf(
      'Active-profile allocation unavailable: active Model Profile is missing'
    ) >= 0
      && hardwareText.indexOf('Allocated to active profile0.0 GB') >= 0
      && hardwareText.indexOf('Headroom to hard maximum85.0 GB') >= 0
      && hardwareText.indexOf('IN ACTIVE PROFILE') < 0,
    hardwareText);
  w.OraModelsPane.destroy();

  var passed = results.filter(function (r) { return r.ok; }).length;
  console.log('\n' + passed + ' / ' + results.length + ' tests passed');
  process.exit(passed === results.length ? 0 : 1);
}

run().catch(function (err) {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
