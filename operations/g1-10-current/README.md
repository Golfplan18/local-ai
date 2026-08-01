# G1.10 current operational package

This directory is the tracked post-cutover source for every installed Mac and
cloud scheduler surface changed by G1.10. The byte-exact pre-change sources
remain beside it in `operations/g1-10-baseline/`.

The package is intentionally consolidated:

- `macos/` retires five cadence LaunchAgents while preserving
  `com.ora.server`; exact vault writes flow through the restart-safe event
  pipeline already hosted by Ora.
- `cloud/` replaces eight cron rows with one justified read-only external
  catalog audit, event entrypoints, explicit campaigns, and exact deadlines.
- `manifest.json` binds every current source file by SHA-256. Installed-state
  receipts bind those source identities to the exact deployed Git commit.

Installers accept only the tracked before or after state and are safe to retry
after interruption. Rollback refuses unrelated drift. Neither an installer nor
a rollback script is a periodic entrypoint.

G1.24 still owns external DCP routine verification and the delivered full-state
audit. Nothing in this package represents those proofs as complete.
