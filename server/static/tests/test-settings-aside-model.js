#!/usr/bin/env node
/* General settings: dedicated Aside model selector + autosave coverage. */
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

  var passed = results.filter(function (r) { return r.ok; }).length;
  console.log('\n' + passed + ' / ' + results.length + ' tests passed');
  process.exit(passed === results.length ? 0 : 1);
}

run().catch(function (err) {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
