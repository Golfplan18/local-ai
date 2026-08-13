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

## 2. Current state (2026-08-13)

Working tree **`~/engram-work`**, branch `engram-permanent-notes`, a git worktree of
`~/Documents/vault`. **The live vault is untouched.** Rollback points: `516100a1d`
(before the rewrites landed), `c637f57995` (after).

| | |
|---|---|
| `Engrams/` — the single corpus | **75,834 notes**, flat, no subdirectories |
| with working relationships | 64,090 · **604,099 edges, 100% resolving, zero dangling** |
| missing relationships | **11,744** (the incorporated Historical Atomics notes) |
| `Archive/Engram Absorbed Sources 2026-08/` | 122,118 pre-merge originals |
| `Archive/Historical Atomics Not Incorporated 2026-08/` | 2,477 |
| Disk | 1.0 GB (was 3.5) |

### THE NUMBER THAT MATTERS MOST

Only **5.3%** of the corpus has been rewritten from good input:

| where each note's current text comes from | notes | |
|---|---|---|
| Rewritten from full source text | 4,026 | **5.3%** |
| Incorporated from Historical Atomics, never revised | 11,572 | 15.3% |
| **Merged text from the defective pass, never revised** | **60,236** | **79.4%** |

The 48-note audit sampled *random* merged notes and found **52% needed a fix**. The
prescan flagged only 19%, so it found roughly a third of what needs work — its
signatures catch fabrication and dropped concessive clauses, and cannot detect "true
but says nothing." **Do not read the completed 4,038 as meaning the corpus is fixed.**

### Done

* Both extractors fixed (`3d4ab7d1`, `bd4f2b31`) — new conversations mint proper notes.
* Migration (Codex): 122,118 originals → 64,144 merged notes; originals archived.
* 8,744 keyword-dump `Instance:` lines deleted; **55,400 grounded ones kept**.
* 604,099 relationship edges restored from the archived originals' frontmatter.
* Historical Atomics folded in (11,572), non-corpus kinds archived (2,474 + 3 predictions).
* 4,038 flagged notes rewritten from full sources; **validation gate passes 4,038/4,038**.
* Rewrites applied; 56,397 edge targets remapped; 100 SPLIT children created.
* MiniMax M3 wired as a backend and **tested on both classification and rewriting**.

### In flight

Temporary atomics index building at `.migration/chroma-temp` from the worktree
(75,834 embeddings, ~$1, ~19/s). Needed because the live atomics index overlaps the
current corpus on only 6,689 of its 129,900 titles.

A blind 3-judge comparison of Opus vs M3 (thinking on/off) on 12 full rewrites was
launched and **its result is not in this document** — check
`.migration/` and the session transcript, or re-run it.

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

## 4. Remaining steps

Steps A (rewrite the flagged notes), its validation gate, and the apply-plus-remap
are **complete**. What follows is what is left.

### The MiniMax finding, which changes the cost of everything below

M3 was tested on the full rewrite task against the 4,038 Opus rewrites as reference,
12 notes, 2 to 12 sources each:

| | parsed | speed | out-tokens | title | **qualifying clauses kept** | false terms |
|---|---|---|---|---|---|---|
| Opus | 12/12 | — | — | 22.6w | **14/24 — 58%** | 0 |
| M3 thinking-ON | 12/12 | 67s | 6,492 | 21.6w | **18/24 — 75%** | 0 |
| M3 thinking-OFF | 12/12 | 5s | 286 | 18.5w | **15/24 — 62%** | 0 |

**M3 preserves the load-bearing qualifying clauses BETTER than Opus** — the exact
failure that de-fanged 56% of the corpus. Neither variant imported a false term of
art. Small sample (24 clauses), so treat the ordering as indicative and the
"not worse than Opus" conclusion as solid.

**RESOLVED by blind judging** — 12 notes, 3 judges, letters shuffled per note:

| condition | met the bar | conversion found | judged best |
|---|---|---|---|
| Opus | 11 | **19** | 16 |
| **M3 thinking-ON** | **17** | 17 | 16 |
| M3 thinking-off | 8 | 16 | 4 |

**M3 with thinking beat Opus on meeting the bar (17 vs 11) and tied on best.** Use
M3 with thinking ON for rewriting. Thinking-off is NOT viable despite being 13x
faster with an 18.5-word average — judges put it best on 4 of 36. Opus found
conversions most often but met the full bar least, because its titles ran long and
clause-stacked ("spends 27 words restating its own first bullet almost verbatim").

### The conversion rule does not apply to every note

**15 of 36 judgements found NO variant met the bar; 12 of 36 found no variant
contained a conversion at all** — because the sources have none. Judges, verbatim:
"Nothing in this note converts — every title states a static blind spot"; "No title
inverts anything — all three merely report that a capacity practised in one
relationship is withheld in another."

