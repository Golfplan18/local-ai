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
| missing relationships | **11,644** — 11,572 incorporated Historical Atomics plus 72 other notes |
| `Archive/Engram Absorbed Sources 2026-08/` | 122,118 pre-merge originals |
| `Archive/Historical Atomics Not Incorporated 2026-08/` | 2,477 (facts, perishable, dated, 3 predictions) |
| Rewrite artifacts | **3,148 of 4,038** present; 3,145 strict-valid, 3 invalid |

**No model process is running.** The prior Opus run stopped after 139 minutes.
Three saved malformed wrappers contain recoverable note objects; 890 output files
are absent, so 893 worklist entries do not yet have a strict-valid output. No
rewrite has been applied to a note.

Check before starting any model work:

```bash
tail -5 ~/engram-work/.migration/rewrite-run.log
ps -eo pid=,etime=,args= | grep "[r]ewrite_run.py"     # NOT pgrep — see §6
```

`rewrite_run.py` now validates existing files before treating them as complete,
validates new records before persisting them, and refuses Opus. The next action is
a representative GPT-5.6 Sol pilot in an isolated output directory, not the full
remaining worklist.

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

## 4. Remaining steps — REVISED after review

**An independent review found the previous version of this section unsafe to
execute. Do not use commands from any earlier copy.** The blocking findings are in
§4a; the corrected order is §4b. No bulk model run or corpus apply is ready yet.

### 4a. Blocking findings (all verified against the code)

**E1 — Phase C would destroy the existing graph.** Without `--paths-file` it globs
every `*.md` under the root (all 75,734) and `write_note_with_relationships` does
`new_fm["relationships"] = relationships if relationships else []` — it REPLACES,
and empties the field when the model finds nothing. The manifest is absent, so
nothing is marked done and resume would not protect anything. Running the naive
command would replace 64,090 working relationship sets and 604,099 edges.
*Never invoke Phase C without an explicit `--paths-file` naming only notes that
lack relationships.*

**E2 — Phase C marks errors and skips as completed.** `completed[p] = entry` runs
regardless of `r.error` or `r.skipped`, so resume never retries a failure. This is
the same trap §6 documents elsewhere. It also caps neighbour bodies at 600
characters (`NEIGHBOR_MAX_CHARS`), affecting 17,671 notes, and does not retain
malformed replies.

**E3 — the vector-store step is wrong twice.** `chroma_source_rebuild.py` requires
a subcommand and `--target-chromadb-path`, and it must be run with `cwd=~/ora` or
the `orchestrator` import fails. Even corrected it rebuilds `knowledge`, while
Phase C queries `atomics`. The live atomics index is profoundly stale: only 6,689
of its 129,900 distinct titles overlap the corpus's 75,675 current H1s, so using it
would generate obsolete and dangling targets at scale.

**E4 — the vector-store ORDER is backwards.** Knowledge metadata stores
relationships and absolute note paths. Building before Phase C omits the new
relationships; building from `~/engram-work` bakes in paths inside a worktree that
Step F deletes. Final indexes must be built AFTER landing, from the canonical
`~/Documents/vault/Engrams`.

**E5 — SPLIT has no graph semantics.** `split_second_note` carries only a title and
body, while `source_files` remains one undivided list. Undefined: which child
inherits the old title's inbound edges, how provenance divides, the second
filename and frontmatter, collision handling, and what happens to inbound edges on
ARCHIVE. At inspection there were 44 SPLITs and 43 affected notes carried 1,949
inbound edges. **This is a decision to be made, not code to be written.**

**E6 — `fix_notes.py` is not a title substitution.** It reconstructs the whole
graph from the archived originals. Its `remap` dict silently overwrites duplicates:
**29 archived H1s map to two different merged notes**, and 801 archived edges
reference those ambiguous titles. SPLIT worsens the ambiguity. Verified: 110,908
remap keys, 29 ambiguous.

**E7 — Step A had no completion gate.** This is now repaired in the runner: an
existing file counts only when ID, verdict, title, bullet-only body, source list,
and SPLIT shape validate; new replies are checked before atomic persistence; a
failed run exits nonzero. The current scan finds 3,145 valid and exactly three
invalid files (two array-valued bodies and one body containing commentary). The
full 4,038-entry bijection is still required before applying anything.

