#!/usr/bin/env node
/* G1.16 browser Model Profile selection and assisted-migration contract. */
'use strict';

var fs = require('fs');
var path = require('path');
var JSDOM_PATH = path.join(
  __dirname, '..', 'ora-visual-compiler', 'tests', 'node_modules', 'jsdom'
);
var jsdom;
try { jsdom = require(JSDOM_PATH); }
catch (error) {
  console.error('error: jsdom not available at ' + JSDOM_PATH);
  process.exit(2);
}

var dom = new jsdom.JSDOM(
  '<!doctype html><html><body>'
  + '<button id="sidebarModelConfigBtn"><span id="sidebarModelConfigName">—</span></button>'
  + '<button id="inputToolbarModelProfile" data-input-toolbar="model-profile">—</button>'
  + '</body></html>',
  { url: 'http://localhost/', pretendToBeVisual: true }
);
var w = dom.window;
global.window = w;
global.document = w.document;
global.Event = w.Event;
global.CustomEvent = w.CustomEvent;
global.HTMLElement = w.HTMLElement;

w.OraSidebar = { getActiveProject: function () { return 'ora'; } };
var requests = [];
var confirmAnswers = [];
w.confirm = function () { return confirmAnswers.shift() === true; };
w.alert = function () {};
global.fetch = function (url, options) {
  options = options || {};
  var payload = options.body ? JSON.parse(options.body) : null;
  requests.push({ url: url, method: options.method || 'GET', payload: payload });
  var data;
  if (url.indexOf('/api/model-profiles?') === 0) {
    data = {
      profiles: [
        { name: 'Balanced', health: { status: 'ok', reason: 'ready' } },
        { name: 'Legacy', health: { status: 'deprecated', reason: 'retired model' } },
        { name: 'Offline', health: { status: 'unavailable', reason: 'no endpoint' } },
      ],
      effective: {
        selected: { source: 'project', name: 'Balanced', runtime_name: 'locked' },
      },
    };
  } else if (url === '/api/model-profiles/migration/preview') {
    data = { ok: true, proposal: {
      proposal_id: 'a'.repeat(64), replacements: { retired: 'replacement' },
    } };
  } else if (url === '/api/model-profiles/migration/confirm') {
    data = { ok: true, receipt: { proposal_id: 'a'.repeat(64) } };
  } else if (url.indexOf('/api/model-profiles/project/') === 0) {
    data = { ok: true };
  } else {
    return Promise.reject(new Error('unexpected fetch: ' + url));
  }
  return Promise.resolve({
    ok: true, status: 200,
    json: function () { return Promise.resolve(data); },
  });
};

require(path.resolve(__dirname, '..', 'js', 'model-profile-selector.js'));

var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? ' - ' + detail : ''));
}
function wait() {
  return new Promise(function (resolve) { w.setTimeout(resolve, 0); });
}
function menuButton(text) {
  return Array.from(w.document.querySelectorAll('.model-profile-menu button')).find(
    function (button) { return button.textContent.indexOf(text) !== -1; }
  );
}
function choiceButton(text) {
  return Array.from(w.document.querySelectorAll('.model-profile-menu__choice')).find(
    function (button) { return button.textContent.indexOf(text) !== -1; }
  );
}

async function run() {
  await wait(); await wait();
  record('project default renders directly beneath the Active Project surface',
    w.document.getElementById('sidebarModelConfigName').textContent === 'Balanced');
  record('input surface shows inherited Model Profile by name',
    w.document.getElementById('inputToolbarModelProfile').textContent === 'Balanced');

  w.document.dispatchEvent(new w.CustomEvent('ora:input-toolbar:model-profile'));
  await wait(); await wait();
  var unavailable = choiceButton('Offline');
  record('unavailable Model Profile cannot be selected', !!unavailable && unavailable.disabled);
  choiceButton('Balanced').click();
  record('one-run choice remains local until submit',
    w.OraModelProfiles.getOneRunOverride() === 'Balanced'
      && requests.filter(function (r) { return r.method === 'POST'; }).length === 0);
  var failedSnapshot = w.OraModelProfiles.snapshotForSubmission();
  var failedReservation = w.OraModelProfiles.reserveSubmission(failedSnapshot);
  w.OraModelProfiles.restoreSubmission(failedReservation);
  record('failed delivery preserves the one-run choice',
    w.OraModelProfiles.getOneRunOverride() === 'Balanced');
  w.OraModelProfiles.reserveSubmission(w.OraModelProfiles.snapshotForSubmission());
  record('server acceptance consumes the one-run choice',
    w.OraModelProfiles.getOneRunOverride() === '');

  w.document.getElementById('sidebarModelConfigBtn').click();
  await wait(); await wait();
  choiceButton('Balanced').click();
  await wait(); await wait();
  var projectWrite = requests.find(function (r) {
    return r.url === '/api/model-profiles/project/ora';
  });
  record('project selection uses the server-issued binding endpoint',
    !!projectWrite && projectWrite.payload.name === 'Balanced'
      && !Object.prototype.hasOwnProperty.call(projectWrite.payload, 'model_locks'));

  w.document.getElementById('sidebarModelConfigBtn').click();
  await wait(); await wait();
  confirmAnswers.push(false);
  menuButton('Review migration').click();
  await wait(); await wait();
  record('reviewing a migration without confirmation performs no mutation',
    requests.filter(function (r) {
      return r.url === '/api/model-profiles/migration/confirm';
    }).length === 0);

  confirmAnswers.push(true);
  menuButton('Review migration').click();
  await wait(); await wait(); await wait();
  var migration = requests.find(function (r) {
    return r.url === '/api/model-profiles/migration/confirm';
  });
  record('explicit acceptance confirms the exact reviewed proposal',
    !!migration && migration.payload.confirmed === true
      && migration.payload.proposal_id === 'a'.repeat(64));

  var index = fs.readFileSync(path.resolve(__dirname, '..', '..', 'index-v3.html'), 'utf8');
  record('public submit binds the one-run Model Profile to config_name',
    index.indexOf("body.append('config_name', submissionModelProfile)") !== -1);
  record('public surfaces use Model Profile terminology',
    index.indexOf('Model configuration</div>') === -1
      && index.indexOf('id="inputToolbarModelProfile"') !== -1);

  var passed = results.filter(function (result) { return result.ok; }).length;
  console.log('\n' + passed + ' / ' + results.length + ' tests passed');
  process.exit(passed === results.length ? 0 : 1);
}

run().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
