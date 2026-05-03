#!/usr/bin/env node
/* test-transcript-panel-helpers.js — A/V Phase 8
 *
 * Tests the pure-math helpers exposed on
 * window.OraTranscriptPanel._internals:
 *
 *   findActiveClip(state, playheadMs)
 *     → returns the media clip whose source range covers playheadMs,
 *       or null. Skips overlay clips and clips without media_entry_id.
 *
 *   sourceTimeAt(clip, playheadMs)
 *     → maps timeline-time → source-time using the clip's in_point_ms
 *       and track_position_ms.
 *
 *   segmentIdxAt(segments, sourceMs)
 *     → returns the index of the segment containing sourceMs, or
 *       falls back to the last segment that started ≤ sourceMs.
 *
 *   trackTimeForSegment(state, entryId, segmentStartMs)
 *     → maps source-time → timeline-time for a segment within a clip
 *       on the timeline; null if the segment is outside every clip's
 *       trim range.
 *
 * These functions back the bidirectional playhead↔transcript sync.
 * Bugs here would mean clicking a transcript line jumps to the
 * wrong moment, or scrubbing the timeline highlights the wrong
 * sentence — both immediately user-visible.
 *
 * Run:
 *   node ~/ora/server/static/tests/test-transcript-panel-helpers.js
 */

'use strict';

var fs   = require('fs');
var path = require('path');
var vm   = require('vm');

var ROOT = path.resolve(__dirname, '..');
var SRC  = path.join(ROOT, 'transcript-panel.js');

// ── boot transcript-panel.js in a sandboxed window ──────────────────────────

