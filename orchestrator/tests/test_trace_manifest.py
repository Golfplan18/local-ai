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
from orchestrator import runtime_hygiene  # noqa: E402


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
        hygiene_data_patcher = mock.patch.object(
            runtime_hygiene._rp, "DATA_DIR_STR",
            os.path.join(self.tmp.name, "data"),
        )
        hygiene_data_patcher.start()
        self.addCleanup(hygiene_data_patcher.stop)
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
        self.assertEqual(m["schema_version"], 2)
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
        self.assertEqual(m["missing_steps"], [])
        self.assertEqual(m["skipped_steps"], [])
        self.assertEqual(m["replaced_steps"], [])
        self.assertEqual(m["contingency_steps"], [])
        self.assertEqual(m["unexpected_steps"], [])
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
        from orchestrator.runtime_hygiene import DeadlineQueue
        deadlines = DeadlineQueue()._load()["deadlines"]
        self.assertEqual(
            len([key for key in deadlines
                 if key.startswith("trace-retention-unpin:")]),
            1,
        )

    def test_refinalization_preserves_one_exact_retention_contract(self):
        d = self.start("conv-refinalize")
        pipeline_trace.finalize_manifest(
            d, kind="chat", status_hint="completed")
        first = self.manifest(d)
        pipeline_trace.finalize_manifest(
            d, kind="chat", status_hint="completed")
        second = self.manifest(d)
        self.assertEqual(first["finalized_at"], second["finalized_at"])
        from orchestrator.runtime_hygiene import DeadlineQueue
        deadlines = DeadlineQueue()._load()["deadlines"]
        self.assertEqual(
            len([key for key in deadlines if key.startswith("trace-retention:")]),
            1,
        )

    def test_finalization_intent_write_failure_cannot_report_lifecycle_success(self):
        d = self.start("conv-intent-fail")
        with mock.patch.object(
            runtime_hygiene.RetentionIntentStore, "put",
            side_effect=OSError("forced intent persistence failure"),
        ):
            pipeline_trace.finalize_manifest(
                d, kind="chat", status_hint="completed",
            )
        manifest = self.manifest(d)
        self.assertEqual(manifest["terminal_status"], "open")
        self.assertIsNone(manifest["finalized_at"])

    def test_finalization_queue_failure_recovers_exact_intent_after_restart(self):
        d = self.start("conv-queue-recover")
        with mock.patch.object(
            runtime_hygiene.DeadlineQueue, "put",
            side_effect=OSError("forced queue failure"),
        ):
            pipeline_trace.finalize_manifest(
                d, kind="chat", status_hint="completed",
            )
        pending_manifest = self.manifest(d)
        self.assertEqual(pending_manifest["terminal_status"], "completed")
        self.assertEqual(pending_manifest["retention_deadline"]["status"], "pending")

        store = runtime_hygiene.retention_intent_store(
            pipeline_trace._rp.DATA_DIR_STR,
        )
        queue = runtime_hygiene.DeadlineQueue(store.storage_root)
        report = runtime_hygiene.recover_retention_intents(
            store=store, queue=queue,
        )
        self.assertEqual(report["failed"], [])
        self.assertEqual(report["registered"], [
            pending_manifest["retention_deadline"]["key"],
        ])
        deadline = queue._load()["deadlines"][report["registered"][0]]
        self.assertEqual(deadline["payload"]["trace_ref"],
                         pipeline_trace.trace_ref_for_dir(d))

    def test_unpin_intent_write_failure_leaves_trace_pinned(self):
        d = self.start("conv-unpin-intent-fail")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.finalize_manifest(
            d, kind="chat", status_hint="completed",
        )
        pipeline_trace.set_retention_state(ref, "pinned")
        with (
            mock.patch.object(
                runtime_hygiene.RetentionIntentStore, "put",
                side_effect=OSError("forced unpin intent failure"),
            ),
            self.assertRaisesRegex(OSError, "forced unpin intent failure"),
        ):
            pipeline_trace.set_retention_state(ref, "default")
        self.assertEqual(self.manifest(d)["retention_state"], "pinned")

    def test_unpin_queue_failure_recovers_exact_intent_after_restart(self):
        d = self.start("conv-unpin-queue-recover")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.finalize_manifest(
            d, kind="chat", status_hint="completed",
        )
        pipeline_trace.set_retention_state(ref, "pinned")
        with mock.patch.object(
            runtime_hygiene.DeadlineQueue, "put",
            side_effect=OSError("forced unpin queue failure"),
        ):
            unpinned = pipeline_trace.set_retention_state(ref, "default")
        self.assertEqual(unpinned["retention_state"], "default")
        self.assertEqual(unpinned["retention_deadline"]["status"], "pending")

        store = runtime_hygiene.retention_intent_store(
            pipeline_trace._rp.DATA_DIR_STR,
        )
        queue = runtime_hygiene.DeadlineQueue(store.storage_root)
        report = runtime_hygiene.recover_retention_intents(
            store=store, queue=queue,
        )
        self.assertEqual(report["failed"], [])
        self.assertEqual(report["registered"], [
            unpinned["retention_deadline"]["key"],
        ])


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
                         ["step-terminal-output", "step1-phase-a",
                          "step1-pre-routing", "step3-direct-response"])
        self.assertEqual(m["missing_steps"], [])
        self.assertEqual(m["skipped_steps"],
                         ["step-terminal-output", "step3-direct-response"])

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
                  "step8-formatted", "step-terminal-output"):
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
        self.touch_step(d, "step3-direct-response")
        self.touch_step(d, "step-terminal-output")
        pipeline_trace.finalize_manifest(d, kind="chat",
                                         status_hint="completed", gear=2)
        m = self.manifest(d)
        self.assertEqual(m["trace_kind"], "chat-gear2")
        self.assertEqual(m["terminal_status"], "completed")
        self.assertEqual(m["expected_steps"],
                         ["step-terminal-output", "step1-phase-a",
                          "step1-pre-routing", "step2-context",
                          "step3-direct-response"])

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
            self.assertNotIn(s, m["skipped_steps"])
            self.assertNotIn(s, m["unexpected_steps"])

    def test_clarification_resume_expects_no_step1(self):
        # The resume reuses the paused turn's stored step1 dict; expecting
        # step1 files would manufacture a false missing-step warning.
        d = self.start()
        pipeline_trace.write_step_health(d, {}, 3, [])
        pipeline_trace.finalize_manifest(d, kind="clarification_resume")
        m = self.manifest(d)
        self.assertEqual(m["expected_steps"],
                         ["step-terminal-output", "step2-context",
                          "step3-depth", "step4-eval", "step5-revised"])

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
                  "step3-depth", "step4-eval", "step5-revised",
                  "step-terminal-output"):
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
                  "step3-single-analyst-fallback", "step-terminal-output"):
            self.touch_step(d, s)
        pipeline_trace.write_step_health(d, {}, 3, [])
        pipeline_trace.finalize_manifest(d, kind="chat")
        m = self.manifest(d)
        self.assertEqual(m["gear"], 3)
        self.assertIn("step3-depth", m["expected_steps"])
        self.assertIn("step4-eval", m["expected_steps"])
        self.assertIn("step5-revised", m["expected_steps"])
        self.assertNotIn("step3-single-analyst-fallback", m["expected_steps"])
        self.assertEqual(set(m["replaced_steps"]), {
            "step3-depth", "step4-eval", "step5-revised",
        })
        self.assertEqual(m["contingency_steps"],
                         ["step3-single-analyst-fallback"])
        self.assertEqual(m["missing_steps"], [])
        self.assertEqual(m["unexpected_steps"], [])

    def test_gear4_external_consolidation_handoff_satisfies_requirement(self):
        d = self.start()
        for s in ("step1-phase-a", "step1-pre-routing", "step2-context",
                  "step3-depth", "step3-breadth", "step4-eval-of-depth",
                  "step4-eval-of-breadth", "step5-revised-depth",
                  "step5-revised-breadth", "step7-external-consolidation-handoff"):
            self.touch_step(d, s)
        self.touch_step(d, "step-terminal-output")
        pipeline_trace.write_step_health(d, {}, 4, [])
        pipeline_trace.finalize_manifest(d, kind="chat")
        m = self.manifest(d)
        self.assertEqual(m["gear"], 4)
        self.assertIn("step7-consolidated", m["expected_steps"])
        self.assertIn("step8-formatted", m["expected_steps"])
        self.assertNotIn("step7-external-consolidation-handoff",
                         m["expected_steps"])
        self.assertEqual(set(m["replaced_steps"]), {
            "step7-consolidated", "step8-formatted",
        })
        self.assertEqual(m["contingency_steps"],
                         ["step7-external-consolidation-handoff"])
        self.assertEqual(m["missing_steps"], [])

    def test_normal_gear4_completion_unaffected_by_contingency_logic(self):
        # No fallback marker present — the normal full table still applies.
        d = self.start()
        for s in ("step1-phase-a", "step1-pre-routing", "step2-context",
                  "step3-depth", "step3-breadth", "step4-eval-of-depth",
                  "step4-eval-of-breadth", "step5-revised-depth",
                  "step5-revised-breadth", "step7-consolidated",
                  "step8-formatted", "step-terminal-output"):
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


class TestTraceWalkProjection(TraceManifestBase):
    def _completed_trace(self):
        d = self.start("conv-walk")
        self.touch_step(d, "step1-phase-a", {
            "prompt": "<script>x</script>",
            "sk-user-secret-key": "system prompt secret",
        })
        Path(os.path.join(d, "step1-phase-a.md")).write_text(
            "# Heading\n\n<script>alert(1)</script>\n\n[bad](https://example.test)\n\n![img](x)",
            encoding="utf-8",
        )
        pipeline_trace.write_step_health(d, {"step1-phase-a": [True, "ok"]}, 3, [])
        pipeline_trace.finalize_manifest(d, kind="chat", gear=3)
        return d, pipeline_trace.trace_ref_for_dir(d)

    def test_step_projection_only_allows_manifest_steps_and_step_health(self):
        _d, ref = self._completed_trace()
        self.assertIsNotNone(
            pipeline_trace.trace_step_projection(ref, "step1-phase-a"))
        self.assertIsNotNone(
            pipeline_trace.trace_step_projection(ref, "step-health"))
        self.assertIsNone(pipeline_trace.trace_step_projection(ref, "metadata"))
        self.assertIsNone(
            pipeline_trace.trace_step_projection(ref, "trace-manifest"))
        self.assertIsNone(
            pipeline_trace.trace_step_projection(ref, "model-call-config"))
        self.assertIsNone(
            pipeline_trace.trace_step_projection(ref, "step999-not-real"))
        self.assertIsNone(
            pipeline_trace.trace_step_projection(ref, "../step1-phase-a"))

    def test_manifest_projection_surfaces_missing_steps(self):
        _d, ref = self._completed_trace()
        projection = pipeline_trace.trace_manifest_projection(ref)
        self.assertIn("step2-context", projection["missing_steps"])
        names = [row["step_name"] for row in projection["steps"]]
        self.assertIn("step2-context", names)
        self.assertIn("step-health", names)

    def test_step_projection_reports_oversized_markdown(self):
        d, ref = self._completed_trace()
        Path(os.path.join(d, "step1-phase-a.md")).write_text(
            "x" * (pipeline_trace.MAX_TRACE_TEXT_BYTES + 1),
            encoding="utf-8",
        )
        step = pipeline_trace.trace_step_projection(ref, "step1-phase-a")
        self.assertIsNone(step["markdown"])
        self.assertIn("file-too-large", step["errors"])

    def test_export_escapes_trace_content_and_omits_active_urls(self):
        _d, ref = self._completed_trace()
        html_doc, filename = pipeline_trace.trace_export_html(ref)
        self.assertTrue(filename.startswith("ora-trace-conv-walk-"))
        self.assertIn("Content-Security-Policy", html_doc)
        self.assertNotIn("alert(1)", html_doc)
        self.assertNotIn("https://example.test", html_doc)
        self.assertNotIn("sk-user-secret-key", html_doc)
        self.assertNotIn("system prompt secret", html_doc)
        self.assertIn("Markdown content redacted", html_doc)
        self.assertIn("sha256", html_doc)
        self.assertNotIn("<script", html_doc.lower())
        self.assertNotIn("href=", html_doc.lower())
        self.assertNotIn("<img", html_doc.lower())

    def test_list_trace_refs_filters_non_manifest_dirs(self):
        d, ref = self._completed_trace()
        os.makedirs(os.path.join(os.path.dirname(d), "not-a-trace"))
        self.assertEqual(pipeline_trace.list_trace_refs("conv-walk"), [ref])

    def test_list_trace_refs_holds_runtime_lock_for_discovery_and_resolution(self):
        d, ref = self._completed_trace()
        locked = {"active": False}
        observed = []

        class FakeLock:
            def __enter__(self):
                locked["active"] = True
                observed.append("enter")

            def __exit__(self, exc_type, exc, tb):
                observed.append("exit")
                locked["active"] = False

        def fake_lock(conversation_id):
            self.assertEqual(conversation_id, "conv-walk")
            return FakeLock()

        def fake_list_traces(conversation_id):
            self.assertEqual(conversation_id, "conv-walk")
            self.assertTrue(locked["active"], "enumeration must run under runtime lock")
            observed.append("list")
            return [d]

        def fake_resolve_trace_ref(candidate):
            self.assertEqual(candidate, ref)
            self.assertTrue(locked["active"], "resolution must run under runtime lock")
            observed.append("resolve")
            return d

        with mock.patch.object(pipeline_trace._rp, "conversation_lifecycle_lock", side_effect=fake_lock), \
             mock.patch.object(pipeline_trace, "list_traces", side_effect=fake_list_traces), \
             mock.patch.object(pipeline_trace, "resolve_trace_ref", side_effect=fake_resolve_trace_ref):
            self.assertEqual(pipeline_trace.list_trace_refs("conv-walk"), [ref])
        self.assertEqual(observed, ["enter", "list", "resolve", "exit"])


