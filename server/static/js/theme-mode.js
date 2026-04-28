// Ora theme mode switcher.
// Loaded with `defer` so it runs after the document is parsed but before
// DOMContentLoaded fires. Reads localStorage for the saved mode and applies
// it to <body>. Default is 'dark' if nothing stored.
//
// Exposed at window.OraTheme for in-page wiring and console testing:
//   OraTheme.get()         → 'dark' | 'light'
//   OraTheme.set('light')  → set + apply + persist
//   OraTheme.toggle()      → flip and persist
//   OraTheme.apply(mode)   → apply without persisting (used internally)

(() => {
  const STORAGE_KEY = 'ora-theme-mode';

  const apply = (mode) => {
    const body = document.body;
    if (!body) return;
    body.classList.remove('theme-dark', 'theme-light');
    body.classList.add(mode === 'light' ? 'theme-light' : 'theme-dark');
  };

  const get = () => localStorage.getItem(STORAGE_KEY) || 'dark';

  const set = (mode) => {
    localStorage.setItem(STORAGE_KEY, mode);
    apply(mode);
  };

  const toggle = () => {
    set(get() === 'dark' ? 'light' : 'dark');
  };

  // Apply on load (defer means body is ready)
  apply(get());

  window.OraTheme = { get, set, toggle, apply };
})();
