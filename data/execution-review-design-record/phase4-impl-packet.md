# Execution Review — Phase 4 Implementation Packet (Evaluation-lane router + polymorphic ExecutionPacket + packet-to-review renderer)

*Status: **REVISION 1** — the judge blocked Rev 0 with 2 narrow findings; both
folded + regression-tested. Awaiting the code-review gate. No commit yet. Built in
a fresh worktree off current `origin/main` (`0dda6ac6`, branch
`execution-review-phase4-impl`). All 4 required conditions folded; all 8
open-question answers honored; adversarial pre-check run each revision + folded.*

Design packet (approved-with-4-conditions): `/Users/oracle/ora-worktrees/phase4-design.md`.
Durable impl diff: `/Users/oracle/ora-worktrees/phase4-impl.diff` (7 files, +1037/-9,
whitespace-clean).

---

## 0. Revision 1 — the two judge findings, folded

**[F1 — P2] Gear-3 stale FAIL verdict on the post-redo deliverable.** The gear-3
quality gate fires a single FAIL redo (`boot.py:11571-11593`) with no re-gate, and
that redone text becomes the shipped deliverable — so the pre-redo `FAIL` no longer
describes it. **Fix:** inside the redo block, `context_pkg['execution_review']` is
overwritten with `{verdict: None, scope: "text_review", status:
"failed-then-redone-unreviewed"}` (a scoped status, no raw verifier text). The
packet's `verification` block now carries `status`; the renderer surfaces a
`=== TEXT-REVIEW STATUS (no verdict covers the shipped text) ===` fence when there
is no verdict but a status, so the final producer claim is never labeled with a
stale verdict. **Gear-4 verified free of the same bug:** its gate loops `range(3)`
with only 2 redo types, so every ship path (including the redo-spent path at
`boot.py:12993`) gates the shipped text. **Regression tests** in
`test_quality_gate.py::TestGear3VerdictThreadForPacket` (FAIL → unreviewed status;
PASS → PASS; BROKEN → BROKEN) + renderer/packet-layer tests.

**[F2 — P2] Silent packet-construction failures.** `build_execution_packet` /
`construct_and_write` swallowed build exceptions as a bare `None`. **Fix:** a new
`_mark_failure(err, where)` helper stamps `tool_events._note_failure` on any caught
**build/write exception** (`build_execution_packet` → `execution_packet_construct`;
`write_packet` → `execution_packet_write`; the wrapper → `execution_packet_construct_and_write`),
while **intentional skips** (no trace dir / empty output / `signals is None`) still
return `None` with **no** marker — the distinction the judge required. Each of the
three disjoint failure paths stamps **exactly once** (traced + test-locked). **Tests**
force a build exception, a write exception (`json.dump` raises), and a wrapper
exception — each asserting `failures == before + 1` — plus an intentional-skip test
asserting the count is unchanged.

**Rev-1 adversarial pre-check** (2 lenses over the delta × verify): 1 finding, a nit
(CONFIRMED) — the one-stamp-per-failure invariant was under-asserted
(`assertGreater` not `assertEqual`) and two failure paths were untested. Folded:
tightened all failure-observability assertions to `assertEqual(before + 1)` and
added the write-path + wrapper-path tests (above). No live defect; a test-quality
hardening. Rev-1 parity re-run stays clean (below).

---

## 1. What shipped (the delta)

Phases 1–3 built the observation substrate (every terminal turn folds a
`route_observed` carrying both §6 signals). Phase 4 makes the output **polymorphic**:
a new `ExecutionPacket` type + a packet-to-review renderer (§12) + an evaluation-lane
router (§5), constructed **at the terminal** from the already-folded signals plus the
in-gear text-review verdict. **Same downstream machinery, richer output — NOT a second
pipeline.** Text behaviour is byte-identical: the six in-gear review sites are
untouched, no new live model call, the renderer is a library function proven by test.

New consolidated module `orchestrator/execution_packet.py`:
- `ExecutionPacket` dataclass — every §9 block **reserved** (task / planning / execution
  / evidence_lanes / judgment_lanes / verification / loop / persistence), tier-optional,
  `frontmatter()` returns flat scalars only, large artifacts held as refs (delta.ref) +
  producer_claim capped.
- `EvidenceLane` (target / lane / `generated_by` / result / **tri-state** `sufficient`)
  and `JudgmentLane` (target / critique — **no verdict field**, §5 structural separation).
- `render_for_review` (evidence-first / claim-last, loud "NO ACCEPTANCE CRITERIA"
  banner, scoped "TEXT-REVIEW VERDICT (does not cover …)" line, unfilled lanes render
  "not yet generated", banner fences); `_format_artifact_for_review` (side-effect-free
  identity on `str`).
- `route_lanes` (signals → evidence lanes; judgment lanes from mode-declared targets
  only); `consistency_note` (record-only §6 declared-vs-observed); `all_evidence_sufficient`
  (empty/unfilled ≠ passed); `build_execution_packet` (never raises) + `write_packet`
  (trace-local, observable failure) + `construct_and_write` (the guarded terminal one-liner).

