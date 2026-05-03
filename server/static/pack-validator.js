/* pack-validator.js — WP-7.0.4
 *
 * Validates Phase 7 toolbar packs against:
 *   1. Structural schema (config/schemas/toolbar-pack.schema.json) via Ajv2020.
 *   2. Lucide name validity for any icon string that isn't an inline SVG —
 *      delegated to OraIconResolver.isValidName (WP-7.0.3).
 *   3. Inline SVG well-formedness — must start with "<svg" (whitespace
 *      tolerated), parse as XML, and declare a viewBox attribute on the
 *      root element.
 *
 * Per-section error messages with locations. Each finding includes:
 *   { severity, code, message, path, source }
 *     severity = "error" | "warning"
 *     code     = stable machine-readable identifier
 *     message  = human-readable, actionable
 *     path     = JSON-path-like string ("toolbars[0].items[2].icon")
 *     source   = "schema" | "lucide" | "svg"
 *
 * Public API (window.OraPackValidator and CommonJS export)
 *   - init(options)                                → Promise<void>
 *       options.ajvValidateFn   pre-compiled Ajv validator (preferred for tests)
 *       options.schema          schema object (used if ajvValidateFn absent)
 *       options.iconResolver    icon-resolver instance (defaults to global
 *                               OraIconResolver) — must expose isValidName(name)
 *       options.svgParser       optional XML parser; defaults to DOMParser in
 *                               browser or an internal regex-tier in Node
 *   - validate(pack)                              → ValidationResult
 *       ValidationResult = { valid: boolean, findings: [Finding, ...] }
 *
 * Implementation notes
 *   - The structural schema is the source of truth for shape; this module
 *     adds two semantic passes (Lucide + SVG) that JSON Schema can't express
 *     cleanly. Schema findings are surfaced first, then semantic findings,
 *     in the same flat list so callers get a single ordered list.
 *   - Pack consumers (WP-7.2.1 loader, WP-7.7.1 install review, WP-7.8.1
 *     default packs) all run in the browser; no Python mirror is required.
 *   - Per §11.15 declarative-only security, this validator never executes
 *     pack content — it only inspects strings. No DOM-mounting of inline
 *     SVGs, no fetch resolution of URLs (URLs are rejected at the schema
 *     layer; the icon_string description forbids them).
 */

