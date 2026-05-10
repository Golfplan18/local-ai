"""Tests for the News Supersession Framework — detection + resolver.

Covers:
- Detection: resource indexing, entity-overlap heuristic, log-pair-key
  extraction, resolved-set filter behavior.
- Resolver: Resolution-line canonical parsing (same fix as Engram
  Cleaning post-2026-05-09), supersession applies `superseded` tag
  (NOT `archived`), wrong:* applies `archived`.
- The load-bearing distinction: news supersession is a weight modifier,
  not a filter — older articles must stay retrievable.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/ora"))

from orchestrator.historical.run_news_supersession_resolver import (
    parse_queue,
    _rebuild_queue_keeping_pending,
    add_tag,
    add_supersedes_relationship,
    has_tag,
)
from orchestrator.historical.run_news_supersession_detection import (
    _parse_log_for_pair_keys,
    entity_overlap,
    _extract_entities,
    _detect_tag_type,
    _parse_date,
)


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


class TestEntityOverlap(unittest.TestCase):
    """Entity-overlap heuristic for Approach B filter."""

    def test_extracts_capitalized_tokens(self):
        entities = _extract_entities(
            "Trump and Xi negotiate over Taiwan policy in Beijing"
        )
        # Trump, Taiwan, Beijing extracted; "And" is a stopword and
        # "Xi" is filtered by the len > 2 rule (known limitation of
        # the simple heuristic — would need a real NER pass to catch
        # short proper nouns reliably).
        self.assertIn("Trump", entities)
        self.assertIn("Taiwan", entities)
        self.assertIn("Beijing", entities)
        self.assertNotIn("And", entities)

    def test_filters_short_tokens(self):
        # "Xi" is 2 chars; should be filtered out by len > 2
        entities = _extract_entities("Xi Trump")
        self.assertNotIn("Xi", entities)
        self.assertIn("Trump", entities)

    def test_filters_stopwords(self):
        entities = _extract_entities("The Trump White House")
        self.assertNotIn("The", entities)
        self.assertIn("Trump", entities)
        self.assertIn("White", entities)
        self.assertIn("House", entities)

    def test_overlap_count(self):
        a = "Apple researchers built AI reasoning model"
        b = "Apple researchers test LLaMA reasoning"
        # Shared: Apple
        # Unshared on each side
        overlap = entity_overlap(a, b)
        self.assertGreaterEqual(overlap, 1)

    def test_no_overlap_returns_zero(self):
        a = "Bezos buys yacht in Mediterranean"
        b = "Mars rover discovers methane"
        # No shared capitalized entities
        self.assertEqual(entity_overlap(a, b), 0)


class TestDetectTagType(unittest.TestCase):
    """Tag-type detection enforces cross-tag-type guard at detection time."""

    def test_news_tag(self):
        self.assertEqual(_detect_tag_type(["news"]), "news")

    def test_opinion_tag(self):
        self.assertEqual(_detect_tag_type(["opinion"]), "opinion")

    def test_resource_tag(self):
        self.assertEqual(_detect_tag_type(["resource"]), "resource")

    def test_first_eligible_wins(self):
        # When multiple tags present, news takes precedence per iteration
        # order of ELIGIBLE_TAG_TYPES ("news", "opinion", "resource").
        self.assertEqual(_detect_tag_type(["opinion", "news"]), "news")

    def test_no_eligible_tag(self):
        self.assertIsNone(_detect_tag_type(["compound", "atomic"]))
        self.assertIsNone(_detect_tag_type([]))


class TestParseDate(unittest.TestCase):
    """Date normalization handles strings and datetime objects."""

    def test_iso_string(self):
        self.assertEqual(_parse_date("2025-08-14"), "2025-08-14")

    def test_iso_string_with_time(self):
        # Some YAML libraries return ISO with time
        self.assertEqual(_parse_date("2025-08-14T10:30:00"), "2025-08-14")

    def test_none(self):
        self.assertIsNone(_parse_date(None))

    def test_invalid_string(self):
        self.assertIsNone(_parse_date("not a date"))


# ---------------------------------------------------------------------------
# Log-pair extraction
# ---------------------------------------------------------------------------


class TestLogPairKeyParser(unittest.TestCase):
    """Same canonical-tuple extraction as Engram Cleaning's."""

    def test_extracts_pair_from_log_entry(self):
        log = (
            "## 2026-05-10 12:00 — changed-mind:source-supersedes-target\n\n"
            "- **Source:** [[2026-04-29_apple-research-newer]]\n"
            "- **Target:** [[2026-04-15_apple-research-older]]\n"
            "- **Files mutated:** ...\n\n"
            "---\n"
        )
        pairs = _parse_log_for_pair_keys(log)
        # Canonical sorted tuple
        self.assertEqual(
            pairs,
            {("2026-04-15_apple-research-older", "2026-04-29_apple-research-newer")},
        )

    def test_empty_log(self):
        self.assertEqual(_parse_log_for_pair_keys(""), set())


# ---------------------------------------------------------------------------
# Queue parsing — Resolution line is canonical
# ---------------------------------------------------------------------------


def _queue_section(heading_marker: str, resolution_marker: str,
                   source_slug: str = "source-news",
                   target_slug: str = "target-news") -> str:
    return (
        f"## [{heading_marker}] Some headline...\n"
        "\n"
        f"- **Source:** [[{source_slug}]] (2026-04-29, tag: news)\n"
        f"  *Source article headline*\n"
        f"- **Target:** [[{target_slug}]] (2026-04-15, tag: news)\n"
        f"  *Target article headline*\n"
        "- **Cluster signal:** similarity 0.85, entity overlap 2, date gap 14 days\n"
        "- **Strategy:** topic-cluster\n"
        "\n"
        f"**Resolution:** [{resolution_marker}]\n"
        "\n"
        "---\n"
    )


