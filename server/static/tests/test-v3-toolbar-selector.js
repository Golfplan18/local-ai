#!/usr/bin/env node
/* test-v3-toolbar-selector.js — V3 specialty-pack toolbar launcher (2026-05-01)
 *
 * Coverage for v3-toolbar-selector.js + the mount/unmount surface added to
 * v3-pack-toolbars.js. Boots both modules into a sandboxed window with a
 * mocked DOM, OraVisualToolbar registry, and dock controller. Verifies:
 *
 *   • listAvailablePacks excludes ora-universal and includes specialty packs.
 *   • mountPack / unmountPack toggle the dock arrangement.
 *   • Active set persists to localStorage across calls.
 *   • mountAll re-mounts only the previously-active set on reboot.
 *   • The selector popover renders one row per available pack with the
 *     correct active checkmark, and clicking a row toggles dock state.
 *   • Outside-click / Escape close the popover.
 *   • Shift+T toggles; plain T does not; Shift+T inside an INPUT does not.
 *
 * Run:
 *   node ~/ora/server/static/tests/test-v3-toolbar-selector.js
 */

'use strict';

var fs   = require('fs');
var path = require('path');
var vm   = require('vm');

var PACKS_SRC    = path.resolve(__dirname, '..', 'js', 'v3-pack-toolbars.js');
var SELECTOR_SRC = path.resolve(__dirname, '..', 'js', 'v3-toolbar-selector.js');

// ── Minimal DOM mock ───────────────────────────────────────────────────────

function makeEl(tagName) {
  var el = {
    tagName: (tagName || 'DIV').toUpperCase(),
    children: [],
    childNodes: [],
    style: {},
    dataset: {},
    classList: null,  // populated below so it can close over `el`
    _attrs: {},
    _listeners: {},
    parentNode: null,
    isContentEditable: false,
    offsetWidth: 240,
    offsetHeight: 200,
    innerHTML_set: '',
  };
  Object.defineProperty(el, 'innerHTML', {
    get: function () { return el.innerHTML_set; },
    set: function (v) {
      el.innerHTML_set = v;
      if (v === '') {
        el.children.forEach(function (c) { c.parentNode = null; });
        el.children = [];
        el.childNodes = [];
      }
    }
  });
  // Reflect `el.id` / `el.className` to underlying _attrs map so direct
  // property assignment (`el.id = 'foo'`) behaves like setAttribute.
  Object.defineProperty(el, 'id', {
    get: function () { return el._attrs.id || ''; },
    set: function (v) { el._attrs.id = String(v); }
  });
  Object.defineProperty(el, 'className', {
    get: function () { return el._attrs['class'] || ''; },
    set: function (v) { el._attrs['class'] = String(v); }
  });
  // classList that reflects both add()/remove() ops and direct className
  // assignments. contains() checks both — so `el.className = 'foo'` then
  // `el.classList.contains('foo')` returns true, matching browser behavior.
  var classListSet = {};
  el.classList = {
    add:    function (c) { classListSet[c] = true; },
    remove: function (c) { delete classListSet[c]; },
    contains: function (c) {
      if (classListSet[c]) return true;
      var cn = el._attrs['class'] || '';
      return cn.split(/\s+/).indexOf(c) >= 0;
    },
    toggle: function (c) {
      if (classListSet[c]) delete classListSet[c];
      else classListSet[c] = true;
    }
  };
  el.setAttribute = function (k, v) { el._attrs[k] = String(v); };
  el.getAttribute = function (k) { return el._attrs.hasOwnProperty(k) ? el._attrs[k] : null; };
  el.removeAttribute = function (k) { delete el._attrs[k]; };
  el.appendChild = function (child) {
    el.children.push(child); el.childNodes.push(child); child.parentNode = el; return child;
  };
  el.removeChild = function (child) {
    var i = el.children.indexOf(child);
    if (i >= 0) { el.children.splice(i, 1); el.childNodes.splice(i, 1); child.parentNode = null; }
    return child;
  };
  el.contains = function (other) {
    if (!other) return false;
    if (other === el) return true;
    var n = other;
    while (n) { if (n === el) return true; n = n.parentNode; }
    return false;
  };
  el.querySelector = function (sel) {
    if (sel && sel[0] === '.') {
      var cls = sel.slice(1);
      function walk(n) {
        if (!n.children) return null;
        for (var i = 0; i < n.children.length; i++) {
          var c = n.children[i];
          if (c.classList && c.classList.contains(cls)) return c;
          var r = walk(c);
          if (r) return r;
        }
        return null;
      }
      return walk(el);
    }
    return null;
  };
  el.addEventListener = function (event, fn) {
    if (!el._listeners[event]) el._listeners[event] = [];
    el._listeners[event].push(fn);
  };
  el.removeEventListener = function (event, fn) {
    var arr = el._listeners[event];
    if (!arr) return;
    var i = arr.indexOf(fn);
    if (i >= 0) arr.splice(i, 1);
  };
  el.click = function () {
    (el._listeners['click'] || []).forEach(function (fn) {
      fn({ preventDefault: function () {}, target: el, currentTarget: el });
    });
  };
  el.dispatchEvent = function (e) {
    var arr = el._listeners[e.type] || [];
    arr.forEach(function (fn) { fn(e); });
    // Bubble to document via window-level listeners — handled by document mock.
    return true;
  };
  el.getBoundingClientRect = function () {
    return { left: 100, top: 100, right: 132, bottom: 132, width: 32, height: 32, x: 100, y: 100 };
  };
  return el;
}

