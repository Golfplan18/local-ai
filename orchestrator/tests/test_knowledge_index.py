"""Tests for orchestrator/tools/knowledge_index.py — Phase 5.2.

The indexer parses vault markdown files (with YAML frontmatter) and writes
ChromaDB metadata that the retrieval layer (Phase 5.3 + 5.6) consumes.

Per Reference — Ora YAML Schema §3, §7, §8 — the indexer must round-trip:
  - core: nexus (list), type, tags (list)
  - standard: subtype, relationships (list of objects), source_file,
    source_format, source_path, processed_date, chunk_index,
    total_chunks, source_document (list)
  - conditional: writing, project_type, hub, source_duration_seconds,
    transcription_*

Per Schema §6.5 — chunks need fast tag-filter access for archived /
incubating / private. ChromaDB cannot filter on list membership in
metadata where-clauses, so the indexer stores parallel boolean
extracts (tag_archived, tag_incubating, tag_private).

Per Schema §9 — retired property `domain` no longer indexed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
if _ORCHESTRATOR not in sys.path:
    sys.path.insert(0, _ORCHESTRATOR)

from tools import knowledge_index  # noqa: E402

# Install the deterministic embedding stub so chromadb operations don't
# depend on Ollama running. Cross-platform — pure Python.
from orchestrator.embedding import install_test_stub, resolve_collection  # noqa: E402
install_test_stub()


# ---------------------------------------------------------------------------
# Frontmatter parser tests — block-list form must work, not just inline.
# ---------------------------------------------------------------------------


class TestFrontmatterParsing(unittest.TestCase):
    """Block-list YAML form is the schema-canonical shape (Schema §10 rule 3)."""

    def test_block_list_nexus(self):
        content = (
            "---\n"
            "nexus:\n"
            "  - ora\n"
            "type: framework\n"
            "tags:\n"
            "  - compound\n"
            "  - framework/instruction\n"
            "---\n\n"
            "# Test Note\n\nBody."
        )
        meta, body = knowledge_index._parse_frontmatter(content)
        self.assertEqual(meta["nexus"], ["ora"])
        self.assertEqual(meta["type"], "framework")
        self.assertEqual(meta["tags"], ["compound", "framework/instruction"])
        self.assertIn("Body.", body)

    def test_multi_value_nexus(self):
        content = (
            "---\n"
            "nexus:\n"
            "  - project_a\n"
            "  - project_b\n"
            "type: incubator\n"
            "tags:\n"
            "  - atomic\n"
            "---\n\nbody"
        )
        meta, _ = knowledge_index._parse_frontmatter(content)
        self.assertEqual(meta["nexus"], ["project_a", "project_b"])

    def test_empty_nexus(self):
        content = (
            "---\n"
            "nexus:\n"
            "type: incubator\n"
            "tags:\n"
            "  - atomic\n"
            "---\n\nbody"
        )
        meta, _ = knowledge_index._parse_frontmatter(content)
        # Empty nexus parses as None; indexer must coerce to [] downstream.
        self.assertIn(meta.get("nexus"), (None, [], ""))

    def test_block_list_relationships(self):
        content = (
            "---\n"
            "nexus:\n"
            "  - ora\n"
            "type: engram\n"
            "tags:\n"
            "  - atomic\n"
            "subtype: fact\n"
            "relationships:\n"
            "  - type: supports\n"
            "    target: \"Other Note\"\n"
            "    confidence: high\n"
            "  - type: extends\n"
            "    target: \"Yet Another\"\n"
            "    confidence: medium\n"
            "---\n\nbody"
        )
        meta, _ = knowledge_index._parse_frontmatter(content)
        self.assertEqual(len(meta["relationships"]), 2)
        self.assertEqual(meta["relationships"][0]["type"], "supports")
        self.assertEqual(meta["relationships"][0]["target"], "Other Note")

    def test_no_frontmatter(self):
        content = "# Just a heading\n\nNo frontmatter at all."
        meta, body = knowledge_index._parse_frontmatter(content)
        self.assertEqual(meta, {})
        self.assertEqual(body.strip(), content.strip())

    def test_dp_source_provenance_fields(self):
        content = (
            "---\n"
            "nexus:\n"
            "type: resource\n"
            "tags:\n"
            "  - epistemology\n"
            "source_file: research-paper.pdf\n"
            "source_format: pdf\n"
            "source_path: /Users/oracle/papers/research-paper.pdf\n"
            "processed_date: 2026-04-30\n"
            "chunk_index: 5\n"
            "total_chunks: 42\n"
            "---\n\nbody"
        )
        meta, _ = knowledge_index._parse_frontmatter(content)
        self.assertEqual(meta["source_file"], "research-paper.pdf")
        self.assertEqual(meta["source_format"], "pdf")
        self.assertEqual(meta["chunk_index"], 5)
        self.assertEqual(meta["total_chunks"], 42)


# ---------------------------------------------------------------------------
# Indexed metadata shape tests — the chromadb metadata dict the indexer
# composes for each chunk.
# ---------------------------------------------------------------------------


class TestComposedMetadata(unittest.TestCase):
    """The metadata dict written to ChromaDB carries all Phase 5.2 fields."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.filepath = os.path.join(self.tmpdir, "test_note.md")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, content):
        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write(content)

    def test_canonical_engram(self):
        self._write(
            "---\n"
            "nexus:\n"
            "  - ora\n"
            "type: engram\n"
            "tags:\n"
            "  - atomic\n"
            "  - epistemology\n"
            "subtype: fact\n"
            "---\n\nBody content."
        )
        meta, _ = knowledge_index._parse_frontmatter(Path(self.filepath).read_text())
        chroma_meta = knowledge_index._compose_chroma_metadata(self.filepath, meta)

        self.assertEqual(chroma_meta["type"], "engram")
        self.assertEqual(chroma_meta["nexus"], "ora")  # comma-joined for filter
        self.assertEqual(chroma_meta["tags"], ["atomic", "epistemology"])
        self.assertEqual(chroma_meta["subtype"], "fact")
        # Tag-filter booleans should be False when not tagged accordingly.
        self.assertFalse(chroma_meta["tag_archived"])
        self.assertFalse(chroma_meta["tag_incubating"])
        self.assertFalse(chroma_meta["tag_private"])

    def test_archived_flag(self):
        self._write(
            "---\n"
            "nexus:\n"
            "type: engram\n"
            "tags:\n"
            "  - atomic\n"
            "  - archived\n"
            "---\n\nBody."
        )
        meta, _ = knowledge_index._parse_frontmatter(Path(self.filepath).read_text())
        chroma_meta = knowledge_index._compose_chroma_metadata(self.filepath, meta)
        self.assertTrue(chroma_meta["tag_archived"])

    def test_incubating_flag(self):
        self._write(
            "---\n"
            "nexus:\n"
            "type: incubator\n"
            "tags:\n"
            "  - atomic\n"
            "  - incubating\n"
            "---\n\nBody."
        )
        meta, _ = knowledge_index._parse_frontmatter(Path(self.filepath).read_text())
        chroma_meta = knowledge_index._compose_chroma_metadata(self.filepath, meta)
        self.assertTrue(chroma_meta["tag_incubating"])

    def test_private_flag(self):
        self._write(
            "---\n"
            "nexus:\n"
            "type: chat\n"
            "tags:\n"
            "  - private\n"
            "---\n\nBody."
        )
        meta, _ = knowledge_index._parse_frontmatter(Path(self.filepath).read_text())
        chroma_meta = knowledge_index._compose_chroma_metadata(self.filepath, meta)
        self.assertTrue(chroma_meta["tag_private"])

    def test_subtype_only_with_atomic(self):
        # Subtype on non-atomic note: indexer should NOT propagate it
        # (Schema §7: subtype is atomic-scoped). Indexer is non-validating
        # but doesn't elevate questionable values.
        self._write(
            "---\n"
            "nexus:\n"
            "type: engram\n"
            "tags:\n"
            "  - molecular\n"
            "subtype: fact\n"
            "---\n\nBody."
        )
        meta, _ = knowledge_index._parse_frontmatter(Path(self.filepath).read_text())
        chroma_meta = knowledge_index._compose_chroma_metadata(self.filepath, meta)
        # If indexer chooses to drop, key is absent. If chooses to pass, key has value.
        # Test the policy: subtype ONLY indexed when atomic is in tags.
        self.assertNotIn("subtype", chroma_meta)

    def test_relationships_serialized_as_json(self):
        self._write(
            "---\n"
            "nexus:\n"
            "  - ora\n"
            "type: engram\n"
            "tags:\n"
            "  - atomic\n"
            "subtype: fact\n"
            "relationships:\n"
            "  - type: supports\n"
            "    target: \"Other Note\"\n"
            "    confidence: high\n"
            "---\n\nBody."
        )
        meta, _ = knowledge_index._parse_frontmatter(Path(self.filepath).read_text())
        chroma_meta = knowledge_index._compose_chroma_metadata(self.filepath, meta)
        self.assertIn("relationships", chroma_meta)
        # Stored as JSON string
        rels = json.loads(chroma_meta["relationships"])
        self.assertEqual(rels[0]["type"], "supports")
        self.assertEqual(rels[0]["target"], "Other Note")

    def test_source_provenance_indexed(self):
        self._write(
            "---\n"
            "nexus:\n"
            "type: resource\n"
            "tags:\n"
            "  - epistemology\n"
            "source_file: research-paper.pdf\n"
            "source_format: pdf\n"
            "source_path: /Users/oracle/papers/research-paper.pdf\n"
            "processed_date: 2026-04-30\n"
            "chunk_index: 5\n"
            "total_chunks: 42\n"
            "---\n\nBody."
        )
        meta, _ = knowledge_index._parse_frontmatter(Path(self.filepath).read_text())
        chroma_meta = knowledge_index._compose_chroma_metadata(self.filepath, meta)
        self.assertEqual(chroma_meta["source_file"], "research-paper.pdf")
        self.assertEqual(chroma_meta["source_format"], "pdf")
        self.assertEqual(chroma_meta["source_path"], "/Users/oracle/papers/research-paper.pdf")
        self.assertEqual(chroma_meta["processed_date"], "2026-04-30")
        self.assertEqual(chroma_meta["chunk_index"], 5)
        self.assertEqual(chroma_meta["total_chunks"], 42)

    def test_source_document_serialized_as_json(self):
        self._write(
            "---\n"
            "nexus:\n"
            "type: incubator\n"
            "tags:\n"
            "  - atomic\n"
            "source_document:\n"
            "  - \"Source — Research Paper Chunk 5\"\n"
            "  - \"Source — Other Source Chunk 3\"\n"
            "---\n\nBody."
        )
        meta, _ = knowledge_index._parse_frontmatter(Path(self.filepath).read_text())
        chroma_meta = knowledge_index._compose_chroma_metadata(self.filepath, meta)
        self.assertIn("source_document", chroma_meta)
        sources = json.loads(chroma_meta["source_document"])
        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0], "Source — Research Paper Chunk 5")

    def test_domain_not_indexed(self):
        # Schema §9 retired `domain`. Even if a legacy file has it, drop it.
        self._write(
            "---\n"
            "nexus:\n"
            "type: engram\n"
            "tags:\n"
            "  - atomic\n"
            "domain:\n"
            "  - epistemology\n"
            "---\n\nBody."
        )
        meta, _ = knowledge_index._parse_frontmatter(Path(self.filepath).read_text())
        chroma_meta = knowledge_index._compose_chroma_metadata(self.filepath, meta)
        self.assertNotIn("domain", chroma_meta)

    def test_filename_derived_title(self):
        # Schema §10 rule 8 / §9: no `title` property. Derived from filename.
        self._write(
            "---\n"
            "nexus:\n"
            "type: engram\n"
            "tags:\n"
            "  - atomic\n"
            "---\n\nBody."
        )
        meta, _ = knowledge_index._parse_frontmatter(Path(self.filepath).read_text())
        chroma_meta = knowledge_index._compose_chroma_metadata(self.filepath, meta)
        self.assertEqual(chroma_meta["title"], "test_note")

    def test_path_and_source_present(self):
        self._write(
            "---\n"
            "nexus:\n"
            "type: engram\n"
            "tags:\n"
            "  - atomic\n"
            "---\n\nBody."
        )
        meta, _ = knowledge_index._parse_frontmatter(Path(self.filepath).read_text())
        chroma_meta = knowledge_index._compose_chroma_metadata(self.filepath, meta)
        self.assertEqual(chroma_meta["source"], "test_note.md")
        self.assertEqual(chroma_meta["path"], os.path.abspath(self.filepath))

    def test_legacy_mental_model_still_parses(self):
        # Mental-model notes use `triggers` (non-canonical, but functional
        # for retrieval). Indexer keeps them in metadata.
        self._write(
            "---\n"
            "title: Inversion\n"
            "nexus: mental-model\n"
            "type: engram\n"
            "triggers: when a problem has been approached from only one direction\n"
            "---\n\n# Inversion\n\nThe principle..."
        )
        meta, _ = knowledge_index._parse_frontmatter(Path(self.filepath).read_text())
        chroma_meta = knowledge_index._compose_chroma_metadata(self.filepath, meta)
        self.assertIn("triggers", chroma_meta)
        self.assertIn("approached from only one direction", chroma_meta["triggers"])


