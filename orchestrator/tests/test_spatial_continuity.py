#!/usr/bin/env python3
"""
WP-5.3 — Spatial continuity across turns (unit + integration tests).

Runs under stdlib ``unittest`` — no pytest dependency. Invoke::

    /opt/homebrew/bin/python3 -m unittest discover -s ~/ora/orchestrator/tests -v

Scope:
* ``conversation_memory.get_prior_spatial_state`` walks history/disk backwards
  and returns the most recent user-turn spatial_representation.
* ``conversation_memory.save_turn_spatial_state`` persists spatial fields
  into ``~/ora/sessions/<id>/conversation.json`` and round-trips cleanly.
* ``boot.build_system_prompt_for_gear`` injects PRIOR + CURRENT fences as
  the turn-sequence dictates; absent prior ⇒ no PRIOR fence.
* Backward compat: a conversation with no spatial fields returns ``None``
  and the system prompt carries no PRIOR fence.
* The layout-preservation instruction line accompanies any PRIOR fence.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
WORKSPACE = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))
sys.path.insert(0, str(WORKSPACE / "server"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _spatial_rep_turn1() -> dict:
    """3-entity partial causal structure — turn 1 baseline."""
    return {
        "entities": [
            {"id": "u-A", "position": [0.15, 0.50], "label": "Hiring"},
            {"id": "u-B", "position": [0.50, 0.50], "label": "Team size"},
            {"id": "u-C", "position": [0.85, 0.50], "label": "Coordination cost"},
        ],
        "relationships": [
            {"source": "u-A", "target": "u-B", "type": "causal"},
            {"source": "u-B", "target": "u-C", "type": "causal"},
        ],
    }


def _spatial_rep_turn2_modified() -> dict:
    """Turn-2 drawing: same three entities plus a new feedback edge."""
    return {
        "entities": [
            {"id": "u-A", "position": [0.15, 0.50], "label": "Hiring"},
            {"id": "u-B", "position": [0.50, 0.50], "label": "Team size"},
            {"id": "u-C", "position": [0.85, 0.50], "label": "Coordination cost"},
        ],
        "relationships": [
            {"source": "u-A", "target": "u-B", "type": "causal"},
            {"source": "u-B", "target": "u-C", "type": "causal"},
            {"source": "u-C", "target": "u-A", "type": "causal"},
        ],
    }


def _minimal_context_pkg(
    *,
    spatial_rep: dict | None = None,
    prior_spatial: dict | None = None,
) -> dict:
    """Minimal context_pkg for build_system_prompt_for_gear."""
    mode_path = WORKSPACE / "modes" / "spatial-reasoning.md"
    mode_text = mode_path.read_text() if mode_path.exists() else "# Spatial Reasoning\n"
    ctx = {
        "mode_text": mode_text,
        "mode_name": "spatial-reasoning",
        "conversation_rag": "",
        "concept_rag": "",
        "relationship_rag": "",
        "rag_utilization": "",
    }
    if spatial_rep is not None:
        ctx["spatial_representation"] = spatial_rep
    if prior_spatial is not None:
        ctx["prior_spatial_representation"] = prior_spatial
    return ctx


# ---------------------------------------------------------------------------
# 1) get_prior_spatial_state — in-memory history walks
# ---------------------------------------------------------------------------


class PriorStateFromHistoryTests(unittest.TestCase):
    """Walking a passed-in history list identifies the most recent user-turn
    spatial_representation."""

    def test_two_turn_history_returns_turn1_spatial(self) -> None:
        from conversation_memory import get_prior_spatial_state
        history = [
            {
                "role": "user",
                "content": "What feedback loops emerge here?",
                "spatial_representation": _spatial_rep_turn1(),
            },
            {
                "role": "assistant",
                "content": "Here is a possible loop...",
            },
        ]
        prior = get_prior_spatial_state("no-such-session", history)
        self.assertIsNotNone(prior)
        self.assertEqual(len(prior["entities"]), 3)
        self.assertEqual(prior["entities"][0]["id"], "u-A")

    def test_three_turn_history_with_spatial_only_on_first_turn(self) -> None:
        """If user drew on turn 1 but not on turns 2 or 3, the prior state
        for turn 3 must still be turn 1's drawing."""
        from conversation_memory import get_prior_spatial_state
        history = [
            {
                "role": "user",
                "content": "Here is my map.",
                "spatial_representation": _spatial_rep_turn1(),
            },
            {"role": "assistant", "content": "Noted."},
            {
                "role": "user",
                "content": "Any refinements?",
                "spatial_representation": None,
            },
            {"role": "assistant", "content": "Perhaps..."},
        ]
        prior = get_prior_spatial_state("none", history)
        self.assertIsNotNone(prior)
        self.assertEqual(len(prior["entities"]), 3)

    def test_most_recent_user_turn_wins(self) -> None:
        """When multiple user turns carry spatial_representation, the most
        recent one is returned."""
        from conversation_memory import get_prior_spatial_state
        history = [
            {
                "role": "user",
                "content": "turn 1",
                "spatial_representation": _spatial_rep_turn1(),
            },
            {"role": "assistant", "content": "ok"},
            {
                "role": "user",
                "content": "turn 2",
                "spatial_representation": _spatial_rep_turn2_modified(),
            },
            {"role": "assistant", "content": "ok"},
        ]
        prior = get_prior_spatial_state("none", history)
        self.assertIsNotNone(prior)
        # Turn 2 has 3 relationships; turn 1 has only 2.
        self.assertEqual(len(prior["relationships"]), 3)

    def test_empty_history_returns_none(self) -> None:
        from conversation_memory import get_prior_spatial_state
        prior = get_prior_spatial_state("none", [])
        self.assertIsNone(prior)

    def test_history_without_spatial_fields_returns_none(self) -> None:
        """Backward compat: a conversation from the pre-WP-5.3 era has no
        spatial_representation keys on its turns — must return None."""
        from conversation_memory import get_prior_spatial_state
        history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        prior = get_prior_spatial_state("none", history)
        self.assertIsNone(prior)

    def test_returned_snapshot_is_safe_to_mutate(self) -> None:
        """The returned dict must be a deep copy — mutating it must not
        affect the history."""
        from conversation_memory import get_prior_spatial_state
        original = _spatial_rep_turn1()
        history = [
            {"role": "user", "content": "hi", "spatial_representation": original},
        ]
        prior = get_prior_spatial_state("none", history)
        prior["entities"].append({"id": "u-Z", "position": [0, 0], "label": "poison"})
        # Original (and history) unchanged.
        self.assertEqual(len(original["entities"]), 3)
        self.assertEqual(len(history[0]["spatial_representation"]["entities"]), 3)


