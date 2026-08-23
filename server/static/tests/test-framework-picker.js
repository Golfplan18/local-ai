#!/usr/bin/env node
/* Focused Landing 2 coverage for the one-list framework picker. */
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

var rows = [
  { id: 'conversation-processing', display_name: 'Conversation Processing', display_description: 'process conversations' },
  { id: 'terrain-mapping', display_name: 'Terrain Mapping', display_description: 'map terrain' },
];
var dom = new jsdom.JSDOM(
  '<!doctype html><html><body>'
  + '<button id="inputToolbarFramework" type="button"></button>'
  + '<div id="frameworkPicker" hidden><input id="frameworkPickerSearch">'
  + '<div id="frameworkPickerList"></div></div>'
  + '</body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
);
var w = dom.window;
var context = dom.getInternalVMContext();
context.fetch = function (url) {
  if (url !== '/api/frameworks/picker') return Promise.reject(new Error('unexpected fetch ' + url));
  return Promise.resolve({ ok: true, json: function () { return Promise.resolve({ frameworks: rows }); } });
};
context.console = console;
vm.runInContext(fs.readFileSync(path.resolve(__dirname, '..', 'js', 'input-state.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.resolve(__dirname, '..', 'js', 'framework-picker.js'), 'utf8'), context);
w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));

function wait() {
  return new Promise(function (resolve) { w.setTimeout(resolve, 0); });
}
function ok(condition, message) {
  if (!condition) throw new Error(message);
  console.log('PASS ' + message);
}

async function run() {
  w.document.dispatchEvent(new w.CustomEvent('ora:input-toolbar:framework'));
  await wait();
  await wait();
  var picker = w.document.getElementById('frameworkPicker');
  var list = w.document.getElementById('frameworkPickerList');
  ok(!picker.hidden, 'picker opens from the toolbar event');
  ok(list.querySelectorAll('.framework-picker__row').length === 2,
     'all public rows render in one list');
  ok(!list.querySelector('.framework-picker__group'),
     'picker does not render category groups');
  ok(!list.querySelector('[data-category]'),
     'picker rows do not carry category metadata');
  list.querySelector('[data-framework-id="terrain-mapping"]').click();
  ok(w.OraInputState.getFramework().id === 'terrain-mapping',
     'selection stores the canonical framework id');

  var source = fs.readFileSync(path.resolve(__dirname, '..', 'settings-panel.js'), 'utf8');
  ok(source.indexOf('Add new provider') === -1,
     'Add-provider shortcut is absent');
  ok(source.indexOf("saveBtn.textContent = 'Save'") !== -1
     && source.indexOf("saveBtn.title = 'Checks the key") !== -1
     && source.indexOf("removeBtn.textContent = 'Remove'") !== -1,
     'provider Save/Verify/Remove controls remain available');
  console.log('6 / 6 tests passed');
}

run().catch(function (error) {
  console.error('FAIL ' + error.message);
  process.exit(1);
});