# ---------------------------------------------------------------------------
# Section-strip helper tests.
# ---------------------------------------------------------------------------


class TestStripMarkdownSections(unittest.TestCase):
    """strip_markdown_sections removes whole H2 sections by title."""

    BODY = (
        "Intro paragraph.\n"
        "\n"
        "## Summary\n"
        "\n"
        "- bullet one\n"
        "- bullet two\n"
        "\n"
        "## Sources\n"
        "\n"
        "### src_001 — Wire, Tier 1\n"
        "**URL:** https://example.com\n"
        "\n"
        "## Analysis\n"
        "\n"
        "Analysis prose.\n"
        "\n"
        "## Atomic claims\n"
        "\n"
        "### c_001\n"
        "> A claim sentence.\n"
    )

    def test_multiple_sections_removed(self):
        out = knowledge_index.strip_markdown_sections(
            self.BODY, ["Sources", "Atomic claims"])
        self.assertNotIn("## Sources", out)
        self.assertNotIn("src_001", out)
        self.assertNotIn("## Atomic claims", out)
        self.assertNotIn("c_001", out)
        # Non-targeted content survives.
        self.assertIn("Intro paragraph.", out)
        self.assertIn("## Summary", out)
        self.assertIn("- bullet one", out)
        self.assertIn("## Analysis", out)
        self.assertIn("Analysis prose.", out)

    def test_case_insensitive_and_whitespace_trimmed(self):
        body = "## SOURCES  \ncitation\n\n##   atomic Claims\nclaim\n\n## Keep\nkept\n"
        out = knowledge_index.strip_markdown_sections(
            body, ["sources", "Atomic claims"])
        self.assertNotIn("citation", out)
        self.assertNotIn("claim\n", out)
        self.assertIn("kept", out)

    def test_section_at_eof(self):
        body = "## Keep\nkept prose\n\n## Sources\nlast section, no newline after"
        out = knowledge_index.strip_markdown_sections(body, ["Sources"])
        self.assertNotIn("last section", out)
        self.assertIn("kept prose", out)

    def test_nested_h3_removed_with_parent(self):
        out = knowledge_index.strip_markdown_sections(self.BODY, ["Sources"])
        # The ### subsection inside ## Sources goes with it...
        self.assertNotIn("### src_001", out)
        # ...but ### inside a kept section stays.
        self.assertIn("### c_001", out)

    def test_no_match_is_identity(self):
        out = knowledge_index.strip_markdown_sections(self.BODY, ["Nonexistent"])
        self.assertEqual(out, self.BODY)


