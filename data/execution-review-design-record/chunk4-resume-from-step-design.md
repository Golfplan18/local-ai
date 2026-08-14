# Chunk 4 Design: Resume from step

Status: Revision 8 proposed for Codex design-gate review. Revision 7 was BLOCKED on one finding (HealthMarkerContract source_order vs precedence table editorial inconsistency); the matcher prose now explicitly ties precedence to the source_order single-pass iteration. All verified code anchors, D4.2 fatal-control contract, and UnhealthyOutputPolicy closed schemas carry forward unchanged. No implementation is authorized by this document.

Verified Ora base: `origin/main` at `81b14cac6d7461e40dcb5cdffd640ea8d484dea2` on 2026-07-14.

Program context: Chunk 3 landed as PR 264 / merge `68ef20db`. The commits between that merge and this design base are runtime-path, registry, and launcher consolidation changes. This design re-derived its code anchors from the current base rather than carrying forward old line numbers.

## 1. Outcome

Chunk 4 adds a default-OFF, trace-backed way to recompute a supported Gear 3 or Gear 4 pipeline from a selected stage through the end. It uses exact execution-time checkpoints, presents a conservative cost and capability plan before approval, consumes server-authoritative approval exactly once, creates a new `resume` trace, and preserves an honest distinction between upstream evidence reused from the source trace and steps recomputed in the new trace.

A resume is not a replay and is not an edit of the original trace. Model sampling, approved read-only external consultations, and an optional human correction can produce a different result. The source trace remains immutable except for deduplicated lineage and append-only resume-attempt events.

## 2. Scope

### In scope

- Text-only finalized `chat-gear3` and `chat-gear4` traces captured after the Chunk 4 checkpoint writer is enabled.
- A structured browser action, "Re-run from here", on supported pipeline steps in Trace Walk.
- Deterministic CLI prepare, approve, and execute commands using the same core implementation.
- Exact checkpoint capture during ordinary Gear 3 and Gear 4 execution.
- Reuse of the existing probe-era prepare, risk-decision, server-side approval, atomic consumption, trace-context binding, and durable-finalization principles.
- A new `trace_kind: "resume"` with exact source lineage.
- A bounded optional human correction, mechanically bound to approval and visibly labelled counterfactual.
- Conservative call/token/capability estimates before approval and hard execution ceilings afterward.
- Explicit re-approval of model calls and read-only web consultation when a selected downstream stage can invoke them.
- Trace Walk and export rendering that separates reused upstream evidence from recomputed evidence.
- Both production entry points: `server.py::_pipeline_stream` and `boot.py::run_pipeline`.
- Clean refusal for legacy, open, abandoned, malformed, cross-conversation, version-incompatible, image-dependent, ambiguous, or incompletely captured traces.

### Out of scope

- Resuming Step 1 intake or Step 2 context assembly. Those operations can route tools, retrieve mutable context, and construct a new turn package; they remain whole-turn reruns.
- Framework-parent and framework-milestone resume. A standalone milestone resume would bypass the framework's orchestration and drift-check contract. It requires a later framework-aware design.
- State-changing tool, publish, send, delete, write, or other external-action replay. Chunk 4 refuses such plans rather than silently repeating them.
- Image-bearing, attachment-dependent, visual-output, visual-model, and local-render work. Chunk 4 is text-only in both input and output.
- Resuming pre-Chunk 4 traces by guessing missing state from step output files.
- Changing provider, model, mode, configuration, or token limits during resume. The only user modification in this chunk is the bounded correction.
- Chained resume. A `resume` trace is not an eligible source and does not emit new resume checkpoints in Chunk 4.
- Natural-language resume routing.
- Vault, Paper, website, or Registry edits during implementation without separately explicit authorization.

## 3. Binding principles

1. **Exact or unavailable.** Diagnostic trace artifacts are not assumed to be executable checkpoints. If the complete required state was not captured exactly, the stage is `NOT_RESUMABLE`.
2. **No false execution history.** Reused source steps are references with digests, not copied files and not `actual_steps` in the resume trace.
3. **Approval is durable, server-authoritative, and one-time.** A client-supplied digest is integrity evidence, not authority. CLI and server use the same cross-process authority under the same `ORA_HOME`; execution atomically consumes it before any paid or external request.
4. **Cost and capabilities are enforceable ceilings.** The approved plan binds maximum physical model attempts, token caps, approved fallback providers, read-only web calls, expiry, correction, source digests, and runtime fingerprint. Execution stops before exceeding any ceiling; all visual capability is refused.
5. **External actions never repeat silently.** Read-only external consultation is named and re-approved. State-changing actions are refused in this release.
6. **Same conversation only.** The active turn, source trace, resume trace, pending approval, and output turn share one conversation ID.
7. **Same engine or unavailable.** The captured state is executed only by the compatible resume engine and stage-prompt implementation identified by its fingerprint.
8. **The normal and resumed paths share stage code.** Gear stage logic is extracted, not copied. Full runs and resumes use the same stage runners so fixes cannot drift between two implementations.
9. **No silent Gear 4 boundary reset.** Existing Gear 4 fallbacks that would restart Gear 3 before the approved boundary are not allowed during resume. The resume ends `error` with an explicit reason.
10. **Durability precedes success.** A resume reports `completed` only after required artifacts, lineage, expected/actual/derived sets, and terminal status have been read back from disk. Uncatchable process loss may leave `open`; it is never falsely called `abandoned`.
11. **Resume-control failure is not model output.** A bound resume policy violation, budget exhaustion, route/policy mismatch, or required policy-evidence write failure is a fatal control stop. It must never be converted into an unhealthy string, `BROKEN`, a retry, a provider fallback, a repair/degradation result, a Gear fallback, or a successful result. Only the shared top-level resume dispatcher may catch this typed fatal control exception and convert it into the documented stop result, durable evidence, step health, and terminal `error` manifest. With no resume policy bound, ordinary runs and probes retain their current exception-to-output and fail-open behavior.

## 4. Verified ground truth on current Ora main

### 4.1 Trace creation, lineage, and projection

- `orchestrator/pipeline_trace.py:271` defines `start_trace()`.
- `orchestrator/pipeline_trace.py:870` and `:898` define exact directory/ref conversion and strict resolution.
- `orchestrator/pipeline_trace.py:938`, `:955`, and `:976` update manifest fields, child refs, and probe refs. The resume implementation must not compose these best-effort helpers into an unlocked multi-file lineage transaction.
- `orchestrator/pipeline_trace.py:1021` builds the current skeleton. It already has parent/child and investigation/probe fields, but no resume-specific fields.
- `orchestrator/pipeline_trace.py:1051` derives expected steps. `resume` currently has no boundary-aware table and would incorrectly fall through to a whole-gear expectation.
- `orchestrator/pipeline_trace.py:1115` finalizes manifests and derives actual/derived artifacts.
- `orchestrator/pipeline_trace.py:1336` builds the browser-safe manifest. Its allowlist currently ends with investigation/probe and contract-capture fields.
- `orchestrator/pipeline_trace.py:1375` and `:1441` project manifests and allowlisted steps under the shared conversation lifecycle lock.
- `orchestrator/pipeline_trace.py:1512` exports a single locked snapshot. The summary currently shows parent/child refs but has no reused/recomputed resume timeline.
- `orchestrator/pipeline_trace.py:1574` lists trace refs while holding the cross-process conversation lifecycle lock.

### 4.2 Probe-era approval and execution primitives

- `orchestrator/trace_debug.py:900` obtains a source trace's effective conversation/redaction handling under the lifecycle lock.
- `orchestrator/trace_debug.py:915` validates probe ownership and its investigation origin.
- `orchestrator/trace_debug.py:981` prepares a probe and binds exact source/request digests, correction, estimate, expiry, origin, and conversation metadata.
- `orchestrator/trace_debug.py:1048` approves pending state.
- `orchestrator/trace_debug.py:1067` consumes approval atomically, rejects replay, and revalidates source mutation.
- `orchestrator/trace_debug.py:1096` creates a probe only after valid consumption, binds trace/model/tool contexts around the physical call, finalizes every outcome, and verifies the durable manifest.
- The probe implementation also records pre-trace rejection and approval events in the originating investigation trace.

These mechanics are the base to generalize. Chunk 4 must not create a second independent nonce registry or a client-authoritative token scheme.

### 4.3 Risk gate

- `orchestrator/risk_gate.py:725` assigns risk tiers.
- `orchestrator/risk_gate.py:829` evaluates holds, consumes one-time task tokens, and persists Paused state when required.
- Current task tokens have a finite TTL and one-shot semantics.

Resume preparation must call this gate with a server-built capability plan. The client cannot supply `risk_decision` as trusted data.

### 4.4 Production entry points

- `orchestrator/boot.py:9217` wraps `run_pipeline()` and finalizes its trace on every exit.
- `orchestrator/boot.py:9278` begins `_run_pipeline_impl()`; trace creation and context binding occur around `:9341`.
- `orchestrator/boot.py:9394-9440` handles current trace probe/debug CLI control paths.
- `server/server.py:3499` wraps `_pipeline_stream()`; finalization occurs around `:3573`.
- `server/server.py:3591` begins `_pipeline_stream_impl()`; trace creation occurs around `:3650`.
- `server/server.py:3737` handles structured trace-debug requests.
- `server/server.py:7900` parses structured trace-debug data into the normal `/chat` pending-turn path.
- `server/server.py:10451-10525` exposes the current probe prepare/approve/execute routes.

Resume execution must be integrated into both wrappers. Passing a resume payload only through the server route or only through `context_pkg` would leave the other production entry point with different behavior.

### 4.5 Captured context is not yet an executable checkpoint

- `orchestrator/boot.py:7202` and `:7250` assemble Step 2 context and bind turn trace, conversation tag, and tool-event contexts.
- The current `step2-context.json` records diagnostic metadata, including mode identity and mode-text character count.
- The in-memory package returned later in Step 2 contains additional execution state, including the full mode text, configuration name, style, RAG material, web consultation material, deterministic tool results, triage/routing state, and isolation metadata.

Therefore, existing `step2-context.json` files cannot be promoted to resume checkpoints. A new exact checkpoint is required at execution time.

### 4.6 Gear stage topology

- `orchestrator/boot.py:11540` starts Gear 3. Its stages are depth analysis, breadth evaluation, claim-verification preflight, revision, unflagged-claim scan, verifier/revision loop, and final quality gate.
- `orchestrator/boot.py:12236` starts Gear 4. Its stages are paired analysts, paired cross-evaluators, paired claim verification, paired revisers, paired unflagged scans, paired verifier/revision loop, consolidation, formatting, and final quality/recovery passes.
- Gear 4 contains internal fallbacks that can restart Gear 3. Those are valid for an ordinary full run but would violate a later resume boundary.
- `orchestrator/boot.py:11385` and `:11463` perform read-only web verification of flagged and unflagged claims respectively; neither site makes model calls.
- Visual synthesis/review helpers can add model calls and local rendered artifacts.

The resume plan must conservatively include retry maxima and every optional capability reachable from the selected stage.

### 4.7 Trace Walk UI and tests

- `server/static/js/trace-walk.js` maintains request generations/abort state, renders the modal, loads selected steps, pins, investigates, and exports.
- The current action bar has Pin, Investigate, and Export but no resume action.
- `orchestrator/tests/test_trace_walk_ui.py` is a jsdom harness that already covers escaped rendering, exact current-turn synchronization, focus restoration, failed requests, and out-of-order manifest/step/pin responses.
- `orchestrator/tests/test_trace_manifest.py` contains the current manifest, debug, probe, risk, mutation, expiry, and concurrent-consumption coverage.

Chunk 4 UI coverage belongs in the jsdom harness, not in syntax checks alone.

### 4.8 Resume-fatal and output-health anchors re-derived from `origin/main`

The current base has the exact broad-catch and fallback seams that a resume policy must cross. The implementation audit and tests must use these current anchors rather than assume that a helper-level guard is sufficient:

- `orchestrator/boot.py:9915-9943` runs the agentic tool loop; `execute_tool_with_outcome()` is followed by assistant/tool-result injection and another model iteration. `:9958-9970` has a best-effort overrun write.
- `orchestrator/boot.py:10212-10246` defines `_PROVIDER_TRANSPORT_ERROR_MARKERS`; `:10497-10554` defines dispatch-noise stripping; `:10565-10620` defines the complete `_UNHEALTHY_PATTERNS` table; `:10623-10682` implements `_step_output_health()`; `:10989-11032` implements the reviser structural check.
- `orchestrator/boot.py:10820-10841` catches router failures while resolving a fallback; `:11096-11246` owns Supplemental RAG retrieval and resubmission; `:11249-11382` catches both `_call_with_retry()` attempts and advances to a fallback endpoint; `:14150-14191` owns truncation retry; `:14081-14116` owns direct-vendor fallback; `:14692-14710` owns prefer-direct to OpenRouter fallback.
- Gear 3 has verifier exception substitution at `:11944-11953` and quality-gate fail-open at `:12078-12087`. Gear 4 has analyst future handlers at `:12390-12404`, evaluator future handlers at `:12490-12518`, reviser future handlers at `:12641-12662`, verifier future handlers at `:12862-12905`, re-revision future handlers at `:13038-13095`, analyst failure Gear 4-to-Gear 3 fallback at `:12415-12440`, and quality-gate fail-open/repair at `:13451-13585`.
- Reachable web parallel handlers are `orchestrator/claim_verification.py:355-368` and, for ordinary Step 2 only, `orchestrator/web_consultation.py:833-854`. A bound resume policy must propagate through the former; the latter must remain ordinary behavior because resume never runs Step 2.
- The top-level lifecycle wrappers are `orchestrator/boot.py:9217-9275` (`run_pipeline`) and `server/server.py:3499-3588` (`_pipeline_stream`). They may finalize and re-raise ordinary exceptions, but they are not additional converters of the fatal resume-control exception. The shared resume dispatcher invoked by both entry points is the sole converter.
- Existing tests that must be extended rather than replaced include `orchestrator/tests/test_gear4_analyst_recovery.py`, `test_gear4_degradation.py`, `test_quality_gate.py`, `test_verifier_retry.py`, `test_verifier_classifier.py`, `test_reviser_gate.py`, `test_sweep3_silent_failures.py`, and the production-entry-point portions of `test_trace_manifest.py` at the `run_pipeline` and `_pipeline_stream` tests. Their current assertions prove the ordinary fallbacks; Revision 7 adds policy-bound fatal variants and preserves the unbound variants.

## 5. Design

### D1. Default-OFF capability and deterministic routing

Add `ORA_TRACE_RESUME_ENABLED`, parsed by the existing strict environment-flag convention. The default is false.

When false:

- Ordinary Gear 3/4 behavior remains unchanged.
- No resume checkpoint is persisted.
- Browser eligibility returns `FEATURE_DISABLED` and does not expose an active action.
- CLI and structured server requests fail cleanly before approval or trace creation.

The browser uses structured JSON only. The server accepts a `trace_resume` field on a normal `/chat` request only for the execute phase. There is no natural-language parser.

The CLI syntax is deterministic:

```text
/trace-resume prepare <trace_ref> <step_name> [--correction <quoted text>] [--token-ceiling <integer>]
/trace-resume approve <approval_id> <approval_digest> [--risk-token <one-time token>]
/trace-resume cancel <approval_id> <approval_digest>
/trace-resume execute <approval_id> <approval_digest>
```

Parsing uses a real option parser. `--correction` consumes exactly one quoted argument and cannot absorb later options. `--token-ceiling` is an aggregate integer token budget with the unit defined in D6; it is never currency. Correction length is capped at 2,000 Unicode code points and its UTF-8 byte length is also bounded.

