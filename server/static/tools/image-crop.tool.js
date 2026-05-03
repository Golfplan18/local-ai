/**
 * image-crop.tool.js — WP-7.4.3 (per-image raster crop)
 *
 * A Tool Primitive (per Reference — Visual Pane Extension Points §B.4):
 * the user selects a raster image on the canvas, activates this tool,
 * draws a rectangle inside the image's bounding rect, and on confirm
 * the image's pixel data is replaced by the cropped region. Layout
 * outside the image is unchanged; only that one image's `image_data`
 * + bounding rect update.
 *
 * Lives on the Image specialty toolbar (which lands in WP-7.1.6); this
 * module just needs to be registerable so that toolbar can pick it up.
 *
 * ── Public surface ──────────────────────────────────────────────────────────
 *
 *   window.OraTools['image-crop']  — full §B.4 primitive contract:
 *     { id, label, defaultIcon, init, activate, deactivate, serializeState,
 *       cropImageObject(state, objectId, region) → { ok, state, ... } }
 *
 *   The headless helper `cropImageObject` is the load-bearing primitive:
 *   it accepts a canvas-state object, an image object id, and a crop
 *   region in image-local pixel coordinates, and returns a new state
 *   with that image's `image_data` + width/height swapped for the
 *   cropped region. The Konva-driven activate/deactivate logic builds
 *   on this helper for the live drawing UX.
 *
 * ── Behavior on activate ────────────────────────────────────────────────────
 *
 *   1. Listens for clicks on Konva.Image nodes anywhere in the stage.
 *   2. When a raster image is clicked, captures it as the crop target.
 *   3. mousedown inside the target image starts a drag-rect; mousemove
 *      grows it; mouseup confirms. The rect is constrained to the
 *      image's bounding rect — clamped on both axes.
 *   4. Confirm: builds a fresh HTMLCanvas, draws the source image,
 *      copies the cropped sub-region into a second canvas, encodes
 *      to base64, and dispatches `ora-image-cropped` with the
 *      { objectId, region, image_data, width, height, x, y } payload.
 *
 * ── Position-preservation rule ──────────────────────────────────────────────
 *
 *   The cropped image's stage-coordinate top-left equals the user's
 *   crop-rectangle top-left (in the same stage coordinates). So if the
 *   user crops the LEFT half, the new image stays where the original
 *   was; if they crop the RIGHT half, the new image's top-left moves
 *   right by half the original width — left half is now empty space,
 *   right-half pixels are at their original screen positions. This is
 *   the §13.4 WP-7.4.3 test contract: "position preserved relative to
 *   other canvas objects."
 *
 * ── Registration ────────────────────────────────────────────────────────────
 *
 *   Auto-registered on load:
 *     window.OraTools = window.OraTools || {};
 *     window.OraTools['image-crop'] = module.exports;
 *
 *   Toolbar JSON entries reference the tool by id `image-crop`
 *   (WP-7.1.6 will surface this on the Image toolbar).
 *
 *   Also exported via CommonJS for the Node test harness.
 */

