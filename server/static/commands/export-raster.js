/**
 * export-raster.js — WP-7.4.9a
 *
 * Implements the **Export → PNG** and **Export → JPG** commands per Visual
 * Intelligence Implementation Plan §11.7 ("Canvas Mechanics — Export") and
 * §13.4 WP-7.4.9 (sub-WP a: raster).
 *
 *   Photoshop equivalent:  File → Export → PNG  /  File → Export → JPEG
 *
 * ── Architecture ────────────────────────────────────────────────────────────
 *
 * Self-registering IIFE alongside `save-canvas.js` (WP-7.4.8). Reuses two
 * helpers from that module:
 *
 *   * `OraSaveCanvas.buildCanvasState(panel)`        — Konva → state object
 *   * `OraSaveCanvas.computeContentExtent(state, m)` — bbox + margin
 *
 * Sub-WPs b (SVG) and c (PDF) live in their own modules and do not collide
 * here; this module's contract is RASTER ONLY.
 *
 * ── Export scope (Plan §11.7) ───────────────────────────────────────────────
 *
 * Like Save, raster export is bounded to:
 *
 *     bbox(all rendered objects) + 100 px margin on each side
 *
 * The bbox computation reuses `OraSaveCanvas.computeContentExtent` so the
 * export footprint matches the saved canvas-state footprint byte-for-byte
 * (no surprise empty space, no missed objects).
 *
 * For an empty canvas, the export falls back to the stage's current
 * dimensions — there's nothing to bound, but the user still expects a file.
 *
 * ── Rasterization (Konva) ───────────────────────────────────────────────────
 *
 * Konva's `stage.toDataURL({ mimeType, quality, pixelRatio, x, y, width,
 * height })` renders the stage to a data URL. We pass the bounded extent
 * via x/y/width/height so the output matches the bbox exactly.
 *
 *   PNG: lossless, transparent background where no pixels are drawn.
 *        Konva renders transparency by default unless a stage background
 *        fill exists; we leave it alone — the user's background layer
 *        (SVG/raster) provides any opacity they want.
 *
 *   JPG: lossy, no transparency. We compose against opaque white before
 *        encoding so transparent regions don't become black (the JPEG
 *        encoder's default for unset alpha). Quality is configurable
 *        (default 0.92 — Photoshop's "12/maximum" equivalent).
 *
 * ── Download ────────────────────────────────────────────────────────────────
 *
 * No native file picker is available from the browser — the closest we can
 * get is an anchor with the `download` attribute, which prompts the user
 * to save (subject to their browser's download settings). The filename is
 * derived from the conversation_id + timestamp + extension.
 *
 * ── Share-reminder integration (WP-7.7.6) ───────────────────────────────────
 *
 * Export expands the canvas's audience beyond the local sessions/ directory
 * (the user explicitly chose to write a file they'll likely share). So we
 * dispatch `ora:canvas-pre-share` with `intent: 'export'` BEFORE triggering
 * the download, and only proceed when the reminder confirms.
 *
 * ── Public surface — exposed as `window.OraExportRaster` ────────────────────
 *
 *   exportPNG(panel, opts?) → Promise<{ ok, dataUrl?, filename, extent, cancelled? }>
 *     Export the canvas as PNG. Lossless. Honors content extent + 100 px margin.
 *
 *   exportJPG(panel, opts?) → Promise<{ ok, dataUrl?, filename, extent, cancelled? }>
 *     Export the canvas as JPEG. Lossy. White-composited to drop alpha.
 *     `opts.quality` (0–1, default 0.92) controls JPEG quality.
 *
 *   `opts` shape (both):
 *     {
 *       conversation_id?: string,    // filename prefix; defaults to panel.config
 *       filename?:        string,    // explicit filename (overrides default)
 *       marginPx?:        number,    // override default 100 px margin
 *       pixelRatio?:      number,    // device-pixel scaling factor (default 2)
 *       quality?:         number,    // JPG only: 0–1 (default 0.92)
 *       dryRun?:          boolean,   // skip download; return dataUrl for tests
 *     }
 *
 *   _computeExportRect(panel, marginPx) → { x, y, width, height } | null
 *     Internal helper; exposed for tests. Reuses save-canvas's content-extent
 *     calculation. Returns null when the panel has no stage.
 *
 *   _triggerDownload(dataUrl, filename) → void
 *     Internal helper; exposed for tests. Creates a hidden anchor with the
 *     `download` attribute and clicks it.
 *
 * ── Constraints ─────────────────────────────────────────────────────────────
 *
 *   * Pure, stateless module. No timers, no DOM mutation outside the
 *     transient anchor element used for the download trigger.
 *   * Does NOT touch save-canvas.js or visual-panel.js. Reads only.
 *   * Test mode: when `opts.dryRun=true`, returns `{ ok, dataUrl, filename,
 *     extent }` without dispatching the share gate or creating the anchor.
 *   * Coordinates with WP-7.4.9b (SVG) and WP-7.4.9c (PDF): each WP owns its
 *     own module file. Shared helpers come from `OraSaveCanvas`.
 */

