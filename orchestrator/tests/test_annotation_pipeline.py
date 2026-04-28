#!/usr/bin/env python3
"""
WP-5.2 — annotation pipeline unit tests (server-side).

Runs under stdlib ``unittest`` — no pytest dependency. Invoke::

    /opt/homebrew/bin/python3 -m unittest discover -s ~/ora/orchestrator/tests -v

Scope:
* ``visual_validator.validate_annotations`` accepts well-formed payloads,
  rejects malformed ones (missing fields, unknown kind/action, bad types).
* ``visual_validator.serialize_annotations_to_text`` produces the fenced
  prompt block per WP-5.2 spec.
* The ``/chat/multipart`` endpoint accepts an ``annotations`` form field,
  validates it, and threads ``annotations`` through ``extra_context``.
* ``boot.build_system_prompt_for_gear`` serializes annotations into the
  assembled prompt when present, and leaves the prompt unchanged when
  absent (backward compat for text-only + spatial-only turns).
"""
from __future__ import annotations

import json
import sys
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
WORKSPACE = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))
sys.path.insert(0, str(WORKSPACE / "server"))


class _NoopThread:
    """Stub thread that fires no side-effects — mirrors test_visual_merged_input."""

    def __init__(self, *a, **k):
        pass

    def start(self):
        pass

    def join(self, *a, **k):
        pass

    daemon = True


def _valid_annotations() -> dict:
    """Well-formed annotations payload covering all five kinds."""
    return {
        "annotations": [
            {
                "annotation_id": "ua-callout-1",
                "kind": "callout",
                "action": "expand",
                "target_id": "node-3",
                "text": "why is this the bottleneck?",
                "position": None,
                "points": None,
            },
            {
                "annotation_id": "ua-hi-1",
                "kind": "highlight",
                "action": "expand",
                "target_id": "node-5",
                "text": "",
                "position": None,
                "points": None,
            },
            {
                "annotation_id": "ua-x-1",
                "kind": "strikethrough",
                "action": "remove",
                "target_id": "edge-4-5",
                "text": "",
                "position": None,
                "points": None,
            },
            {
                "annotation_id": "ua-sticky-1",
                "kind": "sticky",
                "action": "add_element",
                "target_id": None,
                "text": "market volatility",
                "position": [120, 140],
                "points": None,
            },
            {
                "annotation_id": "ua-pen-1",
                "kind": "pen",
                "action": "suggest_cluster",
                "target_id": None,
                "text": "",
                "position": None,
                "points": [[10, 10], [20, 15], [25, 25], [15, 30]],
            },
        ],
    }


# ---------------------------------------------------------------------------
# validate_annotations tests
# ---------------------------------------------------------------------------


