"""Tests for Engram Cleaning resolver parsing, log filtering, and metadata refresh.

Regression coverage includes:
- Resolver was reading the resolution marker from the heading line instead of
  the canonical `**Resolution:** [marker]` line.
- Detection wasn't filtering previously-resolved pairs from the log, causing
  the same pairs to resurface every run.
- Metadata refresh assumed a source path was also its Chroma record id, so it
  skipped HCP chunk records and overstated its update count.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import types
import unittest
import unittest.mock as mock

# Make `orchestrator.historical.*` importable when run from the repo root.
# Derived from __file__ (same pattern as test_stealth_short_circuit_purge_2026_05_17.py)
# rather than hardcoded to ~/ora, so this resolves correctly from a worktree too.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from orchestrator.historical.run_engram_cleaning_resolver import (
    parse_queue,
    _rebuild_queue_keeping_pending,
)
from orchestrator.historical.run_engram_cleaning_detection import (
    _parse_log_for_pair_keys,
    detect_bidirectional,
)
from orchestrator.historical import phase3_chromadb_refresh
from orchestrator.historical import run_engram_cleaning_resolver


class _FakeMetadataCollection:
    """Small Chroma stand-in with metadata filtering and merge updates."""

    def __init__(self, records: dict[str, dict] | None = None,
                 fail_update_ids: set[str] | None = None):
        self.records = records or {}
        self.fail_update_ids = fail_update_ids or set()
        self.get_calls: list[dict] = []

    def count(self):
        return len(self.records)

    def get(self, ids=None, where=None, include=None):
        self.get_calls.append({"ids": ids, "where": where, "include": include})
        selected_ids = list(self.records)
        if ids is not None:
            wanted = set(ids)
            selected_ids = [record_id for record_id in selected_ids
                            if record_id in wanted]
        if where is not None:
            selected_ids = [
                record_id for record_id in selected_ids
                if all(self.records[record_id]["metadata"].get(key) == value
                       for key, value in where.items())
            ]
        return {
            "ids": selected_ids,
            "metadatas": [self.records[record_id]["metadata"]
                          for record_id in selected_ids],
            "embeddings": [self.records[record_id].get("embedding")
                           for record_id in selected_ids],
        }

    def update(self, ids, metadatas):
        if any(record_id in self.fail_update_ids for record_id in ids):
            raise RuntimeError("synthetic update failure")
        for record_id, metadata in zip(ids, metadatas):
            if record_id in self.records:
                self.records[record_id]["metadata"].update(metadata)


@contextlib.contextmanager
def _fake_chroma_modules(collection):
    """Serve a fake chromadb + orchestrator.embedding for the block.

    Deliberately NOT `mock.patch.dict(sys.modules, ...)`. patch.dict restores
    by CLEARING the dict and refilling it from a pre-patch copy, so every
    module first imported inside the block is evicted on exit — including the
    ones the code under test imports lazily (refresh_chromadb does
    `from orchestrator.tools.knowledge_index import ...` inside the window).

    An evicted submodule stays reachable as its parent package's attribute, so
    afterwards `from orchestrator.tools import knowledge_index` returns the old
    object while `from orchestrator.tools.knowledge_index import name` misses
    sys.modules and imports a SECOND copy. A test that patches one is then
    invisible to production code that imports the other: that split is what
    made test_engram_promotion's indexing test fail (silently indexing into a
    real collection instead of its fake) whenever this module ran first under
    `python -m unittest test_engram_cleaning test_engram_promotion`.

    Restoring only the keys we replaced leaves everything imported inside the
    block where the import system put it.
    """
    chromadb_module = types.ModuleType("chromadb")
    chromadb_module.PersistentClient = lambda path: object()

    embedding_module = types.ModuleType("orchestrator.embedding")
    embedding_module.get_or_create_collection = (
        lambda _client, _collection_name: collection)

    fakes = {
        "chromadb": chromadb_module,
        "orchestrator.embedding": embedding_module,
    }
    missing = object()
    previous = {name: sys.modules.get(name, missing) for name in fakes}
    sys.modules.update(fakes)
    try:
        yield
    finally:
        for name, prior in previous.items():
            if prior is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior


def _write_engram(directory: str, slug: str, tag: str = "archived") -> str:
    path = os.path.join(directory, f"{slug}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "---\n"
            "nexus:\n"
            "  - ora\n"
            "type: engram\n"
            "tags:\n"
            f"  - {tag}\n"
            "---\n\n"
            f"# {slug.title()}\n"
        )
    return os.path.abspath(path)


def _queue_section(heading_marker: str, resolution_marker: str,
                   source_slug: str = "source-test",
                   target_slug: str = "target-test") -> str:
    """Build a single pair section in the queue's canonical format."""
    return (
        f"## [{heading_marker}] Some heading text...\n"
        "\n"
        f"- **Source:** [[{source_slug}]] (modified 2026-01-01, provenance: user)\n"
        f"  *Source claim H1*\n"
        f"- **Target:** [[{target_slug}]] (modified 2026-01-02, provenance: ai-derived)\n"
        f"  *Target claim H1*\n"
        "- **Confidence:** high\n"
        "- **Strategy:** bidirectional\n"
        "\n"
        f"**Resolution:** [{resolution_marker}]\n"
        "\n"
        "---\n"
    )


