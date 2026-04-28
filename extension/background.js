/*
 * Ora Browser Bridge — Background Service Worker
 *
 * Polls the Ora server for evaluation requests and handles them in
 * authenticated browser tabs. Uses setTimeout chaining (not while loops)
 * because Chrome Manifest V3 service workers are event-driven.
 */

const ORA_SERVER = 'http://localhost:5000';
const POLL_INTERVAL_MS = 2000;
const RESPONSE_POLL_MS = 2000;
const STABLE_POLLS_NEEDED = 3;
const MAX_RESPONSE_POLLS = 90; // 3 min max

let evaluating = false;
let pollTimer = null;

// ── Service-specific strategies ────────────────────────────────────────────

const STRATEGIES = {
  claude: {
    inputType: 'prosemirror',
    sendSelector: 'button[aria-label="Send Message"], button[data-testid="send-button"]',
    streamingSelector: '[data-is-streaming="true"]',
  },
  chatgpt: {
    inputType: 'prosemirror',
    sendSelector: 'button[data-testid="send-button"], button[aria-label="Send prompt"]',
    streamingSelector: '.result-streaming',
  },
  gemini: {
    inputType: 'quill',
    sendSelector: 'button[aria-label="Send message"], button.send',
    streamingSelector: null,
  },
};

const DEFAULT_STRATEGY = {
  inputType: 'textarea',
  sendSelector: 'button[type="submit"], button[aria-label*="send" i]',
  streamingSelector: null,
};


// ── Poll Loop (setTimeout chain) ───────────────────────────────────────────

function schedulePoll() {
  // Prevent duplicate chains
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = setTimeout(doPoll, POLL_INTERVAL_MS);
}

async function doPoll() {
  pollTimer = null;

  if (evaluating) {
    schedulePoll();
    return;
  }

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);

    const resp = await fetch(`${ORA_SERVER}/api/extension/pending`, {
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!resp.ok) {
      console.log('[ora] Server returned', resp.status);
      updateBadge('error');
      schedulePoll();
      return;
    }

    updateBadge('connected');
    const data = await resp.json();

    if (data.request) {
      console.log('[ora] Got evaluation request:', data.request.service);
      evaluating = true;
      try {
        await handleEvaluation(data.request);
      } finally {
        evaluating = false;
      }
    }
  } catch (e) {
    // Server not running — keep trying silently
    updateBadge('disconnected');
  }

  schedulePoll();
}


// ── Evaluation ─────────────────────────────────────────────────────────────

async function handleEvaluation(request) {
  const { id, service, prompt, config } = request;
  const strategy = STRATEGIES[service] || DEFAULT_STRATEGY;
  let tab = null;

  try {
    updateBadge('working');

    tab = await chrome.tabs.create({ url: config.url, active: false });
    await waitForTabLoad(tab.id, 30000);
    await sleep(3000); // SPA hydration

    // Count existing responses
    const baseline = await runInTab(tab.id, countResponses, [config.response_selector]);
    const baselineCount = baseline || 0;

    // Type prompt
    await runInTab(tab.id, typePrompt, [prompt, config.input_selector, strategy.inputType]);
    await sleep(500);

    // Submit
    await runInTab(tab.id, clickSend, [config.input_selector, strategy.sendSelector]);

    // Poll for response
    const text = await waitForResponse(tab.id, config.response_selector, strategy.streamingSelector, baselineCount);
    await postResult(id, text);
    console.log(`[ora] Done (${service}): ${text.length} chars`);

  } catch (e) {
    console.error(`[ora] Error (${service}):`, e);
    await postResult(id, null, e.message);
  } finally {
    if (tab) try { await chrome.tabs.remove(tab.id); } catch (e) {}
    updateBadge('connected');
  }
}

async function runInTab(tabId, func, args) {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    world: 'MAIN',
    func,
    args,
  });
  return results[0]?.result;
}


// ── Page-injected functions ────────────────────────────────────────────────
// Run inside the AI service page. No closures — all data via args.

function countResponses(responseSelector) {
  for (const sel of responseSelector.split(',')) {
    const els = document.querySelectorAll(sel.trim());
    if (els.length > 0) return els.length;
  }
  return 0;
}

function typePrompt(prompt, inputSelector, inputType) {
  let input = null;
  for (const sel of inputSelector.split(',')) {
    input = document.querySelector(sel.trim());
    if (input) break;
  }
  if (!input) throw new Error('Input not found: ' + inputSelector);

  input.focus();
  input.click();

  if (inputType === 'prosemirror') {
    // ProseMirror (Claude, ChatGPT): innerHTML + InputEvent triggers React state
    const escaped = prompt.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    input.innerHTML = `<p>${escaped}</p>`;
    input.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: prompt }));
  } else if (inputType === 'quill') {
    // Quill (Gemini): use Quill API via __quill on the container
    const container = input.closest('.ql-container') || input.closest('rich-textarea');
    if (container?.__quill) {
      container.__quill.setText(prompt);
    } else {
      input.textContent = prompt;
      input.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: prompt }));
    }
  } else {
    // textarea fallback
    const setter =
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set ||
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
    if (setter) setter.call(input, prompt);
    else input.value = prompt;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }
  return true;
}