# ---------------------------------------------------------------------------
# 2) save_turn_spatial_state + load → round-trip
# ---------------------------------------------------------------------------


class ConversationJsonPersistenceTests(unittest.TestCase):
    """save_turn_spatial_state writes a conversation.json. Subsequent loads
    see the spatial fields verbatim."""

    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="ora-wp53-"))

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_save_creates_conversation_json_with_spatial_fields(self) -> None:
        from conversation_memory import save_turn_spatial_state, load_conversation_json
        rep = _spatial_rep_turn1()
        path = save_turn_spatial_state(
            conversation_id="sess-1",
            user_input="draw this",
            ai_response="looks good",
            spatial_representation=rep,
            timestamp="2026-04-17T10:00:00",
            sessions_root=self._tmp,
        )
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())
        data = load_conversation_json("sess-1", sessions_root=self._tmp)
        self.assertIsNotNone(data)
        self.assertEqual(len(data["messages"]), 2)
        user_turn = data["messages"][0]
        self.assertEqual(user_turn["role"], "user")
        self.assertEqual(user_turn["spatial_representation"]["entities"][0]["id"], "u-A")
        # Assistant turn has None placeholders (forward-compat).
        asst_turn = data["messages"][1]
        self.assertEqual(asst_turn["role"], "assistant")
        self.assertIsNone(asst_turn["spatial_representation"])
        self.assertIsNone(asst_turn["annotations"])
        self.assertIsNone(asst_turn["vision_extraction_result"])

    def test_save_append_preserves_prior_turns(self) -> None:
        from conversation_memory import save_turn_spatial_state, load_conversation_json
        save_turn_spatial_state(
            conversation_id="sess-2",
            user_input="turn 1 text",
            ai_response="response 1",
            spatial_representation=_spatial_rep_turn1(),
            sessions_root=self._tmp,
        )
        save_turn_spatial_state(
            conversation_id="sess-2",
            user_input="turn 2 text",
            ai_response="response 2",
            spatial_representation=None,  # no new drawing
            sessions_root=self._tmp,
        )
        data = load_conversation_json("sess-2", sessions_root=self._tmp)
        self.assertEqual(len(data["messages"]), 4)
        # First user turn preserved the spatial drawing.
        self.assertIsNotNone(data["messages"][0]["spatial_representation"])
        # Second user turn has None.
        self.assertIsNone(data["messages"][2]["spatial_representation"])

    def test_get_prior_spatial_state_reads_from_disk(self) -> None:
        """With an empty in-memory history, get_prior_spatial_state falls
        through to conversation.json on disk."""
        from conversation_memory import save_turn_spatial_state, get_prior_spatial_state
        save_turn_spatial_state(
            conversation_id="sess-3",
            user_input="turn 1",
            ai_response="resp 1",
            spatial_representation=_spatial_rep_turn1(),
            sessions_root=self._tmp,
        )
        prior = get_prior_spatial_state("sess-3", [], sessions_root=self._tmp)
        self.assertIsNotNone(prior)
        self.assertEqual(len(prior["entities"]), 3)

    def test_load_nonexistent_returns_none(self) -> None:
        """Backward compat + fresh-session path."""
        from conversation_memory import load_conversation_json
        data = load_conversation_json("missing-session", sessions_root=self._tmp)
        self.assertIsNone(data)

    def test_annotations_normalized_into_list_form(self) -> None:
        """Whether the caller passes the wrapper dict or a bare list, the
        persisted shape is always the bare list."""
        from conversation_memory import save_turn_spatial_state, load_conversation_json
        annot_list = [{"kind": "callout", "action": "expand", "target_id": "u-A", "text": "why?"}]
        # Shape 1: wrapper dict
        save_turn_spatial_state(
            conversation_id="s-w",
            user_input="u1",
            ai_response="a1",
            annotations={"annotations": annot_list},
            sessions_root=self._tmp,
        )
        data = load_conversation_json("s-w", sessions_root=self._tmp)
        self.assertIsInstance(data["messages"][0]["annotations"], list)
        self.assertEqual(len(data["messages"][0]["annotations"]), 1)
        # Shape 2: bare list
        save_turn_spatial_state(
            conversation_id="s-l",
            user_input="u1",
            ai_response="a1",
            annotations=annot_list,
            sessions_root=self._tmp,
        )
        data2 = load_conversation_json("s-l", sessions_root=self._tmp)
        self.assertIsInstance(data2["messages"][0]["annotations"], list)


