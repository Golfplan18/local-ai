"""Tests for runtime_pipeline's ChromaDB ingest step.

Regression for the one-argument index_file(path) call in
_step7_chromadb_ingest: the TypeError was swallowed by a bare
`except Exception: pass`, so newly staged notes were silently never
indexed. The test runs the real call chain (index_single_file →
index_file) against a fake collection, so an argument mismatch anywhere
in the chain fails the test instead of vanishing.

Hermetic: temp staging dir, fake collection, embedder patched out.
"""
from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
if _ORCHESTRATOR not in sys.path:
    sys.path.insert(0, _ORCHESTRATOR)
_ORA = os.path.dirname(_ORCHESTRATOR)
if _ORA not in sys.path:
    sys.path.insert(0, _ORA)

from orchestrator.tools import knowledge_index  # noqa: E402
from orchestrator.tools import runtime_pipeline as rp  # noqa: E402

STAGED = """---
nexus: null
type: working
tags:
- atomic
subtype: fact
---

# A staged claim about something

- A staged claim about something
- Source: extracted from session abc123
"""


class _FakeCollection:
    """Records add/delete calls; behaves like an empty knowledge collection."""

    def __init__(self):
        self.added_ids = []

    def get(self, ids):
        return {"ids": []}

    def delete(self, ids):
        pass

    def add(self, ids, documents, metadatas, embeddings=None):
        self.added_ids.extend(ids)


