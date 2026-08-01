# News Supersession Framework

## Display Name
News Supersession

## Display Description
Bounded event process for evolving-story pairs touching an exact written Resource, plus an explicit historical-corpus campaign. Runtime model judgment may autonomously apply supersession without per-pair human triage while preserving older reporting at reduced retrieval weight.

---

## PURPOSE

Today's `Resources/` directory holds 2,632 source-extracted resource files, many of which are news articles from 2023–2026 covering evolving stories — the Trump-China trade negotiations, Bezos's wedding, AI research releases, the Iran conflict. Without supersession marking, RAG retrieval pulls both the May article and the September follow-up about the same story with no signal which one is current. A query about *"current state of the trade negotiations"* surfaces 2025 reporting alongside 2026 reporting and lets similarity alone arbitrate.

This framework is the resolution loop for that problem. Its job is to:

1. Cluster `Resources/` articles by topic via embedding similarity.
2. Within each cluster, identify supersession candidates — pairs where one article is a newer version of an evolving story.
3. Complete bounded model judgment before runtime mutation, or present historical campaign candidates for user triage.
4. Apply the governed resolution as a recoverable YAML transaction.
5. Maintain a log of resolutions for the historical record.

The user remains the principal. The approved runtime contract nevertheless delegates bounded pair judgment to a model for exact-write neighborhoods. That delegation is explicit, append-only audited, capped at six pairs, rollback-protected, and has no per-pair human triage. Reflective `wrong:*` classifications remain available through an explicit campaign. The news-specific resolution mechanic remains load-bearing: older reporting is down-weighted, not erased.

---

## How News Supersession Differs From Engram Cleaning

The two frameworks share the supersession concept but diverge on what it *means* in their respective domains.

### Engram Cleaning (existing)

When a user marks a contradicting engram pair as `[changed-mind:source-supersedes-target]`, the older engram is *wrong* (or no longer reflects current thinking). The resolver:
- Adds a `supersedes` relationship from newer → older
- Adds the **`archived`** tag to the older engram (excludes from default retrieval per Schema §6.5)

This is right for engrams: surfacing a wrong claim during retrieval misleads future reasoning.

### News Supersession (this framework)

When the framework marks a topic-cluster pair as the same, the older article is *outdated* but not wrong. The resolver:
- Adds a `supersedes` relationship from newer → older
- Adds the **`superseded`** tag to the older article (weight modifier per Schema §6.5; reduces effective weight from P2 0.8 to **0.6**)

The `archived` mechanic is wrong for news because **news stories develop, but they don't replace history**. An older news article isn't a wrong claim that should disappear from the AI's view — it's the primary record from a particular moment in an evolving story. A query about *"what was reported about Trump-China trade in June 2025?"* must still be able to surface the June article. The `superseded` mechanic preserves the record while tilting current-state queries toward the present.

The `wrong:source` and `wrong:target` markers retain `archived` semantics in news context — when an article is factually wrong (not just outdated), archive is the right action. Only `[changed-mind:*]` markers behave differently between the two frameworks.

---

## INPUT CONTRACT

**Required (detection phase):**

- **`Resources/` folder** — `~/Documents/vault/Resources/`. The framework reads each resource file's frontmatter (for `tags`, `date created`, `processed_date`, source provenance) and body (for title + first paragraph used in clustering). Source: vault filesystem.
- **ChromaDB `knowledge` collection** — for embedding-similarity clustering. Source: `~/ora/chromadb/`.

**Required (manual/campaign resolver phase):**

- **Triage queue file** — `Projects/MSI/Working — News Supersession Queue.md`, populated by detection and edited by the user with resolution markers. Format: markdown with per-pair sections; each pair has a `[pending]`-prefixed heading and a Resolution line.

**Optional:**

- **`--limit N`** — cap on number of pairs surfaced per run. Default: 25. Use lower for focused triage, higher for sprint-mode review.
- **`--similarity T`** — cosine-similarity threshold for topic clustering. Default: **0.80**. Lower values include more loosely-related articles; higher values restrict to near-duplicates.
- **`--strategy S`** — prioritization strategy. Default: `topic-cluster`. See §"LAYER 1: PRIORITIZATION" for alternatives.

**Required (runtime event phase):**

- **Exact Resource identity** — the event contract binds the top-level `Resources/*.md` path, SHA-256 digest, and size before evaluation.
- **Configured model slot** — the runtime uses the governed evaluator/sidebar routing ladder; unresolved or invalid output fails the event without mutation.

---

## OUTPUT CONTRACT

**Detection phase outputs:**

