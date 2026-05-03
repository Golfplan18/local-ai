/* pack-loader.js — WP-7.2.1
 *
 * Phase 7 toolbar-pack loader. Pulls a pack JSON from a disk path or URL,
 * runs it through OraPackValidator (WP-7.0.4), and on success registers
 * each artifact type with the appropriate runtime registry. Tracks an
 * artifact-to-pack mapping so unloadPack(id) removes only that pack's
 * contributions (idempotent; other packs untouched).
 *
 * Public API (exposed on `window.OraPackLoader`)
 *   - init(options)                                → Promise<void>
 *       options.validator           OraPackValidator-shaped object
 *                                   (defaults to global OraPackValidator)
 *       options.toolbarRegistry     OraVisualToolbar-shaped object
 *                                   (defaults to global OraVisualToolbar)
 *       options.macroRegistry       optional — see "stub registration"
 *       options.promptTemplateRegistry  optional — see "stub registration"
 *       options.compositionRegistry optional — see "stub registration"
 *       options.fetch               function(urlOrPath) → Promise<string>
 *                                   (defaults to global fetch when given a URL,
 *                                   or a Node fs read when given a path)
 *       options.fs                  Node fs module (used for disk paths in
 *                                   tests; falls back to require('fs'))
 *
 *   - loadPack(pathOrUrlOrJson)                    → Promise<LoadResult>
 *       LoadResult = {
 *         success:    boolean,
 *         pack_id:    string|null,        // <pack_name>@<pack_version>
 *         errors:     [Finding|Error, ...],
 *         registered: {
 *           toolbars:              [id, ...],
 *           macros:                [id, ...],
 *           prompt_templates:      [id, ...],
 *           composition_templates: [id, ...]
 *         }
 *       }
 *
 *   - unloadPack(packId)                           → UnloadResult
 *       UnloadResult = {
 *         success:    boolean,
 *         pack_id:    string,
 *         errors:     [Error, ...],
 *         removed: {
 *           toolbars:              [id, ...],
 *           macros:                [id, ...],
 *           prompt_templates:      [id, ...],
 *           composition_templates: [id, ...]
 *         }
 *       }
 *
 *   - listInstalled()                              → [InstalledPack, ...]
 *       InstalledPack = {
 *         pack_id, pack_name, pack_version, ora_compatibility,
 *         author, description, source,
 *         registered: {...}            // same shape as loadPack
 *       }
 *
 *   - has(packId)                                  → boolean
 *   - getInstalled(packId)                         → InstalledPack|null
 *   - clear()                                      → resets loader state
 *                                                    (does NOT unregister
 *                                                     artifacts — call
 *                                                     unloadPack for each
 *                                                     pack instead)
 *
 * Pack identity
 * -------------
 * `pack_id = "<pack_name>@<pack_version>"` — the same name+version installed
 * twice is rejected by loadPack with a 'pack_already_installed' error. Two
 * packs with the same name but different versions live side-by-side; the
 * caller decides which to unload.
 *
 * Artifact-to-pack mapping
 * ------------------------
 * For every registered artifact (toolbar, macro, prompt template,
 * composition template), the loader records (artifact_kind, artifact_id,
 * pack_id). Unloading walks that record and removes only that pack's
 * artifacts. Concretely:
 *
 *   _artifactOwners = {
 *     toolbars:              { toolbarId: packId },
 *     macros:                { macroId: packId },
 *     prompt_templates:      { templateId: packId },
 *     composition_templates: { compId: packId }
 *   }
 *
 * If pack A registers toolbar "foo" and pack B then loads, pack B cannot
 * silently shadow "foo" — duplicate ids across packs are rejected at load
 * time with a 'duplicate_artifact_id' error.
 *
 * Stub registration for §7.2.2 / §7.2.3 / §7.2.4
 * ----------------------------------------------
 * The macro runtime (§7.2.2), prompt-template runtime (§7.2.3), and
 * composition-template runtime / New Canvas dialog (§7.7.5 / §7.2.4) are
 * not in flight at the time of this WP. To stay declarative-only and avoid
 * blocking on those WPs, this loader stores the macro, prompt-template,
 * and composition-template definitions in its own state when the matching
 * registry isn't supplied. Each definition is exposed via:
 *
 *   listMacros()                  → [macroDef, ...]
 *   getMacro(macroId)             → macroDef|null
 *   listPromptTemplates()         → [tplDef, ...]
 *   getPromptTemplate(id)         → tplDef|null
 *   listCompositionTemplates()    → [compDef, ...]
 *   getCompositionTemplate(id)    → compDef|null
 *
 * Integration point for §7.2.2 — the macro runtime should call
 * `OraPackLoader.listMacros()` (or pass itself as `options.macroRegistry`
 * to `init()`) to consume the loader's stored macros. The expected shape
 * for `options.macroRegistry` is:
 *
 *   {
 *     register(macroDef)                 → registered_id  (or throws)
 *     unregister(macroId)                → boolean
 *     // optional:
 *     has?(macroId), get?(macroId), list?()
 *   }
 *
 * §7.2.3 (prompt template runtime) — same contract under
 * `options.promptTemplateRegistry`. §7.2.4 / §7.7.5 (composition template /
 * New Canvas dialog) — same contract under `options.compositionRegistry`.
 *
 * When a registry IS supplied, loadPack calls registry.register(def) for
 * each artifact and the loader does not retain the def — the registry
 * owns it. unloadPack then calls registry.unregister(id). The internal
 * fallback storage is used only when the corresponding registry is null.
 *
 * Security & §11.15 declarative-only
 * ----------------------------------
 * This loader inherits the validator's narrow surface — the only data
 * touched here is what the schema permits. There is no eval, no Function
 * constructor, no script injection, no fetch of pack-referenced URLs
 * (URLs only appear in `author.url`, which we treat as a label, never
 * follow). Inline SVGs stay strings until a renderer mounts them.
 *
 * Test criterion (§13.2)
 *   "Load a sample pack; verify all four artifact types register; unload;
 *    verify only that pack's artifacts removed."
 * Tests live at server/static/tests/test-pack-loader.js (Node, jsdom-free).
 */

