"""orchestrator/execution_loop.py — Execution Review Phase 6 (wire the loop).

The execution-review LOOP CONTROLLER (spec §15 Phase 6), assembled ENTIRELY from
parts already present (§4 "same downstream machinery, NOT a second pipeline"):

    plan (apply_criteria + apply_evidence_contract, already live at planning)
      → execute (the gear run — the single-writer actuator, §3)
        → Capture (drive the Phase-5 evidence_runner over the real delta)
          → Verify (dual, DIFFERENT model family; single-family graceful degrade, §12)
            → revision router (findings tagged plan_level vs execution_level, §12)
              → stop rule (converge OR escalate — never churn, §13)
                → escalation to an inspectable, UNMERGED branch the packet links to

This module is a CONTROLLER anchored at the pipeline terminal (``boot.py`` /
``server.py``), engaging ONLY on non-self-evidencing turns (a §6 signal fired). The
common analytical-prose turn is self-evidencing and stays byte-identical to Phase 4
(the gear's own text review WAS the review; the terminal builds the record packet
exactly as before). Two live sub-cases on a reality-contact turn:
  * a **mutation** turn (``any_mutation``) drives the full converge/escalate loop over
    the adapted ``diff_validate`` lane;
  * a **source-read-only** turn (``source_read_suspected`` and NOT ``any_mutation``)
    records the packet with an owed ``collect_provenance`` lane + a LOUD deferred
    marker and does NOT enter the converge/escalate cycle (its fill is Phase-8 — so
    escalating it would churn, ⚖ Rev-1 judge P1).

Held-live invariants (§16): criteria set by a step separate from + prior to execution
(§16-1, via ``apply_criteria``); the evidence recipe declared independently of the
executor (§16-2, the write-protected ``.ora/evidence.yaml`` + the planning Contract);
reality contact observed not narrated (§16-3, the runner records an ``evidence_check``
event per outcome). Escalation lands the abandoned attempt on an inspectable, unmerged
branch (§13) and hands a REFERENCE (not inlined ``producer_claim``) to the durable
Paused queue.

ROLLOUT (house rule — flag provisional, validate then default-ON, mirroring
``ORA_DELIVERABLE_SCRUB`` / the RAG fit-gate / the MSI newsworthiness gate): the LIVE
firing at the terminal is gated behind ``ORA_EXECUTION_LOOP`` (default OFF). Flag OFF
→ the terminal is byte-identical to Phase 4 and this controller never runs at runtime
(parity is trivially preserved); the whole controller + Capture + selector + verify +
fork + stop/escalate + escalation-branch are BUILT and unit-tested regardless. The
flag only governs whether the terminal fires the loop on a reality-contact turn. The
loop introduces NEW live model calls (verify) + a possible gear re-invocation
(actuator) + a git branch on escalation, so a validate-then-default-ON rollout is the
responsible first landing; the flip is one env var once validated live.

Nothing here raises into the pipeline: every entry point is best-effort and a caught
failure stamps an observable marker (``tool_events._note_failure``), never a silent
swallow that could read as "no reality contact."
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

try:  # runtime import shape mirrors the rest of orchestrator/
    import execution_packet as _ep
except ImportError:  # pragma: no cover
    from orchestrator import execution_packet as _ep

try:
    import evidence_runner as _er
except ImportError:  # pragma: no cover
    from orchestrator import evidence_runner as _er

try:  # Phase 7 — tiered persistence at the terminal (§14)
    import execution_persistence as _epersist
except ImportError:  # pragma: no cover
    from orchestrator import execution_persistence as _epersist

try:  # Phase 8 Chunk A — the collect_provenance lane filler (§4/§7)
    import execution_provenance as _eprov
except ImportError:  # pragma: no cover
    from orchestrator import execution_provenance as _eprov

try:  # Phase 8 Chunk C — deploy_probe + render_inspect declared-lane fillers (§4)
    import execution_families as _efam
except ImportError:  # pragma: no cover
    try:
        from orchestrator import execution_families as _efam
    except ImportError:
        _efam = None


# ── Provisional constants (flagged per house rule: retunable, not calibrated) ──
MAX_LOOP_ITERATIONS = 2          # matches the gear's own MAX_VERIFY_CYCLES intuition
SINGLE_FAMILY_CONFIDENCE_PENALTY = 0.3   # lowered confidence when verify is same-family
_DEFAULT_CONFIDENCE = 0.7        # assumed baseline when the verifier omits CONFIDENCE
# Severities that block convergence (any class). The verify prompt asks for
# high|medium|low, but a real model may emit critical/blocker/severe/major for the
# worst issues — treat ANY of those as ≥ high so a critical finding can never slip
# past the stop rule as a mere non-"high" token (adversarial-precheck fold).
HIGH_SEVERITY = "high"
_BLOCKING_SEVERITIES = frozenset({"high", "critical", "blocker", "severe", "major", "fatal"})
_DEFAULT_MODE = "review_dirty_diff"       # non-mutating capture over the live tree
_ENV_FLAG = "ORA_EXECUTION_LOOP"          # LIVE-firing gate (default OFF)
_ESCALATION_BRANCH_PREFIX = "execution-review/escalation-"
_REDACTED_SUMMARY_CAP = 4_000


def loop_enabled() -> bool:
    """True when the LIVE terminal firing is enabled (``ORA_EXECUTION_LOOP`` truthy).
    Default OFF — flag-OFF makes the terminal byte-identical to Phase 4."""
    return str(os.environ.get(_ENV_FLAG, "")).strip().lower() in ("1", "true", "on", "yes")


def _mark_failure(err: Exception, where: str) -> None:
    """Observable marker for a caught failure (never re-raises)."""
    try:
        try:
            import tool_events as _te
        except ImportError:  # pragma: no cover
            from orchestrator import tool_events as _te
        _te._note_failure(err, where)
    except Exception:
        pass


# ── The self-evidencing GATE (§6) — reads only ALREADY-folded signals ──────────
def engage_signals(ro: dict | None) -> dict:
    """Return the two folded §6 signals from the in-scope ``record_route_observed``
    result — NO new observation, NO re-fold (condition 1)."""
    sig = (ro or {}).get("signals") or {}
    return {
        "any_mutation": bool(sig.get("any_mutation")),
        "source_read_suspected": bool(sig.get("source_read_suspected")),
    }


def should_engage(ro: dict | None) -> bool:
    """Engage the loop only on a non-self-evidencing turn (a §6 signal fired). The
    common self-evidencing turn returns False → the terminal degrades to the
    Phase-4 record packet, byte-identical, zero regression."""
    s = engage_signals(ro)
    return bool(s["any_mutation"] or s["source_read_suspected"])


# ── Capture (§3/§7/§10/§11) — drive the Phase-5 runner over the real delta ─────
@dataclass
class CaptureResult:
    """The mechanical Capture outcome for the ``diff_validate`` lane."""

    mode: str = _DEFAULT_MODE
    repo_root: str | None = None
    state_before: dict | None = None
    state_after: dict | None = None
    delta_ref: str | None = None
    results: list = field(default_factory=list)      # list[CheckResult]
    deferred_mutating: list = field(default_factory=list)   # names still deferred (fallback)
    sufficient: bool = False
    no_repo: bool = False            # no discoverable repo → diff+validate lane owed
    no_checks: bool = False          # repo-less / no declared checks → owed, degrade
    base_unknown: bool = False       # no pre-execution snapshot → base-unknown, lane owed
    enforcement_model: str = "in_harness"
    isolated: dict | None = None     # Phase 8 Chunk B — {ran, delta_commit, checks,
                                     #   worktree_removed, fallback_reason} observability

    def ran_and_failed(self) -> bool:
        """A check that RAN and returned a negative verdict (evidence exists and is
        negative) — the ONLY check-side condition that warrants escalation (§13/P4).
        A skipped/refused/deferred check is NOT a ran-and-failed check.

        When the base is UNKNOWN (no pre-execution snapshot), a check outcome is NOT
        attributable to this turn (the working tree may have carried a pre-existing
        failure the executor never touched) — so it is OWED, not a real ran-and-failed
        signal, and does NOT drive escalation (judge P1 fold: base-unknown stays owed).
        Without a base, no §13 abandoned-attempt branch can be created anyway."""
        if self.base_unknown:
            return False
        for r in self.results or []:
            if not getattr(r, "skipped", False) and not getattr(r, "passed", False):
                return True
        return False


def _capture_mode(context_pkg: dict | None) -> str:
    """Capture mode: ``review_dirty_diff`` by default, ``continue_user_changes``
    when the caller declares the user owns the tree. ``clean_worktree`` is
    accepted ONLY as a CALLER DECLARATION (Phase 8, design §3.4/OQ-9): the
    caller attests the checkout it points Capture at IS an isolated worktree
    (a programmatic/recipe executor that ran in isolation from the start) —
    that declaration is the caller's responsibility and is what earns the
    FULL §13 unmerged guarantee. The core chat pipeline never declares it
    (⚖ Rev-2 P1 still holds: never against the user's live checkout); the
    ISOLATED-CHECK actuator does not use this mode either — it builds its own
    disposable worktree and passes mode="clean_worktree" per-call."""
    m = (context_pkg or {}).get("exec_review_mode")
    if m in ("review_dirty_diff", "continue_user_changes", "clean_worktree"):
        return m
    return _DEFAULT_MODE


def discover_repo_root(context_pkg: dict | None = None, *, runner: Any = None) -> str | None:
    """Discover the repo root for Capture / the pre-execution snapshot: explicit
    ``context_pkg['repo_root']`` → ``ORA_PROJECT_ROOT`` → the discoverable catalog's
    grandparent (the dir that holds ``.ora/``) → cwd — each accepted only if it is a
    git repo. Returns the root or None. Never raises."""
    runner = runner or _er
    ctx = context_pkg or {}
    try:
        for cand in (ctx.get("repo_root"), os.environ.get("ORA_PROJECT_ROOT")):
            if cand and _is_git_repo(cand, runner):
                return str(cand)
        cat = None
        try:
            cat = runner.discover_catalog(ctx.get("repo_root"))
        except Exception:
            cat = None
        if cat:
            grand = os.path.dirname(os.path.dirname(str(cat)))
            if grand and _is_git_repo(grand, runner):
                return grand
        try:
            cwd = os.getcwd()
        except Exception:
            cwd = None
        if cwd and _is_git_repo(cwd, runner):
            return cwd
        return None
    except Exception as e:
        _mark_failure(e, "execution_loop_discover_repo")
        return None


def _is_git_repo(path: str, runner: Any = None) -> bool:
    runner = runner or _er
    try:
        rc, out = runner._git(str(path), ["rev-parse", "--is-inside-work-tree"])
        return rc == 0 and out.strip() == "true"
    except Exception:
        return False


def snapshot_pre_execution(context_pkg: dict, *, repo_root: str | None = None,
                           runner: Any = None) -> dict | None:
    """PLANNING-STAGE pre-execution state seam (⚖ Rev-1 judge P0). Capture the TRUE
    pre-execution git state (HEAD SHA + dirty snapshot) BEFORE any mutation-capable
    actuator runs, and stash it on ``context_pkg['exec_review_state_before']`` — the
    exact base for ``execution.state_before`` AND the escalation-branch base (a
    terminal-time read would be POST-execution, ``evidence_runner.py`` ``_git_state``
    reads *current* HEAD). TIER-INDEPENDENT (⚖ Rev-2 P2: ``light`` included — decoupled
    from the ``standard+`` Contract seam). Cheap (``git rev-parse`` + ``status``),
    additive, never-raises. Returns the snapshot or None (no repo / no stash)."""
    runner = runner or _er
    try:
        rr = repo_root or discover_repo_root(context_pkg, runner=runner)
        if not rr:
            return None
        mode = _capture_mode(context_pkg)
        before = runner.snapshot_before(rr, mode)
        # A snapshot with no HEAD (an explicit repo_root that is not a git repo, or a
        # git read that failed) is NOT a valid base — return None rather than stash a
        # FALSE state_before (§P1: never a false state_before; the lane stays owed).
        if not (before and before.get("head")):
            return None
        if context_pkg is not None:
            context_pkg["exec_review_state_before"] = before
            context_pkg.setdefault("repo_root", rr)
        return before
    except Exception as e:
        _mark_failure(e, "execution_loop_snapshot_before")
        return None


def _required_check_names(contract: dict | None, catalog: Any) -> list:
    """The checks Capture must run: at ``standard+`` the Contract's
    ``required_standard_checks`` VERBATIM (a task-specific subset); at ``light`` (no
    bespoke Contract) the repo catalog's own checks directly (§8/§10 "basic evidence =
    the repo catalog checks only"). The Contract set is returned UNFILTERED so a
    required check absent from the catalog is OBSERVED as a refused ``evidence_check``
    event by ``run_contract`` (§16-3 observed-not-narrated), never silently dropped —
    the executor still cannot invent a check (an absent one is recorded as a refusal
    and counts as NOT sufficient, §16-2). The contract producer already restricts
    required to catalog checks upstream, so this is defensive fidelity."""
    if contract and contract.get("required_standard_checks"):
        return list(contract["required_standard_checks"])
    return sorted((getattr(catalog, "checks", None) or {}).keys())


_MUTATING_FLAG = "ORA_EXEC_REVIEW_MUTATING"   # kill-switch (OQ-7): default ON
                                              # when the loop is on; "off"
                                              # restores the deferred marker


def mutating_actuator_enabled() -> bool:
    """The isolated-check actuator runs whenever the loop runs, unless the
    kill-switch says off (OQ-7, judge-approved: the loop flag is the master
    gate; a second default-OFF flag would leave the DEFERRED marker in place
    after the phase that exists to close it)."""
    return str(os.environ.get(_MUTATING_FLAG, "")).strip().lower() not in (
        "0", "off", "false", "no")


def requires_isolated_worktree(repo_root: str | None, runner: Any = None) -> bool:
    """True when in-place checks against this repo would ACTUALLY be refused
    by the runner's own pre-flight (SEC-2: the repo IS / is an ancestor of a
    private root — the vault case). Such a repo's checks — mutating OR not —
    can only ever run inside the disposable worktree (design ⚖ Rev 3: the
    vault family was structurally unrunnable without this routing).

    Delegates to ``runner.inplace_checks_refused`` — keyed on the backend
    that really pre-flights (macOS sandbox-exec). ⚠ Pre-check BLOCKER fold:
    keying on the raw ``sandbox_worktree_unsafe`` misrouted EVERY repo on
    Windows (all backslashed paths are SBPL-unsafe by character set) into
    the worktree path, then deferred every check when the worktree path was
    refused too — a silent off-mac regression of the Phase-5 posture."""
    runner = runner or _er
    try:
        if not repo_root:
            return False
        fn = getattr(runner, "inplace_checks_refused", None)
        if fn is None:
            return False
        return bool(fn(str(repo_root)))
    except Exception:
        return False


def _record_deferred_mutating(name: str, runner: Any,
                              reason: str | None = None,
                              mutates: bool = True) -> Any:
    """Record a required check as DEFERRED — a LOUD owed marker + an OBSERVED
    ``evidence_check`` event with a skip_reason (never a silent skip, §16-3).
    NOT escalate-forcing (P4). Phase 8: this is now the FALLBACK path
    (actuator disabled / base-unknown / lifecycle failure) and the reason
    names the actual cause. ``mutates`` carries the check's REAL flag — the
    SEC-2 fallback defers NON-mutating checks too, and stamping those events
    ``mutates: true`` would be dishonest event metadata (pre-check fold).
    Returns the CheckResult so it rides the packet's lane."""
    reason = reason or (
        "check deferred — the isolated-check actuator did not run "
        "(unspecified); never run against the live checkout")
    res = _er.CheckResult(name=name, skipped=True, skip_reason=reason)
    try:
        _er._record_check_event(_er.Check(name=name, mutates=bool(mutates)), res)
    except Exception:
        pass
    _mark_failure(RuntimeError(f"deferred check '{name}': {reason}"),
                  "execution_loop_deferred_mutating")
    return res


