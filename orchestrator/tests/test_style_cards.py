"""Unit tests for the Output Styles card-label helpers + custom-entry compose."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import style_assembly as sa  # noqa: E402


def test_arrangement_short():
    assert sa.arrangement_short("inverted-pyramid") == "inverted pyr."
    assert sa.arrangement_short("bottom-line-up-front") == "bottom-line"
    assert sa.arrangement_short("unknown-thing") == "unknown thing"   # graceful


def test_elaboration_label():
    assert sa.elaboration_label(2) == "essentials"
    assert sa.elaboration_label(5) == "exhaustive"
    assert sa.elaboration_label(99) == "exhaustive"   # clamped to 5
    assert sa.elaboration_label(None) == "balanced"   # defaults to 3


def test_demeanor_summary():
    reg = sa.load_registry()
    s = sa.demeanor_summary(reg["business"])
    assert s and s != "neutral"                       # business is marked
    parts = s.split(" · ")
    assert 1 <= len(parts) <= 2
    neutral = {"demeanor": {a: sa.RUNGS[a][1] for a in sa.AXIS_ORDER}}
    assert sa.demeanor_summary(neutral) == "neutral"


def test_compose_merges_custom_entry():
    custom = {"mine": {
        "display_name": "Mine", "arrangement": "answer-first",
        "demeanor": {"warmth": "warm"}, "elaboration": 2,
        "register_default": "written"}}
    block = sa.compose("mine", gear=4, custom_entries=custom)
    assert "STYLE" in block and "ARRANGEMENT" in block
    # built-ins still resolve when customs are supplied
    assert "STYLE" in sa.compose("business", gear=4, custom_entries=custom)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
