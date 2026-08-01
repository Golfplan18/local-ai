# Engram Cleaning Framework

## Display Name
Engram Cleaning

## Display Description
Bounded event process for contradictions touching an exact written Engram, plus an explicit historical-corpus campaign. Runtime model judgment may autonomously apply changed-mind supersession without per-pair human triage; reflective/manual classifications remain available through the campaign interface.

---

## PURPOSE

Schema rev 5 (2026-05-09) retired the incubator-elevation lifecycle. New atomic notes from KAC, DP, and atomic-extraction pipelines write directly to `Engrams/` with `type: engram` and an appropriate provenance-modifier tag. The volume of atomic extraction (122k+ atomics as of rev 5) makes per-note pre-elevation impractical — the user cannot personally vet 122,000 notes. Pollution prevention shifts from **gatekeeping at the door** to **continuous cleaning across the corpus**.

This framework is that cleaning loop. Its job is to:

1. Surface contradictions across the engram corpus.
2. Complete bounded model judgment before runtime mutation, or present historical campaign candidates for user triage.
3. Apply the governed resolution as a recoverable YAML transaction.
4. Maintain a log of resolutions for the historical record.

The user remains the principal. The approved runtime contract nevertheless delegates bounded pair judgment to a model for exact-write neighborhoods. That delegation is explicit, append-only audited, capped at eight pairs, rollback-protected, and distinct from reflective hypocrisy/wrong classifications that still return to the user.

---

## INPUT CONTRACT

**Required (detection phase):**

- **`relationship-graph.db`** — SQLite graph at `~/ora/data/relationship-graph.db` containing the typed relationship corpus (Phase C output). The framework reads `contradicts` edges as the primary signal. Format: SQLite schema per `~/ora/orchestrator/tools/relationship_graph.py`. Source: built from vault YAML by `relationship_graph.py rebuild`.
- **Engrams folder** — `~/Documents/vault/Engrams/`. The framework reads each engram's frontmatter (for last-modified date, archived status, provenance tags) and H1 (for the claim title). Source: vault filesystem.

**Required (manual/campaign resolver phase):**

- **Triage queue file** — `Projects/Ora/Working — Engram Cleaning Queue.md`, populated by detection and edited by the user with resolution markers. Format: markdown with per-pair sections; each pair has a `[pending]`-prefixed heading the user replaces with a resolution marker. Source: detection produces it; user mutates it.

**Optional:**

- **`--limit N`** — cap on number of pairs surfaced per run. Default: 25. Use lower for focused triage, higher for sprint-mode review.
- **`--prioritize <strategy>`** — prioritization strategy. Default: `bidirectional`. Other values: `recent`, `clustered`, `random`.

**Required (runtime event phase):**

- **Exact Engram identity** — the event contract binds the top-level `Engrams/*.md` path, SHA-256 digest, and size before evaluation.
- **Configured model slot** — the runtime uses the governed evaluator/sidebar routing ladder; unresolved or invalid output fails the event without mutation.

---

## OUTPUT CONTRACT

**Detection phase outputs:**

- **`Projects/Ora/Working — Engram Cleaning Queue.md`** — markdown triage file. One section per contradiction pair, each with:
  - Pair heading: `## [pending] <truncated-source-claim>`
  - Source/target wikilinks, claim H1s, last-modified dates, confidence
  - Resolution marker line (user edits): `**Resolution:** [pending]`
  - Pre-formatted resolution menu the user picks from
- **Stdout summary** — count of pairs surfaced, prioritization strategy, total contradicts edges in graph.

**Resolver phase outputs (manual and runtime paths converge on the same artifact semantics):**

- **Vault file mutations** — for each non-skipped pair:
  - `changed-mind:source-supersedes-target` → adds a `supersedes` relationship (source → target) in the source's frontmatter; adds `archived` tag to the target's frontmatter.
  - `changed-mind:target-supersedes-source` → mirror of above (target supersedes source).
  - `wrong:source` → adds `archived` tag to the source.
  - `wrong:target` → adds `archived` tag to the target.
  - `hypocrisy` → no automatic mutation; logged for the user's reflection.
  - `skip` → no action.
- **`Projects/Ora/Working — Engram Cleaning Log.md`** — append-only resolution evidence including model slot/reason for autonomous judgments and the exact files changed.
- **ChromaDB metadata refresh** — for affected files, the resolver pushes the updated YAML's metadata into the `knowledge` collection so the new tags (especially `archived`) flow to retrieval.
- **Runtime event evidence** — immutable event claim, bounded candidate/judgment evidence, before/after identities, completion or failure, and authenticated rollback state under `data/runtime-hygiene/`.

---

## EXECUTION TIER

specification.

Manual campaigns run in two decoupled phases: detection and resolver. Runtime mode receives one exact Engram write, evaluates at most eight related pairs, completes every judgment before mutation, and applies the result as one rollback-protected transaction. An error causes no mutation and no clock fallback.

---

## MILESTONES DELIVERED

