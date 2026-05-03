#!/usr/bin/env node
/* test-pack-loader.js — WP-7.2.1
 *
 * Drives OraPackLoader through the §13.2 acceptance criterion plus a
 * battery of edge cases. Run:
 *
 *     node ~/ora/server/static/tests/test-pack-loader.js
 *
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var fs = require('fs');
var path = require('path');
var os = require('os');

var ORA_ROOT = path.resolve(__dirname, '..', '..', '..');
var SCHEMA_PATH    = path.join(ORA_ROOT, 'config', 'schemas', 'toolbar-pack.schema.json');
var VALIDATOR_PATH = path.join(ORA_ROOT, 'server', 'static', 'pack-validator.js');
var LOADER_PATH    = path.join(ORA_ROOT, 'server', 'static', 'pack-loader.js');
var TOOLBAR_PATH   = path.join(ORA_ROOT, 'server', 'static', 'visual-toolbar.js');
var NAMES_PATH     = path.join(ORA_ROOT, 'server', 'static', 'vendor', 'lucide', 'names.json');
var AJV_PATH       = path.join(ORA_ROOT, 'server', 'static', 'ora-visual-compiler', 'tests', 'node_modules', 'ajv', 'dist', '2020.js');

// ---- bootstrap -------------------------------------------------------------

var schema = JSON.parse(fs.readFileSync(SCHEMA_PATH, 'utf8'));
var lucideNames = JSON.parse(fs.readFileSync(NAMES_PATH, 'utf8'));
var canonicalNameSet = new Set(lucideNames.names);

var Ajv2020 = require(AJV_PATH);
var AjvCtor = (typeof Ajv2020 === 'function') ? Ajv2020 : Ajv2020.default;
if (typeof AjvCtor !== 'function') {
  console.error('error: could not load Ajv2020 from ' + AJV_PATH);
  process.exit(2);
}
var ajv = new AjvCtor({
  strict: true, strictRequired: 'log', allErrors: true, allowUnionTypes: true
});
var validateFn = ajv.compile(schema);

// visual-toolbar.js depends on a `document`-style global only at render
// time. register() does not. We'll only call register() in this test.
var iconResolverStub = {
  isValidName: function (name) {
    return canonicalNameSet.has(name);
  },
  resolve: function (n) {
    return '<svg viewBox="0 0 24 24" data-icon="' + String(n).replace(/[<>&"]/g, '') + '"></svg>';
  }
};

// Stand up a fresh module scope for visual-toolbar so the registry starts
// empty and visible. The module attaches OraPackValidator + OraIconResolver
// to whichever `root` is in scope, so we install both onto a sandbox.
function _loadVisualToolbar() {
  // Re-require by path; Node caches but we want a fresh module per-test
  // sometimes. delete cache first.
  delete require.cache[TOOLBAR_PATH];
  return require(TOOLBAR_PATH);
}

var validatorMod = require(VALIDATOR_PATH);
validatorMod.init({ ajvValidateFn: validateFn, iconResolver: iconResolverStub });

// Make resolver + validator available as globals so visual-toolbar.js
// finds them.
global.OraPackValidator = validatorMod;
global.OraIconResolver  = iconResolverStub;

var toolbarMod = _loadVisualToolbar();
var loaderMod = require(LOADER_PATH);

// ---- test runner -----------------------------------------------------------

var passCount = 0;
var failCount = 0;
var failures  = [];

function deepEqual(a, b) {
  if (a === b) return true;
  if (a == null || b == null) return false;
  if (typeof a !== typeof b) return false;
  if (Array.isArray(a)) {
    if (!Array.isArray(b) || a.length !== b.length) return false;
    for (var i = 0; i < a.length; i++) if (!deepEqual(a[i], b[i])) return false;
    return true;
  }
  if (typeof a !== 'object') return false;
  var ak = Object.keys(a).sort();
  var bk = Object.keys(b).sort();
  if (ak.length !== bk.length) return false;
  for (var k = 0; k < ak.length; k++) {
    if (ak[k] !== bk[k]) return false;
    if (!deepEqual(a[ak[k]], b[ak[k]])) return false;
  }
  return true;
}

function check(name, cond, detail) {
  if (cond) {
    passCount++;
    process.stdout.write('  PASS  ' + name + '\n');
  } else {
    failCount++;
    failures.push({ name: name, detail: detail });
    process.stdout.write('  FAIL  ' + name + '\n');
    if (detail) process.stdout.write('    ' + JSON.stringify(detail) + '\n');
  }
}

function arraysEqual(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b)) return false;
  if (a.length !== b.length) return false;
  var aa = a.slice().sort();
  var bb = b.slice().sort();
  for (var i = 0; i < aa.length; i++) if (aa[i] !== bb[i]) return false;
  return true;
}

// ---- fixtures --------------------------------------------------------------

// Pack A — exercises all four artifact types. Spec §14 mood-board pack
// expanded with a macro and a prompt template.
var SAMPLE_PACK_A = {
  pack_name: "Sample Loader Pack A",
  pack_version: "1.0.0",
  ora_compatibility: ">=0.7.0",
  author: { name: "Ora Tests" },
  description: "All four artifact types for WP-7.2.1 acceptance",
  toolbars: [
    {
      id: "loader-test-a",
      label: "Loader Test A",
      default_dock: "left",
      items: [
        { id: "select",   icon: "mouse-pointer", label: "Select",   shortcut: "V", binding: "tool:select" },
        { id: "annotate", icon: "highlighter",   label: "Annotate", binding: "tool:annotate" }
      ]
    }
  ],
  macros: [
    {
      id: "loader-test-macro-a",
      label: "Speech Bubble (test)",
      icon: "message-circle",
      steps: [
        { tool: "shape:speech_bubble", params: { click_to_place: true } }
      ]
    }
  ],
  prompt_templates: [
    {
      id: "loader-test-tpl-a",
      slash_command: "/loader-test-a",
      label: "Loader Test Template A",
      template: "A {{adj|cool}} thing in the style of {{style}}",
      variables: [
        { name: "adj",   type: "text", default: "cool" },
        { name: "style", type: "text" }
      ],
      capability_route: "image_generates"
    }
  ],
  composition_templates: [
    {
      id: "loader-test-comp-a",
      label: "1x1 starter (test)",
      canvas_state: {
        version: 1,
        layers: [{ id: "background", objects: [
          { type: "rect", x: 0, y: 0, width: 100, height: 100, placeholder: true }
        ]}],
        view: { zoom: 1.0, pan_x: 0, pan_y: 0 }
      }
    }
  ]
};

// Pack B — independent ids; used for "unload removes only that pack's
// artifacts".
var SAMPLE_PACK_B = {
  pack_name: "Sample Loader Pack B",
  pack_version: "1.0.0",
  ora_compatibility: ">=0.7.0",
  author: { name: "Ora Tests" },
  toolbars: [
    {
      id: "loader-test-b",
      label: "Loader Test B",
      items: [
        { id: "select", icon: "mouse-pointer", label: "Select", binding: "tool:select" }
      ]
    }
  ],
  macros: [
    { id: "loader-test-macro-b", label: "Macro B", steps: [
      { tool: "shape:speech_bubble", params: {} }
    ]}
  ],
  prompt_templates: [
    { id: "loader-test-tpl-b", label: "Template B",
      template: "Hello {{name}}", variables: [{ name: "name", type: "text" }],
      gear_preference: 1 }
  ],
  composition_templates: [
    { id: "loader-test-comp-b", label: "Comp B",
      canvas_state: { version: 1, layers: [], view: { zoom: 1, pan_x: 0, pan_y: 0 }}}
  ]
};

// Pack C — collides with pack A on a macro id.
var SAMPLE_PACK_C_COLLIDING = {
  pack_name: "Sample Loader Pack C",
  pack_version: "1.0.0",
  ora_compatibility: ">=0.7.0",
  author: { name: "Ora Tests" },
  macros: [
    { id: "loader-test-macro-a", label: "Collides w/ pack A",
      steps: [{ tool: "shape:speech_bubble", params: {} }] }
  ]
};

// Pack D — fails validation (missing required pack_name).
var SAMPLE_PACK_D_INVALID = {
  pack_version: "1.0.0",
  ora_compatibility: ">=0.7.0",
  author: { name: "Ora Tests" },
  macros: [{ id: "x", label: "x", steps: [{ tool: "noop", params: {} }] }]
};

// ---- TEST 1 — §13.2 acceptance criterion ----------------------------------

(async function runTests() {
  process.stdout.write('\n--- TEST 1: §13.2 acceptance criterion ---\n');

  await loaderMod.init({
    validator: validatorMod,
    toolbarRegistry: toolbarMod
  });

  // Confirm clean state before we start. visual-toolbar's registry is
  // module-scoped, so any leftover entries from earlier tests in the same
  // process would falsify our "only this pack's toolbar" check.
  toolbarMod.clear();
  loaderMod.clear();

  var loadRes = await loaderMod.loadPack(SAMPLE_PACK_A);
  check('1a. loadPack(SAMPLE_PACK_A) succeeds',
    loadRes.success === true && loadRes.errors.length === 0,
    loadRes);
  check('1b. pack_id is "<name>@<version>"',
    loadRes.pack_id === 'Sample Loader Pack A@1.0.0', loadRes.pack_id);

  // All four artifact types registered.
  check('1c. registered.toolbars contains loader-test-a',
    arraysEqual(loadRes.registered.toolbars, ['loader-test-a']),
    loadRes.registered.toolbars);
  check('1d. registered.macros contains loader-test-macro-a',
    arraysEqual(loadRes.registered.macros, ['loader-test-macro-a']),
    loadRes.registered.macros);
  check('1e. registered.prompt_templates contains loader-test-tpl-a',
    arraysEqual(loadRes.registered.prompt_templates, ['loader-test-tpl-a']),
    loadRes.registered.prompt_templates);
  check('1f. registered.composition_templates contains loader-test-comp-a',
    arraysEqual(loadRes.registered.composition_templates, ['loader-test-comp-a']),
    loadRes.registered.composition_templates);

  // Toolbar registry shows the pack-supplied toolbar.
  check('1g. toolbar registry has loader-test-a',
    toolbarMod.has('loader-test-a'), toolbarMod.list());

  // Stub stores hold macro/template/composition defs (no external registry
  // wired in this test).
  check('1h. listMacros() returns the macro def',
    loaderMod.listMacros().length === 1
    && loaderMod.listMacros()[0].id === 'loader-test-macro-a',
    loaderMod.listMacros());
  check('1i. listPromptTemplates() returns the template def',
    loaderMod.listPromptTemplates().length === 1
    && loaderMod.listPromptTemplates()[0].id === 'loader-test-tpl-a',
    loaderMod.listPromptTemplates());
  check('1j. listCompositionTemplates() returns the comp def',
    loaderMod.listCompositionTemplates().length === 1
    && loaderMod.listCompositionTemplates()[0].id === 'loader-test-comp-a',
    loaderMod.listCompositionTemplates());

  check('1k. listInstalled() shows pack A',
    loaderMod.listInstalled().length === 1
    && loaderMod.listInstalled()[0].pack_id === 'Sample Loader Pack A@1.0.0',
    loaderMod.listInstalled());

  // Unload — verify each artifact type goes away.
  var unloadRes = loaderMod.unloadPack('Sample Loader Pack A@1.0.0');
  check('1l. unloadPack succeeds',
    unloadRes.success === true && unloadRes.errors.length === 0,
    unloadRes);
  check('1m. removed.toolbars',
    arraysEqual(unloadRes.removed.toolbars, ['loader-test-a']));
  check('1n. removed.macros',
    arraysEqual(unloadRes.removed.macros, ['loader-test-macro-a']));
  check('1o. removed.prompt_templates',
    arraysEqual(unloadRes.removed.prompt_templates, ['loader-test-tpl-a']));
  check('1p. removed.composition_templates',
    arraysEqual(unloadRes.removed.composition_templates, ['loader-test-comp-a']));
  check('1q. toolbar registry no longer has loader-test-a',
    !toolbarMod.has('loader-test-a'));
  check('1r. listMacros() is now empty',
    loaderMod.listMacros().length === 0);
  check('1s. listInstalled() is now empty',
    loaderMod.listInstalled().length === 0);

  // ---- TEST 2 — Two packs side by side; unload one, leave the other --------
  process.stdout.write('\n--- TEST 2: unload removes only target pack ---\n');

  toolbarMod.clear();
  loaderMod.clear();

  var loadA = await loaderMod.loadPack(SAMPLE_PACK_A);
  var loadB = await loaderMod.loadPack(SAMPLE_PACK_B);
  check('2a. pack A loaded',
    loadA.success === true, loadA.errors);
  check('2b. pack B loaded',
    loadB.success === true, loadB.errors);
  check('2c. listInstalled has both',
    loaderMod.listInstalled().length === 2);

  // Unload A only.
  loaderMod.unloadPack('Sample Loader Pack A@1.0.0');
  check('2d. pack A no longer installed',
    !loaderMod.has('Sample Loader Pack A@1.0.0'));
  check('2e. pack B still installed',
    loaderMod.has('Sample Loader Pack B@1.0.0'));
  check('2f. toolbar A removed',
    !toolbarMod.has('loader-test-a'));
  check('2g. toolbar B still present',
    toolbarMod.has('loader-test-b'));
  // Stub stores: B's macro/template/composition still there; A's gone.
  var macroIds = loaderMod.listMacros().map(function (m) { return m.id; });
  check('2h. only pack B macro remains',
    arraysEqual(macroIds, ['loader-test-macro-b']), macroIds);
  var tplIds = loaderMod.listPromptTemplates().map(function (t) { return t.id; });
  check('2i. only pack B prompt template remains',
    arraysEqual(tplIds, ['loader-test-tpl-b']), tplIds);
  var compIds = loaderMod.listCompositionTemplates().map(function (c) { return c.id; });
  check('2j. only pack B composition template remains',
    arraysEqual(compIds, ['loader-test-comp-b']), compIds);

  // ---- TEST 3 — duplicate-id collision rejected ---------------------------
  process.stdout.write('\n--- TEST 3: duplicate-id collision rejected ---\n');

  // Pack C re-uses macro id "loader-test-macro-a" which pack A still owns
  // here (we haven't unloaded B which doesn't carry that id).
  // Re-load A so it's back in flight.
  toolbarMod.clear();
  loaderMod.clear();
  await loaderMod.loadPack(SAMPLE_PACK_A);

  var collideRes = await loaderMod.loadPack(SAMPLE_PACK_C_COLLIDING);
  check('3a. colliding pack rejected',
    collideRes.success === false);
  check('3b. error code is duplicate_artifact_id',
    collideRes.errors.some(function (e) { return e.code === 'duplicate_artifact_id'; }),
    collideRes.errors);
  check('3c. pack A is still installed',
    loaderMod.has('Sample Loader Pack A@1.0.0'));
  check('3d. pack C is NOT installed',
    !loaderMod.has('Sample Loader Pack C@1.0.0'));

  // ---- TEST 4 — invalid pack rejected at validator ------------------------
  process.stdout.write('\n--- TEST 4: invalid pack rejected ---\n');
  var invRes = await loaderMod.loadPack(SAMPLE_PACK_D_INVALID);
  check('4a. invalid pack rejected',
    invRes.success === false);
  check('4b. errors is the validator findings list',
    invRes.errors.length > 0
    && invRes.errors[0].source === 'schema',
    invRes.errors);

  // ---- TEST 5 — duplicate install of same pack rejected -------------------
  process.stdout.write('\n--- TEST 5: duplicate install rejected ---\n');
  var dupRes = await loaderMod.loadPack(SAMPLE_PACK_A);
  check('5a. duplicate install rejected',
    dupRes.success === false
    && dupRes.errors.some(function (e) { return e.code === 'pack_already_installed'; }),
    dupRes.errors);

  // ---- TEST 6 — load from disk path ---------------------------------------
  process.stdout.write('\n--- TEST 6: load from disk path ---\n');
  toolbarMod.clear();
  loaderMod.clear();
  var tmp = path.join(os.tmpdir(), 'ora-pack-loader-test-' + process.pid + '.json');
  fs.writeFileSync(tmp, JSON.stringify(SAMPLE_PACK_A));
  var diskRes = await loaderMod.loadPack(tmp);
  check('6a. disk-path load succeeds',
    diskRes.success === true && diskRes.pack_id === 'Sample Loader Pack A@1.0.0',
    diskRes);
  check('6b. installed.source is the disk path',
    loaderMod.getInstalled('Sample Loader Pack A@1.0.0').source === tmp);
  fs.unlinkSync(tmp);

  // ---- TEST 7 — load from JSON string -------------------------------------
  process.stdout.write('\n--- TEST 7: load from JSON string ---\n');
  toolbarMod.clear();
  loaderMod.clear();
  var jsonRes = await loaderMod.loadPack(JSON.stringify(SAMPLE_PACK_B));
  check('7a. inline-json load succeeds',
    jsonRes.success === true && jsonRes.pack_id === 'Sample Loader Pack B@1.0.0',
    jsonRes);

  // ---- TEST 8 — external macro registry -----------------------------------
  process.stdout.write('\n--- TEST 8: external macro registry passthrough ---\n');
  toolbarMod.clear();
  loaderMod.clear();

  var externalMacros = Object.create(null);
  var externalRegistry = {
    register: function (def) { externalMacros[def.id] = def; },
    unregister: function (id) { delete externalMacros[id]; }
  };
  // Re-init the loader to swap in the external macro registry.
  await loaderMod.init({
    validator: validatorMod,
    toolbarRegistry: toolbarMod,
    macroRegistry: externalRegistry
  });
  await loaderMod.loadPack(SAMPLE_PACK_A);
  check('8a. external registry received the macro',
    externalMacros['loader-test-macro-a'] != null);
  check('8b. fallback store stays empty when external registry is wired',
    loaderMod.listMacros().length === 0);
  loaderMod.unloadPack('Sample Loader Pack A@1.0.0');
  check('8c. external registry was unregistered on unload',
    externalMacros['loader-test-macro-a'] == null);

  // Restore plain config for any later use.
  await loaderMod.init({ validator: validatorMod, toolbarRegistry: toolbarMod });

  // ---- summary ------------------------------------------------------------

  process.stdout.write('\n');
  process.stdout.write('Total: ' + (passCount + failCount) + ' | Passed: ' + passCount + ' | Failed: ' + failCount + '\n');
  if (failCount > 0) {
    process.stdout.write('\nFailures:\n');
    for (var i = 0; i < failures.length; i++) {
      process.stdout.write('  - ' + failures[i].name + '\n');
    }
    process.exit(1);
  }
  process.exit(0);
})().catch(function (e) {
  console.error('FATAL: test harness threw:', e);
  process.exit(2);
});
