# Engram Permanent-Note Migration — Runbook

**ONE-TIME MIGRATION. This whole directory gets deleted when the migration
lands.** Nothing in the running system imports anything here. The deletion point
is Stage 11 completing and the branch merging.

## What problem this solves

The atomic extractor minted one note per conversation-pair mention with no
knowledge of the corpus, so a principle revisited across thirty conversations
produced thirty notes. The result was 122,131 notes that counted *mentions*, not
concepts. Measured on a 45-note random sample, ~60% could not be applied outside
their source domain: the transferable principle was present but welded to the
instance it came from.

The two producers have been fixed so this cannot recur:
- `orchestrator/historical/phase5_atomic_extraction.py` (batch) — commit `3d4ab7d1`
- `orchestrator/tools/extraction_engine.py` (live path) — commit `bd4f2b31`

This directory converts the existing corpus.

## Preconditions

1. **Work in the worktree, never the live vault.** The vault auto-syncs to git
   every ~8 minutes and rsyncs to `cloud-ora` with `--delete`; a bulk edit in
   place would be chopped into arbitrary commits and propagated to the server.

   ```
   git -C ~/Documents/vault worktree add ~/engram-work -b engram-permanent-notes
   ```

   `~/engram-work` sits outside the rsync scope, so nothing propagates until the
   branch is merged deliberately.

2. **Record the baseline SHA.** Git is the only undo. This migration deletes tens
   of thousands of files; a commit before Stage 7 is what makes that recoverable.

## Run order

| Stage | Command | Cost |
|---|---|---|
| 2 | `stage2_cluster.py --out ~/engram-work/.migration` | free |
| 3 | `stage3_run.js` via Workflow (Haiku) | ~51M tokens |
| 5 | `stage5_run.py --backend codex-cli --workers 4` (GPT-5.5/high) | 963 tokens/unit in the first 100 Codex units |
| 6 | `stage6_check.py` | free |
| 7 | `stage7_apply.py` (dry run), then `--apply` | free |
| 8 | `stage8_lexical.py` | free |
| 8b | `stage8b_concept_audit.py` + one batched model pass | small |
| 9 | `stage9_prompt.md` via Codex | small |
| 10 | `orchestrator/historical/phase_c_relationship_extraction.py --vault-root ~/engram-work/Engrams` | existing tool |
| 11 | `orchestrator/tools/chroma_source_rebuild.py --engrams-root ~/engram-work/Engrams` | existing tool |

Stages 10 and 11 reuse tooling that already exists. Do not write new versions.

The historical model assignment followed a measured A/B on 300 identical
notes. Haiku **paraphrases** where it is asked to transform: given "Exposure
holds up a mirror to recognizable selfish choices", it returned a reshuffle of
the same words while Opus produced "The critic who names particular selfish
choices lets the audience check the charge against the conduct". Haiku also
invents canonical-sounding terms that do not exist, claiming a concept name 100%
of the time against Opus's 66%. That evidence still rejects light and local
models for Stage 5. The current user instruction supersedes Claude routing:
Stage 5 and Stage 9 use Codex, and `stage5_run.py` hard-rejects other backends.

## Resumability

Every stage writes one file per shard and derives its worklist from what is
absent, so an interrupted run costs only the shards in flight. Stage 7 is
idempotent — a unit whose members are already gone is skipped.

**Regenerate a runner's shard list rather than passing it as `args`.** A run that
relied on `args` lost them silently, fell back to its defaults, and reprocessed
shards 0-39 for ~4.5M tokens. `stage3_run.js` has its list hardcoded for that
reason.

**Trust the filesystem, not the agents' self-reports.** Agent summary counts
disagreed with disk twice — once claiming 1,476 units processed when the real
figure was 1,013. Every progress number in this migration should be counted from
the result files.

## The gate

`stage6_check.py` classes three violations as HARD, and `stage7_apply.py` refuses
to run while any exists:

- **R2** — the `Instance:` line contains a specific absent from the source. This
  is the only unrecoverable defect: an invented record is indistinguishable from
  a real one, and the member notes are deleted once the merged note is written.
- **R5** — no `Instance:` line, or zero mechanism bullets (a note carrying only
  an Instance line has no claim in it).

Everything else is repairable and routes to `repair.json`.

## Measured facts worth not rediscovering

- **Leader clustering, never connected components.** At 0.75 similarity,
  connected components chains 42,677 notes into one blob. Leader assignment is
  non-transitive and caps the largest cluster at 204.
- **0.75 is calibrated.** Known same-concept families (the 68 productivity-wage
  notes) have median internal similarity 0.60, p95 0.80; random pairs sit at
  median 0.25, p99 0.49.
- **Embeddings miss cross-domain duplicates.** Of pairs whose *generalized*
  titles state the same principle, 70.4% had original similarity below 0.75.
  That is what Stage 8 exists for, and why it must run after Stage 5.
- **Audit `standard_concept` before Stage 10.** It was specified as a retrieval
  aid and turned out to carry the whole merge signal, so its errors propagate
  into the merges and then into the rebuilt graph. Observed failure modes:
  invented terms ("Bad faith reasoning"), misattribution ("Confirmation bias" on
  a social-engineering note), naming drift ("costly signal" vs "costly
  signaling" — 1 + 14 notes that belong together), and over-broad terms.
  Auditing distinct concept NAMES is orders of magnitude cheaper than auditing
  notes.
- **Stage 8's working signal is the shared concept name, not lexical overlap.**
  On 2,337 real generalized notes: 985 pairs from shared `standard_concept`, 1
  from title overlap. Generalization makes the concept nameable, not the wording
  uniform.
- **`seen_count` never worked.** 100% of vault notes read `1`, and in ChromaDB
  only 0.16% exceed 1 with a maximum of 2. Recurrence was never measured; cluster
  size is the real signal.
- **8,021 ChromaDB records resolve to no file on disk.** They inflate every
  similarity query and are cleared by the Stage 11 rebuild.
- **Archive rate splits by unit size**, and this is correct behaviour rather than
  a defect: singletons archive at 9.3%, multi-member units at 2-3%. A bare fact
  clustered with four principles should be absorbed as the Instance evidence of
  the principle it demonstrates, not archived.

## Teardown

When Stage 11 is done and the branch is merged:

```
rm -rf ~/ora/scripts/engram-migration
rm -rf ~/engram-work/.migration
git -C ~/Documents/vault worktree remove ~/engram-work
```

The `.migration` cache holds a 2.1 GB embedding matrix. Do not leave it behind.
