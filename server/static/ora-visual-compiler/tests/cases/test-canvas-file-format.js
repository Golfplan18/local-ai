/**
 * tests/cases/test-canvas-file-format.js — WP-7.0.2 regression suite.
 *
 * Exports { label, run(ctx, record) } per the run.js case-file convention.
 *
 * Coverage of the canvas-state file-format reader/writer
 * (server/static/canvas-file-format.js):
 *
 *   1. Namespace exists on window.OraCanvasFileFormat with the documented
 *      surface (read, write, validate, isCompressed, newCanvasState,
 *      readJsonBytes, writeJsonBytes, writeJsonString).
 *   2. newCanvasState() emits a valid skeleton (4 layers, default view).
 *   3. Compressed round-trip: 5 objects + 2 embedded base64 images survive
 *      write→read with deepEqual. (Direct test-brief coverage for WP-7.0.2.)
 *   4. Uncompressed round-trip: same fixture, raw JSON path.
 *   5. Bytes-equivalent-after-decompression: gunzip(compressed) === raw JSON.
 *   6. Compressed output is smaller than uncompressed (gzip is doing work).
 *   7. Image base64 payloads survive byte-exact through the round-trip.
 *   8. Canonicalisation: two writes of the same canvas produce identical
 *      bytes; permuted key order yields identical bytes.
 *   9. read() rejects non-canvas-state JSON (format_id mismatch).
 *  10. read() rejects malformed JSON.
 *  11. validate() accepts the round-trip fixture and rejects an image
 *      object lacking image_data.
 *  12. isCompressed() detects gzip magic bytes correctly.
 */

'use strict';

const path = require('path');
const fs   = require('fs');
const zlib = require('zlib');

// ── Test fixture ────────────────────────────────────────────────────────────

// Two distinct deterministic byte buffers, base64-encoded. Mirrors the
// Python suite's _PNG_A_BYTES / _PNG_B_BYTES so a future cross-language
// fixture share is straightforward.
function _makeBytesA() {
  var b = new Uint8Array(1024);
  for (var i = 0; i < b.length; i++) b[i] = i % 256;
  return b;
}
function _makeBytesB() {
  var b = new Uint8Array(768);
  for (var i = 0; i < b.length; i++) b[i] = (255 - (i % 256)) & 0xFF;
  return b;
}

function _toBase64(uint8) {
  // Node Buffer is the simplest path inside the jsdom harness.
  return Buffer.from(uint8).toString('base64');
}

function _fromBase64(b64) {
  return new Uint8Array(Buffer.from(b64, 'base64'));
}

function _u8Equal(a, b) {
  if (a.length !== b.length) return false;
  for (var i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

function _deepEqual(a, b) {
  if (a === b) return true;
  if (a === null || b === null) return a === b;
  if (typeof a !== 'object' || typeof b !== 'object') return a === b;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a)) {
    if (a.length !== b.length) return false;
    for (var i = 0; i < a.length; i++) if (!_deepEqual(a[i], b[i])) return false;
    return true;
  }
  var ka = Object.keys(a).sort();
  var kb = Object.keys(b).sort();
  if (ka.length !== kb.length) return false;
  for (var k = 0; k < ka.length; k++) {
    if (ka[k] !== kb[k]) return false;
    if (!_deepEqual(a[ka[k]], b[kb[k]])) return false;
  }
  return true;
}