**E8 — Step F does not land the work.** `git push` cannot push uncommitted B/C/E
changes; feature and main have diverged; untracked `.migration/` blocks ordinary
worktree removal. Final commit, feature push, merge, main push and remote readback
are all missing. And `rm -rf scripts/engram-migration` would delete tracked files
without committing the teardown.

### 4b. Corrected order

1. **Prove the non-Opus writing route, then finish Step A.** Run a representative
   GPT-5.6 Sol pilot in an isolated output directory and compare real notes against
   their full sources and the accepted writing standard. If it meets the bar,
   recover the six structurally damaged-but-complete artifacts where lossless,
   finish the remaining work, and require an exact 4,038-file valid bijection.
2. **Decide SPLIT/ARCHIVE semantics** — edge inheritance, provenance division,
   filenames, collisions. Write the decision down before coding it.
3. **Apply the complete batch atomically**, with a collision-free preflight and a
   commit as the rollback point.
4. **Remap the accepted graph without blindly rerunning `fix_notes.py`.** Preserve
   the accepted relationship graph for ordinary retitles, resolve SPLIT/ARCHIVE
   edges under the decision from step 2, and separately resolve the 58 current
   duplicate H1 values and the one zero-byte note. The 29 archived-H1 collisions
   matter only if archived graph reconstruction remains necessary.
5. **Repair Phase C and build a TEMPORARY current atomics index.** Expose the
   temporary Chroma path to its CLI; remove the 600-character neighbour cap; save
   malformed replies; retry errors/skips; and exit nonzero while any remain.
6. **Derive the exact post-apply set lacking relationships** and pass only those
   via `--paths-file`. Afterwards, prove every pre-existing relationship block is
   byte-identical, not merely that aggregate edge counts match.
7. **Land and merge the corpus** — commit, push feature, merge, push main, read
   back the remote.
8. **Rebuild final atomics and knowledge indexes from `~/Documents/vault/Engrams`**
   after landing, validate inactive copies, then cut over with a retained rollback.
9. **Verify** remote state, graph resolution, stored paths, live queries, and
   rollback. Only then delete archives and scaffolding — as a committed change.

### 4c. Step A, current safe boundary

The runner accepts only `--backend codex-cli --model gpt-5.6-sol`; every other
backend and model is rejected by argument parsing. It requires Codex CLI 0.147.0
or newer and refuses to run without an explicit worklist. The isolated ChatGPT
route passed a real schema-constrained smoke call. It writes one JSON per note and
touches no vault note. First run the representative pilot into a separate staging
directory; do not point it at `.migration/rewrite/` until the real pilot artifacts
meet the writing bar.

Check it with `ps`, never `pgrep` (§6):

```bash
tail -5 ~/engram-work/.migration/rewrite-run.log
ps -eo pid=,etime=,args= | grep "[r]ewrite_run.py"
```

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

All in `~/ora/scripts/engram-migration/`. Delete the directory when this lands;
nothing in the running system imports from it.

| tool | what it does | model |
|---|---|---|
| `prescan.py` | finds which notes need work by mechanical signature | **none** |
| `prescan.py --historical` | pre-migration defect scan (over-fires; see §6) | none |
| `fix_notes.py` | deletes keyword-dump Instance lines, remaps relationship edges | **none** |
| `incorporate_historical.py` | folds Historical Atomics in, archives non-corpus kinds | none |
| `rewrite_run.py` | rewrites flagged notes from full sources | prior: Opus; next: GPT-5.6 Sol after pilot |
| `rewrite_prompt.md` | the writing standard, 15 calibrated rules | — |
| `daemonize.py` | double-fork detach (macOS has no `setsid`) | — |
| `compare_arms.py` | scores rewrite variants against the bar | — |

**Historical measured model assignment.** Opus produced the existing 3,148 files;
it is no longer authorized. On 300 identical notes,
Haiku paraphrased where asked to transform and invented canonical-sounding
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
5. **GPT-5.6 Sol has not yet been measured against this writing bar.** Run the
   isolated representative pilot before spending the remaining worklist through it.
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
