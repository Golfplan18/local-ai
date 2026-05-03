"""Tests for two-pass H.264 split logic in render.py.

Coverage focuses on the pure-function `_split_for_two_pass` and the
``v_two_pass`` preset wiring. The actual ffmpeg subprocess is not
exercised here — that requires real video material and is verified by
integration smoke. What we DO verify:

  • _split_for_two_pass produces argvs with the right pass flags.
  • Pass-1 drops audio (-an) and outputs to the null sink.
  • Pass-2 keeps everything and writes to the original output path.
  • Both passes share the same -passlogfile path so the stats file
    written by pass-1 is read by pass-2.
  • The "high" preset declares v_two_pass = True; others do not.
  • _cleanup_passlog removes both -0.log and -0.log.mbtree files.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from orchestrator.render import (  # noqa: E402  (path setup must precede)
    PRESETS,
    _cleanup_passlog,
    _split_for_two_pass,
)


class TestSplitForTwoPass(unittest.TestCase):
    def setUp(self) -> None:
        # Representative single-pass argv that mirrors what
        # _assemble_command emits: encoder flags, output path last.
        self.output = Path("/tmp/render-out/abc123.mp4")
        self.argv = [
            "ffmpeg", "-y",
            "-i", "/some/clip.mp4",
            "-filter_complex", "scale=1920:1080",
            "-map", "[v_out]",
            "-c:v", "libx264",
            "-preset", "slow",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-r", "60",
            "-c:a", "aac",
            "-b:a", "256k",
            "-t", "12.500",
            str(self.output),
        ]
        self.render_id = "abc123"

    def test_splits_into_two_argvs(self) -> None:
        p1, p2, passlog = _split_for_two_pass(
            self.argv, self.output, self.render_id)
        self.assertIsInstance(p1, list)
        self.assertIsInstance(p2, list)
        self.assertIsInstance(passlog, Path)

    def test_pass_one_carries_pass_1_flag_and_passlogfile(self) -> None:
        p1, _, passlog = _split_for_two_pass(
            self.argv, self.output, self.render_id)
        # Find -pass argument and its value.
        idx = p1.index("-pass")
        self.assertEqual(p1[idx + 1], "1")
        idx = p1.index("-passlogfile")
        self.assertEqual(p1[idx + 1], str(passlog))

    def test_pass_one_drops_audio_and_outputs_to_null_sink(self) -> None:
        p1, _, _ = _split_for_two_pass(
            self.argv, self.output, self.render_id)
        self.assertIn("-an", p1, "pass-1 must drop audio")
        # -f null must appear.
        idx = p1.index("-f")
        self.assertEqual(p1[idx + 1], "null")
        # Last token is the null device.
        self.assertEqual(p1[-1], os.devnull)

    def test_pass_one_does_not_touch_real_output_path(self) -> None:
        p1, _, _ = _split_for_two_pass(
            self.argv, self.output, self.render_id)
        self.assertNotIn(str(self.output), p1)

    def test_pass_two_carries_pass_2_flag_and_real_output_path(self) -> None:
        _, p2, passlog = _split_for_two_pass(
            self.argv, self.output, self.render_id)
        idx = p2.index("-pass")
        self.assertEqual(p2[idx + 1], "2")
        idx = p2.index("-passlogfile")
        self.assertEqual(p2[idx + 1], str(passlog))
        # Output path must remain at the tail.
        self.assertEqual(p2[-1], str(self.output))

    def test_pass_two_keeps_audio_codec_and_settings(self) -> None:
        _, p2, _ = _split_for_two_pass(
            self.argv, self.output, self.render_id)
        # Audio codec and bitrate from the original argv should still be
        # in pass-2 (only pass-1 drops them).
        self.assertIn("aac", p2)
        self.assertIn("256k", p2)
        self.assertNotIn("-an", p2)
        self.assertNotIn(os.devnull, p2)

    def test_passlog_uses_render_id_for_uniqueness(self) -> None:
        _, _, passlog_a = _split_for_two_pass(
            self.argv, self.output, "render-a")
        _, _, passlog_b = _split_for_two_pass(
            self.argv, self.output, "render-b")
        self.assertNotEqual(passlog_a, passlog_b,
                            "passlog paths must differ per render so "
                            "concurrent renders don't share stats files")

    def test_passlog_lives_next_to_output(self) -> None:
        _, _, passlog = _split_for_two_pass(
            self.argv, self.output, self.render_id)
        self.assertEqual(passlog.parent, self.output.parent,
                         "passlog should sit beside the output, not "
                         "in CWD or some other directory")

    def test_raises_when_argv_does_not_end_with_output_path(self) -> None:
        # Defensive: if the argv builder ever changes its tail layout,
        # we want a clear error rather than silently corrupting output.
        bad_argv = list(self.argv) + ["-fake-trailing-flag"]
        with self.assertRaises(RuntimeError):
            _split_for_two_pass(bad_argv, self.output, self.render_id)

    def test_high_preset_has_two_pass_enabled(self) -> None:
        self.assertTrue(
            PRESETS["high"].get("v_two_pass"),
            "the 'high' preset should opt into two-pass x264 — "
            "matches the deferral comment 'higher quality at lower bitrate'"
        )

    def test_other_presets_default_to_single_pass(self) -> None:
        for name in ("standard", "web", "mov", "webm",
                     "audio_only", "preview_proxy"):
            preset = PRESETS.get(name)
            if preset is None:
                continue
            self.assertFalse(
                preset.get("v_two_pass", False),
                f"preset '{name}' should default to single-pass; "
                f"got v_two_pass = {preset.get('v_two_pass')!r}",
            )


class TestCleanupPasslog(unittest.TestCase):
    def test_removes_log_and_mbtree_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            passlog = Path(tmpdir) / "passlog"
            log_file = Path(str(passlog) + "-0.log")
            mbtree = Path(str(passlog) + "-0.log.mbtree")
            log_file.write_text("dummy stats")
            mbtree.write_text("dummy mbtree")

            self.assertTrue(log_file.exists())
            self.assertTrue(mbtree.exists())

            _cleanup_passlog(passlog)

            self.assertFalse(log_file.exists(),
                             "-0.log file should be removed")
            self.assertFalse(mbtree.exists(),
                             "-0.log.mbtree file should be removed")

    def test_handles_missing_files_gracefully(self) -> None:
        # Should not raise even if no passlog files exist.
        with tempfile.TemporaryDirectory() as tmpdir:
            passlog = Path(tmpdir) / "passlog-never-written"
            try:
                _cleanup_passlog(passlog)
            except Exception as e:
                self.fail(f"_cleanup_passlog should not raise: {e}")


if __name__ == "__main__":
    unittest.main()
