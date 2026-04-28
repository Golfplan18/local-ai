/**
 * tests/cases/test-image-upload.js — WP-4.1 regression suite.
 *
 * Exports { label, run(ctx, record) } per the run.js case-file convention.
 *
 * Coverage (jsdom-friendly — we exercise the public API rather than
 * simulating native file-picker UI, which jsdom cannot surface):
 *
 *   1. Toolbar markup contains upload-image button + hidden <input> with
 *      accept="image/*".
 *   2. Drop hint element is present in the viewport.
 *   3. Thumbnail indicator DOM exists, hidden by default.
 *   4. Public API surfaces: attachImage, getPendingImage, clearPendingImage.
 *   5. attachImage(File) populates _pendingImage with blob/name/type/dataUrl.
 *   6. attachImage mounts a Konva.Image on backgroundLayer (name:
 *      'vp-background-image').
 *   7. attachImage rejects non-image MIME with the correct error message.
 *   8. attachImage rejects oversize (> 10 MB) with the correct error message.
 *   9. attachImage does not clear the error bar on failure; succeeds with
 *      recoverable messaging.
 *  10. Second attach replaces the first without modal confirm.
 *  11. clearPendingImage() empties _pendingImage and removes Konva.Image.
 *  12. getPendingImage() returns the same object that _pendingImage holds.
 *  13. Stage scale/pan transform applies to the Konva.Image correctly.
 *  14. Drag-over handler wires up: dragover with Files type triggers the
 *      drop-zone highlight class on the panel root; dragleave removes it.
 *  15. drop event with an image File invokes attachImage.
 *  16. drop event with non-image file surfaces the MIME error.
 *  17. clearUserInput() also clears the pending image.
 *  18. OraPanels.visual.{attachImage,getPendingImage,clearPendingImage}
 *      route to the active instance.
 *  19. Indicator toggle: click the indicator reveals the remove button
 *      (visual-panel__image-indicator--open class).
 *  20. Thumbnail shows the data URL in its <img src>.
 */

'use strict';

// ── Helpers ─────────────────────────────────────────────────────────────────
function mkDiv(win) {
  var d = win.document.createElement('div');
  d.style.cssText = 'width:600px;height:400px;';
  win.document.body.appendChild(d);
  return d;
}

/**
 * Build a tiny real PNG data URL (1x1 transparent pixel) for jsdom's
 * FileReader to consume. We turn this into a Blob/File so `.size` and
 * `.type` round-trip correctly.
 */
function makePngFile(win, name, sizeBytes) {
  // 1x1 transparent PNG
  var base64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';
  // Convert to bytes.
  var binStr;
  if (typeof Buffer !== 'undefined') {
    binStr = Buffer.from(base64, 'base64').toString('binary');
  } else {
    binStr = win.atob(base64);
  }
  var bytes = new Uint8Array(binStr.length);
  for (var i = 0; i < binStr.length; i++) bytes[i] = binStr.charCodeAt(i);
  // Pad to desired size if requested (for oversize tests).
  if (sizeBytes && sizeBytes > bytes.length) {
    var padded = new Uint8Array(sizeBytes);
    padded.set(bytes, 0);
    bytes = padded;
  }
  // Build a File. jsdom's File constructor accepts Uint8Array in a parts list.
  return new win.File([bytes], name || 'test.png', { type: 'image/png' });
}

function makeTextFile(win, name) {
  return new win.File(['hello'], name || 'notes.txt', { type: 'text/plain' });
}

/**
 * Await a microtask tick so Promise chains settle in jsdom. Our attachImage
 * returns a Promise that resolves after FileReader + the next setTimeout(0)
 * fires — a small timed wait covers both.
 */
function tick(ms) {
  return new Promise(function (resolve) { setTimeout(resolve, ms || 5); });
}

/**
 * Fire a DragEvent with a manual dataTransfer stub. jsdom's DataTransfer is
 * read-only for `files`, so we provide a custom object with the minimal
 * surface our handlers use: `types`, `files`, `dropEffect`.
 */
