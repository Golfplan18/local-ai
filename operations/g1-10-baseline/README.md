# G1.10 deployed-schedule baseline

Captured on 2026-07-21 before any installed scheduler, script, or service source was changed.

This directory is an immutable rollback and provenance baseline. `macos/launchagents/` and
`macos/scripts/` are byte-for-byte copies of the installed Mac definitions and script entrypoints.
`cloud/scripts/` and `cloud/crontab.before` are byte-for-byte or exact-text captures from
`cloud-ora`. The SHA-256 identities are recorded in `manifest.json`.

The baseline proves that the installed operational sources existed outside version control before
G1.10. Replacement sources live outside this `g1-10-baseline` directory. Never edit these captures.

## Rollback boundary

The pre-cutover Ora service source is preserved by Git branch
`codex/programming-candidate-preservation` at commit
`97a8b98efe69c367063404c2a6db099ceedf4976`. It is a rejected preservation baseline and MUST NOT be
merged into the accepted runtime. A live rollback may check out that exact branch in
`/Users/oracle/ora`, reinstall the captured LaunchAgents, restore the captured cloud scripts and
crontab, and bootstrap the affected services. Rollback must record the installed-file digests and
service status; it does not certify the rejected branch.

G1.10 cutover is permitted only after replacement sources, a cutover manifest, verification
commands, and the exact reverse procedure are committed and pushed.
