"""Unit tests for style_store — custom Output Style profile persistence.

Each test redirects STORE_PATH to a fresh temp file so the live
~/ora/data/custom-styles.json is never touched."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import style_store as ss  # noqa: E402


def _fresh_store():
    d = tempfile.mkdtemp()
    ss.STORE_PATH = os.path.join(d, "custom-styles.json")
    return ss.STORE_PATH


class TestStyleStore(unittest.TestCase):

    def setUp(self):
        _fresh_store()

    def test_create_and_load(self):
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

    def test_update_merges_nested_blocks(self):
        prof = ss.create_custom_profile(base_entry={
            "display_name": "X", "demeanor": {"warmth": "warm", "force": "measured"}})
        upd = ss.update_custom_profile(prof["id"],
                                       {"demeanor": {"force": "forceful"}, "elaboration": 5})
        assert upd["demeanor"]["warmth"] == "warm"
        assert upd["demeanor"]["force"] == "forceful"
        assert upd["elaboration"] == 5

    def test_update_ignores_unknown_field(self):
        prof = ss.create_custom_profile(base_entry={"display_name": "X"})
        upd = ss.update_custom_profile(prof["id"],
                                       {"evil": "nope", "arrangement": "goal-steps"})
        assert "evil" not in upd
        assert upd["arrangement"] == "goal-steps"

    def test_unique_ids_never_shadow_a_builtin(self):
        a = ss.create_custom_profile(base_entry={"display_name": "Business"})
        assert a["id"] != "business"
        b = ss.create_custom_profile(base_entry={"display_name": "Business"})
        assert a["id"] != b["id"]

    def test_delete(self):
        prof = ss.create_custom_profile(base_entry={"display_name": "X"})
        assert ss.delete_custom_profile(prof["id"]) is True
        assert ss.load_custom_profiles() == {}
        assert ss.delete_custom_profile(prof["id"]) is False

    def test_update_unknown_returns_none(self):
        assert ss.update_custom_profile("does-not-exist", {"arrangement": "x"}) is None

    def test_missing_store_is_empty(self):
        assert ss.load_custom_profiles() == {}

    def test_conversational_override_merge_and_clear(self):
        prof = ss.create_custom_profile(base_entry={"display_name": "X",
                                                    "demeanor": {"warmth": "warm"}})
        pid = prof["id"]
        upd = ss.update_custom_profile(pid, {"conversational": {"demeanor": {"warmth": "cool"}}})
        assert upd["conversational"]["demeanor"]["warmth"] == "cool"
        upd = ss.update_custom_profile(pid, {"conversational": {"demeanor": {"force": "forceful"}}})
        assert upd["conversational"]["demeanor"]["warmth"] == "cool"
        assert upd["conversational"]["demeanor"]["force"] == "forceful"
        upd = ss.update_custom_profile(pid, {"conversational": None})
        assert "conversational" not in upd


if __name__ == "__main__":
    unittest.main()
