#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const modules = path.resolve(
  __dirname, '..', 'ora-visual-compiler', 'tests', 'node_modules'
);
const { JSDOM } = require(path.join(modules, 'jsdom'));
const source = fs.readFileSync(
  path.resolve(__dirname, '..', 'js', 'v3-canvas-mount.js'), 'utf8'
);
const nativeSource = fs.readFileSync(
  path.resolve(__dirname, '..', 'ora-visual-compiler', 'native-excalidraw.js'), 'utf8'
);
const dom = new JSDOM(
  '<!doctype html><html><body><section class="visual-pane-shell">'
    + '<div class="right-pane"></div><div id="visualPaneFooter">'
    + '<span id="visualPaneFooterStatus"></span>'
    + '<div id="visualZoomFallback" role="group" aria-label="Canvas zoom controls">'
    + '<button data-visual-zoom="out" aria-label="Zoom out"></button>'
    + '<button data-visual-zoom="reset" aria-label="Reset zoom to 100%">'
    + '<span id="visualZoomValue">100%</span></button>'
    + '<button data-visual-zoom="in" aria-label="Zoom in"></button></div>'
    + '<div id="visualExportMenu"><button id="visualExportButton" disabled '
    + 'aria-haspopup="menu" aria-expanded="false"></button>'
    + '<div id="visualExportMenuPopup" role="menu" hidden>'
    + '<button role="menuitem" data-export-format="png">PNG</button>'
    + '<button role="menuitem" data-export-format="jpeg">JPEG</button>'
    + '<button role="menuitem" data-export-format="svg">SVG</button>'
    + '<button role="menuitem" data-export-format="pdf">PDF</button>'
    + '</div></div></div></section>'
    + '<button id="visualEditorSwitch" type="button"></button>'
    + '<div id="logo-o"></div>'
    + '</body></html>',
  { url: 'http://localhost/', runScripts: 'outside-only', pretendToBeVisual: true }
);
const w = dom.window;
let canvasStateEvents = 0;
w.document.addEventListener('ora:canvas-state-changed', () => { canvasStateEvents += 1; });
const calls = [];
const sceneLoads = [];
const checkpoints = new Map();
const visualStates = [];
const drafts = new Map();
let islandOptions = null;
let islandHost = null;
let checkpointCounter = 0;
let checkpointFailure = null;
let imageBackedCalls = 0;
let assistantImageCalls = 0;
let capabilityImageCalls = 0;
let konvaAttachCalls = 0;
let konvaArtifactClearCalls = 0;
let konvaPendingImageClearCalls = 0;
let konvaEmptyStateLoadCalls = 0;
let stageRevision = 'baseline';
let stageWidth = 100;
let stageHeight = 100;
let stagePosition = { x: 0, y: 0 };
let stageScale = { x: 1, y: 1 };
let liveObjects = [{ id: 'flattened', x: 0, y: 0, width: 100, height: 100 }];
let currentKonva = null;
const assistantEvents = [];
const compiledEnvelopeIds = [];
const exportRoutes = [];
const downloadedFilenames = [];
let shareGateCalls = 0;
const rasterFixtures = new Map();

const layer = {
  on() {},
  getChildren() { return []; },
};
function VisualPanel(element, config) {
  this.el = element;
  this.config = config;
  this.panelId = config.id;
  this.userInputLayer = layer;
  this.stage = {
    width() { return stageWidth; },
    height() { return stageHeight; },
    position(value) {
      if (value) stagePosition = { x: value.x, y: value.y };
      return { x: stagePosition.x, y: stagePosition.y };
    },
    scale(value) {
      if (value) stageScale = { x: value.x, y: value.y };
      return { x: stageScale.x, y: stageScale.y };
    },
    batchDraw() {},
    toDataURL(options) {
      return 'data:image/png;base64,' + [
        stageRevision, options.x, options.y, options.width, options.height,
        stagePosition.x, stagePosition.y, stageScale.x, stageScale.y,
      ].join(':');
    },
  };
}
VisualPanel.prototype.init = function () {};
VisualPanel.prototype.clearArtifact = function () { konvaArtifactClearCalls += 1; };
VisualPanel.prototype.clearPendingImage = function () {
  konvaPendingImageClearCalls += 1;
  liveObjects = [];
};
VisualPanel.prototype.loadCanvasState = function (state) {
  if (state && Array.isArray(state.objects) && state.objects.length === 0) {
    konvaEmptyStateLoadCalls += 1;
  }
};
VisualPanel.prototype.attachImage = function () {
  konvaAttachCalls += 1;
  liveObjects = [{
    id: 'bg-image', kind: 'image', layer: 'background',
    x: 0, y: 0, width: 100, height: 100,
  }];
  return Promise.resolve({ ok: true });
};

const api = {
  elements: [],
  appState: {},
  files: {},
  getSceneElements() { return this.elements; },
  getAppState() { return this.appState; },
  getFiles() { return this.files; },
  resetScene() { this.elements = []; this.files = {}; },
  addFiles(files) {
    files.forEach((file) => { this.files[file.id] = file; });
  },
  updateScene(scene) {
    if (scene.elements) this.elements = scene.elements;
    if (scene.appState) this.appState = { ...this.appState, ...scene.appState };
    if (scene.files) this.files = scene.files;
    // Exercise the real hazard: Excalidraw reports programmatic updates.
    islandOptions.onChange(this.elements, this.appState, this.files);
  },
  scrollToContent() {},
};

