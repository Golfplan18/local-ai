# Execution Review — Phase 3 Implementation Packet (Universal Capture)

*Status: IMPLEMENTED, awaiting the judge's code-review gate. No commit yet
(per the working model). Built in a fresh worktree off current `origin/main`
(`aec67200`, branch `execution-review-phase3-impl`). Both judge-required
conditions folded; all 6 open-question answers honored.*

Design packet (approved): `/Users/oracle/ora-worktrees/phase3-design.md`.
Durable impl diff: `/Users/oracle/ora-worktrees/phase3-impl.diff`.

---

## 1. What shipped (the delta from Phase 2)

Phase 2's after-clock `route_observed` folded signal 1 (what changed:
`any_mutation`/`max_mutability`) and a raw `reads_present` boolean. Phase 3
adds §6 **signal 2** — the coarse SOURCE-READ over-approximation ("did the
output make claims about material it read?", excluding `local_context_read`) —
as additive fields on the same `route_observed` event, and threads the produced
output into the fold so the "makes claims" test can run. Precise per-claim
`source_read` labeling + the claim-to-source map (§4) remain deferred to Phase 8.

New `signals` keys (additive — no Phase-2 key renamed):
- `source_read_suspected: bool` — the §6 signal 2.
- `source_read_channels: list[str]` — the source-eligible channels that fired.
- `source_candidate_reads: list[dict]` — public-safe descriptors for Phase 8.
- `source_candidate_reads_truncated: bool` — set when the list was capped.

## 2. How the two judge-required conditions are met

**Condition 1 — allowlist + actually-ran (`_source_read_kind`, risk_gate.py).**
An event counts as a source read only if: its `action` is in an explicit
allowlist (`_ALWAYS_SOURCE_ACTIONS` = web_fetch/web_search/knowledge_search/
rag_read; `_AMBIGUOUS_LOCAL_ACTIONS` = file_read/search_files/list_directory;
or a `bash:*` read), `mutability == "read"`, `exit.ok` is truthy (it actually
ran), and the gate decision is not blocked/queued. Internal telemetry
(`task_tier`/`acceptance_criteria`/`route_observed`/`task_execute`/`model_call`/
`credential_store`) is explicitly excluded (`_NON_SOURCE_ACTIONS`) — belt on top
of the allowlist, which already omits them.

**Condition 2 — no private→public downgrade (`_public_safe_candidates` +
`record_route_observed`).** BOTH halves of the judge's "and/or":
- the recorded `route_observed` event's `sensitivity`/`egress` now reflect the
  folded max (honest classification) instead of hardcoded `public`; and
- `source_candidate_reads` is public-safe by construction — a read's `what`
  descriptor (path/URL/query) rides in ONLY when that read's own event
  sensitivity is `public` (deferring to the existing per-event classification,
  which already scrubbed it at write); `action`/`where`/`content_hash`/`chars`
  are tool-name/enum/truncated-hash/count values and are always safe.
This closes the leak even though `_redact_for_record` does not recurse into
`route_signals`.

## 3. Open-question answers honored
- **Q1=A:** ambiguous local reads over-approximate to source; no per-target
  read/write tie-break (the unsound fold-wide-max heuristic was never built).
- **Q2:** shell/search/list reads fold by event action (`bash:*` + read); no
  dispatcher `reads[]` change.
- **Q3:** `rag_read` trips signal 2 on substantive RAG-grounded output, across
  gears.
- **Q4:** the boot.py framework `return-in-finally` was refactored to capture
  `_fw_out` and pass it as `output_text` — the lone output-unavailable path
  removed.
- **Q5:** stealth accepted — no stealth-scoped capture; the limitation is that a
  stealth turn's route_observed (and its tool events) are suppressed at write,
  so signal 2 is not observed there. Stated, not silent.
- **Q6:** provisional thresholds (`_MIN_SUBSTANTIVE_OUTPUT_CHARS = 24`,
  `_MAX_SOURCE_CANDIDATES = 64`) shipped with tests + a calibration note; the
  concurrent-sibling low-water window left as an inherited limitation.

## 4. The self-initiated robustness fold (truncation)
`route_observed` events over `tool_events.MAX_LINE_BYTES` (8 KB) have their
whole `route_signals` block dropped by the truncation keep-set — which would
lose the load-bearing `source_read_suspected` boolean on a very heavy turn.
`source_candidate_reads` is therefore capped at `_MAX_SOURCE_CANDIDATES` (64) and
the cap is FLAGGED (`source_candidate_reads_truncated`), never silent — keeping
the event well under 8 KB so the routing signal always survives. The
boolean/channels are computed from booleans, not the capped list, so the cap
never affects routing; Phase 8 rebuilds the full map from the per-event log.

## 5. Files changed
| file | change |
|---|---|
| `orchestrator/risk_gate.py` | source-read allowlist + `_source_read_kind` (incl. MCP-read branch) + `_public_safe_candidates` + `_output_is_substantive`; `fold_route_observed(output_text=)` accumulation, strong-vs-ambiguous suspected logic, candidate cap+flag; `record_route_observed(output_text=)` honest sensitivity capped at `sensitive`, verdict promoted top-level |
| `orchestrator/tool_events.py` | truncation keep-set gains `source_read_suspected` / `risk_tier` / `divergence` so the routing verdict survives a byte-truncated record |
| `orchestrator/boot.py` | main terminal passes `output_text=response`; framework `return-in-finally` refactored to capture `_fw_out` |
| `server/server.py` | pipeline (`response`), framework success (`result_text`), both `_direct_stream` exits (`clean`) pass output |
| `orchestrator/framework_elicitation.py` | deliverable path inits `result=None`, passes `format_execution_result(result)` |
| `orchestrator/tests/test_risk_gate.py` | +`TestSourceReadSignal` (28 tests) |
| `orchestrator/tests/test_tool_events.py` | +1 truncation-survival test for the routing verdict |

## 6. Tests + parity
- New: `TestSourceReadSignal` — 28 tests covering channel classification,
  actually-ran/allowlist exclusion (blocked/queued/errored/telemetry), Q1-A
  local over-approx, Q3 rag_read, MCP read-as-strong (short + substantive
  suspect, empty + write do not), output-None fallback, strong-channel
  short-output suspects / empty does not, public-safe candidate shape (public
  keeps `what`, private/sensitive drop it), honest event sensitivity capped at
  `sensitive`, top-level verdict promotion, the cap+flag, additive shape /
  back-compat — plus 1 truncation-survival test in `test_tool_events`.
- Focused (`test_tool_events` + `test_risk_gate` + `test_risk_gate_pipeline` +
  `test_dispatcher_gate`): **193 pass**.
- Full-suite parity (`ORA_PIPELINE_TRACE=off ORA_TOOL_EVENTS=off`, discover):
  baseline `aec67200` = 22F/5E (27 pre-existing environmental — lens-integrity,
  retry-fallback, openai-images, mode-relationship-priorities, user-settings,
  visual-routing). Post = **3661 tests** (3634 + 27 new), **22F/5E identical to
  baseline — NEW failures = 0, disappeared = 0**.

## 7. Adversarial pre-check (ONLY the changed logic — 3 lenses × adversarial verify; 6 raw, all CONFIRMED, 0 rejected; then folded)
Ran a small workflow attacking only the changed fold + wiring against both
judge conditions, each finding adversarially verified against the code. All 6
confirmed; I re-checked each myself and folded the 5 real distinct ones (two
lenses reported the same MCP issue):

- **[MCP read channel — folded; strengthened at code-review]** `_source_read_kind`
  had no MCP branch, so an instrumented read-only MCP connector (`event=='mcp'`,
  `mutability:read`) would never trip signal 2 — the unsafe under-route
  direction. Latent today (no shipped MCP server is read-class), fixed now: MCP
  reads fold as a **STRONG** source channel (`"always"`). The judge's code-review
  caught that an interim `"ambiguous"` classification still subjected MCP to the
  24-char floor (MCP read + `Yes.` → not suspected); strong classification
  applies the §6 asymmetry (a terse grounded answer after opaque external
  contact still suspects). +4 tests (read counts, write does not, short output
  suspects, empty does not).
- **[secret-stamp contract — folded]** a `secret` event in the window (e.g. a
  `credential_store` op) made the fold stamp `route_observed` as `secret`, whose
  "existence-only / never-in-a-packet" contract the redactor then half-applies
  (it doesn't recurse into `route_signals`) while the public-safe payload
  persists. Fixed: the stamped sensitivity is capped at `sensitive` (the secret
  fact is still recorded inside `route_signals.max_sensitivity`). +1 test.
- **[short-output under-route — folded]** the 24-char substantive floor could
  under-route a terse grounded answer ("4.1%") after a strong read. Fixed by the
  §6 asymmetry: a strong channel (web/knowledge/rag/MCP) + any non-empty output
  suspects regardless of length; the floor now applies only to ambiguous-local-
  only turns. +2 tests (short suspects, empty does not).
- **[truncation of the routing verdict — folded]** the 64-candidate cap reduces
  but can't fully eliminate a >8 KB `route_observed` whose whole `route_signals`
  (incl. the verdict) is dropped by the truncation keep-set. Fixed by promoting
  `source_read_suspected` to a top-level event field and adding it (+`risk_tier`
  /`divergence`) to the keep-set, so the verdict always survives. +1 test.
- **[web_search query descriptor — accepted, documented]** a public-classified
  `web_search` query can carry a non-credential-sensitive term that rides into
  the public descriptor. Accepted (not folded): the query already lives at equal
  public sensitivity in its own source event's log line, so the summary adds no
  new exposure; over-routing is safe. Flagged as a residual for a future
  per-read (vs per-event) sensitivity tightening.

## 8. Scope discipline (unchanged from the approved design)
No claim-to-source map, no precise source_read labeling, no ExecutionPacket /
lane router / output_type gate, no excerpt capture, no model call, no
before-clock change. All Phase 4/8.
