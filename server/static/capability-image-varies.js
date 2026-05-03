/**
 * capability-image-varies.js — WP-7.3.3f
 *
 * Slot wiring for the `image_varies` capability. Bridges the generic
 * UX layer (capability-invocation-ui.js, WP-7.3.1) with the server
 * route at `/api/capability/image_varies` (added alongside this WP).
 *
 * The WP-7.3.2a foundation registers DALL-E 2 variations; WP-7.3.2c
 * registers `lucataco/sdxl-img2img` as the Replicate fallback. This
 * module is the client side: collect inputs, resolve the source image
 * to bytes, POST to the route, render the result as a 4-image grid,
 * and let the user click a tile to insert it onto the canvas.
 *
 * ── How `image_varies` differs from `image_generates` ──────────────────
 *
 *   - Inputs include `source_image` (canvas-object id), `count`
 *     (default 4), `variation_strength` (float 0-1, default 0.5).
 *     There is no prompt and no aspect_ratio.
 *   - Output is a *list* of images, not one. Per the slot's
 *     `output.type = "images-list"` (config/capabilities.json §3.6),
 *     we render a grid panel where each tile is an inserter button.
 *   - The panel has an "Insert all" affordance so users who want all
 *     four variants on the canvas at once don't have to click four
 *     times.
 *
 * ── Server contract ────────────────────────────────────────────────────
 *
 *   POST /api/capability/image_varies
 *
 *   Request body (JSON):
 *     {
 *       "slot": "image_varies",
 *       "inputs": {
 *         "source_image":         "<canvas-object-id>",
 *         "source_image_data_url": "data:image/png;base64,...", // optional
 *         "count":                4,
 *         "variation_strength":   0.5
 *       },
 *       "provider_override": "openai" | "replicate" | undefined
 *     }
 *
 *   Response 200:
 *     {
 *       "images": [
 *         { "data": "<base64>", "mime_type": "image/png" },
 *         ...
 *       ],
 *       "provider": "openai" | "replicate" | "mock-image-varies",
 *       "metadata": { ... }
 *     }
 *
 *   Response non-2xx:
 *     { "error": { "code": "source_ambiguous" | ..., "message": "..." } }
 *
 * The server's mock fulfilment produces N tinted versions of the source
 * (different hue per tile) so the test criterion ("vary a source image;
 * verify 4 distinct images returned") works without an OpenAI key.
 *
 * ── Public API ─────────────────────────────────────────────────────────
 *
 *   window.OraCapabilityImageVaries
 *
 *     .init({ hostEl, visualPanel, fetchImpl, endpoint, ui })
 *       Mount on `hostEl` (same host as the invocation UI). `visualPanel`
 *       is the active VisualPanel for landing tiles on the canvas.
 *       `fetchImpl` defaults to window.fetch. `endpoint` defaults to
 *       `/api/capability/image_varies`. `ui` is an OraCapabilityInvocationUI
 *       reference (auto-resolved from window if absent).
 *
 *     .destroy()
 *     .handleDispatch(detail)
 *     .buildCanvasObject({ base64, mimeType, anchor, canvasSize, width, height })
 *     .renderGrid({ images, hostEl })
 *           — programmatic grid mount; returns the panel element.
 *     .insertImageAt(index)
 *           — programmatic tile insertion (used by tests).
 *     .insertAllImages()
 *           — programmatic insert-all (used by tests).
 *
 * ── Result delivery ────────────────────────────────────────────────────
 *
 * Like WP-7.3.3a, we prefer `visualPanel.insertImageObject(canvasObject)`
 * when the panel exposes it; fall back to `attachImage(blob)` otherwise.
 * For the 4-up grid, the wiring builds *one* canvas object per tile at
 * insert time (not eagerly), so users can preview the grid without
 * polluting the canvas with rejected variants.
 */
