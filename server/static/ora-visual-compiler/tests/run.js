#!/usr/bin/env node
/**
 * ora-visual-compiler / tests / run.js
 * Node + jsdom harness for WP-1.2a. Boots the compiler the way the browser
 * would, then runs every test case under ./cases/, then prints a summary
 * and exits non-zero on any failure.
 *
 * Usage:
 *   cd ~/ora/server/static/ora-visual-compiler/tests
 *   npm install
 *   node run.js
 */

'use strict';

const fs   = require('fs');
const vm   = require('vm');
const path = require('path');
const { spawnSync } = require('child_process');
const { JSDOM } = require('jsdom');

// ── Paths ────────────────────────────────────────────────────────────────────
const COMPILER_DIR  = path.resolve(__dirname, '..');
const SCHEMAS_DIR   = path.resolve(__dirname, '..', '..', '..', '..', 'config', 'visual-schemas');
const EXAMPLES_DIR  = path.join(SCHEMAS_DIR, 'examples');
const VENDOR_AJV    = path.join(COMPILER_DIR, 'vendor', 'ajv', 'ajv2020.bundle.min.js');
const VENDOR_VEGA   = path.join(COMPILER_DIR, 'vendor', 'vega', 'vega.min.js');
const VENDOR_VL     = path.join(COMPILER_DIR, 'vendor', 'vega-lite', 'vega-lite.min.js');

// Sanity: confirm SCHEMAS_DIR points to the right place.
if (!fs.existsSync(path.join(SCHEMAS_DIR, 'envelope.json'))) {
  console.error('FATAL: could not locate visual-schemas at ' + SCHEMAS_DIR);
  process.exit(2);
}

// ── jsdom boot ───────────────────────────────────────────────────────────────
/**
 * Build a fresh jsdom window with the Vega/canvas polyfills, load every
 * compiler script in order, and return { win, ajvOk } after attempting
 * to bootstrap Ajv from the on-disk schemas.
 */
