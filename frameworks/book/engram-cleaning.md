# Engram Cleaning Framework

## Display Name
Engram Cleaning

## Display Description
Cross-vault sweep that surfaces contradictions in the engram corpus. As of 2026-07-12 the default mode is fully automated: an AI judgment call — not the user — resolves each candidate as supersede or skip, applies the mutation through the same mechanics described below, and logs the decision. No triage queue sits in the loop. The manual `/cleaning` queue workflow (three resolution paths: changed-mind, hypocrisy, wrong) remains available for ad hoc or exploratory sweeps — see LAYER 7. Replaces the incubator-elevation gating model retired in Schema rev 5.

---

## PURPOSE

Schema rev 5 (2026-05-09) retired the incubator-elevation lifecycle. New atomic notes from KAC, DP, and atomic-extraction pipelines write directly to `Engrams/` with `type: engram` and an appropriate provenance-modifier tag. The volume of atomic extraction (122k+ atomics as of rev 5) makes per-note pre-elevation impractical — the user cannot personally vet 122,000 notes. Pollution prevention shifts from **gatekeeping at the door** to **continuous cleaning across the corpus**.

This framework is that cleaning loop. Its job is to:

1. Surface contradictions across the engram corpus.
2. Judge each contradiction — automated by default (LAYER 7), or present to the user for manual triage (LAYER 1-6).
3. Apply the chosen resolution as mechanical YAML mutations.
4. Maintain a log of resolutions for the historical record.

**2026-07-12 revision to the framework's grounding:** the original v1.0 design read the AHI thesis (user is the principal; AI assists) as meaning AI cannot resolve contradictions in the user's thinking — only surface them for the user to decide. At 122k+ atomics and 32k+ contradicts edges, that reading made the framework itself impractical: a human cannot personally triage a corpus at that scale any more than they could pre-vet it (the same volume argument that killed incubator-elevation in Schema rev 5). The revised reading: AHI's user-as-principal holds at the level of *standing instruction* — the user decided, once, durably, what supersession judgment should apply (LAYER 7's SUPERSEDE/SKIP contract) and retains the off-switch (the maintenance-scheduler control doc) and the audit trail (the resolution log). The AI executes that standing instruction per-pair; it does not originate the policy. Manual triage (LAYER 1-6) remains available whenever the user wants to review a specific batch personally.

---

## INPUT CONTRACT

**Required (detection phase):**

