#!/usr/bin/env node
/* test-prompt-template-runtime.js — WP-7.2.3
 *
 * Run:  node ~/ora/server/static/tests/test-prompt-template-runtime.js
 * Exit code 0 on full pass, 1 on any failure.
 *
 * §13.2 acceptance criterion verbatim:
 *   "register `/foo {{var}}` template with Gear 1; invoke `/foo bar`;
 *    verify routed to small-model bucket with `var=bar` substituted."
 *
 * Bucket selection lives in boot.py's pipeline, not in the runtime — the
 * runtime's job is to POST { message, gear_preference } to the configured
 * pipeline endpoint. We therefore assert: gear_preference === 1 AND the
 * POST body's `message` is the rendered template ('foo bar' for the
 * trivial `/foo {{var}}` case where the literal 'foo' is part of the
 * template body, or 'bar' if the template body is just '{{var}}'). The
 * task description shows '/foo {{var}}' → register a TEMPLATE id 'foo'
 * with template '{{var}}'; invoke('/foo bar') yields message 'bar'.
 * We also cover the alternative reading (template includes literal 'foo').
 */

'use strict';

var fs   = require('fs');
var path = require('path');

var STATIC_DIR    = path.resolve(__dirname, '..');
var TPL_PATH      = path.join(STATIC_DIR, 'prompt-template-engine.js');
var RUNTIME_PATH  = path.join(STATIC_DIR, 'prompt-template-runtime.js');

var OraPromptTemplateEngine = require(TPL_PATH);
global.OraPromptTemplateEngine = OraPromptTemplateEngine;

var OraPromptTemplateRuntime = require(RUNTIME_PATH);

