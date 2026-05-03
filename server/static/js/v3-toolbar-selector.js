/* v3-toolbar-selector.js — V3 specialty-pack toolbar launcher (2026-05-01)
 *
 * Small popover that lists every registered specialty-pack toolbar (Diagram
 * Thinking, Photo Editor, Mood Board, Cartoon Studio, …) and lets the user
 * dock or undock each one. Replaces the earlier behavior where every loaded
 * pack auto-docked on V3 boot (which jammed the left edge with four toolbars
 * the user mostly didn't want visible at once).
 *
 * Wires:
 *   • Spine button "spineToolbarSelector" (Position 8) → toggle popover.
 *   • Keyboard shortcut Shift+T (when no input has focus) → toggle popover.
 *
 * Public API: window.OraV3ToolbarSelector
 *   open(anchorEl)   — show the popover, anchored near the given element
 *                       (or centered if omitted, e.g., keyboard-triggered).
 *   close()          — hide the popover.
 *   toggle(anchorEl) — open/close convenience for the spine button.
 *
 * Behavior
 *   • Reads pack list from OraV3PackToolbars.listAvailablePacks().
 *   • Activation goes through OraV3PackToolbars.mountPack(panel, id).
 *   • Deactivation goes through OraV3PackToolbars.unmountPack(panel, id).
 *   • The active set persists in localStorage via mountPack/unmountPack.
 *   • Listens on `ora:pack-toolbar-changed` to keep the popover in sync if
 *     a pack toggles while the popover is open (e.g., another module mounts).
 *
 * Styling is inline so the module is fully self-contained and theme-safe.
 */
