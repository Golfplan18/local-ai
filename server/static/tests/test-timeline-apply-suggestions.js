#!/usr/bin/env node
/* test-timeline-apply-suggestions.js — A/V Phase 8
 *
 * Tests OraTimelineEditor's Apply methods (applyCutSuggestion,
 * applyChapterSuggestion, applyTitleCardSuggestion, applyTransitionSuggestion).
 * These are the rubber-meets-road of the Video Editing Suggestions
 * framework — bugs here would split clips at the wrong moment, drop
 * overlay clips on the wrong track, or apply transitions to the wrong clip.
 *
 * Strategy: inject a known timeline state via the _setStateForTests seam,
 * call the public Apply method, then read back via getState() and verify
 * the mutation. fetch() and DOM/Konva calls are no-ops in this sandbox.
 *
 * Run:
 *   node ~/ora/server/static/tests/test-timeline-apply-suggestions.js
 */

'use strict';

var fs   = require('fs');
var path = require('path');
var vm   = require('vm');

var SRC = path.resolve(__dirname, '..', 'timeline-editor.js');

// ── boot timeline-editor.js in a sandboxed window ──────────────────────────

function bootEditor() {
  var sandbox = {
    window: { OraTimelineEditor: null },
    document: {
      addEventListener: function () {}, removeEventListener: function () {},
      createElement: function () {
        return {
          setAttribute: function () {}, appendChild: function () {},
          remove: function () {}, classList: { add: function () {}, remove: function () {}, contains: function () { return false; } },
          dataset: {}, style: {},
          getBoundingClientRect: function () { return { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 }; },
          querySelector: function () { return null; },
          querySelectorAll: function () { return []; },
          addEventListener: function () {}, removeEventListener: function () {},
        };
      },
      body: { classList: { contains: function () { return false; } } },
      querySelector: function () { return null; },
      querySelectorAll: function () { return []; },
      dispatchEvent: function () {},
    },
    setTimeout: function () { return 0; },
    clearTimeout: function () {},
    fetch: function () {
      // No network in tests — return an unresolvable promise so debounced
      // saves don't actually fire anything. (The Apply methods schedule
      // a save but don't await it.)
      return new Promise(function () {});
    },
    Promise: Promise,
    AbortController: function () { return { abort: function () {}, signal: {} }; },
    CustomEvent: function (name, opts) { this.type = name; this.detail = opts && opts.detail; },
    Map: Map, WeakMap: WeakMap, Set: Set,
    Date: Date, Math: Math, Number: Number, String: String,
    Boolean: Boolean, Object: Object, Array: Array, JSON: JSON,
    isFinite: isFinite, parseInt: parseInt, parseFloat: parseFloat,
    console: console,
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(SRC, 'utf8'), sandbox);
  return sandbox.window.OraTimelineEditor;
}

// ── Test framework ──────────────────────────────────────────────────────────

var pass = 0, fail = 0;

function test(name, fn) {
  try {
    fn();
    pass++;
    console.log('  ✓ ' + name);
  } catch (e) {
    fail++;
    console.log('  ✗ ' + name);
    console.log('    ' + (e && e.stack ? e.stack : e));
  }
}
function assertEqual(a, b, msg) {
  var ok = (a === b) ||
           (a && b && JSON.stringify(a) === JSON.stringify(b));
  if (!ok) throw new Error((msg || 'assertion')
                           + ': expected ' + JSON.stringify(b)
                           + ', got ' + JSON.stringify(a));
}
function assertTrue(c, m) { if (!c) throw new Error(m || 'expected truthy'); }
function assertFalse(c, m) { if (c) throw new Error(m || 'expected falsy'); }

// ── Test fixtures ──────────────────────────────────────────────────────────

function makeStateWithMediaClip() {
  return {
    duration_ms: 10000,
    playhead_ms: 0,
    tracks: [{
      id: 'track1', kind: 'video', label: 'Video', muted: false,
      clips: [
        // Single clip: source [0..5000], placed at track 0..5000.
        { id: 'c1', media_entry_id: 'e1',
          in_point_ms: 0, out_point_ms: 5000, track_position_ms: 0,
          transition_in: 'cut', transition_out: 'cut',
          transition_duration_ms: 500, volume: 1.0,
          fade_in_ms: 0, fade_out_ms: 0 },
      ],
    }],
  };
}

