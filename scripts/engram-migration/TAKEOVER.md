Take over an in-progress repair of my Obsidian vault's `Engrams/` knowledge corpus.
Substantial work is done, everything is committed, nothing is running.

**Read `~/ora/scripts/engram-migration/PLAN.md` completely before running anything.**
It is 441 lines and current. Start with §2 (state), §4 (what's left and in what
order), §6 (traps that cost real tokens), §8 (open items). Do not read
`README.md` — it is marked superseded.

## Where it stands

`~/engram-work` (a git worktree of `~/Documents/vault`, branch
`engram-permanent-notes`), corpus at `Engrams/`:

- **75,834 notes**, flat, no subdirectories
- **604,099 relationship edges, 100% resolving, zero dangling**
- 11,744 notes still have no relationships
- committed at `c637f57995`; rollback point `516100a1d`
- the live vault is untouched

**The number that matters and is easy to misread: only 5.3% of the corpus has been
rewritten from good input.** 4,026 notes were rewritten properly; 60,236 (79.4%)
still carry text from a pass whose writer never saw the source notes. A 48-note audit
of that text found 52% needed a fix and 15% asserted something false. The mechanical
prescan flagged only 19%, so it found about a third of what needs work. The 4,038
completed rewrites are real progress and are not the job finished.

## Do this next

Phase C for the 11,744 notes lacking relationships, on MiniMax (key is in the
keyring, `service='ora'`, `username='minimax-api-key'`):

```bash
cd ~/ora && PYTHONPATH=~/ora python3 orchestrator/historical/phase_c_relationship_extraction.py \
  --vault-root ~/engram-work/Engrams \
  --paths-file ~/engram-work/.migration/phase_c_paths.txt \
  --chromadb-path ~/engram-work/.migration/chroma-temp \
  --backend minimax --max-workers 8
```

Afterwards prove the other 64,090 notes were untouched, against the baseline in
`.migration/phase_c_baseline.txt` (64,090 notes / 604,099 edges / fingerprint
`aaf814bc9f640db3`).

## Then bring me a decision, don't just proceed

**The writing prompt currently demands something a third of the notes cannot supply.**
`rewrite_prompt.md` requires every title to state a "perverse conversion" — X turns
into Y where Y is the opposite of what it should be. That rule came from two titles I
wrote and it does not generalise: blind judging of 12 rewrites found 12 of 36
judgements where NO variant contained a conversion, because the source material has
none. Judges: "Nothing in this note converts — every title states a static blind
spot."

Demanding an inversion where none exists invites the model to invent one, which is
the class of failure this whole repair exists to remove. **Soften that rule before any
further rewriting, and show me your proposed wording first.** What a good note looks
like when the source is plainly descriptive is my call, not yours.

## Hard constraints

1. **Never run Phase C without `--paths-file`.** It globs every note and
   `write_note_with_relationships` REPLACES the field, emptying it where the model
   finds nothing. The naive command destroys 604,099 working edges.
2. **Never work in `~/Documents/vault` directly.** It auto-commits every ~30s and
   rsyncs to a remote with `--delete`.
3. **Rewrite notes BEFORE generating their relationships.** Rewriting 5.3% of notes
   put a changed claim on one end of 16.3% of edges. The remap repairs pointers
   perfectly and cannot repair truth.
4. **Use `ps -eo pid=,args= | grep "[p]attern"`, never `pgrep -f`.** pgrep returned 0
   for four live processes here and four stale shards then burned 25 minutes running
   a buggy parser.
5. **Do not add caps, limits, or word targets.** Every one introduced in this project
   became a defect: truncating the writer's input de-fanged 56% of the corpus,
   capping title length replaced actors with pronouns, capping neighbour text to 600
   chars had the classifier judging 17.6% of notes on partial text.
6. **Sandbox-test anything destructive on a throwaway copy first.** Two bugs in the
   apply step would have reported success while writing nothing.
7. **Verify an alarming rate before believing it.** Five detectors over-fired here —
   one flagged 100%, one 80%, one 42% — every time by proxying a judgement question
   with a string match.

## How I work

Show me real notes, not summaries or percentages — every genuine advance in this
project came from me reading actual output and correcting it. State corrections
plainly and move on. Don't audit indefinitely; audit when a decision turns on the
answer. Tell me the running cost before starting something long, and check in if it
runs over an hour.

Do not merge the branch. Show me the result and I will decide.
