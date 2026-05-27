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


if __name__ == "__main__":
    unittest.main()
