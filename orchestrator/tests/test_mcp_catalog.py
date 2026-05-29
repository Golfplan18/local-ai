"""Tests for the MCP tool-catalog surface in ``orchestrator/boot.py``.

Covers:
  - empty catalog when no MCP client registered
  - empty catalog when get_tool_definitions returns []
  - empty catalog on get_tool_definitions exception
  - grouping by server name from the mcp_<server>_<tool> prefix
  - parameter schema rendering
  - integration with build_system_prompt_for_gear (analyst step only)

All tests are offline — they mock the MCP client manager rather than
spawning real MCP server subprocesses.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
if _ORCHESTRATOR not in sys.path:
    sys.path.insert(0, _ORCHESTRATOR)

import boot  # noqa: E402
import dispatcher  # noqa: E402


def _fake_defs():
    return [
        {
            "name": "mcp_vault-fs_read_file",
            "description": "Read a file from the vault.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string",
                             "description": "Path within vault root."},
                },
            },
        },
        {
            "name": "mcp_vault-fs_list_directory",
            "description": "List directory contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path."},
                },
            },
        },
        {
            "name": "mcp_playwright_browser_navigate",
            "description": "Navigate the browser to a URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                },
            },
        },
    ]


class _FakeMgr:
    def __init__(self, defs=None, raise_exc=None):
        self._defs = defs or []
        self._raise = raise_exc

    def get_tool_definitions(self):
        if self._raise:
            raise self._raise
        return list(self._defs)


class CatalogEmptyCasesTests(unittest.TestCase):

    def test_empty_when_no_client(self):
        with mock.patch.object(dispatcher, "_mcp_client", None):
            self.assertEqual(boot._get_mcp_tool_catalog(), "")

    def test_empty_when_no_defs(self):
        with mock.patch.object(dispatcher, "_mcp_client", _FakeMgr(defs=[])):
            self.assertEqual(boot._get_mcp_tool_catalog(), "")

    def test_empty_when_get_tool_definitions_raises(self):
        with mock.patch.object(
            dispatcher, "_mcp_client",
            _FakeMgr(raise_exc=RuntimeError("boom")),
        ):
            self.assertEqual(boot._get_mcp_tool_catalog(), "")

    def test_empty_when_client_lacks_method(self):
        class NoMethod:
            pass
        with mock.patch.object(dispatcher, "_mcp_client", NoMethod()):
            self.assertEqual(boot._get_mcp_tool_catalog(), "")


class CatalogFormatTests(unittest.TestCase):

    def test_catalog_contains_section_header(self):
        with mock.patch.object(dispatcher, "_mcp_client", _FakeMgr(_fake_defs())):
            out = boot._get_mcp_tool_catalog()
        self.assertIn("## AVAILABLE MCP TOOLS", out)

    def test_catalog_groups_by_server(self):
        with mock.patch.object(dispatcher, "_mcp_client", _FakeMgr(_fake_defs())):
            out = boot._get_mcp_tool_catalog()
        self.assertIn("### Server `vault-fs`", out)
        self.assertIn("### Server `playwright`", out)

    def test_catalog_includes_namespaced_tool_names(self):
        with mock.patch.object(dispatcher, "_mcp_client", _FakeMgr(_fake_defs())):
            out = boot._get_mcp_tool_catalog()
        self.assertIn("`mcp_vault-fs_read_file`", out)
        self.assertIn("`mcp_vault-fs_list_directory`", out)
        self.assertIn("`mcp_playwright_browser_navigate`", out)

    def test_catalog_includes_descriptions(self):
        with mock.patch.object(dispatcher, "_mcp_client", _FakeMgr(_fake_defs())):
            out = boot._get_mcp_tool_catalog()
        self.assertIn("Read a file from the vault", out)
        self.assertIn("Navigate the browser to a URL", out)

    def test_catalog_renders_parameter_schemas(self):
        with mock.patch.object(dispatcher, "_mcp_client", _FakeMgr(_fake_defs())):
            out = boot._get_mcp_tool_catalog()
        self.assertIn("`path` (string)", out)
        self.assertIn("Path within vault root", out)

    def test_servers_sorted_alphabetically(self):
        with mock.patch.object(dispatcher, "_mcp_client", _FakeMgr(_fake_defs())):
            out = boot._get_mcp_tool_catalog()
        # playwright comes after vault-fs alphabetically? No: "playwright" < "vault-fs" lex order
        playwright_idx = out.index("### Server `playwright`")
        vaultfs_idx = out.index("### Server `vault-fs`")
        self.assertLess(playwright_idx, vaultfs_idx)


class CatalogIntegrationTests(unittest.TestCase):
    """build_system_prompt_for_gear injects the catalog for analyst step."""

    def setUp(self):
        boot._reset_perspective_caches()
        # Minimal mode-text fixture
        self.context_pkg = {
            "mode_text": "## DEPTH ANALYSIS GUIDANCE\n\nDepth body.\n\n"
                         "## BREADTH ANALYSIS GUIDANCE\n\nBreadth body.\n\n"
                         "## RAG PROFILE\n\nirrelevant",
            "mode_name": "test-mode",
            "conversation_rag": "",
            "concept_rag": "",
            "relationship_rag": "",
            "web_rag": "",
        }

    def test_catalog_appears_in_breadth_analyst_prompt(self):
        with mock.patch.object(dispatcher, "_mcp_client", _FakeMgr(_fake_defs())):
            prompt = boot.build_system_prompt_for_gear(
                self.context_pkg, slot="breadth", step="analyst",
            )
        self.assertIn("## AVAILABLE MCP TOOLS", prompt)
        self.assertIn("mcp_vault-fs_read_file", prompt)

    def test_catalog_appears_in_depth_analyst_prompt(self):
        with mock.patch.object(dispatcher, "_mcp_client", _FakeMgr(_fake_defs())):
            prompt = boot.build_system_prompt_for_gear(
                self.context_pkg, slot="depth", step="analyst",
            )
        self.assertIn("## AVAILABLE MCP TOOLS", prompt)

    def test_catalog_absent_in_evaluator_prompt(self):
        with mock.patch.object(dispatcher, "_mcp_client", _FakeMgr(_fake_defs())):
            prompt = boot.build_system_prompt_for_gear(
                self.context_pkg, slot="breadth", step="evaluator",
            )
        self.assertNotIn("## AVAILABLE MCP TOOLS", prompt)

    def test_catalog_absent_in_reviser_prompt(self):
        with mock.patch.object(dispatcher, "_mcp_client", _FakeMgr(_fake_defs())):
            prompt = boot.build_system_prompt_for_gear(
                self.context_pkg, slot="breadth", step="reviser",
            )
        self.assertNotIn("## AVAILABLE MCP TOOLS", prompt)

    def test_no_catalog_section_when_no_servers(self):
        with mock.patch.object(dispatcher, "_mcp_client", None):
            prompt = boot.build_system_prompt_for_gear(
                self.context_pkg, slot="breadth", step="analyst",
            )
        self.assertNotIn("## AVAILABLE MCP TOOLS", prompt)


if __name__ == "__main__":
    unittest.main()
