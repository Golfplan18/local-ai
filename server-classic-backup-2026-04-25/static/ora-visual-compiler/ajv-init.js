/**
 * ora-visual-compiler / ajv-init.js
 * Ajv 2020-12 bootstrap — upgrades the compiler from Layer 1 (structural only)
 * to Layer 2 (full schema) validation.
 *
 * ─── Handoff note to WP-2.1 / WP-2.3 ──────────────────────────────────────────
 *
 * This file expects:
 *   1. The vendored Ajv bundle at  vendor/ajv/ajv2020.bundle.min.js
 *      (loaded BEFORE this file), exposing `window.Ajv2020`.
 *   2. The compiler core (errors/validator/dispatcher/index) already loaded.
 *   3. A static HTTP route at `/static/visual-schemas/` that serves the
 *      contents of `~/ora/config/visual-schemas/` (23 JSON files: envelope,
 *      semantic_description, spatial_representation, plus specs/*.json).
 *
 *   ---- server.py wiring (TODO for WP-2.1 / WP-2.3 thread) ----
 *   The schemas currently live at `~/ora/config/visual-schemas/`; Flask's
 *   default static dir is `~/ora/server/static/`. Add an explicit static
 *   route mapping:
 *
 *     from flask import send_from_directory
 *     SCHEMAS_DIR = str(Path("~/ora/config/visual-schemas").expanduser())
 *     @app.route('/static/visual-schemas/<path:filename>')
 *     def serve_visual_schemas(filename):
 *         return send_from_directory(SCHEMAS_DIR, filename)
 *
 *   Do NOT copy the schemas into server/static — the canonical location is
 *   ~/ora/config/visual-schemas/ and duplication would drift.
 *
 *   ---- call sites ----
 *   Two acceptable patterns:
 *     A) Index page <script> tags in this order:
 *        <script src="/static/ora-visual-compiler/errors.js"></script>
 *        <script src="/static/ora-visual-compiler/validator.js"></script>
 *        <script src="/static/ora-visual-compiler/renderers/stub.js"></script>
 *        <script src="/static/ora-visual-compiler/dispatcher.js"></script>
 *        <script src="/static/ora-visual-compiler/index.js"></script>
 *        <script src="/static/ora-visual-compiler/vendor/ajv/ajv2020.bundle.min.js"></script>
 *        <script src="/static/ora-visual-compiler/vendor/vega/vega.min.js"></script>
 *        <script src="/static/ora-visual-compiler/vendor/vega-lite/vega-lite.min.js"></script>
 *        <script src="/static/ora-visual-compiler/ajv-init.js"></script>
 *        <script src="/static/ora-visual-compiler/renderers/vega-lite.js"></script>
 *        <script>OraVisualCompiler.bootstrapAjv();</script>
 *     B) Any time after those loads:
 *        OraVisualCompiler.bootstrapAjv({ schemaRoot: '/static/visual-schemas/' });
 *
 *   ---- fallback ----
 *   If any schema fetch fails (network glitch, missing route, 404), this
 *   module logs a `console.warn` and leaves the compiler in Layer 1 mode.
 *   It NEVER throws. Callers that strictly require Layer 2 can await the
 *   returned Promise and branch on resolve value: `{ ok: true }` or
 *   `{ ok: false, reason: <msg> }`.
 *
 * Depends on: errors.js, validator.js, dispatcher.js, index.js, vendor ajv.
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};

(function (C) {

  // The 23 files that must be loaded into Ajv so $refs resolve. Paths are
  // relative to the schemaRoot and MUST match the paths used inside $ref
  // values in envelope.json (per the README.md "JavaScript" recipe).
  const _SCHEMA_FILES = [
    'envelope.json',
    'semantic_description.json',
    'spatial_representation.json',
    'specs/comparison.json',
    'specs/time_series.json',
    'specs/distribution.json',
    'specs/scatter.json',
    'specs/heatmap.json',
    'specs/tornado.json',
    'specs/causal_loop_diagram.json',
    'specs/stock_and_flow.json',
    'specs/causal_dag.json',
    'specs/fishbone.json',
    'specs/decision_tree.json',
    'specs/influence_diagram.json',
    'specs/ach_matrix.json',
    'specs/quadrant_matrix.json',
    'specs/bow_tie.json',
    'specs/ibis.json',
    'specs/pro_con.json',
    'specs/concept_map.json',
    'specs/sequence.json',
    'specs/flowchart.json',
    'specs/state.json',
    'specs/c4.json',
  ];

  const DEFAULT_SCHEMA_ROOT = '/static/visual-schemas/';

  /**
   * Internal: fetch one JSON schema and parse.
   * Works in two modes:
   *   - Browser / jsdom with window.fetch available → use fetch.
   *   - Node-only test harness → consumer injects a custom loader via
   *     options.load (see tests/run.js).
   */
  function _defaultLoad(url) {
    if (typeof fetch === 'function') {
      return fetch(url).then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status + ' on ' + url);
        return r.json();
      });
    }
    return Promise.reject(new Error('No fetch() in this environment; pass options.load to bootstrapAjv()'));
  }

  /**
   * bootstrapAjv(options?) → Promise<{ ok, reason? }>
   *
   * Options:
   *   schemaRoot (string, default '/static/visual-schemas/'):
   *     Base URL for schema files. Trailing slash required.
   *   load (function(url) → Promise<object>, optional):
   *     Custom loader; overrides fetch. Used by the Node test harness to
   *     read schemas from disk.
   *
   * Side effects on success:
   *   - Creates a singleton Ajv2020 instance with { strict: true, allErrors: true }.
   *   - Registers every schema under both its $id and its relative path, so
   *     either $ref style resolves (matches the Python recipe in README.md).
   *   - Compiles the envelope validator and hands it to OraVisualCompiler.init().
   *
   * Side effects on failure:
   *   - console.warn; returns { ok: false, reason }. Does NOT throw.
   */
  function bootstrapAjv(options) {
    options = options || {};
    const root = options.schemaRoot || DEFAULT_SCHEMA_ROOT;
    const load = options.load || _defaultLoad;

    if (typeof window.Ajv2020 !== 'function') {
      const reason = 'Ajv2020 global not found; check vendor load order';
      console.warn('[OraVisualCompiler] bootstrapAjv: ' + reason);
      return Promise.resolve({ ok: false, reason: reason });
    }

    // Ajv options, tuned for the ora-visual schemas:
    //   - allowUnionTypes: several specs use `type:["number","string"]` for
    //     dimensions (width/height). Strict mode rejects unions unless opted-in.
    //   - strictRequired/strictTuples 'log': the decision_tree schema uses
    //     if/then to conditionally require `utility_units` when mode=decision.
    //     Ajv's strictRequired flags this, but the pattern is valid JSON
    //     Schema 2020-12; we log rather than throw so the compile succeeds.
    //   - allErrors: accumulate every validation error instead of short-
    //     circuiting on the first, so callers get actionable diagnostics.
    const ajv = new window.Ajv2020({
      strict: true,
      strictRequired: 'log',
      allErrors: true,
      allowUnionTypes: true,
    });
    C._ajv = ajv;  // expose for debugging

    // Load all schemas in parallel. On ANY failure, bail out cleanly.
    const fetches = _SCHEMA_FILES.map(function (rel) {
      return load(root + rel).then(function (schema) {
        return { rel: rel, schema: schema };
      });
    });

    return Promise.all(fetches).then(
      function (loaded) {
        // Register each schema under both $id and relative-path keys so
        // envelope.json's $ref:"semantic_description.json" and internal
        // $ref:"https://ora.local/..." both resolve.
        for (let i = 0; i < loaded.length; i++) {
          const rel = loaded[i].rel;
          const s   = loaded[i].schema;
          // addSchema rejects duplicate keys; guard defensively.
          try { if (s.$id && !ajv.getSchema(s.$id)) ajv.addSchema(s, s.$id); }
          catch (_) { /* already registered under $id */ }
          try { if (!ajv.getSchema(rel)) ajv.addSchema(s, rel); }
          catch (_) { /* already registered under rel path */ }
        }

        // Locate the envelope schema and compile.
        const envelope = loaded.find(function (e) { return e.rel === 'envelope.json'; });
        if (!envelope) {
          const reason = 'envelope.json missing from loaded schemas';
          console.warn('[OraVisualCompiler] bootstrapAjv: ' + reason);
          return { ok: false, reason: reason };
        }
        let validate;
        try {
          validate = ajv.compile(envelope.schema);
        } catch (err) {
          const reason = 'ajv.compile(envelope) threw: ' + (err.message || err);
          console.warn('[OraVisualCompiler] bootstrapAjv: ' + reason);
          return { ok: false, reason: reason };
        }

        if (typeof C.init !== 'function') {
          const reason = 'OraVisualCompiler.init not loaded; check load order';
          console.warn('[OraVisualCompiler] bootstrapAjv: ' + reason);
          return { ok: false, reason: reason };
        }
        C.init({ ajvValidateFn: validate });
        return { ok: true };
      },
      function (err) {
        const reason = 'schema fetch failed: ' + (err && err.message ? err.message : err);
        console.warn('[OraVisualCompiler] bootstrapAjv: ' + reason + '; falling back to Layer 1 validation.');
        return { ok: false, reason: reason };
      }
    );
  }

  C.bootstrapAjv = bootstrapAjv;
  C._ajvSchemaFiles = _SCHEMA_FILES;  // exposed for tests

}(window.OraVisualCompiler));