Some notes are plainly descriptive. Forcing a perverse conversion onto them would be
fabrication, and "meets the bar" is the wrong metric for roughly a third of the
corpus. `rewrite_prompt.md` §"Find the CONVERSION" should be softened to say: state
the conversion where the sources contain one, and where they do not, state the claim
plainly rather than manufacturing an inversion. That edit has NOT been made.

Two configuration facts, both measured:

* **Rewriting needs `max_tokens` ≈ 32768.** M3's `<think>` block ran 13,760
  characters and consumed all 8,192 tokens on the first attempt, finishing inside
  the reasoning with no answer. The client floor is now 32768.
* **Thinking is load-bearing for CLASSIFICATION but maybe not for REWRITING.** With
  thinking disabled, Phase C linked a golf-swing note to political blame as
  `analogous-to`; a deliberate distractor. For rewriting, thinking-off was 13x
  faster with comparable output. Do not carry one finding to the other task.

### Order matters — rewrite before generating relationships

Rewriting **5.3%** of notes put a changed claim on at least one end of **16.3%** of
edges (98,187 of 604,099). Rewriting 40% would touch most of the graph.

The remap is deterministic and free, and it repairs the *pointers* perfectly (proven:
100% resolution). It cannot verify that "A supports B" is still TRUE once B's claim
has been rewritten. Nothing detects a now-false edge.

And the 604,099 restored edges were extracted by a model reading the
**pre-migration instance-locked notes**. They already describe relationships between
claims that no longer exist in that form.

**So: if the remaining ~60,000 are to be rewritten, rewrite them FIRST and generate
the graph ONCE at the end.** On MiniMax that final pass is near-free, which is what
makes the sequence affordable. Do not generate relationships for a note you intend
to rewrite.

### 4a. Finish the relationship pass for the 11,744 (safe now)

These notes are NOT scheduled for rewriting, so their relationships will not need
redoing.

```bash
cd ~/ora && PYTHONPATH=~/ora python3 orchestrator/historical/phase_c_relationship_extraction.py \
  --vault-root ~/engram-work/Engrams \
  --paths-file ~/engram-work/.migration/phase_c_paths.txt \
  --chromadb-path ~/engram-work/.migration/chroma-temp \
  --backend minimax --max-workers 8
```

**`--paths-file` is mandatory.** Without it Phase C globs all 75,834 notes and
`write_note_with_relationships` REPLACES the field, emptying it where the model finds
nothing — destroying 604,099 working edges. The paths file holds exactly the 11,744
that lack relationships.

Afterwards, prove the others were untouched. Baseline recorded before the run:

```
64,090 relationship-bearing notes · 604,099 edges · fingerprint aaf814bc9f640db3
```
(`.migration/phase_c_baseline.txt`; the fingerprint is sha256 over `name:edgecount`
for every relationship-bearing note, sorted.)

### 4b. The open decision: rewrite the remaining ~60,236

On the audit's 52% rate roughly 30,000 need work, and the prescan cannot find them
(it caught a third). Options:

1. **Rewrite all 60,236 on M3.** Effectively free, overnight at 5s/note single-stream
   and far less in parallel. Takes the corpus from 5.3% properly rewritten to ~100%.
2. **Sample-audit 40 unrevised notes first** against their archived sources to confirm
   the 52% rate still holds, then decide.
3. **Leave them.** Nothing is junk — zero rejects in 48 audited — they are blunted,
   not wrong.

Option 1 is only defensible once the blind judging confirms M3 clears the bar.

### 4c. Then land it

```bash
git -C ~/engram-work add -A Engrams Archive && git -C ~/engram-work commit
git -C ~/engram-work push origin engram-permanent-notes
# merge into the vault's default branch, push main, read back the remote
```

`.migration/` is untracked and will block an ordinary `git worktree remove`; delete
it (or `--force`) as a deliberate step. Removing `scripts/engram-migration/` deletes
tracked files — commit that teardown, do not just `rm -rf`.

### 4d. Only after landing: final indexes from the canonical path

```bash
mkdir -p /tmp/atomics-final && PYTHONPATH=~/ora python3 \
  orchestrator/historical/rebuild_atomic_dedup.py --chromadb-path /tmp/atomics-final \
  --vault-root ~/Documents/vault/Engrams --expected-source-count <N>
```

