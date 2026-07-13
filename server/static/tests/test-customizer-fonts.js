#!/usr/bin/env node
/* Focused coverage for the platform-aware customizer font catalog.
 *
 * Run:
 *   node server/static/tests/test-customizer-fonts.js
 */

'use strict';

var fs = require('fs');
var path = require('path');
var vm = require('vm');

var SRC = path.resolve(__dirname, '..', 'js', 'customizer.js');
var source = fs.readFileSync(SRC, 'utf8');
var publicAssignment = 'window.OraCustomizer = { enter, exit, toggle };';
var instrumentedAssignment = [
  'window.OraCustomizer = { enter, exit, toggle, __fontTest: {',
  '  classifyPlatformHint, detectClientFontPlatform, visibleSystemFonts,',
  '  describeFontSelection, renderFont: AXIS_RENDERERS.font, catalog: FONT_CATALOG,',
  '  clientPlatform: CLIENT_FONT_PLATFORM',
  '} };',
].join('\n');
if (!source.includes(publicAssignment)) {
  throw new Error('FAIL: customizer public seam changed');
}
source = source.replace(publicAssignment, instrumentedAssignment);

function assert(name, condition, detail) {
  if (!condition) throw new Error('FAIL: ' + name + (detail ? ' — ' + detail : ''));
  console.log('PASS: ' + name);
}

function makeClassList() {
  var values = new Set();
  return {
    add: function () { Array.prototype.forEach.call(arguments, function (v) { values.add(v); }); },
    remove: function () { Array.prototype.forEach.call(arguments, function (v) { values.delete(v); }); },
    contains: function (value) { return values.has(value); },
    toggle: function (value, force) {
      if (force === false) values.delete(value);
      else if (force === true || !values.has(value)) values.add(value);
      else values.delete(value);
    },
  };
}

function makeElement(tag) {
  return {
    tagName: String(tag || '').toUpperCase(),
    children: [],
    style: {},
    dataset: {},
    classList: makeClassList(),
    textContent: '',
    appendChild: function (child) { this.children.push(child); child.parentNode = this; return child; },
    insertBefore: function (child) { return this.appendChild(child); },
    addEventListener: function (type, listener) {
      this._listeners = this._listeners || {};
      this._listeners[type] = listener;
    },
    removeEventListener: function () {},
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    matches: function () { return false; },
    closest: function () { return null; },
    remove: function () {},
    getBoundingClientRect: function () {
      return { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 };
    },
  };
}

function makeStorage(initial) {
  var values = Object.assign({}, initial || {});
  return {
    getItem: function (key) { return Object.prototype.hasOwnProperty.call(values, key) ? values[key] : null; },
    setItem: function (key, value) { values[key] = String(value); },
    removeItem: function (key) { delete values[key]; },
    snapshot: function () { return JSON.stringify(values); },
  };
}

function loadCustomizer(navigatorValue, initialStorage, computedValues) {
  var head = makeElement('head');
  var body = makeElement('body');
  var storage = makeStorage(initialStorage);
  var document = {
    head: head,
    body: body,
    createElement: makeElement,
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: function () { return null; },
    addEventListener: function () {},
    removeEventListener: function () {},
  };
  var context = {
    console: console,
    document: document,
    navigator: navigatorValue || {},
    localStorage: storage,
    getComputedStyle: function () {
      return {
        getPropertyValue: function (name) {
          return (computedValues && computedValues[name]) || '';
        },
        fontSize: '16px',
      };
    },
    setTimeout: function () { return 1; },
    clearTimeout: function () {},
    confirm: function () { return false; },
  };
  context.window = context;
  context.globalThis = context;
  vm.runInNewContext(source, context, { filename: SRC });
  return {
    api: context.OraCustomizer.__fontTest,
    storage: storage,
    userStyle: head.children.find(function (element) {
      return element.id === 'ora-user-customizations';
    }),
  };
}

function labels(fonts) { return fonts.map(function (font) { return font.label; }); }

var windowsNav = {
  userAgentData: { platform: 'Windows' },
  platform: 'Win32',
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
};
var macNav = {
  userAgentData: { platform: 'macOS' },
  platform: 'MacIntel',
  userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)',
  maxTouchPoints: 0,
};

var win = loadCustomizer(windowsNav);
var mac = loadCustomizer(macNav);
var unknown = loadCustomizer({ platform: 'Linux x86_64', userAgent: 'Mozilla/5.0 (X11; Linux x86_64)' });
var conflict = loadCustomizer({
  userAgentData: { platform: 'Windows' },
  platform: 'MacIntel',
  userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X)',
});

assert('consistent Windows hints classify as Windows', win.api.clientPlatform === 'windows');
assert('consistent macOS hints classify as macOS', mac.api.clientPlatform === 'macos');
assert('navigator.platform is used when client hints are absent',
  win.api.detectClientFontPlatform({ platform: 'Win32', userAgent: '' }) === 'windows');
assert('userAgent is the final recognized fallback',
  win.api.detectClientFontPlatform({ platform: '', userAgent: 'Windows NT 10.0' }) === 'windows');
assert('withheld hints fall back to unknown', win.api.detectClientFontPlatform({}) === 'unknown');
assert('Linux falls back to the portable catalog', unknown.api.clientPlatform === 'unknown');
assert('conflicting/spoofed hints fall back to unknown', conflict.api.clientPlatform === 'unknown');
assert('iPadOS MacIntel disguise falls back to unknown',
  win.api.detectClientFontPlatform({ platform: 'MacIntel', maxTouchPoints: 5 }) === 'unknown');
