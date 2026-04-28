#!/usr/bin/env python3
"""
Unit tests for the WP-2.3 visual end-to-end path (server-side).

Runs under the stdlib ``unittest`` runner — no pytest dependency. Invoke::

    /opt/homebrew/bin/python3 -m unittest discover -s ~/ora/orchestrator/tests -v

Scope:
* The chat endpoint streams SSE events; any ``ora-visual`` fenced block in
  the final response survives through the hook pipeline and appears in the
  SSE payload unchanged (for a schema-valid envelope).
* The Python-side visual validator accepts the embedded envelope as valid.
* The ``_default_layout`` retune returns an active preset (solo / studio)
  and resolves ``default_bucket`` annotations onto any declaring panel.
* The ``/api/bridge/<panel>`` endpoint accepts and persists
  ``ora_visual_blocks`` as part of its cached state.

All tests use ``app.test_client()`` so no socket I/O is required. The
orchestrator pipeline is mocked via ``unittest.mock.patch`` so tests are
fast and deterministic and don't need local models loaded.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
WORKSPACE = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))
sys.path.insert(0, str(WORKSPACE / "server"))

from visual_validator import validate_envelope  # noqa: E402


EXAMPLES_DIR = WORKSPACE / "config" / "visual-schemas" / "examples"


def _load_cld_envelope() -> dict:
    """Return a known-valid causal loop diagram envelope fixture."""
    with open(EXAMPLES_DIR / "causal_loop_diagram.valid.json") as fh:
        return json.load(fh)


def _fake_final_response(envelope: dict, prose_prefix: str = "", prose_suffix: str = "") -> str:
    """Build a fake pipeline final response that carries an ora-visual block."""
    fence = "```ora-visual\n" + json.dumps(envelope, indent=2) + "\n```"
    return f"{prose_prefix}\n\n{fence}\n\n{prose_suffix}"


def _extract_fence(text: str) -> dict | None:
    """Server-side mirror of the client-side extractor."""
    m = re.search(r"```ora-visual\s*\n(.*?)\n```", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


class VisualE2ESseTests(unittest.TestCase):
    """End-to-end SSE integration — fake pipeline, real server."""

    def setUp(self) -> None:
        # Import server lazily so orchestrator test ordering stays clean.
        import server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()
        self.envelope = _load_cld_envelope()

    def test_ora_visual_fence_survives_sse_transport(self) -> None:
        """The ora-visual fence appears intact in the streamed SSE body."""
        response_text = _fake_final_response(
            self.envelope,
            prose_prefix="Here is the requested CLD.",
            prose_suffix="Loop B1 balances velocity against accumulated tech debt.",
        )

        # Stub the orchestrator's streaming agent so we don't spin up models.
        # Accepts **kwargs so new optional kwargs (e.g. WP-3.3 extra_context)
        # don't break this fake stream.
        def fake_agentic_loop_stream(clean_input, history, use_pipeline=True,
                                     panel_id="main", images=None, **kwargs):
            # Mimic the agentic loop: pipeline_stage events then a response.
            yield self.server._sse(
                "pipeline_stage",
                stage="step1_cleanup",
                label="Cleaning prompt…",
                mode="systems_dynamics",
                gear=3,
            )
            yield self.server._sse(
                "pipeline_stage",
                stage="complete",
                gear=3,
            )
            yield self.server._sse("response", text=response_text)

        # Fully stub: the chat endpoint also spawns daemon threads that call
        # real models. Mocking the module-level functions isn't enough
        # because the threads may run after the `with` block closes (the
        # threading.Thread target is resolved at target=... time but the
        # daemon thread continues to execute with unmocked globals). We
        # therefore intercept threading.Thread itself to no-op away any
        # background work the endpoint spawns, and replace the streamer.
        class _NoopThread:
            def __init__(self, *a, **k): pass
            def start(self): pass
            def join(self, *a, **k): pass
            daemon = True

        with mock.patch.object(self.server, "agentic_loop_stream",
                               side_effect=fake_agentic_loop_stream), \
             mock.patch.object(self.server.threading, "Thread", _NoopThread):
            resp = self.client.post(
                "/chat",
                data=json.dumps({
                    "message": "Give me a CLD of velocity vs tech debt.",
                    "history": [],
                    "panel_id": "main",
                    "is_main_feed": True,
                }),
                headers={"Content-Type": "application/json"},
            )
            # Iterate the SSE stream INSIDE the with-block so mocks apply
            # during generate() execution (test_client responses are lazy).
            body_bytes = b"".join(resp.response)

        self.assertEqual(resp.status_code, 200)
        body = body_bytes.decode("utf-8")

        # A response event landed:
        self.assertIn('"type": "response"', body)
        # The ora-visual fence is present (SSE JSON-escapes the payload, so
        # backticks and ``` appear as ``` with escaped inner quotes).
        self.assertIn("ora-visual", body)
        # The envelope's discriminator appears in the escaped SSE payload:
        self.assertIn('causal_loop_diagram', body)

        # Pull the response payload out of the SSE stream and extract the fence.
        response_line = None
        for line in body.splitlines():
            if line.startswith("data: ") and '"response"' in line:
                response_line = line[6:]
                break
        self.assertIsNotNone(response_line,
                             "no response SSE event found in stream")
        payload = json.loads(response_line)
        self.assertEqual(payload["type"], "response")
        extracted = _extract_fence(payload["text"])
        self.assertIsNotNone(extracted, "could not extract ora-visual fence")
        self.assertEqual(extracted["type"], "causal_loop_diagram")
        self.assertEqual(extracted["id"], self.envelope["id"])

        # The embedded envelope validates under the Python validator.
        result = validate_envelope(extracted)
        self.assertTrue(result.valid,
                        f"envelope failed validation: {[e.message for e in result.errors]}")


class DefaultLayoutRetuneTests(unittest.TestCase):
    """_default_layout() must resolve to solo/studio and never to legacy."""

    def setUp(self) -> None:
        import server  # noqa: WPS433
        self.server = server

    def test_default_layout_base_is_solo(self) -> None:
        """With no mid+premium buckets populated, default is solo."""
        with mock.patch.object(self.server, "_load_routing_config",
                               return_value={"buckets": {}}):
            layout = self.server._default_layout()
        self.assertEqual(layout["layout"]["preset_base"], "solo")

    def test_default_layout_upgrades_to_studio(self) -> None:
        """When both local-mid and local-premium have entries, upgrade."""
        buckets = {
            "buckets": {
                "local-mid":     ["model-mid"],
                "local-premium": ["model-premium-a", "model-premium-b"],
            },
        }
        with mock.patch.object(self.server, "_load_routing_config",
                               return_value=buckets):
            layout = self.server._default_layout()
        self.assertEqual(layout["layout"]["preset_base"], "studio")

    def test_default_layout_never_returns_legacy(self) -> None:
        """Fail-closed: exceptions in routing config fall back to solo."""
        with mock.patch.object(self.server, "_load_routing_config",
                               side_effect=RuntimeError("simulated")):
            layout = self.server._default_layout()
        self.assertEqual(layout["layout"]["preset_base"], "solo")
        self.assertIn(layout["layout"]["preset_base"], self.server._ACTIVE_LAYOUTS)
        # No panel should reference a legacy `simple` or `workbench` layout.
        for panel in layout["layout"]["panels"]:
            self.assertIn(panel["type"],
                          {"chat", "visual", "vault", "pipeline", "clarification",
                           "switcher", "config"})


class DefaultBucketResolutionTests(unittest.TestCase):
    """_resolve_default_buckets honors default_bucket on layout panels."""

    def setUp(self) -> None:
        import server  # noqa: WPS433
        self.server = server

    def _sample_layout(self) -> dict:
        return {
            "layout": {
                "preset_base": "studio",
                "panels": [
                    {"id": "main", "type": "chat", "width_pct": 40,
                     "model_slot": "breadth", "is_main_feed": True,
                     "bridge_subscribe_to": None, "label": "Main Chat"},
                    {"id": "visual", "type": "visual", "width_pct": 40,
                     "model_slot": None, "is_main_feed": False,
                     "bridge_subscribe_to": "main", "label": "Visual"},
                    {"id": "sidebar", "type": "chat", "width_pct": 20,
                     "model_slot": "sidebar",
                     "default_bucket": "local-fast",
                     "is_main_feed": False, "bridge_subscribe_to": "main",
                     "label": "Sidebar"},
                ],
            },
            "theme": "default-light",
        }

    def test_default_bucket_resolves_to_bucket_entry(self) -> None:
        """Panel with default_bucket gets resolved_slot_assignment set."""
        layout = self._sample_layout()
        routing = {"buckets": {"local-fast": ["fast-a", "fast-b"]}}
        models = {"local_models": [{"id": "fast-a"}, {"id": "fast-b"}],
                  "commercial_models": []}
        with mock.patch.object(self.server, "_load_routing_config",
                               return_value=routing), \
             mock.patch.object(self.server, "load_models",
                               return_value=models), \
             mock.patch.object(self.server, "load_config",
                               return_value={"slot_assignments": {}}):
            resolved = self.server._resolve_default_buckets(layout)

        sidebar = resolved["layout"]["panels"][2]
        self.assertIn("resolved_slot_assignment", sidebar)
        self.assertEqual(sidebar["resolved_slot_assignment"]["source"], "default_bucket")
        self.assertEqual(sidebar["resolved_slot_assignment"]["model_id"], "fast-a")
        self.assertEqual(sidebar["resolved_slot_assignment"]["bucket"], "local-fast")
        # Main chat has no default_bucket — no annotation.
        self.assertNotIn("resolved_slot_assignment", resolved["layout"]["panels"][0])

    def test_explicit_slot_assignment_wins_over_default_bucket(self) -> None:
        """User-pinned slot assignments take precedence."""
        layout = self._sample_layout()
        routing = {"buckets": {"local-fast": ["fast-a"]}}
        models = {"local_models": [{"id": "fast-a"}, {"id": "user-pinned"}],
                  "commercial_models": []}
        with mock.patch.object(self.server, "_load_routing_config",
                               return_value=routing), \
             mock.patch.object(self.server, "load_models",
                               return_value=models), \
             mock.patch.object(self.server, "load_config",
                               return_value={"slot_assignments": {"sidebar": "user-pinned"}}):
            resolved = self.server._resolve_default_buckets(layout)

        sidebar = resolved["layout"]["panels"][2]
        self.assertEqual(sidebar["resolved_slot_assignment"]["source"],
                         "user_slot_assignment")
        self.assertEqual(sidebar["resolved_slot_assignment"]["model_id"],
                         "user-pinned")

    def test_empty_bucket_falls_back_gracefully(self) -> None:
        """Empty bucket → fallback annotation, does not block layout."""
        layout = self._sample_layout()
        routing = {"buckets": {"local-fast": []}}
        models = {"local_models": [{"id": "some-other-model"}],
                  "commercial_models": []}
        with mock.patch.object(self.server, "_load_routing_config",
                               return_value=routing), \
             mock.patch.object(self.server, "load_models",
                               return_value=models), \
             mock.patch.object(self.server, "load_config",
                               return_value={"slot_assignments": {}}):
            resolved = self.server._resolve_default_buckets(layout)

        sidebar = resolved["layout"]["panels"][2]
        self.assertIn("resolved_slot_assignment", sidebar)
        self.assertEqual(sidebar["resolved_slot_assignment"]["source"],
                         "empty_bucket_fallback")
        self.assertIn("fallback_reason", sidebar["resolved_slot_assignment"])
        # Layout still has 3 panels — no dropout on misconfiguration.
        self.assertEqual(len(resolved["layout"]["panels"]), 3)


class BridgeVisualBlocksTests(unittest.TestCase):
    """/api/bridge/<panel> persists ora_visual_blocks for polling consumers."""

    def setUp(self) -> None:
        import server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()
        # Reset bridge state for this panel so tests are independent.
        self.server._bridge_state.pop("e2e-bridge-panel", None)

    def test_post_and_get_roundtrip_preserves_ora_visual_blocks(self) -> None:
        envelope = _load_cld_envelope()
        payload = {
            "current_topic": "CLD request",
            "ora_visual_blocks": [{
                "envelope": envelope,
                "raw_json": json.dumps(envelope),
                "source_message_id": "main-msg-e2e",
            }],
        }
        post = self.client.post(
            "/api/bridge/e2e-bridge-panel",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(post.status_code, 200)
        self.assertIn("ok", post.get_data(as_text=True))

        got = self.client.get("/api/bridge/e2e-bridge-panel")
        self.assertEqual(got.status_code, 200)
        cached = json.loads(got.get_data(as_text=True))
        self.assertIn("ora_visual_blocks", cached)
        self.assertEqual(len(cached["ora_visual_blocks"]), 1)
        self.assertEqual(
            cached["ora_visual_blocks"][0]["envelope"]["type"],
            "causal_loop_diagram",
        )

    def test_bridge_merge_preserves_prior_ora_visual_blocks(self) -> None:
        """A POST missing ora_visual_blocks leaves the last ones in place."""
        envelope = _load_cld_envelope()
        # First POST: topic + blocks
        self.client.post(
            "/api/bridge/e2e-bridge-panel",
            data=json.dumps({
                "current_topic": "first",
                "ora_visual_blocks": [{"envelope": envelope, "raw_json": "{}",
                                       "source_message_id": "a"}],
            }),
            headers={"Content-Type": "application/json"},
        )
        # Second POST: topic only (no blocks)
        self.client.post(
            "/api/bridge/e2e-bridge-panel",
            data=json.dumps({"current_topic": "second"}),
            headers={"Content-Type": "application/json"},
        )
        got = self.client.get("/api/bridge/e2e-bridge-panel")
        cached = json.loads(got.get_data(as_text=True))
        self.assertEqual(cached["current_topic"], "second")
        self.assertIn("ora_visual_blocks", cached)
        self.assertEqual(len(cached["ora_visual_blocks"]), 1)


if __name__ == "__main__":
    unittest.main()