### D2. Exact checkpoint persistence

When the flag is enabled, a normal supported Gear 3/4 run writes exact, versioned resume state inside its own trace directory.

Files:

- `resume-checkpoint.json`: immutable static execution state required by every boundary.
- `resume-boundary-<canonical-stage>.json`: immutable state immediately before one canonical stage.
- `resume-capture-errors.jsonl`: append-only, bounded reasons a static or boundary capture was unavailable.

The static checkpoint contains only allowlisted fields:

- Schema and resume-engine version.
- Conversation ID, source trace ref, trace kind, gear, mode, and config name.
- Complete full mode text used for execution and its digest.
- Provider/model routing policy, endpoint identity without credentials, token limits, and approved fallback policy.
- Complete text-only Step 2 execution inputs needed by the stage dispatcher.
- Source contract fingerprint when present.
- Relevant code/prompt engine fingerprint.
- Redaction level and checkpoint-size accounting.
- A declaration that no image, attachment, state-changing tool dependency, or unsupported external dependency is present.

The static checkpoint schema is concrete and closed. Unknown keys or a missing key make it unavailable:

| Object | Required typed fields |
|---|---|
| `identity` | `conversation_id: string`, `source_trace_ref: string`, `source_trace_kind: enum`, `gear: 3\|4` |
| `prompt` | `cleaned_prompt: string`, `raw_prompt: string`, `natural_prompt: string` |
| `mode` | `name: string`, `text: string`, `text_digest: sha256`, `contract_fingerprint: sha256\|null` |
| `configuration` | Closed `ModelExecutionPolicy` defined below |
| `execution_inputs` | Closed `ExecutionTextInputs` defined below; these are the already-rendered strings consumed by the shared stage runner |
| `provenance` | Closed `InputProvenanceDigests` defined below; diagnostic Step 2 objects are referenced only by fixed digests and are not reconstructed |
| `media` | `images: []`, `attachments: []`, `visual_output_allowed: false` |
| `engine` | `checkpoint_schema_version: integer`, `stage_map_version: integer`, `resume_engine_fingerprint: sha256`, `physical_call_policy_fingerprint: sha256` |
| `limits` | `checkpoint_bytes: integer`, `captured_at: RFC3339 string` |

The static checkpoint contains no generic object or untyped array. Its nested schemas are:

`EndpointIdentity`:

| Field | Type and bound |
|---|---|
| `engine` | enum `openai-compatible`, `anthropic`, `claude-code`, `ollama`, `mlx` |
| `provider` | safe identifier, 1-128 bytes |
| `model` | string, 1-256 bytes |
| `scheme` | enum `https`, `http`, `local-process` |
| `host` | credential-safe normalized host, 1-255 bytes, or literal `local` for local-process |
| `port` | integer 1-65535 or null |
| `path` | string at most 1 KiB, beginning `/`, with no userinfo, query, or fragment |
| `digest` | SHA-256 over canonical object with this field omitted |

`ModelParameters`:

| Field | Type and bound |
|---|---|
| `max_output_tokens` | integer 1-10,000,000 |
| `temperature` | finite number 0-2 or null |
| `top_p` | finite number greater than 0 and at most 1, or null |
| `seed` | signed 64-bit integer or null |
| `stop` | ordered array of at most 16 strings, each at most 1 KiB |
| `timeout_seconds` | integer 1-3600 |
| `digest` | SHA-256 |

Any current provider parameter outside this schema makes the trace non-resumable; it is not dropped or placed in an extension object.

`PhysicalAttemptPolicy`:

| Field | Type and bound |
|---|---|
| `endpoint` | `EndpointIdentity` |
| `parameters` | `ModelParameters` |
| `attempt_role` | enum `primary`, `same-endpoint-retry`, `truncation-retry`, `provider-fallback` |
| `ordinal` | integer 1-16, contiguous in policy order |
| `condition` | closed `PhysicalAttemptCondition` |
| `endpoint_binding` | enum `explicit`, `same-as-previous`; primary/fallback are explicit, same-endpoint retry must use same-as-previous |
| `digest` | SHA-256 |

`PhysicalAttemptCondition`:

| Field | Type and bound |
|---|---|
| `trigger` | enum `initial`, `unhealthy-output`, `truncation`, `transport-error`, `http-status`, `direct-unavailable`, `model-unavailable` |
| `previous_ordinal` | integer 1-15 or null; null only for `initial` |
| `http_statuses` | ordered unique array of at most 16 integers 400-599; nonempty only for `http-status` |
| `unhealthy_reasons` | ordered unique subset of `null`, `empty`, `short`, `refusal`, `clarification`, `malformed-verifier`, `malformed-reviser`, `dispatch-error`; nonempty only for `unhealthy-output` |
| `max_uses_per_logical_invocation` | integer 1-4 |
| `digest` | SHA-256 |

For `endpoint_binding: same-as-previous`, the serialized endpoint remains present and its digest must equal the immediately previous endpoint. This records the effective endpoint while mechanically proving same-endpoint retry. A provider fallback must use `explicit` and a different endpoint/provider identity unless the production configuration explicitly identifies a separate model on the same host.

`UnhealthyOutputPolicy`:

| Field | Type and bound |
|---|---|
| `policy_version` | positive integer |
| `minimum_response_characters` | integer 0-4096, copied from the effective production threshold; current `_step_output_health()` default is 30 |
| `dispatch_noise_contract` | exact versioned `DispatchNoiseContract` below |
| `health_marker_contract` | exact versioned `HealthMarkerContract` below; no implementation-defined marker additions |
| `verifier_validator` | literal `verifier-envelope-v1` for `step_name == "verifier"`, otherwise null |
| `reviser_validator` | literal `reviser-envelope-v1` for `step_name == "reviser"`, otherwise null |
| `verifier_minimum_response_characters` | integer 0-4096; current validator inherits `minimum_response_characters` |
| `reviser_minimum_envelope_characters` | integer 0-4096; current `_reviser_output_structural_check()` value is 200 |
| `reviser_minimum_draft_body_characters` | integer 0-4096; current `_reviser_output_structural_check()` value is 50 |
| `retry_empty` | Boolean |
| `retry_null` | Boolean |
| `retry_short` | Boolean |
| `retry_refusal` | Boolean |
| `retry_clarification` | Boolean |
| `retry_malformed_verifier` | Boolean |
| `retry_malformed_reviser` | Boolean |
| `retry_dispatch_error` | Boolean |
| `digest` | SHA-256 |

`DispatchNoiseContract` is versioned because health is evaluated after `_strip_dispatch_noise()`, not on the raw provider string:

| Field | Exact value in `dispatch-noise-v1` |
|---|---|
| `prefixes` | ordered case-sensitive array: `[model switch]`, `[Tool:`, `[Tool results]`, `[Depth model error`, `[Breadth model error`, `[Evaluation error`, `[Revision error`, `[Re-revision error`, `Playwright session error`, `Claude responded:` |
| `playwright_call_log_prefixes` | ordered array: `Call log:`, `- navigating to`, `- waiting for`, `- locator(`, and any line beginning `-` containing `navigat` |
| `normalization` | remove leading blank/noise lines, remove the Playwright call-log trailer only after a leading `Playwright session error`, then trim surrounding whitespace; no other content mutation |
| `digest` | SHA-256 over this closed object |

`HealthMarkerContract` is the closed, case-insensitive substring mapping used by `health-marker-v1`. The implementation must persist this mapping or an exact contract digest; it may not reconstruct it from a smaller generic "provider error" list:

| Category | Exact ordered markers from current `_UNHEALTHY_PATTERNS` and `_PROVIDER_TRANSPORT_ERROR_MARKERS` |
|---|---|
| `clarification` | `your message got cut off`; `your message appears to be cut off`; `your prompt was cut off`; `your query appears to be missing`; `i'm missing the actual query`; `did you mean to paste`; `did you mean to send`; `looks like the prompt is`; `looks like a partial` |
| `refusal` | `i'm not seeing the`; `i don't see the`; `could you share`; `could you paste`; `could you provide`; `i need more context`; `i need more information`; `i need clarification`; `what would you like me to`; `what do you actually want` |
| `pipeline-dispatch-error` | `[depth model error`; `[breadth model error`; `[evaluation error`; `[revision error`; `[re-revision error`; `[mlx model not found`; `[error] unsupported api service`; `[error] unsupported engine`; `[error] unknown endpoint type`; `[no response]`; `[tools unavailable`; `[tool error —` |
| `provider-transport-error` | `anthropic.apistatuserror`; `anthropic.ratelimiterror`; `anthropic.apiconnectionerror`; `anthropic.internalservererror`; `openai.ratelimiterror`; `openai.apiconnectionerror`; `openai.internalservererror`; `context_length_exceeded`; `invalid_request_error`; `service_unavailable`; `503 service unavailable`; `502 bad gateway`; `504 gateway timeout`; `529 overloaded`; `overloaded_error`; `model is currently overloaded`; `request timed out`; `connection refused`; `connection reset` |
| `provider-wrapper-error` | `error calling claude api`; `error calling openai api`; `error calling gemini api`; `error calling openrouter api`; `error calling local model`; `error calling mlx model` |
| `provider-input-error` | `anthropic.badrequesterror`; `openai.apierror`; `openai.badrequesterror`; `google.api_core.exceptions`; `googleapi error`; `gemini api error` |
| `structured-error` | `{"error":`; `{"type":"error"`; `error_type:`; `error_code:`; `content_filter` |
| `browser-dispatch-error` | `failed to fetch from` |
| `source_order` | The combined refusal/clarification markers retain the current tuple order: `your message got cut off`, `your message appears to be cut off`, `your prompt was cut off`, `your query appears to be missing`, `i'm missing the actual query`, `i'm not seeing the`, `i don't see the`, `could you share`, `could you paste`, `could you provide`, `i need more context`, `i need more information`, `i need clarification`, `what would you like me to`, `what do you actually want`, `did you mean to paste`, `did you mean to send`, `looks like the prompt is`, `looks like a partial`; dispatch/provider categories then retain their current tuple order above |
| `digest` | SHA-256 over the category order, category names, exact arrays, and `source_order` above |

The exact matcher order is the combined source tuple order above, followed by `pipeline-dispatch-error`, `provider-input-error`, `structured-error`, `browser-dispatch-error`, and `provider-transport-error` (whose wrapper-error markers are at the end of the provider tuple). A lower-priority category never replaces an earlier match. Matching is case-insensitive substring matching, exactly as the current lower-cased `_step_output_health()` implementation performs. The current implementation emits one combined `refusal/clarification pattern` diagnostic; the persisted contract records the closed typed subcategory without changing the unhealthy boolean or marker match.

A provider-native refusal that does not match one of the exact current markers remains subject to the current null/empty/short/verifier/reviser checks; implementation may add a new refusal marker only by bumping `health-marker-v1` and the resume policy version. The partition above is typed policy evidence for the existing combined source tuple, not a new refusal heuristic.

`_VERIFIER_EXPLICIT_BROKEN_LINE_PREFIXES` and `_VERIFIER_GENERIC_BROKEN_MARKERS` are deliberately not added to this health-marker table: they belong to `_verifier_broken()`'s downstream ordinary-output classification, not `_step_output_health()`'s retry health. Fatal resume-control errors are separate from both contracts.

`verifier-envelope-v1` is a closed validator matching `_extract_structured_verdict()` and `_step_output_health()`:

- Input is the normalized output after `dispatch-noise-v1` and the minimum-character check.
- The last line-anchored verdict wins. Accepted lines are `VERDICT: PASS`, `VERDICT: FAIL`, `VERDICT: BROKEN`, `VERIFIED`, `VERIFIED WITH CORRECTIONS`, and `VERIFICATION FAILED`, with the current whitespace/case/optional emphasis and `:`/`-`/`—` separators.
- They normalize to `PASS`, `FAIL`, or `BROKEN`. No matching line is `malformed-verifier`, even if prose contains `verified`.
- A matching dispatch/provider marker is classified as `dispatch-error` before this validator, exactly as `_step_output_health()` checks `_UNHEALTHY_PATTERNS` before the verifier branch. The downstream `_verifier_broken()` classifier remains separate and must not swallow a fatal resume-control exception.

`reviser-envelope-v1` is the required versioned companion to the verifier validator and matches `_reviser_output_structural_check()`:

- After normalization, total output length must be at least 200 characters.
- The exact case-sensitive literal `## REVISED DRAFT` must occur. The body begins immediately after its first occurrence.
- The body ends immediately before the first literal `## CHANGELOG` after that header, or at end of text when no changelog occurs. H2 headings inside the body are retained.
- The trimmed body must contain at least 50 characters. Failure is `malformed-reviser`; no fallback envelope is considered healthy by the validator.

Health classification and retry mapping are closed and ordered exactly as follows. The matcher iterates markers in `source_order` (the tuple order above); the precedence column assigns the typed reason after the first match. No marker overlaps between refusal and clarification, so the typed-reason precedence ordering between them is observational rather than behavioral. Matching is a single linear scan; there is no separate precedence pass.

| Precedence | Condition on normalized output | Typed reason | Retry condition |
|---:|---|---|---|
| 1 | `text is None` | `null` | `retry_null` |
| 2 | normalized output is empty | `empty` | `retry_empty` |
| 3 | normalized output length is below `minimum_response_characters` | `short` | `retry_short` |
| 4 | first matching exact marker is in the `refusal` category | `refusal` | `retry_refusal` |
| 5 | first matching exact marker is in the `clarification` category | `clarification` | `retry_clarification` |
| 6 | first matching exact marker is in any dispatch/provider category | `dispatch-error` | `retry_dispatch_error` |
| 7 | active verifier validator finds no accepted verdict line | `malformed-verifier` | `retry_malformed_verifier` |
| 8 | active reviser validator rejects the envelope/body | `malformed-reviser` | `retry_malformed_reviser` |
| 9 | none of the above | healthy | no retry |

Current `_call_with_retry()` retries once after every unhealthy result it receives, so every route that actually uses that wrapper persists all eight retry booleans as `true`, and its ordered `PhysicalAttemptCondition` must include each reachable reason. A route that has a false flag is allowed only when the current production call site demonstrably does not invoke `_call_with_retry()` for that role; it is not a default for resumed execution. A retry is an independent physical attempt and is subject to the fatal-control checks below before dispatch.

`LogicalCallKey`:

| Field | Type and bound |
|---|---|
| `canonical_stage` | one canonical Gear 3/Gear 4 stage enum from D3 |
| `role` | enum `depth-analyst`, `breadth-analyst`, `breadth-evaluator`, `cross-evaluator`, `claim-extractor`, `reviser`, `unflagged-claim-scanner`, `verifier`, `failure-reviser`, `quality-gate`, `quality-reviser`, `consolidator`, `formatter`, `reconsolidator`, `reformatter` |
| `slot` | enum `single`, `a`, `b` |
| `digest` | SHA-256 |

`LogicalCallPolicy`:

| Field | Type and bound |
|---|---|
| `key` | `LogicalCallKey` |
| `logical_retry_type` | enum `none`, `verifier-cycle`, `quality-cycle`, `format-leak-cycle`, `structural-rerevision` |
| `max_logical_invocations` | integer 1-16; total call-site invocations including initial |
| `effective_output_token_cap` | integer 1-10,000,000; must equal each permitted attempt's effective cap unless that attempt is the explicitly captured truncation expansion |
| `unhealthy_output_policy` | closed `UnhealthyOutputPolicy` |
| `physical_attempts` | ordered array of 1-16 `PhysicalAttemptPolicy` objects |
| `fallback_scope` | literal `same-logical-call`; a fallback cannot change stage, role, or slot |
| `digest` | SHA-256 |

