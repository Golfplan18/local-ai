/**
 * ora-visual-compiler / errors.js
 * Loaded first. Sets up OraVisualCompiler.errors namespace.
 *
 * Load order: errors.js → validator.js → renderers/stub.js → dispatcher.js → index.js
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};

window.OraVisualCompiler.errors = (function () {

  // Canonical error codes. Prefix E = error (blocks render), W = warning (render proceeds).
  const CODES = {
    // Envelope-level errors
    E_MISSING_FIELD:       'E_MISSING_FIELD',       // required envelope field absent
    E_UNKNOWN_TYPE:        'E_UNKNOWN_TYPE',         // type not in the 22-value enum
    E_SCHEMA_VERSION:      'E_SCHEMA_VERSION',       // unknown major schema_version
    E_SCHEMA_INVALID:      'E_SCHEMA_INVALID',       // full Ajv validation failure
    E_NO_SPEC:             'E_NO_SPEC',              // spec field present but empty/null
    E_RENDERER_NOT_FOUND:  'E_RENDERER_NOT_FOUND',   // no renderer registered for type (internal)
    E_RENDERER_THREW:      'E_RENDERER_THREW',       // renderer threw an uncaught exception

    // Per-type structural errors (semantic invariants the schema cannot express)
    E_GRAPH_CYCLE:         'E_GRAPH_CYCLE',          // cycle in a DAG-type spec
    E_PROB_SUM:            'E_PROB_SUM',             // probabilities don't sum to 1
    E_IBIS_GRAMMAR:        'E_IBIS_GRAMMAR',         // IBIS grammar violation
    E_DSL_PARSE:           'E_DSL_PARSE',            // Mermaid/Structurizr/DAGitty parse failure
    E_UNRESOLVED_REF:      'E_UNRESOLVED_REF',       // id reference in spec doesn't resolve

    // Warnings
    W_STUB_RENDERER:       'W_STUB_RENDERER',        // using placeholder renderer; no real output
    W_UNKNOWN_MAJOR:       'W_UNKNOWN_MAJOR',        // schema_version major > known (forward-compat)
    W_NOTE_FIELD_STRIPPED: 'W_NOTE_FIELD_STRIPPED',  // _note field present and stripped
    W_MISSING_TITLE:       'W_MISSING_TITLE',        // title absent; accessibility degraded
    W_MISSING_CAPTION:     'W_MISSING_CAPTION',      // caption absent (Tufte T15 partial)
    W_DSL_REPAIRED:        'W_DSL_REPAIRED',         // DSL mechanically/heuristically repaired; render proceeded
    W_DSL_REPAIR_FAILED:   'W_DSL_REPAIR_FAILED',    // repair attempts exhausted; see E_DSL_PARSE for final error
    W_STOCK_ISOLATED:      'W_STOCK_ISOLATED',       // stock declared with no attached flows (stock-and-flow)
    W_UNITS_MISMATCH:      'W_UNITS_MISMATCH',       // declared units dimensionally inconsistent (heuristic)
    W_ACH_NONDIAGNOSTIC:   'W_ACH_NONDIAGNOSTIC',    // ach_matrix evidence row is non-diagnostic (all cells same value)
    W_ORPHAN_NODE:         'W_ORPHAN_NODE',          // graph type: node has no incident edges and allow_isolated is false (CLD et al.)
    W_EFFECT_SOLUTION_PHRASED: 'W_EFFECT_SOLUTION_PHRASED',  // fishbone: effect phrased as a solution rather than a problem (soft lint)
    W_NO_CROSS_LINKS:      'W_NO_CROSS_LINKS',       // concept_map: no proposition has is_cross_link:true (Novak marker of integrative learning)
    W_AXES_DEPENDENT:      'W_AXES_DEPENDENT',       // quadrant_matrix: |Pearson r| > 0.7 across items — axes likely correlated, 2×2 framing weakened
    W_ANNOTATION_KIND_DEFERRED: 'W_ANNOTATION_KIND_DEFERRED', // canvas_action=annotate with kind not yet implemented (arrow, badge — WP-5.1)
    W_ANNOTATE_NO_CONTENT: 'W_ANNOTATE_NO_CONTENT',   // canvas_action=annotate but envelope has no annotations array / spec.annotations
    W_ANNOTATION_TARGET_MISSING: 'W_ANNOTATION_TARGET_MISSING', // annotation target_id does not resolve to an SVG element in backgroundLayer

    // Artifact-level adversarial review (WP-2.5) — post-render SVG inspection
    E_ARTIFACT_OVERLAP:            'E_ARTIFACT_OVERLAP',            // semantic elements overlap > 5% (blocks render; force fallback per Protocol §8.5)
    W_ARTIFACT_OVERLAP_MINOR:      'W_ARTIFACT_OVERLAP_MINOR',      // semantic elements touch (≤ 5% overlap); renders anyway
    W_ARTIFACT_TEXT_TRUNCATED:     'W_ARTIFACT_TEXT_TRUNCATED',     // estimated text width > containing bbox × 1.10 (critical if semantic primary label beyond 1.5×)
    E_ARTIFACT_CONTRAST:           'E_ARTIFACT_CONTRAST',           // WCAG 2.1 SC 1.4.3 text contrast < 4.5:1 (blocks render)
    W_ARTIFACT_CONTRAST_GRAPHICAL: 'W_ARTIFACT_CONTRAST_GRAPHICAL', // WCAG 2.1 SC 1.4.11 graphical contrast < 3:1 (warning)
  };

  /**
   * make(code, message, path?) → { code, message, path, severity }
   * path is a dot-separated JSON path string (e.g. 'spec.variables[0].id').
   */
  function make(code, message, path) {
    const severity = code.startsWith('W_') ? 'warning' : 'error';
    const e = { code, message, severity };
    if (path !== undefined) e.path = path;
    return e;
  }

  return { CODES, make };
}());