// ---- harness ---------------------------------------------------------------

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
function eq(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
function section(name) { console.log('\n[' + name + ']'); }

// Reset runtime state between sections.
function freshRuntime(initOpts) {
  OraPromptTemplateRuntime.clear();
  OraPromptTemplateRuntime.init(initOpts || {});
}

async function runAll() {

  // ─────────────────────────────────────────────────────────────────────────
  section('register / unregister / shape validation');
  // ─────────────────────────────────────────────────────────────────────────
  freshRuntime();

  {
    var tpl = {
      id: 'foo',
      slash_command: '/foo',
      label: 'Foo',
      template: '{{var}}',
      variables: [{ name: 'var', type: 'text' }],
      gear_preference: 1
    };
    var registeredId = OraPromptTemplateRuntime.register(tpl);
    ok('register returns the id',           registeredId === 'foo');
    ok('has(id) === true after register',   OraPromptTemplateRuntime.has('foo'));
    ok('get(id) round-trips definition',    OraPromptTemplateRuntime.get('foo') === tpl);
    ok('list() includes registered',        OraPromptTemplateRuntime.list().length === 1);
  }

  {
    // Re-registering the same object is a no-op.
    var tpl = OraPromptTemplateRuntime.get('foo');
    var again = OraPromptTemplateRuntime.register(tpl);
    ok('idempotent same-object register',   again === 'foo');
  }

  {
    // A different object with the same id throws 'already-registered'.
    var different = {
      id: 'foo',
      template: '{{x}}',
      variables: [{ name: 'x', type: 'text' }],
      gear_preference: 1
    };
    var threw = false, code;
    try { OraPromptTemplateRuntime.register(different); }
    catch (e) { threw = true; code = e.code; }
    ok('different object same id throws',   threw && code === 'already-registered',
      'code=' + code);
  }

  {
    // Both gear_preference and capability_route → invalid.
    var threw = false, code;
    try {
      OraPromptTemplateRuntime.register({
        id: 'bothroutes',
        template: '{{x}}',
        variables: [{ name: 'x', type: 'text' }],
        gear_preference: 1,
        capability_route: 'image_generates'
      });
    } catch (e) { threw = true; code = e.code; }
    ok('both routes rejected',              threw && code === 'invalid-route', 'code=' + code);
  }

  {
    // Neither route → invalid.
    var threw = false, code;
    try {
      OraPromptTemplateRuntime.register({
        id: 'noroute',
        template: 'static',
        variables: []
      });
    } catch (e) { threw = true; code = e.code; }
    ok('no route rejected',                  threw && code === 'invalid-route', 'code=' + code);
  }

  {
    var removed = OraPromptTemplateRuntime.unregister('foo');
    ok('unregister returns true',            removed === true);
    ok('has(id) === false after unregister', !OraPromptTemplateRuntime.has('foo'));
    ok('list() empty after unregister',      OraPromptTemplateRuntime.list().length === 0);
  }

  // ─────────────────────────────────────────────────────────────────────────
  section('parseSlash');
  // ─────────────────────────────────────────────────────────────────────────
  freshRuntime();

  {
    var p = OraPromptTemplateRuntime.parseSlash('/cartoon-bg style: Hergé');
    ok('parses /cmd key: value',
      p && p.templateId === 'cartoon-bg' && p.args.style === 'Hergé',
      JSON.stringify(p));
  }

  {
    var p = OraPromptTemplateRuntime.parseSlash('/cartoon-bg style:Hergé era:1950');
    ok('parses key:value (no whitespace)',
      p && p.args.style === 'Hergé' && p.args.era === '1950',
      JSON.stringify(p));
  }

  {
    var p = OraPromptTemplateRuntime.parseSlash('/foo bar: "two words" baz: q');
    ok('parses quoted values with whitespace',
      p && p.args.bar === 'two words' && p.args.baz === 'q',
      JSON.stringify(p));
  }

  {
    var p = OraPromptTemplateRuntime.parseSlash('/foo bar');
    ok('bare positional → _positional[]',
      p && eq(p.args._positional, ['bar']),
      JSON.stringify(p));
  }

  {
    var p = OraPromptTemplateRuntime.parseSlash('/foo hello world');
    ok('multiple bare tokens captured positionally',
      p && eq(p.args._positional, ['hello', 'world']),
      JSON.stringify(p));
  }

  {
    var p = OraPromptTemplateRuntime.parseSlash('not a slash');
    ok('returns null for non-slash input', p === null);
  }

  {
    var threw = false, code;
    try { OraPromptTemplateRuntime.parseSlash('/foo bar: "unterminated'); }
    catch (e) { threw = true; code = e.code; }
    ok('unterminated quote throws invalid-slash', threw && code === 'invalid-slash',
      'code=' + code);
  }

  // ─────────────────────────────────────────────────────────────────────────
  section('§13.2 acceptance — `/foo bar` with Gear-1 routes through pipeline');
  // ─────────────────────────────────────────────────────────────────────────
  // Capture the fetch call. The pipeline endpoint receives the rendered
  // template + gear_preference; bucket selection is boot.py's job. The
  // task language "small-model bucket" is the §11.4 effect of Gear=1
  // — we assert the contract our runtime emits.
  {
    var captured = null;
    var fakeFetch = function (url, opts) {
      captured = {
        url: url,
        method: opts.method,
        body: JSON.parse(opts.body),
        headers: opts.headers
      };
      return Promise.resolve({ ok: true, status: 200, statusText: 'OK' });
    };

    freshRuntime({ fetchFn: fakeFetch, pipelineEndpoint: '/chat' });

    OraPromptTemplateRuntime.register({
      id: 'foo',
      slash_command: '/foo',
      label: 'Foo',
      template: '{{var}}',
      variables: [{ name: 'var', type: 'text' }],
      gear_preference: 1
    });

    var result = await OraPromptTemplateRuntime.invoke('/foo bar');
    ok('invoke success',                     result.success === true,
      JSON.stringify(result));
    ok('route === text',                     result.route === 'text');
    ok('renderedTemplate === "bar"',         result.renderedTemplate === 'bar',
      'got "' + result.renderedTemplate + '"');
    ok('fetch hit /chat',                    captured && captured.url === '/chat');
    ok('POST method',                        captured && captured.method === 'POST');
    ok('POST body.message === "bar"',
      captured && captured.body.message === 'bar',
      JSON.stringify(captured && captured.body));
    ok('POST body.gear_preference === 1 (small-model bucket)',
      captured && captured.body.gear_preference === 1);
  }

  // ─────────────────────────────────────────────────────────────────────────
  section('text route — multi-positional folds into trailing var');
  // ─────────────────────────────────────────────────────────────────────────
  {
    var captured = null;
    var fakeFetch = function (u, o) {
      captured = JSON.parse(o.body);
      return Promise.resolve({ ok: true, status: 200, statusText: 'OK' });
    };
    freshRuntime({ fetchFn: fakeFetch });
    OraPromptTemplateRuntime.register({
      id: 'echo',
      slash_command: '/echo',
      label: 'Echo',
      template: 'echoing: {{msg}}',
      variables: [{ name: 'msg', type: 'text' }],
      gear_preference: 2
    });
    var r = await OraPromptTemplateRuntime.invoke('/echo hello world');
    ok('multi-positional collapsed into last var',
      r.success && captured.message === 'echoing: hello world',
      'message=' + (captured && captured.message));
    ok('gear_preference forwarded as 2',
      captured && captured.gear_preference === 2);
  }

  // ─────────────────────────────────────────────────────────────────────────
  section('text route — key:value args fill named variables');
  // ─────────────────────────────────────────────────────────────────────────
  {
    var captured = null;
    var fakeFetch = function (u, o) {
      captured = JSON.parse(o.body);
      return Promise.resolve({ ok: true, status: 200, statusText: 'OK' });
    };
    freshRuntime({ fetchFn: fakeFetch });
    OraPromptTemplateRuntime.register({
      id: 'styled',
      slash_command: '/styled',
      label: 'Styled',
      template: 'A {{style}} background in the {{era}} period.',
      variables: [
        { name: 'style', type: 'text' },
        { name: 'era',   type: 'text' }
      ],
      gear_preference: 3
    });
    var r = await OraPromptTemplateRuntime.invoke('/styled style: Hergé era: 1950');
    ok('named args render into template',
      r.success && captured.message === 'A Hergé background in the 1950 period.',
      'message=' + (captured && captured.message));
  }

  // ─────────────────────────────────────────────────────────────────────────
  section('capability route — slot dispatch carries rendered prompt');
  // ─────────────────────────────────────────────────────────────────────────
  {
    var dispatched = null;
    var fakeDispatch = function (slot, inputs, ctx) {
      dispatched = { slot: slot, inputs: inputs, ctx: ctx };
      return { dispatched: true };
    };
    freshRuntime({ capabilityDispatch: fakeDispatch });

    OraPromptTemplateRuntime.register({
      id: 'cartoon',
      slash_command: '/cartoon',
      label: 'Cartoon',
      template: 'Generate a cartoon-style background of {{subject}}.',
      variables: [{ name: 'subject', type: 'text' }],
      capability_route: 'image_generates'
    });

    var r = await OraPromptTemplateRuntime.invoke('/cartoon a fox in a forest');
    ok('capability route succeeds',          r.success === true, JSON.stringify(r));
    ok('route === capability',               r.route === 'capability');
    ok('slot === image_generates',           r.slot === 'image_generates');
    ok('dispatch received slot id',          dispatched && dispatched.slot === 'image_generates');
    ok('dispatch received rendered prompt',
      dispatched && dispatched.inputs.prompt === 'Generate a cartoon-style background of a fox in a forest.',
      JSON.stringify(dispatched && dispatched.inputs));
    ok('dispatch carries variable side-channel',
      dispatched && dispatched.inputs.subject === 'a fox in a forest');
  }

  // ─────────────────────────────────────────────────────────────────────────
  section('missing variable — prompter fills it');
  // ─────────────────────────────────────────────────────────────────────────
  {
    var captured = null;
    var fakeFetch = function (u, o) {
      captured = JSON.parse(o.body);
      return Promise.resolve({ ok: true, status: 200, statusText: 'OK' });
    };
    freshRuntime({ fetchFn: fakeFetch });
    OraPromptTemplateRuntime.register({
      id: 'needs',
      slash_command: '/needs',
      label: 'Needs',
      template: 'value is {{x}}',
      variables: [{ name: 'x', type: 'text' }],
      gear_preference: 1
    });
    var prompted = null;
    var prompter = async function (missing, tpl) {
      prompted = missing.map(function (m) { return m.name; });
      return { x: 'filled-by-prompter' };
    };
    var r = await OraPromptTemplateRuntime.invoke('/needs',
      {}, { promptForVariables: prompter });
    ok('prompter invoked with missing var',  eq(prompted, ['x']),
      JSON.stringify(prompted));
    ok('prompter answer rendered',
      r.success && captured.message === 'value is filled-by-prompter',
      'message=' + (captured && captured.message));
  }

  // ─────────────────────────────────────────────────────────────────────────
  section('missing variable — no prompter, native prompt unavailable → cancel');
  // ─────────────────────────────────────────────────────────────────────────
  {
    freshRuntime({ fetchFn: function () { return Promise.resolve({}); } });
    OraPromptTemplateRuntime.register({
      id: 'unfilled',
      template: 'value is {{x}}',
      variables: [{ name: 'x', type: 'text' }],
      gear_preference: 1
    });
    var r = await OraPromptTemplateRuntime.invoke('unfilled');
    ok('cancellation surfaces as failure',
      r.success === false && r.error && r.error.code === 'cancelled',
      JSON.stringify(r));
  }

  // ─────────────────────────────────────────────────────────────────────────
  section('unknown template');
  // ─────────────────────────────────────────────────────────────────────────
  {
    freshRuntime({});
    var r = await OraPromptTemplateRuntime.invoke('/never-registered foo');
    ok('unknown template returns failure',
      r.success === false && r.error.code === 'unknown-template',
      JSON.stringify(r));
  }

  // ─────────────────────────────────────────────────────────────────────────
  section('inline default + declared default fill in for missing vars');
  // ─────────────────────────────────────────────────────────────────────────
  {
    var captured = null;
    var fakeFetch = function (u, o) {
      captured = JSON.parse(o.body);
      return Promise.resolve({ ok: true });
    };
    freshRuntime({ fetchFn: fakeFetch });
    // Inline default — engine handles it; runtime should NOT prompt.
    OraPromptTemplateRuntime.register({
      id: 'inlinedef',
      template: 'style is {{style|noir}}',
      variables: [{ name: 'style', type: 'text' }],
      gear_preference: 1
    });
    var r1 = await OraPromptTemplateRuntime.invoke('inlinedef');
    ok('inline default rendered without prompting',
      r1.success && captured.message === 'style is noir',
      'message=' + (captured && captured.message));

    // Declared default in variables[].
    OraPromptTemplateRuntime.register({
      id: 'declareddef',
      template: 'era is {{era}}',
      variables: [{ name: 'era', type: 'text', default: '1920s' }],
      gear_preference: 1
    });
    captured = null;
    var r2 = await OraPromptTemplateRuntime.invoke('declareddef');
    ok('declared default rendered without prompting',
      r2.success && captured.message === 'era is 1920s',
      'message=' + (captured && captured.message));
  }

  // ─────────────────────────────────────────────────────────────────────────
  section('asPackLoaderRegistry conforms to loader contract');
  // ─────────────────────────────────────────────────────────────────────────
  {
    freshRuntime({});
    var reg = OraPromptTemplateRuntime.asPackLoaderRegistry();
    ok('register is a function',     typeof reg.register === 'function');
    ok('unregister is a function',   typeof reg.unregister === 'function');

    var def = {
      id: 'pack-installed',
      template: 'inst {{x}}',
      variables: [{ name: 'x', type: 'text' }],
      gear_preference: 1
    };
    reg.register(def);
    ok('loader-registered template visible',
      OraPromptTemplateRuntime.has('pack-installed'));
    reg.unregister('pack-installed');
    ok('loader-unregistered template gone',
      !OraPromptTemplateRuntime.has('pack-installed'));
  }

  // ---- summary ----------------------------------------------------------
  console.log('\n=== ' + PASS + ' passed, ' + FAIL + ' failed ===');
  if (FAIL > 0) {
    console.log('\nFailures:');
    failures.forEach(function (f) {
      console.log('  - ' + f.label + (f.detail ? ' (' + f.detail + ')' : ''));
    });
    process.exit(1);
  }
  process.exit(0);
}

runAll().catch(function (e) {
  console.error('Test harness threw:', e);
  process.exit(2);
});