w.Konva = {};
w.VisualPanel = VisualPanel;
w.OraPanels = { visual: {} };
w.OraCanvasSerializer = { captureFromPanel() { return null; } };
w.OraSaveCanvas = {
  buildCanvasState() { return { objects: liveObjects, view: {
    zoom: stageScale.x, pan: stagePosition,
  } }; },
  computeContentExtent(state, margin) {
    if (!state.objects.length) return null;
    const object = state.objects[0];
    return {
      x: object.x - margin, y: object.y - margin,
      width: object.width + margin * 2,
      height: object.height + margin * 2,
    };
  },
  boundStateToContent(state) { return { state }; },
};
w.OraCanvasFileFormat = {
  write() { return Promise.resolve(new Uint8Array([1])); },
  read() { return Promise.resolve({ objects: [] }); },
};
w.OraExcalidrawIsland = {
  mount(_host, options) {
    islandHost = _host;
    islandOptions = options;
    options.onReady(api);
    // Real Excalidraw reports its initial empty scene during mount. This must
    // not dirty the default or next Dialogue before an explicit load/clear.
    options.onChange(api.elements, api.appState, api.files);
    return { unmount() {} };
  },
  load(blob) {
    sceneLoads.push(blob.marker);
    assistantEvents.push('checkpoint-loaded:' + blob.marker);
    if (blob.marker === 'corrupt-history') {
      return Promise.reject(new Error('corrupt Excalidraw scene'));
    }
    return Promise.resolve({
      elements: blob.elements
        ? blob.elements.map((element) => ({ ...element }))
        : [{ id: blob.marker, type: 'rectangle' }],
      appState: { ...(blob.appState || {}) },
      files: Object.fromEntries(Object.entries(blob.files || {}).map(
        ([id, file]) => [id, { ...file }]
      )),
    });
  },
  serialize(snapshot) {
    const blob = new w.Blob([JSON.stringify(snapshot.elements)]);
    blob.marker = snapshot.elements[0] ? snapshot.elements[0].id : 'empty';
    blob.elements = snapshot.elements.map((element) => ({ ...element }));
    return blob;
  },
  canonicalPng() { return Promise.resolve(new w.Blob(['png'], { type: 'image/png' })); },
  exportJpeg() {
    exportRoutes.push('excalidraw:jpeg');
    return Promise.resolve(new w.Blob(['jpeg'], { type: 'image/jpeg' }));
  },
  exportSvg() {
    exportRoutes.push('excalidraw:svg');
    return Promise.resolve(new w.Blob(['svg'], { type: 'image/svg+xml' }));
  },
  imageBackedScene(_png, locked, customData) {
    let id = 'image-backed-B';
    if (customData && customData.oraAssistantVisual) {
      assistantImageCalls += 1;
      id = 'assistant-png-' + assistantImageCalls;
      assistantEvents.push('png-inserted:' + locked);
    } else if (customData && customData.oraCapabilityOutput) {
      capabilityImageCalls += 1;
      id = 'capability-png-' + capabilityImageCalls;
    } else {
      imageBackedCalls += 1;
    }
    return Promise.resolve({
      elements: [{
        id, type: 'image', locked, customData,
        fileId: id,
        x: 0, y: 0, width: 100, height: 100,
      }],
      appState: {}, files: { [id]: { id } },
    });
  },
};
w.OraExportRaster = {
  _runShareGate() {
    shareGateCalls += 1;
    return Promise.resolve({ confirmed: true });
  },
  _triggerDownload(_dataUrl, filename) {
    downloadedFilenames.push(filename);
    if (/\.png$/.test(filename)) exportRoutes.push('excalidraw:png');
  },
  exportPNG(_panel, options) {
    shareGateCalls += 1;
    exportRoutes.push('konva:png');
    downloadedFilenames.push(options.filename);
    return Promise.resolve({ ok: true });
  },
  exportJPG(_panel, options) {
    shareGateCalls += 1;
    exportRoutes.push('konva:jpeg');
    downloadedFilenames.push(options.filename);
    return Promise.resolve({ ok: true });
  },
};
w.OraExportSVG = {
  exportNow(_panel, options) {
    shareGateCalls += 1;
    exportRoutes.push('konva:svg');
    downloadedFilenames.push(options.filename);
    return Promise.resolve({ ok: true });
  },
};
w.OraExportPdf = {
  buildPdf() {
    return { doc: { save(filename) {
      exportRoutes.push('excalidraw:pdf');
      downloadedFilenames.push(filename);
    } } };
  },
  apply(_panel, options) {
    shareGateCalls += 1;
    exportRoutes.push('konva:pdf');
    downloadedFilenames.push(options.filename);
    return Promise.resolve({ ok: true });
  },
};
w.OraVisualCompiler = {
  compileWithNav(envelope) {
    compiledEnvelopeIds.push(envelope.id);
    assistantEvents.push('compiled:' + envelope.id);
    return { svg: '<svg width="10" height="10"></svg>', errors: [] };
  },
};
w.URL.createObjectURL = function () { return 'blob:assistant-svg'; };
w.URL.revokeObjectURL = function () {};

// Deterministic raster stubs: canonical Konva output changes only when the
// stage data URL changes, allowing byte-for-byte baseline comparison.
w.Image = class {
  set src(value) {
    this._src = value;
    const fixture = rasterFixtures.get(value);
    this.naturalWidth = fixture ? fixture.width : 100;
    this.naturalHeight = fixture ? fixture.height : 100;
    this._rgba = fixture && fixture.rgba;
    setTimeout(() => this.onload && this.onload(), 0);
  }
  get src() { return this._src; }
};
const originalCreateElement = w.document.createElement.bind(w.document);
w.document.createElement = function (name, options) {
  if (String(name).toLowerCase() !== 'canvas') return originalCreateElement(name, options);
  let raster = '';
  let drawnImage = null;
  return {
    width: 0,
    height: 0,
    getContext() {
      return {
        fillStyle: '',
        fillRect() {},
        drawImage(image) {
          drawnImage = image;
          raster += image.src || '';
        },
        getImageData() {
          return { data: drawnImage && drawnImage._rgba
            ? drawnImage._rgba : new w.Uint8ClampedArray([0, 0, 0, 255]) };
        },
      };
    },
    toBlob(callback) { callback(new w.Blob([raster], { type: 'image/png' })); },
  };
};