- **`Projects/MSI/Working — News Supersession Queue.md`** — markdown triage file. One section per supersession-candidate pair, each with:
  - Pair heading: `## [pending] <truncated-newer-article-title>`
  - Article wikilinks, titles, dates, tags
  - Topic-cluster context: shared entities, similarity score, date gap
  - Resolution marker line (user edits): `**Resolution:** [pending]`
  - Pre-formatted resolution menu the user picks from
- **Stdout summary** — count of pairs surfaced, prioritization strategy, total candidate clusters scanned.

**Resolver phase outputs (manual and runtime paths converge on the same artifact semantics):**

- **Vault file mutations** — for each non-skipped pair:
  - `[changed-mind:source-supersedes-target]` → adds `supersedes` relationship (source → target) in source's frontmatter; adds **`superseded`** tag to target's frontmatter.
  - `[changed-mind:target-supersedes-source]` → mirror of above.
  - `[wrong:source]` → adds `archived` tag to source (factually wrong, not just outdated; same semantics as Engram Cleaning).
  - `[wrong:target]` → adds `archived` tag to target.
  - `[skip]` → no action.
  - `[hypocrisy]` → not applicable to news; if used, treated as `[skip]`.
- **`Projects/MSI/Working — News Supersession Log.md`** — append-only resolution evidence including model slot/reason for autonomous judgments and the exact files changed.
- **ChromaDB metadata refresh** — for affected files, the resolver pushes the updated YAML's metadata into the `knowledge` collection so the new tags flow to retrieval.
- **Runtime event evidence** — immutable event claim, bounded candidate/judgment evidence, before/after identities, completion or failure, and authenticated rollback state under `data/runtime-hygiene/`.

---

## EXECUTION TIER

specification.

Manual campaigns run in two decoupled phases: detection and resolver. Runtime mode receives one exact Resource write, evaluates at most six neighbors, completes every judgment before mutation, and applies the result as one rollback-protected transaction. An error causes no mutation and no clock fallback.

---

## MILESTONES DELIVERED

- ☑ The manual candidate-pair corpus can be sampled into a tractable triage queue.
- ☑ The manual resolver applies user-marked resolutions.
- ☑ Exact Resource writes can trigger bounded autonomous judgment with no per-pair human triage.
- ☑ All judgments finish before mutation; errors restore the snapshotted state.
- ☑ Resolution and runtime event evidence are append-only, and explicit rollback is drift-safe.
- ☑ ChromaDB metadata is refreshed inside the governed transaction.

---

## EVALUATION CRITERIA

- **Triage tractability** — each detection run surfaces a queue the user can complete in one sitting (≤25 pairs default; configurable).
- **Resolution fidelity** — the resolver applies exactly the user-marked or bounded model-judged resolution, with zero silent mutations.
- **Cross-tag-type guard** — `news` articles don't supersede `opinion` pieces (and vice versa); `reference` documents don't supersede news. The framework respects artifact-type boundaries; only same-tag pairs become supersession candidates.
- **History preservation** — superseded articles remain retrievable at reduced weight; the resolver never emits `archived` for `[changed-mind:*]` markers.
- **Idempotency** — running detection twice produces a stable queue; running the resolver twice on the same queue is a no-op after the first.
- **Audit trail** — the resolution log and runtime event ledger capture autonomous judgment, no-human-triage status, exact before/after identity, and every mutation.
- **Reversibility** — runtime events carry persisted snapshots and drift-safe authenticated rollback; campaigns also retain repository history.

---

## LAYER 1: PRIORITIZATION

There is no `contradicts`-edge corpus to walk for news (different from Engram Cleaning). Instead, the framework clusters articles by topic via embedding similarity, then identifies supersession candidates within each cluster.

### Strategy: `topic-cluster` (default)

The framework prioritizes pairs surfaced by the following pipeline:

1. **Filter the resource corpus** to chunks tagged `news`, `opinion`, or `resource` and not already carrying `archived` or `superseded`.
2. **Cluster by embedding similarity.** For each candidate chunk, query ChromaDB for nearest neighbors with cosine similarity ≥ threshold (default 0.80) within the same tag (`news` clusters separately from `opinion`; cross-tag-type pairs are excluded per the cross-tag-type guard).
3. **Within each cluster, sort by date** (`date created` from filename / frontmatter).
4. **Generate supersession candidates:** pair each older article with the next-newer article in the same cluster. Skip pairs where both have the same date (no temporal supersession in same-day publishing of two related articles — those would surface as duplicates and need different handling, deferred).
5. **Apply secondary check (Approach B as filter):** for each candidate pair, compute named-entity overlap between titles + first paragraphs. If entity overlap is below threshold (suggesting the cluster grouped articles about distinct events sharing topical vocabulary), drop the pair from the queue. This reduces false positives where embedding similarity grouped articles about, say, two different Apple research papers.
6. **Cap output at `--limit N`** by similarity score descending (highest-confidence candidates first).