class TestStep7ChromadbIngest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.note = os.path.join(self.tmp, "A staged claim about something.md")
        with open(self.note, "w", encoding="utf-8") as f:
            f.write(STAGED)

    def test_staged_note_lands_in_collection(self):
        fake = _FakeCollection()
        custom_chroma = os.path.join(self.tmp, "configured-chroma")
        pipeline = rp.RuntimePipeline({"chromadb_path": custom_chroma})
        with mock.patch.object(rp, "STAGING_DIR", self.tmp), \
             mock.patch.object(knowledge_index, "get_knowledge_collection",
                               return_value=fake) as get_collection, \
             mock.patch.object(knowledge_index, "_nomic_embed",
                               return_value=None):
            pipeline._step7_chromadb_ingest([self.note])

        self.assertIn(os.path.abspath(self.note), fake.added_ids)
        get_collection.assert_called_once_with(os.path.abspath(custom_chroma))

    def test_empty_structured_history_preserves_prompt_output_fallback(self):
        captured = {}

        class FakeEngine:
            def __init__(self, **_kwargs):
                pass

            def extract(self, markdown_text, type_result, **kwargs):
                captured["markdown_text"] = markdown_text
                captured["type_result"] = type_result
                captured.update(kwargs)
                return types.SimpleNamespace(screened=[])

        fake_input = types.SimpleNamespace(
            detect_input_type=lambda _text: {
                "type": "short_document", "details": {},
            },
        )
        fake_extraction = types.SimpleNamespace(ExtractionEngine=FakeEngine)
        fake_quality = types.SimpleNamespace(evaluate_batch=lambda _items: {})
        pipeline = rp.RuntimePipeline(config={"configured": True})
        data = rp.SessionData(
            session_id="fallback-run",
            timestamp="2026-08-10T00:00:00",
            mode="",
            gear=0,
            user_prompt="fallback user",
            final_output="fallback assistant",
            conversation_history=[],
        )

        with mock.patch.dict(sys.modules, {
            "input_detect": fake_input,
            "extraction_engine": fake_extraction,
            "quality_gate": fake_quality,
        }):
            result = pipeline._step4_knowledge_extraction(data)

        self.assertIn("fallback user", captured["markdown_text"])
        self.assertIn("fallback assistant", captured["markdown_text"])
        self.assertIsNone(captured["history_messages"])
        self.assertEqual(result, {
            "extracted": 0, "approved": 0, "review": 0,
            "staged_paths": [],
        })

    def test_explicit_run_paths_do_not_sweep_another_conversation_note(self):
        sibling = os.path.join(self.tmp, "Another conversation.md")
        with open(sibling, "w", encoding="utf-8") as f:
            f.write(STAGED.replace("abc123", "other-conversation"))
        fake = _FakeCollection()
        pipeline = rp.RuntimePipeline()
        with mock.patch.object(rp, "STAGING_DIR", self.tmp), \
             mock.patch.object(knowledge_index, "get_knowledge_collection",
                               return_value=fake), \
             mock.patch.object(knowledge_index, "_nomic_embed",
                               return_value=None):
            pipeline._step7_chromadb_ingest([self.note])

        self.assertEqual(fake.added_ids, [os.path.abspath(self.note)])

    def test_staging_writer_rejects_symlinked_root(self):
        root = os.path.join(self.tmp, "managed-staging")
        outside = os.path.join(self.tmp, "outside")
        os.mkdir(outside)
        os.symlink(outside, root, target_is_directory=True)
        pipeline = rp.RuntimePipeline()
        note = types.SimpleNamespace(
            title="Secret", yaml_frontmatter={}, body="must stay managed",
            subtype=None,
        )

        with mock.patch.object(rp, "STAGING_DIR", root), self.assertRaises(ValueError):
            pipeline._write_note_to_staging(
                note, source_file="conversation-a", private=True,
            )

        self.assertEqual(os.listdir(outside), [])

    def test_staging_writer_rejects_file_symlink_without_touching_target(self):
        staging = os.path.join(self.tmp, "managed-staging")
        os.mkdir(staging)
        outside = os.path.join(self.tmp, "outside.md")
        with open(outside, "w", encoding="utf-8") as stream:
            stream.write("must remain")
        os.symlink(outside, os.path.join(staging, "Secret.md"))
        pipeline = rp.RuntimePipeline()
        note = types.SimpleNamespace(
            title="Secret", yaml_frontmatter={}, body="managed content",
            subtype=None,
        )

        with mock.patch.object(rp, "STAGING_DIR", staging), self.assertRaises(ValueError):
            pipeline._write_note_to_staging(
                note, source_file="conversation-a", private=True,
            )

        with open(outside, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "must remain")

    def test_ingest_skips_symlinked_staging_note(self):
        outside = os.path.join(self.tmp, "outside.md")
        with open(outside, "w", encoding="utf-8") as stream:
            stream.write(STAGED)
        linked = os.path.join(self.tmp, "linked.md")
        os.symlink(outside, linked)
        pipeline = rp.RuntimePipeline()

        with mock.patch.object(rp, "STAGING_DIR", self.tmp):
            self.assertEqual(pipeline._staged_note_paths([linked]), [])

    def test_staging_note_carries_strict_lifecycle_ownership(self):
        staging = os.path.join(self.tmp, "managed-staging")
        pipeline = rp.RuntimePipeline()
        note = types.SimpleNamespace(
            title="Owned", yaml_frontmatter={}, body="managed body",
            subtype=None,
        )
        with mock.patch.object(rp, "STAGING_DIR", staging):
            path = pipeline._write_note_to_staging(
                note, source_file="conversation-a", private=False,
            )
        with open(path, encoding="utf-8") as stream:
            content = stream.read()
        self.assertIn("artifact_kind: conversation_runtime_derivative\n", content)
        self.assertIn("managed_by: ora\n", content)
        self.assertIn('source_file: "conversation-a"\n', content)

    def test_pass2_uses_configured_chroma_and_private_filter(self):
        queries = []
        client_paths = []

        class QueryCollection:
            def query(self, **kwargs):
                queries.append(kwargs)
                return {"ids": [[]], "metadatas": [[]], "distances": [[]]}

        fake_chromadb = types.SimpleNamespace(
            PersistentClient=lambda *, path: client_paths.append(path) or object(),
        )
        configured = os.path.join(self.tmp, "custom-db")
        pipeline = rp.RuntimePipeline({"chromadb_path": configured})
        with mock.patch.object(rp, "STAGING_DIR", self.tmp), \
             mock.patch.dict(sys.modules, {"chromadb": fake_chromadb}), \
             mock.patch("orchestrator.embedding.get_collection",
                        return_value=QueryCollection()):
            pipeline._step12_pass2_relationships(
                [self.note], include_private=False,
            )
            pipeline._step12_pass2_relationships(
                [self.note], include_private=True,
            )

        self.assertEqual(client_paths, [os.path.abspath(configured)] * 2)
        self.assertEqual(queries[0]["where"], {"tag_private": False})
        self.assertIsNone(queries[1]["where"])

    def test_malformed_archived_metadata_has_unknown_policy_state(self):
        self.assertIsNone(rp._metadata_tag_state({
            "tag_archived": "unknown",
        }, "archived"))
        self.assertIsNone(rp._metadata_tag_state({
            "tags": {"archived": True},
        }, "archived"))

    def test_pass2_threads_custom_vault_to_relationship_mutation(self):
        class QueryCollection:
            def query(self, **kwargs):
                return {
                    "ids": [["archived-id"]],
                    "metadatas": [[{"title": "ArchivedTarget"}]],
                    "distances": [[0.1]],
                }

        fake_chromadb = types.SimpleNamespace(
            PersistentClient=lambda *, path: object(),
        )
        custom_vault = os.path.join(self.tmp, "custom-vault")
        pipeline = rp.RuntimePipeline(vault_path=custom_vault)

        with mock.patch.object(rp, "STAGING_DIR", self.tmp), \
             mock.patch.dict(sys.modules, {"chromadb": fake_chromadb}), \
             mock.patch("orchestrator.embedding.get_collection",
                        return_value=QueryCollection()), \
             mock.patch(
                 "orchestrator.tools.relationship_discovery.update_note_relationships"
             ) as update:
            pipeline._step12_pass2_relationships([self.note])

        update.assert_called_once()
        self.assertEqual(update.call_args.kwargs, {
            "vault_path": custom_vault,
            "known_paths": {},
            "return_count": True,
        })

    def test_pass2_batches_candidates_and_counts_only_written_rows(self):
        class QueryCollection:
            def query(self, **kwargs):
                return {
                    "ids": [["one", "two"]],
                    "metadatas": [[{"title": "Target One"}, {"title": "Target Two"}]],
                    "distances": [[0.1, 0.1]],
                }

        fake_chromadb = types.SimpleNamespace(
            PersistentClient=lambda *, path: object(),
        )
        pipeline = rp.RuntimePipeline(vault_path=self.tmp)

        with mock.patch.object(rp, "STAGING_DIR", self.tmp), \
             mock.patch.dict(sys.modules, {"chromadb": fake_chromadb}), \
             mock.patch("orchestrator.embedding.get_collection",
                        return_value=QueryCollection()), \
             mock.patch.object(
                 pipeline, "_classify_relationship_heuristic",
                 return_value="supports",
             ), \
             mock.patch(
                 "orchestrator.tools.relationship_discovery.update_note_relationships",
                 return_value=1,
             ) as update:
            count = pipeline._step12_pass2_relationships([self.note])

        self.assertEqual(count, 1)
        update.assert_called_once()
        self.assertEqual(len(update.call_args.args[1]), 2)

    def test_pass2_missing_canonical_path_fails_open(self):
        class QueryCollection:
            def query(self, **kwargs):
                return {
                    "ids": [["archived"]],
                    "metadatas": [[{
                        "title": "Archived Target",
                        "tag_archived": True,
                    }]],
                    "distances": [[0.1]],
                }

        fake_chromadb = types.SimpleNamespace(
            PersistentClient=lambda *, path: object(),
        )
        pipeline = rp.RuntimePipeline(vault_path=self.tmp)

        with mock.patch.object(rp, "STAGING_DIR", self.tmp), \
             mock.patch.dict(sys.modules, {"chromadb": fake_chromadb}), \
             mock.patch("orchestrator.embedding.get_collection",
                        return_value=QueryCollection()), \
             mock.patch(
                 "orchestrator.tools.relationship_discovery.update_note_relationships",
                 return_value=1,
             ) as update:
            count = pipeline._step12_pass2_relationships([self.note])

        self.assertEqual(count, 1)
        update.assert_called_once()

    def test_pass2_uses_candidate_yaml_over_stale_active_metadata(self):
        target = os.path.join(self.tmp, "Archived Target.md")
        with open(target, "w", encoding="utf-8") as stream:
            stream.write(
                "---\ntype: engram\ntags: [atomic, archived]\n---\n"
                "# Archived Target\n"
            )

        class QueryCollection:
            def query(self, **kwargs):
                return {
                    "ids": [["archived"]],
                    "metadatas": [[{
                        "title": "Archived Target",
                        "path": target,
                        "tag_archived": False,
                    }]],
                    "distances": [[0.1]],
                }

        fake_chromadb = types.SimpleNamespace(
            PersistentClient=lambda *, path: object(),
        )
        pipeline = rp.RuntimePipeline(vault_path=self.tmp)

        with mock.patch.object(rp, "STAGING_DIR", self.tmp), \
             mock.patch.dict(sys.modules, {"chromadb": fake_chromadb}), \
             mock.patch("orchestrator.embedding.get_collection",
                        return_value=QueryCollection()), \
             mock.patch.object(
                 pipeline, "_classify_relationship_heuristic",
                 return_value="supports",
             ):
            count = pipeline._step12_pass2_relationships([self.note])

        self.assertEqual(count, 0)
        with open(self.note, encoding="utf-8") as stream:
            self.assertNotIn("target: Archived Target", stream.read())

    def test_run_threads_only_extracted_paths_through_downstream_steps(self):
        pipeline = rp.RuntimePipeline()
        owned = self.note
        pipeline._step1_session_log = mock.Mock()
        pipeline._step2_conversation_summary = mock.Mock()
        pipeline._step3_continuity_archive = mock.Mock()
        pipeline._step4_knowledge_extraction = mock.Mock(return_value={
            "extracted": 1, "approved": 1, "review": 0,
            "staged_paths": [owned],
        })
        pipeline._step7_chromadb_ingest = mock.Mock()
        pipeline._step8_relationship_extraction = mock.Mock(return_value=0)
        pipeline._step9_glossary_check = mock.Mock(return_value=[])
        pipeline._step10_tag_validation = mock.Mock(return_value=[])
        pipeline._step11_entity_extraction = mock.Mock()
        pipeline._step12_pass2_relationships = mock.Mock(return_value=0)
        pipeline._step13_convergence_check = mock.Mock(return_value=[])
        pipeline._log_result = mock.Mock()

        pipeline.run_sync(rp.SessionData(
            session_id="run-1", timestamp="2026-07-12T00:00:00",
            mode="", gear=0, conversation_id="private-conversation",
            conversation_tag="private", final_output="done",
        ))

        pipeline._step7_chromadb_ingest.assert_called_once_with([owned])
        pipeline._step8_relationship_extraction.assert_called_once_with([owned])
        pipeline._step9_glossary_check.assert_called_once_with([owned])
        pipeline._step10_tag_validation.assert_called_once_with([owned])
        pipeline._step11_entity_extraction.assert_called_once_with([owned])
        pipeline._step12_pass2_relationships.assert_called_once_with(
            [owned], include_private=True,
        )
        pipeline._step13_convergence_check.assert_called_once_with([owned])

    def test_entity_index_writer_is_retired_and_old_cache_removed(self):
        entity_index = os.path.join(self.tmp, "entity-index.json")
        with open(entity_index, "w", encoding="utf-8") as f:
            f.write('{"Sensitive title": ["Private Person"]}')
        pipeline = rp.RuntimePipeline()
        with mock.patch.object(rp, "ENTITY_INDEX_PATH", entity_index):
            pipeline._step11_entity_extraction([self.note])
        self.assertFalse(os.path.exists(entity_index))


if __name__ == "__main__":
    unittest.main()
