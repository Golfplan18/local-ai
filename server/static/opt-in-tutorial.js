/* opt-in-tutorial.js — WP-7.7.3
 *
 * Plan refs: §11.16 (onboarding), §13.7 (WP-7.7.3).
 *
 * Goal
 * ────
 * On the *first* time the visual pane is opened (per browser-localStorage), surface
 * a small unobtrusive "Show me around" button anchored to the toolbar. Clicking it
 * runs a ~60-second guided walkthrough of the basics:
 *
 *   1. Toolbar / docking            (WP-7.1.2)
 *   2. Drawing                      (Phases 1-6 + WP-7.5.1)
 *   3. AI                           (WP-7.3.3a)
 *   4. Save / export                (WP-7.4.8 + WP-7.4.9)
 *
 * Each step is a non-blocking modal/tooltip with Next + Skip buttons. Skip dismisses
 * the entire tour. Completion (reaching the final Next) sets `tutorial_completed`.
 * Either flag prevents the button from appearing again.
 *
 * Foundation
 * ──────────
 * - `~/ora/server/static/visual-toolbar.js` (WP-7.1.1) — universal toolbar registry.
 * - `visual-panel.js` exposes `VisualPanel.prototype.init` which we monkey-patch in
 *   the same idiom the panel itself uses for `_active` registration (line ~4636).
 *   This keeps the wiring inside the existing init lifecycle without touching the
 *   panel source.
 *
 * Persistence keys
 * ────────────────
 * - `ora.tutorial.dismissed`   — set on Skip or on the toolbar X.
 * - `ora.tutorial.completed`   — set when the user reaches the final step.
 *   First-open detection: neither key present.
 *
 * Test criterion (from the WP brief)
 * ──────────────────────────────────
 * - First open  → button visible.
 * - Click       → walkthrough runs.
 * - Close       → button absent on reopen.
 *
 * Style
 * ─────
 * Minimal: no external CSS dependency, no framework. Inline-styled tooltip card +
 * a translucent backdrop. Pointer-events on the highlighted element are preserved
 * so the user can interact during the walk-through.
 */
