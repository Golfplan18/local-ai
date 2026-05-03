/**
 * capability-image-critique.js — WP-7.3.3h
 *
 * Slot wiring for the `image_critique` capability (Reference — Capability
 * Invocation Contracts §3.8). Bridges the generic UX layer
 * (capability-invocation-ui.js, WP-7.3.1) with Ora's analytical pipeline
 * (Gear-based model selection — see boot.py / route_for_image_input) via
 * the server bridge `/api/capability/image_critique`.
 *
 * Unlike the image-producing siblings (image_generates / image_edits /
 * image_styles / image_outpaints / image_upscales), the result of a
 * critique is **structured text**: per-criterion rubric scores plus a
 * prose discussion. There is no canvas insertion. We render the result
 * inside the invocation UI's result panel as a small table (criterion /
 * score / comment) plus a prose section.
 *
 * The module is intentionally narrow:
 *   1. Listen for `capability-dispatch` events whose `slot` is
 *      `image_critique`.
 *   2. POST the inputs to `/api/capability/image_critique`.
 *   3. Render the structured critique into the result panel: rubric
 *      scores as a `<table>`, prose as a `<p>` block. Both live inside
 *      `.ora-cap-result` so the invocation UI's clearing logic finds them.
 *   4. Emit a `capability-result` event so external listeners (analytics,
 *      chat bridge, autosave) can pick up the critique payload.
 *
 * Errors flowing back from the server are translated into the
 * `capability-error` shape `{ code, message, fix_path }`. §3.8 declares
 * `no_specific_guidance` as the slot's only common error (fix path:
 * provide a rubric). Any other 4xx collapses to `no_specific_guidance`
 * (the user should retry with more guidance), 5xx and network failures
 * collapse to `model_unavailable`.
 *
 * ── Public API ─────────────────────────────────────────────────────────
 *
 *   window.OraCapabilityImageCritique
 *
 *     .init({ hostEl, fetchImpl, endpoint, ui })
 *       Mount on `hostEl` (the same host the invocation UI runs on,
 *       since `capability-dispatch` bubbles). `fetchImpl` defaults to
 *       `window.fetch`. `endpoint` defaults to
 *       `/api/capability/image_critique`. `ui` defaults to
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

  var DEFAULT_ENDPOINT = '/api/capability/image_critique';
  var VALID_DEPTHS = { quick: true, standard: true, deep: true };
  var DEFAULT_DEPTH = 'standard';
  var DEFAULT_MIME = 'image/png';

  // Error code translation: HTTP status → slot common_errors code.
  // §3.8 declares only `no_specific_guidance`. Any other 4xx collapses to
  // the same code (the user can fix it with more guidance); 5xx and
  // network errors collapse to `model_unavailable`.
  function _statusToCode(status) {
    if (status >= 400 && status < 500) return 'no_specific_guidance';
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

  // Image-ref inputs from the generic UI may arrive as a data URL
  // string, a `{ data_url: ... }` object, raw base64, or a remote URL.
  // Normalise to a data URL so the server gets a consistent shape.
  function _normalizeImageRef(ref) {
    if (!ref) return null;
    if (typeof ref === 'string') {
      if (ref.indexOf('data:') === 0) return ref;
      if (ref.indexOf('http://') === 0 || ref.indexOf('https://') === 0) return ref;
      // Treat bare base64 as PNG by default.
      return 'data:' + DEFAULT_MIME + ';base64,' + ref;
    }
    if (typeof ref === 'object') {
      if (typeof ref.data_url === 'string') return _normalizeImageRef(ref.data_url);
      if (typeof ref.dataUrl === 'string')  return _normalizeImageRef(ref.dataUrl);
      if (typeof ref.url === 'string')      return ref.url;
      if (typeof ref.base64 === 'string') {
        var mime = ref.mime_type || ref.mimeType || DEFAULT_MIME;
        return 'data:' + mime + ';base64,' + ref.base64;
      }
      if (typeof ref.data === 'string') {
        var mime2 = ref.mime_type || ref.mimeType || DEFAULT_MIME;
        if (ref.data.indexOf('data:') === 0) return ref.data;
        return 'data:' + mime2 + ';base64,' + ref.data;
      }
    }
    return null;
  }

  // ── Server call ──────────────────────────────────────────────────────

  /**
   * POST the dispatch payload to the capability endpoint. Server contract:
   *
   *   200 OK
   *   {
   *     "rubric_scores": {
   *        "<criterion>": { "score": 7, "comment": "..." },
   *        ...
   *     },
   *     "prose":    "<long-form discussion>",
   *     "provider": "claude" | "ora-pipeline" | "mock",
   *     "metadata": { ... }   // optional
   *   }
   *
   *   Non-200
   *   {
   *     "error": { "code": "no_specific_guidance" | ..., "message": "..." }
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
   * Pull the structured critique out of the server response. Accepts a
   * few shapes for forward compatibility:
   *
   *   { rubric_scores: {...}, prose: '...' }
   *   { scores: {...}, prose: '...' }
   *   { rubric_scores: {...}, text: '...' }
   *
   * Returns { rubric_scores, prose, provider, metadata } or null on miss.
   */
  function _extractCritique(response) {
    if (!response || typeof response !== 'object') return null;
    var scores = response.rubric_scores || response.scores || null;
    var prose  = response.prose || response.text || response.output || '';
    if (typeof prose !== 'string') prose = '';
    // Treat empty critique as a miss — at least one of scores/prose must
    // carry content for a useful result.
    var hasScores = scores
      && typeof scores === 'object'
      && Object.keys(scores).length > 0;
    if (!hasScores && !prose.length) return null;
    return {
      rubric_scores: scores || {},
      prose:         prose,
      provider:      response.provider || response.provider_id || null,
      metadata:      response.metadata || null,
    };
  }

  // ── Result rendering ─────────────────────────────────────────────────

  /**
   * Render the rubric scores as a small table inside `.ora-cap-result`.
   * Each row carries a criterion, its numeric score, and a short comment.
   * Scores may be strings or numbers; we coerce to string for display.
   *
   * The DOM is built defensively (createElement / textContent only) to
   * avoid HTML injection from provider responses — critique text is
   * adversarial-friendly territory.
   */
  function _renderRubricTable(resultEl, rubricScores) {
    if (!resultEl || typeof document === 'undefined') return;
    if (!rubricScores || typeof rubricScores !== 'object') return;

    var keys = Object.keys(rubricScores);
    if (!keys.length) return;

    // Avoid duplicating the table across re-renders.
    var prior = resultEl.querySelector('.ora-cap-result__rubric');
    if (prior && prior.parentNode) prior.parentNode.removeChild(prior);

    var table = document.createElement('table');
    table.className = 'ora-cap-result__rubric';

    var thead = document.createElement('thead');
    var headRow = document.createElement('tr');
    ['Criterion', 'Score', 'Comment'].forEach(function (label) {
      var th = document.createElement('th');
      th.textContent = label;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    var tbody = document.createElement('tbody');
    keys.forEach(function (criterion) {
      var entry = rubricScores[criterion];
      var score = '';
      var comment = '';
      if (entry && typeof entry === 'object') {
        if (entry.score != null) score = String(entry.score);
        if (typeof entry.comment === 'string') comment = entry.comment;
        else if (typeof entry.note === 'string') comment = entry.note;
      } else if (entry != null) {
        // Allow shorthand: `{ composition: 7 }` — number only.
        score = String(entry);
      }

      var row = document.createElement('tr');
      var cellName = document.createElement('td');
      cellName.textContent = String(criterion);
      var cellScore = document.createElement('td');
      cellScore.textContent = score;
      var cellComment = document.createElement('td');
      cellComment.textContent = comment;
      row.appendChild(cellName);
      row.appendChild(cellScore);
      row.appendChild(cellComment);
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    resultEl.appendChild(table);
  }

  /**
   * Render the prose section as a `<div>` inside `.ora-cap-result`. The
   * prose is plain text — we don't try to parse markdown — so it lands in
   * a paragraph with `white-space: pre-wrap` semantics via textContent.
   */
  function _renderProse(resultEl, prose) {
    if (!resultEl || typeof document === 'undefined') return;
    if (typeof prose !== 'string' || !prose.length) return;

    var prior = resultEl.querySelector('.ora-cap-result__prose');
    if (prior && prior.parentNode) prior.parentNode.removeChild(prior);

    var box = document.createElement('div');
    box.className = 'ora-cap-result__prose';
    // Use a <pre>-like wrapper so newlines survive without HTML parsing.
    box.style.whiteSpace = 'pre-wrap';
    box.textContent = prose;
    resultEl.appendChild(box);
  }

  /**
   * Locate (or create, if the UI has not produced one) the
   * `.ora-cap-result` container and render the rubric + prose into it.
   * If the invocation UI has not mounted yet (no `.ora-cap-result`
   * present), we synthesise a host container so the critique is still
   * visible to the user — albeit without the UI's chrome.
   */
  function _renderCritique(hostEl, extracted) {
    if (!hostEl || typeof hostEl.querySelector !== 'function') return;
    var resultEl = hostEl.querySelector('.ora-cap-result');
    if (!resultEl && typeof document !== 'undefined') {
      resultEl = document.createElement('div');
      resultEl.className = 'ora-cap-result';
      hostEl.appendChild(resultEl);
    }
    if (!resultEl) return;
    _renderRubricTable(resultEl, extracted.rubric_scores);
    _renderProse(resultEl, extracted.prose);
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
      if (!detail || detail.slot !== 'image_critique') return Promise.resolve(null);
      var inputs = detail.inputs || {};

      var imageUrl = _normalizeImageRef(inputs.image);
      if (!imageUrl) {
        var err = _synthError(
          'no_specific_guidance',
          'image_critique requires an image input.'
        );
        if (state.ui && typeof state.ui.renderError === 'function') {
          try { state.ui.renderError({ code: err.code, message: err.message }); } catch (_e) { /* swallow */ }
        }
        _emit(state.hostEl, 'capability-error', {
          slot:    'image_critique',
          code:    err.code,
          message: err.message,
        });
        return Promise.reject(err);
      }

      var rubric = (typeof inputs.rubric === 'string') ? inputs.rubric.trim() : '';
      var genre  = (typeof inputs.genre === 'string')  ? inputs.genre.trim()  : '';
      var depth  = (typeof inputs.depth === 'string')  ? inputs.depth.trim()  : '';
      if (!VALID_DEPTHS[depth]) depth = DEFAULT_DEPTH;

      // §3.8 fix path: the slot fails with `no_specific_guidance` when no
      // rubric is supplied AND no inferable genre is available. We pass
      // the empty values through to the server so it can either default
      // or refuse — but we surface the error eagerly when both are blank
      // to avoid a needless round-trip.
      if (!rubric && !genre) {
        var noGuide = _synthError(
          'no_specific_guidance',
          'image_critique needs at least a rubric or a genre.'
        );
        if (state.ui && typeof state.ui.renderError === 'function') {
          try { state.ui.renderError({ code: noGuide.code, message: noGuide.message }); } catch (_e) { /* swallow */ }
        }
        _emit(state.hostEl, 'capability-error', {
          slot:    'image_critique',
          code:    noGuide.code,
          message: noGuide.message,
        });
        return Promise.reject(noGuide);
      }

      var payload = {
        image_data_url: imageUrl,
        rubric:         rubric,
        genre:          genre,
        depth:          depth,
      };
      if (detail.provider_override || inputs.provider_override) {
        payload.provider_override = detail.provider_override || inputs.provider_override;
      }
      if (detail.mock || inputs.mock) {
        payload.mock = true;
      }

      return _callServer(state.endpoint, payload, state.fetchImpl).then(function (response) {
        var extracted = _extractCritique(response);
        if (!extracted) {
          throw _synthError('model_unavailable',
            'Provider returned a response with no critique data.');
        }

        var resultPayload = {
          output:        extracted.prose,
          rubric_scores: extracted.rubric_scores,
          prose:         extracted.prose,
          provider:      extracted.provider,
          metadata:      extracted.metadata,
        };
        // Hand the prose to the invocation UI's text-output renderer so
        // it picks up its standard chrome (loading-clear, status pill).
        // The structured rubric table is rendered separately into the
        // same `.ora-cap-result` panel below.
        if (state.ui && typeof state.ui.renderResult === 'function') {
          try {
            state.ui.renderResult({
              output:   extracted.prose,
              provider: extracted.provider,
              metadata: extracted.metadata,
            });
          } catch (_e) { /* swallow */ }
        }
        _renderCritique(state.hostEl, extracted);

        _emit(state.hostEl, 'capability-result', {
          slot:          'image_critique',
          output:        extracted.prose,
          rubric_scores: extracted.rubric_scores,
          prose:         extracted.prose,
          provider:      extracted.provider,
          metadata:      extracted.metadata,
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
          slot:    'image_critique',
          code:    code,
          message: message,
        });
        throw err;
      });
    }

    function _onCapabilityDispatch(evt) {
      if (!evt || !evt.detail) return;
      if (evt.detail.slot !== 'image_critique') return;
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

    function setUI(ui)        { state.ui = ui || null; }
    function setEndpoint(ep)  { state.endpoint = ep || DEFAULT_ENDPOINT; }
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
    _extractCritique:   _extractCritique,
    _statusToCode:      _statusToCode,
    _normalizeImageRef: _normalizeImageRef,
    _renderRubricTable: _renderRubricTable,
    _renderProse:       _renderProse,
    _renderCritique:    _renderCritique,
    DEFAULT_ENDPOINT:   DEFAULT_ENDPOINT,
    DEFAULT_DEPTH:      DEFAULT_DEPTH,
    VALID_DEPTHS:       VALID_DEPTHS,
    _getActive: function () { return _activeController; },
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraCapabilityImageCritique = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
