/**
 * export-pdf.js — WP-7.4.9c
 *
 * Implements the **Export → PDF** workspace command per Visual Intelligence
 * Implementation Plan §11.7 ("Canvas Mechanics — Export") and §13.4 WP-7.4.9
 * (sub-WP c, PDF export).
 *
 *   Photoshop equivalent:  File → Export As → PDF
 *
 * Sister commands (Plan §13.4 WP-7.4.9 a/b/d):
 *   a) export-png.js   — single PNG of the bounded content extent.
 *   b) export-svg.js   — vector export (where the artifact is SVG).
 *   c) export-pdf.js   — THIS module. Single-page PDF for single-canvas
 *                         export. Multi-panel layouts (e.g. comic pages)
 *                         export as a single page showing the layout —
 *                         multi-page PDF deferred per WP brief.
 *   d) export-md.js    — vault-style markdown bundle.
 *
 * ── Approach (per WP brief) ────────────────────────────────────────────────
 *
 * 1. Compute the bounded export extent: union bbox of all content across the
 *    four Konva layers + 100 px margin. Reuses
 *    `OraSaveCanvas.computeContentExtent` from WP-7.4.8 (which itself shares
 *    geometry primitives with `OraResizeCanvas` / `OraCropToContent`) so the
 *    same "content + 100 px margin" rule covers Save, Crop, and Export with
 *    one definition.
 *
 *    Empty canvas → no content to export → throw E_NO_CONTENT. Caller is
 *    expected to gate the toolbar entry via the existing
 *    `enabled_when: "canvas_has_content"` predicate (same gate the other
 *    Phase-7 commands use).
 *
 * 2. Rasterize the bounded region via `stage.toDataURL` at print-quality
 *    pixelRatio (default 2× — 144 dpi at default 72 dpi base, configurable
 *    via opts.pixelRatio). The toDataURL `x`/`y`/`width`/`height` args
 *    select the bounded region from the larger logical canvas, so the
 *    rasterization captures content + margin only — empty space outside
 *    that extent is dropped.
 *
 * 3. Embed the PNG in a jsPDF page sized to the extent (in PDF user units —
 *    we use 'pt' so 1 unit = 1 px at 72 dpi, keeping the page dimensions
 *    numerically equal to the canvas pixel dimensions). The image fills
 *    the page edge-to-edge; the 100 px margin is already baked into the
 *    rasterized extent.
 *
 * 4. Save via `doc.save(filename)` which triggers a browser download.
 *
 * 5. Dispatch `ora:canvas-pre-share` with `intent: 'export'` BEFORE the
 *    download fires. The WP-7.7.6 share-reminder modal listens for this
 *    event and gates the action with a one-time-per-session confirm. If
 *    the user cancels at the modal, the download is skipped and `apply()`
 *    resolves with `{ ok: false, cancelled: true }`.
 *
 * ── Architecture ────────────────────────────────────────────────────────────
 *
 * Self-registering IIFE that lives alongside `save-canvas.js` /
 * `crop-to-content.js`. Reuses (in priority order):
 *
 *   * `OraSaveCanvas.buildCanvasState`        — Konva → canvas-state object
 *                                               translation (so extent is
 *                                               computed off the same shape
 *                                               that Save persists).
 *   * `OraSaveCanvas.computeContentExtent`    — bbox + margin in
 *                                               canvas-state coords.
 *   * `OraResizeCanvas.computeBoundingBox`    — Konva-native bbox fallback
 *                                               (used when state-based
 *                                               extent is null but the
 *                                               panel still has nodes — e.g.
 *                                               canvas-state hasn't been
 *                                               primed yet).
 *   * `OraCanvasShareReminder.requestShare`   — share gate (intent: 'export').
 *
 * It does NOT depend on:
 *   * The server `/api/canvas/save` endpoint (export is client-side only).
 *   * canvas-file-format.js (PDF export bypasses the .ora-canvas serializer
 *     entirely — we go Konva → PNG → PDF, never through the canvas-state
 *     gzipped artifact).
 *
 * It DOES depend on:
 *   * `window.jspdf.jsPDF` from `vendor/jspdf/jspdf.umd.min.js` (must be
 *     loaded in index.html ahead of this command).
 *   * `panel.stage.toDataURL` from Konva.
 *
 * ── Public surface — exposed as `window.OraExportPdf` ──────────────────────
 *
 *   DEFAULT_MARGIN_PX = 100      // px, per Plan §11.7 (matches Save)
 *   DEFAULT_PIXEL_RATIO = 2      // 2× for print quality
 *   DEFAULT_FILENAME = 'canvas.pdf'
 *
 *   apply(panel, opts) → Promise<{
 *       ok, cancelled?, filename?, extent, pixelRatio,
 *       page: { width, height, unit }, bytes?, dataUrl?,
 *     }>
 *     Run the full export pipeline. Resolves with the saved filename on
 *     success, or `{ ok: false, cancelled: true }` if the user dismisses
 *     the share-reminder modal. Throws (rejects) on:
 *       - E_NO_CONTENT     — empty canvas, nothing to export.
 *       - E_NO_JSPDF       — vendor library not loaded.
 *       - E_NO_STAGE       — panel.stage / panel.stage.toDataURL absent.
 *       - E_RASTER_FAILED  — toDataURL threw or returned empty.
 *       - E_PDF_FAILED     — jsPDF threw during addImage / save.
 *
 *     `opts` shape (all optional):
 *       {
 *         filename:     string,    // default 'canvas.pdf'
 *         marginPx:     number,    // default 100; clamped to >= 0
 *         pixelRatio:   number,    // default 2; clamped to > 0
 *         dryRun:       boolean,   // skip share-reminder + skip doc.save();
 *                                  // return bytes + dataUrl for tests
 *         skipShareGate: boolean,  // skip share-reminder dispatch (test-only)
 *       }
 *
 *   computeExportExtent(panel, marginPx?) → { x, y, width, height } | null
 *     Pure helper. Computes the bounded export extent for the panel using
 *     the same content+margin convention Save uses. Returns null when the
 *     panel has no content.
 *
 *   rasterize(panel, extent, pixelRatio?) → string  (data URL)
 *     Pure helper. Rasterizes a stage region via `stage.toDataURL`. Returns
 *     a 'image/png' data URL covering exactly `extent` (in stage-local
 *     coords) at the requested pixel ratio.
 *
 *   buildPdf(dataUrl, extent, opts?) → { doc, page }
 *     Build a single-page jsPDF document with the rasterized PNG embedded
 *     edge-to-edge. Page dimensions equal `extent` in 'pt' units. Returns
 *     the live `jsPDF` instance + a `page` summary; caller drives `.save()`
 *     or `.output()`.
 *
 * ── Test criterion (per §13.4 WP-7.4.9c) ────────────────────────────────────
 *
 *   "Export PDF for a representative canvas; verify renders in Preview /
 *    Acrobat."
 *
 *   The acceptance check verifies:
 *     1. apply() resolves with ok: true and a non-empty filename.
 *     2. The page dimensions equal extent.width × extent.height in 'pt'.
 *     3. The embedded PNG covers the page edge-to-edge.
 *     4. The output bytes start with '%PDF-' (the PDF magic header).
 *
 *   Live verification: open the saved file in macOS Preview + Adobe
 *   Acrobat — both should render the canvas content with the 100 px margin
 *   visible around the artifact.
 *
 * ── Multi-panel layout note ────────────────────────────────────────────────
 *
 * Per the WP brief: "Multi-panel layouts (e.g. comic pages) export as a
 * single page showing the layout — multi-page PDF deferred." This module
 * implements that "single page showing the layout" branch — even if the
 * canvas contains multiple comic panels arranged on the four layers, they
 * all render to one page sized to the union extent. Splitting per panel is
 * a future workpacket (likely WP-7.4.9c-ext or a successor).
 */

