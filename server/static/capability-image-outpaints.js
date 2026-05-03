/**
 * capability-image-outpaints.js — WP-7.3.3c — `image_outpaints` slot wiring
 *
 * Bridges the WP-7.3.1 generic invocation UI with the server-side
 * `dispatch_image_outpaints` handler (Stability provider, WP-7.3.2b).
 *
 * The slot's contract per `~/ora/config/capabilities.json` §image_outpaints:
 *
 *   required_inputs: image (image-ref), directions (direction-list), prompt (text)
 *   optional_inputs: aspect_ratio (enum)
 *   output:          image-bytes — canvas image grows
 *   common_errors:   image_too_large, direction_invalid
 *
 * The capability-invocation-ui.js already renders direction-list as four
 * checkboxes (top/bottom/left/right) and yields an array of selected
 * directions via getValue(). We just consume that array and POST it.
 *
 * Result handling differs from image_edits/image_generates: outpaint
 * extends the canvas image bounds. The server returns bytes for the
 * full extended image; we replace the source Konva.Image's bitmap and
 * resize its bbox to fit the new natural dimensions, scaled around the
 * source's existing top-left so the user's eye stays anchored.
 *
 * ── Public API ──────────────────────────────────────────────────────
 *
 *   window.OraImageOutpaints.attach({ hostEl, panel, endpointUrl, fetch })
 *   window.OraImageOutpaints.detach()
 *   window.OraImageOutpaints.handleDispatch(detail)   — for tests
 *   window.OraImageOutpaints.readSourceImage(panel)   — for tests
 */

