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
  let _revision = 0;

  function modeHasLens(mode, lensId) {
    if (!mode || !lensId || !Array.isArray(mode.lenses)) return false;
    return mode.lenses.some(lens => lens && lens.id === lensId);
  }

  function setFramework(framework) {
    if (!framework || typeof framework !== 'object') {
      return clearFramework();
    }
    if (window.OraProgramming && typeof window.OraProgramming.setActive === 'function') {
      window.OraProgramming.setActive(false);
    }
    document.dispatchEvent(new CustomEvent('ora:turn-tool-selected', {
      detail: { tool: 'framework' },
    }));
    clearAnalysisMode();
    _selectedFramework = framework;
    _revision += 1;
    document.dispatchEvent(new CustomEvent('ora:framework-changed', {
      detail: { framework: _selectedFramework },
    }));
  }

  function clearFramework() {
    if (_selectedFramework === null) return;
    _selectedFramework = null;
    _revision += 1;
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
    if (window.OraProgramming && typeof window.OraProgramming.setActive === 'function') {
      window.OraProgramming.setActive(false);
    }
    document.dispatchEvent(new CustomEvent('ora:turn-tool-selected', {
      detail: { tool: 'analysis' },
    }));
    const previousModeId = _selectedAnalysisMode && _selectedAnalysisMode.id;
    clearFramework();
    if (previousModeId && previousModeId !== mode.id) {
      clearAnalysisLens();
    }
    _selectedAnalysisMode = mode;
    _revision += 1;
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
    _revision += 1;
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
    _revision += 1;
    document.dispatchEvent(new CustomEvent('ora:analysis-lens-changed', {
      detail: { lens: _selectedAnalysisLens },
    }));
  }

  function clearAnalysisLens() {
    if (_selectedAnalysisLens === null) return;
    _selectedAnalysisLens = null;
    _revision += 1;
    document.dispatchEvent(new CustomEvent('ora:analysis-lens-changed', {
      detail: { lens: null },
    }));
  }

  function getAnalysisLens() {
    return _selectedAnalysisLens;
  }

  function snapshotForSubmission() {
    return {
      revision: _revision,
      framework: _selectedFramework,
      analysisMode: _selectedAnalysisMode,
      analysisLens: _selectedAnalysisLens,
    };
  }

  function clearSelection(snapshot) {
    if (snapshot && snapshot.revision !== _revision) return false;
    clearFramework();
    clearAnalysisMode();
    return true;
  }

  function reserveSubmission(snapshot) {
    if (!snapshot || snapshot.revision !== _revision) return null;
    const token = {
      revision: _revision,
      framework: _selectedFramework,
      analysisMode: _selectedAnalysisMode,
      analysisLens: _selectedAnalysisLens,
    };
    const before = _revision;
    clearFramework();
    clearAnalysisMode();
    if (_revision === before) _revision += 1;
    token.reservedRevision = _revision;
    return token;
  }

  function restoreSubmission(token) {
    if (!token || token.reservedRevision !== _revision
        || _selectedFramework !== null
        || _selectedAnalysisMode !== null
        || _selectedAnalysisLens !== null) return false;
    _selectedFramework = token.framework || null;
    _selectedAnalysisMode = token.analysisMode || null;
    _selectedAnalysisLens = token.analysisLens || null;
    _revision += 1;
    document.dispatchEvent(new CustomEvent('ora:framework-changed', {
      detail: { framework: _selectedFramework },
    }));
    document.dispatchEvent(new CustomEvent('ora:analysis-mode-changed', {
      detail: { mode: _selectedAnalysisMode },
    }));
    document.dispatchEvent(new CustomEvent('ora:analysis-lens-changed', {
      detail: { lens: _selectedAnalysisLens },
    }));
    return true;
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
    snapshotForSubmission,
    reserveSubmission,
    restoreSubmission,
    clearSelection,
  };
})();
