'use strict';

const { AsyncLocalStorage } = require('node:async_hooks');
const { randomUUID } = require('node:crypto');
const running = new AsyncLocalStorage();
const tools = new Set([
  'browser_click', 'browser_hover', 'browser_select_option', 'browser_type',
  'browser_drop', 'browser_drag', 'browser_fill_form', 'browser_press_key',
  'browser_handle_dialog', 'browser_file_upload', 'browser_navigate_back',
]);
const fail = () => { throw new Error('Approved browser target changed or is unavailable'); };
const supports = name => tools.has(name);
const active = () => running.getStore();
const impl = object => object._connection.toImpl(object);

function receivesKeys(node) {
  if (!node.isConnected) return false;
  // Walk outward from the actual node: getRootNode exposes its own closed
  // root, whereas walking inward through element.shadowRoot cannot do so.
  for (let current = node; current;) {
    const root = current.getRootNode();
    if (root.activeElement !== current) return false;
    current = root.host;
  }
  return true;
}

const hasFocus = async handle => (await handle._frame.utilityContext()).evaluate(receivesKeys, handle);

function editingHost(node) {
  if (!node.isContentEditable) return node;
  while (node.parentElement?.isContentEditable) node = node.parentElement;
  return node;
}

function selectionWithin(node, fullTarget = false) {
  if (!node.isContentEditable) {
    if (!fullTarget) return true;
    if (typeof node.selectionStart === 'number')
      return node.selectionStart === 0 && node.selectionEnd === node.value.length;
    // Chromium supports native fill for email and number controls, but does
    // not expose their internal selection through selectionStart/selectionEnd.
    // Re-select the exact bound control at the final guard instead of treating
    // an unobservable range as either trusted or unsupported.
    if (node.nodeName !== 'INPUT' || !['email', 'number'].includes(node.type)) return false;
    node.select();
    for (let current = node; current;) {
      const root = current.getRootNode();
      if (root.activeElement !== current) return false;
      current = root.host;
    }
    return true;
  }
  const selection = node.ownerDocument.defaultView.getSelection();
  if (selection?.rangeCount !== 1 || !node.contains(selection.anchorNode)
      || !node.contains(selection.focusNode)) return false;
  if (!fullTarget) return true;
  const actual = selection.getRangeAt(0);
  const expected = node.ownerDocument.createRange();
  expected.selectNodeContents(node);
  return actual.startContainer === expected.startContainer
    && actual.startOffset === expected.startOffset
    && actual.endContainer === expected.endContainer
    && actual.endOffset === expected.endOffset;
}

// One pending target belongs to the existing serialized backend. It is not an
// approval store: only Ora can authorize execution, using its authenticated gate.
async function dispose(backend) {
  const binding = backend._oraTarget;
  backend._oraTarget = undefined;
  if (binding) {
    binding.retired = true;
    if (!binding.nativePending) await disposeHandles(binding);
  }
}

async function disposeHandles(binding) {
  await Promise.all(binding.handles.splice(0).map(async handle => {
    try { await handle.dispose(); } catch {}
  }));
}

// The connector returns a modal before the native callback has completed.
// Keep that callback's targets alive, without keeping the approval slot or
// blocking the next (separately approved) dialog response.
async function nativeCompletion(callback) {
  const binding = active();
  if (!binding) return callback();
  binding.nativePending++;
  try { return await callback(); }
  catch (error) { await recoverInput(binding); throw error; }
  finally {
    binding.nativePending--;
    if (binding.retired && !binding.nativePending) await disposeHandles(binding);
  }
}

function check(binding) {
  if (binding.input?.recovered
      || (binding.backend._oraTarget !== binding && !(binding.retired && binding.nativePending))
      || binding.tab.page.isClosed()
      || binding.backend._context.currentTab() !== binding.tab) fail();
  for (const [frame, document] of binding.documents)
    if (frame._isDetached() || frame._currentDocument !== document) fail();
}