function makeStateMultiClip() {
  // Two clips of the same entry, separated by a gap. Real-world: user
  // already cut something out; we want subsequent applyCut to work
  // within whichever clip contains the source range.
  return {
    duration_ms: 10000,
    playhead_ms: 0,
    tracks: [{
      id: 'track1', kind: 'video', label: 'Video', muted: false,
      clips: [
        { id: 'c1', media_entry_id: 'e1',
          in_point_ms: 0, out_point_ms: 2000, track_position_ms: 0,
          transition_in: 'cut', transition_out: 'cut' },
        { id: 'c2', media_entry_id: 'e1',
          in_point_ms: 4000, out_point_ms: 8000, track_position_ms: 2000,
          transition_in: 'cut', transition_out: 'cut' },
        { id: 'c3', media_entry_id: 'e2',
          in_point_ms: 0, out_point_ms: 3000, track_position_ms: 6000,
          transition_in: 'cut', transition_out: 'cut' },
      ],
    }],
  };
}

// ── Tests ───────────────────────────────────────────────────────────────────

console.log('test-timeline-apply-suggestions.js');

var api = bootEditor();

// ─── applyCutSuggestion ─────────────────────────────────────────────

test('applyCutSuggestion validates the source range', function () {
  api._setStateForTests(makeStateWithMediaClip());
  var bad = api.applyCutSuggestion({ media_entry_id: 'e1', start_ms: 1000, end_ms: 1000 });
  assertFalse(bad.ok, 'zero-length range must fail');
  bad = api.applyCutSuggestion({ media_entry_id: 'e1', start_ms: 2000, end_ms: 1000 });
  assertFalse(bad.ok, 'inverted range must fail');
  bad = api.applyCutSuggestion({ start_ms: 1000, end_ms: 2000 });
  assertFalse(bad.ok, 'missing entry_id must fail');
});

test('applyCutSuggestion fails when no clip contains the source range', function () {
  api._setStateForTests(makeStateWithMediaClip());
  // Source clip covers [0..5000]. Asking to cut [6000..7000] is outside.
  var res = api.applyCutSuggestion({
    media_entry_id: 'e1', start_ms: 6000, end_ms: 7000,
  });
  assertFalse(res.ok);
  assertTrue(/no clip|range/.test(res.reason), 'reason should mention range');
});

test('applyCutSuggestion splits a clip and ripples', function () {
  api._setStateForTests(makeStateWithMediaClip());
  var res = api.applyCutSuggestion({
    media_entry_id: 'e1', start_ms: 1000, end_ms: 2000,
  });
  assertTrue(res.ok, res && res.reason);
  assertEqual(res.deleted_ms, 1000);
  var s = api.getState();
  // Should now have TWO clips: the left half [0..1000] + the right half [2000..5000].
  var clips = s.tracks[0].clips.sort(function (a, b) {
    return a.track_position_ms - b.track_position_ms;
  });
  assertEqual(clips.length, 2);
  assertEqual(clips[0].in_point_ms, 0);
  assertEqual(clips[0].out_point_ms, 1000);
  assertEqual(clips[0].track_position_ms, 0);
  assertEqual(clips[1].in_point_ms, 2000);
  assertEqual(clips[1].out_point_ms, 5000);
  // Right half rippled left to fill the gap → starts at where the cut began (1000).
  assertEqual(clips[1].track_position_ms, 1000);
});

test('applyCutSuggestion shifts subsequent clips on same track', function () {
  api._setStateForTests(makeStateMultiClip());
  // Cut inside c2's source range. c3 (e2 clip) starts at track 6000.
  // Cut covers track 3000..4000 (1000ms). c3 should shift to 5000.
  var res = api.applyCutSuggestion({
    media_entry_id: 'e1', start_ms: 5000, end_ms: 6000,
  });
  assertTrue(res.ok, res && res.reason);
  var s = api.getState();
  var c3 = s.tracks[0].clips.find(function (c) { return c.media_entry_id === 'e2'; });
  assertEqual(c3.track_position_ms, 5000, 'c3 should ripple-shift left by 1000ms');
});

test('applyCutSuggestion handles cut at exact clip start (left half collapses)', function () {
  api._setStateForTests(makeStateWithMediaClip());
  // Cut from source 0 to 1000 — the very start of the clip.
  var res = api.applyCutSuggestion({
    media_entry_id: 'e1', start_ms: 0, end_ms: 1000,
  });
  assertTrue(res.ok);
  var s = api.getState();
  // Only one clip survives (the right half).
  assertEqual(s.tracks[0].clips.length, 1);
  assertEqual(s.tracks[0].clips[0].in_point_ms, 1000);
  assertEqual(s.tracks[0].clips[0].out_point_ms, 5000);
  assertEqual(s.tracks[0].clips[0].track_position_ms, 0);
});

