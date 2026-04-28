/**
 * ora-visual-compiler / tests/standalone-c4.js
 *
 * Node-runnable regression tests for the C4 renderer (WP-1.2d).
 * Uses a minimal `window` shim — no jsdom required, no network access.
 *
 * Run:
 *   node tests/standalone-c4.js
 *
 * Exit code 0 on all-pass; non-zero on any failure.
 *
 * Coverage:
 *   Valid specs (>=6): 3 context + 3 container including nested containers,
 *     external systems, multiple relationships, autolayout variants.
 *   Invalid specs (>=3): forward-reference unresolved ref, malformed DSL,
 *     level mismatch (level=context with only a container view).
 *   SVG sanity checks: semantic classes + stable element IDs present.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

// ── Test harness ────────────────────────────────────────────────────────────
let PASS = 0;
let FAIL = 0;
const FAILURES = [];

function assert(cond, label) {
  if (cond) { PASS++; return; }
  FAIL++;
  FAILURES.push(label);
  console.error('  FAIL: ' + label);
}

function assertEqual(actual, expected, label) {
  const ok = actual === expected;
  if (!ok) {
    console.error('    expected: ' + JSON.stringify(expected));
    console.error('    actual:   ' + JSON.stringify(actual));
  }
  assert(ok, label);
}

// ── Load compiler modules into a sandboxed `window` ─────────────────────────
function loadCompiler() {
  const sandbox = { window: {}, console: console };
  sandbox.global = sandbox;
  vm.createContext(sandbox);
  const ROOT = path.resolve(__dirname, '..');
  const files = [
    'errors.js',
    'validator.js',
    'renderers/stub.js',
    'dispatcher.js',
    'index.js',
    'vendor/structurizr-mini/parser.js',
    'vendor/structurizr-mini/renderer.js',
    'renderers/c4.js',
  ];
  files.forEach(function (f) {
    const code = fs.readFileSync(path.join(ROOT, f), 'utf8');
    vm.runInContext(code, sandbox, { filename: f });
  });
  return sandbox.window.OraVisualCompiler;
}

const C = loadCompiler();

// ── Envelope builders ────────────────────────────────────────────────────────
function envelope(level, dsl, extras) {
  const e = {
    schema_version: '0.2',
    id: 'fig-c4-test',
    type: 'c4',
    mode_context: 'testing',
    relation_to_prose: 'integrated',
    spec: { level: level, dsl: dsl },
    semantic_description: {
      level_1_elemental: 'C4 test diagram.',
      level_2_statistical: 'N/A',
      level_3_perceptual: 'N/A',
      level_4_contextual: null,
      short_alt: 'C4 test',
      data_table_fallback: null,
    },
    title: 'Test C4',
  };
  Object.assign(e, extras || {});
  return e;
}

// ── Semantic assertions ─────────────────────────────────────────────────────
function assertValidRender(res, label) {
  assertEqual(res.errors.length, 0, label + ' — no errors');
  assert(res.svg && res.svg.indexOf('<svg') === 0, label + ' — SVG present');
  assert(res.svg.indexOf('class="ora-visual ora-visual--c4') !== -1,
    label + ' — has ora-visual--c4 root class');
  assert(res.svg.indexOf('role="img"') !== -1, label + ' — role=img');
  assert(res.svg.indexOf('aria-label=') !== -1, label + ' — aria-label set');
}

function assertHasIds(res, ids, label) {
  ids.forEach(function (id) {
    assert(res.svg.indexOf('id="' + id + '"') !== -1,
      label + ' — element id ' + id + ' present');
  });
}

function assertErrorCode(res, code, label) {
  assert(res.svg === '', label + ' — empty SVG on error');
  const hit = res.errors.some(function (e) { return e.code === code; });
  if (!hit) {
    console.error('    got errors: ' + JSON.stringify(res.errors));
  }
  assert(hit, label + ' — error code ' + code);
}

// ─────────────────────────────────────────────────────────────────────────────
// VALID CONTEXT (3+)
// ─────────────────────────────────────────────────────────────────────────────

function testContextMinimal() {
  console.log('test: context — minimal');
  const dsl = [
    'workspace {',
    '  model {',
    '    u = person "User" "A human user"',
    '    ss = softwareSystem "System" "The core system"',
    '    u -> ss "Uses"',
    '  }',
    '  views {',
    '    systemContext ss "Context" {',
    '      include *',
    '      autolayout lr',
    '    }',
    '  }',
    '}',
  ].join('\n');
  const res = C.compile(envelope('context', dsl));
  assertValidRender(res, 'context minimal');
  assertHasIds(res, ['c4-person-u', 'c4-system-ss'], 'context minimal');
  assert(res.svg.indexOf('ora-visual__c4-person') !== -1,
    'context minimal — person class');
  assert(res.svg.indexOf('ora-visual__c4-relationship') !== -1,
    'context minimal — relationship class');
  assert(res.svg.indexOf('Uses') !== -1,
    'context minimal — relationship label rendered');
}

function testContextWithExternalSystem() {
  console.log('test: context — external system');
  const dsl = [
    'workspace "Big Bank" "Example workspace" {',
    '  model {',
    '    u = person "Customer" "A bank customer"',
    '    ss = softwareSystem "Internet Banking System" "Core banking"',
    '    ex = softwareSystem "Mainframe" "Legacy mainframe" {',
    '      tags "External"',
    '    }',
    '    u -> ss "Uses"',
    '    ss -> ex "Reads from"',
    '  }',
    '  views {',
    '    systemContext ss "SystemContext" {',
    '      include *',
    '      autolayout lr',
    '    }',
    '  }',
    '}',
  ].join('\n');
  const res = C.compile(envelope('context', dsl));
  assertValidRender(res, 'context external');
  assert(res.svg.indexOf('ora-visual__c4-system--external') !== -1,
    'context external — external class applied');
  assertHasIds(res, ['c4-system-ss', 'c4-system-ex', 'c4-person-u'],
    'context external');
}

function testContextMultiplePeople() {
  console.log('test: context — multiple people + relationships');
  const dsl = [
    'workspace {',
    '  model {',
    '    admin = person "Admin" "System admin"',
    '    customer = person "Customer" "End user"',
    '    ss = softwareSystem "Portal" "Main portal"',
    '    notify = softwareSystem "Notifier" "Notification service" {',
    '      tags "External"',
    '    }',
    '    admin -> ss "Manages"',
    '    customer -> ss "Uses"',
    '    ss -> notify "Sends alerts via"',
    '  }',
    '  views {',
    '    systemContext ss "Ctx" {',
    '      include *',
    '      autolayout tb',
    '    }',
    '  }',
    '}',
  ].join('\n');
  const res = C.compile(envelope('context', dsl));
  assertValidRender(res, 'context multi-people');
  assertHasIds(res,
    ['c4-person-admin', 'c4-person-customer', 'c4-system-ss', 'c4-system-notify'],
    'context multi-people');
  // Three relationships → three relationship groups.
  const relCount = (res.svg.match(/ora-visual__c4-relationship"/g) || []).length;
  assert(relCount === 3, 'context multi-people — 3 relationship groups');
  assert(res.svg.indexOf('ora-visual--c4-context') !== -1,
    'context multi-people — context level class');
}

// ─────────────────────────────────────────────────────────────────────────────
// VALID CONTAINER (3+)
// ─────────────────────────────────────────────────────────────────────────────

function testContainerNested() {
  console.log('test: container — nested containers');
  const dsl = [
    'workspace {',
    '  model {',
    '    u = person "User" "A user"',
    '    ss = softwareSystem "App" "Web app" {',
    '      web = container "Web App" "Browser UI" "React"',
    '      api = container "API" "HTTP API" "Node.js"',
    '      db = container "DB" "Relational store" "Postgres"',
    '      web -> api "Calls"',
    '      api -> db "Queries"',
    '    }',
    '    u -> web "Browses"',
    '  }',
    '  views {',
    '    container ss "Containers" {',
    '      include *',
    '      autolayout lr',
    '    }',
    '  }',
    '}',
  ].join('\n');
  const res = C.compile(envelope('container', dsl));
  assertValidRender(res, 'container nested');
  assertHasIds(res,
    ['c4-container-web', 'c4-container-api', 'c4-container-db'],
    'container nested');
  assert(res.svg.indexOf('ora-visual--c4-container') !== -1,
    'container nested — container level class');
  assert(res.svg.indexOf('[React]') !== -1,
    'container nested — technology label rendered');
  assert(res.svg.indexOf('Calls') !== -1 && res.svg.indexOf('Queries') !== -1,
    'container nested — relationship labels rendered');
}

function testContainerWithPersonNeighbour() {
  console.log('test: container — with person neighbour');
  const dsl = [
    'workspace {',
    '  model {',
    '    u = person "Customer" "Customer"',
    '    ss = softwareSystem "Shop" "E-commerce" {',
    '      ui = container "Storefront" "Public site" "Next.js"',
    '      api = container "API" "REST API" "Go"',
    '      ui -> api "Calls"',
    '    }',
    '    u -> ui "Shops on"',
    '  }',
    '  views {',
    '    container ss "Containers" {',
    '      include *',
    '      autolayout tb',
    '    }',
    '  }',
    '}',
  ].join('\n');
  const res = C.compile(envelope('container', dsl));
  assertValidRender(res, 'container with person');
  assertHasIds(res,
    ['c4-person-u', 'c4-container-ui', 'c4-container-api'],
    'container with person');
  // With autolayout tb the rows should still contain all three shapes.
  const relCount = (res.svg.match(/ora-visual__c4-relationship"/g) || []).length;
  assert(relCount === 2, 'container with person — 2 relationships visible');
}

function testContainerWithExternalSystem() {
  console.log('test: container — external system neighbour');
  const dsl = [
    'workspace {',
    '  model {',
    '    ss = softwareSystem "Core" "Core" {',
    '      api = container "API" "HTTP" "Python"',
    '      worker = container "Worker" "Async" "Go"',
    '      api -> worker "Enqueues"',
    '    }',
    '    ext = softwareSystem "PaymentProvider" "Stripe-like" {',
    '      tags "External"',
    '    }',
    '    api -> ext "Charges via"',
    '  }',
    '  views {',
    '    container ss "Containers" {',
    '      include *',
    '      autolayout lr',
    '    }',
    '  }',
    '}',
  ].join('\n');
  const res = C.compile(envelope('container', dsl));
  assertValidRender(res, 'container with external');
  assertHasIds(res,
    ['c4-container-api', 'c4-container-worker', 'c4-system-ext'],
    'container with external');
  assert(res.svg.indexOf('ora-visual__c4-system--external') !== -1,
    'container with external — external class on neighbour system');
}

// Extra valid — synthesized view fallback.
function testContextSynthesizedView() {
  console.log('test: context — no matching view, synthesized fallback');
  const dsl = [
    'workspace {',
    '  model {',
    '    u = person "U" "User"',
    '    ss = softwareSystem "S" "Sys"',
    '    u -> ss "Uses"',
    '  }',
    '}', // no views block at all
  ].join('\n');
  const res = C.compile(envelope('context', dsl));
  assertValidRender(res, 'context synthesized view');
  assertHasIds(res, ['c4-person-u', 'c4-system-ss'], 'context synthesized view');
}

// ─────────────────────────────────────────────────────────────────────────────
// INVALID
// ─────────────────────────────────────────────────────────────────────────────

function testInvalidForwardRef() {
  console.log('test: invalid — forward reference (unresolved relationship id)');
  const dsl = [
    'workspace {',
    '  model {',
    '    u = person "User" "U"',
    '    u -> ghost "Uses"', // ghost never declared
    '  }',
    '}',
  ].join('\n');
  const res = C.compile(envelope('context', dsl));
  assertErrorCode(res, 'E_UNRESOLVED_REF', 'invalid forward-ref');
}

function testInvalidMalformedDsl() {
  console.log('test: invalid — malformed DSL (missing closing brace)');
  const dsl = [
    'workspace {',
    '  model {',
    '    u = person "User" "U"',
    // deliberately no closing braces
  ].join('\n');
  const res = C.compile(envelope('context', dsl));
  assertErrorCode(res, 'E_DSL_PARSE', 'invalid malformed DSL');
}

function testInvalidLevelMismatch() {
  console.log('test: invalid — level=context but only a container view present');
  const dsl = [
    'workspace {',
    '  model {',
    '    u = person "User" "U"',
    '    ss = softwareSystem "S" "Sys" {',
    '      c = container "C" "Thing" "Tech"',
    '    }',
    '    u -> c "Uses"',
    '  }',
    '  views {',
    '    container ss "Containers" {',
    '      include *',
    '      autolayout lr',
    '    }',
    '  }',
    '}',
  ].join('\n');
  const res = C.compile(envelope('context', dsl));
  assertErrorCode(res, 'E_SCHEMA_INVALID', 'invalid level mismatch');
}

// Extra invalid — bad token.
function testInvalidBadToken() {
  console.log('test: invalid — bad token at top level');
  const dsl = 'notAWorkspace { model { u = person "U" "U" } }';
  const res = C.compile(envelope('context', dsl));
  assertErrorCode(res, 'E_DSL_PARSE', 'invalid bad top-level keyword');
}

// ─────────────────────────────────────────────────────────────────────────────
// SVG stability spot-checks
// ─────────────────────────────────────────────────────────────────────────────

function testSvgSemanticClassesOnly() {
  console.log('test: svg — no inline style="..."');
  const dsl = [
    'workspace { model {',
    '  u = person "U" "U"',
    '  ss = softwareSystem "S" "Sys"',
    '  u -> ss "Uses"',
    '} views { systemContext ss "C" { include * autolayout lr } } }',
  ].join('\n');
  const res = C.compile(envelope('context', dsl));
  assertValidRender(res, 'svg semantic-only');
  assert(res.svg.indexOf(' style="') === -1,
    'svg semantic-only — no inline style attributes');
}

function testSvgStableRelationshipIds() {
  console.log('test: svg — relationship IDs are stable across renders');
  const dsl = [
    'workspace { model {',
    '  u = person "U" "U"',
    '  ss = softwareSystem "S" "Sys"',
    '  u -> ss "Uses"',
    '} views { systemContext ss "C" { include * autolayout lr } } }',
  ].join('\n');
  const a = C.compile(envelope('context', dsl));
  const b = C.compile(envelope('context', dsl));
  assertEqual(a.svg, b.svg,
    'svg stable — two compiles of same DSL produce identical SVG');
  assert(a.svg.indexOf('id="c4-relationship-u-ss-0"') !== -1,
    'svg stable — relationship id present');
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared cases from tests/cases/test-c4.js — verify they round-trip identically.
// ─────────────────────────────────────────────────────────────────────────────
function testSharedCasesFile() {
  console.log('test: shared cases file — runs against C.compile');
  const { CASES } = require('./cases/test-c4.js');
  assert(CASES.length >= 9, 'shared cases — at least 9 cases present');
  const okCount = CASES.filter(function (c) { return c.expect === 'ok'; }).length;
  const errCount = CASES.filter(function (c) { return c.expect === 'error'; }).length;
  assert(okCount >= 6, 'shared cases — at least 6 valid cases');
  assert(errCount >= 3, 'shared cases — at least 3 invalid cases');
  CASES.forEach(function (c) {
    const res = C.compile(envelope(c.level, c.dsl));
    if (c.expect === 'ok') {
      assertEqual(res.errors.length, 0,
        'shared case ' + c.name + ' — expected success');
      assert(res.svg.length > 0,
        'shared case ' + c.name + ' — non-empty SVG');
    } else {
      assertEqual(res.errors.length > 0, true,
        'shared case ' + c.name + ' — expected error');
      assert(res.errors.some(function (e) { return e.code === c.expectCode; }),
        'shared case ' + c.name + ' — code ' + c.expectCode);
    }
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Run
// ─────────────────────────────────────────────────────────────────────────────
[
  testContextMinimal,
  testContextWithExternalSystem,
  testContextMultiplePeople,
  testContainerNested,
  testContainerWithPersonNeighbour,
  testContainerWithExternalSystem,
  testContextSynthesizedView,
  testInvalidForwardRef,
  testInvalidMalformedDsl,
  testInvalidLevelMismatch,
  testInvalidBadToken,
  testSvgSemanticClassesOnly,
  testSvgStableRelationshipIds,
  testSharedCasesFile,
].forEach(function (fn) {
  try {
    fn();
  } catch (err) {
    FAIL++;
    FAILURES.push(fn.name + ' threw: ' + err.stack);
    console.error('  THROWN in ' + fn.name + ': ' + err.stack);
  }
});

console.log('\n' + (FAIL === 0 ? 'PASS' : 'FAIL') +
  ' ' + PASS + '/' + (PASS + FAIL) + ' assertions');
if (FAIL > 0) {
  console.log('Failures:');
  FAILURES.forEach(function (f) { console.log(' - ' + f); });
  process.exit(1);
}
process.exit(0);