// Runtime.evaluate installs Playwright's shared utility library; rejecting that
// bootstrap poisons its cached context for later independent calls. Native DOM
// actions use callFunctionOn, and browser-provided code remains denied by Ora.
const effectSend = method => /^(Input\.|DOM\.setFileInputFiles$|Runtime\.callFunctionOn$|Page\.(handleJavaScriptDialog|navigateToHistoryEntry)$)/.test(method);
const sameDocuments = binding => [...binding.documents].every(([frame, document]) =>
  !frame._isDetached() && frame._currentDocument === document);
function checkSend(method) {
  const binding = active();
  if (!binding || !effectSend(method)) return;
  if (!binding.recovering) return check(binding);
  if (binding.tab.page.isClosed()
      || (method !== 'Input.dispatchDragEvent' && !sameDocuments(binding))) fail();
}

function inputState(kind, owner) {
  const binding = active();
  if (!binding) return;
  check(binding);
  if (owner._page !== binding.rawPage) fail();
  const input = binding.input;
  if (kind === 'keyboard' && !input.keyboard) input.keyboard = {
    keys: [...owner._pressedKeys], modifiers: [...owner._pressedModifiers],
  };
  if (kind === 'mouse' && !input.mouse) {
    input.mouse = { buttons: [...owner._buttons], lastButton: owner._lastButton };
    input.point = { x: owner._x, y: owner._y };
  }
}

// Record only events that reached the native transport. Playwright changes its
// input bookkeeping earlier, before an awaited guard can refuse the send.
function sent(method, params) {
  const binding = active();
  const input = binding?.input;
  if (!input || binding.recovering) return;
  if (method === 'Input.dispatchKeyEvent') {
    if (params.type === 'keyUp') input.keys.delete(params.code);
    else {
      input.keys.set(params.code, { params, focusChains: [
        [...(binding.inputTarget?.focusChain ?? binding.focusChain ?? [])],
      ] });
      // Tab and Enter are themselves allowed to move focus. Their own release,
      // and a chord's trailing modifier releases, still belong to this one
      // reviewed keyboard interaction.
      if (params.key === 'Tab' || params.key === 'Enter') input.focusTransition = true;
    }
  }
  if (method === 'Input.dispatchMouseEvent') {
    input.point = { x: params.x, y: params.y };
    if (params.type === 'mousePressed') {
      input.buttons.set(params.button, binding.pointerTarget.pointer);
      // Click modifiers are pressed against the reviewed old focus, while the
      // native click may then focus its reviewed target before releasing them.
      // Retain both approved receiver chains; no unrelated focus is admitted.
      const target = binding.pointerTarget;
      for (const clickedFocus of new Set([target.focusChain, target.receiverFocusChain]))
        for (const key of input.keys.values()) key.focusChains.push([...clickedFocus]);
    }
    if (params.type === 'mouseReleased') input.buttons.delete(params.button);
  }
}

async function keyReleaseFocusIsValid(binding, key) {
  if (binding.input.focusTransition) return true;
  for (const focusChain of key.focusChains) {
    if (await running.exit(() => Promise.all(focusChain.map(hasFocus)))
      .then(results => results.every(Boolean), () => false)) return true;
  }
  return false;
}

