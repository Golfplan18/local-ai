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
from unittest.mock import MagicMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical.phase3_extraction import (  # noqa: E402
    EXTRACTION_MODEL,
    ExtractionTarget,
    _slugify,
    _vault_path_for,
    build_vault_note,
    extract_segment,
    extraction_self_reports_failure,
    fiction_guard_reason,
    find_extraction_targets,
    index_notes_into_knowledge,
    run_phase3,
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
    """Flat Resources/ layout (Schema rev 5): no kind subfolders, no
    year subfolders — kind lives in YAML tags."""

    def test_news_path_is_flat(self):
        target = ExtractionTarget(
            file_path="/x.md", pair_num=1,
            when=datetime(2025, 7, 14),
            source_chat="x", source_platform="gemini",
            chain_id="", chain_label="",
            seg_index=0, seg_kind="news", content="x", user_voice="",
        )
        path = _vault_path_for(target, {"headline": "Climate Bill"},
                                 resources_root="/vault/Resources")
        self.assertEqual(str(path),
                         "/vault/Resources/2025-07-14_climate-bill.md")

    def test_opinion_path_is_flat(self):
        target = ExtractionTarget(
            file_path="/x.md", pair_num=1,
            when=datetime(2024, 12, 1),
            source_chat="x", source_platform="claude",
            chain_id="", chain_label="",
            seg_index=0, seg_kind="opinion", content="x", user_voice="",
        )
        path = _vault_path_for(target, {"headline": "Why X Matters"},
                                 resources_root="/v/Resources")
        self.assertEqual(str(path),
                         "/v/Resources/2024-12-01_why-x-matters.md")

    def test_resource_path_uses_title(self):
        target = ExtractionTarget(
            file_path="/x.md", pair_num=1,
            when=datetime(2026, 1, 5),
            source_chat="x", source_platform="chatgpt",
            chain_id="", chain_label="",
            seg_index=3, seg_kind="resource", content="x", user_voice="",
        )
        path = _vault_path_for(target, {"title": "Quantum Mechanics Survey"},
                                 resources_root="/v/Resources")
        self.assertEqual(str(path),
                         "/v/Resources/2026-01-05_quantum-mechanics-survey.md")

    def test_no_kind_or_year_segments_ever(self):
        for kind in ("news", "opinion", "resource"):
            target = ExtractionTarget(
                file_path="/x.md", pair_num=1,
                when=datetime(2025, 7, 14),
                source_chat="x", source_platform="gemini",
                chain_id="", chain_label="",
                seg_index=0, seg_kind=kind, content="x", user_voice="",
            )
            path = _vault_path_for(target, {"headline": "T", "title": "T"},
                                     resources_root="/v/Resources")
            self.assertEqual(path.parent, Path("/v/Resources"))


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

    def test_writes_file_flat_in_resources_root(self):
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
        path = write_vault_note(target, extracted, resources_root=self.tmp)
        self.assertTrue(os.path.exists(path))
        # Flat: written directly into the root, no kind/year subfolders.
        self.assertEqual(os.path.dirname(path), self.tmp)
        self.assertTrue(path.endswith("2025-07-14_climate-bill-passes.md"))
        body = Path(path).read_text(encoding="utf-8")
        self.assertIn("# Climate Bill Passes", body)
        self.assertIn("- news", body)  # kind encoded in tags

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
        p1 = write_vault_note(target1, extracted, resources_root=self.tmp)
        p2 = write_vault_note(target2, extracted, resources_root=self.tmp)
        self.assertNotEqual(p1, p2)
        self.assertIn("seg05", p2)


# ---------------------------------------------------------------------------
# Own-fiction guard (fail-open)
# ---------------------------------------------------------------------------


class TestFictionGuard(unittest.TestCase):

    def test_large_dialogue_heavy_paste_is_skipped(self):
        # Manuscript-style: most lines carry dialogue quotes.
        content = ('"Where are we going?" Thomas asked.\n'
                   'Sarah looked away. "You know where."\n'
                   "The rain kept falling on the empty street.\n") * 800
        self.assertGreater(len(content), 20_000)
        reason = fiction_guard_reason(content)
        self.assertIn("own fiction", reason)
        self.assertIn("dialogue", reason)

    def test_large_chaptered_manuscript_is_skipped(self):
        prose = "The morning light crept over the hills. " * 300
        content = f"Chapter 1\n\n{prose}\n\nChapter 2\n\n{prose}\n\nChapter 3\n\n{prose}"
        self.assertGreater(len(content), 20_000)
        reason = fiction_guard_reason(content)
        self.assertIn("own fiction", reason)
        self.assertIn("chapter", reason.lower())

    def test_small_dialogue_heavy_paste_passes(self):
        # Below the size floor the guard never engages — a short news
        # article full of quotes must still extract.
        content = ('"This is a major step," Sen. Doe said.\n'
                   "The bill passed 87-12 late Thursday.\n") * 20
        self.assertLess(len(content), 20_000)
        self.assertEqual(fiction_guard_reason(content), "")

    def test_large_technical_document_passes(self):
        # A long research paper: low dialogue density, no chapters.
        content = ("The methodology follows a standard regression design. "
                   "Results indicate a significant effect (p < 0.01). ") * 400
        self.assertGreater(len(content), 20_000)
        self.assertEqual(fiction_guard_reason(content), "")

    def test_guard_fails_open_on_bad_input(self):
        # None would raise inside the guard — it must swallow and pass.
        self.assertEqual(fiction_guard_reason(None), "")


class TestSelfReportGuard(unittest.TestCase):

    def test_unable_to_determine_headline_is_skipped(self):
        extracted = {"headline": "Unable to determine — text appears to be "
                                 "navigation/footer content from CNN website"}
        reason = extraction_self_reports_failure(extracted)
        self.assertIn("self-reported failure", reason)

    def test_unable_to_determine_title_is_skipped(self):
        extracted = {"title": "Unable to determine document type"}
        self.assertNotEqual(extraction_self_reports_failure(extracted), "")

    def test_normal_headline_passes(self):
        extracted = {"headline": "Senate Passes Climate Bill 87-12"}
        self.assertEqual(extraction_self_reports_failure(extracted), "")

    def test_guard_fails_open_on_bad_input(self):
        self.assertEqual(extraction_self_reports_failure(None), "")


# ---------------------------------------------------------------------------
# Knowledge indexing (mocked collection; fail-open)
# ---------------------------------------------------------------------------


class TestIndexNotesIntoKnowledge(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.note = os.path.join(self.tmp, "2025-07-14_test-note.md")
        Path(self.note).write_text(
            "---\ntype: resource\ntags:\n  - news\n---\n\n# Test Note\n\n"
            "Body long enough to index. " * 10,
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_indexes_written_notes(self):
        from unittest.mock import patch
        fake_collection = MagicMock()
        fake_collection.get.return_value = {"ids": []}  # not yet indexed
        with patch("orchestrator.tools.knowledge_index."
                   "get_knowledge_collection",
                   return_value=fake_collection), \
             patch("orchestrator.tools.knowledge_index._nomic_embed",
                   return_value=[0.0] * 8):
            stats = index_notes_into_knowledge([self.note],
                                               progress_to_stderr=False)
        self.assertEqual(stats["indexed"], 1)
        fake_collection.add.assert_called_once()
        # type: resource must reach ChromaDB metadata (0.8 provenance
        # weight keys off it at query time).
        meta = fake_collection.add.call_args[1]["metadatas"][0]
        self.assertEqual(meta["type"], "resource")

    def test_empty_path_list_is_noop(self):
        stats = index_notes_into_knowledge([], progress_to_stderr=False)
        self.assertEqual(stats["indexed"], 0)
        self.assertEqual(stats["errors"], 0)

    def test_fails_open_when_collection_unavailable(self):
        from unittest.mock import patch
        with patch("orchestrator.tools.knowledge_index."
                   "get_knowledge_collection",
                   side_effect=RuntimeError("chromadb down")):
            stats = index_notes_into_knowledge([self.note],
                                               progress_to_stderr=False)
        # No exception escapes; failure is recorded loudly in stats.
        self.assertGreaterEqual(stats["errors"], 1)
        self.assertIn("chromadb down", stats.get("fatal", ""))


# ---------------------------------------------------------------------------
# Backend selection — mirrors phase5_atomic_extraction.run_phase5's pattern
# ---------------------------------------------------------------------------


class TestRunPhase3Backend(unittest.TestCase):
    """run_phase3 must route model calls through the selected backend
    instead of always using the metered-API AnthropicClient."""

    def setUp(self):
        self.archive = tempfile.mkdtemp()
        self.resources = tempfile.mkdtemp()
        self.manifest_dir = tempfile.mkdtemp()
        # run_phase3's file loop needs at least one archive file to walk.
        Path(self.archive, "2025-07-14_test.md").write_text(
            "placeholder", encoding="utf-8")

    def tearDown(self):
        for d in (self.archive, self.resources, self.manifest_dir):
            shutil.rmtree(d, ignore_errors=True)

    def _one_target(self):
        return ExtractionTarget(
            file_path=os.path.join(self.archive, "2025-07-14_test.md"),
            pair_num=1, when=datetime(2025, 7, 14),
            source_chat="x", source_platform="gemini",
            chain_id="", chain_label="",
            seg_index=0, seg_kind="news", content="body " * 100,
            user_voice="",
        )

    def _run(self, backend, mock_build_client, mock_anthropic_client):
        manifest_path = os.path.join(self.manifest_dir, "manifest.json")
        with patch("orchestrator.historical.phase3_extraction."
                   "find_extraction_targets",
                   return_value=[self._one_target()]), \
             patch("orchestrator.historical.phase3_extraction."
                   "extract_segment",
                   return_value=({"headline": "T", "lede": "L",
                                  "key_facts": [], "key_quotes": [],
                                  "context": ""}, 10, 5, 0.0, "")) as m_extract, \
             patch("orchestrator.historical.phase3_extraction."
                   "index_notes_into_knowledge",
                   return_value={"indexed": 0}), \
             patch("orchestrator.historical.phase3_extraction."
                   "load_chain_index", return_value={}), \
             patch("orchestrator.historical.phase3_extraction."
                   "AnthropicClient", mock_anthropic_client), \
             patch("orchestrator.historical.cleanup_backends.build_client",
                   mock_build_client):
            run_phase3(
                archive_dir=self.archive, resources_root=self.resources,
                manifest_path=manifest_path, progress_to_stderr=False,
                backend=backend,
            )
        return m_extract

    def test_api_backend_uses_anthropic_client_directly(self):
        mock_anthropic_client = MagicMock(return_value="anthropic-sentinel")
        mock_build_client = MagicMock(return_value="build-client-sentinel")
        m_extract = self._run("api", mock_build_client, mock_anthropic_client)
        mock_anthropic_client.assert_called_once_with(model=EXTRACTION_MODEL)
        mock_build_client.assert_not_called()
        self.assertEqual(m_extract.call_args.kwargs["client"],
                         "anthropic-sentinel")

    def test_claude_cli_backend_routes_through_build_client(self):
        mock_anthropic_client = MagicMock(return_value="anthropic-sentinel")
        mock_build_client = MagicMock(return_value="cli-client-sentinel")
        m_extract = self._run("claude-cli", mock_build_client,
                              mock_anthropic_client)
        mock_build_client.assert_called_once_with("claude-cli")
        mock_anthropic_client.assert_not_called()
        self.assertEqual(m_extract.call_args.kwargs["client"],
                         "cli-client-sentinel")

    def test_ora_slots_backend_routes_through_build_client(self):
        mock_anthropic_client = MagicMock(return_value="anthropic-sentinel")
        mock_build_client = MagicMock(return_value="slot-client-sentinel")
        m_extract = self._run("ora-slots", mock_build_client,
                              mock_anthropic_client)
        mock_build_client.assert_called_once_with("ora-slots")
        mock_anthropic_client.assert_not_called()
        self.assertEqual(m_extract.call_args.kwargs["client"],
                         "slot-client-sentinel")


if __name__ == "__main__":
    unittest.main()
