"""Tests for the per-turn trace manifest (Trace Walk Chunk 0).

Covers the pipeline_trace manifest layer (skeleton at start_trace, the
idempotent fail-open finalizer, honest kind/status derivation per path
class, actual-step filtering, trace refs), the conversation-side
``trace_ref`` stamp, gitignore coverage, and the server generator wrapper
(short-circuit / error / disconnect finalization) with the pipeline body
stubbed — no model calls.

Run::

    /opt/homebrew/bin/python3 -m unittest orchestrator.tests.test_trace_manifest -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import live_guard  # noqa: E402,F401  — arm the oversight write quarantine

# NOTE: running the suite from a worktree other than ~/ora requires
# ``ORA_HOME`` exported to that worktree's root (as start.sh does in
# production) — server.py's WORKSPACE and several other modules default to
# the literal ``~/ora`` otherwise, which can cross-contaminate sys.modules
# with the live checkout's copy of a same-named module during full-suite
# discovery. Do NOT work around this here with sys.modules eviction: doing
# so swaps the module OBJECT out from under any earlier-collected test
# fixture that already patched attributes on it (observed regression:
# test_conversations_filter.py / test_modal_endpoints.py silently read the
# live default sessions root instead of their tempdir because server.py's
# lazy per-request ``from conversation_memory import ...`` resolved a
# different object than the one the test patched). Set ORA_HOME instead.
import pipeline_trace  # noqa: E402
import conversation_memory  # noqa: E402


class TraceManifestBase(unittest.TestCase):
    """Redirect TRACE_ROOT into a tempdir; no test touches the live tree."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "pipeline-traces")
        os.makedirs(self.root)
        patcher = mock.patch.object(pipeline_trace, "TRACE_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    # -- helpers -----------------------------------------------------------

    def start(self, conv="conv-a", **kw):
        return pipeline_trace.start_trace(conv, raw_input="hello", **kw)

    def manifest(self, trace_dir):
        with open(os.path.join(trace_dir, "trace-manifest.json")) as f:
            return json.load(f)

    def touch_step(self, trace_dir, stem, payload=None):
        pipeline_trace.write_step(trace_dir, stem, payload or {"x": 1})


class TestSkeleton(TraceManifestBase):
    def test_start_trace_writes_manifest_skeleton(self):
        d = self.start()
        m = self.manifest(d)
        self.assertEqual(m["schema_version"], 1)
        self.assertEqual(m["trace_kind"], "unknown")
        self.assertEqual(m["terminal_status"], "open")
        self.assertEqual(m["conversation_id"], "conv-a")
        self.assertEqual(m["turn_timestamp_utc"], os.path.basename(d))
        self.assertIsNone(m["gear"])
        self.assertIsNone(m["mode"])
        self.assertIsNone(m["parent_trace_ref"])
        self.assertEqual(m["child_trace_refs"], [])
        self.assertEqual(m["retention_state"], "default")
        self.assertEqual(m["redaction_level"], "default")
        self.assertIsNone(m["finalized_at"])

    def test_private_tag_sets_redaction_level(self):
        d = self.start(conversation_tag="private")
        self.assertEqual(self.manifest(d)["redaction_level"], "private")

    def test_stealth_produces_no_files(self):
        d = pipeline_trace.start_trace("conv-s", stealth=True)
        self.assertIsNone(d)
        self.assertEqual(os.listdir(self.root), [])

    def test_global_disable_produces_no_files(self):
        with mock.patch.dict(os.environ, {"ORA_PIPELINE_TRACE": "off"}):
            d = pipeline_trace.start_trace("conv-x")
        self.assertIsNone(d)
        self.assertEqual(os.listdir(self.root), [])

    def test_no_tmp_residue(self):
        d = self.start()
        residue = [n for n in os.listdir(d) if n.endswith(".tmp")]
        self.assertEqual(residue, [])


class TestTraceRef(TraceManifestBase):
    def test_ref_is_relative_conv_slash_ts(self):
        d = self.start("conv-r")
        ref = pipeline_trace.trace_ref_for_dir(d)
        self.assertEqual(ref, f"conv-r/{os.path.basename(d)}")
        self.assertNotIn(os.sep if os.sep != "/" else "\\", ref)

    def test_none_and_outside_root(self):
        self.assertIsNone(pipeline_trace.trace_ref_for_dir(None))
        self.assertIsNone(pipeline_trace.trace_ref_for_dir(""))
        self.assertIsNone(pipeline_trace.trace_ref_for_dir(self.tmp.name))


class TestFinalizeStatusAndKind(TraceManifestBase):
    """One test per turn-path class (design §Tests: simulate the groups)."""

    def test_metadata_only_short_circuit(self):
        # Runtime command, resolution continuation, framework paths: the
        # turn dir holds metadata + manifest only.
        d = self.start()
        pipeline_trace.finalize_manifest(d, kind="runtime_command")
        m = self.manifest(d)
        self.assertEqual(m["trace_kind"], "runtime_command")
        self.assertEqual(m["terminal_status"], "short_circuit")
        self.assertEqual(m["expected_steps"], [])
        self.assertEqual(m["actual_steps"], [])
        self.assertIsNotNone(m["finalized_at"])

    def test_caught_error_path_is_error_not_short_circuit(self):
        # Design-gate condition 1: paths that catch, yield error, and
        # return must finalize as error.
        d = self.start()
        pipeline_trace.finalize_manifest(d, kind="runtime_command",
                                         status_hint="error")
        self.assertEqual(self.manifest(d)["terminal_status"], "error")

    def test_no_endpoint_error(self):
        d = self.start()
        pipeline_trace.finalize_manifest(d, kind="no_endpoint_error",
                                         status_hint="error")
        m = self.manifest(d)
        self.assertEqual(m["trace_kind"], "no_endpoint_error")
        self.assertEqual(m["terminal_status"], "error")

    def test_clarification_pending_is_paused_not_abandoned(self):
        # Design-gate condition 2.
        d = self.start()
        self.touch_step(d, "step1-phase-a")
        self.touch_step(d, "step1-pre-routing")
        pipeline_trace.finalize_manifest(d, kind="clarification_pending",
                                         status_hint="paused")
        m = self.manifest(d)
        self.assertEqual(m["terminal_status"], "paused")
        self.assertEqual(m["expected_steps"], [])
        self.assertEqual(m["actual_steps"],
                         ["step1-phase-a", "step1-pre-routing"])

    def test_direct_bypass_short_circuit(self):
        d = self.start()
        self.touch_step(d, "step1-phase-a")
        self.touch_step(d, "step1-pre-routing")
        pipeline_trace.finalize_manifest(d, kind="direct")
        m = self.manifest(d)
        self.assertEqual(m["trace_kind"], "direct")
        self.assertEqual(m["terminal_status"], "short_circuit")
        self.assertEqual(m["expected_steps"],
                         ["step1-phase-a", "step1-pre-routing"])

    def test_abandoned_mid_pipeline(self):
        # step1 landed, no step-health, kind chat, no hints → abandoned;
        # the bare "chat" kind survives (gear never known).
        d = self.start()
        self.touch_step(d, "step1-phase-a")
        self.touch_step(d, "step1-pre-routing")
        pipeline_trace.finalize_manifest(d, kind="chat")
        m = self.manifest(d)
        self.assertEqual(m["trace_kind"], "chat")
        self.assertEqual(m["terminal_status"], "abandoned")

    def test_completed_gear4_via_step_health(self):
        d = self.start()
        for s in ("step1-phase-a", "step1-pre-routing", "step2-context",
                  "step3-depth", "step3-breadth", "step4-eval-of-depth",
                  "step4-eval-of-breadth", "step5-revised-depth",
                  "step5-revised-breadth", "step7-consolidated",
                  "step8-formatted"):
            self.touch_step(d, s)
        pipeline_trace.write_step_health(d, {"step3": (True, "ok")}, 4, [])
        pipeline_trace.finalize_manifest(d, kind="chat")
        m = self.manifest(d)
        self.assertEqual(m["trace_kind"], "chat-gear4")
        self.assertEqual(m["terminal_status"], "completed")
        self.assertEqual(m["gear"], 4)
        self.assertEqual(m["expected_steps"],
                         sorted(pipeline_trace._REQUIRED_STEPS_BY_GEAR[4]))
        self.assertEqual(set(m["expected_steps"]) - set(m["actual_steps"]),
                         set())

    def test_completed_gear2_without_step_health(self):
        # Gear 1/2 never writes step-health — the explicit completed hint
        # + gear from turn state must classify honestly (never abandoned).
        d = self.start()
        self.touch_step(d, "step1-phase-a")
        self.touch_step(d, "step1-pre-routing")
        self.touch_step(d, "step2-context")
        pipeline_trace.finalize_manifest(d, kind="chat",
                                         status_hint="completed", gear=2)
        m = self.manifest(d)
        self.assertEqual(m["trace_kind"], "chat-gear2")
        self.assertEqual(m["terminal_status"], "completed")
        self.assertEqual(m["expected_steps"],
                         ["step1-phase-a", "step1-pre-routing",
                          "step2-context"])

    def test_error_hint_beats_step_health(self):
        # A turn that completed its gear but crashed on the way out is an
        # error, not completed.
        d = self.start()
        pipeline_trace.write_step_health(d, {}, 3, [])
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="error")
        self.assertEqual(self.manifest(d)["terminal_status"], "error")

    def test_mid_pipeline_risk_hold(self):
        # _run_pipeline_from_step2's hold return reassigns the kind.
        d = self.start()
        self.touch_step(d, "step1-phase-a")
        self.touch_step(d, "step1-pre-routing")
        self.touch_step(d, "step2-context")
        pipeline_trace.finalize_manifest(d, kind="risk_hold", gear=4)
        m = self.manifest(d)
        self.assertEqual(m["trace_kind"], "risk_hold")
        self.assertEqual(m["terminal_status"], "short_circuit")
        self.assertEqual(m["expected_steps"], [])


