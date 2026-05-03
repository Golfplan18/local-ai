#!/usr/bin/env python3
"""
Unit tests for ``orchestrator/canvas_file_format.py`` — WP-7.0.2.

Runs under stdlib ``unittest`` (no pytest)::

    /opt/homebrew/bin/python3 -m unittest discover -s ~/ora/orchestrator/tests -v
    # or
    /opt/homebrew/bin/python3 ~/ora/orchestrator/tests/test_canvas_file_format.py

Coverage maps directly to the WP-7.0.2 test brief:

    "Round-trip a canvas with 5 objects + 2 embedded images through both
     compressed and uncompressed paths; visual recovery exact; bytes
     equivalent after decompression."

Plus structural-validator coverage, gzip-magic detection, and the schema
file's existence + parsability check.
"""
from __future__ import annotations

import base64
import gzip
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

from canvas_file_format import (  # noqa: E402
    DEFAULT_CANVAS_H,
    DEFAULT_CANVAS_W,
    FORMAT_ID,
    SCHEMA_PATH,
    SCHEMA_VERSION,
    is_compressed,
    new_canvas_state,
    read_bytes,
    read_path,
    validate,
    write_bytes,
    write_json_string,
    write_path,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

# Two tiny but real-looking PNGs encoded as base64. The bytes are arbitrary —
# they only need to be distinct, non-empty, and survive a JSON round-trip.
_PNG_A_BYTES = bytes(range(256)) * 4          # 1024 bytes, deterministic
_PNG_B_BYTES = bytes(reversed(range(256))) * 3  # 768 bytes, deterministic

_PNG_A_B64 = base64.b64encode(_PNG_A_BYTES).decode("ascii")
_PNG_B_B64 = base64.b64encode(_PNG_B_BYTES).decode("ascii")


def _make_test_canvas() -> dict:
    """Build a canvas state with 5 objects (3 shapes + 2 images), plus a
    non-default view, exercising every required schema field."""
    state = new_canvas_state(
        title="Round-trip fixture",
        conversation_id="conv-12345",
        ora_version="ora-test",
        # Pin the timestamp so two writes of this fixture compare equal byte-for-byte.
        now="2026-04-29T12:00:00+00:00",
    )
    state["view"] = {"zoom": 1.5, "pan": {"x": -250.5, "y": 80}}
    state["objects"] = [
        # Three Konva-style shapes on user_input.
        {
            "id": "u-rect-0",
            "kind": "shape",
            "layer": "user_input",
            "konva_class": "Rect",
            "x": 100, "y": 200, "width": 80, "height": 40,
            "rotation": 0, "scale_x": 1, "scale_y": 1, "opacity": 1, "visible": True,
            "user_label": "Cause",
            "attrs": {"fill": "#aabbcc", "stroke": "#112233", "strokeWidth": 2},
        },
        {
            "id": "u-rect-1",
            "kind": "shape",
            "layer": "user_input",
            "konva_class": "Rect",
            "x": 300, "y": 200, "width": 80, "height": 40,
            "user_label": "Effect",
            "attrs": {"fill": "#ddeeff", "stroke": "#112233", "strokeWidth": 2},
        },
        {
            "id": "u-arr-0",
            "kind": "shape",
            "layer": "user_input",
            "konva_class": "Arrow",
            "user_label": "→",
            "attrs": {"points": [180, 220, 300, 220], "stroke": "#000", "strokeWidth": 2},
        },
        # Two embedded images on background.
        {
            "id": "img-bg-0",
            "kind": "image",
            "layer": "background",
            "x": 0, "y": 0, "width": 800, "height": 600,
            "image_data": {
                "mime_type": "image/png",
                "encoding": "base64",
                "data": _PNG_A_B64,
                "natural_width": 800,
                "natural_height": 600,
                "source": "upload",
            },
        },
        {
            "id": "img-overlay-0",
            "kind": "image",
            "layer": "annotation",
            "x": 50, "y": 50, "width": 200, "height": 150,
            "image_data": {
                "mime_type": "image/jpeg",
                "encoding": "base64",
                "data": _PNG_B_B64,
                "natural_width": 200,
                "natural_height": 150,
                "source": "generated:test-provider",
            },
        },
    ]
    return state


# ── Tests ───────────────────────────────────────────────────────────────────

class TestSchemaFileExists(unittest.TestCase):
    """The schema doc lives at ~/ora/config/schemas/canvas-state.schema.json
    per WP-7.0.2 deliverable. Confirm it's present and well-formed JSON."""

    def test_schema_file_present(self) -> None:
        self.assertTrue(SCHEMA_PATH.exists(), f"schema not found at {SCHEMA_PATH}")

    def test_schema_file_parses(self) -> None:
        doc = json.loads(SCHEMA_PATH.read_text())
        self.assertEqual(doc["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(doc["title"], "Ora Canvas State v0.1")
        self.assertEqual(doc["additionalProperties"], False)
        # Sanity-check the discriminator for objects.
        defs = doc.get("$defs", {}).get("object", {})
        self.assertEqual(defs.get("additionalProperties"), False)


class TestNewCanvasState(unittest.TestCase):
    def test_factory_defaults(self) -> None:
        s = new_canvas_state()
        self.assertEqual(s["schema_version"], SCHEMA_VERSION)
        self.assertEqual(s["format_id"], FORMAT_ID)
        self.assertEqual(s["metadata"]["canvas_size"]["width"], DEFAULT_CANVAS_W)
        self.assertEqual(s["metadata"]["canvas_size"]["height"], DEFAULT_CANVAS_H)
        self.assertEqual(s["view"]["zoom"], 1)
        self.assertEqual(s["view"]["pan"], {"x": 0, "y": 0})
        kinds = [L["kind"] for L in s["layers"]]
        self.assertEqual(kinds, ["background", "annotation", "user_input", "selection"])
        self.assertEqual(s["objects"], [])

    def test_factory_overrides(self) -> None:
        s = new_canvas_state(canvas_size={"width": 4096, "height": 4096}, title="t", conversation_id="c-1")
        self.assertEqual(s["metadata"]["canvas_size"], {"width": 4096, "height": 4096})
        self.assertEqual(s["metadata"]["title"], "t")
        self.assertEqual(s["metadata"]["conversation_id"], "c-1")


class TestRoundTrip(unittest.TestCase):
    """The WP-7.0.2 test criterion in three parts."""

    def test_compressed_round_trip_visual_exact(self) -> None:
        s = _make_test_canvas()
        blob = write_bytes(s, compressed=True)
        self.assertTrue(is_compressed(blob), "compressed output missing gzip magic header")
        recovered = read_bytes(blob)
        self.assertEqual(recovered, s, "compressed round-trip lost data")

    def test_uncompressed_round_trip_visual_exact(self) -> None:
        s = _make_test_canvas()
        blob = write_bytes(s, compressed=False)
        self.assertFalse(is_compressed(blob), "uncompressed output should not have gzip magic")
        recovered = read_bytes(blob)
        self.assertEqual(recovered, s, "uncompressed round-trip lost data")

    def test_bytes_equivalent_after_decompression(self) -> None:
        """Plan §11.7 contract: ‘Both round-trip identically.’ This is the
        load-bearing invariant — the compressed and uncompressed surfacing
        forms wrap the SAME bytes."""
        s = _make_test_canvas()
        compressed   = write_bytes(s, compressed=True)
        uncompressed = write_bytes(s, compressed=False)
        decompressed = gzip.decompress(compressed)
        self.assertEqual(
            decompressed, uncompressed,
            "decompressed gzip output diverges from raw JSON output",
        )

    def test_compressed_smaller_than_uncompressed(self) -> None:
        """Sanity check that gzip is doing useful work on a payload that
        contains base64-encoded image data (which compresses very well)."""
        s = _make_test_canvas()
        c = write_bytes(s, compressed=True)
        u = write_bytes(s, compressed=False)
        self.assertLess(len(c), len(u), "compressed should be smaller than uncompressed for this fixture")

    def test_image_payloads_recovered_byte_exact(self) -> None:
        s = _make_test_canvas()
        recovered = read_bytes(write_bytes(s, compressed=True))
        for orig_obj, rec_obj in zip(s["objects"], recovered["objects"]):
            if orig_obj.get("kind") == "image":
                self.assertEqual(orig_obj["image_data"]["data"], rec_obj["image_data"]["data"])
                # Decode and confirm bytes match the source fixture.
                if orig_obj["id"] == "img-bg-0":
                    self.assertEqual(base64.b64decode(rec_obj["image_data"]["data"]), _PNG_A_BYTES)
                if orig_obj["id"] == "img-overlay-0":
                    self.assertEqual(base64.b64decode(rec_obj["image_data"]["data"]), _PNG_B_BYTES)

    def test_canonicalisation_stable_across_writes(self) -> None:
        """Two writes of the same canvas should produce identical bytes —
        otherwise diff-based persistence (autosave, vault export) is
        unreliable."""
        s = _make_test_canvas()
        b1 = write_bytes(s, compressed=False)
        b2 = write_bytes(s, compressed=False)
        self.assertEqual(b1, b2)
        gz1 = write_bytes(s, compressed=True)
        gz2 = write_bytes(s, compressed=True)
        self.assertEqual(gz1, gz2)

    def test_canonicalisation_orders_keys(self) -> None:
        """Permuting key insertion order must not change the output bytes."""
        a = {"format_id": "ora-canvas", "schema_version": "0.1.0", "metadata": {"canvas_size": {"width": 10, "height": 10}}, "view": {"zoom": 1, "pan": {"x": 0, "y": 0}}, "layers": [{"id": "background", "kind": "background"}], "objects": []}
        b = {"layers": [{"kind": "background", "id": "background"}], "objects": [], "view": {"pan": {"y": 0, "x": 0}, "zoom": 1}, "metadata": {"canvas_size": {"height": 10, "width": 10}}, "schema_version": "0.1.0", "format_id": "ora-canvas"}
        self.assertEqual(write_bytes(a, compressed=False), write_bytes(b, compressed=False))


class TestPathHelpers(unittest.TestCase):
    def test_write_and_read_compressed_path(self) -> None:
        s = _make_test_canvas()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "session.ora-canvas"
            write_path(s, p)
            self.assertTrue(p.exists())
            self.assertTrue(is_compressed(p.read_bytes()))
            self.assertEqual(read_path(p), s)

    def test_write_and_read_uncompressed_path(self) -> None:
        s = _make_test_canvas()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "session.ora-canvas.json"
            write_path(s, p)
            self.assertTrue(p.exists())
            self.assertFalse(is_compressed(p.read_bytes()))
            self.assertEqual(read_path(p), s)
            # Auto-detection: gunzip magic is absent so read_path treats
            # this as raw JSON regardless of extension.

    def test_unknown_extension_rejected(self) -> None:
        s = _make_test_canvas()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                write_path(s, Path(tmp) / "session.canvas")


class TestReadEdgeCases(unittest.TestCase):
    def test_format_id_mismatch_raises(self) -> None:
        bad = json.dumps({"format_id": "not-ora-canvas"}).encode("utf-8")
        with self.assertRaises(ValueError):
            read_bytes(bad)

    def test_invalid_json_raises(self) -> None:
        with self.assertRaises(ValueError):
            read_bytes(b"not json at all")

    def test_top_level_must_be_object(self) -> None:
        with self.assertRaises(ValueError):
            read_bytes(json.dumps([1, 2, 3]).encode("utf-8"))

    def test_auto_detect_compressed(self) -> None:
        s = _make_test_canvas()
        gz = gzip.compress(json.dumps(s).encode("utf-8"), mtime=0)
        # Force-feed unconventional compression source — read_bytes should
        # still gunzip then parse.
        recovered = read_bytes(gz)
        # JSON passes through json.loads, so equality is via Python value
        # comparison (key order does not matter).
        self.assertEqual(recovered, s)


class TestValidator(unittest.TestCase):
    def test_factory_state_validates(self) -> None:
        ok, errs = validate(new_canvas_state())
        self.assertTrue(ok, f"empty factory state failed validation: {errs}")

    def test_round_trip_state_validates(self) -> None:
        ok, errs = validate(_make_test_canvas())
        self.assertTrue(ok, f"round-trip fixture failed validation: {errs}")

    def test_missing_format_id_fails(self) -> None:
        bad = _make_test_canvas()
        bad.pop("format_id")
        ok, errs = validate(bad)
        self.assertFalse(ok)

    def test_image_without_image_data_fails(self) -> None:
        bad = _make_test_canvas()
        bad["objects"].append({"id": "broken", "kind": "image", "layer": "background"})
        ok, errs = validate(bad)
        self.assertFalse(ok)
        self.assertTrue(any("image_data" in e["message"] or "image_data" in e["path"] for e in errs))

    def test_image_data_url_prefix_rejected(self) -> None:
        bad = _make_test_canvas()
        bad["objects"][3]["image_data"]["data"] = "data:image/png;base64," + _PNG_A_B64
        ok, errs = validate(bad)
        self.assertFalse(ok)

    def test_unknown_top_level_property_fails(self) -> None:
        bad = _make_test_canvas()
        bad["surprise"] = True
        ok, errs = validate(bad)
        self.assertFalse(ok)

    def test_duplicate_object_id_fails_structural(self) -> None:
        bad = _make_test_canvas()
        bad["objects"].append({"id": "u-rect-0", "kind": "shape", "layer": "user_input"})
        ok, errs = validate(bad, use_jsonschema=False)
        self.assertFalse(ok)
        self.assertTrue(any("duplicate" in e["message"].lower() for e in errs))

    def test_invalid_layer_kind_fails(self) -> None:
        bad = _make_test_canvas()
        bad["layers"][0]["kind"] = "garbage"
        ok, errs = validate(bad)
        self.assertFalse(ok)


class TestGroupNesting(unittest.TestCase):
    def test_group_with_children_round_trips(self) -> None:
        s = new_canvas_state()
        s["objects"] = [
            {
                "id": "g-1",
                "kind": "group",
                "layer": "user_input",
                "children": [
                    {"id": "g-1.r-1", "kind": "shape", "layer": "user_input", "konva_class": "Rect", "attrs": {"fill": "red"}},
                    {"id": "g-1.r-2", "kind": "shape", "layer": "user_input", "konva_class": "Rect", "attrs": {"fill": "blue"}},
                ],
            }
        ]
        ok, errs = validate(s)
        self.assertTrue(ok, f"group fixture failed validation: {errs}")
        self.assertEqual(read_bytes(write_bytes(s)), s)

    def test_group_without_children_fails(self) -> None:
        s = new_canvas_state()
        s["objects"] = [{"id": "g-bad", "kind": "group", "layer": "user_input"}]
        ok, errs = validate(s)
        self.assertFalse(ok)


class TestWriteJsonString(unittest.TestCase):
    def test_pretty_print(self) -> None:
        s = _make_test_canvas()
        out = write_json_string(s, indent=2)
        self.assertIn("\n", out)
        # Re-parse and confirm equivalence.
        self.assertEqual(json.loads(out), s)

    def test_compact_default(self) -> None:
        s = _make_test_canvas()
        out = write_json_string(s)
        self.assertNotIn("\n", out)
        self.assertEqual(json.loads(out), s)


if __name__ == "__main__":
    unittest.main(verbosity=2)
