#!/usr/bin/env node
/* test-keyboard-shortcuts.js
 *
 * Focused coverage for the runtime shortcut registry:
 *   - platform display
 *   - user overrides
 *   - duplicate / reserved conflict detection
 *   - plus-key aliases
 *
 * Run:
 *   node ~/ora/server/static/tests/test-keyboard-shortcuts.js
 */

'use strict';

var fs = require('fs');
var path = require('path');
var vm = require('vm');

var SRC = path.resolve(__dirname, '..', 'keyboard-shortcuts.js');

function assert(name, cond) {
  if (!cond) throw new Error('FAIL: ' + name);
  console.log('PASS: ' + name);
}

function makeContext() {
  var listeners = {};
  var ctx = {
    console: console,
    navigator: { platform: 'MacIntel' },
    document: {
      readyState: 'loading',
      addEventListener: function (type, fn) {
        listeners[type] = fn;
      },
    },
    fetch: function () {
      return Promise.resolve({
        ok: true,
        json: function () {
          return Promise.resolve({ settings: {} });
        },
      });
    },
  };
  ctx.window = ctx;
  ctx.globalThis = ctx;
  ctx._listeners = listeners;
  return ctx;
}

function evt(key, opts) {
  opts = opts || {};
  return {
    key: key,
    metaKey: !!opts.metaKey,
    ctrlKey: !!opts.ctrlKey,
    altKey: !!opts.altKey,
    shiftKey: !!opts.shiftKey,
    target: { tagName: 'DIV', isContentEditable: false },
  };
}

var ctx = makeContext();
vm.runInNewContext(fs.readFileSync(SRC, 'utf8'), ctx, { filename: SRC });

var K = ctx.OraKeyboardShortcuts;
assert('registry exported', !!K);

K.refresh({ keyboard: { shortcuts: { app_open_sidebar: 'Mod+Alt+K' } } });
assert('platform display uses Cmd/Option',
  K.displayFor('app_open_sidebar') === 'Cmd+Option+K');
assert('override matches remapped chord',
  K.matches('app_open_sidebar', evt('k', { metaKey: true, altKey: true })));
assert('override stops old chord',
  !K.matches('app_open_sidebar', evt('k', { metaKey: true })));

var dup = K.validateShortcut(
  'app_new_conversation',
  'Mod+Alt+K',
  { keyboard: { shortcuts: { app_open_sidebar: 'Mod+Alt+K' } } }
);
assert('duplicate overlapping global shortcut blocked',
  dup.ok === false && dup.errors.length > 0);

var reserved = K.validateShortcut('app_new_conversation', 'Mod+W', {});
assert('reserved browser shortcut blocked',
  reserved.ok === false && reserved.errors.length > 0);

K.refresh({});
assert('zoom in matches equals alias',
  K.matches('visual_zoom_in', evt('=')));
assert('zoom in matches shifted plus alias',
  K.matches('visual_zoom_in', evt('+', { shiftKey: true })));

K.refresh({ keyboard: { shortcuts: { visual_zoom_in: '' } } });
assert('empty override preserves default aliases',
  K.matches('visual_zoom_in', evt('=')));

console.log('keyboard-shortcuts tests passed');
