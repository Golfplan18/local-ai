"""Sweep-3 silent-failure probes: dispatch-layer error strings + parse_tool_calls
malformed JSON + conversation.json atomic writes / corruption recovery.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stderr
from pathlib import Path

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKTREE_ROOT = os.path.dirname(HERE)
for p in (HERE, WORKTREE_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import boot


# ---------------------------------------------------------------------------
# Dispatch-layer error strings caught by health check
# ---------------------------------------------------------------------------

class TestDispatchErrorStringsAreUnhealthy(unittest.TestCase):
    """Each of these strings is what boot.py's dispatch layer returns to
    callers on failure. Without health-check pattern coverage, they
    flowed downstream as if they were real model output.
    """

    CASES = [
        "[Error calling Claude API: 401 Unauthorized] " + "x" * 250,
        "[Error calling OpenAI API: context_length_exceeded] " + "x" * 250,
        "[Error calling Gemini API: 503 Service Unavailable] " + "x" * 250,
        "[Error calling local model: timeout after 120s] " + "x" * 250,
        "[Error calling MLX model 'qwen3.5-27b': out of memory] " + "x" * 250,
        "[MLX model not found: 'missing-model' — check the model path] " + "x" * 250,
        "[Error] Unsupported API service: bing " + "x" * 250,
        "[Error] Unsupported engine: vllm " + "x" * 250,
        "[Error] Unknown endpoint type: experimental " + "x" * 250,
        "[No response] " + "x" * 250,
        "[Tools unavailable — import failed at startup] " + "x" * 250,
        "[Tool error — knowledge_search: ChromaDB not initialised] " + "x" * 250,
    ]

    def test_each_dispatch_error_string_flagged(self):
        for case in self.CASES:
            with self.subTest(case=case[:60]):
                ok, reason = boot._step_output_health(
                    case, step_name="analyst", min_chars=200
                )
                self.assertFalse(
                    ok, f"Health check missed dispatch error: {case[:80]!r}"
                )


# ---------------------------------------------------------------------------
# parse_tool_calls malformed JSON warning
# ---------------------------------------------------------------------------

class TestParseToolCallsMalformedJson(unittest.TestCase):
    def test_invalid_json_logs_stderr_and_marks_parse_error(self):
        text = (
            "<tool_call><n>my_tool</n>"
            "<parameters>{not_valid_json: foo</parameters></tool_call>"
        )
        buf = io.StringIO()
        with redirect_stderr(buf):
            calls = boot.parse_tool_calls(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["name"], "my_tool")
        self.assertIn("_parse_error", calls[0]["parameters"])
        self.assertIn("raw", calls[0]["parameters"])
        self.assertIn("[parse_tool_calls] malformed JSON", buf.getvalue())

    def test_valid_json_no_warning(self):
        text = (
            "<tool_call><n>my_tool</n>"
            '<parameters>{"x": 1}</parameters></tool_call>'
        )
        buf = io.StringIO()
        with redirect_stderr(buf):
            calls = boot.parse_tool_calls(text)
        self.assertEqual(calls[0]["parameters"], {"x": 1})
        self.assertEqual(buf.getvalue(), "")


# ---------------------------------------------------------------------------
# conversation.json atomic writes + corruption recovery
# ---------------------------------------------------------------------------

class TestConversationMemoryAtomic(unittest.TestCase):
    def setUp(self):
        # Stub conversation_memory's relative-import dependency if needed.
        if "orchestrator.conversation_memory" in sys.modules:
            return
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "orchestrator.conversation_memory",
            os.path.join(HERE, "conversation_memory.py"),
        )
        # Make a package shell so the relative import works.
        if "orchestrator" not in sys.modules:
            pkg = type(sys)("orchestrator")
            pkg.__path__ = [HERE]
            sys.modules["orchestrator"] = pkg
        mod = importlib.util.module_from_spec(spec)
        sys.modules["orchestrator.conversation_memory"] = mod
        spec.loader.exec_module(mod)

    def test_atomic_write_uses_tmp_then_rename(self):
        from orchestrator.conversation_memory import save_turn_spatial_state as append_pair
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = append_pair(
                "conv-atomic",
                user_input="hello",
                ai_response="hi",
                sessions_root=root,
            )
            self.assertIsNotNone(p)
            self.assertTrue(p.exists())
            data = json.loads(p.read_text())
            self.assertEqual(len(data["messages"]), 2)
            # No .tmp left behind.
            self.assertFalse(p.with_suffix(p.suffix + ".tmp").exists())

    def test_corrupt_envelope_preserved_in_place(self):
        from orchestrator.conversation_memory import save_turn_spatial_state as append_pair
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conv_dir = root / "conv-corrupt"
            conv_dir.mkdir()
            corrupt_path = conv_dir / "conversation.json"
            for content in (b"{this is not valid JSON", b"[]", b'{"messages": {}}', b"\xff"):
                with self.subTest(content=content):
                    corrupt_path.write_bytes(content)
                    buf = io.StringIO()
                    with redirect_stderr(buf), mock.patch.object(Path, "rename") as rename:
                        result = append_pair(
                            "conv-corrupt", "new turn", "response", sessions_root=root,
                        )
                    self.assertIsNone(result)
                    self.assertIn("preserving the existing file", buf.getvalue())
                    self.assertEqual(corrupt_path.read_bytes(), content)
                    rename.assert_not_called()
                    self.assertEqual(list(conv_dir.glob("conversation.json.corrupt-*")), [])
            content = b'{"messages": [], "tag": "private"}'
            corrupt_path.write_bytes(content)
            with mock.patch.object(Path, "read_text", side_effect=PermissionError("unreadable")):
                result = append_pair("conv-corrupt", "new turn", "response", sessions_root=root)
            self.assertIsNone(result)
            self.assertEqual(corrupt_path.read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
