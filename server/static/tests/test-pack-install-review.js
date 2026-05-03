#!/usr/bin/env node
/* test-pack-install-review.js — WP-7.7.1
 *
 * Drives OraPackInstallReview through the §13.7 acceptance criterion:
 *   "load 3rd-party pack; modal shows all 4 categories; capability scope
 *    reflects macros' invocations; install only fires after explicit
 *    click."
 *
 * Run:
 *     node ~/ora/server/static/tests/test-pack-install-review.js
 *
 * Exit code 0 on full pass, 1 on any failure.
 */

'use strict';

var fs = require('fs');
var path = require('path');

var ORA_ROOT = path.resolve(__dirname, '..', '..', '..');
var REVIEW_PATH = path.join(ORA_ROOT, 'server', 'static', 'pack-install-review.js');

// ---- minimal jsdom-free DOM shim ------------------------------------------
//
// Mirrors the strategy used in test-canvas-share-reminder.js: a tiny
// Element/Document stand-in that supports innerHTML parsing for the
// shapes our modal uses (querySelector by class / id, addEventListener,
// click dispatch, focus, hidden flag). We don't aim for full DOM
// compliance — only enough to drive Show → Click → resolve.

function makeDom() {
  function newEl(tag) {
    var el = {
      tagName: String(tag).toUpperCase(),
      attributes: Object.create(null),
      dataset: Object.create(null),
      children: [],
      parent: null,
      _listeners: Object.create(null),
      _innerHTML: '',
      hidden: false,
      style: {},
      textContent: '',
      classList: {
        _set: Object.create(null),
        add: function (c) { this._set[c] = true; },
        remove: function (c) { delete this._set[c]; },
        contains: function (c) { return !!this._set[c]; }
      }
    };
    el.setAttribute = function (k, v) {
      el.attributes[k] = String(v);
      if (k === 'id') el.id = String(v);
      if (k === 'class') {
        el.className = String(v);
        el.classList._set = Object.create(null);
        var parts = String(v).split(/\s+/);
        for (var i = 0; i < parts.length; i++) {
          if (parts[i]) el.classList._set[parts[i]] = true;
        }
      }
      if (k.indexOf('data-') === 0) {
        el.dataset[k.slice(5).replace(/-([a-z])/g, function (_, c) { return c.toUpperCase(); })] = String(v);
      }
    };
    el.getAttribute = function (k) {
      return Object.prototype.hasOwnProperty.call(el.attributes, k)
        ? el.attributes[k] : null;
    };
    el.hasAttribute = function (k) {
      return Object.prototype.hasOwnProperty.call(el.attributes, k);
    };
    el.appendChild = function (child) {
      child.parent = el;
      el.children.push(child);
      return child;
    };
    el.removeChild = function (child) {
      var idx = el.children.indexOf(child);
      if (idx >= 0) el.children.splice(idx, 1);
      child.parent = null;
      return child;
    };
    el.addEventListener = function (type, fn) {
      (el._listeners[type] = el._listeners[type] || []).push(fn);
    };
    el.removeEventListener = function (type, fn) {
      var L = el._listeners[type] || [];
      var i = L.indexOf(fn); if (i >= 0) L.splice(i, 1);
    };
    el.dispatchEvent = function (evt) {
      evt.target = evt.target || el;
      var L = el._listeners[evt.type] || [];
      for (var i = 0; i < L.length; i++) L[i](evt);
      return !evt.defaultPrevented;
    };
    el.focus = function () { doc.activeElement = el; };
    Object.defineProperty(el, 'innerHTML', {
      get: function () { return el._innerHTML; },
      set: function (html) {
        el._innerHTML = String(html);
        el.children = parseHtmlChildren(String(html), el);
      }
    });
    el.querySelector = function (sel) {
      var match = matcherFor(sel);
      return findFirst(el, match);
    };
    el.querySelectorAll = function (sel) {
      var match = matcherFor(sel);
      return findAll(el, match);
    };
    return el;
  }

  function matcherFor(sel) {
    sel = String(sel).trim();
    if (sel.charAt(0) === '#') {
      var id = sel.slice(1);
      return function (n) { return n.id === id; };
    }
    if (sel.charAt(0) === '.') {
      var cls = sel.slice(1);
      return function (n) {
        return n.classList && n.classList.contains(cls);
      };
    }
    var tag = sel.toUpperCase();
    return function (n) { return n.tagName === tag; };
  }

  function findFirst(node, match) {
    for (var i = 0; i < node.children.length; i++) {
      var c = node.children[i];
      if (match(c)) return c;
      var deep = findFirst(c, match);
      if (deep) return deep;
    }
    return null;
  }

  function findAll(node, match) {
    var out = [];
    (function walk(n) {
      for (var i = 0; i < n.children.length; i++) {
        var c = n.children[i];
        if (match(c)) out.push(c);
        walk(c);
      }
    })(node);
    return out;
  }

  // Tiny parser: extracts elements with attributes + nested children.
  // Good enough for the shapes our renderer produces.
  function parseHtmlChildren(html, parent) {
    var out = [];
    var i = 0;
    while (i < html.length) {
      // Skip leading text.
      var lt = html.indexOf('<', i);
      if (lt < 0) {
        var trail = html.slice(i);
        if (trail.replace(/\s+/g, '').length > 0 && parent) {
          parent.textContent = (parent.textContent || '') + trail;
        }
        break;
      }
      // Comment / declaration.
      if (html.slice(lt, lt + 4) === '<!--') {
        var endC = html.indexOf('-->', lt + 4);
        i = endC < 0 ? html.length : endC + 3;
        continue;
      }
      // Closing tag — ignore at this level (caller already consumed it).
      if (html.charAt(lt + 1) === '/') {
        var gt0 = html.indexOf('>', lt);
        i = gt0 < 0 ? html.length : gt0 + 1;
        continue;
      }
      var gt = html.indexOf('>', lt);
      if (gt < 0) break;
      var tagBody = html.slice(lt + 1, gt);
      var selfClose = tagBody.charAt(tagBody.length - 1) === '/';
      if (selfClose) tagBody = tagBody.slice(0, -1);
      var sp = tagBody.search(/\s/);
      var tag, attrStr;
      if (sp < 0) { tag = tagBody; attrStr = ''; }
      else        { tag = tagBody.slice(0, sp); attrStr = tagBody.slice(sp + 1); }
      var el = newEl(tag);
      // Parse attributes.
      var ax = 0;
      while (ax < attrStr.length) {
        var nMatch = attrStr.slice(ax).match(/^\s*([a-zA-Z_:][\w:.\-]*)/);
        if (!nMatch) break;
        ax += nMatch[0].length;
        var name = nMatch[1];
        var val = '';
        if (attrStr.charAt(ax) === '=') {
          ax++;
          var quote = attrStr.charAt(ax);
          if (quote === '"' || quote === "'") {
            ax++;
            var endQ = attrStr.indexOf(quote, ax);
            val = endQ < 0 ? attrStr.slice(ax) : attrStr.slice(ax, endQ);
            ax = endQ < 0 ? attrStr.length : endQ + 1;
          } else {
            var unq = attrStr.slice(ax).match(/^[^\s>]*/);
            val = unq ? unq[0] : '';
            ax += val.length;
          }
        }
        el.setAttribute(name, val);
      }
      el.parent = parent;
      out.push(el);
      i = gt + 1;
      if (!selfClose) {
        // Find matching close — naive, doesn't handle deeply nested
        // same-tag, but our renderer always closes.
        var closeRe = new RegExp('</' + tag + '\\s*>', 'i');
        var rest = html.slice(i);
        var closeMatch = closeRe.exec(rest);
        if (closeMatch) {
          var inner = rest.slice(0, closeMatch.index);
          el._innerHTML = inner;
          el.children = parseHtmlChildren(inner, el);
          i += closeMatch.index + closeMatch[0].length;
        }
      }
    }
    return out;
  }

  var doc = newEl('document');
  doc.body = newEl('body');
  doc.appendChild(doc.body);
  doc.activeElement = doc.body;
  doc.createElement = newEl;
  doc._docListeners = Object.create(null);
  doc.addEventListener = function (type, fn /*, capture */) {
    (doc._docListeners[type] = doc._docListeners[type] || []).push(fn);
  };
  doc.removeEventListener = function (type, fn) {
    var L = doc._docListeners[type] || [];
    var i = L.indexOf(fn); if (i >= 0) L.splice(i, 1);
  };
  doc._fireKey = function (key) {
    var evt = { type: 'keydown', key: key, target: doc.activeElement,
                defaultPrevented: false,
                preventDefault: function () { this.defaultPrevented = true; } };
    var L = (doc._docListeners.keydown || []).slice();
    for (var i = 0; i < L.length; i++) L[i](evt);
  };
  return doc;
}

