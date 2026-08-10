# Engram Permanent-Note Migration — Handoff

Written 2026-08-09. Everything needed to finish this without the session that
started it. Read `README.md` alongside this for the calibrated constants and the
measured facts; this file covers **state, intent, and what to run next**.

---

## 1. The problem, in one paragraph

`Engrams/` held 122,131 auto-extracted notes. The extractor processed one
conversation-pair at a time with no knowledge of the corpus, so a principle
revisited across thirty conversations minted thirty notes. The count measured
*mentions*, not concepts. Worse, the extraction prompt instructed the model to
"name what does what" in every bullet, which pinned each note to the individual
who happened to act in that conversation — "Honnold eliminates execution
uncertainty by memorizing every hold" instead of "pre-memorization converts
problem-solving under stress into rehearsed performance". Measured on a 45-note
random sample, **~60% of notes could not be applied outside their source
domain**. The transferable principle was usually present but welded to its
instance.

The goal is one **permanent note** per concept: a general claim as the title, the
mechanism in domain-neutral role language, and the specific case retained beneath
it as `Instance:` evidence.

---

## 2. What is already permanent and safe

**Both producers are fixed.** This was the root cause and it is closed; new
conversations no longer add to the pile.

| Commit | What |
|---|---|
| `3d4ab7d1` | `orchestrator/historical/phase5_atomic_extraction.py` — batch extractor |
| `bd4f2b31` | `orchestrator/tools/extraction_engine.py` — live path (`runtime_pipeline` → staging → `engram_promotion`) |

Four changes in each: replaced the named-actors rule with domain-neutral roles
plus a trailing `Instance:` bullet; added an explicit transfer test that permits
minting nothing; added title prohibitions plus a requirement that the canonical
concept name appear verbatim; stopped minting bare facts.

**The live path was the easy thing to miss** — it has a separate prompt from the
batch extractor, and `"actor-verb-target"` appeared in the `required_elements` of
all six of its subtype schemas.

---

## 3. Exact state

Working tree: **`~/engram-work`**, branch `engram-permanent-notes`, based on
vault commit `c8e5c3782f12b9f063be4d103555ef2d922f8416` (the undo point).
The live vault at `~/Documents/vault` is **untouched**.

| Stage | State |
|---|---|
| 2 — cluster | **done.** 122,118 notes → 72,737 units (25,319 clusters + 46,559 singletons) |
| 3 — triage + specifics (Haiku) | **done.** 72,539 units. 88.2% KEEP, 7.4% ARCHIVE, 4.5% RESOURCES |
| 5 — write permanent notes (Opus) | **320 of 63,734 units (0.5%)** — `stage5/` |
| 6 — checker | built, tested, run on the pilot |
| 7 — apply to vault | built, sandbox-tested, **never run** |
| 8 / 8b / 9 | built, tested on pilot output |
| 10 / 11 | reuse existing tools, not started |

Artifacts live in `~/engram-work/.migration/`:
`shards/` (Stage 3 input) · `stage3/` · `stage5_shards/` (Stage 5 input) ·
`stage5/` · `cache/` (2.1 GB embedding matrix) · `repair.json` ·
`stage8_groups.json`

---

## 4. Run this next

```bash
cd ~/ora
# 1. Stage 5 — the bulk. Unattended, resumable, ~3,171 batches.
python3 scripts/engram-migration/stage5_run.py --backend claude-cli --workers 8

# 2. Conformance check over 100% of output. Must show zero HARD violations.
python3 scripts/engram-migration/stage6_check.py

# 3. Apply to the vault — dry run first, always.
python3 scripts/engram-migration/stage7_apply.py
python3 scripts/engram-migration/stage7_apply.py --apply

# 4. Cross-domain merge candidates, then audit the concept field
python3 scripts/engram-migration/stage8_lexical.py
python3 scripts/engram-migration/stage8b_concept_audit.py

# 5. Stage 9 — decide each candidate group (see stage9_prompt.md)

# 6. Rebuild relationships and the vector store with EXISTING tools
python3 orchestrator/historical/phase_c_relationship_extraction.py \
    --vault-root ~/engram-work/Engrams
python3 orchestrator/tools/chroma_source_rebuild.py \
    --engrams-root ~/engram-work/Engrams
```