class ValidateAnnotationsTests(unittest.TestCase):
    """Unit tests for ``visual_validator.validate_annotations``."""

    def test_valid_payload_passes(self) -> None:
        from visual_validator import validate_annotations
        result = validate_annotations(_valid_annotations())
        self.assertTrue(
            result.valid,
            f"unexpected errors: {[e.message for e in result.errors]}",
        )
        self.assertEqual(len(result.errors), 0)

    def test_empty_annotations_list_is_valid(self) -> None:
        from visual_validator import validate_annotations
        result = validate_annotations({"annotations": []})
        self.assertTrue(result.valid)
        self.assertEqual(len(result.errors), 0)

    def test_bare_list_also_accepted(self) -> None:
        """validate_annotations accepts a bare list or wrapped dict."""
        from visual_validator import validate_annotations
        items = _valid_annotations()["annotations"]
        result = validate_annotations(items)
        self.assertTrue(result.valid)

    def test_missing_kind_rejected(self) -> None:
        from visual_validator import validate_annotations
        payload = {"annotations": [{
            "annotation_id": "ua-x", "action": "expand",
            "target_id": "n-1", "text": "",
            "position": None, "points": None,
        }]}
        result = validate_annotations(payload)
        self.assertFalse(result.valid)
        self.assertTrue(
            any(e.code == "E_MISSING_FIELD" for e in result.errors),
            f"errors: {[e.as_dict() for e in result.errors]}",
        )

    def test_unknown_kind_rejected(self) -> None:
        from visual_validator import validate_annotations
        payload = {"annotations": [{
            "annotation_id": "ua-x", "kind": "underline", "action": "expand",
            "target_id": "n-1", "text": "",
            "position": None, "points": None,
        }]}
        result = validate_annotations(payload)
        self.assertFalse(result.valid)
        self.assertTrue(
            any("unknown kind" in e.message for e in result.errors),
            f"errors: {[e.message for e in result.errors]}",
        )

    def test_unknown_action_rejected(self) -> None:
        from visual_validator import validate_annotations
        payload = {"annotations": [{
            "annotation_id": "ua-x", "kind": "callout", "action": "teleport",
            "target_id": "n-1", "text": "",
            "position": None, "points": None,
        }]}
        result = validate_annotations(payload)
        self.assertFalse(result.valid)
        self.assertTrue(
            any("unknown action" in e.message for e in result.errors),
            f"errors: {[e.message for e in result.errors]}",
        )

    def test_non_dict_input_rejected(self) -> None:
        from visual_validator import validate_annotations
        result = validate_annotations("not-a-payload")  # type: ignore[arg-type]
        self.assertFalse(result.valid)

    def test_malformed_annotations_array_rejected(self) -> None:
        from visual_validator import validate_annotations
        result = validate_annotations({"annotations": "not-a-list"})
        self.assertFalse(result.valid)

    def test_missing_annotation_id_rejected(self) -> None:
        from visual_validator import validate_annotations
        payload = {"annotations": [{
            "kind": "callout", "action": "expand",
            "target_id": "n-1", "text": "",
            "position": None, "points": None,
        }]}
        result = validate_annotations(payload)
        self.assertFalse(result.valid)

    def test_bad_position_rejected(self) -> None:
        from visual_validator import validate_annotations
        payload = {"annotations": [{
            "annotation_id": "ua-x", "kind": "sticky", "action": "add_element",
            "target_id": None, "text": "t",
            "position": "not-a-list", "points": None,
        }]}
        result = validate_annotations(payload)
        self.assertFalse(result.valid)

    def test_bad_points_rejected(self) -> None:
        from visual_validator import validate_annotations
        payload = {"annotations": [{
            "annotation_id": "ua-x", "kind": "pen", "action": "suggest_cluster",
            "target_id": None, "text": "",
            "position": None, "points": [[1, 2], ["string", 4]],
        }]}
        result = validate_annotations(payload)
        self.assertFalse(result.valid)

    def test_target_id_must_be_string_or_null(self) -> None:
        from visual_validator import validate_annotations
        payload = {"annotations": [{
            "annotation_id": "ua-x", "kind": "callout", "action": "expand",
            "target_id": 42, "text": "",
            "position": None, "points": None,
        }]}
        result = validate_annotations(payload)
        self.assertFalse(result.valid)


# ---------------------------------------------------------------------------
# serialize_annotations_to_text tests
# ---------------------------------------------------------------------------


