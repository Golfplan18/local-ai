/**
 * ask-ora-prompt.js — WP-7.1.5
 *
 * Compact floating prompt panel that the "Ask Ora" toolbar item opens.
 * It's a single-line text input with a Submit button and a small
 * dismissible label, anchored under the toolbar by default. The panel:
 *
 *   - Mounts on demand (`open()`), unmounts on dismiss (`close()` /
 *     Escape / outside click).
 *   - Reads canvas state via `OraCanvasSerializer.captureFromPanel(panel)`
 *     when an `OraVisualPanel` instance is available, falling back to
 *     a serialized userInputLayer when only the layer is exposed.
 *   - Calls back to the host with `{ text, snapshot }` on submit, where
 *     `snapshot` is the spatial_representation dict (or null if no
 *     spatial input).
 *
 * The panel is intentionally provider-agnostic: it does no routing of
 * its own. visual-toolbar-bindings.js wires the on-submit handler and
 * decides between capability dispatch (slot match) and the prose chat
 * path (no slot match).
 *
 * Public API: window.OraAskOraPrompt
 *
 *   .open(opts)    → controller
 *     opts:
 *       hostEl        — element to anchor under (REQUIRED).
 *       onSubmit(detail) — callback(detail = { text, snapshot, panel? })
 *       getCanvasPanel() — returns an OraVisualPanel-like instance
 *                          (something with userInputLayer) or null.
 *                          Optional; defaults to using
 *                          window._oraActiveVisualPanel (set by
 *                          visual-panel.js for cross-module access).
 *       doc           — document override (for jsdom tests).
 *       initialText   — pre-fill the input with this string.
 *       placeholder   — input placeholder text.
 *
 *   .close()       — destroy the live controller (if any)
 *   .isOpen()      — boolean
 *   ._getActive()  — current controller (for tests)
 *
 * Style hooks: every element has an `ora-ask-ora-` class. Inline fallback
 * styles applied so the panel renders sensibly without component CSS.
 */
