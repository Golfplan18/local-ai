# Chunk 1 Design Addendum - Capture Integrity

*Design-gate packet for Codex. Parent plan: `/Users/oracle/Documents/vault/Working - Trace Walk and Earned Autonomy Build Plan.md` (approved 2026-07-09; current vault copy read after `git pull`, already up to date). Kickoff protocol: `/Users/oracle/ora-worktrees/trace-walk-kickoff-prompt.md` read first in full. Code anchors below were freshly re-derived against ora HEAD `86a888bc4f0603dd32abdf3aecafcad7f48c29f3` on 2026-07-12. Do not trust these anchors after any rebase; re-verify before implementation and again before merge.*

## Scope

Chunk 1 closes trace replay gaps that Chunk 0 intentionally left open:

- Framework trace propagation: `/framework` one-shot parent traces become honest `framework-run` manifests, and every milestone gear call gets a child trace directory linked from the parent.
- Gear-3 step4/step5 capture: persist the verbatim evaluator and reviser user messages.
- Verifier prompt capture: persist the verifier system prompt verbatim for Gear 3 and Gear 4 verifier-cycle files, and for final-output quality gate files where the gate uses verifier framework prompts.
- Redo capture: write dedicated step files for re-revisions after verifier FAIL and quality-gate redos.
- Per-call config snapshots: record endpoint/model/sampling configuration for every model call in the trace context, without secrets.
- Pin/archive semantics: honor `retention_state: pinned` in the trace sweeper and provide a CLI pin/unpin/status affordance now. The UI pin button remains Chunk 2.

Out of scope:

- Trace viewer/export routes and UI.
- Resume/re-execution risk gating.
- Framework reliability ledger or learning library.
- Vault documentation edits until the user explicitly approves vault-side changes.

## Verified Ground Truth The Design Rests On

- `pipeline_trace.start_trace` writes `metadata.json` and a `trace-manifest.json` skeleton at lines 80-166. The skeleton already has `framework_id`, `milestone_id`, `retention_state`, `parent_trace_ref`, and `child_trace_refs` fields at lines 442-465.
- `pipeline_trace.finalize_manifest` is idempotent/fail-open and currently accepts `trace_dir`, `kind`, `status_hint`, `mode`, `gear`, and `parent_trace_ref` at lines 528-645. It preserves existing manifest fields it does not own, but it does not yet accept framework/milestone fields or child refs.
- `pipeline_trace.trace_ref_for_dir` returns the relative `<conversation_id>/<turn_timestamp>` ref at lines 422-439. This is the right key for parent/child linkage and CLI pinning.
- `server._pipeline_stream` wraps `_pipeline_stream_impl` and finalizes the manifest in a single generator-level `finally` at lines 3048-3097. Its `turn_state` has `trace_dir`, `kind`, `status`, `mode`, `gear`, and `parent_ref`, but no framework fields or child refs yet.
- The server `/framework` one-shot path starts at `server/server.py` lines 3390-3445. It sets `turn_state["kind"] = "framework_command"` and calls `run_framework_command(user_input, config)` with no trace argument at line 3431.
- `boot.run_pipeline` mirrors the server wrapper at lines 9165-9207. Its CLI `/framework` branch starts at lines 9321-9367, seeds tool context with `trace_dir`, then calls `run_framework_command(user_input, config)` with no trace argument at line 9364.
- `milestone_executor.run_framework_command` is the shared server/CLI framework entry point at lines 994-1020. It calls `execute_framework(framework_name, framework_query, config, config_name=config_name)` at line 1017.
- `milestone_executor.execute_framework` parses the framework and selects mode/milestones at lines 205-287, then iterates milestones at lines 302-305. It does not accept or propagate trace context.
- `_run_milestone` builds the handoff and calls `_run_through_gear_pipeline` at lines 416-456. Retries are possible, so a "milestone gear call" can occur more than once for the same milestone.
- `_run_through_gear_pipeline` builds `context_pkg` at lines 565-589 and dispatches to `run_gear4` or `run_gear3` without a trace dir. `_build_context_pkg` at lines 610-622 contains `framework_execution` and `milestone_id`, but no `trace_dir`, `framework_id`, parent trace ref, or child trace ref.
- Gear 3 captures Step 3 user message, but Step 4 and Step 5 omit it. `step4-eval` payload at `boot.py` lines 11486-11492 has `system_prompt` and responses, but no `user_message`. `step5-revised` payload at lines 11585-11591 has `system_prompt` and responses, but no `user_message`.
- Gear 3 verifier cycles build `verify_system` at lines 11637-11640 and `verify_user` at lines 11644-11670. The `step6-verifier-cycle-N` payload at lines 11708-11720 stores verdicts/retry metadata but not `system_prompt` or `user_message`.
- Gear 3 verifier FAIL re-revision happens at lines 11747-11763 with no dedicated trace step file. Gear 3 quality-gate redo happens at lines 11824-11843 with no dedicated trace step file. The quality-gate result file at lines 11857-11865 omits `system_prompt` and `user_message`.
- Gear 4 Step 4 and Step 5 already capture user messages at lines 12390-12446.
- Gear 4 verifier cycles build `verify_system` at lines 12502-12505 and per-stream user messages at lines 12511-12555. The cycle trace payload at lines 12648-12676 stores `verify_system_prompt_chars` plus both user messages, but not the system prompt itself.
- Gear 4 verifier FAIL re-revisions run at lines 12740-12777 with no dedicated step file. Gear 4 quality gate pass files at lines 13143-13155 omit `system_prompt` and `user_message`. Formatting redo, analysis reconsolidation redo, and post-reconsolidation reformat run at lines 13170-13260 with health records but no dedicated trace files.
- `retention_sweeper._sweep_traces` deletes old turn dirs only by `mtime` at lines 135-153 and never reads `trace-manifest.json`; pinned traces are not honored yet.
- Existing focused tests are `orchestrator/tests/test_trace_manifest.py` and `orchestrator/tests/test_retention_sweeper.py`. The full suite lives under `orchestrator/tests`; when run from a worktree, `ORA_HOME` must be exported to that worktree.

