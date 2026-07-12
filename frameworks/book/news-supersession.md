# News Supersession Framework

## Display Name
News Supersession

## Display Description
Cross-vault sweep that surfaces evolving-story article pairs in `Resources/` (news / opinion / reference). As of 2026-07-12 the default mode is fully automated: an AI judgment call — not the user — resolves each candidate as supersede or skip, applies the mutation, and logs the decision. No triage queue sits in the loop. The manual `/news` queue workflow remains available for ad hoc or exploratory sweeps — see LAYER 7. Identifies the current version of each story; down-weights superseded older versions without erasing them from retrieval. Parallel framework to Engram Cleaning but with different detection logic (topic-cluster + date-sort instead of `contradicts` edges) and different resolution mechanics (`superseded` weight modifier instead of `archived` filter).

---

## PURPOSE

Today's `Resources/` directory holds 2,632+ source-extracted resource files, many of which are news articles from 2023–2026 covering evolving stories — the Trump-China trade negotiations, Bezos's wedding, AI research releases, the Iran conflict. Without supersession marking, RAG retrieval pulls both the May article and the September follow-up about the same story with no signal which one is current. A query about *"current state of the trade negotiations"* surfaces 2025 reporting alongside 2026 reporting and lets similarity alone arbitrate.

This framework is the resolution loop for that problem. Its job is to:

1. Cluster `Resources/` articles by topic via embedding similarity.
2. Within each cluster, identify supersession candidates — pairs where one article is a newer version of an evolving story.
3. Judge each candidate — automated by default (LAYER 7), or present to the user for manual triage (LAYER 1-6).
4. Apply the chosen resolution as mechanical YAML mutations.
5. Maintain a log of resolutions for the historical record.

**2026-07-12 revision to the framework's grounding:** the original v1.0 design read the same AHI principle as Engram Cleaning — AI surfaces candidates, the user decides. In practice, detection had been silently broken since the 2026-05-29 embedder migration (it opened the physical ChromaDB collection directly instead of resolving the logical name, so it queried an empty collection and always reported zero candidates — nobody triaged anything because nothing was ever surfaced). Fixing that wiring bug reopened the question of how a corpus this size (thousands of resource files, growing continuously via ingest) gets triaged at all. The same volume argument that moved Engram Cleaning to automated judgment applies here: manual `/news` triage remains available, but the default is now the standing-instruction model described in Engram Cleaning's PURPOSE section — the user decided once, durably, what supersession judgment should apply; the AI executes it per-pair and retains the off-switch and audit trail.

What's different from Engram Cleaning is the resolution mechanic — see §"How News Supersession Differs From Engram Cleaning" below for the load-bearing distinction — and the detection logic (topic-cluster + date-sort, not `contradicts` edges, so there is no `date-gap`-style strategy or Phase-C fold here; LAYER 7 automates the existing `topic-cluster` strategy once its detection wiring is correct).

---

## How News Supersession Differs From Engram Cleaning

The two frameworks share the supersession concept but diverge on what it *means* in their respective domains.

### Engram Cleaning (existing)