function makeDoc() {
  var byId = {};
  var listeners = {};
  var body = makeEl('body');
  var doc = {
    body: body,
    readyState: 'complete',
    createElement: function (tag) { return makeEl(tag); },
    getElementById: function (id) {
      if (byId[id]) return byId[id];
      // Fallback: walk the body tree so dynamically-appended hosts (e.g.,
      // the selector popover) are findable by their id attribute.
      function walk(el) {
        if (!el) return null;
        if (el._attrs && el._attrs.id === id) return el;
        if (el.children) {
          for (var i = 0; i < el.children.length; i++) {
            var r = walk(el.children[i]);
            if (r) return r;
          }
        }
        return null;
      }
      return walk(body);
    },
    querySelector: function (sel) {
      // Minimal attribute-selector matcher for `[attr="value"]` and class
      // `.foo` selectors. Walks the document body tree.
      var attrMatch = /^\[([^=]+)=["']?([^"'\]]+)["']?\]$/.exec(sel || '');
      var classMatch = (sel && sel[0] === '.') ? sel.slice(1) : null;
      function walk(el) {
        if (!el) return null;
        if (attrMatch && el._attrs && el._attrs[attrMatch[1]] === attrMatch[2]) return el;
        if (classMatch && el.classList && el.classList.contains(classMatch)) return el;
        if (el.children) {
          for (var i = 0; i < el.children.length; i++) {
            var r = walk(el.children[i]);
            if (r) return r;
          }
        }
        return null;
      }
      return walk(body);
    },
    addEventListener: function (ev, fn) {
      if (!listeners[ev]) listeners[ev] = [];
      listeners[ev].push(fn);
    },
    removeEventListener: function (ev, fn) {
      var arr = listeners[ev]; if (!arr) return;
      var i = arr.indexOf(fn); if (i >= 0) arr.splice(i, 1);
    },
    dispatchEvent: function (e) {
      var arr = (listeners[e.type] || []).slice();
      arr.forEach(function (fn) { fn(e); });
      return true;
    },
    _registerEl: function (el) { if (el && el._attrs && el._attrs.id) byId[el._attrs.id] = el; },
    _listeners: listeners,
  };
  // Override setAttribute to keep getElementById in sync with id changes.
  return doc;
}

// ── OraVisualToolbar mock ─────────────────────────────────────────────────

function makeToolbarRegistry(definitions) {
  var defs = {};
  Object.keys(definitions || {}).forEach(function (k) { defs[k] = definitions[k]; });
  return {
    list: function () { return Object.keys(defs); },
    get:  function (id) { return defs[id]; },
    register: function (def) { defs[def.id] = def; },
    render: function (def, opts) {
      // Return a minimal "controller" with an el, an id, and destroy.
      return {
        id: def.id,
        definition: def,
        el: { tagName: 'DIV', _attrs: {}, getAttribute: function () { return null; } },
        destroy: function () { /* no-op */ }
      };
    }
  };
}

// ── Dock controller mock ──────────────────────────────────────────────────

function makeDock() {
  var arrangement = {};
  return {
    getArrangement: function () {
      var copy = {};
      Object.keys(arrangement).forEach(function (k) { copy[k] = { edge: arrangement[k] }; });
      return copy;
    },
    mount: function (ctl, opts) { arrangement[opts.id] = opts.defaultEdge || 'left'; },
    unmount: function (id) { delete arrangement[id]; },
    _arrangement: arrangement
  };
}

