#!/usr/bin/env python3
"""Provider-registry + auto-activation + prefer-direct dispatch tests.

Covers:
  1. provider_registry — integrity, derived maps, key-format validation.
  2. user_settings — registry-derived maps, enriched status rows,
     group order, AA-path auto-derivation (with a stubbed keyring).
  3. boot._resolve_direct_endpoint — the prefer-direct rewrite that maps an
     OpenRouter ``vendor/model`` id to a direct-vendor endpoint (skipped if
     boot can't be imported in the test environment).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))
sys.path.insert(0, str(ORCHESTRATOR / "tools"))

import provider_registry as registry  # noqa: E402


class TestRegistryIntegrity(unittest.TestCase):
    def test_ids_unique(self):
        ids = registry.provider_ids()
        self.assertEqual(len(ids), len(set(ids)), "duplicate provider id")

    def test_keyring_usernames_unique(self):
        names = list(registry.keyring_username_map().values())
        self.assertEqual(len(names), len(set(names)), "duplicate keyring username")

    def test_required_fields_present(self):
        required = {
            "id", "label", "category", "keyring_username", "signup_url",
            "console_url", "essential", "auto_activate",
        }
        for p in registry.PROVIDERS:
            self.assertTrue(required.issubset(p.keys()),
                            f"{p.get('id')} missing {required - set(p.keys())}")

    def test_categories_are_known(self):
        known = {c for c, _ in registry.GROUP_ORDER}
        for p in registry.PROVIDERS:
            self.assertIn(p["category"], known, f"{p['id']} unknown category")

    def test_openrouter_is_the_only_essential(self):
        essential = [p["id"] for p in registry.PROVIDERS if p.get("essential")]
        self.assertEqual(essential, ["openrouter"])

    def test_direct_providers_have_dispatch_metadata(self):
        for p in registry.direct_llm_providers():
            self.assertIn(p["dispatch"], ("native", "openai_compatible"))
            self.assertTrue(p.get("or_prefix"), f"{p['id']} missing or_prefix")
            if p["dispatch"] == "openai_compatible":
                self.assertTrue(p.get("base_url"), f"{p['id']} missing base_url")
            else:
                self.assertIn(p.get("native_service"), ("claude", "openai", "gemini"))

    def test_or_prefix_map_covers_expected_vendors(self):
        prefixes = set(registry.or_prefix_map().keys())
        for expect in ("anthropic", "openai", "google", "x-ai", "meta-llama",
                       "deepseek", "qwen", "moonshotai", "minimax", "xiaomi"):
            self.assertIn(expect, prefixes)

    def test_env_bridge_pairs_well_formed(self):
        for env, kr in registry.env_bridge_pairs():
            self.assertTrue(env and env.isupper())
            self.assertTrue(kr.endswith("-api-key"))


class TestKeyFormatValidation(unittest.TestCase):
    def test_good_prefix(self):
        ok, _ = registry.validate_key_format("anthropic", "sk-ant-abc123def456ghi")
        self.assertTrue(ok)

    def test_wrong_prefix_warns(self):
        ok, msg = registry.validate_key_format("anthropic", "tvly-abc123def456ghi")
        self.assertFalse(ok)
        self.assertIn("sk-ant-", msg)

    def test_too_short(self):
        ok, msg = registry.validate_key_format("openrouter", "sk-or-x")
        self.assertFalse(ok)
        self.assertIn("short", msg.lower())

    def test_opaque_provider_accepts_any_long_value(self):
        ok, _ = registry.validate_key_format("brave", "a" * 30)
        self.assertTrue(ok)


class _FakeKeyring:
    def __init__(self):
        self.store = {}

    def set_password(self, s, u, v):
        self.store[(s, u)] = v

    def get_password(self, s, u):
        return self.store.get((s, u))

    def delete_password(self, s, u):
        self.store.pop((s, u), None)


class TestUserSettingsIntegration(unittest.TestCase):
    def setUp(self):
        self.fake = _FakeKeyring()
        self.kp = mock.patch.dict(sys.modules, {"keyring": self.fake})
        self.kp.start()
        import user_settings
        self.us = user_settings

    def tearDown(self):
        self.kp.stop()

    def test_maps_derive_from_registry(self):
        self.assertEqual(self.us.PROVIDER_LABELS, registry.labels_map())
        self.assertEqual(self.us.PROVIDER_KEYRING_USERNAME,
                         registry.keyring_username_map())

    def test_status_rows_enriched(self):
        self.fake.set_password("ora", "openrouter-api-key", "sk-or-xyz")
        rows = self.us.list_api_key_status()
        self.assertEqual(len(rows), len(registry.PROVIDERS))
        oro = next(r for r in rows if r["provider"] == "openrouter")
        self.assertTrue(oro["present"])
        self.assertTrue(oro["essential"])
        for field in ("category", "signup_url", "console_url", "verifiable", "direct"):
            self.assertIn(field, oro)
        ds = next(r for r in rows if r["provider"] == "deepseek")
        self.assertFalse(ds["present"])
        self.assertTrue(ds["direct"])

    def test_group_order_matches_registry(self):
        self.assertEqual([g[0] for g in self.us.group_order()],
                         [g[0] for g in registry.GROUP_ORDER])

    def test_aa_path_auto(self):
        self.assertEqual(self.us.aa_path_auto(), "scrape")
        self.fake.set_password("ora", "aa-api-key", "aa-key")
        self.assertEqual(self.us.aa_path_auto(), "api")


class TestPreferDirectResolution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import boot  # noqa
            cls.boot = boot
        except Exception as e:  # pragma: no cover
            raise unittest.SkipTest(f"boot import failed: {e}")

    def setUp(self):
        self._orig_key = self.boot._provider_key
        self.boot._provider_key = lambda entry: "fake-key"  # all keys present

    def tearDown(self):
        self.boot._provider_key = self._orig_key

    def _base(self, model):
        return {"id": "x", "service": "openrouter", "model": model,
                "tier": "premium", "credential_key": "ora/openrouter-api-key"}

    def test_openai_compatible_vendor(self):
        ep = self.boot._resolve_direct_endpoint("deepseek/deepseek-chat",
                                                self._base("deepseek/deepseek-chat"))
        self.assertIsNotNone(ep)
        self.assertEqual(ep["service"], "deepseek")
        self.assertEqual(ep["model"], "deepseek-chat")
        self.assertEqual(ep["base_url"], "https://api.deepseek.com/v1")

    def test_native_vendor_strips_to_native_service(self):
        ep = self.boot._resolve_direct_endpoint("anthropic/claude-opus-4-8",
                                                self._base("anthropic/claude-opus-4-8"))
        self.assertEqual(ep["service"], "claude")
        self.assertEqual(ep["model"], "claude-opus-4-8")
        self.assertNotIn("base_url", ep)

    def test_variant_suffix_skips(self):
        self.assertIsNone(self.boot._resolve_direct_endpoint(
            "deepseek/deepseek-chat:free", self._base("deepseek/deepseek-chat:free")))

    def test_unknown_vendor_skips(self):
        self.assertIsNone(self.boot._resolve_direct_endpoint(
            "nobody/model", self._base("nobody/model")))

    def test_no_slash_skips(self):
        self.assertIsNone(self.boot._resolve_direct_endpoint(
            "justamodel", self._base("justamodel")))

    def test_absent_key_skips(self):
        self.boot._provider_key = lambda entry: ""
        self.assertIsNone(self.boot._resolve_direct_endpoint(
            "deepseek/deepseek-chat", self._base("deepseek/deepseek-chat")))

    def test_disabled_flag_skips(self):
        import os
        with mock.patch.dict(os.environ, {"ORA_PREFER_DIRECT": "0"}):
            self.assertIsNone(self.boot._resolve_direct_endpoint(
                "deepseek/deepseek-chat", self._base("deepseek/deepseek-chat")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
