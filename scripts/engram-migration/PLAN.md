# Engram Corpus Repair — Plan and Handoff

Written 2026-08-12. Self-contained: everything needed to finish this without the
session that produced it. Read it all before running anything.

---

## 1. What this is

A personal knowledge base of auto-extracted "atomic notes" distilled from ~40,000
AI conversations. The owner's goal: **one corpus of notes that are generalizable,
internally coherent, and not contrary to fact.** The source conversations are
irrelevant to that test — 85% of the paths cited in the notes no longer exist on
disk, and even where they do, a note's truth is judged on its own face.

Two things went wrong historically, and both are now fixed at the source:

1. **Over-extraction.** The extractor processed one conversation-pair at a time
   with no knowledge of the corpus, so one principle revisited across thirty
   conversations minted thirty notes. The count measured *mentions*, not concepts.
2. **Instance-locking.** The extraction prompt demanded every bullet "name what
   does what", which welded each note to whoever happened to act in that
   conversation — "Honnold eliminates execution uncertainty by memorizing every
   hold" rather than "pre-memorization converts problem-solving under stress into
   rehearsed performance." Measured on a 45-note random sample, **~60% could not
   be applied outside their source domain.**

**Both producers are fixed and landed** (`~/ora`, commits `3d4ab7d1` batch
extractor and `bd4f2b31` live path). New conversations mint proper notes. Nothing
below is required to stop the corpus getting worse — it is repair of what exists.

---

## 2. Current state

Working tree **`~/engram-work`**, branch `engram-permanent-notes`. This is a git
worktree of the vault at `~/Documents/vault`. **The live vault is untouched.**

| | |
|---|---|
| `Engrams/` — the single corpus | **75,734 notes**, flat, no subdirectories |
| with working relationships | 64,090 (84.6%), **604,099 edges** |
| missing relationships | **11,644** (the incorporated Historical Atomics notes) |
| `Archive/Engram Absorbed Sources 2026-08/` | 122,118 pre-merge originals |
| `Archive/Historical Atomics Not Incorporated 2026-08/` | 2,477 (facts, perishable, dated, 3 predictions) |
| Rewrite in progress | **1,644 of 4,038** done, ~2.2 h remaining |

**A rewrite process is running right now**, detached (`ppid 1`), 8 workers:

```bash
tail -5 ~/engram-work/.migration/rewrite-run.log
ps -eo pid=,etime=,args= | grep "[r]ewrite_run.py"     # NOT pgrep — see §6
```

It is resumable and idempotent. If it dies, re-run the identical command; the
worklist is derived from which output files already exist.

---

## 3. How the corpus got to this shape

**Migration (Codex, completed):** 122,118 originals were clustered into 64,144
groups and each group rewritten as one merged note. The originals were archived,
not deleted. This is the work that produced the current top-level corpus.

**The migration's writing pass was defective**, and the cause was an input-design
error rather than a weak model: the writer received member *titles* plus a list of
"specifics" that an earlier stage had extracted — isolated keywords, bare dates,
filename debris — and never saw the source note bodies. A 48-note audit against
full sources measured:

| | |
|---|---|
| Generalizable | 46/48 (96%) — this part worked |
| Kept every idea from its sources | 21/48 (44%) |
| Internally coherent | 41/48 (85%) |
| **Contrary to fact** | **7/48 (15%)** |
| Better than the originals | 30 better · 13 same · 5 worse |
| **Rejected outright** | **0** |

**Nothing is junk.** The dominant failure is *de-fanging*: the merge keeps the
general claim and drops the clause that gave it force, leaving a tautology. One
note lost "despite the dual mandate of price stability and full employment" and was
left asserting only that captured institutions favour their capturers. Another lost
"without any elected official casting a vote."

Second failure, rarer and worse: **imported terms of art.** Titles claimed "the
framing effect", "photographic memory", "identity-protective cognition" — each
naming a different mechanism than the note's own content. These falsehoods were
introduced by the migration, not inherited.