function makePanel() {
  // panel.el needs to behave like a real DOM element since the selector
  // appends its popover host into it (post-rebuild: popover is scoped to
  // the visual pane, not document.body).
  var paneEl = makeEl('div');
  paneEl.setAttribute('class', 'right-pane visual-panel');
  // Provide a getBoundingClientRect override so positioning math has
  // realistic numbers to clamp against.
  paneEl.getBoundingClientRect = function () {
    return { left: 600, top: 100, right: 1200, bottom: 700,
             width: 600, height: 600, x: 600, y: 100 };
  };
  return { _dockController: makeDock(), el: paneEl };
}

// ── localStorage mock ─────────────────────────────────────────────────────

function makeLocalStorage() {
  var store = {};
  return {
    getItem: function (k) { return store.hasOwnProperty(k) ? store[k] : null; },
    setItem: function (k, v) { store[k] = String(v); },
    removeItem: function (k) { delete store[k]; },
    clear: function () { store = {}; },
    _peek: function () { return store; }
  };
}

// ── Boot both modules into a shared sandbox ───────────────────────────────

function boot() {
  var doc = makeDoc();
  var localStorage = makeLocalStorage();

  // Spine button — referenced by the selector via getElementById.
  var spineBtn = makeEl('button');
  spineBtn.setAttribute('id', 'spineToolbarSelector');
  doc._registerEl(spineBtn);

  var registry = makeToolbarRegistry({
    'ora-universal':     { id: 'ora-universal',     label: 'Universal',         default_dock: 'top'  },
    'cartoon-studio':    { id: 'cartoon-studio',    label: 'Cartoon Studio',    default_dock: 'left' },
    'mood-board':        { id: 'mood-board',        label: 'Mood Board',        default_dock: 'left' },
    'photo-editor':      { id: 'photo-editor',      label: 'Photo Editor',      default_dock: 'left' },
    'diagram-thinking':  { id: 'diagram-thinking',  label: 'Diagram Thinking',  default_dock: 'left' },
  });

  var sandbox = {
    window: {
      OraVisualToolbar: registry,
      OraCanvas: null,
      localStorage: localStorage,
      innerWidth: 1280,
      innerHeight: 800,
    },
    document: doc,
    console: { log: function () {}, info: function () {}, warn: function () {}, error: function () {} },
    setTimeout: function (fn) { return 0; },
    clearTimeout: function () {},
    CustomEvent: function (type, opts) {
      this.type = type;
      this.detail = opts && opts.detail;
      this.preventDefault = function () {};
    },
    Date: Date, Math: Math, Object: Object, Array: Array, JSON: JSON, WeakMap: WeakMap,
    isFinite: isFinite, parseInt: parseInt, parseFloat: parseFloat,
  };
  vm.createContext(sandbox);
  // Make `localStorage` directly accessible to module code that does
  // `window.localStorage` (already covered) and bare `localStorage`.
  sandbox.localStorage = localStorage;

  vm.runInContext(fs.readFileSync(PACKS_SRC,    'utf8'), sandbox);
  vm.runInContext(fs.readFileSync(SELECTOR_SRC, 'utf8'), sandbox);

  return {
    sandbox: sandbox,
    doc: doc,
    registry: registry,
    localStorage: localStorage,
    spineBtn: spineBtn,
    Packs: sandbox.window.OraV3PackToolbars,
    Selector: sandbox.window.OraV3ToolbarSelector,
    setActivePanel: function (panel) {
      sandbox.window.OraCanvas = { panel: panel };
      // Attach the panel element to the document body so the popover host
      // (which the selector appends inside panel.el) is findable via
      // document.getElementById walking from body.
      if (panel && panel.el && panel.el.parentNode == null) {
        doc.body.appendChild(panel.el);
      }
    },
  };
}

// ── Test framework ─────────────────────────────────────────────────────────

var pass = 0, fail = 0;
function test(name, fn) {
  try { fn(); pass++; console.log('  ✓ ' + name); }
  catch (e) {
    fail++;
    console.log('  ✗ ' + name);
    console.log('    ' + (e && e.stack ? e.stack : e));
  }
}
function assertEqual(a, b, msg) {
  var ok = (a === b) || (a && b && JSON.stringify(a) === JSON.stringify(b));
  if (!ok) throw new Error((msg || 'assertion')
                           + ': expected ' + JSON.stringify(b)
                           + ', got ' + JSON.stringify(a));
}
function assertTrue(c, m) { if (!c) throw new Error(m || 'expected truthy'); }
function assertFalse(c, m) { if (c) throw new Error(m || 'expected falsy'); }

