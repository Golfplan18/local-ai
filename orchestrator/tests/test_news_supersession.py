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

import contextlib
import io
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

# Derived from __file__ (same pattern as test_stealth_short_circuit_purge_2026_05_17.py)
# rather than hardcoded to ~/ora, so this resolves correctly from a worktree too.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from orchestrator.historical import run_news_supersession_detection as news_det
from orchestrator.historical import run_news_supersession_resolver as news_res
from orchestrator.historical.run_news_supersession_detection import (
    _parse_log_for_pair_keys,
    entity_overlap,
    _extract_entities,
    _detect_tag_type,
    _parse_date,
)
from orchestrator.historical.run_news_supersession_resolver import (
    parse_queue,
    _rebuild_queue_keeping_pending,
    add_tag,
    add_supersedes_relationship,
    has_tag,
)


class _FakeKnowledgeCollection:
    """Small Chroma fake that models path lookup and metadata merging."""

    def __init__(self, records=None, query_result=None, fail_update_ids=None):
        self.records = records or {}
        self.query_result = query_result or {
            "ids": [[]], "distances": [[]], "metadatas": [[]],
        }
        self.fail_update_ids = set(fail_update_ids or [])
        self.query_calls = []
        self.update_calls = []

    def get(self, ids=None, where=None, include=None):
        if where is not None:
            wanted_path = os.path.abspath(where["path"])
            selected_ids = [
                record_id
                for record_id, record in self.records.items()
                if os.path.abspath(record["metadata"]["path"]) == wanted_path
            ]
        else:
            selected_ids = [
                record_id for record_id in (ids or [])
                if record_id in self.records
            ]

        result = {"ids": selected_ids}
        if include is None or "metadatas" in include:
            result["metadatas"] = [
                dict(self.records[record_id]["metadata"])
                for record_id in selected_ids
            ]
        if include is None or "embeddings" in include:
            result["embeddings"] = [
                self.records[record_id].get("embedding")
                for record_id in selected_ids
            ]
        return result

    def query(self, query_embeddings, n_results, include=None):
        self.query_calls.append({
            "query_embeddings": query_embeddings,
            "n_results": n_results,
            "include": include,
        })
        return self.query_result

    def update(self, ids, metadatas):
        if self.fail_update_ids.intersection(ids):
            raise RuntimeError("synthetic update failure")
        self.update_calls.append((list(ids), list(metadatas)))
        for record_id, metadata in zip(ids, metadatas):
            # Real Chroma update() merges per key; retain chunk-specific keys.
            self.records[record_id]["metadata"].update(metadata)


def _resource_meta(path: str, slug: str, title: str, date_created: str) -> dict:
    return {
        "path": path,
        "slug": slug,
        "filename": f"{slug}.md",
        "h1": title,
        "tag_type": "news",
        "tags": ["news"],
        "date_created": date_created,
    }


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


class TestChunkedDetection(unittest.TestCase):
    """Detection treats physical chunk records as logical source files."""

    def test_centroid_query_maps_chunked_neighbors_by_path_and_dedupes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_path = os.path.abspath(os.path.join(tmp, "source.md"))
            neighbor_path = os.path.abspath(os.path.join(tmp, "neighbor.md"))
            # Real files make this fixture representative of build_resources_index
            # output even though detection itself only consumes the path index.
            for path in (source_path, neighbor_path):
                with open(path, "w", encoding="utf-8") as f:
                    f.write("---\ntype: resource\ntags:\n  - news\n---\n# Apple Update\n")

            source_1 = f"{source_path}#chunk-1"
            source_2 = f"{source_path}#chunk-2"
            neighbor_1 = f"{neighbor_path}#chunk-1"
            neighbor_2 = f"{neighbor_path}#chunk-2"
            collection = _FakeKnowledgeCollection(
                records={
                    source_1: {
                        "embedding": [1.0, 0.0],
                        "metadata": {"path": source_path, "chunk_index": 1},
                    },
                    source_2: {
                        "embedding": [3.0, 0.0],
                        "metadata": {"path": source_path, "chunk_index": 2},
                    },
                    neighbor_1: {
                        "embedding": [5.0, 0.0],
                        "metadata": {"path": neighbor_path, "chunk_index": 1},
                    },
                    neighbor_2: {
                        "embedding": [7.0, 0.0],
                        "metadata": {"path": neighbor_path, "chunk_index": 2},
                    },
                },
                query_result={
                    "ids": [[source_1, neighbor_1, neighbor_2]],
                    "distances": [[0.0, 0.1, 0.2]],
                    "metadatas": [[
                        {"path": source_path},
                        {"path": neighbor_path},
                        {"path": neighbor_path},
                    ]],
                },
            )
            by_path = {
                source_path: _resource_meta(
                    source_path, "source", "Apple Update Begins", "2026-01-01"
                ),
                neighbor_path: _resource_meta(
                    neighbor_path, "neighbor", "Apple Update Continues", "2026-02-01"
                ),
            }
            fake_chromadb = types.SimpleNamespace(
                PersistentClient=lambda path: object()
            )
            import orchestrator.embedding as embedding

            with mock.patch.dict(sys.modules, {"chromadb": fake_chromadb}), \
                    mock.patch.object(
                        embedding, "get_collection",
                        lambda client, name: collection,
                    ):
                candidates = news_det.detect_topic_cluster(
                    by_path, similarity_threshold=0.5, limit=10,
                )

            # The source query vector is the mean of its two chunk vectors.
            self.assertEqual(
                collection.query_calls[0]["query_embeddings"], [[2.0, 0.0]]
            )
            self.assertEqual(
                collection.query_calls[0]["include"],
                ["distances", "metadatas"],
            )
            # Both neighbor chunks map to the same logical path and therefore
            # produce one candidate, using the closest chunk's similarity.
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["older"]["slug"], "source")
            self.assertEqual(candidates[0]["newer"]["slug"], "neighbor")
            self.assertAlmostEqual(candidates[0]["similarity"], 0.9)

    def test_missing_document_embedding_is_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_path = os.path.abspath(os.path.join(tmp, "unindexed.md"))
            with open(source_path, "w", encoding="utf-8") as f:
                f.write("---\ntype: resource\ntags:\n  - news\n---\n# Apple Update\n")
            collection = _FakeKnowledgeCollection()
            by_path = {
                source_path: _resource_meta(
                    source_path, "unindexed", "Apple Update", "2026-01-01"
                )
            }
            fake_chromadb = types.SimpleNamespace(
                PersistentClient=lambda path: object()
            )
            import orchestrator.embedding as embedding
            stderr = io.StringIO()

            with mock.patch.dict(sys.modules, {"chromadb": fake_chromadb}), \
                    mock.patch.object(
                        embedding, "get_collection",
                        lambda client, name: collection,
                    ), contextlib.redirect_stderr(stderr):
                candidates = news_det.detect_topic_cluster(
                    by_path, similarity_threshold=0.5, limit=10,
                )

            self.assertEqual(candidates, [])
            self.assertEqual(collection.query_calls, [])
            self.assertIn("no chromadb embedding", stderr.getvalue())
            self.assertIn(source_path, stderr.getvalue())


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


