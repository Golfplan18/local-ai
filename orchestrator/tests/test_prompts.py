"""Tests for cleanup prompt templates (Phase 1.7).

Verifies:
  - System prompts have key directives
  - Paste-marker insertion preserves source order
  - Output parser detects missing/extra markers
  - Output parser substitutes original paste content even if the model
    drifts inside markers (drift flagged as warning)
"""

from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical.prompts import (  # noqa: E402
    AI_CLEANUP_SYSTEM,
    USER_CLEANUP_SYSTEM,
    build_ai_cleanup_call,
    build_user_cleanup_call,
    build_user_cleanup_call_interleaved,
    extract_user_cleanup_result,
)


# ---------------------------------------------------------------------------
# System prompt content guards
# ---------------------------------------------------------------------------


class TestSystemPrompts(unittest.TestCase):

    def test_user_prompt_mentions_paste_markers(self):
        self.assertIn("PASTE_START", USER_CLEANUP_SYSTEM)
        self.assertIn("PASTE_END", USER_CLEANUP_SYSTEM)
        self.assertIn("LEAVE PASTED CONTENT EXACTLY AS-IS",
                      USER_CLEANUP_SYSTEM)

    def test_user_prompt_says_no_summarization(self):
        # Must preserve thoughts, not summarize.
        self.assertIn("PRESERVE 100%", USER_CLEANUP_SYSTEM)
        self.assertIn("MEANING must remain intact", USER_CLEANUP_SYSTEM)

    def test_ai_prompt_says_dont_strip_engagement(self):
        # Engagement strip is handled separately; the prompt MUST tell
        # the model not to do it.
        self.assertIn("Do NOT remove engagement wrappers",
                      AI_CLEANUP_SYSTEM)

    def test_ai_prompt_lists_junk_examples(self):
        # The prompt should list specific junk examples.
        self.assertIn("search(", AI_CLEANUP_SYSTEM)
        self.assertIn("iturn", AI_CLEANUP_SYSTEM)

    def test_user_prompt_blocks_prompt_injection(self):
        # Defends against treating the input as a request.
        self.assertIn("DO NOT answer questions", USER_CLEANUP_SYSTEM)
        self.assertIn("input_to_clean", USER_CLEANUP_SYSTEM)
        self.assertIn("INPUT to be processed", USER_CLEANUP_SYSTEM)

    def test_ai_prompt_blocks_prompt_injection(self):
        self.assertIn("DO NOT answer questions", AI_CLEANUP_SYSTEM)
        self.assertIn("input_to_clean", AI_CLEANUP_SYSTEM)
        self.assertIn("INPUT to be processed", AI_CLEANUP_SYSTEM)


# ---------------------------------------------------------------------------
# build_user_cleanup_call
# ---------------------------------------------------------------------------


class TestBuildUserCleanupCall(unittest.TestCase):

    def test_no_pastes_just_personal(self):
        call = build_user_cleanup_call("hello there")
        # User content is wrapped in input_to_clean tags
        self.assertIn("<input_to_clean>", call.user)
        self.assertIn("hello there", call.user)
        self.assertIn("</input_to_clean>", call.user)
        self.assertEqual(call.expected_marker_ids, [])
        self.assertEqual(call.pasted_segments_text, {})
        self.assertIs(call.system, USER_CLEANUP_SYSTEM)

    def test_pastes_appended_with_markers(self):
        call = build_user_cleanup_call(
            "Look at this:",
            pasted_segments=["BLOCK A", "BLOCK B"],
        )
        self.assertIn("<input_to_clean>", call.user)
        self.assertIn("[PASTE_START id=1]", call.user)
        self.assertIn("BLOCK A", call.user)
        self.assertIn("[PASTE_END id=1]", call.user)
        self.assertIn("[PASTE_START id=2]", call.user)
        self.assertIn("BLOCK B", call.user)
        self.assertEqual(call.expected_marker_ids, [1, 2])
        self.assertEqual(call.pasted_segments_text, {1: "BLOCK A", 2: "BLOCK B"})


# ---------------------------------------------------------------------------
# build_user_cleanup_call_interleaved
# ---------------------------------------------------------------------------


