"""Tests for orchestrator/tools/knowledge_search.py — Phase 5.3.

Per Reference — Ora YAML Schema §6.5 (rev 3, 2026-04-30) the retrieval
engine applies tag filters before any provenance or decay weighting:

    - `archived`   → always excluded
    - `incubating` → included with explicit status flag in output
    - `private`    → excluded when active conversation is NOT in private
                      mode; included when it IS (one-way visibility,
                      mode-conditioned at retrieval time)

Phase 5.3 also introduces a `type_filter` parameter that maps to a
ChromaDB where-clause filtering on the `type` field — consumed from the
active mode's `## RAG PROFILE → ### type_filter` subsection (Phase 4
mode files).

Transitional note: the `knowledge` collection uses the new
`tag_archived/incubating/private` booleans (Phase 5.2). The
`conversations` collection still uses the legacy V3 `tag` string field
until Phase 5.8. `knowledge_search` dispatches by collection name so
both work during the transition.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
if _ORCHESTRATOR not in sys.path:
    sys.path.insert(0, _ORCHESTRATOR)

from tools import knowledge_search  # noqa: E402

from orchestrator.embedding import install_test_stub  # noqa: E402
install_test_stub()


# ---------------------------------------------------------------------------
# Mode file type_filter extraction
# ---------------------------------------------------------------------------


class TestModeTypeFilterExtraction(unittest.TestCase):
    """The ranker reads the active mode's type_filter from the mode file."""

    def test_typical_mode_file(self):
        mode_text = (
            "## RAG PROFILE\n\n"
            "Some preamble text.\n\n"
            "### type_filter\n\n"
            "Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`\n\n"
            "Rationale: ...\n\n"
            "### Provenance Treatment\n\n..."
        )
        result = knowledge_search._extract_mode_type_filter(mode_text)
        self.assertEqual(result, ["engram", "resource", "incubator"])

    def test_chat_inclusive_mode(self):
        mode_text = (
            "## RAG PROFILE\n\n"
            "### type_filter\n\n"
            "Retrieve only chunks whose `type` is in: `[engram, chat, incubator]`\n"
        )
        result = knowledge_search._extract_mode_type_filter(mode_text)
        self.assertEqual(result, ["engram", "chat", "incubator"])

    def test_single_type(self):
        mode_text = (
            "## RAG PROFILE\n\n"
            "### type_filter\n\n"
            "Retrieve only chunks whose `type` is in: `[framework]`\n"
        )
        result = knowledge_search._extract_mode_type_filter(mode_text)
        self.assertEqual(result, ["framework"])

    def test_missing_section_returns_none(self):
        mode_text = "## SOMETHING ELSE\n\nNo RAG PROFILE here.\n"
        result = knowledge_search._extract_mode_type_filter(mode_text)
        self.assertIsNone(result)

    def test_malformed_section_returns_none(self):
        # Section heading present but no bracketed list.
        mode_text = (
            "## RAG PROFILE\n\n### type_filter\n\nNo list here, just prose.\n"
        )
        result = knowledge_search._extract_mode_type_filter(mode_text)
        self.assertIsNone(result)

    def test_empty_string_returns_none(self):
        result = knowledge_search._extract_mode_type_filter("")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Where-clause composition
# ---------------------------------------------------------------------------