(function () {
  'use strict';

  // ── Pure helpers (Node-friendly, no Konva / DOM dependency) ────────────────

  function _isObj(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }

  /**
   * Find an image object by id inside a canvas-state objects[] tree.
   * Recurses into group children so nested images are reachable.
   * Returns { object, parent, path } or null.
   */
  function _findImageObject(state, objectId) {
    if (!_isObj(state) || !Array.isArray(state.objects)) return null;
    function walk(arr, parent, path) {
      for (var i = 0; i < arr.length; i++) {
        var O = arr[i];
        if (!_isObj(O)) continue;
        if (O.id === objectId && O.kind === 'image') {
          return { object: O, parent: parent, path: path.concat(i) };
        }
        if (O.kind === 'group' && Array.isArray(O.children)) {
          var hit = walk(O.children, O, path.concat(i, 'children'));
          if (hit) return hit;
        }
      }
      return null;
    }
    return walk(state.objects, null, []);
  }

  /**
   * Validate a crop region against an image object's natural pixel
   * dimensions (width × height on the object). Returns { ok, errors[] }.
   *
   * `region` is in IMAGE-LOCAL PIXEL COORDINATES (0,0 = top-left of
   * the image's bitmap). Caller is responsible for converting from
   * stage coords if needed.
   */
  function _validateRegion(imgObj, region) {
    var errs = [];
    if (!_isObj(region)) {
      errs.push('region must be an object with x/y/width/height');
      return { ok: false, errors: errs };
    }
    if (typeof region.x !== 'number' || region.x < 0) errs.push('region.x must be ≥ 0');
    if (typeof region.y !== 'number' || region.y < 0) errs.push('region.y must be ≥ 0');
    if (typeof region.width !== 'number' || region.width <= 0) errs.push('region.width must be > 0');
    if (typeof region.height !== 'number' || region.height <= 0) errs.push('region.height must be > 0');
    var iw = (typeof imgObj.width === 'number') ? imgObj.width : null;
    var ih = (typeof imgObj.height === 'number') ? imgObj.height : null;
    if (iw == null || ih == null) {
      errs.push('image object missing width/height — cannot bound-check region');
    } else {
      if (region.x + region.width  > iw + 1e-6) errs.push('region exceeds image width on x-axis');
      if (region.y + region.height > ih + 1e-6) errs.push('region exceeds image height on y-axis');
    }
    return { ok: errs.length === 0, errors: errs };
  }

  /**
   * Strip a "data:<mime>;base64," prefix from a string if present, returning
   * the raw base64 payload. Canvas-state image_data forbids the prefix
   * (see canvas-file-format.js §validate /image_data/data check).
   */
  function _stripDataUrlPrefix(s) {
    if (typeof s !== 'string') return s;
    var m = /^data:[^;,]+;base64,(.*)$/.exec(s);
    return m ? m[1] : s;
  }

  /**
   * Crop a base64-encoded raster image down to a region using an
   * offscreen <canvas>. Returns a Promise<string> resolving to raw
   * base64 (no data: URL prefix).
   *
   * Caller-supplied `host` provides the document/canvas factory and
   * a function to load an HTMLImageElement from a data URL. This lets
   * the helper run identically in browser and jsdom.
   *
   *   host = {
   *     createCanvas(width, height) → HTMLCanvasElement,
   *     loadImage(dataUrl) → Promise<HTMLImageElement>,
   *     toDataURL(canvas, mimeType) → string  // "data:<mime>;base64,<payload>"
   *   }
   */
  function _cropBase64InHost(host, base64Data, mimeType, region) {
    return new Promise(function (resolve, reject) {
      try {
        var dataUrl = 'data:' + mimeType + ';base64,' + base64Data;
        host.loadImage(dataUrl).then(function (img) {
          try {
            // Source canvas: full image at native size. We don't strictly
            // need this — drawImage(img, sx, sy, sw, sh, 0, 0, dw, dh)
            // can clip directly — but the two-canvas form is friendlier
            // to environments where the HTMLImage isn't fully decoded.
            var iw = img.naturalWidth  || img.width  || region.width;
            var ih = img.naturalHeight || img.height || region.height;
            var src = host.createCanvas(iw, ih);
            var sctx = src.getContext('2d');
            try { sctx.drawImage(img, 0, 0, iw, ih); } catch (e) { /* ignore */ }

            var dst = host.createCanvas(region.width, region.height);
            var dctx = dst.getContext('2d');
            try {
              dctx.drawImage(
                src,
                region.x, region.y, region.width, region.height,
                0, 0, region.width, region.height
              );
            } catch (e) { /* ignore — fallback to all-zero canvas */ }

            var out = host.toDataURL(dst, mimeType);
            resolve(_stripDataUrlPrefix(out));
          } catch (inner) {
            reject(inner);
          }
        }, reject);
      } catch (outer) {
        reject(outer);
      }
    });
  }

  /**
   * Pure mutation: given a canvas-state object, the id of an embedded
   * image, and a crop region in image-local pixel coordinates, returns
   * a new state with that image's `image_data.data` + width/height +
   * (optionally) x/y replaced for the cropped region.
   *
   *   cropImageObject(state, imageId, region, opts?) → Promise<{
   *     ok: true|false,
   *     state: <new state>,           // identity-equal to input on failure
   *     errors: string[],
   *     newImageData: { mime_type, encoding, data }   // for live Konva swap
   *   }>
   *
   * `opts.host` defaults to a browser-aware host built from `document`
   * if available. In Node tests, callers pass a custom host — see
   * the test file for an example (canvas/jpeg or pure-JS PNG splice).
   *
   * `opts.preservePosition` (default true): the new image's `x`/`y`
   * are shifted by `region.x` / `region.y` (in image-local pixels)
   * scaled to stage units via `image.width / natural_width`. The
   * stage-coordinate top-left of the visible cropped pixels stays
   * fixed — exactly the §13.4 test rule.
   */
  function cropImageObject(state, objectId, region, opts) {
    opts = _isObj(opts) ? opts : {};
    return new Promise(function (resolve) {
      var hit = _findImageObject(state, objectId);
      if (!hit) {
        resolve({ ok: false, state: state, errors: ['no image object with id "' + objectId + '"'] });
        return;
      }
      var imgObj = hit.object;
      var v = _validateRegion(imgObj, region);
      if (!v.ok) {
        resolve({ ok: false, state: state, errors: v.errors });
        return;
      }
      if (!_isObj(imgObj.image_data) || typeof imgObj.image_data.data !== 'string') {
        resolve({ ok: false, state: state, errors: ['image object has no image_data.data'] });
        return;
      }

      var host = opts.host || _defaultHost();
      if (!host) {
        resolve({ ok: false, state: state, errors: ['no offscreen-canvas host available'] });
        return;
      }

      var mimeType = imgObj.image_data.mime_type || 'image/png';
      // canvas.toDataURL('image/jpeg') is fine; for unknown mimes we coerce
      // to PNG so the host doesn't reject. Crop is lossless in PNG; for
      // JPEG the crop will incur a re-encode pass.
      var encMime = /^image\/(png|jpeg|webp)$/i.test(mimeType) ? mimeType : 'image/png';

      _cropBase64InHost(host, imgObj.image_data.data, mimeType, region).then(function (newBase64) {
        // Build the patched object. Width/height reflect the cropped
        // pixel dimensions; x/y shift so the visible content stays
        // fixed in stage coordinates (preservePosition default).
        var preservePosition = opts.preservePosition !== false;
        var newObj = _shallowMerge(imgObj, {
          width:  region.width,
          height: region.height,
          image_data: { mime_type: encMime, encoding: 'base64', data: newBase64 }
        });
        if (preservePosition && typeof imgObj.x === 'number' && typeof imgObj.y === 'number') {
          // Image-local pixels → stage coords scale factor.
          // If image.width was used as the "stage width" of the image
          // (the convention in canvas-file-format.js where width/height
          // are the on-canvas dimensions), the scale is 1:1 against
          // image-local pixels per WP-7.0.2. We honor that convention.
          newObj.x = imgObj.x + region.x;
          newObj.y = imgObj.y + region.y;
        }
        var newState = _replaceObject(state, hit, newObj);
        resolve({
          ok: true,
          state: newState,
          errors: [],
          newImageData: newObj.image_data,
          newRect: { x: newObj.x, y: newObj.y, width: newObj.width, height: newObj.height }
        });
      }, function (err) {
        resolve({ ok: false, state: state, errors: [String(err && err.message || err)] });
      });
    });
  }

  function _shallowMerge(a, b) {
    var out = {};
    var k;
    for (k in a) if (Object.prototype.hasOwnProperty.call(a, k)) out[k] = a[k];
    for (k in b) if (Object.prototype.hasOwnProperty.call(b, k)) out[k] = b[k];
    return out;
  }

  function _replaceObject(state, hit, newObj) {
    // Clone the path top-down so callers see a structurally fresh state.
    var newState = {};
    var k;
    for (k in state) if (Object.prototype.hasOwnProperty.call(state, k)) newState[k] = state[k];
    newState.objects = state.objects.slice();
    var path = hit.path;
    if (path.length === 1) {
      newState.objects[path[0]] = newObj;
      return newState;
    }
    // Path is [outerIdx, 'children', innerIdx, 'children', ...].
    // Walk down cloning each group's children array so references higher
    // up the tree don't mutate.
    var i = 0;
    var cursor = newState.objects;
    while (i + 2 < path.length) {
      var idx = path[i];
      var obj = cursor[idx];
      var clone = _shallowMerge(obj, {});
      clone.children = obj.children.slice();
      cursor[idx] = clone;
      cursor = clone.children;
      i += 2;  // skip 'children' marker
    }
    cursor[path[i]] = newObj;
    return newState;
  }

  function _defaultHost() {
    if (typeof document === 'undefined') return null;
    return {
      createCanvas: function (w, h) {
        var c = document.createElement('canvas');
        c.width = w; c.height = h;
        return c;
      },
      loadImage: function (dataUrl) {
        return new Promise(function (resolve, reject) {
          var img = (typeof Image !== 'undefined') ? new Image() : document.createElement('img');
          img.onload  = function () { resolve(img); };
          img.onerror = function () { reject(new Error('image load failed')); };
          try { img.src = dataUrl; } catch (e) { reject(e); }
        });
      },
      toDataURL: function (canvas, mime) {
        try { return canvas.toDataURL(mime); }
        catch (e) { return canvas.toDataURL('image/png'); }
      }
    };
  }

  // ── §B.4 Tool Primitive surface ────────────────────────────────────────────

  var tool = {
    id: 'image-crop',
    label: 'Crop image',
    defaultIcon: 'crop',   // Lucide name

    // Live-mode state populated by activate(); zeroed by deactivate().
    _panel:           null,
    _ctx:             null,
    _targetNode:      null,   // Konva.Image being cropped
    _targetObjectId:  null,   // canvas-state object id (if known)
    _drag:            null,   // { startX, startY, rectNode }
    _onStageClick:    null,
    _onStageDown:     null,
    _onStageMove:     null,
    _onStageUp:       null,
    _onKey:           null,

    init: function (panel, ctx) {
      this._panel = panel || null;
      this._ctx   = ctx   || null;
    },

    activate: function (ctx) {
      var self = this;
      var panel = this._panel;
      if (!panel || typeof panel.stage === 'undefined') return;

      // Click handler: pick the topmost Konva.Image under the pointer.
      this._onStageClick = function (evt) {
        var node = evt && evt.target;
        if (node && node.getClassName && node.getClassName() === 'Image') {
          self._targetNode = node;
          self._targetObjectId = (typeof node.attrs.canvasObjectId === 'string')
            ? node.attrs.canvasObjectId : null;
          self._dispatch('ora-image-crop-target', { objectId: self._targetObjectId });
        }
      };
      panel.stage.on('click.image-crop', this._onStageClick);

      // Drag-rect on the selection layer — only when a target image is set.
      this._onStageDown = function (evt) {
        if (!self._targetNode) return;
        var stage = panel.stage;
        var pos = stage.getPointerPosition();
        if (!pos) return;
        // Constrain to image bounding rect in stage coords.
        var box = self._targetNode.getClientRect({ skipTransform: false });
        if (pos.x < box.x || pos.x > box.x + box.width)  return;
        if (pos.y < box.y || pos.y > box.y + box.height) return;
        self._drag = { startX: pos.x, startY: pos.y, rectNode: null };
      };
      panel.stage.on('mousedown.image-crop touchstart.image-crop', this._onStageDown);

      this._onStageMove = function (evt) {
        if (!self._drag || !self._targetNode) return;
        self._renderPreview();
      };
      panel.stage.on('mousemove.image-crop touchmove.image-crop', this._onStageMove);

      this._onStageUp = function (evt) {
        if (!self._drag || !self._targetNode) return;
        self._confirmCrop();
      };
      panel.stage.on('mouseup.image-crop touchend.image-crop', this._onStageUp);

      // Esc cancels an in-flight drag and clears the target.
      this._onKey = function (e) {
        if (e && e.key === 'Escape') self._cancel();
      };
      if (typeof window !== 'undefined' && window.addEventListener) {
        window.addEventListener('keydown', this._onKey, true);
      }
    },

    deactivate: function (ctx) {
      var panel = this._panel;
      if (panel && panel.stage) {
        panel.stage.off('.image-crop');
      }
      if (this._onKey && typeof window !== 'undefined' && window.removeEventListener) {
        window.removeEventListener('keydown', this._onKey, true);
      }
      this._cancel();
      this._targetNode = null;
      this._targetObjectId = null;
      this._onStageClick = this._onStageDown = this._onStageMove = this._onStageUp = this._onKey = null;
    },

    serializeState: function (state) {
      // No persistent drawing state — all crops commit immediately.
      return { in_progress: !!this._drag, has_target: !!this._targetNode };
    },

    // Pure helper exposed for headless tests + capability slot integrations.
    cropImageObject: cropImageObject,

    // ── Internals ────────────────────────────────────────────────────────────

    _renderPreview: function () {
      var panel = this._panel;
      var stage = panel && panel.stage;
      if (!stage || !this._drag || !this._targetNode) return;
      var pos = stage.getPointerPosition();
      if (!pos) return;
      var box = this._targetNode.getClientRect({ skipTransform: false });
      // Clamp to image bounds.
      var x1 = Math.max(box.x, Math.min(this._drag.startX, box.x + box.width));
      var y1 = Math.max(box.y, Math.min(this._drag.startY, box.y + box.height));
      var x2 = Math.max(box.x, Math.min(pos.x, box.x + box.width));
      var y2 = Math.max(box.y, Math.min(pos.y, box.y + box.height));
      var px = Math.min(x1, x2), py = Math.min(y1, y2);
      var pw = Math.abs(x2 - x1), ph = Math.abs(y2 - y1);
      if (typeof Konva === 'undefined') return;
      if (!this._drag.rectNode) {
        var layer = panel.selectionLayer || panel.userInputLayer;
        if (!layer) return;
        this._drag.rectNode = new Konva.Rect({
          x: px, y: py, width: pw, height: ph,
          stroke: '#ff8800', strokeWidth: 1.5, dash: [6, 4],
          name: 'vp-image-crop-preview',
          listening: false
        });
        layer.add(this._drag.rectNode);
      } else {
        this._drag.rectNode.setAttrs({ x: px, y: py, width: pw, height: ph });
      }
      try { this._drag.rectNode.getLayer().batchDraw(); } catch (e) { /* ignore */ }
    },

    _confirmCrop: function () {
      var panel = this._panel;
      var node  = this._targetNode;
      var drag  = this._drag;
      if (!panel || !node || !drag || !drag.rectNode) { this._cancel(); return; }
      var rect = drag.rectNode.getAttrs();
      // Image-local pixel coordinates: subtract the image's top-left in
      // stage space. WP-7.0.2 uses 1:1 stage-pixel-per-image-pixel mapping.
      var box = node.getClientRect({ skipTransform: false });
      var region = {
        x: Math.max(0, rect.x - box.x),
        y: Math.max(0, rect.y - box.y),
        width:  Math.max(1, rect.width),
        height: Math.max(1, rect.height)
      };
      // Disposal of preview rect happens in _cancel().
      this._cancel();

      // Dispatch an event the host integration consumes. The event
      // detail carries everything visual-panel.js needs to (a) call
      // cropImageObject() against the canvas-state and (b) swap the
      // Konva.Image's source bitmap once the new base64 is computed.
      this._dispatch('ora-image-crop-confirm', {
        objectId: this._targetObjectId,
        region:   region,
        konvaNode: node,
        // Convenience: the live host can call this directly with the
        // current canvas-state to compute the new state.
        cropImageObject: cropImageObject
      });
    },

    _cancel: function () {
      if (this._drag && this._drag.rectNode) {
        try { this._drag.rectNode.destroy(); } catch (e) { /* ignore */ }
        try { this._drag.rectNode.getLayer && this._drag.rectNode.getLayer().batchDraw(); } catch (e) { /* ignore */ }
      }
      this._drag = null;
    },

    _dispatch: function (name, detail) {
      var panel = this._panel;
      var target = (panel && panel.el) || (typeof window !== 'undefined' ? window : null);
      if (!target || typeof CustomEvent === 'undefined') return;
      try {
        target.dispatchEvent(new CustomEvent(name, { detail: detail, bubbles: true }));
      } catch (e) { /* ignore */ }
    }
  };

  // Expose the helpers as named exports for fine-grained tests + integrations.
  tool.cropImageObject       = cropImageObject;
  tool._findImageObject      = _findImageObject;
  tool._validateRegion       = _validateRegion;
  tool._stripDataUrlPrefix   = _stripDataUrlPrefix;

  // ── Registration ────────────────────────────────────────────────────────────
  //
  // Two surfaces:
  //   • window.OraImageCropTool — matches the per-tool global convention
  //     used by sibling WP-7.5.1 tools (rect-selection, brush, lasso).
  //   • window.OraTools['image-crop'] — registered-tools map convention from
  //     §B.4 of Reference — Visual Pane Extension Points. WP-7.1.6 will use
  //     this map to wire the Image specialty toolbar.

  if (typeof window !== 'undefined') {
    window.OraImageCropTool = tool;
    window.OraTools = window.OraTools || {};
    window.OraTools['image-crop'] = tool;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = tool;
  }
})();