async function recoverInput(binding) {
  const input = binding.input;
  if (!input || input.recovered) return;
  input.recovered = true;
  const { keyboard, mouse } = binding.rawPage;
  const client = binding.rawPage.delegate._mainFrameSession._client;
  try {
    // A distinct async context grants only cancellation sends. Original native
    // sends still awaiting a guard are invalidated by input.recovered above.
    await running.run({ ...binding, recovering: true }, async () => {
      if (!binding.tab.page.isClosed()) {
        const drag = mouse._raw._dragManager;
        if (input.mouse && drag.isDragging()) await drag.cancelDrag();
        if (!sameDocuments(binding)) return;
        for (const button of input.buttons.keys()) {
          // Cancel the task-owned press outside the viewport, never release it
          // at the now-untrusted hit point. Zero click count cannot complete a
          // click. A native drag is cancelled above instead of being dropped.
          await client.send('Input.dispatchMouseEvent', {
            type: 'mouseReleased', x: -1, y: -1, button, buttons: 0,
            modifiers: 0, clickCount: 0,
          });
          input.point = { x: -1, y: -1 };
        }
        // Cleanup never releases a key into a different document or focus.
        for (const key of input.keys.values()) {
          const { params } = key;
          if (await keyReleaseFocusIsValid(binding, key)) {
            await client.send('Input.dispatchKeyEvent', {
              type: 'keyUp', modifiers: 0, key: params.key, code: params.code,
              windowsVirtualKeyCode: params.windowsVirtualKeyCode, location: params.location,
            });
          }
        }
      }
    });
  } finally {
    // Only the input families this action actually mutated belong to it. A
    // concurrent dialog response must not restore a pending action's keys.
    if (input.keyboard) {
      keyboard._pressedKeys = new Set(input.keyboard.keys);
      keyboard._pressedModifiers = new Set(input.keyboard.modifiers);
    }
    if (input.mouse) {
      mouse._buttons = new Set(input.mouse.buttons);
      mouse._lastButton = input.mouse.lastButton;
      mouse._x = input.point.x;
      mouse._y = input.point.y;
    }
    // A navigation discards the old document's drag; never retain a connector
    // drag object that would turn the next approved mouse-up into an old drop.
    if (input.mouse && (!sameDocuments(binding) || binding.tab.page.isClosed())) mouse._raw._dragManager._dragState = null;
  }
}

async function beforeRecoverySend(binding, method, params) {
  checkSend(method);
  if (method === 'Input.dispatchDragEvent' && params.type === 'dragCancel') return;
  if (method === 'Input.dispatchKeyEvent' && params.type === 'keyUp') {
    const key = binding.input.keys.get(params.code);
    if (!key || !await keyReleaseFocusIsValid(binding, key)) fail();
    return;
  }
  if (method === 'Input.dispatchMouseEvent' && params.type === 'mouseReleased'
      && params.x === -1 && params.y === -1 && params.clickCount === 0) {
    const pointer = binding.input.buttons.get(params.button);
    if (!pointer) fail();
    await running.exit(() => cancelPointerCapture(pointer));
    return;
  }
  fail();
}

async function withDocumentRoots(frame, callback) {
  // CDP pierces closed roots. Adopt into Playwright's isolated world so page
  // overrides of focus, capture, or DOM prototypes cannot forge these reads.
  const session = frame._page.delegate._sessionForFrame(frame);
  const utility = await frame.utilityContext();
  const document = await utility.evaluateHandle(() => document);
  const roots = [document];
  try {
    const { node } = await session._client.send('DOM.describeNode', {
      objectId: document._objectId, depth: -1, pierce: true,
    });
    const shadowRoots = [];
    const collect = node => {
      for (const shadow of node.shadowRoots ?? []) { shadowRoots.push(shadow); collect(shadow); }
      for (const child of node.children ?? []) collect(child);
    };
    collect(node);
    for (const shadow of shadowRoots)
      roots.push(await session._adoptBackendNodeId(shadow.backendNodeId, document._context));
    return await callback(document, roots);
  } finally {
    await Promise.all(roots.map(root => root.dispose()));
  }
}

async function cancelPointerCapture(pointer) {
  // Inspect the original pointer document and cancel only this mouse's capture.
  await withDocumentRoots(pointer._frame, (document, roots) => document.evaluate((document, roots) => {
    for (const root of roots)
      for (const element of root.querySelectorAll('*'))
        if (element.hasPointerCapture(1)) element.releasePointerCapture(1);
  }, roots));
}

async function history(binding) {
  return binding.rawPage.delegate._mainFrameSession._client.send('Page.getNavigationHistory');
}

async function validate(binding, selectors = true) {
  check(binding);
  if (binding.modal && !binding.tab.modalStates().includes(binding.modal)) fail();
  if (binding.chooser && !await binding.chooser.evaluate(node =>
    node.isConnected && node.ownerDocument === document)) fail();
  for (const target of binding.targets.values()) {
    if (!await target.handle.evaluate(node => node.isConnected && node.ownerDocument === document)) fail();
    if (selectors && !await target.locator.evaluate((node, original) => node === original, target.handle,
      { timeout: 1000 })) fail();
  }
  for (const focus of binding.focusChain ?? [])
    if (!await hasFocus(focus)) fail();
  if (binding.history && JSON.stringify(await history(binding)) !== binding.history) fail();
  await validateIntrinsic(binding);
  check(binding);
}

