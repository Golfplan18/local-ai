#!/usr/bin/env node
/* Behavioral coverage for Delete Forever browser-residue cleanup. */
'use strict';

var fs = require('fs');
var path = require('path');
var vm = require('vm');

var modules = path.resolve(
  __dirname, '..', 'ora-visual-compiler', 'tests', 'node_modules'
);
var jsdom;
try {
  jsdom = require(path.join(modules, 'jsdom'));
} catch (e) {
  console.error('error: jsdom not available at ' + modules);
  process.exit(2);
}

var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name
    + (detail ? ' - ' + detail : ''));
}
function wait(w, ms) {
  return new Promise(function (resolve) { w.setTimeout(resolve, ms || 0); });
}
function response(payload, status) {
  var ok = !status || (status >= 200 && status < 300);
  return Promise.resolve({
    ok: ok,
    status: status || 200,
    json: function () { return Promise.resolve(payload || {}); },
    blob: function () { return Promise.resolve(new Blob(['frame'])); },
  });
}
function makeDom(body) {
  return new jsdom.JSDOM(
    '<!doctype html><html><body>' + (body || '') + '</body></html>',
    { url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only' }
  );
}
function load(dom, filename) {
  var context = dom.getInternalVMContext();
  context.console = console;
  context.fetch = dom.window.fetch;
  vm.runInContext(
    fs.readFileSync(path.resolve(__dirname, '..', filename), 'utf8'),
    context,
    { filename: filename }
  );
}
function deleteEvent(w, conversationId) {
  w.document.dispatchEvent(new w.CustomEvent(
    'ora:conversation-lifecycle-completed',
    { detail: { action: 'delete-forever', conversation_id: conversationId } }
  ));
}

async function testMediaLibrary() {
  var dom = makeDom('<div class="visual-panel"></div>');
  var w = dom.window;
  var deferredResolve = null;
  var deferNext = false;
  w.document.body.classList.add('pane-mode-video');
  w.fetch = function (url) {
    if (deferNext) {
      deferNext = false;
      return new Promise(function (resolve) { deferredResolve = resolve; });
    }
    if (String(url) === '/api/media-library/media-replacement') {
      return response({ entries: [] });
    }
    return response({ entries: [{ id: 'sensitive-entry', kind: 'audio' }] });
  };
  load(dom, '../../plugins/video/static/media-library.js');
  w.OraMediaLibrary.init();
  w.OraMediaLibrary.setConversationId('media-target');
  await wait(w, 0);
  record('media library starts with correlated entry state',
    w.OraMediaLibrary.getState().entries.length === 1);
  deleteEvent(w, 'other-dialogue');
  record('media library ignores deletion of another Dialogue',
    w.OraMediaLibrary.getState().conversationId === 'media-target');

  deferNext = true;
  var pending = w.OraMediaLibrary.refresh();
  w.OraConversation = {
    getActiveConversationId: function () { return 'media-replacement'; },
  };
  deleteEvent(w, 'media-target');
  deferredResolve(await response({
    entries: [{ id: 'late-sensitive-entry', kind: 'audio' }],
  }));
  await pending;
  await wait(w, 0);
  var state = w.OraMediaLibrary.getState();
  record('media library deletion survives a late list response',
    state.conversationId === 'media-replacement' && state.entries.length === 0);
  dom.window.close();
}

async function testTimelineAndTranscript() {
  var timelineDom = makeDom('<div class="visual-panel"></div>');
  var tw = timelineDom.window;
  tw.fetch = function () { return response({ entries: [] }); };
  load(timelineDom, '../../plugins/video/static/timeline-editor.js');
  tw.OraTimelineEditor.init();
  tw.OraTimelineEditor.setConversationId('timeline-target');
  tw.OraTimelineEditor._setStateForTests({
    duration_ms: 1000,
    playhead_ms: 10,
    zoom_pixels_per_ms: 0.05,
    tracks: [{ id: 'track-secret', clips: [] }],
  });
  deleteEvent(tw, 'other-dialogue');
  record('timeline ignores deletion of another Dialogue',
    !!tw.OraTimelineEditor.getState());
  deleteEvent(tw, 'timeline-target');
  record('timeline clears canonical state for the deleted Dialogue',
    tw.OraTimelineEditor.getState() === null);
  timelineDom.window.close();

  var transcriptDom = makeDom('<div class="visual-panel"></div>');
  var sw = transcriptDom.window;
  sw.fetch = function () { return response({ segments: [] }); };
  load(transcriptDom, '../../plugins/video/static/transcript-panel.js');
  sw.OraTranscriptPanel.init();
  sw.OraTranscriptPanel.setConversationId('transcript-target');
  deleteEvent(sw, 'other-dialogue');
  record('transcript panel ignores deletion of another Dialogue',
    sw.OraTranscriptPanel.getState().conversation_id === 'transcript-target');
  deleteEvent(sw, 'transcript-target');
  var transcriptState = sw.OraTranscriptPanel.getState();
  record('transcript panel drops deleted correlation and segment state',
    transcriptState.conversation_id === null
      && transcriptState.loaded_entry_id === null
      && transcriptState.segment_count === 0);
  transcriptDom.window.close();
}

async function testCaptureAndRender() {
  var captureDom = makeDom('<div class="visual-panel"></div>');
  var cw = captureDom.window;
  cw.setInterval = function () { return 1; };
  cw.clearInterval = function () {};
  cw.fetch = function (url) {
    url = String(url);
    if (url === '/api/capture/devices') return response({ video: [], audio: [] });
    if (url === '/api/settings') return response({ settings: {} });
    if (url === '/api/capture/start') {
      return response({ capture_id: 'capture-secret', state: { state: 'recording' } });
    }
    if (url === '/api/capture/capture-secret/state') {
      return response({ type: 'duration', duration_ms: 2500 });
    }
    return response({}, 404);
  };
  load(captureDom, '../../plugins/video/static/capture-controls.js');
  cw.OraCaptureControls.init();
  cw.OraCaptureControls.setConversationId('capture-target');
  cw.document.dispatchEvent(new cw.CustomEvent('ora:pane-mode-toggle', {
    detail: { current: 'video' },
  }));
  cw.document.querySelector('[data-role="start"]').click();
  await wait(cw, 0);
  record('capture controls hold an active correlated capture before deletion',
    cw.OraCaptureControls.getState().captureId === 'capture-secret');
  deleteEvent(cw, 'other-dialogue');
  record('capture controls ignore deletion of another Dialogue',
    cw.OraCaptureControls.getState().captureId === 'capture-secret');
  deleteEvent(cw, 'capture-target');
  var captureState = cw.OraCaptureControls.getState();
  record('capture controls clear deleted polling and measurement state',
    captureState.conversationId === null
      && captureState.captureId === null
      && captureState.captureState === 'idle'
      && captureState.durationMs === 0
      && captureState.rmsDb === null);
  captureDom.window.close();

  var renderDom = makeDom(
    '<div class="visual-panel"><div class="timeline-editor">'
      + '<div class="timeline-editor__ruler-row"></div></div></div>'
  );
  var rw = renderDom.window;
  rw.setInterval = function () { return 1; };
  rw.clearInterval = function () {};
  rw.fetch = function (url) {
    url = String(url);
    if (url === '/api/render/presets') {
      return response({ presets: [{ key: 'standard', label: 'Standard' }] });
    }
    if (url === '/api/settings') return response({ settings: {} });
    if (url === '/api/render/render-target') {
      return response({ render_id: 'render-secret' });
    }
    if (url === '/api/render/render-secret/state') {
      return response({ type: 'rendering', progress_pct: 25 });
    }
    return response({}, 404);
  };
  load(renderDom, '../../plugins/video/static/render-controls.js');
  rw.OraRenderControls.init();
  await wait(rw, 0);
  rw.OraRenderControls.setConversationId('render-target');
  rw.OraRenderControls.openRenderPicker();
  rw.document.querySelector('[data-preset="standard"]').click();
  await wait(rw, 0);
  record('render controls hold an active correlated render before deletion',
    rw.OraRenderControls.getState().activeRenderId === 'render-secret');
  deleteEvent(rw, 'other-dialogue');
  record('render controls ignore deletion of another Dialogue',
    rw.OraRenderControls.getState().activeRenderId === 'render-secret');
  deleteEvent(rw, 'render-target');
  var renderState = rw.OraRenderControls.getState();
  record('render controls clear deleted render and polling state',
    renderState.conversationId === null
      && renderState.activeRenderId === null
      && renderState.activePreset === null);
  renderDom.window.close();
}

async function testPreviewAndDocuments() {
  var previewDom = makeDom('<div class="visual-panel"></div>');
  var pw = previewDom.window;
  pw.HTMLMediaElement.prototype.pause = function () {};
  pw.HTMLMediaElement.prototype.load = function () {};
  pw.URL.createObjectURL = function () { return 'blob:preview-secret'; };
  pw.URL.revokeObjectURL = function () {};
  pw.fetch = function (url) {
    url = String(url);
    if (url === '/api/preview/preview-target/state') {
      return response({ fresh: true, has_proxy: true, sensitive: 'proxy-state' });
    }
    if (url.indexOf('/api/preview/preview-target/frame?') === 0) {
      return response({});
    }
    return response({}, 404);
  };
  load(previewDom, '../../plugins/video/static/preview-monitor.js');
  pw.OraPreviewMonitor.init();
  pw.document.body.classList.add('pane-mode-video');
  pw.OraPreviewMonitor.setConversationId('preview-target');
  await wait(pw, 0);
  record('preview monitor holds correlated proxy state before deletion',
    !!pw.OraPreviewMonitor.getState().proxyState);
  deleteEvent(pw, 'other-dialogue');
  record('preview monitor ignores deletion of another Dialogue',
    pw.OraPreviewMonitor.getState().conversationId === 'preview-target');
  deleteEvent(pw, 'preview-target');
  var previewState = pw.OraPreviewMonitor.getState();
  record('preview monitor clears deleted proxy, frame, and overlay state',
    previewState.conversationId === null
      && previewState.proxyState === null
      && previewState.activeProxyRenderId === null
      && previewState.selectedOverlay === null);
  previewDom.window.close();

  var documentDom = makeDom('<div id="host"></div>');
  var dw = documentDom.window;
  var deferDocumentStart = false;
  var resolveDocumentStart = null;
  dw.fetch = function (url) {
    if (String(url) === '/api/document/process') {
      if (deferDocumentStart) {
        deferDocumentStart = false;
        return new Promise(function (resolve) { resolveDocumentStart = resolve; });
      }
      return response({ processing_id: 'document-secret' });
    }
    return response({ state: 'converting' });
  };
  load(documentDom, 'js/document-input.js');
  dw.OraDocumentInput.init();
  await dw.OraDocumentInput.acceptFile(
    new dw.File(['secret'], 'private.pdf', { type: 'application/pdf' }),
    dw.document.getElementById('host'),
    { conversation_id: 'document-target', tag: 'private' }
  );
  var job = dw.OraDocumentInput.getJobs()['document-secret'];
  record('document input retains correlation but not the uploaded File object',
    job && job.conversation_id === 'document-target' && job.file === null);
  deleteEvent(dw, 'other-dialogue');
  record('document input ignores deletion of another Dialogue',
    !!dw.OraDocumentInput.getJobs()['document-secret']);
  deleteEvent(dw, 'document-target');
  record('document input removes exact deleted job and chip state',
    !Object.keys(dw.OraDocumentInput.getJobs()).length
      && !dw.document.querySelector('[data-document-id="document-secret"]'));

  deferDocumentStart = true;
  var lateDocument = dw.OraDocumentInput.acceptFile(
    new dw.File(['late secret'], 'late-private.pdf', { type: 'application/pdf' }),
    dw.document.getElementById('host'),
    { conversation_id: 'document-late', tag: 'private' }
  );
  deleteEvent(dw, 'document-late');
  resolveDocumentStart(await response({ processing_id: 'document-late-secret' }));
  await lateDocument;
  record('document input deletion survives a late upload-start response',
    !Object.keys(dw.OraDocumentInput.getJobs()).length
      && !dw.document.querySelector('[data-document-id="document-late-secret"]'));
  documentDom.window.close();
}

async function run() {
  await testMediaLibrary();
  await testTimelineAndTranscript();
  await testCaptureAndRender();
  await testPreviewAndDocuments();
  var passed = results.filter(function (result) { return result.ok; }).length;
  console.log('\n' + passed + ' / ' + results.length + ' tests passed');
  process.exit(passed === results.length ? 0 : 1);
}

run().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
