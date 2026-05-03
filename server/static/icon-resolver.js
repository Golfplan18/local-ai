/* icon-resolver.js — WP-7.0.3
 *
 * Resolves an icon reference to an SVG string. Three input shapes:
 *   1. A Lucide icon name (e.g. "image", "crop", "rotate-cw") → returns the
 *      vendored SVG string.
 *   2. An inline SVG string starting with "<svg" → validated and returned.
 *   3. An unknown name or invalid SVG → clearly-marked fallback glyph
 *      (a question-mark inside a dashed square; no hard error).
 *
 * Loading model
 *   The browser side calls `OraIconResolver.init()` once at boot. That fetches
 *   the runtime icon set (tree-shaken output if present, full vendored set
 *   otherwise) and the canonical name list, caches them in-memory, and
 *   resolves synchronously thereafter.
 *
 * Public API (exposed on `window.OraIconResolver`)
 *   - init({ iconSetUrl?, namesUrl?, runtimeBaseUrl? })  → Promise<void>
 *   - resolve(nameOrSvg, options?)                       → string (SVG)
 *   - isValidName(name)                                  → boolean
 *   - listNames()                                        → string[]   (canonical names from names.json)
 *   - listLoadedNames()                                  → string[]   (names actually loaded into memory)
 *   - getVersion()                                       → string     (Lucide version)
 *   - clearCache()                                       → void
 *
 * Tree-shake awareness
 *   When `runtime/icon-set.json` exists (produced by scripts/lucide-tree-shake.js),
 *   only the icons in that set are loaded by default — keeps the runtime payload
 *   small. When it's absent, the resolver falls back to lazy per-icon fetching
 *   from the full vendored `vendor/lucide/icons/` directory.
 *
 * Environment
 *   Works in the browser (uses fetch + URL relative to the script tag's src
 *   when possible, or a configured base URL). Also works under Node + jsdom
 *   for the test harness — when the harness pre-populates `_state.iconSet`
 *   via init({ iconSet, names, version }), no fetch happens.
 */

