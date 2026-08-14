# Execution Review — Phase 8 Chunk B IMPLEMENTATION packet (Rev 1)
## The isolated mutating-check actuator

*Execution Thread, 2026-07-05. Design: `phase8-design.md` Rev 4 §3 (judge-approved). Worktree `/Users/oracle/ora-worktrees/phase8b-impl`, branch `execution-review-phase8b-impl` **rebased onto current origin/main `a511e7c4`** (the legacy-path portability retrofit PR #194 landed — boot.py/web_search.py, zero overlap; rebase was clean). Durable diff: `phase8b-impl.diff`. NO commit — this goes to the CODE-REVIEW gate.*

*__⚖ Rev 1 (2026-07-05) — code-review BLOCK folded + adversarial re-check.__ The judge BLOCKED Rev 0 with 2 findings, both real, both folded: __P1 (portability):__ the 3 "runs-isolated-and-passes" integration tests assumed an enforcing `network:deny` backend and would FAIL (not skip) on a no-backend Windows/CI box → gated with `@unittest.skipUnless(_BACKEND_AVAILABLE, …)` (non-probing capability predicate) + a new `test_no_backend_defers_honestly_without_worktree` proving the deferral directly. __P2 (honest observability):__ `run_isolated_checks` stamped `isolated.ran=True` even when the runner refused every check unrun (no backend) → added the up-front `_batch_has_enforcing_backend` gate (defer WITHOUT building a pointless worktree, matching "defer honestly where no enforcing backend exists") + a belt (`isolated.ran` True only when a check GENUINELY ran, `checks_ran` count) + reworded caller reason. Then a 3-lens adversarial re-check over the fold (opus verifiers) surfaced __1 REAL minor__ (the new gate short-circuited the backend-independent crash-residue orphan-prune sweep on no-backend turns — narrowing the load-bearing ref-less-snapshot-unpin guarantee) → FOLDED: prune moved ABOVE the gate, runs unconditionally + regression test; __1 REJECTED__ (import-time network probe — the verifier reproduced only a mild ~4s single-probe on an off-mac declared-wrapper box, not the filed hang; folded anyway as cheap hardening: the test's `_BACKEND_AVAILABLE` now uses non-probing capability checks so import stays pure). Design-spec-fidelity lens: ZERO findings. Rev-0 body below (still accurate; test/parity counts updated at the tail).*

---

## 1. What was built (design §3, complete)

### 1.1 Lifecycle primitives (`evidence_runner.py`, generic)
- **`tree_commit_at(repo, base_sha)`** — REF-LESS temp commit of the CURRENT tree parented at the pre-exec base, via the proven Phase-6 throwaway-index idiom (`GIT_INDEX_FILE` + `read-tree base` + `add -A` + `write-tree` + `commit-tree`). Captures untracked files (the delta_ref patch does not — test-pinned); user HEAD/index/refs/status byte-identical after (test-pinned). Ref-less is definitive per Rev 3: a crash leaves an unreachable object, GC-collectable — **now actually true cross-repo, see fold #1**.
- **`create_isolated_worktree(repo, sha, sparse=None)`** — `git worktree add --detach` under `runtime_paths.SCRATCH_DIR/exec-review-worktrees/` (`mkdtemp`); containment via `runtime_paths.within_base` (case-normalized house helper) + the pre-flight the ACTIVE backend will apply (full SBPL check on-mac; SEC-2-ancestry-only elsewhere — fold #2); sparse support (`--no-checkout` + `sparse-checkout set --no-cone` + `checkout`, §3.6) with the `extensions.worktreeConfig` side effect DISCLOSED in-code (fold #5; no Chunk-B caller passes `sparse` — the Chunk-C addendum decides the vault opt-in). Half-built worktrees are removed before returning None (test-pinned).
- **`remove_isolated_worktree`** — `worktree remove --force` + retry + `rmtree` fallback + `worktree prune`; **containment-guarded: refuses any path outside the scratch worktree root** (test-pinned against a victim dir) — this function cannot be aimed at user content.
- **`prune_orphan_worktrees`** — crash-residue sweep at actuator start: age-based (24h) rmtree of stale scratch dirs, **each swept dir's OWNING repo resolved from its `.git` gitdir pointer and pruned** (fold #1 — a linked worktree's detached HEAD is a GC reachability ROOT; without the owner prune, a crashed vault run's snapshot of uncommitted vault content stayed retrievable in the vault's object store indefinitely; the pre-check pinned this empirically and the fold is test-pinned end-to-end: sweep for repo A → repo B's snapshot becomes GC-collectable), plus a trailing prune on the current repo.
- **`inplace_checks_refused(repo_root)`** — the §3.3 routing predicate, keyed on the backend that ACTUALLY pre-flights (macOS sandbox-exec) — see fold #2.
- `_git` gains `timeout=` (default 30s unchanged; lifecycle passes 300s — vault-scale `add -A`).

### 1.2 Loop integration (`execution_loop.py`)
- **`run_capture` split rewrite:** mutating checks now RUN via `run_isolated_checks` (prune → temp-commit → worktree → `run_contract(…, worktree=wt, mode="clean_worktree")` → finally remove+prune, `worktree_removed` recorded, residue marker if removal fails). The DEFERRED marker survives only as the honest fallback — kill-switch (`ORA_EXEC_REVIEW_MUTATING=off`, OQ-7: default ON with the loop), base-unknown (no pre-exec parent for the delta commit), or lifecycle failure — each with a cause-naming reason. `fill_contract` sufficiency unchanged (full required set; a run-and-passed mutating check now flips sufficiency TRUE — test-pinned).
- **SEC-2 routing (Rev-3 blocker fold delivered):** `requires_isolated_worktree` repos (the vault class — in-place runs refused by the sandbox pre-flight) route ALL their checks through the worktree, mutating or not (test-pinned: a non-mutating check on a refused repo runs isolated and passes).
- **Caller-declared `clean_worktree` (§3.4/OQ-9):** `_capture_mode` accepts the declaration (caller attests the checkout IS isolated → checks run in place, runner permits mutating); nothing in boot/server ever declares it (verified — no live-chat rewiring). The escalation `unmerged_guarantee` note is NARROWED per §3.4: full isolation "available via clean_worktree execution from the start; this run executed in place."
- **Observability:** `execution.isolated_checks` ({ran, delta_commit, checks, worktree_removed, fallback_reason}) + `delta_attribution: approximate` in review_dirty_diff mode — whitelisted into `populate_loop_fields` (the Rev-3 silently-dropped-keys hazard).

### 1.3 Live-path probe (evidence, not narration)
Hand-probed against the REAL default scratch (`~/ora/scratch`, under the deny-listed WORKSPACE root — the one location the hermetic tests don't use): the sandboxed mutating check **ran** (`enforcement_model: orchestrated`), passed, `sufficient: True`, `worktree_removed: True`, zero residue — the Phase-5 SBPL last-match-wins re-allow behaves as designed at the live location.

## 2. Adversarial pre-check + the rate-limit fallback

4 lenses × per-finding verify; **the session limit killed 10 verify agents and one whole lens (regression-live) mid-run — per the standing discipline every null vote was RE-VERIFIED BY HAND and the missing lens was run by hand.** Disposition: **6 REAL folded, 4 REJECTED** (with reasons), regression-lens findings folded or cleared:

| # | Sev | Finding (verification) | Fold |
|---|---|---|---|
| 1 | major | Cross-repo orphan sweep stranded the OWNER repo's `.git/worktrees` metadata, whose detached HEAD PINS the ref-less snapshot against GC — attacker reproduced empirically (snapshot survives `gc --prune=now` until owner prune) | gitdir-pointer owner resolution + per-owner prune + trailing current-repo prune; end-to-end GC test |
| 2 | **blocker** | Windows misroute: `\` is SBPL-unsafe by character set → the routing predicate flagged EVERY off-mac repo → all checks (incl. previously-running non-mutating ones) deferred — hand-confirmed against `_SBPL_UNSAFE` | new `inplace_checks_refused` keyed on `_macos_sandbox_available()`; worktree pre-flight platform-split (SEC-2 ancestry everywhere, SBPL chars on-mac only); off-mac ntpath test |
| 3 | minor | SEC-2/fallback deferrals stamped `mutates: true` on NON-mutating checks' events (hand-confirmed) | `_record_deferred_mutating` carries the check's real flag; test |
| 4 | minor | Test suite hardcoded `/opt/homebrew/bin/python3` (portability; judge focus) | bare `python3` token — `resolve_command` maps to `sys.executable` (house convention) |
| 5 | minor | Sparse path durably writes `extensions.worktreeConfig=true` into the user repo's shared `.git/config` (attacker pinned empirically; latent — no sparse caller in B) | disclosed in-code + here; Chunk-C addendum decides the vault opt-in posture |
| 6 | minor | Injected runners without the lifecycle fell back with an `AttributeError` dressed as a lifecycle error | capability guard → honest "runner lacks worktree lifecycle support"; test |
| R1 | — | `tree_commit_at` index leak — REJECTED (hand-review: `finally` unlinks on every path incl. timeout) | — |
| R2 | — | sparse unreachable from run_capture — REJECTED as defect (design-approved sequencing: support in B, vault wiring in C) | disclosed |
| R3 | — | `delta_attribution` keyed on actuator-ran — REJECTED (matches §3.2's approved scope) | — |
| R4 | — | `rmtree(ignore_errors)` silent partial — REJECTED as blocker (removal failure IS marked: `worktree_removed: False` + residue marker + 24h age-prune backstop; disclosed residue window) | — |

**Hand-run regression-live lens:** ora's own catalog declares ZERO `mutates: true` checks → **the live actuator surface today is nil** (it engages only when a repo catalog declares a mutating check — no behavior change on current live turns beyond the dormant code path); ora's tracked tree is 372 files → per-turn worktree cost trivial when it does engage; `enforcement_model: "orchestrated"` on isolated results is honest (they really ran under sandbox-exec) and downstream-safe (display/packet only); the `isolated` dict is plain-JSON-serializable; per-capture prune cost is one `listdir`.

## 3. Tests + parity

- **New `test_isolated_actuator.py` (17 tests, real git + real sandbox):** untracked-file fidelity (asserted INSIDE the check: it exits nonzero if the untracked file is missing from the worktree), ref-less + HEAD/index/refs/status untouched, materialize/remove/prune-metadata, sparse-only materialization, containment refusal (victim dir untouched), orphan sweep (stale swept/fresh kept), **cross-repo GC-unpin end-to-end**, add-failure cleanup, end-to-end mutating check passes isolated + writes land ONLY in the disposable tree + zero residue + sufficiency flips true, kill-switch/base-unknown/lifecycle fallbacks with cause-naming reasons, SEC-2 all-checks routing, declared-clean_worktree in-place run, **off-mac predicate never misroutes (Windows-shaped paths)**, deferred-event mutates honesty, bare-runner fallback, packet observability fields.
- **Focused: 211 pass** (isolated_actuator [20 tests, incl. the 3 Rev-1 backend-gated + 3 new no-backend/belt/orphan-sweep-on-defer regressions] + execution_loop + evidence_runner + execution_packet).
- **Parity (FINAL, post-all-folds, rebased base):** fresh baseline captured at the REBASED base `a511e7c4` in a throwaway worktree (22F+5E=27, `phase8b-baseline-a511.txt`). Final run: **3,982 tests, sorted FAIL/ERROR lists IDENTICAL (`diff` clean) — ZERO new** (`phase8b-post-final.txt`). Suite env: `ORA_PIPELINE_TRACE=off ORA_TOOL_EVENTS=off`. Diff: 4 files, +1,089/−35.
- **Rev-1 test additions (P1/P2 + re-check folds):** `test_no_backend_defers_honestly_without_worktree` (no worktree built, honest deferral, no residue), `test_all_skipped_isolated_run_records_fallback_not_true` (belt: `isolated.ran` never True on all-skipped), `test_orphan_sweep_runs_even_on_no_backend_defer_path` (the re-check fold — crash-residue sweep runs before the gate); the 3 run-path tests skip cleanly where no backend enforces `network:deny`.

## 4. Portability (release-blocking amendment)

- The Windows-misroute blocker fold is the headline: routing + worktree pre-flights are now platform-honest (SBPL character rules apply only where SBPL runs; SEC-2 ancestry containment is universal). Off-mac behavior: non-mutating checks unchanged from Phase 5; mutating checks defer honestly where no enforcing backend exists (unchanged enforce-or-refuse posture).
- `remove --force` + retry + `rmtree` fallback per design (Windows handle-latency); short `wt-` mkdtemp names; `within_base` for every new containment decision; no `fcntl`/POSIX-only APIs; `encoding="utf-8"` pinned on the one new file read (`.git` gitdir pointer); no new locks.
- Windows-sim coverage: ntpath-shaped predicate tests; lifecycle helpers exercised via real git (platform-neutral commands).
- Unchanged assumption (disclosed): sandbox ENFORCEMENT stays macOS/Linux — Phase-5 posture untouched.

## 5. Scope boundary honored

No flag flips; no gear-reinvocation actuator; no adapter families (C) or MSI wiring (D); no `reversible:true` change; no live-chat-turn rewiring (nothing sets `exec_review_mode`; the declaration is caller-opt-in only); execution_loop.py edits do not overlap the parallel legacy-path session's files; `ORA_EXEC_REVIEW_MUTATING` born default-ON-with-loop per the judge's OQ-7 decision (kill-switch available).

---
*Gate: NO commit until the judge approves. On approval: re-fetch origin/main (the legacy-path PR may have landed), rebase, branch → commit → push → PR → squash-merge → delete branch → prune worktree → ff `~/ora` main; report PR# + bare SHA.*