**Historical Atomics (incorporated 2026-08-12):** `Engrams/Historical Atomics/`
held 14,049 notes the entire migration never saw — `phase5_atomic_extraction.py`
hardcodes its output there and every migration script globbed `Engrams/*.md`
non-recursively. They were **not duplicates**: of 2,265 distinct (conversation,
turn) citations only 22 appear in the archive (1.0%), and the date ranges are
complementary — the main corpus stops at end of April 2026 while 90% of that folder
is May–July. It was the continuation. 11,575 were folded into the corpus; 2,474
archived (1,888 tagged `fact`, 505 perishable politics, 577 carrying a year).

---

## 4. Remaining steps, in order

Order matters: rewrites change titles, and relationship edges are keyed by title.

### Step A — finish the rewrite (running)

```bash
python3 ~/ora/scripts/engram-migration/rewrite_run.py --apply \
  --worklist ~/engram-work/.migration/opus_worklist.json --workers 8
```

4,038 notes carrying a mechanically detected defect. **~4,900 tokens per note,
~19.8M total.** Opus, batch 1. Writes one JSON per note to
`.migration/rewrite/`; touches no vault file.

### Step B — apply the rewrites to the notes

**NOT YET BUILT.** Reads `.migration/rewrite/*.json` and writes each `title` and
`body` into its note, preserving frontmatter. Must handle `verdict`:

- `KEEP` — replace title and body
- `SPLIT` — write the note plus a second note from `split_second_note` (the
  grouping audit found 20% of multi-source groups carry two claims and 8%
  contradict outright; ~1 in 20 rewrites returns SPLIT)
- `ARCHIVE` — move to Archive (the general form would be a truism)

### Step C — remap relationship edges to the new titles

```bash
python3 ~/ora/scripts/engram-migration/fix_notes.py --apply
```

Edges are keyed by **claim sentence** — the target note's H1 — so every retitle
dangles the edges pointing at it. `fix_notes.py` rebuilds the old→new mapping from
`absorbed_from` plus the archived H1s and rewrites the targets. Deterministic, no
model. It already did this once for 604,099 edges across 64,089 notes.

*It may need extending:* it currently maps archived-original H1s to current H1s.
After Step B the mapping is current-H1 → new-H1, which is a different pair. Verify
before trusting it.

### Step D — rebuild the vector store

```bash
python3 ~/ora/orchestrator/tools/chroma_source_rebuild.py --engrams-root ~/engram-work/Engrams
```

Also clears **8,021 orphaned records** that resolve to no file and inflate every
similarity query today.

### Step E — relationships for the 11,644 incorporated notes

```bash
python3 ~/ora/orchestrator/historical/phase_c_relationship_extraction.py \
  --vault-root ~/engram-work/Engrams
```

ChromaDB nearest-neighbours plus a **Haiku** classification per note, resumable via
`~/ora/data/phase-c-manifest.json`. Roughly 24M Haiku tokens. Haiku is the correct
tier here — constrained classification against a fixed vocabulary is where its
literalism is an asset.

### Step F — land it and tear down

```bash
git -C ~/engram-work push origin engram-permanent-notes
# merge into the vault's default branch, then:
git -C ~/Documents/vault worktree remove ~/engram-work
rm -rf ~/engram-backups ~/ora/scripts/engram-migration
```

The owner has decided the 122,118 archived originals **stay in Archive until this
is proven done properly**, then may be deleted. Nothing depends on them after
Step B: provenance lives in each note's own frontmatter, and the source
conversations they point at are 85% gone anyway.

---

## 5. What a note must be — the writing standard

The prompt is `~/ora/scripts/engram-migration/rewrite_prompt.md`, 15 rules, twelve
of them derived from the owner reading real output across seven rounds. None were
derivable in advance. **Do not rewrite this prompt from first principles.**

The two calibration titles, both written by the owner:

> A leader who blames others turns criticism of his policy and actions into proof
> his enemies are real

> People blame themselves for the harms perpetrated by others until they find
> other victims that share their experiences, which protects the perpetrators

The rules that carry the most weight:

