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
var VIDEO_SRC = path.resolve(
  __dirname, '..', '..', '..', 'plugins', 'video', 'static', 'video-shortcuts.js'
);

function assert(name, cond) {
  if (!cond) throw new Error('FAIL: ' + name);
  console.log('PASS: ' + name);
}

function makeContext(platform) {
  var listeners = {};
  var ctx = {
    console: console,
    navigator: { platform: platform || 'MacIntel' },
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
assert('video shortcuts are absent from core',
  !K.definitions().some(function (row) {
    return row.category === 'Video' || row.category === 'Timeline';
  }));
assert('absent video shortcut is not consumed',
  !K.matches('video_toggle_capture', evt('r', { metaKey: true, altKey: true })));

vm.runInNewContext(fs.readFileSync(VIDEO_SRC, 'utf8'), ctx, { filename: VIDEO_SRC });
assert('video package registers Video and Timeline shortcut rows',
  K.definitions().filter(function (row) {
    return row.category === 'Video' || row.category === 'Timeline';
  }).length === 9);
assert('installed video capture shortcut is active',
  K.matches('video_toggle_capture', evt('r', { metaKey: true, altKey: true })));

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

var winCtx = makeContext('Win32');
vm.runInNewContext(fs.readFileSync(SRC, 'utf8'), winCtx, { filename: SRC });
var WinK = winCtx.OraKeyboardShortcuts;
var winMinimize = WinK.validateShortcut('app_new_conversation', 'Mod+M', {});
assert('macOS-only reserved shortcut does not block Windows Ctrl+M',
  winMinimize.ok === true);
var winHistory = WinK.validateShortcut('app_new_conversation', 'Mod+H', {});
assert('browser-reserved Windows Ctrl+H remains blocked',
  winHistory.ok === false && winHistory.errors.length > 0);
assert('macOS-only reserved rows are hidden on Windows',
  !WinK.reserved().some(function (row) { return row.shortcut === 'Mod+Space'; }));

console.log('keyboard-shortcuts tests passed');