- **`relationship-graph.db`** — SQLite graph at `~/ora/data/relationship-graph.db` containing the typed relationship corpus (Phase C output). The framework reads `contradicts` edges as the primary signal (and, for LAYER 7's Phase-C fold, `supersedes` edges). Format: SQLite schema per `~/ora/orchestrator/tools/relationship_graph.py`. Source: built from vault YAML by `relationship_graph.py rebuild`.
- **Engrams folder** — `~/Documents/vault/Engrams/`. The framework reads each engram's frontmatter (for last-modified date, archived status, provenance tags) and H1 (for the claim title). Source: vault filesystem.

**Required (resolver phase, manual mode):**

- **Triage queue file** — `Working — Engram Cleaning Queue.md` at vault root, populated by detection and edited by the user with resolution markers. Format: markdown with per-pair sections; each pair has a `[pending]`-prefixed heading the user replaces with a resolution marker. Source: detection produces it; user mutates it.

**Required (automated mode, LAYER 7):**

- **A configured model slot** — `evaluator`, falling back to `sidebar`, per `~/ora/config/routing-config.json`. If neither slot resolves, the sweep fails open (skips the pair, logs the error, retries next sweep) rather than blocking.

**Optional:**

- **`--limit N`** — cap on number of pairs surfaced per run (manual mode). Default: 25. Use lower for focused triage, higher for sprint-mode review.
- **`--prioritize <strategy>`** — prioritization strategy. Default: `bidirectional`. Other values: `date-gap`, `recent`, `clustered`, `random`.

---

## OUTPUT CONTRACT

**Detection phase outputs (manual mode):**

- **`Working — Engram Cleaning Queue.md`** — markdown triage file at vault root. One section per contradiction pair, each with:
  - Pair heading: `## [pending] <truncated-source-claim>`
  - Source/target wikilinks, claim H1s, last-modified dates, confidence
  - Resolution marker line (user edits): `**Resolution:** [pending]`
  - Pre-formatted resolution menu the user picks from
- **Stdout summary** — count of pairs surfaced, prioritization strategy, total contradicts edges in graph.

**Resolver phase outputs (both modes — manual resolver and LAYER 7's automated sweep converge on identical mutations):**

- **Vault file mutations** — for each non-skipped pair:
  - `changed-mind:source-supersedes-target` → adds a `supersedes` relationship (source → target) in the source's frontmatter; adds `archived` tag to the target's frontmatter.
  - `changed-mind:target-supersedes-source` → mirror of above (target supersedes source).
  - `wrong:source` → adds `archived` tag to the source.
  - `wrong:target` → adds `archived` tag to the target.
  - `hypocrisy` → no automatic mutation; logged for the user's reflection. (Manual mode only — LAYER 7's automated judgment is a binary supersede/skip call, not a three-way hypocrisy distinction.)
  - `skip` → no action, but still logged (automated mode logs every skip so the pair doesn't resurface).
- **`Working — Engram Cleaning Log.md`** — history file at vault root. Append-only log of resolutions: timestamp, pair, resolution marker, files mutated. Automated-mode entries additionally carry a `**Judge:** model (<slot>) — <reason>` line.
- **ChromaDB metadata refresh** — for affected files, the resolver pushes the updated YAML's metadata into the `knowledge` collection so the new tags (especially `archived`) flow to retrieval.

---

## EXECUTION TIER

specification.

Manual mode runs in two phases: **detection** (produces the queue) and **resolver** (applies the user's resolutions), decoupled so the user can edit the queue at their own pace. Automated mode (LAYER 7) collapses detection, judgment, and resolution into one scheduled sweep — no decoupled phases, no queue file.

---

## MILESTONES DELIVERED

- ☑ The contradicts-edge corpus is sampled and prioritized into a tractable triage queue (manual mode, LAYER 1-6).
- ☑ The user reviews the queue and marks resolutions on each pair (manual mode).
- ☑ The resolver applies the chosen resolutions as mechanical YAML mutations.
- ☑ The resolution log is appended with the actions taken.
- ☑ ChromaDB metadata is refreshed for affected files.
- ☑ **(2026-07-12) A model judgment replaces the human triage step** — LAYER 7's automated sweep judges each candidate directly and applies the same resolver mechanics, with no queue and no human in the loop.
- ☑ **(2026-07-12) The one-directional edge population is reachable** — the `date-gap` strategy surfaces the 40k+ `contradicts` edges `bidirectional` never sees.
- ☑ **(2026-07-12) Unconsumed Phase-C `supersedes` edges are folded in** — ~4,676 high-confidence `supersedes` edges the extraction pipeline recorded but nothing ever applied now flow through the same judged sweep.
- ☑ **(2026-07-12) The sweep runs on a schedule, governed by the vault** — weekly by default via the maintenance scheduler's `Reference — Ora Periodic Maintenance.md` control doc; `off` is the user's escape hatch.

---

## EVALUATION CRITERIA

- **Triage tractability** — each manual detection run surfaces a queue the user can complete in one sitting (≤25 pairs default; configurable).
- **Resolution fidelity** — the resolver applies exactly the resolutions marked (manual) or judged (automated), with zero silent mutations.
- **Idempotency** — running detection twice produces a stable queue; running the resolver twice on the same queue is a no-op after the first. Automated mode: a judged pair (supersede or skip) never resurfaces in a later sweep.
- **Audit trail** — the resolution log captures every mutation for review and rollback, including the model's stated reason in automated mode.
- **Fail-open** (automated mode) — a model error, missing endpoint, or unparseable response skips that pair and retries next sweep; it never blocks the sweep or the pairs after it.
- **Reversibility** — git is the safety net. The vault is committed before each resolver run; if a resolution turns out to be wrong, `git revert` restores the prior state.

---

## LAYER 1: PRIORITIZATION

The graph contains 32k+ high-confidence `contradicts` edges. Surfacing all at once is intractable. The framework prioritizes per the active strategy.

### Strategy: `bidirectional` (default, manual mode)

A contradiction is most likely "real" when both engrams independently reference each other as contradicting. The framework filters to pairs where:
- A `contradicts` B exists with confidence `high`
- B `contradicts` A also exists (directionality reciprocal)
- Neither A nor B already carries the `archived` tag

These are the contradictions the extraction pipeline saw from both directions — strongest signal that the contradiction is genuine and not a one-sided misread.

### Strategy: `date-gap` (2026-07-12, default for LAYER 7's automated sweep)

`bidirectional` requires the extraction pipeline to have recorded the contradiction from both directions — a strong signal, but one that only exists for a fraction of the corpus. Of the graph's `contradicts` edges, 40k+ are one-directional; `bidirectional` never sees them. `date-gap` reaches that population: a single `contradicts` edge (confidence `high` or `medium`) between two engrams whose dates are separated by at least a configurable gap (default 90 days, `ORA_ENGRAM_DATE_GAP_DAYS` — provisional, uncalibrated) is a candidate — the reasoning being that a genuine changed-mind reversal plays out over time, while same-period contrastive writing (the dominant false-positive class identified in the rounds 1+2 triage learning below) clusters within days of itself. Candidates are ordered by date gap descending (clearest reversals first) and the (newer, older) pair is reported with the newer engram as the candidate survivor. LAYER 7's automated sweep runs this strategy by default because it is the one that actually drains the one-directional backlog; `bidirectional`, `recent`, `clustered`, and `random` remain available for manual `/cleaning detect`.

### Strategy: `recent`

Pairs where at least one of the engrams was last-modified in the last 30 days. Surfaces contradictions that involve recent thinking, where the user is most likely to remember context and apply meaningful resolution.

### Strategy: `clustered`

Groups contradicts pairs by source-engram. Surfaces engrams that contradict many others (high outgoing-contradicts-degree) — these are likely either:
- Drift indicators (the user's position has shifted and many older notes are now superseded)
- Faulty notes (the engram is wrong and contradicts everything correct)

Useful for batch resolution where one decision (e.g., "I changed my mind on X") supersedes a cluster of older notes.

### Strategy: `random`

Uniform random sample. Useful for unbiased corpus-health spot-checks.

---

## LAYER 2: TRIAGE QUEUE FORMAT (manual mode)

The detection phase writes `Working — Engram Cleaning Queue.md` at vault root. Format:

```markdown
---
nexus:
  - ora
type: working
tags:
  - engram-cleaning
date created: <YYYY-MM-DD>
date modified: <YYYY-MM-DD>
---

# Engram Cleaning Queue — <YYYY-MM-DD>

*Generated by Framework — Engram Cleaning detection phase. Strategy: <strategy>. Pairs: <N>.*

For each pair below, edit the **Resolution** line. Replace `[pending]` with one of:
- `[changed-mind:source-supersedes-target]` — source claim is your current position; target is older thinking
- `[changed-mind:target-supersedes-source]` — target claim is your current position; source is older thinking
- `[hypocrisy]` — both are positions you hold; the contradiction reflects motivated reasoning or genuine tension to examine
- `[wrong:source]` — source is incorrect; archive it
- `[wrong:target]` — target is incorrect; archive it
- `[skip]` — defer; remove from this queue without action

When done, run the resolver: `python3 ~/ora/orchestrator/historical/run_engram_cleaning_resolver.py`

---

## [pending] <source-claim-truncated>

- **Source:** [[<source-filename>]] (modified <YYYY-MM-DD>)
  *<source H1 — the full claim>*
- **Target:** [[<target-filename>]] (modified <YYYY-MM-DD>)
  *<target H1 — the full claim>*
- **Confidence:** high
- **Strategy match:** bidirectional
- **Provenance:** source=<user|ai-derived|source-derived>, target=<user|ai-derived|source-derived>

**Resolution:** [pending]

---

## [pending] ...

(repeat per pair)
```

The provenance line surfaces who originated each claim (per the rev 5 provenance-modifier tags). A user-vs-user contradiction is the user's own thinking; user-vs-ai is the user contradicting an AI claim; ai-vs-ai is two AI claims contradicting each other (resolution: usually the user picks one or marks both `wrong`).

---

## LAYER 3: RESOLUTION MECHANICS

The resolver reads the queue file (manual mode) or a judged candidate (automated mode, LAYER 7) and processes each pair whose resolution is not `[pending]`. Mechanics per resolution marker:

### `[changed-mind:source-supersedes-target]`

The source claim is your current thinking; the target is older thinking superseded by it.

Mutations:
1. **Add `supersedes` relationship** to the source's frontmatter `relationships:` list:
   ```yaml
   - type: supersedes
     target: <target-claim-H1>
     confidence: high
   ```
2. **Add `archived` tag** to the target's frontmatter `tags:` list (if not already present).

The target stays in the vault as a record of the user's intellectual evolution but leaves default retrieval (per Schema §6.5 `archived` filter).

### `[changed-mind:target-supersedes-source]`

Mirror of the above: target supersedes source.

### `[hypocrisy]` (manual mode only)

The contradiction reflects genuine tension or motivated reasoning the user wants to examine. No automatic mutation.

The pair is logged with marker `[hypocrisy]` to a separate file: `Working — Engram Cleaning Hypocrisy Review.md`. The user reviews this file at their own pace and may later apply resolutions through normal vault editing or by re-running detection. LAYER 7's automated judgment does not use this marker — its binary SUPERSEDE/SKIP contract defaults ambiguous or "both still held" cases to SKIP.

### `[wrong:source]` / `[wrong:target]` (manual mode only)

The named claim is incorrect.

Mutations:
- Default action: add `archived` tag to the named engram. The engram stays in the vault as a record of past mistakes but leaves default retrieval.
- Aggressive action (`--delete-wrong` flag on the resolver): physically delete the file. Use sparingly; `archived` is the safer default.

LAYER 7's automated judgment does not use `wrong:*` — distinguishing "outdated" from "factually wrong" is a call the framework reserves for manual review; the automated sweep only ever applies supersede or skip.

### `[skip]`

No mutation. The pair is removed from the manual queue, or (automated mode) simply not mutated — either way it's logged so it doesn't resurface in subsequent runs (manual: until/unless the user explicitly re-includes it via `--include-skipped`; automated: never, short of manually editing the log).

---

## LAYER 4: RESOLUTION LOG

The resolver appends each completed resolution to `Working — Engram Cleaning Log.md` at vault root:

```markdown
## <YYYY-MM-DD HH:MM> — <resolution-marker>

- **Source:** [[<source-filename>]]
- **Target:** [[<target-filename>]]
- **Resolution:** <full-marker>
- **Files mutated:** <list>
- **Strategy:** <strategy that surfaced this pair>
- **User note:** *(blank — user can add commentary inline if desired)*
```

Automated-mode entries (LAYER 7) carry the same Source/Target adjacency plus a `**Judge:** model (<slot>) — <reason>` line recording the model's stated reasoning, and the marker is suffixed `(auto)`.

The log is the audit trail. To roll back a resolution, the user can `git revert` the relevant commit (the resolver auto-commits each batch with a structured message).

---

## LAYER 5: CHROMADB METADATA REFRESH

After mutations land, the resolver pushes the updated YAML metadata into the ChromaDB `knowledge` collection for affected files. This ensures the `archived` tag (and any new `supersedes` relationship) flows to the retrieval path immediately — `archived`-tagged engrams are excluded from default retrieval per Schema §6.5.

The refresh uses `collection.update()` (no re-embedding; metadata-only) following the same pattern as `phase3_chromadb_refresh.py` from the rev 5 migration. LAYER 7's automated sweep uses this exact same refresh call.

---

## LAYER 6: SELF-EVALUATION

After running, the framework reports:
- **Pairs surfaced:** N
- **Pairs resolved:** N (changed-mind: X, wrong: Y, hypocrisy: Z, skip: W) — manual mode
- **Files mutated:** N
- **ChromaDB updates:** N
- **Errors:** N (with file paths)

If errors > 0, the framework lists the affected files and exits non-zero. The user inspects, fixes, and re-runs the resolver — idempotency guarantees no double-mutation. LAYER 7's automated sweep reports the equivalent shape (candidates found / judged / superseded / skipped / errors / left for next sweep) in its maintenance-scheduler task result rather than stdout — see LAYER 7.

---

## LAYER 7: AUTOMATED JUDGED SWEEP (2026-07-12)

The default mode. No triage queue, no manual Resolution-line editing — the AI makes the supersession call itself, applies it, and logs it. Implementation: `orchestrator/tools/supersession_sweep.py::task_engram_cleaning`, `orchestrator/historical/supersession_judge.py`.

### Why scheduled, not runtime-triggered

Ora's Runtime Principle holds that a process executable at runtime should not be deferred to a schedule. This framework's automated mode is scheduled, and that requires justification: the KAC end-of-session trigger (below, under "Trigger from KAC") already covers the *runtime* case — new atomics written this session, checked against contradictions this session. What that trigger structurally cannot reach is the **backlog** — 32k+ existing `contradicts` edges, 40k+ one-directional edges, ~4,676 unconsumed Phase-C `supersedes` edges — content that already existed before this framework's automated mode shipped and is not tied to any single write event. There is no runtime hook to attach "re-examine the entire historical graph" to; it is a whole-corpus sweep by nature, exactly like the pre-existing scheduled tasks in `orchestrator/maintenance_scheduler.py` (`orphan_cleanup`, `vault_health`, `graph_density`) that this framework's scheduling now sits alongside. Per-sweep pair bounds (below) exist for the same reason those tasks are bounded: judging a 40k-pair backlog cannot happen synchronously inside one chat turn without making that turn arbitrarily slow and costly.

### Candidate sourcing

Each sweep run pulls from two sources, in order, until the per-sweep bound is filled:

1. **`date-gap` detection** (LAYER 1) — the one-directional-edge strategy, since it's the population the manual `bidirectional` default never reached.
2. **Unconsumed Phase-C `supersedes` edges** — `orchestrator.tools.supersession_sweep.phase_c_supersedes_candidates()` reads high-confidence `supersedes` edges from `relationship-graph.db` whose target was never actually archived (the extraction pipeline recorded the edge; nothing downstream applied it). Source = claimed survivor, target = claimed superseded — a lower-uncertainty population than fresh contradicts detection, since Phase-C already asserted a direction; the model judgment step still runs on every pair, it does not auto-apply Phase-C edges unjudged.

Both sources exclude pairs already present in `Working — Engram Cleaning Log.md` (the same resolved-pair filter LAYER 1's manual strategies use), so a judged pair — supersede or skip — never resurfaces.

### The judgment call

For each candidate pair, `supersession_judge.judge_pair()` sends both engrams' claim (H1), date, and body excerpt (capped at `MAX_NOTE_CHARS`, default 3000 chars, provisional) to a model via `orchestrator/model_dispatch.py::invoke_chat`, slot `evaluator` falling back to `sidebar` if no evaluator endpoint is configured, `context="autonomous"` (local transports only — no metered API cost for an unattended sweep; model selection is never hardcoded). The model returns exactly:

```
VERDICT: SUPERSEDE
REASON: <one line>
```

or `VERDICT: SKIP` with the same reason line. The system prompt names the same false-positive patterns the rounds-1+2 triage learning identified (contrastive distinctions, problem/solution pairs) as SKIP cases, and instructs SKIP as the safe default under uncertainty — a wrong SUPERSEDE hides a note from retrieval, which is the worse failure direction.

### Application and logging

- **SUPERSEDE** → applies through the exact same `apply_changed_mind()` resolver mechanics as manual `[changed-mind:source-supersedes-target]` (LAYER 3): `supersedes` relationship on the survivor, `archived` tag on the superseded engram, ChromaDB metadata refresh for both.
- **SKIP** → no mutation, but the pair is still appended to `Working — Engram Cleaning Log.md` (marked `skip (auto)`) so it does not resurface next sweep.
- **Model error** (unreachable endpoint, unparseable response, any exception) → **NOT logged**. The pair is not marked resolved, so it retries on the next sweep once the model is healthy again. This is the fail-open contract: a broken model never blocks the sweep and never gets silently treated as a resolved judgment.

Every log entry — supersede or skip — carries the `**Judge:** model (<slot>) — <reason>` line, so the resolution log doubles as the automated system's audit trail, same file, same format the manual workflow already used.

### Per-sweep bound

`MAX_ENGRAM_PAIRS` (default 50, provisional tuning constant, `ORA_SUPERSESSION_ENGRAM_PAIRS`) caps how many pairs one sweep judges. The task result message reports candidates found vs. judged vs. left for next sweep — no silent truncation. At weekly cadence and 50 pairs/sweep, the ~40k one-directional backlog drains over roughly 18 months; the bound can be raised via the env var once judgment quality is validated against a sample.

### Schedule and escape hatch

Registered as task `engram_cleaning` in `orchestrator/maintenance_scheduler.py`, cadence governed by `Reference — Ora Periodic Maintenance.md`'s frontmatter (default `weekly`). Setting the cadence to `off` in that document is the escape hatch — the automated sweep stops, and the manual `/cleaning` workflow (LAYER 1-6) remains fully available regardless of the scheduled mode's state.

---

## INTEGRATION

### Trigger from KAC

KAC's Layer 8 (error correction and output formatting) writes its output to the vault. After write, KAC checks whether the user has the cleaning queue setting enabled (default: true after Schema rev 5). If yes, KAC suggests at session-end:

> *"Your session added N atomic engrams. The Engram Cleaning Framework has surfaced M new contradictions involving these atomics or related ones. Run `/cleaning` to triage them, or defer."*

The user runs `/cleaning` interactively or skips. This runtime trigger is unaffected by LAYER 7's scheduled automation — it still checks only the current session's new atomics, not the historical backlog.

### Manual invocation

**Slash commands** (chat interface, mechanical — no model call):

```
/cleaning                                  → status summary
/cleaning status                           → queue state without re-running detection
/cleaning detect [strategy] [limit]        → produce triage queue (default: bidirectional 25; strategies: bidirectional, date-gap, recent, clustered, random)
/cleaning resolve                          → dry-run resolver against current queue
/cleaning resolve --apply                  → apply queued resolutions
/cleaning help                             → usage
```

The `/cleaning` family is registered in `~/ora/orchestrator/slash_commands.py` alongside `/instance`, `/render`, `/queue`, and the meta-layer mechanical operations. It bypasses the analytical pipeline entirely.

**Direct CLI** (for scripting or sleep-wake invocation):

```bash
# Detection — produces Working — Engram Cleaning Queue.md
python3 ~/ora/orchestrator/historical/run_engram_cleaning_detection.py [--limit N] [--strategy bidirectional|date-gap|random]

# Resolver — applies queued resolutions, mutates vault, refreshes chromadb
python3 ~/ora/orchestrator/historical/run_engram_cleaning_resolver.py [--dry-run]

# Automated judged sweep (LAYER 7) — normally run by the maintenance scheduler,
# but callable standalone for testing or an out-of-cadence pass:
python3 ~/ora/orchestrator/tools/supersession_sweep.py engram
```

### Cadence

**Automated mode (default):** weekly, via the maintenance scheduler — see LAYER 7. Governed by `Reference — Ora Periodic Maintenance.md`; set `engram_cleaning: off` there to disable.

**Manual mode:** the user controls cadence at will. Suggested:
- Ad hoc: quick `bidirectional --limit 10` or `date-gap --limit 10` sweep to spot-check a specific angle.
- **After sprint extraction sessions** (Phase 5 / DP runs that add many atomics): trigger via KAC suggestion.
- **Quarterly:** `clustered --limit 50` deep pass to surface drift patterns the automated sweep's per-pair judgment doesn't aggregate.

---

## DEPENDENCIES

- **Schema rev 5+** — provenance-modifier tags (`ai-derived`, `source-derived`) are read for the queue's provenance line.
- **`relationship-graph.db`** — must be populated. Rebuild via `python3 ~/ora/orchestrator/tools/relationship_graph.py rebuild` if stale.
- **ChromaDB `knowledge` collection** — for metadata refresh after resolution.
- **Vault is a git repo** — for rollback safety.
- **(LAYER 7) `orchestrator/historical/supersession_judge.py`** — the model-judgment core (prompt, slot ladder, fail-open parsing).
- **(LAYER 7) `orchestrator/tools/supersession_sweep.py`** — the scheduled task; also folds Phase-C `supersedes` edges.
- **(LAYER 7) `orchestrator/model_dispatch.py::invoke_chat`** — model routing; never a hardcoded model.
- **(LAYER 7) `orchestrator/maintenance_scheduler.py`** + **`Reference — Ora Periodic Maintenance.md`** — cadence governance.

---

## DEFERRED FOR LATER

- **Bidirectional supersedes graph traversal** — when applying `changed-mind`, optionally walk the relationship graph to find chains (A supersedes B; B supersedes C → archive both B and C). v1 handles only the immediate pair.
- **Multi-user contradiction reasoning** — if Ora ever supports multiple authors, the source_side / provenance distinction becomes per-author; the framework's prioritization should weight intra-author contradictions higher than cross-author (which are likely just disagreements, not contradictions in any one author's thinking).
- **Automated `wrong:*` and `hypocrisy` judgment** — LAYER 7's model judgment is binary (supersede/skip) by design; extending it to distinguish "factually wrong" from "outdated" or to flag genuine hypocrisy/motivated-reasoning tension would need a richer judgment contract and is not yet built.
- **Calibrating `ORA_ENGRAM_DATE_GAP_DAYS` and `MAX_ENGRAM_PAIRS`** — both are provisional first guesses (90 days, 50 pairs/sweep respectively), not tuned against outcome data. Revisit once the automated sweep has run enough cycles to sample judgment quality.

---

## CHANGE LOG

- **2026-07-12 (v2.0) — Automated judged sweep.** Adds LAYER 7: the default mode is now a scheduled, model-judged sweep with no human triage queue, per explicit user decision (standing zero-manual-labor / fail-open convention). New `date-gap` prioritization strategy (LAYER 1) reaches the 40k+ one-directional `contradicts` edges the `bidirectional` default never surfaced. Unconsumed Phase-C `supersedes` edges (~4,676) are folded into the same judged sweep. Scheduled weekly via `orchestrator/maintenance_scheduler.py`, governed by `Reference — Ora Periodic Maintenance.md` (`off` = escape hatch); justification for scheduling over runtime execution recorded in LAYER 7 per the vault's Runtime Principle. Manual `/cleaning` workflow (LAYER 1-6) is unchanged and remains available. New modules: `orchestrator/historical/supersession_judge.py`, `orchestrator/tools/supersession_sweep.py`. 30 new unit tests in `orchestrator/tests/test_supersession_auto.py`; existing `test_engram_cleaning.py` and `test_maintenance_scheduler.py` suites pass unmodified in behavior (scheduler tests updated for the new task set).

- **2026-05-09 (v1.0)** — Initial draft. Specifies detection + resolver workflow, four prioritization strategies, six resolution markers, ChromaDB metadata refresh, KAC integration. Implementation lands in `~/ora/orchestrator/historical/run_engram_cleaning_detection.py` and `run_engram_cleaning_resolver.py` (resolver deferred — implemented after first queue review).

- **2026-05-09 (v1.0.1)** — Two implementation bugs surfaced during the first two triage rounds (50 pairs total) and fixed in ora commit `81ea313`:
  - **Resolver parser** was reading the resolution marker from the heading line (`## [pending] ...`) instead of the user-edit canonical `**Resolution:** [marker]` line. Users editing only the Resolution line per the framework's user-facing instructions saw their resolutions silently ignored. Fixed by anchoring the regex on Source/Target wikilinks and capturing the Resolution line as canonical; heading marker is now informational only. Queue-rebuild logic similarly updated to read Resolution lines.
  - **Detection log filter** was missing entirely. The framework spec promised previously-resolved pairs wouldn't resurface, but the first round-2 detection returned 22/25 same pairs as round 1 because no log-reading was implemented. Fixed by adding `_load_resolved_pair_set()` that extracts canonical (sorted) source-target slug tuples from `Working — Engram Cleaning Log.md` and excluding them from `detect_bidirectional` and `detect_random` candidate sets. New `--include-skipped` CLI flag (and slash-command arg) opts out of the filter to re-surface resolved pairs.
  - Slash command status (`_cleaning_queue_status`) updated to count pending pairs by Resolution-line markers, matching the canonical edit point.
  - 14 new unit tests in `orchestrator/tests/test_engram_cleaning.py`; 113 regression tests pass across the touched provenance / RAG / slash-command suites.

- **Triage learning (rounds 1+2, 2026-05-09)** — Across 50 pairs the bidirectional strategy produced ~92% false positives (46 skips, 4 substantive resolutions). All 4 substantive resolutions came from **mixed-provenance** pairs (one user-authored, one AI-derived). Two recurring user-touching patterns the detector consistently misreads as contradictions: (a) **contrastive distinctions** — user articulating what X is and what non-X is not as paired engrams; (b) **problem-followed-by-solution** — user stating a problem in one engram and the proposed solution in another. Both default to `[skip]`. The high-value pattern: AI-overreach (claim with absolute qualifier — "regardless of intent," "always," "never") + user counter that accepts factual core but rejects qualifier. These map cleanly to `[changed-mind:source-supersedes-target]`. These patterns informed the v2 smart-filter detection roadmap (separate task), and directly shaped LAYER 7's judgment-prompt SKIP guidance above.
