"""Tests for engram_promotion — the staging->vault step that closes the
conversation->engram loop.

Hermetic: uses temp staging/vault dirs and index=False (no ChromaDB / no model).
Locks the transform (type working->engram, subtype folded into tags, canonical
filename, body preserved, staging archived) and the batch helper.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
if _ORCHESTRATOR not in sys.path:
    sys.path.insert(0, _ORCHESTRATOR)
_ORA = os.path.dirname(_ORCHESTRATOR)
if _ORA not in sys.path:
    sys.path.insert(0, _ORA)

from orchestrator.tools import engram_promotion as ep  # noqa: E402

STAGED = """---
nexus: null
type: working
tags:
- atomic
subtype: fact
relationships:
- target: 2026-03-20_some-other-note
  type: parallels
  confidence: 0.86
  source: pass2_runtime
---

# A vetted claim about something

- A vetted claim about something
- Source: extracted from session abc123
"""


class TestStagingNoteToEngram(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.staging = os.path.join(self.tmp, "staging")
        self.vault = os.path.join(self.tmp, "Engrams")
        self.promoted = os.path.join(self.tmp, "promoted")
        os.makedirs(self.staging)
        self.note = os.path.join(self.staging, "A vetted claim about something.md")
        with open(self.note, "w", encoding="utf-8") as f:
            f.write(STAGED)

    def _promote(self, **kw):
        return ep.staging_note_to_engram(
            self.note, vault_engrams=self.vault, promoted_dir=self.promoted,
            index=False, **kw)

    def test_type_becomes_engram(self):
        r = self._promote()
        with open(r["dest"], encoding="utf-8") as f:
            body = f.read()
        self.assertIn("type: engram", body)
        self.assertNotIn("type: working", body)

    def test_subtype_folded_into_tags(self):
        r = self._promote()
        with open(r["dest"], encoding="utf-8") as f:
            body = f.read()
        self.assertIn("- atomic", body)
        self.assertIn("- fact", body)        # subtype folded in
        self.assertNotIn("subtype:", body)   # subtype field removed

    def test_canonical_filename(self):
        r = self._promote()
        name = os.path.basename(r["dest"])
        # YYYY-MM-DD_<slug>.md
        self.assertRegex(name, r"^\d{4}-\d{2}-\d{2}_[a-z0-9-]+\.md$")

    def test_body_and_relationships_preserved(self):
        r = self._promote()
        with open(r["dest"], encoding="utf-8") as f:
            body = f.read()
        self.assertIn("A vetted claim about something", body)
        self.assertIn("extracted from session abc123", body)
        self.assertIn("2026-03-20_some-other-note", body)   # relationship target kept

    def test_provenance_marker(self):
        r = self._promote()
        with open(r["dest"], encoding="utf-8") as f:
            body = f.read()
        self.assertIn("source_platform: ora-local", body)

    def test_staging_archived(self):
        r = self._promote()
        self.assertFalse(os.path.exists(self.note))          # moved out of staging
        self.assertTrue(os.path.exists(
            os.path.join(self.promoted, os.path.basename(self.note))))

    def test_dry_run_writes_nothing(self):
        r = self._promote(dry_run=True)
        self.assertIn("preview", r)
        self.assertFalse(os.path.exists(r["dest"]))          # nothing written
        self.assertTrue(os.path.exists(self.note))           # staging untouched

    def test_collision_suffix(self):
        r1 = self._promote()
        # re-create the staged note and promote again — must not overwrite
        with open(self.note, "w", encoding="utf-8") as f:
            f.write(STAGED)
        r2 = self._promote()
        self.assertNotEqual(r1["dest"], r2["dest"])
        self.assertTrue(os.path.exists(r1["dest"]) and os.path.exists(r2["dest"]))


class TestPromoteStagingDir(unittest.TestCase):
    def test_batch(self):
        tmp = tempfile.mkdtemp()
        staging = os.path.join(tmp, "staging")
        vault = os.path.join(tmp, "Engrams")
        promoted = os.path.join(tmp, "promoted")
        os.makedirs(staging)
        for i in range(3):
            with open(os.path.join(staging, f"claim number {i}.md"), "w", encoding="utf-8") as f:
                f.write(STAGED.replace("A vetted claim about something", f"claim number {i}"))
        res = ep.promote_staging_dir(staging_dir=staging, vault_engrams=vault,
                                     promoted_dir=promoted, index=False)
        self.assertEqual(res["promoted"], 3)
        self.assertEqual(len([f for f in os.listdir(vault) if f.endswith(".md")]), 3)
        self.assertEqual(len([f for f in os.listdir(staging) if f.endswith(".md")]), 0)

    def test_autocommit_commits_and_pushes_promoted_files(self):
        tmp = tempfile.mkdtemp()
        repo = os.path.join(tmp, "vault")
        remote = os.path.join(tmp, "remote.git")
        staging = os.path.join(tmp, "staging")
        vault = os.path.join(repo, "Engrams")
        promoted = os.path.join(tmp, "promoted")
        os.makedirs(repo)
        os.makedirs(staging)
        os.makedirs(vault)

        def git(args, cwd=repo):
            return subprocess.run(
                ["git", *args], cwd=cwd, check=True, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        git(["init"])
        git(["config", "user.email", "ora-test@example.com"])
        git(["config", "user.name", "Ora Test"])
        git(["config", "commit.gpgsign", "false"])
        git(["init", "--bare", remote], cwd=tmp)
        git(["remote", "add", "origin", remote])
        with open(os.path.join(repo, "README.md"), "w", encoding="utf-8") as f:
            f.write("test vault\n")
        git(["add", "README.md"])
        git(["commit", "-m", "Initial"])
        git(["branch", "-M", "main"])
        git(["push", "-u", "origin", "main"])

        with open(os.path.join(staging, "claim.md"), "w", encoding="utf-8") as f:
            f.write(STAGED)

        old = os.environ.get("ORA_RUNTIME_ENGRAM_AUTOCOMMIT")
        os.environ["ORA_RUNTIME_ENGRAM_AUTOCOMMIT"] = "1"
        try:
            res = ep.promote_staging_dir(
                staging_dir=staging, vault_engrams=vault,
                promoted_dir=promoted, index=False)
        finally:
            if old is None:
                os.environ.pop("ORA_RUNTIME_ENGRAM_AUTOCOMMIT", None)
            else:
                os.environ["ORA_RUNTIME_ENGRAM_AUTOCOMMIT"] = old

        self.assertEqual(res["promoted"], 1)
        self.assertTrue(res["autocommit"]["committed"])
        self.assertTrue(res["autocommit"]["pushed"])
        status = git(["status", "--short"]).stdout
        self.assertEqual(status, "")
        latest = git(["log", "--oneline", "-1", "origin/main"]).stdout
        self.assertIn("Add runtime engram", latest)


class _FakeCollection:
    """Records add/delete calls; behaves like an empty knowledge collection."""

    def __init__(self):
        self.added_ids = []
        self.deleted_ids = []

    def get(self, ids):
        return {"ids": []}

    def delete(self, ids):
        self.deleted_ids.extend(ids)

    def add(self, ids, documents, metadatas, embeddings=None):
        self.added_ids.extend(ids)


class TestPromotionIndexing(unittest.TestCase):
    """Regression for the one-argument index_file(dest) call: the TypeError
    was caught and logged, so every promoted engram landed with
    indexed=False and never entered the knowledge collection. The index=True
    path must actually land a record, and must drop the transient
    staging-path entry the session pipeline may have created."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.staging = os.path.join(self.tmp, "staging")
        self.vault = os.path.join(self.tmp, "Engrams")
        self.promoted = os.path.join(self.tmp, "promoted")
        os.makedirs(self.staging)
        self.note = os.path.join(self.staging, "A vetted claim about something.md")
        with open(self.note, "w", encoding="utf-8") as f:
            f.write(STAGED)

    def test_promotion_lands_record_in_collection(self):
        from unittest import mock

        from orchestrator.tools import knowledge_index

        fake = _FakeCollection()
        with mock.patch.object(knowledge_index, "get_knowledge_collection",
                               return_value=fake), \
             mock.patch.object(knowledge_index, "_nomic_embed",
                               return_value=None):
            r = ep.staging_note_to_engram(
                self.note, vault_engrams=self.vault,
                promoted_dir=self.promoted, index=True)

        self.assertTrue(r["indexed"])
        self.assertIn(os.path.abspath(r["dest"]), fake.added_ids)
        # Staging-path entry dropped so the moved file leaves no dangling id.
        self.assertIn(os.path.abspath(self.note), fake.deleted_ids)


