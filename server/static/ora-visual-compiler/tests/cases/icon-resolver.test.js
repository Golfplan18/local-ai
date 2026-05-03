/**
 * Test harness for icon-resolver.js + scripts/lucide-tree-shake.js (WP-7.0.3).
 *
 * Plain Node — does not use the visual-compiler jsdom stack. Run with:
 *   node ~/ora/server/static/ora-visual-compiler/tests/cases/icon-resolver.test.js
 *
 * Test criterion (per §13.0 WP-7.0.3):
 *   "Resolve 20 known names; resolve a custom inline SVG; resolve an unknown
 *    name returns fallback; tree-shake produces an output set matching only
 *    referenced names."
 *
 * Exits non-zero on any failure.
 */

'use strict';

var fs = require('fs');
var os = require('os');
var path = require('path');

var resolverPath = path.resolve(__dirname, '../../../icon-resolver.js');
var resolver = require(resolverPath);

var treeShakePath = path.resolve(__dirname, '../../../../../scripts/lucide-tree-shake.js');
var treeShake = require(treeShakePath);

var ICON_DIR = path.resolve(__dirname, '../../../vendor/lucide/icons');
var NAMES_PATH = path.resolve(__dirname, '../../../vendor/lucide/names.json');

var passed = 0;
var failed = 0;
var failures = [];

function ok(label, cond) {
  if (cond) {
    passed++;
    console.log('  PASS  ' + label);
  } else {
    failed++;
    failures.push(label);
    console.log('  FAIL  ' + label);
  }
}

function eq(label, actual, expected) {
  var match = JSON.stringify(actual) === JSON.stringify(expected);
  if (!match) {
    console.log('       expected: ' + JSON.stringify(expected));
    console.log('       actual:   ' + JSON.stringify(actual));
  }
  ok(label, match);
}

// ---- bootstrap resolver from disk -----------------------------------------

function _bootstrapResolver() {
  // Pre-populate from the actual vendored set so the test runs hermetically
  // (no fetch needed).
  var namesPayload = JSON.parse(fs.readFileSync(NAMES_PATH, 'utf8'));
  var iconSet = {};
  // Load just enough icons for the known-name test (the resolver returns a
  // marked fallback for canonical-but-not-loaded names; we want real SVGs
  // for the 20-known-name test).
  var seedNames = [
    'image', 'crop', 'rotate-cw', 'type', 'square', 'circle', 'pencil',
    'eraser', 'undo-2', 'redo-2', 'save', 'download', 'upload',
    'arrow-up', 'arrow-down', 'arrow-left', 'arrow-right',
    'zoom-in', 'zoom-out', 'trash-2'
  ];
  seedNames.forEach(function (n) {
    var p = path.join(ICON_DIR, n + '.svg');
    if (fs.existsSync(p)) iconSet[n] = fs.readFileSync(p, 'utf8');
  });
  resolver.clearCache();
  return resolver.init({
    iconSet: iconSet,
    names: namesPayload.names,
    version: namesPayload.version
  }).then(function () {
    return seedNames;
  });
}

// ---- tests ----------------------------------------------------------------

function testKnownNames(seedNames) {
  console.log('\n[1] resolve 20 known names');
  ok('seed name list contains 20 entries', seedNames.length === 20);
  for (var i = 0; i < seedNames.length; i++) {
    var name = seedNames[i];
    var svg = resolver.resolve(name);
    // Vendored SVGs lead with a "<!-- @license ... -->" comment then <svg>.
    var hasSvgTag = typeof svg === 'string'
      && /<svg[\s>]/i.test(svg);
    var notFallback = svg.indexOf('data-ora-icon-fallback') === -1;
    var hasClosing = svg.indexOf('</svg>') !== -1;
    var hasLucideClass = svg.indexOf('lucide-' + name) !== -1;
    ok('  resolve("' + name + '") → real Lucide SVG',
       hasSvgTag && notFallback && hasClosing && hasLucideClass);
  }
}

function testInlineSvg() {
  console.log('\n[2] resolve a custom inline SVG');

  var customSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/></svg>';
  var resolved = resolver.resolve(customSvg);
  ok('  inline <svg> string returned as-is', resolved === customSvg);

  var withWhitespace = '   <SVG width="10" height="10"><rect/></svg>  ';
  var resolved2 = resolver.resolve(withWhitespace);
  ok('  case-insensitive <svg> opener accepted', resolved2 === withWhitespace);

  // Validation: malformed SVGs fall back, not crash.
  var noClosing = '<svg width="10"';
  var fb = resolver.resolve(noClosing);
  ok('  malformed SVG (no closing tag) → fallback',
     fb.indexOf('data-ora-icon-fallback="true"') !== -1);

  var withScript = '<svg><script>alert(1)</script></svg>';
  var fbScript = resolver.resolve(withScript);
  ok('  SVG with <script> → fallback (security)',
     fbScript.indexOf('data-ora-icon-fallback="true"') !== -1);

  var withHandler = '<svg onload="evil()"><circle/></svg>';
  var fbHandler = resolver.resolve(withHandler);
  ok('  SVG with on* event handler → fallback (security)',
     fbHandler.indexOf('data-ora-icon-fallback="true"') !== -1);
}

