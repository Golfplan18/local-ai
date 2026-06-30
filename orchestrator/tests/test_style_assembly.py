"""Unit tests for style_assembly — runs the assembly against the real
frameworks/book/style-*.md files. Run directly (`python3 test_style_assembly.py`)
or via pytest."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import style_assembly as sa  # noqa: E402

GENRES = ["conversational", "explainer", "technical", "how-to", "journalism",
          "business", "white-paper", "academic", "legal", "marketing",
          "reference", "narrative"]


def test_registry_loads_all_genres():
    reg = sa.load_registry()
    assert set(GENRES).issubset(reg), "missing genres: %s" % (set(GENRES) - set(reg))
    assert reg["explainer"]["demeanor"]["warmth"] == "warm"
    assert reg["business"]["arrangement"] == "bottom-line-up-front"


def test_axes_and_rungs_match_library():
    axes, devices = sa.load_demeanor_axes()
    assert set(sa.AXIS_ORDER) == set(axes), axes.keys()
    for axis, rungs in sa.RUNGS.items():
        assert set(rungs) == set(axes[axis]), (axis, list(axes[axis]))
    assert {"sarcasm", "irony", "hyperbole", "understatement"} <= set(devices)


def test_every_genre_composes_both_blocks():
    for g in GENRES:
        full = sa.compose(g, gear=3)
        compact = sa.compose(g, gear=1)
        assert "SECONDARY TO SUBSTANCE" in full
        assert "(schema not found)" not in full, "%s: arrangement id mismatch" % g
        assert "DEMEANOR (this turn)" in compact


def test_full_block_explainer_content():
    b = sa.compose("explainer", gear=3)
    assert "ARRANGEMENT (motivation-first):" in b
    assert "hook" in b                       # schema prose
    assert "reasonable" in b                 # warmth=warm rung line
    assert "Elaboration 3 of 5" in b
    assert "Avoid:" in b                     # explainer forbidden glossary


def test_compact_block_is_demeanor_only():
    b = sa.compose("explainer", gear=1)
    assert "reasonable" in b                 # warmth=warm
    assert sa.VALUES_FLOOR_LINE in b
    assert sa.COMPLETENESS_LINE in b
    assert "motivation-first" not in b       # no arrangement in the compact block


def test_one_off_swap_changes_everything():
    a = sa.compose("explainer", gear=3)
    b = sa.compose("business", gear=3)
    assert a != b
    assert "bottom-line-up-front" in b
    assert "defend it" in b                  # business force=forceful rung line


def test_situational_delta_swaps_one_rung_only():
    base = sa.compose("technical", gear=1)            # warmth=cool, force=measured
    bumped = sa.compose("technical", gear=1, deltas={"warmth": 1})  # cool -> even
    assert "without acknowledging" in base            # cool line
    assert "Address the reader plainly" in bumped     # even line
    assert "without acknowledging" not in bumped      # only warmth moved
    # an untouched axis is identical in both:
    assert "State your view plainly and back it" in base
    assert "State your view plainly and back it" in bumped


def test_delta_clamps_at_bound():
    b = sa.compose("explainer", gear=1, deltas={"warmth": 1})  # already 'warm' (top)
    assert "reasonable" in b                 # stays warm, no out-of-range


def test_unknown_style_raises():
    try:
        sa.compose("does-not-exist")
    except KeyError:
        return
    raise AssertionError("expected KeyError for unknown style_id")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS  %s" % t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL  %s -> %r" % (t.__name__, exc))
    print("\n%d/%d passed" % (len(tests) - failed, len(tests)))
    sys.exit(1 if failed else 0)
