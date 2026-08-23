#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const modules = path.resolve(
  __dirname, '..', 'ora-visual-compiler', 'tests', 'node_modules'
);
const { JSDOM } = require(path.join(modules, 'jsdom'));

const dom = new JSDOM(
  '<!doctype html><html><body><section class="visual-pane-shell">'
    + '<div class="right-pane"></div><div id="visualPaneFooter">'
    + '<span id="visualPaneFooterStatus"></span></div></section>'
    + '<button id="visualEditorSwitch" type="button"></button>'
    + '<div id="logo-o"></div></body></html>',
  { url: 'http://localhost/', runScripts: 'outside-only', pretendToBeVisual: true }
);
const w = dom.window;
const context = dom.getInternalVMContext();
context.console = console;
w.globalThis = w;
w.console = console;

w.HTMLCanvasElement.prototype.getContext = function () {
  return {
    canvas: this,
    measureText(text) { return { width: String(text || '').length * 6 }; },
    fillText() {}, save() {}, restore() {}, scale() {}, translate() {}, rotate() {},
    beginPath() {}, closePath() {}, fillRect() {}, strokeRect() {}, clearRect() {},
    moveTo() {}, lineTo() {}, stroke() {}, fill() {}, arc() {}, rect() {}, drawImage() {},
    transform() {}, setTransform() {}, bezierCurveTo() {}, quadraticCurveTo() {}, clip() {},
    getImageData() { return { data: new Uint8ClampedArray(4) }; },
    putImageData() {}, createImageData() { return { data: new Uint8ClampedArray(4) }; },
    createLinearGradient() { return { addColorStop() {} }; },
    createRadialGradient() { return { addColorStop() {} }; },
    createPattern() { return null; },
    globalAlpha: 1,
  };
};
if (w.SVGElement && !w.SVGElement.prototype.getBBox) {
  w.SVGElement.prototype.getBBox = function () {
    return { x: 10, y: 10, width: 40, height: 20 };
  };
}

function load(relativePath) {
  const filename = path.resolve(__dirname, '..', relativePath);
  vm.runInContext(fs.readFileSync(filename, 'utf8'), context, { filename });
}

load('vendor/konva/konva.min.js');
w.OraVisualCompiler = {
  compileWithNav() {
    return {
      svg: '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80">'
        + '<rect id="artifact-node" x="10" y="10" width="40" height="20"/></svg>',
      ariaDescription: {
        root_id: 'artifact-node',
        nodes: [{ id: 'artifact-node', level: 1, parent_id: null, children_ids: [] }],
      },
      errors: [],
    };
  },
};
load('visual-panel.js');

w.OraSaveCanvas = {
  buildCanvasState(panel) {
    const objects = [];
    if (panel._currentEnvelope) objects.push({ kind: 'artifact' });
    if (panel._backgroundImageNode) objects.push({ kind: 'image' });
    if (panel.userInputLayer) {
      panel.userInputLayer.find('.user-shape').forEach(() => objects.push({ kind: 'shape' }));
    }
    if (panel.annotationLayer) {
      panel.annotationLayer.getChildren().forEach(() => objects.push({ kind: 'annotation' }));
    }
    return { objects };
  },
  saveImmediate() { return Promise.resolve(); },
};
w.OraExcalidrawIsland = {
  mount(host) {
    return { unmount() {}, host };
  },
};

load('js/v3-canvas-mount.js');

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
const tests = [];
function test(name, fn) { tests.push({ name, fn }); }
function assert(condition, message) {
  if (!condition) throw new Error(message);
}
function shapeCount(panel) { return panel.userInputLayer.find('.user-shape').length; }
function userAnnotationCount(panel) {
  return panel.annotationLayer.getChildren().filter(
    (node) => node.getAttr && node.getAttr('annotationSource') === 'user'
  ).length;
}