// Install the shim as `document` + `window` globals before requiring
// the module — module captures `document` on first show.
var doc = makeDom();
global.document = doc;
global.window   = global.window || {};
global.window.document = doc;

// Promise polyfill is unnecessary on Node 14+; we assume Node ≥ 10.

var reviewMod = require(REVIEW_PATH);

// ---- runner ---------------------------------------------------------------

var passCount = 0;
var failCount = 0;
var failures  = [];

function check(name, cond, detail) {
  if (cond) {
    passCount++;
    process.stdout.write('  PASS  ' + name + '\n');
  } else {
    failCount++;
    failures.push({ name: name, detail: detail });
    process.stdout.write('  FAIL  ' + name + '\n');
    if (detail) process.stdout.write('    ' + JSON.stringify(detail) + '\n');
  }
}

function arraysEqual(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b)) return false;
  if (a.length !== b.length) return false;
  for (var i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

// ---- fixtures -------------------------------------------------------------

var THIRD_PARTY_PACK = {
  pack_name: "Cartoon Studio",
  pack_version: "2.1.0",
  ora_compatibility: ">=0.7.0",
  author: { name: "An Outside Author", url: "https://example.com/cartoon",
            email: "author@example.com" },
  description: "Comic-book toolbar with speech-bubble macro and panel layouts.",
  toolbars: [
    {
      id: "cartoon-tb",
      label: "Cartoon",
      default_dock: "left",
      items: [
        { id: "select", icon: "mouse-pointer", label: "Select", shortcut: "V",
          binding: "tool:select" },
        { id: "speech",  icon: "message-circle", label: "Speech bubble",
          binding: "macro:add-speech-bubble" },
        { id: "img-gen", icon: "sparkles", label: "Generate image",
          binding: "capability:image_generates" }
      ]
    }
  ],
  macros: [
    {
      id: "add-speech-bubble",
      label: "Add speech bubble",
      icon: "message-circle",
      steps: [
        { tool: "shape:speech_bubble", params: { click_to_place: true } },
        { tool: "text_input",          params: { var: "dialogue", label: "Dialogue" } },
        { tool: "set_bubble_text",     params: { text: "{{dialogue}}" } }
      ]
    },
    {
      id: "stylize-panel",
      label: "Stylize panel",
      icon: "wand-2",
      steps: [
        { capability: "image_edits",     params: { instruction: "comic-book ink and color" } },
        { capability: "image_describes", params: {} }
      ]
    }
  ],
  prompt_templates: [
    {
      id: "cartoon-bg",
      slash_command: "/cartoon-bg",
      label: "Cartoon background",
      template: "A {{style|Hergé}}-style background of {{scene}}",
      variables: [
        { name: "scene", type: "text" },
        { name: "style", type: "text", default: "Hergé" }
      ],
      capability_route: "image_generates"
    },
    {
      id: "panel-caption",
      label: "Panel caption",
      template: "Write a one-sentence caption for: {{description}}",
      variables: [{ name: "description", type: "text" }],
      gear_preference: 2
    }
  ],
  composition_templates: [
    {
      id: "4-panel",
      label: "4-panel comic strip",
      thumbnail: "<svg viewBox='0 0 100 60'><rect x='2' y='2' width='22' height='56'/></svg>",
      canvas_state: { version: 1, layers: [], view: { zoom: 1, pan_x: 0, pan_y: 0 } }
    }
  ]
};

// ---- TEST 1 — capability scope (pure function) ----------------------------

process.stdout.write('\n--- TEST 1: capability scope per Toolbar Pack Format §10 ---\n');

(function () {
  var scope = reviewMod.computeCapabilityScope(THIRD_PARTY_PACK);
  // Toolbar item: capability:image_generates
  // Macro steps: image_edits, image_describes
  // Prompt template: image_generates (already present, dedup)
  check('1a. computeCapabilityScope returns sorted, deduplicated slot list',
    arraysEqual(scope, ['image_describes', 'image_edits', 'image_generates']),
    scope);

  var emptyScope = reviewMod.computeCapabilityScope({
    pack_name: "T", pack_version: "1.0.0",
    toolbars: [{ id: "t", label: "T",
      items: [{ id: "i", icon: "circle", label: "L", binding: "tool:select" }] }]
  });
  check('1b. capability scope is empty when no slots are invoked',
    Array.isArray(emptyScope) && emptyScope.length === 0, emptyScope);

  var nullSafe = reviewMod.computeCapabilityScope({});
  check('1c. computeCapabilityScope handles missing arrays',
    Array.isArray(nullSafe) && nullSafe.length === 0, nullSafe);
})();

// ---- TEST 2 — show() renders all four categories --------------------------

process.stdout.write('\n--- TEST 2: §13.7 — modal shows all four categories ---\n');

(async function () {
  reviewMod.init();
  // Don't await yet — we need to inspect the DOM while the modal is open.
  var pending = reviewMod.show(THIRD_PARTY_PACK,
    { source: '/Users/oracle/Downloads/cartoon-studio.pack.json' });

  var modal = doc.querySelector('#ora-pack-install-review-modal');
  check('2a. modal element is mounted on show()', !!modal, !!modal);
  check('2b. modal is visible (hidden flag false)', modal && modal.hidden === false,
    modal ? modal.hidden : null);

  var body = modal && modal.querySelector('#ora-pack-install-review-modal-body');
  var html = body ? body._innerHTML : '';

  check('2c. body shows pack name and version',
    html.indexOf('Cartoon Studio') >= 0 && html.indexOf('v2.1.0') >= 0);
  check('2d. body shows author info', html.indexOf('An Outside Author') >= 0);
  check('2e. body shows author URL', html.indexOf('https://example.com/cartoon') >= 0);
  check('2f. body shows author email', html.indexOf('author@example.com') >= 0);
  check('2g. body shows source path',
    html.indexOf('/Users/oracle/Downloads/cartoon-studio.pack.json') >= 0);

  check('2h. body has Toolbars section heading',           html.indexOf('Toolbars') >= 0);
  check('2i. body has Macros section heading',             html.indexOf('Macros') >= 0);
  check('2j. body has Prompt templates section heading',   html.indexOf('Prompt templates') >= 0);
  check('2k. body has Composition templates section heading', html.indexOf('Composition templates') >= 0);

  // Toolbar contents.
  check('2l. body lists the cartoon toolbar', html.indexOf('cartoon-tb') >= 0);
  check('2m. body lists the toolbar items',
    html.indexOf('mouse-pointer') >= 0 && html.indexOf('Speech bubble') >= 0
    && html.indexOf('Generate image') >= 0);

  // Macro contents — both macros + their step bindings.
  check('2n. body lists the speech-bubble macro',
    html.indexOf('add-speech-bubble') >= 0
    && html.indexOf('shape:speech_bubble') >= 0
    && html.indexOf('text_input') >= 0
    && html.indexOf('set_bubble_text') >= 0);
  check('2o. body lists the stylize-panel macro and its capability steps',
    html.indexOf('stylize-panel') >= 0
    && html.indexOf('capability: image_edits') >= 0
    && html.indexOf('capability: image_describes') >= 0);

  // Prompt template contents.
  check('2p. body shows the cartoon-bg template + its prompt body',
    html.indexOf('cartoon-bg') >= 0
    && html.indexOf('/cartoon-bg') >= 0
    && html.indexOf('background of') >= 0);
  check('2q. body shows the panel-caption template + its prompt body',
    html.indexOf('panel-caption') >= 0
    && html.indexOf('one-sentence caption') >= 0);

  // Composition template contents.
  check('2r. body shows the 4-panel composition + thumbnail SVG',
    html.indexOf('4-panel') >= 0 && html.indexOf('viewBox') >= 0);

  // Capability scope reflects macros' invocations (acceptance criterion).
  check('2s. body shows the capability-scope section',
    html.indexOf('Capability scope') >= 0);
  check('2t. capability scope reflects macros\' invocations (image_edits)',
    html.indexOf('image_edits') >= 0);
  check('2u. capability scope reflects macros\' invocations (image_describes)',
    html.indexOf('image_describes') >= 0);
  check('2v. capability scope reflects toolbar binding (image_generates)',
    html.indexOf('image_generates') >= 0);

  // ---- TEST 3 — install only fires after explicit click -----------------
  process.stdout.write('\n--- TEST 3: install fires only on explicit click ---\n');

  // Probe state before any click — promise must not have resolved.
  var resolvedYet = { value: false, accepted: null };
  pending.then(function (r) { resolvedYet.value = true; resolvedYet.accepted = r.accepted; });
  await Promise.resolve(); await Promise.resolve();
  check('3a. promise has NOT resolved before any user action',
    resolvedYet.value === false, resolvedYet);

  // Pressing Escape resolves with accepted:false (cancel-equivalent), not install.
  doc._fireKey('Escape');
  await Promise.resolve(); await Promise.resolve();
  check('3b. Escape closes the modal as cancel (accepted=false)',
    resolvedYet.value === true && resolvedYet.accepted === false, resolvedYet);

  // Re-open and verify Install button click resolves accepted:true.
  var pending2 = reviewMod.show(THIRD_PARTY_PACK);
  var resolvedYet2 = { value: false, accepted: null };
  pending2.then(function (r) { resolvedYet2.value = true; resolvedYet2.accepted = r.accepted; });
  await Promise.resolve();
  check('3c. promise has NOT resolved on second show (no click yet)',
    resolvedYet2.value === false, resolvedYet2);

  var installBtn = doc.querySelector('.ora-pack-install-review__btn--install');
  check('3d. Install button is present',
    !!installBtn && installBtn.dataset && installBtn.dataset.action === 'install',
    installBtn ? installBtn.dataset : null);

  // Find the modal root (it owns the click delegation listener).
  var modal2 = doc.querySelector('#ora-pack-install-review-modal');
  modal2.dispatchEvent({ type: 'click', target: installBtn, defaultPrevented: false,
                         preventDefault: function () { this.defaultPrevented = true; } });
  await Promise.resolve(); await Promise.resolve();
  check('3e. Install click resolves promise with accepted=true',
    resolvedYet2.value === true && resolvedYet2.accepted === true, resolvedYet2);

  // Re-open and verify Cancel button click resolves accepted:false.
  var pending3 = reviewMod.show(THIRD_PARTY_PACK);
  var resolvedYet3 = { value: false, accepted: null };
  pending3.then(function (r) { resolvedYet3.value = true; resolvedYet3.accepted = r.accepted; });
  await Promise.resolve();
  var cancelBtn = doc.querySelector('.ora-pack-install-review__btn--cancel');
  var modal3 = doc.querySelector('#ora-pack-install-review-modal');
  modal3.dispatchEvent({ type: 'click', target: cancelBtn, defaultPrevented: false,
                         preventDefault: function () { this.defaultPrevented = true; } });
  await Promise.resolve(); await Promise.resolve();
  check('3f. Cancel click resolves promise with accepted=false',
    resolvedYet3.value === true && resolvedYet3.accepted === false, resolvedYet3);

  // ---- summary ---------------------------------------------------------
  process.stdout.write('\n--- summary ---\n');
  process.stdout.write('  passed: ' + passCount + '\n');
  process.stdout.write('  failed: ' + failCount + '\n');
  if (failCount > 0) {
    process.stdout.write('\nfailures:\n');
    for (var i = 0; i < failures.length; i++) {
      process.stdout.write('  - ' + failures[i].name + '\n');
    }
    process.exit(1);
  } else {
    process.exit(0);
  }
})();