class TestChunkedMetadataRefresh(unittest.TestCase):
    """Resolver refreshes logical files without assuming id == path."""

    @staticmethod
    def _write_resource(directory: str, slug: str):
        path = os.path.join(directory, f"{slug}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(
                "---\n"
                "nexus:\n"
                "  - ora\n"
                "type: resource\n"
                "tags:\n"
                "  - news\n"
                "---\n"
                f"# {slug}\n"
            )
        return os.path.abspath(path)

    def test_updates_all_chunks_and_reports_zero_missing_and_errors(self):
        with tempfile.TemporaryDirectory() as resources_dir:
            chunked_path = self._write_resource(resources_dir, "chunked")
            unindexed_path = self._write_resource(resources_dir, "unindexed")
            broken_path = self._write_resource(resources_dir, "broken")
            missing_path = os.path.abspath(
                os.path.join(resources_dir, "missing.md")
            )

            chunk_1 = f"{chunked_path}#chunk-1"
            chunk_2 = f"{chunked_path}#chunk-2"
            broken_id = f"{broken_path}#chunk-1"
            collection = _FakeKnowledgeCollection(
                records={
                    chunk_1: {
                        "embedding": [1.0, 0.0],
                        "metadata": {
                            "path": chunked_path,
                            "stale": True,
                            "chunk_index": 1,
                            "total_chunks": 2,
                        },
                    },
                    chunk_2: {
                        "embedding": [3.0, 0.0],
                        "metadata": {
                            "path": chunked_path,
                            "stale": True,
                            "chunk_index": 2,
                            "total_chunks": 2,
                        },
                    },
                    broken_id: {
                        "embedding": [9.0, 0.0],
                        "metadata": {"path": broken_path, "chunk_index": 1},
                    },
                },
                fail_update_ids={broken_id},
            )
            fake_chromadb = types.SimpleNamespace(
                PersistentClient=lambda path: object()
            )
            import orchestrator.embedding as embedding
            stdout = io.StringIO()
            stderr = io.StringIO()

            with mock.patch.object(news_res, "RESOURCES_DIR", resources_dir), \
                    mock.patch.dict(sys.modules, {"chromadb": fake_chromadb}), \
                    mock.patch.object(
                        embedding, "get_or_create_collection",
                        lambda client, name: collection,
                    ), contextlib.redirect_stdout(stdout), \
                    contextlib.redirect_stderr(stderr):
                summary = news_res.refresh_chromadb({
                    "chunked", "unindexed", "missing", "broken",
                })

            self.assertEqual(summary["updated_records"], 2)
            self.assertEqual(summary["updated_files"], 1)
            self.assertEqual(summary["never_indexed_files"], 1)
            self.assertEqual(summary["missing_source_files"], 1)
            self.assertEqual(summary["never_indexed_slugs"], ["unindexed"])
            self.assertEqual(summary["missing_source_slugs"], ["missing"])
            self.assertEqual(summary["errors"], 1)
            self.assertEqual(len(summary["error_messages"]), 1)
            self.assertIn(
                "synthetic update failure", summary["error_messages"][0]
            )
            self.assertNotIn("broken", summary["never_indexed_slugs"])

            updated_ids = {
                record_id
                for ids, _metadatas in collection.update_calls
                for record_id in ids
            }
            self.assertEqual(updated_ids, {chunk_1, chunk_2})
            for record_id, expected_chunk in ((chunk_1, 1), (chunk_2, 2)):
                metadata = collection.records[record_id]["metadata"]
                self.assertEqual(metadata["path"], chunked_path)
                self.assertEqual(metadata["tags"], ["news"])
                # The update payload omits HCP-stamped keys; merge semantics
                # preserve each physical record's distinct chunk identity.
                self.assertEqual(metadata["chunk_index"], expected_chunk)
                self.assertEqual(metadata["total_chunks"], 2)

            report = stdout.getvalue()
            self.assertIn(
                "Refreshed ChromaDB metadata for 2 records across 1 source files",
                report,
            )
            self.assertIn(
                "Existing source files with no ChromaDB records: 1 (unindexed)",
                report,
            )
            self.assertIn("Missing source files: 1 (missing)", report)
            self.assertIn("ChromaDB metadata errors: 1", stderr.getvalue())
            self.assertFalse(os.path.exists(missing_path))
            self.assertTrue(os.path.exists(unindexed_path))


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
