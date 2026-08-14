"""Focused contract tests for Dialogue lifecycle mutations.

These tests intentionally exercise the lifecycle helpers without importing the
Flask server.  The server has a broad import graph (models, media, and runtime
workers); the durable contract belongs in ``conversation_memory`` and
``conversation_closeout`` and can be verified hermetically with temp roots.

Coverage:

* Standard/Private envelope mutation and Stealth immutability
* fork creation-mode override, including a new Stealth fork
* authoritative display names and derived title fallback
* denormalized Chroma/chunk/submission metadata propagation
* best-effort permanent deletion, raw-log recovery, rotated telemetry scrub,
  sticky-risk cleanup, explicit vault-export retention, and diagnostics
"""

from __future__ import annotations

import contextlib
import gzip
import io
import json
import os
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

from orchestrator import conversation_closeout as closeout
from orchestrator import conversation_memory as memory
from orchestrator import runtime_paths


def _write_envelope(
    sessions_root: Path,
    conversation_id: str,
    *,
    tag: str = "",
    display_name: str | None = None,
    messages: list[dict] | None = None,
) -> Path:
    path = sessions_root / conversation_id / "conversation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "conversation_id": conversation_id,
        "tag": tag,
        "messages": messages or [],
        "project_ids": ["ora"],
    }
    if display_name is not None:
        envelope["display_name"] = display_name
    path.write_text(json.dumps(envelope), encoding="utf-8")
    return path


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


class _FakeCollection:
    """Small Chroma-shaped collection that records metadata-only updates."""

    def __init__(self, rows: list[dict], *, fail_ids: set[str] | None = None):
        self.rows = {row["id"]: {
            "document": row.get("document", ""),
            "metadata": dict(row.get("metadata") or {}),
        } for row in rows}
        self.fail_ids = set(fail_ids or ())
        self.updates: list[str] = []

    def get(self, *, where=None, ids=None, include=None, **_kwargs):
        selected = []
        requested = set(ids or ()) if ids is not None else None
        for row_id, row in self.rows.items():
            if requested is not None and row_id not in requested:
                continue
            if where and any(row["metadata"].get(k) != v for k, v in where.items()):
                continue
            selected.append((row_id, row))
        return {
            "ids": [row_id for row_id, _ in selected],
            "documents": [row["document"] for _, row in selected],
            "metadatas": [dict(row["metadata"]) for _, row in selected],
        }

    def update(self, *, ids, metadatas=None, documents=None, **_kwargs):
        for index, row_id in enumerate(ids):
            if row_id in self.fail_ids:
                raise RuntimeError(f"synthetic update failure for {row_id}")
            if metadatas is not None:
                self.rows[row_id]["metadata"] = dict(metadatas[index])
            if documents is not None:
                self.rows[row_id]["document"] = documents[index]
            self.updates.append(row_id)

    def delete(self, *, ids, **_kwargs):
        for row_id in ids:
            self.rows.pop(row_id, None)