- **Find the CONVERSION.** Every accepted title has the shape *something turns
  into something and the result is perverse*. Criticism becomes proof of enemies.
  Private shame becomes protection for the harm-doer. An exemption becomes people
  stranded. When you can state either the mechanism or its perverse result, the
  perverse result is the insight and the mechanism is a bullet. This single rule
  independently re-derived two owner-approved titles verbatim after earlier rules
  had permitted worse alternatives.
- **Generalization has a floor as well as a ceiling.** Replacing a noun with the
  most abstract available word makes the claim ambiguous and often false. Run the
  substitution test both ways: name two other things your noun covers and check
  the claim stays true; also check the noun reaches everything the mechanism
  reaches. "A shared system" failed because a grazing commons is one.
- **Some notes are domain-bound.** Roughly one in nine is craft knowledge — about
  writing fiction, about a physical technique — where the domain IS the subject,
  not costume. Stripping it produces gibberish. Keep the domain and generalize
  within it.
- **Name the parties who act, once each.** Not every abstract noun needs an owner,
  and repeating a role six times in a sentence is worse than the vagueness it
  fixes. Actors may be things — a tool, a rule, a market.
- **Qualifications go in the bullets, never the title.** A title crammed with
  conditions is less general, not more faithful. But the qualification must
  survive somewhere: dropping it is the dominant measured failure.
- **Never introduce a term of art absent from the sources.**
- **No caps on anything.** No word target, no bullet limit. The owner's standing
  instruction is that limits destroy the work; every cap this project introduced
  produced a defect (see §6).

Titles land at 18–22 words when the rules are followed. That is an outcome, not a
target.

---

## 6. Traps — every one of these cost real tokens or real errors

**Every defect this project introduced came from a cap or an omission chosen to
save cost or length.** Four instances:

1. **Excluding source bodies from the writer's input** to save tokens →
   de-fanged 56% of the corpus. The median group's full source text is 512
   characters. It was always affordable.
2. **Capping titles at ~20 words** → the model deleted the actors to hit the
   length, producing "findings no one answers for."
3. **Extracting "specifics" instead of passing text** → fabricated evidence lines
   assembled from keyword debris.
4. **Batching 20 notes per call** → measured 25% quality loss at batch 8 (Opus met
   the bar 16/16 at batch 1, 12/16 at batch 8). Batch 1 is the measured default.

**Verify before believing an alarming rate.** Four detectors over-fired and each
was caught only by noticing the number was implausible:

- A tautology check flagged **100%** because it counted the `# title` heading as
  the first bullet, comparing the title to itself.
- A dropped-clause check flagged **42%** because "rather than" was treated as
  load-bearing; it is ordinary contrastive phrasing a faithful paraphrase rewords.
- A fabrication check produced **31 false HARD failures** by comparing
  case-sensitively — "Cultural Accessibility" read as invented when the source
  said "cultural accessibility." Fix: compare against the source's whole
  vocabulary, not against entities extracted from it.
- An instance-locking check flagged **80%** by conflating domain-bound
  (legitimate) with instance-locked (defective).

**The parser bug that mattered most.** A JSON extractor slicing from the first `{`
to the last `}` discarded 17–45% of *valid* replies — anything with trailing CLI
output or braces inside a string. Diagnosed wrongly three times (transient, then
concurrency, then truncation) before the fix that worked: **write every unparseable
reply to disk instead of theorising.** The moment failures became inspectable the
rate went to zero. `rewrite_run.py` now records them in `.migration/rewrite_failures/`.

**A silent-loss bug in the same function.** When a returned `note_id` did not match
the request, the loop `continue`d, wrote nothing, and **still counted the call a
success**. A run could report 1,000 ok having produced 900 files. Now counted as
`id_mismatch` and printed.

**`pgrep -fc` gives false negatives here.** It reported `0` for four processes that
`ps` clearly showed running, and on that basis four stale shards ran the old buggy
parser for 25 minutes. **Use `ps -eo pid=,args= | grep "[r]ewrite_run.py"`.**

**Prompt caching is unavailable on `--backend claude-cli`.** It shells out to
`claude -p` per call and sets no `cache_control`. The 3,863-token system prompt is
paid in full on every call — **79% of the 4,894 tokens per note.** Halving it is
the largest remaining cost lever (~7.8M of 19.8M). The safest cut is
defect-targeted prompts: each flagged note carries a known defect class from the
prescan, so send the core title/conversion rules plus only the section addressing
that defect. Do not blanket-compress; the rules were expensively calibrated.