Wiring:
- `risk_gate.record_route_observed` — single fold; gains `declared_output_type`
  (default `unknown`, raw, never rewritten); records `output_type` + the consistency
  note on the event; returns them. **No packet ref on `route_observed`** (condition 1).
- `tool_events` — truncation keep-set gains `output_type` + `consistency`.
- `boot.py` / `server.py` — the verdict LABEL is threaded onto
  `context_pkg['execution_review']` at each quality gate; the packet is built at the
  terminal from `record_route_observed`'s returned signals, guarded to a real
  deliverable + trace dir + non-stealth.

## 2. How the four judge-required conditions are met

**Condition 1 — packet/ref ordering (no double-fold, no ref on route_observed).**
Chose the judge's option (b): `record_route_observed` folds **once** and records
`route_observed` first (now also carrying `output_type` + the consistency note);
the terminal then builds the packet **separately** from that call's returned
`signals` dict (`_ro["signals"]`) — no re-fold. **No packet ref is placed on the
`route_observed` event.** The packet is a standalone trace-local artifact that
references the turn via its trace dir; it is not indexed on `route_observed`.

**Condition 2 — narrow, trace-local storage.** `write_packet` writes
`execution-packet.json` **into the trace dir only** — `persistence.tier =
"trace_local"`. `construct_and_write` returns `None` (no packet) when there is no
`trace_dir` (tracing off → no new runtime store invented) or no real deliverable;
the terminal additionally gates on `not stealth` (stealth turns get no packet,
inheriting the Phase-1/2/3 model). Nothing is written to the vault or a durable
store; Phase 7 owns durable tiered persistence. `producer_claim` (possibly private)
therefore lives only where the trace already holds the full deliverable.

**Condition 3 — explicit `output_type` plumbing, raw hint never rewritten.** The
terminal passes `declared_output_type=context_pkg.get("output_type", "unknown")`
into `record_route_observed`, which records it verbatim and returns it; the packet
frontmatter carries it as the RAW hint. The observed reality-contact character lives
separately in `execution` / `observed`; the consistency note reconciles them **without
ever writing the observed value back** into `output_type`. Default `unknown` → the
assertion is dormant on every live P4 turn (test-only firing).

**Condition 4 — safe verdict thread.** `run_gear3`/`run_gear4` stash **only the
verdict LABEL** (`PASS`/`FAIL`/`BROKEN`) on the namespaced
`context_pkg['execution_review']` subdict — no raw verifier prose is copied in
(test asserts it). It is scope-labeled `"text_review — does not cover state changes
or provenance"`. No prompt-assembly path reads this new key (grep-verified;
`build_system_prompt_for_gear` and the step prompt builders read specific keys, not
this one), so there is no leak into later prompts. producer_claim is capped
(`_PRODUCER_CLAIM_CAP`), task instruction capped, source_reads reuse the Phase-3
public-safe descriptors.

## 3. Open-question answers honored (all 8)
1. **Architecture A** — type + renderer + router as a library; packet constructed
   live at the terminal; the renderer proven by a rendered-string test into the real
   evaluator prompt shape; **no** live packet review, **no** six-site seam edit.
2. **`output_type` unset** — introduced defaulting to `unknown`; consistency
   assertion exercised in tests only (dormant live).
3. **Gears keep returning `str`** — verdict threaded via `context_pkg`, packet built
   at the terminal; zero gear return-type change.
4. **Evidence lanes declared-empty** — tri-state `sufficient`; unfilled/empty ≠
   sufficient, pinned at the data layer + tested.
5. **Consistency assertion record-only** — appended to the `route_observed` event; no
   tier change, no enforcement.
6. **`JudgmentLane` defined, not mass-populated** — no verdict field; empty unless a
   mode declares interpretive targets.
7. **One consolidated `orchestrator/execution_packet.py`** — names/enums flagged provisional.
8. **Verdict threaded via `context_pkg['execution_review']`** — label-only, scope-labeled,
   no leak, capped (the condition-4 safety constraints).