(function (root) {
  'use strict';

  var ENDPOINT_DEFAULT = '/api/capability/image_outpaints';
  var VALID_DIRECTIONS = { top: 1, bottom: 1, left: 1, right: 1 };

  // ── DOM helpers ────────────────────────────────────────────────────

  function _emit(targetEl, name, detail) {
    if (!targetEl || typeof CustomEvent !== 'function') return;
    var evt = new CustomEvent(name, { detail: detail, bubbles: true });
    targetEl.dispatchEvent(evt);
  }

  function _doc() {
    return (typeof document !== 'undefined') ? document : null;
  }

  // ── Source-image extraction (mirrors image-edits.js readSourceImageFromPanel) ──

  function readSourceImage(panel) {
    if (!panel) return null;
    var node = panel._backgroundImageNode;
    if (!node) return null;

    var attrs = (typeof node.getAttrs === 'function') ? node.getAttrs() : (node.attrs || {});
    var naturalW = attrs.naturalWidth  | 0;
    var naturalH = attrs.naturalHeight | 0;

    var dataUrl = null;
    if (panel._pendingImage && panel._pendingImage.dataUrl) {
      dataUrl = panel._pendingImage.dataUrl;
    } else if (typeof node.image === 'function') {
      var imgEl = node.image();
      if (imgEl && imgEl.src) dataUrl = imgEl.src;
    }
    if (!dataUrl && typeof node.toDataURL === 'function') {
      try { dataUrl = node.toDataURL({ pixelRatio: 1 }); } catch (e) { /* tainted */ }
    }
    if (!dataUrl) return null;

    var stageBbox = null;
    if (typeof node.getClientRect === 'function' && panel.stage) {
      try { stageBbox = node.getClientRect({ relativeTo: panel.stage }); } catch (e) {}
    }

    var imageId = attrs.image_id
                || (typeof node.id === 'function' ? node.id() : null)
                || (typeof node.name === 'function' ? node.name() : null)
                || 'background-image';

    return {
      dataUrl: dataUrl,
      naturalWidth: naturalW || (stageBbox ? Math.round(stageBbox.width)  : 0),
      naturalHeight: naturalH || (stageBbox ? Math.round(stageBbox.height) : 0),
      stageBbox: stageBbox,
      imageId: imageId,
      konvaNode: node
    };
  }

  // ── Direction normalization ────────────────────────────────────────

  /**
   * Accept either an array of strings ({"top","right"}) or a map
   * ({top:true,right:true}); return a deduped array filtered to the
   * four valid directions. Returns null for an empty selection so the
   * caller can surface `direction_invalid`.
   */
  function _normalizeDirections(raw) {
    var out = [];
    if (Array.isArray(raw)) {
      raw.forEach(function (d) {
        if (typeof d === 'string' && VALID_DIRECTIONS[d] && out.indexOf(d) < 0) {
          out.push(d);
        }
      });
    } else if (raw && typeof raw === 'object') {
      Object.keys(raw).forEach(function (d) {
        if (raw[d] && VALID_DIRECTIONS[d] && out.indexOf(d) < 0) {
          out.push(d);
        }
      });
    }
    return out.length ? out : null;
  }

  // ── Result insertion ────────────────────────────────────────────────

  /**
   * Mount the extended image onto the canvas, replacing the source's
   * bitmap. The image grows: stage bbox is rescaled so the new natural
   * dimensions fit, anchored at the source's existing top-left so the
   * user's eye stays where it was.
   *
   * Note: more refined anchoring (e.g. shifting the bbox left when
   * outpainting `left`) is a Phase 8 polish task; v1 keeps the source's
   * top-left fixed and grows the bottom-right corner. The image content
   * is correctly extended either way — only the on-stage offset differs.
   */
  function insertResult(panel, sourceMeta, base64Png) {
    if (!panel || !sourceMeta || !base64Png) return false;
    var doc = _doc();
    if (!doc) return false;

    var dataUrl = (base64Png.indexOf('data:image/') === 0)
      ? base64Png
      : 'data:image/png;base64,' + base64Png;

    var newImg = doc.createElement('img');
    newImg.onload = function () {
      var node = sourceMeta.konvaNode;
      if (!node) return;
      try {
        var newW = newImg.naturalWidth  || sourceMeta.naturalWidth;
        var newH = newImg.naturalHeight || sourceMeta.naturalHeight;

        // Scale the stage bbox to track the new natural dimensions. We
        // preserve the source's stage scale (pixels-per-natural) so a
        // 50%-zoomed source doubles in stage pixels when its naturals
        // double.
        var srcBbox = sourceMeta.stageBbox || null;
        var srcNW = sourceMeta.naturalWidth  || newW;
        var srcNH = sourceMeta.naturalHeight || newH;
        if (srcBbox && srcNW > 0 && srcNH > 0) {
          var scaleX = srcBbox.width  / srcNW;
          var scaleY = srcBbox.height / srcNH;
          if (typeof node.width  === 'function') node.width(newW * scaleX);
          if (typeof node.height === 'function') node.height(newH * scaleY);
        } else {
          if (typeof node.width  === 'function') node.width(newW);
          if (typeof node.height === 'function') node.height(newH);
        }

        if (typeof node.image === 'function') node.image(newImg);
        if (typeof node.setAttrs === 'function') {
          node.setAttrs({ naturalWidth: newW, naturalHeight: newH });
        }
        var layer = (typeof node.getLayer === 'function') ? node.getLayer() : panel.backgroundLayer;
        if (layer && typeof layer.draw === 'function') layer.draw();
      } catch (e) { /* swallow */ }

      _emit(panel.el || _doc(),
            'canvas-state-changed',
            { source: 'image_outpaints' });
    };
    newImg.onerror = function () {
      _emit(panel.el, 'capability-error', {
        slot: 'image_outpaints',
        code: 'handler_failed',
        message: 'Result image failed to decode in browser.'
      });
    };
    try { newImg.src = dataUrl; } catch (e) { /* swallow */ }
    return true;
  }

  // ── Wiring ──────────────────────────────────────────────────────────

  var _state = {
    hostEl: null,
    panel: null,
    endpointUrl: ENDPOINT_DEFAULT,
    fetchFn: null,
    listeners: []
  };

  function _addListener(target, evt, fn) {
    if (!target || !target.addEventListener) return;
    target.addEventListener(evt, fn);
    _state.listeners.push({ target: target, evt: evt, fn: fn });
  }

  function _removeAllListeners() {
    _state.listeners.forEach(function (l) {
      try { l.target.removeEventListener(l.evt, l.fn); } catch (e) {}
    });
    _state.listeners = [];
  }

  /**
   * Handle a `capability-dispatch` event whose slot is `image_outpaints`.
   * Validates inputs, POSTs to the server, and lands the result.
   */
  function handleDispatch(detail) {
    if (!detail || detail.slot !== 'image_outpaints') return Promise.resolve(null);

    var inputs = detail.inputs || {};
    var prompt = (inputs.prompt || '').toString().trim();
    var directions = _normalizeDirections(inputs.directions);
    var aspectRatio = inputs.aspect_ratio || null;

    var sourceMeta = readSourceImage(_state.panel);

    if (!sourceMeta) {
      _emit(_state.hostEl, 'capability-error', {
        slot: 'image_outpaints',
        code: 'handler_failed',
        message: 'No image is currently mounted on the canvas.'
      });
      return Promise.resolve(null);
    }
    if (!prompt) {
      _emit(_state.hostEl, 'capability-error', {
        slot: 'image_outpaints',
        code: 'handler_failed',
        message: 'A non-empty prompt is required.'
      });
      return Promise.resolve(null);
    }
    if (!directions) {
      _emit(_state.hostEl, 'capability-error', {
        slot: 'image_outpaints',
        code: 'direction_invalid',
        message: 'Select at least one direction (top / bottom / left / right).'
      });
      return Promise.resolve(null);
    }

    var body = {
      slot: 'image_outpaints',
      prompt: prompt,
      directions: directions,
      image_data_url: sourceMeta.dataUrl,
      parent_image_id: sourceMeta.imageId,
      aspect_ratio: aspectRatio,
      provider_override: inputs.provider_override || null
    };

    var fetchFn = _state.fetchFn || (typeof fetch === 'function' ? fetch : null);
    if (!fetchFn) {
      _emit(_state.hostEl, 'capability-error', {
        slot: 'image_outpaints',
        code: 'handler_failed',
        message: 'fetch unavailable in this environment.'
      });
      return Promise.resolve(null);
    }

    return fetchFn(_state.endpointUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (resp) {
      var status = (resp && typeof resp.status === 'number') ? resp.status : 0;
      var jsonP = (resp && typeof resp.json === 'function')
        ? resp.json()
        : Promise.resolve(resp && resp.body ? resp.body : null);
      return jsonP.then(function (payload) {
        if (status < 200 || status >= 300 || !payload || !payload.image_b64) {
          var err = (payload && payload.error) || {};
          _emit(_state.hostEl, 'capability-error', {
            slot: 'image_outpaints',
            code: err.code || 'handler_failed',
            message: err.message || ('Server returned HTTP ' + status + '.')
          });
          return null;
        }
        var ok = insertResult(_state.panel, sourceMeta, payload.image_b64);
        if (ok) {
          _emit(_state.hostEl, 'capability-result', {
            slot: 'image_outpaints',
            output: payload.image_b64,
            imageDataUrl: 'data:image/png;base64,' + payload.image_b64,
            directions: directions
          });
        }
        return payload;
      });
    }).catch(function (err) {
      _emit(_state.hostEl, 'capability-error', {
        slot: 'image_outpaints',
        code: 'handler_failed',
        message: 'Network error: ' + (err && err.message ? err.message : String(err))
      });
      return null;
    });
  }

  function _onCapabilityDispatch(e) {
    if (!e || !e.detail) return;
    if (e.detail.slot !== 'image_outpaints') return;
    if (typeof e.preventDefault === 'function') e.preventDefault();
    handleDispatch(e.detail).catch(function () { /* surfaced via event */ });
  }

  function attach(opts) {
    opts = opts || {};
    detach();   // idempotent re-attach

    _state.hostEl      = opts.hostEl || null;
    _state.panel       = opts.panel || null;
    _state.endpointUrl = opts.endpointUrl || ENDPOINT_DEFAULT;
    _state.fetchFn     = opts.fetch || null;

    if (_state.hostEl) {
      _addListener(_state.hostEl, 'capability-dispatch', _onCapabilityDispatch);
    }
    return { detach: detach };
  }

  function detach() {
    _removeAllListeners();
    _state.hostEl = null;
    _state.panel = null;
  }

  // ── Public API ──────────────────────────────────────────────────────

  var api = {
    attach: attach,
    detach: detach,
    handleDispatch: handleDispatch,
    readSourceImage: readSourceImage,
    insertResult: insertResult,
    _normalizeDirections: _normalizeDirections,
    _state: _state,
    ENDPOINT_DEFAULT: ENDPOINT_DEFAULT
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraImageOutpaints = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