`ModelExecutionPolicy`:

| Field | Type and bound |
|---|---|
| `config_name` | string, 1-256 bytes |
| `style_instructions` | exact string or null, at most 256 KiB |
| `logical_calls` | ordered array of 1-64 `LogicalCallPolicy` objects, unique by `(canonical_stage, role, slot)` |
| `prefer_direct` | Boolean |
| `allow_truncation_retry` | Boolean |
| `credential_source` | literal `runtime-only` |
| `policy_version` | positive integer |
| `digest` | SHA-256 |

The stage runner may resolve model policy only by exact `(canonical_stage, role, slot)`. It cannot take the last call, a stage-wide default, or a similarly named route. There is exactly one `LogicalCallPolicy` per key. Same-endpoint unhealthy-output retries and physical fallbacks remain inside that one policy and run only when their closed condition matches the immediately preceding attempt. Estimates and hard ceilings include every conditionally reachable physical attempt at its maximum permitted use.

Required route matrix:

| Gear stage | Required logical keys |
|---|---|
| `g3-analysis` | `(depth-analyst, single)` |
| `g3-breadth` | `(breadth-evaluator, single)` |
| `g3-claim-check` | `(claim-extractor, single)` only when the current production call site is enabled; otherwise the policy records no model route and the closed web plan governs |
| `g3-revision` | `(reviser, single)` |
| `g3-unflagged-scan` | `(unflagged-claim-scanner, single)` |
| `g3-verification` | `(verifier, single)`, `(failure-reviser, single)` |
| `g3-final-quality` | `(quality-gate, single)`, `(quality-reviser, single)` |
| `g4-analysis` | `(depth-analyst, a)`, `(breadth-analyst, b)` |
| `g4-cross-evaluation` | `(cross-evaluator, a)`, `(cross-evaluator, b)` |
| `g4-claim-check` | `(claim-extractor, a)` and `(claim-extractor, b)` only for enabled production model call sites; otherwise closed web plans only |
| `g4-revision` | `(reviser, a)`, `(reviser, b)` |
| `g4-unflagged-scan` | `(unflagged-claim-scanner, a)`, `(unflagged-claim-scanner, b)` |
| `g4-verification` | `(verifier, a)`, `(verifier, b)`, `(failure-reviser, a)`, `(failure-reviser, b)` |
| `g4-consolidation` | `(consolidator, single)` |
| `g4-formatting` | `(formatter, single)` with its one policy carrying `logical_retry_type: format-leak-cycle` and the total invocation bound |
| `g4-final-quality` | `(quality-gate, single)`, `(reconsolidator, single)`, `(reformatter, single)` |

At checkpoint capture, this matrix is generated from the effective production Gear configuration and compared with the concrete call-site registry extracted during the shared-runner refactor. A missing, duplicate, extra, wrong-slot, wrong-stage, wrong-role, or conditionally reachable route makes the affected boundary unavailable. Focused configuration fixtures cover every production Gear 3 and Gear 4 config, direct/prefer-direct/fallback combinations, truncation expansion, and disabled optional call sites. The checkpoint digest binds the complete route matrix and ordered physical chains.

`ExecutionTextInputs`:

| Field | Type and bound |
|---|---|
| `source_request` | exact user request string, at most 2 MiB UTF-8 |
| `stage3_user_message` | exact fully rendered user message consumed by the first Gear stage, at most 4 MiB |
| `downstream_context_text` | exact fully rendered context reused by downstream prompt builders, at most 4 MiB |
| `mode_text` | exact complete mode text, at most 2 MiB |
| `style_text` | exact style text or empty string, at most 256 KiB |
| `human_correction_text` | literal empty string for eligible source chat traces |
| `digest` | SHA-256 |

The shared Gear runner is refactored so it consumes only these rendered strings and the closed model policy. Raw `rag_selection`, `rag_isolation`, `triage`, `pre_routing`, `web_chunks`, `deterministic_tool_results`, inferred-item objects, and other Step 2 dictionaries are never loaded by resumed stages. During an ordinary full run, current Step 2 objects are rendered once into the exact strings above before the Step 3 boundary. If any later stage still consults a raw object after refactor, checkpoint capture fails and that code path is not eligible until it has a closed rendering contract.

`InputProvenanceDigests`:

| Field | Type and meaning |
|---|---|
| `step2_context_artifact_digest` | SHA-256 or null |
| `rag_rendered_text_digest` | SHA-256 of the exact RAG contribution or null |
| `web_rendered_text_digest` | SHA-256 of the exact Step 2 web contribution or null |
| `deterministic_tool_rendered_text_digest` | SHA-256 of the exact tool-results contribution or null |
| `triage_rendered_text_digest` | SHA-256 of the exact triage contribution or null |
| `routing_rendered_text_digest` | SHA-256 of the exact routing contribution or null |
| `inference_rendered_text_digest` | SHA-256 of the exact inferred-item/correction contribution or null |
| `execution_input_composition_digest` | SHA-256 of canonical `{execution_inputs_digest, ordered_component_digests}` |
| `digest` | SHA-256 over this closed object |

These digests prove which rendered components formed `stage3_user_message` and `downstream_context_text`; they are not references that require mutable source objects at resume time. `ordered_component_digests` is the fixed seven-field order shown above, including null placeholders. Static checkpoint objects use the same canonical UTF-8 JSON rules defined in D3.2. The top-level `resume-checkpoint.json` has `checkpoint_digest`, computed over the complete checkpoint with only that field omitted. Capture recomputes the rendered-string composition digest and top-level digest; load verifies every nested digest and both aggregate digests. Headers, cookies, environment values, credential locations, API keys, and URL userinfo are forbidden in every checkpoint field.

Each boundary file contains a stage-specific allowlisted state object, the static-checkpoint digest, digests of every source artifact/state component it uses, the canonical stage, and the exact list of source step names represented by that state.

Capture rules:

- Capture is complete or failed. Executable text is never truncated, summarized, or silently redacted.
- Credentials, authorization headers, cookies, API keys, and environment secrets are never included. If exact execution would require one of these values in the checkpoint, capture fails; providers obtain credentials normally at execution time.
- If a secret-redaction pass would alter an executable field, capture fails rather than preserving an altered contract.
- Image-, attachment-, or visual-dependent state is `NOT_RESUMABLE` in this release.
- Each checkpoint file is limited to 8 MiB and total resume checkpoint material per trace is limited to 64 MiB. Crossing either bound records an explicit capture error and leaves that boundary unavailable.
- Writes use safe direct-child/no-follow primitives, atomic temp-file replacement, and the conversation lifecycle lock. No lock is held across model or web calls.
- A boundary is written before its stage begins, after every prerequisite state component exists. A crash can therefore leave earlier boundaries usable without implying that later ones exist.
- The manifest records only checkpoint schema, capture status, available canonical stages, aggregate bytes, and digests. Raw checkpoint content is not included in browser manifest or step projections.
- Stealth execution writes no trace directory and therefore writes no checkpoint. Eligibility for a missing/stealth ref is `TRACE_NOT_FOUND`; there is no fallback lookup or stealth bypass.

Legacy traces, traces captured while the flag was off, and traces with incomplete checkpoints remain walkable and exportable but show `NOT_RESUMABLE` with an exact reason.

Resume execution does not run the checkpoint writer. A `resume` trace records its direct `chat-gear3`/`chat-gear4` source, reused source step refs/digests, recomputed artifacts, and correction, but emits no `resume-checkpoint.json` or boundary files. Therefore every reused upstream item always points directly to the original eligible chat trace, and no correction can be mistaken for source checkpoint input. Trace Walk disables "Re-run from here" on `resume` traces with `CHAINED_RESUME_UNSUPPORTED`. Chained production is deferred to a later design that defines correction composition and multi-generation evidence ownership.

### D3. Canonical stage map

Resume begins at a canonical stage and recomputes that stage through the end. UI step names map mechanically to a stage; there is no inferred nearest step.

Gear 3 canonical stages:

| Canonical stage | Visible source steps that select it | First recomputed work |
|---|---|---|
| `g3-analysis` | depth-analysis Step 3 | Depth analysis |
| `g3-breadth` | breadth-evaluation Step 4 | Breadth evaluation |
| `g3-claim-check` | claim-verification Step 4.5 | Claim-verification preflight |
| `g3-revision` | revision Step 5 | Revision |
| `g3-unflagged-scan` | unflagged-claim Step 5.5 | Unflagged scan |
| `g3-verification` | any verifier/revision cycle Step 6 | Verifier cycle 1 |
| `g3-final-quality` | any final-quality/revision Step 6.5 | Final-quality pass 1 |

Gear 4 canonical stages:

| Canonical stage | Visible source steps that select it | First recomputed work |
|---|---|---|
| `g4-analysis` | either paired analyst Step 3 | Both analysts |
| `g4-cross-evaluation` | either paired evaluator Step 4 | Both cross-evaluators |
| `g4-claim-check` | either paired Step 4.5 | Both claim checks |
| `g4-revision` | either paired reviser Step 5 | Both revisers |
| `g4-unflagged-scan` | either paired Step 5.5 | Both scans |
| `g4-verification` | any paired verifier/revision cycle Step 6 | Both verifier streams at cycle 1 |
| `g4-consolidation` | Step 7 | Consolidation |
| `g4-formatting` | Step 8 | Formatting |
| `g4-final-quality` | any Step 8.6 quality/recovery step | Quality pass 1 |

The implementation derives the concrete source-step mapping from the current exact step-name constants and tests every mapped name. `step-health`, debug/probe control artifacts, cost logs, manifests, model-call logs, and unknown `step*` names are not resume boundaries.

Selecting one member of a paired stage recomputes the complete pair. Selecting a later retry/cycle restarts that canonical stage at cycle 1. The prepare response states this expansion before approval.

#### D3.1 Boundary-state contract

Every boundary file has this closed envelope and no additional keys:

```text
schema_version: integer
gear: 3 | 4
canonical_stage: canonical-stage enum
capture_point: literal "before-stage"
static_checkpoint_digest: sha256
source_artifacts: ordered array<BoundaryArtifactRef>
state_schema: stage-state-schema enum
state: exact state object selected by state_schema
retry_state: NoRetryState | FreshRetryState
web_state: NoWebBoundaryState | PendingWebBoundaryState
fallback_state: FallbackState
boundary_digest: sha256
```

`BoundaryArtifactRef`:

| Field | Type and bound |
|---|---|
| `trace_ref` | exact source `chat-gear3`/`chat-gear4` ref; must equal the checkpoint source |
| `step_name` | safe manifest-listed `step*` stem, at most 128 bytes |
| `artifact_kind` | enum `json`, `markdown`, `health` |
| `byte_length` | integer 0-8 MiB |
| `artifact_digest` | SHA-256 of the exact regular non-symlink file bytes |
| `digest` | SHA-256 of this object |

The ordered array has at most 128 unique `(step_name, artifact_kind)` entries. Every `source_steps` value embedded in typed state must have a matching artifact ref; every artifact ref must be consumed by a typed state value or named provenance field. Extras and omissions fail capture.

`NoRetryState` is exactly `{ "kind": "none", "digest": <sha256> }`.

`FreshRetryState` is exactly `{ "kind": "fresh", "plan": <RetryPlan>, "digest": <sha256> }`. Its plan has `attempts_completed: 0`, `next_attempt_number: 1`, and empty history.

`NoWebBoundaryState` is exactly `{ "kind": "none", "digest": <sha256> }`. It carries no health or source step because the selected stage has no new web action.

`PendingWebBoundaryState` is exactly:

```text
kind: literal "pending"
web_kind: "claim-verification" | "unflagged-claim-scan"
slot: "single" | "a" | "b" | "paired"
max_queries: integer 1-64
max_evidence_records: integer 1-256
read_only: literal true
digest: sha256
```

It intentionally has no health or source step because capture occurs before the web stage. Completed prior web output appears only as a typed `WebStageState` or `PairedWebStageState` inside `state`.

`boundary_digest` is SHA-256 over the complete canonical envelope with only `boundary_digest` omitted. The outer schema validator chooses the permitted state/retry/web variants from the canonical stage table below; a well-typed but wrong variant is rejected.

Common invariants:

- `capture_point` is always immediately after the previous stage's output and health write succeed and immediately before the first model or web request of the named stage.
- The boundary contains the exact live values consumed by the current stage runner, not values re-parsed later from diagnostic Markdown.
- Every required string is preserved exactly. Empty and missing are different.
- Every represented source artifact has a digest. Extra or unknown state fields fail schema validation.
- A retrying canonical stage always starts at attempt/cycle 1. A boundary never captures a partially completed retry as a resumable entry point.
- A later boundary may include completed retry history as evidence, but its live retry counter is reset for the later stage only.
- Paired Gear 4 fields are keyed by stable `a` and `b` slots. Both must be present unless the current ordinary pipeline has already performed a documented full-run fallback and invalidated all Gear 4 boundaries.
- Web records contain exact query text, returned evidence records, errors, provider identity, and timestamps, but no credentials. Later stages reuse this captured evidence; only resuming at or before a web stage performs new web calls.

Each stage `state` object contains exactly `kind`, the fields listed below, and `digest`. The `kind` literal equals `state_schema`. No catch-all metadata or extension object is permitted.

| Canonical stage / `state_schema` | Exact typed state fields | Required retry variant | Required web variant |
|---|---|---|---|
| `g3-analysis-state` | none | `NoRetryState` | `NoWebBoundaryState` |
| `g3-breadth-state` | `depth_analysis: StageText` | `NoRetryState` | `NoWebBoundaryState` |
| `g3-claim-check-state` | `depth_analysis: StageText`, `breadth_evaluation: StageText` | `NoRetryState` | `PendingWebBoundaryState(single, claim-verification)` |
| `g3-revision-state` | `depth_analysis: StageText`, `breadth_evaluation: StageText`, `claim_verification: WebStageState` | `NoRetryState` | `NoWebBoundaryState` |
| `g3-unflagged-scan-state` | `depth_analysis: StageText`, `breadth_evaluation: StageText`, `claim_verification: WebStageState`, `revised_draft: StageText` | `NoRetryState` | `PendingWebBoundaryState(single, unflagged-claim-scan)` |
| `g3-verification-state` | `depth_analysis: StageText`, `breadth_evaluation: StageText`, `claim_verification: WebStageState`, `revised_draft: StageText`, `unflagged_scan: WebStageState` | `FreshRetryState(verifier-cycle)` | `NoWebBoundaryState` |
| `g3-final-quality-state` | `depth_analysis: StageText`, `breadth_evaluation: StageText`, `claim_verification: WebStageState`, `unflagged_scan: WebStageState`, `verified_draft: StageText`, `verification_history: AttemptHistory` | `FreshRetryState(quality-cycle)` | `NoWebBoundaryState` |
| `g4-analysis-state` | none | `NoRetryState` | `NoWebBoundaryState` |
| `g4-cross-evaluation-state` | `analyses: PairedStageText` | `NoRetryState` | `NoWebBoundaryState` |
| `g4-claim-check-state` | `analyses: PairedStageText`, `evaluations: PairedStageText` | `NoRetryState` | `PendingWebBoundaryState(paired, claim-verification)` |
| `g4-revision-state` | `analyses: PairedStageText`, `evaluations: PairedStageText`, `claim_verification: PairedWebStageState` | `NoRetryState` | `NoWebBoundaryState` |
| `g4-unflagged-scan-state` | `analyses: PairedStageText`, `evaluations: PairedStageText`, `claim_verification: PairedWebStageState`, `revisions: PairedStageText` | `NoRetryState` | `PendingWebBoundaryState(paired, unflagged-claim-scan)` |
| `g4-verification-state` | `analyses: PairedStageText`, `evaluations: PairedStageText`, `claim_verification: PairedWebStageState`, `revisions: PairedStageText`, `unflagged_scans: PairedWebStageState` | `FreshRetryState(verifier-cycle)` | `NoWebBoundaryState` |
| `g4-consolidation-state` | `analyses: PairedStageText`, `evaluations: PairedStageText`, `claim_verification: PairedWebStageState`, `unflagged_scans: PairedWebStageState`, `verified_revisions: PairedStageText`, `verification_history_a: AttemptHistory`, `verification_history_b: AttemptHistory` | `NoRetryState` | `NoWebBoundaryState` |
| `g4-formatting-state` | `consolidated_draft: StageText` | `FreshRetryState(format-leak-cycle)` | `NoWebBoundaryState` |
| `g4-final-quality-state` | `analyses: PairedStageText`, `evaluations: PairedStageText`, `claim_verification: PairedWebStageState`, `unflagged_scans: PairedWebStageState`, `verified_revisions: PairedStageText`, `verification_history_a: AttemptHistory`, `verification_history_b: AttemptHistory`, `consolidated_draft: StageText`, `formatted_draft: StageText`, `formatting_history: AttemptHistory` | `FreshRetryState(quality-cycle)` | `NoWebBoundaryState` |

