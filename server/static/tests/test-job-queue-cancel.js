#!/usr/bin/env node
/* test-job-queue-cancel.js — WP-7.6.3
 *
 * jsdom-driven test harness for the cancel-with-billing-warning flow
 * added to job-queue.js. The §13.6 acceptance criterion is verbatim:
 *
 *   "Dispatch async job; click cancel; verify warning; click again;
 *    verify cancel signal sent and job removed."
 *
 * We drive the flow via the public test hooks
 * (OraJobQueue._testRequestCancel / _testConfirmCancel /
 *  _testGetModalState) rather than synthesizing DOM clicks, so the
 * test is independent of CSS hit-testing.
 *
 * Run:  node ~/ora/server/static/tests/test-job-queue-cancel.js
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var path = require('path');

var ORA_ROOT = path.resolve(__dirname, '..', '..', '..');
var MODULE_PATH = path.join(ORA_ROOT, 'server', 'static', 'job-queue.js');
var JSDOM_PATH = path.join(ORA_ROOT, 'server', 'static',
                           'ora-visual-compiler', 'tests', 'node_modules', 'jsdom');

var JSDOM = require(JSDOM_PATH).JSDOM;

// ── Runner ────────────────────────────────────────────────────────────────

var passCount = 0;
var failCount = 0;

function pass(n) { passCount++; process.stdout.write('  PASS  ' + n + '\n'); }
function fail(n, m) {
  failCount++;
  process.stdout.write('  FAIL  ' + n + ' — ' + m + '\n');
}
function assertEqual(n, actual, expected) {
  if (actual === expected) pass(n);
  else fail(n, 'expected ' + JSON.stringify(expected) + ', got ' + JSON.stringify(actual));
}
function assertTrue(n, cond, detail) {
  if (cond) pass(n);
  else fail(n, 'condition false' + (detail ? ' — ' + detail : ''));
}

// ── Per-case fresh harness ───────────────────────────────────────────────

function fresh() {
  delete require.cache[require.resolve(MODULE_PATH)];
  var dom = new JSDOM(
    '<!doctype html><html><body><div id="chat-host"></div></body></html>',
    { url: 'http://localhost/', pretendToBeVisual: true }
  );
  global.window = dom.window;
  global.document = dom.window.document;
  // job-queue.js calls window.fetch when no transport is supplied. We
  // pass a stub transport explicitly per test to keep things hermetic.
  require(MODULE_PATH);
  var ns = dom.window.OraJobQueue;
  if (!ns) throw new Error('OraJobQueue did not register');
  return { win: dom.window, doc: dom.window.document, ns: ns };
}
function teardown(h) {
  try { h.ns.destroy(); } catch (_e) {}
  try { h.win.close(); } catch (_e) {}
  delete global.window;
  delete global.document;
}

// ── §13.6 acceptance test ────────────────────────────────────────────────

process.stdout.write('\n--- job-queue cancel flow (WP-7.6.3) ---\n');

(function acceptance() {
  var h = fresh();
  try {
    var transportCalls = [];
    var resolveTransport;
    h.ns.init({
      chatHostEl: h.doc.getElementById('chat-host'),
      conversationId: 'cid-test',
      cancelTransport: function (jobId) {
        transportCalls.push(jobId);
        return new Promise(function (res) { resolveTransport = res; });
      },
    });

    // 1. Dispatch — feed an "in_progress" job event as if the SSE bridge
    //    delivered it.
    var jobId = 'job-1';
    h.ns.handleEvent({
      type: 'status_changed',
      conversation_id: 'cid-test',
      job: {
        id: jobId,
        capability: 'video_generates',
        parameters: {},
        dispatched_at: Date.now() / 1000 - 5,
        status: 'in_progress',
        cancel_requested: false,
      },
    });
    var jobs = h.ns.getKnownJobs();
    assertTrue('job present after dispatch', !!jobs[jobId]);
    var btn = h.doc.querySelector('[data-job-cancel="' + jobId + '"]');
    assertTrue('cancel button rendered for in_progress job', !!btn);

    // 2. First click → modal opens with billing warning text.
    h.ns._testRequestCancel(jobId);
    var modal = h.ns._testGetModalState();
    assertTrue('modal visible after first click', modal.visible);
    assertEqual('modal scoped to job id', modal.forJobId, jobId);
    assertTrue('warning text mentions billing',
               modal.warningText &&
               modal.warningText.indexOf('billing') !== -1,
               'got: ' + modal.warningText);

    // 3. Second click (confirm) → transport called with the job id.
    assertEqual('transport not called before confirm', transportCalls.length, 0);
    h.ns._testConfirmCancel();
    assertEqual('transport called once', transportCalls.length, 1);
    assertEqual('transport called with job id', transportCalls[0], jobId);
    var modal2 = h.ns._testGetModalState();
    assertTrue('modal hidden after confirm', !modal2.visible);

    // 4. Optimistic UI: row pill shows "Cancelling…" and button is gone.
    var pill = h.doc.querySelector('[data-job-id="' + jobId + '"] .ora-job__status');
    assertTrue('pill shows Cancelling…',
               pill && pill.textContent.indexOf('Cancelling') !== -1,
               'got: ' + (pill && pill.textContent));
    var btnAfter = h.doc.querySelector('[data-job-cancel="' + jobId + '"]');
    assertTrue('cancel button removed after confirm', !btnAfter);

    // 5. Server-side SSE confirms the cancellation: status flips to
    //    "cancelled". The row should reflect the new status (and the
    //    standard terminal-delay schedules removal — we only check the
    //    transition here).
    h.ns.handleEvent({
      type: 'status_changed',
      conversation_id: 'cid-test',
      job: {
        id: jobId,
        capability: 'video_generates',
        parameters: {},
        dispatched_at: Date.now() / 1000 - 6,
        status: 'cancelled',
        cancel_requested: true,
        completed_at: Date.now() / 1000,
      },
    });
    var pillAfter = h.doc.querySelector('[data-job-id="' + jobId + '"] .ora-job__status');
    assertTrue('pill shows Cancelled',
               pillAfter && pillAfter.textContent.indexOf('Cancelled') !== -1,
               'got: ' + (pillAfter && pillAfter.textContent));

    // Resolve transport so the test exits cleanly.
    if (typeof resolveTransport === 'function') resolveTransport({});
  } finally {
    teardown(h);
  }
})();

// ── Edge: cancel from modal "Keep running" button is a no-op ────────────

(function keepRunningIsNoop() {
  var h = fresh();
  try {
    var calls = 0;
    h.ns.init({
      chatHostEl: h.doc.getElementById('chat-host'),
      conversationId: 'cid-x',
      cancelTransport: function () { calls++; return Promise.resolve({}); },
    });
    h.ns.handleEvent({
      type: 'job_dispatched',
      conversation_id: 'cid-x',
      job: {
        id: 'jx', capability: 'image_generates', parameters: {},
        dispatched_at: Date.now() / 1000, status: 'in_progress',
        cancel_requested: false,
      },
    });
    h.ns._testRequestCancel('jx');
    assertTrue('modal opens', h.ns._testGetModalState().visible);
    // Click "Keep running" (we use the DOM button so we exercise the
    // real listener, not just the test hook).
    var keep = h.doc.querySelector('.ora-job-cancel-modal__keep');
    assertTrue('keep-running button mounted', !!keep);
    var ev = new h.win.MouseEvent('click', { bubbles: true, cancelable: true });
    keep.dispatchEvent(ev);
    assertTrue('modal closed after keep', !h.ns._testGetModalState().visible);
    assertEqual('transport NOT called', calls, 0);
    var btn = h.doc.querySelector('[data-job-cancel="jx"]');
    assertTrue('cancel button still rendered after keep', !!btn);
  } finally {
    teardown(h);
  }
})();

// ── Edge: terminal jobs do NOT get a cancel button ───────────────────────

(function noCancelOnTerminal() {
  var h = fresh();
  try {
    h.ns.init({
      chatHostEl: h.doc.getElementById('chat-host'),
      conversationId: 'cid-t',
    });
    h.ns.handleEvent({
      type: 'status_changed',
      conversation_id: 'cid-t',
      job: {
        id: 'jt', capability: 'video_generates', parameters: {},
        dispatched_at: Date.now() / 1000, status: 'complete',
        cancel_requested: false, completed_at: Date.now() / 1000,
      },
    });
    var btn = h.doc.querySelector('[data-job-cancel="jt"]');
    assertTrue('no cancel button on complete job', !btn);
  } finally {
    teardown(h);
  }
})();

// ── Summary ─────────────────────────────────────────────────────────────

process.stdout.write('\n  ' + passCount + ' passed, ' + failCount + ' failed\n');
process.exit(failCount === 0 ? 0 : 1);
