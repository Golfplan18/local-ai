'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { AsyncResource } = require('node:async_hooks');

test('approved browser targets stay bound across page and document drift', async () => {
  require('../patch-playwright.cjs').patch();
  const { chromium } = require('../node_modules/playwright-core');
  const { createConnection } = require('../node_modules/@playwright/mcp');
  const { Client } = require('../node_modules/playwright-core/lib/utilsBundle');
  const guard = require('../browser-target-binding.cjs');
  const root = process.env.ORA_BROWSER_TEST_IPC_ROOT;
  assert.ok(root && path.isAbsolute(root), 'explicit task-owned IPC root is required');
  const executable = process.env.ORA_BROWSER_TEST_EXECUTABLE;
  assert.ok(executable && path.isAbsolute(executable)
    && path.basename(executable) === 'chrome-headless-shell'
    && !executable.includes('.app/'), 'explicit dedicated headless shell is required; no full browser fallback');
  fs.mkdirSync(root);
  let context, server, client;
  const originalSend = guard.beforeSend;
  const fixture = new AsyncResource('independent fixture');
  const html = `<!doctype html><body>
    <button id="click" onclick="window.clicks++">Click</button>
    <a id="nestedLink" href="/nested" onclick="event.preventDefault();this.focus();window.nestedClicks++"><span id="nestedLinkChild">Nested link</span></a>
    <input id="text"><textarea id="textarea"></textarea><input id="email" type="email"><input id="number" type="number"><input id="other">
    <div id="repeat" contenteditable="true" role="checkbox" aria-checked="false">Original repeated</div>
    <form onsubmit="event.preventDefault();window.submissions++;document.querySelector('#other').focus()"><input id="submit"></form>
    <iframe id="frame" srcdoc="<input id='frameText'><button id='frameButton' onclick='window.clicks=(window.clicks||0)+1'>Frame button</button>"></iframe>
    <label id="label" for="text" onclick="window.labelClicks++">Text label</label>
    <select id="select"><option>a</option><option>b</option></select>
    <input id="check" type="checkbox"><input id="file" type="file">
    <div id="source" draggable="true">Drag</div><div id="captureSource">Pointer drag</div><div id="drop" style="height:80px" ondragover="event.preventDefault()" ondrop="event.preventDefault();window.dropped++">Drop</div>
    <button id="dialog" onclick="window.answer=prompt('Original prompt')">Dialog</button>
    <button id="downDialog" onmousedown="window.downAnswer=prompt('Mouse down prompt')" onmouseup="window.mouseUps++">Mouse dialog</button>
    <input id="keyDialog" onkeydown="if(event.key==='Enter')window.keyAnswer=prompt('Key down prompt')" onkeyup="window.keyUps++">
    <input id="slowDialog" onkeydown="if(event.key==='A')window.slowAnswer=prompt('Typing prompt')">
    <div id="editor" contenteditable="true"><span id="editableChild">Child text</span><span id="editableOther">Keep me</span></div>
    <button id="navigate" onclick="location.href='/clicked'">Navigate</button>
    <script>window.clicks=0;window.nestedClicks=0;window.dropped=0;window.keys=[];window.releases=[];window.labelClicks=0;window.submissions=0;window.mouseUps=0;window.keyUps=0;
    document.addEventListener('keydown',e=>keys.push([e.target.id,e.key,e.isTrusted]));
    document.addEventListener('keyup',e=>releases.push([e.target.id,e.key,e.isTrusted]));</script>`;
  try {
    context = await chromium.launchPersistentContext(path.join(root, 'profile'), {
      executablePath: executable, headless: true,
      serviceWorkers: 'block', env: { ...process.env, TMPDIR: root, MAC_CHROMIUM_TMPDIR: root },
      args: ['--disable-crash-reporter', '--disable-crashpad'],
    });
    await context.route('**/*', route => route.fulfill({ contentType: 'text/html', body: html }));
    const first = context.pages()[0];
    await first.goto('https://ora-fixture.invalid/same');
    const second = await context.newPage();
    await second.goto(first.url());
    server = await createConnection({ browser: { isolated: false },
      outputDir: root, timeouts: { action: 1500, navigation: 1500 },
    }, () => context);
    const serverTransport = { start: async () => {}, close: async () => {},
      send: async message => queueMicrotask(() => clientTransport.onmessage?.(message)) };
    const clientTransport = { start: async () => {}, close: async () => {},
      send: async message => queueMicrotask(() => serverTransport.onmessage?.(message)) };
    await server.connect(serverTransport);
    client = new Client({ name: 'ora-network-denied-fixture', version: '1' });
    await client.connect(clientTransport);
    const call = (name, args = {}, ora) => client.callTool({ name,
      arguments: { ...args, ...(ora ? { _meta: { ora } } : {}) } });
    const okay = result => { assert.ok(!result.isError, JSON.stringify(result)); return result; };
    const prepare = async (name, args) => okay(await call(name, args, { phase: 'prepare' })).structuredContent.oraBrowserBinding;
    const execute = async (name, args, binding) => call(name, args, { phase: 'execute', id: binding.id });
    const action = async (name, args = {}) => okay(await execute(name, args, await prepare(name, args)));
    const select = async index => okay(await call('browser_tabs', { action: 'select', index }));
    const refused = result => assert.equal(result.isError, true, JSON.stringify(result));
    const click = { target: '#click' };
    okay(await call('browser_snapshot'));
    await select(0);

    // Same URL does not identify a Page. Replacement and closure cannot send to
    // the fallback selected tab, nor restore an old approval through ABA.
    const approved = await prepare('browser_click', click);
    assert.deepEqual(await prepare('browser_click', click), approved);
    await select(1);
    refused(await execute('browser_click', click, approved));
    const replacement = await prepare('browser_click', click);
    assert.notEqual(replacement.id, approved.id);
    assert.notEqual(replacement.page, approved.page);
    await select(0);
    refused(await execute('browser_click', click, approved));
    const closing = await prepare('browser_click', click);
    await first.close();
    refused(await execute('browser_click', click, closing));
    assert.equal(await second.evaluate(() => clicks), 0);

    // Replace a same-selector node without changing the document.
    const changedNode = await prepare('browser_click', click);
    await second.locator('#click').evaluate(node => node.replaceWith(node.cloneNode(true)));
    refused(await execute('browser_click', click, changedNode));
    assert.equal(await second.evaluate(() => clicks), 0);

    // Real native actionability await: a reload must not retarget the locator.
    const raw = second._connection.toImpl(second);
    const originalPrecheck = raw.performActionPreChecks;
    const duringAwait = await prepare('browser_click', click);
    let reloaded = false;
    let reload;
    raw.performActionPreChecks = async function(progress) {
      if (!reloaded) { reloaded = true; reload = fixture.runInAsyncScope(() => second.reload()); await reload; }
      return originalPrecheck.call(this, progress);
    };
    try { refused(await execute('browser_click', click, duringAwait)); }
    finally { raw.performActionPreChecks = originalPrecheck; }
    await reload;
    assert.equal(await second.evaluate(() => clicks), 0);

    // Real pointer retry: hide the reviewed button, then reload once Playwright
    // reaches its retry wait. No substitute node receives a click.
    await second.locator('#click').evaluate(node => node.hidden = true);
    const duringRetry = await prepare('browser_click', click);
    let calls = 0;
    reload = undefined;
    raw.performActionPreChecks = async function(progress) {
      if (++calls === 3) { reload = fixture.runInAsyncScope(() => second.reload()); await reload; }
      return originalPrecheck.call(this, progress);
    };
    try { refused(await execute('browser_click', click, duringRetry)); }
    finally { raw.performActionPreChecks = originalPrecheck; }
    await reload;
    assert.ok(calls >= 3, 'native pointer retry was reached');
    assert.equal(await second.evaluate(() => clicks), 0);

    // Drift after native actionability but before the connector's final send.
    const finalSend = await prepare('browser_click', click);
    let intercepted = false;
    // Use the test's original async context for the independent page reload.
    guard.beforeSend = async (session, method, params) => {
      if (guard.active() && method === 'Input.dispatchMouseEvent' && !intercepted) {
        intercepted = true;
        await fixture.runInAsyncScope(() => second.reload());
      }
      return originalSend(session, method, params);
    };
    try { refused(await execute('browser_click', click, finalSend)); }
    finally { guard.beforeSend = originalSend; }
    assert.ok(intercepted);
    assert.equal(await second.evaluate(() => clicks), 0);

    // A document can also reload after the native press was delivered. Its old
    // pressed state must not alter a new approved action in the new document.
    const releaseReload = await prepare('browser_click', click);
    let reloadedAtRelease = false;
    guard.beforeSend = async (session, method, params) => {
      if (guard.active() && method === 'Input.dispatchMouseEvent'
          && params.type === 'mouseReleased' && !reloadedAtRelease) {
        reloadedAtRelease = true;
        await fixture.runInAsyncScope(() => second.reload());
      }
      return originalSend(session, method, params);
    };
    try { refused(await execute('browser_click', click, releaseReload)); }
    finally { guard.beforeSend = originalSend; }
    assert.ok(reloadedAtRelease);
    assert.equal(await second.evaluate(() => clicks), 0);
    await action('browser_click', click);
    assert.equal(await second.evaluate(() => clicks), 1);
    await second.evaluate(() => clicks = 0);

    // Label-controlled inputs and native selected option nodes are intrinsic
    // targets too, not a fresh value/label lookup after review.
    const labelCall = { target: '#label', text: 'wrong' };
    const label = await prepare('browser_type', labelCall);
    await second.locator('#label').evaluate(node => node.htmlFor = 'other');
    refused(await execute('browser_type', labelCall, label));
    assert.equal(await second.locator('#other').inputValue(), '');
    await second.locator('#label').evaluate(node => node.htmlFor = 'text');
    const optionCall = { target: '#select', values: ['b'] };
    const option = await prepare('browser_select_option', optionCall);
    await second.locator('#select option').last().evaluate(node => node.replaceWith(node.cloneNode(true)));
    refused(await execute('browser_select_option', optionCall, option));
    assert.equal(await second.locator('#select').inputValue(), 'a');

    const typing = await prepare('browser_type', { target: '#text', text: 'wrong' });
    const focusFixture = new AsyncResource('independent focus drift');
    let focusMoved = false;
    guard.beforeSend = async (session, method, params) => {
      if (guard.active() && method === 'Input.insertText' && !focusMoved) {
        focusMoved = true;
        await focusFixture.runInAsyncScope(() => second.locator('#other').focus());
      }
      return originalSend(session, method, params);
    };
    try { refused(await execute('browser_type', { target: '#text', text: 'wrong' }, typing)); }
    finally { guard.beforeSend = originalSend; focusFixture.emitDestroy(); }
    assert.ok(focusMoved, 'native fill reached its keyboard delivery await');
    assert.equal(await second.locator('#other').inputValue(), '');

    // Native fill owns the whole approved text control at its final insertion
    // or deletion. A same-control caret cannot narrow the approved effect.
    for (const [target, initial] of [
      ['#text', 'Original input'], ['#textarea', 'Original textarea'],
    ]) {
      for (const text of ['Collapsed replacement', '']) {
        await second.locator(target).fill(initial);
        const args = { target, text };
        const approval = await prepare('browser_type', args);
        let selectionCollapsed = false;
        guard.beforeSend = async (session, method, params) => {
          const mutation = text ? method === 'Input.insertText'
            : method === 'Input.dispatchKeyEvent' && params.type !== 'keyUp' && params.key === 'Delete';
          if (guard.active() && mutation && !selectionCollapsed) {
            selectionCollapsed = true;
            await fixture.runInAsyncScope(() => second.locator(target).evaluate(node => {
              node.setSelectionRange(1, 1);
            }));
          }
          return originalSend(session, method, params);
        };
        try { refused(await execute('browser_type', args, approval)); }
        finally { guard.beforeSend = originalSend; }
        assert.ok(selectionCollapsed, `collapsed ${target} selection reached native ${text ? 'insertion' : 'deletion'}`);
        assert.equal(await second.locator(target).inputValue(), initial);
      }
    }
    await second.locator('#text').fill('');
    await second.locator('#textarea').fill('');

    // Email and number inputs support native fill but intentionally expose no
    // numeric selection range. Collapse their internal selection with a real
    // key event; the final guard must reselect the exact bound control so both
    // replacement and deletion still own the whole target.
    for (const [target, initial, replacement] of [
      ['#email', 'old@example.test', 'new@example.test'], ['#number', '17', '29'],
    ]) {
      for (const text of [replacement, '']) {
        await second.locator(target).fill(initial);
        const args = { target, text };
        const approval = await prepare('browser_type', args);
        let selectionCollapsed = false;
        guard.beforeSend = async (session, method, params) => {
          const mutation = text ? method === 'Input.insertText'
            : method === 'Input.dispatchKeyEvent' && params.type !== 'keyUp' && params.key === 'Delete';
          if (guard.active() && mutation && !selectionCollapsed) {
            selectionCollapsed = true;
            await fixture.runInAsyncScope(() => second.keyboard.press('ArrowRight'));
          }
          return originalSend(session, method, params);
        };
        try { okay(await execute('browser_type', args, approval)); }
        finally { guard.beforeSend = originalSend; }
        assert.ok(selectionCollapsed, `collapsed ${target} selection reached native ${text ? 'insertion' : 'deletion'}`);
        assert.equal(await second.locator(target).inputValue(), text);
      }
    }

    // A refusal after Playwright marks Control pressed must not turn the next
    // independently approved A into Control+A or leave a repeating key behind.
    await second.locator('#text').focus();
    const controlKey = { key: 'Control+A' };
    const controlApproval = await prepare('browser_press_key', controlKey);
    let controlRefused = false;
    guard.beforeSend = async (session, method, params) => {
      if (guard.active() && method === 'Input.dispatchKeyEvent' && params.key.toLowerCase() === 'a' && !controlRefused) {
        controlRefused = true;
        await fixture.runInAsyncScope(() => second.locator('#other').focus());
      }
      return originalSend(session, method, params);
    };
    try { refused(await execute('browser_press_key', controlKey, controlApproval)); }
    finally { guard.beforeSend = originalSend; }
    assert.ok(controlRefused);
    assert.ok(await second.evaluate(() => keys.some(([id, key]) => id === 'text' && key === 'Control')));
    assert.equal(await second.evaluate(() => keys.some(([id, key]) => id === 'other' && key === 'Control')), false);
    assert.equal(await second.evaluate(() => releases.some(([id, key]) => id === 'other' && key === 'Control')), false);
    await action('browser_press_key', { key: 'A' });
    assert.equal(await second.locator('#other').inputValue(), 'A');
    assert.equal(raw.keyboard._pressedKeys.size, 0);
    assert.equal(raw.keyboard._pressedModifiers.size, 0);
    await second.locator('#other').fill('');

    // An ordinary release is a separate native send. If focus moves after its
    // approved keydown, the keyup must not be delivered to the new recipient.
    await second.locator('#text').focus();
    const releaseArgs = { key: 'ArrowRight' };
    const releaseApproval = await prepare('browser_press_key', releaseArgs);
    const releasesBefore = await second.evaluate(() => releases.length);
    let movedBeforeRelease = false;
    guard.beforeSend = async (session, method, params) => {
      if (guard.active() && method === 'Input.dispatchKeyEvent'
          && params.type === 'keyUp' && params.key === 'ArrowRight' && !movedBeforeRelease) {
        movedBeforeRelease = true;
        await fixture.runInAsyncScope(() => second.locator('#other').focus());
      }
      return originalSend(session, method, params);
    };
    try { refused(await execute('browser_press_key', releaseArgs, releaseApproval)); }
    finally { guard.beforeSend = originalSend; }
    assert.ok(movedBeforeRelease);
    assert.ok(await second.evaluate(() => keys.some(([id, key, trusted]) =>
      id === 'text' && key === 'ArrowRight' && trusted)));
    assert.equal(await second.evaluate(() => releases.length), releasesBefore);
    assert.equal(raw.keyboard._pressedKeys.size, 0);

    // Both closed-root focus and a page-forged activeElement must preserve the
    // actual native keyboard receiver, including click modifier keydowns.
    for (const closed of [true, false]) {
      await second.evaluate(closed => {
        window.focusEvents = [];
        if (closed) {
          const host = document.createElement('div'); host.id = 'focusHost';
          document.body.append(host);
          const root = host.attachShadow({ mode: 'closed' });
          root.innerHTML = '<input id="closedA"><input id="closedB">';
          window.focusInputs = [...root.querySelectorAll('input')];
        } else {
          window.focusInputs = [document.querySelector('#text'), document.querySelector('#other')];
          Object.defineProperty(document, 'activeElement', { configurable: true, get: () => focusInputs[0] });
        }
        for (const node of focusInputs) {
          node.value = '';
          node.addEventListener('keydown', event => focusEvents.push([node.id, event.key, event.isTrusted]));
          node.addEventListener('keyup', event => focusEvents.push([node.id, event.key, event.isTrusted]));
        }
        focusInputs[0].focus();
      }, closed);
      await action('browser_press_key', { key: 'A' });
      assert.deepEqual(await second.evaluate(() => focusInputs.map(node => node.value)), ['A', '']);
      assert.ok(await second.evaluate(() => focusEvents.some(([id, key, trusted]) => id === focusInputs[0].id && key === 'A' && trusted)));

      const keyArgs = { key: 'Control+A' };
      const keyApproval = await prepare('browser_press_key', keyArgs);
      let hiddenFocusMoved = false;
      guard.beforeSend = async (session, method, params) => {
        if (guard.active() && method === 'Input.dispatchKeyEvent'
            && params.key.toLowerCase() === 'a' && !hiddenFocusMoved) {
          hiddenFocusMoved = true;
          await fixture.runInAsyncScope(() => second.evaluate(() => focusInputs[1].focus()));
        }
        return originalSend(session, method, params);
      };
      try { refused(await execute('browser_press_key', keyArgs, keyApproval)); }
      finally { guard.beforeSend = originalSend; }
      assert.ok(hiddenFocusMoved);
      assert.equal(await second.evaluate(() => focusEvents.some(([id]) => id === focusInputs[1].id)), false);
      assert.equal(raw.keyboard._pressedKeys.size, 0);
      assert.equal(raw.keyboard._pressedModifiers.size, 0);
      await action('browser_press_key', { key: 'B' });
      assert.deepEqual(await second.evaluate(() => focusInputs.map(node => node.value)), ['A', 'B']);

      await second.evaluate(() => { focusInputs[0].focus(); focusEvents = []; });
      const modifiedClick = { ...click, modifiers: ['Control'] };
      const clickApproval = await prepare('browser_click', modifiedClick);
      await second.evaluate(() => focusInputs[1].focus());
      refused(await execute('browser_click', modifiedClick, clickApproval));
      assert.deepEqual(await second.evaluate(() => focusEvents), []);
      assert.equal(await second.evaluate(() => clicks), 0);
      await second.evaluate(closed => {
        if (closed) document.querySelector('#focusHost').remove();
        else {
          delete document.activeElement;
          for (const node of focusInputs) node.value = '';
        }
        delete window.focusInputs;
      }, closed);
    }

    // An Enter submission can deliberately move focus before key release. It
    // must return success once, without asking the caller to retry a submission.
    await action('browser_type', { target: '#submit', text: 'submit once', submit: true });
    assert.equal(await second.evaluate(() => submissions), 1);
    assert.equal(await second.evaluate(() => document.activeElement.id), 'other');
    assert.equal(await second.evaluate(() => keys.filter(([id, key, trusted]) => id === 'submit' && key === 'Enter' && trusted).length), 1);

    // Receiving focus must include every iframe owner, not just the input in
    // the child document, when top-level focus is taken away.
    const frameTarget = '#frame >> internal:control=enter-frame >> #frameText';
    const frameInput = second.frameLocator('#frame').locator('#frameText');
    await action('browser_type', { target: frameTarget, text: 'frame native' });
    assert.equal(await frameInput.inputValue(), 'frame native');
    await frameInput.fill('');
    await action('browser_type', { target: frameTarget, text: 'slow frame', slowly: true });
    assert.equal(await frameInput.inputValue(), 'slow frame');
    const frameFill = { fields: [{ name: 'Frame text', target: frameTarget, type: 'textbox', value: 'wrong frame' }] };
    const frameApproval = await prepare('browser_fill_form', frameFill);
    let outerFocusMoved = false;
    guard.beforeSend = async (session, method, params) => {
      if (guard.active() && method === 'Input.insertText' && !outerFocusMoved) {
        outerFocusMoved = true;
        await fixture.runInAsyncScope(() => second.locator('#other').focus());
      }
      return originalSend(session, method, params);
    };
    try { refused(await execute('browser_fill_form', frameFill, frameApproval)); }
    finally { guard.beforeSend = originalSend; }
    assert.ok(outerFocusMoved);
    assert.equal(await second.evaluate(() => document.activeElement.id), 'other');
    assert.notEqual(await frameInput.inputValue(), 'wrong frame');
    assert.equal(await second.locator('#other').inputValue(), '');
    await action('browser_fill_form', frameFill);
    assert.equal(await frameInput.inputValue(), 'wrong frame');

    // Native fill can select a child inside an editing host. Bind the host's
    // focus separately, while keeping the actual selection inside that child.
    await action('browser_type', { target: '#editableChild', text: 'Child filled' });
    // Chromium may remove the selected span as part of native editing.
    assert.equal(await second.locator('#editor').textContent(), 'Child filledKeep me');
    const resetEditable = () => second.locator('#editor').evaluate(node => {
      node.innerHTML = '<span id="editableChild">Child text</span><span id="editableOther">Keep me</span>';
    });
    await resetEditable();
    await second.locator('#other').focus();
    const editableFill = { fields: [
      { name: 'Editable child', target: '#editableChild', type: 'textbox', value: 'Form filled' },
      { name: 'Later ordinary field', target: '#text', type: 'textbox', value: 'Later filled' },
    ] };
    await action('browser_fill_form', editableFill);
    assert.equal(await second.locator('#editor').textContent(), 'Form filledKeep me');
    assert.equal(await second.locator('#text').inputValue(), 'Later filled');
    await resetEditable();
    await action('browser_type', { target: '#editableChild', text: '' });
    assert.equal(await second.locator('#editor').textContent(), 'Keep me');
    assert.equal(raw.keyboard._pressedKeys.size, 0);
    for (const text of ['Collapsed replacement', '']) {
      await resetEditable();
      const args = { target: '#editableChild', text };
      const approval = await prepare('browser_type', args);
      let selectionCollapsed = false;
      guard.beforeSend = async (session, method, params) => {
        const mutation = text ? method === 'Input.insertText'
          : method === 'Input.dispatchKeyEvent' && params.type !== 'keyUp' && params.key === 'Delete';
        if (guard.active() && mutation && !selectionCollapsed) {
          selectionCollapsed = true;
          await fixture.runInAsyncScope(() => second.locator('#editableChild').evaluate(node => {
            const range = document.createRange();
            range.setStart(node.firstChild, 1); range.collapse(true);
            const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
          }));
        }
        return originalSend(session, method, params);
      };
      try { refused(await execute('browser_type', args, approval)); }
      finally { guard.beforeSend = originalSend; }
      assert.ok(selectionCollapsed, `collapsed selection reached native ${text ? 'insertion' : 'deletion'}`);
      assert.equal(await second.locator('#editor').textContent(), 'Child textKeep me');
    }
    await resetEditable();
    await second.locator('#editor').focus();
    await second.locator('#editableChild').evaluate(node => {
      const range = document.createRange();
      range.setStart(node.firstChild, 5); range.collapse(true);
      const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
    });
    await action('browser_type', { target: '#editableChild', text: ' slow', slowly: true });
    assert.equal(await second.locator('#editor').textContent(), 'Child slow textKeep me');
    await resetEditable();
    const editableApproval = await prepare('browser_fill_form', editableFill);
    let selectionMoved = false;
    guard.beforeSend = async (session, method, params) => {
      if (guard.active() && method === 'Input.insertText' && !selectionMoved) {
        selectionMoved = true;
        await fixture.runInAsyncScope(() => second.locator('#editableOther').evaluate(node => {
          const range = document.createRange(); range.selectNodeContents(node);
          const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
        }));
      }
      return originalSend(session, method, params);
    };
    try { refused(await execute('browser_fill_form', editableFill, editableApproval)); }
    finally { guard.beforeSend = originalSend; }
    assert.ok(selectionMoved);
    assert.equal(await second.locator('#editableOther').textContent(), 'Keep me');
    await second.locator('#text').fill('');

    // Every fill-form occurrence contributes to one target binding. The first
    // field sees the same dual-role node as an already-unchecked checkbox; the
    // later textbox fill must retain its stronger direct/native-fill requirements
    // and reject a same-node caret for both insertion and deletion.
    for (const text of ['Collapsed form replacement', '']) {
      await second.locator('#repeat').evaluate(node => {
        node.setAttribute('aria-checked', 'false'); node.textContent = 'Original repeated';
      });
      const repeatedFill = { fields: [
        { name: 'Dual-role control', target: '#repeat', type: 'checkbox', value: 'false' },
        { name: 'Same control as textbox', target: '#repeat', type: 'textbox', value: text },
      ] };
      const repeatedApproval = await prepare('browser_fill_form', repeatedFill);
      let selectionCollapsed = false;
      guard.beforeSend = async (session, method, params) => {
        const mutation = text ? method === 'Input.insertText'
          : method === 'Input.dispatchKeyEvent' && params.type !== 'keyUp' && params.key === 'Delete';
        if (guard.active() && mutation && !selectionCollapsed) {
          selectionCollapsed = true;
          await fixture.runInAsyncScope(() => second.locator('#repeat').evaluate(node => {
            const range = document.createRange();
            range.setStart(node.firstChild, 1); range.collapse(true);
            const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
          }));
        }
        return originalSend(session, method, params);
      };
      try { refused(await execute('browser_fill_form', repeatedFill, repeatedApproval)); }
      finally { guard.beforeSend = originalSend; }
      assert.ok(selectionCollapsed, `collapsed fill-form selection reached native ${text ? 'insertion' : 'deletion'}`);
      assert.equal(await second.locator('#repeat').textContent(), 'Original repeated');
    }

    // Native pointerdown may put an overlay over the still-connected target.
    // Recheck the release after that real handler, not concurrently with press.
    await second.locator('#click').evaluate(node => {
      window.pointerDowns = 0; window.wrongPointerUps = 0; window.lostCaptures = 0; window.gotCaptures = 0;
      node.addEventListener('pointerdown', event => {
        window.pointerDowns++;
        const rect = node.getBoundingClientRect();
        const overlay = document.createElement('div');
        overlay.id = 'overlay';
        overlay.style.cssText = `position:fixed;left:${rect.x}px;top:${rect.y}px;width:${rect.width}px;height:${rect.height}px;z-index:999`;
        overlay.onpointerup = () => window.wrongPointerUps++;
        document.body.append(overlay);
        const capturer = document.createElement('button');
        overlay.attachShadow({ mode: 'closed' }).append(capturer);
        capturer.addEventListener('gotpointercapture', () => window.gotCaptures++);
        capturer.addEventListener('lostpointercapture', () => {
          window.lostCaptures++;
          capturer.setPointerCapture(event.pointerId);
        });
        capturer.setPointerCapture(event.pointerId);
      }, { once: true });
    });
    let captureCommitted = false;
    guard.beforeSend = async (session, method, params) => {
      if (guard.active() && method === 'Input.dispatchMouseEvent'
          && params.type === 'mouseReleased' && !captureCommitted) {
        captureCommitted = true;
        // Commit the page's pending capture with a real move before refusal,
        // so cleanup also encounters the native lost-capture/recapture path.
        // Mouse.up has already removed its connector button by this seam, so
        // preserve the actually delivered press explicitly in this event.
        await fixture.runInAsyncScope(() => raw.delegate._mainFrameSession._client.send('Input.dispatchMouseEvent', {
          type: 'mouseMoved', x: params.x + 1, y: params.y + 1, button: 'left', buttons: 1, modifiers: 0,
        }));
      }
      return originalSend(session, method, params);
    };
    let captureResult;
    try { captureResult = await execute('browser_click', click, await prepare('browser_click', click)); refused(captureResult); }
    finally { guard.beforeSend = originalSend; }
    assert.ok(captureCommitted);
    assert.equal(await second.evaluate(() => pointerDowns), 1);
    assert.equal(await second.evaluate(() => wrongPointerUps), 0);
    assert.equal(await second.evaluate(() => gotCaptures), 1, JSON.stringify(captureResult));
    assert.equal(await second.evaluate(() => lostCaptures), 1, JSON.stringify(captureResult));
    assert.equal(await second.evaluate(() => clicks), 0);
    await second.locator('#other').evaluate(node => {
      node.onpointermove = event => window.recoveryHoverButtons = event.buttons;
    });
    await action('browser_hover', { target: '#other' });
    assert.equal(await second.evaluate(() => recoveryHoverButtons), 0);
    await second.locator('#overlay').evaluate(node => node.remove());
    await action('browser_click', click);
    assert.equal(await second.evaluate(() => clicks), 1);
    await second.evaluate(() => clicks = 0);

    // Capture alone redirects native release: no overlay, movement, or target
    // replacement is needed. Check pending and committed closed-root capture.
    for (const commitCapture of [false, true]) {
      await second.locator('#click').evaluate(node => {
        window.captureUps = 0; window.captureDowns = 0;
        const host = document.createElement('div'); host.id = 'captureHost';
        document.body.append(host);
        const capturer = document.createElement('button');
        host.attachShadow({ mode: 'closed' }).append(capturer);
        capturer.onpointerup = () => window.captureUps++;
        node.addEventListener('pointerdown', event => {
          window.captureDowns++;
          capturer.setPointerCapture(event.pointerId);
        }, { once: true });
      });
      let releaseReached = false;
      guard.beforeSend = async (session, method, params) => {
        if (guard.active() && !guard.active().recovering && method === 'Input.dispatchMouseEvent'
            && params.type === 'mouseReleased' && !releaseReached) {
          releaseReached = true;
          if (commitCapture) await fixture.runInAsyncScope(() => raw.delegate._mainFrameSession._client.send('Input.dispatchMouseEvent', {
            type: 'mouseMoved', x: params.x, y: params.y, button: 'left', buttons: 1, modifiers: 0,
          }));
          assert.equal(await fixture.runInAsyncScope(() => second.evaluate(({ x, y }) =>
            document.elementFromPoint(x, y).id, params)), 'click');
        }
        return originalSend(session, method, params);
      };
      try { refused(await execute('browser_click', click, await prepare('browser_click', click))); }
      finally { guard.beforeSend = originalSend; }
      assert.ok(releaseReached);
      assert.equal(await second.evaluate(() => captureDowns), 1);
      assert.equal(await second.evaluate(() => captureUps), 0);
      assert.equal(await second.evaluate(() => clicks), 0);
      assert.equal(raw.mouse._buttons.size, 0);
      await second.locator('#captureHost').evaluate(node => node.remove());
      await action('browser_click', click);
      assert.equal(await second.evaluate(() => clicks), 1);
      await second.evaluate(() => clicks = 0);
    }

    const hoverApproval = await prepare('browser_hover', click);
    let hoverDisplaced = false;
    guard.beforeSend = async (session, method, params) => {
      if (guard.active() && method === 'Input.dispatchMouseEvent' && params.type === 'mouseMoved' && !hoverDisplaced) {
        hoverDisplaced = true;
        await fixture.runInAsyncScope(() => second.locator('#click').evaluate(node => node.style.transform = 'translateX(400px)'));
      }
      return originalSend(session, method, params);
    };
    try { refused(await execute('browser_hover', click, hoverApproval)); }
    finally { guard.beforeSend = originalSend; }
    assert.ok(hoverDisplaced);
    await second.locator('#click').evaluate(node => node.style.transform = '');

    // Pointer authentication retains native iframe geometry, including a
    // transformed owner, rather than rejecting frames Playwright can target.
    await second.locator('#frame').evaluate(node => node.style.transform = 'translateX(35px) scale(0.9)');
    const frameButton = '#frame >> internal:control=enter-frame >> #frameButton';
    await action('browser_hover', { target: frameButton });
    await action('browser_click', { target: frameButton });
    assert.equal(await second.frameLocator('#frame').locator('#frameButton').evaluate(() => clicks), 1);

    // A fractional layout boundary must not make hit authentication inspect a
    // different point from the actual native event. Both use the snapped point.
    await second.evaluate(() => {
      window.boundaryClicks = 0; window.wrongBoundary = 0;
      const node = document.createElement('button'); node.id = 'fractional';
      node.style.cssText = 'position:fixed;left:120.15px;top:500.15px;width:20.2px;height:20.2px;margin:0;padding:0;border:0';
      node.onclick = () => window.boundaryClicks++;
      document.body.append(node);
    });
    const boundaryArgs = { target: '#fractional' };
    const boundaryApproval = await prepare('browser_click', boundaryArgs);
    let boundaryPoint;
    guard.beforeSend = async (session, method, params) => {
      if (guard.active() && method === 'Input.dispatchMouseEvent' && params.type === 'mousePressed' && !boundaryPoint) {
        boundaryPoint = { x: params.x, y: params.y };
        await fixture.runInAsyncScope(() => second.evaluate(() => {
          const overlay = document.createElement('button'); overlay.id = 'fractionalOverlay';
          overlay.style.cssText = 'position:fixed;left:130.2px;top:500px;width:0.5px;height:25px;border:0;padding:0;z-index:999';
          overlay.onpointerdown = () => window.wrongBoundary++;
          document.body.append(overlay);
        }));
      }
      return originalSend(session, method, params);
    };
    try { refused(await execute('browser_click', boundaryArgs, boundaryApproval)); }
    finally { guard.beforeSend = originalSend; }
    assert.ok(Number.isInteger(boundaryPoint?.x) && Number.isInteger(boundaryPoint?.y));
    assert.equal(await second.evaluate(() => boundaryClicks), 0);
    assert.equal(await second.evaluate(() => wrongBoundary), 0);
    await second.locator('#fractionalOverlay, #fractional').evaluateAll(nodes => nodes.forEach(node => node.remove()));
    await action('browser_click', click);
    assert.equal(await second.evaluate(() => clicks), 1);
    await second.evaluate(() => clicks = 0);

    // The destination of native HTML dragging is checked again immediately
    // before its drop send, even if an earlier drag event passed hit testing.
    const dragArgs = { startTarget: '#source', endTarget: '#drop' };
    const dragApproval = await prepare('browser_drag', dragArgs);
    let dropDisplaced = false;
    guard.beforeSend = async (session, method, params) => {
      if (guard.active() && method === 'Input.dispatchDragEvent' && params.type === 'drop' && !dropDisplaced) {
        dropDisplaced = true;
        await fixture.runInAsyncScope(() => second.locator('#drop').evaluate(node => node.style.transform = 'translateY(200px)'));
      }
      return originalSend(session, method, params);
    };
    try { refused(await execute('browser_drag', dragArgs, dragApproval)); }
    finally { guard.beforeSend = originalSend; }
    assert.ok(dropDisplaced, 'native HTML drag reached its final drop send');
    assert.equal(await second.evaluate(() => dropped), 0);
    await second.locator('#drop').evaluate(node => node.style.transform = '');
    await action('browser_drag', dragArgs);
    assert.equal(await second.evaluate(() => dropped), 1);
    await second.evaluate(() => dropped = 0);

    // Pointer capture stays with the reviewed source throughout a native drag,
    // even while the active endpoint advances to the reviewed destination.
    const captureDragArgs = { startTarget: '#captureSource', endTarget: '#drop' };
    await second.locator('#captureSource').evaluate(node => {
      window.sourceCaptureMoves = 0; window.sourceCaptureUps = 0;
      node.addEventListener('pointerdown', event => node.setPointerCapture(event.pointerId), { once: true });
      node.addEventListener('pointermove', () => window.sourceCaptureMoves++);
      node.addEventListener('pointerup', () => window.sourceCaptureUps++, { once: true });
    });
    await action('browser_drag', captureDragArgs);
    assert.ok(await second.evaluate(() => sourceCaptureMoves) > 0);
    assert.equal(await second.evaluate(() => sourceCaptureUps), 1);

    const dragReloadApproval = await prepare('browser_drag', dragArgs);
    let dragReloaded = false;
    guard.beforeSend = async (session, method, params) => {
      if (guard.active() && method === 'Input.dispatchDragEvent' && params.type === 'drop' && !dragReloaded) {
        dragReloaded = true;
        await fixture.runInAsyncScope(() => second.reload());
      }
      return originalSend(session, method, params);
    };
    try { refused(await execute('browser_drag', dragArgs, dragReloadApproval)); }
    finally { guard.beforeSend = originalSend; }
    assert.ok(dragReloaded);
    assert.equal(await second.evaluate(() => dropped), 0);
    await action('browser_drag', dragArgs);
    assert.equal(await second.evaluate(() => dropped), 1);
    await second.evaluate(() => dropped = 0);

    // Retained native target families still have their ordinary browser effects.
    await action('browser_click', { target: '#label' });
    assert.equal(await second.evaluate(() => labelClicks), 1);
    await action('browser_click', click);
    assert.equal(await second.evaluate(() => clicks), 1);
    await action('browser_hover', { target: '#click' });
    await action('browser_type', { target: '#text', text: 'native', slowly: true });
    assert.equal(await second.locator('#text').inputValue(), 'native');
    await action('browser_select_option', { target: '#select', values: ['b'] });
    assert.equal(await second.locator('#select').inputValue(), 'b');
    await action('browser_fill_form', { fields: [
      { name: 'Text', target: '#text', type: 'textbox', value: 'filled' },
      { name: 'Check', target: '#check', type: 'checkbox', value: 'true' },
      { name: 'Email', target: '#email', type: 'textbox', value: 'form@example.test' },
      { name: 'Number', target: '#number', type: 'textbox', value: '41' },
    ] });
    assert.equal(await second.locator('#text').inputValue(), 'filled');
    assert.equal(await second.locator('#check').isChecked(), true);
    assert.equal(await second.locator('#email').inputValue(), 'form@example.test');
    assert.equal(await second.locator('#number').inputValue(), '41');
    await action('browser_drag', { startTarget: '#source', endTarget: '#drop' });
    await action('browser_drop', { target: '#drop', data: { 'text/plain': 'native drop' } });
    assert.ok(await second.evaluate(() => dropped) >= 1);

    await second.locator('#text').focus();
    const focused = await prepare('browser_press_key', { key: 'X' });
    await second.locator('#other').focus();
    refused(await execute('browser_press_key', { key: 'X' }, focused));
    assert.equal(await second.locator('#other').inputValue(), '');
    await second.locator('#text').focus();
    await action('browser_press_key', { key: 'End' });
    await action('browser_press_key', { key: 'X' });
    await action('browser_press_key', { key: 'Tab' });
    assert.equal(await second.locator('#text').inputValue(), 'filledX');
    assert.ok(await second.evaluate(() => keys.some(([id, key, trusted]) => id === 'text' && key === 'X' && trusted)));

    // Click modifiers first reach the old focused element, before the click
    // intentionally changes focus. That keydown recipient needs its own bind.
    await second.locator('#text').focus();
    const modifiedClick = { target: '#click', modifiers: ['Alt'] };
    const modifierApproval = await prepare('browser_click', modifiedClick);
    await second.locator('#other').focus();
    refused(await execute('browser_click', modifiedClick, modifierApproval));
    assert.equal(await second.evaluate(() => keys.filter(([id, key]) => id === 'other' && key === 'Alt').length), 0);
    await second.locator('#text').focus();
    await action('browser_click', modifiedClick);
    assert.ok(await second.evaluate(() => keys.some(([id, key, trusted]) => id === 'text' && key === 'Alt' && trusted)));
    assert.equal(raw.keyboard._pressedModifiers.size, 0);

    // A label click can focus its captured associated control before modifier
    // release. Keep that control-rooted receiver alongside pointer retargets.
    const labelModifiedClick = { target: '#label', modifiers: ['Alt'] };
    await second.locator('#other').focus();
    const labelKeyStart = await second.evaluate(() => keys.length);
    const labelReleaseStart = await second.evaluate(() => releases.length);
    await action('browser_click', labelModifiedClick);
    assert.equal(await second.evaluate(() => labelClicks), 2);
    assert.equal(await second.evaluate(() => document.activeElement.id), 'text');
    assert.ok(await second.evaluate(start => keys.slice(start).some(([id, key, trusted]) =>
      id === 'other' && key === 'Alt' && trusted), labelKeyStart));
    assert.ok(await second.evaluate(start => releases.slice(start).some(([id, key, trusted]) =>
      id === 'text' && key === 'Alt' && trusted), labelReleaseStart));
    assert.equal(raw.keyboard._pressedModifiers.size, 0);

    // A nested click target can retarget to a link that receives focus before
    // the modifier release. Bind that native receiver separately from the
    // nested control so the completed click is not reported as a refusal.
    const nestedModifiedClick = { target: '#nestedLinkChild', modifiers: ['Alt'] };
    await second.locator('#text').focus();
    const nestedKeyStart = await second.evaluate(() => keys.length);
    const nestedReleaseStart = await second.evaluate(() => releases.length);
    await action('browser_click', nestedModifiedClick);
    assert.equal(await second.evaluate(() => nestedClicks), 1);
    assert.equal(await second.evaluate(() => document.activeElement.id), 'nestedLink');
    assert.ok(await second.evaluate(start => keys.slice(start).some(([id, key, trusted]) =>
      id === 'text' && key === 'Alt' && trusted), nestedKeyStart));
    assert.ok(await second.evaluate(start => releases.slice(start).some(([id, key, trusted]) =>
      id === 'nestedLink' && key === 'Alt' && trusted), nestedReleaseStart));
    assert.equal(raw.keyboard._pressedModifiers.size, 0);

    // The modal response is a separate call, but the original native mouse or
    // key action still owns its final release and cleans up only its targets.
    await action('browser_click', { target: '#downDialog' });
    await action('browser_handle_dialog', { accept: true, promptText: 'mouse accepted' });
    assert.equal(await second.evaluate(() => downAnswer), 'mouse accepted');
    assert.equal(await second.evaluate(() => mouseUps), 1);
    assert.equal(raw.mouse._buttons.size, 0);
    await second.locator('#keyDialog').focus();
    await action('browser_press_key', { key: 'Enter' });
    await action('browser_handle_dialog', { accept: true, promptText: 'key accepted' });
    assert.equal(await second.evaluate(() => keyAnswer), 'key accepted');
    assert.equal(await second.evaluate(() => keyUps), 1);
    assert.equal(raw.keyboard._pressedKeys.size, 0);
    await action('browser_type', { target: '#slowDialog', text: 'AB', slowly: true });
    await action('browser_handle_dialog', { accept: true, promptText: 'typing accepted' });
    assert.equal(await second.evaluate(() => slowAnswer), 'typing accepted');
    assert.equal(await second.locator('#slowDialog').inputValue(), 'AB');
    assert.equal(raw.keyboard._pressedKeys.size, 0);

    await action('browser_click', { target: '#dialog' });
    await action('browser_handle_dialog', { accept: true, promptText: 'accepted' });
    assert.equal(await second.evaluate(() => answer), 'accepted');
    await action('browser_click', { target: '#file' });
    const upload = path.join(root, 'upload.txt');
    fs.writeFileSync(upload, 'only fixture bytes');
    await action('browser_file_upload', { paths: [upload] });
    assert.equal(await second.locator('#file').evaluate(node => node.files[0].name), 'upload.txt');
    await action('browser_click', { target: '#file' });
    await action('browser_file_upload', {});
    await action('browser_click', { target: '#file' });
    await second.locator('#file').evaluate(node => node.remove());
    refused(await call('browser_file_upload', { paths: [upload] }, { phase: 'prepare' }));
    await action('browser_file_upload', { paths: [] });

    await second.goto('https://ora-fixture.invalid/next');
    const back = await prepare('browser_navigate_back', {});
    await second.evaluate(() => history.pushState({}, '', '/replaced-history'));
    refused(await execute('browser_navigate_back', {}, back));
    await action('browser_navigate_back');
    assert.equal(second.url(), 'https://ora-fixture.invalid/next');
    await action('browser_navigate_back');
    assert.equal(second.url(), 'https://ora-fixture.invalid/same');
    await action('browser_click', { target: '#navigate' });
    assert.equal(second.url(), 'https://ora-fixture.invalid/clicked');
    const policy = JSON.parse(fs.readFileSync(path.join(__dirname, '../../config/mcp-servers.json')))
      .servers.find(server => server.name === 'playwright').tools;
    for (const name of ['browser_evaluate', 'browser_run_code'])
      assert.ok(!policy[name] || policy[name].adapter === 'deny_opaque_code');
  } finally {
    guard.beforeSend = originalSend;
    await client?.close();
    await server?.close();
    await context?.close();
    fixture.emitDestroy();
    fs.rmSync(root, { recursive: true, force: true });
  }
});
