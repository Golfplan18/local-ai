#!/usr/bin/env node
/* test-composition-template-loader.js — WP-7.2.4
 *
 * Drives OraCompositionTemplateLoader through the §13.2 acceptance
 * criterion plus a battery of edge cases. Run:
 *
 *     node ~/ora/server/static/tests/test-composition-template-loader.js
 *
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var path = require('path');
var zlib = require('zlib');

var ORA_ROOT = path.resolve(__dirname, '..', '..', '..');
var CFF_PATH    = path.join(ORA_ROOT, 'server', 'static', 'canvas-file-format.js');
var LOADER_PATH = path.join(ORA_ROOT, 'server', 'static', 'composition-template-loader.js');

// ---- bootstrap -------------------------------------------------------------

delete require.cache[CFF_PATH];
delete require.cache[LOADER_PATH];

var canvasFileFormat = require(CFF_PATH);
canvasFileFormat._setGzipImpl({
  deflate: function (b) { return zlib.gzipSync(Buffer.from(b)); },
  inflate: function (b) { return zlib.gunzipSync(Buffer.from(b)); }
});
global.OraCanvasFileFormat = canvasFileFormat;

var loader = require(LOADER_PATH);

// ---- test harness ----------------------------------------------------------

var passCount = 0;
var failCount = 0;
var failures  = [];

function check(name, cond, detail) {
  if (cond) {
    passCount++;
    process.stdout.write('  PASS  ' + name + '\n');
  } else {
    failCount++;
    failures.push({ name: name, detail: detail });
    process.stdout.write('  FAIL  ' + name + '\n');
    if (detail !== undefined) {
      process.stdout.write('    ' + JSON.stringify(detail) + '\n');
    }
  }
}

function group(label) {
  process.stdout.write('\n' + label + '\n');
}

function freshLoader() {
  loader.init({ canvasFileFormat: canvasFileFormat });
  loader.clear();
}

// ---- fixture: 4-panel comic strip composition template -------------------

function buildComicStripTemplate() {
  var state = canvasFileFormat.newCanvasState({
    canvas_size: { width: 4000, height: 1200 },
    title: '4-panel comic strip'
  });

  for (var i = 0; i < 4; i++) {
    state.objects.push({
      id:    'panel-' + (i + 1),
      kind:  'shape',
      layer: 'background',
      placeholder: true,
      x: 100 + i * 950,
      y: 100,
      width:  900,
      height: 1000,
      shape:  'rect',
      stroke: '#000',
      stroke_width: 4,
      fill: '#ffffff'
    });
  }

  return {
    id:           'comic-4panel',
    title:        '4-panel comic strip',
    description:  'Classic four-panel layout with placeholder frames.',
    canvas_state: state
  };
}

function makeStubPanel() {
  return {
    received: null,
    loadCanvasState: function (state) { this.received = state; return true; }
  };
}

// ---- run -------------------------------------------------------------------

function runSync() {
  group('1. Registry surface');

  freshLoader();
  var tmpl = buildComicStripTemplate();
  var registeredId;
  try { registeredId = loader.register(tmpl); }
  catch (e) { registeredId = null; }
  check('register() returns the template id', registeredId === 'comic-4panel');
  check('has() finds the registered id',      loader.has('comic-4panel') === true);
  check('get() returns a deep clone', (function () {
    var got = loader.get('comic-4panel');
    if (!got) return false;
    got.title = 'mutated';
    var again = loader.get('comic-4panel');
    return again.title === '4-panel comic strip';
  })());
  check('list() returns one entry', loader.list().length === 1);

  try {
    loader.register(tmpl);
    check('register() rejects duplicate id', false);
  } catch (e) {
    check('register() rejects duplicate id', e && e.code === 'duplicate_template_id', { code: e && e.code });
  }

  check('unregister() removes the template', loader.unregister('comic-4panel') === true);
  check('unregister() after removal returns false', loader.unregister('comic-4panel') === false);
  check('list() empty after clear', loader.list().length === 0);

  group('2. Validation');

  freshLoader();
  try {
    loader.register({ id: '', title: 'no id', canvas_state: canvasFileFormat.newCanvasState({}) });
    check('rejects missing id', false);
  } catch (e) {
    check('rejects missing id', e && e.code === 'invalid_template');
  }
  try {
    loader.register({ id: 'bad-cs', title: 'bad', canvas_state: { not: 'a canvas' } });
    check('rejects malformed canvas_state', false);
  } catch (e) {
    check('rejects malformed canvas_state', e && e.code === 'invalid_template');
  }
}

function runAcceptance() {
  group('3. §13.2 acceptance — applyTemplate populates a fresh canvas');

  freshLoader();
  loader.register(buildComicStripTemplate());

  var panel = makeStubPanel();
  return loader.applyTemplate('comic-4panel', panel).then(function (state) {
    check('applyTemplate resolved with a state object', !!state && state.format_id === 'ora-canvas');
    check('panel.loadCanvasState was invoked', panel.received !== null);

    var st = panel.received;
    check('loaded state has 4 objects', Array.isArray(st.objects) && st.objects.length === 4);
    var allRects = st.objects.every(function (o) { return o.kind === 'shape' && o.shape === 'rect'; });
    check('all 4 objects are rect shapes', allRects);
    var allPlaceholders = st.objects.every(function (o) { return o.placeholder === true; });
    check('all 4 objects carry placeholder:true', allPlaceholders);
    var ids = st.objects.map(function (o) { return o.id; });
    check('panel ids preserved',
      JSON.stringify(ids) === JSON.stringify(['panel-1','panel-2','panel-3','panel-4']));
    check('modified_at is a fresh ISO timestamp',
      !!(st.metadata && /^\d{4}-\d{2}-\d{2}T/.test(st.metadata.modified_at)));

    // Defensive clone — caller mutation should not poison the registry.
    st.objects[0].id = 'mutated';
    var refetched = loader.get('comic-4panel');
    check('registry is shielded from caller mutation',
      refetched && refetched.canvas_state.objects[0].id === 'panel-1');
  });
}

function runOpenBlank() {
  group('4. openBlank() opens an empty canvas');

  var blankPanel = makeStubPanel();
  return loader.openBlank(blankPanel, { title: 'fresh' }).then(function (state) {
    check('blank state has format_id ora-canvas', state.format_id === 'ora-canvas');
    check('blank state has zero objects',         Array.isArray(state.objects) && state.objects.length === 0);
    check('blank state has 4 canonical layers',   Array.isArray(state.layers) && state.layers.length === 4);
    check('blank state title applied',            state.metadata && state.metadata.title === 'fresh');
    check('panel received the blank state',       blankPanel.received === state);
  });
}

function runPanelFallbacks() {
  group('5. Panel surface fallback chain');

  var altPanel = {
    got: null,
    loadFromCanvasState: function (s) { this.got = s; }
  };
  return loader.applyTemplate('comic-4panel', altPanel).then(function () {
    check('falls through to loadFromCanvasState', altPanel.got !== null);
  }).then(function () {
    return loader.applyTemplate('comic-4panel', { unrelated: 1 }).then(function () {
      check('rejects when panel has no load surface', false);
    }, function (e) {
      check('rejects when panel has no load surface',
        e && e.code === 'panel_load_unavailable', { code: e && e.code });
    });
  }).then(function () {
    return loader.applyTemplate('does-not-exist', makeStubPanel()).then(function () {
      check('rejects unknown template id', false);
    }, function (e) {
      check('rejects unknown template id',
        e && e.code === 'template_not_found', { code: e && e.code });
    });
  });
}

function runDialogHeadless() {
  group('6. showNewCanvasDialog headless choose');

  return loader.showNewCanvasDialog({
    choose: function (items) {
      check('dialog received template list',
        Array.isArray(items) && items.length === 1 && items[0].id === 'comic-4panel');
      return 'comic-4panel';
    }
  }).then(function (result) {
    check('dialog resolves with chosen template_id',
      result && result.template_id === 'comic-4panel');
  }).then(function () {
    return loader.showNewCanvasDialog({ choose: function () { return 'blank'; } })
      .then(function (result) {
        check('dialog "blank" resolves to template_id null',
          result && result.template_id === null);
      });
  }).then(function () {
    return loader.showNewCanvasDialog({ choose: function () { return null; } })
      .then(function (result) {
        check('dialog cancel resolves null', result === null);
      });
  });
}

function runPackLoaderSeams() {
  group('7. Pack-loader integration seams');

  freshLoader();
  var registry = loader.asPackLoaderRegistry();
  check('asPackLoaderRegistry exposes register/unregister/has/get/list',
    typeof registry.register === 'function'
      && typeof registry.unregister === 'function'
      && typeof registry.has === 'function'
      && typeof registry.get === 'function'
      && typeof registry.list === 'function');

  var t2 = buildComicStripTemplate();
  t2.id = 'comic-via-pack';
  registry.register(t2);
  check('pack-loader-style register lands in the loader', loader.has('comic-via-pack') === true);
  registry.unregister('comic-via-pack');
  check('pack-loader-style unregister removes from loader', loader.has('comic-via-pack') === false);

  freshLoader();
  var fakePackLoader = {
    listCompositionTemplates: function () {
      return [
        buildComicStripTemplate(),
        { id: '', title: 'invalid', canvas_state: {} },
        { id: 'second', title: 'Second',
          canvas_state: canvasFileFormat.newCanvasState({}) }
      ];
    }
  };
  var imported = loader.importFromPackLoader(fakePackLoader);
  check('importFromPackLoader returns ids of imported templates',
    Array.isArray(imported)
      && imported.indexOf('comic-4panel') !== -1
      && imported.indexOf('second') !== -1
      && imported.indexOf('') === -1,
    imported);
  check('importFromPackLoader skips malformed entries',
    loader.list().length === 2);
}

// ---- driver ---------------------------------------------------------------

Promise.resolve()
  .then(runSync)
  .then(runAcceptance)
  .then(runOpenBlank)
  .then(runPanelFallbacks)
  .then(runDialogHeadless)
  .then(runPackLoaderSeams)
  .then(function () {
    process.stdout.write('\n' + (failCount === 0
      ? 'ALL ' + passCount + ' CHECKS PASSED\n'
      : passCount + ' passed, ' + failCount + ' failed\n'));
    if (failCount > 0) {
      process.stdout.write(JSON.stringify(failures, null, 2) + '\n');
      process.exit(1);
    }
    process.exit(0);
  })
  .catch(function (e) {
    process.stderr.write('UNHANDLED: ' + (e && e.stack ? e.stack : e) + '\n');
    process.exit(2);
  });