class TestExpectedActualDerivation(TraceManifestBase):
    def test_derived_artifacts_filtered_from_actual(self):
        # Design-gate condition 5: step-health / visual hook / visual
        # emissions / cost-summary are derived, never steps.
        d = self.start()
        self.touch_step(d, "step1-phase-a")
        self.touch_step(d, "step-visual-hook")
        self.touch_step(d, "step-visual-emissions")
        pipeline_trace.write_step_health(d, {}, 3, [])
        pipeline_trace._atomic_write_json(
            os.path.join(d, "cost-summary.json"), {"total": 0})
        pipeline_trace.finalize_manifest(d, kind="chat")
        m = self.manifest(d)
        self.assertEqual(m["actual_steps"], ["step1-phase-a"])
        self.assertEqual(m["derived_artifacts"],
                         ["cost-summary", "step-health",
                          "step-visual-emissions", "step-visual-hook"])

    def test_observed_only_steps_stay_in_actual_but_never_expected(self):
        # Verifier cycles / claim verification / quality gate / web
        # consultation are observed-only (design Q3 as modified): present
        # in actual_steps, never in expected_steps.
        d = self.start()
        observed = ["step2-web-consultation", "step4.5-claim-verification",
                    "step5.5-unflagged-scan", "step6-verifier-cycle-1",
                    "step6-verifier-cycle-2", "step6_5-quality-gate"]
        for s in observed:
            self.touch_step(d, s)
        pipeline_trace.write_step_health(d, {}, 3, [])
        pipeline_trace.finalize_manifest(d, kind="chat")
        m = self.manifest(d)
        for s in observed:
            self.assertIn(s, m["actual_steps"])
            self.assertNotIn(s, m["expected_steps"])

    def test_clarification_resume_expects_no_step1(self):
        # The resume reuses the paused turn's stored step1 dict; expecting
        # step1 files would manufacture a false missing-step warning.
        d = self.start()
        pipeline_trace.write_step_health(d, {}, 3, [])
        pipeline_trace.finalize_manifest(d, kind="clarification_resume")
        m = self.manifest(d)
        self.assertEqual(m["expected_steps"],
                         ["step2-context", "step3-depth", "step4-eval",
                          "step5-revised"])

    def test_mode_from_pre_routing_when_no_hint(self):
        d = self.start()
        self.touch_step(d, "step1-pre-routing",
                        {"dispatched_mode_id": "root-cause-analysis"})
        pipeline_trace.finalize_manifest(d, kind="chat")
        self.assertEqual(self.manifest(d)["mode"], "root-cause-analysis")

    def test_explicit_mode_hint_wins(self):
        d = self.start()
        self.touch_step(d, "step1-pre-routing",
                        {"dispatched_mode_id": "other"})
        pipeline_trace.finalize_manifest(d, kind="chat", mode="cui-bono")
        self.assertEqual(self.manifest(d)["mode"], "cui-bono")


