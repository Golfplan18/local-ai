"""Execution Review Phase 6 — the loop controller (gate + Capture driver +
different-family verify selector + single-family degrade + plan/exec revision router
+ stop rule + escalation-branch primitive + handback), per the design packet §5 test
plan. Mocked gear actuator + mocked runner (no live model); a REAL temp git repo only
for the escalation-branch + snapshot primitives (git is a hard dependency)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ORCH = Path(__file__).resolve().parent.parent
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
import live_guard  # noqa: E402,F401 — quarantines durable oversight/telemetry writes

import execution_loop as el  # noqa: E402
import execution_packet as ep  # noqa: E402
import evidence_runner as er  # noqa: E402
import execution_persistence as epx  # noqa: E402


_STORE_ENV: dict = {}


def setUpModule():
    # Phase 7: run_loop's terminal now calls execution_persistence.persist_packet, which writes to
    # the operational store data/execution-records/. Redirect it to a tempdir for the whole module so
    # the suite never touches the real ~/ora store (or the live server's store).
    d = tempfile.mkdtemp(prefix="er-loop-store-")
    _STORE_ENV["dir"] = d
    for k, v in (("ORA_EXECUTION_RECORDS_DIR", d),
                 ("ORA_EXECUTION_LEDGER_PATH", os.path.join(d, "execution-ledger.jsonl"))):
        _STORE_ENV[k] = os.environ.get(k)
        os.environ[k] = v


def tearDownModule():
    import shutil
    for k in ("ORA_EXECUTION_RECORDS_DIR", "ORA_EXECUTION_LEDGER_PATH"):
        prev = _STORE_ENV.get(k)
        if prev is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = prev
    shutil.rmtree(_STORE_ENV.get("dir", ""), ignore_errors=True)


# ── Fakes ─────────────────────────────────────────────────────────────────────
class FakeRouter:
    """A pure-config router double: one cross-family verify endpoint by default."""

    def __init__(self, *, different=None, same=None, exec_ep=None):
        self._different = different if different is not None else {
            "id": "verifier-x", "name": "verifier-x", "training_family": "gpt"}
        self._same = same if same is not None else {
            "id": "same-fam", "name": "same-fam", "training_family": "llama"}
        # The executor endpoint the loop resolves to derive the executor family.
        self._exec = exec_ep if exec_ep is not None else {
            "id": "exec", "name": "exec", "training_family": "llama"}

    def resolve_different_family(self, slot, exclude_family, context="interactive",
                                config_name=None, gear=4):
        if not exclude_family:
            return None
        fam = (self._different or {}).get("training_family")
        return self._different if (fam and fam != exclude_family) else None

    def resolve_post_analysis_slot(self, slot, context="interactive", config_name=None):
        return self._same

    def resolve_endpoint(self, slot, gear, context, config_name=None):
        return self._exec

    def _to_v1_endpoint(self, ep):
        return ep


class FakeRunner:
    """A deterministic evidence-runner double — no subprocess, no sandbox."""

    CheckResult = er.CheckResult
    Check = er.Check

    def __init__(self, *, sufficient=False, results=None, catalog=None,
                 after=None, delta_ref=None):
        self._suff = sufficient
        self._results = results if results is not None else []
        self._catalog = catalog
        self._after = after or {"head": "aaaaaaaa", "mode": "review_dirty_diff"}
        self._delta_ref = delta_ref

    def discover_catalog(self, repo_root):
        return "cat" if self._catalog is not None else None

    def parse_catalog(self, path):
        return self._catalog

    def snapshot_before(self, repo_root, mode):
        return {"head": "b" * 40, "tree": "t", "dirty_hash": None, "mode": mode}

    def snapshot_after(self, repo_root, mode, trace_dir, before):
        return dict(self._after), self._delta_ref

    def run_contract(self, catalog, contract, repo_root, worktree=None, mode=None):
        return list(self._results)

    def fill_evidence_lanes(self, packet, results, contract, delta_ref):
        return packet

    def contract_sufficient(self, results, contract):
        return self._suff

    def _git(self, repo, args, env=None):
        if args[:1] == ["rev-parse"] and "--is-inside-work-tree" in args:
            return 0, "true"
        return 0, "true"

    def _record_check_event(self, check, result):
        pass


def _pkt(sig, **kw):
    ctx = kw.pop("context_pkg", {"acceptance_criteria": "AC-1", "conversation_id": "c1",
                                 "task_id": "c1"})
    return ep.build_execution_packet(signals=sig, context_pkg=ctx,
                                     output_text=kw.pop("output_text", "did the thing"),
                                     risk_tier=kw.pop("risk_tier", "standard"), **kw)


V_PASS = "VERDICT: PASS\nCONFIDENCE: 0.9\n"
V_FAIL_HIGH = ("VERDICT: FAIL\nCONFIDENCE: 0.4\n"
               "FINDING: severity=high; class=execution_level; broke the build\n")
V_FAIL_PLAN_HIGH = ("VERDICT: FAIL\nCONFIDENCE: 0.5\n"
                    "FINDING: severity=high; class=plan_level; wrong problem\n")
# The exact confirmed-bug shapes: a FAIL with a NON-"high" severity, and a prose-only
# FAIL with zero parsed findings — both previously converged as criteria_met.
V_FAIL_CRITICAL = ("VERDICT: FAIL\nCONFIDENCE: 0.2\n"
                   "FINDING: severity=critical; class=execution_level; deletes prod db\n")
V_FAIL_PROSE = "VERDICT: FAIL\nCONFIDENCE: 0.2\nThe deliverable is unacceptable.\n"
V_PASS_ACCEPTANCE = ("VERDICT: PASS\nCONFIDENCE: 0.9\n"
                     "INVENTED_TEST: kind=acceptance; handles empty input\n")
V_PASS_DIAGNOSTIC = ("VERDICT: PASS\nCONFIDENCE: 0.9\n"
                     "INVENTED_TEST: kind=diagnostic; print timing\n")


def _verify(text):
    return lambda system, user, endpoint: text


# ── The self-evidencing GATE (§6) ──────────────────────────────────────────────
class TestGate(unittest.TestCase):
    def test_self_evidencing_turn_does_not_engage(self):
        self.assertFalse(el.should_engage({"signals": {}}))
        self.assertFalse(el.should_engage(None))
        self.assertFalse(el.should_engage({"signals": {"any_mutation": False,
                                                       "source_read_suspected": False}}))

    def test_mutation_or_source_read_engages(self):
        self.assertTrue(el.should_engage({"signals": {"any_mutation": True}}))
        self.assertTrue(el.should_engage({"signals": {"source_read_suspected": True}}))

    def test_engage_signals_reads_only_folded_data(self):
        s = el.engage_signals({"signals": {"any_mutation": True, "source_read_suspected": False}})
        self.assertEqual(s, {"any_mutation": True, "source_read_suspected": False})

    def test_loop_disabled_by_default(self):
        os.environ.pop(el._ENV_FLAG, None)
        self.assertFalse(el.loop_enabled())

    def test_loop_enabled_flag(self):
        try:
            os.environ[el._ENV_FLAG] = "1"
            self.assertTrue(el.loop_enabled())
            os.environ[el._ENV_FLAG] = "false"
            self.assertFalse(el.loop_enabled())
        finally:
            os.environ.pop(el._ENV_FLAG, None)


# ── Different-family verify selector (§12) ─────────────────────────────────────
class TestFamilySelector(unittest.TestCase):
    def test_picks_cross_family(self):
        ep_, same = el.select_verify_endpoint(executor_fam="llama", router_obj=FakeRouter())
        self.assertEqual(ep_["training_family"], "gpt")
        self.assertFalse(same)

    def test_single_family_when_no_cross_family(self):
        # different_family returns None → single-family degrade over the default slot.
        r = FakeRouter(different={"id": "x", "training_family": "llama"})
        ep_, same = el.select_verify_endpoint(executor_fam="llama", router_obj=r)
        self.assertTrue(same)
        self.assertEqual(ep_["id"], "same-fam")

    def test_unknown_executor_family_degrades(self):
        ep_, same = el.select_verify_endpoint(executor_fam=None, router_obj=FakeRouter())
        self.assertTrue(same)

    def test_router_method_skips_same_and_unknown_family(self):
        # Exercise the REAL Router.resolve_different_family candidate filter directly.
        import router as rt
        r = object.__new__(rt.Router)
        r.config = {"pipelines": {"interactive": {"post_analysis": {
            "buckets": ["b"], "cells": {}}}}}
        r._buckets = {"b": ["same", "nofam", "cross"]}
        r._endpoints = {
            "same": {"id": "same", "enabled": True, "status": "active", "training_family": "llama"},
            "nofam": {"id": "nofam", "enabled": True, "status": "active"},
            "cross": {"id": "cross", "enabled": True, "status": "active", "training_family": "qwen"},
        }
        r._resolve_endpoint_id = lambda x: x
        r._resolve_config_name = lambda cn, ctx: None
        r._to_v1_endpoint = lambda e: e
        got = r.resolve_different_family("verification", "llama")
        self.assertEqual(got["id"], "cross")
        # unknown executor family → None
        self.assertIsNone(r.resolve_different_family("verification", None))
        # if only same-family available → None
        r._buckets = {"b": ["same"]}
        self.assertIsNone(r.resolve_different_family("verification", "llama"))


# ── Verify + single-family degrade (§12) ───────────────────────────────────────
class TestVerify(unittest.TestCase):
    def test_parse_output(self):
        p = el.parse_verify_output(
            "VERDICT: FAIL\nCONFIDENCE: 0.75\n"
            "FINDING: severity=high; class=plan_level; the plan is wrong\n"
            "FINDING: severity=low; class=execution_level; a nit\n"
            "INVENTED_TEST: kind=acceptance; handles empty input\n"
            "INVENTED_TEST: kind=diagnostic; prints timing\n")
        self.assertEqual(p["verdict"], "FAIL")
        self.assertEqual(p["confidence"], 0.75)
        self.assertEqual(len(p["findings"]), 2)
        self.assertEqual(p["findings"][0]["class"], "plan_level")
        self.assertEqual(p["findings"][0]["severity"], "high")
        self.assertEqual([t["kind"] for t in p["invented_tests"]], ["acceptance", "diagnostic"])

    def test_parse_defaults(self):
        p = el.parse_verify_output("FINDING: just a description with no fields\n")
        self.assertEqual(p["findings"][0]["class"], "execution_level")
        self.assertEqual(p["findings"][0]["severity"], "medium")

    def test_single_family_lowers_confidence(self):
        rec = el.run_verify("review", verify_invoker=_verify(V_PASS),
                            endpoint={"id": "v"}, same_family=True, risk_tier="standard")
        self.assertTrue(rec["same_family"])
        self.assertIsNotNone(rec["fallback_reason"])
        # 0.9 baseline − 0.3 penalty = 0.6
        self.assertAlmostEqual(rec["confidence"], 0.6, places=4)

    def test_single_family_high_risk_escalates_to_human(self):
        rec = el.run_verify("review", verify_invoker=_verify(V_PASS),
                            endpoint={"id": "v"}, same_family=True, risk_tier="irreversible")
        self.assertTrue(rec["escalate_human"])

    def test_cross_family_no_penalty(self):
        rec = el.run_verify("review", verify_invoker=_verify(V_PASS),
                            endpoint={"id": "v"}, same_family=False, risk_tier="standard")
        self.assertFalse(rec["same_family"])
        self.assertEqual(rec["confidence"], 0.9)
        self.assertFalse(rec["escalate_human"])

    def test_no_invoker_is_safe(self):
        rec = el.run_verify("review", verify_invoker=None)
        self.assertEqual(rec["findings"], [])
        self.assertIsNotNone(rec["fallback_reason"])
        self.assertFalse(rec["ran"])   # no invoker → verify did not run

    def test_empty_or_broken_output_marks_not_ran(self):
        # judge P1 fold: an empty / no-VERDICT response is NOT a usable verify.
        for out in ("", "   ", "I could not complete the review.", "blah blah no verdict"):
            rec = el.run_verify("review", verify_invoker=_verify(out), endpoint={"id": "v"})
            self.assertFalse(rec["ran"], repr(out))
            self.assertIsNotNone(rec["fallback_reason"])
        # a PASS or a lone FINDING IS usable → ran.
        self.assertTrue(el.run_verify("review", verify_invoker=_verify(V_PASS),
                                      endpoint={"id": "v"})["ran"])
        self.assertTrue(el.run_verify(
            "review", verify_invoker=_verify("FINDING: severity=low; class=execution_level; nit"),
            endpoint={"id": "v"})["ran"])

    def test_broken_verify_high_risk_escalates_to_human(self):
        rec = el.run_verify("review", verify_invoker=_verify(""), endpoint={"id": "v"},
                            risk_tier="irreversible")
        self.assertTrue(rec["escalate_human"])


# ── Revision router (§12) ──────────────────────────────────────────────────────
class TestRouterAndSeverity(unittest.TestCase):
    def test_fork_plan_vs_execution(self):
        f = [{"class": "plan_level", "severity": "high", "description": "a"},
             {"class": "execution_level", "severity": "low", "description": "b"},
             {"severity": "medium", "description": "c"}]  # default → execution
        ex, pl = el.route_findings(f)
        self.assertEqual(len(pl), 1)
        self.assertEqual(len(ex), 2)

    def test_high_severity_any_class_blocks(self):
        self.assertTrue(el.has_high_severity([{"class": "plan_level", "severity": "high"}]))
        self.assertTrue(el.has_high_severity([{"class": "execution_level", "severity": "high"}]))
        self.assertFalse(el.has_high_severity([{"severity": "medium"}]))

    def test_critical_and_blocker_severity_also_block(self):
        # Adversarial-precheck fold: a verifier that emits critical/blocker/severe/major
        # must not slip past the stop rule as a mere non-"high" token.
        for sev in ("critical", "blocker", "severe", "major", "fatal", "CRITICAL"):
            self.assertTrue(el.has_high_severity([{"severity": sev}]), sev)
        self.assertFalse(el.has_high_severity([{"severity": "low"}]))

    def test_only_acceptance_invented_tests_obligate(self):
        tests = [{"kind": "acceptance", "name": "x"}, {"kind": "diagnostic", "name": "y"},
                 {"kind": "exploratory", "name": "z"}]
        self.assertEqual(len(el.obligating_invented_tests(tests)), 1)


# ── Stop rule (§13) ────────────────────────────────────────────────────────────
class TestStopRule(unittest.TestCase):
    def _cap(self, **kw):
        return el.CaptureResult(**kw)

    def test_converge_requires_sufficient_and_no_high_severity(self):
        self.assertTrue(el.converged(self._cap(sufficient=True), []))
        self.assertFalse(el.converged(self._cap(sufficient=False), []))
        # sufficient but a high-severity PLAN-level finding remains → not converged
        self.assertFalse(el.converged(self._cap(sufficient=True),
                                      [{"class": "plan_level", "severity": "high"}]))

    def test_fail_verdict_blocks_convergence(self):
        # Adversarial-precheck fold: an explicit VERDICT: FAIL never reads as converged,
        # even with sufficient evidence and no high-severity finding parsed.
        self.assertFalse(el.converged(self._cap(sufficient=True), [], "FAIL"))
        self.assertTrue(el.converged(self._cap(sufficient=True), [], "PASS"))
        self.assertTrue(el.converged(self._cap(sufficient=True), [], None))
        # and a FAIL verdict warrants escalation (not a silent degrade).
        self.assertTrue(el.escalation_warranted(self._cap(sufficient=True), [], "FAIL"))

    def test_only_acceptance_invented_tests_block_and_escalate(self):
        acceptance = [{"kind": "acceptance", "name": "handles empty input"}]
        diagnostic = [{"kind": "diagnostic", "name": "print timing"}]
        cap = self._cap(sufficient=True)
        self.assertFalse(el.converged(cap, [], "PASS", True, acceptance))
        self.assertTrue(el.escalation_warranted(cap, [], "PASS", acceptance))
        self.assertTrue(el.converged(cap, [], "PASS", True, diagnostic))
        self.assertFalse(el.escalation_warranted(cap, [], "PASS", diagnostic))

    def test_unverified_blocks_convergence(self):
        # judge P1 fold: a verify that did NOT run (empty/broken) cannot converge —
        # criteria_met with no reviewer is grading-your-own-homework.
        self.assertFalse(el.converged(self._cap(sufficient=True), [], "PASS", verify_ran=False))
        self.assertFalse(el.converged(self._cap(sufficient=True), [], None, verify_ran=False))
        self.assertTrue(el.converged(self._cap(sufficient=True), [], "PASS", verify_ran=True))

    def test_escalate_only_on_ran_and_failed_or_high_severity(self):
        ran_failed = self._cap(results=[er.CheckResult(name="t", skipped=False, passed=False)])
        self.assertTrue(el.escalation_warranted(ran_failed, []))
        self.assertTrue(el.escalation_warranted(self._cap(),
                                                [{"class": "execution_level", "severity": "high"}]))

    def test_owed_deferred_empty_lane_never_escalates(self):
        # A DEFERRED / REFUSED / owed check (skipped=True) is NOT ran-and-failed.
        deferred = self._cap(results=[er.CheckResult(name="mut", skipped=True,
                                                     skip_reason="deferred to Phase 8")])
        self.assertFalse(el.escalation_warranted(deferred, []))
        # no repo / no checks / no findings → no escalation
        self.assertFalse(el.escalation_warranted(self._cap(no_repo=True), []))
        self.assertFalse(el.escalation_warranted(self._cap(no_checks=True), []))
        # a non-high finding does not force escalation either
        self.assertFalse(el.escalation_warranted(self._cap(), [{"severity": "medium"}]))


# ── Capture driver (§3/§10/§11) ────────────────────────────────────────────────
class TestCaptureDriver(unittest.TestCase):
    def test_no_repo_owes_lane(self):
        pkt = _pkt({"any_mutation": True})
        cap = el.run_capture(pkt, context_pkg={}, runner=FakeRunner(),
                             repo_root=None)
        # FakeRunner._git says every path is a work tree, so discover would find cwd;
        # force no repo by making discover fail.
        r = FakeRunner()
        r._git = lambda repo, args, env=None: (1, "")
        cap = el.run_capture(pkt, context_pkg={}, runner=r, repo_root=None)
        self.assertTrue(cap.no_repo)
        self.assertFalse(cap.sufficient)

    def test_mutating_required_check_is_deferred_not_run(self):
        cat = er.Catalog(checks={
            "build": er.Check(name="build", argv=["true"], mutates=False),
            "mig": er.Check(name="mig", argv=["true"], mutates=True)})
        runner = FakeRunner(catalog=cat, sufficient=False,
                            results=[er.CheckResult(name="build", skipped=False, passed=True)])
        pkt = _pkt({"any_mutation": True},
                   context_pkg={"repo_root": "/x", "evidence_contract":
                                {"required_standard_checks": ["build", "mig"]}})
        cap = el.run_capture(pkt, context_pkg={"repo_root": "/x", "evidence_contract":
                             {"required_standard_checks": ["build", "mig"]}},
                             runner=runner, repo_root="/x")
        self.assertIn("mig", cap.deferred_mutating)
        # a deferred mutating required check → not a ran-and-failed check
        self.assertFalse(cap.ran_and_failed())

    _BASE = {"repo_root": "/x", "exec_review_state_before": {"head": "b" * 40}}

    def test_light_runs_catalog_checks_directly(self):
        cat = er.Catalog(checks={"build": er.Check(name="build", argv=["true"], mutates=False)})
        runner = FakeRunner(catalog=cat, sufficient=True,
                            results=[er.CheckResult(name="build", skipped=False, passed=True)])
        pkt = _pkt({"any_mutation": True}, context_pkg=dict(self._BASE))
        cap = el.run_capture(pkt, context_pkg=dict(self._BASE), runner=runner, repo_root="/x")
        # no contract (light) → runs the catalog's own checks; sufficiency via runner
        self.assertFalse(cap.base_unknown)
        self.assertTrue(cap.sufficient)

    def test_base_unknown_forces_diff_lane_owed(self):
        # judge P1 fold: no pre-execution snapshot → base-unknown → NEVER sufficient,
        # even if the checks pass on the current tree.
        cat = er.Catalog(checks={"build": er.Check(name="build", argv=["true"], mutates=False)})
        runner = FakeRunner(catalog=cat, sufficient=True,
                            results=[er.CheckResult(name="build", skipped=False, passed=True)])
        pkt = _pkt({"any_mutation": True}, context_pkg={"repo_root": "/x"})   # no base stashed
        cap = el.run_capture(pkt, context_pkg={"repo_root": "/x"}, runner=runner, repo_root="/x")
        self.assertTrue(cap.base_unknown)
        self.assertFalse(cap.sufficient)   # owed, not a false convergence
        lane = next(l for l in pkt.evidence_lanes if l.lane == "diff_validate")
        self.assertIsNone(lane.sufficient)   # lane marked owed

    def test_light_tier_deferred_mutating_is_not_sufficient(self):
        # Adversarial-precheck fold: at LIGHT tier (no contract) a deferred mutating
        # catalog check must count as NOT sufficient — using the REAL sufficiency logic.
        cat = er.Catalog(checks={
            "build": er.Check(name="build", argv=["true"], mutates=False),
            "migrate": er.Check(name="migrate", argv=["true"], mutates=True)})

        class RealSuff(FakeRunner):
            def contract_sufficient(self, results, contract):
                return er.contract_sufficient(results, contract)

            def run_contract(self, catalog, contract, repo_root, worktree=None, mode=None):
                return [er.CheckResult(name=n, skipped=False, passed=True)
                        for n in contract.get("required_standard_checks", [])]

        pkt = _pkt({"any_mutation": True}, context_pkg=dict(self._BASE))
        cap = el.run_capture(pkt, context_pkg=dict(self._BASE),
                             runner=RealSuff(catalog=cat), repo_root="/x")
        self.assertFalse(cap.base_unknown)   # a base IS stashed — isolate the deferral
        self.assertIn("migrate", cap.deferred_mutating)
        self.assertFalse(cap.sufficient)   # deferred required check → NOT sufficient
        self.assertFalse(cap.ran_and_failed())   # deferred is not ran-and-failed


# ── Escalation branch primitive (§13) — REAL temp git repo ─────────────────────
class TestEscalationBranch(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="er-escal-")
        self._git("init", "-q")
        self._git("config", "user.email", "t@t")
        self._git("config", "user.name", "t")
        (Path(self.d) / "a.txt").write_text("base\n")
        self._git("add", "-A")
        self._git("commit", "-qm", "base")
        self.base = self._git("rev-parse", "HEAD").stdout.strip()

    def _git(self, *a):
        return subprocess.run(["git", "-C", self.d, *a], capture_output=True, text=True)

    def test_branch_is_unmerged_and_leaves_user_state_untouched(self):
        (Path(self.d) / "a.txt").write_text("CHANGED\n")
        (Path(self.d) / "new.txt").write_text("added\n")
        # Preserve a real staged-index state as well as the working tree. The
        # escalation snapshot must use only its throwaway index.
        self._git("add", "a.txt")
        index_before = self._git("write-tree").stdout.strip()
        branch = el.create_escalation_branch(self.d, self.base, "task-1", trace_dir=self.d)
        self.assertTrue(branch)
        self.assertEqual(self._git("rev-parse", "--verify", branch).returncode, 0)
        # user HEAD + working tree untouched
        self.assertEqual(self._git("rev-parse", "HEAD").stdout.strip(), self.base)
        self.assertEqual((Path(self.d) / "a.txt").read_text(), "CHANGED\n")
        self.assertEqual(self._git("write-tree").stdout.strip(), index_before)
        # abandoned attempt captured on the branch
        tree = self._git("ls-tree", "-r", "--name-only", branch).stdout
        self.assertIn("new.txt", tree)
        # branch is unmerged relative to HEAD
        self.assertNotIn(branch, self._git("branch", "--merged", "HEAD").stdout)

    def test_bad_base_returns_none(self):
        self.assertIsNone(el.create_escalation_branch(self.d, "not-a-sha", "t"))
        self.assertIsNone(el.create_escalation_branch(None, self.base, "t"))

    def test_gitignored_files_excluded(self):
        (Path(self.d) / ".gitignore").write_text("secret.env\n")
        self._git("add", "-A")
        self._git("commit", "-qm", "ignore")
        base = self._git("rev-parse", "HEAD").stdout.strip()
        (Path(self.d) / "secret.env").write_text("API_KEY=xyz\n")
        (Path(self.d) / "ok.txt").write_text("ok\n")
        branch = el.create_escalation_branch(self.d, base, "t2")
        tree = self._git("ls-tree", "-r", "--name-only", branch).stdout
        self.assertIn("ok.txt", tree)
        self.assertNotIn("secret.env", tree)   # secret file gated out by .gitignore

    def test_second_escalation_same_conversation_does_not_overwrite_first(self):
        # §13: the abandoned attempt is never silently discarded. Two escalations
        # in the SAME conversation share task_id; the per-turn trace_dir basename
        # discriminates them so the second does not replace the first ref.
        (Path(self.d) / "a.txt").write_text("ATTEMPT-ONE\n")
        b1 = el.create_escalation_branch(self.d, self.base, "conv-42",
                                         trace_dir="/traces/turn-aaa")
        (Path(self.d) / "a.txt").write_text("ATTEMPT-TWO\n")
        b2 = el.create_escalation_branch(self.d, self.base, "conv-42",
                                         trace_dir="/traces/turn-bbb")
        self.assertTrue(b1 and b2)
        self.assertNotEqual(b1, b2)                       # distinct branches
        self.assertEqual(self._git("rev-parse", "--verify", b1).returncode, 0)
        self.assertEqual(self._git("rev-parse", "--verify", b2).returncode, 0)
        # The first branch still holds the FIRST abandoned attempt, not the second.
        self.assertEqual(self._git("show", f"{b1}:a.txt").stdout, "ATTEMPT-ONE\n")
        self.assertEqual(self._git("show", f"{b2}:a.txt").stdout, "ATTEMPT-TWO\n")

    def test_every_capture_failure_preserves_ref_head_index_and_worktree(self):
        stages = ("read-tree", "add", "write-tree", "commit-tree", "update-ref", "readback")
        for stage in stages:
            with self.subTest(stage=stage):
                task_id = f"fault-{stage}"
                trace_dir = f"/traces/turn-{stage}"
                branch = f"execution-review/escalation-{task_id}-turn-{stage}"
                self._git("branch", branch, self.base)
                old_ref = self._git("rev-parse", branch).stdout.strip()

                (Path(self.d) / "a.txt").write_text(f"ATTEMPT-{stage}\n")
                self._git("add", "a.txt")
                (Path(self.d) / f"untracked-{stage}.txt").write_text("attempt\n")
                head_before = self._git("rev-parse", "HEAD").stdout.strip()
                index_before = self._git("write-tree").stdout.strip()
                status_before = self._git("status", "--porcelain=v1").stdout
                failed = False

                def fault_git(repo, args, env=None):
                    nonlocal failed
                    op = args[0]
                    is_readback = (
                        op == "rev-parse"
                        and args[1:2] == ["--verify"]
                        and "--quiet" not in args
                    )
                    if not failed and (op == stage or (stage == "readback" and is_readback)):
                        failed = True
                        return 1, f"simulated {stage} failure"
                    return er._git(repo, args, env=env)

                result = el.create_escalation_branch(
                    self.d, self.base, task_id, trace_dir=trace_dir, git=fault_git)

                self.assertTrue(failed)
                self.assertIsNone(result)
                self.assertEqual(self._git("rev-parse", branch).stdout.strip(), old_ref)
                self.assertEqual(self._git("rev-parse", "HEAD").stdout.strip(), head_before)
                self.assertEqual(self._git("write-tree").stdout.strip(), index_before)
                self.assertEqual(self._git("status", "--porcelain=v1").stdout, status_before)

                # Reset only this subtest's fixture state; the assertion above has
                # already proved the function itself did not touch it.
                self._git("reset", "--hard", "-q", self.base)
                self._git("clean", "-fdq")

    def test_failed_new_ref_readback_removes_the_unverified_ref(self):
        branch = "execution-review/escalation-new-ref-turn-new"
        (Path(self.d) / "a.txt").write_text("ATTEMPT\n")
        failed = False

        def fault_git(repo, args, env=None):
            nonlocal failed
            is_readback = (
                args[0] == "rev-parse"
                and args[1:2] == ["--verify"]
                and "--quiet" not in args
            )
            if is_readback and not failed:
                failed = True
                return 1, "simulated readback failure"
            return er._git(repo, args, env=env)

        result = el.create_escalation_branch(
            self.d, self.base, "new-ref", trace_dir="/traces/turn-new", git=fault_git)
        self.assertTrue(failed)
        self.assertIsNone(result)
        self.assertNotEqual(self._git("rev-parse", "--verify", branch).returncode, 0)

    def test_every_capture_failure_leaves_no_new_ref(self):
        stages = ("read-tree", "add", "write-tree", "commit-tree", "update-ref", "readback")
        for stage in stages:
            with self.subTest(stage=stage):
                task_id = f"new-{stage}"
                trace_dir = f"/traces/new-turn-{stage}"
                branch = f"execution-review/escalation-{task_id}-new-turn-{stage}"
                (Path(self.d) / "a.txt").write_text(f"ATTEMPT-{stage}\n")
                failed = False

                def fault_git(repo, args, env=None):
                    nonlocal failed
                    op = args[0]
                    is_readback = (
                        op == "rev-parse"
                        and args[1:2] == ["--verify"]
                        and "--quiet" not in args
                    )
                    if not failed and (op == stage or (stage == "readback" and is_readback)):
                        failed = True
                        return 1, f"simulated {stage} failure"
                    return er._git(repo, args, env=env)

                result = el.create_escalation_branch(
                    self.d, self.base, task_id, trace_dir=trace_dir, git=fault_git)

                self.assertTrue(failed)
                self.assertIsNone(result)
                self.assertNotEqual(
                    self._git("rev-parse", "--verify", branch).returncode, 0)
                self._git("reset", "--hard", "-q", self.base)


# ── snapshot_pre_execution (planning seam) — REAL temp git repo ────────────────
class TestSnapshotBefore(unittest.TestCase):
    def test_captures_pre_execution_head(self):
        d = tempfile.mkdtemp(prefix="er-snap-")
        subprocess.run(["git", "-C", d, "init", "-q"])
        subprocess.run(["git", "-C", d, "config", "user.email", "t@t"])
        subprocess.run(["git", "-C", d, "config", "user.name", "t"])
        (Path(d) / "a.txt").write_text("x\n")
        subprocess.run(["git", "-C", d, "add", "-A"])
        subprocess.run(["git", "-C", d, "commit", "-qm", "base"])
        head = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        ctx = {"repo_root": d}
        before = el.snapshot_pre_execution(ctx, repo_root=d)
        self.assertEqual(before["head"], head)
        self.assertEqual(ctx["exec_review_state_before"]["head"], head)

    def test_no_repo_returns_none(self):
        d = tempfile.mkdtemp(prefix="er-norepo-")
        self.assertIsNone(el.snapshot_pre_execution({"repo_root": d}, repo_root=d))


# ── run_loop end-to-end (mocked runner + verify) ───────────────────────────────
class TestRunLoop(unittest.TestCase):
    _OK_BRANCH = staticmethod(lambda *a, **k: "execution-review/escalation-test")

    def _run(self, sig, verify_text, runner, *, risk_tier="standard", actuator=None,
             ctx=None, branch_creator="__ok__", queue_delivery="__ok__",
             trace_dir=None):
        pushes = []
        ctx = ctx or {"acceptance_criteria": "AC", "conversation_id": "c1", "task_id": "c1",
                      "exec_review_state_before": {"head": "a" * 40, "mode": "review_dirty_diff"}}
        # Inject a working branch creator by default so escalation tests exercise a
        # real §13 branch ref (create_escalation_branch itself is covered by the real-
        # git TestEscalationBranch); pass branch_creator=... to test the no-branch path.
        if branch_creator == "__ok__":
            branch_creator = self._OK_BRANCH
        if queue_delivery == "__ok__":
            def queue_delivery(entry):
                pushes.append(entry)
                return True
        pkt = ep.build_execution_packet(signals=sig, context_pkg=ctx, output_text="x",
                                        risk_tier=risk_tier)
        revised = el.run_loop(packet=pkt, context_pkg=ctx, response="x", signals=sig,
                              risk_tier=risk_tier, trace_dir=trace_dir,
                              config={}, config_name=None,
                              verify_invoker=_verify(verify_text), actuator=actuator,
                              runner=runner, router_obj=FakeRouter(),
                              queue_push=queue_delivery,
                              branch_creator=branch_creator)
        return pkt, revised, pushes

    def test_converge(self):
        pkt, revised, pushes = self._run({"any_mutation": True}, V_PASS,
                                         FakeRunner(sufficient=True))
        self.assertEqual(pkt.loop["stop_condition"], "criteria_met")
        self.assertEqual(pkt.status, "converged")
        self.assertEqual(pkt.verification["reviewer_a"]["family"], "gpt")
        self.assertIsNone(revised)
        self.assertEqual(pushes, [])

    def test_acceptance_obligation_blocks_pass_and_reaches_existing_authority(self):
        pkt, revised, pushes = self._run(
            {"any_mutation": True}, V_PASS_ACCEPTANCE,
            FakeRunner(sufficient=True))
        self.assertEqual(pkt.loop["stop_condition"], "max_iterations_escalated")
        self.assertEqual(pkt.status, "escalated")
        self.assertIsNone(revised)
        self.assertEqual(len(pushes), 1)
        self.assertIn("acceptance-kind verifier obligation", pkt.loop["escalation"]["reason"])

    def test_diagnostic_suggestion_does_not_block_pass(self):
        pkt, revised, pushes = self._run(
            {"any_mutation": True}, V_PASS_DIAGNOSTIC,
            FakeRunner(sufficient=True))
        self.assertEqual(pkt.loop["stop_condition"], "criteria_met")
        self.assertEqual(pkt.status, "converged")
        self.assertIsNone(revised)
        self.assertEqual(pushes, [])

    def test_converged_turn_is_git_only(self):
        # Phase 7 parity: a clean converge earns the cheapest tier — no durable record.
        pkt, _, _ = self._run({"any_mutation": True}, V_PASS, FakeRunner(sufficient=True))
        self.assertEqual(pkt.status, "converged")
        self.assertEqual(epx.decide_tier(pkt), epx.TIER_GIT_ONLY)

    def test_escalation_persists_durable_note_and_ledger(self):
        # Phase 7 end-to-end wiring: an escalated turn drives persist_packet at the run_loop
        # terminal, writing a durable_note markdown record + its ledger index (into the redirected
        # store). Proves the terminal actually reaches the persistence layer.
        import json as _json
        pkt, _, _ = self._run({"any_mutation": True}, V_FAIL_HIGH, FakeRunner(sufficient=False))
        self.assertEqual(pkt.status, "escalated")
        self.assertEqual(pkt.persistence["tier"], epx.TIER_DURABLE_NOTE)
        lp = epx.ledger_sink_path()
        self.assertTrue(os.path.exists(lp), "run_loop terminal did not write the ledger")
        with open(lp) as _f:
            durable = [_json.loads(l) for l in _f
                       if l.strip() and _json.loads(l).get("tier") == "durable_note"]
        self.assertTrue(durable, "no durable_note ledger line for the escalated turn")
        self.assertTrue(os.path.exists(durable[-1]["note_ref"]))

    def test_escalation_handback_carries_note_ref(self):
        # Phase 8 (OQ6 rewire): the Paused-queue handback prefers the DURABLE
        # note ref (persist_packet stamps packet.persistence["note_ref"]
        # BEFORE the handback is built) — packet_ref alone dangles after the
        # 30d trace sweep. And the handback summary is the durable-suppressed
        # render (no lane excerpts).
        pkt, _, pushes = self._run({"any_mutation": True}, V_FAIL_HIGH,
                                   FakeRunner(sufficient=False))
        self.assertEqual(pkt.status, "escalated")
        self.assertEqual(len(pushes), 1)
        cs = pushes[0]["context_summary"]
        self.assertEqual(cs["note_ref"], pkt.persistence.get("note_ref"))
        self.assertTrue(cs["note_ref"] and os.path.exists(cs["note_ref"]))
        self.assertIn("ephemeral", cs["packet_ref_note"])

    def test_escalate_on_high_severity(self):
        pkt, revised, pushes = self._run({"any_mutation": True}, V_FAIL_HIGH,
                                         FakeRunner(sufficient=False))
        self.assertEqual(pkt.loop["stop_condition"], "max_iterations_escalated")
        self.assertEqual(pkt.status, "escalated")
        self.assertEqual(len(pushes), 1)
        self.assertEqual(pushes[0]["context_summary"]["kind"], "execution_review_escalation")

    def test_high_severity_plan_level_also_escalates(self):
        # ⚖ Rev-1 P1: a high-severity PLAN-level finding must block convergence too.
        pkt, _, pushes = self._run({"any_mutation": True}, V_FAIL_PLAN_HIGH,
                                   FakeRunner(sufficient=True))
        self.assertEqual(pkt.loop["stop_condition"], "max_iterations_escalated")
        self.assertEqual(len(pushes), 1)

    def test_owed_lane_degrades_not_escalates(self):
        # insufficient + verifier did NOT fail + NO ran-and-failed check + NO
        # high-severity finding → degrade (the owed/deferred lane, not a failure).
        pkt, _, pushes = self._run({"any_mutation": True}, V_PASS,
                                   FakeRunner(sufficient=False))
        self.assertIsNone(pkt.loop["stop_condition"])
        self.assertIn("degraded to text review", pkt.loop["note"])
        self.assertEqual(pushes, [])

    def test_source_read_only_fills_provenance_lane(self):
        # Phase 8 Chunk A: the owed stub is replaced by a REAL fill — the lane
        # is no longer tri-state-None, the loop note says FILLED, and the turn
        # still never enters the converge/escalate cycle.
        pkt, revised, pushes = self._run(
            {"source_read_suspected": True, "any_mutation": False}, V_FAIL_HIGH,
            FakeRunner(sufficient=False))
        self.assertIsNone(pkt.loop["stop_condition"])
        self.assertIn("collect_provenance lane FILLED", pkt.loop["note"])
        lane = next(l for l in pkt.evidence_lanes
                    if l.lane == "collect_provenance")
        self.assertIsNotNone(lane.sufficient)      # filled (tri-state resolved)
        self.assertFalse(lane.sufficient)          # Level 1 never sufficient
        self.assertIn("provenance", lane.result)
        self.assertEqual(pushes, [])   # never escalates

    def test_mixed_turn_fills_lane_informationally_and_still_converges(self):
        # Phase 8 §9-required mixed-turn test: any_mutation + source_read →
        # the provenance lane is FILLED (mixed_turn flagged) and renders
        # under the informational header, while the mutation loop's
        # convergence is UNCHANGED (OQ-4 deferral: provenance is not a
        # convergence input; a Level-1 insufficient lane must not block
        # criteria_met or leak an INSUFFICIENT token into the verify prompt).
        pkt, revised, pushes = self._run(
            {"any_mutation": True, "source_read_suspected": True}, V_PASS,
            FakeRunner(sufficient=True))
        self.assertEqual(pkt.loop["stop_condition"], "criteria_met")
        self.assertEqual(pkt.status, "converged")
        lane = next(l for l in pkt.evidence_lanes
                    if l.lane == "collect_provenance")
        self.assertIsNotNone(lane.sufficient)
        self.assertFalse(lane.sufficient)
        self.assertTrue(lane.result["provenance"]["mixed_turn"])
        text = ep.render_for_review(pkt)
        self.assertIn("informational — not a convergence input", text)
        self.assertNotIn("INSUFFICIENT", text)
        self.assertEqual(pushes, [])

    def test_source_read_only_owed_fallback_when_fill_unavailable(self):
        # The honest owed marker survives as the FALLBACK when the filler
        # fails: lane stays tri-state None, loud marker, still no escalation.
        import unittest.mock as _mock
        with _mock.patch.object(el._eprov, "fill_provenance_lane",
                                return_value=None):
            pkt, revised, pushes = self._run(
                {"source_read_suspected": True, "any_mutation": False},
                V_FAIL_HIGH, FakeRunner(sufficient=False))
        self.assertIsNone(pkt.loop["stop_condition"])
        self.assertIn("collect_provenance owed", pkt.loop["note"])
        lane = next(l for l in pkt.evidence_lanes
                    if l.lane == "collect_provenance")
        self.assertIsNone(lane.sufficient)         # still owed
        self.assertEqual(pushes, [])   # never escalates

    def test_stealth_is_dormant(self):
        pkt = ep.build_execution_packet(signals={"any_mutation": True},
                                        context_pkg={}, output_text="x", risk_tier="standard")
        out = el.run_loop(packet=pkt, context_pkg={}, response="x",
                          signals={"any_mutation": True}, stealth=True)
        self.assertIsNone(out)
        self.assertIsNone(pkt.loop)   # untouched

    def test_fail_verdict_with_sufficient_evidence_escalates_not_converges(self):
        # The confirmed bug: sufficient=True + VERDICT: FAIL (critical severity, or a
        # prose-only FAIL with no parsed findings) previously converged as criteria_met.
        # Both must now ESCALATE, never converge.
        for vtext in (V_FAIL_CRITICAL, V_FAIL_PROSE):
            pkt, _, pushes = self._run({"any_mutation": True}, vtext,
                                       FakeRunner(sufficient=True))
            self.assertEqual(pkt.loop["stop_condition"], "max_iterations_escalated", vtext)
            self.assertEqual(pkt.status, "escalated", vtext)
            self.assertEqual(len(pushes), 1, vtext)
        # The prose-only FAIL (no findings) escalates specifically on the FAIL verdict.
        pkt, _, _ = self._run({"any_mutation": True}, V_FAIL_PROSE, FakeRunner(sufficient=True))
        self.assertIn("VERDICT: FAIL", pkt.loop["escalation"]["reason"])
        # The critical-severity FAIL escalates on the (now-blocking) high-severity finding.
        pkt2, _, _ = self._run({"any_mutation": True}, V_FAIL_CRITICAL, FakeRunner(sufficient=True))
        self.assertIn("high-severity", pkt2.loop["escalation"]["reason"])

    def test_owed_lane_with_pass_verdict_and_actuator_does_not_churn(self):
        # actuator wired, but insufficiency is a purely owed lane (no findings, no
        # ran-and-failed): the loop must DEGRADE without ever re-invoking the actuator.
        calls = []

        def actuator(ex, pl, it):
            calls.append(it)
            return "should never be produced"

        ctx = {"acceptance_criteria": "AC", "task_id": "c1",
               "exec_review_state_before": {"head": "a" * 40, "mode": "review_dirty_diff"}}
        pkt = ep.build_execution_packet(signals={"any_mutation": True}, context_pkg=ctx,
                                        output_text="x", risk_tier="standard")
        revised = el.run_loop(packet=pkt, context_pkg=ctx, response="x",
                              signals={"any_mutation": True}, risk_tier="standard",
                              config={}, verify_invoker=_verify(V_PASS), actuator=actuator,
                              runner=FakeRunner(sufficient=False), router_obj=FakeRouter())
        self.assertEqual(calls, [])   # actuator never called — no futile churn
        self.assertIsNone(pkt.loop["stop_condition"])
        self.assertIn("degraded to text review", pkt.loop["note"])
        self.assertIsNone(revised)

    def test_broken_verify_does_not_converge(self):
        # judge P1 fold: an empty verifier response + sufficient evidence must NOT
        # converge as criteria_met — it degrades (standard tier), unverified.
        pkt, _, pushes = self._run({"any_mutation": True}, "", FakeRunner(sufficient=True))
        self.assertIsNone(pkt.loop["stop_condition"])
        self.assertIn("unverified", pkt.loop["note"])
        self.assertEqual(pushes, [])

    def test_broken_verify_high_risk_escalates(self):
        pkt, _, pushes = self._run({"any_mutation": True}, "", FakeRunner(sufficient=True),
                                   risk_tier="irreversible")
        self.assertEqual(pkt.loop["stop_condition"], "max_iterations_escalated")
        self.assertEqual(len(pushes), 1)
        self.assertIn("unverified", pkt.loop["escalation"]["reason"])

    def test_base_unknown_failed_check_degrades_no_null_branch(self):
        # judge Rev-2 P1: base-unknown (no snapshot) + a FAILED check must NOT escalate
        # with a null branch — the check outcome is owed (not attributable), so it
        # degrades. Reproduces the judge's exact probe.
        cat = er.Catalog(checks={"build": er.Check(name="build", argv=["true"], mutates=False)})
        runner = FakeRunner(catalog=cat, sufficient=False,
                            results=[er.CheckResult(name="build", skipped=False, passed=False)])
        ctx = {"acceptance_criteria": "AC", "task_id": "c1", "repo_root": "/x"}  # NO snapshot
        pkt, _, pushes = self._run({"any_mutation": True}, V_PASS, runner, ctx=ctx)
        self.assertIsNone(pkt.loop["stop_condition"])   # degraded, not escalated
        self.assertEqual(pushes, [])                    # NO null-branch handback
        self.assertIsNone(pkt.loop.get("escalation"))

    def test_evidence_escalation_without_creatable_branch_downgrades_to_degrade(self):
        # An EVIDENCE escalation (high-severity finding, standard tier → not
        # escalate_human) with NO creatable §13 branch must DOWNGRADE to a loud degrade
        # rather than queue a branchless handback — its value is the inspectable attempt.
        pkt, _, pushes = self._run({"any_mutation": True}, V_FAIL_HIGH,
                                   FakeRunner(sufficient=False),
                                   branch_creator=lambda *a, **k: None)
        self.assertIsNone(pkt.loop["stop_condition"])
        self.assertIn("escalation WITHHELD", pkt.loop["note"])
        self.assertEqual(pushes, [])   # never a null-branch evidence escalation

    def test_failed_attempt_capture_never_projects_a_preserved_attempt(self):
        calls = []

        def failing_git(repo, args, env=None):
            calls.append(tuple(args))
            if args[0] in {"read-tree", "add"}:
                return 0, ""
            if args[0] == "write-tree":
                return 1, "simulated write-tree failure"
            raise AssertionError(args)

        def failed_capture(*args, **kwargs):
            return el.create_escalation_branch(
                "/tmp/does-not-matter", "a" * 40, "recovery-probe",
                trace_dir="/tmp/turn-1", git=failing_git)

        pkt, _, pushes = self._run(
            {"any_mutation": True}, V_FAIL_HIGH, FakeRunner(sufficient=False),
            branch_creator=failed_capture)

        self.assertEqual(calls[-1][0], "write-tree")
        self.assertIsNone(pkt.loop["stop_condition"])
        self.assertIsNone(pkt.loop.get("escalation"))
        self.assertTrue(pkt.loop["escalation_withheld"])
        self.assertNotIn("preserved attempt", pkt.loop["note"].lower())
        self.assertEqual(pushes, [])

    def test_same_family_fail_reason_does_not_claim_different_family(self):
        # Adversarial re-check fold: a same-family VERDICT:FAIL escalation reason must
        # NOT claim "the different-family verifier" (would overstate assurance). Router
        # returns no cross-family endpoint → single-family degrade → same_family=True.
        same_router = FakeRouter(different={"id": "x", "training_family": "llama"})
        ctx = {"acceptance_criteria": "AC", "task_id": "c1",
               "exec_review_state_before": {"head": "a" * 40, "mode": "review_dirty_diff"}}
        pkt = ep.build_execution_packet(signals={"any_mutation": True}, context_pkg=ctx,
                                        output_text="x", risk_tier="high-risk")
        pushes = []

        def queue_delivery(entry):
            pushes.append(entry)
            return True

        el.run_loop(packet=pkt, context_pkg=ctx, response="x", signals={"any_mutation": True},
                    risk_tier="high-risk", config={},
                    verify_invoker=_verify("VERDICT: FAIL\nCONFIDENCE: 0.5\n"
                                           "FINDING: severity=medium; class=execution_level; concern\n"),
                    actuator=None, runner=FakeRunner(sufficient=False), router_obj=same_router,
                    branch_creator=self._OK_BRANCH, queue_push=queue_delivery)
        reason = pkt.loop["escalation"]["reason"]
        self.assertNotIn("different-family verifier returned", reason)
        self.assertIn("single-family verifier returned VERDICT: FAIL", reason)

    def test_policy_escalation_reaches_human_without_branch(self):
        # Adversarial re-check fold: a §12 POLICY escalation (single-family / unverified
        # verify on HIGH-RISK work → escalate_human) is branch-INDEPENDENT — it MUST
        # reach the human queue even when no §13 branch can be created (base-unknown),
        # NOT be silently degraded. Reproduces the re-check's exact scenario.
        pkt, _, pushes = self._run({"any_mutation": True}, "",   # empty → unverified
                                   FakeRunner(sufficient=True), risk_tier="irreversible",
                                   branch_creator=lambda *a, **k: None)   # no branch possible
        self.assertEqual(pkt.loop["stop_condition"], "max_iterations_escalated")
        self.assertEqual(len(pushes), 1)                    # human IS reached
        esc = pkt.loop["escalation"]
        self.assertEqual(esc["kind"], "policy_human_review")
        self.assertIsNone(esc["abandoned_attempt_branch"])   # honestly no branch
        self.assertIn("unverified", esc["reason"])

    def test_acceptance_obligation_reaches_authority_without_branch(self):
        pkt, _, pushes = self._run(
            {"any_mutation": True}, V_PASS_ACCEPTANCE,
            FakeRunner(sufficient=True),
            branch_creator=lambda *a, **k: None)
        self.assertEqual(pkt.loop["stop_condition"], "max_iterations_escalated")
        self.assertEqual(len(pushes), 1)
        self.assertEqual(pkt.loop["escalation"]["kind"], "policy_human_review")
        self.assertIsNone(pkt.loop["escalation"]["abandoned_attempt_branch"])

    def test_failed_handoff_stays_retryable_and_visible(self):
        import json as _json

        attempted = []

        def fail_delivery(entry):
            attempted.append(entry)
            return False

        with tempfile.TemporaryDirectory(prefix="er-handoff-") as trace_dir:
            pkt, returned, _ = self._run(
                {"any_mutation": True}, V_FAIL_HIGH,
                FakeRunner(sufficient=False), queue_delivery=fail_delivery,
                trace_dir=trace_dir)
            on_disk = _json.loads(
                (Path(trace_dir) / ep._PACKET_FILENAME).read_text())

        self.assertEqual(len(attempted), 1)
        pending = pkt.loop["human_handoff"]
        self.assertEqual(pending["status"], "pending")
        self.assertTrue(pending["retryable"])
        self.assertFalse(pending["human_reached"])
        self.assertEqual(on_disk["loop"]["human_handoff"], pending)
        self.assertIn("No human was reached", returned)
        self.assertIn("pending and retryable", returned)
        self.assertTrue(returned.startswith("x\n\n"))

    def test_verifier_renders_with_acceptance_criteria_not_absence_fence(self):
        # judge P1 fold: the packet must carry the criteria BEFORE the verify render,
        # so the verifier never judges against a false "NO ACCEPTANCE CRITERIA" fence.
        seen = {}

        def capturing_verify(system, user, endpoint):
            seen["review"] = user
            return V_PASS

        ctx = {"acceptance_criteria": "AC-42: must not delete prod", "task_id": "c1",
               "exec_review_state_before": {"head": "a" * 40, "mode": "review_dirty_diff"}}
        pkt = ep.build_execution_packet(signals={"any_mutation": True}, context_pkg=ctx,
                                        output_text="x", risk_tier="standard")
        el.run_loop(packet=pkt, context_pkg=ctx, response="x", signals={"any_mutation": True},
                    risk_tier="standard", config={}, verify_invoker=capturing_verify,
                    actuator=None, runner=FakeRunner(sufficient=True), router_obj=FakeRouter())
        self.assertIn("AC-42: must not delete prod", seen["review"])
        self.assertNotIn("NO ACCEPTANCE CRITERIA DECLARED", seen["review"])

    def test_actuator_revises_then_converges(self):
        # First verify FAILs high-sev → revise via actuator → second verify PASSes.
        calls = {"n": 0}

        def verify(system, user, endpoint):
            calls["n"] += 1
            return V_FAIL_HIGH if calls["n"] == 1 else V_PASS

        # runner becomes sufficient after the revision (simulate the fix landing)
        state = {"suff": False}

        class R(FakeRunner):
            def contract_sufficient(self, results, contract):
                return state["suff"]

        def actuator(exec_findings, plan_findings, iteration):
            state["suff"] = True
            return "revised deliverable"

        ctx = {"acceptance_criteria": "AC", "task_id": "c1",
               "exec_review_state_before": {"head": "a" * 40, "mode": "review_dirty_diff"}}
        pkt = ep.build_execution_packet(signals={"any_mutation": True}, context_pkg=ctx,
                                        output_text="x", risk_tier="standard")
        revised = el.run_loop(packet=pkt, context_pkg=ctx, response="x",
                              signals={"any_mutation": True}, risk_tier="standard",
                              config={}, verify_invoker=verify, actuator=actuator,
                              runner=R(sufficient=False), router_obj=FakeRouter())
        self.assertEqual(pkt.loop["stop_condition"], "criteria_met")
        self.assertEqual(revised, "revised deliverable")
        self.assertEqual(pkt.loop["iteration"], 1)

    def test_actuator_clears_current_acceptance_obligation_then_converges(self):
        calls = {"verify": 0, "actuator": []}

        def verify(system, user, endpoint):
            calls["verify"] += 1
            return V_PASS_ACCEPTANCE if calls["verify"] == 1 else V_PASS

        def actuator(exec_findings, plan_findings, iteration):
            calls["actuator"].append((exec_findings, plan_findings, iteration))
            return "acceptance obligation corrected"

        ctx = {"acceptance_criteria": "AC", "task_id": "c1",
               "exec_review_state_before": {"head": "a" * 40,
                                             "mode": "review_dirty_diff"}}
        pkt = ep.build_execution_packet(
            signals={"any_mutation": True}, context_pkg=ctx,
            output_text="x", risk_tier="standard")
        revised = el.run_loop(
            packet=pkt, context_pkg=ctx, response="x",
            signals={"any_mutation": True}, risk_tier="standard", config={},
            verify_invoker=verify, actuator=actuator,
            runner=FakeRunner(sufficient=True), router_obj=FakeRouter())

        self.assertEqual(pkt.loop["stop_condition"], "criteria_met")
        self.assertEqual(revised, "acceptance obligation corrected")
        self.assertEqual(calls["verify"], 2)
        self.assertEqual(len(calls["actuator"]), 1)
        exec_findings, plan_findings, iteration = calls["actuator"][0]
        self.assertEqual(exec_findings[0]["invented_test_kind"], "acceptance")
        self.assertEqual(plan_findings, [])
        self.assertEqual(iteration, 1)


# ── Handback (§7/§13) — reference-only + stealth defense-in-depth ──────────────
class TestHandback(unittest.TestCase):
    def _ref(self, conversation_id="c9"):
        packet_context = {"raw_prompt": "do x"}
        handback_context = {}
        if conversation_id is not None:
            packet_context["conversation_id"] = conversation_id
            handback_context["conversation_id"] = conversation_id
        pkt = ep.build_execution_packet(signals={"any_mutation": True},
                                        context_pkg=packet_context,
                                        output_text="SECRET producer claim text",
                                        risk_tier="standard")
        return el.handback_reference(packet=pkt, packet_path="/trace/p.json",
                                     branch_ref="execution-review/escalation-c9",
                                     reason="did not converge",
                                     context_pkg=handback_context)

    def test_reference_has_top_level_conversation_id(self):
        ref = self._ref()
        self.assertEqual(ref["conversation_id"], "c9")            # top-level for purge backstop
        self.assertEqual(ref["event"]["conversation_id"], "c9")

    def test_summary_is_redacted_reference_not_inlined_claim(self):
        ref = self._ref()
        summ = ref["context_summary"]["summary"]
        self.assertNotIn("SECRET producer claim text", summ)      # producer claim NOT inlined
        self.assertIn("PRODUCER CLAIM REDACTED", summ)
        self.assertEqual(ref["context_summary"]["packet_ref"], "/trace/p.json")
        self.assertEqual(ref["context_summary"]["abandoned_attempt_branch"],
                         "execution-review/escalation-c9")

    def test_push_handback_stealth_skips_durable_write(self):
        # Even though run_loop gates on non-stealth, push_handback itself must skip the
        # durable write under a stealth context (defense in depth) — regardless of which
        # backend it would use.
        import oversight_events as oe
        from unittest import mock
        with mock.patch.object(oe, "_is_stealth_context", return_value=True):
            self.assertFalse(el.push_handback(self._ref()))

    def test_push_handback_reports_dual_backend_failure(self):
        import oversight_actions as oa
        import oversight_events as oe
        import oversight_queue as oq
        import tool_events as te
        from unittest import mock

        token = te.set_turn_context(
            conversation_id="c9", principal_id="principal:user",
        )
        try:
            with mock.patch.object(oe, "_is_stealth_context", return_value=False), \
                    mock.patch.object(
                        oq, "add_entry",
                        side_effect=OSError("primary failed")) as primary, \
                    mock.patch.object(
                        oa, "_append_human_queue",
                        side_effect=OSError("fallback failed")) as fallback:
                self.assertFalse(el.push_handback(self._ref()))
        finally:
            te.reset_turn_context(token)
        primary.assert_called_once()
        fallback.assert_called_once()

    def test_generated_handback_resolves_acceptance_and_waiver(self):
        """A real generated handback is signed, typed, and terminally resolved.

        Approve exercises the managed queue plus the real discussion chain.
        Deny exercises the raw fallback plus the direct slash path. Neither
        disposition may fall into PED handling or mint rerun authority.
        """
        import json
        from contextlib import ExitStack
        from unittest import mock

        import oversight_actions as oa
        import oversight_queue as oq
        import redefinition_handler as rh
        import resolution_chain as rc
        import runtime_paths as rp
        import slash_commands as sc
        import tool_events as te

        cases = (
            ("accept", False, "accepted"),
            ("waive", True, "waived"),
        )
        for disposition, force_fallback, expected_event in cases:
            with self.subTest(disposition=disposition), \
                    tempfile.TemporaryDirectory(
                        prefix="er-handback-authority-",
                    ) as tmp, ExitStack() as stack:
                queue_path = os.path.join(tmp, "human-queue.jsonl")
                approvals_path = os.path.join(tmp, "execution-approvals.json")
                events_path = os.path.join(tmp, "tool-events.jsonl")
                sessions_root = os.path.join(tmp, "sessions")
                stack.enter_context(mock.patch.object(
                    oq, "HUMAN_QUEUE_PATH", queue_path,
                ))
                stack.enter_context(mock.patch.object(
                    oa, "HUMAN_QUEUE_PATH", queue_path,
                ))
                stack.enter_context(mock.patch.object(
                    rh, "HUMAN_QUEUE_PATH", queue_path,
                ))
                stack.enter_context(mock.patch.object(
                    te, "APPROVALS_PATH", approvals_path,
                ))
                stack.enter_context(mock.patch.object(
                    te, "GLOBAL_SINK_DEFAULT", events_path,
                ))
                stack.enter_context(mock.patch.object(
                    rp, "ORA_HOME", Path(tmp),
                ))
                stack.enter_context(mock.patch.object(
                    oq, "_generate_name", return_value="Execution Review",
                ))
                stack.enter_context(mock.patch.object(
                    rh, "approve_redefinition",
                    side_effect=AssertionError("PED approval must not run"),
                ))
                stack.enter_context(mock.patch.object(
                    rh, "deny_redefinition",
                    side_effect=AssertionError("PED denial must not run"),
                ))
                if force_fallback:
                    stack.enter_context(mock.patch.object(
                        oq, "add_entry",
                        side_effect=OSError("force raw fallback"),
                    ))

                principal_id = f"principal:{disposition}-turn"
                token = te.set_turn_context(
                    conversation_id="c9", principal_id=principal_id,
                )
                stack.callback(te.reset_turn_context, token)
                te._queued_hashes.clear()
                stack.callback(te._queued_hashes.clear)

                unstamped = self._ref(conversation_id=None)
                self.assertEqual(unstamped["conversation_id"], "")
                self.assertEqual(unstamped["event"]["conversation_id"], "")

                for location in ("top-level", "event"):
                    conflicting = dict(unstamped)
                    conflicting["event"] = dict(unstamped["event"])
                    if location == "top-level":
                        conflicting["conversation_id"] = "different-dialogue"
                    else:
                        conflicting["event"]["conversation_id"] = (
                            "different-dialogue"
                        )
                    with mock.patch.object(
                        te, "get_turn_context", wraps=te.get_turn_context,
                    ) as get_turn_context, mock.patch.object(
                        te, "_register_pending_approval",
                    ) as register_pending:
                        with self.assertRaisesRegex(
                            ValueError, "conversation_id conflicts",
                        ):
                            te.prepare_execution_review_handback(conflicting)
                    self.assertEqual(get_turn_context.call_count, 1)
                    register_pending.assert_not_called()
                    self.assertFalse(os.path.exists(approvals_path))
                    self.assertFalse(os.path.exists(queue_path))

                with mock.patch.object(
                    te, "get_turn_context", wraps=te.get_turn_context,
                ) as get_turn_context, mock.patch.object(
                    te, "_register_pending_approval",
                    return_value="snapshot-only-nonce",
                ) as register_pending:
                    snapshot_prepared, snapshot_nonce = (
                        te.prepare_execution_review_handback(unstamped)
                    )
                self.assertEqual(get_turn_context.call_count, 1)
                register_pending.assert_called_once()
                self.assertEqual(snapshot_nonce, "snapshot-only-nonce")
                self.assertEqual(snapshot_prepared["conversation_id"], "c9")
                self.assertEqual(
                    snapshot_prepared["event"]["conversation_id"], "c9",
                )
                self.assertEqual(
                    snapshot_prepared["event"]["principal_id"], principal_id,
                )
                self.assertFalse(os.path.exists(approvals_path))
                self.assertFalse(os.path.exists(queue_path))

                self.assertTrue(el.push_handback(unstamped))
                with open(queue_path, encoding="utf-8") as stream:
                    stored = json.loads(stream.readline())

                event = stored["event"]
                self.assertEqual(stored["kind"], "execution_gate")
                self.assertFalse(stored["redefinition"])
                self.assertEqual(stored["conversation_id"], "c9")
                self.assertEqual(event["conversation_id"], "c9")
                self.assertEqual(event["principal_id"], principal_id)
                self.assertEqual(
                    event["event_type"], "ExecutionReviewEscalation",
                )
                self.assertEqual(
                    stored["context_summary"]["kind"],
                    "execution_review_escalation",
                )
                self.assertEqual(
                    event["action"], "execution_review_handback",
                )
                self.assertEqual(
                    event["args_hash"], te.normalize_args_hash(
                        "execution_review_handback",
                        event["handback_identity"],
                    ),
                )
                self.assertEqual(
                    event["handback_identity"]["conversation_id"], "c9",
                )
                self.assertTrue(te.has_live_approval_request(
                    stored, principal_id=principal_id,
                ))
                approval_state = te._load_approvals()
                self.assertEqual(approval_state["tokens"], [])
                self.assertEqual(len(approval_state["pending"]), 1)
                request = approval_state["pending"][0]
                self.assertEqual(request["nonce"], event["approval_nonce"])
                self.assertEqual(request["queue_id"], stored["id"])
                self.assertEqual(request["action"], event["action"])
                self.assertEqual(request["args_hash"], event["args_hash"])
                self.assertEqual(request["conversation_id"], "c9")
                self.assertEqual(request["principal_id"], principal_id)
                self.assertEqual(
                    request["queue_authority_digest"],
                    te._queue_authority_digest(stored),
                )
                self.assertFalse(request["consumed"])
                queue_text = sc.run_runtime_command("/queue")
                self.assertIn("execution review handback", queue_text.lower())
                self.assertNotIn("legacy_untyped", queue_text)

                entry_id = stored["id"]
                if disposition == "accept":
                    started = rc.start_resolution(
                        entry_id, sessions_root=sessions_root, config={},
                    )
                    result = rc.continue_resolution(
                        rc.ContinuationContext(
                            queue_id=entry_id, last_alternative="",
                        ),
                        [],
                        "1",
                        conversation_id=started["conversation_id"],
                        principal_id=principal_id,
                    )
                    self.assertIn("Accepted and resolved", result)
                else:
                    result = sc.run_runtime_command(
                        "/deny 0 deliberate verifier waiver",
                        conversation_id="c9",
                        principal_id=principal_id,
                    )
                    self.assertIn("Waived and rejected", result)
                    self.assertIn(
                        "The terminal Execution Review handback was "
                        "deliberately rejected and marked waived for this "
                        "preserved attempt.",
                        result,
                    )
                    self.assertIn("deliberate verifier waiver", result)
                    self.assertNotIn("acceptance obligation", result)

                self.assertIn("No rerun authority was granted", result)
                self.assertIsNone(oq.find_paused_by_id(entry_id))
                self.assertEqual(oq.list_paused(), [])
                self.assertFalse(te.has_live_approval_request(
                    stored, principal_id=principal_id,
                ))
                self.assertIsNone(te.check_and_consume_approval(
                    "execution_review_handback",
                    event["args_hash"],
                    "c9",
                    principal_id=principal_id,
                ))
                approval_state = te._load_approvals()
                self.assertEqual(approval_state["tokens"], [])
                self.assertEqual(len(approval_state["pending"]), 1)
                consumed = approval_state["pending"][0]
                self.assertEqual(consumed["nonce"], event["approval_nonce"])
                self.assertEqual(consumed["queue_id"], entry_id)
                self.assertTrue(consumed["consumed"])
                with open(events_path, encoding="utf-8") as stream:
                    terminal_events = [
                        json.loads(line) for line in stream if line.strip()
                    ]
                self.assertEqual(
                    terminal_events[-1]["gate"]["decision"], expected_event,
                )


# ── Portability (Windows-sim pure logic) ───────────────────────────────────────
class TestPortability(unittest.TestCase):
    def test_branch_name_is_git_ref_safe(self):
        # Windows-style path chars + spaces must not leak into a git ref name.
        for tid in ("C:\\Users\\x\\conv 1", "a/b\\c:d*e", "conv\t1", ""):
            name = el._safe_ref(tid)
            for bad in ("\\", ":", "*", " ", "\t"):
                self.assertNotIn(bad, name)
            self.assertTrue(name)   # never empty

    def test_family_selector_is_pure_config_read(self):
        # The selector never touches the OS / filesystem — pure config double.
        ep_, same = el.select_verify_endpoint(executor_fam="qwen", router_obj=FakeRouter())
        self.assertEqual(ep_["training_family"], "gpt")
        self.assertFalse(same)

    def test_looks_like_sha(self):
        self.assertTrue(el._looks_like_sha("a" * 40))
        self.assertFalse(el._looks_like_sha("nothex-zz"))
        self.assertFalse(el._looks_like_sha(None))


if __name__ == "__main__":
    unittest.main()