## 4. Adversarial pre-check (ONLY the changed logic — 3 lenses × adversarial verify; 4 raw findings; folded)
Ran a small workflow attacking the changed fold + wiring against the 4 conditions +
safety invariants; each finding re-verified against the code by hand (majority
under-reports).
- **[P4-1 doc/code mismatch — CONFIRMED, folded]** the module docstring said the
  packet is "built at the two gear terminals," but construction sits at the single
  `run_pipeline` / `_run_pipeline_from_step2` terminal reached by **every** non-hold
  gear (1/2/3/4/bare); gear-1/2 turns carry `text_review_verdict=None`. Harmless
  (trace-local, rendered gracefully, holds excluded) and arguably *more* spec-correct
  (a gear-2 grounded lookup is non-self-evidencing) — **folded the docstring** to
  describe the shipped behaviour accurately, incl. that non-gate paths carry an honest
  null verdict (this also folds F1's documentation point).
- **[F1 verdict-null on non-gate paths — REJECTED, not a defect]** gear-1/2, the gear-3
  single-model fallback, and the gear-4 external-consolidation handoff carry
  `verdict=None`. Re-verified: `None` is the HONEST value (no review gate ran on those
  paths — the single-model fallback is analyst-only; external_consolidation hands the
  gate to the MSI caller), the renderer omits the text-review line, and `context_pkg`
  is fresh per turn (no stale/cross-turn verdict). Documented via the P4-1 docstring fold.
- **[P4-2 fold-failure → signals=None → packet built — REJECTED, hardened anyway]**
  re-verified impossible: `fold_route_observed` never returns `None` (always returns
  its defaults dict), and a real mutation *sets* `any_mutation=True` in that dict, so
  "mutation observed but signals=None" can't occur. Added a cheap **`if signals is None:
  return None`** guard in `construct_and_write` as explicit hardening (keeps "packet ⇒
  successful fold" true if that ever changes) + a test.
- **[F2 `reversible` marks high-risk reversible — REJECTED (I overturned the
  real_defect flag), clarified]** re-verified against the spec: §9's `reversible`
  gates **post-hoc routing** (§6: "permitted inside reversible tiers only"), and the
  only non-reversible tier is `irreversible` (high-risk carries a rollback check, §8),
  so `risk_tier != "irreversible"` is **spec-correct** — the verifier's proposed fix
  (marking high-risk non-reversible) would be wrong. Added a §6 clarifying comment +
  a test asserting high-risk is reversible and irreversible is not.

## 5. Files changed
| file | change |
|---|---|
| `orchestrator/execution_packet.py` | NEW consolidated module (packet + lanes + renderer + router + consistency note + builder/writer) |
| `orchestrator/risk_gate.py` | `record_route_observed` single-fold + `declared_output_type` + record-only consistency note + `output_type`/`consistency` on the event and in the return |
| `orchestrator/tool_events.py` | truncation keep-set gains `output_type` + `consistency` |
| `orchestrator/boot.py` | verdict-label stash at gear-3 + gear-4 quality gates; **Rev 1:** gear-3 redo unreviewed-status overwrite; terminal packet construction (guarded, non-stealth) |
| `server/server.py` | terminal packet construction on the pipeline-stream path (guarded, non-stealth) |
| `orchestrator/execution_packet.py` (**Rev 1**) | `_mark_failure` helper + observable build/write/wrapper failure stamps; `verification.status` field + renderer `TEXT-REVIEW STATUS` fence |
| `orchestrator/tests/test_execution_packet.py` | NEW — 55 tests |
| `orchestrator/tests/test_quality_gate.py` (**Rev 1**) | +`TestGear3VerdictThreadForPacket` (3 — the exact redo path) |

## 6. Tests + parity
- **New:** `test_execution_packet.py` — **55 tests** (packet shape / reserved §9
  blocks / flat frontmatter / capped artifacts; lane router + structural separation;
  tri-state `sufficient`; the renderer incl. the **Rev-1** unreviewed-status line;
  rendered-string acceptance into the real evaluator prompt shape; side-effect-free
  `str` seam; record-only consistency note; verdict threading label-only;
  output_type-never-rewritten; construction guards; **Rev-1** exactly-one-stamp
  observability across all three failure paths + intentional-skip stamps-nothing;
  high-risk-reversible; risk_gate integration + keep-set survival). Plus
  `test_quality_gate.py::TestGear3VerdictThreadForPacket` (**Rev 1**, 3 — the gear-3
  FAIL-redo verdict-status regression).
- **Focused** (`test_execution_packet` + `test_quality_gate` + `test_risk_gate` +
  `test_tool_events` + `test_risk_gate_pipeline`): all pass.
- **Full-suite parity** (`ORA_PIPELINE_TRACE=off ORA_TOOL_EVENTS=off`, discover):
  baseline `0dda6ac6` = **22F/5E** (27 pre-existing environmental — lens-integrity,
  retry-fallback, openai-images, mode-relationship-priorities, user-settings,
  visual-routing). Definitive Rev-1 run = **3721 tests (3663 + 58 new), 22F/5E
  identical to baseline — NEW failures = 0, disappeared = 0** (verified by diffing
  sorted FAIL/ERROR name lists branch-vs-baseline).

## 7. Scope discipline (unchanged from the approved design)
No real evidence generation (Phase 5), no claim-to-source map / precise source_read
labeling (Phase 8), no live model-review of a packet / full loop (Phase 6), no edit
to the six in-gear review sites, no packet on hold/direct-stream/framework paths, no
before-clock change, no MSI adapter work, no new redaction surface (source_reads reuse
the Phase-3 public-safe descriptors; large artifacts referenced not inlined).
