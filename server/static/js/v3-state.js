/* V3 Phase 7.3 — Layout state persistence.
 *
 * Saves the user's spatial layout to localStorage so it restores on
 * reload. Spec §9 lists the persisted fields:
 *
 *   - Spine horizontal position (--ora-left-w / --ora-right-w)
 *   - ORA logo vertical position (input-pane height)
 *   - Sidebar state: collapsed | expanded | locked, plus width if resizable
 *   - Pane collapsed-or-not states + last-non-collapsed widths
 *   - QQB collapsed-or-not state + last height
 *   - Active conversation thread
 *
 * Theme + customizer settings are already persisted by the existing
 * theme system, so this module leaves them alone.
 *
 * Operating contract:
 *   - Save is debounced 500ms after any state-changing event
 *   - Save also fires on beforeunload (synchronous, captures last state)
 *   - Restore happens on DOMContentLoaded after layout JS has set up the
 *     DOM but before the user has had a chance to interact
 *   - If localStorage parsing fails or the saved schema doesn't match,
 *     the module silently falls back to defaults — never blocks startup
 */
(() => {
  const STORAGE_KEY    = 'ora-v3-layout-state';
  const SCHEMA_VERSION = 1;
  const SAVE_DEBOUNCE  = 500;  // ms

  // ── Snapshot ───────────────────────────────────────────────────────────
  const captureState = () => {
    const shell    = document.querySelector('.ora-shell');
    const sidebar  = document.querySelector('.left-sidebar');
    const inputPane = document.querySelector('.input-pane');
    const chatZone = document.querySelector('.chat-zone');

    const layoutState = (window.OraLayout && window.OraLayout.state) ? window.OraLayout.state() : {};
    const sidebarState = (window.OraSidebar && window.OraSidebar.getState) ? window.OraSidebar.getState() : null;

    return {
      schemaVersion: SCHEMA_VERSION,
      capturedAt:    new Date().toISOString(),

      // Column widths (from CSS variables; fall back to live measurements
      // if the variables haven't been set yet).
      leftW:  shell ? (shell.style.getPropertyValue('--ora-left-w')  || '').trim() : '',
      rightW: shell ? (shell.style.getPropertyValue('--ora-right-w') || '').trim() : '',

      // Vertical split — input-pane height (drives bridge + wordmark Y).
      inputPaneH: inputPane ? inputPane.style.height || '' : '',

      // Sidebar state
      sidebarExpanded: sidebar ? sidebar.classList.contains('expanded') : false,
      sidebarLocked:   sidebar ? sidebar.classList.contains('locked')   : false,

      // Pane collapse state — pulled from OraLayout.state()
      leftCollapsed:        !!layoutState.leftCollapsed,
      leftCollapsedBy:      layoutState.leftCollapsedBy || null,
      leftLastUncollapsedW: layoutState.leftLastUncollapsedW || null,
      rightCollapsed:        !!layoutState.rightCollapsed,
      rightCollapsedBy:      layoutState.rightCollapsedBy || null,
      rightLastUncollapsedW: layoutState.rightLastUncollapsedW || null,

      // QQB collapse state
      qqbCollapsed:        !!layoutState.qqbCollapsed,
      qqbCollapsedBy:      layoutState.qqbCollapsedBy || null,
      qqbLastUncollapsedH: layoutState.qqbLastUncollapsedH || null,

      // Active conversation
      activeConversationId: (window.OraSidebar && window.OraSidebar.getActiveConversation)
        ? window.OraSidebar.getActiveConversation()
        : null,

      // Sidebar passthrough (whatever sidebar exposes — kept opaque)
      sidebarRaw: sidebarState,
    };
  };

  // ── Persist ────────────────────────────────────────────────────────────
  const save = () => {
    try {
      const snap = captureState();
      localStorage.setItem(STORAGE_KEY, JSON.stringify(snap));
    } catch (e) {
      // Quota exceeded, private mode, etc. — non-fatal.
    }
  };

  let saveTimer = null;
  const queueSave = () => {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(save, SAVE_DEBOUNCE);
  };

  // ── Restore ────────────────────────────────────────────────────────────
  const loadState = () => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      const data = JSON.parse(raw);
      if (data.schemaVersion !== SCHEMA_VERSION) return null;
      return data;
    } catch (e) {
      return null;
    }
  };

  const applyState = (state) => {
    if (!state) return;
    const shell     = document.querySelector('.ora-shell');
    const sidebar   = document.querySelector('.left-sidebar');
    const inputPane = document.querySelector('.input-pane');
    const chatZone  = document.querySelector('.chat-zone');

    if (shell) {
      // Migration: pre-2026-05-04 layouts persisted column widths in pixels.
      // Once the window resizes, fixed-pixel columns leave dead space in the
      // sidebar's auto-track. New writes use `fr` ratios; old `px` values are
      // converted to fr at load time so existing users don't see dead space.
      const toFr = (val) => {
        if (!val) return val;
        const m = String(val).match(/^([\d.]+)\s*px\s*$/);
        if (!m) return val;
        return parseFloat(m[1]);  // returned as raw number, paired below
      };
      const leftPx  = toFr(state.leftW);
      const rightPx = toFr(state.rightW);
      if (typeof leftPx === 'number' && typeof rightPx === 'number') {
        const sum = leftPx + rightPx;
        if (sum > 0) {
          shell.style.setProperty('--ora-left-w',  ((leftPx  / sum) * 2).toFixed(4) + 'fr');
          shell.style.setProperty('--ora-right-w', ((rightPx / sum) * 2).toFixed(4) + 'fr');
        }
      } else {
        if (state.leftW)  shell.style.setProperty('--ora-left-w',  state.leftW);
        if (state.rightW) shell.style.setProperty('--ora-right-w', state.rightW);
      }
    }

    if (inputPane && state.inputPaneH) {
      inputPane.style.height = state.inputPaneH;
      // The existing inline script's setMainHeight wires chat-zone too,
      // but we don't have setMainHeight in scope here. Fire a resize so
      // the wordmark/bridge realign on the next animation frame.
      window.dispatchEvent(new Event('resize'));
    }

    if (sidebar) {
      if (state.sidebarExpanded) {
        sidebar.classList.add('expanded');
        document.body.classList.add('sidebar-expanded');
      }
      if (state.sidebarLocked) sidebar.classList.add('locked');
    }

    // Pane collapse — replay through OraLayout's API so the internal
    // bookkeeping (collapsedBy, last widths) is consistent.
    if (state.leftCollapsed && window.OraLayout) {
      window.OraLayout.collapseLeft();
    }
    if (state.rightCollapsed && window.OraLayout) {
      window.OraLayout.collapseRight();
    }
    if (state.qqbCollapsed && window.OraLayout) {
      window.OraLayout.collapseQQB();
    }

    // Active conversation: re-fire the selection event if there's a sidebar
    // listener that handles re-loading.
    if (state.activeConversationId) {
      document.dispatchEvent(new CustomEvent('ora:conversation-selected', {
        detail: {
          conversation_id: state.activeConversationId,
          tag: '',  // we don't restore tag here; the sidebar will re-fetch
          source: 'state-restore',
        },
      }));
    }
  };

  // ── Triggers ───────────────────────────────────────────────────────────
  // Save on any mouseup that follows a drag (event-horizon committed).
  document.addEventListener('mouseup', queueSave);

  // Save on sidebar / mode / collapse / bootstrap events fired by sibling modules.
  ['ora:sidebar-state-changed',
   'ora:conversation-selected',
   'ora:thread-bootstrapped'].forEach(name => {
    document.addEventListener(name, queueSave);
  });

  // Save synchronously before unload as a final safety net.
  window.addEventListener('beforeunload', save);

  // ── Restore on load ────────────────────────────────────────────────────
  // Wait one tick after DOMContentLoaded so v3-layout, sidebar, and the
  // inline script have all initialized. Restoring before they exist
  // would clobber the initial state with a no-op apply.
  const init = () => {
    setTimeout(() => {
      const saved = loadState();
      applyState(saved);
    }, 0);
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Public API for tests + manual reset
  window.OraState = {
    save,
    load:  loadState,
    apply: applyState,
    capture: captureState,
    clear: () => {
      try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
    },
  };
})();
