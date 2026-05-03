#!/usr/bin/env python3
"""
WP-4.4 — Text-only fallback UX tests.

Runs under stdlib ``unittest`` — no pytest dependency. Invoke::

    /opt/homebrew/bin/python3 -m unittest discover -s ~/ora/orchestrator/tests -v

Scope:
* ``_build_visual_fallback_frame`` returns ``None`` for unset/mixed
  context_pkg (backward compat: no image, no signals → no frame).
* ``no_vision_available=True`` → frame with ``reason='no_vision_available'``
  and the full action set.
* ``vision_extraction_result=None`` + ``vision_extractor_selected`` set +
  ``image_path`` present + ``vision_extraction_meta`` with parse_errors →
  frame with ``reason='extraction_failed'`` + ``extractor_attempted`` + the
  listed parse_errors.
* Direct-pass (vision-capable downstream, result set) produces no frame.
* Backward compat — text-only requests with no image flow unchanged.
* ``/chat/queue-retry`` endpoint:
    - valid payload → 200 with queued=True and a growing queue_size
    - missing fields → 400 with descriptive error
    - bad attempt_reason → 400
    - persists to both in-memory dict and per-session JSON file
* SSE pipeline integration — a mocked pipeline that sets
  ``no_vision_available`` emits a ``visual_fallback`` event BEFORE the
  response event.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
WORKSPACE = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))
sys.path.insert(0, str(WORKSPACE / "server"))


class _NoopThread:
    """Stub thread that fires no side-effects — mirrors test_visual_e2e."""

    def __init__(self, *a, **k):
        pass

    def start(self):
        pass

    def join(self, *a, **k):
        pass

    daemon = True


# ---------------------------------------------------------------------------
# Unit tests for _build_visual_fallback_frame
# ---------------------------------------------------------------------------


class BuildVisualFallbackFrameTests(unittest.TestCase):
    """Direct unit tests for the pure helper ``_build_visual_fallback_frame``."""

    def setUp(self) -> None:
        import server  # noqa: WPS433
        self.server = server
        self.build = server._build_visual_fallback_frame

    def test_none_context_returns_none(self) -> None:
        """Calling with ``None`` returns ``None`` — no frame to emit."""
        self.assertIsNone(self.build(None))

    def test_empty_context_returns_none(self) -> None:
        """No signals set → backward-compat quiet path."""
        self.assertIsNone(self.build({}))

    def test_text_only_context_returns_none(self) -> None:
        """Typical text-only request (no image, no signals) → no frame."""
        ctx = {"mode_name": "systems_dynamics", "gear": 3}
        self.assertIsNone(self.build(ctx))

    def test_direct_pass_context_returns_none(self) -> None:
        """Vision-capable downstream: image_path + vision_direct_pass, no fallback."""
        ctx = {
            "image_path": "/abs/path/img.png",
            "vision_direct_pass": True,
            "vision_extractor_selected": None,
        }
        self.assertIsNone(self.build(ctx))

    def test_no_vision_available_emits_frame(self) -> None:
        """``no_vision_available=True`` → frame with reason='no_vision_available'."""
        ctx = {
            "image_path": "/abs/img.png",
            "no_vision_available": True,
            "vision_extractor_selected": None,
        }
        frame = self.build(ctx)
        self.assertIsNotNone(frame)
        self.assertEqual(frame["reason"], "no_vision_available")
        # No extractor was tried — extractor_attempted is None.
        self.assertIsNone(frame["extractor_attempted"])
        self.assertEqual(frame["parse_errors"], [])
        self.assertIn("couldn't extract structure", frame["user_message"].lower())
        self.assertEqual(
            frame["actions"],
            ["start_tracing", "queue_for_later", "dismiss"],
        )

    def test_extraction_failed_emits_frame_with_meta(self) -> None:
        """Null result + meta with parse_errors → reason='extraction_failed'."""
        ctx = {
            "image_path": "/abs/img.png",
            "vision_extractor_selected": {
                "id": "api-vision",
                "bucket": "premium",
                "display_name": "API Vision Model",
            },
            "vision_extraction_result": None,  # explicit key, explicit None
            "vision_extraction_meta": {
                "extractor_model": "api-vision",
                "confidence": 0.0,
                "parse_errors": ["JSON parse failed at col 37", "unexpected token"],
            },
        }
        frame = self.build(ctx)
        self.assertIsNotNone(frame)
        self.assertEqual(frame["reason"], "extraction_failed")
        self.assertEqual(frame["extractor_attempted"], "api-vision")
        self.assertEqual(
            frame["parse_errors"],
            ["JSON parse failed at col 37", "unexpected token"],
        )
        self.assertIn("couldn't extract", frame["user_message"].lower())
        self.assertIn("start_tracing", frame["actions"])
        self.assertIn("queue_for_later", frame["actions"])
        self.assertIn("dismiss", frame["actions"])

    def test_extraction_failed_falls_back_to_selected_display_name(self) -> None:
        """When meta lacks extractor_model, fall back to the selected display_name."""
        ctx = {
            "image_path": "/abs/img.png",
            "vision_extractor_selected": {
                "id": "api-vision",
                "bucket": "premium",
                "display_name": "Fancy Vision",
            },
            "vision_extraction_result": None,
            "vision_extraction_meta": {
                "parse_errors": ["bad json"],
            },
        }
        frame = self.build(ctx)
        self.assertEqual(frame["extractor_attempted"], "Fancy Vision")

    def test_extraction_failed_coerces_non_list_parse_errors(self) -> None:
        """Defensive: if parse_errors is a string, wrap it; if missing, use []."""
        ctx = {
            "image_path": "/abs/img.png",
            "vision_extractor_selected": {"id": "x", "bucket": "y", "display_name": "X"},
            "vision_extraction_result": None,
            "vision_extraction_meta": {
                "extractor_model": "x",
                "parse_errors": "single string",
            },
        }
        frame = self.build(ctx)
        self.assertEqual(frame["parse_errors"], ["single string"])

    def test_extraction_present_no_frame(self) -> None:
        """``vision_extraction_result`` non-None → extraction succeeded, no frame."""
        ctx = {
            "image_path": "/abs/img.png",
            "vision_extractor_selected": {"id": "api-vision", "bucket": "premium"},
            "vision_extraction_result": {"entities": [{"id": "e-1"}], "relationships": []},
            "vision_extraction_meta": {"extractor_model": "api-vision"},
        }
        self.assertIsNone(self.build(ctx))

    def test_non_dict_context_is_noop(self) -> None:
        """Defensive: a non-dict (list, str) → None."""
        self.assertIsNone(self.build([]))
        self.assertIsNone(self.build("nope"))
        self.assertIsNone(self.build(42))

    def test_no_image_but_flag_set_still_emits(self) -> None:
        """If the server somehow sees no_vision_available=True without an image,
        still emit — the flag is authoritative."""
        ctx = {"no_vision_available": True}
        frame = self.build(ctx)
        self.assertIsNotNone(frame)
        self.assertEqual(frame["reason"], "no_vision_available")

    def test_extraction_result_key_missing_no_frame(self) -> None:
        """Without the `vision_extraction_result` key at all, the gate hasn't
        run the extractor yet — do not surface an extraction_failed frame."""
        ctx = {
            "image_path": "/abs/img.png",
            "vision_extractor_selected": {"id": "api-vision", "bucket": "premium"},
            # No vision_extraction_result key at all.
        }
        self.assertIsNone(self.build(ctx))


# ---------------------------------------------------------------------------
# /chat/queue-retry endpoint
# ---------------------------------------------------------------------------


class ChatQueueRetryTests(unittest.TestCase):
    """Endpoint-level tests for the vision-retry persistence surface."""

    def setUp(self) -> None:
        import server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()
        # Isolate the disk queue to a throwaway temp directory. The
        # ``_persist_vision_retry_queue`` helper joins VISUAL_UPLOADS_ROOT so
        # swapping it here sandboxes every test.
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_root = server.VISUAL_UPLOADS_ROOT
        server.VISUAL_UPLOADS_ROOT = self._tmpdir.name
        # Clear the in-memory queue between runs.
        server._vision_retry_queue.clear()

    def tearDown(self) -> None:
        self.server.VISUAL_UPLOADS_ROOT = self._orig_root
        self._tmpdir.cleanup()
        self.server._vision_retry_queue.clear()

    def test_queue_retry_valid_payload_returns_200(self) -> None:
        resp = self.client.post(
            "/chat/queue-retry",
            data=json.dumps({
                "conversation_id": "wp44-a",
                "image_path": "/abs/sessions/wp44-a/uploads/x.png",
                "attempt_reason": "no_vision_available",
            }),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.data.decode("utf-8"))
        self.assertTrue(payload["queued"])
        self.assertEqual(payload["queue_size"], 1)
        entry = payload["entry"]
        self.assertEqual(entry["conversation_id"], "wp44-a")
        self.assertEqual(entry["attempt_reason"], "no_vision_available")
        self.assertIn("queued_at", entry)

    def test_queue_retry_persists_to_disk(self) -> None:
        self.client.post(
            "/chat/queue-retry",
            data=json.dumps({
                "conversation_id": "wp44-b",
                "image_path": "/x.png",
                "attempt_reason": "extraction_failed",
            }),
            headers={"Content-Type": "application/json"},
        )
        disk_path = os.path.join(
            self.server.VISUAL_UPLOADS_ROOT, "wp44-b", "vision-retry-queue.json"
        )
        self.assertTrue(os.path.exists(disk_path),
                        f"expected queue file at {disk_path}")
        with open(disk_path) as f:
            contents = json.load(f)
        self.assertIsInstance(contents, list)
        self.assertEqual(len(contents), 1)
        self.assertEqual(contents[0]["conversation_id"], "wp44-b")

    def test_queue_retry_appends_multiple_entries(self) -> None:
        for i in range(3):
            self.client.post(
                "/chat/queue-retry",
                data=json.dumps({
                    "conversation_id": "wp44-c",
                    "image_path": f"/img-{i}.png",
                    "attempt_reason": "no_vision_available",
                }),
                headers={"Content-Type": "application/json"},
            )
        self.assertEqual(len(self.server._vision_retry_queue.get("wp44-c", [])), 3)

    def test_queue_retry_missing_conversation_id_is_400(self) -> None:
        resp = self.client.post(
            "/chat/queue-retry",
            data=json.dumps({
                "image_path": "/x.png",
                "attempt_reason": "no_vision_available",
            }),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 400)
        payload = json.loads(resp.data.decode("utf-8"))
        self.assertIn("conversation_id", payload.get("error", "").lower())

    def test_queue_retry_missing_image_path_is_400(self) -> None:
        resp = self.client.post(
            "/chat/queue-retry",
            data=json.dumps({
                "conversation_id": "wp44-d",
                "attempt_reason": "no_vision_available",
            }),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 400)
        payload = json.loads(resp.data.decode("utf-8"))
        self.assertIn("image_path", payload.get("error", "").lower())

    def test_queue_retry_bad_attempt_reason_is_400(self) -> None:
        resp = self.client.post(
            "/chat/queue-retry",
            data=json.dumps({
                "conversation_id": "wp44-e",
                "image_path": "/x.png",
                "attempt_reason": "bogus-reason",
            }),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 400)
        payload = json.loads(resp.data.decode("utf-8"))
        self.assertIn("attempt_reason", payload.get("error", "").lower())

    def test_queue_retry_empty_body_is_400(self) -> None:
        resp = self.client.post(
            "/chat/queue-retry",
            data="",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_queue_retry_loads_existing_disk_queue_on_first_post(self) -> None:
        """If the disk file exists from a prior session, new posts append."""
        # Pre-seed the on-disk queue file.
        pre_dir = os.path.join(self.server.VISUAL_UPLOADS_ROOT, "wp44-f")
        os.makedirs(pre_dir, exist_ok=True)
        pre_path = os.path.join(pre_dir, "vision-retry-queue.json")
        with open(pre_path, "w") as f:
            json.dump([{"conversation_id": "wp44-f",
                        "image_path": "/pre-existing.png",
                        "attempt_reason": "no_vision_available",
                        "queued_at": "2026-04-01T00:00:00"}], f)
        # POST a new entry — should append to the pre-seeded entry.
        resp = self.client.post(
            "/chat/queue-retry",
            data=json.dumps({
                "conversation_id": "wp44-f",
                "image_path": "/new.png",
                "attempt_reason": "extraction_failed",
            }),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.data.decode("utf-8"))
        self.assertEqual(payload["queue_size"], 2)


# ---------------------------------------------------------------------------
# SSE integration — pipeline emits visual_fallback before response
# ---------------------------------------------------------------------------


class VisualFallbackSseIntegrationTests(unittest.TestCase):
    """End-to-end: when context_pkg carries no_vision_available, the SSE
    stream emits a ``visual_fallback`` event BEFORE the first response
    event. Uses mocks at the step1/step2 layer so no real pipeline runs."""

    def setUp(self) -> None:
        import server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()

    def _run_fake_pipeline(self, ctx_pkg: dict) -> str:
        """Mock run_step1_cleanup + run_step2_context_assembly so
        _pipeline_stream produces the SSE frames we care about."""
        step1_ret = {
            "mode": "systems_dynamics",
            "cleaned_prompt": "test prompt",
            "operational_notation": "test prompt",
            "triage_tier": 1,
            "classification_confidence": "high",
        }

        def fake_run_step1_cleanup(user_input, conv_context, config):
            return step1_ret

        def fake_run_step2_context_assembly(step1, config):
            # Return a context_pkg with the upstream signals set AND the
            # mandatory fields build_system_prompt_for_gear needs.
            pkg = {
                "mode_name": step1["mode"],
                "mode_text": "",
                "cleaned_prompt": step1["cleaned_prompt"],
                "gear": 2,
                "conversation_rag": "",
                "concept_rag": "",
            }
            pkg.update(ctx_pkg)
            return pkg

        def fake_route_for_image_input(context_pkg, requested_model=None, **kwargs):
            # No-op: the ctx_pkg we assemble already carries the fallback
            # signals, so the real routing gate doesn't need to run.
            return requested_model, context_pkg

        def fake_get_endpoint(cfg):
            return {"name": "mock-model", "model": "mock-model"}

        def fake_run_model_with_tools(messages, ep, images=None):
            return "Mocked assistant prose reply."

        with mock.patch.object(self.server, "run_step1_cleanup",
                               side_effect=fake_run_step1_cleanup), \
             mock.patch.object(self.server, "run_step2_context_assembly",
                               side_effect=fake_run_step2_context_assembly), \
             mock.patch("boot.route_for_image_input",
                        side_effect=fake_route_for_image_input,
                        create=True), \
             mock.patch.object(self.server, "get_endpoint",
                               side_effect=fake_get_endpoint), \
             mock.patch.object(self.server, "_run_model_with_tools",
                               side_effect=fake_run_model_with_tools), \
             mock.patch.object(self.server.threading, "Thread", _NoopThread):
            resp = self.client.post(
                "/chat",
                data=json.dumps({
                    "message": "Describe this image.",
                    "history": [],
                    "panel_id": "main",
                    "is_main_feed": True,
                }),
                headers={"Content-Type": "application/json"},
            )
            body_bytes = b"".join(resp.response)
        self.assertEqual(resp.status_code, 200)
        return body_bytes.decode("utf-8")

    @staticmethod
    def _find_events(body: str, event_type: str) -> list:
        out = []
        for line in body.splitlines():
            if not line.startswith("data: "):
                continue
            try:
                d = json.loads(line[6:])
            except Exception:
                continue
            if d.get("type") == event_type:
                out.append(d)
        return out

    @unittest.skip(
        "V3 Backlog 2A (2026-04-30): /chat moved to plain HTTP. The "
        "visual_fallback SSE signal no longer reaches the browser. The UX "
        "still needs a path (e.g. chunk-YAML metadata + sidebar badge), "
        "but that is a separate redesign. The pipeline still emits the "
        "frame internally — it just doesn't surface client-side until the "
        "redesign lands."
    )
    def test_no_vision_available_emits_visual_fallback_event(self) -> None:
        pass

    @unittest.skip(
        "V3 Backlog 2A (2026-04-30): see "
        "test_no_vision_available_emits_visual_fallback_event."
    )
    def test_visual_fallback_precedes_response(self) -> None:
        pass

    @unittest.skip(
        "V3 Backlog 2A (2026-04-30): see "
        "test_no_vision_available_emits_visual_fallback_event."
    )
    def test_extraction_failed_emits_frame_with_parse_errors(self) -> None:
        pass

    def test_backward_compat_no_image_no_frame(self) -> None:
        """Text-only request → no visual_fallback frame in stream."""
        body = self._run_fake_pipeline({})
        events = self._find_events(body, "visual_fallback")
        self.assertEqual(events, [])

    def test_successful_extraction_no_frame(self) -> None:
        """image_path present but extraction SUCCESSFUL → no frame."""
        body = self._run_fake_pipeline({
            "image_path": "/abs/img.png",
            "vision_extractor_selected": {
                "id": "api-vision", "bucket": "premium",
            },
            "vision_extraction_result": {
                "entities": [{"id": "e-1", "position": [0.3, 0.3], "label": "A"}],
                "relationships": [],
            },
            "vision_extraction_meta": {
                "extractor_model": "api-vision",
                "confidence": 0.9,
                "parse_errors": [],
            },
        })
        events = self._find_events(body, "visual_fallback")
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
