#!/usr/bin/env python3
"""Tests for tools/news_index.py — MSI news-article indexer."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
ROOT = ORCHESTRATOR.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ORCHESTRATOR))

from orchestrator import embedding  # noqa: E402
from orchestrator.tools import news_index  # noqa: E402


_APRIL_CPI_FRONTMATTER = """---
headline: April CPI headline cools to 3.1% as shelter inflation stays sticky
lede: |
  Consumer prices rose 3.1 percent over the 12 months ending April 2026, down from 3.3 percent the prior month.
nut_graf: |
  The April reading marks the third consecutive month of cooling headline inflation.
publish_date: 2026-05-13
sources: []
atomic_claims: []
metadata:
  source_cluster_id: cluster_2026-05-13_april_cpi_release
  primary_themes:
    - inflation
    - monetary-policy
  primary_entities:
    - Q_BLS
    - Q_CPI
---

Body of the April CPI article. Includes a discussion of shelter inflation persistence.
"""


_IRAN_FRONTMATTER = """---
headline: Iran response to U.S. proposal rejected as war reaches day 72
lede: |
  Iran transmitted its response to a U.S. 14-point proposal to end the U.S.-Israel war on Iran via Pakistani mediation channels.
nut_graf: |
  The 14-point U.S. proposal requires Iran to abstain from nuclear-weapon development.
publish_date: 2026-05-11
sources: []
atomic_claims: []
metadata:
  source_cluster_id: cluster_2026-05-11_iran_war_day_72
  primary_themes:
    - foreign-policy
  primary_entities:
    - Q_IRAN
    - Q_TRUMP
---

Body of the Iran article. Discusses the 14-point proposal and the rejection.
"""


_NO_METADATA_FRONTMATTER = """---
headline: Sample article with no metadata block
lede: A short lede.
nut_graf: A short nut graf.
publish_date: 2026-05-14
---