### Strategy: `recent` (alternative)

Pairs where at least one article was last-modified in the last 30 days. Surfaces supersession candidates involving recent reporting where the user is most likely to remember the story arc and apply meaningful resolution. Uses the same topic-cluster + date-sort logic as the default strategy, just date-filtered.

### Strategy: `random` (alternative)

Uniform random sample. Useful for unbiased corpus-health spot-checks.

---

## LAYER 2: TRIAGE QUEUE FORMAT

The detection phase writes `Projects/MSI/Working — News Supersession Queue.md`. Format:

```markdown
---
nexus:
  - ora
type: working
tags:
  - news-supersession
date created: <YYYY-MM-DD>
date modified: <YYYY-MM-DD>
---

# News Supersession Queue — <YYYY-MM-DD>

*Generated by Framework — News Supersession detection phase. Strategy: <strategy>. Pairs: <N>. Similarity threshold: <T>.*

For each pair below, edit the **Resolution** line. Replace `[pending]` with one of:
- `[changed-mind:source-supersedes-target]` — source article is the current version of the story; target is older
- `[changed-mind:target-supersedes-source]` — target article is the current version of the story; source is older
- `[wrong:source]` — source article is factually wrong; archive (note: this is different from "older" — use only when the article is incorrect, not just outdated)
- `[wrong:target]` — target article is factually wrong; archive
- `[skip]` — defer; the cluster grouped two articles that don't actually supersede each other (different angles on related events, opinion responding to news, or false-positive cluster)

When done, run the resolver: `python3 ~/ora/orchestrator/historical/run_news_supersession_resolver.py`

---

## [pending] <newer-article-title-truncated>

- **Source:** [[<source-filename>]] (<YYYY-MM-DD>, tag: <news|opinion|resource>)
  *<source title — full>*
- **Target:** [[<target-filename>]] (<YYYY-MM-DD>, tag: <news|opinion|resource>)
  *<target title — full>*
- **Cluster signal:** similarity <T>, entity overlap <N entities shared>, date gap <N days>
- **Strategy match:** topic-cluster

**Resolution:** [pending]

---

## [pending] ...

(repeat per pair)
```

The cluster-signal line surfaces what made the framework consider the pair related — the user can decide quickly whether the signal reflects a genuine supersession or a false-positive cluster.

---

## LAYER 3: RESOLUTION MECHANICS

The resolver reads the queue file and processes each pair whose Resolution is non-`[pending]`. Mechanics per resolution marker:

### `[changed-mind:source-supersedes-target]`

Source article is the current version; target is older.

Mutations:
1. **Add `supersedes` relationship** to the source's frontmatter `relationships:` list (same format as Engram Cleaning).
2. **Add `superseded` tag** to the target's frontmatter `tags:` list (NOT `archived`).

The target stays retrievable at reduced weight (0.6) per Schema §6.5. Older versions of the story remain accessible for date-anchored queries; current-state queries naturally favor the source.

### `[changed-mind:target-supersedes-source]`

Mirror of the above: target supersedes source. Target gets the relationship; source gets `superseded`.

### `[wrong:source]` / `[wrong:target]`

The named article is factually wrong (not just outdated). This is rarer in news context — most older articles are *outdated*, not *wrong* — but corrections, retractions, and original-reporting errors do happen.

Mutations:
- Default action: add **`archived`** tag (filter; excludes from default retrieval per Schema §6.5). Same mechanic as Engram Cleaning's `wrong:*` markers.
- The article stays in the vault as a record of past mistakes but leaves default retrieval.

### `[skip]`

No mutation. The pair is removed from the queue but logged so it doesn't resurface in subsequent detection runs (until/unless the user re-includes it via `--include-skipped`).

### `[hypocrisy]`

Not applicable to news (the user does not "hold" two contradicting news articles as their own positions). If the marker appears, the resolver treats it as `[skip]` and emits a warning.

---

## LAYER 4: RESOLUTION LOG

The resolver appends each completed resolution to `Projects/MSI/Working — News Supersession Log.md`, mirroring the Engram Cleaning Log format. The log is the audit trail; rollback via `git revert`.

---

## LAYER 5: CHROMADB METADATA REFRESH