(function (root) {
  'use strict';

  // ---- helpers -------------------------------------------------------------

  function _isObj(x) {
    return x !== null && typeof x === 'object' && !Array.isArray(x);
  }

  function _isStr(x) {
    return typeof x === 'string' && x.length > 0;
  }

  function _err(code, message, extra) {
    var e = { code: code, message: message };
    if (extra) {
      var keys = Object.keys(extra);
      for (var i = 0; i < keys.length; i++) e[keys[i]] = extra[keys[i]];
    }
    return e;
  }

  function _packIdOf(pack) {
    return String(pack.pack_name) + '@' + String(pack.pack_version);
  }

  // Looks like a URL ("http://...", "https://...", "file://..."). Anything
  // else we treat as a disk path.
  function _looksLikeUrl(s) {
    return /^(https?|file):\/\//i.test(s);
  }

  // Treat an input as a JSON string when it starts (after whitespace) with
  // "{" — disk paths and URLs never do.
  function _looksLikeJsonString(s) {
    return /^\s*\{/.test(s);
  }

  // ---- state ---------------------------------------------------------------

  var _state = {
    initialized: false,
    validator: null,
    toolbarRegistry: null,
    macroRegistry: null,
    promptTemplateRegistry: null,
    compositionRegistry: null,
    fetchFn: null,
    fsMod: null,

    // Installed packs keyed by pack_id ("<name>@<version>").
    installed: Object.create(null),

    // Artifact-to-pack mapping. Each entry is { artifactId: packId }.
    artifactOwners: {
      toolbars:              Object.create(null),
      macros:                Object.create(null),
      prompt_templates:      Object.create(null),
      composition_templates: Object.create(null)
    },

    // Fallback storage when no external registry is provided.
    fallback: {
      macros:                Object.create(null),
      prompt_templates:      Object.create(null),
      composition_templates: Object.create(null)
    }
  };

  // ---- init ----------------------------------------------------------------

  function init(options) {
    options = options || {};
    _state.validator =
         options.validator
      || (typeof root !== 'undefined' ? root.OraPackValidator : null);
    _state.toolbarRegistry =
         options.toolbarRegistry
      || (typeof root !== 'undefined' ? root.OraVisualToolbar : null);
    _state.macroRegistry           = options.macroRegistry           || null;
    _state.promptTemplateRegistry  = options.promptTemplateRegistry  || null;
    _state.compositionRegistry     = options.compositionRegistry     || null;
    _state.fetchFn                 = options.fetch                   || null;
    _state.fsMod                   = options.fs                      || null;

    if (!_state.fsMod && typeof require === 'function') {
      try { _state.fsMod = require('fs'); } catch (_) { /* browser */ }
    }

    _state.initialized = true;
    return Promise.resolve();
  }

  // ---- input loaders -------------------------------------------------------

  // Resolves the input (disk path / URL / JSON string / object) to a parsed
  // pack object plus the source-string we'll record on the InstalledPack.
  function _resolveInput(input) {
    // 1. Object — already parsed.
    if (_isObj(input)) {
      return Promise.resolve({ pack: input, source: '(object)' });
    }
    if (typeof input !== 'string') {
      return Promise.reject(_err(
        'invalid_input',
        'loadPack: input must be a string (path/URL/JSON) or a parsed pack object; got ' + typeof input
      ));
    }

    // 2. JSON string.
    if (_looksLikeJsonString(input)) {
      try {
        return Promise.resolve({ pack: JSON.parse(input), source: '(inline-json)' });
      } catch (e) {
        return Promise.reject(_err(
          'invalid_json',
          'loadPack: input looked like JSON but failed to parse: ' + (e && e.message)
        ));
      }
    }

    // 3. URL.
    if (_looksLikeUrl(input)) {
      var fetchFn = _state.fetchFn
        || (typeof root !== 'undefined' && typeof root.fetch === 'function'
            ? function (u) { return root.fetch(u).then(function (r) {
                if (!r.ok) throw _err('fetch_failed',
                  'loadPack: fetch failed (' + r.status + ' ' + r.statusText + ') for ' + u);
                return r.text();
              }); }
            : null);
      if (!fetchFn) {
        return Promise.reject(_err(
          'fetch_unavailable',
          'loadPack: URL given but no fetch function configured. Pass options.fetch or run in a browser.'
        ));
      }
      return Promise.resolve(fetchFn(input)).then(function (text) {
        try {
          return { pack: JSON.parse(text), source: input };
        } catch (e) {
          throw _err('invalid_json',
            'loadPack: response from ' + input + ' did not parse as JSON: ' + (e && e.message));
        }
      });
    }

    // 4. Disk path.
    if (!_state.fsMod || typeof _state.fsMod.readFileSync !== 'function') {
      return Promise.reject(_err(
        'fs_unavailable',
        'loadPack: disk path given but no fs module available. Pass options.fs or run in Node.'
      ));
    }
    try {
      var text = _state.fsMod.readFileSync(input, 'utf8');
      return Promise.resolve({ pack: JSON.parse(text), source: input });
    } catch (e) {
      return Promise.reject(_err(
        e && e.code === 'ENOENT' ? 'file_not_found' : 'fs_error',
        'loadPack: could not read pack from ' + input + ': ' + (e && e.message)
      ));
    }
  }

  // ---- registration helpers ------------------------------------------------

  // Registers one toolbar via the toolbar registry. Throws on failure.
  function _registerToolbar(def, packId) {
    if (!_state.toolbarRegistry || typeof _state.toolbarRegistry.register !== 'function') {
      throw _err('toolbar_registry_missing',
        'pack-loader: OraVisualToolbar registry is required to register toolbars; pass options.toolbarRegistry to init().');
    }
    _state.toolbarRegistry.register(def);
    _state.artifactOwners.toolbars[def.id] = packId;
  }

  function _unregisterToolbar(toolbarId) {
    var reg = _state.toolbarRegistry;
    if (!reg) return;
    // OraVisualToolbar exposes clear() for full reset; for targeted removal
    // we mutate the registry through its public seam where possible. The
    // current visual-toolbar.js exposes register/get/has/list/clear/render
    // but no remove(). Re-clearing all and re-registering survivors is the
    // declarative-only fallback that keeps the registry consistent.
    if (typeof reg.remove === 'function') {
      reg.remove(toolbarId);
      return;
    }
    if (typeof reg.list !== 'function' || typeof reg.get !== 'function'
        || typeof reg.clear !== 'function' || typeof reg.register !== 'function') {
      // Can't safely target one entry. Surface as a soft failure — the
      // toolbar definition stays orphaned in the registry but the
      // artifactOwner record is dropped, so a re-load won't double-register.
      return;
    }
    var ids = reg.list();
    var survivors = [];
    for (var i = 0; i < ids.length; i++) {
      if (ids[i] === toolbarId) continue;
      var def = reg.get(ids[i]);
      if (def) survivors.push(def);
    }
    reg.clear();
    for (var j = 0; j < survivors.length; j++) {
      try { reg.register(survivors[j]); } catch (_) { /* best-effort */ }
    }
  }

  // Generic "register via external registry OR fall back to local store".
  function _registerOrStore(kind, def, registry, fallbackStore, packId) {
    if (registry && typeof registry.register === 'function') {
      registry.register(def);
    } else {
      fallbackStore[def.id] = def;
    }
    _state.artifactOwners[kind][def.id] = packId;
  }

  function _unregisterOrForget(kind, artifactId, registry, fallbackStore) {
    if (registry && typeof registry.unregister === 'function') {
      try { registry.unregister(artifactId); } catch (_) { /* best-effort */ }
    } else {
      delete fallbackStore[artifactId];
    }
  }

  // ---- precheck: duplicate ids across packs --------------------------------

  function _precheckIdCollisions(pack, packId) {
    var clashes = [];
    function check(kind, defs) {
      if (!Array.isArray(defs)) return;
      for (var i = 0; i < defs.length; i++) {
        var d = defs[i];
        if (!d || !_isStr(d.id)) continue;
        var existingOwner = _state.artifactOwners[kind][d.id];
        if (existingOwner && existingOwner !== packId) {
          clashes.push({ kind: kind, id: d.id, owner: existingOwner });
        }
      }
    }
    check('toolbars',              pack.toolbars);
    check('macros',                pack.macros);
    check('prompt_templates',      pack.prompt_templates);
    check('composition_templates', pack.composition_templates);
    return clashes;
  }

  // ---- loadPack ------------------------------------------------------------

  function loadPack(input) {
    if (!_state.initialized) {
      return Promise.reject(_err(
        'loader_not_initialized',
        'OraPackLoader.init() must be called before loadPack().'
      ));
    }
    if (!_state.validator || typeof _state.validator.validate !== 'function') {
      return Promise.reject(_err(
        'validator_missing',
        'OraPackLoader: validator is not configured. Pass options.validator to init().'
      ));
    }

    return _resolveInput(input).then(function (resolved) {
      var pack = resolved.pack;
      var source = resolved.source;
      var result = {
        success: false,
        pack_id: null,
        errors: [],
        registered: {
          toolbars:              [],
          macros:                [],
          prompt_templates:      [],
          composition_templates: []
        }
      };

      // ---- 1. Validate against schema + semantic layers ------------------
      var v;
      try {
        v = _state.validator.validate(pack);
      } catch (e) {
        result.errors.push(_err('validator_threw',
          'OraPackValidator.validate threw: ' + (e && e.message)));
        return result;
      }
      if (!v.valid) {
        result.errors = (v.findings || []).slice();
        return result;
      }

      // ---- 2. Compute pack_id; reject duplicate installs -----------------
      if (!_isStr(pack.pack_name) || !_isStr(pack.pack_version)) {
        result.errors.push(_err('invalid_pack_identity',
          'pack must declare pack_name and pack_version (validator should have caught this).'));
        return result;
      }
      var packId = _packIdOf(pack);
      result.pack_id = packId;

      if (_state.installed[packId]) {
        result.errors.push(_err('pack_already_installed',
          "pack '" + packId + "' is already installed; unload it first to reinstall."));
        return result;
      }

      // ---- 3. Detect cross-pack id collisions ----------------------------
      var clashes = _precheckIdCollisions(pack, packId);
      if (clashes.length > 0) {
        for (var c = 0; c < clashes.length; c++) {
          var cl = clashes[c];
          result.errors.push(_err('duplicate_artifact_id',
            "artifact id '" + cl.id + "' (" + cl.kind + ") is already registered by pack '"
              + cl.owner + "'; rename or unload the other pack first.",
            { kind: cl.kind, id: cl.id, conflicting_pack: cl.owner }));
        }
        return result;
      }

      // ---- 4. Register each artifact type --------------------------------
      // Per-artifact try/catch so a single bad artifact rolls back cleanly
      // and leaves no half-installed pack behind.
      var rollback = [];
      function trackRollback(fn) { rollback.push(fn); }
      function doRollback() {
        for (var r = rollback.length - 1; r >= 0; r--) {
          try { rollback[r](); } catch (_) { /* best-effort */ }
        }
      }

      try {
        // Toolbars.
        var toolbars = Array.isArray(pack.toolbars) ? pack.toolbars : [];
        for (var i = 0; i < toolbars.length; i++) {
          var tb = toolbars[i];
          _registerToolbar(tb, packId);
          (function (id) {
            trackRollback(function () {
              _unregisterToolbar(id);
              delete _state.artifactOwners.toolbars[id];
            });
          })(tb.id);
          result.registered.toolbars.push(tb.id);
        }

        // Macros (stub-registered if no registry).
        var macros = Array.isArray(pack.macros) ? pack.macros : [];
        for (var m = 0; m < macros.length; m++) {
          var mc = macros[m];
          _registerOrStore('macros', mc,
            _state.macroRegistry, _state.fallback.macros, packId);
          (function (id) {
            trackRollback(function () {
              _unregisterOrForget('macros', id,
                _state.macroRegistry, _state.fallback.macros);
              delete _state.artifactOwners.macros[id];
            });
          })(mc.id);
          result.registered.macros.push(mc.id);
        }

        // Prompt templates.
        var pts = Array.isArray(pack.prompt_templates) ? pack.prompt_templates : [];
        for (var p = 0; p < pts.length; p++) {
          var pt = pts[p];
          _registerOrStore('prompt_templates', pt,
            _state.promptTemplateRegistry, _state.fallback.prompt_templates, packId);
          (function (id) {
            trackRollback(function () {
              _unregisterOrForget('prompt_templates', id,
                _state.promptTemplateRegistry, _state.fallback.prompt_templates);
              delete _state.artifactOwners.prompt_templates[id];
            });
          })(pt.id);
          result.registered.prompt_templates.push(pt.id);
        }

        // Composition templates.
        var cts = Array.isArray(pack.composition_templates) ? pack.composition_templates : [];
        for (var k = 0; k < cts.length; k++) {
          var ct = cts[k];
          _registerOrStore('composition_templates', ct,
            _state.compositionRegistry, _state.fallback.composition_templates, packId);
          (function (id) {
            trackRollback(function () {
              _unregisterOrForget('composition_templates', id,
                _state.compositionRegistry, _state.fallback.composition_templates);
              delete _state.artifactOwners.composition_templates[id];
            });
          })(ct.id);
          result.registered.composition_templates.push(ct.id);
        }
      } catch (e) {
        doRollback();
        result.registered = {
          toolbars: [], macros: [], prompt_templates: [], composition_templates: []
        };
        var asErr = (e && e.code) ? e : _err('registration_failed',
          'pack-loader: artifact registration failed: ' + (e && e.message));
        result.errors.push(asErr);
        return result;
      }

      // ---- 5. Record installation -----------------------------------------
      _state.installed[packId] = {
        pack_id:           packId,
        pack_name:         pack.pack_name,
        pack_version:      pack.pack_version,
        ora_compatibility: pack.ora_compatibility,
        author:            pack.author,
        description:       pack.description || '',
        source:            source,
        registered: {
          toolbars:              result.registered.toolbars.slice(),
          macros:                result.registered.macros.slice(),
          prompt_templates:      result.registered.prompt_templates.slice(),
          composition_templates: result.registered.composition_templates.slice()
        }
      };

      result.success = true;
      return result;
    }, function (err) {
      // _resolveInput rejected.
      return {
        success: false,
        pack_id: null,
        errors: [err && err.code ? err : _err('load_failed',
          'loadPack: ' + (err && err.message ? err.message : String(err)))],
        registered: {
          toolbars: [], macros: [], prompt_templates: [], composition_templates: []
        }
      };
    });
  }

  // ---- unloadPack ----------------------------------------------------------

  function unloadPack(packId) {
    var result = {
      success: false,
      pack_id: packId,
      errors: [],
      removed: {
        toolbars:              [],
        macros:                [],
        prompt_templates:      [],
        composition_templates: []
      }
    };
    if (!_state.initialized) {
      result.errors.push(_err('loader_not_initialized',
        'OraPackLoader.init() must be called before unloadPack().'));
      return result;
    }
    var entry = _state.installed[packId];
    if (!entry) {
      result.errors.push(_err('pack_not_installed',
        "pack '" + packId + "' is not installed; nothing to unload."));
      return result;
    }

    // Toolbars.
    for (var i = 0; i < entry.registered.toolbars.length; i++) {
      var tbId = entry.registered.toolbars[i];
      // Only remove if we still own it (defense against external mutation).
      if (_state.artifactOwners.toolbars[tbId] === packId) {
        try {
          _unregisterToolbar(tbId);
          delete _state.artifactOwners.toolbars[tbId];
          result.removed.toolbars.push(tbId);
        } catch (e) {
          result.errors.push(_err('toolbar_unregister_failed',
            "could not unregister toolbar '" + tbId + "': " + (e && e.message)));
        }
      }
    }

    // Macros / prompt_templates / composition_templates — generic path.
    var kinds = [
      ['macros',                _state.macroRegistry,           _state.fallback.macros],
      ['prompt_templates',      _state.promptTemplateRegistry,  _state.fallback.prompt_templates],
      ['composition_templates', _state.compositionRegistry,     _state.fallback.composition_templates]
    ];
    for (var k = 0; k < kinds.length; k++) {
      var kind = kinds[k][0];
      var reg = kinds[k][1];
      var fb = kinds[k][2];
      var ids = entry.registered[kind] || [];
      for (var j = 0; j < ids.length; j++) {
        var id = ids[j];
        if (_state.artifactOwners[kind][id] === packId) {
          try {
            _unregisterOrForget(kind, id, reg, fb);
            delete _state.artifactOwners[kind][id];
            result.removed[kind].push(id);
          } catch (e) {
            result.errors.push(_err(kind + '_unregister_failed',
              "could not unregister " + kind + " '" + id + "': " + (e && e.message)));
          }
        }
      }
    }

    delete _state.installed[packId];
    result.success = result.errors.length === 0;
    return result;
  }

  // ---- introspection -------------------------------------------------------

  function listInstalled() {
    var keys = Object.keys(_state.installed).sort();
    var out = [];
    for (var i = 0; i < keys.length; i++) {
      // Defensive shallow-copy so callers can't mutate loader state.
      var e = _state.installed[keys[i]];
      out.push({
        pack_id:           e.pack_id,
        pack_name:         e.pack_name,
        pack_version:      e.pack_version,
        ora_compatibility: e.ora_compatibility,
        author:            e.author,
        description:       e.description,
        source:            e.source,
        registered: {
          toolbars:              e.registered.toolbars.slice(),
          macros:                e.registered.macros.slice(),
          prompt_templates:      e.registered.prompt_templates.slice(),
          composition_templates: e.registered.composition_templates.slice()
        }
      });
    }
    return out;
  }

  function has(packId) {
    return Object.prototype.hasOwnProperty.call(_state.installed, packId);
  }

  function getInstalled(packId) {
    if (!has(packId)) return null;
    var e = _state.installed[packId];
    return {
      pack_id:           e.pack_id,
      pack_name:         e.pack_name,
      pack_version:      e.pack_version,
      ora_compatibility: e.ora_compatibility,
      author:            e.author,
      description:       e.description,
      source:            e.source,
      registered: {
        toolbars:              e.registered.toolbars.slice(),
        macros:                e.registered.macros.slice(),
        prompt_templates:      e.registered.prompt_templates.slice(),
        composition_templates: e.registered.composition_templates.slice()
      }
    };
  }

  function clear() {
    _state.installed = Object.create(null);
    _state.artifactOwners = {
      toolbars:              Object.create(null),
      macros:                Object.create(null),
      prompt_templates:      Object.create(null),
      composition_templates: Object.create(null)
    };
    _state.fallback = {
      macros:                Object.create(null),
      prompt_templates:      Object.create(null),
      composition_templates: Object.create(null)
    };
  }

  // ---- §7.2.2 / §7.2.3 / §7.2.4 integration seams --------------------------

  function _listFallback(store) {
    var out = [];
    var keys = Object.keys(store);
    for (var i = 0; i < keys.length; i++) out.push(store[keys[i]]);
    return out;
  }

  function listMacros() {
    return _listFallback(_state.fallback.macros);
  }
  function getMacro(id) {
    return _state.fallback.macros[id] || null;
  }
  function listPromptTemplates() {
    return _listFallback(_state.fallback.prompt_templates);
  }
  function getPromptTemplate(id) {
    return _state.fallback.prompt_templates[id] || null;
  }
  function listCompositionTemplates() {
    return _listFallback(_state.fallback.composition_templates);
  }
  function getCompositionTemplate(id) {
    return _state.fallback.composition_templates[id] || null;
  }

  // ---- export --------------------------------------------------------------

  var api = {
    init:                     init,
    loadPack:                 loadPack,
    unloadPack:               unloadPack,
    listInstalled:            listInstalled,
    has:                      has,
    getInstalled:             getInstalled,
    clear:                    clear,
    // Stub-registry accessors for §7.2.2/3/4 integration.
    listMacros:               listMacros,
    getMacro:                 getMacro,
    listPromptTemplates:      listPromptTemplates,
    getPromptTemplate:        getPromptTemplate,
    listCompositionTemplates: listCompositionTemplates,
    getCompositionTemplate:   getCompositionTemplate,
    // Exposed for tests / introspection only.
    _state:                   _state
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraPackLoader = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