(function (root) {
  'use strict';

  // ── DOM helpers ─────────────────────────────────────────────────────────

  function _el(doc, tag, cls, text) {
    var n = doc.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  // ── Canvas snapshot ─────────────────────────────────────────────────────
  //
  // We try, in order:
  //   1. opts.getCanvasPanel() and pass the panel to the serializer.
  //   2. window._oraActiveVisualPanel (set by visual-panel when active).
  //   3. window.OraVisualPanel.getActive() if it exists.
  // Returns spatial_representation | null.

  function _capture(opts) {
    var Serializer = root.OraCanvasSerializer;
    if (!Serializer) return null;
    var panel = null;
    try {
      if (typeof opts.getCanvasPanel === 'function') {
        panel = opts.getCanvasPanel();
      }
    } catch (e) { panel = null; }
    if (!panel && typeof root !== 'undefined') {
      panel = root._oraActiveVisualPanel || null;
      if (!panel && root.OraVisualPanel && typeof root.OraVisualPanel.getActive === 'function') {
        try { panel = root.OraVisualPanel.getActive() || null; } catch (e) { panel = null; }
      }
    }
    if (!panel) return null;
    try {
      if (typeof Serializer.captureFromPanel === 'function') {
        return Serializer.captureFromPanel(panel);
      }
      // Fallback: panel exposes userInputLayer directly.
      if (panel.userInputLayer && typeof Serializer.serialize === 'function') {
        return Serializer.serialize(panel.userInputLayer);
      }
    } catch (e) {
      try { console.warn('[ask-ora-prompt] capture failed:', e); } catch (_e) {}
    }
    return null;
  }

  // ── Controller ──────────────────────────────────────────────────────────

  var _activeController = null;

  function _close() {
    if (_activeController) {
      try { _activeController.destroy(); } catch (e) {}
      _activeController = null;
    }
  }

  function open(opts) {
    opts = opts || {};
    var doc = opts.doc || (typeof document !== 'undefined' ? document : null);
    if (!doc) throw new Error('OraAskOraPrompt.open: no document available');
    if (!opts.hostEl) throw new Error('OraAskOraPrompt.open: hostEl is required');

    // Single-instance: tearing down any prior open panel first.
    _close();

    var rootEl = _el(doc, 'div', 'ora-ask-ora-prompt');
    rootEl.setAttribute('role', 'dialog');
    rootEl.setAttribute('aria-label', 'Ask Ora');
    var s = rootEl.style;
    s.position = 'absolute';
    s.zIndex = '9000';
    s.background = 'var(--ora-panel-bg, #1c1f26)';
    s.color = 'var(--ora-panel-fg, #f6f7f9)';
    s.border = '1px solid var(--ora-panel-border, rgba(255,255,255,0.12))';
    s.borderRadius = '6px';
    s.padding = '8px 10px';
    s.boxShadow = '0 4px 14px rgba(0,0,0,0.3)';
    s.display = 'flex';
    s.gap = '6px';
    s.alignItems = 'center';
    s.minWidth = '320px';

    var input = _el(doc, 'input', 'ora-ask-ora-prompt__input');
    input.type = 'text';
    input.setAttribute('aria-label', 'Ask Ora prompt');
    input.placeholder = opts.placeholder || 'Ask Ora… (e.g., "describe what\'s on the canvas")';
    input.style.flex = '1 1 auto';
    input.style.background = 'transparent';
    input.style.color = 'inherit';
    input.style.border = '1px solid var(--ora-input-border, rgba(255,255,255,0.18))';
    input.style.borderRadius = '4px';
    input.style.padding = '6px 8px';
    input.style.font = '13px/1.4 var(--ora-ui-font, system-ui, -apple-system, sans-serif)';
    input.style.outline = 'none';
    if (opts.initialText) input.value = String(opts.initialText);

    var submitBtn = _el(doc, 'button', 'ora-ask-ora-prompt__submit', 'Ask');
    submitBtn.type = 'button';
    submitBtn.style.background = 'var(--ora-accent, #6f7cff)';
    submitBtn.style.color = '#fff';
    submitBtn.style.border = '0';
    submitBtn.style.borderRadius = '4px';
    submitBtn.style.padding = '6px 12px';
    submitBtn.style.font = '13px/1.4 var(--ora-ui-font, system-ui, -apple-system, sans-serif)';
    submitBtn.style.cursor = 'pointer';

    var dismissBtn = _el(doc, 'button', 'ora-ask-ora-prompt__dismiss', '×');
    dismissBtn.type = 'button';
    dismissBtn.setAttribute('aria-label', 'Close');
    dismissBtn.style.background = 'transparent';
    dismissBtn.style.color = 'inherit';
    dismissBtn.style.border = '0';
    dismissBtn.style.font = '16px/1 var(--ora-ui-font, system-ui, -apple-system, sans-serif)';
    dismissBtn.style.cursor = 'pointer';
    dismissBtn.style.padding = '0 4px';

    rootEl.appendChild(input);
    rootEl.appendChild(submitBtn);
    rootEl.appendChild(dismissBtn);

    // Anchor under the host element.
    var hostRect = (typeof opts.hostEl.getBoundingClientRect === 'function')
      ? opts.hostEl.getBoundingClientRect() : null;
    var win = doc.defaultView || (typeof window !== 'undefined' ? window : null);
    var scrollX = (win && win.scrollX) || 0;
    var scrollY = (win && win.scrollY) || 0;
    if (hostRect) {
      s.left = (hostRect.left + scrollX) + 'px';
      s.top = (hostRect.bottom + scrollY + 6) + 'px';
    }

    (doc.body || doc.documentElement).appendChild(rootEl);

    function _doSubmit() {
      var text = (input.value || '').trim();
      if (!text.length) {
        // Don't dispatch on empty; jiggle focus and bail.
        try { input.focus(); } catch (e) {}
        return null;
      }
      var snapshot = null;
      try { snapshot = _capture(opts); } catch (e) { snapshot = null; }
      var detail = {
        text: text,
        snapshot: snapshot,
        panel: (function () {
          try {
            if (typeof opts.getCanvasPanel === 'function') return opts.getCanvasPanel();
            return root._oraActiveVisualPanel || null;
          } catch (e) { return null; }
        })()
      };
      try {
        if (typeof opts.onSubmit === 'function') opts.onSubmit(detail);
      } catch (e) {
        try { console.error('[ask-ora-prompt] onSubmit error:', e); } catch (_e) {}
      }
      // Default behavior: close the panel after a successful submit so the
      // user isn't left with a stale input. Caller can re-open if needed.
      destroy();
      return detail;
    }

    function _onKeyDown(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        _doSubmit();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        destroy();
      }
    }

    function _onSubmitClick(e) {
      e.preventDefault();
      _doSubmit();
    }

    function _onDismissClick(e) {
      e.preventDefault();
      destroy();
    }

    function _onDocClick(e) {
      // Outside-click closes the panel. We also ignore clicks on the
      // host element so the toolbar button toggle keeps behaving sanely
      // (the binding handler decides whether to re-open).
      if (!rootEl.contains(e.target) && !opts.hostEl.contains(e.target)) {
        destroy();
      }
    }

    input.addEventListener('keydown', _onKeyDown);
    submitBtn.addEventListener('click', _onSubmitClick);
    dismissBtn.addEventListener('click', _onDismissClick);
    // Defer attaching the document-click handler one tick so the click
    // that opened the panel doesn't immediately close it.
    var docClickAttached = false;
    var attachTimer = setTimeout(function () {
      try { doc.addEventListener('click', _onDocClick, true); docClickAttached = true; }
      catch (e) {}
    }, 0);

    // Focus the input after mounting.
    try { input.focus(); } catch (e) {}

    var destroyed = false;

    function destroy() {
      if (destroyed) return;
      destroyed = true;
      try { clearTimeout(attachTimer); } catch (e) {}
      try { input.removeEventListener('keydown', _onKeyDown); } catch (e) {}
      try { submitBtn.removeEventListener('click', _onSubmitClick); } catch (e) {}
      try { dismissBtn.removeEventListener('click', _onDismissClick); } catch (e) {}
      if (docClickAttached) {
        try { doc.removeEventListener('click', _onDocClick, true); } catch (e) {}
      }
      if (rootEl.parentNode) {
        try { rootEl.parentNode.removeChild(rootEl); } catch (e) {}
      }
      if (_activeController === ctl) _activeController = null;
    }

    var ctl = {
      el: rootEl,
      input: input,
      submitBtn: submitBtn,
      dismissBtn: dismissBtn,
      submit: _doSubmit,
      destroy: destroy,
      isOpen: function () { return !destroyed; }
    };
    _activeController = ctl;
    return ctl;
  }

  function isOpen() {
    return !!(_activeController && _activeController.isOpen && _activeController.isOpen());
  }

  var api = {
    open: open,
    close: _close,
    isOpen: isOpen,
    _getActive: function () { return _activeController; }
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraAskOraPrompt = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
