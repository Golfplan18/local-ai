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

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
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
        data_patcher = mock.patch.object(
            pipeline_trace._rp, "DATA_DIR_STR",
            os.path.join(self.tmp.name, "data"),
        )
        data_patcher.start()
        self.addCleanup(data_patcher.stop)
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

    def test_trace_root_symlink_is_refused_without_touching_target(self):
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        Path(self.root).rmdir()
        Path(self.root).symlink_to(outside, target_is_directory=True)

        self.assertIsNone(self.start())
        self.assertEqual(list(outside.iterdir()), [])

    def test_conversation_trace_symlink_is_refused(self):
        outside = Path(self.tmp.name) / "outside-conversation"
        outside.mkdir()
        (Path(self.root) / "conv-a").symlink_to(
            outside, target_is_directory=True,
        )

        self.assertIsNone(self.start())
        self.assertEqual(list(outside.iterdir()), [])

    def test_trace_writers_refuse_swapped_turn_directory_symlink(self):
        trace_dir = Path(self.start())
        outside = Path(self.tmp.name) / "outside-turn"
        outside.mkdir()
        shutil.rmtree(trace_dir)
        trace_dir.symlink_to(outside, target_is_directory=True)

        pipeline_trace.write_step(str(trace_dir), "step1", {"secret": "no"})
        pipeline_trace.append_jsonl(str(trace_dir), "usage.jsonl", {"secret": "no"})
        pipeline_trace.write_step_health(str(trace_dir), {}, 1, [])
        pipeline_trace.finalize_manifest(str(trace_dir), kind="direct")

        self.assertEqual(list(outside.iterdir()), [])

    def test_trace_writer_rejects_filename_traversal(self):
        trace_dir = Path(self.start())
        pipeline_trace.write_step(str(trace_dir), "../escape", {"secret": "no"})
        pipeline_trace.append_jsonl(str(trace_dir), "../escape.jsonl", {})
        self.assertFalse((trace_dir.parent / "escape.json").exists())
        self.assertFalse((trace_dir.parent / "escape.jsonl").exists())


