"""Unit tests for the Output Styles card-label helpers + custom-entry compose."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import style_assembly as sa  # noqa: E402


class TestStyleCards(unittest.TestCase):

    def test_arrangement_short(self):
        assert sa.arrangement_short("inverted-pyramid") == "inverted pyr."
        assert sa.arrangement_short("bottom-line-up-front") == "bottom-line"
        assert sa.arrangement_short("unknown-thing") == "unknown thing"

    def test_elaboration_label(self):
        assert sa.elaboration_label(2) == "essentials"
        assert sa.elaboration_label(5) == "exhaustive"
        assert sa.elaboration_label(99) == "exhaustive"
        assert sa.elaboration_label(None) == "balanced"

    def test_compose_merges_custom_entry(self):
        custom = {"mine": {
            "display_name": "Mine", "arrangement": "answer-first",
            "demeanor": {"warmth": "warm"}, "elaboration": 2,
            "register_default": "written"}}
        block = sa.compose("mine", gear=4, custom_entries=custom)
        assert "STYLE" in block and "ARRANGEMENT" in block
        assert "STYLE" in sa.compose("business", gear=4, custom_entries=custom)

    def test_conversational_override_only_affects_gears_1_2(self):
        reg = sa.load_registry()
        axes, _ = sa.load_demeanor_axes()
        base = dict(reg["explainer"])
        base["conversational"] = {"demeanor": {"warmth": "cool"}}
        custom = {"mine": base}

        conv_block = sa.compose(
            "mine", register="conversational", gear=2, custom_entries=custom)
        assert axes["warmth"]["cool"] in conv_block
        assert axes["warmth"]["warm"] not in conv_block

        written_block = sa.compose("mine", gear=4, custom_entries=custom)
        assert axes["warmth"]["warm"] in written_block
        assert axes["warmth"]["cool"] not in written_block


if __name__ == "__main__":
    unittest.main()
