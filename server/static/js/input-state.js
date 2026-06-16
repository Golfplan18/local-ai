/* V3 Input Handling Phase 4 — input-pane state container.
 *
 * Single source of truth for input-pane selections that survive across
 * components but not across submits. Tracks per-input framework and
 * analysis-mode selections (stickiness: per-input only — auto-clears on
 * submit per design doc Q3 § Stickiness).
 *
 * Listeners:
 *   - bridge zone (Phase 5) reads this to render the framework label
 *   - submit code reads this to populate `framework_selected` or
 *     `manual_mode_selection` in the /chat/multipart payload
 *   - toolbar buttons toggle their `.is-active` class via the change
 *     events below
 *
 * Events:
 *   - `ora:framework-changed` fires on every set/clear with
 *     `detail: { framework: { id, display_name, … } | null }`
 *   - `ora:analysis-mode-changed` fires on every set/clear with
 *     `detail: { mode: { id, display_name, … } | null }`
 */
(() => {
  let _selectedFramework = null;
  let _selectedAnalysisMode = null;

  function setFramework(framework) {
    if (!framework || typeof framework !== 'object') {
      return clearFramework();
    }
    clearAnalysisMode();
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

  function setAnalysisMode(mode) {
    if (!mode || typeof mode !== 'object') {
      return clearAnalysisMode();
    }
    clearFramework();
    _selectedAnalysisMode = mode;
    document.dispatchEvent(new CustomEvent('ora:analysis-mode-changed', {
      detail: { mode: _selectedAnalysisMode },
    }));
  }

  function clearAnalysisMode() {
    if (_selectedAnalysisMode === null) return;
    _selectedAnalysisMode = null;
    document.dispatchEvent(new CustomEvent('ora:analysis-mode-changed', {
      detail: { mode: null },
    }));
  }

  function getAnalysisMode() {
    return _selectedAnalysisMode;
  }

  function clearSelection() {
    clearFramework();
    clearAnalysisMode();
  }

  window.OraInputState = {
    setFramework,
    clearFramework,
    getFramework,
    setAnalysisMode,
    clearAnalysisMode,
    getAnalysisMode,
    clearSelection,
  };
})();