- ☑ The manual contradicts-edge corpus can be sampled into a tractable triage queue.
- ☑ The manual resolver applies user-marked resolutions.
- ☑ Exact Engram writes can trigger bounded autonomous judgment with no per-pair human triage.
- ☑ All judgments finish before mutation; errors restore the snapshotted state.
- ☑ Resolution and runtime event evidence are append-only, and explicit rollback is drift-safe.
- ☑ ChromaDB metadata is refreshed inside the governed transaction.

---

## EVALUATION CRITERIA

- **Triage tractability** — each detection run surfaces a queue the user can complete in one sitting (≤25 pairs default; configurable).
- **Resolution fidelity** — the resolver applies exactly the user-marked or bounded model-judged resolution, with zero silent mutations.
- **Idempotency** — running detection twice produces a stable queue; running the resolver twice on the same queue is a no-op after the first.
- **Audit trail** — the resolution log and runtime event ledger capture autonomous judgment, no-human-triage status, exact before/after identity, and every mutation.
- **Reversibility** — runtime events carry persisted snapshots and drift-safe authenticated rollback; campaigns also retain repository history.

---

## LAYER 1: PRIORITIZATION

The graph contains 32k+ high-confidence `contradicts` edges. Surfacing all at once is intractable. The framework prioritizes per the active strategy.

### Strategy: `bidirectional` (default)

A contradiction is most likely "real" when both engrams independently reference each other as contradicting. The framework filters to pairs where:
- A `contradicts` B exists with confidence `high`
- B `contradicts` A also exists (directionality reciprocal)
- Neither A nor B already carries the `archived` tag

These are the contradictions the extraction pipeline saw from both directions — strongest signal that the contradiction is genuine and not a one-sided misread.

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

## LAYER 2: TRIAGE QUEUE FORMAT

The detection phase writes `Projects/Ora/Working — Engram Cleaning Queue.md`. Format:

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

The resolver reads the queue file and processes each pair whose Resolution is non-`[pending]`. Mechanics per resolution marker:

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

### `[hypocrisy]`

The contradiction reflects genuine tension or motivated reasoning the user wants to examine. No automatic mutation.

The pair is logged with marker `[hypocrisy]` to a separate file: `Projects/Ora/Working — Engram Cleaning Hypocrisy Review.md`. The user reviews this file at their own pace and may later apply resolutions through normal vault editing or by re-running detection.

### `[wrong:source]` / `[wrong:target]`

The named claim is incorrect.

Mutations:
- Default action: add `archived` tag to the named engram. The engram stays in the vault as a record of past mistakes but leaves default retrieval.
- Aggressive action (`--delete-wrong` flag on the resolver): physically delete the file. Use sparingly; `archived` is the safer default.

### `[skip]`

No mutation. The pair is removed from the queue but logged so it doesn't resurface in subsequent detection runs (until/unless the user explicitly re-includes it via `--include-skipped`).

---

## LAYER 4: RESOLUTION LOG

The resolver appends each completed resolution to `Projects/Ora/Working — Engram Cleaning Log.md`:

```markdown
## <YYYY-MM-DD HH:MM> — <resolution-marker>

- **Source:** [[<source-filename>]]
- **Target:** [[<target-filename>]]
- **Resolution:** <full-marker>
- **Files mutated:** <list>
- **Strategy:** <strategy that surfaced this pair>
- **User note:** *(blank — user can add commentary inline if desired)*
```

The log is the audit trail. To roll back a resolution, the user can `git revert` the relevant commit (the resolver auto-commits each batch with a structured message).

---

## LAYER 5: CHROMADB METADATA REFRESH

After mutations land, the resolver pushes the updated YAML metadata into the ChromaDB `knowledge` collection for affected files. This ensures the `archived` tag (and any new `supersedes` relationship) flows to the retrieval path immediately — `archived`-tagged engrams are excluded from default retrieval per Schema §6.5.

The refresh uses `collection.update()` (no re-embedding; metadata-only) following the same pattern as `phase3_chromadb_refresh.py` from the rev 5 migration.

---

## LAYER 6: SELF-EVALUATION

After running, the framework reports:
- **Pairs surfaced:** N
- **Pairs resolved:** N (changed-mind: X, wrong: Y, hypocrisy: Z, skip: W)
- **Files mutated:** N
- **ChromaDB updates:** N
- **Errors:** N (with file paths)

If errors > 0, the framework lists the affected files and exits non-zero. The user inspects, fixes, and re-runs the resolver — idempotency guarantees no double-mutation.

---

## INTEGRATION

### Trigger from KAC

KAC's Layer 8 (error correction and output formatting) writes its output to the vault. After write, KAC checks whether the user has the cleaning queue setting enabled (default: true after Schema rev 5). If yes, KAC suggests at session-end:

> *"Your session added N atomic engrams. The Engram Cleaning Framework has surfaced M new contradictions involving these atomics or related ones. Run `/cleaning` to triage them, or defer."*

The interactive queue remains available for explicit historical campaigns. Separately, an exact Engram write may autonomously evaluate and mutate its bounded neighborhood under the event contract; an error causes no subject mutation and no clock retry.

### Manual invocation

**Slash commands** (chat interface, mechanical — no model call):

