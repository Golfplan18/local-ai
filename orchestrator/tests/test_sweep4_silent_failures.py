"""Sweep-4 silent-failure probes: looks-like-success failures.

Closes the failure class where the pipeline thought it succeeded and the
model had nothing visible to tell it otherwise:

1. compact_context silent failures (no log when it skips, fails, or drops)
2. COMPACTED CONTEXT mis-attribution (assistant-said vs system-injected)
3. RAG ranker silent cap-drop
4. conversation.json concurrent-write race (last-writer-wins)
5. _direct_stream agentic-loop overrun
6. Tool execution success-vs-error ambiguity
"""

import io
import json
import os
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKTREE_ROOT = os.path.dirname(HERE)
for p in (HERE, WORKTREE_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)



import boot
import compaction
import rag_engine


# ---------------------------------------------------------------------------
# compact_context observability
# ---------------------------------------------------------------------------

class TestCompactContextObservability(unittest.TestCase):
    def test_skip_no_callmodelfn_is_logged(self):
        # unittest captures stderr ahead of contextlib.redirect_stderr,
        # so we hook the JSONL surface instead.
        events = []
        with mock.patch.object(compaction, "_log_compaction",
                                side_effect=lambda e, **kw: events.append((e, kw))):
            out = compaction.compact_context(
                [{"role": "user", "content": "x" * 99999}],
                call_model_fn=None,
                context_limit=1000,
            )
        self.assertEqual(len(out), 1)
        kinds = [e for e, _ in events]
        self.assertIn("skipped", kinds)
        skipped_event = next(kw for e, kw in events if e == "skipped")
        self.assertEqual(skipped_event["reason"], "no_call_model_fn")

    def test_failure_logs_with_lost_chars_metric(self):
        # 4 user + 4 assistant + 1 system = 9 msgs. keep_tail=6 leaves a
        # middle of 2 messages — enough to trigger the compaction path.
        msgs = (
            [{"role": "system", "content": "sys"}]
            + [{"role": "user", "content": "u" * 10000}] * 4
            + [{"role": "assistant", "content": "a" * 10000}] * 4
        )
        def short_summary(messages, endpoint):
            return "tiny"

        events = []
        with mock.patch.object(compaction, "_log_compaction",
                                side_effect=lambda e, **kw: events.append((e, kw))):
            with mock.patch("boot.load_routing_config", return_value={}):
                with mock.patch("boot.get_slot_endpoint", return_value=None):
                    with mock.patch("boot.get_active_endpoint",
                                     return_value={"name": "test-ep"}):
                        compaction.compact_context(msgs,
                                                    call_model_fn=short_summary,
                                                    context_limit=100)
        kinds = [e for e, _ in events]
        self.assertIn("failed", kinds)
        failed_event = next(kw for e, kw in events if e == "failed")
        self.assertEqual(failed_event["reason"], "summary_too_short_or_empty")
        self.assertIn("middle_chars_lost_if_we_proceeded", failed_event)

    def test_compacted_summary_is_system_attributed(self):
        msgs = (
            [{"role": "system", "content": "sys"}]
            + [{"role": "user", "content": "u" * 1500}] * 4
            + [{"role": "assistant", "content": "a" * 1500}] * 4
        )
        def good_summary(messages, endpoint):
            return "Summary: discussed X, decided Y, open question Z. " * 5

        with mock.patch("boot.load_routing_config", return_value={}):
            with mock.patch("boot.get_slot_endpoint", return_value=None):
                with mock.patch("boot.get_active_endpoint",
                                 return_value={"name": "test-ep"}):
                    out = compaction.compact_context(msgs,
                                                      call_model_fn=good_summary,
                                                      context_limit=200)
        summary_msg = next(
            m for m in out if "COMPACTED CONTEXT" in (m.get("content") or "")
        )
        self.assertEqual(summary_msg["role"], "system")
        self.assertIn("the model did not say this", summary_msg["content"])


# ---------------------------------------------------------------------------
# RAG ranker truncation visibility
# ---------------------------------------------------------------------------