def _batch_has_enforcing_backend(runner: Any, catalog: Any,
                                 check_names: list) -> bool:
    """True when AT LEAST ONE named check has an enforcing backend for its
    network policy right now (macOS sandbox-exec / native Linux unshare /
    declared ``ORA_EVIDENCE_SANDBOX`` wrapper). When none do, the runner
    would refuse every check unrun (§7) and the worktree would be pointless —
    the actuator defers honestly instead (judge P2 fold). Uses the SAME
    ``enforcement_backend`` decision the runner itself makes, so it can never
    disagree with the runner. Fails toward True (attempt) on any error — a
    predicate bug must never silently disable the actuator where a backend
    genuinely exists; a wrong 'attempt' is still safe (the runner refuses)."""
    try:
        fn = getattr(runner, "enforcement_backend", None)
        if fn is None:
            return True
        checks = getattr(catalog, "checks", None) or {}
        for n in check_names:
            c = checks.get(n)
            net = getattr(c, "network", "deny") if c is not None else "deny"
            if fn(net) is not None:
                return True
        return False
    except Exception:
        return True


# ── Phase 8 Chunk C — check-inputs orchestration (§2.2) ───────────────────────
# Thin wrappers over evidence_runner's git-mechanics so a minimal injected runner
# (test double) degrades gracefully instead of raising: a runner without the
# builder returns "no inputs", and a check declaring inputs then refuses cleanly.

def _collect_inputs(runner: Any, catalog: Any, check_names: list) -> set:
    fn = getattr(runner, "collect_declared_inputs", None) or getattr(
        _er, "collect_declared_inputs", None)
    try:
        return fn(catalog, check_names) if fn else set()
    except Exception:
        return set()


def _batch_all_changed_scope(runner: Any, catalog: Any, check_names: list) -> bool:
    fn = getattr(runner, "batch_all_changed_scope", None) or getattr(
        _er, "batch_all_changed_scope", None)
    try:
        return bool(fn(catalog, check_names)) if fn else False
    except Exception:
        return False


def _changed_files(runner: Any, repo_root: str, base_sha: str,
                   delta_commit: str | None) -> list:
    fn = getattr(runner, "changed_files_at", None) or getattr(
        _er, "changed_files_at", None)
    try:
        return fn(repo_root, base_sha, delta_commit) if fn else []
    except Exception:
        return []


def _build_inputs(runner: Any, repo_root: str, needed: set, base_sha: str,
                  delta_commit: str | None, changed: list | None,
                  cr: CaptureResult | None = None) -> str | None:
    """Build the read-only inputs dir; returns its path (or None on any failure —
    the checks then refuse cleanly rather than run against a missing input). The
    inputs each check actually consumed are recorded on its own evidence_check
    event (``inputs: [...]``), the observed-not-narrated record that matters."""
    mk = getattr(runner, "make_inputs_dir", None) or getattr(
        _er, "make_inputs_dir", None)
    build = getattr(runner, "build_check_inputs", None) or getattr(
        _er, "build_check_inputs", None)
    if not (mk and build):
        return None
    try:
        d = mk()
        build(repo_root, d, needed, base_sha, delta_commit, changed=changed)
        return d
    except Exception as e:
        _mark_failure(e, "execution_loop_build_inputs")
        return None


def _cleanup_inputs(inputs_dir: str | None) -> None:
    if not inputs_dir:
        return
    try:
        import shutil as _sh
        _sh.rmtree(inputs_dir, ignore_errors=True)
    except Exception:
        pass