class TestWhereClauseComposition(unittest.TestCase):
    """The where-clause builder produces ChromaDB-valid syntax for the
    knowledge and conversations collections."""

    def test_no_filters_returns_none(self):
        # No filters → no where clause (chromadb.query without where)
        result = knowledge_search._build_where_clause(
            collection="knowledge", type_filter=None, include_private=False,
            include_archived=False,
        )
        # archived is always excluded by default → at least one filter
        self.assertIsNotNone(result)

    def test_knowledge_archived_only(self):
        result = knowledge_search._build_where_clause(
            collection="knowledge", type_filter=None, include_private=True,
            include_archived=False,
        )
        self.assertEqual(result, {"$and": [
            {"tag_archived": {"$ne": True}},
            {"tag_stealth": {"$ne": True}},
        ]})

    def test_knowledge_archived_and_private(self):
        result = knowledge_search._build_where_clause(
            collection="knowledge", type_filter=None, include_private=False,
            include_archived=False,
        )
        # Two filters → $and
        self.assertIn("$and", result)
        clauses = result["$and"]
        self.assertEqual(len(clauses), 3)
        self.assertIn({"tag_archived": {"$ne": True}}, clauses)
        self.assertIn({"tag_private": {"$ne": True}}, clauses)
        self.assertIn({"tag_stealth": {"$ne": True}}, clauses)

    def test_knowledge_full_filter_stack(self):
        result = knowledge_search._build_where_clause(
            collection="knowledge",
            type_filter=["engram", "resource"],
            include_private=False,
            include_archived=False,
        )
        self.assertIn("$and", result)
        clauses = result["$and"]
        self.assertEqual(len(clauses), 4)
        self.assertIn({"type": {"$in": ["engram", "resource"]}}, clauses)
        self.assertIn({"tag_archived": {"$ne": True}}, clauses)
        self.assertIn({"tag_private": {"$ne": True}}, clauses)
        self.assertIn({"tag_stealth": {"$ne": True}}, clauses)

    def test_knowledge_private_included(self):
        # include_private=True: private filter is dropped.
        result = knowledge_search._build_where_clause(
            collection="knowledge", type_filter=None, include_private=True,
            include_archived=False,
        )
        # Private callers still cannot retrieve Stealth records.
        self.assertEqual(result, {"$and": [
            {"tag_archived": {"$ne": True}},
            {"tag_stealth": {"$ne": True}},
        ]})

    def test_conversations_uses_legacy_tag_string(self):
        # Transitional: conversations collection has no tag_archived/private
        # booleans yet (Phase 5.8 will add them). Until then, fall back to
        # the V3 legacy tag string.
        result = knowledge_search._build_where_clause(
            collection="conversations", type_filter=None,
            include_private=False, include_archived=False,
        )
        self.assertEqual(result, {"$and": [
            {"tag": {"$ne": "private"}},
            {"tag": {"$ne": "stealth"}},
        ]})

    def test_conversations_include_private(self):
        # include_private=True maps to a Private caller, not Stealth.
        result = knowledge_search._build_where_clause(
            collection="conversations", type_filter=None,
            include_private=True, include_archived=False,
        )
        self.assertEqual(result, {"tag": {"$ne": "stealth"}})

    def test_conversations_explicit_privacy_lattice(self):
        expected = {
            "": {"$and": [
                {"tag": {"$ne": "private"}},
                {"tag": {"$ne": "stealth"}},
            ]},
            "private": {"tag": {"$ne": "stealth"}},
            "stealth": None,
        }
        for privacy_tag, where in expected.items():
            with self.subTest(privacy_tag=privacy_tag):
                self.assertEqual(
                    knowledge_search._build_where_clause(
                        collection="conversations", type_filter=None,
                        include_private=False, include_archived=False,
                        privacy_tag=privacy_tag,
                    ),
                    where,
                )


# ---------------------------------------------------------------------------
# End-to-end search behavior on knowledge collection
# ---------------------------------------------------------------------------


