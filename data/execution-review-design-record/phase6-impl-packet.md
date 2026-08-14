# Execution Review — Phase 6 Implementation Packet (Wire the loop + governance + stop rule)

*Spec §15 Phase 6. Implements the judge-approved design packet
`/Users/oracle/ora-worktrees/phase6-design.md` (Architecture A, both Rev-2 conditions folded).
Delivered to the CODE-REVIEW gate. NO commit until the judge approves the code.*

- **Worktree:** `/Users/oracle/ora-worktrees/phase6-impl` — branch `execution-review-phase6-impl`
  off **current** `origin/main = c9501e2d` (re-fetched; only a docs-only PR #186 landed past the
  design's scout point `ffea2b4e`, so **zero orchestrator/server code moved** and every design
  file:line anchor held exactly — re-verified by hand).
- **Durable diff:** `/Users/oracle/ora-worktrees/phase6-impl.diff` (9 files, +2251/−25).
- **Parity:** full suite **3869 tests, 22 FAIL + 5 ERROR = 27, IDENTICAL to the baseline (zero new,
  zero disappeared)** — re-run AFTER the judge code-review folds (Revisions 1 + 2 below). Baseline
  (27) captured in the same worktree pre-edit; run with `ORA_PIPELINE_TRACE=off ORA_TOOL_EVENTS=off`.
- **Status:** Revision 2 — the judge's follow-on §13 finding (Rev 1 introduced a base-unknown
  null-branch escalation) is folded, reproduced-then-fixed. Two further adversarial re-checks of the
  escalation restructure found + I folded a major (§12 policy escalations were being silently
  degraded) and a minor (same-family FAIL reason overstated assurance) issue; the block then
  converged. Revisions 1 + 2 blocks below; **all judge findings to date + all self-found follow-ons
  are addressed**; 186 focused Phase-6 tests pass.

---

## Revision 2 — judge follow-on §13 finding (Rev 1's base-unknown fold was incomplete)

The judge caught that Rev 1's base-unknown fold only forced the diff lane owed when the run was
*sufficient* — so a base-unknown turn with a **failed** check kept `ran_and_failed() == True`,
triggered escalation, but `create_escalation_branch` cannot make a branch without a `base_sha`, and
`run_loop` then queued a handback with `abandoned_attempt_branch: None` — violating both "base-unknown
stays owed" and §13's "escalations link an inspectable abandoned-attempt branch." Reproduced. **Fold
(two parts):**

- **base-unknown check outcomes are OWED, not attributable failures.** `CaptureResult.ran_and_failed()`
  now returns `False` when `base_unknown` — without a pre-execution base a check outcome cannot be
  attributed to this turn (the tree may have carried a pre-existing failure), so it does not drive
  escalation. This directly fixes the judge's probe: base-unknown + failed check now degrades.
- **never a branchless §13 escalation.** `run_loop`'s escalation block now downgrades to a LOUD
  degrade (`stop_condition=None`, `escalation=None`, an "escalation WITHHELD" note) and queues NO
  handback whenever the abandoned-attempt branch cannot be created — base-unknown, no repo, or a git
  failure. A `branch_creator` injection param was added for testability; the live wiring uses the
  real `create_escalation_branch`.

**Rev 2 follow-on (found by my own adversarial re-check of the Rev-2 restructure, folded before
re-delivery):** the first cut of "downgrade when no branch" was too broad — it swept in the §12
`escalate_human` case (single-family / unverified verify on **high-risk/irreversible** work), whose
whole purpose is to reach a human *independent* of any abandoned-attempt branch, so a high-risk turn
genuinely needing human review was silently degraded. **Fold:** split escalations into
**evidence/abandoned-attempt** (ran-and-failed / high-severity / VERDICT:FAIL → §13 requires an
inspectable branch → degrade if none) vs **policy/human-review** (`escalate_human`, §12 → reaches the
human queue even without a branch; `escalation.kind="policy_human_review"`, honest `no_branch_reason`).
(`test_policy_escalation_reaches_human_without_branch` +
`test_evidence_escalation_without_creatable_branch_downgrades_to_degrade`.)

