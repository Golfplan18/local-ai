/* macro-engine.js — WP-7.2.2
 *
 * Linear-only macro execution engine for the Phase 7 visual pane.
 *
 * Per `Reference — Toolbar Pack Format.md` §6 and the Visual Intelligence
 * Implementation Plan §11.15 / §13.2:
 *   • Macro JSON shape: { id, label, icon, shortcut, steps[] }.
 *   • Each step is exactly one of:
 *         { tool: "<tool_id>",       params: { ... } }
 *         { capability: "<slot_id>", params: { ... } }
 *   • Steps execute strictly in declaration order. No conditionals,
 *     no loops, no flow control. Linear. Period.
 *   • On step failure, execution halts and the engine surfaces which
 *     step failed (zero-based index + the offending step + the error).
 *
 * Variable substitution
 * ---------------------
 * `params` may contain Mustache-style `{{name}}` or `{{name|default}}`
 * tokens (the same subset OraPromptTemplateEngine handles, WP-7.0.6).
 * The engine collects every referenced variable across every step, asks
 * the caller for any not pre-supplied via `prefilledVars`, and then
 * renders each step's params with a stable value map.
 *
 * Substitution walks the params object recursively. Strings get
 * `OraPromptTemplateEngine.render` applied; arrays/objects are walked;
 * primitives (numbers, booleans, null) pass through unchanged.
 *
 * Public API (window.OraMacroEngine)
 * ----------------------------------
 *   extractMacroVariables(macroDef)
 *     → [{ name, type? }]
 *
 *     Returns the deduplicated, in-order list of every variable name
 *     referenced anywhere in the macro's `steps[]`. The `type` field
 *     is reserved for future declarations attached to the macro
 *     itself; absent today, it stays undefined and the caller treats
 *     the variable as untyped text.
 *
 *   runMacro(macroDef, prefilledVars, options?)
 *     → Promise<{ success, completedSteps, error?, results? }>
 *
 *     Executes the macro. `prefilledVars` is a `{ name: value }` map.
 *     Any variable referenced by the macro that is missing from this
 *     map is requested via `options.promptForVariables`, an async
 *     callback `(missing) → Promise<{ name: value, ... }>`. When no
 *     prompter is supplied, missing variables abort with a
 *     `missing-variable` error before any step runs.
 *
 *     Step dispatch is delegated to caller-supplied registries:
 *       options.toolRegistry        — { toolId: async (params, ctx) => any }
 *       options.capabilityRegistry  — { slotId: async (params, ctx) => any }
 *     This matches the actionRegistry pattern visual-toolbar.js uses
 *     and keeps the engine decoupled from the runtime — callers wire
 *     it to live tools or to test stubs.
 *
 *     Result shape:
 *       success         boolean
 *       completedSteps  number — count of steps that ran to completion
 *       results         array  — the resolved value of each completed step
 *       error           object — present when success === false:
 *                           { stepIndex, step, code, message,
 *                             cause? (the underlying Error) }
 *
 *     Error codes:
 *       'malformed-macro'     macroDef shape is invalid
 *       'malformed-step'      a step is neither tool nor capability,
 *                             or has both, or lacks a binding id
 *       'unknown-tool'        step.tool isn't in toolRegistry
 *       'unknown-capability'  step.capability isn't in capabilityRegistry
 *       'missing-variable'    a referenced variable was neither
 *                             pre-supplied nor resolved by the prompter
 *       'render-error'        OraPromptTemplateEngine refused a token
 *       'step-failed'         the dispatched handler threw / rejected
 *       'cancelled'           the prompter signalled cancellation by
 *                             returning null/undefined
 *
 * What this engine does NOT do
 * ----------------------------
 *   • It does not load packs from disk — that's WP-7.2.1 and runs in
 *     parallel. Callers pass a macro definition object directly.
 *   • It does not own the toolRegistry / capabilityRegistry — it
 *     receives them per call. The wiring in visual-panel.js (later
 *     work package) supplies the live registries.
 *   • It does not render the variable-prompt UI — the caller passes
 *     `promptForVariables`, which can route to a modal, prefilled
 *     form, or test stub.
 */