function testUnknownName() {
  console.log('\n[3] resolve an unknown name returns fallback');

  var fb = resolver.resolve('definitely-not-a-real-icon');
  ok('  unknown name returns fallback SVG',
     fb.indexOf('data-ora-icon-fallback="true"') !== -1);
  ok('  fallback contains aria-label naming the missing icon',
     fb.indexOf('Unknown icon: definitely-not-a-real-icon') !== -1);
  ok('  fallback marked with reason',
     fb.indexOf('data-ora-icon-fallback-reason="unknown-name"') !== -1);

  // Edge cases.
  ok('  empty string → fallback',
     resolver.resolve('').indexOf('data-ora-icon-fallback') !== -1);
  ok('  null → fallback',
     resolver.resolve(null).indexOf('data-ora-icon-fallback') !== -1);
  ok('  undefined → fallback',
     resolver.resolve(undefined).indexOf('data-ora-icon-fallback') !== -1);
  ok('  Uppercase / weird name → fallback',
     resolver.resolve('Image_With_Underscores').indexOf('data-ora-icon-fallback') !== -1);
  ok('  attempted XSS via name → fallback',
     resolver.resolve('"><script>x</script>').indexOf('data-ora-icon-fallback') !== -1);
}

function testIsValidName() {
  console.log('\n[4] isValidName / listNames introspection (for WP-7.0.4)');

  ok('  isValidName("image") → true', resolver.isValidName('image') === true);
  ok('  isValidName("crop") → true', resolver.isValidName('crop') === true);
  ok('  isValidName("not-a-real-icon") → false',
     resolver.isValidName('not-a-real-icon') === false);
  ok('  isValidName("") → false', resolver.isValidName('') === false);
  ok('  isValidName(undefined) → false', resolver.isValidName(undefined) === false);
  ok('  isValidName("Image") → false (case-sensitive)',
     resolver.isValidName('Image') === false);

  var names = resolver.listNames();
  ok('  listNames() returns array', Array.isArray(names));
  ok('  listNames() has > 1000 entries', names.length > 1000);
  ok('  listNames() is sorted',
     names.length > 1 && names[0] < names[names.length - 1]);
  ok('  listNames() contains "image"', names.indexOf('image') !== -1);

  ok('  getVersion() returns Lucide version', /\d+\.\d+\.\d+/.test(resolver.getVersion()));
}

