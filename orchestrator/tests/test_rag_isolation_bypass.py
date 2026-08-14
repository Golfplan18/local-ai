#!/usr/bin/env python3
"""Tests for the CAMPAIGN-RAG-BYPASS-2026-05-26 flag — `rag_isolation: web_only`.

Temporary file alongside the Comparative Evaluation Campaign bypass in
`orchestrator/boot.py::run_step2_context_assembly`. Verifies that when the
active configuration carries `rag_isolation: web_only`, conversation +
concept + relationship RAG are all skipped (no calls to the RAG engine,
no calls to legacy `knowledge_search`), while the rest of step 2 (mode
loading, prompt assembly, web consultation gate) is left undisturbed.

DELETE this file when the bypass is removed from boot.py (see the removal
procedure in the marker comment block in boot.py).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
REPO_ROOT = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))

import boot  # noqa: E402


def _make_step1(mode: str = "root-cause-analysis") -> dict:
    return {
        "mode": mode,
        "raw_prompt": "why does fixing X make things worse",
        "cleaned_prompt": "why does fixing X make things worse",
        "triage_tier": 1,
    }


class RagIsolationWebOnlyFlag(unittest.TestCase):
    """Verify rag_isolation: web_only skips all three RAG channels."""

    def setUp(self):
        """Block live web consultation for every test in this class.

        `rag_isolation: web_only` routes step 2 into
        web_consultation.assemble_consultation_package, which fans out to real
        model calls with no timeout. These tests exercise flag RESOLUTION, not
        consultation, so an unmocked call here is purely an accident of the
        code path — and it deadlocked the whole suite: the module hung
        indefinitely on a future waiting for a live model response.

        Patch the name boot actually calls. This module puts `orchestrator/`
        on sys.path, so boot does `from web_consultation import ...` — binding
        a TOP-LEVEL `web_consultation` module, not `orchestrator.web_
        consultation`. Patching the dotted path silently misses: it decorates a
        different module object while boot keeps calling the real function.
        """
        patcher = patch.object(
            boot, "assemble_consultation_package", create=True,
            return_value=None,
        )
        self.mock_consultation = patcher.start()
        self.addCleanup(patcher.stop)

    @patch.object(boot, "knowledge_search", create=True)
    @patch.object(boot, "assemble_ranked_context", create=True)
    def test_web_only_flag_skips_rag_engine_calls(self, mock_rag, mock_legacy):
        """assemble_ranked_context and knowledge_search are never called."""
        mock_rag.return_value = "SHOULD-NOT-APPEAR"
        mock_legacy.return_value = "SHOULD-NOT-APPEAR"
        config = {
            "name": "test-config-isolated",
            "rag_isolation": "web_only",
            "cells": {},
        }
        result = boot.run_step2_context_assembly(_make_step1(), config)
        self.assertFalse(
            mock_rag.called,
            f"assemble_ranked_context called {mock_rag.call_count} times "
            f"under rag_isolation: web_only",
        )
        self.assertFalse(
            mock_legacy.called,
            f"knowledge_search called {mock_legacy.call_count} times "
            f"under rag_isolation: web_only",
        )
        self.assertEqual(result["conversation_rag"], "")
        self.assertEqual(result["concept_rag"], "")
        self.assertEqual(result["relationship_rag"], "")

    @patch.object(boot, "knowledge_search", create=True)
    @patch.object(boot, "assemble_ranked_context", create=True)
    def test_web_only_flag_absent_does_not_skip(self, mock_rag, mock_legacy):
        """Without the flag, the normal RAG path runs (control)."""
        mock_rag.return_value = "[normal conversation rag content]"
        mock_legacy.return_value = "[legacy knowledge content]"
        config = {"name": "test-config-default", "cells": {}}
        boot.run_step2_context_assembly(_make_step1(), config)
        # Under default config one of the two paths should fire for
        # conversation RAG (RAG_ENGINE_AVAILABLE OR TOOLS_AVAILABLE).
        # If neither module is available the test is a no-op — but in
        # the development environment one of them should be present.
        if boot.RAG_ENGINE_AVAILABLE or boot.TOOLS_AVAILABLE:
            self.assertTrue(
                mock_rag.called or mock_legacy.called,
                "Expected RAG engine OR legacy knowledge_search to be "
                "called when rag_isolation flag is absent",
            )

    @patch.object(boot, "knowledge_search", create=True)
    @patch.object(boot, "assemble_ranked_context", create=True)
    def test_web_only_flag_other_value_does_not_skip(self, mock_rag, mock_legacy):
        """Flag set to anything other than 'web_only' does not skip RAG."""
        mock_rag.return_value = "[content]"
        mock_legacy.return_value = "[content]"
        config = {
            "name": "test-config-other",
            "rag_isolation": "some_future_mode",
            "cells": {},
        }
        boot.run_step2_context_assembly(_make_step1(), config)
        if boot.RAG_ENGINE_AVAILABLE or boot.TOOLS_AVAILABLE:
            self.assertTrue(
                mock_rag.called or mock_legacy.called,
                "Only the exact string 'web_only' should trigger the "
                "campaign bypass.",
            )

    @patch.object(boot, "knowledge_search", create=True)
    @patch.object(boot, "assemble_ranked_context", create=True)
    @patch.object(boot, "_load_profile_config")
    def test_per_profile_config_resolves_flag(
        self, mock_load_profile, mock_rag, mock_legacy
    ):
        """Production path: the flag lives in the per-profile JSON
        (config/configurations/<name>.json), NOT in routing-config.json.

        When ``config_name`` is provided, ``run_step2_context_assembly``
        must load the per-profile file and consult its ``rag_isolation``
        field. The ``config`` dict (routing-config) does not carry the
        flag in production.
        """
        mock_rag.return_value = "SHOULD-NOT-APPEAR"
        mock_legacy.return_value = "SHOULD-NOT-APPEAR"
        mock_load_profile.return_value = {
            "name": "qwen-9b-only",
            "rag_isolation": "web_only",
        }
        # ``config`` here mimics routing-config.json — no rag_isolation field.
        routing_config = {"endpoints": [], "cells": {}}
        result = boot.run_step2_context_assembly(
            _make_step1(), routing_config, config_name="qwen-9b-only",
        )
        mock_load_profile.assert_called_once_with("qwen-9b-only")
        self.assertFalse(
            mock_rag.called,
            "assemble_ranked_context should be skipped when per-profile "
            "config carries rag_isolation: web_only, even when the "
            "routing-config does not.",
        )
        self.assertFalse(
            mock_legacy.called,
            "knowledge_search should be skipped under per-profile "
            "rag_isolation: web_only.",
        )
        self.assertEqual(result["conversation_rag"], "")
        self.assertEqual(result["concept_rag"], "")
        self.assertEqual(result["relationship_rag"], "")


class RagIsolationDispatcherToolGate(unittest.TestCase):
    """Verify the knowledge_search tool wrapper refuses when the
    per-turn rag_isolation flag is web_only.

    The tool wrapper hits ChromaDB's knowledge (vault) and conversations
    collections. Models can invoke this tool via <tool_call> markup, so
    a campaign run with rag_isolation: web_only must reject any such
    call — otherwise the agentic loop leaks vault content into outputs
    that should be reproducible from a clean install.
    """

    def test_knowledge_search_refused_under_web_only(self):
        import dispatcher
        # Set the per-turn flag (matches what boot.py does at step 2).
        dispatcher.set_rag_isolation("web_only")
        try:
            result = dispatcher._wrap_knowledge_search(
                {"query": "anything", "collection": "knowledge"}
            )
        finally:
            dispatcher.set_rag_isolation(None)
        self.assertIn("refused", result.lower())
        self.assertIn("rag_isolation", result.lower())
        self.assertIn("web_search", result.lower())

    def test_knowledge_search_allowed_when_flag_absent(self):
        import dispatcher
        # Default state — no flag set.
        dispatcher.set_rag_isolation(None)
        # We patch the underlying knowledge_search so the test doesn't
        # depend on a populated ChromaDB index. The point is to verify
        # the wrapper passes through when the flag is not "web_only".
        with patch.object(
            dispatcher, "knowledge_search", return_value="[mock-result]",
        ):
            result = dispatcher._wrap_knowledge_search(
                {"query": "anything", "collection": "knowledge"}
            )
        self.assertEqual(result, "[mock-result]")

    def test_knowledge_search_allowed_when_flag_is_other_value(self):
        import dispatcher
        dispatcher.set_rag_isolation("some_future_mode")
        try:
            with patch.object(
                dispatcher, "knowledge_search", return_value="[mock-result]",
            ):
                result = dispatcher._wrap_knowledge_search(
                    {"query": "anything", "collection": "knowledge"}
                )
        finally:
            dispatcher.set_rag_isolation(None)
        self.assertEqual(result, "[mock-result]")


if __name__ == "__main__":
    unittest.main()