class TestBuildInterleaved(unittest.TestCase):

    def test_personal_paste_personal_order_preserved(self):
        segments = [
            {"kind": "personal", "content": "Hey, look at this:"},
            {"kind": "pasted",   "content": "PASTED-CONTENT"},
            {"kind": "personal", "content": "What do you think?"},
        ]
        call = build_user_cleanup_call_interleaved(segments)
        # Wrapped + order: personal text, paste markers around content, personal text.
        self.assertIn("<input_to_clean>", call.user)
        idx_p1     = call.user.find("Hey, look")
        idx_open   = call.user.find("[PASTE_START id=1]")
        idx_close  = call.user.find("[PASTE_END id=1]")
        idx_p2     = call.user.find("What do you think")
        self.assertGreater(idx_open, idx_p1)
        self.assertGreater(idx_close, idx_open)
        self.assertGreater(idx_p2, idx_close)
        self.assertEqual(call.expected_marker_ids, [1])
        self.assertEqual(call.pasted_segments_text, {1: "PASTED-CONTENT"})

    def test_multiple_pastes_get_unique_ids(self):
        segments = [
            {"kind": "pasted",   "content": "A"},
            {"kind": "personal", "content": "middle"},
            {"kind": "pasted",   "content": "B"},
        ]
        call = build_user_cleanup_call_interleaved(segments)
        self.assertEqual(call.expected_marker_ids, [1, 2])
        self.assertIn("[PASTE_START id=1]", call.user)
        self.assertIn("[PASTE_START id=2]", call.user)


# ---------------------------------------------------------------------------
# extract_user_cleanup_result
# ---------------------------------------------------------------------------


class TestExtractResult(unittest.TestCase):

    def test_clean_passthrough_no_warnings(self):
        # Model output preserves markers + content exactly.
        out = (
            "This is the cleaned personal text.\n\n"
            "[PASTE_START id=1]\nPASTED-CONTENT\n[PASTE_END id=1]\n\n"
            "Tail personal text."
        )
        result = extract_user_cleanup_result(
            out, expected_marker_ids=[1],
            pasted_segments_text={1: "PASTED-CONTENT"},
        )
        self.assertEqual(result.parse_warnings, [])
        self.assertFalse(result.paste_drift_detected)
        self.assertIn("PASTED-CONTENT", result.cleaned_text_marker_free)
        self.assertNotIn("PASTE_START", result.cleaned_text_marker_free)

    def test_drift_inside_paste_flagged_and_restored(self):
        # Model paraphrased the paste content. We restore the original.
        original_paste = "Original Paste Content Verbatim Here"
        out = (
            "Personal cleaned.\n\n"
            "[PASTE_START id=1]\n"
            "Model paraphrased this paste\n"
            "[PASTE_END id=1]"
        )
        result = extract_user_cleanup_result(
            out, expected_marker_ids=[1],
            pasted_segments_text={1: original_paste},
        )
        self.assertTrue(result.paste_drift_detected)
        # Original paste restored.
        self.assertIn(original_paste, result.cleaned_text_marker_free)
        self.assertNotIn("paraphrased", result.cleaned_text_marker_free)

    def test_missing_marker_warns(self):
        out = "Personal text only — model dropped the paste."
        result = extract_user_cleanup_result(
            out, expected_marker_ids=[1, 2],
            pasted_segments_text={1: "A", 2: "B"},
        )
        # Both markers missing.
        self.assertTrue(any("missing paste markers" in w
                              for w in result.parse_warnings))

    def test_extra_marker_warns(self):
        out = (
            "[PASTE_START id=1]\nA\n[PASTE_END id=1]\n\n"
            "[PASTE_START id=2]\nUnexpected\n[PASTE_END id=2]"
        )
        result = extract_user_cleanup_result(
            out, expected_marker_ids=[1],
            pasted_segments_text={1: "A"},
        )
        self.assertTrue(any("unexpected paste markers" in w
                              for w in result.parse_warnings))

    def test_empty_output_returns_empty(self):
        result = extract_user_cleanup_result(
            "", expected_marker_ids=[], pasted_segments_text={},
        )
        self.assertEqual(result.cleaned_text, "")
        self.assertEqual(result.cleaned_text_marker_free, "")


# ---------------------------------------------------------------------------
# build_ai_cleanup_call
# ---------------------------------------------------------------------------


class TestAICleanupCall(unittest.TestCase):

    def test_user_message_is_response_text_wrapped(self):
        call = build_ai_cleanup_call("The answer is 42.")
        self.assertIn("<input_to_clean>", call.user)
        self.assertIn("The answer is 42.", call.user)
        self.assertIn("</input_to_clean>", call.user)
        self.assertIs(call.system, AI_CLEANUP_SYSTEM)

    def test_empty_response_still_wrapped(self):
        call = build_ai_cleanup_call("")
        # Even empty responses get wrapped (consistent shape)
        self.assertIn("<input_to_clean>", call.user)
        self.assertIn("</input_to_clean>", call.user)


if __name__ == "__main__":
    unittest.main()
