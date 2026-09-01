"""Focused contract tests for the renderer-neutral Library adapter."""

from __future__ import annotations

import unittest
from unittest import mock

from orchestrator.library_browser import (
    LibraryBrowserError,
    build_browser_response,
    parse_sources,
    stable_item_id,
)


def _row(identity: str, title: str, *, tag: str, modified_at: str) -> dict:
    return {
        "identity": identity,
        "title": title,
        "metadata": {
            "project_ids": ["ora"],
            "tags": [tag],
            "lifecycle": "active",
            "privacy": "standard",
            "modified_at": modified_at,
            "content_type": "text/markdown",
            "item_type": "note",
        },
        "provenance": {
            "available": True,
            "kind": "fixture",
            "identity": identity,
        },
        "relationships": {
            "state": "fresh",
            "updated_at": modified_at,
            "summaries": [{
                "type": "supports",
                "direction": "outgoing",
                "confidence": "high",
                "count": 2,
            }],
        },
        "preview": {
            "kind": "text",
            "available": True,
            "locator": {"identity": identity},
        },
        "editability": {
            "available": True,
            "editable": False,
            "surface": "fixture",
        },
    }


def _server_module():
    from orchestrator.embedding import install_test_stub

    install_test_stub()
    from server import app as server
    return server


class TestLibraryBrowser(unittest.TestCase):
    def test_sources_accept_repeated_and_comma_delimited_values(self):
        self.assertEqual(
            parse_sources(["files,dialogues", "engrams", "files"]),
            ("files", "dialogues", "engrams"),
        )
        self.assertEqual(parse_sources(None), ("dialogues", "engrams", "files"))
        with self.assertRaises(LibraryBrowserError):
            parse_sources(["dialogues,semantic-search"])

    def test_complete_universe_is_faceted_before_pagination(self):
        providers = {
            "dialogues": {
                "complete": True,
                "rows": [
                    _row("d-older", "Older", tag="alpha",
                         modified_at="2026-08-01T00:00:00Z"),
                    _row("d-newer", "Newer", tag="beta",
                         modified_at="2026-08-04T00:00:00Z"),
                ],
            },
            "engrams": {
                "complete": True,
                "rows": [_row("/vault/e.md", "Engram", tag="gamma",
                              modified_at="2026-08-03T00:00:00Z")],
            },
            "files": {
                "complete": True,
                "rows": [_row("/vault/f.md", "File", tag="delta",
                              modified_at="2026-08-02T00:00:00Z")],
            },
        }

        payload = build_browser_response(providers, offset=1, limit=2)

        self.assertEqual(payload["total"], 4)
        self.assertEqual(
            payload["source_counts"],
            {"dialogues": 2, "engrams": 1, "files": 1},
        )
        self.assertTrue(payload["universe"]["complete"])
        self.assertEqual(payload["pagination"], {
            "offset": 1, "limit": 2, "returned": 2,
            "has_more": True, "next_offset": 3,
        })
        self.assertEqual(
            payload["facets"]["tags"]["counts"],
            {"alpha": 1, "beta": 1, "delta": 1, "gamma": 1},
        )
        self.assertEqual(payload["facets"]["projects"]["counts"], {"ora": 4})
        self.assertTrue(payload["facets"]["tags"]["complete"])
        self.assertEqual(
            [row["title"] for row in payload["rows"]],
            ["Engram", "File"],
        )
        for row in payload["rows"]:
            self.assertTrue(row["id"].startswith(f"{row['source']}:"))
            self.assertEqual(row["preview"]["route"], "text-pane")
            self.assertTrue(row["editability"]["descriptor_only"])
            self.assertEqual(row["relationships"]["state"], "fresh")

    def test_incomplete_provider_never_presents_partial_universe_as_complete(self):
        providers = {
            "dialogues": {
                "complete": True,
                "rows": [_row("d1", "Dialogue", tag="visible",
                              modified_at="2026-08-01T00:00:00Z")],
            },
            "files": {
                "complete": False,
                "reason": "file authority unavailable",
                "rows": [],
            },
        }

        payload = build_browser_response(
            providers, requested_sources=["dialogues,files"], limit=20,
        )

        self.assertEqual(payload["total"], 1)
        self.assertFalse(payload["universe"]["complete"])
        self.assertEqual(payload["universe"]["unavailable_sources"], [{
            "source": "files", "reason": "file authority unavailable",
        }])
        self.assertFalse(payload["facets"]["tags"]["complete"])
        self.assertEqual(payload["source_counts"], {"dialogues": 1, "files": 0})

    def test_ids_are_deterministic_source_namespaced_and_metadata_is_truthful(self):
        identity = "/vault/shared.md"
        self.assertEqual(
            stable_item_id("engrams", identity),
            stable_item_id("engrams", identity),
        )
        self.assertNotEqual(
            stable_item_id("engrams", identity),
            stable_item_id("files", identity),
        )
        payload = build_browser_response({
            "files": {
                "complete": True,
                "rows": [{
                    "identity": identity,
                    "title": "Unknown metadata",
                    "metadata": {"item_type": "file"},
                    "preview": {"kind": "unsupported", "available": False},
                    "relationships": {"state": "unavailable", "summaries": []},
                    "editability": {"available": False},
                }],
            },
        }, requested_sources=["files"])
        row = payload["rows"][0]
        self.assertIn("privacy", row["unavailable_fields"])
        self.assertIn("modified_at", row["unavailable_fields"])
        self.assertFalse(row["provenance"]["available"])
        self.assertEqual(row["preview"]["route"], "metadata-only")
        self.assertIsNone(row["editability"]["editable"])

    def test_dialogue_provider_is_read_only_and_maps_stored_directions(self):
        server = _server_module()
        import conversation_memory as runtime_conversation_memory

        relationship_kinds = [
            "direct-child", "sibling", "parent", "contributor",
            "direct-related", "shared-project",
        ]
        snapshot = [{"conversation_id": "dialogue-1"}]
        with (
            mock.patch.object(
                runtime_conversation_memory,
                "iter_conversations",
                return_value=snapshot,
            ) as iter_dialogues,
            mock.patch.object(server, "_browser_live_rows", return_value=[{
                "conversation_id": "dialogue-1",
                "source_kind": "live",
                "title": "Dialogue one",
                "display_name": "Dialogue one",
                "last_activity_at": "2026-09-01T12:00:00Z",
                "project_ids": ["ora"],
                "tags": [],
                "_relationship_available": True,
                "_relationship_kinds": relationship_kinds,
            }]) as live_rows,
        ):
            provider = server._library_dialogue_provider()

        iter_dialogues.assert_called_once_with(
            include_closed=True,
            include_content=True,
            persist_heal=False,
            skipped_authority=mock.ANY,
        )
        live_rows.assert_called_once_with(
            "", target_tag="", persist_heal=False,
            skipped_authority=mock.ANY,
            preloaded_summaries=snapshot,
        )
        self.assertEqual(
            live_rows.call_args.kwargs["skipped_authority"], [],
        )
        self.assertTrue(provider["complete"])
        row = provider["rows"][0]
        self.assertIsNone(row["relationships"]["updated_at"])
        self.assertEqual(row["editability"], {
            "available": True,
            "editable": False,
            "surface": "dialogue",
            "reason": "Dialogues are read-only in the active Library programme",
        })
        summaries = {
            summary["type"]: summary for summary in row["relationships"]["summaries"]
        }
        self.assertEqual(
            {kind: summary["direction"] for kind, summary in summaries.items()},
            {
                "direct-child": "outgoing",
                "sibling": "peer",
                "parent": "incoming",
                "contributor": "outgoing",
                "direct-related": "incoming",
                "shared-project": "peer",
            },
        )
        self.assertTrue(all("count" not in summary for summary in summaries.values()))

    def test_dialogue_provider_nonempty_query_without_terms_has_no_matches(self):
        server = _server_module()
        import conversation_memory as runtime_conversation_memory

        snapshot = [{"conversation_id": "dialogue-1"}]
        readable = [{
            "conversation_id": "dialogue-1",
            "source_kind": "live",
            "title": "Dialogue one",
            "display_name": "Dialogue one",
            "project_ids": [],
            "tags": [],
        }]
        with (
            mock.patch.object(
                runtime_conversation_memory,
                "iter_conversations",
                return_value=snapshot,
            ),
            mock.patch.object(
                server, "_browser_live_rows", return_value=readable,
            ) as live_rows,
        ):
            provider = server._library_dialogue_provider("AI the")

        self.assertEqual(provider["rows"], [])
        live_rows.assert_called_once_with(
            "", target_tag="", persist_heal=False,
            skipped_authority=mock.ANY,
            preloaded_summaries=snapshot,
        )

    def test_engram_and_file_providers_take_one_complete_inventory_read(self):
        import hashlib
        import sqlite3
        import tempfile
        from pathlib import Path

        server = _server_module()
        import chromadb
        from orchestrator import conversation_memory, embedding, project_meta

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            chroma_dir = root / "chromadb"
            chroma_dir.mkdir()
            db_path = chroma_dir / "chroma.sqlite3"
            engram_path = root / "indexed-engram.md"
            vector_path = root / "vector-engram.md"
            other_database_path = root / "other-database-engram.md"
            vector_only_path = root / "vector-only-engram.md"
            for path in (
                engram_path, vector_path, other_database_path, vector_only_path,
            ):
                path.write_text(f"# {path.stem}\n", encoding="utf-8")
            physical_collection = "knowledge-physical"
            vector_only_collection = "knowledge-vector-only"

            real_connect = sqlite3.connect
            fixture = real_connect(db_path)
            try:
                fixture.executescript(
                    """
                    CREATE TABLE databases (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        tenant_id TEXT NOT NULL
                    );
                    CREATE TABLE collections (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        database_id TEXT NOT NULL
                    );
                    CREATE TABLE segments (
                        id TEXT PRIMARY KEY,
                        collection TEXT NOT NULL,
                        scope TEXT NOT NULL,
                        type TEXT NOT NULL
                    );
                    CREATE TABLE embeddings (
                        id INTEGER PRIMARY KEY,
                        segment_id TEXT NOT NULL,
                        embedding_id TEXT NOT NULL
                    );
                    CREATE TABLE embedding_metadata (
                        id INTEGER NOT NULL,
                        key TEXT NOT NULL,
                        string_value TEXT,
                        int_value INTEGER,
                        float_value REAL,
                        bool_value INTEGER
                    );
                    """
                )
                fixture.executemany(
                    "INSERT INTO databases(id, name, tenant_id) VALUES (?, ?, ?)",
                    [
                        ("default-db", "default_database", "default_tenant"),
                        ("other-db", "other_database", "default_tenant"),
                    ],
                )
                fixture.executemany(
                    "INSERT INTO collections(id, name, database_id) VALUES (?, ?, ?)",
                    [
                        ("collection-1", physical_collection, "default-db"),
                        ("collection-other", physical_collection, "other-db"),
                        ("collection-vector-only", vector_only_collection, "default-db"),
                    ],
                )
                fixture.executemany(
                    "INSERT INTO segments(id, collection, scope, type) "
                    "VALUES (?, ?, ?, ?)",
                    [
                        ("segment-metadata", "collection-1", "METADATA",
                         "urn:chroma:segment/metadata/sqlite"),
                        ("segment-vector", "collection-1", "VECTOR",
                         "urn:chroma:segment/vector/hnsw-local-persisted"),
                        ("segment-other-metadata", "collection-other", "METADATA",
                         "urn:chroma:segment/metadata/sqlite"),
                        ("segment-vector-only", "collection-vector-only", "VECTOR",
                         "urn:chroma:segment/vector/hnsw-local-persisted"),
                    ],
                )
                fixture.executemany(
                    "INSERT INTO embeddings(id, segment_id, embedding_id) "
                    "VALUES (?, ?, ?)",
                    [
                        (1, "segment-metadata", "chunk-1"),
                        (2, "segment-vector", "chunk-vector"),
                        (3, "segment-other-metadata", "chunk-other-database"),
                        (4, "segment-vector-only", "chunk-vector-only"),
                    ],
                )
                for row_id, path, title in (
                    (1, engram_path, "Indexed Engram"),
                    (2, vector_path, "Vector Fake"),
                    (3, other_database_path, "Other Database Fake"),
                    (4, vector_only_path, "Vector Only Fake"),
                ):
                    fixture.executemany(
                        "INSERT INTO embedding_metadata"
                        "(id, key, string_value) VALUES (?, ?, ?)",
                        [
                            (row_id, "nexus", "ora"),
                            (row_id, "path", str(path)),
                            (row_id, "tags", '["alpha"]'),
                            (row_id, "title", title),
                            (row_id, "type", "engram"),
                        ],
                    )
                fixture.commit()
            finally:
                fixture.close()

            fixture_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()
            fixture_entries = sorted(path.name for path in chroma_dir.iterdir())
            connect_calls = []
            statements = []

            def read_only_connect(database, *args, **kwargs):
                connect_calls.append((database, args, kwargs))
                connection = real_connect(database, *args, **kwargs)
                connection.set_trace_callback(statements.append)
                return connection

            with (
                mock.patch.object(server.rp, "chromadb_dir", return_value=chroma_dir),
                mock.patch.object(
                    embedding, "resolve_collection",
                    side_effect=[physical_collection, vector_only_collection],
                ) as resolve_collection,
                mock.patch.object(
                    chromadb, "PersistentClient",
                    side_effect=AssertionError("Library GET must not open Chroma"),
                ) as persistent_client,
                mock.patch.object(
                    sqlite3, "connect", side_effect=read_only_connect,
                ),
                mock.patch.object(
                    conversation_memory, "knowledge_admitted_paths",
                    wraps=conversation_memory.knowledge_admitted_paths,
                ) as admitted_paths,
            ):
                engrams = server._library_engram_provider()
                vector_only = server._library_engram_provider()

            self.assertTrue(engrams["complete"])
            self.assertIsNone(engrams["reason"])
            self.assertEqual(len(engrams["rows"]), 1)
            engram = engrams["rows"][0]
            self.assertEqual(engram["identity"], str(engram_path.resolve()))
            self.assertEqual(engram["title"], "Indexed Engram")
            self.assertEqual(engram["metadata"]["tags"], ["alpha"])
            self.assertEqual(engram["metadata"]["project_ids"], ["ora"])
            self.assertEqual(engram["metadata"]["item_type"], "engram")
            self.assertTrue(engram["preview"]["available"])
            self.assertEqual(engram["provenance"]["details"], {
                "index": "knowledge",
            })
            self.assertFalse(vector_only["complete"])
            self.assertEqual(vector_only["rows"], [])
            self.assertIn("metadata segment", vector_only["reason"])
            self.assertEqual(
                resolve_collection.call_args_list,
                [mock.call("knowledge"), mock.call("knowledge")],
            )
            persistent_client.assert_not_called()
            admitted_paths.assert_called_once()
            admitted_metadata, admitted_target = admitted_paths.call_args.args
            self.assertEqual(admitted_target, "")
            self.assertEqual(admitted_metadata, [{
                "nexus": "ora",
                "path": str(engram_path),
                "tags": '["alpha"]',
                "title": "Indexed Engram",
                "type": "engram",
            }])

            expected_connect = (
                f"file:{db_path}?mode=ro", (), {"uri": True},
            )
            self.assertEqual(connect_calls, [expected_connect, expected_connect])
            self.assertTrue(all(
                "immutable" not in database for database, _args, _kwargs in connect_calls
            ))
            normalized_statements = [" ".join(sql.split()) for sql in statements]
            self.assertEqual(normalized_statements[0], "PRAGMA query_only=ON")
            self.assertEqual(normalized_statements[1], "BEGIN")
            self.assertEqual(normalized_statements[-1], "COMMIT")
            inventory_queries = [
                sql for sql in normalized_statements if sql.startswith("SELECT ")
            ]
            self.assertEqual(len(inventory_queries), 2)
            for table in (
                "databases", "collections", "segments", "embeddings",
                "embedding_metadata",
            ):
                self.assertTrue(all(table in query for query in inventory_queries))
            self.assertEqual(
                hashlib.sha256(db_path.read_bytes()).hexdigest(), fixture_hash,
            )
            self.assertEqual(
                sorted(path.name for path in chroma_dir.iterdir()), fixture_entries,
            )

            encoded_engram = server._browser_encode_source_id(
                "engram", str(engram_path),
            )

            def surviving_exact(*_args, **_kwargs):
                return [{"conversation_id": encoded_engram}]

            def unavailable_fuzzy(*_args, **kwargs):
                kwargs["error_sink"].append("fuzzy knowledge search failed")
                return []

            with (
                mock.patch.object(server.rp, "chromadb_dir", return_value=chroma_dir),
                mock.patch.object(
                    embedding, "resolve_collection", return_value=physical_collection,
                ),
                mock.patch.object(sqlite3, "connect", side_effect=read_only_connect),
                mock.patch.object(
                    conversation_memory, "knowledge_admitted_paths",
                    wraps=conversation_memory.knowledge_admitted_paths,
                ),
                mock.patch.object(
                    server, "_browser_chroma_exact_rows",
                    side_effect=surviving_exact,
                ),
                mock.patch.object(
                    server, "_browser_chroma_fuzzy_rows",
                    side_effect=unavailable_fuzzy,
                ),
            ):
                searched = server._library_engram_provider("forecast")

            self.assertFalse(searched["complete"])
            self.assertIn("keyword search paths", searched["reason"])
            self.assertEqual(
                [row["identity"] for row in searched["rows"]],
                [str(engram_path.resolve())],
            )

            for helper, label in (
                (server._browser_chroma_exact_rows, "exact"),
                (server._browser_chroma_fuzzy_rows, "fuzzy"),
            ):
                errors = []
                with mock.patch.object(
                    server,
                    "_browser_knowledge_admitted_path_inventory",
                    return_value=None,
                ):
                    helper_rows = helper(
                        "forecast", logical_collection="knowledge", limit=None,
                        error_sink=errors,
                    )
                self.assertEqual(helper_rows, [])
                self.assertIn(
                    f"{label} knowledge authority inventory unavailable",
                    errors,
                )

            file_paths = []
            for index in range(2):
                path = root / f"f{index}.md"
                path.write_text(f"# File {index}\n", encoding="utf-8")
                file_paths.append(path)
            inventory = {
                "exists": True,
                "complete": True,
                "reason": None,
                "files": [
                    {
                        "name": path.name,
                        "rel_path": path.name,
                        "abs_path": str(path),
                        "size": path.stat().st_size,
                        "mtime": "2026-09-01T12:00:00",
                    }
                    for path in file_paths
                ],
                "total": 2,
                "offset": 0,
                "limit": None,
                "next_offset": None,
            }
            with (
                mock.patch.object(
                    project_meta, "list_project_meta", return_value=[{
                        "nexus": "ora", "folder_name": "Ora", "is_default": False,
                    }],
                ) as list_projects,
                mock.patch.object(
                    project_meta, "list_project_files", return_value=inventory,
                ) as list_files,
            ):
                files = server._library_file_provider()

            self.assertTrue(files["complete"])
            self.assertEqual(
                {row["identity"] for row in files["rows"]},
                {str(path) for path in file_paths},
            )
            self.assertTrue(all(
                row["metadata"]["project_ids"] == ["ora"]
                and row["preview"]["available"]
                and row["provenance"]["kind"] == "project-file-inventory"
                for row in files["rows"]
            ))
            list_files.assert_called_once_with("Ora", max_files=None)
            list_projects.assert_called_once_with(skipped_authority=mock.ANY)
            self.assertEqual(
                list_projects.call_args.kwargs["skipped_authority"], [],
            )

    def test_skipped_authority_records_keep_safe_rows_but_make_counts_incomplete(self):
        import copy
        import json
        import tempfile
        from pathlib import Path

        server = _server_module()
        from orchestrator import conversation_memory, project_meta
        import conversation_memory as runtime_conversation_memory

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sessions = root / "sessions"
            good = sessions / "good"
            good.mkdir(parents=True)
            envelope_path = good / "conversation.json"
            envelope_path.write_text(json.dumps({
                "conversation_id": "good",
                "display_name": "Readable Dialogue",
                "tag": "",
                "closed": True,
                "messages": [
                    {"role": "user", "content": "Question"},
                    {"role": "assistant", "content": "Answer"},
                ],
                "project_ids": ["ora"],
            }), encoding="utf-8")
            envelope_bytes = envelope_path.read_bytes()
            envelope_mtime_ns = envelope_path.stat().st_mtime_ns
            (sessions / "missing").mkdir()
            malformed = sessions / "malformed"
            malformed.mkdir()
            (malformed / "conversation.json").write_text(
                "{", encoding="utf-8",
            )
            (sessions / "archived").mkdir()

            skipped_dialogues: list[str] = []
            dialogue_rows = conversation_memory.iter_conversations(
                sessions_root=sessions,
                include_closed=True,
                persist_heal=False,
                skipped_authority=skipped_dialogues,
            )
            default_dialogue_rows = conversation_memory.iter_conversations(
                sessions_root=sessions,
                include_closed=True,
                persist_heal=False,
            )
            self.assertEqual(
                [row["conversation_id"] for row in dialogue_rows], ["good"],
            )
            self.assertEqual(
                [row["conversation_id"] for row in default_dialogue_rows],
                ["good"],
            )
            self.assertEqual(set(skipped_dialogues), {"missing", "malformed"})

            pointers = root / "projects"
            pointers.mkdir()
            (pointers / "ora.json").write_text(json.dumps({
                "nexus": "ora", "name": "Ora", "status": "active",
            }), encoding="utf-8")
            (pointers / "broken.json").write_text("{", encoding="utf-8")
            skipped_projects: list[str] = []
            project_rows = project_meta.list_project_meta(
                pointer_dir=pointers,
                skipped_authority=skipped_projects,
            )
            default_project_rows = project_meta.list_project_meta(
                pointer_dir=pointers,
            )
            self.assertEqual(
                [row["nexus"] for row in project_rows], ["commons", "ora"],
            )
            self.assertEqual(
                [row["nexus"] for row in default_project_rows],
                ["commons", "ora"],
            )
            self.assertEqual(skipped_projects, ["broken.json"])

            file_path = root / "readable.md"
            file_path.write_text("# Readable\n", encoding="utf-8")
            inventory = {
                "exists": True,
                "complete": True,
                "reason": None,
                "files": [{
                    "name": file_path.name,
                    "rel_path": file_path.name,
                    "abs_path": str(file_path),
                    "size": file_path.stat().st_size,
                    "mtime": "2026-09-01T12:00:00",
                }],
                "total": 1,
                "offset": 0,
                "limit": None,
                "next_offset": None,
            }

            def partial_projects(*, skipped_authority):
                skipped_authority.append("broken.json")
                return [{
                    "nexus": "ora", "folder_name": "Ora", "is_default": False,
                }]

            iter_for_provider = runtime_conversation_memory.iter_conversations
            provider_snapshots: list[list[dict]] = []
            provider_snapshots_before: list[list[dict]] = []

            def one_dialogue_snapshot(*args, **kwargs):
                snapshot = iter_for_provider(*args, **kwargs)
                provider_snapshots.append(snapshot)
                provider_snapshots_before.append(copy.deepcopy(snapshot))
                return snapshot

            with (
                mock.patch.object(
                    runtime_conversation_memory,
                    "_DEFAULT_SESSIONS_ROOT",
                    sessions,
                ),
                mock.patch.object(
                    runtime_conversation_memory,
                    "iter_conversations",
                    side_effect=one_dialogue_snapshot,
                ) as iter_dialogues,
                mock.patch.object(
                    server,
                    "_browser_live_rows",
                    wraps=server._browser_live_rows,
                ) as live_rows,
                mock.patch.object(
                    project_meta, "list_project_meta", side_effect=partial_projects,
                ),
                mock.patch.object(
                    project_meta, "list_project_files", return_value=inventory,
                ),
            ):
                dialogue_provider = server._library_dialogue_provider()
                file_provider = server._library_file_provider()

            iter_dialogues.assert_called_once_with(
                include_closed=True,
                include_content=True,
                persist_heal=False,
                skipped_authority=mock.ANY,
            )
            live_rows.assert_called_once()
            provider_snapshot = live_rows.call_args.kwargs[
                "preloaded_summaries"
            ]
            self.assertIs(provider_snapshot, provider_snapshots[0])
            self.assertEqual(provider_snapshot, provider_snapshots_before[0])
            self.assertEqual(len(provider_snapshot), 1)
            self.assertEqual(provider_snapshot[0]["conversation_id"], "good")
            self.assertIn("_envelope", provider_snapshot[0])
            self.assertIn("_effective_messages", provider_snapshot[0])
            self.assertIs(
                live_rows.call_args.kwargs["skipped_authority"],
                iter_dialogues.call_args.kwargs["skipped_authority"],
            )
            self.assertEqual(len(dialogue_provider["rows"]), 1)
            self.assertFalse(dialogue_provider["complete"])
            self.assertIn("missing or unreadable", dialogue_provider["reason"])
            self.assertIn(
                "no privacy-admitted exchange", dialogue_provider["reason"],
            )
            provider_row = dialogue_provider["rows"][0]
            self.assertNotIn("_envelope", provider_row)
            self.assertNotIn("_effective_messages", provider_row)
            self.assertEqual(provider_row["title"], "Dialogue metadata")
            self.assertNotIn("Readable Dialogue", str(provider_row))
            self.assertNotIn("Question", str(provider_row))
            self.assertNotIn("Answer", str(provider_row))
            self.assertNotIn("snippet", provider_row)
            self.assertEqual(provider_row["metadata"]["project_ids"], ["ora"])
            self.assertEqual(provider_row["metadata"]["lifecycle"], "inactive")
            self.assertEqual(provider_row["metadata"]["message_count"], 2)
            self.assertIsNone(provider_row["metadata"]["privacy"])
            self.assertIsNone(provider_row["metadata"]["tags"])
            self.assertIn("title", provider_row["unavailable_fields"])
            self.assertIn("privacy", provider_row["unavailable_fields"])
            self.assertIn("tags", provider_row["unavailable_fields"])
            self.assertFalse(provider_row["preview"]["available"])
            self.assertNotIn("locator", provider_row["preview"])
            self.assertTrue(provider_row["editability"]["available"])
            self.assertFalse(provider_row["editability"]["editable"])
            self.assertEqual(
                provider_row["relationships"]["state"],
                "incomplete",
            )
            self.assertIsNone(provider_row["relationships"]["updated_at"])
            self.assertEqual(provider_row["relationships"]["summaries"], [])
            self.assertIn(
                "per-turn privacy authority",
                provider_row["relationships"]["reason"],
            )
            self.assertEqual(envelope_path.read_bytes(), envelope_bytes)
            self.assertEqual(envelope_path.stat().st_mtime_ns, envelope_mtime_ns)
            self.assertEqual(len(file_provider["rows"]), 1)
            self.assertFalse(file_provider["complete"])
            self.assertIn("enumerated or read", file_provider["reason"])

            payload = build_browser_response(
                {"dialogues": dialogue_provider, "files": file_provider},
                requested_sources=["dialogues,files"],
                limit=20,
            )
            self.assertEqual(payload["total"], 2)
            self.assertEqual(
                payload["source_counts"], {"dialogues": 1, "files": 1},
            )
            self.assertFalse(payload["universe"]["complete"])
            self.assertFalse(payload["facets"]["projects"]["complete"])
            dialogue_row = next(
                row for row in payload["rows"] if row["source"] == "dialogues"
            )
            self.assertEqual(dialogue_row["title"], "Dialogue metadata")
            self.assertIn("title", dialogue_row["unavailable_fields"])
            self.assertIn("privacy", dialogue_row["unavailable_fields"])
            self.assertIn("tags", dialogue_row["unavailable_fields"])
            self.assertFalse(dialogue_row["preview"]["available"])
            self.assertNotIn("locator", dialogue_row["preview"])
            self.assertEqual(
                dialogue_row["relationships"]["state"], "incomplete",
            )
            self.assertIn(
                "per-turn privacy authority",
                dialogue_row["relationships"]["reason"],
            )
            self.assertEqual(
                {item["source"] for item in payload["universe"]["unavailable_sources"]},
                {"dialogues", "files"},
            )

    def test_http_endpoint_accepts_multiple_sources_and_pages_combined_rows(self):
        server = _server_module()

        fixtures = {
            source: {"complete": True, "rows": [
                _row(source, source.title(), tag=source,
                     modified_at=f"2026-08-0{index}T00:00:00Z")
            ]}
            for index, source in enumerate(
                ("dialogues", "engrams", "files"), start=1,
            )
        }
        fixtures["dialogues"]["rows"][0]["metadata"]["project_ids"] = ["project-a"]
        fixtures["engrams"]["rows"][0]["metadata"]["project_ids"] = ["project-b"]
        fixtures["files"]["rows"][0]["metadata"]["project_ids"] = ["project-a"]
        searched = {
            "dialogues": fixtures["dialogues"],
            "engrams": fixtures["engrams"],
        }
        with (
            mock.patch.object(
                server, "_library_dialogue_provider",
                side_effect=lambda query="": (
                    searched["dialogues"] if query else fixtures["dialogues"]
                ),
            ) as dialogue_provider,
            mock.patch.object(
                server, "_library_engram_provider",
                side_effect=lambda query="": (
                    searched["engrams"] if query else fixtures["engrams"]
                ),
            ) as engram_provider,
            mock.patch.object(
                server, "_library_file_provider",
                return_value=fixtures["files"],
            ) as file_provider,
            server.app.test_client() as client,
        ):
            response = client.get(
                "/api/library/browser?source=files,dialogues&source=engrams"
                "&offset=1&limit=1"
            )
            scoped_response = client.get(
                "/api/library/browser?source=files,dialogues&source=engrams"
                "&project_id=project-a&offset=0&limit=1"
            )
            query_response = client.get(
                "/api/library/browser?source=dialogues&source=engrams&source=files"
                "&q=budget+forecast&offset=0&limit=20"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["sources"], ["files", "dialogues", "engrams"])
        self.assertEqual(payload["project_id"], "commons")
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["source_counts"], {
            "files": 1, "dialogues": 1, "engrams": 1,
        })
        self.assertEqual(payload["pagination"]["returned"], 1)
        self.assertEqual(scoped_response.status_code, 200)
        scoped = scoped_response.get_json()
        self.assertEqual(scoped["project_id"], "project-a")
        self.assertEqual(scoped["total"], 2)
        self.assertEqual(scoped["source_counts"], {
            "files": 1, "dialogues": 1, "engrams": 0,
        })
        self.assertEqual(scoped["pagination"]["returned"], 1)
        self.assertEqual(query_response.status_code, 200)
        queried = query_response.get_json()
        self.assertEqual(queried["query"], "budget forecast")
        self.assertEqual(queried["project_id"], "commons")
        self.assertEqual(queried["total"], 2)
        self.assertEqual(queried["source_counts"], {
            "dialogues": 1, "engrams": 1, "files": 0,
        })
        self.assertFalse(queried["universe"]["complete"])
        self.assertEqual(
            queried["universe"]["unavailable_sources"],
            [{
                "source": "files",
                "reason": (
                    "Files do not support body keyword search; Dialogue "
                    "and Engram matches remain available"
                ),
            }],
        )
        dialogue_provider.assert_any_call("budget forecast")
        engram_provider.assert_any_call("budget forecast")
        self.assertEqual(file_provider.call_count, 2)

    def test_creation_browser_preserves_repeated_included_context(self):
        server = _server_module()
        engram_ref = server._browser_encode_source_id(
            "engram", "/vault/Engrams/claim.md",
        )
        included_rows = {
            "dialogue-a": {
                "conversation_id": "dialogue-a",
                "source_kind": "live",
                "title": "Dialogue A",
                "tags": [],
                "project_ids": [],
            },
            engram_ref: {
                "conversation_id": engram_ref,
                "source_kind": "engram",
                "title": "Atomic claim",
                "tags": ["atomic"],
                "project_ids": [],
            },
        }
        with (
            mock.patch.object(server, "_browser_live_rows", return_value=[]),
            mock.patch.object(server, "_browser_chroma_exact_rows", return_value=[]),
            mock.patch.object(server, "_browser_chroma_fuzzy_rows", return_value=[]),
            mock.patch.object(server, "_browser_chroma_semantic_rows", return_value=[]),
            mock.patch.object(server, "_browser_vault_markdown_rows", return_value=[]),
            mock.patch.object(
                server, "_browser_creation_row_allowed",
                side_effect=lambda row, _target_tag: (
                    row.get("conversation_id") in included_rows
                ),
            ),
            mock.patch.object(
                server, "_browser_row_for_creation_ref",
                side_effect=lambda ref, **_kwargs: included_rows.get(ref),
            ),
            mock.patch.object(
                server, "_register_conversation_discovery",
                return_value="review-token",
            ),
            server.app.test_client() as client,
        ):
            response = client.get(
                "/api/conversations/browser",
                query_string=[
                    ("q", "Build a grounded planning dialogue"),
                    ("purpose", "creation"),
                    ("conversations", "1"),
                    ("engrams", "1"),
                    ("limit", "1"),
                    ("include_ref", "dialogue-a"),
                    ("include_ref", engram_ref),
                ],
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["review_token"], "review-token")
        self.assertEqual(
            [row["conversation_id"] for row in payload["rows"]],
            ["dialogue-a", engram_ref],
        )
        self.assertEqual(payload["total"], 2)


if __name__ == "__main__":
    unittest.main()
