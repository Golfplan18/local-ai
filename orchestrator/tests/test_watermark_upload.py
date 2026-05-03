#!/usr/bin/env python3
"""A/V Phase 6 follow-up — watermark image upload + render filter tests.

Covers three layers:

1. ``timeline._normalize_watermark`` — verifies ``image_path`` round-trips
   through save/load and that bogus values fall back to None.

2. ``render._watermark_image_overlay_steps`` — verifies the FFmpeg
   chain steps produced for image watermarks (and the empty-list paths
   for disabled / no-image / missing-file cases).

3. ``POST /api/watermark/<conv>/upload`` — verifies file landing,
   path returned, extension whitelist, and the 10 MB size cap.
"""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))


class WatermarkNormalizerTests(unittest.TestCase):

    def setUp(self):
        from timeline import _normalize_watermark, _default_watermark
        self.normalize = _normalize_watermark
        self.default = _default_watermark

    def test_default_includes_image_path_none(self):
        d = self.default()
        self.assertIn("image_path", d)
        self.assertIsNone(d["image_path"])

    def test_image_path_preserved_when_valid_string(self):
        out = self.normalize({
            "enabled": True,
            "image_path": "/absolute/path/wm.png",
        })
        self.assertEqual(out["image_path"], "/absolute/path/wm.png")

    def test_image_path_stripped_when_empty(self):
        out = self.normalize({"enabled": True, "image_path": ""})
        self.assertIsNone(out["image_path"])
        out2 = self.normalize({"enabled": True, "image_path": "   "})
        self.assertIsNone(out2["image_path"])

    def test_image_path_rejected_when_not_string(self):
        out = self.normalize({"enabled": True, "image_path": 12345})
        self.assertIsNone(out["image_path"])

    def test_other_fields_still_normalized(self):
        out = self.normalize({
            "enabled": True,
            "corner": "top-left",
            "opacity": 0.8,
            "image_path": "/p/wm.png",
        })
        self.assertTrue(out["enabled"])
        self.assertEqual(out["corner"], "top-left")
        self.assertAlmostEqual(out["opacity"], 0.8)
        self.assertEqual(out["image_path"], "/p/wm.png")


class WatermarkImageOverlayTests(unittest.TestCase):

    def setUp(self):
        from render import _watermark_image_overlay_steps
        self.steps = _watermark_image_overlay_steps
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _make_image(self):
        img = self.tmp_path / "wm.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        return img

    def test_returns_empty_when_disabled(self):
        img = self._make_image()
        self.assertEqual(
            self.steps({"enabled": False, "image_path": str(img)},
                       "vmain", "v_out"),
            [],
        )

    def test_returns_empty_when_no_image_path(self):
        self.assertEqual(
            self.steps({"enabled": True, "image_path": ""}, "vmain", "v_out"),
            [],
        )

    def test_returns_empty_when_image_missing(self):
        self.assertEqual(
            self.steps(
                {"enabled": True, "image_path": str(self.tmp_path / "missing.png")},
                "vmain", "v_out"),
            [],
        )

    def test_emits_two_chain_steps_when_enabled(self):
        img = self._make_image()
        steps = self.steps(
            {"enabled": True, "image_path": str(img),
             "corner": "top-right", "opacity": 0.7},
            "vmain", "v_out",
        )
        self.assertEqual(len(steps), 2)
        # First step: load + alpha-mix.
        self.assertIn("movie=", steps[0])
        self.assertIn("colorchannelmixer=aa=0.700", steps[0])
        self.assertIn("[wm_img]", steps[0])
        # Second step: overlay onto the main chain.
        self.assertIn("[vmain][wm_img]overlay=", steps[1])
        # Top-right corner uses W-w-margin and y-margin.
        self.assertIn("W-w-20:20", steps[1])
        self.assertIn("[v_out]", steps[1])

    def test_corner_mapping(self):
        img = self._make_image()
        cases = [
            ("top-left",     "20:20"),
            ("top-right",    "W-w-20:20"),
            ("bottom-left",  "20:H-h-20"),
            ("bottom-right", "W-w-20:H-h-20"),
        ]
        for corner, expected in cases:
            steps = self.steps(
                {"enabled": True, "image_path": str(img), "corner": corner},
                "vmain", "v_out",
            )
            self.assertEqual(len(steps), 2)
            self.assertIn(expected, steps[1],
                          f"corner {corner!r} should produce {expected!r}")

    def test_opacity_clamped(self):
        img = self._make_image()
        # opacity=2 (out of range) should clamp to 1.000
        steps = self.steps(
            {"enabled": True, "image_path": str(img), "opacity": 2.0},
            "vmain", "v_out",
        )
        self.assertIn("colorchannelmixer=aa=1.000", steps[0])
        # opacity=-1 (below range) should clamp to 0.000
        steps = self.steps(
            {"enabled": True, "image_path": str(img), "opacity": -1.0},
            "vmain", "v_out",
        )
        self.assertIn("colorchannelmixer=aa=0.000", steps[0])


class WatermarkUploadEndpointTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path.home() / "ora" / "server"))
        try:
            import server as S  # type: ignore
            cls.S = S
            cls.import_ok = True
        except Exception as exc:
            cls.S = None
            cls.import_ok = False
            cls.import_err = str(exc)

    def setUp(self):
        if not self.import_ok:
            self.skipTest(
                f"could not import server.py: "
                f"{getattr(self, 'import_err', '<unknown>')}"
            )
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)

        # The endpoint computes the upload dir via
        # ``os.path.expanduser('~/ora/sessions/<conv>/uploads/')``.
        # Patch HOME so it lands inside our tmp dir.
        import os
        self._saved_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self._tmp_path)

        self.client = self.S.app.test_client()
        self.conv_id = "test_conv_wm"

    def tearDown(self):
        if self.import_ok:
            import os
            if self._saved_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = self._saved_home
            self._tmp.cleanup()

    def _upload(self, filename, data):
        return self.client.post(
            f"/api/watermark/{self.conv_id}/upload",
            data={
                "file": (io.BytesIO(data), filename),
            },
            content_type="multipart/form-data",
        )

    def test_uploads_png_and_returns_path(self):
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
        resp = self._upload("logo.png", png_bytes)
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        data = resp.get_json()
        self.assertEqual(data["conversation_id"], self.conv_id)
        self.assertTrue(data["image_path"].endswith(".png"))
        self.assertTrue(Path(data["image_path"]).exists())
        # Path must be under the conversation's uploads dir.
        expected_prefix = str(self._tmp_path / "ora" / "sessions"
                              / self.conv_id / "uploads")
        self.assertTrue(data["image_path"].startswith(expected_prefix),
                        f"unexpected path: {data['image_path']}")

    def test_rejects_missing_file(self):
        resp = self.client.post(
            f"/api/watermark/{self.conv_id}/upload",
            data={},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 400)

    def test_rejects_unsupported_extension(self):
        resp = self._upload("script.exe", b"MZ\x00\x00")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("unsupported", resp.get_json().get("error", ""))

    def test_rejects_oversized_file(self):
        # Build a > 10 MB blob.
        big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (11 * 1024 * 1024)
        resp = self._upload("huge.png", big)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("under 10 MB", resp.get_json().get("error", ""))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
