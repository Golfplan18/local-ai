/**
 * canvas-share-reminder.js — WP-7.7.6
 *
 * One-time-per-session share-reminder modal for canvas files.
 *
 * ── Why this exists (Plan §11.15) ─────────────────────────────────────────
 *
 * Canvas files (`.ora-canvas` / `.ora-canvas.json`) carry the user's prompts
 * and embedded image data. When the user shares one — by uploading,
 * emailing, posting, or otherwise sending the file outside the local
 * machine — they should be reminded once per session that the file's
 * contents go with it.
 *
 * Per the §11.15 security model: Ora informs and lets the user decide.
 * No gating, no analytics, no policy. A single confirm step before the
 * first share of a session, then silent for the rest of that session.
 *
 * ── Event surface (the contract) ──────────────────────────────────────────
 *
 * Future Share / Export commands dispatch a CustomEvent on `window`:
 *
 *     window.dispatchEvent(new CustomEvent('ora:canvas-pre-share', {
 *       detail: {
 *         path:     '/path/to/file.ora-canvas',     // optional
 *         intent:   'share' | 'export' | 'save-as', // optional, hint for label
 *         onConfirm: function () { ... actual write ... },
 *         onCancel:  function () { ... no-op default ... },
 *       }
 *     }));
 *
 * The reminder module:
 *   1. If already-confirmed-this-session → calls `onConfirm` immediately, returns.
 *   2. Otherwise → renders the modal. User clicks Continue → onConfirm.
 *      User clicks Cancel or Esc → onCancel (or no-op if not provided).
 *
 * Either way, after the first confirm in a session, subsequent dispatches
 * pass through silently. A page reload or new conversation resets the
 * session flag (the flag lives in `sessionStorage`).
 *
 * ── Conversation-state persistence ────────────────────────────────────────
 *
 * Per the WP brief: "Reminded this session" persists in conversation state
 * (sessionStorage or equivalent — when the page reloads or a new
 * conversation starts, the reminder fires again on first share."
 *
 *   - `sessionStorage` covers the page-reload reset automatically.
 *   - "New conversation" reset: callers (chat panel, when starting a new
 *     conversation) can call `OraCanvasShareReminder.reset()` to clear the
 *     flag mid-session. This is the intended hook for the "new conversation"
 *     trigger described in the WP.
 *
 * If `sessionStorage` is unavailable (privacy mode, sandboxed iframe), a
 * module-local fallback flag is used — same one-modal-per-session
 * semantics, just doesn't survive a page reload (which is the same outcome
 * sessionStorage gives anyway).
 *
 * ── Public surface ────────────────────────────────────────────────────────
 *
 *   OraCanvasShareReminder.init({ host })
 *     Mount the listener and lazy-mount the modal. Call once at boot.
 *     `host` (optional) is a DOM element to mount the modal into; defaults
 *     to document.body.
 *
 *   OraCanvasShareReminder.requestShare({ intent, path, onConfirm, onCancel })
 *     Convenience helper. Equivalent to dispatching `ora:canvas-pre-share`
 *     with the same detail. Future Share/Export commands can use either.
 *
 *   OraCanvasShareReminder.hasBeenReminded()
 *     Read the session flag. Tests + diagnostics.
 *
 *   OraCanvasShareReminder.reset()
 *     Clear the session flag. Call when starting a new conversation.
 *
 *   OraCanvasShareReminder.destroy()
 *     Tear down listener and modal. Tests use this between cases.
 *
 * ── Why not modify canvas-file-format.js itself? ──────────────────────────
 *
 * canvas-file-format.js is a pure (de)serializer — bytes in, bytes out. It
 * has no concept of "where the bytes are going". Wrapping its writes with
 * a UI prompt would couple the data layer to the DOM and break the test
 * harness's headless usage. The event surface keeps the data layer pure
 * and lets the eventual Share / Export commands (WP-7.4.8 onward) decide
 * when sharing is plausible.
 */

