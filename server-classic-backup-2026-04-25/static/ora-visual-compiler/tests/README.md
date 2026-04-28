# ora-visual-compiler / tests

Node + jsdom regression harness introduced as part of **WP-1.2a**. Covers
the entire compiler module: Layer 1 structural validation, Layer 2 Ajv
validation (bootstrapped from the on-disk schemas in
`~/ora/config/visual-schemas/`), the stub renderer, and the Vega-Lite
renderer for the QUANT family.

## Running

```bash
cd ~/ora/server/static/ora-visual-compiler/tests
npm install        # installs ajv, jsdom, vega, vega-lite (test-only)
node run.js
```

Exit code is 0 on pass, 1 on any failure, 2 on harness-level crash.

## Expected output

At the tail of the run:

```
=================================
Results: N/N passed, 0 failed.
```

Example breakdown:

- 22 passes from `test-envelope-valid.js` (one per
  `examples/*.valid.json`; types still on the stub renderer report
  `via stub renderer`).
- 22 passes from `test-envelope-invalid.js` (each deliberately-bad
  example rejected with an `E_*` error and empty SVG).
- 19 passes from `test-vega-lite.js` (≥ 3 hand-written fixtures per QUANT
  type plus one deliberate parse-failure asserting `E_DSL_PARSE`).

## Layout

```
tests/
  package.json          # ajv, jsdom, vega, vega-lite (dev deps only)
  run.js                # harness entry point; jsdom boot + suite loop
  README.md             # this file
  cases/
    test-envelope-valid.js    # examples/*.valid.json → compile must succeed
    test-envelope-invalid.js  # examples/*.invalid.json → compile must fail
    test-vega-lite.js         # hand-written QUANT fixtures + parse-failure
  fixtures/             # reserved for hand-written envelopes beyond examples/
```

## Adding a test case

### New QUANT fixture

Open `cases/test-vega-lite.js` and extend the relevant `<type>Fixtures()`
function. Each fixture is built via the `envelope(type, spec, overrides?)`
helper which supplies a valid envelope skeleton. Make sure the `spec.mark`
stays within the verified subset (see `ALLOWED_MARKS` in
`renderers/vega-lite.js`) and the `spec.caption` includes `source`,
`period`, `n`, and `units` as required by the per-type schema.

### New envelope example

Drop `<new_type>.valid.json` and `<new_type>.invalid.json` into
`~/ora/config/visual-schemas/examples/` and they are picked up
automatically by both envelope-suite runs. The invalid file should include
a top-level `"_note": "..."` explaining the violation; the compiler strips
it (emitting `W_NOTE_FIELD_STRIPPED`) before Ajv runs, so it does not
itself trigger the failure.

### New suite

1. Write `cases/test-<topic>.js` exporting `{ label, run }` where
   `run(ctx, record)` performs assertions.
2. `ctx` carries `{ win, ajvOk, EXAMPLES_DIR, SCHEMAS_DIR }`.
3. `record(name, ok, detail?)` is the single pass/fail reporter; use it
   for every individual assertion so the final tally is meaningful.
4. Register the new file in `run.js`'s `caseFiles` array.

## How the harness boots the compiler

`run.js` constructs a fresh jsdom window, polyfills `structuredClone` and
a minimal `HTMLCanvasElement.getContext` (Vega needs text metrics), and
evaluates every compiler script in the order documented in `ajv-init.js`:

```
errors.js → validator.js → renderers/stub.js → dispatcher.js → index.js
→ vendor/ajv/ajv2020.bundle.min.js
→ vendor/vega/vega.min.js
→ vendor/vega-lite/vega-lite.min.js
→ ajv-init.js
→ renderers/vega-lite.js
```

Ajv bootstrap uses a custom `load` callback that reads schemas from disk
via `fs.readFile`, so the harness does not depend on the server being up.
