#!/usr/bin/env python3
"""A/V Phase 5+ polish — audio waveform thumbnail tests.

Covers two layers:

1. ``waveform.render_waveform`` — invokes ffmpeg as a subprocess; the
   tests mock the subprocess so they don't depend on a working ffmpeg
   on the test machine. They verify the command line shape and the
   true/false return contract for failure cases (missing source,
   non-zero exit, missing output).

2. ``GET /api/media-library/<conv>/<entry>/waveform`` — verifies the
   endpoint's lazy-cache contract (first hit triggers render; second
   hit serves cached file without re-rendering), 404 paths for unknown
   entries / non-audio entries / failed render.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))


class RenderWaveformTests(unittest.TestCase):

    def setUp(self):
        from waveform import render_waveform, waveform_cache_path
        self.render_waveform = render_waveform
        self.waveform_cache_path = waveform_cache_path
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _make_source(self, name="clip.wav"):
        src = self._tmp_path / name
        src.write_bytes(b"\x00" * 1024)
        return src

    def test_returns_false_for_missing_source(self):
        ok = self.render_waveform(
            self._tmp_path / "nonexistent.wav",
            self._tmp_path / "out.png",
        )
        self.assertFalse(ok)

    def test_returns_true_when_ffmpeg_succeeds_and_writes_output(self):
        src = self._make_source()
        out = self._tmp_path / "out.png"

        def fake_run(cmd, **kwargs):
            # Simulate ffmpeg writing the output file.
            output_path = Path(cmd[cmd.index(str(out))])
            output_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
            r = mock.Mock()
            r.returncode = 0
            r.stdout = b""
            r.stderr = b""
            return r

        with mock.patch("waveform.subprocess.run", side_effect=fake_run):
            ok = self.render_waveform(src, out)
        self.assertTrue(ok)
        self.assertTrue(out.exists())
        self.assertGreater(out.stat().st_size, 0)

    def test_returns_false_on_ffmpeg_nonzero_exit(self):
        src = self._make_source()
        out = self._tmp_path / "out.png"
        proc = mock.Mock(returncode=1, stdout=b"", stderr=b"oops")
        with mock.patch("waveform.subprocess.run", return_value=proc):
            ok = self.render_waveform(src, out)
        self.assertFalse(ok)

    def test_returns_false_when_output_missing_after_run(self):
        # ffmpeg "succeeded" (rc=0) but didn't actually produce the file.
        src = self._make_source()
        out = self._tmp_path / "out.png"
        proc = mock.Mock(returncode=0, stdout=b"", stderr=b"")
        with mock.patch("waveform.subprocess.run", return_value=proc):
            ok = self.render_waveform(src, out)
        self.assertFalse(ok)

    def test_returns_false_on_subprocess_timeout(self):
        import subprocess as _sp
        src = self._make_source()
        out = self._tmp_path / "out.png"
        with mock.patch(
            "waveform.subprocess.run",
            side_effect=_sp.TimeoutExpired(cmd="ffmpeg", timeout=1),
        ):
            ok = self.render_waveform(src, out, timeout=1)
        self.assertFalse(ok)

    def test_command_line_shape(self):
        """The ffmpeg command must include showwavespic + -frames:v 1."""
        src = self._make_source()
        out = self._tmp_path / "out.png"
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            Path(cmd[-1]).write_bytes(b"\x89PNG" + b"\x00" * 32)
            r = mock.Mock()
            r.returncode = 0
            r.stdout = b""
            r.stderr = b""
            return r

        with mock.patch("waveform.subprocess.run", side_effect=fake_run):
            self.render_waveform(src, out, width=600, height=120)

        cmd = captured["cmd"]
        joined = " ".join(cmd)
        self.assertIn("showwavespic", joined)
        self.assertIn("s=600x120", joined)
        self.assertIn("-frames:v", cmd)
        self.assertIn("1", cmd)
        self.assertIn(str(src), cmd)
        self.assertIn(str(out), cmd)

    def test_cache_path_helper(self):
        thumbs_dir = self._tmp_path / "thumbnails"
        p = self.waveform_cache_path(thumbs_dir, "abcd1234")
        self.assertEqual(p, thumbs_dir / "abcd1234.waveform.png")


class WaveformEndpointTests(unittest.TestCase):

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
        import media_library as ML  # noqa: WPS433
        self._ML = ML
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)
        self._saved_sessions_root = ML.SESSIONS_ROOT
        ML.SESSIONS_ROOT = self._tmp_path / "sessions"
        ML.SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
        ML._libraries.clear()

        from media_library import get_library
        self._saved_server_getter = self.S._get_media_library
        self.S._get_media_library = get_library
        self._saved_has_flag = self.S._HAS_MEDIA_LIBRARY
        self.S._HAS_MEDIA_LIBRARY = True
        self.client = self.S.app.test_client()
        self.conv_id = "test_conv_waveform"

    def tearDown(self):
        if self.import_ok:
            self.S._get_media_library = self._saved_server_getter
            self.S._HAS_MEDIA_LIBRARY = self._saved_has_flag
            self._ML.SESSIONS_ROOT = self._saved_sessions_root
            self._ML._libraries.clear()
            self._tmp.cleanup()

    def _add_audio(self, basename="clip.wav"):
        media_dir = self._tmp_path / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        src = media_dir / basename
        src.write_bytes(b"\x00" * 1024)
        lib = self._ML.get_library(self.conv_id)
        return lib.add_entry(str(src))

    def _stub_render_writes_png(self, content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 32):
        """Patch waveform.render_waveform to write a fake PNG and return True."""
        def fake_render(src, out, **kwargs):
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_bytes(content)
            return True
        return mock.patch("waveform.render_waveform", side_effect=fake_render)

    def test_endpoint_renders_on_first_hit_and_caches(self):
        entry = self._add_audio()
        with self._stub_render_writes_png() as patched:
            resp = self.client.get(
                f"/api/media-library/{self.conv_id}/{entry['id']}/waveform"
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.mimetype, "image/png")
            self.assertEqual(patched.call_count, 1)
            resp.close()

            # Second hit should NOT call render_waveform — file is cached.
            resp2 = self.client.get(
                f"/api/media-library/{self.conv_id}/{entry['id']}/waveform"
            )
            self.assertEqual(resp2.status_code, 200)
            self.assertEqual(patched.call_count, 1, "render must not run twice")
            resp2.close()

    def test_endpoint_404_for_unknown_entry(self):
        resp = self.client.get(
            f"/api/media-library/{self.conv_id}/notreal/waveform"
        )
        self.assertEqual(resp.status_code, 404)

    def test_endpoint_404_for_non_audio_video_entry(self):
        # Add a fake "image" entry by faking the kind on the entry itself.
        media_dir = self._tmp_path / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        img = media_dir / "shot.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 32)
        lib = self._ML.get_library(self.conv_id)
        entry = lib.add_entry(str(img))
        # Sanity: image classification should put kind='image'.
        self.assertEqual(entry["kind"], "image")

        resp = self.client.get(
            f"/api/media-library/{self.conv_id}/{entry['id']}/waveform"
        )
        self.assertEqual(resp.status_code, 404)

    def test_endpoint_404_when_render_fails(self):
        entry = self._add_audio()
        with mock.patch("waveform.render_waveform", return_value=False):
            resp = self.client.get(
                f"/api/media-library/{self.conv_id}/{entry['id']}/waveform"
            )
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertEqual(data.get("error"), "waveform render failed")

    def test_endpoint_404_when_source_file_missing(self):
        entry = self._add_audio()
        # Delete the underlying file.
        Path(entry["source_path"]).unlink()
        resp = self.client.get(
            f"/api/media-library/{self.conv_id}/{entry['id']}/waveform"
        )
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