`stage5_run.py` re-derives its worklist from what is absent on disk, so
re-invoking the same command retries failures and continues. There is no resume
flag.

---

## 5. Token burn — read this before running anything

The agent pilot measured **4,475 tokens per unit**, which I extrapolated to 283M
for the corpus. **That was wrong by ~10x.** Two compounding errors:

1. **Sampling.** Units are ordered largest-first so a pilot exercises the hard
   facet-absorption cases. Units with 8+ members are **2.7%** of the corpus. The
   mean unit carries **58 tokens** of title text. Never extrapolate cost from the
   head of that ordering.

2. **Conversational accumulation.** An agent writing 40 notes in one context
   re-sends its own prior output every turn, so cost grows quadratically in the
   batch. A stateless call pays input + output once.

| Approach | tokens/unit | corpus total |
|---|---|---|
| Agent, one note per turn (pilot) | 4,475 | 283M |
| Script, batch 20, stateless | 574 | 36.6M |
| Script, batch 20 + system-prompt caching | **462** | **29.4M** |

`--batch` is the main cost lever. 20 is a reasonable default; raising it lowers
per-unit cost but increases the blast radius of one malformed response.

---

## 6. Model assignment is measured, not preference

An A/B on **300 identical notes** with an identical prompt:

- **Haiku paraphrases where it is asked to transform.** Given *"Exposure holds up
  a mirror to recognizable selfish choices"*, Haiku returned a reshuffle of the
  same words; Opus produced *"The critic who names particular selfish choices
  lets the audience check the charge against the conduct"* — naming the role,
  exposing the mechanism. Nominalization density 11.0% vs 7.6%.
- **Haiku invents canonical-sounding terms.** It claimed a concept name on 100%
  of notes against Opus's 66%, offering *"Bad faith reasoning"* where the real
  term is *techniques of neutralization*, and *"Confirmation bias"* on a note
  actually about social engineering. A plausible fake term is worse than none: it
  pollutes the vocabulary and misdirects every later search.
- **Haiku is better at extraction** — 63.6% source retention vs 54.2%, half the
  fabrication rate. Its literalism is an asset for triage and specifics.

**Local models were tested for Stage 5 and rejected.** Do not repeat this
experiment; the findings are unambiguous.

Qwen3.5-122B-A10B (mxfp4, 61 GB) with `enable_thinking=False`, lean prompt:
2.9 s/unit (~2.1 days for the corpus), 20/20 JSON parse, 20/20 Instance lines.
Format and speed are fine. It fails on the only thing that matters:

- **It paraphrases instead of raising the level.** Local title: *"Narrative
  themes emerge through character choices that embody universal dilemmas rather
  than exposition"* — still a fiction-craft claim. Opus on a sibling unit: *"The
  choice architecture of an environment, not its description, determines what
  the people inside it do"* — transfers to workplace design, urban planning,
  product design. That gap IS the migration.
- **Body bullets copy member titles verbatim.** Enumeration, not consolidation.
- **It names no concepts** under the lean prompt (0 of 20), and invents
  canonical-sounding ones under the long prompt ("Choice Causality Design").

Two configuration traps found while testing, which apply to ANY local use:

1. `boot.call_local_endpoint` passes no `enable_thinking`, and the Qwen chat
   template defaults it on. The model emitted 26,756 characters of "Thinking
   Process:" and never reached the JSON. Pass
   `apply_chat_template(..., enable_thinking=False)`.
2. No local endpoint in `routing-config.json` declares `max_tokens`, and
   `boot.call_local_endpoint` defaults to `999_999_999`. MLX treats that as a
   hard stop, so generation ends only on a spontaneous EOS. One unit ran 20+
   minutes. Set it explicitly.

Local IS suitable for Stage 10 edge typing (constrained classification from a
13-term vocabulary) and for re-running Stage 3 shards (triage + verbatim
extraction, where literalism is an asset).