class TestKnowledgeSearchEndToEnd(unittest.TestCase):
    """Search the new-shape (Phase 5.2) knowledge collection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.chromadb_path = os.path.join(self.tmpdir, "chromadb")
        self._original = knowledge_search.CHROMADB_PATH
        knowledge_search.CHROMADB_PATH = self.chromadb_path

        # Seed a knowledge collection with mixed-type, mixed-tag chunks.
        # Let chromadb auto-embed (matches production behavior — production
        # collection is 384-dim from chromadb's default sentence-transformers
        # fallback when nomic isn't reached).
        import chromadb
        from orchestrator.embedding import get_or_create_collection as _bind_ef
        client = chromadb.PersistentClient(path=self.chromadb_path)
        col = _bind_ef(client, "knowledge")

        col.add(
            ids=["k_engram_active", "k_engram_archived",
                 "k_resource", "k_chat",
                 "k_engram_incubating", "k_engram_private",
                 "k_engram_legacy_stealth"],
            documents=[
                "Engram about consciousness — vetted user position.",
                "Old engram superseded by new framework.",
                "Resource chunk about epistemology from a research paper.",
                "Conversation chunk about consciousness from last week.",
                "Engram still being curated about cosmology.",
                "Private engram about a sensitive topic.",
                "Legacy stealth engram about a sensitive topic.",
            ],
            metadatas=[
                {"type": "engram",   "source": "engram_active.md",
                 "tag_archived": False, "tag_incubating": False, "tag_private": False},
                {"type": "engram",   "source": "engram_archived.md",
                 "tag_archived": True,  "tag_incubating": False, "tag_private": False},
                {"type": "resource", "source": "resource.md",
                 "tag_archived": False, "tag_incubating": False, "tag_private": False},
                {"type": "chat",     "source": "chat.md",
                 "tag_archived": False, "tag_incubating": False, "tag_private": False},
                {"type": "engram",   "source": "engram_incubating.md",
                 "tag_archived": False, "tag_incubating": True,  "tag_private": False},
                {"type": "engram",   "source": "engram_private.md",
                 "tag_archived": False, "tag_incubating": False, "tag_private": True},
                {"type": "engram",   "source": "engram_legacy_stealth.md",
                 "tags": ["atomic", "stealth"],
                 "tag_archived": False, "tag_incubating": False,
                 "tag_private": False},
            ],
        )

    def tearDown(self):
        knowledge_search.CHROMADB_PATH = self._original
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _search(self, **kwargs):
        kwargs.setdefault("query", "consciousness epistemology")
        kwargs.setdefault("collection", "knowledge")
        kwargs.setdefault("n_results", 10)
        return knowledge_search.knowledge_search(**kwargs)

    def test_default_excludes_archived_and_private(self):
        result = self._search()
        self.assertNotIn("engram_archived.md", result)
        self.assertNotIn("engram_private.md", result)
        self.assertNotIn("engram_legacy_stealth.md", result)
        # active, resource, chat, incubating engram should all be retrievable
        self.assertIn("engram_active.md", result)

    def test_type_filter_engram_only(self):
        result = self._search(type_filter=["engram"])
        # All 'engram'-typed chunks except archived and private:
        self.assertIn("engram_active.md", result)
        self.assertIn("engram_incubating.md", result)
        # Non-engram should be absent
        self.assertNotIn("resource.md", result)
        self.assertNotIn("chat.md", result)
        # Archived / private engrams still excluded
        self.assertNotIn("engram_archived.md", result)
        self.assertNotIn("engram_private.md", result)

    def test_type_filter_engram_resource(self):
        result = self._search(type_filter=["engram", "resource"])
        self.assertIn("engram_active.md", result)
        self.assertIn("resource.md", result)
        self.assertNotIn("chat.md", result)

    def test_incubating_chunks_carry_flag(self):
        result = self._search(type_filter=["engram"])
        # The incubating chunk must surface an [incubating] marker.
        self.assertIn("engram_incubating.md", result)
        # Find the line for the incubating chunk and confirm flag is present
        lines = result.splitlines()
        incubating_lines = [ln for ln in lines if "engram_incubating.md" in ln]
        self.assertTrue(any("[incubating]" in ln for ln in incubating_lines))
        # Non-incubating chunks should NOT carry the flag.
        active_lines = [ln for ln in lines if "engram_active.md" in ln]
        self.assertTrue(active_lines)
        self.assertFalse(any("[incubating]" in ln for ln in active_lines))

    def test_include_private_surfaces_private_chunks(self):
        result = self._search(include_private=True)
        self.assertIn("engram_private.md", result)
        self.assertNotIn("engram_legacy_stealth.md", result)

    def test_stealth_caller_includes_legacy_canonical_stealth_tag(self):
        result = self._search(
            query="sensitive topic", privacy_tag="stealth",
        )
        self.assertIn("engram_private.md", result)
        self.assertIn("engram_legacy_stealth.md", result)

    def test_include_private_modifier_in_query(self):
        # Legacy V3 modifier: prefix query with `include:private`.
        result = self._search(query="include:private consciousness")
        self.assertIn("engram_private.md", result)


class TestHybridLexicalRetrieval(unittest.TestCase):
    """The hybrid lane rescues exact/near title-source matches that vector
    search may miss because Chroma stores the title in metadata, not body."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.chromadb_path = os.path.join(self.tmpdir, "chromadb")
        self._original = knowledge_search.CHROMADB_PATH
        knowledge_search.CHROMADB_PATH = self.chromadb_path
        knowledge_search._METADATA_CACHE.clear()

        import chromadb
        from orchestrator.embedding import get_or_create_collection as _bind_ef
        client = chromadb.PersistentClient(path=self.chromadb_path)
        col = _bind_ef(client, "knowledge")
        col.add(
            ids=["target_title_only", "garden_note", "archived_title"],
            documents=[
                "This body discusses sincerity, lying, and bad-faith public argument.",
                "This body discusses Japanese garden design, negative space, and stones.",
                "This archived body should stay out of default retrieval.",
            ],
            metadatas=[
                {"type": "engram",
                 "source": "Book — Disingenuous Bullshitters Book Report.md",
                 "title": "Book — Disingenuous Bullshitters Book Report",
                 "path": "/vault/Book — Disingenuous Bullshitters Book Report.md",
                 "tag_archived": False, "tag_incubating": False, "tag_private": False},
                {"type": "engram", "source": "garden.md", "title": "Garden Note",
                 "path": "/vault/garden.md",
                 "tag_archived": False, "tag_incubating": False, "tag_private": False},
                {"type": "engram", "source": "Archived Hard Problem of Consciousness.md",
                 "title": "Archived Hard Problem of Consciousness",
                 "path": "/vault/Archived Hard Problem of Consciousness.md",
                 "tag_archived": True, "tag_incubating": False, "tag_private": False},
            ],
        )

    def tearDown(self):
        knowledge_search.CHROMADB_PATH = self._original
        knowledge_search._METADATA_CACHE.clear()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_exact_title_match_returns_metadata_only_hit(self):
        chunks = knowledge_search.lexical_search_raw(
            "Disingenuous Bullshitters Book Report",
            collection="knowledge",
            n_results=5,
        )
        sources = [c["metadata"].get("source") for c in chunks]
        self.assertIn("Book — Disingenuous Bullshitters Book Report.md", sources)
        target = next(c for c in chunks if c["metadata"].get("source", "").startswith("Book"))
        self.assertEqual(target["retrieval_source"], "lexical")
        self.assertGreaterEqual(target["lexical_score"], 0.90)

    def test_near_miss_title_match_handles_minor_misspelling(self):
        chunks = knowledge_search.lexical_search_raw(
            "hard problem of conciousness",
            collection="knowledge",
            n_results=5,
            include_archived=True,
        )
        sources = [c["metadata"].get("source") for c in chunks]
        self.assertIn("Archived Hard Problem of Consciousness.md", sources)

    def test_archived_filter_applies_to_lexical_lane(self):
        chunks = knowledge_search.lexical_search_raw(
            "hard problem of consciousness",
            collection="knowledge",
            n_results=5,
        )
        sources = [c["metadata"].get("source") for c in chunks]
        self.assertNotIn("Archived Hard Problem of Consciousness.md", sources)

    def test_hybrid_marks_semantic_and_lexical_sources(self):
        chunks = knowledge_search.knowledge_search_hybrid_raw(
            "Disingenuous Bullshitters Book Report",
            collection="knowledge",
            n_results=1,
            lexical_n_results=5,
        )
        target = next(
            c for c in chunks
            if c["metadata"].get("source") == "Book — Disingenuous Bullshitters Book Report.md"
        )
        self.assertIn("lexical", target.get("retrieval_source", ""))

    def test_declared_atomic_path_cannot_reenter_semantic_or_lexical_results(self):
        excluded = "/vault/Book — Disingenuous Bullshitters Book Report.md"
        semantic = knowledge_search.knowledge_search_raw(
            "Disingenuous Bullshitters Book Report",
            collection="knowledge",
            n_results=5,
            excluded_paths=[excluded],
        )
        hybrid = knowledge_search.knowledge_search_hybrid_raw(
            "Disingenuous Bullshitters Book Report",
            collection="knowledge",
            n_results=5,
            lexical_n_results=5,
            excluded_paths=[excluded],
        )
        formatted = knowledge_search.knowledge_search(
            "Disingenuous Bullshitters Book Report",
            collection="knowledge",
            n_results=5,
            excluded_paths=[excluded],
        )
        for chunks in (semantic, hybrid):
            self.assertNotIn(
                excluded,
                {chunk["metadata"].get("path") for chunk in chunks},
            )
        self.assertNotIn("Disingenuous Bullshitters", formatted)


