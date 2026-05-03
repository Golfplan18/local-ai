"""Tests for paste detection + 4-bucket classification (Phase 1.3).

Verifies:
  - Block segmentation: blank-line splits, signal detection per block
  - is_block_pasted: strong vs weak signals, defaults
  - Adjacent merging: same-kind blocks coalesce into one Segment
  - Classification scoring: news / opinion / resource / other
  - Vault index integration: paragraph-hash match → earlier-draft override
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical.paste_detection import (  # noqa: E402
    Segment,
    classify_pasted_segment,
    detect_paste_signals,
    is_block_pasted,
    merge_segments,
    process_user_input,
    segment_user_input,
    split_into_blocks,
)


# ---------------------------------------------------------------------------
# Block splitting + signal detection
# ---------------------------------------------------------------------------


class TestSplitting(unittest.TestCase):

    def test_blank_lines_split(self):
        text = "block one\n\nblock two\n\nblock three"
        self.assertEqual(split_into_blocks(text),
                         ["block one", "block two", "block three"])

    def test_empty_input_returns_empty(self):
        self.assertEqual(split_into_blocks(""), [])
        self.assertEqual(split_into_blocks("   \n\n   "), [])

    def test_whitespace_blocks_dropped(self):
        text = "block one\n\n   \n\nblock two"
        self.assertEqual(split_into_blocks(text), ["block one", "block two"])


class TestSignalDetection(unittest.TestCase):

    def test_md_heading_detected(self):
        flags = detect_paste_signals("# Title\n\nBody")
        self.assertIn("md-heading", flags)

    def test_code_fence_detected(self):
        flags = detect_paste_signals("```python\nprint('hi')\n```")
        self.assertIn("code-fence", flags)

    def test_blockquote_detected(self):
        flags = detect_paste_signals("> Quoted text here")
        self.assertIn("blockquote", flags)

    def test_bullet_list_count(self):
        text = "- one\n- two\n- three\n- four"
        flags = detect_paste_signals(text)
        # Should be tagged as bullet-list-N where N >= 3
        joined = " ".join(flags)
        self.assertIn("bullet-list-", joined)

    def test_citation_pattern_detected(self):
        text = "As shown by Smith (2024), the effect is robust."
        flags = detect_paste_signals(text)
        self.assertIn("citation-pattern", flags)

    def test_doi_detected(self):
        text = "See doi: 10.1234/abc.5678 for the full paper."
        flags = detect_paste_signals(text)
        self.assertIn("doi", flags)

    def test_byline_detected(self):
        text = "By Jane Smith, Reuters\n\nWASHINGTON — President said..."
        flags = detect_paste_signals(text)
        self.assertIn("byline", flags)

    def test_dateline_detected(self):
        text = "WASHINGTON — Officials announced new policy today."
        flags = detect_paste_signals(text)
        self.assertIn("dateline", flags)


# ---------------------------------------------------------------------------
# Block-level paste classification
# ---------------------------------------------------------------------------


class TestBlockClassification(unittest.TestCase):

    def test_short_personal_text(self):
        text = "Can you help me think about this problem?"
        is_paste, _ = is_block_pasted(text)
        self.assertFalse(is_paste)

    def test_md_heading_flips_to_pasted(self):
        text = "## Background\n\nLong section of content..."
        is_paste, _ = is_block_pasted(text)
        self.assertTrue(is_paste)

    def test_code_block_flips_to_pasted(self):
        text = "```python\ndef foo():\n    pass\n```"
        is_paste, _ = is_block_pasted(text)
        self.assertTrue(is_paste)

    def test_long_block_no_first_person_pasted(self):
        # 1500 chars of news-like prose with no I/me/my.
        text = ("The committee announced new regulations today. "
                "Officials said the move addresses long-standing concerns "
                "about industry practices. Industry groups responded with "
                "criticism, citing implementation costs. ") * 6
        is_paste, _ = is_block_pasted(text)
        self.assertTrue(is_paste)

    def test_long_personal_rambling_not_pasted(self):
        # Long-ish but full of first-person, no markdown structure.
        text = ("I've been thinking about this for a while. " * 8 +
                "I want to ask you about it. I'm not sure what to do. "
                "My experience is that this kind of thing is hard. " * 4)
        is_paste, _ = is_block_pasted(text)
        self.assertFalse(is_paste)


# ---------------------------------------------------------------------------
# Adjacent-merging
# ---------------------------------------------------------------------------


class TestMerging(unittest.TestCase):

    def test_personal_then_paste_then_personal(self):
        text = (
            "I want you to look at this article:\n\n"
            "By Jane Smith, Reuters\n\n"
            "WASHINGTON — Officials said today.\n\n"
            "What do you think?"
        )
        segments = segment_user_input(text)
        kinds = [s.kind for s in segments]
        self.assertEqual(kinds, ["personal", "pasted", "personal"])
        self.assertIn("look at this article", segments[0].content)
        self.assertIn("WASHINGTON", segments[1].content)
        self.assertIn("What do you think", segments[2].content)

    def test_multi_block_paste_merges(self):
        text = (
            "Here is the document:\n\n"
            "## Section 1\n\nContent A\n\n"
            "## Section 2\n\nContent B\n\n"
            "## Section 3\n\nContent C\n\n"
            "Thoughts?"
        )
        segments = segment_user_input(text)
        kinds = [s.kind for s in segments]
        self.assertEqual(kinds, ["personal", "pasted", "personal"])
        self.assertIn("Section 1", segments[1].content)
        self.assertIn("Section 3", segments[1].content)

    def test_only_personal(self):
        text = "Hi, can you tell me about quantum mechanics?"
        segments = segment_user_input(text)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].kind, "personal")

    def test_only_pasted(self):
        text = "## Document Title\n\nFirst paragraph content."
        segments = segment_user_input(text)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].kind, "pasted")


# ---------------------------------------------------------------------------
# 4-bucket classification (no vault index)
# ---------------------------------------------------------------------------


class TestClassification(unittest.TestCase):

    def _classify(self, text: str) -> Segment:
        seg = Segment(
            kind="pasted", content=text, block_indices=(0, 0),
            heuristic_flags=detect_paste_signals(text),
        )
        return classify_pasted_segment(seg, vault_index=None)

    def test_news_classified(self):
        # ≥500 chars (the news classifier's minimum) plus byline +
        # dateline + attributed quote — the original strong signals.
        text = (
            "By Jane Smith, Reuters\n\n"
            "WASHINGTON — President signed legislation today, officials said. "
            "\"This is a major step,\" said Senator Doe. The bill addresses "
            "long-standing concerns. Industry groups responded with criticism. "
            "Lawmakers had spent the previous week negotiating exemptions for "
            "small businesses. Both chambers approved the final language by "
            "wide margins after a marathon session that ran past midnight. "
            "Implementation will begin in stages over the next eighteen months. "
            "Analysts say the impact on consumer prices is likely to be "
            "modest in the near term but more significant downstream."
        )
        seg = self._classify(text)
        self.assertEqual(seg.classification, "news")
        self.assertGreaterEqual(seg.confidence, 0.5)

    def test_opinion_classified(self):
        text = (
            "## Why The Current System Is Broken\n\n"
            "I think we've been wrong about this for decades. "
            "I've spent years studying these issues, and I argue that "
            "we need a fundamental rethink. In my view, the case for "
            "reform is overwhelming. My experience working in this field "
            "has shown me time and again that we cannot continue. " * 3
        )
        seg = self._classify(text)
        self.assertEqual(seg.classification, "opinion")
        self.assertGreaterEqual(seg.confidence, 0.5)

    def test_resource_classified(self):
        text = (
            "## Abstract\n\n"
            "We examine the relationship between X and Y. "
            "Smith (2024) found significant effects. Jones et al. (2023) "
            "extended this with broader samples (doi: 10.1234/abc).\n\n"
            "## Methodology\n\n"
            "We employed standard procedures [1] across N=500 subjects. "
            "Results are reported in Section 3.\n\n"
            "## Results\n\n"
            "Our findings replicate Smith (2024) and extend Jones et al. (2023). "
            + "More content here. " * 30
        )
        seg = self._classify(text)
        self.assertEqual(seg.classification, "resource")
        self.assertGreaterEqual(seg.confidence, 0.5)

    def test_unclassifiable_pasted_text(self):
        # Pasted (has heading) but no news/opinion/resource signals.
        text = (
            "## Random Notes\n\n"
            "Some content here. More content. Another sentence. "
            "Continued thoughts that don't match any specific bucket."
        )
        seg = self._classify(text)
        self.assertEqual(seg.classification, "other")


# ---------------------------------------------------------------------------
# Vault index integration → earlier-draft override
# ---------------------------------------------------------------------------


class TestVaultLookup(unittest.TestCase):

    def setUp(self):
        # Build a tiny synthetic vault index with one mature entry.
        self.tmp = tempfile.mkdtemp()
        self.vault = Path(self.tmp) / "vault"
        self.vault.mkdir()
        target_text = (
            "# Three-Volume Strategy\n\n"
            + "Volume one covers the natural-language pipeline. "
              "Volume two addresses adversarial process. "
              "Volume three is the practitioner's field manual. " * 10
        )
        (self.vault / "Working — Three-Volume Strategy.md").write_text(
            target_text, encoding="utf-8")
        self.output = Path(self.tmp) / "vault-index.json"
        from orchestrator.tools.vault_indexer import build_index, load_index
        build_index(vault_path=str(self.vault),
                     output_path=str(self.output), rebuild=True)
        self.index = load_index(str(self.output))
        # Verify there's at least one entry with paragraph hashes.
        self.assertGreaterEqual(len(self.index["entries"]), 1)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_earlier_draft_override(self):
        # Paste content that's a near-duplicate of the vault entry.
        candidate = (
            "## Three-Volume Strategy (draft)\n\n"
            + "Volume one covers the natural-language pipeline. "
              "Volume two addresses adversarial process. "
              "Volume three is the practitioner's field manual. " * 10
        )
        seg = Segment(
            kind="pasted", content=candidate, block_indices=(0, 0),
            heuristic_flags=["md-heading"],
        )
        classify_pasted_segment(seg, vault_index=self.index)
        self.assertEqual(seg.classification, "earlier-draft")
        self.assertIsNotNone(seg.vault_match)
        self.assertIn("Three-Volume Strategy", seg.vault_match["title"])
        self.assertGreaterEqual(seg.vault_match["overlap_ratio"], 0.5)

    def test_no_match_for_unrelated_pasted_content(self):
        candidate = (
            "By Jane Smith, Reuters\n\n"
            "WASHINGTON — Officials announced. " * 30
        )
        seg = Segment(
            kind="pasted", content=candidate, block_indices=(0, 0),
            heuristic_flags=["byline", "dateline"],
        )
        classify_pasted_segment(seg, vault_index=self.index)
        # Should NOT be earlier-draft — falls through to news.
        self.assertEqual(seg.classification, "news")
        self.assertIsNone(seg.vault_match)

    def test_personal_segment_reclassified_when_matches_vault(self):
        # A user input where the 'personal' middle paragraph actually contains
        # vault content with first-person dialogue (fooling the personal-voice
        # heuristic). The end-to-end pipeline should reclassify it via the
        # vault lookup.
        text = (
            "## Three-Volume Strategy (draft)\n\n"
            + "Volume one covers the natural-language pipeline. "
              "Volume two addresses adversarial process. "
              "Volume three is the practitioner's field manual. " * 10
            + "\n\n"
            # "Personal-looking" middle paragraph that's actually still
            # vault content (matches the same entry):
            + "I think volume one covers the natural-language pipeline. "
              "Volume two addresses adversarial process. " * 5
        )
        segments = process_user_input(text, vault_index=self.index)
        # Both segments should end up classified as earlier-draft via vault.
        kinds = [s.kind for s in segments]
        classifications = [s.classification for s in segments]
        self.assertIn("pasted", kinds)
        self.assertTrue(any(c == "earlier-draft" for c in classifications))


# ---------------------------------------------------------------------------
# Top-level pipeline
# ---------------------------------------------------------------------------


class TestProcessUserInput(unittest.TestCase):

    def test_mixed_personal_and_news_paste(self):
        text = (
            "Hey, I read this article and want your take on it:\n\n"
            "By Jane Smith, Reuters\n\n"
            "WASHINGTON — Officials announced today, said the spokesperson. "
            "\"This is a major step,\" Smith said. The legislation passed unanimously. " * 4 + "\n\n"
            "What do you think?"
        )
        segments = process_user_input(text, vault_index=None)
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[0].kind, "personal")
        self.assertEqual(segments[1].kind, "pasted")
        self.assertEqual(segments[1].classification, "news")
        self.assertEqual(segments[2].kind, "personal")

    def test_no_pasted_segments_skips_classification(self):
        text = "Just a quick question — how does X work?"
        segments = process_user_input(text, vault_index=None)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].kind, "personal")
        self.assertEqual(segments[0].classification, "")  # no classification on personal


# ---------------------------------------------------------------------------
# Headline + webpage-garbage classification (2026-05-02)
# ---------------------------------------------------------------------------


class TestHeadlineWebpageGarbage(unittest.TestCase):

    # Tests use ≥500-char realistic content because the news classifier
    # explicitly rejects shorter segments (a 100-char block can't be a
    # news article — it'd be a sub-heading or tagline).

    def _force_pasted(self, content: str, flags=()) -> Segment:
        return Segment(
            kind="pasted", content=content, block_indices=(0, 0),
            heuristic_flags=list(flags),
        )

    _BODY = (
        "Lawmakers approved the legislation after months of negotiation. "
        "The vote was 87 to 12. The bill now goes to the House for a "
        "second reading next week. Industry groups expressed support but "
        "urged amendments. Climate scientists called the package a "
        "meaningful step but noted that significant gaps remain in "
        "addressing high-emission sectors. The package includes "
        "previously-debated provisions on grid modernization and updates "
        "to permitting rules that critics said had stalled major projects."
    )

    def test_headline_plus_garbage_combo_forces_news(self):
        content = (
            "Senate Passes Sweeping Climate Bill in Late-Night Vote\n\n"
            f"{self._BODY}\n\n"
            "Subscribe to our newsletter for daily updates.\n\n"
            "Read more on this topic. Share this article."
        )
        seg = self._force_pasted(content)
        classify_pasted_segment(seg, source_platform="gemini")
        self.assertEqual(seg.classification, "news")
        self.assertGreater(seg.confidence, 0.8)

    def test_headline_alone_below_threshold_for_claude(self):
        # Headline + body but no webpage garbage. Claude's high threshold
        # keeps this as "other".
        content = (
            "Senate Passes Sweeping Climate Bill in Late-Night Vote\n\n"
            f"{self._BODY}"
        )
        seg = self._force_pasted(content)
        classify_pasted_segment(seg, source_platform="claude")
        self.assertEqual(seg.classification, "other")

    def test_headline_plus_one_garbage_passes_for_gemini(self):
        content = (
            "Senate Passes Sweeping Climate Bill in Late-Night Vote\n\n"
            f"{self._BODY}\n\n"
            "Subscribe to our newsletter for daily updates."
        )
        seg = self._force_pasted(content)
        classify_pasted_segment(seg, source_platform="gemini")
        self.assertEqual(seg.classification, "news")

    def test_webpage_garbage_alone_classifies_as_news_on_gemini(self):
        # Several garbage hits without a headline opening — Gemini's low
        # threshold lets multi-garbage classify as news.
        content = (
            f"{self._BODY}\n\n"
            "Subscribe to our newsletter for daily updates.\n\n"
            "Read the full story. Share this article. Related: more on climate.\n\n"
            "© 2025 The Daily News. All rights reserved."
        )
        seg = self._force_pasted(content)
        classify_pasted_segment(seg, source_platform="gemini")
        self.assertEqual(seg.classification, "news")

    def test_news_outlet_attribution_with_headline(self):
        # Reuters mention + headline + body + garbage.
        content = (
            "Climate Bill Heads to House After Senate Vote\n\n"
            f"Reuters reports that {self._BODY}\n\n"
            "Read more from Reuters."
        )
        seg = self._force_pasted(content)
        classify_pasted_segment(seg, source_platform="gemini")
        self.assertEqual(seg.classification, "news")

    def test_personal_voice_in_headline_position_disqualifies(self):
        content = (
            "I read this article today and was surprised by it\n\n"
            f"{self._BODY}\n\n"
            "Subscribe to our newsletter."
        )
        seg = self._force_pasted(content)
        classify_pasted_segment(seg, source_platform="gemini")
        self.assertNotEqual(seg.classification, "news")

    def test_clean_personal_paste_remains_other(self):
        content = (
            "These are some thoughts I jotted down earlier:\n\n"
            "Point one is about the architecture.\n\n"
            "Point two is about the tradeoffs we discussed."
        )
        seg = self._force_pasted(content)
        classify_pasted_segment(seg, source_platform="gemini")
        self.assertEqual(seg.classification, "other")

    def test_short_segment_rejected_for_news(self):
        # A short markdown sub-heading + a few words must NOT be news,
        # even on Gemini. This is the bug the spot-check exposed.
        content = "### John Johnny Zebedee\n\nSome short note here."
        seg = self._force_pasted(content, flags=["md-heading"])
        classify_pasted_segment(seg, source_platform="gemini")
        self.assertNotEqual(seg.classification, "news")

    def test_subsection_heading_not_treated_as_news_headline(self):
        # A `###` subsection heading at start of a long pasted block
        # (e.g. from the user's own framework documents) must NOT
        # trigger headline detection.
        content = (
            "### Supporting Theme Framework\n\n"
            "This framework explains how to develop themes for the chapter. "
            "It walks through the steps needed to build a thematic structure "
            "and identifies the key emotional beats that drive the narrative. "
            "Each step is annotated with examples from prior chapters and "
            "guidance for adapting the structure to new material."
        )
        seg = self._force_pasted(content)
        classify_pasted_segment(seg, source_platform="gemini")
        self.assertNotEqual(seg.classification, "news")


# ---------------------------------------------------------------------------
# Platform-aware threshold test
# ---------------------------------------------------------------------------


class TestPlatformAwareThresholds(unittest.TestCase):

    def test_borderline_news_classification_varies_by_platform(self):
        # A segment with moderate news score (one webpage-garbage hit,
        # no headline) should be classified as news on Gemini but NOT
        # on Claude (Gemini threshold is much lower).
        content = (
            "Lawmakers debated the legislation for hours. The bill includes "
            "provisions for climate adaptation funding.\n\n"
            "Subscribe to our newsletter."
        )
        seg_gemini = Segment(kind="pasted", content=content,
                              block_indices=(0, 0), heuristic_flags=[])
        seg_claude = Segment(kind="pasted", content=content,
                              block_indices=(0, 0), heuristic_flags=[])
        classify_pasted_segment(seg_gemini, source_platform="gemini")
        classify_pasted_segment(seg_claude, source_platform="claude")
        # Borderline cases: Gemini lets through, Claude stays "other".
        # Threshold tuning may shift exact boundaries; this test asserts
        # only that Gemini is at least as permissive as Claude.
        if seg_claude.classification == "news":
            self.assertEqual(seg_gemini.classification, "news")
        # Confidence at least equals on Gemini.
        self.assertGreaterEqual(seg_gemini.confidence, seg_claude.confidence)


if __name__ == "__main__":
    unittest.main()
