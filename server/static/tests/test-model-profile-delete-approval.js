#!/usr/bin/env node
/* Focused jsdom coverage for protected custom Model Profile deletion. */
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

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body>'
  + '<button id="sidebarReviewQueueOpen">Review Queue</button>'
  + '<div id="modelsHost"></div>'
  + '</body></html>',
  {url: 'http://localhost/', pretendToBeVisual: true, runScripts: 'outside-only'}
);
var w = dom.window;
var deleteCalls = [];
var confirmations = [];
var alerts = [];
var protectionEvents = [];
var reviewQueueOpens = [];
var deleted = false;

function response(payload, status) {
  return Promise.resolve({
    ok: !status || status < 400,
    status: status || 200,
    json: function () { return Promise.resolve(payload); },
  });
}

w.confirm = function (message) {
  confirmations.push(String(message));
  return true;
};
w.alert = function (message) { alerts.push(String(message)); };
w.OraReviewQueuePanel = {
  open: function (options) { reviewQueueOpens.push(options || {}); },
};
w.document.addEventListener(
  'ora:system-protection-approval-required',
  function (event) { protectionEvents.push(event.detail || {}); }
);
w.fetch = function (url, options) {
  var decoded = decodeURIComponent(String(url));
  options = options || {};
  if (decoded === '/api/model-registry?categories=all') {
    return response({
      models: {},
      generated_at: new Date().toISOString(),
      reach_counts: {
        total: 0, reach_true: 0, reach_rate: 0,
        reach_false: 0, reach_null: 0,
        vendor_true: 0, vendor_false: 0, vendor_null: 0,
        newest_probed_at: null,
      },
    });
  }
  if (decoded === '/api/model-registry/picks') return response({picks: []});
  if (decoded === '/api/configurations') {
    return response({
      presets: {},
      customs: deleted ? [] : [{
        name: 'Approval Test',
        big1: null, big2: null, fast1: null, small: null,
        toggles: {},
      }],
      active_name: 'free',
      active_toggles: {},
    });
  }
  if (decoded === '/models') return response({});
  if (decoded === '/api/model-registry/reach/status') {
    return response({in_progress: false, last_summary: {}});
  }
  if (decoded === '/api/configurations/Approval Test'
      && options.method === 'DELETE') {
    deleteCalls.push({url: decoded, options: options});
    if (deleteCalls.length === 1) {
      return response({
        status: 'awaiting_system_protection_approval',
        error: 'GATED: exact approval is required',
        queue_id: 'queue-model-profile-delete',
        retry_required: true,
      }, 409);
    }
    deleted = true;
    return response({deleted: 'Approval Test'});
  }
  return response({});
};

vm.runInContext(
  fs.readFileSync(path.resolve(__dirname, '..', 'models-pane.js'), 'utf8'),
  dom.getInternalVMContext(),
  {filename: 'models-pane.js'}
);

var results = [];
function record(name, ok, detail) {
  results.push({name: name, ok: !!ok, detail: detail || ''});
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name
    + (detail ? ' - ' + detail : ''));
}
function waitFor(predicate) {
  var started = Date.now();
  return new Promise(function poll(resolve, reject) {
    if (predicate()) return resolve();
    if (Date.now() - started > 1000) return reject(new Error('timed out'));
    w.setTimeout(function () { poll(resolve, reject); }, 5);
  });
}

(async function run() {
  var host = w.document.getElementById('modelsHost');
  w.OraModelsPane.init(host);
  await waitFor(function () {
    return !!host.querySelector('[data-config-name="Approval Test"] [data-action="delete"]');
  });

  var deleteButton = host.querySelector(
    '[data-config-name="Approval Test"] [data-action="delete"]'
  );
  deleteButton.click();
  await waitFor(function () { return alerts.length === 1; });

  var alertText = alerts[0] || '';
  record('first Delete dispatches the structured approval event',
    protectionEvents.length === 1
      && protectionEvents[0].action === 'Delete Model Profile'
      && protectionEvents[0].profile_name === 'Approval Test'
      && protectionEvents[0].queue_id === 'queue-model-profile-delete'
      && protectionEvents[0].retry_required === true);
  record('first Delete opens Review Queue on Paused',
    reviewQueueOpens.length === 1 && reviewQueueOpens[0].tab === 'paused');
  record('alert gives approval and second-Delete instructions in plain language',
    /approve the request in review queue/i.test(alertText)
      && /click delete again/i.test(alertText)
      && !/^could not delete:/i.test(alertText)
      && !/GATED/.test(alertText));

  deleteButton.click();
  await waitFor(function () {
    return deleteCalls.length === 2
      && !host.querySelector('[data-config-name="Approval Test"]');
  });
  record('approved retry asks for confirmation again and succeeds',
    confirmations.length === 2
      && deleteCalls.length === 2
      && deleted === true
      && alerts.length === 1);

  w.OraModelsPane.destroy();
  var failures = results.filter(function (result) { return !result.ok; });
  if (failures.length) process.exitCode = 1;
})().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
});
