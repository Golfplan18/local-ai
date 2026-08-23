/* visual-toolbar.js — WP-7.1.1
 *
 * Toolbar registry + renderer for the Phase 7 visual pane.
 *
 * Two responsibilities:
 *   1. **Registry.** Holds toolbar definitions (the JSON shape from
 *      `config/toolbars/<id>.toolbar.json`, matching the `toolbar` $def in
 *      `config/schemas/toolbar-pack.schema.json`). Toolbars register by id;
 *      registering a duplicate id replaces the prior definition (per the
 *      pack-loader contract that lands in WP-7.2.1).
 *
 *   2. **Renderer.** Produces toolbar DOM from a registered definition.
 *      Each tool item becomes a <button class="ora-toolbar__item" ...> with
 *      the resolved Lucide / inline SVG icon embedded. Each item is wired
 *      to an action handler, an enabled-state predicate, and a hover
 *      tooltip text (label + shortcut on enabled items; label + shortcut +
 *      "missing prerequisite" reason on disabled items). The shared
 *      renderer in tooltip.js owns the actual tooltip surface and behavior.
 *
 * Action wiring contract
 * ----------------------
 * The renderer takes an `actionRegistry` — a map from binding string
 * (`"tool:select"`, `"tool:undo"`, etc.) to a handler function. When a
 * binding has no registered handler, the renderer falls back to a stub:
 * clicking the button surfaces the message "<binding> coming with WP-7.X.Y"
 * via an optional `onStub` callback (or a console.info if none). This lets
 * us wire WP-7.1.1's universal toolbar before all backing capability slots
 * land — exactly the §13.1 fallback contract.
 *
 * Enabled-state predicates
 * ------------------------
 * The renderer takes a `predicateRegistry` — a map from predicate string
 * (`"selection_active"`, `"history_has_undo"`, etc.) to a function returning
 * `{ enabled: boolean, reason?: string }`. The toolbar exposes
 * `refreshEnabled()` so callers (visual-panel.js) can re-evaluate after a
 * state change (selection toggle, history push, image load). When a
 * predicate returns `enabled: false`, the button gets `disabled=true` plus
 * a tooltip that combines the static label/shortcut and the reason
 * surfaced by the predicate. Predicates are evaluated only for items that
 * declare `enabled_when`; items without it are always enabled.
 *
 * Public API (exposed on `window.OraVisualToolbar`)
 *   - register(toolbarDef)                      → normalized definition
 *   - get(id)                                   → toolbar def or null
 *   - has(id)                                   → boolean
 *   - list()                                    → [id, ...]
 *   - clear()                                   → resets the registry
 *   - render(idOrDef, options)                  → ToolbarController
 *
 * ToolbarController
 *   - el                  HTMLElement (the rendered <div role="toolbar">)
 *   - id                  toolbar id
 *   - definition          the (validated) definition object
 *   - itemEls             { itemId: HTMLElement }
 *   - refreshEnabled()    re-evaluates predicates and updates DOM state
 *   - setContext(ctx)     replaces the predicate-context object passed
 *                         to predicate functions (so callers can flip
 *                         e.g. selection state without re-rendering)
 *   - destroy()           tears down event listeners and removes DOM
 *
 * Validation
 * ----------
 * On register(), the toolbar is run through OraPackValidator if available
 * (wrapping it in a minimal pack envelope so the existing validator can
 * be reused). On failure, register() throws — built-in toolbars are
 * authored by Ora and should never fail validation; if they do, that's a
 * developer bug, not a user-supplied-pack failure. Pack-supplied toolbars
 * go through their own validation in WP-7.2.1's pack loader.
 *
 * Independent of WP-7.1.2 (docking) — the rendered toolbar can be mounted
 * anywhere; docking lands in WP-7.1.2. For now we mount it once at the
 * top of the visual pane (CSS handles the layout).
 */

