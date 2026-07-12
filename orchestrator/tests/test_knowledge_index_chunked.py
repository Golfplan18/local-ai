"""Tests for HCP chunked indexing in orchestrator/tools/knowledge_index.py.

A file whose body exceeds one HCP chunk (CHUNK_THRESHOLD_CHARS) is indexed
as MULTIPLE ChromaDB records — ids "<abspath>#chunk-N", chunk_index /
total_chunks stamped, HCP context prepend in each stored document. Before
this, a long file was ONE record hard-truncated at MAX_INDEX_CHARS, so a
100-page document silently lost everything past ~40 pages.

Also covers the delete/reindex flows that previously assumed id = abspath:
index_file's force path and index_msi_news.remove_paths now delete by PATH
(delete_file_records), so single-record ↔ chunked transitions leave no
orphans.

Short files keep the original single-record layout — regression-pinned here.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.tools import index_msi_news, knowledge_index  # noqa: E402

# Deterministic embedding stub: hcp's similarity scorer routes through
# orchestrator.embedding; the stub keeps it off Ollama.
from orchestrator.embedding import install_test_stub  # noqa: E402
install_test_stub()


class _FakeCollection:
    """Chromadb stand-in supporting the pieces the indexer touches,
    including get(where=...) equality filtering on metadata (which the
    delete-by-path flow relies on)."""

    def __init__(self):
        self.store = {}
        self.get_calls = []

    def add(self, ids, documents, metadatas, embeddings=None):
        for j, id_ in enumerate(ids):
            self.store[id_] = {
                "document": documents[j],
                "metadata": metadatas[j],
                "embedding": embeddings[j] if embeddings else None,
            }

    def get(self, ids=None, where=None, include=None):
        self.get_calls.append({
            "ids": ids,
            "where": where,
            "include": include,
        })
        if where:
            found = [i for i, rec in self.store.items()
                     if all(rec["metadata"].get(k) == v
                            for k, v in where.items())]
        elif ids is None:
            found = list(self.store)
        else:
            found = [i for i in (ids or []) if i in self.store]
        result = {
            "ids": found,
            "documents": [self.store[i]["document"] for i in found],
            "metadatas": [self.store[i]["metadata"] for i in found],
        }
        if include and "embeddings" in include:
            result["embeddings"] = [self.store[i]["embedding"] for i in found]
        return result

    def update(self, ids, metadatas):
        for j, id_ in enumerate(ids):
            if id_ in self.store:
                self.store[id_]["metadata"].update(metadatas[j])

    def delete(self, ids):
        for i in ids:
            self.store.pop(i, None)

    def count(self):
        return len(self.store)


def _long_body(tail_sentinel: str) -> str:
    """A sectioned body comfortably over CHUNK_THRESHOLD_CHARS, ending in a
    recognizable sentinel so tail loss is detectable."""
    sections = []
    for i in range(6):
        paras = "\n\n".join(
            f"Section {i} paragraph {j}. " + ("Substantive prose text. " * 15)
            for j in range(8))
        sections.append(f"## Section {i}\n\n{paras}")
    return ("# Long Work\n\nThe long work's thesis sentence.\n\n"
            + "\n\n".join(sections)
            + f"\n\n{tail_sentinel}\n")


class _Base(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.col = _FakeCollection()
        self._original_embed = knowledge_index._nomic_embed
        knowledge_index._nomic_embed = lambda text: [0.1] * 8

    def tearDown(self):
        knowledge_index._nomic_embed = self._original_embed
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, name, content):
        path = os.path.join(self.tmpdir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def _index(self, path, **kwargs):
        stats = {"indexed": 0, "skipped": 0, "errors": 0}
        knowledge_index.index_file(self.col, path, stats,
                                   verbose=False, **kwargs)
        return stats

    def _chunk_ids(self, path):
        abspath = os.path.abspath(path)
        return sorted(i for i in self.col.store if i.startswith(f"{abspath}#chunk-"))


class TestFileRecordPrimitives(_Base):
    """Shared path-resolution helpers work across both record layouts."""

    def _seed(self, path, ids, embeddings):
        abspath = os.path.abspath(path)
        self.col.add(
            ids=ids,
            documents=[f"document {i}" for i in range(len(ids))],
            metadatas=[{
                "path": abspath,
                "title": os.path.basename(path),
                "chunk_index": i + 1,
                "total_chunks": len(ids),
            } for i in range(len(ids))],
            embeddings=embeddings,
        )

    def test_resolve_file_ids_single_chunked_and_never_indexed(self):
        single = os.path.join(self.tmpdir, "single.md")
        chunked = os.path.join(self.tmpdir, "chunked.md")
        single_id = os.path.abspath(single)
        chunk_ids = [f"{os.path.abspath(chunked)}#chunk-{i}" for i in (1, 2)]
        self._seed(single, [single_id], [[9.0, 1.0]])
        self._seed(chunked, chunk_ids, [[1.0, 0.0], [3.0, 0.0]])

        self.assertEqual(
            knowledge_index.resolve_file_ids(self.col, single), [single_id])
        self.assertEqual(
            knowledge_index.resolve_file_ids(self.col, chunked), chunk_ids)
        self.assertEqual(
            knowledge_index.resolve_file_ids(
                self.col, os.path.join(self.tmpdir, "missing.md")),
            [],
        )

    def test_build_path_id_index_groups_all_records_in_one_bulk_get(self):
        single = os.path.join(self.tmpdir, "single.md")
        chunked = os.path.join(self.tmpdir, "chunked.md")
        single_id = os.path.abspath(single)
        chunk_ids = [f"{os.path.abspath(chunked)}#chunk-{i}" for i in (1, 2)]
        self._seed(single, [single_id], [[9.0, 1.0]])
        self._seed(chunked, chunk_ids, [[1.0, 0.0], [3.0, 0.0]])
        self.col.add(
            ids=["orphan"], documents=["orphan"],
            metadatas=[{"title": "no path"}], embeddings=[[0.0, 0.0]],
        )
        self.col.get_calls.clear()

        id_index = knowledge_index.build_path_id_index(self.col)

        self.assertEqual(id_index[os.path.abspath(single)], [single_id])
        self.assertEqual(id_index[os.path.abspath(chunked)], chunk_ids)
        self.assertNotIn("orphan", id_index)
        self.assertEqual(len(self.col.get_calls), 1)
        self.assertEqual(self.col.get_calls[0]["include"], ["metadatas"])
        self.assertIsNone(self.col.get_calls[0]["ids"])
        self.assertIsNone(self.col.get_calls[0]["where"])

    def test_update_file_metadata_merges_single_chunked_and_counts_real_records(self):
        single = os.path.join(self.tmpdir, "single.md")
        chunked = os.path.join(self.tmpdir, "chunked.md")
        single_id = os.path.abspath(single)
        chunk_ids = [f"{os.path.abspath(chunked)}#chunk-{i}" for i in (1, 2)]
        self._seed(single, [single_id], [[9.0, 1.0]])
        self._seed(chunked, chunk_ids, [[1.0, 0.0], [3.0, 0.0]])

        self.assertEqual(
            knowledge_index.update_file_metadata(
                self.col, single, {"tags": ["new"]}),
            1,
        )
        id_index = knowledge_index.build_path_id_index(self.col)
        self.col.get_calls.clear()
        self.assertEqual(
            knowledge_index.update_file_metadata(
                self.col, chunked, {"tags": ["new"]}, id_index=id_index),
            2,
        )
        self.assertEqual(
            knowledge_index.update_file_metadata(
                self.col, os.path.join(self.tmpdir, "missing.md"),
                {"tags": ["new"]}, id_index=id_index),
            0,
        )
        self.assertEqual(self.col.get_calls, [])  # indexed fast path made no reads
        for index, record_id in enumerate(chunk_ids, 1):
            metadata = self.col.store[record_id]["metadata"]
            self.assertEqual(metadata["tags"], ["new"])
            self.assertEqual(metadata["chunk_index"], index)
            self.assertEqual(metadata["total_chunks"], 2)

    def test_get_document_embedding_single_centroid_and_missing(self):
        single = os.path.join(self.tmpdir, "single.md")
        chunked = os.path.join(self.tmpdir, "chunked.md")
        no_embedding = os.path.join(self.tmpdir, "no-embedding.md")
        self._seed(single, [os.path.abspath(single)], [[9.0, 1.0]])
        chunk_ids = [f"{os.path.abspath(chunked)}#chunk-{i}" for i in (1, 2)]
        self._seed(chunked, chunk_ids, [[1.0, 0.0], [3.0, 0.0]])
        self._seed(no_embedding, [os.path.abspath(no_embedding)], [None])

        self.assertEqual(
            knowledge_index.get_document_embedding(self.col, single),
            [9.0, 1.0],
        )
        self.assertEqual(
            knowledge_index.get_document_embedding(self.col, chunked),
            [2.0, 0.0],
        )
        self.assertIsNone(
            knowledge_index.get_document_embedding(self.col, no_embedding))
        self.assertIsNone(
            knowledge_index.get_document_embedding(
                self.col, os.path.join(self.tmpdir, "missing.md")))


class TestChunkedRoundTrip(_Base):

    FRONT = "---\nnexus:\n  - ora\ntype: resource\ntags:\n  - epistemology\n---\n\n"

    def test_long_file_indexes_as_chunk_records(self):
        sentinel = "FINAL-TAIL-SENTINEL the very last line of the work."
        path = self._write("long.md", self.FRONT + _long_body(sentinel))
        stats = self._index(path)
        self.assertEqual(stats["indexed"], 1)

        abspath = os.path.abspath(path)
        chunk_ids = self._chunk_ids(path)
        self.assertGreater(len(chunk_ids), 1)
        self.assertNotIn(abspath, self.col.store)  # no bare-abspath record

        total = len(chunk_ids)
        seen_indices = set()
        for cid in chunk_ids:
            rec = self.col.store[cid]
            self.assertEqual(rec["metadata"]["total_chunks"], total)
            self.assertEqual(rec["metadata"]["path"], abspath)
            self.assertEqual(rec["metadata"]["type"], "resource")
            self.assertIn("[POSITION]", rec["document"])  # HCP prepend stored
            seen_indices.add(rec["metadata"]["chunk_index"])
        self.assertEqual(seen_indices, set(range(1, total + 1)))
        # Ids carry the 1-based chunk number.
        self.assertIn(f"{abspath}#chunk-1", chunk_ids)

    def test_tail_content_is_retrievable(self):
        # The 120k-truncation regression, at test scale: content past the
        # old single-record horizon must land in SOME stored record.
        sentinel = "FINAL-TAIL-SENTINEL the very last line of the work."
        path = self._write("long.md", self.FRONT + _long_body(sentinel))
        self._index(path)
        blob = "\n".join(rec["document"] for rec in self.col.store.values())
        self.assertIn(sentinel, blob)

    def test_skip_if_already_indexed(self):
        path = self._write("long.md", self.FRONT + _long_body("tail."))
        self._index(path)
        size = len(self.col.store)
        stats = self._index(path)  # second pass, no force
        self.assertEqual(stats["skipped"], 1)
        self.assertEqual(stats["indexed"], 0)
        self.assertEqual(len(self.col.store), size)


class TestShortFileUnchanged(_Base):

    def test_single_record_layout(self):
        content = ("---\nnexus:\n  - ora\ntype: engram\ntags:\n  - atomic\n---\n\n"
                   "A short note body well under one chunk.")
        path = self._write("short.md", content)
        stats = self._index(path)
        self.assertEqual(stats["indexed"], 1)

        abspath = os.path.abspath(path)
        self.assertIn(abspath, self.col.store)
        self.assertEqual(self._chunk_ids(path), [])
        rec = self.col.store[abspath]
        self.assertNotIn("chunk_index", rec["metadata"])
        self.assertNotIn("total_chunks", rec["metadata"])
        self.assertNotIn("[POSITION]", rec["document"])
        self.assertIn("A short note body", rec["document"])

    def test_frontmatter_chunk_fields_still_roundtrip(self):
        # DP-provenance files that ARE a chunk of some source keep their
        # frontmatter-declared chunk_index/total_chunks on the single record.
        content = ("---\nnexus:\ntype: resource\ntags:\n"
                   "chunk_index: 5\ntotal_chunks: 42\n---\n\n"
                   "Short chunk-output note body.")
        path = self._write("dp-chunk.md", content)
        self._index(path)
        rec = self.col.store[os.path.abspath(path)]
        self.assertEqual(rec["metadata"]["chunk_index"], 5)
        self.assertEqual(rec["metadata"]["total_chunks"], 42)


class TestDeleteAndReindexTransitions(_Base):

    FRONT = "---\nnexus:\ntype: resource\ntags:\n---\n\n"

    def test_force_reindex_shrink_leaves_no_orphan_chunks(self):
        path = self._write("doc.md", self.FRONT + _long_body("tail."))
        self._index(path)
        self.assertGreater(len(self._chunk_ids(path)), 1)

        # File shrinks below the chunking threshold; force re-index.
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.FRONT + "Now a short body that fits one record.")
        stats = self._index(path, force=True)
        self.assertEqual(stats["indexed"], 1)

        abspath = os.path.abspath(path)
        self.assertEqual(self._chunk_ids(path), [])  # no orphans
        self.assertIn(abspath, self.col.store)
        self.assertIn("Now a short body", self.col.store[abspath]["document"])

    def test_force_reindex_grow_replaces_single_record(self):
        path = self._write("doc.md", self.FRONT + "Short body first.")
        self._index(path)
        abspath = os.path.abspath(path)
        self.assertIn(abspath, self.col.store)

        with open(path, "w", encoding="utf-8") as f:
            f.write(self.FRONT + _long_body("grown tail."))
        stats = self._index(path, force=True)
        self.assertEqual(stats["indexed"], 1)
        self.assertNotIn(abspath, self.col.store)  # bare record gone
        self.assertGreater(len(self._chunk_ids(path)), 1)

    def test_force_reindex_chunked_to_chunked_no_stale_high_chunks(self):
        path = self._write("doc.md", self.FRONT + _long_body("tail one."))
        self._index(path)
        first_count = len(self._chunk_ids(path))
        self.assertGreater(first_count, 1)

        # Re-index a shorter (but still chunked) version: stale high-numbered
        # chunk records from the longer pass must not survive.
        shorter = self.FRONT + _long_body("tail two.")[: len(_long_body("x")) // 2]
        with open(path, "w", encoding="utf-8") as f:
            f.write(shorter)
        self._index(path, force=True)
        new_ids = self._chunk_ids(path)
        totals = {self.col.store[i]["metadata"]["total_chunks"] for i in new_ids}
        self.assertEqual(len(totals), 1)
        self.assertEqual(len(new_ids), totals.pop())

    def test_delete_file_records_counts_both_layouts(self):
        long_path = self._write("a.md", self.FRONT + _long_body("t."))
        short_path = self._write("b.md", self.FRONT + "Short body here.")
        self._index(long_path)
        self._index(short_path)
        knowledge_index.delete_file_records(self.col, long_path)
        knowledge_index.delete_file_records(self.col, short_path)
        self.assertEqual(len(self.col.store), 0)


class TestMsiRemovePathsChunked(_Base):

    def test_remove_paths_drops_chunked_article(self):
        body = _long_body("msi tail sentinel.")
        path = self._write("2026-05-01-article.md", body)
        stats = {"indexed": 0, "skipped": 0, "errors": 0}
        knowledge_index.index_file(
            self.col, path, stats,
            meta_overrides=index_msi_news.MSI_META_OVERRIDES,
            body_filter=index_msi_news.msi_body_filter,
            verbose=False)
        self.assertGreater(len(self.col.store), 1)  # chunked

        removed = index_msi_news.remove_paths([path], collection=self.col)
        self.assertGreater(removed, 1)
        self.assertEqual(len(self.col.store), 0)

    def test_remove_paths_still_works_for_single_record(self):
        path = self._write("2026-05-02-short.md",
                           "Short MSI article body, single record layout, "
                           "definitely over fifty characters long.")
        stats = {"indexed": 0, "skipped": 0, "errors": 0}
        knowledge_index.index_file(
            self.col, path, stats,
            meta_overrides=index_msi_news.MSI_META_OVERRIDES,
            verbose=False)
        self.assertEqual(len(self.col.store), 1)
        index_msi_news.remove_paths([path], collection=self.col)
        self.assertEqual(len(self.col.store), 0)


class TestSplitForStorage(unittest.TestCase):
    """_split_for_storage — the storage-layer backstop for a single HCP
    chunk whose one unsplittable paragraph/block exceeds MAX_INDEX_CHARS.
    Regression coverage for a bug found by adversarial review: the old
    `[:MAX_INDEX_CHARS]` slice silently truncated such a chunk, with no
    sibling chunk carrying the lost tail."""

    def test_short_text_returned_as_single_part(self):
        parts = knowledge_index._split_for_storage("short text", 100)
        self.assertEqual(parts, ["short text"])

    def test_oversized_text_split_without_loss(self):
        text = ("word " * 5000).strip()
        parts = knowledge_index._split_for_storage(text, 1000)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(p) <= 1000 for p in parts))
        self.assertEqual("".join(parts), text)  # byte-exact reassembly

    def test_prefers_paragraph_boundary(self):
        para_a = "Alpha content. " * 50
        para_b = "Beta content. " * 50
        text = para_a + "\n\n" + para_b
        parts = knowledge_index._split_for_storage(text, len(para_a) + 5)
        self.assertGreaterEqual(len(parts), 2)
        self.assertTrue(parts[0].rstrip().endswith("Alpha content."))

    def test_no_boundary_hard_cuts_without_loss(self):
        text = "x" * 3000  # no paragraph or sentence boundary anywhere
        parts = knowledge_index._split_for_storage(text, 1000)
        self.assertEqual(len(parts), 3)
        self.assertEqual("".join(parts), text)


class TestChunkedIndexingOversizedSingleChunk(_Base):
    """End-to-end: an HCP chunk whose formatted text exceeds MAX_INDEX_CHARS
    is stored as multiple '#chunk-N-part-P' records, with the full text
    recoverable across them — not truncated."""

    def setUp(self):
        super().setUp()
        self._orig_max = knowledge_index.MAX_INDEX_CHARS
        self._orig_threshold = knowledge_index.CHUNK_THRESHOLD_CHARS
        knowledge_index.MAX_INDEX_CHARS = 500       # small, so a normal-sized
                                                     # HCP chunk still overflows it
        knowledge_index.CHUNK_THRESHOLD_CHARS = 200  # so a modest test body
                                                      # still routes through
                                                      # _index_chunked at all

    def tearDown(self):
        knowledge_index.MAX_INDEX_CHARS = self._orig_max
        knowledge_index.CHUNK_THRESHOLD_CHARS = self._orig_threshold
        super().tearDown()

    def test_oversized_chunk_splits_into_part_records_no_loss(self):
        sentinel = "TAIL-OF-OVERSIZED-CHUNK-SENTINEL"
        # One long unbroken paragraph per section (no internal blank
        # lines) so HCP keeps each as a single raw chunk exceeding the
        # 500-char storage cap set above.
        body = ("---\nnexus:\ntype: resource\ntags:\n---\n\n"
                "# Doc\n\nThesis sentence.\n\n"
                + "\n\n".join(
                    f"## Section {i}\n\n" + ("Prose word run. " * 40)
                    for i in range(3))
                + f"\n\n{sentinel}\n")
        path = self._write("oversized.md", body)
        stats = self._index(path)
        self.assertEqual(stats["indexed"], 1)

        part_ids = sorted(i for i in self.col.store if "-part-" in i)
        self.assertTrue(part_ids, "expected at least one split storage record")

        # The sentinel (true tail of the source) is present somewhere in
        # the stored records — not truncated away.
        blob = "".join(rec["document"] for rec in self.col.store.values())
        self.assertIn(sentinel, blob)

        for cid in part_ids:
            self.assertLessEqual(len(self.col.store[cid]["document"]),
                                 knowledge_index.MAX_INDEX_CHARS)

    def test_split_records_cleaned_up_by_delete_file_records(self):
        body = ("---\nnexus:\ntype: resource\ntags:\n---\n\n"
                "# Doc\n\nThesis sentence.\n\n"
                + "\n\n".join(
                    f"## Section {i}\n\n" + ("Prose word run. " * 40)
                    for i in range(3))
                + "\n\ntail.\n")
        path = self._write("oversized2.md", body)
        self._index(path)
        self.assertTrue(any("-part-" in i for i in self.col.store))
        knowledge_index.delete_file_records(self.col, path)
        self.assertEqual(len(self.col.store), 0)


class TestChunkedAddFailureFallsBackToSingleRecord(_Base):
    """A collection.add() failure inside _index_chunked must fall back to
    the single-record path rather than leave the file with zero records
    (especially load-bearing for force=True, which already deleted any
    prior records before this runs). Regression coverage for a bug found
    by adversarial review."""

    FRONT = "---\nnexus:\ntype: resource\ntags:\n---\n\n"

    def test_add_failure_falls_back(self):
        real_add = self.col.add
        call_count = {"n": 0}

        def flaky_add(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1 and len(kwargs.get("ids", [])) > 1:
                raise RuntimeError("simulated collection.add failure")
            return real_add(*args, **kwargs)

        self.col.add = flaky_add
        body = self.FRONT + _long_body("fallback tail.")
        path = self._write("flaky.md", body)
        stats = self._index(path)

        self.assertEqual(stats["indexed"], 1)
        # Fell back to the single-record layout — one record at the bare
        # abspath, not zero records.
        self.assertIn(os.path.abspath(path), self.col.store)
        self.assertEqual(len([i for i in self.col.store if "#chunk-" in i]), 0)


if __name__ == "__main__":
    unittest.main()
