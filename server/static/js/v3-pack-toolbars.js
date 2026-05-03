/* v3-pack-toolbars.js — V3 pack-toolbar wiring (2026-04-30)
 *
 * Pack-loaded toolbars (Diagram Thinking, Photo Editor, Mood Board, …)
 * register themselves in OraVisualToolbar's catalog at pack-load time but
 * are not auto-mounted by visual-panel — visual-panel only docks the
 * universal toolbar. This module:
 *
 *   1. Builds an extended action registry that handles the bindings pack
 *      toolbars use (drawing tools, image tools, capability dispatches).
 *   2. Builds a predicate registry that mirrors what visual-panel uses
 *      for the universal toolbar plus an `image_present` predicate the
 *      photo-editor pack relies on.
 *   3. Iterates registered toolbars (skipping ora-universal) and docks
 *      each one at its declared default_dock edge.
 *   4. For capability:* bindings, opens a small floating popover with
 *      OraCapabilityInvocationUI mounted inside. Outside-click and Esc
 *      close the popover; submit auto-closes it.
 *
 * Public API: window.OraV3PackToolbars
 *   mountAll(panel)              — dock every registered non-universal
 *                                  toolbar against the panel
 *   buildExtendedRegistry(panel) — exposes the action registry for tests
 *
 * The popover styling is inline so this module is fully self-contained
 * and works regardless of which theme is active.
 */
