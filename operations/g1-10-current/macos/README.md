# G1.10 Mac operational cutover

`com.ora.server` remains the single supervised runtime. Its G1.10 source uses
OS filesystem events and persisted exact deadlines. The five captured cadence
agents are retired:

- vault Git, derived-page, and cloud synchronization are chained to exact
  coalesced vault-write events by `vault-event-pipeline.py`;
- the tracked cloud-sync step keeps its machine-local exclude file, log, and
  cloud-return inbox under the explicitly ignored `~/ora/data/cloud-sync/`;
- MSI repository refresh is explicit at the beginning of MSI work;
- MSI image recovery mirroring is an explicit pull after a verified
  publication/startup sync or when the recovery copy needs refreshing. Run
  `./msi-image-mirror.sh --verify-local` for a read-only local check and
  `./msi-image-mirror.sh pull` for the supported update. Both commands use
  `${ORA_HOME:-$HOME/ora}/data/msi-image-mirror/` (normally
  `~/ora/data/msi-image-mirror/`); no mirror action runs on a clock.

The installation script accepts only the exact tracked pre-cutover or
post-cutover state, unloads only the five exact labels, and preserves their
byte-identical plists in a fixed recovery directory. A persisted receipt makes
interrupted delivery and retries reconstructible. It does not touch
`com.ora.server`.

Rollback restores only the three remaining captured cadence agents:
`com.msi.repo-pullsync`, `com.ora.vault-derive-sync`, and
`com.ora.vault-git-autocommit`. It deliberately keeps both
`com.cloud-ora.sync` and `com.msi.image-mirror` retired: cloud sync now runs
only from the tracked event pipeline above, while MSI image recovery stays
explicit and clock-free.
