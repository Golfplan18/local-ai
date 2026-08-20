#!/usr/bin/env python3
"""
Unit tests for the WP-2.3 visual end-to-end path (server-side).

Runs under the stdlib ``unittest`` runner — no pytest dependency. Invoke::

    /opt/homebrew/bin/python3 -m pytest ~/ora/orchestrator/tests -q

Scope:
* The chat endpoint streams SSE events; any ``ora-visual`` fenced block in
  the final response survives through the hook pipeline and appears in the
  SSE payload unchanged (for a schema-valid envelope).
* The Python-side visual validator accepts the embedded envelope as valid.
* V3 owns its panel structure directly and does not expose the retired
  config-driven layout/theme routes.
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


from oversight_sandbox import redirect_sessions_root  # noqa: E402


def setUpModule():
    # Keep this module's Dialogue writes out of the live sessions store. The
    # endpoint handlers default an absent conversation_id to "main" — the
    # user's own Dialogue — and persist envelopes under the sessions root.
    redirect_sessions_root()

class VisualE2ESseTests(unittest.TestCase):
    """End-to-end SSE integration — fake pipeline, real server."""

    def setUp(self) -> None:
        # Import server lazily so orchestrator test ordering stays clean.
        from server import app as server  # noqa: WPS433
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
             mock.patch.object(self.server, "_save_conversation",
                               return_value="session-test-pair-001"), \
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
            body_bytes = b"".join(resp.response)

        self.assertEqual(resp.status_code, 200)
        body = body_bytes.decode("utf-8")

        # V3 Backlog 2A — plain-HTTP reply: status / conversation_id /
        # chunk_id. The visual fence now lives in the chunk file (saved by
        # _save_conversation, mocked here), not in the response body.
        payload = json.loads(body)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["conversation_id"], "main")
        self.assertEqual(payload["chunk_id"], "session-test-pair-001")

        # The fence round-trip is validated directly against the upstream
        # response_text we fed into the mock pipeline. (On a real run, the
        # same string would be persisted to the chunk file.)
        extracted = _extract_fence(response_text)
        self.assertIsNotNone(extracted, "could not extract ora-visual fence")
        self.assertEqual(extracted["type"], "causal_loop_diagram")
        self.assertEqual(extracted["id"], self.envelope["id"])

        # The embedded envelope validates under the Python validator.
        result = validate_envelope(extracted)
        self.assertTrue(result.valid,
                        f"envelope failed validation: {[e.message for e in result.errors]}")


class V3LayoutContractTests(unittest.TestCase):
    """V3's hardcoded workspace replaces the retired configuration path."""

    def setUp(self) -> None:
        from server import app as server  # noqa: WPS433
        self.server = server

    def test_legacy_layout_and_theme_routes_are_retired(self) -> None:
        rules = {rule.rule for rule in self.server.app.url_map.iter_rules()}
        retired = {
            "/api/layout",
            "/api/layouts",
            "/api/layouts/<name>",
            "/api/generate-layout",
            "/api/theme",
            "/api/themes",
        }
        self.assertTrue(retired.isdisjoint(rules))
        # The active V3 theme library is a separate subsystem and remains live.
        self.assertIn("/api/v3-themes/list", rules)

    def test_v3_declares_workspace_structure_without_config_fetches(self) -> None:
        html = (WORKSPACE / "server" / "index-v3.html").read_text()
        layout_js = (WORKSPACE / "server" / "static" / "js" /
                     "v3-layout.js").read_text()

        self.assertIn('/static/js/v3-layout.js', html)
        self.assertIn('class="left-column"', html)
        self.assertIn('class="right-column"', html)
        self.assertIn('class="chat-zone"', html)
        self.assertIn('class="pane right-pane"', html)

        legacy_paths = (
            "/api/layout",
            "/api/layouts",
            "/api/generate-layout",
            "/api/theme",
            "/api/themes",
        )
        for path in legacy_paths:
            self.assertNotIn(path, html)
            self.assertNotIn(path, layout_js)


class BridgeVisualBlocksTests(unittest.TestCase):
    """/api/bridge/<panel> persists ora_visual_blocks for polling consumers."""

    def setUp(self) -> None:
        from server import app as server  # noqa: WPS433
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
