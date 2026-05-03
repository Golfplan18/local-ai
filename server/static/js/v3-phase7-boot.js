/* v3-phase7-boot.js — V3 Phase 7 platform bootstrap (2026-04-30)
 *
 * Initializes the Phase 7 runtime singletons that V1's index.html never
 * wired up at boot:
 *
 *   1. OraPackValidator.init({ schema }) — compiles the toolbar-pack JSON
 *      Schema. WITHOUT THIS, every OraVisualToolbar.register() call throws
 *      "validator_not_initialized", and the universal toolbar / dock never
 *      mounts. visual-panel.js _mountUniversalToolbar swallows the error
 *      silently, so V1 has been quietly broken since WP-7.1.2 landed.
 *
 *   2. OraIconResolver.init() — loads the Lucide icon set. If absent,
 *      icons render as the dashed-square fallback glyph.
 *
 *   3. After both inits resolve, force a re-mount attempt by calling
 *      panel._mountUniversalToolbar(). The natural retry path inside that
 *      function would eventually catch up via its fetch loop, but a single
 *      explicit call avoids the wasteful retry chain.
 *
 * Fires whenever:
 *   • The script loads (defer; runs after DOM parsed).
 *   • The 'ora:canvas-mounted' event fires (in case canvas mount happens
 *     before init completes).
 *
 * Idempotent — re-entrant calls are no-ops once Init has succeeded.
 */
