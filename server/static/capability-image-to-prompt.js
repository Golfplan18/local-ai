/**
 * capability-image-to-prompt.js — WP-7.3.3g
 *
 * Slot wiring for the `image_to_prompt` capability. Bridges the generic
 * UX layer (capability-invocation-ui.js, WP-7.3.1) with the server-side
 * dispatcher in `orchestrator/integrations/replicate.py` (WP-7.3.2c)
 * which captions an image via salesforce/blip and adapts the caption
 * tail per `target_style` (DALL-E plain / SD detail-stack / MJ flags /
 * Flux cinematic).
 *
 * Unlike sibling slots (image_generates / image_edits / image_styles),
 * this slot returns **text** — a prompt string the user can paste into
 * the target image generator. There is no canvas insertion. The result
 * is rendered into the invocation UI's result panel with a
 * copy-to-clipboard affordance.
 *
 * The module is intentionally narrow:
 *   1. Listen for `capability-dispatch` events whose `slot` is
 *      `image_to_prompt`.
 *   2. POST the inputs to `/api/capability/image_to_prompt` (the server
 *      route added alongside this WP).
 *   3. Surface the returned prompt string to the invocation UI's
 *      `renderResult` (which already renders `output.type === 'text'`
 *      into a `<pre>`) and decorate the result panel with a Copy button.
 *   4. Emit a `capability-result` event so any external listener (e.g.
 *      analytics, the chat bridge) can pick up the text.
 *
 * Errors flowing back from the server are translated into the
 * `capability-error` shape `{ code, message, fix_path }` so the
 * invocation UI's error renderer can hang the right fix-path button on
 * them. `image_unreadable` is the slot's only declared common error
 * (re-upload fix path) — anything else collapses to `model_unavailable`.
 *
 * ── Public API ─────────────────────────────────────────────────────────
 *
 *   window.OraCapabilityImageToPrompt
 *
 *     .init({ hostEl, fetchImpl, endpoint, ui })
 *       Mount on `hostEl` (the same host the invocation UI runs on,
 *       since `capability-dispatch` bubbles). `fetchImpl` defaults to
 *       `window.fetch` and exists so tests can inject mocks. `endpoint`
 *       defaults to `/api/capability/image_to_prompt`. `ui` defaults to
 *       `window.OraCapabilityInvocationUI` so the result/error renderers
 *       fire automatically when the UI is mounted on the same host.
 *
 *     .destroy()           — detach listener.
 *     .handleDispatch(detail)
 *                          — programmatic entry point (test introspection
 *                            and integration with hosts that prefer
 *                            method calls over events).
 */
