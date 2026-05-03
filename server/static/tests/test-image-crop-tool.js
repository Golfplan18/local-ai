#!/usr/bin/env node
/* test-image-crop-tool.js — WP-7.4.3
 *
 * Validates the per-image raster crop tool's headless `cropImageObject`
 * primitive. The Konva-driven activate/deactivate UX is exercised at
 * structural level only; the load-bearing assertions are on the pure
 * state-mutation helper because that's where the §13.4 test contract
 * (preserve position, replace pixels) actually lives.
 *
 * Run:  node ~/ora/server/static/tests/test-image-crop-tool.js
 * Exit code 0 on full pass, 1 on any failure.
 *
 * Test cases:
 *   1. tool exposes the §B.4 primitive surface
 *   2. cropImageObject rejects non-existent object id
 *   3. cropImageObject rejects out-of-bounds region
 *   4. cropImageObject preserves position when crop region offset is 0,0
 *   5. cropImageObject shifts position by (region.x, region.y) for off-origin crops
 *   6. cropImageObject replaces image_data with the cropped pixel payload
 *   7. cropImageObject locates nested images inside group children
 *   8. cropping the right half of a 4×2 checkerboard yields the right-half
 *      pixels at the original-position-shifted location (the §13.4 test)
 *   9. tool registers on window.OraTools when window is present
 *  10. activate / deactivate are no-ops when no Konva panel is attached
 */

'use strict';

var path = require('path');

var TOOL_PATH = path.resolve(__dirname, '..', 'tools', 'image-crop.tool.js');

// ── Test infrastructure ──────────────────────────────────────────────────────