def run_isolated_checks(runner: Any, catalog: Any, check_names: list,
                        repo_root: str, base_sha: str,
                        cr: CaptureResult) -> list | None:
    """The Phase-8 isolated-check actuator (§3.1): ref-less temp commit of the
    CURRENT tree parented at the pre-exec base (captures untracked files —
    higher fidelity than applying the delta_ref patch, which omits them) →
    ``git worktree add --detach`` under scratch → run the named checks there
    with ``mode="clean_worktree"`` (the only mode the runner permits mutating
    checks under; the sandbox grants write ONLY inside that worktree) →
    remove + prune, finally-guaranteed. The user's HEAD/index/tree are never
    touched. Returns the CheckResults, or None on ANY lifecycle failure (the
    caller falls back to the honest deferred marker — the actuator never
    turns a working degrade path into a crash)."""
    wt = None
    try:
        # An injected runner without the Chunk-B lifecycle (test doubles,
        # stripped deployments) falls back cleanly — never an AttributeError
        # dressed up as a lifecycle failure (pre-check regression-lens fold).
        if not all(hasattr(runner, a) for a in
                   ("prune_orphan_worktrees", "tree_commit_at",
                    "create_isolated_worktree", "remove_isolated_worktree")):
            cr.isolated = {"ran": False,
                           "fallback_reason": "runner lacks worktree lifecycle support"}
            return None
        # Crash-residue sweep FIRST, UNCONDITIONALLY — ⚖ fold-recheck (real
        # minor): this must run BEFORE the no-backend gate below. The sweep is
        # backend-INDEPENDENT (needs only repo_root + the lifecycle methods,
        # both confirmed present by the hasattr guard above) and is the sole
        # mechanism that unpins a PRIOR crashed run's ref-less snapshot from
        # its owner repo's object store. Gating it behind an enforcing backend
        # silently narrowed that load-bearing crash-residue guarantee on
        # all-no-enforcing-policy turns.
        runner.prune_orphan_worktrees(repo_root)
        # ⚖ Code-review fold (judge P2): if NO enforcing backend exists for
        # these checks' network policy on this platform, the runner would
        # REFUSE every one unrun (§7 enforce-or-refuse) — so DEFER honestly
        # WITHOUT building a pointless worktree that would then stamp a
        # misleading isolated.ran=True. This is the "defer honestly where no
        # enforcing backend exists" behavior (the common no-backend Windows
        # case). Fails toward attempting on a predicate error (the runner
        # still refuses safely).
        if not _batch_has_enforcing_backend(runner, catalog, check_names):
            cr.isolated = {"ran": False, "fallback_reason": (
                "no enforcing backend for the checks' network policy on this "
                "platform — refused, not run unenforced (§7)")}
            return None
        delta_commit = runner.tree_commit_at(repo_root, base_sha)
        if not delta_commit:
            cr.isolated = {"ran": False, "fallback_reason": "temp-commit failed"}
            return None
        # Phase 8 Chunk C (§2.2): sparse opt-in + harness-built check INPUTS.
        # Only when EVERY check in the batch is scope:changed_files may the
        # worktree be sparse (a scope:repo check in a sparse tree would silently
        # miss files). The changed-file list is computed ONCE (from the delta
        # commit) and reused for both the sparse set and changed-files.txt.
        needed = _collect_inputs(runner, catalog, check_names)
        sparse = None
        changed = None
        if _batch_all_changed_scope(runner, catalog, check_names):
            changed = _changed_files(runner, repo_root, base_sha, delta_commit)
            # sparse = the changed paths ∪ .ora (so the check scripts + catalog
            # materialize in the worktree). Empty changed → just .ora.
            sparse = list(dict.fromkeys((changed or []) + [".ora"]))
        wt = (runner.create_isolated_worktree(repo_root, delta_commit, sparse=sparse)
              if sparse is not None
              else runner.create_isolated_worktree(repo_root, delta_commit))
        if not wt:
            cr.isolated = {"ran": False, "delta_commit": delta_commit,
                           "fallback_reason": "worktree add failed/refused"}
            return None
        inputs_dir = _build_inputs(runner, repo_root, needed, base_sha,
                                   delta_commit, changed, cr) if needed else None
        # Pass inputs_dir ONLY when built (byte-identical to the pre-Chunk-C call
        # for a no-declared-inputs batch — preserves the Chunk-B test doubles).
        kw = {"worktree": wt, "mode": "clean_worktree"}
        if inputs_dir is not None:
            kw["inputs_dir"] = inputs_dir
        try:
            results = runner.run_contract(
                catalog, {"required_standard_checks": list(check_names)},
                repo_root, **kw)
        finally:
            _cleanup_inputs(inputs_dir)
        # Belt (judge P2): isolated.ran=True must mean a check GENUINELY RAN,
        # not merely that the lifecycle completed. If every result came back
        # skipped/refused (a mixed-policy batch the up-front gate could not
        # rule out, or an unexpected in-runner refusal), record the honest
        # fallback and let the caller defer — never a false isolated run.
        genuinely_ran = [r for r in (results or [])
                         if not getattr(r, "skipped", False)]
        if not genuinely_ran:
            cr.isolated = {"ran": False, "delta_commit": delta_commit,
                           "fallback_reason": (
                               "every isolated check was refused/skipped by "
                               "the runner (no genuine execution)")}
            return None
        cr.isolated = {"ran": True, "delta_commit": delta_commit,
                       "checks": list(check_names),
                       "checks_ran": len(genuinely_ran)}
        return results
    except Exception as e:
        _mark_failure(e, "execution_loop_isolated_checks")
        cr.isolated = {"ran": False,
                       "fallback_reason": f"lifecycle error: {str(e)[:160]}"}
        return None
    finally:
        if wt:
            removed = runner.remove_isolated_worktree(repo_root, wt)
            if isinstance(cr.isolated, dict):
                cr.isolated["worktree_removed"] = bool(removed)
            if not removed:
                _mark_failure(RuntimeError(
                    f"disposable worktree not fully removed: {wt}"),
                    "execution_loop_worktree_residue")


