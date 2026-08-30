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


_dns_patch = None


def setUpModule():
    global _dns_patch
    _dns_patch = mock.patch.object(
        rep_mod.network_policy.socket,
        "getaddrinfo",
        return_value=[
            (rep_mod.network_policy.socket.AF_INET,
             rep_mod.network_policy.socket.SOCK_STREAM, 6, "",
             ("93.184.216.34", 443)),
        ],
    )
    _dns_patch.start()


def tearDownModule():
    if _dns_patch is not None:
        _dns_patch.stop()


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

    def post(self, url, headers=None, json=None, timeout=None,
             allow_redirects=None):
        self.posts.append((url, headers or {}, json or {}))
        return self._dequeue(self.post_responses, url)

    def get(self, url, headers=None, timeout=None, allow_redirects=None):
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

    def test_image_edits_normalizes_byte_inputs(self):
        self._seed_sync_run("stability-ai/sdxl", ["https://r/edited.png"])
        with mock.patch.object(rep_mod, "time") as t:
            t.time.return_value = 0
            t.sleep.side_effect = lambda s: None
            result = rep_mod.dispatch_image_edits({
                "image": b"source-png",
                "mask": bytearray(b"mask-png"),
                "prompt": "add a blue hat",
                "strength": 0.6,
            })
        self.assertEqual(result, {"image_url": "https://r/edited.png"})
        payload = self.fake.posts[0][2]["input"]
        self.assertEqual(payload["image"],
                         "data:image/png;base64,c291cmNlLXBuZw==")
        self.assertEqual(payload["mask"],
                         "data:image/png;base64,bWFzay1wbmc=")
        self.assertEqual(payload["prompt_strength"], 0.6)

    def test_image_outpaints_registers_a_real_prediction(self):
        self._seed_sync_run("stability-ai/sdxl", ["https://r/outpaint.png"])
        with mock.patch.object(rep_mod, "time") as t:
            t.time.return_value = 0
            t.sleep.side_effect = lambda s: None
            result = rep_mod.dispatch_image_outpaints({
                "image": b"source-png",
                "directions": ["right"],
                "prompt": "continue the landscape",
                "aspect_ratio": "16:9",
            })
        self.assertEqual(result, {"image_url": "https://r/outpaint.png"})
        payload = self.fake.posts[0][2]["input"]
        self.assertEqual(payload["image"],
                         "data:image/png;base64,c291cmNlLXBuZw==")
        self.assertEqual(payload["directions"], ["right"])
        self.assertEqual(payload["aspect_ratio"], "16:9")

    def test_image_upscales_uses_configured_scale(self):
        self._seed_sync_run("nightmareai/real-esrgan", ["https://r/upscaled.png"])
        with mock.patch.object(rep_mod, "time") as t:
            t.time.return_value = 0
            t.sleep.side_effect = lambda s: None
            result = rep_mod.dispatch_image_upscales({
                "image": memoryview(b"source-png"),
                "scale_factor": 4,
            })
        self.assertEqual(result, {"image_url": "https://r/upscaled.png"})
        payload = self.fake.posts[0][2]["input"]
        self.assertEqual(payload["image"],
                         "data:image/png;base64,c291cmNlLXBuZw==")
        self.assertEqual(payload["scale"], 4)


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
        if hasattr(rep_mod._thread_local, "conversation_id"):
            del rep_mod._thread_local.conversation_id

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

    def _create_dialogue(self, conversation_id):
        dialogue_dir = Path(self.tmpdir.name) / conversation_id
        dialogue_dir.mkdir(parents=True, exist_ok=True)
        (dialogue_dir / "conversation.json").write_text(
            json.dumps({"conversation_id": conversation_id, "messages": []}),
            encoding="utf-8",
        )

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
        signed_url = "https://r.example/clip.mp4?token=never-persist"
        binding_seen = []

        def poll_after_durable_binding(_client, prediction_id):
            persisted_jobs = json.loads(
                (Path(self.tmpdir.name) / "conv-1" / "jobs.json").read_text(
                    encoding="utf-8",
                )
            )
            binding_seen.append(dict(persisted_jobs[0]["metadata"]))
            return {"id": prediction_id, "status": "succeeded", "output": signed_url}

        self._create_dialogue("conv-1")
        rep_mod.set_active_conversation("conv-1")
        with mock.patch.object(rep_mod, "_HAS_JOB_QUEUE", True), \
             mock.patch.object(
                 rep_mod.ReplicateClient,
                 "poll",
                 autospec=True,
                 side_effect=poll_after_durable_binding,
             ), \
             mock.patch.object(
                 rep_mod.network_policy, "urllib_request_bytes",
                 return_value=(b"video-bytes", mock.sentinel.destination),
             ) as fetch:
            job = rep_mod.dispatch_video_generates({
                "prompt": "a serene lake at dawn",
                "duration": 4,
                "resolution": "720p",
            })
            deadline = time.time() + 5.0
            while time.time() < deadline:
                updated = self.queue.get_job("conv-1", job["id"])
                if updated["status"] in {"complete", "failed", "cancelled"}:
                    break
                time.sleep(0.02)
        self.assertIn(job["status"], {"queued", "in_progress", "complete"})
        updated = self.queue.get_job("conv-1", job["id"])
        self.assertEqual(updated["status"], "complete")
        self.assertEqual(len(binding_seen), 1)
        self.assertEqual(binding_seen[0]["provider_submission_state"], "bound")
        self.assertEqual(binding_seen[0]["provider_prediction_id"], "vp")
        self.assertEqual(binding_seen[0]["provider_conversation_id"], "conv-1")
        self.assertEqual(binding_seen[0]["provider_job_id"], job["id"])
        route = updated["result_ref"]["video_url"]
        self.assertTrue(route.startswith(f"/api/jobs/conv-1/{job['id']}/artifacts/"))
        self.assertNotIn("never-persist", json.dumps(updated))
        artifact = Path(self.tmpdir.name) / "conv-1" / "uploads" / route.rsplit("/", 1)[-1]
        self.assertEqual(artifact.read_bytes(), b"video-bytes")
        fetch.assert_called_once_with(
            signed_url, timeout=180, max_bytes=rep_mod._ASYNC_ARTIFACT_LIMIT,
        )
        persisted = (Path(self.tmpdir.name) / "conv-1" / "jobs.json").read_text(
            encoding="utf-8",
        )
        self.assertNotIn("never-persist", persisted)

    def test_restart_reconciles_bound_jobs_without_resubmission(self):
        original = JobQueue(sessions_root=self.tmpdir.name)

        def make_job(
            conversation_id, prediction_id, *, indeterminate=False,
            authenticated=True,
        ):
            if authenticated:
                self._create_dialogue(conversation_id)
            job = original.dispatch(
                conversation_id,
                "video_generates",
                {"prompt": conversation_id},
                metadata={"provider": "replicate", "model": "minimax/video-01"},
            )
            binding = {
                "provider_submission_state": (
                    "submitting" if indeterminate else "bound"
                ),
                "provider_version": "v-sha",
                "provider_conversation_id": conversation_id,
                "provider_job_id": job["id"],
            }
            if prediction_id is not None:
                binding["provider_prediction_id"] = prediction_id
            original.begin_submission(conversation_id, job["id"], binding)
            if not indeterminate:
                original.update_metadata(
                    conversation_id,
                    job["id"],
                    {"provider_prediction_id": prediction_id},
                    require_persisted=True,
                )
            return job

        complete = make_job("restart-complete", "pred-complete")
        failed = make_job("restart-failed", "pred-failed")
        canceled = make_job("restart-canceled", "pred-canceled")
        indeterminate = make_job("restart-indeterminate", None, indeterminate=True)
        orphan = make_job(
            "restart-orphan", "pred-orphan", authenticated=False,
        )
        del original

        signed_url = "https://r.example/resumed.mp4?token=resume-never-persist"
        self.fake.queue_get(
            "/predictions/pred-complete",
            _FakeResponse(200, {
                "id": "pred-complete",
                "status": "succeeded",
                "output": signed_url,
            }),
        )
        self.fake.queue_get(
            "/predictions/pred-failed",
            _FakeResponse(200, {
                "id": "pred-failed",
                "status": "failed",
                "error": "provider rejected output",
            }),
        )
        self.fake.queue_get(
            "/predictions/pred-canceled",
            _FakeResponse(200, {
                "id": "pred-canceled",
                "status": "canceled",
            }),
        )

        restarted = JobQueue(sessions_root=self.tmpdir.name)
        with mock.patch.object(rep_mod, "get_default_queue", return_value=restarted), \
             mock.patch.object(
                 rep_mod.network_policy,
                 "urllib_request_bytes",
                 return_value=(b"resumed-video", mock.sentinel.destination),
             ) as fetch:
            threads = rep_mod.reconcile_unfinished_jobs()
            for thread in threads:
                thread.join(timeout=5.0)
                self.assertFalse(thread.is_alive())

        self.assertEqual(len(threads), 3)
        self.assertEqual(self.fake.posts, [])
        self.assertEqual(
            {url.rsplit("/", 1)[-1] for url, _headers in self.fake.gets},
            {"pred-complete", "pred-failed", "pred-canceled"},
        )
        complete_state = restarted.get_job("restart-complete", complete["id"])
        self.assertEqual(complete_state["status"], "complete")
        route = complete_state["result_ref"]["video_url"]
        artifact = (
            Path(self.tmpdir.name)
            / "restart-complete"
            / "uploads"
            / route.rsplit("/", 1)[-1]
        )
        self.assertEqual(artifact.read_bytes(), b"resumed-video")
        fetch.assert_called_once_with(
            signed_url, timeout=180, max_bytes=rep_mod._ASYNC_ARTIFACT_LIMIT,
        )
        self.assertEqual(
            restarted.get_job("restart-failed", failed["id"])["status"],
            "failed",
        )
        self.assertEqual(
            restarted.get_job("restart-canceled", canceled["id"])["status"],
            "cancelled",
        )
        indeterminate_state = restarted.get_job(
            "restart-indeterminate", indeterminate["id"],
        )
        self.assertEqual(indeterminate_state["status"], "failed")
        self.assertIn("Automatic resubmission is disabled", indeterminate_state["error"])
        self.assertEqual(
            restarted.get_job("restart-orphan", orphan["id"])["status"],
            "in_progress",
        )
        persisted = (
            Path(self.tmpdir.name) / "restart-complete" / "jobs.json"
        ).read_text(encoding="utf-8")
        self.assertNotIn("resume-never-persist", persisted)

    def test_style_training_materializes_case_varied_urls_in_values_and_keys(self):
        self.fake.queue_get(
            "/models/ostris/flux-dev-lora-trainer",
            _FakeResponse(200, {"latest_version": {"id": "v-sha"}}),
        )
        self.fake.queue_post(
            "/predictions",
            _FakeResponse(201, {"id": "sp", "status": "starting"}),
        )
        weights_url = (
            "hTTps://r.example/weights.safetensors?sig=weights-never-persist"
        )
        key_url = "HTTP://r.example/key.bin?token=key-never-persist"
        preview_url = "HtTpS://r.example/preview.mp4?token=preview-never-persist"
        self.fake.queue_get(
            "/predictions/sp",
            _FakeResponse(200, {"id": "sp", "status": "succeeded",
                                "output": {
                                    "weights": weights_url,
                                    key_url: {"nested": [preview_url]},
                                }}),
        )
        self._create_dialogue("conv-style")
        rep_mod.set_active_conversation("conv-style")
        with mock.patch.object(rep_mod, "_HAS_JOB_QUEUE", True), \
             mock.patch.object(
                 rep_mod.network_policy, "urllib_request_bytes",
                 side_effect=[
                     (b"weights", mock.sentinel.destination),
                     (b"key", mock.sentinel.destination),
                     (b"preview", mock.sentinel.destination),
                 ],
             ) as fetch:
            job = rep_mod.dispatch_style_trains({
                "reference_images": ["data:a", "data:b", "data:c"],
                "name": "watercolor",
            })
            deadline = time.time() + 5.0
            while time.time() < deadline:
                updated = self.queue.get_job("conv-style", job["id"])
                if updated["status"] in {"complete", "failed", "cancelled"}:
                    break
                time.sleep(0.02)
        updated = self.queue.get_job("conv-style", job["id"])
        self.assertEqual(updated["status"], "complete")
        result_ref = updated["result_ref"]
        self.assertTrue(result_ref["weights"].endswith(".safetensors"))
        materialized_keys = [
            key for key in result_ref
            if key.startswith(f"/api/jobs/conv-style/{job['id']}/artifacts/")
        ]
        self.assertEqual(len(materialized_keys), 1)
        preview_route = result_ref[materialized_keys[0]]["nested"][0]
        self.assertTrue(preview_route.startswith(
            f"/api/jobs/conv-style/{job['id']}/artifacts/"
        ))
        self.assertEqual(
            [call.args[0] for call in fetch.call_args_list],
            [weights_url, key_url, preview_url],
        )
        persisted = (
            Path(self.tmpdir.name) / "conv-style" / "jobs.json"
        ).read_text(encoding="utf-8")
        self.assertNotIn("never-persist", persisted)
        self.assertNotIn("r.example", persisted)
        for raw_url in (weights_url, key_url, preview_url):
            self.assertNotIn(raw_url, persisted)

    def test_style_trains_rejects_under_three_refs(self):
        with self.assertRaises(rep_mod.ReplicateError) as cm:
            rep_mod.dispatch_style_trains({
                "reference_images": [{"url": "a"}, {"url": "b"}],
                "name": "my-style",
            })
        self.assertEqual(cm.exception.code, "insufficient_examples")

    def test_style_trains_requires_an_explicit_live_dialogue(self):
        request = {
            "reference_images": ["data:a", "data:b", "data:c"],
            "name": "watercolor",
        }
        for owner in ("default", "missing-dialogue"):
            rep_mod.set_active_conversation(owner)
            with self.assertRaises(rep_mod.ReplicateError) as cm:
                rep_mod.dispatch_style_trains(request)
            self.assertEqual(cm.exception.code, "prompt_rejected")
        self.assertEqual(self.fake.gets, [])
        self.assertEqual(self.fake.posts, [])

    def test_cancel_wins_before_submission_and_contacts_no_provider(self):
        conversation_id = "cancel-first"
        self._create_dialogue(conversation_id)
        job = self.queue.dispatch(
            conversation_id,
            "style_trains",
            {},
            metadata={"provider": "replicate", "model": "trainer"},
        )
        client = rep_mod.ReplicateClient(api_key="t-tok", session=self.fake)
        ready = threading.Event()
        release = threading.Event()
        original_begin = self.queue.begin_submission

        def blocked_begin(*args, **kwargs):
            ready.set()
            self.assertTrue(release.wait(5.0))
            return original_begin(*args, **kwargs)

        with mock.patch.object(
            self.queue, "begin_submission", side_effect=blocked_begin,
        ):
            worker = threading.Thread(
                target=rep_mod._poll_thread,
                args=(
                    "style_trains", client, {"model": "trainer"}, {},
                    conversation_id, job["id"],
                ),
            )
            worker.start()
            self.assertTrue(ready.wait(5.0))
            self.queue.request_cancel(conversation_id, job["id"])
            release.set()
            worker.join(5.0)
        self.assertFalse(worker.is_alive())
        self.assertEqual(
            self.queue.get_job(conversation_id, job["id"])["status"],
            "cancelled",
        )
        self.assertEqual(self.fake.gets, [])
        self.assertEqual(self.fake.posts, [])

    def test_submission_wins_then_persisted_cancel_reaches_prediction(self):
        conversation_id = "submit-first"
        self._create_dialogue(conversation_id)
        job = self.queue.dispatch(
            conversation_id,
            "style_trains",
            {},
            metadata={"provider": "replicate", "model": "trainer"},
        )
        self.fake.queue_post(
            "/predictions/pred-race/cancel",
            _FakeResponse(200, {"id": "pred-race", "status": "canceled"}),
        )
        self.fake.queue_post(
            "/predictions",
            _FakeResponse(201, {"id": "pred-race", "status": "starting"}),
        )
        client = rep_mod.ReplicateClient(api_key="t-tok", session=self.fake)
        ready = threading.Event()
        release = threading.Event()

        def blocked_version(_model):
            ready.set()
            self.assertTrue(release.wait(5.0))
            return "v-race"

        with mock.patch.object(client, "resolve_version", side_effect=blocked_version):
            worker = threading.Thread(
                target=rep_mod._poll_thread,
                args=(
                    "style_trains", client, {"model": "trainer"}, {},
                    conversation_id, job["id"],
                ),
            )
            worker.start()
            self.assertTrue(ready.wait(5.0))
            claimed = self.queue.get_job(conversation_id, job["id"])
            self.assertEqual(claimed["status"], "in_progress")
            self.assertEqual(
                claimed["metadata"]["provider_submission_state"], "submitting",
            )
            self.queue.request_cancel(conversation_id, job["id"])
            release.set()
            worker.join(5.0)
        self.assertFalse(worker.is_alive())
        final = self.queue.get_job(conversation_id, job["id"])
        self.assertEqual(final["status"], "cancelled")
        self.assertTrue(final["cancel_requested"])
        self.assertEqual(
            [url.rsplit("/v1", 1)[-1] for url, _headers, _body in self.fake.posts],
            ["/predictions", "/predictions/pred-race/cancel"],
        )

    def test_delete_waits_for_poll_and_cancel_ack_before_erasing_binding(self):
        conversation_id = "delete-race"
        self._create_dialogue(conversation_id)
        job = self.queue.dispatch(
            conversation_id,
            "style_trains",
            {},
            metadata={"provider": "replicate", "model": "trainer"},
        )
        self.queue.begin_submission(
            conversation_id,
            job["id"],
            {
                "provider_submission_state": "bound",
                "provider_prediction_id": "pred-delete",
                "provider_conversation_id": conversation_id,
                "provider_job_id": job["id"],
            },
        )
        worker_client = mock.Mock()
        poll_entered = threading.Event()
        release_poll = threading.Event()

        def blocked_poll(_prediction_id):
            poll_entered.set()
            self.assertTrue(release_poll.wait(5.0))
            return {"id": "pred-delete", "status": "processing"}

        worker_client.poll.side_effect = blocked_poll
        worker = threading.Thread(
            target=rep_mod._poll_thread,
            args=(
                "style_trains", worker_client, {}, {}, conversation_id, job["id"],
                "pred-delete",
            ),
        )
        worker.start()
        self.assertTrue(poll_entered.wait(5.0))

        delete_client = mock.Mock()
        delete_client.cancel.return_value = {
            "id": "pred-delete", "status": "processing",
        }
        confirmation_entered = threading.Event()
        release_confirmation = threading.Event()

        def blocked_confirmation(_prediction_id):
            confirmation_entered.set()
            self.assertTrue(release_confirmation.wait(5.0))
            return {"id": "pred-delete", "status": "canceled"}

        delete_client.poll.side_effect = blocked_confirmation
        delete_done = threading.Event()
        delete_result = []

        def delete():
            try:
                delete_result.append(
                    self.queue.forget_conversation(conversation_id)
                )
            finally:
                delete_done.set()

        deleter = threading.Thread(
            target=delete,
        )
        with mock.patch.object(
            rep_mod, "ReplicateClient", return_value=delete_client,
        ):
            deleter.start()
            self.assertFalse(delete_done.wait(0.1))
            release_poll.set()
            self.assertTrue(confirmation_entered.wait(5.0))
            self.assertFalse(delete_done.wait(0.1))

            # Cancellation acknowledgement has not arrived, so the queue and
            # its durable provider binding must still be recoverable.
            during = self.queue.get_job(conversation_id, job["id"])
            self.assertEqual(
                during["metadata"]["provider_prediction_id"], "pred-delete",
            )
            persisted_during = json.loads(
                (Path(self.tmpdir.name) / conversation_id / "jobs.json")
                .read_text(encoding="utf-8")
            )[0]
            self.assertEqual(
                persisted_during["metadata"]["provider_prediction_id"],
                "pred-delete",
            )

            release_confirmation.set()
            self.assertTrue(delete_done.wait(5.0))
        deleter.join(5.0)
        worker.join(5.0)
        self.assertFalse(deleter.is_alive())
        self.assertFalse(worker.is_alive())
        worker_client.poll.assert_called_once_with("pred-delete")
        worker_client.cancel.assert_not_called()
        delete_client.cancel.assert_called_once_with("pred-delete")
        delete_client.poll.assert_called_once_with("pred-delete")
        self.assertEqual(delete_result, [1])
        self.assertEqual(self.queue.list_jobs(conversation_id), [])

    def test_delete_cancel_failure_reports_and_retains_durable_binding(self):
        conversation_id = "delete-cancel-fails"
        self._create_dialogue(conversation_id)
        job = self.queue.dispatch(
            conversation_id,
            "style_trains",
            {},
            metadata={"provider": "replicate", "model": "trainer"},
        )
        self.queue.begin_submission(
            conversation_id,
            job["id"],
            {
                "provider_submission_state": "bound",
                "provider_prediction_id": "pred-retained",
                "provider_conversation_id": conversation_id,
                "provider_job_id": job["id"],
            },
        )
        client = mock.Mock()
        client.cancel.side_effect = RuntimeError("controlled cancel failure")
        client.poll.side_effect = RuntimeError("controlled confirmation failure")

        with mock.patch.object(rep_mod, "ReplicateClient", return_value=client):
            with self.assertRaises(RuntimeError) as raised:
                self.queue.forget_conversation(conversation_id)

        self.assertIn("was not confirmed", str(raised.exception))
        retained = self.queue.get_job(conversation_id, job["id"])
        self.assertEqual(retained["status"], "in_progress")
        self.assertEqual(
            retained["metadata"]["provider_prediction_id"], "pred-retained",
        )
        persisted = json.loads(
            (Path(self.tmpdir.name) / conversation_id / "jobs.json")
            .read_text(encoding="utf-8")
        )[0]
        self.assertEqual(
            persisted["metadata"]["provider_prediction_id"], "pred-retained",
        )
        self.assertNotIn(
            conversation_id.casefold(), self.queue._deleted_conversations,
        )

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
        for slot in ("image_edits", "image_outpaints", "image_upscales",
                     "image_styles", "image_varies", "image_to_prompt",
                     "video_generates", "style_trains"):
            self.assertIn(slot, registered)
            self.assertTrue(registry.has_provider(slot, "replicate"))

    def test_invocation_with_no_key_surfaces_model_unavailable(self):
        registry = _registry_for_capabilities()
        # The mock must cover BOTH registration AND invocation — the
        # ReplicateClient resolves the key lazily inside the handler, so
        # narrowing the mock to just the registration call would let a
        # real keychain key leak through at invocation time.
        with mock.patch.object(rep_mod, "_resolve_api_key", return_value=None):
            rep_mod.register_replicate_provider(registry)
            # Force the routing to pick replicate for image_to_prompt.
            registry._routing_config = {"slots": {"image_to_prompt": {"preferred": "replicate"}}}
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