Every row is a closed schema: the serialized state object contains its literal `kind`, exactly the explicitly typed fields in that row, and `digest`. Every resumable stage requires `FallbackState.status: "none"`.

Gear 3 state table:

| Boundary | Required state before stage | Retry/web/fallback invariants | Output that must exist before the next boundary |
|---|---|---|---|
| `g3-analysis` | Static checkpoint only | No retry state; no web state | `depth_analysis: string` plus Step 3 health |
| `g3-breadth` | `depth_analysis` | No retry state; no web state | `breadth_evaluation: string` plus Step 4 health |
| `g3-claim-check` | `depth_analysis`, `breadth_evaluation` | `PendingWebBoundaryState(single, claim-verification)`; approved read-only web ceiling applies | `claim_verification` with exact queries/evidence/errors plus Step 4.5 health |
| `g3-revision` | `depth_analysis`, `breadth_evaluation`, complete `claim_verification` | No live retry counter | `revised_draft: string` plus Step 5 health |
| `g3-unflagged-scan` | Prior analysis/evaluation/evidence and `revised_draft` | Model/read-only-web ceilings plus `PendingWebBoundaryState(single, unflagged-claim-scan)` | `unflagged_scan` with exact model findings, queries/evidence/errors plus Step 5.5 health |
| `g3-verification` | Prior evidence and `revised_draft`, complete `unflagged_scan` | Fresh `RetryPlan` with total `max_attempts = MAX_VERIFY_CYCLES + 1`; empty verifier/revision history | `verified_draft`, ordered verifier/revision history, terminal verifier result, Step 6 health |
| `g3-final-quality` | `verified_draft`, verifier/revision history, analysis/evaluation/evidence needed by the existing repair prompt | Fresh quality `RetryPlan`; final-reviser history empty | `final_draft`, quality/revision history, scrub result, Step 6.5 health |

Gear 4 state table:

| Boundary | Required state before stage | Retry/web/fallback invariants | Output that must exist before the next boundary |
|---|---|---|---|
| `g4-analysis` | Static checkpoint only | Empty paired slots; fallback state `none` | `analyses.a` and `analyses.b`, paired health |
| `g4-cross-evaluation` | Complete `analyses.a/b` | Empty evaluator slots; fallback state `none` | `evaluations.a` and `evaluations.b`, paired health |
| `g4-claim-check` | Complete analyses and evaluations | `PendingWebBoundaryState(paired, claim-verification)`; approved read-only web ceiling applies | `claim_verification.a/b` with exact queries/evidence/errors, paired health |
| `g4-revision` | Analyses, evaluations, and claim verification for both slots | Empty reviser slots | `revisions.a` and `revisions.b`, paired health |
| `g4-unflagged-scan` | Prior paired state and `revisions.a/b` | Model/web ceilings plus `PendingWebBoundaryState(paired, unflagged-claim-scan)` | `unflagged_scans.a/b`, paired health |
| `g4-verification` | Prior paired evidence and revisions | Fresh per-slot `RetryPlan`; `max_attempts` equals the actual permitted Gear 4 loop-body count, empty verifier/revision histories | `verified_revisions.a/b`, ordered per-slot histories and terminal results, paired health |
| `g4-consolidation` | Verified revisions and all evidence consumed by the current consolidator | No retry state; external-consolidation mode must be false | `consolidated_draft`, Step 7 health |
| `g4-formatting` | `consolidated_draft`, exact mode/style formatting inputs | Fresh formatting/leak `RetryPlan` with total attempts | `formatted_draft`, ordered formatting/leak history, Step 8 health |
| `g4-final-quality` | Consolidated and formatted drafts plus exact upstream repair inputs | Fresh quality `RetryPlan` with total attempts; recovery history empty | `final_draft`, quality/reconsolidation/reformat history, scrub result, Step 8.6 health |

Fallback invariants:

- Ordinary full-run resilience before Gear dispatch records the effective gear in the static checkpoint.
- If an ordinary Gear 4 run falls back to full Gear 3 after any Gear 4 boundary was written, all Gear 4 boundaries are marked invalid in manifest checkpoint metadata and a capture-error event records the transition. The Gear 3 path writes a fresh Gear 3 static checkpoint/boundaries and final eligibility follows finalized kind `chat-gear3`.
- Resume execution never uses ordinary Gear 4-to-Gear 3 fallback. An attempted fallback ends the resume `error` before crossing the approved boundary.
- External consolidation and any early-return path that does not satisfy the table's next-boundary state leave later boundaries unavailable.

#### D3.2 Closed nested schemas, bounds, and digests

Boundary state does not embed arbitrary Python dictionaries. Every named payload in D3.1 uses one of the following closed JSON schemas. Unless a smaller field limit is stated, any string is at most 1 MiB UTF-8, any array has at most 256 entries, and nesting is limited to these declared objects. The existing 8 MiB per-file and 64 MiB per-trace limits remain hard aggregate ceilings.

Canonical encoding for every digest is UTF-8 JSON with sorted object keys, no insignificant whitespace, Unicode preserved, finite JSON numbers only, and array order preserved. Each object's `digest` is SHA-256 over that object with its own `digest` field omitted. The boundary envelope also has `boundary_digest`, computed over the complete envelope with only `boundary_digest` omitted. On load, all leaf/object digests, source artifact digests, static checkpoint digest, and boundary digest must match.

`StageHealth`:

| Field | Type and bound |
|---|---|
| `execution_status` | enum `completed`, `error`, `skipped` |
| `structural_status` | enum `pass`, `fail`, `unknown` |
| `semantic_status` | enum `pass`, `fail`, `unknown` |
| `reason_codes` | ordered array of at most 32 strings, each at most 128 bytes |
| `source_step` | safe manifest-listed `step*` stem, at most 128 bytes |
| `recorded_at` | RFC3339 UTC string |
| `digest` | SHA-256 |

`StageText` for analysis, evaluation, revision, consolidation, formatting, and final draft values:

| Field | Type and bound |
|---|---|
| `role` | enum `analysis`, `evaluation`, `revision`, `consolidation`, `formatting`, `final-draft` |
| `text` | exact string, at most 2 MiB UTF-8 |
| `source_steps` | ordered array of 1-16 safe manifest-listed stems |
| `health` | `StageHealth` |
| `digest` | SHA-256 |

`PairedStageText`:

| Field | Type and bound |
|---|---|
| `a` | `StageText`; required and role-compatible |
| `b` | `StageText`; required and role-compatible |
| `pair_order` | exactly `["a", "b"]` |
| `digest` | SHA-256 |

`StageError`:

| Field | Type and bound |
|---|---|
| `code` | uppercase safe token, at most 128 bytes |
| `message` | redacted non-secret string, at most 64 KiB |
| `retryable` | Boolean |
| `source_step` | safe manifest-listed stem or null |
| `digest` | SHA-256 |

`WebQuery`:

| Field | Type and bound |
|---|---|
| `query_id` | safe token, at most 128 bytes |
| `query_text` | exact string, at most 8 KiB |
| `provider` | credential-free provider identifier, at most 128 bytes |
| `requested_at` | RFC3339 UTC string |
| `digest` | SHA-256 |

`WebEvidence`:

| Field | Type and bound |
|---|---|
| `query_id` | references one query in the same state |
| `rank` | integer 0-255 |
| `title` | string, at most 16 KiB |
| `source_host` | credential-safe normalized host, at most 255 bytes |
| `source_url` | credential-safe URL without userinfo, fragment, or secret query values, at most 4 KiB |
| `content` | exact evidence text consumed downstream, at most 512 KiB |
| `retrieved_at` | RFC3339 UTC string |
| `digest` | SHA-256 |

If the downstream executable value depends on URL material removed by credential-safe normalization, capture fails rather than storing an altered value.

`WebStageState` for claim verification and unflagged scan:

| Field | Type and bound |
|---|---|
| `kind` | enum `claim-verification`, `unflagged-claim-scan` |
| `status` | enum `not-run`, `completed`, `error` |
| `read_only` | literal `true` |
| `queries` | ordered array of at most 64 `WebQuery` objects |
| `evidence` | ordered array of at most 256 `WebEvidence` objects |
| `model_output` | exact string or null, at most 1 MiB |
| `rendered_context` | exact string consumed by the next stage, at most 2 MiB |
| `errors` | ordered array of at most 64 `StageError` objects |
| `health` | `StageHealth` |
| `digest` | SHA-256 |

`PairedWebStageState` contains required `a` and `b` `WebStageState` objects, exact `pair_order: ["a", "b"]`, and its digest.

`StructuralViolation`:

| Field | Type and bound |
|---|---|
| `code` | safe uppercase token, at most 128 bytes |
| `path` | string at most 1 KiB or null |
| `message` | string at most 64 KiB |
| `digest` | SHA-256 |

`StructuralCheck`:

| Field | Type and bound |
|---|---|
| `status` | enum `pass`, `fail`, `not-run` |
| `validator` | versioned safe identifier at most 128 bytes |
| `violations` | ordered array of at most 64 `StructuralViolation` objects |
| `candidate_draft_digest` | SHA-256 of the exact candidate draft checked, or null only when status is `not-run` |
| `digest` | SHA-256 |

`BrokenResolution`:

| Field | Type and bound |
|---|---|
| `broken_gate_output_digest` | SHA-256 of the exact verifier/quality output classified `BROKEN` |
| `candidate_draft_digest` | SHA-256 of the candidate draft supplied to that gate |
| `candidate_structural_check` | `StructuralCheck` |
| `action` | enum `unblock-and-continue`, `rerevise-and-retry`, `cycle-cap-continue`, `ship-immediately` |
| `resulting_draft_digest` | SHA-256 of the draft carried forward |
| `digest` | SHA-256 |

`AttemptRecord` for verifier, repair, format/leak, quality, reconsolidation, and reformat histories:

| Field | Type and bound |
|---|---|
| `attempt_number` | integer starting at 1, contiguous within history |
| `kind` | enum `verify`, `revise`, `quality`, `format`, `leak-retry`, `reconsolidate`, `reformat` |
| `slot` | enum `single`, `a`, `b` |
| `input_digest` | SHA-256 of the exact draft/state passed to the attempt |
| `raw_output` | exact provider output string, at most 2 MiB |
| `structural_check` | `StructuralCheck` |
| `classification` | enum `pass`, `fail`, `broken`, `unknown`, `not-applicable` |
| `broken_resolution` | `BrokenResolution` when classification is `broken`, otherwise null |
| `draft_after` | `StageText` or null |
| `source_steps` | ordered array of 1-16 safe manifest-listed stems |
| `health` | `StageHealth` |
| `digest` | SHA-256 |

`AttemptHistory`:

| Field | Type and bound |
|---|---|
| `attempts` | ordered array of at most 16 `AttemptRecord` objects |
| `terminal_classification` | enum `pass`, `fail`, `broken`, `unknown`, `not-run` |
| `final_draft_digest` | SHA-256 or null; must match the current draft when present |
| `digest` | SHA-256 |

`RetryPlan` replaces the ambiguous `max_cycles` field:

| Field | Type and meaning |
|---|---|
| `attempts_completed` | integer; always `0` at a resumable pre-stage retry boundary |
| `max_attempts` | total number of stage loop bodies that may execute, including the initial attempt |
| `next_attempt_number` | literal `1` at the boundary |
| `history` | empty `AttemptHistory` for the selected retry stage |
| `digest` | SHA-256 |

`max_attempts` never means maximum zero-based index. For current Gear 3 verification it is `MAX_VERIFY_CYCLES + 1`, so `MAX_VERIFY_CYCLES = 2` yields `max_attempts = 3`. For current Gear 4 it is the number of loop bodies the Gear 4 code actually permits; where that code uses the constant directly, `max_attempts` equals that constant. Quality and formatting retry plans use the same total-attempt meaning. Checkpoint capture, cost estimate, approved physical-call ceiling, budget enforcement, and shared runner all consume this one normalized field. Tests compare it with actual mocked loop-body counts for every retrying stage.

`BROKEN` is lossless and mirrors current Ora fail-open transitions; Chunk 4 does not redesign them:

0. Fatal resume-control propagation runs before health parsing or verdict classification. A `FatalResumeControlError` is never converted to output text, `BROKEN`, `PASS`, `FAIL`, `ship-immediately`, candidate structural state, or any repair/fallback transition.
1. The gate/verifier output is parsed first only for ordinary output/provider results. If it is `BROKEN`, `AttemptRecord.classification` is `broken` and `broken_gate_output_digest` hashes that exact broken output.
2. In Gear 3 and Gear 4 verifier loops, Ora structurally checks the candidate draft that was submitted to the broken verifier, not the verifier output. `candidate_draft_digest` and `StructuralCheck.candidate_draft_digest` must match.
3. If that candidate draft structurally passes, action is `unblock-and-continue`; the same candidate becomes the resulting draft, no re-revision runs, and the pipeline advances despite the broken verifier output.
4. If that candidate draft structurally fails and another verification cycle is available, action is `rerevise-and-retry`; the existing failure-reviser path creates the resulting draft and the next verifier cycle runs.
5. If the candidate structurally fails at the verification cycle cap, action is `cycle-cap-continue`; Ora carries forward the latest candidate and continues rather than returning a structural error.
6. For a `BROKEN` final-quality gate, action is `ship-immediately`; the candidate draft is shipped immediately with `candidate_structural_check.status: not-run`. No quality repair, reconsolidation, reformat, or terminal structural error is introduced.
7. Semantic `FAIL` retains the current semantic revision/reconsolidation behavior and is never conflated with these `BROKEN` actions.
8. `AttemptHistory.terminal_classification` remains `broken` even when the associated resolution continues or ships. Step health records the broken gate plus resolution action so Trace Walk does not mislabel it as a clean pass.
9. Ordinary full-run and resume use the same transition function for ordinary outputs only. Fatal-control golden tests are separate and prove that a policy stop never enters this transition function. Ordinary golden tests compare call order, carried draft digest, revision invocation, cap behavior, final output, and step health for Gear 3, Gear 4, and final quality across `PASS`, semantic `FAIL`, `BROKEN + candidate pass`, `BROKEN + candidate fail with cycle remaining`, `BROKEN + candidate fail at cap`, and `BROKEN final quality`.

`FallbackState`:

