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
  const URL_CACHE_KEY = 'ora-active-theme-css-url';
  const STYLE_ID    = 'ora-loaded-theme';

  const getActive = () => localStorage.getItem(STORAGE_KEY) || 'default';
  const getActiveCachedUrl = () => localStorage.getItem(URL_CACHE_KEY) || null;
  const getThemeInfo = (themeId) => themesIndex[themeId] || null;

  // In-memory cache of the last /api/v3-themes/list response, indexed
  // by theme id. Populated on init() and refreshed whenever
  // listInstalled() is called. Used by applyTheme to find the right
  // theme.css URL when the caller doesn't pass one explicitly (e.g.,
  // theme restore on page load).
  let themesIndex = {};

  // Ensure the user-customizations stylesheet stays after the loaded theme
  // so user overrides win over both base CSS and active theme variables.
  const reorderUserCustomizations = () => {
    const userStyle = document.getElementById('ora-user-customizations');
    if (userStyle) document.head.appendChild(userStyle);
  };

  // Resolve the theme.css URL for a given id. Priority:
  //  1. Explicit themeCssUrl argument (from a list response entry).
  //  2. In-memory index from the last list fetch.
  //  3. localStorage cache from the previous active-theme apply.
  //  4. Legacy fallback: /static/themes/<id>/theme.css (core themes).
  // Project themes per Plugin Convention §13 serve from
  // /themes/project/<nexus>/theme.css; that URL must come through (1)
  // or (2) — the legacy fallback only resolves to core themes.
  const resolveThemeCssUrl = (themeId, themeCssUrl) => {
    if (themeCssUrl) return themeCssUrl;
    const indexed = themesIndex[themeId];
    if (indexed && indexed.theme_css_url) return indexed.theme_css_url;
    return `/static/themes/${themeId}/theme.css`;
  };

  const applyTheme = async (themeId, themeCssUrl) => {
    const existing = document.getElementById(STYLE_ID);
    if (existing) existing.remove();

    if (!themeId || themeId === 'default') {
      localStorage.setItem(STORAGE_KEY, 'default');
      localStorage.removeItem(URL_CACHE_KEY);
      reorderUserCustomizations();
      document.dispatchEvent(new CustomEvent('ora-theme-changed', { detail: { themeId: 'default' } }));
      return { ok: true, id: 'default' };
    }

    try {
      const url = resolveThemeCssUrl(themeId, themeCssUrl);
      const cssResp = await fetch(url);
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
      // Cache the resolved URL so page-load restore works without a
      // list-API roundtrip. Required for project themes whose URL
      // doesn't match the legacy /static/themes/<id>/ pattern.
      localStorage.setItem(URL_CACHE_KEY, resolveThemeCssUrl(themeId, themeCssUrl));
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
    const data = await resp.json();
    // Refresh the in-memory index so subsequent applyTheme calls have
    // the right theme_css_url available without re-fetching.
    themesIndex = {};
    for (const entry of (data && data.themes) || []) {
      if (entry && entry.id) themesIndex[entry.id] = entry;
    }
    return data;
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

  const installFromZip = async (file, name) => {
    const form = new FormData();
    form.append('file', file);
    if (name) form.append('name', name);
    const resp = await fetch('/api/v3-themes/install-zip', {
      method: 'POST',
      body: form,
    });
    return await resp.json();
  };

  const duplicateTheme = async (themeId, name, customizations) => {
    const resp = await fetch(`/api/v3-themes/${themeId}/duplicate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, customizations: customizations || {} }),
    });
    const result = await resp.json();
    if (result && result.ok && result.id) {
      themesIndex[result.id] = {
        id: result.id,
        name: result.name,
        directory: result.id,
        bundled: false,
        theme_css_url: result.theme_css_url || `/static/themes/${result.id}/theme.css`,
      };
    }
    return result;
  };

  const saveCustomizations = async (themeId, customizations) => {
    const resp = await fetch(`/api/v3-themes/${themeId}/save-customizations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ customizations: customizations || {} }),
    });
    return await resp.json();
  };

  const exportTheme = (themeId) => {
    window.location.href = `/api/v3-themes/${themeId}/export`;
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

  // Restore active theme on load (if not default — default is always present).
  // Uses the URL-cache to avoid an API roundtrip when the URL is already
  // known from the previous apply. Falls through to the legacy
  // /static/themes/<id>/theme.css path for core themes that haven't
  // been applied via the cache-aware path yet (backward compat for
  // existing local-storage entries written by older versions).
  const init = () => {
    const id = getActive();
    if (id && id !== 'default') {
      const cachedUrl = getActiveCachedUrl();
      applyTheme(id, cachedUrl);
    }
  };
  init();

  window.OraThemeLoader = {
    getActive,
    getThemeInfo,
    applyTheme,
    listInstalled,
    installFromGitHub,
    installFromCSS,
    installFromZip,
    duplicateTheme,
    saveCustomizations,
    exportTheme,
    deleteTheme,
    fetchCommunityDirectory,
    fetchCommunityStats,
  };
})();
