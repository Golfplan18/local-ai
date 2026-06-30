"""Unit tests for style_store — custom Output Style profile persistence.

Each test redirects STORE_PATH to a fresh temp file so the live
~/ora/data/custom-styles.json is never touched."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import style_store as ss  # noqa: E402


def _fresh_store():
    d = tempfile.mkdtemp()
    ss.STORE_PATH = os.path.join(d, "custom-styles.json")
    return ss.STORE_PATH


def test_create_and_load():
    _fresh_store()
    base = {"display_name": "Explainer", "arrangement": "motivation-first",
            "demeanor": {"warmth": "warm"}, "elaboration": 3}
    prof = ss.create_custom_profile(base_entry=base, forked_from="explainer")
    assert prof["custom"] is True
    assert prof["id"]
    assert prof["forked_from"] == "explainer"
    loaded = ss.load_custom_profiles()
    assert prof["id"] in loaded
    assert loaded[prof["id"]]["arrangement"] == "motivation-first"
    assert loaded[prof["id"]]["custom"] is True


def test_update_merges_nested_blocks():
    _fresh_store()
    prof = ss.create_custom_profile(base_entry={
        "display_name": "X", "demeanor": {"warmth": "warm", "force": "measured"}})
    upd = ss.update_custom_profile(prof["id"],
                                   {"demeanor": {"force": "forceful"}, "elaboration": 5})
    assert upd["demeanor"]["warmth"] == "warm"      # untouched axis preserved
    assert upd["demeanor"]["force"] == "forceful"   # patched axis changed
    assert upd["elaboration"] == 5


def test_update_ignores_unknown_field():
    _fresh_store()
    prof = ss.create_custom_profile(base_entry={"display_name": "X"})
    upd = ss.update_custom_profile(prof["id"],
                                   {"evil": "nope", "arrangement": "goal-steps"})
    assert "evil" not in upd
    assert upd["arrangement"] == "goal-steps"


def test_unique_ids_never_shadow_a_builtin():
    _fresh_store()
    a = ss.create_custom_profile(base_entry={"display_name": "Business"})
    assert a["id"] != "business"          # would shadow the genre otherwise
    b = ss.create_custom_profile(base_entry={"display_name": "Business"})
    assert a["id"] != b["id"]             # second copy gets a distinct id


def test_delete():
    _fresh_store()
    prof = ss.create_custom_profile(base_entry={"display_name": "X"})
    assert ss.delete_custom_profile(prof["id"]) is True
    assert ss.load_custom_profiles() == {}
    assert ss.delete_custom_profile(prof["id"]) is False


def test_update_unknown_returns_none():
    _fresh_store()
    assert ss.update_custom_profile("does-not-exist", {"arrangement": "x"}) is None


def test_missing_store_is_empty():
    _fresh_store()  # path points at a dir with no file yet
    assert ss.load_custom_profiles() == {}


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