(function (root) {
  'use strict';

  var DEFAULT_FALLBACK_GLYPH = [
    '<svg class="lucide lucide-fallback ora-icon-fallback"',
    '     xmlns="http://www.w3.org/2000/svg"',
    '     width="24" height="24" viewBox="0 0 24 24"',
    '     fill="none" stroke="currentColor" stroke-width="2"',
    '     stroke-linecap="round" stroke-linejoin="round"',
    '     data-ora-icon-fallback="true"',
    '     aria-label="Unknown icon">',
    '  <rect width="18" height="18" x="3" y="3" rx="2" ry="2" stroke-dasharray="3 3" />',
    '  <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />',
    '  <line x1="12" y1="17" x2="12.01" y2="17" />',
    '</svg>'
  ].join('\n');

  // ---- internal state ------------------------------------------------------

  var _state = {
    initialized: false,
    initPromise: null,
    iconSet: null,            // { name: svgString }
    canonicalNames: null,     // Set of all valid Lucide names (from names.json)
    nameList: null,           // sorted array (cached for listNames())
    version: null,            // string from names.json
    runtimeBaseUrl: null,     // e.g. "/static/vendor/lucide/icons" — for lazy fallback
    fetchImpl: null,          // overridable fetch (defaults to globalThis.fetch)
    isFallbackMode: false     // true when running without a tree-shaken icon set
  };

  // ---- helpers -------------------------------------------------------------

  function _defaultFetch() {
    if (typeof root !== 'undefined' && typeof root.fetch === 'function') {
      return root.fetch.bind(root);
    }
    if (typeof fetch === 'function') return fetch;
    return null;
  }

  function _isInlineSvg(value) {
    if (typeof value !== 'string') return false;
    var trimmed = value.trim();
    return trimmed.length >= 4 && trimmed.slice(0, 4).toLowerCase() === '<svg';
  }

  function _looksLikeIconName(value) {
    // Lucide icon names: lowercase letters, digits, hyphens. e.g. "alarm-clock",
    // "a-arrow-down", "1-circle". Anything else is rejected.
    return typeof value === 'string'
      && /^[a-z0-9][a-z0-9-]*$/.test(value);
  }

  function _validateInlineSvg(svg) {
    // Lightweight validation: must contain a <svg ...> opener, a matching </svg>
    // close, and no obvious script tag. We do NOT execute or DOM-parse — purely
    // a string check, mirroring how the toolbar pack validator (WP-7.0.4) will
    // surface obvious errors before render time. Anything more sophisticated
    // belongs in pack-validator.js per §11.15 declarative-only security.
    var t = svg.trim();
    if (!_isInlineSvg(t)) return { valid: false, reason: 'not-an-svg-element' };
    if (!/<\/svg>\s*$/i.test(t)) return { valid: false, reason: 'missing-closing-tag' };
    if (/<script[\s>]/i.test(t)) return { valid: false, reason: 'contains-script-tag' };
    if (/\son[a-z]+\s*=/i.test(t)) return { valid: false, reason: 'contains-event-handler' };
    return { valid: true };
  }

  function _markedFallback(reason, originalName) {
    // Decorate the fallback so callers can detect it visually + programmatically.
    var label = (typeof originalName === 'string' && originalName)
      ? ('Unknown icon: ' + originalName.replace(/[<>"]/g, ''))
      : 'Unknown icon';
    return DEFAULT_FALLBACK_GLYPH
      .replace(/aria-label="[^"]*"/, 'aria-label="' + label + '"')
      .replace(/data-ora-icon-fallback="true"/,
               'data-ora-icon-fallback="true" data-ora-icon-fallback-reason="'
               + (reason || 'unknown') + '"');
  }

  function _resolveBaseUrl(explicit) {
    if (explicit) return explicit.replace(/\/+$/, '');
    if (typeof document !== 'undefined') {
      var scripts = document.getElementsByTagName('script');
      for (var i = 0; i < scripts.length; i++) {
        var src = scripts[i].getAttribute('src') || '';
        if (src.indexOf('icon-resolver.js') !== -1) {
          // Sibling of static/icon-resolver.js → static/vendor/lucide/icons
          var dir = src.replace(/icon-resolver\.js.*$/, '');
          return dir.replace(/\/+$/, '') + '/vendor/lucide/icons';
        }
      }
    }
    return '/static/vendor/lucide/icons';
  }

  function _runtimeSetUrl(explicit) {
    if (explicit) return explicit;
    if (typeof document !== 'undefined') {
      var scripts = document.getElementsByTagName('script');
      for (var i = 0; i < scripts.length; i++) {
        var src = scripts[i].getAttribute('src') || '';
        if (src.indexOf('icon-resolver.js') !== -1) {
          var dir = src.replace(/icon-resolver\.js.*$/, '');
          return dir.replace(/\/+$/, '') + '/runtime/icon-set.json';
        }
      }
    }
    return '/static/runtime/icon-set.json';
  }

  function _namesUrl(explicit) {
    if (explicit) return explicit;
    if (typeof document !== 'undefined') {
      var scripts = document.getElementsByTagName('script');
      for (var i = 0; i < scripts.length; i++) {
        var src = scripts[i].getAttribute('src') || '';
        if (src.indexOf('icon-resolver.js') !== -1) {
          var dir = src.replace(/icon-resolver\.js.*$/, '');
          return dir.replace(/\/+$/, '') + '/vendor/lucide/names.json';
        }
      }
    }
    return '/static/vendor/lucide/names.json';
  }

  // ---- init ----------------------------------------------------------------

  function init(options) {
    options = options || {};

    // Synchronous bootstrap path — used by the test harness to inject a
    // pre-built icon set without going through fetch.
    if (options.iconSet || options.names) {
      _state.iconSet = options.iconSet || {};
      _state.canonicalNames = new Set(options.names || Object.keys(_state.iconSet));
      _state.nameList = Array.from(_state.canonicalNames).sort();
      _state.version = options.version || 'unknown';
      _state.runtimeBaseUrl = options.runtimeBaseUrl || null;
      _state.fetchImpl = options.fetchImpl || _defaultFetch();
      _state.isFallbackMode = !!options.isFallbackMode;
      _state.initialized = true;
      _state.initPromise = Promise.resolve();
      return _state.initPromise;
    }

    if (_state.initPromise) return _state.initPromise;

    var fetchImpl = options.fetchImpl || _defaultFetch();
    _state.fetchImpl = fetchImpl;

    var runtimeUrl = _runtimeSetUrl(options.iconSetUrl);
    var namesUrl = _namesUrl(options.namesUrl);
    _state.runtimeBaseUrl = _resolveBaseUrl(options.runtimeBaseUrl);

    if (!fetchImpl) {
      // No fetch available and no pre-injected set — degrade gracefully.
      _state.iconSet = {};
      _state.canonicalNames = new Set();
      _state.nameList = [];
      _state.version = 'unknown';
      _state.isFallbackMode = true;
      _state.initialized = true;
      _state.initPromise = Promise.resolve();
      return _state.initPromise;
    }

    _state.initPromise = Promise.all([
      fetchImpl(namesUrl).then(function (r) {
        if (!r || !r.ok) throw new Error('names.json fetch failed');
        return r.json();
      }).catch(function () { return null; }),
      fetchImpl(runtimeUrl).then(function (r) {
        if (!r || !r.ok) throw new Error('runtime icon-set.json absent');
        return r.json();
      }).catch(function () { return null; })
    ]).then(function (results) {
      var namesPayload = results[0] || { version: 'unknown', names: [] };
      var runtimePayload = results[1];

      _state.canonicalNames = new Set(namesPayload.names || []);
      _state.nameList = (namesPayload.names || []).slice().sort();
      _state.version = namesPayload.version || 'unknown';

      if (runtimePayload && runtimePayload.icons) {
        _state.iconSet = runtimePayload.icons;
        _state.isFallbackMode = false;
      } else {
        _state.iconSet = {};
        _state.isFallbackMode = true;
      }
      _state.initialized = true;
    });

    return _state.initPromise;
  }

  // ---- resolve -------------------------------------------------------------

  function resolve(nameOrSvg, options) {
    options = options || {};

    // Handle inline SVG first — same shape as toolbar pack icon entries that
    // supply a custom glyph.
    if (_isInlineSvg(nameOrSvg)) {
      var v = _validateInlineSvg(nameOrSvg);
      if (v.valid) return nameOrSvg;
      return _markedFallback('invalid-inline-svg-' + v.reason, '<inline-svg>');
    }

    // Empty / non-string / structurally invalid name → fallback.
    if (!nameOrSvg || typeof nameOrSvg !== 'string') {
      return _markedFallback('not-a-string', String(nameOrSvg));
    }
    var name = nameOrSvg.trim();
    if (!_looksLikeIconName(name)) {
      return _markedFallback('malformed-name', name);
    }

    // Unknown name (per canonical names list) → fallback.
    if (_state.canonicalNames && _state.canonicalNames.size > 0
        && !_state.canonicalNames.has(name)) {
      return _markedFallback('unknown-name', name);
    }

    // Loaded into the runtime icon set → return it.
    if (_state.iconSet && Object.prototype.hasOwnProperty.call(_state.iconSet, name)) {
      return _state.iconSet[name];
    }

    // Synchronous lookup miss but name is canonically valid. The browser path
    // can't issue a synchronous fetch, so we fall back. Callers that want
    // lazy-load behavior should call ensureLoaded(name) ahead of resolve().
    if (options.allowFallback === false) {
      return _markedFallback('not-loaded', name);
    }
    return _markedFallback('not-loaded', name);
  }

  // Lazy-load a single icon by name (returns Promise<svgString>). Useful for
  // plugins that ship custom toolbar packs at runtime referencing icons not in
  // the tree-shake output.
  function ensureLoaded(name) {
    if (!_looksLikeIconName(name)) {
      return Promise.resolve(_markedFallback('malformed-name', name));
    }
    if (_state.canonicalNames && !_state.canonicalNames.has(name)) {
      return Promise.resolve(_markedFallback('unknown-name', name));
    }
    if (_state.iconSet && Object.prototype.hasOwnProperty.call(_state.iconSet, name)) {
      return Promise.resolve(_state.iconSet[name]);
    }
    if (!_state.fetchImpl || !_state.runtimeBaseUrl) {
      return Promise.resolve(_markedFallback('no-fetch', name));
    }
    return _state.fetchImpl(_state.runtimeBaseUrl + '/' + name + '.svg')
      .then(function (r) {
        if (!r || !r.ok) throw new Error('fetch failed');
        return r.text();
      })
      .then(function (svg) {
        _state.iconSet[name] = svg;
        return svg;
      })
      .catch(function () {
        return _markedFallback('fetch-failed', name);
      });
  }

  // ---- introspection -------------------------------------------------------

  function isValidName(name) {
    if (!_looksLikeIconName(name)) return false;
    if (!_state.canonicalNames) return false;
    return _state.canonicalNames.has(name);
  }

  function listNames() {
    return _state.nameList ? _state.nameList.slice() : [];
  }

  function listLoadedNames() {
    return _state.iconSet ? Object.keys(_state.iconSet).sort() : [];
  }

  function getVersion() {
    return _state.version || 'unknown';
  }

  function clearCache() {
    _state.initialized = false;
    _state.initPromise = null;
    _state.iconSet = null;
    _state.canonicalNames = null;
    _state.nameList = null;
    _state.version = null;
    _state.runtimeBaseUrl = null;
    _state.isFallbackMode = false;
  }

  // ---- export --------------------------------------------------------------

  var api = {
    init: init,
    resolve: resolve,
    ensureLoaded: ensureLoaded,
    isValidName: isValidName,
    listNames: listNames,
    listLoadedNames: listLoadedNames,
    getVersion: getVersion,
    clearCache: clearCache,
    // exposed for the test harness only:
    _state: _state,
    _validateInlineSvg: _validateInlineSvg,
    _markedFallback: _markedFallback,
    FALLBACK_GLYPH: DEFAULT_FALLBACK_GLYPH
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraIconResolver = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