def _queue_text(*sections: str) -> str:
    preamble = (
        "---\nnexus:\n  - ora\ntype: working\n---\n\n"
        "# Engram Cleaning Queue — test\n\n"
        "*Generated by test fixture.*\n\n"
        "---\n\n"
    )
    return preamble + "\n".join(sections)


class TestResolverReadsResolutionLine(unittest.TestCase):
    """The canonical marker is the `**Resolution:**` line, not the heading."""

    def test_resolution_overrides_pending_heading(self):
        """User edited only the Resolution line; heading still says [pending]."""
        text = _queue_text(_queue_section(
            heading_marker="pending", resolution_marker="skip"
        ))
        pairs = parse_queue(text)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["resolution"], "skip")

    def test_resolution_with_compound_marker(self):
        text = _queue_text(_queue_section(
            heading_marker="pending",
            resolution_marker="changed-mind:source-supersedes-target",
        ))
        pairs = parse_queue(text)
        self.assertEqual(pairs[0]["resolution"], "changed-mind:source-supersedes-target")

    def test_synced_heading_and_resolution(self):
        """When both have the same marker, parser reads consistently."""
        text = _queue_text(_queue_section(
            heading_marker="wrong:source", resolution_marker="wrong:source"
        ))
        pairs = parse_queue(text)
        self.assertEqual(pairs[0]["resolution"], "wrong:source")

    def test_extracts_slugs_and_h1s(self):
        text = _queue_text(_queue_section(
            heading_marker="pending", resolution_marker="skip",
            source_slug="alpha", target_slug="beta",
        ))
        pairs = parse_queue(text)
        self.assertEqual(pairs[0]["source_slug"], "alpha")
        self.assertEqual(pairs[0]["target_slug"], "beta")
        self.assertEqual(pairs[0]["source_h1"], "Source claim H1")
        self.assertEqual(pairs[0]["target_h1"], "Target claim H1")

    def test_multiple_pairs(self):
        text = _queue_text(
            _queue_section("pending", "skip", "a", "b"),
            _queue_section("pending", "wrong:target", "c", "d"),
            _queue_section("pending", "pending", "e", "f"),
        )
        pairs = parse_queue(text)
        self.assertEqual(len(pairs), 3)
        self.assertEqual(pairs[0]["resolution"], "skip")
        self.assertEqual(pairs[1]["resolution"], "wrong:target")
        self.assertEqual(pairs[2]["resolution"], "pending")


class TestQueueRebuild(unittest.TestCase):
    """Queue rebuild keeps only sections whose Resolution line is [pending]."""

    def test_keeps_only_pending(self):
        text = _queue_text(
            _queue_section("pending", "skip", "a", "b"),
            _queue_section("pending", "pending", "c", "d"),
            _queue_section("pending", "wrong:source", "e", "f"),
        )
        rebuilt = _rebuild_queue_keeping_pending(text)
        # The section with [c]-[d] (Resolution: pending) should remain
        self.assertIn("[[c]]", rebuilt)
        self.assertIn("[[d]]", rebuilt)
        # The other two should be removed
        self.assertNotIn("[[a]]", rebuilt)
        self.assertNotIn("[[b]]", rebuilt)
        self.assertNotIn("[[e]]", rebuilt)
        self.assertNotIn("[[f]]", rebuilt)

    def test_resolution_line_is_canonical_for_rebuild(self):
        """Heading [pending] but Resolution [skip] should still be removed."""
        text = _queue_text(_queue_section(
            heading_marker="pending", resolution_marker="skip",
            source_slug="x", target_slug="y",
        ))
        rebuilt = _rebuild_queue_keeping_pending(text)
        self.assertNotIn("[[x]]", rebuilt)
        self.assertNotIn("[[y]]", rebuilt)

    def test_all_pending_returns_unchanged_pairs(self):
        text = _queue_text(
            _queue_section("pending", "pending", "a", "b"),
            _queue_section("pending", "pending", "c", "d"),
        )
        rebuilt = _rebuild_queue_keeping_pending(text)
        self.assertIn("[[a]]", rebuilt)
        self.assertIn("[[c]]", rebuilt)


