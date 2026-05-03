"""Tests for multi-stop title-card gradients.

Covers two surfaces:
  • timeline.py — clip normalizer accepts a `gradient.stops` list, caps
    at 8 colors, drops malformed entries, requires at least 2 stops to
    consider the multi-stop path active.
  • render.py — `_build_title_card_gradient` emits FFmpeg's
    `gradients=...:c0..cN-1=...:nb_colors=N` form when stops are set;
    falls back to the legacy 2-color `from_color` / `to_color` form
    when stops are absent or invalid.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from orchestrator.render import (  # noqa: E402
    _build_title_card_gradient,
)
from orchestrator.timeline import _normalize_clip  # noqa: E402


class TestNormalizerStops(unittest.TestCase):
    """Gradient normalization lives inside _normalize_overlay_content,
    which runs only for clips that have ``overlay_type`` set. The
    gradient itself is nested under ``overlay_content``."""

    def _norm(self, gradient: dict) -> dict:
        clip = {
            "id": "c1",
            "track_position_ms": 0,
            "in_point_ms": 0,
            "out_point_ms": 2000,
            "overlay_type": "title-card",
            "overlay_content": {"gradient": gradient},
        }
        return _normalize_clip(clip)

    def _grad(self, gradient: dict) -> dict:
        return self._norm(gradient)["overlay_content"]["gradient"]

    def test_normalizes_three_stop_gradient(self) -> None:
        g = self._grad({
            "kind": "linear",
            "stops": ["#ff0000", "#00ff00", "#0000ff"],
        })
        self.assertEqual(g["stops"], ["#ff0000", "#00ff00", "#0000ff"])

    def test_caps_stops_at_eight(self) -> None:
        many = [f"#{i:02x}{i:02x}{i:02x}" for i in range(12)]
        g = self._grad({"kind": "linear", "stops": many})
        self.assertEqual(len(g["stops"]), 8,
                         "FFmpeg's gradients filter caps at 8 colors")

    def test_drops_stops_when_only_one_valid_entry(self) -> None:
        g = self._grad({
            "kind": "linear",
            "stops": ["#ff0000", "", "   "],
        })
        self.assertNotIn("stops", g)

    def test_accepts_dict_stop_form(self) -> None:
        g = self._grad({
            "kind": "linear",
            "stops": [
                {"color": "#ff0000", "position": 0.0},
                {"color": "#00ff00", "position": 0.5},
                {"color": "#0000ff", "position": 1.0},
            ],
        })
        self.assertEqual(g["stops"], ["#ff0000", "#00ff00", "#0000ff"])

    def test_legacy_two_color_still_works(self) -> None:
        g = self._grad({
            "kind": "linear",
            "from_color": "#aabbcc",
            "to_color": "#ddeeff",
        })
        self.assertEqual(g["from_color"], "#aabbcc")
        self.assertEqual(g["to_color"], "#ddeeff")
        self.assertNotIn("stops", g)

    def test_kind_none_is_preserved(self) -> None:
        g = self._grad({"kind": "none"})
        self.assertEqual(g["kind"], "none")
        self.assertNotIn("stops", g)


class TestRenderBuildsMultiStopFilter(unittest.TestCase):
    def setUp(self) -> None:
        self.clip = {
            "id": "tc-1", "kind": "title_card",
            "track_position_ms": 0, "duration_ms": 2000,
            "in_point_ms": 0, "out_point_ms": 2000,
        }
        self.canvas_size = "1920x1080"
        self.frame_rate = 30

    def _filter_str(self, gradient: dict) -> str:
        result = _build_title_card_gradient(
            self.clip, gradient, "between(t,0,2)",
            self.canvas_size, self.frame_rate,
        )
        self.assertIsNotNone(result)
        parts, _label = result
        # First filter part is the `gradients=...` source.
        return parts[0]

    def test_three_stop_gradient_emits_three_color_args(self) -> None:
        f = self._filter_str({
            "kind": "linear",
            "stops": ["#ff0000", "#00ff00", "#0000ff"],
        })
        self.assertIn("c0=0xff0000ff", f)
        self.assertIn("c1=0x00ff00ff", f)
        self.assertIn("c2=0x0000ffff", f)
        self.assertIn("nb_colors=3", f)

    def test_two_stop_gradient_via_stops_field(self) -> None:
        f = self._filter_str({
            "kind": "linear",
            "stops": ["#000000", "#ffffff"],
        })
        self.assertIn("c0=0x000000ff", f)
        self.assertIn("c1=0xffffffff", f)
        self.assertIn("nb_colors=2", f)
        self.assertNotIn("c2=", f)

    def test_eight_stop_gradient_at_filter_limit(self) -> None:
        stops = [f"#{i*16:02x}{i*16:02x}{i*16:02x}" for i in range(8)]
        f = self._filter_str({"kind": "linear", "stops": stops})
        self.assertIn("nb_colors=8", f)
        self.assertIn("c7=", f)
        self.assertNotIn("c8=", f, "FFmpeg gradients filter has no c8")

    def test_falls_back_to_two_color_when_stops_absent(self) -> None:
        f = self._filter_str({
            "kind": "linear",
            "from_color": "#112233",
            "to_color": "#445566",
        })
        self.assertIn("c0=0x112233ff", f)
        self.assertIn("c1=0x445566ff", f)
        self.assertIn("nb_colors=2", f)

    def test_falls_back_when_stops_has_only_one_entry(self) -> None:
        # Multi-stop requires ≥ 2 colors; with one we use the legacy
        # from_color/to_color path.
        f = self._filter_str({
            "kind": "linear",
            "stops": ["#abcdef"],
            "from_color": "#001122",
            "to_color":   "#334455",
        })
        self.assertIn("c0=0x001122ff", f)
        self.assertIn("c1=0x334455ff", f)
        self.assertNotIn("0xabcdef", f)

    def test_radial_kind_uses_type_one(self) -> None:
        f = self._filter_str({
            "kind": "radial",
            "stops": ["#000000", "#ffffff"],
        })
        self.assertIn("type=1", f)

    def test_linear_kind_uses_type_zero(self) -> None:
        f = self._filter_str({
            "kind": "linear",
            "stops": ["#000000", "#ffffff"],
        })
        self.assertIn("type=0", f)

    def test_kind_none_returns_none(self) -> None:
        result = _build_title_card_gradient(
            self.clip, {"kind": "none"}, "between(t,0,2)",
            self.canvas_size, self.frame_rate,
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
