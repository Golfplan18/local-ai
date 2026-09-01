"""Focused backend coverage for Library tag and archived-engram filters."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERVER_DIR = os.path.join(REPO_ROOT, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from server import app as server  # noqa: E402
import conversation_memory as memory  # noqa: E402


def _engram_row(identity: str, tags, *, score: float = 90.0) -> dict:
    return {
        "conversation_id": f"engram:{identity}",
        "source_conversation_id": f"/{identity}.md",
        "source_kind": "engram",
        "result_type": "engram",
        "title": identity,
        "tag": tags,
        "tags": tags,
        "score": score,
        "search_relevance": score,
        "last_activity_at": "2026-07-12T00:00:00+00:00",
    }


class TestLibraryTagHelpers(unittest.TestCase):
    def test_normalizes_native_json_comma_and_scalar_forms(self):
        expected = ["atomic", "framework/instruction"]
        self.assertEqual(
            server._browser_normalize_tags(["Atomic", "framework/instruction"]),
            expected,
        )
        self.assertEqual(
            server._browser_normalize_tags('["Atomic", "framework/instruction"]'),
            expected,
        )
        self.assertEqual(
            server._browser_normalize_tags("Atomic, framework/instruction"),
            expected,
        )
        self.assertEqual(server._browser_normalize_tags("Atomic"), ["atomic"])

    def test_metadata_boolean_extract_restores_missing_archived_tag(self):
        self.assertEqual(
            server._browser_metadata_tags({
                "tags": "atomic",
                "tag_archived": True,
                "tag_private": "false",
            }),
            ["atomic", "archived"],
        )

    def test_filter_uses_all_selected_tags_and_never_duplicates_rows(self):
        both = _engram_row("both", ["atomic", "molecular"])
        partial = _engram_row("partial", ["atomic"])
        rows = server._browser_filter_rows(
            [both, partial],
            include_conversations=True,
            include_engrams=True,
            min_relevance=0,
            has_query=True,
            required_tags=["atomic", "molecular"],
        )
        self.assertEqual([row["conversation_id"] for row in rows], ["engram:both"])
        self.assertEqual(len(rows), 1)

    def test_archived_filter_applies_only_to_engram_lane(self):
        archived_engram = _engram_row("retired", ["archived"])
        archived_dialogue = {
            "conversation_id": "archive:dialogue",
            "source_kind": "archive",
            "tags": ["archived"],
        }
        hidden = server._browser_filter_rows(
            [archived_engram, archived_dialogue],
            include_conversations=True,
            include_engrams=True,
            min_relevance=0,
            has_query=False,
        )
        self.assertEqual([row["conversation_id"] for row in hidden], ["archive:dialogue"])
        shown = server._browser_filter_rows(
            [archived_engram],
            include_conversations=True,
            include_engrams=True,
            min_relevance=0,
            has_query=False,
            show_archived=True,
        )
        self.assertEqual([row["conversation_id"] for row in shown], ["engram:retired"])

    def test_malformed_yaml_fallback_still_recognizes_archived(self):
        tags = server._browser_frontmatter_tags(
            "---\ntags:\n  - archived\nbroken: [\n---\n# Alpha\n",
            path="broken.md",
        )
        self.assertEqual(tags, ["archived"])

    def test_unterminated_frontmatter_fails_open_loudly(self):
        stderr = StringIO()
        with redirect_stderr(stderr):
            tags = server._browser_frontmatter_tags(
                "---\ntags: [archived]\n# Alpha\n",
                path="unterminated.md",
            )
        self.assertEqual(tags, [])
        self.assertIn("unterminated YAML frontmatter", stderr.getvalue())


class TestVaultMarkdownTagFiltering(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = self.tmp.name
        with open(os.path.join(self.vault, "Alpha Active.md"), "w", encoding="utf-8") as f:
            f.write("---\ntype: engram\ntags:\n  - atomic\n---\n# Alpha Active\nalpha body\n")
        with open(os.path.join(self.vault, "Alpha Archived.md"), "w", encoding="utf-8") as f:
            f.write(
                "---\ntype: engram\ntags: [atomic, archived]\n---\n"
                "# Alpha Archived\nalpha retired body\n"
            )
        archive_dir = os.path.join(self.vault, "Archive")
        os.mkdir(archive_dir)
        with open(os.path.join(archive_dir, "Alpha Physical Archive.md"), "w", encoding="utf-8") as f:
            f.write("---\ntype: engram\ntags: [atomic]\n---\n# Alpha Physical Archive\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_vault_fallback_hides_archived_by_default_and_can_show_it(self):
        hidden = server._browser_vault_markdown_rows(
            "alpha", vault_root=self.vault, limit=10
        )
        self.assertEqual([row["title"] for row in hidden], ["Alpha Active"])

        shown = server._browser_vault_markdown_rows(
            "alpha", vault_root=self.vault, limit=10, show_archived=True
        )
        self.assertEqual(
            {row["title"] for row in shown},
            {"Alpha Active", "Alpha Archived"},
        )

    def test_vault_fallback_applies_all_selected_tags(self):
        rows = server._browser_vault_markdown_rows(
            "alpha",
            vault_root=self.vault,
            limit=10,
            required_tags=["atomic", "archived"],
            show_archived=True,
        )
        self.assertEqual([row["title"] for row in rows], ["Alpha Archived"])

    def test_vault_fallback_never_surfaces_physical_archive(self):
        rows = server._browser_vault_markdown_rows(
            "alpha physical",
            vault_root=self.vault,
            limit=10,
            show_archived=True,
        )
        self.assertNotIn("Alpha Physical Archive", {row["title"] for row in rows})


class TestLibraryBrowserAPI(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()

    def _request(self, suffix: str):
        active = _engram_row(
            "active",
            ["atomic", "molecular", "framework/instruction"],
        )
        active["nexus"] = "book, ora"
        archived = _engram_row(
            "archived",
            '["atomic", "molecular", "framework/instruction", "archived"]',
            score=89.0,
        )
        archived["nexus"] = "book, ora"
        partial = _engram_row("partial", ["atomic"], score=88.0)
        with (
            patch.object(
                server, "_browser_chroma_exact_rows",
                return_value=[active, archived, partial],
            ) as exact_rows,
            patch.object(
                server, "_browser_chroma_fuzzy_rows", return_value=[],
            ) as fuzzy_rows,
            patch.object(
                server, "_browser_chroma_semantic_rows", return_value=[],
            ) as semantic_rows,
            patch.object(
                server, "_browser_vault_markdown_rows", return_value=[],
            ) as vault_rows,
        ):
            response = self.client.get("/api/conversations/browser?" + suffix)
        for search in (exact_rows, fuzzy_rows, semantic_rows, vault_rows):
            self.assertTrue(search.called)
            self.assertTrue(all(
                call.kwargs["limit"] is None
                for call in search.call_args_list
            ))
        return response

    def test_repeated_and_comma_tags_are_all_required(self):
        response = self._request(
            "q=alpha&conversations=0&tags=Atomic&tags=molecular,framework/instruction"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(
            payload["tags"],
            ["atomic", "molecular", "framework/instruction"],
        )
        self.assertFalse(payload["show_archived"])
        self.assertEqual(
            [row["conversation_id"] for row in payload["rows"]],
            ["engram:active"],
        )

    def test_show_archived_parameter_includes_archived_engram(self):
        response = self._request(
            "q=alpha&conversations=0&tags=atomic,molecular&show_archived=1"
            "&project_id=book&limit=1"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["show_archived"])
        self.assertEqual(
            [row["conversation_id"] for row in payload["rows"]],
            ["engram:active"],
        )
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["source_counts"], {"live": 0, "archive": 0, "engram": 2})
        self.assertEqual(payload["facets"]["projects"]["counts"]["book"], 2)
        self.assertEqual(payload["rows"][0]["project_ids"], ["book", "ora"])
        self.assertEqual(payload["rows"][0]["privacy"]["state"], "standard")
        self.assertEqual(payload["rows"][0]["provenance"]["kind"], "engram")
        self.assertEqual(payload["rows"][0]["lifecycle"]["state"], "knowledge")
        self.assertFalse(payload["rows"][0]["relationship"]["available"])
        self.assertFalse(payload["facets"]["local_restriction"]["available"])

    def test_server_filters_and_counts_the_complete_pre_limit_universe(self):
        live_rows = [
            {
                "conversation_id": "book-standard-private-composer",
                "source_kind": "live",
                "title": "Standard history, Private composer",
                "tag": "private",
                "contains_private": False,
                "project_ids": ["book"],
                "last_activity_at": "2026-08-20T10:00:00+00:00",
                "closed": True,
                "_relationship_available": True,
                "_relationship_kinds": ["direct-child"],
            },
            *[
                {
                    "conversation_id": f"book-private-{index}",
                    "source_kind": "live",
                    "title": f"Book {index}",
                    "tag": "private",
                    "contains_private": True,
                    "project_ids": ["book"],
                    "last_activity_at": f"2026-08-2{index}T10:00:00+00:00",
                    "closed": True,
                    "_relationship_available": True,
                    "_relationship_kinds": ["direct-child"],
                }
                for index in (0, 1)
            ],
        ]
        self.assertEqual(
            server._browser_contract_row(live_rows[0])["privacy"],
            {"state": "standard", "contains_private": False},
        )
        with (
            patch.object(server, "_browser_live_rows", return_value=live_rows),
            patch.object(
                server, "_browser_latest_archive_rows",
                side_effect=AssertionError("archive lookup ran while hidden"),
            ),
        ):
            response = self.client.get(
                "/api/conversations/browser?engrams=0&project_id=book"
                "&privacy=contains_private&lifecycle=inactive"
                "&relationship=direct-child&date_from=2026-08-20"
                "&date_to=2026-08-21&limit=1"
            )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(len(payload["rows"]), 1)
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["source_counts"], {"live": 2, "archive": 0, "engram": 0})
        self.assertEqual(payload["facets"]["privacy"]["counts"]["contains_private"], 2)
        self.assertEqual(payload["rows"][0]["relationship"]["kinds"], ["direct-child"])

    def test_commons_universe_and_unavailable_local_restriction_are_truthful(self):
        rows = [
            {"conversation_id": "commons", "source_kind": "live", "project_ids": []},
            {"conversation_id": "book", "source_kind": "live", "project_ids": ["book"]},
            {
                "conversation_id": "archive:unknown-relationship",
                "source_conversation_id": "unknown-relationship",
                "source_kind": "archive",
                "project_ids": [],
                "_archive_privacies": [],
            },
        ]
        with patch.object(server, "_browser_live_rows", return_value=rows):
            commons = self.client.get(
                "/api/conversations/browser?engrams=0&project_id=commons",
            ).get_json()
            restricted = self.client.get(
                "/api/conversations/browser?engrams=0&local_restriction=restricted",
            ).get_json()
            no_relationship = self.client.get(
                "/api/conversations/browser?engrams=0&relationship=none",
            ).get_json()
        self.assertEqual(
            [row["conversation_id"] for row in commons["rows"]],
            ["commons", "book", "archive:unknown-relationship"],
        )
        self.assertEqual(commons["facets"]["projects"]["counts"]["commons"], 3)
        self.assertEqual(
            [row["conversation_id"] for row in no_relationship["rows"]],
            ["commons", "book"],
        )
        self.assertEqual(restricted["rows"], [])
        self.assertEqual(restricted["total"], 0)
        self.assertEqual(
            restricted["facets"]["local_restriction"]["counts"],
            {"restricted": 0, "unrestricted": 0},
        )
        self.assertFalse(restricted["facets"]["local_restriction"]["available"])

    def test_empty_live_browse_uses_inventory_snapshot_without_body_cleaning(self):
        effective = [
            {"role": "user", "content": "question", "turn_privacy": "standard",
             "timestamp": "2026-08-31T10:00:00+00:00"},
            {"role": "assistant", "content": "answer", "turn_privacy": "standard",
             "timestamp": "2026-08-31T10:01:00+00:00"},
        ]
        summary = {
            "conversation_id": "snapshot",
            "project_ids": [],
            "_envelope": {"conversation_id": "snapshot", "display_name": "Snapshot"},
            "_effective_messages": effective,
        }
        with (
            patch.object(memory, "iter_conversations", return_value=[summary]),
            patch.object(
                memory, "load_conversation_json",
                side_effect=AssertionError("inventory envelope was reopened"),
            ),
            patch.object(
                memory, "resolve_effective_conversation_history",
                side_effect=AssertionError("inventory history was recomputed"),
            ),
            patch.object(
                server, "_conversation_search_snippet",
                side_effect=AssertionError("empty browse cleaned message bodies"),
            ),
        ):
            rows = server._browser_live_rows("", target_tag="")
        self.assertEqual([row["conversation_id"] for row in rows], ["snapshot"])

    def test_related_labels_only_authoritative_relationships(self):
        direct_engram = server._browser_encode_source_id(
            "engram", "/vault/Engrams/direct.md",
        )
        atomic_engram = server._browser_encode_source_id(
            "engram", "/vault/Engrams/atomic.md",
        )
        summaries = [
            {"conversation_id": "current", "parent_conversation_id": "parent",
             "project_ids": ["book"],
             "contributors": [
                 {"kind": "conversation", "ref": "contributor"},
                 {"kind": "conversation", "ref": direct_engram},
                 {"kind": "atomic_note", "path": "/vault/Engrams/atomic.md"},
             ]},
            {"conversation_id": "parent", "project_ids": []},
            {"conversation_id": "child", "parent_conversation_id": "current",
             "project_ids": []},
            {"conversation_id": "sibling", "parent_conversation_id": "parent",
             "project_ids": []},
            {"conversation_id": "contributor", "project_ids": []},
            {"conversation_id": "incoming", "project_ids": [],
             "contributors": [{"kind": "conversation", "ref": "current"}]},
            {"conversation_id": "project-peer", "project_ids": ["book"]},
        ]
        safe_rows = [
            {"conversation_id": row["conversation_id"], "source_kind": "live",
             "title": row["conversation_id"], "project_ids": row.get("project_ids", [])}
            for row in summaries
        ]
        contributor_rows = {
            direct_engram: {
                "conversation_id": direct_engram, "source_kind": "engram",
                "title": "Direct Engram", "tags": ["atomic"],
            },
            atomic_engram: {
                "conversation_id": atomic_engram, "source_kind": "engram",
                "title": "Atomic Engram", "tags": ["atomic"],
            },
        }
        with (
            patch.object(server, "_valid_existing_conversation_id", return_value=True),
            patch.object(memory, "iter_conversations", return_value=summaries),
            patch.object(server, "_browser_live_rows", return_value=safe_rows),
            patch.object(
                server, "_browser_row_for_creation_ref",
                side_effect=lambda ref, **_kwargs: contributor_rows.get(ref),
            ) as resolve_contributor,
        ):
            response = self.client.get("/api/conversation/current/related")
            engrams_only = self.client.get(
                "/api/conversation/current/related?conversations=0&engrams=1",
            )
        self.assertEqual(response.status_code, 200)
        rows = response.get_json()["rows"]
        relations = {row["conversation_id"]: row["relation"] for row in rows}
        self.assertEqual(relations["parent"], "parent")
        self.assertEqual(relations["child"], "direct-child")
        self.assertEqual(relations["sibling"], "sibling")
        self.assertEqual(relations["contributor"], "contributor")
        self.assertEqual(relations["incoming"], "direct-related")
        self.assertEqual(relations["project-peer"], "shared-project")
        self.assertEqual(relations[direct_engram], "contributor")
        self.assertEqual(relations[atomic_engram], "contributor")
        self.assertNotIn("fork", relations.values())
        self.assertEqual(engrams_only.status_code, 200)
        engram_relations = {
            row["conversation_id"]: row["relation"]
            for row in engrams_only.get_json()["rows"]
        }
        self.assertEqual(engram_relations, {
            direct_engram: "contributor",
            atomic_engram: "contributor",
        })
        self.assertEqual(
            [call.args[0] for call in resolve_contributor.call_args_list],
            [direct_engram, atomic_engram, direct_engram, atomic_engram],
        )


if __name__ == "__main__":
    unittest.main()
