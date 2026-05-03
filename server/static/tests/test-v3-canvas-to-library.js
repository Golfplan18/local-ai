#!/usr/bin/env node
/* test-v3-canvas-to-library.js — canvas-image → media-library helper
 *
 * Coverage for v3-canvas-to-library.js:
 *   • _dataUrlToBlob — base64 + percent-encoded data URLs, malformed
 *     inputs, mime-type round-trip.
 *   • _filenameFor — uses sourceName when present, falls back to a
 *     timestamped name with the right extension based on sourceType.
 *   • findCandidateImage — selection > userInputLayer (top-down) >
 *     backgroundImageNode preference order.
 *   • send — happy path, no-conversation, no-source, fetch failure.
 *   • sendBest — uses findCandidateImage to pick a node.
 *
 * Strategy: vm-sandbox the module with mocked Konva nodes (className
 * + getAttr + image()), mocked panel object, mocked fetch. The DOM
 * context-menu open path is covered indirectly by send (which is what
 * the menu actually invokes).
 *
 * Run:
 *   node ~/ora/server/static/tests/test-v3-canvas-to-library.js
 */

'use strict';

var fs   = require('fs');
var path = require('path');
var vm   = require('vm');

var SRC = path.resolve(__dirname, '..', 'js', 'v3-canvas-to-library.js');

// ── Mocked Konva node ──────────────────────────────────────────────────────

function makeImageNode(opts) {
  opts = opts || {};
  var attrs = Object.assign({}, opts.attrs || {});
  var imageEl = opts.image || null;
  return {
    _className: 'Image',
    getClassName: function () { return 'Image'; },
    getAttr: function (k) { return attrs[k]; },
    setAttr: function (k, v) { attrs[k] = v; },
    image: function () { return imageEl; },
  };
}

function makeShapeNode(className) {
  var attrs = {};
  return {
    getClassName: function () { return className; },
    getAttr: function (k) { return attrs[k]; },
    setAttr: function (k, v) { attrs[k] = v; },
  };
}

function makeLayer(children) {
  return {
    getChildren: function () { return (children || []).slice(); },
  };
}

function makePanel(opts) {
  opts = opts || {};
  return {
    _selectedShapeIds: opts.selectedShapeIds || [],
    _findShapeById: opts.findShapeById || function () { return null; },
    userInputLayer: opts.userInputLayer || null,
    _backgroundImageNode: opts.backgroundImageNode || null,
    conversationId: opts.conversationId || null,
  };
}

// ── Boot module into a sandbox ─────────────────────────────────────────────

function boot() {
  var fetchCalls = [];
  var fetchImpl = function (url, init) {
    fetchCalls.push({ url: url, init: init });
    return Promise.resolve({
      ok: true, status: 200,
      json: function () { return Promise.resolve({ ok: true, entry_id: 'e1' }); },
      blob: function () { return Promise.resolve({ size: 1, type: 'image/png' }); }
    });
  };

  var sandbox = {
    window: {
      OraConversation: { getCurrentId: function () { return 'conv-1'; } },
      OraCanvas: null,
      OraMediaLibrary: { refresh: function () { sandbox.window._refreshCalls = (sandbox.window._refreshCalls || 0) + 1; } },
      OraToast: null,
    },
    document: {
      createElement: function () { return { style: {}, setAttribute: function () {},
                                             addEventListener: function () {},
                                             appendChild: function () {} }; },
      body: { appendChild: function () {} },
      addEventListener: function () {},
      removeEventListener: function () {},
    },
    fetch: fetchImpl,
    setTimeout: function (fn) { return fn ? fn() : 0; },
    clearTimeout: function () {},
    Promise: Promise,
    Blob: function (parts, opts) {
      this.size = (parts && parts[0] && parts[0].length) || 0;
      this.type = (opts && opts.type) || '';
    },
    FormData: function () {
      var entries = [];
      this.append = function (k, v, n) { entries.push({k:k, v:v, n:n}); };
      this._entries = entries;
    },
    Uint8Array: Uint8Array,
    atob: function (s) { return Buffer.from(s, 'base64').toString('binary'); },
    decodeURIComponent: decodeURIComponent,
    encodeURIComponent: encodeURIComponent,
    console: { log:function(){}, info:function(){}, warn:function(){}, error:function(){} },
    Date: Date, Math: Math, Object: Object, Array: Array, JSON: JSON,
    isFinite: isFinite, parseInt: parseInt, parseFloat: parseFloat,
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(SRC, 'utf8'), sandbox);
  return {
    sandbox: sandbox,
    Lib: sandbox.window.OraV3CanvasToLibrary,
    fetchCalls: fetchCalls,
    setFetch: function (impl) {
      // Replace the live fetch in-context, also capturing calls into
      // fetchCalls so existing assertions keep working.
      sandbox.fetch = function (url, init) {
        fetchCalls.push({ url: url, init: init });
        return impl(url, init);
      };
    },
  };
}