class TestRagRankerTruncationVisible(unittest.TestCase):
    def test_truncated_package_carries_trailer(self):
        # Chunks small enough that the first two fit but the third doesn't.
        chunks = [
            {"document": "x" * 800,
             "metadata": {"source": f"src{i}.md", "type": "engram"},
             "weight": 1.0 / (i + 1)}
            for i in range(5)
        ]
        out = rag_engine.format_context_with_provenance(chunks, max_chars=2000)
        self.assertIn("ranker-truncation", out)
        self.assertIn("SUPPLEMENTAL RAG REQUEST", out)
        # Some dropped source MUST appear in the trailer.
        self.assertTrue(any(f"src{i}.md" in out for i in range(2, 5)))

    def test_no_truncation_no_trailer(self):
        chunks = [
            {"document": "y" * 100,
             "metadata": {"source": "small.md", "type": "engram"},
             "weight": 1.0}
        ]
        out = rag_engine.format_context_with_provenance(chunks, max_chars=5000)
        self.assertNotIn("ranker-truncation", out)


# ---------------------------------------------------------------------------
# conversation.json per-conversation write lock
# ---------------------------------------------------------------------------

class TestConversationWriteLock(unittest.TestCase):
    def setUp(self):
        if "orchestrator.conversation_memory" in sys.modules:
            return
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "orchestrator.conversation_memory",
            os.path.join(HERE, "conversation_memory.py"),
        )
        if "orchestrator" not in sys.modules:
            pkg = type(sys)("orchestrator")
            pkg.__path__ = [HERE]
            sys.modules["orchestrator"] = pkg
        mod = importlib.util.module_from_spec(spec)
        sys.modules["orchestrator.conversation_memory"] = mod
        spec.loader.exec_module(mod)

    def test_concurrent_writes_to_same_conversation_serialise(self):
        from orchestrator.conversation_memory import save_turn_spatial_state
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            errors = []

            def writer(i):
                try:
                    save_turn_spatial_state(
                        "race-conv",
                        user_input=f"u{i}",
                        ai_response=f"a{i}",
                        sessions_root=root,
                    )
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=writer, args=(i,))
                       for i in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errors, [])
            # Every pair must land (2 messages per writer × 10 writers = 20).
            data = json.loads((root / "race-conv" / "conversation.json").read_text())
            self.assertEqual(len(data["messages"]), 20)


# ---------------------------------------------------------------------------
# Tool outcome classification
# ---------------------------------------------------------------------------

class TestToolOutcomeClassification(unittest.TestCase):
    def test_error_marker_classified_as_error(self):
        out, reason = boot.classify_tool_outcome(
            "bash_execute",
            "[Tool error — bash_execute: command not found]",
        )
        self.assertEqual(out, "error")

    def test_empty_result_classified_as_empty(self):
        out, reason = boot.classify_tool_outcome("knowledge_search", "")
        self.assertEqual(out, "empty")

    def test_normal_result_classified_as_ok(self):
        out, reason = boot.classify_tool_outcome(
            "knowledge_search",
            "Found 3 relevant chunks: file1.md, file2.md, file3.md",
        )
        self.assertEqual(out, "ok")

    def test_parse_error_params_surface_in_execute_tool(self):
        # When parse_tool_calls fails to parse JSON, the params dict carries
        # _parse_error. execute_tool must catch this and not try to run.
        result = boot.execute_tool("mytool", {
            "_parse_error": "Expecting value: line 1 column 2",
            "raw": "{garbage",
        })
        self.assertIn("[Tool error", result)
        self.assertIn("failed to parse as JSON", result)

    def test_with_outcome_wrapper_returns_triple(self):
        with mock.patch.object(boot, "execute_tool", return_value="ok result"):
            result, outcome, reason = boot.execute_tool_with_outcome("t", {})
        self.assertEqual(result, "ok result")
        self.assertEqual(outcome, "ok")


if __name__ == "__main__":
    unittest.main()
