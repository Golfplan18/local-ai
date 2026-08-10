Take over an in-progress migration of my Obsidian vault's `Engrams/` folder. The
analysis and tooling are done; the bulk writing stage is not. Everything is
committed and resumable.

**Read `~/ora/scripts/engram-migration/HANDOFF.md` first, completely, before
running anything.** It carries the state, the calibrated constants, the measured
model-assignment rationale, and a list of traps that have already cost real
tokens. Then read `README.md` in the same directory.

## What this is

122,131 auto-extracted "atomic notes" that record *mentions*, not concepts — one
principle revisited across thirty conversations minted thirty notes. They are
also welded to their instances, because the old extraction prompt demanded every
bullet "name what does what": I got *"Honnold eliminates execution uncertainty by
memorizing every hold"* instead of *"pre-memorization converts problem-solving
under stress into rehearsed performance"*. On a 45-note random sample, ~60% could
not be applied outside their source domain.

The goal is one **permanent note** per concept: a general claim as the title, the
mechanism stated in domain-neutral role language, and the specific case kept
beneath it as `Instance:` evidence.

## Where it stands

- Working tree `~/engram-work`, branch `engram-permanent-notes`, based on vault
  commit `c8e5c3782f`. **The live vault at `~/Documents/vault` is untouched and
  must stay that way.**
- Stage 2 (clustering) and Stage 3 (triage + specifics) are **complete**:
  122,118 notes → 72,737 units → 63,734 KEEP units.
- **Stage 5 — writing the permanent notes — is 320 of 63,734 done (0.5%). This
  is your job.**
- Stages 6, 7, 8, 8b, 9 are built and tested. 10 and 11 reuse existing tools.

## What to run

```bash
cd ~/ora
python3 scripts/engram-migration/stage5_run.py --backend claude-cli --workers 8
```

It derives its worklist from what is absent on disk, so re-invoking the same
command retries failures and continues — there is no resume flag. Expect ~3,171
batches and roughly 30M tokens. Then:

```bash
python3 scripts/engram-migration/stage6_check.py          # must reach zero HARD
python3 scripts/engram-migration/stage7_apply.py          # DRY RUN — read it
python3 scripts/engram-migration/stage7_apply.py --apply
python3 scripts/engram-migration/stage8_lexical.py
python3 scripts/engram-migration/stage8b_concept_audit.py
# Stage 9 per stage9_prompt.md, then rebuild relationships and ChromaDB
```

## Hard constraints

1. **Never work in `~/Documents/vault`.** It auto-commits to git every ~8 minutes
   and rsyncs to a remote host with `--delete`. A bulk edit there would be chopped
   into arbitrary commits and propagated to the server. `~/engram-work` is outside
   the rsync scope; that is the point.

2. **Nothing gets deleted. Ever.** Absorbed source notes move to
   `Archive/Engram Absorbed Sources 2026-08/`. The judgement defects in this
   pipeline — an invented canonical term, a paraphrase that failed to raise the
   level, a dropped facet, a platitude — are all structurally perfect and pass
   every mechanical check. The only way to catch them later is re-reading a merged
   note against the sources it claims to summarise, which requires those sources
   to still exist.

3. **`stage6_check.py` must report zero HARD violations before
   `stage7_apply.py --apply`.** The script refuses otherwise. `--allow-hard`
   exists; do not use it. A HARD violation means a fabricated `Instance:`
   specific or a note with no claim in it.

4. **Do not move Stage 5 to a cheaper model.** This is measured, not preference.
   On 300 identical notes with an identical prompt, Haiku paraphrased where it was
   asked to transform and invented canonical-sounding terms ("Bad faith reasoning"
   for what is actually *techniques of neutralization*). A local 122B did the same.
   Stage 5 is the only irreplaceable judgement in the pipeline. HANDOFF.md §6 has
   the evidence.

5. **Trust the filesystem, not any model's self-report.** Agent summary counts
   disagreed with disk twice here, once claiming 1,476 units processed when the
   real number was 1,013. Count from the result files.

6. **If a rate looks alarming, inspect real examples before believing it.** The
   conformance checker had three bugs of its own, each inflating a failure rate;
   one produced 31 false HARD failures that would have blocked the apply step over
   nothing. HANDOFF.md §7 documents all three.

## What I want from you

Run Stage 5 to completion, then walk the remaining stages in order. Report
measured rates from the real run rather than estimates. When you hit something
that contradicts what HANDOFF.md says, tell me — the doc is my best current
understanding, not scripture, and several of its numbers were corrected during
the work that produced it.

Do not merge the branch. Show me the result and I will decide.
