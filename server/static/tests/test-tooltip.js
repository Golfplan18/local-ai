#!/usr/bin/env node
/* Focused regression coverage for the shared tooltip lifecycle. */

'use strict';

var fs = require('fs');
var path = require('path');
var vm = require('vm');

var JSDOM_PATH = path.resolve(
  __dirname, '..', 'ora-visual-compiler', 'tests', 'node_modules', 'jsdom'
);
var jsdom;
try {
  jsdom = require(JSDOM_PATH);
} catch (e) {
  try { jsdom = require('jsdom'); }
  catch (_) {
    console.error('error: jsdom not available at ' + JSDOM_PATH);
    process.exit(2);
  }
}

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body><div id="sidebar-row" data-tooltip="Dialogue title">'
    + '<button id="nested-action">Close</button></div></body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
);
var win = dom.window;
var context = dom.getInternalVMContext();
var tooltipPath = path.resolve(__dirname, '..', 'tooltip.js');
vm.runInContext(fs.readFileSync(tooltipPath, 'utf8'), context, { filename: tooltipPath });
var toolbarPath = path.resolve(__dirname, '..', 'visual-toolbar.js');
vm.runInContext(fs.readFileSync(toolbarPath, 'utf8'), context, { filename: toolbarPath });

var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? ' - ' + detail : ''));
}

function flushMutations() {
  return new Promise(function (resolve) { win.queueMicrotask(resolve); });
}

function flushTimers() {
  return new Promise(function (resolve) { win.setTimeout(resolve, 0); });
}

function surfaceVisible() {
  var surface = win.document.getElementById('ora-shared-tooltip');
  return surface && surface.getAttribute('aria-hidden') === 'false';
}

async function show(anchor) {
  win.OraTooltip.setDelay(0);
  anchor.dispatchEvent(new win.MouseEvent('mouseover', { bubbles: true }));
  await flushTimers();
  await flushMutations();
}

async function run() {
  var row = win.document.getElementById('sidebar-row');
  var nestedAction = win.document.getElementById('nested-action');
  win.OraTooltip.init({ delayMs: 0 });

  await show(row);
  record('tooltip shows for the sidebar row', surfaceVisible());

  row.remove();
  await flushMutations();
  record('sidebar rerender removal dismisses the shared tooltip',
    !surfaceVisible() && win.OraTooltip._state.anchor === null);

  win.document.body.appendChild(row);
  nestedAction.addEventListener('click', function (event) { event.stopPropagation(); });
  await show(row);
  nestedAction.dispatchEvent(new win.MouseEvent('click', { bubbles: true }));
  record('nested action click dismisses despite stopped propagation', !surfaceVisible());

  win.document.body.removeChild(row);
  await flushMutations();
  win.OraVisualToolbar.register({
    id: 'test-toolbar',
    label: 'Test toolbar',
    items: [{ id: 'test-tool', binding: 'tool:test', label: 'Toolbar action', icon: 'square' }]
  });
  var toolbar = win.OraVisualToolbar.render('test-toolbar', { doc: win.document });
  win.document.body.appendChild(toolbar.el);
  var toolbarButton = toolbar.itemEls['test-tool'];
  await show(toolbarButton);
  record('tooltip shows for a visual-toolbar control', surfaceVisible());
  toolbar.destroy();
  await flushMutations();
  record('visual-toolbar teardown dismisses the shared tooltip',
    !surfaceVisible() && win.OraTooltip._state.anchor === null);

  win.OraTooltip.disable();
  var fallbackRow = win.document.createElement('div');
  fallbackRow.className = 'sidebar-row';
  fallbackRow.setAttribute('data-tooltip', 'New conversation title');
  win.document.body.appendChild(fallbackRow);
  win.OraVisualToolbar.register({
    id: 'fallback-toolbar',
    label: 'Fallback toolbar',
    items: [{ id: 'fallback-tool', binding: 'tool:fallback', label: 'Fallback action', icon: 'square' }]
  });
  var fallbackToolbar = win.OraVisualToolbar.render('fallback-toolbar', { doc: win.document });
  win.document.body.appendChild(fallbackToolbar.el);
  var fallbackButton = fallbackToolbar.itemEls['fallback-tool'];
  var genuineTitle = win.document.createElement('button');
  genuineTitle.setAttribute('data-tooltip', 'Renderer text');
  genuineTitle.setAttribute('title', 'Genuine native title');
  win.document.body.appendChild(genuineTitle);
  await flushMutations();
  record('disabled tooltips give dynamically created sidebar and toolbar controls native titles',
    fallbackRow.getAttribute('title') === 'New conversation title'
      && fallbackButton.getAttribute('title') === 'Fallback action');

  win.OraTooltip.enable();
  await flushMutations();
  record('re-enabled tooltips remove only renderer-owned native titles',
    !fallbackRow.hasAttribute('title')
      && !fallbackButton.hasAttribute('title')
      && genuineTitle.getAttribute('title') === 'Genuine native title');
  fallbackToolbar.destroy();

  var failed = results.filter(function (result) { return !result.ok; });
  console.log('');
  console.log((results.length - failed.length) + ' / ' + results.length + ' tests passed');
  if (failed.length) {
    failed.forEach(function (result) {
      console.log('  - ' + result.name + (result.detail ? ' :: ' + result.detail : ''));
    });
    process.exit(1);
  }
}

run().catch(function (error) {
  console.error(error && error.stack || error);
  process.exit(1);
});
