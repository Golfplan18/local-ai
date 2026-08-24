# G1.10 Mac operational cutover

`com.ora.server` remains the single supervised runtime. Its G1.10 source uses
OS filesystem events and persisted exact deadlines. The five captured cadence
agents are retired:

- vault Git, derived-page, and cloud synchronization are chained to exact
  coalesced vault-write events by `vault-event-pipeline.py`;
- the tracked cloud-sync step keeps its machine-local exclude file, log, and
  cloud-return inbox under the explicitly ignored `~/ora/data/cloud-sync/`;
- MSI repository refresh is explicit at the beginning of MSI work;
- MSI image recovery mirroring follows a verified publication/startup sync
  event and remains available as an explicit recovery command, never a clock.

The installation script accepts only the exact tracked pre-cutover or
post-cutover state, unloads only the five exact labels, and preserves their
byte-identical plists in a fixed recovery directory. A persisted receipt makes
interrupted delivery and retries reconstructible. It does not touch
`com.ora.server`.

Rollback can restore the other four retired cadence agents, but it deliberately
does not reinstall `com.cloud-ora.sync`: that agent depended on the obsolete
external `sync.py`, while cloud sync now runs only from the tracked event
pipeline above.
