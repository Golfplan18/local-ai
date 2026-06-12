#!/usr/bin/env python3
"""Install Chunk 11 — /config/routing/slots endpoint tests.

The V3 Settings → Visual tab (server/static/visual-slots-pane.js)
edits the capability-slots block of routing-config.json through a
per-slot merge endpoint, so a pane that touches only image_generates
can never clobber the other slots or strip the ``_note`` annotations.

* GET  /config/routing/slots → just the slots block.
* POST /config/routing/slots → merges each named slot's fields into
  the existing slot dict; underscore-prefixed keys in the patch are
  ignored; unknown slot names are created; non-dict payloads → 400.

Run::

    /opt/homebrew/bin/python3 -m unittest \
        orchestrator.tests.test_routing_slots_endpoint -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

FIXTURE = {
    "_schema_version": 2,
    "slots": {
        "image_generates": {
            "preferred": "openrouter:openai/gpt-5.4-image-2",
            "fallback": ["openrouter:google/gemini-3.1-flash-image-preview",
                         "local-diffusers"],
            "_note": "annotation that must survive client edits",
        },
        "video_generates": {"preferred": "replicate", "fallback": []},
    },
    "endpoints": [],
}


class RoutingSlotsEndpoint(unittest.TestCase):
    """End-to-end tests for ``/config/routing/slots``."""

    @classmethod
    def setUpClass(cls):
        # Lazy server import — drags a lot of orchestrator code in.
        sys.path.insert(0, str(Path.home() / "ora" / "server"))
        try:
            import server as S  # type: ignore
            cls.S = S
            cls.import_ok = True
        except Exception as exc:  # pragma: no cover
            cls.S = None
            cls.import_ok = False
            cls.import_err = str(exc)

    def setUp(self):
        if not self.import_ok:
            self.skipTest(
                f"could not import server.py: "
                f"{getattr(self, 'import_err', '<unknown>')}"
            )
        # Point the routing-config path at a temp fixture so the tests
        # never touch the machine's real config, and stub out the
        # router-reload hook (it imports boot's singleton — irrelevant
        # to the merge semantics under test here).
        self._tmp = tempfile.TemporaryDirectory()
        self._cfg_path = os.path.join(self._tmp.name, "routing-config.json")
        with open(self._cfg_path, "w") as f:
            json.dump(FIXTURE, f, indent=2)
        self._saved_path = self.S.ROUTING_CONFIG
        self._saved_reload = self.S._reload_pipeline_router_after_config_change
        self.S.ROUTING_CONFIG = self._cfg_path
        self.S._reload_pipeline_router_after_config_change = lambda: False
        self.client = self.S.app.test_client()

    def tearDown(self):
        if self.import_ok:
            self.S.ROUTING_CONFIG = self._saved_path
            self.S._reload_pipeline_router_after_config_change = self._saved_reload
            self._tmp.cleanup()

    def _on_disk(self):
        with open(self._cfg_path) as f:
            return json.load(f)

    def _post(self, payload):
        return self.client.post(
            "/config/routing/slots",
            data=json.dumps(payload),
            content_type="application/json",
        )

    # ── GET ──────────────────────────────────────────────────────────────

    def test_get_returns_just_the_slots_block(self):
        resp = self.client.get("/config/routing/slots")
        self.assertEqual(resp.status_code, 200, resp.data)
        payload = json.loads(resp.data)
        self.assertEqual(set(payload.keys()), {"slots"})
        self.assertEqual(
            payload["slots"]["image_generates"]["preferred"],
            "openrouter:openai/gpt-5.4-image-2",
        )

    # ── POST merge semantics ─────────────────────────────────────────────

    def test_post_merges_into_named_slot_only(self):
        resp = self._post({"slots": {"image_generates": {
            "preferred": "openrouter:openai/gpt-5-image",
            "fallback": ["local-diffusers"],
        }}})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(json.loads(resp.data)["ok"])
        cfg = self._on_disk()
        slot = cfg["slots"]["image_generates"]
        self.assertEqual(slot["preferred"], "openrouter:openai/gpt-5-image")
        self.assertEqual(slot["fallback"], ["local-diffusers"])
        # Untouched slot and non-slots keys survive intact.
        self.assertEqual(cfg["slots"]["video_generates"],
                         FIXTURE["slots"]["video_generates"])
        self.assertEqual(cfg["_schema_version"], 2)

    def test_post_preserves_note_annotations(self):
        self._post({"slots": {"image_generates": {"preferred": None}}})
        slot = self._on_disk()["slots"]["image_generates"]
        self.assertEqual(slot["_note"],
                         "annotation that must survive client edits")
        # The patched field landed; the unpatched fallback survived.
        self.assertIsNone(slot["preferred"])
        self.assertEqual(slot["fallback"],
                         FIXTURE["slots"]["image_generates"]["fallback"])

    def test_post_ignores_underscore_keys_in_patch(self):
        self._post({"slots": {"image_generates": {
            "preferred": "local-diffusers",
            "_note": "client tried to overwrite",
        }}})
        slot = self._on_disk()["slots"]["image_generates"]
        self.assertEqual(slot["preferred"], "local-diffusers")
        self.assertEqual(slot["_note"],
                         "annotation that must survive client edits")

    def test_post_creates_unknown_slot(self):
        self._post({"slots": {"image_edits": {
            "preferred": "local-diffusers", "fallback": ["replicate"],
        }}})
        slot = self._on_disk()["slots"]["image_edits"]
        self.assertEqual(slot["preferred"], "local-diffusers")
        self.assertEqual(slot["fallback"], ["replicate"])

    # ── POST validation ──────────────────────────────────────────────────

    def test_post_rejects_non_dict_slots(self):
        resp = self._post({"slots": ["image_generates"]})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(json.loads(resp.data)["ok"])
        self.assertEqual(self._on_disk()["slots"], FIXTURE["slots"])

    def test_post_rejects_missing_slots_key(self):
        resp = self._post({"preferred": "local-diffusers"})
        self.assertEqual(resp.status_code, 400)

    def test_post_rejects_non_dict_slot_patch(self):
        resp = self._post({"slots": {"image_generates": "local-diffusers"}})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self._on_disk()["slots"], FIXTURE["slots"])


if __name__ == "__main__":
    unittest.main()
