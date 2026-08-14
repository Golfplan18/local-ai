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
const dom = new JSDOM(
  '<!doctype html><html><body><div class="right-pane"></div><div id="logo-o"></div>'
    + '<button id="visualExportPng" disabled>Export</button></body></html>',
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
let failVisualState = false;
let imageBackedCalls = 0;
let assistantImageCalls = 0;
let capabilityImageCalls = 0;
let konvaAttachCalls = 0;
let stageRevision = 'baseline';
let stageWidth = 100;
let stageHeight = 100;
let stagePosition = { x: 0, y: 0 };
let stageScale = { x: 1, y: 1 };
let liveObjects = [{ id: 'flattened', x: 0, y: 0, width: 100, height: 100 }];
let currentKonva = null;
const assistantEvents = [];
const compiledEnvelopeIds = [];

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
VisualPanel.prototype.clearArtifact = function () {};
VisualPanel.prototype.loadCanvasState = function () {};
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
    if (scene.appState) this.appState = scene.appState;
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
      appState: {}, files: {},
    });
  },
  serialize(snapshot) {
    const blob = new w.Blob([JSON.stringify(snapshot.elements)]);
    blob.marker = snapshot.elements[0] ? snapshot.elements[0].id : 'empty';
    blob.elements = snapshot.elements.map((element) => ({ ...element }));
    return blob;
  },
  canonicalPng() { return Promise.resolve(new w.Blob(['png'], { type: 'image/png' })); },
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
    this.naturalWidth = 100;
    this.naturalHeight = 100;
    setTimeout(() => this.onload && this.onload(), 0);
  }
  get src() { return this._src; }
};
const originalCreateElement = w.document.createElement.bind(w.document);
w.document.createElement = function (name, options) {
  if (String(name).toLowerCase() !== 'canvas') return originalCreateElement(name, options);
  let raster = '';
  return {
    width: 0,
    height: 0,
    getContext() {
      return {
        fillStyle: '',
        fillRect() {},
        drawImage(image) { raster += image.src || ''; },
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
    if (failVisualState) return Promise.resolve({ ok: false, status: 500 });
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
vm.runInContext(source, context, { filename: 'v3-canvas-mount.js' });
w.document.dispatchEvent(new w.Event('DOMContentLoaded'));

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

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
      || w.document.getElementById('visualExportPng').disabled) {
    throw new Error('current-dialogue load did not refresh the non-empty canvas/export state once');
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
      || w.document.getElementById('visualExportPng').disabled
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
  if (api.elements.length !== 1
      || api.elements[0].customData.oraAssistantVisualKind !== 'artifact') {
    throw new Error('first omitted canvas_action did not replace the whole scene');
  }
  const artifactBeforeUpdate = api.elements[0];
  Object.assign(artifactBeforeUpdate, { x: 70, y: 80, width: 90, height: 60 });
  const replacedFileId = artifactBeforeUpdate.fileId;
  api.elements.push(
    { id: 'user-preserved', type: 'rectangle', x: 0, y: 0, width: 10, height: 10 },
    {
      id: 'annotation-preserved', type: 'image', x: 20, y: 0, width: 10, height: 10,
      customData: { oraAssistantVisual: true, oraAssistantVisualKind: 'annotation' },
    }
  );
  await w.OraPanels.visual.onBridgeUpdate({
    envelope: { id: 'explicit-update', type: 'comparison', canvas_action: 'update' },
    ora_visual_dispatch_key: 'actions#update',
  });
  if (!api.elements.some((element) => element.id === 'user-preserved')
      || !api.elements.some((element) => element.id === 'annotation-preserved')
      || api.elements.filter((element) => element.customData
        && element.customData.oraAssistantVisualKind === 'artifact').length !== 1
      || api.elements.find((element) => element.customData
        && element.customData.oraAssistantVisualKind === 'artifact').x !== 70
      || api.elements.find((element) => element.customData
        && element.customData.oraAssistantVisualKind === 'artifact').y !== 80
      || api.elements.find((element) => element.customData
        && element.customData.oraAssistantVisualKind === 'artifact').width !== 90
      || api.elements.find((element) => element.customData
        && element.customData.oraAssistantVisualKind === 'artifact').height !== 60
      || api.files[replacedFileId]) {
    throw new Error('update did not replace only the whole assistant artifact');
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
  if (api.elements.length !== 1
      || api.elements[0].customData.oraAssistantVisualKind !== 'artifact'
      || Object.keys(api.files).length !== 1) {
    throw new Error('explicit replace did not remove user and annotation content');
  }
  const compiledBeforeClear = compiledEnvelopeIds.length;
  const stateEventsBeforeClear = canvasStateEvents;
  await w.OraPanels.visual.onBridgeUpdate({
    envelope: { id: 'explicit-clear', type: 'comparison', canvas_action: 'clear' },
    ora_visual_dispatch_key: 'actions#clear',
  });
  if (api.elements.length !== 0
      || compiledEnvelopeIds.length !== compiledBeforeClear
      || canvasStateEvents !== stateEventsBeforeClear + 1
      || !w.document.getElementById('visualExportPng').disabled) {
    throw new Error('clear did not empty the scene and refresh canvas/export state once');
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
  if (capabilityImageCalls !== 1
      || konvaAttachCalls !== konvaAttachBeforeExcalidrawCapability
      || api.elements.length !== 1 || api.elements[0].id !== 'capability-png-1'
      || api.elements[0].locked !== false
      || api.elements[0].x !== 0 || api.elements[0].y !== 0
      || calls.filter((call) => call.url === '/api/canvas/draft'
        && call.method === 'POST').length !== draftCountBeforeCapability + 1) {
    throw new Error('image capability result did not land in and persist the active Excalidraw scene');
  }

  api.elements = [{ id: 'editable-A', type: 'rectangle' }];
  await w.OraCanvas.switchEditor();
  const xToK = visualStates[visualStates.length - 1];
  if (w.OraCanvas.getActiveEditor() !== 'konva'
      || xToK.active_editor !== 'konva'
      || !xToK.resume_excalidraw_checkpoint_id
      || !xToK.konva_baseline_checkpoint_id
      || !checkpoints.has(xToK.resume_excalidraw_checkpoint_id)
      || !checkpoints.has(xToK.konva_baseline_checkpoint_id)
      || !currentKonva) {
    throw new Error('X→K did not publish provenance only after both checkpoints');
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

  failVisualState = true;
  let failed = false;
  try { await w.OraCanvas.switchEditor(); } catch (_) { failed = true; }
  if (!failed || w.OraCanvas.getActiveEditor() !== 'excalidraw') {
    throw new Error('failed X→K publication did not keep the last durable editor');
  }

  console.log('ok - Excalidraw load/dispatch, exact identity, and durable switches');
  dom.window.close();
})().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
