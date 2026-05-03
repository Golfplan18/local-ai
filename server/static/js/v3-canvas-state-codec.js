/* v3-canvas-state-codec.js — Konva ↔ canvas-state v0.1 (2026-04-30)
 *
 * Bidirectional codec for the canvas-state schema (config/schemas/
 * canvas-state.schema.json). serializeFromPanel walks the panel's Konva
 * layers and emits a canvas_state.objects[] array. deserializeIntoPanel
 * reverses it: clears the layers, recreates each object as a Konva node,
 * and adds it back to the matching layer.
 *
 * Public API: window.OraV3CanvasStateCodec
 *   serializeFromPanel(panel, opts) → canvas_state
 *     opts.title             — metadata.title (optional)
 *     opts.canvas_size       — metadata.canvas_size override
 *
 *   deserializeIntoPanel(panel, state) → void
 *     Clears layers then re-populates from state.objects[].
 *
 * Coverage
 * --------
 *  ✓ shape (Rect / Ellipse / Circle / Line / Arrow + diamond-via-Line)
 *  ✓ text  (Text)
 *  ✓ image (Image with embedded base64; round-trips via toDataURL)
 *  ✗ group (children round-trip is delegated; nested shape-with-text groups
 *           survive because we serialize their Konva attrs, but custom
 *           constructors aren't reinstantiated)
 *  ✗ path  (freehand pen — captured as Konva.Line, no smoothing pass)
 *
 * Layers
 * ------
 * Maps via canonical kind: user-drawn shapes live on `user_input`,
 * annotations on `annotation`. Background images currently surface on
 * `user_input` (visual-panel doesn't expose backgroundLayer separately).
 */