async function bootCompiler() {
  const dom = new JSDOM(
    '<!DOCTYPE html><html><head></head><body></body></html>',
    { url: 'http://localhost/', runScripts: 'outside-only', pretendToBeVisual: true }
  );
  const win = dom.window;

  // structuredClone: jsdom doesn't expose it on window in all versions.
  win.structuredClone = globalThis.structuredClone || ((v) => JSON.parse(JSON.stringify(v)));

  // Mermaid's UMD assigns globalThis.mermaid; point globalThis at the jsdom
  // window so the assignment lands on window.mermaid.
  win.globalThis = win;
  win.console = console;

  // Polyfills for browser APIs used by Mermaid / Vega / D3 but missing in jsdom.
  if (!win.getComputedStyle) {
    win.getComputedStyle = () => ({ getPropertyValue: () => '' });
  }
  if (!win.matchMedia) {
    win.matchMedia = () => ({ matches: false, addListener: () => {}, removeListener: () => {} });
  }
  if (!win.requestAnimationFrame) {
    win.requestAnimationFrame = (cb) => setTimeout(cb, 16);
  }

  // jsdom doesn't implement SVG getBBox / getComputedTextLength. Mermaid and
  // any text-measuring SVG library needs these. Mock with character-width
  // heuristics — fine for structural tests, not for pixel layout checks.
  // Minimum-size floor (width >= 10, height = 14): a real browser never measures
  // a rendered node as zero-width, but the naive `length * 6` returns 0 for
  // empty/whitespace textContent. Zero-width nodes collapse Mermaid's edge-label
  // geometry and trip "Could not find a suitable point for the given distance".
  if (win.SVGElement && !win.SVGElement.prototype.getBBox) {
    win.SVGElement.prototype.getBBox = function () {
      const text = (this.textContent || '').length;
      return { x: 0, y: 0, width: Math.max(text * 6, 10), height: 14 };
    };
  }
  if (win.SVGElement && !win.SVGElement.prototype.getComputedTextLength) {
    win.SVGElement.prototype.getComputedTextLength = function () {
      return Math.max((this.textContent || '').length * 6, 10);
    };
  }
  if (win.SVGElement && !win.SVGElement.prototype.getScreenCTM) {
    win.SVGElement.prototype.getScreenCTM = function () {
      return { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0, inverse: function () { return this; } };
    };
  }
  // SVG <path> length & point-along-path. Mermaid's flowchart uses these
  // for arrow routing. jsdom doesn't implement them.
  if (win.SVGPathElement && !win.SVGPathElement.prototype.getTotalLength) {
    win.SVGPathElement.prototype.getTotalLength = function () { return 100; };
  }
  if (win.SVGPathElement && !win.SVGPathElement.prototype.getPointAtLength) {
    win.SVGPathElement.prototype.getPointAtLength = function (dist) {
      return { x: dist || 0, y: 0 };
    };
  }

  // Canvas: mock getContext so Vega can measure text without the native
  // `canvas` npm package. The mock returns constant widths — fine for
  // structural SVG tests; we're not pixel-diffing.
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

  // Use vm.runInContext so UMD bundles that assign to `globalThis` (Mermaid,
  // D3, Dagre, viz-js) land on the jsdom window rather than Node's own
  // globalThis. win.eval() works for plain IIFEs but not for UMDs.
  const jsdomCtx = dom.getInternalVMContext();
  function loadScript(absPath) {
    const src = fs.readFileSync(absPath, 'utf-8');
    vm.runInContext(src, jsdomCtx, { filename: absPath });
  }

  // Load order — core first, then vendor libs, then compiler utilities, then
  // every renderer. Each renderer self-registers via registerRenderer() at
  // evaluation time, replacing the stub entry in dispatcher._registry.
  loadScript(path.join(COMPILER_DIR, 'errors.js'));
  loadScript(path.join(COMPILER_DIR, 'validator.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'stub.js'));
  loadScript(path.join(COMPILER_DIR, 'dispatcher.js'));
  loadScript(path.join(COMPILER_DIR, 'index.js'));

  // Vendor libraries (order within this block is independent).
  loadScript(VENDOR_AJV);
  loadScript(VENDOR_VEGA);
  loadScript(VENDOR_VL);
  loadScript(path.join(COMPILER_DIR, 'vendor', 'mermaid', 'mermaid.min.js'));
  loadScript(path.join(COMPILER_DIR, 'vendor', 'viz-js', 'viz-standalone.js'));
  loadScript(path.join(COMPILER_DIR, 'vendor', 'd3', 'd3.min.js'));
  loadScript(path.join(COMPILER_DIR, 'vendor', 'dagre', 'dagre.min.js'));
  loadScript(path.join(COMPILER_DIR, 'vendor', 'structurizr-mini', 'parser.js'));
  loadScript(path.join(COMPILER_DIR, 'vendor', 'structurizr-mini', 'renderer.js'));

  // Compiler utilities (palettes + dot-engine + ajv-init loaded before the
  // renderers that consume them).
  loadScript(path.join(COMPILER_DIR, 'palettes.js'));
  loadScript(path.join(COMPILER_DIR, 'dot-engine.js'));
  loadScript(path.join(COMPILER_DIR, 'ajv-init.js'));

  // Renderers — each self-registers for its type(s).
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

  // Accessibility layer (WP-1.5). Loads AFTER all renderers so compile() can
  // invoke them during output enrichment.
  loadScript(path.join(COMPILER_DIR, 'alt-text-generator.js'));
  loadScript(path.join(COMPILER_DIR, 'aria-annotator.js'));
  loadScript(path.join(COMPILER_DIR, 'keyboard-nav.js'));

  // WP-2.5 — Artifact-level adversarial reviewer. Runs after the renderer
  // produces SVG; inspects layout, text truncation, and WCAG contrast. It
  // must load after the a11y modules so compile() can invoke both passes
  // in the enrichment stage, and before visual-panel so visual-panel's
  // rendering path can observe review findings on result.errors/.warnings.
  loadScript(path.join(COMPILER_DIR, 'artifact-adversarial.js'));
  loadScript(path.join(COMPILER_DIR, 'native-excalidraw.js'));

  // WP-2.1 — Konva + visual-panel. Konva is a UMD bundle that assigns to
  // globalThis.Konva (our `win.globalThis = win` aliasing lands it on
  // window.Konva). visual-panel.js is a plain IIFE that reads window.Konva
  // and window.OraVisualCompiler, and exposes window.VisualPanel +
  // window.OraPanels.visual.
  //
  // Konva needs a few extra canvas mocks beyond what Mermaid/Vega need;
  // drawImage/transform/bezierCurveTo/quadraticCurveTo/clip/gradient stubs
  // must exist on the returned 2D context. We patch the getContext mock
  // before loading Konva.
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
  loadScript(path.join(COMPILER_DIR, '..', 'vendor', 'konva', 'konva.min.js'));

  // WP-7.1.1 / WP-7.1.2 — universal toolbar registry/renderer + edge-dock
  // manager. Both load BEFORE visual-panel.js so that
  // VisualPanel.prototype._mountUniversalToolbar finds OraVisualToolbar +
  // OraVisualDock on `win` at init time. icon-resolver.js stubs / vendors
  // the Lucide bundle that visual-toolbar.js consults via OraIconResolver.
  loadScript(path.join(COMPILER_DIR, '..', 'icon-resolver.js'));
  loadScript(path.join(COMPILER_DIR, '..', 'visual-toolbar.js'));
  loadScript(path.join(COMPILER_DIR, '..', 'visual-dock.js'));

  loadScript(path.join(COMPILER_DIR, '..', 'visual-panel.js'));

  // WP-3.2 — Canvas serializer. Plain IIFE; reads window.OraVisualCompiler._ajv
  // when present for full schema validation. Load AFTER visual-panel.js so the
  // `VisualPanel` class and its userInputLayer convention are in scope when
  // tests exercise captureFromPanel().
  loadScript(path.join(COMPILER_DIR, '..', 'canvas-serializer.js'));

  // WP-5.2 — Annotation parser. Translates user annotations on annotationLayer
  // into structured pipeline instructions. Consumes VisualPanel.getUserAnnotations().
  loadScript(path.join(COMPILER_DIR, '..', 'annotation-parser.js'));

  // WP-7.0.2 — canvas-state file format reader/writer. Load before the
  // Phase 7 commands (resize-canvas / lazy-expansion) so they can pull
  // OraCanvasFileFormat.newCanvasState() at boot.
  loadScript(path.join(COMPILER_DIR, '..', 'canvas-file-format.js'));

  // WP-7.4.1 — Resize canvas command. Required by lazy-expansion.js
  // (which calls OraResizeCanvas.apply / .getCurrentSize / .computeBoundingBox).
  loadScript(path.join(COMPILER_DIR, '..', 'commands', 'resize-canvas.js'));
  loadScript(path.join(COMPILER_DIR, '..', 'commands', 'crop-to-content.js'));
  loadScript(path.join(COMPILER_DIR, '..', 'commands', 'crop-to-selection.js'));

  // WP-7.4.6 — Lazy canvas expansion. Prototype-patches VisualPanel so
  // newly-placed objects near a canvas edge silently grow the canvas.
  loadScript(path.join(COMPILER_DIR, '..', 'lazy-expansion.js'));

  // WP-7.1.1 / WP-7.1.2 — pre-register the universal toolbar JSON so
  // VisualPanel.prototype._mountUniversalToolbar finds it via
  // OraVisualToolbar.get('ora-universal') without hitting fetch (jsdom
  // has no network). Tests that want to exercise the no-toolbar path can
  // call OraVisualToolbar.clear() before constructing a panel.
  try {
    const toolbarPath = path.join(__dirname, '..', '..', '..', '..',
                                  'config', 'toolbars', 'universal.toolbar.json');
    if (fs.existsSync(toolbarPath) && win.OraVisualToolbar &&
        typeof win.OraVisualToolbar.register === 'function') {
      const toolbarDef = JSON.parse(fs.readFileSync(toolbarPath, 'utf-8'));
      try { win.OraVisualToolbar.register(toolbarDef); }
      catch (e) {
        // Validator may reject — log but continue; per-test code can
        // re-register or work around as needed.
        console.warn('WARN: universal toolbar registration failed: ' + e.message);
      }
    }
  } catch (e) {
    console.warn('WARN: universal toolbar pre-register: ' + e.message);
  }

  // Bootstrap Ajv by reading schemas from disk (no fetch in Node without deps).
  const customLoad = (url) => {
    // url format: "/static/visual-schemas/<rel>" or just "<rel>" via root.
    // Our bootstrap uses schemaRoot + rel, so url begins with schemaRoot.
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

  const result = await win.OraVisualCompiler.bootstrapAjv({ load: customLoad });
  if (!result.ok) {
    console.warn('WARN: bootstrapAjv failed: ' + result.reason + ' — continuing on Layer 1.');
  }

  return { win, ajvOk: !!result.ok };
}

// ── Test infrastructure ──────────────────────────────────────────────────────
const results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  const sigil = ok ? 'PASS' : 'FAIL';
  const line = '  ' + sigil + '  ' + name + (detail ? '  — ' + detail : '');
  console.log(line);
}

async function runSuite(label, fn, ctx) {
  console.log('\n== ' + label + ' ==');
  try {
    await fn(ctx, record);
  } catch (err) {
    record(label + ' suite', false, 'uncaught: ' + (err.stack || err.message || err));
  }
}

function runStandaloneSuite(label, relativePath) {
  const script = path.resolve(__dirname, relativePath);
  const result = spawnSync(process.execPath, [script], {
    cwd: path.dirname(script),
    encoding: 'utf8',
  });
  const output = [result.stdout, result.stderr].filter(Boolean).join('\n').trim();
  const detail = result.status === 0
    ? (output.split('\n').slice(-1)[0] || 'passed')
    : (output.split('\n').slice(-8).join(' ') || `exit ${result.status}`);
  record(label, result.status === 0, detail);
}

// ── Main ─────────────────────────────────────────────────────────────────────
(async function main() {
  console.log('Ora visual compiler — WP-1.2a test harness');
  console.log('Schemas:  ' + SCHEMAS_DIR);
  console.log('Examples: ' + EXAMPLES_DIR);

  const ctx = await bootCompiler();
  console.log('Ajv bootstrapped: ' + (ctx.ajvOk ? 'yes (Layer 2)' : 'no (Layer 1 only)'));
  console.log('Known types: ' + ctx.win.OraVisualCompiler.KNOWN_TYPES.size);

  // Suite files that export { label, run(ctx, record) } are loaded below.
  // The detailed DAG, concept-map, Mermaid, and C4 suites predate this
  // harness and remain standalone runners. They are part of this canonical
  // gate now; test-c4.js is their data-only case index, consumed by the C4
  // runner rather than registered as a second runner.
  runStandaloneSuite('detailed causal-DAG suite', './cases/test-causal-dag.js');
  runStandaloneSuite('detailed concept-map suite', './cases/test-concept-map.js');
  runStandaloneSuite('detailed Mermaid suite', './cases/test-mermaid.js');
  runStandaloneSuite('detailed C4 suite', './standalone-c4.js');

  await runSuite('native Excalidraw shared-layout contract', async ({ win }, record) => {
    const envelope = JSON.parse(fs.readFileSync(
      path.join(EXAMPLES_DIR, 'concept_map.valid.json'), 'utf8'
    ));
    const result = await Promise.resolve(win.OraVisualCompiler.compileWithNav(envelope));
    const builder = win.OraVisualCompiler.nativeExcalidraw;
    const scene = builder.buildScene(envelope, {
      assistantVisualId: 'harness-native',
      generationRevision: 1,
      layout: result.layout,
    });
    const arrows = scene.elements.filter((element) => element.type === 'arrow');
    const owned = scene.elements.every((element) => {
      const data = element.customData || {};
      return data.assistantVisualId === 'harness-native'
        && data.generationRevision === 1
        && data.semanticElementId
        && data.originalGenerationFingerprint;
    });
    const bindings = arrows.every((arrow) => arrow.startBinding && arrow.endBinding
      && scene.elements.some((element) => element.id === arrow.startBinding.elementId)
      && scene.elements.some((element) => element.id === arrow.endBinding.elementId));
    record('compiler exposes one layout reused by native scene', !!result.layout
      && scene.layout && scene.layout.nodes === result.layout.nodes);
    record('native scene has editable owned objects and bound arrows', scene.elements.length > 4
      && arrows.length > 0 && owned && bindings);

    const dagEnvelope = {
      id: 'native-dag-operators',
      type: 'causal_dag',
      spec: {
        dsl: [
          'dag {',
          '  Exposure [exposure]',
          '  Outcome [outcome]',
          '  BareNode',
          '  ReverseNode',
          '  BothNode',
          '  UndirectedNode',
          '  Exposure -> Outcome',
          '  ReverseNode <- Exposure',
          '  Exposure <-> BothNode',
          '  BothNode -- UndirectedNode',
          '}',
        ].join('\n'),
        focal_exposure: 'Exposure',
        focal_outcome: 'Outcome',
      },
    };
    const dagGraph = builder._graph(dagEnvelope);
    const dagScene = builder.buildScene(dagEnvelope, {
      assistantVisualId: 'harness-native-dag',
      generationRevision: 1,
    });
    const dagArrows = dagScene.elements.filter((element) => element.type === 'arrow');
    const arrowByOperator = (operator) => dagArrows.find((element) => (
      element.customData && element.customData.dagOperator === operator
    ));
    const exposure = dagGraph.nodes.find((node) => node.id === 'Exposure');
    record('native DAG uses roles as metadata and retains bare-node labels',
      dagGraph.nodes.some((node) => node.id === 'BareNode' && node.label === 'BareNode')
      && exposure && exposure.label === 'Exposure'
      && Array.isArray(exposure.dagRoles) && exposure.dagRoles.includes('exposure')
      && !dagGraph.nodes.some((node) => node.label === 'exposure' || node.label === 'outcome'));
    record('native DAG parser retains forward, reverse, bidirectional, and undirected edges',
      dagGraph.edges.some((edge) => edge.from === 'Exposure' && edge.to === 'Outcome'
        && edge.operator === '->')
      && dagGraph.edges.some((edge) => edge.from === 'Exposure' && edge.to === 'ReverseNode'
        && edge.operator === '->')
      && dagGraph.edges.some((edge) => edge.operator === '<->')
      && dagGraph.edges.some((edge) => edge.operator === '--'));
    record('native DAG arrowheads match parsed edge operators',
      arrowByOperator('->') && arrowByOperator('->').startArrowhead === null
      && arrowByOperator('->').endArrowhead === 'arrow'
      && arrowByOperator('<->') && arrowByOperator('<->').startArrowhead === 'arrow'
      && arrowByOperator('<->').endArrowhead === 'arrow'
      && arrowByOperator('--') && arrowByOperator('--').startArrowhead === null
      && arrowByOperator('--').endArrowhead === null
      && dagArrows.every((arrow) => arrow.width > 0 && arrow.height > 0));

    const weightedEnvelope = JSON.parse(fs.readFileSync(
      path.join(EXAMPLES_DIR, 'pro_con.valid.json'), 'utf8'
    ));
    const weightedGraph = builder._graph(weightedEnvelope);
    const weightedScene = builder.buildScene(weightedEnvelope, {
      assistantVisualId: 'harness-native-pro-con', generationRevision: 1,
    });
    record('native pro/con nodes visibly retain declared weight',
      weightedGraph.nodes.some((node) => node.argumentWeight === 4
        && node.label.includes('[weight 4/5]'))
      && weightedScene.elements.some((element) => element.type === 'text'
        && element.text.includes('[weight 4/5]')
        && element.customData.argumentWeight === 4));

    const hierarchyEnvelope = {
      id: 'native-concept-hierarchy', type: 'concept_map',
      spec: {
        focus_question: 'Does declared hierarchy control layout?',
        concepts: [
          { id: 'Deep', label: 'Declared deep', hierarchy_level: 3 },
          { id: 'Root', label: 'Declared root', hierarchy_level: 0 },
        ],
        linking_phrases: [{ id: 'p', text: 'points back to' }],
        propositions: [{ from_concept: 'Deep', via_phrase: 'p', to_concept: 'Root' }],
      },
    };
    const hierarchyGraph = builder._graph(hierarchyEnvelope);
    const hierarchyLayout = builder.buildLayout(hierarchyEnvelope);
    record('native concept-map layout retains declared hierarchy levels',
      hierarchyGraph.nodes.find((node) => node.id === 'Deep').hierarchyLevel === 3
      && hierarchyGraph.nodes.find((node) => node.id === 'Root').hierarchyLevel === 0
      && hierarchyLayout.nodes.Deep.x > hierarchyLayout.nodes.Root.x);
  }, ctx);

  const caseFiles = [
    './cases/test-envelope-valid.js',
    './cases/test-envelope-invalid.js',
    './cases/test-vega-lite.js',
    './cases/test-causal-loop-diagram.js',
    './cases/test-stock-and-flow.js',
    './cases/test-fishbone.js',
    './cases/test-decision-tree.js',
    './cases/test-influence-diagram.js',
    './cases/test-ach-matrix.js',
    './cases/test-quadrant-matrix.js',
    './cases/test-bow-tie.js',
    './cases/test-ibis.js',
    './cases/test-pro-con.js',
    './cases/test-accessibility.js',
    './cases/test-visual-panel.js',
    './cases/test-canvas-action.js',
    './cases/test-artifact-adversarial.js',
    './cases/test-canvas-serializer.js',
    './cases/test-canvas-file-format.js',
    './cases/test-lazy-expansion.js',
    './cases/test-shape-tools.js',
    './cases/test-annotation-tools.js',
    './cases/test-v3-visual-dispatch.js',
    './cases/test-spatial-reasoning-e2e.js',
    './cases/test-image-upload.js',
    './cases/test-visual-fallback.js',
    './cases/test-render-envelope-cli.js',
    './cases/test-annotation-parser.js',
    './cases/test-toolbar-docking.js',
    './cases/test-icon-size.js',
    './cases/test-visual-slots-pane.js',
    './cases/test-styles-pane-guided.js',
    './cases/test-sidebar-triggers.js',
  ];
  for (const rel of caseFiles) {
    const mod = require(path.resolve(__dirname, rel));
    await runSuite(mod.label, mod.run, { ...ctx, EXAMPLES_DIR, SCHEMAS_DIR });
  }

  const pass = results.filter(r => r.ok).length;
  const fail = results.length - pass;
  console.log('\n=================================');
  console.log('Results: ' + pass + '/' + results.length + ' passed, ' + fail + ' failed.');
  if (fail > 0) {
    console.log('\nFailures:');
    for (const r of results) if (!r.ok) console.log('  - ' + r.name + ': ' + r.detail);
    process.exit(1);
  }
  process.exit(0);
})().catch(err => {
  console.error('FATAL:', err);
  process.exit(2);
});