# ---------------------------------------------------------------------------
# 3) build_system_prompt_for_gear — PRIOR fences
# ---------------------------------------------------------------------------


class PriorStatePromptInjectionTests(unittest.TestCase):
    """Verify the build_system_prompt_for_gear extension serializes the
    PRIOR spatial state under the correct header."""

    def setUp(self) -> None:
        from boot import build_system_prompt_for_gear
        self.build = build_system_prompt_for_gear

    def test_no_prior_no_current_no_fence(self) -> None:
        """Backward compat: no spatial state anywhere → serializer emitted
        neither PRIOR nor USER SPATIAL fences."""
        ctx = _minimal_context_pkg()
        prompt = self.build(ctx, slot="breadth")
        self.assertNotIn("=== PRIOR SPATIAL STATE", prompt)
        # Phase 4: the spatial-reasoning mode's EMISSION CONTRACT references
        # the literal ``=== USER SPATIAL INPUT ===`` as documentation. That
        # text is now injected into the assembled prompt even when no
        # spatial input was serialized. The close-tag marker, though, is
        # only emitted by ``serialize_spatial_representation_to_text``
        # — use it to assert the fence is absent.
        self.assertNotIn("=== END SPATIAL INPUT ===", prompt)

    def test_current_only_no_prior_fence(self) -> None:
        """User drew this turn but no prior state exists → USER SPATIAL
        INPUT fence present; PRIOR fence absent."""
        ctx = _minimal_context_pkg(spatial_rep=_spatial_rep_turn1())
        prompt = self.build(ctx, slot="breadth")
        self.assertIn("=== USER SPATIAL INPUT ===", prompt)
        self.assertNotIn("=== PRIOR SPATIAL STATE", prompt)

    def test_prior_only_persistent_label(self) -> None:
        """Prior exists but user didn't draw this turn → PRIOR fence uses
        the "persistent" label and the serialization includes the user's
        prior entities. No USER SPATIAL INPUT fence from the serializer."""
        ctx = _minimal_context_pkg(prior_spatial=_spatial_rep_turn1())
        prompt = self.build(ctx, slot="breadth")
        self.assertIn("=== PRIOR SPATIAL STATE (persistent) ===", prompt)
        self.assertIn("=== END PRIOR SPATIAL STATE ===", prompt)
        # Phase 4: see test_no_prior_no_current_no_fence — the USER SPATIAL
        # INPUT literal is now part of the spatial-reasoning EMISSION
        # CONTRACT documentation, so the close-tag marker is the reliable
        # check that the serializer did not emit a fence.
        self.assertNotIn("=== END SPATIAL INPUT ===", prompt)
        # The three entities from prior are in the serialization.
        for ent in _spatial_rep_turn1()["entities"]:
            self.assertIn(ent["id"], prompt)
            self.assertIn(ent["label"], prompt)

    def test_prior_and_current_both_fences_present(self) -> None:
        """Both states present → PRIOR (turn n-1) + USER SPATIAL INPUT
        fences both visible, prior above current in the assembled prompt."""
        ctx = _minimal_context_pkg(
            spatial_rep=_spatial_rep_turn2_modified(),
            prior_spatial=_spatial_rep_turn1(),
        )
        prompt = self.build(ctx, slot="breadth")
        self.assertIn("=== PRIOR SPATIAL STATE (turn n-1) ===", prompt)
        self.assertIn("=== END PRIOR SPATIAL STATE ===", prompt)
        self.assertIn("=== END SPATIAL INPUT ===", prompt)
        prior_idx = prompt.index("=== PRIOR SPATIAL STATE (turn n-1) ===")
        # Phase 4: the spatial-reasoning EMISSION CONTRACT mentions
        # ``=== USER SPATIAL INPUT ===`` as documentation, so use ``rfind``
        # to locate the actual serializer-emitted fence (the last
        # occurrence is always the real one since the serializer appends
        # after EMISSION CONTRACT).
        current_idx = prompt.rfind("=== USER SPATIAL INPUT ===")
        self.assertGreater(current_idx, 0, "serializer fence should appear")
        self.assertLess(
            prior_idx, current_idx,
            "PRIOR fence should appear before USER SPATIAL INPUT fence",
        )
        # Current turn's NEW edge should be in the USER SPATIAL INPUT
        # block, not in PRIOR.
        prior_block = prompt[prior_idx:current_idx]
        self.assertNotIn("u-C --(causal)--> u-A", prior_block)
        current_end = prompt.index("=== END SPATIAL INPUT ===")
        current_block = prompt[current_idx:current_end]
        self.assertIn("u-C --(causal)--> u-A", current_block)

    def test_layout_preservation_instruction_accompanies_prior(self) -> None:
        """Whenever a PRIOR fence appears, the layout-preservation
        instruction line must appear too so the model knows to either keep
        the arrangement or declare the change."""
        ctx = _minimal_context_pkg(prior_spatial=_spatial_rep_turn1())
        prompt = self.build(ctx, slot="breadth")
        self.assertIn("preserve layout", prompt)
        self.assertIn("declare the layout change with rationale", prompt)

    def test_no_preservation_instruction_when_no_prior(self) -> None:
        """Absent prior → no instruction line (avoid bloating the prompt)."""
        ctx = _minimal_context_pkg(spatial_rep=_spatial_rep_turn1())
        prompt = self.build(ctx, slot="breadth")
        self.assertNotIn("preserve layout", prompt)