(function () {
  'use strict';

  var POPOVER_ID = 'ora-toolbar-selector-popover';
  var SHORTCUT_KEY = 'T';     // matched case-insensitively against e.key
  var SHORTCUT_REQUIRES_SHIFT = true;

  var _popover = null;        // { host, body, anchorEl }
  var _docListenersAttached = false;

  // ── DOM helpers ─────────────────────────────────────────────────────────

  function _activePanel() {
    return (window.OraCanvas && window.OraCanvas.panel) || null;
  }

  function _ensurePopoverHost(panel) {
    // Append to the visual pane element so the popover is scoped to
    // the pane (clipped on close, hidden on blur via the same lifecycle
    // that hides the toolbars themselves). Falls back to document.body
    // only if no panel is supplied — keeps the keyboard-shortcut path
    // working even when no canvas is mounted yet.
    var parentEl = (panel && panel.el) ? panel.el : document.body;

    // If a host already exists under a DIFFERENT parent (panel changed),
    // detach + re-create to keep scoping correct.
    var existing = document.getElementById(POPOVER_ID);
    if (existing) {
      if (existing.parentNode === parentEl) {
        return {
          host: existing,
          body: existing.querySelector('.ora-toolbar-selector-body')
        };
      }
      try { existing.parentNode && existing.parentNode.removeChild(existing); }
      catch (e) { /* ignore */ }
    }

    var host = document.createElement('div');
    host.id = POPOVER_ID;
    host.setAttribute('role', 'dialog');
    host.setAttribute('aria-label', 'Toolbar selector');
    host.setAttribute('aria-hidden', 'true');
    host.style.cssText = [
      // absolute (relative to the visual pane) so the popover is
      // visually contained within the pane bounds.
      'position:absolute', 'z-index:50', 'display:none',
      'min-width:240px', 'max-width:320px',
      'background:var(--ora-bg-1, #282a36)',
      'color:var(--ora-fg, #f8f8f2)',
      'border:1px solid var(--ora-border, #44475a)',
      'border-radius:8px', 'padding:10px',
      'box-shadow:0 8px 24px rgba(0,0,0,0.5)',
      'font-family:var(--ora-font-body, Inter, system-ui, sans-serif)',
      'font-size:13px', 'line-height:1.4'
    ].join(';');

    var header = document.createElement('div');
    header.style.cssText =
      'display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;';
    var title = document.createElement('span');
    title.textContent = 'Toolbars';
    title.style.cssText = 'font-weight:600;font-size:13px;letter-spacing:0.02em;';
    var hint = document.createElement('span');
    hint.textContent = 'Shift+T';
    hint.style.cssText =
      'font-size:11px;opacity:0.55;font-family:var(--ora-font-mono, ui-monospace, monospace);';
    header.appendChild(title);
    header.appendChild(hint);

    var body = document.createElement('div');
    body.className = 'ora-toolbar-selector-body';
    body.style.cssText = 'display:flex;flex-direction:column;gap:2px;';

    host.appendChild(header);
    host.appendChild(body);
    parentEl.appendChild(host);
    return { host: host, body: body };
  }

  // ── Row rendering ──────────────────────────────────────────────────────

  function _makeRow(pack, isActive, panel) {
    var row = document.createElement('button');
    row.type = 'button';
    row.className = 'ora-toolbar-selector-row';
    row.setAttribute('data-pack-id', pack.id);
    row.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    row.style.cssText = [
      'display:flex', 'align-items:center', 'gap:8px',
      'width:100%', 'text-align:left',
      'background:' + (isActive ? 'var(--ora-bg-2, #44475a)' : 'transparent'),
      'color:inherit',
      'border:1px solid transparent',
      'border-radius:6px', 'padding:7px 9px', 'cursor:pointer',
      'font:inherit'
    ].join(';');

    var check = document.createElement('span');
    check.textContent = isActive ? '✓' : '';
    check.style.cssText =
      'display:inline-block;width:14px;text-align:center;font-weight:700;color:var(--ora-accent, #50fa7b);';

    var label = document.createElement('span');
    label.textContent = pack.label || pack.id;
    label.style.cssText = 'flex:1;';

    var dock = document.createElement('span');
    dock.textContent = pack.default_dock || 'left';
    dock.style.cssText =
      'font-size:11px;opacity:0.5;font-family:var(--ora-font-mono, ui-monospace, monospace);';

    row.appendChild(check);
    row.appendChild(label);
    row.appendChild(dock);

    row.addEventListener('mouseenter', function () {
      if (row.getAttribute('aria-pressed') !== 'true') {
        row.style.background = 'var(--ora-bg-2, #44475a)';
      }
    });
    row.addEventListener('mouseleave', function () {
      if (row.getAttribute('aria-pressed') !== 'true') {
        row.style.background = 'transparent';
      }
    });

    row.addEventListener('click', function () {
      var Packs = window.OraV3PackToolbars;
      if (!Packs) return;
      var p = panel || _activePanel();
      if (!p) {
        console.warn('[v3-toolbar-selector] no active visual panel');
        return;
      }
      var nowActive = (row.getAttribute('aria-pressed') === 'true');
      if (nowActive) Packs.unmountPack(p, pack.id);
      else           Packs.mountPack(p, pack.id);
      // Re-render to reflect new state. mountPack/unmountPack also fire
      // ora:pack-toolbar-changed which our listener picks up.
    });

    return row;
  }

  function _renderRows() {
    if (!_popover) return;
    var Packs = window.OraV3PackToolbars;
    if (!Packs || typeof Packs.listAvailablePacks !== 'function') return;

    var panel = _activePanel();
    var packs = Packs.listAvailablePacks();
    var body = _popover.body;
    body.innerHTML = '';

    if (!packs.length) {
      var empty = document.createElement('div');
      empty.textContent = 'No specialty packs registered.';
      empty.style.cssText = 'opacity:0.6;padding:8px 6px;font-style:italic;';
      body.appendChild(empty);
      return;
    }

    packs.forEach(function (p) {
      var active = panel ? Packs.isMounted(panel, p.id) : false;
      body.appendChild(_makeRow(p, active, panel));
    });
  }

  // ── Positioning ────────────────────────────────────────────────────────
  //
  // Coordinates are relative to the visual pane element (host's parent),
  // since the host is `position:absolute` inside it. We compute panel-local
  // coordinates by subtracting the panel's bounding rect from the anchor's.

  function _position(host, anchorEl, panel) {
    var parentRect = null;
    if (panel && panel.el && typeof panel.el.getBoundingClientRect === 'function') {
      parentRect = panel.el.getBoundingClientRect();
    }

    if (anchorEl && typeof anchorEl.getBoundingClientRect === 'function' && parentRect) {
      var r = anchorEl.getBoundingClientRect();
      var hostW = host.offsetWidth || 280;
      var hostH = host.offsetHeight || 200;
      // Prefer placing the popover BELOW the anchor (since the universal
      // toolbar typically docks at the top edge of the pane).
      var localLeft = r.left - parentRect.left;
      var localTop  = r.bottom - parentRect.top + 6;
      // Clamp inside the pane bounds so the popover never spills out.
      var maxLeft = Math.max(0, parentRect.width  - hostW - 8);
      var maxTop  = Math.max(0, parentRect.height - hostH - 8);
      localLeft = Math.max(8, Math.min(maxLeft, localLeft));
      localTop  = Math.max(8, Math.min(maxTop,  localTop));
      host.style.left = localLeft + 'px';
      host.style.top  = localTop  + 'px';
      host.style.transform = '';
    } else if (parentRect) {
      // Keyboard-triggered open without an anchor: center inside the pane.
      var hW = host.offsetWidth || 280;
      var hH = host.offsetHeight || 200;
      host.style.left = Math.max(8, (parentRect.width  - hW) / 2) + 'px';
      host.style.top  = Math.max(8, (parentRect.height - hH) / 2) + 'px';
      host.style.transform = '';
    } else {
      // Last-ditch fallback (no panel): centered in viewport. Should not
      // happen in normal flow because the universal toolbar lives on a panel.
      host.style.left = '50%';
      host.style.top = '50%';
      host.style.transform = 'translate(-50%, -50%)';
    }
  }

  // ── Outside click + escape ─────────────────────────────────────────────

  function _outsideClickHandler(e) {
    if (!_popover) return;
    if (_popover.host.contains(e.target)) return;
    if (_popover.anchorEl && _popover.anchorEl.contains(e.target)) return;
    close();
  }

  function _escHandler(e) {
    if (e.key === 'Escape' && _popover) {
      e.preventDefault();
      close();
    }
  }

  function _packChangedHandler() {
    if (_popover) _renderRows();
  }

  function _attachDocListeners() {
    if (_docListenersAttached) return;
    document.addEventListener('mousedown', _outsideClickHandler, true);
    document.addEventListener('keydown', _escHandler);
    document.addEventListener('ora:pack-toolbar-changed', _packChangedHandler);
    _docListenersAttached = true;
  }

  function _detachDocListeners() {
    if (!_docListenersAttached) return;
    document.removeEventListener('mousedown', _outsideClickHandler, true);
    document.removeEventListener('keydown', _escHandler);
    document.removeEventListener('ora:pack-toolbar-changed', _packChangedHandler);
    _docListenersAttached = false;
  }

  // ── Public API ─────────────────────────────────────────────────────────

  function open(anchorEl, panel) {
    var p = panel || _activePanel();
    var bits = _ensurePopoverHost(p);
    _popover = { host: bits.host, body: bits.body, anchorEl: anchorEl || null, panel: p };
    _renderRows();

    bits.host.style.display = 'block';
    bits.host.style.transform = '';
    bits.host.setAttribute('aria-hidden', 'false');
    // Position after display so offset measurements are real.
    _position(bits.host, anchorEl, p);
    _attachDocListeners();
  }

  function close() {
    if (!_popover) return;
    _popover.host.style.display = 'none';
    _popover.host.setAttribute('aria-hidden', 'true');
    _popover = null;
    _detachDocListeners();
  }

  function toggle(anchorEl, panel) {
    if (_popover) close();
    else open(anchorEl, panel);
  }

  function isOpen() { return !!_popover; }

  // ── Keyboard shortcut wiring ───────────────────────────────────────────

  function _shouldIgnoreShortcut(e) {
    var t = e.target;
    if (!t) return false;
    var tag = (t.tagName || '').toUpperCase();
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
    if (t.isContentEditable) return true;
    return false;
  }

  function _shortcutHandler(e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (SHORTCUT_REQUIRES_SHIFT && !e.shiftKey) return;
    if ((e.key || '').toUpperCase() !== SHORTCUT_KEY) return;
    if (_shouldIgnoreShortcut(e)) return;
    e.preventDefault();
    // Try to anchor next to the universal-toolbar launcher button if it
    // exists in the DOM; otherwise the popover centers inside the pane.
    var anchor = document.querySelector('[data-binding="tool:toolbar_selector"]')
              || document.querySelector('[data-toolbar-item-id="toolbar-selector"]')
              || null;
    toggle(anchor, _activePanel());
  }

  // ── Boot wiring ────────────────────────────────────────────────────────
  // The launcher itself lives on the universal toolbar (config:
  // ~/ora/config/toolbars/universal.toolbar.json) and its click is wired
  // via visual-panel.js's actionRegistry under the "tool:toolbar_selector"
  // binding. There is no spine button — the launcher is contained inside
  // the visual pane so it inherits the toolbar's hide-on-blur lifecycle.
  // We only register the global keyboard shortcut here.

  function _wire() {
    document.addEventListener('keydown', _shortcutHandler);
  }

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', _wire);
    } else {
      _wire();
    }
  }

  window.OraV3ToolbarSelector = {
    open: open,
    close: close,
    toggle: toggle,
    isOpen: isOpen,
    _shortcutHandler: _shortcutHandler   // exposed for tests
  };
})();