class TestGearDegradeAndContingencies(TraceManifestBase):
    """Adversarial-review findings (2026-07-11): run_gear4 silently
    degrading to run_gear3, and the two documented fallback branches that
    complete with a smaller step footprint than the gear's normal table.
    """

    def test_step_health_gear_wins_over_stale_predispatch_hint(self):
        # run_gear4 falls back to run_gear3 internally on unrecoverable
        # analyst streams; the caller's turn_state["gear"] was stamped
        # BEFORE dispatch and never corrected. step-health.json (written
        # last, by whichever gear function actually completed) must win.
        d = self.start()
        for s in ("step1-phase-a", "step1-pre-routing", "step2-context",
                  "step3-depth", "step4-eval", "step5-revised"):
            self.touch_step(d, s)
        pipeline_trace.write_step_health(d, {}, 3, [])
        pipeline_trace.finalize_manifest(d, kind="chat", gear=4)
        m = self.manifest(d)
        self.assertEqual(m["gear"], 3)
        self.assertEqual(m["trace_kind"], "chat-gear3")
        self.assertEqual(
            set(m["expected_steps"]) - set(m["actual_steps"]), set())

    def test_predispatch_hint_used_when_no_step_health(self):
        # Gear 1/2 never writes step-health.json — the caller's hint is
        # the only signal and must still be honored (no regression).
        d = self.start()
        pipeline_trace.finalize_manifest(d, kind="chat",
                                         status_hint="completed", gear=2)
        self.assertEqual(self.manifest(d)["gear"], 2)

    def test_gear3_single_analyst_fallback_satisfies_requirement(self):
        d = self.start()
        for s in ("step1-phase-a", "step1-pre-routing", "step2-context",
                  "step3-single-analyst-fallback"):
            self.touch_step(d, s)
        pipeline_trace.write_step_health(d, {}, 3, [])
        pipeline_trace.finalize_manifest(d, kind="chat")
        m = self.manifest(d)
        self.assertEqual(m["gear"], 3)
        self.assertNotIn("step3-depth", m["expected_steps"])
        self.assertNotIn("step4-eval", m["expected_steps"])
        self.assertNotIn("step5-revised", m["expected_steps"])
        self.assertIn("step3-single-analyst-fallback", m["expected_steps"])
        self.assertEqual(
            set(m["expected_steps"]) - set(m["actual_steps"]), set())

    def test_gear4_external_consolidation_handoff_satisfies_requirement(self):
        d = self.start()
        for s in ("step1-phase-a", "step1-pre-routing", "step2-context",
                  "step3-depth", "step3-breadth", "step4-eval-of-depth",
                  "step4-eval-of-breadth", "step5-revised-depth",
                  "step5-revised-breadth", "step7-external-consolidation-handoff"):
            self.touch_step(d, s)
        pipeline_trace.write_step_health(d, {}, 4, [])
        pipeline_trace.finalize_manifest(d, kind="chat")
        m = self.manifest(d)
        self.assertEqual(m["gear"], 4)
        self.assertNotIn("step7-consolidated", m["expected_steps"])
        self.assertNotIn("step8-formatted", m["expected_steps"])
        self.assertIn("step7-external-consolidation-handoff",
                      m["expected_steps"])
        self.assertEqual(
            set(m["expected_steps"]) - set(m["actual_steps"]), set())

    def test_normal_gear4_completion_unaffected_by_contingency_logic(self):
        # No fallback marker present — the normal full table still applies.
        d = self.start()
        for s in ("step1-phase-a", "step1-pre-routing", "step2-context",
                  "step3-depth", "step3-breadth", "step4-eval-of-depth",
                  "step4-eval-of-breadth", "step5-revised-depth",
                  "step5-revised-breadth", "step7-consolidated",
                  "step8-formatted"):
            self.touch_step(d, s)
        pipeline_trace.write_step_health(d, {}, 4, [])
        pipeline_trace.finalize_manifest(d, kind="chat")
        m = self.manifest(d)
        self.assertIn("step7-consolidated", m["expected_steps"])
        self.assertIn("step8-formatted", m["expected_steps"])
        self.assertNotIn("step7-external-consolidation-handoff",
                         m["expected_steps"])


