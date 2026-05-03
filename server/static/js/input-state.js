/* V3 Input Handling Phase 4 — input-pane state container.
 *
 * Single source of truth for input-pane selections that survive across
 * components but not across submits. Currently tracks the per-input
 * framework selection (stickiness: per-input only — auto-clears on submit
 * per design doc Q3 § Stickiness).
 *
 * Listeners:
 *   - bridge zone (Phase 5) reads this to render the framework label
 *   - submit code reads this to populate `framework_selected` in the
 *     /chat/multipart payload
 *   - the toolbar button toggles its `.is-active` class via the
 *     `ora:framework-changed` event
 *
 * Events:
 *   - `ora:framework-changed` fires on every set/clear with
 *     `detail: { framework: { id, display_name, … } | null }`
 *
 * Mode selection deliberately is NOT tracked here. The mode-selection
 * subsystem is being redesigned end-to-end and will introduce its own
 * state shape; mixing a placeholder here would prejudice that design.
 */
(() => {
  let _selectedFramework = null;

  function setFramework(framework) {
    if (!framework || typeof framework !== 'object') {
      return clearFramework();
    }
    _selectedFramework = framework;
    document.dispatchEvent(new CustomEvent('ora:framework-changed', {
      detail: { framework: _selectedFramework },
    }));
  }

  function clearFramework() {
    if (_selectedFramework === null) return;
    _selectedFramework = null;
    document.dispatchEvent(new CustomEvent('ora:framework-changed', {
      detail: { framework: null },
    }));
  }

  function getFramework() {
    return _selectedFramework;
  }

  window.OraInputState = {
    setFramework,
    clearFramework,
    getFramework,
  };
})();
