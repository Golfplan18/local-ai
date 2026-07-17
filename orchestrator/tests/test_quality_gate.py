"""Final-output quality gate (f-quality-gate.md) — unit + behavioral tests.

Covers the bounded-redo gate ported from MSI into the base engine:

  * ``_parse_quality_gate_problem`` — the Gear-4 ANALYSIS/FORMATTING routing
    key, including the safe-default behaviour.
  * Reuse of the existing ``VERDICT:`` contract — a gate output that also
    carries a ``PROBLEM:`` line still parses to the right verdict.
  * Gear 3: a real FAIL sends REQUIRED FIXES to the reviser and independently
    reinspects the corrected identity; FAIL and BROKEN withhold the candidate.
  * Gear 4: a FAIL routes a bounded redo by problem type — FORMATTING re-runs
    the step-8 formatter; ANALYSIS re-runs the step-7 consolidator then
    re-formats; one redo per problem type across at most three gate passes.
  * Doc/source backstops: the framework spec exists (ora + vault pair) and the
    gate stays wired into both gears.

The gears are driven with the proven mock pattern from
``test_gear4_no_short_circuit`` — every model call funnels through
``_call_with_supplement`` / ``_call_with_retry``, so a side-effect router keyed
on the step name scripts the whole pipeline deterministically without any
network or model dependency.
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ORCH_DIR = Path(__file__).resolve().parent.parent
if str(ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(ORCH_DIR))

import boot  # noqa: E402
import governed_process_runtime as gpr  # noqa: E402
from tests.test_governed_process_runtime import make_definition, make_run  # noqa: E402

DUMMY_EP = {"id": "ep", "name": "ep", "type": "remote"}


# ───────────────────────────── pure unit tests ──────────────────────────────


class TestParseQualityGateProblem(unittest.TestCase):
    """The Gear-4 routing key. Defaults to ANALYSIS (substance-first)."""

    def test_explicit_formatting(self):
        self.assertEqual(
            boot._parse_quality_gate_problem("PROBLEM: FORMATTING\nVERDICT: FAIL"),
            "FORMATTING",
        )

    def test_explicit_analysis(self):
        self.assertEqual(
            boot._parse_quality_gate_problem("PROBLEM: ANALYSIS\nVERDICT: FAIL"),
            "ANALYSIS",
        )

    def test_case_insensitive_and_dash_variants(self):
        for line in ("problem: formatting", "PROBLEM - FORMATTING",
                     "**PROBLEM:** FORMATTING", "PROBLEM — FORMATTING"):
            self.assertEqual(
                boot._parse_quality_gate_problem(line + "\nVERDICT: FAIL"),
                "FORMATTING", msg=line)

    def test_last_occurrence_wins(self):
        text = "PROBLEM: FORMATTING\n...discussion...\nPROBLEM: ANALYSIS\nVERDICT: FAIL"
        self.assertEqual(boot._parse_quality_gate_problem(text), "ANALYSIS")

    def test_missing_problem_defaults_to_analysis(self):
        self.assertEqual(boot._parse_quality_gate_problem("VERDICT: FAIL"), "ANALYSIS")

    def test_empty_defaults_to_analysis(self):
        self.assertEqual(boot._parse_quality_gate_problem(""), "ANALYSIS")
        self.assertEqual(boot._parse_quality_gate_problem(None), "ANALYSIS")

    def test_problem_word_in_prose_does_not_false_match(self):
        # "the problem with the analysis" is not an anchored PROBLEM: line.
        prose = "There is a problem with the analysis here.\nVERDICT: PASS"
        self.assertEqual(boot._parse_quality_gate_problem(prose), "ANALYSIS")


class TestVerdictContractReuse(unittest.TestCase):
    """A gate output carrying a PROBLEM line must still parse via the existing
    VERDICT parser — the PROBLEM line must not perturb verdict resolution."""

    def test_fail_with_problem_line(self):
        out = "## QUALITY GATE\n...\nPROBLEM: FORMATTING\nVERDICT: FAIL"
        self.assertEqual(boot._extract_structured_verdict(out), "FAIL")
        self.assertFalse(boot._verifier_passed(out))
        self.assertFalse(boot._verifier_broken(out))

    def test_pass_with_problem_line(self):
        out = "## QUALITY GATE\n...\nPROBLEM: ANALYSIS\nVERDICT: PASS"
        self.assertEqual(boot._extract_structured_verdict(out), "PASS")
        self.assertTrue(boot._verifier_passed(out))

    def test_broken(self):
        out = "Cannot evaluate — corpus missing.\nVERDICT: BROKEN"
        self.assertTrue(boot._verifier_broken(out))
        self.assertFalse(boot._verifier_passed(out))

    def test_problem_formatting_token_not_misread_as_verdict(self):
        # 'FORMATTING'/'ANALYSIS' are not verdict tokens; only the VERDICT line
        # should resolve. A FAIL deliverable tagged FORMATTING is still FAIL.
        out = "PROBLEM: FORMATTING\nVERDICT: FAIL"
        self.assertEqual(boot._extract_structured_verdict(out), "FAIL")


# ───────────────────────── behavioral harness ───────────────────────────────


class _Harness:
    """Scripts the pipeline. ``gate_outputs`` are returned for successive
    ``quality-gate`` judge calls (the last one repeats if exhausted)."""

    def __init__(self, gate_outputs, verifier_outputs=None):
        self.gate_outputs = list(gate_outputs)
        self.gate_idx = 0
        self.verifier_outputs = list(verifier_outputs or [
            "All universal checks pass.\nVERDICT: PASS"
        ])
        self.verifier_idx = 0
        self.calls = []  # list of (step_name, user_content)

    def _route(self, messages, step_name):
        user = messages[-1]["content"] if messages else ""
        self.calls.append((step_name, user))
        if step_name == "verifier":
            out = self.verifier_outputs[
                min(self.verifier_idx, len(self.verifier_outputs) - 1)
            ]
            self.verifier_idx += 1
            return (out, True, "ok")
        if step_name == "quality-gate":
            out = self.gate_outputs[min(self.gate_idx, len(self.gate_outputs) - 1)]
            self.gate_idx += 1
            return (out, True, "ok")
        tag = "QGFIX" if "QUALITY-GATE — REQUIRED FIXES" in user else "ORIG"
        return (f"<<{step_name}:{tag}>> " + ("x" * 80), True, "ok")

    def supp(self, messages, endpoint, step_name, *a, **k):
        return self._route(messages, step_name)

    def retry(self, messages, endpoint, step_name, *a, **k):
        return self._route(messages, step_name)

    def count(self, step_name):
        return sum(1 for s, _ in self.calls if s == step_name)

    def saw_qgfix(self, step_name):
        return any(s == step_name and "QUALITY-GATE — REQUIRED FIXES" in u
                   for s, u in self.calls)


@contextlib.contextmanager
def _patched(h):
    with contextlib.ExitStack() as es:
        def p(name, **kw):
            es.enter_context(mock.patch.object(boot, name, **kw))
        p("get_slot_endpoint", return_value=DUMMY_EP)
        p("resolve_gear4_endpoints", return_value=(DUMMY_EP, DUMMY_EP, True))
        p("_assemble_step_prompt", return_value="sys")
        p("_images_for_endpoint", return_value=None)
        p("vision_capable_for_endpoint", return_value=True)
        p("_run_claim_verification_preflight", return_value=("", [], {}, []))
        p("_run_unflagged_claim_scan", return_value=("", {}, []))
        p("_maybe_synthesize_visual", return_value=("", {}))
        p("_maybe_review_and_refine_visual", side_effect=lambda text, *a, **k: text)
        p("_formatter_output_structural_check", return_value=(True, "ok"))
        p("_reviser_output_structural_check", return_value=(True, "ok"))
        p("_strip_consolidator_preamble", side_effect=lambda t: t)
        p("_strip_dispatch_noise", side_effect=lambda t: t)
        p("_scrub_pipeline_leaks", side_effect=lambda t: (t, [], None))
        p("extract_revised_draft_section", side_effect=lambda t: "", create=True)
        p("_call_with_supplement", side_effect=h.supp)
        p("_call_with_retry", side_effect=h.retry)
        yield


def _ctx():
    return {"cleaned_prompt": "Q", "trace_dir": None, "mode_name": "test-mode"}


def _bind_run(ctx, runtime, run_id, evaluator=None):
    if evaluator is None:
        evaluator = lambda observation: {  # noqa: E731
            "directive": "ACCEPT",
            "target_node_id": "accepted",
            "reason": "independent final evidence supports acceptance",
            "evaluation_boundary": "independent_quality_review",
        }
    ctx["process_run_binding"] = {
        "runtime": runtime,
        "run_id": run_id,
        "segment_id": "text-review",
        "final_review": {
            "candidate_artifact_id": "gear3-result",
            "evidence_artifact_prefix": "gear3-final-review",
            "evidence_id": "result_verified",
            "candidate_node_id": "act",
            "evidence_node_id": "verify",
            "candidate_action": "produce_artifact",
            "evidence_action": "record_evidence",
            "candidate_selector": "scope:declared_outputs",
            "evidence_selector": "scope:declared_outputs",
            "reviewer_id": "independent-gear3-reviewer",
            "satisfied_conditions": ["approved_plan_digest_matches"],
        },
        "process_coherence_evaluator": evaluator,
    }
    return ctx


# ─────────────────────────── Gear 3 behavior ────────────────────────────────


class TestGear3QualityGate(unittest.TestCase):
    def test_pass_ships_without_redo(self):
        h = _Harness(["## QUALITY GATE\nall good\nVERDICT: PASS"])
        with _patched(h):
            result = boot.run_gear3(_ctx(), {}, config_name=None)
        self.assertEqual(h.count("quality-gate"), 1)
        self.assertNotIn("QGFIX", result)              # no reviser redo fired
        self.assertFalse(h.saw_qgfix("reviser"))

    def test_fail_fires_one_reviser_redo_and_reinspects_before_release(self):
        h = _Harness([
            "## QUALITY GATE\nCQ1 unmet\nVERDICT: FAIL",
            "## QUALITY GATE\ncorrected\nVERDICT: PASS",
        ])
        with _patched(h):
            result = boot.run_gear3(_ctx(), {}, config_name=None)
        self.assertEqual(h.count("quality-gate"), 2)
        self.assertTrue(h.saw_qgfix("reviser"))        # reviser got the fixes
        self.assertIn("QGFIX", result)                 # reviewed redo ships

    def test_fail_after_reinspection_withholds_corrected_candidate(self):
        h = _Harness(["VERDICT: FAIL", "VERDICT: FAIL"])
        with _patched(h):
            result = boot.run_gear3(_ctx(), {}, config_name=None)
        self.assertEqual(h.count("quality-gate"), 2)
        self.assertTrue(h.saw_qgfix("reviser"))
        self.assertIn("Deliverable withheld", result)
        self.assertNotIn("QGFIX", result)

    def test_broken_withholds_without_content_redo(self):
        h = _Harness(["Cannot reach a verdict.\nVERDICT: BROKEN"])
        with _patched(h):
            result = boot.run_gear3(_ctx(), {}, config_name=None)
        self.assertEqual(h.count("quality-gate"), 1)
        self.assertFalse(h.saw_qgfix("reviser"))
        self.assertNotIn("QGFIX", result)
        self.assertIn("Deliverable withheld", result)

    def test_bound_process_run_supplies_limit_and_persists_attempts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = gpr.GovernedProcessRuntime(temp_dir, now=lambda: "2026-07-16T18:00:00-07:00")
            definition = make_definition()
            run = make_run("run-gear3", definition)
            run["contracts"]["correction_loop"]["max_attempts"] = 12
            run["contracts"]["correction_loop"]["repeated_defect_limit"] = 12
            runtime.create_run(definition, run)
            ctx = _ctx()
            _bind_run(ctx, runtime, "run-gear3")
            h = _Harness(
                ["VERDICT: PASS"],
                verifier_outputs=["VERDICT: FAIL", "VERDICT: PASS"],
            )
            with _patched(h):
                boot.run_gear3(ctx, {}, config_name=None)

            persisted = runtime.load_run("run-gear3")
            self.assertEqual(persisted["contracts"]["correction_loop"]["attempt"], 2)
            self.assertEqual(persisted["state"], "completed")
            attempts = [
                record["event"]["event_type"]
                for record in runtime.load_records("run-gear3")
                if record["record_type"] == "event"
                and record["event"]["event_type"].startswith("attempt_")
            ]
            self.assertEqual(attempts, [
                "attempt_started", "attempt_completed",
                "attempt_started", "attempt_completed",
            ])

    def test_high_bound_does_not_force_extra_gear3_attempts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = gpr.GovernedProcessRuntime(temp_dir, now=lambda: "2026-07-16T18:00:00-07:00")
            definition = make_definition()
            run = make_run("run-gear3-pass", definition)
            run["contracts"]["correction_loop"]["max_attempts"] = 12
            runtime.create_run(definition, run)
            ctx = _ctx()
            _bind_run(ctx, runtime, "run-gear3-pass")
            with _patched(_Harness(["VERDICT: PASS"])):
                boot.run_gear3(ctx, {}, config_name=None)
            self.assertEqual(
                runtime.load_run("run-gear3-pass")["contracts"]["correction_loop"]["attempt"],
                1,
            )

    def test_bound_fail_observation_follows_process_coherence_replan_not_redo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = gpr.GovernedProcessRuntime(temp_dir, now=lambda: "2026-07-16T18:00:00-07:00")
            definition = make_definition()
            run = make_run("run-gear3-replan", definition)
            runtime.create_run(definition, run)
            ctx = _ctx()
            _bind_run(ctx, runtime, "run-gear3-replan", evaluator=lambda observation: {
                "failure_class": "plan",
                "target_node_id": "verify",
                "reason": "Process Coherence found a plan-level defect",
                "evaluation_boundary": "independent_quality_review",
            })
            h = _Harness(["VERDICT: FAIL"])
            with _patched(h):
                result = boot.run_gear3(ctx, {}, config_name=None)
            self.assertFalse(h.saw_qgfix("reviser"))
            self.assertIn("Deliverable withheld", result)
            persisted = runtime.load_run("run-gear3-replan")
            self.assertEqual(persisted["state"], "pending")
            self.assertEqual(
                [
                    record["transition"]["directive"]
                    for record in runtime.load_records("run-gear3-replan")
                    if record["record_type"] == "transition"
                ],
                ["REPLAN"],
            )

    def test_bound_revision_is_reinspected_then_accepts_new_artifact_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = gpr.GovernedProcessRuntime(temp_dir, now=lambda: "2026-07-16T18:00:00-07:00")
            definition = make_definition()
            verification = next(
                node for node in definition["graph"]["nodes"]
                if node["node_id"] == "verify"
            )
            verification["routes"]["REVISE"] = "verify"
            run = make_run("run-gear3-reinspect", definition)
            runtime.create_run(definition, run)
            ctx = _ctx()

            def evaluate(observation):
                if observation["observation"] == "PASS":
                    return {
                        "directive": "ACCEPT",
                        "target_node_id": "accepted",
                        "reason": "corrected identity passed independent reinspection",
                        "evaluation_boundary": "independent_quality_review",
                    }
                return {
                    "failure_class": "execution",
                    "target_node_id": "verify",
                    "reason": "the current artifact has a correctable execution defect",
                    "evaluation_boundary": "independent_quality_review",
                }

            _bind_run(ctx, runtime, "run-gear3-reinspect", evaluator=evaluate)
            h = _Harness(["VERDICT: FAIL", "VERDICT: PASS"])
            with _patched(h):
                result = boot.run_gear3(ctx, {}, config_name=None)
            self.assertIn("QGFIX", result)
            self.assertEqual(runtime.load_run("run-gear3-reinspect")["state"], "completed")
            records = runtime.load_records("run-gear3-reinspect")
            self.assertEqual(
                [r["transition"]["directive"] for r in records if r["record_type"] == "transition"],
                ["REVISE", "ACCEPT"],
            )
            artifact_events = [
                r["event"]["details"] for r in records
                if (r.get("event") or {}).get("event_type") == "artifact_recorded"
                and r["event"]["details"]["artifact_id"] == "gear3-result"
            ]
            self.assertEqual(len(artifact_events), 2)
            self.assertTrue(artifact_events[-1]["stale_review_invalidated"])


class TestGear3VerdictThreadForPacket(unittest.TestCase):
    """The packet label describes the inspected identity and release state."""

    def test_fail_redo_records_fresh_pass_after_reinspection(self):
        ctx = _ctx()
        h = _Harness([
            "## QUALITY GATE\nCQ1 unmet\nVERDICT: FAIL",
            "## QUALITY GATE\nfixed\nVERDICT: PASS",
        ])
        with _patched(h):
            result = boot.run_gear3(ctx, {}, config_name=None)
        self.assertIn("QGFIX", result)
        er = ctx.get("execution_review")
        self.assertIsNotNone(er)
        self.assertEqual(er["verdict"], "PASS")
        self.assertEqual(er["status"], "passed-after-correction-reinspection")
        self.assertEqual(er["scope"], "text_review")

    def test_failed_reinspection_records_withheld_status(self):
        ctx = _ctx()
        h = _Harness(["VERDICT: FAIL", "VERDICT: FAIL"])
        with _patched(h):
            result = boot.run_gear3(ctx, {}, config_name=None)
        self.assertIn("Deliverable withheld", result)
        self.assertEqual(ctx["execution_review"]["verdict"], "FAIL")
        self.assertEqual(
            ctx["execution_review"]["status"],
            "failed-after-final-reinspection-withheld",
        )

    def test_pass_records_pass_verdict(self):
        ctx = _ctx()
        h = _Harness(["## QUALITY GATE\nall good\nVERDICT: PASS"])
        with _patched(h):
            boot.run_gear3(ctx, {}, config_name=None)
        er = ctx.get("execution_review")
        self.assertEqual(er["verdict"], "PASS")
        self.assertIsNone(er.get("status"))

    def test_broken_records_broken_verdict(self):
        ctx = _ctx()
        h = _Harness(["Cannot reach a verdict.\nVERDICT: BROKEN"])
        with _patched(h):
            boot.run_gear3(ctx, {}, config_name=None)
        er = ctx.get("execution_review")
        self.assertEqual(er["verdict"], "BROKEN")
        self.assertEqual(er["status"], "review-unavailable-withheld")


# ─────────────────────────── Gear 4 behavior ────────────────────────────────


class TestGear4QualityGate(unittest.TestCase):
    def _run(self, h):
        with _patched(h):
            return boot.run_gear4(_ctx(), {}, execution_context="interactive",
                                  config_name=None)

    def test_pass_ships_formatter_output_without_redo(self):
        h = _Harness(["VERDICT: PASS"])
        result = self._run(h)
        self.assertEqual(h.count("quality-gate"), 1)
        self.assertIn("<<formatter:ORIG>>", result)
        self.assertEqual(h.count("formatter-quality-redo"), 0)
        self.assertEqual(h.count("consolidator-quality-redo"), 0)

    def test_formatting_fail_reruns_formatter_only(self):
        h = _Harness(["PROBLEM: FORMATTING\nVERDICT: FAIL", "VERDICT: PASS"])
        result = self._run(h)
        self.assertEqual(h.count("quality-gate"), 2)            # gate re-ran once
        self.assertEqual(h.count("formatter-quality-redo"), 1)  # formatter redo
        self.assertEqual(h.count("consolidator-quality-redo"), 0)  # not analysis
        self.assertTrue(h.saw_qgfix("formatter-quality-redo"))
        self.assertIn("formatter-quality-redo", result)

    def test_analysis_fail_reconsolidates_then_reformats(self):
        h = _Harness(["PROBLEM: ANALYSIS\nVERDICT: FAIL", "VERDICT: PASS"])
        result = self._run(h)
        self.assertEqual(h.count("quality-gate"), 2)
        self.assertEqual(h.count("consolidator-quality-redo"), 1)
        self.assertEqual(h.count("formatter-after-reconsolidate"), 1)
        self.assertEqual(h.count("formatter-quality-redo"), 0)
        self.assertTrue(h.saw_qgfix("consolidator-quality-redo"))
        # the corrected corpus is re-formatted into the shipped deliverable
        self.assertIn("formatter-after-reconsolidate", result)

    def test_missing_problem_on_fail_routes_to_analysis(self):
        h = _Harness(["VERDICT: FAIL", "VERDICT: PASS"])  # no PROBLEM line
        result = self._run(h)
        self.assertEqual(h.count("consolidator-quality-redo"), 1)
        self.assertEqual(h.count("formatter-quality-redo"), 0)

    def test_one_redo_per_problem_type_bound(self):
        # Gate FAILs ANALYSIS every pass: the analysis redo fires once, then the
        # gate is consulted again, sees the redo is spent, and ships.
        h = _Harness(["PROBLEM: ANALYSIS\nVERDICT: FAIL"])  # repeats
        self._run(h)
        self.assertEqual(h.count("consolidator-quality-redo"), 1)  # bounded
        self.assertEqual(h.count("formatter-after-reconsolidate"), 1)
        self.assertEqual(h.count("quality-gate"), 2)               # not 3+

    def test_both_problem_types_each_redo_once(self):
        h = _Harness([
            "PROBLEM: ANALYSIS\nVERDICT: FAIL",
            "PROBLEM: FORMATTING\nVERDICT: FAIL",
            "VERDICT: PASS",
        ])
        self._run(h)
        self.assertEqual(h.count("consolidator-quality-redo"), 1)
        self.assertEqual(h.count("formatter-quality-redo"), 1)
        self.assertEqual(h.count("quality-gate"), 3)

    def test_broken_ships_without_redo(self):
        h = _Harness(["Corpus missing.\nVERDICT: BROKEN"])
        result = self._run(h)
        self.assertEqual(h.count("quality-gate"), 1)
        self.assertEqual(h.count("formatter-quality-redo"), 0)
        self.assertEqual(h.count("consolidator-quality-redo"), 0)
        self.assertIn("<<formatter:ORIG>>", result)


# ────────────────────────── doc / source backstops ──────────────────────────


class TestGateWiredAndDocumented(unittest.TestCase):
    def test_framework_spec_present_ora_and_vault(self):
        ora_spec = ORCH_DIR.parent / "frameworks" / "book" / "f-quality-gate.md"
        self.assertTrue(ora_spec.is_file(), "runtime f-quality-gate.md missing")
        vault_root = Path(
            os.environ.get("ORA_VAULT_PATH")
            or os.environ.get("ORA_VAULT")
            or (Path.home() / "Documents" / "vault"))
        vault_spec = vault_root / "Specification — F-Quality-Gate.md"
        if not vault_spec.is_file():
            vault_spec = vault_root / "Projects" / "Ora" / "Specification — F-Quality-Gate.md"
        # The vault is the canonical source; skip rather than fail if the vault
        # is not mounted in this environment.
        if vault_spec.parent.is_dir():
            self.assertTrue(vault_spec.is_file(),
                            "vault canonical pair missing")

    def test_gate_wired_into_both_gears(self):
        text = (ORCH_DIR / "boot.py").read_text(encoding="utf-8")
        self.assertIn("QUALITY_GATE_FRAMEWORK", text)
        self.assertIn("step6_5-quality-gate", text)   # gear 3
        self.assertIn("step8_6-quality-gate", text)   # gear 4
        self.assertIn('slot="verification"', text)    # dedicated judge slot
        self.assertIn("_parse_quality_gate_problem", text)

    def test_runtime_spec_remains_present_for_phase_1_5_sync(self):
        text = (
            ORCH_DIR.parent / "frameworks" / "book" / "f-quality-gate.md"
        ).read_text(encoding="utf-8")
        self.assertIn("F-QUALITY-GATE", text)
        self.assertIn("VERDICT:", text)


if __name__ == "__main__":
    unittest.main()
