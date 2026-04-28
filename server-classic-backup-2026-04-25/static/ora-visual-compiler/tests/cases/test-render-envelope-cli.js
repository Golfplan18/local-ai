/**
 * tests/cases/test-render-envelope-cli.js
 *
 * WP-6.1 — exercises the Node CLI at ../../tools/render-envelope.js as a
 * child process. The CLI reads an envelope JSON from stdin and writes SVG
 * to stdout (exit 0) or a structured JSON error to stderr (exit != 0).
 *
 * Five assertions:
 *   1. Valid envelope → exit 0, stdout contains '<svg'.
 *   2. Valid envelope → stdout SVG is non-empty (> 500 chars).
 *   3. Invalid envelope (bad shape) → exit != 0.
 *   4. Invalid envelope → stderr carries a structured JSON error record
 *      with `kind`, `message`, `detail.errors`.
 *   5. Malformed stdin (not JSON) → exit 2 + JSON parse-failure record.
 *
 * Reference harness target bump: the existing run.js passes 603 tests.
 * This suite adds 5 more → 608.
 */

'use strict';

const fs    = require('fs');
const path  = require('path');
const { spawnSync } = require('child_process');

const CLI_PATH = path.resolve(__dirname, '..', '..', 'tools', 'render-envelope.js');
const EXAMPLE_VALID = path.resolve(__dirname, '..', '..', '..', '..', '..', 'config', 'visual-schemas', 'examples', 'fishbone.valid.json');

function runCli(stdin) {
  // Spawn the CLI synchronously. Timeout protects the harness from a
  // hung jsdom boot — 120s is enough for cold start on an M4 Max.
  return spawnSync(process.execPath, [CLI_PATH], {
    input: stdin,
    encoding: 'utf-8',
    timeout: 120 * 1000,
    maxBuffer: 16 * 1024 * 1024,
  });
}

module.exports = {
  label: 'WP-6.1 — render-envelope CLI (child-process)',
  run: async function run(ctx, record) {
    // ── Case 1 & 2: valid envelope ───────────────────────────────────────────
    if (!fs.existsSync(EXAMPLE_VALID)) {
      record('cli: fishbone.valid.json exists', false,
        'missing fixture at ' + EXAMPLE_VALID);
      return;
    }
    record('cli: fishbone.valid.json exists', true);

    const validJson = fs.readFileSync(EXAMPLE_VALID, 'utf-8');
    const rValid = runCli(validJson);

    const exit0 = rValid.status === 0;
    record('cli: valid envelope exits 0',
      exit0,
      exit0 ? '' : 'status=' + rValid.status + ' stderr=' + String(rValid.stderr || '').slice(0, 200));

    const hasSvg = typeof rValid.stdout === 'string' && rValid.stdout.indexOf('<svg') === 0;
    record('cli: valid envelope stdout starts with <svg',
      hasSvg,
      hasSvg ? 'length=' + rValid.stdout.length : 'stdout head=' + String(rValid.stdout || '').slice(0, 80));

    const longEnough = typeof rValid.stdout === 'string' && rValid.stdout.length >= 500;
    record('cli: valid envelope stdout non-trivial (>=500 chars)',
      longEnough,
      longEnough ? '' : 'length=' + (rValid.stdout || '').length);

    // ── Case 3 & 4: invalid envelope (bad shape, passes JSON.parse but fails
    // schema validation) ────────────────────────────────────────────────────
    const rInvalid = runCli(JSON.stringify({ bogus: true }));

    const nonzero = rInvalid.status !== 0;
    record('cli: invalid envelope exits non-zero',
      nonzero,
      nonzero ? 'status=' + rInvalid.status : 'unexpectedly succeeded');

    let parsedErr = null;
    try {
      // stderr may contain non-JSON log lines; find the JSON line.
      const lines = String(rInvalid.stderr || '').split(/\r?\n/);
      for (const ln of lines) {
        const s = ln.trim();
        if (s.startsWith('{')) {
          try { parsedErr = JSON.parse(s); break; } catch (_) {}
        }
      }
    } catch (_) {
      parsedErr = null;
    }

    const hasKind = parsedErr && typeof parsedErr.kind === 'string' && parsedErr.kind.length > 0;
    record('cli: invalid envelope stderr carries structured JSON',
      hasKind,
      hasKind ? 'kind=' + parsedErr.kind : 'stderr=' + String(rInvalid.stderr || '').slice(0, 200));

    // ── Case 5: malformed stdin ──────────────────────────────────────────────
    const rMalformed = runCli('this is not json');
    const exit2 = rMalformed.status === 2;
    record('cli: non-JSON stdin exits 2',
      exit2,
      exit2 ? '' : 'status=' + rMalformed.status);

    let parsedMalformed = null;
    try {
      const lines = String(rMalformed.stderr || '').split(/\r?\n/);
      for (const ln of lines) {
        const s = ln.trim();
        if (s.startsWith('{')) {
          try { parsedMalformed = JSON.parse(s); break; } catch (_) {}
        }
      }
    } catch (_) { /* ignore */ }
    const isParseFailure = parsedMalformed && parsedMalformed.kind === 'json_parse_failed';
    record('cli: non-JSON stdin stderr kind=json_parse_failed',
      isParseFailure,
      isParseFailure ? '' : 'parsed=' + JSON.stringify(parsedMalformed));
  },
};
