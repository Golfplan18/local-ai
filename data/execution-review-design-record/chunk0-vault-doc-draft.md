# Draft — vault "Reference — Pipeline Trace System" edits for Chunk 0 landing

*Applied to the vault (branch → PR → squash-merge on obsidian-vault) only after Codex code-review approval. Three edits.*

## Edit 1 — §2 Storage layout: add the manifest line to the tree

In the per-turn directory listing, after the `metadata.json` line, add:

```
│   │   ├── trace-manifest.json           (join layer — kind, terminal status, expected vs actual steps, lineage; §4)
```

## Edit 2 — §4: new subsection after "### metadata.json"

### trace-manifest.json

The per-turn join layer (Trace Walk Chunk 0, landed 2026-07-12). Written as a skeleton by `start_trace` (`terminal_status: "open"`) and atomically overwritten by `pipeline_trace.finalize_manifest` from a single generator-level (or function-level, for the CLI path) `finally` — covering both production entry points, the Flask chat server's `_pipeline_stream` and the CLI/terminal interface's `run_pipeline` — so it also finalizes on client disconnect and uncaught exceptions. Schema v1 fields:

- `schema_version` — 1.
- `conversation_id`, `turn_timestamp_utc` — the join key. `trace_ref` on the conversation side (conversation.json assistant turns; conversation-manifest.jsonl lines) is `"<conversation_id>/<turn_timestamp>"` relative to the trace root, so any saved turn resolves mechanically to its trace dir with zero inference.
- `trace_kind` — what the turn actually was: `chat-gear1..4` (full pipeline), `chat` (pipeline turn that died before gear selection), `direct` (gear-1/2 bypass), `runtime_command`, `risk_hold`, `resolution_continuation`, `framework_elicitation`, `framework_command`, `clarification_pending`, `clarification_resume`, `no_endpoint_error`, `unknown` (died before any branch). `framework-run` / `framework-milestone` / `debug-run` / `resume` are reserved for Chunks 1/3/4.
- `terminal_status` — `completed` | `short_circuit` | `paused` (clarification pending — an intentional stop, never "abandoned") | `error` (including paths that catch, yield an SSE error, and return) | `abandoned` (e.g. client disconnect mid-pipeline) | `open` (finalizer never ran — the turn died catastrophically).
- `gear`, `mode` — gear is signalled explicitly at dispatch, but `step-health.json` (the actual-execution ground truth, written by whichever gear function really completed) always wins when present — gear 4 can silently degrade to gear 3 internally on unrecoverable analyst streams, and the manifest reports what actually ran, not the pre-dispatch guess. Gear-1/2 turns write no step-health.json, so the dispatch-time signal is the only one available there.
- `framework_id`, `milestone_id` — null until Chunk 1.
- `expected_steps` — static per-gear required-step tables. Deliberately conservative: verifier cycles, claim verification (step4.5), unflagged scans (step5.5), the quality gate, and web consultation are observed-only — they appear in `actual_steps` when they ran but are never "missing". Two documented reduced-footprint completions (a single-endpoint gear-3 fallback; a gear-4 external-consolidation handoff) are contingency-aware: the fallback marker replaces the steps it makes moot in `expected_steps` rather than the manifest reporting a healthy turn as broken. A viewer renders `expected − actual` loudly; that difference is real, not noise.
- `actual_steps` — the `step*.json` files that actually landed, minus derived artifacts.
- `derived_artifacts` — summaries present in the dir (`step-health`, `step-visual-hook`, `step-visual-emissions`, `cost-summary`) — classified separately so they can never masquerade as pipeline steps.
- `redaction_level` — `private` for private-tagged conversations, else `default` (stealth turns have no trace at all).
- `retention_state` — `default` | `pinned`. Carried in schema v1; sweeper *enforcement* of pins lands with Chunk 1.
- `parent_trace_ref` / `child_trace_refs` — lineage. Exercised today by clarification resume/skip: the paused turn's ref is stored at pause time and stamped on the resume turn's manifest. `child_trace_refs` populates in Chunk 1 (framework parent → milestone children).
- `finalized_at` — UTC timestamp of the last finalize.

Failure posture: fail-open everywhere. A manifest failure prints to stderr and never breaks a turn, never blocks a conversation save, and never costs the turn its trace.

## Edit 3 — new §9g entry (after §9f)

## 9g. Trace manifest + conversation-side trace_ref (Chunk 0, 2026-07-12)

The Trace Walk build program's join layer. One `trace-manifest.json` per turn dir (see §4); `trace_ref` added to conversation-manifest.jsonl lines and conversation.json assistant turns (null for stealth/untraced turns by construction). Covers both the Flask chat server (`_pipeline_stream`) and the CLI/terminal interface (`run_pipeline`) — an earlier draft of this chunk covered only the former; a self-review before code review caught that the CLI path opened traces it never finalized. §10 checklist for the new surface: **off-switch** — inherits `ORA_PIPELINE_TRACE` (no trace dir → no manifest); **stealth** — inherits Layer-1 no-creation (§5), and the conversation-side field is null; a code-review finding caught the turn-head tag lookup silently missing a brand-new stealth/private conversation's first-turn request tag (no envelope yet to read) — fixed to prefer the persisted envelope tag but fall back to the request's own tag when no envelope exists; **purge** — the manifest lives inside the turn dir, so `purge_conversation_traces` rmtree covers it, and the conversation-manifest purge rewrite carries the new field transparently; **gitignore** — covered by the existing `data/pipeline-traces/` exclusion (regression-tested via `git check-ignore` in `orchestrator/tests/test_trace_manifest.py`); **documentation** — this entry + §4. In passing, the clarification resume/skip endpoints gained the same best-effort `cost-summary.json` computation the main pipeline path has had since 2026-05-28 (they previously never wrote one). Verified live post-landing: a real bypass turn and a real full-adversarial-pipeline turn (gear 4, `steelman-construction` mode, 8 legitimately-observed-only steps correctly excluded from `expected_steps`) both produced honestly-classified manifests with correctly-stamped `trace_ref`.