class TestFinalizeLifecycle(TraceManifestBase):
    def test_idempotent_double_finalize(self):
        d = self.start()
        self.touch_step(d, "step1-phase-a")
        pipeline_trace.finalize_manifest(d, kind="direct")
        first = self.manifest(d)
        pipeline_trace.finalize_manifest(d, kind="direct")
        second = self.manifest(d)
        first.pop("finalized_at"); second.pop("finalized_at")
        self.assertEqual(first, second)

    def test_refinalize_preserves_unowned_fields(self):
        d = self.start()
        m = self.manifest(d)
        m["retention_state"] = "pinned"
        m["child_trace_refs"] = ["conv-a/x"]
        pipeline_trace._atomic_write_json(
            os.path.join(d, "trace-manifest.json"), m)
        pipeline_trace.finalize_manifest(d, kind="direct")
        m2 = self.manifest(d)
        self.assertEqual(m2["retention_state"], "pinned")
        self.assertEqual(m2["child_trace_refs"], ["conv-a/x"])

    def test_parent_trace_ref_recorded_and_preserved(self):
        d = self.start()
        pipeline_trace.finalize_manifest(d, kind="clarification_resume",
                                         parent_trace_ref="conv-a/20260101T000000Z")
        self.assertEqual(self.manifest(d)["parent_trace_ref"],
                         "conv-a/20260101T000000Z")
        # A later re-finalize without the arg must not erase it.
        pipeline_trace.finalize_manifest(d, kind="clarification_resume")
        self.assertEqual(self.manifest(d)["parent_trace_ref"],
                         "conv-a/20260101T000000Z")

    def test_finalize_rebuilds_when_skeleton_missing(self):
        # Pre-manifest trace dirs (or a clobbered skeleton) still finalize.
        d = self.start()
        os.remove(os.path.join(d, "trace-manifest.json"))
        pipeline_trace.finalize_manifest(d, kind="runtime_command")
        m = self.manifest(d)
        self.assertEqual(m["conversation_id"], "conv-a")
        self.assertEqual(m["turn_timestamp_utc"], os.path.basename(d))
        self.assertEqual(m["terminal_status"], "short_circuit")

    def test_fail_open(self):
        # None and nonexistent dirs must never raise.
        pipeline_trace.finalize_manifest(None, kind="chat")
        pipeline_trace.finalize_manifest(
            os.path.join(self.root, "nope", "nothere"), kind="chat")

    def test_no_tmp_residue_after_finalize(self):
        d = self.start()
        pipeline_trace.finalize_manifest(d, kind="direct")
        residue = [n for n in os.listdir(d) if n.endswith(".tmp")]
        self.assertEqual(residue, [])