// ── Test framework ─────────────────────────────────────────────────────────

var pass = 0, fail = 0;

function test(name, fn) {
  var p = Promise.resolve();
  return p.then(fn).then(function () {
    pass++; console.log('  ✓ ' + name);
  }).catch(function (e) {
    fail++;
    console.log('  ✗ ' + name);
    console.log('    ' + (e && e.stack ? e.stack : e));
  });
}
function assertEqual(a, b, msg) {
  var ok = (a === b) || (a && b && JSON.stringify(a) === JSON.stringify(b));
  if (!ok) throw new Error((msg || 'assertion')
                           + ': expected ' + JSON.stringify(b)
                           + ', got ' + JSON.stringify(a));
}
function assertTrue(c, m) { if (!c) throw new Error(m || 'expected truthy'); }
function assertFalse(c, m) { if (c) throw new Error(m || 'expected falsy'); }

// ─────────────────────────────────────────────────────────────────────────
// Tests run as a chain so async tests serialize (avoids interleaving in
// console output).
// ─────────────────────────────────────────────────────────────────────────

console.log('test-v3-canvas-to-library.js — canvas image → media library');

var b = boot();
var Lib = b.Lib;
var chain = Promise.resolve();

// ── _dataUrlToBlob ─────────────────────────────────────────────────────────

chain = chain.then(function () { return test('exports the public API', function () {
  assertTrue(typeof Lib.findCandidateImage === 'function');
  assertTrue(typeof Lib.send === 'function');
  assertTrue(typeof Lib.sendBest === 'function');
  assertTrue(typeof Lib.openContextMenu === 'function');
  assertTrue(typeof Lib._dataUrlToBlob === 'function');
  assertTrue(typeof Lib._filenameFor === 'function');
}); });

chain = chain.then(function () { return test('_dataUrlToBlob decodes a base64 PNG', function () {
  // 1x1 transparent PNG (well-known short data URL).
  var url = 'data:image/png;base64,'
    + 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=';
  var blob = Lib._dataUrlToBlob(url);
  assertTrue(blob !== null);
  assertEqual(blob.type, 'image/png');
  assertTrue(blob.size > 0);
}); });

chain = chain.then(function () { return test('_dataUrlToBlob preserves JPEG mime type', function () {
  var url = 'data:image/jpeg;base64,/9j/4AAQ';
  var blob = Lib._dataUrlToBlob(url);
  assertTrue(blob !== null);
  assertEqual(blob.type, 'image/jpeg');
}); });

chain = chain.then(function () { return test('_dataUrlToBlob returns null on malformed input', function () {
  assertEqual(Lib._dataUrlToBlob(''), null);
  assertEqual(Lib._dataUrlToBlob('not a data url'), null);
  assertEqual(Lib._dataUrlToBlob(null), null);
  assertEqual(Lib._dataUrlToBlob(123), null);
}); });

// ── _filenameFor ───────────────────────────────────────────────────────────

chain = chain.then(function () { return test('_filenameFor uses sourceName when present', function () {
  var node = makeImageNode({ attrs: { sourceName: 'my-image.png' } });
  assertEqual(Lib._filenameFor(node), 'my-image.png');
}); });

