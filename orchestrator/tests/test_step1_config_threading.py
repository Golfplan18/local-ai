#!/usr/bin/env python3
"""Per-request config_name threading into step-1/step-2 model resolution.

Regression guard for the 2026-06-12 campaign fidelity fix: before it,
``run_step1_cleanup`` (Phase A cleanup) resolved its utility endpoint
without the per-request ``config_name``, so a `/chat` request that named
a configuration still ran its step-1 calls on the ACTIVE configuration's
models — caught live by the campaign runner's fidelity gate (gpt-5.4-nano
executing inside a campaign-premium run).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "orchestrator"))

import boot  # noqa: E402
import conversation_memory  # noqa: E402
import pipeline_trace  # noqa: E402


class TestStep1ConfigThreading(unittest.TestCase):
    def test_pre_phase_a_retrieval_dispatch_remains_gear2(self):
        result = boot.run_step1_cleanup(
            "Who is the current president of France?", "", {})
        self.assertEqual(result["mode"], "factual-lookup")
        self.assertEqual(result["classification_intent"], "LOOKUP")
        self.assertFalse(result["pre_routing"]["bypass_to_direct_response"])
        self.assertTrue(result["pre_routing"]["gear2_rag_dispatch"])
        self.assertEqual(
            boot.extract_default_gear(boot.load_mode(result["mode"])), 2)

    def test_pre_phase_a_greeting_dispatch_remains_gear1(self):
        result = boot.run_step1_cleanup("Hello", "", {})
        self.assertEqual(result["mode"], "simple")
        self.assertTrue(result["pre_routing"]["bypass_to_direct_response"])
        self.assertEqual(
            boot.extract_default_gear(boot.load_mode(result["mode"])), 1)

    def test_run_step1_cleanup_passes_config_name(self):
        calls = []

        def fake_get_slot_endpoint(config, slot, context="interactive",
                                   config_name=None):
            calls.append({"slot": slot, "config_name": config_name})
            return None  # passthrough path — no model call attempted

        prompt = "Run a full cui bono analysis on this policy proposal."
        with mock.patch.object(boot, "get_slot_endpoint",
                               side_effect=fake_get_slot_endpoint), \
             mock.patch.object(boot, "pre_phase_a_bypass_check",
                               return_value=None):
            boot.run_step1_cleanup(prompt, "", {},
                                   config_name="campaign-premium")
        step1_calls = [c for c in calls if c["slot"] == "step1_cleanup"]
        self.assertTrue(step1_calls, "step1_cleanup endpoint never resolved")
        self.assertEqual(step1_calls[0]["config_name"], "campaign-premium")

    def test_phase_a_provider_error_never_becomes_cleaned_prompt(self):
        prompt = "I've been wondering why landscapes feel restorative."
        with mock.patch.object(
                boot, "get_slot_endpoint",
                return_value={"id": "qwen/qwen3.5-9b", "name": "qwen-9b"}), \
             mock.patch.object(boot, "call_model", return_value=(
                 "[Error calling OpenRouter API: Error code: 401 - "
                 "{'error': {'message': 'User not found.'}}]")), \
             mock.patch.object(boot, "pre_phase_a_bypass_check",
                               return_value=None):
            result = boot.run_step1_cleanup(
                prompt, "", {}, config_name="campaign-optimum-plus")
        self.assertEqual(result["cleaned_prompt"], prompt)
        self.assertEqual(result["operational_notation"], prompt)
        self.assertTrue(result["phase_a_transport_failed"])

    def test_phase_a_receives_full_recent_history_without_fixed_count_or_char_caps(self):
        captured = []
        history = []
        for index in range(5):
            history.extend([
                {
                    "role": "user",
                    "content": f"history-user-{index}:" + (str(index) * 700),
                },
                {
                    "role": "assistant",
                    "content": f"history-assistant-{index}:" + (str(index) * 700),
                },
            ])

        def phase_a(messages, _endpoint, images=None):
            captured.append(messages)
            return (
                "### CLEANED PROMPT (Natural Language)\n"
                "Analyse this policy.\n"
                "### CLEANED PROMPT (Operational Notation)\n"
                "analyse_policy()\n"
                "### CORRECTIONS LOG\nNone\n"
                "### INFERRED ITEMS\nNone"
            )

        endpoint = {
            "id": "phase-a-test", "type": "api",
            "context_window": 100_000, "max_tokens": 1_000,
        }
        with mock.patch.object(
                boot, "get_slot_endpoint", return_value=endpoint), \
             mock.patch.object(boot, "call_model", side_effect=phase_a), \
             mock.patch.object(boot, "pre_phase_a_bypass_check",
                               return_value=None):
            boot.run_step1_cleanup(
                "Analyse this policy.", "browser context must be ignored", {},
                conversation_history=history,
            )

        phase_a_user = captured[0][-1]["content"]
        self.assertIn("history-user-0:" + ("0" * 700), phase_a_user)
        self.assertIn("history-assistant-4:" + ("4" * 700), phase_a_user)
        self.assertNotIn("browser context must be ignored", phase_a_user)

    def test_history_packer_respects_safe_capacity_and_whole_turn_priority(self):
        required = [
            {"role": "system", "content": "required-system"},
            {"role": "user", "content": "required-current-input"},
        ]

        def pair(prefix, segment, depth):
            return [
                {
                    "role": "user", "content": prefix + "-u-" + ("x" * 200),
                    "_ora_history_segment": segment,
                    "_ora_ancestry_depth": depth,
                },
                {
                    "role": "assistant", "content": prefix + "-a-" + ("y" * 200),
                    "_ora_history_segment": segment,
                    "_ora_ancestry_depth": depth,
                },
            ]

        history = (
            pair("ancestor-old", "ancestry", 2)
            + pair("ancestor-near", "ancestry", 1)
            + pair("local-old", "local", 0)
            + pair("local-new", "local", 0)
        )
        unit_tokens = boot.estimate_message_tokens(history[-2:])
        required_tokens = boot.estimate_message_tokens(required)
        endpoint = {
            "context_window": 100 + 128 + required_tokens + (2 * unit_tokens),
            "max_tokens": 100,
        }

        packed, stats = boot.pack_conversation_history(
            history, endpoint, required,
        )

        self.assertEqual(
            [message["content"].rsplit("-", 2)[0] for message in packed],
            ["ancestor-near", "ancestor-near", "local-new", "local-new"],
        )
        self.assertEqual(
            [message["role"] for message in packed],
            ["user", "assistant", "user", "assistant"],
        )
        self.assertEqual(stats["history_selected_units"], 2)
        self.assertLessEqual(
            stats["estimated_call_input_tokens"],
            stats["safe_input_capacity"],
        )
        self.assertLessEqual(stats["history_allowance"], 200_000)

    def test_combined_context_is_lossless_when_every_complete_unit_fits(self):
        history = [
            {"role": "user", "content": "local user"},
            {"role": "assistant", "content": "local assistant"},
        ]
        optional = [
            {
                "lane": "contributor", "unit_id": "contributor:one",
                "source_id": "selected-source-0", "explicit_index": 0,
                "content": "EXACT CONTRIBUTOR ONE",
            },
            {
                "lane": "contributor", "unit_id": "contributor:two",
                "source_id": "selected-source-1", "explicit_index": 1,
                "content": "EXACT CONTRIBUTOR TWO",
            },
            {
                "lane": "global", "unit_id": "global:one",
                "source_id": "global-source", "content": "EXACT GLOBAL ONE",
            },
        ]
        token = boot.set_optional_context_context(optional, {
            "sources": [
                {"source_id": "selected-source-0", "explicit_index": 0,
                 "status": "available"},
                {"source_id": "selected-source-1", "explicit_index": 1,
                 "status": "available"},
            ],
        })
        try:
            prepared, stats = boot.prepare_messages_with_continuity(
                [{"role": "system", "content": "system"},
                 {"role": "user", "content": "current"}],
                {"type": "api", "context_window": 100_000, "max_tokens": 1_000},
                history=history,
            )
        finally:
            boot.reset_optional_context_context(token)
        joined = "\n".join(message["content"] for message in prepared)
        for exact in (
            "local user", "local assistant", "EXACT CONTRIBUTOR ONE",
            "EXACT CONTRIBUTOR TWO", "EXACT GLOBAL ONE",
        ):
            self.assertIn(exact, joined)
        coverage = stats["context_coverage"]
        self.assertTrue(coverage["lossless_when_fit"])
        self.assertEqual(coverage["deferred_unit_count"], 0)

    def test_overflow_preserves_whole_units_and_fair_selected_sources(self):
        optional = [
            {
                "lane": "contributor", "unit_id": "s0-first",
                "source_id": "selected-source-0", "explicit_index": 0,
                "order": 0, "content": "S0_FIRST " + ("a" * 350),
            },
            {
                "lane": "contributor", "unit_id": "s0-second",
                "source_id": "selected-source-0", "explicit_index": 0,
                "order": 1, "content": "S0_SECOND " + ("b" * 350),
            },
            {
                "lane": "contributor", "unit_id": "s1-first",
                "source_id": "selected-source-1", "explicit_index": 1,
                "order": 2, "content": "S1_FIRST " + ("c" * 350),
            },
            {
                "lane": "contributor", "unit_id": "s2-first",
                "source_id": "selected-source-2", "explicit_index": 2,
                "order": 3, "content": "S2_FIRST " + ("d" * 350),
            },
        ]
        inventory = {"sources": [
            {"source_id": f"selected-source-{index}",
             "explicit_index": index, "status": "available"}
            for index in range(3)
        ] + [
            {"source_id": "selected-source-3", "explicit_index": 3,
             "status": "missing"},
            {"source_id": "selected-source-4", "explicit_index": 4,
             "status": "withheld"},
        ]}
        required = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "current"},
        ]
        selected = None
        for window in range(1_700, 5_000, 100):
            _history, reference, stats = boot._pack_physical_call_context(
                [], {"context_window": window, "max_tokens": 100}, required,
                optional_units=optional, source_inventory=inventory,
            )
            ids = stats["context_coverage"]["selected_unit_ids"]
            if len(ids) == 3:
                selected = (reference, stats)
                break
        self.assertIsNotNone(selected, "test fixture found no three-unit capacity")
        reference, stats = selected
        coverage = stats["context_coverage"]
        self.assertEqual(
            set(coverage["selected_unit_ids"]),
            {"s0-first", "s1-first", "s2-first"},
        )
        self.assertNotIn("S0_SECOND", reference["content"])
        self.assertNotIn("b" * 40, reference["content"])
        self.assertEqual(coverage["source_counts"]["represented"], 3)
        self.assertEqual(coverage["source_counts"]["missing"], 1)
        self.assertEqual(coverage["source_counts"]["withheld"], 1)
        self.assertEqual(coverage["deferred_unit_count"], 1)
        self.assertLessEqual(
            stats["estimated_call_input_tokens"], stats["safe_input_capacity"],
        )

    def test_1300_window_keeps_recent_and_near_fork_ahead_of_contributor(self):
        history = [
            {
                "role": "assistant", "content": "NEAR " + ("x" * 320),
                "_ora_history_segment": "ancestry",
                "_ora_history_owner": "parent",
                "_ora_history_turn_index": 1,
                "_ora_ancestry_depth": 1,
            },
            {
                "role": "assistant", "content": "RECENT " + ("x" * 100),
                "_ora_history_segment": "local",
                "_ora_history_owner": "current",
                "_ora_history_turn_index": 2,
                "_ora_ancestry_depth": 0,
            },
        ]
        for contributor_chars, contributor_fits in ((20, True), (150, False)):
            with self.subTest(contributor_chars=contributor_chars):
                contributor = [{
                    "lane": "contributor", "unit_id": "contributor-small",
                    "source_id": "selected-source-0", "explicit_index": 0,
                    "content": "CONTRIB " + ("c" * contributor_chars),
                }]
                packed, _reference, stats = boot._pack_physical_call_context(
                    history,
                    {"context_window": 1_300, "max_tokens": 100},
                    [{"role": "system", "content": "system"},
                     {"role": "user", "content": "current"}],
                    optional_units=contributor,
                    additional_required_tokens=100,
                )
                joined = "\n".join(message["content"] for message in packed)
                self.assertIn("NEAR ", joined)
                self.assertIn("RECENT ", joined)
                selected = stats["context_coverage"]["selected_unit_ids"]
                self.assertIn("conversation:parent:turn:1", selected)
                self.assertIn("conversation:current:turn:2", selected)
                self.assertEqual(
                    "contributor-small" in selected, contributor_fits,
                )
                self.assertLessEqual(
                    stats["estimated_call_input_tokens"],
                    stats["safe_input_capacity"],
                )

    def test_optional_ceiling_and_endpoint_capacity_are_enforced(self):
        huge = {
            "lane": "contributor", "unit_id": "huge",
            "source_id": "selected-source-0", "explicit_index": 0,
            "content": "z" * 210_000,
        }
        required = [{"role": "user", "content": "current"}]
        _history, _reference, stats = boot._pack_physical_call_context(
            [], {"context_window": 500_000, "max_tokens": 1_000}, required,
            optional_units=[huge],
        )
        self.assertEqual(stats["history_allowance"], 200_000)
        self.assertEqual(
            stats["context_coverage"]["lanes"]["contributor"]["selected_units"],
            0,
        )
        self.assertLessEqual(
            stats["estimated_call_input_tokens"], stats["safe_input_capacity"],
        )
        with self.assertRaisesRegex(ValueError, "endpoint-safe"):
            boot.prepare_messages_with_continuity(
                [{"role": "user", "content": "r" * 4_000}],
                {"type": "api", "context_window": 1_000, "max_tokens": 100},
                history=[],
            )

    def test_global_units_exclude_lineage_and_explicit_sources_then_deduplicate(self):
        atomic_path = str((REPO_ROOT / "atomic-source.md").resolve())
        contributor = {
            "lane": "contributor", "unit_id": "contributor-unit",
            "provenance_id": "conversation:contributor:turn:1",
            "source_id": "selected-source-0", "explicit_index": 0,
            "content": "EXACT EXPLICIT CONTENT",
        }
        context = {
            "cleaned_prompt": "allowed evidence",
            "contributor_bundle": {
                "units": [contributor],
                "sources": [{
                    "source_id": "selected-source-0", "explicit_index": 0,
                    "status": "available",
                }],
                "exclude_conversation_ids": [
                    "contributor", "contributor-parent",
                ],
                "exclude_paths": [atomic_path],
            },
            "conversation_context_chunks": [
                {"id": "current", "document": "current leak",
                 "metadata": {"conversation_id": "current", "turn_index": 9, "tag": ""}},
                {"id": "ancestor", "document": "ancestor leak",
                 "metadata": {"conversation_id": "current-parent", "turn_index": 9, "tag": ""}},
                {"id": "contributor", "document": "post-fork contributor leak",
                 "metadata": {"conversation_id": "contributor", "turn_index": 9, "tag": ""}},
                {"id": "contributor-parent", "document": "contributor ancestor leak",
                 "metadata": {"conversation_id": "contributor-parent", "turn_index": 9, "tag": ""}},
                {"id": "atomic", "document": "atomic duplicate leak",
                 "metadata": {"conversation_id": "other", "path": atomic_path,
                              "turn_index": 1, "tag": ""}},
                {"id": "private", "document": "private global leak",
                 "metadata": {"conversation_id": "private-source", "turn_index": 1,
                              "tag": "private"}},
                {"id": "duplicate", "document": "EXACT EXPLICIT CONTENT",
                 "metadata": {"conversation_id": "allowed-duplicate", "turn_index": 1,
                              "tag": ""}},
                {"id": "allowed", "document": "ALLOWED GLOBAL CONTENT",
                 "metadata": {"conversation_id": "allowed", "turn_index": 2,
                              "tag": ""}},
            ],
        }

        def resolve(_conversation_id, *, lineage_sink=None, **_kwargs):
            lineage_sink.update({"current", "current-parent"})
            return []

        tag_token = boot.set_conversation_tag_context("")
        try:
            with mock.patch.object(
                conversation_memory, "resolve_effective_conversation_history",
                side_effect=resolve,
            ):
                boot._finalize_optional_context_package(
                    context, conversation_id="current", history=[],
                )
        finally:
            boot.reset_conversation_tag_context(tag_token)
        documents = [
            unit["content"] for unit in context["optional_context_units"]
        ]
        self.assertIn("EXACT EXPLICIT CONTENT", documents)
        self.assertIn("ALLOWED GLOBAL CONTENT", documents)
        for leaked in (
            "current leak", "ancestor leak", "post-fork contributor leak",
            "contributor ancestor leak", "atomic duplicate leak",
            "private global leak",
        ):
            self.assertNotIn(leaked, documents)
        self.assertEqual(context["conversation_context_chunks"], [])
        self.assertEqual(context["conversation_rag"], "")

        _history, reference, stats = boot._pack_physical_call_context(
            [], {"context_window": 100_000, "max_tokens": 1_000},
            [{"role": "user", "content": "current"}],
            optional_units=context["optional_context_units"],
            source_inventory=context["context_source_inventory"],
        )
        self.assertEqual(reference["content"].count("EXACT EXPLICIT CONTENT"), 1)
        self.assertIn("ALLOWED GLOBAL CONTENT", reference["content"])
        self.assertEqual(
            stats["context_coverage"]["deduplicated_unit_count"], 1,
        )

    def test_local_contributor_and_global_exact_duplicates_share_one_unit(self):
        duplicate = "ONE AUTHORITATIVE COMPLETE UNIT"
        optional = [
            {
                "lane": "contributor", "unit_id": "contributor-copy",
                "source_id": "selected-source-0", "explicit_index": 0,
                "content": duplicate,
            },
            {
                "lane": "global", "unit_id": "global-copy",
                "source_id": "global:other", "content": duplicate,
            },
        ]
        packed, reference, stats = boot._pack_physical_call_context(
            [{"role": "assistant", "content": duplicate}],
            {"context_window": 100_000, "max_tokens": 1_000},
            [{"role": "user", "content": "current"}],
            optional_units=optional,
            source_inventory={"sources": [{
                "source_id": "selected-source-0", "explicit_index": 0,
                "status": "available",
            }]},
        )
        self.assertEqual([message["content"] for message in packed], [duplicate])
        self.assertIsNone(reference)
        coverage = stats["context_coverage"]
        self.assertEqual(coverage["deduplicated_unit_count"], 2)
        self.assertEqual(coverage["lanes"]["history"]["selected_units"], 1)
        self.assertEqual(coverage["lanes"]["contributor"]["available_units"], 0)
        self.assertEqual(coverage["lanes"]["global"]["available_units"], 0)

    @staticmethod
    def _supplement_fixture():
        units = [
            {
                "lane": "contributor", "unit_id": f"unit-{index}",
                "source_id": f"selected-source-{index}",
                "explicit_index": index, "order": index,
                "content": f"{term.upper()} COMPLETE UNIT " + (term * 160),
            }
            for index, term in enumerate(("alpha", "beta", "gamma", "delta"))
        ]
        inventory = {"sources": [
            {"source_id": f"selected-source-{index}",
             "explicit_index": index, "status": "available"}
            for index in range(len(units))
        ]}
        required = [{"role": "user", "content": "current analysis request"}]
        endpoint = None
        for window in range(2_000, 8_000, 100):
            _history, _reference, stats = boot._pack_physical_call_context(
                [], {"type": "api", "context_window": window, "max_tokens": 100},
                required, optional_units=units, source_inventory=inventory,
            )
            lane = stats["context_coverage"]["lanes"]["contributor"]
            if lane["selected_units"] == 1:
                endpoint = {"type": "api", "context_window": window, "max_tokens": 100}
                break
        if endpoint is None:
            raise AssertionError("supplement fixture found no one-unit capacity")
        return units, inventory, required, endpoint

    def test_supplement_can_progress_beyond_two_without_exceeding_capacity(self):
        units, inventory, required, endpoint = self._supplement_fixture()
        requests = [
            "## SUPPLEMENTAL RAG REQUEST\n"
            f"gap_statement: Need {term} evidence\n"
            f"query_terms: {term}\n"
            "why_it_matters: It resolves the current claim"
            for term in ("beta", "gamma", "delta")
        ]
        responses = requests + ["Final analysis with all reachable evidence."]
        calls = []

        def physical(messages, _endpoint, _step_name, **_kwargs):
            prepared, stats = boot.prepare_messages_with_continuity(
                messages, endpoint, history=[],
            )
            calls.append((prepared, stats))
            return responses[len(calls) - 1], True, "ok"

        token = boot.set_optional_context_context(units, inventory)
        try:
            with mock.patch.object(boot, "_call_with_retry", side_effect=physical):
                text, ok, _reason = boot._call_with_supplement(
                    required, endpoint, "analyst", context_pkg={},
                )
        finally:
            boot.reset_optional_context_context(token)
        self.assertTrue(ok)
        self.assertEqual(text, responses[-1])
        self.assertEqual(len(calls), 4)
        for call_index, marker in enumerate(("BETA", "GAMMA", "DELTA"), 1):
            joined = "\n".join(
                message["content"] for message in calls[call_index][0]
            )
            self.assertIn(f"{marker} COMPLETE UNIT", joined)
        for _prepared, stats in calls:
            self.assertLessEqual(
                stats["estimated_call_input_tokens"],
                stats["safe_input_capacity"],
            )

    def test_supplement_stops_on_repeated_gap_without_an_append_call(self):
        units, inventory, required, endpoint = self._supplement_fixture()
        request = (
            "## SUPPLEMENTAL RAG REQUEST\n"
            "gap_statement: Need beta evidence\n"
            "query_terms: beta\n"
            "why_it_matters: It resolves the current claim"
        )
        calls = []

        def physical(messages, _endpoint, _step_name, **_kwargs):
            prepared, stats = boot.prepare_messages_with_continuity(
                messages, endpoint, history=[],
            )
            calls.append((prepared, stats))
            return request, True, "ok"

        token = boot.set_optional_context_context(units, inventory)
        try:
            with mock.patch.object(boot, "_call_with_retry", side_effect=physical):
                text, ok, _reason = boot._call_with_supplement(
                    required, endpoint, "analyst", context_pkg={},
                )
        finally:
            boot.reset_optional_context_context(token)
        self.assertTrue(ok)
        self.assertEqual(len(calls), 2)
        self.assertIn("## COVERAGE GAP", text)
        self.assertNotIn("## SUPPLEMENTAL RAG REQUEST", text)

    def test_request_only_verifier_and_reviser_promote_before_health_verdict(self):
        units, inventory, required, endpoint = self._supplement_fixture()
        request = (
            "## SUPPLEMENTAL RAG REQUEST\n"
            "gap_statement: Need beta evidence\n"
            "query_terms: beta\n"
            "why_it_matters: It resolves the current claim"
        )
        terminal = {
            "verifier": (
                "The promoted evidence resolves the factual gap.\n\n"
                "VERDICT: PASS"
            ),
            "reviser": (
                "## REVISED DRAFT\n\n"
                "The promoted beta evidence is now incorporated into this "
                "complete corrected draft with enough substantive detail. "
                "The revision explains how the evidence changes the claim, "
                "preserves the supported analysis, and identifies the exact "
                "conclusion that now follows from the retrieved source."
            ),
        }
        for step_name in ("verifier", "reviser"):
            with self.subTest(step_name=step_name):
                calls = []
                responses = [request, terminal[step_name]]

                def physical(messages, _endpoint, images=None):
                    prepared, stats = boot.prepare_messages_with_continuity(
                        messages, endpoint, history=[],
                    )
                    calls.append((prepared, stats))
                    return responses[len(calls) - 1]

                token = boot.set_optional_context_context(units, inventory)
                try:
                    with mock.patch.object(
                        boot, "_run_model_with_tools", side_effect=physical,
                    ):
                        text, ok, _reason = boot._call_with_supplement(
                            required, endpoint, step_name, context_pkg={},
                        )
                finally:
                    boot.reset_optional_context_context(token)
                self.assertTrue(ok)
                self.assertEqual(text, terminal[step_name])
                self.assertEqual(len(calls), 2)
                first = "\n".join(m["content"] for m in calls[0][0])
                second = "\n".join(m["content"] for m in calls[1][0])
                self.assertNotIn("BETA COMPLETE UNIT", first)
                self.assertIn("BETA COMPLETE UNIT", second)
                for _prepared, stats in calls:
                    self.assertLessEqual(
                        stats["estimated_call_input_tokens"],
                        stats["safe_input_capacity"],
                    )

    def test_request_only_repeated_gap_stops_and_remains_unhealthy(self):
        units, inventory, required, endpoint = self._supplement_fixture()
        request = (
            "## SUPPLEMENTAL RAG REQUEST\n"
            "gap_statement: Need beta evidence\n"
            "query_terms: beta\n"
            "why_it_matters: It resolves the current claim"
        )
        calls = []

        def physical(messages, _endpoint, images=None):
            prepared, stats = boot.prepare_messages_with_continuity(
                messages, endpoint, history=[],
            )
            calls.append((prepared, stats))
            return request

        token = boot.set_optional_context_context(units, inventory)
        try:
            with mock.patch.object(
                boot, "_run_model_with_tools", side_effect=physical,
            ):
                text, ok, _reason = boot._call_with_supplement(
                    required, endpoint, "verifier", context_pkg={},
                )
        finally:
            boot.reset_optional_context_context(token)
        self.assertFalse(ok)
        self.assertEqual(len(calls), 2)
        self.assertIn("## COVERAGE GAP", text)
        self.assertNotIn("## SUPPLEMENTAL RAG REQUEST", text)

    def test_public_and_persisted_coverage_never_exposes_private_unit_identity(self):
        secret = "/Users/private/SECRET_TITLE.md"
        units = [{
            "lane": "contributor", "unit_id": secret,
            "provenance_id": secret, "source_id": secret,
            "source_path": secret, "content": "private content",
        }]
        optional_token = boot.set_optional_context_context(units)
        call_meta = {"step": "analyst", "slot": "depth", "gear": 3}
        meta_token = boot._CALL_METADATA_CV.set(call_meta)
        try:
            boot.prepare_messages_with_continuity(
                [{"role": "user", "content": "current"}],
                {"type": "api", "context_window": 10_000, "max_tokens": 100},
                history=[],
            )
            private = boot._LAST_CONTEXT_COVERAGE_CV.get()
            public = boot.get_context_coverage()
        finally:
            boot._CALL_METADATA_CV.reset(meta_token)
            boot.reset_optional_context_context(optional_token)
        self.assertIn(secret, private["selected_unit_ids"])
        for value in (public, call_meta["context_coverage"]):
            encoded = json.dumps(value)
            self.assertNotIn(secret, encoded)
            for key in (
                "selected_unit_ids", "deferred_unit_ids", "source_coverage",
            ):
                self.assertNotIn(key, value)

        with tempfile.TemporaryDirectory() as trace_dir:
            pipeline_trace.record_model_call_config(
                trace_dir, {"id": "test"},
                {"context_coverage": private},
            )
            pipeline_trace.record_supplemental_request(
                trace_dir, "analyst", "gap", "terms", "why", None, True,
                selected_unit_ids=[secret], deferred_unit_count=0,
            )
            persisted = "\n".join(
                path.read_text(encoding="utf-8")
                for path in Path(trace_dir).glob("*.jsonl")
            )
        self.assertNotIn(secret, persisted)
        self.assertNotIn("selected_unit_ids", persisted)

    def test_nested_gear3_scope_merges_with_existing_gear4_coverage(self):
        context_pkg = {
            "optional_context_units": [{
                "lane": "global", "unit_id": "unit-one",
                "source_id": "global-one", "content": "reference",
            }],
            "context_source_inventory": {},
        }
        outer_token = boot._set_context_units_from_package(context_pkg)
        try:
            boot.prepare_messages_with_continuity(
                [{"role": "user", "content": "outer"}],
                {"type": "api", "context_window": 10_000, "max_tokens": 100},
                history=[],
            )

            def nested(*_args, **_kwargs):
                boot.prepare_messages_with_continuity(
                    [{"role": "user", "content": "nested"}],
                    {"type": "api", "context_window": 10_000,
                     "max_tokens": 100},
                    history=[],
                )
                return "fallback"

            with mock.patch.object(boot, "_run_gear3_impl", side_effect=nested):
                self.assertEqual(boot.run_gear3(context_pkg, {}, history=[]), "fallback")
            self.assertEqual(boot.get_context_coverage()["physical_calls"], 2)
            self.assertEqual(context_pkg["context_coverage"]["physical_calls"], 2)
        finally:
            boot.reset_optional_context_context(outer_token)

    def test_step2_threads_standard_private_and_stealth_to_primary_knowledge(self):
        calls = []

        class FakeEngine:
            def __init__(self, _config):
                self.hardware = {"tier": 0}

            @staticmethod
            def get_relationship_context(_initial, _mode):
                return ""

            @staticmethod
            def assemble_context(**_kwargs):
                return {"signals": [], "utilization": ""}

        def concept(**kwargs):
            calls.append(kwargs)
            return ""

        step1 = {
            "mode": "test", "raw_prompt": "privacy matrix query",
            "cleaned_prompt": "privacy matrix query", "triage_tier": 1,
        }
        with mock.patch.object(
            boot, "load_mode", return_value="## DEFAULT GEAR\n\nGear 2",
        ), mock.patch.object(boot, "RAG_ENGINE_AVAILABLE", True), \
             mock.patch.object(boot, "WEB_CONSULTATION_AVAILABLE", False), \
             mock.patch.object(boot, "retrieve_ranked_chunks", return_value=[]), \
             mock.patch.object(boot, "assemble_ranked_context", side_effect=concept), \
             mock.patch.object(boot, "RAGEngine", FakeEngine), \
             mock.patch.object(boot, "_load_profile_config", return_value=None):
            for raw_tag, expected in (
                ("", ""), ("private", "private"),
                ("stealth", "stealth"), ("invalid", ""),
            ):
                boot.run_step2_context_assembly(
                    step1, {}, conversation_tag=raw_tag,
                )
                self.assertEqual(calls[-1]["privacy_tag"], expected)
                self.assertEqual(
                    calls[-1]["include_private"],
                    expected in {"private", "stealth"},
                )

    def test_step2_legacy_stealth_uses_prefix_and_explicit_privacy(self):
        concept_calls = []
        conversation_calls = []
        step1 = {
            "mode": "test", "raw_prompt": "legacy privacy query",
            "cleaned_prompt": "legacy privacy query", "triage_tier": 1,
        }

        def conversation(*args, **kwargs):
            conversation_calls.append((args, kwargs))
            return []

        def concept(*args, **kwargs):
            concept_calls.append((args, kwargs))
            return ""

        with mock.patch.object(
            boot, "load_mode", return_value="## DEFAULT GEAR\n\nGear 2",
        ), mock.patch.object(boot, "RAG_ENGINE_AVAILABLE", False), \
             mock.patch.object(boot, "TOOLS_AVAILABLE", True), \
             mock.patch.object(boot, "WEB_CONSULTATION_AVAILABLE", False), \
             mock.patch.object(boot, "knowledge_search_raw", side_effect=conversation), \
             mock.patch.object(boot, "knowledge_search", side_effect=concept), \
             mock.patch.object(boot, "_load_profile_config", return_value=None):
            boot.run_step2_context_assembly(
                step1, {}, conversation_tag="stealth",
            )
        self.assertTrue(conversation_calls[0][0][0].startswith("include:private "))
        self.assertEqual(conversation_calls[0][1]["privacy_tag"], "stealth")
        self.assertTrue(concept_calls[0][0][0].startswith("include:private "))
        self.assertEqual(concept_calls[0][1]["privacy_tag"], "stealth")

    def test_structured_conversation_units_feed_utilization_and_fconsult_once(self):
        engine_calls = {"relationship_inputs": None, "assembly": None}
        consultation = {}
        physical_calls = []
        small = "STRUCTURED CONVERSATION COMPLETE UNIT"
        oversized = "OVERSIZED-UNIT " + ("z" * 210_000)
        chunks = [
            {"id": "small", "document": small, "score": 1.0,
             "metadata": {"conversation_id": "prior", "turn_index": 1,
                          "tag": ""}},
            {"id": "oversized", "document": oversized, "score": 0.5,
             "metadata": {"conversation_id": "older", "turn_index": 2,
                          "tag": ""}},
        ]
        endpoint = {
            "id": "fast", "name": "fast", "type": "api",
            "context_window": 3_000, "max_tokens": 100,
        }

        class FakeEngine:
            def __init__(self, _config):
                self.hardware = {"tier": 0}

            @staticmethod
            def get_relationship_context(initial, _mode):
                engine_calls["relationship_inputs"] = initial
                return ""

            @staticmethod
            def assemble_context(**kwargs):
                engine_calls["assembly"] = kwargs
                return {"signals": [], "utilization": "bounded"}

        def fake_call_model(messages, call_endpoint, images=None):
            prepared, stats = boot.prepare_messages_with_continuity(
                messages, call_endpoint, history=[],
            )
            physical_calls.append((prepared, stats))
            return "INTENTS:\n(none)"

        def fake_consultation(**kwargs):
            consultation["conversation_context"] = kwargs["conversation_context"]
            kwargs["call_model"](
                [{"role": "system", "content": "intent system"},
                 {"role": "user", "content": "intent user"}],
                kwargs["fast_endpoint"],
            )
            return {
                "web_rag": "", "chunks": [], "prompt_sanity_flags": [],
                "consultation_trace": {"status": "ran"},
            }

        step1 = {
            "mode": "test", "raw_prompt": "structured context query",
            "cleaned_prompt": "structured context query", "triage_tier": 1,
        }
        with mock.patch.object(
            boot, "load_mode", return_value="## DEFAULT GEAR\n\nGear 2",
        ), mock.patch.object(boot, "RAG_ENGINE_AVAILABLE", True), \
             mock.patch.object(boot, "WEB_CONSULTATION_AVAILABLE", True), \
             mock.patch.object(boot, "retrieve_ranked_chunks", return_value=chunks), \
             mock.patch.object(boot, "assemble_ranked_context", return_value=""), \
             mock.patch.object(boot, "RAGEngine", FakeEngine), \
             mock.patch.object(boot, "_load_profile_config", return_value=None), \
             mock.patch.object(boot, "_load_web_consultation_config",
                               return_value={"enabled": True}), \
             mock.patch.object(boot, "get_slot_endpoint", return_value=endpoint), \
             mock.patch.object(boot, "assemble_consultation_package",
                               side_effect=fake_consultation), \
             mock.patch.object(boot, "call_model", side_effect=fake_call_model):
            result = boot.run_step2_context_assembly(step1, {})

        relationship_view = engine_calls["assembly"]["conversation_rag"]
        self.assertEqual(relationship_view.count(small), 1)
        self.assertNotIn("OVERSIZED-UNIT", relationship_view)
        self.assertEqual(engine_calls["relationship_inputs"], [])
        self.assertEqual(consultation["conversation_context"], "")
        self.assertEqual(len(physical_calls), 1)
        prepared, stats = physical_calls[0]
        joined = "\n".join(message["content"] for message in prepared)
        self.assertEqual(joined.count(small), 1)
        self.assertNotIn("OVERSIZED-UNIT", joined)
        self.assertEqual(result["conversation_rag"], "")
        self.assertLessEqual(
            stats["estimated_call_input_tokens"], stats["safe_input_capacity"],
        )
        self.assertIsNone(boot._OPTIONAL_CONTEXT_CV.get())

    def test_synthesis_endpoint_honors_config_name(self):
        # Visual repair-on-miss synthesis must resolve from the named
        # configuration (fast → small), never the active configuration —
        # third instance of the class the campaign fidelity gate caught.
        calls = []

        def fake_get_slot_endpoint(config, slot, context="interactive",
                                   config_name=None):
            calls.append({"slot": slot, "config_name": config_name})
            return {"id": "cfg-model"} if slot == "fast" else None

        with mock.patch.object(boot, "get_slot_endpoint",
                               side_effect=fake_get_slot_endpoint), \
             mock.patch.object(boot, "load_routing_config", return_value={}):
            ep = boot._resolve_synthesis_endpoint("campaign-premium")
        self.assertEqual(ep, {"id": "cfg-model"})
        self.assertEqual(calls[0],
                         {"slot": "fast", "config_name": "campaign-premium"})

    def test_synthesis_endpoint_no_cross_config_fallback(self):
        # A named-config turn whose config has no fast/small endpoint must
        # SKIP synthesis (return None), not fall back to the active config.
        with mock.patch.object(boot, "get_slot_endpoint",
                               return_value=None), \
             mock.patch.object(boot, "load_routing_config",
                               return_value={"visual_synthesis":
                                             {"preferred": "active-model"}}):
            self.assertIsNone(
                boot._resolve_synthesis_endpoint("campaign-premium"))

    def test_unflagged_claim_scan_passes_config_name(self):
        calls = []

        def fake_get_slot_endpoint(config, slot, context="interactive",
                                   config_name=None):
            calls.append({"slot": slot, "config_name": config_name})
            return None  # scan degrades gracefully with no endpoint

        with mock.patch.object(boot, "get_slot_endpoint",
                               side_effect=fake_get_slot_endpoint):
            boot._run_unflagged_claim_scan(
                "## REVISED DRAFT\ntext", [], {},
                label="t", config_name="campaign-premium")
        self.assertTrue(calls)
        self.assertEqual(calls[0]["config_name"], "campaign-premium")

    def test_gear2_resolves_named_fast_cell_without_active_fallback(self):
        calls = []

        def fake_get_slot_endpoint(config, slot, context="interactive",
                                   config_name=None):
            calls.append((slot, config_name))
            return {"id": "campaign-fast"} if slot == "fast" else None

        with mock.patch.object(boot, "get_slot_endpoint",
                               side_effect=fake_get_slot_endpoint), \
             mock.patch.object(boot, "get_active_endpoint",
                               return_value={"id": "active-must-not-run"}):
            endpoint, slot = boot.resolve_single_pass_endpoint(
                {}, 2, config_name="campaign-optimum-plus")
        self.assertEqual(endpoint["id"], "campaign-fast")
        self.assertEqual(slot, "gear2_rag_lookup")
        self.assertEqual(calls[0], ("fast", "campaign-optimum-plus"))

    def test_missing_named_fast_cells_fail_closed(self):
        with mock.patch.object(boot, "get_slot_endpoint", return_value=None), \
             mock.patch.object(boot, "get_active_endpoint",
                               return_value={"id": "active-must-not-run"}):
            endpoint, slot = boot.resolve_single_pass_endpoint(
                {}, 2, config_name="campaign-optimum-plus")
        self.assertIsNone(endpoint)
        self.assertEqual(slot, "gear2_rag_lookup")

    def test_single_pass_trace_binds_slot_gear_and_configuration(self):
        observed = []

        def fake_call_model(messages, endpoint, images=None):
            observed.append(dict(boot._CALL_METADATA_CV.get() or {}))
            return "done"

        with mock.patch.object(boot, "call_model", side_effect=fake_call_model):
            result = boot.run_single_pass_with_tools(
                [{"role": "user", "content": "test"}],
                {"id": "campaign-fast"},
                slot="gear2_rag_lookup",
                gear=2,
                config_name="campaign-optimum-plus",
            )
        self.assertEqual(result, "done")
        self.assertEqual(observed, [{
            "step": "gear2-single-pass",
            "slot": "gear2_rag_lookup",
            "gear": 2,
            "config_name": "campaign-optimum-plus",
        }])

    def test_web_consultation_binds_named_utility_cell(self):
        observed = []

        def fake_call_model(messages, endpoint, images=None):
            observed.append(dict(boot._CALL_METADATA_CV.get() or {}))
            return "[]"

        invoke = boot._make_web_consultation_invoker(
            "campaign-optimum-plus", "step1_cleanup")
        with mock.patch.object(boot, "call_model", side_effect=fake_call_model):
            self.assertEqual(invoke([], {"id": "qwen/qwen3.5-9b"}), "[]")
            self.assertEqual(invoke([], {"id": "qwen/qwen3.5-9b"}), "[]")
        self.assertEqual(observed, [
            {
                "step": "web-consultation",
                "slot": "step1_cleanup",
                "gear": 1,
                "config_name": "campaign-optimum-plus",
            },
            {
                "step": "web-consultation",
                "slot": "step1_cleanup",
                "gear": 1,
                "config_name": "campaign-optimum-plus",
            },
        ])

    def test_analysis_slot_resolution_uses_exact_gear(self):
        class FakeRouter:
            def resolve_endpoint(self, slot, gear, context,
                                 config_name=None):
                return {"id": f"gear{gear}-{slot}"}

            @staticmethod
            def _to_v1_endpoint(endpoint):
                return dict(endpoint)

        with mock.patch.object(boot, "_get_router", return_value=FakeRouter()):
            gear3 = boot.get_analysis_slot_endpoint(
                {}, "breadth", 3, config_name="campaign-optimum-plus")
            gear4 = boot.get_analysis_slot_endpoint(
                {}, "breadth", 4, config_name="campaign-optimum-plus")
        self.assertEqual(gear3["id"], "gear3-breadth")
        self.assertEqual(gear4["id"], "gear4-breadth")


if __name__ == "__main__":
    unittest.main()
