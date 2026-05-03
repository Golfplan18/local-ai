#!/usr/bin/env node
/* test-capability-image-critique.js — WP-7.3.3h
 *
 * Smoke test for OraCapabilityImageCritique. Spins up jsdom, loads the
 * slot wiring against a mocked fetch, and walks the §3.8 contract:
 *
 *   - dispatch with {image, rubric, depth} POSTs the right body
 *   - structured response (rubric_scores + prose) renders into the
 *     invocation UI's `.ora-cap-result` panel as a table + prose div
 *   - capability-result event fires with both rubric_scores and prose
 *   - missing image surfaces `no_specific_guidance` without round-trip
 *   - missing rubric AND missing genre also surfaces no_specific_guidance
 *   - depth defaults to "standard" for invalid values
 *   - 5xx maps to model_unavailable; other 4xx maps to no_specific_guidance
 *   - slot filter: image_styles dispatches do not trigger this module
 *
 * Run:  node ~/ora/server/static/tests/test-capability-image-critique.js
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var path = require('path');

// ── jsdom bootstrap (vendored under ora-visual-compiler/tests) ───────────────

var COMPILER_TEST_NODE_MODULES = path.resolve(
  __dirname, '..', 'ora-visual-compiler', 'tests', 'node_modules'
);
var JSDOM_PATH = path.join(COMPILER_TEST_NODE_MODULES, 'jsdom');

var jsdom;
try {
  jsdom = require(JSDOM_PATH);
} catch (e) {
  console.error('error: jsdom not available at ' + JSDOM_PATH);
  console.error('  install via: cd ' + path.dirname(COMPILER_TEST_NODE_MODULES) + ' && npm install');
  process.exit(2);
}

var dom = new jsdom.JSDOM('<!doctype html><html><body><div id="host"></div></body></html>', {
  pretendToBeVisual: true,
});

var w = dom.window;
global.window = w;
global.document = w.document;
global.HTMLElement = w.HTMLElement;
global.Element = w.Element;
global.Event = w.Event;
global.CustomEvent = w.CustomEvent;
global.requestAnimationFrame = w.requestAnimationFrame || function (fn) { return setTimeout(fn, 0); };

// ── Module under test ────────────────────────────────────────────────────────

var WIRING_PATH = path.resolve(__dirname, '..', 'capability-image-critique.js');
require(WIRING_PATH);  // attaches to global.window.OraCapabilityImageCritique
var WIRING = w.OraCapabilityImageCritique;
if (!WIRING) {
  console.error('error: OraCapabilityImageCritique did not register on window');
  process.exit(2);
}

// ── Test harness ─────────────────────────────────────────────────────────────

var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  console.log('  ' + (ok ? 'PASS' : 'FAIL') + '  ' + name + (detail ? '  — ' + detail : ''));
}

function summarize() {
  var total = results.length;
  var passed = results.filter(function (r) { return r.ok; }).length;
  console.log('');
  console.log(passed + ' / ' + total + ' tests passed');
  if (passed < total) {
    console.log('FAILURES:');
    results.filter(function (r) { return !r.ok; }).forEach(function (r) {
      console.log('  - ' + r.name + ' :: ' + (r.detail || '(no detail)'));
    });
    process.exit(1);
  }
  process.exit(0);
}

function _resetHost() {
  if (WIRING._getActive()) WIRING.destroy();
  var host = w.document.getElementById('host');
  while (host.firstChild) host.removeChild(host.firstChild);
  // Pre-mount a `.ora-cap-result` so we mimic what the invocation UI
  // would have placed in the DOM after an in-flight dispatch.
  var resultEl = w.document.createElement('div');
  resultEl.className = 'ora-cap-result';
  host.appendChild(resultEl);
  return host;
}

// 1×1 red PNG, base64 — stand-in for "the painting under critique".
var RED_SQUARE_B64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=';
var RED_SQUARE_DATA_URL = 'data:image/png;base64,' + RED_SQUARE_B64;

function _mockFetchOk(payload) {
  var calls = [];
  var fn = function (url, init) {
    calls.push({ url: url, init: init });
    return Promise.resolve({
      status: 200,
      ok: true,
      json: function () { return Promise.resolve(payload); },
    });
  };
  fn.calls = calls;
  return fn;
}

function _mockFetchErr(status, code, message) {
  var calls = [];
  var fn = function (url, init) {
    calls.push({ url: url, init: init });
    return Promise.resolve({
      status: status,
      ok: false,
      json: function () {
        return Promise.resolve({ error: { code: code, message: message } });
      },
    });
  };
  fn.calls = calls;
  return fn;
}

// ── Tests ────────────────────────────────────────────────────────────────────

async function testHappyPath() {
  var host = _resetHost();
  var fetchImpl = _mockFetchOk({
    rubric_scores: {
      composition: { score: 8, comment: 'Strong rule-of-thirds.' },
      color:       { score: 7, comment: 'Cohesive palette.' },
      technique:   { score: 6, comment: 'Brushwork inconsistent.' },
    },
    prose:    'A confident landscape with notable strengths in composition.',
    provider: 'mock',
    metadata: { depth: 'standard' },
  });
  var ui = {
    _result: null, _error: null,
    renderResult: function (p) { ui._result = p; },
    renderError: function (p) { ui._error = p; },
  };

  var resultEvent = null;
  host.addEventListener('capability-result', function (e) { resultEvent = e.detail; });

  var ctl = WIRING.init({ hostEl: host, fetchImpl: fetchImpl, ui: ui });

  await ctl.handleDispatch({
    slot: 'image_critique',
    inputs: {
      image:  RED_SQUARE_DATA_URL,
      rubric: 'composition, color, technique',
      genre:  'landscape',
      depth:  'standard',
    },
  });

  record('fetch was POSTed to default endpoint',
    fetchImpl.calls.length === 1
      && fetchImpl.calls[0].url === WIRING.DEFAULT_ENDPOINT
      && fetchImpl.calls[0].init && fetchImpl.calls[0].init.method === 'POST',
    fetchImpl.calls.length ? fetchImpl.calls[0].url : 'no calls');

  var sentBody = fetchImpl.calls[0] ? JSON.parse(fetchImpl.calls[0].init.body) : null;
  record('request body carries image_data_url + rubric + genre + depth',
    sentBody
      && sentBody.image_data_url === RED_SQUARE_DATA_URL
      && sentBody.rubric === 'composition, color, technique'
      && sentBody.genre === 'landscape'
      && sentBody.depth === 'standard',
    sentBody ? JSON.stringify(Object.keys(sentBody)) : 'no body');

  // Result panel rendering
  var table = host.querySelector('.ora-cap-result__rubric');
  record('rubric table rendered into .ora-cap-result',
    !!table, table ? 'ok' : 'no table');

  if (table) {
    var rows = table.querySelectorAll('tbody tr');
    record('rubric table has one row per criterion',
      rows.length === 3, 'rows=' + rows.length);
    if (rows.length > 0) {
      var firstCells = rows[0].querySelectorAll('td');
      record('first row carries criterion / score / comment in three cells',
        firstCells.length === 3
          && firstCells[0].textContent === 'composition'
          && firstCells[1].textContent === '8'
          && /rule-of-thirds/.test(firstCells[2].textContent),
        firstCells.length + ' cells | ' + (firstCells[0] ? firstCells[0].textContent : ''));
    }
  }

  var prose = host.querySelector('.ora-cap-result__prose');
  record('prose section rendered into .ora-cap-result',
    !!prose && prose.textContent.indexOf('confident landscape') >= 0,
    prose ? prose.textContent.slice(0, 30) : 'no prose');

  // Event + UI delivery
  record('capability-result event carried rubric_scores + prose',
    resultEvent
      && resultEvent.rubric_scores
      && resultEvent.rubric_scores.composition
      && resultEvent.rubric_scores.composition.score === 8
      && typeof resultEvent.prose === 'string'
      && resultEvent.prose.length > 0,
    resultEvent ? 'ok' : 'no event');

  record('UI.renderResult was invoked with prose',
    ui._result && ui._result.output && ui._result.output.indexOf('confident') >= 0,
    ui._result ? 'ok' : 'not invoked');
  record('UI.renderError was NOT invoked on happy path',
    ui._error === null,
    ui._error ? 'invoked: ' + ui._error.code : 'ok');
}

async function testMissingImage() {
  var host = _resetHost();
  var fetchImpl = _mockFetchOk({ rubric_scores: {}, prose: 'unused' });
  var ui = { _err: null, renderError: function (p) { ui._err = p; }, renderResult: function () {} };

  var errorEvent = null;
  host.addEventListener('capability-error', function (e) { errorEvent = e.detail; });

  var ctl = WIRING.init({ hostEl: host, fetchImpl: fetchImpl, ui: ui });

  var threw = null;
  try {
    await ctl.handleDispatch({
      slot:   'image_critique',
      inputs: { rubric: 'composition' },
    });
  } catch (e) { threw = e; }

  record('missing image surfaces no_specific_guidance',
    threw && threw.code === 'no_specific_guidance',
    threw ? threw.code : 'no throw');
  record('no fetch round-trip when image is missing',
    fetchImpl.calls.length === 0,
    'calls=' + fetchImpl.calls.length);
  record('capability-error fired with no_specific_guidance',
    errorEvent && errorEvent.code === 'no_specific_guidance',
    errorEvent ? errorEvent.code : 'no event');
  record('UI.renderError was invoked',
    ui._err && ui._err.code === 'no_specific_guidance',
    ui._err ? ui._err.code : 'not invoked');
}

async function testMissingRubricAndGenre() {
  var host = _resetHost();
  var fetchImpl = _mockFetchOk({ rubric_scores: {}, prose: 'unused' });

  var ctl = WIRING.init({ hostEl: host, fetchImpl: fetchImpl });

  var threw = null;
  try {
    await ctl.handleDispatch({
      slot:   'image_critique',
      inputs: { image: RED_SQUARE_DATA_URL },
    });
  } catch (e) { threw = e; }

  record('no rubric AND no genre surfaces no_specific_guidance eagerly',
    threw && threw.code === 'no_specific_guidance',
    threw ? threw.code : 'no throw');
  record('no fetch round-trip when rubric and genre both empty',
    fetchImpl.calls.length === 0,
    'calls=' + fetchImpl.calls.length);
}

async function testGenreOnlyAllowed() {
  // §3.8 says rubric is optional — genre alone is enough guidance.
  var host = _resetHost();
  var fetchImpl = _mockFetchOk({
    rubric_scores: { mood: { score: 5, comment: 'Sombre.' } },
    prose: 'A sombre piece.',
  });

  var ctl = WIRING.init({ hostEl: host, fetchImpl: fetchImpl });
  await ctl.handleDispatch({
    slot:   'image_critique',
    inputs: { image: RED_SQUARE_DATA_URL, genre: 'expressionism' },
  });

  record('genre-only dispatch reaches the server (rubric optional)',
    fetchImpl.calls.length === 1,
    'calls=' + fetchImpl.calls.length);

  var sentBody = fetchImpl.calls[0] ? JSON.parse(fetchImpl.calls[0].init.body) : null;
  record('genre-only request body carries genre and empty rubric',
    sentBody && sentBody.genre === 'expressionism' && sentBody.rubric === '',
    sentBody ? JSON.stringify({ rubric: sentBody.rubric, genre: sentBody.genre }) : 'no body');
}

async function testInvalidDepthFallsBack() {
  var host = _resetHost();
  var fetchImpl = _mockFetchOk({ rubric_scores: {}, prose: 'ok' });
  var ctl = WIRING.init({ hostEl: host, fetchImpl: fetchImpl });

  await ctl.handleDispatch({
    slot:   'image_critique',
    inputs: {
      image:  RED_SQUARE_DATA_URL,
      rubric: 'composition',
      depth:  'banana-foster',
    },
  });

  var sentBody = fetchImpl.calls[0] ? JSON.parse(fetchImpl.calls[0].init.body) : null;
  record('invalid depth coerced to "standard"',
    sentBody && sentBody.depth === WIRING.DEFAULT_DEPTH,
    sentBody ? sentBody.depth : 'no body');
}

async function testQuickDepthPreserved() {
  var host = _resetHost();
  var fetchImpl = _mockFetchOk({ rubric_scores: {}, prose: 'ok' });
  var ctl = WIRING.init({ hostEl: host, fetchImpl: fetchImpl });

  await ctl.handleDispatch({
    slot:   'image_critique',
    inputs: { image: RED_SQUARE_DATA_URL, rubric: 'x', depth: 'quick' },
  });

  var sentBody = fetchImpl.calls[0] ? JSON.parse(fetchImpl.calls[0].init.body) : null;
  record('valid depth "quick" passes through',
    sentBody && sentBody.depth === 'quick',
    sentBody ? sentBody.depth : 'no body');
}

async function test4xxFromServer() {
  var host = _resetHost();
  var fetchImpl = _mockFetchErr(400, 'no_specific_guidance', 'Need a rubric or genre.');
  var ui = { _err: null, renderError: function (p) { ui._err = p; }, renderResult: function () {} };
  var errorEvent = null;
  host.addEventListener('capability-error', function (e) { errorEvent = e.detail; });

  var ctl = WIRING.init({ hostEl: host, fetchImpl: fetchImpl, ui: ui });
  var threw = null;
  try {
    await ctl.handleDispatch({
      slot:   'image_critique',
      inputs: { image: RED_SQUARE_DATA_URL, rubric: 'x' },
    });
  } catch (e) { threw = e; }

  record('server 400 maps to no_specific_guidance',
    threw && threw.code === 'no_specific_guidance',
    threw ? threw.code : 'no throw');
  record('capability-error fired on 4xx',
    errorEvent && errorEvent.code === 'no_specific_guidance',
    errorEvent ? errorEvent.code : 'no event');
}

async function test5xxFromServer() {
  var host = _resetHost();
  var fetchImpl = _mockFetchErr(503, null, 'Vision model offline.');
  var ui = { _err: null, renderError: function (p) { ui._err = p; }, renderResult: function () {} };

  var ctl = WIRING.init({ hostEl: host, fetchImpl: fetchImpl, ui: ui });
  var threw = null;
  try {
    await ctl.handleDispatch({
      slot:   'image_critique',
      inputs: { image: RED_SQUARE_DATA_URL, rubric: 'x' },
    });
  } catch (e) { threw = e; }

  record('server 5xx maps to model_unavailable',
    threw && threw.code === 'model_unavailable',
    threw ? threw.code : 'no throw');
}

async function testEmptyResponseRejected() {
  var host = _resetHost();
  // Server returns 200 but with no scores AND no prose — count as miss.
  var fetchImpl = _mockFetchOk({});
  var ctl = WIRING.init({ hostEl: host, fetchImpl: fetchImpl });

  var threw = null;
  try {
    await ctl.handleDispatch({
      slot:   'image_critique',
      inputs: { image: RED_SQUARE_DATA_URL, rubric: 'x' },
    });
  } catch (e) { threw = e; }

  record('empty response body rejected as model_unavailable',
    threw && threw.code === 'model_unavailable',
    threw ? threw.code : 'no throw');
}

async function testProseOnlyAccepted() {
  // Server returns 200 with prose but no scores — accepted as a valid result.
  var host = _resetHost();
  var fetchImpl = _mockFetchOk({ prose: 'A short impression.' });
  var ctl = WIRING.init({ hostEl: host, fetchImpl: fetchImpl });

  var resultEvent = null;
  host.addEventListener('capability-result', function (e) { resultEvent = e.detail; });

  await ctl.handleDispatch({
    slot:   'image_critique',
    inputs: { image: RED_SQUARE_DATA_URL, rubric: 'composition' },
  });

  record('prose-only response is accepted',
    resultEvent && resultEvent.prose === 'A short impression.',
    resultEvent ? 'prose=' + resultEvent.prose : 'no event');

  // Result panel: prose should render even when scores are absent.
  var prose = host.querySelector('.ora-cap-result__prose');
  record('prose renders in result panel even without scores',
    !!prose, prose ? 'ok' : 'no prose');
  // Table should NOT render when scores are absent.
  var table = host.querySelector('.ora-cap-result__rubric');
  record('rubric table absent when no scores',
    !table, table ? 'unexpected table' : 'ok');
}

async function testSlotFilter() {
  // image_styles dispatches must not be intercepted.
  var host = _resetHost();
  var fetchImpl = _mockFetchOk({ rubric_scores: {}, prose: 'ok' });
  WIRING.init({ hostEl: host, fetchImpl: fetchImpl });

  var evt = new w.CustomEvent('capability-dispatch', {
    detail: { slot: 'image_styles', inputs: { source_image: RED_SQUARE_DATA_URL } },
    bubbles: true,
  });
  host.dispatchEvent(evt);
  await new Promise(function (r) { setTimeout(r, 5); });

  record('image_styles dispatch did not trigger fetch',
    fetchImpl.calls.length === 0,
    'calls=' + fetchImpl.calls.length);
}

async function testNumericScoreShorthand() {
  // Server may return shorthand: { composition: 7 } instead of { composition: { score: 7 } }
  var host = _resetHost();
  var fetchImpl = _mockFetchOk({
    rubric_scores: { composition: 7, color: 8 },
    prose: 'shorthand test',
  });
  var ctl = WIRING.init({ hostEl: host, fetchImpl: fetchImpl });

  await ctl.handleDispatch({
    slot:   'image_critique',
    inputs: { image: RED_SQUARE_DATA_URL, rubric: 'composition, color' },
  });

  var rows = host.querySelectorAll('.ora-cap-result__rubric tbody tr');
  record('numeric-shorthand scores render two rows',
    rows.length === 2, 'rows=' + rows.length);
  if (rows.length >= 1) {
    var cells = rows[0].querySelectorAll('td');
    record('shorthand score renders in score column',
      cells.length === 3 && cells[1].textContent === '7',
      cells.length ? 'cell[1]=' + cells[1].textContent : 'no cells');
    record('shorthand row has empty comment cell',
      cells.length === 3 && cells[2].textContent === '',
      cells.length ? 'cell[2]=' + JSON.stringify(cells[2].textContent) : 'no cells');
  }
}

async function testStatusCodeMap() {
  record('status 400 → no_specific_guidance',
    WIRING._statusToCode(400) === 'no_specific_guidance',
    WIRING._statusToCode(400));
  record('status 422 → no_specific_guidance',
    WIRING._statusToCode(422) === 'no_specific_guidance',
    WIRING._statusToCode(422));
  record('status 429 → no_specific_guidance',
    WIRING._statusToCode(429) === 'no_specific_guidance',
    WIRING._statusToCode(429));
  record('status 500 → model_unavailable',
    WIRING._statusToCode(500) === 'model_unavailable',
    WIRING._statusToCode(500));
  record('status 503 → model_unavailable',
    WIRING._statusToCode(503) === 'model_unavailable',
    WIRING._statusToCode(503));
  record('status 0 (network error) → model_unavailable',
    WIRING._statusToCode(0) === 'model_unavailable',
    WIRING._statusToCode(0));
}

async function testNormalizeImageRef() {
  record('normalizeImageRef: data URL passes through',
    WIRING._normalizeImageRef(RED_SQUARE_DATA_URL) === RED_SQUARE_DATA_URL,
    'ok');
  record('normalizeImageRef: bare base64 wraps in data URL',
    WIRING._normalizeImageRef(RED_SQUARE_B64) === RED_SQUARE_DATA_URL,
    'ok');
  record('normalizeImageRef: null returns null',
    WIRING._normalizeImageRef(null) === null,
    'ok');
  record('normalizeImageRef: object with data_url unwraps',
    WIRING._normalizeImageRef({ data_url: RED_SQUARE_DATA_URL }) === RED_SQUARE_DATA_URL,
    'ok');
  record('normalizeImageRef: http URL passes through',
    WIRING._normalizeImageRef('https://example.com/foo.png') === 'https://example.com/foo.png',
    'ok');
}

// ── Run ──────────────────────────────────────────────────────────────────────

(async function () {
  console.log('test-capability-image-critique (WP-7.3.3h)');
  console.log('-------------------------------------------');

  try { await testHappyPath(); }                catch (e) { record('happy path threw', false, e.message); }
  try { await testMissingImage(); }             catch (e) { record('missing image threw', false, e.message); }
  try { await testMissingRubricAndGenre(); }    catch (e) { record('missing rubric+genre threw', false, e.message); }
  try { await testGenreOnlyAllowed(); }         catch (e) { record('genre-only threw', false, e.message); }
  try { await testInvalidDepthFallsBack(); }    catch (e) { record('invalid depth threw', false, e.message); }
  try { await testQuickDepthPreserved(); }      catch (e) { record('quick depth threw', false, e.message); }
  try { await test4xxFromServer(); }            catch (e) { record('4xx threw', false, e.message); }
  try { await test5xxFromServer(); }            catch (e) { record('5xx threw', false, e.message); }
  try { await testEmptyResponseRejected(); }    catch (e) { record('empty response threw', false, e.message); }
  try { await testProseOnlyAccepted(); }        catch (e) { record('prose-only threw', false, e.message); }
  try { await testSlotFilter(); }               catch (e) { record('slot filter threw', false, e.message); }
  try { await testNumericScoreShorthand(); }    catch (e) { record('numeric shorthand threw', false, e.message); }
  try { await testStatusCodeMap(); }            catch (e) { record('status code map threw', false, e.message); }
  try { await testNormalizeImageRef(); }        catch (e) { record('normalize image ref threw', false, e.message); }

  summarize();
})();
