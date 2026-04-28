/**
 * ora-visual-compiler / dispatcher.js
 * Type-to-renderer dispatch table.
 *
 * All 22 known types start wired to the stub renderer.
 * WP-1.2 (low-tier) and WP-1.3 (high-tier) replace entries via register().
 *
 * Depends on: errors.js, renderers/stub.js
 * Load order: errors.js → validator.js → renderers/stub.js → dispatcher.js → index.js
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};

window.OraVisualCompiler._dispatcher = (function () {

  const { CODES, make } = window.OraVisualCompiler.errors;
  const stubRenderer     = window.OraVisualCompiler._renderers.stub;

  // Map: type string → { render(envelope) → { svg, errors, warnings } }
  // Populated with stub for all 22 types. Replaced as real renderers land.
  const _registry = {
    // QUANT family — WP-1.2a (Vega-Lite)
    comparison:          stubRenderer,
    time_series:         stubRenderer,
    distribution:        stubRenderer,
    scatter:             stubRenderer,
    heatmap:             stubRenderer,
    tornado:             stubRenderer,

    // CAUSAL family
    causal_loop_diagram: stubRenderer,  // WP-1.3a (D3 force)
    stock_and_flow:      stubRenderer,  // WP-1.3b (XMILE-aligned)
    causal_dag:          stubRenderer,  // WP-1.2c (Graphviz WASM)
    fishbone:            stubRenderer,  // WP-1.3c (deterministic herringbone)

    // DECISION family
    decision_tree:       stubRenderer,  // WP-1.3d (Dagre tree)
    influence_diagram:   stubRenderer,  // WP-1.3e (Graphviz DOT)
    ach_matrix:          stubRenderer,  // WP-1.3f (Vega-Lite heatmap wrapper)
    quadrant_matrix:     stubRenderer,  // WP-1.3g (SVG grid)

    // RISK family
    bow_tie:             stubRenderer,  // WP-1.3h (symmetric SVG)

    // ARGUMENT family
    ibis:                stubRenderer,  // WP-1.3i (Graphviz DOT + grammar)
    pro_con:             stubRenderer,  // WP-1.3j (tree SVG)

    // RELATIONAL family
    concept_map:         stubRenderer,  // WP-1.3k (D3 force / Graphviz)

    // PROCESS family — WP-1.2b (Mermaid)
    sequence:            stubRenderer,
    flowchart:           stubRenderer,
    state:               stubRenderer,

    // SPATIAL family — WP-1.2d (Structurizr DSL)
    c4:                  stubRenderer,
  };

  /**
   * register(type, rendererModule)
   * Called by WP-1.2/1.3 renderer files to replace the stub entry.
   * rendererModule must expose a render(envelope) function.
   */
  function register(type, rendererModule) {
    if (!(type in _registry)) {
      console.warn(`[OraVisualCompiler] register(): unknown type '${type}'. ` +
        'Add it to dispatcher.js and envelope.json before registering.');
    }
    if (typeof rendererModule.render !== 'function') {
      throw new Error(`[OraVisualCompiler] register(): renderer for '${type}' ` +
        'must expose a render(envelope) function');
    }
    _registry[type] = rendererModule;
  }

  /**
   * dispatch(envelope) → { svg, errors, warnings }
   * Looks up the renderer for envelope.type and invokes it.
   * Catches renderer exceptions and converts them to E_RENDERER_THREW errors.
   */
  function dispatch(envelope) {
    const renderer = _registry[envelope.type];

    if (!renderer) {
      // Should not happen if validate() passed, but guard anyway.
      return {
        svg: '',
        errors: [make(CODES.E_RENDERER_NOT_FOUND,
          `No renderer registered for type '${envelope.type}'`, 'type')],
        warnings: [],
      };
    }

    try {
      return renderer.render(envelope);
    } catch (err) {
      return {
        svg: '',
        errors: [make(CODES.E_RENDERER_THREW,
          `Renderer for '${envelope.type}' threw: ${err.message || err}`, 'type')],
        warnings: [],
      };
    }
  }

  /** isStub(type) — true if the type is still on the stub renderer. */
  function isStub(type) {
    return _registry[type] === stubRenderer;
  }

  return { register, dispatch, isStub };
}());
