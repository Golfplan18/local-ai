"""Slice A: the /style one-off command parsing in parse_user_command."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boot  # noqa: E402


def p(s):
    return boot.parse_user_command(s)


def test_returns_four_tuple():
    assert len(p("hello")) == 4


def test_plain_input_has_no_override():
    clean, use_pipe, target, override = p("just a normal message")
    assert clean == "just a normal message"
    assert use_pipe is True and target == "screen"
    assert override is None


def test_style_known_id_strips_and_sets():
    clean, _, _, override = p("/style technical Write me a spec")
    assert clean == "Write me a spec"
    assert override == {"style_id": "technical"}


def test_style_off_clears_for_this_turn():
    clean, _, _, override = p("/style off back to normal")
    assert clean == "back to normal"
    assert override == {"style_id": ""}


def test_unknown_style_passes_through_as_text():
    clean, _, _, override = p("/style nonexistentstyle hi")
    assert clean == "/style nonexistentstyle hi"   # left intact — likely a typo
    assert override is None


def test_other_commands_unaffected():
    clean, use_pipe, _, override = p("/direct hello")
    assert clean == "hello" and use_pipe is False and override is None


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS  " + t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL  %s -> %r" % (t.__name__, exc))
    print("\n%d/%d passed" % (len(tests) - failed, len(tests)))
    sys.exit(1 if failed else 0)
