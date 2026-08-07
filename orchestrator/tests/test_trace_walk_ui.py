"""jsdom coverage for the Chunk 2 Trace Walk browser affordances."""
from __future__ import annotations

import subprocess
import textwrap
import unittest
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
JSDOM_MODULE_DIRS = [
    ROOT / "server/static/ora-visual-compiler/tests/node_modules",
    Path("/Users/oracle/ora/server/static/ora-visual-compiler/tests/node_modules"),
    Path.home() / ".hermes/hermes-agent/node_modules",
]


def _node_env() -> dict[str, str]:
    env = os.environ.copy()
    module_dirs = [str(p) for p in JSDOM_MODULE_DIRS if p.exists()]
    if module_dirs:
        existing = env.get("NODE_PATH")
        env["NODE_PATH"] = os.pathsep.join(module_dirs + ([existing] if existing else []))
    return env


class TraceWalkUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        probe = subprocess.run(
            ["node", "-e", "require('jsdom')"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_node_env(),
        )
        if probe.returncode != 0:
            raise unittest.SkipTest("jsdom is not installed")

    def run_node(self, script: str) -> None:
        result = subprocess.run(
            ["node", "-e", script],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_node_env(),
        )
        if result.returncode != 0:
            self.fail(result.stdout + result.stderr)

    def test_trace_walk_modal_races_controls_and_escaping(self):
        self.run_node(textwrap.dedent(r"""
            const assert = require('assert');
            const fs = require('fs');
            const path = require('path');
            const vm = require('vm');
            const { JSDOM } = require('jsdom');

            const ROOT = process.cwd();
            const dom = new JSDOM('<!doctype html><html><head></head><body><button id="launch">Launch</button></body></html>', {
              url: 'http://ora.test',
              pretendToBeVisual: true,
            });
            const window = dom.window;
            window.console = console;
            window.Response = Response;
            window.Headers = Headers;
            window.Blob = Blob;
            window.URL.createObjectURL = () => 'blob:trace';
            window.URL.revokeObjectURL = () => {};
            window.HTMLAnchorElement.prototype.click = function () { window.__downloaded = this.download; };
            window.prompt = () => 'looked wrong';
            const privacyCalls = [];
            window.OraConversation = {
              getActiveConversationId: () => 'conv-d',
              submitChatTurn: async (body, options) => {
                privacyCalls.push({ stage: 'privacy', body, options });
                const response = await window.fetch('/chat', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify(body),
                });
                if (!response.ok) {
                  const error = await response.json();
                  throw new Error(error.error || error.message || 'Chat failed');
                }
                return body.conversation_id;
              },
            };

            const pending = [];
            const deferred = () => {
              let resolve, reject;
              const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
              return { promise, resolve, reject };
            };
            const jsonResponse = (body, status = 200, headers = {}) => new Response(
              JSON.stringify(body),
              { status, headers: Object.assign({ 'Content-Type': 'application/json' }, headers) }
            );
            window.fetch = (input, opts = {}) => {
              const d = deferred();
              pending.push({ url: String(input), opts, d });
              return d.promise;
            };

            vm.runInContext(
              fs.readFileSync(path.join(ROOT, 'server/static/js/trace-walk.js'), 'utf8'),
              vm.createContext(window),
              { filename: 'trace-walk.js' }
            );
            const flush = () => new Promise((resolve) => setTimeout(resolve, 0));
            const manifest = (ref, status = 'completed') => ({
              trace_ref: ref,
              trace_kind: 'chat',
              terminal_status: status,
              gear: 3,
              mode: 'mode-a',
              retention_state: 'default',
              redaction_level: 'default',
              parent_trace_ref: null,
              child_trace_refs: [],
              missing_steps: [],
              steps: [{ step_name: 'step1-phase-a', label: 'Prompt', expected: true, actual: true }],
            });

            (async () => {
              const launch = window.document.getElementById('launch');
              launch.focus();
              window.OraTraceWalk.open({ trace_ref: 'bad-ref' });
              await flush();
              assert(window.document.querySelector('[data-role="export"]').disabled, 'invalid ref keeps export disabled');
              assert(window.document.querySelector('[data-role="pin"]').disabled, 'invalid ref keeps pin disabled');

              window.OraTraceWalk.open({ trace_ref: 'conv-a/turn-a' });
              const reqA = pending.pop();
              window.OraTraceWalk.open({ trace_ref: 'conv-b/turn-b' });
              const reqB = pending.pop();
              reqA.d.resolve(jsonResponse(manifest('conv-a/turn-a')));
              await flush();
              assert(!window.document.body.textContent.includes('conv-a/turn-a'), 'stale manifest ignored');
              reqB.d.resolve(jsonResponse(manifest('conv-b/turn-b')));
              await flush();
              assert(window.document.body.textContent.includes('conv-b/turn-b'), 'current manifest rendered');
              assert(!window.document.querySelector('[data-role="export"]').disabled, 'loaded trace enables export');

              window.document.querySelector('.ora-trace-step').click();
              const stepReq = pending.pop();
              window.OraTraceWalk.open({ trace_ref: 'conv-c/turn-c' });
              const reqC = pending.pop();
              stepReq.d.resolve(jsonResponse({
                step_name: 'step1-phase-a',
                label: 'Prompt',
                markdown: '<script>alert(1)</script>\n[bad](https://x)\n![img](x)',
                payload: { stale: true },
                errors: [],
              }));
              reqC.d.resolve(jsonResponse(manifest('conv-c/turn-c')));
              await flush();
              assert(!window.document.body.textContent.includes('stale'), 'stale step ignored');

              window.document.querySelector('.ora-trace-step').click();
              const currentStep = pending.pop();
              currentStep.d.resolve(jsonResponse({
                step_name: 'step1-phase-a',
                label: 'Prompt',
                markdown: '<script>alert(1)</script>\n[bad](https://x)\n![img](x)',
                markdown_summary: { characters: 49, sha256: 'safe-digest' },
                payload: { safe: true },
                errors: [],
              }));
              await flush();
              const detail = window.document.querySelector('.ora-trace-detail');
              assert(!detail.textContent.includes('alert(1)'), 'raw markdown ignored');
              assert(detail.textContent.includes('Markdown content redacted'), 'redaction is visible');
              assert(detail.textContent.includes('"safe": true'), 'safe projection rendered');
              assert(!detail.querySelector('script'), 'no script tag emitted');
              assert(!detail.querySelector('a'), 'markdown links not transformed');
              assert(!detail.querySelector('img'), 'markdown images not transformed');

              window.document.querySelector('[data-role="pin"]').click();
              const pinReq = pending.pop();
              window.OraTraceWalk.open({ trace_ref: 'conv-d/turn-d' });
              const reqD = pending.pop();
              pinReq.d.resolve(jsonResponse({ ok: true, trace_ref: 'conv-c/turn-c', retention_state: 'pinned' }));
              reqD.d.resolve(jsonResponse(manifest('conv-d/turn-d')));
              await flush();
              assert(window.document.body.textContent.includes('conv-d/turn-d'), 'new trace remains active after stale pin');
              assert(!window.document.body.textContent.includes('"retention_state": "pinned"'), 'stale pin ignored');

              window.document.querySelector('[data-role="export"]').click();
              const exportReq = pending.pop();
              const beforeHref = window.location.href;
              exportReq.d.resolve(jsonResponse({ error: 'gone' }, 404));
              await flush();
              assert.strictEqual(window.location.href, beforeHref, 'failed export does not navigate page');
              assert(window.document.querySelector('[data-role="status"]').textContent.includes('gone'), 'export failure is visible');

              const investigate = window.document.querySelector('[data-role="investigate"]');
              assert(investigate && !investigate.disabled, 'loaded trace enables investigate');
              investigate.click();
              const invReq = pending.pop();
              const invBody = JSON.parse(invReq.opts.body);
              assert.strictEqual(privacyCalls.length, 1);
              assert.strictEqual(privacyCalls[0].options.privacyText, 'looked wrong');
              assert.strictEqual(invReq.url, '/chat');
              assert.strictEqual(invBody.panel_id, 'conv-d');
              assert.strictEqual(invBody.trace_debug.trace_ref, 'conv-d/turn-d');
              assert.strictEqual(invBody.trace_debug.step_hint, '');
              assert.strictEqual(invBody.trace_debug.symptom, 'looked wrong');
              invReq.d.resolve(jsonResponse({ ok: true }));
              await flush();
              assert(window.document.querySelector('[data-role="status"]').textContent.includes('submitted'), 'successful investigation is visible');

              investigate.click();
              const invFailReq = pending.pop();
              invFailReq.d.resolve(jsonResponse({ error: 'trace expired' }, 404));
              await flush();
              assert(window.document.querySelector('[data-role="status"]').textContent.includes('trace expired'), 'failed investigation is visible');

              window.OraTraceWalk.close();
              assert.strictEqual(window.document.activeElement, launch, 'focus restored on close');
            })().catch((err) => {
              console.error(err && err.stack || err);
              process.exit(1);
            });
        """))

    def test_toolbar_current_turn_sync_and_paused_exact_trace_links(self):
        self.run_node(textwrap.dedent(r"""
            const assert = require('assert');
            const fs = require('fs');
            const path = require('path');
            const vm = require('vm');
            const { JSDOM } = require('jsdom');

            const ROOT = process.cwd();
            const dom = new JSDOM('<!doctype html><html><head></head><body><div class="output-pane"></div></body></html>', {
              url: 'http://ora.test',
              pretendToBeVisual: true,
            });
            const window = dom.window;
            window.console = console;
            window.Response = Response;
            let opened = null;
            let currentTurn = null;
            const chatSubmissions = [];
            window.OraConversation = {
              getCurrentTurn: () => currentTurn,
              getActiveConversationId: () => 'conv-live',
              submitChatTurn: (body, options) => {
                chatSubmissions.push({ body, options });
                return Promise.resolve(body.conversation_id);
              },
            };
            window.OraTraceWalk = { open: (opts) => { opened = opts; } };
            window.fetch = (input) => {
              const url = String(input);
              if (url === '/api/export/locations') {
                return Promise.resolve(new Response(JSON.stringify({ capabilities: {} }), { status: 200 }));
              }
              if (url === '/api/oversight/paused') {
                return Promise.resolve(new Response(JSON.stringify({ entries: [{
                  id: 'pause-1',
                  name: 'Gate',
                  reasoning_excerpt: 'safe',
                  trace_ref: 'conv-paused/turn-paused',
                  trace_step: 'step4-tools',
                  engagement: 'unseen',
                  discussion_conversation_id: 'conv-paused',
                }] }), { status: 200 }));
              }
              if (url === '/api/oversight/operating') {
                return Promise.resolve(new Response(JSON.stringify({ entries: [] }), { status: 200 }));
              }
              if (url.includes('/engagement')) {
                return Promise.resolve(new Response('{}', { status: 200 }));
              }
              if (url === '/chat') {
                return Promise.resolve(new Response('{}', { status: 200 }));
              }
              throw new Error('unexpected fetch ' + url);
            };
            const run = (rel) => vm.runInContext(
              fs.readFileSync(path.join(ROOT, rel), 'utf8'),
              vm.createContext(window),
              { filename: rel }
            );
            const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

            (async () => {
              run('server/static/js/export-toolbar.js');
              window.document.dispatchEvent(new window.Event('DOMContentLoaded'));
              await flush();
              const traceBtn = window.document.getElementById('traceWalkBtn');
              assert(traceBtn.disabled, 'trace button starts disabled');
              currentTurn = { assistant: { trace_ref: 'conv-current/turn-current' } };
              window.document.dispatchEvent(new window.CustomEvent('ora:current-turn-changed'));
              assert(!traceBtn.disabled, 'current-turn change enables trace button');
              traceBtn.click();
              assert.strictEqual(opened.trace_ref, 'conv-current/turn-current');
              currentTurn = { assistant: {} };
              window.document.dispatchEvent(new window.CustomEvent('ora:current-turn-changed'));
              assert(traceBtn.disabled, 'current-turn change disables trace button when ref disappears');

              run('server/static/js/review-queue-panel.js');
              await window.OraReviewQueuePanel.open({ tab: 'paused' });
              await flush();
              const buttons = Array.from(window.document.querySelectorAll('button'));
              const openTrace = buttons.find((btn) => btn.textContent === 'Open trace');
              assert(openTrace, 'paused entry renders Open trace');
              openTrace.click();
              assert.strictEqual(opened.trace_ref, 'conv-paused/turn-paused');
              assert.strictEqual(opened.step, 'step4-tools');
              const investigate = buttons.find((btn) => btn.textContent === 'Investigate trace');
              assert(investigate, 'paused entry renders Investigate trace');
              investigate.click();
              await flush();
              assert.strictEqual(chatSubmissions[0].body.message, 'Investigate this trace.');
              assert.strictEqual(chatSubmissions[0].options.privacyText, undefined);

              window.prompt = () => 'My bank account details were exposed.';
              const deny = buttons.find((btn) => btn.textContent === 'Deny');
              deny.click();
              await flush();
              await flush();
              assert.strictEqual(chatSubmissions[1].body.message, 'My bank account details were exposed.');
              assert.strictEqual(chatSubmissions[1].options.privacyText, 'My bank account details were exposed.');
              assert.strictEqual(chatSubmissions[2].body.message, '2');
              assert.strictEqual(chatSubmissions[2].options.privacyText, undefined);
              process.exit(0);
            })().catch((err) => {
              console.error(err && err.stack || err);
              process.exit(1);
            });
        """))


if __name__ == "__main__":
    unittest.main()
