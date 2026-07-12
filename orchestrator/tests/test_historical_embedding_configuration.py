"""Configured-embedding coverage for the Phase B/C historical pipelines."""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from orchestrator import embedding
from orchestrator.historical import phase_b_vault_extraction as phase_b
from orchestrator.historical import phase_c_relationship_extraction as phase_c


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