| Field | Type and bound |
|---|---|
| `status` | enum `none`, `invalidated-to-gear3`, `external-consolidation` |
| `from_gear` | integer 4 or null |
| `to_gear` | integer 3 or null |
| `occurred_at_stage` | canonical stage enum or null |
| `reason_code` | safe token at most 128 bytes or null |
| `invalidated_boundary_digests` | ordered array of at most 16 SHA-256 values |
| `digest` | SHA-256 |

A resumable Gear 4 boundary requires `FallbackState.status == "none"`. The other values are audit-only and make that Gear 4 checkpoint chain unavailable.

Boundary payload mapping is exact:

- `depth_analysis`, `breadth_evaluation`, `revised_draft`, `verified_draft`, `consolidated_draft`, `formatted_draft`, and `final_draft` are `StageText`.
- Gear 4 analysis/evaluation/revision/verified-revision slots are `PairedStageText`.
- `claim_verification` and `unflagged_scan` are `WebStageState` in Gear 3 and `PairedWebStageState` in Gear 4.
- Every verifier/revision/quality/format/recovery history is `AttemptHistory`; every stage that starts a retry loop carries a fresh `RetryPlan`.
- Every boundary carries one `FallbackState` and the exact preceding `StageHealth` records already embedded in its typed objects. Health is not an untyped copy of `step-health.json`.

### D4. Shared stage runner, not a second pipeline

Refactor the current Gear 3 and Gear 4 functions into state initialization plus ordered stage runners. The ordinary full path and resume path call the same runners.

Conceptual interface:

```text
run_gear_stages(gear, state, start_stage, execution_policy) -> final result
```

`state` is an allowlisted typed structure whose serializable form is exactly the boundary checkpoint schema. `execution_policy` carries normal-versus-resume mode, approved budgets/capabilities, correction, and trace context.

The refactor must preserve ordinary full-run call ordering, retry counts, prompts, health recording, fallback behavior, and outputs. The full path remains the behavioral baseline.

Resume-specific rules:

- It loads static and boundary state under one lifecycle-lock snapshot and verifies all digests before approval preparation and again before consumption.
- It never runs Step 1 or Step 2.
- It invokes the selected canonical stage and all following stages through the shared dispatcher.
- It writes recomputed artifacts only to the new resume trace.
- It does not copy upstream step files.
- It does not invoke the ordinary Gear 4-to-full-Gear 3 fallback if that would cross the approved boundary. It records an explicit error instead.
- It binds turn trace, current step, model-call metadata, conversation tag, and tool-event ContextVars to the resume trace around the entire resumed execution, restoring the outer context in `finally`.

#### D4.1 Resume capability policy at hidden execution seams

The prepared request, durable approval, `step-resume-approval` artifact, and resume manifest bind one closed `ResumeCapabilityPolicy`:

| Field | Type and required value |
|---|---|
| `policy_version` | positive integer |
| `supplemental_rag` | literal `fail-on-request` |
| `model_tools` | literal `reject-all` |
| `read_only_web` | enum `disabled`, `approved-with-ceiling` |
| `max_read_only_web_calls` | integer 0-128; zero when disabled |
| `visual_compute` | literal `reject-all` |
| `state_changing_actions` | literal `reject-all` |
| `unknown_capabilities` | literal `reject-all` |
| `fatal_control_contract` | literal `fatal-resume-control-v1`, implementing D4.2 and the four closed reason codes |
| `digest` | SHA-256 |

The policy is installed in a `ResumeExecutionPolicy` ContextVar around the complete resumed dispatcher in both production entry points and reset in `finally`. Ordinary full runs and trace probes have no resume policy and retain existing behavior.

##### Supplemental RAG

Chunk 4 does not read mutable vault state after the captured Step 2 package. `_call_with_supplement()` must consult the resume policy before any Supplemental RAG retrieval or supplemental model resubmission.

Behavior is deterministic:

1. The approved primary logical model call runs against the exact captured context and consumes its normal physical-attempt/token budget.
2. If its output does not request Supplemental RAG, execution continues normally.
3. If the output requests Supplemental RAG, Ora records a `supplemental-rag-refused` policy event containing the trace ref, step, logical-call key, model-call ID, request digest, timestamp, and reason code. Raw generated retrieval text is not copied into the event. If that required append/read-back fails, it raises `FatalResumeControlError(reason_code="RESUME_POLICY_EVIDENCE_WRITE_FAILURE")` before any retrieval or resubmission.
4. Ora performs zero vault/RAG queries and zero supplemental `_call_with_retry()` invocations.
5. `_call_with_supplement()` raises `FatalResumeControlError(reason_code="RESUME_POLICY_VIOLATION", detail_code="SUPPLEMENTAL_RAG_REQUIRED")`.
6. The current step health records the coverage gap, the resume returns `[Resume stopped: downstream Supplemental RAG was requested but is disabled.]`, and the resume trace finalizes `error` with full missing-step derivation.

Eligibility rejects a source/configuration whose selected downstream path has an unconditional Supplemental RAG dependency. Conditional Supplemental RAG remains eligible because the request is model-output-dependent, but the prepare panel states: "If a resumed stage requests additional vault retrieval, this run will stop rather than read mutable vault state."

No `rag_selection`, `rag_isolation`, or mutable vault object is captured for downstream retrieval. The only RAG content available to resume is the already-rendered exact text in `ExecutionTextInputs`.

##### Model tool calls

`_run_model_with_tools()` is an enforcement seam, not merely a downstream helper. When resume policy is present:

1. It sends no callable tool definitions to the provider.
2. It still parses structured or textual tool calls defensively after each approved model response.
3. Before `execute_tool_with_outcome()` or any equivalent executor can run, every parsed tool call, including nominally read-only tools, is rejected.
4. Ora records one `tool-call-refused` policy event with trace ref, step, logical-call key, model-call ID, iteration number, sanitized tool name, argument digest, timestamp, and reason. Raw arguments are not persisted in this event. If that required append/read-back fails, it raises `FatalResumeControlError(reason_code="RESUME_POLICY_EVIDENCE_WRITE_FAILURE")` before any executor or follow-up iteration.
5. No tool result is fabricated or fed back to the model, and none of the agentic loop's remaining iterations run.
6. `_run_model_with_tools()` raises `FatalResumeControlError(reason_code="RESUME_POLICY_VIOLATION", detail_code="MODEL_TOOL_CALL_REFUSED")`.
7. The current step health records the refusal, the user sees `[Resume stopped: the model requested a tool; no tool was executed.]`, and the resume trace finalizes `error` with full missing-step derivation.

If static analysis of the selected route identifies an unconditional tool dependency, prepare returns `NOT_RESUMABLE: TOOL_DEPENDENCY_UNSUPPORTED` before approval persistence. The runtime rejection is defense against conditional, stray, malformed, or adversarial tool requests.

Policy events are append-only `resume-policy-events.jsonl` in the resume trace. This file is a bounded derived artifact under existing private/redaction, retention, lock, safe-write, and purge rules. Each record is at most 16 KiB; the file is capped at 1 MiB. Oversize or write failure raises the fatal evidence-writer reason; the top-level dispatcher then uses the independent fallback artifact and reports `error`, never an ordinary unhealthy/BROKEN result.

#### D4.2 Fatal resume-control exception contract

The implementation adds one shared, typed exception family, `FatalResumeControlError`, with a closed `reason_code` enum:

| Reason code | Raised when | Required terminal user/result meaning |
|---|---|---|
| `RESUME_POLICY_VIOLATION` | A bound resume capability is requested or observed outside its approved policy, including Supplemental RAG, any model tool, visual work, state-changing action, or unknown capability | `Resume stopped: approved resume policy was violated.` |
| `RESUME_BUDGET_EXHAUSTED` | The next physical model attempt or approved read-only web call cannot reserve its approved token/call budget | `Resume stopped: the approved resume budget was exhausted.` |
| `RESUME_ROUTE_POLICY_MISMATCH` | The runtime call site, endpoint/provider/model, slot, stage, retry condition, output cap, or capability route differs from the exact approved `LogicalCallPolicy`/`PhysicalAttemptPolicy` | `Resume stopped: the runtime route no longer matches the approved resume policy.` |
| `RESUME_POLICY_EVIDENCE_WRITE_FAILURE` | A required refusal/stop evidence append or read-back fails, including oversize, unsafe path, lock, schema, or atomic-write failure | `Resume stopped: the policy stop could not be evidenced by the required writer.` |

The exception carries only bounded, redacted fields: `reason_code`, `policy_contract_version`, `trace_ref`, `canonical_stage`, `logical_call_key`, `physical_attempt_ordinal` or null, `capability`, `phase`, a sanitized detail code, and a digest of any generated request/tool arguments. It never carries raw provider output, credentials, raw retrieval text, raw tool arguments, or an arbitrary exception string. It is not a provider error, output-health result, verifier verdict, or ordinary `Exception` payload to be rendered.

Fatal propagation is an explicit control-flow invariant. Every current and refactored broad handler in the resume call graph must have this ordering:

```python
except FatalResumeControlError:
    raise
except Exception as exc:
    # existing ordinary full-run behavior, unchanged when no policy is bound
```

This rule applies to all of the following, including handlers introduced while extracting the shared stage runner:

- Both model-attempt handlers in `_call_with_retry()`, including the first call and the retry call. An exception is never substituted with `[... call error ...]` under a bound resume policy.
- `_call_with_supplement()`, before the first delegation, after every returned primary output, before any `_fetch_supplement()`, before writing a supplemental result, and before every supplemental resubmission. A fatal from `_call_with_retry()` is re-raised unchanged.
- `_resolve_fallback_endpoint()` and every same-endpoint/provider fallback wrapper: the retry branch in `_call_with_retry()`, `call_api_endpoint()` direct-vendor fallback, prefer-direct-to-OpenRouter fallback, `_call_api_with_truncation_retry()`, and local/API dispatch wrappers. No fatal is converted into a marker that could trigger another attempt.
- Every Gear 3 and Gear 4 stage-level `except Exception`, including verifier exception substitution, quality-gate fail-open/BROKEN conversion, reviser/formatter/consolidator degradation, formatter leak repair, quality reconsolidation/reformat, and the Gear 4-to-Gear 3 fallback at the analyst boundary. A fatal is never passed to `_verifier_broken()`, `_verifier_passed()`, `_step_output_health()`, a degradation wrapper, or a fallback selector.
- Every parallel `Future.result()` handler reachable from resumed stages: Gear 4 analyst, evaluator, reviser, verifier, and re-revision futures; `claim_verification.py` futures; and any future handler added to the resumed shared runner. The same explicit re-raise rule must also be present in `web_consultation.py:837-854` if that helper is ever called under a bound policy, while its current Step 2 no-policy aggregation remains unchanged. The handler sets the shared resume-stop token, cancels not-yet-running sibling futures, waits for running workers to reach their next policy seam, and re-raises the same fatal. Workers check the stop token before a retry, provider fallback, repair, web call, tool call, or model call. A normal ordinary-run future handler keeps its current substitution behavior when no resume policy is bound.
- Verifier and quality-gate fail-open/BROKEN handlers, including the Gear 3 and Gear 4 sites that currently ship on a failed gate. Fatal control never becomes `BROKEN`, `PASS`, `FAIL`, `ship-immediately`, or a candidate structural result.
- Repair, degradation, formatter leak, reconsolidation, reformat, and final-output scrub paths. No fatal is wrapped as a usable revised draft or consolidated corpus.

The runtime stop token is process-local and is not a new authority. It is set atomically when the first fatal is raised, and every physical-call, web, tool, retry, fallback, repair, and future-join seam checks it before doing work. In-flight provider calls cannot be force-killed, so production tests use deterministic gates to prove no post-stop request is started; a provider result that returns after the stop is discarded and cannot trigger a follow-up action.

Only `execute_resume()`—the shared top-level resume dispatcher invoked by both `server.py::_pipeline_stream` and `boot.py::run_pipeline` after durable approval consumption—may catch `FatalResumeControlError`. Its catch path is the sole conversion point:

1. Atomically mark the stop token and cancel/join reachable siblings.
2. Write a bounded `resume-stop` policy event containing the typed reason, stage, call key, attempt/capability, and evidence digest; read it back before claiming a policy stop.
3. If the original failure is `RESUME_POLICY_EVIDENCE_WRITE_FAILURE`, or the normal stop-event write fails, write and read back an independent `resume-control-failure.json` safe artifact with the same bounded fields and the writer-failure code. This fallback writer must not reuse the failed JSONL append path. If both evidence surfaces fail, the result says policy evidence is unavailable and makes no claim that the refusal/no-action event was durably recorded.
4. Write/read back `step-health.json` with `execution_status: error`, `structural_status: unknown`, `semantic_status: unknown`, and a fatal-control reason code; never mark the stage healthy or `BROKEN`.
5. Set the resume turn state to `error`, finalize/read back the complete resume manifest with missing-step derivation and `policy_stop` metadata, and return exactly one documented status/result string. It must not call any later stage, retry, fallback, verifier/quality repair, Supplemental RAG, tool executor, or agentic follow-up.

The server and CLI lifecycle wrappers may still catch/re-raise ordinary `BaseException` for their existing finalization semantics, but they do not convert this exception and they must not run a second fatal catch. If a fatal unexpectedly escapes `execute_resume()`, the wrapper re-raises it after setting `error`; that is an implementation defect covered by a production-entry-point test, not a second conversion path. No-resume-policy execution never raises this family for ordinary model/provider/output failures and retains existing behavior.

### D5. Human correction semantics

An empty correction produces a normal stochastic resume under the captured execution contract.

A non-empty correction produces a **counterfactual corrected resume**. The exact correction is:

- Bound into the prepared digest and pending approval.
- Persisted in the private/default resume trace according to inherited redaction policy.
- Delimited as a human correction, not concatenated ambiguously with source content.
- Included as an explicit constraint in every downstream model prompt generated by the resumed stage dispatcher.
- Never used to mutate the reused upstream checkpoint or original trace.
- Never transformed into a tool instruction or external action.

Trace Walk and export label the run "Corrected resume" and state that it is not a faithful replay. The manifest stores only correction presence and digest; the exact text lives in the bounded `step-resume-request` artifact.

### D6. Eligibility and preparation

Add a shared `orchestrator/trace_resume.py` core. It owns schema validation, checkpoint capture/load, stage mapping, estimates, prepare/approve/consume, execution policy, event recording, and the durable operation-approval adapter.

`prepare_resume()` returns `NOT_RESUMABLE` before pending approval creation unless all checks pass:

- Feature flag enabled.
- Exact valid trace ref and same active conversation.
- Source kind is exactly `chat-gear3` or `chat-gear4`. `resume` is explicitly rejected with `CHAINED_RESUME_UNSUPPORTED`.
- Source is terminal `completed` or `error`, not `open` or `abandoned`.
- Selected step is manifest-listed and maps exactly to one supported canonical stage.
- Static and boundary checkpoints exist as regular, non-symlink direct children.
- Checkpoints are within size limits, valid JSON, complete, and mutually digest-consistent.
- Redaction/conversation ownership is valid.
- Engine, schema, stage map, and physical-call policy fingerprints are compatible.
- Kind `chat`, `resume`, `clarification_resume`, `direct`, `framework-run`, `framework-milestone`, `trace-debug`, `trace-probe`, and every unknown kind are rejected.
- No image, attachment, visual input/output/model/render, framework, state-changing action, unknown capability, or ambiguous dependency is present.
- The complete downstream maximum call/token/capability plan can be calculated.
- Every reachable logical call has the exact versioned `UnhealthyOutputPolicy`, `DispatchNoiseContract`, `HealthMarkerContract`, verifier/reviser validator selection, and ordered physical-attempt conditions. Missing or stale health policy evidence makes preparation `NOT_RESUMABLE`, not a reason to fall back to a generic retry rule.
- The fatal-control contract version and route-policy digest are compatible. Any runtime route, endpoint, provider fallback, truncation cap, stage/role/slot, or capability mismatch will raise `RESUME_ROUTE_POLICY_MISMATCH` before the physical request.
- Correction and aggregate token ceiling are valid.

