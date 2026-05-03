/* visual-dock.js — WP-7.1.2
 *
 * Edge-docking manager for visual-pane toolbars.
 *
 * Responsibilities:
 *   1. Maintain the four-edge dock model (top / bottom / left / right) + a
 *      "floating" overflow set. Each toolbar lives in exactly one slot.
 *   2. Wrap a rendered toolbar (from visual-toolbar.js) in a chrome shell
 *      that adds a drag handle. The handle is what the user grabs to dock,
 *      undock, or reorder.
 *   3. Hit-test pointer drags against the four edge zones and the inter-
 *      toolbar gaps within each edge. On drop, place the toolbar at the
 *      target slot and re-layout.
 *   4. Compute the canvas-drawable region: window/host minus the cumulative
 *      footprint of all docked toolbars on each edge. Emit an
 *      "arrangement_changed" event so visual-panel can resize the Konva
 *      stage to match.
 *   5. Persist the arrangement to localStorage so WP-7.1.4 hide-on-blur can
 *      restore a user's last layout when chrome reappears.
 *
 * Public API (exposed on `window.OraVisualDock`):
 *
 *   create(host, options) -> DockController
 *     host    — the .visual-panel element. Dock containers are inserted into
 *               this element; the existing .visual-panel__viewport (and any
 *               siblings the panel keeps) is repositioned in-flow so the
 *               viewport occupies the centre row/column.
 *     options:
 *       storageKey: string. Defaults to 'ora.visualPane.dockArrangement.v1'.
 *                   Pass null to disable persistence.
 *       initialArrangement: { id: { edge, position } } overrides any persisted
 *                   arrangement. Useful for tests.
 *       defaultEdges: { id: edge } default edge per toolbar id, used when no
 *                   persisted arrangement exists. Falls back to data-default-
 *                   dock attribute on the toolbar root, then to "top".
 *       onArrangementChanged(footprints, arrangement) — fired after every
 *                   dock/undock/reorder/resize. footprints is
 *                   { top, bottom, left, right } in pixels; arrangement is the
 *                   per-toolbar slot map.
 *       doc:        document override (jsdom tests).
 *       window:     window override (jsdom tests).
 *
 *   The returned DockController exposes:
 *     mount(toolbarController, options)
 *       toolbarController — the controller object returned by
 *                           OraVisualToolbar.render().
 *       options.id       — toolbar id (defaults to controller.id).
 *       options.label    — display label for the drag handle (defaults to
 *                          controller.definition.label or controller.id).
 *       options.defaultEdge — edge used when no persisted/option arrangement
 *                          exists.
 *       Returns the wrapper element (.ora-toolbar-wrap).
 *
 *     unmount(id)
 *       Removes a toolbar from the dock manager. Wrapper is detached but
 *       toolbarController.destroy() is NOT called (the caller owns that).
 *
 *     getArrangement()
 *       Returns the current arrangement map (deep copy).
 *
 *     setArrangement(arrangement)
 *       Replaces the arrangement and re-flows. Unknown ids are ignored.
 *
 *     getFootprints()
 *       Returns { top, bottom, left, right } pixel footprints currently
 *       carved out of the host.
 *
 *     getDrawableRegion()
 *       Returns { width, height } — the size the canvas should occupy after
 *       subtracting all docked toolbar footprints from the host's content
 *       box. visual-panel uses this to size the Konva stage.
 *
 *     destroy()
 *       Removes all listeners and dock containers; the toolbar wrappers
 *       remain (caller is responsible for their teardown via the toolbar
 *       controllers).
 *
 * DOM layout produced (when wired to a host):
 *
 *   <div class="visual-panel">                 <-- the host
 *     <div class="ora-dock ora-dock--top">     <-- rows of toolbars
 *     <div class="ora-dock ora-dock--middle">  <-- left dock | viewport+host content | right dock
 *       <div class="ora-dock ora-dock--left">
 *       <div class="ora-dock-content">         <-- viewport + other panel children
 *       <div class="ora-dock ora-dock--right">
 *     <div class="ora-dock ora-dock--bottom">
 *     <div class="ora-dock ora-dock--floating">
 *
 * The "ora-dock-content" container takes ownership of every existing child
 * of the host that isn't part of the dock skeleton. visual-panel mounts the
 * universal toolbar AFTER setting up the viewport, so by the time create()
 * is called the viewport / overlay elements are already in place; we move
 * them into the centre slot once.
 *
 * Independent of WP-7.1.3 (icon size — controlled via the toolbar's
 * data-icon-size attribute) and WP-7.1.4 (hide-on-blur). Both can read /
 * mutate the arrangement via getArrangement() / setArrangement() without
 * needing to know how docking is implemented.
 */