class TestGitignoreCoverage(unittest.TestCase):
    def test_manifest_path_is_gitignored(self):
        repo = ORCHESTRATOR.parent
        if not (repo / ".git").exists():  # pragma: no cover
            self.skipTest("not a git checkout")
        probe = "data/pipeline-traces/conv/20260101T000000Z/trace-manifest.json"
        rc = subprocess.run(
            ["git", "check-ignore", "-q", probe],
            cwd=str(repo), capture_output=True,
        ).returncode
        self.assertEqual(rc, 0, f"{probe} is not gitignored")


class TestConversationSideJoin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_trace_ref_stamped_on_assistant_turn(self):
        path = conversation_memory.save_turn_spatial_state(
            "conv-j", "hi", "hello",
            sessions_root=Path(self.tmp.name),
            trace_ref="conv-j/20260101T000000Z",
        )
        data = json.loads(Path(path).read_text())
        user_turn, assistant_turn = data["messages"][-2:]
        self.assertEqual(assistant_turn["role"], "assistant")
        self.assertEqual(assistant_turn["trace_ref"],
                         "conv-j/20260101T000000Z")
        self.assertNotIn("trace_ref", user_turn)

    def test_trace_ref_defaults_null(self):
        # Stealth / untraced turns: the key is present, value null.
        path = conversation_memory.save_turn_spatial_state(
            "conv-k", "hi", "hello", sessions_root=Path(self.tmp.name),
        )
        data = json.loads(Path(path).read_text())
        self.assertIsNone(data["messages"][-1]["trace_ref"])