## Design

### D1 - Framework Parent And Child Trace Lineage

Add optional trace plumbing through the shared framework entry path:

- `run_framework_command(user_input, config, *, trace_dir=None, conversation_tag="", trace_context=None)`
- `execute_framework(..., trace_dir=None, conversation_tag="", trace_context=None)`
- `_run_milestone(..., parent_trace_dir=None, parent_trace_ref=None, framework_id=None, selected_mode=None, conversation_tag="", trace_context=None)`
- `_run_through_gear_pipeline(..., child_trace_dir=None, parent_trace_ref=None, framework_id=None, selected_mode=None)`
- `_build_context_pkg(..., trace_dir=None, parent_trace_ref=None, framework_id=None, selected_mode=None)`

Server and CLI `/framework <name> <query>` branches will set the parent turn kind to `framework-run`, pass their already-opened `trace_dir` to `run_framework_command`, and pass a small mutable `trace_context` dict. On success, they set `turn_state["status"] = "completed"` because parent framework runs do not write `step-health.json` themselves. On framework command errors caught and returned as user-facing bracketed text, the shared command sets `trace_context["status"] = "error"` so server/CLI wrappers finalize honestly.

`execute_framework` fills `trace_context` with `framework_id`, selected mode, execution id, and child trace refs. `pipeline_trace.finalize_manifest` gets optional `framework_id`, `milestone_id`, and `child_trace_refs` parameters; server and CLI wrappers pass the extra `turn_state` values. This keeps finalization single-point and preserves Chunk 0's disconnect/error behavior.

Each milestone attempt opens its own child trace dir using `pipeline_trace.start_trace`:

- `conversation_id`: inherited from the parent trace manifest when available, otherwise the existing orphan path.
- `raw_input`: the handoff packet, because that is the actual user message sent into the gear pipeline for this milestone.
- `conversation_tag`: inherited from the parent so private traces stay marked private and stealth remains no-trace.
- Manifest fields: `trace_kind: "framework-milestone"`, `framework_id`, `milestone_id`, `mode`, `gear`, `parent_trace_ref`.

The child ref is appended to the parent manifest immediately after child creation, using a fail-open helper in `pipeline_trace` such as `append_child_trace_ref(parent_trace_dir, child_ref)`. The child is finalized in `_run_milestone` with `completed` or `error` in a `finally`, so retries leave separate child traces instead of overwriting the first failed attempt.

### D2 - Gear 3 Verbatim Step 4 And Step 5 User Messages

Persist the already-built messages:

- Add `user_message: eval_messages[1]["content"]` or a named `eval_user` variable to `step4-eval`.
- Add `user_message: revise_user` to `step5-revised`.

No prompt behavior changes; this is trace-only.

### D3 - Verifier System Prompt Verbatim, Both Gears

Add `system_prompt: verify_system` to:

- Gear 3 `step6-verifier-cycle-N`.
- Gear 4 `step6-verifier-cycle-N`.

Add `system_prompt` and `user_message` to final-output quality gate trace payloads:

- Gear 3 `step6_5-quality-gate`.
- Gear 4 `step8_6-quality-gate-pass-N`.