Preparation computes and displays:

- Source trace and canonical boundary.
- Exact reused step refs/digests.
- Exact stages that will be recomputed.
- Maximum physical model attempts, provider/model identities, per-call caps, and aggregate token ceiling.
- Every conditionally reachable same-endpoint unhealthy-output retry, truncation retry, and provider fallback under its exact logical-call key.
- Estimated input tokens and conservative maximum output tokens.
- Informational monetary estimate when authoritative pricing is available. If pricing is unavailable, the UI says so; it never displays zero cost. Currency is not an enforceable ceiling in Chunk 4.
- Read-only web call ceiling.
- Supplemental RAG policy `fail-on-request` and model-tool policy `reject-all`, including their deterministic terminal behavior.
- Explicitly forbidden capability classes.
- Whether the resume is corrected/counterfactual.
- Expiry.

The only hard user-supplied cost limit is `aggregate_token_ceiling` from CLI `--token-ceiling` or the equivalent JSON integer. Its persisted unit is `ora-estimated-input-plus-max-output-tokens`, and its `token_estimator_policy_version` is approval-bound.

Before each physical attempt, Ora reserves:

```text
versioned_estimate(exact serialized input messages) + effective max_output_tokens
```

from the aggregate ceiling. Reservation happens before dispatch and is not refunded after failure, truncation, or unused output. Retry and provider fallback attempts reserve independently. The versioned estimator is deterministic for the same serialized messages; a tokenizer/policy-version change invalidates approval. The approved request and resume manifest persist `aggregate_token_ceiling`, `token_unit`, and `token_estimator_policy_version`. `estimated_usd` and its pricing-source timestamp may be displayed as informational metadata but are not named or enforced as a ceiling. A future hard currency limit requires a separate policy.

The prepared immutable request includes a canonical source-execution digest, digests of the static checkpoint, selected boundary, represented source artifacts, correction, logical-call/physical-attempt policy, resume capability policy, stage map, estimate, and runtime fingerprint.

The canonical source-execution digest is the SHA-256 of the canonical JSON encoding of the complete source manifest after removing exactly these permitted mutable fields:

- `child_trace_refs`
- `probe_trace_refs`
- `retention_state`

All other current and future manifest fields are included by default. `parent_trace_ref`, terminal status, expected/actual/derived artifacts, contract/checkpoint metadata, finalization time, gear, mode, and redaction are therefore protected. Resume events are a separate JSONL file and are protected by their own bound source-event prefix digest only when they are execution inputs; ordinary append-only audit events do not mutate the manifest digest.

The digest is checked immediately before consumption while holding the source conversation lifecycle lock. The same lock remains held through durable approval consumption, child creation, and reciprocal lineage read-back. Because `child_trace_refs` is the explicitly excluded lineage field, the authorized append does not invalidate the execution digest. A retention or probe-lineage update can proceed without false tamper detection; any other source-manifest mutation rejects execution.

### D7. Durable resume approval authority, risk state machine, and hard ceilings

Add `orchestrator/trace_resume_approval.py` as a resume-only durable authority. Existing `trace_debug.py` probe approvals remain process-local in `_APPROVALS` with their current complete-manifest digest, TTL, restart loss, purge behavior, and public APIs. Chunk 4 may extract pure canonical-JSON and constant-time-comparison helpers into a non-persistent utility, but probe prepare/approve/consume must not read or write the durable resume store.

When `ORA_TRACE_RESUME_ENABLED` is false, no code creates, scans, migrates, or cleans the resume approval directory. Probe use while resume is OFF creates no new persistence. There is no compatibility migration for old in-memory probe approvals.

Authority location:

```text
$ORA_HOME/data/trace-operation-approvals/<conversation_id>/<approval_id>.json
```

Every process resolves the path through `runtime_paths`; CLI and server can share authority only when they use the same canonical `ORA_HOME`. A request from a different home cannot see or recreate approval and returns `APPROVAL_AUTHORITY_MISMATCH`. The approval-store root and each conversation directory are created and verified as mode `0700`; approval files are regular non-symlink direct children created and verified as mode `0600`. Creation does not rely on ambient `umask`. Files are written atomically and read/transitioned under the cross-process conversation lifecycle lock. IDs are random server-generated values validated as safe filename stems.

Add the repository-root `.gitignore` rule `/data/trace-operation-approvals/`. This is defense in depth for an `ORA_HOME` rooted at the repository; approval content must never appear as an untracked candidate even though normal runtime data may be elsewhere.

The closed resume approval record contains:

- Schema version, approval ID, operation kind fixed to `resume`, conversation ID.
- Immutable prepared request and digest.
- Canonical source-execution and checkpoint/artifact/runtime digests.
- Server-generated risk task/digest, risk tier, hold/Paused entry ID when present.
- State, state version, creation, absolute expiry, transition timestamps.
- Consumed timestamp and execution trace ref when available.
- No credentials, provider secrets, or raw risk token.

Every durable record persists digest policy `resume-execution-projection-v1`, which hashes the complete manifest except exactly `child_trace_refs`, `probe_trace_refs`, and `retention_state`. Unknown policies are rejected. The existing ephemeral probe path continues to hash the complete source manifest and therefore continues to reject every post-prepare manifest mutation, including those three fields.

States and transitions:

| Current state | Trigger | Next state | Rules |
|---|---|---|---|
| none | valid prepare, risk clear | `risk-cleared` | Durable record exists before response. |
| none | valid prepare, risk hold | `risk-held` | Exact approval ID and operation digest are persisted in the Paused entry. |
| `risk-held` | valid one-time risk token | `risk-cleared` | Token is bound to the exact risk-task digest and consumed by the risk gate. |
| `risk-cleared` | explicit approve | `approved` | Source/checkpoint/runtime digests and expiry are rechecked. |
| `approved` | execute | `consumed` | Atomic one-winner transition before child creation or external work. |
| nonterminal | cancel | `cancelled` | Irreversible; Paused entry is closed when present. |
| nonterminal | absolute expiry observed | `expired` | Irreversible; no extension after hold clearance. |
| terminal | any repeat | unchanged | Returns an exact terminal reason; never reopens. |

Risk-hold continuation is explicit:

1. Prepare builds the exact downstream task/capability digest and asks `risk_gate` to classify it without trusting client fields.
2. A hold writes `risk-held` and an exact Paused entry. The approval expiry is the earlier of the configured approval TTL and any risk-token validity bound.
3. The user clears the existing risk gate. Server or CLI `approve` supplies the resulting one-time risk token alongside approval ID/digest.
4. To avoid lifecycle-lock recursion, approval reads a snapshot under the conversation lock, releases it, asks an operation-bound risk-gate API to consume the token, then reacquires the conversation lock and compares the approval record's state version, digest, and expiry. If another process won or the record changed, approval fails closed. A consumed risk token never authorizes a different or changed operation.
5. On successful comparison, the durable record moves `risk-held -> risk-cleared -> approved` in one atomic replacement. A no-hold operation moves `risk-cleared -> approved` directly.
6. Clearing risk does not extend absolute approval expiry. If expiry wins the race, the operation becomes `expired` and must be prepared again.
7. Cancellation is available through server and CLI and closes any linked Paused entry. Expiry cleanup occurs synchronously on approval access, server startup, CLI startup, or conversation closeout, not on a scheduled maintenance loop.

Consumption and lineage use one lifecycle-locked sequence:

1. Read and validate the durable `approved` record.
2. Recompute canonical source-execution, checkpoint, artifact, policy, and runtime digests.
3. Atomically transition the record to `consumed` with no execution ref yet.
4. Create the resume child, stamp its source parent, append the child to the source, and read back reciprocal lineage.
5. Write `execution_trace_ref` into the consumed record.
6. Release the lock, bind execution contexts, then permit the first physical request.

If the process fails between steps 3 and 5, the approval remains consumed and cannot be replayed. No external request is allowed before step 6. On next authority access, a consumed record without durable reciprocal lineage is reported `CONSUMED_BEFORE_EXECUTION`; any partial child is left `open`/incomplete or finalized by an ordinary catchable wrapper path, and the user must prepare a new operation. The authority never guesses that an external request occurred.

Forged, expired, cancelled, replayed, cross-conversation, wrong-operation, mutated, or authority-mismatched requests create no resume trace. When the source remains valid, rejection is appended to `trace-resume-events.jsonl` under its lifecycle lock.

During execution, a resume budget ContextVar is checked at each physical provider-attempt seam and each approved read-only web seam. The check reserves budget atomically before the request. Every unhealthy-output same-endpoint retry, truncation retry, and provider fallback is a separate physical attempt under the same exact logical-call policy. Unsupported engines are not counted as physical calls and are rejected before dispatch. Supplemental RAG, model tools, visual work, and state-changing capabilities are enforced by D4.1. Exceeding or changing the approved plan ends the trace `error` before the request.

Each check raises the typed fatal family on a bound resume path: an unavailable reservation is `RESUME_BUDGET_EXHAUSTED`; any route or policy discrepancy is `RESUME_ROUTE_POLICY_MISMATCH`; a forbidden capability is `RESUME_POLICY_VIOLATION`; and failure to append/read back the required refusal evidence is `RESUME_POLICY_EVIDENCE_WRITE_FAILURE`. No check may return an unhealthy string or a provider-style error marker for these cases. The first fatal wins, the stop token is monotonic, and later workers/handlers only re-raise it.

### D8. Trace creation, lineage, and manifest semantics

Add paired `pipeline_trace` helpers: a public lifecycle-locked wrapper and an internal `_start_derived_trace_unlocked()` for callers that already hold the non-reentrant conversation lock. Durable approval consumption calls only the unlocked helper inside its single lock window. For resume the helper must:

- Resolve and revalidate the source under the conversation lifecycle lock.
- Create a unique child trace directory atomically.
- Inherit conversation ID and effective redaction/private handling.
- Stamp `trace_kind: "resume"` and `parent_trace_ref: <exact source ref>`.
- Append/dedupe the child ref in the source `child_trace_refs` without clobbering unrelated fields.
- Read both manifests back before execution.
- Finalize the child `error` and make no external request if reciprocal lineage cannot be made durable.

Resume manifest additions:

- `resume_schema_version`
- `resume_source_trace_ref`
- `resume_from_step`
- `resume_canonical_stage`
- `resume_mode`: `uncorrected` or `corrected-counterfactual`
- `human_correction_present`
- `human_correction_digest`
- `resume_checkpoint_digest`
- `resume_engine_fingerprint`
- `resume_approval_digest`
- `reused_steps`
- `recomputed_steps`
- `resume_expected_steps`
- `approved_capabilities`
- `resume_capability_policy_digest`
- `aggregate_token_ceiling`
- `token_unit`
- `token_estimator_policy_version`

`parent_trace_ref` and `resume_source_trace_ref` must agree and must identify the eligible original `chat-gear3` or `chat-gear4` trace. Because chained resume is rejected, no resume-root walk or ancestry inference is performed.

`reused_steps` is an ordered list of source trace ref, source step name, digest, and canonical role. It contains no claim that the step executed in the resume trace.

`recomputed_steps` is derived from actual pipeline stage artifacts in the resume trace. Control artifacts are not counted as recomputed pipeline steps.

Expected steps are boundary-specific:

- Control artifacts: `step-resume-request`, `step-resume-checkpoint`, `step-resume-approval`, and `step-resume-result`. A fatal policy stop additionally requires `step-resume-policy-stop` and its typed reason/evidence digest; a policy-evidence writer failure additionally requires the independently written `resume-control-failure.json` when the normal JSONL writer cannot be read back.
- Concrete pipeline step artifacts from the selected canonical stage through the normal terminal stage, including bounded retry alternatives represented by the current stage map.
- `step-health.json` remains a derived artifact.

`_expected_steps_for()` uses the persisted `resume_expected_steps` only after validating it against the versioned canonical stage table. It never expands a resume to the entire gear table.

Terminal states:

- `completed`: all required resumed stages succeeded, final output was captured, full manifest derivation succeeded, and the complete durable manifest read-back matches.
- `error`: provider, approved capability, stage, budget, checkpoint, lineage, or finalization failure after trace creation.
- `abandoned`: a `KeyboardInterrupt`, `SystemExit`, cancellation, or other premature exit only when control reaches the Python wrapper/finalizer and no completed/error result exists.
- `open`: an uncatchable crash, `SIGKILL`, kernel termination, or power loss may leave the durable skeleton open. Chunk 4 adds no heartbeat or stale-open reconciler and does not relabel such traces. Trace Walk/export continue to label them incomplete.
- A fatal resume-control stop is always terminal `error` once the top-level dispatcher has read back its stop evidence and manifest. It is not `abandoned`, `open`, `BROKEN`, or a completed degraded result. If the process dies before the dispatcher catch, normal uncatchable-loss semantics apply and the manifest remains honestly `open`.
- Pre-approval/pre-trace refusal: no resume trace; append an origin event when safely possible.

Finalization must derive expected, actual, derived, missing, reused, and recomputed fields for every terminal status. A metadata-only fallback is not sufficient.

### D9. Server integration

Add strict JSON endpoints:

- `GET /api/trace/resume/eligibility?trace_ref=...`
- `POST /api/trace/resume/prepare`
- `POST /api/trace/resume/approve`
- `POST /api/trace/resume/cancel`

Execution uses the normal `/chat` pipeline with:

```json
{
  "trace_resume": {
    "approval_id": "server-issued",
    "approval_digest": "prepared-digest"
  }
}
```

All request bodies must be JSON objects with exact string/integer/Boolean types as applicable. Do not coerce strings with `bool()` or accept unknown fields silently. A held approval accepts a risk token only at the approve endpoint; it is passed to the risk gate and is never persisted in the operation record.

The `/chat` handler performs strict shape checks and associates the request with the active conversation, but does not treat the client token as approval. `_pipeline_stream` consumes server state before creating the resume trace. The consumed immutable request, not client fields, drives execution.

`_pipeline_stream` then:

- Creates the checked reciprocal resume lineage.
- Binds all trace/call/tool contexts to the new trace.
- Invokes the shared top-level `execute_resume()` dispatcher from the approved boundary. `execute_resume()` is the only converter of `FatalResumeControlError`; it returns one visible stop result while setting `turn_state["status"] = "error"`, writing/read-backing policy-stop evidence and `step-health.json`, and allowing the wrapper's normal finalizer to derive the terminal manifest.
- Streams/saves the resulting assistant turn through the normal turn path.
- Copies any bracketed/internal error state into `turn_state` before finalization.
- Restores outer contexts in `finally`.
- Durably finalizes and reads back every outcome.

For a fatal resume stop, `_pipeline_stream` emits the documented error result and no assistant success turn, no later SSE stage, no retry/fallback/repair event, no Supplemental RAG retrieval/resubmission, no tool execution or injected tool result, and no agentic follow-up. Any applicable bounded refusal event, policy-stop evidence, and terminal manifest are the only allowed control evidence. Its wrapper finalizes `error`; it does not catch and reinterpret the fatal exception a second time.

A successful saved assistant turn carries the new resume `trace_ref`. A failed/stale approval stays in Ora and returns a visible error rather than navigating or claiming submission.

### D10. CLI integration

`boot.py::run_pipeline` recognizes deterministic prepare/approve/cancel/execute commands. Every phase uses the durable authority resolved from the same `ORA_HOME`; no phase depends on process memory. A CLI process may prepare, a server process may approve, either process may restart, and a later compatible process may execute before absolute expiry. Execute uses the same lineage, context binding, stage dispatcher, budgets, and finalization as the server.