chain = chain.then(function () { return test('_filenameFor maps sourceType to extension when no sourceName', function () {
  var n1 = makeImageNode({ attrs: { sourceType: 'image/jpeg' } });
  assertTrue(/\.jpg$/.test(Lib._filenameFor(n1)));
  var n2 = makeImageNode({ attrs: { sourceType: 'image/png' } });
  assertTrue(/\.png$/.test(Lib._filenameFor(n2)));
  var n3 = makeImageNode({ attrs: { sourceType: 'image/webp' } });
  assertTrue(/\.webp$/.test(Lib._filenameFor(n3)));
}); });

chain = chain.then(function () { return test('_filenameFor falls back to .png when nothing is known', function () {
  var node = makeImageNode({});
  assertTrue(/\.png$/.test(Lib._filenameFor(node)));
}); });

// ── findCandidateImage ─────────────────────────────────────────────────────

chain = chain.then(function () { return test('findCandidateImage prefers the selected Konva.Image', function () {
  var img = makeImageNode({});
  img.id = 'img-1';
  var nonImg = makeShapeNode('Rect');
  nonImg.id = 'rect-1';
  var panel = makePanel({
    selectedShapeIds: ['img-1'],
    findShapeById: function (id) { return id === 'img-1' ? img : null; },
    userInputLayer: makeLayer([nonImg]),
    backgroundImageNode: makeImageNode({}),
  });
  assertEqual(Lib.findCandidateImage(panel), img);
}); });

chain = chain.then(function () { return test('findCandidateImage falls back to userInputLayer top-down', function () {
  var bottomImg = makeImageNode({}); bottomImg._tag = 'bottom';
  var topImg = makeImageNode({});    topImg._tag = 'top';
  var panel = makePanel({
    selectedShapeIds: [],
    findShapeById: function () { return null; },
    userInputLayer: makeLayer([bottomImg, topImg]),
    backgroundImageNode: null,
  });
  // Top of stack first.
  assertEqual(Lib.findCandidateImage(panel)._tag, 'top');
}); });

chain = chain.then(function () { return test('findCandidateImage falls back to background image', function () {
  var bg = makeImageNode({});
  var panel = makePanel({
    selectedShapeIds: [],
    findShapeById: function () { return null; },
    userInputLayer: makeLayer([makeShapeNode('Rect'), makeShapeNode('Text')]),
    backgroundImageNode: bg,
  });
  assertEqual(Lib.findCandidateImage(panel), bg);
}); });

chain = chain.then(function () { return test('findCandidateImage returns null on a blank canvas', function () {
  var panel = makePanel({
    selectedShapeIds: [],
    findShapeById: function () { return null; },
    userInputLayer: makeLayer([]),
    backgroundImageNode: null,
  });
  assertEqual(Lib.findCandidateImage(panel), null);
}); });

chain = chain.then(function () { return test('findCandidateImage skips selected non-image shapes', function () {
  var rect = makeShapeNode('Rect');
  rect.id = 'rect-1';
  var bg = makeImageNode({});
  var panel = makePanel({
    selectedShapeIds: ['rect-1'],
    findShapeById: function (id) { return id === 'rect-1' ? rect : null; },
    userInputLayer: makeLayer([rect]),
    backgroundImageNode: bg,
  });
  // Rect can't be sent; falls through to background image.
  assertEqual(Lib.findCandidateImage(panel), bg);
}); });

// ── send ───────────────────────────────────────────────────────────────────

chain = chain.then(function () { return test('send rejects when no node provided', function () {
  return Lib.send(makePanel(), null).then(function (r) {
    assertEqual(r.ok, false);
    assertEqual(r.reason, 'no image');
  });
}); });

chain = chain.then(function () { return test('send rejects when no active conversation', function () {
  // Boot a fresh sandbox without the OraConversation getter.
  var b2 = boot();
  b2.sandbox.window.OraConversation = null;
  // Re-extract Lib pointer (same module, same sandbox).
  var node = makeImageNode({ image: { src: 'data:image/png;base64,iVB' } });
  return b2.Lib.send(makePanel(), node).then(function (r) {
    assertEqual(r.ok, false);
    assertEqual(r.reason, 'no active conversation');
  });
}); });

