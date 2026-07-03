"""Tests for the 2026-05-17 stealth-context + oversight-logs leak fix.

Two coupled fixes:

1. ``server.py::_pipeline_stream`` now sets the stealth thread-local
   (and opens the per-turn trace dir) at the top of every turn — above
   the four short-circuits (runtime command / resolution-chain
   continuation / framework-elicitation continuation / framework
   slash-command). Previously the setup ran only after those four
   short-circuits returned, so a stealth turn that hit any of them
   leaked ``user_input`` into ``~/ora/data/oversight/events.jsonl`` via
   the ``FrameworkStarted`` (and similar) payloads emitted by
   ``milestone_executor``.

2. ``conversation_closeout._purge_stealth`` gained Layer 9: a defence-
   in-depth scrub of ``events.jsonl`` / ``actions.jsonl`` /
   ``human-queue.jsonl`` keyed on ``conversation_id``. Records are now
   stamped with ``conversation_id`` by ``oversight_events.emit`` and the
   two write helpers in ``oversight_actions`` when the per-thread
   context is set.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

# Same path-bootstrap pattern as test_silent_failure_fixes_2026_05_15.py.
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKTREE_ROOT = os.path.dirname(HERE)
for p in (HERE, WORKTREE_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)


class TestPipelineStreamHoistsStealthAboveShortCircuits(unittest.TestCase):
    """Fix 1 — source inspection.

    The four short-circuit handlers (``is_runtime_command``,
    ``is_resolution_continuation``, ``is_continuation``,
    ``is_framework_command``) must all appear AFTER the stealth-context
    setup block in ``_pipeline_stream``. If a future edit hoists any
    short-circuit above the stealth block, this test fires and the
    privacy guarantee is back to broken.
    """

    def setUp(self):
        server_py = Path(HERE).parent / "server" / "server.py"
        self.src = server_py.read_text()

        # Locate the _pipeline_stream function body (next def after it).
        start = self.src.index("def _pipeline_stream(")
        # Heuristic: cut at the next top-level def or @route.
        end = self.src.index("\ndef ", start + 1)
        self.body = self.src[start:end]

    def _idx(self, needle: str) -> int:
        i = self.body.find(needle)
        self.assertGreaterEqual(
            i, 0,
            f"Expected to find {needle!r} inside _pipeline_stream body",
        )
        return i

    def test_stealth_setup_appears_before_runtime_command_gate(self):
        stealth = self._idx("set_stealth_context as _set_stealth")
        gate = self._idx("if is_runtime_command(user_input):")
        self.assertLess(
            stealth, gate,
            "set_stealth_context must run before the runtime-command "
            "short-circuit so /queue, /approve, /deny etc. honour stealth.",
        )

    def test_stealth_setup_appears_before_resolution_chain_gate(self):
        stealth = self._idx("set_stealth_context as _set_stealth")
        gate = self._idx(
            "resolution_chain.is_resolution_continuation"
        )
        self.assertLess(
            stealth, gate,
            "set_stealth_context must run before the resolution-chain "
            "continuation short-circuit.",
        )

    def test_stealth_setup_appears_before_elicitation_gate(self):
        stealth = self._idx("set_stealth_context as _set_stealth")
        gate = self._idx("framework_elicitation.is_continuation(history")
        self.assertLess(
            stealth, gate,
            "set_stealth_context must run before the framework-elicitation "
            "continuation short-circuit.",
        )

    def test_stealth_setup_appears_before_framework_slash_gate(self):
        stealth = self._idx("set_stealth_context as _set_stealth")
        gate = self._idx("if is_framework_command(user_input):")
        self.assertLess(
            stealth, gate,
            "set_stealth_context must run before the framework slash-command "
            "short-circuit.",
        )

    def test_trace_start_appears_before_runtime_command_gate(self):
        trace = self._idx("_pt.start_trace(")
        gate = self._idx("if is_runtime_command(user_input):")
        self.assertLess(
            trace, gate,
            "start_trace must also run before the four short-circuits so "
            "the stealth flag is threaded into the trace layer.",
        )

    def test_conversation_id_context_set_alongside_stealth(self):
        # The conversation_id thread-local is what Layer 9 keys on; if a
        # future edit drops the set_conversation_id_context call, the
        # post-hoc scrub silently no-ops.
        self.assertIn(
            "set_conversation_id_context as _set_cid",
            self.body,
        )
        self.assertIn("_set_cid(panel_id)", self.body)


class TestEmitStampsConversationIdAndHonoursStealth(unittest.TestCase):
    """Fix 1 — runtime behaviour of the oversight bus under the new
    thread-local context.

    Simulates each of the four short-circuit paths by calling the same
    emit() entry point milestone_executor uses, with the stealth +
    conversation_id thread-locals set the way ``_pipeline_stream`` now
    sets them.
    """

    def setUp(self):
        from orchestrator import oversight_events as oe
        # Snapshot + clear handlers / context so tests are isolated.
        self._prior_handlers = list(oe._handlers)
        oe.clear_handlers()
        oe.clear_stealth_context()
        oe.clear_conversation_id_context()
        self.oe = oe

        # Capture every event the bus sees plus the thread-local state at
        # emit time so we can assert (a) stealth flag was set and (b)
        # conversation_id was stamped.
        self.captured: list[dict] = []
        self.stealth_at_emit: list[bool] = []

        def probe(event):
            self.captured.append(dict(event))
            self.stealth_at_emit.append(oe._is_stealth_context())

        oe.register_handler(probe)

        # Redirect events.jsonl into a tempdir so the test can't pollute
        # the real ~/ora/data/oversight/events.jsonl.
        self._tmp = tempfile.TemporaryDirectory()
        self._patches = [
            mock.patch.object(
                oe, "EVENT_LOG_PATH",
                os.path.join(self._tmp.name, "events.jsonl"),
            ),
            mock.patch.object(
                oe, "OVERSIGHT_DATA_DIR", self._tmp.name,
            ),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()
        self.oe.clear_handlers()
        self.oe.clear_stealth_context()
        self.oe.clear_conversation_id_context()
        for h in self._prior_handlers:
            self.oe.register_handler(h)

    def _emit_for_each_short_circuit(self, conv_id: str):
        """Mimic the events each short-circuit handler emits via
        milestone_executor or its equivalents, with the stealth thread-
        local set the way _pipeline_stream now sets it.
        """
        self.oe.set_stealth_context(True)
        self.oe.set_conversation_id_context(conv_id)

        # (1) runtime command path — slash_commands.run_runtime_command
        #     doesn't emit through this bus today, but corpus_runtime
        #     (called by /instance, /validate) does emit
        #     ``CorpusInstanceCreated`` / ``CorpusValidated`` events.
        self.oe.emit({"event_type": "CorpusInstanceCreated",
                      "user_input": "/instance secret-template 2026-05",
                      "framework_id": "cff"})

        # (2) resolution-chain continuation — redefinition_handler
        #     emits a RedefinitionEvidence event when the user commits.
        self.oe.emit({"event_type": "RedefinitionEvidence",
                      "user_input": "stealth secret about Alice",
                      "queue_id": "abc"})

        # (3) framework-elicitation continuation — the final-deliverable
        #     hand-off into milestone_executor emits FrameworkStarted /
        #     FrameworkComplete with the elicited user_input.
        self.oe.emit({"event_type": "FrameworkStarted",
                      "framework_id": "pef",
                      "user_input": "stealth elicitation: Alice's diagnosis"})

        # (4) framework slash-command — milestone_executor.execute_framework
        #     emits FrameworkStarted with user_input.
        self.oe.emit({"event_type": "FrameworkStarted",
                      "framework_id": "mom",
                      "user_input": "/framework mom stealth secret"})

    def test_stealth_flag_set_at_every_emission(self):
        self._emit_for_each_short_circuit("conv-stealth-1")
        self.assertEqual(len(self.captured), 4)
        self.assertTrue(
            all(self.stealth_at_emit),
            "Stealth thread-local must be True at the moment every event "
            "is emitted — otherwise the on-disk write is not suppressed.",
        )

    def test_conversation_id_stamped_on_every_event(self):
        self._emit_for_each_short_circuit("conv-stealth-2")
        for evt in self.captured:
            self.assertEqual(
                evt.get("conversation_id"), "conv-stealth-2",
                "emit() must stamp conversation_id from the thread-local "
                "so _purge_stealth Layer 9 can find these records.",
            )

    def test_stealth_skipped_writes_leave_events_jsonl_empty(self):
        self._emit_for_each_short_circuit("conv-stealth-3")
        log_path = Path(self.oe.EVENT_LOG_PATH)
        # Primary defence: stealth=True means events never land on disk.
        self.assertFalse(
            log_path.exists() and log_path.stat().st_size > 0,
            f"events.jsonl was written for a stealth turn: "
            f"{log_path.read_text() if log_path.exists() else '<absent>'}",
        )

    def test_non_stealth_turn_still_writes(self):
        # Regression guard: clearing the stealth flag must restore writes.
        self.oe.clear_stealth_context()
        self.oe.set_conversation_id_context("conv-public-1")
        self.oe.emit({"event_type": "FrameworkComplete",
                      "framework_id": "pef"})
        log_path = Path(self.oe.EVENT_LOG_PATH)
        self.assertTrue(log_path.exists() and log_path.stat().st_size > 0)
        rec = json.loads(log_path.read_text().splitlines()[-1])
        self.assertEqual(rec["conversation_id"], "conv-public-1")
        self.assertNotIn("stealth", rec)


class TestPurgeStealthLayer9ScrubsOversightLogs(unittest.TestCase):
    """Fix 2 — Layer 9 wipes entries from events.jsonl / actions.jsonl /
    human-queue.jsonl matching the stealth conversation_id and leaves
    other conversations' entries untouched. Uses the atomic-rewrite
    pattern (``.tmp`` + replace).
    """

    def setUp(self):
        # Stub conversation_memory so the closeout module import chain
        # works against whatever HEAD is checked out, matching the
        # pattern used by test_silent_failure_fixes_2026_05_15.py.
        if "orchestrator.conversation_memory" not in sys.modules:
            stub = types.ModuleType("orchestrator.conversation_memory")
            stub.get_conversation_tag = lambda *a, **kw: "stealth"
            stub.set_conversation_closed = lambda *a, **kw: None
            sys.modules["orchestrator.conversation_memory"] = stub
        else:
            cm = sys.modules["orchestrator.conversation_memory"]
            if not hasattr(cm, "set_conversation_closed"):
                cm.set_conversation_closed = lambda *a, **kw: None
            if not hasattr(cm, "get_conversation_tag"):
                cm.get_conversation_tag = lambda *a, **kw: "stealth"

    def _write_jsonl(self, path: Path, records: list[dict]):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

    def test_layer_9_scrubs_three_oversight_logs_by_conversation_id(self):
        from orchestrator.conversation_closeout import _purge_stealth

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            oversight_dir = tmp_path / "oversight"

            stealth_id = "conv-stealth-target"
            other_id = "conv-other"

            events = [
                {"event_type": "FrameworkStarted",
                 "user_input": "stealth secret",
                 "conversation_id": stealth_id},
                {"event_type": "FrameworkComplete",
                 "conversation_id": stealth_id},
                {"event_type": "MilestoneClaimed",
                 "conversation_id": other_id},
                {"event_type": "FrameworkComplete"},  # legacy, no conv id
            ]
            actions = [
                {"action": "PROCEED",
                 "conversation_id": stealth_id},
                {"action": "ESCALATE",
                 "conversation_id": other_id},
            ]
            queue = [
                {"event_type": "MilestoneBlocked",
                 "context": "stealth payload here",
                 "conversation_id": stealth_id},
                {"event_type": "FrameworkComplete",
                 "conversation_id": other_id},
            ]

            events_path = oversight_dir / "events.jsonl"
            actions_path = oversight_dir / "actions.jsonl"
            queue_path = oversight_dir / "human-queue.jsonl"
            self._write_jsonl(events_path, events)
            self._write_jsonl(actions_path, actions)
            self._write_jsonl(queue_path, queue)

            # Layer 9 derives its targets from runtime_paths at call time
            # (DATA_DIR_STR/oversight); map that onto our tempdir. Also
            # point the Layer 6a tool-event sink into the tempdir so the
            # test never touches the real global sink.
            from orchestrator import runtime_paths as _rt
            with mock.patch.object(_rt, "DATA_DIR_STR", str(tmp_path)), \
                 mock.patch.dict(os.environ, {
                     "ORA_TOOL_EVENTS_PATH":
                         str(tmp_path / "tool-events.jsonl")}):
                result = _purge_stealth(
                    stealth_id,
                    sessions_root=tmp_path / "sessions",
                    conversations_dir=tmp_path / "convs",
                    conversations_raw=tmp_path / "raw",
                    chromadb_path=tmp_path / "chroma",
                    vault_sessions=tmp_path / "vault",
                )

            # Layer 9 report shape.
            layer9 = result["deleted"].get("oversight_log_entries", {})
            self.assertEqual(layer9.get("events.jsonl"), 2)
            self.assertEqual(layer9.get("actions.jsonl"), 1)
            self.assertEqual(layer9.get("human-queue.jsonl"), 1)

            # events.jsonl: only the two stealth_id rows are stripped;
            # other_id row + legacy no-conv-id row survive.
            remaining = [
                json.loads(line)
                for line in events_path.read_text().splitlines()
                if line.strip()
            ]
            self.assertEqual(len(remaining), 2)
            remaining_ids = [r.get("conversation_id", "<none>") for r in remaining]
            self.assertIn(other_id, remaining_ids)
            self.assertIn("<none>", remaining_ids)
            self.assertNotIn(stealth_id, remaining_ids)

            # actions.jsonl and human-queue.jsonl: only the other_id rows
            # survive.
            remaining_actions = [
                json.loads(line)
                for line in actions_path.read_text().splitlines()
                if line.strip()
            ]
            self.assertEqual(len(remaining_actions), 1)
            self.assertEqual(remaining_actions[0]["conversation_id"], other_id)

            remaining_queue = [
                json.loads(line)
                for line in queue_path.read_text().splitlines()
                if line.strip()
            ]
            self.assertEqual(len(remaining_queue), 1)
            self.assertEqual(remaining_queue[0]["conversation_id"], other_id)

    def test_layer_6a_purges_relocated_global_sink(self):
        # Revision 7 fold: the purge must rewrite the SAME sink
        # tool_events.record() writes (env override / runtime_paths), not
        # a hardcoded ~/ora path — otherwise stealth gate-decision records
        # persist forever under ORA_HOME / ORA_TOOL_EVENTS_PATH relocation.
        from orchestrator.conversation_closeout import _purge_stealth
        from orchestrator import runtime_paths as _rt

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sink = tmp_path / "relocated-tool-events.jsonl"
            self._write_jsonl(sink, [
                {"conversation_id": "conv-stealth-reloc",
                 "action": "bash_execute", "what": "cat plan.md"},
                {"conversation_id": "conv-keep", "action": "file_read"},
            ])

            with mock.patch.object(_rt, "DATA_DIR_STR", str(tmp_path)), \
                 mock.patch.dict(os.environ, {
                     "ORA_TOOL_EVENTS_PATH": str(sink)}):
                result = _purge_stealth(
                    "conv-stealth-reloc",
                    sessions_root=tmp_path / "sessions",
                    conversations_dir=tmp_path / "convs",
                    conversations_raw=tmp_path / "raw",
                    chromadb_path=tmp_path / "chroma",
                    vault_sessions=tmp_path / "vault",
                )

            self.assertEqual(result["deleted"]["tool_event_entries"], 1)
            remaining = [
                json.loads(line)
                for line in sink.read_text().splitlines()
                if line.strip()
            ]
            self.assertEqual(
                [r["conversation_id"] for r in remaining], ["conv-keep"])

    def test_layer_9_handles_missing_logs_gracefully(self):
        from orchestrator.conversation_closeout import _purge_stealth

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            oversight_dir = tmp_path / "oversight"  # never created

            from orchestrator import runtime_paths as _rt
            with mock.patch.object(_rt, "DATA_DIR_STR", str(tmp_path)), \
                 mock.patch.dict(os.environ, {
                     "ORA_TOOL_EVENTS_PATH":
                         str(tmp_path / "tool-events.jsonl")}):
                result = _purge_stealth(
                    "conv-stealth-x",
                    sessions_root=tmp_path / "sessions",
                    conversations_dir=tmp_path / "convs",
                    conversations_raw=tmp_path / "raw",
                    chromadb_path=tmp_path / "chroma",
                    vault_sessions=tmp_path / "vault",
                )

            layer9 = result["deleted"].get("oversight_log_entries", {})
            self.assertEqual(layer9.get("events.jsonl"), 0)
            self.assertEqual(layer9.get("actions.jsonl"), 0)
            self.assertEqual(layer9.get("human-queue.jsonl"), 0)
            for err in result["errors"]:
                self.assertNotIn("oversight_log", err)


if __name__ == "__main__":
    unittest.main()