**Rev 2 second follow-on (found by a third adversarial re-check, folded before re-delivery — minor):**
in the co-occurring single-family + high-risk + base-unknown + FAIL case, the durable handback reason
hardcoded "the different-family verifier returned VERDICT: FAIL" even though the verify was
*same-family* — overstating the assurance to the human adjudicator. **Fold:** the reason now
attributes a FAIL to the verifier that actually ran ("the single-family verifier returned VERDICT:
FAIL (lowered assurance)" when same-family). Control flow unchanged; human-facing honesty only.
(`test_same_family_fail_reason_does_not_claim_different_family`.)

**Verification of Rev 2:** the judge's exact base-unknown-failed-check probe degrades with zero
handbacks and no null branch; the §12 human-review escalation reaches the human even when no branch
can be built; focused Phase-6 suites **186 tests pass**; full parity re-run below; **three** focused
adversarial re-checks of the escalation restructure were run — each of the last two found one real
issue (the policy/evidence split, then the same-family reason text), both hand-verified and folded,
so the block converged.

*Note:* the branch is behind `origin/main` by one docs-only commit (the judge flagged this) — the
landing steps already re-fetch + rebase onto current main before the PR.

---

## Revision 1 — judge CODE-REVIEW gate findings (all 3 folded, hand-verified + reproduced)

The judge blocked Rev 0 with three P1 loop-correctness findings. I confirmed each against the code
(reproduced the judge's exact scenarios), fixed all three, added targeted tests, and ran a focused
3-lens adversarial re-check over ONLY the changed stop-rule/capture/verify logic (**0 findings —
the folds don't over-block a legitimate convergence and leave no remaining false-converge path**).

1. **[P1] Verifier saw "NO ACCEPTANCE CRITERIA" even when criteria existed.** `run_loop` computed
   the `planning` block but attached it to the packet only in the FINAL `populate_loop_fields`,
   *after* the verifier had already rendered the packet inside the loop — so `render_for_review`
   read `packet.planning = None` and fired the LOUD absence fence, and every verify judged against a
   false absence. **Fold:** attach `packet.planning` immediately after computing it, BEFORE any
   render. (`test_verifier_renders_with_acceptance_criteria_not_absence_fence` — asserts the exact
   text the verifier receives contains the criteria and not the fence.)
2. **[P1] A missing pre-execution snapshot still produced a sufficient diff lane.** `run_capture`
   accepted `state_before=None` and still marked sufficiency — a false `state_before`/sufficiency
   the design's P1 forbids (absent base ⇒ base-unknown ⇒ owed). **Fold:** new `CaptureResult.base_unknown`
   (true when there is no stashed HEAD); when set, force `sufficient=False` and mark the diff lane
   owed (`None`). *(Rev 2 completed this: without a base a check outcome is not attributable to this
   turn, so `ran_and_failed()` also returns False when base-unknown — the failure signal is owed too,
   not just the sufficiency — so a base-unknown failed check degrades rather than driving a branchless
   escalation. See Revision 2 above.)* (`test_base_unknown_forces_diff_lane_owed`.)
3. **[P1] An empty/broken verifier output converged as `criteria_met`.** The boot verify callback
   returns `""` on a missing endpoint or a failed call; `run_verify` parsed that to no-verdict/
   no-findings, and `converged` only blocked an explicit FAIL/high-severity — so a broken verify
   with sufficient mechanical evidence converged with NO reviewer (grading-your-own-homework).
   **Fold:** `run_verify` now sets `ran = (verdict in PASS/FAIL) or has-findings`; a not-ran verify
   (empty/broken/no-invoker) lowers confidence to 0, and — for high-risk/irreversible — escalates to
   a human; `converged` blocks convergence when `verify_ran` is False, so a broken verify degrades
   (standard) or escalates (high-risk) instead of converging.
   (`test_empty_or_broken_output_marks_not_ran`, `test_unverified_blocks_convergence`,
   `test_broken_verify_does_not_converge`, `test_broken_verify_high_risk_escalates`.)

**Verification of Rev 1:** the judge's three exact probes now report FIXED
(criteria-visible / base-unknown-owed / empty-verify-not-converged + high-risk-escalates); focused
Phase-6 suites **182 tests pass**; full parity **3865 tests, 27 F/E identical to baseline, ZERO
new**; the adversarial re-check of the folds returned **0 findings**. Rev-0 detail follows.

---

## 1. What was built (design P0–P8 → code)

One new consolidated module + three additive extensions + the terminal/planning wiring, per the
consolidated-files rule. **Everything is gated behind `ORA_EXECUTION_LOOP` (default OFF)** — see §3.

| Design | Code | File |
|---|---|---|
| P0 self-evidencing gate; terminal-anchored controller | `should_engage` / `engage_signals`; `run_loop` | `orchestrator/execution_loop.py` (new) |
| P1 pre-execution state seam (tier-independent) | `snapshot_pre_execution` + planning-seam calls | `execution_loop.py`, `boot.py`, `server.py` |
| P1 Capture driver (non-mutating; mutating deferred) | `run_capture`, `_required_check_names`, `_record_deferred_mutating` | `execution_loop.py` |
| P2 dual-family verify + single-family degrade | `select_verify_endpoint`, `run_verify`; `Router.resolve_different_family` | `execution_loop.py`, `router.py` |
| P3 plan/exec revision router + invented-test tags | `route_findings`, `has_high_severity`, `obligating_invented_tests`, `parse_verify_output` | `execution_loop.py` |
| P4 stop rule + escalation branch + handback | `converged`, `escalation_warranted`, `create_escalation_branch`, `handback_reference`, `push_handback` | `execution_loop.py` |
| P5 criteria threading (dual planning scaffold) | `planning_block_from_context` | `execution_packet.py` |
| P6 fill the §9 blocks | `populate_loop_fields` | `execution_packet.py` |
| P4/P7 escalation git primitive env | `_git(env=)` | `evidence_runner.py` |
| terminal dispatch + verify invoker | `_execution_review_terminal`, `_make_execution_verify_invoker` | `boot.py` (+ `server.py` twin) |

## 2. The loop, concretely (what fires when)

- **Self-evidencing turn (neither §6 signal):** the loop is dormant; the terminal builds the
  Phase-4 record packet exactly as before — **byte-identical**.
- **Mutation turn (`any_mutation`):** Capture (drive the Phase-5 runner over the real delta, using
  the STASHED pre-execution base) → dual-family Verify over `render_for_review(packet)` → stop rule
  → converge (`criteria_met`) or escalate (`max_iterations_escalated`, unmerged branch + handback)
  or **degrade** to the text review (owed/deferred/empty lanes only — never churn).
- **Source-read-only turn (`source_read_suspected` and not `any_mutation`):** record the packet +
  a LOUD owed-`collect_provenance` marker; **does NOT enter the converge/escalate cycle** (its fill
  is Phase 8 — escalating would churn).

## 3. The one first-landing decision the judge should ratify (flag + actuator)

**`ORA_EXECUTION_LOOP` (default OFF), and `actuator=None` for the first landing.** This is the
house "flag provisional, validate-then-default-ON" rule — the same pattern as
`ORA_DELIVERABLE_SCRUB`, the RAG fit-gate, and the MSI newsworthiness gate (all shipped flag-gated
OFF). Rationale, stated plainly so the judge can accept or override:

- The loop introduces **new live behaviour** on mutation turns: a live verify model call, a git
  branch + durable-queue handback on escalation, and (when an actuator is wired) gear
  re-invocation. Landing that silently-on by default is a large, cost-affecting change on a
  cost-watched system.
- Flag OFF → the terminal + planning seam are **byte-identical to Phase 4** (parity is trivially
  preserved; confirmed: zero new failures). The whole controller — Capture, selector, verify, fork,
  stop rule, escalation branch, handback — is **built and unit-tested regardless of the flag**.
- **`actuator=None` (no live gear re-invocation) for the first landing** answers design **OQ1's**
  conservative option: the live loop does exactly ONE Capture + ONE verify + record + converge/
  escalate/degrade — **no surprise gear re-runs, no response mutation**. The full multi-iteration
  fork+actuator path is implemented and unit-tested (`test_actuator_revises_then_converges`),
  ready for a follow-up flip. The judge may direct default-ON and/or a wired actuator; both are
  one-line changes.

## 4. Safety properties held (hand-verified + tested)

- **Never mutates the user's git state.** `create_escalation_branch` writes only a NEW ref
  (`execution-review/escalation-<task_id>`) at the stashed pre-execution base and commits the
  working-tree snapshot via a **throwaway `GIT_INDEX_FILE`** + `commit-tree` — the user's real
  index, HEAD, working tree, and existing branches are untouched (verified against a real temp git
  repo: `test_branch_is_unmerged_and_leaves_user_state_untouched`). `.gitignore`d/secret files are
  excluded (`add -A` respects ignore; `test_gitignored_files_excluded`).
- **Never runs a mutating check against the live checkout** (⚖ Rev-2 P1). A `mutates:true` required
  check is recorded DEFERRED (loud marker + observed `evidence_check` event) and is **not
  escalate-forcing**; Phase 6's live evidence is the non-mutating catalog checks.
- **Escalates only on a RAN-and-FAILED check or a persistent high-severity finding** (⚖ Rev-1/Rev-2
  P4). An owed/deferred/empty lane (source-read provenance, repo-less, deferred mutating, no-sandbox
  refusal) records a loud marker + degrades — never escalates (`test_owed_lane_degrades_not_escalates`,
  `test_owed_deferred_empty_lane_never_escalates`).
- **Converges only with no high-severity finding of ANY class** (⚖ Rev-1 P1 — plan-level too:
  `test_high_severity_plan_level_also_escalates`).
- **state_before + escalation base come from the STASHED planning snapshot**, never a terminal-time
  (post-execution) read (⚖ Rev-1 P0). A snapshot with no valid HEAD is dropped, never a false
  `state_before`.
- **Different-family verify** never returns a same-family endpoint and never silently substitutes
  breadth; no cross-family endpoint → single-family degrade (lowered confidence + `fallback_reason`
  + human escalation on high-risk/irreversible) — `test_router_method_skips_same_and_unknown_family`,
  `test_single_family_*`.
- **Handback is a REFERENCE, not inlined content** — packet path + branch ref + reason + a REDACTED
  `render_for_review` summary with the UNVERIFIED-PRODUCER-CLAIM fence dropped; inherits the
  oversight queue's stealth-skip (`test_escalate_on_high_severity` asserts the redaction).
- **Stealth is dormant** (no packet, no loop, no branch, no queue — `test_stealth_is_dormant`).
- **Never raises into the pipeline** — every entry point is best-effort with `_note_failure`
  markers; the terminal returns the unchanged response on any failure.
- **`reversible` is NOT recomputed** (§6 tier-gate; high-risk == reversible:true is spec-correct).
- **Phase-4 fields preserved** — `populate_loop_fields` layers P6 fields over the P4 text-review
  verdict/scope/status and never clobbers `execution.delta`/`source_reads`/`producer_claim`.

## 5. §16-3 / observed-not-narrated fidelity (fold from hand-review)

`_required_check_names` returns the Contract's required set **verbatim** (unfiltered), so a required
check absent from the catalog is OBSERVED as a refused `evidence_check` event by `run_contract`
(never silently dropped) and counts as NOT sufficient — the executor still cannot invent a passing
check.

## 6. Tests

- **New `orchestrator/tests/test_execution_loop.py` (39 tests):** gate/self-evidencing short-circuit;
  loop-enabled flag; different-family selector (real `Router.resolve_different_family` +
  single-family + unknown-family); verify parse + single-family degrade + high-risk human-escalate;
  plan/exec fork + any-class high-severity; stop rule (converge / escalate-on-ran-and-failed /
  owed-never-escalates); Capture driver (no-repo owed, mutating deferred, light-runs-catalog);
  escalation branch (real temp git repo — unmerged + user-state-untouched + gitignore-excluded);
  `snapshot_pre_execution`; `run_loop` end-to-end (converge / escalate + handback / plan-level
  escalate / owed-degrade / source-read-only / stealth-dormant / actuator-revises-then-converges);
  Portability (git-ref-safe branch name, pure-config selector, sha check).
- **`test_execution_packet.py` (+~12):** `populate_loop_fields` fills each §9 block; preserves
  Phase-4 verification/execution fields; `reversible` not recomputed; light planning stays None;
  render shows populated criteria; escalated status; owed lane ≠ sufficient.
- **`test_evidence_runner.py` (+2):** `_git(env=)` inherit + GIT_INDEX_FILE isolation.
- **Judge-fold coverage (Rev 1):** base-unknown owed lane; verify `ran`/broken-verify degrade +
  high-risk escalate; verifier-sees-criteria; unverified blocks convergence.
- **Parity:** 3865 tests, 27 environmental FAIL/ERROR identical to baseline, ZERO new; 182 focused
  Phase-6 tests pass.

## 7. Portability (release-blocking amendment)

- **Surfaces touched:** the escalation-branch git primitive (`_git` is `subprocess`-based, shell-free,
  cross-platform; `GIT_INDEX_FILE` is a git-native env var, portable); the different-family selector
  (pure config read, platform-neutral); the Capture driver (delegates to the Phase-5 runner, already
  platform-gated — macOS `sandbox-exec` / Linux `unshare` / Windows `ORA_EVIDENCE_SANDBOX`; a host
  with no enforcing backend REFUSES the check cleanly → the lane stays owed → the loop degrades, does
  not escalate). No new path roots (all via `runtime_paths` / the runner's existing discovery /
  `tempfile`).
- **Tests added (Windows-sim, run on mac/Linux):** `test_branch_name_is_git_ref_safe` (Windows-style
  path chars `C:\…`, spaces, tabs never leak into a git ref); `test_family_selector_is_pure_config_read`
  (no OS/filesystem touch); `_looks_like_sha`.
- **Remaining assumption:** on a host with no enforcing sandbox backend (or for any `mutates:true`
  check, deferred regardless of host), the check is REFUSED/DEFERRED for an environment/scope reason
  → recorded as owed with a LOUD marker + an observed `evidence_check` event → the loop **degrades to
  the text review, it does NOT escalate**. Honest degradation, surfaced in the packet.

## 8. Scope boundary (deferred, stated not silently assumed)

Not built (correct scope): the `collect_provenance` claim-to-source map fill (Phase 8); the isolated
mutating actuator (git worktree add → apply delta → run → remove) (Phase 8); MSI's own loop wiring
beyond the `invoke_real_gear4` inheritance it gets by construction (Phase 8); tiered durable
persistence / sensitivity-driven redaction of the packet (Phase 7 — the packet stays `trace_local`);
a live gear-reinvocation actuator (wired-and-tested, flag/param-gated OFF for the first landing).

## 9. Adversarial pre-check (7 diverse lenses × adversarial verify; every finding hand-re-verified)

Ran a 7-lens adversarial completeness-critic over ONLY the changed logic (git-mutation safety,
parity/regression, loop convergence/churn, family selector + capture, secrets/handback/stealth,
spec-fidelity). Surfaced **5 raw findings**; two were CONFIRMED by the automated verify with full
end-to-end reproduction, and **I hand-re-verified all five against the code myself** (the proven
discipline — the automated vote under-reports and was partly rate-limited). **4 were real bugs
(1 duplicate); all folded.** Zero regressions found in the parity/git-mutation/secrets lenses.

1. **[MAJOR, CONFIRMED] Light-tier deferred mutating check → false convergence.** At `light` tier
   (no Contract), `run_capture`'s sufficiency fell back to the `runnable`-only set, so a deferred
   `mutates:true` catalog check was dropped from `contract_sufficient` and the turn falsely read
   sufficient → `criteria_met` — the exact tier ⚖ Rev-2 P2 brought into scope, violating ⚖ Rev-2 P1
   ("a deferred mutating required check → not sufficient → honest degrade") and §16-2 "absence ≠
   pass". **Fold:** sufficiency is judged against the FULL required set (`required`, incl. the
   deferred names), so a deferred required check is skipped → not sufficient → honest degrade.
   (`test_light_tier_deferred_mutating_is_not_sufficient` — uses the REAL sufficiency logic.)
2. **[MAJOR, CONFIRMED] Stop rule ignored the verifier's `VERDICT: FAIL` and non-"high" severities.**
   `converged` = `sufficient AND not has_high_severity`, and `has_high_severity` matched ONLY the
   literal token `"high"`, and the parsed VERDICT was read nowhere in the stop logic. So a
   `VERDICT: FAIL` with a `severity=critical` finding, or a prose-only FAIL with no parsed findings,
   converged as `criteria_met` on a deliverable the different-family verifier explicitly rejected —
   the "converge over a failed verify" failure ⚖ Rev-1 P1 exists to prevent. **Fold (two parts):**
   (a) broadened the blocking-severity set to `{high, critical, blocker, severe, major, fatal}`;
   (b) `converged` now blocks on an explicit `VERDICT: FAIL`, and `escalation_warranted` treats a
   FAIL verdict as a genuine unresolved failure → escalate to a human, not a silent degrade.
   (`test_critical_and_blocker_severity_also_block`, `test_fail_verdict_blocks_convergence`,
   `test_fail_verdict_with_sufficient_evidence_escalates_not_converges`.)
3. **[MAJOR, hand-verified] Handback stealth defense-in-depth gap.** `push_handback`'s primary path
   `oversight_queue.add_entry` writes straight to the durable JSONL with NO stealth guard (only the
   `_append_human_queue` fallback stealth-skips), and the entry lacked a top-level `conversation_id`
   for the Layer-9 purge backstop — defeating both stealth layers the design named (run_loop already
   gates on non-stealth, but the design relies on the handback INHERITING the skip). **Fold:**
   `push_handback` now checks the stealth context itself before either backend; `handback_reference`
   carries a top-level `conversation_id`. (`test_push_handback_stealth_skips_durable_write`,
   `test_reference_has_top_level_conversation_id`.)
4. **[MINOR, hand-verified] Futile actuator churn on a structurally-owed lane.** When an actuator is
   wired (the Phase-8 shape), an insufficiency caused ONLY by an owed/deferred lane (no finding to
   route, no ran-and-failed check) still spent a full gear re-invocation that could never make the
   lane sufficient (against P4 "never churn"; latent because the first landing wires `actuator=None`).
   **Fold:** the loop only revises when there is something a revision can act on (a finding to route
   OR a ran-and-failed check); a purely-owed insufficiency degrades without re-invoking the actuator.
   (`test_owed_lane_with_pass_verdict_and_actuator_does_not_churn`.)

**Also folded from my own hand-review (before the workflow):**
- **§16-3 fidelity:** `_required_check_names` returns the Contract required set VERBATIM so a
  catalog-absent required check is OBSERVED as a refused `evidence_check` by `run_contract`, never
  silently dropped.
- **⚖ Rev-1 P4 / OQ4 honesty:** when the executor committed in place (HEAD advanced past the base),
  the escalation records `unmerged_guarantee: PARTIAL` — the branch isolates the working-tree delta
  only; full §13 isolation of a committing run requires `clean_worktree` from the start (Phase 8) —
  rather than resetting the user's branch to fake an unmerged branch.
- **Hardening:** `snapshot_pre_execution` drops a snapshot with no valid HEAD (an explicit non-git
  `repo_root`) rather than stashing a FALSE `state_before`.

**Correctly NOT flagged** (hand-verified as non-issues): parity flag-OFF byte-identity; the
`create_escalation_branch` git plumbing (never touches user HEAD/index/tree — proven against a real
repo); circular imports; `reversible:true` at high-risk; Phase 7/8 scope items.

Post-fold: Phase 6 focused suites **175 tests, all pass**; full parity re-run clean (see §below).

## 10. On approval

Re-fetch origin/main (it advances via concurrent sessions); rebase onto current; branch → commit →
push → PR → squash-merge → delete branch (local + remote) → prune the worktree → fast-forward
`~/ora` main (ff-only). Report PR # + bare SHA.