class TestServerStreamWrapper(unittest.TestCase):
    """The generator-level wrapper finalizes on every exit path.

    Uses the real _pipeline_stream with the runtime-command short-circuit
    (run_runtime_command stubbed) — no model calls, no endpoint needed.
    """

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ORCHESTRATOR.parent / "server"))
        import server  # noqa: WPS433
        cls.S = server

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "pipeline-traces")
        os.makedirs(self.root)
        # The server imports ``orchestrator.pipeline_trace``; the unit tests
        # above import top-level ``pipeline_trace``. They are DISTINCT module
        # objects — patch TRACE_ROOT on both so no path escapes the tempdir.
        import orchestrator.pipeline_trace as opt  # noqa: WPS433
        for mod in (pipeline_trace, opt):
            patcher = mock.patch.object(mod, "TRACE_ROOT", self.root)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def _events(self, chunks):
        out = []
        for c in chunks:
            try:
                out.append(json.loads(c[6:]))
            except Exception:
                pass
        return out

    def _manifest_for(self, conv):
        conv_dir = os.path.join(self.root, conv)
        turns = [t for t in os.listdir(conv_dir) if not t.startswith("_")]
        self.assertEqual(len(turns), 1)
        with open(os.path.join(conv_dir, turns[0], "trace-manifest.json")) as f:
            return json.load(f)

    def test_runtime_command_short_circuit_finalizes_honestly(self):
        import slash_commands
        with mock.patch.object(slash_commands, "run_runtime_command",
                               return_value="queue empty"):
            events = self._events(
                self.S._pipeline_stream("/queue", [], panel_id="t-conv-rc"))
        m = self._manifest_for("t-conv-rc")
        self.assertEqual(m["trace_kind"], "runtime_command")
        self.assertEqual(m["terminal_status"], "short_circuit")
        # The in-band trace_ref channel fired and matches the manifest dir.
        refs = [e["ref"] for e in events if e.get("type") == "trace_ref"]
        self.assertEqual(len(refs), 1)
        self.assertTrue(refs[0].startswith("t-conv-rc/"))

    def test_runtime_command_error_finalizes_error(self):
        import slash_commands
        with mock.patch.object(slash_commands, "run_runtime_command",
                               side_effect=RuntimeError("boom")):
            list(self.S._pipeline_stream("/queue", [], panel_id="t-conv-err"))
        m = self._manifest_for("t-conv-err")
        self.assertEqual(m["trace_kind"], "runtime_command")
        self.assertEqual(m["terminal_status"], "error")

    def test_client_disconnect_finalizes_abandoned(self):
        gen = self.S._pipeline_stream("anything", [], panel_id="t-conv-gx")
        next(gen)          # first event (trace_ref) — turn underway
        gen.close()        # GeneratorExit — client disconnected
        m = self._manifest_for("t-conv-gx")
        self.assertEqual(m["terminal_status"], "abandoned")
        self.assertEqual(m["trace_kind"], "unknown")

    def test_direct_stream_no_endpoint_finalizes_error_via_fallback(self):
        # Adversarial-review finding: _direct_stream's own endpoint check
        # (reached via the fallback_to_direct branch, which already set
        # kind="direct") must set turn_state["status"]="error" — not
        # leave the turn misclassified as a clean short_circuit.
        with mock.patch.object(self.S, "get_endpoint", return_value=None):
            list(self.S._direct_stream("hi", [], turn_state={
                "kind": "direct", "status": None,
            }))
        # Verified via the turn_state dict directly (no trace_dir here —
        # this unit exercises _direct_stream in isolation, matching the
        # design's own call-site contract).

    def test_direct_stream_sets_error_status_on_turn_state(self):
        turn_state = {"kind": "direct", "status": None}
        with mock.patch.object(self.S, "get_endpoint", return_value=None):
            list(self.S._direct_stream("hi", [], turn_state=turn_state))
        self.assertEqual(turn_state["status"], "error")

    def test_direct_stream_turn_state_none_is_a_no_op(self):
        # The /direct slash-command call site passes no turn_state at all.
        with mock.patch.object(self.S, "get_endpoint", return_value=None):
            list(self.S._direct_stream("hi", []))  # must not raise

    def test_direct_stream_risk_hold_rekinds_from_direct(self):
        # Codex code-review-gate block, finding #2: the caller already
        # stamped kind="direct" before invoking this generator; a held
        # turn is an intentional stop, not the "direct" short-circuit —
        # it must re-kind to risk_hold, or the manifest reads
        # terminal_status: short_circuit for a turn that was actually held.
        import risk_gate
        turn_state = {"kind": "direct", "status": None}
        with mock.patch.object(self.S, "get_endpoint",
                               return_value={"name": "mock"}), \
             mock.patch.object(risk_gate, "evaluate_hold",
                               return_value=("held for review.", "fp")):
            events = self._events(
                list(self.S._direct_stream("hi", [], turn_state=turn_state)))
        self.assertEqual(turn_state["kind"], "risk_hold")
        self.assertTrue(any(e.get("type") == "response" for e in events))

    def test_first_turn_stealth_tag_honored_when_no_envelope_exists(self):
        # Codex code-review-gate block, finding #1: a brand-new
        # conversation has no conversation.json envelope yet, so
        # get_conversation_tag returns "" — the REQUEST's own
        # conversation_tag (the client's stealth choice for this
        # submission) must still be honoured, not silently ignored.
        import slash_commands
        with mock.patch.object(slash_commands, "run_runtime_command",
                               return_value="queue empty"), \
             mock.patch("orchestrator.conversation_memory.get_conversation_tag",
                        return_value=""):
            events = self._events(list(self.S._pipeline_stream(
                "/queue", [], panel_id="t-conv-stealth-new",
                conversation_tag="stealth")))
        conv_dir = os.path.join(self.root, "t-conv-stealth-new")
        self.assertFalse(os.path.isdir(conv_dir))
        self.assertFalse(any(e.get("type") == "trace_ref" for e in events))

    def test_persisted_envelope_tag_wins_over_differing_request_tag(self):
        # The inverse precedence: an EXISTING conversation's persisted tag
        # is authoritative (immutable after first save) even if this
        # particular request carries no tag of its own.
        import slash_commands
        with mock.patch.object(slash_commands, "run_runtime_command",
                               return_value="queue empty"), \
             mock.patch("orchestrator.conversation_memory.get_conversation_tag",
                        return_value="stealth"):
            list(self.S._pipeline_stream(
                "/queue", [], panel_id="t-conv-stealth-existing",
                conversation_tag=""))
        conv_dir = os.path.join(self.root, "t-conv-stealth-existing")
        self.assertFalse(os.path.isdir(conv_dir))