# ---------------------------------------------------------------------------
# 4) Invariant: when the model's output mirrors input layout, element IDs
# survive end-to-end through the envelope annotation path.
# ---------------------------------------------------------------------------


class LayoutPreservationInvariantTests(unittest.TestCase):
    """Hand-crafted mock: if the analytical model emits an annotate
    envelope whose target_ids match the user's spatial_representation, the
    annotation compiler binds to the user's elements (not newly
    generated ones). This is the layout-preservation invariant at the
    data-flow level."""

    def test_annotate_targets_match_user_entity_ids(self) -> None:
        from visual_validator import validate_envelope
        user_rep = _spatial_rep_turn1()
        user_ids = {e["id"] for e in user_rep["entities"]}

        envelope = {
            "schema_version": "0.2",
            "id": "preserve-test",
            "type": "concept_map",
            "mode_context": "spatial-reasoning",
            "relation_to_prose": "visually_native",
            "title": "Layout preserved",
            "canvas_action": "annotate",
            "annotations": [
                {"target_id": "u-A", "kind": "callout", "text": "This is the driver."},
            ],
            "spec": {
                "focus_question": "?",
                "concepts": [
                    {"id": "u-A", "label": "Hiring", "hierarchy_level": 0},
                    {"id": "u-B", "label": "Team size", "hierarchy_level": 1},
                    {"id": "u-C", "label": "Coordination cost", "hierarchy_level": 2},
                ],
                "linking_phrases": [{"id": "lp-1", "text": "increases"}],
                "propositions": [
                    {"from_concept": "u-A", "via_phrase": "lp-1", "to_concept": "u-B"},
                ],
            },
            "semantic_description": {
                "level_1_elemental": "Three concepts.",
                "level_2_statistical": "2 of 3 propositions drawn.",
                "level_3_perceptual": "Chain preserved as baseline.",
                "short_alt": "Three concepts.",
            },
        }
        result = validate_envelope(envelope)
        self.assertTrue(result.valid, f"errors: {[e.message for e in result.errors]}")
        for a in envelope["annotations"]:
            self.assertIn(
                a["target_id"], user_ids,
                "annotate target_id must resolve to a user entity id",
            )