(function (root) {
  'use strict';

  // ── Constants ─────────────────────────────────────────────────────────────

  var DEFAULT_MARGIN_PX     = 100;     // matches save-canvas (Plan §11.7)
  var DEFAULT_PIXEL_RATIO   = 2;       // 2× for retina-quality export
  var DEFAULT_JPG_QUALITY   = 0.92;    // PS "12/maximum" equivalent
  var JPG_BG_COLOR          = '#FFFFFF';

  var MIME_PNG = 'image/png';
  var MIME_JPG = 'image/jpeg';

  // ── Helpers ───────────────────────────────────────────────────────────────

  function _isObj(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }
  function _isFiniteNumber(v) { return typeof v === 'number' && isFinite(v); }
  function _isPositiveNumber(v) { return _isFiniteNumber(v) && v > 0; }

  function _getSaveCanvas() {
    return (typeof window !== 'undefined' && window.OraSaveCanvas) || null;
  }
  function _getReminder() {
    return (typeof window !== 'undefined' && window.OraCanvasShareReminder) || null;
  }

  function _timestamp() {
    // Filesystem-safe ISO-ish: 2026-04-30T07-30-00
    var d = new Date();
    var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
           'T' + pad(d.getHours()) + '-' + pad(d.getMinutes()) + '-' + pad(d.getSeconds());
  }

  function _defaultFilename(conversationId, ext) {
    var prefix = (conversationId && typeof conversationId === 'string') ? conversationId : 'canvas';
    return prefix + '-' + _timestamp() + '.' + ext;
  }

  // ── Export rect computation ──────────────────────────────────────────────

  /**
   * Compute the bounded rect to rasterize: content bbox + margin. Reuses
   * save-canvas's `buildCanvasState` + `computeContentExtent` so the export
   * footprint exactly matches the save footprint.
   *
   * Returns null when the panel has no stage. Falls back to stage dimensions
   * when the canvas is empty.
   */
  function _computeExportRect(panel, marginPx) {
    if (!panel || !panel.stage || typeof panel.stage.width !== 'function') return null;
    var sc = _getSaveCanvas();
    var margin = _isFiniteNumber(marginPx) ? marginPx : DEFAULT_MARGIN_PX;

    if (sc && typeof sc.buildCanvasState === 'function' && typeof sc.computeContentExtent === 'function') {
      try {
        var state = sc.buildCanvasState(panel);
        var extent = sc.computeContentExtent(state, margin);
        if (extent && _isPositiveNumber(extent.width) && _isPositiveNumber(extent.height)) {
          return {
            x:      extent.x,
            y:      extent.y,
            width:  extent.width,
            height: extent.height,
          };
        }
      } catch (e) { /* fall through to stage-size default */ }
    }

    // Empty canvas (or save-canvas unavailable in tests) — use stage dims.
    var w = panel.stage.width();
    var h = panel.stage.height();
    if (!_isPositiveNumber(w) || !_isPositiveNumber(h)) return null;
    return { x: 0, y: 0, width: w, height: h };
  }

  // ── Konva rasterization ───────────────────────────────────────────────────

  /**
   * Call `stage.toDataURL` with the export rect + format options. Returns
   * the data URL or null on failure (caller decides how to surface).
   */
  function _rasterize(panel, rect, mimeType, quality, pixelRatio) {
    if (!panel || !panel.stage || typeof panel.stage.toDataURL !== 'function') return null;
    var args = {
      mimeType:   mimeType,
      pixelRatio: _isPositiveNumber(pixelRatio) ? pixelRatio : DEFAULT_PIXEL_RATIO,
      x:          rect.x,
      y:          rect.y,
      width:      rect.width,
      height:     rect.height,
    };
    if (mimeType === MIME_JPG && _isFiniteNumber(quality)) args.quality = quality;
    try {
      return panel.stage.toDataURL(args);
    } catch (e) {
      if (typeof console !== 'undefined' && console.warn) {
        console.warn('[export-raster] toDataURL failed: ' + (e && e.message ? e.message : e));
      }
      return null;
    }
  }

  /**
   * Compose a transparent PNG data URL onto an opaque white background and
   * return a JPEG data URL. Used for JPG export so transparent regions
   * don't render as black (JPEG has no alpha channel).
   *
   * Pure synchronous on failure → returns the original data URL untouched
   * so the export still produces a file.
   */
  function _composeJpgOnWhite(pngDataUrl, rect, pixelRatio, quality) {
    if (typeof document === 'undefined' || !pngDataUrl) return pngDataUrl;
    var pr = _isPositiveNumber(pixelRatio) ? pixelRatio : DEFAULT_PIXEL_RATIO;
    var w = Math.max(1, Math.round(rect.width  * pr));
    var h = Math.max(1, Math.round(rect.height * pr));
    try {
      var canvas = document.createElement('canvas');
      canvas.width  = w;
      canvas.height = h;
      var ctx = canvas.getContext('2d');
      if (!ctx) return pngDataUrl;
      // White fill first.
      ctx.fillStyle = JPG_BG_COLOR;
      ctx.fillRect(0, 0, w, h);
      // Draw the PNG on top — but we can only do that asynchronously via
      // an Image. Since the public API returns a Promise, we fold the
      // image-load wait into the calling chain via _composeJpgOnWhiteAsync.
      // This sync helper returns null to indicate "use async".
      return null;
    } catch (e) {
      return pngDataUrl;
    }
  }

  function _composeJpgOnWhiteAsync(pngDataUrl, rect, pixelRatio, quality) {
    return new Promise(function (resolve) {
      if (typeof document === 'undefined' || !pngDataUrl) { resolve(pngDataUrl); return; }
      var pr = _isPositiveNumber(pixelRatio) ? pixelRatio : DEFAULT_PIXEL_RATIO;
      var w = Math.max(1, Math.round(rect.width  * pr));
      var h = Math.max(1, Math.round(rect.height * pr));
      var canvas, ctx;
      try {
        canvas = document.createElement('canvas');
        canvas.width  = w;
        canvas.height = h;
        ctx = canvas.getContext('2d');
        if (!ctx) { resolve(pngDataUrl); return; }
        ctx.fillStyle = JPG_BG_COLOR;
        ctx.fillRect(0, 0, w, h);
      } catch (e) { resolve(pngDataUrl); return; }
      var img = new Image();
      img.onload = function () {
        try {
          ctx.drawImage(img, 0, 0, w, h);
          var q = _isFiniteNumber(quality) ? quality : DEFAULT_JPG_QUALITY;
          resolve(canvas.toDataURL(MIME_JPG, q));
        } catch (e) {
          resolve(pngDataUrl);
        }
      };
      img.onerror = function () { resolve(pngDataUrl); };
      img.src = pngDataUrl;
    });
  }

  // ── Download trigger ─────────────────────────────────────────────────────

  /**
   * Trigger a browser download via a transient anchor element. Browsers
   * with download-prompt settings will show the file picker; otherwise
   * the file lands in the configured downloads folder.
   *
   * No-op when `document` is unavailable (test/headless mode).
   */
  function _triggerDownload(dataUrl, filename) {
    if (typeof document === 'undefined' || !dataUrl) return;
    try {
      var a = document.createElement('a');
      a.href = dataUrl;
      a.download = filename || 'canvas.png';
      // Some browsers require the anchor to be in the DOM to honor `download`.
      a.style.display = 'none';
      if (document.body) document.body.appendChild(a);
      a.click();
      if (document.body && a.parentNode === document.body) {
        document.body.removeChild(a);
      }
    } catch (e) {
      if (typeof console !== 'undefined' && console.warn) {
        console.warn('[export-raster] download trigger failed: ' + (e && e.message ? e.message : e));
      }
    }
  }

  // ── Share-reminder gate ──────────────────────────────────────────────────

  /**
   * Run the export through the share-reminder gate. Returns a Promise that
   * resolves to the user's choice. When the reminder module isn't loaded,
   * we still dispatch `ora:canvas-pre-share` for any other listeners and
   * proceed.
   */
  function _runShareGate(conversationId, filename) {
    return new Promise(function (resolve) {
      var reminder = _getReminder();
      var detail = {
        intent:    'export',
        path:      filename || conversationId || 'canvas',
        onConfirm: function () { resolve({ confirmed: true }); },
        onCancel:  function () { resolve({ confirmed: false }); },
      };
      if (reminder && typeof reminder.requestShare === 'function') {
        reminder.requestShare(detail);
        return;
      }
      // No reminder module — dispatch the event for any other listeners
      // and resolve confirmed (export is the user's explicit ask).
      if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
        try {
          var evt = new CustomEvent('ora:canvas-pre-share', { detail: detail });
          window.dispatchEvent(evt);
        } catch (e) { /* CustomEvent unavailable; fall through */ }
      }
      resolve({ confirmed: true });
    });
  }

  // ── Public: exportPNG / exportJPG ─────────────────────────────────────────

  function _exportRaster(panel, mimeType, opts) {
    opts = opts || {};
    if (!panel) return Promise.reject(new Error('export-raster: panel is required'));

    var marginPx = _isFiniteNumber(opts.marginPx)   ? opts.marginPx   : DEFAULT_MARGIN_PX;
    var pixelRatio = _isPositiveNumber(opts.pixelRatio) ? opts.pixelRatio : DEFAULT_PIXEL_RATIO;
    var quality  = _isFiniteNumber(opts.quality)    ? opts.quality    : DEFAULT_JPG_QUALITY;

    var rect = _computeExportRect(panel, marginPx);
    if (!rect) return Promise.reject(new Error('export-raster: could not compute export rect'));

    var ext = (mimeType === MIME_JPG) ? 'jpg' : 'png';
    var conversationId = opts.conversation_id || (panel.config && panel.config.conversation_id) || 'canvas';
    var filename = (typeof opts.filename === 'string' && opts.filename) ? opts.filename : _defaultFilename(conversationId, ext);

    // For JPG, rasterize PNG first, then composite to white before encoding.
    // Konva's toDataURL with mimeType='image/jpeg' produces black where
    // alpha=0; we fix that by going PNG → canvas-on-white → JPEG.
    var rasterPromise;
    if (mimeType === MIME_JPG) {
      var pngUrl = _rasterize(panel, rect, MIME_PNG, undefined, pixelRatio);
      if (!pngUrl) return Promise.reject(new Error('export-raster: rasterization failed'));
      rasterPromise = _composeJpgOnWhiteAsync(pngUrl, rect, pixelRatio, quality);
    } else {
      var pngDirect = _rasterize(panel, rect, MIME_PNG, undefined, pixelRatio);
      if (!pngDirect) return Promise.reject(new Error('export-raster: rasterization failed'));
      rasterPromise = Promise.resolve(pngDirect);
    }

    return rasterPromise.then(function (dataUrl) {
      var result = {
        ok:       true,
        dataUrl:  dataUrl,
        filename: filename,
        extent:   rect,
        mimeType: mimeType,
      };

      if (opts.dryRun) return result;

      return _runShareGate(conversationId, filename).then(function (gate) {
        if (!gate.confirmed) {
          return { ok: false, cancelled: true, filename: filename, extent: rect, mimeType: mimeType };
        }
        _triggerDownload(dataUrl, filename);
        return result;
      });
    });
  }

  function exportPNG(panel, opts) {
    return _exportRaster(panel, MIME_PNG, opts);
  }

  function exportJPG(panel, opts) {
    return _exportRaster(panel, MIME_JPG, opts);
  }

  // ── Module export ────────────────────────────────────────────────────────

  var ns = {
    DEFAULT_MARGIN_PX:   DEFAULT_MARGIN_PX,
    DEFAULT_PIXEL_RATIO: DEFAULT_PIXEL_RATIO,
    DEFAULT_JPG_QUALITY: DEFAULT_JPG_QUALITY,
    MIME_PNG:            MIME_PNG,
    MIME_JPG:            MIME_JPG,
    exportPNG:           exportPNG,
    exportJPG:           exportJPG,
    // Internals exposed for tests.
    _computeExportRect:   _computeExportRect,
    _rasterize:           _rasterize,
    _composeJpgOnWhiteAsync: _composeJpgOnWhiteAsync,
    _triggerDownload:     _triggerDownload,
    _runShareGate:        _runShareGate,
    _defaultFilename:     _defaultFilename,
  };

  if (typeof window !== 'undefined') {
    window.OraExportRaster = ns;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = ns;
  }
})(typeof window !== 'undefined' ? window : this);