def run_capture(packet: Any, *, context_pkg: dict | None = None,
                trace_dir: str | None = None, runner: Any = None,
                repo_root: str | None = None) -> CaptureResult:
    """Drive the Phase-5 runner AFTER the actuator, over whatever the turn actually
    mutated, using the STASHED pre-execution base (never a terminal-time read). Runs
    ONLY non-mutating catalog checks live (mutating ones are recorded DEFERRED to
    Phase 8, ⚖ Rev-2). Fills the packet's ``diff_validate`` lane. Never raises —
    returns a CaptureResult describing what happened (including honest owed states)."""
    runner = runner or _er
    ctx = context_pkg or {}
    mode = _capture_mode(ctx)
    before = ctx.get("exec_review_state_before")
    cr = CaptureResult(mode=mode, state_before=before)
    # No true pre-execution base (the planning-stage snapshot did not fire, or had no
    # HEAD) → the diff+validate lane is BASE-UNKNOWN: the before/after delta cannot be
    # trusted, so the lane stays OWED and is NEVER marked sufficient — even if the
    # checks pass on the current tree (design P1: never a false state_before /
    # sufficiency). [judge P1 fold]
    cr.base_unknown = not (isinstance(before, dict) and before.get("head"))
    try:
        rr = repo_root or ctx.get("repo_root") or discover_repo_root(ctx, runner=runner)
        cr.repo_root = rr
        if not rr:
            # No discoverable repo → no diff+validate checks to run; the lane stays
            # owed (not sufficient). Degrade to text review, never escalate (P4).
            cr.no_repo = True
            return cr

        catalog = None
        try:
            cat_path = runner.discover_catalog(rr)
            if cat_path:
                catalog = runner.parse_catalog(cat_path)
        except Exception as e:
            _mark_failure(e, "execution_loop_capture_parse")
            catalog = None

        contract = ctx.get("evidence_contract")
        required = _required_check_names(contract, catalog) if catalog else []
        if not required:
            # repo-less / no-catalog / no declared checks → owed lane, degrade
            # (never a false "sufficient", never escalate-churn — ⚖ Rev-1 OQ6).
            cr.no_checks = True

        # Split mutating from non-mutating checks. Phase 8 Chunk B: mutating
        # checks RUN in the isolated actuator (disposable worktree at the
        # turn's delta) instead of being recorded deferred — the deferred
        # marker survives only as the honest FALLBACK (kill-switch off /
        # base-unknown / lifecycle failure). SEC-2 repos (the vault class:
        # in-place checks refused by the sandbox pre-flight) route ALL their
        # checks through the worktree — without that they were structurally
        # unrunnable (⚖ Rev 3). A caller-DECLARED clean_worktree checkout
        # (§3.4) runs everything in place — the tree is already isolated.
        results: list = []
        runnable: list = []
        mutating: list = []
        for name in required:
            chk = (getattr(catalog, "checks", None) or {}).get(name)
            if chk is not None and getattr(chk, "mutates", False):
                mutating.append(name)
            else:
                runnable.append(name)

        actuator_on = mutating_actuator_enabled()
        iso_all = (mode != "clean_worktree"
                   and requires_isolated_worktree(rr, runner))
        before_head = (before or {}).get("head") if isinstance(before, dict) else None

        def _defer_all(names: list, why: str) -> None:
            for n in names:
                chk_n = (getattr(catalog, "checks", None) or {}).get(n)
                cr.deferred_mutating.append(n)
                results.append(_record_deferred_mutating(
                    n, runner, reason=why,
                    mutates=bool(getattr(chk_n, "mutates", False))))

        def _run_in_place(names: list) -> list:
            """Run a batch of checks IN PLACE, building any declared inputs from the
            CURRENT tree (in-place derivation: changed = diff base + untracked;
            title universe = current tracked+untracked — §2.2). No pre-exec base
            (base_unknown) → no inputs dir → a declared-inputs check refuses
            cleanly, never runs against a missing input."""
            needed = _collect_inputs(runner, catalog, names)
            inputs_dir = None
            if needed and before_head:
                inputs_dir = _build_inputs(runner, rr, needed, before_head,
                                           None, None, cr)
            # Pass inputs_dir ONLY when built — a batch with no declared inputs is
            # byte-identical to the pre-Chunk-C call (no new kwarg).
            kw = {"mode": mode}
            if inputs_dir is not None:
                kw["inputs_dir"] = inputs_dir
            try:
                return runner.run_contract(
                    catalog, {"required_standard_checks": names}, rr, **kw)
            finally:
                _cleanup_inputs(inputs_dir)

        if mode == "clean_worktree":
            # Caller-attested isolated checkout: the runner permits mutating
            # checks in place; no actuator worktree needed.
            if required and catalog is not None:
                results.extend(_run_in_place(required))
        elif iso_all and required and catalog is not None:
            # SEC-2 repo: EVERY check must run isolated (in-place would be
            # refused check-by-check). Requires the actuator + a real base.
            if not actuator_on:
                _defer_all(required,
                           "checks deferred — SEC-2 repo requires the isolated "
                           "worktree and ORA_EXEC_REVIEW_MUTATING is off")
            elif cr.base_unknown or not before_head:
                _defer_all(required,
                           "checks deferred — SEC-2 repo requires the isolated "
                           "worktree and no pre-execution base was stashed "
                           "(base-unknown)")
            else:
                iso = run_isolated_checks(runner, catalog, required, rr,
                                          before_head, cr)
                if iso is not None:
                    results.extend(iso)
                else:
                    _defer_all(required,
                               "checks deferred — isolated run did not execute ("
                               + str((cr.isolated or {}).get(
                                   "fallback_reason", "unknown")) + ")")
        else:
            # Normal repo: non-mutating checks run in place (unchanged);
            # mutating checks run in the isolated worktree.
            if mutating and catalog is not None:
                if not actuator_on:
                    _defer_all(mutating,
                               "mutating check deferred — "
                               "ORA_EXEC_REVIEW_MUTATING is off; never run "
                               "against the live checkout")
                elif cr.base_unknown or not before_head:
                    _defer_all(mutating,
                               "mutating check deferred — no pre-execution "
                               "base was stashed (base-unknown); the isolated "
                               "worktree needs the pre-exec base as parent")
                else:
                    iso = run_isolated_checks(runner, catalog, mutating, rr,
                                              before_head, cr)
                    if iso is not None:
                        results.extend(iso)
                    else:
                        _defer_all(mutating,
                                   "mutating check deferred — isolated run did "
                                   "not execute ("
                                   + str((cr.isolated or {}).get(
                                       "fallback_reason", "unknown")) + ")")
            if runnable and catalog is not None:
                results.extend(_run_in_place(runnable))
        cr.results = results

        # state_after + a delta REFERENCE (diff written trace-local, never inlined).
        try:
            after, delta_ref = runner.snapshot_after(rr, mode, trace_dir, before)
            cr.state_after = after
            cr.delta_ref = delta_ref
        except Exception as e:
            _mark_failure(e, "execution_loop_capture_after")

        # Fill the packet's diff_validate lane + judge sufficiency against the FULL
        # required set — the ORIGINAL contract (standard+) OR every catalog check
        # (light). It must include the DEFERRED mutating checks: a deferred required
        # check is skipped → contract_sufficient counts it NOT sufficient → honest
        # degrade, never a false "sufficient" (⚖ Rev-2 P1; §16-2 absence ≠ pass). Using
        # `runnable` here would silently drop the deferred mutating check at light tier
        # and falsely converge — precisely the tier ⚖ Rev-2 P2 brought into scope.
        fill_contract = contract or {"required_standard_checks": required}
        try:
            runner.fill_evidence_lanes(packet, results, fill_contract, cr.delta_ref)
            cr.sufficient = runner.contract_sufficient(results, fill_contract)
        except Exception as e:
            _mark_failure(e, "execution_loop_capture_fill")

        # Base-unknown → the diff+validate lane is fully OWED: without a pre-execution
        # base a check outcome is not attributable to this turn, so (Rev-2) both the
        # SUFFICIENCY and the FAILURE signals are suppressed — ``ran_and_failed()``
        # already returns False when ``base_unknown`` (so a failed check does NOT drive
        # escalation), and here a passing-but-base-less run has its false SUFFICIENCY
        # forced to owed. Either way the lane reads owed and the turn degrades, never a
        # false sufficiency and never a branchless escalation (judge Rev-1/Rev-2 fold).
        if cr.base_unknown and cr.sufficient:
            cr.sufficient = False
            for lane in (getattr(packet, "evidence_lanes", None) or []):
                if getattr(lane, "lane", None) == "diff_validate":
                    lane.sufficient = None   # owed (not sufficient)
            _mark_failure(RuntimeError(
                "diff+validate base unknown — no pre-execution snapshot; lane owed, "
                "not sufficient"), "execution_loop_base_unknown")

        # Honest enforcement_model: the strongest backend that actually RAN a check
        # (orchestrated / declared-sandbox), else in_harness (no orchestrated capture).
        for r in results:
            enf = getattr(r, "enforcement_model", None)
            if enf and enf != "in_harness" and not getattr(r, "skipped", False):
                cr.enforcement_model = enf
                break
        return cr
    except Exception as e:
        _mark_failure(e, "execution_loop_capture")
        return cr


# ── Verify (§12) — dual DIFFERENT-family; single-family graceful degrade ───────
def executor_family(config: dict | None, config_name: str | None,
                    router_obj: Any = None) -> str | None:
    """The executor's training family = the resolved analyst/``depth`` endpoint's
    ``training_family``. None/unknown → the caller degrades to single-family (an
    unconfirmed difference is never presented as cross-family assurance, §12)."""
    try:
        if router_obj is None:
            try:
                import boot as _boot
            except ImportError:  # pragma: no cover
                from orchestrator import boot as _boot
            ep = _boot.get_slot_endpoint(config or {}, "depth", config_name=config_name)
        else:
            ep = router_obj.resolve_endpoint("depth", 4, "interactive", config_name=config_name)
            if ep is None:
                ep = router_obj.resolve_endpoint("depth", 3, "interactive", config_name=config_name)
            ep = router_obj._to_v1_endpoint(ep) if ep else None
        fam = (ep or {}).get("training_family") if isinstance(ep, dict) else None
        return (fam or None)
    except Exception:
        return None


def select_verify_endpoint(*, executor_fam: str | None, config: dict | None = None,
                           config_name: str | None = None, router_obj: Any = None
                           ) -> tuple[dict | None, bool]:
    """Select the verify endpoint. Returns ``(endpoint, same_family)``:
      * a CONFIRMED different-family endpoint → ``(endpoint, False)``;
      * else the default ``verification`` endpoint under the single-family
        graceful-degrade path → ``(endpoint_or_None, True)``.
    NEVER silently substitutes ``breadth`` for the exec-review verify (that fallback
    would defeat the different-family requirement, §12). Never raises."""
    try:
        router_obj = router_obj or _get_router()
        if router_obj is not None:
            diff = router_obj.resolve_different_family(
                "verification", executor_fam, config_name=config_name)
            if diff:
                return diff, False
            # No cross-family endpoint → single-family degrade over the default slot.
            same = router_obj.resolve_post_analysis_slot("verification", config_name=config_name)
            same_v1 = router_obj._to_v1_endpoint(same) if same else None
            return same_v1, True
    except Exception as e:
        _mark_failure(e, "execution_loop_select_verify")
    return None, True


def _get_router():
    try:
        try:
            import boot as _boot
        except ImportError:  # pragma: no cover
            from orchestrator import boot as _boot
        return _boot._get_router()
    except Exception:
        return None


_VERIFY_SYSTEM = (
    "You are the EXECUTION-REVIEW verifier (spec §12). You are reviewing a rendered "
    "packet whose MECHANICAL EVIDENCE is presented FIRST and whose PRODUCER CLAIM is "
    "LAST and explicitly UNVERIFIED — weigh the evidence, never let a fluent claim "
    "out-argue a failing or absent check. Judge whether the evidence lanes are "
    "SUFFICIENT against the declared acceptance criteria + evidence contract. Emit "
    "EXACTLY this structure and nothing else:\n"
    "VERDICT: PASS | FAIL\n"
    "CONFIDENCE: <0.0-1.0>\n"
    "FINDING: severity=<high|medium|low>; class=<plan_level|execution_level>; <one-line description>\n"
    "  (repeat FINDING per issue; a PLAN_LEVEL finding = the acceptance criteria / "
    "contract themselves are wrong; an EXECUTION_LEVEL finding = the implementation "
    "does not meet a correct criterion)\n"
    "INVENTED_TEST: kind=<acceptance|regression|diagnostic|exploratory>; <name>\n"
    "  (only an ACCEPTANCE-kind invented test obligates the executor)\n"
)
_SINGLE_FAMILY_ADDENDUM = (
    "\n\nNOTE: no different-family verifier is available, so you share the executor's "
    "training lineage. Compensate by being MAXIMALLY ADVERSARIAL in a distinct "
    "skeptic's role — actively hunt the failure modes an aligned reviewer would wave "
    "through. Your review carries LOWERED confidence and does not substitute for "
    "cross-family assurance."
)


