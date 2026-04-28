/**
 * ora-visual-compiler / validator.js
 * Two-layer validation.
 *
 * Layer 1 — structural (synchronous, always available):
 *   Checks required envelope fields and known type enum. Sufficient for WP-1.1
 *   tests and all situations where Ajv is not yet loaded.
 *
 * Layer 2 — full schema (synchronous after init(), Ajv-based):
 *   Validates against JSON Schema 2020-12 definitions from WP-0.2.
 *   Enabled by calling OraVisualCompiler.init({ ajvValidateFn }) where
 *   ajvValidateFn is the result of ajv.compile(envelopeSchema). See
 *   ajv-init.js (WP-1.2a) for the bootstrap that wires this up.
 *   Until init() is called, validate() returns Layer 1 results only.
 *
 * Depends on: errors.js
 * Load order: errors.js → validator.js → renderers/stub.js → dispatcher.js → index.js
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};

window.OraVisualCompiler._validator = (function () {

  const { CODES, make } = window.OraVisualCompiler.errors;

  // Exactly the 22 types in envelope.json §type enum.
  const KNOWN_TYPES = new Set([
    'comparison', 'time_series', 'distribution', 'scatter', 'heatmap', 'tornado',
    'causal_loop_diagram', 'stock_and_flow', 'causal_dag', 'fishbone',
    'decision_tree', 'influence_diagram', 'ach_matrix', 'quadrant_matrix',
    'bow_tie', 'ibis', 'pro_con', 'concept_map',
    'sequence', 'flowchart', 'state', 'c4',
  ]);

  const REQUIRED_FIELDS = [
    'schema_version', 'id', 'type', 'mode_context',
    'relation_to_prose', 'spec', 'semantic_description',
  ];

  const RELATION_TO_PROSE = new Set(['integrated', 'visually_native', 'redundant']);

  // Holds the compiled Ajv validator once init() is called.
  let _ajvValidate = null;

  /**
   * Layer 1: structural validation.
   * Returns { valid: bool, errors: Array, warnings: Array }.
   */
  function validateStructural(raw) {
    const errors = [];
    const warnings = [];

    if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
      errors.push(make(CODES.E_MISSING_FIELD, 'Spec must be a JSON object', ''));
      return { valid: false, errors, warnings };
    }

    // Strip _note field (test-harness convention; see WP-0.2 notes).
    if ('_note' in raw) {
      warnings.push(make(CODES.W_NOTE_FIELD_STRIPPED,
        '_note field stripped before validation (test-harness convention)'));
    }
    // Work on a copy so callers are not mutated.
    const spec = Object.assign({}, raw);
    delete spec._note;

    // Required fields
    for (const f of REQUIRED_FIELDS) {
      if (!(f in spec) || spec[f] === null || spec[f] === undefined) {
        errors.push(make(CODES.E_MISSING_FIELD, `Required field '${f}' is absent or null`, f));
      }
    }

    // type must be a known value
    if ('type' in spec && spec.type !== null) {
      if (!KNOWN_TYPES.has(spec.type)) {
        errors.push(make(CODES.E_UNKNOWN_TYPE,
          `Unknown visual type '${spec.type}'. Known types: ${[...KNOWN_TYPES].join(', ')}`,
          'type'));
      }
    }

    // relation_to_prose enum check
    if ('relation_to_prose' in spec && spec.relation_to_prose !== null) {
      if (!RELATION_TO_PROSE.has(spec.relation_to_prose)) {
        errors.push(make(CODES.E_SCHEMA_INVALID,
          `Invalid relation_to_prose '${spec.relation_to_prose}'. ` +
          `'no_visual' is represented by the absence of an envelope, not by this field.`,
          'relation_to_prose'));
      }
    }

    // spec field must be a non-null object
    if ('spec' in spec && (spec.spec === null || typeof spec.spec !== 'object')) {
      errors.push(make(CODES.E_NO_SPEC, `'spec' field must be a non-null object`, 'spec'));
    }

    // schema_version: reject unknown major versions (fail-closed per Protocol §2).
    if ('schema_version' in spec && typeof spec.schema_version === 'string') {
      const major = parseInt(spec.schema_version.split('.')[0], 10);
      if (isNaN(major) || major > 0) {
        // Currently only major version 0 is known. >0 is forward-unknown → fail-closed.
        errors.push(make(CODES.E_SCHEMA_VERSION,
          `Unknown major schema_version '${spec.schema_version}'. This compiler knows v0.x only.`,
          'schema_version'));
      }
    }

    // Accessibility warnings
    if (!spec.title) {
      warnings.push(make(CODES.W_MISSING_TITLE,
        'title is absent; semantic alt-text will be degraded'));
    }
    if (!spec.caption) {
      warnings.push(make(CODES.W_MISSING_CAPTION,
        'caption is absent (Tufte T15: source, period, n should be present)'));
    }

    return { valid: errors.length === 0, errors, warnings };
  }

  /**
   * Layer 2: full Ajv schema validation.
   * Only called when _ajvValidate is set (after init()).
   * Merges any Ajv errors into the error list.
   */
  function validateFull(spec) {
    const layer1 = validateStructural(spec);
    if (!_ajvValidate) return layer1;

    // Strip _note before passing to Ajv (additionalProperties: false rejects it).
    const clean = Object.assign({}, spec);
    delete clean._note;

    const ok = _ajvValidate(clean);
    if (ok) return layer1;

    const ajvErrors = (_ajvValidate.errors || []).map(e =>
      make(CODES.E_SCHEMA_INVALID,
        `[Ajv] ${e.instancePath || '(root)'}: ${e.message}`,
        e.instancePath || undefined)
    );
    return {
      valid: false,
      errors: layer1.errors.concat(ajvErrors),
      warnings: layer1.warnings,
    };
  }

  /**
   * Set the compiled Ajv validate function. Called by OraVisualCompiler.init().
   * ajvValidateFn must be the result of ajv.compile(envelopeSchema).
   */
  function setAjvValidator(ajvValidateFn) {
    _ajvValidate = ajvValidateFn;
  }

  return { validateStructural, validateFull, setAjvValidator, KNOWN_TYPES };
}());