(function (root) {
  'use strict';

  // ── Constants ─────────────────────────────────────────────────────────

  var DEFAULT_ENDPOINT = '/api/capability/image_varies';

  // Canvas-state schema constants (mirror WP-7.3.3a).
  var DEFAULT_CANVAS_W = 10000;
  var DEFAULT_CANVAS_H = 10000;
  var USER_INPUT_LAYER_ID = 'user_input';
  var DEFAULT_MIME = 'image/png';

  // §3.6 default count is 4 per capabilities.json. We clamp at 1..8 so a
  // pathological provider response or a UI bug doesn't paint a 50-tile
  // grid on the user's screen.
  var DEFAULT_COUNT = 4;
  var MIN_COUNT = 1;
  var MAX_COUNT = 8;

  // §3.6 default variation_strength is 0.5; range is 0..1.
  var DEFAULT_STRENGTH = 0.5;

  // Default tile dimensions when the source image's dimensions are
  // unknown. Matches DALL-E 2's 1024×1024 native output.
  var DEFAULT_TILE_W = 1024;
  var DEFAULT_TILE_H = 1024;

  // Layout of the inserted tiles when "Insert all" is used. We arrange
  // them in a 2×2 (for 4) or row layout (for fewer/more), centred on the
  // anchor with this much spacing in canvas units.
  var INSERT_ALL_GAP_PX = 64;

  // Error code translation: HTTP status → slot common_errors code.
  // `image_varies` only declares `source_ambiguous` in capabilities.json,
  // but the route can also surface `model_unavailable` and
  // `quota_exceeded` from the provider; we map status → best-fit code.
  function _statusToCode(status) {
    if (status === 400) return 'source_ambiguous';
    if (status === 422) return 'source_ambiguous';
    if (status === 429) return 'quota_exceeded';
    if (status === 403) return 'source_ambiguous';
    return 'model_unavailable';
  }

  // ── DOM / event helpers ──────────────────────────────────────────────

  function _el(tag, cls, text) {
    if (typeof document === 'undefined') return null;
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function _emit(targetEl, name, detail) {
    if (!targetEl || typeof CustomEvent !== 'function') return;
    var evt = new CustomEvent(name, { detail: detail, bubbles: true });
    targetEl.dispatchEvent(evt);
  }

  function _genId(prefix) {
    var stamp = Date.now().toString(36);
    var rand = Math.random().toString(36).slice(2, 8);
    return (prefix || 'img_var_') + stamp + '_' + rand;
  }

  function _synthError(code, message) {
    var e = new Error(message || code);
    e.code = code;
    return e;
  }

  // ── Base64 / Blob helpers (mirror WP-7.3.3a) ─────────────────────────

  function _base64ToBlob(base64, mimeType) {
    if (typeof atob !== 'function') return null;
    try {
      var bin = atob(base64);
      var len = bin.length;
      var arr = new Uint8Array(len);
      for (var i = 0; i < len; i++) arr[i] = bin.charCodeAt(i);
      if (typeof Blob === 'function') {
        return new Blob([arr], { type: mimeType || DEFAULT_MIME });
      }
    } catch (_e) { /* fall through */ }
    return null;
  }

  function _base64ToDataUrl(base64, mimeType) {
    return 'data:' + (mimeType || DEFAULT_MIME) + ';base64,' + base64;
  }

  function _stripDataUrlPrefix(s) {
    if (typeof s !== 'string') return s;
    if (s.indexOf('data:') === 0) {
      var idx = s.indexOf('base64,');
      if (idx >= 0) return s.slice(idx + 7);
    }
    return s;
  }

  // ── Source-image resolution ──────────────────────────────────────────

  /**
   * Given a canvas-object id, ask the visual panel for the underlying
   * data URL. Returns null when the panel doesn't expose a lookup or
   * the id isn't found. The server can synthesise a stand-in when this
   * resolves to null (mock path), so this is best-effort.
   *
   * Recognised panel APIs (preference order):
   *   getImageDataUrlById(id)        → string
   *   getCanvasObjectById(id)        → { image_data: { data, mime_type } }
   *   getObjectById(id)              → same shape as getCanvasObjectById
   */
  function _resolveSourceImageDataUrl(visualPanel, sourceId) {
    if (!visualPanel || !sourceId) return null;
    if (typeof visualPanel.getImageDataUrlById === 'function') {
      try {
        var url = visualPanel.getImageDataUrlById(sourceId);
        if (typeof url === 'string' && url) return url;
      } catch (_e) { /* fall through */ }
    }
    var lookup = null;
    if (typeof visualPanel.getCanvasObjectById === 'function') {
      lookup = visualPanel.getCanvasObjectById;
    } else if (typeof visualPanel.getObjectById === 'function') {
      lookup = visualPanel.getObjectById;
    }
    if (lookup) {
      try {
        var obj = lookup.call(visualPanel, sourceId);
        if (obj && obj.image_data && typeof obj.image_data.data === 'string') {
          var mime = obj.image_data.mime_type || DEFAULT_MIME;
          return _base64ToDataUrl(obj.image_data.data, mime);
        }
      } catch (_e) { /* fall through */ }
    }
    return null;
  }

  /**
   * Pull a usable anchor from the visual panel (same logic as WP-7.3.3a).
   * Returns null when no anchor is selected.
   */
  function _resolveAnchor(visualPanel) {
    if (!visualPanel) return null;
    if (typeof visualPanel.getSelectionAnchor === 'function') {
      try {
        var a = visualPanel.getSelectionAnchor();
        if (a && typeof a.x === 'number' && typeof a.y === 'number') return a;
      } catch (_e) { /* fall through */ }
    }
    if (typeof visualPanel.getSelectedShapeIds === 'function') {
      try {
        var ids = visualPanel.getSelectedShapeIds() || [];
        if (ids.length && typeof visualPanel._computeSelectionBBox === 'function') {
          var bbox = visualPanel._computeSelectionBBox();
          if (bbox && typeof bbox.x === 'number' && typeof bbox.y === 'number'
              && typeof bbox.width === 'number' && typeof bbox.height === 'number') {
            return { x: bbox.x + bbox.width / 2, y: bbox.y + bbox.height / 2 };
          }
        }
      } catch (_e) { /* fall through */ }
    }
    return null;
  }

  // ── Canvas-object construction ───────────────────────────────────────

  /**
   * Build a canvas-state image object for a single variation tile.
   * Same schema as WP-7.3.3a's buildCanvasObject. Default tile size is
   * 1024×1024 (DALL-E 2 native); callers can override via opts.width /
   * opts.height when the source image's dimensions are known.
   */
  function buildCanvasObject(opts) {
    opts = opts || {};
    var base64 = opts.base64 || '';
    var mimeType = opts.mimeType || DEFAULT_MIME;
    var canvasSize = opts.canvasSize || { width: DEFAULT_CANVAS_W, height: DEFAULT_CANVAS_H };

    var w = (typeof opts.width === 'number' && opts.width > 0) ? opts.width : DEFAULT_TILE_W;
    var h = (typeof opts.height === 'number' && opts.height > 0) ? opts.height : DEFAULT_TILE_H;

    var cx, cy;
    if (opts.anchor && typeof opts.anchor === 'object'
        && typeof opts.anchor.x === 'number' && typeof opts.anchor.y === 'number') {
      cx = opts.anchor.x;
      cy = opts.anchor.y;
    } else {
      cx = canvasSize.width  / 2;
      cy = canvasSize.height / 2;
    }
    var x = Math.round(cx - w / 2);
    var y = Math.round(cy - h / 2);

    return {
      id:    opts.id || _genId(),
      kind:  'image',
      layer: USER_INPUT_LAYER_ID,
      x:     x,
      y:     y,
      width: w,
      height: h,
      image_data: {
        mime_type: mimeType,
        encoding:  'base64',
        data:      base64,
      },
    };
  }

  /**
   * Compute a 2-column grid offset for tile index i in a 0-indexed list,
   * centred on (cx, cy). Used by insertAllImages so the four tiles don't
   * land on top of each other.
   */
  function _gridOffset(index, count, tileW, tileH, cx, cy) {
    var cols = Math.min(2, Math.max(1, Math.ceil(Math.sqrt(count))));
    var rows = Math.ceil(count / cols);
    var col = index % cols;
    var row = Math.floor(index / cols);
    var totalW = cols * tileW + (cols - 1) * INSERT_ALL_GAP_PX;
    var totalH = rows * tileH + (rows - 1) * INSERT_ALL_GAP_PX;
    var startX = cx - totalW / 2;
    var startY = cy - totalH / 2;
    return {
      x: startX + col * (tileW + INSERT_ALL_GAP_PX) + tileW / 2,
      y: startY + row * (tileH + INSERT_ALL_GAP_PX) + tileH / 2,
    };
  }

  // ── Visual panel delivery ────────────────────────────────────────────

  function _deliverToPanel(visualPanel, canvasObject, blob) {
    if (!visualPanel) return Promise.resolve(null);
    if (typeof visualPanel.insertImageObject === 'function') {
      try {
        var ret = visualPanel.insertImageObject(canvasObject);
        return Promise.resolve(ret);
      } catch (e) {
        return Promise.reject(e);
      }
    }
    if (typeof visualPanel.attachImage === 'function' && blob) {
      try {
        var named = blob;
        try {
          if (typeof File === 'function') {
            named = new File([blob], 'image_varies.png',
              { type: blob.type || DEFAULT_MIME });
          } else {
            blob.name = 'image_varies.png';
          }
        } catch (_e) { /* ignore */ }
        return Promise.resolve(visualPanel.attachImage(named));
      } catch (e) {
        return Promise.reject(e);
      }
    }
    return Promise.resolve(null);
  }

  // ── Server call ──────────────────────────────────────────────────────

  function _callServer(endpoint, payload, fetchImpl) {
    var fn = fetchImpl
      || (typeof root !== 'undefined' && root.fetch)
      || (typeof fetch !== 'undefined' ? fetch : null);
    if (typeof fn !== 'function') {
      return Promise.reject(_synthError('model_unavailable',
        'fetch is not available in this environment.'));
    }
    var body = JSON.stringify(payload);
    return fn(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body,
    }).then(function (response) {
      var status = (response && typeof response.status === 'number') ? response.status : 0;
      var jsonPromise = (response && typeof response.json === 'function')
        ? response.json()
        : Promise.resolve(response && response.body ? response.body : null);
      return jsonPromise.then(function (data) {
        if (status >= 200 && status < 300) {
          return data;
        }
        var errBody = (data && data.error) || {};
        var code = errBody.code || _statusToCode(status);
        var message = errBody.message
          || ('Provider returned HTTP ' + status + '.');
        throw _synthError(code, message);
      });
    });
  }

  // ── Result extraction ────────────────────────────────────────────────

  /**
   * Pull the array of {base64, mimeType} entries out of the server
   * response. Accepts a few flexible shapes:
   *
   *   { images: [{ data, mime_type }, ...] }
   *   { images: ['<base64>', ...] }                 // bare strings
   *   { result: [...] }                             // legacy
   *   single-image fallback: { image: {data, mime_type} } → one-tile list
   */
  function _extractImages(response) {
    if (!response || typeof response !== 'object') return [];
    var raw = null;
    if (Array.isArray(response.images)) raw = response.images;
    else if (Array.isArray(response.result)) raw = response.result;
    else if (response.image && typeof response.image === 'object') raw = [response.image];
    if (!raw) return [];

    var out = [];
    for (var i = 0; i < raw.length; i++) {
      var entry = raw[i];
      var base64 = null;
      var mimeType = DEFAULT_MIME;
      if (typeof entry === 'string') {
        base64 = entry;
      } else if (entry && typeof entry === 'object') {
        base64 = entry.data || entry.b64_json || entry.base64 || null;
        mimeType = entry.mime_type || entry.mimeType || DEFAULT_MIME;
      }
      if (typeof base64 === 'string' && base64.length) {
        base64 = _stripDataUrlPrefix(base64);
        out.push({ base64: base64, mimeType: mimeType });
      }
    }
    return out;
  }

  // ── Result panel (4-up grid) ─────────────────────────────────────────

  /**
   * Mount a grid panel under hostEl listing the variation tiles. Each
   * tile has an "Insert" button; the panel has an "Insert all" button
   * at the foot for users who want every variant on the canvas.
   *
   * Returns { el, insertOne(i), insertAll() } so callers (and tests)
   * can drive insertion programmatically.
   */
  function renderGrid(opts) {
    opts = opts || {};
    var images = Array.isArray(opts.images) ? opts.images : [];
    var hostEl = opts.hostEl;
    var onInsertOne = typeof opts.onInsertOne === 'function' ? opts.onInsertOne : null;
    var onInsertAll = typeof opts.onInsertAll === 'function' ? opts.onInsertAll : null;
    var onClose     = typeof opts.onClose === 'function' ? opts.onClose : null;

    var panel = _el('div', 'ora-cap-image-varies-grid');
    if (!panel) return { el: null, insertOne: function () {}, insertAll: function () {} };
    panel.setAttribute('role', 'region');
    panel.setAttribute('aria-label', 'Image variation results');

    var header = _el('div', 'ora-cap-image-varies-grid__header');
    var title = _el('span', 'ora-cap-image-varies-grid__title',
      images.length + ' variation' + (images.length === 1 ? '' : 's'));
    header.appendChild(title);
    if (onClose) {
      var closeBtn = _el('button', 'ora-cap-image-varies-grid__close', '×');
      closeBtn.type = 'button';
      closeBtn.setAttribute('aria-label', 'Close grid');
      closeBtn.addEventListener('click', function (e) {
        e.preventDefault();
        try { onClose(); } catch (_e) { /* swallow */ }
      });
      header.appendChild(closeBtn);
    }
    panel.appendChild(header);

    var tilesWrap = _el('div', 'ora-cap-image-varies-grid__tiles');
    panel.appendChild(tilesWrap);

    var tileEls = [];
    images.forEach(function (img, i) {
      var tile = _el('div', 'ora-cap-image-varies-grid__tile');
      tile.setAttribute('data-tile-index', String(i));
      var imgEl = _el('img', 'ora-cap-image-varies-grid__img');
      imgEl.alt = 'Variation ' + (i + 1);
      imgEl.src = _base64ToDataUrl(img.base64, img.mimeType);
      var insertBtn = _el('button', 'ora-cap-image-varies-grid__insert', 'Insert');
      insertBtn.type = 'button';
      insertBtn.setAttribute('aria-label', 'Insert variation ' + (i + 1) + ' onto canvas');
      insertBtn.addEventListener('click', function (e) {
        e.preventDefault();
        if (onInsertOne) {
          try { onInsertOne(i); } catch (_e) { /* swallow */ }
        }
      });
      tile.appendChild(imgEl);
      tile.appendChild(insertBtn);
      tilesWrap.appendChild(tile);
      tileEls.push(tile);
    });

    var foot = _el('div', 'ora-cap-image-varies-grid__foot');
    var allBtn = _el('button', 'ora-cap-image-varies-grid__insert-all',
      'Insert all ' + images.length);
    allBtn.type = 'button';
    allBtn.disabled = images.length === 0;
    allBtn.addEventListener('click', function (e) {
      e.preventDefault();
      if (onInsertAll) {
        try { onInsertAll(); } catch (_e) { /* swallow */ }
      }
    });
    foot.appendChild(allBtn);
    panel.appendChild(foot);

    if (hostEl && typeof hostEl.appendChild === 'function') {
      hostEl.appendChild(panel);
    }

    return {
      el: panel,
      tiles: tileEls,
      insertOne: function (i) { if (onInsertOne) onInsertOne(i); },
      insertAll: function () { if (onInsertAll) onInsertAll(); },
    };
  }

  // ── Module state ─────────────────────────────────────────────────────

  function _makeController(opts) {
    opts = opts || {};
    var state = {
      hostEl:       opts.hostEl || (typeof document !== 'undefined' ? document : null),
      visualPanel:  opts.visualPanel || null,
      fetchImpl:    opts.fetchImpl || null,
      endpoint:     opts.endpoint || DEFAULT_ENDPOINT,
      ui:           opts.ui || (typeof root !== 'undefined' ? root.OraCapabilityInvocationUI : null),
      _listener:    null,
      _destroyed:   false,
      _lastResult:  null,    // { images, anchor }
      _lastGrid:    null,    // grid handle returned by renderGrid()
    };

    function _clearLastGrid() {
      if (state._lastGrid && state._lastGrid.el && state._lastGrid.el.parentNode) {
        try { state._lastGrid.el.parentNode.removeChild(state._lastGrid.el); }
        catch (_e) { /* ignore */ }
      }
      state._lastGrid = null;
    }

    function _insertTile(i) {
      var last = state._lastResult;
      if (!last || !Array.isArray(last.images) || !last.images[i]) {
        return Promise.resolve(null);
      }
      var img = last.images[i];
      var canvasObject = buildCanvasObject({
        base64:   img.base64,
        mimeType: img.mimeType,
        anchor:   last.anchor,
      });
      var blob = _base64ToBlob(img.base64, img.mimeType);
      return _deliverToPanel(state.visualPanel, canvasObject, blob)
        .then(function () {
          _emit(state.hostEl, 'canvas-state-changed', {
            source: 'image_varies',
            object: canvasObject,
            anchor: last.anchor,
          });
          return canvasObject;
        });
    }

    function _insertAll() {
      var last = state._lastResult;
      if (!last || !Array.isArray(last.images) || last.images.length === 0) {
        return Promise.resolve([]);
      }
      var images = last.images;
      var n = images.length;
      var canvasSize = { width: DEFAULT_CANVAS_W, height: DEFAULT_CANVAS_H };
      var anchor = last.anchor || { x: canvasSize.width / 2, y: canvasSize.height / 2 };

      var promises = images.map(function (img, i) {
        var pos = _gridOffset(i, n, DEFAULT_TILE_W, DEFAULT_TILE_H, anchor.x, anchor.y);
        var canvasObject = buildCanvasObject({
          base64:   img.base64,
          mimeType: img.mimeType,
          anchor:   pos,
          canvasSize: canvasSize,
        });
        var blob = _base64ToBlob(img.base64, img.mimeType);
        return _deliverToPanel(state.visualPanel, canvasObject, blob)
          .then(function () {
            _emit(state.hostEl, 'canvas-state-changed', {
              source: 'image_varies',
              object: canvasObject,
              anchor: pos,
            });
            return canvasObject;
          });
      });
      return Promise.all(promises);
    }

    function handleDispatch(detail) {
      if (state._destroyed) return Promise.resolve(null);
      if (!detail || detail.slot !== 'image_varies') return Promise.resolve(null);
      var inputs = detail.inputs || {};

      // Required input.
      var sourceId = inputs.source_image || null;
      if (!sourceId) {
        var err = _synthError('source_ambiguous',
          'image_varies requires a non-empty source_image.');
        if (state.ui && typeof state.ui.renderError === 'function') {
          try { state.ui.renderError({ code: err.code, message: err.message }); }
          catch (_e) { /* swallow */ }
        }
        _emit(state.hostEl, 'capability-error', {
          slot: 'image_varies', code: err.code, message: err.message,
        });
        return Promise.reject(err);
      }

      // Clamp count + strength to declared bounds.
      var count = parseInt(inputs.count, 10);
      if (!isFinite(count) || count <= 0) count = DEFAULT_COUNT;
      count = Math.min(MAX_COUNT, Math.max(MIN_COUNT, count));

      var strength = parseFloat(inputs.variation_strength);
      if (!isFinite(strength)) strength = DEFAULT_STRENGTH;
      strength = Math.min(1.0, Math.max(0.0, strength));

      // Try to resolve source bytes via the panel; fall back to id-only
      // (server can mock from a stand-in in that case).
      var dataUrl = inputs.source_image_data_url
        || _resolveSourceImageDataUrl(state.visualPanel, sourceId);

      var serverInputs = {
        source_image:       sourceId,
        count:              count,
        variation_strength: strength,
      };
      if (dataUrl) serverInputs.source_image_data_url = dataUrl;

      var payload = {
        slot:   'image_varies',
        inputs: serverInputs,
      };
      if (detail.provider_override || inputs.provider_override) {
        payload.provider_override = detail.provider_override || inputs.provider_override;
      }

      return _callServer(state.endpoint, payload, state.fetchImpl).then(function (response) {
        var images = _extractImages(response);
        if (!images.length) {
          throw _synthError('model_unavailable',
            'Provider returned a response with no image data.');
        }

        var anchor = _resolveAnchor(state.visualPanel);
        state._lastResult = {
          images:   images,
          anchor:   anchor,
          provider: response.provider || null,
          metadata: response.metadata || null,
        };

        // Replace any prior grid (re-running varies on a new source
        // shouldn't accumulate panels).
        _clearLastGrid();
        var gridHost = (state.ui && state.ui.getResultHost && state.ui.getResultHost())
          || state.hostEl;
        state._lastGrid = renderGrid({
          images: images,
          hostEl: gridHost,
          onInsertOne: function (i) { _insertTile(i); },
          onInsertAll: function () { _insertAll(); },
          onClose: function () { _clearLastGrid(); },
        });

        // Surface to the invocation UI so the spinner clears. We pass
        // the grid element so hosts that want to relocate the panel
        // can do so. The output id is the synthetic batch id, not a
        // single canvas object — insertion happens lazily.
        var batchId = _genId('img_var_batch_');
        var resultPayload = {
          output:    batchId,
          images:    images.map(function (im) {
            return { dataUrl: _base64ToDataUrl(im.base64, im.mimeType) };
          }),
          gridEl:    state._lastGrid && state._lastGrid.el || null,
          provider:  response.provider || null,
          metadata:  response.metadata || null,
        };
        if (state.ui && typeof state.ui.renderResult === 'function') {
          try { state.ui.renderResult(resultPayload); } catch (_e) { /* swallow */ }
        }
        _emit(state.hostEl, 'capability-result', {
          slot:    'image_varies',
          output:  batchId,
          images:  resultPayload.images,
          gridEl:  resultPayload.gridEl,
          provider: resultPayload.provider,
          metadata: resultPayload.metadata,
        });
        return resultPayload;
      }).catch(function (err) {
        var code = (err && err.code) || 'model_unavailable';
        var message = (err && err.message) || String(err);
        if (state.ui && typeof state.ui.renderError === 'function') {
          try { state.ui.renderError({ code: code, message: message }); }
          catch (_e) { /* swallow */ }
        }
        _emit(state.hostEl, 'capability-error', {
          slot: 'image_varies', code: code, message: message,
        });
        throw err;
      });
    }

    function _onCapabilityDispatch(evt) {
      if (!evt || !evt.detail) return;
      if (evt.detail.slot !== 'image_varies') return;
      handleDispatch(evt.detail).catch(function () { /* surfaced */ });
    }

    function destroy() {
      if (state._destroyed) return;
      state._destroyed = true;
      _clearLastGrid();
      if (state.hostEl && state._listener) {
        state.hostEl.removeEventListener('capability-dispatch', state._listener);
      }
      state._listener = null;
    }

    function setVisualPanel(panel) { state.visualPanel = panel || null; }
    function setUI(ui)             { state.ui = ui || null; }
    function setEndpoint(ep)       { state.endpoint = ep || DEFAULT_ENDPOINT; }
    function setFetchImpl(fn)      { state.fetchImpl = fn || null; }

    if (state.hostEl && typeof state.hostEl.addEventListener === 'function') {
      state._listener = _onCapabilityDispatch;
      state.hostEl.addEventListener('capability-dispatch', state._listener);
    }

    return {
      handleDispatch:    handleDispatch,
      destroy:           destroy,
      setVisualPanel:    setVisualPanel,
      setUI:             setUI,
      setEndpoint:       setEndpoint,
      setFetchImpl:      setFetchImpl,
      buildCanvasObject: buildCanvasObject,
      renderGrid:        renderGrid,
      insertImageAt:     _insertTile,
      insertAllImages:   _insertAll,
      _state:            state,
    };
  }

  // ── Module-level "active" controller ─────────────────────────────────

  var _activeController = null;

  function init(opts) {
    if (_activeController) {
      try { _activeController.destroy(); } catch (_e) { /* ignore */ }
    }
    _activeController = _makeController(opts || {});
    return _activeController;
  }

  function _delegate(method) {
    return function () {
      if (!_activeController) return null;
      return _activeController[method].apply(_activeController, arguments);
    };
  }

  var api = {
    init:               init,
    handleDispatch:     _delegate('handleDispatch'),
    setVisualPanel:     _delegate('setVisualPanel'),
    setUI:              _delegate('setUI'),
    setEndpoint:        _delegate('setEndpoint'),
    setFetchImpl:       _delegate('setFetchImpl'),
    insertImageAt:      _delegate('insertImageAt'),
    insertAllImages:    _delegate('insertAllImages'),
    destroy: function () {
      if (_activeController) _activeController.destroy();
      _activeController = null;
    },
    buildCanvasObject:  buildCanvasObject,
    renderGrid:         renderGrid,
    // Test hooks
    _extractImages:     _extractImages,
    _statusToCode:      _statusToCode,
    _resolveAnchor:     _resolveAnchor,
    _resolveSourceImageDataUrl: _resolveSourceImageDataUrl,
    _base64ToBlob:      _base64ToBlob,
    _base64ToDataUrl:   _base64ToDataUrl,
    _gridOffset:        _gridOffset,
    DEFAULT_ENDPOINT:   DEFAULT_ENDPOINT,
    DEFAULT_COUNT:      DEFAULT_COUNT,
    MIN_COUNT:          MIN_COUNT,
    MAX_COUNT:          MAX_COUNT,
    DEFAULT_STRENGTH:   DEFAULT_STRENGTH,
    USER_INPUT_LAYER_ID: USER_INPUT_LAYER_ID,
    _getActive: function () { return _activeController; },
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraCapabilityImageVaries = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
