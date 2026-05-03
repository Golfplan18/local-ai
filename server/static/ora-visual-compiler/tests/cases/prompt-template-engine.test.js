/**
 * Test harness for prompt-template-engine.js (WP-7.0.6).
 *
 * Plain Node — does not use the visual-compiler jsdom stack. Run with:
 *   node ~/ora/server/static/ora-visual-compiler/tests/cases/prompt-template-engine.test.js
 *
 * Tests are deliberately self-contained so this file can also live alongside
 * a future test runner. Exits non-zero on any failure.
 */

'use strict';

var path = require('path');
var enginePath = path.resolve(__dirname,
  '../../../prompt-template-engine.js');
var engine = require(enginePath);

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

function throws(label, fn, expectedCode) {
  try {
    fn();
    failed++;
    failures.push(label + ' (did not throw)');
    console.log('  FAIL  ' + label + ' (did not throw)');
  } catch (e) {
    if (expectedCode && e.code !== expectedCode) {
      failed++;
      failures.push(label + ' (wrong code: ' + e.code + ')');
      console.log('  FAIL  ' + label
        + ' (expected code=' + expectedCode + ', got ' + e.code + ')');
    } else {
      passed++;
      console.log('  PASS  ' + label + ' [code=' + e.code + ']');
    }
  }
}

// ─── parseToken ──────────────────────────────────────────────────────────────

console.log('parseToken:');
eq('plain name',
  engine.parseToken('name'),
  { name: 'name', default: null });
eq('name with default',
  engine.parseToken('name|default'),
  { name: 'name', default: 'default' });
eq('whitespace tolerated',
  engine.parseToken(' name | default '),
  { name: 'name', default: 'default' });
eq('multi-word default preserved',
  engine.parseToken('style|art deco'),
  { name: 'style', default: 'art deco' });
throws('invalid name rejected', function () {
  engine.parseToken('1bad');
}, 'invalid-template');
throws('empty name rejected', function () {
  engine.parseToken('');
}, 'invalid-template');

// ─── extractVariables ────────────────────────────────────────────────────────

console.log('\nextractVariables:');
eq('no variables',
  engine.extractVariables('hello world'),
  []);
eq('single variable',
  engine.extractVariables('hello {{name}}'),
  ['name']);
eq('declaration order preserved',
  engine.extractVariables('A {{a}} B {{b}} C {{c}}'),
  ['a', 'b', 'c']);
eq('deduplicated',
  engine.extractVariables('{{x}} and {{x}} again'),
  ['x']);
eq('default suffix stripped from extracted name',
  engine.extractVariables('{{style|Hergé}} drawing of {{scene}}'),
  ['style', 'scene']);
eq('whitespace inside braces',
  engine.extractVariables('{{ name }}'),
  ['name']);

// ─── render: §13.0 test criterion ────────────────────────────────────────────

console.log('\nrender (§13.0 test criterion):');

// "Render a template with all variables filled"
eq('all variables filled',
  engine.render('A cartoon of {{scene}} in {{style}} style',
    { scene: 'a robot', style: 'noir' }),
  'A cartoon of a robot in noir style');

// "with one missing → declared error"
throws('missing variable raises RenderError', function () {
  engine.render('A cartoon of {{scene}} in {{style}} style',
    { scene: 'a robot' });
}, 'missing-variable');

// "with default → uses default"
eq('inline default applies when value missing',
  engine.render('A cartoon of {{scene}} in {{style|noir}} style',
    { scene: 'a robot' }),
  'A cartoon of a robot in noir style');

eq('inline default ignored when value supplied',
  engine.render('A cartoon of {{scene}} in {{style|noir}} style',
    { scene: 'a robot', style: 'pop' }),
  'A cartoon of a robot in pop style');

// "type-constrained variable rejects wrong type"
throws('text type rejects non-string', function () {
  engine.render('Hello {{name}}', { name: 42 }, {
    variables: [{ name: 'name', type: 'text' }],
  });
}, 'type-mismatch');

throws('image-ref type rejects empty string', function () {
  engine.render('Use {{img}}', { img: '' }, {
    variables: [{ name: 'img', type: 'image-ref' }],
  });
}, 'type-mismatch');

eq('image-ref type accepts non-empty string',
  engine.render('Use {{img}}', { img: 'img:abc123' }, {
    variables: [{ name: 'img', type: 'image-ref' }],
  }),
  'Use img:abc123');

throws('enum type rejects out-of-set value', function () {
  engine.render('Style: {{s}}', { s: 'punk' }, {
    variables: [{ name: 's', type: 'enum', options: ['noir', 'pop'] }],
  });
}, 'type-mismatch');

eq('enum type accepts valid value',
  engine.render('Style: {{s}}', { s: 'noir' }, {
    variables: [{ name: 's', type: 'enum', options: ['noir', 'pop'] }],
  }),
  'Style: noir');

throws('enum without options rejects', function () {
  engine.render('Style: {{s}}', { s: 'noir' }, {
    variables: [{ name: 's', type: 'enum' }],
  });
}, 'invalid-declaration');

// ─── render: pack §7 example end-to-end ──────────────────────────────────────

console.log('\nrender (pack §7 cartoon-bg end-to-end):');

var cartoonBgTemplate =
  'A cartoon-style background showing {{scene}}, in the style of {{style|Hergé}}';
var cartoonBgVars = [
  { name: 'scene', type: 'text', label: 'Scene description' },
  { name: 'style', type: 'text', label: 'Drawing style', default: 'Hergé' },
];

eq('cartoon-bg with both supplied',
  engine.render(cartoonBgTemplate,
    { scene: 'a Paris cafe', style: 'Tintin' },
    { variables: cartoonBgVars }),
  'A cartoon-style background showing a Paris cafe, in the style of Tintin');

eq('cartoon-bg with style omitted (inline default wins)',
  engine.render(cartoonBgTemplate,
    { scene: 'a Paris cafe' },
    { variables: cartoonBgVars }),
  'A cartoon-style background showing a Paris cafe, in the style of Hergé');

throws('cartoon-bg with scene omitted raises', function () {
  engine.render(cartoonBgTemplate, {}, { variables: cartoonBgVars });
}, 'missing-variable');

// ─── render: declared default fallback (no inline) ───────────────────────────

console.log('\nrender (declared default with no inline):');

eq('declared default applies when no inline and no value',
  engine.render('Hello {{name}}', {},
    { variables: [{ name: 'name', type: 'text', default: 'world' }] }),
  'Hello world');

eq('declared default skipped when value supplied',
  engine.render('Hello {{name}}', { name: 'Ora' },
    { variables: [{ name: 'name', type: 'text', default: 'world' }] }),
  'Hello Ora');

// ─── render: edge cases ──────────────────────────────────────────────────────

console.log('\nrender (edge cases):');

eq('repeated variable substituted multiple times',
  engine.render('{{x}} and {{x}} again', { x: 'foo' }),
  'foo and foo again');

eq('no variables — passthrough',
  engine.render('static text', {}),
  'static text');

throws('null values + missing variable raises', function () {
  engine.render('Hello {{n}}', null);
}, 'missing-variable');

// values=null with no missing variable should work (template has no vars):
eq('null values with no template variables',
  engine.render('static', null),
  'static');

// ─── Summary ─────────────────────────────────────────────────────────────────

console.log('\n────────────────────────────────────────');
console.log('  passed: ' + passed);
console.log('  failed: ' + failed);
if (failed > 0) {
  console.log('\nFailures:');
  failures.forEach(function (f) { console.log('  - ' + f); });
  process.exit(1);
}
process.exit(0);