**Concurrency is fine** — 20/20 at 4 workers once the parser was fixed, 4.3×
faster. The earlier 45% failure was the parser, not contention.

**Never work in `~/Documents/vault` directly.** It auto-commits every ~30 s and
rsyncs to a remote with `--delete`. A bulk edit there would be chopped into
arbitrary commits and propagated. `~/engram-work` is outside the rsync scope.

**macOS TCC blocks `~/Documents` unless Claude.app has Full Disk Access.** Without
it, git in the vault and the worktree is unreachable and there is no usable undo.
Grant it to `/Applications/Claude.app` (not the nested binary) and restart the app.

---

## 7. Tools

All in `~/ora/scripts/engram-migration/`. Delete the directory when this lands;
nothing in the running system imports from it.

| tool | what it does | model |
|---|---|---|
| `prescan.py` | finds which notes need work by mechanical signature | **none** |
| `prescan.py --historical` | pre-migration defect scan (over-fires; see §6) | none |
| `fix_notes.py` | deletes keyword-dump Instance lines, remaps relationship edges | **none** |
| `incorporate_historical.py` | folds Historical Atomics in, archives non-corpus kinds | none |
| `rewrite_run.py` | rewrites flagged notes from full sources | Opus |
| `rewrite_prompt.md` | the writing standard, 15 calibrated rules | — |
| `daemonize.py` | double-fork detach (macOS has no `setsid`) | — |
| `compare_arms.py` | scores rewrite variants against the bar | — |

**Measured model assignment.** Opus for writing (Stage 5, 9): on 300 identical
notes Haiku paraphrased where asked to transform and invented canonical-sounding
terms — "Bad faith reasoning" where the real term is *techniques of
neutralization*. Haiku for triage and constrained classification (Stage 3, `phase_c`):
63.6% source retention against Opus's 54.2%, half the fabrication rate. A local
Qwen3.5-122B was tested and rejected for writing: format and speed were fine
(2.9 s/unit) but it paraphrased inside the source domain and named no concepts.

Two local-model configuration traps, if local is ever tried again: the Qwen chat
template defaults `enable_thinking` **on** (26,756 characters of chain-of-thought
before any output), and no local endpoint declares `max_tokens` so
`boot.call_local_endpoint` falls back to `999_999_999`.

---

## 8. What is still unresolved

1. **Step B does not exist.** The rewrites are accumulating as JSON with nothing to
   apply them.
2. **`fix_notes.py` may need extending for Step C** — its mapping is
   archived-H1 → current-H1, but after Step B it needs current-H1 → new-H1.
3. **The 11,644 incorporated notes have no relationships** until Step E.
4. **~51,600 notes were never flagged and never rewritten.** The prescan finds
   defects with mechanical signatures; a note that is merely bland, or generalized
   one notch too far, passes clean. Those exist and are not findable mechanically.
   Re-running clean notes is measurably harmful — two owner-approved titles came
   back *worse* when re-processed under new rules — so leaving them is the correct
   default, not laziness.
5. **The tier/batch matrix was run but never judged.** Titles for nine
   model/batch conditions are in `.migration/MEASUREMENTS.json`; two of three
   judges failed on a file-path bug. Sonnet at batch 1 is untested and could cut
   cost several-fold if it meets the bar.

---

## 9. How to work with this corpus's owner

- **Show real artifacts, not summaries.** Every genuine advance in this project
  came from the owner reading actual notes and correcting them. Rates and
  percentages produced almost nothing by comparison.
- **Never propose a limit, cap, or word target.** Standing instruction, and every
  violation produced a defect.
- **State corrections plainly and move on.** No hedging about whether a number
  might be wrong — check it, then say what it is.
- **Do not add gates, kill switches, or default-off flags to content pipelines.**
  Fail open with loud logging.
- **Deliver, don't audit indefinitely.** The owner tired of audits before the work
  was done, correctly. Audit when a decision genuinely turns on the answer.