class TestLogPairKeyParser(unittest.TestCase):
    """The log-parser produces canonical (sorted) source-target tuples."""

    def test_extracts_pair_from_log_entry(self):
        log = (
            "## 2026-05-09 16:24 — skip\n\n"
            "- **Source:** [[slug-alpha]]\n"
            "- **Target:** [[slug-beta]]\n"
            "- **Files mutated:** (none)\n\n"
            "---\n"
        )
        pairs = _parse_log_for_pair_keys(log)
        # Canonical (sorted) tuple
        self.assertIn(("slug-alpha", "slug-beta"), pairs)
        self.assertEqual(len(pairs), 1)

    def test_canonical_sorting(self):
        """Source/target order in the log doesn't matter — pair key is sorted."""
        log_one = (
            "- **Source:** [[zebra]]\n- **Target:** [[apple]]\n"
        )
        log_two = (
            "- **Source:** [[apple]]\n- **Target:** [[zebra]]\n"
        )
        self.assertEqual(
            _parse_log_for_pair_keys(log_one),
            _parse_log_for_pair_keys(log_two),
        )

    def test_multiple_log_entries(self):
        log = (
            "- **Source:** [[a]]\n- **Target:** [[b]]\n\n"
            "- **Source:** [[c]]\n- **Target:** [[d]]\n\n"
            "- **Source:** [[e]]\n- **Target:** [[f]]\n"
        )
        pairs = _parse_log_for_pair_keys(log)
        self.assertEqual(len(pairs), 3)
        self.assertEqual(pairs, {("a", "b"), ("c", "d"), ("e", "f")})

    def test_empty_log(self):
        self.assertEqual(_parse_log_for_pair_keys(""), set())


class TestDetectionFiltersResolved(unittest.TestCase):
    """detect_bidirectional skips pairs whose canonical key is in resolved_set."""

    def setUp(self):
        # Build a fake engram index — two engrams that contradict each other.
        self.by_slug = {
            "alpha": {
                "slug": "alpha",
                "h1": "Alpha claim",
                "filename": "alpha.md",
                "path": "/fake/alpha.md",
                "frontmatter": {"tags": []},
            },
            "beta": {
                "slug": "beta",
                "h1": "Beta claim",
                "filename": "beta.md",
                "path": "/fake/beta.md",
                "frontmatter": {"tags": []},
            },
        }
        self.by_h1 = {
            "Alpha claim": self.by_slug["alpha"],
            "Beta claim": self.by_slug["beta"],
        }

    def test_resolved_pair_is_filtered(self):
        """When (alpha, beta) is in resolved_set, detection skips it."""
        # Stub the sqlite call by patching the module-level GRAPH_DB.
        # Easier path: mock the connection inline.
        from orchestrator.historical import run_engram_cleaning_detection as det

        # Edges: alpha contradicts beta-claim AND beta contradicts alpha-claim
        edges = [("alpha", "Beta claim"), ("beta", "Alpha claim")]

        class FakeCursor:
            def execute(self, *_args, **_kw):
                pass

            def fetchall(self):
                return edges

        class FakeConn:
            def cursor(self):
                return FakeCursor()

            def close(self):
                pass

        with mock.patch.object(det.sqlite3, "connect", return_value=FakeConn()):
            # Without filter: pair surfaces
            unfiltered = detect_bidirectional(
                self.by_slug, self.by_h1, limit=10, resolved_set=set()
            )
            self.assertEqual(len(unfiltered), 1)

            # With filter on canonical (alpha, beta): pair is skipped
            filtered = detect_bidirectional(
                self.by_slug, self.by_h1, limit=10,
                resolved_set={("alpha", "beta")},
            )
            self.assertEqual(len(filtered), 0)

    def test_resolved_set_default_is_empty(self):
        """Backward compatibility — old callers without resolved_set still work."""
        from orchestrator.historical import run_engram_cleaning_detection as det

        edges = [("alpha", "Beta claim"), ("beta", "Alpha claim")]

        class FakeCursor:
            def execute(self, *_args, **_kw):
                pass

            def fetchall(self):
                return edges

        class FakeConn:
            def cursor(self):
                return FakeCursor()

            def close(self):
                pass

        with mock.patch.object(det.sqlite3, "connect", return_value=FakeConn()):
            pairs = detect_bidirectional(self.by_slug, self.by_h1, limit=10)
            self.assertEqual(len(pairs), 1)


