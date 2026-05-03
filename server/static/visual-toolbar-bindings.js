/**
 * visual-toolbar-bindings.js — WP-7.1.5
 *
 * Action-registry bindings for the universal visual toolbar that need
 * cross-module wiring beyond what the in-line tool handlers in
 * visual-panel.js cover. WP-7.1.5 introduces the first such binding:
 *
 *   tool:ask_ora  →  open the Ask Ora prompt panel; on submit:
 *                      • If OraAskOraRouter.classify(text) returns a slot,
 *                        spin up OraCapabilityInvocationUI against that
 *                        slot, prefilled with { ...prefill, prompt: text },
 *                        and submit() it programmatically against a
 *                        contextProvider that returns the captured
 *                        canvas snapshot.
 *                      • Otherwise, POST the text to /chat as prose.
 *
 * This module deliberately exposes a small, explicit API instead of
 * mutating an existing actionRegistry inside visual-panel.js. The visual
 * panel calls `OraVisualToolbarBindings.attach(actionRegistry, opts)`
 * before rendering, then passes the augmented registry to
 * OraVisualToolbar.render(). That keeps the wiring inspectable and
 * testable in isolation.
 *
 * Public API: window.OraVisualToolbarBindings
 *
 *   .attach(actionRegistry, opts) → mutated registry (same reference)
 *     opts:
 *       getHostElement()       — returns the toolbar item element to
 *                                anchor the prompt panel under. REQUIRED.
 *       getCanvasPanel()       — returns the active visual panel for
 *                                snapshot capture. Optional; falls back
 *                                to window._oraActiveVisualPanel.
 *       getCapabilities()      — returns the parsed capabilities.json
 *                                dict { slots: {...} }. REQUIRED for
 *                                slot dispatch. If absent, every classified
 *                                prompt falls through to the prose path.
 *       getCapabilityHost()    — returns a hidden DOM element to mount
 *                                the OraCapabilityInvocationUI against.
 *                                Optional; defaults to a shared off-screen
 *                                wrapper this module creates.
 *       chatEndpoint           — POST URL for the prose path. Default '/chat'.
 *       fetchFn                — fetch implementation (override in tests).
 *       onProseResult          — callback({ text, response }) when /chat
 *                                returns. Optional.
 *       onProseError           — callback(error) on /chat failure. Optional.
 *       onCapabilityDispatch   — callback(detail) when a slot dispatch
 *                                fires. Optional; useful for tests/logging.
 *
 *   .ASK_ORA_BINDING            — string constant ('tool:ask_ora') for
 *                                 toolbar JSON / tests to reference.
 */
