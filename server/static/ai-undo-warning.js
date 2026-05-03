/**
 * ai-undo-warning.js — WP-7.7.2
 *
 * One-time-per-session warning shown the first time the user undoes a
 * history frame whose origin was an AI-generated content insertion (or a
 * macro that invoked one).
 *
 * ── Why this exists (Plan §11.15, §12 Q17, §13.7) ─────────────────────────
 *
 * AI generations cost real time and money — when the user clicks Undo on
 * an AI-inserted shape, removing it from the canvas does NOT refund the
 * inference cost. Users who don't realise this can be surprised. Per the
 * §11.15 security model: Ora informs and lets the user decide. A single
 * advisory dialog the first time it matters in a session, then silent.
 *
 * ── Detection model ───────────────────────────────────────────────────────
 *
 *   1. AI capabilities (image_generates / image_outpaints / image_edits)
 *      already emit `canvas-state-changed` events tagged with
 *      `source: 'image_generates'` (etc.) when they finish inserting a
 *      canvas object — see capability-image-generates.js, capability-
 *      image-outpaints.js, tools/image-edits.js.
 *
 *   2. The object insertion goes through VisualPanel which pushes a
 *      history frame. By the time `canvas-state-changed` fires, the
 *      panel's `_historyCursor` already points one past the new frame.
 *
 *   3. We subscribe to `canvas-state-changed` at the window level, take
 *      the active panel's current cursor, and tag frame index
 *      `cursor - 1` as AI-sourced in a side map keyed by frame index.
 *
 *   4. Macro-undo: when the macro engine invokes an AI capability, the
 *      same `canvas-state-changed` event fires from the capability
 *      handler. So macro-driven AI insertions tag automatically. A
 *      `markRange()` helper is also exposed for callers that want to
 *      explicitly tag a span (e.g., a macro that batches several
 *      inserts under a single conceptual undo unit).
 *
 *   5. We wrap `OraPanels.visual.undo` (and the panel instance's `undo`
 *      via prototype patch) so before each undo we inspect the frame
 *      that's about to be unwound: if it's AI-tagged AND the session
 *      flag is unset, show the warning, then perform the undo. The
 *      warning is advisory — it does NOT gate the undo.
 *
 * ── Session persistence (matches WP-7.7.6 pattern) ────────────────────────
 *
 *   `sessionStorage` under key `ora.aiUndo.warned`. Page reload or new
 *   conversation resets the flag (chat-panel can call `reset()` on new
 *   conversation). Privacy-mode fallback: module-local flag.
 *
 * ── Public surface ────────────────────────────────────────────────────────
 *
 *   OraAIUndoWarning.init({ host })
 *     Mount listeners + lazy-mount modal. Idempotent.
 *
 *   OraAIUndoWarning.markCurrent({ panel })
 *     Explicitly tag the most recent history frame on `panel` as
 *     AI-sourced. Used by callers that don't go through
 *     `canvas-state-changed` (rare).
 *
 *   OraAIUndoWarning.markRange({ panel, from, to })
 *     Tag a contiguous range of frame indices [from, to) as AI-sourced.
 *     Useful for macro batch operations.
 *
 *   OraAIUndoWarning.hasBeenWarned()      // session flag read
 *   OraAIUndoWarning.reset()              // clear session flag
 *   OraAIUndoWarning.destroy()            // tear down (tests)
 *   OraAIUndoWarning._isFrameAI(panel, i) // test introspection
 *
 * ── Why a separate file, not a patch to visual-panel.js? ──────────────────
 *
 * Per the WP brief: "Prefer event-listener pattern over modifying
 * visual-panel.js directly." visual-panel owns canvas drawing + history
 * mechanics; it shouldn't know about cost-advisory UX. By layering on
 * top via the `canvas-state-changed` event surface and a thin prototype
 * wrap on `undo`, this module is fully self-contained and can be
 * removed by deleting one `<script>` tag.
 */