def parse_verify_output(text: str | None) -> dict:
    """Parse the verifier's structured output into
    ``{verdict, confidence, findings[], invented_tests[]}``. Line-anchored + tolerant
    (case-insensitive keys, missing fields default safely). Never raises."""
    out: dict = {"verdict": None, "confidence": None, "findings": [], "invented_tests": []}
    try:
        for raw in (text or "").splitlines():
            line = raw.strip()
            low = line.lower()
            if low.startswith("verdict:"):
                v = line.split(":", 1)[1].strip().upper()
                out["verdict"] = ("PASS" if v.startswith("PASS")
                                  else "FAIL" if v.startswith("FAIL")
                                  else (v or None))
            elif low.startswith("confidence:"):
                try:
                    out["confidence"] = float(line.split(":", 1)[1].strip().split()[0])
                except Exception:
                    pass
            elif low.startswith("finding:"):
                out["findings"].append(_parse_finding(line.split(":", 1)[1]))
            elif low.startswith("invented_test:") or low.startswith("invented test:"):
                out["invented_tests"].append(_parse_invented(line.split(":", 1)[1]))
    except Exception as e:
        _mark_failure(e, "execution_loop_parse_verify")
    return out


def _kv(body: str) -> tuple[dict, str]:
    """Split a ``k=v; k=v; free text`` body into (kv-dict, trailing free text)."""
    kv: dict = {}
    rest_parts: list[str] = []
    for seg in body.split(";"):
        seg = seg.strip()
        if "=" in seg and " " not in seg.split("=", 1)[0].strip():
            k, v = seg.split("=", 1)
            kv[k.strip().lower()] = v.strip()
        elif seg:
            rest_parts.append(seg)
    return kv, "; ".join(rest_parts).strip()


def _parse_finding(body: str) -> dict:
    kv, rest = _kv(body)
    sev = (kv.get("severity") or "medium").strip().lower()
    cls = (kv.get("class") or "execution_level").strip().lower()
    if cls not in ("plan_level", "execution_level"):
        cls = "execution_level"
    return {"severity": sev, "class": cls, "description": rest or body.strip()}


def _parse_invented(body: str) -> dict:
    kv, rest = _kv(body)
    kind = (kv.get("kind") or "diagnostic").strip().lower()
    if kind not in ("acceptance", "regression", "diagnostic", "exploratory"):
        kind = "diagnostic"
    return {"kind": kind, "name": rest or body.strip()}


def run_verify(review_text: str, *, verify_invoker: Callable | None,
               endpoint: dict | None = None, same_family: bool = False,
               risk_tier: str | None = None) -> dict:
    """Run the §3 execution-review verify over ``render_for_review`` output. The
    ``verify_invoker(system, user, endpoint) -> str`` callback isolates the model call
    over the SELECTED verify endpoint (injected for tests). On the single-family path,
    lower the recorded confidence and stamp a ``fallback_reason`` (§12). Returns a
    structured verify record; never raises."""
    rec: dict = {"reviewer": _endpoint_ref(endpoint), "same_family": bool(same_family),
                 "verdict": None, "confidence": None, "findings": [], "invented_tests": [],
                 "fallback_reason": None, "escalate_human": False, "ran": False}
    if verify_invoker is None:
        rec["fallback_reason"] = "no verify invoker available"
        _mark_unverified(rec, risk_tier)
        return rec
    try:
        system = _VERIFY_SYSTEM + (_SINGLE_FAMILY_ADDENDUM if same_family else "")
        raw = verify_invoker(system, review_text, endpoint)
        actual_endpoint = getattr(raw, "endpoint", None)
        if isinstance(actual_endpoint, dict) and actual_endpoint:
            rec["reviewer"] = _endpoint_ref(actual_endpoint)
        parsed = parse_verify_output(raw or "")
        conf = parsed["confidence"]
        if same_family:
            base = conf if conf is not None else _DEFAULT_CONFIDENCE
            conf = max(0.0, round(base - SINGLE_FAMILY_CONFIDENCE_PENALTY, 4))
            rec["fallback_reason"] = "single-family verify — no cross-family endpoint available"
            # For high-risk / irreversible, single-family review must ESCALATE to a
            # human rather than pass as cross-family assurance (§12).
            if _tier_at_least(risk_tier, "high-risk"):
                rec["escalate_human"] = True
        rec.update(verdict=parsed["verdict"], confidence=conf,
                   findings=parsed["findings"], invented_tests=parsed["invented_tests"])
        # The §3 Verify RAN only if it produced a usable result — a recognizable
        # VERDICT (PASS/FAIL) or at least one finding. An empty / unparseable / broken
        # response (a missing endpoint, a failed call, garbage with no VERDICT line)
        # gives NO assurance and must NOT be allowed to converge as criteria_met — that
        # would be "grading your own homework" with no reviewer (judge P1 fold).
        rec["ran"] = (rec["verdict"] in ("PASS", "FAIL")) or bool(rec["findings"])
        if not rec["ran"]:
            _mark_unverified(rec, risk_tier)
        return rec
    except Exception as e:
        _mark_failure(e, "execution_loop_run_verify")
        _mark_unverified(rec, risk_tier)
        return rec


def _mark_unverified(rec: dict, risk_tier: str | None) -> None:
    """The §3 verify could not produce a usable verdict (no invoker / empty / broken).
    Record it, lower confidence, and — for high-risk/irreversible — escalate to a human
    (shipping high-risk work with NO verification is worse than degrading)."""
    rec["ran"] = False
    rec["confidence"] = 0.0
    rec["fallback_reason"] = rec.get("fallback_reason") or "verify produced no usable verdict (empty/broken)"
    if _tier_at_least(risk_tier, "high-risk"):
        rec["escalate_human"] = True


def _endpoint_ref(ep: dict | None) -> dict | None:
    if not isinstance(ep, dict):
        return None
    return {"endpoint": ep.get("id") or ep.get("name"),
            "family": ep.get("training_family")}


def _tier_at_least(tier: str | None, floor: str) -> bool:
    try:
        try:
            import risk_gate as _rg
        except ImportError:  # pragma: no cover
            from orchestrator import risk_gate as _rg
        return _rg.tier_at_least(tier or "standard", floor)
    except Exception:
        # Conservative: treat an unknown tier as at-least-high-risk for the escalate
        # decision only if the floor is high-risk (fail toward more human oversight).
        return floor in ("high-risk", "irreversible")


# ── Revision router (§12) — plan-level vs execution-level fork ─────────────────
def route_findings(findings: list) -> tuple[list, list]:
    """Fork findings by their reviewer-assigned ``class`` (no separate classification
    pass — §12): execution-level → back to the executor; plan-level → back to the
    planners (else you 'converge on a better implementation of a wrong plan')."""
    execution_level, plan_level = [], []
    for f in findings or []:
        if (f or {}).get("class") == "plan_level":
            plan_level.append(f)
        else:
            execution_level.append(f)
    return execution_level, plan_level


def has_high_severity(findings: list) -> bool:
    """True if ANY finding of ANY class is high-severity-or-worse (⚖ Rev-1 judge P1:
    spec §364 'no high-severity finding remains' — NOT narrowed to execution_level,
    else a high-severity plan-level wrong-problem finding could coexist with
    criteria_met). Matches high AND critical/blocker/severe/major/fatal (a verifier
    that emits 'critical' must not slip past the stop rule)."""
    return any(str((f or {}).get("severity", "")).strip().lower() in _BLOCKING_SEVERITIES
               for f in (findings or []))


def obligating_invented_tests(invented_tests: list) -> list:
    """Only ``acceptance``-kind invented tests obligate the executor (§12) — genuine
    missing acceptance criteria. diagnostic / exploratory / preference do not, so the
    executor is not trapped chasing every invented objection."""
    return [t for t in (invented_tests or []) if (t or {}).get("kind") == "acceptance"]


# ── Stop rule (§13) — converge OR escalate, never churn ────────────────────────
def converged(capture: CaptureResult, findings: list, verdict: str | None = None,
              verify_ran: bool = True) -> bool:
    """Converge when the evidence is sufficient AND no high-severity finding of ANY
    class remains (§13/⚖ Rev-1) AND the verify actually RAN AND did not explicitly
    FAIL. Sufficiency is the runner's Contract judgment (empty / owed lanes are NOT
    sufficient — absence ≠ pass, §16-2).

    - An explicit ``VERDICT: FAIL`` from the different-family verifier BLOCKS
      convergence even when the mechanical evidence is sufficient and no finding parsed
      as high-severity (a reviewer-failed deliverable must never be ``criteria_met``).
    - A verify that did NOT run (empty / broken / no invoker — ``verify_ran=False``)
      BLOCKS convergence: with no §3 reviewer, ``criteria_met`` would be
      grading-your-own-homework (judge P1 fold)."""
    if verdict == "FAIL" or not verify_ran:
        return False
    return bool(capture and capture.sufficient) and not has_high_severity(findings)


def escalation_warranted(capture: CaptureResult, findings: list,
                         verdict: str | None = None) -> bool:
    """Escalate ONLY on real negative evidence — a RAN-and-FAILED check, a persistent
    high-severity finding, OR an explicit ``VERDICT: FAIL`` from the different-family
    verifier (a reviewer rejection with nothing left to revise is a genuine unresolved
    failure a human must adjudicate). NEVER on an owed / deferred / empty lane (⚖ Rev-1
    + Rev-2: a source-read owed provenance lane, a repo-less no-catalog contract, a
    deferred mutating check, or a no-sandbox refusal are honest 'can't verify here',
    not test failures — escalating them would churn every such turn, and a human can't
    fix an environment limit mid-loop)."""
    if verdict == "FAIL":
        return True
    if capture and capture.ran_and_failed():
        return True
    return has_high_severity(findings)


# ── Escalation branch (§13) — inspectable, UNMERGED, never discarded ───────────
def _safe_ref(task_id: Any) -> str:
    s = "".join(c if (c.isalnum() or c in "-_") else "-" for c in str(task_id or "task"))
    return s.strip("-") or "task"


def _looks_like_sha(s: Any) -> bool:
    return bool(s) and isinstance(s, str) and 7 <= len(s) <= 64 and all(
        c in "0123456789abcdefABCDEF" for c in s)


