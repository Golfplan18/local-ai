/**
 * prompt-template-engine.js — WP-7.0.6
 *
 * Mustache-style prompt template engine for Phase 7 prompt templates per
 * `Reference — Toolbar Pack Format.md` §7 and the Visual Intelligence
 * Implementation Plan §12 Q3 / §13.0.
 *
 * Exposed namespace: window.OraPromptTemplateEngine.
 *
 *   OraPromptTemplateEngine.extractVariables(templateString)
 *     → ['name', 'name', ...]   (in declaration order; deduplicated)
 *
 *   OraPromptTemplateEngine.parseToken(rawToken)
 *     → { name: string, default: string|null }
 *
 *   OraPromptTemplateEngine.render(templateString, values, options?)
 *     → string                  (rendered template)
 *     throws                    (declared-error class on missing or type-mismatch)
 *
 *   OraPromptTemplateEngine.RenderError                — thrown on any failure
 *
 * ── Mustache subset supported ────────────────────────────────────────────────
 *
 *   ✓ {{name}}                                — variable interpolation
 *   ✓ {{name|default}}                        — default value when name unset
 *   ✓ Whitespace inside braces                — {{ name }} / {{ name | default }}
 *   ✓ Multi-character defaults                — {{style|art deco}}
 *   ✓ Variable extraction in declaration order, deduplicated
 *   ✓ Optional `variables[]` declarations carrying type constraints
 *     (text / image-ref / enum) — values are validated against the declared
 *     type at render time. Defaults are also validated.
 *
 *   ✗ Sections {{#name}}…{{/name}}            — deliberately unsupported
 *   ✗ Inverted sections {{^name}}…{{/name}}   — deliberately unsupported
 *   ✗ Partials {{>name}}                      — deliberately unsupported
 *   ✗ Comments {{! comment }}                 — deliberately unsupported
 *   ✗ Triple-stash {{{html}}}                 — not needed (no HTML escaping)
 *   ✗ Set delimiter {{=<% %>=}}               — deliberately unsupported
 *
 * The engine renders the template; routing (gear_preference vs
 * capability_route) is the runtime's job (WP-7.2.3) per §11.4 of the plan.
 *
 * ── Variable name rules ──────────────────────────────────────────────────────
 *
 * Variable names match /^[A-Za-z_][A-Za-z0-9_]*$/ — alphanumeric + underscore,
 * leading character non-numeric. This lines up with most identifier
 * conventions and lets us reserve `|` as the unambiguous default delimiter.
 *
 * ── Type constraints (per `Reference — Toolbar Pack Format.md` §7) ───────────
 *
 *   text       — any string. Rejects non-string values.
 *   image-ref  — string referring to an image; either an embedded id
 *                ("img:<sha>") or a canvas object id ("obj:<uuid>"). We accept
 *                any non-empty string; deeper resolution is the runtime's job.
 *   enum       — string equal to one of declared `options[]`. Reject
 *                otherwise. `options[]` is required when type is `enum`.
 *
 * ── Error contract ───────────────────────────────────────────────────────────
 *
 * Render failures throw a `RenderError` carrying:
 *   .code     — one of:
 *                 'missing-variable'
 *                 'type-mismatch'
 *                 'invalid-template'
 *                 'invalid-declaration'
 *   .variable — the offending variable name (when applicable)
 *   .message  — human-readable description
 *
 * Callers (WP-7.2.3) can catch and surface a UI prompt, or convert to a
 * fatal-error toast for malformed pack content.
 */