function makeCanvasFixture() {
  var pngA = _toBase64(_makeBytesA());
  var pngB = _toBase64(_makeBytesB());
  return {
    schema_version: '0.1.0',
    format_id:      'ora-canvas',
    metadata: {
      title:           'Round-trip fixture',
      conversation_id: 'conv-12345',
      ora_version:     'ora-test',
      created_at:      '2026-04-29T12:00:00.000Z',
      modified_at:     '2026-04-29T12:00:00.000Z',
      canvas_size:     { width: 10000, height: 10000 }
    },
    view: { zoom: 1.5, pan: { x: -250.5, y: 80 } },
    layers: [
      { id: 'background',  kind: 'background',  visible: true, locked: false, opacity: 1 },
      { id: 'annotation',  kind: 'annotation',  visible: true, locked: false, opacity: 1 },
      { id: 'user_input',  kind: 'user_input',  visible: true, locked: false, opacity: 1 },
      { id: 'selection',   kind: 'selection',   visible: true, locked: false, opacity: 1 }
    ],
    objects: [
      { id: 'u-rect-0', kind: 'shape', layer: 'user_input', konva_class: 'Rect',
        x: 100, y: 200, width: 80, height: 40, rotation: 0, scale_x: 1, scale_y: 1,
        opacity: 1, visible: true, user_label: 'Cause',
        attrs: { fill: '#aabbcc', stroke: '#112233', strokeWidth: 2 } },
      { id: 'u-rect-1', kind: 'shape', layer: 'user_input', konva_class: 'Rect',
        x: 300, y: 200, width: 80, height: 40, user_label: 'Effect',
        attrs: { fill: '#ddeeff', stroke: '#112233', strokeWidth: 2 } },
      { id: 'u-arr-0',  kind: 'shape', layer: 'user_input', konva_class: 'Arrow',
        user_label: '→',
        attrs: { points: [180, 220, 300, 220], stroke: '#000', strokeWidth: 2 } },
      { id: 'img-bg-0', kind: 'image', layer: 'background',
        x: 0, y: 0, width: 800, height: 600,
        image_data: { mime_type: 'image/png', encoding: 'base64', data: pngA,
                      natural_width: 800, natural_height: 600, source: 'upload' } },
      { id: 'img-overlay-0', kind: 'image', layer: 'annotation',
        x: 50, y: 50, width: 200, height: 150,
        image_data: { mime_type: 'image/jpeg', encoding: 'base64', data: pngB,
                      natural_width: 200, natural_height: 150,
                      source: 'generated:test-provider' } }
    ]
  };
}

// ── Suite ───────────────────────────────────────────────────────────────────