(function () {
  'use strict';

  var SCHEMA_URL = '/static/config/schemas/toolbar-pack.schema.json';
  var DEFAULTS_URL = '/static/config/packs/_defaults.json';

  var _initPromise = null;
  var _initDone = false;
  var _initError = null;
  var _packsLoadResults = [];
  var _mountedPanels = (typeof WeakSet !== 'undefined') ? new WeakSet() : null;

  function ensureInit() {
    if (_initPromise) return _initPromise;

    _initPromise = (function () {
      var validatorInit = Promise.resolve(null);
      var iconInit = Promise.resolve(null);

      if (window.OraPackValidator && typeof window.OraPackValidator.init === 'function'
          && !(window.OraPackValidator._state && window.OraPackValidator._state.initialized)) {
        validatorInit = fetch(SCHEMA_URL)
          .then(function (r) {
            if (!r || !r.ok) throw new Error('schema fetch failed: ' + (r && r.status));
            return r.json();
          })
          .then(function (schema) {
            return window.OraPackValidator.init({ schema: schema });
          })
          .then(function () {
            console.info('[v3-phase7-boot] OraPackValidator initialized');
          });
      }

      if (window.OraIconResolver && typeof window.OraIconResolver.init === 'function') {
        iconInit = window.OraIconResolver.init().then(function () {
          console.info('[v3-phase7-boot] OraIconResolver initialized');
        }).catch(function (e) {
          console.warn('[v3-phase7-boot] OraIconResolver init failed (non-fatal):', e && e.message);
        });
      }

      return Promise.all([validatorInit, iconInit])
        .then(function () { return loadDefaultPacks(); })
        .then(function () { _initDone = true; })
        .catch(function (e) {
          _initError = e;
          console.warn('[v3-phase7-boot] init failed:', e && e.message);
        });
    })();

    return _initPromise;
  }

  function loadDefaultPacks() {
    if (!window.OraPackLoader || typeof window.OraPackLoader.init !== 'function'
        || typeof window.OraPackLoader.loadPack !== 'function') {
      return Promise.resolve();
    }

    // Wire OraCompositionTemplateLoader as the registry pack-loader
    // delegates composition_template registration to. The loader's
    // validator wants `title`; pack format uses `label`. Wrap register
    // so we map label → title (and back to attrs.label so the gallery
    // can still display the original).
    var compositionRegistry = null;
    var ctl = window.OraCompositionTemplateLoader;
    if (ctl && typeof ctl.asPackLoaderRegistry === 'function') {
      try { ctl.init({}); } catch (e) { /* idempotent — ignore */ }
      var realReg = ctl.asPackLoaderRegistry();
      compositionRegistry = {
        register: function (def) {
          var adapted = Object.assign({}, def);
          if (!adapted.title && adapted.label) adapted.title = adapted.label;
          return realReg.register(adapted);
        },
        unregister: realReg.unregister,
        has:        realReg.has,
        get:        realReg.get,
        list:       realReg.list
      };
    }

    return window.OraPackLoader.init({ compositionRegistry: compositionRegistry })
      .then(function () {
        return fetch(DEFAULTS_URL).then(function (r) {
          if (!r || !r.ok) throw new Error('defaults fetch failed: ' + (r && r.status));
          return r.json();
        });
      })
      .then(function (defaults) {
        var names = (defaults && defaults.default_packs) || [];
        var promises = names.map(function (name) {
          var url = '/static/config/packs/' + name;
          return fetch(url)
            .then(function (r) { return r && r.ok ? r.text() : Promise.reject(new Error('pack fetch failed: ' + name)); })
            .then(function (jsonStr) { return window.OraPackLoader.loadPack(jsonStr); })
            .then(function (result) {
              _packsLoadResults.push({ name: name, success: !!(result && result.success), pack_id: result && result.pack_id, errors: result && result.errors });
              if (result && result.success) {
                console.info('[v3-phase7-boot] loaded pack: ' + name + ' → ' + result.pack_id);
              } else {
                console.warn('[v3-phase7-boot] pack load failed: ' + name, result && result.errors);
              }
              return result;
            })
            .catch(function (e) {
              _packsLoadResults.push({ name: name, success: false, errors: [{ message: e && e.message }] });
              console.warn('[v3-phase7-boot] pack fetch/load threw: ' + name, e && e.message);
            });
        });
        return Promise.all(promises);
      });
  }

  function tryMountToolbar() {
    var canvas = window.OraCanvas;
    var panel = canvas && canvas.panel;
    if (!panel) return;

    // Universal toolbar mounting is owned by visual-panel.js — it kicks
    // off a recursive fetch+register+mount chain at panel.init() time.
    // Once the pack validator finishes initializing, the next iteration
    // of that chain succeeds. We do NOT call _mountUniversalToolbar from
    // here: a second concurrent call races visual-panel's retry chain
    // and ends in duplicate universal toolbar wraps.
    //
    // Pack toolbars are a different story — visual-panel never docks
    // them, so OraV3PackToolbars handles that. Wait until the universal
    // toolbar is actually in the dock arrangement (i.e. visual-panel's
    // retry chain has settled) before mounting packs, so the pack edge
    // positions don't fight with universal's auto-placement.
    if (_mountedPanels && _mountedPanels.has(panel)) return;

    var dockReady = panel._dockController
      && panel._dockController.getArrangement
      && panel._dockController.getArrangement()['ora-universal'];

    if (dockReady) {
      if (_mountedPanels) _mountedPanels.add(panel);
      _mountPacks(panel);
      return;
    }

    // Universal not yet in the dock — poll briefly. visual-panel's retry
    // chain settles within ~500ms once init completes.
    var attempts = 0;
    var poll = setInterval(function () {
      attempts++;
      var ready = panel._dockController
        && panel._dockController.getArrangement
        && panel._dockController.getArrangement()['ora-universal'];
      if (ready) {
        clearInterval(poll);
        if (_mountedPanels) _mountedPanels.add(panel);
        _mountPacks(panel);
      } else if (attempts > 40) { // ~4 seconds
        clearInterval(poll);
        console.warn('[v3-phase7-boot] universal toolbar never appeared; mounting packs anyway');
        if (_mountedPanels) _mountedPanels.add(panel);
        _mountPacks(panel);
      }
    }, 100);
  }

  function _mountPacks(panel) {
    if (window.OraV3PackToolbars && typeof window.OraV3PackToolbars.mountAll === 'function') {
      try {
        window.OraV3PackToolbars.mountAll(panel);
        console.info('[v3-phase7-boot] mountAll fired for pack toolbars');
      } catch (e) {
        console.warn('[v3-phase7-boot] OraV3PackToolbars.mountAll threw:', e && e.message);
      }
    }
  }

  // Path A — the canvas mounts AFTER our init completes.
  // We listen for the canvas-mounted event and (re)fire mount if init
  // already completed, or chain it after init.
  document.addEventListener('ora:canvas-mounted', function () {
    ensureInit().then(tryMountToolbar);
  });

  // Path B — the canvas mounts BEFORE our init completes (rare given
  // defer ordering, but possible). Kick off init immediately and re-
  // mount when it resolves.
  ensureInit().then(function () {
    if (window.OraCanvas && window.OraCanvas.panel) {
      tryMountToolbar();
    }
  });

  // Expose for debugging / tests.
  window.OraV3Phase7Boot = {
    ensureInit: ensureInit,
    tryMountToolbar: tryMountToolbar,
    isInitialized: function () { return _initDone; },
    getError: function () { return _initError; },
    getPackResults: function () { return _packsLoadResults.slice(); },
  };
})();