(function (root) {
  'use strict';

  // ── Constants ─────────────────────────────────────────────────────────

  var DEFAULT_ENDPOINT = '/api/capability/image_to_prompt';

  // Error code translation: HTTP status → slot common_errors code. The
  // slot only declares `image_unreadable`; everything else collapses to
  // `model_unavailable` so the user always gets a fix-path button.
  function _statusToCode(status) {
    if (status === 400) return 'image_unreadable';
    if (status === 422) return 'image_unreadable';
    if (status === 415) return 'image_unreadable';
    return 'model_unavailable';
  }

  // ── DOM / event helpers ──────────────────────────────────────────────

  function _emit(targetEl, name, detail) {
    if (!targetEl || typeof CustomEvent !== 'function') return;
    var evt = new CustomEvent(name, { detail: detail, bubbles: true });
    targetEl.dispatchEvent(evt);
  }

  function _synthError(code, message) {
    var e = new Error(message || code);
    e.code = code;
    return e;
  }

  // ── Server call ──────────────────────────────────────────────────────

  /**
   * POST the dispatch payload to the capability endpoint and parse the
   * response. The server's response shape is the contract:
   *
   *   200 OK
   *   {
   *     "prompt": "<generated prompt string>",
   *     "provider": "replicate" | "mock",
   *     "metadata": { ... }   // optional
   *   }
   *
   *   Non-200
   *   {
   *     "error": { "code": "image_unreadable" | ..., "message": "..." }
   *   }
   */
  function _callServer(endpoint, payload, fetchImpl) {
    var fn = fetchImpl
      || (typeof root !== 'undefined' && root.fetch)
      || (typeof fetch !== 'undefined' ? fetch : null);
    if (typeof fn !== 'function') {
      return Promise.reject(_synthError('model_unavailable',
        'fetch is not available in this environment.'));
    }
    var body = JSON.stringify(payload);
    return fn(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body,
    }).then(function (response) {
      var status = (response && typeof response.status === 'number') ? response.status : 0;
      var jsonPromise = (response && typeof response.json === 'function')
        ? response.json()
        : Promise.resolve(response && response.body ? response.body : null);
      return jsonPromise.then(function (data) {
        if (status >= 200 && status < 300) {
          return data;
        }
        var errBody = (data && data.error) || {};
        var code = errBody.code || _statusToCode(status);
        var message = errBody.message
          || ('Provider returned HTTP ' + status + '.');
        throw _synthError(code, message);
      });
    });
  }

  // ── Result extraction ────────────────────────────────────────────────

  /**
   * Pull the prompt text out of the server response. Accepts a few
   * shapes for forward compatibility:
   *
   *   { prompt: '<text>' }
   *   { text:   '<text>' }
   *   { output: '<text>' }
   *
   * Returns { prompt, provider, metadata } or null on miss.
   */
  function _extractPrompt(response) {
    if (!response || typeof response !== 'object') return null;
    var prompt = response.prompt || response.text || response.output || null;
    if (typeof prompt !== 'string' || !prompt.length) return null;
    return {
      prompt:   prompt,
      provider: response.provider || null,
      metadata: response.metadata || null,
    };
  }

  // ── Copy-to-clipboard decoration ─────────────────────────────────────

  /**
   * Locate the invocation UI's result panel and append a Copy button.
   * The UI's renderResult already drops the prompt text into a
   * `<pre class="ora-cap-result__text">`; we add a sibling button that
   * copies that text via the Clipboard API (with a textarea fallback for
   * environments without `navigator.clipboard`).
   */
  function _decorateWithCopyButton(hostEl, promptText) {
    if (!hostEl || typeof hostEl.querySelector !== 'function') return;
    var resultEl = hostEl.querySelector('.ora-cap-result');
    if (!resultEl) return;

    // Avoid duplicating the button across re-renders — clear any prior.
    var prior = resultEl.querySelector('.ora-cap-result__copy');
    if (prior && prior.parentNode) prior.parentNode.removeChild(prior);

    var btn = (typeof document !== 'undefined')
      ? document.createElement('button')
      : null;
    if (!btn) return;
    btn.className = 'ora-cap-result__copy';
    btn.type = 'button';
    btn.textContent = 'Copy prompt';

    btn.addEventListener('click', function () {
      _copyText(promptText).then(function (ok) {
        btn.textContent = ok ? 'Copied!' : 'Copy failed';
        // Restore label after a moment so repeated copies feel responsive.
        if (typeof setTimeout === 'function') {
          setTimeout(function () { btn.textContent = 'Copy prompt'; }, 1500);
        }
      });
    });

    resultEl.appendChild(btn);
  }

  function _copyText(text) {
    var asString = String(text == null ? '' : text);
    // Modern Clipboard API path.
    if (typeof navigator !== 'undefined'
        && navigator.clipboard
        && typeof navigator.clipboard.writeText === 'function') {
      try {
        return navigator.clipboard.writeText(asString)
          .then(function () { return true; })
          .catch(function () { return _copyTextFallback(asString); });
      } catch (_e) {
        return Promise.resolve(_copyTextFallback(asString));
      }
    }
    return Promise.resolve(_copyTextFallback(asString));
  }

  function _copyTextFallback(text) {
    // Last-ditch: textarea + execCommand. Works in older browsers and
    // jsdom environments that polyfill execCommand.
    if (typeof document === 'undefined') return false;
    try {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'absolute';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = !!document.execCommand && document.execCommand('copy'); }
      catch (_e) { ok = false; }
      document.body.removeChild(ta);
      return !!ok;
    } catch (_e) {
      return false;
    }
  }

  // ── Module state ─────────────────────────────────────────────────────

  function _makeController(opts) {
    opts = opts || {};
    var state = {
      hostEl:       opts.hostEl || (typeof document !== 'undefined' ? document : null),
      fetchImpl:    opts.fetchImpl || null,
      endpoint:     opts.endpoint || DEFAULT_ENDPOINT,
      ui:           opts.ui || (typeof root !== 'undefined' ? root.OraCapabilityInvocationUI : null),
      _listener:    null,
      _destroyed:   false,
    };

    function handleDispatch(detail) {
      if (state._destroyed) return Promise.resolve(null);
      if (!detail || detail.slot !== 'image_to_prompt') return Promise.resolve(null);
      var inputs = detail.inputs || {};

      var payload = {
        slot:    'image_to_prompt',
        inputs:  inputs,
      };
      if (detail.provider_override || inputs.provider_override) {
        payload.provider_override = detail.provider_override || inputs.provider_override;
      }

      return _callServer(state.endpoint, payload, state.fetchImpl).then(function (response) {
        var extracted = _extractPrompt(response);
        if (!extracted) {
          throw _synthError('model_unavailable',
            'Provider returned a response with no prompt text.');
        }

        // Surface to the invocation UI: renderResult handles the
        // text-output rendering (per capability-invocation-ui.js
        // line ~915, output.type 'text' lands in a <pre>). We then
        // decorate that panel with our Copy button.
        var resultPayload = {
          output:   extracted.prompt,
          provider: extracted.provider,
          metadata: extracted.metadata,
        };
        if (state.ui && typeof state.ui.renderResult === 'function') {
          try { state.ui.renderResult(resultPayload); } catch (_e) { /* swallow */ }
        }
        _decorateWithCopyButton(state.hostEl, extracted.prompt);

        _emit(state.hostEl, 'capability-result', {
          slot:     'image_to_prompt',
          output:   extracted.prompt,
          provider: extracted.provider,
          metadata: extracted.metadata,
        });
        return resultPayload;
      }).catch(function (err) {
        var code = (err && err.code) || 'model_unavailable';
        var message = (err && err.message) || String(err);
        if (state.ui && typeof state.ui.renderError === 'function') {
          try {
            state.ui.renderError({ code: code, message: message });
          } catch (_e) { /* swallow */ }
        }
        _emit(state.hostEl, 'capability-error', {
          slot:    'image_to_prompt',
          code:    code,
          message: message,
        });
        throw err;
      });
    }

    function _onCapabilityDispatch(evt) {
      if (!evt || !evt.detail) return;
      if (evt.detail.slot !== 'image_to_prompt') return;
      // Fire-and-forget: rejection is already surfaced via UI / event.
      handleDispatch(evt.detail).catch(function () { /* surfaced */ });
    }

    function destroy() {
      if (state._destroyed) return;
      state._destroyed = true;
      if (state.hostEl && state._listener) {
        state.hostEl.removeEventListener('capability-dispatch', state._listener);
      }
      state._listener = null;
    }

    function setUI(ui)       { state.ui = ui || null; }
    function setEndpoint(ep) { state.endpoint = ep || DEFAULT_ENDPOINT; }
    function setFetchImpl(fn) { state.fetchImpl = fn || null; }

    if (state.hostEl && typeof state.hostEl.addEventListener === 'function') {
      state._listener = _onCapabilityDispatch;
      state.hostEl.addEventListener('capability-dispatch', state._listener);
    }

    return {
      handleDispatch: handleDispatch,
      destroy:        destroy,
      setUI:          setUI,
      setEndpoint:    setEndpoint,
      setFetchImpl:   setFetchImpl,
      _state:         state,
    };
  }

  // ── Module-level "active" controller ─────────────────────────────────

  var _activeController = null;

  function init(opts) {
    if (_activeController) {
      try { _activeController.destroy(); } catch (_e) { /* ignore */ }
    }
    _activeController = _makeController(opts || {});
    return _activeController;
  }

  function _delegate(method) {
    return function () {
      if (!_activeController) return null;
      return _activeController[method].apply(_activeController, arguments);
    };
  }

  var api = {
    init:           init,
    handleDispatch: _delegate('handleDispatch'),
    setUI:          _delegate('setUI'),
    setEndpoint:    _delegate('setEndpoint'),
    setFetchImpl:   _delegate('setFetchImpl'),
    destroy: function () {
      if (_activeController) _activeController.destroy();
      _activeController = null;
    },
    // Test hooks
    _extractPrompt:  _extractPrompt,
    _statusToCode:   _statusToCode,
    _copyText:       _copyText,
    _copyTextFallback: _copyTextFallback,
    DEFAULT_ENDPOINT: DEFAULT_ENDPOINT,
    _getActive: function () { return _activeController; },
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraCapabilityImageToPrompt = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