async function validateIntrinsic(binding, targets = binding.targets.values()) {
  for (const target of targets) {
    if (!await target.rawHandle.evaluateInUtility(([injected, node, control]) =>
      node.isConnected && injected.retarget(node, 'follow-label') === control, target.control)) fail();
    if (!await target.rawHandle.evaluateInUtility(([injected, node, pointer]) =>
      injected.retarget(node, 'button-link') === pointer, target.pointer)) fail();
    if (!await target.control.evaluate((node, host) => {
      if (!node.isContentEditable) return node === host;
      while (node.parentElement?.isContentEditable) node = node.parentElement;
      return node === host;
    }, target.editingHost)) fail();
    for (const [key, options] of target.options) {
      if (!await target.control.evaluate(optionTargets,
        { values: JSON.parse(key), expected: options })) fail();
    }
  }
}

// Read-only counterpart of the locked native selectOptions matching semantics;
// execution still uses native selectOptions, supplied with these exact nodes.
function optionTargets(select, { values, expected }) {
  const normalize = value => value.replace(/[\u200b\u00ad]/g, '').replace(/\s+/g, ' ').trim();
  let remaining = [...values];
  const selected = [];
  for (const option of select.options ?? []) {
    const matches = value => value.valueOrLabel !== undefined
      ? value.valueOrLabel === option.value || normalize(value.valueOrLabel) === normalize(option.label)
      : normalize(value.label) === normalize(option.label);
    if (!remaining.some(matches)) continue;
    selected.push(option);
    if (!select.multiple) { remaining = []; break; }
    remaining = remaining.filter(value => !matches(value));
  }
  if (remaining.length) throw new Error('Approved select option is unavailable');
  return expected ? expected.length === selected.length && selected.every((node, i) => node === expected[i]) : selected;
}

