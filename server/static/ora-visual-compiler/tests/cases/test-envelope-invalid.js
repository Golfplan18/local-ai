/**
 * tests/cases/test-envelope-invalid.js
 *
 * Loads every examples/*.invalid.json envelope, calls OraVisualCompiler.compile(),
 * asserts validation fails (errors contains at least one E_* entry, svg empty).
 *
 * The invalid examples include a `_note` top-level field describing the
 * violation. Compile already strips `_note` before Ajv sees it (per
 * W_NOTE_FIELD_STRIPPED convention), so the test doesn't need to pre-process.
 */

'use strict';

const fs   = require('fs');
const path = require('path');

module.exports = {
  label: 'Envelope — invalid examples (must fail validation)',
  run: async function run(ctx, record) {
    const { win, EXAMPLES_DIR } = ctx;
    const files = fs.readdirSync(EXAMPLES_DIR)
      .filter((f) => f.endsWith('.invalid.json'))
      .sort();

    for (const f of files) {
      const envelope = JSON.parse(fs.readFileSync(path.join(EXAMPLES_DIR, f), 'utf-8'));
      try {
        let result = win.OraVisualCompiler.compile(envelope);
        if (result && typeof result.then === 'function') {
          result = await result;
        }
        const errs = result.errors || [];
        const hasErrCode = errs.some((e) => typeof e.code === 'string' && e.code.startsWith('E_'));
        const emptySvg   = !result.svg || result.svg.length === 0;
        const ok = hasErrCode && emptySvg;
        let detail = '';
        if (!ok) {
          detail = 'expected E_* error + empty svg; got ' +
            (errs.length ? ('errors=' + errs.map((e) => e.code).join(',')) : 'no errors') +
            (emptySvg ? '' : '; svg non-empty');
        } else {
          detail = 'rejected with ' + errs.filter((e) => e.code.startsWith('E_')).map((e) => e.code).join(',');
        }
        record(f, ok, detail);
      } catch (err) {
        record(f, false, 'threw: ' + (err.message || err));
      }
    }
  },
};