// ─────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────

console.log('test-v3-toolbar-selector.js — pack mount/unmount + selector popover');

// ── Mount/unmount API on OraV3PackToolbars ───────────────────────────────

test('listAvailablePacks excludes ora-universal', function () {
  var b = boot();
  var ids = b.Packs.listAvailablePacks().map(function (p) { return p.id; });
  assertFalse(ids.indexOf('ora-universal') >= 0, 'universal must not appear');
  assertTrue(ids.indexOf('cartoon-studio') >= 0,   'cartoon-studio missing');
  assertTrue(ids.indexOf('mood-board') >= 0,       'mood-board missing');
  assertTrue(ids.indexOf('photo-editor') >= 0,     'photo-editor missing');
  assertTrue(ids.indexOf('diagram-thinking') >= 0, 'diagram-thinking missing');
  assertEqual(ids.length, 4);
});

test('listAvailablePacks carries label + default_dock', function () {
  var b = boot();
  var packs = b.Packs.listAvailablePacks();
  var cartoon = packs.filter(function (p) { return p.id === 'cartoon-studio'; })[0];
  assertEqual(cartoon.label, 'Cartoon Studio');
  assertEqual(cartoon.default_dock, 'left');
});

test('mountPack docks a pack toolbar to its default edge', function () {
  var b = boot();
  var panel = makePanel();
  var ok = b.Packs.mountPack(panel, 'cartoon-studio');
  assertTrue(ok, 'mountPack should return true');
  assertTrue(b.Packs.isMounted(panel, 'cartoon-studio'));
  assertEqual(panel._dockController._arrangement['cartoon-studio'], 'left');
});

test('mountPack rejects ora-universal', function () {
  var b = boot();
  var panel = makePanel();
  assertFalse(b.Packs.mountPack(panel, 'ora-universal'));
});

test('mountPack on unknown id returns false', function () {
  var b = boot();
  var panel = makePanel();
  assertFalse(b.Packs.mountPack(panel, 'no-such-pack'));
});

test('mountPack twice is idempotent', function () {
  var b = boot();
  var panel = makePanel();
  b.Packs.mountPack(panel, 'cartoon-studio');
  var ok = b.Packs.mountPack(panel, 'cartoon-studio');
  assertTrue(ok, 'second mount should still succeed');
  // Arrangement still has it.
  assertTrue(b.Packs.isMounted(panel, 'cartoon-studio'));
});

test('unmountPack removes the toolbar from the dock', function () {
  var b = boot();
  var panel = makePanel();
  b.Packs.mountPack(panel, 'cartoon-studio');
  assertTrue(b.Packs.isMounted(panel, 'cartoon-studio'));
  b.Packs.unmountPack(panel, 'cartoon-studio');
  assertFalse(b.Packs.isMounted(panel, 'cartoon-studio'));
});

test('unmountPack on a not-mounted pack is a no-op (returns true)', function () {
  var b = boot();
  var panel = makePanel();
  var ok = b.Packs.unmountPack(panel, 'cartoon-studio');
  assertTrue(ok);
});

// ── Persistence ────────────────────────────────────────────────────────────

test('mountPack persists active set to localStorage', function () {
  var b = boot();
  var panel = makePanel();
  b.Packs.mountPack(panel, 'cartoon-studio');
  b.Packs.mountPack(panel, 'mood-board');
  var saved = JSON.parse(b.localStorage.getItem('ora.v3.activePackToolbars.v1'));
  assertEqual(saved.sort(), ['cartoon-studio', 'mood-board']);
});

test('unmountPack removes from persisted active set', function () {
  var b = boot();
  var panel = makePanel();
  b.Packs.mountPack(panel, 'cartoon-studio');
  b.Packs.mountPack(panel, 'mood-board');
  b.Packs.unmountPack(panel, 'mood-board');
  var saved = JSON.parse(b.localStorage.getItem('ora.v3.activePackToolbars.v1'));
  assertEqual(saved, ['cartoon-studio']);
});