(function (root) {
  'use strict';

  var EDGES = ['top', 'bottom', 'left', 'right'];
  var FLOAT = 'floating';
  var ALL   = EDGES.concat([FLOAT]);

  var DEFAULT_STORAGE_KEY = 'ora.visualPane.dockArrangement.v1';

  // WP-7.1.3 — per-toolbar thickness in px keyed off data-icon-size. See
  // _estimateDockSize for the derivation (CSS --ora-toolbar-item-size + 10px
  // chrome). Used as a fallback when offsetWidth/Height is zero (jsdom + pre-
  // layout) so the canvas-shrink + min-canvas warning contracts are testable.
  var _ICON_SIZE_PX = {
    'small':       32,
    'medium':      38,
    'large':       46,
    'extra-large': 54
  };

  // WP-7.1.3 — minimum drawable canvas before we surface a warning to the
  // user. Below this the icon-size choice is leaving too little room to draw.
  var MIN_CANVAS_W = 400;
  var MIN_CANVAS_H = 300;
  var MIN_CANVAS_WARN_KEY = 'ora.visualPane.iconSizeWarn.dismissed';

  function _isObj(x) {
    return x !== null && typeof x === 'object' && !Array.isArray(x);
  }
  function _normEdge(e) {
    if (e === 'top' || e === 'bottom' || e === 'left' || e === 'right') return e;
    if (e === FLOAT) return FLOAT;
    return 'top';
  }
  function _deepCopy(o) {
    return JSON.parse(JSON.stringify(o));
  }

  /**
   * create(host, options) — wire a dock manager to a host element. See the
   * file header for the full API. Returns a DockController.
   */
  function create(host, options) {
    options = options || {};
    var doc = options.doc || (host && host.ownerDocument) ||
              (typeof document !== 'undefined' ? document : null);
    var win = options.window ||
              (doc && doc.defaultView) ||
              (typeof window !== 'undefined' ? window : null);
    if (!doc) {
      throw new Error('OraVisualDock.create: no document available');
    }
    if (!host) {
      throw new Error('OraVisualDock.create: host element required');
    }

    var storageKey = (options.storageKey === null) ? null
                   : (options.storageKey || DEFAULT_STORAGE_KEY);
    var defaultEdges = options.defaultEdges || {};
    var onChange = (typeof options.onArrangementChanged === 'function')
                 ? options.onArrangementChanged : null;

    // ---- registry -----------------------------------------------------------

    var toolbars = Object.create(null);  // { id: { id, controller, wrapper, label, defaultEdge } }
    // Edge → ordered list of toolbar ids.
    var slots = { top: [], bottom: [], left: [], right: [], floating: [] };
    // Initial arrangement from persistence + options.initialArrangement.
    var seedArrangement = _loadPersisted() || {};
    if (_isObj(options.initialArrangement)) {
      Object.keys(options.initialArrangement).forEach(function (id) {
        seedArrangement[id] = options.initialArrangement[id];
      });
    }

    // ---- DOM scaffolding ----------------------------------------------------

    host.classList.add('ora-dock-host');

    // Move every existing host child into the centre dock-content container.
    var center = doc.createElement('div');
    center.className = 'ora-dock-content';
    while (host.firstChild) {
      center.appendChild(host.firstChild);
    }

    var topDock     = _mkDock(doc, 'top');
    var bottomDock  = _mkDock(doc, 'bottom');
    var leftDock    = _mkDock(doc, 'left');
    var rightDock   = _mkDock(doc, 'right');
    var middleRow   = doc.createElement('div');
    middleRow.className = 'ora-dock ora-dock--middle';
    middleRow.appendChild(leftDock);
    middleRow.appendChild(center);
    middleRow.appendChild(rightDock);

    var floatLayer  = doc.createElement('div');
    floatLayer.className = 'ora-dock ora-dock--floating';
    floatLayer.setAttribute('data-edge', 'floating');

    host.appendChild(topDock);
    host.appendChild(middleRow);
    host.appendChild(bottomDock);
    host.appendChild(floatLayer);

    var dockEls = { top: topDock, bottom: bottomDock, left: leftDock, right: rightDock, floating: floatLayer };

    // ---- internal helpers ---------------------------------------------------

    function _mkDock(d, edge) {
      var el = d.createElement('div');
      el.className = 'ora-dock ora-dock--' + edge;
      el.setAttribute('data-edge', edge);
      return el;
    }

    function _loadPersisted() {
      if (!storageKey || !win || !win.localStorage) return null;
      try {
        var raw = win.localStorage.getItem(storageKey);
        if (!raw) return null;
        var parsed = JSON.parse(raw);
        return _isObj(parsed) ? parsed : null;
      } catch (e) { return null; }
    }
    function _persist() {
      if (!storageKey || !win || !win.localStorage) return;
      try {
        win.localStorage.setItem(storageKey, JSON.stringify(getArrangement()));
      } catch (e) { /* quota / disabled — silent */ }
    }

    function _resolveSeedEdge(id, fallback) {
      if (seedArrangement[id] && _isObj(seedArrangement[id])) {
        return _normEdge(seedArrangement[id].edge);
      }
      if (defaultEdges[id]) return _normEdge(defaultEdges[id]);
      if (fallback) return _normEdge(fallback);
      return 'top';
    }
    function _resolveSeedPos(id) {
      if (seedArrangement[id] && _isObj(seedArrangement[id]) &&
          typeof seedArrangement[id].position === 'number') {
        return seedArrangement[id].position;
      }
      return null;
    }

    function _placeInSlot(id, edge, position) {
      edge = _normEdge(edge);
      // Remove from any slot first.
      ALL.forEach(function (e) {
        var idx = slots[e].indexOf(id);
        if (idx !== -1) slots[e].splice(idx, 1);
      });
      var arr = slots[edge];
      var insertAt = (typeof position === 'number') ? Math.max(0, Math.min(arr.length, position))
                                                    : arr.length;
      arr.splice(insertAt, 0, id);
    }

    function _redrawSlots() {
      ALL.forEach(function (edge) {
        var dockEl = dockEls[edge];
        if (!dockEl) return;
        // Remove current toolbar wrappers (preserving any decoration nodes).
        var children = Array.prototype.slice.call(dockEl.children);
        for (var i = 0; i < children.length; i++) {
          if (children[i].classList && children[i].classList.contains('ora-toolbar-wrap')) {
            dockEl.removeChild(children[i]);
          }
        }
        // Re-append in slot order.
        var ids = slots[edge];
        for (var j = 0; j < ids.length; j++) {
          var t = toolbars[ids[j]];
          if (t && t.wrapper) {
            t.wrapper.setAttribute('data-edge', edge);
            t.wrapper.setAttribute('data-orientation', _orientationFor(edge));
            dockEl.appendChild(t.wrapper);
          }
        }
        dockEl.toggleAttribute('data-empty', ids.length === 0);
      });
    }

    function _orientationFor(edge) {
      return (edge === 'left' || edge === 'right') ? 'vertical' : 'horizontal';
    }

    function _emitChange() {
      _redrawSlots();
      _persist();
      if (onChange) {
        try { onChange(getFootprints(), getArrangement()); }
        catch (e) { /* ignore */ }
      }
      // WP-7.1.3 — re-evaluate the minimum-canvas warning after every
      // arrangement change. _checkMinCanvas is a no-op until the host UI
      // calls onMinCanvasWarning() to register a handler, so the boot-time
      // _emitChange() pulse from create() is safe.
      _checkMinCanvas();
    }

    // ---- footprint computation ---------------------------------------------

    function _measureDock(edge) {
      var el = dockEls[edge];
      if (!el || edge === 'floating') return 0;
      // If the dock has no toolbars, footprint is zero — even if CSS reserves
      // space we don't want to charge the canvas for an empty rail.
      if (!slots[edge].length) return 0;
      // Use offsetWidth/Height from real DOM. In jsdom these can be 0; we
      // fall back to a deterministic estimate based on toolbar item count
      // so tests can still verify the contract.
      var measured = (edge === 'left' || edge === 'right')
        ? (el.offsetWidth  || 0)
        : (el.offsetHeight || 0);
      if (measured > 0) return measured;
      return _estimateDockSize(edge);
    }
    function _estimateDockSize(edge) {
      // Heuristic for jsdom and pre-layout situations. Each toolbar
      // contributes a thickness keyed off its current data-icon-size
      // attribute (small/medium/large/extra-large) so the drawable region
      // shrinks correctly when the user picks bigger icons. The numbers are
      // CSS-source-of-truth: --ora-toolbar-item-size + 4px chrome padding.
      // small=22+10=32, medium=28+10=38, large=36+10=46, extra-large=44+10=54.
      var ids = slots[edge];
      var total = 0;
      for (var i = 0; i < ids.length; i++) {
        var t = toolbars[ids[i]];
        var size = 'medium';
        if (t && t.controller && t.controller.el &&
            typeof t.controller.el.getAttribute === 'function') {
          var attr = t.controller.el.getAttribute('data-icon-size');
          if (attr === 'small' || attr === 'medium' ||
              attr === 'large' || attr === 'extra-large') {
            size = attr;
          }
        }
        total += _ICON_SIZE_PX[size] || _ICON_SIZE_PX.medium;
      }
      return total;
    }

    function getFootprints() {
      return {
        top:    _measureDock('top'),
        bottom: _measureDock('bottom'),
        left:   _measureDock('left'),
        right:  _measureDock('right'),
      };
    }

    function getDrawableRegion() {
      var fp = getFootprints();
      var hw = host.clientWidth  || 0;
      var hh = host.clientHeight || 0;
      var w = Math.max(0, hw - fp.left - fp.right);
      var h = Math.max(0, hh - fp.top  - fp.bottom);
      return { width: w, height: h };
    }

    // WP-7.1.3 — Handler slot for right-click on the toolbar handle. Set via
    // the `onToolbarHandleContextMenu(fn)` API call below.
    var _onHandleContextMenu = null;
    function onToolbarHandleContextMenu(fn) {
      _onHandleContextMenu = (typeof fn === 'function') ? fn : null;
    }

    // WP-7.1.3 — Apply an icon-size string to every mounted toolbar by
    // delegating to each controller's setIconSize(). Returns the number of
    // toolbars updated so callers can branch on no-op cases.
    function setIconSizeAll(size) {
      var n = 0;
      for (var id in toolbars) {
        var t = toolbars[id];
        if (t && t.controller && typeof t.controller.setIconSize === 'function') {
          t.controller.setIconSize(size);
          n++;
        }
      }
      // Footprints depend on toolbar sizes; emit a change so the canvas
      // can re-measure and re-fit, then run the min-canvas safety check.
      _emitChange();
      _checkMinCanvas();
      return n;
    }

    // WP-7.1.3 — minimum-canvas warning. Fires the registered handler with
    // a payload describing the squeeze. The host UI is responsible for the
    // actual visible warning; we just signal. Dismissal is per-session via
    // sessionStorage so the user isn't nagged on every re-trigger inside one
    // tab session, but a fresh tab gets the warning back.
    var _onMinCanvasWarning = null;
    function onMinCanvasWarning(fn) {
      _onMinCanvasWarning = (typeof fn === 'function') ? fn : null;
    }

    function _isMinCanvasWarnDismissed() {
      if (!win || !win.sessionStorage) return false;
      try {
        return win.sessionStorage.getItem(MIN_CANVAS_WARN_KEY) === '1';
      } catch (e) { return false; }
    }
    function dismissMinCanvasWarning() {
      if (!win || !win.sessionStorage) return;
      try { win.sessionStorage.setItem(MIN_CANVAS_WARN_KEY, '1'); }
      catch (e) { /* quota / disabled — silent */ }
    }
    function resetMinCanvasWarning() {
      if (!win || !win.sessionStorage) return;
      try { win.sessionStorage.removeItem(MIN_CANVAS_WARN_KEY); }
      catch (e) { /* ignore */ }
    }

    function _checkMinCanvas() {
      var region = getDrawableRegion();
      // If layout hasn't run (jsdom or pre-layout), region is zero. Use the
      // estimate-driven shrink: host size minus the sum of footprints. This
      // makes the test contract observable even in jsdom.
      var hw = host.clientWidth  || 0;
      var hh = host.clientHeight || 0;
      var fp = getFootprints();
      // Effective region: prefer the real one, fall back to estimate-based
      // remainder using a notional 800x500 host so footprints can still
      // squeeze it below the threshold in tests with zero-sized hosts.
      var effW, effH;
      if (hw > 0 && hh > 0) {
        effW = region.width;
        effH = region.height;
      } else {
        effW = Math.max(0, 800 - fp.left - fp.right);
        effH = Math.max(0, 500 - fp.top  - fp.bottom);
      }
      var tooNarrow = effW < MIN_CANVAS_W;
      var tooShort  = effH < MIN_CANVAS_H;
      if (!tooNarrow && !tooShort) return false;
      if (_isMinCanvasWarnDismissed()) return false;
      if (typeof _onMinCanvasWarning === 'function') {
        try {
          _onMinCanvasWarning({
            width: effW, height: effH,
            minWidth: MIN_CANVAS_W, minHeight: MIN_CANVAS_H,
            footprints: fp,
            dismiss: dismissMinCanvasWarning
          });
        } catch (e) { /* ignore handler errors */ }
      }
      return true;
    }

    // ---- arrangement read/write --------------------------------------------

    function getArrangement() {
      var out = {};
      ALL.forEach(function (edge) {
        slots[edge].forEach(function (id, pos) {
          out[id] = { edge: edge, position: pos };
        });
      });
      return _deepCopy(out);
    }

    function setArrangement(arrangement) {
      if (!_isObj(arrangement)) return;
      // Clear current slots.
      ALL.forEach(function (e) { slots[e] = []; });
      // Build a sorted list per edge from the input.
      var perEdge = { top: [], bottom: [], left: [], right: [], floating: [] };
      Object.keys(arrangement).forEach(function (id) {
        if (!toolbars[id]) return;
        var entry = arrangement[id];
        if (!_isObj(entry)) return;
        var edge = _normEdge(entry.edge);
        var pos = (typeof entry.position === 'number') ? entry.position : 0;
        perEdge[edge].push({ id: id, position: pos });
      });
      Object.keys(perEdge).forEach(function (edge) {
        perEdge[edge].sort(function (a, b) { return a.position - b.position; });
        slots[edge] = perEdge[edge].map(function (e) { return e.id; });
      });
      // Append any registered toolbars that the input didn't mention to
      // their default edge — never silently lose a toolbar.
      Object.keys(toolbars).forEach(function (id) {
        var found = false;
        ALL.forEach(function (e) { if (slots[e].indexOf(id) !== -1) found = true; });
        if (!found) {
          var t = toolbars[id];
          slots[_normEdge(t.defaultEdge)].push(id);
        }
      });
      _emitChange();
    }

    // ---- mount / unmount ----------------------------------------------------

    function mount(toolbarController, mountOpts) {
      if (!toolbarController || !toolbarController.el) {
        throw new Error('OraVisualDock.mount: toolbarController.el missing');
      }
      mountOpts = mountOpts || {};
      var id = mountOpts.id || toolbarController.id || ('toolbar-' + Object.keys(toolbars).length);
      if (toolbars[id]) {
        // Re-mount: detach the old wrapper first.
        unmount(id);
      }

      var defLabel = (toolbarController.definition && toolbarController.definition.label) ||
                     toolbarController.id || id;
      var label = mountOpts.label || defLabel;

      var defaultEdge = _resolveSeedEdge(id,
        mountOpts.defaultEdge ||
        (toolbarController.el.getAttribute('data-default-dock')) ||
        'top'
      );
      var seedPos = _resolveSeedPos(id);

      // Build the wrapper: handle + toolbar root.
      var wrap = doc.createElement('div');
      wrap.className = 'ora-toolbar-wrap';
      wrap.setAttribute('data-toolbar-id', id);
      wrap.setAttribute('data-edge', defaultEdge);
      wrap.setAttribute('data-orientation', _orientationFor(defaultEdge));

      var handle = doc.createElement('button');
      handle.type = 'button';
      handle.className = 'ora-toolbar-handle';
      handle.setAttribute('aria-label', 'Drag to dock ' + label);
      handle.setAttribute('title', 'Drag to dock ' + label + ' (or drag away to float)');
      handle.setAttribute('data-handle-for', id);
      handle.innerHTML = '<span class="ora-toolbar-handle__grip" aria-hidden="true"></span>';

      // WP-7.1.3 — Right-click on the toolbar handle opens an icon-size
      // picker. The picker itself is registered by visual-panel.js via
      // `dock.onToolbarHandleContextMenu(handler)` so the dock module stays
      // free of UI-construction concerns. We always preventDefault so the
      // browser's native context menu doesn't appear, even if no handler is
      // registered yet — better to be silent than to flash the wrong menu.
      handle.oncontextmenu = function (e) {
        if (e && e.preventDefault) e.preventDefault();
        if (typeof _onHandleContextMenu === 'function') {
          try { _onHandleContextMenu(id, handle, e); }
          catch (err) { /* ignore handler errors */ }
        }
        return false;
      };

      wrap.appendChild(handle);
      wrap.appendChild(toolbarController.el);

      toolbars[id] = {
        id: id,
        controller: toolbarController,
        wrapper: wrap,
        handle: handle,
        label: label,
        defaultEdge: defaultEdge,
      };

      _placeInSlot(id, defaultEdge, seedPos);
      _wireDrag(toolbars[id]);
      _emitChange();
      return wrap;
    }

    function unmount(id) {
      var t = toolbars[id];
      if (!t) return;
      _unwireDrag(t);
      if (t.wrapper && t.wrapper.parentNode) {
        try { t.wrapper.parentNode.removeChild(t.wrapper); } catch (e) { /* ignore */ }
      }
      ALL.forEach(function (e) {
        var idx = slots[e].indexOf(id);
        if (idx !== -1) slots[e].splice(idx, 1);
      });
      delete toolbars[id];
      _emitChange();
    }

    // ---- drag wiring --------------------------------------------------------

    var _dragState = null;

    function _wireDrag(t) {
      var onPointerDown = function (e) {
        if (e.button != null && e.button !== 0) return;  // primary only
        e.preventDefault();
        var hostRect = host.getBoundingClientRect ? host.getBoundingClientRect() : { left: 0, top: 0, width: 0, height: 0 };
        _dragState = {
          id: t.id,
          startX: e.clientX != null ? e.clientX : 0,
          startY: e.clientY != null ? e.clientY : 0,
          hostRect: hostRect,
          dropPreviewEl: null,
        };
        host.classList.add('ora-dock-host--dragging');
        // Listen on doc/window so drag continues outside the handle.
        doc.addEventListener('pointermove', onPointerMove);
        doc.addEventListener('pointerup',   onPointerUp);
        doc.addEventListener('pointercancel', onPointerUp);
      };
      var onPointerMove = function (e) {
        if (!_dragState) return;
        _showDropPreview(e.clientX, e.clientY);
      };
      var onPointerUp = function (e) {
        if (!_dragState) return;
        var target = _hitTestDrop(e.clientX, e.clientY);
        host.classList.remove('ora-dock-host--dragging');
        _clearDropPreview();
        doc.removeEventListener('pointermove', onPointerMove);
        doc.removeEventListener('pointerup',   onPointerUp);
        doc.removeEventListener('pointercancel', onPointerUp);
        if (target) {
          _placeInSlot(_dragState.id, target.edge, target.position);
          _emitChange();
        }
        _dragState = null;
      };
      t.handle.addEventListener('pointerdown', onPointerDown);
      t._listeners = {
        down: onPointerDown,
        move: onPointerMove,
        up:   onPointerUp,
      };
    }
    function _unwireDrag(t) {
      if (!t || !t._listeners) return;
      try { t.handle.removeEventListener('pointerdown', t._listeners.down); }
      catch (e) { /* ignore */ }
      try { doc.removeEventListener('pointermove', t._listeners.move); }
      catch (e) { /* ignore */ }
      try { doc.removeEventListener('pointerup',   t._listeners.up); }
      catch (e) { /* ignore */ }
      try { doc.removeEventListener('pointercancel', t._listeners.up); }
      catch (e) { /* ignore */ }
      t._listeners = null;
    }

    /**
     * Identify the dock target (edge + insertion position) for a pointer
     * coordinate. Returns null if the pointer is outside the host (treated
     * as "float" — the toolbar moves to the floating layer).
     *
     * Hit zones:
     *   - Top edge:    pointer y within EDGE_THICKNESS px of host top.
     *   - Bottom edge: pointer y within EDGE_THICKNESS px of host bottom.
     *   - Left edge:   pointer x within EDGE_THICKNESS px of host left.
     *   - Right edge:  pointer x within EDGE_THICKNESS px of host right.
     *
     * Inside an edge, the position is determined by which existing toolbar
     * the pointer is nearest to (above/below for vertical edges, left/right
     * for horizontal edges).
     *
     * Outside any edge zone but inside the host: pointer is over the
     * canvas area → treat as "float" so the toolbar undocks. This
     * matches the spec's "drag away to float" interaction.
     */
    function _hitTestDrop(clientX, clientY) {
      var rect = host.getBoundingClientRect ? host.getBoundingClientRect() : null;
      if (!rect) return { edge: 'floating', position: 0 };
      var EDGE_THICK = 32;  // px hit zone
      var x = clientX - rect.left;
      var y = clientY - rect.top;
      var w = rect.width  || host.clientWidth  || 0;
      var h = rect.height || host.clientHeight || 0;

      var inside = (x >= 0 && x <= w && y >= 0 && y <= h);
      if (!inside) {
        return { edge: 'floating', position: slots.floating.length };
      }
      var edge = null;
      // Distances to each edge.
      var dT = y, dB = h - y, dL = x, dR = w - x;
      var minD = Math.min(dT, dB, dL, dR);
      if (minD <= EDGE_THICK) {
        if (minD === dT)      edge = 'top';
        else if (minD === dB) edge = 'bottom';
        else if (minD === dL) edge = 'left';
        else                  edge = 'right';
      } else {
        // Inside the canvas → float.
        return { edge: 'floating', position: slots.floating.length };
      }
      // Determine insertion position by walking the existing toolbars on
      // that edge and finding the slot whose midpoint the pointer is past.
      var ids = slots[edge].filter(function (id) { return id !== _dragState.id; });
      var pos = ids.length;  // default: end
      var dockEl = dockEls[edge];
      if (dockEl && ids.length) {
        var horizontal = (edge === 'top' || edge === 'bottom');
        for (var i = 0; i < ids.length; i++) {
          var tw = toolbars[ids[i]] && toolbars[ids[i]].wrapper;
          if (!tw || !tw.getBoundingClientRect) continue;
          var twRect = tw.getBoundingClientRect();
          if (horizontal) {
            var midX = twRect.left + (twRect.width / 2);
            if (clientX < midX) { pos = i; break; }
          } else {
            var midY = twRect.top + (twRect.height / 2);
            if (clientY < midY) { pos = i; break; }
          }
        }
      }
      return { edge: edge, position: pos };
    }

    function _showDropPreview(clientX, clientY) {
      _clearDropPreview();
      var target = _hitTestDrop(clientX, clientY);
      if (!target) return;
      var dockEl = dockEls[target.edge];
      if (!dockEl) return;
      var preview = doc.createElement('div');
      preview.className = 'ora-dock-drop-preview';
      preview.setAttribute('data-edge', target.edge);
      _dragState.dropPreviewEl = preview;
      // Insert into the dock at the target index (skip the dragged
      // toolbar's own entry so the preview lands in the visual position
      // the user will see when they drop).
      var ids = slots[target.edge].filter(function (id) { return id !== _dragState.id; });
      var anchorId = ids[target.position];
      if (anchorId && toolbars[anchorId] && toolbars[anchorId].wrapper) {
        dockEl.insertBefore(preview, toolbars[anchorId].wrapper);
      } else {
        dockEl.appendChild(preview);
      }
    }
    function _clearDropPreview() {
      if (_dragState && _dragState.dropPreviewEl && _dragState.dropPreviewEl.parentNode) {
        try { _dragState.dropPreviewEl.parentNode.removeChild(_dragState.dropPreviewEl); }
        catch (e) { /* ignore */ }
        _dragState.dropPreviewEl = null;
      }
    }

    // ---- window resize ------------------------------------------------------

    var _onWinResize = function () {
      // Footprints depend on element layout; emit a change pulse so consumers
      // re-measure and resize their canvases.
      if (onChange) {
        try { onChange(getFootprints(), getArrangement()); }
        catch (e) { /* ignore */ }
      }
    };
    if (win && typeof win.addEventListener === 'function') {
      win.addEventListener('resize', _onWinResize);
    }

    // ---- destroy ------------------------------------------------------------

    function destroy() {
      // Detach all toolbars (caller still owns their controllers).
      Object.keys(toolbars).slice().forEach(function (id) { unmount(id); });
      if (win && typeof win.removeEventListener === 'function') {
        win.removeEventListener('resize', _onWinResize);
      }
      // Move any centre-dock children back to the host (best effort).
      while (center.firstChild) {
        host.appendChild(center.firstChild);
      }
      // Remove the dock skeleton.
      [topDock, bottomDock, leftDock, rightDock, middleRow, floatLayer].forEach(function (n) {
        if (n && n.parentNode) {
          try { n.parentNode.removeChild(n); } catch (e) { /* ignore */ }
        }
      });
      host.classList.remove('ora-dock-host');
    }

    // ---- public surface -----------------------------------------------------

    var api = {
      mount:             mount,
      unmount:           unmount,
      getArrangement:    getArrangement,
      setArrangement:    setArrangement,
      getFootprints:     getFootprints,
      getDrawableRegion: getDrawableRegion,
      // WP-7.1.3 — icon-size hooks
      setIconSizeAll:           setIconSizeAll,
      onToolbarHandleContextMenu: onToolbarHandleContextMenu,
      onMinCanvasWarning:       onMinCanvasWarning,
      dismissMinCanvasWarning:  dismissMinCanvasWarning,
      resetMinCanvasWarning:    resetMinCanvasWarning,
      checkMinCanvas:           _checkMinCanvas,
      destroy:           destroy,
      // Internal hooks — exposed for tests, not part of the contract.
      _hitTestDrop:      _hitTestDrop,
      _slots:            slots,
      _dockEls:          dockEls,
      _toolbars:         toolbars,
    };
    // Initial change pulse so consumers can size the canvas off the seed.
    _emitChange();
    return api;
  }

  // ---- export ---------------------------------------------------------------

  var module_api = { create: create, EDGES: EDGES, FLOAT: FLOAT };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = module_api;
  }
  if (typeof root !== 'undefined') {
    root.OraVisualDock = module_api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
