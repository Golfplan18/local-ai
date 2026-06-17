/* V3 Analyses picker — executable mode selection.
 *
 * The picker is intentionally separate from the framework picker. Modes
 * answer "what analytical operation should run"; lenses refine a selected
 * mode, so they appear only as a second pass under that mode.
 */
(() => {
  const PICKER_SELECTOR = '#analysisPicker';
  const SEARCH_SELECTOR = '#analysisPickerSearch';
  const TERRITORIES_SELECTOR = '#analysisPickerTerritories';
  const RESULTS_SELECTOR = '#analysisPickerResults';
  const TOOLBAR_BTN_SELECTOR = '#inputToolbarAnalysis';
  const OVERVIEW_TERRITORY = '__overview__';
  const LENS_GROUPS = [
    ['required', 'Core lenses'],
    ['optional', 'Optional lenses'],
    ['foundational', 'Foundational lenses'],
    ['related', 'Related lenses'],
  ];

  let _picker = null;
  let _search = null;
  let _territories = null;
  let _results = null;
  let _btn = null;
  let _modes = [];
  let _activeTerritory = OVERVIEW_TERRITORY;
  let _lensStepModeId = null;
  let _outsideHandler = null;
  let _escapeHandler = null;

  function open() {
    if (!_picker) return;
    if (window.OraFrameworkPicker && typeof window.OraFrameworkPicker.close === 'function') {
      window.OraFrameworkPicker.close();
    }
    _picker.hidden = false;
    if (_btn) _btn.setAttribute('aria-expanded', 'true');

    fetch('/api/analyses/picker')
      .then(res => res.ok ? res.json() : { modes: [] })
      .then(payload => {
        _modes = Array.isArray(payload && payload.modes) ? payload.modes : [];
        ensureActiveTerritory();
        const selected = freshSelectedMode();
        if (selected && lensesForMode(selected).length) {
          renderLensStep(selected);
        } else {
          render('');
        }
      })
      .catch(err => {
        console.warn('[analysis-picker] fetch failed:', err);
        renderError('Could not load analyses. Check the server log.');
      });

    if (_search) {
      _search.value = '';
      setTimeout(() => { try { _search.focus(); } catch (_) {} }, 0);
    }

    _outsideHandler = (e) => {
      if (_picker.hidden) return;
      const target = e.target;
      if (_picker.contains(target) || (_btn && _btn.contains(target))) return;
      close();
    };
    _escapeHandler = (e) => {
      if (e.key === 'Escape' && !_picker.hidden) {
        e.stopPropagation();
        close();
      }
    };
    document.addEventListener('mousedown', _outsideHandler, true);
    document.addEventListener('keydown', _escapeHandler, true);
  }

  function close() {
    if (!_picker || _picker.hidden) return;
    _picker.hidden = true;
    if (_btn) _btn.setAttribute('aria-expanded', 'false');
    if (_outsideHandler) {
      document.removeEventListener('mousedown', _outsideHandler, true);
      _outsideHandler = null;
    }
    if (_escapeHandler) {
      document.removeEventListener('keydown', _escapeHandler, true);
      _escapeHandler = null;
    }
  }

  function toggle() {
    if (!_picker) return;
    if (_picker.hidden) open();
    else close();
  }

  function ensureActiveTerritory() {
    if (_activeTerritory === OVERVIEW_TERRITORY) return;
    if (_modes.some(m => m.territory === _activeTerritory)) return;
    const selected = selectedMode();
    if (selected && _modes.some(m => m.territory === selected.territory)) {
      _activeTerritory = selected.territory;
      return;
    }
    _activeTerritory = OVERVIEW_TERRITORY;
  }

  function selectedMode() {
    if (!window.OraInputState || typeof window.OraInputState.getAnalysisMode !== 'function') {
      return null;
    }
    return window.OraInputState.getAnalysisMode();
  }

  function selectedLens() {
    if (!window.OraInputState || typeof window.OraInputState.getAnalysisLens !== 'function') {
      return null;
    }
    return window.OraInputState.getAnalysisLens();
  }

  function lensesForMode(mode) {
    return Array.isArray(mode && mode.lenses) ? mode.lenses : [];
  }

  function freshSelectedMode() {
    const selected = selectedMode();
    if (!selected || !selected.id) return null;
    return _modes.find(mode => mode.id === selected.id) || selected;
  }

  function searchText(mode) {
    return [
      mode.id,
      mode.display_name,
      mode.display_description,
      mode.educational_name,
      mode.territory_name,
      ...(Array.isArray(mode.aliases) ? mode.aliases : []),
      ...lensesForMode(mode).flatMap(lens => [
        lens.id,
        lens.display_name,
        lens.display_description,
      ]),
    ].join(' ').toLowerCase();
  }

  function territoryRows() {
    const map = new Map();
    for (const mode of _modes) {
      const key = mode.territory || 'T0';
      if (!map.has(key)) {
        map.set(key, {
          id: key,
          name: mode.territory_name || key,
          order: Number.isFinite(mode.territory_order) ? mode.territory_order : 99,
          count: 0,
        });
      }
      map.get(key).count += 1;
    }
    return [...map.values()].sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
  }

  function modesForTerritory(territoryId) {
    return _modes.filter(mode => mode.territory === territoryId);
  }

  function render(query) {
    if (!_territories || !_results) return;
    _lensStepModeId = null;
    const q = (query || '').trim().toLowerCase();
    renderTerritories(q);
    renderResults(q);
  }

  function renderTerritories(query) {
    _territories.innerHTML = '';
    const head = document.createElement('div');
    head.className = 'analysis-picker__rail-label';
    head.textContent = 'Analyses';
    _territories.appendChild(head);

    const overview = document.createElement('button');
    overview.type = 'button';
    overview.className = 'analysis-picker__territory analysis-picker__territory--overview';
    overview.dataset.territory = OVERVIEW_TERRITORY;
    if (!query && _activeTerritory === OVERVIEW_TERRITORY) {
      overview.classList.add('is-active');
    }
    const overviewName = document.createElement('span');
    overviewName.className = 'analysis-picker__territory-name';
    overviewName.textContent = 'All territories';
    overview.appendChild(overviewName);
    const overviewCount = document.createElement('span');
    overviewCount.className = 'analysis-picker__territory-count';
    overviewCount.textContent = String(_modes.length);
    overview.appendChild(overviewCount);
    overview.addEventListener('click', () => {
      _activeTerritory = OVERVIEW_TERRITORY;
      if (_search) _search.value = '';
      render('');
    });
    _territories.appendChild(overview);

    for (const territory of territoryRows()) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'analysis-picker__territory';
      btn.dataset.territory = territory.id;
      if (!query && territory.id === _activeTerritory) {
        btn.classList.add('is-active');
      }

      const name = document.createElement('span');
      name.className = 'analysis-picker__territory-name';
      name.textContent = territory.name;
      btn.appendChild(name);

      const count = document.createElement('span');
      count.className = 'analysis-picker__territory-count';
      count.textContent = String(territory.count);
      btn.appendChild(count);

      btn.addEventListener('click', () => {
        _activeTerritory = territory.id;
        if (_search) _search.value = '';
        render('');
      });
      _territories.appendChild(btn);
    }
  }

  function renderResults(query) {
    _results.innerHTML = '';
    let rows;
    let title;
    if (query) {
      rows = _modes.filter(mode => searchText(mode).includes(query));
      title = 'Search results';
    } else if (_activeTerritory === OVERVIEW_TERRITORY) {
      renderOverview();
      return;
    } else {
      rows = modesForTerritory(_activeTerritory);
      const terr = territoryRows().find(t => t.id === _activeTerritory);
      title = terr ? terr.name : 'Analyses';
    }

    const header = document.createElement('div');
    header.className = 'analysis-picker__results-header';
    const h = document.createElement('div');
    h.className = 'analysis-picker__results-title';
    h.textContent = title;
    header.appendChild(h);
    const count = document.createElement('div');
    count.className = 'analysis-picker__results-count';
    count.textContent = `${rows.length}`;
    header.appendChild(count);
    _results.appendChild(header);

    if (!rows.length) {
      const empty = document.createElement('div');
      empty.className = 'analysis-picker__empty';
      empty.textContent = query ? `No analyses match "${_search.value}".` : 'No analyses available.';
      _results.appendChild(empty);
      return;
    }

    const list = document.createElement('div');
    list.className = 'analysis-picker__list';
    for (const mode of rows) list.appendChild(buildRow(mode, Boolean(query)));
    _results.appendChild(list);
  }

  function renderOverview() {
    const territories = territoryRows();
    const header = document.createElement('div');
    header.className = 'analysis-picker__results-header';
    const h = document.createElement('div');
    h.className = 'analysis-picker__results-title';
    h.textContent = 'All territories';
    header.appendChild(h);
    const count = document.createElement('div');
    count.className = 'analysis-picker__results-count';
    count.textContent = `${_modes.length} modes`;
    header.appendChild(count);
    _results.appendChild(header);

    if (!territories.length) {
      const empty = document.createElement('div');
      empty.className = 'analysis-picker__empty';
      empty.textContent = 'No analyses available.';
      _results.appendChild(empty);
      return;
    }

    const list = document.createElement('div');
    list.className = 'analysis-picker__territory-list';
    for (const territory of territories) {
      list.appendChild(buildTerritoryOverviewRow(territory));
    }
    _results.appendChild(list);
  }

  function buildTerritoryOverviewRow(territory) {
    const rows = modesForTerritory(territory.id);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'analysis-picker__territory-card';
    btn.dataset.territory = territory.id;

    const titleRow = document.createElement('div');
    titleRow.className = 'analysis-picker__row-title-row';

    const title = document.createElement('div');
    title.className = 'analysis-picker__row-title';
    title.textContent = territory.name;
    titleRow.appendChild(title);

    const badge = document.createElement('span');
    badge.className = 'analysis-picker__badge';
    badge.textContent = `${territory.count}`;
    titleRow.appendChild(badge);
    btn.appendChild(titleRow);

    const examples = rows.slice(0, 3)
      .map(mode => mode.display_name || mode.id)
      .join(', ');
    const desc = document.createElement('div');
    desc.className = 'analysis-picker__row-desc';
    desc.textContent = examples;
    btn.appendChild(desc);

    btn.addEventListener('click', () => {
      _activeTerritory = territory.id;
      if (_search) _search.value = '';
      render('');
    });
    return btn;
  }

  function buildRow(mode, showTerritory) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'analysis-picker__row';
    btn.dataset.modeId = mode.id;
    const selected = selectedMode();
    if (selected && selected.id === mode.id) {
      btn.classList.add('is-selected');
    }

    const titleRow = document.createElement('div');
    titleRow.className = 'analysis-picker__row-title-row';

    const title = document.createElement('div');
    title.className = 'analysis-picker__row-title';
    title.textContent = mode.display_name || mode.id;
    titleRow.appendChild(title);

    if (showTerritory && mode.territory_name) {
      const badge = document.createElement('span');
      badge.className = 'analysis-picker__badge';
      badge.textContent = mode.territory_name;
      titleRow.appendChild(badge);
    }
    btn.appendChild(titleRow);

    const desc = document.createElement('div');
    desc.className = 'analysis-picker__row-desc';
    desc.textContent = mode.display_description || mode.educational_name || '';
    btn.appendChild(desc);

    btn.addEventListener('click', () => commitModeSelection(mode));
    return btn;
  }

  function renderError(message) {
    if (!_territories || !_results) return;
    _territories.innerHTML = '';
    _results.innerHTML = '';
    const empty = document.createElement('div');
    empty.className = 'analysis-picker__empty';
    empty.textContent = message;
    _results.appendChild(empty);
  }

  function renderLensStep(mode) {
    if (!_territories || !_results || !mode) return;
    _lensStepModeId = mode.id;
    _activeTerritory = mode.territory || OVERVIEW_TERRITORY;
    renderTerritories('');
    _results.innerHTML = '';

    const lenses = lensesForMode(mode);
    const header = document.createElement('div');
    header.className = 'analysis-picker__results-header';
    const h = document.createElement('div');
    h.className = 'analysis-picker__results-title';
    h.textContent = mode.display_name || mode.id;
    header.appendChild(h);
    const count = document.createElement('div');
    count.className = 'analysis-picker__results-count';
    count.textContent = `${lenses.length} lenses`;
    header.appendChild(count);
    _results.appendChild(header);

    const selected = document.createElement('div');
    selected.className = 'analysis-picker__selected-card';
    const selectedTitle = document.createElement('div');
    selectedTitle.className = 'analysis-picker__selected-title';
    selectedTitle.textContent = 'Analysis selected';
    selected.appendChild(selectedTitle);
    const selectedDesc = document.createElement('div');
    selectedDesc.className = 'analysis-picker__row-desc';
    selectedDesc.textContent = mode.display_description || mode.educational_name || '';
    selected.appendChild(selectedDesc);
    _results.appendChild(selected);

    const actions = document.createElement('div');
    actions.className = 'analysis-picker__lens-actions';
    const currentLens = selectedLens();
    if (currentLens) {
      actions.appendChild(buildLensAction('Use without lens', () => {
        if (window.OraInputState && typeof window.OraInputState.clearAnalysisLens === 'function') {
          window.OraInputState.clearAnalysisLens();
        }
        close();
      }, true));
      actions.appendChild(buildLensAction('Keep lens', () => close(), false));
    } else {
      actions.appendChild(buildLensAction('Use as-is', () => close(), true));
    }
    actions.appendChild(buildLensAction('Change analysis', () => {
      if (_search) _search.value = '';
      render('');
    }, false));
    _results.appendChild(actions);

    if (!lenses.length) return;

    for (const group of LENS_GROUPS) {
      const category = group[0];
      const label = group[1];
      const groupRows = lenses.filter(lens => lens.category === category);
      if (!groupRows.length) continue;

      const block = document.createElement('div');
      block.className = 'analysis-picker__lens-group';
      const groupLabel = document.createElement('div');
      groupLabel.className = 'analysis-picker__lens-group-label';
      groupLabel.textContent = label;
      block.appendChild(groupLabel);
      for (const lens of groupRows) {
        block.appendChild(buildLensRow(mode, lens));
      }
      _results.appendChild(block);
    }
  }

  function buildLensAction(label, onClick, primary) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'analysis-picker__lens-action';
    if (primary) btn.classList.add('is-primary');
    btn.textContent = label;
    btn.addEventListener('click', onClick);
    return btn;
  }

  function buildLensRow(mode, lens) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'analysis-picker__lens-row';
    btn.dataset.lensId = lens.id;
    const current = selectedLens();
    if (current && current.id === lens.id) {
      btn.classList.add('is-selected');
    }

    const titleRow = document.createElement('div');
    titleRow.className = 'analysis-picker__row-title-row';
    const title = document.createElement('div');
    title.className = 'analysis-picker__row-title';
    title.textContent = lens.display_name || lens.id;
    titleRow.appendChild(title);
    btn.appendChild(titleRow);

    const desc = document.createElement('div');
    desc.className = 'analysis-picker__row-desc';
    desc.textContent = lens.display_description || lens.dependency_note || '';
    btn.appendChild(desc);

    btn.addEventListener('click', () => commitLensSelection(mode, lens));
    return btn;
  }

  function commitModeSelection(mode) {
    if (window.OraInputState && typeof window.OraInputState.setAnalysisMode === 'function') {
      window.OraInputState.setAnalysisMode(mode);
    }
    _activeTerritory = mode.territory || OVERVIEW_TERRITORY;
    document.dispatchEvent(new CustomEvent('ora:analysis-mode-selected', {
      detail: { mode },
    }));
    if (lensesForMode(mode).length) {
      if (_search) _search.value = '';
      renderLensStep(mode);
      return;
    }
    close();
  }

  function commitLensSelection(mode, lens) {
    if (window.OraInputState && typeof window.OraInputState.setAnalysisMode === 'function') {
      window.OraInputState.setAnalysisMode(mode);
    }
    if (window.OraInputState && typeof window.OraInputState.setAnalysisLens === 'function') {
      window.OraInputState.setAnalysisLens(lens);
    }
    document.dispatchEvent(new CustomEvent('ora:analysis-lens-selected', {
      detail: { mode, lens },
    }));
    close();
  }

  function syncToolbarState(mode) {
    if (!_btn) return;
    if (mode) _btn.classList.add('is-active');
    else _btn.classList.remove('is-active');
  }

  function init() {
    _picker = document.querySelector(PICKER_SELECTOR);
    _search = document.querySelector(SEARCH_SELECTOR);
    _territories = document.querySelector(TERRITORIES_SELECTOR);
    _results = document.querySelector(RESULTS_SELECTOR);
    _btn = document.querySelector(TOOLBAR_BTN_SELECTOR);
    if (!_picker || !_search || !_territories || !_results) {
      console.warn('[analysis-picker] DOM nodes missing; picker disabled.');
      return;
    }

    _search.addEventListener('input', () => render(_search.value));
    document.addEventListener('ora:input-toolbar:analysis', () => toggle());
    document.addEventListener('ora:analysis-mode-changed', (e) => {
      syncToolbarState(e.detail && e.detail.mode);
      if (_picker && !_picker.hidden && _lensStepModeId && !(e.detail && e.detail.mode)) {
        render('');
      }
    });
    document.addEventListener('ora:analysis-lens-changed', () => {
      if (!_picker || _picker.hidden || !_lensStepModeId) return;
      const mode = _modes.find(row => row.id === _lensStepModeId);
      if (mode) renderLensStep(mode);
    });

    if (window.OraInputState && typeof window.OraInputState.getAnalysisMode === 'function') {
      syncToolbarState(window.OraInputState.getAnalysisMode());
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.OraAnalysisPicker = { open, close, toggle };
})();
