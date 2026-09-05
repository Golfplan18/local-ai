#!/usr/bin/env node
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { TextEncoder } = require('node:util');
const modules = path.resolve(__dirname, '../../document-surface/node_modules');
let JSDOM;
try {
  ({ JSDOM } = require(path.join(modules, 'jsdom')));
  assert.equal(require(path.join(modules, 'jsdom/package.json')).version, '29.0.2');
} catch (error) {
  console.error(`Install the pinned document-surface test DOM at ${modules}/jsdom: ${error.message}`);
  process.exit(2);
}
const { EditorView } = require(path.join(modules, '@codemirror/view'));
const dom = new JSDOM('<!doctype html><html><head></head><body><main></main><aside></aside></body></html>', {
  url: 'http://localhost/', runScripts: 'outside-only', pretendToBeVisual: true,
});
const w = dom.window;
w.TextEncoder = TextEncoder;
// jsdom has no shadow-root selection API or native layout; model those browser
// seams only. All editing/state/history below use the real bundled EditorView.
w.ShadowRoot.prototype.getSelection = () => w.getSelection();
w.document.execCommand = () => false;
const rectangle = { left: 0, right: 0, top: 0, bottom: 0, width: 0, height: 0 };
w.Range.prototype.getClientRects = () => [];
w.Range.prototype.getBoundingClientRect = () => rectangle;
w.eval(fs.readFileSync(path.resolve(__dirname, '../vendor/document-surface/ora-document-surface.js'), 'utf8'));
const surface = w.OraDocumentSurface;
const host = w.document.querySelector('main');
const other = w.document.querySelector('aside');
const tick = () => new Promise(resolve => w.setTimeout(resolve, 0));