module.exports = {
  label: 'Canvas file format (WP-7.0.2) — .ora-canvas + .ora-canvas.json round-trip',
  run: async function run(ctx, record) {
    var win = ctx.win;

    // The module file lives one level above the compiler dir under
    // server/static/. Load it inside the jsdom context so it registers on
    // the window namespace.
    var modulePath = path.resolve(__dirname, '..', '..', '..', 'canvas-file-format.js');
    if (!fs.existsSync(modulePath)) {
      record('canvas-file-format: module file present', false, 'not found at ' + modulePath);
      return;
    }
    var src = fs.readFileSync(modulePath, 'utf-8');
    // win.eval lands the IIFE assignment on win.OraCanvasFileFormat.
    win.eval(src);

    if (typeof win.OraCanvasFileFormat === 'undefined') {
      record('canvas-file-format: namespace present', false, 'window.OraCanvasFileFormat undefined');
      return;
    }
    var F = win.OraCanvasFileFormat;

    // jsdom's window does NOT expose CompressionStream; inject Node's zlib
    // as the gzip implementation so the streams-API path doesn't fire.
    F._setGzipImpl({
      deflate: function (bytes) {
        // Mirror Python's mtime=0 + level=6 so the byte-equivalence
        // invariant holds across both languages where that matters.
        var buf = Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength);
        var out = zlib.gzipSync(buf, { level: 6 });
        return new Uint8Array(out.buffer, out.byteOffset, out.byteLength);
      },
      inflate: function (bytes) {
        var buf = Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength);
        var out = zlib.gunzipSync(buf);
        return new Uint8Array(out.buffer, out.byteOffset, out.byteLength);
      }
    });

    // 1. Namespace surface.
    record('canvas-file-format #1: namespace surface',
      typeof F === 'object' &&
      typeof F.read === 'function' &&
      typeof F.write === 'function' &&
      typeof F.validate === 'function' &&
      typeof F.isCompressed === 'function' &&
      typeof F.newCanvasState === 'function' &&
      typeof F.readJsonBytes === 'function' &&
      typeof F.writeJsonBytes === 'function' &&
      typeof F.writeJsonString === 'function' &&
      F.SCHEMA_VERSION === '0.1.0' &&
      F.FORMAT_ID === 'ora-canvas',
      'keys=' + Object.keys(F).join(','));

    // 2. newCanvasState skeleton.
    try {
      var skel = F.newCanvasState();
      var v = F.validate(skel);
      record('canvas-file-format #2: newCanvasState validates',
        v.valid && skel.layers.length === 4 && skel.view.zoom === 1,
        v.valid ? '' : JSON.stringify(v.errors));
    } catch (e) {
      record('canvas-file-format #2', false, 'threw: ' + (e.stack || e.message));
    }

    // 3. Compressed round-trip — 5 objects + 2 embedded images, deepEqual.
    var fixture = makeCanvasFixture();
    var compressedBytes;
    try {
      compressedBytes = await F.write(fixture, { compressed: true });
      var hasMagic = compressedBytes.length >= 2 && compressedBytes[0] === 0x1F && compressedBytes[1] === 0x8B;
      var recovered = await F.read(compressedBytes);
      record('canvas-file-format #3: compressed round-trip (5 objects + 2 images)',
        hasMagic && _deepEqual(recovered, fixture),
        hasMagic ? '' : 'gzip magic missing');
    } catch (e) {
      record('canvas-file-format #3', false, 'threw: ' + (e.stack || e.message));
    }

    // 4. Uncompressed round-trip.
    var uncompressedBytes;
    try {
      uncompressedBytes = await F.write(fixture, { compressed: false });
      var noMagic = !(uncompressedBytes[0] === 0x1F && uncompressedBytes[1] === 0x8B);
      var recovered = await F.read(uncompressedBytes);
      record('canvas-file-format #4: uncompressed round-trip',
        noMagic && _deepEqual(recovered, fixture),
        noMagic ? '' : 'unexpected gzip magic on uncompressed output');
    } catch (e) {
      record('canvas-file-format #4', false, 'threw: ' + (e.stack || e.message));
    }

    // 5. Bytes-equivalent-after-decompression.
    try {
      var c = await F.write(fixture, { compressed: true });
      var u = await F.write(fixture, { compressed: false });
      var dec = zlib.gunzipSync(Buffer.from(c.buffer, c.byteOffset, c.byteLength));
      var decU8 = new Uint8Array(dec.buffer, dec.byteOffset, dec.byteLength);
      record('canvas-file-format #5: gunzip(compressed) === uncompressed JSON bytes',
        _u8Equal(decU8, u),
        _u8Equal(decU8, u) ? '' :
          'decompressed=' + decU8.length + 'B, raw=' + u.length + 'B');
    } catch (e) {
      record('canvas-file-format #5', false, 'threw: ' + (e.stack || e.message));
    }

    // 6. Compression effectiveness.
    try {
      var c = await F.write(fixture, { compressed: true });
      var u = await F.write(fixture, { compressed: false });
      record('canvas-file-format #6: compressed smaller than uncompressed',
        c.length < u.length,
        'compressed=' + c.length + 'B, uncompressed=' + u.length + 'B');
    } catch (e) {
      record('canvas-file-format #6', false, 'threw: ' + (e.stack || e.message));
    }

    // 7. Image bytes survive byte-exact.
    try {
      var c = await F.write(fixture, { compressed: true });
      var rec = await F.read(c);
      var imgA = rec.objects.find(function (o) { return o.id === 'img-bg-0'; });
      var imgB = rec.objects.find(function (o) { return o.id === 'img-overlay-0'; });
      var aBytes = _fromBase64(imgA.image_data.data);
      var bBytes = _fromBase64(imgB.image_data.data);
      var aMatch = _u8Equal(aBytes, _makeBytesA());
      var bMatch = _u8Equal(bBytes, _makeBytesB());
      record('canvas-file-format #7: image base64 payloads recovered byte-exact',
        aMatch && bMatch,
        'A:' + (aMatch ? 'ok' : 'MISMATCH') + ' B:' + (bMatch ? 'ok' : 'MISMATCH'));
    } catch (e) {
      record('canvas-file-format #7', false, 'threw: ' + (e.stack || e.message));
    }

    // 8a. Canonicalisation stable across writes.
    try {
      var b1 = await F.write(fixture, { compressed: false });
      var b2 = await F.write(fixture, { compressed: false });
      record('canvas-file-format #8a: two writes of same canvas → identical bytes',
        _u8Equal(b1, b2),
        '');
    } catch (e) {
      record('canvas-file-format #8a', false, 'threw: ' + (e.stack || e.message));
    }

    // 8b. Canonicalisation orders keys.
    try {
      var a = { format_id: 'ora-canvas', schema_version: '0.1.0',
                metadata: { canvas_size: { width: 10, height: 10 } },
                view: { zoom: 1, pan: { x: 0, y: 0 } },
                layers: [{ id: 'background', kind: 'background' }],
                objects: [] };
      var b = { layers: [{ kind: 'background', id: 'background' }], objects: [],
                view: { pan: { y: 0, x: 0 }, zoom: 1 },
                metadata: { canvas_size: { height: 10, width: 10 } },
                schema_version: '0.1.0', format_id: 'ora-canvas' };
      var ba = await F.write(a, { compressed: false });
      var bb = await F.write(b, { compressed: false });
      record('canvas-file-format #8b: permuted key order yields identical bytes',
        _u8Equal(ba, bb),
        '');
    } catch (e) {
      record('canvas-file-format #8b', false, 'threw: ' + (e.stack || e.message));
    }

    // 9. format_id mismatch rejected.
    try {
      var bad = new TextEncoder().encode(JSON.stringify({ format_id: 'not-ora-canvas' }));
      var threw = false;
      try { await F.read(bad); } catch (e) { threw = /format_id/.test(e.message); }
      record('canvas-file-format #9: format_id mismatch rejected', threw, '');
    } catch (e) {
      record('canvas-file-format #9', false, 'threw: ' + (e.stack || e.message));
    }

    // 10. Malformed JSON rejected.
    try {
      var bad = new TextEncoder().encode('not json at all');
      var threw = false;
      try { await F.read(bad); } catch (e) { threw = /invalid JSON/.test(e.message); }
      record('canvas-file-format #10: malformed JSON rejected', threw, '');
    } catch (e) {
      record('canvas-file-format #10', false, 'threw: ' + (e.stack || e.message));
    }

    // 11. validate() accepts fixture; rejects image without image_data.
    try {
      var ok1 = F.validate(fixture);
      var bad = JSON.parse(JSON.stringify(fixture));
      bad.objects.push({ id: 'broken', kind: 'image', layer: 'background' });
      var ok2 = F.validate(bad);
      record('canvas-file-format #11: validate accepts fixture and rejects bad image',
        ok1.valid === true && ok2.valid === false,
        'valid_fixture=' + ok1.valid + ' bad_image=' + ok2.valid);
    } catch (e) {
      record('canvas-file-format #11', false, 'threw: ' + (e.stack || e.message));
    }

    // 12. isCompressed detection.
    try {
      var u = await F.write(fixture, { compressed: false });
      var c = await F.write(fixture, { compressed: true });
      record('canvas-file-format #12: isCompressed detects gzip magic',
        F.isCompressed(c) === true && F.isCompressed(u) === false,
        '');
    } catch (e) {
      record('canvas-file-format #12', false, 'threw: ' + (e.stack || e.message));
    }
  }
};
