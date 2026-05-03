#!/usr/bin/env node
/* test-pack-validator.js — WP-7.0.4
 *
 * End-to-end test for OraPackValidator. Loads the schema + validator,
 * stubs OraIconResolver against the canonical Lucide names.json, then
 * runs a battery of valid + invalid packs and reports per-case results.
 *
 * Run:  node ~/ora/server/static/tests/test-pack-validator.js
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var fs = require('fs');
var path = require('path');

var ORA_ROOT = path.resolve(__dirname, '..', '..', '..');
var SCHEMA_PATH = path.join(ORA_ROOT, 'config', 'schemas', 'toolbar-pack.schema.json');
var VALIDATOR_PATH = path.join(ORA_ROOT, 'server', 'static', 'pack-validator.js');
var NAMES_PATH = path.join(ORA_ROOT, 'server', 'static', 'vendor', 'lucide', 'names.json');
var AJV_PATH = path.join(ORA_ROOT, 'server', 'static', 'ora-visual-compiler', 'tests', 'node_modules', 'ajv', 'dist', '2020.js');

// ---- bootstrap -------------------------------------------------------------

var schema = JSON.parse(fs.readFileSync(SCHEMA_PATH, 'utf8'));
var lucideNames = JSON.parse(fs.readFileSync(NAMES_PATH, 'utf8'));
var canonicalNameSet = new Set(lucideNames.names);

var Ajv2020 = require(AJV_PATH);
// Ajv may be exported as default in some bundles
var AjvCtor = (typeof Ajv2020 === 'function') ? Ajv2020 : Ajv2020.default;
if (typeof AjvCtor !== 'function') {
  console.error('error: could not load Ajv2020 from ' + AJV_PATH);
  process.exit(2);
}

var ajv = new AjvCtor({
  strict: true,
  strictRequired: 'log',
  allErrors: true,
  allowUnionTypes: true
});
var validateFn = ajv.compile(schema);

var validatorMod = require(VALIDATOR_PATH);

// Stub OraIconResolver with the canonical names.
var iconResolverStub = {
  isValidName: function (name) {
    if (typeof name !== 'string') return false;
    if (!/^[a-z0-9][a-z0-9-]*$/.test(name)) return false;
    return canonicalNameSet.has(name);
  }
};

validatorMod.init({
  ajvValidateFn: validateFn,
  iconResolver: iconResolverStub
  // svgParser omitted → fallback regex-tier validator for inline SVGs
});

// ---- test runner -----------------------------------------------------------

var passCount = 0;
var failCount = 0;
var failures = [];

function _summarizeFindings(findings) {
  if (!findings || findings.length === 0) return '(no findings)';
  return findings.map(function (f) {
    return '  [' + f.severity + ' ' + f.code + ' @ ' + f.path + '] ' + f.message;
  }).join('\n');
}

function expectValid(name, pack) {
  var res = validatorMod.validate(pack);
  if (res.valid) {
    passCount++;
    process.stdout.write('  PASS  ' + name + '\n');
  } else {
    failCount++;
    failures.push({ name: name, expected: 'valid', got: res });
    process.stdout.write('  FAIL  ' + name + ' (expected valid; got errors)\n');
    process.stdout.write(_summarizeFindings(res.findings) + '\n');
  }
}

function expectInvalid(name, pack, expectedCodes) {
  var res = validatorMod.validate(pack);
  if (res.valid) {
    failCount++;
    failures.push({ name: name, expected: 'invalid', got: res });
    process.stdout.write('  FAIL  ' + name + ' (expected invalid; got valid)\n');
    return;
  }
  // If expectedCodes provided, ensure each appears among the findings.
  var got = (res.findings || []).map(function (f) { return f.code; });
  var missing = (expectedCodes || []).filter(function (c) { return got.indexOf(c) === -1; });
  if (missing.length > 0) {
    failCount++;
    failures.push({ name: name, expected: expectedCodes, got: got });
    process.stdout.write('  FAIL  ' + name + ' (missing expected codes: ' + missing.join(', ') + ')\n');
    process.stdout.write(_summarizeFindings(res.findings) + '\n');
    return;
  }
  passCount++;
  process.stdout.write('  PASS  ' + name + ' (rejected with: ' + got.join(', ') + ')\n');
}

// ---- valid pack fixtures ---------------------------------------------------

process.stdout.write('\n--- valid packs (must pass) ---\n');

// Pack 1 — the §14 example pack from Reference — Toolbar Pack Format.md
var pack_mood_board = {
  pack_name: "Mood Board",
  pack_version: "1.0.0",
  ora_compatibility: ">=0.7.0",
  author: { name: "Ora Defaults" },
  description: "Image collection and inspiration workflow with grid composition",
  toolbars: [
    {
      id: "mood-board",
      label: "Mood Board",
      default_dock: "left",
      items: [
        { id: "select", icon: "mouse-pointer", label: "Select", shortcut: "V", binding: "tool:select" },
        { id: "image-upload", icon: "image-up", label: "Upload Image", shortcut: "U", binding: "tool:image_upload" },
        { id: "image-generate", icon: "sparkles", label: "Generate Image", binding: "capability:image_generates" },
        { id: "annotate", icon: "highlighter", label: "Annotate", binding: "tool:annotate" }
      ]
    }
  ],
  composition_templates: [
    {
      id: "mood-board-3x3",
      label: "3x3 mood board grid",
      canvas_state: {
        version: 1,
        layers: [
          {
            id: "background",
            objects: [
              { type: "rect", x: 100, y: 100, width: 300, height: 300, placeholder: true },
              { type: "rect", x: 450, y: 100, width: 300, height: 300, placeholder: true },
              { type: "rect", x: 800, y: 100, width: 300, height: 300, placeholder: true }
            ]
          }
        ],
        view: { zoom: 1.0, pan_x: 0, pan_y: 0 }
      }
    }
  ]
};
expectValid('§14 example pack — Mood Board', pack_mood_board);

// Pack 2 — Photo Editor (toolbars + macros + prompt templates), exercises:
//   * macros with steps using both 'tool' and 'capability' forms
//   * prompt template with capability_route (image route)
//   * inline SVG icon for a custom tool (with viewBox)
var pack_photo_editor = {
  pack_name: "Photo Editor",
  pack_version: "0.9.1-beta+ora",
  ora_compatibility: "^0.7.0",
  author: { name: "test", email: "t@example.com" },
  toolbars: [
    {
      id: "photo-editor",
      label: "Photo Editor",
      default_dock: "right",
      default_icon_size: "large",
      items: [
        { id: "select", icon: "mouse-pointer", label: "Select", shortcut: "V", binding: "tool:select" },
        { id: "crop", icon: "crop", label: "Crop", shortcut: "C", binding: "tool:crop" },
        { id: "custom", icon: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="12" cy="12" r="10"/></svg>', label: "Custom", binding: "tool:custom_op" },
        { id: "ai-fill", icon: "sparkles", label: "AI Fill", binding: "macro:ai-fill-selection", enabled_when: "selection_active" }
      ]
    }
  ],
  macros: [
    {
      id: "ai-fill-selection",
      label: "AI Fill Selection",
      icon: "wand-sparkles",
      shortcut: null,
      steps: [
        { tool: "ensure_selection", params: {} },
        { capability: "image_inpaint", params: { prompt: "{{prompt}}" } }
      ]
    }
  ],
  prompt_templates: [
    {
      id: "fill-style",
      slash_command: "/fill-style",
      label: "Style Fill",
      template: "Fill the selected area in the style of {{style|impressionist}}",
      variables: [
        { name: "style", type: "text", label: "Style", default: "impressionist" }
      ],
      capability_route: "image_inpaint"
    }
  ]
};
expectValid('synthetic Photo Editor pack (toolbars + macros + templates)', pack_photo_editor);

// Pack 3 — Diagram Thinking (toolbars only), text-route prompt template,
// enum prompt variable.
var pack_diagram = {
  pack_name: "Diagram Thinking",
  pack_version: "1.0.0",
  ora_compatibility: ">=0.7.0",
  author: { name: "Ora Defaults", url: "https://ora.example/defaults" },
  toolbars: [
    {
      id: "shapes",
      label: "Shapes & Diagrams",
      items: [
        { id: "rect", icon: "square", label: "Rectangle", binding: "tool:shape_rect" },
        { id: "ellipse", icon: "circle", label: "Ellipse", binding: "tool:shape_ellipse" },
        { id: "arrow", icon: "arrow-right", label: "Arrow", binding: "tool:shape_arrow" }
      ]
    },
    {
      id: "annotation",
      label: "Annotation",
      items: [
        { id: "highlighter", icon: "highlighter", label: "Highlighter", binding: "tool:annotate_highlight" },
        { id: "sticky", icon: "sticky-note", label: "Sticky Note", binding: "tool:annotate_sticky" }
      ]
    }
  ],
  prompt_templates: [
    {
      id: "summarize-diagram",
      label: "Summarize Diagram",
      template: "Summarize the diagram in the style of {{tone}}",
      variables: [
        { name: "tone", type: "enum", options: ["formal", "casual", "technical"], default: "formal" }
      ],
      gear_preference: 2
    }
  ]
};
expectValid('synthetic Diagram Thinking pack (text-route, enum var)', pack_diagram);

// Pack 4 — minimal pack carrying only macros (validates the empty-pack
// rejection logic admits any single non-empty section).
var pack_macros_only = {
  pack_name: "Macros Only",
  pack_version: "0.0.1",
  ora_compatibility: ">=0.7.0",
  author: { name: "anon" },
  macros: [
    {
      id: "greet",
      label: "Greet",
      steps: [
        { tool: "say", params: { text: "hello" } }
      ]
    }
  ]
};
expectValid('synthetic minimal pack (macros only)', pack_macros_only);

// ---- malformed pack fixtures ----------------------------------------------

process.stdout.write('\n--- malformed packs (must fail with specific codes) ---\n');

// 1. Empty pack — no toolbars / macros / templates
expectInvalid(
  'empty pack (no sections present)',
  {
    pack_name: "Empty",
    pack_version: "1.0.0",
    ora_compatibility: ">=0.7.0",
    author: { name: "x" }
  },
  ['schema_anyOf']
);

// 2. Unknown top-level field — additionalProperties:false enforcement
expectInvalid(
  'unknown top-level field "extras"',
  {
    pack_name: "Has Extras",
    pack_version: "1.0.0",
    ora_compatibility: ">=0.7.0",
    author: { name: "x" },
    extras: { stuff: 1 },
    macros: [{ id: "m", label: "M", steps: [{ tool: "t", params: {} }] }]
  },
  ['schema_additionalProperties']
);

// 3. Unknown nested field on a toolbar item
expectInvalid(
  'unknown nested field "color" on toolbar item',
  {
    pack_name: "Bad Item",
    pack_version: "1.0.0",
    ora_compatibility: ">=0.7.0",
    author: { name: "x" },
    toolbars: [{
      id: "t", label: "T",
      items: [{ id: "i", icon: "circle", label: "I", binding: "tool:x", color: "red" }]
    }]
  },
  ['schema_additionalProperties']
);

// 4. Missing required pack-level field
expectInvalid(
  'missing required pack_version',
  {
    pack_name: "No Version",
    ora_compatibility: ">=0.7.0",
    author: { name: "x" },
    macros: [{ id: "m", label: "M", steps: [{ tool: "t", params: {} }] }]
  },
  ['schema_required']
);

// 5. Bad semver in pack_version
expectInvalid(
  'bad semver in pack_version',
  {
    pack_name: "Bad Semver",
    pack_version: "1.x",
    ora_compatibility: ">=0.7.0",
    author: { name: "x" },
    macros: [{ id: "m", label: "M", steps: [{ tool: "t", params: {} }] }]
  },
  ['schema_pattern']
);

// 6. Unknown Lucide icon name (passes the schema pattern but isn't canonical)
expectInvalid(
  'unknown Lucide icon name',
  {
    pack_name: "Bad Icon",
    pack_version: "1.0.0",
    ora_compatibility: ">=0.7.0",
    author: { name: "x" },
    toolbars: [{
      id: "t", label: "T",
      items: [{ id: "i", icon: "this-is-not-a-real-icon", label: "I", binding: "tool:x" }]
    }]
  },
  ['icon_unknown_lucide_name']
);

// 7. Inline SVG missing viewBox attribute
expectInvalid(
  'inline SVG missing viewBox',
  {
    pack_name: "No ViewBox",
    pack_version: "1.0.0",
    ora_compatibility: ">=0.7.0",
    author: { name: "x" },
    toolbars: [{
      id: "t", label: "T",
      items: [{
        id: "i",
        icon: '<svg xmlns="http://www.w3.org/2000/svg"><circle cx="5" cy="5" r="2"/></svg>',
        label: "I", binding: "tool:x"
      }]
    }]
  },
  ['inline_svg_invalid']
);

// 8. Inline SVG containing <script> — defense-in-depth
expectInvalid(
  'inline SVG with <script> tag',
  {
    pack_name: "Scripted SVG",
    pack_version: "1.0.0",
    ora_compatibility: ">=0.7.0",
    author: { name: "x" },
    toolbars: [{
      id: "t", label: "T",
      items: [{
        id: "i",
        icon: '<svg viewBox="0 0 24 24"><script>alert(1)</script><circle cx="5" cy="5" r="2"/></svg>',
        label: "I", binding: "tool:x"
      }]
    }]
  },
  ['inline_svg_invalid']
);

// 9. URL as icon (external resource) — should be rejected via
//    icon_external_reference (the schema pattern lets a regex match through
//    semantically, but our walker pre-rejects URLs explicitly).
expectInvalid(
  'icon as a URL string',
  {
    pack_name: "URL Icon",
    pack_version: "1.0.0",
    ora_compatibility: ">=0.7.0",
    author: { name: "x" },
    toolbars: [{
      id: "t", label: "T",
      items: [{
        id: "i",
        icon: "https://example.com/icon.svg",
        label: "I", binding: "tool:x"
      }]
    }]
  },
  ['icon_external_reference']
);

// 10. Macro step has both 'tool' and 'capability' (oneOf violation)
expectInvalid(
  'macro step with both tool and capability',
  {
    pack_name: "Bad Step",
    pack_version: "1.0.0",
    ora_compatibility: ">=0.7.0",
    author: { name: "x" },
    macros: [{
      id: "m", label: "M",
      steps: [{ tool: "x", capability: "y", params: {} }]
    }]
  },
  ['schema_oneOf']
);

// 11. Prompt template declaring both gear_preference and capability_route
expectInvalid(
  'prompt template with both gear_preference and capability_route',
  {
    pack_name: "Bad Template",
    pack_version: "1.0.0",
    ora_compatibility: ">=0.7.0",
    author: { name: "x" },
    prompt_templates: [{
      id: "t", label: "T",
      template: "say {{x}}",
      variables: [{ name: "x", type: "text" }],
      gear_preference: 1,
      capability_route: "image_generates"
    }]
  },
  ['schema_oneOf']
);

// 12. Bad binding form
expectInvalid(
  'bad binding (no tool:/capability:/macro: prefix)',
  {
    pack_name: "Bad Binding",
    pack_version: "1.0.0",
    ora_compatibility: ">=0.7.0",
    author: { name: "x" },
    toolbars: [{
      id: "t", label: "T",
      items: [{ id: "i", icon: "circle", label: "I", binding: "do-the-thing" }]
    }]
  },
  ['schema_pattern']
);

// 13. Enum prompt variable missing options
expectInvalid(
  'enum prompt variable missing options',
  {
    pack_name: "Bad Enum",
    pack_version: "1.0.0",
    ora_compatibility: ">=0.7.0",
    author: { name: "x" },
    prompt_templates: [{
      id: "t", label: "T",
      template: "v {{c}}",
      variables: [{ name: "c", type: "enum" }],
      gear_preference: 1
    }]
  },
  ['schema_required']
);

// 14. Pack at top level is not an object
expectInvalid(
  'pack is an array',
  [],
  ['pack_not_an_object']
);

// 15. ID with uppercase / underscores — should fail kebab-case pattern
expectInvalid(
  'toolbar id with uppercase letters',
  {
    pack_name: "Bad ID",
    pack_version: "1.0.0",
    ora_compatibility: ">=0.7.0",
    author: { name: "x" },
    toolbars: [{
      id: "MoodBoard", label: "Bad",
      items: [{ id: "i", icon: "circle", label: "I", binding: "tool:x" }]
    }]
  },
  ['schema_pattern']
);

// ---- summary ---------------------------------------------------------------

process.stdout.write('\n--- summary ---\n');
process.stdout.write('passed: ' + passCount + '\n');
process.stdout.write('failed: ' + failCount + '\n');

if (failCount > 0) {
  process.stdout.write('\nfailures:\n');
  for (var i = 0; i < failures.length; i++) {
    process.stdout.write('  ' + failures[i].name + '\n');
  }
  process.exit(1);
}

process.stdout.write('\nall tests passed.\n');
process.exit(0);

