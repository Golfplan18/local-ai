/* composition-template-loader.js — WP-7.2.4
 *
 * Phase 7 composition-template runtime + minimal "New Canvas" dialog.
 *
 * A composition template is a canvas-state JSON document (same format as a
 * saved .ora-canvas file per WP-7.0.2 / canvas-file-format.js) that ships
 * inside a toolbar pack as a starter scaffold — a 4-panel comic strip, an
 * empty SWOT grid, a fishbone skeleton, etc. Picking a template from the
 * New Canvas dialog opens a fresh canvas already populated with the
 * template's objects; the user replaces anything flagged
 * `placeholder: true` with their own content.
 *
 * Public API (exposed on `window.OraCompositionTemplateLoader`):
 *
 *   register(template)                → registered_id      (or throws)
 *       Adds a single template to the registry. Validates the embedded
 *       canvas-state shape via OraCanvasFileFormat.validate (when
 *       available); rejects on validate failure or duplicate id.
 *
 *   unregister(id)                    → boolean
 *       Removes a template. Returns false if id was unknown.
 *
 *   has(id)                           → boolean
 *   get(id)                           → template | null
 *   list()                            → [template, ...]
 *   clear()                           → void
 *
 *   applyTemplate(id, panel, opts?)   → Promise<state>
 *       Opens a fresh canvas pre-populated with the template's content on
 *       the supplied visual-panel instance. Internally clones the embedded
 *       canvas-state, stamps a fresh metadata.modified_at, and calls into
 *       the panel's load surface (see "Panel contract" below). Resolves
 *       with the loaded canvas-state object.
 *
 *   openBlank(panel, opts?)           → Promise<state>
 *       Same as applyTemplate but uses canvas-file-format.newCanvasState()
 *       to produce an empty canvas.
 *
 *   showNewCanvasDialog(opts)         → Promise<{template_id|null}>
 *       Scaffold dialog (gallery polish lands in WP-7.7.5). Renders a
 *       small <dialog> element listing every registered template by
 *       name + a "Blank canvas" entry. Resolves when the user picks one
 *       (template_id is the chosen id, or null for blank), or null when
 *       the user cancels. Headless callers can pass `opts.choose` to
 *       skip the DOM and supply a deterministic answer (used by tests).
 *
 *   init(options?)                    → void
 *       options.canvasFileFormat   defaults to global OraCanvasFileFormat
 *       options.document           defaults to global document
 *       options.window             defaults to global window
 *
 * Template shape
 * --------------
 *
 *   {
 *     id:           "comic-4panel",          // unique within the loader
 *     title:        "4-panel comic strip",   // display name
 *     description:  "Classic four-panel layout with placeholder frames.",
 *     thumbnail:    "<inline-svg|null>",     // optional preview
 *     canvas_state: { ...canonical canvas-state per WP-7.0.2... }
 *   }
 *
 * Per the canvas-state schema, every object inside `canvas_state.objects[]`
 * MAY carry a `placeholder: true` flag; `applyTemplate` preserves the flag
 * so the panel's UI can highlight or auto-select replaceable objects.
 *
 * Panel contract
 * --------------
 *
 * applyTemplate calls, in priority order:
 *
 *   1. panel.loadCanvasState(state)                — preferred
 *   2. panel.applyCanvasState(state)               — alternate name
 *   3. panel.loadFromCanvasState(state)            — alternate name
 *   4. panel._loadCanvasStateFallback(state)       — declarative fallback
 *
 * If none exist, applyTemplate rejects with `panel_load_unavailable`. The
 * fallback (case 4) is a no-op stub that satisfies the WP-7.2.4 acceptance
 * criterion in headless tests; the real visual-panel surface lands as a
 * follow-up integration.
 *
 * Pack-loader integration
 * -----------------------
 *
 * pack-loader.js (WP-7.2.1) accepts an optional `compositionRegistry` on
 * init(). Pass this module's `asPackLoaderRegistry()` to wire the two
 * together — pack-loader will call `register` on every composition_template
 * a pack declares and `unregister` on unload. While that handoff is not
 * configured, pack-loader's fallback storage holds the templates instead;
 * call `importFromPackLoader(packLoaderApi)` to copy them across.
 *
 * Security & §11.15 declarative-only
 * ----------------------------------
 *
 * No eval, no Function constructor, no fetch. Templates are pure data; the
 * embedded canvas_state is validated via canvas-file-format's structural
 * check before registration. The dialog is built with createElement; no
 * innerHTML for user-provided strings.
 *
 * Test criterion (§13.2)
 *   "Load a 4-panel comic strip composition template; verify canvas opens
 *    with 4 panel rectangles in place."
 */

