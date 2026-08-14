# Engram corpus repair — measurement record

The evidence behind the 2026-08 engram repair, preserved because `.migration/`
is scratch and gets deleted. These files are the reason the project ended where
it did; the numbers in them are not reproducible without re-running paid work.

The corpus lives in the Obsidian vault. The tooling was `scripts/engram-migration/`
in this repo, and the writing standard survives as the vault document
`Projects/Ora/Reference — Permanent Note Writer Calibration Record.md`.

## What was wrong, and what got fixed

122,118 auto-extracted notes were merged into 64,144. The merge's writer never
saw the source note bodies — only member titles plus extracted "specifics" — so
it kept general claims and dropped the clauses that gave them force. A 48-note
audit against full sources measured the damage.

Repaired: 4,038 notes rewritten from full sources, 8,744 keyword-dump `Instance:`
lines deleted, 604,099 relationship edges restored, 11,572 Historical Atomics
folded in, and relationships generated for the 11,744 notes that had none.

**Not repaired: ~60,206 never-revised merged notes.** That was a deliberate
decision, and the files here are why.

## The decision to stop

The case for rewriting the remaining 60,206 rested on the audit's 15%
"contrary to fact" rate. Interrogating that number dissolved it:

- 7 of 48 audited notes were contrary to fact. **6 of the 7 were a single
  defect** — a technical term in the title naming a different mechanism than the
  note's own content.
- 3 of those were caught by the prescan's imported-term detector and **are
  already rewritten**. Running that detector over the remaining 60,206 flags
  **zero** — the class is repaired at 100% coverage (`d2_imported_terms.json`).
- Of the 4 still unrepaired, **3 use terms present in the owner's own source
  text**. The audit judged them against each term's established meaning, not
  against provenance. In a private knowledge base that is grading the owner's
  vocabulary, not finding errors.
- That leaves 1–2 of 48 genuinely migration-introduced falsehoods — 2–4%, not
  15%.

The two criteria matter and were being conflated. The mechanical one, used by
both `prescan.py` and the rewrite prompt, is **provenance**: "never introduce a
named concept, bias, theory, or term of art that does not appear in the source
text." It fires only on terms the migration invented. The audit's criterion was
**correspondence with established meaning**, which is an outside standard.

Remaining damage is blunted prose, not falsehood — and a blunted note still
retrieves and still carries its subject. Rewriting 60,206 notes to sharpen it
was not worth ~660M tokens against a quota where 30 days of use is ~206M.

## Files

| file | what it establishes |
|---|---|
| `AUDIT-48-notes.json` | the 48-note audit — source of the 52% and 15% figures, with per-note reasoning |
| `MEASUREMENTS.json` | tier/batch arms and the blind judging that selected MiniMax-M3 over Opus for writing |
| `prescan.json` | 4,141 mechanically-flagged notes: 2,524 dropped qualifier, 1,588 imported term, 105 tautology |
| `d2_imported_terms.json` | empty by design — the imported-term scan over the 60,206, confirming zero remain |
| `pilot40_compare.json` | 40 never-revised notes, two independent M3 rewrites each, against their sources |
| `pilot40-rewrites/` | the 40 rewrites as returned |
| `judge_benchmark80_*.json` | 80 single notes labelled SOUND/DEFECT. Labels are an Opus pass, NOT human ground truth — the scorer measures agreement with Opus, not correctness |
| `m3-judge-verdicts/` | M3 judging itself against that benchmark |
| `phase_c_baseline.txt` | pre-run edge counts: 64,090 notes, 604,099 edges |
| `validation.json`, `pilot40_worklist.json` | the completion gate, and the sampled worklist |
| `PILOT-v7-fresh-titles.md`, `RETEST-6-defects.md` | title pilots the calibration record was derived from |

## Judge findings, for anyone who needs a defect judge here

Measured on the 80-case benchmark, where a redo repairs a real defect ~87.5% of
the time and breaks a sound note ~12.5% — so **a blind second pass is exactly
break-even** and all value comes from discrimination:

| judge | recall on 10 real defects | false alarms /70 | net fixed /10 |
|---|---|---|---|
| Haiku | 0/10 | 2 | **−0.3** |
| MiniMax-M3 judging itself | 4/10 | 18 | +1.3 |
| Opus | 10/10 | 0 | +8.8 |
| mechanical novel-vocabulary ≥20 | 9/10 | 35 | +3.5 |

Haiku is worse than doing nothing. M3 missed **both** `unsupported_hardening`
cases — the defect that comes from a model's own priors, which it cannot see in
its own output. Opus works but cost ~22k tokens per pairwise judgement.
