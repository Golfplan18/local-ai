#!/usr/bin/env python3
"""WP-7.3.2c — Replicate aggregator integration tests.

The §13.3 WP-7.3.2 test criterion specifies "Live call to each integrated
endpoint with a benign payload" as the deliverable verification — that
belongs in WP-7.3.5's manual integration smoke test, not the unit suite
(it incurs a per-run charge to the user's Replicate account).

These tests therefore mock ``requests`` at the module-import boundary
and exercise:

* sync run + poll loop reaches a terminal state correctly,
* per-slot dispatchers translate the validated input dict into the
  expected Replicate payload shape,
* error mapping (401/429/422) maps to the slot-taxonomy ``code``,
* async dispatch files a job + spawns a polling thread that transitions
  the queue when the prediction completes,
* registration walks every supported slot and registers without raising
  even when no API key is present (graceful-degradation contract).

A ``--live`` opt-in flag (``ORA_REPLICATE_LIVE=1`` env) gates a single
benign captioning call against the live API. It is ``skipUnless`` by
default and never runs in CI.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
WORKSPACE = ORCHESTRATOR.parent
sys.path.insert(0, str(WORKSPACE))
sys.path.insert(0, str(ORCHESTRATOR))

from orchestrator.integrations import replicate as rep_mod  # noqa: E402
from orchestrator.capability_registry import (  # noqa: E402
    CapabilityRegistry,
    load_registry,
)
from orchestrator.job_queue import JobQueue  # noqa: E402


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _FakeRequests:
    """Stand-in for the ``requests`` module — records calls."""

    def __init__(self):
        self.posts: list[tuple[str, dict, dict]] = []
        self.gets: list[tuple[str, dict]] = []
        # Static or callable per-URL responses.
        self.post_responses: dict[str, list[_FakeResponse]] = {}
        self.get_responses: dict[str, list[_FakeResponse]] = {}

    def queue_post(self, url_substr: str, *responses: _FakeResponse) -> None:
        self.post_responses.setdefault(url_substr, []).extend(responses)

    def queue_get(self, url_substr: str, *responses: _FakeResponse) -> None:
        self.get_responses.setdefault(url_substr, []).extend(responses)

    def post(self, url, headers=None, json=None, timeout=None):
        self.posts.append((url, headers or {}, json or {}))
        return self._dequeue(self.post_responses, url)

    def get(self, url, headers=None, timeout=None):
        self.gets.append((url, headers or {}))
        return self._dequeue(self.get_responses, url)

    @staticmethod
    def _dequeue(table, url):
        for substr, responses in table.items():
            if substr in url:
                if responses:
                    return responses.pop(0)
        return _FakeResponse(500, {"error": f"no fake response for {url}"})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _registry_for_capabilities() -> CapabilityRegistry:
    return load_registry()


# ---------------------------------------------------------------------------
# Auth + module-load tests
# ---------------------------------------------------------------------------

class AuthAndKeyResolutionTests(unittest.TestCase):
    def test_env_override_beats_keychain(self):
        with mock.patch.dict(os.environ, {"REPLICATE_API_TOKEN": "env-key"}):
            self.assertEqual(rep_mod._resolve_api_key(), "env-key")

    def test_no_key_returns_none(self):
        with mock.patch.dict(os.environ, {"REPLICATE_API_TOKEN": ""}, clear=False):
            with mock.patch.object(rep_mod, "_HAS_KEYRING", False):
                self.assertIsNone(rep_mod._resolve_api_key())


# ---------------------------------------------------------------------------
# HTTP error mapping
# ---------------------------------------------------------------------------

class HttpErrorMappingTests(unittest.TestCase):
    def setUp(self):
        self.fake = _FakeRequests()
        self.client = rep_mod.ReplicateClient(api_key="t-tok", session=self.fake)

    def test_401_maps_to_model_unavailable(self):
        self.fake.queue_post("/predictions",
                             _FakeResponse(401, {"detail": "no auth"}))
        with self.assertRaises(rep_mod.ReplicateError) as cm:
            self.client.create("ver-x", {"prompt": "hi"})
        self.assertEqual(cm.exception.code, "model_unavailable")

    def test_429_maps_to_quota_exceeded(self):
        self.fake.queue_post("/predictions",
                             _FakeResponse(429, {"detail": "rate"}))
        with self.assertRaises(rep_mod.ReplicateError) as cm:
            self.client.create("ver-x", {"prompt": "hi"})
        self.assertEqual(cm.exception.code, "quota_exceeded")

    def test_422_nsfw_maps_to_prompt_rejected(self):
        self.fake.queue_post("/predictions",
                             _FakeResponse(422, {"detail": "NSFW content blocked"}))
        with self.assertRaises(rep_mod.ReplicateError) as cm:
            self.client.create("ver-x", {"prompt": "hi"})
        self.assertEqual(cm.exception.code, "prompt_rejected")


# ---------------------------------------------------------------------------
# Sync run() polling loop
# ---------------------------------------------------------------------------

class SyncRunTests(unittest.TestCase):
    def test_run_polls_until_succeeded(self):
        fake = _FakeRequests()
        fake.queue_get(
            "/models/stability-ai/sdxl",
            _FakeResponse(200, {"latest_version": {"id": "v-sha"}}),
        )
        fake.queue_post(
            "/predictions",
            _FakeResponse(201, {"id": "p1", "status": "starting", "output": None}),
        )
        fake.queue_get(
            "/predictions/p1",
            _FakeResponse(200, {"id": "p1", "status": "processing", "output": None}),
            _FakeResponse(200, {"id": "p1", "status": "succeeded",
                                "output": ["https://example/result.png"]}),
        )
        client = rep_mod.ReplicateClient(api_key="t-tok", session=fake)
        result = client.run("stability-ai/sdxl", {"prompt": "a cat"},
                            poll_interval=0.0, timeout=5.0)
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["output"][0], "https://example/result.png")

    def test_run_failed_raises(self):
        fake = _FakeRequests()
        fake.queue_get(
            "/models/foo/bar",
            _FakeResponse(200, {"latest_version": {"id": "v-sha"}}),
        )
        fake.queue_post(
            "/predictions",
            _FakeResponse(201, {"id": "p1", "status": "starting"}),
        )
        fake.queue_get(
            "/predictions/p1",
            _FakeResponse(200, {"id": "p1", "status": "failed", "error": "boom"}),
        )
        client = rep_mod.ReplicateClient(api_key="t-tok", session=fake)
        with self.assertRaises(rep_mod.ReplicateError) as cm:
            client.run("foo/bar", {}, poll_interval=0.0, timeout=2.0)
        self.assertEqual(cm.exception.code, "handler_failed")


# ---------------------------------------------------------------------------
# Per-slot dispatchers
# ---------------------------------------------------------------------------

class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.fake = _FakeRequests()
        # Inject the fake into every ReplicateClient created during the test.
        self._patcher_session = mock.patch.object(
            rep_mod.ReplicateClient, "__init__",
            autospec=True,
            side_effect=self._init_with_fake,
        )
        self._patcher_session.start()
        # Also patch _resolve_api_key so the key path always succeeds.
        self._patcher_key = mock.patch.object(
            rep_mod, "_resolve_api_key", return_value="t-tok"
        )
        self._patcher_key.start()

    def tearDown(self):
        self._patcher_session.stop()
        self._patcher_key.stop()

    def _init_with_fake(self, instance, api_key=None, *, api_base=rep_mod.API_BASE,
                        session=None):
        instance._api_key = "t-tok"
        instance._api_base = api_base.rstrip("/")
        instance._session = self.fake
        instance._auth_error = None

    # ------------------------------------------------------------------

    def _seed_sync_run(self, model_slug: str, output):
        self.fake.queue_get(
            f"/models/{model_slug}",
            _FakeResponse(200, {"latest_version": {"id": "v-sha"}}),
        )
        self.fake.queue_post(
            "/predictions",
            _FakeResponse(201, {"id": "p1", "status": "starting"}),
        )
        self.fake.queue_get(
            "/predictions/p1",
            _FakeResponse(200, {"id": "p1", "status": "succeeded", "output": output}),
        )

    def test_image_styles_returns_image_url(self):
        self._seed_sync_run("stability-ai/sdxl", ["https://r.example/styled.png"])
        with mock.patch.object(rep_mod, "time") as t:
            t.time.return_value = 0
            t.sleep.side_effect = lambda s: None
            result = rep_mod.dispatch_image_styles({
                "source_image": "https://src.example/x.png",
                "style_reference": "https://style.example/y.png",
                "strength": 0.9,
            })
        self.assertEqual(result, {"image_url": "https://r.example/styled.png"})
        # First post is the prediction creation; verify the input shape.
        post_url, _, post_body = self.fake.posts[0]
        self.assertIn("/predictions", post_url)
        self.assertEqual(post_body["version"], "v-sha")
        self.assertIn("image", post_body["input"])
        self.assertIn("style_image", post_body["input"])
        self.assertEqual(post_body["input"]["prompt_strength"], 0.9)

    def test_image_to_prompt_adapts_caption(self):
        self._seed_sync_run("salesforce/blip", "a cat sitting on a fence")
        with mock.patch.object(rep_mod, "time") as t:
            t.time.return_value = 0
            t.sleep.side_effect = lambda s: None
            text = rep_mod.dispatch_image_to_prompt({
                "image": "https://x/y.png",
                "target_style": "mj",
            })
        self.assertTrue(text.startswith("a cat sitting on a fence"))
        self.assertIn("--ar 16:9", text)

    def test_image_varies_returns_list(self):
        # Three runs because count=3.
        for _ in range(3):
            self.fake.queue_get(
                "/models/lucataco/sdxl-img2img",
                _FakeResponse(200, {"latest_version": {"id": "v-sha"}}),
            )
            self.fake.queue_post(
                "/predictions",
                _FakeResponse(201, {"id": "p1", "status": "starting"}),
            )
            self.fake.queue_get(
                "/predictions/p1",
                _FakeResponse(200, {"id": "p1", "status": "succeeded",
                                    "output": ["https://r/v.png"]}),
            )
        with mock.patch.object(rep_mod, "time") as t:
            t.time.return_value = 0
            t.sleep.side_effect = lambda s: None
            res = rep_mod.dispatch_image_varies({
                "source_image": "https://src/x.png",
                "count": 3,
                "variation_strength": 0.4,
            })
        self.assertEqual(len(res), 3)
        self.assertEqual(res[0], {"image_url": "https://r/v.png"})


# ---------------------------------------------------------------------------
# Async dispatch (queue interaction)
# ---------------------------------------------------------------------------

class AsyncDispatchTests(unittest.TestCase):
    def setUp(self):
        # Use a tmp-rooted JobQueue so the test never touches ~/ora/sessions.
        import tempfile
        self.tmpdir = tempfile.TemporaryDirectory()
        self.queue = JobQueue(sessions_root=self.tmpdir.name)
        # Replace get_default_queue for the duration of the test.
        self._patch_queue = mock.patch.object(
            rep_mod, "get_default_queue", return_value=self.queue
        )
        self._patch_queue.start()
        # Auth + session.
        self.fake = _FakeRequests()
        self._patch_init = mock.patch.object(
            rep_mod.ReplicateClient, "__init__", autospec=True,
            side_effect=self._init,
        )
        self._patch_init.start()
        self._patch_key = mock.patch.object(
            rep_mod, "_resolve_api_key", return_value="t-tok"
        )
        self._patch_key.start()

    def tearDown(self):
        self._patch_queue.stop()
        self._patch_init.stop()
        self._patch_key.stop()
        self.tmpdir.cleanup()

    def _init(self, instance, api_key=None, *, api_base=rep_mod.API_BASE, session=None):
        instance._api_key = "t-tok"
        instance._api_base = api_base.rstrip("/")
        instance._session = self.fake
        instance._auth_error = None

    def test_video_dispatch_files_queued_job(self):
        # Seed one full cycle's worth: model lookup, create, terminal poll.
        # We make the very first poll terminal so the loop exits without
        # ever sleeping — keeps the test deterministic.
        self.fake.queue_get(
            "/models/minimax/video-01",
            _FakeResponse(200, {"latest_version": {"id": "v-sha"}}),
        )
        self.fake.queue_post(
            "/predictions",
            _FakeResponse(201, {"id": "vp", "status": "starting"}),
        )
        self.fake.queue_get(
            "/predictions/vp",
            _FakeResponse(200, {"id": "vp", "status": "succeeded",
                                "output": "https://r.example/clip.mp4"}),
        )
        rep_mod.set_active_conversation("conv-1")
        with mock.patch.object(rep_mod, "_HAS_JOB_QUEUE", True):
            job = rep_mod.dispatch_video_generates({
                "prompt": "a serene lake at dawn",
                "duration": 4,
                "resolution": "720p",
            })
        self.assertIn(job["status"], {"queued", "in_progress", "complete"})
        # Wait for the polling thread to drive the queue to terminal.
        deadline = time.time() + 5.0
        while time.time() < deadline:
            updated = self.queue.get_job("conv-1", job["id"])
            if updated["status"] in {"complete", "failed", "cancelled"}:
                break
            time.sleep(0.02)
        updated = self.queue.get_job("conv-1", job["id"])
        self.assertEqual(updated["status"], "complete")
        self.assertEqual(updated["result_ref"], "https://r.example/clip.mp4")

    def test_style_trains_rejects_under_three_refs(self):
        with self.assertRaises(rep_mod.ReplicateError) as cm:
            rep_mod.dispatch_style_trains({
                "reference_images": [{"url": "a"}, {"url": "b"}],
                "name": "my-style",
            })
        self.assertEqual(cm.exception.code, "insufficient_examples")

    def test_async_stub_when_queue_missing(self):
        with mock.patch.object(rep_mod, "_HAS_JOB_QUEUE", False):
            with mock.patch.object(rep_mod, "get_default_queue", None):
                stub = rep_mod.dispatch_video_generates({"prompt": "x"})
        self.assertTrue(stub.get("stub"))
        self.assertIn("WP-7.6.1", stub.get("TODO", ""))


# ---------------------------------------------------------------------------
# Registration against the live capabilities.json registry
# ---------------------------------------------------------------------------

class RegistrationTests(unittest.TestCase):
    def test_register_replicate_provider_no_key_still_registers(self):
        registry = _registry_for_capabilities()
        with mock.patch.object(rep_mod, "_resolve_api_key", return_value=None):
            registered = rep_mod.register_replicate_provider(registry)
        # Replicate fulfills these slots — they all live in the shipped
        # capabilities.json.
        for slot in ("image_styles", "image_varies", "image_to_prompt",
                     "video_generates", "style_trains"):
            self.assertIn(slot, registered)
            self.assertTrue(registry.has_provider(slot, "replicate"))

    def test_invocation_with_no_key_surfaces_model_unavailable(self):
        registry = _registry_for_capabilities()
        with mock.patch.object(rep_mod, "_resolve_api_key", return_value=None):
            rep_mod.register_replicate_provider(registry)
        # Force the routing to pick replicate for image_to_prompt.
        registry._routing_config = {"slots": {"image_to_prompt": {"preferred": "replicate"}}}
        # Fake requests still installed? No — but the auth error fires
        # before any HTTP call. Verify we get model_unavailable.
        with self.assertRaises(Exception) as cm:
            registry.invoke("image_to_prompt", {"image": "https://x/y.png"})
        self.assertIn("model_unavailable", str(cm.exception))


# ---------------------------------------------------------------------------
# Optional live smoke (gated on env var; opt-in only)
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    os.environ.get("ORA_REPLICATE_LIVE") == "1",
    "Live Replicate call disabled; set ORA_REPLICATE_LIVE=1 to enable.",
)
class LiveSmokeTest(unittest.TestCase):  # pragma: no cover — opt-in only
    def test_caption_real_image(self):
        client = rep_mod.ReplicateClient()
        result = client.run(
            "salesforce/blip",
            {"image": "https://replicate.delivery/pbxt/IkChvHgbQDbgN6jW3"
                       "B9OrzFySSNlqdCPOzRoBMK0c1cXaJsX/cat.jpg",
             "task": "image_captioning"},
            timeout=180.0,
        )
        self.assertEqual(result["status"], "succeeded")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
