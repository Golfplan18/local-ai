/* Honne/tatemae audience toggle — G1.36 (§1.4).
 *
 * A two-state input-toolbar toggle that marks the NEXT turn(s) as internal
 * (Ora talks to you — the project's interaction style) vs external (a
 * deliverable that reads for the world — the project's output style, the
 * default). Sticky across turns until changed. The submit flow reads
 * window.OraStyleAudience.get(); the server folds an "internal" turn onto the
 * per-turn style override (server._apply_style_audience).
 */
(() => {
  const KEY = 'ora-style-audience';
  let state = 'external';
  try { if (localStorage.getItem(KEY) === 'internal') state = 'internal'; } catch (e) {}
  let btn = null;

  const apply = () => {
    if (!btn) return;
    const internal = state === 'internal';
    btn.setAttribute('aria-pressed', internal ? 'true' : 'false');
    btn.setAttribute('aria-label',
      internal ? 'Audience: internal (interaction style)' : 'Audience: external (deliverable)');
    btn.title = internal
      ? 'Internal — Ora talks to you (this project\'s interaction style). Click for External.'
      : 'External — reads for the world (this project\'s output style). Click for Internal.';
    btn.classList.toggle('is-audience-internal', internal);
  };

  const set = (v) => {
    state = (v === 'internal') ? 'internal' : 'external';
    try { localStorage.setItem(KEY, state); } catch (e) {}
    apply();
  };
  const toggle = () => set(state === 'internal' ? 'external' : 'internal');

  const mount = () => {
    btn = document.getElementById('inputToolbarAudience');
    if (!btn) return;
    btn.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); toggle(); });
    apply();
  };

  window.OraStyleAudience = { get: () => state, set, toggle };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
})();
