"""Tests for the per-file orchestrator (Phase 1.11)."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical.api_client import AnthropicClient  # noqa: E402
from orchestrator.historical.file_orchestrator import (  # noqa: E402
    ABORT_ERROR_FRACTION,
    FileProcessingResult,
    ProgressEvent,
    process_chat_file,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_SAMPLE_WEB_CLIPPER = """---
title: Test Chat
type: chat
---
# Test Chat

## Overview

- **Title:** Test Chat
- **Url:** [https://chatgpt.com/c/test](https://chatgpt.com/c/test)
- **ID:** test-conv-001
- **Created:** 7/14/2025, 9:00:00 AM
- **Last Updated:** 7/14/2025, 9:30:00 AM
- **Total Messages:** 6

## Conversation

<i>[7/14/2025, 9:00:00 AM]</i> 👉 <b>👤 User</b>: First question about quantum mechanics.
<i>[7/14/2025, 9:00:05 AM]</i> 👉 <b>🤖 Assistant</b>: First answer about quantum mechanics.<br>
<i>[7/14/2025, 9:10:00 AM]</i> 👉 <b>👤 User</b>: Second question about quantum waves.
<i>[7/14/2025, 9:10:05 AM]</i> 👉 <b>🤖 Assistant</b>: Second answer about quantum waves.<br>
<i>[7/14/2025, 9:20:00 AM]</i> 👉 <b>👤 User</b>: Third question about baking bread.
<i>[7/14/2025, 9:20:05 AM]</i> 👉 <b>🤖 Assistant</b>: Third answer about baking bread.<br>
"""


class _FakeStream:
    def __init__(self, text, input_tokens=30, output_tokens=20):
        self._text = text
        self._in = input_tokens
        self._out = output_tokens
    def __enter__(self): return self
    def __exit__(self, *args): return False
    @property
    def text_stream(self):
        return iter([self._text])
    def get_final_message(self):
        msg = MagicMock()
        msg.usage = MagicMock(input_tokens=self._in, output_tokens=self._out)
        return msg


def _fake_message(text: str, input_tokens: int = 30,
                   output_tokens: int = 20) -> _FakeStream:
    return _FakeStream(text, input_tokens, output_tokens)


def _make_client_returning_cleanups():
    """Return a client whose .stream() returns a streaming context manager
    yielding 'cleaned: <prefix>' for each call."""
    fake = MagicMock()
    fake.messages = MagicMock()
    fake.messages.stream = MagicMock(side_effect=lambda **kwargs:
        _fake_message(f"cleaned: {kwargs.get('messages', [{}])[0].get('content','')[:30]}"))
    return AnthropicClient(client=fake)


# ---------------------------------------------------------------------------
# End-to-end happy path
# ---------------------------------------------------------------------------


class TestEndToEnd(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.raw_path = os.path.join(self.tmp, "test_chat.md")
        with open(self.raw_path, "w", encoding="utf-8") as f:
            f.write(_SAMPLE_WEB_CLIPPER)
        self.output_dir = os.path.join(self.tmp, "cleaned")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_processes_all_pairs(self):
        client = _make_client_returning_cleanups()
        result = process_chat_file(
            self.raw_path,
            vault_index={"entries": []},
            anthropic_client=client,
            output_dir=self.output_dir,
            max_workers=2,
            engagement_log_path=os.path.join(self.tmp, "strips.log"),
        )
        self.assertEqual(result.pairs_total, 3)
        self.assertEqual(result.pairs_succeeded, 3)
        self.assertEqual(result.pairs_with_errors, 0)
        self.assertEqual(len(result.output_paths), 3)
        self.assertEqual(result.chat_platform, "chatgpt")
        # Output files exist
        for p in result.output_paths:
            self.assertTrue(os.path.exists(p))

    def test_progress_callback_invoked(self):
        client = _make_client_returning_cleanups()
        events: list[ProgressEvent] = []
        process_chat_file(
            self.raw_path,
            vault_index={"entries": []},
            anthropic_client=client,
            output_dir=self.output_dir,
            max_workers=2,
            progress_cb=events.append,
            engagement_log_path=os.path.join(self.tmp, "strips.log"),
        )
        stages = {e.stage for e in events}
        self.assertIn("parse", stages)
        self.assertIn("cleanup-start", stages)
        self.assertIn("cleanup-done", stages)
        self.assertIn("write", stages)
        self.assertIn("complete", stages)

    def test_engagement_strips_logged(self):
        # Make AI cleanup return engagement-wrapped responses.
        fake = MagicMock()
        fake.messages = MagicMock()
        responses = []
        for _ in range(3):
            responses.append(_fake_message("cleaned user input"))
            responses.append(_fake_message(
                "Real content.\n\nWould you like more details?"
            ))
        fake.messages.stream = MagicMock(side_effect=responses)
        client = AnthropicClient(client=fake)
        log_path = os.path.join(self.tmp, "strips.log")
        result = process_chat_file(
            self.raw_path,
            vault_index={"entries": []},
            anthropic_client=client,
            output_dir=self.output_dir,
            max_workers=1,
            engagement_log_path=log_path,
        )
        self.assertGreater(result.engagement_strips_logged, 0)
        self.assertTrue(os.path.exists(log_path))


# ---------------------------------------------------------------------------
# Error budget / abort
# ---------------------------------------------------------------------------


class TestErrorBudget(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.raw_path = os.path.join(self.tmp, "test_chat.md")
        with open(self.raw_path, "w", encoding="utf-8") as f:
            f.write(_SAMPLE_WEB_CLIPPER)
        self.output_dir = os.path.join(self.tmp, "cleaned")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_abort_when_majority_pairs_fail(self):
        # Every API call raises terminally → all 3 pairs error out
        # → ratio = 100% > 50% → abort.
        class TerminalErr(Exception):
            pass
        fake = MagicMock()
        fake.messages = MagicMock()
        fake.messages.stream = MagicMock(side_effect=TerminalErr("nope"))
        client = AnthropicClient(client=fake)
        client._backoff = staticmethod(lambda attempt: 0.0)
        result = process_chat_file(
            self.raw_path,
            vault_index={"entries": []},
            anthropic_client=client,
            output_dir=self.output_dir,
            max_workers=1,
            engagement_log_path=os.path.join(self.tmp, "strips.log"),
        )
        self.assertTrue(result.aborted)
        self.assertIn("error rate", result.abort_reason)
        # No files written.
        self.assertEqual(result.output_paths, [])

    def test_parse_failure_aborts(self):
        bad_path = os.path.join(self.tmp, "missing.md")
        client = _make_client_returning_cleanups()
        result = process_chat_file(
            bad_path,
            vault_index={"entries": []},
            anthropic_client=client,
            output_dir=self.output_dir,
            max_workers=1,
            engagement_log_path=os.path.join(self.tmp, "strips.log"),
        )
        self.assertTrue(result.aborted)
        self.assertEqual(result.abort_reason, "parse failed")


# ---------------------------------------------------------------------------
# Empty file handling
# ---------------------------------------------------------------------------


class TestEmptyChat(unittest.TestCase):

    def test_empty_chat_produces_zero_pairs(self):
        tmp = tempfile.mkdtemp()
        try:
            raw = os.path.join(tmp, "empty.md")
            with open(raw, "w") as f:
                f.write("---\ntype: chat\n---\n# Just a heading, no turns")
            client = _make_client_returning_cleanups()
            result = process_chat_file(
                raw, vault_index={"entries": []},
                anthropic_client=client,
                output_dir=os.path.join(tmp, "out"),
                max_workers=1,
                engagement_log_path=os.path.join(tmp, "strips.log"),
            )
            self.assertEqual(result.pairs_total, 0)
            self.assertEqual(result.output_paths, [])
            self.assertFalse(result.aborted)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
