/**
 * ask-ora-router.js — WP-7.1.5
 *
 * Keyword-ranked classifier that maps a free-text "Ask Ora" prompt to one
 * of the image capability slots declared in `~/ora/config/capabilities.json`.
 * When no rule matches, returns null — caller routes the prompt to the
 * prose chat path instead.
 *
 * The mapping rules below match the WP-7.1.5 plan exactly:
 *
 *   describe|what.*on.*canvas        → image_to_prompt
 *   critique|review|feedback         → image_critique
 *   restyle|in the style of          → image_styles
 *   upscale|sharpen                  → image_upscales
 *   edit|change|remove               → image_edits
 *   generate|create|draw             → image_generates
 *
 * Order matters. We test rules in declaration order and return on the
 * FIRST match. The order is "specific first / generic last" so that, for
 * example, "generate a critique of this canvas" still resolves to
 * `image_critique` (the more specific intent), not `image_generates`.
 *
 * The classifier returns:
 *   { slot: <slot-name>, prefilled_inputs: { ...partial inputs } }
 *
 * `prefilled_inputs` is a partial-input dict the caller can spread into
 * the capability-invocation-ui submit() arguments. The router itself does
 * not know which fields the slot requires — it only fills the obvious
 * ones (`prompt` from the user's text, when applicable).
 *
 * Public API: window.OraAskOraRouter
 *
 *   .classify(text)      → { slot, prefilled_inputs } | null
 *   .RULES               → the declarative rule list (for tests)
 *
 * Pure module — no DOM, no network. Safe to require under jsdom and node.
 */

(function (root) {
  'use strict';

  // ── Rule table ──────────────────────────────────────────────────────────
  //
  // Each rule = { slot, pattern, prefill(text) }.
  // Order is significant — first match wins. `pattern` is a RegExp object
  // so callers can introspect it (RULES is exposed for tests).
  //
  // The `prefill` function builds the partial input dict for the slot.
  // We default to passing the full user text as `prompt` because every
  // slot in the WP-7.1.5 mapping accepts a `prompt` (either as a required
  // input or, in `image_to_prompt` / `image_critique`, as an optional
  // hint that narrows the response). The capability-invocation-ui drops
  // unknown keys, so spreading extra fields is safe.

  var RULES = [
    {
      slot: 'image_to_prompt',
      // "describe X" or "what's on the canvas / what is on the canvas / etc."
      pattern: /\b(describe|what(?:'s|s|\sis)?\s+on\s+(?:the\s+)?canvas)\b/i,
      prefill: function (text) { return { prompt: text }; }
    },
    {
      slot: 'image_critique',
      pattern: /\b(critique|review|feedback)\b/i,
      prefill: function (text) { return { prompt: text }; }
    },
    {
      slot: 'image_styles',
      // "restyle" OR the phrase "in the style of"
      pattern: /\b(restyle|in\s+the\s+style\s+of)\b/i,
      prefill: function (text) { return { prompt: text }; }
    },
    {
      slot: 'image_upscales',
      pattern: /\b(upscale|sharpen)\b/i,
      prefill: function (text) { return { prompt: text }; }
    },
    {
      slot: 'image_edits',
      pattern: /\b(edit|change|remove)\b/i,
      prefill: function (text) { return { prompt: text }; }
    },
    {
      slot: 'image_generates',
      pattern: /\b(generate|create|draw)\b/i,
      prefill: function (text) { return { prompt: text }; }
    }
  ];

  // ── classify ────────────────────────────────────────────────────────────

  function classify(text) {
    if (typeof text !== 'string') return null;
    var trimmed = text.trim();
    if (!trimmed.length) return null;

    for (var i = 0; i < RULES.length; i++) {
      var rule = RULES[i];
      if (rule.pattern.test(trimmed)) {
        var prefill = {};
        try {
          prefill = rule.prefill(trimmed) || {};
        } catch (e) {
          prefill = {};
        }
        return {
          slot: rule.slot,
          prefilled_inputs: prefill
        };
      }
    }
    return null;
  }

  // ── Export ──────────────────────────────────────────────────────────────

  var api = {
    classify: classify,
    RULES: RULES
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraAskOraRouter = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