class SerializeAnnotationsToTextTests(unittest.TestCase):
    """The serializer builds the compact =<fenced block> for the system prompt."""

    def test_empty_returns_empty_string(self) -> None:
        from visual_validator import serialize_annotations_to_text
        self.assertEqual(serialize_annotations_to_text({"annotations": []}), "")
        self.assertEqual(serialize_annotations_to_text(None), "")  # type: ignore[arg-type]

    def test_fenced_block_present(self) -> None:
        from visual_validator import serialize_annotations_to_text
        out = serialize_annotations_to_text(_valid_annotations())
        self.assertIn("=== USER ANNOTATIONS ===", out)
        self.assertIn("=== END USER ANNOTATIONS ===", out)

    def test_callout_expand_line_format(self) -> None:
        from visual_validator import serialize_annotations_to_text
        out = serialize_annotations_to_text(_valid_annotations())
        # Per spec: [callout→expand] on node-3: "why is this the bottleneck?"
        self.assertIn("[callout\u2192expand] on node-3:", out)
        self.assertIn('"why is this the bottleneck?"', out)

    def test_strikethrough_remove_line_includes_parenthetical(self) -> None:
        from visual_validator import serialize_annotations_to_text
        out = serialize_annotations_to_text(_valid_annotations())
        # Strikethrough with empty text carries "(flagged for removal)"
        self.assertIn("[strikethrough\u2192remove] on edge-4-5:", out)
        self.assertIn("(flagged for removal)", out)

    def test_sticky_add_element_includes_position(self) -> None:
        from visual_validator import serialize_annotations_to_text
        out = serialize_annotations_to_text(_valid_annotations())
        self.assertIn("[sticky\u2192add_element] free-position", out)
        self.assertIn('"market volatility"', out)

    def test_pen_suggest_cluster_freehand(self) -> None:
        from visual_validator import serialize_annotations_to_text
        out = serialize_annotations_to_text(_valid_annotations())
        self.assertIn("[pen\u2192suggest_cluster]", out)


# ---------------------------------------------------------------------------
# Multipart endpoint integration
# ---------------------------------------------------------------------------


class MultipartAnnotationsEndpointTests(unittest.TestCase):
    """End-to-end multipart endpoint integration — fake pipeline, real server."""

    def setUp(self) -> None:
        import server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()
        self._tmp = tempfile.mkdtemp(prefix="ora-annot-test-")
        self._orig_uploads_root = server.VISUAL_UPLOADS_ROOT
        server.VISUAL_UPLOADS_ROOT = self._tmp

    def tearDown(self) -> None:
        self.server.VISUAL_UPLOADS_ROOT = self._orig_uploads_root
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _mock_stream(self, response_text: str, captured: dict):
        server = self.server

        def fake_stream(clean_input, history, use_pipeline=True,
                        panel_id="main", images=None, extra_context=None, **kwargs):
            captured["clean_input"] = clean_input
            captured["panel_id"] = panel_id
            captured["extra_context"] = extra_context
            captured["images"] = images
            yield server._sse("pipeline_stage", stage="complete", gear=3)
            yield server._sse("response", text=response_text)

        return fake_stream

    def test_valid_annotations_reach_pipeline(self) -> None:
        """POST with annotations → pipeline's extra_context carries them."""
        captured: dict = {}
        data = {
            "message": "What do you make of my markup?",
            "conversation_id": "annot-convo-1",
            "panel_id": "main",
            "annotations": json.dumps(_valid_annotations()),
        }

        with mock.patch.object(self.server, "agentic_loop_stream",
                               side_effect=self._mock_stream("ok", captured)), \
             mock.patch.object(self.server.threading, "Thread", _NoopThread):
            resp = self.client.post("/chat/multipart", data=data,
                                    content_type="multipart/form-data")
            b"".join(resp.response)

        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(captured.get("extra_context"))
        self.assertIn("annotations", captured["extra_context"])
        annots = captured["extra_context"]["annotations"]
        self.assertEqual(len(annots["annotations"]), 5)
        self.assertEqual(annots["annotations"][0]["kind"], "callout")

    def test_invalid_annotations_rejected_with_400(self) -> None:
        """Unknown kind → 400 with structured errors."""
        bad = {"annotations": [{
            "annotation_id": "ua-x", "kind": "underline", "action": "expand",
            "target_id": "n-1", "text": "",
            "position": None, "points": None,
        }]}
        data = {
            "message": "oops",
            "conversation_id": "annot-convo-bad",
            "annotations": json.dumps(bad),
        }

        with mock.patch.object(self.server.threading, "Thread", _NoopThread):
            resp = self.client.post("/chat/multipart", data=data,
                                    content_type="multipart/form-data")

        self.assertEqual(resp.status_code, 400)
        body = json.loads(resp.get_data(as_text=True))
        self.assertIn("error", body)
        self.assertIn("errors", body)

    def test_malformed_annotations_json_rejected(self) -> None:
        """Malformed JSON → 400 with parse detail."""
        data = {
            "message": "oops",
            "conversation_id": "annot-convo-malformed",
            "annotations": "{not json",
        }
        with mock.patch.object(self.server.threading, "Thread", _NoopThread):
            resp = self.client.post("/chat/multipart", data=data,
                                    content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 400)
        body = json.loads(resp.get_data(as_text=True))
        self.assertIn("invalid annotations JSON", body["error"])

    def test_no_annotations_still_works(self) -> None:
        """Backward compat: multipart without annotations field still flows."""
        captured: dict = {}
        data = {
            "message": "Just text.",
            "conversation_id": "annot-convo-empty",
        }
        with mock.patch.object(self.server, "agentic_loop_stream",
                               side_effect=self._mock_stream("ok", captured)), \
             mock.patch.object(self.server.threading, "Thread", _NoopThread):
            resp = self.client.post("/chat/multipart", data=data,
                                    content_type="multipart/form-data")
            b"".join(resp.response)

        self.assertEqual(resp.status_code, 200)
        ec = captured.get("extra_context")
        self.assertTrue(
            ec is None or "annotations" not in (ec or {}),
            f"unexpected extra_context: {ec}",
        )