async function capture(backend, name, params, key) {
  const tab = await backend._context.ensureTab();
  const rawPage = impl(tab.page);
  if (!rawPage.delegate._mainFrameSession) throw new Error('Bound browser actions require pinned local Chromium');
  const binding = { backend, tab, rawPage, name, key, id: randomUUID(), nativePending: 0,
    documents: new Map(), targets: new Map(), handles: [] };
  backend._oraTarget = binding;
  const rememberFrame = frame => binding.documents.set(frame, frame._currentDocument);
  rememberFrame(rawPage.mainFrame());
  const targetParams = name === 'browser_drag'
    ? [{ target: params.startTarget }, { target: params.endTarget }]
    : name === 'browser_fill_form' ? params.fields
    : params.target ? [params] : [];
  for (const item of targetParams) {
    const direct = name === 'browser_type' || name === 'browser_select_option'
      || (name === 'browser_fill_form' && ['textbox', 'slider', 'combobox'].includes(item.type));
    const nativeFill = (name === 'browser_type' && !params.slowly)
      || (name === 'browser_fill_form' && ['textbox', 'slider'].includes(item.type));
    const existing = binding.targets.get(item.target);
    if (existing) {
      // The form handler executes every field in order. A later occurrence of
      // the same selector must not lose stronger target/fill requirements just
      // because an earlier field used a weaker operation such as setChecked.
      existing.direct ||= direct;
      existing.nativeFill ||= nativeFill;
      continue;
    }
    const resolved = await tab.targetLocator(item);
    if (await resolved.locator.count() !== 1) fail();
    const handle = await resolved.locator.elementHandle({ timeout: 1000 });
    if (!handle) fail();
    binding.handles.push(handle);
    const rawHandle = impl(handle);
    rememberFrame(rawHandle._frame);
    const control = await rawHandle._evaluateHandleInUtility(
      ([injected, node]) => injected.retarget(node, 'follow-label'), {});
    if (!control?.asElement?.()) fail();
    binding.handles.push(control);
    const pointer = await rawHandle._evaluateHandleInUtility(
      ([injected, node]) => injected.retarget(node, 'button-link'), {});
    if (!pointer?.asElement?.()) fail();
    binding.handles.push(pointer);
    const host = await control.evaluateHandle(editingHost);
    binding.handles.push(host);
    const sameReceiver = await pointer.evaluate((node, receiver) => node === receiver, host);
    const focusChain = [host];
    const target = { ...resolved, handle, rawHandle, control, options: new Map(),
      pointer, editingHost: host, focusChain,
      receiverFocusChain: sameReceiver ? focusChain : [pointer],
      contentEditable: await control.evaluate(node => node.isContentEditable),
      direct, nativeFill,
      // Frame actions receive the original locator selector, not the generated
      // display-code selector returned by normalize().
      actionSelector: resolved.locator._selector, actionFrame: impl(resolved.locator._frame) };
    // Keyboard sends address the whole Page, so authenticate the input's full
    // receiving focus chain, including every iframe owner.
    for (let frame = rawHandle._frame; frame.parentFrame(); frame = frame.parentFrame()) {
      const owner = await rawPage.delegate.getFrameElement(frame);
      binding.handles.push(owner);
      target.focusChain.push(owner);
      if (target.receiverFocusChain !== target.focusChain) target.receiverFocusChain.push(owner);
      rememberFrame(frame.parentFrame());
    }
    binding.targets.set(item.target, target);
  }
  for (const item of targetParams) {
    const values = name === 'browser_select_option' ? params.values.map(valueOrLabel => ({ valueOrLabel }))
      : name === 'browser_fill_form' && item.type === 'combobox' ? [{ label: item.value }] : undefined;
    if (!values) continue;
    const target = binding.targets.get(item.target);
    const options = [];
    target.options.set(JSON.stringify(values), options);
    const selected = await target.control.evaluateHandle(optionTargets, { values });
    binding.handles.push(selected);
    for (let index = 0, count = await selected.evaluate(nodes => nodes.length); index < count; index++) {
      const option = await selected.evaluateHandle((nodes, index) => nodes[index], index);
      binding.handles.push(option);
      if (!option.asElement()) fail();
      options.push(option);
    }
  }
  if (name === 'browser_press_key' || (name === 'browser_click' && params.modifiers?.length)) {
    binding.focusChain = [];
    let frame = rawPage.mainFrame();
    while (true) {
      const focus = await withDocumentRoots(frame, (document, roots) => document.evaluateHandle((document, roots) => {
        let node = document.activeElement;
        while (node) {
          const next = roots.find(root => root.host === node)?.activeElement;
          if (!next) break;
          node = next;
        }
        return node;
      }, roots));
      if (!focus.asElement()) { await focus.dispose(); fail(); }
      binding.handles.push(focus);
      binding.focusChain.push(focus);
      rememberFrame(frame);
      const child = await focus._contentFrame();
      if (!child) { binding.focus = focus; break; }
      frame = child;
    }
  }
  if (name === 'browser_handle_dialog' || name === 'browser_file_upload') {
    const type = name === 'browser_handle_dialog' ? 'dialog' : 'fileChooser';
    binding.modal = tab.modalStates().find(state => state.type === type);
    if (!binding.modal) fail();
    if (type === 'fileChooser' && params.paths?.length) {
      binding.chooser = binding.modal.fileChooser.element();
      // The chooser owns this handle; disposal belongs to Playwright.
      rememberFrame(impl(binding.chooser)._frame);
    }
  }
  if (name === 'browser_navigate_back') {
    const current = await history(binding);
    binding.history = JSON.stringify(current);
    binding.backEntry = current.entries[current.currentIndex - 1]?.id;
  }
  await validate(binding);
  return binding;
}

async function control(backend, name, params, control) {
  if (!['prepare', 'validate'].includes(control?.phase)) fail();
  const key = JSON.stringify([name, params]);
  let binding = backend._oraTarget;
  if (control.phase === 'validate') {
    if (!binding || binding.key !== key || binding.id !== control.id) fail();
    await validate(binding);
  } else {
    if (binding?.key === key) {
      try { await validate(binding); }
      catch { await dispose(backend); binding = undefined; }
    } else {
      await dispose(backend);
      binding = undefined;
    }
    if (!binding) {
      try { binding = await capture(backend, name, params, key); }
      catch (error) { await dispose(backend); throw error; }
    }
  }
  return { content: [], structuredContent: { oraBrowserBinding: {
    id: binding.id, page: binding.tab.page._guid, url: binding.tab.page.url(),
  } } };
}

