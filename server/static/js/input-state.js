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
 *     `manual_mode_selection` / `manual_lens_selection` in the
 *     /chat/multipart payload
 *   - toolbar buttons toggle their `.is-active` class via the change
 *     events below
 *
 * Events:
 *   - `ora:framework-changed` fires on every set/clear with
 *     `detail: { framework: { id, display_name, … } | null }`
 *   - `ora:analysis-mode-changed` fires on every set/clear with
 *     `detail: { mode: { id, display_name, … } | null }`
 *   - `ora:analysis-lens-changed` fires on every set/clear with
 *     `detail: { lens: { id, display_name, … } | null }`
 */
(() => {
  let _selectedFramework = null;
  let _selectedAnalysisMode = null;
  let _selectedAnalysisLens = null;

  function modeHasLens(mode, lensId) {
    if (!mode || !lensId || !Array.isArray(mode.lenses)) return false;
    return mode.lenses.some(lens => lens && lens.id === lensId);
  }

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
    const previousModeId = _selectedAnalysisMode && _selectedAnalysisMode.id;
    clearFramework();
    if (previousModeId && previousModeId !== mode.id) {
      clearAnalysisLens();
    }
    _selectedAnalysisMode = mode;
    if (_selectedAnalysisLens && !modeHasLens(mode, _selectedAnalysisLens.id)) {
      clearAnalysisLens();
    }
    document.dispatchEvent(new CustomEvent('ora:analysis-mode-changed', {
      detail: { mode: _selectedAnalysisMode },
    }));
  }

  function clearAnalysisMode() {
    clearAnalysisLens();
    if (_selectedAnalysisMode === null) return;
    _selectedAnalysisMode = null;
    document.dispatchEvent(new CustomEvent('ora:analysis-mode-changed', {
      detail: { mode: null },
    }));
  }

  function getAnalysisMode() {
    return _selectedAnalysisMode;
  }

  function setAnalysisLens(lens) {
    if (!lens || typeof lens !== 'object') {
      return clearAnalysisLens();
    }
    if (!_selectedAnalysisMode || !modeHasLens(_selectedAnalysisMode, lens.id)) {
      return clearAnalysisLens();
    }
    _selectedAnalysisLens = lens;
    document.dispatchEvent(new CustomEvent('ora:analysis-lens-changed', {
      detail: { lens: _selectedAnalysisLens },
    }));
  }

  function clearAnalysisLens() {
    if (_selectedAnalysisLens === null) return;
    _selectedAnalysisLens = null;
    document.dispatchEvent(new CustomEvent('ora:analysis-lens-changed', {
      detail: { lens: null },
    }));
  }

  function getAnalysisLens() {
    return _selectedAnalysisLens;
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
    setAnalysisLens,
    clearAnalysisLens,
    getAnalysisLens,
    clearSelection,
  };
})();