# ---------------------------------------------------------------------------
# 5) End-to-end server wiring — /chat/multipart threads prior spatial state
# ---------------------------------------------------------------------------


class _NoopThread:
    def __init__(self, *a, **k):
        pass
    def start(self):
        pass
    def join(self, *a, **k):
        pass
    daemon = True


class ServerPriorStateWiringTests(unittest.TestCase):
    """The /chat/multipart handler calls get_prior_spatial_state and stashes
    the result on extra_context so build_system_prompt_for_gear can inject
    the PRIOR fence."""

    def setUp(self) -> None:
        import server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()

    def test_prior_spatial_state_threaded_via_history(self) -> None:
        """When history carries a prior user turn with
        spatial_representation, /chat/multipart stashes it on
        extra_context as ``prior_spatial_representation``."""
        captured: dict = {}

        def fake_stream(clean_input, history, use_pipeline=True,
                        panel_id="main", images=None, extra_context=None, **kwargs):
            captured["extra_context"] = extra_context
            yield self.server._sse("pipeline_stage", stage="step1_cleanup",
                                    mode="spatial-reasoning", gear=3)
            yield self.server._sse("pipeline_stage", stage="complete", gear=3)
            yield self.server._sse("response", text="ok")

        history = [
            {
                "role": "user",
                "content": "first turn",
                "spatial_representation": _spatial_rep_turn1(),
            },
            {"role": "assistant", "content": "noted"},
        ]

        with mock.patch.object(self.server, "agentic_loop_stream", fake_stream), \
             mock.patch.object(self.server.threading, "Thread", _NoopThread):
            resp = self.client.post(
                "/chat/multipart",
                data={
                    "message": "follow-up without new drawing",
                    "conversation_id": "wp53-e2e-history",
                    "history": json.dumps(history),
                    "is_main_feed": "true",
                },
                content_type="multipart/form-data",
            )
            # Drain the SSE so generate() runs to completion.
            resp.get_data(as_text=True)

        extra = captured.get("extra_context") or {}
        self.assertIn("prior_spatial_representation", extra)
        self.assertEqual(len(extra["prior_spatial_representation"]["entities"]), 3)
        # Current-turn spatial absent (user didn't draw this turn).
        self.assertNotIn("spatial_representation", extra)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
