# Engram Cleaning Framework

## Display Name
Engram Cleaning

## Display Description
Cross-vault sweep that surfaces contradictions in the engram corpus and presents them for user triage. Three resolution paths per contradiction: changed-mind (supersedes + archive the older claim), hypocrisy/motivated reasoning (flag for reflection), or wrong (delete or archive). Replaces the incubator-elevation gating model retired in Schema rev 5.

---

## PURPOSE

Schema rev 5 (2026-05-09) retired the incubator-elevation lifecycle. New atomic notes from KAC, DP, and atomic-extraction pipelines write directly to `Engrams/` with `type: engram` and an appropriate provenance-modifier tag. The volume of atomic extraction (122k+ atomics as of rev 5) makes per-note pre-elevation impractical — the user cannot personally vet 122,000 notes. Pollution prevention shifts from **gatekeeping at the door** to **continuous cleaning across the corpus**.

This framework is that cleaning loop. Its job is to:

1. Surface contradictions across the engram corpus.
2. Present each contradiction to the user for triage.
3. Apply the user's chosen resolution as mechanical YAML mutations.
4. Maintain a log of resolutions for the historical record.

The framework grounds in the AHI thesis: the user is the principal; AI assists. AI cannot resolve contradictions in the user's thinking — it can only surface them and apply the resolution the user chooses.

---

## INPUT CONTRACT

**Required (detection phase):**

- **`relationship-graph.db`** — SQLite graph at `~/ora/data/relationship-graph.db` containing the typed relationship corpus (Phase C output). The framework reads `contradicts` edges as the primary signal. Format: SQLite schema per `~/ora/orchestrator/tools/relationship_graph.py`. Source: built from vault YAML by `relationship_graph.py rebuild`.
- **Engrams folder** — `~/Documents/vault/Engrams/`. The framework reads each engram's frontmatter (for last-modified date, archived status, provenance tags) and H1 (for the claim title). Source: vault filesystem.

**Required (resolver phase):**

- **Triage queue file** — `Working — Engram Cleaning Queue.md` at vault root, populated by detection and edited by the user with resolution markers. Format: markdown with per-pair sections; each pair has a `[pending]`-prefixed heading the user replaces with a resolution marker. Source: detection produces it; user mutates it.

**Optional:**

- **`--limit N`** — cap on number of pairs surfaced per run. Default: 25. Use lower for focused triage, higher for sprint-mode review.
- **`--prioritize <strategy>`** — prioritization strategy. Default: `bidirectional`. Other values: `recent`, `clustered`, `random`.

---

## OUTPUT CONTRACT

**Detection phase outputs:**

- **`Working — Engram Cleaning Queue.md`** — markdown triage file at vault root. One section per contradiction pair, each with:
  - Pair heading: `## [pending] <truncated-source-claim>`
  - Source/target wikilinks, claim H1s, last-modified dates, confidence
  - Resolution marker line (user edits): `**Resolution:** [pending]`
  - Pre-formatted resolution menu the user picks from
- **Stdout summary** — count of pairs surfaced, prioritization strategy, total contradicts edges in graph.

**Resolver phase outputs:**

- **Vault file mutations** — for each non-skipped pair:
  - `changed-mind:source-supersedes-target` → adds a `supersedes` relationship (source → target) in the source's frontmatter; adds `archived` tag to the target's frontmatter.
  - `changed-mind:target-supersedes-source` → mirror of above (target supersedes source).
  - `wrong:source` → adds `archived` tag to the source.
  - `wrong:target` → adds `archived` tag to the target.
  - `hypocrisy` → no automatic mutation; logged for the user's reflection.
  - `skip` → no action.
- **`Working — Engram Cleaning Log.md`** — history file at vault root. Append-only log of resolutions: timestamp, pair, resolution marker, files mutated.
- **ChromaDB metadata refresh** — for affected files, the resolver pushes the updated YAML's metadata into the `knowledge` collection so the new tags (especially `archived`) flow to retrieval.

---

## EXECUTION TIER

specification.

This framework runs in two phases: **detection** (produces the queue) and **resolver** (applies the user's resolutions). They are decoupled — the user can edit the queue at their own pace and run the resolver when satisfied with the markings.

---

## MILESTONES DELIVERED

- ☐ The contradicts-edge corpus is sampled and prioritized into a tractable triage queue.
- ☐ The user reviews the queue and marks resolutions on each pair.
- ☐ The resolver applies the chosen resolutions as mechanical YAML mutations.
- ☐ The resolution log is appended with the actions taken.
- ☐ ChromaDB metadata is refreshed for affected files.

---

## EVALUATION CRITERIA

- **Triage tractability** — each detection run surfaces a queue the user can complete in one sitting (≤25 pairs default; configurable).
- **Resolution fidelity** — the resolver applies exactly the resolutions the user marked, with zero silent mutations.
- **Idempotency** — running detection twice produces a stable queue; running the resolver twice on the same queue is a no-op after the first.
- **Audit trail** — the resolution log captures every mutation for review and rollback.
- **Reversibility** — git is the safety net. The vault is committed before each resolver run; if a resolution turns out to be wrong, `git revert` restores the prior state.

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

The pair is logged with marker `[hypocrisy]` to a separate file: `Working — Engram Cleaning Hypocrisy Review.md`. The user reviews this file at their own pace and may later apply resolutions through normal vault editing or by re-running detection.

### `[wrong:source]` / `[wrong:target]`

The named claim is incorrect.

Mutations:
- Default action: add `archived` tag to the named engram. The engram stays in the vault as a record of past mistakes but leaves default retrieval.
- Aggressive action (`--delete-wrong` flag on the resolver): physically delete the file. Use sparingly; `archived` is the safer default.

### `[skip]`

No mutation. The pair is removed from the queue but logged so it doesn't resurface in subsequent detection runs (until/unless the user explicitly re-includes it via `--include-skipped`).

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

The user runs `/cleaning` interactively or skips. The framework does not auto-execute mutations.

### Manual invocation

```bash
# Detection — produces Working — Engram Cleaning Queue.md
python3 ~/ora/orchestrator/historical/run_engram_cleaning_detection.py [--limit N] [--strategy bidirectional|recent|clustered|random]

# Resolver — applies queued resolutions, mutates vault, refreshes chromadb
python3 ~/ora/orchestrator/historical/run_engram_cleaning_resolver.py [--delete-wrong]
```

### Cadence

The user controls cadence. Suggested:
- **Weekly:** quick `bidirectional --limit 10` sweep to catch the most-likely-real contradictions.
- **After sprint extraction sessions** (Phase 5 / DP runs that add many atomics): trigger via KAC suggestion.
- **Quarterly:** `clustered --limit 50` deep pass to surface drift patterns.

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