class TestTraceWalkServerRoutes(TraceManifestBase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ORCHESTRATOR.parent / "server"))
        import server  # noqa: WPS433
        cls.S = server

    def setUp(self):
        super().setUp()
        import orchestrator.pipeline_trace as opt  # noqa: WPS433
        patcher = mock.patch.object(opt, "TRACE_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_export_route_is_attachment_with_hardening_headers(self):
        d = self.start("conv-route")
        self.touch_step(d, "step1-phase-a")
        pipeline_trace.write_step_health(d, {}, 3, [])
        pipeline_trace.finalize_manifest(d, kind="chat", gear=3)
        turn = os.path.basename(d)
        client = self.S.app.test_client()
        response = client.get(f"/api/trace/export/conv-route/{turn}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers.get("Content-Disposition", ""))
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("default-src 'none'", response.headers.get("Content-Security-Policy", ""))

    def test_retention_route_preserves_lineage_fields(self):
        d = self.start("conv-route-pin")
        pipeline_trace.finalize_manifest(
            d, kind="framework-run", status_hint="completed",
            framework_id="fw", child_trace_refs=["conv-route-pin/child"],
        )
        turn = os.path.basename(d)
        client = self.S.app.test_client()
        response = client.post(
            "/api/trace/retention",
            json={"trace_ref": f"conv-route-pin/{turn}", "pinned": True},
        )
        self.assertEqual(response.status_code, 200)
        m = self.manifest(d)
        self.assertEqual(m["retention_state"], "pinned")
        self.assertEqual(m["framework_id"], "fw")
        self.assertEqual(m["child_trace_refs"], ["conv-route-pin/child"])

    def test_retention_route_requires_boolean_pinned(self):
        d = self.start("conv-route-schema")
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed")
        turn = os.path.basename(d)
        client = self.S.app.test_client()
        response = client.post(
            "/api/trace/retention",
            json={"trace_ref": f"conv-route-schema/{turn}", "pinned": "false"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.manifest(d)["retention_state"], "default")

    def test_retention_route_rejects_open_trace(self):
        d = self.start("conv-route-open-pin")
        turn = os.path.basename(d)
        client = self.S.app.test_client()
        response = client.post(
            "/api/trace/retention",
            json={"trace_ref": f"conv-route-open-pin/{turn}", "pinned": True},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.manifest(d)["retention_state"], "default")

    def test_probe_route_preserves_private_source_redaction(self):
        import trace_debug
        d = self.start("conv-route-private-probe", conversation_tag="private")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.write_step(d, "step1-phase-a", {"model_request": {
            "messages": [{"role": "user", "content": "private input"}],
            "endpoint_id": "test-endpoint", "provider": "test", "model": "m",
            "parameters": {}, "max_tokens": 10,
        }})
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        client = self.S.app.test_client()
        prepared_response = client.post(
            "/api/trace/probe/prepare",
            json={"trace_ref": ref, "step_name": "step1-phase-a"},
        )
        self.assertEqual(prepared_response.status_code, 200)
        prepared = json.loads(prepared_response.get_data(as_text=True))
        self.assertEqual(
            trace_debug._APPROVALS[prepared["approval_id"]]["request"]["conversation_tag"],
            "private",
        )
        approved_response = client.post(
            "/api/trace/probe/approve",
            json={
                "approval_id": prepared["approval_id"],
                "approval_digest": prepared["approval_digest"],
            },
        )
        self.assertEqual(approved_response.status_code, 200)
        with mock.patch.object(self.S, "load_config", return_value={}), \
             mock.patch.object(self.S, "get_endpoint", return_value=object()), \
             mock.patch.object(trace_debug, "endpoint_from_probe_envelope", return_value=object()), \
             mock.patch.object(self.S, "call_model", return_value="private probe result"):
            executed_response = client.post(
                "/api/trace/probe/execute",
                json={
                    "conversation_id": "conv-route-private-probe",
                    "approval_id": prepared["approval_id"],
                    "approval_digest": prepared["approval_digest"],
                },
            )
        self.assertEqual(executed_response.status_code, 200)
        executed = json.loads(executed_response.get_data(as_text=True))
        self.assertTrue(executed["ok"], executed)
        probe_manifest = self.manifest(
            pipeline_trace.resolve_trace_ref(executed["trace_ref"])
        )
        self.assertEqual(probe_manifest["redaction_level"], "private")



class TestExecutionGateTraceRefs(TraceManifestBase):
    def test_execution_gate_paused_entry_gets_exact_trace_ref(self):
        import tool_events
        d = self.start("conv-gate")
        ref = pipeline_trace.trace_ref_for_dir(d)
        captured = {}

        def fake_add_entry(entry):
            captured.update(entry)
            return SimpleNamespace(id="queue-1")

        with mock.patch("oversight_queue.add_entry", side_effect=fake_add_entry):
            qid = tool_events._queue_gate_entry(
                "danger", "hash", "needs approval", "delete it",
                {"conversation_id": "conv-gate", "trace_dir": d},
            )
        self.assertEqual(qid, "queue-1")
        self.assertEqual(captured["event"]["trace_ref"], ref)


class TestTraceDebugChunk3(TraceManifestBase):
    def test_contract_snapshot_preserves_complete_fields_and_survives_mutation(self):
        import trace_debug
        milestone = SimpleNamespace(
            id="M1", name="Failure diagnosis", mode="P-Debug",
            endpoint_produced="Trace-backed verdict",
            verification_criterion="Use execution-time contract only",
            drift_check_question="Stayed inside trace evidence?",
            output_format="Trace Diagnostic Report",
            gear=4,
            layers_covered=["1", "2"],
            required_prior=[],
            conditional_layers="Only if probe needed",
        )
        framework = SimpleNamespace(name="process-inference", file_path="/tmp/process-inference.md")
        snap = trace_debug.framework_contract_snapshot(framework, milestone, selected_mode="P-Debug")
        self.assertEqual(snap["capture_status"], "captured")
        fields = snap["canonical_fields"]
        self.assertEqual(fields["verification_criterion"], "Use execution-time contract only")
        self.assertEqual(fields["conditional_layers"], "Only if probe needed")
        before = snap["fingerprint"]
        milestone.verification_criterion = "MUTATED CONTRACT"
        after = trace_debug.framework_contract_snapshot(framework, milestone, selected_mode="P-Debug")
        self.assertNotEqual(before, after["fingerprint"])

    def test_oversize_contract_records_failure_not_truncated_contract(self):
        import trace_debug
        milestone = SimpleNamespace(
            id="M1", name="Huge", mode="P-Debug",
            endpoint_produced="x", verification_criterion="x" * (trace_debug.MAX_CONTRACT_BYTES + 1),
            drift_check_question="x", output_format="x", gear=4,
            layers_covered=[], required_prior=[], conditional_layers=None,
        )
        framework = SimpleNamespace(name="fw", file_path="/tmp/fw.md")
        snap = trace_debug.framework_contract_snapshot(framework, milestone, selected_mode="P-Debug")
        self.assertEqual(snap["capture_status"], "failed")
        self.assertNotIn("fingerprint", snap)

    def test_debug_prompt_rejects_cross_conversation_and_unavailable_contract(self):
        import trace_debug
        d = self.start("conv-debug")
        ref = pipeline_trace.trace_ref_for_dir(d)
        ok, msg = trace_debug.validate_same_conversation(ref, "other-conv")
        self.assertFalse(ok)
        prompt, meta = trace_debug.build_debug_prompt({"trace_ref": ref}, conversation_id="conv-debug")
        self.assertIn("CONTRACT_UNAVAILABLE", prompt)
        self.assertFalse(meta["contract_available"])

    def test_probe_approval_is_server_authoritative_one_shot(self):
        import trace_debug
        d = self.start("conv-probe")
        ref = pipeline_trace.trace_ref_for_dir(d)
        payload = {"model_request": {
            "messages": [{"role": "user", "content": "hi"}],
            "endpoint_id": "test-endpoint", "provider": "test", "model": "m", "parameters": {}, "max_tokens": 10,
        }}
        pipeline_trace.write_step(d, "step1-phase-a", payload)
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        prepared = trace_debug.prepare_probe({"trace_ref": ref, "step_name": "step1-phase-a", "cost_ceiling": 1000}, conversation_id="conv-probe")
        self.assertTrue(prepared["ok"])
        forged = trace_debug.consume_probe_approval(prepared["approval_id"], "bad", conversation_id="conv-probe")
        self.assertFalse(forged["ok"])
        approved = trace_debug.approve_probe(prepared["approval_id"], prepared["approval_digest"])
        self.assertTrue(approved["ok"])
        first = trace_debug.consume_probe_approval(prepared["approval_id"], prepared["approval_digest"], conversation_id="conv-probe")
        self.assertTrue(first["ok"])
        second = trace_debug.consume_probe_approval(prepared["approval_id"], prepared["approval_digest"], conversation_id="conv-probe")
        self.assertFalse(second["ok"])

    def test_not_replayable_probe_creates_no_probe_trace(self):
        import trace_debug
        d = self.start("conv-noreplay")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.write_step(d, "step1-phase-a", {"not": "an envelope"})
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        before = set(pipeline_trace.list_trace_refs("conv-noreplay"))
        prepared = trace_debug.prepare_probe({"trace_ref": ref, "step_name": "step1-phase-a"}, conversation_id="conv-noreplay")
        after = set(pipeline_trace.list_trace_refs("conv-noreplay"))
        self.assertEqual(prepared["status"], "NOT_REPLAYABLE")
        self.assertEqual(before, after)

    def test_execute_probe_consumes_before_trace_and_records_completed_probe(self):
        import trace_debug
        d = self.start("conv-exec-probe")
        ref = pipeline_trace.trace_ref_for_dir(d)
        payload = {"model_request": {
            "messages": [{"role": "user", "content": "hi"}],
            "endpoint_id": "test-endpoint", "provider": "test", "model": "m", "parameters": {}, "max_tokens": 10,
        }}
        pipeline_trace.write_step(d, "step1-phase-a", payload)
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        prepared = trace_debug.prepare_probe({"trace_ref": ref, "step_name": "step1-phase-a"}, conversation_id="conv-exec-probe")
        trace_debug.approve_probe(prepared["approval_id"], prepared["approval_digest"])
        result = trace_debug.execute_probe(
            prepared["approval_id"], prepared["approval_digest"],
            conversation_id="conv-exec-probe",
            model_executor=lambda req: "probe result")
        self.assertTrue(result["ok"])
        probe_dir = pipeline_trace.resolve_trace_ref(result["trace_ref"])
        probe = self.manifest(probe_dir)
        self.assertEqual(probe["trace_kind"], "trace-probe")
        self.assertEqual(probe["terminal_status"], "completed")
        self.assertEqual(probe["investigates_trace_ref"], ref)
        replay = trace_debug.execute_probe(
            prepared["approval_id"], prepared["approval_digest"],
            conversation_id="conv-exec-probe",
            model_executor=lambda req: "second")
        self.assertFalse(replay["ok"])

    def test_framework_contract_bundle_fails_if_any_child_unavailable(self):
        import trace_debug
        framework = SimpleNamespace(name="fw", file_path="/tmp/fw.md")
        ok = SimpleNamespace(
            id="M1", name="OK", mode="P-Debug", endpoint_produced="x",
            verification_criterion="x", drift_check_question="x", output_format="x",
            gear=4, layers_covered=[], required_prior=[], conditional_layers=None,
        )
        huge = SimpleNamespace(
            id="M2", name="Huge", mode="P-Debug", endpoint_produced="x",
            verification_criterion="x" * (trace_debug.MAX_CONTRACT_BYTES + 1),
            drift_check_question="x", output_format="x", gear=4,
            layers_covered=[], required_prior=[], conditional_layers=None,
        )
        bundle = trace_debug.framework_contract_bundle(framework, [ok, huge], selected_mode="P-Debug")
        self.assertEqual(bundle["capture_status"], "failed")
        self.assertIn("child_statuses", bundle)

    def test_debug_prompt_walks_all_steps_health_and_children(self):
        import trace_debug
        parent = self.start("conv-walk")
        child = self.start("conv-walk")
        child_ref = pipeline_trace.trace_ref_for_dir(child)
        pipeline_trace.write_step(child, "step1-phase-a", {"semantic_status": "pass"})
        pipeline_trace.finalize_manifest(child, kind="framework-milestone", status_hint="completed", gear=1)
        pipeline_trace.write_step(parent, "step1-phase-a", {"system_prompt": "s", "user_message": "u", "semantic_status": "pass"})
        pipeline_trace.write_step(parent, "step1-phase-b", {"semantic_status": "fail"})
        pipeline_trace.write_step_health(parent, {"step1-phase-a": (True, "ok"), "step1-phase-b": (False, "bad")}, 1, [])
        pipeline_trace.append_jsonl(parent, "model-call-config.jsonl", {"step": "step1-phase-a", "provider": "p", "model_id": "m", "effective_max_tokens": 10})
        parent_fields = {"mode": "P-Debug"}
        pipeline_trace.update_manifest_fields(parent, contract_snapshot={"capture_status": "captured", "canonical_fields": parent_fields, "fingerprint": trace_debug.digest(parent_fields)})
        pipeline_trace.finalize_manifest(parent, kind="chat", status_hint="completed", gear=1, child_trace_refs=[child_ref])
        ref = pipeline_trace.trace_ref_for_dir(parent)
        prompt, meta = trace_debug.build_debug_prompt({"trace_ref": ref}, conversation_id="conv-walk")
        self.assertTrue(meta["contract_available"])
        self.assertIn('"step_name": "step1-phase-a"', prompt)
        self.assertIn('"step_name": "step1-phase-b"', prompt)
        self.assertIn('"step_health"', prompt)
        self.assertIn(child_ref, prompt)
        self.assertIn('"boundary_table"', prompt)
        self.assertIn('"semantic_evidence": "fail"', prompt)

    def test_prepare_probe_uses_production_step_and_model_call_config(self):
        import trace_debug
        d = self.start("conv-prod-probe")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.write_step(d, "step1-phase-a", {"system_prompt": "sys", "user_message": "hello"})
        pipeline_trace.append_jsonl(d, "model-call-config.jsonl", {
            "step": "step1-phase-a", "endpoint_id": "production-test", "provider": "openrouter", "model_id": "model-x",
            "effective_max_tokens": 123, "sampling": {"temperature": 0.1},
        })
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        prepared = trace_debug.prepare_probe({"trace_ref": ref, "step_name": "step1-phase-a"}, conversation_id="conv-prod-probe")
        self.assertTrue(prepared["ok"], prepared)
        trace_debug.approve_probe(prepared["approval_id"], prepared["approval_digest"])
        seen = {}
        result = trace_debug.execute_probe(
            prepared["approval_id"], prepared["approval_digest"],
            conversation_id="conv-prod-probe",
            model_executor=lambda req: (seen.__setitem__("req", req) or "ok"))
        self.assertTrue(result["ok"])
        env = seen["req"]["envelope"]
        self.assertEqual(env["provider"], "openrouter")
        self.assertEqual(env["model"], "model-x")
        self.assertEqual(env["max_tokens"], 123)
        self.assertEqual(env["messages"][0]["role"], "system")

    def test_execute_probe_fails_closed_if_trace_creation_fails(self):
        import trace_debug
        d = self.start("conv-failclosed")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.write_step(d, "step1-phase-a", {"model_request": {
            "messages": [{"role": "user", "content": "hi"}],
            "endpoint_id": "test-endpoint", "provider": "test", "model": "m", "parameters": {}, "max_tokens": 10,
        }})
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        prepared = trace_debug.prepare_probe({"trace_ref": ref, "step_name": "step1-phase-a"}, conversation_id="conv-failclosed")
        trace_debug.approve_probe(prepared["approval_id"], prepared["approval_digest"])
        called = {"value": False}
        with mock.patch.object(pipeline_trace, "start_trace", return_value=None):
            result = trace_debug.execute_probe(
                prepared["approval_id"], prepared["approval_digest"],
                conversation_id="conv-failclosed",
                model_executor=lambda req: called.__setitem__("value", True))
        self.assertFalse(result["ok"])
        self.assertFalse(called["value"])

    def test_probe_manifest_writes_fail_closed_and_read_back(self):
        import trace_debug

        def prepare(conversation_id):
            d = self.start(conversation_id)
            ref = pipeline_trace.trace_ref_for_dir(d)
            pipeline_trace.write_step(d, "step1-phase-a", {"model_request": {
                "messages": [{"role": "user", "content": "hi"}],
                "endpoint_id": "test-endpoint", "provider": "test", "model": "m",
                "parameters": {}, "max_tokens": 10,
            }})
            pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
            prepared = trace_debug.prepare_probe(
                {"trace_ref": ref, "step_name": "step1-phase-a"},
                conversation_id=conversation_id,
            )
            trace_debug.approve_probe(prepared["approval_id"], prepared["approval_digest"])
            return prepared

        first = prepare("conv-probe-manifest-update")
        with mock.patch.object(pipeline_trace, "update_manifest_fields", return_value=None):
            update_result = trace_debug.execute_probe(
                first["approval_id"], first["approval_digest"],
                conversation_id="conv-probe-manifest-update",
                model_executor=lambda req: "should not run",
            )
        self.assertFalse(update_result["ok"])

        second = prepare("conv-probe-manifest-finalize")
        with mock.patch.object(trace_debug.pipeline_trace, "finalize_manifest", return_value=None):
            finalize_result = trace_debug.execute_probe(
                second["approval_id"], second["approval_digest"],
                conversation_id="conv-probe-manifest-finalize",
                model_executor=lambda req: "probe result",
            )
        self.assertTrue(finalize_result["ok"])
        self.assertEqual(finalize_result["status"], "completed")
        finalized = self.manifest(pipeline_trace.resolve_trace_ref(finalize_result["trace_ref"]))
        self.assertEqual(finalized["trace_kind"], "trace-probe")
        self.assertTrue(finalized["investigates_trace_ref"].startswith("conv-probe-manifest-finalize/"))
        self.assertEqual(finalized["expected_steps"], [
            "step-probe-prepare", "step-probe-approval",
            "step-probe-model-attempt", "step-probe-result", "step-health",
        ])
        self.assertEqual(set(finalized["actual_steps"]), {
            "step-probe-approval", "step-probe-model-attempt",
            "step-probe-prepare", "step-probe-result",
        })
        self.assertEqual(finalized["derived_artifacts"], ["step-health"])
        self.assertEqual(finalized["terminal_status"], "completed")

    def test_learning_library_schema_redacts_and_rejects_cross_conversation(self):
        import trace_debug
        d = self.start("conv-learn-schema")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        with mock.patch.object(trace_debug._rp, "DATA_DIR_STR", str(Path(self.tmp.name) / "data")):
            self.assertFalse(trace_debug.append_learning_entry({
                "conversation_id": "other", "trace_ref": ref, "verdict": "NO_DEFECT",
            }))
            self.assertTrue(trace_debug.append_learning_entry({
                "conversation_id": "conv-learn-schema", "trace_ref": ref,
                "verdict": "DEFECT_LOCALIZED", "root_cause": "retrieval gap",
                "extra": "must not persist", "correction_summary": "api_key=SECRET123",
            }))
            entries = trace_debug.list_learning_entries()
        self.assertEqual(len(entries), 1)
        self.assertNotIn("extra", entries[0])
        self.assertIn("[REDACTED]", entries[0]["correction_summary"])

    def test_natural_language_routing_is_exact_ref_and_default_off(self):
        import trace_debug
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(trace_debug.TRACE_DEBUG_NL_ENABLED_ENV, None)
            self.assertIsNone(trace_debug.parse_natural_language_request("please investigate conv-a/turn-a"))
        with mock.patch.dict(os.environ, {trace_debug.TRACE_DEBUG_NL_ENABLED_ENV: "1"}):
            payload = trace_debug.parse_natural_language_request("please investigate trace conv-a/turn-a")
            self.assertEqual(payload["trace_ref"], "conv-a/turn-a")
            self.assertIsNone(trace_debug.parse_natural_language_request("please investigate trace conv-a/turn-a and conv-b/turn-b"))

    def test_trace_debug_purge_unlocked_does_not_reacquire_lifecycle_lock(self):
        import trace_debug
        d = self.start("conv-deadlock")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        with mock.patch.object(trace_debug._rp, "DATA_DIR_STR", str(Path(self.tmp.name) / "data")):
            self.assertTrue(trace_debug.append_learning_entry({
                "conversation_id": "conv-deadlock", "trace_ref": ref,
                "verdict": "NO_DEFECT",
            }))
            with mock.patch.object(trace_debug._rp, "conversation_lifecycle_lock", side_effect=AssertionError("would deadlock")):
                result = trace_debug.purge_conversation_unlocked("conv-deadlock")
        self.assertEqual(result["removed"], 1)

    def test_debug_prompt_is_aggregate_bounded_and_marks_truncation(self):
        import trace_debug
        d = self.start("conv-bound")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.write_step(d, "step1-phase-a", {
            "system_prompt": "s" * 300000,
            "user_message": "u" * 300000,
            "raw_response": "r" * 300000,
        }, markdown="m" * 300000)
        fields = {"mode": "P-Debug"}
        pipeline_trace.update_manifest_fields(d, contract_snapshot={"capture_status": "captured", "canonical_fields": fields, "fingerprint": trace_debug.digest(fields)})
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        prompt, meta = trace_debug.build_debug_prompt({"trace_ref": ref}, conversation_id="conv-bound")
        self.assertTrue(meta["contract_available"])
        self.assertLess(len(prompt), trace_debug.MAX_DEBUG_CONTEXT_CHARS + 25000)
        self.assertIn('"evidence_budget"', prompt)
        self.assertIn("TRACE_DEBUG_EVIDENCE_TRUNCATED", prompt)

    def test_framework_parent_debug_walks_child_steps_and_boundary(self):
        import trace_debug
        parent = self.start("conv-parent")
        child = self.start("conv-parent")
        child_ref = pipeline_trace.trace_ref_for_dir(child)
        pipeline_trace.write_step(child, "step1-phase-a", {"semantic_status": "fail", "user_message": "child evidence"})
        pipeline_trace.write_step_health(child, {"step1-phase-a": (False, "bad child")}, 1, [])
        pipeline_trace.append_jsonl(child, "model-call-config.jsonl", {"step": "step1-phase-a", "provider": "p", "model_id": "m", "effective_max_tokens": 10})
        child_fields = {"mode": "P-Debug"}
        pipeline_trace.update_manifest_fields(child, contract_snapshot={"capture_status": "captured", "canonical_fields": child_fields, "fingerprint": trace_debug.digest(child_fields)})
        parent_ref = pipeline_trace.trace_ref_for_dir(parent)
        pipeline_trace.finalize_manifest(child, kind="framework-milestone", status_hint="completed", gear=1, parent_trace_ref=parent_ref)
        parent_fields = {"mode": "P-Debug"}
        pipeline_trace.update_manifest_fields(parent, contract_snapshot={"capture_status": "captured", "canonical_fields": parent_fields, "fingerprint": trace_debug.digest(parent_fields)})
        pipeline_trace.finalize_manifest(parent, kind="framework-run", status_hint="completed", child_trace_refs=[child_ref])
        ref = pipeline_trace.trace_ref_for_dir(parent)
        prompt, _meta = trace_debug.build_debug_prompt({"trace_ref": ref}, conversation_id="conv-parent")
        self.assertIn(child_ref, prompt)
        self.assertIn('"user_message": "child evidence"', prompt)
        self.assertIn('"semantic_evidence": "fail"', prompt)
        self.assertIn('"model_call_configs"', prompt)

    def test_child_walk_rejects_foreign_and_nonreciprocal_children(self):
        import trace_debug
        parent = self.start("conv-a")
        foreign = self.start("conv-b")
        foreign_ref = pipeline_trace.trace_ref_for_dir(foreign)
        pipeline_trace.write_step(foreign, "step1-secret", {"secret": "SECRET_FROM_B"})
        pipeline_trace.finalize_manifest(foreign, kind="framework-milestone", status_hint="completed", gear=1)
        pipeline_trace.update_manifest_fields(parent, child_trace_refs=[foreign_ref])
        pipeline_trace.finalize_manifest(parent, kind="framework-run", status_hint="completed")
        parent_ref = pipeline_trace.trace_ref_for_dir(parent)
        prompt, _meta = trace_debug.build_debug_prompt({"trace_ref": parent_ref}, conversation_id="conv-a")
        self.assertNotIn("SECRET_FROM_B", prompt)
        self.assertIn("child trace conversation mismatch", prompt)

    def test_child_walk_marks_omitted_child_limit(self):
        import trace_debug
        parent = self.start("conv-limit")
        refs = [f"conv-limit/missing-{i}" for i in range(trace_debug.MAX_DEBUG_CHILDREN + 1)]
        pipeline_trace.update_manifest_fields(parent, child_trace_refs=refs)
        pipeline_trace.finalize_manifest(parent, kind="framework-run", status_hint="completed")
        ref = pipeline_trace.trace_ref_for_dir(parent)
        prompt, _meta = trace_debug.build_debug_prompt({"trace_ref": ref}, conversation_id="conv-limit")
        self.assertIn("child trace count limit reached", prompt)

    def test_probe_provider_failure_is_error_not_completed(self):
        import trace_debug
        d = self.start("conv-provider-error")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.write_step(d, "step1-phase-a", {"model_request": {
            "messages": [{"role": "user", "content": "hi"}],
            "endpoint_id": "test-endpoint", "provider": "test", "model": "m",
            "parameters": {}, "max_tokens": 10,
        }})
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        prepared = trace_debug.prepare_probe({"trace_ref": ref, "step_name": "step1-phase-a"}, conversation_id="conv-provider-error")
        trace_debug.approve_probe(prepared["approval_id"], prepared["approval_digest"])
        result = trace_debug.execute_probe(
            prepared["approval_id"], prepared["approval_digest"],
            conversation_id="conv-provider-error",
            model_executor=lambda _req: "[Error] provider unavailable",
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "error")
        probe = self.manifest(pipeline_trace.resolve_trace_ref(result["trace_ref"]))
        self.assertEqual(probe["terminal_status"], "error")

    def test_probe_provider_error_finalization_readback_persists_terminal_error(self):
        import trace_debug
        d = self.start("conv-probe-error-finalization")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.write_step(d, "step1-phase-a", {"model_request": {
            "messages": [{"role": "user", "content": "hi"}],
            "endpoint_id": "test-endpoint", "provider": "test", "model": "m",
            "parameters": {}, "max_tokens": 10,
        }})
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        prepared = trace_debug.prepare_probe(
            {"trace_ref": ref, "step_name": "step1-phase-a"},
            conversation_id="conv-probe-error-finalization",
        )
        trace_debug.approve_probe(prepared["approval_id"], prepared["approval_digest"])
        with mock.patch.object(trace_debug.pipeline_trace, "TRACE_ROOT", self.root), \
             mock.patch.object(trace_debug.pipeline_trace, "finalize_manifest", return_value=None):
            result = trace_debug.execute_probe(
                prepared["approval_id"], prepared["approval_digest"],
                conversation_id="conv-probe-error-finalization",
                model_executor=lambda _req: "[Error] provider unavailable",
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "error")
        manifest = self.manifest(pipeline_trace.resolve_trace_ref(result["trace_ref"]))
        self.assertEqual(manifest["terminal_status"], "error")

    def test_contract_budget_preserves_exact_captured_clause(self):
        import trace_debug
        d = self.start("conv-contract-exact")
        ref = pipeline_trace.trace_ref_for_dir(d)
        fields = {"mode": "P-Debug", "verification_criteria": "x" * 20000}
        pipeline_trace.update_manifest_fields(
            d,
            contract_snapshot={
                "capture_status": "captured",
                "canonical_fields": fields,
                "fingerprint": trace_debug.digest(fields),
            },
        )
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        prompt, meta = trace_debug.build_debug_prompt({"trace_ref": ref}, conversation_id="conv-contract-exact")
        self.assertTrue(meta["contract_available"])
        self.assertIn("x" * 20000, prompt)
        self.assertNotIn("TRACE_DEBUG_EVIDENCE_TRUNCATED", prompt.split('"contract_snapshot"', 1)[-1].split('"selected_step"', 1)[0])

    def test_step_health_boolean_false_is_semantic_failure(self):
        import trace_debug
        boundary = trace_debug._boundary_table(
            {"expected_steps": ["step1"], "actual_steps": ["step1"], "derived_artifacts": ["step-health"]},
            [
                {"step_name": "step1", "json_present": True, "payload": {"ok": False}, "errors": []},
                {"step_name": "step-health", "payload": {"step_health": {"step1": {"ok": False, "reason": "bad"}}}},
            ],
        )
        self.assertEqual(boundary[0]["semantic_evidence"], "fail")

    def test_trace_debug_and_probe_expected_artifacts_are_explicit(self):
        d = self.start("conv-kinds")
        pipeline_trace.write_step(d, "step-debug-request", {"trace_ref": "conv-kinds/target"})
        pipeline_trace.write_step(d, "step-debug-result", {"status": "completed"})
        pipeline_trace.finalize_manifest(d, kind="trace-debug", status_hint="completed")
        debug_manifest = self.manifest(d)
        self.assertEqual(debug_manifest["expected_steps"], ["step-debug-request", "step-debug-result"])
        p = self.start("conv-kinds")
        for name in ("step-probe-prepare", "step-probe-approval", "step-probe-model-attempt", "step-probe-result"):
            pipeline_trace.write_step(p, name, {"ok": True})
        pipeline_trace.write_step_health(p, {"step-probe-result": (True, "ok")}, 0, [])
        pipeline_trace.finalize_manifest(p, kind="trace-probe", status_hint="completed")
        probe_manifest = self.manifest(p)
        self.assertIn("step-health", probe_manifest["expected_steps"])
        self.assertEqual(probe_manifest["missing_steps"] if "missing_steps" in probe_manifest else [], [])

    def test_private_conversation_cannot_write_learning_entry(self):
        import trace_debug
        d = self.start("conv-private-learning", conversation_tag="private")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        self.assertFalse(trace_debug.append_learning_entry({
            "conversation_id": "conv-private-learning",
            "trace_ref": ref,
            "verdict": "NO_DEFECT",
        }))

    def test_boundary_last_known_good_stops_before_first_failure(self):
        import trace_debug
        manifest = {"expected_steps": ["step1", "step2", "step3"], "actual_steps": ["step1", "step2", "step3"], "derived_artifacts": []}
        steps = [
            {"step_name": "step1", "json_present": True, "payload": {"semantic_status": "pass"}, "errors": []},
            {"step_name": "step2", "json_present": True, "payload": {"semantic_status": "fail"}, "errors": []},
            {"step_name": "step3", "json_present": True, "payload": {"semantic_status": "pass"}, "errors": []},
        ]
        boundary = trace_debug._boundary_table(manifest, steps)
        self.assertEqual(trace_debug._last_before_first_failure(boundary, "semantic_evidence"), "step1")

    def test_probe_rejects_ambiguous_or_incomplete_call_mapping(self):
        import trace_debug
        d = self.start("conv-ambig-probe")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.write_step(d, "step1-phase-a", {"system_prompt": "sys", "user_message": "hello"})
        pipeline_trace.append_jsonl(d, "model-call-config.jsonl", {"step": "other", "provider": "p", "model_id": "m", "effective_max_tokens": 10})
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        prepared = trace_debug.prepare_probe({"trace_ref": ref, "step_name": "step1-phase-a"}, conversation_id="conv-ambig-probe")
        self.assertEqual(prepared["status"], "NOT_REPLAYABLE")
        d2 = self.start("conv-ambig-probe")
        ref2 = pipeline_trace.trace_ref_for_dir(d2)
        pipeline_trace.write_step(d2, "step1-phase-a", {"system_prompt": "sys", "user_message": "hello"})
        for _ in range(2):
            pipeline_trace.append_jsonl(d2, "model-call-config.jsonl", {"step": "step1-phase-a", "provider": "p", "model_id": "m", "effective_max_tokens": 10})
        pipeline_trace.finalize_manifest(d2, kind="chat", status_hint="completed", gear=1)
        prepared2 = trace_debug.prepare_probe({"trace_ref": ref2, "step_name": "step1-phase-a"}, conversation_id="conv-ambig-probe")
        self.assertEqual(prepared2["status"], "NOT_REPLAYABLE")
        d3 = self.start("conv-ambig-probe")
        ref3 = pipeline_trace.trace_ref_for_dir(d3)
        pipeline_trace.write_step(d3, "step1-phase-a", {"system_prompt": "sys only"})
        pipeline_trace.append_jsonl(d3, "model-call-config.jsonl", {"step": "step1-phase-a", "provider": "p", "model_id": "m", "effective_max_tokens": 10})
        pipeline_trace.finalize_manifest(d3, kind="chat", status_hint="completed", gear=1)
        prepared3 = trace_debug.prepare_probe({"trace_ref": ref3, "step_name": "step1-phase-a"}, conversation_id="conv-ambig-probe")
        self.assertEqual(prepared3["status"], "NOT_REPLAYABLE")

    def test_probe_applies_prompt_delta_and_enforces_cost_ceiling(self):
        import trace_debug
        d = self.start("conv-delta-probe")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.write_step(d, "step1-phase-a", {"system_prompt": "sys", "user_message": "hello"})
        pipeline_trace.append_jsonl(d, "model-call-config.jsonl", {"step": "step1-phase-a", "endpoint_id": "test-endpoint", "provider": "p", "model_id": "m", "effective_max_tokens": 10})
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        too_low = trace_debug.prepare_probe({"trace_ref": ref, "step_name": "step1-phase-a", "cost_ceiling": 1}, conversation_id="conv-delta-probe")
        self.assertEqual(too_low["status"], "COST_EXCEEDED")
        prepared = trace_debug.prepare_probe({"trace_ref": ref, "step_name": "step1-phase-a", "prompt_delta": "try shorter", "cost_ceiling": 1000}, conversation_id="conv-delta-probe")
        self.assertTrue(prepared["ok"], prepared)
        trace_debug.approve_probe(prepared["approval_id"], prepared["approval_digest"])
        seen = {}
        result = trace_debug.execute_probe(prepared["approval_id"], prepared["approval_digest"], conversation_id="conv-delta-probe", model_executor=lambda req: (seen.__setitem__("req", req) or "ok"))
        self.assertTrue(result["ok"])
        contents = [m["content"] for m in seen["req"]["envelope"]["messages"]]
        self.assertTrue(any("try shorter" in c for c in contents))

    def test_learning_records_require_single_verdict_field_and_store_fingerprints(self):
        import trace_debug
        d = self.start("conv-verdict-safe")
        ref = pipeline_trace.trace_ref_for_dir(d)
        fields = {"framework_fingerprint": "ffp"}
        pipeline_trace.update_manifest_fields(d, framework_id="fw", mode="P-Debug", contract_snapshot={"capture_status": "captured", "fingerprint": trace_debug.digest(fields), "canonical_fields": fields})
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        with mock.patch.object(trace_debug._rp, "DATA_DIR_STR", str(Path(self.tmp.name) / "data")):
            self.assertFalse(trace_debug.record_diagnosis_learning("conv-verdict-safe", ref, "Could be NO_DEFECT but maybe DEFECT_LOCALIZED"))
            self.assertFalse(trace_debug.record_diagnosis_learning("conv-verdict-safe", ref, "VERDICT: NO_DEFECT\nVERDICT: BAD_DRAW"))
            self.assertTrue(trace_debug.record_diagnosis_learning("conv-verdict-safe", ref, "VERDICT: NO_DEFECT\nFAILING STEP: none\nVERIFICATION PROBE: not needed"))
            entries = trace_debug.list_learning_entries()
        self.assertEqual(entries[0]["verdict"], "NO_DEFECT")
        self.assertEqual(entries[0]["contract_fingerprint"], trace_debug.digest(fields))
        self.assertEqual(entries[0]["framework_fingerprint"], "ffp")
        self.assertEqual(entries[0]["verification_probe"], "not needed")

    def test_learning_library_purge_physically_removes_conversation_records(self):
        import trace_debug
        d1 = self.start("conv-learn")
        ref1 = pipeline_trace.trace_ref_for_dir(d1)
        pipeline_trace.finalize_manifest(d1, kind="chat", status_hint="completed", gear=1)
        d2 = self.start("other")
        ref2 = pipeline_trace.trace_ref_for_dir(d2)
        pipeline_trace.finalize_manifest(d2, kind="chat", status_hint="completed", gear=1)
        store = Path(self.tmp.name) / "data" / "trace-debug" / "learning-library.jsonl"
        with mock.patch.object(trace_debug._rp, "DATA_DIR_STR", str(Path(self.tmp.name) / "data")):
            self.assertTrue(trace_debug.append_learning_entry({
                "conversation_id": "conv-learn", "trace_ref": ref1,
                "verdict": "NO_DEFECT", "root_cause": "none",
            }))
            self.assertTrue(trace_debug.append_learning_entry({
                "conversation_id": "other", "trace_ref": ref2,
                "verdict": "DEFECT_LOCALIZED", "root_cause": "retrieval gap",
            }))
            result = trace_debug.purge_conversation("conv-learn")
            self.assertEqual(result["removed"], 1)
            text = store.read_text(encoding="utf-8")
            self.assertNotIn("conv-learn", text)
            self.assertIn("other", text)

    def test_debug_budget_marks_omitted_child_contracts_unavailable(self):
        import trace_debug
        contract = {
            "capture_status": "captured",
            "canonical_fields": {"verification_criterion": "x" * 50000},
            "fingerprint": trace_debug.digest({"verification_criterion": "x" * 50000}),
        }
        context = {
            "contract_snapshot": contract,
            "contract_unavailable": None,
            "trace_walk": {
                "trace_ref": "conv-budget/turn",
                "manifest": {"trace_ref": "conv-budget/turn"},
                "raw_manifest_fields": {"contract_snapshot": contract},
                "boundary_table": [],
                "boundary_summary": {},
                "child_traces": [
                    {"trace_ref": f"conv-budget/child-{i}", "manifest": {},
                     "raw_manifest_fields": {"contract_snapshot": contract},
                     "boundary_table": [], "boundary_summary": {},
                     "steps": [{"markdown": "x" * 100000}]}
                    for i in range(4)
                ],
            },
        }
        bounded = trace_debug._apply_debug_budget(context)
        self.assertIsNotNone(bounded.get("contract_unavailable"))
        children = bounded["trace_walk"]["child_traces"]
        self.assertTrue(all(c["raw_manifest_fields"]["contract_snapshot"] is None for c in children))
        self.assertTrue(all(c["raw_manifest_fields"]["contract_capture_error"] for c in children))

    def test_mode_contract_refresh_uses_recorded_final_gear(self):
        import trace_debug
        d = self.start("conv-mode-gear")
        pipeline_trace.write_step_health(d, {"step3": (True, "ok")}, 3, [])
        trace_debug.refresh_mode_contract_snapshot(
            d, "P-Debug", "## VERIFICATION CRITERIA\n\n- criteria", 4)
        manifest = self.manifest(d)
        self.assertEqual(manifest["contract_snapshot"]["canonical_fields"]["gear"], 3)

    def test_framework_fingerprint_changes_with_source_content(self):
        import trace_debug
        source = Path(self.tmp.name) / "framework.md"
        source.write_text("contract one", encoding="utf-8")
        framework = SimpleNamespace(name="fw", file_path=str(source), raw_markdown="contract one")
        milestone = SimpleNamespace(id="m", name="M", verification_criterion="ok")
        first = trace_debug.framework_contract_snapshot(framework, milestone)
        source.write_text("contract two", encoding="utf-8")
        second = trace_debug.framework_contract_snapshot(framework, milestone)
        self.assertEqual(
            first["canonical_fields"]["framework_fingerprint"],
            second["canonical_fields"]["framework_fingerprint"],
        )
        framework.raw_markdown = "contract two"
        third = trace_debug.framework_contract_snapshot(framework, milestone)
        self.assertNotEqual(
            first["canonical_fields"]["framework_fingerprint"],
            third["canonical_fields"]["framework_fingerprint"],
        )

    def test_prior_learning_requires_matching_contract_versions(self):
        import trace_debug
        records = [
            {"trace_ref": "old/one", "framework_id": "fw", "framework_fingerprint": "new-fw", "contract_fingerprint": "new-contract", "verdict": "NO_DEFECT"},
            {"trace_ref": "old/two", "framework_id": "fw", "framework_fingerprint": "old-fw", "contract_fingerprint": "new-contract", "verdict": "NO_DEFECT"},
        ]
        with mock.patch.object(trace_debug, "list_learning_entries", return_value=records):
            kept = trace_debug._prior_learning(
                "current/turn", {"framework_id": "fw", "mode": "P-Debug"},
                framework_fingerprint="new-fw", contract_fingerprint="new-contract",
            )
        self.assertEqual([entry["trace_ref"] for entry in kept], ["old/one"])

    def test_probe_cli_delta_does_not_consume_cost_option(self):
        import trace_debug
        parsed = trace_debug.parse_probe_cli_command(
            "/trace-probe prepare conv/turn step1 --delta try shorter --cost-ceiling 100"
        )
        self.assertEqual(parsed["prompt_delta"], "try shorter")
        self.assertEqual(parsed["cost_ceiling"], "100")
        with mock.patch.object(
            trace_debug,
            "_replay_envelope",
            return_value=({"messages": [{"role": "user", "content": "hello"}], "endpoint_id": "e", "provider": "p", "model": "m", "parameters": {}, "max_tokens": 1}, ""),
        ):
            rejected = trace_debug.prepare_probe(
                {"trace_ref": "conv-delta/turn", "step_name": "step1", "prompt_delta": "x" * (trace_debug.MAX_PROBE_DELTA_CHARS + 1)},
                conversation_id="conv-delta",
            )
        self.assertEqual(rejected["status"], "REJECTED")

    def test_probe_binds_physical_context_and_records_non_lineage_ref(self):
        import trace_debug
        d = self.start("conv-probe-context")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.write_step(d, "step1-phase-a", {"system_prompt": "sys", "user_message": "hello"})
        pipeline_trace.append_jsonl(d, "model-call-config.jsonl", {
            "step": "step1-phase-a", "endpoint_id": "test-endpoint",
            "provider": "p", "model_id": "m", "effective_max_tokens": 10,
        })
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        prepared = trace_debug.prepare_probe({"trace_ref": ref, "step_name": "step1-phase-a"}, conversation_id="conv-probe-context")
        self.assertTrue(prepared["ok"], prepared)
        trace_debug.approve_probe(prepared["approval_id"], prepared["approval_digest"])
        seen = {}
        def executor(request):
            import boot
            seen["trace_dir"] = boot._TURN_TRACE_DIR_CV.get()
            return "ok"
        result = trace_debug.execute_probe(
            prepared["approval_id"], prepared["approval_digest"],
            conversation_id="conv-probe-context", model_executor=executor,
        )
        self.assertTrue(result["ok"], result)
        probe_dir = pipeline_trace.resolve_trace_ref(result["trace_ref"])
        self.assertEqual(seen["trace_dir"], probe_dir)
        source = self.manifest(d)
        self.assertIn(result["trace_ref"], source["probe_trace_refs"])
        self.assertNotIn(result["trace_ref"], source["child_trace_refs"])

    def test_probe_origin_requires_same_conversation_debug_reciprocity(self):
        import trace_debug
        target = self.start("conv-origin-a")
        target_ref = pipeline_trace.trace_ref_for_dir(target)
        pipeline_trace.write_step(target, "step1-phase-a", {"model_request": {
            "messages": [{"role": "user", "content": "hello"}],
            "endpoint_id": "test-endpoint", "provider": "test", "model": "m",
            "parameters": {}, "max_tokens": 10,
        }})
        pipeline_trace.finalize_manifest(target, kind="chat", status_hint="completed", gear=1)
        foreign_origin = self.start("conv-origin-b")
        foreign_ref = pipeline_trace.trace_ref_for_dir(foreign_origin)
        pipeline_trace.update_manifest_fields(
            foreign_origin, trace_kind="trace-debug", investigates_trace_ref=target_ref)
        pipeline_trace.finalize_manifest(foreign_origin, kind="trace-debug", status_hint="completed")
        prepared = trace_debug.prepare_probe({
            "trace_ref": target_ref, "step_name": "step1-phase-a",
            "origin_trace_ref": foreign_ref,
        }, conversation_id="conv-origin-a")
        self.assertEqual(prepared["status"], "REJECTED")
        self.assertEqual(self.manifest(foreign_origin).get("probe_trace_refs"), [])

    def test_probe_required_result_artifact_fails_closed(self):
        import trace_debug
        d = self.start("conv-required-probe")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.write_step(d, "step1-phase-a", {"model_request": {
            "messages": [{"role": "user", "content": "hello"}],
            "endpoint_id": "test-endpoint", "provider": "test", "model": "m",
            "parameters": {}, "max_tokens": 10,
        }})
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        prepared = trace_debug.prepare_probe({"trace_ref": ref, "step_name": "step1-phase-a"}, conversation_id="conv-required-probe")
        trace_debug.approve_probe(prepared["approval_id"], prepared["approval_digest"])
        original_write = pipeline_trace.write_step
        def drop_result(trace_dir, step_name, payload, markdown=None):
            if step_name != "step-probe-result":
                original_write(trace_dir, step_name, payload, markdown)
        with mock.patch.object(pipeline_trace, "write_step", side_effect=drop_result):
            result = trace_debug.execute_probe(
                prepared["approval_id"], prepared["approval_digest"],
                conversation_id="conv-required-probe", model_executor=lambda _req: "ok")
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "error")
        probe = self.manifest(pipeline_trace.resolve_trace_ref(result["trace_ref"]))
        self.assertEqual(probe["terminal_status"], "error")

    def test_probe_execute_rejection_is_recorded_on_latest_debug_trace(self):
        import trace_debug
        d = self.start("conv-rejection-events")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.update_manifest_fields(d, trace_kind="trace-debug", investigates_trace_ref="conv-rejection-events/target")
        pipeline_trace.finalize_manifest(d, kind="trace-debug", status_hint="completed")
        rejected = trace_debug.consume_probe_approval("forged", "bad", conversation_id="conv-rejection-events")
        self.assertFalse(rejected["ok"])
        events = trace_debug._read_jsonl_records_locked(Path(d), "trace-probe-events.jsonl")
        self.assertTrue(any(event.get("event") == "execute_rejected" for event in events))

    def test_learning_boundary_redacts_bounds_and_reports_corruption(self):
        import trace_debug
        d = self.start("conv-learning-boundary")
        ref = pipeline_trace.trace_ref_for_dir(d)
        pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
        data_dir = Path(self.tmp.name) / "data"
        with mock.patch.object(trace_debug._rp, "DATA_DIR_STR", str(data_dir)):
            self.assertFalse(trace_debug.append_learning_entry({
                "conversation_id": "conv-learning-boundary", "trace_ref": ref,
                "verdict": "NO_DEFECT", "root_cause": "invented class",
            }))
            self.assertTrue(trace_debug.append_learning_entry({
                "conversation_id": "conv-learning-boundary", "trace_ref": ref,
                "verdict": "NO_DEFECT", "root_cause": "none",
                "failing_step": "api_key=SECRET " + "x" * 1000,
            }))
            store = Path(trace_debug.learning_library_path())
            with store.open("a", encoding="utf-8") as handle:
                handle.write("not-json\n")
                handle.write(json.dumps({"schema_version": 999, "conversation_id": "bad"}) + "\n")
            entries = trace_debug.list_learning_entries()
            status = trace_debug.learning_library_status()
        self.assertEqual(len(entries), 1)
        self.assertNotIn("SECRET", json.dumps(entries))
        self.assertLessEqual(len(entries[0]["failing_step"]), 200)
        self.assertEqual(status["malformed_records"], 1)
        self.assertEqual(status["unsupported_schema_records"], 1)

    def test_seeded_four_verdict_learning_paths_are_unambiguous(self):
        import trace_debug
        outputs = {
            "DEFECT_LOCALIZED": "retrieval gap",
            "BAD_DRAW": "model bad-draw",
            "CONTRACT_MISMATCH": "framework underspecification",
            "NO_DEFECT": "none",
        }
        with mock.patch.object(trace_debug._rp, "DATA_DIR_STR", str(Path(self.tmp.name) / "data")):
            for index, (verdict, root_cause) in enumerate(outputs.items()):
                d = self.start("conv-seeded-verdicts")
                ref = pipeline_trace.trace_ref_for_dir(d)
                fields = {"framework_fingerprint": "fw-v1", "mode": "P-Debug"}
                pipeline_trace.update_manifest_fields(
                    d, framework_id="fw", mode="P-Debug",
                    contract_snapshot={"capture_status": "captured", "canonical_fields": fields,
                                       "fingerprint": trace_debug.digest(fields)})
                pipeline_trace.finalize_manifest(d, kind="trace-debug", status_hint="completed", gear=1)
                self.assertTrue(trace_debug.record_diagnosis_learning(
                    "conv-seeded-verdicts", ref,
                    f"VERDICT: {verdict}\nROOT CAUSE: {root_cause}\nFAILING STEP: none\nVERIFICATION PROBE: none"))
            entries = trace_debug.list_learning_entries()
        self.assertEqual({entry["verdict"] for entry in entries}, set(outputs))

    def test_probe_expiry_mutation_and_concurrent_execution_are_rejected_once(self):
        import trace_debug
        def make_source(conversation):
            d = self.start(conversation)
            ref = pipeline_trace.trace_ref_for_dir(d)
            pipeline_trace.write_step(d, "step1-phase-a", {"model_request": {
                "messages": [{"role": "user", "content": "hello"}],
                "endpoint_id": "test-endpoint", "provider": "test", "model": "m",
                "parameters": {}, "max_tokens": 10,
            }})
            pipeline_trace.finalize_manifest(d, kind="chat", status_hint="completed", gear=1)
            return d, ref
        expired_dir, expired_ref = make_source("conv-expiry")
        expired = trace_debug.prepare_probe({"trace_ref": expired_ref, "step_name": "step1-phase-a"}, conversation_id="conv-expiry")
        trace_debug._APPROVALS[expired["approval_id"]]["request"]["expires_at"] = 0
        self.assertFalse(trace_debug.approve_probe(expired["approval_id"], expired["approval_digest"])["ok"])
        mutated_dir, mutated_ref = make_source("conv-mutation")
        mutated = trace_debug.prepare_probe({"trace_ref": mutated_ref, "step_name": "step1-phase-a"}, conversation_id="conv-mutation")
        trace_debug.approve_probe(mutated["approval_id"], mutated["approval_digest"])
        pipeline_trace.append_jsonl(mutated_dir, "model-call-config.jsonl", {"step": "step1-phase-a", "endpoint_id": "changed"})
        self.assertEqual(trace_debug.execute_probe(mutated["approval_id"], mutated["approval_digest"], conversation_id="conv-mutation").get("status"), "REJECTED")
        _concurrent_dir, concurrent_ref = make_source("conv-concurrent")
        concurrent = trace_debug.prepare_probe({"trace_ref": concurrent_ref, "step_name": "step1-phase-a"}, conversation_id="conv-concurrent")
        trace_debug.approve_probe(concurrent["approval_id"], concurrent["approval_digest"])
        results = []
        threads = [threading.Thread(target=lambda: results.append(trace_debug.execute_probe(
            concurrent["approval_id"], concurrent["approval_digest"],
            conversation_id="conv-concurrent", model_executor=lambda _req: "ok"))) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sum(bool(result.get("ok")) for result in results), 1)


class TestTraceCompletenessV5Behavior(TraceManifestBase):
    """Behavioral coverage through the real Gear and CLI/server funnels.

    Production functions under test are never replaced. The only call seams
    replaced below are model, web-search, retrieval, embedding, and Chroma
    boundaries; trace failures use real filesystem permissions.
    """

    CONFIG_NAME = "qwen-9b-only"

    @classmethod
    def setUpClass(cls):
        import boot
        sys.path.insert(0, str(ORCHESTRATOR.parent / "server"))
        import server
        cls.boot = boot
        cls.S = server

    def setUp(self):
        super().setUp()
        import orchestrator.pipeline_trace as opt
        for mod in (self.boot.pipeline_trace, opt):
            patcher = mock.patch.object(mod, "TRACE_ROOT", self.root)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.opt = opt
        self.provider_calls = []
        self.provider_lock = threading.Lock()
        self.emit_flagged_claim = False
        self.emit_web_intent = False
        self.emit_supplement = False
        self.supplement_sent = False

    @staticmethod
    def _long(text):
        return text + "\n\n" + ("Substantive production-path evidence. " * 24)

    def _provider(self, messages, _endpoint, images=None):
        snapshot = [dict(m) for m in messages]
        with self.provider_lock:
            self.provider_calls.append(snapshot)
        system = str(messages[0].get("content") or "") if messages else ""
        user = str(messages[-1].get("content") or "") if messages else ""
        low_system = system.lower()
        low_user = user.lower()

        if "ambiguity_mode:" in low_system:
            raw = user.split("[Current prompt]\n")[-1].strip()
            return (
                "### CLEANED PROMPT (Operational Notation)\n" + raw +
                "\n\n### CLEANED PROMPT (Natural Language)\n" + raw +
                "\n\n### CORRECTIONS LOG\nNone.\n\n"
                "### INFERRED ITEMS\nNone."
            )
        if "identifying web search intents" in low_system:
            if self.emit_web_intent:
                return (
                    "INTENTS:\n- query: current trace evidence\n"
                    "  justification: Grounds the requested factual angle."
                )
            return "INTENTS:\n(none)"
        if "light factual-sanity check" in low_system:
            return "FLAGS:\n(none)"
        if "checking whether web search results contradict" in low_system:
            return "CONFLICTS:\n(none)"
        if "scanning a revised analysis" in low_system:
            return "EXTRACTED:\n(none)"

        if (self.emit_supplement and not self.supplement_sent
                and user.strip() == "gear3 feature request"):
            self.supplement_sent = True
            return self._long(
                "## SUPPLEMENTAL RAG REQUEST\n"
                "gap_statement: Need a local evidence record\n"
                "query_terms: trace evidence source\n"
                "why_it_matters: Grounds the analyst conclusion"
            )
        if "supplemental rag result" in low_user:
            return self._long("## ANALYSIS\nSupplement incorporated into analysis.")
        if "evaluate per the universal seven-section contract" in low_user:
            flagged = ""
            if self.emit_flagged_claim:
                flagged = (
                    "\n\n## FLAGGED CLAIMS\n"
                    "- **Claim 1 — `dated-event` — risk: high**\n"
                    "  - claim: \"The event occurred in 2024\"\n"
                    "  - why_flagged: The date is externally checkable.\n"
                    "  - challenge_query: event occurrence 2024\n"
                )
            else:
                flagged = "\n\n## FLAGGED CLAIMS\nNone.\n"
            return self._long("## EVALUATION\nThe analysis is usable." + flagged)
        if "revise per the universal reviser output contract" in low_user or "address the verifier's findings" in low_user:
            return self._long(
                "## ADDRESSED\nAll material feedback.\n\n"
                "## CLAIM RESOLUTIONS\nVerified where evidence exists.\n\n"
                "## REVISED DRAFT\nFinal revised production answer. "
                + ("Grounded production detail. " * 12) + "\n\n"
                "## CHANGELOG\nGrounding improved."
            )
        if ("conclude with verified" in low_user or "run v1-v9" in low_user
                or "candidate analysis" in low_user
                or "candidate deliverable" in low_user):
            return self._long("VERDICT: PASS\nPROBLEM: NONE\nAll checks pass.")
        if "the output is the **corpus**" in low_user:
            return self._long("## CONSOLIDATED ANALYSIS\nBoth streams consolidated.")
        if "flowing prose addressed to the user" in low_user:
            return self._long("## Final Answer\nProduction-formatted deliverable.")
        if "evaluate" in low_user and "analyst output" in low_user:
            return self._long("## EVALUATION\nNo blocking issue.\n\n## FLAGGED CLAIMS\nNone.")
        return self._long("## ANALYSIS\nIndependent production analysis.")

    def _context(self, trace_dir, gear, prompt="production trace request"):
        mode = "subjective-inquiry" if gear == 3 else "root-cause-analysis"
        return {
            "cleaned_prompt": prompt,
            "raw_prompt": prompt,
            "natural_language_prompt": prompt,
            "operational_notation": prompt,
            "mode": mode,
            "mode_name": mode,
            "mode_text": self.boot.load_mode(mode),
            "gear": gear,
            "triage_tier": 1,
            "conversation_rag": "",
            "concept_rag": "",
            "relationship_rag": "",
            "web_rag": "",
            "trace_dir": trace_dir,
            "execution_context": "interactive",
        }

    def _only_turn(self, conversation):
        conv_dir = Path(self.root) / conversation
        turns = [path for path in conv_dir.iterdir() if path.is_dir()]
        self.assertEqual(len(turns), 1)
        return turns[0]

    @contextlib.contextmanager
    def _routing_config(self, endpoints):
        """Exercise the real config loader with a temp production-shaped file."""
        path = Path(self.tmp.name) / f"routing-{len(list(Path(self.tmp.name).glob('routing-*')))}.json"
        default = endpoints[0]["id"] if endpoints else None
        path.write_text(json.dumps({
            "endpoints": endpoints,
            "default_endpoint": default,
            "slot_assignments": ({
                "classification": default,
                "step1_cleanup": default,
                "fast": default,
                "primary": default,
                "breadth": default,
            } if default else {}),
            "buckets": {},
        }))
        with mock.patch.dict(
            os.environ, {"ORA_ROUTING_CONFIG_PATH": str(path)}, clear=False,
        ), mock.patch.object(
            self.boot, "_router_instance", False,
        ), mock.patch.dict(
            self.S.get_endpoint.__globals__, {"_router_instance": False},
        ):
            yield path

    @contextlib.contextmanager
    def _fake_openai_transport(self, response_text="provider terminal value"):
        """Replace only the external SDK transport; retain Ora call telemetry."""
        calls = []

        class Completions:
            def create(_self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(
                    choices=[SimpleNamespace(
                        message=SimpleNamespace(content=response_text),
                        finish_reason="stop",
                    )],
                    usage=SimpleNamespace(
                        prompt_tokens=11,
                        completion_tokens=5,
                        total_tokens=16,
                    ),
                )

        client = SimpleNamespace(
            chat=SimpleNamespace(completions=Completions()),
        )
        module = SimpleNamespace(OpenAI=lambda **_kwargs: client)
        with mock.patch.dict(sys.modules, {"openai": module}):
            yield calls

    @contextlib.contextmanager
    def _production_conversation_memory(self):
        """Temporarily undo incomplete fake-module residue from prior tests."""
        real = conversation_memory
        self.assertTrue(hasattr(real, "_DEFAULT_SESSIONS_ROOT"))
        sentinel = object()
        old_top = sys.modules.get("conversation_memory", sentinel)
        old_package = sys.modules.get(
            "orchestrator.conversation_memory", sentinel
        )
        package = sys.modules.get("orchestrator")
        old_attribute = getattr(package, "conversation_memory", sentinel)
        sessions = Path(self.tmp.name) / "sessions"
        sessions.mkdir()
        try:
            sys.modules["conversation_memory"] = real
            sys.modules["orchestrator.conversation_memory"] = real
            if package is not None:
                setattr(package, "conversation_memory", real)
            with mock.patch.object(
                real, "_DEFAULT_SESSIONS_ROOT", sessions,
            ):
                yield real
        finally:
            for name, previous in (
                ("conversation_memory", old_top),
                ("orchestrator.conversation_memory", old_package),
            ):
                if previous is sentinel:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous
            if package is not None:
                if old_attribute is sentinel:
                    try:
                        delattr(package, "conversation_memory")
                    except AttributeError:
                        pass
                else:
                    setattr(package, "conversation_memory", old_attribute)

    def test_cli_gear1_records_exact_value_after_screen_file_and_both_routes(self):
        expected = "provider terminal value"
        targets = []
        cases = []
        for label in ("screen", "file", "both"):
            target = Path(self.tmp.name) / f"{label}.txt"
            targets.append(target)
            output_target = (
                "screen" if label == "screen" else f"{label}:{target}"
            )
            with mock.patch.object(self.boot, "call_model", return_value=expected):
                result = self.boot.run_pipeline(
                    "hello", conversation_id=f"v5-cli-{label}",
                    output_target=output_target,
                )
            cases.append((label, target, result))

        self.assertEqual(cases[0][2], expected)
        self.assertEqual(cases[1][2], f"[Output written to {targets[1]}]")
        self.assertEqual(cases[2][2], expected)
        self.assertEqual(targets[1].read_text(), expected)
        self.assertEqual(targets[2].read_text(), expected)
        for label, _target, result in cases:
            turn = self._only_turn(f"v5-cli-{label}")
            manifest = json.loads((turn / "trace-manifest.json").read_text())
            terminal = json.loads((turn / "step-terminal-output.json").read_text())
            direct = json.loads((turn / "step3-direct-response.json").read_text())
            self.assertEqual(manifest["gear"], 1)
            self.assertEqual(manifest["missing_steps"], [])
            self.assertEqual(manifest["unexpected_steps"], [])
            self.assertEqual(direct["raw_response"], expected)
            self.assertEqual(terminal["terminal_value"], result)

    def test_cli_gear3_and_gear4_entry_points_record_exact_terminal_value(self):
        cases = (
            ("v5-cli-gear3", 3,
             "Use the endowment effect to analyze why I prefer keeping "
             "this old chair."),
            ("v5-cli-gear4", 4,
             "Use five whys to analyze why a houseplant has leaves that keep "
             "turning yellow despite weekly watering."),
        )
        for conversation, expected_gear, prompt in cases:
            with self.subTest(gear=expected_gear), \
                 mock.patch.object(
                     self.boot, "call_model", side_effect=self._provider,
                 ):
                result = self.boot.run_pipeline(
                    prompt, conversation_id=conversation,
                    config_name=self.CONFIG_NAME,
                )
            turn = self._only_turn(conversation)
            manifest = json.loads((turn / "trace-manifest.json").read_text())
            terminal = json.loads(
                (turn / "step-terminal-output.json").read_text()
            )
            self.assertEqual(manifest["gear"], expected_gear)
            self.assertEqual(manifest["terminal_status"], "completed")
            self.assertEqual(manifest["missing_steps"], [])
            self.assertEqual(terminal["terminal_value"], result)

    def test_explicit_cli_direct_entry_is_traced_without_changing_return(self):
        secret = "cli-direct-private-response-secret"
        with mock.patch.object(self.boot, "call_model", return_value=secret):
            result = self.boot.run_agentic_loop(
                "cli-direct-private-prompt-secret", use_pipeline=False,
            )
        self.assertEqual(result, secret)
        turn = self._only_turn("_orphan")
        manifest = json.loads((turn / "trace-manifest.json").read_text())
        self.assertEqual(manifest["trace_kind"], "direct-entry")
        self.assertEqual(manifest["terminal_status"], "completed")
        self.assertEqual(manifest["missing_steps"], [])
        projection = pipeline_trace.trace_step_projection(
            pipeline_trace.trace_ref_for_dir(str(turn)),
            "step3-direct-response",
        )
        projected = json.dumps(projection)
        self.assertNotIn(secret, projected)
        self.assertNotIn("cli-direct-private-prompt-secret", projected)

    def test_server_gear2_funnel_records_web_consultation_and_direct_response(self):
        trace_dir = pipeline_trace.start_trace(
            "v5-server-gear2", raw_input="current fact lookup"
        )
        config = self.boot.load_routing_config()
        turn_state = {"kind": "chat", "status": None, "gear": None}
        self.emit_web_intent = True
        search_result = [{
            "title": "Current source", "url": "https://example.test/current",
            "snippet": "Current externally grounded fact.",
        }]
        step2_globals = self.S.run_step2_context_assembly.__globals__
        web_globals = step2_globals["assemble_consultation_package"].__globals__
        search_globals = web_globals["_execute_intent_query"].__globals__
        search_mock = mock.Mock(return_value=search_result)

        def web_provider(messages, endpoint, images=None):
            user = str(messages[-1].get("content") or "") if messages else ""
            if (self.emit_web_intent
                    and user.startswith("USER PROMPT:\ncurrent fact lookup\n")
                    and "RECENT CONVERSATION CONTEXT:" in user):
                with self.provider_lock:
                    self.provider_calls.append([dict(m) for m in messages])
                return (
                    "INTENTS:\n- query: current trace evidence\n"
                    "  justification: Grounds the requested factual angle."
                )
            return self._provider(messages, endpoint, images=images)

        with mock.patch.object(self.boot, "call_model", side_effect=web_provider), \
             mock.patch.dict(step2_globals, {"call_model": web_provider}), \
             mock.patch.dict(search_globals,
                             {"web_search_structured": search_mock}):
            step1 = self.boot.run_step1_cleanup(
                "current fact lookup", "", config, trace_dir=trace_dir,
                config_name=self.CONFIG_NAME,
            )
            step1.update({
                "mode": "factual-lookup",
                "cleaned_prompt": "current fact lookup",
                "operational_notation": "current fact lookup",
                "raw_prompt": "current fact lookup",
                "triage_tier": 2,
                "pre_routing": {},
            })
            chunks = list(self.S._run_pipeline_from_step2(
                step1, config, [],
                "current fact lookup", trace_dir=trace_dir,
                config_name=self.CONFIG_NAME, turn_state=turn_state,
            ))
        events = [json.loads(chunk[6:]) for chunk in chunks]
        response = [e["text"] for e in events if e.get("type") == "response"][-1]
        pipeline_trace.record_terminal_output(
            trace_dir, response, route="server-stream-response",
            output_target="screen", persisted=True,
        )
        pipeline_trace.finalize_manifest(
            trace_dir, kind="chat", status_hint=turn_state["status"],
            gear=turn_state["gear"],
        )
        manifest = self.manifest(trace_dir)
        web_step = json.loads(Path(trace_dir, "step2-web-consultation.json").read_text())
        self.assertEqual(manifest["gear"], 2)
        self.assertIn("step2-web-consultation", manifest["actual_steps"])
        self.assertNotIn("step2-web-consultation", manifest["unexpected_steps"])
        self.assertIn("step3-direct-response", manifest["actual_steps"])
        self.assertEqual(manifest["missing_steps"], [])
        self.assertEqual(web_step["status"], "ran")
        search_mock.assert_called_once()
        self.assertGreater(web_step["chunks_total"], 0)

    def test_real_gear3_assembles_supplement_and_flagged_claim_evidence(self):
        import claim_verification
        trace_dir = self.start("v5-gear3-features")
        context = self._context(
            trace_dir, 3, prompt="gear3 feature request"
        )
        self.emit_supplement = True
        self.emit_flagged_claim = True
        search_result = [{
            "title": "Claim source", "url": "https://example.test/claim",
            "snippet": "The source records the event in 2024.",
        }]
        with mock.patch.object(self.boot, "call_model", side_effect=self._provider), \
             mock.patch.object(self.boot, "assemble_ranked_context",
                               return_value="SUPPLEMENT_EVIDENCE_SECRET"), \
             mock.patch.object(claim_verification, "web_search_structured",
                               return_value=search_result):
            output = self.boot.run_gear3(
                context, self.boot.load_routing_config(),
                config_name=self.CONFIG_NAME,
            )
        self.assertIn("Final revised production answer", output)
        requests = Path(trace_dir, "supplemental-rag.jsonl").read_text()
        self.assertIn("trace evidence source", requests)
        self.assertTrue(any(
            "SUPPLEMENT_EVIDENCE_SECRET" in str(message.get("content"))
            for call in self.provider_calls for message in call
        ))
        claim_step = json.loads(
            Path(trace_dir, "step4.5-claim-verification.json").read_text()
        )
        revised_step = json.loads(Path(trace_dir, "step5-revised.json").read_text())
        self.assertEqual(claim_step["trace"]["status"], "ran")
        self.assertEqual(len(claim_step["flagged_claims_parsed"]), 1)
        self.assertTrue(claim_step["per_claim_evidence"][0]["chunks"])
        self.assertIn("FLAGGED CLAIM EVIDENCE", revised_step["user_message"])
        pipeline_trace.record_terminal_output(
            trace_dir, output, route="gear3-production-return",
        )
        pipeline_trace.finalize_manifest(
            trace_dir, kind="chat", status_hint="completed", gear=3,
        )
        manifest = self.manifest(trace_dir)
        self.assertNotIn("step4.5-claim-verification",
                         manifest["unexpected_steps"])
        self.assertNotIn("step4.5-claim-verification",
                         manifest["skipped_steps"])

    def test_real_gear4_preserves_distinct_parallel_stage_traces(self):
        trace_dir = self.start("v5-gear4-normal")
        context = self._context(trace_dir, 4)
        with mock.patch.object(self.boot, "call_model", side_effect=self._provider):
            output = self.boot.run_gear4(
                context, self.boot.load_routing_config(),
                config_name=self.CONFIG_NAME,
            )
        pipeline_trace.record_terminal_output(
            trace_dir, output, route="gear4-production-return",
        )
        pipeline_trace.finalize_manifest(
            trace_dir, kind="framework-milestone",
            status_hint="completed", gear=4,
        )
        manifest = self.manifest(trace_dir)
        for step in (
            "step3-depth", "step3-breadth",
            "step4-eval-of-depth", "step4-eval-of-breadth",
            "step5-revised-depth", "step5-revised-breadth",
            "step7-consolidated", "step8-formatted",
            "step-terminal-output",
        ):
            self.assertIn(step, manifest["actual_steps"])
        self.assertEqual(manifest["missing_steps"], [])
        self.assertEqual(manifest["unexpected_steps"], [])

    def test_gear4_to_gear3_before_health_finalizes_effective_gear_and_error(self):
        trace_dir = self.start("v5-gear4-no-endpoints")
        context = self._context(trace_dir, 4)
        output = self.boot.run_gear4(
            context, self.boot.load_routing_config(),
            config_name="v5-configuration-does-not-exist",
        )
        self.assertIn("couldn't resolve", output)
        pipeline_trace.finalize_manifest(
            trace_dir, kind="chat", status_hint=None, gear=4,
        )
        manifest = self.manifest(trace_dir)
        self.assertEqual(manifest["gear"], 3)
        self.assertEqual(manifest["trace_kind"], "chat-gear3")
        self.assertEqual(manifest["terminal_status"], "error")
        self.assertIn("step3-gear4-fallback-to-gear3",
                      manifest["contingency_steps"])
        self.assertIn("step3-gear3-no-endpoint",
                      manifest["contingency_steps"])
        self.assertEqual(manifest["missing_steps"], [])
        self.assertIn("step3-depth", manifest["skipped_steps"])
        self.assertIn("step4-eval", manifest["skipped_steps"])
        self.assertTrue(
            set(manifest["actual_steps"]).isdisjoint(
                manifest["replaced_steps"]
            )
        )

    def test_real_writer_failure_during_retry_and_fallback_changes_no_output(self):
        def run_once(conversation, make_read_only):
            trace_dir = self.start(conversation)
            context = self._context(trace_dir, 4)
            calls = {"count": 0}

            def provider(messages, endpoint, images=None):
                calls["count"] += 1
                if context.get("_trace_effective_gear") != 3:
                    return ""
                return self._provider(messages, endpoint, images=images)

            if make_read_only:
                os.chmod(trace_dir, 0o500)
            try:
                with mock.patch.object(self.boot, "call_model", side_effect=provider):
                    output = self.boot.run_gear4(
                        context, self.boot.load_routing_config(),
                        config_name=self.CONFIG_NAME,
                    )
            finally:
                if make_read_only:
                    os.chmod(trace_dir, 0o700)
            return output, calls["count"], context

        writable = run_once("v5-fallback-writable", False)
        failed_writer = run_once("v5-fallback-readonly", True)
        self.assertEqual(failed_writer[0], writable[0])
        self.assertEqual(failed_writer[1], writable[1])
        self.assertGreaterEqual(failed_writer[1], 6)
        self.assertEqual(failed_writer[2]["_trace_effective_gear"], 3)

    def test_private_server_direct_entry_persists_exact_terminal_but_projects_no_content(self):
        import chromadb
        import orchestrator.embedding as embedding

        class Collection:
            def add(self, **_kwargs):
                return None

        conv = "v5-private-direct"
        processed = Path(self.tmp.name) / "processed"
        raw = Path(self.tmp.name) / "raw"
        processed.mkdir()
        raw.mkdir()
        self.S._session_data.pop(conv, None)
        self.S._closed_conversations.discard(conv)
        self.S._deleted_conversations.discard(conv)
        with self._production_conversation_memory(), \
             mock.patch.object(self.S, "CONVERSATIONS_DIR", str(processed)), \
             mock.patch.object(self.S, "CONVERSATIONS_RAW", str(raw)), \
             mock.patch.object(self.S, "call_model",
                               return_value="server-direct-response-secret"), \
             mock.patch.object(self.S, "_nomic_embed", return_value=[0.0]), \
             mock.patch.object(chromadb, "PersistentClient", return_value=object()), \
             mock.patch.object(embedding, "get_or_create_collection",
                               return_value=Collection()):
            reply = self.S._invoke_pipeline_unlocked(
                "/direct server-direct-prompt-secret", [], conv, False,
                tag="private", output_destination=str(processed),
            )
        payload = json.loads(reply[0] if isinstance(reply, tuple) else reply)
        self.assertEqual(payload["status"], "ok")
        turn = self._only_turn(conv)
        manifest = json.loads((turn / "trace-manifest.json").read_text())
        terminal = json.loads((turn / "step-terminal-output.json").read_text())
        self.assertEqual(manifest["trace_kind"], "direct-entry")
        self.assertEqual(manifest["redaction_level"], "private")
        self.assertEqual(manifest["missing_steps"], [])
        self.assertIn("server-direct-response-secret",
                      terminal["terminal_value"])
        chunks = list(processed.glob("*.md"))
        self.assertEqual(len(chunks), 1)
        self.assertIn(terminal["terminal_value"], chunks[0].read_text())
        ref = self.opt.trace_ref_for_dir(str(turn))
        projected = json.dumps(self.opt.trace_step_projection(
            ref, "step-terminal-output"
        ))
        export, _filename = self.opt.trace_export_html(ref)
        for raw_secret in (
            "server-direct-response-secret", "server-direct-prompt-secret",
        ):
            self.assertNotIn(raw_secret, projected)
            self.assertNotIn(raw_secret, export)

    def test_server_file_route_records_value_after_route_and_successful_save(self):
        import chromadb
        import orchestrator.embedding as embedding

        class Collection:
            def add(self, **_kwargs):
                return None

        conv = "v5-server-file-route"
        processed = Path(self.tmp.name) / "server-file-processed"
        raw = Path(self.tmp.name) / "server-file-raw"
        routed_file = Path(self.tmp.name) / "server-routed.txt"
        processed.mkdir()
        raw.mkdir()
        self.S._session_data.pop(conv, None)
        self.S._closed_conversations.discard(conv)
        self.S._deleted_conversations.discard(conv)
        with self._production_conversation_memory(), \
             mock.patch.object(self.S, "CONVERSATIONS_DIR", str(processed)), \
             mock.patch.object(self.S, "CONVERSATIONS_RAW", str(raw)), \
             mock.patch.object(self.S, "call_model",
                               return_value="server-file-response-secret"), \
             mock.patch.object(self.boot, "call_model",
                               return_value="server-file-response-secret"), \
             mock.patch.object(self.S, "_nomic_embed", return_value=[0.0]), \
             mock.patch.object(chromadb, "PersistentClient", return_value=object()), \
             mock.patch.object(embedding, "get_or_create_collection",
                               return_value=Collection()):
            reply = self.S._invoke_pipeline_unlocked(
                f"/save {routed_file} hello", [], conv, False,
                output_destination=str(processed),
                config_name=self.CONFIG_NAME,
            )
        payload = json.loads(reply[0] if isinstance(reply, tuple) else reply)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(routed_file.read_text(), "server-file-response-secret")
        expected_terminal = f"[Output written to {routed_file}]"
        turn = self._only_turn(conv)
        terminal = json.loads((turn / "step-terminal-output.json").read_text())
        manifest = json.loads((turn / "trace-manifest.json").read_text())
        self.assertEqual(terminal["terminal_value"], expected_terminal)
        self.assertEqual(
            terminal["routing"], {
                "route": "server-conversation-save",
                "output_target": f"file:{routed_file}",
                "persisted": True,
            },
        )
        self.assertEqual(manifest["missing_steps"], [])
        chunk = next(processed.glob("*.md")).read_text()
        self.assertIn(expected_terminal, chunk)

    def test_explicit_server_direct_stealth_suppresses_trace(self):
        conv = "v5-stealth-direct"
        with mock.patch.object(
            self.S, "call_model", return_value="stealth direct response",
        ):
            chunks = list(self.S.agentic_loop_stream(
                "stealth direct prompt", [], use_pipeline=False,
                panel_id=conv, conversation_tag="stealth",
            ))
        events = [json.loads(chunk[6:]) for chunk in chunks]
        responses = [event.get("text") for event in events
                     if event.get("type") == "response"]
        self.assertEqual(responses, ["stealth direct response"])
        self.assertFalse(any(event.get("type") == "trace_ref"
                             for event in events))
        self.assertFalse((Path(self.root) / conv).exists())

    def test_real_no_endpoint_entries_record_failure_and_delivered_terminal(self):
        empty = []
        with self._routing_config(empty):
            cli_value = self.boot.run_pipeline(
                "hello", conversation_id="v5-no-endpoint-cli",
            )
            direct_value = self.boot.run_agentic_loop(
                "hello", use_pipeline=False,
            )
            server_chunks = list(self.S.agentic_loop_stream(
                "hello", [], use_pipeline=True,
                panel_id="v5-no-endpoint-server",
            ))
            with self._production_conversation_memory():
                server_reply = self.S._invoke_pipeline_unlocked(
                    "hello", [], "v5-no-endpoint-http", False,
                )

        self.assertEqual(cli_value, "[No AI endpoints configured.]")
        self.assertIn("No AI endpoints configured", direct_value)
        server_events = [json.loads(chunk[6:]) for chunk in server_chunks]
        server_error = next(event["text"] for event in server_events
                            if event.get("type") == "error")
        server_reply_text = (
            server_reply[0] if isinstance(server_reply, tuple)
            else server_reply
        )
        self.assertEqual(json.loads(server_reply_text)["status"], "errored")

        cases = (
            (self._only_turn("v5-no-endpoint-cli"), cli_value),
            (self._only_turn("_orphan"), direct_value),
            (self._only_turn("v5-no-endpoint-server"), server_error),
            (self._only_turn("v5-no-endpoint-http"), server_reply_text),
        )
        for turn, delivered in cases:
            with self.subTest(turn=turn.parent.name):
                manifest = json.loads(
                    (turn / "trace-manifest.json").read_text()
                )
                terminal = json.loads(
                    (turn / "step-terminal-output.json").read_text()
                )
                self.assertEqual(manifest["terminal_status"], "error")
                self.assertIn("step3-direct-no-endpoint",
                              manifest["contingency_steps"])
                self.assertEqual(manifest["missing_steps"], [])
                self.assertEqual(terminal["terminal_value"], delivered)
                self.assertFalse(terminal["routing"]["persisted"])

    def test_framework_gear1_no_endpoint_records_each_real_attempt(self):
        import milestone_executor

        parent = self.start("v5-framework-no-endpoint")
        parent_ref = pipeline_trace.trace_ref_for_dir(parent)
        framework = SimpleNamespace(name="v5-framework", layers={})
        milestone = SimpleNamespace(
            id="m1", name="Milestone One", gear=1,
            required_prior=[], layers_covered=[],
            output_format="Return text.",
            verification_criterion="Text exists.",
            conditional_layers="", drift_check_question="",
        )
        scratch = SimpleNamespace(
            read_all_prior=lambda _ids: {},
            write_milestone=lambda _mid, _deliverable: None,
        )
        config = {"endpoints": [], "default_endpoint": None,
                  "slot_assignments": {}}
        with mock.patch.object(self.boot, "_router_instance", False), \
             mock.patch.object(milestone_executor.time, "sleep",
                               return_value=None):
            with self.assertRaises(milestone_executor.MilestoneExecutionError):
                milestone_executor._run_milestone(
                    framework, milestone, scratch, "user input", config,
                    parent_trace_dir=parent,
                    parent_trace_ref=parent_ref,
                    selected_mode="all", trace_context={},
                )

        child_refs = self.manifest(parent)["child_trace_refs"]
        self.assertEqual(len(child_refs), milestone_executor.MAX_RETRIES)
        for child_ref in child_refs:
            child = Path(pipeline_trace.resolve_trace_ref(child_ref))
            manifest = json.loads(
                (child / "trace-manifest.json").read_text()
            )
            self.assertTrue(
                (child / "step3-direct-no-endpoint.json").is_file()
            )
            self.assertEqual(manifest["terminal_status"], "error")
            self.assertIn("step3-direct-no-endpoint",
                          manifest["contingency_steps"])
            self.assertEqual(manifest["missing_steps"], [])
            self.assertIn("step3-direct-response",
                          manifest["skipped_steps"])

    def test_real_pipeline_to_direct_fallback_is_short_circuit(self):
        endpoint = {
            "id": "v5-fallback-endpoint", "name": "v5-fallback-endpoint",
            "type": "api", "service": "openai", "model": "gpt-4o",
            "api_key": "test-only", "enabled": True, "status": "active",
            # gpt-4o accepts at most 16384 completion tokens. Without an
            # explicit value the endpoint falls back to _DEFAULT_API_MAX_TOKENS
            # (32000) and the provider rejects the call with a 400, which
            # _with_truncation_retry returns as text rather than raising — so
            # the assertion below sees an error string instead of the response.
            # Declared here to keep this test about fallback short-circuiting.
            # The default itself is wrong in both directions (it also throttles
            # models supporting far more) and is tracked separately.
            "max_tokens": 16384,
        }
        with self._routing_config([endpoint]), mock.patch.object(
            self.S, "call_model", return_value="fallback response",
        ):
            chunks = list(self.S.agentic_loop_stream(
                "hello", [], use_pipeline=True,
                panel_id="v5-real-direct-fallback",
            ))
        events = [json.loads(chunk[6:]) for chunk in chunks]
        self.assertEqual(
            [event.get("text") for event in events
             if event.get("type") == "response"],
            ["fallback response"],
        )
        turn = self._only_turn("v5-real-direct-fallback")
        manifest = json.loads((turn / "trace-manifest.json").read_text())
        self.assertEqual(manifest["trace_kind"], "direct")
        self.assertEqual(manifest["terminal_status"], "short_circuit")
        self.assertIn("step3-direct-response", manifest["actual_steps"])
        self.assertIn("step-terminal-output", manifest["skipped_steps"])

    def test_failed_real_server_save_records_exact_error_not_persistence(self):
        endpoint = {
            "id": "v5-save-endpoint", "name": "v5-save-endpoint",
            "type": "api", "service": "openai", "model": "gpt-4o",
            "api_key": "test-only", "enabled": True, "status": "active",
        }
        conv = "v5-save-refused"
        identity = self.S._conversation_storage_identity(conv)
        self.S._session_data.pop(conv, None)
        self.S._deleted_conversations.discard(identity)
        self.S._closed_conversations.add(identity)
        self.addCleanup(self.S._closed_conversations.discard, identity)
        with self._routing_config([endpoint]), mock.patch.object(
            self.S, "call_model", return_value="unsaved response",
        ):
            reply = self.S._invoke_pipeline_unlocked(
                "/direct persist this", [], conv, False,
            )
        reply_text = reply[0] if isinstance(reply, tuple) else reply
        payload = json.loads(reply_text)
        self.assertEqual(payload["status"], "errored")
        self.assertIsNone(payload["chunk_id"])
        turn = self._only_turn(conv)
        terminal = json.loads(
            (turn / "step-terminal-output.json").read_text()
        )
        manifest = json.loads((turn / "trace-manifest.json").read_text())
        self.assertEqual(terminal["terminal_value"], reply_text)
        self.assertEqual(terminal["routing"]["route"], "server-http-error")
        self.assertFalse(terminal["routing"]["persisted"])
        self.assertEqual(manifest["terminal_status"], "error")

    def test_direct_and_gear1_physical_events_keep_owning_stage(self):
        endpoint = {
            "id": "v5-physical-endpoint",
            "name": "v5-physical-endpoint",
            "type": "api", "service": "openai", "model": "gpt-4o",
            "api_key": "test-only", "enabled": True, "status": "active",
        }
        with self._routing_config([endpoint]), \
             self._fake_openai_transport() as sdk_calls, \
             mock.patch.dict(os.environ, {"ORA_TOOL_EVENTS": "on"},
                             clear=False):
            direct = self.boot.run_agentic_loop(
                "physical direct", use_pipeline=False,
            )
            normal = self.boot.run_pipeline(
                "hello", conversation_id="v5-physical-gear1",
            )
        self.assertEqual(direct, "provider terminal value")
        self.assertEqual(normal, "provider terminal value")
        self.assertEqual(len(sdk_calls), 2)

        for turn in (
            self._only_turn("_orphan"),
            self._only_turn("v5-physical-gear1"),
        ):
            configs = [json.loads(line) for line in
                       (turn / "model-call-config.jsonl").read_text().splitlines()]
            usage = [json.loads(line) for line in
                     (turn / "usage.jsonl").read_text().splitlines()]
            events = [json.loads(line) for line in
                      (turn / "tool-events.jsonl").read_text().splitlines()]
            model_events = [event for event in events
                            if event.get("event") == "model_call"]
            self.assertTrue(configs)
            self.assertTrue(usage)
            self.assertTrue(model_events)
            self.assertTrue(all(
                record["step"] == "step3-direct-response"
                for record in configs
            ))
            self.assertTrue(all(
                record["step_hint"] == "step3-direct-response"
                for record in usage
            ))
            self.assertTrue(all(
                event["args_redacted"]["step"] == "step3-direct-response"
                for event in model_events
            ))


if __name__ == "__main__":
    unittest.main()