(function (root) {
  'use strict';

  // ---- finding shape ------------------------------------------------------

  function _finding(severity, code, message, path, source) {
    return {
      severity: severity,
      code: code,
      message: message,
      path: path,
      source: source
    };
  }

  // ---- AJV adapter --------------------------------------------------------

  // Convert one Ajv error to a Finding. Ajv error shape:
  //   { instancePath, schemaPath, keyword, params, message, ... }
  function _ajvErrorToFinding(err) {
    var path = err.instancePath || '(root)';
    // Ajv encodes paths as "/toolbars/0/items/2/icon"; convert to dotted form.
    if (path && path.indexOf('/') === 0) {
      var parts = path.split('/').slice(1);
      var rebuilt = '';
      for (var i = 0; i < parts.length; i++) {
        var seg = parts[i].replace(/~1/g, '/').replace(/~0/g, '~');
        if (/^\d+$/.test(seg)) rebuilt += '[' + seg + ']';
        else rebuilt += (rebuilt.length === 0 ? '' : '.') + seg;
      }
      path = rebuilt || '(root)';
    }
    var msg = err.message || ('schema violation: ' + err.keyword);
    if (err.keyword === 'additionalProperties' && err.params && err.params.additionalProperty) {
      msg = "unknown field '" + err.params.additionalProperty
          + "' — additionalProperties:false is enforced (§11.15 declarative-only security).";
    } else if (err.keyword === 'required' && err.params && err.params.missingProperty) {
      msg = "missing required field '" + err.params.missingProperty + "'.";
    } else if (err.keyword === 'enum' && err.params && err.params.allowedValues) {
      msg = "value must be one of: " + err.params.allowedValues.join(', ') + ".";
    } else if (err.keyword === 'pattern' && err.params && err.params.pattern) {
      msg = "value does not match expected pattern " + err.params.pattern + " (" + msg + ").";
    } else if (err.keyword === 'oneOf') {
      msg = "must satisfy exactly one of the alternative shapes (e.g. macro step has 'tool' XOR 'capability'; prompt template has 'gear_preference' XOR 'capability_route').";
    } else if (err.keyword === 'anyOf' && (path === '(root)' || path === '')) {
      msg = "pack must contain at least one of toolbars, macros, prompt_templates, composition_templates — empty packs are rejected.";
    }
    return _finding('error', 'schema_' + err.keyword, msg, path, 'schema');
  }

  // ---- inline SVG validation ---------------------------------------------

  function _isInlineSvg(value) {
    if (typeof value !== 'string') return false;
    return value.trim().slice(0, 4).toLowerCase() === '<svg';
  }

  // Fallback XML well-formedness check used in Node when no DOMParser is
  // available. Not a full XML parser — checks: starts with <svg, has a
  // matching close, balanced tag structure (rough), declares viewBox.
  function _validateInlineSvgFallback(svg) {
    var t = svg.trim();
    if (!t || t.slice(0, 4).toLowerCase() !== '<svg') {
      return { valid: false, reason: 'must-start-with-svg-tag' };
    }
    if (!/<\/svg\s*>\s*$/i.test(t)) {
      return { valid: false, reason: 'missing-or-malformed-closing-svg-tag' };
    }
    // Reject script tags + inline event handlers — defense-in-depth even
    // though §11.15 says we don't execute pack content.
    if (/<script[\s>]/i.test(t)) return { valid: false, reason: 'contains-script-tag' };
    if (/\son[a-z]+\s*=\s*["']/i.test(t)) return { valid: false, reason: 'contains-inline-event-handler' };
    // Rough tag balance: count <foo and </foo (excluding self-closing <foo/>).
    // Self-closing forms include "<foo .../>"; we strip those before counting.
    var stripped = t.replace(/<[^>]*\/>/g, '');
    var openCount = (stripped.match(/<[a-zA-Z][^>!?]*?>/g) || []).length;
    var closeCount = (stripped.match(/<\/[a-zA-Z][^>]*>/g) || []).length;
    if (openCount !== closeCount) {
      return { valid: false, reason: 'unbalanced-tags-' + openCount + '-open-vs-' + closeCount + '-close' };
    }
    // viewBox on the root <svg ...> element.
    var rootMatch = t.match(/^<svg\b[^>]*>/i);
    if (!rootMatch) return { valid: false, reason: 'malformed-root-svg-tag' };
    if (!/\bviewBox\s*=\s*["']/.test(rootMatch[0])) {
      return { valid: false, reason: 'missing-viewBox-attribute' };
    }
    return { valid: true };
  }

  function _validateInlineSvgWithDOMParser(svg, parser) {
    try {
      var doc = parser.parseFromString(svg, 'image/svg+xml');
      // DOMParser surfaces parse errors as <parsererror> elements.
      var errs = doc.getElementsByTagName('parsererror');
      if (errs && errs.length > 0) {
        var msg = errs[0].textContent || 'xml parse error';
        return { valid: false, reason: 'xml-parse-error: ' + msg.slice(0, 120) };
      }
      var rootEl = doc.documentElement;
      if (!rootEl || rootEl.tagName.toLowerCase() !== 'svg') {
        return { valid: false, reason: 'root-element-is-not-svg' };
      }
      if (!rootEl.hasAttribute('viewBox')) {
        return { valid: false, reason: 'missing-viewBox-attribute' };
      }
      // Defense-in-depth: still flag scripts / event handlers.
      if (rootEl.getElementsByTagName('script').length > 0) {
        return { valid: false, reason: 'contains-script-tag' };
      }
      var all = rootEl.getElementsByTagName('*');
      for (var i = -1; i < all.length; i++) {
        var el = (i === -1) ? rootEl : all[i];
        var attrs = el.attributes || [];
        for (var j = 0; j < attrs.length; j++) {
          if (/^on[a-z]+$/i.test(attrs[j].name)) {
            return { valid: false, reason: 'contains-inline-event-handler' };
          }
        }
      }
      return { valid: true };
    } catch (e) {
      return { valid: false, reason: 'parse-threw: ' + (e && e.message ? e.message : 'unknown') };
    }
  }

  // ---- icon walker --------------------------------------------------------

  // Walks the pack object collecting every (path, value) pair where the
  // field name is "icon" or "thumbnail". These are the strings that need
  // semantic validation (Lucide name vs inline SVG vs reject).
  function _collectIconLikeFields(pack) {
    var out = [];
    function walk(node, path, parentField) {
      if (node == null) return;
      if (typeof node === 'string') {
        if (parentField === 'icon' || parentField === 'thumbnail') {
          out.push({ path: path, field: parentField, value: node });
        }
        return;
      }
      if (Array.isArray(node)) {
        for (var i = 0; i < node.length; i++) {
          walk(node[i], path + '[' + i + ']', null);
        }
        return;
      }
      if (typeof node === 'object') {
        var keys = Object.keys(node);
        for (var k = 0; k < keys.length; k++) {
          var key = keys[k];
          var nextPath = path === '' ? key : (path + '.' + key);
          walk(node[key], nextPath, key);
        }
      }
    }
    walk(pack, '', null);
    return out;
  }

  // ---- module state -------------------------------------------------------

  var _state = {
    initialized: false,
    ajvValidateFn: null,
    iconResolver: null,
    svgParser: null,
    schemaPath: 'config/schemas/toolbar-pack.schema.json'
  };

  function init(options) {
    options = options || {};

    if (options.ajvValidateFn) {
      _state.ajvValidateFn = options.ajvValidateFn;
    } else if (options.schema) {
      // Try to compile from a passed schema using a vendored Ajv if available.
      var AjvCtor = (typeof root !== 'undefined' && root.Ajv2020) ? root.Ajv2020 : null;
      if (typeof Ajv2020 !== 'undefined' && !AjvCtor) AjvCtor = Ajv2020;  // eslint-disable-line no-undef
      if (typeof require === 'function' && !AjvCtor) {
        try { AjvCtor = require('ajv/dist/2020.js'); } catch (_) { /* ignore */ }
      }
      if (!AjvCtor) {
        return Promise.reject(new Error('OraPackValidator.init: no Ajv2020 available; pass options.ajvValidateFn instead'));
      }
      var ajv = new AjvCtor({
        strict: true,
        strictRequired: 'log',
        allErrors: true,
        allowUnionTypes: true
      });
      _state.ajvValidateFn = ajv.compile(options.schema);
    }

    _state.iconResolver = options.iconResolver
      || (typeof root !== 'undefined' ? root.OraIconResolver : null)
      || null;

    _state.svgParser = options.svgParser
      || (typeof DOMParser !== 'undefined' ? new DOMParser() : null);

    _state.initialized = true;
    return Promise.resolve();
  }

  // ---- main entry ---------------------------------------------------------

  function validate(pack) {
    var findings = [];

    // Defensive: top-level shape must be a plain object before we hand it
    // to the schema (schema would reject arrays / primitives anyway, but
    // a clearer up-front message helps).
    if (pack === null || typeof pack !== 'object' || Array.isArray(pack)) {
      findings.push(_finding(
        'error',
        'pack_not_an_object',
        'pack must be a JSON object at the top level.',
        '(root)',
        'schema'
      ));
      return { valid: false, findings: findings };
    }

    // ---- 1. Schema layer --------------------------------------------------

    if (!_state.ajvValidateFn) {
      findings.push(_finding(
        'error',
        'validator_not_initialized',
        'OraPackValidator.init() must be called before validate(); no compiled schema available.',
        '(root)',
        'schema'
      ));
      return { valid: false, findings: findings };
    }

    var schemaOk = _state.ajvValidateFn(pack);
    if (!schemaOk) {
      var errs = _state.ajvValidateFn.errors || [];
      for (var i = 0; i < errs.length; i++) {
        findings.push(_ajvErrorToFinding(errs[i]));
      }
    }

    // ---- 2. Icon (Lucide name OR inline SVG) layer -----------------------
    //
    // We run this layer even if the schema layer found errors — the user
    // gets the most-actionable, complete list of fixes in one pass. Skip
    // any icon field whose value isn't a string (schema layer already
    // flagged it).

    var iconFields = _collectIconLikeFields(pack);
    for (var f = 0; f < iconFields.length; f++) {
      var entry = iconFields[f];
      var v = entry.value;
      if (typeof v !== 'string' || v.length === 0) continue;

      if (_isInlineSvg(v)) {
        // Inline SVG path: validate well-formedness + viewBox.
        var svgRes = _state.svgParser
          ? _validateInlineSvgWithDOMParser(v, _state.svgParser)
          : _validateInlineSvgFallback(v);
        if (!svgRes.valid) {
          findings.push(_finding(
            'error',
            'inline_svg_invalid',
            "inline SVG rejected (" + svgRes.reason
              + "). Inline SVGs must start with '<svg', be valid XML, and declare a viewBox attribute (spec §9).",
            entry.path,
            'svg'
          ));
        }
      } else {
        // Lucide-name path: cross-reference the canonical name list.
        var bytesPreview = v.length > 60 ? (v.slice(0, 60) + '…') : v;
        // Quick reject for shapes the schema description forbids: URLs,
        // base64 data URIs, anything with whitespace / uppercase.
        if (/^(https?:|file:|data:)/i.test(v)) {
          findings.push(_finding(
            'error',
            'icon_external_reference',
            "icon '" + bytesPreview + "' looks like an external reference (URL or data URI). External resources are forbidden — use a Lucide name or inline SVG (spec §9).",
            entry.path,
            'svg'
          ));
          continue;
        }
        if (!_state.iconResolver || typeof _state.iconResolver.isValidName !== 'function') {
          // Resolver missing — fall back to the schema-level pattern check
          // already enforced by icon_string. Surface a warning so callers
          // know we couldn't cross-check the canonical list.
          findings.push(_finding(
            'warning',
            'icon_resolver_unavailable',
            "icon '" + bytesPreview + "' could not be cross-checked against the Lucide canonical name list — OraIconResolver was not provided. Pattern check passed (lowercase kebab-case).",
            entry.path,
            'lucide'
          ));
          continue;
        }
        if (!_state.iconResolver.isValidName(v)) {
          findings.push(_finding(
            'error',
            'icon_unknown_lucide_name',
            "icon '" + bytesPreview + "' is not a known Lucide name. Either pick a name from server/static/vendor/lucide/names.json or supply an inline SVG starting with '<svg' (spec §9).",
            entry.path,
            'lucide'
          ));
        }
      }
    }

    var hasError = false;
    for (var k = 0; k < findings.length; k++) {
      if (findings[k].severity === 'error') { hasError = true; break; }
    }

    return { valid: !hasError, findings: findings };
  }

  // ---- export -------------------------------------------------------------

  var api = {
    init: init,
    validate: validate,
    // exposed for tests / introspection only:
    _collectIconLikeFields: _collectIconLikeFields,
    _validateInlineSvgFallback: _validateInlineSvgFallback,
    _ajvErrorToFinding: _ajvErrorToFinding,
    _state: _state
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraPackValidator = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);

