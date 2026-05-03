"""Tests for the cleaned-pair file reader (Phase 2A foundation).

Verifies the reader extracts frontmatter + body sections correctly from
the four shapes Phase 1 emits:
  1. Standard pair (both sides present)
  2. Empty user input (Claude Code "press Enter to advance" case)
  3. Empty AI response (user message sent, no reply captured)
  4. AI response containing markdown `###` headings (must NOT truncate)
  5. Pasted-segments + engagement-strip annotations (must be stripped
     from the cleaned text exposed by the reader)
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical.cleaned_pair_reader import (  # noqa: E402
    CleanedPairFile,
    load_cleaned_pair,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _frontmatter(
    pair_num: int = 1,
    platform: str = "claude",
    timestamp: str = "2025-06-15T10:30:00",
    thread_id: str = "thread_abc12345_001",
    prior_pair: str = "",
    next_pair: str = "",
    processing_model: str = "claude-haiku-4-5",
) -> str:
    return (
        "---\n"
        "nexus:\n"
        "type: cleaned-pair\n"
        f"date created: 2025-06-15\n"
        f"date modified: 2026-05-02\n"
        f"source_chat: ~/Documents/conversations/raw/test-chat.md\n"
        f"source_pair_num: {pair_num}\n"
        f"source_platform: {platform}\n"
        f"source_timestamp: {timestamp}\n"
        f"thread_id: {thread_id}\n"
        f"prior_pair: {prior_pair}\n"
        f"next_pair: {next_pair}\n"
        f"processing_model: {processing_model}\n"
        f"processed_at: 2026-05-02T08:00:00\n"
        "tags: []\n"
        "---\n"
    )


def _write_file(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


# ---------------------------------------------------------------------------
# Standard pair
# ---------------------------------------------------------------------------


class TestStandardPair(unittest.TestCase):

    def test_standard_pair_parses(self):
        content = _frontmatter() + (
            "\n## Context\n\n"
            "### Session context\n\n"
            "Conversation about quantum mechanics.\n\n"
            "### Pair context\n\n"
            "Pair 1 of 12.\n\n"
            "## Exchange\n\n"
            "### User input\n\n"
            "Tell me about quantum entanglement.\n\n"
            "### Assistant response\n\n"
            "Quantum entanglement is a physical phenomenon.\n"
        )
        path = _write_file(content)
        try:
            cp = load_cleaned_pair(path)
            self.assertEqual(cp.source_pair_num, 1)
            self.assertEqual(cp.source_platform, "claude")
            self.assertEqual(cp.thread_id, "thread_abc12345_001")
            self.assertEqual(cp.processing_model, "claude-haiku-4-5")
            self.assertIsNotNone(cp.source_timestamp)
            self.assertIn("quantum", cp.session_context.lower())
            self.assertIn("Pair 1", cp.pair_context)
            self.assertEqual(cp.cleaned_user_input,
                             "Tell me about quantum entanglement.")
            self.assertEqual(cp.cleaned_ai_response,
                             "Quantum entanglement is a physical phenomenon.")
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Phase 1 empty-side success contract
# ---------------------------------------------------------------------------


class TestEmptySides(unittest.TestCase):

    def test_empty_user_input_section(self):
        # Claude Code "press Enter" case — user side is empty.
        content = _frontmatter() + (
            "\n## Context\n\n"
            "### Session context\n\n"
            "An installer flow.\n\n"
            "### Pair context\n\n"
            "Pair 5.\n\n"
            "## Exchange\n\n"
            "### User input\n\n"
            "\n\n"
            "### Assistant response\n\n"
            "Theme selected. Continuing setup.\n"
        )
        path = _write_file(content)
        try:
            cp = load_cleaned_pair(path)
            self.assertEqual(cp.cleaned_user_input, "")
            self.assertIn("Theme selected", cp.cleaned_ai_response)
        finally:
            os.unlink(path)

    def test_empty_ai_response_section(self):
        content = _frontmatter() + (
            "\n## Context\n\n"
            "### Session context\n\n"
            "An interrupted exchange.\n\n"
            "### Pair context\n\n"
            "Pair 2.\n\n"
            "## Exchange\n\n"
            "### User input\n\n"
            "Please continue from where we left off.\n\n"
            "### Assistant response\n\n"
            "\n"
        )
        path = _write_file(content)
        try:
            cp = load_cleaned_pair(path)
            self.assertIn("Please continue", cp.cleaned_user_input)
            self.assertEqual(cp.cleaned_ai_response, "")
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Markdown headings inside content (must NOT truncate sections)
# ---------------------------------------------------------------------------


class TestMarkdownInsideContent(unittest.TestCase):

    def test_ai_response_with_markdown_headings_is_fully_captured(self):
        # AI response carries `###` and `####` markdown headings — those
        # are content, not section boundaries.
        ai_body = (
            "Here's the analysis:\n\n"
            "### Section A\n\n"
            "Some content.\n\n"
            "#### Subsection\n\n"
            "More content.\n\n"
            "### Section B\n\n"
            "Final content."
        )
        content = _frontmatter() + (
            "\n## Context\n\n"
            "### Session context\n\nA discussion.\n\n"
            "### Pair context\n\nPair 1.\n\n"
            "## Exchange\n\n"
            "### User input\n\nAnalyze this.\n\n"
            f"### Assistant response\n\n{ai_body}\n"
        )
        path = _write_file(content)
        try:
            cp = load_cleaned_pair(path)
            self.assertIn("### Section A", cp.cleaned_ai_response)
            self.assertIn("#### Subsection", cp.cleaned_ai_response)
            self.assertIn("Final content.", cp.cleaned_ai_response)
        finally:
            os.unlink(path)

    def test_user_input_with_markdown_headings_is_fully_captured(self):
        user_body = (
            "Here's a doc dump:\n\n"
            "### Heading 1\n\n"
            "Content.\n\n"
            "### Heading 2\n\n"
            "More content."
        )
        content = _frontmatter() + (
            "\n## Context\n\n"
            "### Session context\n\nA doc review.\n\n"
            "### Pair context\n\nPair 1.\n\n"
            "## Exchange\n\n"
            f"### User input\n\n{user_body}\n\n"
            "### Assistant response\n\nAcknowledged.\n"
        )
        path = _write_file(content)
        try:
            cp = load_cleaned_pair(path)
            self.assertIn("### Heading 1", cp.cleaned_user_input)
            self.assertIn("### Heading 2", cp.cleaned_user_input)
            self.assertEqual(cp.cleaned_ai_response, "Acknowledged.")
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Optional annotation subsections must be stripped from cleaned content
# ---------------------------------------------------------------------------


class TestOptionalSubsectionStripping(unittest.TestCase):

    def test_pasted_segments_subsection_stripped_from_user_input(self):
        content = _frontmatter() + (
            "\n## Context\n\n"
            "### Session context\n\nA review.\n\n"
            "### Pair context\n\nPair 1.\n\n"
            "## Exchange\n\n"
            "### User input\n\n"
            "Cleaned user text.\n\n"
            "#### Pasted segments\n\n"
            "- **Segment 1** — type=`other`, status=`review`\n"
            "  - Source marker: `Pasted text starts here`\n\n"
            "### Assistant response\n\nReply.\n"
        )
        path = _write_file(content)
        try:
            cp = load_cleaned_pair(path)
            self.assertEqual(cp.cleaned_user_input, "Cleaned user text.")
            self.assertNotIn("Pasted segments", cp.cleaned_user_input)
            self.assertNotIn("Source marker", cp.cleaned_user_input)
        finally:
            os.unlink(path)

    def test_engagement_strip_log_stripped_from_ai_response(self):
        content = _frontmatter() + (
            "\n## Context\n\n"
            "### Session context\n\nA discussion.\n\n"
            "### Pair context\n\nPair 1.\n\n"
            "## Exchange\n\n"
            "### User input\n\nQuestion.\n\n"
            "### Assistant response\n\n"
            "Cleaned reply.\n\n"
            "#### Engagement strip log\n\n"
            "- Stripped trailing paragraph (50 chars): \"Want me to elaborate?\"\n"
        )
        path = _write_file(content)
        try:
            cp = load_cleaned_pair(path)
            self.assertEqual(cp.cleaned_ai_response, "Cleaned reply.")
            self.assertNotIn("Engagement strip log", cp.cleaned_ai_response)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Frontmatter parsing edges
# ---------------------------------------------------------------------------


class TestFrontmatterParsing(unittest.TestCase):

    def test_yaml_quoted_values_unquoted(self):
        content = (
            "---\n"
            "nexus:\n"
            "type: cleaned-pair\n"
            "date created: 2025-06-15\n"
            "date modified: 2025-06-15\n"
            "source_chat: '~/Documents/conversations/raw/Path with: colons.md'\n"
            "source_pair_num: 1\n"
            "source_platform: claude\n"
            "source_timestamp: 2025-06-15T10:30:00\n"
            "thread_id: thread_abc12345_001\n"
            "prior_pair:\n"
            "next_pair:\n"
            "processing_model: claude-haiku-4-5\n"
            "processed_at: 2026-05-02T08:00:00\n"
            "tags: []\n"
            "---\n"
            "\n## Context\n### Session context\nfoo\n### Pair context\nbar\n"
            "## Exchange\n### User input\nU\n### Assistant response\nA\n"
        )
        path = _write_file(content)
        try:
            cp = load_cleaned_pair(path)
            self.assertEqual(
                cp.source_chat,
                "~/Documents/conversations/raw/Path with: colons.md",
            )
        finally:
            os.unlink(path)

    def test_missing_frontmatter_raises(self):
        path = _write_file("Just markdown, no frontmatter.\n")
        try:
            with self.assertRaises(ValueError):
                load_cleaned_pair(path)
        finally:
            os.unlink(path)

    def test_missing_exchange_section_raises(self):
        content = _frontmatter() + "\n## Context\nNo Exchange section follows.\n"
        path = _write_file(content)
        try:
            with self.assertRaises(ValueError):
                load_cleaned_pair(path)
        finally:
            os.unlink(path)

    def test_unparseable_pair_num_raises(self):
        content = (
            "---\n"
            "type: cleaned-pair\n"
            "source_pair_num: not-a-number\n"
            "---\n"
            "## Exchange\n### User input\nU\n### Assistant response\nA\n"
        )
        path = _write_file(content)
        try:
            with self.assertRaises(ValueError):
                load_cleaned_pair(path)
        finally:
            os.unlink(path)

    def test_timestamp_parsed_as_datetime(self):
        content = _frontmatter(timestamp="2025-06-15T10:30:00") + (
            "\n## Context\n### Session context\nfoo\n### Pair context\nbar\n"
            "## Exchange\n### User input\nU\n### Assistant response\nA\n"
        )
        path = _write_file(content)
        try:
            cp = load_cleaned_pair(path)
            self.assertIsInstance(cp.source_timestamp, datetime)
            self.assertEqual(cp.source_timestamp.year, 2025)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