w.fetch = function (url, options = {}) {
  calls.push({
    url: String(url),
    method: options.method || 'GET',
    conversationId: options.body && typeof options.body.get === 'function'
      ? options.body.get('conversation_id') : null,
  });
  if (String(url).startsWith('data:image/')) {
    return Promise.resolve({
      ok: true,
      blob() { return Promise.resolve(new w.Blob(['capability'], { type: 'image/png' })); },
    });
  }
  if (String(url).includes('draft=excalidraw')) {
    const parsed = new URL(String(url), 'http://localhost/');
    const id = decodeURIComponent(parsed.pathname.split('/').pop());
    const storedDraft = drafts.get(id);
    return Promise.resolve({
      ok: true,
      headers: { get() { return 'excalidraw'; } },
      blob() { return Promise.resolve(storedDraft || { marker: 'current-B' }); },
    });
  }
  if (String(url).includes('checkpoint=')) {
    const parsed = new URL(String(url), 'http://localhost/');
    const id = parsed.searchParams.get('checkpoint');
    const stored = checkpoints.get(id);
    return Promise.resolve({
      ok: !!stored || id === '20260813T123456123456Z-deadbeef',
      headers: { get() { return stored ? stored.editor : 'excalidraw'; } },
      blob() {
        if (stored) return Promise.resolve(parsed.searchParams.get('preview') ? stored.preview : stored.native);
        return Promise.resolve({ marker: 'historical-A' });
      },
    });
  }
  if (String(url) === '/api/canvas/checkpoint') {
    if (checkpointFailure) {
      return Promise.resolve({
        ok: false,
        status: 500,
        json() { return Promise.resolve(checkpointFailure); },
      });
    }
    const id = 'checkpoint-' + (++checkpointCounter);
    const native = options.body.get('native');
    if (options.body.get('editor') === 'excalidraw') {
      native.marker = api.elements[0] ? api.elements[0].id : 'empty';
    }
    checkpoints.set(id, {
      editor: options.body.get('editor'),
      native,
      preview: options.body.get('preview'),
    });
    return Promise.resolve({ ok: true, json() { return Promise.resolve({ checkpoint_id: id }); } });
  }
  if (String(url).includes('/api/canvas/visual-state/')) {
    visualStates.push(JSON.parse(options.body).visual_state);
    return Promise.resolve({ ok: true, json() { return Promise.resolve({ ok: true }); } });
  }
  if (String(url) === '/api/canvas/draft') {
    const scene = options.body.get('scene');
    return scene.text().then((serialized) => {
      const elements = JSON.parse(serialized);
      drafts.set(options.body.get('conversation_id'), {
        marker: elements[0] ? elements[0].id : 'empty', elements,
      });
      return { ok: true };
    });
  }
  if (String(url) === '/api/canvas/save') {
    currentKonva = options.body.get('canvas');
    return Promise.resolve({ ok: true });
  }
  if (/\/api\/canvas\/load\/[^?]+$/.test(String(url))) {
    return Promise.resolve({
      ok: !!currentKonva,
      headers: { get() { return currentKonva ? 'konva' : null; } },
      blob() { return Promise.resolve(currentKonva); },
    });
  }
  throw new Error('unexpected fetch: ' + url);
};

const context = dom.getInternalVMContext();
context.console = console;
context.fetch = w.fetch;
context.VisualPanel = VisualPanel;
context.Konva = w.Konva;
vm.runInContext(nativeSource, context, { filename: 'native-excalidraw.js' });
vm.runInContext(source, context, { filename: 'v3-canvas-mount.js' });

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
const exportThroughMenu = async (format) => {
  const button = w.document.getElementById('visualExportButton');
  const popup = w.document.getElementById('visualExportMenuPopup');
  button.click();
  if (popup.hidden) throw new Error('Export menu did not open');
  popup.querySelector(`[data-export-format="${format}"]`).click();
  for (let index = 0; index < 12 && button.disabled; index += 1) await tick();
  if (button.disabled) throw new Error(`${format} export did not finish`);
};