function boundTab(context) {
  const binding = active();
  if (!binding) return;
  if (binding.backend._context !== context) fail();
  check(binding);
  return binding.tab;
}

async function withTarget(frame, progress, selector, options, action) {
  const binding = active();
  check(binding);
  const target = [...binding.targets.values()].find(item => item.actionSelector === selector);
  if (!target || target.actionFrame !== frame) fail();
  if ((options.performActionPreChecks ?? !options.force) && !options.noAutoWaiting)
    await frame._page.performActionPreChecks(progress);
  check(binding);
  binding.inputTarget = target.direct ? target : undefined;
  binding.pointerTarget = target;
  try {
    // An editable descendant need not itself be focusable. Use the captured
    // native editing host for focus; native fill still selects only the child.
    if (target.direct && target.contentEditable) await target.editingHost._focus(progress);
    const result = await action(progress, target.direct ? target.control : target.rawHandle);
    if (result === 'error:notconnected') fail();
    return result;
  } finally {
    binding.inputTarget = undefined;
    binding.pointerTarget = undefined;
    binding.pointerPoint = undefined;
  }
}

function focusTarget(handle) {
  const target = active()?.inputTarget;
  return target?.control === handle ? target.editingHost : undefined;
}

function optionsFor(handle, values) {
  if (!active()) return;
  const target = [...active().targets.values()].find(target => target.control === handle);
  const options = target?.options.get(JSON.stringify(values));
  if (!options) fail();
  return options;
}

function pointerPoint(handle, point) {
  const binding = active();
  if (!binding) return;
  if (![binding.pointerTarget?.rawHandle, binding.pointerTarget?.control].includes(handle)) fail();
  // DOM.getNodeForLocation accepts integral CSS coordinates. Choose the same
  // point before native instrumentation/hit testing and native input delivery.
  point.x = Math.round(point.x);
  point.y = Math.round(point.y);
  binding.pointerPoint = point;
}

async function validatePointer(binding, params) {
  const target = binding.pointerTarget;
  if (!target) fail();
  // Chromium returns the actual hit frame and node, including transformed
  // iframe geometry. Resolve only in that reviewed frame, never a substitute.
  const frame = target.rawHandle._frame;
  if (!Number.isInteger(params.x) || !Number.isInteger(params.y)) fail();
  const hit = await binding.rawPage.delegate._mainFrameSession._client.send('DOM.getNodeForLocation', {
    x: params.x, y: params.y, includeUserAgentShadowDOM: false,
  });
  if (hit.frameId !== frame._id) fail();
  const receiver = await binding.rawPage.delegate._sessionForFrame(frame)._adoptBackendNodeId(
    hit.backendNodeId, await frame.utilityContext());
  try {
    if (!await target.pointer.evaluate((node, hit) => {
      for (let current = hit; current; current = current.assignedSlot || current.parentElement || current.getRootNode().host)
        if (current === node) return node.isConnected;
      return false;
    }, receiver)) fail();
  } finally {
    await receiver.dispose();
  }
}

async function validatePointerCapture(binding) {
  const target = binding.pointerTarget;
  if (!target) fail();
  const approvedPointers = [target.pointer, ...binding.input.buttons.values()];
  // Capture overrides coordinate hit testing, including pending capture set
  // by pointerdown. During drag, the active endpoint changes from source to
  // destination, but native capture may legitimately remain on the reviewed
  // source. Check every bound frame and refuse capture by any third node.
  for (const frame of binding.documents.keys()) {
    const pointers = approvedPointers.filter(pointer => pointer?._frame === frame);
    if (!await withDocumentRoots(frame, (document, roots) => document.evaluate((document, { roots, pointers }) => {
      for (const root of roots) {
        for (const element of root.querySelectorAll('*')) {
          if (!element.hasPointerCapture(1)) continue;
          const approved = pointers.some(pointer => {
            let current = element;
            while (current && current !== pointer)
              current = current.assignedSlot || current.parentElement || current.getRootNode().host;
            return current === pointer && pointer.isConnected;
          });
          if (!approved) return false;
        }
      }
      return true;
    }, { roots, pointers }))) fail();
  }
}

