/**
 * ora-visual-compiler / renderers/c4.js
 *
 * WP-1.2d — C4 architecture renderer (SPATIAL family).
 * Thin wrapper over vendor/structurizr-mini/parser.js + renderer.js.
 *
 * Load order:
 *   errors.js → validator.js → renderers/stub.js → dispatcher.js → index.js →
 *   vendor/structurizr-mini/parser.js → vendor/structurizr-mini/renderer.js →
 *   renderers/c4.js
 *
 * Contract:
 *   render(envelope) → { svg, errors, warnings }
 *   Never throws. Converts parser/layout failures to E_DSL_PARSE /
 *   E_UNRESOLVED_REF / E_SCHEMA_INVALID with JSON-path hints.
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};
window.OraVisualCompiler._renderers = window.OraVisualCompiler._renderers || {};

window.OraVisualCompiler._renderers.c4 = (function () {

  const { CODES, make } = window.OraVisualCompiler.errors;

  // Lazy-read of vendor modules so this file doesn't fail to load when
  // evaluated before the vendor scripts (e.g. tooling that loads renderers
  // alphabetically). The registerRenderer call at the bottom still runs at
  // script-evaluation time; render() is called later.
  function getVendor() {
    const v = (window.OraVisualCompiler._vendor || {}).structurizrMini;
    if (!v || !v.parser || !v.renderer) {
      return null;
    }
    return v;
  }

  /**
   * render(envelope) → { svg, errors, warnings }
   */
  function render(envelope) {
    const errors = [];
    const warnings = [];

    const spec = envelope && envelope.spec ? envelope.spec : {};
    const level = spec.level;
    const dsl = spec.dsl;

    // The envelope-level schema already guaranteed these but we stay
    // defensive — the compiler must never throw from a renderer.
    if (typeof level !== 'string') {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        "spec.level must be a string ('context' or 'container')",
        'spec.level'));
      return { svg: '', errors: errors, warnings: warnings };
    }
    if (level !== 'context' && level !== 'container') {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        "spec.level '" + level + "' not supported at v0.2 " +
        '(context | container only)',
        'spec.level'));
      return { svg: '', errors: errors, warnings: warnings };
    }
    if (typeof dsl !== 'string' || dsl.trim().length === 0) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        'spec.dsl must be a non-empty Structurizr DSL string',
        'spec.dsl'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    const vendor = getVendor();
    if (!vendor) {
      errors.push(make(CODES.E_RENDERER_THREW,
        'structurizr-mini vendor module not loaded. ' +
        'Ensure vendor/structurizr-mini/{parser,renderer}.js load before renderers/c4.js',
        'type'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    // Step 1 — parse DSL.
    let ast;
    try {
      ast = vendor.parser.parse(dsl);
    } catch (err) {
      const code = err && err.kind === 'unresolved_ref'
        ? CODES.E_UNRESOLVED_REF
        : CODES.E_DSL_PARSE;
      const locus = err && (err.line || err.col)
        ? ' [line ' + (err.line || 0) + ':' + (err.col || 0) + ']'
        : '';
      errors.push(make(code,
        'Structurizr DSL parse failed' + locus + ': ' +
        (err && err.message ? err.message : String(err)),
        'spec.dsl'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    // Step 2 — single-level integrity. The Protocol forbids mixing C4 levels
    // in one view. The schema restricts spec.level to context|container; we
    // verify the DSL actually contains a view matching spec.level.
    const kindWanted = level === 'context' ? 'systemContext' : 'container';
    const matchingViews = (ast.views || []).filter(function (v) {
      return v.kind === kindWanted;
    });

    if ((ast.views || []).length > 0 && matchingViews.length === 0) {
      errors.push(make(CODES.E_SCHEMA_INVALID,
        "spec.level is '" + level + "' but the DSL defines no '" +
        kindWanted + "' view. Single-level-per-view rule (Protocol §3.16).",
        'spec.level'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    // If views exist but the scope of the matching view doesn't resolve to
    // a declared softwareSystem we reject — parser already did this, so
    // this is defensive belt-and-braces.

    // Step 3 — layout + SVG emit.
    let rendered;
    try {
      rendered = vendor.renderer.render(ast, {
        level: level,
        title: envelope.title || '',
        ariaLabel: buildAriaLabel(envelope),
      });
    } catch (err) {
      errors.push(make(CODES.E_RENDERER_THREW,
        'C4 renderer failed: ' + (err && err.message ? err.message : String(err)),
        'type'));
      return { svg: '', errors: errors, warnings: warnings };
    }

    return { svg: rendered.svg, errors: errors, warnings: warnings };
  }

  function buildAriaLabel(envelope) {
    const title = envelope && envelope.title ? envelope.title : 'C4 diagram';
    const sd = envelope && envelope.semantic_description;
    const gist = sd && (sd.level_1_elemental || sd.short_alt);
    return gist ? (title + ' — ' + gist) : title;
  }

  // Register once this module loads. If index.js hasn't yet created the
  // public API we still have _dispatcher.register from dispatcher.js.
  if (window.OraVisualCompiler.registerRenderer) {
    window.OraVisualCompiler.registerRenderer('c4', { render: render });
  } else if (window.OraVisualCompiler._dispatcher &&
             window.OraVisualCompiler._dispatcher.register) {
    window.OraVisualCompiler._dispatcher.register('c4', { render: render });
  }

  return { render: render };

}());
