"""Tests for the Whisper non-speech hallucination filter.

The filter is a pure function — it takes a list of segment dicts and
returns a filtered list plus a drop count. We don't exercise the full
transcription pipeline here (that requires whisper.cpp + audio); we
verify the filter's matching rules.

Coverage:
  • Known closing-credit hallucinations are dropped.
  • Music-symbol-only segments are dropped.
  • Adjacent duplicate segments: keep the first 2, drop the 3rd+.
  • Real "thank you" alone is NOT dropped (too risky a false positive).
  • Real "[music]" alone is NOT dropped (legitimate caption text).
  • Empty segments don't trigger drops.
  • Whitespace and capitalization variations are normalized.
  • Drop count tallies correctly.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from orchestrator.transcription import (  # noqa: E402
    _filter_hallucinations,
    _is_hallucination,
    _normalize_for_hallucination_check,
)


def seg(start_ms: int, end_ms: int, text: str) -> dict:
    return {"start_ms": start_ms, "end_ms": end_ms, "text": text}


class TestNormalize(unittest.TestCase):
    def test_strips_and_lowercases(self) -> None:
        self.assertEqual(
            _normalize_for_hallucination_check("  THANKS for Watching!  "),
            "thanks for watching!"
        )

    def test_collapses_internal_whitespace(self) -> None:
        self.assertEqual(
            _normalize_for_hallucination_check("thanks  for\twatching"),
            "thanks for watching"
        )

    def test_handles_empty(self) -> None:
        self.assertEqual(_normalize_for_hallucination_check(""), "")
        self.assertEqual(_normalize_for_hallucination_check("   "), "")
        self.assertEqual(_normalize_for_hallucination_check(None), "")


class TestIsHallucination(unittest.TestCase):
    def test_thanks_for_watching_variants(self) -> None:
        for variant in [
            "Thanks for watching!",
            "thanks for watching",
            "  Thanks For Watching.  ",
            "thanks for watching!",
        ]:
            self.assertTrue(_is_hallucination(variant),
                            f"should flag: {variant!r}")

    def test_subscribe_variants(self) -> None:
        for v in ["Please subscribe", "Subscribe to my channel!",
                  "Subscribe to the channel"]:
            self.assertTrue(_is_hallucination(v))

    def test_subtitles_credit(self) -> None:
        self.assertTrue(_is_hallucination(
            "Subtitles by the Amara.org community"))
        self.assertTrue(_is_hallucination("subtitles by"))

    def test_music_symbol_alone(self) -> None:
        self.assertTrue(_is_hallucination("♪"))
        self.assertTrue(_is_hallucination("♪ ♪ ♪"))

    def test_real_speech_not_flagged(self) -> None:
        # These are ambiguous — could be hallucinations OR legit speech.
        # The filter is conservative and lets them through.
        for v in ["Thank you.", "thank you", "Hello", "Yeah",
                  "[music]", "[Music]", "(music)",
                  "We thank you for watching this presentation",
                  "Don't forget to subscribe to our newsletter"]:
            self.assertFalse(_is_hallucination(v),
                             f"should NOT flag: {v!r}")

    def test_empty_not_flagged(self) -> None:
        self.assertFalse(_is_hallucination(""))
        self.assertFalse(_is_hallucination("   "))


class TestFilterHallucinations(unittest.TestCase):
    def test_drops_known_pattern(self) -> None:
        segs = [
            seg(0, 1000, "Hello there."),
            seg(1000, 2000, "Thanks for watching!"),
            seg(2000, 3000, "See you next time."),
        ]
        kept, drops = _filter_hallucinations(segs)
        self.assertEqual(len(kept), 2)
        self.assertEqual(drops, 1)
        self.assertEqual(kept[0]["text"], "Hello there.")
        self.assertEqual(kept[1]["text"], "See you next time.")

    def test_drops_multiple_known_patterns(self) -> None:
        segs = [
            seg(0, 1000, "Hello."),
            seg(1000, 2000, "Thanks for watching!"),
            seg(2000, 3000, "Please subscribe!"),
            seg(3000, 4000, "Subscribe to my channel"),
            seg(4000, 5000, "Goodbye."),
        ]
        kept, drops = _filter_hallucinations(segs)
        self.assertEqual(len(kept), 2)
        self.assertEqual(drops, 3)

    def test_keeps_first_two_consecutive_duplicates(self) -> None:
        # 2 consecutive identical segments → both kept (real speech can
        # repeat).
        segs = [
            seg(0, 1000, "Yeah"),
            seg(1000, 2000, "Yeah"),
            seg(2000, 3000, "Okay let's go."),
        ]
        kept, drops = _filter_hallucinations(segs)
        self.assertEqual(len(kept), 3)
        self.assertEqual(drops, 0)

    def test_drops_third_plus_consecutive_duplicate(self) -> None:
        # 4 consecutive identical → keep first 2, drop next 2.
        segs = [
            seg(0, 1000, "yeah"),
            seg(1000, 2000, "yeah"),
            seg(2000, 3000, "yeah"),
            seg(3000, 4000, "yeah"),
            seg(4000, 5000, "Okay."),
        ]
        kept, drops = _filter_hallucinations(segs)
        self.assertEqual(len(kept), 3,
                         "should keep first 2 'yeah' + 'Okay.'")
        self.assertEqual(drops, 2)
        self.assertEqual(kept[0]["text"], "yeah")
        self.assertEqual(kept[1]["text"], "yeah")
        self.assertEqual(kept[2]["text"], "Okay.")

    def test_normalization_makes_repetition_match_case_insensitive(self) -> None:
        segs = [
            seg(0, 1000, "Yes"),
            seg(1000, 2000, "yes"),
            seg(2000, 3000, "YES"),
            seg(3000, 4000, "yes"),
        ]
        kept, drops = _filter_hallucinations(segs)
        self.assertEqual(len(kept), 2,
                         "case-insensitive repetition: keep first 2 only")
        self.assertEqual(drops, 2)

    def test_empty_segments_pass_through(self) -> None:
        # Empty-text segments are kept (could be silence-marker placeholders);
        # they don't count as repetitions of each other.
        segs = [
            seg(0, 1000, ""),
            seg(1000, 2000, ""),
            seg(2000, 3000, ""),
        ]
        kept, drops = _filter_hallucinations(segs)
        self.assertEqual(len(kept), 3)
        self.assertEqual(drops, 0)

    def test_combined_pattern_and_repetition(self) -> None:
        segs = [
            seg(0, 1000, "Hello"),
            seg(1000, 2000, "Thanks for watching!"),  # pattern drop
            seg(2000, 3000, "Hello"),                  # repetition counter resets
            seg(3000, 4000, "Hello"),                  # 2nd consecutive — keep
            seg(4000, 5000, "Hello"),                  # 3rd — drop
        ]
        kept, drops = _filter_hallucinations(segs)
        self.assertEqual(drops, 2)
        self.assertEqual([s["text"] for s in kept],
                         ["Hello", "Hello", "Hello"])

    def test_pattern_drop_resets_repetition_counter(self) -> None:
        # If a pattern hallucination sits between repeats, it resets the
        # counter — we shouldn't penalize the user for Whisper's noise.
        segs = [
            seg(0, 1000, "yeah"),
            seg(1000, 2000, "yeah"),
            seg(2000, 3000, "Thanks for watching!"),  # pattern drop
            seg(3000, 4000, "yeah"),                  # counter reset
            seg(4000, 5000, "yeah"),                  # 2nd after reset — keep
        ]
        kept, drops = _filter_hallucinations(segs)
        self.assertEqual(drops, 1)
        self.assertEqual(len(kept), 4)

    def test_empty_input_returns_empty(self) -> None:
        kept, drops = _filter_hallucinations([])
        self.assertEqual(kept, [])
        self.assertEqual(drops, 0)

    def test_segment_objects_are_returned_intact(self) -> None:
        # The filter should preserve segment dicts as-is — same start/end/text,
        # not lossy / not coerced.
        original = seg(123, 456, "Hello there.")
        kept, _ = _filter_hallucinations([original])
        self.assertEqual(len(kept), 1)
        self.assertIs(kept[0], original,
                      "filter should pass dicts by reference, not copy")


if __name__ == "__main__":
    unittest.main()
