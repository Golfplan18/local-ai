#!/usr/bin/env node
/* test-macro-engine.js — WP-7.2.2
 *
 * Exercises the linear-only macro execution engine against the §13.2
 * acceptance criterion plus the surrounding shape, variable, and
 * dispatch-error contracts.
 *
 * Run:  node ~/ora/server/static/tests/test-macro-engine.js
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var fs   = require('fs');
var path = require('path');
var vm   = require('vm');

// ---- bootstrap -------------------------------------------------------------

var STATIC_DIR = path.resolve(__dirname, '..');
var TPL_PATH   = path.join(STATIC_DIR, 'prompt-template-engine.js');
var ENGINE_PATH = path.join(STATIC_DIR, 'macro-engine.js');

// Both files attach to `window` and to `module.exports`. Loading the
// template engine through require gives us its module API; we then put
// it on the shared global so macro-engine can find it via _getTemplateEngine.
var OraPromptTemplateEngine = require(TPL_PATH);
global.OraPromptTemplateEngine = OraPromptTemplateEngine;

var OraMacroEngine = require(ENGINE_PATH);

// ---- tiny test harness ------------------------------------------------------

var PASS = 0;
var FAIL = 0;
var failures = [];

function ok(label, cond, detail) {
  if (cond) {
    PASS += 1;
    console.log('  PASS  ' + label);
  } else {
    FAIL += 1;
    failures.push({ label: label, detail: detail });
    console.log('  FAIL  ' + label + (detail ? ' — ' + detail : ''));
  }
}

function eq(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

function section(name) {
  console.log('\n[' + name + ']');
}

// Wrap async test bodies — we serialise them so output is stable.
async function runAll() {

  // ─────────────────────────────────────────────────────────────────────────
  section('extractMacroVariables — variable collection');
  // ─────────────────────────────────────────────────────────────────────────

  {
    var macro = {
      id: 'speech-bubble',
      label: 'Speech bubble',
      steps: [
        { tool: 'shape:speech_bubble', params: { click_to_place: true } },
        { tool: 'text_input', params: { var: 'dialogue', label: 'Dialogue text' } },
        { tool: 'set_bubble_text', params: { text: '{{dialogue}}' } }
      ]
    };
    var vars = OraMacroEngine.extractMacroVariables(macro);
    ok('collects single-var macro', eq(vars, [{ name: 'dialogue' }]),
      JSON.stringify(vars));
  }

  {
    var macro = {
      id: 'multi',
      steps: [
        { tool: 't1', params: { a: '{{first}}', b: 'literal' } },
        { tool: 't2', params: { c: ['{{second}}', '{{first}}'] } },
        { tool: 't3', params: { d: { nested: '{{third|fallback}}' } } }
      ]
    };
    var vars = OraMacroEngine.extractMacroVariables(macro);
    ok('dedupes + walks arrays + nested objects',
      eq(vars, [{ name: 'first' }, { name: 'second' }, { name: 'third' }]),
      JSON.stringify(vars));
  }

  {
    var macro = {
      id: 'no-vars',
      steps: [{ tool: 't', params: { x: 1, y: true, z: null } }]
    };
    var vars = OraMacroEngine.extractMacroVariables(macro);
    ok('returns [] when no tokens reference vars', eq(vars, []),
      JSON.stringify(vars));
  }

  // ─────────────────────────────────────────────────────────────────────────
  section('runMacro — §13.2 acceptance: 3-step linear execution');
  // ─────────────────────────────────────────────────────────────────────────

  {
    var order = [];
    var toolRegistry = {
      'shape:rect':       function (p) { order.push('rect:'   + JSON.stringify(p));   return 'r'; },
      'text_input':       function (p) { order.push('text:'   + JSON.stringify(p));   return 't'; },
      'set_text':         function (p) { order.push('settxt:' + JSON.stringify(p));   return 's'; }
    };
    var macro = {
      id: 'three-step',
      steps: [
        { tool: 'shape:rect', params: { w: 100 } },
        { tool: 'text_input', params: { label: '{{prompt_label}}' } },
        { tool: 'set_text',   params: { value: '{{value}}' } }
      ]
    };
    var result = await OraMacroEngine.runMacro(macro,
      { prompt_label: 'Enter text', value: 'hello' },
      { toolRegistry: toolRegistry });
    ok('success === true',                     result.success === true,
      JSON.stringify(result));
    ok('completedSteps === 3',                 result.completedSteps === 3,
      'got ' + result.completedSteps);
    ok('steps ran in declared order',
      eq(order, [
        'rect:{"w":100}',
        'text:{"label":"Enter text"}',
        'settxt:{"value":"hello"}'
      ]),
      JSON.stringify(order));
    ok('results carry per-step return values',
      result.results.length === 3
        && result.results[0].value === 'r'
        && result.results[1].value === 't'
        && result.results[2].value === 's',
      JSON.stringify(result.results));
  }

  // ─────────────────────────────────────────────────────────────────────────
  section('runMacro — §13.2 acceptance: step 2 fails → halt + error surface');
  // ─────────────────────────────────────────────────────────────────────────

  {
    var order = [];
    var toolRegistry = {
      'a': function () { order.push('a'); return 'A'; },
      'b': function () { order.push('b'); throw new Error('intentional failure in step 2'); },
      'c': function () { order.push('c'); return 'C'; }
    };
    var macro = {
      id: 'fail-mid',
      steps: [
        { tool: 'a', params: {} },
        { tool: 'b', params: {} },
        { tool: 'c', params: {} }
      ]
    };
    var result = await OraMacroEngine.runMacro(macro, {}, { toolRegistry: toolRegistry });
    ok('success === false on step failure',     result.success === false,
      JSON.stringify(result));
    ok('completedSteps === 1 (only step 0 finished)',
      result.completedSteps === 1, 'got ' + result.completedSteps);
    ok('step 3 was NOT invoked',                eq(order, ['a', 'b']),
      JSON.stringify(order));
    ok('error.stepIndex === 1',                 result.error.stepIndex === 1,
      JSON.stringify(result.error));
    ok('error.code === step-failed',            result.error.code === 'step-failed',
      result.error.code);
    ok('error.message names the failing step',
      /Step 1 \(tool:b\) failed/.test(result.error.message),
      result.error.message);
    ok('error.cause carries the underlying Error',
      result.error.cause instanceof Error
        && result.error.cause.message === 'intentional failure in step 2',
      result.error.cause && result.error.cause.message);
    ok('error.step references the offending step shape',
      result.error.step && result.error.step.tool === 'b',
      JSON.stringify(result.error.step));
  }

  // ─────────────────────────────────────────────────────────────────────────
  section('runMacro — async handler failure halts cleanly');
  // ─────────────────────────────────────────────────────────────────────────

  {
    var toolRegistry = {
      'a': async function () { return 'A'; },
      'b': async function () { throw new Error('async boom'); },
      'c': async function () { return 'C'; }
    };
    var macro = {
      id: 'async-fail',
      steps: [
        { tool: 'a', params: {} },
        { tool: 'b', params: {} },
        { tool: 'c', params: {} }
      ]
    };
    var result = await OraMacroEngine.runMacro(macro, {}, { toolRegistry: toolRegistry });
    ok('async failure produces success === false', result.success === false);
    ok('async failure stepIndex === 1',            result.error.stepIndex === 1);
    ok('async failure code === step-failed',       result.error.code === 'step-failed');
    ok('async failure cause.message preserved',
      result.error.cause && result.error.cause.message === 'async boom',
      result.error.cause && result.error.cause.message);
  }

  // ─────────────────────────────────────────────────────────────────────────
  section('runMacro — capability dispatch');
  // ─────────────────────────────────────────────────────────────────────────

  {
    var calls = [];
    var capabilityRegistry = {
      'image_generates': function (p, ctx, meta) {
        calls.push({ p: p, kind: meta.kind, slot: meta.slotId });
        return { ok: true };
      }
    };
    var macro = {
      id: 'cap',
      steps: [{ capability: 'image_generates', params: { prompt: '{{p}}' } }]
    };
    var result = await OraMacroEngine.runMacro(macro,
      { p: 'a fox' },
      { capabilityRegistry: capabilityRegistry });
    ok('capability step succeeds',  result.success === true);
    ok('capability handler received rendered params',
      calls.length === 1 && calls[0].p.prompt === 'a fox',
      JSON.stringify(calls));
    ok('handler meta.kind === capability',
      calls[0].kind === 'capability' && calls[0].slot === 'image_generates',
      JSON.stringify(calls));
  }

  // ─────────────────────────────────────────────────────────────────────────
  section('runMacro — unknown tool / capability');
  // ─────────────────────────────────────────────────────────────────────────

  {
    var result = await OraMacroEngine.runMacro(
      { id: 'm', steps: [{ tool: 'never_registered', params: {} }] },
      {}, { toolRegistry: {} });
    ok('unknown tool → unknown-tool code',  result.error.code === 'unknown-tool',
      result.error.code);
    ok('unknown tool → success false + completedSteps 0',
      result.success === false && result.completedSteps === 0,
      JSON.stringify(result));
  }

  {
    var result = await OraMacroEngine.runMacro(
      { id: 'm', steps: [{ capability: 'no_such', params: {} }] },
      {}, { capabilityRegistry: {} });
    ok('unknown capability → unknown-capability code',
      result.error.code === 'unknown-capability', result.error.code);
  }

  // ─────────────────────────────────────────────────────────────────────────
  section('runMacro — variable prompting');
  // ─────────────────────────────────────────────────────────────────────────

  {
    var promptArgs;
    var result = await OraMacroEngine.runMacro(
      { id: 'm', steps: [{ tool: 't', params: { a: '{{x}}', b: '{{y}}' } }] },
      { x: 'pre' },
      {
        toolRegistry: { t: function (p) { return p; } },
        promptForVariables: function (missing, macro) {
          promptArgs = missing.map(function (m) { return m.name; });
          return { y: 'asked' };
        }
      });
    ok('prompter called with only missing vars',  eq(promptArgs, ['y']),
      JSON.stringify(promptArgs));
    ok('rendered params merge prefilled + prompted',
      result.success === true
        && result.results[0].value.a === 'pre'
        && result.results[0].value.b === 'asked',
      JSON.stringify(result.results));
  }

  {
    var result = await OraMacroEngine.runMacro(
      { id: 'm', steps: [{ tool: 't', params: { a: '{{x}}' } }] },
      {},
      { toolRegistry: { t: function () {} } });
    ok('no prompter + missing var → missing-variable',
      result.error.code === 'missing-variable',
      JSON.stringify(result.error));
    ok('no prompter halt before any step ran',
      result.completedSteps === 0 && result.error.stepIndex === -1,
      JSON.stringify(result.error));
  }

  {
    var result = await OraMacroEngine.runMacro(
      { id: 'm', steps: [{ tool: 't', params: { a: '{{x}}' } }] },
      {},
      {
        toolRegistry: { t: function () {} },
        promptForVariables: function () { return null; }   // user cancelled
      });
    ok('prompter returns null → cancelled code',  result.error.code === 'cancelled',
      JSON.stringify(result.error));
  }

  // ─────────────────────────────────────────────────────────────────────────
  section('runMacro — malformed macro / step');
  // ─────────────────────────────────────────────────────────────────────────

  {
    var result = await OraMacroEngine.runMacro(null, {}, {});
    ok('null macro → malformed-macro',  result.error.code === 'malformed-macro');
  }

  {
    var result = await OraMacroEngine.runMacro({ id: 'm' }, {}, {});
    ok('missing steps[] → malformed-macro',
      result.error.code === 'malformed-macro'
      && /steps/.test(result.error.message),
      result.error.message);
  }

  {
    var result = await OraMacroEngine.runMacro(
      { id: 'm', steps: [{ tool: 't', capability: 'c' }] }, {}, {});
    ok('step with both tool+capability → malformed-step',
      result.error.code === 'malformed-step',
      JSON.stringify(result.error));
  }

  {
    var result = await OraMacroEngine.runMacro(
      { id: 'm', steps: [{}] }, {}, {});
    ok('step with neither tool nor capability → malformed-step',
      result.error.code === 'malformed-step', result.error.code);
  }

  {
    var result = await OraMacroEngine.runMacro(
      { id: 'm', steps: [] }, {}, {});
    ok('zero-step macro → malformed-macro',
      result.error.code === 'malformed-macro'
      && /zero steps/.test(result.error.message),
      result.error.message);
  }

  // ─────────────────────────────────────────────────────────────────────────
  section('extractMacroVariables — input validation');
  // ─────────────────────────────────────────────────────────────────────────

  {
    var threw = false;
    try { OraMacroEngine.extractMacroVariables(null); }
    catch (e) { threw = (e.code === 'malformed-macro'); }
    ok('null macro throws malformed-macro', threw);
  }

  // ---- summary --------------------------------------------------------------

  console.log('\n──────────────────────────────────────────');
  console.log('Pass: ' + PASS + '   Fail: ' + FAIL);
  if (FAIL > 0) {
    console.log('\nFailures:');
    failures.forEach(function (f) {
      console.log('  • ' + f.label + (f.detail ? '  [' + f.detail + ']' : ''));
    });
    process.exit(1);
  }
  process.exit(0);
}

runAll().catch(function (e) {
  console.error('test runner crashed:', e);
  process.exit(2);
});
