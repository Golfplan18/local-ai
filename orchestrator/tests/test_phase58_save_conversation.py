"""Tests for Phase 5.8 changes to server.py::_save_conversation.

Per Reference — Conversational RAG for Persistent AI Memory §2 (rev
2026-04-30) and Reference — Ora YAML Schema §12 (rev 3, 2026-04-30):

  (1) Chunk file YAML follows the canonical Schema §12 conversation
      chunk template — only nexus, type: chat, tags, dates. Bespoke
      fields (session_id, model_id, source_file, etc.) move to
      ChromaDB metadata.
  (2) ChromaDB metadata expands to ~22 fields (temporal, identity,
      structure, content, source, thread, pipeline). Nothing is
      deferred at save time except total_turns and is_last_turn,
      which finalize at conversation close-out.

V3 stealth/private semantics preserved (tag remains a singular field
for legacy dispatch; tag_private boolean added per Phase 5.3).
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

# Path setup: server.py lives in ~/ora/server/, which has no __init__.py.
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SERVER_DIR = os.path.join(_REPO, "server")
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

import server  # noqa: E402

from orchestrator.embedding import install_test_stub  # noqa: E402
install_test_stub()


# ---------------------------------------------------------------------------
# Helper-function unit tests
# ---------------------------------------------------------------------------


class TestExtractEntities(unittest.TestCase):
    """Capitalized noun-phrase extraction (approximate NER)."""

    def test_simple_proper_nouns(self):
        text = "Python and FastAPI work well together."
        entities = server._extract_entities(text)
        self.assertIn("Python", entities)
        self.assertIn("FastAPI", entities)

    def test_multi_word_phrases(self):
        text = "We discussed the Hard Problem of Consciousness."
        entities = server._extract_entities(text)
        # Multi-word capitalized sequence should match.
        self.assertTrue(any("Hard Problem" in e for e in entities))

    def test_empty_text(self):
        self.assertEqual(server._extract_entities(""), [])
        self.assertEqual(server._extract_entities(None), [])

    def test_lowercase_only_returns_empty(self):
        self.assertEqual(server._extract_entities("just lowercase words here"), [])

    def test_dedupe_case_insensitive(self):
        text = "Python is great. Python rocks. python is a snake."
        entities = server._extract_entities(text)
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0], "Python")

    def test_max_n_cap(self):
        # Use sentences so each capitalized word is a separate entity
        # (consecutive caps would merge into one multi-word phrase).
        text = ". ".join(f"Apple{i}" for i in range(50))
        entities = server._extract_entities(text, max_n=5)
        self.assertEqual(len(entities), 5)


class TestExtractKeywords(unittest.TestCase):
    """Heuristic keyword extraction with stop-word filtering."""

    def test_basic_extraction(self):
        text = "The user asked about pipeline architecture and ranking."
        kws = server._extract_keywords(text)
        self.assertIn("pipeline", kws)
        self.assertIn("architecture", kws)
        self.assertIn("ranking", kws)

    def test_stop_words_filtered(self):
        kws = server._extract_keywords("the and or but if while because")
        self.assertEqual(kws, [])

    def test_dedupe_preserves_order(self):
        kws = server._extract_keywords("alpha beta alpha gamma beta")
        self.assertEqual(kws, ["alpha", "beta", "gamma"])

    def test_max_n_cap(self):
        # Pure alpha words (the keyword regex requires 3+ alphabetic chars).
        text = " ".join("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda".split())
        kws = server._extract_keywords(text, max_n=5)
        self.assertEqual(len(kws), 5)


class TestComputePairHash(unittest.TestCase):
    def test_deterministic(self):
        h1 = server._compute_pair_hash("hello", "world")
        h2 = server._compute_pair_hash("hello", "world")
        self.assertEqual(h1, h2)

    def test_different_inputs_different_hashes(self):
        h1 = server._compute_pair_hash("hello", "world")
        h2 = server._compute_pair_hash("hello", "earth")
        self.assertNotEqual(h1, h2)

    def test_pair_separator_matters(self):
        # "AB" "C" should differ from "A" "BC"
        h1 = server._compute_pair_hash("AB", "C")
        h2 = server._compute_pair_hash("A", "BC")
        self.assertNotEqual(h1, h2)

    def test_returns_hex_string(self):
        h = server._compute_pair_hash("x", "y")
        self.assertTrue(all(c in "0123456789abcdef" for c in h))


class TestV3TagMapping(unittest.TestCase):
    """V3 stealth/private semantics → Schema §3 tags + Phase 5.3 booleans."""

    def test_empty_tag(self):
        tags, booleans = server._v3_tag_to_schema_tags("")
        self.assertEqual(tags, [])
        self.assertFalse(booleans["tag_private"])
        self.assertFalse(booleans["tag_archived"])
        self.assertFalse(booleans["tag_incubating"])

    def test_private_tag(self):
        tags, booleans = server._v3_tag_to_schema_tags("private")
        self.assertEqual(tags, ["private"])
        self.assertTrue(booleans["tag_private"])

    def test_stealth_tag_no_content_tag(self):
        # Per Q2: stealth is a conversation-level mode, not a content tag.
        # Schema §3 doesn't include `stealth` in its controlled vocabulary.
        tags, booleans = server._v3_tag_to_schema_tags("stealth")
        self.assertEqual(tags, [])
        self.assertFalse(booleans["tag_private"])

    def test_invalid_tag_normalizes_to_empty(self):
        tags, booleans = server._v3_tag_to_schema_tags("nonsense")
        self.assertEqual(tags, [])
        self.assertFalse(any(booleans.values()))


# ---------------------------------------------------------------------------
# End-to-end chunk write — both representations in lockstep
# ---------------------------------------------------------------------------


class TestSaveConversationLockstep(unittest.TestCase):
    """A single _save_conversation call writes both:
      (1) chunk file with Schema §12 YAML
      (2) ChromaDB record with full ~22-field metadata
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.raw_dir = os.path.join(self.tmpdir, "raw")
        self.conv_dir = os.path.join(self.tmpdir, "conversations")
        self.chroma_dir = os.path.join(self.tmpdir, "chromadb")
        os.makedirs(self.raw_dir)
        os.makedirs(self.conv_dir)

        # Patch module-level paths and dependencies.
        self._patches = [
            ("CONVERSATIONS_RAW", self.raw_dir),
            ("CONVERSATIONS_DIR", self.conv_dir),
        ]
        self._originals = {}
        for name, value in self._patches:
            self._originals[name] = getattr(server, name)
            setattr(server, name, value)

        # Stub load_config so the chunk routes to our temp chromadb.
        self._original_load = server.load_config
        server.load_config = lambda: {"chromadb_path": self.chroma_dir}

        # Stub get_endpoint so model_id is predictable.
        self._original_endpoint = server.get_endpoint
        server.get_endpoint = lambda cfg: {"name": "test-model"}

        # Stub the metadata generator so we don't hit a sidebar model.
        self._original_meta = server._generate_chunk_metadata
        server._generate_chunk_metadata = (
            lambda u, a, d, p, m, n: ("Stub context header.", ["topic-x", "topic-y"])
        )

        # Stub the embedder so we don't hit Ollama.
        self._original_embed = server._nomic_embed
        server._nomic_embed = lambda text: None  # let chroma use default

        # Reset session state.
        self._original_sess = server._session_data
        server._session_data = {}

    def tearDown(self):
        for name, _ in self._patches:
            setattr(server, name, self._originals[name])
        server.load_config = self._original_load
        server.get_endpoint = self._original_endpoint
        server._generate_chunk_metadata = self._original_meta
        server._nomic_embed = self._original_embed
        server._session_data = self._original_sess
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _save(self, user, assistant, panel="conv-test-001",
              is_new=True, tag=""):
        server._save_conversation(user, assistant, panel, is_new, tag=tag)

    def _read_chunk_file(self):
        # The most recent .md file in CONVERSATIONS_DIR.
        files = sorted(
            (f for f in os.listdir(self.conv_dir) if f.endswith(".md")),
            key=lambda f: os.path.getmtime(os.path.join(self.conv_dir, f)),
        )
        if not files:
            return None
        return open(os.path.join(self.conv_dir, files[-1]),
                    encoding="utf-8").read()

    def _read_chroma_meta(self, conversation_id):
        import chromadb
        client = chromadb.PersistentClient(path=self.chroma_dir)
        col = client.get_collection("conversations")
        return col.get(where={"conversation_id": conversation_id})

    def test_chunk_yaml_has_schema12_keys_only(self):
        self._save("Hello, what is consciousness?", "Consciousness is...")
        body = self._read_chunk_file()
        self.assertIsNotNone(body)
        # YAML opens with --- and includes the canonical chunk template keys.
        self.assertTrue(body.startswith("---\n"))
        self.assertIn("type: chat", body)
        self.assertIn("date created:", body)
        self.assertIn("date modified:", body)
        # Bespoke fields no longer in YAML.
        self.assertNotIn("source_file:", body)
        self.assertNotIn("source_platform:", body)
        self.assertNotIn("model_used:", body)
        self.assertNotIn("session_id:", body)
        self.assertNotIn("topics:", body)
        self.assertNotIn("chunk_id:", body)

    def test_chunk_yaml_uses_dashes_for_dates(self):
        self._save("Hello", "Hi there")
        body = self._read_chunk_file()
        # Pick out the date created line and check format.
        m = [ln for ln in body.splitlines() if ln.startswith("date created:")]
        self.assertEqual(len(m), 1)
        # YYYY-MM-DD shape (dashes, not slashes).
        self.assertRegex(m[0], r"date created: \d{4}-\d{2}-\d{2}")

    def test_private_tag_appears_in_yaml_tags_list(self):
        self._save("Hello", "Hi", tag="private")
        body = self._read_chunk_file()
        self.assertIn("tags:\n  - private", body)

    def test_stealth_tag_does_not_appear_in_yaml_tags(self):
        # Stealth is a conversation-level mode, not a content tag.
        self._save("Hello", "Hi", tag="stealth")
        body = self._read_chunk_file()
        # `tags:` is present (Schema §3 core property) but stealth should
        # not appear as a tag value.
        self.assertNotIn("- stealth", body)

    def test_chromadb_has_full_metadata_schema(self):
        self._save("Hello, what is Python?", "Python is a programming language.")
        result = self._read_chroma_meta("conv-test-001")
        self.assertEqual(len(result["ids"]), 1)
        meta = result["metadatas"][0]
        # Conv RAG §2 fields
        for field in (
            "timestamp_utc", "date", "year", "month",
            "conversation_id", "conversation_title", "session_id",
            "turn_index", "total_turns", "chunk_type",
            "is_first_turn", "is_last_turn",
            "topic_primary", "turn_summary",
            "source_platform", "model_id",
            "thread_id",
            "obsidian_path", "file_hash",
        ):
            self.assertIn(field, meta, f"missing metadata field: {field}")
        # type field is what knowledge_search type_filter checks against.
        self.assertEqual(meta["type"], "chat")
        # Phase 5.3 boolean filter extracts.
        self.assertIn("tag_archived", meta)
        self.assertIn("tag_incubating", meta)
        self.assertIn("tag_private", meta)

    def test_chromadb_first_turn_marked_correctly(self):
        self._save("Turn 1", "Response 1")
        result = self._read_chroma_meta("conv-test-001")
        meta = result["metadatas"][0]
        self.assertTrue(meta["is_first_turn"])
        self.assertFalse(meta["is_last_turn"])
        self.assertEqual(meta["turn_index"], 1)
        self.assertEqual(meta["total_turns"], 1)

    def test_chromadb_subsequent_turns_increment(self):
        self._save("Turn 1", "Response 1")
        self._save("Turn 2", "Response 2", is_new=False)
        self._save("Turn 3", "Response 3", is_new=False)
        result = self._read_chroma_meta("conv-test-001")
        # Three chunks, turn_index 1/2/3, total_turns 3 each (initial value
        # at save = current pair_num; close-out finalize updates to final).
        ids = result["ids"]
        metas = result["metadatas"]
        self.assertEqual(len(ids), 3)
        turn_indices = sorted(m["turn_index"] for m in metas)
        self.assertEqual(turn_indices, [1, 2, 3])
        # is_last_turn defaults False for all (close-out updates).
        for m in metas:
            self.assertFalse(m["is_last_turn"])

    def test_chromadb_topic_primary_drives_thread_id(self):
        # Two turns same topic → same thread_id; third turn different
        # topic → new thread_id.
        server._generate_chunk_metadata = (
            lambda u, a, d, p, m, n: ("ctx", ["consciousness"])
        )
        self._save("Q1", "A1")
        self._save("Q2", "A2", is_new=False)
        server._generate_chunk_metadata = (
            lambda u, a, d, p, m, n: ("ctx", ["epistemology"])
        )
        self._save("Q3", "A3", is_new=False)

        result = self._read_chroma_meta("conv-test-001")
        thread_ids = sorted(
            (m["turn_index"], m["thread_id"]) for m in result["metadatas"]
        )
        # Turns 1 and 2 share a thread; turn 3 is different.
        self.assertEqual(thread_ids[0][1], thread_ids[1][1])
        self.assertNotEqual(thread_ids[1][1], thread_ids[2][1])

    def test_chromadb_private_tag_sets_boolean(self):
        self._save("Q", "A", tag="private")
        result = self._read_chroma_meta("conv-test-001")
        meta = result["metadatas"][0]
        self.assertTrue(meta["tag_private"])

    def test_chromadb_legacy_v3_compatibility_fields(self):
        # close_conversation reads chunk_path and raw_path from chunk
        # metadata for stealth purges. Phase 5.8 keeps these populated.
        self._save("Q", "A")
        result = self._read_chroma_meta("conv-test-001")
        meta = result["metadatas"][0]
        self.assertIn("chunk_path", meta)
        self.assertIn("raw_path", meta)
        self.assertIn("tag", meta)

    def test_chromadb_file_hash_present(self):
        self._save("Q", "A")
        result = self._read_chroma_meta("conv-test-001")
        meta = result["metadatas"][0]
        self.assertTrue(meta["file_hash"])
        self.assertEqual(len(meta["file_hash"]), 16)  # truncated SHA256

    def test_references_turns_simple_proxy(self):
        self._save("Q1", "A1")
        self._save("Q2", "A2", is_new=False)
        result = self._read_chroma_meta("conv-test-001")
        metas = sorted(result["metadatas"], key=lambda m: m["turn_index"])
        # Turn 1: no references (or empty list dropped from metadata).
        self.assertNotIn("references_turns", metas[0])
        # Turn 2: references turn 1 via simple proxy.
        self.assertIn("references_turns", metas[1])
        self.assertEqual(metas[1]["references_turns"], [1])


if __name__ == "__main__":
    unittest.main()