# ---------------------------------------------------------------------------
# boot.build_system_prompt_for_gear — annotation injection
# ---------------------------------------------------------------------------


class BuildSystemPromptIncludesAnnotationsTests(unittest.TestCase):
    """``build_system_prompt_for_gear`` must render annotations into the prompt
    when context_pkg['annotations'] is present, and leave the prompt unchanged
    when absent (backward compat)."""

    def setUp(self) -> None:
        from boot import build_system_prompt_for_gear  # noqa: WPS433
        self.build = build_system_prompt_for_gear

    def _context_pkg(self, **extras) -> dict:
        pkg = {
            "mode_text": "# Fake Mode\n",
            "mode_name": "spatial_reasoning",
            "conversation_rag": "",
            "concept_rag": "",
            "relationship_rag": "",
            "rag_utilization": "",
        }
        pkg.update(extras)
        return pkg

    def test_annotations_fenced_block_rendered(self) -> None:
        pkg = self._context_pkg(annotations=_valid_annotations())
        prompt = self.build(pkg, slot="breadth")
        self.assertIn("=== USER ANNOTATIONS ===", prompt)
        self.assertIn("=== END USER ANNOTATIONS ===", prompt)

    def test_annotations_include_action_markers(self) -> None:
        pkg = self._context_pkg(annotations=_valid_annotations())
        prompt = self.build(pkg, slot="breadth")
        # Each mapping produces the kind→action signature.
        self.assertIn("[callout\u2192expand]", prompt)
        self.assertIn("[strikethrough\u2192remove]", prompt)
        self.assertIn("[sticky\u2192add_element]", prompt)
        self.assertIn("[pen\u2192suggest_cluster]", prompt)

    def test_no_annotations_leaves_prompt_clean(self) -> None:
        """Backward compat: absent annotations → no fence in prompt."""
        pkg = self._context_pkg()  # no annotations key
        prompt = self.build(pkg, slot="breadth")
        self.assertNotIn("=== USER ANNOTATIONS ===", prompt)

    def test_empty_annotations_list_leaves_prompt_clean(self) -> None:
        """Edge case: context_pkg carries empty list → no fence added."""
        pkg = self._context_pkg(annotations={"annotations": []})
        prompt = self.build(pkg, slot="breadth")
        self.assertNotIn("=== USER ANNOTATIONS ===", prompt)


if __name__ == "__main__":
    unittest.main()