def create_escalation_branch(repo_root: str | None, base_sha: str | None,
                             task_id: Any, *, trace_dir: str | None = None,
                             git: Callable | None = None) -> str | None:
    """Create + KEEP an inspectable, UNMERGED branch (§13) at the STASHED
    pre-execution ``base_sha`` (⚖ Rev-1 P0 — never a terminal-time HEAD), holding the
    abandoned attempt. The working-tree delta is committed onto the branch via a
    THROWAWAY index (``GIT_INDEX_FILE``) + ``commit-tree`` — the user's real index and
    HEAD are left EXACTLY as the executor left them (Phase 6 never resets/rewrites the
    user's working branch to manufacture an unmerged branch, ⚖ Rev-1 P4). The branch
    is unmerged by construction (it diverges from the base the user is on). Respects
    ``.gitignore`` (``add -A`` skips ignored/secret files). Returns the branch ref or
    None. Never raises."""
    git = git or _er._git
    if not (repo_root and _looks_like_sha(base_sha)):
        return None
    try:
        # The branch name carries a PER-TURN discriminator (the trace dir basename,
        # unique per run) IN ADDITION to the conversation-stable task_id. Without it
        # a SECOND escalation in the same conversation reused the same name and the
        # `branch -f` below force-overwrote the FIRST abandoned attempt — silently
        # discarding it and mis-linking its handback (§13: the abandoned work is
        # never silently discarded). Falls back to task_id-only when no trace_dir.
        disc = _safe_ref(os.path.basename(str(trace_dir).rstrip("/\\"))) if trace_dir else ""
        branch = _ESCALATION_BRANCH_PREFIX + _safe_ref(task_id)
        if disc and disc != "task":
            branch += "-" + disc
        # 1. Create/point the branch at the pre-execution base — does NOT touch the
        #    working tree, the index, or HEAD (a ref write only).
        rc, _ = git(repo_root, ["branch", "-f", branch, base_sha])
        if rc != 0:
            return None
        # 2. Snapshot the CURRENT working tree (the abandoned attempt) onto the branch
        #    via a throwaway index so the user's .git/index + HEAD are untouched.
        import tempfile
        fd, idx_path = tempfile.mkstemp(prefix="er-escal-idx-")
        os.close(fd)
        try:
            os.unlink(idx_path)   # git wants to create the index fresh
        except OSError:
            pass
        env = dict(os.environ)
        env["GIT_INDEX_FILE"] = idx_path
        try:
            git(repo_root, ["read-tree", base_sha], env=env)
            git(repo_root, ["add", "-A"], env=env)
            rc_wt, tree = git(repo_root, ["write-tree"], env=env)
            if rc_wt == 0 and _looks_like_sha(tree):
                rc_c, commit = git(
                    repo_root,
                    ["commit-tree", tree, "-p", base_sha, "-m",
                     f"execution-review: abandoned attempt (escalated) — task {task_id}"],
                    env=env)
                if rc_c == 0 and _looks_like_sha(commit):
                    git(repo_root, ["update-ref", f"refs/heads/{branch}", commit])
        finally:
            try:
                os.unlink(idx_path)
            except OSError:
                pass
        return branch
    except Exception as e:
        _mark_failure(e, "execution_loop_escalation_branch")
        return None


# ── Handback (§7/§13) — a REFERENCE to the durable queue, never inlined content ─
def _level2_invoker(config, config_name, router_obj, verify_invoker):
    """Phase 8: build the Level-2 mapper invoker when ``ORA_PROVENANCE_CLAIM_MAP``
    is on — different-family endpoint via the landed §12 selector (a same-family
    mapper is recorded as lowered assurance on the lane, never presented as
    cross-family). Returns ``(invoker|None, family_note|None)``. Never raises."""
    try:
        if not _eprov.level2_enabled() or verify_invoker is None:
            return None, None
        exec_fam = executor_family(config, config_name, router_obj)
        ep, same_family = select_verify_endpoint(
            executor_fam=exec_fam, config=config, config_name=config_name,
            router_obj=router_obj)
        if ep is None:
            return None, None
        note = ("same_family (lowered assurance)" if same_family
                else "different_family")
        return (lambda system, user: verify_invoker(system, user, ep)), note
    except Exception as e:
        _mark_failure(e, "execution_loop_level2_invoker")
        return None, None


def redacted_review_summary(packet: Any) -> str:
    """A REDACTED render_for_review for the durable handback: evidence + verdict, with
    the UNVERIFIED PRODUCER CLAIM fence DROPPED (the claim may be private/sensitive and
    the durable queue is more durable than the trace-local packet — §7), and lane
    RESULT content suppressed (``durable_summary=True`` — Phase 8: provenance
    excerpts must never reach the durable Paused queue through this render; the
    Rev-3 handback-leak blocker fold). Fail-CLOSED: any render failure returns ""
    and the handback ships reference-only. Capped."""
    try:
        text = _ep.render_for_review(packet, durable_summary=True)
    except Exception:
        return ""
    marker = "=== UNVERIFIED PRODUCER CLAIM"
    idx = text.find(marker)
    if idx != -1:
        text = text[:idx].rstrip() + "\n=== PRODUCER CLAIM REDACTED (see trace-local packet) ==="
    return text[:_REDACTED_SUMMARY_CAP]


def handback_reference(*, packet: Any, packet_path: str | None, branch_ref: str | None,
                       reason: str, context_pkg: dict | None = None) -> dict:
    """Build the Paused-queue handback as a REFERENCE (⚖ folded): the trace-local
    packet path + the abandoned-attempt branch ref + the reason + a REDACTED
    render_for_review summary — NOT the inlined ``producer_claim``. Shaped for
    ``oversight_queue.PausedEntry.context_summary``."""
    ctx = context_pkg or {}
    cid = ctx.get("conversation_id", "")
    # Phase 8 (OQ6 rewire): prefer the DURABLE note ref persist_packet stamped
    # on the packet — an escalated turn always earns durable_note, while
    # packet_ref points into data/pipeline-traces/ and dangles after the 30d
    # sweep. Both are carried; packet_ref is labeled ephemeral.
    note_ref = None
    try:
        note_ref = (getattr(packet, "persistence", None) or {}).get("note_ref")
    except Exception:
        note_ref = None
    return {
        "queued_at": _now_iso(),
        # Top-level conversation_id so the conversation_closeout stealth-purge backstop
        # (Layer 9) can scrub this entry if a conversation is later stealth-purged —
        # oversight_queue.add_entry does NOT re-derive it the way _append_human_queue does.
        "conversation_id": cid,
        "event": {"event_type": "ExecutionReviewEscalation",
                  "project_nexus": ctx.get("project_nexus", ""),
                  "conversation_id": cid},
        "verdict": {"decision": "ESCALATE", "reasoning": reason},
        "context_summary": {
            "kind": "execution_review_escalation",
            "note_ref": note_ref,
            "packet_ref": packet_path,
            "packet_ref_note": "ephemeral — trace-local, swept after ~30d",
            "abandoned_attempt_branch": branch_ref,
            "reason": reason,
            "summary": redacted_review_summary(packet),
        },
    }


def push_handback(entry: dict) -> bool:
    """Best-effort push of the handback reference to the durable Paused queue. Never
    raises; returns True on a successful hand-off (or a deliberate stealth skip).

    Defense in depth: ``run_loop`` already gates on non-stealth, but the design relies
    on the handback INHERITING the human-queue's stealth-skip — and the PRIMARY path
    ``oversight_queue.add_entry`` writes straight to the durable JSONL with NO stealth
    guard (only the ``_append_human_queue`` fallback stealth-skips). So check the
    stealth context HERE first, before either backend, so a stealth escalation leaves
    no durable residue regardless of which backend runs."""
    try:
        try:
            from oversight_events import _is_stealth_context as _isc
        except ImportError:  # pragma: no cover
            from orchestrator.oversight_events import _is_stealth_context as _isc
        if _isc():
            return False   # stealth: no durable queue residue
    except Exception:
        pass
    try:
        try:
            from oversight_queue import add_entry as _add
        except ImportError:  # pragma: no cover
            from orchestrator.oversight_queue import add_entry as _add
        _add(entry)
        return True
    except Exception:
        try:
            try:
                from oversight_actions import _append_human_queue as _aq
            except ImportError:  # pragma: no cover
                from orchestrator.oversight_actions import _append_human_queue as _aq
            _aq(entry)
            return True
        except Exception as e:
            _mark_failure(e, "execution_loop_push_handback")
            return False


def _now_iso() -> str:
    return _ep._now_iso()


# ── Phase 8 Chunk C — declared-lane filler registry (§2.3/§4.1) ───────────────
# The two OBSERVED lanes (diff_validate, collect_provenance) are filled by their
# own signal-keyed paths (run_capture / fill_provenance_lane) and are NOT in this
# map. This registry dispatches only the DECLARED lanes. A None entry means "no
# filler shipped in Phase 8" (run_observe) — the lane stays honestly owed.

def _deploy_probe_filler(packet, lane, *, fill_ctx):
    if _efam is None:
        return None
    return _efam.fill_deploy_probe_lane(packet, lane, fill_ctx=fill_ctx)


def _render_inspect_filler(packet, lane, *, fill_ctx):
    if _efam is None:
        return None
    return _efam.fill_render_inspect_lane(packet, lane, fill_ctx=fill_ctx)


LANE_FILLERS = {
    "deploy_probe": _deploy_probe_filler,
    "render_inspect": _render_inspect_filler,
    "run_observe": None,          # DECLARED-ONLY in Phase 8 — no filler shipped
}


