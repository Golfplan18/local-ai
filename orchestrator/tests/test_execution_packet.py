"""Execution Review Phase 4 — ExecutionPacket + renderer + lane router + the
terminal construction wiring (evaluation-lane router, polymorphic output,
packet-to-review renderer). Mirrors the design packet §5 test plan and the four
judge conditions."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_ORCH = Path(__file__).resolve().parent.parent
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
import live_guard  # noqa: E402,F401 — quarantines durable oversight/telemetry writes

import execution_packet as ep  # noqa: E402
import risk_gate as rg  # noqa: E402
import tool_events as te  # noqa: E402


def _sig(**kw):
    base = {"any_mutation": False, "max_mutability": "read", "reads_present": False,
            "max_sensitivity": "public", "max_egress": "none", "gate_outcomes": {},
            "events_scanned": 0, "source_read_suspected": False,
            "source_read_channels": [], "source_candidate_reads": [],
            "source_candidate_reads_truncated": False}
    base.update(kw)
    return base


# ── §9 packet shape: tier-optional, every block reserved, flat frontmatter ────
class TestPacketShape(unittest.TestCase):
    def _pkt(self, **kw):
        return ep.build_execution_packet(signals=_sig(), context_pkg={"raw_prompt": "do x"},
                                         output_text="a deliverable", risk_tier="light", **kw)

    def test_frontmatter_is_flat_scalars_only(self):
        p = self._pkt()
        fm = p.frontmatter()
        self.assertEqual(sorted(fm), ["created", "modified", "output_type",
                                      "reversible", "risk_tier", "status",
                                      "tags", "task_id"])
        # no nested block leaks into the header
        for k in ("task", "execution", "verification", "evidence_lanes", "loop"):
            self.assertNotIn(k, fm)
        for v in fm.values():
            self.assertNotIsInstance(v, dict)

    def test_every_section9_block_reserved(self):
        p = self._pkt().to_dict()
        # blocks reserved even when unfilled, so later phases fill not retrofit
        self.assertIn("loop", p)
        self.assertIn("planning", p)          # None at light, but the key exists
        self.assertIn("confidence", p["verification"])
        self.assertIn("reviewer_a", p["verification"])
        self.assertIn("reviewer_b", p["verification"])
        for k in ("mode", "state_before", "state_after"):
            self.assertIn(k, p["execution"])   # §11 dirty-state reserved (Phase 5)

    def test_light_tier_has_no_planning(self):
        # §8/§9: a light packet legitimately has no planning stage — correct, not incomplete.
        self.assertIsNone(self._pkt().planning)

    def test_large_artifacts_capped_not_inlined(self):
        big = "x" * (ep._PRODUCER_CLAIM_CAP + 5000)
        p = ep.build_execution_packet(signals=_sig(), context_pkg={"raw_prompt": "y"},
                                      output_text=big, risk_tier="light")
        summary = p.execution["producer_claim"]["summary"]
        self.assertLessEqual(len(summary), ep._PRODUCER_CLAIM_CAP + 20)
        self.assertTrue(summary.endswith("[capped]"))

    def test_delta_is_a_reference_not_a_blob(self):
        p = ep.build_execution_packet(signals=_sig(any_mutation=True), context_pkg={},
                                      output_text="d", risk_tier="light",
                                      trace_ref="/traces/turn-1")
        self.assertEqual(p.execution["delta"]["ref"], "/traces/turn-1")

    def test_enforcement_model_recorded(self):
        self.assertEqual(self._pkt().execution["enforcement_model"], "in_harness")

    def test_reversible_derived_from_tier(self):
        self.assertFalse(ep.build_execution_packet(signals=_sig(), context_pkg={},
                         output_text="d", risk_tier="irreversible").reversible)
        self.assertTrue(ep.build_execution_packet(signals=_sig(), context_pkg={},
                        output_text="d", risk_tier="standard").reversible)


# ── §5 lane router — structurally separate evidence vs judgment ───────────────
class TestLaneRouter(unittest.TestCase):
    def test_mutation_yields_diff_evidence_lane(self):
        ev, ju = ep.route_lanes(_sig(any_mutation=True))
        self.assertEqual([(l.lane, l.target) for l in ev], [("diff_validate", "state_change")])
        self.assertEqual(ju, [])

    def test_source_read_yields_provenance_lane(self):
        ev, _ = ep.route_lanes(_sig(source_read_suspected=True))
        self.assertEqual([(l.lane, l.target) for l in ev], [("collect_provenance", "grounded_claims")])

    def test_both_signals_two_lanes(self):
        ev, _ = ep.route_lanes(_sig(any_mutation=True, source_read_suspected=True))
        self.assertEqual(len(ev), 2)

    def test_neither_signal_no_evidence_lane(self):
        ev, ju = ep.route_lanes(_sig())
        self.assertEqual(ev, [])
        self.assertEqual(ju, [])

    def test_judgment_lanes_from_mode_meta_only(self):
        _, ju = ep.route_lanes(_sig(any_mutation=True),
                               mode_meta={"judgment_targets": ["voice", " ", "persuasion"]})
        self.assertEqual([j.target for j in ju], ["voice", "persuasion"])

    def test_judgment_lane_has_no_verdict_field(self):
        # §5 structural separation: a JudgmentLane by CONSTRUCTION cannot hold a verdict.
        fields = ep.JudgmentLane("voice").__dataclass_fields__
        self.assertNotIn("verdict", fields)
        self.assertNotIn("sufficient", fields)


# ── sufficient tri-state — unfilled/empty is NOT vacuously passed (adv-L1-5) ──
class TestSufficientTriState(unittest.TestCase):
    def test_empty_lane_list_is_not_sufficient(self):
        self.assertFalse(ep.all_evidence_sufficient([]))

    def test_unfilled_lane_is_not_sufficient(self):
        self.assertFalse(ep.lane_is_sufficient(ep.EvidenceLane("t", "diff_validate")))
        self.assertFalse(ep.all_evidence_sufficient([ep.EvidenceLane("t", "diff_validate")]))

    def test_explicit_false_is_not_sufficient(self):
        self.assertFalse(ep.all_evidence_sufficient(
            [ep.EvidenceLane("t", "diff_validate", sufficient=False)]))

    def test_all_explicit_true_is_sufficient(self):
        self.assertTrue(ep.all_evidence_sufficient(
            [ep.EvidenceLane("t", "diff_validate", sufficient=True)]))

    def test_mixed_is_not_sufficient(self):
        self.assertFalse(ep.all_evidence_sufficient(
            [ep.EvidenceLane("a", "diff_validate", sufficient=True),
             ep.EvidenceLane("b", "collect_provenance")]))


# ── §12 renderer — evidence FIRST, producer claim LAST (unverified) ──────────
class TestRenderer(unittest.TestCase):
    def _render(self, **kw):
        p = ep.build_execution_packet(signals=_sig(**kw.pop("signals", {})),
                                      context_pkg=kw.pop("ctx", {"raw_prompt": "task text"}),
                                      output_text=kw.pop("out", "the produced claim"),
                                      risk_tier="light", **kw)
        return ep.render_for_review(p)

    def test_evidence_before_claim(self):
        r = self._render()
        self.assertLess(r.index("OBSERVED EVIDENCE"), r.index("UNVERIFIED PRODUCER CLAIM"))

    def test_producer_claim_labeled_unverified(self):
        self.assertIn("UNVERIFIED PRODUCER CLAIM", self._render())

    def test_missing_acceptance_criteria_is_loud(self):
        self.assertIn("NO ACCEPTANCE CRITERIA DECLARED", self._render())

    def test_unfilled_evidence_lane_never_reads_sufficient(self):
        r = self._render(signals={"any_mutation": True})
        self.assertIn("evidence not yet generated", r)
        self.assertNotIn("sufficient (via", r)

    def test_text_review_verdict_is_scope_labeled(self):
        r = self._render(ctx={"raw_prompt": "t", "execution_review": {"verdict": "PASS"}})
        self.assertIn("TEXT-REVIEW VERDICT (does not cover state changes or provenance)", r)
        # the raw PASS must not appear as an unqualified green check line
        self.assertNotIn("VERDICT: PASS", r)

    def test_unreviewed_status_shown_when_no_verdict(self):
        # Rev 1: a redo produced a new unreviewed deliverable → no verdict, but the
        # scoped status is surfaced (never a stale/absent silent claim).
        r = self._render(ctx={"raw_prompt": "t", "execution_review": {
            "verdict": None, "scope": "text_review",
            "status": "failed-then-redone-unreviewed"}})
        self.assertIn("TEXT-REVIEW STATUS", r)
        self.assertIn("failed-then-redone-unreviewed", r)
        self.assertNotIn("TEXT-REVIEW VERDICT", r)

    def test_uses_banner_fences_not_hash_headings(self):
        r = self._render()
        self.assertIn("=== OBSERVED EVIDENCE ===", r)
        self.assertNotIn("\n## ", r)

    def test_rendered_packet_drops_into_real_evaluator_prompt(self):
        # "the existing review logic accepts an ExecutionPacket" — proven by
        # feeding the rendered string into the REAL evaluator user-prompt shape,
        # WITHOUT editing any live in-gear site.
        import boot
        rendered = self._render(signals={"source_read_suspected": True},
                                ctx={"raw_prompt": "Q", "execution_review": {"verdict": "PASS"}})
        user_msg = (f"## ORIGINAL QUERY\n\nQ\n\n"
                    f"## ANALYST OUTPUT\n\n{rendered}\n\n"
                    "Evaluate per the universal seven-section contract.")
        self.assertIn("UNVERIFIED PRODUCER CLAIM", user_msg)
        self.assertTrue(hasattr(boot, "build_system_prompt_for_gear"))


# ── polymorphic seam — side-effect-free identity on str (adv-L1-6) ───────────
class TestFormatArtifactSeam(unittest.TestCase):
    def test_str_returned_unchanged(self):
        s = "a plain draft string"
        self.assertIs(ep._format_artifact_for_review(s), s)

    def test_str_branch_has_no_side_effects(self):
        # msi_run_gear4.invoke_real_gear4 is the one live path through this if it
        # is ever wired — the str branch must make no telemetry/fold calls.
        before = te.get_telemetry_health().get("failures")
        out = ep._format_artifact_for_review("draft")
        after = te.get_telemetry_health().get("failures")
        self.assertEqual(out, "draft")
        self.assertEqual(before, after)

    def test_packet_is_rendered(self):
        p = ep.build_execution_packet(signals=_sig(), context_pkg={"raw_prompt": "x"},
                                      output_text="claim", risk_tier="light")
        self.assertIn("UNVERIFIED PRODUCER CLAIM", ep._format_artifact_for_review(p))


# ── §6 consistency assertion — record-only, dormant on unknown (condition 3) ─
class TestConsistencyNote(unittest.TestCase):
    def test_text_plus_mutation_flags(self):
        self.assertIn("under-review", ep.consistency_note("text", _sig(any_mutation=True)))

    def test_text_plus_source_read_flags(self):
        self.assertIn("under-review", ep.consistency_note("text", _sig(source_read_suspected=True)))

    def test_execution_plus_neither_flags(self):
        self.assertIn("over-heavy", ep.consistency_note("execution", _sig()))

    def test_execution_with_contact_no_flag(self):
        self.assertIsNone(ep.consistency_note("execution", _sig(any_mutation=True)))

    def test_text_without_contact_no_flag(self):
        self.assertIsNone(ep.consistency_note("text", _sig()))

    def test_unknown_default_is_dormant(self):
        # P4: no mode declares output_type → the assertion fires on zero live turns.
        self.assertIsNone(ep.consistency_note("unknown", _sig(any_mutation=True, source_read_suspected=True)))
        self.assertIsNone(ep.consistency_note(None, _sig(any_mutation=True)))


# ── construction — guarded, never raises, observable failure (conds 1/2/4) ──
class TestConstruction(unittest.TestCase):
    def test_verdict_threaded_from_context_pkg(self):
        p = ep.build_execution_packet(signals=_sig(), context_pkg={"execution_review": {"verdict": "FAIL"}},
                                      output_text="d", risk_tier="light")
        self.assertEqual(p.verification["text_review_verdict"], "FAIL")
        self.assertIn("text_review", p.verification["scope"])

    def test_no_raw_verifier_text_in_verification(self):
        # condition 4: only the LABEL rides in; no raw verifier prose.
        er = {"verdict": "PASS", "raw": "long verifier prose " * 50}
        p = ep.build_execution_packet(signals=_sig(), context_pkg={"execution_review": er},
                                      output_text="d", risk_tier="light")
        self.assertNotIn("long verifier prose", json.dumps(p.verification))

    def test_output_type_is_raw_hint_never_from_observation(self):
        # declared unknown even though reality-contact observed — never rewritten.
        p = ep.build_execution_packet(signals=_sig(any_mutation=True, source_read_suspected=True),
                                      context_pkg={}, output_text="d", risk_tier="light",
                                      declared_output_type="unknown")
        self.assertEqual(p.output_type, "unknown")

    def test_findings_empty_class_untagged(self):
        # spec-L1-8: a P4 finding carries no class (findings is empty; no fabricated tag).
        p = ep.build_execution_packet(signals=_sig(), context_pkg={}, output_text="d", risk_tier="light")
        self.assertEqual(p.verification["findings"], [])

    def test_build_never_raises_on_malformed(self):
        # all-None inputs must not raise (they normalize to empties → a valid packet).
        out = ep.build_execution_packet(signals=None, context_pkg=None,
                                        output_text=None, risk_tier=None)
        self.assertIsInstance(out, (ep.ExecutionPacket, type(None)))
        # a well-formed call returns a packet
        self.assertIsInstance(ep.build_execution_packet(signals=_sig(), context_pkg={},
                              output_text="d", risk_tier="light"), ep.ExecutionPacket)

    def test_construct_and_write_skips_without_trace(self):
        self.assertIsNone(ep.construct_and_write(signals=_sig(), context_pkg={},
                          output_text="d", risk_tier="light", trace_dir=None))

    def test_construct_and_write_skips_when_fold_failed(self):
        # signals is None means the fold failed — no packet describes a turn whose
        # reality-contact was never successfully observed (adversarial pre-check fold).
        d = tempfile.mkdtemp()
        self.assertIsNone(ep.construct_and_write(signals=None, context_pkg={},
                          output_text="d", risk_tier="light", trace_dir=d))
        self.assertFalse(os.path.exists(os.path.join(d, ep._PACKET_FILENAME)))

    def test_high_risk_tier_is_reversible(self):
        # §6/§9: `reversible` gates post-hoc routing; only 'irreversible' tier is
        # non-reversible. high-risk (with rollback) is reversible.
        self.assertTrue(ep.build_execution_packet(signals=_sig(), context_pkg={},
                        output_text="d", risk_tier="high-risk").reversible)
        self.assertFalse(ep.build_execution_packet(signals=_sig(), context_pkg={},
                         output_text="d", risk_tier="irreversible").reversible)

    def test_construct_and_write_skips_empty_output(self):
        d = tempfile.mkdtemp()
        self.assertIsNone(ep.construct_and_write(signals=_sig(), context_pkg={},
                          output_text="   ", risk_tier="light", trace_dir=d))
        self.assertFalse(os.path.exists(os.path.join(d, ep._PACKET_FILENAME)))

    def test_construct_and_write_writes_git_only_tier(self):
        d = tempfile.mkdtemp()
        ref = ep.construct_and_write(signals=_sig(any_mutation=True), context_pkg={"raw_prompt": "p"},
                                     output_text="deliverable", risk_tier="standard", trace_dir=d)
        self.assertEqual(ref, os.path.join(d, ep._PACKET_FILENAME))
        self.assertTrue(os.path.exists(ref))
        pkt = json.load(open(ref))
        # Phase 7: the build-time default §14 tier is git_only (was the "trace_local" placeholder);
        # the common self-evidencing path never promotes above git_only. Nothing reads this value.
        self.assertEqual(pkt["persistence"]["tier"], "git_only")

    def test_write_failure_is_observable(self):
        # a caught write failure stamps EXACTLY ONE marker (never silently vanishes).
        p = ep.build_execution_packet(signals=_sig(), context_pkg={}, output_text="d", risk_tier="light")
        before = te.get_telemetry_health()["failures"]
        ref = ep.write_packet(p, "/nonexistent-root-\x00/definitely/cannot/write")
        after = te.get_telemetry_health()["failures"]
        self.assertIsNone(ref)
        self.assertEqual(after, before + 1)  # exactly one stamp, not swallowed


# ── construction failures are OBSERVABLE, skips are NOT (Rev 1, F2) ──────────
class TestConstructionFailureObservable(unittest.TestCase):
    def test_build_exception_stamps_exactly_one_marker(self):
        # A build exception (here: route_lanes raises) must NOT be a silent None —
        # it stamps EXACTLY ONE observable marker while never interrupting the turn.
        before = te.get_telemetry_health()["failures"]
        with mock.patch.object(ep, "route_lanes", side_effect=RuntimeError("boom")):
            out = ep.build_execution_packet(signals=_sig(), context_pkg={},
                                            output_text="d", risk_tier="light")
        after = te.get_telemetry_health()["failures"]
        self.assertIsNone(out)
        self.assertEqual(after, before + 1)

    def test_construct_and_write_build_exception_stamps_exactly_one(self):
        # Build fails inside construct_and_write: build stamps once, write_packet
        # short-circuits on the None packet (no second stamp), wrapper completes.
        d = tempfile.mkdtemp()
        before = te.get_telemetry_health()["failures"]
        with mock.patch.object(ep, "route_lanes", side_effect=RuntimeError("boom")):
            ref = ep.construct_and_write(signals=_sig(), context_pkg={},
                                         output_text="d", risk_tier="light", trace_dir=d)
        after = te.get_telemetry_health()["failures"]
        self.assertIsNone(ref)
        self.assertFalse(os.path.exists(os.path.join(d, ep._PACKET_FILENAME)))
        self.assertEqual(after, before + 1)  # exactly one stamp, no double-count

    def test_construct_and_write_write_failure_stamps_exactly_one(self):
        # Build succeeds, WRITE fails (json.dump raises): write_packet stamps once,
        # the wrapper try completes normally — no second stamp.
        d = tempfile.mkdtemp()
        before = te.get_telemetry_health()["failures"]
        with mock.patch.object(ep.json, "dump", side_effect=OSError("disk full")):
            ref = ep.construct_and_write(signals=_sig(), context_pkg={"raw_prompt": "p"},
                                         output_text="d", risk_tier="light", trace_dir=d)
        after = te.get_telemetry_health()["failures"]
        self.assertIsNone(ref)
        self.assertEqual(after, before + 1)

    def test_construct_and_write_wrapper_failure_stamps_exactly_one(self):
        # An unexpected error in the wrapper body (build_execution_packet re-raises)
        # is caught by the wrapper's own except and stamped exactly once.
        d = tempfile.mkdtemp()
        before = te.get_telemetry_health()["failures"]
        with mock.patch.object(ep, "build_execution_packet",
                               side_effect=RuntimeError("boom")):
            ref = ep.construct_and_write(signals=_sig(), context_pkg={},
                                         output_text="d", risk_tier="light", trace_dir=d)
        after = te.get_telemetry_health()["failures"]
        self.assertIsNone(ref)
        self.assertEqual(after, before + 1)

    def test_intentional_skip_stamps_no_marker(self):
        # No trace dir / empty output / no signals are INTENTIONAL skips — they
        # return None WITHOUT a failure marker (distinct from a build exception).
        before = te.get_telemetry_health()["failures"]
        self.assertIsNone(ep.construct_and_write(signals=_sig(), context_pkg={},
                          output_text="d", risk_tier="light", trace_dir=None))
        self.assertIsNone(ep.construct_and_write(signals=_sig(), context_pkg={},
                          output_text="  ", risk_tier="light", trace_dir=tempfile.mkdtemp()))
        self.assertIsNone(ep.construct_and_write(signals=None, context_pkg={},
                          output_text="d", risk_tier="light", trace_dir=tempfile.mkdtemp()))
        after = te.get_telemetry_health()["failures"]
        self.assertEqual(after, before)  # skips are not failures


# ── risk_gate integration — single fold, output_type + consistency recorded ─
class TestRiskGateWiring(unittest.TestCase):
    def _trace_with(self, *events):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "tool-events.jsonl"), "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        return d

    def test_return_carries_output_type_and_consistency(self):
        d = self._trace_with({"event": "tool", "action": "web_fetch", "mutability": "read",
                              "reads": [{"what": "u", "where": "network"}],
                              "exit": {"ok": True}, "sensitivity": "public"})
        r = rg.record_route_observed(d, risk_tier="standard",
                                     output_text="a grounded answer", declared_output_type="text")
        self.assertEqual(sorted(r), ["consistency", "divergence", "output_type", "signals"])
        self.assertEqual(r["output_type"], "text")
        self.assertIn("under-review", r["consistency"])

    def test_unknown_declared_is_dormant(self):
        d = self._trace_with({"event": "tool", "action": "web_fetch", "mutability": "read",
                              "reads": [{"what": "u", "where": "network"}],
                              "exit": {"ok": True}, "sensitivity": "public"})
        r = rg.record_route_observed(d, risk_tier="standard", output_text="x")
        self.assertEqual(r["output_type"], "unknown")
        self.assertIsNone(r["consistency"])

    def test_record_never_raises_and_returns_output_type_on_error(self):
        # a bad turn_key should not raise; output_type still echoes back.
        r = rg.record_route_observed(object(), risk_tier="light", declared_output_type="text")
        self.assertEqual(r["output_type"], "text")


# ── tool_events keep-set — output_type + consistency survive truncation ──────
class TestKeepSetSurvival(unittest.TestCase):
    def test_keepset_includes_output_type_and_consistency(self):
        # the route_observed verdict fields must survive a byte-truncated event.
        import inspect
        src = inspect.getsource(te.record)
        self.assertIn('"output_type"', src)
        self.assertIn('"consistency"', src)


# ── Phase 6: populate_loop_fields fills the reserved §9 blocks (fill, not retrofit) ──
class TestPopulateLoopFields(unittest.TestCase):
    def _pkt(self, tier="standard"):
        return ep.build_execution_packet(
            signals=_sig(any_mutation=True), output_text="the deliverable",
            context_pkg={"raw_prompt": "do x", "acceptance_criteria": "AC-1",
                         "evidence_contract": {"required_standard_checks": ["build"]}},
            risk_tier=tier)

    def test_planning_block_from_context_threads_criteria_and_contract(self):
        plan = ep.planning_block_from_context(
            {"acceptance_criteria": "AC-1", "evidence_contract": {"x": 1}})
        self.assertEqual(plan["converged_brief"]["acceptance_criteria"], "AC-1")
        self.assertEqual(plan["evidence_contract"], {"x": 1})

    def test_fills_each_reserved_block(self):
        p = self._pkt()
        self.assertIsNone(p.planning)          # reserved-empty before Phase 6
        ep.populate_loop_fields(
            p,
            planning=ep.planning_block_from_context(
                {"acceptance_criteria": "AC-1", "evidence_contract": {"required_standard_checks": ["build"]}}),
            verification={"reviewer_a": {"endpoint": "v", "family": "gpt"},
                          "confidence": 0.6,
                          "findings": [{"severity": "low", "class": "execution_level", "description": "n"}],
                          "invented_tests": [{"kind": "acceptance", "name": "t"}]},
            execution={"mode": "review_dirty_diff", "state_before": {"head": "abc"},
                       "state_after": {"head": "def"}, "enforcement_model": "orchestrated"},
            loop={"iteration": 0, "stop_condition": "criteria_met"})
        self.assertEqual(p.planning["converged_brief"]["acceptance_criteria"], "AC-1")
        self.assertEqual(p.verification["reviewer_a"]["family"], "gpt")
        self.assertEqual(p.verification["confidence"], 0.6)
        self.assertEqual(p.execution["mode"], "review_dirty_diff")
        self.assertEqual(p.execution["enforcement_model"], "orchestrated")
        self.assertEqual(p.loop["stop_condition"], "criteria_met")
        self.assertEqual(p.status, "converged")

    def test_preserves_phase4_verification_and_execution_fields(self):
        # Thread a text-review verdict via context_pkg['execution_review'] (Phase 4).
        p = ep.build_execution_packet(
            signals=_sig(any_mutation=True), output_text="deliverable",
            context_pkg={"raw_prompt": "x",
                         "execution_review": {"verdict": "PASS", "scope": "text_review"}},
            risk_tier="standard")
        pre_claim = p.execution["producer_claim"]["summary"]
        ep.populate_loop_fields(p, verification={"reviewer_a": {"endpoint": "v"}, "confidence": 0.5},
                                execution={"mode": "review_dirty_diff",
                                           "enforcement_model": "orchestrated"})
        # Phase-4 text-review verdict/scope preserved (the judgment-lane review, §5).
        self.assertEqual(p.verification["text_review_verdict"], "PASS")
        self.assertTrue(p.verification["scope"].startswith("text_review"))
        # Phase-6 fields layered on top.
        self.assertEqual(p.verification["reviewer_a"]["endpoint"], "v")
        # Phase-4 producer_claim + delta preserved (Phase 6 owns only mode/state_*/enforcement).
        self.assertEqual(p.execution["producer_claim"]["summary"], pre_claim)
        self.assertIn("delta", p.execution)
        self.assertEqual(p.execution["enforcement_model"], "orchestrated")

    def test_reversible_flag_is_not_recomputed(self):
        # high-risk == reversible:true is the §6 tier-boundary gate — NOT recomputed.
        p = ep.build_execution_packet(signals=_sig(any_mutation=True), output_text="x",
                                      context_pkg={"raw_prompt": "x"}, risk_tier="high-risk")
        self.assertTrue(p.reversible)
        ep.populate_loop_fields(p, loop={"iteration": 0, "stop_condition": "criteria_met"})
        self.assertTrue(p.reversible)   # untouched

    def test_light_planning_stays_none(self):
        p = self._pkt(tier="light")
        ep.populate_loop_fields(p, planning=None,
                                loop={"iteration": 0, "stop_condition": None})
        self.assertIsNone(p.planning)   # §9 tier-optional — correct, not incomplete
        # renderer then fires the LOUD absence fence.
        self.assertIn("NO ACCEPTANCE CRITERIA DECLARED", ep.render_for_review(p))

    def test_render_shows_populated_criteria(self):
        p = self._pkt()
        ep.populate_loop_fields(p, planning=ep.planning_block_from_context(
            {"acceptance_criteria": "AC-1"}))
        r = ep.render_for_review(p)
        self.assertIn("ACCEPTANCE CRITERIA", r)
        self.assertIn("AC-1", r)
        self.assertNotIn("NO ACCEPTANCE CRITERIA DECLARED", r)

    def test_escalated_status_from_loop(self):
        p = self._pkt()
        ep.populate_loop_fields(p, loop={"iteration": 2,
                                         "stop_condition": "max_iterations_escalated"})
        self.assertEqual(p.status, "escalated")

    def test_owed_evidence_lane_is_not_sufficient(self):
        # an unfilled (owed) diff_validate lane must never read as sufficient (§16-2).
        p = self._pkt()
        self.assertTrue(any(l.lane == "diff_validate" for l in p.evidence_lanes))
        self.assertFalse(ep.all_evidence_sufficient(p.evidence_lanes))

    def test_none_packet_is_safe(self):
        self.assertIsNone(ep.populate_loop_fields(None, loop={"iteration": 0}))


if __name__ == "__main__":
    unittest.main()