test('Konva user Clear is one frame and one Undo restores all canvas content', async () => {
  await tick();
  const panel = w.OraCanvas.panel;
  const envelope = { id: 'artifact-envelope', type: 'concept_map', spec: {} };
  await panel.renderSpec(envelope);
  const shape = panel._createShape('rect', {
    x: 20, y: 30, width: 80, height: 50, userLabel: 'drawing',
  });
  const annotation = panel._createUserAnnotation('sticky', {
    text: 'annotation', position: { x: 110, y: 70 },
  });
  const image = new w.File([new Uint8Array([137, 80, 78, 71])], 'upload.png', {
    type: 'image/png',
  });
  await panel.attachImage(image);
  await tick();
  panel._transform = { x: 37, y: -12, scale: 1.4 };
  panel._applyTransform();
  panel._selectedShapeIds = [shape.getAttr('userShapeId')];
  panel._selectedAnnotIds = [annotation.getAttr('userAnnotationId')];
  panel._focusNavId('artifact-node');
  panel._redrawSelection();
  panel._redrawAnnotationSelection();
  const drawPreview = new w.Konva.Rect({ name: 'user-shape-preview' });
  const selectionPreview = new w.Konva.Rect({ name: 'vp-selection-marquee' });
  const penPreview = new w.Konva.Line({ name: 'vp-pen-preview', points: [0, 0, 2, 2] });
  panel.userInputLayer.add(drawPreview);
  panel.selectionLayer.add(selectionPreview);
  panel.annotationLayer.add(penPreview);
  panel._drawContext = { preview: drawPreview };
  panel._selectionDrag = { preview: selectionPreview };
  panel._penContext = { line: penPreview };
  panel._textInputEl = w.document.createElement('input');
  panel._annotInputEl = w.document.createElement('input');
  panel._viewportEl.appendChild(panel._textInputEl);
  panel._viewportEl.appendChild(panel._annotInputEl);
  const historyBefore = panel.getHistoryLength();

  w.OraCanvas.clearForUser();
  assert(panel.getHistoryLength() === historyBefore + 1, 'Clear did not add exactly one frame');
  assert(panel._currentEnvelope === null && panel._svgHost.innerHTML === '', 'artifact survived Clear');
  assert(shapeCount(panel) === 0 && userAnnotationCount(panel) === 0, 'drawing or annotation survived Clear');
  assert(panel.getPendingImage() === null && panel._backgroundImageNode === null, 'uploaded image survived Clear');
  assert(panel._drawContext === null && panel._selectionDrag === null && panel._penContext === null
    && panel._textInputEl === null && panel._annotInputEl === null,
  'Clear did not cancel every in-progress interaction');
  assert(panel._bgSentinel && panel._bgSentinel.getAttr('name') === 'svg-sentinel',
    'Clear did not leave a valid empty background sentinel');
  assert(panel._transform.x === 37 && panel._transform.y === -12 && panel._transform.scale === 1.4,
    'Clear changed the viewport');

  assert(panel.undo() === true, 'one Undo did not consume the Clear frame');
  assert(panel._currentEnvelope === envelope && panel._ariaDescription.root_id === 'artifact-node',
    'artifact envelope or ARIA description was not restored');
  assert(panel._svgHost.querySelector('#artifact-node'), 'SVG host contents were not restored');
  assert(shapeCount(panel) === 1 && userAnnotationCount(panel) === 1,
    'drawing or annotation was not restored');
  assert(panel.getPendingImage() && panel.getPendingImage().name === 'upload.png'
    && panel._backgroundImageNode, 'uploaded image and pending-image state were not restored');
  assert(panel._bgSentinel && panel._bgSentinel.getAttr('name') === 'svg-sentinel',
    'background sentinel state was not restored');
  assert(panel._selectedShapeIds.length === 1 && panel._selectedAnnotIds.length === 1
    && panel._selectedNodeId === 'artifact-node', 'selection state was not restored');
});

test('lifecycle reset empties Konva history so Undo restores nothing', async () => {
  const panel = w.OraCanvas.panel;
  w.OraCanvas.reset();
  panel._createShape('ellipse', { x: 15, y: 15, radiusX: 20, radiusY: 15 });
  assert(panel.getHistoryLength() > 0 && shapeCount(panel) === 1, 'reset fixture did not populate');
  w.OraCanvas.reset();
  assert(panel.getHistoryLength() === 0 && panel.getHistoryCursor() === 0, 'reset retained history');
  assert(shapeCount(panel) === 0 && panel.undo() === false && shapeCount(panel) === 0,
    'Undo crossed the lifecycle boundary');
});

test('keydown from inside Excalidraw never reaches Konva history or preventDefault', async () => {
  const panel = w.OraCanvas.panel;
  panel._createShape('rect', { x: 5, y: 5, width: 30, height: 30 });
  const cursorBefore = panel.getHistoryCursor();
  const island = w.document.querySelector('.ora-excalidraw-island');
  const target = w.document.createElement('button');
  island.appendChild(target);
  const event = new w.KeyboardEvent('keydown', {
    key: 'z', metaKey: true, bubbles: true, cancelable: true,
  });
  target.dispatchEvent(event);
  assert(panel.getHistoryCursor() === cursorBefore, 'Konva history moved for an Excalidraw event');
  assert(event.defaultPrevented === false, 'Konva prevented the Excalidraw event default');
});

(async () => {
  let failures = 0;
  for (const item of tests) {
    try {
      await item.fn();
      console.log('PASS ' + item.name);
    } catch (error) {
      failures += 1;
      console.error('FAIL ' + item.name + ': ' + (error.stack || error.message || error));
    }
  }
  if (tests.length !== 3) {
    console.error('FAIL expected exactly three tests, found ' + tests.length);
    failures += 1;
  }
  process.exitCode = failures ? 1 : 0;
})();