(function () {
  'use strict';

  var EVENT_NAME = 'ora:canvas-pre-share';
  var STORAGE_KEY = 'ora.canvas.shareReminder.acknowledged';
  var MODAL_ID = 'ora-canvas-share-reminder-modal';

  // Module-local fallback when sessionStorage is unavailable.
  var _localFlag = false;

  // Mount state.
  var _listener = null;
  var _modalEl = null;
  var _hostEl = null;
  var _activePending = null;   // { onConfirm, onCancel } during modal-open
  var _previousFocus = null;
  var _onKeydown = null;

  // ── Persistence helpers ──────────────────────────────────────────────────

  function _getStorage() {
    try {
      if (typeof window !== 'undefined' && window.sessionStorage) {
        // Probe — privacy mode can throw on access.
        var probeKey = '__ora_canvas_share_probe__';
        window.sessionStorage.setItem(probeKey, '1');
        window.sessionStorage.removeItem(probeKey);
        return window.sessionStorage;
      }
    } catch (e) {
      /* fall through to local flag */
    }
    return null;
  }

  function hasBeenReminded() {
    var s = _getStorage();
    if (s) {
      try {
        return s.getItem(STORAGE_KEY) === '1';
      } catch (e) { /* fall through */ }
    }
    return _localFlag === true;
  }

  function _markReminded() {
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

  // ── Modal construction ───────────────────────────────────────────────────

  function _buildModal() {
    if (typeof document === 'undefined') return null;
    var root = document.createElement('div');
    root.id = MODAL_ID;
    root.className = 'ora-canvas-share-reminder';
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-labelledby', MODAL_ID + '-title');
    root.setAttribute('aria-describedby', MODAL_ID + '-body');
    root.hidden = true;

    root.innerHTML =
      '<div class="ora-canvas-share-reminder__backdrop" data-action="cancel"></div>' +
      '<div class="ora-canvas-share-reminder__dialog">' +
        '<h2 class="ora-canvas-share-reminder__title" id="' + MODAL_ID + '-title">Before you share</h2>' +
        '<div class="ora-canvas-share-reminder__body" id="' + MODAL_ID + '-body">' +
          '<p>This canvas file contains the prompts you typed and any images you placed on the canvas (including AI-generated images).</p>' +
          '<p>Anyone you send the file to will be able to read those prompts and view those images.</p>' +
          '<p class="ora-canvas-share-reminder__note">Shown once per session.</p>' +
        '</div>' +
        '<div class="ora-canvas-share-reminder__actions">' +
          '<button type="button" class="ora-canvas-share-reminder__btn ora-canvas-share-reminder__btn--cancel" data-action="cancel">Cancel</button>' +
          '<button type="button" class="ora-canvas-share-reminder__btn ora-canvas-share-reminder__btn--confirm" data-action="confirm">Continue</button>' +
        '</div>' +
      '</div>';

    root.addEventListener('click', _onModalClick);
    return root;
  }

  function _onModalClick(e) {
    var target = e.target;
    if (!target || !target.dataset) return;
    var action = target.dataset.action;
    if (!action) {
      // Click on the dialog body (not backdrop / button) → ignore.
      return;
    }
    if (action === 'confirm')      _handleConfirm();
    else if (action === 'cancel')  _handleCancel();
  }

  function _showModal(detail) {
    if (!_modalEl) return false;
    _activePending = {
      onConfirm: (detail && typeof detail.onConfirm === 'function') ? detail.onConfirm : null,
      onCancel:  (detail && typeof detail.onCancel  === 'function') ? detail.onCancel  : null
    };

    // Customize the body for the supplied intent / path, if any.
    var bodyEl = _modalEl.querySelector('#' + MODAL_ID + '-body');
    if (bodyEl) {
      var intent = (detail && typeof detail.intent === 'string') ? detail.intent : '';
      var verb = 'share';
      if (intent === 'export')  verb = 'export';
      if (intent === 'save-as') verb = 'save';
      var label = bodyEl.querySelector('.ora-canvas-share-reminder__intent');
      if (!label) {
        label = document.createElement('p');
        label.className = 'ora-canvas-share-reminder__intent';
        bodyEl.insertBefore(label, bodyEl.firstChild);
      }
      label.textContent =
        (verb === 'share')  ? 'You are about to share a canvas file.' :
        (verb === 'export') ? 'You are about to export a canvas file.' :
                              'You are about to save a canvas file you may share.';
    }

    _modalEl.hidden = false;
    // Capture focus so Esc / Tab work intuitively.
    if (typeof document !== 'undefined' && document.activeElement) {
      _previousFocus = document.activeElement;
    }
    var confirmBtn = _modalEl.querySelector('.ora-canvas-share-reminder__btn--confirm');
    if (confirmBtn && typeof confirmBtn.focus === 'function') {
      try { confirmBtn.focus(); } catch (e) { /* ignore */ }
    }

    _onKeydown = function (e) {
      if (!_modalEl || _modalEl.hidden) return;
      if (e.key === 'Escape' || e.keyCode === 27) {
        e.preventDefault();
        _handleCancel();
      } else if ((e.key === 'Enter' || e.keyCode === 13) && e.target && e.target.dataset && e.target.dataset.action !== 'cancel') {
        // Enter on the confirm button (default focus) confirms; on the
        // cancel button it should cancel — let the click handler run.
        if (e.target.dataset && e.target.dataset.action === 'confirm') {
          e.preventDefault();
          _handleConfirm();
        }
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

  function _handleConfirm() {
    var pending = _activePending;
    _activePending = null;
    _markReminded();
    _hideModal();
    if (pending && pending.onConfirm) {
      try { pending.onConfirm(); }
      catch (e) {
        if (typeof console !== 'undefined' && console.error) {
          console.error('[canvas-share-reminder] onConfirm threw:', e);
        }
      }
    }
  }

  function _handleCancel() {
    var pending = _activePending;
    _activePending = null;
    _hideModal();
    if (pending && pending.onCancel) {
      try { pending.onCancel(); }
      catch (e) {
        if (typeof console !== 'undefined' && console.error) {
          console.error('[canvas-share-reminder] onCancel threw:', e);
        }
      }
    }
  }

  // ── Event surface ────────────────────────────────────────────────────────

  function _handleEvent(evt) {
    var detail = (evt && evt.detail) ? evt.detail : {};
    if (hasBeenReminded()) {
      // Already confirmed this session — pass through immediately.
      if (typeof detail.onConfirm === 'function') {
        try { detail.onConfirm(); }
        catch (e) {
          if (typeof console !== 'undefined' && console.error) {
            console.error('[canvas-share-reminder] passthrough onConfirm threw:', e);
          }
        }
      }
      return;
    }
    _showModal(detail);
  }

  function requestShare(detail) {
    if (typeof window === 'undefined') {
      // Non-browser context — invoke confirm immediately, treating it as
      // the simplest possible passthrough. Matches "no UI available" flow.
      if (detail && typeof detail.onConfirm === 'function') detail.onConfirm();
      return;
    }
    var evt;
    try {
      evt = new window.CustomEvent(EVENT_NAME, { detail: detail || {} });
    } catch (e) {
      // Older runtime fallback.
      evt = document.createEvent('CustomEvent');
      evt.initCustomEvent(EVENT_NAME, false, false, detail || {});
    }
    window.dispatchEvent(evt);
  }

  // ── Init / destroy ───────────────────────────────────────────────────────

  function init(opts) {
    if (typeof window === 'undefined' || typeof document === 'undefined') return;
    if (_listener) return;   // idempotent
    opts = (opts && typeof opts === 'object') ? opts : {};
    _hostEl = (opts.host && opts.host.appendChild) ? opts.host : document.body;
    _modalEl = _buildModal();
    if (_modalEl && _hostEl) _hostEl.appendChild(_modalEl);
    _listener = _handleEvent;
    window.addEventListener(EVENT_NAME, _listener);
  }

  function destroy() {
    if (typeof window !== 'undefined' && _listener) {
      window.removeEventListener(EVENT_NAME, _listener);
    }
    _listener = null;
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
  }

  // ── Exports ──────────────────────────────────────────────────────────────

  var ns = {
    EVENT_NAME:        EVENT_NAME,
    STORAGE_KEY:       STORAGE_KEY,
    init:              init,
    destroy:           destroy,
    reset:             reset,
    hasBeenReminded:   hasBeenReminded,
    requestShare:      requestShare,
    // Test introspection — return the active modal node (or null).
    _getModalEl:       function () { return _modalEl; },
    _getActivePending: function () { return _activePending; }
  };

  if (typeof window !== 'undefined') {
    window.OraCanvasShareReminder = ns;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = ns;
  }
})();