The existing `verify_system_prompt_chars` field in Gear 4 can remain as a cheap summary, but it is no longer the only persisted verifier system prompt evidence.

### D4 - Dedicated Redo Step Files

Write a trace step for every model call that changes the draft after a verifier or quality-gate rejection:

- Gear 3 verifier FAIL re-revision: `step6-cycle-{N}-re-revision`, with `system_prompt`, `user_message`, `raw_response`, `ok`, `reason`, `endpoint`, and resolved prior verifier verdict.
- Gear 3 quality-gate redo: `step6_5-quality-gate-redo`, with `system_prompt`, `user_message`, `raw_response`, `ok`, `reason`, and `endpoint`.
- Gear 4 verifier FAIL re-revision depth/breadth: `step6-cycle-{N}-re-revision-depth` and `step6-cycle-{N}-re-revision-breadth`, with the same fields.
- Gear 4 quality-gate formatting redo: `step8_6-quality-gate-formatting-redo`.
- Gear 4 quality-gate analysis redo/reconsolidation: `step8_6-quality-gate-reconsolidate`.
- Gear 4 reformat after reconsolidation: `step8_6-quality-gate-reformat`.

These are observed-only steps. They should appear in `actual_steps` but not in `expected_steps`, matching Chunk 0's "verifier cycles and contingencies are legitimate observed steps, not required steps" rule.

### D5 - Per-Call Config Snapshots

Add one append-only trace-local file, `model-call-config.jsonl`, written at the call boundary for every model call when a trace context exists. This should live near `call_model`, alongside the existing usage recording flow, because that is the narrowest place where every external/local model call already has an endpoint dict and the active trace context.

Each line should include:

- timestamp UTC.
- step label from the existing model-call context var where available.
- endpoint id/name/type/service/provider/base_url host only, not API keys or credentials.
- model id/model name/openrouter fallback model id where present.
- sampling/limit parameters present on the endpoint: `temperature`, `top_p`, `top_k`, `max_tokens`, `max_completion_tokens`, timeout fields, reasoning effort fields if present.
- `config_name`, `slot`, and `gear` when the caller supplied them through the existing retry/call path.

This is intentionally a sidecar JSONL rather than duplicating the same config blob into every step file. Step files remain the human replay package; `model-call-config.jsonl` is the per-call runtime configuration ledger.

### D6 - Pinned Retention And CLI Affordance

Add trace-layer helpers in `pipeline_trace.py`:

- `resolve_trace_ref(trace_ref) -> path | None`, with boundary-anchored containment under `TRACE_ROOT`.
- `read_manifest(trace_dir)` / `update_manifest_fields(trace_dir, **fields)` fail-open helpers.
- `set_retention_state(trace_ref, state)` accepting `default` and `pinned`.

Add a minimal CLI in `pipeline_trace.py` itself:

- `python orchestrator/pipeline_trace.py pin <trace_ref>`
- `python orchestrator/pipeline_trace.py unpin <trace_ref>`
- `python orchestrator/pipeline_trace.py status <trace_ref>`

This keeps the affordance next to the trace persistence code and gives Chunk 2's UI button a reusable function. It does not create a second command system or add a visible chat UI.

Modify `retention_sweeper._sweep_traces`: before deleting an old turn dir, read `trace-manifest.json`; if `retention_state == "pinned"`, skip deletion and count it in a new `traces_pinned_skipped` summary field. Unreadable/missing manifests are not treated as pinned.

## Trace Doc Section 10 Checklist

Chunk 1 adds new data inside the existing trace persistence surface and changes the retention behavior for pinned traces. Checklist:

1. Off-switch: all new step files, child traces, and `model-call-config.jsonl` inherit `ORA_PIPELINE_TRACE` because they only write when `trace_dir` exists.
2. Stealth-awareness: stealth prevents parent trace creation; no parent means no child traces or config snapshots. If a future bug bypasses that, `conversation_closeout._purge_stealth` still wipes by conversation id.
3. Purge layer: unpinned child traces and config snapshots live under `data/pipeline-traces` and are swept with the turn dir. Pinned traces are intentionally exempt until unpinned.
4. Gitignore: existing `data/pipeline-traces/` exclusion covers child trace dirs and `model-call-config.jsonl`; add/extend tests using the existing manifest gitignore pattern if needed.
5. Documentation: update `Reference - Pipeline Trace System.md` after implementation approval and user vault go-ahead, noting framework parent/child traces, config snapshots, redo step files, and pinned retention.

## Tests

Focused unit/integration tests:

