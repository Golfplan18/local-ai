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
from orchestrator.embedding import install_test_stub  # noqa: E402
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
        col = client.get_collection("knowledge")
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
        col = client.get_collection("knowledge")
        framework_results = col.get(where={"type": "framework"})
        self.assertEqual(len(framework_results["ids"]), 1)
        chat_results = col.get(where={"type": "chat"})
        self.assertEqual(len(chat_results["ids"]), 1)

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
        col = client.get_collection("knowledge")
        # Active records: tag_archived = False
        active = col.get(where={"tag_archived": False})
        self.assertEqual(len(active["ids"]), 1)
        archived = col.get(where={"tag_archived": True})
        self.assertEqual(len(archived["ids"]), 1)


if __name__ == "__main__":
    unittest.main()
