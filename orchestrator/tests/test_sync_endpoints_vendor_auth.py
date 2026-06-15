#!/usr/bin/env python3
"""PR-B: vendor-authoritative endpoint generation (flag-gated) tests."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORA = HERE.parent.parent
sys.path.insert(0, str(ORA / "orchestrator"))


def _load():
    spec = importlib.util.spec_from_file_location(
        "synceps", str(ORA / "scripts" / "sync_endpoints_from_catalog.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TestBuildDirectEndpoint(unittest.TestCase):
    def setUp(self):
        self.m = _load()

    def test_native_vendor_uses_native_service_no_id_translation(self):
        ep = self.m.build_direct_endpoint({
            "id": "anthropic/claude-opus-4-8", "native_model_id": "claude-opus-4-8",
            "vendor": "anthropic", "display_name": "Claude Opus 4.8", "context_length": 200000})
        self.assertEqual(ep["service"], "claude")
        self.assertEqual(ep["model_id"], "claude-opus-4-8")   # native id verbatim
        self.assertEqual(ep["dispatch"], "direct")
        self.assertEqual(ep["context_window"], 200000)

    def test_openai_compatible_vendor_sets_base_url(self):
        ep = self.m.build_direct_endpoint({
            "id": "xai/grok-4.3", "native_model_id": "grok-4.3", "vendor": "xai"})
        self.assertEqual(ep["service"], "xai")
        self.assertEqual(ep["base_url"], "https://api.x.ai/v1")
        self.assertEqual(ep["credential_key"], "ora/xai-api-key")
        self.assertEqual(ep["model_id"], "grok-4.3")


class TestApplyVendorAuthoritative(unittest.TestCase):
    def setUp(self):
        self.m = _load()
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"models": {
            "qwen/qwen-plus": {"id": "qwen/qwen-plus", "native_model_id": "qwen-plus",
                               "vendor": "qwen", "dispatch": "direct"},
            "qwen/qwen3-max": {"id": "qwen/qwen3-max", "native_model_id": "qwen3-max",
                               "vendor": "qwen", "dispatch": "direct"},
        }}, self.tmp)
        self.tmp.close()
        self.m.VENDOR_AUTH_PATH = Path(self.tmp.name)

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_dedup_replaces_or_with_native_keeps_referenced(self):
        OR = {"type": "api", "service": "openrouter", "dispatch": "openrouter"}
        by_id = {
            "qwen/qwen-2.5-72b-instruct": {"provider": "qwen", **OR},   # unreferenced → removed
            "qwen/qwen-plus": {"provider": "qwen", **OR},               # → replaced by native
            "qwen/qwen-legacy-pinned": {"provider": "qwen", **OR},       # referenced → kept
            "qwen/qwen-coder": {"provider": "qwen", **OR},               # only substring-of a ref → removed
            "alibaba/qwen-z": {"provider": "alibaba", **OR},             # provider is an OR prefix → qwen → removed
            "anthropic/claude-x": {"provider": "anthropic", **OR},       # other vendor → untouched
            "local-mlx-qwen3.5-9b": {"provider": "qwen", "type": "local"},  # local → never touched
        }
        routing = {"slot_assignments": {"premium": "qwen/qwen-legacy-pinned",
                                        "fast": "qwen/qwen-coder:free"}}  # :free, NOT qwen-coder
        res = self.m.apply_vendor_authoritative(by_id, routing)
        self.assertNotIn("qwen/qwen-2.5-72b-instruct", by_id)      # unreferenced OR removed
        self.assertEqual(by_id["qwen/qwen-plus"]["dispatch"], "direct")   # replaced by native
        self.assertIn("qwen/qwen3-max", by_id)                     # new native added
        self.assertIn("qwen/qwen-legacy-pinned", by_id)            # referenced → kept legacy
        self.assertNotIn("qwen/qwen-coder", by_id)                 # substring-only → NOT referenced → removed
        self.assertNotIn("alibaba/qwen-z", by_id)                  # provider OR-prefix → classified qwen → removed
        self.assertIn("anthropic/claude-x", by_id)                 # untouched
        self.assertIn("local-mlx-qwen3.5-9b", by_id)               # local never touched
        self.assertEqual(res["openrouter_removed"], 3)
        self.assertEqual(res["kept_legacy_referenced"], ["qwen/qwen-legacy-pinned"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