After mutations land, the resolver pushes the updated YAML metadata into the ChromaDB `knowledge` collection for affected files — same pattern as Engram Cleaning. The `superseded` tag must flow to retrieval immediately so the weight-modifier takes effect on subsequent queries; otherwise queries continue to use stale (un-superseded) weight until next refresh.

---

## LAYER 6: SELF-EVALUATION

After running, the framework reports:

- **Pairs surfaced:** N
- **Pairs resolved:** N (changed-mind: X, wrong: Y, skip: Z)
- **Files mutated:** N
- **`superseded` tags applied:** N (subset of mutations; tracks the news-specific mechanic)
- **`archived` tags applied:** N (only from `wrong:*` markers)
- **ChromaDB updates:** N
- **Errors:** N (with file paths)

If errors > 0, the framework lists the affected files and exits non-zero. The user inspects, fixes, and re-runs the resolver — idempotency guarantees no double-mutation.

---

## INTEGRATION

### Slash commands (chat interface, mechanical — no model call)

```
/news                                  → status summary
/news status                           → queue state without re-running detection
/news detect [strategy] [limit] [--similarity T]   → produce triage queue (default: topic-cluster 25 0.80)
/news resolve                          → dry-run resolver against current queue
/news resolve --apply                  → apply queued resolutions
/news help                             → usage
```

The `/news` family is registered in `~/ora/orchestrator/slash_commands.py` alongside `/cleaning` and the meta-layer mechanical operations. It bypasses the analytical pipeline entirely.

### Direct CLI (explicit historical campaign only)

```bash
# Detection — produces Projects/MSI/Working — News Supersession Queue.md
python3 ~/ora/orchestrator/historical/run_news_supersession_detection.py \
    [--strategy topic-cluster|recent|random] \
    [--limit N] [--similarity T]

# Resolver — applies queued resolutions, mutates vault, refreshes chromadb
python3 ~/ora/orchestrator/historical/run_news_supersession_resolver.py [--dry-run]
```

### Runtime trigger and campaign boundary

An exact top-level Resource write automatically evaluates at most six semantic neighbors. Model judgment is autonomous and bounded; there is no per-pair human triage. All judgments finish before mutation. The runtime records append-only event, judgment, before/after, and rollback evidence; any error restores subject state and has no clock-driven retry.

The CLI above is a historical-backlog campaign surface. A deep or corpus-wide pass requires an explicit campaign identity and command provenance. Weekly and quarterly sweeps are prohibited.

---

## DEPENDENCIES

- **Schema rev 5.1+** — `superseded` tag is in the controlled vocabulary; weight modifier behavior is documented in §6.5.
- **`~/ora/orchestrator/provenance.py::weight_for()`** — must apply the `superseded` modifier (P2 0.8 → 0.6) when present on a `resource` chunk.
- **ChromaDB `knowledge` collection** — must include Resources/ entries (indexed 2026-05-09).
- **Vault is a git repo** — for rollback safety.
- **Engram Cleaning Framework** — the resolver may share logic with `~/ora/orchestrator/historical/run_engram_cleaning_resolver.py` via parameterization (target-tag = `archived` for engrams, `superseded` for news).

---

## DEFERRED FOR LATER

- **Same-day duplicates handling.** Two articles with the same date in the same topic cluster (e.g., Reuters + AP coverage of one event) currently aren't surfaced as supersession candidates. Future enhancement could mark one as duplicate of the other rather than superseded.
- **Multi-step supersession chains.** When article A is superseded by B which is superseded by C, the queue today shows two separate pairs (A↔B and B↔C). A graph-traversal step at retrieval could surface only C as the current version when querying about the story. v1 doesn't do that; users see and resolve the chain pairwise.
- **Cross-source attribution.** When the same story is reported by multiple outlets (Bloomberg + WSJ + Reuters), the framework treats them as separate articles. A future enhancement could detect cross-source duplicates and mark the most authoritative one as canonical.
- **Opinion-news pairing.** Cross-tag-type supersession is currently disallowed (the cross-tag-type guard). But sometimes an opinion piece responds directly to a specific news article. There's no relationship type that captures "responds to" cleanly today. Future schema revision could add one.

---

## CHANGE LOG

- **2026-05-10 (v1.0)** — Initial draft. Specifies detection (topic-cluster + date-sort) + resolver workflow, six resolution markers (5 active + `[hypocrisy]` not-applicable), `superseded` tag application, ChromaDB metadata refresh, integration with `/news` slash command. Schema rev 5.1 companion adds the `superseded` tag to the controlled vocabulary. Implementation lands in `~/ora/orchestrator/historical/run_news_supersession_detection.py` and `run_news_supersession_resolver.py` (deferred — implemented after first design review).
