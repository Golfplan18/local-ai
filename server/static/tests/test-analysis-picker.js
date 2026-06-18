#!/usr/bin/env node
/* test-analysis-picker.js
 *
 * Focused jsdom coverage for the V3 Analyses picker and input state:
 *   - opens from the toolbar event
 *   - starts on the grouped territory overview
 *   - drills into a territory
 *   - searches globally
 *   - commits the selected analysis mode into OraInputState
 *   - offers mode-scoped lenses as the second pass
 *
 * Run:
 *   node ~/ora/server/static/tests/test-analysis-picker.js
 */

'use strict';

var path = require('path');

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

var modes = [
  {
    id: 'factual-lookup',
    display_name: 'Factual Lookup',
    display_description: 'look up a fact',
    educational_name: 'fact lookup',
    territory: 'T0',
    territory_name: 'Default & General',
    territory_order: 0,
    aliases: ['fact'],
  },
  {
    id: 'boundary-critique',
    display_name: 'Boundary Critique',
    display_description: 'I think the framing of this leaves people out',
    educational_name: 'boundary critique',
    territory: 'T2',
    territory_name: 'Interest & Power',
    territory_order: 2,
    aliases: ['power'],
  },
  {
    id: 'cui-bono',
    display_name: 'Cui Bono',
    display_description: "trying to understand who's behind this",
    educational_name: 'who benefits analysis',
    territory: 'T2',
    territory_name: 'Interest & Power',
    territory_order: 2,
    aliases: ['cui bono', 'who benefits'],
    lenses: [
      {
        id: 'ulrich-csh-boundary-categories',
        display_name: 'Ulrich CSH Boundary Categories',
        display_description: 'clarifies stakeholders and boundary judgments',
        category: 'optional',
      },
      {
        id: 'public-choice-theory',
        display_name: 'Public Choice Theory',
        display_description: 'looks for institutional incentives',
        category: 'foundational',
      },
      {
        id: 'principal-agent-problem',
        display_name: 'Principal-Agent Problem',
        display_description: 'checks delegated incentive conflict',
        category: 'related',
      },
    ],
  },
  {
    id: 'causal-dag',
    display_name: 'Causal DAG',
    display_description: 'map causes',
    educational_name: 'causal graph',
    territory: 'T4',
    territory_name: 'Causal Investigation',
    territory_order: 4,
    aliases: ['causal'],
  },
];

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body>' +
  '<button id="inputToolbarAnalysis" type="button">Analyses</button>' +
  '<div id="analysisPicker" hidden>' +
  '  <input id="analysisPickerSearch" type="text">' +
  '  <div id="analysisPickerTerritories"></div>' +
  '  <div id="analysisPickerResults"></div>' +
  '</div>' +
  '</body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true }
);

var w = dom.window;
global.window = w;
global.document = w.document;
global.HTMLElement = w.HTMLElement;
global.Event = w.Event;
global.CustomEvent = w.CustomEvent;
global.fetch = function (url) {
  if (url !== '/api/analyses/picker') {
    return Promise.reject(new Error('unexpected fetch: ' + url));
  }
  return Promise.resolve({
    ok: true,
    json: function () { return Promise.resolve({ modes: modes }); },
  });
};

var frameworkCloseCalls = 0;
w.OraFrameworkPicker = {
  close: function () { frameworkCloseCalls += 1; },
};

require(path.resolve(__dirname, '..', 'js', 'input-state.js'));
require(path.resolve(__dirname, '..', 'js', 'analysis-picker.js'));
w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));

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

function flush() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

function text(selector) {
  var el = w.document.querySelector(selector);
  return el ? el.textContent.trim() : '';
}

