#!/usr/bin/env python3
"""Router vision-input backstop tests (2026-06-14).

The image-reading backstop moved from a per-cell ``vision_substitute`` field to
a single GLOBAL capability slot, routing-config.json::slots.vision_input
(edited in Settings → Visual → Advanced routing). resolve_vision_fallback now
reads that slot's preferred + fallback chain.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from router import Router  # noqa: E402


def _cfg(slots):
    return {
        "endpoints": [
            {"id": "vis-a", "type": "api", "service": "claude",
             "vision_capable": True, "enabled": True, "status": "active"},
            {"id": "vis-b", "type": "api", "service": "openai",
             "vision_capable": True, "enabled": True, "status": "active"},
            {"id": "blind", "type": "api", "service": "x",
             "vision_capable": False, "enabled": True, "status": "active"},
        ],
        "slots": slots,
        "buckets": {}, "machines": {}, "pipelines": {},
    }


class TestVisionInputChain(unittest.TestCase):
    def test_chain_preferred_then_fallback(self):
        r = Router(config_dict=_cfg({"vision_input": {
            "preferred": "vis-a", "fallback": ["vis-b"]}}))
        self.assertEqual(r._vision_input_chain(), ["vis-a", "vis-b"])

    def test_empty_when_unconfigured(self):
        self.assertEqual(Router(config_dict=_cfg({}))._vision_input_chain(), [])
        self.assertEqual(
            Router(config_dict=_cfg({"vision_input": {}}))._vision_input_chain(), [])

    def test_declared_capability_resolves_but_typo_does_not(self):
        router = Router(config_dict=_cfg({"vision_input": {
            "preferred": "vis-a", "fallback": ["vis-b"],
        }}))
        self.assertEqual(
            router.resolve_capability_slot("vision_input")["id"], "vis-a")
        self.assertIsNone(router.resolve_capability_slot("vision_inpt"))


class TestResolveVisionFallback(unittest.TestCase):
    def _router(self):
        return Router(config_dict=_cfg({"vision_input": {
            "preferred": "vis-a", "fallback": ["vis-b", "blind"]}}))

    def test_returns_preferred(self):
        ep = self._router().resolve_vision_fallback("depth", 4)
        self.assertEqual(ep["id"], "vis-a")

    def test_skips_excluded_to_next_vision_capable(self):
        ep = self._router().resolve_vision_fallback("depth", 4, excluded_ids={"vis-a"})
        self.assertEqual(ep["id"], "vis-b")

    def test_skips_image_blind_fallback_entry(self):
        # vis-b excluded too → 'blind' is in the chain but not vision-capable,
        # so it must NOT be returned (the whole point of the backstop).
        ep = self._router().resolve_vision_fallback(
            "depth", 4, excluded_ids={"vis-a", "vis-b"})
        self.assertIsNone(ep)

    def test_none_when_slot_unconfigured_and_no_chain(self):
        r = Router(config_dict=_cfg({}))
        self.assertIsNone(r.resolve_vision_fallback("depth", 4))


if __name__ == "__main__":
    unittest.main(verbosity=2)