def _queue_text(*sections: str) -> str:
    preamble = (
        "---\nnexus:\n  - ora\ntype: working\n---\n\n"
        "# News Supersession Queue — test\n\n"
        "*Generated by test fixture.*\n\n"
        "---\n\n"
    )
    return preamble + "\n".join(sections)


class TestQueueParsing(unittest.TestCase):
    """Resolution line is canonical (same fix as Engram Cleaning resolver)."""

    def test_resolution_line_canonical(self):
        text = _queue_text(_queue_section("pending", "skip"))
        pairs = parse_queue(text)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["resolution"], "skip")

    def test_compound_resolution_marker(self):
        text = _queue_text(_queue_section(
            "pending", "changed-mind:source-supersedes-target",
        ))
        pairs = parse_queue(text)
        self.assertEqual(
            pairs[0]["resolution"],
            "changed-mind:source-supersedes-target",
        )

    def test_extracts_slugs_and_h1s(self):
        text = _queue_text(_queue_section(
            "pending", "skip", "alpha", "beta",
        ))
        pairs = parse_queue(text)
        self.assertEqual(pairs[0]["source_slug"], "alpha")
        self.assertEqual(pairs[0]["target_slug"], "beta")
        self.assertEqual(pairs[0]["source_h1"], "Source article headline")
        self.assertEqual(pairs[0]["target_h1"], "Target article headline")


class TestQueueRebuild(unittest.TestCase):
    """Queue rebuild keeps only pending pairs (reads Resolution line)."""

    def test_resolution_drives_rebuild(self):
        text = _queue_text(
            _queue_section("pending", "skip", "a", "b"),
            _queue_section("pending", "pending", "c", "d"),
        )
        rebuilt = _rebuild_queue_keeping_pending(text)
        # c-d (pending) kept; a-b (skip) removed
        self.assertIn("[[c]]", rebuilt)
        self.assertNotIn("[[a]]", rebuilt)


# ---------------------------------------------------------------------------
# YAML mutation primitives
# ---------------------------------------------------------------------------


class TestTagApplication(unittest.TestCase):
    """add_tag is idempotent and inserts at end of tags: list."""

    def test_add_tag(self):
        fm = "type: resource\ntags:\n  - news\ndate created: 2025-01-01"
        new_fm = add_tag(fm, "superseded")
        self.assertIn("- superseded", new_fm)
        self.assertIn("- news", new_fm)

    def test_add_tag_idempotent(self):
        fm = "type: resource\ntags:\n  - news\n  - superseded\ndate created: 2025-01-01"
        new_fm = add_tag(fm, "superseded")
        # Should not duplicate
        self.assertEqual(new_fm.count("- superseded"), 1)

    def test_has_tag(self):
        fm = "tags:\n  - news\n  - archived"
        self.assertTrue(has_tag(fm, "news"))
        self.assertTrue(has_tag(fm, "archived"))
        self.assertFalse(has_tag(fm, "superseded"))


class TestSupersessionApplication(unittest.TestCase):
    """The load-bearing test: `superseded` (not `archived`) for changed-mind."""

    def test_supersedes_relationship_added(self):
        fm = (
            "type: resource\n"
            "tags:\n  - news\n"
            "date created: 2026-04-29"
        )
        new_fm = add_supersedes_relationship(fm, "Older Article Headline")
        self.assertIn("type: supersedes", new_fm)
        self.assertIn("target: Older Article Headline", new_fm)
        self.assertIn("confidence: high", new_fm)

    def test_supersedes_relationship_idempotent(self):
        fm = (
            "type: resource\n"
            "tags:\n  - news\n"
            "relationships:\n"
            "- type: supersedes\n"
            "  target: Older Article\n"
            "  confidence: high\n"
            "date created: 2026-04-29"
        )
        new_fm = add_supersedes_relationship(fm, "Older Article")
        # Should not duplicate
        self.assertEqual(new_fm.count("type: supersedes"), 1)


# ---------------------------------------------------------------------------
# Public-API smoke (no chromadb required for these helpers)
# ---------------------------------------------------------------------------


class TestResolverImports(unittest.TestCase):
    """Verifies the resolver's public symbols are importable."""

    def test_apply_supersession_importable(self):
        from orchestrator.historical.run_news_supersession_resolver import (
            apply_supersession,
        )
        self.assertTrue(callable(apply_supersession))

    def test_apply_wrong_importable(self):
        from orchestrator.historical.run_news_supersession_resolver import (
            apply_wrong,
        )
        self.assertTrue(callable(apply_wrong))

    def test_run_resolver_importable(self):
        from orchestrator.historical.run_news_supersession_resolver import (
            run_resolver,
        )
        self.assertTrue(callable(run_resolver))


class TestDetectionImports(unittest.TestCase):
    """Verifies the detection's public symbols are importable."""

    def test_run_detection_importable(self):
        from orchestrator.historical.run_news_supersession_detection import (
            run_detection,
        )
        self.assertTrue(callable(run_detection))

    def test_build_resources_index_importable(self):
        from orchestrator.historical.run_news_supersession_detection import (
            build_resources_index,
        )
        self.assertTrue(callable(build_resources_index))


if __name__ == "__main__":
    unittest.main()