function clickSend(inputSelector, sendSelector) {
  if (sendSelector) {
    for (const sel of sendSelector.split(',')) {
      try {
        const btn = document.querySelector(sel.trim());
        if (btn && !btn.disabled) { btn.click(); return 'button'; }
      } catch (e) {}
    }
  }
  // Fallback: Enter key
  let input = null;
  for (const sel of inputSelector.split(',')) {
    input = document.querySelector(sel.trim());
    if (input) break;
  }
  if (input) {
    input.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
      bubbles: true, cancelable: true,
    }));
  }
  return 'enter';
}

function readResponse(responseSelector, streamingSelector, baselineCount) {
  let streaming = false;
  if (streamingSelector) streaming = !!document.querySelector(streamingSelector);

  let elements = [];
  for (const sel of responseSelector.split(',')) {
    elements = [...document.querySelectorAll(sel.trim())];
    if (elements.length > 0) break;
  }

  const newEls = elements.slice(baselineCount);
  const last = newEls[newEls.length - 1];
  return { text: last ? last.innerText.trim() : '', streaming, count: elements.length };
}


// ── Response polling ───────────────────────────────────────────────────────

async function waitForResponse(tabId, responseSelector, streamingSelector, baselineCount) {
  let lastText = '';
  let stableCount = 0;

  for (let i = 0; i < MAX_RESPONSE_POLLS; i++) {
    await sleep(RESPONSE_POLL_MS);
    let result;
    try {
      result = await runInTab(tabId, readResponse, [responseSelector, streamingSelector, baselineCount]);
    } catch (e) { continue; }

    if (!result) continue;
    if (result.streaming) { stableCount = 0; lastText = result.text || ''; continue; }

    if (result.text && result.text.length > 0) {
      if (result.text === lastText) {
        stableCount++;
        if (stableCount >= STABLE_POLLS_NEEDED) return result.text;
      } else {
        stableCount = 0;
        lastText = result.text;
      }
    }
  }

  if (lastText) return lastText;
  throw new Error('No response within timeout');
}


// ── Utility ────────────────────────────────────────────────────────────────

function waitForTabLoad(tabId, timeoutMs) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error('Tab load timeout'));
    }, timeoutMs);

    function listener(id, info) {
      if (id === tabId && info.status === 'complete') {
        chrome.tabs.onUpdated.removeListener(listener);
        clearTimeout(timer);
        resolve();
      }
    }
    chrome.tabs.onUpdated.addListener(listener);
    chrome.tabs.get(tabId, (tab) => {
      if (tab?.status === 'complete') {
        chrome.tabs.onUpdated.removeListener(listener);
        clearTimeout(timer);
        resolve();
      }
    });
  });
}

function sleep(ms) {
  // Manifest V3 kills workers after ~30s of no Chrome API calls.
  // Ping chrome.runtime periodically during sleeps to stay alive.
  return new Promise(resolve => {
    const end = Date.now() + ms;
    function tick() {
      chrome.runtime.getPlatformInfo(() => {});
      if (Date.now() >= end) return resolve();
      setTimeout(tick, Math.min(5000, end - Date.now()));
    }
    tick();
  });
}

async function postResult(id, response, error = null) {
  try {
    await fetch(`${ORA_SERVER}/api/extension/result`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, response, error }),
    });
  } catch (e) { console.error('[ora] Post result failed:', e); }
}

function updateBadge(status) {
  const c = { connected: '#4CAF50', disconnected: '#9E9E9E', working: '#FF9800', error: '#F44336' };
  const t = { connected: 'ON', disconnected: '', working: '...', error: 'ERR' };
  chrome.action.setBadgeBackgroundColor({ color: c[status] || '#9E9E9E' });
  chrome.action.setBadgeText({ text: t[status] || '' });
}


// ── Lifecycle ──────────────────────────────────────────────────────────────

// Start polling immediately on worker load
console.log('[ora] Service worker started — beginning poll loop');
schedulePoll();

// Alarm wakes the worker if Chrome terminated it between polls
chrome.alarms.create('ora-restart', { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'ora-restart' && !pollTimer) {
    console.log('[ora] Alarm woke service worker — restarting poll');
    schedulePoll();
  }
});

// Messages from popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'getStatus') {
    sendResponse({ connected: !!pollTimer || evaluating });
    return true;
  }
  if (msg.type === 'reconnect') {
    console.log('[ora] Manual reconnect requested');
    schedulePoll();
    sendResponse({ ok: true });
    return true;
  }
});
