/* prompt-template-runtime.js — WP-7.2.3
 *
 * Phase 7 prompt-template runtime per Visual Intelligence Implementation
 * Plan §11.4 (routing) and §13.2 (test criterion).
 *
 * Runs prompt templates registered by the pack loader (WP-7.2.1), parses
 * `/slash-command key: value` invocations from the chat input, gathers any
 * missing template variables via a pluggable prompter, renders the template
 * through OraPromptTemplateEngine (WP-7.0.6), and routes the rendered string
 * down one of two paths declared on the template:
 *
 *   • `gear_preference` (1|2|3|4) — text route. POSTs the rendered template
 *     to the existing pipeline endpoint with the chosen Gear, just like a
 *     normal chat turn.
 *   • `capability_route` — image / capability route. Dispatches into the
 *     capability slot registered for that name (WP-7.0.1).
 *
 * Public API (window.OraPromptTemplateRuntime)
 * --------------------------------------------
 *   .init(options)
 *     Wire dependencies. All optional; sane fallbacks pull from globals.
 *       options.engine            — OraPromptTemplateEngine (default global)
 *       options.pipelineEndpoint  — URL string for text route (default '/chat')
 *       options.fetchFn           — fetch implementation (default window.fetch)
 *       options.capabilityDispatch — function(slot, inputs) → Promise|any
 *                                    Default emits a CustomEvent
 *                                    'capability-dispatch' on document.body.
 *       options.promptForVariables — async (missingVars[], template, prefilled)
 *                                    → { name: value, ... } | null (cancel)
 *                                    Default uses a minimal native-prompt
 *                                    fallback when window is present;
 *                                    rejects with 'missing-variable' otherwise.
 *
 *   .register(template)
 *     Register a prompt template. Idempotent for re-registration of the same
 *     id only when the template object is identical; otherwise throws
 *     'already-registered' (mirrors macro/toolbar registries).
 *
 *   .unregister(id)            → boolean
 *   .has(id) / .get(id) / .list()
 *
 *   .parseSlash(input)         → { templateId, args, raw } | null
 *     Parses '/cmd key: value other: "two words"'. Returns null when the
 *     input doesn't start with '/'. Throws 'invalid-slash' for a malformed
 *     command body.
 *
 *   .invoke(idOrSlash, prefilledVars, options?)
 *     → Promise<InvokeResult>
 *     Runs the full pipeline: variable collection → render → route. The
 *     first arg may be a template id, a slash-command id (with or without
 *     leading '/'), or a parsed-slash object from parseSlash.
 *
 *     options.gearPreferenceOverride  — number, override template default.
 *     options.capabilityRouteOverride — string, override template default.
 *     options.promptForVariables      — per-call prompter (overrides init).
 *     options.context                 — passed verbatim to capabilityDispatch
 *                                       and to text-route POST as a tag.
 *
 *     InvokeResult shape:
 *       { success, route, renderedTemplate, response?, error? }
 *       route ∈ 'text' | 'capability'
 *       error: { code, message, ... }
 *
 *     Error codes:
 *       'unknown-template'   id not registered
 *       'invalid-slash'      malformed slash-command text
 *       'invalid-template'   template object missing required fields
 *       'missing-variable'   prompter returned without filling required vars
 *       'render-error'       OraPromptTemplateEngine refused a substitution
 *       'invalid-route'      neither gear_preference nor capability_route set
 *       'route-failed'       transport layer threw / rejected
 *       'cancelled'          prompter returned null (user cancelled)
 *
 * Pack-loader contract (WP-7.2.1)
 * --------------------------------
 * pack-loader.js looks for a registry-shaped object on
 * `options.promptTemplateRegistry` with `register(def)` / `unregister(id)`.
 * This module supplies that contract via .register / .unregister so the
 * loader routes installed templates here automatically. See the module's
 * `attachToPackLoader(loader)` convenience for the one-liner wiring.
 *
 * §11.4 routing detail
 * --------------------
 * For text routes, we POST { message, gear_preference, history?, panel_id?,
 * tag } to the configured pipelineEndpoint (default '/chat'). The Gear
 * system (in boot.py) consumes `gear_preference` to pick the bucket and
 * pipeline depth — the runtime itself is unaware of bucket policy.
 *
 * For capability routes, we hand inputs {slot, inputs:{prompt: rendered,
 * ...prefilledVars}, context} to the configured capabilityDispatch. The
 * default dispatch emits a DOM CustomEvent so unrelated host code (visual
 * panel, job queue) can pick it up without a hard-coded import.
 *
 * §13.2 test criterion
 * --------------------
 * Test at server/static/tests/test-prompt-template-runtime.js exercises:
 *   1. register('/foo {{var}}', gear_preference: 1)
 *   2. invoke('/foo bar') → text-route POST
 *   3. asserts the POST body carries gear_preference=1 and message="foo bar"
 *      (template rendered with var=bar; no command prefix in the message).
 */

