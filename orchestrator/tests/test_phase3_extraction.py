"""Tests for Phase 3 extraction (news/opinion/resource → vault notes)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical.phase3_extraction import (  # noqa: E402
    ExtractionTarget,
    _slugify,
    _vault_path_for,
    build_vault_note,
    extract_segment,
    find_extraction_targets,
    write_vault_note,
)


# ---------------------------------------------------------------------------
# Slug helper
# ---------------------------------------------------------------------------


class TestSlugify(unittest.TestCase):

    def test_basic_slug(self):
        self.assertEqual(_slugify("Senate Passes Climate Bill"),
                         "senate-passes-climate-bill")

    def test_punctuation_stripped(self):
        self.assertEqual(_slugify("AI's Future: A Look"),
                         "ai-s-future-a-look")

    def test_max_words(self):
        s = _slugify("This Headline Has Many Many Many Many Many Words", max_words=3)
        self.assertEqual(s, "this-headline-has")

    def test_empty_or_punctuation_only(self):
        self.assertEqual(_slugify(""), "untitled")
        self.assertEqual(_slugify("!!!"), "untitled")


# ---------------------------------------------------------------------------
# Vault note building
# ---------------------------------------------------------------------------


class TestBuildVaultNote(unittest.TestCase):

    def _target(self, kind="news", user_voice="") -> ExtractionTarget:
        return ExtractionTarget(
            file_path="/tmp/fake.md",
            pair_num=5,
            when=datetime(2025, 7, 14, 21, 5, 0),
            source_chat="~/Documents/conversations/raw/test.md",
            source_platform="gemini",
            chain_id="chain-abcd1234",
            chain_label="topic-label",
            seg_index=2,
            seg_kind=kind,
            content="Original article text starts here. " * 30,
            user_voice=user_voice,
        )

    def test_news_note_structure(self):
        t = self._target(kind="news")
        extracted = {
            "headline":   "Senate Passes Climate Bill 87-12",
            "source":     "The Daily News",
            "date":       "2025-07-14",
            "lede":       "Lawmakers approved the climate bill in a late-night vote.",
            "key_facts":  ["Vote was 87 to 12.", "Bill includes grid funding."],
            "key_quotes": [{"quote": "A major step.", "speaker": "Sen. Doe", "context": "after the vote"}],
            "context":    "Negotiation took several months.",
        }
        body = build_vault_note(t, extracted)
        self.assertIn("type: resource", body)
        self.assertIn("- news", body)
        self.assertIn("# Senate Passes Climate Bill 87-12", body)
        self.assertIn("**Source:** The Daily News", body)
        self.assertIn("## Lede", body)
        self.assertIn("## Key Facts", body)
        self.assertIn("- Vote was 87 to 12.", body)
        self.assertIn("## Key Quotes", body)
        self.assertIn('> "A major step."', body)
        self.assertIn("Sen. Doe", body)
        self.assertIn("## Context", body)
        self.assertIn("## Original (excerpt)", body)
        self.assertIn("chain_id: chain-abcd1234", body)

    def test_opinion_note_includes_user_reaction(self):
        t = self._target(kind="opinion",
                          user_voice="I disagree with the framing here.")
        extracted = {
            "headline":        "Why The Climate Bill Falls Short",
            "source":          "Substack",
            "author":          "Jane Doe",
            "date":            "2025-07-14",
            "lede":            "The bill is insufficient.",
            "argument_stance": "More aggressive policy is needed.",
            "key_claims":      ["Cap is too low.", "Enforcement is weak."],
            "key_quotes":      [],
            "context":         "Background on prior bills.",
        }
        body = build_vault_note(t, extracted)
        self.assertIn("- opinion", body)
        self.assertIn("**Author:** Jane Doe", body)
        self.assertIn("## Argument Stance", body)
        self.assertIn("## Key Claims", body)
        self.assertIn("## User's Reaction", body)
        self.assertIn("I disagree with the framing here.", body)

    def test_resource_note_structure(self):
        t = self._target(kind="resource")
        extracted = {
            "title":         "Bell Inequality Experimental Tests",
            "source":        "Phys. Rev. Lett.",
            "date":          "2024-03-15",
            "topic_summary": "Survey of experimental tests of Bell's inequality.",
            "key_points":    ["Many loophole-free tests now exist.",
                              "Local realism is ruled out."],
            "citations":     ["doi:10.1103/PhysRevLett.123.456",
                              "Aspect et al. (1982)"],
        }
        body = build_vault_note(t, extracted)
        self.assertIn("- resource", body)
        self.assertIn("# Bell Inequality Experimental Tests", body)
        self.assertIn("## Topic", body)
        self.assertIn("## Key Points", body)
        self.assertIn("## Citations", body)
        self.assertIn("doi:10.1103/PhysRevLett.123.456", body)


# ---------------------------------------------------------------------------
# Vault path computation
# ---------------------------------------------------------------------------


class TestVaultPath(unittest.TestCase):

    def test_news_path_includes_year_subfolder(self):
        target = ExtractionTarget(
            file_path="/x.md", pair_num=1,
            when=datetime(2025, 7, 14),
            source_chat="x", source_platform="gemini",
            chain_id="", chain_label="",
            seg_index=0, seg_kind="news", content="x", user_voice="",
        )
        path = _vault_path_for(target, {"headline": "Climate Bill"},
                                 sources_root="/vault/Sources")
        self.assertEqual(str(path),
                         "/vault/Sources/News/2025/2025-07-14_climate-bill.md")

    def test_opinion_path(self):
        target = ExtractionTarget(
            file_path="/x.md", pair_num=1,
            when=datetime(2024, 12, 1),
            source_chat="x", source_platform="claude",
            chain_id="", chain_label="",
            seg_index=0, seg_kind="opinion", content="x", user_voice="",
        )
        path = _vault_path_for(target, {"headline": "Why X Matters"},
                                 sources_root="/v/Sources")
        self.assertEqual(str(path),
                         "/v/Sources/Opinion/2024/2024-12-01_why-x-matters.md")

    def test_resource_path_uses_title(self):
        target = ExtractionTarget(
            file_path="/x.md", pair_num=1,
            when=datetime(2026, 1, 5),
            source_chat="x", source_platform="chatgpt",
            chain_id="", chain_label="",
            seg_index=3, seg_kind="resource", content="x", user_voice="",
        )
        path = _vault_path_for(target, {"title": "Quantum Mechanics Survey"},
                                 sources_root="/v/Sources")
        self.assertEqual(str(path),
                         "/v/Sources/Resources/2026/2026-01-05_quantum-mechanics-survey.md")


# ---------------------------------------------------------------------------
# Sonnet call (mocked) — verifies JSON parsing + error path
# ---------------------------------------------------------------------------


class TestExtractSegment(unittest.TestCase):

    def _target(self, kind="news") -> ExtractionTarget:
        return ExtractionTarget(
            file_path="/x.md", pair_num=1,
            when=datetime(2025, 7, 14),
            source_chat="x", source_platform="gemini",
            chain_id="", chain_label="",
            seg_index=0, seg_kind=kind, content="article body " * 50,
            user_voice="",
        )

    def test_parses_clean_json_response(self):
        client = MagicMock()
        client.call.return_value = MagicMock(
            text='{"headline": "X", "lede": "Y"}',
            input_tokens=100, output_tokens=20, cost_usd=0.001, error="",
        )
        parsed, ti, to, cost, err = extract_segment(self._target(), client=client)
        self.assertEqual(err, "")
        self.assertEqual(parsed["headline"], "X")
        self.assertEqual(parsed["lede"], "Y")
        self.assertEqual(ti, 100)
        self.assertEqual(to, 20)

    def test_strips_markdown_fences_around_json(self):
        client = MagicMock()
        client.call.return_value = MagicMock(
            text='```json\n{"headline": "X"}\n```',
            input_tokens=100, output_tokens=20, cost_usd=0.001, error="",
        )
        parsed, _, _, _, err = extract_segment(self._target(), client=client)
        self.assertEqual(err, "")
        self.assertEqual(parsed["headline"], "X")

    def test_invalid_json_returns_error(self):
        client = MagicMock()
        client.call.return_value = MagicMock(
            text='not valid json {{{',
            input_tokens=100, output_tokens=20, cost_usd=0.001, error="",
        )
        parsed, _, _, _, err = extract_segment(self._target(), client=client)
        self.assertIsNone(parsed)
        self.assertIn("json parse", err)

    def test_api_error_propagates(self):
        client = MagicMock()
        client.call.return_value = MagicMock(
            text="", input_tokens=0, output_tokens=0, cost_usd=0.0,
            error="rate limit",
        )
        parsed, _, _, _, err = extract_segment(self._target(), client=client)
        self.assertIsNone(parsed)
        self.assertEqual(err, "rate limit")


# ---------------------------------------------------------------------------
# write_vault_note end-to-end (filesystem)
# ---------------------------------------------------------------------------


class TestWriteVaultNote(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_writes_file_in_correct_year_folder(self):
        target = ExtractionTarget(
            file_path="/x.md", pair_num=1,
            when=datetime(2025, 7, 14),
            source_chat="x", source_platform="gemini",
            chain_id="", chain_label="",
            seg_index=0, seg_kind="news",
            content="article body " * 50, user_voice="",
        )
        extracted = {"headline": "Climate Bill Passes",
                     "lede": "It happened today.",
                     "key_facts": [], "key_quotes": [], "context": ""}
        path = write_vault_note(target, extracted, sources_root=self.tmp)
        self.assertTrue(os.path.exists(path))
        self.assertIn("/News/2025/", path)
        self.assertTrue(path.endswith(".md"))
        body = open(path).read()
        self.assertIn("# Climate Bill Passes", body)

    def test_filename_collision_appends_seg_suffix(self):
        target1 = ExtractionTarget(
            file_path="/x.md", pair_num=1,
            when=datetime(2025, 7, 14),
            source_chat="x", source_platform="gemini",
            chain_id="", chain_label="",
            seg_index=0, seg_kind="news",
            content="body" * 100, user_voice="",
        )
        target2 = ExtractionTarget(
            file_path="/x.md", pair_num=1,
            when=datetime(2025, 7, 14),
            source_chat="x", source_platform="gemini",
            chain_id="", chain_label="",
            seg_index=5, seg_kind="news",
            content="body" * 100, user_voice="",
        )
        extracted = {"headline": "Same Title", "lede": "...",
                     "key_facts": [], "key_quotes": [], "context": ""}
        p1 = write_vault_note(target1, extracted, sources_root=self.tmp)
        p2 = write_vault_note(target2, extracted, sources_root=self.tmp)
        self.assertNotEqual(p1, p2)
        self.assertIn("seg05", p2)


if __name__ == "__main__":
    unittest.main()