test('mountAll re-mounts only previously-active packs (post-reboot scenario)', function () {
  // Simulate a prior session that left cartoon-studio active.
  var b1 = boot();
  var p1 = makePanel();
  b1.Packs.mountPack(p1, 'cartoon-studio');
  var saved = b1.localStorage.getItem('ora.v3.activePackToolbars.v1');

  // Reboot — fresh sandbox, but seed the localStorage with the prior state.
  var b2 = boot();
  b2.localStorage.setItem('ora.v3.activePackToolbars.v1', saved);
  var p2 = makePanel();
  b2.Packs.mountAll(p2);

  assertTrue(b2.Packs.isMounted(p2, 'cartoon-studio'),
             'cartoon-studio should be re-mounted from localStorage');
  assertFalse(b2.Packs.isMounted(p2, 'mood-board'),
              'mood-board was never active; should NOT auto-mount');
  assertFalse(b2.Packs.isMounted(p2, 'photo-editor'),
              'photo-editor was never active; should NOT auto-mount');
  assertFalse(b2.Packs.isMounted(p2, 'diagram-thinking'),
              'diagram-thinking was never active; should NOT auto-mount');
});

test('mountAll on a fresh user (empty localStorage) docks nothing', function () {
  var b = boot();
  var panel = makePanel();
  b.Packs.mountAll(panel);
  assertEqual(Object.keys(panel._dockController._arrangement).length, 0,
              'no auto-mounts on first boot');
});

// ── Selector popover ──────────────────────────────────────────────────────

test('open() shows popover with one row per available pack', function () {
  var b = boot();
  var panel = makePanel();
  b.setActivePanel(panel);

  b.Selector.open(b.spineBtn, panel);
  assertTrue(b.Selector.isOpen(), 'popover should be open');

  var host = b.doc.getElementById('ora-toolbar-selector-popover');
  assertTrue(host !== null);
  var bodyEl = host.querySelector('.ora-toolbar-selector-body');
  assertEqual(bodyEl.children.length, 4, 'should render 4 pack rows');
});

test('popover is appended INSIDE the visual pane element (scoping rule)', function () {
  // The user-facing rule: nothing visual-pane-related lives outside the
  // pane bounds. The popover host must be a descendant of panel.el — NOT
  // a child of document.body — so it inherits the pane's hide-on-blur
  // lifecycle and is visually clipped to the pane.
  var b = boot();
  var panel = makePanel();
  b.setActivePanel(panel);
  b.Selector.open(b.spineBtn, panel);

  var host = b.doc.getElementById('ora-toolbar-selector-popover');
  assertTrue(host !== null);
  // Walk up from host: must hit panel.el before hitting body.
  var n = host.parentNode, hitPanelFirst = false;
  while (n) {
    if (n === panel.el) { hitPanelFirst = true; break; }
    if (n === b.doc.body) break;
    n = n.parentNode;
  }
  assertTrue(hitPanelFirst,
             'popover host should be a descendant of panel.el, not document.body');
});

test('row click on inactive pack mounts it and updates the row', function () {
  var b = boot();
  var panel = makePanel();
  b.setActivePanel(panel);
  b.Selector.open(b.spineBtn, panel);

  var host = b.doc.getElementById('ora-toolbar-selector-popover');
  var bodyEl = host.querySelector('.ora-toolbar-selector-body');
  var cartoonRow = bodyEl.children.filter(function (r) {
    return r.getAttribute('data-pack-id') === 'cartoon-studio';
  })[0];
  assertEqual(cartoonRow.getAttribute('aria-pressed'), 'false');

  cartoonRow.click();

  assertTrue(b.Packs.isMounted(panel, 'cartoon-studio'),
             'cartoon-studio should be mounted after click');
  // Row re-renders via the ora:pack-toolbar-changed event.
  var refreshed = bodyEl.children.filter(function (r) {
    return r.getAttribute('data-pack-id') === 'cartoon-studio';
  })[0];
  assertEqual(refreshed.getAttribute('aria-pressed'), 'true');
});

test('row click on an already-active pack unmounts it', function () {
  var b = boot();
  var panel = makePanel();
  b.setActivePanel(panel);
  b.Packs.mountPack(panel, 'cartoon-studio');
  b.Selector.open(b.spineBtn, panel);

  var host = b.doc.getElementById('ora-toolbar-selector-popover');
  var bodyEl = host.querySelector('.ora-toolbar-selector-body');
  var row = bodyEl.children.filter(function (r) {
    return r.getAttribute('data-pack-id') === 'cartoon-studio';
  })[0];
  assertEqual(row.getAttribute('aria-pressed'), 'true');

  row.click();
  assertFalse(b.Packs.isMounted(panel, 'cartoon-studio'));
});

test('close() hides the popover', function () {
  var b = boot();
  var panel = makePanel(); b.setActivePanel(panel);
  b.Selector.open(b.spineBtn, panel);
  assertTrue(b.Selector.isOpen());
  b.Selector.close();
  assertFalse(b.Selector.isOpen());
});