var hostileNavigator = {};
['userAgentData', 'platform', 'userAgent', 'maxTouchPoints'].forEach(function (name) {
  Object.defineProperty(hostileNavigator, name, {
    get: function () { throw new Error('withheld ' + name); },
  });
});
assert('throwing navigator getters fail safely to unknown',
  win.api.detectClientFontPlatform(hostileNavigator) === 'unknown');

var winLabels = labels(win.api.visibleSystemFonts('windows'));
var macLabels = labels(mac.api.visibleSystemFonts('macos'));
var unknownLabels = labels(unknown.api.visibleSystemFonts('unknown'));
assert('Windows offers Segoe UI and Consolas',
  winLabels.includes('Segoe UI') && winLabels.includes('Consolas'));
assert('Windows hides Avenir and SF Mono',
  !winLabels.includes('Avenir') && !winLabels.includes('SF Mono'));
assert('macOS offers Avenir and SF Mono',
  macLabels.includes('Avenir') && macLabels.includes('SF Mono') && macLabels.includes('Tahoma'));
assert('macOS hides Segoe UI and Consolas',
  !macLabels.includes('Segoe UI') && !macLabels.includes('Consolas'));
assert('unknown clients receive only portable choices',
  JSON.stringify(unknownLabels) === JSON.stringify(['System default', 'Sans-serif', 'Serif', 'Monospace']),
  JSON.stringify(unknownLabels));

var catalog = win.api.catalog;
assert('every catalog entry has an explicit platform tag',
  catalog.every(function (font) { return Array.isArray(font.platforms) && font.platforms.length > 0; }));
assert('every catalog stack ends with a generic fallback',
  catalog.every(function (font) { return /(sans-serif|serif|monospace)$/.test(font.value); }));
assert('font labels are unique', new Set(catalog.map(function (font) { return font.label; })).size === catalog.length);
assert('font values are unique', new Set(catalog.map(function (font) { return font.value; })).size === catalog.length);
assert('system default remains first and byte-compatible',
  catalog[0].value === '-apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif');

var avenir = 'Avenir, "Avenir Next", sans-serif';
var hiddenMac = win.api.describeFontSelection(avenir, 'windows');
assert('saved Mac font is not presented as a native Windows option', hiddenMac.matched === null);
assert('saved Mac font is explicitly surfaced instead of rewritten',
  hiddenMac.currentLabel === 'Current — Avenir (not standard on Windows)');
var renderedHidden = loadCustomizer(windowsNav, {}, { '--font-text': avenir });
var controls = makeElement('div');
renderedHidden.api.renderFont(
  { label: 'Font', var: '--font-text', type: 'font' }, makeElement('p'), controls
);
var renderedSelect = controls.children[0].children[1];
var renderedOptions = [];
renderedSelect.children.forEach(function (child) {
  if (child.tagName === 'OPTION') renderedOptions.push(child);
  else child.children.forEach(function (option) { renderedOptions.push(option); });
});
var currentOptions = renderedOptions.filter(function (option) { return option.value === avenir; });
assert('renderer shows a hidden saved stack exactly once and selected',
  currentOptions.length === 1 && currentOptions[0].selected === true &&
  currentOptions[0].textContent === hiddenMac.currentLabel);
var seg = '"Segoe UI", Arial, sans-serif';
var renderedWindowsOnMac = loadCustomizer(macNav, {}, { '--font-text': seg });
var macControls = makeElement('div');
renderedWindowsOnMac.api.renderFont(
  { label: 'Font', var: '--font-text', type: 'font' }, makeElement('p'), macControls
);
var macSelect = macControls.children[0].children[1];
var macOptions = [];
macSelect.children.forEach(function (child) {
  if (child.tagName === 'OPTION') macOptions.push(child);
  else child.children.forEach(function (option) { macOptions.push(option); });
});
var currentWindowsOptions = macOptions.filter(function (option) { return option.value === seg; });
assert('macOS renderer likewise preserves a saved Windows stack',
  currentWindowsOptions.length === 1 && currentWindowsOptions[0].selected === true &&
  currentWindowsOptions[0].textContent === 'Current — Segoe UI (not standard on macOS)');
var supportedWindows = win.api.describeFontSelection(seg, 'windows');
assert('supported saved Windows font selects its named option',
  supportedWindows.matched && supportedWindows.matched.label === 'Segoe UI' && supportedWindows.currentLabel === null);
assert('unknown custom stack remains a custom current value',
  win.api.describeFontSelection('Example Sans, sans-serif', 'windows').currentLabel === 'Current (custom)');
assert('known font on an unknown client is labeled without claiming absence',
  win.api.describeFontSelection(avenir, 'unknown').currentLabel ===
    'Current — Avenir (platform unknown)');

var stored = JSON.stringify({ default: { '--font-text': avenir } });
var applied = loadCustomizer(windowsNav, { 'ora-customizations-by-theme': stored });
assert('loading on Windows does not mutate a saved Mac stack',
  applied.storage.getItem('ora-customizations-by-theme') === stored);
assert('saved cross-platform value is applied byte-for-byte to CSS',
  applied.userStyle && applied.userStyle.textContent.includes('  --font-text: ' + avenir + ';'));

var changed = loadCustomizer(windowsNav, {}, {
  '--font-text': '-apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif',
});
var changedControls = makeElement('div');
changed.api.renderFont(
  { label: 'Font', var: '--font-text', type: 'font' }, makeElement('p'), changedControls
);
var changedSelect = changedControls.children[0].children[1];
changedSelect.value = seg;
Promise.resolve(changedSelect._listeners.change({ target: changedSelect })).then(function () {
  var persisted = JSON.parse(changed.storage.getItem('ora-customizations-by-theme'));
  assert('choosing a Windows font persists its exact fallback stack',
    persisted.default['--font-text'] === seg);
  console.log('customizer font tests passed');
}).catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