class TestResolverChromaRefresh(unittest.TestCase):
    """Resolver refreshes all chunk records and reports file states exactly."""

    def test_chunked_records_zero_missing_and_error_are_distinct(self):
        with tempfile.TemporaryDirectory() as engrams_dir:
            alpha_path = _write_engram(engrams_dir, "alpha")
            _write_engram(engrams_dir, "beta")
            gamma_path = _write_engram(engrams_dir, "gamma")

            alpha_one = f"{alpha_path}#chunk-1"
            alpha_two = f"{alpha_path}#chunk-2"
            gamma_id = f"{gamma_path}#chunk-1"
            collection = _FakeMetadataCollection(
                records={
                    alpha_one: {"metadata": {
                        "path": alpha_path, "tags": ["old"],
                        "chunk_index": 1, "total_chunks": 2,
                    }},
                    alpha_two: {"metadata": {
                        "path": alpha_path, "tags": ["old"],
                        "chunk_index": 2, "total_chunks": 2,
                    }},
                    gamma_id: {"metadata": {
                        "path": gamma_path, "tags": ["old"],
                        "chunk_index": 1, "total_chunks": 1,
                    }},
                },
                fail_update_ids={gamma_id},
            )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                mock.patch.object(
                    run_engram_cleaning_resolver, "ENGRAMS_DIR", engrams_dir),
                _fake_chroma_modules(collection),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                summary = run_engram_cleaning_resolver.refresh_chromadb({
                    "alpha", "beta", "gamma", "missing",
                })

            self.assertEqual(summary, {
                "updated_records": 2,
                "updated_files": 1,
                "never_indexed_files": 1,
                "missing_source_files": 1,
                "errors": 1,
            })
            for record_id, expected_chunk in ((alpha_one, 1), (alpha_two, 2)):
                metadata = collection.records[record_id]["metadata"]
                self.assertEqual(metadata["tags"], ["archived"])
                self.assertEqual(metadata["chunk_index"], expected_chunk)
                self.assertEqual(metadata["total_chunks"], 2)
            self.assertIn("2 records across 1 source files", stdout.getvalue())
            self.assertIn(
                "Existing source files with no ChromaDB records: 1",
                stdout.getvalue(),
            )
            self.assertIn("Missing source files: 1", stdout.getvalue())
            self.assertIn("ChromaDB metadata errors: 1", stderr.getvalue())


class TestPhase3ChromaRefresh(unittest.TestCase):
    """Phase 3 uses one bulk id index and counts records, not source paths."""

    def test_bulk_index_chunk_updates_and_summary_units(self):
        with tempfile.TemporaryDirectory() as engrams_dir:
            alpha_path = _write_engram(engrams_dir, "alpha")
            _write_engram(engrams_dir, "beta")
            gamma_path = _write_engram(engrams_dir, "gamma")

            alpha_one = f"{alpha_path}#chunk-1"
            alpha_two = f"{alpha_path}#chunk-2"
            gamma_id = f"{gamma_path}#chunk-1"
            collection = _FakeMetadataCollection(
                records={
                    alpha_one: {"metadata": {
                        "path": alpha_path, "tags": ["old"],
                        "chunk_index": 1, "total_chunks": 2,
                    }},
                    alpha_two: {"metadata": {
                        "path": alpha_path, "tags": ["old"],
                        "chunk_index": 2, "total_chunks": 2,
                    }},
                    gamma_id: {"metadata": {
                        "path": gamma_path, "tags": ["old"],
                        "chunk_index": 1, "total_chunks": 1,
                    }},
                },
                fail_update_ids={gamma_id},
            )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                mock.patch.object(phase3_chromadb_refresh, "ENGRAMS_DIR",
                                  engrams_dir),
                _fake_chroma_modules(collection),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                summary = phase3_chromadb_refresh.main()

            self.assertEqual(summary, {
                "source_files_scanned": 3,
                "updated_files": 1,
                "updated_records": 2,
                "never_indexed_files": 1,
                "errors": 1,
            })
            for record_id, expected_chunk in ((alpha_one, 1), (alpha_two, 2)):
                metadata = collection.records[record_id]["metadata"]
                self.assertEqual(metadata["tags"], ["archived"])
                self.assertEqual(metadata["chunk_index"], expected_chunk)
                self.assertEqual(metadata["total_chunks"], 2)

            # build_path_id_index() is the only collection-wide get; the
            # id_index fast path prevents one where-query per source file.
            self.assertEqual(len(collection.get_calls), 1)
            self.assertIsNone(collection.get_calls[0]["ids"])
            self.assertIsNone(collection.get_calls[0]["where"])
            output = stdout.getvalue()
            self.assertIn("ChromaDB records updated:         2", output)
            self.assertIn("source files never indexed:       1", output)
            self.assertIn("source files with update errors:  1", output)
            self.assertIn("synthetic update failure", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