(function (root) {
  'use strict';

  // ---- registry state ------------------------------------------------------

  var _registry = Object.create(null);  // { id: definition }

  function _isObj(x) {
    return x !== null && typeof x === 'object' && !Array.isArray(x);
  }

  // Wrap a toolbar def in a minimal pack envelope so OraPackValidator can
  // run its structural + semantic checks. Returns { valid, findings }.
  function _validateToolbarDef(def) {
    if (!root.OraPackValidator || typeof root.OraPackValidator.validate !== 'function') {
      // Validator unavailable — trust the def. Built-in toolbars are
      // authored by Ora; pack-supplied toolbars go through validation
      // separately in WP-7.2.1.
      return { valid: true, findings: [] };
    }
    var pack = {
      pack_name: '__ora_internal_toolbar_wrapper__',
      pack_version: '0.0.0',
      ora_compatibility: '*',
      author: { name: 'Ora' },
      toolbars: [def]
    };
    try {
      return root.OraPackValidator.validate(pack);
    } catch (e) {
      return { valid: false, findings: [{
        severity: 'error',
        code: 'validator_threw',
        message: 'OraPackValidator.validate threw: ' + (e && e.message),
        path: '',
        source: 'validator'
      }] };
    }
  }

  function register(def) {
    if (!_isObj(def)) {
      throw new Error('OraVisualToolbar.register: definition must be an object');
    }
    if (typeof def.id !== 'string' || def.id.length === 0) {
      throw new Error('OraVisualToolbar.register: definition.id is required');
    }
    var result = _validateToolbarDef(def);
    if (!result.valid) {
      var msg = (result.findings || []).map(function (f) {
        return '[' + (f.severity || 'error') + ' ' + (f.code || '?') + ' @ '
             + (f.path || '?') + '] ' + (f.message || '');
      }).join('\n');
      throw new Error('OraVisualToolbar.register: invalid toolbar "' + def.id + '"\n' + msg);
    }
    // Defensive deep-copy so callers can't mutate the registered def.
    var stored = JSON.parse(JSON.stringify(def));
    _registry[stored.id] = stored;
    return stored;
  }

  function get(id) {
    return _registry[id] || null;
  }

  function has(id) {
    return Object.prototype.hasOwnProperty.call(_registry, id);
  }

  function list() {
    return Object.keys(_registry).sort();
  }

  function clear() {
    _registry = Object.create(null);
  }

  // ---- icon resolution helper ----------------------------------------------

  function _resolveIcon(iconRef) {
    if (root.OraIconResolver && typeof root.OraIconResolver.resolve === 'function') {
      return root.OraIconResolver.resolve(iconRef);
    }
    // Resolver unavailable — emit a placeholder rather than failing.
    var safe = String(iconRef == null ? '' : iconRef)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
         + 'data-icon-fallback="no-resolver" data-icon="' + safe + '"></svg>';
  }

  // ---- tooltip composition --------------------------------------------------

  function _composeTooltip(item, enabled, reason) {
    var parts = [item.label];
    var shortcut = item.shortcut;
    if (root.OraKeyboardShortcuts && typeof root.OraKeyboardShortcuts.displayForBinding === 'function') {
      shortcut = root.OraKeyboardShortcuts.displayForBinding(item.binding, item.shortcut);
    }
    if (shortcut) parts.push('(' + shortcut + ')');
    var base = parts.join(' ');
    if (enabled) return base;
    if (reason) return base + ' — ' + reason;
    return base + ' — unavailable';
  }


  // ---- render ---------------------------------------------------------------

  /**
   * Render a toolbar.
   *
   * @param idOrDef    string id (looked up in registry) OR a toolbar def
   * @param options    {
   *   actionRegistry:    { binding -> handler(item, ctx) },
   *   predicateRegistry: { predicate -> ({ enabled, reason } | bool) },
   *   context:           free-form object passed to handlers and predicates,
   *   onStub:            handler(binding, item) called when an item has no
   *                      registered action (defaults to console.info),
   *   stubLabel:         function(binding) -> string. Default returns
   *                      "<binding> coming with WP-7.X.Y".
   *   doc:               document object (override for jsdom tests),
   *   className:         additional CSS class on the toolbar root,
   * }
   * @returns ToolbarController
   */
  function render(idOrDef, options) {
    options = options || {};
    var doc = options.doc || (typeof document !== 'undefined' ? document : null);
    if (!doc) {
      throw new Error('OraVisualToolbar.render: no document available');
    }
    var def = (typeof idOrDef === 'string') ? get(idOrDef) : idOrDef;
    if (!def) {
      throw new Error('OraVisualToolbar.render: unknown toolbar id "' + idOrDef + '"');
    }

    var actionRegistry    = options.actionRegistry    || {};
    var predicateRegistry = options.predicateRegistry || {};
    var context           = options.context           || {};
    var onStub            = options.onStub
      || function (binding, item) {
        try { console.info('[OraVisualToolbar] stub binding: ' + binding); }
        catch (e) { /* ignore */ }
      };
    var stubLabel = options.stubLabel || function (binding) {
      return binding + ' coming with WP-7.X.Y';
    };

    var rootEl = doc.createElement('div');
    rootEl.className = 'ora-toolbar' + (options.className ? (' ' + options.className) : '');
    rootEl.setAttribute('role', 'toolbar');
    rootEl.setAttribute('aria-label', def.label || def.id);
    rootEl.setAttribute('data-toolbar-id', def.id);
    if (def.default_icon_size) {
      rootEl.setAttribute('data-icon-size', def.default_icon_size);
    }
    if (def.default_dock) {
      rootEl.setAttribute('data-default-dock', def.default_dock);
    }

    var itemEls = Object.create(null);
    var listeners = [];

    var items = Array.isArray(def.items) ? def.items : [];
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var btn = doc.createElement('button');
      btn.type = 'button';
      btn.className = 'ora-toolbar__item';
      btn.setAttribute('data-item-id', item.id);
      btn.setAttribute('data-binding', item.binding);
      var shortcut = item.shortcut;
      if (root.OraKeyboardShortcuts && typeof root.OraKeyboardShortcuts.displayForBinding === 'function') {
        shortcut = root.OraKeyboardShortcuts.displayForBinding(item.binding, item.shortcut);
      }
      if (shortcut) btn.setAttribute('data-shortcut', shortcut);
      if (item.enabled_when) btn.setAttribute('data-enabled-when', item.enabled_when);
      btn.setAttribute('aria-label', item.label);
      // WP-7.7.4 — store tooltip text on a data attribute and let the shared
      // tooltip surface render it on hover. We deliberately do NOT set the
      // native `title` attribute, because the browser would render `title`
      // immediately and with platform-default styling, defeating the
      // 500ms-delay + flip-positioned + click-dismissed behaviour spec'd
      // in §13.7.
      btn.setAttribute('data-tooltip', _composeTooltip(item, true));

      // Icon mount — innerHTML is acceptable here because OraIconResolver
      // either returns a vendored Lucide SVG (trusted) or a validated
      // inline SVG. The validator strips script tags and event handlers
      // before this point; pack-validator additionally enforces this for
      // user-supplied packs in WP-7.2.1.
      var iconWrap = doc.createElement('span');
      iconWrap.className = 'ora-toolbar__icon';
      iconWrap.setAttribute('aria-hidden', 'true');
      iconWrap.innerHTML = _resolveIcon(item.icon);
      btn.appendChild(iconWrap);

      // Visually-hidden label so screen readers don't rely on icon-only
      // semantics, and so labels render in environments without CSS.
      var labelWrap = doc.createElement('span');
      labelWrap.className = 'ora-toolbar__label';
      labelWrap.textContent = item.label;
      btn.appendChild(labelWrap);

      // Bind the action lifecycle. Tooltip text stays on the button for the
      // shared renderer in tooltip.js.
      (function (currentItem, currentBtn) {
        function onClick(e) {
          if (currentBtn.disabled) {
            // Disabled state should already prevent the click, but defensive.
            e.preventDefault();
            return;
          }
          var binding = currentItem.binding;
          var handler = actionRegistry[binding];
          if (typeof handler === 'function') {
            try { handler(currentItem, context, e); }
            catch (err) { console.error('[OraVisualToolbar] handler error:', err); }
            return;
          }
          // Stub fallback — wire allows future WPs to register without
          // requiring this code to know which slot owns the binding.
          var msg = stubLabel(binding);
          try { onStub(binding, currentItem, msg); }
          catch (err) { console.error('[OraVisualToolbar] stub error:', err); }
        }
        currentBtn.addEventListener('click',      onClick);
        listeners.push({ el: currentBtn, type: 'click',      fn: onClick });
      })(item, btn);

      rootEl.appendChild(btn);
      itemEls[item.id] = btn;
    }

    // ---- enabled-state evaluation -----------------------------------------

    function _runPredicate(predName, ctx) {
      var fn = predicateRegistry[predName];
      if (typeof fn !== 'function') {
        // Unknown predicate → leave the button enabled but flag through
        // the tooltip so misconfigured definitions are visible. This
        // matches the §13.1 disabled-state contract for missing
        // prerequisites — except we explicitly call it out as
        // "predicate not registered" so the developer sees it in QA.
        return { enabled: true, reason: 'predicate "' + predName + '" not registered' };
      }
      var raw = fn(ctx);
      if (raw === true)  return { enabled: true,  reason: null };
      if (raw === false) return { enabled: false, reason: null };
      if (_isObj(raw)) {
        return {
          enabled: !!raw.enabled,
          reason: typeof raw.reason === 'string' ? raw.reason : null
        };
      }
      return { enabled: true, reason: null };
    }

    function refreshEnabled() {
      for (var j = 0; j < items.length; j++) {
        var it = items[j];
        var el = itemEls[it.id];
        if (!el) continue;
        if (!it.enabled_when) {
          // No predicate → always enabled.
          el.disabled = false;
          el.removeAttribute('aria-disabled');
          el.setAttribute('data-tooltip', _composeTooltip(it, true));
          continue;
        }
        var verdict = _runPredicate(it.enabled_when, context);
        var enabled = !!verdict.enabled;
        el.disabled = !enabled;
        if (enabled) {
          el.removeAttribute('aria-disabled');
        } else {
          el.setAttribute('aria-disabled', 'true');
        }
        el.setAttribute('data-tooltip', _composeTooltip(it, enabled, verdict.reason));
        // Also expose the reason as an attribute for CSS/tooling.
        if (!enabled && verdict.reason) {
          el.setAttribute('data-disabled-reason', verdict.reason);
        } else {
          el.removeAttribute('data-disabled-reason');
        }
      }
    }

    refreshEnabled();

    function setContext(newCtx) {
      context = newCtx || {};
      refreshEnabled();
    }

    // WP-7.1.3 — Icon size configuration. Sets the data-icon-size attribute
    // on the toolbar root, which the CSS uses to switch between
    // small/medium/large/extra-large variants. Caller is expected to pass one
    // of those four canonical strings; anything else is ignored so the
    // attribute keeps its last valid value rather than going blank.
    function setIconSize(size) {
      var allowed = { small: 1, medium: 1, large: 1, 'extra-large': 1 };
      if (!size || !allowed[size]) return;
      rootEl.setAttribute('data-icon-size', size);
    }

    function destroy() {
      for (var k = 0; k < listeners.length; k++) {
        try { listeners[k].el.removeEventListener(listeners[k].type, listeners[k].fn); }
        catch (e) { /* ignore */ }
      }
      listeners = [];
      if (rootEl.parentNode) {
        try { rootEl.parentNode.removeChild(rootEl); } catch (e) { /* ignore */ }
      }
    }

    return {
      el:         rootEl,
      id:         def.id,
      definition: def,
      itemEls:    itemEls,
      refreshEnabled: refreshEnabled,
      setContext: setContext,
      setIconSize: setIconSize,
      destroy:    destroy
    };
  }

  // ---- export --------------------------------------------------------------

  var api = {
    register: register,
    get:      get,
    has:      has,
    list:     list,
    clear:    clear,
    render:   render
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraVisualToolbar = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