CLI execute must not create an ordinary `chat` trace and then a second resume trace. The wrapper creates exactly one `resume` trace for the resumed turn. `run_pipeline()` calls the same top-level `execute_resume()` dispatcher as the server. Fatal stops become the documented status/result string after durable policy-stop evidence and `step-health.json` read-back; the CLI wrapper finalizes `error` and does not catch the fatal family as an ordinary model error. Errors returned normally by the stage dispatcher must be copied into terminal state before finalization.

CLI persistence is deliberately narrower than server persistence. `run_pipeline()` remains a string-returning API and Chunk 4 does not claim that it saves a conversation assistant turn. After durable manifest read-back, the deterministic CLI execute result is rendered exactly as:

```text
[Resume completed]
Trace ref: <conversation-id>/<turn-id>

<result text>
```

For an error or catchable abandonment after trace creation, the first line names that status and the second line still carries the exact durable trace ref. A pre-trace rejection returns its reason and no trace-ref line. The ref is obtained from the created trace directory with `trace_ref_for_dir()` and compared with the finalized manifest before rendering. Tests assert the returned binding and on-disk manifest; they do not assert a saved CLI conversation turn. Any future CLI conversation saver is a separate integration gate.

The CLI and server have parity tests for completed, error, abandoned, stale approval, and source mutation behavior.

### D11. Trace Walk and export

The browser-safe manifest projection adds only bounded resume metadata and a server-computed eligibility summary. Raw checkpoints, correction text, approval state, and private execution packages are never exposed by manifest projection.

Trace Walk behavior:

- A loaded supported step shows "Re-run from here".
- Unsupported, legacy, stale, open, framework, image-bearing, or incompatible traces show the exact non-resumable reason.
- The action opens a prepare panel with optional correction and aggregate token ceiling.
- Prepare displays canonical stage expansion, inherited/recomputed plan, cost/token/call ceilings, capabilities, expiry, and counterfactual label before approval.
- Pin/Export/Investigate semantics remain per trace.
- Approval and `/chat` submission reject stale async responses with the existing generation/AbortController pattern.
- Controls stay disabled during loading, invalid/stale state, preparation, approval, and submission.
- Escape, focus trap, and focus restoration continue to work.

Resume trace rendering has two visually distinct sections:

- **Reused from source**: exact source refs, step names, digests, and availability. Opening one targets that exact source trace/step.
- **Recomputed here**: only actual and missing steps owned by the resume trace.

A stale/expired parent remains a visible lineage gap; the UI never joins to a similarly named trace.

Export remains attachment-only with the existing no-sniff/CSP protections. It includes a bounded lineage summary, correction label, reused step refs/digests, recomputed steps, and missing expected steps. It does not inline raw parent trace content or checkpoints and does not label reused steps as executed by the resume.

### D12. Conversation purge and retention

Resume traces live under the investigated/source conversation and use existing trace retention. A conversation purge therefore physically removes source checkpoints, resume traces, resume events, and exact identifiers with the existing trace tree.

Durable approval files are private derived state outside the trace tree. Add locked public and unlocked closeout helpers, following the learning-library deadlock lesson, so conversation closeout physically removes every approval record for the conversation without reacquiring a non-reentrant lifecycle lock. Startup/access cleanup transitions expired records before eventual removal; it never preserves an identifiable approval after conversation purge.

Retention remains per trace. Pinning a source does not pin a resume child, and pinning a resume child does not pin its parent. The UI labels "Pin trace". Stale lineage after independent expiry is expected and handled cleanly.

## 6. Trace-document section 10 persistence checklist

Chunk 4 adds files within the existing trace persistence surface and a new durable operation-approval surface shared across Ora processes.

| Section 10 question | Chunk 4 answer |
|---|---|
| Owner | The source conversation owns checkpoint files, resume events, resume traces, and durable approvals. |
| Location | Trace checkpoints, resume traces, `resume-policy-events.jsonl`, and independent `resume-control-failure.json` policy-stop evidence are under the existing trace root. Approval files are under `$ORA_HOME/data/trace-operation-approvals/<conversation>/<approval>.json`. |
| Git exclusion | Repository-root `.gitignore` contains `/data/trace-operation-approvals/`; isolated tests prove approval files do not appear in Git status. |
| Schema/version | Explicit resume checkpoint, boundary, event, and manifest schema versions. Unknown versions fail closed. |
| Creation | Only when `ORA_TRACE_RESUME_ENABLED` is true; atomic safe/no-follow writes under the conversation lifecycle lock. Approval root/conversation directories are verified `0700`; records are verified `0600`. |
| Mutation | Checkpoint and boundary files are immutable after write. Resume and policy-event JSONL files are append-only. `resume-control-failure.json` is a one-time immutable fallback evidence artifact. Manifests use locked preserve-and-dedupe updates. Approval state uses closed monotonic transitions and atomic replacement. |
| Read discipline | Exact ref resolution, same-conversation check, regular non-symlink direct children, bounded reads, one lifecycle-lock snapshot. CLI and server must resolve the same canonical `ORA_HOME`. |
| Size limits | 8 MiB per checkpoint/boundary file, 64 MiB aggregate checkpoint material, 16 KiB per policy event and 1 MiB policy-event file, bounded `resume-control-failure.json`, correction, and other event records. Oversize is explicit failure, never truncation. |
| Secrets | No credentials/auth material. Policy events store generated-request/tool-argument digests, not raw values. If exact checkpoint state cannot be captured without forbidden material or redaction would alter it, capture fails. |
| Private traces | Resume and approval records inherit the effective private conversation identity. Exact correction/prepared text remains only in `0700`/`0600` storage and is physically purged; derived output cannot downgrade to default. |
| Retention | Existing per-trace retention applies. Source and child pins are independent. |
| Purge | Conversation purge physically removes checkpoints/events, `resume-control-failure.json`, traces, and durable approval files via an unlocked helper when the caller already holds the lock. |
| Corruption/missing files | Stage becomes `NOT_RESUMABLE`; after trace creation, corruption produces terminal `error`. No heuristic substitution. |
| Open/abandoned traces | Not resumable in this release. Walk/export still label them honestly. |
| Browser/export exposure | Only allowlisted bounded metadata. No raw checkpoint route or arbitrary artifact projection. |
| Off switch | Default-OFF `ORA_TRACE_RESUME_ENABLED`; disabling blocks prepare/approve/execute and stops new capture without damaging existing traces or reopening approval state. |
| Stealth | Stealth turns create no trace, checkpoint, or approval. A missing/stealth ref fails before approval persistence. |
| Migration | None. Legacy traces remain valid historical traces and are explicitly non-resumable. |
| Observability | Capture errors and pre-trace rejections are recorded with bounded reason codes. Supplemental-RAG and tool refusal must be durably recorded before the no-action claim is returned. Fatal resume-control stops use `fatal-resume-control-v1`, typed reason codes, stop-token state, step-health `error`, and terminal-manifest `error`; a policy-evidence writer failure uses the independent `resume-control-failure.json` fallback and never claims durable refusal evidence when read-back fails. Approval records persist exact prepared correction as private operation state; event logs contain no credentials, correction text, raw retrieval requests, or raw tool arguments. |

After implementation approval and landing, `Reference - Pipeline Trace System` must be updated under separate vault authorization before the persistence surface is considered fully documented.

## 7. Security and failure analysis

### Source mutation

Preparation and consumption hash the canonical source-execution projection, checkpoint, boundary, represented source artifacts, stage map, and runtime policy. Only `child_trace_refs`, `probe_trace_refs`, and `retention_state` may change without invalidation. Symlinks and non-regular files are rejected.

### Forgery and replay

Approval requires a durable authority record, not process memory. Digest comparison is constant-time. Cross-process lifecycle locking and atomic replacement allow one winner under concurrent execute requests. Replays create no trace and make no request.

### Cost expansion

Retries and provider fallbacks are separate physical attempts. Conservative maxima are approved. ContextVar budgets reserve before dispatch. A new/unexpected provider, model, cap, or capability ends `error` before the request.

### Fatal-control containment

The fatal reason is carried as a typed control record, not a model/provider string. Inner catches, future handlers, verifier/quality classifiers, repair/degradation helpers, and Gear fallbacks re-raise it. The shared stop token prevents new work after the first fatal; the top-level dispatcher is the sole converter and must read back stop evidence, `step-health.json`, and the terminal `error` manifest before returning. Ordinary runs and probes have no bound policy and therefore preserve their existing retry, fallback, fail-open, and future-error behavior.

### False lineage

Source/child manifests are updated and read back under one conversation lock before execution. Parent refs are exact and same-conversation. Walk/export never infer lineage by timestamp or filename.

### False completed status

Every terminal path finalizes and reads back full derivation. `completed` requires all boundary-specific expected artifacts. Error and abandoned traces receive the same durability check.

An uncatchable process loss is not a terminal path. It may leave `terminal_status: open`; the UI/export label it incomplete. This design intentionally makes no `abandoned` claim for `SIGKILL`, kernel failure, or power loss.

### Context leakage

All turn-trace, step, call metadata, conversation tag, tool-event, and resume-budget ContextVars are set around execution and reset in reverse order in `finally`. Physical call evidence therefore lands in the resume trace.

### Private-data downgrade

Effective redaction is read from the source under lock and passed into trace creation by server and CLI. The finalized trace is read back to confirm it did not downgrade.

### Prompt correction ambiguity

Correction is bounded, exact, delimited, and labelled counterfactual. It cannot change provider/configuration or authorize actions. Its digest is approval-bound.

## 8. Expected implementation files

No file in this section is modified by the design phase.

- `orchestrator/trace_resume.py` (new)
- `orchestrator/trace_resume_approval.py` (new durable cross-process authority used only by resume)
- `.gitignore` (exclude `/data/trace-operation-approvals/`)
- `orchestrator/trace_debug.py` only if a pure non-persistent canonicalization helper is shared; probe `_APPROVALS` and behavior remain unchanged
- `orchestrator/pipeline_trace.py`
- `orchestrator/boot.py`
- `orchestrator/claim_verification.py` (only for fatal propagation through resumed claim-verification futures; ordinary future-error aggregation remains unchanged)
- `orchestrator/conversation_closeout.py`
- `server/server.py`
- `server/static/js/trace-walk.js`
- `orchestrator/tests/test_trace_manifest.py`
- `orchestrator/tests/test_trace_walk_ui.py`
- Focused server/CLI tests already used for production trace entry points, if maintained separately on implementation HEAD

No database is introduced. The new durable approval directory is a scoped persistence surface covered by section 6.

## 9. Test plan

### Checkpoint capture

- Exact static and every canonical boundary capture for successful Gear 3 and Gear 4 runs.
- Checkpoints are written before the represented stage begins.
- Closed-schema validation covers every common field and every Gear 3/Gear 4 table row; missing, extra, wrong-type, partial paired, nonzero retry, incomplete web, and inconsistent fallback state are rejected.
- Static checkpoint tests cover every `EndpointIdentity`, `ModelParameters`, `PhysicalAttemptCondition`, `PhysicalAttemptPolicy`, `UnhealthyOutputPolicy`, `DispatchNoiseContract`, `HealthMarkerContract`, `verifier-envelope-v1`, `reviser-envelope-v1`, `LogicalCallKey`, `LogicalCallPolicy`, `ModelExecutionPolicy`, `ExecutionTextInputs`, and `InputProvenanceDigests` field, enum, cardinality, byte bound, secret exclusion, composition digest, and unknown-key rejection.
- Production Gear 3/Gear 4 configuration fixtures prove each reachable call site resolves one exact `(canonical_stage, role, slot)` route and ordered physical chain; missing, duplicate, extra, wrong-slot, cross-role fallback, and condition mismatch are rejected.
- Gear 4 analysis fixtures require `(depth-analyst, a)` and `(breadth-analyst, b)`; every paired key is enumerated separately and formatting has exactly one `(g4-formatting, formatter, single)` policy.
- `_step_output_health()` parity tests cover `None`, dispatch-noise-only/empty, below-threshold short output, every exact refusal and clarification marker in source order, every pipeline/provider/input/structured/browser dispatch marker category, missing and line-anchored verifier verdicts, and the complete reviser envelope matrix: null, short envelope, missing `## REVISED DRAFT`, empty draft body, body below 50 characters, H2 headings inside the body, and a valid envelope. They assert the exact typed reason (`null`, `empty`, `short`, `refusal`, `clarification`, `dispatch-error`, `malformed-verifier`, or `malformed-reviser`) and the corresponding `retry_*` condition.
- Empty, short, refusal, clarification, malformed-verifier, malformed-reviser, and dispatch-error outputs trigger only their captured `unhealthy-output` conditions. Same-endpoint retries prove endpoint-digest equality and consume separate physical/token reservations. The parity fixture compares the persisted health contract digest with the current marker/validator contract and fails if a code marker is added without a policy-version update.
- Every canonical boundary validates the exact closed envelope, typed artifact refs, state schema, required `NoRetryState`/`FreshRetryState`, required `NoWebBoundaryState`/`PendingWebBoundaryState`, fallback state, and `boundary_digest`.
- Pre-web boundary fixtures require no fabricated source step or health; completed web evidence is accepted only inside the later stage's typed state.
- A runner path that consults any raw Step 2 object after normalized text rendering is ineligible and emits an exact capture error.
- Capture off when flag is false.
- Legacy trace, missing boundary, malformed JSON, oversized field/file/aggregate, symlink, non-regular file, forbidden credential material, image/attachment/visual dependency, stealth/missing trace, and unsupported capability all return exact non-resumable reason codes.
- Every nested schema field, enum, cardinality, UTF-8 byte limit, source-step reference, canonical digest, and aggregate bound has accept/reject tests.
- Gear 3 `MAX_VERIFY_CYCLES = 2` normalizes to `max_attempts = 3`; Gear 4 and quality/format stages normalize to their actual mocked loop-body counts. Estimates, approval ceilings, and runners use the same values.
- Mutation after prepare invalidates approval.
- Mode/runtime code mutation produces `RUNTIME_MISMATCH`; no current-file substitution.
- Reads and writes occur while the cross-process lifecycle lock is held.

### Shared stage execution

- Ordinary full Gear 3 and Gear 4 mock call order, prompts, retry maxima, fallback behavior, step names, and outputs are unchanged by refactor.
- Resume from every canonical Gear 3 stage invokes no earlier stage and runs every required later stage.
- Resume from every canonical Gear 4 stage does the same.
- Either member of a pair maps to the whole pair.
- Later cycle names map to cycle 1.
- Gear 4 fallback that would cross the approved boundary fails explicitly rather than silently restarting Gear 3.
- Gear 3/Gear 4 verifier golden cases preserve current ordinary-run `BROKEN` behavior: candidate-pass unblocks, candidate-fail re-revises when a cycle remains, candidate-fail at cap continues, and separate gate-output/candidate digests remain exact. Final-quality `BROKEN` ships immediately without repair. A parallel fatal-control golden suite proves none of those transitions is entered after a bound resume stop.
- Empty correction adds no prompt text.
- Non-empty correction is exact, bounded, delimited, approval-bound, present in every resumed downstream model prompt, and labelled counterfactual.

### Fatal resume-control propagation

These are production-entry-point tests, not helper-only tests. Each case runs once through `server.py::_pipeline_stream` and once through `boot.py::run_pipeline`, with a fresh approved resume trace and a deterministic fake call graph. The test fixture records physical model calls, endpoint IDs, retry ordinals, provider-fallback selections, Supplemental RAG fetches/resubmissions, tool executions, agentic iterations, verifier classifications, repairs, Gear fallback calls, policy events, step health, and terminal manifest status.

