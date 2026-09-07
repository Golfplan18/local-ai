/* Dependency-free fixture of the existing toolbar's user-visible status. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ids = new Map();
const actions = [];
class Element {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.events = {};
    this.classList = {add() {}, remove() {}, toggle() {}};
    this._text = '';
  }
  setAttribute() {}
  addEventListener(name, handler) { this.events[name] = handler; }
  appendChild(child) { this.children.push(child); }
  contains(child) { return this.children.includes(child); }
  querySelector(selector) { return ids.get(selector) || null; }
  querySelectorAll() { return actions; }
  set textContent(value) { this._text = value; this.children = []; }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(''); }
  set innerHTML(value) {
    this.children = [];
    this._text = '';
    if (!value) return;
    // Only the fixed toolbar template may be parsed as HTML. Any warning
    // interpolated into HTML would fail this fixture rather than look safe.
    assert.ok(value.includes('id="exportToolbarStatus"'), 'dynamic status was assigned as HTML');
    for (const id of value.matchAll(/id="([^"]+)"/g)) ids.set('#' + id[1], new Element('div'));
    for (const action of ['output', 'conversation', 'docx', 'pdf']) {
      const item = new Element('button');
      item.dataset.action = action;
      actions.push(item);
    }
  }
}
const pane = new Element('div');
const requests = [];
let reply = {};
const turn = { _ora_history_owner: 'source', _ora_history_turn_index: 1, chunk_id: 'chunk', turn_privacy: 'private' };
const context = {
  document: {
    readyState: 'complete',
    querySelector: selector => selector === '.output-pane' ? pane : null,
    createElement: tag => new Element(tag),
    addEventListener() {},
  },
  window: { OraConversation: {
    getActiveConversationId: () => 'dialogue',
    getCurrentTurn: () => ({user: {...turn}, assistant: {...turn}}),
  }},
  fetch: async (url, options) => {
    if (url === '/api/export/locations') return {json: async () => ({capabilities: {}})};
    requests.push({url, options});
    return {json: async () => reply};
  },
  setTimeout: () => 1,
  clearTimeout() {},
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../server/static/js/export-toolbar.js'), 'utf8'), context);
const status = ids.get('#exportToolbarStatus');
const flush = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  for (const action of ['output', 'conversation']) {
    reply = {ok: true, path: '/vault/Note.md', warnings: ['description: <img src=x onerror="bad()">']};
    actions.find(item => item.dataset.action === action).events.click();
    await flush();
    assert.ok(status.textContent.includes('Saved Note.md — Warning: description: <img'));
    assert.equal(status.children[0].tagName, 'span');
    assert.equal(status.children[0].children.length, 0, 'warning must remain inert text');
    assert.equal(status.children[1].textContent, 'Reveal');
    reply = {ok: false, metadata_invalid: true, error: 'Document metadata refused: nexus: wrong identity'};
    actions.find(item => item.dataset.action === action).events.click();
    await flush();
    assert.equal(status.textContent, reply.error);
    assert.equal(status.children.length, 1, 'refusal must remove Reveal');
    assert.ok(!status.textContent.includes('Saved'));
  }
  reply = {ok: true, path: '/vault/Plain.md', warnings: []};
  actions[0].events.click();
  await flush();
  assert.equal(status.children[0].textContent, 'Saved Plain.md');
  assert.equal(JSON.parse(requests[0].options.body).source_chunk_id, 'chunk');
  console.log('PASS: current-output and Dialogue warnings use inert status text; refusal removes Reveal; normal success stays unchanged.');
})().catch(error => { console.error(error); process.exitCode = 1; });
