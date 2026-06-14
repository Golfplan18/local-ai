#!/usr/bin/env python3
"""Catalogue resolver tests — OpenRouter id → native vendor id mapping.

Network is fully stubbed: _load_catalog / _fetch_ids are monkeypatched so the
matching logic is exercised against fixed catalogues per vendor. The emphasis
is on the safety invariant: never resolve to a DIFFERENT model.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

import direct_catalog as dc  # noqa: E402


def _entry(pid, base_url=None):
    return {"id": pid, "base_url": base_url, "keyring_username": pid + "-api-key",
            "env_var": pid.upper() + "_API_KEY"}


class TestMatching(unittest.TestCase):
    def setUp(self):
        dc.reset_caches()
        os.environ.pop("ORA_DIRECT_CATALOG", None)

    def _resolve(self, pid, catalog, or_id):
        with mock.patch.object(dc, "_load_catalog", return_value=set(catalog)):
            return dc.resolve(_entry(pid), or_id, "k")

    # ── legitimate, identity-preserving matches ──────────────────────────
    def test_exact_match(self):
        self.assertEqual(self._resolve("openai", ["gpt-5.5", "gpt-5"], "gpt-5.5"),
                         ("direct", "gpt-5.5"))

    def test_anthropic_dotted_to_hyphen(self):
        self.assertEqual(
            self._resolve("anthropic", ["claude-opus-4-8", "claude-sonnet-4-6"], "claude-opus-4.8"),
            ("direct", "claude-opus-4-8"))

    def test_unpinned_uses_latest_alias(self):
        self.assertEqual(
            self._resolve("mistral", ["mistral-large-latest", "mistral-small-latest"], "mistral-large"),
            ("direct", "mistral-large-latest"))

    def test_minimax_case_fold(self):
        self.assertEqual(self._resolve("minimax", ["MiniMax-M2", "MiniMax-M3"], "minimax-m2"),
                         ("direct", "MiniMax-M2"))

    def test_structural_namespace_strip(self):
        # NVIDIA NIM namespaces ids; reduce drops the leading "nvidia/".
        self.assertEqual(
            self._resolve("nvidia", ["nvidia/llama-3.3-nemotron-super-49b-v1.5"], "llama-3.3-nemotron-super-49b-v1.5"),
            ("direct", "nvidia/llama-3.3-nemotron-super-49b-v1.5"))

    def test_structural_dated_snapshot_unpinned(self):
        # Unpinned request matches the vendor's single dated snapshot of it.
        self.assertEqual(
            self._resolve("xai", ["grok-4-multi-agent-0309"], "grok-4-multi-agent"),
            ("direct", "grok-4-multi-agent-0309"))

    def test_exact_pinned_snapshot(self):
        # A pinned id that the vendor lists exactly resolves to itself.
        self.assertEqual(
            self._resolve("moonshot", ["kimi-k2", "kimi-k2-0711-preview"], "kimi-k2-0711-preview"),
            ("direct", "kimi-k2-0711-preview"))

    # ── safety: never resolve to a DIFFERENT model ───────────────────────
    def test_wrong_model_continuation_token_skips(self):
        # grok-3 must NOT become grok-3-mini (a different, cheaper model).
        self.assertEqual(self._resolve("xai", ["grok-3-mini"], "grok-3"), ("skip", None))

    def test_wrong_model_chat_latest_skips(self):
        # gpt-5 must NOT become gpt-5-chat-latest (chat-tuned, non-reasoning).
        self.assertEqual(self._resolve("openai", ["gpt-5-chat-latest", "o3"], "gpt-5"), ("skip", None))

    def test_wrong_model_search_preview_skips(self):
        self.assertEqual(
            self._resolve("openai", ["gpt-4o-mini-search-preview", "o3"], "gpt-4"), ("skip", None))

    def test_pinned_not_repinned_to_other_snapshot(self):
        # mistral-large-2407 must NOT resolve to -latest or a different -2411 snapshot.
        self.assertEqual(
            self._resolve("mistral", ["mistral-large-latest", "mistral-large-2411"], "mistral-large-2407"),
            ("skip", None))

    def test_descriptive_suffix_skips(self):
        # Meta-style descriptive ids are not a safe structural match → skip.
        self.assertEqual(
            self._resolve("meta", ["Llama-4-Maverick-17B-128E-Instruct-FP8"], "llama-4-maverick"),
            ("skip", None))

    def test_not_listed_skips(self):
        self.assertEqual(self._resolve("mistral", ["mistral-large-latest"], "ministral-3b"),
                         ("skip", None))

    def test_ambiguous_skips(self):
        self.assertEqual(self._resolve("openai", ["gpt-4o", "gpt-4-turbo", "gpt-4.1"], "gpt-4"),
                         ("skip", None))

    # ── degrade / config ─────────────────────────────────────────────────
    def test_unreachable_catalogue_is_unknown(self):
        with mock.patch.object(dc, "_load_catalog", return_value=None):
            self.assertEqual(dc.resolve(_entry("xai", "https://api.x.ai/v1"), "grok-4", "k"),
                             ("unknown", "grok-4"))

    def test_disabled_is_unknown(self):
        with mock.patch.dict(os.environ, {"ORA_DIRECT_CATALOG": "0"}):
            self.assertEqual(dc.resolve(_entry("xai"), "grok-4", "k"), ("unknown", "grok-4"))

    def test_resolution_is_cached(self):
        calls = {"n": 0}

        def _fake(entry, key):
            calls["n"] += 1
            return {"grok-4"}

        with mock.patch.object(dc, "_load_catalog", side_effect=_fake):
            dc.resolve(_entry("xai"), "grok-4", "k")
            dc.resolve(_entry("xai"), "grok-4", "k")
        self.assertEqual(calls["n"], 1)


class TestSingleFlight(unittest.TestCase):
    def setUp(self):
        dc.reset_caches()

    def test_concurrent_same_vendor_fetches_once(self):
        calls = {"n": 0}

        def _slow(entry, key):
            calls["n"] += 1
            time.sleep(0.2)
            return {"grok-4"}

        with mock.patch.object(dc, "_fetch_ids", side_effect=_slow), \
                mock.patch.object(dc, "_read_disk", return_value=None), \
                mock.patch.object(dc, "_write_disk", return_value=None):
            threads = [threading.Thread(target=dc._load_catalog, args=(_entry("xai"), "k"))
                       for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(calls["n"], 1)  # single-flight: only one real fetch


class TestParsing(unittest.TestCase):
    def test_openai_shape(self):
        self.assertEqual(dc._parse_ids({"data": [{"id": "gpt-5.5"}, {"id": "gpt-4o"}]}),
                         {"gpt-5.5", "gpt-4o"})

    def test_gemini_models_prefix_stripped(self):
        self.assertEqual(dc._parse_ids({"data": [{"id": "models/gemini-2.5-flash"}]}),
                         {"gemini-2.5-flash"})

    def test_bare_list(self):
        self.assertEqual(dc._parse_ids(["a", "b"]), {"a", "b"})


class TestDateStrip(unittest.TestCase):
    def test_strips_dates_not_sizes(self):
        self.assertEqual(dc._base_id("deepseek-chat-v3-0324"), "deepseek-chat")
        self.assertEqual(dc._base_id("mistral-large-2411"), "mistral-large")
        self.assertEqual(dc._base_id("kimi-k2-0711-preview"), "kimi-k2")
        self.assertEqual(dc._base_id("gpt-4o-2024-08-06"), "gpt-4o")
        # must NOT strip size/version that look numeric-ish
        self.assertEqual(dc._base_id("qwen3-14b"), "qwen3-14b")
        self.assertEqual(dc._base_id("claude-opus-4-8"), "claude-opus-4-8")


if __name__ == "__main__":
    unittest.main(verbosity=2)