# ---------------------------------------------------------------------------
# body_filter + cap tests — fake collection + recording embedder, so both
# the stored document and the embed text are observable.
# ---------------------------------------------------------------------------


class _FakeCollection:
    """Minimal stand-in for a chromadb collection (add/get/delete)."""

    def __init__(self):
        self.store = {}

    def add(self, ids, documents, metadatas, embeddings=None):
        for j, id_ in enumerate(ids):
            self.store[id_] = {
                "document": documents[j],
                "metadata": metadatas[j],
                "embedding": embeddings[j] if embeddings else None,
            }

    def get(self, ids=None, where=None):
        found = [i for i in (ids or []) if i in self.store]
        return {
            "ids": found,
            "documents": [self.store[i]["document"] for i in found],
            "metadatas": [self.store[i]["metadata"] for i in found],
        }

    def delete(self, ids):
        for i in ids:
            self.store.pop(i, None)

    def count(self):
        return len(self.store)


class TestBodyFilterAndCaps(unittest.TestCase):
    """body_filter shapes BOTH the stored doc and the embed text; the only
    length cap is MAX_INDEX_CHARS (the old 8000/1000 caps are gone)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.col = _FakeCollection()
        self.embed_texts = []
        self._original_embed = knowledge_index._nomic_embed

        def _recorder(text):
            self.embed_texts.append(text)
            return [0.1] * 8

        knowledge_index._nomic_embed = _recorder

    def tearDown(self):
        knowledge_index._nomic_embed = self._original_embed
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _index(self, name, content, **kwargs):
        path = os.path.join(self.tmpdir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        stats = {"indexed": 0, "skipped": 0, "errors": 0}
        knowledge_index.index_file(self.col, path, stats,
                                   verbose=False, **kwargs)
        return os.path.abspath(path), stats

    def test_body_filter_applied_to_doc_and_embed_text(self):
        content = (
            "---\nnexus:\ntype: resource\ntags:\n  - news\n---\n\n"
            "Keep this paragraph.\n\n## Drop me\nsecret apparatus text\n"
        )

        def flt(body):
            return knowledge_index.strip_markdown_sections(body, ["Drop me"])

        doc_id, stats = self._index("filtered.md", content, body_filter=flt)
        self.assertEqual(stats["indexed"], 1)
        stored = self.col.store[doc_id]["document"]
        self.assertIn("Keep this paragraph.", stored)
        self.assertNotIn("secret apparatus text", stored)
        # The embed text saw the same filtered body.
        self.assertEqual(len(self.embed_texts), 1)
        self.assertIn("Keep this paragraph.", self.embed_texts[0])
        self.assertNotIn("secret apparatus text", self.embed_texts[0])

    def test_20k_body_stored_in_full(self):
        body = "paragraph of article prose. " * 715  # > 20,000 chars
        body = body[:20_000]
        content = "---\nnexus:\ntype: resource\ntags:\n---\n\n" + body
        doc_id, _ = self._index("long.md", content)
        stored = self.col.store[doc_id]["document"]
        self.assertEqual(len(stored), 20_000)  # no 8000-char truncation
        # Embed text carries the full body too (plus title header line).
        self.assertGreater(len(self.embed_texts[0]), 20_000)
        self.assertIn(body[-50:], self.embed_texts[0])

    def test_empty_filter_output_falls_back_to_unfiltered_body(self):
        # Apparatus-only files: the filter consumes the whole body. The
        # unfiltered body must be indexed instead of an empty document.
        content = (
            "---\nnexus:\ntype: resource\ntags:\n  - news\n---\n\n"
            "## Drop me\nquoted claim sentences live here\n"
        )

        def flt(body):
            return knowledge_index.strip_markdown_sections(
                body, ["Drop me"]).strip()

        doc_id, stats = self._index("apparatus-only.md", content,
                                    body_filter=flt)
        self.assertEqual(stats["indexed"], 1)
        stored = self.col.store[doc_id]["document"]
        self.assertIn("quoted claim sentences live here", stored)
        self.assertNotEqual(stored.strip(), "")
        # The embed text also carries the fallback body, so the doc
        # remains retrievable.
        self.assertIn("quoted claim sentences live here",
                      self.embed_texts[0])

    def test_whitespace_only_filter_output_falls_back(self):
        content = ("---\nnexus:\ntype: resource\ntags:\n---\n\n"
                   "Real body text that must survive.\n")
        doc_id, stats = self._index("blank-filter.md", content,
                                    body_filter=lambda b: "  \n\t\n ")
        self.assertEqual(stats["indexed"], 1)
        self.assertIn("Real body text that must survive.",
                      self.col.store[doc_id]["document"])

    def test_max_index_chars_guards_both(self):
        overshoot = knowledge_index.MAX_INDEX_CHARS + 5_000
        content = "---\nnexus:\ntype: resource\ntags:\n---\n\n" + ("A" * overshoot)
        doc_id, _ = self._index("pathological.md", content)
        stored = self.col.store[doc_id]["document"]
        self.assertEqual(len(stored), knowledge_index.MAX_INDEX_CHARS)
        # Embed text body portion is capped at the same constant; the full
        # composed text is body + short title line only.
        self.assertLessEqual(
            len(self.embed_texts[0]),
            knowledge_index.MAX_INDEX_CHARS + 200,
        )


# ---------------------------------------------------------------------------
# End-to-end indexing tests — write a file, run the indexer, query the
# collection, verify roundtrip.
# ---------------------------------------------------------------------------


class TestEndToEndIndexing(unittest.TestCase):
    """Full pipeline: file → parse → index → query → recover values."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.chromadb_path = os.path.join(self.tmpdir, "chromadb")
        # Patch CHROMADB_PATH so the indexer writes to our temp dir.
        self._original_chroma_path = knowledge_index.CHROMADB_PATH
        knowledge_index.CHROMADB_PATH = self.chromadb_path
        # Patch the embedding fn to a fixed vector so the test doesn't
        # depend on a running Ollama instance.
        self._original_embed = knowledge_index._nomic_embed
        knowledge_index._nomic_embed = lambda text: [0.1] * 768

    def tearDown(self):
        knowledge_index.CHROMADB_PATH = self._original_chroma_path
        knowledge_index._nomic_embed = self._original_embed
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_md(self, name, content):
        path = os.path.join(self.tmpdir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def _get_chunk(self, doc_id):
        import chromadb
        client = chromadb.PersistentClient(path=self.chromadb_path)
        col = client.get_collection(resolve_collection("knowledge"))
        return col.get(ids=[doc_id])

    def test_block_list_tags_roundtrip(self):
        path = self._write_md(
            "engram_note.md",
            "---\n"
            "nexus:\n"
            "  - ora\n"
            "type: engram\n"
            "tags:\n"
            "  - atomic\n"
            "  - epistemology\n"
            "subtype: definition\n"
            "---\n\nBody body body."
        )
        knowledge_index.index_path(path, reindex=False)
        result = self._get_chunk(os.path.abspath(path))
        self.assertTrue(result["ids"])
        m = result["metadatas"][0]
        self.assertEqual(m["type"], "engram")
        self.assertEqual(m["tags"], ["atomic", "epistemology"])
        self.assertEqual(m["subtype"], "definition")

    def test_filter_by_type(self):
        # Indexer must produce chunks filterable by type via where-clause.
        # This is what Phase 5.3 type_filter consumes.
        # Bodies padded past the indexer's 50-char content-quality threshold.
        self._write_md(
            "framework_note.md",
            "---\nnexus:\n  - ora\ntype: framework\ntags:\n  - compound\n---\n\n"
            "Body content for the framework note that exceeds fifty characters."
        )
        self._write_md(
            "chat_note.md",
            "---\nnexus:\ntype: chat\ntags:\n---\n\n"
            "Body content for the chat note that exceeds fifty characters in length."
        )
        knowledge_index.index_path(self.tmpdir, reindex=False)

        import chromadb
        client = chromadb.PersistentClient(path=self.chromadb_path)
        col = client.get_collection(resolve_collection("knowledge"))
        framework_results = col.get(where={"type": "framework"})
        self.assertEqual(len(framework_results["ids"]), 1)
        chat_results = col.get(where={"type": "chat"})
        self.assertEqual(len(chat_results["ids"]), 1)

    def test_20k_body_roundtrips_in_full_through_chromadb(self):
        body = ("Long article prose sentence number one of many. " * 500)[:20_000]
        path = self._write_md(
            "long_article.md",
            "---\nnexus:\ntype: resource\ntags:\n  - news\n---\n\n" + body,
        )
        knowledge_index.index_path(path, reindex=False)
        result = self._get_chunk(os.path.abspath(path))
        self.assertTrue(result["ids"])
        self.assertEqual(len(result["documents"][0]), 20_000)

    def test_filter_by_archived_flag(self):
        self._write_md(
            "active.md",
            "---\nnexus:\ntype: engram\ntags:\n  - atomic\n---\n\nBody."
        )
        self._write_md(
            "retired.md",
            "---\nnexus:\ntype: engram\ntags:\n  - atomic\n  - archived\n---\n\nBody."
        )
        knowledge_index.index_path(self.tmpdir, reindex=False)

        import chromadb
        client = chromadb.PersistentClient(path=self.chromadb_path)
        col = client.get_collection(resolve_collection("knowledge"))
        # Active records: tag_archived = False
        active = col.get(where={"tag_archived": False})
        self.assertEqual(len(active["ids"]), 1)
        archived = col.get(where={"tag_archived": True})
        self.assertEqual(len(archived["ids"]), 1)


if __name__ == "__main__":
    unittest.main()


class _ScopedReindexCollection:
    """Minimal Chroma stand-in recording what a reindex deletes."""

    def __init__(self, records):
        self._records = dict(records)   # id -> metadata
        self.deleted: list[str] = []

    def count(self):
        return len(self._records)

    def get(self, limit=None, offset=0, include=None):
        items = list(self._records.items())[offset:offset + (limit or len(self._records))]
        return {"ids": [i for i, _ in items], "metadatas": [m for _, m in items]}

    def delete(self, ids=None, **_):
        for i in ids or []:
            self._records.pop(i, None)
            self.deleted.append(i)

    def add(self, **_):
        pass


class TestReindexIsScopedToThePath(unittest.TestCase):
    """--reindex must replace only the given path's records.

    It previously called delete_collection(client, "knowledge"), dropping the
    ENTIRE collection and then re-indexing only the path given — so
    `--reindex <Engrams>` destroyed the MSI News and Resources records that
    nothing was going to put back. main() also passes reindex through to every
    path argument, so a multi-path run wiped the collection before each one and
    only the last survived.
    """

    def test_only_records_under_the_indexed_path_are_deleted(self):
        from unittest.mock import patch
        from orchestrator.tools import knowledge_index

        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            target = os.path.join(temp, "Engrams")
            os.makedirs(target)
            keep_dir = os.path.join(temp, "MSI News")
            os.makedirs(keep_dir)

            fake = _ScopedReindexCollection({
                os.path.join(target, "a.md"): {"path": os.path.join(target, "a.md")},
                os.path.join(target, "b.md") + "#chunk-2": {
                    "path": os.path.join(target, "b.md")},
                os.path.join(keep_dir, "keep.md"): {
                    "path": os.path.join(keep_dir, "keep.md")},
                os.path.join(temp, "lenses", "lens.md"): {
                    "path": os.path.join(temp, "lenses", "lens.md")},
            })

            with patch.object(knowledge_index, "chromadb", create=True), \
                    patch("chromadb.PersistentClient"), \
                    patch("orchestrator.embedding.get_or_create_collection",
                          return_value=fake):
                knowledge_index.index_path(target, reindex=True)

            self.assertEqual(
                sorted(fake.deleted),
                sorted([os.path.join(target, "a.md"),
                        os.path.join(target, "b.md") + "#chunk-2"]),
                "reindex must delete the indexed path's records, including chunked ids",
            )
            self.assertIn(os.path.join(keep_dir, "keep.md"), fake._records,
                          "records outside the indexed path must survive")
            self.assertIn(os.path.join(temp, "lenses", "lens.md"), fake._records,
                          "the lens library must survive an Engrams reindex")