chain = chain.then(function () { return test('send extracts a data URL and POSTs to media-library', function () {
  var b3 = boot();
  var dataUrl = 'data:image/png;base64,'
    + 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=';
  var node = makeImageNode({
    attrs: { sourceName: 'pic.png', sourceType: 'image/png' },
    image: { src: dataUrl }
  });
  return b3.Lib.send(makePanel(), node).then(function (r) {
    assertEqual(r.ok, true);
    assertEqual(r.via, 'dataUrl');
    var hits = b3.fetchCalls.filter(function (c) {
      return /\/api\/media-library\/[^/]+\/add$/.test(c.url);
    });
    assertEqual(hits.length, 1, 'one POST to /add');
    assertEqual(hits[0].init.method, 'POST');
  });
}); });

chain = chain.then(function () { return test('send rejects when source src is missing', function () {
  var node = makeImageNode({ image: { src: '' } });
  return Lib.send(makePanel(), node).then(function (r) {
    assertEqual(r.ok, false);
    assertEqual(r.reason, 'no source available');
  });
}); });

chain = chain.then(function () { return test('send fetches an http(s) src URL', function () {
  var b4 = boot();
  // Replace fetch to capture the URL pattern; the second fetch (POST to
  // /add) returns ok.
  var seen = [];
  b4.setFetch(function (url, init) {
    seen.push(url);
    if (url === 'https://example.invalid/img.png') {
      return Promise.resolve({
        ok: true, status: 200,
        blob: function () { return Promise.resolve({ size: 12, type: 'image/png' }); },
        json: function () { return Promise.resolve({}); }
      });
    }
    return Promise.resolve({
      ok: true, status: 200,
      json: function () { return Promise.resolve({ ok: true }); },
      blob: function () { return Promise.resolve({}); }
    });
  });
  var node = makeImageNode({ image: { src: 'https://example.invalid/img.png' } });
  return b4.Lib.send(makePanel(), node).then(function (r) {
    assertEqual(r.ok, true);
    assertEqual(r.via, 'url');
    assertTrue(seen.indexOf('https://example.invalid/img.png') >= 0);
  });
}); });

chain = chain.then(function () { return test('send surfaces an HTTP error from /add', function () {
  var b5 = boot();
  b5.setFetch(function (url) {
    if (/\/add$/.test(url)) {
      return Promise.resolve({
        ok: false, status: 413,
        json: function () { return Promise.resolve({ error: 'file too large' }); },
        blob: function () { return Promise.resolve({}); }
      });
    }
    return Promise.resolve({
      ok: true, status: 200,
      blob: function () { return Promise.resolve({}); },
      json: function () { return Promise.resolve({}); }
    });
  });
  var node = makeImageNode({
    image: { src: 'data:image/png;base64,aGk=' }
  });
  return b5.Lib.send(makePanel(), node).then(function (r) {
    assertEqual(r.ok, false);
    assertEqual(r.reason, 'file too large');
  });
}); });

// ── sendBest ──────────────────────────────────────────────────────────────

chain = chain.then(function () { return test('sendBest reports "no image on canvas" on a blank panel', function () {
  return Lib.sendBest(makePanel()).then(function (r) {
    assertEqual(r.ok, false);
    assertEqual(r.reason, 'no image on canvas');
  });
}); });

chain = chain.then(function () { return test('sendBest picks the best image and sends', function () {
  var b6 = boot();
  var node = makeImageNode({
    attrs: { sourceName: 'shot.png' },
    image: { src: 'data:image/png;base64,aGk=' }
  });
  var panel = makePanel({
    userInputLayer: makeLayer([node]),
  });
  return b6.Lib.sendBest(panel).then(function (r) {
    assertEqual(r.ok, true);
  });
}); });

// ── result ────────────────────────────────────────────────────────────────

chain = chain.then(function () {
  console.log('\n  ' + pass + ' passed, ' + fail + ' failed');
  process.exit(fail === 0 ? 0 : 1);
});