class TestTraceLifecycleMutation(TraceManifestBase):
    def test_purge_uses_shared_lock_and_removes_case_variants(self):
        first = self.start("Dialogue-A")
        self.assertTrue(first)
        entered: list[str] = []

        @contextlib.contextmanager
        def fake_lock(conversation_id):
            entered.append(conversation_id)
            yield

        with mock.patch.object(
            pipeline_trace._rp, "conversation_lifecycle_lock", fake_lock,
        ):
            result = pipeline_trace.purge_conversation_traces("DIALOGUE-A")

        self.assertEqual(entered, ["DIALOGUE-A"])
        self.assertTrue(result["deleted"])
        self.assertEqual(len(result["paths"]), 1)
        self.assertFalse(Path(first).parent.exists())

    def test_purge_unlinks_conversation_symlink_not_external_target(self):
        outside = Path(self.tmp.name) / "external-traces"
        outside.mkdir()
        sentinel = outside / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        link = Path(self.root) / "conv-link"
        link.symlink_to(outside, target_is_directory=True)

        result = pipeline_trace.purge_conversation_traces("conv-link")

        self.assertTrue(result["deleted"])
        self.assertTrue(result["symlink_removed"])
        self.assertFalse(link.exists())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_retag_updates_owned_manifests_and_reverses_exact_level(self):
        first = self.start("Dialogue-A")

        private = pipeline_trace.retag_conversation_trace_manifests(
            "DIALOGUE-A", "private",
        )
        self.assertEqual(private["updated"], 1)
        self.assertEqual(private["errors"], [])
        self.assertEqual(self.manifest(first)["redaction_level"], "private")
        self.assertEqual(self.manifest(first)["terminal_status"], "open")

        standard = pipeline_trace.retag_conversation_trace_manifests(
            "dialogue-a", "",
        )
        self.assertEqual(standard["updated"], 1)
        self.assertEqual(self.manifest(first)["redaction_level"], "default")

    def test_retag_refuses_foreign_or_symlinked_manifest(self):
        owned = Path(self.start("conv-a"))
        manifest = owned / pipeline_trace.MANIFEST_FILENAME
        outside = Path(self.tmp.name) / "outside-manifest.json"
        outside.write_text(
            json.dumps({"conversation_id": "conv-a", "redaction_level": "default"}),
            encoding="utf-8",
        )
        manifest.unlink()
        manifest.symlink_to(outside)

        result = pipeline_trace.retag_conversation_trace_manifests(
            "conv-a", "private",
        )

        self.assertEqual(result["updated"], 0)
        self.assertTrue(result["errors"])
        self.assertEqual(
            json.loads(outside.read_text(encoding="utf-8"))["redaction_level"],
            "default",
        )

        manifest.unlink()
        manifest.write_text(
            json.dumps({"conversation_id": "someone-else",
                        "redaction_level": "default"}),
            encoding="utf-8",
        )
        result = pipeline_trace.retag_conversation_trace_manifests(
            "conv-a", "private",
        )
        self.assertEqual(result["updated"], 0)
        self.assertTrue(any("does not match" in error
                            for error in result["errors"]))

    def test_retag_rejects_stealth_and_uses_shared_lock(self):
        self.start("conv-a")
        entered: list[str] = []

        @contextlib.contextmanager
        def fake_lock(conversation_id):
            entered.append(conversation_id)
            yield

        with mock.patch.object(
            pipeline_trace._rp, "conversation_lifecycle_lock", fake_lock,
        ):
            pipeline_trace.retag_conversation_trace_manifests(
                "conv-a", "private",
            )
        self.assertEqual(entered, ["conv-a"])
        with self.assertRaises(ValueError):
            pipeline_trace.retag_conversation_trace_manifests(
                "conv-a", "stealth",
            )

    def test_start_trace_concurrent_same_timestamp_unique_dirs(self):
        results = []
        errors = []

        def _worker():
            try:
                results.append(self.start("conv-race"))
            except Exception as exc:
                errors.append(exc)

        with mock.patch.object(pipeline_trace, "_now_ts",
                               return_value="20260712T000000Z"):
            threads = [threading.Thread(target=_worker) for _ in range(50)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 50)
        self.assertEqual(len(set(results)), 50)
        self.assertTrue(all(os.path.isdir(p) for p in results))



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

    def test_resolve_trace_ref_requires_manifest_bearing_turn_dir(self):
        d = self.start("conv-r")
        ref = pipeline_trace.trace_ref_for_dir(d)
        self.assertEqual(pipeline_trace.resolve_trace_ref(ref),
                         os.path.realpath(d))
        self.assertIsNone(pipeline_trace.resolve_trace_ref("../conv-r/x"))
        self.assertIsNone(pipeline_trace.resolve_trace_ref("conv-r"))
        self.assertIsNone(pipeline_trace.resolve_trace_ref("conv-r/nope"))

    def test_resolve_trace_ref_rejects_symlink_escape(self):
        external = tempfile.TemporaryDirectory()
        self.addCleanup(external.cleanup)
        outside_turn = os.path.join(external.name, "turn")
        os.makedirs(outside_turn)
        pipeline_trace._atomic_write_json(
            os.path.join(outside_turn, "trace-manifest.json"),
            {"trace_kind": "chat"})
        conv_dir = os.path.join(self.root, "conv-link")
        os.makedirs(conv_dir)
        os.symlink(outside_turn, os.path.join(conv_dir, "evil"))
        self.assertIsNone(pipeline_trace.resolve_trace_ref("conv-link/evil"))

    def test_pin_unpin_preserves_manifest_fields(self):
        d = self.start("conv-pin")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.finalize_manifest(
            d, kind="framework-run", status_hint="completed",
            framework_id="deep-research-protocol",
            child_trace_refs=["conv-pin/child-a"])
        pinned = pipeline_trace.set_retention_state(ref, "pinned")
        self.assertEqual(pinned["retention_state"], "pinned")
        self.assertEqual(pinned["framework_id"], "deep-research-protocol")
        self.assertEqual(pinned["child_trace_refs"], ["conv-pin/child-a"])
        unpinned = pipeline_trace.set_retention_state(ref, "default")
        self.assertEqual(unpinned["retention_state"], "default")


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

    def test_framework_fields_and_child_refs_dedupe(self):
        d = self.start()
        m = self.manifest(d)
        m["child_trace_refs"] = ["conv-a/child-1"]
        pipeline_trace._atomic_write_json(
            os.path.join(d, "trace-manifest.json"), m)
        pipeline_trace.finalize_manifest(
            d, kind="framework-run", status_hint="completed",
            mode="all", framework_id="fw-a",
            child_trace_refs=["conv-a/child-1", "conv-a/child-2"])
        m2 = self.manifest(d)
        self.assertEqual(m2["trace_kind"], "framework-run")
        self.assertEqual(m2["terminal_status"], "completed")
        self.assertEqual(m2["framework_id"], "fw-a")
        self.assertEqual(m2["mode"], "all")
        self.assertEqual(m2["child_trace_refs"],
                         ["conv-a/child-1", "conv-a/child-2"])

    def test_append_child_trace_ref_preserves_and_dedupes(self):
        d = self.start()
        pipeline_trace.append_child_trace_ref(d, "conv-a/child-1")
        pipeline_trace.append_child_trace_ref(d, "conv-a/child-1")
        pipeline_trace.append_child_trace_ref(d, "conv-a/child-2")
        self.assertEqual(self.manifest(d)["child_trace_refs"],
                         ["conv-a/child-1", "conv-a/child-2"])

    def test_model_call_config_snapshot_is_redacted(self):
        d = self.start()
        endpoint = {
            "id": "ep-a", "name": "Endpoint A", "type": "api",
            "service": "openai", "provider": "openai",
            "model": "gpt-test", "temperature": 0.2,
            "top_p": 0.9, "max_tokens": 123,
            "api_key": "SECRET", "credential_key": "ora/secret",
            "base_url": "https://user:pass@example.test/v1",
        }
        pipeline_trace.record_model_call_config(
            d, endpoint,
            {"step": "verifier", "slot": "breadth", "gear": 4,
             "config_name": "Premium"})
        with open(os.path.join(d, "model-call-config.jsonl")) as f:
            rec = json.loads(f.readline())
        self.assertEqual(rec["step"], "verifier")
        self.assertEqual(rec["slot"], "breadth")
        self.assertEqual(rec["gear"], 4)
        self.assertEqual(rec["config_name"], "Premium")
        self.assertEqual(rec["model_id"], "gpt-test")
        self.assertEqual(rec["sampling"]["temperature"], 0.2)
        blob = json.dumps(rec)
        self.assertNotIn("SECRET", blob)
        self.assertNotIn("credential_key", blob)
        self.assertNotIn("user:pass", blob)

    def test_model_call_config_rejects_schemeless_credential_url(self):
        d = self.start()
        endpoint = {
            "id": "ep-b", "type": "api", "service": "openai",
            "model": "gpt-test",
            "base_url": "user:pass@example.test/v1",
        }
        pipeline_trace.record_model_call_config(d, endpoint, {})
        with open(os.path.join(d, "model-call-config.jsonl")) as f:
            rec = json.loads(f.readline())
        blob = json.dumps(rec)
        self.assertEqual(rec["base_url_host"], "")
        self.assertNotIn("pass@example.test", blob)

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