test('applyCutSuggestion handles cut at exact clip end (right half collapses)', function () {
  api._setStateForTests(makeStateWithMediaClip());
  // Cut from 4000 to 5000 — to the very end.
  var res = api.applyCutSuggestion({
    media_entry_id: 'e1', start_ms: 4000, end_ms: 5000,
  });
  assertTrue(res.ok);
  var s = api.getState();
  // Only the left half survives.
  assertEqual(s.tracks[0].clips.length, 1);
  assertEqual(s.tracks[0].clips[0].in_point_ms, 0);
  assertEqual(s.tracks[0].clips[0].out_point_ms, 4000);
});

test('applyCutSuggestion ignores clips on other media entries', function () {
  api._setStateForTests(makeStateMultiClip());
  // Cut targeting e1 should not affect c3 (which is on e2) other than ripple.
  var before = api.getState().tracks[0].clips.length;
  var res = api.applyCutSuggestion({
    media_entry_id: 'e1', start_ms: 0, end_ms: 1000,
  });
  assertTrue(res.ok);
  // We started with 3 clips; the cut splits c1 into one (left collapsed
  // since cut started at 0) so total clips = 1 (e1 right) + 1 (e2 c2)
  // + 1 (e2 c3) = 3.
  var after = api.getState().tracks[0].clips.length;
  assertEqual(after, before);
});

// ─── applyChapterSuggestion ──────────────────────────────────────────

test('applyChapterSuggestion creates an overlay track on first call', function () {
  api._setStateForTests(makeStateWithMediaClip());
  // Pre-state: only video track exists.
  var before = api.getState().tracks.filter(function (t) { return t.kind === 'overlay'; });
  assertEqual(before.length, 0);
  var res = api.applyChapterSuggestion({ at_ms: 5000, label: 'Section 2' });
  assertTrue(res.ok);
  var after = api.getState().tracks.filter(function (t) { return t.kind === 'overlay'; });
  assertEqual(after.length, 1);
  assertEqual(after[0].clips.length, 1);
  assertEqual(after[0].clips[0].overlay_type, 'lower-third');
  assertEqual(after[0].clips[0].overlay_content.text, 'Section 2');
  assertEqual(after[0].clips[0].track_position_ms, 5000);
});

test('applyChapterSuggestion reuses existing overlay track', function () {
  var s = makeStateWithMediaClip();
  s.tracks.push({ id: 't_overlay', kind: 'overlay', label: 'Overlay', muted: false, clips: [] });
  api._setStateForTests(s);
  api.applyChapterSuggestion({ at_ms: 5000, label: 'A' });
  api.applyChapterSuggestion({ at_ms: 8000, label: 'B' });
  var overlays = api.getState().tracks.filter(function (t) { return t.kind === 'overlay'; });
  assertEqual(overlays.length, 1, 'must not create duplicate overlay tracks');
  assertEqual(overlays[0].clips.length, 2);
});

test('applyChapterSuggestion validates inputs', function () {
  api._setStateForTests(makeStateWithMediaClip());
  assertFalse(api.applyChapterSuggestion({ at_ms: -1, label: 'x' }).ok);
  assertFalse(api.applyChapterSuggestion({ at_ms: 1000, label: '' }).ok);
  assertFalse(api.applyChapterSuggestion({ at_ms: 1000, label: '   ' }).ok);
});

// ─── applyTitleCardSuggestion ────────────────────────────────────────

test('applyTitleCardSuggestion creates a title-card overlay clip', function () {
  api._setStateForTests(makeStateWithMediaClip());
  var res = api.applyTitleCardSuggestion({
    at_ms: 0, duration_ms: 3000, title: 'Welcome', subtitle: 'A talk',
  });
  assertTrue(res.ok);
  var overlays = api.getState().tracks.filter(function (t) { return t.kind === 'overlay'; });
  assertEqual(overlays.length, 1);
  var clip = overlays[0].clips[0];
  assertEqual(clip.overlay_type, 'title-card');
  assertEqual(clip.track_position_ms, 0);
  assertEqual(clip.out_point_ms, 3000);
  assertEqual(clip.overlay_content.text, 'Welcome\nA talk');
});

