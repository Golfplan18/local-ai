"""Integration test for the Output Style injection in
build_system_prompt_for_gear. Imports the real boot module and builds system
prompts, asserting style appears only where it should. The load-bearing safety
property: with no style_id resolved onto the context, the prompt is unchanged."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boot  # noqa: E402

BASE = {
    "mode_text": "## DEPTH ANALYSIS GUIDANCE\nDepth.\n\n## BREADTH ANALYSIS GUIDANCE\nBreadth.\n",
    "mode_name": "Test",
    "conversation_rag": "", "concept_rag": "", "relationship_rag": "",
    "web_rag": "", "tool_results": "",
}


def _build(overrides, step="analyst"):
    ctx = dict(BASE)
    ctx.update(overrides)
    return boot.build_system_prompt_for_gear(ctx, "breadth", step)


def test_gear34_producing_steps_get_full_block():
    for step in ("analyst", "reviser", "consolidator", "formatter"):
        p = _build({"gear": 4, "style_id": "explainer"}, step)
        assert "SECONDARY TO SUBSTANCE" in p, step
        assert "motivation-first" in p, step


def test_evaluator_and_verifier_excluded():
    # Style must never reach the grading steps — a style mismatch can't fail a draft.
    for step in ("evaluator", "verifier"):
        p = _build({"gear": 4, "style_id": "explainer"}, step)
        assert "SECONDARY TO SUBSTANCE" not in p, step


def test_gear12_gets_compact_demeanor_only():
    p = _build({"gear": 2, "style_id": "explainer"})
    assert "DEMEANOR (this turn)" in p
    assert "SECONDARY TO SUBSTANCE" not in p


def test_default_unchanged_without_style_id():
    on = _build({"gear": 4, "style_id": "explainer"})
    off = _build({"gear": 4})
    assert "SECONDARY TO SUBSTANCE" not in off
    assert "DEMEANOR (this turn)" not in off
    assert off != on


def test_one_off_swap_changes_block():
    a = _build({"gear": 4, "style_id": "explainer"})
    b = _build({"gear": 4, "style_id": "business"})
    assert a != b
    assert "bottom-line-up-front" in b


def test_situational_delta_edits_block():
    a = _build({"gear": 4, "style_id": "explainer"})
    b = _build({"gear": 4, "style_id": "explainer", "style_deltas": {"warmth": -1}})
    assert a != b


def test_bogus_style_id_is_safe_noop():
    # Best-effort: an unknown style never raises.
    assert isinstance(_build({"gear": 4, "style_id": "nope-not-real"}), str)


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