class TestConversationMemoryLifecycle(unittest.TestCase):
    def test_zero_turn_artifact_envelope_is_durable_and_creation_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = memory.ensure_conversation_envelope(
                "artifact-first", tag="private", sessions_root=root,
            )
            self.assertIsNotNone(path)
            data = json.loads(path.read_text())
            self.assertEqual(data["tag"], "private")
            self.assertEqual(data["messages"], [])
            # A later artifact request cannot implicitly retag the envelope.
            same = memory.ensure_conversation_envelope(
                "artifact-first", tag="", sessions_root=root,
            )
            self.assertEqual(same, path)
            self.assertEqual(json.loads(path.read_text())["tag"], "private")

    def test_zero_turn_artifact_envelope_refuses_corrupt_existing_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "corrupt" / "conversation.json"
            path.parent.mkdir()
            path.write_text("{broken")
            self.assertIsNone(memory.ensure_conversation_envelope(
                "corrupt", tag="private", sessions_root=root,
            ))
            self.assertEqual(path.read_text(), "{broken")

    def test_direct_writers_refuse_session_symlink_escape(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sessions = base / "sessions"
            external = base / "external"
            sessions.mkdir()
            external.mkdir()
            outside_envelope = external / "conversation.json"
            outside_envelope.write_text(json.dumps({
                "conversation_id": "escape",
                "tag": "private",
                "messages": [],
            }), encoding="utf-8")
            (sessions / "escape").symlink_to(external, target_is_directory=True)

            self.assertIsNone(memory.ensure_conversation_envelope(
                "escape", tag="private", sessions_root=sessions,
            ))
            self.assertIsNone(memory.save_turn_spatial_state(
                "escape", "user", "assistant", sessions_root=sessions,
            ))
            self.assertEqual(
                json.loads(outside_envelope.read_text(encoding="utf-8"))["messages"],
                [],
            )

    def test_effective_title_prefers_display_name_and_derives_after_clear(self):
        data = {
            "display_name": "  My durable name  ",
            "messages": [{"role": "user", "content": "fallback prompt"}],
        }
        self.assertEqual(memory.effective_conversation_title(data), "My durable name")

        data.pop("display_name")
        self.assertEqual(memory.effective_conversation_title(data), "fallback prompt")
        data["is_welcome"] = True
        self.assertEqual(memory.effective_conversation_title(data), "Welcome to Ora")

    def test_effective_title_collapses_and_truncates_derived_text(self):
        data = {"messages": [{
            "role": "user",
            "content": "one\n\t two  three four",
        }]}
        self.assertEqual(memory.effective_conversation_title(data, max_len=14),
                         "one two three…")

    def test_standard_private_round_trip_preserves_envelope(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = _write_envelope(
                root, "conv-tag", tag="",
                messages=[{"role": "user", "content": "hello"}],
            )

            self.assertEqual(
                memory.set_conversation_tag("conv-tag", "private", sessions_root=root),
                path,
            )
            private = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(private["tag"], "private")
            self.assertEqual(private["messages"][0]["content"], "hello")
            self.assertEqual(private["project_ids"], ["ora"])

            # Re-applying the same value is intentionally idempotent.
            self.assertEqual(
                memory.set_conversation_tag("conv-tag", "private", sessions_root=root),
                path,
            )
            memory.set_conversation_tag("conv-tag", "", sessions_root=root)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["tag"], "")

    def test_stealth_is_creation_only_and_missing_is_nonfatal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            stealth_path = _write_envelope(root, "stealth-one", tag="stealth")
            before = stealth_path.read_text(encoding="utf-8")

            with self.assertRaises(ValueError):
                memory.set_conversation_tag("stealth-one", "stealth", sessions_root=root)
            with self.assertRaises(PermissionError):
                memory.set_conversation_tag("stealth-one", "private", sessions_root=root)
            self.assertEqual(stealth_path.read_text(encoding="utf-8"), before)
            self.assertIsNone(
                memory.set_conversation_tag("does-not-exist", "private", sessions_root=root)
            )

    def test_fork_creation_tag_overrides_parent_without_mutating_it(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            parent_path = _write_envelope(
                root, "parent", tag="private", display_name="Research",
                messages=[
                    {"role": "user", "content": "source one"},
                    {"role": "assistant", "content": "answer one"},
                    {"role": "user", "content": "source two"},
                    {"role": "assistant", "content": "answer two"},
                ],
            )
            parent_before = parent_path.read_bytes()

            child = memory.fork_conversation(
                "parent", "child-stealth", creation_tag="stealth",
                fork_point_turn_index=0,
                fork_point_chunk_id="parent-002", sessions_root=root,
                timestamp="2026-07-12T10:00:00",
            )
            self.assertIsNotNone(child)
            assert child is not None
            self.assertEqual(child["tag"], "stealth")
            self.assertEqual(child["parent_conversation_id"], "parent")
            self.assertEqual(child["fork_point_message_count"], 2)
            self.assertEqual(child["fork_point_chunk_id"], "parent-002")
            self.assertEqual(child["display_name"], "Research (fork)")
            self.assertEqual(child["messages"], [])
            parent = json.loads(parent_path.read_text(encoding="utf-8"))
            self.assertEqual(parent["tag"], "private")
            self.assertEqual(parent["messages"][0]["content"], "source one")
            self.assertEqual(parent_path.read_bytes(), parent_before)

            inherited = memory.fork_conversation(
                "parent", "child-inherited", sessions_root=root,
            )
            self.assertEqual(inherited["tag"], "private")
            self.assertEqual(inherited["fork_point_message_count"], 4)
            self.assertEqual(inherited["messages"], [])

            memory.save_turn_spatial_state(
                "parent", "later parent", "later answer", sessions_root=root,
            )
            persisted_child = memory.load_conversation_json(
                "child-inherited", sessions_root=root,
            )
            self.assertEqual(persisted_child["fork_point_message_count"], 4)
            self.assertEqual(persisted_child["messages"], [])
            summaries = {
                row["conversation_id"]: row
                for row in memory.iter_conversations(sessions_root=root)
            }
            self.assertEqual(summaries["child-inherited"]["inherited_message_count"], 4)
            self.assertEqual(summaries["child-inherited"]["local_message_count"], 0)

    def test_fork_rejects_invalid_displayed_turn_without_creating_child(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_envelope(
                root, "parent",
                messages=[
                    {"role": "user", "content": "source"},
                    {"role": "assistant", "content": "answer"},
                ],
            )
            for index in (-1, 1, True, "0"):
                with self.subTest(index=index), self.assertRaises(ValueError):
                    memory.fork_conversation(
                        "parent", f"child-{index}",
                        fork_point_turn_index=index,
                        sessions_root=root,
                    )
            self.assertEqual(
                sorted(path.name for path in root.iterdir()),
                ["parent"],
            )

    def test_fork_privacy_lattice_is_enforced_by_storage_helper(self):
        allowed = {
            "": {"", "private", "stealth"},
            "private": {"private", "stealth"},
            "stealth": {"stealth"},
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for parent_tag in ("", "private", "stealth"):
                parent_id = f"parent-{parent_tag or 'standard'}"
                _write_envelope(root, parent_id, tag=parent_tag)
                for child_tag in ("", "private", "stealth"):
                    child_id = (
                        f"child-{parent_tag or 'standard'}-"
                        f"{child_tag or 'standard'}"
                    )
                    if child_tag in allowed[parent_tag]:
                        child = memory.fork_conversation(
                            parent_id, child_id, creation_tag=child_tag,
                            sessions_root=root,
                        )
                        self.assertEqual(child["tag"], child_tag)
                    else:
                        with self.assertRaisesRegex(ValueError, "privacy"):
                            memory.fork_conversation(
                                parent_id, child_id, creation_tag=child_tag,
                                sessions_root=root,
                            )
                        self.assertFalse((root / child_id).exists())

    def test_legacy_envelope_backfills_cutoff_on_next_write(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = _write_envelope(root, "legacy")
            self.assertNotIn(
                "fork_point_message_count",
                json.loads(path.read_text(encoding="utf-8")),
            )
            memory.save_turn_spatial_state(
                "legacy", "user", "answer", sessions_root=root,
            )
            self.assertIsNone(
                json.loads(path.read_text(encoding="utf-8"))[
                    "fork_point_message_count"
                ]
            )

    def test_standard_and_private_close_are_retained_and_reversible(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for tag in ("", "private"):
                with self.subTest(tag=tag):
                    cid = "standard" if not tag else "private"
                    path = _write_envelope(
                        root, cid, tag=tag,
                        messages=[{"role": "user", "content": "keep me"}],
                    )
                    with mock.patch.object(
                        closeout, "_finalize_conversation_chunks",
                        return_value={"errors": [], "chunks_updated": 0},
                    ):
                        result = closeout.close_conversation(
                            cid, sessions_root=root,
                        )
                    self.assertEqual(result["action"], "close")
                    self.assertTrue(path.exists())
                    self.assertTrue(json.loads(path.read_text())["closed"])
                    memory.set_conversation_closed(cid, False, sessions_root=root)
                    restored = json.loads(path.read_text())
                    self.assertNotIn("closed", restored)
                    self.assertEqual(restored["messages"][0]["content"], "keep me")


class TestConversationMetadataPropagation(unittest.TestCase):
    def _collection(self, chunk_paths: tuple[Path, Path] | None = None):
        p1, p2 = chunk_paths or (Path("/tmp/chunk-1.md"), Path("/tmp/chunk-2.md"))
        return _FakeCollection([
            {"id": "target-1", "document": "doc one", "metadata": {
                "conversation_id": "target", "conversation_title": "Old",
                "tag": "", "tag_private": False, "chunk_path": str(p1),
                "turn_index": 1, "custom": "keep-one",
            }},
            {"id": "target-2", "document": "doc two", "metadata": {
                "conversation_id": "target", "conversation_title": "Old",
                "tag": "", "tag_private": False, "chunk_path": str(p2),
                "turn_index": 2, "custom": "keep-two",
            }},
            {"id": "other-1", "document": "other doc", "metadata": {
                "conversation_id": "other", "conversation_title": "Other",
                "tag": "private", "tag_private": True, "custom": "untouched",
            }},
        ])

    def test_refresh_title_updates_every_target_metadata_only(self):
        collection = self._collection()
        result = closeout.refresh_conversation_title_metadata(
            "target", "A new name", collection=collection,
            daily_notes_dir=Path("/__ora_nonexistent_daily_notes__"),
        )

        self.assertEqual(result["conversation_id"], "target")
        self.assertEqual(result["conversation_title"], "A new name")
        self.assertEqual(result["chromadb_records"], 2)
        self.assertEqual(result["errors"], [])
        self.assertEqual(collection.rows["target-1"]["metadata"]["custom"], "keep-one")
        self.assertEqual(collection.rows["target-2"]["metadata"]["custom"], "keep-two")
        self.assertEqual(collection.rows["target-1"]["document"], "doc one")
        self.assertEqual(collection.rows["other-1"]["metadata"]["conversation_title"],
                         "Other")

    def test_refresh_title_reports_partial_failure_without_touching_other_rows(self):
        collection = self._collection()
        collection.fail_ids.add("target-2")
        result = closeout.refresh_conversation_title_metadata(
            "target", "A new name", collection=collection,
            daily_notes_dir=Path("/__ora_nonexistent_daily_notes__"),
        )

        self.assertTrue(result["errors"])
        self.assertIn("synthetic update failure", " ".join(result["errors"]))
        self.assertEqual(collection.rows["other-1"]["metadata"]["conversation_title"],
                         "Other")

    def test_refresh_title_renames_exact_daily_note_summary(self):
        from orchestrator.tools import daily_note

        with tempfile.TemporaryDirectory() as td:
            daily_dir = Path(td) / "Daily Notes"
            daily_dir.mkdir()
            note = daily_dir / "2026-07-12.md"
            note.write_text(daily_note.render_note(
                "2026-07-12",
                [{"id": "target", "name": "Old", "exchanges": 1,
                  "first": "09:00", "last": "09:00", "gist": "question"}],
                [], [], [],
            ), encoding="utf-8")
            result = closeout.refresh_conversation_title_metadata(
                "target", "New", previous_title="Old",
                collection=self._collection(), daily_notes_dir=daily_dir,
            )
            self.assertEqual(result["daily_notes"]["summaries_renamed"], 1)
            self.assertIn("**New**", note.read_text(encoding="utf-8"))

    def test_privacy_tightening_commits_envelope_despite_daily_note_error(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sessions = base / "sessions"
            conversations = base / "conversations"
            raw = conversations / "raw"
            data = base / "data"
            vault = base / "vault"
            for directory in (
                sessions, conversations, raw / "pending", raw / "processed",
                data, vault,
            ):
                directory.mkdir(parents=True, exist_ok=True)
            envelope = _write_envelope(sessions, "target", tag="")
            daily_error = {
                "errors": ["edited legacy summary requires manual review"],
                "files_updated": [],
                "summaries_removed": 0,
            }
            with (
                mock.patch.object(runtime_paths, "DATA_DIR_STR", str(data)),
                mock.patch(
                    "orchestrator.tools.daily_note.reconcile_conversation_summaries",
                    return_value=daily_error,
                ),
            ):
                result = closeout.update_conversation_privacy_tag(
                    "target", "private",
                    sessions_root=sessions,
                    conversations_dir=conversations,
                    conversations_raw=raw,
                    chromadb_path=base / "chroma",
                    collection=_FakeCollection([]),
                    knowledge_collection=_FakeCollection([]),
                    vault_root=vault,
                )
            self.assertTrue(result["envelope_updated"])
            self.assertEqual(
                json.loads(envelope.read_text(encoding="utf-8"))["tag"],
                "private",
            )
            self.assertIn("manual review", " ".join(result["errors"]))

    def test_privacy_change_retags_trace_manifest_inside_lifecycle_lock(self):
        from orchestrator import pipeline_trace

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sessions = base / "sessions"
            conversations = base / "conversations"
            raw = conversations / "raw"
            data = base / "data"
            vault = base / "vault"
            trace_root = base / "traces"
            for directory in (
                sessions, conversations, raw / "pending", raw / "processed",
                data, vault,
            ):
                directory.mkdir(parents=True, exist_ok=True)
            _write_envelope(sessions, "target", tag="")
            manifest = trace_root / "TARGET" / "20260712T120000Z" / "trace-manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({
                "conversation_id": "target",
                "redaction_level": "default",
            }), encoding="utf-8")

            with (
                mock.patch.object(runtime_paths, "DATA_DIR_STR", str(data)),
                mock.patch.object(pipeline_trace, "TRACE_ROOT", str(trace_root)),
            ):
                private = closeout.update_conversation_privacy_tag(
                    "target", "private",
                    sessions_root=sessions,
                    conversations_dir=conversations,
                    conversations_raw=raw,
                    collection=_FakeCollection([]),
                    knowledge_collection=_FakeCollection([]),
                    vault_root=vault,
                )
                self.assertEqual(
                    json.loads(manifest.read_text(encoding="utf-8"))[
                        "redaction_level"
                    ],
                    "private",
                )
                standard = closeout.update_conversation_privacy_tag(
                    "target", "",
                    sessions_root=sessions,
                    conversations_dir=conversations,
                    conversations_raw=raw,
                    collection=_FakeCollection([]),
                    knowledge_collection=_FakeCollection([]),
                    vault_root=vault,
                )

            self.assertEqual(private["trace_manifests"]["updated"], 1)
            self.assertEqual(standard["trace_manifests"]["updated"], 1)
            self.assertEqual(
                json.loads(manifest.read_text(encoding="utf-8"))[
                    "redaction_level"
                ],
                "default",
            )

    def test_privacy_change_propagates_envelope_chroma_yaml_and_json_records(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sessions = base / "sessions"
            conversations = base / "conversations"
            raw = conversations / "raw"
            data = base / "data"
            for directory in (sessions, conversations, raw / "pending", raw / "processed", data):
                directory.mkdir(parents=True, exist_ok=True)

            envelope = _write_envelope(sessions, "target", tag="")
            chunk_one = conversations / "chunk-one.md"
            chunk_two = conversations / "chunk-two.md"
            chunk_one.write_text(
                "---\nnexus:\ntype: chat\ntags:\n  - atomic\n---\n\nFirst body.\n",
                encoding="utf-8",
            )
            chunk_two.write_text(
                "---\nnexus:\ntype: chat\ntags:\n---\n\nSecond body.\n",
                encoding="utf-8",
            )
            collection = self._collection((chunk_one, chunk_two))
            knowledge_collection = _FakeCollection([])

            manifest = data / "conversation-manifest.jsonl"
            manifest.write_text(
                json.dumps({"conversation_id": "target", "chunk_path": str(chunk_one),
                            "tag": "", "untouched": 1}) + "\n" +
                json.dumps({"conversation_id": "other", "tag": ""}) + "\n",
                encoding="utf-8",
            )
            failures = data / "conversation-indexing-failures.jsonl"
            failures.write_text(
                json.dumps({"conversation_id": "target", "tag": "", "error": "old"}) + "\n" +
                json.dumps({"conversation_id": "other", "tag": ""}) + "\n",
                encoding="utf-8",
            )
            entity_index = data / "entity-index.json"
            entity_index.write_text(
                json.dumps({"Sensitive title": ["Private Person"]}),
                encoding="utf-8",
            )
            visual_emissions = data / "visual-emission-log.jsonl"
            visual_emissions.write_text(
                json.dumps({"conversation_id": "target", "tag": ""}) + "\n" +
                json.dumps({"conversation_id": "other", "tag": ""}) + "\n",
                encoding="utf-8",
            )
            vault_root = base / "vault"
            vault_root.mkdir()
            from orchestrator.tools import daily_note
            daily_notes = vault_root / "Daily Notes"
            daily_notes.mkdir()
            daily_path = daily_notes / "2026-07-12.md"
            daily_path.write_text(daily_note.render_note(
                "2026-07-12",
                [{"id": "target", "name": "Sensitive title",
                  "exchanges": 1, "first": "09:00", "last": "09:00",
                  "gist": "Sensitive prompt"}],
                [], [], [],
            ), encoding="utf-8")
            managed_transcript = vault_root / "Transcript — Managed.md"
            managed_transcript.write_text(
                "---\n"
                "type: transcript\n"
                "tags:\n  - incubating\n"
                "artifact_kind: conversation_transcript\n"
                "managed_by: ora\n"
                "source_file: target\n"
                "---\n\nSensitive transcript.\n",
                encoding="utf-8",
            )
            explicit_note = vault_root / "Explicit Source Note.md"
            explicit_note.write_text(
                "---\ntype: resource\ntags:\nsource_file: target\n---\n\nKeep.\n",
                encoding="utf-8",
            )
            for folder, name in ((raw / "pending", "pending.json"),
                                 (raw / "processed", "processed.json")):
                (folder / name).write_text(json.dumps({
                    "conversation_id": "target", "panel_id": "target",
                    "tag": "", "user_input": "keep me",
                }), encoding="utf-8")
                (folder / f"other-{name}").write_text(json.dumps({
                    "conversation_id": "other", "tag": "",
                }), encoding="utf-8")
            raw_audit = raw / "target-audit.md"
            raw_audit.write_text(
                "# Session session-1\n\npanel_id: target\n"
                "source_platform: local\n\n---\n\nexchange\n",
                encoding="utf-8",
            )

            with mock.patch.object(runtime_paths, "DATA_DIR_STR", str(data)):
                result = closeout.update_conversation_privacy_tag(
                    "target", "private", sessions_root=sessions,
                    conversations_dir=conversations, conversations_raw=raw,
                    collection=collection,
                    knowledge_collection=knowledge_collection,
                    vault_root=vault_root,
                )

            self.assertEqual(result["previous_tag"], "")
            self.assertEqual(result["tag"], "private")
            self.assertTrue(result["entity_index_retired"])
            self.assertFalse(entity_index.exists())
            self.assertEqual(result["visual_emission_entries"], 1)
            self.assertEqual(_read_jsonl(visual_emissions)[0]["tag"], "private")
            self.assertEqual(_read_jsonl(visual_emissions)[1]["tag"], "")
            self.assertIn("  - private\n", managed_transcript.read_text())
            self.assertNotIn("  - private\n", explicit_note.read_text())
            self.assertNotIn("Sensitive title", daily_path.read_text())
            self.assertEqual(result["daily_notes"]["summaries_removed"], 1)
            self.assertIn("tag: private\n", raw_audit.read_text())
            self.assertIn("tag_private: true\n", raw_audit.read_text())
            self.assertTrue(result["envelope_updated"])
            self.assertEqual(json.loads(envelope.read_text(encoding="utf-8"))["tag"],
                             "private")
            for row_id in ("target-1", "target-2"):
                metadata = collection.rows[row_id]["metadata"]
                self.assertEqual(metadata["tag"], "private")
                self.assertTrue(metadata["tag_private"])
                self.assertTrue(metadata["custom"].startswith("keep-"))
            self.assertEqual(collection.rows["other-1"]["metadata"]["tag"], "private")
            self.assertIn("  - atomic\n", chunk_one.read_text(encoding="utf-8"))
            self.assertIn("  - private\n", chunk_one.read_text(encoding="utf-8"))
            self.assertIn("  - private\n", chunk_two.read_text(encoding="utf-8"))
            self.assertEqual(_read_jsonl(manifest)[0]["tag"], "private")
            self.assertEqual(_read_jsonl(manifest)[0]["untouched"], 1)
            self.assertEqual(_read_jsonl(manifest)[1]["tag"], "")
            self.assertEqual(_read_jsonl(failures)[0]["tag"], "private")
            self.assertEqual(
                json.loads((raw / "pending" / "pending.json").read_text())["tag"],
                "private",
            )
            self.assertEqual(
                json.loads((raw / "processed" / "processed.json").read_text())["tag"],
                "private",
            )
            self.assertEqual(result["errors"], [])

            # The reverse mutation removes only the controlled private tag;
            # unrelated frontmatter tags and content remain.
            with mock.patch.object(runtime_paths, "DATA_DIR_STR", str(data)):
                reverse = closeout.update_conversation_privacy_tag(
                    "target", "", sessions_root=sessions,
                    conversations_dir=conversations, conversations_raw=raw,
                    collection=collection,
                    knowledge_collection=knowledge_collection,
                    vault_root=vault_root,
                )
            self.assertEqual(reverse["previous_tag"], "private")
            self.assertNotIn("  - private\n", chunk_one.read_text(encoding="utf-8"))
            self.assertIn("  - atomic\n", chunk_one.read_text(encoding="utf-8"))
            self.assertFalse(collection.rows["target-1"]["metadata"]["tag_private"])
            self.assertNotIn("  - private\n", managed_transcript.read_text())
            self.assertIn("tag: \n", raw_audit.read_text())
            self.assertIn("tag_private: false\n", raw_audit.read_text())

    def test_privacy_change_rejects_stealth_and_does_not_mutate_caches(self):
        with tempfile.TemporaryDirectory() as td:
            sessions = Path(td) / "sessions"
            envelope = _write_envelope(sessions, "stealth", tag="stealth")
            collection = _FakeCollection([{
                "id": "stealth-1", "metadata": {
                    "conversation_id": "stealth", "tag": "stealth",
                    "tag_private": False,
                },
            }])
            with self.assertRaises(PermissionError):
                closeout.update_conversation_privacy_tag(
                    "stealth", "private", sessions_root=sessions,
                    collection=collection,
                )
            self.assertEqual(json.loads(envelope.read_text())["tag"], "stealth")
            self.assertEqual(collection.rows["stealth-1"]["metadata"]["tag"],
                             "stealth")

    def test_private_tightening_failure_commits_envelope_and_reports_residue(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sessions = base / "sessions"
            conversations = base / "conversations"
            raw = conversations / "raw"
            data = base / "data"
            for path in (sessions, conversations, raw, data):
                path.mkdir(parents=True, exist_ok=True)
            envelope = _write_envelope(sessions, "target", tag="")
            chunk = conversations / "owned.md"
            chunk.write_text(
                "---\nnexus:\ntype: chat\ntags:\n---\nbody\n",
                encoding="utf-8",
            )
            collection = _FakeCollection([{
                "id": "broken-row",
                "metadata": {
                    "conversation_id": "target",
                    "chunk_path": str(chunk),
                    "tag": "",
                    "tag_private": False,
                },
            }], fail_ids={"broken-row"})
            with mock.patch.object(runtime_paths, "DATA_DIR_STR", str(data)):
                result = closeout.update_conversation_privacy_tag(
                    "target", "private",
                    sessions_root=sessions,
                    conversations_dir=conversations,
                    conversations_raw=raw,
                    collection=collection,
                    knowledge_collection=_FakeCollection([]),
                    vault_root=base / "vault",
                )
            self.assertTrue(result["envelope_updated"])
            self.assertEqual(json.loads(envelope.read_text())["tag"], "private")
            self.assertIn("synthetic update failure", " ".join(result["errors"]))

    def test_private_tightening_reports_incomplete_transcript_scan(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sessions = base / "sessions"
            conversations = base / "conversations"
            raw = conversations / "raw"
            data = base / "data"
            vault = base / "vault"
            for path in (sessions, conversations, raw, data, vault):
                path.mkdir(parents=True, exist_ok=True)
            envelope = _write_envelope(sessions, "target", tag="")
            original_iterdir = Path.iterdir

            def fail_vault_iterdir(path):
                if path == vault:
                    raise PermissionError("synthetic vault scan denial")
                return original_iterdir(path)

            with (
                mock.patch.object(runtime_paths, "DATA_DIR_STR", str(data)),
                mock.patch.object(Path, "iterdir", fail_vault_iterdir),
            ):
                result = closeout.update_conversation_privacy_tag(
                    "target", "private",
                    sessions_root=sessions,
                    conversations_dir=conversations,
                    conversations_raw=raw,
                    collection=_FakeCollection([]),
                    knowledge_collection=_FakeCollection([]),
                    vault_root=vault,
                )

            self.assertTrue(result["envelope_updated"])
            self.assertEqual(json.loads(envelope.read_text())["tag"], "private")
            self.assertIn(
                "synthetic vault scan denial", " ".join(result["errors"]),
            )

    def test_privacy_retags_runtime_derivative_files_and_knowledge_rows(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sessions = base / "sessions"
            conversations = base / "conversations"
            raw = conversations / "raw"
            data = base / "data"
            vault = base / "vault"
            staging = data / "extraction-staging"
            engrams = vault / "Engrams"
            for path in (sessions, conversations, raw, data, staging, engrams):
                path.mkdir(parents=True, exist_ok=True)
            _write_envelope(sessions, "target", tag="")
            for path in (staging / "Working.md", engrams / "Engram.md"):
                path.write_text(
                    "---\nnexus:\ntype: working\ntags:\n  - atomic\n"
                    "artifact_kind: conversation_runtime_derivative\n"
                    "managed_by: ora\nsource_file: target\n---\n\n# Derived\n",
                    encoding="utf-8",
                )
            vault_index = data / "vault-index.json"
            vault_index.write_text(json.dumps({
                "version": 1,
                "vault_path": str(vault),
                "entries": [
                    {"vault_path": "Engrams/Engram.md", "summary": "secret"},
                    {"vault_path": "Reference.md", "summary": "keep"},
                ],
            }), encoding="utf-8")
            conversations_collection = _FakeCollection([])
            knowledge = _FakeCollection([{
                "id": str((staging / "Working.md").resolve()),
                "metadata": {
                    "source_file": "target",
                    "tags": ["atomic"],
                    "tag_private": False,
                },
            }, {
                "id": str((engrams / "Engram.md").resolve()) + "#chunk-0",
                "metadata": {
                    "path": str((engrams / "Engram.md").resolve()),
                    "tags": ["atomic"],
                    "tag_private": False,
                },
            }])
            with mock.patch.object(runtime_paths, "DATA_DIR_STR", str(data)):
                private = closeout.update_conversation_privacy_tag(
                    "target", "private",
                    sessions_root=sessions,
                    conversations_dir=conversations,
                    conversations_raw=raw,
                    collection=conversations_collection,
                    knowledge_collection=knowledge,
                    vault_root=vault,
                )
                standard = closeout.update_conversation_privacy_tag(
                    "target", "",
                    sessions_root=sessions,
                    conversations_dir=conversations,
                    conversations_raw=raw,
                    collection=conversations_collection,
                    knowledge_collection=knowledge,
                    vault_root=vault,
                )
            self.assertTrue(private["envelope_updated"])
            self.assertEqual(len(private["runtime_derivative_files"]), 2)
            self.assertTrue(private["runtime_knowledge_records"])
            self.assertEqual(private["vault_index_entries"], 1)
            self.assertTrue(standard["envelope_updated"])
            self.assertEqual(standard["vault_index_entries"], 1)
            for path in (staging / "Working.md", engrams / "Engram.md"):
                self.assertNotIn("  - private\n", path.read_text())
            row = knowledge.rows[str((staging / "Working.md").resolve())]["metadata"]
            self.assertFalse(row["tag_private"])
            self.assertNotIn("private", row.get("tags", []))
            chunked = knowledge.rows[
                str((engrams / "Engram.md").resolve()) + "#chunk-0"
            ]["metadata"]
            self.assertFalse(chunked["tag_private"])
            self.assertNotIn("private", chunked.get("tags", []))
            self.assertEqual(
                [row["vault_path"] for row in json.loads(
                    vault_index.read_text(encoding="utf-8")
                )["entries"]],
                ["Reference.md", "Engrams/Engram.md"],
            )

    def test_private_ped_refresh_deletes_stale_row_before_reindex(self):
        from orchestrator import oversight_actions
        from orchestrator.tools import knowledge_index

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sessions = base / "sessions"
            conversations = base / "conversations"
            raw = conversations / "raw"
            data = base / "data"
            vault = base / "vault"
            for path in (sessions, conversations, raw, data, vault):
                path.mkdir(parents=True, exist_ok=True)
            _write_envelope(sessions, "ped-private", tag="")
            ped = vault / "Project.md"
            old_body = "# Project\n\nPublic context.\n\nPrivate managed verdict text.\n"
            scrubbed = "# Project\n\nPublic context remains after lifecycle mutation.\n"
            ped.write_text(old_body, encoding="utf-8")
            row_id = str(ped.absolute())
            knowledge = _FakeCollection([{
                "id": row_id,
                "document": old_body,
                "metadata": {"path": row_id},
            }])
            indexed_bodies: list[str] = []

            def hide_derivative(*_args, **_kwargs):
                ped.write_text(scrubbed, encoding="utf-8")
                return {
                    "requires_reindex": [row_id],
                    "modified_paths": [row_id],
                    "failed_paths": [],
                    "errors": [],
                }

            def index_after_delete(current, filepath, stats, **_kwargs):
                self.assertNotIn(row_id, current.rows)
                body = Path(filepath).read_text(encoding="utf-8")
                indexed_bodies.append(body)
                current.rows[row_id] = {
                    "document": body, "metadata": {"path": row_id},
                }
                stats["indexed"] += 1

            with (
                mock.patch.object(runtime_paths, "DATA_DIR_STR", str(data)),
                mock.patch.object(
                    oversight_actions,
                    "set_conversation_ped_derivatives_private",
                    side_effect=hide_derivative,
                ),
                mock.patch.object(
                    knowledge_index, "index_file", side_effect=index_after_delete,
                ),
            ):
                result = closeout.update_conversation_privacy_tag(
                    "ped-private", "private",
                    sessions_root=sessions,
                    conversations_dir=conversations,
                    conversations_raw=raw,
                    collection=_FakeCollection([]),
                    knowledge_collection=knowledge,
                    vault_root=vault,
                )

            self.assertTrue(result["envelope_updated"])
            self.assertEqual(indexed_bodies, [scrubbed])
            self.assertNotIn("Private managed verdict", knowledge.rows[row_id]["document"])
            self.assertEqual(
                result["ped_indexes"]["knowledge_files_reindexed"], 1,
            )

    def test_failed_private_ped_mutation_removes_stale_row_without_readd(self):
        from orchestrator import oversight_actions
        from orchestrator.tools import knowledge_index

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sessions = base / "sessions"
            conversations = base / "conversations"
            raw = conversations / "raw"
            data = base / "data"
            vault = base / "vault"
            for path in (sessions, conversations, raw, data, vault):
                path.mkdir(parents=True, exist_ok=True)
            _write_envelope(sessions, "ped-failed", tag="")
            ped = vault / "Project.md"
            ped.write_text(
                "# Project\n\nPrivate managed verdict remains on disk after failure.\n",
                encoding="utf-8",
            )
            row_id = str(ped.absolute())
            knowledge = _FakeCollection([{
                "id": row_id,
                "document": "stale private verdict",
                "metadata": {"path": row_id},
            }])

            with (
                mock.patch.object(runtime_paths, "DATA_DIR_STR", str(data)),
                mock.patch.object(
                    oversight_actions,
                    "set_conversation_ped_derivatives_private",
                    return_value={
                        "requires_reindex": [row_id],
                        "modified_paths": [],
                        "failed_paths": [row_id],
                        "errors": ["synthetic PED mutation failure"],
                    },
                ),
                mock.patch.object(knowledge_index, "index_file") as reindex,
            ):
                result = closeout.update_conversation_privacy_tag(
                    "ped-failed", "private",
                    sessions_root=sessions,
                    conversations_dir=conversations,
                    conversations_raw=raw,
                    collection=_FakeCollection([]),
                    knowledge_collection=knowledge,
                    vault_root=vault,
                )

            self.assertTrue(result["envelope_updated"])
            self.assertNotIn(row_id, knowledge.rows)
            reindex.assert_not_called()
            self.assertIn("synthetic PED mutation failure", " ".join(result["errors"]))

    def test_ped_refresh_deletes_all_paths_before_any_reindex_failure(self):
        from orchestrator.tools import knowledge_index

        with tempfile.TemporaryDirectory() as td:
            vault = Path(td) / "vault"
            data = Path(td) / "data"
            vault.mkdir()
            data.mkdir()
            first = vault / "First.md"
            second = vault / "Second.md"
            for path in (first, second):
                path.write_text(
                    f"# {path.stem}\n\nLong enough public PED content after scrub.\n",
                    encoding="utf-8",
                )
            first_id = str(first.absolute())
            second_id = str(second.absolute())
            collection = _FakeCollection([
                {"id": first_id, "metadata": {"path": first_id}},
                {"id": second_id, "metadata": {"path": second_id}},
            ])
            calls: list[str] = []

            def index_one_fails(current, filepath, stats, **_kwargs):
                # Pass 1 must already have removed BOTH stale rows.
                self.assertNotIn(first_id, current.rows)
                self.assertNotIn(second_id, current.rows)
                calls.append(filepath)
                if filepath == first_id:
                    raise RuntimeError("synthetic first reindex failure")
                stats["indexed"] += 1

            errors: list[str] = []
            with (
                mock.patch.object(runtime_paths, "DATA_DIR_STR", str(data)),
                mock.patch.object(
                    knowledge_index, "index_file", side_effect=index_one_fails,
                ),
            ):
                refreshed = closeout._refresh_ped_derivative_indexes(
                    {
                        "requires_reindex": [first_id, second_id],
                        "failed_paths": [],
                    },
                    chromadb_path=Path(td) / "chroma",
                    vault_root=vault,
                    errors=errors,
                    collection=collection,
                    remove_vault_first=True,
                )

            self.assertEqual(calls, [first_id, second_id])
            self.assertEqual(refreshed["knowledge_files_reindexed"], 1)
            self.assertIn("synthetic first reindex failure", " ".join(errors))

    def test_privacy_retags_typed_custom_output_with_exact_marker(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sessions = base / "sessions"
            conversations = base / "conversations"
            raw = conversations / "raw"
            data = base / "data"
            custom_root = base / "custom"
            for path in (sessions, conversations, raw, data, custom_root):
                path.mkdir(parents=True, exist_ok=True)
            _write_envelope(sessions, "target")
            custom = custom_root / "turn.md"
            custom.write_text(
                "---\nnexus:\ntype: chat\ntags:\n---\n\n"
                '<!-- ora-conversation-id: "target" -->\n',
                encoding="utf-8",
            )
            (data / "conversation-manifest.jsonl").write_text(json.dumps({
                "conversation_id": "target",
                "chunk_path": str(custom),
                "chunk_root": str(custom_root),
                "artifact_kind": "conversation_chunk",
                "managed_by": "ora",
                "tag": "",
            }) + "\n")
            with mock.patch.object(runtime_paths, "DATA_DIR_STR", str(data)):
                result = closeout.update_conversation_privacy_tag(
                    "target", "private",
                    sessions_root=sessions,
                    conversations_dir=conversations,
                    conversations_raw=raw,
                    collection=_FakeCollection([]),
                    knowledge_collection=_FakeCollection([]),
                    vault_root=base / "vault",
                )
            self.assertTrue(result["envelope_updated"])
            self.assertIn("  - private\n", custom.read_text())

    def test_collection_discovery_finds_retired_families_without_history(self):
        from orchestrator import embedding

        class Client:
            def list_collections(self):
                return [
                    types.SimpleNamespace(
                        name="conversations_qwen", metadata={},
                    ),
                    types.SimpleNamespace(name="conversations_v2", metadata={}),
                    types.SimpleNamespace(name="conversations", metadata={}),
                    types.SimpleNamespace(
                        name="conversations_incognito_qwen", metadata={},
                    ),
                    types.SimpleNamespace(name="knowledge_qwen", metadata={}),
                    types.SimpleNamespace(name="knowledge_v2", metadata={}),
                    types.SimpleNamespace(name="knowledge-graph", metadata={}),
                ]

        with (
            mock.patch.dict(embedding.COLLECTIONS, {
                "conversations": "conversations_qwen",
                "conversations_incognito": "conversations_incognito_qwen",
                "knowledge": "knowledge_qwen",
            }),
            mock.patch.dict(embedding.COLLECTION_HISTORY, {}, clear=True),
        ):
            self.assertEqual(
                embedding.discover_collection_copies(Client(), "conversations"),
                ("conversations_qwen", "conversations_v2", "conversations"),
            )
            self.assertEqual(
                embedding.discover_collection_copies(Client(), "knowledge"),
                ("knowledge_qwen", "knowledge_v2"),
            )

    def test_all_discovered_copies_follow_rename_privacy_finalize_and_delete(self):
        from orchestrator import embedding, execution_persistence, pipeline_trace

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sessions = base / "sessions"
            conversations = base / "conversations"
            raw = conversations / "raw"
            data = base / "data"
            vault = base / "vault"
            staging = data / "extraction-staging"
            for path in (
                sessions, conversations, raw, data, vault, staging,
                vault / "Sessions",
            ):
                path.mkdir(parents=True, exist_ok=True)
            _write_envelope(sessions, "target", tag="")
            derivative = staging / "derived.md"
            derivative.write_text(
                "---\ntype: working\ntags:\nsource_file: target\n---\nbody\n",
                encoding="utf-8",
            )

            def conversation_rows(prefix: str, turn: int):
                return _FakeCollection([{
                    "id": f"{prefix}-row",
                    "metadata": {
                        "conversation_id": "target",
                        "conversation_title": "Old",
                        "tag": "",
                        "tag_private": False,
                        "turn_index": turn,
                    },
                }])

            active_conversations = conversation_rows("active", 2)
            retired_conversations = conversation_rows("retired", 1)
            active_knowledge = _FakeCollection([{
                "id": str(derivative.resolve()),
                "metadata": {"source_file": "target", "tag_private": False},
            }])
            retired_knowledge = _FakeCollection([{
                "id": str(derivative.resolve()),
                "metadata": {"source_file": "target", "tag_private": False},
            }])
            mapping = {
                "conversations_current": active_conversations,
                "conversations_v2": retired_conversations,
                "knowledge_current": active_knowledge,
                "knowledge_v2": retired_knowledge,
            }

            class Client:
                def list_collections(self):
                    return [types.SimpleNamespace(name=name, metadata={})
                            for name in mapping]

                def get_collection(self, *, name, **_kwargs):
                    return mapping[name]

            client = Client()

            def logical_collection(client_arg, logical_name):
                return client_arg.get_collection(
                    name=embedding.resolve_collection(logical_name),
                )

            with (
                mock.patch.dict(embedding.COLLECTIONS, {
                    "conversations": "conversations_current",
                    "knowledge": "knowledge_current",
                }),
                mock.patch.dict(embedding.COLLECTION_HISTORY, {}, clear=True),
                mock.patch("chromadb.PersistentClient", return_value=client),
                mock.patch.object(
                    embedding, "get_collection", side_effect=logical_collection,
                ),
                mock.patch.object(runtime_paths, "DATA_DIR_STR", str(data)),
                mock.patch.dict(
                    os.environ, {"ORA_OVERSIGHT_SANDBOX": str(data)},
                ),
                mock.patch.object(
                    pipeline_trace, "purge_conversation_traces",
                    return_value={"deleted": False, "path": "test", "error": None},
                ),
                mock.patch.object(
                    execution_persistence, "purge_conversation",
                    return_value={"errors": [], "ledger_entries": 0},
                ),
            ):
                renamed = closeout.refresh_conversation_title_metadata(
                    "target", "New title", chromadb_path=base / "chroma",
                    daily_notes_dir=vault / "Daily Notes",
                )
                private = closeout.update_conversation_privacy_tag(
                    "target", "private",
                    sessions_root=sessions,
                    conversations_dir=conversations,
                    conversations_raw=raw,
                    chromadb_path=base / "chroma",
                    vault_root=vault,
                )
                finalized = closeout._finalize_conversation_chunks(
                    "target", chromadb_path=base / "chroma",
                )
                deleted = closeout._purge_stealth(
                    "target",
                    sessions_root=sessions,
                    conversations_dir=conversations,
                    conversations_raw=raw,
                    chromadb_path=base / "chroma",
                    vault_sessions=vault / "Sessions",
                )

            self.assertEqual(renamed["chromadb_records"], 2)
            self.assertTrue(private["envelope_updated"])
            self.assertEqual(private["chromadb_records"], 2)
            self.assertEqual(private["runtime_knowledge_records"], 2)
            self.assertEqual(finalized["chunks_updated"], 2)
            self.assertEqual(deleted["deleted"]["chromadb_records"], 2)
            self.assertEqual(deleted["deleted"]["runtime_knowledge_records"], 2)
            self.assertEqual(active_conversations.rows, {})
            self.assertEqual(retired_conversations.rows, {})
            self.assertEqual(active_knowledge.rows, {})
            self.assertEqual(retired_knowledge.rows, {})


class TestDeleteConversationForever(unittest.TestCase):
    def _roots(self, base: Path) -> dict[str, Path]:
        roots = {
            "sessions": base / "sessions",
            "conversations": base / "conversations",
            "raw": base / "conversations" / "raw",
            "chroma": base / "chroma",
            "vault": base / "vault" / "Sessions",
            "data": base / "data",
        }
        for path in roots.values():
            path.mkdir(parents=True, exist_ok=True)
        (roots["raw"] / "pending").mkdir()
        (roots["raw"] / "processed").mkdir()
        (roots["data"] / "archive").mkdir()
        return roots

    def test_historical_default_root_pointer_requires_exact_marker(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            collision = root / "computed-name.md"
            collision.write_text("user-owned collision", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ownership marker mismatch"):
                closeout._owned_chunk_path(
                    str(collision),
                    default_root=root,
                    conversation_id="historical-0123456789ab",
                )
            # Existing live records retain their pre-marker compatibility.
            self.assertEqual(
                closeout._owned_chunk_path(
                    str(collision),
                    default_root=root,
                    conversation_id="legacy-live-dialogue",
                ),
                collision,
            )

    def _run_delete(
        self,
        conversation_id: str,
        roots: dict[str, Path],
        *,
        collection: _FakeCollection | None = None,
        knowledge_collection: _FakeCollection | None = None,
        collection_error: BaseException | None = None,
    ):
        # Keep all telemetry and approval lookups hermetic. The delete helper
        # still executes its normal layers; only their roots are redirected.
        from orchestrator import (
            dispatcher,
            embedding,
            execution_persistence,
            pipeline_trace,
            tool_events,
        )

        sandbox = str(roots["data"])
        knowledge_collection = knowledge_collection or _FakeCollection([])

        def logical_collection(_client, logical_name):
            if logical_name == "conversations":
                if collection_error is not None:
                    raise collection_error
                return collection
            if logical_name == "knowledge":
                return knowledge_collection
            raise AssertionError(f"unexpected logical collection {logical_name}")

        class LogicalClient:
            def list_collections(self):
                return [types.SimpleNamespace(
                    name=embedding.resolve_collection("conversations"),
                    metadata={"ora:logical_collection": "conversations"},
                )]

        modules_before = set(sys.modules)
        try:
            with (
                mock.patch.object(runtime_paths, "DATA_DIR_STR", sandbox),
                mock.patch.object(
                    dispatcher, "LOG_DIR", str(roots["data"].parent / "logs"),
                ),
                mock.patch.dict(os.environ, {"ORA_OVERSIGHT_SANDBOX": sandbox}),
                mock.patch.object(tool_events, "APPROVALS_PATH",
                                  str(roots["data"] / "execution-approvals.json")),
                mock.patch.object(tool_events, "global_sink_path",
                                  return_value=str(roots["data"] / "tool-events.jsonl")),
                mock.patch.object(pipeline_trace, "purge_conversation_traces",
                                  return_value={"deleted": False, "path": "test", "error": None}),
                mock.patch.object(execution_persistence, "purge_conversation",
                                  return_value={"errors": [], "ledger_entries": 0}),
                mock.patch("chromadb.PersistentClient", return_value=LogicalClient()),
                mock.patch.object(embedding, "get_collection",
                                  side_effect=logical_collection),
            ):
                return closeout.delete_conversation_forever(
                    conversation_id,
                    sessions_root=roots["sessions"],
                    conversations_dir=roots["conversations"],
                    conversations_raw=roots["raw"],
                    chromadb_path=roots["chroma"],
                    vault_sessions=roots["vault"],
                )
        finally:
            # Some legacy oversight modules bake their sandbox root at import
            # time. Remove only modules first imported inside this temporary
            # sandbox so later portability tests import them against the real
            # runtime_paths state instead of inheriting our fixture.
            for name in set(sys.modules) - modules_before:
                module = sys.modules.get(name)
                baked_root = str(getattr(module, "OVERSIGHT_DATA_DIR", ""))
                if baked_root.startswith(sandbox):
                    sys.modules.pop(name, None)

    def test_delete_helper_refuses_retained_dialogues_without_mutation(self):
        for tag in ("", "private"):
            with self.subTest(tag=tag), tempfile.TemporaryDirectory() as td:
                roots = self._roots(Path(td))
                envelope = _write_envelope(
                    roots["sessions"], "retained", tag=tag,
                    messages=[{"role": "user", "content": "must survive"}],
                )
                raw = roots["raw"] / "retained.md"
                raw.write_text(
                    "# Session retained\n\npanel_id: retained\n\n---\nkeep\n",
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(PermissionError, "use Close"):
                    self._run_delete("retained", roots)

                self.assertTrue(envelope.exists())
                self.assertTrue(raw.exists())

    def test_empty_legacy_approval_store_allows_explicit_stealth_delete_retry(self):
        repo = Path(__file__).resolve().parents[2]
        server_dir = str(repo / "server")
        if server_dir not in sys.path:
            sys.path.insert(0, server_dir)
        from server import app as server  # type: ignore
        import oversight_queue
        import tool_events
        from orchestrator import system_protection

        def path_state(path: Path):
            try:
                value = os.lstat(path)
            except FileNotFoundError:
                return None
            return (
                value.st_mode, value.st_dev, value.st_ino,
                value.st_size, value.st_mtime_ns,
            )

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            roots = self._roots(base)
            conversation_id = f"legacy-empty-{base.name.lower()}"
            sibling_id = f"sibling-{base.name.lower()}"
            _write_envelope(
                roots["sessions"], conversation_id, tag="stealth",
                messages=[{"role": "user", "content": "purge only this"}],
            )
            _write_envelope(
                roots["sessions"], sibling_id, tag="stealth",
                messages=[{"role": "user", "content": "must survive"}],
            )

            approval_path = roots["data"] / "execution-approvals.json"
            approval_path.write_text(
                json.dumps({"tokens": [], "standing": []}), encoding="utf-8",
            )
            queue_path = roots["data"] / "oversight" / "human-queue.jsonl"
            actions_path = roots["data"] / "oversight" / "actions.jsonl"
            event_path = roots["data"] / "tool-events.jsonl"

            live_approval = Path(tool_events._APPROVALS_BAKED)
            live_key = Path(str(live_approval) + ".auth.key")
            live_session = closeout._DEFAULT_SESSIONS_ROOT / conversation_id
            live_before = {
                live_approval: path_state(live_approval),
                live_key: path_state(live_key),
                live_session: path_state(live_session),
            }
            self.assertIsNone(live_before[live_session])

            purged: list[str] = []

            def purge_exact(value: str):
                self.assertEqual(value, conversation_id)
                purged.append(value)
                result = self._run_delete(
                    value, roots, collection=_FakeCollection([]),
                )
                server._deleted_conversations.add(
                    server._conversation_storage_identity(value),
                )
                return result

            server._conversation_creation_tags[
                server._conversation_storage_identity(conversation_id)
            ] = "stealth"
            tool_events._queued_hashes.clear()
            turn_token = tool_events.set_turn_context(
                conversation_id=conversation_id,
                surface="server_api", stealth=False,
            )
            try:
                with (
                    mock.patch.dict(
                        os.environ, {"ORA_OVERSIGHT_SANDBOX": str(roots["data"])},
                    ),
                    mock.patch.object(
                        tool_events, "APPROVALS_PATH", str(approval_path),
                    ),
                    mock.patch.object(
                        tool_events, "GLOBAL_SINK_DEFAULT", str(event_path),
                    ),
                    mock.patch.object(
                        oversight_queue, "HUMAN_QUEUE_PATH", str(queue_path),
                    ),
                    mock.patch.object(
                        system_protection, "_actions_path",
                        return_value=str(actions_path),
                    ),
                    mock.patch.object(
                        server, "_delete_conversation_runtime",
                        side_effect=purge_exact,
                    ) as delete_runtime,
                ):
                    client = server.app.test_client()
                    first = client.post(
                        f"/api/conversation/{conversation_id}/delete-forever",
                    )
                    first_payload = json.loads(first.get_data(as_text=True))
                    self.assertEqual(first.status_code, 409, first_payload)
                    self.assertEqual(
                        first_payload["status"],
                        "awaiting_system_protection_approval",
                    )
                    self.assertTrue(first_payload["retry_required"])
                    delete_runtime.assert_not_called()
                    self.assertTrue(
                        (roots["sessions"] / conversation_id).is_dir(),
                    )

                    migrated = tool_events._load_approvals()
                    self.assertEqual(migrated["schema_version"], 2)
                    self.assertEqual(migrated["tokens"], [])
                    self.assertEqual(migrated["standing"], [])
                    self.assertEqual(len(migrated["pending"]), 1)
                    entry = oversight_queue.find_paused_by_id(
                        first_payload["queue_id"],
                    )
                    self.assertIsNotNone(entry)
                    approved = tool_events.resolve_gate_entry(
                        entry.to_dict(), approve=True,
                    )
                    self.assertIn("One-shot token", approved)

                    after_approval = tool_events._load_approvals()
                    self.assertEqual(len(after_approval["tokens"]), 1)
                    self.assertFalse(after_approval["tokens"][0]["used"])

                    retry = client.post(
                        f"/api/conversation/{conversation_id}/delete-forever",
                    )
                    retry_payload = json.loads(retry.get_data(as_text=True))
                    self.assertEqual(retry.status_code, 200, retry_payload)
                    self.assertEqual(retry_payload["conversation_id"], conversation_id)
                    self.assertEqual(retry_payload["tag"], "stealth")
                    self.assertEqual(retry_payload["action"], "delete_forever")
                    self.assertTrue(retry_payload["deleted"]["session_dir"])
                    self.assertEqual(retry_payload["deleted"]["task_tokens"], 1)
                    self.assertEqual(retry_payload["errors"], [])
                    self.assertEqual(purged, [conversation_id])
                    self.assertFalse(
                        (roots["sessions"] / conversation_id).exists(),
                    )
                    self.assertTrue((roots["sessions"] / sibling_id).is_dir())

                    post_purge_store = tool_events._load_approvals()
                    self.assertEqual(post_purge_store["tokens"], [])
                    self.assertTrue(all(
                        item.get("consumed")
                        for item in post_purge_store["pending"]
                    ))
            finally:
                tool_events.reset_turn_context(turn_token)
                tool_events._queued_hashes.clear()
                server._conversation_creation_tags.pop(
                    server._conversation_storage_identity(conversation_id), None,
                )
                server._deleted_conversations.discard(
                    server._conversation_storage_identity(conversation_id),
                )

            self.assertEqual(
                {path: path_state(path) for path in live_before}, live_before,
            )

    def test_delete_removes_ora_managed_layers_but_retains_flat_exports(self):
        with tempfile.TemporaryDirectory() as td:
            roots = self._roots(Path(td))
            target = "delete-me"

            _write_envelope(roots["sessions"], target, tag="stealth")
            archived = roots["sessions"] / "archived" / target
            archived.mkdir(parents=True)
            (archived / "conversation.json").write_text("{}")

            recovered_chunk = roots["conversations"] / "recovered.md"
            recovered_chunk.write_text(
                "---\nnexus:\ntype: chat\ntags:\nconversation_id: delete-me\n---\nsecret\n",
                encoding="utf-8",
            )
            other_chunk = roots["conversations"] / "other.md"
            other_chunk.write_text(
                "---\nnexus:\ntype: chat\ntags:\nconversation_id: other\n---\nkeep\n",
                encoding="utf-8",
            )
            target_raw = roots["raw"] / "target.md"
            target_raw.write_text(
                "# Session abc\n\npanel_id: delete-me\nmodel: test\n\n---\nsecret\n",
                encoding="utf-8",
            )
            other_raw = roots["raw"] / "other.md"
            other_raw.write_text("# Session xyz\n\npanel_id: other\n\n---\nkeep\n")

            chroma_chunk = roots["conversations"] / "from-chroma.md"
            chroma_chunk.write_text("indexed secret")
            chroma_raw = roots["raw"] / "from-chroma.md"
            chroma_raw.write_text("indexed raw secret")
            collection = _FakeCollection([
                {"id": "target-indexed", "metadata": {
                    "conversation_id": target,
                    "chunk_path": str(chroma_chunk),
                    "raw_path": str(chroma_raw),
                }},
                {"id": "other-indexed", "metadata": {
                    "conversation_id": "other",
                }},
            ])

            for folder, filename in (("pending", "target.json"),
                                     ("processed", "target.json")):
                (roots["raw"] / folder / filename).write_text(json.dumps({
                    "conversation_id": target, "panel_id": target, "tag": "private",
                }))
                (roots["raw"] / folder / f"other-{filename}").write_text(json.dumps({
                    "conversation_id": "other", "panel_id": "other",
                }))

            manifest_chunk = roots["conversations"] / "from-manifest.md"
            manifest_chunk.write_text("manifest secret")
            manifest = roots["data"] / "conversation-manifest.jsonl"
            manifest.write_text(
                json.dumps({"conversation_id": target,
                            "chunk_path": str(manifest_chunk),
                            "raw_path": str(target_raw), "tag": "private"}) + "\n" +
                json.dumps({"conversation_id": "other", "tag": ""}) + "\n"
            )
            failures = roots["data"] / "conversation-indexing-failures.jsonl"
            failures.write_text(
                json.dumps({"conversation_id": target, "error": "secret"}) + "\n" +
                json.dumps({"conversation_id": "other", "error": "keep"}) + "\n"
            )
            entity_index = roots["data"] / "entity-index.json"
            entity_index.write_text(
                json.dumps({"Sensitive title": ["Private Person"]}),
                encoding="utf-8",
            )

            sticky = roots["data"] / "risk-sticky.json"
            sticky.write_text(json.dumps({target: "high-risk", "other": "irreversible"}))
            live_tool_events = roots["data"] / "tool-events.jsonl"
            live_tool_events.write_text(
                json.dumps({"conversation_id": target, "event": "secret"}) + "\n" +
                json.dumps({"conversation_id": "other", "event": "keep"}) + "\n"
            )
            visual_emissions = roots["data"] / "visual-emission-log.jsonl"
            visual_emissions.write_text(
                json.dumps({"conversation_id": target, "event": "secret"}) + "\n" +
                json.dumps({"conversation_id": "other", "event": "keep"}) + "\n"
            )
            oversight = roots["data"] / "oversight"
            oversight.mkdir()
            human_queue = oversight / "human-queue.jsonl"
            human_queue.write_text(
                json.dumps({"conversation_id": target, "payload": "drop"}) + "\n" +
                json.dumps({"conversation_id": "other",
                            "discussion_conversation_id": target,
                            "payload": "keep"}) + "\n"
            )
            router_log = oversight / "router.jsonl"
            router_log.write_text(
                json.dumps({
                    "event": {"conversation_id": target, "payload": "drop"},
                    "action": "continue",
                }) + "\n" +
                json.dumps({
                    "event": {"conversation_id": "other", "payload": "keep"},
                    "action": "continue",
                }) + "\n"
            )
            legacy_dispatch_log = roots["data"].parent / "logs" / "session-old.log"
            legacy_dispatch_log.parent.mkdir()
            legacy_dispatch_log.write_text("uncorrelated secret\n")
            rotated = roots["data"] / "archive" / "tool-events-20260712.jsonl.gz"
            with gzip.open(rotated, "wt", encoding="utf-8") as stream:
                stream.write(json.dumps({"conversation_id": target, "event": "old secret"}) + "\n")
                stream.write(json.dumps({"conversation_id": "other", "event": "old keep"}) + "\n")

            legacy_export_dir = roots["vault"] / target
            legacy_export_dir.mkdir()
            (legacy_export_dir / "old.md").write_text("legacy")
            explicit_export = roots["vault"] / "User Named Export.md"
            explicit_export.write_text("explicit export remains")
            explicit_figure = roots["vault"] / "User Named Export.fig-1.svg"
            explicit_figure.write_text("<svg/>")
            explicit_sidecars = roots["vault"] / "User Named Export_files"
            explicit_sidecars.mkdir()
            (explicit_sidecars / "figure.png").write_bytes(b"png")
            from orchestrator.tools import daily_note
            daily_dir = roots["vault"].parent / "Daily Notes"
            daily_dir.mkdir()
            daily_path = daily_dir / "2026-07-12.md"
            daily_path.write_text(
                daily_note.render_note(
                    "2026-07-12",
                    [{"id": target, "name": "Delete me", "exchanges": 1,
                      "first": "09:00", "last": "09:00", "gist": "secret"}],
                    [], [], [],
                ) + "\nUser-authored Daily Note line stays.\n",
                encoding="utf-8",
            )
            managed_transcript = roots["vault"].parent / "Transcript — Managed.md"
            managed_transcript.write_text(
                "---\n"
                "type: transcript\n"
                "tags:\n  - incubating\n"
                "artifact_kind: conversation_transcript\n"
                "managed_by: ora\n"
                f"source_file: {target}\n"
                "---\n\nDelete this managed transcript.\n",
                encoding="utf-8",
            )
            user_transcript = roots["vault"].parent / "Transcript — User Export.md"
            user_transcript.write_text(
                f"---\ntype: transcript\ntags:\nsource_file: {target}\n---\n\nKeep.\n",
                encoding="utf-8",
            )
            vault_index = roots["data"] / "vault-index.json"
            vault_index.write_text(json.dumps({
                "version": 1,
                "vault_path": str(roots["vault"].parent),
                "entries": [
                    {"vault_path": managed_transcript.name, "summary": "secret"},
                    {"vault_path": user_transcript.name, "summary": "keep"},
                ],
            }), encoding="utf-8")

            result = self._run_delete(target, roots, collection=collection)

            self.assertEqual(result["conversation_id"], target)
            self.assertEqual(result["tag"], "stealth")
            self.assertEqual(result["action"], "delete_forever")
            self.assertTrue(result["retained"]["explicit_vault_exports"])
            self.assertFalse((roots["sessions"] / target).exists())
            self.assertFalse(archived.exists())
            self.assertFalse(recovered_chunk.exists())
            self.assertFalse(chroma_chunk.exists())
            self.assertFalse(chroma_raw.exists())
            self.assertFalse(manifest_chunk.exists())
            self.assertFalse(target_raw.exists())
            self.assertFalse(entity_index.exists())
            self.assertTrue(result["deleted"]["entity_index_retired"])
            self.assertTrue(other_chunk.exists())
            self.assertTrue(other_raw.exists())
            self.assertFalse((roots["raw"] / "pending" / "target.json").exists())
            self.assertFalse((roots["raw"] / "processed" / "target.json").exists())
            self.assertTrue((roots["raw"] / "pending" / "other-target.json").exists())
            self.assertEqual(_read_jsonl(manifest), [{"conversation_id": "other", "tag": ""}])
            self.assertEqual(_read_jsonl(failures),
                             [{"conversation_id": "other", "error": "keep"}])
            self.assertEqual(json.loads(sticky.read_text()), {"other": "irreversible"})
            self.assertEqual(_read_jsonl(live_tool_events),
                             [{"conversation_id": "other", "event": "keep"}])
            self.assertEqual(_read_jsonl(visual_emissions),
                             [{"conversation_id": "other", "event": "keep"}])
            self.assertEqual(result["deleted"]["visual_emission_entries"], 1)
            self.assertEqual(_read_jsonl(human_queue), [{
                "conversation_id": "other",
                "discussion_conversation_id": None,
                "payload": "keep",
            }])
            self.assertEqual(_read_jsonl(router_log), [{
                "event": {"conversation_id": "other", "payload": "keep"},
                "action": "continue",
            }])
            self.assertEqual(
                result["deleted"]["oversight_log_entries"]["router.jsonl"], 1,
            )
            self.assertFalse(legacy_dispatch_log.exists())
            self.assertIn(
                str(legacy_dispatch_log),
                result["deleted"]["legacy_dispatch_session_logs"],
            )
            with gzip.open(rotated, "rt", encoding="utf-8") as stream:
                archived_events = [json.loads(line) for line in stream if line.strip()]
            self.assertEqual(archived_events,
                             [{"conversation_id": "other", "event": "old keep"}])
            self.assertFalse(legacy_export_dir.exists())
            self.assertTrue(explicit_export.exists())
            self.assertTrue(explicit_figure.exists())
            self.assertTrue((explicit_sidecars / "figure.png").exists())
            daily_body = daily_path.read_text(encoding="utf-8")
            self.assertNotIn("Delete me", daily_body)
            self.assertIn("User-authored Daily Note line stays.", daily_body)
            self.assertEqual(result["deleted"]["daily_note_summaries"], 1)
            self.assertFalse(managed_transcript.exists())
            self.assertTrue(user_transcript.exists())
            self.assertEqual(result["deleted"]["vault_index_entries"], 1)
            self.assertEqual(
                [row["vault_path"] for row in json.loads(
                    vault_index.read_text(encoding="utf-8")
                )["entries"]],
                [user_transcript.name],
            )
            self.assertEqual(result["deleted"]["chromadb_records"], 1)
            self.assertNotIn("target-indexed", collection.rows)
            self.assertIn("other-indexed", collection.rows)

            # A second call is a safe no-op over already-removed Ora state.
            second = self._run_delete(target, roots)
            self.assertEqual(second["action"], "delete_forever")
            self.assertTrue(second["retained"]["explicit_vault_exports"])
            self.assertTrue(explicit_export.exists())
            self.assertTrue(explicit_figure.exists())
            self.assertTrue((explicit_sidecars / "figure.png").exists())

    def test_delete_detaches_direct_children_without_copying_or_guessing(self):
        with tempfile.TemporaryDirectory() as td:
            roots = self._roots(Path(td))
            parent_messages = [
                {"role": "user", "content": "parent prompt"},
                {"role": "assistant", "content": "parent answer"},
            ]
            _write_envelope(
                roots["sessions"], "parent", tag="stealth",
                messages=parent_messages,
            )

            memory.fork_conversation(
                "parent", "current-child", sessions_root=roots["sessions"],
                fork_point_chunk_id="legacy-readable-pointer",
            )
            memory.save_turn_spatial_state(
                "current-child", "local prompt", "local answer",
                sessions_root=roots["sessions"],
            )

            legacy_exact = {
                "conversation_id": "legacy-exact",
                "tag": "",
                "parent_conversation_id": "parent",
                "fork_point_chunk_id": "old-chunk",
                "messages": parent_messages + [
                    {"role": "user", "content": "legacy local"},
                    {"role": "assistant", "content": "legacy answer"},
                ],
                "project_ids": [],
            }
            legacy_ambiguous = {
                "conversation_id": "legacy-ambiguous",
                "tag": "",
                "parent_conversation_id": "parent",
                "fork_point_chunk_id": "old-other-chunk",
                "messages": [
                    {"role": "user", "content": "not the parent prefix"},
                    {"role": "assistant", "content": "must remain"},
                ],
                "project_ids": [],
            }
            for envelope in (legacy_exact, legacy_ambiguous):
                path = (
                    roots["sessions"] / envelope["conversation_id"]
                    / "conversation.json"
                )
                path.parent.mkdir()
                path.write_text(json.dumps(envelope), encoding="utf-8")
            grandchild_path = _write_envelope(
                roots["sessions"], "grandchild",
                messages=[{"role": "user", "content": "grandchild local"}],
            )
            grandchild = json.loads(grandchild_path.read_text())
            grandchild.update({
                "parent_conversation_id": "current-child",
                "fork_point_message_count": 2,
                "fork_point_chunk_id": None,
            })
            grandchild_path.write_text(json.dumps(grandchild), encoding="utf-8")

            result = self._run_delete("parent", roots)

            self.assertFalse((roots["sessions"] / "parent").exists())
            current = memory.load_conversation_json(
                "current-child", sessions_root=roots["sessions"],
            )
            self.assertIsNone(current["parent_conversation_id"])
            self.assertIsNone(current["fork_point_message_count"])
            self.assertIsNone(current["fork_point_chunk_id"])
            self.assertEqual(
                [message["content"] for message in current["messages"]],
                ["local prompt", "local answer"],
            )

            exact = memory.load_conversation_json(
                "legacy-exact", sessions_root=roots["sessions"],
            )
            self.assertEqual(
                [message["content"] for message in exact["messages"]],
                ["legacy local", "legacy answer"],
            )
            ambiguous = memory.load_conversation_json(
                "legacy-ambiguous", sessions_root=roots["sessions"],
            )
            self.assertEqual(ambiguous["messages"], legacy_ambiguous["messages"])
            self.assertIsNone(ambiguous["parent_conversation_id"])
            self.assertIn("legacy-ambiguous", " ".join(result["errors"]))
            self.assertIn("preserved", " ".join(result["errors"]))

            untouched_grandchild = json.loads(grandchild_path.read_text())
            self.assertEqual(
                untouched_grandchild["parent_conversation_id"], "current-child",
            )
            detachment = result["deleted"]["fork_children"]
            self.assertCountEqual(
                detachment["children_detached"],
                ["current-child", "legacy-exact", "legacy-ambiguous"],
            )
            self.assertEqual(detachment["legacy_prefix_messages_removed"], 2)
            self.assertEqual(
                detachment["ambiguous_children_preserved"],
                ["legacy-ambiguous"],
            )

    def test_collection_not_found_is_idempotent_but_other_failures_are_loud(self):
        from chromadb.errors import NotFoundError

        with tempfile.TemporaryDirectory() as td:
            roots = self._roots(Path(td) / "missing")
            absent = self._run_delete(
                "already-gone",
                roots,
                collection_error=NotFoundError("collection does not exist"),
            )
            self.assertEqual(absent["errors"], [])

            broken_roots = self._roots(Path(td) / "broken")
            broken = self._run_delete(
                "must-report",
                broken_roots,
                collection_error=RuntimeError("synthetic Chroma corruption"),
            )
            self.assertIn(
                "synthetic Chroma corruption",
                " ".join(broken["errors"]),
            )

    def test_session_symlink_is_unlinked_but_external_target_is_reported(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            roots = self._roots(base / "owned")
            external = base / "external-session"
            external.mkdir()
            outside = external / "conversation.json"
            outside.write_text(json.dumps({
                "conversation_id": "escape",
                "tag": "stealth",
                "messages": [{"role": "user", "content": "retain"}],
            }), encoding="utf-8")
            link = roots["sessions"] / "escape"
            link.symlink_to(external, target_is_directory=True)

            result = self._run_delete("escape", roots)

            self.assertFalse(link.exists())
            self.assertFalse(link.is_symlink())
            self.assertTrue(outside.exists())
            self.assertFalse(result["deleted"]["session_dir"])
            self.assertTrue(result["deleted"]["session_symlink_removed"])
            self.assertEqual(
                result["deleted"]["session_symlink_target_residue"],
                [str(external.resolve())],
            )
            self.assertIn(
                "target residue requires explicit owner action",
                " ".join(result["errors"]),
            )

    def test_delete_reports_incomplete_managed_transcript_scan(self):
        with tempfile.TemporaryDirectory() as td:
            roots = self._roots(Path(td))
            _write_envelope(roots["sessions"], "target", tag="stealth")
            vault_root = roots["vault"].parent
            original_iterdir = Path.iterdir

            def fail_vault_iterdir(path):
                if path == vault_root:
                    raise PermissionError("synthetic delete scan denial")
                return original_iterdir(path)

            with mock.patch.object(Path, "iterdir", fail_vault_iterdir):
                result = self._run_delete("target", roots)

            self.assertEqual(result["action"], "delete_forever")
            self.assertIn(
                "synthetic delete scan denial", " ".join(result["errors"]),
            )

    def test_legacy_mixed_case_delete_removes_casefolded_derivatives(self):
        with tempfile.TemporaryDirectory() as td:
            roots = self._roots(Path(td))
            _write_envelope(roots["sessions"], "LegacyA", tag="stealth")
            staging = roots["data"] / "extraction-staging"
            staging.mkdir()
            derivative = staging / "private-note.md"
            derivative.write_text(
                "---\ntype: working\ntags:\n  - private\n"
                "source_file: legacya\n---\n\nSensitive.\n",
                encoding="utf-8",
            )
            knowledge = _FakeCollection([{
                "id": str(derivative.resolve()),
                "metadata": {
                    "source_file": "legacya",
                    "path": str(derivative.resolve()),
                    "tag_private": True,
                },
            }])

            result = self._run_delete(
                "LegacyA", roots, knowledge_collection=knowledge,
            )

            self.assertFalse(derivative.exists())
            self.assertEqual(knowledge.rows, {})
            self.assertEqual(result["deleted"]["runtime_knowledge_records"], 1)

    def test_raw_log_scan_never_claims_sibling_session_derivatives(self):
        with tempfile.TemporaryDirectory() as td:
            roots = self._roots(Path(td))
            _write_envelope(roots["sessions"], "target", tag="stealth")
            (roots["raw"] / "target.md").write_text(
                "# Session target-run\n\npanel_id: target\n\n---\nsecret\n",
                encoding="utf-8",
            )
            (roots["raw"] / "sibling.md").write_text(
                "# Session sibling-run\n\npanel_id: sibling\n\n---\nkeep\n",
                encoding="utf-8",
            )
            staging = roots["data"] / "extraction-staging"
            staging.mkdir()
            target_note = staging / "target.md"
            sibling_note = staging / "sibling.md"
            target_note.write_text(
                "---\ntype: working\ntags:\nsource_file: target-run\n---\ntarget\n",
                encoding="utf-8",
            )
            sibling_note.write_text(
                "---\ntype: working\ntags:\nsource_file: sibling-run\n---\nsibling\n",
                encoding="utf-8",
            )
            knowledge = _FakeCollection([
                {"id": str(target_note.resolve()), "metadata": {
                    "source_file": "target-run", "path": str(target_note.resolve()),
                }},
                {"id": str(sibling_note.resolve()), "metadata": {
                    "source_file": "sibling-run", "path": str(sibling_note.resolve()),
                }},
            ])

            self._run_delete(
                "target", roots, knowledge_collection=knowledge,
            )

            self.assertFalse(target_note.exists())
            self.assertTrue(sibling_note.exists())
            self.assertNotIn(str(target_note.resolve()), knowledge.rows)
            self.assertIn(str(sibling_note.resolve()), knowledge.rows)

    def test_manifest_only_deletes_owned_artifact_roots_and_retains_unsafe_rows(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            roots = self._roots(base / "scoped")
            target = "manifest-boundary"

            external_chunk = base / "external-chunk.md"
            external_raw = base / "external-raw.md"
            external_chunk.write_text("must survive", encoding="utf-8")
            external_raw.write_text("must survive", encoding="utf-8")
            owned_chunk = roots["conversations"] / "owned-chunk.md"
            owned_chunk.write_text("remove me", encoding="utf-8")

            unsafe = {
                "conversation_id": target,
                "chunk_path": str(external_chunk),
                "raw_path": str(external_raw),
            }
            unrelated = {"conversation_id": "other", "tag": ""}
            manifest = roots["data"] / "conversation-manifest.jsonl"
            manifest.write_text(
                json.dumps(unsafe) + "\n"
                + json.dumps({
                    "conversation_id": target,
                    "chunk_path": str(owned_chunk),
                }) + "\n"
                + json.dumps(unrelated) + "\n",
                encoding="utf-8",
            )

            result = self._run_delete(target, roots)

            self.assertTrue(external_chunk.exists())
            self.assertTrue(external_raw.exists())
            self.assertFalse(owned_chunk.exists())
            self.assertEqual(_read_jsonl(manifest), [unsafe, unrelated])
            self.assertEqual(result["deleted"]["manifest_orphans_removed"], 1)
            self.assertGreaterEqual(
                sum(
                    ("outside expected root" in error
                     or "lacks typed Ora ownership" in error)
                    for error in result["errors"]
                ),
                2,
            )

    def test_approval_and_rotated_event_rewrites_use_dynamic_paths_and_locks(self):
        from orchestrator import tool_events

        with tempfile.TemporaryDirectory() as td:
            roots = self._roots(Path(td))
            target = "locked-delete"
            approvals = roots["data"] / "dynamic" / "execution-approvals.json"
            approvals.parent.mkdir()
            standing = {"scope": "project:ora", "granted_via": "test"}
            with mock.patch.object(
                tool_events, "APPROVALS_PATH", str(approvals),
            ):
                def seed_signed_store():
                    data = tool_events._empty_approvals()
                    data["tokens"] = [
                        {"token": "drop", "conversation_id": target},
                        {"token": "keep", "conversation_id": "other"},
                    ]
                    data["standing"] = [standing]
                    tool_events._save_approvals(data)

                tool_events._with_approvals_lock(seed_signed_store)

            archive = roots["data"] / "archive" / "tool-events-locked.jsonl.gz"
            with gzip.open(archive, "wt", encoding="utf-8") as stream:
                stream.write(json.dumps({
                    "conversation_id": target, "event": "drop",
                }) + "\n")
                stream.write(json.dumps({
                    "conversation_id": "other", "event": "keep",
                }) + "\n")

            real_locked_file = runtime_paths.locked_file
            locked_paths: list[Path] = []
            lock_entries: list[tuple[Path, tuple[Path, ...]]] = []
            lock_stack: list[Path] = []

            @contextlib.contextmanager
            def record_lock(path, *args, **kwargs):
                resolved = Path(path)
                locked_paths.append(resolved)
                with real_locked_file(path, *args, **kwargs):
                    lock_entries.append((resolved, tuple(lock_stack)))
                    lock_stack.append(resolved)
                    try:
                        yield
                    finally:
                        lock_stack.pop()

            with (
                mock.patch.object(
                    tool_events, "_approvals_path", return_value=str(approvals),
                ) as resolve_approvals,
                mock.patch.object(
                    runtime_paths, "locked_file", side_effect=record_lock,
                ),
                mock.patch.object(
                    tool_events._rp, "locked_file", side_effect=record_lock,
                ),
            ):
                result = self._run_delete(target, roots)

            self.assertGreaterEqual(resolve_approvals.call_count, 1)
            self.assertIn(approvals, locked_paths)
            self.assertIn(archive, locked_paths)
            archive_parents = [
                parents for path, parents in lock_entries if path == archive
            ]
            self.assertEqual(len(archive_parents), 1)
            self.assertIn(roots["data"] / "tool-events.jsonl",
                          archive_parents[0])
            with mock.patch.object(
                tool_events, "APPROVALS_PATH", str(approvals),
            ):
                approval_data = tool_events._load_approvals()
            self.assertEqual(approval_data["tokens"], [
                {"token": "keep", "conversation_id": "other"},
            ])
            self.assertEqual(approval_data["standing"], [standing])
            self.assertEqual(result["deleted"]["task_tokens"], 1)
            with gzip.open(archive, "rt", encoding="utf-8") as stream:
                self.assertEqual(
                    [json.loads(line) for line in stream if line.strip()],
                    [{"conversation_id": "other", "event": "keep"}],
                )

    def test_invalid_ids_cannot_escape_configured_roots(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            roots = self._roots(base / "scoped")
            sentinel = base / "sentinel.txt"
            sentinel.write_text("must survive")

            for invalid in ("", "..", "../sentinel.txt", "/tmp/not-a-dialogue"):
                with self.assertRaises(ValueError, msg=invalid):
                    self._run_delete(invalid, roots)
                self.assertTrue(sentinel.exists(), invalid)
                self.assertEqual(sentinel.read_text(), "must survive")

    def test_delete_removes_runtime_derivatives_but_not_flat_export(self):
        with tempfile.TemporaryDirectory() as td:
            roots = self._roots(Path(td))
            target = "derived-delete"
            session_id = "legacy-session-7"
            _write_envelope(roots["sessions"], target, tag="stealth")

            staging = roots["data"] / "extraction-staging"
            promoted = roots["data"] / "extraction-promoted"
            engrams = roots["vault"].parent / "Engrams"
            for path in (staging, promoted, engrams):
                path.mkdir(parents=True, exist_ok=True)
            by_conversation = staging / "By Conversation.md"
            by_conversation.write_text(
                "---\ntype: working\ntags:\nsource_file: derived-delete\n---\n",
                encoding="utf-8",
            )
            legacy = promoted / "Legacy.md"
            legacy.write_text(
                "---\ntype: working\ntags:\n---\n\n"
                "- Source: extracted from session legacy-session-7\n",
                encoding="utf-8",
            )
            engram = engrams / "Auto Engram.md"
            engram.write_text(
                "---\ntype: engram\ntags:\n"
                "artifact_kind: conversation_runtime_derivative\n"
                "managed_by: ora\nsource_file: derived-delete\n---\n",
                encoding="utf-8",
            )
            explicit = roots["vault"] / "Explicit Export.md"
            explicit.write_text(
                "---\ntype: chat\ntags:\nsource_file: derived-delete\n---\n",
                encoding="utf-8",
            )
            log = roots["data"] / "session-logs"
            log.mkdir()
            (log / f"{session_id}.json").write_text("{}")
            (log / f"{session_id}-runtime.json").write_text("{}")

            conversations = _FakeCollection([{
                "id": "turn",
                "metadata": {
                    "conversation_id": target,
                    "session_id": session_id,
                },
            }])
            knowledge = _FakeCollection([
                {"id": str(by_conversation.resolve()), "metadata": {
                    "source_file": target,
                }},
                {"id": str(legacy.resolve()), "metadata": {
                    "source_file": session_id,
                }},
                {"id": str(engram.resolve()) + "#chunk-0", "metadata": {
                    "path": str(engram.resolve()),
                }},
                {"id": "other", "metadata": {"source_file": "other"}},
            ])
            result = self._run_delete(
                target, roots,
                collection=conversations,
                knowledge_collection=knowledge,
            )

            for path in (by_conversation, legacy, engram,
                         log / f"{session_id}.json",
                         log / f"{session_id}-runtime.json"):
                self.assertFalse(path.exists(), str(path))
            self.assertTrue(explicit.exists())
            self.assertIn("other", knowledge.rows)
            self.assertNotIn(str(by_conversation.resolve()), knowledge.rows)
            self.assertNotIn(str(engram.resolve()) + "#chunk-0", knowledge.rows)
            self.assertGreaterEqual(
                len(result["deleted"]["runtime_derivative_files"]), 3,
            )

    def test_delete_retains_ambiguous_user_vault_note_and_knowledge_row(self):
        with tempfile.TemporaryDirectory() as td:
            roots = self._roots(Path(td))
            target = "cited-dialogue"
            _write_envelope(roots["sessions"], target, tag="stealth")
            engrams = roots["vault"].parent / "Engrams"
            engrams.mkdir()
            user_note = engrams / "User Authored.md"
            user_note.write_text(
                "---\ntype: engram\ntags:\nsource_file: cited-dialogue\n---\n\n"
                "# User Authored\n\nThis note merely cites the Dialogue.\n",
                encoding="utf-8",
            )
            row_id = str(user_note.resolve())
            knowledge = _FakeCollection([{
                "id": row_id,
                "metadata": {
                    "path": row_id,
                    "source_file": target,
                },
            }])

            result = self._run_delete(
                target, roots,
                collection=_FakeCollection([]),
                knowledge_collection=knowledge,
            )

            self.assertTrue(user_note.exists())
            self.assertIn(row_id, knowledge.rows)
            self.assertIn(
                "lacks the complete Ora ownership marker",
                " ".join(result["errors"]),
            )

    def test_typed_custom_chunk_with_exact_marker_is_deleted(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            roots = self._roots(base / "runtime")
            target = "custom-output"
            _write_envelope(roots["sessions"], target, tag="stealth")
            custom_root = base / "custom-chunks"
            custom_root.mkdir()
            custom = custom_root / "turn.md"
            custom.write_text(
                "---\nnexus:\ntype: chat\ntags:\n---\n\n"
                '<!-- ora-conversation-id: "custom-output" -->\n'
                "secret\n",
                encoding="utf-8",
            )
            manifest = roots["data"] / "conversation-manifest.jsonl"
            manifest.write_text(json.dumps({
                "conversation_id": target,
                "chunk_path": str(custom),
                "chunk_root": str(custom_root),
                "artifact_kind": "conversation_chunk",
                "managed_by": "ora",
            }) + "\n")

            result = self._run_delete(target, roots)
            self.assertFalse(custom.exists())
            self.assertEqual(_read_jsonl(manifest), [])
            self.assertFalse(result["errors"])

    def test_layer_failure_is_reported_and_other_layers_continue(self):
        with tempfile.TemporaryDirectory() as td:
            roots = self._roots(Path(td))
            target = "partial-delete"
            _write_envelope(roots["sessions"], target, tag="stealth")
            raw_path = roots["raw"] / "target.md"
            raw_path.write_text(f"# Session abc\n\npanel_id: {target}\n\n---\n")

            original_rmtree = closeout.shutil.rmtree

            def fail_session(path, *args, **kwargs):
                if Path(path) == roots["sessions"] / target:
                    raise OSError("synthetic session delete failure")
                return original_rmtree(path, *args, **kwargs)

            with mock.patch.object(closeout.shutil, "rmtree", side_effect=fail_session):
                result = self._run_delete(target, roots)

            self.assertIn("synthetic session delete failure", " ".join(result["errors"]))
            self.assertTrue((roots["sessions"] / target).exists())
            self.assertFalse(raw_path.exists(), "raw cleanup must continue after session failure")


class TestServerLifecycleWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repo = Path(__file__).resolve().parents[2]
        server_dir = str(repo / "server")
        if server_dir not in sys.path:
            sys.path.insert(0, server_dir)
        from server import app as server  # type: ignore
        cls.server = server

    def setUp(self):
        self.server._conversation_creation_tags.clear()
        self.server._deleted_conversations.clear()
        self.server._unreadable_conversations.clear()
        self.server._closed_conversations.clear()

    def tearDown(self):
        self.server._conversation_creation_tags.clear()
        self.server._deleted_conversations.clear()
        self.server._unreadable_conversations.clear()
        self.server._closed_conversations.clear()
        self.server._session_data.clear()
        self.server._bridge_state.clear()

    def test_effective_tag_distinguishes_missing_from_standard_envelope(self):
        with mock.patch.object(memory, "load_conversation_json", return_value=None):
            self.assertEqual(
                self.server._effective_conversation_tag("new", "stealth"),
                "stealth",
            )
            # The first creation request wins until an envelope exists.
            self.assertEqual(
                self.server._effective_conversation_tag("new", "private"),
                "stealth",
            )

        with mock.patch.object(
            memory, "load_conversation_json", return_value={"tag": "", "messages": []},
        ):
            self.assertEqual(
                self.server._effective_conversation_tag("existing", "stealth"),
                "",
            )
        with mock.patch.object(
            memory,
            "load_conversation_json",
            return_value={"tag": "private", "messages": []},
        ):
            self.assertEqual(
                self.server._effective_conversation_tag("private", ""),
                "private",
            )

    def test_chat_logs_and_invokes_with_authoritative_tag(self):
        captured: dict[str, str] = {}

        def fake_pending(payload):
            captured["pending_tag"] = payload["tag"]
            return "submission"

        def fake_invoke(*_args, **kwargs):
            captured["invoke_tag"] = kwargs["tag"]
            return json.dumps({"status": "ok"})

        with (
            mock.patch.object(
                memory,
                "load_conversation_json",
                return_value={"tag": "private", "messages": []},
            ),
            mock.patch.object(self.server, "_log_pending_submission",
                              side_effect=fake_pending),
            mock.patch.object(self.server, "_invoke_pipeline",
                              side_effect=fake_invoke),
        ):
            response = self.server.app.test_client().post("/chat", json={
                "message": "hello",
                "panel_id": "authoritative-tag",
                "tag": "stealth",
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured, {
            "pending_tag": "private",
            "invoke_tag": "private",
        })

    def test_first_turn_stealth_suppresses_trace_before_envelope_exists(self):
        from orchestrator import pipeline_trace
        with (
            mock.patch.object(memory, "load_conversation_json", return_value=None),
            mock.patch.object(self.server, "load_config", return_value={}),
            mock.patch.object(self.server, "get_endpoint", return_value=None),
            mock.patch.object(pipeline_trace, "start_trace", return_value=None) as start,
        ):
            list(self.server._pipeline_stream(
                "secret prompt", [], panel_id="first-stealth",
                conversation_tag="stealth",
            ))
        self.assertTrue(start.call_args.kwargs["stealth"])

    def test_privacy_endpoint_rejects_stealth_target(self):
        response = self.server.app.test_client().post(
            "/api/conversation/test/privacy-tag",
            json={"tag": "stealth"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("creation-only", response.get_data(as_text=True))

    def test_fork_endpoint_resolves_displayed_turn_and_reports_counts(self):
        import conversation_memory as legacy_import_memory

        with tempfile.TemporaryDirectory() as td:
            sessions = Path(td) / "sessions"
            _write_envelope(
                sessions, "api-parent",
                messages=[
                    {"role": "user", "content": "first"},
                    {"role": "assistant", "content": "first answer"},
                    {"role": "user", "content": "second"},
                    {"role": "assistant", "content": "second answer"},
                ],
            )
            with (
                mock.patch.object(memory, "_DEFAULT_SESSIONS_ROOT", sessions),
                mock.patch.object(
                    legacy_import_memory, "_DEFAULT_SESSIONS_ROOT", sessions,
                ),
            ):
                response = self.server.app.test_client().post(
                    "/api/conversation/api-parent/fork",
                    json={
                        "new_id": "api-child",
                        "fork_point_turn_index": 0,
                    },
                )
                invalid = self.server.app.test_client().post(
                    "/api/conversation/api-parent/fork",
                    json={
                        "new_id": "invalid-child",
                        "fork_point_turn_index": 2,
                    },
                )

            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            payload = json.loads(response.get_data(as_text=True))
            self.assertEqual(payload["fork_point_message_count"], 2)
            self.assertEqual(payload["inherited_message_count"], 2)
            self.assertEqual(payload["local_message_count"], 0)
            child = json.loads(
                (sessions / "api-child" / "conversation.json").read_text()
            )
            self.assertEqual(child["messages"], [])
            self.assertEqual(invalid.status_code, 400)
            self.assertFalse((sessions / "invalid-child").exists())

    def test_fork_endpoint_rejects_weaker_child_privacy(self):
        import conversation_memory as legacy_import_memory

        with tempfile.TemporaryDirectory() as td:
            sessions = Path(td) / "sessions"
            _write_envelope(
                sessions, "private-api-parent", tag="private",
                messages=[{"role": "user", "content": "private source"}],
            )
            with (
                mock.patch.object(memory, "_DEFAULT_SESSIONS_ROOT", sessions),
                mock.patch.object(
                    legacy_import_memory, "_DEFAULT_SESSIONS_ROOT", sessions,
                ),
            ):
                response = self.server.app.test_client().post(
                    "/api/conversation/private-api-parent/fork",
                    json={"new_id": "standard-api-child", "tag": ""},
                )
            self.assertEqual(response.status_code, 400)
            self.assertIn("privacy", response.get_data(as_text=True))
            self.assertFalse((sessions / "standard-api-child").exists())

    def test_deleted_tombstone_refuses_late_save(self):
        self.server._deleted_conversations.add("gone")
        with mock.patch.object(
            self.server, "_save_conversation_unlocked",
        ) as underlying:
            result = self.server._save_conversation(
                "prompt", "answer", "gone", True, "private",
            )
        self.assertIsNone(result)
        underlying.assert_not_called()

    def test_runtime_cleanup_forgets_sidebar_turn_window(self):
        self.server._render_conversation_lookup["render-aside"] = (
            "aside-dialogue"
        )
        with (
            mock.patch.object(self.server, "SIDEBAR_WINDOW_AVAILABLE", True),
            mock.patch.object(
                self.server, "clear_sidebar_window", return_value=1,
            ) as clear_sidebar,
            mock.patch.object(
                self.server, "_purge_media_library_staging", return_value=0,
            ),
        ):
            result = self.server._clear_conversation_runtime_state(
                "Aside-Dialogue",
            )

        clear_sidebar.assert_called_once_with("Aside-Dialogue")
        self.assertEqual(result["cleared"]["sidebar_windows"], 1)
        self.assertNotIn("render-aside", self.server._render_conversation_lookup)
        self.assertFalse(result["errors"])

    def test_unreadable_existing_envelope_is_not_treated_as_new_standard(self):
        with tempfile.TemporaryDirectory() as td:
            corrupt = Path(td) / "conversation.json"
            corrupt.write_text("{not-json", encoding="utf-8")
            with (
                mock.patch.object(memory, "load_conversation_json",
                                  return_value=None),
                mock.patch.object(memory, "_conversation_path",
                                  return_value=corrupt),
                mock.patch.object(self.server, "_delete_conversation_runtime") as delete,
            ):
                tag = self.server._effective_conversation_tag(
                    "existing-corrupt", "",
                )
                response = self.server.app.test_client().post(
                    "/api/conversation/existing-corrupt/close",
                )
        self.assertEqual(tag, "stealth")
        self.assertEqual(response.status_code, 409)
        delete.assert_not_called()

    def test_cross_origin_delete_is_rejected_before_purge(self):
        with mock.patch.object(
            self.server, "_delete_conversation_runtime",
        ) as delete:
            response = self.server.app.test_client().post(
                "/api/conversation/csrf-target/delete-forever",
                headers={"Origin": "https://attacker.example"},
            )
        self.assertEqual(response.status_code, 403)
        delete.assert_not_called()

    def test_delete_forever_route_refuses_retained_dialogues_before_approval(self):
        from orchestrator import system_protection

        for tag in ("", "private"):
            with self.subTest(tag=tag):
                with (
                    mock.patch.object(
                        memory, "read_conversation_history_envelope",
                        return_value={"tag": tag, "messages": []},
                    ),
                    mock.patch.object(
                        system_protection, "authorize_server_action",
                    ) as authorize,
                ):
                    response = self.server.app.test_client().post(
                        "/api/conversation/retained/delete-forever",
                    )
                self.assertEqual(response.status_code, 409)
                self.assertIn("use Close", response.get_data(as_text=True))
                authorize.assert_not_called()

    def test_delete_runtime_refuses_nonstealth_without_tombstone_or_purge(self):
        for tag in ("", "private"):
            conversation_id = f"retained-{tag or 'standard'}"
            self.server._deleted_conversations.discard(conversation_id)
            with self.subTest(tag=tag):
                with (
                    mock.patch.object(
                        memory, "read_conversation_history_envelope",
                        return_value={"tag": tag, "messages": []},
                    ),
                    mock.patch.object(
                        closeout, "delete_conversation_forever",
                    ) as purge,
                ):
                    with self.assertRaises(PermissionError):
                        self.server._delete_conversation_runtime(conversation_id)
                self.assertNotIn(
                    conversation_id, self.server._deleted_conversations,
                )
                purge.assert_not_called()

    def test_clarification_resume_and_skip_refresh_history_and_contributors_under_lock(self):
        import boot as runtime_boot

        fresh_history = [{"role": "assistant", "content": "fresh history"}]
        fresh_bundle = {
            "units": [{
                "lane": "contributor", "unit_id": "fresh-unit",
                "source_id": "selected-source-0", "content": "fresh source",
            }],
            "sources": [{
                "source_id": "selected-source-0", "status": "available",
            }],
            "exclude_conversation_ids": ["fresh-source"],
            "exclude_paths": [],
        }

        for route, payload in (
            ("/api/clarification", {"panel_id": "refresh-resume", "answers": "detail"}),
            ("/api/clarification/skip", {"panel_id": "refresh-skip"}),
        ):
            panel_id = payload["panel_id"]
            captured = {}
            self.server._pending_clarification[panel_id] = {
                "step1": {
                    "mode": "simple", "triage_tier": 1,
                    "cleaned_prompt": "original",
                    "operational_notation": "original",
                    "pre_routing": {},
                },
                "config": {},
                "history": [{"role": "assistant", "content": "stale history"}],
                "user_input": "original",
                "images": None,
                "extra_context": {
                    "contributor_bundle": {
                        "units": [{"content": "stale source"}],
                        "sources": [{"status": "available"}],
                    },
                },
                "conversation_tag": "",
                "trace_ref": None,
            }
            lifecycle_lock = self.server._conversation_lifecycle_lock(panel_id)

            def authoritative(_conversation_id, _supplied=None):
                self.assertTrue(lifecycle_lock._is_owned())
                return fresh_history, {"source": "conversation_json"}

            def contributors(_conversation_id, *, target_tag):
                self.assertTrue(lifecycle_lock._is_owned())
                self.assertEqual(target_tag, "private")
                return fresh_bundle

            def run_from_step2(_step1, _config, history, _user_input, *args, **kwargs):
                self.assertTrue(lifecycle_lock._is_owned())
                self.assertEqual(
                    runtime_boot._CONVERSATION_TAG_CV.get(), "private",
                )
                captured["history"] = history
                captured["extra_context"] = kwargs.get("extra_context")
                yield self.server._sse("response", text="complete")

            def effective_tag(_conversation_id, _requested=""):
                self.assertTrue(lifecycle_lock._is_owned())
                return "private"

            with self.subTest(route=route):
                with (
                    mock.patch.object(runtime_boot, "PIPELINE_TRACE_AVAILABLE", False),
                    mock.patch.object(
                        self.server, "_effective_conversation_tag",
                        side_effect=effective_tag,
                    ),
                    mock.patch.object(
                        self.server, "_authoritative_dialogue_history",
                        side_effect=authoritative,
                    ),
                    mock.patch.object(
                        self.server, "build_contributor_bundle",
                        side_effect=contributors,
                    ),
                    mock.patch.object(
                        self.server, "_run_pipeline_from_step2",
                        side_effect=run_from_step2,
                    ),
                    mock.patch.object(
                        self.server, "_save_conversation", return_value=None,
                    ),
                ):
                    response = self.server.app.test_client().post(route, json=payload)
                    response.get_data()

                self.assertEqual(response.status_code, 200)
                self.assertEqual(captured["history"], fresh_history)
                self.assertEqual(
                    captured["extra_context"]["contributor_bundle"], fresh_bundle,
                )

    def test_zero_turn_close_blocks_late_artifact_creation(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "missing" / "conversation.json"
            with (
                mock.patch.object(memory, "load_conversation_json", return_value=None),
                mock.patch.object(memory, "_conversation_path", return_value=missing),
            ):
                response = self.server.app.test_client().post(
                    "/api/conversation/closed-before-artifact/close",
                )
        self.assertEqual(response.status_code, 200)
        self.assertIn("closed-before-artifact", self.server._closed_conversations)
        with self.assertRaisesRegex(RuntimeError, "closed"):
            self.server._ensure_artifact_conversation_envelope(
                "closed-before-artifact", "private",
            )

    def test_durable_envelope_reconciles_closed_cache(self):
        identity = self.server._conversation_storage_identity("cache-state")
        self.server._closed_conversations.add(identity)
        with mock.patch.object(
            memory,
            "load_conversation_json",
            return_value={"conversation_id": "cache-state", "messages": []},
        ):
            self.assertFalse(self.server._is_conversation_closed("cache-state"))
        self.assertNotIn(identity, self.server._closed_conversations)

        self.server._closed_conversations.add(identity)
        with mock.patch.object(memory, "load_conversation_json", return_value=None):
            self.assertTrue(self.server._is_conversation_closed("cache-state"))
        self.assertIn(identity, self.server._closed_conversations)

    def test_privacy_route_uses_save_configured_chromadb_path(self):
        custom = os.path.abspath("/tmp/ora-custom-chroma")
        with (
            mock.patch.object(memory, "load_conversation_json",
                              return_value={"tag": "", "messages": []}),
            mock.patch.object(self.server, "load_config",
                              return_value={"chromadb_path": custom}),
            mock.patch.object(
                closeout, "update_conversation_privacy_tag",
                return_value={
                    "envelope_updated": True,
                    "errors": [],
                    "tag": "private",
                },
            ) as update,
            mock.patch(
                "orchestrator.document_input.update_conversation_tag",
                return_value={"jobs": 0, "outputs": 0, "errors": []},
            ),
        ):
            response = self.server.app.test_client().post(
                "/api/conversation/config-path/privacy-tag",
                json={"tag": "private"},
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(update.call_args.kwargs["chromadb_path"], custom)

    def test_fresh_privacy_route_creates_durable_zero_turn_envelope(self):
        with tempfile.TemporaryDirectory() as td:
            sessions = Path(td) / "sessions"

            def update(cid, target, **_kwargs):
                previous = memory.get_conversation_tag(
                    cid, sessions_root=sessions,
                )
                path = memory.set_conversation_tag(
                    cid, target, sessions_root=sessions,
                )
                return {
                    "conversation_id": cid,
                    "previous_tag": previous,
                    "tag": target,
                    "envelope_updated": path is not None,
                    "errors": [],
                }

            with (
                mock.patch.object(memory, "_DEFAULT_SESSIONS_ROOT", sessions),
                mock.patch.object(closeout, "update_conversation_privacy_tag",
                                  side_effect=update),
                mock.patch(
                    "orchestrator.document_input.update_conversation_tag",
                    return_value={"jobs": 0, "outputs": 0, "errors": []},
                ),
            ):
                response = self.server.app.test_client().post(
                    "/api/conversation/fresh-private/privacy-tag",
                    json={"tag": "private"},
                )
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            payload = json.loads(response.get_data(as_text=True))
            self.assertTrue(payload["envelope_created"])
            envelope = json.loads(
                (sessions / "fresh-private" / "conversation.json").read_text()
            )
            self.assertEqual(envelope["tag"], "private")
            self.assertEqual(envelope["messages"], [])

    def test_delete_waits_for_runtime_pipeline_before_purge(self):
        conversation_id = "runtime-barrier"
        runtime_started = threading.Event()
        release_runtime = threading.Event()
        purge_called = threading.Event()
        observed: dict[str, object] = {}

        class BlockingRuntimePipeline:
            def __init__(self, **_kwargs):
                pass

            def run_sync(self, session_data):
                observed["session_data"] = session_data
                runtime_started.set()
                release_runtime.wait(timeout=3)

        def fake_purge(cid, **_kwargs):
            purge_called.set()
            return {
                "conversation_id": cid,
                "action": "delete_forever",
                "deleted": {},
                "retained": {"explicit_vault_exports": True},
                "errors": [],
            }

        self.server._session_data[conversation_id] = {
            "session_id": "runtime-session",
            "model": "test-model",
        }
        self.server._conversation_creation_tags[conversation_id] = "stealth"
        with (
            mock.patch.object(self.server, "RUNTIME_PIPELINE_AVAILABLE", True),
            mock.patch.object(self.server, "RuntimePipeline",
                              BlockingRuntimePipeline),
            mock.patch.object(memory, "load_conversation_json",
                              return_value={"tag": "stealth", "messages": []}),
            mock.patch.object(
                memory, "read_conversation_history_envelope",
                return_value={"tag": "stealth", "messages": []},
            ),
            mock.patch.object(
                self.server, "_effective_conversation_tag",
                return_value="private",
            ),
            mock.patch.object(closeout, "delete_conversation_forever",
                              side_effect=fake_purge),
            mock.patch.object(self.server, "_quiesce_conversation_workers",
                              return_value={"cleaned": {}, "errors": []}),
            mock.patch.object(self.server, "_clear_conversation_runtime_state",
                              return_value={"cleared": {}, "errors": []}),
        ):
            runtime_thread = threading.Thread(
                target=self.server._run_end_of_session_pipeline,
                args=("prompt", "answer", conversation_id, {}, []),
            )
            runtime_thread.start()
            self.assertTrue(runtime_started.wait(timeout=2))
            delete_thread = threading.Thread(
                target=lambda: observed.setdefault(
                    "delete", self.server._delete_conversation_runtime(
                        conversation_id,
                    ),
                ),
            )
            delete_thread.start()
            self.assertFalse(purge_called.wait(timeout=0.1))
            release_runtime.set()
            runtime_thread.join(timeout=3)
            delete_thread.join(timeout=3)

        self.assertFalse(runtime_thread.is_alive())
        self.assertFalse(delete_thread.is_alive())
        self.assertTrue(purge_called.is_set())
        session_data = observed["session_data"]
        self.assertEqual(session_data.conversation_id, conversation_id)
        self.assertEqual(session_data.conversation_tag, "private")
        limitations = observed["delete"]["limitations"]
        self.assertIn("external_provider_retention", limitations)
        self.assertIn("repository_history", limitations)
        self.assertIn("explicit_and_configured_outputs", limitations)
        self.assertIn("registered_external_sources", limitations)

    def test_document_upload_uses_durable_conversation_staging_subtree(self):
        from orchestrator import document_input
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            start = mock.Mock(return_value="processing-1")
            with (
                mock.patch.object(self.server.rp, "ORA_HOME", home),
                mock.patch.object(document_input, "start", start),
                mock.patch.object(
                    self.server, "_ensure_artifact_conversation_envelope",
                    return_value=("private", False),
                ),
            ):
                response = self.server.app.test_client().post(
                    "/api/document/process",
                    data={
                        "conversation_id": "doc-conv",
                        "tag": "private",
                        "file": (io.BytesIO(b"sensitive"), "Report.pdf"),
                    },
                    content_type="multipart/form-data",
                )

            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            staged_path = Path(start.call_args.args[0])
            self.assertEqual(
                staged_path.parent,
                home / "staging" / "documents" / "doc-conv",
            )
            self.assertTrue(staged_path.is_file())

    def test_document_start_failure_preserves_envelope_context_in_response(self):
        from orchestrator import document_input
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            with (
                mock.patch.object(self.server.rp, "ORA_HOME", home),
                mock.patch.object(
                    document_input, "start",
                    side_effect=RuntimeError("synthetic start failure"),
                ),
                mock.patch.object(
                    self.server, "_ensure_artifact_conversation_envelope",
                    return_value=("private", True),
                ),
                mock.patch.object(
                    memory, "load_conversation_json",
                    return_value={"conversation_id": "doc-failure", "tag": "private"},
                ),
            ):
                response = self.server.app.test_client().post(
                    "/api/document/process",
                    data={
                        "conversation_id": "doc-failure",
                        "tag": "private",
                        "file": (io.BytesIO(b"sensitive"), "Report.pdf"),
                    },
                    content_type="multipart/form-data",
                )

            self.assertEqual(response.status_code, 500)
            payload = response.get_json()
            self.assertEqual(payload["conversation_id"], "doc-failure")
            self.assertEqual(payload["tag"], "private")
            self.assertTrue(payload["envelope_created"])
            self.assertTrue(payload["envelope_available"])
            self.assertIn("synthetic start failure", payload["error"])

    def test_bootstrap_filters_private_knowledge_outside_private_mode(self):
        calls: dict[str, list[dict]] = {"knowledge": [], "conversations": []}

        class QueryCollection:
            def __init__(self, name):
                self.name = name

            def query(self, **kwargs):
                calls[self.name].append(kwargs)
                return {"ids": [[]], "documents": [[]], "metadatas": [[]]}

        fake_chromadb = types.SimpleNamespace(
            PersistentClient=mock.Mock(return_value=object()),
        )

        def logical_collection(_client, logical_name):
            return QueryCollection(logical_name)

        with (
            mock.patch.dict(sys.modules, {"chromadb": fake_chromadb}),
            mock.patch("orchestrator.embedding.get_collection",
                       side_effect=logical_collection),
            mock.patch.object(self.server, "load_config",
                              return_value={"chromadb_path": "/configured/chroma"}),
        ):
            client = self.server.app.test_client()
            standard = client.post("/api/bootstrap", json={
                "topic": "sensitive topic", "tag": "",
            })
            private = client.post("/api/bootstrap", json={
                "topic": "sensitive topic", "tag": "private",
            })

        self.assertEqual(standard.status_code, 200)
        self.assertEqual(private.status_code, 200)
        self.assertEqual(calls["knowledge"][0]["where"], {"tag_private": False})
        self.assertIsNone(calls["knowledge"][1]["where"])
        self.assertEqual(
            calls["conversations"][0]["where"],
            {"tag": {"$ne": "private"}},
        )
        self.assertIsNone(calls["conversations"][1]["where"])


class TestVaultTranscriptOwnership(unittest.TestCase):
    def test_writer_emits_strict_lifecycle_markers_and_private_tag(self):
        from orchestrator.vault_transcript import write_transcript_note
        with tempfile.TemporaryDirectory() as td:
            path = write_transcript_note(
                source_media_path=Path(td) / "recording.wav",
                plain_text="Sensitive transcript text.",
                segments=[],
                language="en",
                duration_ms=1000,
                conversation_id="transcript-conv",
                private=True,
                vault_root=td,
            )

            text = path.read_text(encoding="utf-8")
            self.assertIn("artifact_kind: conversation_transcript\n", text)
            self.assertIn("managed_by: ora\n", text)
            self.assertIn('source_file: "transcript-conv"\n', text)
            self.assertIn('  - "private"\n', text)

    def test_writer_quotes_all_caller_controlled_yaml_scalars(self):
        import yaml
        from orchestrator.vault_transcript import write_transcript_note

        language = 'en"\ntags:\n  - standard'
        model = 'model\nmanaged_by: attacker'
        injected_tag = 'topic\nprivate: false'
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / 'recording"\ntags:\n  - standard.wav'
            path = write_transcript_note(
                source_media_path=source,
                plain_text="Sensitive transcript text.",
                segments=[],
                language=language,
                duration_ms=1000,
                transcription_model=model,
                extra_tags=[injected_tag],
                conversation_id="transcript-injection",
                private=True,
                vault_root=td,
            )

            frontmatter = path.read_text(encoding="utf-8").split("---", 2)[1]
            metadata = yaml.safe_load(frontmatter)
            self.assertEqual(
                Path(metadata["source_media"]).resolve(),
                source.resolve(),
            )
            self.assertEqual(metadata["language"], language)
            self.assertEqual(metadata["transcription_model"], model)
            self.assertEqual(metadata["managed_by"], "ora")
            self.assertEqual(metadata["source_file"], "transcript-injection")
            self.assertIn("private", metadata["tags"])
            self.assertIn(injected_tag, metadata["tags"])
            self.assertNotIn("standard", metadata["tags"])

    def test_writer_never_follows_dangling_symlink_filename_slot(self):
        from datetime import datetime, timezone
        from orchestrator.vault_transcript import write_transcript_note

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            vault = base / "vault"
            vault.mkdir()
            outside = base / "outside.md"
            date_part = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            occupied = vault / f"Transcript — recording — {date_part}.md"
            occupied.symlink_to(outside)

            path = write_transcript_note(
                source_media_path=base / "recording.wav",
                plain_text="Must remain inside the vault.",
                segments=[],
                language="en",
                duration_ms=1000,
                conversation_id="transcript-symlink",
                vault_root=vault,
            )

            self.assertEqual(
                path.name,
                f"Transcript — recording — {date_part} - 2.md",
            )
            self.assertTrue(occupied.is_symlink())
            self.assertFalse(outside.exists())
            self.assertTrue(path.is_file())


class TestLiveDocumentCleanup(unittest.TestCase):
    def test_live_job_purge_removes_owned_staging_and_created_output(self):
        from orchestrator import document_input
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            staging = base / "staging"
            incubator = base / "Incubator"
            sessions = base / "sessions"
            staging.mkdir()
            incubator.mkdir()
            sessions.mkdir()
            source = staging / "upload.pdf"
            output = incubator / "Converted.md"
            source.write_bytes(b"source")
            output.write_text("derived", encoding="utf-8")

            document_input.reset_for_tests()
            with (
                mock.patch.object(document_input, "STAGING_DIR", str(staging)),
                mock.patch.object(document_input, "VAULT_INCUBATOR_DIR", str(incubator)),
                mock.patch.object(document_input, "STEALTH_TEMP_ROOT", str(sessions)),
            ):
                with document_input._jobs_lock:
                    document_input._jobs["job-1"] = {
                        "processing_id": "job-1",
                        "conversation_id": "doc-conv",
                        "source_path": str(source),
                        "vault_path": str(output),
                        "output_created": True,
                    }
                result = document_input.purge_conversation("doc-conv")
                self.assertEqual(result["jobs"], 1)
                self.assertEqual(result["staged_files"], 1)
                self.assertEqual(result["created_outputs"], 1)
                self.assertFalse(source.exists())
                self.assertFalse(output.exists())
                with self.assertRaises(RuntimeError):
                    document_input.start(str(staging / "late.pdf"), {
                        "conversation_id": "doc-conv",
                    })
            document_input.reset_for_tests()

    def test_restart_purge_removes_durable_staging_subtree_only(self):
        from orchestrator import document_input
        with tempfile.TemporaryDirectory() as td:
            staging = Path(td) / "staging"
            owned = staging / "doc-conv"
            sibling = staging / "other-conv"
            (owned / "nested").mkdir(parents=True)
            sibling.mkdir(parents=True)
            (owned / "upload.pdf").write_bytes(b"source")
            (owned / "nested" / "sidecar.bin").write_bytes(b"sidecar")
            (sibling / "keep.pdf").write_bytes(b"keep")

            document_input.reset_for_tests()
            with mock.patch.object(document_input, "STAGING_DIR", str(staging)):
                # No live job is present: this models a server restart.
                result = document_input.purge_conversation("DOC-CONV")

            self.assertEqual(result["jobs"], 0)
            self.assertEqual(result["staged_files"], 2)
            self.assertFalse(owned.exists())
            self.assertTrue((sibling / "keep.pdf").exists())
            self.assertEqual(result["errors"], [])
            document_input.reset_for_tests()

    def test_live_conversion_uses_privacy_tag_updated_while_running(self):
        from orchestrator import document_input
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            staging = base / "staging"
            incubator = base / "Incubator"
            sessions = base / "sessions"
            for path in (staging, incubator, sessions):
                path.mkdir()
            source = staging / "Report.pdf"
            source.write_bytes(b"source")
            conversion_started = threading.Event()
            release_conversion = threading.Event()
            output_written = threading.Event()
            original_write = document_input._write_destination

            def blocking_convert(_source):
                conversion_started.set()
                release_conversion.wait(timeout=3)
                return "converted body"

            def observed_write(*args, **kwargs):
                result = original_write(*args, **kwargs)
                output_written.set()
                return result

            document_input.reset_for_tests()
            try:
                with (
                    mock.patch.object(document_input, "STAGING_DIR", str(staging)),
                    mock.patch.object(document_input, "VAULT_INCUBATOR_DIR",
                                      str(incubator)),
                    mock.patch.object(document_input, "STEALTH_TEMP_ROOT",
                                      str(sessions)),
                    mock.patch.object(document_input, "convert_to_markdown",
                                      side_effect=blocking_convert),
                    mock.patch.object(document_input, "_write_destination",
                                      side_effect=observed_write),
                ):
                    processing_id = document_input.start(str(source), {
                        "conversation_id": "document-privacy",
                        "tag": "",
                        "original_name": "Report.pdf",
                    })
                    self.assertTrue(conversion_started.wait(timeout=2))
                    update = document_input.update_conversation_tag(
                        "document-privacy", "private",
                    )
                    self.assertEqual(update["jobs"], 1)
                    release_conversion.set()
                    self.assertTrue(output_written.wait(timeout=3))
                    state = document_input.get_state(processing_id)
                    output = Path(state["vault_path"])
                    self.assertIn("  - private\n", output.read_text())
                    self.assertIn("source_file: \"document-privacy\"",
                                  output.read_text())
            finally:
                release_conversion.set()
                document_input.reset_for_tests()


class TestMediaLibraryDeletionRace(unittest.TestCase):
    def test_stale_library_instance_cannot_commit_after_forget(self):
        from orchestrator import media_library
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            root.mkdir()
            source = Path(td) / "image.png"
            source.write_bytes(b"image")
            probe_started = threading.Event()
            release_probe = threading.Event()
            observed: dict[str, object] = {}

            def blocking_probe(_path):
                probe_started.set()
                release_probe.wait(timeout=3)
                return {}

            with media_library._libraries_lock:
                media_library._libraries.clear()
                media_library._deleted_libraries.clear()
            try:
                with (
                    mock.patch.object(media_library, "SESSIONS_ROOT", root),
                    mock.patch.object(media_library, "_probe_metadata",
                                      side_effect=blocking_probe),
                ):
                    library = media_library.get_library("media-race")

                    def add_late():
                        try:
                            library.add_entry(source)
                        except Exception as exc:  # expected tombstone
                            observed["error"] = exc

                    worker = threading.Thread(target=add_late)
                    worker.start()
                    self.assertTrue(probe_started.wait(timeout=2))
                    self.assertTrue(media_library.forget_library("media-race"))
                    release_probe.set()
                    worker.join(timeout=3)
                    self.assertFalse(worker.is_alive())
                    self.assertIsInstance(observed.get("error"), RuntimeError)
                    self.assertFalse(library.state_path.exists())
            finally:
                release_probe.set()
                with media_library._libraries_lock:
                    media_library._libraries.clear()
                    media_library._deleted_libraries.clear()


if __name__ == "__main__":
    unittest.main()
