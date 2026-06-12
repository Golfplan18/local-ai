#!/usr/bin/env python3
"""Model-picker iteration 1 (2026-06-11) — unit tests.

Covers the three offline-testable fixes:

1. Vendor-audit name reconciliation (scripts/sync_model_registry.py):
   - Anthropic dot→hyphen normalization (OpenRouter ``claude-opus-4.5``
     vs Anthropic's own ``claude-opus-4-5``) — previously every dotted
     Claude id was falsely flagged NOT IN VENDOR LIST.
   - Google prefix mapping — ``_bare_id_for_vendor`` did an inverted
     lookup (vendor name into a prefix-keyed map), so ``google/...`` ids
     were silently never audited.

2. Strict reachability gate (scripts/auto-populate-configuration.py::
   registry_crossref): only probe-verified models (reachable=True) are
   pick-eligible; fresh-install fallback when no positive verdicts exist.

3. Media gating: the sync's ``--include-media`` flag defaults off, so AA
   media-leaderboard entries (aa-img:/aa-edit:/aa-vid:) stay out of the
   registry until image-generation routing is implemented.
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent


def _load_script(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        module_name, REPO_ROOT / "scripts" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sync_registry = _load_script("_t_sync_model_registry", "sync_model_registry.py")
auto_populate = _load_script("_t_auto_populate", "auto-populate-configuration.py")
endpoint_sync = _load_script("_t_sync_endpoints", "sync_endpoints_from_catalog.py")


class TestBareIdForVendor(unittest.TestCase):
    def test_google_prefix_maps_to_gemini_vendor(self):
        # The original bug: google/ ids returned None for vendor=gemini,
        # so no Google model was ever audited.
        self.assertEqual(
            sync_registry._bare_id_for_vendor("google/gemini-3.1-pro-preview", "gemini"),
            "gemini-3.1-pro-preview",
        )

    def test_anthropic_dots_normalize_to_hyphens(self):
        self.assertEqual(
            sync_registry._bare_id_for_vendor("anthropic/claude-opus-4.5", "anthropic"),
            "claude-opus-4-5",
        )

    def test_anthropic_undotted_id_passes_through(self):
        self.assertEqual(
            sync_registry._bare_id_for_vendor("anthropic/claude-3-haiku", "anthropic"),
            "claude-3-haiku",
        )

    def test_openai_ids_keep_dots(self):
        self.assertEqual(
            sync_registry._bare_id_for_vendor("openai/gpt-4.1", "openai"),
            "gpt-4.1",
        )

    def test_free_suffix_stripped(self):
        self.assertEqual(
            sync_registry._bare_id_for_vendor("openai/gpt-5.4-mini:free", "openai"),
            "gpt-5.4-mini",
        )

    def test_tilde_mirror_prefix_stripped(self):
        self.assertEqual(
            sync_registry._bare_id_for_vendor("~anthropic/claude-opus-4.5", "anthropic"),
            "claude-opus-4-5",
        )

    def test_wrong_vendor_returns_none(self):
        self.assertIsNone(
            sync_registry._bare_id_for_vendor("qwen/qwen3.6-plus", "openai"))
        self.assertIsNone(
            sync_registry._bare_id_for_vendor("openai/gpt-4.1", "gemini"))

    def test_no_slash_returns_none(self):
        self.assertIsNone(sync_registry._bare_id_for_vendor("gpt-4.1", "openai"))


class TestVendorAuditOne(unittest.TestCase):
    VENDOR_LISTS = {
        "anthropic": {"claude-opus-4-5", "claude-opus-4-5-20251101", "claude-3-haiku-20240307"},
        "openai": {"gpt-4.1", "gpt-5.5"},
        "gemini": {"gemini-3.1-pro-preview", "gemini-2.5-flash"},
    }

    def test_dotted_anthropic_id_now_confirms(self):
        rec = sync_registry._vendor_audit_one(
            "anthropic/claude-opus-4.5", self.VENDOR_LISTS)
        self.assertTrue(rec["vendor_listed"])
        self.assertEqual(rec["bare_id"], "claude-opus-4-5")

    def test_dated_variant_prefix_match_still_works(self):
        rec = sync_registry._vendor_audit_one(
            "anthropic/claude-3-haiku", self.VENDOR_LISTS)
        self.assertTrue(rec["vendor_listed"])

    def test_openrouter_only_variant_still_flags(self):
        # -fast variants are OpenRouter aliases Anthropic doesn't list —
        # the chip's intended catch, which must survive the normalization.
        rec = sync_registry._vendor_audit_one(
            "anthropic/claude-opus-4.5-fast", self.VENDOR_LISTS)
        self.assertFalse(rec["vendor_listed"])

    def test_google_models_are_audited(self):
        rec = sync_registry._vendor_audit_one(
            "google/gemini-3.1-pro-preview", self.VENDOR_LISTS)
        self.assertIsNotNone(rec)
        self.assertTrue(rec["vendor_listed"])

    def test_google_phantom_flags(self):
        rec = sync_registry._vendor_audit_one(
            "google/gemini-9.9-imaginary", self.VENDOR_LISTS)
        self.assertFalse(rec["vendor_listed"])

    def test_unaudited_vendor_returns_none(self):
        self.assertIsNone(
            sync_registry._vendor_audit_one("qwen/qwen3.6-plus", self.VENDOR_LISTS))

    def test_missing_vendor_list_is_inconclusive(self):
        rec = sync_registry._vendor_audit_one(
            "openai/gpt-4.1", {"anthropic": {"claude-opus-4-5"}})
        self.assertIsNone(rec["vendor_listed"])
        self.assertEqual(rec["reason"], "no_vendor_key_or_list")


class TestRegistryCrossref(unittest.TestCase):
    def _write_registry(self, models: dict) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False)
        json.dump({"models": models}, tmp)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return Path(tmp.name)

    def test_strict_gate_excludes_unverified(self):
        path = self._write_registry({
            "a/verified": {"reachable": True},
            "a/rate-limited": {"reachable": True, "reachable_rate_limited": True},
            "a/dead": {"reachable": False},
            "a/unprobed": {"reachable": None},
            "a/never-probed": {},
        })
        xref = auto_populate.registry_crossref(path)
        self.assertEqual(
            xref["unreachable_ids"],
            {"a/dead", "a/unprobed", "a/never-probed"},
        )
        self.assertEqual(len(xref["registry_ids"]), 5)

    def test_fresh_install_fallback_without_positive_verdicts(self):
        # Probe never ran: strict gate would exclude everything and bake
        # empty presets — fall back to confirmed-unreachable only.
        path = self._write_registry({
            "a/unprobed": {"reachable": None},
            "a/never-probed": {},
            "a/dead": {"reachable": False},
        })
        xref = auto_populate.registry_crossref(path)
        self.assertEqual(xref["unreachable_ids"], {"a/dead"})

    def test_media_categories_exempt_from_gate(self):
        path = self._write_registry({
            "a/verified": {"reachable": True},
            "aa-img:123": {"category": "image_generation"},
        })
        xref = auto_populate.registry_crossref(path)
        self.assertEqual(xref["unreachable_ids"], set())

    def test_missing_registry_returns_empty_sets(self):
        xref = auto_populate.registry_crossref(Path("/nonexistent/registry.json"))
        self.assertEqual(xref["registry_ids"], set())
        self.assertEqual(xref["unreachable_ids"], set())

    def test_tps_and_reasoning_passthrough(self):
        path = self._write_registry({
            "a/fast": {"reachable": True, "output_tokens_per_second": 120.5},
            "a/thinker": {"reachable": True, "reasoning_model": True},
        })
        xref = auto_populate.registry_crossref(path)
        self.assertEqual(xref["tokens_per_sec"], {"a/fast": 120.5})
        self.assertEqual(xref["reasoning_model_ids"], {"a/thinker"})


class TestMediaGatingDefault(unittest.TestCase):
    def test_sync_parser_defaults_media_off(self):
        # The REAL parser: a default `sync` invocation must keep AA media
        # entries out of the registry until image-gen routing exists.
        args = sync_registry.build_parser().parse_args(["sync", "--no-probe"])
        self.assertFalse(args.include_media)

    def test_sync_parser_accepts_include_media(self):
        args = sync_registry.build_parser().parse_args(["sync", "--include-media"])
        self.assertTrue(args.include_media)

    def test_build_media_entries_empty_rows(self):
        self.assertEqual(
            sync_registry.build_media_entries([], [], [], fetched_at="now"), {})


class TestEndpointDirectGate(unittest.TestCase):
    """build_endpoint must not mark vendor-phantom ids (vendor_listed=False
    — OpenRouter-only variants like -fast / -customtools) as dispatch=direct:
    the vendor's API would 404 on every call before falling back."""

    def setUp(self):
        # Bypass the real keychain: pretend all three vendor keys exist.
        self._saved = dict(endpoint_sync._KEY_CACHE)
        for spec in endpoint_sync.DIRECT_SERVICES.values():
            endpoint_sync._KEY_CACHE[spec["keyring_name"]] = True

    def tearDown(self):
        endpoint_sync._KEY_CACHE.clear()
        endpoint_sync._KEY_CACHE.update(self._saved)

    @staticmethod
    def _model(cid, provider):
        return {"id": cid, "provider": provider, "display_name": cid,
                "output_modalities": ["text"]}

    def test_vendor_listed_true_dispatches_direct(self):
        ep = endpoint_sync.build_endpoint(
            self._model("anthropic/claude-opus-4.8", "anthropic"),
            {"anthropic/claude-opus-4.8": True})
        self.assertEqual(ep["dispatch"], "direct")
        self.assertEqual(ep["model_id"], "claude-opus-4-8")

    def test_vendor_phantom_routes_openrouter(self):
        ep = endpoint_sync.build_endpoint(
            self._model("anthropic/claude-opus-4.8-fast", "anthropic"),
            {"anthropic/claude-opus-4.8-fast": False})
        self.assertEqual(ep["dispatch"], "openrouter")
        self.assertEqual(ep["model_id"], "anthropic/claude-opus-4.8-fast")

    def test_unaudited_still_direct(self):
        ep = endpoint_sync.build_endpoint(
            self._model("openai/gpt-5.5", "openai"), {})
        self.assertEqual(ep["dispatch"], "direct")

    def test_no_key_routes_openrouter(self):
        endpoint_sync._KEY_CACHE["openai-api-key"] = False
        ep = endpoint_sync.build_endpoint(
            self._model("openai/gpt-5.5", "openai"),
            {"openai/gpt-5.5": True})
        self.assertEqual(ep["dispatch"], "openrouter")


if __name__ == "__main__":
    unittest.main()
