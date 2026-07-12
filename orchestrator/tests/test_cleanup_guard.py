"""Tests for the cleanup refusal guard + pluggable backends (CPP v2.1).

Covers:
  - looks_like_cleanup_refusal: signature detection, input-echo immunity
  - strip_cleanup_preamble: framing-line removal
  - clean_pair integration: user-side refusal falls back to raw text,
    AI-side refusal falls back to raw response, guard log is written
  - ClaudeCLIClient: model-alias mapping, subprocess call construction,
    retry-then-fail behavior (all subprocess calls mocked)
  - build_client: backend selection
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical import RawPair, RawTurn  # noqa: E402
from orchestrator.historical.api_client import AnthropicClient  # noqa: E402
from orchestrator.historical.cleanup_backends import (  # noqa: E402
    BACKEND_API,
    BACKEND_CLAUDE_CLI,
    ClaudeCLIClient,
    OraSlotClient,
    build_client,
)
from orchestrator.historical.pair_cleanup import clean_pair  # noqa: E402
from orchestrator.historical.prompts import (  # noqa: E402
    looks_like_cleanup_refusal,
    strip_cleanup_preamble,
)


REFUSAL_TEXT = (
    "I appreciate the instruction, but I need to clarify my role: I'm a "
    "text-cleanup tool, and the input you've provided is a request, not "
    "a user's past message that needs cleaning."
)


def _make_pair(user: str, assistant: str, pair_num: int = 1) -> RawPair:
    when = datetime(2026, 7, 10, 9, 0, 0)
    user_turn = RawTurn(role="user", content=user, timestamp=when,
                        raw_text=user)
    asst_turn = RawTurn(role="assistant", content=assistant,
                        timestamp=when, raw_text=assistant)
    return RawPair(
        pair_num=pair_num,
        user_turn=user_turn,
        assistant_turns=[asst_turn] if assistant else [],
        when=when,
    )


class _FakeStream:
    def __init__(self, text):
        self._text = text
    def __enter__(self): return self
    def __exit__(self, *args): return False
    @property
    def text_stream(self):
        return iter([self._text])
    def get_final_message(self):
        msg = MagicMock()
        msg.usage = MagicMock(input_tokens=50, output_tokens=30)
        return msg


def _client_with_responses(*texts) -> AnthropicClient:
    fake = MagicMock()
    fake.messages = MagicMock()
    fake.messages.stream = MagicMock(
        side_effect=[_FakeStream(t) for t in texts],
    )
    return AnthropicClient(client=fake)


# ---------------------------------------------------------------------------
# Detection primitives
# ---------------------------------------------------------------------------


class TestRefusalDetection(unittest.TestCase):

    def test_refusal_is_detected(self):
        sig = looks_like_cleanup_refusal(REFUSAL_TEXT, "Describe this image.")
        self.assertIsNotNone(sig)

    def test_clean_output_passes(self):
        self.assertIsNone(looks_like_cleanup_refusal(
            "I want to build a folder watcher for conversation imports.",
            "i wanna build like a folder watcher thing for the convo imports",
        ))

    def test_signature_in_input_does_not_trip(self):
        # The user's own conversations about this pipeline legitimately
        # contain the signature phrases — guard must not fire.
        text = ("The cleanup prompt says: 'You are a text-cleanup tool' "
                "and that wording caused refusals.")
        self.assertIsNone(looks_like_cleanup_refusal(text, text))

    def test_empty_output_passes(self):
        self.assertIsNone(looks_like_cleanup_refusal("", "anything"))

    def test_cannot_process_detected(self):
        sig = looks_like_cleanup_refusal(
            "I cannot process this input. The text provided is a template.",
            "[Insert framework purpose here]",
        )
        self.assertIsNotNone(sig)

    def test_generic_safety_refusal_detected(self):
        sig = looks_like_cleanup_refusal(
            "I'm sorry, but I can't reproduce that content.",
            "summarize the article i pasted",
        )
        self.assertIsNotNone(sig)

    def test_copyright_refusal_detected(self):
        sig = looks_like_cleanup_refusal(
            "Due to copyright restrictions I can only summarize this.",
            "here are the lyrics i was discussing",
        )
        self.assertIsNotNone(sig)

    def test_elicitation_reply_detected(self):
        sig = looks_like_cleanup_refusal(
            "Please provide the text you'd like me to clean.",
            "ok",
        )
        self.assertIsNotNone(sig)

    def test_truncation_marker_detected(self):
        sig = looks_like_cleanup_refusal(
            "The first half of the thought... [TRUNCATED - length limit]",
            "a very long dictated passage",
        )
        self.assertIsNotNone(sig)


class TestPreambleStrip(unittest.TestCase):

    def test_here_is_the_cleaned_text_stripped(self):
        out = strip_cleanup_preamble(
            "Here is the cleaned text:\nThe actual content.")
        self.assertEqual(out, "The actual content.")

    def test_heres_variant_stripped(self):
        out = strip_cleanup_preamble(
            "Here's the cleaned version:\n\nThe actual content.")
        self.assertEqual(out, "The actual content.")

    def test_text_without_preamble_unchanged(self):
        text = "The user asked about provenance weighting in RAG."
        self.assertEqual(strip_cleanup_preamble(text), text)

    def test_mid_text_here_is_not_stripped(self):
        text = "First line.\nHere is the cleaned truth of it: nothing."
        self.assertEqual(strip_cleanup_preamble(text), text)

    def test_framing_line_present_in_input_not_stripped(self):
        # An archived assistant response that genuinely BEGAN with a
        # framing line must survive cleanup intact (immunity rule).
        text = ("Here's the revised version of your paragraph:\n\n"
                "The committee found three problems.")
        self.assertEqual(strip_cleanup_preamble(text, input_text=text), text)

    def test_preamble_only_output_strips_to_empty(self):
        # A model output that is ONLY a framing line (truncation shape)
        # must strip to empty so the empty-output guard can catch it.
        self.assertEqual(strip_cleanup_preamble("Here is the cleaned text:"),
                         "")


# ---------------------------------------------------------------------------
# clean_pair integration
# ---------------------------------------------------------------------------


class TestGuardIntegration(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._log = os.path.join(self._tmp.name, "guard.log")
        os.environ["ORA_CLEANUP_GUARD_LOG"] = self._log

    def tearDown(self):
        os.environ.pop("ORA_CLEANUP_GUARD_LOG", None)
        self._tmp.cleanup()

    def test_user_refusal_falls_back_to_raw(self):
        raw_user = "Describe this image."
        client = _client_with_responses(REFUSAL_TEXT, "A fine response.")
        out = clean_pair(_make_pair(raw_user, "A fine response."),
                         anthropic_client=client, source_path="/x/y.md")
        self.assertEqual(out.cleaned_user_input, raw_user)
        self.assertTrue(any("commentary" in w
                            for w in out.user_cleanup_warnings))
        # Guard log written
        with open(self._log, encoding="utf-8") as fh:
            rec = json.loads(fh.readline())
        self.assertEqual(rec["side"], "user")
        self.assertEqual(rec["action"], "raw_preserved")
        self.assertEqual(rec["source_path"], "/x/y.md")

    def test_ai_refusal_falls_back_to_raw(self):
        raw_ai = "The mechanism works through three stages of review."
        client = _client_with_responses(
            "The user asked about mechanisms.",   # user side, clean
            REFUSAL_TEXT,                          # ai side, refusal
        )
        out = clean_pair(_make_pair("how's the mechanism work", raw_ai),
                         anthropic_client=client, source_path="/x/y.md")
        self.assertEqual(out.cleaned_ai_response, raw_ai)
        self.assertEqual(out.ai_record.retried_tier, "guard-raw-preserved")

    def test_clean_output_used_normally(self):
        client = _client_with_responses(
            "I want to compare provenance weighting approaches.",
            "Provenance weighting can be handled three ways.",
        )
        out = clean_pair(
            _make_pair("i wanna compare like the providence weighting stuff",
                       "Provenance weighting can be handled three ways."),
            anthropic_client=client,
        )
        self.assertIn("provenance", out.cleaned_user_input)
        self.assertFalse(os.path.exists(self._log))

    def test_preamble_stripped_before_guard(self):
        client = _client_with_responses(
            "Here is the cleaned text:\nI want a folder watcher.",
            "Sure — a watcher works.",
        )
        out = clean_pair(_make_pair("i want uh a folder watcher",
                                    "Sure — a watcher works."),
                         anthropic_client=client)
        self.assertEqual(out.cleaned_user_input, "I want a folder watcher.")

    def test_empty_output_falls_back_to_raw_user(self):
        raw_user = "a real thought that must not vanish"
        client = _client_with_responses("", "fine response")
        out = clean_pair(_make_pair(raw_user, "fine response"),
                         anthropic_client=client, source_path="/x/y.md")
        self.assertEqual(out.cleaned_user_input, raw_user)
        with open(self._log, encoding="utf-8") as fh:
            rec = json.loads(fh.readline())
        self.assertEqual(rec["signature"], "empty-output")

    def test_preamble_only_ai_output_falls_back_to_raw(self):
        raw_ai = "The full response with actual substance in it."
        client = _client_with_responses(
            "A clean user input.",
            "Here is the cleaned text:\n",   # truncation shape
        )
        out = clean_pair(_make_pair("a clean user input", raw_ai),
                         anthropic_client=client)
        self.assertEqual(out.cleaned_ai_response, raw_ai)

    def test_ai_response_beginning_with_framing_line_survives(self):
        raw_ai = ("Here's the revised version of your paragraph:\n\n"
                  "The committee found three problems.")
        client = _client_with_responses("A clean user input.", raw_ai)
        out = clean_pair(_make_pair("a clean user input", raw_ai),
                         anthropic_client=client)
        self.assertEqual(out.cleaned_ai_response, raw_ai)

    def test_preamble_then_wrapper_tag_both_stripped(self):
        client = _client_with_responses(
            "Here is the cleaned text:\n<input_to_clean>\nThe thought."
            "\n</input_to_clean>",
            "fine response",
        )
        out = clean_pair(_make_pair("the uh thought", "fine response"),
                         anthropic_client=client)
        self.assertEqual(out.cleaned_user_input, "The thought.")


# ---------------------------------------------------------------------------
# Claude CLI backend
# ---------------------------------------------------------------------------


def _proc(returncode=0, stdout="cleaned text", stderr=""):
    p = MagicMock()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


class TestClaudeCLIClient(unittest.TestCase):

    def _client(self):
        with patch("orchestrator.historical.cleanup_backends.shutil.which",
                   return_value="/usr/local/bin/claude"):
            return ClaudeCLIClient(max_retries=2, timeout_secs=5)

    def test_model_alias_mapping(self):
        c = self._client()
        self.assertEqual(c._cli_model("claude-haiku-4-5"), "haiku")
        self.assertEqual(c._cli_model("claude-sonnet-4-5"), "sonnet")
        self.assertEqual(c._cli_model(None), "haiku")

    def test_model_env_override(self):
        c = self._client()
        os.environ["ORA_CLEANUP_CLI_MODEL"] = "opus"
        try:
            self.assertEqual(c._cli_model("claude-haiku-4-5"), "opus")
        finally:
            os.environ.pop("ORA_CLEANUP_CLI_MODEL", None)

    def test_successful_call(self):
        c = self._client()
        with patch("orchestrator.historical.cleanup_backends.subprocess.run",
                   return_value=_proc()) as run:
            result = c.call(system="sys prompt", user="user text",
                            model="claude-haiku-4-5")
        self.assertEqual(result.text, "cleaned text")
        self.assertEqual(result.error, "")
        self.assertEqual(result.cost_usd, 0.0)
        cmd = run.call_args[0][0]
        self.assertIn("-p", cmd)
        self.assertIn("--model", cmd)
        self.assertIn("haiku", cmd)
        self.assertIn("--system-prompt", cmd)
        # User text goes via stdin, not argv.
        self.assertNotIn("user text", cmd)
        self.assertEqual(run.call_args[1]["input"], "user text")

    def test_launches_the_pathext_resolved_binary(self):
        resolved = r"C:\Users\Ora\bin\claude.cmd"
        with patch(
            "orchestrator.historical.cleanup_backends.shutil.which",
            return_value=resolved,
        ):
            client = ClaudeCLIClient(binary="claude")
        with patch(
            "orchestrator.historical.cleanup_backends.subprocess.run",
            return_value=_proc(),
        ) as run:
            client.call(system="s", user="u")
        self.assertEqual(client.binary, resolved)
        self.assertEqual(run.call_args[0][0][0], resolved)

    def test_call_is_locked_down(self):
        # The archive text is adversarial by construction; the CLI call
        # must be a pure text transform — no tools, no settings, no
        # session files, neutral cwd.
        c = self._client()
        with patch("orchestrator.historical.cleanup_backends.subprocess.run",
                   return_value=_proc()) as run:
            c.call(system="s", user="u", model="claude-haiku-4-5")
        cmd = run.call_args[0][0]
        self.assertIn("--tools", cmd)
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertIn("--setting-sources", cmd)
        self.assertEqual(cmd[cmd.index("--setting-sources") + 1], "")
        self.assertIn("--no-session-persistence", cmd)
        self.assertEqual(run.call_args[1]["cwd"], c._cwd)
        self.assertTrue(os.path.isdir(c._cwd))

    def test_retry_then_success(self):
        c = self._client()
        with patch("orchestrator.historical.cleanup_backends.subprocess.run",
                   side_effect=[_proc(returncode=1, stdout="", stderr="boom"),
                                _proc()]), \
             patch("orchestrator.historical.cleanup_backends.time.sleep"):
            result = c.call(system="s", user="u")
        self.assertEqual(result.text, "cleaned text")
        self.assertEqual(result.attempts, 2)

    def test_terminal_failure_sets_error(self):
        c = self._client()
        with patch("orchestrator.historical.cleanup_backends.subprocess.run",
                   return_value=_proc(returncode=1, stdout="", stderr="nope")), \
             patch("orchestrator.historical.cleanup_backends.time.sleep"):
            result = c.call(system="s", user="u")
        self.assertEqual(result.text, "")
        self.assertIn("exit 1", result.error)

    def test_missing_binary_raises(self):
        with patch("orchestrator.historical.cleanup_backends.shutil.which",
                   return_value=None):
            with self.assertRaises(RuntimeError):
                ClaudeCLIClient()


class TestCapCliWorkers(unittest.TestCase):

    def test_defaults_are_capped_to_total(self):
        from orchestrator.historical.cli import _cap_cli_workers
        fw, mw = _cap_cli_workers(max_workers=8, file_workers=12)
        self.assertLessEqual(fw * mw, 3)

    def test_sequential_file_worker_keeps_pair_parallelism(self):
        from orchestrator.historical.cli import _cap_cli_workers
        fw, mw = _cap_cli_workers(max_workers=8, file_workers=1)
        self.assertEqual((fw, mw), (1, 3))

    def test_small_values_pass_through(self):
        from orchestrator.historical.cli import _cap_cli_workers
        fw, mw = _cap_cli_workers(max_workers=1, file_workers=1)
        self.assertEqual((fw, mw), (1, 1))

    def test_never_zero(self):
        from orchestrator.historical.cli import _cap_cli_workers
        fw, mw = _cap_cli_workers(max_workers=1, file_workers=3)
        self.assertEqual((fw, mw), (3, 1))


class TestBackendFactory(unittest.TestCase):

    def test_unknown_backend_raises(self):
        with self.assertRaises(ValueError):
            build_client("nonsense")

    def test_claude_cli_backend_builds(self):
        with patch("orchestrator.historical.cleanup_backends.shutil.which",
                   return_value="/usr/local/bin/claude"):
            self.assertIsInstance(build_client(BACKEND_CLAUDE_CLI),
                                  ClaudeCLIClient)

    def test_ora_slot_heavy_routing(self):
        c = OraSlotClient()
        self.assertFalse(c._is_heavy("claude-haiku-4-5"))
        self.assertTrue(c._is_heavy("claude-sonnet-4-5"))


if __name__ == "__main__":
    unittest.main()