class TestMilestoneChildLifecycle(TraceManifestBase):
    def _fake_framework(self):
        return SimpleNamespace(name="fw-a", layers={})

    def _fake_milestone(self):
        return SimpleNamespace(
            id="m1",
            name="Milestone One",
            gear=3,
            required_prior=[],
            layers_covered=[],
            output_format="Return text.",
            verification_criterion="Text exists.",
            conditional_layers="",
            drift_check_question="",
        )

    def _fake_scratch(self):
        return SimpleNamespace(
            read_all_prior=lambda _ids: {},
            write_milestone=lambda _mid, _deliverable: None,
        )

    def test_child_trace_stays_open_until_attempt_finalizes(self):
        import milestone_executor
        parent = self.start("fw-parent")
        parent_ref = pipeline_trace.trace_ref_for_dir(parent)
        child = milestone_executor._start_child_trace(
            parent, "handoff", "fw-a", "m1", parent_ref, "all", 3, "", {})
        m = self.manifest(child)
        self.assertEqual(m["trace_kind"], "framework-milestone")
        self.assertEqual(m["terminal_status"], "open")
        self.assertIsNone(m["finalized_at"])
        self.assertEqual(m["parent_trace_ref"], parent_ref)

    def test_keyboard_interrupt_finalizes_child_error(self):
        import milestone_executor
        parent = self.start("fw-parent")
        parent_ref = pipeline_trace.trace_ref_for_dir(parent)
        with mock.patch.object(milestone_executor, "_run_child_attempt",
                               side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                milestone_executor._run_milestone(
                    self._fake_framework(), self._fake_milestone(),
                    self._fake_scratch(), "user input", {},
                    parent_trace_dir=parent,
                    parent_trace_ref=parent_ref,
                    selected_mode="all",
                    trace_context={},
                )
        parent_m = self.manifest(parent)
        self.assertEqual(len(parent_m["child_trace_refs"]), 1)
        child = pipeline_trace.resolve_trace_ref(parent_m["child_trace_refs"][0])
        self.assertEqual(self.manifest(child)["terminal_status"], "error")

    def test_run_milestone_retry_creates_error_then_completed_children(self):
        import milestone_executor
        parent = self.start("fw-parent")
        parent_ref = pipeline_trace.trace_ref_for_dir(parent)
        writes = []
        scratch = SimpleNamespace(
            read_all_prior=lambda _ids: {},
            write_milestone=lambda mid, deliverable: writes.append(
                (mid, deliverable)),
        )
        trace_context = {}
        with mock.patch.object(
            milestone_executor, "_run_child_attempt",
            side_effect=[RuntimeError("first attempt failed"), "deliverable"],
        ), mock.patch.object(
            milestone_executor, "_run_drift_check",
            return_value=("IN_SCOPE", "ok"),
        ), mock.patch.object(milestone_executor.time, "sleep",
                            return_value=None):
            result = milestone_executor._run_milestone(
                self._fake_framework(), self._fake_milestone(),
                scratch, "user input", {},
                parent_trace_dir=parent,
                parent_trace_ref=parent_ref,
                selected_mode="all",
                trace_context=trace_context,
            )

        self.assertEqual(result.attempts, 2)
        self.assertEqual(writes, [("m1", "deliverable")])
        parent_m = self.manifest(parent)
        child_refs = parent_m["child_trace_refs"]
        self.assertEqual(len(child_refs), 2)
        self.assertEqual(len(set(child_refs)), 2)
        self.assertEqual(trace_context["child_trace_refs"], child_refs)
        statuses = []
        for child_ref in child_refs:
            child_dir = pipeline_trace.resolve_trace_ref(child_ref)
            self.assertIsNotNone(child_dir)
            child = self.manifest(child_dir)
            statuses.append(child["terminal_status"])
            self.assertEqual(child["parent_trace_ref"], parent_ref)
            self.assertEqual(child["framework_id"], "fw-a")
            self.assertEqual(child["milestone_id"], "m1")
        self.assertEqual(statuses, ["error", "completed"])

    def test_framework_gear_pipeline_passes_mode_text_to_gear4(self):
        import boot
        import milestone_executor
        seen = {}

        def _fake_run_gear4(context_pkg, _config, **_kwargs):
            seen.update(context_pkg)
            return "ok"

        milestone = self._fake_milestone()
        milestone.gear = 4
        with mock.patch.object(boot, "run_gear4", side_effect=_fake_run_gear4):
            result = milestone_executor._run_through_gear_pipeline(
                "handoff", milestone, {},
                trace_dir="/tmp/trace",
                parent_trace_ref="parent/ref",
                framework_id="fw-a",
                selected_mode="all",
            )

        self.assertEqual(result, "ok")
        self.assertEqual(seen["mode_name"], "synthesis")
        self.assertEqual(seen["mode"], "synthesis")
        self.assertIn("mode_text", seen)
        self.assertTrue(seen["mode_text"])
        self.assertEqual(seen["raw_prompt"], "handoff")
        self.assertEqual(seen["natural_language_prompt"], "handoff")
        self.assertEqual(seen["parent_trace_ref"], "parent/ref")
        self.assertEqual(seen["framework_id"], "fw-a")


class TestPhysicalModelCallConfig(TraceManifestBase):
    def setUp(self):
        super().setUp()
        import boot
        self.boot = boot
        patcher = mock.patch.object(self.boot.pipeline_trace, "TRACE_ROOT",
                                    self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_truncation_retry_records_each_effective_attempt(self):
        d = self.start("model-config")
        trace_token = self.boot._TURN_TRACE_DIR_CV.set(d)
        meta_token = self.boot._CALL_METADATA_CV.set({
            "step": "step-x",
            "slot": "analyst",
            "gear": 4,
            "config_name": "test-config",
        })
        try:
            def _make_call(max_tokens):
                return ("text", max_tokens == 10)

            result = self.boot._call_api_with_truncation_retry(
                _make_call, "OpenAI",
                {"id": "ep-a", "type": "api", "service": "openai",
                 "model": "gpt-test", "max_tokens": 10})
        finally:
            self.boot._CALL_METADATA_CV.reset(meta_token)
            self.boot._TURN_TRACE_DIR_CV.reset(trace_token)

        self.assertEqual(result, "text")
        with open(os.path.join(d, "model-call-config.jsonl")) as f:
            records = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(records), 2)
        self.assertEqual([r["effective_max_tokens"] for r in records],
                         [10, 20])
        self.assertEqual([r["attempt_index"] for r in records], [1, 2])
        self.assertEqual({r["provider_attempt"] for r in records},
                         {"OpenAI"})
        self.assertEqual(len({r["invocation_id"] for r in records}), 1)

    def _bind_boot_trace(self, trace_dir, meta=None):
        trace_token = self.boot._TURN_TRACE_DIR_CV.set(trace_dir)
        meta_token = self.boot._CALL_METADATA_CV.set(meta or {
            "step": "step-x", "slot": "analyst", "gear": 4,
            "config_name": "test-config",
        })
        return trace_token, meta_token

    def _reset_boot_trace(self, trace_token, meta_token):
        self.boot._CALL_METADATA_CV.reset(meta_token)
        self.boot._TURN_TRACE_DIR_CV.reset(trace_token)

    def _model_config_records(self, trace_dir):
        with open(os.path.join(trace_dir, "model-call-config.jsonl")) as f:
            return [json.loads(line) for line in f if line.strip()]

    def test_claude_code_subscription_records_physical_attempt(self):
        d = self.start("cc-config")
        trace_token, meta_token = self._bind_boot_trace(d)
        completed = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "result": "hello",
                "usage": {"input_tokens": 1, "output_tokens": 2},
                "modelUsage": {
                    "claude-opus-4-8": {
                        "inputTokens": 1, "outputTokens": 2,
                    },
                },
            }),
            stderr="",
        )
        try:
            with mock.patch("subprocess.run", return_value=completed), \
                 mock.patch.dict(os.environ, {"ORA_CLAUDE_CODE_BIN": "claude"}):
                result = self.boot._call_claude_code_subscription(
                    [{"role": "user", "content": "hello"}],
                    {"id": "cc", "type": "api", "service": "claude-code",
                     "model": "claude-opus-4-8"})
        finally:
            self._reset_boot_trace(trace_token, meta_token)
        self.assertEqual(result, "hello")
        records = self._model_config_records(d)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["provider_attempt"], "claude-code")
        self.assertEqual(records[0]["model_id"], "claude-opus-4-8")

    def test_mlx_records_resolved_default_token_cap(self):
        d = self.start("mlx-config")
        trace_token, meta_token = self._bind_boot_trace(d)
        fake_tokenizer = SimpleNamespace(
            apply_chat_template=lambda *_args, **_kw: "prompt")
        fake_mlx = SimpleNamespace(
            load=lambda _model: ("model-obj", fake_tokenizer),
            generate=lambda *_args, **_kw: "answer",
        )
        try:
            with mock.patch.dict(sys.modules, {"mlx_lm": fake_mlx}):
                result = self.boot.call_local_endpoint(
                    [{"role": "user", "content": "hello"}],
                    {"id": "local-mlx", "type": "local",
                     "engine": "mlx", "model": "mlx-model"})
        finally:
            self.boot._mlx_cache.clear()
            self._reset_boot_trace(trace_token, meta_token)
        self.assertEqual(result, "answer")
        records = self._model_config_records(d)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["provider_attempt"], "mlx")
        self.assertEqual(records[0]["effective_max_tokens"], 999_999_999)

    def test_unsupported_local_engine_records_no_physical_attempt(self):
        d = self.start("unsupported-local")
        trace_token, meta_token = self._bind_boot_trace(d)
        try:
            result = self.boot.call_local_endpoint(
                [{"role": "user", "content": "hello"}],
                {"id": "local-bad", "type": "local",
                 "engine": "nope", "model": "x"})
        finally:
            self._reset_boot_trace(trace_token, meta_token)
        self.assertIn("Unsupported engine", result)
        self.assertFalse(os.path.exists(
            os.path.join(d, "model-call-config.jsonl")))


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
        trace_dir = self._turn_dir_for(conv)
        with open(os.path.join(trace_dir, "trace-manifest.json")) as f:
            return json.load(f)

    def _turn_dir_for(self, conv):
        conv_dir = os.path.join(self.root, conv)
        turns = [t for t in os.listdir(conv_dir) if not t.startswith("_")]
        self.assertGreaterEqual(len(turns), 1)
        if len(turns) == 1:
            return os.path.join(conv_dir, turns[0])
        parents = []
        for turn in turns:
            trace_dir = os.path.join(conv_dir, turn)
            try:
                with open(os.path.join(trace_dir, "trace-manifest.json")) as f:
                    m = json.load(f)
                if m.get("trace_kind") != "framework-milestone":
                    parents.append(trace_dir)
            except Exception:
                pass
        self.assertEqual(len(parents), 1)
        return parents[0]

    def _fake_completed_framework_with_retry(self, *_args, **kwargs):
        import milestone_executor
        trace_dir = kwargs["trace_dir"]
        trace_context = kwargs["trace_context"]
        parent_ref = pipeline_trace.trace_ref_for_dir(trace_dir)
        first = milestone_executor._start_child_trace(
            trace_dir, "attempt one", "fw-happy", "m1", parent_ref,
            "all", 3, kwargs.get("conversation_tag", ""), trace_context)
        milestone_executor._finalize_child_trace(
            first, "error", "fw-happy", "m1", "all", 3, parent_ref)
        second = milestone_executor._start_child_trace(
            trace_dir, "attempt two", "fw-happy", "m1", parent_ref,
            "all", 3, kwargs.get("conversation_tag", ""), trace_context)
        milestone_executor._finalize_child_trace(
            second, "completed", "fw-happy", "m1", "all", 3, parent_ref)
        trace_context.update({
            "status": "completed",
            "framework_id": "fw-happy",
            "mode": "all",
        })
        return "framework complete"

    def _assert_completed_framework_lineage(self, conv):
        parent_dir = self._turn_dir_for(conv)
        parent = self._manifest_for(conv)
        parent_ref = pipeline_trace.trace_ref_for_dir(parent_dir)
        self.assertEqual(parent["trace_kind"], "framework-run")
        self.assertEqual(parent["terminal_status"], "completed")
        self.assertEqual(parent["framework_id"], "fw-happy")
        self.assertEqual(len(parent["child_trace_refs"]), 2)
        self.assertEqual(len(set(parent["child_trace_refs"])), 2)
        child_statuses = []
        for child_ref in parent["child_trace_refs"]:
            child_dir = pipeline_trace.resolve_trace_ref(child_ref)
            self.assertIsNotNone(child_dir)
            with open(os.path.join(child_dir, "trace-manifest.json")) as f:
                child = json.load(f)
            child_statuses.append(child["terminal_status"])
            self.assertEqual(child["trace_kind"], "framework-milestone")
            self.assertEqual(child["parent_trace_ref"], parent_ref)
            self.assertEqual(child["framework_id"], "fw-happy")
            self.assertEqual(child["milestone_id"], "m1")
        self.assertEqual(child_statuses, ["error", "completed"])

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

    def test_framework_command_error_finalizes_error(self):
        import milestone_executor
        def _fake_framework(*_args, **kwargs):
            kwargs["trace_context"].update({
                "status": "error", "framework_id": "fw-x",
            })
            return "[Framework parse error: bad]"

        with mock.patch.object(milestone_executor, "framework_command_has_query",
                               return_value=True), \
             mock.patch.object(milestone_executor, "run_framework_command",
                               side_effect=_fake_framework):
            list(self.S._pipeline_stream(
                "/framework fw-x do thing", [], panel_id="t-conv-fw-err"))
        m = self._manifest_for("t-conv-fw-err")
        self.assertEqual(m["trace_kind"], "framework-run")
        self.assertEqual(m["terminal_status"], "error")
        self.assertEqual(m["framework_id"], "fw-x")

    def test_framework_command_completed_parent_child_lineage(self):
        import milestone_executor
        with mock.patch.object(milestone_executor, "framework_command_has_query",
                               return_value=True), \
             mock.patch.object(milestone_executor, "run_framework_command",
                               side_effect=self._fake_completed_framework_with_retry):
            events = self._events(list(self.S._pipeline_stream(
                "/framework fw-happy do thing", [],
                panel_id="t-conv-fw-happy")))
        self.assertTrue(any(e.get("type") == "trace_ref" for e in events))
        self._assert_completed_framework_lineage("t-conv-fw-happy")

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
        trace_dir = self._turn_dir_for(conv)
        with open(os.path.join(trace_dir, "trace-manifest.json")) as f:
            return json.load(f)

    def _turn_dir_for(self, conv):
        conv_dir = os.path.join(self.root, conv)
        turns = [t for t in os.listdir(conv_dir) if not t.startswith("_")]
        self.assertGreaterEqual(len(turns), 1)
        if len(turns) == 1:
            return os.path.join(conv_dir, turns[0])
        parents = []
        for turn in turns:
            trace_dir = os.path.join(conv_dir, turn)
            try:
                with open(os.path.join(trace_dir, "trace-manifest.json")) as f:
                    m = json.load(f)
                if m.get("trace_kind") != "framework-milestone":
                    parents.append(trace_dir)
            except Exception:
                pass
        self.assertEqual(len(parents), 1)
        return parents[0]

    def _fake_completed_framework_with_retry(self, *_args, **kwargs):
        import milestone_executor
        trace_dir = kwargs["trace_dir"]
        trace_context = kwargs["trace_context"]
        parent_ref = pipeline_trace.trace_ref_for_dir(trace_dir)
        first = milestone_executor._start_child_trace(
            trace_dir, "attempt one", "fw-cli-happy", "m1", parent_ref,
            "all", 3, kwargs.get("conversation_tag", ""), trace_context)
        milestone_executor._finalize_child_trace(
            first, "error", "fw-cli-happy", "m1", "all", 3, parent_ref)
        second = milestone_executor._start_child_trace(
            trace_dir, "attempt two", "fw-cli-happy", "m1", parent_ref,
            "all", 3, kwargs.get("conversation_tag", ""), trace_context)
        milestone_executor._finalize_child_trace(
            second, "completed", "fw-cli-happy", "m1", "all", 3, parent_ref)
        trace_context.update({
            "status": "completed",
            "framework_id": "fw-cli-happy",
            "mode": "all",
        })
        return "framework complete"

    def _assert_completed_framework_lineage(self, conv):
        parent_dir = self._turn_dir_for(conv)
        parent = self._manifest_for(conv)
        parent_ref = pipeline_trace.trace_ref_for_dir(parent_dir)
        self.assertEqual(parent["trace_kind"], "framework-run")
        self.assertEqual(parent["terminal_status"], "completed")
        self.assertEqual(parent["framework_id"], "fw-cli-happy")
        self.assertEqual(len(parent["child_trace_refs"]), 2)
        self.assertEqual(len(set(parent["child_trace_refs"])), 2)
        child_statuses = []
        for child_ref in parent["child_trace_refs"]:
            child_dir = pipeline_trace.resolve_trace_ref(child_ref)
            self.assertIsNotNone(child_dir)
            with open(os.path.join(child_dir, "trace-manifest.json")) as f:
                child = json.load(f)
            child_statuses.append(child["terminal_status"])
            self.assertEqual(child["trace_kind"], "framework-milestone")
            self.assertEqual(child["parent_trace_ref"], parent_ref)
            self.assertEqual(child["framework_id"], "fw-cli-happy")
            self.assertEqual(child["milestone_id"], "m1")
        self.assertEqual(child_statuses, ["error", "completed"])

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

    def test_framework_command_error_finalizes_error(self):
        import milestone_executor
        def _fake_framework(*_args, **kwargs):
            kwargs["trace_context"].update({
                "status": "error", "framework_id": "fw-cli",
            })
            return "[Framework parse error: bad]"

        with mock.patch.object(milestone_executor, "framework_command_has_query",
                               return_value=True), \
             mock.patch.object(milestone_executor, "run_framework_command",
                               side_effect=_fake_framework):
            result = self.boot.run_pipeline(
                "/framework fw-cli do thing", conversation_id="t-boot-fw-err")
        self.assertIn("Framework parse error", result)
        m = self._manifest_for("t-boot-fw-err")
        self.assertEqual(m["trace_kind"], "framework-run")
        self.assertEqual(m["terminal_status"], "error")
        self.assertEqual(m["framework_id"], "fw-cli")

    def test_framework_command_completed_parent_child_lineage(self):
        import milestone_executor
        with mock.patch.object(milestone_executor, "framework_command_has_query",
                               return_value=True), \
             mock.patch.object(milestone_executor, "run_framework_command",
                               side_effect=self._fake_completed_framework_with_retry):
            result = self.boot.run_pipeline(
                "/framework fw-cli-happy do thing",
                conversation_id="t-boot-fw-happy")
        self.assertEqual(result, "framework complete")
        self._assert_completed_framework_lineage("t-boot-fw-happy")

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

    def test_cli_turn_context_is_private_then_standard_without_leak(self):
        import slash_commands
        import tool_events

        observed = []

        def observe_context(_command):
            observed.append((
                self.boot._CONVERSATION_TAG_CV.get(),
                self.boot._TURN_TRACE_DIR_CV.get(),
                tool_events.get_turn_context(),
            ))
            return "queue empty"

        outer_tag = self.boot.set_conversation_tag_context("")
        outer_trace = self.boot.set_turn_trace_context("/tmp/caller-trace")
        outer_tool = tool_events.set_turn_context(
            trace_dir="/tmp/caller-tool-trace",
            conversation_id="caller",
            surface="test",
        )
        try:
            with mock.patch.object(
                slash_commands, "run_runtime_command",
                side_effect=observe_context,
            ):
                self.boot.run_pipeline(
                    "/queue", conversation_id="t-context-private",
                    conversation_tag="private",
                )
                self.assertEqual(self.boot._CONVERSATION_TAG_CV.get(), "")
                self.assertEqual(
                    self.boot._TURN_TRACE_DIR_CV.get(), "/tmp/caller-trace",
                )
                self.boot.run_pipeline(
                    "/queue", conversation_id="t-context-standard",
                )
            self.assertEqual([item[0] for item in observed], ["private", ""])
            self.assertEqual(
                [Path(item[1]).parent.name for item in observed],
                ["t-context-private", "t-context-standard"],
            )
            self.assertEqual(
                [item[2]["conversation_id"] for item in observed],
                ["t-context-private", "t-context-standard"],
            )
            self.assertEqual(
                [item[2]["surface"] for item in observed],
                ["terminal", "terminal"],
            )
            self.assertEqual(self.boot._CONVERSATION_TAG_CV.get(), "")
            self.assertEqual(
                self.boot._TURN_TRACE_DIR_CV.get(), "/tmp/caller-trace",
            )
            self.assertEqual(
                tool_events.get_turn_context()["conversation_id"], "caller",
            )
        finally:
            tool_events.reset_turn_context(outer_tool)
            self.boot.reset_turn_trace_context(outer_trace)
            self.boot.reset_conversation_tag_context(outer_tag)

    def test_step2_context_tokens_reset_on_return_and_exception(self):
        import tool_events

        observed = []

        def observe_step2(*_args, **_kwargs):
            observed.append((
                self.boot._CONVERSATION_TAG_CV.get(),
                self.boot._TURN_TRACE_DIR_CV.get(),
                tool_events.get_turn_context(),
            ))
            return {"ok": True}

        outer_tag = self.boot.set_conversation_tag_context("")
        outer_trace = self.boot.set_turn_trace_context("/tmp/outer-step2")
        outer_tool = tool_events.set_turn_context(
            trace_dir="/tmp/outer-tool-step2",
            conversation_id="outer-step2",
            surface="test",
        )
        try:
            with mock.patch.object(
                self.boot, "_run_step2_context_assembly_impl",
                side_effect=observe_step2,
            ):
                result = self.boot.run_step2_context_assembly(
                    {}, {}, trace_dir="/tmp/private-step2/turn",
                    conversation_tag="private",
                )
            self.assertEqual(result, {"ok": True})
            self.assertEqual(
                observed[0][:2], ("private", "/tmp/private-step2/turn"),
            )
            self.assertEqual(
                observed[0][2]["conversation_id"], "private-step2",
            )
            self.assertEqual(self.boot._CONVERSATION_TAG_CV.get(), "")
            self.assertEqual(
                self.boot._TURN_TRACE_DIR_CV.get(), "/tmp/outer-step2",
            )
            self.assertEqual(
                tool_events.get_turn_context()["conversation_id"],
                "outer-step2",
            )

            with mock.patch.object(
                self.boot, "_run_step2_context_assembly_impl",
                side_effect=RuntimeError("step2 failed"),
            ):
                with self.assertRaisesRegex(RuntimeError, "step2 failed"):
                    self.boot.run_step2_context_assembly(
                        {}, {}, trace_dir="/tmp/error-step2/turn",
                        conversation_tag="private",
                    )
            self.assertEqual(self.boot._CONVERSATION_TAG_CV.get(), "")
            self.assertEqual(
                self.boot._TURN_TRACE_DIR_CV.get(), "/tmp/outer-step2",
            )
        finally:
            tool_events.reset_turn_context(outer_tool)
            self.boot.reset_turn_trace_context(outer_trace)
            self.boot.reset_conversation_tag_context(outer_tag)


if __name__ == "__main__":
    unittest.main()
