/* Honne/tatemae audience toggle — G1.36 (§1.4).
 *
 * A two-state input-toolbar toggle that marks the NEXT turn(s) as internal
 * (Ora talks to you — the project's interaction style, the default) vs
 * external (a one-turn deliverable that reads for the world — the project's
 * output style). The override applies to one accepted turn. The submit flow reads
 * window.OraStyleAudience.get(); the server folds an "internal" turn onto the
 * per-turn style override (server._apply_style_audience). It resets only
 * after the server accepts the turn; a failed request leaves the override.
 */
(() => {
  const defaultAudience = 'internal';
  let state = defaultAudience;
  let revision = 0;
  let btn = null;

  const apply = () => {
    if (!btn) return;
    const internal = state === 'internal';
    const overridden = state !== defaultAudience;
    const stateLabel = btn.querySelector('.input-pane-toolbar__state-label');
    btn.setAttribute('aria-pressed', overridden ? 'true' : 'false');
    btn.setAttribute('aria-label',
      internal ? 'Audience: In (project default)' : 'Audience override: Out (external deliverable)');
    btn.title = internal
      ? 'Audience: In — project interaction style'
      : 'Audience override: Out — project output style for this turn';
    if (stateLabel) stateLabel.textContent = internal ? 'In' : 'Out';
    btn.classList.toggle('is-audience-internal', internal);
    btn.classList.toggle('is-active', overridden);
  };

  const set = (v) => {
    const next = (v === 'internal') ? 'internal' : 'external';
    if (next !== state) revision += 1;
    state = next;
    apply();
  };
  const toggle = () => set(state === 'internal' ? 'external' : 'internal');

  const reserveSubmission = (snapshot) => {
    if (!snapshot || snapshot.revision !== revision || snapshot.value !== state) return null;
    const token = { value: state, revision };
    state = defaultAudience;
    revision += 1;
    token.reservedRevision = revision;
    apply();
    return token;
  };

  const restoreSubmission = (token) => {
    if (!token || token.reservedRevision !== revision || state !== defaultAudience) return false;
    state = token.value;
    revision += 1;
    apply();
    return true;
  };

  const mount = () => {
    btn = document.getElementById('inputToolbarAudience');
    if (!btn) return;
    btn.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); toggle(); });
    apply();
  };

  window.OraStyleAudience = {
    get: () => state,
    snapshotForSubmission: () => ({ value: state, revision }),
    reserveSubmission,
    restoreSubmission,
    set,
    toggle,
    acknowledgeSubmission: (response, snapshot) => {
      if (!response || response.ok !== true) return false;
      if (snapshot && (snapshot.revision !== revision || snapshot.value !== state)) {
        return false;
      }
      set(defaultAudience);
      return true;
    },
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
})();
