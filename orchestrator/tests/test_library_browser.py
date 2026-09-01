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
        relationship_kinds = [
            "direct-child", "sibling", "parent", "contributor",
            "direct-related", "shared-project",
        ]
        with mock.patch.object(server, "_browser_live_rows", return_value=[{
            "conversation_id": "dialogue-1",
            "source_kind": "live",
            "title": "Dialogue one",
            "display_name": "Dialogue one",
            "last_activity_at": "2026-09-01T12:00:00Z",
            "project_ids": ["ora"],
            "tags": [],
            "_relationship_available": True,
            "_relationship_kinds": relationship_kinds,
        }]):
            provider = server._library_dialogue_provider()

        self.assertTrue(provider["complete"])
        row = provider["rows"][0]
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

    def test_engram_and_file_providers_take_one_complete_inventory_read(self):
        server = _server_module()
        import chromadb
        from orchestrator import conversation_memory, embedding, project_meta

        class EngramCollection:
            def __init__(self):
                self.calls = []

            def get(self, **kwargs):
                self.calls.append(kwargs)
                return {
                    "ids": ["chunk-1"],
                    "metadatas": [{
                        "type": "engram",
                        "path": "/missing/engram.md",
                        "title": "Engram",
                        "tags": ["alpha"],
                        "nexus": "ora",
                    }],
                }

        collection = EngramCollection()
        with (
            mock.patch.object(chromadb, "PersistentClient", return_value=object()),
            mock.patch.object(embedding, "get_collection", return_value=collection),
            mock.patch.object(
                conversation_memory, "knowledge_admitted_paths",
                return_value=["/missing/engram.md"],
            ),
        ):
            engrams = server._library_engram_provider()

        inventory = {
            "exists": True,
            "complete": True,
            "reason": None,
            "files": [
                {
                    "name": f"f{index}.md",
                    "rel_path": f"f{index}.md",
                    "abs_path": f"/missing/f{index}.md",
                    "size": 1,
                    "mtime": "2026-09-01T12:00:00",
                }
                for index in range(2)
            ],
            "total": 2,
            "offset": 0,
            "limit": None,
            "next_offset": None,
        }
        with (
            mock.patch.object(project_meta, "list_project_meta", return_value=[{
                "nexus": "ora", "folder_name": "Ora", "is_default": False,
            }]),
            mock.patch.object(
                project_meta, "list_project_files", return_value=inventory,
            ) as list_files,
        ):
            files = server._library_file_provider()

        self.assertTrue(engrams["complete"])
        self.assertEqual(len(engrams["rows"]), 1)
        self.assertEqual(collection.calls, [{"include": ["metadatas"]}])
        self.assertTrue(files["complete"])
        self.assertEqual(len(files["rows"]), 2)
        list_files.assert_called_once_with("Ora", max_files=None)

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
        with (
            mock.patch.object(
                server, "_library_dialogue_provider",
                return_value=fixtures["dialogues"],
            ),
            mock.patch.object(
                server, "_library_engram_provider",
                return_value=fixtures["engrams"],
            ),
            mock.patch.object(
                server, "_library_file_provider",
                return_value=fixtures["files"],
            ),
            server.app.test_client() as client,
        ):
            response = client.get(
                "/api/library/browser?source=files,dialogues&source=engrams"
                "&offset=1&limit=1"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["sources"], ["files", "dialogues", "engrams"])
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["source_counts"], {
            "files": 1, "dialogues": 1, "engrams": 1,
        })
        self.assertEqual(payload["pagination"]["returned"], 1)


if __name__ == "__main__":
    unittest.main()
