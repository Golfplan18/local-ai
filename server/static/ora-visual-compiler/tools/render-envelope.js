#!/usr/bin/env node
/**
 * ora-visual-compiler / tools / render-envelope.js
 *
 * WP-6.1 headless SVG renderer.
 *
 * Reads a single ora-visual envelope (JSON) from stdin, boots the full
 * compiler (the same way tests/run.js does — jsdom + all vendor libs +
 * every renderer + accessibility + adversarial layers), runs
 * ``OraVisualCompiler.compileWithNav(envelope)`` inside that window, and
 * writes the resulting SVG to stdout.
 *
 * Exit codes:
 *   0  — success; SVG written to stdout.
 *   1  — compilation failed (validation error, renderer error, adversarial
 *        block, or empty SVG). A structured JSON error record is written
 *        to stderr.
 *   2  — CLI-level failure (stdin parse, jsdom boot, missing schemas).
 *        JSON error record on stderr.
 *
 * Invocation (from Python or the shell):
 *   echo '{"schema_version":"0.2","id":"fig-1","type":"fishbone",...}' |
 *     node ~/ora/server/static/ora-visual-compiler/tools/render-envelope.js
 *
 * Stays side-by-side with tests/run.js — both share the same boot sequence
 * because both need the exact same jsdom environment. When tests/run.js's
 * boot is updated, this CLI must be updated to match.
 */

'use strict';

const fs   = require('fs');
const vm   = require('vm');
const path = require('path');

// jsdom is installed under tests/node_modules/. The CLI lives in a sibling
// directory, so we teach require() where to find it. Module.paths is the
// canonical hook — prepending to it is safer than mutating require.cache or
// shipping a duplicate install.
const _testsNodeModules = path.resolve(__dirname, '..', 'tests', 'node_modules');
if (fs.existsSync(_testsNodeModules)) {
  // Node module lookup walks up parent node_modules directories. We insert
  // the tests/node_modules path directly into the module path array so
  // require('jsdom') resolves regardless of cwd.
  require('module').Module._initPaths();
  const _mod = require('module');
  if (Array.isArray(_mod.globalPaths) && _mod.globalPaths.indexOf(_testsNodeModules) === -1) {
    _mod.globalPaths.unshift(_testsNodeModules);
  }
}

// Fallback: if globalPaths adjustment didn't take (newer Node versions are
// stricter), resolve jsdom's main file by absolute path.
let JSDOM;
try {
  ({ JSDOM } = require('jsdom'));
} catch (e) {
  const abs = path.join(_testsNodeModules, 'jsdom');
  if (!fs.existsSync(abs)) {
    process.stderr.write(JSON.stringify({
      kind: 'missing_jsdom',
      message: 'jsdom not resolvable; install under tests/node_modules or add a package.json at ora-visual-compiler/',
      searched: [_testsNodeModules],
    }) + '\n');
    process.exit(2);
  }
  ({ JSDOM } = require(abs));
}

// ── Paths ────────────────────────────────────────────────────────────────────
const COMPILER_DIR  = path.resolve(__dirname, '..');
const SCHEMAS_DIR   = path.resolve(__dirname, '..', '..', '..', '..', 'config', 'visual-schemas');
const VENDOR_AJV    = path.join(COMPILER_DIR, 'vendor', 'ajv', 'ajv2020.bundle.min.js');
const VENDOR_VEGA   = path.join(COMPILER_DIR, 'vendor', 'vega', 'vega.min.js');
const VENDOR_VL     = path.join(COMPILER_DIR, 'vendor', 'vega-lite', 'vega-lite.min.js');

function emitCliError(kind, message, detail) {
  const payload = {
    kind: kind || 'cli_error',
    message: message || 'unknown',
  };
  if (detail !== undefined) payload.detail = detail;
  try {
    process.stderr.write(JSON.stringify(payload) + '\n');
  } catch (e) {
    // last-resort raw write
    try { process.stderr.write(String(message) + '\n'); } catch (_) {}
  }
}

if (!fs.existsSync(path.join(SCHEMAS_DIR, 'envelope.json'))) {
  emitCliError('schema_root_missing',
    'could not locate visual-schemas',
    { expected: SCHEMAS_DIR });
  process.exit(2);
}

// ── Read stdin (blocking, full buffer) ───────────────────────────────────────
async function readStdin() {
  return new Promise((resolve, reject) => {
    const chunks = [];
    process.stdin.on('data', (c) => chunks.push(c));
    process.stdin.on('end', () => resolve(Buffer.concat(chunks).toString('utf-8')));
    process.stdin.on('error', reject);
  });
}

