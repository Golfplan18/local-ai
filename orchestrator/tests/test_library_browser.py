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

    def test_complete_universe_is_faceted_before_page_relationship_resolution(self):
        providers = {
            "dialogues": {
                "complete": True,
                "rows": [
                    _row("d-older", "Dialogue", tag="alpha",
                         modified_at="2026-08-01T00:00:00Z"),
                ],
            },
            "engrams": {
                "complete": True,
                "rows": [
                    dict(
                        _row("/vault/selected.md", "Selected", tag="beta",
                             modified_at="2026-08-04T00:00:00Z"),
                        _relationship_identity="Selected",
                    ),
                    dict(
                        _row("/vault/off-page.md", "Off page", tag="gamma",
                             modified_at="2026-08-03T00:00:00Z"),
                        _relationship_identity="OffPage",
                    ),
                    dict(
                        _row("/vault/other-project.md", "Other project",
                             tag="delta",
                             modified_at="2026-08-05T00:00:00Z"),
                        _relationship_identity="OtherProject",
                    ),
                ],
            },
        }
        for row in providers["dialogues"]["rows"]:
            row["metadata"]["project_ids"] = ["project-a"]
        for row in providers["engrams"]["rows"][:2]:
            row["metadata"]["project_ids"] = ["project-a"]
        providers["engrams"]["rows"][2]["metadata"]["project_ids"] = [
            "project-b"
        ]
        requested = []

        def resolve(identities):
            requested.append(set(identities))
            return {
                "state": "stale",
                "updated_at": "2026-08-06T00:00:00Z",
                "reason": "canonical notes changed",
                "items": {
                    "Selected": {
                        "summaries": [{
                            "type": "supports",
                            "direction": "outgoing",
                            "confidence": "high",
                            "count": 2,
                        }],
                    },
                },
            }

        payload = build_browser_response(
            providers,
            requested_sources=["dialogues", "engrams"],
            project_id="project-a",
            limit=1,
            relationship_resolver=resolve,
        )

        self.assertEqual(requested, [{"Selected"}])
        self.assertNotIn("OffPage", requested[0])
        self.assertEqual(payload["total"], 3)
        self.assertEqual(
            payload["source_counts"],
            {"dialogues": 1, "engrams": 2},
        )
        self.assertTrue(payload["universe"]["complete"])
        self.assertEqual(payload["pagination"], {
            "offset": 0, "limit": 1, "returned": 1,
            "has_more": True, "next_offset": 1,
        })
        self.assertEqual(
            payload["facets"]["tags"]["counts"],
            {"alpha": 1, "beta": 1, "gamma": 1},
        )
        self.assertEqual(
            payload["facets"]["relationships"]["counts"],
            {"fresh": 1, "incomplete": 0, "stale": 2, "unavailable": 0},
        )
        self.assertEqual(
            payload["facets"]["projects"]["counts"], {"project-a": 3},
        )
        self.assertTrue(payload["facets"]["tags"]["complete"])
        row = payload["rows"][0]
        self.assertEqual(row["title"], "Selected")
        self.assertEqual(row["relationships"], {
            "state": "stale",
            "updated_at": "2026-08-06T00:00:00Z",
            "reason": "canonical notes changed",
            "summaries": [{
                "type": "supports", "direction": "outgoing",
                "confidence": "high", "count": 2,
            }],
        })
        self.assertNotIn("_relationship_identity", str(payload))

        def fail_resolution(_identities):
            raise RuntimeError("relationship database unavailable")

        failed = build_browser_response(
            providers,
            requested_sources=["dialogues", "engrams"],
            project_id="project-a",
            limit=1,
            relationship_resolver=fail_resolution,
        )
        self.assertEqual(failed["total"], 3)
        self.assertEqual(len(failed["rows"]), 1)
        self.assertTrue(failed["universe"]["complete"])
        self.assertTrue(failed["facets"]["relationships"]["complete"])
        self.assertEqual(
            failed["facets"]["relationships"]["counts"],
            {"fresh": 1, "incomplete": 0, "stale": 0, "unavailable": 2},
        )
        self.assertEqual(
            failed["rows"][0]["relationships"]["state"], "unavailable",
        )
        self.assertNotIn("_relationship_identity", str(failed))

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
        import inspect
        import json
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
            non_engram_path = root / "indexed-chat.md"
            blocked_path = root / "blocked-engram.md"
            private_path = root / "private-engram.md"
            blank_key_path = root / "blank-key-engram.md"
            duplicate_key_path = root / "duplicate-key-engram.md"
            for path in (
                engram_path, vector_path, other_database_path, vector_only_path,
                non_engram_path, blocked_path, private_path, blank_key_path,
                duplicate_key_path,
            ):
                path.write_text(f"# {path.stem}\n", encoding="utf-8")
            physical_collection = "knowledge-physical"
            vector_only_collection = "knowledge-vector-only"
            blocked_sibling_id = 50_000
            filler_row_ids = tuple(range(100, 4_190))

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
                        embedding_id TEXT NOT NULL,
                        UNIQUE (segment_id, embedding_id)
                    );
                    CREATE TABLE embedding_metadata (
                        id INTEGER NOT NULL,
                        key TEXT NOT NULL,
                        string_value TEXT,
                        int_value INTEGER,
                        float_value REAL,
                        bool_value INTEGER,
                        PRIMARY KEY (id, key)
                    );
                    CREATE TABLE embedding_metadata_array (
                        id INTEGER NOT NULL,
                        key TEXT NOT NULL,
                        string_value TEXT,
                        int_value INTEGER,
                        float_value REAL,
                        bool_value INTEGER
                    );
                    CREATE INDEX embedding_metadata_array_by_id_key
                        ON embedding_metadata_array(id, key);
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
                        (5, "segment-metadata", "chunk-non-engram"),
                        (6, "segment-metadata", "chunk-2"),
                        (7, "segment-metadata", "chunk-blocked-engram"),
                        (9, "segment-metadata", "chunk-private-engram"),
                        (10, "segment-metadata", "chunk"),
                        (11, "segment-metadata", " chunk "),
                        (12, "segment-metadata", "chunk-blank-key"),
                        (13, "segment-metadata", "chunk-duplicate-key"),
                        (blocked_sibling_id, "segment-metadata",
                         "chunk-blocked-sibling"),
                    ] + [
                        (row_id, "segment-metadata", f"filler-{row_id}")
                        for row_id in filler_row_ids
                    ],
                )
                for row_id, path, title, item_type in (
                    (1, engram_path, "Indexed Engram", "engram"),
                    (2, vector_path, "Vector Fake", "engram"),
                    (3, other_database_path, "Other Database Fake", "engram"),
                    (4, vector_only_path, "Vector Only Fake", "engram"),
                    (5, non_engram_path, "Indexed Chat", "chat"),
                    (6, engram_path, "Indexed Engram", "engram"),
                    (7, blocked_path, "Blocked Engram", "engram"),
                    (blocked_sibling_id, blocked_path, "Blocked sibling", "chat"),
                    (9, private_path, "Private Engram", "engram"),
                    (10, engram_path, "Whitespace duplicate A", "chat"),
                    (11, engram_path, "Whitespace duplicate B", "chat"),
                    (12, blank_key_path, "Blank key Engram", "engram"),
                    (13, duplicate_key_path, "Duplicate key Engram", "engram"),
                ):
                    fixture.executemany(
                        "INSERT INTO embedding_metadata"
                        "(id, key, string_value) VALUES (?, ?, ?)",
                        [
                            (row_id, "nexus", "ora"),
                            (row_id, "path", str(path)),
                            (row_id, "title", title),
                            (row_id, "type", item_type),
                        ],
                    )
                fixture.executemany(
                    "INSERT INTO embedding_metadata"
                    "(id, key, string_value) VALUES (?, ?, ?)",
                    (
                        (row_id, key, value)
                        for row_id in filler_row_ids
                        for key, value in (
                            ("path", str(engram_path)),
                            ("type", "chat"),
                        )
                    ),
                )
                document_sentinel = "not-materialized-" + ("x" * 100_000)
                fixture.execute(
                    "INSERT INTO embedding_metadata"
                    "(id, key, string_value) VALUES (?, ?, ?)",
                    (1, "chroma:document", document_sentinel),
                )
                masked_numeric_key = "internal_sequence"
                fixture.execute(
                    "INSERT INTO embedding_metadata"
                    "(id, key, int_value) VALUES (?, ?, ?)",
                    (1, masked_numeric_key, 17),
                )
                fixture.execute(
                    "INSERT INTO embedding_metadata"
                    "(id, key, string_value) VALUES (?, ?, ?)",
                    (12, " \t ", "unsafe blank key"),
                )
                fixture.execute(
                    "INSERT INTO embedding_metadata"
                    "(id, key, string_value) VALUES (?, ?, ?)",
                    (13, " title ", "unsafe duplicate title"),
                )
                fixture.execute(
                    "INSERT INTO embedding_metadata"
                    "(id, key, string_value) VALUES (?, ?, ?)",
                    (blocked_sibling_id, "\u2003artifact_kind\u2029",
                     "conversation_runtime_derivative"),
                )
                fixture.executemany(
                    "INSERT INTO embedding_metadata"
                    "(id, key, string_value, int_value) VALUES (?, ?, ?, ?)",
                    [
                        (blocked_sibling_id, " managed_by ", "ora", None),
                        (blocked_sibling_id, " source_file ",
                         "blocked-source.json", None),
                        (blocked_sibling_id, " source_chunk_id ",
                         "blocked-chunk", None),
                        (blocked_sibling_id, " source_turn_index ", None, 1),
                        (blocked_sibling_id, " turn_privacy ", "standard", None),
                    ],
                )
                fixture.execute(
                    "UPDATE embedding_metadata SET key = ?, string_value = ? "
                    "WHERE id = ? AND key = 'path'",
                    ("\u2003path\u2029", f"\t\u2003{blocked_path}\u2029\n",
                     blocked_sibling_id),
                )
                fixture.execute(
                    "UPDATE embedding_metadata SET key = ? "
                    "WHERE id = ? AND key = 'type'",
                    ("\u2003type\u2029", 7),
                )
                fixture.execute(
                    "INSERT INTO embedding_metadata"
                    "(id, key, string_value) VALUES (?, ?, ?)",
                    (6, "tags", '["legacy"]'),
                )
                fixture.execute(
                    "INSERT INTO embedding_metadata"
                    "(id, key, bool_value) VALUES (?, ?, ?)",
                    (9, "tag_private", 1),
                )
                fixture.executemany(
                    "INSERT INTO embedding_metadata_array"
                    "(id, key, string_value) VALUES (?, ?, ?)",
                    [
                        (1, "tags", "alpha"),
                        (6, "tags", "beta"),
                        (6, "\u2003project_ids\u2029", "project-x"),
                        (1, "chroma:document", document_sentinel),
                    ],
                )
                candidate_row_ids = (
                    1, 6, 7, 9, 10, 11, 12, 13, blocked_sibling_id,
                    *filler_row_ids,
                )
                fixture.commit()
            finally:
                fixture.close()

            fixture_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()
            fixture_entries = sorted(path.name for path in chroma_dir.iterdir())
            connect_calls = []
            statements = []
            raw_key_rows = []
            raw_key_queries = []
            identity_queries = []
            identity_parameters = []
            identity_query_plan = []
            selected_flat_row_ids = []
            flat_rows = []
            flat_queries = []
            flat_parameters = []
            flat_query_plan = []
            registered_functions = []
            streamed_cursors = []
            stat_calls = []
            real_stat = server.os.stat

            class StreamingCursor:
                def __init__(self, cursor, label):
                    self._cursor = cursor
                    self._label = label
                    self._started = False

                def __iter__(self):
                    if not self._started:
                        streamed_cursors.append(self._label)
                        self._started = True
                    return self

                def __next__(self):
                    row = next(self._cursor)
                    if self._label == "keys":
                        raw_key_rows.append(row)
                    elif self._label == "flat":
                        selected_flat_row_ids.append(row[1])
                        flat_rows.append(row)
                    return row

                def fetchall(self):
                    raise AssertionError(
                        f"{self._label} inventory must be streamed"
                    )

                def __getattr__(self, name):
                    return getattr(self._cursor, name)

            class ReadOnlyConnection:
                def __init__(self, connection):
                    self._connection = connection

                def execute(self, sql, parameters=()):
                    normalized = " ".join(sql.split())
                    if "SELECT DISTINCT metadata.key AS key" in normalized:
                        raw_key_queries.append(normalized)
                    elif "AS identity_key" in normalized:
                        identity_queries.append(normalized)
                        identity_parameters.append(parameters)
                        identity_query_plan.extend(
                            self._connection.execute(
                                f"EXPLAIN QUERY PLAN {sql}", parameters,
                            ).fetchall()
                        )
                    elif "FROM json_each(?) AS candidate" in normalized:
                        flat_queries.append(normalized)
                        flat_parameters.append(parameters)
                        flat_query_plan.extend(
                            self._connection.execute(
                                f"EXPLAIN QUERY PLAN {sql}", parameters,
                            ).fetchall()
                        )
                    cursor = self._connection.execute(sql, parameters)
                    if "SELECT DISTINCT metadata.key AS key" in normalized:
                        return StreamingCursor(cursor, "keys")
                    if "AS identity_key" in normalized:
                        return StreamingCursor(cursor, "identity")
                    if "FROM json_each(?) AS candidate" in normalized:
                        return StreamingCursor(cursor, "flat")
                    return cursor

                def create_function(self, name, narg, function, **kwargs):
                    registered_functions.append((name, narg))
                    return self._connection.create_function(
                        name, narg, function, **kwargs,
                    )

                def __getattr__(self, name):
                    return getattr(self._connection, name)

            def read_only_connect(database, *args, **kwargs):
                connect_calls.append((database, args, kwargs))
                connection = real_connect(database, *args, **kwargs)
                connection.set_trace_callback(statements.append)
                return ReadOnlyConnection(connection)

            def counted_stat(path, *args, **kwargs):
                stat_calls.append(str(path))
                return real_stat(path, *args, **kwargs)

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
                mock.patch.object(server.os, "stat", side_effect=counted_stat),
            ):
                engrams = server._library_engram_provider()
                vector_only = server._library_engram_provider()

            self.assertFalse(engrams["complete"])
            self.assertIn("unstable identities", engrams["reason"])
            self.assertEqual(len(engrams["rows"]), 1)
            engram = engrams["rows"][0]
            self.assertEqual(engram["identity"], str(engram_path.resolve()))
            self.assertEqual(engram["title"], "Indexed Engram")
            self.assertEqual(
                engram["metadata"]["tags"], ["alpha", "legacy", "beta"],
            )
            self.assertEqual(
                engram["metadata"]["project_ids"], ["ora", "project-x"],
            )
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
            admission_groups = []
            for admission_call in admitted_paths.call_args_list:
                admitted_metadata, admitted_target = admission_call.args
                self.assertEqual(admitted_target, "")
                admitted_group_paths = {
                    str(row.get("path") or "").strip()
                    for row in admitted_metadata
                }
                self.assertEqual(len(admitted_group_paths), 1)
                admission_groups.append(admitted_metadata)
            all_admitted_metadata = [
                row for group in admission_groups for row in group
            ]
            admitted_by_id = {
                (str(row["path"]).strip(), row["type"], row.get("title")): row
                for row in all_admitted_metadata
            }
            self.assertTrue(all(
                masked_numeric_key not in row for row in all_admitted_metadata
            ))
            self.assertTrue(all(
                masked_numeric_key not in row["metadata"]
                for row in engrams["rows"]
            ))
            self.assertIn(
                (str(engram_path), "engram", "Indexed Engram"),
                admitted_by_id,
            )
            self.assertIn(
                (str(blocked_path), "chat", "Blocked sibling"),
                admitted_by_id,
            )
            self.assertEqual(
                admitted_by_id[
                    (str(blocked_path), "chat", "Blocked sibling")
                ]["artifact_kind"],
                "conversation_runtime_derivative",
            )
            self.assertEqual(
                admitted_by_id[
                    (str(blocked_path), "chat", "Blocked sibling")
                ]["source_turn_index"],
                1,
            )
            self.assertIs(
                type(admitted_by_id[
                    (str(blocked_path), "chat", "Blocked sibling")
                ]["source_turn_index"]),
                int,
            )
            self.assertIs(
                admitted_by_id[
                    (str(private_path), "engram", "Private Engram")
                ]["tag_private"],
                True,
            )
            blocked_admission_groups = [
                group for group in admission_groups
                if str(group[0].get("path") or "").strip() == str(blocked_path)
            ]
            self.assertEqual(len(blocked_admission_groups), 1)
            self.assertEqual(
                {row.get("title") for row in blocked_admission_groups[0]},
                {"Blocked Engram", "Blocked sibling"},
            )
            self.assertNotIn(
                str(blocked_path.resolve()),
                [row["identity"] for row in engrams["rows"]],
            )
            self.assertNotIn(
                str(private_path.resolve()),
                [row["identity"] for row in engrams["rows"]],
            )
            self.assertNotIn(
                str(blank_key_path.resolve()),
                [row["identity"] for row in engrams["rows"]],
            )
            self.assertNotIn(
                str(duplicate_key_path.resolve()),
                [row["identity"] for row in engrams["rows"]],
            )
            self.assertEqual(stat_calls, [str(engram_path.resolve())])
            self.assertEqual(set(selected_flat_row_ids), set(candidate_row_ids))
            self.assertNotIn(5, selected_flat_row_ids)
            candidate_batches = [
                json.loads(parameters[0]) for parameters in flat_parameters
            ]
            self.assertEqual(len(candidate_batches), 2)
            self.assertIn(7, candidate_batches[0])
            self.assertNotIn(blocked_sibling_id, candidate_batches[0])
            self.assertNotIn(7, candidate_batches[1])
            self.assertIn(blocked_sibling_id, candidate_batches[1])
            self.assertEqual(
                set().union(*(set(batch) for batch in candidate_batches)),
                set(candidate_row_ids),
            )
            self.assertEqual({row[0] for row in flat_rows}, {"scalar", "array"})
            self.assertTrue(all(len(row) == 5 for row in flat_rows))
            self.assertIn("", [
                row[2].strip() for row in flat_rows
                if row[0] == "scalar" and row[1] == 12
            ])
            self.assertEqual(sum(
                row[0] == "scalar" and row[1] == 13
                and row[2].strip() == "title"
                for row in flat_rows
            ), 2)
            document_rows = [
                row for row in flat_rows
                if row[2] == "chroma:document"
            ]
            self.assertEqual(document_rows, [])
            masked_numeric_rows = [
                row for row in flat_rows
                if row[0] == "scalar" and row[2] == masked_numeric_key
            ]
            self.assertEqual(masked_numeric_rows, [])
            self.assertFalse(any(
                document_sentinel in value
                for row in flat_rows
                for value in row[3:]
                if isinstance(value, str)
            ))
            discovered_raw_keys = set(raw_key_rows)
            self.assertIn(("scalar", "\u2003path\u2029"), discovered_raw_keys)
            self.assertIn(("scalar", "\u2003type\u2029"), discovered_raw_keys)
            self.assertIn(
                ("scalar", "\u2003artifact_kind\u2029"),
                discovered_raw_keys,
            )
            self.assertIn(
                ("array", "\u2003project_ids\u2029"),
                discovered_raw_keys,
            )
            identity_bound_keys = set(json.loads(identity_parameters[0][0]))
            self.assertTrue({
                "path", "type", "\u2003path\u2029", "\u2003type\u2029",
            }.issubset(identity_bound_keys))
            scalar_bound_keys = set(json.loads(flat_parameters[0][1]))
            scalar_guard_keys = set(json.loads(flat_parameters[0][3]))
            array_bound_keys = set(json.loads(flat_parameters[0][5]))
            self.assertIn("\u2003artifact_kind\u2029", scalar_bound_keys)
            self.assertIn("\u2003project_ids\u2029", array_bound_keys)
            self.assertIn(" \t ", scalar_guard_keys)
            self.assertTrue({"title", " title "}.issubset(scalar_bound_keys))
            self.assertNotIn("chroma:document", scalar_bound_keys)
            self.assertNotIn("chroma:document", array_bound_keys)
            self.assertNotIn(masked_numeric_key, scalar_bound_keys)
            self.assertTrue(all(
                set(json.loads(parameters[1])) == scalar_bound_keys
                and set(json.loads(parameters[3])) == scalar_guard_keys
                and set(json.loads(parameters[5])) == array_bound_keys
                for parameters in flat_parameters
            ))
            self.assertEqual(registered_functions, [])
            self.assertEqual(
                streamed_cursors, ["keys", "identity", "flat", "flat"],
            )

            expected_connect = (
                f"file:{db_path}?mode=ro", (), {"uri": True},
            )
            self.assertEqual(connect_calls, [expected_connect, expected_connect])
            self.assertTrue(all(
                "immutable" not in database for database, _args, _kwargs in connect_calls
            ))
            normalized_statements = [" ".join(sql.split()) for sql in statements]
            self.assertEqual(normalized_statements[0], "PRAGMA query_only=ON")
            self.assertEqual(normalized_statements[-1], "COMMIT")
            first_begin = normalized_statements.index("BEGIN")
            first_commit = normalized_statements.index("COMMIT", first_begin)
            second_begin = normalized_statements.index("BEGIN", first_commit + 1)
            second_commit = normalized_statements.index("COMMIT", second_begin)
            first_reads = [
                sql for sql in normalized_statements[first_begin + 1:first_commit]
                if sql.startswith("SELECT ")
            ]
            second_reads = [
                sql for sql in normalized_statements[second_begin + 1:second_commit]
                if sql.startswith("SELECT ")
            ]
            self.assertEqual(len(first_reads), 5)
            self.assertEqual(len(second_reads), 1)
            self.assertEqual(len(raw_key_queries), 1)
            self.assertEqual(len(identity_queries), 1)
            self.assertEqual(len(flat_queries), 2)
            self.assertEqual(len(set(flat_queries)), 1)
            self.assertTrue(all(
                all(table in query for table in (
                    "databases", "collections", "segments",
                ))
                for query in (first_reads[0], second_reads[0])
            ))
            raw_key_query = raw_key_queries[0]
            identity_query = identity_queries[0]
            flat_query = flat_queries[0]
            self.assertIn("SELECT DISTINCT metadata.key AS key", raw_key_query)
            self.assertEqual(raw_key_query.count("embedding.segment_id = ?"), 2)
            self.assertTrue(all(
                table in raw_key_query for table in (
                    "embeddings", "embedding_metadata",
                    "embedding_metadata_array",
                )
            ))
            self.assertIn("FROM embeddings AS embedding", identity_query)
            self.assertIn("CROSS JOIN json_each(?) AS identity_key", identity_query)
            self.assertIn("metadata.key = identity_key.value", identity_query)
            self.assertNotIn("embedding_metadata_array", identity_query)
            self.assertTrue(all(
                table in flat_query for table in (
                    "json_each", "embedding_metadata",
                    "embedding_metadata_array",
                )
            ))
            self.assertNotIn("embeddings AS embedding", flat_query)
            self.assertIn("UNION ALL", flat_query)
            self.assertEqual(
                flat_query.count("FROM json_each(?) AS candidate"), 3,
            )
            self.assertEqual(
                flat_query.count("WHERE +metadata.key IN ("), 3,
            )
            self.assertEqual(
                flat_query.count("SELECT value FROM json_each(?)"), 3,
            )
            self.assertNotIn("AS selected_key", flat_query)
            hot_sql = " ".join([identity_query, *flat_queries])
            self.assertNotIn("PYTHON_STRIP", hot_sql)
            self.assertNotIn("PYTHON_PROJECTABLE_KEY", hot_sql)
            identity_plan_details = [
                str(row[3]) for row in identity_query_plan
            ]
            self.assertTrue(any(
                "sqlite_autoindex_embedding_metadata_1 (id=? AND key=?)"
                in detail
                for detail in identity_plan_details
            ), identity_plan_details)
            plan_details = [str(row[3]) for row in flat_query_plan]
            candidate_plan_rows = [
                index for index, detail in enumerate(plan_details)
                if "SCAN candidate VIRTUAL TABLE" in detail
            ]
            metadata_plan_rows = [
                index for index, detail in enumerate(plan_details)
                if (
                    "SEARCH metadata USING INDEX" in detail
                    or "SEARCH metadata USING COVERING INDEX" in detail
                )
            ]
            self.assertEqual(len(candidate_plan_rows), 6, plan_details)
            self.assertEqual(len(metadata_plan_rows), 6, plan_details)
            for candidate_plan_row, metadata_plan_row in zip(
                candidate_plan_rows, metadata_plan_rows,
            ):
                self.assertLess(
                    candidate_plan_row, metadata_plan_row, plan_details,
                )
            metadata_plan_details = [
                plan_details[index] for index in metadata_plan_rows
            ]
            self.assertTrue(all(
                "(id=?)" in detail for detail in metadata_plan_details
            ), metadata_plan_details)
            self.assertFalse(any(
                "key=?" in detail for detail in metadata_plan_details
            ), metadata_plan_details)
            self.assertEqual(sum(
                "LIST SUBQUERY" in detail for detail in plan_details
            ), 6, plan_details)
            self.assertEqual(sum(
                "CREATE BLOOM FILTER" in detail for detail in plan_details
            ), 6, plan_details)
            self.assertTrue(any(
                "sqlite_autoindex_embedding_metadata_1 (id=?)"
                in detail
                for detail in plan_details
            ), plan_details)
            self.assertTrue(any(
                "embedding_metadata_array_by_id_key (id=?)"
                in detail
                for detail in plan_details
            ), plan_details)
            self.assertFalse(any(
                "SEARCH embedding USING INTEGER PRIMARY KEY" in detail
                for detail in plan_details
            ), plan_details)
            self.assertNotIn("chroma:document", [row[2] for row in flat_rows])
            self.assertNotIn("json_object", flat_query)
            self.assertNotIn("json_group_array", flat_query)
            self.assertNotIn(" OVER ", flat_query)
            self.assertNotIn(" GROUP BY ", flat_query)
            self.assertNotIn(" ORDER BY ", flat_query)
            provider_source = inspect.getsource(server._library_engram_provider)
            self.assertNotIn("json.loads", provider_source)
            self.assertNotIn("metadata_records", provider_source)
            self.assertNotIn("connection.create_function", provider_source)
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
