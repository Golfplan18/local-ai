/* V3 Input Handling Phase 7 — framework setup popup.
 *
 * Renders the gap-analysis report from /api/framework/analyze-inputs as
 * a list of requirements with per-row text input + "It's on the canvas"
 * checkbox for missing/unclear items, plus a footer with Cancel /
 * Run anyway / Continue.
 *
 * Public API
 * ----------
 *   OraFrameworkSetupPopup.show(report) → Promise<UserChoice>
 *
 *     Renders the popup, awaits the user's footer action, returns:
 *
 *       {
 *         action: "continue" | "run-anyway" | "cancel",
 *         responses: { <question_name>: <text the user typed> },
 *         on_canvas: { <question_name>: true|false },
 *         missing_summary: "<comma-joined list of still-missing names>"
 *       }
 *
 *   OraFrameworkSetupPopup.close() — programmatically close, resolves the
 *   pending promise (if any) as { action: "cancel" }.
 *
 * Iteration loop ownership
 * ------------------------
 * The submit-flow code (Phase 7.E in index-v3.html) drives the loop. It
 * calls show() once, gets a UserChoice, and decides whether to re-call
 * the analyzer with the new responses or to submit. The popup itself
 * does not iterate — keeping each show() turn self-contained makes the
 * state easier to reason about.
 */