function testTreeShake() {
  console.log('\n[5] tree-shake produces output set matching only referenced names');

  // Build temp config dirs with synthetic toolbar + pack JSONs.
  var tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'ora-treeshake-'));
  var toolbarDir = path.join(tmpRoot, 'toolbars');
  var packDir = path.join(tmpRoot, 'packs');
  fs.mkdirSync(toolbarDir, { recursive: true });
  fs.mkdirSync(packDir, { recursive: true });

  var universalToolbar = {
    id: 'universal',
    label: 'Universal',
    items: [
      { id: 'select', icon: 'mouse-pointer', action: 'select' },
      { id: 'pan', icon: 'hand', action: 'pan' },
      { id: 'zoom-in', icon: 'zoom-in', action: 'zoom_in' },
      { id: 'zoom-out', icon: 'zoom-out', action: 'zoom_out' },
      { id: 'undo', icon: 'undo-2', action: 'undo' },
      { id: 'redo', icon: 'redo-2', action: 'redo' },
      { id: 'save', icon: 'save', action: 'save' }
    ]
  };
  var imageToolbar = {
    id: 'image',
    label: 'Image',
    items: [
      { id: 'upload', icon: 'upload', action: 'upload_image' },
      { id: 'crop', icon: 'crop', action: 'crop_image' },
      // Inline SVG should be skipped:
      { id: 'custom', icon: '<svg width="24"><circle/></svg>', action: 'custom' },
      // Unknown name should be flagged but not crash:
      { id: 'bogus', icon: 'fake-not-real-icon', action: 'bogus' }
    ]
  };
  var diagPack = {
    pack_name: 'Diagram Thinking',
    pack_version: '0.1.0',
    toolbars: [
      {
        id: 'shapes',
        items: [
          { id: 'rect', icon: 'square', action: 'rect' },
          { id: 'circle', icon: 'circle', action: 'circle' },
          { id: 'text', icon: 'type', action: 'text' }
        ]
      }
    ]
  };

  fs.writeFileSync(path.join(toolbarDir, 'universal.json'),
                   JSON.stringify(universalToolbar));
  fs.writeFileSync(path.join(toolbarDir, 'image.json'),
                   JSON.stringify(imageToolbar));
  fs.writeFileSync(path.join(packDir, 'diagram-thinking.json'),
                   JSON.stringify(diagPack));

  // Manually orchestrate _extractReferencedNames against the temp dirs.
  // (Easier than monkey-patching the full main() with envvars.)
  var collected = new Set();
  function collectFromFile(p) {
    var data = JSON.parse(fs.readFileSync(p, 'utf8'));
    treeShake._collectIconRefs(data, collected);
  }
  collectFromFile(path.join(toolbarDir, 'universal.json'));
  collectFromFile(path.join(toolbarDir, 'image.json'));
  collectFromFile(path.join(packDir, 'diagram-thinking.json'));

  var found = Array.from(collected).sort();
  var expected = [
    'circle', 'crop', 'fake-not-real-icon', 'hand',
    'mouse-pointer', 'redo-2', 'save', 'square', 'type',
    'undo-2', 'upload', 'zoom-in', 'zoom-out'
  ].sort();
  eq('  scanner extracts all referenced icon names', found, expected);

  // Verify inline SVG was skipped.
  ok('  inline-SVG icon value not collected as a name',
     !collected.has('<svg width="24"><circle/></svg>'));

  // Now verify canonical filtering: real names go into output, unknown names
  // are rejected.
  var canonical = treeShake._loadCanonicalNames();
  var validReferenced = found.filter(function (n) { return canonical.set.has(n); });
  var invalidReferenced = found.filter(function (n) { return !canonical.set.has(n); });

  eq('  invalid name rejected by canonical filter',
     invalidReferenced, ['fake-not-real-icon']);
  ok('  all valid referenced names are in canonical set',
     validReferenced.length === expected.length - 1);

  // Verify the actual SVG bytes for the valid names exist on disk.
  validReferenced.forEach(function (n) {
    var svgPath = path.join(ICON_DIR, n + '.svg');
    ok('  vendored SVG exists for "' + n + '"', fs.existsSync(svgPath));
  });

  // Run the actual main() with no real source files (no-references fallback).
  var fallbackOut = path.join(tmpRoot, 'fallback-out.json');
  var origArgv = process.argv.slice();
  process.argv = ['node', treeShakePath, '--out', fallbackOut, '--quiet'];
  try {
    var payload = treeShake.main();
    ok('  no-references fallback produces empty icons object',
       payload.icon_count === 0
       && payload.mode === 'no-references-found-no-tree-shake-performed');
    ok('  fallback file written', fs.existsSync(fallbackOut));
    var written = JSON.parse(fs.readFileSync(fallbackOut, 'utf8'));
    ok('  fallback file has version field', !!written.version);
    ok('  fallback file is JSON-parseable', typeof written.icons === 'object');
  } finally {
    process.argv = origArgv;
  }

  // Cleanup.
  try { fs.rmSync(tmpRoot, { recursive: true, force: true }); } catch (e) {}
}

function testRuntimeOutputShape() {
  console.log('\n[6] runtime/icon-set.json shape (smoke)');

  var runtimePath = path.resolve(__dirname,
    '../../../runtime/icon-set.json');
  if (!fs.existsSync(runtimePath)) {
    console.log('  SKIP  (runtime/icon-set.json not yet generated; run lucide-tree-shake.js first)');
    return;
  }
  var data = JSON.parse(fs.readFileSync(runtimePath, 'utf8'));
  ok('  has version field', typeof data.version === 'string');
  ok('  has generated_at timestamp',
     typeof data.generated_at === 'string'
     && /\d{4}-\d{2}-\d{2}T/.test(data.generated_at));
  ok('  has icons object', typeof data.icons === 'object');
  ok('  has mode field', typeof data.mode === 'string');
  ok('  icon_count matches icons keys',
     data.icon_count === Object.keys(data.icons).length);
}

// ---- run ------------------------------------------------------------------

(function run() {
  console.log('icon-resolver.js + lucide-tree-shake.js — WP-7.0.3 tests');
  _bootstrapResolver().then(function (seedNames) {
    testKnownNames(seedNames);
    testInlineSvg();
    testUnknownName();
    testIsValidName();
    testTreeShake();
    testRuntimeOutputShape();

    console.log('\n=================================================');
    console.log('  passed: ' + passed + ', failed: ' + failed);
    if (failed > 0) {
      console.log('  failures:');
      failures.forEach(function (f) { console.log('    - ' + f); });
      process.exit(1);
    } else {
      console.log('  all tests passed');
      process.exit(0);
    }
  }).catch(function (err) {
    console.log('FATAL: ' + (err && err.stack ? err.stack : err));
    process.exit(2);
  });
})();