So: **Haiku sorts and extracts (Stage 3, 10); Opus writes (Stage 5, 9).** Do not
move Stage 5 to a cheaper tier to save tokens — Stage 5 is the only irreplaceable
judgement in the pipeline, and the ~30M figure already makes it affordable.

---

## 7. The gate — do not bypass

`stage6_check.py` classes three violations **HARD**, and `stage7_apply.py`
refuses to run while any exists (`--allow-hard` overrides; do not use it
casually):

- **R2** — the `Instance:` line contains a specific absent from the source. The
  only unrecoverable defect: an invented record cannot be distinguished from a
  real one, and the member notes are deleted once the merged note is written.
- **R5** — no `Instance:` line, or zero mechanism bullets (a note carrying only an
  Instance line has no claim in it).

Measured on the pilot after the checker was corrected: **0.6% HARD**, 17.5% title
violations, 9.4% concept-absent, 47.5% fully clean.

**The checker had three bugs of its own, all of which inflated failure rates.**
If a rate looks alarming, inspect real examples before believing it:

- Counting the first word of every title as a proper noun → a phantom 92%
  content-loss rate.
- Case-sensitive comparison → *"Cultural Accessibility"* read as invented when
  the source said *"cultural accessibility"*: **31 false HARD failures** that
  would have blocked Stage 7.
- The structural fix: compare candidate entities against the source's **whole
  vocabulary**, not against entities extracted from it. A source writing
  "chapter 4" in lowercase contributes nothing to a proper-noun comparison set.

---

## 8. Traps that already cost real tokens

- **Never pass a worklist through Workflow `args`.** A run lost its args
  silently, fell back to defaults, and reprocessed shards 0-39 for ~4.5M tokens.
  Hardcode or derive from disk.
- **Trust the filesystem, not agent self-reports.** Agent summary counts
  disagreed with disk twice, once claiming 1,476 units processed when the real
  figure was 1,013. Count from the result files.
- **Never work in the live vault.** It auto-commits to git every ~8 minutes and
  rsyncs to `cloud-ora` with `--delete`. A bulk edit in place would be chopped
  into arbitrary commits and propagated to the server. `~/engram-work` is outside
  the rsync scope.
- **Leader clustering, never connected components.** At 0.75 similarity,
  connected components chains 42,677 notes into one blob.
- **`seen_count` never worked** — 100% of vault notes read `1`; in ChromaDB only
  0.16% exceed 1, max 2. It is not a usefulness signal. Cluster size is.

---

## 9. Open questions

1. **The A/B on member bodies is unfinished** (6 of 8 shards). Stage 5 currently
   receives member **titles** only, on the argument that titles carry the claims
   while bodies were written under the broken named-actors rule and may anchor the
   writer toward the instance. That is a hypothesis; `stage5_build.py
   --with-bodies` builds the other arm. Output for the finished arm is in
   `.migration/stage5_bodies/`. Compare on facet absorption and concept-naming
   rate before committing the full run.
2. **~22% of units carry no specifics at all**, so those notes will read
   `Instance: none recorded in source.` — faithful to the source, but a fifth of
   the corpus will be pure abstraction with no evidence layer and no keyword
   surface beyond its title. Acceptable or not is a publisher's call.
3. **Stage 9 has no runner yet**, only a prompt. It needs the same treatment
   `stage5_run.py` got if the candidate-group count is large.
4. **8,021 ChromaDB records resolve to no file on disk.** They inflate every
   similarity query today; the Stage 11 rebuild clears them.

---

## 10. Teardown

When Stage 11 completes and the branch merges:

```bash
rm -rf ~/ora/scripts/engram-migration
rm -rf ~/engram-work/.migration          # holds a 2.1 GB embedding matrix
git -C ~/Documents/vault worktree remove ~/engram-work
```

Nothing in the running system imports anything under
`scripts/engram-migration/`. The two extractor fixes are the only permanent code
changes, and they live in the orchestrator proper.