(async () => {
  await tick();
  islandOptions.onChange([], {
    zoom: { value: 2 }, scrollX: 5, scrollY: -3,
  }, {});
  const excalHost = islandHost;
  if (excalHost.style.getPropertyValue('--ora-excal-grid-size') !== '48px'
      || excalHost.style.getPropertyValue('--ora-excal-grid-x') !== '34px'
      || excalHost.style.getPropertyValue('--ora-excal-grid-y') !== '18px') {
    throw new Error('Excalidraw dot grid did not track zoom and pan: '
      + JSON.stringify({
        size: excalHost.style.getPropertyValue('--ora-excal-grid-size'),
        x: excalHost.style.getPropertyValue('--ora-excal-grid-x'),
        y: excalHost.style.getPropertyValue('--ora-excal-grid-y'),
      }));
  }
  const zoomGroup = w.document.getElementById('visualZoomFallback');
  if (!zoomGroup || zoomGroup.getAttribute('role') !== 'group'
      || zoomGroup.querySelectorAll('[data-visual-zoom]').length !== 3
      || w.document.querySelector('.visual-pane-shell').dataset.activeEditor !== 'excalidraw') {
    throw new Error('narrow Excalidraw zoom controls are not present and reachable');
  }
  api.appState = {
    zoom: { value: 1 }, scrollX: 0, scrollY: 0, offsetLeft: 0, offsetTop: 0,
  };
  const wheelCanvas = originalCreateElement('canvas');
  wheelCanvas.className = 'excalidraw__canvas';
  islandHost.appendChild(wheelCanvas);
  const wheel = new w.WheelEvent('wheel', {
    bubbles: true, cancelable: true, deltaY: -100, clientX: 40, clientY: 30,
  });
  wheelCanvas.dispatchEvent(wheel);
  const wheelState = api.getAppState();
  const wheelZoom = wheelState.zoom.value;
  const anchoredX = 40 / wheelZoom - wheelState.scrollX;
  const anchoredY = 30 / wheelZoom - wheelState.scrollY;
  if (!wheel.defaultPrevented || wheelZoom <= 1
      || Math.abs(anchoredX - 40) > 0.0001
      || Math.abs(anchoredY - 30) > 0.0001) {
    throw new Error('ordinary wheel did not zoom around the pointer without native panning');
  }
  // A user edit made while the old Dialogue is visible may become dirty after
  // load() starts but before its target envelope resolves. Binding dirtiness
  // to its owner prevents the subsequent target load from stealing the draft.
  w.OraCanvas.setConversationContext('old-dialogue', '');
  w.OraCanvas.clear();
  await Promise.resolve();
  api.elements = [{ id: 'dirty-old-scene', type: 'rectangle' }];
  islandOptions.onChange(api.elements, api.appState, api.files);
  w.OraCanvas.setConversationContext('target-dialogue', '');
  const stateEventsBeforeLoad = canvasStateEvents;
  await w.OraCanvas.loadCheckpoint(
    'target-dialogue', '20260813T123456123456Z-deadbeef', null,
    { active_editor: 'excalidraw' }, { preferDraft: true }
  );
  await tick();

  const draftPosts = calls.filter(
    (call) => call.url === '/api/canvas/draft' && call.method === 'POST'
  );
  if (draftPosts.length !== 1 || draftPosts[0].conversationId !== 'old-dialogue') {
    throw new Error('dirty old scene was written under target Dialogue: '
      + JSON.stringify(draftPosts));
  }
  if (sceneLoads[0] !== 'current-B'
      || canvasStateEvents !== stateEventsBeforeLoad + 1
      || w.document.getElementById('visualExportButton').disabled) {
    throw new Error('current-dialogue load did not refresh the non-empty canvas/export state once');
  }

  const exportButton = w.document.getElementById('visualExportButton');
  const exportPopup = w.document.getElementById('visualExportMenuPopup');
  exportButton.dispatchEvent(new w.KeyboardEvent('keydown', {
    key: 'ArrowDown', bubbles: true, cancelable: true,
  }));
  if (exportPopup.hidden || w.document.activeElement.dataset.exportFormat !== 'png') {
    throw new Error('Export menu keyboard opening did not focus its first format');
  }
  exportPopup.dispatchEvent(new w.KeyboardEvent('keydown', {
    key: 'Escape', bubbles: true, cancelable: true,
  }));
  if (!exportPopup.hidden || w.document.activeElement !== exportButton) {
    throw new Error('Export menu Escape handling did not close and restore focus');
  }
  exportButton.click();
  w.document.body.dispatchEvent(new w.Event('pointerdown', { bubbles: true }));
  if (!exportPopup.hidden) throw new Error('Export menu did not close outside');
  for (const format of ['png', 'jpeg', 'svg', 'pdf']) await exportThroughMenu(format);
  if (exportRoutes.join(',') !== 'excalidraw:png,excalidraw:jpeg,excalidraw:svg,excalidraw:pdf'
      || shareGateCalls !== 4
      || downloadedFilenames.map((name) => path.extname(name)).join(',') !== '.png,.jpg,.svg,.pdf') {
    throw new Error('Excalidraw Export menu did not route four formats through one share gate each: '
      + JSON.stringify({ exportRoutes, shareGateCalls, downloadedFilenames }));
  }

  w.OraCanvas.setConversationContext('privacy-parent', '');
  api.elements = [{ id: 'privacy-parent-visual', type: 'rectangle' }];
  const privacySnapshot = w.OraCanvas.snapshotForSubmit();
  w.OraCanvas.setConversationContext('privacy-child', 'private');
  api.elements = [];
  await w.OraCanvas.persistSnapshotDraft(privacySnapshot);
  if (drafts.has('privacy-parent')
      || !drafts.get('privacy-child')
      || drafts.get('privacy-child').marker !== 'privacy-parent-visual') {
    throw new Error('carried privacy snapshot was not persisted under child ownership');
  }

  await w.OraCanvas.loadCheckpoint(
    'target-dialogue', '20260813T123456123456Z-deadbeef', null,
    { active_editor: 'excalidraw' }, { preferDraft: false }
  );
  if (sceneLoads[1] !== 'historical-A') {
    throw new Error('historical navigation did not load exact checkpoint A');
  }

  const legacyWhiteDataURL = 'data:image/png;base64,bGVnYWN5LXdoaXRl';
  const nonwhiteDataURL = 'data:image/png;base64,bm9ud2hpdGU=';
  rasterFixtures.set(legacyWhiteDataURL, {
    width: 2, height: 2, rgba: new w.Uint8ClampedArray(16).fill(255),
  });
  const nonwhitePixels = new w.Uint8ClampedArray(16).fill(255);
  nonwhitePixels[0] = 254;
  rasterFixtures.set(nonwhiteDataURL, { width: 2, height: 2, rgba: nonwhitePixels });
  const legacyImage = (id, dataURL, customData) => ({
    marker: id,
    elements: [{
      id: `${id}-element`, type: 'image', locked: true,
      fileId: `ora-image-${id}`, customData,
    }],
    appState: { legacyStateMarker: id },
    files: {
      [`ora-image-${id}`]: {
        id: `ora-image-${id}`, dataURL, mimeType: 'image/png',
      },
    },
  });
  checkpoints.set('legacy-white', {
    editor: 'excalidraw', native: legacyImage('white', legacyWhiteDataURL),
    preview: new w.Blob(['legacy-white'], { type: 'image/png' }),
  });
  await w.OraCanvas.loadCheckpoint(
    'target-dialogue', 'legacy-white', null,
    { active_editor: 'excalidraw' }, { currentDialogue: false, preferDraft: false }
  );
  if (api.elements.length !== 0 || Object.keys(api.files).length !== 0
      || api.appState.legacyStateMarker !== 'white') {
    throw new Error('opaque-white legacy singleton did not normalize while retaining appState');
  }
  checkpoints.set('legacy-marked', {
    editor: 'excalidraw',
    native: legacyImage('marked', legacyWhiteDataURL, { oraAssistantVisual: true }),
    preview: new w.Blob(['legacy-marked'], { type: 'image/png' }),
  });
  await w.OraCanvas.loadCheckpoint(
    'target-dialogue', 'legacy-marked', null,
    { active_editor: 'excalidraw' }, { currentDialogue: false, preferDraft: false }
  );
  if (api.elements.length !== 1 || api.elements[0].id !== 'marked-element'
      || !api.files['ora-image-marked']) {
    throw new Error('marked opaque-white image was incorrectly normalized');
  }
  checkpoints.set('legacy-nonwhite', {
    editor: 'excalidraw', native: legacyImage('nonwhite', nonwhiteDataURL),
    preview: new w.Blob(['legacy-nonwhite'], { type: 'image/png' }),
  });
  await w.OraCanvas.loadCheckpoint(
    'target-dialogue', 'legacy-nonwhite', null,
    { active_editor: 'excalidraw' }, { currentDialogue: false, preferDraft: false }
  );
  if (api.elements.length !== 1 || api.elements[0].id !== 'nonwhite-element'
      || !api.files['ora-image-nonwhite']) {
    throw new Error('nonwhite flattened image was incorrectly normalized');
  }

  assistantEvents.length = 0;
  compiledEnvelopeIds.length = 0;
  const draftCountBeforeAssistant = calls.filter(
    (call) => call.url === '/api/canvas/draft' && call.method === 'POST'
  ).length;
  await w.OraCanvas.loadCheckpoint(
    'target-dialogue', '20260813T123456123456Z-deadbeef', null,
    { active_editor: 'excalidraw' }, { currentDialogue: false, preferDraft: false }
  );
  const stateEventsBeforeAssistant = canvasStateEvents;
  await w.OraPanels.visual.onBridgeUpdate({ ora_visual_blocks: [
    { envelope: { id: 'assistant-one', type: 'comparison', canvas_action: 'replace' } },
    { envelope: { id: 'assistant-two', type: 'comparison', canvas_action: 'annotate' } },
  ], ora_visual_dispatch_key: 'target-dialogue#0' });
  const draftCountAfterAssistant = calls.filter(
    (call) => call.url === '/api/canvas/draft' && call.method === 'POST'
  ).length;
  if (assistantEvents[0] !== 'checkpoint-loaded:historical-A'
      || compiledEnvelopeIds.join(',') !== 'assistant-one'
      || assistantEvents.filter((event) => event === 'png-inserted:true').length !== 1
      || canvasStateEvents !== stateEventsBeforeAssistant + 1
      || w.document.getElementById('visualExportButton').disabled
      || draftCountAfterAssistant !== draftCountBeforeAssistant) {
    throw new Error('historical assistant blocks did not load checkpoint, preserve unsupported annotation, and avoid drafting: '
      + JSON.stringify({ assistantEvents, compiledEnvelopeIds,
        draftCountBeforeAssistant, draftCountAfterAssistant }));
  }

  await w.OraCanvas.loadCheckpoint(
    'target-dialogue', '20260813T123456123456Z-deadbeef', null,
    { active_editor: 'excalidraw' }, { currentDialogue: true, preferDraft: true }
  );
  await tick();
  api.elements = [{ id: 'unsent-latest-draft', type: 'rectangle' }];
  islandOptions.onChange(api.elements, api.appState, api.files);
  await w.OraCanvas.flushDraft();
  const unsentDraftWrites = calls.filter(
    (call) => call.url === '/api/canvas/draft' && call.method === 'POST'
  ).length;
  await w.OraCanvas.loadCheckpoint(
    'target-dialogue', '20260813T123456123456Z-deadbeef', null,
    { active_editor: 'excalidraw' }, { currentDialogue: false, preferDraft: false }
  );
  await w.OraPanels.visual.onBridgeUpdate({ ora_visual_blocks: [
    { envelope: { id: 'assistant-one', type: 'comparison', canvas_action: 'replace' } },
    { envelope: { id: 'assistant-two', type: 'comparison', canvas_action: 'annotate' } },
  ], ora_visual_dispatch_key: 'target-dialogue#0' });
  if (api.elements.filter((element) => element.customData
      && element.customData.oraAssistantVisualKey).length !== 1
      || calls.filter((call) => call.url === '/api/canvas/draft'
        && call.method === 'POST').length !== unsentDraftWrites) {
    throw new Error('historical assistant replay duplicated images or persisted over latest draft');
  }
  await w.OraCanvas.loadCheckpoint(
    'target-dialogue', '20260813T123456123456Z-deadbeef', null,
    { active_editor: 'excalidraw' }, { currentDialogue: true, preferDraft: true }
  );
  if (sceneLoads[sceneLoads.length - 1] !== 'unsent-latest-draft') {
    throw new Error('returning to latest did not restore the recoverable draft: '
      + JSON.stringify({ sceneLoads, drafts: Array.from(drafts.entries()).map(
        ([id, blob]) => [id, blob.marker]
      ) }));
  }
  checkpoints.set('corrupt-history', {
    editor: 'excalidraw',
    native: { marker: 'corrupt-history' },
    preview: new w.Blob(['safe-preview'], { type: 'image/png' }),
  });
  const authoritativeDraft = drafts.get('target-dialogue');
  const visualStateCountBeforeCorruptHistory = visualStates.length;
  const checkpointCountBeforeCorruptHistory = checkpointCounter;
  const currentKonvaBeforeCorruptHistory = currentKonva;
  const konvaAttachBeforeCorruptHistory = konvaAttachCalls;
  await w.OraCanvas.loadCheckpoint(
    'target-dialogue', 'corrupt-history', null,
    { active_editor: 'excalidraw' }, { currentDialogue: false, preferDraft: false }
  );
  if (w.OraCanvas.getActiveEditor() !== 'konva'
      || konvaAttachCalls !== konvaAttachBeforeCorruptHistory + 1
      || drafts.get('target-dialogue') !== authoritativeDraft
      || visualStates.length !== visualStateCountBeforeCorruptHistory
      || checkpointCounter !== checkpointCountBeforeCorruptHistory
      || currentKonva !== currentKonvaBeforeCorruptHistory) {
    throw new Error('corrupt historical recovery changed durable current authority');
  }
  await w.OraCanvas.loadCheckpoint(
    'target-dialogue', '20260813T123456123456Z-deadbeef', null,
    { active_editor: 'excalidraw' }, { currentDialogue: true, preferDraft: true }
  );
  if (w.OraCanvas.getActiveEditor() !== 'excalidraw'
      || sceneLoads[sceneLoads.length - 1] !== 'unsent-latest-draft') {
    throw new Error('current draft was not restored after historical fallback');
  }
  await w.OraPanels.visual.onBridgeUpdate({ ora_visual_blocks: [
    { envelope: { id: 'assistant-one', type: 'comparison' } },
  ], ora_visual_dispatch_key: 'target-dialogue#latest' });
  const currentLocked = api.elements.filter((element) => element.customData
    && element.customData.oraAssistantVisualKey === 'target-dialogue#latest:0');
  if (currentLocked.length !== 1) {
    throw new Error('current assistant visual was not inserted once');
  }
  await w.OraCanvas.loadCheckpoint(
    'target-dialogue', '20260813T123456123456Z-deadbeef', null,
    { active_editor: 'excalidraw' }, { currentDialogue: true, preferDraft: true }
  );
  await w.OraPanels.visual.onBridgeUpdate({ ora_visual_blocks: [
    { envelope: { id: 'assistant-one', type: 'comparison' } },
  ], ora_visual_dispatch_key: 'target-dialogue#latest' });
  if (api.elements.filter((element) => element.customData
      && element.customData.oraAssistantVisualKey === 'target-dialogue#latest:0').length !== 1) {
    throw new Error('current assistant visual duplicated during reload replay');
  }

  api.elements = [{
    id: 'user-before-first', type: 'rectangle',
    x: 0, y: 0, width: 10, height: 10,
  }];
  await w.OraPanels.visual.onBridgeUpdate({
    envelope: { id: 'default-replace', type: 'comparison' },
    ora_visual_dispatch_key: 'actions#default',
  });
  if (!api.elements.some((element) => element.id === 'user-before-first')
      || api.elements.filter((element) => element.customData
        && element.customData.oraAssistantVisualKind === 'artifact').length !== 1) {
    throw new Error('first omitted canvas_action did not preserve user material and add the artifact');
  }
  const artifactBeforeUpdate = api.elements.find((element) => element.customData
    && element.customData.oraAssistantVisualKind === 'artifact');
  Object.assign(artifactBeforeUpdate, { x: 70, y: 80, width: 90, height: 60 });
  const replacedFileId = artifactBeforeUpdate.fileId;
  api.elements.push(
    { id: 'user-preserved', type: 'rectangle', x: 0, y: 0, width: 10, height: 10 },
    {
      id: 'annotation-preserved', type: 'image', x: 20, y: 0, width: 10, height: 10,
      customData: { annotationSource: 'user' },
    }
  );
  await w.OraPanels.visual.onBridgeUpdate({
    envelope: { id: 'explicit-update', type: 'comparison', canvas_action: 'update' },
    ora_visual_dispatch_key: 'actions#update',
  });
  const artifactsAfterModifiedUpdate = api.elements.filter((element) => element.customData
    && element.customData.oraAssistantVisualKind === 'artifact');
  if (!api.elements.some((element) => element.id === 'user-preserved')
      || !api.elements.some((element) => element.id === 'annotation-preserved')
      || artifactsAfterModifiedUpdate.length !== 2
      || !artifactsAfterModifiedUpdate.some((element) => element.x === 70
        && element.y === 80 && element.width === 90 && element.height === 60)
      || !api.files[replacedFileId]
      || Object.keys(api.files).length !== 2) {
    throw new Error('update did not preserve the modified assistant artifact and user material');
  }
  const sceneBeforeAnnotate = JSON.stringify({ elements: api.elements, files: api.files });
  const compiledBeforeAnnotate = compiledEnvelopeIds.length;
  const draftsBeforeAnnotate = calls.filter(
    (call) => call.url === '/api/canvas/draft' && call.method === 'POST'
  ).length;
  const annotateResult = await w.OraPanels.visual.onBridgeUpdate({
    envelope: { id: 'explicit-annotate', type: 'comparison', canvas_action: 'annotate' },
    ora_visual_dispatch_key: 'actions#annotate',
  });
  if (JSON.stringify({ elements: api.elements, files: api.files }) !== sceneBeforeAnnotate
      || compiledEnvelopeIds.length !== compiledBeforeAnnotate
      || calls.filter((call) => call.url === '/api/canvas/draft'
        && call.method === 'POST').length !== draftsBeforeAnnotate
      || !Array.isArray(annotateResult)
      || !annotateResult[0]
      || annotateResult[0].unsupported !== true
      || !Array.isArray(annotateResult[0].warnings)
      || !annotateResult[0].warnings[0].includes('switch to Konva')) {
    throw new Error('unsupported Excalidraw annotate was not reported while preserving the scene exactly');
  }
  await w.OraPanels.visual.onBridgeUpdate({
    envelope: { id: 'explicit-replace', type: 'comparison', canvas_action: 'replace' },
    ora_visual_dispatch_key: 'actions#replace',
  });
  const artifactsAfterReplace = api.elements.filter((element) => element.customData
    && element.customData.oraAssistantVisualKind === 'artifact');
  if (!api.elements.some((element) => element.id === 'user-before-first')
      || !api.elements.some((element) => element.id === 'user-preserved')
      || !api.elements.some((element) => element.id === 'annotation-preserved')
      || artifactsAfterReplace.length !== 2
      || Object.keys(api.files).length !== 2) {
    throw new Error('explicit replace did not preserve user material and modified assistant content');
  }
  const compiledBeforeClear = compiledEnvelopeIds.length;
  const stateEventsBeforeClear = canvasStateEvents;
  await w.OraPanels.visual.onBridgeUpdate({
    envelope: { id: 'explicit-clear', type: 'comparison', canvas_action: 'clear' },
    ora_visual_dispatch_key: 'actions#clear',
  });
  const assistantElementsAfterClear = api.elements.filter((element) => element.customData
    && element.customData.oraAssistantVisualKind === 'artifact');
  if (assistantElementsAfterClear.length !== 1
      || !assistantElementsAfterClear.some((element) => element.x === 70
        && element.y === 80 && element.width === 90 && element.height === 60)
      || !api.elements.some((element) => element.id === 'user-before-first')
      || !api.elements.some((element) => element.id === 'user-preserved')
      || !api.elements.some((element) => element.id === 'annotation-preserved')
      || Object.keys(api.files).length !== 1
      || !api.files[replacedFileId]
      || compiledEnvelopeIds.length !== compiledBeforeClear
      || canvasStateEvents !== stateEventsBeforeClear + 1
      || w.document.getElementById('visualExportButton').disabled) {
    throw new Error('clear did not remove untouched assistant material while preserving modified output and user content');
  }

  api.elements = [{ id: 'native-user', type: 'rectangle', x: 8, y: 8, width: 20, height: 20 }];
  const nativeEnvelope = {
    id: 'native-visual', type: 'concept_map', canvas_action: 'replace',
    spec: {
      focus_question: 'How do the two ideas connect?',
      concepts: [
        { id: 'A', label: 'First idea', hierarchy_level: 0 },
        { id: 'B', label: 'Second idea', hierarchy_level: 1 },
      ],
      linking_phrases: [{ id: 'L1', text: 'supports' }],
      propositions: [{ from_concept: 'A', via_phrase: 'L1', to_concept: 'B' }],
    },
  };
  await w.OraPanels.visual.onBridgeUpdate({
    ora_visual_blocks: [{ envelope: nativeEnvelope }],
    ora_visual_dispatch_key: 'native#1',
  });
  const nativeElements = api.elements.filter((element) => element.customData
    && element.customData.oraAssistantVisualKind === 'native');
  if (!api.elements.some((element) => element.id === 'native-user')
      || nativeElements.length < 5
      || !nativeElements.some((element) => element.type === 'arrow')
      || nativeElements.some((element) => !element.customData.assistantVisualId
        || !element.customData.generationRevision
        || !element.customData.semanticElementId
        || !element.customData.originalGenerationFingerprint)
      || nativeElements.filter((element) => element.type === 'arrow').some((element) => (
        !element.startBinding || !element.endBinding
        || !api.elements.some((candidate) => candidate.id === element.startBinding.elementId)
        || !api.elements.some((candidate) => candidate.id === element.endBinding.elementId)
      ))) {
    throw new Error('native structural visual did not install editable owned objects with bound initial arrows');
  }
  const modifiedNative = nativeElements.find((element) => element.type === 'rectangle');
  const modifiedNativeX = modifiedNative.x + 180;
  modifiedNative.x = modifiedNativeX;
  const modifiedNativeLabel = nativeElements.find((element) => element.type === 'text');
  modifiedNativeLabel.text = 'User-edited label';
  await w.OraPanels.visual.onBridgeUpdate({
    ora_visual_blocks: [{ envelope: Object.assign({}, nativeEnvelope, { canvas_action: 'update' }) }],
    ora_visual_dispatch_key: 'native#2',
  });
  const sameSemanticNative = api.elements.filter((element) => element.customData
    && element.customData.semanticElementId === modifiedNative.customData.semanticElementId);
  if (sameSemanticNative.length !== 2
      || !sameSemanticNative.some((element) => element.id === modifiedNative.id
        && element.x === modifiedNativeX)
      || sameSemanticNative.some((element) => element.id !== modifiedNative.id
        && element.x === modifiedNativeX)) {
    throw new Error('modified native assistant object was not preserved beside its regenerated replacement');
  }
  const sameSemanticLabel = api.elements.filter((element) => element.customData
    && element.customData.semanticElementId === modifiedNativeLabel.customData.semanticElementId);
  if (sameSemanticLabel.length !== 2
      || !sameSemanticLabel.some((element) => element.id === modifiedNativeLabel.id
        && element.text === 'User-edited label')
      || sameSemanticLabel.some((element) => element.id !== modifiedNativeLabel.id
        && element.text === 'User-edited label')) {
    throw new Error('edited native label was not preserved beside its regenerated replacement');
  }

  const draftCountBeforeCapability = calls.filter(
    (call) => call.url === '/api/canvas/draft' && call.method === 'POST'
  ).length;
  const konvaAttachBeforeExcalidrawCapability = konvaAttachCalls;
  await w.OraCanvas.insertImageObject({
    id: 'generated-active-x', kind: 'image', layer: 'user_input',
    x: 4488, y: 4488, width: 80, height: 60,
    image_data: { mime_type: 'image/png', encoding: 'base64', data: 'aW1hZ2U=' },
  });
  const capabilityElement = api.elements.find((element) => element.id === 'capability-png-1');
  if (capabilityImageCalls !== 1
      || konvaAttachCalls !== konvaAttachBeforeExcalidrawCapability
      || !capabilityElement
      || capabilityElement.locked !== false
      || capabilityElement.x < 0 || capabilityElement.y < 0
      || calls.filter((call) => call.url === '/api/canvas/draft'
        && call.method === 'POST').length !== draftCountBeforeCapability + 1) {
    throw new Error('image capability result did not land in and persist the active Excalidraw scene');
  }

  api.elements = [{ id: 'deleted-only', type: 'rectangle', isDeleted: true }];
  const attachBeforeEmptyXToK = konvaAttachCalls;
  const artifactClearsBeforeEmptyXToK = konvaArtifactClearCalls;
  const pendingClearsBeforeEmptyXToK = konvaPendingImageClearCalls;
  const stateClearsBeforeEmptyXToK = konvaEmptyStateLoadCalls;
  await w.OraCanvas.switchEditor();
  if (w.OraCanvas.getActiveEditor() !== 'konva'
      || konvaAttachCalls !== attachBeforeEmptyXToK
      || konvaArtifactClearCalls !== artifactClearsBeforeEmptyXToK + 1
      || konvaPendingImageClearCalls !== pendingClearsBeforeEmptyXToK
      || konvaEmptyStateLoadCalls !== stateClearsBeforeEmptyXToK) {
    throw new Error('empty X→K did not clear the assistant artifact without erasing user material');
  }
  await w.OraCanvas.switchEditor();
  if (w.OraCanvas.getActiveEditor() !== 'excalidraw'
      || imageBackedCalls !== 0
      || !api.elements[0]
      || api.elements[0].id !== 'deleted-only') {
    throw new Error('empty X→K→X did not reopen its native checkpoint');
  }

  api.elements = [{ id: 'editable-A', type: 'rectangle' }];
  const attachBeforeNonemptyXToK = konvaAttachCalls;
  await w.OraCanvas.switchEditor();
  const xToK = visualStates[visualStates.length - 1];
  if (w.OraCanvas.getActiveEditor() !== 'konva'
      || konvaAttachCalls !== attachBeforeNonemptyXToK + 1
      || xToK.active_editor !== 'konva'
      || !xToK.resume_excalidraw_checkpoint_id
      || !xToK.konva_baseline_checkpoint_id
      || !checkpoints.has(xToK.resume_excalidraw_checkpoint_id)
      || !checkpoints.has(xToK.konva_baseline_checkpoint_id)
      || !currentKonva) {
    throw new Error('X→K did not publish provenance only after both checkpoints');
  }
  for (const format of ['png', 'jpeg', 'svg', 'pdf']) await exportThroughMenu(format);
  if (exportRoutes.slice(4).join(',') !== 'konva:png,konva:jpeg,konva:svg,konva:pdf'
      || shareGateCalls !== 8) {
    throw new Error('Konva Export menu did not route four formats through one share gate each: '
      + JSON.stringify({ exportRoutes, shareGateCalls }));
  }
  const statesBeforeWarning = visualStates.length;
  let confirmAnswer = false;
  let confirmCalls = 0;
  w.confirm = function () { confirmCalls += 1; return confirmAnswer; };
  if (w.OraCanvas.panel.config.beforeUserMutation({ label: 'create:rect' }) !== false
      || visualStates.length !== statesBeforeWarning) {
    throw new Error('cancelled first Konva edit did not preserve the unacknowledged handoff');
  }
  confirmAnswer = true;
  if (w.OraCanvas.panel.config.beforeUserMutation({ label: 'create:rect' }) !== true) {
    throw new Error('confirmed first Konva edit was not accepted');
  }
  await w.OraCanvas.flushDraft();
  if (confirmCalls !== 2
      || !visualStates[visualStates.length - 1].konva_edit_warning_acknowledged) {
    throw new Error('Konva editability warning acknowledgement was not persisted once');
  }
  const flattenedObjects = liveObjects.slice();
  const konvaAttachBeforeCapability = konvaAttachCalls;
  await w.OraCanvas.insertImageObject({
    id: 'generated-active-k', kind: 'image', layer: 'user_input',
    x: 0, y: 0, width: 20, height: 20,
    image_data: { mime_type: 'image/png', encoding: 'base64', data: 'aW1hZ2U=' },
  });
  if (konvaAttachCalls !== konvaAttachBeforeCapability + 1 || capabilityImageCalls !== 1) {
    throw new Error('image capability result did not use Konva while Konva was active');
  }
  liveObjects = flattenedObjects;
  liveObjects = [];
  if (w.OraCanvas.hasContent()) {
    throw new Error('genuinely blank Konva state was reported as visual content');
  }
  liveObjects = flattenedObjects;
  if (!w.OraCanvas.hasContent()) {
    throw new Error('flattened background-only Konva handoff was reported blank');
  }

  await w.OraCanvas.loadCheckpoint(
    'target-dialogue', '20260813T123456123456Z-deadbeef', null,
    xToK, { currentDialogue: true }
  );
  if (w.OraCanvas.getActiveEditor() !== 'konva') {
    throw new Error('reload during Konva authority did not restore baseline K');
  }

  stageWidth = 880;
  stageHeight = 640;
  stagePosition = { x: 73, y: -41 };
  stageScale = { x: 2.5, y: 2.5 };
  await w.OraCanvas.switchEditor();
  if (w.OraCanvas.getActiveEditor() !== 'excalidraw'
      || imageBackedCalls !== 0
      || api.elements[0].id !== 'editable-A') {
    throw new Error('resize/pan/zoom-only K→X did not reopen native checkpoint A: '
      + JSON.stringify({ editor: w.OraCanvas.getActiveEditor(), imageBackedCalls,
        element: api.elements[0] && api.elements[0].id }));
  }

  await w.OraCanvas.switchEditor();
  stageWidth = 1200;
  stageHeight = 700;
  stagePosition = { x: -12, y: 95 };
  stageScale = { x: 0.5, y: 0.5 };
  liveObjects = [{ id: 'flattened-edited', x: 0, y: 0, width: 130, height: 100 }];
  stageRevision = 'modified';
  const beforeChangedCount = checkpointCounter;
  await w.OraCanvas.switchEditor();
  if (w.OraCanvas.getActiveEditor() !== 'excalidraw'
      || imageBackedCalls !== 1
      || checkpointCounter !== beforeChangedCount + 1
      || api.elements[0].id !== 'image-backed-B') {
    throw new Error('changed K→X did not create the image-backed checkpoint B');
  }

  checkpointFailure = {
    error: 'checkpoint write failed',
    message: 'conversation is closed',
  };
  const failedSwitchButton = w.document.getElementById('visualEditorSwitch');
  failedSwitchButton.click();
  for (let index = 0; index < 12; index += 1) await tick();
  const failedSwitchStatus = w.document.getElementById('visualPaneFooterStatus');
  if (w.OraCanvas.getActiveEditor() !== 'excalidraw'
      || failedSwitchButton.disabled
      || !failedSwitchStatus.classList.contains('is-error')
      || !failedSwitchStatus.textContent.includes(
        'Checkpoint write failed for target-dialogue (500): '
        + 'checkpoint write failed: conversation is closed'
      )) {
    throw new Error('production-shaped checkpoint failure was not visibly parsed while keeping the durable editor');
  }
  checkpointFailure = null;
  failedSwitchButton.click();
  for (let index = 0; index < 12 && w.OraCanvas.getActiveEditor() !== 'konva'; index += 1) {
    await tick();
  }
  failedSwitchButton.click();
  for (let index = 0; index < 12 && w.OraCanvas.getActiveEditor() !== 'excalidraw'; index += 1) {
    await tick();
  }
  if (w.OraCanvas.getActiveEditor() !== 'excalidraw') {
    throw new Error('checkpoint recovery did not switch Excalidraw → Konva → Excalidraw');
  }

  console.log('ok - Excalidraw wheel/export, exact identity, and durable switches');
  dom.window.close();
})().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
