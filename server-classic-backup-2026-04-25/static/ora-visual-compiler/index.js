/**
 * ora-visual-compiler / index.js
 * Public API — loaded last.
 *
 * Exposes these functions on the global OraVisualCompiler object:
 *   compile(spec)            → { svg, errors, warnings }
 *   compileWithNav(spec)     → { svg, errors, warnings, ariaDescription }
 *                              (WP-1.5; ariaDescription === null when
 *                              accessibility modules aren't loaded)
 *   validate(spec)           → { valid, errors, warnings }
 *   postProcess(svg)         → svg     (identity; theme hook — override to inject styles)
 *   init(options)            → void    (optional: wires in Ajv for full schema validation)
 *   registerRenderer(t, m)   → void    (WP-1.2/1.3 extension point)
 *
 * Load order (add to index.html in this order):
 *   /static/ora-visual-compiler/errors.js
 *   /static/ora-visual-compiler/validator.js
 *   /static/ora-visual-compiler/renderers/stub.js
 *   /static/ora-visual-compiler/dispatcher.js
 *   /static/ora-visual-compiler/index.js
 *   … vendor libs, palettes, dot-engine, ajv-init, renderers …
 *   /static/ora-visual-compiler/alt-text-generator.js   (WP-1.5)
 *   /static/ora-visual-compiler/aria-annotator.js       (WP-1.5)
 *   /static/ora-visual-compiler/keyboard-nav.js         (WP-1.5)
 *
 * Depends on: errors.js, validator.js, renderers/stub.js, dispatcher.js
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};

(function (C) {

  const { validateStructural, validateFull, setAjvValidator } = C._validator;
  const { dispatch }                                           = C._dispatcher;
  const { register }                                          = C._dispatcher;

  /**
   * _applyArtifactAdversarial(result, envelope) → result
   *
   * Internal helper. Runs the WP-2.5 post-render adversarial reviewer if it's
   * loaded. When the review blocks (any Critical finding), we clear
   * result.svg so the caller renders the fallback (table / prose / placeholder)
   * per Protocol §8.5, and append the Critical findings to result.errors.
   * Non-Critical findings attach to result.warnings.
   *
   * Backward-compatible: when artifactAdversarial is absent, result is
   * returned unchanged.
   */
  function _applyArtifactAdversarial(result, envelope) {
    if (!C.artifactAdversarial || typeof C.artifactAdversarial.review !== 'function') {
      return result;
    }
    if (!result || typeof result.svg !== 'string' || result.svg.length === 0) {
      return result;
    }
    try {
      var review = C.artifactAdversarial.review(result.svg, envelope);
      if (!review || !Array.isArray(review.findings)) return result;
      if (review.blocks) {
        result.svg = '';
        result.errors = (result.errors || []).concat(
          review.findings.filter(function (f) { return f.severity === 'error'; })
        );
        // Preserve warnings too for diagnostics.
        result.warnings = (result.warnings || []).concat(
          review.findings.filter(function (f) { return f.severity !== 'error'; })
        );
      } else {
        result.warnings = (result.warnings || []).concat(review.findings);
      }
    } catch (e) {
      // Reviewer must never break compile(). Swallow and return original.
    }
    return result;
  }

  /**
   * _applyAccessibility(svg, envelope) → { svg, ariaDescription|null }
   *
   * Internal helper. Runs the three accessibility modules (alt-text-generator,
   * aria-annotator, keyboard-nav) in sequence if they've loaded. If any
   * module is missing, degrades gracefully — svg passes through unchanged
   * and ariaDescription is null. This preserves backward compatibility with
   * any harness/caller that loads compile() without the a11y files.
   */
  function _applyAccessibility(svg, envelope) {
    if (typeof svg !== 'string' || svg.length === 0) {
      return { svg: svg, ariaDescription: null };
    }
    const a11y = C.accessibility;
    if (!a11y) return { svg: svg, ariaDescription: null };

    let working = svg;
    if (typeof a11y.decorateAltText === 'function') {
      working = a11y.decorateAltText(working, envelope);
    }
    if (typeof a11y.annotateAria === 'function') {
      working = a11y.annotateAria(working);
    }
    let description = null;
    if (typeof a11y.buildKeyboardNav === 'function') {
      const built = a11y.buildKeyboardNav(working, envelope);
      if (built && typeof built === 'object') {
        working = built.svg || working;
        description = built.ariaDescription || null;
      }
    }
    return { svg: working, ariaDescription: description };
  }

  /**
   * compile(spec) → { svg: string, errors: Array, warnings: Array }
   *
   * spec is a plain JS object — a parsed `ora-visual` block.
   * Returns { svg: '', errors, warnings } on validation failure (never throws).
   * Returns { svg, errors: [], warnings } on success (svg may include stub warnings).
   *
   * When the WP-1.5 accessibility modules are loaded, the returned svg is
   * decorated with <title>/<desc>, role="img", aria-labelledby/-describedby,
   * element-level aria-label/aria-hidden, and tabindex + data-olli-level.
   * Callers that also need the navigation graph should use compileWithNav().
   *
   * Caller MUST check errors.length before rendering the SVG into the DOM.
   * If errors is non-empty, fall back to table or prose per Protocol §8.5.
   */
  function compile(spec) {
    const validation = C._ajvReady ? validateFull(spec) : validateStructural(spec);

    if (!validation.valid) {
      return { svg: '', errors: validation.errors, warnings: validation.warnings };
    }

    // Strip _note before dispatch (mirrors test-harness convention).
    const envelope = Object.assign({}, spec);
    delete envelope._note;

    // Dispatch may be synchronous (stub, sync renderers) OR Promise-returning
    // (Vega-Lite, Mermaid, Graphviz-WASM, etc.). If it's async, we return a
    // Promise<{svg,errors,warnings}>. If sync, we return the plain object.
    // Callers that must support both should `await` the result; Promise.resolve
    // on a plain object is idempotent.
    const dispatched = dispatch(envelope);
    if (dispatched && typeof dispatched.then === 'function') {
      return dispatched.then(function (r) {
        const enriched = _applyAccessibility(r.svg, envelope);
        const out = {
          svg:      enriched.svg,
          errors:   r.errors,
          warnings: validation.warnings.concat(r.warnings || []),
        };
        return _applyArtifactAdversarial(out, envelope);
      });
    }
    const enriched = _applyAccessibility(dispatched.svg, envelope);
    const syncOut = {
      svg:      enriched.svg,
      errors:   dispatched.errors,
      warnings: validation.warnings.concat(dispatched.warnings || []),
    };
    return _applyArtifactAdversarial(syncOut, envelope);
  }

  /**
   * compileWithNav(spec) → { svg, errors, warnings, ariaDescription }
   *
   * Same as compile(), plus returns the Olli-pattern keyboard navigation
   * description used by WP-2.1's visual panel for arrow-key wiring.
   *
   * ariaDescription is null when validation fails, the renderer returns an
   * empty svg, or the accessibility modules are not loaded (backward-compat).
   */
  function compileWithNav(spec) {
    const validation = C._ajvReady ? validateFull(spec) : validateStructural(spec);

    if (!validation.valid) {
      return {
        svg:             '',
        errors:          validation.errors,
        warnings:        validation.warnings,
        ariaDescription: null,
      };
    }

    const envelope = Object.assign({}, spec);
    delete envelope._note;

    const dispatched = dispatch(envelope);
    if (dispatched && typeof dispatched.then === 'function') {
      return dispatched.then(function (r) {
        const enriched = _applyAccessibility(r.svg, envelope);
        const out = {
          svg:             enriched.svg,
          errors:          r.errors,
          warnings:        validation.warnings.concat(r.warnings || []),
          ariaDescription: enriched.ariaDescription,
        };
        return _applyArtifactAdversarial(out, envelope);
      });
    }
    const enriched = _applyAccessibility(dispatched.svg, envelope);
    const syncOut = {
      svg:             enriched.svg,
      errors:          dispatched.errors,
      warnings:        validation.warnings.concat(dispatched.warnings || []),
      ariaDescription: enriched.ariaDescription,
    };
    return _applyArtifactAdversarial(syncOut, envelope);
  }

  /**
   * validate(spec) → { valid: bool, errors: Array, warnings: Array }
   *
   * Runs validation only (no rendering). Useful for pre-flight checks and
   * the Python-side analogue (both layers should agree).
   */
  function validate(spec) {
    return C._ajvReady ? validateFull(spec) : validateStructural(spec);
  }

  /**
   * postProcess(svg) → svg
   *
   * Identity transform by default. Override this function to inject a theme,
   * rough.js treatment, high-contrast mode, or any other post-render aesthetic.
   *
   * The contract: input and output are both SVG strings. The function must not
   * break the semantic element IDs or ARIA attributes added by the compiler.
   *
   * Example override (drop in at WP-1.4):
   *   OraVisualCompiler.postProcess = roughPostProcess;
   */
  function postProcess(svg) {
    return svg;
  }

  /**
   * init(options)
   * Optional. Call to upgrade validation from structural-only to full Ajv.
   *
   * options.ajvValidateFn  — a compiled Ajv validate function from:
   *   ajv.compile(envelopeSchema)  (see README.md JS loading recipe)
   *
   * Until this is called, compile() and validate() use Layer 1 only.
   * WP-1.2 or WP-2.1 should call init() after loading Ajv + schemas.
   */
  function init(options) {
    if (options && typeof options.ajvValidateFn === 'function') {
      setAjvValidator(options.ajvValidateFn);
      C._ajvReady = true;
    }
  }

  /**
   * registerRenderer(type, rendererModule)
   * Called by WP-1.2/1.3 renderer files after this script loads.
   * rendererModule must expose render(envelope) → { svg, errors, warnings }.
   */
  function registerRenderer(type, rendererModule) {
    register(type, rendererModule);
  }

  // ── Public surface ──────────────────────────────────────────────────────────
  C._ajvReady        = false;
  C.compile          = compile;
  C.compileWithNav   = compileWithNav;
  C.validate         = validate;
  C.postProcess      = postProcess;
  C.init             = init;
  C.registerRenderer = registerRenderer;

  // Convenience: expose known types for introspection.
  C.KNOWN_TYPES = C._validator.KNOWN_TYPES;

}(window.OraVisualCompiler));
