#!/usr/bin/env python3
"""
WP-3.3 — merged-input pipeline unit tests (server-side).

Runs under stdlib ``unittest`` — no pytest dependency. Invoke::

    /opt/homebrew/bin/python3 -m pytest ~/ora/orchestrator/tests -q

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
import base64
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


from oversight_sandbox import (  # noqa: E402
    redirect_active_project,
    redirect_sessions_root,
)


def setUpModule():
    # Keep this module's Dialogue writes out of the live sessions store. The
    # endpoint handlers default an absent conversation_id to "main" — the
    # user's own Dialogue — and persist envelopes under the sessions root.
    redirect_sessions_root()
    # And keep its verdict off the live project registry: the chat handler
    # attaches the active project's model-profile locks, so a registered
    # project on the developer's machine leaks into the request context.
    redirect_active_project()

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
        from server import app as server  # noqa: WPS433
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

    def test_multipart_threads_image_preference_and_provider_override(self) -> None:
        captured = {}
        data = {
            "message": "Create an image of the dependency.",
            "conversation_id": "e2e-image-preference",
            "manual_visual_type": "image",
            "image_provider_override": "openai:gpt-image-1",
        }
        with mock.patch.object(
            self.server, "agentic_loop_stream",
            side_effect=self._mock_agentic_stream("analytical prose", captured),
        ), mock.patch.object(self.server.threading, "Thread", _NoopThread):
            resp = self.client.post(
                "/chat/multipart", data=data,
                content_type="multipart/form-data",
            )
            b"".join(resp.response)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(captured["extra_context"]["visual_kind"], "image")
        self.assertEqual(
            captured["extra_context"]["image_provider_override"],
            "openai:gpt-image-1",
        )

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


class VisualCheckpointAtomicityTests(unittest.TestCase):
    """Focused checkpoint identity, commit-marker, and rollback behavior."""

    def setUp(self) -> None:
        from server import app as server
        self.server = server
        self.client = server.app.test_client()
        self._tmp = tempfile.mkdtemp(prefix="ora-visual-checkpoint-")
        self._old_canvas_root = server.CANVAS_ROOT
        self._old_uploads_root = server.VISUAL_UPLOADS_ROOT
        self._old_pending = server.CONVERSATIONS_PENDING
        self._old_processed = server.CONVERSATIONS_PROCESSED
        server.CANVAS_ROOT = self._tmp
        server.VISUAL_UPLOADS_ROOT = self._tmp
        server.CONVERSATIONS_PENDING = os.path.join(self._tmp, "pending")
        server.CONVERSATIONS_PROCESSED = os.path.join(self._tmp, "processed")
        self.scene = json.dumps({
            "type": "excalidraw",
            "version": 2,
            "source": "local",
            "elements": [{"id": "editable-rectangle", "type": "rectangle"}],
            "appState": {"viewBackgroundColor": "#ffffff"},
            "files": {},
        }).encode()
        self.png = b"\x89PNG\r\n\x1a\ncanonical-preview"

    def tearDown(self) -> None:
        self.server.CANVAS_ROOT = self._old_canvas_root
        self.server.VISUAL_UPLOADS_ROOT = self._old_uploads_root
        self.server.CONVERSATIONS_PENDING = self._old_pending
        self.server.CONVERSATIONS_PROCESSED = self._old_processed
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _visual_form(self, conversation_id: str) -> dict:
        return {
            "message": "Use this exact visual.",
            "conversation_id": conversation_id,
            "panel_id": conversation_id,
            "visual_editor": "excalidraw",
            "visual_native": (io.BytesIO(self.scene), "scene.excalidraw"),
            "canvas_preview_png": (io.BytesIO(self.png), "preview.png"),
            "exhibits_submission_intent": "explicit_send",
        }

    def test_pending_marker_records_both_paths_and_checkpoint(self) -> None:
        captured = {}

        def invoke(*args, **kwargs):
            captured["extra_context"] = kwargs.get("extra_context")
            captured["submission_id"] = kwargs.get("submission_id")
            captured["images"] = kwargs.get("images")
            return json.dumps({"status": "ok"})

        with mock.patch.object(self.server, "_invoke_pipeline", side_effect=invoke), \
             mock.patch.object(
                 self.server, "_ensure_artifact_conversation_envelope",
                 return_value=("", False),
             ):
            response = self.client.post(
                "/chat/multipart",
                data=self._visual_form("checkpoint-atomic-success"),
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        submission_id = captured["submission_id"]
        marker = Path(self.server.CONVERSATIONS_PENDING, submission_id + ".json")
        payload = json.loads(marker.read_text(encoding="utf-8"))
        self.assertEqual(payload["visual_checkpoint_id"], submission_id)
        self.assertTrue(Path(payload["visual_native_path"]).is_file())
        self.assertTrue(Path(payload["canvas_preview_path"]).is_file())
        self.assertEqual(
            captured["extra_context"]["visual_checkpoint_id"], submission_id,
        )
        self.assertEqual(
            captured["extra_context"]["image_path"], payload["canvas_preview_path"],
        )
        self.assertEqual(
            [image["source"] for image in captured["images"]],
            ["v3_canvas_preview"],
        )

    def test_drawing_only_submit_reaches_pipeline_with_empty_message(self) -> None:
        captured = {}

        def invoke(*args, **kwargs):
            captured["message"] = args[0]
            captured["extra_context"] = kwargs.get("extra_context")
            return json.dumps({"status": "ok"})

        form = self._visual_form("checkpoint-drawing-only")
        form["message"] = ""
        with mock.patch.object(self.server, "_invoke_pipeline", side_effect=invoke), \
             mock.patch.object(
                 self.server, "_ensure_artifact_conversation_envelope",
                 return_value=("", False),
             ):
            response = self.client.post(
                "/chat/multipart", data=form,
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["message"], "")
        self.assertIsNotNone(captured["extra_context"]["visual_checkpoint_id"])

    def test_pipeline_guard_allows_empty_text_only_for_validated_checkpoint(self) -> None:
        with mock.patch.object(
            self.server, "parse_user_command",
            side_effect=RuntimeError("passed content guard"),
        ):
            with self.assertRaisesRegex(RuntimeError, "passed content guard"):
                self.server._invoke_pipeline_unlocked(
                    "", [], "checkpoint-guard-visual", False,
                    extra_context={
                        "visual_checkpoint_id": "20260813T123456123456Z-deadbeef",
                    },
                )

        response, status = self.server._invoke_pipeline_unlocked(
            "", [], "checkpoint-guard-empty", False,
        )
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(response)["error"], "empty message")

    def test_empty_scene_does_not_authorize_empty_message(self) -> None:
        invoked = mock.Mock()
        empty_scene = json.dumps({
            "type": "excalidraw",
            "version": 2,
            "source": "local",
            "elements": [],
            "appState": {"viewBackgroundColor": "#ffffff"},
            "files": {},
        }).encode()
        form = self._visual_form("checkpoint-empty-scene")
        form["message"] = ""
        form["visual_native"] = (io.BytesIO(empty_scene), "scene.excalidraw")
        with mock.patch.object(self.server, "_invoke_pipeline", invoked), \
             mock.patch.object(
                 self.server, "_ensure_artifact_conversation_envelope",
                 return_value=("", False),
             ):
            response = self.client.post(
                "/chat/multipart", data=form,
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 400)
        invoked.assert_not_called()

    def test_attachment_is_removed_when_visual_checkpoint_is_invalid(self) -> None:
        invoked = mock.Mock()
        form = self._visual_form("checkpoint-invalid-with-attachment")
        form["image"] = (io.BytesIO(b"ordinary-attachment"), "ordinary.png")
        form["visual_native"] = (io.BytesIO(b"not-an-excalidraw-scene"), "scene.excalidraw")
        with mock.patch.object(self.server, "_invoke_pipeline", invoked), \
             mock.patch.object(
                 self.server, "_ensure_artifact_conversation_envelope",
                 return_value=("", False),
             ):
            response = self.client.post(
                "/chat/multipart", data=form,
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 400)
        invoked.assert_not_called()
        self.assertFalse([
            path for path in Path(self._tmp).rglob("*") if path.is_file()
        ])

    def test_attachment_and_canvas_preview_both_reach_model_input(self) -> None:
        captured = {}
        attachment = b"\x89PNG\r\n\x1a\nordinary-attachment"

        def invoke(*args, **kwargs):
            captured["images"] = kwargs.get("images")
            return json.dumps({"status": "ok"})

        form = self._visual_form("checkpoint-two-images")
        form["image"] = (io.BytesIO(attachment), "ordinary.png")
        with mock.patch.object(self.server, "_invoke_pipeline", side_effect=invoke), \
             mock.patch.object(
                 self.server, "_ensure_artifact_conversation_envelope",
                 return_value=("", False),
             ):
            response = self.client.post(
                "/chat/multipart", data=form,
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(captured["images"]), 2)
        self.assertEqual(
            [base64.b64decode(image["base64"]) for image in captured["images"]],
            [attachment, self.png],
        )
        self.assertEqual(
            [image["source"] for image in captured["images"]],
            ["upload", "v3_canvas_preview"],
        )

    def test_pending_marker_failure_removes_checkpoint_and_skips_model(self) -> None:
        invoked = mock.Mock()
        form = self._visual_form("checkpoint-atomic-failure")
        form["image"] = (io.BytesIO(b"ordinary-attachment"), "ordinary.png")
        with mock.patch.object(self.server, "_invoke_pipeline", invoked), \
             mock.patch.object(self.server, "_log_pending_submission", return_value=""), \
             mock.patch.object(
                 self.server, "_ensure_artifact_conversation_envelope",
                 return_value=("", False),
             ):
            response = self.client.post(
                "/chat/multipart",
                data=form,
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 500)
        invoked.assert_not_called()
        canvas = Path(self._tmp, "checkpoint-atomic-failure", "canvas")
        self.assertFalse(list(canvas.glob("*.excalidraw")))
        self.assertFalse(list(canvas.glob("*.preview.png")))
        self.assertFalse([
            path for path in Path(self._tmp, "checkpoint-atomic-failure").rglob("*")
            if path.is_file()
        ])

    def test_pending_marker_failure_removes_separate_legacy_preview(self) -> None:
        invoked = mock.Mock()
        preview_data_url = "data:image/png;base64," + base64.b64encode(
            self.png
        ).decode("ascii")
        with mock.patch.object(self.server, "_invoke_pipeline", invoked), \
             mock.patch.object(self.server, "_log_pending_submission", return_value=""), \
             mock.patch.object(
                 self.server, "_ensure_artifact_conversation_envelope",
                 return_value=("", False),
             ):
            response = self.client.post("/chat/multipart", data={
                "message": "Legacy preview must roll back.",
                "conversation_id": "checkpoint-legacy-preview-failure",
                "panel_id": "checkpoint-legacy-preview-failure",
                "canvas_preview_png_data_url": preview_data_url,
            }, content_type="multipart/form-data")

        self.assertEqual(response.status_code, 500)
        invoked.assert_not_called()
        self.assertFalse([
            path for path in Path(
                self._tmp, "checkpoint-legacy-preview-failure"
            ).rglob("*") if path.is_file()
        ])

    def test_exact_checkpoint_load_ignores_newer_autosave(self) -> None:
        checkpoint_id = "20260813T123456123456Z-deadbeef"
        conversation_id = "checkpoint-exact-load"
        with mock.patch.object(
            self.server, "_canonical_live_conversation_id",
            side_effect=lambda value: value,
        ):
            self.server._write_visual_checkpoint(
                conversation_id, checkpoint_id, "excalidraw", self.scene, self.png,
            )
        canvas = Path(self._tmp, conversation_id, "canvas")
        (canvas / "20990101-000000-000000.ora-canvas").write_bytes(b"newer autosave")
        response = self.client.get(
            f"/api/canvas/load/{conversation_id}?checkpoint={checkpoint_id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Ora-Visual-Editor"], "excalidraw")
        self.assertEqual(response.data, self.scene)

    def test_private_child_retry_copies_parent_checkpoint_under_child_id(self) -> None:
        parent_id = "checkpoint-retry-parent"
        child_id = "checkpoint-retry-private"
        source_id = "20260813T123456123456Z-deadbeef"
        with mock.patch.object(
            self.server, "_canonical_live_conversation_id",
            side_effect=lambda value: value,
        ):
            self.server._write_visual_checkpoint(
                parent_id, source_id, "excalidraw", self.scene, self.png,
            )
        captured = {}

        def invoke(*args, **kwargs):
            captured["extra_context"] = kwargs.get("extra_context")
            captured["submission_id"] = kwargs.get("submission_id")
            return json.dumps({"status": "ok"})

        form = {
            "message": "Retry this private visual.",
            "conversation_id": child_id,
            "panel_id": child_id,
            "tag": "private",
            "retry_visual_checkpoint_id": source_id,
            "retry_visual_source_conversation_id": parent_id,
            "exhibits_submission_intent": "explicit_send",
        }
        with mock.patch.object(
            self.server, "_canonical_live_conversation_id",
            side_effect=lambda value: value,
        ), mock.patch(
            "conversation_memory.load_conversation_json",
            return_value={"parent_conversation_id": parent_id},
        ), mock.patch.object(
            self.server, "_invoke_pipeline", side_effect=invoke,
        ), mock.patch.object(
            self.server, "_ensure_artifact_conversation_envelope",
            return_value=("private", False),
        ):
            response = self.client.post(
                "/chat/multipart", data=form,
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        child_checkpoint_id = captured["submission_id"]
        self.assertNotEqual(child_checkpoint_id, source_id)
        child_canvas = Path(self._tmp, child_id, "canvas")
        self.assertEqual(
            (child_canvas / f"{child_checkpoint_id}.excalidraw").read_bytes(),
            self.scene,
        )
        self.assertEqual(
            (child_canvas / f"{child_checkpoint_id}.preview.png").read_bytes(),
            self.png,
        )
        self.assertEqual(
            captured["extra_context"]["visual_checkpoint_id"],
            child_checkpoint_id,
        )
        self.assertEqual(
            captured["extra_context"]["image_path"],
            str(child_canvas / f"{child_checkpoint_id}.preview.png"),
        )
        self.assertTrue(
            Path(self._tmp, parent_id, "canvas", f"{source_id}.excalidraw").is_file()
        )
        marker = json.loads(Path(
            self.server.CONVERSATIONS_PENDING,
            child_checkpoint_id + ".json",
        ).read_text(encoding="utf-8"))
        self.assertEqual(marker["visual_checkpoint_id"], child_checkpoint_id)
        self.assertIn(f"/{child_id}/canvas/", marker["visual_native_path"])
        self.assertIn(f"/{child_id}/canvas/", marker["canvas_preview_path"])

    def test_private_child_retry_copy_failure_skips_model_and_cleans_pair(self) -> None:
        parent_id = "checkpoint-retry-fail-parent"
        child_id = "checkpoint-retry-fail-child"
        source_id = "20260813T123456123456Z-deadbeef"
        with mock.patch.object(
            self.server, "_canonical_live_conversation_id",
            side_effect=lambda value: value,
        ):
            self.server._write_visual_checkpoint(
                parent_id, source_id, "excalidraw", self.scene, self.png,
            )
        invoked = mock.Mock()
        original_atomic = self.server.rp.atomic_write_bytes
        writes = 0

        def fail_second(path, payload, **kwargs):
            nonlocal writes
            writes += 1
            if writes == 2:
                raise OSError("preview copy failed")
            return original_atomic(path, payload, **kwargs)

        with mock.patch.object(
            self.server, "_canonical_live_conversation_id",
            side_effect=lambda value: value,
        ), mock.patch(
            "conversation_memory.load_conversation_json",
            return_value={"parent_conversation_id": parent_id},
        ), mock.patch.object(
            self.server.rp, "atomic_write_bytes", side_effect=fail_second,
        ), mock.patch.object(self.server, "_invoke_pipeline", invoked), \
             mock.patch.object(
                 self.server, "_ensure_artifact_conversation_envelope",
                 return_value=("private", False),
             ):
            response = self.client.post("/chat/multipart", data={
                "message": "Retry this private visual.",
                "conversation_id": child_id,
                "panel_id": child_id,
                "tag": "private",
                "retry_visual_checkpoint_id": source_id,
                "retry_visual_source_conversation_id": parent_id,
                "exhibits_submission_intent": "explicit_send",
            }, content_type="multipart/form-data")

        self.assertEqual(response.status_code, 500)
        invoked.assert_not_called()
        child_canvas = Path(self._tmp, child_id, "canvas")
        self.assertFalse(list(child_canvas.glob("*.excalidraw")))
        self.assertFalse(list(child_canvas.glob("*.preview.png")))

    def test_retry_lookup_carries_validated_source_checkpoint_identity(self) -> None:
        checkpoint_id = "20260813T123456123456Z-deadbeef"
        with mock.patch(
            "conversation_memory.load_conversation_json",
            return_value={
                "tag": "",
                "messages": [{
                    "role": "user",
                    "content": "Retry this visual.",
                    "visual_checkpoint_id": checkpoint_id,
                }],
            },
        ):
            response = self.client.post(
                "/api/conversation/retry-visual-source/retry"
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.data)
        self.assertEqual(payload["visual_checkpoint_id"], checkpoint_id)
        self.assertEqual(
            payload["visual_checkpoint_source_conversation_id"],
            "retry-visual-source",
        )


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
        from server import app as server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()

    def test_json_chat_endpoint_returns_plain_http(self) -> None:
        """V3 Backlog 2A — /chat returns plain JSON {status, conversation_id,
        chunk_id} after running the pipeline synchronously. No SSE frames.
        """
        captured = {}

        def fake_stream(clean_input, history, use_pipeline=True,
                        panel_id="main", images=None, extra_context=None, **kwargs):
            captured["extra_context"] = extra_context
            yield self.server._sse("pipeline_stage", stage="complete", gear=3)
            yield self.server._sse("response", text="text-only reply")

        with mock.patch.object(self.server, "agentic_loop_stream",
                               side_effect=fake_stream), \
             mock.patch.object(self.server, "_save_conversation",
                               return_value="session-test-pair-001"), \
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
        payload = json.loads(body)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["conversation_id"], "main")
        self.assertEqual(payload["chunk_id"], "session-test-pair-001")
        # Ordinary chat carries no Programming context unless explicitly entered.
        self.assertIsNone(captured.get("extra_context"))


if __name__ == "__main__":
    unittest.main()
