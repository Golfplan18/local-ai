# G1.10 cloud operational sources

This is the tracked installed-source set after cutover.

Only the model-price audit remains in crontab. It reads a third-party catalog
that provides no authenticated change callback, performs no content mutation,
and therefore has a written runtime-impossibility justification. All other
former cron rows move to their cause:

- Ora deploy: explicit accepted-release deployment event.
- MSI deploy: exact `article.publish` completion event in unified production.
- WSJ auth: preflight immediately before an actual WSJ source fetch.
- MSI vault outbox: exact verified `article.live` completion event.
- Ora vault-runtime sync: exact Mac-to-cloud vault-sync receipt.
- Gear-4 expiration: one persisted systemd deadline per exact graveyard entry.
- MSI full deploy: explicit release/integrity campaign only.

`install-cloud-cutover.sh` captures one immutable on-host rollback copy,
verifies each of the six replaced scripts against either the tracked
pre-cutover or current identity, installs the seventh deadline helper, and
replaces the crontab. A persisted receipt makes interrupted delivery and
retries reconstructible. `rollback-cloud-cutover.sh` refuses unrelated drift,
restores the tracked baseline, and removes only the exact installed deadline
helper. Neither script is a periodic entrypoint.