function bootPanel() {
  var sandbox = {
    window: { OraTranscriptPanel: null, OraTimelineEditor: null },
    document: {
      addEventListener: function () {},
      removeEventListener: function () {},
      createElement: function () { return { setAttribute: function(){}, appendChild: function(){} }; },
      body: { classList: { contains: function () { return false; } } },
      querySelector: function () { return null; },
      dispatchEvent: function () {},
    },
    setTimeout: function () {}, clearTimeout: function () {},
    fetch: function () { return Promise.resolve({ ok: false }); },
    AbortController: function () { return { abort: function () {}, signal: {} }; },
    Date: Date, Math: Math, Number: Number, String: String,
    Boolean: Boolean, Object: Object, Array: Array, JSON: JSON,
    isFinite: isFinite, parseInt: parseInt, parseFloat: parseFloat,
    console: console,
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(SRC, 'utf8'), sandbox);
  return sandbox.window.OraTranscriptPanel._internals;
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
function assertNull(v, m) { if (v !== null) throw new Error((m||'expected null') + '; got ' + JSON.stringify(v)); }

// ── Tests ───────────────────────────────────────────────────────────────────

console.log('test-transcript-panel-helpers.js');

var helpers = bootPanel();

// ─── findActiveClip ───────────────────────────────────────────────────

test('findActiveClip returns the clip under the playhead', function () {
  var state = {
    tracks: [{
      clips: [
        { id: 'c1', media_entry_id: 'e1', in_point_ms: 1000, out_point_ms: 5000, track_position_ms: 0 },
        { id: 'c2', media_entry_id: 'e1', in_point_ms: 0, out_point_ms: 3000, track_position_ms: 4000 },
      ],
    }],
  };
  var clip = helpers.findActiveClip(state, 2000);
  assertEqual(clip && clip.id, 'c1');
});

test('findActiveClip prefers the clip whose track range contains playhead', function () {
  var state = {
    tracks: [{
      clips: [
        { id: 'a', media_entry_id: 'e1', in_point_ms: 0, out_point_ms: 5000, track_position_ms: 0 },
        { id: 'b', media_entry_id: 'e1', in_point_ms: 0, out_point_ms: 5000, track_position_ms: 5000 },
      ],
    }],
  };
  // Playhead at 6000 falls within clip b only (track range 5000-10000).
  var clip = helpers.findActiveClip(state, 6000);
  assertEqual(clip && clip.id, 'b');
});

test('findActiveClip returns null when playhead lands in a gap', function () {
  var state = {
    tracks: [{
      clips: [
        { id: 'a', media_entry_id: 'e1', in_point_ms: 0, out_point_ms: 1000, track_position_ms: 0 },
        { id: 'b', media_entry_id: 'e1', in_point_ms: 0, out_point_ms: 1000, track_position_ms: 5000 },
      ],
    }],
  };
  // Playhead at 3000 falls in the 1000..5000 gap.
  assertNull(helpers.findActiveClip(state, 3000));
});

test('findActiveClip skips overlay clips (no media_entry_id)', function () {
  var state = {
    tracks: [{
      clips: [
        { id: 'overlay', overlay_type: 'title-card', track_position_ms: 0,
          in_point_ms: 0, out_point_ms: 3000 },
        { id: 'media', media_entry_id: 'e1', in_point_ms: 0, out_point_ms: 5000,
          track_position_ms: 0 },
      ],
    }],
  };
  var clip = helpers.findActiveClip(state, 1500);
  assertEqual(clip && clip.id, 'media');
});

test('findActiveClip handles multi-track timelines', function () {
  var state = {
    tracks: [
      { clips: [{ id: 'audio', media_entry_id: 'e2', in_point_ms: 0, out_point_ms: 8000, track_position_ms: 0 }] },
      { clips: [{ id: 'video', media_entry_id: 'e1', in_point_ms: 1000, out_point_ms: 5000, track_position_ms: 0 }] },
    ],
  };
  // Both tracks have a clip at playhead 2000; we just want any non-null match.
  var clip = helpers.findActiveClip(state, 2000);
  assertTrue(clip, 'expected a clip match');
});

test('findActiveClip returns null on null/empty inputs', function () {
  assertNull(helpers.findActiveClip(null, 0));
  assertNull(helpers.findActiveClip({}, 0));
  assertNull(helpers.findActiveClip({ tracks: [] }, 0));
  assertNull(helpers.findActiveClip({ tracks: [{ clips: [] }] }, 0));
});

test('findActiveClip handles clips with zero length defensively', function () {
  var state = {
    tracks: [{
      clips: [
        { id: 'broken', media_entry_id: 'e1', in_point_ms: 1000, out_point_ms: 1000, track_position_ms: 0 },
      ],
    }],
  };
  // Zero-length clip should never be "active."
  assertNull(helpers.findActiveClip(state, 0));
});

// ─── sourceTimeAt ────────────────────────────────────────────────────

test('sourceTimeAt: trim-from-start respected', function () {
  var clip = { in_point_ms: 1000, track_position_ms: 0 };
  // playhead at 0 = source 1000 (trimmed start).
  assertEqual(helpers.sourceTimeAt(clip, 0), 1000);
  // playhead at 500 = source 1500.
  assertEqual(helpers.sourceTimeAt(clip, 500), 1500);
});

test('sourceTimeAt: track_position offset respected', function () {
  var clip = { in_point_ms: 0, track_position_ms: 2000 };
  // playhead at 2500 = clip-local 500 = source 500.
  assertEqual(helpers.sourceTimeAt(clip, 2500), 500);
});

test('sourceTimeAt: combined trim + track offset', function () {
  var clip = { in_point_ms: 1000, track_position_ms: 2000 };
  // playhead at 2500 = clip-local 500 = source (1000 + 500) = 1500.
  assertEqual(helpers.sourceTimeAt(clip, 2500), 1500);
});

// ─── segmentIdxAt ─────────────────────────────────────────────────────

test('segmentIdxAt: returns idx of containing segment', function () {
  var segments = [
    { start_ms: 0, end_ms: 1000 },
    { start_ms: 1000, end_ms: 2500 },
    { start_ms: 2500, end_ms: 4000 },
  ];
  assertEqual(helpers.segmentIdxAt(segments, 500), 0);
  assertEqual(helpers.segmentIdxAt(segments, 1500), 1);
  assertEqual(helpers.segmentIdxAt(segments, 3000), 2);
});

test('segmentIdxAt: boundary lands on next segment (start inclusive)', function () {
  var segments = [
    { start_ms: 0, end_ms: 1000 },
    { start_ms: 1000, end_ms: 2000 },
  ];
  // 1000 belongs to seg 1 because seg 0's end is exclusive.
  assertEqual(helpers.segmentIdxAt(segments, 1000), 1);
});

test('segmentIdxAt: returns -1 on empty segments', function () {
  assertEqual(helpers.segmentIdxAt([], 5000), -1);
  assertEqual(helpers.segmentIdxAt(null, 5000), -1);
});

test('segmentIdxAt: falls back to last-started when in a gap', function () {
  var segments = [
    { start_ms: 0,    end_ms: 1000 },
    { start_ms: 5000, end_ms: 6000 },
  ];
  // Source 3000 is past seg 0's end and before seg 1's start. Fallback
  // returns the last segment that started ≤ 3000, which is seg 0.
  assertEqual(helpers.segmentIdxAt(segments, 3000), 0);
});

test('segmentIdxAt: source past end returns last segment', function () {
  var segments = [
    { start_ms: 0,    end_ms: 1000 },
    { start_ms: 1000, end_ms: 2000 },
  ];
  assertEqual(helpers.segmentIdxAt(segments, 9999), 1);
});

// ─── trackTimeForSegment ──────────────────────────────────────────────

test('trackTimeForSegment: maps source → track for matching clip', function () {
  var state = {
    tracks: [{
      clips: [
        { media_entry_id: 'e1', in_point_ms: 1000, out_point_ms: 5000, track_position_ms: 2000 },
      ],
    }],
  };
  // Source 2500 within trim range [1000..5000]. Track time = 2000 + (2500 - 1000) = 3500.
  assertEqual(helpers.trackTimeForSegment(state, 'e1', 2500), 3500);
});

test('trackTimeForSegment: returns null when segment is trimmed out', function () {
  var state = {
    tracks: [{
      clips: [
        { media_entry_id: 'e1', in_point_ms: 1000, out_point_ms: 5000, track_position_ms: 0 },
      ],
    }],
  };
  // Segment at source 500 is BEFORE the trim-in (1000). Not on the timeline.
  assertNull(helpers.trackTimeForSegment(state, 'e1', 500));
  // Segment at source 6000 is AFTER the trim-out (5000). Not on the timeline.
  assertNull(helpers.trackTimeForSegment(state, 'e1', 6000));
});

test('trackTimeForSegment: returns null when entry has no clips', function () {
  var state = { tracks: [{ clips: [] }] };
  assertNull(helpers.trackTimeForSegment(state, 'e1', 500));
});

test('trackTimeForSegment: picks the right clip when entry split into multiple', function () {
  // The entry was split into two clips on the timeline (cut middle).
  var state = {
    tracks: [{
      clips: [
        // Clip A: source [0..1000], placed at track 0..1000
        { media_entry_id: 'e1', in_point_ms: 0, out_point_ms: 1000, track_position_ms: 0 },
        // Clip B: source [3000..5000], placed at track 1000..3000 (after ripple)
        { media_entry_id: 'e1', in_point_ms: 3000, out_point_ms: 5000, track_position_ms: 1000 },
      ],
    }],
  };
  // Source 500 → in clip A at track 500.
  assertEqual(helpers.trackTimeForSegment(state, 'e1', 500), 500);
  // Source 4000 → in clip B at track 1000 + (4000 - 3000) = 2000.
  assertEqual(helpers.trackTimeForSegment(state, 'e1', 4000), 2000);
  // Source 1500 → fell into the cut gap, not on timeline.
  assertNull(helpers.trackTimeForSegment(state, 'e1', 1500));
});

// ── summary ────────────────────────────────────────────────────────────

console.log('');
console.log('Results: ' + pass + ' passed, ' + fail + ' failed');
process.exit(fail > 0 ? 1 : 0);