test('applyTitleCardSuggestion handles missing subtitle', function () {
  api._setStateForTests(makeStateWithMediaClip());
  var res = api.applyTitleCardSuggestion({
    at_ms: 0, duration_ms: 3000, title: 'Just a title',
  });
  assertTrue(res.ok);
  var clip = api.getState().tracks.filter(function (t) { return t.kind === 'overlay'; })[0].clips[0];
  assertEqual(clip.overlay_content.text, 'Just a title');
});

test('applyTitleCardSuggestion enforces minimum duration', function () {
  api._setStateForTests(makeStateWithMediaClip());
  api.applyTitleCardSuggestion({ at_ms: 0, duration_ms: 100, title: 'X' });
  var clip = api.getState().tracks.filter(function (t) { return t.kind === 'overlay'; })[0].clips[0];
  assertTrue(clip.out_point_ms >= 500, 'duration floor should clamp to 500ms');
});

// ─── applyTransitionSuggestion ───────────────────────────────────────

test('applyTransitionSuggestion sets transition on the nearest clip end', function () {
  api._setStateForTests(makeStateWithMediaClip());
  // Single clip ends at track time 5000. Suggestion at_ms=5000 (perfect match).
  var res = api.applyTransitionSuggestion({
    at_ms: 5000, kind: 'fade', duration_ms: 800,
  });
  assertTrue(res.ok);
  assertEqual(res.applied_kind, 'fade-to-black');
  var clip = api.getState().tracks[0].clips[0];
  assertEqual(clip.transition_out, 'fade-to-black');
  assertEqual(clip.transition_duration_ms, 800);
});

test('applyTransitionSuggestion within tolerance still applies', function () {
  api._setStateForTests(makeStateWithMediaClip());
  // Clip ends at 5000. Ask for transition at 5400 (400ms off).
  var res = api.applyTransitionSuggestion({ at_ms: 5400, kind: 'dissolve' });
  assertTrue(res.ok);
  assertEqual(res.applied_kind, 'dissolve');
});

test('applyTransitionSuggestion fails outside tolerance window', function () {
  api._setStateForTests(makeStateWithMediaClip());
  // Clip ends at 5000. Ask for transition at 9000 (4000ms off).
  var res = api.applyTransitionSuggestion({ at_ms: 9000, kind: 'fade' });
  assertFalse(res.ok);
  assertTrue(/clip ends/.test(res.reason));
});

test('applyTransitionSuggestion maps kinds to canonical names', function () {
  api._setStateForTests(makeStateWithMediaClip());
  // 'fade' → 'fade-to-black'
  api.applyTransitionSuggestion({ at_ms: 5000, kind: 'fade' });
  assertEqual(api.getState().tracks[0].clips[0].transition_out, 'fade-to-black');

  // 'dissolve' → 'dissolve'
  api._setStateForTests(makeStateWithMediaClip());
  api.applyTransitionSuggestion({ at_ms: 5000, kind: 'dissolve' });
  assertEqual(api.getState().tracks[0].clips[0].transition_out, 'dissolve');

  // 'cut' → 'cut'
  api._setStateForTests(makeStateWithMediaClip());
  api.applyTransitionSuggestion({ at_ms: 5000, kind: 'cut' });
  assertEqual(api.getState().tracks[0].clips[0].transition_out, 'cut');
});

test('applyTransitionSuggestion ignores overlay clips when finding nearest', function () {
  var s = makeStateWithMediaClip();
  // Add an overlay track with a clip ending right at 5500.
  s.tracks.push({
    id: 't2', kind: 'overlay', label: 'Overlay', muted: false,
    clips: [{ id: 'ov1', overlay_type: 'lower-third', overlay_content: { text: 'X' },
              in_point_ms: 0, out_point_ms: 500, track_position_ms: 5000,
              transition_in: 'cut', transition_out: 'cut' }],
  });
  api._setStateForTests(s);
  // Without overlay-skip the overlay clip would be the closest match.
  // With it, we apply to the media clip (ends at 5000).
  var res = api.applyTransitionSuggestion({ at_ms: 5500, kind: 'fade' });
  assertTrue(res.ok);
  var media = api.getState().tracks[0].clips[0];
  var ov   = api.getState().tracks[1].clips[0];
  assertEqual(media.transition_out, 'fade-to-black');
  assertEqual(ov.transition_out, 'cut', 'overlay must not be touched');
});

// ── summary ────────────────────────────────────────────────────────────

console.log('');
console.log('Results: ' + pass + ' passed, ' + fail + ' failed');
process.exit(fail > 0 ? 1 : 0);