(() => {
  const POPUP_SELECTOR = '#frameworkSetupPopup';

  let _popup = null;
  let _resolver = null;  // pending Promise resolver; null when popup is closed
  let _escapeHandler = null;

  // ── Status icon glyphs ───────────────────────────────────────────────
  const STATUS_GLYPH = {
    provided: '✓',
    missing:  '!',
    unclear:  '?',
  };

  // ── Open / render ────────────────────────────────────────────────────

  function show(report) {
    return new Promise((resolve) => {
      _resolver = resolve;
      render(report);
      _popup.hidden = false;

      _escapeHandler = (e) => {
        if (e.key === 'Escape' && !_popup.hidden) {
          e.stopPropagation();
          _resolveAndClose({ action: 'cancel' });
        }
      };
      document.addEventListener('keydown', _escapeHandler, true);
    });
  }

  function close() {
    if (_resolver) _resolveAndClose({ action: 'cancel' });
  }

  function _resolveAndClose(choice) {
    if (_escapeHandler) {
      document.removeEventListener('keydown', _escapeHandler, true);
      _escapeHandler = null;
    }
    if (_popup) _popup.hidden = true;
    if (_resolver) {
      const r = _resolver;
      _resolver = null;
      r(choice);
    }
  }

  function render(report) {
    if (!_popup) return;
    _popup.innerHTML = '';

    // Header
    const header = document.createElement('div');
    header.className = 'framework-setup-popup__header';
    const titleWrap = document.createElement('div');
    const title = document.createElement('div');
    title.className = 'framework-setup-popup__title';
    title.textContent = `Framework setup: ${_displayName(report)}`;
    const subtitle = document.createElement('div');
    subtitle.className = 'framework-setup-popup__subtitle';
    subtitle.textContent = _subtitle(report);
    titleWrap.appendChild(title);
    titleWrap.appendChild(subtitle);
    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'framework-setup-popup__close';
    closeBtn.setAttribute('aria-label', 'Close popup');
    closeBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg>';
    closeBtn.addEventListener('click', () => _resolveAndClose({ action: 'cancel' }));
    header.appendChild(titleWrap);
    header.appendChild(closeBtn);
    _popup.appendChild(header);

    // Body
    const body = document.createElement('div');
    body.className = 'framework-setup-popup__body';

    if (report.error) {
      const err = document.createElement('div');
      err.className = 'framework-setup-popup__error';
      err.textContent = `Could not analyze inputs: ${report.error}`;
      body.appendChild(err);
    }

    const intro = document.createElement('div');
    intro.className = 'framework-setup-popup__intro';
    intro.textContent = _introText(report);
    body.appendChild(intro);

    const requirements = Array.isArray(report.requirements) ? report.requirements : [];
    requirements.forEach((req) => {
      body.appendChild(_buildRow(req));
    });

    if (requirements.length === 0 && !report.error) {
      const note = document.createElement('div');
      note.className = 'framework-setup-popup__intro';
      note.textContent =
        'No specific input requirements declared by this framework. ' +
        'You can run it as-is.';
      body.appendChild(note);
    }

    _popup.appendChild(body);

    // Footer
    const footer = document.createElement('div');
    footer.className = 'framework-setup-popup__footer';

    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'framework-setup-popup__btn';
    cancel.textContent = 'Cancel';
    cancel.addEventListener('click', () => _resolveAndClose({ action: 'cancel' }));

    const runAnyway = document.createElement('button');
    runAnyway.type = 'button';
    runAnyway.className = 'framework-setup-popup__btn framework-setup-popup__btn--danger';
    runAnyway.textContent = 'Run anyway';
    runAnyway.addEventListener('click', () => _resolveAndClose(_collect('run-anyway')));

    const cont = document.createElement('button');
    cont.type = 'button';
    cont.className = 'framework-setup-popup__btn framework-setup-popup__btn--primary';
    cont.textContent = 'Continue';
    cont.addEventListener('click', () => _resolveAndClose(_collect('continue')));

    footer.appendChild(cancel);
    footer.appendChild(runAnyway);
    footer.appendChild(cont);
    _popup.appendChild(footer);
  }

  function _buildRow(req) {
    const row = document.createElement('div');
    row.className = 'framework-setup-popup__row';
    row.dataset.requirementName = req.name;
    row.dataset.status          = req.status || 'unclear';

    const head = document.createElement('div');
    head.className = 'framework-setup-popup__row-head';

    const icon = document.createElement('span');
    icon.className =
      'framework-setup-popup__status-icon ' +
      `framework-setup-popup__status-icon--${req.status || 'unclear'}`;
    icon.textContent = STATUS_GLYPH[req.status] || STATUS_GLYPH.unclear;

    const name = document.createElement('span');
    name.className = 'framework-setup-popup__row-name';
    name.textContent = req.name || '(unnamed)';

    const flag = document.createElement('span');
    flag.className =
      'framework-setup-popup__row-flag ' +
      (req.required ? 'framework-setup-popup__row-flag--required' : '');
    flag.textContent = req.required ? 'Required' : 'Optional';

    head.appendChild(icon);
    head.appendChild(name);
    head.appendChild(flag);
    row.appendChild(head);

    if (req.description) {
      const desc = document.createElement('div');
      desc.className = 'framework-setup-popup__row-desc';
      desc.textContent = req.description;
      row.appendChild(desc);
    }

    if (req.evidence && req.status === 'provided') {
      const ev = document.createElement('div');
      ev.className = 'framework-setup-popup__row-evidence';
      ev.textContent = `Evidence: ${req.evidence}`;
      row.appendChild(ev);
    }

    // For missing or unclear rows, render the user-input slots:
    //   1. Free-text response (always)
    //   2. "It's on the canvas" checkbox (always)
    // Per design: BOTH may be filled. Free-text adds detail; checkbox
    // asserts that data is on the visual canvas. The submit code will
    // serialize both into the final prompt.
    if (req.status === 'missing' || req.status === 'unclear') {
      const inputWrap = document.createElement('div');
      inputWrap.className = 'framework-setup-popup__row-input';
      const ta = document.createElement('textarea');
      ta.placeholder = 'Type the missing information here…';
      ta.dataset.role = 'response-text';
      inputWrap.appendChild(ta);
      row.appendChild(inputWrap);

      const toggleLabel = document.createElement('label');
      toggleLabel.className = 'framework-setup-popup__canvas-toggle';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.dataset.role = 'response-canvas';
      const span = document.createElement('span');
      span.textContent = "It's on the canvas";
      toggleLabel.appendChild(cb);
      toggleLabel.appendChild(span);
      row.appendChild(toggleLabel);
    }

    return row;
  }

  function _collect(action) {
    const responses = {};
    const onCanvas  = {};
    const stillMissing = [];

    _popup.querySelectorAll('.framework-setup-popup__row').forEach(row => {
      const name = row.dataset.requirementName;
      const status = row.dataset.status;
      const ta = row.querySelector('textarea[data-role="response-text"]');
      const cb = row.querySelector('input[type="checkbox"][data-role="response-canvas"]');
      const text = ta ? ta.value.trim() : '';
      const canvas = cb ? cb.checked : false;
      if (text) responses[name] = text;
      if (canvas) onCanvas[name] = true;
      // Track which were already missing/unclear AND not addressed in this round.
      if ((status === 'missing' || status === 'unclear') && !text && !canvas) {
        stillMissing.push(name);
      }
    });

    return {
      action,
      responses,
      on_canvas: onCanvas,
      missing_summary: stillMissing.join(', '),
    };
  }

  // ── Helpers ──────────────────────────────────────────────────────────

  function _displayName(report) {
    // The framework display name lives on OraInputState; the report only
    // carries framework_id. Look it up from current state for display.
    if (window.OraInputState) {
      const fw = window.OraInputState.getFramework();
      if (fw && fw.display_name) return fw.display_name;
    }
    return report.framework_id || 'Unknown';
  }

  function _subtitle(report) {
    const reqs = Array.isArray(report.requirements) ? report.requirements : [];
    const provided = reqs.filter(r => r.status === 'provided').length;
    const missing  = reqs.filter(r => r.status === 'missing').length;
    const unclear  = reqs.filter(r => r.status === 'unclear').length;
    const parts = [];
    if (provided) parts.push(`${provided} provided`);
    if (missing)  parts.push(`${missing} missing`);
    if (unclear)  parts.push(`${unclear} unclear`);
    return parts.length ? parts.join(' · ') : '';
  }

  function _introText(report) {
    const reqs = Array.isArray(report.requirements) ? report.requirements : [];
    const gaps = reqs.filter(r => r.status === 'missing' || r.status === 'unclear');
    if (gaps.length === 0) {
      return 'All declared inputs look covered. Click Continue to run the framework.';
    }
    if (gaps.length === 1) {
      return 'One input still needs attention. Provide it below, mark it as on the canvas, ' +
             'or click Run anyway to proceed and let the framework caveat the gap.';
    }
    return `${gaps.length} inputs still need attention. Provide them below, mark any that ` +
           'are on the canvas, or click Run anyway to proceed and let the framework caveat the gaps.';
  }

  // ── Boot ─────────────────────────────────────────────────────────────

  function init() {
    _popup = document.querySelector(POPUP_SELECTOR);
    if (!_popup) {
      console.warn('[framework-setup-popup] DOM container missing; popup disabled.');
      return;
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.OraFrameworkSetupPopup = { show, close };
})();