(function () {
  'use strict';

  var SCHEMA_VERSION = '0.1';
  var FORMAT_ID      = 'ora-canvas';
  var DEFAULT_W      = 10000;
  var DEFAULT_H      = 10000;

  // ── helpers ────────────────────────────────────────────────────────────

  function _now() { return (new Date()).toISOString(); }

  function _newId(prefix) {
    return (prefix || 'obj') + '-' + Date.now().toString(36) + '-'
      + Math.floor(Math.random() * 1e6).toString(36);
  }

  function _layerKindFor(panel, layer) {
    if (!layer) return 'user_input';
    if (layer === panel.userInputLayer) return 'user_input';
    if (layer === panel.annotationLayer) return 'annotation';
    if (layer === panel.selectionLayer) return 'selection';
    if (layer === panel.backgroundLayer) return 'background';
    return 'user_input';
  }

  function _layerForKind(panel, kind) {
    switch (kind) {
      case 'annotation': return panel.annotationLayer || panel.userInputLayer;
      case 'background': return panel.backgroundLayer || panel.userInputLayer;
      case 'selection':  return panel.selectionLayer  || panel.userInputLayer;
      case 'user_input':
      default:           return panel.userInputLayer;
    }
  }

  // ── serialize ──────────────────────────────────────────────────────────

  function _nodeToObject(node, layerId, idx) {
    if (!node || typeof node.getClassName !== 'function') return null;
    var className = node.getClassName();
    var attrs = (typeof node.getAttrs === 'function') ? Object.assign({}, node.getAttrs()) : {};

    // Strip the Konva 'image' attr (HTMLImageElement) for Image nodes; we
    // re-derive image bytes via toDataURL into the typed image_data field.
    var imageData = null;
    if (className === 'Image' && attrs.image) {
      try {
        var imgEl = attrs.image;
        if (imgEl && typeof imgEl.src === 'string') {
          // If the source is already a data URL we can trim it; else use
          // an offscreen canvas to convert.
          if (imgEl.src.indexOf('data:') === 0) {
            var match = /^data:([^;]+);base64,(.+)$/.exec(imgEl.src);
            if (match) {
              imageData = { mime_type: match[1], encoding: 'base64', data: match[2] };
            }
          } else {
            try {
              var off = document.createElement('canvas');
              off.width  = imgEl.naturalWidth  || attrs.width  || imgEl.width  || 1;
              off.height = imgEl.naturalHeight || attrs.height || imgEl.height || 1;
              var ctx = off.getContext('2d');
              ctx.drawImage(imgEl, 0, 0, off.width, off.height);
              var dataUrl = off.toDataURL('image/png');
              var m2 = /^data:([^;]+);base64,(.+)$/.exec(dataUrl);
              if (m2) imageData = { mime_type: m2[1], encoding: 'base64', data: m2[2] };
            } catch (e) {
              // Tainted canvas (cross-origin image without CORS). Skip.
              imageData = null;
            }
          }
        }
      } catch (e) { /* ignore */ }
      delete attrs.image;
    }

    var kind = 'shape';
    if (className === 'Text')           kind = 'text';
    else if (className === 'Image')     kind = 'image';
    else if (className === 'Group')     kind = 'group';
    else if (className === 'Path' || className === 'Line') kind = (attrs.points && attrs.points.length > 4) ? 'path' : 'shape';

    var id = (typeof node.id === 'function' && node.id()) || attrs.id || _newId(kind);

    var obj = {
      id:          id,
      kind:        kind,
      layer:       layerId,
      konva_class: className,
      attrs:       attrs
    };

    // Pull common geometry to top level for downstream readers that
    // don't want to crawl attrs. Konva attrs are still authoritative.
    ['x', 'y', 'width', 'height', 'rotation', 'scaleX', 'scaleY', 'opacity', 'visible'].forEach(function (k) {
      if (typeof attrs[k] !== 'undefined') {
        // Keep Konva camelCase in attrs but mirror to schema snake_case at top
        var schemaKey = (k === 'scaleX') ? 'scale_x'
                      : (k === 'scaleY') ? 'scale_y'
                      : k;
        obj[schemaKey] = attrs[k];
      }
    });

    if (imageData) obj.image_data = imageData;

    // Group children — recurse, skipping transient overlay siblings.
    if (className === 'Group' && typeof node.getChildren === 'function') {
      obj.children = [];
      var kids = node.getChildren();
      for (var i = 0; i < kids.length; i++) {
        var childN = kids[i];
        var childName = (typeof childN.name === 'function') ? childN.name() : '';
        if (childName === 'tail-anchor' || childName === 'panel-grid-handle') continue;
        var child = _nodeToObject(childN, layerId, i);
        if (child) obj.children.push(child);
      }
    }

    return obj;
  }

  // V3 Item 12 Q1 follow-up — content-hash dedup for embedded image
  // binaries. Same image referenced twice in a single canvas (e.g. a
  // logo placed on two layers, or a PiP frame copied across panels)
  // gets stored once in a top-level ``binaries`` map. Each Image obj's
  // ``image_data`` is replaced with ``image_data_ref: <id>`` pointing
  // at the entry. Deserialize resolves the ref back to image_data.
  //
  // The id is a simple synchronous FNV-1a hash so we don't need
  // crypto.subtle (async) here. Collisions are vanishingly unlikely at
  // the scale of a single canvas (a handful of images at most).
  function _fnv1a(str) {
    var hash = 0x811c9dc5;
    for (var i = 0; i < str.length; i++) {
      hash ^= str.charCodeAt(i);
      hash = (hash * 0x01000193) >>> 0;
    }
    return ('00000000' + hash.toString(16)).slice(-8);
  }

  function _internImageBinaries(objects, binaries) {
    objects.forEach(function (obj) {
      if (obj && obj.image_data && obj.image_data.data) {
        var data = obj.image_data.data;
        var mime = obj.image_data.mime_type || 'image/png';
        var hash = _fnv1a(mime + ':' + data);
        if (!binaries[hash]) {
          binaries[hash] = {
            mime_type: mime,
            encoding:  obj.image_data.encoding || 'base64',
            data:      data,
          };
        }
        obj.image_data_ref = hash;
        delete obj.image_data;
      }
      if (Array.isArray(obj && obj.children)) {
        _internImageBinaries(obj.children, binaries);
      }
    });
  }

  function serializeFromPanel(panel, opts) {
    opts = opts || {};
    var objects = [];

    var layers = [
      { node: panel.userInputLayer,  id: 'user_input' },
      { node: panel.annotationLayer, id: 'annotation' }
    ];

    // Names of transient/derived overlays we never want serialized — they
    // get re-derived on canvas load (panel-grid handles via the panel-grid
    // module; tail-anchor handles via the bubble-tools module).
    var SKIP_NAMES = {
      'selection': 1,
      'transformer': 1,
      'panel-grid-handle': 1,
      'tail-anchor': 1
    };

    layers.forEach(function (entry) {
      if (!entry.node || typeof entry.node.getChildren !== 'function') return;
      var kids = entry.node.getChildren();
      for (var i = 0; i < kids.length; i++) {
        var n = kids[i];
        var name = (typeof n.name === 'function') ? n.name() : '';
        if (SKIP_NAMES[name]) continue;
        if (typeof n.getClassName === 'function' && n.getClassName() === 'Transformer') continue;

        var obj = _nodeToObject(n, entry.id, i);
        if (obj) objects.push(obj);
      }
    });

    // V3 Item 12 Q1 follow-up — intern every embedded image binary into a
    // top-level ``binaries`` map keyed by content hash; the per-object
    // ``image_data`` is replaced with ``image_data_ref``. Files where no
    // image binaries appear get an empty map — preserves shape for
    // forward-compat tooling that reads `state.binaries` unconditionally.
    var binaries = {};
    _internImageBinaries(objects, binaries);

    return {
      schema_version: SCHEMA_VERSION,
      format_id:      FORMAT_ID,
      metadata: {
        title:       opts.title || 'Untitled',
        canvas_size: opts.canvas_size || { width: DEFAULT_W, height: DEFAULT_H },
        created_at:  opts.created_at || _now(),
        modified_at: _now()
      },
      view: {
        zoom: (typeof panel._zoom === 'number') ? panel._zoom
            : (typeof panel.getZoom === 'function') ? panel.getZoom()
            : 1,
        pan: { x: 0, y: 0 }
      },
      layers: [
        { id: 'background', kind: 'background' },
        { id: 'annotation', kind: 'annotation' },
        { id: 'user_input', kind: 'user_input' },
        { id: 'selection',  kind: 'selection' }
      ],
      binaries: binaries,
      objects:  objects
    };
  }

  // ── deserialize ────────────────────────────────────────────────────────

  function _ensureLayerCleared(layer) {
    if (!layer || typeof layer.removeChildren !== 'function') return;
    // Preserve Konva-internal infra by destroying only user shapes.
    var kids = layer.getChildren ? layer.getChildren().slice() : [];
    for (var i = 0; i < kids.length; i++) {
      var k = kids[i];
      var nm = (typeof k.name === 'function') ? k.name() : '';
      if (nm === 'transformer') continue;
      if (typeof k.getClassName === 'function' && k.getClassName() === 'Transformer') continue;
      try { k.destroy(); } catch (e) { /* ignore */ }
    }
  }

  function _objectToNode(obj, KonvaNS) {
    if (!obj || !obj.konva_class) return null;
    var ctor = KonvaNS[obj.konva_class];
    if (!ctor) {
      // Unknown class — fall back to a Group so children can still mount.
      if (obj.kind === 'group' && KonvaNS.Group) ctor = KonvaNS.Group;
      else return null;
    }

    var attrs = Object.assign({}, obj.attrs || {});

    // Top-level obj.id is the canonical identity; mirror into attrs.id so
    // Konva node.id() returns it after construction. Without this, calls
    // like stage.findOne('#some-id') and bubble↔target linking fail.
    if (obj.id && !attrs.id) attrs.id = obj.id;

    // Image objects need an HTMLImageElement reconstituted from image_data.
    if (obj.kind === 'image' && obj.image_data && obj.image_data.data) {
      var dataUrl = 'data:' + obj.image_data.mime_type + ';base64,' + obj.image_data.data;
      var img = new Image();
      img.src = dataUrl;
      attrs.image = img;
    }

    var node;
    try { node = new ctor(attrs); }
    catch (e) {
      console.warn('[v3-canvas-state-codec] node construct failed for', obj.konva_class, e && e.message);
      return null;
    }

    if (obj.kind === 'group' && Array.isArray(obj.children)) {
      obj.children.forEach(function (childObj) {
        var childNode = _objectToNode(childObj, KonvaNS);
        if (childNode && typeof node.add === 'function') node.add(childNode);
      });
    }

    return node;
  }

  // V3 Item 12 Q1 follow-up — resolve content-hashed binary refs back
  // to inline image_data before Konva sees them. Walks groups too.
  function _hydrateImageBinaries(objects, binaries) {
    if (!binaries) return;
    objects.forEach(function (obj) {
      if (obj && obj.image_data_ref && binaries[obj.image_data_ref]) {
        obj.image_data = binaries[obj.image_data_ref];
        // Keep the ref around for save round-trips; harmless on the
        // Konva side because _objectToNode reads image_data, not _ref.
      }
      if (Array.isArray(obj && obj.children)) {
        _hydrateImageBinaries(obj.children, binaries);
      }
    });
  }

  function deserializeIntoPanel(panel, state) {
    if (!state || !Array.isArray(state.objects)) return;
    var KonvaNS = (typeof window !== 'undefined' && window.Konva) || null;
    if (!KonvaNS) {
      console.warn('[v3-canvas-state-codec] Konva not available; cannot deserialize');
      return;
    }

    _ensureLayerCleared(panel.userInputLayer);
    _ensureLayerCleared(panel.annotationLayer);

    // Hydrate image_data_ref → image_data before object construction so
    // _objectToNode's existing image_data path works without changes.
    _hydrateImageBinaries(state.objects, state.binaries || {});

    state.objects.forEach(function (obj) {
      var layer = _layerForKind(panel, obj.layer);
      if (!layer) return;
      var node = _objectToNode(obj, KonvaNS);
      if (node) layer.add(node);
    });

    if (panel.userInputLayer && typeof panel.userInputLayer.draw === 'function') panel.userInputLayer.draw();
    if (panel.annotationLayer && typeof panel.annotationLayer.draw === 'function') panel.annotationLayer.draw();

    // Reset undo history — applied state is the new baseline.
    if (Array.isArray(panel._history)) panel._history.length = 0;
    panel._historyCursor = 0;

    // Apply view if present.
    if (state.view) {
      if (typeof panel.setZoom === 'function') panel.setZoom(state.view.zoom);
      else if (typeof panel.zoomTo === 'function') panel.zoomTo(state.view.zoom);
    }

    try {
      document.dispatchEvent(new CustomEvent('ora:canvas-loaded', { detail: { state: state } }));
    } catch (e) {}

    // Fire layer add event so v3-canvas-mount's empty-class observer updates.
    if (panel.userInputLayer && typeof panel.userInputLayer.fire === 'function') {
      try { panel.userInputLayer.fire('add'); } catch (e) {}
    }
  }

  // ── panel.loadCanvasState patch ───────────────────────────────────────
  // Visual-panel doesn't ship a loadCanvasState method. The codec's
  // deserialize is the natural implementation. We attach it as a method on
  // the panel as soon as the canvas mounts, so any caller that does
  // `panel.loadCanvasState(state)` works regardless of whether the
  // template gallery has been opened. Previously the gallery patched it
  // lazily on first open, which was brittle.
  function _patchPanel(panel) {
    if (!panel || typeof panel.loadCanvasState === 'function') return;
    panel.loadCanvasState = function (state) {
      try { deserializeIntoPanel(panel, state); }
      catch (e) { console.warn('[v3-canvas-state-codec] loadCanvasState failed:', e && e.message); }
    };
  }

  if (typeof document !== 'undefined') {
    document.addEventListener('ora:canvas-mounted', function () {
      var panel = window.OraCanvas && window.OraCanvas.panel;
      _patchPanel(panel);
    });
  }

  window.OraV3CanvasStateCodec = {
    serializeFromPanel:   serializeFromPanel,
    deserializeIntoPanel: deserializeIntoPanel,
    _patchPanel:          _patchPanel
  };
})();