class _FakeChunkedCollection:
    """Chromadb stand-in that actually stores records and supports the
    where= metadata filter delete_file_records()/resolve_file_ids() rely
    on — unlike _FakeCollection above, which can't represent a staging note
    stored as multiple '<abspath>#chunk-N' records."""

    def __init__(self):
        self.store = {}

    def seed_chunked(self, path, n_chunks):
        abspath = os.path.abspath(path)
        for i in range(1, n_chunks + 1):
            self.store[f"{abspath}#chunk-{i}"] = {
                "document": f"chunk {i}",
                "metadata": {"path": abspath, "chunk_index": i,
                             "total_chunks": n_chunks},
            }

    def get(self, ids=None, where=None, include=None):
        if where:
            found = [i for i, rec in self.store.items()
                     if all(rec["metadata"].get(k) == v
                            for k, v in where.items())]
        elif ids is None:
            found = list(self.store)
        else:
            found = [i for i in ids if i in self.store]
        return {"ids": found}

    def delete(self, ids):
        for i in ids:
            self.store.pop(i, None)

    def add(self, ids, documents, metadatas, embeddings=None):
        for j, id_ in enumerate(ids):
            self.store[id_] = {"document": documents[j], "metadata": metadatas[j]}


class TestPromotionIndexingChunkedStaging(unittest.TestCase):
    """Regression for engram_promotion.py:254 assuming single-record
    id == abspath. A staging note whose body exceeded one HCP chunk (PR
    #215) is stored as multiple '<abspath>#chunk-N' records; the promotion
    step must drop ALL of them, not just the (never-present) bare-abspath
    id, or orphan chunk records survive the promotion."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.staging = os.path.join(self.tmp, "staging")
        self.vault = os.path.join(self.tmp, "Engrams")
        self.promoted = os.path.join(self.tmp, "promoted")
        os.makedirs(self.staging)
        self.note = os.path.join(self.staging, "A vetted claim about something.md")
        with open(self.note, "w", encoding="utf-8") as f:
            f.write(STAGED)

    def test_promotion_drops_all_chunk_records_for_staging_path(self):
        from unittest import mock

        from orchestrator.tools import knowledge_index

        fake = _FakeChunkedCollection()
        fake.seed_chunked(self.note, 3)  # staging note indexed as 3 chunks
        with mock.patch.object(knowledge_index, "get_knowledge_collection",
                               return_value=fake), \
             mock.patch.object(knowledge_index, "_nomic_embed",
                               return_value=None):
            ep.staging_note_to_engram(
                self.note, vault_engrams=self.vault,
                promoted_dir=self.promoted, index=True)

        staging_abspath = os.path.abspath(self.note)
        self.assertFalse(
            any(rec["metadata"].get("path") == staging_abspath
                for rec in fake.store.values()),
            "orphan chunk record(s) survived promotion")


if __name__ == "__main__":
    unittest.main()