| Injection point / representative call site | Fatal reason | Required assertions after the stop |
|---|---|---|
| Gear 3 analyst through `_call_with_supplement()` → `_call_with_retry()` first attempt | `RESUME_POLICY_VIOLATION` | Exactly one initial model attempt; no same-endpoint retry, provider fallback, Supplemental RAG retrieval/resubmission, tool execution, or agentic follow-up; no later evaluator/reviser stage; no unhealthy string or `BROKEN` substitution |
| Gear 4 paired analyst future and each `Future.result()` handler | `RESUME_ROUTE_POLICY_MISMATCH` | The fatal is re-raised from the worker/handler; pending sibling futures are cancelled and stopped at their next seam; no analyst fallback and no Gear 4-to-Gear 3 fallback; terminal `error` with missing-step derivation |
| Gear 3 verifier call and Gear 4 verifier futures | `RESUME_BUDGET_EXHAUSTED` | No second verifier physical attempt, no verifier `BROKEN` conversion, no re-revision/failure-reviser call, no next verifier cycle, no consolidation/quality stage, and no provider fallback |
| Gear 3 and Gear 4 quality-gate call sites | `RESUME_ROUTE_POLICY_MISMATCH` | No fail-open `BROKEN`, no quality re-revision, reconsolidation, reformat, scrub repair, or shipping; fatal reason is in step health and terminal manifest |
| Conditional Supplemental RAG request from an otherwise healthy analyst/evaluator/verifier | `RESUME_POLICY_VIOLATION` | Zero `_fetch_supplement()`/RAG queries and zero supplemental `_call_with_retry()` calls; one durable `supplemental-rag-refused` evidence event followed by the fatal stop; no tool or agentic iteration |
| Structured and textual tool-call response inside `_run_model_with_tools()` | `RESUME_POLICY_VIOLATION` | Zero `execute_tool_with_outcome()` calls, zero injected tool results, zero follow-up model iterations, one durable `tool-call-refused` event followed by the fatal stop |
| Claim-verification and any approved resumed web parallel future (`claim_verification.py` and the guarded `web_consultation.py` seam) | `RESUME_ROUTE_POLICY_MISMATCH` | Every `Future.result()` handler re-raises the fatal; no sibling aggregation, retry, web fallback, or later verifier/repair stage occurs. Ordinary Step 2 web consultation remains unbound and unchanged |
| Required policy-event append/read-back failure | `RESUME_POLICY_EVIDENCE_WRITE_FAILURE` | No claim that the refusal was durably recorded; independent `resume-control-failure.json` is attempted/read back; terminal `error` and visible evidence-unavailable result if both writers fail |

The same test matrix injects `RESUME_ROUTE_POLICY_MISMATCH` at the same-endpoint retry, provider fallback, truncation retry, and direct-vendor/prefer-direct fallback seams. Every counter remains at zero after the initial fatal. Tests also assert that `run_pipeline()` and `_pipeline_stream()` restore all ContextVars and that no fatal exception is caught by an inner stage handler. A control pair runs the same analyst/verifier/quality/future failures with no `ResumeExecutionPolicy` bound and asserts the current ordinary behavior—exception substitution, retries, provider fallbacks, `BROKEN` handling, repairs, and Gear fallback where current tests require them—remains unchanged.

### Hidden capability seams

- A primary response with no Supplemental RAG request performs no downstream retrieval and continues.
- A generated Supplemental RAG request performs zero vault/RAG queries and zero supplemental `_call_with_retry()` calls, records one bounded `supplemental-rag-refused` event, returns the exact `[Resume stopped: downstream Supplemental RAG was requested but is disabled.]` result, and finalizes `error`.
- Unconditional Supplemental RAG dependencies fail prepare before durable approval creation.
- Resume mode exposes no callable tools to the provider.
- Structured and textual mocked calls for both read-only and state-changing tools produce zero `execute_tool_with_outcome()` invocations and zero agentic follow-up model iterations.
- Tool requests record one bounded `tool-call-refused` event, return the exact refusal message, and finalize `error`.
- Policy-event append failure prevents Ora from claiming the retrieval/tool was refused and produces terminal `error` through durable finalization.
- Server and CLI tests prove the resume policy ContextVar is present at `_call_with_supplement()` and `_run_model_with_tools()`, and restored afterward.
- Ordinary full runs and trace probes retain existing Supplemental RAG and tool behavior when no resume policy is bound.

### Cost, capability, and approval

- Estimate includes retry/fallback maxima and all reachable model/read-only-web work.
- Unknown pricing is labelled unavailable, never zero.
- CLI accepts `--token-ceiling` and rejects `--cost-ceiling`; JSON persists integer `aggregate_token_ceiling`, unit `ora-estimated-input-plus-max-output-tokens`, and estimator policy version.
- Each physical attempt reserves deterministic estimated input plus effective maximum output before dispatch; retries/fallbacks are not refunded and a policy-version change invalidates approval.
- Conservative estimates include every conditionally reachable unhealthy-output retry. Rejected tools add no agentic follow-up budget, and Supplemental RAG adds no retrieval/resubmission budget because it is fail-on-request.
- Informational USD metadata cannot satisfy, replace, or alter the token ceiling.
- Forged ID/digest, unapproved, expired, replayed, cross-conversation, wrong operation kind, mutated source, mutated checkpoint, changed runtime, and changed cost/capability plan all fail before trace creation.
- Separate CLI and server processes using the same `ORA_HOME` can prepare, approve, and execute across process boundaries.
- Prepared, held, risk-cleared, and approved state survives process restart until absolute expiry.
- A different `ORA_HOME` returns authority mismatch and cannot recreate approval.
- Concurrent double execution from separate processes has one winner and one rejection.
- Probe approvals remain in process memory and retain their current complete-manifest digest; retention, child, or probe-ref mutation still invalidates them, and restart still loses them.
- With resume OFF, preparing, approving, and losing a probe across restart creates no durable approval directory or file.
- Resume approvals persist `resume-execution-projection-v1`; only child refs, probe refs, and retention may mutate without invalidation.
- Trace-creation failure makes no model/web request.
- Physical fallback/retry attempts consume separate approved budget.
- Budget exhaustion blocks the next physical request.
- Risk hold/denial is generated server-side and cannot be overridden by request JSON.
- Risk-held to cleared to approved continuation works with one exact operation-bound token.
- Risk clearance after approval expiry fails; clearance never extends expiry.
- Risk cancellation closes the Paused entry; cancelled/expired approvals cannot be reopened or replayed.
- Concurrent risk clearance consumes one token once and authorizes at most one unchanged operation.
- Visual, state-changing, and unknown external capabilities are refused.

### Manifest and lineage

- Server successful mid-pipeline resume produces one `resume` trace and one saved lineage-marked turn; CLI produces one trace and an exact returned trace-ref binding without claiming conversation persistence.
- Source child and resume parent refs are reciprocal, deduplicated, same-conversation, and durable.
- Appending resume lineage, probe lineage, or changing retention does not invalidate canonical source execution; changing any other manifest field does.
- `resume` sources are rejected with `CHAINED_RESUME_UNSUPPORTED`; resume traces contain no fresh checkpoints.
- Reused steps have source refs/digests and are absent from resume `actual_steps`.
- Recomputed steps contain only new trace-owned pipeline artifacts.
- Boundary-specific expected steps expose missing artifacts.
- Parent finalization/retention updates preserve resume child refs and unrelated fields.
- Private source produces private resume for server and CLI.
- Completed, provider error, budget error, trace write error, `KeyboardInterrupt`, and `SystemExit` produce durable completed/error/abandoned manifests with full expected/actual/derived derivation.
- A subprocess killed without running `finally` leaves an honestly `open` resume trace; no test or UI calls it abandoned.

### Production entry points

- `_pipeline_stream` happy path from a mid-Gear 4 boundary, including saved assistant trace ref.
- `run_pipeline` happy path from a mid-Gear 3 boundary.
- Both paths bind physical model-call and tool-event evidence to the resume trace, then restore outer context.
- Normally returned bracketed errors copy into turn state before finalization.
- Prepare/approval refusal creates no resume trace in either path.
- Both paths invoke one shared top-level `execute_resume()` fatal-stop converter. Production analyst, verifier, and quality-gate injections prove the fatal family is not caught by stage handlers, future handlers, provider wrappers, fail-open/BROKEN logic, repair/degradation, or Gear fallback; both finalize one terminal `error` resume manifest with durable stop evidence and no assistant success turn.
- A fatal stop from a parallel worker cancels pending siblings and prevents post-stop retries, provider fallbacks, Supplemental RAG, tools, agentic follow-ups, verifier repair, quality repair, and Gear 4-to-Gear 3 fallback in both entry points.

### UI and export

- Action availability updates after modal open, selected step changes, and stale trace expiry.
- Unsupported stages show reason and cannot prepare.
- Aggregate-token-unit/ceiling, physical-call, informational-currency, unhealthy-retry, Supplemental-RAG refusal, reject-all-tools, and approved-web confirmation appears before approval.
- Loading, invalid, stale, open, malformed, approval failure, risk hold, submission failure, completed submission, and counterfactual states are visible.
- Out-of-order eligibility, prepare, approve, and `/chat` responses cannot join trace A state to trace B.
- Focus trap, Escape, and focus restoration remain intact.
- Reused and recomputed sections are visually and semantically distinct.
- Exact parent/step refs are used; stale parent is a lineage gap, not guessed.
- Export keeps CSP/attachment protections and labels reused/recomputed/missing evidence honestly.

### Purge and retention

- Conversation purge physically removes source checkpoints, events, resume traces, and durable approval files.
- Conversation purge physically removes `resume-policy-events.jsonl` with its owning resume trace.
- Conversation purge physically removes an independent `resume-control-failure.json` fallback artifact with its owning resume trace.
- Closeout uses the unlocked pending-state helper while already holding lifecycle lock, with no deadlock.
- Startup/access performs synchronous expiry transitions and Paused cleanup without a scheduled loop.
- Source and resume pins remain independent.
- Approval-store root and conversation directories are `0700`; approval files are `0600` even under a permissive test `umask`.
- Symlinked approval roots, conversation directories, and files are rejected.
- An isolated repository-root `ORA_HOME` proves `/data/trace-operation-approvals/` is ignored with `git check-ignore` and absent from `git status --porcelain --untracked-files=all`.
- Private prepared requests/corrections remain in the private conversation's protected approval directory and are physically absent after purge.
- Stealth/missing sources create no approval directory or file.

### Protocol validation after implementation

- Adversarial self-review with every finding verified against source.
- Focused Python and jsdom suites.
- Fresh baseline and implementation full suites with `ORA_HOME` explicitly exported for both.
- Sorted FAIL/ERROR signatures byte-identical.
- Python/JavaScript syntax and `git diff --check`.
- Implementation packet and exact diff, followed by a stop for Codex code-review gate.

## 10. Acceptance criteria

1. With the feature flag enabled during capture, a completed text Gear 4 trace exposes mechanically verified resume eligibility at a mid-pipeline stage.
2. The user sees canonical boundary expansion, the named aggregate token unit/ceiling, physical-call ceiling, informational currency estimate, external capability plan, correction label, and expiry before approval.
3. One server-approved resume recomputes only the selected canonical stage through the end, creates one durable `resume` trace, and saves a normal assistant turn pointing to it.
4. Source and resume manifests have reciprocal exact lineage. Reused steps remain source references; recomputed steps are owned by the new trace.
5. A Gear 3 resume works through the CLI production entry point, returns a status/result string carrying the exact durable trace ref, and makes no unsupported claim that `run_pipeline()` itself saved an assistant turn.
6. Prepare in one process, restart, approve in another process, and execute in either server or CLI works through one durable authority when all phases share canonical `ORA_HOME`.
7. A correction is visibly counterfactual and cannot alter configuration or action authority.
8. Forgery, replay, expiry, cancellation, risk-hold misuse, mutation outside the three permitted manifest fields, runtime mismatch, missing checkpoint, unsupported action/visual work, and budget expansion fail before the relevant paid/external request.
9. Every unhealthy-output retry is tied to one exact logical-call route, same-endpoint/fallback condition, and pre-reserved token budget.
10. Supplemental RAG performs no mutable vault read during resume; a generated request produces one durable refusal event and the exact fatal stop result, or an evidence-unavailable terminal error if the required writer fails. Parsed tool calls invoke no tool and no agentic follow-up.
11. Private handling is inherited without downgrade.
12. Completed, error, and catchably abandoned resumes have durable full manifest derivation and honest missing-step rendering; uncatchable loss remains visibly open.
13. Trace Walk and hardened export label source, boundary, reused evidence, recomputed evidence, correction state, lineage gaps, and missing steps without guessing.
14. Ordinary full Gear 3/4 behavior remains parity-equivalent when resume is default OFF.
15. Server and CLI production tests cover successful lineage, cross-process approval, restart survival, Supplemental RAG refusal, and tool refusal, not only helper-created traces.
16. For each of `RESUME_POLICY_VIOLATION`, `RESUME_BUDGET_EXHAUSTED`, `RESUME_ROUTE_POLICY_MISMATCH`, and `RESUME_POLICY_EVIDENCE_WRITE_FAILURE`, both production entry points produce one terminal `error` resume manifest, typed fatal step health, durable stop evidence or an explicit evidence-unavailable result, and no same-endpoint retry, provider fallback, verifier/quality repair, Gear fallback, Supplemental RAG, tool execution, or agentic follow-up.
17. The persisted `UnhealthyOutputPolicy` is exact parity with `_step_output_health()`, including dispatch-noise normalization, the closed marker mapping, null/empty/short/refusal/clarification/dispatch-error classification, `verifier-envelope-v1`, `reviser-envelope-v1`, and all corresponding retry conditions; missing or unusable `## REVISED DRAFT` output is never considered healthy.

## 11. Open questions for the design gate

### Q1. Supported source kinds

Recommendation: authorize only text `chat-gear3` and `chat-gear4` traces in Chunk 4. Reject `resume`, `chat`, `clarification_resume`, `direct`, `framework-run`, `framework-milestone`, `trace-debug`, `trace-probe`, stealth/missing traces, and unknown kinds. Framework and chained resume require later designs.

### Q2. Step 1/2 behavior

Recommendation: keep Step 1 and Step 2 as whole-turn reruns. The Trace Walk action should say "Start a new turn" rather than "Re-run from here" for those steps because their retrieval/tool-routing state is not a downstream Gear checkpoint.

### Q3. Image and attachment inputs

Recommendation: return `NOT_RESUMABLE: MEDIA_SNAPSHOT_UNAVAILABLE` in Chunk 4. Do not persist copied media or depend on mutable external paths without a separately reviewed storage/redaction design.

### Q4. State-changing external actions

Recommendation: refuse them in Chunk 4 even if the ordinary historical turn used them. Only model calls and explicitly approved read-only web may proceed. Visual compute and write/publish/send/delete/tool-action replay need later capability-specific designs.

### Q5. Monetary estimates

Recommendation: when authoritative current pricing is unavailable, show input estimate plus hard model-call/output-token ceilings and require explicit approval. Do not block all resume solely because a currency conversion cannot be made, and never represent unknown monetary cost as zero.

Binding unit decision: Chunk 4 has no hard currency ceiling. Its only user cost ceiling is the aggregate token ceiling and unit defined in D6; monetary values are informational.

## 12. Design-gate decision requested

Approve, approve with modifications, or block this design before any runtime implementation begins. Approval of this document does not authorize vault edits, implementation landing, or enabling the feature by default.