- `test_trace_manifest.py`: finalize preserves and stamps `framework_id`, `milestone_id`, `parent_trace_ref`, and `child_trace_refs`.
- New/extended framework trace test: stub gear execution so `/framework` or `run_framework_command` creates a parent `framework-run` manifest and a child `framework-milestone` manifest, without real model calls.
- Server and CLI entry tests: verify both `server._pipeline_stream` and `boot.run_pipeline` pass the parent trace into `run_framework_command` and finalize the parent as `framework-run`.
- Gear 3 trace tests: stub model calls and assert `step4-eval.json`, `step5-revised.json`, `step6-verifier-cycle-1.json`, and `step6_5-quality-gate.json` contain the newly required verbatim fields.
- Gear 4 trace tests: assert verifier cycle and quality gate pass files contain verbatim system/user prompts; force verifier FAIL/quality-gate redo branches and assert dedicated redo step files are written.
- Config snapshot test: run a mocked model call under a trace context and assert `model-call-config.jsonl` contains endpoint/model/sampling fields and no API key/credential fields.
- Retention sweeper test: old pinned turn dir is skipped; old default turn dir is removed; missing/unreadable manifest is not treated as pinned.
- CLI pin test: pin/unpin/status update only manifests under `TRACE_ROOT`, reject traversal refs, and preserve existing manifest fields.

Protocol tests:

- Full-suite parity after implementation: two fresh runs at the same commit, baseline and implementation, both with `ORA_HOME` exported to their respective worktree roots, sorted FAIL/ERROR lists byte-identical.
- Live smoke after Codex code-review approval and merge: one real gear-3 turn, one real gear-4 turn, and one framework run inspected from disk for parent + child trace lineage.

## Acceptance Criteria

- One real gear-3 turn is replayable from disk with verbatim Step 4 user message, Step 5 user message, verifier system prompt, verifier user prompt, quality-gate prompt, redo files if the branch fires, and per-call config snapshots.
- One real gear-4 turn is replayable from disk with verifier system prompt, verifier user prompts, quality-gate prompts, redo files if branches fire, and per-call config snapshots.
- A real framework run produces a parent `framework-run` trace plus one or more child `framework-milestone` traces. Parent and child manifests link mechanically via `child_trace_refs` and `parent_trace_ref`.
- Pinned trace dirs survive the retention sweeper; unpinned old trace dirs are still swept.
- Stealth and global trace-off modes produce no new trace files.
- Full-suite parity shows zero new FAIL/ERROR entries versus a fresh baseline.

## Open Questions For The Judge

- Q1: Should a framework run whose `run_framework_command` catches a parse/file error and returns a user-facing bracketed error finalize as `terminal_status: "error"`? Recommendation: yes. It is not a successful framework run, even though the chat transport returned normally.
- Q2: For milestone retries, should each failed attempt get its own child trace? Recommendation: yes. The plan says each milestone gear call gets a child trace; collapsing retries would erase the failure evidence the trace system is meant to preserve.
- Q3: Should the CLI affordance live in `pipeline_trace.py` rather than a new script? Recommendation: yes. It avoids another active file, keeps path-containment and manifest update logic in one place, and gives the future UI button one shared function.
- Q4: Should `model-call-config.jsonl` be automatic at `call_model` rather than manually duplicated into every step file? Recommendation: yes. It captures visual/retry/supplemental calls as well as main gear calls and is less likely to drift when new model-call sites are added.

## Design-Gate Verdict

Codex design gate, 2026-07-12: APPROVE WITH MODIFICATIONS against ora HEAD `1eaacc67cda542c805edeb6289a5598e8d011637`.

Approved Q answers:

- Q1: Bracketed parse/file/framework errors finalize as `terminal_status: "error"`.
- Q2: Each milestone retry gets its own child trace.
- Q3: The CLI affordance lives in `pipeline_trace.py`.
- Q4: `model-call-config.jsonl` is automatic at `call_model`.

Binding implementation conditions:

1. Child trace context must be explicitly bound around each `_run_milestone` attempt. Framework milestone gear calls bypass `run_step2_context_assembly`, so passing only `trace_dir` in `context_pkg` is insufficient; set/reset trace and tool-event context for the child attempt, then restore the parent context.
2. `config_name`, `slot`, and `gear` must reach `call_model` via a concrete per-call metadata channel, such as a `ContextVar` set/reset by `_call_with_retry`.
3. `trace_context["status"] = "error"` from bracketed framework errors must be copied back into server/CLI `turn_state` before finalization.
4. `append_child_trace_ref` and finalization must dedupe and preserve existing `child_trace_refs`; parent finalization must not clobber refs appended during milestone execution.
5. `resolve_trace_ref` for pin/unpin/status must resolve only to a turn directory containing `trace-manifest.json`, reject traversal/root/conversation-directory refs, and preserve unrelated manifest fields.