class TestRunPipelineFinalization(unittest.TestCase):
    """boot.py::run_pipeline (the CLI/terminal entry point) is a second,
    independent trace-opening call path from server.py's _pipeline_stream.
    Adversarial-review finding: Chunk 0 originally wired the finalizer
    into server.py only, leaving every run_pipeline turn's manifest
    permanently stuck at terminal_status "open".
    """

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ORCHESTRATOR))
        import boot  # noqa: WPS433
        cls.boot = boot

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "pipeline-traces")
        os.makedirs(self.root)
        import orchestrator.pipeline_trace as opt  # noqa: WPS433
        for mod in (pipeline_trace, opt, self.boot.pipeline_trace):
            patcher = mock.patch.object(mod, "TRACE_ROOT", self.root)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def _manifest_for(self, conv):
        conv_dir = os.path.join(self.root, conv)
        turns = [t for t in os.listdir(conv_dir) if not t.startswith("_")]
        self.assertEqual(len(turns), 1)
        with open(os.path.join(conv_dir, turns[0], "trace-manifest.json")) as f:
            return json.load(f)

    def test_runtime_command_finalizes_honestly(self):
        import slash_commands
        with mock.patch.object(slash_commands, "run_runtime_command",
                               return_value="queue empty"):
            result = self.boot.run_pipeline(
                "/queue", conversation_id="t-boot-rc")
        self.assertEqual(result, "queue empty")
        m = self._manifest_for("t-boot-rc")
        self.assertEqual(m["trace_kind"], "runtime_command")
        self.assertEqual(m["terminal_status"], "short_circuit")

    def test_exception_finalizes_error_not_left_open(self):
        import slash_commands
        with mock.patch.object(slash_commands, "run_runtime_command",
                               side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.boot.run_pipeline("/queue", conversation_id="t-boot-err")
        m = self._manifest_for("t-boot-err")
        self.assertEqual(m["terminal_status"], "error")

    def test_conversation_tag_reaches_redaction_level(self):
        # Adversarial-review finding: run_pipeline never threaded
        # conversation_tag into start_trace, so CLI-invoked private
        # conversations were silently stamped redaction_level "default".
        import slash_commands
        with mock.patch.object(slash_commands, "run_runtime_command",
                               return_value="queue empty"):
            self.boot.run_pipeline("/queue", conversation_id="t-boot-priv",
                                   conversation_tag="private")
        m = self._manifest_for("t-boot-priv")
        self.assertEqual(m["redaction_level"], "private")


if __name__ == "__main__":
    unittest.main()