(function (root) {
  'use strict';

  // ── Constants ─────────────────────────────────────────────────────────────

  var DEFAULT_MARGIN_PX   = 100;             // px, per Plan §11.7 (matches Save)
  var DEFAULT_PIXEL_RATIO = 2;               // 2× for print quality
  var DEFAULT_FILENAME    = 'canvas.pdf';
  var PDF_UNIT            = 'pt';            // 1 unit = 1 px at 72 dpi base

  // ── Type guards ───────────────────────────────────────────────────────────

  function _isObj(v)            { return v !== null && typeof v === 'object' && !Array.isArray(v); }
  function _isFiniteNumber(v)   { return typeof v === 'number' && isFinite(v); }
  function _isPositiveNumber(v) { return _isFiniteNumber(v) && v > 0; }
  function _isNonNegNumber(v)   { return _isFiniteNumber(v) && v >= 0; }
  function _isNonEmptyString(v) { return typeof v === 'string' && v.length > 0; }

  // ── Module resolvers ──────────────────────────────────────────────────────

  function _saveCanvas() {
    return (typeof window !== 'undefined' && window.OraSaveCanvas) || null;
  }
  function _resizeCanvas() {
    return (typeof window !== 'undefined' && window.OraResizeCanvas) || null;
  }
  function _shareReminder() {
    return (typeof window !== 'undefined' && window.OraCanvasShareReminder) || null;
  }
  function _jsPdfCtor() {
    if (typeof window === 'undefined') return null;
    if (window.jspdf && typeof window.jspdf.jsPDF === 'function') return window.jspdf.jsPDF;
    if (typeof window.jsPDF === 'function') return window.jsPDF;
    return null;
  }

  // ── Extent computation ────────────────────────────────────────────────────

  /**
   * Compute the bounded export extent for the panel. Tries OraSaveCanvas's
   * canvas-state-based extent first (so Save and Export agree on what
   * "content + margin" means), and falls back to OraResizeCanvas's Konva-
   * native bounding box when the canvas-state hasn't been primed yet (e.g.
   * fresh panel that hasn't run a save cycle).
   *
   * Returns { x, y, width, height } in stage-local coordinates, or null
   * when there's no content.
   */
  function computeExportExtent(panel, marginPx) {
    if (!panel) return null;
    var margin = _isNonNegNumber(marginPx) ? marginPx : DEFAULT_MARGIN_PX;

    // Path 1 — canvas-state-based (preferred; mirrors Save scope exactly).
    var sc = _saveCanvas();
    if (sc && typeof sc.buildCanvasState === 'function'
           && typeof sc.computeContentExtent === 'function') {
      try {
        var state  = sc.buildCanvasState(panel);
        var extent = sc.computeContentExtent(state, margin);
        if (extent && _isPositiveNumber(extent.width) && _isPositiveNumber(extent.height)) {
          return extent;
        }
      } catch (e) { /* fall through to Konva-native */ }
    }

    // Path 2 — Konva-native bbox + margin (fallback).
    var rc = _resizeCanvas();
    if (rc && typeof rc.computeBoundingBox === 'function') {
      try {
        var bb = rc.computeBoundingBox(panel);
        if (bb && bb.union
               && _isFiniteNumber(bb.union.x) && _isFiniteNumber(bb.union.y)
               && _isPositiveNumber(bb.union.width) && _isPositiveNumber(bb.union.height)) {
          return {
            x:      bb.union.x      - margin,
            y:      bb.union.y      - margin,
            width:  bb.union.width  + margin * 2,
            height: bb.union.height + margin * 2,
          };
        }
      } catch (e) { /* fall through to null */ }
    }
    return null;
  }

  // ── Rasterization ─────────────────────────────────────────────────────────

  /**
   * Rasterize a stage region via Konva's `stage.toDataURL`. The
   * `x`/`y`/`width`/`height` args clip to the requested extent in stage-
   * local coordinates; `pixelRatio` controls the raster density (2× by
   * default for print quality).
   *
   * Returns a 'image/png' data URL string.
   */
  function rasterize(panel, extent, pixelRatio) {
    if (!panel || !panel.stage || typeof panel.stage.toDataURL !== 'function') {
      var noStage = new Error('export-pdf: panel.stage.toDataURL unavailable');
      noStage.code = 'E_NO_STAGE';
      throw noStage;
    }
    if (!_isObj(extent)
        || !_isFiniteNumber(extent.x) || !_isFiniteNumber(extent.y)
        || !_isPositiveNumber(extent.width) || !_isPositiveNumber(extent.height)) {
      var bad = new Error('export-pdf: extent { x, y, width, height } required');
      bad.code = 'E_BAD_EXTENT';
      throw bad;
    }
    var pr = _isPositiveNumber(pixelRatio) ? pixelRatio : DEFAULT_PIXEL_RATIO;
    var dataUrl;
    try {
      dataUrl = panel.stage.toDataURL({
        mimeType:   'image/png',
        x:          extent.x,
        y:          extent.y,
        width:      extent.width,
        height:     extent.height,
        pixelRatio: pr,
      });
    } catch (e) {
      var fail = new Error('export-pdf: stage.toDataURL threw — ' + (e && e.message ? e.message : e));
      fail.code  = 'E_RASTER_FAILED';
      fail.cause = e;
      throw fail;
    }
    if (!_isNonEmptyString(dataUrl) || dataUrl.indexOf('data:image/') !== 0) {
      var empty = new Error('export-pdf: stage.toDataURL returned empty/invalid data URL');
      empty.code = 'E_RASTER_FAILED';
      throw empty;
    }
    return dataUrl;
  }

  // ── PDF assembly ──────────────────────────────────────────────────────────

  /**
   * Build a single-page jsPDF document with the rasterized PNG embedded
   * edge-to-edge. The page is sized to `extent.width × extent.height` in
   * 'pt' units so 1 user unit = 1 canvas pixel — keeping the content's
   * absolute pixel size when printed at default scaling.
   *
   * Orientation is auto-derived from extent (landscape if w > h, portrait
   * otherwise).
   */
  function buildPdf(dataUrl, extent, opts) {
    var Ctor = _jsPdfCtor();
    if (!Ctor) {
      var noLib = new Error('export-pdf: jsPDF not loaded (window.jspdf.jsPDF missing)');
      noLib.code = 'E_NO_JSPDF';
      throw noLib;
    }
    if (!_isObj(extent)
        || !_isPositiveNumber(extent.width) || !_isPositiveNumber(extent.height)) {
      var badExt = new Error('export-pdf: extent.width / extent.height must be positive numbers');
      badExt.code = 'E_BAD_EXTENT';
      throw badExt;
    }
    if (!_isNonEmptyString(dataUrl)) {
      var badData = new Error('export-pdf: dataUrl is required');
      badData.code = 'E_BAD_DATA';
      throw badData;
    }
    opts = _isObj(opts) ? opts : {};

    var orientation = (extent.width > extent.height) ? 'landscape' : 'portrait';
    var doc;
    try {
      doc = new Ctor({
        orientation: orientation,
        unit:        PDF_UNIT,
        format:      [extent.width, extent.height],
        compress:    opts.compress !== false,    // default true; smaller files
      });
    } catch (e) {
      var ctorFail = new Error('export-pdf: new jsPDF threw — ' + (e && e.message ? e.message : e));
      ctorFail.code  = 'E_PDF_FAILED';
      ctorFail.cause = e;
      throw ctorFail;
    }
    try {
      // 'PNG' format string + (x=0, y=0, w=extent.width, h=extent.height)
      // → image fills the page edge-to-edge. The 100 px margin is already
      //   baked into extent (margin around content), so the PDF page itself
      //   has no extra padding — the white space at the edges is the margin.
      doc.addImage(dataUrl, 'PNG', 0, 0, extent.width, extent.height, undefined, 'FAST');
    } catch (e2) {
      var addFail = new Error('export-pdf: doc.addImage threw — ' + (e2 && e2.message ? e2.message : e2));
      addFail.code  = 'E_PDF_FAILED';
      addFail.cause = e2;
      throw addFail;
    }
    return {
      doc:  doc,
      page: { width: extent.width, height: extent.height, unit: PDF_UNIT, orientation: orientation },
    };
  }

  // ── Filename derivation ──────────────────────────────────────────────────

  function _deriveFilename(panel, opts) {
    if (opts && _isNonEmptyString(opts.filename)) {
      var f = opts.filename;
      // Always end in .pdf — append if the caller forgot.
      return /\.pdf$/i.test(f) ? f : (f + '.pdf');
    }
    var conv = (panel && panel.config && panel.config.conversation_id) || null;
    if (_isNonEmptyString(conv)) return 'canvas-' + conv + '.pdf';
    return DEFAULT_FILENAME;
  }

  // ── Share-reminder gate dispatch ──────────────────────────────────────────

  /**
   * Dispatch `ora:canvas-pre-share` with intent: 'export'. The WP-7.7.6
   * share-reminder modal listens and gates the action with a one-time-per-
   * session confirm. If the user cancels, `onCancel` resolves the promise
   * with cancelled=true and the export aborts before doc.save().
   *
   * Two paths:
   *   1. `OraCanvasShareReminder.requestShare` is available (the typical
   *      runtime case) — call it directly with onConfirm/onCancel callbacks.
   *   2. The reminder module is missing (test/headless) — dispatch a
   *      CustomEvent on window for any listener that wants to observe;
   *      proceed immediately (no gate).
   */
  function _gateShare(filename, onConfirm, onCancel) {
    var reminder = _shareReminder();
    if (reminder && typeof reminder.requestShare === 'function') {
      reminder.requestShare({
        intent:    'export',
        path:      filename,
        onConfirm: onConfirm,
        onCancel:  onCancel,
      });
      return;
    }
    // No reminder module — best-effort CustomEvent dispatch, then proceed.
    if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function'
                                      && typeof CustomEvent === 'function') {
      try {
        window.dispatchEvent(new CustomEvent('ora:canvas-pre-share', {
          detail: {
            intent:    'export',
            path:      filename,
            onConfirm: onConfirm,
            onCancel:  onCancel,
          },
        }));
        return;
      } catch (e) { /* fall through */ }
    }
    // Last resort — straight through.
    onConfirm();
  }

  // ── Public command API ───────────────────────────────────────────────────

  /**
   * Run the full Export → PDF pipeline. See module header for full contract.
   * Returns Promise<{ ok, cancelled?, filename?, extent, pixelRatio, page,
   *                   bytes?, dataUrl? }>.
   */
  function apply(panel, opts) {
    opts = _isObj(opts) ? opts : {};
    if (!panel) {
      return Promise.reject(new Error('export-pdf: panel is required'));
    }
    if (!_jsPdfCtor()) {
      var noLib = new Error('export-pdf: jsPDF not loaded — vendor/jspdf/jspdf.umd.min.js required');
      noLib.code = 'E_NO_JSPDF';
      return Promise.reject(noLib);
    }

    var marginPx   = _isNonNegNumber(opts.marginPx)   ? opts.marginPx   : DEFAULT_MARGIN_PX;
    var pixelRatio = _isPositiveNumber(opts.pixelRatio) ? opts.pixelRatio : DEFAULT_PIXEL_RATIO;

    var extent = computeExportExtent(panel, marginPx);
    if (!extent) {
      var noContent = new Error('export-pdf: panel has no content; nothing to export.');
      noContent.code = 'E_NO_CONTENT';
      return Promise.reject(noContent);
    }

    // Rasterize + build the PDF synchronously; toDataURL is sync in Konva.
    var dataUrl, built;
    try {
      dataUrl = rasterize(panel, extent, pixelRatio);
      built   = buildPdf(dataUrl, extent, opts);
    } catch (e) {
      return Promise.reject(e);
    }

    var filename = _deriveFilename(panel, opts);

    // dryRun / skipShareGate test paths — skip share gate and skip download.
    if (opts.dryRun) {
      var bytes = null;
      try { bytes = built.doc.output('arraybuffer'); } catch (e) { /* ignore in tests */ }
      return Promise.resolve({
        ok:         true,
        filename:   filename,
        extent:     extent,
        pixelRatio: pixelRatio,
        page:       built.page,
        bytes:      bytes,
        dataUrl:    dataUrl,
      });
    }

    return new Promise(function (resolve, reject) {
      var doConfirm = function () {
        try {
          built.doc.save(filename);
        } catch (e) {
          var fail = new Error('export-pdf: doc.save threw — ' + (e && e.message ? e.message : e));
          fail.code  = 'E_PDF_FAILED';
          fail.cause = e;
          reject(fail);
          return;
        }
        resolve({
          ok:         true,
          filename:   filename,
          extent:     extent,
          pixelRatio: pixelRatio,
          page:       built.page,
        });
      };
      var doCancel = function () {
        resolve({
          ok:        false,
          cancelled: true,
          reason:    'share-cancelled',
          extent:    extent,
          pixelRatio: pixelRatio,
          page:      built.page,
        });
      };
      if (opts.skipShareGate) {
        doConfirm();
        return;
      }
      _gateShare(filename, doConfirm, doCancel);
    });
  }

  // ── Module export ────────────────────────────────────────────────────────

  var ns = {
    DEFAULT_MARGIN_PX:    DEFAULT_MARGIN_PX,
    DEFAULT_PIXEL_RATIO:  DEFAULT_PIXEL_RATIO,
    DEFAULT_FILENAME:     DEFAULT_FILENAME,
    PDF_UNIT:             PDF_UNIT,
    apply:                apply,
    computeExportExtent:  computeExportExtent,
    rasterize:            rasterize,
    buildPdf:             buildPdf,
    // Internals exposed for tests.
    _deriveFilename:      _deriveFilename,
    _gateShare:           _gateShare,
    _jsPdfCtor:           _jsPdfCtor,
  };

  if (typeof window !== 'undefined') {
    window.OraExportPdf = ns;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = ns;
  }
})(typeof window !== 'undefined' ? window : this);