// ── jsdom boot (mirror of tests/run.js bootCompiler) ─────────────────────────
async function bootCompiler() {
  const dom = new JSDOM(
    '<!DOCTYPE html><html><head></head><body></body></html>',
    { url: 'http://localhost/', runScripts: 'outside-only', pretendToBeVisual: true }
  );
  const win = dom.window;

  win.structuredClone = globalThis.structuredClone || ((v) => JSON.parse(JSON.stringify(v)));
  win.globalThis = win;
  win.console = console;

  if (!win.getComputedStyle) {
    win.getComputedStyle = () => ({ getPropertyValue: () => '' });
  }
  if (!win.matchMedia) {
    win.matchMedia = () => ({ matches: false, addListener: () => {}, removeListener: () => {} });
  }
  if (!win.requestAnimationFrame) {
    win.requestAnimationFrame = (cb) => setTimeout(cb, 16);
  }

  if (win.SVGElement && !win.SVGElement.prototype.getBBox) {
    win.SVGElement.prototype.getBBox = function () {
      const text = (this.textContent || '').length;
      return { x: 0, y: 0, width: text * 6, height: 14 };
    };
  }
  if (win.SVGElement && !win.SVGElement.prototype.getComputedTextLength) {
    win.SVGElement.prototype.getComputedTextLength = function () {
      return (this.textContent || '').length * 6;
    };
  }
  if (win.SVGElement && !win.SVGElement.prototype.getScreenCTM) {
    win.SVGElement.prototype.getScreenCTM = function () {
      return { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0, inverse: function () { return this; } };
    };
  }
  if (win.SVGPathElement && !win.SVGPathElement.prototype.getTotalLength) {
    win.SVGPathElement.prototype.getTotalLength = function () { return 100; };
  }
  if (win.SVGPathElement && !win.SVGPathElement.prototype.getPointAtLength) {
    win.SVGPathElement.prototype.getPointAtLength = function (dist) {
      return { x: dist || 0, y: 0 };
    };
  }

  win.HTMLCanvasElement.prototype.getContext = function () {
    return {
      measureText: (t) => ({ width: (t || '').length * 6 }),
      fillText: () => {}, save: () => {}, restore: () => {},
      scale: () => {}, translate: () => {}, rotate: () => {},
      beginPath: () => {}, closePath: () => {}, fillRect: () => {},
      strokeRect: () => {}, clearRect: () => {}, moveTo: () => {},
      lineTo: () => {}, stroke: () => {}, fill: () => {},
      arc: () => {}, rect: () => {},
      getImageData: () => ({ data: new Uint8ClampedArray(4) }),
      putImageData: () => {}, createImageData: () => ({ data: new Uint8ClampedArray(4) }),
      setTransform: () => {}, canvas: this,
    };
  };

  const jsdomCtx = dom.getInternalVMContext();
  function loadScript(absPath) {
    const src = fs.readFileSync(absPath, 'utf-8');
    vm.runInContext(src, jsdomCtx, { filename: absPath });
  }

  loadScript(path.join(COMPILER_DIR, 'errors.js'));
  loadScript(path.join(COMPILER_DIR, 'validator.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'stub.js'));
  loadScript(path.join(COMPILER_DIR, 'dispatcher.js'));
  loadScript(path.join(COMPILER_DIR, 'index.js'));

  loadScript(VENDOR_AJV);
  loadScript(VENDOR_VEGA);
  loadScript(VENDOR_VL);
  loadScript(path.join(COMPILER_DIR, 'vendor', 'mermaid', 'mermaid.min.js'));
  loadScript(path.join(COMPILER_DIR, 'vendor', 'viz-js', 'viz-standalone.js'));
  loadScript(path.join(COMPILER_DIR, 'vendor', 'd3', 'd3.min.js'));
  loadScript(path.join(COMPILER_DIR, 'vendor', 'dagre', 'dagre.min.js'));
  loadScript(path.join(COMPILER_DIR, 'vendor', 'structurizr-mini', 'parser.js'));
  loadScript(path.join(COMPILER_DIR, 'vendor', 'structurizr-mini', 'renderer.js'));

  loadScript(path.join(COMPILER_DIR, 'palettes.js'));
  loadScript(path.join(COMPILER_DIR, 'dot-engine.js'));
  loadScript(path.join(COMPILER_DIR, 'ajv-init.js'));

  loadScript(path.join(COMPILER_DIR, 'renderers', 'vega-lite.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'mermaid.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'causal-dag.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'c4.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'causal-loop-diagram.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'stock-and-flow.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'fishbone.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'decision-tree.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'influence-diagram.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'ach-matrix.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'quadrant-matrix.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'bow-tie.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'ibis.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'pro-con.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'concept-map.js'));

  loadScript(path.join(COMPILER_DIR, 'alt-text-generator.js'));
  loadScript(path.join(COMPILER_DIR, 'aria-annotator.js'));
  loadScript(path.join(COMPILER_DIR, 'keyboard-nav.js'));
  loadScript(path.join(COMPILER_DIR, 'artifact-adversarial.js'));

  // Konva + visual-panel needed for full parity with run.js, but not
  // strictly required for compileWithNav on the envelope. We still patch
  // the canvas mock so any renderer that measures via canvas doesn't blow up.
  const origGetContext = win.HTMLCanvasElement.prototype.getContext;
  win.HTMLCanvasElement.prototype.getContext = function () {
    const c = origGetContext.apply(this, arguments) || {};
    if (!c.drawImage)           c.drawImage           = function () {};
    if (!c.transform)           c.transform           = function () {};
    if (!c.bezierCurveTo)       c.bezierCurveTo       = function () {};
    if (!c.quadraticCurveTo)    c.quadraticCurveTo    = function () {};
    if (!c.clip)                c.clip                = function () {};
    if (!c.createLinearGradient) c.createLinearGradient = function () { return { addColorStop: function () {} }; };
    if (!c.createRadialGradient) c.createRadialGradient = function () { return { addColorStop: function () {} }; };
    if (!c.createPattern)       c.createPattern       = function () { return null; };
    if (c.globalAlpha == null)  c.globalAlpha         = 1;
    return c;
  };

  const customLoad = (url) => {
    const prefix = '/static/visual-schemas/';
    const rel = url.startsWith(prefix) ? url.slice(prefix.length) : url;
    const abs = path.join(SCHEMAS_DIR, rel);
    return new Promise((resolve, reject) => {
      fs.readFile(abs, 'utf-8', (err, data) => {
        if (err) return reject(err);
        try { resolve(JSON.parse(data)); }
        catch (e) { reject(e); }
      });
    });
  };

  await win.OraVisualCompiler.bootstrapAjv({ load: customLoad });
  return win;
}

// ── Main ─────────────────────────────────────────────────────────────────────
(async function main() {
  let raw;
  try {
    raw = await readStdin();
  } catch (e) {
    emitCliError('stdin_read_failed', e.message || String(e));
    process.exit(2);
  }
  if (!raw || !raw.trim()) {
    emitCliError('empty_stdin', 'no envelope JSON received on stdin');
    process.exit(2);
  }

  let envelope;
  try {
    envelope = JSON.parse(raw);
  } catch (e) {
    emitCliError('json_parse_failed', 'stdin did not contain valid JSON',
      { js_message: e.message || String(e) });
    process.exit(2);
  }
  if (!envelope || typeof envelope !== 'object' || Array.isArray(envelope)) {
    emitCliError('envelope_not_object',
      'parsed stdin was not a JSON object');
    process.exit(2);
  }

  let win;
  try {
    win = await bootCompiler();
  } catch (e) {
    emitCliError('boot_failed',
      'jsdom compiler boot failed',
      { js_message: e.message || String(e), stack: (e.stack || '').slice(0, 2000) });
    process.exit(2);
  }

  let result;
  try {
    let r = win.OraVisualCompiler.compileWithNav(envelope);
    if (r && typeof r.then === 'function') {
      r = await r;
    }
    result = r;
  } catch (e) {
    emitCliError('compile_threw',
      'compileWithNav threw',
      { js_message: e.message || String(e), stack: (e.stack || '').slice(0, 2000) });
    process.exit(1);
  }

  const errs = (result && result.errors) || [];
  const svg = (result && result.svg) || '';

  if (errs.length > 0 || !svg) {
    emitCliError('compile_failed',
      'envelope failed validation or renderer emitted no SVG',
      {
        errors: errs.map((e) => ({
          code: e.code || '',
          message: (e.message || '').slice(0, 400),
          path: e.path || '',
          severity: e.severity || 'error',
        })),
        warnings: ((result && result.warnings) || []).map((w) => ({
          code: w.code || '',
          message: (w.message || '').slice(0, 400),
        })),
        svg_length: svg.length,
      });
    process.exit(1);
  }

  try {
    process.stdout.write(svg);
  } catch (e) {
    emitCliError('stdout_write_failed', e.message || String(e));
    process.exit(2);
  }
  process.exit(0);
})().catch((err) => {
  emitCliError('unhandled', err.message || String(err),
    { stack: (err.stack || '').slice(0, 2000) });
  process.exit(2);
});