async function run() {
  record('OraInputState registered',
    !!w.OraInputState
      && typeof w.OraInputState.getAnalysisMode === 'function'
      && typeof w.OraInputState.getAnalysisLens === 'function');
  record('OraAnalysisPicker registered',
    !!w.OraAnalysisPicker && typeof w.OraAnalysisPicker.open === 'function');

  w.OraInputState.setFramework({
    id: 'terrain-mapping',
    display_name: 'Terrain Mapping',
  });
  record('framework can be staged before analysis selection',
    w.OraInputState.getFramework().id === 'terrain-mapping');

  w.document.dispatchEvent(new w.CustomEvent('ora:input-toolbar:analysis'));
  await flush();
  await flush();

  record('opening analyses closes framework picker',
    frameworkCloseCalls === 1,
    'calls=' + frameworkCloseCalls);
  record('picker is visible after toolbar event',
    w.document.getElementById('analysisPicker').hidden === false);
  record('initial view is territory overview',
    text('.analysis-picker__results-title') === 'All territories',
    text('.analysis-picker__results-title'));
  record('overview count uses mode total',
    text('.analysis-picker__results-count') === '4 modes',
    text('.analysis-picker__results-count'));
  record('overview renders territory rows',
    w.document.querySelectorAll('.analysis-picker__territory-card').length === 3);

  w.document.querySelector('.analysis-picker__territory-card[data-territory="T2"]').click();
  record('territory click drills into Interest & Power',
    text('.analysis-picker__results-title') === 'Interest & Power',
    text('.analysis-picker__results-title'));
  record('territory mode rows render',
    w.document.querySelectorAll('.analysis-picker__row').length === 2);

  var search = w.document.getElementById('analysisPickerSearch');
  search.value = 'cui bono';
  search.dispatchEvent(new w.Event('input', { bubbles: true }));
  record('search switches to global results',
    text('.analysis-picker__results-title') === 'Search results',
    text('.analysis-picker__results-title'));
  record('exact search narrows to Cui Bono',
    w.document.querySelectorAll('.analysis-picker__row').length === 1
      && w.document.querySelector('.analysis-picker__row').dataset.modeId === 'cui-bono');

  w.document.querySelector('.analysis-picker__row[data-mode-id="cui-bono"]').click();
  record('selecting analysis stores mode in input state',
    w.OraInputState.getAnalysisMode().id === 'cui-bono',
    JSON.stringify(w.OraInputState.getAnalysisMode()));
  record('selecting analysis clears staged framework',
    w.OraInputState.getFramework() === null);
  record('mode with lenses opens lens pass',
    w.document.getElementById('analysisPicker').hidden === false
      && text('.analysis-picker__results-title') === 'Cui Bono',
    text('.analysis-picker__results-title'));
  record('lens pass renders selectable lenses',
    w.document.querySelectorAll('.analysis-picker__lens-row').length === 3);
  record('lens row renders explanation',
    text('.analysis-picker__lens-row[data-lens-id="ulrich-csh-boundary-categories"] .analysis-picker__row-desc')
      === 'clarifies stakeholders and boundary judgments',
    text('.analysis-picker__lens-row[data-lens-id="ulrich-csh-boundary-categories"] .analysis-picker__row-desc'));

  w.document.querySelector('.analysis-picker__lens-row[data-lens-id="ulrich-csh-boundary-categories"]').click();
  record('selecting lens stores lens in input state',
    w.OraInputState.getAnalysisLens().id === 'ulrich-csh-boundary-categories',
    JSON.stringify(w.OraInputState.getAnalysisLens()));
  record('selecting lens closes picker',
    w.document.getElementById('analysisPicker').hidden === true);
  record('toolbar active state follows selected analysis',
    w.document.getElementById('inputToolbarAnalysis').classList.contains('is-active'));

  w.OraInputState.clearSelection();
  record('clearSelection clears selected analysis',
    w.OraInputState.getAnalysisMode() === null);
  record('clearSelection clears selected lens',
    w.OraInputState.getAnalysisLens() === null);
  record('clearSelection clears active toolbar state',
    !w.document.getElementById('inputToolbarAnalysis').classList.contains('is-active'));

  w.OraAnalysisPicker.open();
  await flush();
  await flush();
  record('reopening returns to selected mode territory',
    text('.analysis-picker__results-title') === 'Interest & Power',
    text('.analysis-picker__results-title'));
  record('reopened territory has no selected mode after clear',
    !w.document.querySelector('.analysis-picker__row[data-mode-id="cui-bono"]').classList.contains('is-selected'));
  w.OraAnalysisPicker.close();

  summarize();
}

run().catch(function (err) {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
