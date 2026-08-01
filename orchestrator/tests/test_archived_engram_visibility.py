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
        archived = _engram_row(
            "archived",
            '["atomic", "molecular", "framework/instruction", "archived"]',
            score=89.0,
        )
        partial = _engram_row("partial", ["atomic"], score=88.0)
        with (
            patch.object(server, "_browser_chroma_exact_rows", return_value=[active, archived, partial]),
            patch.object(server, "_browser_chroma_fuzzy_rows", return_value=[]),
            patch.object(server, "_browser_chroma_semantic_rows", return_value=[]),
            patch.object(server, "_browser_vault_markdown_rows", return_value=[]),
        ):
            return self.client.get("/api/conversations/browser?" + suffix)

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
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["show_archived"])
        self.assertEqual(
            [row["conversation_id"] for row in payload["rows"]],
            ["engram:active", "engram:archived"],
        )


if __name__ == "__main__":
    unittest.main()
