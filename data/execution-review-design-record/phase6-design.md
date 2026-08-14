# Execution Review — Phase 6 Design Packet (Wire the loop + governance + stop rule)

*Spec §15 Phase 6. Scoped by §3 (core architecture — the single-writer-execution /
multi-agent-judgment loop), §12 (governance), §13 (stop rule + escalation), §8 (risk
tiers + criteria-source scaling), §5 (evaluation lanes), §9 (the ExecutionPacket
loop/verification/execution fields Phase 6 finally populates), §16 (the three
load-bearing invariants held live).*

*Working model: this thread implements; a separate judge thread reviews at gates; NO
code is written until the judge approves this design. This is a DESIGN packet only.
Substrate scouted read-only in the pinned worktree
`/Users/oracle/ora-worktrees/phase6-scout` (detached @ `ffea2b4e` = current
origin/main = the Phase-5 landing / PR #185). All file:line references below were
verified by hand against that worktree.*

---

## 0. The one-paragraph statement of Phase 6

Phase 6 assembles the execution-review **loop** — dual plan → converged brief +
contract → single executor → mechanical **Capture** → dual **Verify** (different model
family, with the single-family graceful-degrade) → **revision router** (findings
tagged plan-level vs execution-level) → **stop rule** (converge or escalate, never
churn) with the abandoned attempt on an inspectable, unmerged branch the packet links
to — **entirely from parts already present** (§4 "same downstream machinery, NOT a
second pipeline"). Nothing here is a new gear pipeline: the planning pass is the
already-live `apply_criteria` + `apply_evidence_contract`; the execute+revise actuator
is the existing `run_gear3`/`run_gear4`; the Capture tool is the Phase-5
`evidence_runner`; the review surface is the Phase-4 `render_for_review`. Phase 6 makes
LIVE the two pieces built-but-unwired — the Phase-4 renderer (governs no live review
until now) and the Phase-5 runner (drives no check until now) — and **populates** the
§9 packet blocks Phase 4 reserved (`loop`, `verification.reviewer_a/b/findings[].class/
invented_tests[].kind/confidence`, `execution.mode/state_before/state_after`,
`planning.converged_brief.acceptance_criteria`). The recommended architecture is a
**loop CONTROLLER anchored at the terminal with a planning-stage pre-execution state seam**
(⚖ Rev-1, judge P0 — a terminal-only design cannot capture a true `state_before` or a correct
escalation-branch base; the pre-execution snapshot is captured at planning, before the actuator
runs). It engages only for non-self-evidencing turns (§6 signal fired): the common
analytical-prose turn is self-evidencing and degrades gracefully to the gear's own text review
with a richer *record* packet (byte-identical output, zero regression). The full
Capture→verify→revise→stop/escalate machinery fires on a **mutation** turn (the adapted
`diff_validate` lane); a **source-read-only** turn records the packet with an owed
`collect_provenance` lane + a loud deferred-provenance marker and does NOT enter the
converge/escalate cycle (⚖ Rev-1, judge P1 — its lane is Phase-8-owed, so escalating it would
churn). This packet states honestly what becomes **live** (the mutation/`diff_validate` loop),
what is **recorded-and-deferred** (source-read provenance → Phase 8), and what stays
**scaffolding** for Phase 7/8.

---

## 1. Substrate scout — evidence (file:line, all @ `ffea2b4e`)

### 1.1 The gear produce→verify→revise cycle Phase 6 REUSES (not rebuilds)

Both gears already ARE a produce→verify→revise engine with a bounded correction loop.
Phase 6 does not build a second one (§4).

- **`run_gear3`** (`orchestrator/boot.py:11059`): Step 3 analyst (depth) → Step 4
  evaluator (breadth) → Step 5 reviser (depth) → **Step 6 per-stream verifier**
  (breadth, `for cycle in range(MAX_VERIFY_CYCLES + 1)` = up to 2 re-revisions,
  `boot.py:11406`) → **Step 6.5 final-output quality gate** (verification slot, one
  bounded reviser redo on FAIL). Returns the reviser's `## REVISED DRAFT` body.
- **`run_gear4`** (`orchestrator/boot.py:11704`): parallel analysts (Step 3,
  `ThreadPoolExecutor` @ `11858`) → cross-eval (Step 4, `11958`) → parallel revise
  (Step 5, `12095`) → **Step 6 cross-verify** (`range(MAX_VERIFY_CYCLES=2)` @ `12252`,
  nested re-revision executor @ `12485`) → Step 7 consolidator (sequential, `12566`) →
  Step 8 formatter (sequential, `12690`) → **Step 8.6 final quality gate**
  (`range(3)` @ `12843`, redo routed by `_parse_quality_gate_problem` @ `10018` back to
  step 7 or step 8). **Gear 4's parallelism is parallel *analysis* that converges at the
  single sequential consolidator (Step 7)** — it is NOT parallel *execution* of a
  mutating actuator (§3 "single-writer execution" holds; the merge points are exactly
  planning-fan-in at Step 7 and verify-fan-in at Step 6, the two cheap-merge points §3
  names).
- **The single verdict parser** is `_verifier_passed` (`boot.py:9967`, three-way via
  `_extract_structured_verdict` @ `9932` + `_verifier_broken` @ `9855`): line-anchored
  `VERDICT:` token → PASS | FAIL | BROKEN | None. **BROKEN ≠ FAIL** (BROKEN = verifier
  transport/exception; unblocks the cycle if the revised output is structurally sound;
  FAIL fires re-revision). Phase 6 must not conflate them.
- **The gear already stashes a text-review verdict label** onto
  `context_pkg["execution_review"]` (gear3 @ `boot.py:11581`; gear4 @ `12883`), scoped
  `"text_review"` — this is the Phase-4 wiring the packet's `verification.text_review_verdict`
  reads. On a gear-3 quality-gate FAIL redo it overwrites with `{"verdict": None,
  "status": "failed-then-redone-unreviewed"}` (`11612`).

### 1.2 The terminal packet build + the Capture-timing decision

- The ExecutionPacket is built at the **pipeline terminal** — `boot.py:9429`
  (`record_route_observed`) → `9445` (`construct_and_write`), twinned at
  `server.py:2979`/`2991`. This is **AFTER** the gear (including its internal prose
  verify) has finished; the packet is currently a post-hoc *record*
  (`build_execution_packet` sets `planning=None`, `loop=None` — `execution_packet.py:400`,
  `405`).
- Guards: `if not stealth:` (`boot.py:9440`); `construct_and_write` further guards on
  `trace_dir` present + `output_text` non-empty + `signals` non-None
  (`execution_packet.py:448`).
- **In scope at the terminal**: `response` (the deliverable text, `boot.py:9433`);
  `_ro` (the folded signals + consistency, `9429`); `context_pkg["risk_tier"]`
  (`9285`); `context_pkg["trace_dir"]` (set @ `boot.py:7810`, read inside the gears @
  `11136`/`11791`, per-turn unique + writable); `context_pkg["acceptance_criteria"]`
  (set by `apply_criteria` @ `risk_gate.py:952`); `context_pkg["evidence_contract"]`
  (set by `apply_evidence_contract` @ `9331`); `context_pkg["output_type"]` (raw hint).
- **What is NOT in scope at the terminal**: a `repo_root`, a git-worktree handle, or the
  gear's intermediate artifacts (`revised_analysis` etc. are function-local to the gear).
  The Capture step must discover `repo_root` itself (the runner's `discover_catalog` does
  this — `evidence_runner.py:272`).

### 1.3 The planning stage is ALREADY live (§8/§16-1/§16-2)

Both siblings run at planning, BEFORE the executor, additive, never-raise:
- **`apply_criteria`** (`risk_gate.py:935`, called `boot.py:9304` / `server.py:2857`):
  produces + stashes `context_pkg["acceptance_criteria"]` (`risk_gate.py:952`); returns
  a `None`/`WARN:`/`HOLD:` directive; standard+ only. **This is §16-1 already satisfied:
  criteria set by a step prior to and separate from execution.**
- **`apply_evidence_contract`** (`evidence_runner.py:862`, called `boot.py:9331` /
  `server.py:2877`): discovers the catalog, invokes the sidebar-slot model to author the
  task-specific Evidence Contract, stashes `context_pkg["evidence_contract"]` =
  `{required_standard_checks, bespoke_probes, sufficiency, repo_less}`; returns a
  directive. **This is §16-2 already satisfied: the recipe declared independently of the
  executor.** Both are driven by the SAME `_make_criteria_invoker(config, config_name)`
  callback (`boot.py:9306`/`9331`).

### 1.4 The Phase-5 runner driver surface (Capture) + the git escalation primitive

The Capture step's call sequence is fully present and never-raises
(`orchestrator/evidence_runner.py`):
- `snapshot_before(repo_root, mode)` → `{head, tree, dirty_hash, mode}` (`:948`).
- `run_contract(catalog, contract, repo_root, worktree=, mode=)` → `list[CheckResult]`
  (`:1022`) — runs the Contract's `required_standard_checks` ENFORCE-OR-REFUSE; a
  required check missing from the catalog is recorded as a refusal + a tool-event
  (`:1035`). `run_check` (`:675`) records exactly one `evidence_check` tool-event per
  outcome (§16-3 observed-not-narrated).
- `snapshot_after(repo_root, mode, trace_dir, before)` → `(state, delta_ref)` — writes
  the `git diff` to `trace_dir/evidence-diff.patch`, a *reference* never inlined (`:955`).
- `fill_evidence_lanes(packet, results, contract, delta_ref)` — fills the
  `diff_validate` `EvidenceLane`'s `generated_by`/`result`/`sufficient` (`:997`).
- `contract_sufficient(results, contract)` — **True only when EVERY Contract-required
  check ran (not skipped) and passed; empty required list → False; refused/failed/absent
  → not sufficient** (`:978`). This is the machine-readable stop-rule input;
  `all_evidence_sufficient(lanes)` (`execution_packet.py:97`) is its lane-level twin
  (empty lanes ≠ vacuously passed). **Absence ≠ pass** is enforced in BOTH.
- **Enforcement honesty**: `CheckResult.enforcement_model` is `orchestrated` (verified
  kernel isolation: macOS `sandbox-exec` / Linux `unshare -rn`), `declared-sandbox`
  (operator-attested `ORA_EVIDENCE_SANDBOX` wrapper — weaker confidence), or `None`
  (refused). A refused check carries `skipped=True` + `skip_reason` (`:591`).
- **The git escalation primitive**: `_git(repo, args)` (`:927`) is the subprocess
  helper (mirrors `engram_promotion._git`); `snapshot_before` captures the pre-execution
  HEAD SHA. §13's inspectable-unmerged-branch is created FROM this SHA via `_git`
  (`git branch <name> <sha>` / `git worktree add`). **Gotcha (scout-verified):** the
  runner has NO branch-*keeping* logic today — the sandbox tmp worktrees are
  `shutil.rmtree`'d in a `finally` (`:785`). Phase 6 must CREATE + KEEP the escalation
  branch explicitly; it is not a byproduct of the runner.
- **Dirty-state modes**: only `clean_worktree` is gated today (mutating checks refuse
  unless `mode == "clean_worktree"`, `:695`); `review_dirty_diff` / `continue_user_changes`
  are declared in the docstring but are Phase-6 semantics (see P1/OQ7).

### 1.5 The Phase-4 renderer + the reserved §9 fields Phase 6 fills

- **`render_for_review(packet)`** (`execution_packet.py:236`, **tested-but-unwired — no
  live caller**): emits five fences in review order — TASK, ACCEPTANCE CRITERIA (or a
  LOUD "NO ACCEPTANCE CRITERIA DECLARED" absence fence, `:255`), **OBSERVED EVIDENCE
  first** (`_render_evidence` @ `:203`), scoped TEXT-REVIEW VERDICT/STATUS, and the
  **UNVERIFIED PRODUCER CLAIM last** (`:283`). It already reads
  `packet.planning.converged_brief.acceptance_criteria` (`:251`) and the evidence lanes
  — so it is genuinely wire-not-build once Phase 6 populates those blocks.
- **The fields Phase 6 fills** (all reserved-empty at P4 — `build_execution_packet`,
  `execution_packet.py:322`):
  - `planning` = `None` (`:400`) → Phase 6 fills `converged_brief.acceptance_criteria`
    (from `context_pkg["acceptance_criteria"]`), `evidence_contract` (from
    `context_pkg["evidence_contract"]`), and (dual at high-risk) `planner_a`/`planner_b`.
  - `verification.reviewer_a/reviewer_b/confidence` = `None`; `findings`/`invented_tests`
    = `[]` (`:348-349`) → Phase 6 fills.
  - `loop` = `None` (`:405`) → Phase 6 fills `iteration`/`stop_condition`/`escalation`.
  - `execution.mode`/`state_before`/`state_after` = `None` (`:361`) → filled from the
    runner snapshots; `enforcement_model` = `"in_harness"` with the literal comment
    *"§7 — TODO owned by the P6 enumeration"* (`:352-355`) → Phase 6 sets the honest value.
  - `evidence_lanes[].generated_by/result/sufficient` → filled by `fill_evidence_lanes`.

### 1.6 The model-family substrate (§12) — training_family ALREADY exists

- Every endpoint carries **`provider`** and **`training_family`**
  (`config/routing-config.json`: `qwen`/`llama`/`claude`/`gpt`/`gemini`/… — e.g.
  `:150`, `:174`, `:292`). Closed/commercial models resolve family via
  `config/family-classification.json`.
- `router._generate_warnings` (`router.py:1194`) already **detects** same-provider /
  same-model / **same-family** (`training_family` equality @ `:1228`) between the depth
  and breadth slots — but it is **advisory only** (emits a `Warning`, does not enforce or
  select). `config.diversity` (`routing-config.json`) is `{"enabled": true}` and, in
  `resolve_endpoint`, already excludes the depth model from breadth resolution.
- The executor's family = the resolved `depth`/analyst slot's `training_family`; the
  verify slot = `verification` (post-analysis), resolved once before the loop (gear3 @
  `boot.py:11537`, gear4 @ `12834`), **falling back to `breadth_endpoint` when the
  verification slot is empty** (scout gotcha: this silent fallback can defeat a
  different-family requirement).
- **Conclusion:** the *data* for "different family" exists; Phase 6 adds a **selector**
  (pick a verify endpoint whose `training_family` ≠ the executor's) + a **detector**
  (single-family = no configured/available endpoint differs from the executor's family).
  It does NOT add new model metadata.

### 1.7 The §15 Phase-0 audit — which paths the loop reaches (MSI stays Phase 8)

Re-run @ `ffea2b4e` against the core + `~/sites/mainstreetindependent/ora-project`:
- **Reaches the loop** (they call `boot.run_gear3`/`run_gear4` and flow through the
  terminal): (1) the entire core pipeline (`run_pipeline` @ `boot.py:9053` → `run_gear3`
  @ `9389` / `run_gear4` @ `9398`), (2) the server twin (`_run_pipeline_from_step2`,
  `_pipeline_stream`), and (3) **MSI's `invoke_real_gear4`** (`msi_run_gear4.py:1566`
  delegates steps 3–8 to `boot.run_gear4` — the one partial MSI path that inherits, and
  only when `MSI_RUN_GEAR4=on`, which is OFF by default). **"Inherits" is by construction,
  once the controller lands:** because Phase 6 anchors the loop at the shared terminal
  (`boot.py:9429`), any path that flows through that terminal — `invoke_real_gear4` included —
  gets the loop with no MSI-specific wiring; the custom Gear-3 path never flows through the
  terminal, so it inherits nothing. Today, with no controller, neither inherits anything — the
  claim is about the post-approval state, not the Phase-5 substrate.
- **Does NOT reach the loop** (build their own prompts via `prompt_fences.py`, a mirror
  of `boot._fenced`): `gear3_orchestrator.write_column`, `chain_invoke_default`,
  `backfill_orchestrator`'s custom Gear-3 voice paths, `article_generator` /
  `analysis_generator` when they route to `chain_invoke_default`. **MSI's own loop
  wiring is Phase 8** (per the standing MSI-adapter deferral); Phase 6 states this
  boundary, does not silently assume coverage.

### 1.8 Tests / the parity surface

Environmental baseline @ `ffea2b4e`: **22 FAIL + 5 ERROR = 27** (lens-integrity,
retry-fallback, openai-images, mode-relationship-priorities, user-settings,
visual-routing — all pre-existing, none related to this project). Phase 6's new tests
live in a new `test_execution_loop.py` (loop controller + selector + router + stop rule)
plus additions to `test_execution_packet.py` (filled §9 blocks) and
`test_evidence_runner.py` (Capture-driver integration + escalation-branch primitive).
Parity target: diff sorted FAIL/ERROR name lists pre-vs-post in the same worktree,
**ZERO new**.

---

## 2. The design

### P0 — Architecture call: a terminal-anchored loop CONTROLLER that engages on non-self-evidencing turns (Architecture A) — NOT a second pipeline (§3/§4)

**The call.** Wire the loop as a controller anchored at the pipeline terminal
(`boot.py:9429` / `server.py:2979`), gated to non-self-evidencing turns. Keep the gear
internals untouched (continuing Phase 4's deliberate "terminal packet, six in-gear sites
NOT edited" choice — and the lowest-regression path through MSI-inherited
`invoke_real_gear4`). The loop wraps the existing gear as its execute+revise **actuator**
and adds Capture → dual-family Verify → fork → stop/escalate around it.

**Why this maps to §3 cleanly (the timing reconciliation the judge should check).** The
§3 loop is `Plan → Execute → Capture → Verify → Revise → re-verify-or-escalate`. In
Architecture A:
- **Plan** = `apply_criteria` + `apply_evidence_contract` at the planning seam (live;
  dual-family at high-risk — P5).
- **Execute** = the gear run (produces ONE deliverable; single-writer — §3). Its
  *internal* Step-6/Step-8.6 prose verify is **not the §3 Verify** — it is the §5
  **judgment-lane** text review (prose quality), threaded onto the packet as
  `verification.text_review_verdict`.
- **Capture** = drive the Phase-5 runner AFTER the gear finishes, over whatever the turn
  actually mutated (P1). This sits *between* execute and the §3 Verify — "between" holds.
- **Verify** = the NEW dual-family execution-review verify over `render_for_review(packet)`
  (P2) — the §3 Verify, judging **evidence-lane sufficiency against the Contract**,
  structurally separate from the prose text-review (§5).
- **Revise / re-verify-or-escalate** = the revision router + stop rule (P3/P4), with the
  gear re-invoked as the actuator.

**The honesty crux (stated up front, not buried).** The gate is driven by the
**observed §6 signal, gear-INDEPENDENTLY** — *not* by a presumption about which gear
"writes prose." (Correction folded from a hand-check: every gear step routes through the
shared `_run_model_with_tools` loop — `run_gear3`/`run_gear4` dispatch via
`_call_with_supplement`→`_call_with_retry`→`_run_model_with_tools`, `boot.py:10830`/`10900`
— so an analyst/reviser on ANY gear can mutate a repo via Edit/bash/code_execute; and
`any_mutation` is folded purely from the tool-event log, `risk_gate.py:602`, with no gear
dependence. The earlier "gears 3-4 write prose, rarely mutate" framing was wrong and is
removed.) **The controller's gate mechanism is explicit and reads only already-folded
data**: at the terminal, `_ro = record_route_observed(...)` is already in scope
(`boot.py:9445`); the controller branches on
`sig = (_ro or {}).get("signals") or {}; engage = bool(sig.get("any_mutation") or
sig.get("source_read_suspected"))` — no new observation, no re-fold (condition 1 preserved).
So:
- On a **self-evidencing** turn (neither §6 signal fired — the common case, whatever the
  gear), the loop is **correctly dormant**: the gear's own text review WAS the review;
  Phase 6 builds the record packet exactly as Phase 4 does. **Byte-identical output,
  zero regression.**
- On a **mutation** turn (`any_mutation` fired, any gear): the **full converge/escalate loop
  engages** over the adapted `diff_validate` lane — Capture → verify → fork → stop/escalate.
- On a **source-read-ONLY** turn (`source_read_suspected` fired but NOT `any_mutation`): the
  loop does **NOT** enter the converge/escalate cycle (⚖ Rev-1, judge P1). Its only lane is
  `collect_provenance`, whose fill is the Phase-8 claim-to-source map — so it is legitimately
  **owed**, and `all_evidence_sufficient` would be `False` **forever**, which would escalate
  every source-read turn (churn). Instead Phase 6 records the packet with the owed
  `collect_provenance` lane + a **LOUD deferred-provenance marker** (`persistence`/`observed`
  note: "provenance evidence owed — claim-to-source map is Phase 8") and degrades to the gear's
  text review. It is honestly marked non-sufficient WITHOUT churning the loop. This resolves
  OQ6 (below): **the loop's convergence machinery is driven by adapted lanes only —
  `diff_validate` in Phase 6; `collect_provenance` is deferred, marked, never escalate-forcing.**
- The **diff+validate** evidence lane genuinely fires only when the turn actually mutated
  an **instrumented repo** (a discoverable `.ora/evidence.yaml` catalog + a contract) —
  i.e., agentic code-edit turns (via the `_run_model_with_tools` tool loop) and
  `invoke_real_gear4` runs against a catalogued repo. The `collect_provenance` lane
  (source-read grounding) is **declared but its result stays owed** (Phase 8 owns the
  claim-to-source map — §4); the loop treats an owed lane as NOT sufficient (`:97`), so it
  never reads absence as pass.

**Recommendation:** Architecture A. The alternative — **Architecture B (in-gear
Capture)**, inserting the runner between Step 5 and Step 6 inside `run_gear3`/`run_gear4`
and injecting an EXECUTION-REVIEW block into the prose verifier's user prompt (the scout's
S3/S5 suggestion) — reuses the gear's own revise loop directly (cheaper iteration) but
(a) reverses Phase 4's deliberate terminal choice, (b) edits the delicate,
MSI-inherited gear internals (regression risk into `invoke_real_gear4`), and (c) conflates
the prose verify (judgment lane) with the evidence verify (evidence lane), which §5 keeps
structurally separate. **The terminal-wrapper vs in-gear fork, and specifically how
heavyweight the revise actuator may be, is Open Question 1 — the headline decision for the
judge** (it mirrors Phase 4's "how live should P4 go?").

### P1 — The pre-execution state seam + the Capture step — drive the Phase-5 runner (§3, §7, §10)

**⚖ Rev 1 (judge P0): the loop is NOT purely terminal — it needs a PRE-EXECUTION state
seam.** The terminal runs AFTER the gear/actuator (`boot.py:9389` gear → `9429` terminal), so
a `snapshot_before` READ at the terminal (`_git_state` reads *current* HEAD/dirty state,
`evidence_runner.py:938`) captures POST-execution state — a false `state_before` and, worse,
a wrong base ref for the escalation branch (the abandoned attempt would already be folded into
that ref, so it could not be isolated as unmerged). **Fold:** capture the pre-execution git
state at the PLANNING seam, before the actuator runs, and stash it. This is cheap
(`git rev-parse HEAD` + `git status --porcelain`), additive, never-raises.

**⚖ Rev 2 (judge P2): the snapshot seam is TIER-INDEPENDENT — decoupled from the `standard+`
Contract seam.** The earlier draft tied it to `apply_evidence_contract` (which is `standard+`),
but spec §192/§8 says a `light` turn still gets **basic evidence = the repo catalog checks
only** (no bespoke planning). So the pre-execution snapshot must fire **whenever a repo is
discoverable, before ANY mutation-capable actuator runs — at every tier, `light` included**, and
NOT gated on `standard+` or on the Contract being produced. Concretely, at a repo-discoverable,
non-stealth pre-executor point (the risk-gate seam already runs there — `boot.py:~9284` /
`server.py:~2840`, before the gear at `9389`):

- `context_pkg["exec_review_state_before"] = snapshot_before(repo_root, mode)` — the TRUE
  pre-execution base (HEAD SHA + dirty snapshot), captured independent of tier. Post-hoc routing
  (§6) is preserved: we don't yet know the turn will mutate, so this snapshot is captured
  unconditionally-when-a-repo-exists and simply goes unused on a non-mutating turn.
- **At `light`** there is no bespoke Evidence Contract (planning is absent), so Capture runs the
  **repo catalog's own checks directly** (the independently-declared `.ora/evidence.yaml`
  checks — §8/§10, "the repo catalog checks only"), NOT a Contract-filtered subset; the snapshot
  still applies so `state_before` and any escalation base are exact. At `standard+` the
  Contract (a task-specific subset) drives which catalog checks run.

Then, at the terminal, when the turn is non-self-evidencing and non-stealth, run the Capture
sequence (all never-raise; a caught failure stamps `tool_events._note_failure`, observable),
using the STASHED pre-execution base rather than a fresh read:

1. `repo_root = discover repo root` (reuse `evidence_runner.discover_catalog`'s discovery:
   explicit → `ORA_PROJECT_ROOT` → bounded pathlib walk). No catalog / no repo →
   `evidence_contract.repo_less` is true → **no diff+validate checks to run**; the lane
   stays owed (not sufficient); Capture records the repo-less condition and the loop
   proceeds to verify on the evidence it has (which may be none → the packet degrades to
   the text review, loudly, via the renderer's "evidence not yet generated" line).
2. `before = context_pkg["exec_review_state_before"]` — the PLANNING-stage snapshot (true
   pre-execution base), NOT a terminal-time read. If it is somehow absent (no repo at
   planning, or the seam did not fire), the diff+validate lane is honestly marked
   base-unknown and stays owed (never a false `state_before`).
3. `results = run_contract(catalog, context_pkg["evidence_contract"], repo_root,
   worktree=, mode=)`.
4. `after, delta_ref = snapshot_after(repo_root, mode, trace_dir, before)` — the diff is
   computed from the stashed pre-execution `before.head`, so it is exactly the change this
   turn's execution produced on top of the true base.
5. `fill_evidence_lanes(packet, results, contract, delta_ref)`; set
   `execution.mode`/`state_before` (= the stashed pre-execution snapshot)/`state_after`.
6. `sufficient = contract_sufficient(results, contract)` — the stop-rule input.

**Mode selection (dirty-state, §11):** Phase 6 runs Capture in `review_dirty_diff`
(evaluate the executor's changes already in the tree, no clean requirement — the standard case
for an agentic edit turn) or `continue_user_changes` (the user owns the tree, don't revert) —
both **non-mutating capture over the live repo**. `clean_worktree`-isolated execution is the
Phase-8 adapter actuator (P8/OQ7).

**⚖ Rev 2 (judge P1): NO `mutates:true` check runs against the user's live checkout, and the
`clean_worktree` contradiction is removed.** The earlier draft said the selector "must pick
`clean_worktree`" for a mutating check while also deferring isolated execution to Phase 8 — a
contradiction, because passing `mode="clean_worktree"` at `boot.py`'s live-repo `repo_root`
would run a mutating check (a state-writing integration test) against the user's real tree
(only the mode gate at `:695` distinguishes it; the runner would still `cwd=repo_root`). **Phase
6 never does this.** A `mutates:true` required check is a **known Phase-8-deferred capability**
(it needs the isolated actuator that (i) creates a fresh worktree at the pre-execution base via
`git worktree add`, (ii) applies the executor's `delta_ref` patch, (iii) runs the check under
`mode="clean_worktree"` in THAT worktree, (iv) `git worktree remove`s it). Until Phase 8 builds
that, a `mutates:true` required check is **recorded as DEFERRED** (a loud owed marker + an
`evidence_check` tool-event with `skip_reason="mutating check deferred — isolated actuator is
Phase 8"`, so the deferral is OBSERVED, never a silent skip) and — per the owed/deferred-lane
principle (P4) — does **NOT escalate-churn**. Phase 6's live evidence is the **non-mutating**
catalog checks (build / lint / typecheck / read-only test — the common `mutates:false` case),
which is the honest live boundary; mutating integration tests wait for the Phase-8 isolated
actuator.

### P2 — Dual-family Verify + single-family graceful degrade (§12)

**The verify.** After Capture, render `render_for_review(packet)` and run the
execution-review verifier on it. This is the §3 Verify — evidence-first, producer-claim-last,
so a fluent claim cannot out-argue a failing check (the renderer physically enforces this).

**Different-family selection (leverage the existing substrate, §1.6).**
- Resolve the executor family = the `training_family` of the resolved analyst/`depth`
  endpoint.
- Select the verify endpoint by walking the `verification` slot's fallback chain and
  **skipping candidates whose `training_family` == the executor's** (a new
  `router.resolve_different_family(slot, exclude_family, config_name)` or a filter param on
  `resolve_post_analysis_slot`, `router.py:578`). Record
  `verification.reviewer_a = {endpoint, family}` and, when a second reviewer is warranted
  (high-risk/irreversible → dual), `reviewer_b`.
- **Do NOT silently fall back to `breadth_endpoint`** for the execution-review verify when
  no cross-family option exists (that fallback defeats the requirement, scout gotcha) —
  instead trigger the single-family path.

**Single-family graceful degrade (§12, verbatim).** When no different-family endpoint is
available: run the verify with an **explicitly adversarial prompt in a distinct role**
(weaker — blind spots stay partly correlated), record **lowered `confidence`**, set
`verification.reviewer_a.same_family = true` + a `fallback_reason`, and — for
**high-risk / irreversible** — **escalate to a human reviewer** rather than presenting
single-family review as cross-family assurance. The failure mode §12 names (same-family
review presented as cross-family) is closed by recording it on the packet AND surfacing it.

### P3 — Findings tagged plan/execution + invented tests tagged + the revision router (§12)

**Finding class (the fork).** The verify reviewer tags each finding
`class: plan_level | execution_level` as part of producing the review (no separate
classification pass — §12). Phase 6 fills `verification.findings[] = {description, severity,
class}`.
- **execution-level** finding → route back to the **executor**: re-invoke the gear (the
  actuator) with the findings threaded as additional review context. This reuses the gear's
  own machinery, not a new one.
- **plan-level** finding → route back to the **planners**: re-invoke `apply_criteria` +
  `apply_evidence_contract` (revised brief/contract), then re-execute. Without this fork,
  plan-level defects feed the executor alone and you "converge on a steadily better
  implementation of a wrong plan" (§12).

**Reviewer-invented tests tagged (§12).** `verification.invented_tests[] = {name,
kind: acceptance | regression | diagnostic | exploratory}`. Only `acceptance`-kind
invented tests obligate the executor (genuine missing acceptance criteria); `diagnostic` /
`exploratory` / reviewer-preference do not (so the executor is not trapped chasing every
invented objection). An `acceptance`-kind invented test authored by the verify stage is the
§12 "grading-your-own-homework" closure: the executor is never the sole author of its own
passing condition (acceptance criteria set at planning + verify may author adversarial
acceptance tests).

### P4 — The stop rule + escalation to an inspectable unmerged branch (§13)

**Stop rule.** Stop and converge when `all_evidence_sufficient(lanes)` AND **no high-severity
finding of ANY class remains** (⚖ Rev-1, judge P1: spec §364 says "no high-severity finding
remains" — an earlier draft wrongly narrowed this to `execution_level` only, which would let a
high-severity **plan-level** wrong-problem finding coexist with `criteria_met`; that is exactly
the "converged on a better implementation of a wrong plan" failure §12 warns against) →
`loop.stop_condition = "criteria_met"`, `status = "converged"`. A high-severity **plan-level**
finding routes to the planners (P3) and MUST be resolved (or cap-escalated) before convergence —
it is never waived by evidence sufficiency alone. Otherwise, at a fixed iteration cap
(`MAX_LOOP_ITERATIONS`, provisional — see below) → **escalate**:
`loop.stop_condition = "max_iterations_escalated"`, `status = "escalated"`. **The loop
has no guaranteed fixed point** (two verifiers can persistently disagree; the plan/exec
fork can ping-pong — §13) → **build it to converge OR hand back the packet and stop, never
churn.** `loop.iteration` counts the passes.

**Escalate only on a RAN-and-FAILED check or a persistent finding — never on a deferred /
owed / empty lane (⚖ Rev-1 + Rev-2, unifies judge P1 source-read, OQ6 repo-less, and the
Rev-2 mutating-check deferral).** Insufficiency has distinct causes that must NOT be conflated:
- **A check RAN and FAILED** (evidence exists and is negative) → real insufficiency → revise;
  at cap → escalate. This is the loop's actual work.
- **A high-severity finding of any class persists** across iterations → revise/route; at cap →
  escalate.
- **A check was REFUSED / a lane is OWED for an environment or scope reason** — the network
  policy can't be enforced on this host (no sandbox backend), a `mutates:true` check is deferred
  to the Phase-8 isolated actuator (Rev-2), `collect_provenance` awaits the Phase-8 map, or a
  `repo_less` contract declared no checks (OQ6) — → **record the packet with a LOUD
  owed/deferred marker + an observed `evidence_check` event, and degrade to the text review; do
  NOT escalate.** These are honest "can't verify this here," not test failures — escalating them
  would churn every source-read / no-catalog / no-sandbox / mutating-check turn, and a human
  can't act on an environment limitation mid-loop anyway. **The escalate condition reads only
  lanes whose declared checks actually RAN and returned a verdict.**

**The abandoned attempt lands on an inspectable, UNMERGED branch (§13).** On escalation,
create a git branch from the **stashed pre-execution base**
(`context_pkg["exec_review_state_before"].head`, per P1's ⚖ Rev-1 fold — NOT a terminal-time
HEAD read) via the `evidence_runner._git` primitive, record the abandoned attempt on it, and
record `loop.escalation = {reason, abandoned_attempt_branch: "<branch-name-or-ref>"}`. **Never
silently discarded; never left as a dangling untracked worktree.** This matches Ora's
git-for-everything discipline (no `.bak`). The runner's own `finally` `shutil.rmtree`
(`:785`) destroys only the sandbox *scratch* home/tmp — it is NOT the escalation branch;
Phase 6 creates and KEEPS the branch explicitly (it is not a runner byproduct — §1.4 gotcha).

**The unmerged guarantee splits by whether the executor COMMITTED (⚖ Rev-1, judge P0).** Two
honest cases:
- **In-tree, uncommitted attempt** (`review_dirty_diff` / `continue_user_changes` — the live
  default): the abandoned attempt is the uncommitted working-tree delta. It is captured as
  `snapshot_after`'s `evidence-diff.patch` (`:968`) AND committed onto
  `execution-review/escalation-<task_id>` created from the stashed pre-execution `before.head`,
  **without touching the user's working branch / HEAD** (`git branch <name> <base>` + a tree
  snapshot commit onto it via a temp index — the user's checkout is left exactly as the executor
  left it). The branch is unmerged by construction (it diverges from the base the user is on).
- **Committing executor** (the actuator committed to a branch during execution — the
  `clean_worktree` / adapter case): the only way to leave the abandoned commits **unmerged**
  without rewriting the user's branch is to have run execution in an **isolated worktree/branch
  from the start**. So the escalation guarantee *requires* isolation whenever execution commits
  — which is exactly the `clean_worktree` mode the Contract-aware selector already forces for
  `mutates:true` Contracts (P1). Phase 6 does NOT reset or rewrite the user's working branch to
  manufacture an unmerged branch after a committing in-place run — that would mutate the user's
  repo state silently. Instead, a committing in-place run without isolation is flagged as a
  configuration that cannot satisfy the §13 unmerged guarantee, and the loop records that
  honestly rather than faking it (OQ4).

**The escalation branch commits only what the executor already wrote to the tree.** It adds
no new secret exposure beyond what is already on disk, and secret/sensitive *files* are
already kept out of the repo upstream by the Phase-1 gate + the repo's `.gitignore`; the
branch respects those. For a `clean_worktree`-isolated attempt the branch lives in the
isolated worktree, not the user's main checkout (OQ4d).

**Escalation handback is a REFERENCE, never the inlined sensitive content (folded).** The
Paused human-queue is a DURABLE JSONL (`data/oversight/human-queue.jsonl`), more durable than
the trace-local packet — and `producer_claim` may be `private`/`sensitive`. So the handback
carries a **reference**: the trace-local packet path, the `abandoned_attempt_branch` ref, the
escalation `reason`, and a **redacted** `render_for_review` summary — NOT the inlined
`producer_claim`. This fits the existing `oversight_queue.PausedEntry.context_summary` shape
(`oversight_queue.py:75` — a summary dict, not a full-packet field) and inherits
`_append_human_queue`'s existing stealth-skip. Full sensitivity-driven redaction of durable
records is **Phase 7's** job; Phase 6's obligation is narrower and enforced now: do NOT inline
`secret`/`sensitive` content into the more-durable queue (§7 sensitivity axis is the driver).

**Provisional constants (flagged per house rule — retunable, not calibrated):**
`MAX_LOOP_ITERATIONS` (start at 2, matching the gear's own `MAX_VERIFY_CYCLES` intuition);
the high-severity threshold for "no high-severity finding remains"; the single-family
`confidence` penalty. All flagged in code + packet, empirically calibratable later.

### P5 — Dual planning at high-risk/irreversible + criteria-source scaling (§8) + threading criteria into the packet

- **Criteria-source scaling (§8, a scaling rule not an exception).** `light` — no planning
  stage; the instruction is the criterion; the executor authors nothing beyond running
  declared catalog checks. `standard` — single planning pass (already live). `high-risk` /
  `irreversible` — **dual planning (two families)** sets the contract adversarially. Phase 6
  adds the dual variant: run `apply_criteria`/`apply_evidence_contract` twice with two
  different-family invokers and converge, recording `planning.planner_a`/`planner_b`. The
  invariant across all tiers above `light` (§16-1): setting the criteria is a separate act,
  prior to execution — **duality is the high-tier strengthening, not the invariant itself.**
- **Thread criteria into the packet.** Populate `planning.converged_brief.acceptance_criteria`
  from `context_pkg["acceptance_criteria"]` and `planning.evidence_contract` from
  `context_pkg["evidence_contract"]`, so `render_for_review` shows the criteria (or fires its
  LOUD absence fence when planning genuinely set none — e.g. a `light` turn). At `light`,
  `planning` stays `None` (correct, not incomplete — §9 tier-optional).

### P6 — Filling the §9 loop / verification / execution blocks — fill, not retrofit (§9)

Phase 6 populates exactly the reserved fields (§1.5) via a new
`execution_packet.populate_loop_fields(packet, ...)` builder called from the loop
controller (keeping `build_execution_packet` byte-compatible for the self-evidencing path):
`planning`, `verification.reviewer_a/reviewer_b/findings/invented_tests/confidence`,
`execution.mode/state_before/state_after/enforcement_model`, `loop.*`, and the runner-filled
`evidence_lanes[].*`. **`enforcement_model` honesty (the P4 TODO):** set from the actual
Capture backend — `in_harness` for a core in-harness gear run with no orchestrated capture;
`orchestrated`/`declared-sandbox` when the runner ran checks under kernel isolation / a
declared wrapper; never a blanket `in_harness` inherited onto an orchestrated or MSI-custom
path. The `reversible` flag is NOT recomputed post-hoc (it is the §6 tier-boundary gate;
high-risk == `reversible: true` is spec-correct — GOTCHA carried from P4/P5, do not "fix").

### P7 — The evaluation-lane verify: evidence lanes judged, judgment lanes get no verdict (§5)

The verify stage judges **each evidence lane's sufficiency against the Contract** (the
`diff_validate` lane via `contract_sufficient`); the `collect_provenance` lane stays owed
(Phase 8). **Judgment lanes get NO mechanical verdict** — `JudgmentLane` has no
`verdict`/`sufficient` field by construction (`execution_packet.py:81`), so a matter of
taste can never be dressed up as a passing check. The gear's prose text-review verdict lands
in `verification.text_review_verdict` (the judgment-lane review), structurally separate from
the evidence-lane execution-review verify. This is the §5 separation held live.

**The gear-3 `failed-then-redone-unreviewed` status is honored, not acted on by the evidence
verify (folded).** When gear-3's quality gate FAILs and fires a redo, it overwrites the
text-review with `{verdict: None, status: "failed-then-redone-unreviewed"}` (`boot.py:11612`),
which the renderer surfaces as a LOUD "no verdict covers the shipped text" fence
(`execution_packet.py:272`). Because the execution-review verify judges the EVIDENCE lanes
(not the prose), it proceeds independently of that status — but the status rides the packet
into the review + any escalation handback, so a human never mistakes an unreviewed-text redo
for a text-reviewed deliverable. (The status is a judgment-lane fact; it does not by itself
trigger an evidence-lane re-verify.)

### P8 — §16 invariants held live + the custom-path reach (§15 Phase-0)

- **§16-1** (criteria separate + prior): live via `apply_criteria` at planning; dual at
  high-risk; threaded into the packet so the review sees it (or the LOUD absence).
- **§16-2** (recipe declared independently): the write-protected `.ora/evidence.yaml` +
  the planning-stage contract; the runner runs declared checks mechanically;
  `contract_sufficient` = "nothing broke that you knew to check", never "solved the right
  problem" (that is criteria + adversarial verify).
- **§16-3** (observed not narrated): `route_observed` folds the tool-event log (Phase 3);
  the runner records an `evidence_check` event per outcome (Phase 5); lanes carry
  `generated_by` = declared commands actually run, never executor self-report.
- **Custom-path reach (§15 Phase-0):** the loop reaches the core pipeline + MSI's
  `invoke_real_gear4` only; MSI's `gear3_orchestrator` and single-pass paths do NOT
  inherit and are **explicitly deferred to Phase 8**. Stated, not silently assumed.

---

## 3. Design consequences the judge should weigh explicitly

1. **The honest live/dormant/scaffolding split.** LIVE on approval: the loop controller
   (planning-stage pre-execution state seam + terminal-anchored gate, ⚖ Rev-1);
   `render_for_review` as the live review surface; the dual-family selector + single-family
   degrade; the plan/exec fork + revision router; the stop rule + escalation branch + human
   handback; the §9 loop/verification/execution blocks populated; the runner DRIVEN in Capture.
   The full converge/escalate loop FIRES ONLY on a **mutation** turn (diff+validate) — the
   common analytical prose turn stays the existing gear + record packet.
   RECORDED-AND-DEFERRED (⚖ Rev-1): a **source-read-only** turn gets the packet + a loud
   owed-provenance marker and does NOT escalate (its `collect_provenance` fill is Phase 8).
   SCAFFOLDING/DEFERRED: `clean_worktree`-isolated single-writer code execution as a first-class
   Ora mode (Phase-8 adapter actuator — but the escalation guarantee already REQUIRES it for a
   committing executor, ⚖ Rev-1 P4); `collect_provenance` lane fill (Phase-8 claim-to-source
   map); durable tiered persistence (Phase 7 — the packet stays `trace_local`;
   `status="escalated"` is recorded but not promoted to `durable_note`); MSI's own loop wiring
   (Phase 8).
2. **The revise actuator is heavyweight in Architecture A.** Re-invoking the whole gear on
   each execution-level revision re-runs a full analytical pass. This is why
   `MAX_LOOP_ITERATIONS` is conservative and why OQ1 (terminal-wrapper vs in-gear
   piggyback) is the headline decision.
3. **Escalation reuses the Paused human-queue** rather than inventing an escalation surface
   — consistent with the meta-layer oversight subsystem, but the judge should confirm the
   packet + branch-ref payload shape on that queue.
4. **Stealth turns produce no packet, no loop, no evidence events** (inherited) — the loop
   respects stealth wholesale (`_append_human_queue` already stealth-skips the durable queue).
5. **Packet writes across loop iterations are last-writer-wins, which is intended.** `trace_dir`
   is per-turn (`boot.py:7810` — `data/pipeline-traces/<conversation_id>/<turn>/`), so there is
   no cross-turn race; within a turn the loop rewrites the same trace-local packet each
   iteration and the FINAL iteration's state is the durable record (converged or escalated).
   No file-lock is needed for the single-turn, single-writer loop; if a future concurrency model
   runs iterations in parallel this becomes a real race (flagged, not a Phase-6 concern).

---

## 4. Scope boundary — what Phase 6 deliberately does NOT do

- Does NOT build a second gear pipeline (§4) — it wires a controller from existing parts.
- Does NOT build other adapters (notes/vault, publish, data pipelines) — Phase 8.
- Does NOT build the claim-to-source map / `collect_provenance` fill — Phase 8.
- Does NOT do MSI's loop wiring beyond the `invoke_real_gear4` inheritance it already gets —
  Phase 8.
- Does NOT implement tiered durable persistence or sensitivity-driven redaction of the
  packet — Phase 7 (packet stays `trace_local`).
- Does NOT make `clean_worktree`-isolated single-writer code execution a first-class Ora
  execution mode, and does NOT run any `mutates:true` check against the user's live checkout
  (⚖ Rev-2). It runs only **non-mutating** catalog checks over the live repo
  (`review_dirty_diff`/`continue_user_changes`) — at any tier where a repo is discoverable
  (`light` included, via the repo catalog directly) — and defers mutating checks + the isolated
  actuator (worktree + apply-delta + escalation branch) to Phase 8.
- Does NOT "fix" `reversible: true` at high-risk (spec-correct §6 tier-boundary gate).

---

## 5. Test + parity plan

- **New `orchestrator/tests/test_execution_loop.py`:** the loop controller (self-evidencing
  short-circuit = byte-identical; non-self-evidencing engage); the different-family selector
  (skips same-family, picks cross-family, detects single-family); the single-family degrade
  (lowered confidence + high-risk escalation); the plan/exec revision router; the stop rule
  (converge on sufficient+no-high-severity; escalate at cap); the escalation branch primitive
  (branch created from `snapshot_before` SHA, kept unmerged, ref on the packet); mocked gear
  actuator + mocked runner so no live model / no real subprocess.
- **Additions to `test_execution_packet.py`:** `populate_loop_fields` fills each reserved §9
  block; `render_for_review` shows populated criteria + findings; owed lane ≠ sufficient.
- **Additions to `test_evidence_runner.py`:** Capture-driver integration (snapshot→run→fill→
  sufficiency); escalation-branch creation via `_git`.
- **Parity:** pre-edit baseline in the SAME worktree; diff sorted FAIL/ERROR name lists
  pre-vs-post; **target ZERO new** vs the 27 environmental (22F/5E). Full suite run with
  `ORA_PIPELINE_TRACE=off ORA_TOOL_EVENTS=off`.
- **Adversarial pre-check** over ONLY the changed logic each revision (2–3 lenses × verify),
  re-verifying security/git-mutation findings by hand (the majority vote under-reports).

---

## 6. Portability (required by the amendment — cross-platform surfaces, tests, remaining assumptions)

- **Surfaces touched:** the escalation-branch git primitive (`_git` is already
  `subprocess`-based, no shell, cross-platform); the different-family selector (pure config
  read, platform-neutral); the Capture driver (delegates to the Phase-5 runner, which is
  already enforce-or-refuse + platform-gated — macOS `sandbox-exec` / Linux `unshare` /
  Windows `ORA_EVIDENCE_SANDBOX`; a platform with no enforcing backend refuses cleanly →
  the diff+validate lane stays owed, the loop still runs its non-mutating verify + stop
  rule). No new path roots (all via `runtime_paths` / the runner's existing discovery).
- **Tests:** Windows-sim the branch-name construction + the family selector (pure logic,
  runnable on mac/Linux CI); the runner's platform behavior is already covered by Phase 5.
- **Remaining assumption:** on a host with NO enforcing sandbox backend (or for any
  `mutates:true` check, which Phase 6 defers regardless of host — ⚖ Rev-2), the check is
  REFUSED/DEFERRED for an environment/scope reason → the lane is recorded as owed with a LOUD
  marker + an observed `evidence_check` event → the loop **degrades to the text review, it does
  NOT escalate** (an environment limitation is not a test failure, and a human can't fix it
  mid-loop). Honest degradation, not a silent pass; surfaced in the packet.

---

## 7. Open questions for the judge

**OQ1 (headline — the architecture fork).** Terminal-anchored loop wrapper (Architecture A,
recommended: lowest regression, continues Phase 4's terminal choice, keeps the prose-verify
and evidence-verify structurally separate) vs in-gear Capture (Architecture B: inserts the
runner between Step 5 and Step 6 and reuses the gear's own revise loop — cheaper iteration
but edits MSI-inherited gear internals and conflates the two §5 lanes)? And, within A: may
the revise actuator re-run the whole gear, or should iteration be capped at 1 execution-level
+ 1 plan-level revision for the first landing to bound cost?

**OQ2.** Verify-verdict logic when the loop's execution-review verify and the gear's own
prose text-review disagree: are they simply the two §5 lanes (independent, both recorded —
recommended), or should the execution-review verify be able to *block* a gear that its own
prose verify passed? (Recommended: independent lanes; the execution-review verify governs
convergence/escalation, the prose verify governs text quality.)

**OQ3.** Single-family graceful degrade UX when no cross-family verify model exists: (A)
same-family adversarial-prompt verify + lowered confidence + escalate on high-risk
(recommended, §12 verbatim); (B) skip the execution-review verify entirely and record
"verification skipped — no cross-family model"; (C) downgrade the gear. Which is canonical?

**OQ4.** The escalation branch (base ref now RESOLVED by ⚖ Rev-1 — from the stashed
pre-execution `exec_review_state_before.head`, and a *committing* executor requires
`clean_worktree` isolation for the unmerged guarantee, P4): remaining — (a) created only on the
escalation decision (recommended) vs eagerly per failed iteration; (b) `git branch` + a
tree-snapshot commit onto it without touching the user's HEAD (recommended for the in-tree case)
vs a full `git worktree add`; (c) fate on later human resolution (leave unmerged for inspection
— recommended — vs auto-archive/tag). Confirm the Rev-1 stance that Phase 6 never resets/rewrites
the user's working branch to manufacture an unmerged branch after a committing in-place run.

**OQ5.** Dual planning at high-risk/irreversible: two `apply_criteria`/`apply_evidence_contract`
passes with two different-family invokers converged into one brief (recommended) vs a
structural two-context-pkg pattern? And what "converge" operator (synthesis vs
select-the-stricter)?

**OQ6 (RESOLVED by ⚖ Rev-1, judge P1).** Repo-less / no-catalog turns AND source-read-only
turns share one resolution: an **owed/empty lane never escalates** — the loop escalates only on
FAILED/REFUSED *declared* evidence or a persistent high-severity finding (P4 escalate-precision).
A `repo_less` contract (no declared checks) or an owed `collect_provenance` lane → record the
packet with a LOUD owed/deferred marker + degrade to the text review; no churn. Confirming this
resolution is the only open part.

**OQ7 (RESOLVED by ⚖ Rev-2, judge P1).** Dirty-state mode: Phase 6 wires non-mutating
`review_dirty_diff` / `continue_user_changes` capture over the live repo and NEVER passes
`mode="clean_worktree"` against the live checkout; a `mutates:true` check is deferred to the
Phase-8 isolated actuator (recorded, not escalate-forcing). No open part remains.

**OQ8.** Where the Capture result + the loop verdict are recorded for downstream: on
`context_pkg` (for the terminal packet builder) + trace-local JSON (recommended), and whether
a new `evidence_check` / loop-iteration event should also land on the tool-event bus for the
oversight health surface.

**OQ9.** Provisional constants (`MAX_LOOP_ITERATIONS`, the high-severity threshold, the
single-family confidence penalty) — accept as flagged-provisional-retunable (house rule) or
does the judge want specific starting values pinned in the design?

**OQ10.** Escalation payload on the Paused human-queue: confirm the shape (packet ref +
`abandoned_attempt_branch` + reason + the render_for_review text) and whether the existing
`oversight_queue` naming/engagement machinery is the right surface vs a dedicated
execution-review escalation lane.

---

## ⚖ Revision 2 — judge APPROVE-WITH-CONDITIONS (2026-07-04), both conditions folded

The judge **approved Architecture A for implementation** with two clarifications to fold before
coding. Both folded (no code written):

- **[P1] The `clean_worktree` contradiction is removed.** The draft said the selector "must" pick
  `clean_worktree` for a `mutates:true` check while also deferring isolated execution to Phase 8 —
  contradictory, because `mode="clean_worktree"` at the live `repo_root` would run a state-writing
  check against the user's real tree. **FOLDED (P1 + P4 + §4):** Phase 6 **never** passes
  `mode="clean_worktree"` against the live checkout; a `mutates:true` required check is a known
  **Phase-8-deferred capability** (needs the isolated actuator: `git worktree add` at base → apply
  `delta_ref` → run → `git worktree remove`), recorded as DEFERRED (loud marker + observed
  `evidence_check` event) and — per the owed/deferred-lane rule — **not escalate-forcing**. Phase
  6's live evidence is the **non-mutating** catalog checks (build/lint/typecheck/read-only test).
  The P4 escalate-precision now separates a RAN-and-FAILED check (escalate) from an
  environment/scope REFUSAL/deferral (record + degrade).
- **[P2] The pre-execution snapshot is TIER-INDEPENDENT.** Spec §192/§8: a `light` turn still gets
  basic evidence = the repo catalog checks. The draft tied the snapshot to the `standard+`
  `apply_evidence_contract` seam. **FOLDED (P1):** capture the snapshot whenever a repo is
  discoverable, before ANY mutation-capable actuator, at EVERY tier (`light` included) — decoupled
  from `standard+`; at `light` Capture runs the repo catalog's checks directly (no bespoke
  Contract), and the snapshot still gives an exact `state_before` + escalation base.

With both folded, Architecture A is judge-approved for implementation. NEXT: implement in a FRESH
worktree off CURRENT origin/main (re-fetch), adversarial pre-check over the changed logic, parity
(diff sorted FAIL/ERROR name lists, ZERO new vs the 22F/5E = 27 environmental baseline), land per
the git workflow (branch → PR → squash-merge → delete branch + prune worktree → ff ~/ora main).

## ⚖ Revision 1 — judge design-gate findings (2026-07-04), all folded

The judge blocked Rev 0 with 3 findings; all confirmed real against the code and folded. The
core structural consequence: **Architecture A is no longer purely terminal — it gains a
planning-stage pre-execution state seam**, without which the escalation guarantee cannot hold.

- **[P0] No true `state_before`; escalation branch built from the wrong ref.** A `snapshot_before`
  READ at the terminal is POST-execution (`_git_state` reads current HEAD, `evidence_runner.py:938`;
  gear runs at `boot.py:9389` before the terminal at `9429`). **FOLDED (P1 + P4):** capture the
  pre-execution git state at the PLANNING seam (right after `apply_evidence_contract`), stash it on
  `context_pkg["exec_review_state_before"]`, and derive both `execution.state_before` and the
  escalation-branch base from that stashed ref — never a terminal-time read. Added the
  committing-vs-uncommitted split: an in-tree uncommitted attempt is branched from the stashed base
  without touching the user's HEAD; a *committing* executor requires `clean_worktree` isolation for
  the unmerged guarantee (Phase 6 never resets the user's branch to fake one).
- **[P1] Stop rule could converge with a high-severity PLAN-level finding present.** Spec §364 says
  "no high-severity finding remains"; the draft wrongly narrowed to `execution_level`. **FOLDED
  (P4):** convergence requires **no high-severity finding of ANY class**; a high-severity plan-level
  finding routes to planners and must resolve or cap-escalate — never waived by evidence sufficiency.
- **[P1] Source-read path caused escalation churn.** `source_read_suspected` engages the loop, routes
  a `collect_provenance` lane (`execution_packet.py:186`) whose fill is Phase 8, so the owed lane is
  never sufficient (`:97`) → escalate every source-read turn. OQ6 was undecided. **FOLDED (P0 + P4 +
  OQ6):** the loop escalates only on FAILED/REFUSED *declared* evidence or a persistent high-severity
  finding; an **owed/empty lane** (`collect_provenance` Phase-8, or a `repo_less` contract) records a
  LOUD deferred marker and degrades to the text review, never escalating. Phase 6's convergence
  machinery is driven by adapted lanes only — `diff_validate` now, `collect_provenance` deferred.

No new code written; the design packet is revised and re-delivered for the design gate.

## ⚖ Completeness-critic folds (adversarial pass — 5 diverse lenses × per-finding adversarial verify; 42 raw findings)

Ran a 5-lens completeness-critic over this packet (code-claim auditor, spec-fidelity,
architecture-hole, omission, security/git-mutation), each verifying claims against the
scout worktree. The per-finding adversarial verify stage was **largely killed by
server-side rate-limiting** (the exact hazard the handoff flags), so — per the proven
discipline — **I re-verified every finding against the code by hand** rather than trusting
the automated vote.

**Of the 42 raw findings, ~28 were the SAME meta-observation** — "the loop controller /
Capture wiring / different-family selector / revision router / stop rule /
`populate_loop_fields` / `test_execution_loop.py` does not exist in the Phase-5 scout
worktree." **Correctly REJECTED as design defects**: this is a DESIGN-gate packet against the
Phase-5 landing; "not yet built" is not a flaw — it enumerates exactly the Phase-6 build
surface, which the design already names with a mechanism for each. (Hand-verified: each such
finding maps to a design section that states it is Phase-6 scope — P0/P1/P2/P3/P4/P6 + §5.
The critics' enumeration actually *confirms* the design's scope map.)

**8 genuine design-level findings FOLDED (each hand-verified against the code):**

1. **[correction, hand-found + confirmed] The "gears 3-4 write prose, rarely mutate" framing
   was WRONG.** All gear steps route through `_run_model_with_tools`
   (`_call_with_supplement`→`_call_with_retry`→tool loop, `boot.py:10830`/`10900`); `any_mutation`
   folds gear-independently from the tool-event log (`risk_gate.py:602`). Rewrote P0: the gate
   keys on the OBSERVED §6 signal, gear-independent, and the controller's gate mechanism is now
   stated explicitly (reads the already-folded `_ro['signals']`, no re-fold).
2. **[MAJOR, security] Escalation handback could leak `producer_claim` into the durable queue.**
   The Paused queue is durable JSONL; `producer_claim` may be `sensitive`. Folded into P4: the
   handback is a REFERENCE (packet trace path + branch ref + reason + a redacted
   `render_for_review` summary), NOT the inlined content — consistent with the existing
   `PausedEntry.context_summary` shape (`oversight_queue.py:75`, verified) and its stealth-skip.
3. **[MAJOR→refinement, security] Mode selection must be Contract-AWARE.** A `mutates:true`
   required check refuses under `review_dirty_diff` and `contract_sufficient` counts it not
   sufficient → the loop can't converge. Folded into P1: the mode selector picks `clean_worktree`
   when any required check mutates, else honestly escalates on insufficient evidence (the refusal
   is an observed `evidence_check` event, not a silent skip).
4. **[MAJOR, security] Escalation branch + secrets in git.** Folded into P4: the branch commits
   only what the executor already wrote to the tree (no new exposure; secret *files* are gated
   out upstream by Phase 1 + `.gitignore`), and an isolated `clean_worktree` attempt branches in
   the isolated worktree, not the user's main.
5. **[MINOR] The self-evidencing gate did not name its signal/mechanism.** Folded into P0: the
   controller branches on `sig.get("any_mutation") or sig.get("source_read_suspected")` from the
   in-scope `_ro`.
6. **[MINOR, omission] The gear-3 `failed-then-redone-unreviewed` status.** Folded into P7: the
   status rides the packet (judgment-lane fact, surfaced by the renderer + on escalation); the
   evidence verify proceeds independently of it.
7. **[MINOR, omission] Concurrency / last-writer-wins on the trace-local packet.** Folded into §3
   consequence 5: `trace_dir` is per-turn (no cross-turn race); the loop's final iteration is the
   intended durable state; no lock needed for the single-turn single-writer loop.
8. **[MINOR] MSI `invoke_real_gear4` inheritance framing.** Folded into §1.7: "inherits" is
   by-construction once the terminal controller lands (it flows through the shared terminal); the
   custom Gear-3 path never flows through the terminal and stays Phase 8.

**Correctly REJECTED (hand-verified, not folded):** the ~28 "does-not-exist-yet" findings
(design-gate scope, not defects); OQ9's "MAX_LOOP_ITERATIONS not pinned" (a starting value IS
pinned — `2` — flagged provisional per the house rule, and the pin-vs-defer is legitimately OQ9);
"repo-less path untested" (it is OQ6 with a recommended answer + a named test in §5 — a design
packet does not carry tests). None of the rejected findings survived a hand re-check as a design
defect.