(function (root) {
  'use strict';

  var ASK_ORA_BINDING = 'tool:ask_ora';
  var DEFAULT_CHAT_ENDPOINT = '/chat';

  // ── Capability-host helper ──────────────────────────────────────────────
  //
  // OraCapabilityInvocationUI.init() needs a DOM element to mount its
  // form into. For ask-ora we don't render the form visibly; we just
  // submit() programmatically. So we keep a single off-screen host node
  // around and reuse it across invocations.

  function _ensureCapabilityHost(doc, override) {
    if (override) return override;
    var existing = doc.getElementById('ora-ask-ora-capability-host');
    if (existing) return existing;
    var host = doc.createElement('div');
    host.id = 'ora-ask-ora-capability-host';
    host.setAttribute('aria-hidden', 'true');
    var s = host.style;
    s.position = 'absolute';
    s.left = '-99999px';
    s.top = '-99999px';
    s.width = '1px';
    s.height = '1px';
    s.overflow = 'hidden';
    s.pointerEvents = 'none';
    (doc.body || doc.documentElement).appendChild(host);
    return host;
  }

  // ── Slot dispatch path ──────────────────────────────────────────────────

  function _dispatchToSlot(opts, classification, text) {
    var capabilities = (typeof opts.getCapabilities === 'function')
      ? opts.getCapabilities() : null;
    var UI = root.OraCapabilityInvocationUI;
    if (!UI || !capabilities || !capabilities.slots
        || !capabilities.slots[classification.slot]) {
      // Capability layer unavailable or slot missing — fall back to prose.
      return _dispatchToProse(opts, text, {
        reason: 'slot_unavailable',
        slot: classification.slot
      });
    }

    var doc = opts.doc || (typeof document !== 'undefined' ? document : null);
    if (!doc) return null;
    var host = _ensureCapabilityHost(doc, (typeof opts.getCapabilityHost === 'function')
      ? opts.getCapabilityHost() : null);

    var snapshot = _captureSnapshot(opts);

    var ctl = UI.init({
      hostEl: host,
      capabilities: capabilities,
      slotName: classification.slot,
      contextProvider: function () {
        // The invocation UI inspects this for image-ref / mask widgets.
        // For ask-ora we surface the spatial snapshot under a custom key
        // and the active selection (if any) so image-ref widgets can
        // pre-fill. We can't synthesize an image-ref out of nothing —
        // if the slot needs one and there isn't a selection, the run
        // button stays disabled and the user is told what's missing.
        return {
          canvasSnapshot: snapshot,
          canvasSelection: snapshot && snapshot._activeSelection
            ? snapshot._activeSelection : null
        };
      },
      onDispatch: function (detail) {
        if (typeof opts.onCapabilityDispatch === 'function') {
          try { opts.onCapabilityDispatch(detail); } catch (e) {}
        }
      }
    });

    // Prefill known inputs. The UI's setValue per-control isn't part of
    // the public API; the documented programmatic path is to set form
    // values directly. We use the input names declared in
    // capabilities.json. Unknown keys are ignored by the UI.
    var prefilled = classification.prefilled_inputs || {};
    prefilled.prompt = text;  // always force the user's text as prompt

    // Auto-fill image-ref required inputs from the canvas snapshot's
    // active selection when present. The Ask Ora flow assumes the user's
    // intent is "operate on what I see"; if there's no selection, the
    // capability-invocation-ui's enabled-state predicate will keep the
    // Run button disabled and surface the missing-prereq tooltip.
    var contract = capabilities.slots[classification.slot];
    var requiredInputs = (contract && contract.required_inputs) || [];
    var activeSel = snapshot && (snapshot._activeSelection || snapshot._selectionId);
    requiredInputs.forEach(function (spec) {
      if (spec.type === 'image-ref' && activeSel && prefilled[spec.name] == null) {
        prefilled[spec.name] = activeSel;
      }
    });
    var active = ctl;
    if (active && active.formEl) {
      _applyPrefill(active.formEl, prefilled);
    } else if (active) {
      // Some controllers expose inputControls directly.
      _applyPrefillViaControls(active, prefilled);
    }

    var detail = ctl.submit();
    return {
      mode: 'slot',
      slot: classification.slot,
      detail: detail,
      controller: ctl
    };
  }

  function _applyPrefill(formEl, values) {
    if (!formEl || !values) return;
    Object.keys(values).forEach(function (k) {
      var v = values[k];
      var node = formEl.querySelector('[name="' + k + '"]');
      if (!node) return;
      if (node.tagName === 'INPUT' && node.type === 'checkbox') {
        node.checked = !!v;
      } else if (node.tagName === 'INPUT' && node.type === 'file') {
        // Can't programmatically prefill a file input — skip silently.
      } else {
        try { node.value = v == null ? '' : String(v); } catch (e) {}
        // Fire input event so the UI's enabled-state predicate updates.
        try {
          var evt = new (root.Event || Event)('input', { bubbles: true });
          node.dispatchEvent(evt);
        } catch (e) {}
      }
    });
  }

  function _applyPrefillViaControls(ctl, values) {
    if (!ctl || !values) return;
    var ic = ctl.inputControls || (ctl._state && ctl._state.inputControls) || null;
    if (!ic) return;
    Object.keys(values).forEach(function (k) {
      var entry = ic[k];
      if (entry && typeof entry.setValue === 'function') {
        try { entry.setValue(values[k]); } catch (e) {}
      }
    });
  }

  function _captureSnapshot(opts) {
    var Serializer = root.OraCanvasSerializer;
    if (!Serializer) return null;
    var panel = null;
    try {
      if (typeof opts.getCanvasPanel === 'function') panel = opts.getCanvasPanel();
    } catch (e) { panel = null; }
    if (!panel) panel = root._oraActiveVisualPanel || null;
    if (!panel) return null;
    try {
      if (typeof Serializer.captureFromPanel === 'function') {
        return Serializer.captureFromPanel(panel);
      }
      if (panel.userInputLayer && typeof Serializer.serialize === 'function') {
        return Serializer.serialize(panel.userInputLayer);
      }
    } catch (e) {}
    return null;
  }

  // ── Prose fallback path ─────────────────────────────────────────────────

  function _dispatchToProse(opts, text, meta) {
    var fetchFn = opts.fetchFn || (typeof fetch === 'function' ? fetch : null);
    if (!fetchFn) {
      var err = new Error('No fetch implementation available for prose dispatch');
      if (typeof opts.onProseError === 'function') {
        try { opts.onProseError(err); } catch (e) {}
      }
      return { mode: 'prose', error: err };
    }
    var endpoint = opts.chatEndpoint || DEFAULT_CHAT_ENDPOINT;
    var body = {
      message: text,
      history: [],
      panel_id: 'ask-ora',
      is_main_feed: false,
      _ask_ora_meta: meta || null
    };
    var promise = fetchFn(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (resp) {
      if (typeof opts.onProseResult === 'function') {
        try { opts.onProseResult({ text: text, response: resp }); } catch (e) {}
      }
      return resp;
    }, function (err) {
      if (typeof opts.onProseError === 'function') {
        try { opts.onProseError(err); } catch (e) {}
      }
      throw err;
    });
    return { mode: 'prose', promise: promise };
  }

  // ── Toolbar handler ─────────────────────────────────────────────────────

  function _makeAskOraHandler(opts) {
    return function (item, ctx, evt) {
      var Prompt = root.OraAskOraPrompt;
      if (!Prompt) {
        try { console.warn('[visual-toolbar-bindings] OraAskOraPrompt not loaded'); } catch (e) {}
        return;
      }
      var hostEl = null;
      try {
        if (typeof opts.getHostElement === 'function') hostEl = opts.getHostElement(item, ctx, evt);
      } catch (e) { hostEl = null; }
      // Fallback: anchor under the toolbar button itself if the host
      // accessor isn't wired (or returns null).
      if (!hostEl && evt && evt.currentTarget) hostEl = evt.currentTarget;
      if (!hostEl) {
        try { console.warn('[visual-toolbar-bindings] no host element for ask-ora'); } catch (e) {}
        return;
      }

      // Toggle behavior: if the panel is already open, the click closes it.
      if (typeof Prompt.isOpen === 'function' && Prompt.isOpen()) {
        Prompt.close();
        return;
      }

      Prompt.open({
        hostEl: hostEl,
        getCanvasPanel: opts.getCanvasPanel,
        onSubmit: function (detail) {
          var text = detail && detail.text;
          if (!text) return;
          var Router = root.OraAskOraRouter;
          var classification = Router && typeof Router.classify === 'function'
            ? Router.classify(text) : null;
          if (classification) {
            return _dispatchToSlot(opts, classification, text);
          }
          return _dispatchToProse(opts, text, { reason: 'no_classification' });
        }
      });
    };
  }

  // ── Public attach ───────────────────────────────────────────────────────

  function attach(actionRegistry, opts) {
    actionRegistry = actionRegistry || {};
    opts = opts || {};
    actionRegistry[ASK_ORA_BINDING] = _makeAskOraHandler(opts);
    return actionRegistry;
  }

  // ── Export ──────────────────────────────────────────────────────────────

  var api = {
    attach: attach,
    ASK_ORA_BINDING: ASK_ORA_BINDING,
    DEFAULT_CHAT_ENDPOINT: DEFAULT_CHAT_ENDPOINT,
    // Test introspection
    _dispatchToSlot: _dispatchToSlot,
    _dispatchToProse: _dispatchToProse,
    _ensureCapabilityHost: _ensureCapabilityHost,
    _captureSnapshot: _captureSnapshot
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraVisualToolbarBindings = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