(function () {
  'use strict';

  // ─── Errors ────────────────────────────────────────────────────────────────

  function RenderError(code, message, variable) {
    this.name = 'OraPromptTemplateRenderError';
    this.code = code;
    this.message = message;
    if (variable !== undefined) this.variable = variable;
    if (typeof Error.captureStackTrace === 'function') {
      Error.captureStackTrace(this, RenderError);
    }
  }
  RenderError.prototype = Object.create(Error.prototype);
  RenderError.prototype.constructor = RenderError;

  // ─── Constants ─────────────────────────────────────────────────────────────

  var VAR_NAME_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

  // {{ ... }} — non-greedy, captures the inner content. Allows whitespace
  // inside the braces.
  var TOKEN_RE = /\{\{\s*([^{}]+?)\s*\}\}/g;

  var KNOWN_TYPES = {
    'text':       true,
    'image-ref':  true,
    'enum':       true,
  };

  // ─── Token parsing ─────────────────────────────────────────────────────────

  /**
   * Parse a raw token body (the text between `{{` and `}}`, already trimmed).
   * Recognizes `{{name}}` and `{{name|default}}`.
   *
   * @param {string} raw — token body, e.g. "name" or "name|default"
   * @returns {{name: string, default: string|null}}
   * @throws {RenderError} if the token is malformed.
   */
  function parseToken(raw) {
    if (typeof raw !== 'string') {
      throw new RenderError('invalid-template',
        'Token body must be a string; got ' + typeof raw);
    }
    var trimmed = raw.trim();
    var pipeIdx = trimmed.indexOf('|');
    var name, def;
    if (pipeIdx === -1) {
      name = trimmed;
      def = null;
    } else {
      name = trimmed.slice(0, pipeIdx).trim();
      // Default value preserves internal whitespace but trims the outer pad.
      def = trimmed.slice(pipeIdx + 1).trim();
    }
    if (!VAR_NAME_RE.test(name)) {
      throw new RenderError('invalid-template',
        'Invalid variable name: ' + JSON.stringify(name));
    }
    return { name: name, default: def };
  }

  // ─── Variable extraction ───────────────────────────────────────────────────

  /**
   * Walk the template and return a deduplicated, in-order list of variable
   * names. The default-value suffix (the `|default` portion) is stripped —
   * callers want names, not the embedded defaults.
   *
   * @param {string} template
   * @returns {string[]}
   * @throws {RenderError} if the template contains a malformed token.
   */
  function extractVariables(template) {
    if (typeof template !== 'string') {
      throw new RenderError('invalid-template',
        'Template must be a string; got ' + typeof template);
    }
    var seen = Object.create(null);
    var out = [];
    var match;
    // Reset regex state — TOKEN_RE has the `g` flag.
    TOKEN_RE.lastIndex = 0;
    while ((match = TOKEN_RE.exec(template)) !== null) {
      var token = parseToken(match[1]);
      if (!seen[token.name]) {
        seen[token.name] = true;
        out.push(token.name);
      }
    }
    return out;
  }

  // ─── Type validation ───────────────────────────────────────────────────────

  /**
   * Validate `value` against `declaration` (a `variables[]` entry from a
   * prompt template). Returns true on success; throws RenderError on failure.
   */
  function _validateType(value, declaration) {
    if (declaration == null) return true;
    var type = declaration.type;
    if (type == null) return true;        // untyped → no constraint
    if (!KNOWN_TYPES[type]) {
      throw new RenderError('invalid-declaration',
        'Unknown variable type: ' + JSON.stringify(type),
        declaration.name);
    }
    if (type === 'text') {
      if (typeof value !== 'string') {
        throw new RenderError('type-mismatch',
          'Variable ' + JSON.stringify(declaration.name)
            + ' is declared as text but received ' + typeof value,
          declaration.name);
      }
      return true;
    }
    if (type === 'image-ref') {
      if (typeof value !== 'string' || value.length === 0) {
        throw new RenderError('type-mismatch',
          'Variable ' + JSON.stringify(declaration.name)
            + ' is declared as image-ref but received '
            + (typeof value === 'string' ? 'empty string' : typeof value),
          declaration.name);
      }
      return true;
    }
    if (type === 'enum') {
      if (!Array.isArray(declaration.options) || declaration.options.length === 0) {
        throw new RenderError('invalid-declaration',
          'Variable ' + JSON.stringify(declaration.name)
            + ' is declared as enum but has no options[]',
          declaration.name);
      }
      if (declaration.options.indexOf(value) === -1) {
        throw new RenderError('type-mismatch',
          'Variable ' + JSON.stringify(declaration.name)
            + ' must be one of ' + JSON.stringify(declaration.options)
            + '; received ' + JSON.stringify(value),
          declaration.name);
      }
      return true;
    }
    // Unreachable — KNOWN_TYPES gate already exhausted.
    return true;
  }

  // ─── Render ────────────────────────────────────────────────────────────────

  /**
   * Render `template` with `values`. Variables in `values` override any
   * `|default` literal in the template. Variables missing from both `values`
   * and the template default raise a 'missing-variable' RenderError.
   *
   * `options.variables[]` (optional) — variable declarations as in
   * `Reference — Toolbar Pack Format.md` §7. When present, the engine
   * type-checks each substituted value against its declaration. Declarations
   * with `default: <value>` apply when the template has no inline default
   * AND the value is not in `values`. (Inline `{{name|default}}` literal
   * still wins over a declared `default`.)
   *
   * @param {string} template
   * @param {Object} values   — { name: value, ... }
   * @param {{variables?: Array}} [options]
   * @returns {string}
   * @throws {RenderError}
   */
  function render(template, values, options) {
    if (typeof template !== 'string') {
      throw new RenderError('invalid-template',
        'Template must be a string; got ' + typeof template);
    }
    if (values == null) values = {};
    if (typeof values !== 'object') {
      throw new RenderError('invalid-template',
        'values must be an object; got ' + typeof values);
    }
    var declarations = (options && options.variables) || null;
    var declMap = Object.create(null);
    if (declarations != null) {
      if (!Array.isArray(declarations)) {
        throw new RenderError('invalid-declaration',
          'options.variables must be an array');
      }
      for (var i = 0; i < declarations.length; i++) {
        var d = declarations[i];
        if (d == null || typeof d.name !== 'string' || !VAR_NAME_RE.test(d.name)) {
          throw new RenderError('invalid-declaration',
            'Each variable declaration must have a valid `name` string');
        }
        declMap[d.name] = d;
      }
    }

    var hasOwn = Object.prototype.hasOwnProperty;

    return template.replace(TOKEN_RE, function (whole, body) {
      var token = parseToken(body);
      var name = token.name;
      var inlineDefault = token.default;          // string | null
      var declaration = declMap[name] || null;
      var declaredDefault = declaration && hasOwn.call(declaration, 'default')
        ? declaration.default : undefined;

      // Resolve in priority order:
      //   1. values[name]                                  (caller-supplied)
      //   2. inline `{{name|default}}` literal             (template-author)
      //   3. declaration `{ default: ... }`                (declaration-author)
      //   4. error: missing
      var resolved;
      var resolvedFrom;                            // 'values' | 'inline' | 'declared'
      if (hasOwn.call(values, name) && values[name] !== undefined) {
        resolved = values[name];
        resolvedFrom = 'values';
      } else if (inlineDefault !== null) {
        resolved = inlineDefault;
        resolvedFrom = 'inline';
      } else if (declaredDefault !== undefined) {
        resolved = declaredDefault;
        resolvedFrom = 'declared';
      } else {
        throw new RenderError('missing-variable',
          'Variable ' + JSON.stringify(name) + ' was not supplied and has no default',
          name);
      }

      // Type-check ALL resolved values against the declaration (if any) —
      // including defaults, so a malformed pack surfaces at render time.
      if (declaration != null) {
        _validateType(resolved, declaration);
      }

      // Stringify. Caller-supplied values may be non-string only when
      // un-typed (no declaration); coerce for safe interpolation.
      if (typeof resolved !== 'string') {
        resolved = String(resolved);
      }
      return resolved;
    });
  }

  // ─── Public API ────────────────────────────────────────────────────────────

  var api = {
    extractVariables: extractVariables,
    parseToken:       parseToken,
    render:           render,
    RenderError:      RenderError,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof window !== 'undefined') {
    window.OraPromptTemplateEngine = api;
  }
})();