function fireDragEvent(win, el, type, files) {
  var dt = {
    types: ['Files'],
    files: files || [],
    dropEffect: 'none',
  };
  var evt;
  try {
    evt = new win.Event(type, { bubbles: true, cancelable: true });
  } catch (e) {
    evt = win.document.createEvent('Event');
    evt.initEvent(type, true, true);
  }
  // Override dataTransfer via defineProperty (jsdom's native DragEvent
  // lacks a settable dataTransfer too).
  Object.defineProperty(evt, 'dataTransfer', { value: dt, configurable: true });
  el.dispatchEvent(evt);
  return evt;
}

module.exports = {
  label: 'Image upload UI (WP-4.1) — drag-drop + file picker + _pendingImage',
  run: async function run(ctx, record) {
    const { win } = ctx;

    if (typeof win.Konva === 'undefined' || typeof win.VisualPanel === 'undefined') {
      record('image-upload: harness bootstrap', false,
        'Konva=' + typeof win.Konva + ' VisualPanel=' + typeof win.VisualPanel);
      return;
    }

    // ── 1. Toolbar markup contains upload button + file input ─────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'iu-1' });
      panel.init();
      const uploadBtn = div.querySelector('.vp-tool-btn[data-tool="upload-image"]');
      const fileInput = div.querySelector('input[type="file"][id="vp-file-input-iu-1"]');
      record('image-upload: toolbar has upload-image button',
        !!uploadBtn, 'upload-image btn=' + !!uploadBtn);
      record('image-upload: hidden file input exists with accept="image/*"',
        !!fileInput && fileInput.getAttribute('accept') === 'image/*',
        'accept=' + (fileInput && fileInput.getAttribute('accept')));
      record('image-upload: upload-image button has aria-label',
        uploadBtn && (uploadBtn.getAttribute('aria-label') || '').length > 0,
        'aria-label=' + (uploadBtn && uploadBtn.getAttribute('aria-label')));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('image-upload: toolbar markup', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 2. Drop hint element is present ───────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'iu-2' });
      panel.init();
      const hint = div.querySelector('.visual-panel__drop-hint');
      record('image-upload: drop hint element is present',
        !!hint, 'hint=' + !!hint);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('image-upload: drop hint', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 3. Thumbnail indicator DOM present + hidden by default ────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'iu-3' });
      panel.init();
      const ind = div.querySelector('.visual-panel__image-indicator');
      record('image-upload: image indicator exists',
        !!ind, 'indicator=' + !!ind);
      record('image-upload: image indicator hidden by default',
        ind && ind.hidden === true, 'hidden=' + (ind && ind.hidden));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('image-upload: indicator DOM', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 4. Public API surfaces exist ──────────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'iu-4' });
      panel.init();
      record('image-upload: attachImage is a function',
        typeof panel.attachImage === 'function',
        'type=' + typeof panel.attachImage);
      record('image-upload: getPendingImage is a function',
        typeof panel.getPendingImage === 'function',
        'type=' + typeof panel.getPendingImage);
      record('image-upload: clearPendingImage is a function',
        typeof panel.clearPendingImage === 'function',
        'type=' + typeof panel.clearPendingImage);
      record('image-upload: getPendingImage returns null by default',
        panel.getPendingImage() === null,
        'initial=' + JSON.stringify(panel.getPendingImage()));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('image-upload: public API', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 5–6. attachImage populates _pendingImage + Konva.Image ────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'iu-5' });
      panel.init();
      const file = makePngFile(win, 'sketch.png');
      const result = await panel.attachImage(file);
      record('image-upload: attachImage resolves to the pending-image object',
        result && result.blob === file && result.name === 'sketch.png',
        'result=' + JSON.stringify(result && { name: result.name, type: result.type }));
      record('image-upload: _pendingImage populated',
        panel._pendingImage && panel._pendingImage.blob === file,
        '_pendingImage=' + JSON.stringify(panel._pendingImage && { name: panel._pendingImage.name }));
      record('image-upload: _pendingImage.dataUrl is a data URL string',
        panel._pendingImage && typeof panel._pendingImage.dataUrl === 'string'
          && panel._pendingImage.dataUrl.indexOf('data:image/') === 0,
        'dataUrl prefix=' + (panel._pendingImage && panel._pendingImage.dataUrl || '').slice(0, 22));
      record('image-upload: getPendingImage returns same object',
        panel.getPendingImage() === panel._pendingImage,
        'match=' + (panel.getPendingImage() === panel._pendingImage));
      const imgs = panel.backgroundLayer.find('.vp-background-image');
      record('image-upload: Konva.Image named "vp-background-image" on backgroundLayer',
        imgs.length === 1,
        'count=' + imgs.length);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('image-upload: attachImage basic', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 7. Non-image MIME rejected with correct message ───────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'iu-7' });
      panel.init();
      const tf = makeTextFile(win, 'notes.txt');
      const result = await panel.attachImage(tf);
      const errBar = div.querySelector('.visual-panel__errorbar');
      record('image-upload: non-image MIME rejected (resolve returns null)',
        result === null,
        'result=' + JSON.stringify(result));
      record('image-upload: _pendingImage remains null after reject',
        panel._pendingImage === null,
        '_pendingImage=' + JSON.stringify(panel._pendingImage));
      record('image-upload: error bar shows "Only image files" message',
        errBar && !errBar.hidden
          && /Only image files/.test(errBar.textContent || ''),
        'text=' + (errBar && errBar.textContent));
      record('image-upload: error bar has image variant class',
        errBar && errBar.classList.contains('visual-panel__errorbar--image'),
        'has class=' + (errBar && errBar.classList.contains('visual-panel__errorbar--image')));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('image-upload: non-image reject', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 8. Oversize file rejected ─────────────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'iu-8' });
      panel.init();
      // 11 MB — over the 10 MB cap.
      const big = makePngFile(win, 'big.png', 11 * 1024 * 1024);
      const result = await panel.attachImage(big);
      const errBar = div.querySelector('.visual-panel__errorbar');
      record('image-upload: oversize rejected',
        result === null && panel._pendingImage === null,
        'result=' + JSON.stringify(result));
      record('image-upload: oversize message references 10 MB',
        errBar && !errBar.hidden
          && /10 MB/i.test(errBar.textContent || ''),
        'text=' + (errBar && errBar.textContent));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('image-upload: oversize reject', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 9. Second attach replaces first ───────────────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'iu-9' });
      panel.init();
      const f1 = makePngFile(win, 'first.png');
      const f2 = makePngFile(win, 'second.png');
      await panel.attachImage(f1);
      const firstNode = panel._backgroundImageNode;
      await panel.attachImage(f2);
      const secondNode = panel._backgroundImageNode;
      record('image-upload: second attach replaces Konva.Image node',
        firstNode !== secondNode && !!secondNode,
        'same=' + (firstNode === secondNode));
      record('image-upload: only one Konva.Image on backgroundLayer after replace',
        panel.backgroundLayer.find('.vp-background-image').length === 1,
        'count=' + panel.backgroundLayer.find('.vp-background-image').length);
      record('image-upload: _pendingImage reflects the second file',
        panel._pendingImage && panel._pendingImage.name === 'second.png',
        'name=' + (panel._pendingImage && panel._pendingImage.name));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('image-upload: replace-on-second-attach', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 10. clearPendingImage empties state + removes Konva.Image ─────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'iu-10' });
      panel.init();
      await panel.attachImage(makePngFile(win, 'gone.png'));
      record('image-upload: pending image present before clear',
        panel._pendingImage !== null, 'pre=' + !!panel._pendingImage);
      panel.clearPendingImage();
      record('image-upload: clearPendingImage sets _pendingImage to null',
        panel._pendingImage === null,
        '_pendingImage=' + JSON.stringify(panel._pendingImage));
      record('image-upload: clearPendingImage removes Konva.Image node',
        panel.backgroundLayer.find('.vp-background-image').length === 0,
        'count=' + panel.backgroundLayer.find('.vp-background-image').length);
      record('image-upload: getPendingImage returns null after clear',
        panel.getPendingImage() === null,
        'get=' + JSON.stringify(panel.getPendingImage()));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('image-upload: clearPendingImage', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 11. Stage transform applies to Konva.Image parent ─────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'iu-11' });
      panel.init();
      await panel.attachImage(makePngFile(win, 'transform.png'));
      // Programmatically apply a zoom+pan transform.
      panel._transform.scale = 2;
      panel._transform.x = 50;
      panel._transform.y = 30;
      panel._applyTransform();
      const stage = panel.stage;
      // The Konva stage carries the transform so all its layers (including
      // backgroundLayer + its child Konva.Image) inherit it.
      record('image-upload: stage x reflects pan',
        stage.x() === 50, 'stage.x=' + stage.x());
      record('image-upload: stage y reflects pan',
        stage.y() === 30, 'stage.y=' + stage.y());
      record('image-upload: stage scaleX reflects zoom',
        stage.scaleX() === 2, 'scaleX=' + stage.scaleX());
      // Konva.Image lives under backgroundLayer → stage, so an absolute
      // transform walk picks up the stage's scale.
      const imgNode = panel._backgroundImageNode;
      const abs = imgNode && imgNode.getAbsoluteTransform && imgNode.getAbsoluteTransform();
      const decoded = abs && abs.decompose && abs.decompose();
      record('image-upload: Konva.Image inherits stage scale via parent transform',
        decoded && Math.abs(decoded.scaleX - 2) < 0.001,
        'absScaleX=' + (decoded && decoded.scaleX));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('image-upload: transform on Konva.Image', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 12. dragover highlight + dragleave clears ─────────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'iu-12' });
      panel.init();
      const file = makePngFile(win, 'hover.png');
      fireDragEvent(win, div, 'dragover', [file]);
      record('image-upload: dragover with Files adds dropzone-active class',
        div.classList.contains('visual-panel--dropzone-active'),
        'classes=' + div.className);
      // dragleave with relatedTarget outside the panel clears highlight.
      var evt = win.document.createEvent('Event');
      evt.initEvent('dragleave', true, true);
      Object.defineProperty(evt, 'relatedTarget', { value: win.document.body, configurable: true });
      div.dispatchEvent(evt);
      record('image-upload: dragleave removes dropzone-active class',
        !div.classList.contains('visual-panel--dropzone-active'),
        'classes=' + div.className);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('image-upload: dragover/dragleave', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 13. drop with image File invokes attachImage path ─────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'iu-13' });
      panel.init();
      const file = makePngFile(win, 'dropped.png');
      fireDragEvent(win, div, 'drop', [file]);
      // attachImage is async via FileReader; wait a tick.
      await tick(20);
      record('image-upload: drop with image File populates _pendingImage',
        panel._pendingImage && panel._pendingImage.name === 'dropped.png',
        '_pendingImage name=' + (panel._pendingImage && panel._pendingImage.name));
      record('image-upload: drop clears dropzone-active class',
        !div.classList.contains('visual-panel--dropzone-active'),
        'classes=' + div.className);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('image-upload: drop image', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 14. drop with non-image surfaces MIME error ───────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'iu-14' });
      panel.init();
      const tf = makeTextFile(win, 'notes.txt');
      fireDragEvent(win, div, 'drop', [tf]);
      await tick(20);
      const errBar = div.querySelector('.visual-panel__errorbar');
      record('image-upload: drop with non-image leaves _pendingImage null',
        panel._pendingImage === null,
        '_pendingImage=' + JSON.stringify(panel._pendingImage));
      record('image-upload: drop with non-image surfaces "Only image files" error',
        errBar && !errBar.hidden && /Only image files/.test(errBar.textContent || ''),
        'text=' + (errBar && errBar.textContent));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('image-upload: drop non-image', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 15. clearUserInput also clears pending image ──────────────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'iu-15' });
      panel.init();
      await panel.attachImage(makePngFile(win, 'staged.png'));
      // Also create a shape so clearUserInput has both affordances to clear.
      panel._createShape('rect', { x: 0, y: 0, width: 30, height: 30 });
      record('image-upload: pre-clear, pending image present',
        panel._pendingImage !== null, 'pre=' + !!panel._pendingImage);
      panel.clearUserInput();
      record('image-upload: clearUserInput nulls _pendingImage',
        panel._pendingImage === null,
        '_pendingImage=' + JSON.stringify(panel._pendingImage));
      record('image-upload: clearUserInput removes background image from backgroundLayer',
        panel.backgroundLayer.find('.vp-background-image').length === 0,
        'count=' + panel.backgroundLayer.find('.vp-background-image').length);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('image-upload: clearUserInput hook', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 16. OraPanels.visual surface routes to active instance ────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'iu-16' });
      panel.init();
      record('image-upload: OraPanels.visual.attachImage is a function',
        typeof win.OraPanels.visual.attachImage === 'function',
        'type=' + typeof win.OraPanels.visual.attachImage);
      const f = makePngFile(win, 'routed.png');
      await win.OraPanels.visual.attachImage(f);
      record('image-upload: OraPanels.visual.getPendingImage returns active panel value',
        win.OraPanels.visual.getPendingImage() === panel.getPendingImage(),
        'same=' + (win.OraPanels.visual.getPendingImage() === panel.getPendingImage()));
      win.OraPanels.visual.clearPendingImage();
      record('image-upload: OraPanels.visual.clearPendingImage clears active panel',
        panel._pendingImage === null,
        '_pendingImage=' + JSON.stringify(panel._pendingImage));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('image-upload: OraPanels routing', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 17. Indicator click toggles remove button visibility ──────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'iu-17' });
      panel.init();
      await panel.attachImage(makePngFile(win, 'thumb.png'));
      const ind = div.querySelector('.visual-panel__image-indicator');
      record('image-upload: indicator visible after attach',
        ind && ind.hidden === false, 'hidden=' + (ind && ind.hidden));
      record('image-upload: indicator starts closed (no --open class)',
        ind && !ind.classList.contains('visual-panel__image-indicator--open'),
        'classes=' + (ind && ind.className));
      // Click the indicator (not the remove button) — should toggle --open.
      const thumbWrap = ind.querySelector('.vp-image-thumb-wrap');
      var clickEvt = win.document.createEvent('MouseEvent');
      clickEvt.initMouseEvent('click', true, true, win, 0, 0, 0, 0, 0,
        false, false, false, false, 0, null);
      thumbWrap.dispatchEvent(clickEvt);
      record('image-upload: click toggles --open class on',
        ind.classList.contains('visual-panel__image-indicator--open'),
        'classes=' + ind.className);
      // Thumbnail <img> carries the data URL.
      const thumbImg = ind.querySelector('img.vp-image-thumb');
      record('image-upload: thumbnail <img> has data URL as src',
        thumbImg && typeof thumbImg.src === 'string' && thumbImg.src.indexOf('data:image/') === 0,
        'src prefix=' + (thumbImg && thumbImg.src || '').slice(0, 22));
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('image-upload: indicator toggle', false, 'threw: ' + (err.stack || err.message || err));
    }

    // ── 18. Remove button on indicator clears pending image ───────────────
    try {
      const div = mkDiv(win);
      const panel = new win.VisualPanel(div, { id: 'iu-18' });
      panel.init();
      await panel.attachImage(makePngFile(win, 'rm.png'));
      const ind = div.querySelector('.visual-panel__image-indicator');
      const removeBtn = ind.querySelector('.vp-image-remove');
      var ev = win.document.createEvent('MouseEvent');
      ev.initMouseEvent('click', true, true, win, 0, 0, 0, 0, 0,
        false, false, false, false, 0, null);
      removeBtn.dispatchEvent(ev);
      record('image-upload: remove button clears _pendingImage',
        panel._pendingImage === null,
        '_pendingImage=' + JSON.stringify(panel._pendingImage));
      record('image-upload: remove button hides indicator',
        ind.hidden === true, 'hidden=' + ind.hidden);
      panel.destroy();
      win.document.body.removeChild(div);
    } catch (err) {
      record('image-upload: remove button', false, 'threw: ' + (err.stack || err.message || err));
    }
  },
};