(function () {
  'use strict';

  // The set of `canvas-state-changed` source values that count as
  // AI-generated. New AI capabilities should add their source string here.
  var AI_SOURCES = {
    'image_generates':  true,
    'image_outpaints':  true,
    'image_edits':      true,
    'ai-generation':    true   // generic alias accepted by the WP brief
  };

  var STORAGE_KEY = 'ora.aiUndo.warned';
  var MODAL_ID    = 'ora-ai-undo-warning-modal';
  var EVENT_NAME  = 'canvas-state-changed';

  // Module-local fallback when sessionStorage is unavailable.
  var _localFlag = false;

  // Mount state.
  var _initialized      = false;
  var _hostEl           = null;
  var _modalEl          = null;
  var _stateListener    = null;     // capture listener on window
  var _activePending    = null;     // { onAck } during modal-open
  var _previousFocus    = null;
  var _onKeydown        = null;
  var _patchedPanels    = new WeakSet();
  var _patchedNamespace = false;

  // Per-panel side maps. Each map is panel-instance → Set<frameIndex>.
  // We use a WeakMap so destroyed panels are garbage-collected.
  var _aiFrames = new WeakMap();

  // ── Persistence helpers ──────────────────────────────────────────────────

  function _getStorage() {
    try {
      if (typeof window !== 'undefined' && window.sessionStorage) {
        var probeKey = '__ora_ai_undo_probe__';
        window.sessionStorage.setItem(probeKey, '1');
        window.sessionStorage.removeItem(probeKey);
        return window.sessionStorage;
      }
    } catch (e) { /* fall through */ }
    return null;
  }

  function hasBeenWarned() {
    var s = _getStorage();
    if (s) {
      try { return s.getItem(STORAGE_KEY) === '1'; }
      catch (e) { /* fall through */ }
    }
    return _localFlag === true;
  }

  function _markWarned() {
    var s = _getStorage();
    if (s) {
      try { s.setItem(STORAGE_KEY, '1'); }
      catch (e) { _localFlag = true; }
    } else {
      _localFlag = true;
    }
  }

  function reset() {
    var s = _getStorage();
    if (s) {
      try { s.removeItem(STORAGE_KEY); }
      catch (e) { /* ignore */ }
    }
    _localFlag = false;
  }

  // ── Per-panel AI-frame tagging ───────────────────────────────────────────

  function _getOrCreateSet(panel) {
    if (!panel) return null;
    var set = _aiFrames.get(panel);
    if (!set) {
      set = Object.create(null);
      // Use plain object as a sparse-int set; keys are stringified ints.
      _aiFrames.set(panel, set);
    }
    return set;
  }

  function _tagFrame(panel, frameIndex) {
    if (!panel || typeof frameIndex !== 'number' || frameIndex < 0) return;
    var set = _getOrCreateSet(panel);
    if (set) set[String(frameIndex)] = true;
  }

  function _isFrameAI(panel, frameIndex) {
    if (!panel) return false;
    var set = _aiFrames.get(panel);
    if (!set) return false;
    return set[String(frameIndex)] === true;
  }

  /**
   * Active-panel resolver. Looks at OraPanels.visual._getActive() if
   * present (the visual-panel module exposes this). Returns null if no
   * panel is mounted.
   */
  function _getActivePanel() {
    if (typeof window === 'undefined') return null;
    var P = window.OraPanels && window.OraPanels.visual;
    if (P && typeof P._getActive === 'function') {
      try { return P._getActive() || null; }
      catch (e) { return null; }
    }
    return null;
  }

  function markCurrent(detail) {
    var panel = (detail && detail.panel) || _getActivePanel();
    if (!panel || typeof panel.getHistoryCursor !== 'function') return;
    var cursor = panel.getHistoryCursor();
    if (cursor > 0) _tagFrame(panel, cursor - 1);
  }

  function markRange(detail) {
    if (!detail) return;
    var panel = detail.panel || _getActivePanel();
    if (!panel) return;
    var from = (typeof detail.from === 'number') ? detail.from : 0;
    var to   = (typeof detail.to   === 'number') ? detail.to   : from;
    if (to < from) { var tmp = from; from = to; to = tmp; }
    for (var i = from; i < to; i++) _tagFrame(panel, i);
  }

  // ── Modal construction ───────────────────────────────────────────────────

  function _buildModal() {
    if (typeof document === 'undefined') return null;
    var root = document.createElement('div');
    root.id = MODAL_ID;
    root.className = 'ora-ai-undo-warning';
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-labelledby', MODAL_ID + '-title');
    root.setAttribute('aria-describedby', MODAL_ID + '-body');
    root.hidden = true;

    root.innerHTML =
      '<div class="ora-ai-undo-warning__backdrop" data-action="ack"></div>' +
      '<div class="ora-ai-undo-warning__dialog">' +
        '<h2 class="ora-ai-undo-warning__title" id="' + MODAL_ID + '-title">Heads up: AI cost is already spent</h2>' +
        '<div class="ora-ai-undo-warning__body" id="' + MODAL_ID + '-body">' +
          '<p>You are about to undo a step that inserted AI-generated content on the canvas.</p>' +
          '<p>Undo removes the content, but the AI generation already ran — the time and any associated cost are not refunded. If you want a different result, you will need to generate again.</p>' +
          '<p class="ora-ai-undo-warning__note">Shown once per session.</p>' +
        '</div>' +
        '<div class="ora-ai-undo-warning__actions">' +
          '<button type="button" class="ora-ai-undo-warning__btn ora-ai-undo-warning__btn--ack" data-action="ack">Got it</button>' +
        '</div>' +
      '</div>';

    root.addEventListener('click', _onModalClick);
    return root;
  }

  function _onModalClick(e) {
    var target = e.target;
    if (!target || !target.dataset) return;
    var action = target.dataset.action;
    if (action === 'ack') _handleAck();
  }

  function _showModal(onAck) {
    if (!_modalEl) { if (onAck) onAck(); return false; }
    _activePending = { onAck: (typeof onAck === 'function') ? onAck : null };
    _modalEl.hidden = false;
    if (typeof document !== 'undefined' && document.activeElement) {
      _previousFocus = document.activeElement;
    }
    var ackBtn = _modalEl.querySelector('.ora-ai-undo-warning__btn--ack');
    if (ackBtn && typeof ackBtn.focus === 'function') {
      try { ackBtn.focus(); } catch (e) { /* ignore */ }
    }
    _onKeydown = function (e) {
      if (!_modalEl || _modalEl.hidden) return;
      if (e.key === 'Escape' || e.keyCode === 27 ||
          e.key === 'Enter'  || e.keyCode === 13) {
        e.preventDefault();
        _handleAck();
      }
    };
    if (typeof document !== 'undefined') {
      document.addEventListener('keydown', _onKeydown, true);
    }
    return true;
  }

  function _hideModal() {
    if (!_modalEl) return;
    _modalEl.hidden = true;
    if (typeof document !== 'undefined' && _onKeydown) {
      document.removeEventListener('keydown', _onKeydown, true);
    }
    _onKeydown = null;
    if (_previousFocus && typeof _previousFocus.focus === 'function') {
      try { _previousFocus.focus(); } catch (e) { /* ignore */ }
    }
    _previousFocus = null;
  }

  function _handleAck() {
    var pending = _activePending;
    _activePending = null;
    _markWarned();
    _hideModal();
    if (pending && pending.onAck) {
      try { pending.onAck(); }
      catch (e) {
        if (typeof console !== 'undefined' && console.error) {
          console.error('[ai-undo-warning] onAck threw:', e);
        }
      }
    }
  }

  // ── canvas-state-changed listener ────────────────────────────────────────

  /**
   * Capture-phase listener on `window`. Events bubble from hostEl up to
   * document/window (capability handlers dispatch on hostEl, which is
   * either the active document or the panel host). When an AI source
   * fires, tag the active panel's just-pushed history frame.
   *
   * The event happens AFTER the panel's `_pushHistory` runs (the
   * capability inserts the object via panel methods first, then emits
   * canvas-state-changed). So `getHistoryCursor()` already points one
   * past the new frame.
   */
  function _onCanvasStateChanged(evt) {
    if (!evt || !evt.detail) return;
    var src = evt.detail.source;
    if (!src || !AI_SOURCES[src]) return;
    var panel = _getActivePanel();
    if (!panel) return;
    markCurrent({ panel: panel });
  }

  // ── Undo wrap ────────────────────────────────────────────────────────────

  /**
   * Wrap `panel.undo` once per panel instance. The wrap inspects the
   * frame about to be unwound — that frame's index is `cursor - 1`
   * (since panel.undo decrements then runs `frames[cursor]`). If it's
   * AI-tagged and we haven't warned this session, show the modal, then
   * proceed with the undo regardless of acknowledgement state.
   */
  function _wrapPanelUndo(panel) {
    if (!panel || _patchedPanels.has(panel)) return;
    if (typeof panel.undo !== 'function') return;
    var origUndo = panel.undo.bind(panel);
    panel.undo = function () {
      var cursor = (typeof panel.getHistoryCursor === 'function')
        ? panel.getHistoryCursor() : 0;
      var aboutToUnwindIndex = cursor - 1;
      var isAI = _isFrameAI(panel, aboutToUnwindIndex);
      if (isAI && !hasBeenWarned()) {
        // Show the warning, then perform the undo. The warning is
        // advisory — non-gating per §11.15.
        _showModal(function () { /* ack callback — undo already ran below */ });
      }
      return origUndo();
    };
    _patchedPanels.add(panel);
  }

  /**
   * Wrap the OraPanels.visual namespace methods that proxy to the
   * active panel. We patch `undo` so callers using the namespace path
   * (e.g., toolbar buttons that go through the namespace) also trigger
   * the warning. Visual-panel.js dispatches its own keyboard Cmd+Z
   * through the instance's `undo`, which we patch separately on init.
   */
  function _wrapNamespaceUndo() {
    if (_patchedNamespace) return;
    if (typeof window === 'undefined') return;
    var P = window.OraPanels && window.OraPanels.visual;
    if (!P || typeof P.undo !== 'function') return;
    var origUndo = P.undo;
    P.undo = function () {
      var panel = _getActivePanel();
      if (panel) _wrapPanelUndo(panel);
      return origUndo.apply(P, arguments);
    };
    _patchedNamespace = true;
  }

  /**
   * Patch the VisualPanel prototype's `undo` once so every instance
   * (including ones mounted before init runs) inherits the wrap. We
   * cannot simply patch the prototype unconditionally — a stale wrap
   * across destroy/init cycles would compound. Instead we patch the
   * instance lazily via _wrapPanelUndo on first observation of an
   * active panel.
   */
  function _ensurePanelPatched() {
    var panel = _getActivePanel();
    if (panel) _wrapPanelUndo(panel);
  }

  // ── Init / destroy ───────────────────────────────────────────────────────

  function init(opts) {
    if (_initialized) return;
    if (typeof window === 'undefined' || typeof document === 'undefined') return;
    opts = (opts && typeof opts === 'object') ? opts : {};
    _hostEl = (opts.host && opts.host.appendChild) ? opts.host : document.body;

    _modalEl = _buildModal();
    if (_modalEl && _hostEl) _hostEl.appendChild(_modalEl);

    _stateListener = _onCanvasStateChanged;
    // Capture phase so we run before any later handler can mutate the
    // event. AI capabilities dispatch on hostEl which bubbles to window.
    window.addEventListener(EVENT_NAME, _stateListener, true);

    _wrapNamespaceUndo();
    _ensurePanelPatched();

    _initialized = true;
  }

  function destroy() {
    if (typeof window !== 'undefined' && _stateListener) {
      window.removeEventListener(EVENT_NAME, _stateListener, true);
    }
    _stateListener = null;
    if (_modalEl) {
      _modalEl.removeEventListener('click', _onModalClick);
      if (_modalEl.parentNode) _modalEl.parentNode.removeChild(_modalEl);
    }
    _modalEl = null;
    _hostEl = null;
    _activePending = null;
    _previousFocus = null;
    if (typeof document !== 'undefined' && _onKeydown) {
      document.removeEventListener('keydown', _onKeydown, true);
    }
    _onKeydown = null;
    _patchedPanels = new WeakSet();
    _aiFrames = new WeakMap();
    // _patchedNamespace remains true — the namespace function is now
    // wrapped permanently for the lifetime of OraPanels.visual. The
    // wrap is a no-op once `_initialized` is false because
    // _wrapPanelUndo bails on already-patched panels and the missing
    // tag set means hasBeenWarned() is the only gate, which still
    // works correctly. Re-initing simply rebuilds the modal + state.
    _initialized = false;
  }

  // ── Exports ──────────────────────────────────────────────────────────────

  var ns = {
    STORAGE_KEY:     STORAGE_KEY,
    AI_SOURCES:      AI_SOURCES,
    init:            init,
    destroy:         destroy,
    reset:           reset,
    hasBeenWarned:   hasBeenWarned,
    markCurrent:     markCurrent,
    markRange:       markRange,
    // Test introspection.
    _isFrameAI:      _isFrameAI,
    _getModalEl:     function () { return _modalEl; },
    _getActivePanel: _getActivePanel,
    _onCanvasStateChanged: _onCanvasStateChanged
  };

  if (typeof window !== 'undefined') {
    window.OraAIUndoWarning = ns;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = ns;
  }
})();