(function (root) {
  'use strict';

  // ---- helpers --------------------------------------------------------------

  function _isObj(x) {
    return x !== null && typeof x === 'object' && !Array.isArray(x);
  }

  function _isFn(x) { return typeof x === 'function'; }

  function _MacroError(code, message, extras) {
    var err = new Error(message);
    err.name = 'OraMacroError';
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

  // Resolve OraPromptTemplateEngine lazily so the engine works in
  // both the browser (where it lives on `window`) and node tests
  // (where the test harness wires it via global injection).
  function _getTemplateEngine() {
    if (root && root.OraPromptTemplateEngine) return root.OraPromptTemplateEngine;
    if (typeof globalThis !== 'undefined' && globalThis.OraPromptTemplateEngine) {
      return globalThis.OraPromptTemplateEngine;
    }
    throw _MacroError('malformed-macro',
      'OraPromptTemplateEngine is not loaded; macro-engine cannot resolve {{vars}}');
  }

  // ---- shape validation -----------------------------------------------------

  function _validateMacroShape(macro) {
    if (!_isObj(macro)) {
      throw _MacroError('malformed-macro', 'Macro definition must be an object');
    }
    if (typeof macro.id !== 'string' || macro.id.length === 0) {
      throw _MacroError('malformed-macro', 'Macro must have a non-empty `id`');
    }
    if (!Array.isArray(macro.steps)) {
      throw _MacroError('malformed-macro',
        'Macro `' + macro.id + '` must have a `steps[]` array');
    }
    if (macro.steps.length === 0) {
      throw _MacroError('malformed-macro',
        'Macro `' + macro.id + '` has zero steps; nothing to run');
    }
    for (var i = 0; i < macro.steps.length; i++) {
      _validateStepShape(macro.steps[i], i);
    }
  }

  function _validateStepShape(step, index) {
    if (!_isObj(step)) {
      throw _MacroError('malformed-step',
        'Step ' + index + ' must be an object', { stepIndex: index, step: step });
    }
    var hasTool = (typeof step.tool === 'string' && step.tool.length > 0);
    var hasCap  = (typeof step.capability === 'string' && step.capability.length > 0);
    if (hasTool && hasCap) {
      throw _MacroError('malformed-step',
        'Step ' + index + ' declares both `tool` and `capability`; pick one',
        { stepIndex: index, step: step });
    }
    if (!hasTool && !hasCap) {
      throw _MacroError('malformed-step',
        'Step ' + index + ' must declare exactly one of `tool` or `capability`',
        { stepIndex: index, step: step });
    }
    if (step.params != null && !_isObj(step.params)) {
      throw _MacroError('malformed-step',
        'Step ' + index + ' `params` must be an object when present',
        { stepIndex: index, step: step });
    }
  }

  // ---- variable extraction --------------------------------------------------

  // Walk a params subtree and collect every {{name}} token referenced.
  function _collectVarsFromValue(value, engine, seen, out) {
    if (typeof value === 'string') {
      // extractVariables throws on malformed tokens — let it bubble.
      var names = engine.extractVariables(value);
      for (var i = 0; i < names.length; i++) {
        if (!seen[names[i]]) {
          seen[names[i]] = true;
          out.push({ name: names[i] });
        }
      }
      return;
    }
    if (Array.isArray(value)) {
      for (var j = 0; j < value.length; j++) {
        _collectVarsFromValue(value[j], engine, seen, out);
      }
      return;
    }
    if (_isObj(value)) {
      for (var k in value) {
        if (Object.prototype.hasOwnProperty.call(value, k)) {
          _collectVarsFromValue(value[k], engine, seen, out);
        }
      }
    }
    // primitives — nothing to extract.
  }

  function extractMacroVariables(macro) {
    _validateMacroShape(macro);
    var engine = _getTemplateEngine();
    var seen = Object.create(null);
    var out  = [];
    for (var i = 0; i < macro.steps.length; i++) {
      var step = macro.steps[i];
      if (step.params != null) {
        _collectVarsFromValue(step.params, engine, seen, out);
      }
    }
    return out;
  }

  // ---- param rendering ------------------------------------------------------

  // Recursively render every string in a params subtree against `vars`.
  // Non-strings pass through. Throws a wrapped 'render-error' on any
  // RenderError surfaced by the template engine.
  function _renderValue(value, vars, engine, stepIndex) {
    if (typeof value === 'string') {
      try {
        return engine.render(value, vars);
      } catch (e) {
        // Surface the underlying RenderError verbatim, but tag it.
        throw _MacroError('render-error',
          'Step ' + stepIndex + ' render failed: ' + (e && e.message),
          { stepIndex: stepIndex, variable: e && e.variable, cause: e });
      }
    }
    if (Array.isArray(value)) {
      var arr = new Array(value.length);
      for (var i = 0; i < value.length; i++) {
        arr[i] = _renderValue(value[i], vars, engine, stepIndex);
      }
      return arr;
    }
    if (_isObj(value)) {
      var out = {};
      for (var k in value) {
        if (Object.prototype.hasOwnProperty.call(value, k)) {
          out[k] = _renderValue(value[k], vars, engine, stepIndex);
        }
      }
      return out;
    }
    return value;
  }

  // ---- runMacro -------------------------------------------------------------

  function runMacro(macro, prefilledVars, options) {
    options = options || {};
    var toolRegistry       = options.toolRegistry       || {};
    var capabilityRegistry = options.capabilityRegistry || {};
    var promptForVariables = options.promptForVariables || null;
    var ctx                = options.context            || {};

    return Promise.resolve().then(function () {
      // 1. Validate the macro's overall shape (and every step's shape).
      //    We do this before doing any UI work so a malformed pack
      //    fails fast with a clear pointer.
      _validateMacroShape(macro);
      var engine = _getTemplateEngine();

      // 2. Collect referenced variables and figure out what's missing.
      var referenced = extractMacroVariables(macro);
      var supplied   = (prefilledVars && _isObj(prefilledVars)) ? prefilledVars : {};
      var missing    = [];
      for (var i = 0; i < referenced.length; i++) {
        var name = referenced[i].name;
        if (!Object.prototype.hasOwnProperty.call(supplied, name)
            || supplied[name] === undefined) {
          missing.push(referenced[i]);
        }
      }

      // 3. If anything is missing, ask the caller. No prompter →
      //    abort cleanly with a missing-variable error.
      var resolveMissing;
      if (missing.length === 0) {
        resolveMissing = Promise.resolve(supplied);
      } else if (!_isFn(promptForVariables)) {
        return _failBeforeRun({
          code: 'missing-variable',
          message: 'Macro requires variables that were not supplied: '
            + missing.map(function (v) { return v.name; }).join(', '),
          missing: missing
        });
      } else {
        resolveMissing = Promise.resolve(promptForVariables(missing, macro))
          .then(function (filled) {
            if (filled == null) {
              throw _MacroError('cancelled',
                'User cancelled the variable prompt; macro not run');
            }
            if (!_isObj(filled)) {
              throw _MacroError('missing-variable',
                'promptForVariables must resolve to an object map');
            }
            // Merge prompter answers over prefilled (prompter wins
            // for variables it answered; pre-supplied values are
            // preserved for any name the prompter didn't touch).
            var merged = {};
            var key;
            for (key in supplied) {
              if (Object.prototype.hasOwnProperty.call(supplied, key)) {
                merged[key] = supplied[key];
              }
            }
            for (key in filled) {
              if (Object.prototype.hasOwnProperty.call(filled, key)) {
                merged[key] = filled[key];
              }
            }
            // Re-check that nothing required is still missing.
            for (var j = 0; j < missing.length; j++) {
              var nm = missing[j].name;
              if (!Object.prototype.hasOwnProperty.call(merged, nm)
                  || merged[nm] === undefined) {
                throw _MacroError('missing-variable',
                  'Variable "' + nm + '" was still not supplied after prompting',
                  { variable: nm });
              }
            }
            return merged;
          });
      }

      // 4. With variables resolved, run the steps in order.
      return resolveMissing.then(function (vars) {
        return _runStepsSequentially(macro, vars, engine, {
          toolRegistry:       toolRegistry,
          capabilityRegistry: capabilityRegistry,
          ctx:                ctx
        });
      });
    }).catch(function (err) {
      // Top-level catch — anything that escapes step-level handling
      // turns into a structured failure result. We do NOT throw —
      // callers want a uniform shape.
      return _normalizeError(err);
    });
  }

  // Helper for the no-prompter missing-vars case — synchronous bail
  // out with the standard failure shape.
  function _failBeforeRun(err) {
    return {
      success: false,
      completedSteps: 0,
      results: [],
      error: {
        stepIndex: -1,
        step: null,
        code: err.code,
        message: err.message,
        missing: err.missing || undefined
      }
    };
  }

  function _normalizeError(err) {
    // An OraMacroError carrying a stepIndex came from inside the
    // step loop or shape validation; shape it for the caller.
    var e = err || {};
    return {
      success: false,
      completedSteps: (typeof e.completedSteps === 'number') ? e.completedSteps : 0,
      results: Array.isArray(e.results) ? e.results : [],
      error: {
        stepIndex: (typeof e.stepIndex === 'number') ? e.stepIndex : -1,
        step:      e.step || null,
        code:      e.code || 'step-failed',
        message:   e.message || String(err),
        cause:     e.cause || (err instanceof Error ? err : undefined),
        variable:  e.variable
      }
    };
  }

  function _runStepsSequentially(macro, vars, engine, dispatch) {
    var results = [];
    var idx     = 0;
    var steps   = macro.steps;

    function runOne() {
      if (idx >= steps.length) {
        return { success: true, completedSteps: results.length, results: results };
      }
      var step = steps[idx];
      var thisIndex = idx;

      // Render this step's params against the resolved variable map.
      var renderedParams;
      try {
        renderedParams = (step.params != null)
          ? _renderValue(step.params, vars, engine, thisIndex)
          : {};
      } catch (renderErr) {
        // _renderValue throws OraMacroError; attach progress and bail.
        renderErr.completedSteps = results.length;
        renderErr.results = results;
        renderErr.step = step;
        return Promise.reject(renderErr);
      }

      // Dispatch to the right registry.
      var handler, kind, slotId;
      if (typeof step.tool === 'string') {
        kind   = 'tool';
        slotId = step.tool;
        handler = dispatch.toolRegistry[slotId];
        if (!_isFn(handler)) {
          var unknownTool = _MacroError('unknown-tool',
            'Step ' + thisIndex + ' references unknown tool "' + slotId + '"',
            { stepIndex: thisIndex, step: step });
          unknownTool.completedSteps = results.length;
          unknownTool.results = results;
          return Promise.reject(unknownTool);
        }
      } else {
        kind   = 'capability';
        slotId = step.capability;
        handler = dispatch.capabilityRegistry[slotId];
        if (!_isFn(handler)) {
          var unknownCap = _MacroError('unknown-capability',
            'Step ' + thisIndex + ' references unknown capability "' + slotId + '"',
            { stepIndex: thisIndex, step: step });
          unknownCap.completedSteps = results.length;
          unknownCap.results = results;
          return Promise.reject(unknownCap);
        }
      }

      // Invoke the handler. It may be sync or async; Promise.resolve
      // normalises both. A throw / rejection halts the macro.
      return Promise.resolve()
        .then(function () { return handler(renderedParams, dispatch.ctx, {
          stepIndex: thisIndex,
          kind:      kind,
          slotId:    slotId,
          macroId:   macro.id
        }); })
        .then(function (value) {
          results.push({ stepIndex: thisIndex, kind: kind, slotId: slotId, value: value });
          idx += 1;
          return runOne();
        }, function (handlerErr) {
          var failure = _MacroError('step-failed',
            'Step ' + thisIndex + ' (' + kind + ':' + slotId + ') failed: '
              + (handlerErr && handlerErr.message ? handlerErr.message : String(handlerErr)),
            { stepIndex: thisIndex, step: step, cause: handlerErr });
          failure.completedSteps = results.length;
          failure.results = results;
          return Promise.reject(failure);
        });
    }

    return runOne();
  }

  // ---- public API -----------------------------------------------------------

  var api = {
    extractMacroVariables: extractMacroVariables,
    runMacro:              runMacro,
    // Test introspection — not part of the documented contract.
    _validateMacroShape:   _validateMacroShape,
    _validateStepShape:    _validateStepShape
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.OraMacroEngine = api;
  }
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this));