(function (root) {
  'use strict';

  // ---- helpers ------------------------------------------------------------

  function _isObj(x) {
    return x !== null && typeof x === 'object' && !Array.isArray(x);
  }
  function _isStr(x) { return typeof x === 'string' && x.length > 0; }
  function _isFn(x) { return typeof x === 'function'; }

  function _RuntimeError(code, message, extras) {
    var err = new Error(message);
    err.name = 'OraPromptTemplateRuntimeError';
    err.code = code;
    if (extras) {
      for (var k in extras) {
        if (Object.prototype.hasOwnProperty.call(extras, k)) {
          err[k] = extras[k];
        }
      }
    }
    return err;
  }

  function _getEngine() {
    if (_state.engine) return _state.engine;
    if (root && root.OraPromptTemplateEngine) return root.OraPromptTemplateEngine;
    if (typeof globalThis !== 'undefined' && globalThis.OraPromptTemplateEngine) {
      return globalThis.OraPromptTemplateEngine;
    }
    throw _RuntimeError('invalid-template',
      'OraPromptTemplateEngine is not loaded; runtime cannot render templates');
  }

  // ---- state --------------------------------------------------------------

  var _state = {
    engine: null,
    pipelineEndpoint: '/chat',
    fetchFn: null,
    capabilityDispatch: null,
    promptForVariables: null,

    // Registered templates keyed by template id.
    templates: Object.create(null),
    // slash command (without leading '/') → template id.
    slashIndex: Object.create(null),
  };

  // ---- init ---------------------------------------------------------------

  function init(options) {
    options = options || {};
    if (options.engine) _state.engine = options.engine;
    if (_isStr(options.pipelineEndpoint)) {
      _state.pipelineEndpoint = options.pipelineEndpoint;
    }
    if (_isFn(options.fetchFn)) _state.fetchFn = options.fetchFn;
    if (_isFn(options.capabilityDispatch)) {
      _state.capabilityDispatch = options.capabilityDispatch;
    }
    if (_isFn(options.promptForVariables)) {
      _state.promptForVariables = options.promptForVariables;
    }
  }

  // ---- registry ----------------------------------------------------------

  function _validateTemplateShape(tpl) {
    if (!_isObj(tpl)) {
      throw _RuntimeError('invalid-template',
        'Template must be an object');
    }
    if (!_isStr(tpl.id)) {
      throw _RuntimeError('invalid-template',
        'Template must have a non-empty `id`');
    }
    if (!_isStr(tpl.template)) {
      throw _RuntimeError('invalid-template',
        'Template `' + tpl.id + '` must have a non-empty `template` string');
    }
    var hasGear = (typeof tpl.gear_preference === 'number');
    var hasCap  = _isStr(tpl.capability_route);
    if (hasGear && hasCap) {
      throw _RuntimeError('invalid-route',
        'Template `' + tpl.id + '` declares both gear_preference and capability_route; pick one');
    }
    if (!hasGear && !hasCap) {
      throw _RuntimeError('invalid-route',
        'Template `' + tpl.id + '` must declare exactly one of gear_preference or capability_route');
    }
    if (hasGear && [1, 2, 3, 4].indexOf(tpl.gear_preference) === -1) {
      throw _RuntimeError('invalid-route',
        'Template `' + tpl.id + '` gear_preference must be 1|2|3|4 (got ' + tpl.gear_preference + ')');
    }
    if (tpl.slash_command != null) {
      if (!_isStr(tpl.slash_command) || tpl.slash_command.charAt(0) !== '/') {
        throw _RuntimeError('invalid-template',
          'Template `' + tpl.id + '` slash_command must be a string beginning with "/"');
      }
    }
  }

  function _slashKey(slashCommand) {
    // slashCommand always begins with '/' per shape validation above.
    return slashCommand.slice(1);
  }

  function register(template) {
    _validateTemplateShape(template);
    var existing = _state.templates[template.id];
    if (existing) {
      // Idempotent same-object re-registration; otherwise reject. This
      // keeps repeated pack-load attempts from silently shadowing prior
      // definitions, but lets the loader call register() twice with the
      // same def object without spurious failure.
      if (existing === template) return template.id;
      throw _RuntimeError('already-registered',
        "Template id '" + template.id + "' is already registered; "
          + 'unregister it first to replace.');
    }
    _state.templates[template.id] = template;
    if (_isStr(template.slash_command)) {
      var key = _slashKey(template.slash_command);
      // Avoid two templates owning the same slash command.
      if (_state.slashIndex[key] && _state.slashIndex[key] !== template.id) {
        delete _state.templates[template.id];
        throw _RuntimeError('already-registered',
          "Slash command '" + template.slash_command + "' is already bound to template '"
            + _state.slashIndex[key] + "'.");
      }
      _state.slashIndex[key] = template.id;
    }
    return template.id;
  }

  function unregister(id) {
    var tpl = _state.templates[id];
    if (!tpl) return false;
    delete _state.templates[id];
    if (_isStr(tpl.slash_command)) {
      var key = _slashKey(tpl.slash_command);
      if (_state.slashIndex[key] === id) {
        delete _state.slashIndex[key];
      }
    }
    return true;
  }

  function has(id)    { return Object.prototype.hasOwnProperty.call(_state.templates, id); }
  function get(id)    { return _state.templates[id] || null; }
  function list() {
    var out = [];
    var keys = Object.keys(_state.templates);
    for (var i = 0; i < keys.length; i++) out.push(_state.templates[keys[i]]);
    return out;
  }

  function clear() {
    _state.templates  = Object.create(null);
    _state.slashIndex = Object.create(null);
  }

  // ---- slash-command parser ----------------------------------------------

  // parseSlash('/cartoon-bg style: Hergé era: 1950')
  //   → { templateId: 'cartoon-bg', args: { style: 'Hergé', era: '1950' }, raw: ... }
  //
  // Quoted strings supported for values that contain whitespace or colons:
  //   /foo bar: "hello world"  →  args.bar === 'hello world'
  //
  // The first token after the '/' is treated as the template id (or as the
  // matching slash_command). Bare positional words after that are folded
  // into a synthetic `_positional` array — consumers that want strict
  // positional → first-required-var binding can read it. invoke() uses
  // _positional to fill the FIRST referenced variable when no key:value
  // pair targets it, which makes `/foo bar` → {{var}} substitution Just
  // Work for single-variable templates (the §13.2 acceptance case).

  function parseSlash(input) {
    if (!_isStr(input)) return null;
    var trimmed = input.replace(/^\s+/, '');
    if (trimmed.charAt(0) !== '/') return null;
    var body = trimmed.slice(1).trim();
    if (body.length === 0) {
      throw _RuntimeError('invalid-slash',
        'Empty slash command (just "/")');
    }
    // Tokenise respecting double-quoted values.
    var tokens = [];
    var i = 0;
    while (i < body.length) {
      // skip whitespace
      while (i < body.length && /\s/.test(body.charAt(i))) i++;
      if (i >= body.length) break;
      if (body.charAt(i) === '"') {
        // quoted literal — find matching quote
        var endQuote = body.indexOf('"', i + 1);
        if (endQuote === -1) {
          throw _RuntimeError('invalid-slash',
            'Unterminated quoted value in slash command');
        }
        tokens.push({ quoted: true, text: body.slice(i + 1, endQuote) });
        i = endQuote + 1;
      } else {
        var start = i;
        while (i < body.length && !/\s/.test(body.charAt(i))) i++;
        tokens.push({ quoted: false, text: body.slice(start, i) });
      }
    }
    if (tokens.length === 0) {
      throw _RuntimeError('invalid-slash',
        'Slash command tokenised to nothing');
    }
    var headTok = tokens.shift();
    if (headTok.quoted) {
      throw _RuntimeError('invalid-slash',
        'Slash command name must not be quoted');
    }
    var templateId = headTok.text;
    // The head token is a slash_command body OR a direct template id.
    // We accept both — a key like 'cartoon-bg' is valid as either.
    if (!/^[A-Za-z0-9][A-Za-z0-9_\-]*$/.test(templateId)) {
      throw _RuntimeError('invalid-slash',
        "Slash command name must be alphanumeric/underscore/dash; got '"
          + templateId + "'");
    }

    // Coalesce key: value pairs; bare tokens become positional.
    var args = {};
    var positional = [];
    var t = 0;
    while (t < tokens.length) {
      var cur = tokens[t];
      // A key:value pair is either:
      //   "key:" + next token  (tokeniser split on whitespace, so colon
      //                         at the END of a bare token signals key)
      //   "key:value"          (no whitespace around colon)
      if (!cur.quoted) {
        var colonIdx = cur.text.indexOf(':');
        if (colonIdx > 0 && colonIdx === cur.text.length - 1) {
          // 'key:' — value is the next token (quoted or bare).
          var key = cur.text.slice(0, colonIdx);
          if (t + 1 >= tokens.length) {
            throw _RuntimeError('invalid-slash',
              "Key '" + key + "' has no value");
          }
          if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
            throw _RuntimeError('invalid-slash',
              "Invalid argument name '" + key + "'");
          }
          args[key] = tokens[t + 1].text;
          t += 2;
          continue;
        }
        if (colonIdx > 0) {
          // 'key:value'
          var k2 = cur.text.slice(0, colonIdx);
          var v2 = cur.text.slice(colonIdx + 1);
          if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(k2)) {
            throw _RuntimeError('invalid-slash',
              "Invalid argument name '" + k2 + "'");
          }
          args[k2] = v2;
          t += 1;
          continue;
        }
      }
      // Bare token — positional.
      positional.push(cur.text);
      t += 1;
    }
    if (positional.length > 0) {
      args._positional = positional;
    }
    return {
      templateId: templateId,
      args: args,
      raw: input
    };
  }

  // ---- invoke -------------------------------------------------------------

  function _resolveTemplate(idOrSlash) {
    if (idOrSlash == null) {
      throw _RuntimeError('unknown-template', 'No template id supplied');
    }
    var parsed = null;
    if (_isObj(idOrSlash) && _isStr(idOrSlash.templateId)) {
      parsed = idOrSlash;
    } else if (_isStr(idOrSlash) && idOrSlash.charAt(0) === '/') {
      parsed = parseSlash(idOrSlash);
    } else if (_isStr(idOrSlash)) {
      parsed = { templateId: idOrSlash, args: {}, raw: idOrSlash };
    } else {
      throw _RuntimeError('unknown-template',
        'invoke() expects a template id, slash string, or parseSlash result');
    }
    var key = parsed.templateId;
    var tpl = _state.templates[key];
    if (!tpl) {
      // Try the slash-command index — same key may be a slash_command body.
      var byId = _state.slashIndex[key];
      if (byId && _state.templates[byId]) {
        tpl = _state.templates[byId];
      }
    }
    if (!tpl) {
      throw _RuntimeError('unknown-template',
        "No prompt template registered for '" + key + "'");
    }
    return { tpl: tpl, parsed: parsed };
  }

  function _collectMissingVars(tpl, suppliedNames) {
    var engine = _getEngine();
    var referenced = engine.extractVariables(tpl.template);
    var declared = Array.isArray(tpl.variables) ? tpl.variables : [];
    var declMap = Object.create(null);
    for (var d = 0; d < declared.length; d++) {
      if (declared[d] && _isStr(declared[d].name)) {
        declMap[declared[d].name] = declared[d];
      }
    }
    var missing = [];
    for (var i = 0; i < referenced.length; i++) {
      var name = referenced[i];
      if (Object.prototype.hasOwnProperty.call(suppliedNames, name)
          && suppliedNames[name] !== undefined) {
        continue;
      }
      // Inline default in the template means engine.render won't fail for
      // this variable — treat it as resolved.
      // We don't have a clean public extractor for inline defaults, so we
      // do a regex sniff matching OraPromptTemplateEngine's TOKEN_RE shape.
      var pattern = new RegExp('\\{\\{\\s*' + _escapeReg(name) + '\\s*\\|', '');
      if (pattern.test(tpl.template)) continue;
      // A declaration default also resolves it.
      if (declMap[name] && Object.prototype.hasOwnProperty.call(declMap[name], 'default')) {
        continue;
      }
      // Otherwise it's missing — pass through the declaration if we have one.
      missing.push(declMap[name] || { name: name });
    }
    return missing;
  }

  function _escapeReg(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function _defaultPromptForVariables(missing) {
    // Minimal fallback: if window.prompt exists, ask one at a time. The
    // production UX path is to pass a richer promptForVariables at init().
    if (typeof window === 'undefined' || !_isFn(window.prompt)) {
      return Promise.resolve(null);
    }
    var out = {};
    for (var i = 0; i < missing.length; i++) {
      var v = missing[i];
      var label = (v && (v.label || v.name)) || ('arg' + i);
      var ans = window.prompt(label + ':');
      if (ans == null) return Promise.resolve(null); // cancelled
      out[v.name] = ans;
    }
    return Promise.resolve(out);
  }

  function _routeText(rendered, gearPreference, ctx) {
    var fetchFn = _state.fetchFn || (typeof root !== 'undefined' && root.fetch) || null;
    if (!_isFn(fetchFn)) {
      return Promise.reject(_RuntimeError('route-failed',
        'No fetch implementation available for text route. Pass options.fetchFn to init().'));
    }
    var body = {
      message: rendered,
      gear_preference: gearPreference,
      history: (ctx && ctx.history) || [],
      panel_id: (ctx && ctx.panel_id) || 'main',
      is_main_feed: (ctx && ctx.is_main_feed) !== false,
      tag: (ctx && ctx.tag) || ''
    };
    return Promise.resolve(fetchFn(_state.pipelineEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })).then(function (response) {
      return { route: 'text', request: body, response: response };
    });
  }

  function _routeCapability(slot, rendered, prefilledVars, ctx) {
    var dispatch = _state.capabilityDispatch;
    if (!_isFn(dispatch)) {
      // Default: emit a CustomEvent the host can listen for.
      dispatch = function (s, inputs, c) {
        if (typeof document === 'undefined' || typeof CustomEvent !== 'function') {
          throw _RuntimeError('route-failed',
            'No capabilityDispatch configured and DOM CustomEvent unavailable.');
        }
        var evt = new CustomEvent('capability-dispatch', {
          detail: { slot: s, inputs: inputs, context: c },
          bubbles: true
        });
        document.body.dispatchEvent(evt);
        return { dispatched: true, slot: s };
      };
    }
    // Combine rendered prompt with any other prefilled variables so callers
    // who care about (e.g.) image refs can pick them out of inputs.
    var inputs = { prompt: rendered };
    for (var k in prefilledVars) {
      if (Object.prototype.hasOwnProperty.call(prefilledVars, k)) {
        // Skip _positional — internal bookkeeping only.
        if (k === '_positional') continue;
        if (!Object.prototype.hasOwnProperty.call(inputs, k)) {
          inputs[k] = prefilledVars[k];
        }
      }
    }
    return Promise.resolve(dispatch(slot, inputs, ctx || {})).then(function (response) {
      return { route: 'capability', slot: slot, inputs: inputs, response: response };
    });
  }

  function invoke(idOrSlash, prefilledVars, options) {
    options = options || {};
    return Promise.resolve().then(function () {
      var resolved = _resolveTemplate(idOrSlash);
      var tpl = resolved.tpl;
      var parsed = resolved.parsed;

      // Merge: caller's prefilledVars > parsed slash args > nothing.
      var supplied = {};
      if (parsed && _isObj(parsed.args)) {
        for (var pk in parsed.args) {
          if (Object.prototype.hasOwnProperty.call(parsed.args, pk)) {
            supplied[pk] = parsed.args[pk];
          }
        }
      }
      if (_isObj(prefilledVars)) {
        for (var sk in prefilledVars) {
          if (Object.prototype.hasOwnProperty.call(prefilledVars, sk)) {
            supplied[sk] = prefilledVars[sk];
          }
        }
      }

      // Bind positional → first referenced variable iff the caller didn't
      // already supply that variable explicitly. Drives the §13.2 case
      // where '/foo bar' fills the single {{var}} without a key:value.
      var engine = _getEngine();
      var referenced = engine.extractVariables(tpl.template);
      var positional = Array.isArray(supplied._positional) ? supplied._positional : [];
      delete supplied._positional;
      if (positional.length > 0) {
        // For each unbound referenced var, take from positional in order.
        var pi = 0;
        for (var ri = 0; ri < referenced.length && pi < positional.length; ri++) {
          var refName = referenced[ri];
          if (!Object.prototype.hasOwnProperty.call(supplied, refName)
              || supplied[refName] === undefined) {
            // For multi-positional cases, fold remaining tail into the last
            // bound var so '/foo hello world' (template {{msg}}) gives
            // msg = 'hello world' rather than dropping 'world'.
            if (ri === referenced.length - 1 && positional.length - pi > 1) {
              supplied[refName] = positional.slice(pi).join(' ');
              pi = positional.length;
            } else {
              supplied[refName] = positional[pi];
              pi += 1;
            }
          }
        }
        // Tail positional with no var to bind to: surface on supplied._extra
        // for capability routes (image-edits cases want raw extras).
        if (pi < positional.length) {
          supplied._extra = positional.slice(pi);
        }
      }

      var missing = _collectMissingVars(tpl, supplied);
      var prompter = options.promptForVariables || _state.promptForVariables;

      var resolveMissing;
      if (missing.length === 0) {
        resolveMissing = Promise.resolve(supplied);
      } else if (!_isFn(prompter)) {
        // Fall through to default native prompt only when window present.
        prompter = _defaultPromptForVariables;
        resolveMissing = Promise.resolve(prompter(missing, tpl, supplied))
          .then(function (filled) {
            if (filled == null) {
              throw _RuntimeError('cancelled',
                'Variable prompt cancelled; template not run');
            }
            return _mergeVars(supplied, filled);
          });
      } else {
        resolveMissing = Promise.resolve(prompter(missing, tpl, supplied))
          .then(function (filled) {
            if (filled == null) {
              throw _RuntimeError('cancelled',
                'Variable prompt cancelled; template not run');
            }
            if (!_isObj(filled)) {
              throw _RuntimeError('missing-variable',
                'promptForVariables must resolve to a { name: value } object');
            }
            return _mergeVars(supplied, filled);
          });
      }

      return resolveMissing.then(function (vars) {
        // Render. Engine throws RenderError on missing/type-mismatch.
        var rendered;
        try {
          rendered = engine.render(tpl.template, vars, {
            variables: tpl.variables
          });
        } catch (e) {
          throw _RuntimeError(
            (e && e.code === 'missing-variable') ? 'missing-variable' : 'render-error',
            (e && e.message) || 'Template render failed',
            { variable: e && e.variable, cause: e });
        }

        // Route: gear_preference (text) or capability_route.
        var gear = (typeof options.gearPreferenceOverride === 'number')
          ? options.gearPreferenceOverride
          : tpl.gear_preference;
        var slot = _isStr(options.capabilityRouteOverride)
          ? options.capabilityRouteOverride
          : tpl.capability_route;

        if (typeof gear === 'number') {
          return _routeText(rendered, gear, options.context).then(function (r) {
            return _ok(rendered, r, tpl);
          });
        }
        if (_isStr(slot)) {
          return _routeCapability(slot, rendered, vars, options.context).then(function (r) {
            return _ok(rendered, r, tpl);
          });
        }
        throw _RuntimeError('invalid-route',
          "Template '" + tpl.id + "' has no gear_preference or capability_route");
      });
    }).catch(function (err) {
      return {
        success: false,
        error: {
          code: (err && err.code) || 'route-failed',
          message: (err && err.message) || String(err),
          variable: err && err.variable,
          cause: err && err.cause
        }
      };
    });
  }

  function _mergeVars(base, extra) {
    var out = {};
    var k;
    for (k in base) {
      if (Object.prototype.hasOwnProperty.call(base, k)) out[k] = base[k];
    }
    for (k in extra) {
      if (Object.prototype.hasOwnProperty.call(extra, k)) out[k] = extra[k];
    }
    return out;
  }

  function _ok(rendered, routed, tpl) {
    return {
      success: true,
      templateId: tpl.id,
      route: routed.route,
      renderedTemplate: rendered,
      slot: routed.slot,
      request: routed.request,
      response: routed.response,
      inputs: routed.inputs
    };
  }

  // ---- pack-loader integration --------------------------------------------

  // Returns a registry-shaped object suitable for
  // OraPackLoader.init({ promptTemplateRegistry: ... }).
  function asPackLoaderRegistry() {
    return {
      register:   register,
      unregister: unregister,
      has:        has,
      get:        get,
      list:       list
    };
  }

  function attachToPackLoader(loader) {
    if (!loader || !_isFn(loader.init)) {
      throw _RuntimeError('invalid-template',
        'attachToPackLoader requires an OraPackLoader-shaped object');
    }
    // The loader's init() merges options with whatever it already had,
    // so callers can re-init to swap registry late if needed.
    return loader.init({ promptTemplateRegistry: asPackLoaderRegistry() });
  }

  // ---- export -------------------------------------------------------------

  var api = {
    init:                  init,
    register:              register,
    unregister:            unregister,
    has:                   has,
    get:                   get,
    list:                  list,
    clear:                 clear,
    parseSlash:            parseSlash,
    invoke:                invoke,
    asPackLoaderRegistry:  asPackLoaderRegistry,
    attachToPackLoader:    attachToPackLoader,
    // Exposed for tests.
    _state:                _state
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (typeof root !== 'undefined') {
    root.OraPromptTemplateRuntime = api;
  }
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis
   : this);
