"""Tests for orchestrator/tools/index_msi_news.py — MSI body filter +
forced re-index path.

The MSI News mirror articles carry non-content apparatus (## Sources,
## Atomic claims, a trailing generation-notice paragraph) that must not
reach the ChromaDB document or the embed text. `msi_body_filter` strips
it; `index_msi_news` passes the filter into `knowledge_index.index_file`
via `body_filter`, so the stored doc and the embedding always agree.

No network / no Ollama: the embedding stub is installed and the ChromaDB
collection is replaced with an in-memory fake.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO_ROOT = os.path.dirname(_ORCHESTRATOR)
for _p in (_ORCHESTRATOR, _REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from orchestrator.tools import index_msi_news, knowledge_index  # noqa: E402

# Deterministic embedding stub — no Ollama / OpenRouter needed.
from orchestrator.embedding import install_test_stub  # noqa: E402
install_test_stub()


BOILERPLATE = (
    "*This article was generated algorithmically by Main Street "
    "Independent's News Article Generator framework from the public "
    "sources listed above. [Methodology](/methodology). Published under "
    "[CC0](https://creativecommons.org/publicdomain/zero/1.0/).*"
)

ARTICLE_BODY = (
    "## Summary\n"
    "\n"
    "**Subtype:** fact\n"
    "\n"
    "- New York school districts are encouraging vegetarian meals at home.\n"
    "- A poll found 64% of U.S. adults eat chicken several times weekly.\n"
    "\n"
    "School nutrition programs that feature vegetarian lunch options are\n"
    "successfully encouraging students to adopt meat-reduced diets at home.\n"
    "\n"
    "Experts say the spillover effect from cafeterias to home kitchens\n"
    "represents a measurable dietary adjustment.\n"
    "\n"
    "## Atomic claims\n"
    "\n"
    "### c_001\n"
    "- **Hedge:** attributed\n"
    "- **Sources:** src_001\n"
    "\n"
    "> School nutrition programs are encouraging meat-reduced diets.\n"
    "\n"
    "## Sources\n"
    "\n"
    "### src_001 — Associated Press, wire, Tier 1, originating\n"
    "**Author:** A Reporter\n"
    "**URL:** https://apnews.com/article/example\n"
    "\n"
    "---\n"
    "\n"
    + BOILERPLATE
    + "\n"
)


class _FakeCollection:
    """Minimal chromadb-collection stand-in (add/get/delete/count)."""

    def __init__(self):
        self.store = {}
        self.add_calls = 0

    def add(self, ids, documents, metadatas, embeddings=None):
        self.add_calls += 1
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


# ---------------------------------------------------------------------------
# msi_body_filter unit tests
# ---------------------------------------------------------------------------


class TestMsiBodyFilter(unittest.TestCase):

    def test_keeps_summary_and_prose_drops_apparatus(self):
        out = index_msi_news.msi_body_filter(ARTICLE_BODY)
        # Kept: summary heading, bullets, article prose.
        self.assertIn("## Summary", out)
        self.assertIn("- New York school districts", out)
        self.assertIn("School nutrition programs that feature", out)
        self.assertIn("spillover effect", out)
        # Dropped: Sources, Atomic claims (incl. nested ###), boilerplate.
        self.assertNotIn("## Sources", out)
        self.assertNotIn("src_001", out)
        self.assertNotIn("## Atomic claims", out)
        self.assertNotIn("c_001", out)
        self.assertNotIn("generated algorithmically", out)
        # The rule preceding the boilerplate goes with it.
        self.assertFalse(out.rstrip().endswith("---"))

    def test_boilerplate_without_preceding_rule(self):
        body = "## Summary\n\nProse here.\n\n" + BOILERPLATE + "\n"
        out = index_msi_news.msi_body_filter(body)
        self.assertIn("Prose here.", out)
        self.assertNotIn("generated algorithmically", out)

    def test_boilerplate_with_rule(self):
        body = "## Summary\n\nProse here.\n\n---\n\n" + BOILERPLATE + "\n"
        out = index_msi_news.msi_body_filter(body)
        self.assertIn("Prose here.", out)
        self.assertNotIn("generated algorithmically", out)
        self.assertNotIn("---", out)

    def test_boilerplate_corpus_variants(self):
        # The corpus carries non-canonical disclosure paragraphs: plain
        # (no italics), underscore italics, and "AI disclosure:" lead-ins.
        variants = [
            "This article was generated algorithmically by Main Street "
            "Independent's News Article Generator framework from the public "
            "sources listed under sources. Specification: /methodology. "
            "Human review: not_triggered.",
            "_This article was generated algorithmically by Main Street "
            "Independent. [Methodology](/methodology)._",
            "*AI disclosure: This article was generated algorithmically "
            "from the public sources listed above.*",
            "**AI Disclosure:** This article was generated algorithmically.",
        ]
        for v in variants:
            body = "## Summary\n\nProse here.\n\n" + v + "\n"
            out = index_msi_news.msi_body_filter(body)
            self.assertIn("Prose here.", out)
            self.assertNotIn("generated algorithmically", out,
                             msg=f"variant not stripped: {v[:40]}...")

    def test_trailing_license_paragraph_stripped_with_notice(self):
        body = (
            "## Summary\n\nProse here.\n\n"
            "AI disclosure: This article was generated algorithmically "
            "by Main Street Independent.\n\n"
            "License: CC0 — https://creativecommons.org/publicdomain/zero/1.0/\n"
        )
        out = index_msi_news.msi_body_filter(body)
        self.assertIn("Prose here.", out)
        self.assertNotIn("generated algorithmically", out)
        self.assertNotIn("CC0", out)

    def test_lone_license_mention_kept_without_notice(self):
        # A license-ish final paragraph with NO generation notice above it
        # is real content — never stripped on its own.
        body = ("## Summary\n\nThe artwork enters the public domain "
                "under CC0 next year.\n")
        out = index_msi_news.msi_body_filter(body)
        self.assertIn("public domain", out)

    def test_disclosure_h2_section_stripped(self):
        body = (
            "## Summary\n\nProse here.\n\n"
            "## AI disclosure / CC0\n"
            "This article was generated algorithmically by Main Street "
            "Independent.\nLicensed CC0.\n"
        )
        out = index_msi_news.msi_body_filter(body)
        self.assertIn("Prose here.", out)
        self.assertNotIn("generated algorithmically", out)

    def test_non_trailing_boilerplate_left_alone(self):
        body = ("## Summary\n\n" + BOILERPLATE + "\n\n"
                "Real content continues after the notice.\n")
        out = index_msi_news._strip_trailing_boilerplate(body)
        self.assertIn("generated algorithmically", out)
        self.assertIn("Real content continues", out)

    def test_internal_rule_kept(self):
        body = "## Summary\n\nBefore.\n\n---\n\nAfter.\n\n" + BOILERPLATE
        out = index_msi_news.msi_body_filter(body)
        # The mid-article rule separates real content — it stays.
        self.assertIn("---", out)
        self.assertIn("After.", out)

    def test_no_boilerplate_is_identity(self):
        body = "## Summary\n\nJust an article.\n"
        self.assertEqual(index_msi_news.msi_body_filter(body),
                         body.strip())

    def test_marker_match_is_case_insensitive(self):
        # Real corpus variant: capital "Generated", rule joined into the
        # same paragraph (no blank line between "---" and the notice).
        body = (
            "## Summary\n\nProse here.\n\n"
            "---\n"
            "Source: Associated Press. AI disclosure: Generated "
            "algorithmically by Main Street Independent from the public "
            "source(s) listed above. CC0 license applies.\n"
        )
        out = index_msi_news.msi_body_filter(body)
        self.assertIn("Prose here.", out)
        self.assertNotIn("algorithmically", out)
        self.assertNotIn("---", out)

    def test_crlf_body_keeps_content_strips_notice(self):
        # CRLF line endings must not defeat the paragraph-boundary regex:
        # before the fix, a CRLF file had NO boundaries, the whole body
        # became the "final paragraph", and the notice wiped everything.
        body = ("## Summary\r\n\r\nProse here.\r\n\r\n---\r\n\r\n"
                + BOILERPLATE.replace("\n", "\r\n") + "\r\n")
        out = index_msi_news.msi_body_filter(body)
        self.assertIn("Prose here.", out)
        self.assertNotIn("generated algorithmically", out)

    def test_crlf_without_notice_is_untouched(self):
        body = "## Summary\r\n\r\nJust an article.\r\n"
        out = index_msi_news.msi_body_filter(body)
        self.assertIn("Just an article.", out)


# ---------------------------------------------------------------------------
# index_msi_news integration — filter reaches storage + embedding,
# forced re-index re-stores, progress prints every 100 files.
# ---------------------------------------------------------------------------


class TestIndexMsiNews(unittest.TestCase):

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

    def _write_article(self, name, body=ARTICLE_BODY):
        path = os.path.join(self.tmpdir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write("---\nheadline: Test article\nai_generated: true\n---\n\n")
            f.write(body)
        return path

    def test_filter_applied_to_stored_doc_and_embed_text(self):
        path = self._write_article("2026-01-01-test-article.md")
        with contextlib.redirect_stdout(io.StringIO()):
            stats = index_msi_news.index_msi_news([path], collection=self.col)
        self.assertEqual(stats, {"indexed": 1, "skipped": 0, "errors": 0})

        stored = self.col.store[os.path.abspath(path)]["document"]
        self.assertIn("School nutrition programs that feature", stored)
        self.assertNotIn("## Sources", stored)
        self.assertNotIn("## Atomic claims", stored)
        self.assertNotIn("generated algorithmically", stored)

        self.assertEqual(len(self.embed_texts), 1)
        embed = self.embed_texts[0]
        self.assertIn("School nutrition programs that feature", embed)
        self.assertNotIn("## Sources", embed)
        self.assertNotIn("## Atomic claims", embed)
        self.assertNotIn("generated algorithmically", embed)

    def test_meta_overrides_still_forced(self):
        path = self._write_article("2026-01-02-another-article.md")
        with contextlib.redirect_stdout(io.StringIO()):
            index_msi_news.index_msi_news([path], collection=self.col)
        meta = self.col.store[os.path.abspath(path)]["metadata"]
        self.assertEqual(meta["type"], "resource")
        self.assertEqual(meta["nexus"], "main-street-independent")
        self.assertEqual(meta["tags"],
                         ["news", "main-street-independent", "msi-news"])
        self.assertTrue(meta["tag_msi-news"])

    def test_force_reindexes_already_indexed_files(self):
        path = self._write_article("2026-01-03-force-me.md")
        with contextlib.redirect_stdout(io.StringIO()):
            index_msi_news.index_msi_news([path], collection=self.col)
            stats = index_msi_news.index_msi_news([path], collection=self.col)
        # Without force the second pass skips.
        self.assertEqual(stats, {"indexed": 0, "skipped": 1, "errors": 0})
        with contextlib.redirect_stdout(io.StringIO()):
            stats = index_msi_news.index_msi_news(
                [path], force=True, collection=self.col)
        # With force it re-embeds and re-stores.
        self.assertEqual(stats, {"indexed": 1, "skipped": 0, "errors": 0})
        self.assertEqual(len(self.embed_texts), 2)
        self.assertEqual(self.col.add_calls, 2)

    def test_apparatus_only_article_indexes_unfiltered_body(self):
        # Some corpus files are apparatus-only: after section-strip +
        # boilerplate-strip the body is empty. index_file must fall back
        # to the unfiltered body — never store an empty document.
        body = (
            "## Atomic claims\n"
            "\n"
            "### c_001\n"
            "> Finland arrested two crew members over cable damage.\n"
            "\n"
            "## Sources\n"
            "\n"
            "### src_001 — Associated Press, wire, Tier 1, originating\n"
            "**URL:** https://apnews.com/article/example\n"
            "\n"
            "---\n"
            "\n"
            + BOILERPLATE
            + "\n"
        )
        self.assertEqual(index_msi_news.msi_body_filter(body), "")
        path = self._write_article("2026-01-05-apparatus-only.md", body)
        with contextlib.redirect_stdout(io.StringIO()):
            stats = index_msi_news.index_msi_news([path], collection=self.col)
        self.assertEqual(stats, {"indexed": 1, "skipped": 0, "errors": 0})
        stored = self.col.store[os.path.abspath(path)]["document"]
        self.assertNotEqual(stored.strip(), "")
        # The quoted claim (real article content) is retrievable again.
        self.assertIn("Finland arrested two crew members", stored)
        self.assertIn("Finland arrested two crew members",
                      self.embed_texts[0])

    def test_progress_printed_every_100_files(self):
        paths = [
            self._write_article(f"2026-01-04-batch-{i:03d}.md")
            for i in range(250)
        ]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            stats = index_msi_news.index_msi_news(
                paths, force=True, collection=self.col)
        self.assertEqual(stats["indexed"], 250)
        out = buf.getvalue()
        self.assertIn("[100/250]", out)
        self.assertIn("[200/250]", out)
        self.assertIn("[250/250]", out)
        # No noisy per-file lines from index_file.
        self.assertNotIn("  + 2026-01-04-batch", out)


if __name__ == "__main__":
    unittest.main()