(function () {
  'use strict';

  // ── Storage keys ──────────────────────────────────────────────────────────
  var KEY_DISMISSED = 'ora.tutorial.dismissed';
  var KEY_COMPLETED = 'ora.tutorial.completed';

  function _getFlag(key) {
    try { return !!window.localStorage && !!window.localStorage.getItem(key); }
    catch (_) { return false; }
  }
  function _setFlag(key) {
    try { if (window.localStorage) window.localStorage.setItem(key, '1'); }
    catch (_) { /* private mode etc. — silent */ }
  }

  function _isFirstOpen() {
    return !_getFlag(KEY_DISMISSED) && !_getFlag(KEY_COMPLETED);
  }

  // ── Step definitions ──────────────────────────────────────────────────────
  // Each step:
  //   title       — short heading
  //   body        — one-or-two sentences
  //   selector    — DOM selector relative to the panel; null = centered, no anchor
  //   wpRef       — provenance string shown in small text (debugging aid)
  var STEPS = [
    {
      title: 'Welcome to the visual pane',
      body:  'This pane is where Ora draws diagrams and where you can sketch alongside it. ' +
             'A 60-second tour, then you’re free.',
      selector: null,
      wpRef: '§11.16'
    },
    {
      title: 'Toolbar & docking',
      body:  'The toolbar lives along the edge. You can drag it to dock left, right, top, or bottom — ' +
             'or hide it entirely; it returns when you hover.',
      selector: '.visual-panel__toolbar',
      wpRef: 'WP-7.1.2'
    },
    {
      title: 'Drawing',
      body:  'Pick rectangle, ellipse, arrow, text, sticky, pen. Click to place, drag to size. ' +
             'Cmd+Z undoes; the X clears your input layer without touching Ora’s drawing.',
      selector: '.vp-tool-btn[data-tool="rect"]',
      wpRef: 'Phases 1-6 + WP-7.5.1'
    },
    {
      title: 'Ask the AI',
      body:  'Drop an image, sketch a question, or just type a prompt in chat. ' +
             'Ora reads what’s on the canvas and replies in kind — a chart, a diagram, or prose.',
      selector: '.visual-panel__viewport',
      wpRef: 'WP-7.3.3a'
    },
    {
      title: 'Save & export',
      body:  'Cmd+S saves the canvas (autosave runs every 30 s in the background). ' +
             'Export gives you SVG / PNG / canvas-file for sharing.',
      selector: '.vp-tool-btn[data-tool="upload-image"]',
      wpRef: 'WP-7.4.8 + WP-7.4.9'
    },
    {
      title: 'You’re set',
      body:  'That’s the basics. Re-open this tour any time from the help menu. ' +
             'Have fun.',
      selector: null,
      wpRef: '§13.7'
    }
  ];

  // ── DOM helpers ───────────────────────────────────────────────────────────
  function _el(tag, props, styles) {
    var node = document.createElement(tag);
    if (props) {
      for (var k in props) if (Object.prototype.hasOwnProperty.call(props, k)) {
        if (k === 'text') node.textContent = props[k];
        else if (k === 'html') node.innerHTML = props[k];
        else node.setAttribute(k, props[k]);
      }
    }
    if (styles) {
      for (var s in styles) if (Object.prototype.hasOwnProperty.call(styles, s)) {
        node.style[s] = styles[s];
      }
    }
    return node;
  }

  function _findInPanel(panelEl, selector) {
    if (!selector || !panelEl) return null;
    try { return panelEl.querySelector(selector); } catch (_) { return null; }
  }

  // ── "Show me around" launcher button ──────────────────────────────────────
  function _renderLauncher(panelEl, onLaunch, onClose) {
    var btn = _el('button', {
      type: 'button',
      'class': 'ora-tutorial-launcher',
      'aria-label': 'Show me around',
      title: 'Show me around'
    }, {
      position:        'absolute',
      top:             '8px',
      right:           '8px',
      zIndex:          '90',
      padding:         '6px 10px 6px 10px',
      borderRadius:    '14px',
      border:          '1px solid rgba(189, 147, 249, 0.55)',
      background:      'rgba(40, 42, 54, 0.92)',
      color:           '#f8f8f2',
      font:            '500 12px/1.2 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
      letterSpacing:   '0.01em',
      cursor:          'pointer',
      boxShadow:       '0 2px 6px rgba(0, 0, 0, 0.35)',
      display:         'inline-flex',
      alignItems:      'center',
      gap:             '6px'
    });
    btn.innerHTML =
      '<span aria-hidden="true">✨</span>' +
      '<span class="ora-tutorial-launcher__label">Show me around</span>' +
      '<span class="ora-tutorial-launcher__close" aria-label="Dismiss" ' +
      'style="opacity:0.65;margin-left:4px;font-size:14px;line-height:1;">×</span>';

    btn.addEventListener('click', function (e) {
      var closeHit = e.target && e.target.classList &&
                     e.target.classList.contains('ora-tutorial-launcher__close');
      if (closeHit) {
        e.stopPropagation();
        onClose();
        return;
      }
      onLaunch();
    });
    panelEl.appendChild(btn);
    return btn;
  }

  // ── Tooltip card + backdrop ───────────────────────────────────────────────
  function _renderBackdrop() {
    var b = _el('div', { 'class': 'ora-tutorial-backdrop', role: 'presentation' }, {
      position:       'fixed',
      inset:          '0',
      zIndex:         '9998',
      background:     'rgba(15, 16, 22, 0.42)',
      pointerEvents:  'none'                       // never block panel input
    });
    document.body.appendChild(b);
    return b;
  }

  function _renderCard(stepIndex, total, step) {
    var card = _el('div', {
      'class': 'ora-tutorial-card',
      role: 'dialog',
      'aria-modal': 'false',
      'aria-labelledby': 'ora-tutorial-title',
      'aria-describedby': 'ora-tutorial-body'
    }, {
      position:       'fixed',
      zIndex:         '9999',
      maxWidth:       '320px',
      minWidth:       '260px',
      padding:        '14px 16px 12px 16px',
      borderRadius:   '10px',
      background:     'rgba(40, 42, 54, 0.98)',
      color:          '#f8f8f2',
      border:         '1px solid rgba(189, 147, 249, 0.55)',
      boxShadow:      '0 10px 30px rgba(0, 0, 0, 0.5)',
      font:           '13px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
      pointerEvents:  'auto'
    });

    var counter = _el('div', { text: 'Step ' + (stepIndex + 1) + ' of ' + total }, {
      fontSize:    '11px',
      opacity:     '0.55',
      marginBottom: '4px',
      letterSpacing: '0.04em',
      textTransform: 'uppercase'
    });

    var title = _el('div', { id: 'ora-tutorial-title', text: step.title }, {
      fontSize:    '15px',
      fontWeight:  '600',
      marginBottom: '6px',
      color:       '#bd93f9'
    });

    var body = _el('div', { id: 'ora-tutorial-body', text: step.body }, {
      fontSize: '13px', marginBottom: '12px'
    });

    var btnRow = _el('div', null, {
      display:        'flex',
      justifyContent: 'space-between',
      alignItems:     'center',
      gap:            '8px'
    });

    var skip = _el('button', {
      type: 'button', 'class': 'ora-tutorial-skip', text: 'Skip',
      'aria-label': 'Skip tour'
    }, {
      background:   'transparent',
      border:       '1px solid rgba(248, 248, 242, 0.25)',
      color:        '#f8f8f2',
      borderRadius: '6px',
      padding:      '5px 10px',
      cursor:       'pointer',
      font:         'inherit'
    });

    var nextLabel = (stepIndex === total - 1) ? 'Done' : 'Next';
    var next = _el('button', {
      type: 'button', 'class': 'ora-tutorial-next', text: nextLabel,
      'aria-label': nextLabel
    }, {
      background:   '#bd93f9',
      border:       '1px solid #bd93f9',
      color:        '#282a36',
      borderRadius: '6px',
      padding:      '5px 14px',
      cursor:       'pointer',
      fontWeight:   '600',
      font:         'inherit'
    });

    btnRow.appendChild(skip);
    btnRow.appendChild(next);

    card.appendChild(counter);
    card.appendChild(title);
    card.appendChild(body);
    card.appendChild(btnRow);

    if (step.wpRef) {
      var ref = _el('div', { text: step.wpRef }, {
        fontSize:  '10px',
        opacity:   '0.4',
        marginTop: '8px',
        textAlign: 'right',
        fontStyle: 'italic'
      });
      card.appendChild(ref);
    }

    document.body.appendChild(card);
    return { card: card, skipBtn: skip, nextBtn: next };
  }

  function _positionCard(card, anchor) {
    // If no anchor, center it on screen.
    var vpW = window.innerWidth, vpH = window.innerHeight;
    if (!anchor) {
      var cw = card.offsetWidth || 300, ch = card.offsetHeight || 160;
      card.style.left = Math.max(16, Math.round((vpW - cw) / 2)) + 'px';
      card.style.top  = Math.max(16, Math.round((vpH - ch) / 2)) + 'px';
      return;
    }
    var rect = anchor.getBoundingClientRect();
    var cw = card.offsetWidth || 300, ch = card.offsetHeight || 160;
    var pad = 12;

    // Prefer below; fall back to above; then right; then left.
    var top  = rect.bottom + pad;
    var left = rect.left + Math.round((rect.width - cw) / 2);

    if (top + ch > vpH - 16) top = rect.top - ch - pad;
    if (top < 16) {
      top  = Math.max(16, rect.top + Math.round((rect.height - ch) / 2));
      left = (rect.right + cw + pad <= vpW - 16) ? rect.right + pad : rect.left - cw - pad;
    }
    left = Math.min(Math.max(16, left), vpW - cw - 16);
    top  = Math.min(Math.max(16, top),  vpH - ch - 16);

    card.style.left = left + 'px';
    card.style.top  = top  + 'px';
  }

  function _highlight(anchor) {
    if (!anchor) return null;
    var rect = anchor.getBoundingClientRect();
    var ring = _el('div', { 'class': 'ora-tutorial-ring', 'aria-hidden': 'true' }, {
      position:      'fixed',
      left:          (rect.left - 4) + 'px',
      top:           (rect.top  - 4) + 'px',
      width:         (rect.width  + 8) + 'px',
      height:        (rect.height + 8) + 'px',
      border:        '2px solid #bd93f9',
      borderRadius:  '8px',
      pointerEvents: 'none',
      zIndex:        '9998',
      boxShadow:     '0 0 0 9999px rgba(15, 16, 22, 0.32)',
      transition:    'all 120ms ease-out'
    });
    document.body.appendChild(ring);
    return ring;
  }

  // ── Walkthrough runner ────────────────────────────────────────────────────
  function _run(panelEl, onClose) {
    var idx = 0;
    var backdrop = _renderBackdrop();
    var cardEls = null, ring = null;

    function teardown(reason) {
      if (cardEls && cardEls.card && cardEls.card.parentNode) cardEls.card.parentNode.removeChild(cardEls.card);
      if (ring && ring.parentNode) ring.parentNode.removeChild(ring);
      if (backdrop && backdrop.parentNode) backdrop.parentNode.removeChild(backdrop);
      cardEls = null; ring = null; backdrop = null;
      if (reason === 'completed') _setFlag(KEY_COMPLETED);
      else                        _setFlag(KEY_DISMISSED);
      onClose && onClose(reason);
    }

    function show(i) {
      if (cardEls && cardEls.card && cardEls.card.parentNode) cardEls.card.parentNode.removeChild(cardEls.card);
      if (ring && ring.parentNode) ring.parentNode.removeChild(ring);

      var step   = STEPS[i];
      var anchor = _findInPanel(panelEl, step.selector);
      ring        = _highlight(anchor);
      cardEls     = _renderCard(i, STEPS.length, step);
      _positionCard(cardEls.card, anchor);

      cardEls.skipBtn.addEventListener('click', function () { teardown('dismissed'); });
      cardEls.nextBtn.addEventListener('click', function () {
        if (i >= STEPS.length - 1) { teardown('completed'); return; }
        idx = i + 1;
        show(idx);
      });

      // Esc aborts.
      var keyHandler = function (e) {
        if (e.key === 'Escape') {
          window.removeEventListener('keydown', keyHandler, true);
          teardown('dismissed');
        }
      };
      window.addEventListener('keydown', keyHandler, true);
      cardEls.card.dataset.keyHandlerInstalled = '1';
    }

    show(0);
  }

  // ── Per-panel mount ───────────────────────────────────────────────────────
  // Called once per VisualPanel.init(). Idempotent: safe to call again on the
  // same panel (no-op if the launcher already exists or the user has dismissed).
  function _mountForPanel(panelInst) {
    if (!panelInst || !panelInst.el) return;
    if (panelInst._oraTutorialMounted) return;
    panelInst._oraTutorialMounted = true;

    if (!_isFirstOpen()) return;                              // already seen → skip

    // Wait one frame so the panel's innerHTML is on the DOM before we anchor.
    var raf = window.requestAnimationFrame || function (fn) { return setTimeout(fn, 16); };
    raf(function () {
      var panelEl = panelInst.el;
      // Ensure positioning context.
      var pos = window.getComputedStyle ? window.getComputedStyle(panelEl).position : '';
      if (pos === 'static' || !pos) panelEl.style.position = 'relative';

      var launcher = null;
      function close()  { if (launcher && launcher.parentNode) launcher.parentNode.removeChild(launcher); _setFlag(KEY_DISMISSED); }
      function launch() {
        if (launcher && launcher.parentNode) launcher.parentNode.removeChild(launcher);
        _run(panelEl, function (_reason) { /* both reasons end the tour */ });
      }
      launcher = _renderLauncher(panelEl, launch, close);
    });
  }

  // ── Hook into VisualPanel lifecycle ───────────────────────────────────────
  // The panel installs `window.VisualPanel` (line ~4626 of visual-panel.js) and
  // `window.OraPanels.visual.init` (~4647). We patch the prototype `init` the
  // same way the panel itself does (the `origInit` pattern at line 4636) so we
  // run *after* the toolbar DOM exists.
  function _installLifecycleHook() {
    if (!window.VisualPanel || !window.VisualPanel.prototype) return false;
    if (window.VisualPanel.prototype.__oraTutorialPatched) return true;

    var origInit = window.VisualPanel.prototype.init;
    window.VisualPanel.prototype.init = function () {
      var ret = origInit.apply(this, arguments);
      try { _mountForPanel(this); }
      catch (e) {
        if (window.console && console.warn) console.warn('[opt-in-tutorial] mount failed:', e);
      }
      return ret;
    };
    window.VisualPanel.prototype.__oraTutorialPatched = true;

    // If the panel already initialized before this script ran, mount on the
    // active instance directly.
    try {
      var active = window.OraPanels && window.OraPanels.visual &&
                   typeof window.OraPanels.visual._getActive === 'function' &&
                   window.OraPanels.visual._getActive();
      if (active) _mountForPanel(active);
    } catch (_) { /* silent */ }

    return true;
  }

  // Try immediately; if VisualPanel isn't on window yet, retry on DOMContentLoaded
  // and once more after a short tick (covers script-order edge cases).
  if (!_installLifecycleHook()) {
    var tryAgain = function () { _installLifecycleHook(); };
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', tryAgain, { once: true });
    }
    setTimeout(tryAgain, 0);
    setTimeout(tryAgain, 250);
  }

  // ── Public surface (testing + manual reopen) ──────────────────────────────
  // `OraTutorial.reset()`     — clear both flags so the launcher reappears.
  // `OraTutorial.run(panel?)` — force-run on the given panel (or active).
  // `OraTutorial.isFirstOpen()` — predicate used at mount time.
  window.OraTutorial = {
    reset: function () {
      try {
        if (window.localStorage) {
          window.localStorage.removeItem(KEY_DISMISSED);
          window.localStorage.removeItem(KEY_COMPLETED);
        }
      } catch (_) { /* silent */ }
    },
    run: function (panelInst) {
      var inst = panelInst || (window.OraPanels && window.OraPanels.visual &&
                               typeof window.OraPanels.visual._getActive === 'function' &&
                               window.OraPanels.visual._getActive());
      if (!inst || !inst.el) return false;
      _run(inst.el, function () {});
      return true;
    },
    isFirstOpen: _isFirstOpen,
    _STEPS: STEPS,
    _KEY_DISMISSED: KEY_DISMISSED,
    _KEY_COMPLETED: KEY_COMPLETED
  };
})();
