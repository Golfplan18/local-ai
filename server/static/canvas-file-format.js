/**
 * canvas-file-format.js — WP-7.0.2
 *
 * Reader / writer for the Ora canvas-state file format.
 *
 *   .ora-canvas       → gzip-compressed JSON (default save format)
 *   .ora-canvas.json  → uncompressed JSON (export-on-demand "Save as readable copy")
 *
 * Both surfacing forms wrap the SAME canonical JSON payload; round-trip is
 * byte-identical after decompression. The schema lives at
 * `~/ora/config/schemas/canvas-state.schema.json` and is the source of truth
 * for the structure described here.
 *
 * Public surface — exposed as `window.OraCanvasFileFormat`:
 *
 *   write(state, { compressed }) → Promise<Uint8Array>
 *     Serialize a canvas-state object into wire bytes.
 *     `compressed: true`  → gzip-compressed (.ora-canvas)         [default]
 *     `compressed: false` → UTF-8 JSON bytes (.ora-canvas.json)
 *
 *   read(bytes) → Promise<state>
 *     Parse wire bytes back into a canvas-state object. Auto-detects gzip
 *     vs raw JSON by sniffing the magic header (1F 8B). The returned object
 *     is structurally identical to the input passed to write().
 *
 *   validate(state) → { valid, errors }
 *     Structural validation. Uses Ajv when bootstrapped via
 *     OraCanvasFileFormat._setAjv(ajvInstance) (the visual compiler's
 *     bootstrapAjv path can call this). Otherwise falls back to a hand-rolled
 *     check covering required fields, additionalProperties, and the
 *     image-must-have-image_data invariant.
 *
 *   isCompressed(bytes) → boolean
 *     Header sniff helper. True iff bytes begin with the gzip magic 1F 8B.
 *
 *   newCanvasState({ canvas_size, layers }) → state
 *     Convenience factory for an empty canvas with the four canonical layers
 *     (background / annotation / user_input / selection) and a default view.
 *
 * ── Compression ─────────────────────────────────────────────────────────────
 *
 * Uses the WHATWG Streams API CompressionStream / DecompressionStream when
 * available (modern browsers, Node 18+). For environments where the streams
 * API is missing on the runtime global (jsdom test harness lacks it on
 * window), an alternate gzip implementation can be injected via
 * OraCanvasFileFormat._setGzipImpl({ deflate, inflate }). Each function takes
 * a Uint8Array and returns a Uint8Array (sync OR Promise). The harness
 * shims this to Node's zlib so the round-trip suite runs without a vendored
 * pako bundle.
 *
 * ── Round-trip contract ────────────────────────────────────────────────────
 *
 * For any canvas-state object S with no functions and no NaN/Infinity:
 *
 *     read(write(S, {compressed: true}))   ⟶ deepEqual(S)
 *     read(write(S, {compressed: false}))  ⟶ deepEqual(S)
 *     gunzip(write(S, {compressed: true})) ⟶ write(S, {compressed: false})
 *
 * The third invariant is the bytes-equivalent-after-decompression criterion
 * from WP-7.0.2's test brief.
 *
 * No direct dependency on Konva or the visual panel. Operates on plain
 * canvas-state JSON; the panel is responsible for converting Konva nodes
 * into canvas-state objects (and back) before/after calling this module.
 */