(function () {
  'use strict';

  var CAPABILITIES_URL = '/static/config/capabilities.json';
  var CAPABILITY_SLOTS = [
    'image_generates', 'image_edits', 'image_outpaints', 'image_upscales',
    'image_styles', 'image_varies', 'image_to_prompt', 'image_critique',
    'video_generates', 'style_trains'
  ];
  var DRAWING_TOOLS = ['rect', 'ellipse', 'diamond', 'line', 'arrow', 'text'];

  var _capabilitiesPromise = null;
  var _activePopover = null;

  // ── Capabilities loader ───────────────────────────────────────────────

  function _loadCapabilities() {
    if (_capabilitiesPromise) return _capabilitiesPromise;
    _capabilitiesPromise = fetch(CAPABILITIES_URL)
      .then(function (r) { return r && r.ok ? r.json() : null; })
      .catch(function (e) {
        console.warn('[v3-pack-toolbars] capabilities load failed:', e && e.message);
        return null;
      });
    return _capabilitiesPromise;
  }

  // ── Action handlers ───────────────────────────────────────────────────

  function _onImageUpload(panel) {
    var input = panel && panel.el && panel.el.querySelector && panel.el.querySelector('.vp-hidden-file');
    if (input && typeof input.click === 'function') input.click();
    else console.warn('[v3-pack-toolbars] no hidden file input found on panel');
  }

  function _onCapability(slotName, anchorEl, panel) {
    _openCapabilityPopover(slotName, anchorEl, panel);
  }

  function buildExtendedRegistry(panel) {
    var reg = {};

    // Drawing tools — visual-panel.setActiveTool accepts these.
    DRAWING_TOOLS.forEach(function (t) {
      reg['tool:' + t] = function () { panel.setActiveTool(t); };
    });

    // Cartoon Studio bubble tools (§7.9). Click-to-place: arming the
    // tool primes the next pointer-down on the stage to place a bubble,
    // then auto-deactivates.
    ['speech', 'thought', 'shout', 'caption'].forEach(function (kind) {
      var binding = (kind === 'caption') ? 'tool:caption_box' : ('tool:' + kind + '_bubble');
      reg[binding] = function () {
        if (window.OraV3BubbleTools && typeof window.OraV3BubbleTools.activateTool === 'function') {
          window.OraV3BubbleTools.activateTool(panel, kind);
        } else {
          console.warn('[v3-pack-toolbars] OraV3BubbleTools not loaded');
        }
      };
    });

    // Image tools.
    reg['tool:image_upload'] = function () { _onImageUpload(panel); };
    reg['tool:image-crop']   = function () {
      // image-crop tool self-registers on window.OraTools; activating it
      // should go through the panel's tool dispatch when wired. For now,
      // surface it as a no-op-with-log so the click is visible.
      if (panel.setActiveTool) panel.setActiveTool('image-crop');
    };
    // image_rotate / image_flip / image_brightness / image_contrast are
    // not implemented in visual-panel. They render as buttons but click
    // falls through to the toolbar's onStub callback (logged).

    // Capability dispatches.
    CAPABILITY_SLOTS.forEach(function (slot) {
      reg['capability:' + slot] = function (item, ctx, e) {
        var anchor = (e && (e.currentTarget || e.target)) || null;
        _onCapability(slot, anchor, panel);
      };
    });

    // Mirror universal-toolbar bindings so pack toolbars that include
    // them (Ask Ora, undo/redo, etc.) work uniformly.
    reg['tool:select']   = function () { panel.setActiveTool('select'); };
    reg['tool:pan']      = function () { panel._spaceHeld = true; panel._applyCursor && panel._applyCursor(); };
    reg['tool:zoom_in']  = function () { if (panel.zoomIn) panel.zoomIn(); else if (panel._zoomBy) panel._zoomBy(1.2); };
    reg['tool:zoom_out'] = function () { if (panel.zoomOut) panel.zoomOut(); else if (panel._zoomBy) panel._zoomBy(1 / 1.2); };
    reg['tool:zoom_100'] = function () { if (panel.zoomTo100) panel.zoomTo100(); else if (panel.resetView) panel.resetView(); };
    reg['tool:zoom_fit'] = function () { if (panel.zoomToExtents) panel.zoomToExtents(); else if (panel.zoomToFit) panel.zoomToFit(); };
    reg['tool:undo']     = function () { if (panel.undo) panel.undo(); };
    reg['tool:redo']     = function () { if (panel.redo) panel.redo(); };
    reg['tool:save']     = function () { if (panel.saveCanvas) panel.saveCanvas(); };
    reg['tool:export']   = function () { if (panel.exportCanvas) panel.exportCanvas(); };
    reg['tool:clear']    = function () { if (panel.clearArtifact) panel.clearArtifact(); };

    // Ask Ora — mirror the visual-toolbar-bindings attach pattern by
    // letting it overwrite this stub if available.
    reg['tool:ask_ora'] = function () { /* replaced by Bindings.attach below */ };
    try {
      var Bindings = window.OraVisualToolbarBindings;
      if (Bindings && typeof Bindings.attach === 'function') {
        Bindings.attach(reg, { panel: panel });
      }
    } catch (e) { /* silent — Ask Ora stub remains */ }

    return reg;
  }

  function buildExtendedPredicateRegistry(panel) {
    return {
      'image_present': function () {
        var layer = panel && panel.userInputLayer;
        if (!layer || typeof layer.getChildren !== 'function') return { enabled: false, reason: 'No image' };
        var has = false;
        var kids = layer.getChildren();
        for (var i = 0; i < kids.length; i++) {
          var n = kids[i];
          var name = (n && typeof n.getClassName === 'function') ? n.getClassName() : (n && n.className);
          if (name === 'Image') { has = true; break; }
        }
        if (!has && panel._backgroundImageNode) has = true;
        return { enabled: has, reason: has ? null : 'Add an image first' };
      },
      'history_has_undo': function () {
        var has = panel._historyCursor > 0;
        return { enabled: has, reason: has ? null : 'Nothing to undo yet' };
      },
      'history_has_redo': function () {
        var n = panel._history ? panel._history.length : 0;
        var has = panel._historyCursor < n;
        return { enabled: has, reason: has ? null : 'Nothing to redo' };
      },
      'selection_active': function () {
        var n = (panel._selectedShapeIds ? panel._selectedShapeIds.length : 0)
              + (panel._selectedAnnotIds ? panel._selectedAnnotIds.length : 0)
              + (panel._selectedNodeId ? 1 : 0);
        return { enabled: n > 0, reason: n > 0 ? null : 'Select something first' };
      },
      'canvas_has_content': function () {
        var has = !!(panel._currentEnvelope || panel._backgroundImageNode
                  || (panel.userInputLayer && panel.userInputLayer.children
                      && panel.userInputLayer.children.length > 0));
        return { enabled: has, reason: has ? null : 'Canvas is empty' };
      }
    };
  }

  // ── Pack toolbar mounting ─────────────────────────────────────────────

  var ACTIVE_STORAGE_KEY = 'ora.v3.activePackToolbars.v1';

  // Track per-panel mounted toolbar controllers so unmountPack can call
  // controller.destroy() — Dock.unmount() detaches the wrapper but the
  // toolbar's own teardown is the caller's responsibility.
  var _mountedControllers = (typeof WeakMap !== 'undefined') ? new WeakMap() : null;

  function _ensurePanelMap(panel) {
    if (!_mountedControllers) return null;
    var m = _mountedControllers.get(panel);
    if (!m) { m = {}; _mountedControllers.set(panel, m); }
    return m;
  }

  function _readActivePackIds() {
    try {
      var raw = window.localStorage && window.localStorage.getItem(ACTIVE_STORAGE_KEY);
      if (!raw) return [];
      var parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed.slice() : [];
    } catch (e) { return []; }
  }

  function _writeActivePackIds(ids) {
    try {
      if (window.localStorage) {
        window.localStorage.setItem(ACTIVE_STORAGE_KEY, JSON.stringify(ids || []));
      }
    } catch (e) { /* quota / private mode — ignore */ }
  }

  function _isMounted(panel, id) {
    var Dock = panel && panel._dockController;
    if (!Dock || typeof Dock.getArrangement !== 'function') return false;
    var arr = Dock.getArrangement() || {};
    return !!arr[id];
  }

  function listAvailablePacks() {
    var Toolbar = window.OraVisualToolbar;
    if (!Toolbar || typeof Toolbar.list !== 'function') return [];
    var rows = [];
    Toolbar.list().forEach(function (id) {
      if (id === 'ora-universal') return;
      var def = Toolbar.get && Toolbar.get(id);
      if (!def) return;
      rows.push({
        id: id,
        label: def.label || id,
        default_dock: def.default_dock || 'left'
      });
    });
    return rows;
  }

  function mountPack(panel, id) {
    var Toolbar = window.OraVisualToolbar;
    var Dock = panel && panel._dockController;
    if (!Toolbar || !Dock) return false;
    if (id === 'ora-universal') return false;
    if (_isMounted(panel, id)) return true;

    var def = Toolbar.get && Toolbar.get(id);
    if (!def) {
      console.warn('[v3-pack-toolbars] mountPack: unknown toolbar id ' + id);
      return false;
    }

    try {
      var ctl = Toolbar.render(def, {
        actionRegistry:    buildExtendedRegistry(panel),
        predicateRegistry: buildExtendedPredicateRegistry(panel),
        context:           panel
      });
      Dock.mount(ctl, {
        id: id,
        label: def.label || id,
        defaultEdge: def.default_dock || 'left'
      });
      var m = _ensurePanelMap(panel);
      if (m) m[id] = ctl;
      console.info('[v3-pack-toolbars] mounted: ' + id + ' → ' + (def.default_dock || 'left'));

      // Persist new active set.
      var active = _readActivePackIds();
      if (active.indexOf(id) < 0) { active.push(id); _writeActivePackIds(active); }

      // Notify listeners (selector UI).
      try {
        document.dispatchEvent(new CustomEvent('ora:pack-toolbar-changed',
          { detail: { panel: panel, id: id, mounted: true } }));
      } catch (e) { /* no DOM in tests — fine */ }
      return true;
    } catch (e) {
      console.warn('[v3-pack-toolbars] mountPack failed: ' + id + ':', e && e.message);
      return false;
    }
  }

  function unmountPack(panel, id) {
    var Dock = panel && panel._dockController;
    if (!Dock || typeof Dock.unmount !== 'function') return false;
    if (id === 'ora-universal') return false;
    if (!_isMounted(panel, id)) return true;

    try {
      Dock.unmount(id);
      var m = _ensurePanelMap(panel);
      var ctl = m && m[id];
      if (ctl && typeof ctl.destroy === 'function') {
        try { ctl.destroy(); } catch (e) { /* ignore — best-effort cleanup */ }
      }
      if (m) delete m[id];

      var active = _readActivePackIds();
      var idx = active.indexOf(id);
      if (idx >= 0) { active.splice(idx, 1); _writeActivePackIds(active); }

      try {
        document.dispatchEvent(new CustomEvent('ora:pack-toolbar-changed',
          { detail: { panel: panel, id: id, mounted: false } }));
      } catch (e) {}
      return true;
    } catch (e) {
      console.warn('[v3-pack-toolbars] unmountPack failed: ' + id + ':', e && e.message);
      return false;
    }
  }

  // Boot-time mount: only re-mount packs the user previously selected.
  // Replaces the prior "auto-mount everything registered" behavior.
  function mountAll(panel) {
    var ids = _readActivePackIds();
    if (!ids.length) return;
    ids.forEach(function (id) { mountPack(panel, id); });
  }

  // ── Capability popover ────────────────────────────────────────────────

  function _ensurePopoverHost() {
    var existing = document.getElementById('ora-capability-popover');
    if (existing) return existing;

    var host = document.createElement('div');
    host.id = 'ora-capability-popover';
    host.setAttribute('role', 'dialog');
    host.setAttribute('aria-hidden', 'true');
    host.style.cssText = [
      'position:fixed', 'z-index:99999', 'display:none',
      'min-width:340px', 'max-width:520px',
      'background:var(--ora-bg-1, #282a36)',
      'color:var(--ora-fg, #f8f8f2)',
      'border:1px solid var(--ora-border, #44475a)',
      'border-radius:8px', 'padding:12px',
      'box-shadow:0 8px 24px rgba(0,0,0,0.5)',
      'font-family:var(--ora-font-body, Inter, system-ui, sans-serif)',
      'font-size:13px', 'line-height:1.4'
    ].join(';');

    var header = document.createElement('div');
    header.style.cssText = 'display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;';
    var title = document.createElement('span');
    title.id = 'ora-capability-popover-title';
    title.style.cssText = 'font-weight:600;font-size:14px;';
    title.textContent = 'Capability';
    var close = document.createElement('button');
    close.type = 'button';
    close.textContent = '×';
    close.setAttribute('aria-label', 'Close');
    close.style.cssText = 'background:none;border:none;color:inherit;font-size:20px;line-height:1;cursor:pointer;padding:0 4px;';
    close.addEventListener('click', _closeCapabilityPopover);
    header.appendChild(title);
    header.appendChild(close);

    var body = document.createElement('div');
    body.id = 'ora-capability-popover-body';

    host.appendChild(header);
    host.appendChild(body);
    document.body.appendChild(host);
    return host;
  }

  function _positionPopover(host, anchorEl) {
    if (!anchorEl || typeof anchorEl.getBoundingClientRect !== 'function') {
      host.style.left = '50%';
      host.style.top  = '20%';
      host.style.transform = 'translateX(-50%)';
      return;
    }
    var r = anchorEl.getBoundingClientRect();
    var w = host.offsetWidth || 340;
    var h = host.offsetHeight || 240;
    var left = r.left;
    var top  = r.bottom + 8;
    if (left + w > window.innerWidth) left = window.innerWidth - w - 16;
    if (top  + h > window.innerHeight) top = Math.max(8, r.top - h - 8);
    if (left < 8) left = 8;
    host.style.left = left + 'px';
    host.style.top  = top + 'px';
    host.style.transform = '';
  }

  function _openCapabilityPopover(slotName, anchorEl, panel) {
    _loadCapabilities().then(function (caps) {
      if (!caps || !caps.slots || !caps.slots[slotName]) {
        console.warn('[v3-pack-toolbars] slot not configured:', slotName);
        return;
      }
      _closeCapabilityPopover();

      var host  = _ensurePopoverHost();
      var title = document.getElementById('ora-capability-popover-title');
      var body  = document.getElementById('ora-capability-popover-body');
      title.textContent = caps.slots[slotName].label
        || slotName.replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
      body.innerHTML = '';
      host.style.display = 'block';
      host.setAttribute('aria-hidden', 'false');
      _positionPopover(host, anchorEl);

      var ctl = window.OraCapabilityInvocationUI.init({
        hostEl: body,
        capabilities: caps,
        slotName: slotName,
        contextProvider: function () {
          var Serializer = window.OraCanvasSerializer;
          if (!Serializer || !panel) return { canvasSnapshot: null, canvasSelection: null };
          try {
            var snap = (typeof Serializer.captureFromPanel === 'function')
              ? Serializer.captureFromPanel(panel)
              : (panel.userInputLayer && Serializer.serialize ? Serializer.serialize(panel.userInputLayer) : null);
            return {
              canvasSnapshot:  snap,
              canvasSelection: snap && snap._activeSelection ? snap._activeSelection : null
            };
          } catch (e) {
            return { canvasSnapshot: null, canvasSelection: null };
          }
        },
        onDispatch: function (detail) {
          console.info('[v3-pack-toolbars] capability dispatched:', detail && detail.slot);
          setTimeout(_closeCapabilityPopover, 250);
        }
      });

      _activePopover = { host: host, controller: ctl };
      setTimeout(function () {
        document.addEventListener('mousedown', _outsideClickHandler);
        document.addEventListener('keydown', _escHandler);
      }, 10);
    });
  }

  function _outsideClickHandler(e) {
    if (!_activePopover) return;
    if (_activePopover.host.contains(e.target)) return;
    _closeCapabilityPopover();
  }

  function _escHandler(e) {
    if (e.key === 'Escape') _closeCapabilityPopover();
  }

  function _closeCapabilityPopover() {
    if (!_activePopover) return;
    try {
      if (_activePopover.controller && typeof _activePopover.controller.destroy === 'function') {
        _activePopover.controller.destroy();
      }
    } catch (e) {}
    _activePopover.host.style.display = 'none';
    _activePopover.host.setAttribute('aria-hidden', 'true');
    _activePopover = null;
    document.removeEventListener('mousedown', _outsideClickHandler);
    document.removeEventListener('keydown', _escHandler);
  }

  // ── Public API ────────────────────────────────────────────────────────

  window.OraV3PackToolbars = {
    mountAll: mountAll,
    mountPack: mountPack,
    unmountPack: unmountPack,
    isMounted: _isMounted,
    listAvailablePacks: listAvailablePacks,
    readActivePackIds: _readActivePackIds,
    buildExtendedRegistry: buildExtendedRegistry,
    buildExtendedPredicateRegistry: buildExtendedPredicateRegistry,
    _openCapabilityPopover: _openCapabilityPopover,
    _closeCapabilityPopover: _closeCapabilityPopover,
    _loadCapabilities: _loadCapabilities
  };
})();