Knowledge metadata stores absolute note paths. Building from `~/engram-work` bakes in
paths inside a worktree that gets deleted. `chroma_source_rebuild.py knowledge` needs
its subcommand and `--target-chromadb-path`, and must run with cwd `~/ora`.

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
reply to disk instead of theorising.** Inspection exposed a second malformed
wrapper shape: a complete inner note followed by object fields stranded inside
the surrounding array. The current parser recovers the three retained examples,
but the stopped process used the older parser and logged four failures. Strict
record validation now prevents a recovered fragment from becoming “complete”
unless every note-building field is valid.

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

All in `~/ora/scripts/engram-migration/`. Delete the directory when this lands —
nothing in the running system imports from it, but do it as a committed change.

| tool | what it does | model |
|---|---|---|
| `prescan.py` | finds notes needing work by mechanical signature | **none** |
| `prescan.py --historical` | pre-migration defect scan — OVER-FIRES, see §6 | none |
| `fix_notes.py` | deletes keyword-dump Instance lines, restores edges from the archive | **none** |
| `incorporate_historical.py` | folds Historical Atomics in, archives non-corpus kinds | none |
| `rewrite_run.py` | rewrites flagged notes from full sources; `--worklist`, `--shard k/N`, `--backend` | Opus / M3 |
| `validate_rewrites.py` | completion gate: bijection + per-record schema | **none** |
| `apply_rewrites.py` | writes rewrites into notes AND remaps the graph, one pass | **none** |
| `rewrite_prompt.md` | the writing standard, 15 calibrated rules | — |
| `daemonize.py` | double-fork detach (macOS has no `setsid`) | — |

**Measured model assignment.** Haiku for triage and constrained classification (63.6%
source retention against Opus's 54.2%, half the fabrication rate). Opus WAS the only
tier trusted for writing until M3 was tested — see §4, where M3 preserved qualifying
clauses better than Opus. A local Qwen3.5-122B was tested and rejected for writing:
format and speed fine, but it paraphrased inside the source domain and named no
concepts.

Local-model traps if that is ever revisited: the Qwen chat template defaults
`enable_thinking` ON (26,756 characters of chain-of-thought before any output), and no
local endpoint declares `max_tokens`, so `boot.call_local_endpoint` falls back to
`999_999_999`.

**Credentials.** MiniMax key is in the macOS keyring, `service='ora'`,
`username='minimax-api-key'` — never in a file. OpenRouter key likewise
(`openrouter-api-key`); the embedder uses it.

## 8. What is still unresolved

1. **The apply step does not exist.** Rewrites are accumulating as JSON with
   nothing to write them into the notes. See E5 — it cannot be written until the
   SPLIT/ARCHIVE graph semantics are decided.
2. **`fix_notes.py` cannot be reused as-is** for the post-apply remap. See E6: it
   rebuilds the graph from archived originals and its remap silently drops one of
   each ambiguous pair (29 of them).
3. **11,644 notes have no relationships** — 11,572 incorporated Historical
   Atomics and 72 others. The tool that would supply them will destroy the other
   64,090 unless driven by an explicit `--paths-file`. See E1.
4. **The atomics index Phase C queries is stale** — 6,689 of 129,900 titles
   overlap the current corpus. It must be rebuilt before Phase C runs, and
   rebuilt again from the canonical vault path after landing. See E3, E4.
5. **GPT-5.6 Sol has not yet met this writing bar.** Two isolated pilots failed
   the content bar despite perfect structure: 6/13 and 9/13 groups needed
   substantive correction. The prompt now states those measured SPLIT, coverage,
   actor, domain, comparison, and title-entailment defects; rerun the identical
   pilot once more before spending the remaining worklist through Sol.
6. **~51,600 notes were never flagged and never rewritten.** The prescan finds
   defects with mechanical signatures; a note that is merely bland, or generalized
   one notch too far, passes clean. Those exist and are not findable mechanically.
   Re-running clean notes is measurably harmful — two owner-approved titles came
   back *worse* when re-processed under new rules — so leaving them is the correct
   default, not laziness.
7. **The tier/batch matrix was not fully judged.** `MEASUREMENTS.json` contains
   four title arms and two judge-result arrays. Sonnet at batch 1 remains untested,
   but it is not the current route.

---

## 9. How to work with this corpus's owner

- **Show real artifacts, not summaries.** Every genuine advance in this project
  came from the owner reading actual notes and correcting them. Rates and
  percentages produced almost nothing by comparison.
- **Never propose a limit, cap, or word target.** Standing instruction, and every
  violation produced a defect.
- **State corrections plainly and move on.** No hedging about whether a number
  might be wrong — check it, then say what it is.
- **Do not add discretionary gates, kill switches, or default-off flags to content
  pipelines.** Fail open with loud logging. Structural validation that prevents a
  malformed or missing artifact from being marked complete is required.
- **Deliver, don't audit indefinitely.** The owner tired of audits before the work
  was done, correctly. Audit when a decision genuinely turns on the answer.