// Guard inside the pinned Chromium session, after native actionability awaits
// and retries. This is the final connector send, not browser-delivery atomicity.
async function beforeSend(session, method, params) {
  const binding = active();
  if (!binding || !effectSend(method)) return;
  if (binding.recovering) return beforeRecoverySend(binding, method, params);
  check(binding);
  if (binding.modal && binding.tab.modalStates().some(state =>
    state.type === binding.modal.type && state !== binding.modal)) fail();
  // Full preflight binds every field. During native execution authenticate the
  // active field only: completed edits may legitimately remove their own node.
  // Native keydown may itself remove the editable node. Its keyup still owns
  // the same Page/document, just as Tab/Enter may intentionally move focus.
  if (!(method === 'Input.dispatchKeyEvent' && params.type === 'keyUp'))
    await running.exit(() => validateIntrinsic(binding, binding.pointerTarget ? [binding.pointerTarget] : []));
  if (/^Input\.(dispatchMouseEvent|dispatchDragEvent)$/.test(method)
      && params.type !== 'dragCancel') {
    // Drag interpolation traverses unreviewed space by design. Authenticate
    // the reviewed endpoints, every press/release, and the hover destination.
    const movement = ['mouseMoved', 'dragEnter', 'dragOver'].includes(params.type);
    const atEndpoint = binding.pointerPoint
      && Math.abs(params.x - binding.pointerPoint.x) < 1e-7
      && Math.abs(params.y - binding.pointerPoint.y) < 1e-7;
    if (!movement || binding.name !== 'browser_drag' || atEndpoint)
      await running.exit(() => validatePointer(binding, params));
    if (method === 'Input.dispatchMouseEvent')
      await running.exit(() => validatePointerCapture(binding));
  }
  if (binding.inputTarget && /^Input\.(dispatchKeyEvent|insertText)$/.test(method)
      && params.type !== 'keyUp') {
    for (const focus of binding.inputTarget.focusChain)
      if (!await running.exit(() => hasFocus(focus))) fail();
    const fullTarget = binding.inputTarget.nativeFill && (method === 'Input.insertText'
      || (method === 'Input.dispatchKeyEvent' && params.key === 'Delete'));
    if (!await running.exit(() => binding.inputTarget.control.evaluate(selectionWithin, fullTarget))) fail();
  }
  // Native keyboard.press may intentionally move focus (Tab, Enter). Validate
  // every keydown (including modifiers); keyup still checks Page/documents.
  if (binding.focus && method === 'Input.dispatchKeyEvent' && params.type !== 'keyUp') {
    await running.exit(() => validate(binding, false));
  }
  if (method === 'Input.dispatchKeyEvent' && params.type === 'keyUp') {
    const key = binding.input.keys.get(params.code);
    if (!key || !await keyReleaseFocusIsValid(binding, key)) fail();
  }
  if (method === 'Page.navigateToHistoryEntry') {
    if (params.entryId !== binding.backEntry) fail();
    if (JSON.stringify(await running.exit(() => history(binding))) !== binding.history) fail();
  }
  if (binding.chooser && method === 'DOM.setFileInputFiles') {
    if (!await running.exit(() => binding.chooser.evaluate(node => node.isConnected && node.ownerDocument === document))) fail();
  }
  check(binding);
}

async function run(backend, name, params, control, callback) {
  if (!supports(name)) return callback();
  const binding = backend._oraTarget;
  if (!binding || control?.phase !== 'execute' || binding.id !== control.id
      || binding.key !== JSON.stringify([name, params])) fail();
  await validate(binding);
  binding.input = { keys: new Map(), buttons: new Map() };
  try { return await running.run(binding, callback); }
  catch (error) { if (!binding.nativePending) await recoverInput(binding); throw error; }
  finally { await dispose(backend); }
}

module.exports = { supports, active, dispose, control, boundTab, withTarget, focusTarget, optionsFor, pointerPoint, beforeSend, checkSend, inputState, sent, nativeCompletion, run };