(function () {
  'use strict';

  var SCHEMA_VERSION = '0.1.0';
  var FORMAT_ID      = 'ora-canvas';

  // gzip magic bytes (RFC 1952 §2.3.1).
  var GZIP_MAGIC_0 = 0x1F;
  var GZIP_MAGIC_1 = 0x8B;

  // Default canvas dims per Plan §11.7 (10000 x 10000 px).
  var DEFAULT_CANVAS_W = 10000;
  var DEFAULT_CANVAS_H = 10000;

  // Injection slots — populated by host integrations. Both default to null;
  // the implementations below auto-detect runtime alternatives.
  var _ajv          = null;          // Ajv instance with the canvas-state schema added
  var _ajvValidate  = null;          // compiled validator function from _ajv
  var _gzipImpl     = null;          // { deflate(bytes)→bytes|Promise, inflate(bytes)→bytes|Promise }

  // ── Utilities ─────────────────────────────────────────────────────────────

  function _isObj(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }
  function _isArr(v) { return Array.isArray(v); }

  /**
   * Stable JSON stringification — sorts object keys recursively. The
   * compressed and uncompressed surfacing forms must produce the same
   * decompressed bytes, so we canonicalize before serializing. Arrays
   * preserve order (semantic).
   */
  function _canonicalize(value) {
    if (value === null) return null;
    if (typeof value !== 'object') return value;
    if (_isArr(value)) {
      var out = new Array(value.length);
      for (var i = 0; i < value.length; i++) out[i] = _canonicalize(value[i]);
      return out;
    }
    var keys = Object.keys(value).sort();
    var obj = {};
    for (var k = 0; k < keys.length; k++) obj[keys[k]] = _canonicalize(value[keys[k]]);
    return obj;
  }

  function _utf8Encode(str) {
    if (typeof TextEncoder !== 'undefined') {
      return new TextEncoder().encode(str);
    }
    // Fallback (older runtimes): naive UTF-16 → UTF-8 walk. Canvas state is
    // ASCII-dominant in practice (base64 + JSON syntax) so this stays fast.
    var bytes = [];
    for (var i = 0; i < str.length; i++) {
      var c = str.charCodeAt(i);
      if (c < 0x80) bytes.push(c);
      else if (c < 0x800) { bytes.push(0xC0 | (c >> 6)); bytes.push(0x80 | (c & 0x3F)); }
      else if (c < 0xD800 || c >= 0xE000) {
        bytes.push(0xE0 | (c >> 12));
        bytes.push(0x80 | ((c >> 6) & 0x3F));
        bytes.push(0x80 | (c & 0x3F));
      } else {
        i++;
        var c2 = str.charCodeAt(i);
        var cp = 0x10000 + (((c & 0x3FF) << 10) | (c2 & 0x3FF));
        bytes.push(0xF0 | (cp >> 18));
        bytes.push(0x80 | ((cp >> 12) & 0x3F));
        bytes.push(0x80 | ((cp >> 6) & 0x3F));
        bytes.push(0x80 | (cp & 0x3F));
      }
    }
    return new Uint8Array(bytes);
  }

  function _utf8Decode(bytes) {
    if (typeof TextDecoder !== 'undefined') {
      return new TextDecoder('utf-8').decode(bytes);
    }
    // Fallback inverse of _utf8Encode.
    var out = '';
    var i = 0;
    while (i < bytes.length) {
      var b = bytes[i++];
      if (b < 0x80) { out += String.fromCharCode(b); continue; }
      if ((b & 0xE0) === 0xC0) {
        out += String.fromCharCode(((b & 0x1F) << 6) | (bytes[i++] & 0x3F));
        continue;
      }
      if ((b & 0xF0) === 0xE0) {
        out += String.fromCharCode(((b & 0x0F) << 12) | ((bytes[i++] & 0x3F) << 6) | (bytes[i++] & 0x3F));
        continue;
      }
      var cp = ((b & 0x07) << 18) | ((bytes[i++] & 0x3F) << 12) | ((bytes[i++] & 0x3F) << 6) | (bytes[i++] & 0x3F);
      cp -= 0x10000;
      out += String.fromCharCode(0xD800 | (cp >> 10));
      out += String.fromCharCode(0xDC00 | (cp & 0x3FF));
    }
    return out;
  }

  function _toUint8(input) {
    if (input instanceof Uint8Array) return input;
    if (typeof Buffer !== 'undefined' && input && input.buffer && input.constructor && input.constructor.name === 'Buffer') {
      // Node Buffer → Uint8Array view over the same bytes.
      return new Uint8Array(input.buffer, input.byteOffset, input.byteLength);
    }
    if (input && input.byteLength !== undefined && input.buffer) {
      return new Uint8Array(input.buffer, input.byteOffset || 0, input.byteLength);
    }
    if (input instanceof ArrayBuffer) return new Uint8Array(input);
    throw new Error('canvas-file-format: cannot coerce ' + Object.prototype.toString.call(input) + ' to Uint8Array');
  }

  // ── Compression layer ─────────────────────────────────────────────────────

  function _hasStreamsCompression() {
    return typeof globalThis !== 'undefined'
        && typeof globalThis.CompressionStream === 'function'
        && typeof globalThis.DecompressionStream === 'function';
  }

  function _streamsGzip(bytes) {
    var input = _toUint8(bytes);
    var stream = new globalThis.CompressionStream('gzip');
    var writer = stream.writable.getWriter();
    writer.write(input);
    writer.close();
    return new Response(stream.readable).arrayBuffer().then(function (ab) {
      return new Uint8Array(ab);
    });
  }

  function _streamsGunzip(bytes) {
    var input = _toUint8(bytes);
    var stream = new globalThis.DecompressionStream('gzip');
    var writer = stream.writable.getWriter();
    writer.write(input);
    writer.close();
    return new Response(stream.readable).arrayBuffer().then(function (ab) {
      return new Uint8Array(ab);
    });
  }

  function _gzip(bytes) {
    if (_gzipImpl && typeof _gzipImpl.deflate === 'function') {
      return Promise.resolve(_gzipImpl.deflate(_toUint8(bytes))).then(_toUint8);
    }
    if (_hasStreamsCompression()) {
      return _streamsGzip(bytes);
    }
    return Promise.reject(new Error(
      'canvas-file-format: no gzip implementation available. ' +
      'Inject one via OraCanvasFileFormat._setGzipImpl({ deflate, inflate }).'
    ));
  }

  function _gunzip(bytes) {
    if (_gzipImpl && typeof _gzipImpl.inflate === 'function') {
      return Promise.resolve(_gzipImpl.inflate(_toUint8(bytes))).then(_toUint8);
    }
    if (_hasStreamsCompression()) {
      return _streamsGunzip(bytes);
    }
    return Promise.reject(new Error(
      'canvas-file-format: no gunzip implementation available. ' +
      'Inject one via OraCanvasFileFormat._setGzipImpl({ deflate, inflate }).'
    ));
  }

  function isCompressed(bytes) {
    var u = _toUint8(bytes);
    return u.length >= 2 && u[0] === GZIP_MAGIC_0 && u[1] === GZIP_MAGIC_1;
  }

  // ── Public API ────────────────────────────────────────────────────────────

  /**
   * Build an empty canvas state with the four canonical Konva-mirrored layers
   * (background / annotation / user_input / selection) and a default
   * 100%-zoom centered view. `opts` overrides:
   *   canvas_size: { width, height }   default 10000 x 10000
   *   layers:       array              overrides the default layer set
   *   conversation_id: string          optional metadata tag
   *   title:        string             optional metadata tag
   */
  function newCanvasState(opts) {
    opts = _isObj(opts) ? opts : {};
    var size = _isObj(opts.canvas_size) ? opts.canvas_size : { width: DEFAULT_CANVAS_W, height: DEFAULT_CANVAS_H };
    var now = (new Date()).toISOString();
    var layers = _isArr(opts.layers) ? opts.layers : [
      { id: 'background',  kind: 'background',  visible: true,  locked: false, opacity: 1 },
      { id: 'annotation',  kind: 'annotation',  visible: true,  locked: false, opacity: 1 },
      { id: 'user_input',  kind: 'user_input',  visible: true,  locked: false, opacity: 1 },
      { id: 'selection',   kind: 'selection',   visible: true,  locked: false, opacity: 1 }
    ];
    var meta = { canvas_size: { width: size.width, height: size.height }, created_at: now, modified_at: now };
    if (opts.title)            meta.title           = opts.title;
    if (opts.conversation_id)  meta.conversation_id = opts.conversation_id;
    if (opts.ora_version)      meta.ora_version     = opts.ora_version;
    return {
      schema_version: SCHEMA_VERSION,
      format_id:      FORMAT_ID,
      metadata:       meta,
      view:           { zoom: 1, pan: { x: 0, y: 0 } },
      layers:         layers,
      objects:        []
    };
  }

  /**
   * Serialize a canvas-state object to wire bytes.
   *   write(state)                         → gzip bytes (default)
   *   write(state, { compressed: true })   → gzip bytes
   *   write(state, { compressed: false })  → utf-8 JSON bytes
   *
   * Also accepts { canonical: false } to skip key sorting (useful for
   * preserving insertion order during diagnostic exports).
   *
   * Returns a Promise<Uint8Array>.
   */
  function write(state, opts) {
    if (!_isObj(state)) {
      return Promise.reject(new Error('canvas-file-format.write: state must be an object'));
    }
    opts = _isObj(opts) ? opts : {};
    var compressed = (opts.compressed !== false);   // default true
    var canonical  = (opts.canonical  !== false);   // default true
    var payload = canonical ? _canonicalize(state) : state;
    var json    = JSON.stringify(payload);
    var bytes   = _utf8Encode(json);
    if (!compressed) return Promise.resolve(bytes);
    return _gzip(bytes);
  }

  /**
   * Synchronous JSON-only write — convenience for callers that already
   * know they want the uncompressed form. Returns a Uint8Array directly.
   */
  function writeJsonBytes(state, opts) {
    if (!_isObj(state)) throw new Error('canvas-file-format.writeJsonBytes: state must be an object');
    opts = _isObj(opts) ? opts : {};
    var canonical = (opts.canonical !== false);
    var payload = canonical ? _canonicalize(state) : state;
    return _utf8Encode(JSON.stringify(payload));
  }

  /**
   * Synchronous JSON string view — useful for debugging or for the
   * "Save as readable copy" command that wants pretty-printed output.
   */
  function writeJsonString(state, opts) {
    if (!_isObj(state)) throw new Error('canvas-file-format.writeJsonString: state must be an object');
    opts = _isObj(opts) ? opts : {};
    var canonical = (opts.canonical !== false);
    var indent    = (typeof opts.indent === 'number') ? opts.indent : 0;
    var payload = canonical ? _canonicalize(state) : state;
    return indent > 0 ? JSON.stringify(payload, null, indent) : JSON.stringify(payload);
  }

  /**
   * Parse wire bytes back into a canvas-state object. Auto-detects gzip
   * vs raw JSON via header sniff (1F 8B). Accepts Uint8Array, ArrayBuffer,
   * Buffer, or any TypedArray view. Returns Promise<state>.
   */
  function read(bytes) {
    var u;
    try { u = _toUint8(bytes); }
    catch (e) { return Promise.reject(e); }
    var step = isCompressed(u) ? _gunzip(u) : Promise.resolve(u);
    return step.then(function (jsonBytes) {
      var text = _utf8Decode(jsonBytes);
      var obj;
      try { obj = JSON.parse(text); }
      catch (e) {
        throw new Error('canvas-file-format.read: invalid JSON — ' + (e && e.message ? e.message : String(e)));
      }
      if (!_isObj(obj)) {
        throw new Error('canvas-file-format.read: top-level value must be an object');
      }
      if (obj.format_id !== FORMAT_ID) {
        throw new Error('canvas-file-format.read: format_id mismatch (expected "' + FORMAT_ID + '", got ' + JSON.stringify(obj.format_id) + ')');
      }
      return obj;
    });
  }

  /**
   * Synchronous read — caller asserts the bytes are uncompressed.
   * Throws if a gzip header is detected.
   */
  function readJsonBytes(bytes) {
    var u = _toUint8(bytes);
    if (isCompressed(u)) {
      throw new Error('canvas-file-format.readJsonBytes: bytes are gzip-compressed; use read() instead.');
    }
    var obj = JSON.parse(_utf8Decode(u));
    if (!_isObj(obj)) throw new Error('canvas-file-format.readJsonBytes: top-level value must be an object');
    if (obj.format_id !== FORMAT_ID) {
      throw new Error('canvas-file-format.readJsonBytes: format_id mismatch (got ' + JSON.stringify(obj.format_id) + ')');
    }
    return obj;
  }

  // ── Validation ────────────────────────────────────────────────────────────

  function _setAjv(ajvInstance) {
    _ajv = ajvInstance || null;
    _ajvValidate = null;
    if (_ajv && typeof _ajv.getSchema === 'function') {
      var got = _ajv.getSchema('https://ora.local/schemas/canvas-state.schema.json');
      if (got) _ajvValidate = got;
    }
  }

  function _setGzipImpl(impl) {
    _gzipImpl = impl || null;
  }

  /**
   * Hand-rolled fallback validator. Covers the load-bearing invariants:
   *   - top-level required fields and additionalProperties:false
   *   - layers minItems=1 + per-layer required + kind enum
   *   - objects: required id/kind/layer; image objects MUST carry image_data;
   *     group objects MUST carry children[]; image_data fields validate
   *
   * Used when Ajv is not bootstrapped; otherwise the Ajv-compiled validator
   * is the source of truth.
   */
  function _structuralValidate(state) {
    var errs = [];
    if (!_isObj(state)) {
      errs.push({ path: '', message: 'state must be an object' });
      return { valid: false, errors: errs };
    }
    var allowedTop = { schema_version: 1, format_id: 1, metadata: 1, view: 1, layers: 1, objects: 1 };
    for (var k in state) {
      if (Object.prototype.hasOwnProperty.call(state, k) && !allowedTop[k]) {
        errs.push({ path: '/' + k, message: 'unknown top-level property' });
      }
    }
    var required = ['schema_version', 'format_id', 'metadata', 'view', 'layers', 'objects'];
    for (var i = 0; i < required.length; i++) {
      if (!(required[i] in state)) errs.push({ path: '/' + required[i], message: 'required' });
    }
    if (state.format_id !== FORMAT_ID) {
      errs.push({ path: '/format_id', message: 'must equal "' + FORMAT_ID + '"' });
    }
    if (typeof state.schema_version !== 'string' || !/^[0-9]+\.[0-9]+(\.[0-9]+)?$/.test(state.schema_version)) {
      errs.push({ path: '/schema_version', message: 'must be a semver string' });
    }
    if (_isObj(state.metadata)) {
      if (!_isObj(state.metadata.canvas_size)) {
        errs.push({ path: '/metadata/canvas_size', message: 'required object with width+height' });
      } else {
        var cs = state.metadata.canvas_size;
        if (typeof cs.width !== 'number' || cs.width <= 0)   errs.push({ path: '/metadata/canvas_size/width',  message: 'positive number required' });
        if (typeof cs.height !== 'number' || cs.height <= 0) errs.push({ path: '/metadata/canvas_size/height', message: 'positive number required' });
      }
    } else {
      errs.push({ path: '/metadata', message: 'required object' });
    }
    if (_isObj(state.view)) {
      if (typeof state.view.zoom !== 'number' || state.view.zoom <= 0) {
        errs.push({ path: '/view/zoom', message: 'positive number required' });
      }
      if (!_isObj(state.view.pan) || typeof state.view.pan.x !== 'number' || typeof state.view.pan.y !== 'number') {
        errs.push({ path: '/view/pan', message: 'object with numeric x and y required' });
      }
    } else {
      errs.push({ path: '/view', message: 'required object' });
    }
    if (!_isArr(state.layers) || state.layers.length < 1) {
      errs.push({ path: '/layers', message: 'non-empty array required' });
    } else {
      var layerIds = {};
      var layerKinds = { background: 1, annotation: 1, user_input: 1, selection: 1 };
      for (var li = 0; li < state.layers.length; li++) {
        var L = state.layers[li];
        if (!_isObj(L)) { errs.push({ path: '/layers[' + li + ']', message: 'object required' }); continue; }
        if (typeof L.id !== 'string' || !L.id) errs.push({ path: '/layers[' + li + ']/id', message: 'non-empty string required' });
        if (!layerKinds[L.kind]) errs.push({ path: '/layers[' + li + ']/kind', message: 'must be background|annotation|user_input|selection' });
        if (L.id && layerIds[L.id]) errs.push({ path: '/layers[' + li + ']/id', message: 'duplicate layer id "' + L.id + '"' });
        layerIds[L.id] = 1;
      }
    }
    if (!_isArr(state.objects)) {
      errs.push({ path: '/objects', message: 'array required' });
    } else {
      var objectIds = {};
      var objKinds = { shape: 1, text: 1, image: 1, group: 1, path: 1 };
      var imgEnc = { base64: 1 };
      var validateObject = function (O, base) {
        if (!_isObj(O)) { errs.push({ path: base, message: 'object required' }); return; }
        if (typeof O.id !== 'string' || !O.id) errs.push({ path: base + '/id', message: 'non-empty string required' });
        if (!objKinds[O.kind]) errs.push({ path: base + '/kind', message: 'must be shape|text|image|group|path' });
        if (typeof O.layer !== 'string' || !O.layer) errs.push({ path: base + '/layer', message: 'non-empty layer reference required' });
        if (O.id) {
          if (objectIds[O.id]) errs.push({ path: base + '/id', message: 'duplicate object id "' + O.id + '"' });
          objectIds[O.id] = 1;
        }
        if (O.kind === 'image') {
          if (!_isObj(O.image_data)) {
            errs.push({ path: base + '/image_data', message: 'required for kind=image' });
          } else {
            var I = O.image_data;
            if (typeof I.mime_type !== 'string' || !/^image\/[A-Za-z0-9.+-]+$/.test(I.mime_type)) {
              errs.push({ path: base + '/image_data/mime_type', message: 'must match image/<subtype>' });
            }
            if (!imgEnc[I.encoding]) errs.push({ path: base + '/image_data/encoding', message: 'must be "base64"' });
            if (typeof I.data !== 'string' || !I.data.length) errs.push({ path: base + '/image_data/data', message: 'non-empty base64 string required' });
            if (typeof I.data === 'string' && /^data:/.test(I.data)) {
              errs.push({ path: base + '/image_data/data', message: 'must NOT include a data: URL prefix; raw base64 only' });
            }
          }
        }
        if (O.kind === 'group') {
          if (!_isArr(O.children)) errs.push({ path: base + '/children', message: 'required array for kind=group' });
          else {
            for (var ci = 0; ci < O.children.length; ci++) {
              validateObject(O.children[ci], base + '/children[' + ci + ']');
            }
          }
        }
      };
      for (var oi = 0; oi < state.objects.length; oi++) {
        validateObject(state.objects[oi], '/objects[' + oi + ']');
      }
    }
    return { valid: errs.length === 0, errors: errs };
  }

  function validate(state) {
    if (_ajvValidate) {
      var ok = _ajvValidate(state);
      if (ok) return { valid: true, errors: [] };
      var errors = (_ajvValidate.errors || []).map(function (e) {
        return { path: e.instancePath || '', message: e.message + (e.params ? ' ' + JSON.stringify(e.params) : '') };
      });
      return { valid: false, errors: errors };
    }
    return _structuralValidate(state);
  }

  // ── Exports ───────────────────────────────────────────────────────────────

  var ns = {
    SCHEMA_VERSION:   SCHEMA_VERSION,
    FORMAT_ID:        FORMAT_ID,
    DEFAULT_CANVAS_W: DEFAULT_CANVAS_W,
    DEFAULT_CANVAS_H: DEFAULT_CANVAS_H,
    write:            write,
    writeJsonBytes:   writeJsonBytes,
    writeJsonString:  writeJsonString,
    read:             read,
    readJsonBytes:    readJsonBytes,
    validate:         validate,
    isCompressed:     isCompressed,
    newCanvasState:   newCanvasState,
    // Injection slots — host environments call these once at boot.
    _setAjv:          _setAjv,
    _setGzipImpl:     _setGzipImpl,
    // Internals exposed for tests.
    _canonicalize:    _canonicalize,
    _structuralValidate: _structuralValidate
  };

  if (typeof window !== 'undefined') {
    window.OraCanvasFileFormat = ns;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = ns;
  }
})();