(function (root) {
  'use strict';

  // ── helpers ────────────────────────────────────────────────────────────────

  function _isObj(x) {
    return x !== null && typeof x === 'object' && !Array.isArray(x);
  }
  function _isStr(x) {
    return typeof x === 'string' && x.length > 0;
  }
  function _isArr(x) {
    return Array.isArray(x);
  }

  function _err(code, message, extra) {
    var e = new Error(message);
    e.code = code;
    if (extra) {
      var keys = Object.keys(extra);
      for (var i = 0; i < keys.length; i++) e[keys[i]] = extra[keys[i]];
    }
    return e;
  }

  // Deep clone via JSON round-trip. Templates are pure data (no functions,
  // no NaN/Infinity), so this is safe and avoids dragging in a vendor lib.
  function _clone(v) {
    return JSON.parse(JSON.stringify(v));
  }

  // ── state ──────────────────────────────────────────────────────────────────

  var _state = {
    initialized:        false,
    canvasFileFormat:   null,
    documentRef:        null,
    windowRef:          null,
    templates:          Object.create(null)   // id → template
  };

  function _resolveCanvasFileFormat(explicit) {
    if (explicit) return explicit;
    if (typeof root !== 'undefined' && root.OraCanvasFileFormat) {
      return root.OraCanvasFileFormat;
    }
    return null;
  }

  function init(options) {
    options = options || {};
    _state.canvasFileFormat = _resolveCanvasFileFormat(options.canvasFileFormat);
    _state.documentRef =
         options.document
      || (typeof document !== 'undefined' ? document : null);
    _state.windowRef =
         options.window
      || (typeof root !== 'undefined' ? root : null);
    _state.initialized = true;
  }

  // ── validation ─────────────────────────────────────────────────────────────

  function _validateTemplateShape(t) {
    var errs = [];
    if (!_isObj(t)) {
      errs.push({ path: '', message: 'template must be an object' });
      return errs;
    }
    if (!_isStr(t.id))    errs.push({ path: '/id',    message: 'non-empty string required' });
    if (!_isStr(t.title)) errs.push({ path: '/title', message: 'non-empty string required' });
    if (t.description !== undefined && typeof t.description !== 'string') {
      errs.push({ path: '/description', message: 'must be a string when present' });
    }
    if (t.thumbnail !== undefined && t.thumbnail !== null && typeof t.thumbnail !== 'string') {
      errs.push({ path: '/thumbnail', message: 'must be a string or null when present' });
    }
    if (!_isObj(t.canvas_state)) {
      errs.push({ path: '/canvas_state', message: 'object required' });
      return errs;
    }
    // Canvas-state structural check — only when canvas-file-format is wired.
    var cff = _state.canvasFileFormat;
    if (cff && typeof cff.validate === 'function') {
      var v = cff.validate(t.canvas_state);
      if (v && v.valid === false) {
        for (var i = 0; i < (v.errors || []).length; i++) {
          var e = v.errors[i];
          errs.push({ path: '/canvas_state' + (e.path || ''), message: e.message });
        }
      }
    }
    return errs;
  }

  // ── registry surface ───────────────────────────────────────────────────────

  function register(template) {
    if (!_state.initialized) init();   // be tolerant — auto-init with defaults
    var errs = _validateTemplateShape(template);
    if (errs.length > 0) {
      throw _err('invalid_template',
        'composition-template-loader.register: invalid template — '
          + errs.map(function (e) { return e.path + ' ' + e.message; }).join('; '),
        { findings: errs });
    }
    if (_state.templates[template.id]) {
      throw _err('duplicate_template_id',
        "composition-template-loader.register: template id '"
          + template.id + "' is already registered.");
    }
    // Store a defensive clone so later mutation of the input can't alter
    // the registry copy.
    _state.templates[template.id] = _clone(template);
    return template.id;
  }

  function unregister(id) {
    if (!_isStr(id)) return false;
    if (!_state.templates[id]) return false;
    delete _state.templates[id];
    return true;
  }

  function has(id) {
    return _isStr(id)
      && Object.prototype.hasOwnProperty.call(_state.templates, id);
  }

  function get(id) {
    if (!has(id)) return null;
    return _clone(_state.templates[id]);
  }

  function list() {
    var keys = Object.keys(_state.templates).sort();
    var out = [];
    for (var i = 0; i < keys.length; i++) out.push(_clone(_state.templates[keys[i]]));
    return out;
  }

  function clear() {
    _state.templates = Object.create(null);
  }

  // ── pack-loader handoff ────────────────────────────────────────────────────

  // The shape pack-loader.js expects under `options.compositionRegistry`.
  function asPackLoaderRegistry() {
    return {
      register:   function (def) { return register(def); },
      unregister: function (id)  { return unregister(id); },
      has:        has,
      get:        get,
      list:       list
    };
  }

  // Pull templates that pack-loader stored in its fallback registry into
  // this loader. Idempotent: skips ids already registered.
  function importFromPackLoader(packLoaderApi) {
    if (!packLoaderApi || typeof packLoaderApi.listCompositionTemplates !== 'function') {
      throw _err('pack_loader_missing',
        'composition-template-loader.importFromPackLoader: api with '
          + 'listCompositionTemplates() required.');
    }
    var defs = packLoaderApi.listCompositionTemplates() || [];
    var imported = [];
    for (var i = 0; i < defs.length; i++) {
      var d = defs[i];
      if (!_isObj(d) || !_isStr(d.id)) continue;
      if (_state.templates[d.id]) continue;
      try {
        register(d);
        imported.push(d.id);
      } catch (_) { /* skip malformed entries; don't poison the loader */ }
    }
    return imported;
  }

  // ── apply / open ───────────────────────────────────────────────────────────

  // Stamp a fresh modified_at + best-effort title onto the cloned state.
  function _prepareStateForLoad(state, opts) {
    var s = _clone(state);
    if (!_isObj(s.metadata)) s.metadata = {};
    s.metadata.modified_at = (new Date()).toISOString();
    if (opts && _isStr(opts.title)) s.metadata.title = opts.title;
    if (opts && _isStr(opts.conversation_id)) s.metadata.conversation_id = opts.conversation_id;
    return s;
  }

  function _invokePanelLoad(panel, state) {
    if (!panel || !_isObj(panel)) {
      return Promise.reject(_err('invalid_panel',
        'composition-template-loader.applyTemplate: panel must be an object.'));
    }
    var fn = null;
    if (typeof panel.loadCanvasState === 'function')      fn = panel.loadCanvasState;
    else if (typeof panel.applyCanvasState === 'function') fn = panel.applyCanvasState;
    else if (typeof panel.loadFromCanvasState === 'function') fn = panel.loadFromCanvasState;
    else if (typeof panel._loadCanvasStateFallback === 'function') fn = panel._loadCanvasStateFallback;
    if (!fn) {
      return Promise.reject(_err('panel_load_unavailable',
        'composition-template-loader.applyTemplate: panel has no '
          + 'loadCanvasState / applyCanvasState / loadFromCanvasState surface.'));
    }
    try {
      var r = fn.call(panel, state);
      // Accept either Promise or sync return.
      return Promise.resolve(r).then(function () { return state; });
    } catch (e) {
      return Promise.reject(e && e.code ? e : _err('panel_load_failed',
        'composition-template-loader.applyTemplate: panel load threw: '
          + (e && e.message ? e.message : String(e))));
    }
  }

  function applyTemplate(id, panel, opts) {
    if (!_isStr(id)) {
      return Promise.reject(_err('invalid_template_id',
        'composition-template-loader.applyTemplate: id must be a non-empty string.'));
    }
    var entry = _state.templates[id];
    if (!entry) {
      return Promise.reject(_err('template_not_found',
        "composition-template-loader.applyTemplate: no template registered with id '" + id + "'."));
    }
    var state = _prepareStateForLoad(entry.canvas_state, opts);
    return _invokePanelLoad(panel, state);
  }

  function openBlank(panel, opts) {
    var cff = _state.canvasFileFormat;
    if (!cff || typeof cff.newCanvasState !== 'function') {
      return Promise.reject(_err('canvas_file_format_missing',
        'composition-template-loader.openBlank: OraCanvasFileFormat.newCanvasState '
          + 'is not available. Pass options.canvasFileFormat to init().'));
    }
    var blank = cff.newCanvasState(opts || {});
    return _invokePanelLoad(panel, blank);
  }

  // ── New Canvas dialog (scaffold; gallery polish in WP-7.7.5) ───────────────

  function _buildDialogElement(doc, items, resolve) {
    var dialog = doc.createElement('dialog');
    dialog.className = 'ora-new-canvas-dialog';
    dialog.setAttribute('aria-label', 'Choose a starter for your new canvas');

    var heading = doc.createElement('h2');
    heading.textContent = 'New canvas';
    dialog.appendChild(heading);

    var list = doc.createElement('ul');
    list.className = 'ora-new-canvas-list';
    list.setAttribute('role', 'list');

    function addEntry(label, description, value) {
      var li = doc.createElement('li');
      var btn = doc.createElement('button');
      btn.type = 'button';
      btn.className = 'ora-new-canvas-item';
      btn.textContent = label;
      if (_isStr(description)) {
        var sub = doc.createElement('span');
        sub.className = 'ora-new-canvas-item-description';
        sub.textContent = description;
        btn.appendChild(doc.createElement('br'));
        btn.appendChild(sub);
      }
      btn.addEventListener('click', function () {
        try { dialog.close(); } catch (_) { /* jsdom may not support close */ }
        resolve({ template_id: value });
      });
      li.appendChild(btn);
      list.appendChild(li);
    }

    addEntry('Blank canvas', 'Start with an empty canvas.', null);
    for (var i = 0; i < items.length; i++) {
      var t = items[i];
      addEntry(t.title || t.id, t.description || '', t.id);
    }

    dialog.appendChild(list);

    var cancel = doc.createElement('button');
    cancel.type = 'button';
    cancel.className = 'ora-new-canvas-cancel';
    cancel.textContent = 'Cancel';
    cancel.addEventListener('click', function () {
      try { dialog.close(); } catch (_) { /* jsdom */ }
      resolve(null);
    });
    dialog.appendChild(cancel);

    return dialog;
  }

  function showNewCanvasDialog(opts) {
    opts = opts || {};
    var items = list();

    // Headless / test path — caller provides a deterministic answer.
    if (typeof opts.choose === 'function') {
      try {
        var pick = opts.choose(items);
        if (pick === null || pick === undefined) return Promise.resolve(null);
        if (_isStr(pick)) return Promise.resolve({ template_id: pick === 'blank' ? null : pick });
        if (_isObj(pick)) return Promise.resolve({ template_id: pick.template_id || null });
        return Promise.resolve(null);
      } catch (e) {
        return Promise.reject(e);
      }
    }

    var doc = opts.document || _state.documentRef;
    if (!doc || typeof doc.createElement !== 'function') {
      return Promise.reject(_err('no_document',
        'composition-template-loader.showNewCanvasDialog: no document available. '
          + 'Pass opts.document or run in a browser.'));
    }

    return new Promise(function (resolve) {
      var dialog = _buildDialogElement(doc, items, resolve);
      var mount = opts.container
        || (doc.body || (doc.documentElement && doc.documentElement.firstElementChild));
      if (!mount || typeof mount.appendChild !== 'function') {
        resolve(null);
        return;
      }
      mount.appendChild(dialog);
      // Modal display — fall back to plain visibility when showModal absent.
      if (typeof dialog.showModal === 'function') {
        try { dialog.showModal(); } catch (_) { dialog.setAttribute('open', ''); }
      } else {
        dialog.setAttribute('open', '');
      }
    });
  }

  // ── export ─────────────────────────────────────────────────────────────────

  var api = {
    init:                  init,
    register:              register,
    unregister:            unregister,
    has:                   has,
    get:                   get,
    list:                  list,
    clear:                 clear,
    applyTemplate:         applyTemplate,
    openBlank:             openBlank,
    showNewCanvasDialog:   showNewCanvasDialog,
    asPackLoaderRegistry:  asPackLoaderRegistry,
    importFromPackLoader:  importFromPackLoader,
    // Test/introspection seam.
    _state:                _state
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraCompositionTemplateLoader = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