Body content padded to clear the 50-character minimum threshold.
"""


# ---------------------------------------------------------------------------
# Pure-Python helper unit tests (no chromadb / no embedding required)
# ---------------------------------------------------------------------------


class TestFrontmatterParsing(unittest.TestCase):
    """Unit tests for _parse_frontmatter."""

    def test_basic(self):
        meta, body = news_index._parse_frontmatter(_APRIL_CPI_FRONTMATTER)
        self.assertEqual(meta["headline"][:5], "April")
        self.assertEqual(meta["publish_date"].isoformat(), "2026-05-13")
        self.assertIn("Body of the April CPI article", body)

    def test_no_frontmatter(self):
        meta, body = news_index._parse_frontmatter("Just a body, no fences.")
        self.assertEqual(meta, {})
        self.assertIn("Just a body", body)

    def test_malformed_yaml(self):
        meta, body = news_index._parse_frontmatter(
            "---\nbroken: [unterminated\n---\n\nBody"
        )
        # Should not raise; returns empty meta.
        self.assertEqual(meta, {})


class TestMetadataComposition(unittest.TestCase):

    def test_full_article(self):
        meta, _ = news_index._parse_frontmatter(_APRIL_CPI_FRONTMATTER)
        chroma = news_index._compose_chroma_metadata("/tmp/2026-05-13-april-cpi.md", meta)

        self.assertEqual(chroma["slug"], "2026-05-13-april-cpi")
        self.assertEqual(chroma["headline"][:5], "April")
        self.assertEqual(chroma["publish_date"], "2026-05-13")
        self.assertEqual(chroma["source_cluster_id"], "cluster_2026-05-13_april_cpi_release")

        themes = json.loads(chroma["primary_themes_json"])
        self.assertEqual(themes, ["inflation", "monetary-policy"])
        entities = json.loads(chroma["primary_entities_json"])
        self.assertEqual(entities, ["Q_BLS", "Q_CPI"])

    def test_lede_excerpt_truncated(self):
        long_lede = "x" * 500
        meta = {"headline": "h", "lede": long_lede, "publish_date": "2026-05-14"}
        chroma = news_index._compose_chroma_metadata("/tmp/foo.md", meta)
        self.assertEqual(len(chroma["lede_excerpt"]), 300)

    def test_no_metadata_block(self):
        meta, _ = news_index._parse_frontmatter(_NO_METADATA_FRONTMATTER)
        chroma = news_index._compose_chroma_metadata("/tmp/2026-05-14-foo.md", meta)
        # Should not raise; cluster id is empty; themes/entities omitted.
        self.assertEqual(chroma["source_cluster_id"], "")
        self.assertNotIn("primary_themes_json", chroma)
        self.assertNotIn("primary_entities_json", chroma)

    def test_empty_themes_list_omitted(self):
        meta = {
            "headline": "h",
            "publish_date": "2026-05-14",
            "metadata": {
                "source_cluster_id": "c1",
                "primary_themes": None,  # null in YAML
                "primary_entities": [],
            },
        }
        chroma = news_index._compose_chroma_metadata("/tmp/foo.md", meta)
        self.assertNotIn("primary_themes_json", chroma)
        self.assertNotIn("primary_entities_json", chroma)


class TestSlugAndEmbedText(unittest.TestCase):

    def test_slug_strips_md(self):
        self.assertEqual(
            news_index._filename_slug("/path/2026-05-13-april-cpi.md"),
            "2026-05-13-april-cpi",
        )

    def test_slug_handles_no_md(self):
        self.assertEqual(
            news_index._filename_slug("/path/something"),
            "something",
        )

    def test_embed_text_combines_fields(self):
        meta = {
            "headline": "HEADLINE",
            "lede": "LEDE",
            "nut_graf": "NUT",
        }
        text = news_index._build_embed_text(meta, "BODY")
        self.assertIn("HEADLINE", text)
        self.assertIn("LEDE", text)
        self.assertIn("NUT", text)
        self.assertIn("BODY", text)

    def test_embed_text_truncates_body(self):
        text = news_index._build_embed_text({"headline": "h"}, "x" * 10000)
        # Body capped at 6000.
        self.assertLessEqual(len(text), 6500)


# ---------------------------------------------------------------------------
# Indexer integration tests (use chromadb + test-stub embedder)
# ---------------------------------------------------------------------------


class TestIndexerIntegration(unittest.TestCase):
    """End-to-end indexing into a temp ChromaDB with the deterministic stub embedder."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="news_index_test_")
        self.chromadb_path = os.path.join(self.tmpdir, "chromadb")
        os.makedirs(self.chromadb_path, exist_ok=True)
        self.articles_dir = os.path.join(self.tmpdir, "articles")
        os.makedirs(self.articles_dir, exist_ok=True)

        # Patch CHROMADB_PATH on the module.
        self._original_path = news_index.CHROMADB_PATH
        news_index.CHROMADB_PATH = self.chromadb_path

        # Install the deterministic SHA256-based stub embedder.
        embedding.install_test_stub()

    def tearDown(self):
        news_index.CHROMADB_PATH = self._original_path
        embedding.uninstall_test_stub()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, name, content):
        path = os.path.join(self.articles_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def _open_collection(self):
        import chromadb
        from orchestrator.embedding import get_or_create_collection
        client = chromadb.PersistentClient(path=self.chromadb_path)
        return get_or_create_collection(client, news_index.COLLECTION_NAME)

    def test_index_single_file(self):
        path = self._write("2026-05-13-april-cpi.md", _APRIL_CPI_FRONTMATTER)
        news_index.index_path(path, reindex=False)

        col = self._open_collection()
        self.assertEqual(col.count(), 1)

        result = col.get(ids=[os.path.abspath(path)])
        self.assertTrue(result["ids"])
        m = result["metadatas"][0]
        self.assertEqual(m["slug"], "2026-05-13-april-cpi")
        self.assertEqual(m["source_cluster_id"], "cluster_2026-05-13_april_cpi_release")

    def test_index_directory(self):
        self._write("2026-05-13-april-cpi.md", _APRIL_CPI_FRONTMATTER)
        self._write("2026-05-11-iran-rejects.md", _IRAN_FRONTMATTER)

        news_index.index_path(self.articles_dir, reindex=False)

        col = self._open_collection()
        self.assertEqual(col.count(), 2)

    def test_idempotent_reindex_skip(self):
        path = self._write("2026-05-13-april-cpi.md", _APRIL_CPI_FRONTMATTER)
        news_index.index_path(path, reindex=False)
        news_index.index_path(path, reindex=False)  # Second call should be a no-op

        col = self._open_collection()
        self.assertEqual(col.count(), 1)

    def test_reindex_clears_collection(self):
        path1 = self._write("2026-05-13-april-cpi.md", _APRIL_CPI_FRONTMATTER)
        news_index.index_path(path1, reindex=False)

        # Add a second article via fresh reindex of just the second.
        path2 = self._write("2026-05-11-iran-rejects.md", _IRAN_FRONTMATTER)
        news_index.index_path(path2, reindex=True)

        col = self._open_collection()
        self.assertEqual(col.count(), 1)

    def test_filter_by_source_cluster_id(self):
        path1 = self._write("a.md", _APRIL_CPI_FRONTMATTER)
        path2 = self._write("b.md", _IRAN_FRONTMATTER)
        news_index.index_path(self.articles_dir, reindex=False)

        col = self._open_collection()
        cpi = col.get(where={"source_cluster_id": "cluster_2026-05-13_april_cpi_release"})
        self.assertEqual(len(cpi["ids"]), 1)
        iran = col.get(where={"source_cluster_id": "cluster_2026-05-11_iran_war_day_72"})
        self.assertEqual(len(iran["ids"]), 1)


if __name__ == "__main__":
    unittest.main()