def _match_recipe(recipes: dict, lane: str, target: str | None):
    """Find the declared recipe for a (lane, target) pair — the recipe body is the
    §6-protected catalog file, never model output (§16-2)."""
    for r in (recipes or {}).values():
        if getattr(r, "lane", None) == lane and (
                target is None or getattr(r, "target", None) == target):
            return r
    return None


def fill_declared_lanes(packet: Any, *, context_pkg: dict | None = None,
                        capture: Any = None, trace_dir: str | None = None,
                        stealth: bool = False, runner: Any = None) -> None:
    """Fill every DECLARED lane (deploy_probe / render_inspect) that is still owed,
    has a registered filler, AND a matching recipe in the target repo's catalog.
    No filler / no recipe → today's exact owed semantics. Called on BOTH engaged
    branches — mutation (capture set) and source-read-only (capture=None). The
    catalog is re-discovered + re-parsed here (the landed re-parse-per-seam idiom);
    on a live turn ``repo_root`` resolves to ~/ora (§3.0) whose catalog declares no
    recipes, so live turns get no declared-lane fill — reachable only via explicit
    repo_root (programmatic runs / tests). Never raises."""
    runner = runner or _er
    try:
        lanes = getattr(packet, "evidence_lanes", None) or []
        # Any owed declared lane to consider before paying for catalog discovery?
        pending = [l for l in lanes
                   if getattr(l, "sufficient", None) is None
                   and LANE_FILLERS.get(getattr(l, "lane", None)) is not None]
        if not pending:
            return
        rr = (getattr(capture, "repo_root", None)
              or discover_repo_root(context_pkg, runner=runner))
        catalog = None
        if rr:
            try:
                cat_path = runner.discover_catalog(rr)
                if cat_path:
                    catalog = runner.parse_catalog(cat_path)
            except Exception as e:
                _mark_failure(e, "execution_loop_declared_catalog")
                catalog = None
        recipes = getattr(catalog, "recipes", None) or {}
        for lane in pending:
            lname = getattr(lane, "lane", None)
            recipe = _match_recipe(recipes, lname, getattr(lane, "target", None))
            if recipe is None:
                continue          # no recipe → stays owed (unchanged semantics)
            fill_ctx = {"context_pkg": context_pkg, "recipe": recipe,
                        "catalog": catalog, "repo_root": rr, "capture": capture,
                        "trace_dir": trace_dir, "stealth": stealth,
                        "runner": runner}
            filler = LANE_FILLERS.get(lname)
            try:
                filler(packet, lane, fill_ctx=fill_ctx)
            except Exception as e:
                _mark_failure(e, "execution_loop_fill_declared")
    except Exception as e:
        _mark_failure(e, "execution_loop_fill_declared_lanes")