When a pair is marked `[changed-mind:source-supersedes-target]` (manually or by LAYER 7's automated judgment), the older engram is *wrong* (or no longer reflects current thinking). The resolver:
- Adds a `supersedes` relationship from newer → older
- Adds the **`archived`** tag to the older engram (excludes from default retrieval per Schema §6.5)

This is right for engrams: surfacing a wrong claim during retrieval misleads future reasoning.

### News Supersession (this framework)

When a topic-cluster pair is judged the same story, the older article is *outdated* but not wrong. The resolver:
- Adds a `supersedes` relationship from newer → older
- Adds the **`superseded`** tag to the older article (weight modifier per Schema §6.5; reduces effective weight from P2 0.8 to **0.6**)

The `archived` mechanic is wrong for news because **news stories develop, but they don't replace history**. An older news article isn't a wrong claim that should disappear from the AI's view — it's the primary record from a particular moment in an evolving story. A query about *"what was reported about Trump-China trade in June 2025?"* must still be able to surface the June article. The `superseded` mechanic preserves the record while tilting current-state queries toward the present.

The `wrong:source` and `wrong:target` markers retain `archived` semantics in news context — when an article is factually wrong (not just outdated), archive is the right action. Only `[changed-mind:*]` markers behave differently between the two frameworks. LAYER 7's automated judgment is binary (supersede/skip), same as Engram Cleaning's — it does not attempt the `wrong:*` distinction; that stays a manual-review-only marker in both frameworks.

---

## INPUT CONTRACT

**Required (detection phase):**

- **`Resources/` folder** — `~/Documents/vault/Resources/`. The framework reads each resource file's frontmatter (for `tags`, `date created`, `processed_date`, source provenance) and body (for title + first paragraph used in clustering). Source: vault filesystem.
- **ChromaDB `knowledge` collection** — for embedding-similarity clustering. Opened via `orchestrator.embedding.get_collection()` (logical→physical name resolution — see the 2026-07-12 wiring-fix note in DEPENDENCIES). Source: `~/ora/chromadb/`.

**Required (resolver phase, manual mode):**

- **Triage queue file** — `Working — News Supersession Queue.md` at vault root, populated by detection and edited by the user with resolution markers. Format: markdown with per-pair sections; each pair has a `[pending]`-prefixed heading and a Resolution line.

**Required (automated mode, LAYER 7):**

- **A configured model slot** — `evaluator`, falling back to `sidebar`, per `~/ora/config/routing-config.json`. If neither slot resolves, the sweep fails open (skips the pair, logs the error, retries next sweep) rather than blocking.

**Optional:**

- **`--limit N`** — cap on number of pairs surfaced per run (manual mode). Default: 25. Use lower for focused triage, higher for sprint-mode review.
- **`--similarity T`** — cosine-similarity threshold for topic clustering. Default: **0.80**. Lower values include more loosely-related articles; higher values restrict to near-duplicates.
- **`--strategy S`** — prioritization strategy. Default: `topic-cluster`. See §"LAYER 1: PRIORITIZATION" for alternatives.

---

## OUTPUT CONTRACT

**Detection phase outputs (manual mode):**

- **`Working — News Supersession Queue.md`** — markdown triage file at vault root. One section per supersession-candidate pair, each with:
  - Pair heading: `## [pending] <truncated-newer-article-title>`
  - Article wikilinks, titles, dates, tags
  - Topic-cluster context: shared entities, similarity score, date gap
  - Resolution marker line (user edits): `**Resolution:** [pending]`
  - Pre-formatted resolution menu the user picks from
- **Stdout summary** — count of pairs surfaced, prioritization strategy, total candidate clusters scanned.

**Resolver phase outputs (both modes — manual resolver and LAYER 7's automated sweep converge on identical mutations):**

- **Vault file mutations** — for each non-skipped pair:
  - `[changed-mind:source-supersedes-target]` → adds `supersedes` relationship (source → target) in source's frontmatter; adds **`superseded`** tag to target's frontmatter.
  - `[changed-mind:target-supersedes-source]` → mirror of above.
  - `[wrong:source]` → adds `archived` tag to source (factually wrong, not just outdated; same semantics as Engram Cleaning). Manual mode only.
  - `[wrong:target]` → adds `archived` tag to target. Manual mode only.
  - `[skip]` → no action, but still logged (automated mode logs every skip so the pair doesn't resurface).
  - `[hypocrisy]` → not applicable to news; if used, treated as `[skip]`. Manual mode only.
- **`Working — News Supersession Log.md`** — history file at vault root. Append-only log of resolutions: timestamp, pair, resolution marker, files mutated. Automated-mode entries additionally carry a `**Judge:** model (<slot>) — <reason>` line.
- **ChromaDB metadata refresh** — for affected files, the resolver pushes the updated YAML's metadata into the `knowledge` collection so the new tags flow to retrieval.

---

## EXECUTION TIER

specification.

Manual mode runs in two phases: **detection** (produces the queue) and **resolver** (applies the user's resolutions), decoupled so the user can edit the queue at their own pace. Automated mode (LAYER 7) collapses detection, judgment, and resolution into one scheduled sweep — no decoupled phases, no queue file.

---

## MILESTONES DELIVERED

- ☑ The candidate-pair corpus is sampled and prioritized into a tractable triage queue (manual mode, LAYER 1-6).
- ☑ The user reviews the queue and marks resolutions on each pair (manual mode).
- ☑ The resolver applies the chosen resolutions as mechanical YAML mutations.
- ☑ The resolution log is appended with the actions taken.
- ☑ ChromaDB metadata is refreshed for affected files.
- ☑ **(2026-07-12) Detection wiring fixed** — the collection-open bug that made detection silently report zero candidates since the 2026-05-29 embedder migration is resolved; `topic-cluster` detection now actually queries live data.
- ☑ **(2026-07-12) A model judgment replaces the human triage step** — LAYER 7's automated sweep judges each candidate directly and applies the same resolver mechanics, with no queue and no human in the loop.
- ☑ **(2026-07-12) The sweep runs on a schedule, governed by the vault** — weekly by default via the maintenance scheduler's `Reference — Ora Periodic Maintenance.md` control doc; `off` is the user's escape hatch.

---

## EVALUATION CRITERIA

- **Triage tractability** — each manual detection run surfaces a queue the user can complete in one sitting (≤25 pairs default; configurable).
- **Resolution fidelity** — the resolver applies exactly the resolutions marked (manual) or judged (automated), with zero silent mutations.
- **Cross-tag-type guard** — `news` articles don't supersede `opinion` pieces (and vice versa); `reference` documents don't supersede news. The framework respects artifact-type boundaries; only same-tag pairs become supersession candidates.
- **History preservation** — superseded articles remain retrievable at reduced weight; the resolver never emits `archived` for `[changed-mind:*]` markers (manual or automated).
- **Idempotency** — running detection twice produces a stable queue; running the resolver twice on the same queue is a no-op after the first. Automated mode: a judged pair (supersede or skip) never resurfaces in a later sweep.
- **Fail-open** (automated mode) — a model error, missing endpoint, or unparseable response skips that pair and retries next sweep; it never blocks the sweep or the pairs after it.
- **Audit trail** — the resolution log captures every mutation for review and rollback, including the model's stated reason in automated mode.
- **Reversibility** — git is the safety net. The vault is committed before each resolver run; if a resolution turns out to be wrong, `git revert` restores the prior state.

---

## LAYER 1: PRIORITIZATION

There is no `contradicts`-edge corpus to walk for news (different from Engram Cleaning). Instead, the framework clusters articles by topic via embedding similarity, then identifies supersession candidates within each cluster.

### Strategy: `topic-cluster` (default — both manual mode and LAYER 7's automated sweep)

The framework prioritizes pairs surfaced by the following pipeline:

1. **Filter the resource corpus** to chunks tagged `news`, `opinion`, or `resource` and not already carrying `archived` or `superseded`.
2. **Cluster by embedding similarity.** For each candidate chunk, query ChromaDB for nearest neighbors with cosine similarity ≥ threshold (default 0.80) within the same tag (`news` clusters separately from `opinion`; cross-tag-type pairs are excluded per the cross-tag-type guard).
3. **Within each cluster, sort by date** (`date created` from filename / frontmatter).
4. **Generate supersession candidates:** pair each older article with the next-newer article in the same cluster. Skip pairs where both have the same date (no temporal supersession in same-day publishing of two related articles — those would surface as duplicates and need different handling, deferred).
5. **Apply secondary check (Approach B as filter):** for each candidate pair, compute named-entity overlap between titles + first paragraphs. If entity overlap is below threshold (suggesting the cluster grouped articles about distinct events sharing topical vocabulary), drop the pair from the queue. This reduces false positives where embedding similarity grouped articles about, say, two different Apple research papers.
6. **Cap output at `--limit N`** (manual) or `MAX_NEWS_PAIRS` (automated, LAYER 7) by similarity score descending (highest-confidence candidates first).

### Strategy: `recent` (alternative, manual mode)

Pairs where at least one article was last-modified in the last 30 days. Surfaces supersession candidates involving recent reporting where the user is most likely to remember the story arc and apply meaningful resolution. Uses the same topic-cluster + date-sort logic as the default strategy, just date-filtered.

### Strategy: `random` (alternative, manual mode)

Uniform random sample. Useful for unbiased corpus-health spot-checks.

---

## LAYER 2: TRIAGE QUEUE FORMAT (manual mode)

The detection phase writes `Working — News Supersession Queue.md` at vault root. Format:

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

The cluster-signal line surfaces what made the framework consider the pair related — the user can decide quickly whether the signal reflects a genuine supersession or a false-positive cluster. LAYER 7's automated judgment receives this same signal as context (similarity, entity overlap, date gap) alongside the article text.

---

## LAYER 3: RESOLUTION MECHANICS

The resolver reads the queue file (manual mode) or a judged candidate (automated mode, LAYER 7) and processes each pair whose resolution is not `[pending]`. Mechanics per resolution marker:

### `[changed-mind:source-supersedes-target]`

Source article is the current version; target is older.

Mutations:
1. **Add `supersedes` relationship** to the source's frontmatter `relationships:` list (same format as Engram Cleaning).
2. **Add `superseded` tag** to the target's frontmatter `tags:` list (NOT `archived`).

The target stays retrievable at reduced weight (0.6) per Schema §6.5. Older versions of the story remain accessible for date-anchored queries; current-state queries naturally favor the source.

### `[changed-mind:target-supersedes-source]`

Mirror of the above: target supersedes source. Target gets the relationship; source gets `superseded`.

### `[wrong:source]` / `[wrong:target]` (manual mode only)

The named article is factually wrong (not just outdated). This is rarer in news context — most older articles are *outdated*, not *wrong* — but corrections, retractions, and original-reporting errors do happen.

Mutations:
- Default action: add **`archived`** tag (filter; excludes from default retrieval per Schema §6.5). Same mechanic as Engram Cleaning's `wrong:*` markers.
- The article stays in the vault as a record of past mistakes but leaves default retrieval.

LAYER 7's automated judgment does not use `wrong:*` — distinguishing "outdated" from "factually wrong" stays a manual-review call; the automated sweep only ever applies supersede or skip.

### `[skip]`

No mutation. The pair is removed from the manual queue, or (automated mode) simply not mutated — either way it's logged so it doesn't resurface in subsequent runs (manual: until/unless the user re-includes it via `--include-skipped`; automated: never, short of manually editing the log).

### `[hypocrisy]` (manual mode only)

Not applicable to news (the user does not "hold" two contradicting news articles as their own positions). If the marker appears, the resolver treats it as `[skip]` and emits a warning. LAYER 7's automated judgment never emits this marker.

---

## LAYER 4: RESOLUTION LOG

The resolver appends each completed resolution to `Working — News Supersession Log.md` at vault root, mirroring the Engram Cleaning Log format. Automated-mode entries (LAYER 7) carry a `**Judge:** model (<slot>) — <reason>` line and the marker is suffixed `(auto)`. The log is the audit trail; rollback via `git revert`.

---

## LAYER 5: CHROMADB METADATA REFRESH

After mutations land, the resolver pushes the updated YAML metadata into the ChromaDB `knowledge` collection for affected files — same pattern as Engram Cleaning. The `superseded` tag must flow to retrieval immediately so the weight-modifier takes effect on subsequent queries; otherwise queries continue to use stale (un-superseded) weight until next refresh. LAYER 7's automated sweep uses this exact same refresh call.

---

## LAYER 6: SELF-EVALUATION

After running, the framework reports:

- **Pairs surfaced:** N
- **Pairs resolved:** N (changed-mind: X, wrong: Y, skip: Z) — manual mode
- **Files mutated:** N
- **`superseded` tags applied:** N (subset of mutations; tracks the news-specific mechanic)
- **`archived` tags applied:** N (only from `wrong:*` markers, manual mode)
- **ChromaDB updates:** N
- **Errors:** N (with file paths)

If errors > 0, the framework lists the affected files and exits non-zero. The user inspects, fixes, and re-runs the resolver — idempotency guarantees no double-mutation. LAYER 7's automated sweep reports the equivalent shape (candidates found / judged / superseded / skipped / errors / left for next sweep) in its maintenance-scheduler task result — see LAYER 7.

---

## LAYER 7: AUTOMATED JUDGED SWEEP (2026-07-12)

The default mode. No triage queue, no manual Resolution-line editing — the AI makes the supersession call itself, applies it, and logs it. Implementation: `orchestrator/tools/supersession_sweep.py::task_news_supersession`, `orchestrator/historical/supersession_judge.py` (shared with Engram Cleaning's LAYER 7).

### Why scheduled, not runtime-triggered

Ora's Runtime Principle holds that a process executable at runtime should not be deferred to a schedule. This framework's automated mode is scheduled, and that requires justification, mirroring Engram Cleaning's LAYER 7: the natural runtime hook — "after Resources/ ingest events" (INTEGRATION, below) — only covers newly-ingested articles. It cannot reach the existing multi-thousand-file `Resources/` backlog, which is not tied to any single write event and needs a whole-corpus re-scan to cluster. That backlog is exactly what detection had never actually been surfacing since the 2026-05-29 collection-wiring bug (see DEPENDENCIES) — fixing the bug without also automating the sweep would have left the backlog to accumulate indefinitely behind a triage queue nobody has time to clear by hand. The scheduled sweep sits alongside Engram Cleaning's and the pre-existing `orphan_cleanup` / `vault_health` / `graph_density` tasks in `orchestrator/maintenance_scheduler.py` for the same reason: whole-corpus sweeps with no natural runtime trigger.

### Candidate sourcing

Each sweep run pulls `topic-cluster` detection candidates (LAYER 1) via `run_news_supersession_detection.detect_topic_cluster()`, filtered against `Working — News Supersession Log.md`'s resolved-pair set (the same filter manual detection uses, so a judged pair — supersede or skip — never resurfaces), ordered by similarity score descending, capped at the per-sweep bound (below).

### The judgment call

For each candidate pair, `supersession_judge.judge_pair()` sends both articles' title (H1), date, and body excerpt (capped at `MAX_NOTE_CHARS`, default 3000 chars, provisional) plus the cluster signal (similarity, entity overlap, date gap) to a model via `orchestrator/model_dispatch.py::invoke_chat`, slot `evaluator` falling back to `sidebar`, `context="autonomous"` (local transports only — no metered API cost for an unattended sweep; model selection is never hardcoded). The model returns exactly:

```
VERDICT: SUPERSEDE
REASON: <one line>
```

or `VERDICT: SKIP` with the same reason line. The prompt frames the news-specific question — does the newer article represent the developed version of the same evolving story, or are these different angles/different stories that happen to cluster on embedding similarity — and instructs SKIP as the safe default under uncertainty, mirroring the entity-overlap false-positive guard LAYER 1's `topic-cluster` strategy already applies mechanically.

### Application and logging

- **SUPERSEDE** → applies through the exact same `apply_supersession()` resolver mechanics as manual `[changed-mind:source-supersedes-target]` (LAYER 3): `supersedes` relationship on the newer article, **`superseded`** tag (weight modifier, not `archived`) on the older, ChromaDB metadata refresh for both.
- **SKIP** → no mutation, but the pair is still appended to `Working — News Supersession Log.md` (marked `skip (auto)`) so it does not resurface next sweep.
- **Model error** (unreachable endpoint, unparseable response, any exception) → **NOT logged**. The pair is not marked resolved, so it retries on the next sweep once the model is healthy again. Fail-open: a broken model never blocks the sweep and never gets silently treated as a resolved judgment.

Every log entry — supersede or skip — carries the `**Judge:** model (<slot>) — <reason>` line, so the resolution log doubles as the automated system's audit trail, same file, same format the manual workflow already used.

### Per-sweep bound

`MAX_NEWS_PAIRS` (default 25, provisional tuning constant, `ORA_SUPERSESSION_NEWS_PAIRS`) caps how many pairs one sweep judges. The task result message reports candidates found vs. judged vs. left for next sweep — no silent truncation.

### Schedule and escape hatch

Registered as task `news_supersession` in `orchestrator/maintenance_scheduler.py`, cadence governed by `Reference — Ora Periodic Maintenance.md`'s frontmatter (default `weekly`). Setting the cadence to `off` in that document is the escape hatch — the automated sweep stops, and the manual `/news` workflow (LAYER 1-6) remains fully available regardless of the scheduled mode's state.

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

### Direct CLI (for scripting or sleep-wake invocation)

```bash
# Detection — produces Working — News Supersession Queue.md
python3 ~/ora/orchestrator/historical/run_news_supersession_detection.py \
    [--strategy topic-cluster|recent|random] \
    [--limit N] [--similarity T]

# Resolver — applies queued resolutions, mutates vault, refreshes chromadb
python3 ~/ora/orchestrator/historical/run_news_supersession_resolver.py [--dry-run]

# Automated judged sweep (LAYER 7) — normally run by the maintenance scheduler,
# but callable standalone for testing or an out-of-cadence pass:
python3 ~/ora/orchestrator/tools/supersession_sweep.py news
```

### Cadence

**Automated mode (default):** weekly, via the maintenance scheduler — see LAYER 7. Governed by `Reference — Ora Periodic Maintenance.md`; set `news_supersession: off` there to disable.

**Manual mode:** the user controls cadence at will. Suggested:
- **After Resources/ ingest events** (when new articles get extracted from cleaned-pair conversations into Resources/): run detection to catch new supersession candidates immediately, ahead of the weekly automated sweep.
- Ad hoc: quick `topic-cluster --limit 10` sweep to spot-check a specific story.
- **Quarterly:** deep pass for corpus-wide health.

---

## DEPENDENCIES

- **Schema rev 5.1+** — `superseded` tag is in the controlled vocabulary; weight modifier behavior is documented in §6.5.
- **`~/ora/orchestrator/provenance.py::weight_for()`** — must apply the `superseded` modifier (P2 0.8 → 0.6) when present on a `resource` chunk.
- **ChromaDB `knowledge` collection** — must include Resources/ entries (indexed 2026-05-09).
- **`orchestrator/embedding.py::get_collection()`** — detection must resolve the `knowledge` collection's logical name to its physical name through this helper. **2026-07-12 fix:** detection previously called `chromadb`'s raw `client.get_collection("knowledge")`, which opened the empty pre-2026-05-29-migration physical collection and silently reported zero candidates for six weeks — detection appeared to work (no error) but never actually surfaced anything. Any future call site touching this collection must go through `get_collection`/`get_or_create_collection`, never a raw client call.
- **Vault is a git repo** — for rollback safety.
- **Engram Cleaning Framework** — the resolver shares mechanics with `~/ora/orchestrator/historical/run_engram_cleaning_resolver.py` (parameterized by target-tag: `archived` for engrams, `superseded` for news) and LAYER 7's judgment core (`orchestrator/historical/supersession_judge.py`) is shared verbatim between both frameworks.
- **(LAYER 7) `orchestrator/tools/supersession_sweep.py`** — the scheduled task.
- **(LAYER 7) `orchestrator/model_dispatch.py::invoke_chat`** — model routing; never a hardcoded model.
- **(LAYER 7) `orchestrator/maintenance_scheduler.py`** + **`Reference — Ora Periodic Maintenance.md`** — cadence governance.

---

## DEFERRED FOR LATER

- **Same-day duplicates handling.** Two articles with the same date in the same topic cluster (e.g., Reuters + AP coverage of one event) currently aren't surfaced as supersession candidates. Future enhancement could mark one as duplicate of the other rather than superseded.
- **Multi-step supersession chains.** When article A is superseded by B which is superseded by C, the queue today shows two separate pairs (A↔B and B↔C). A graph-traversal step at retrieval could surface only C as the current version when querying about the story. v1 doesn't do that; users see and resolve the chain pairwise (and LAYER 7's automated sweep judges them pairwise too).
- **Cross-source attribution.** When the same story is reported by multiple outlets (Bloomberg + WSJ + Reuters), the framework treats them as separate articles. A future enhancement could detect cross-source duplicates and mark the most authoritative one as canonical.
- **Opinion-news pairing.** Cross-tag-type supersession is currently disallowed (the cross-tag-type guard). But sometimes an opinion piece responds directly to a specific news article. There's no relationship type that captures "responds to" cleanly today. Future schema revision could add one.
- **Automated `wrong:*` and `hypocrisy` judgment** — LAYER 7's model judgment is binary (supersede/skip) by design; extending it to distinguish "factually wrong" from "outdated" would need a richer judgment contract and is not yet built.
- **Calibrating `MAX_NEWS_PAIRS`** — provisional first guess (25 pairs/sweep), not tuned against outcome data. Revisit once the automated sweep has run enough cycles to sample judgment quality.

---

## CHANGE LOG

- **2026-07-12 (v2.0) — Detection wiring fix + automated judged sweep.** Fixes the collection-open bug that had silently zeroed out detection since the 2026-05-29 embedder migration (raw `chromadb.get_collection` → `orchestrator.embedding.get_collection`). Adds LAYER 7: the default mode is now a scheduled, model-judged sweep with no human triage queue, per explicit user decision (standing zero-manual-labor / fail-open convention), reusing the same `supersession_judge.py` judgment core Engram Cleaning's LAYER 7 introduced. Scheduled weekly via `orchestrator/maintenance_scheduler.py`, governed by `Reference — Ora Periodic Maintenance.md` (`off` = escape hatch); justification for scheduling over runtime execution recorded in LAYER 7 per the vault's Runtime Principle. Manual `/news` workflow (LAYER 1-6) is unchanged and remains available. New/changed modules: `orchestrator/historical/run_news_supersession_detection.py` (one-line collection-wiring fix), `orchestrator/tools/supersession_sweep.py` (new). Tests in `orchestrator/tests/test_supersession_auto.py`.

- **2026-05-10 (v1.0)** — Initial draft. Specifies detection (topic-cluster + date-sort) + resolver workflow, six resolution markers (5 active + `[hypocrisy]` not-applicable), `superseded` tag application, ChromaDB metadata refresh, integration with `/news` slash command. Schema rev 5.1 companion adds the `superseded` tag to the controlled vocabulary. Implementation lands in `~/ora/orchestrator/historical/run_news_supersession_detection.py` and `run_news_supersession_resolver.py` (deferred — implemented after first design review).