test('toggle() opens then closes', function () {
  var b = boot();
  var panel = makePanel(); b.setActivePanel(panel);
  assertFalse(b.Selector.isOpen());
  b.Selector.toggle(b.spineBtn, panel);
  assertTrue(b.Selector.isOpen());
  b.Selector.toggle(b.spineBtn, panel);
  assertFalse(b.Selector.isOpen());
});

test('Escape key closes the popover', function () {
  var b = boot();
  var panel = makePanel(); b.setActivePanel(panel);
  b.Selector.open(b.spineBtn, panel);
  assertTrue(b.Selector.isOpen());
  // Fire keydown on the document.
  var listeners = (b.doc._listeners.keydown || []).slice();
  listeners.forEach(function (fn) {
    fn({ key: 'Escape', preventDefault: function () {}, target: b.doc.body });
  });
  assertFalse(b.Selector.isOpen());
});

// ── Keyboard shortcut ─────────────────────────────────────────────────────

test('Shift+T toggles popover', function () {
  var b = boot();
  var panel = makePanel(); b.setActivePanel(panel);
  assertFalse(b.Selector.isOpen());
  b.Selector._shortcutHandler({
    key: 't', shiftKey: true, ctrlKey: false, metaKey: false, altKey: false,
    target: b.doc.body, preventDefault: function () {}
  });
  assertTrue(b.Selector.isOpen());
});

test('plain T (no shift) does NOT toggle', function () {
  var b = boot();
  var panel = makePanel(); b.setActivePanel(panel);
  b.Selector._shortcutHandler({
    key: 't', shiftKey: false, ctrlKey: false, metaKey: false, altKey: false,
    target: b.doc.body, preventDefault: function () {}
  });
  assertFalse(b.Selector.isOpen());
});

test('Shift+T inside an INPUT does NOT toggle', function () {
  var b = boot();
  var panel = makePanel(); b.setActivePanel(panel);
  var input = makeEl('input');
  b.Selector._shortcutHandler({
    key: 't', shiftKey: true, ctrlKey: false, metaKey: false, altKey: false,
    target: input, preventDefault: function () {}
  });
  assertFalse(b.Selector.isOpen());
});

test('Shift+T inside a TEXTAREA does NOT toggle', function () {
  var b = boot();
  var panel = makePanel(); b.setActivePanel(panel);
  var ta = makeEl('textarea');
  b.Selector._shortcutHandler({
    key: 't', shiftKey: true, ctrlKey: false, metaKey: false, altKey: false,
    target: ta, preventDefault: function () {}
  });
  assertFalse(b.Selector.isOpen());
});

test('Shift+T on contenteditable element does NOT toggle', function () {
  var b = boot();
  var panel = makePanel(); b.setActivePanel(panel);
  var div = makeEl('div');
  div.isContentEditable = true;
  b.Selector._shortcutHandler({
    key: 't', shiftKey: true, ctrlKey: false, metaKey: false, altKey: false,
    target: div, preventDefault: function () {}
  });
  assertFalse(b.Selector.isOpen());
});

test('Cmd+Shift+T does NOT trigger (modifier conflict)', function () {
  var b = boot();
  var panel = makePanel(); b.setActivePanel(panel);
  b.Selector._shortcutHandler({
    key: 't', shiftKey: true, ctrlKey: false, metaKey: true, altKey: false,
    target: b.doc.body, preventDefault: function () {}
  });
  assertFalse(b.Selector.isOpen());
});

// ── No-active-panel safety ────────────────────────────────────────────────

test('clicking a row when no panel is active is a safe no-op', function () {
  var b = boot();
  // Do NOT setActivePanel — leave OraCanvas null. The popover falls back
  // to document.body for parent (no visual pane to anchor to). Row clicks
  // should warn but not throw.
  b.Selector.open(b.spineBtn);
  var host = b.doc.getElementById('ora-toolbar-selector-popover');
  var bodyEl = host.querySelector('.ora-toolbar-selector-body');
  var row = bodyEl.children[0];
  // Should warn and return without throwing.
  row.click();
  // Nothing should have been mounted (no panel exists to mount to).
  // Just verify no exception bubbled up.
  assertTrue(true);
});

// ── result ────────────────────────────────────────────────────────────────

console.log('\n  ' + pass + ' passed, ' + fail + ' failed');
process.exit(fail === 0 ? 0 : 1);
