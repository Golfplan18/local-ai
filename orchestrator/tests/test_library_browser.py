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
        import os
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
            regular_sibling_path = root / "regular-sibling-engram.md"
            symlink_alias_path = root / "zz-indexed-engram-alias.md"
            missing_path = root / "missing-engram.md"
            for path in (
                engram_path, vector_path, other_database_path, vector_only_path,
                non_engram_path, blocked_path, private_path, blank_key_path,
                duplicate_key_path, regular_sibling_path,
            ):
                path.write_text(f"# {path.stem}\n", encoding="utf-8")
            indexed_mtime = 1_700_000_200
            sibling_mtime = 1_700_000_100
            os.utime(engram_path, (indexed_mtime, indexed_mtime))
            os.utime(regular_sibling_path, (sibling_mtime, sibling_mtime))
            symlink_alias_path.symlink_to(engram_path.name)
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
                        (14, "segment-metadata", "chunk-regular-sibling"),
                        (15, "segment-metadata", "chunk-symlink-alias"),
                        (16, "segment-metadata", "chunk-missing-engram"),
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
                    (14, regular_sibling_path, "Regular sibling", "engram"),
                    (15, symlink_alias_path, "Symlink alias", "engram"),
                    (16, missing_path, "Missing Engram", "engram"),
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
                    1, 6, 7, 9, 10, 11, 12, 13, 14, 15, 16,
                    blocked_sibling_id,
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
            identity_payload_rows = []
            identity_rows = []
            selected_flat_row_ids = []
            flat_rows = []
            flat_payload_rows = []
            flat_queries = []
            flat_parameters = []
            flat_query_plan = []
            registered_functions = []
            streamed_cursors = []
            scandir_calls = []
            realpath_calls = []
            real_scandir = server.os.scandir
            real_realpath = server.os.path.realpath

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
                    elif self._label == "identity":
                        identity_payload_rows.append(row)
                        (payload,) = row
                        identity_rows.extend(
                            tuple(payload_row)
                            for payload_row in json.loads(payload)
                        )
                    elif self._label == "flat":
                        flat_payload_rows.append(row)
                        lane, payload = row
                        for payload_row in json.loads(payload):
                            logical_row = (lane, *payload_row)
                            selected_flat_row_ids.append(logical_row[1])
                            flat_rows.append(logical_row)
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

            def counted_scandir(path, *args, **kwargs):
                scandir_calls.append(str(path))
                return real_scandir(path, *args, **kwargs)

            def counted_realpath(path, *args, **kwargs):
                realpath_calls.append(str(path))
                return real_realpath(path, *args, **kwargs)

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
                mock.patch.object(
                    server.os, "stat",
                    side_effect=AssertionError(
                        "the Engram universe must use parent enumeration stats"
                    ),
                ) as universe_stat,
                mock.patch.object(
                    server.os, "scandir", side_effect=counted_scandir,
                ),
                mock.patch.object(
                    server.os.path, "realpath", side_effect=counted_realpath,
                ),
                mock.patch.object(
                    server.os.path, "islink",
                    side_effect=AssertionError(
                        "the Engram universe must use enumerated symlink state"
                    ),
                ) as universe_islink,
            ):
                engrams = server._library_engram_provider()
                vector_only = server._library_engram_provider()

            self.assertFalse(engrams["complete"])
            self.assertIn("unstable identities", engrams["reason"])
            self.assertEqual(len(engrams["rows"]), 3)
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
            self.assertFalse(engram["preview"]["available"])
            self.assertIn("returned Library rows", engram["preview"]["reason"])
            self.assertTrue(engram["editability"]["available"])
            self.assertFalse(engram["editability"]["editable"])
            self.assertIn(
                "unique direct source", engram["editability"]["reason"],
            )
            self.assertEqual(engram["provenance"]["details"], {
                "index": "knowledge",
            })
            self.assertEqual(
                [row["identity"] for row in engrams["rows"]],
                [
                    str(engram_path.resolve()),
                    str(missing_path.resolve()),
                    str(regular_sibling_path.resolve()),
                ],
            )
            self.assertEqual(
                sum(
                    row["identity"] == str(engram_path.resolve())
                    for row in engrams["rows"]
                ),
                1,
            )
            self.assertNotIn(
                str(symlink_alias_path),
                [row["identity"] for row in engrams["rows"]],
            )
            missing_engram = next(
                row for row in engrams["rows"]
                if row["identity"] == str(missing_path.resolve())
            )
            self.assertIn(
                "modified_at", missing_engram["unavailable_fields"],
            )
            self.assertFalse(missing_engram["preview"]["available"])
            self.assertTrue(missing_engram["editability"]["available"])
            self.assertFalse(missing_engram["editability"]["editable"])
            self.assertIn(
                "provider is incomplete",
                missing_engram["editability"]["reason"],
            )
            self.assertEqual(
                engram["metadata"]["modified_at"],
                server.datetime.fromtimestamp(indexed_mtime).isoformat(
                    timespec="seconds",
                ),
            )
            regular_sibling = next(
                row for row in engrams["rows"]
                if row["identity"] == str(regular_sibling_path.resolve())
            )
            self.assertEqual(
                regular_sibling["metadata"]["modified_at"],
                server.datetime.fromtimestamp(sibling_mtime).isoformat(
                    timespec="seconds",
                ),
            )
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
            canonical_root = engram_path.resolve().parent
            self.assertEqual(scandir_calls, [str(canonical_root)])
            universe_stat.assert_not_called()
            universe_islink.assert_not_called()
            self.assertEqual(
                realpath_calls,
                [str(root), str(canonical_root / symlink_alias_path.name)],
            )
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
            self.assertEqual(len(flat_payload_rows), 6)
            self.assertTrue(all(len(row) == 2 for row in flat_payload_rows))
            self.assertTrue(all(
                isinstance(json.loads(row[1]), list)
                for row in flat_payload_rows
            ))
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
            self.assertEqual(len(identity_payload_rows), 1)
            self.assertEqual(len(identity_payload_rows[0]), 1)
            self.assertEqual(
                len(identity_rows), 2 * (len(candidate_row_ids) + 1),
            )
            self.assertTrue(all(len(row) == 4 for row in identity_rows))
            self.assertEqual(
                {row[0] for row in identity_rows},
                set(candidate_row_ids) | {5},
            )
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
            self.assertIn(
                "FROM embeddings AS embedding NOT INDEXED", identity_query,
            )
            self.assertIn("CROSS JOIN json_each(?) AS identity_key", identity_query)
            self.assertIn("metadata.key = identity_key.value", identity_query)
            self.assertNotIn("embedding_metadata_array", identity_query)
            self.assertEqual(
                identity_query.count("json_group_array(json_array("), 1,
            )
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
            self.assertEqual(
                flat_query.count("json_group_array(json_array("), 3,
            )
            self.assertNotIn("AS selected_key", flat_query)
            hot_sql = " ".join([identity_query, *flat_queries])
            self.assertNotIn("PYTHON_STRIP", hot_sql)
            self.assertNotIn("PYTHON_PROJECTABLE_KEY", hot_sql)
            identity_plan_details = [
                str(row[3]) for row in identity_query_plan
            ]
            self.assertTrue(any(
                "SCAN embedding" in detail
                for detail in identity_plan_details
            ), identity_plan_details)
            self.assertFalse(any(
                "sqlite_autoindex_embeddings_1" in detail
                for detail in identity_plan_details
            ), identity_plan_details)
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
            self.assertNotIn(" OVER ", flat_query)
            self.assertNotIn(" GROUP BY ", flat_query)
            self.assertNotIn(" ORDER BY ", flat_query)
            provider_source = inspect.getsource(server._library_engram_provider)
            self.assertIn("json.loads(payload)", provider_source)
            self.assertNotIn("metadata_records", provider_source)
            self.assertNotIn("connection.create_function", provider_source)
            self.assertEqual(
                hashlib.sha256(db_path.read_bytes()).hexdigest(), fixture_hash,
            )
            self.assertEqual(
                sorted(path.name for path in chroma_dir.iterdir()), fixture_entries,
            )

            permission_calls = []

            def returned_row_access(path, mode):
                permission_calls.append((str(path), mode))
                self.assertEqual(str(path), str(engram_path.resolve()))
                return mode == server.os.R_OK

            with (
                mock.patch.object(server.rp, "chromadb_dir", return_value=chroma_dir),
                mock.patch.object(
                    embedding, "resolve_collection", return_value=physical_collection,
                ),
                mock.patch.object(
                    server, "_library_resolve_relationships",
                    return_value={
                        "state": "unavailable",
                        "reason": "test relationship authority is unavailable",
                        "items": {},
                    },
                ),
                mock.patch.object(
                    server.os, "access", side_effect=returned_row_access,
                ),
                mock.patch.object(server, "_library_dialogue_provider", return_value={"rows": [], "complete": True}),
                mock.patch.object(server, "_library_file_provider", return_value={"rows": [], "complete": True}),
                server.app.test_client() as client,
            ):
                page_response = client.get(
                    "/api/library/browser?source=engrams&limit=1",
                )

            self.assertEqual(page_response.status_code, 200)
            page_payload = page_response.get_json()
            self.assertEqual(page_payload["total"], 3)
            self.assertEqual(page_payload["source_counts"], {"engrams": 3})
            self.assertEqual(page_payload["pagination"]["returned"], 1)
            self.assertTrue(page_payload["pagination"]["has_more"])
            self.assertEqual(
                page_payload["facets"]["editability"]["counts"],
                {"editable": 0, "read_only": 3, "unavailable": 0},
            )
            self.assertEqual(
                page_payload["facets"]["item_type"]["counts"],
                {"engram": 3},
            )
            page_row = page_payload["rows"][0]
            self.assertEqual(
                page_row["preview"]["locator"]["path"], str(engram_path.resolve()),
            )
            self.assertFalse(page_row["provenance"]["available"])
            self.assertTrue(page_row["preview"]["available"])
            self.assertTrue(page_row["editability"]["available"])
            self.assertFalse(page_row["editability"]["editable"])
            self.assertEqual(
                permission_calls,
                [
                    (str(engram_path.resolve()), server.os.R_OK),
                    (str(engram_path.resolve()), server.os.W_OK),
                ],
            )
            self.assertEqual(
                hashlib.sha256(db_path.read_bytes()).hexdigest(), fixture_hash,
            )
            self.assertEqual(
                sorted(path.name for path in chroma_dir.iterdir()), fixture_entries,
            )

            encoded_engram = server._browser_encode_source_id(
                "engram", str(engram_path),
            )
            encoded_regular_sibling = server._browser_encode_source_id(
                "engram", str(regular_sibling_path),
            )
            canonical_engram_path = str(engram_path.resolve())
            windows_realpath_calls = []

            def windows_realpath(path, *args, **kwargs):
                value = str(path)
                windows_realpath_calls.append(value)
                if value == str(canonical_root / regular_sibling_path.name):
                    return canonical_engram_path
                return real_realpath(path, *args, **kwargs)

            real_os = server.os

            class WindowsOSProxy:
                name = "nt"

                def __getattr__(self, name):
                    return getattr(real_os, name)

            with (
                mock.patch.object(server, "os", WindowsOSProxy()),
                mock.patch.object(
                    real_os.path, "realpath", side_effect=windows_realpath,
                ),
                mock.patch.object(
                    real_os.path, "islink",
                    side_effect=AssertionError(
                        "Windows leaves must use full-path realpath"
                    ),
                ) as windows_islink,
                mock.patch.object(server.rp, "chromadb_dir", return_value=chroma_dir),
                mock.patch.object(
                    embedding, "resolve_collection", return_value=physical_collection,
                ),
                mock.patch.object(
                    server, "_browser_chroma_exact_rows",
                    return_value=[{"conversation_id": encoded_regular_sibling}],
                ),
                mock.patch.object(
                    server, "_browser_chroma_fuzzy_rows", return_value=[],
                ),
            ):
                windows_searched = server._library_engram_provider("forecast")

            self.assertEqual(
                [row["identity"] for row in windows_searched["rows"]],
                [canonical_engram_path],
            )
            windows_islink.assert_not_called()
            self.assertEqual(
                windows_realpath_calls,
                [
                    str(root),
                    str(canonical_root / engram_path.name),
                    str(canonical_root / missing_path.name),
                    str(canonical_root / regular_sibling_path.name),
                    str(canonical_root / symlink_alias_path.name),
                ],
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

            malformed_search_path = server.os.path.join(
                str(root), "malformed-search\x00-engram.md",
            )
            encoded_malformed_search = server._browser_encode_source_id(
                "engram", malformed_search_path,
            )
            with (
                mock.patch.object(server.rp, "chromadb_dir", return_value=chroma_dir),
                mock.patch.object(
                    embedding, "resolve_collection", return_value=physical_collection,
                ),
                mock.patch.object(
                    server, "_browser_chroma_exact_rows",
                    return_value=[{"conversation_id": encoded_malformed_search}],
                ),
                mock.patch.object(
                    server, "_browser_chroma_fuzzy_rows", return_value=[],
                ),
            ):
                malformed_search = server._library_engram_provider("forecast")

            self.assertFalse(malformed_search["complete"])
            self.assertEqual(malformed_search["rows"], [])
            self.assertIn("keyword search paths", malformed_search["reason"])

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
            obsidian_uri = (
                "obsidian://open?vault=Wisdom%20Nexus&"
                "file=Projects%2FOra%2Ff0.md"
            )

            def provider_obsidian_uri(path):
                return obsidian_uri if path == str(file_paths[0]) else None

            with (
                mock.patch.object(
                    project_meta, "list_project_meta", return_value=[{
                        "nexus": "ora", "folder_name": "Ora", "is_default": False,
                    }],
                ) as list_projects,
                mock.patch.object(
                    project_meta, "list_project_files", return_value=inventory,
                ) as list_files,
                mock.patch.object(
                    server, "_obsidian_uri_for",
                    side_effect=provider_obsidian_uri,
                ) as obsidian_for,
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
            file_rows = {row["identity"]: row for row in files["rows"]}
            self.assertEqual(
                file_rows[str(file_paths[0])]["preview"]["locator"],
                {"path": str(file_paths[0]), "obsidian_uri": obsidian_uri},
            )
            self.assertEqual(
                file_rows[str(file_paths[1])]["preview"]["locator"],
                {"path": str(file_paths[1])},
            )
            self.assertEqual(
                obsidian_for.call_args_list,
                [mock.call(str(path)) for path in file_paths],
            )
            list_files.assert_called_once_with("Ora", max_files=None)
            list_projects.assert_called_once_with(skipped_authority=mock.ANY)
            self.assertEqual(
                list_projects.call_args.kwargs["skipped_authority"], [],
            )

            malformed_inventory_path = server.os.path.join(
                str(root), "malformed-inventory\x00-engram.md",
            )
            malformed_row_id = 60_000
            fixture = real_connect(db_path)
            try:
                fixture.execute(
                    "INSERT INTO embeddings(id, segment_id, embedding_id) "
                    "VALUES (?, ?, ?)",
                    (malformed_row_id, "segment-metadata", "chunk-malformed-path"),
                )
                fixture.executemany(
                    "INSERT INTO embedding_metadata"
                    "(id, key, string_value) VALUES (?, ?, ?)",
                    [
                        (malformed_row_id, "nexus", "ora"),
                        (malformed_row_id, "path", malformed_inventory_path),
                        (malformed_row_id, "title", "Malformed path Engram"),
                        (malformed_row_id, "type", "engram"),
                    ],
                )
                fixture.commit()
            finally:
                fixture.close()

            with (
                mock.patch.object(server.rp, "chromadb_dir", return_value=chroma_dir),
                mock.patch.object(
                    embedding, "resolve_collection", return_value=physical_collection,
                ),
            ):
                malformed_inventory = server._library_engram_provider()

            self.assertEqual(malformed_inventory, {
                "rows": [],
                "complete": False,
                "reason": "the Engram index could not be read",
            })

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

    def test_text_preview_revalidates_library_authority(self):
        import base64
        import io
        import tempfile
        from pathlib import Path

        from PIL import Image as PillowImage

        server = _server_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            engram, empty_engram, plain_engram, project_file, withheld, invalid, malformed = (
                root / "admitted.md", root / "empty.md", root / "plain.md",
                root / "notes.txt", root / "withheld.md", root / "invalid.md",
                root / "malformed.md",
            )
            image, image_link, image_spoof, image_svg, image_truncated = (
                root / "admitted.png", root / "linked.png",
                root / "spoofed.png", root / "unsupported.svg",
                root / "truncated.jpg",
            )
            exact_body = "\n  # Engram\r\nVisible body  \r\n\r\n"
            plain_body = "  Plain body\r\nTrailing  \r\n"
            for path, text in (
                (engram, "---\ntags: [engram]\n---\n" + exact_body),
                (empty_engram, "---\ntags: [engram]\n---"),
                (plain_engram, plain_body),
                (project_file, "Project body\n**plain text**\n"),
                (withheld, "---\ntags: [private]\n---\nprivate body"),
                (malformed, "---\ntags: [engram]\nno closing fence"),
            ):
                path.write_bytes(text.encode("utf-8"))
            invalid.write_bytes(
                b"---\ntags: [engram]\n---\ninvalid \xff SECRET_INVALID_BODY"
            )
            image_bytes = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
                "+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
            image.write_bytes(image_bytes)
            image_link.symlink_to(image)
            image_spoof.write_bytes(b"not a PNG")
            image_svg.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
            jpeg_buffer = io.BytesIO()
            with PillowImage.new("RGB", (1, 1)) as valid_jpeg:
                valid_jpeg.save(jpeg_buffer, format="JPEG")
            image_truncated.write_bytes(jpeg_buffer.getvalue()[:-2])

            def row(path, kind="text", available=True):
                return {"identity": str(path), "preview": {
                    "kind": kind, "available": available,
                    "locator": {"path": str(path)},
                }}

            with (
                server.app.test_client() as client,
                mock.patch.object(
                    server, "_browser_engram_envelope",
                    wraps=server._browser_engram_envelope,
                ) as reader,
            ):
                def request(source, item_path, rows, **extra):
                    provider = ("_library_engram_provider" if source == "engrams"
                                else "_library_file_provider")
                    with mock.patch.object(server, provider,
                                           return_value={"rows": rows}):
                        return client.get("/api/library/preview", query_string={
                            "id": stable_item_id(source, str(item_path)), **extra,
                        })

                for source, path, expected in (
                    ("engrams", engram, exact_body),
                    ("engrams", empty_engram, ""),
                    ("engrams", plain_engram, plain_body),
                    ("files", project_file, "Project body\n**plain text**\n"),
                ):
                    with self.subTest(f"admitted {source}"):
                        response = request(source, path, [row(
                            path, available=source == "files",
                        )])
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.get_json()["text"], expected)

                raster = request("files", image, [row(image, "visual")])
                self.assertEqual(raster.status_code, 200)
                self.assertEqual(raster.get_json()["image"]["mime_type"], "image/png")
                self.assertEqual(
                    base64.b64decode(raster.get_json()["image"]["data"]),
                    image_bytes,
                )

                for label, source, path, rows, extra, status in (
                    ("stale/private", "engrams", withheld,
                     [row(withheld, available=False)], {}, 409),
                    ("unlisted", "files", withheld, [row(project_file)], {}, 404),
                    ("unsupported", "files", project_file,
                     [row(project_file, "unsupported", False)], {}, 409),
                    ("forged locator", "files", project_file, [row(project_file)],
                     {"path": str(withheld)}, 400),
                    ("invalid UTF-8", "engrams", invalid,
                     [row(invalid, available=False)], {}, 409),
                    ("malformed frontmatter", "engrams", malformed,
                     [row(malformed, available=False)], {}, 409),
                ):
                    with self.subTest(label):
                        response = request(source, path, rows, **extra)
                        self.assertEqual(response.status_code, status)
                        self.assertNotIn("private body", response.get_data(as_text=True))
                        self.assertNotIn(
                            "SECRET_INVALID_BODY", response.get_data(as_text=True),
                        )

                for label, path, rows, extra, status in (
                    ("stale/unlisted image", image, [row(project_file)], {}, 404),
                    ("forged image locator", image, [row(image, "visual")],
                     {"path": str(image_spoof)}, 400),
                    ("symlink image", image_link, [row(image_link, "visual")], {}, 409),
                    ("unsupported visual type", image_svg,
                     [row(image_svg, "visual")], {}, 409),
                    ("spoofed image bytes", image_spoof,
                     [row(image_spoof, "visual")], {}, 409),
                    ("truncated JPEG pixels", image_truncated,
                     [row(image_truncated, "visual")], {}, 409),
                ):
                    with self.subTest(label):
                        response = request("files", path, rows, **extra)
                        self.assertEqual(response.status_code, status)
                        self.assertNotIn("not a PNG", response.get_data(as_text=True))

                with mock.patch.object(
                    server, "_LIBRARY_IMAGE_PREVIEW_MAX_BYTES",
                    len(image_bytes) - 1,
                ):
                    oversized = request(
                        "files", image, [row(image, "visual")],
                    )
                self.assertEqual(oversized.status_code, 409)

                with mock.patch.object(
                    server.os, "open", side_effect=PermissionError,
                ):
                    unreadable = request(
                        "files", image, [row(image, "visual")],
                    )
                self.assertEqual(unreadable.status_code, 409)

                self.assertTrue(reader.called)
                self.assertTrue(all(call.kwargs == {"target_tag": ""}
                                    for call in reader.call_args_list))

    def test_markdown_edit_revalidates_authority_and_conflicts(self):
        from contextlib import contextmanager
        import stat
        import tempfile
        from pathlib import Path

        from orchestrator import project_meta
        from orchestrator.tools import knowledge_index

        server = _server_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            project_file = root / "project.md"
            malformed_file = root / "malformed.md"
            engram = root / "engram.md"
            private_engram = root / "private-engram.md"
            ambiguous_engram = root / "ambiguous-engram.md"
            project_file.write_bytes(b"Original project file\r\n")
            project_file.chmod(0o640)
            malformed_claim = "---\ntype: engram\nbroken: [\n"
            malformed_file.write_text(malformed_claim, encoding="utf-8")
            standard = (
                "---\nnexus:\n  - ora\ntype: engram\ntags:\n  - atomic\n"
                "date created: 2026-09-02\ndate modified: 2026-09-02\n---\n\n"
                "# Engram\n\nOriginal Standard body long enough for indexing.\n"
            )
            engram.write_text(standard, encoding="utf-8")
            private = standard.replace("  - atomic", "  - private")
            private_engram.write_text(private, encoding="utf-8")
            ambiguous_engram.write_text(standard, encoding="utf-8")
            inventory = {
                "exists": True, "complete": True, "files": [{
                    "abs_path": str(engram), "name": engram.name,
                    "rel_path": engram.name, "mtime": None,
                    "size": engram.stat().st_size,
                }],
                "total": 1, "offset": 0, "next_offset": None,
            }
            with (
                mock.patch.object(project_meta, "list_project_meta", return_value=[{
                    "nexus": "ora", "is_default": True,
                }]),
                mock.patch.object(project_meta, "list_project_files", return_value=inventory),
            ):
                provider_row = server._library_file_provider()["rows"][0]
                inventory["files"][0] = {
                    "abs_path": str(malformed_file), "name": malformed_file.name,
                    "rel_path": malformed_file.name, "mtime": None,
                    "size": malformed_file.stat().st_size,
                }
                malformed_provider_row = (
                    server._library_file_provider()["rows"][0]
                )
            self.assertFalse(provider_row["editability"]["editable"])
            self.assertFalse(
                malformed_provider_row["editability"]["editable"],
            )
            self.assertIn(
                "frontmatter",
                malformed_provider_row["editability"]["reason"],
            )
            preview = {"kind": "text", "available": True}
            file_rows = {"complete": True, "rows": [
                {
                    "identity": str(path),
                    "metadata": {"content_type": "text/markdown"},
                    "preview": preview,
                }
                for path in (
                    project_file, engram, private_engram, malformed_file,
                )
            ]}
            engram_rows = {"complete": True, "rows": [
                {"identity": str(engram), "_unique_direct_authority": True},
                {"identity": str(ambiguous_engram),
                 "_unique_direct_authority": False},
            ]}
            file_id = stable_item_id("files", str(project_file))
            engram_id = stable_item_id("engrams", str(engram))
            ambiguous_id = stable_item_id("engrams", str(ambiguous_engram))
            file_engram_id = stable_item_id("files", str(engram))
            private_file_engram_id = stable_item_id("files", str(private_engram))
            malformed_file_id = stable_item_id("files", str(malformed_file))
            lock_state = {"paths": None, "entries": 0}
            drift_authority = [False]
            drift_provider_calls = [0]
            engram_complete = [True]

            def current_file_rows():
                self.assertIsNone(lock_state["paths"])
                if drift_authority[0]:
                    drift_provider_calls[0] += 1
                    if drift_provider_calls[0] > 1:
                        return {
                            "complete": True, "rows": file_rows["rows"][1:],
                        }
                return file_rows

            def current_engram_rows():
                self.assertIsNone(lock_state["paths"])
                return {**engram_rows, "complete": engram_complete[0]}

            @contextmanager
            def observed_path_locks(paths):
                requested = tuple(paths)
                self.assertEqual(len(requested), 1)
                lock_state["entries"] += 1
                lock_state["paths"] = set(requested)
                try:
                    yield requested
                finally:
                    lock_state["paths"] = None

            with (
                mock.patch.object(
                    server, "_library_file_provider", side_effect=current_file_rows,
                ),
                mock.patch.object(
                    server, "_library_engram_provider",
                    side_effect=current_engram_rows,
                ),
                mock.patch.object(
                    server, "mutation_path_locks", side_effect=observed_path_locks,
                ),
                server.app.test_client() as client,
            ):
                def open_digest(item_id):
                    response = client.get("/api/library/edit", query_string={"id": item_id})
                    self.assertEqual(response.status_code, 200)
                    return response.get_json()["digest"]

                def replace(item_id, digest, text):
                    return client.put("/api/library/edit", json={
                        "id": item_id, "expected_digest": digest, "text": text,
                    })

                saved = replace(
                    file_id, open_digest(file_id), "Saved project file\r\n",
                )
                self.assertEqual(saved.status_code, 200)
                self.assertTrue(saved.get_json()["saved"])
                self.assertIsNone(saved.get_json()["index_refreshed"])
                self.assertEqual(
                    project_file.read_bytes(), b"Saved project file\r\n",
                )
                self.assertEqual(stat.S_IMODE(project_file.stat().st_mode), 0o640)

                for label, unsafe_text in (
                    ("changed to LF", "Saved project file\n"),
                    ("mixed endings", "Mixed\r\nendings\n"),
                    ("lone CR", "Lone\rending"),
                ):
                    with self.subTest(label):
                        unsafe = replace(
                            file_id, open_digest(file_id), unsafe_text,
                        )
                        self.assertEqual(unsafe.status_code, 409)
                        self.assertEqual(
                            project_file.read_bytes(), b"Saved project file\r\n",
                        )

                stale_digest = open_digest(file_id)
                project_file.write_text("Concurrent replacement\n", encoding="utf-8")
                conflict = replace(file_id, stale_digest, "Stale draft must not land\n")
                self.assertEqual(conflict.status_code, 409)
                self.assertEqual(conflict.get_json()["code"], "conflict")
                self.assertEqual(project_file.read_text(), "Concurrent replacement\n")

                converted = replace(file_id, open_digest(file_id), standard)
                self.assertEqual(converted.status_code, 409)
                self.assertEqual(project_file.read_text(), "Concurrent replacement\n")

                malformed_replacement = replace(
                    file_id, open_digest(file_id), malformed_claim,
                )
                self.assertEqual(malformed_replacement.status_code, 409)
                self.assertEqual(project_file.read_text(), "Concurrent replacement\n")
                project_file.write_text(malformed_claim, encoding="utf-8")
                self.assertEqual(client.get(
                    "/api/library/edit", query_string={"id": file_id},
                ).status_code, 409)
                self.assertEqual(
                    replace(file_id, "0" * 64, "Must not land\n").status_code,
                    409,
                )
                self.assertEqual(project_file.read_text(), malformed_claim)
                project_file.write_text("Concurrent replacement\n", encoding="utf-8")

                drift_digest = open_digest(file_id)
                lock_entries = lock_state["entries"]
                drift_provider_calls[0] = 0
                drift_authority[0] = True
                drifted = replace(file_id, drift_digest, "Authority moved\n")
                drift_authority[0] = False
                self.assertEqual(drifted.status_code, 409)
                self.assertEqual(drift_provider_calls[0], 2)
                self.assertEqual(lock_state["entries"], lock_entries)
                self.assertEqual(project_file.read_text(), "Concurrent replacement\n")

                refused = replace(engram_id, open_digest(engram_id), private)
                self.assertEqual(refused.status_code, 409)
                self.assertFalse(refused.get_json()["saved"])
                self.assertEqual(engram.read_text(), standard)

                blocked = replace(ambiguous_id, "0" * 64, standard + "blocked")
                self.assertEqual(blocked.status_code, 409)
                self.assertEqual(ambiguous_engram.read_text(), standard)

                incomplete_digest = open_digest(engram_id)
                engram_complete[0] = False
                incomplete = replace(
                    engram_id, incomplete_digest, standard + "incomplete",
                )
                engram_complete[0] = True
                self.assertEqual(incomplete.status_code, 409)
                self.assertEqual(engram.read_text(), standard)

                self.assertEqual(client.get(
                    "/api/library/edit", query_string={"id": file_engram_id},
                ).status_code, 409)
                standard_preview = client.get(
                    "/api/library/preview",
                    query_string={"id": file_engram_id},
                )
                self.assertEqual(standard_preview.status_code, 409)
                self.assertNotIn(
                    "Original Standard body", standard_preview.get_data(as_text=True),
                )
                private_preview = client.get(
                    "/api/library/preview",
                    query_string={"id": private_file_engram_id},
                )
                self.assertEqual(private_preview.status_code, 409)
                self.assertNotIn(
                    "Original Standard body", private_preview.get_data(as_text=True),
                )
                malformed_preview = client.get(
                    "/api/library/preview",
                    query_string={"id": malformed_file_id},
                )
                self.assertEqual(malformed_preview.status_code, 409)
                self.assertNotIn(
                    "broken", malformed_preview.get_data(as_text=True),
                )

                replacement = standard.replace("Original Standard body", "Saved Standard body")

                def failed_refresh(target, **_kwargs):
                    self.assertIsNone(lock_state["paths"])
                    self.assertEqual(Path(target).read_text(), replacement)
                    return {"indexed": 0, "skipped": 0, "errors": 1}

                with mock.patch.object(
                    knowledge_index, "index_single_file",
                    side_effect=failed_refresh,
                ) as refresh:
                    partial = replace(
                        engram_id, open_digest(engram_id), replacement,
                    )
                self.assertEqual(partial.status_code, 200)
                self.assertTrue(partial.get_json()["saved"])
                self.assertFalse(partial.get_json()["index_refreshed"])
                self.assertIn("not refreshed", partial.get_json()["index_error"])
                self.assertEqual(engram.read_text(), replacement)
                refresh.assert_called_once_with(str(engram), force=True, verbose=False)

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
        fixtures["engrams"]["rows"][0]["identity"] = "/fixture/engram.md"
        with (
            mock.patch.object(
                server, "_library_dialogue_provider",
                side_effect=lambda query="": (
                    searched["dialogues"] if query else fixtures["dialogues"]
                ),
            ) as dialogue_provider,
            mock.patch.object(
                server, "_library_engram_provider",
                side_effect=lambda query="", **_kwargs: (
                    searched["engrams"] if query else fixtures["engrams"]
                ),
            ) as engram_provider,
            mock.patch.object(
                server, "_library_file_provider",
                return_value=fixtures["files"],
            ) as file_provider,
            mock.patch.object(server, "_browser_chroma_exact_rows", return_value=[{
                "conversation_id": server._browser_encode_source_id("engram", "/fixture/engram.md"),
            }]),
            mock.patch.object(server, "_browser_chroma_fuzzy_rows", return_value=[]),
            mock.patch.object(server, "_library_archive_connection", return_value=mock.Mock()) as snapshot_connection,
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
        self.assertEqual(engram_provider.call_count, 3)
        self.assertEqual(engram_provider.call_args_list[:2], [mock.call(), mock.call()])
        self.assertIs(engram_provider.call_args.kwargs["snapshot_connection"], snapshot_connection.return_value)
        self.assertEqual(file_provider.call_count, 3)

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


class TestLibraryCompletion(unittest.TestCase):
    def test_retained_nested_fork_preview_preserves_attribution_privacy_and_files(self):
        import json
        import tempfile
        from pathlib import Path
        server = _server_module()
        import conversation_memory as memory
        def pair(text, privacy="standard"):
            return [{"role": "user", "content": text, "turn_privacy": privacy, "secret_extra": "not returned"},
                    {"role": "assistant", "content": "answer " + text, "turn_privacy": privacy}]
        large_text = "## Complete large source\n" + "λ" * (1024 * 1024) + "\nFinal source line"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bodies = {
                "parent": {"messages": pair("parent public") + pair("later parent")},
                "child": {"parent_conversation_id": "parent", "fork_point_message_count": 2, "messages": pair("child public") + pair("later child")},
                "nested": {"parent_conversation_id": "child", "fork_point_message_count": 2,
                    "messages": pair("local public") + pair("SECRET", "private") + pair("UNKNOWN", None)
                        + [{"role": "assistant", "content": "ORPHAN", "turn_privacy": "standard"}]},
                "large": {"messages": pair(large_text) + pair("SECRET", "private") + pair("UNKNOWN", None)},
            }
            before = {}
            for identity, body in bodies.items():
                path = root / identity / "conversation.json"
                path.parent.mkdir()
                path.write_text(json.dumps({"conversation_id": identity, "project_ids": ["commons"], **body}))
                before[path] = path.read_bytes()
            raw = _row("nested", "Nested", tag="", modified_at="2026-09-01")
            raw["metadata"].update(item_type="dialogue", content_type="application/x-ora-dialogue")
            large_raw = {**raw, "identity": "large", "title": "Large Dialogue"}
            with mock.patch.object(memory, "_DEFAULT_SESSIONS_ROOT", root), \
                 mock.patch.object(server, "_library_dialogue_provider", return_value={"rows": [raw, large_raw], "complete": True}), \
                 mock.patch.object(server, "_library_engram_provider", side_effect=AssertionError("wrong inventory")), \
                 mock.patch.object(server, "_library_file_provider", side_effect=AssertionError("wrong inventory")):
                client = server.app.test_client()
                item_id = stable_item_id("dialogues", "nested")
                response = client.get('/api/library/preview', query_string={"id": item_id})
                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertEqual([turn["content"] for turn in payload["turns"]],
                    ["parent public", "answer parent public", "child public", "answer child public", "local public", "answer local public"])
                self.assertTrue(all(set(turn) == {"role", "content"} for turn in payload["turns"]))
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertNotIn("SECRET", str(payload))
                self.assertNotIn("ORPHAN", str(payload))
                self.assertEqual(client.get('/api/library/edit', query_string={"id": item_id}).status_code, 400)
                self.assertEqual(client.get('/api/library/preview?id=' + item_id + '&id=' + item_id).status_code, 400)
                large_response = client.get('/api/library/preview', query_string={"id": stable_item_id("dialogues", "large")})
                self.assertEqual(large_response.status_code, 200)
                large_turns = large_response.get_json()["turns"]
                self.assertEqual(large_turns, [{"role": "user", "content": large_text},
                                             {"role": "assistant", "content": "answer " + large_text}])
                self.assertTrue(all(len(turn["content"].encode("utf-8")) < 4 * 1024 * 1024 for turn in large_turns))
                self.assertGreater(sum(len(turn["content"].encode("utf-8")) for turn in large_turns), 4 * 1024 * 1024)
                self.assertEqual(large_response.headers['Cache-Control'], 'no-store')
            self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_read_only_file_metadata_categories_and_explicit_relationships_are_optional(self):
        import tempfile
        from pathlib import Path
        from orchestrator import project_meta
        server = _server_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            note = root / 'Research.md'
            note.write_text('---\ntype: paper\ntags: [read, kept]\nnexus: [ora]\nrelationships:\n  - type: supports\n    target: "[[Reference]]"\n    confidence: high\n---\nBODY MUST NOT BE SEARCHED\n')
            reference = root / 'Reference.md'
            reference.write_text('---\ntype: note\n---\nReference body\n')
            note.chmod(0o444)
            project = {"nexus": "ora", "folder_name": "Ora", "library_file_categories": [{"id": "papers", "label": "Research papers", "match": {"type": "paper", "tags": ["read", "kept"]}}], "library_category_warnings": ["Invalid category omitted"]}
            inventory = {"exists": True, "complete": True, "total": 2, "offset": 0, "next_offset": None,
                "files": [{"abs_path": str(path), "name": path.name, "rel_path": path.name} for path in (note, reference)]}
            with mock.patch.object(project_meta, "list_project_meta", return_value=[project]), \
                 mock.patch.object(project_meta, "list_project_files", return_value=inventory), \
                 mock.patch.object(server.os, "access", side_effect=lambda path, mode: mode == server.os.R_OK), \
                 mock.patch.object(server, "_browser_read_frontmatter_metadata", wraps=server._browser_read_frontmatter_metadata) as read_metadata:
                provider = server._library_file_provider()
                self.assertEqual(read_metadata.call_count, 2)
                server._library_join_provenance({"files": provider})
                payload = build_browser_response({"files": provider}, requested_sources=["files"], refinements={"category": "ora:papers", "file_type": "paper"})
                self.assertEqual(payload["total"], 1)
                row = payload["rows"][0]
                self.assertFalse(row["editability"]["editable"])
                self.assertEqual(row["metadata"]["item_type"], "file")
                self.assertEqual(row["metadata"]["file_type"], "paper")
                self.assertEqual(payload["facets"]["category"]["labels"]["ora:papers"], "Research papers")
                self.assertNotIn("BODY MUST", str(payload))
                self.assertTrue(any(summary.get("origin") == "explicit-metadata" for summary in row["relationships"]["summaries"]))
                self.assertIn("Invalid category", row["provenance"]["details"]["category_warning"])

    def test_full_universe_refinements_and_failed_relationship_filter_preserve_inventory(self):
        rows = [_row(str(index), f"File {index}", tag="kept", modified_at="2026-09-01") for index in range(52)]
        for row in rows:
            row["metadata"].update(item_type="file", file_type="paper", tags=["kept", "read"])
        rows[-1]["metadata"].update(tags=None, file_type=None)
        providers = {"files": {"rows": rows, "complete": True}}
        payload = build_browser_response(providers, requested_sources=["files"], limit=1,
            refinements={"tag": ["kept", "read"], "file_type": "paper", "date_from": "2026-09-01", "date_to": "2026-09-01"})
        self.assertEqual(payload["total"], 51)
        self.assertEqual(payload["facets"]["file_type"]["counts"], {"paper": 51})
        self.assertEqual(payload["refinements"]["file_type"]["unknown_count"], 1)
        rows[0]["relationships"]["state"] = "unavailable"
        payload = build_browser_response(providers, requested_sources=["files"], refinements={"relationship": "supports"})
        self.assertEqual(payload["total"], 52)
        self.assertFalse(payload["refinements"]["relationship"]["available"])
        for refinements in ({"date_from": "2026-02-30"}, {"privacy": "guess"}):
            with self.assertRaises(LibraryBrowserError):
                build_browser_response(providers, refinements=refinements)

    def test_provenance_preserves_multiple_proven_sources_and_inherits_only_admitted_projects(self):
        server = _server_module()
        dialogue = _row("d-1", "Public Dialogue", tag="", modified_at="2026-09-01")
        dialogue["metadata"]["project_ids"] = ["source-project"]
        file = _row("/fixture/Paper.md", "Paper", tag="", modified_at="2026-09-01")
        engram = _row("/fixture/Claim.md", "Claim", tag="", modified_at="2026-09-01")
        engram["_provenance_candidates"] = [{"source_file": "d-1", "source_document": '["[[Paper]]", "hidden-source"]', "source_turn_index": 3}]
        providers = {"dialogues": {"rows": [dialogue]}, "files": {"rows": [file]}, "engrams": {"rows": [engram], "complete": True}}
        server._library_join_provenance(providers)
        payload = build_browser_response(providers, requested_sources=["engrams"], project_id="source-project",
            refinements={"provenance_id": stable_item_id("dialogues", "d-1")})
        self.assertEqual(payload["total"], 1)
        self.assertEqual(len(payload["rows"][0]["provenance"]["sources"]), 2)
        self.assertNotIn("hidden-source", str(payload))
        self.assertIn("unresolved", payload["rows"][0]["provenance"]["reason"])

    def test_trace_49_50_51_expansion_directions_pair_edges_and_private_non_disclosure(self):
        for count in (49, 50, 51):
            with self.subTest(count=count):
                rows = []
                for index in range(count + 1):
                    row = _row(f"/fixture/N{index}.md", f"N{index}", tag="kept", modified_at="2026-09-01")
                    row["metadata"]["item_type"] = "engram"
                    row["_relationship_identity"] = f"N{index}"
                    rows.append(row)
                edges = [{"source": "N0", "target": f"N{index}", "type": ("supports", "extends", "requires", "parent", "custom")[index % 5], "confidence": ("high", ".8", "low", "nan")[index % 4]} for index in range(1, count + 1)]
                edges += [{"source": "N1", "target": "N0", "type": "contradicts", "confidence": "medium"},
                          {"source": "N1", "target": "N2", "type": "enables", "confidence": "high"},
                          {"source": "N0", "target": "SECRET", "type": "supports", "confidence": "high"}]
                calls = []
                def resolve(identities):
                    calls.append(identities)
                    return {"state": "fresh", "edges": [edge for edge in edges if edge["source"] in identities or edge["target"] in identities]}
                providers = {"engrams": {"rows": rows, "complete": True}, "files": {"rows": [dict(_row("/fixture/SECRET.md", "File", tag="", modified_at="2026-09-01"), _relationship_identity="SECRET")], "complete": True}}
                selected = stable_item_id("engrams", "/fixture/N0.md")
                payload = build_browser_response(providers, trace_id=selected, relationship_resolver=resolve, limit=1)
                trace = payload["trace"]
                self.assertEqual(trace["total_neighbors"], count)
                self.assertEqual(len(trace["rows"]), min(count, 50) + 1)
                self.assertEqual(trace["remaining"], max(0, count - 50))
                self.assertNotIn("SECRET", str(trace))
                expanded = build_browser_response(providers, trace_id=selected, trace_limit=100, relationship_resolver=resolve)["trace"]
                self.assertEqual(len(expanded["rows"]), count + 1)
                self.assertEqual(expanded["remaining"], 0)
                self.assertTrue(any(edge["type"] == "enables" for edge in expanded["edges"]))
                self.assertTrue(any(edge["family"] == "unclassified" for edge in expanded["edges"]))
                self.assertTrue(all(len(call) <= count + 1 for call in calls))

    def test_stream_is_finite_qualified_and_final_equals_json_with_failures_visible(self):
        import json
        import copy
        server = _server_module()
        with mock.patch.object(server, "_library_dialogue_provider", side_effect=lambda *a, **k: {"rows": [copy.deepcopy(_row("d1", "Dialogue", tag="kept", modified_at="2026-09-01"))], "complete": True}) as dialogues, \
             mock.patch.object(server, "_library_engram_provider", side_effect=lambda *a, **k: {"rows": [], "complete": True}) as engrams, \
             mock.patch.object(server, "_library_file_provider", side_effect=OSError("fixture unavailable")), \
             mock.patch.object(server, "_library_resolve_relationships", return_value={"state": "unavailable"}):
            client = server.app.test_client()
            response = client.get('/api/library/browser?stream=1&tag=kept', buffered=False)
            iterator = iter(response.response)
            first = json.loads(next(iterator))
            self.assertFalse(first["final"])
            self.assertEqual(first["data"]["total"], 1)
            self.assertFalse(first["data"]["universe"]["complete"])
            self.assertEqual(engrams.call_count, 0)
            frames = [first] + [json.loads(value) for value in iterator]
            self.assertTrue(frames[-1]["final"])
            self.assertEqual(dialogues.call_count, 1)
            self.assertEqual(engrams.call_count, 1)
            self.assertIn("files", frames[-1]["data"]["progress"]["failed_sources"])
            normal = client.get('/api/library/browser?tag=kept').get_json()
            self.assertEqual(frames[-1]["data"], normal)
            response.close()

    def test_indexed_archive_admission_pair_attribution_opt_in_and_read_only(self):
        import sqlite3
        server = _server_module()
        connection = sqlite3.connect(':memory:')
        connection.executescript("CREATE TABLE collections(id TEXT,name TEXT); CREATE TABLE segments(id TEXT,collection TEXT); CREATE TABLE embeddings(id INTEGER,segment_id TEXT,embedding_id TEXT); CREATE TABLE embedding_metadata(id INTEGER,key TEXT,string_value TEXT,int_value INTEGER,float_value REAL,bool_value INTEGER); INSERT INTO collections VALUES('c','conversations'); INSERT INTO segments VALUES('s','c');")
        def add(index, source, privacy, text):
            connection.execute('INSERT INTO embeddings VALUES(?,?,?)', (index, 's', str(index)))
            for key, value in {'conversation_id': source, 'turn_privacy': privacy, 'chroma:document': text, 'timestamp_utc': '2026-09-01', 'pair_num': str(index)}.items():
                connection.execute('INSERT INTO embedding_metadata(id,key,string_value) VALUES(?,?,?)', (index, key, value))
        add(1, 'historical', 'standard', '# SECRET HEADER\n\n## Exchange\n\n### User input\n\n  public question  \n\n### Assistant response\n\npublic answer')
        add(2, 'historical', 'private', '**User:**\nSECRET\n**Assistant:**\nSECRET')
        add(3, 'bad', 'standard', '**User:**\norphan')
        add(4, 'duplicate', 'standard', '**User:**\nu\n**Assistant:**\na\n**Assistant:**\nwrong')
        add(5, 'retained', 'standard', '**User:**\nretained\n**Assistant:**\na')
        with mock.patch.object(server, '_browser_physical_collection', return_value='conversations'):
            provider = server._library_archive_provider(retained_ids={'retained'}, connection=connection)
            self.assertFalse(provider['complete'])
            self.assertEqual(len(provider['rows']), 3)
            good = next(row for row in provider['rows'] if row['preview']['available'])
            self.assertEqual(good['metadata']['lifecycle'], 'indexed_archive')
            self.assertFalse(good['editability']['editable'])
            turns, incomplete = server._library_archive_turns(connection, 'historical')
            self.assertFalse(incomplete)
            self.assertEqual(turns, [{'role': 'user', 'content': '  public question  '}, {'role': 'assistant', 'content': 'public answer'}])
            self.assertNotIn('SECRET', str(provider))
            self.assertNotIn('retained', str(provider))
            self.assertIsNone(server._library_archive_pair('**User:**\nu\n**Assistant:**\na\n**User:**\nfake'))
            add(6, 'historical', None, '**User:**\nUNKNOWN\n**Assistant:**\nUNKNOWN')
            turns, incomplete = server._library_archive_turns(connection, 'historical')
            self.assertTrue(incomplete)
            self.assertNotIn('UNKNOWN', str(turns))
        connection.close()

    def test_archived_engram_opt_in_is_consistent_for_inventory_preview_and_not_edit(self):
        import json
        import sqlite3
        import tempfile
        from pathlib import Path
        from orchestrator import embedding
        server = _server_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            note = root / 'Historical.md'
            note.write_text('---\ntype: engram\ntags: [archived]\n---\nHistorical body\n')
            alias = root / 'IndexedAlias.md'
            alias.symlink_to(note)
            database = root / 'chroma.sqlite3'
            con = sqlite3.connect(database)
            con.executescript("CREATE TABLE databases(id TEXT,name TEXT,tenant_id TEXT); CREATE TABLE collections(id TEXT,name TEXT,database_id TEXT); CREATE TABLE segments(id TEXT,collection TEXT,scope TEXT,type TEXT); CREATE TABLE embeddings(id INTEGER PRIMARY KEY,segment_id TEXT,embedding_id TEXT); CREATE TABLE embedding_metadata(id INTEGER,key TEXT,string_value TEXT,int_value INTEGER,float_value REAL,bool_value INTEGER,PRIMARY KEY(id,key)); CREATE TABLE embedding_metadata_array(id INTEGER,key TEXT,string_value TEXT,int_value INTEGER,float_value REAL,bool_value INTEGER); INSERT INTO databases VALUES('d','default_database','default_tenant'); INSERT INTO collections VALUES('c','knowledge','d'); INSERT INTO segments VALUES('s','c','METADATA','urn:chroma:segment/metadata/sqlite'); INSERT INTO embeddings VALUES(1,'s','chunk');")
            con.executemany('INSERT INTO embedding_metadata(id,key,string_value) VALUES(1,?,?)', [('path', str(alias)), ('type', 'engram'), ('title', 'Historical'), ('tags', '["archived"]'), ('chroma:document', 'Historical body')])
            con.execute('CREATE VIRTUAL TABLE embedding_fulltext_search USING fts5(string_value)')
            con.execute('INSERT INTO embedding_fulltext_search(rowid,string_value) VALUES(1,?)', ('Historical body',))
            con.commit(); con.close()
            before = database.read_bytes()
            with mock.patch.object(server.rp, 'chromadb_dir', return_value=root), \
                 mock.patch.object(embedding, 'resolve_collection', return_value='knowledge'), \
                 mock.patch.object(server, '_library_dialogue_provider', return_value={'rows': [], 'complete': True}), \
                 mock.patch.object(server, '_library_file_provider', return_value={'rows': [], 'complete': True}), \
                 mock.patch.object(server, '_library_resolve_relationships', return_value={'state': 'unavailable'}):
                client = server.app.test_client()
                self.assertEqual(client.get('/api/library/browser?source=engrams').get_json()['total'], 0)
                payload = client.get('/api/library/browser?source=engrams&show_archived=1').get_json()
                self.assertEqual(payload['total'], 1)
                row = payload['rows'][0]
                self.assertEqual(row['metadata']['lifecycle'], 'archived')
                self.assertFalse(row['editability']['editable'])
                archive_frames = [json.loads(line) for line in client.get(
                    '/api/library/browser?source=dialogues&show_archived=1&stream=1').data.splitlines()]
                self.assertEqual(archive_frames[0]['data']['progress']['pending_sources'], ['dialogues'])
                self.assertEqual(archive_frames[-1]['data']['progress']['pending_sources'], [])
                with mock.patch.object(server, '_browser_chroma_exact_rows', wraps=server._browser_chroma_exact_rows) as exact, \
                     mock.patch.object(server, '_browser_chroma_fuzzy_rows', wraps=server._browser_chroma_fuzzy_rows) as fuzzy:
                    searched = client.get('/api/library/browser?source=engrams&show_archived=1&q=Historical').get_json()
                    self.assertEqual([item['id'] for item in searched['rows']], [row['id']])
                    self.assertTrue(searched['universe']['complete'])
                    exact_knowledge = [call for call in exact.call_args_list if call.kwargs['logical_collection'] == 'knowledge'][0]
                    fuzzy_knowledge = [call for call in fuzzy.call_args_list if call.kwargs['logical_collection'] == 'knowledge'][0]
                    self.assertEqual(exact_knowledge.kwargs['admitted_paths'], {str(alias)})
                    self.assertIs(exact_knowledge.kwargs['connection'], fuzzy_knowledge.kwargs['connection'])
                    with self.assertRaises(sqlite3.ProgrammingError):
                        exact_knowledge.kwargs['connection'].execute('SELECT 1')
                self.assertEqual(client.get('/api/library/preview', query_string={'id': row['id']}).status_code, 404)
                preview = client.get('/api/library/preview', query_string={'id': row['id'], 'show_archived': '1'})
                self.assertEqual(preview.status_code, 200)
                self.assertEqual(preview.get_json()['text'], 'Historical body\n')
                self.assertEqual(client.get('/api/library/edit', query_string={'id': row['id']}).status_code, 404)
            self.assertEqual(database.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
