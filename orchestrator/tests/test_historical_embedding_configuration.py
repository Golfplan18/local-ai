"""Configured-embedding coverage for the Phase B/C historical pipelines."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from orchestrator import embedding
from orchestrator import retrieval_config
from orchestrator.historical import phase_b_vault_extraction as phase_b
from orchestrator.historical import phase_c_relationship_extraction as phase_c
from orchestrator.tools import chroma_source_rebuild as chroma_rebuild


def _load_isolated_embedding(config: object = None, *, raw: str | None = None):
    """Load a fresh embedding module against a disposable config directory."""
    with tempfile.TemporaryDirectory(prefix="ora-r13-embedding-") as temp_dir:
        root = Path(temp_dir)
        module_path = root / "orchestrator" / "embedding.py"
        module_path.parent.mkdir(parents=True)
        shutil.copyfile(Path(embedding.__file__), module_path)
        if raw is not None or config is not None:
            config_path = root / "config" / "chromadb.json"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                raw if raw is not None else json.dumps(config),
                encoding="utf-8",
            )
        spec = importlib.util.spec_from_file_location(
            f"_ora_r13_embedding_{id(root)}", module_path
        )
        assert spec is not None and spec.loader is not None
        isolated = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(isolated)
        return isolated


def _valid_chromadb_config() -> dict:
    return {
        "embedder": {
            "profile_id": "ollama:bge-m3",
            "provider": "ollama",
            "model": "bge-m3",
            "dim": 1024,
        },
        "collections": {
            "knowledge": "knowledge",
            "conversations": "conversations",
            "atomics": "atomic_dedup",
            "conversations_incognito": "conversations-incognito",
            "help": "help",
        },
    }


class TestChromaConfigurationIdentity(unittest.TestCase):
    def test_absent_configuration_uses_documented_defaults(self):
        isolated = _load_isolated_embedding()

        self.assertEqual(isolated.EMBEDDING_PROVIDER, "ollama")
        self.assertEqual(isolated.EMBEDDING_MODEL, "bge-m3")
        self.assertEqual(isolated.EMBEDDING_DIM, 1024)
        self.assertEqual(isolated.resolve_collection("knowledge"), "knowledge")

    def test_present_invalid_configuration_refuses_before_collection_access(self):
        valid = _valid_chromadb_config()
        partial = _valid_chromadb_config()
        partial["collections"] = {"knowledge": "knowledge"}
        inconsistent = _valid_chromadb_config()
        inconsistent["embedder"]["profile_id"] = "ollama:another-model"
        cases = {
            "unreadable": {"raw": "{"},
            "non-object": {"config": []},
            "partial": {"config": partial},
            "inconsistent": {"config": inconsistent},
        }

        for label, kwargs in cases.items():
            client = mock.Mock()
            with self.subTest(label=label), self.assertRaisesRegex(
                RuntimeError, "Chroma configuration"
            ):
                isolated = _load_isolated_embedding(**kwargs)
                isolated.get_or_create_collection(client, "knowledge")
            client.get_or_create_collection.assert_not_called()

    def test_known_model_wrong_dimension_refuses_before_collection_access(self):
        wrong_dimension = _valid_chromadb_config()
        wrong_dimension["embedder"]["dim"] = 768
        client = mock.Mock()

        with self.assertRaisesRegex(
            RuntimeError, "expected 1024, found 768"
        ):
            isolated = _load_isolated_embedding(config=wrong_dimension)
            isolated.get_or_create_collection(client, "knowledge")

        client.get_or_create_collection.assert_not_called()

    def test_reranker_writer_seeds_complete_identity_only_when_file_is_absent(self):
        with tempfile.TemporaryDirectory(prefix="ora-r13-retrieval-") as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config" / "chromadb.json"
            reranker = {"id": "none", "provider": "none", "model": ""}
            with mock.patch.object(
                retrieval_config, "CONFIG_DIR", config_path.parent
            ), mock.patch.object(
                retrieval_config, "CHROMADB_CONFIG_PATH", config_path
            ):
                written = retrieval_config.update_active_reranker(reranker)

            validated = embedding.validate_chromadb_config(written, config_path)
            self.assertEqual(validated["embedder"]["profile_id"], "ollama:bge-m3")
            self.assertEqual(
                validated["collections"], _valid_chromadb_config()["collections"]
            )
            self.assertEqual(written["reranker"]["id"], "none")

    def test_settings_writer_preserves_present_invalid_bytes(self):
        invalid_documents = (b"{", b"[]", b'{"reranker": {"id": "none"}}')
        reranker = {"id": "none", "provider": "none", "model": ""}

        for original in invalid_documents:
            with self.subTest(original=original):
                with tempfile.TemporaryDirectory(prefix="ora-r13-retrieval-") as temp_dir:
                    root = Path(temp_dir)
                    config_path = root / "config" / "chromadb.json"
                    config_path.parent.mkdir(parents=True)
                    config_path.write_bytes(original)
                    with mock.patch.object(
                        retrieval_config, "CONFIG_DIR", config_path.parent
                    ), mock.patch.object(
                        retrieval_config, "CHROMADB_CONFIG_PATH", config_path
                    ), self.assertRaisesRegex(RuntimeError, "Chroma configuration"):
                        retrieval_config.update_active_reranker(reranker)

                    self.assertEqual(config_path.read_bytes(), original)

    def test_invalid_collection_names_cannot_overwrite_valid_config(self):
        with tempfile.TemporaryDirectory(prefix="ora-r13-retrieval-") as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config" / "chromadb.json"
            config_path.parent.mkdir(parents=True)
            original = json.dumps(_valid_chromadb_config(), indent=1).encode("utf-8")
            config_path.write_bytes(original)
            profile = retrieval_config.DEFAULT_EMBEDDING_PROFILES[0]

            with mock.patch.object(
                retrieval_config, "CONFIG_DIR", config_path.parent
            ), mock.patch.object(
                retrieval_config, "CHROMADB_CONFIG_PATH", config_path
            ), self.assertRaisesRegex(RuntimeError, "Chroma configuration"):
                retrieval_config.update_active_embedding_profile(
                    profile, collection_names={"knowledge": ""},
                )

            self.assertEqual(config_path.read_bytes(), original)
            self.assertFalse(config_path.with_suffix(".json.tmp").exists())

    def test_promotion_and_rollback_reject_incomplete_identity_before_chroma(self):
        partial = _valid_chromadb_config()
        partial["collections"] = {"conversations": "conversations_old"}
        inconsistent = _valid_chromadb_config()
        inconsistent["collections"]["conversations"] = "conversations_old"
        inconsistent["embedder"]["profile_id"] = "ollama:another-model"

        for operation in ("promotion", "rollback"):
            for label, config in (("partial", partial), ("inconsistent", inconsistent)):
                with self.subTest(operation=operation, label=label):
                    with tempfile.TemporaryDirectory(
                        prefix="ora-r13-rebuild-"
                    ) as temp_dir:
                        root = Path(temp_dir)
                        inactive = root / "inactive"
                        active = root / "active"
                        home = root / "ora-home"
                        for path in (inactive, active, home):
                            path.mkdir()
                        config_path = root / "chromadb.json"
                        original = json.dumps(config, indent=1).encode("utf-8")
                        config_path.write_bytes(original)
                        client_factory = mock.Mock()
                        embedding_factory = mock.Mock()
                        common = {
                            "expected_current_physical": "conversations_old",
                            "active_chromadb_path": active,
                            "config_path": config_path,
                            "ora_home": home,
                            "client_factory": client_factory,
                            "embedding_function_factory": embedding_factory,
                            "ora_active_probe": lambda _home: [],
                        }

                        if operation == "promotion":
                            evidence = {
                                "profile": {
                                    "provider": "ollama",
                                    "model": "bge-m3",
                                    "dimension": 1024,
                                    "physical_collection": "replay_source",
                                },
                                "count": 1,
                                "fingerprint": "0" * 64,
                            }
                            with mock.patch.object(
                                chroma_rebuild, "_replay_evidence", return_value=evidence,
                            ), self.assertRaisesRegex(
                                chroma_rebuild.RebuildError, "Chroma config identity",
                            ):
                                chroma_rebuild.promote_conversation_replay(
                                    inactive_chromadb_path=inactive,
                                    target_physical_collection="conversations_new",
                                    **common,
                                )
                        else:
                            with self.assertRaisesRegex(
                                chroma_rebuild.RebuildError, "Chroma config identity",
                            ):
                                chroma_rebuild.rollback_conversation_mapping(
                                    restore_physical_collection="conversations_older",
                                    **common,
                                )

                        client_factory.assert_not_called()
                        embedding_factory.assert_not_called()
                        self.assertEqual(config_path.read_bytes(), original)


class TestSingleTextEmbeddingAdapter(unittest.TestCase):
    def test_uses_active_factory_and_preserves_configured_dimension(self):
        vector = [0.25] * embedding.EMBEDDING_DIM
        function = mock.Mock(return_value=[vector])

        with mock.patch.object(
            embedding, "get_embedding_function", return_value=function
        ) as factory:
            result = embedding.embed_text("configured input")

        factory.assert_called_once_with()
        function.assert_called_once_with(["configured input"])
        self.assertEqual(result, vector)
        self.assertEqual(len(result), embedding.EMBEDDING_DIM)

    def test_rejects_vector_with_wrong_configured_dimension(self):
        wrong_dim = embedding.EMBEDDING_DIM + 1
        function = mock.Mock(return_value=[[0.0] * wrong_dim])

        with mock.patch.object(
            embedding, "get_embedding_function", return_value=function
        ):
            with self.assertRaisesRegex(RuntimeError, "vector dim"):
                embedding.embed_text("wrong dimension")


class TestHistoricalPipelinesUseConfiguredAdapter(unittest.TestCase):
    def test_phase_b_and_phase_c_delegate_to_shared_adapter(self):
        vector = [0.5] * embedding.EMBEDDING_DIM

        with mock.patch.object(
            embedding, "embed_text", return_value=vector
        ) as configured:
            self.assertEqual(phase_b._embedder_configured("phase b"), vector)
            self.assertEqual(phase_c.embed_configured("phase c"), vector)

        self.assertEqual(
            configured.call_args_list,
            [mock.call("phase b"), mock.call("phase c")],
        )

    def test_phase_c_collection_uses_configured_binding(self):
        client = object()
        persistent_client = mock.Mock(return_value=client)
        chromadb_stub = types.SimpleNamespace(PersistentClient=persistent_client)

        with mock.patch.dict(sys.modules, {"chromadb": chromadb_stub}), mock.patch.object(
            embedding, "get_collection", return_value="collection"
        ) as get_collection:
            result = phase_c._open_collection("/tmp/chroma", "atomic_dedup")

        self.assertEqual(result, "collection")
        persistent_client.assert_called_once_with(path="/tmp/chroma")
        get_collection.assert_called_once_with(client, "atomic_dedup")

    def test_no_hardcoded_legacy_nomic_endpoint_remains(self):
        for module in (phase_b, phase_c):
            source = Path(module.__file__).read_text(encoding="utf-8")
            self.assertNotIn("nomic-embed-text", source)
            self.assertNotIn("/api/embeddings", source)


if __name__ == "__main__":
    unittest.main()
