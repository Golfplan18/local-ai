/* V3 Input Handling Phase 4 — framework picker dropdown.
 *
 * Listens for `ora:input-toolbar:framework` (emitted by the input-pane
 * toolbar's framework button), opens a picker overlay anchored to the top
 * of the output pane, and renders rows fetched from
 * GET /api/frameworks/picker. Search-as-you-type filters in place. On row
 * click the picker commits the framework via OraInputState.setFramework
 * and closes itself. Outside-click and Escape close without committing.
 *
 * Analysis/mode selection now lives in analysis-picker.js as a separate
 * button and surface. Opening either picker closes the other; committing a
 * framework clears any staged analysis mode through OraInputState.
 */
(() => {
  const PICKER_SELECTOR = '#frameworkPicker';
  const SEARCH_SELECTOR = '#frameworkPickerSearch';
  const LIST_SELECTOR   = '#frameworkPickerList';
  const TOOLBAR_BTN_SELECTOR = '#inputToolbarFramework';

  let _picker = null;
  let _list   = null;
  let _search = null;
  let _btn    = null;
  let _frameworks = [];
  let _outsideHandler = null;
  let _escapeHandler  = null;
  let _home = null;
  let _homeNext = null;

  function placeForCurrentLayout() {
    const collapsed = document.querySelector('.left-column')?.classList.contains('collapsed');
    if (!collapsed) {
      if (_home && _picker.parentNode !== _home) {
        _home.insertBefore(_picker, _homeNext && _homeNext.parentNode === _home ? _homeNext : null);
      }
      _picker.removeAttribute('style');
      return;
    }
    const anchor = _btn && _btn.getBoundingClientRect();
    document.body.appendChild(_picker);
    const left = Math.max(16, Math.round((anchor && anchor.right || 0) + 10));
    Object.assign(_picker.style, {
      position: 'fixed',
      top: '16px',
      left: `${left}px`,
      right: 'auto',
      width: `min(520px, calc(100vw - ${left + 16}px))`,
      maxHeight: 'calc(100vh - 32px)',
      zIndex: '10060',
    });
  }

  function restoreHome() {
    if (!_home || _picker.parentNode === _home) return;
    _home.insertBefore(_picker, _homeNext && _homeNext.parentNode === _home ? _homeNext : null);
    _picker.removeAttribute('style');
  }

  // ── Open / close ────────────────────────────────────────────────────

  function open() {
    if (!_picker) return;
    if (window.OraAnalysisPicker && typeof window.OraAnalysisPicker.close === 'function') {
      window.OraAnalysisPicker.close();
    }
    placeForCurrentLayout();
    _picker.hidden = false;
    if (_btn) _btn.setAttribute('aria-expanded', 'true');

    // Fetch rows fresh on every open — frameworks can change as the user
    // installs / authors / generates them. Cheap call: it's a directory
    // scan of frameworks/book/.
    fetch('/api/frameworks/picker')
      .then(res => res.ok ? res.json() : { frameworks: [] })
      .then(payload => {
        _frameworks = Array.isArray(payload && payload.frameworks)
          ? payload.frameworks : [];
        render(_frameworks, '');
      })
      .catch(err => {
        console.warn('[framework-picker] fetch failed:', err);
        _list.innerHTML = '';
        const empty = document.createElement('div');
        empty.className = 'framework-picker__empty';
        empty.textContent = 'Could not load frameworks. Check the server log.';
        _list.appendChild(empty);
      });

    if (_search) {
      _search.value = '';
      // Defer focus so the click that opened us doesn't immediately blur.
      setTimeout(() => { try { _search.focus(); } catch (_) {} }, 0);
    }

    _outsideHandler = (e) => {
      if (_picker.hidden) return;
      const t = e.target;
      if (_picker.contains(t) || (_btn && _btn.contains(t))) return;
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
    restoreHome();
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

  // ── Render ──────────────────────────────────────────────────────────

  function render(rows, query) {
    if (!_list) return;
    _list.innerHTML = '';
    const q = (query || '').trim().toLowerCase();
    const filtered = q
      ? rows.filter(r =>
          (r.display_name || '').toLowerCase().includes(q) ||
          (r.display_description || '').toLowerCase().includes(q))
      : rows;

    if (filtered.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'framework-picker__empty';
      empty.textContent = q
        ? `No frameworks match "${query}".`
        : 'No frameworks available.';
      _list.appendChild(empty);
      return;
    }

    for (const row of filtered) _list.appendChild(buildRow(row));
  }

  function buildRow(framework) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'framework-picker__row';
    btn.dataset.frameworkId = framework.id;

    const body = document.createElement('div');
    body.className = 'framework-picker__row-body';

    const title = document.createElement('div');
    title.className = 'framework-picker__row-title';
    title.textContent = framework.display_name || framework.id;
    body.appendChild(title);

    const desc = document.createElement('div');
    desc.className = 'framework-picker__row-desc';
    desc.textContent = framework.display_description || '';
    body.appendChild(desc);

    btn.appendChild(body);

    btn.addEventListener('click', () => {
      commitSelection(framework);
    });

    return btn;
  }

  function commitSelection(framework) {
    if (window.OraInputState && typeof window.OraInputState.setFramework === 'function') {
      window.OraInputState.setFramework(framework);
    }
    document.dispatchEvent(new CustomEvent('ora:framework-selected', {
      detail: { framework },
    }));
    close();
  }

  // ── Toolbar button .is-active state ──────────────────────────────────

  function syncToolbarState(framework) {
    if (!_btn) return;
    if (framework) _btn.classList.add('is-active');
    else _btn.classList.remove('is-active');
  }

  // ── Boot ─────────────────────────────────────────────────────────────

  function init() {
    _picker = document.querySelector(PICKER_SELECTOR);
    _search = document.querySelector(SEARCH_SELECTOR);
    _list   = document.querySelector(LIST_SELECTOR);
    _btn    = document.querySelector(TOOLBAR_BTN_SELECTOR);
    if (!_picker || !_search || !_list) {
      console.warn('[framework-picker] DOM nodes missing; picker disabled.');
      return;
    }
    _home = _picker.parentNode;
    _homeNext = _picker.nextSibling;

    _search.addEventListener('input', () => {
      render(_frameworks, _search.value);
    });

    document.addEventListener('ora:input-toolbar:framework', () => {
      toggle();
    });

    // Reflect external state changes (e.g., bridge label or future code
    // clearing the framework on submit) back onto the toolbar button.
    document.addEventListener('ora:framework-changed', (e) => {
      syncToolbarState(e.detail && e.detail.framework);
    });

    // Initial state sync — in case the page loads with a framework
    // already set in OraInputState (it never does today, but cheap to
    // be correct).
    if (window.OraInputState && typeof window.OraInputState.getFramework === 'function') {
      syncToolbarState(window.OraInputState.getFramework());
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Tiny public surface for tests / external callers (Phase 5 bridge,
  // Phase 7 setup popup).
  window.OraFrameworkPicker = { open, close, toggle };
})();