```
/cleaning                                  → status summary
/cleaning status                           → queue state without re-running detection
/cleaning detect [strategy] [limit]        → produce triage queue (default: bidirectional 25)
/cleaning resolve                          → dry-run resolver against current queue
/cleaning resolve --apply                  → apply queued resolutions
/cleaning help                             → usage
```

The `/cleaning` family is registered in `~/ora/orchestrator/slash_commands.py` alongside `/instance`, `/render`, `/queue`, and the meta-layer mechanical operations. It bypasses the analytical pipeline entirely.

**Direct CLI** (for scripting or sleep-wake invocation):

```bash
# Detection — produces Projects/Ora/Working — Engram Cleaning Queue.md
python3 ~/ora/orchestrator/historical/run_engram_cleaning_detection.py [--limit N] [--strategy bidirectional|random]

# Resolver — applies queued resolutions, mutates vault, refreshes chromadb
python3 ~/ora/orchestrator/historical/run_engram_cleaning_resolver.py [--dry-run]
```

### Runtime trigger and campaign boundary

Exact Engram writes are the only automatic trigger. Weekly and quarterly sweeps are prohibited. Historical unresolved relationships require an explicitly identified campaign using the manual interfaces above. The visible maintenance key and code default remain `off`; configuration cannot create a clock fallback.

---

## DEPENDENCIES

- **Schema rev 5+** — provenance-modifier tags (`ai-derived`, `source-derived`) are read for the queue's provenance line.
- **`relationship-graph.db`** — must be populated. Rebuild via `python3 ~/ora/orchestrator/tools/relationship_graph.py rebuild` if stale.
- **ChromaDB `knowledge` collection** — for metadata refresh after resolution.
- **Vault is a git repo** — for rollback safety.

---

## DEFERRED FOR LATER

- **News Supersession sweep** — parallel framework that applies the same supersession mechanism to evolving news stories in `Resources/`. Different detection logic (cluster by topic + date, not by `contradicts` edges) but the same resolution mechanics.
- **Bidirectional supersedes graph traversal** — when applying `changed-mind`, optionally walk the relationship graph to find chains (A supersedes B; B supersedes C → archive both B and C). v1 handles only the immediate pair.
- **Multi-user contradiction reasoning** — if Ora ever supports multiple authors, the source_side / provenance distinction becomes per-author; the framework's prioritization should weight intra-author contradictions higher than cross-author (which are likely just disagreements, not contradictions in any one author's thinking).

---

## CHANGE LOG

- **2026-05-09 (v1.0)** — Initial draft. Specifies detection + resolver workflow, four prioritization strategies, six resolution markers, ChromaDB metadata refresh, KAC integration. Implementation lands in `~/ora/orchestrator/historical/run_engram_cleaning_detection.py` and `run_engram_cleaning_resolver.py` (resolver deferred — implemented after first queue review).

- **2026-05-09 (v1.0.1)** — Two implementation bugs surfaced during the first two triage rounds (50 pairs total) and fixed in ora commit `81ea313`:
  - **Resolver parser** was reading the resolution marker from the heading line (`## [pending] ...`) instead of the user-edit canonical `**Resolution:** [marker]` line. Users editing only the Resolution line per the framework's user-facing instructions saw their resolutions silently ignored. Fixed by anchoring the regex on Source/Target wikilinks and capturing the Resolution line as canonical; heading marker is now informational only. Queue-rebuild logic similarly updated to read Resolution lines.
  - **Detection log filter** was missing entirely. The framework spec promised previously-resolved pairs wouldn't resurface, but the first round-2 detection returned 22/25 same pairs as round 1 because no log-reading was implemented. Fixed by adding `_load_resolved_pair_set()` that extracts canonical (sorted) source-target slug tuples from `Projects/Ora/Working — Engram Cleaning Log.md` and excluding them from `detect_bidirectional` and `detect_random` candidate sets. New `--include-skipped` CLI flag (and slash-command arg) opts out of the filter to re-surface resolved pairs.
  - Slash command status (`_cleaning_queue_status`) updated to count pending pairs by Resolution-line markers, matching the canonical edit point.
  - 14 new unit tests in `orchestrator/tests/test_engram_cleaning.py`; 113 regression tests pass across the touched provenance / RAG / slash-command suites.

- **Triage learning (rounds 1+2, 2026-05-09)** — Across 50 pairs the bidirectional strategy produced ~92% false positives (46 skips, 4 substantive resolutions). All 4 substantive resolutions came from **mixed-provenance** pairs (one user-authored, one AI-derived). Two recurring user-touching patterns the detector consistently misreads as contradictions: (a) **contrastive distinctions** — user articulating what X is and what non-X is not as paired engrams; (b) **problem-followed-by-solution** — user stating a problem in one engram and the proposed solution in another. Both default to `[skip]`. The high-value pattern: AI-overreach (claim with absolute qualifier — "regardless of intent," "always," "never") + user counter that accepts factual core but rejects qualifier. These map cleanly to `[changed-mind:source-supersedes-target]`. These patterns informed the v2 smart-filter detection roadmap (separate task).
