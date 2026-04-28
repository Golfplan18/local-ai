#!/usr/bin/env python3
"""
WP-3.3 — merged-input pipeline unit tests (server-side).

Runs under stdlib ``unittest`` — no pytest dependency. Invoke::

    /opt/homebrew/bin/python3 -m unittest discover -s ~/ora/orchestrator/tests -v

Scope:
* The ``/chat/multipart`` endpoint accepts multipart payloads with text +
  spatial_representation + image and forwards all three into the shared
  pipeline helper (``_invoke_pipeline``).
* Invalid spatial_representation → 400 with structured error details.
* Valid spatial_representation → pipeline's context_pkg carries the
  parsed JSON under ``spatial_representation`` and the serialized text
  rendering lands in the system prompt via ``build_system_prompt_for_gear``.
* Uploaded images land under ``~/ora/sessions/<conversation_id>/uploads/``.
* Missing image and missing spatial_representation → falls back to the
  text-only path without breaking the existing /chat contract.

The orchestrator pipeline is mocked via ``unittest.mock.patch`` and
``threading.Thread`` is stubbed the same way ``test_visual_e2e.py`` does —
tests are fast and model-free.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import shutil
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


def _valid_spatial_rep() -> dict:
    """A minimal schema-conformant spatial_representation fixture."""
    return {
        "entities": [
            {"id": "e-A", "position": [0.1, 0.2], "label": "Alpha"},
            {"id": "e-B", "position": [0.4, 0.2], "label": "Beta"},
            {"id": "e-C", "position": [0.7, 0.2], "label": "Gamma"},
        ],
        "relationships": [
            {"source": "e-A", "target": "e-B", "type": "causal"},
            {"source": "e-B", "target": "e-C", "type": "associative"},
        ],
        "clusters": [
            {"members": ["e-A", "e-B"], "label": "left-pair"},
        ],
    }


def _invalid_spatial_rep() -> dict:
    """Missing required ``label`` on an entity."""
    return {
        "entities": [
            {"id": "e-A", "position": [0.1, 0.2]},
        ],
    }


class ValidateSpatialRepresentationTests(unittest.TestCase):
    """Unit tests for ``visual_validator.validate_spatial_representation``."""

    def test_valid_spatial_rep_passes(self) -> None:
        from visual_validator import validate_spatial_representation
        result = validate_spatial_representation(_valid_spatial_rep())
        self.assertTrue(result.valid,
                        f"unexpected errors: {[e.message for e in result.errors]}")
        self.assertEqual(len(result.errors), 0)

    def test_invalid_spatial_rep_reports_schema_error(self) -> None:
        from visual_validator import validate_spatial_representation
        result = validate_spatial_representation(_invalid_spatial_rep())
        self.assertFalse(result.valid)
        self.assertTrue(any(e.code == "E_SCHEMA_INVALID" for e in result.errors))

    def test_unresolved_relationship_source_rejected(self) -> None:
        """Cross-check: source id must resolve to an entity id."""
        from visual_validator import validate_spatial_representation
        sr = _valid_spatial_rep()
        sr["relationships"].append({
            "source": "e-NONEXISTENT", "target": "e-B", "type": "causal",
        })
        result = validate_spatial_representation(sr)
        self.assertFalse(result.valid)
        self.assertTrue(any(e.code == "E_UNRESOLVED_REF" for e in result.errors))

    def test_cluster_member_must_resolve_to_entity(self) -> None:
        from visual_validator import validate_spatial_representation
        sr = _valid_spatial_rep()
        sr["clusters"].append({"members": ["e-A", "ghost"], "label": "mixed"})
        result = validate_spatial_representation(sr)
        self.assertFalse(result.valid)
        self.assertTrue(any(e.code == "E_UNRESOLVED_REF" for e in result.errors))

    def test_non_dict_input_rejected(self) -> None:
        from visual_validator import validate_spatial_representation
        result = validate_spatial_representation("not-a-dict")  # type: ignore[arg-type]
        self.assertFalse(result.valid)


class SerializeSpatialRepresentationToTextTests(unittest.TestCase):
    """Unit tests for the text serialization format used by boot.py."""

    def test_format_contains_entity_line(self) -> None:
        from visual_validator import serialize_spatial_representation_to_text
        out = serialize_spatial_representation_to_text(_valid_spatial_rep())
        # Entity: "<id> at [x, y]: <label>"
        self.assertIn("e-A", out)
        self.assertIn("Alpha", out)
        self.assertIn("at [0.100, 0.200]", out)
        # Delimiter fences
        self.assertIn("=== USER SPATIAL INPUT ===", out)
        self.assertIn("=== END SPATIAL INPUT ===", out)

    def test_format_contains_relationship_arrow(self) -> None:
        from visual_validator import serialize_spatial_representation_to_text
        out = serialize_spatial_representation_to_text(_valid_spatial_rep())
        self.assertIn("e-A --(causal)--> e-B", out)
        self.assertIn("e-B --(associative)--> e-C", out)

    def test_format_contains_cluster_line(self) -> None:
        from visual_validator import serialize_spatial_representation_to_text
        out = serialize_spatial_representation_to_text(_valid_spatial_rep())
        self.assertIn('cluster "left-pair": e-A, e-B', out)

    def test_empty_input_returns_empty_string(self) -> None:
        from visual_validator import serialize_spatial_representation_to_text
        self.assertEqual(serialize_spatial_representation_to_text({}), "")
        self.assertEqual(serialize_spatial_representation_to_text(None), "")  # type: ignore[arg-type]


class MultipartEndpointIntegrationTests(unittest.TestCase):
    """End-to-end multipart endpoint integration — fake pipeline, real server."""

    def setUp(self) -> None:
        import server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()
        # Force uploads to a temp directory so tests don't pollute the real vault.
        self._tmp = tempfile.mkdtemp(prefix="ora-multipart-test-")
        self._orig_uploads_root = server.VISUAL_UPLOADS_ROOT
        server.VISUAL_UPLOADS_ROOT = self._tmp

    def tearDown(self) -> None:
        self.server.VISUAL_UPLOADS_ROOT = self._orig_uploads_root
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _mock_agentic_stream(self, response_text: str, captured: dict):
        """Return a fake agentic_loop_stream that records its kwargs."""
        server = self.server

        def fake_stream(clean_input, history, use_pipeline=True,
                        panel_id="main", images=None, extra_context=None, **kwargs):
            captured["clean_input"] = clean_input
            captured["panel_id"] = panel_id
            captured["extra_context"] = extra_context
            captured["images"] = images
            yield server._sse("pipeline_stage", stage="step1_cleanup",
                               label="Cleaning prompt…", mode="systems_dynamics", gear=3)
            yield server._sse("pipeline_stage", stage="complete", gear=3)
            yield server._sse("response", text=response_text)

        return fake_stream

    def test_multipart_valid_spatial_reaches_pipeline(self) -> None:
        """POST with text + spatial_representation → pipeline sees both."""
        captured = {}
        data = {
            "message": "Analyze this diagram.",
            "conversation_id": "e2e-convo-1",
            "panel_id": "main",
            "spatial_representation": json.dumps(_valid_spatial_rep()),
        }

        with mock.patch.object(self.server, "agentic_loop_stream",
                               side_effect=self._mock_agentic_stream("ok", captured)), \
             mock.patch.object(self.server.threading, "Thread", _NoopThread):
            resp = self.client.post("/chat/multipart", data=data,
                                    content_type="multipart/form-data")
            # Drain the SSE stream inside the mock scope so the generator runs.
            b"".join(resp.response)

        self.assertEqual(resp.status_code, 200)
        # The shared streamer must have been called with extra_context carrying
        # the parsed spatial_representation.
        self.assertIsNotNone(captured.get("extra_context"))
        self.assertIn("spatial_representation", captured["extra_context"])
        spatial = captured["extra_context"]["spatial_representation"]
        self.assertEqual(len(spatial["entities"]), 3)
        # The cleaned user input survived.
        self.assertIn("Analyze this diagram", captured["clean_input"])

    def test_multipart_invalid_spatial_rejected_with_400(self) -> None:
        """Invalid spatial_representation → 400 with structured errors."""
        data = {
            "message": "oops",
            "conversation_id": "e2e-convo-2",
            "spatial_representation": json.dumps(_invalid_spatial_rep()),
        }

        with mock.patch.object(self.server.threading, "Thread", _NoopThread):
            resp = self.client.post("/chat/multipart", data=data,
                                    content_type="multipart/form-data")

        self.assertEqual(resp.status_code, 400)
        body = json.loads(resp.get_data(as_text=True))
        self.assertIn("error", body)
        self.assertIn("errors", body)
        self.assertTrue(any(e["code"] == "E_SCHEMA_INVALID" for e in body["errors"]))

    def test_multipart_malformed_spatial_json_rejected_with_400(self) -> None:
        """Malformed JSON string → 400 with parse-error detail."""
        data = {
            "message": "oops",
            "conversation_id": "e2e-convo-malformed",
            "spatial_representation": "{not json at all",
        }

        with mock.patch.object(self.server.threading, "Thread", _NoopThread):
            resp = self.client.post("/chat/multipart", data=data,
                                    content_type="multipart/form-data")

        self.assertEqual(resp.status_code, 400)
        body = json.loads(resp.get_data(as_text=True))
        self.assertIn("invalid spatial_representation JSON", body["error"])

    def test_multipart_image_upload_lands_on_disk(self) -> None:
        """Image uploaded → file appears under VISUAL_UPLOADS_ROOT/<conv>/uploads/."""
        captured = {}
        image_bytes = b"\x89PNG\r\n\x1a\nFAKE-PNG-PAYLOAD"
        data = {
            "message": "Here is a sketch.",
            "conversation_id": "e2e-convo-img",
            "spatial_representation": json.dumps(_valid_spatial_rep()),
            "image": (io.BytesIO(image_bytes), "sketch.png"),
        }

        with mock.patch.object(self.server, "agentic_loop_stream",
                               side_effect=self._mock_agentic_stream("ok", captured)), \
             mock.patch.object(self.server.threading, "Thread", _NoopThread):
            resp = self.client.post("/chat/multipart", data=data,
                                    content_type="multipart/form-data")
            b"".join(resp.response)

        self.assertEqual(resp.status_code, 200)
        # The saved file must live under the configured uploads root.
        conv_dir = os.path.join(self._tmp, "e2e-convo-img", "uploads")
        self.assertTrue(os.path.isdir(conv_dir),
                        f"uploads dir missing: {conv_dir}")
        saved_files = os.listdir(conv_dir)
        self.assertEqual(len(saved_files), 1, f"files={saved_files}")
        self.assertTrue(saved_files[0].endswith("sketch.png"),
                        f"unexpected filename: {saved_files[0]}")
        # The pipeline's extra_context carries the image path.
        self.assertIn("image_path", captured["extra_context"])
        self.assertTrue(
            captured["extra_context"]["image_path"].startswith(conv_dir),
            f"image_path={captured['extra_context']['image_path']}",
        )
        # Bytes landed on disk unchanged.
        with open(captured["extra_context"]["image_path"], "rb") as fh:
            self.assertEqual(fh.read(), image_bytes)

    def test_multipart_missing_message_returns_400(self) -> None:
        """Empty message field → 400."""
        data = {
            "message": "",
            "conversation_id": "e2e-convo-empty",
        }
        with mock.patch.object(self.server.threading, "Thread", _NoopThread):
            resp = self.client.post("/chat/multipart", data=data,
                                    content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 400)

    def test_multipart_no_extras_falls_back_to_text_only(self) -> None:
        """Missing image + missing spatial_representation → text-only path works.

        The pipeline still sees the text; extra_context is either None or an
        empty dict-equivalent (no spatial_representation, no image_path keys).
        """
        captured = {}
        data = {
            "message": "Just text, please.",
            "conversation_id": "e2e-convo-textonly",
        }

        with mock.patch.object(self.server, "agentic_loop_stream",
                               side_effect=self._mock_agentic_stream("ok", captured)), \
             mock.patch.object(self.server.threading, "Thread", _NoopThread):
            resp = self.client.post("/chat/multipart", data=data,
                                    content_type="multipart/form-data")
            b"".join(resp.response)

        self.assertEqual(resp.status_code, 200)
        # extra_context is either None or carries no merged-input keys.
        ec = captured.get("extra_context")
        self.assertTrue(
            ec is None or (
                "spatial_representation" not in (ec or {})
                and "image_path" not in (ec or {})
            ),
            f"unexpected extra_context: {ec}",
        )
        # The cleaned text reached the pipeline.
        self.assertIn("Just text", captured["clean_input"])


class BuildSystemPromptIncludesSpatialTests(unittest.TestCase):
    """boot.build_system_prompt_for_gear renders spatial_representation to text
    and includes the image path stub when those keys are set on context_pkg."""

    def setUp(self) -> None:
        # Import lazily to respect test ordering.
        from boot import build_system_prompt_for_gear  # noqa: WPS433
        self.build = build_system_prompt_for_gear

    def _context_pkg(self, **extras) -> dict:
        # A minimal context_pkg shape the builder consumes. mode_text can be
        # empty — we're asserting on the merged-input sections only.
        pkg = {
            "mode_text": "# Fake Mode\n",
            "mode_name": "systems_dynamics",
            "conversation_rag": "",
            "concept_rag": "",
            "relationship_rag": "",
            "rag_utilization": "",
        }
        pkg.update(extras)
        return pkg

    def test_spatial_representation_serialized_into_prompt(self) -> None:
        pkg = self._context_pkg(spatial_representation=_valid_spatial_rep())
        prompt = self.build(pkg, slot="breadth")
        # Fences
        self.assertIn("=== USER SPATIAL INPUT ===", prompt)
        self.assertIn("=== END SPATIAL INPUT ===", prompt)
        # Entity line
        self.assertIn("e-A at [0.100, 0.200]: Alpha", prompt)
        # Relationship line
        self.assertIn("e-A --(causal)--> e-B", prompt)

    def test_image_path_stub_injected(self) -> None:
        pkg = self._context_pkg(image_path="/abs/path/to/image.png")
        prompt = self.build(pkg, slot="breadth")
        self.assertIn("=== USER IMAGE ===", prompt)
        self.assertIn("/abs/path/to/image.png", prompt)
        self.assertIn("=== END IMAGE ===", prompt)

    def test_no_merged_input_leaves_prompt_unchanged(self) -> None:
        """Text-only pipelines: no spatial fences appear."""
        pkg = self._context_pkg()  # no merged-input keys
        prompt = self.build(pkg, slot="breadth")
        self.assertNotIn("=== USER SPATIAL INPUT ===", prompt)
        self.assertNotIn("=== USER IMAGE ===", prompt)


class ChatEndpointBackwardCompatTests(unittest.TestCase):
    """The original /chat endpoint must continue to behave as before."""

    def setUp(self) -> None:
        import server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()

    def test_json_chat_endpoint_still_streams_response(self) -> None:
        """Simple JSON POST → SSE response event lands as before."""
        captured = {}

        def fake_stream(clean_input, history, use_pipeline=True,
                        panel_id="main", images=None, extra_context=None, **kwargs):
            captured["extra_context"] = extra_context
            yield self.server._sse("pipeline_stage", stage="complete", gear=3)
            yield self.server._sse("response", text="text-only reply")

        with mock.patch.object(self.server, "agentic_loop_stream",
                               side_effect=fake_stream), \
             mock.patch.object(self.server.threading, "Thread", _NoopThread):
            resp = self.client.post(
                "/chat",
                data=json.dumps({
                    "message": "hi",
                    "history": [],
                    "panel_id": "main",
                    "is_main_feed": True,
                }),
                headers={"Content-Type": "application/json"},
            )
            body = b"".join(resp.response).decode("utf-8")

        self.assertEqual(resp.status_code, 200)
        self.assertIn('"type": "response"', body)
        self.assertIn("text-only reply", body)
        # /chat must not thread any merged-input extras.
        self.assertIsNone(captured.get("extra_context"))


if __name__ == "__main__":
    unittest.main()
