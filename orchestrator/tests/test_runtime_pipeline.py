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
        pipeline = rp.RuntimePipeline()
        with mock.patch.object(rp, "STAGING_DIR", self.tmp), \
             mock.patch.object(knowledge_index, "get_knowledge_collection",
                               return_value=fake), \
             mock.patch.object(knowledge_index, "_nomic_embed",
                               return_value=None):
            pipeline._step7_chromadb_ingest()

        self.assertIn(os.path.abspath(self.note), fake.added_ids)


if __name__ == "__main__":
    unittest.main()
