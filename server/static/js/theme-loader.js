// Ora Theme Loader
//
// Loads and applies installed themes on top of ora-default.css.
// Cascade order maintained:
//   ora-default.css → loaded theme (#ora-loaded-theme) → user customizations (#ora-user-customizations)
//
// Active theme persisted in localStorage as 'ora-active-theme' (theme id).
// On page load, the previously active theme is restored if not 'default'.
//
// Exposed at window.OraThemeLoader for in-page wiring.

(() => {
  const STORAGE_KEY = 'ora-active-theme';
  const STYLE_ID    = 'ora-loaded-theme';

  const getActive = () => localStorage.getItem(STORAGE_KEY) || 'default';

  // Ensure the user-customizations stylesheet stays after the loaded theme
  // so user overrides win over both base CSS and active theme variables.
  const reorderUserCustomizations = () => {
    const userStyle = document.getElementById('ora-user-customizations');
    if (userStyle) document.head.appendChild(userStyle);
  };

  const applyTheme = async (themeId) => {
    const existing = document.getElementById(STYLE_ID);
    if (existing) existing.remove();

    if (!themeId || themeId === 'default') {
      localStorage.setItem(STORAGE_KEY, 'default');
      reorderUserCustomizations();
      document.dispatchEvent(new CustomEvent('ora-theme-changed', { detail: { themeId: 'default' } }));
      return { ok: true, id: 'default' };
    }

    try {
      const cssResp = await fetch(`/static/themes/${themeId}/theme.css`);
      if (!cssResp.ok) throw new Error(`HTTP ${cssResp.status} loading '${themeId}'`);
      const css = await cssResp.text();

      const style = document.createElement('style');
      style.id = STYLE_ID;
      style.dataset.themeId = themeId;
      style.textContent = css;

      const base = document.querySelector('link[href*="ora-default.css"]');
      if (base && base.parentNode) {
        base.parentNode.insertBefore(style, base.nextSibling);
      } else {
        document.head.appendChild(style);
      }

      localStorage.setItem(STORAGE_KEY, themeId);
      reorderUserCustomizations();
      document.dispatchEvent(new CustomEvent('ora-theme-changed', { detail: { themeId } }));
      return { ok: true, id: themeId };
    } catch (e) {
      console.error('[Ora] applyTheme failed:', e);
      return { ok: false, error: e.message };
    }
  };

  const listInstalled = async () => {
    const resp = await fetch('/api/v3-themes/list');
    if (!resp.ok) throw new Error('Failed to list themes');
    return await resp.json();
  };

  // installFromGitHub accepts an optional `fallback` manifest (used by the
  // browse view to supply name/author/modes when the repo lacks manifest.json).
  const installFromGitHub = async (repo, fallback) => {
    const resp = await fetch('/api/v3-themes/install-from-github', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo, fallback: fallback || null }),
    });
    return await resp.json();
  };

  const installFromCSS = async (name, css, manifest) => {
    const resp = await fetch('/api/v3-themes/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, css, manifest: manifest || { name, version: '1.0.0' } }),
    });
    return await resp.json();
  };

  const deleteTheme = async (themeId) => {
    if (themeId === 'default') throw new Error('Cannot delete default');
    const resp = await fetch(`/api/v3-themes/${themeId}`, { method: 'DELETE' });
    return await resp.json();
  };

  const fetchCommunityDirectory = async () => {
    const resp = await fetch('/api/v3-themes/community-directory');
    if (!resp.ok) {
      const errBody = await resp.text();
      throw new Error(`Directory fetch failed: ${errBody.slice(0, 100)}`);
    }
    return await resp.json();
  };

  // Fetch download stats for sorting. Returns {} on failure so the caller
  // can fall back to directory order without breaking.
  const fetchCommunityStats = async () => {
    try {
      const resp = await fetch('/api/v3-themes/community-stats');
      if (!resp.ok) return {};
      return await resp.json();
    } catch {
      return {};
    }
  };

  // Restore active theme on load (if not default — default is always present)
  const init = () => {
    const id = getActive();
    if (id && id !== 'default') applyTheme(id);
  };
  init();

  window.OraThemeLoader = {
    getActive,
    applyTheme,
    listInstalled,
    installFromGitHub,
    installFromCSS,
    deleteTheme,
    fetchCommunityDirectory,
    fetchCommunityStats,
  };
})();