(async () => {
  try {
    assert.deepEqual(Object.keys(surface).sort(), ['createEditor', 'renderRead']);
    let reader = surface.renderRead({ host, ariaLabel: 'Read fixture', markdown:
      '---\ntype: file\n---\n# Heading\n\nA **bold** and *emphasized* paragraph.\n\n- item\n\n1. ordered\n\n> quote\n\n```js\n<script>inert()</script>\n```\n\n`inline`\n\n| A | B |\n| - | - |\n| one | two |\n\n---' });
    for (const tag of ['h1', 'p', 'strong', 'em', 'ul', 'ol', 'blockquote', 'pre', 'code', 'table', 'th', 'td', 'hr']) {
      assert.ok(host.querySelector(tag), `supported ${tag}`);
    }
    assert.ok(host.textContent.includes('type: file'), 'the surface does not strip frontmatter');
    assert.equal(host.querySelector('article').getAttribute('aria-label'), 'Read fixture');
    reader.destroy(); reader.destroy();
    assert.equal(host.childNodes.length, 0);
    reader = surface.renderRead({ host, markdown:
      '<script>window.pwned=1</script>\n<img src="https://invalid.example/a" onerror="pwned=1">\n<svg><script>pwned=1</script></svg>\n<math><mtext>evil</mtext></math>\n<form><input autofocus></form>\n\n' +
      '[web](https://example.com/a?q=1) [http](http://example.com) [mail](mailto:reader@example.com)\n\n' +
      '[relative](../secret.md) [fragment](#id) [file](file:///private) [data](data:text/html,x) [script](javascript:alert%281%29) [custom](obsidian://open?vault=x) [network](//invalid.example/x)\n\n' +
      '![remote](https://invalid.example/image.png) ![data](data:image/png;base64,YQ==) ![[Embedded Note]] [[Wiki Note]]\n\nhttps://example.com/unlinked' });
    const anchors = [...host.querySelectorAll('a')];
    assert.equal(anchors.length, 3, 'only explicit allowed-protocol links activate');
    for (const anchor of anchors) {
      assert.equal(anchor.target, '_blank');
      assert.equal(anchor.rel, 'noopener noreferrer');
      assert.equal(anchor.getAttribute('referrerpolicy'), 'no-referrer');
    }
    assert.equal(host.querySelector('script,img,svg,math,form,input,iframe,video,audio,object,embed,style'), null);
    assert.equal(host.querySelector('[src],[srcset],[style],[id],[onerror],[onclick]'), null);
    assert.equal(host.querySelector('[class]:not(.ora-document-read)'), null);
    for (const label of ['link: ../secret.md', 'link: #id', 'Image: remote', 'Embed: Embedded Note', 'Wiki link: Wiki Note']) {
      assert.ok(host.textContent.includes(label), `meaningful inert ${label}`);
    }
    assert.equal(w.pwned, undefined);
    console.log('PASS: supported Markdown, retained frontmatter, fixed anchors, inert links/images/embeds, raw HTML and XSS rejection');

    const limit = 4 * 1024 * 1024;
    for (const bytes of [limit - 1, limit, limit + 1]) {
      const text = '# ' + 'é'.repeat(Math.floor((bytes - 2) / 2)) + ((bytes - 2) % 2 ? 'x' : '');
      reader = surface.renderRead({ host, markdown: text });
      if (bytes <= limit) assert.ok(host.querySelector('h1'), `${bytes} UTF-8 bytes render`);
      else {
        assert.equal(host.querySelector('.ora-document-literal').textContent, text);
        assert.ok(host.textContent.includes('4 MiB'));
      }
      reader.destroy();
    }
    const descriptor = Object.getOwnPropertyDescriptor(w.Element.prototype, 'innerHTML');
    Object.defineProperty(w.Element.prototype, 'innerHTML', { configurable: true,
      get: descriptor.get, set(value) {
        if (this.className === 'ora-document-read') throw new Error('simulated sink failure');
        return descriptor.set.call(this, value);
      } });
    const expectedError = w.console.error;
    w.console.error = () => {};
    reader = surface.renderRead({ host, markdown: '# complete <unsafe> original' });
    w.console.error = expectedError;
    Object.defineProperty(w.Element.prototype, 'innerHTML', descriptor);
    assert.equal(host.querySelector('pre').textContent, '# complete <unsafe> original');
    assert.ok(host.querySelector('[role="status"]').textContent.includes('unavailable'));
    reader.destroy();
    console.log('PASS: exact 4 MiB UTF-8 boundary and complete literal fallback after rendering failure');

    let changed = '';
    const editor = surface.createEditor({ host, text: '# Complete draft\n\nText', ariaLabel: 'Edit fixture', onChange: text => { changed = text; } });
    const shell = host.querySelector('.ora-document-editor');
    const root = shell.shadowRoot;
    const content = root.querySelector('.cm-content');
    const view = EditorView.findFromDOM(content);
    assert.ok(view && root.querySelector('style'), 'the shipped view and its runtime styles mount');
    assert.ok(root.querySelector('style').textContent.includes('.cm-content'));
    assert.equal(w.document.head.querySelector('style'), null, 'styles remain local to the disposable editor root');
    assert.equal(content.getAttribute('aria-label'), 'Edit fixture');
    assert.equal(host.querySelector('textarea'), null);
    editor.focus();
    assert.equal(root.activeElement, content);
    view.dispatch({ changes: { from: view.state.doc.length, insert: ' edited' }, selection: { anchor: 4 }, userEvent: 'input.type' });
    assert.equal(editor.getText(), '# Complete draft\n\nText edited');
    assert.equal(changed, editor.getText());
    const selection = view.state.selection.main.anchor;
    editor.setDisabled(true);
    assert.equal(content.getAttribute('contenteditable'), 'false');
    assert.equal(content.getAttribute('aria-disabled'), 'true');
    assert.equal(view.state.selection.main.anchor, selection);
    editor.setDisabled(false);
    content.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'z', code: 'KeyZ', ctrlKey: true, bubbles: true, cancelable: true }));
    assert.equal(editor.getText(), '# Complete draft\n\nText', 'undo survives disabling and re-enabling');
    assert.throws(() => surface.createEditor({ host: other, text: 'second' }), /already open/);
    assert.throws(() => surface.renderRead({ host, markdown: 'replace draft' }), /current editor/);
    const daily = surface.renderRead({ host: other, markdown: '# Read elsewhere' });
    assert.ok(other.querySelector('h1'));
    daily.destroy(); daily.destroy();
    assert.equal(editor.getText(), '# Complete draft\n\nText', 'another reader cannot disturb the draft');
    editor.destroy(); editor.destroy();
    await tick();
    assert.equal(host.childNodes.length, 0);
    assert.equal(shell.isConnected, false);
    assert.equal(root.querySelector('style'), null);
    assert.equal(w.document.querySelector('style'), null);
    const next = surface.createEditor({ host, text: 'next' });
    assert.ok(host.firstChild.shadowRoot.querySelector('style'), 'a later editor mounts fresh working styles');
    next.destroy();
    console.log('PASS: real CodeMirror editing, focus, disable/undo, one-editor ownership, host isolation and idempotent view/style teardown');

    const html = fs.readFileSync(path.resolve(__dirname, '../../index-v3.html'), 'utf8');
    const bundleIndex = html.indexOf('/static/vendor/document-surface/ora-document-surface.js');
    assert.ok(bundleIndex >= 0 && bundleIndex < html.indexOf('/static/js/library-workspace.js') && bundleIndex < html.indexOf('/static/js/overview-desktop.js'));
    const notices = fs.readFileSync(path.resolve(__dirname, '../vendor/document-surface/THIRD_PARTY_NOTICES.txt'), 'utf8');
    assert.ok(notices.includes('@codemirror/view 6.43.11') && notices.includes('dompurify 3.4.14') && notices.includes('markdown-it 15.0.1'));
    assert.ok(!notices.includes('jsdom ') && !notices.includes('esbuild ') && !notices.includes('@codemirror/lang-javascript '));
    console.log('PASS: local bundle load order and runtime-only license inventory');
  } finally { w.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