# ---------------------------------------------------------------------------
# End-to-end behavior on conversations collection (transitional)
# ---------------------------------------------------------------------------


class TestConversationsLegacyFilter(unittest.TestCase):
    """Conversations collection still uses V3 legacy `tag` string field
    until Phase 5.8. knowledge_search must dispatch correctly so existing
    chunks remain filterable."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.chromadb_path = os.path.join(self.tmpdir, "chromadb")
        self._original = knowledge_search.CHROMADB_PATH
        knowledge_search.CHROMADB_PATH = self.chromadb_path

        import chromadb
        from orchestrator.embedding import get_or_create_collection as _bind_ef
        client = chromadb.PersistentClient(path=self.chromadb_path)
        col = _bind_ef(client, "conversations")

        col.add(
            ids=["c_normal", "c_private", "c_stealth"],
            documents=[
                "Normal conversation about pipelines.",
                "Private conversation about a sensitive matter.",
                "Stealth conversation, transient.",
            ],
            metadatas=[
                {"source": "conv_normal.md", "conversation_id": "normal",
                 "tag": ""},
                {"source": "conv_private.md", "conversation_id": "private",
                 "tag": "private"},
                {"source": "conv_stealth.md", "conversation_id": "stealth",
                 "tag": "stealth"},
            ],
        )

    def tearDown(self):
        knowledge_search.CHROMADB_PATH = self._original
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_standard_excludes_private_and_stealth_chunks(self):
        result = knowledge_search.knowledge_search(
            "pipelines", collection="conversations", n_results=10,
        )
        self.assertIn("conv_normal.md", result)
        self.assertNotIn("conv_private.md", result)
        self.assertNotIn("conv_stealth.md", result)

    def test_include_private_surfaces_private_chunks(self):
        result = knowledge_search.knowledge_search(
            "pipelines", collection="conversations", n_results=10,
            include_private=True,
        )
        self.assertIn("conv_private.md", result)
        self.assertNotIn("conv_stealth.md", result)

    def test_stealth_caller_surfaces_all_privacy_levels(self):
        result = knowledge_search.knowledge_search(
            "pipelines", collection="conversations", n_results=10,
            privacy_tag="stealth",
        )
        self.assertIn("conv_normal.md", result)
        self.assertIn("conv_private.md", result)
        self.assertIn("conv_stealth.md", result)

    def test_explicit_dialogue_identity_is_excluded_from_raw_and_formatted_results(self):
        raw = knowledge_search.knowledge_search_raw(
            "pipelines", collection="conversations", n_results=10,
            excluded_conversation_ids=["NORMAL"],
        )
        formatted = knowledge_search.knowledge_search(
            "pipelines", collection="conversations", n_results=10,
            excluded_conversation_ids=["normal"],
        )
        self.assertNotIn(
            "normal",
            {chunk["metadata"].get("conversation_id") for chunk in raw},
        )
        self.assertNotIn("conv_normal.md", formatted)


class TestLegacyAndConflictingPrivacyMetadata(unittest.TestCase):
    """Missing booleans stay searchable; every truthful privacy signal wins."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.chromadb_path = os.path.join(self.tmpdir, "chromadb")
        self._original = knowledge_search.CHROMADB_PATH
        knowledge_search.CHROMADB_PATH = self.chromadb_path
        knowledge_search._METADATA_CACHE.clear()

        import chromadb
        from orchestrator.embedding import get_or_create_collection
        client = chromadb.PersistentClient(path=self.chromadb_path)
        knowledge = get_or_create_collection(client, "knowledge")
        knowledge.add(
            ids=["legacy-standard", "legacy-private", "legacy-stealth",
                 "legacy-archived", "conflicting-private"],
            documents=["legacy privacy beacon " + name for name in (
                "standard", "private", "stealth", "archived", "conflict",
            )],
            metadatas=[
                {"type": "engram", "source": "legacy-standard.md",
                 "tags": ["atomic"]},
                {"type": "engram", "source": "legacy-private.md",
                 "tags": ["atomic", "private"]},
                {"type": "engram", "source": "legacy-stealth.md",
                 "tags": ["atomic", "stealth"]},
                {"type": "engram", "source": "legacy-archived.md",
                 "tags": ["atomic", "archived"]},
                {"type": "engram", "source": "conflicting-private.md",
                 "tag": "", "tags": ["atomic"], "tag_private": True},
            ],
        )
        conversations = get_or_create_collection(client, "conversations")
        conversations.add(
            ids=["stale-standard", "stale-tags-private", "stale-bool-private",
                 "stale-conflict-stealth", "stale-archived"],
            documents=["conversation privacy beacon " + name for name in (
                "standard", "tags-private", "bool-private",
                "conflict-stealth", "archived",
            )],
            metadatas=[
                {"source": "stale-standard.md", "tag": ""},
                {"source": "stale-tags-private.md", "tag": "",
                 "tags": ["private"]},
                {"source": "stale-bool-private.md", "tag": "",
                 "tag_private": True},
                {"source": "stale-conflict-stealth.md", "tag": "private",
                 "tags": ["private"], "tag_stealth": True},
                {"source": "stale-archived.md", "tag": "",
                 "tags": ["archived"]},
            ],
        )

    def tearDown(self):
        knowledge_search.CHROMADB_PATH = self._original
        knowledge_search._METADATA_CACHE.clear()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @staticmethod
    def _sources(chunks):
        return {chunk["metadata"].get("source") for chunk in chunks}

    def test_knowledge_semantic_lexical_and_tool_use_strictest_privacy(self):
        expected = {
            "": {"legacy-standard.md"},
            "private": {
                "legacy-standard.md", "legacy-private.md",
                "conflicting-private.md",
            },
            "stealth": {
                "legacy-standard.md", "legacy-private.md",
                "legacy-stealth.md", "conflicting-private.md",
            },
        }
        for privacy_tag, allowed in expected.items():
            with self.subTest(privacy_tag=privacy_tag):
                semantic = knowledge_search.knowledge_search_raw(
                    "legacy privacy beacon", "knowledge", n_results=20,
                    privacy_tag=privacy_tag,
                )
                lexical = knowledge_search.lexical_search_raw(
                    "legacy privacy beacon", "knowledge", n_results=20,
                    privacy_tag=privacy_tag,
                )
                formatted = knowledge_search.knowledge_search(
                    "legacy privacy beacon", "knowledge", n_results=20,
                    privacy_tag=privacy_tag,
                )
                self.assertEqual(self._sources(semantic), allowed)
                self.assertEqual(self._sources(lexical), allowed)
                for source in allowed:
                    self.assertIn(source, formatted)
                self.assertNotIn("legacy-archived.md", formatted)

    def test_conversation_semantic_lexical_and_tool_use_strictest_privacy(self):
        expected = {
            "": {"stale-standard.md"},
            "private": {
                "stale-standard.md", "stale-tags-private.md",
                "stale-bool-private.md",
            },
            "stealth": {
                "stale-standard.md", "stale-tags-private.md",
                "stale-bool-private.md", "stale-conflict-stealth.md",
            },
        }
        for privacy_tag, allowed in expected.items():
            with self.subTest(privacy_tag=privacy_tag):
                semantic = knowledge_search.knowledge_search_raw(
                    "conversation privacy beacon", "conversations",
                    n_results=20, privacy_tag=privacy_tag,
                )
                lexical = knowledge_search.lexical_search_raw(
                    "conversation privacy beacon", "conversations",
                    n_results=20, privacy_tag=privacy_tag,
                )
                formatted = knowledge_search.knowledge_search(
                    "conversation privacy beacon", "conversations",
                    n_results=20, privacy_tag=privacy_tag,
                )
                self.assertEqual(self._sources(semantic), allowed)
                self.assertEqual(self._sources(lexical), allowed)
                for source in allowed:
                    self.assertIn(source, formatted)
                self.assertNotIn("stale-archived.md", formatted)


if __name__ == "__main__":
    unittest.main()