# ── The controller (§3/§4) — assemble the loop from the parts above ────────────
def run_loop(*, packet: Any, context_pkg: dict | None, response: str,
             ro: dict | None = None, signals: dict | None = None,
             risk_tier: str | None = None, trace_dir: str | None = None,
             stealth: bool = False, config: dict | None = None,
             config_name: str | None = None,
             verify_invoker: Callable | None = None,
             actuator: Callable | None = None,
             runner: Any = None, router_obj: Any = None,
             queue_push: Callable | None = None,
             branch_creator: Callable | None = None,
             now_iso: str | None = None) -> str | None:
    """The terminal-anchored controller. Assembles plan → (already-run) execute →
    Capture → dual-family Verify → revision router → stop/escalate over the ALREADY-
    produced ``response`` on a non-self-evidencing turn. Populates the §9 packet
    blocks and writes the packet trace-local. Returns a POSSIBLY-REVISED response (the
    actuator re-invoked the gear) or None when the response is unchanged. NEVER raises
    — every failure degrades to the Phase-4 record behaviour.

    Callbacks are injected for testability: ``verify_invoker(system,user,endpoint)->str``,
    ``actuator(exec_findings, plan_findings, iteration)->str|None`` (re-invokes the
    gear), ``queue_push(entry)->bool`` (durable handback). ``runner``/``router_obj``
    default to the live modules."""
    try:
        if stealth or packet is None:
            return None
        runner = runner or _er
        sig = signals if signals is not None else engage_signals(ro)
        any_mut = bool(sig.get("any_mutation"))
        src_read = bool(sig.get("source_read_suspected"))
        # The FULL folded signals (carries max_sensitivity — the redaction driver, §7). engage_signals
        # returns only the two §6 booleans, so source max_sensitivity from the full ro/signals dict.
        full_signals = (signals if signals is not None else (ro or {}).get("signals")) or {}

        # Thread the planning-stage acceptance criteria + contract into the packet so
        # the renderer shows them (or fires its LOUD absence fence). At light there is
        # no planning block (§9 tier-optional) — leave planning None.
        planning = None
        if risk_tier and risk_tier != "light":
            planning = _ep.planning_block_from_context(context_pkg)
            # Attach it to the packet NOW — BEFORE any render_for_review — so the
            # different-family verifier sees the real acceptance criteria, not the LOUD
            # "NO ACCEPTANCE CRITERIA DECLARED" absence fence. The verifier renders the
            # packet inside the loop below, which runs BEFORE the final
            # populate_loop_fields; without this the criteria were populated too late
            # and every verify judged against a false absence (judge P1 fold).
            packet.planning = planning

        # ── Source-read-ONLY turn: FILL the collect_provenance lane (Phase 8
        # Chunk A) — registry + Level-1 map from content the turn already
        # fetched, flag-gated Level 2 for the extraction+support judgment.
        # Still NO converge/escalate cycle (the landed P1/P4 rule: an
        # insufficient provenance lane records + degrades, never escalates).
        # The owed marker survives ONLY as the honest fallback when the fill
        # itself is unavailable/failed.
        if src_read and not any_mut:
            _l2_inv, _l2_note = _level2_invoker(config, config_name,
                                                router_obj, verify_invoker)
            prov = _eprov.fill_provenance_lane(
                packet, context_pkg=context_pkg, response=response,
                trace_dir=trace_dir, stealth=stealth, mixed_turn=False,
                level2_invoker=_l2_inv, level2_family_note=_l2_note)
            if prov is None:
                note = ("source-read-only — collect_provenance owed "
                        "(lane fill unavailable); not entered into the "
                        "converge/escalate cycle")
                _mark_failure(RuntimeError(
                    "provenance evidence owed — lane fill unavailable"),
                    "execution_loop_owed_provenance")
            else:
                cov = prov.get("coverage") or {}
                note = ("source-read-only — collect_provenance lane FILLED "
                        f"(level2={'ran' if cov.get('level2_ran') else 'off'}, "
                        f"examined={cov.get('claims_examined', 0)}, "
                        f"unsupported={cov.get('claims_unsupported', 0)}); "
                        "not entered into the converge/escalate cycle")
            # Phase 8 Chunk C: fill any DECLARED lanes on this engaged branch too
            # (deploy_probe / render_inspect) — capture=None here (this branch runs
            # no diff capture). Record + render only; never a convergence input.
            fill_declared_lanes(packet, context_pkg=context_pkg, capture=None,
                                trace_dir=trace_dir, stealth=stealth, runner=runner)
            _ep.populate_loop_fields(
                packet, planning=planning,
                loop={"iteration": 0, "stop_condition": None, "note": note},
                now_iso=now_iso)
            # Phase 7: set the §14 tier BEFORE write_packet (Phase 8: a filled
            # lane with unsupported claims may now earn ledger_line — OQ-3).
            _epersist.persist_packet(packet, sig=full_signals, context_pkg=context_pkg,
                                     trace_dir=trace_dir, stealth=stealth, now_iso=now_iso)
            _ep.write_packet(packet, trace_dir)
            return None

        if not any_mut:
            return None   # defensive — the caller gates on should_engage

        # ── Mutation turn: the full converge/escalate loop over diff_validate. ──
        exec_fam = executor_family(config, config_name, router_obj)
        verify_ep, same_family = select_verify_endpoint(
            executor_fam=exec_fam, config=config, config_name=config_name,
            router_obj=router_obj)

        current_response = response
        iteration = 0
        loop_state: dict = {"iteration": 0, "stop_condition": None}
        verify_rec: dict = {}
        capture = run_capture(packet, context_pkg=context_pkg, trace_dir=trace_dir,
                              runner=runner)

        # Phase 8: MIXED mutation+source-read turns get the provenance fill the
        # owed branch never gave them (scout-confirmed gap). The lane renders
        # under an INFORMATIONAL header and is NOT a convergence input —
        # converged() still reads only capture.sufficient + findings (OQ-4
        # deferral, judge-approved). Filled once over the ORIGINAL response;
        # actuator revisions do not re-map in this phase (recorded limitation).
        if src_read:
            _l2_inv, _l2_note = _level2_invoker(config, config_name,
                                                router_obj, verify_invoker)
            _eprov.fill_provenance_lane(
                packet, context_pkg=context_pkg, response=response,
                trace_dir=trace_dir, stealth=stealth, mixed_turn=True,
                level2_invoker=_l2_inv, level2_family_note=_l2_note)

        # Phase 8 Chunk C: fill any DECLARED lanes (deploy_probe / render_inspect)
        # on the mutation branch too — informational, never a convergence input
        # (converged() reads only capture.sufficient + findings).
        fill_declared_lanes(packet, context_pkg=context_pkg, capture=capture,
                            trace_dir=trace_dir, stealth=stealth, runner=runner)

        while True:
            review_text = _ep.render_for_review(packet)
            verify_rec = run_verify(review_text, verify_invoker=verify_invoker,
                                    endpoint=verify_ep, same_family=same_family,
                                    risk_tier=risk_tier)
            findings = verify_rec.get("findings") or []
            verdict = verify_rec.get("verdict")
            verify_ran = bool(verify_rec.get("ran"))
            loop_state["iteration"] = iteration

            # Converge? (sufficient + no high-severity finding of any class + the verify
            # actually RAN + did not explicitly FAIL).
            if (converged(capture, findings, verdict, verify_ran)
                    and not verify_rec.get("escalate_human")):
                loop_state["stop_condition"] = "criteria_met"
                break

            # Decide escalate-vs-degrade when we are out of revisions — the cap is
            # reached, no actuator is wired, single-family high-risk forces a human,
            # OR the remaining insufficiency is structurally UNFIXABLE by a revision
            # (no finding to route and no ran-and-failed check — a purely owed/deferred
            # lane). Re-invoking the gear on an owed lane is futile churn (P4).
            exec_findings, plan_findings = route_findings(findings)
            actionable = bool(exec_findings or plan_findings) or (capture and capture.ran_and_failed())
            if (iteration >= MAX_LOOP_ITERATIONS or actuator is None
                    or verify_rec.get("escalate_human") or not actionable):
                if escalation_warranted(capture, findings, verdict) or verify_rec.get("escalate_human"):
                    loop_state["stop_condition"] = "max_iterations_escalated"
                else:
                    # Owed/deferred/empty lanes only (or a verify that could not run on
                    # a non-high-risk turn) → degrade to the text review, loudly marked,
                    # WITHOUT escalating (P4).
                    loop_state["stop_condition"] = None
                    loop_state["note"] = (
                        "degraded to text review — the different-family verify could not "
                        "produce a usable verdict (unverified)"
                        if not verify_ran else
                        "degraded to text review — evidence owed/deferred (no "
                        "ran-and-failed check, no persistent high-severity finding, "
                        "verifier did not fail)")
                break

            # Revise — fork the findings, re-invoke the gear as the actuator.
            iteration += 1
            try:
                new_resp = actuator(exec_findings, plan_findings, iteration)
            except Exception as e:
                _mark_failure(e, "execution_loop_actuator")
                new_resp = None
            if new_resp:
                current_response = new_resp
                # Update the packet's producer claim to the revised deliverable so the
                # next render reviews the current attempt.
                try:
                    ex = dict(packet.execution or {})
                    pc = dict(ex.get("producer_claim") or {})
                    pc["summary"] = str(new_resp)[:_ep._PRODUCER_CLAIM_CAP]
                    ex["producer_claim"] = pc
                    packet.execution = ex
                except Exception:
                    pass
            capture = run_capture(packet, context_pkg=context_pkg, trace_dir=trace_dir,
                                  runner=runner)

        # ── Escalation side effects (branch + handback) ──
        # Two KINDS of escalation with different branch requirements:
        #   * EVIDENCE / abandoned-attempt escalation (a check RAN-and-FAILED, a
        #     high-severity finding, or a VERDICT: FAIL) — its value is that a human can
        #     INSPECT the abandoned attempt, so §13 requires an inspectable branch. If
        #     none can be built (base-unknown / no repo / git failure) → base-unknown
        #     stays owed → DEGRADE (no dangling branchless evidence escalation, judge P1).
        #   * POLICY / human-review escalation (§12 `escalate_human`: single-family or
        #     unverified review on high-risk / irreversible work) — a branch-INDEPENDENT
        #     safety obligation: a human must review because high-risk work shipped
        #     without cross-family assurance, NOT because there is an abandoned diff to
        #     inspect. This MUST reach the human queue even when no branch exists
        #     (silently degrading it would defeat §12 — adversarial re-check fold).
        escalation = None
        if loop_state.get("stop_condition") == "max_iterations_escalated":
            base_sha = ((context_pkg or {}).get("exec_review_state_before") or {}).get("head")
            task_id = ((context_pkg or {}).get("task_id")
                       or (context_pkg or {}).get("conversation_id") or "task")
            branch_ref = (branch_creator or create_escalation_branch)(
                capture.repo_root, base_sha, task_id, trace_dir=trace_dir)
            policy_escalation = bool(verify_rec.get("escalate_human"))
            if branch_ref or policy_escalation:
                reason = ("execution-review did not converge: "
                          + ("a declared check ran and failed" if capture.ran_and_failed()
                             else "a persistent high-severity finding remains"
                             if has_high_severity(verify_rec.get("findings") or [])
                             # Attribute a FAIL to the verifier that ACTUALLY ran — never
                             # claim a different-family reviewer failed the work when only a
                             # same-family (lowered-assurance) one did (would overstate the
                             # evidence to the human adjudicator; adversarial re-check fold).
                             else "the different-family verifier returned VERDICT: FAIL"
                             if verify_rec.get("verdict") == "FAIL" and not same_family
                             else "the single-family verifier returned VERDICT: FAIL "
                                  "(lowered assurance) on high-risk work"
                             if verify_rec.get("verdict") == "FAIL"
                             else "the execution-review verify could not run (unverified) on high-risk work"
                             if not verify_rec.get("ran")
                             else "single-family verify on high-risk work — human review required"))
                escalation = {"reason": reason, "abandoned_attempt_branch": branch_ref}
                if not branch_ref:
                    # A §12 policy escalation reaches the human WITHOUT an inspectable
                    # branch: there is no abandoned attempt to link (the deliverable
                    # shipped; the issue is inadequate cross-family verification), so this
                    # is NOT a §13 abandoned-attempt escalation. Record that honestly.
                    escalation["kind"] = "policy_human_review"
                    escalation["no_branch_reason"] = (
                        "no inspectable abandoned-attempt branch — base-unknown / no repo; "
                        "this is a §12 verification-gap human-review escalation, not a §13 "
                        "abandoned-attempt escalation")
                # ⚖ Rev-1 P4 / OQ4 honesty, NARROWED by Phase 8 (§3.4/OQ-9): if the
                # executor COMMITTED in place (HEAD advanced past the pre-execution
                # base), the branch isolates the working-tree delta but the committed
                # work stays on the user's branch. Full §13 isolation is now AVAILABLE
                # — a caller that declares exec_review_mode="clean_worktree" and runs
                # its executor in an isolated checkout from the start earns it — but
                # THIS run executed in place, and Phase 8 never rewrites the user's
                # branch to fake an unmerged branch.
                after_head = (capture.state_after or {}).get("head")
                if branch_ref and base_sha and after_head and after_head != base_sha:
                    escalation["unmerged_guarantee"] = (
                        "PARTIAL — executor committed in place (HEAD advanced); the "
                        "branch isolates the working-tree delta only. Full §13 "
                        "isolation is available via clean_worktree execution from the "
                        "start (exec_review_mode declaration, Phase 8); this run "
                        "executed in place.")
                loop_state["escalation"] = escalation
            else:
                # Evidence escalation with NO creatable branch → base-unknown stays owed
                # → DEGRADE (never a dangling branchless evidence escalation, judge P1).
                # The packet is recorded trace-local (never silently discarded).
                loop_state["stop_condition"] = None
                loop_state["escalation"] = None
                # Phase-7 promotion signal: a hard non-convergence (tried to escalate, no §13 branch)
                # is genuinely informative → durable_note. A structural flag, not a note-substring match.
                loop_state["escalation_withheld"] = True
                loop_state["note"] = (
                    "escalation WITHHELD — evidence escalation but no inspectable §13 "
                    "abandoned-attempt branch could be created (base-unknown / no repo / "
                    "git failure); degraded to text review, packet recorded trace-local")
                _mark_failure(RuntimeError(
                    "evidence escalation withheld — no §13 branch (base-unknown/no-repo)"),
                    "execution_loop_escalation_no_branch")

        # ── Populate the §9 packet blocks + write trace-local. ──
        reviewer_a = verify_rec.get("reviewer")
        if reviewer_a is not None:
            reviewer_a = dict(reviewer_a)
            if same_family:
                reviewer_a["same_family"] = True
                reviewer_a["fallback_reason"] = verify_rec.get("fallback_reason")
        verification = {
            "reviewer_a": reviewer_a,
            "reviewer_b": None,
            "confidence": verify_rec.get("confidence"),
            "findings": verify_rec.get("findings") or [],
            "invented_tests": verify_rec.get("invented_tests") or [],
        }
        execution = {
            "mode": capture.mode,
            "state_before": capture.state_before,
            "state_after": capture.state_after,
            "enforcement_model": capture.enforcement_model,
        }
        # Phase 8 Chunk B observability: the isolated-run record (delta commit,
        # checks, worktree_removed / fallback_reason) + the honest delta-
        # attribution caveat — in review_dirty_diff mode the temp commit
        # snapshots the LIVE tree, so foreign churn (vault autocommit,
        # editor-side linters) can ride the delta (§3.2, no new exactness claim).
        if capture.isolated is not None:
            execution["isolated_checks"] = capture.isolated
            if capture.mode == "review_dirty_diff":
                execution["delta_attribution"] = (
                    "approximate — dirty-tree capture; concurrent mutators may "
                    "ride the delta (dirty_hash recorded in state_before)")
        _ep.populate_loop_fields(packet, planning=planning, verification=verification,
                                 execution=execution, loop=loop_state, now_iso=now_iso)
        # Phase 7 (§14): decide the durable-memory tier + do the durable write (ledger / note) BEFORE
        # write_packet, so the trace JSON records the final tier. Never raises; stealth-gated; a
        # git_only turn writes nothing durable (parity). Reads max_sensitivity off full_signals.
        _epersist.persist_packet(packet, sig=full_signals, context_pkg=context_pkg,
                                 trace_dir=trace_dir, stealth=stealth, now_iso=now_iso)
        packet_path = _ep.write_packet(packet, trace_dir)

        if escalation is not None:
            entry = handback_reference(
                packet=packet, packet_path=packet_path,
                branch_ref=escalation["abandoned_attempt_branch"],
                reason=escalation["reason"], context_pkg=context_pkg)
            (queue_push or push_handback)(entry)

        return current_response if current_response != response else None
    except Exception as e:
        _mark_failure(e, "execution_loop_run")
        return None