var results = [];
function record(name, ok, detail) {
  results.push({ name: name, ok: !!ok, detail: detail || '' });
  var sigil = ok ? 'PASS' : 'FAIL';
  console.log('  ' + sigil + '  ' + name + (detail ? '  — ' + detail : ''));
}
function summarize() {
  var total  = results.length;
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

// ── Fake "raster" payload model ─────────────────────────────────────────────
//
// We don't depend on a real PNG codec. Instead, the fake host treats the
// image's "data" payload as a JSON-encoded 2D array of pixel values. That
// gives us deterministic, position-checkable crop output without pulling
// in node-canvas / jimp. The MIME type is fudged to "image/x-fake".

function makeFakeBitmap(width, height, fillFn) {
  var rows = [];
  for (var y = 0; y < height; y++) {
    var row = [];
    for (var x = 0; x < width; x++) row.push(fillFn(x, y));
    rows.push(row);
  }
  return rows;
}

function bitmapToBase64(rows) {
  var json = JSON.stringify(rows);
  return Buffer.from(json, 'utf8').toString('base64');
}

function base64ToBitmap(b64) {
  var json = Buffer.from(b64, 'base64').toString('utf8');
  return JSON.parse(json);
}

function makeFakeHost() {
  // The fake host stashes the bitmap on a per-canvas backing store and
  // performs the crop in pure JS. drawImage(img, 0, 0, w, h) blits
  // img._bitmap onto the canvas; drawImage(canvas, sx, sy, sw, sh, dx, dy, dw, dh)
  // copies a sub-rect from one canvas into another.
  return {
    createCanvas: function (w, h) {
      var rows = makeFakeBitmap(w, h, function () { return null; });
      return {
        width: w,
        height: h,
        _bitmap: rows,
        getContext: function (kind) {
          if (kind !== '2d') return null;
          var canvas = this;
          return {
            drawImage: function () {
              var args = Array.prototype.slice.call(arguments);
              var src = args[0];
              if (args.length === 3) {
                // drawImage(src, dx, dy)
                _blitFull(src, canvas, args[1], args[2]);
              } else if (args.length === 5) {
                _blitFull(src, canvas, args[1], args[2], args[3], args[4]);
              } else if (args.length === 9) {
                _blitClipped(
                  src, canvas,
                  args[1], args[2], args[3], args[4],
                  args[5], args[6], args[7], args[8]
                );
              }
            }
          };
        },
        toDataURL: function (mime) {
          return 'data:' + (mime || 'image/x-fake') + ';base64,' + bitmapToBase64(this._bitmap);
        }
      };
    },
    loadImage: function (dataUrl) {
      // Strip data URL, decode bitmap.
      var m = /^data:[^;]+;base64,(.*)$/.exec(dataUrl);
      var b64 = m ? m[1] : dataUrl;
      var rows = base64ToBitmap(b64);
      var img = {
        _bitmap:       rows,
        naturalWidth:  rows[0] ? rows[0].length : 0,
        naturalHeight: rows.length,
        width:         rows[0] ? rows[0].length : 0,
        height:        rows.length
      };
      return Promise.resolve(img);
    },
    toDataURL: function (canvas, mime) {
      return canvas.toDataURL(mime);
    }
  };

  function _blitFull(src, dst, dx, dy, dw, dh) {
    var srcBitmap = src._bitmap;
    var sw = (src.naturalWidth  || src.width  || (srcBitmap[0] ? srcBitmap[0].length : 0));
    var sh = (src.naturalHeight || src.height || srcBitmap.length);
    if (typeof dw !== 'number') dw = sw;
    if (typeof dh !== 'number') dh = sh;
    for (var y = 0; y < dh; y++) {
      for (var x = 0; x < dw; x++) {
        var sx = Math.floor(x * sw / dw);
        var sy = Math.floor(y * sh / dh);
        if (srcBitmap[sy] && typeof srcBitmap[sy][sx] !== 'undefined') {
          dst._bitmap[dy + y][dx + x] = srcBitmap[sy][sx];
        }
      }
    }
  }

  function _blitClipped(src, dst, sx, sy, sw, sh, dx, dy, dw, dh) {
    var srcBitmap = src._bitmap;
    for (var y = 0; y < dh; y++) {
      for (var x = 0; x < dw; x++) {
        var srcX = Math.floor(sx + x * sw / dw);
        var srcY = Math.floor(sy + y * sh / dh);
        if (srcBitmap[srcY] && typeof srcBitmap[srcY][srcX] !== 'undefined') {
          dst._bitmap[dy + y][dx + x] = srcBitmap[srcY][srcX];
        }
      }
    }
  }
}

// ── Fixture builders ─────────────────────────────────────────────────────────

function buildState(images) {
  return {
    schema_version: '1.0',
    format_id:      'ora-canvas-v1',
    metadata:       { canvas_size: { width: 100, height: 100 } },
    view:           { zoom: 1, pan: { x: 0, y: 0 } },
    layers: [
      { id: 'background', kind: 'background', visible: true, locked: false, opacity: 1 },
      { id: 'user_input', kind: 'user_input', visible: true, locked: false, opacity: 1 }
    ],
    objects: images
  };
}

function makeImageObj(id, x, y, w, h, fillFn) {
  var rows = makeFakeBitmap(w, h, fillFn);
  return {
    id: id,
    kind: 'image',
    layer: 'user_input',
    x: x, y: y, width: w, height: h,
    image_data: {
      mime_type: 'image/x-fake',
      encoding: 'base64',
      data: bitmapToBase64(rows)
    }
  };
}

// ── Bootstrap ────────────────────────────────────────────────────────────────

// Establish a minimal `window` so the tool's auto-registration block fires.
global.window = global.window || {};

var tool = require(TOOL_PATH);
var host = makeFakeHost();

console.log('image-crop.tool.js — WP-7.4.3 test suite');
console.log('');

// ── Tests ────────────────────────────────────────────────────────────────────

(async function main() {

  // 1. §B.4 primitive surface.
  (function () {
    var ok =
      tool && tool.id === 'image-crop' &&
      typeof tool.label === 'string' &&
      typeof tool.defaultIcon === 'string' &&
      typeof tool.init === 'function' &&
      typeof tool.activate === 'function' &&
      typeof tool.deactivate === 'function' &&
      typeof tool.serializeState === 'function' &&
      typeof tool.cropImageObject === 'function';
    record('1. tool exposes §B.4 primitive surface', ok,
      ok ? '' : 'missing one or more of {id,label,defaultIcon,init,activate,deactivate,serializeState,cropImageObject}');
  })();

  // 2. Reject unknown id.
  await (async function () {
    var state = buildState([makeImageObj('img-A', 10, 20, 4, 2, function () { return 1; })]);
    var r = await tool.cropImageObject(state, 'nope', { x: 0, y: 0, width: 1, height: 1 }, { host: host });
    record('2. unknown object id rejected',
      !r.ok && r.errors.some(function (e) { return /no image object/.test(e); }),
      r.ok ? 'expected failure but got ok=true' : '');
  })();

  // 3. Out-of-bounds region rejected.
  await (async function () {
    var state = buildState([makeImageObj('img-A', 0, 0, 4, 2, function () { return 1; })]);
    var r = await tool.cropImageObject(state, 'img-A', { x: 0, y: 0, width: 10, height: 1 }, { host: host });
    record('3. out-of-bounds region rejected',
      !r.ok && r.errors.some(function (e) { return /exceeds image width/.test(e); }),
      r.ok ? 'expected failure but got ok=true' : '');
  })();

  // 4. Origin crop preserves position.
  await (async function () {
    var state = buildState([makeImageObj('img-A', 50, 60, 4, 2, function () { return 1; })]);
    var r = await tool.cropImageObject(state, 'img-A', { x: 0, y: 0, width: 2, height: 2 }, { host: host });
    var newImg = r.state.objects[0];
    var ok = r.ok && newImg.x === 50 && newImg.y === 60 && newImg.width === 2 && newImg.height === 2;
    record('4. origin crop preserves position', ok,
      ok ? '' : 'expected (x=50,y=60,w=2,h=2), got (' + newImg.x + ',' + newImg.y + ',' + newImg.width + ',' + newImg.height + ')');
  })();

  // 5. Off-origin crop shifts position by (region.x, region.y).
  await (async function () {
    var state = buildState([makeImageObj('img-A', 50, 60, 4, 2, function () { return 1; })]);
    var r = await tool.cropImageObject(state, 'img-A', { x: 1, y: 1, width: 2, height: 1 }, { host: host });
    var newImg = r.state.objects[0];
    var ok = r.ok && newImg.x === 51 && newImg.y === 61 && newImg.width === 2 && newImg.height === 1;
    record('5. off-origin crop shifts position by (region.x, region.y)', ok,
      ok ? '' : 'expected (x=51,y=61,w=2,h=1), got (' + newImg.x + ',' + newImg.y + ',' + newImg.width + ',' + newImg.height + ')');
  })();

  // 6. image_data replaced with cropped payload.
  await (async function () {
    var srcRows = [
      [10, 20, 30, 40],
      [50, 60, 70, 80]
    ];
    var imgObj = {
      id: 'img-A', kind: 'image', layer: 'user_input',
      x: 0, y: 0, width: 4, height: 2,
      image_data: { mime_type: 'image/x-fake', encoding: 'base64', data: bitmapToBase64(srcRows) }
    };
    var state = buildState([imgObj]);
    var r = await tool.cropImageObject(state, 'img-A', { x: 1, y: 0, width: 2, height: 2 }, { host: host });
    var newImg = r.state.objects[0];
    var newRows = base64ToBitmap(newImg.image_data.data);
    var expected = [[20, 30], [60, 70]];
    var ok = r.ok && JSON.stringify(newRows) === JSON.stringify(expected) && newImg.image_data.encoding === 'base64';
    record('6. image_data replaced with cropped payload', ok,
      ok ? '' : 'got rows=' + JSON.stringify(newRows));
  })();

  // 7. Locate nested image inside a group.
  await (async function () {
    var state = buildState([
      {
        id: 'grp-1', kind: 'group', layer: 'user_input',
        children: [
          makeImageObj('inner-A', 5, 5, 4, 2, function () { return 9; })
        ]
      }
    ]);
    var r = await tool.cropImageObject(state, 'inner-A', { x: 0, y: 0, width: 2, height: 1 }, { host: host });
    var inner = r.state.objects[0].children[0];
    var ok = r.ok && inner.width === 2 && inner.height === 1 && inner.x === 5 && inner.y === 5;
    record('7. locates nested image inside group children', ok,
      ok ? '' : (r.errors || []).join('; '));
    // Also check we didn't mutate the input state.
    var origInner = state.objects[0].children[0];
    record('7b. original state objects[] not mutated by crop',
      origInner.width === 4 && origInner.height === 2,
      'origInner=' + JSON.stringify({ w: origInner.width, h: origInner.height }));
  })();

  // 8. The §13.4 test contract: crop right half, position preserved.
  await (async function () {
    // 4x2 image starting at (100, 200) — pixels labelled 1..8 left to right top to bottom.
    var srcRows = [[1, 2, 3, 4], [5, 6, 7, 8]];
    var imgObj = {
      id: 'img-A', kind: 'image', layer: 'user_input',
      x: 100, y: 200, width: 4, height: 2,
      image_data: { mime_type: 'image/x-fake', encoding: 'base64', data: bitmapToBase64(srcRows) }
    };
    // Add a sibling text object so we can verify other-objects-untouched.
    var textObj = { id: 'txt-1', kind: 'text', layer: 'user_input', x: 999, y: 999, text: 'untouched' };
    var state = buildState([imgObj, textObj]);

    // Crop the RIGHT half: image-local x=2..3, full height.
    var r = await tool.cropImageObject(state, 'img-A', { x: 2, y: 0, width: 2, height: 2 }, { host: host });
    var newImg = r.state.objects[0];
    var newRows = base64ToBitmap(newImg.image_data.data);

    // Test contract checks:
    //   • cropped pixels are the right half:   [[3,4],[7,8]]
    //   • new image origin is shifted to (102, 200) so the visible
    //     pixels stay at their original screen positions
    //   • the sibling object at (999,999) is untouched
    var expectedRows = [[3, 4], [7, 8]];
    var pixelsOk = JSON.stringify(newRows) === JSON.stringify(expectedRows);
    var positionOk = (newImg.x === 102 && newImg.y === 200 && newImg.width === 2 && newImg.height === 2);
    var siblingUntouched = (r.state.objects[1] === textObj);

    record('8a. §13.4 right-half crop yields right-half pixels', pixelsOk,
      pixelsOk ? '' : 'got=' + JSON.stringify(newRows) + ' expected=' + JSON.stringify(expectedRows));
    record('8b. §13.4 new image positioned to keep visible pixels at original screen position', positionOk,
      positionOk ? '' : 'got (x=' + newImg.x + ',y=' + newImg.y + ',w=' + newImg.width + ',h=' + newImg.height + ')');
    record('8c. §13.4 sibling object untouched after crop', siblingUntouched,
      siblingUntouched ? '' : 'sibling reference replaced');

    // Also: verify the §13.4 LITERAL phrasing — "Crop the right half of an image;
    // verify left half is the new image" is satisfied by inverse: cropping the
    // left half preserves position exactly.
    var stateB = buildState([{
      id: 'img-A', kind: 'image', layer: 'user_input',
      x: 100, y: 200, width: 4, height: 2,
      image_data: { mime_type: 'image/x-fake', encoding: 'base64', data: bitmapToBase64(srcRows) }
    }]);
    var rB = await tool.cropImageObject(stateB, 'img-A', { x: 0, y: 0, width: 2, height: 2 }, { host: host });
    var newImgB = rB.state.objects[0];
    var newRowsB = base64ToBitmap(newImgB.image_data.data);
    var leftPixelsOk = JSON.stringify(newRowsB) === JSON.stringify([[1, 2], [5, 6]]);
    var leftPositionOk = (newImgB.x === 100 && newImgB.y === 200);
    record('8d. §13.4 left-half crop yields left-half pixels at original (x,y)',
      leftPixelsOk && leftPositionOk,
      'rows=' + JSON.stringify(newRowsB) + ' pos=(' + newImgB.x + ',' + newImgB.y + ')');
  })();

  // 9. Registration on window.OraTools.
  (function () {
    var ok = global.window && global.window.OraTools && global.window.OraTools['image-crop'] === tool;
    record('9. registers on window.OraTools[\'image-crop\']', ok,
      ok ? '' : 'window.OraTools registry not populated');
  })();

  // 10. activate / deactivate are no-ops without a Konva panel.
  (function () {
    var threw = false;
    try {
      tool.init(null, {});
      tool.activate({});
      tool.deactivate({});
    } catch (e) {
      threw = true;
    }
    record('10. activate/deactivate no-op without panel', !threw,
      threw ? 'threw on no-panel path' : '');
  })();

  summarize();
})().catch(function (err) {
  console.error('FATAL:', err && err.stack ? err.stack : err);
  process.exit(2);
});
