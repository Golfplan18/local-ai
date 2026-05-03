"""Tests for the cleaned-pair file writer (Phase 1.10)."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical import (  # noqa: E402
    Platform, RawChat, RawChatMetadata, RawTurn,
)
from orchestrator.historical.context_header import ContextHeader  # noqa: E402
from orchestrator.historical.engagement import StripRecord  # noqa: E402
from orchestrator.historical.model_router import ModelRoute  # noqa: E402
from orchestrator.historical.pair_cleanup import (  # noqa: E402
    CleanedPair, CleanupSideRecord,
)
from orchestrator.historical.paste_detection import Segment  # noqa: E402
from orchestrator.historical.writer import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    build_body,
    build_cleaned_pair_markdown,
    build_yaml_frontmatter,
    write_cleaned_pair_file,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _raw_chat(title: str = "Test", platform: Platform = Platform.CHATGPT) -> RawChat:
    when = datetime(2025, 7, 14, 21, 0, 0)
    md = RawChatMetadata(
        title=title, platform=platform, created_at=when,
        conversation_id="conv-test",
    )
    return RawChat(
        source_path="raw/test.md", metadata=md,
        turns=[
            RawTurn(role="user", content="hi", timestamp=when, raw_text="hi"),
            RawTurn(role="assistant", content="ok", timestamp=when, raw_text="ok"),
        ],
    )


def _basic_route() -> ModelRoute:
    from orchestrator.historical.model_router import (
        TIER_HAIKU, MODEL_HAIKU,
    )
    return ModelRoute(
        tier=TIER_HAIKU, model_id=MODEL_HAIKU,
        dispatch="anthropic-api", slot_name="", rationale="test",
    )


def _cleaned_pair(
    *,
    user_text:        str = "Cleaned user input.",
    ai_text:          str = "Cleaned AI response.",
    pasted_segments:  list[Segment] = None,
    strips:           list[StripRecord] = None,
    when:             datetime = datetime(2025, 7, 14, 21, 0, 0),
) -> CleanedPair:
    record = CleanupSideRecord(
        route=_basic_route(),
        input_tokens=100, output_tokens=50, cost_usd=0.001,
    )
    return CleanedPair(
        pair_num=1,
        when=when,
        source_path="raw/test.md",
        user_segments=pasted_segments or [],
        cleaned_user_input=user_text,
        user_record=record,
        cleaned_ai_response=ai_text,
        cleaned_ai_pre_strip=ai_text,
        engagement_strips=strips or [],
        ai_record=record,
    )


def _context_header(filename: str = "2025-07-14_21-00_test.md") -> ContextHeader:
    return ContextHeader(
        session_context="Conversation 'Test' on chatgpt, dated 2025-07-14.",
        pair_context="Pair 1 of 1.",
        thread_id="thread_abc12345_001",
        is_thread_start=False,
        prior_pair_file="",
        next_pair_file="",
        pair_filename=filename,
        pair_keywords=["test", "input"],
    )


# ---------------------------------------------------------------------------
# YAML frontmatter
# ---------------------------------------------------------------------------


class TestYamlFrontmatter(unittest.TestCase):

    def test_frontmatter_has_all_required_fields(self):
        cp = _cleaned_pair()
        ch = _context_header()
        chat = _raw_chat()
        ym = build_yaml_frontmatter(cp, ch, chat,
                                       processed_at=datetime(2026, 5, 1, 12, 0, 0))
        for key in (
            "type: cleaned-pair",
            "date created:",
            "date modified:",
            "source_chat:",
            "source_pair_num: 1",
            "source_platform: chatgpt",
            "source_timestamp:",
            "thread_id: thread_abc12345_001",
            "prior_pair:",
            "next_pair:",
            "processing_model:",
            "processed_at:",
            "tags: []",
        ):
            self.assertIn(key, ym, f"missing: {key}")

    def test_frontmatter_starts_and_ends_with_fence(self):
        ym = build_yaml_frontmatter(_cleaned_pair(), _context_header(), _raw_chat())
        self.assertTrue(ym.startswith("---\n"))
        self.assertTrue("---\n" in ym[3:])  # closing fence


# ---------------------------------------------------------------------------
# Body
# ---------------------------------------------------------------------------


class TestBody(unittest.TestCase):

    def test_body_has_context_and_exchange_sections(self):
        body = build_body(_cleaned_pair(), _context_header())
        self.assertIn("## Context", body)
        self.assertIn("### Session context", body)
        self.assertIn("### Pair context", body)
        self.assertIn("## Exchange", body)
        self.assertIn("### User input", body)
        self.assertIn("### Assistant response", body)

    def test_body_contains_cleaned_text(self):
        cp = _cleaned_pair(user_text="user content here",
                            ai_text="ai response content")
        body = build_body(cp, _context_header())
        self.assertIn("user content here", body)
        self.assertIn("ai response content", body)

    def test_pasted_segments_section_only_when_pastes(self):
        # No pastes → no section
        body = build_body(_cleaned_pair(), _context_header())
        self.assertNotIn("#### Pasted segments", body)
        # With pastes → section present
        seg = Segment(
            kind="pasted", content="By Jane Smith, Reuters\n\nWASHINGTON — text",
            block_indices=(0, 0), classification="news", confidence=0.8,
            heuristic_flags=["byline", "dateline"],
        )
        body2 = build_body(_cleaned_pair(pasted_segments=[seg]), _context_header())
        self.assertIn("#### Pasted segments", body2)
        self.assertIn("type=`news`", body2)
        self.assertIn("status=`extract-news`", body2)
        self.assertIn("byline", body2)

    def test_pasted_segment_with_vault_match(self):
        seg = Segment(
            kind="pasted", content="Earlier draft content here",
            block_indices=(0, 0), classification="earlier-draft", confidence=0.95,
            heuristic_flags=["md-heading"],
            vault_match={
                "id": "vault-127",
                "vault_path": "Working — Book — NLP Outline v3.md",
                "title": "NLP Outline v3",
                "overlap_ratio": 0.78,
                "mature": True,
            },
        )
        body = build_body(_cleaned_pair(pasted_segments=[seg]), _context_header())
        self.assertIn("status=`mention-only`", body)
        self.assertIn("vault-127", body)
        self.assertIn("78%", body)

    def test_engagement_strip_log_only_when_strips(self):
        # No strips → no section
        body = build_body(_cleaned_pair(), _context_header())
        self.assertNotIn("#### Engagement strip log", body)
        # With strips → section present
        strip = StripRecord(
            paragraph="Want me to explain more?",
            paragraph_index=0, paragraph_length=24,
            reason="trailing-question",
        )
        body2 = build_body(_cleaned_pair(strips=[strip]), _context_header())
        self.assertIn("#### Engagement strip log", body2)
        self.assertIn("Want me to explain", body2)


# ---------------------------------------------------------------------------
# Full markdown + write to disk
# ---------------------------------------------------------------------------


class TestWrite(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_produces_well_formed_file(self):
        cp = _cleaned_pair()
        ch = _context_header()
        chat = _raw_chat()
        path = write_cleaned_pair_file(cp, ch, chat, output_dir=self.tmp)
        self.assertTrue(os.path.exists(path))
        text = open(path, encoding="utf-8").read()
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("type: cleaned-pair", text)
        self.assertIn("## Exchange", text)
        # Round-trip basic structure
        self.assertIn("Cleaned user input.", text)
        self.assertIn("Cleaned AI response.", text)

    def test_filename_collision_handled(self):
        cp = _cleaned_pair()
        ch = _context_header(filename="2025-07-14_21-00_test.md")
        chat = _raw_chat()
        # Pre-create the target file
        path1 = os.path.join(self.tmp, ch.pair_filename)
        open(path1, "w").write("placeholder")
        # Write — should land at a non-colliding path
        path2 = write_cleaned_pair_file(cp, ch, chat, output_dir=self.tmp)
        self.assertNotEqual(path1, path2)
        self.assertTrue("pair001" in os.path.basename(path2))


if __name__ == "__main__":
    unittest.main()
