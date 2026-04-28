#!/usr/bin/env python3
"""
Unit tests for ``orchestrator/visual_validator.py`` (WP-1.6).

Runs under the stdlib ``unittest`` runner — no pytest dependency in the
ora runtime. Invoke::

    /opt/homebrew/bin/python3 -m unittest discover -s ~/ora/orchestrator/tests -v
    # or
    /opt/homebrew/bin/python3 ~/ora/orchestrator/tests/test_visual_validator.py

Coverage:
* Golden-path: every ``examples/*.valid.json`` envelope validates true.
* Invalid-path: every ``examples/*.invalid.json`` envelope validates false
  and reports at least one schema error.
* Per-type structural checks exercised with hand-authored fixtures:
  CLD polarity-parity, declared-non-cycle loop, decision-tree probability
  sums, IBIS grammar violations, reference resolution, fishbone depth /
  framework, stock-and-flow DAG, influence-diagram temporal order, ACH
  non-diagnostic evidence, concept-map cross-link warning, tornado sort.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

from visual_validator import (  # noqa: E402
    CODES,
    Error,
    ValidationResult,
    validate_envelope,
    SCHEMAS_ROOT,
    _check_causal_loop_diagram,
    _check_decision_tree,
    _check_ibis,
    _check_stock_and_flow,
    _check_fishbone,
    _check_influence_diagram,
    _check_ach_matrix,
    _check_quadrant_matrix,
    _check_concept_map,
    _check_tornado,
    _check_causal_dag,
    _has_cycle,
)

EXAMPLES = SCHEMAS_ROOT / "examples"


def _load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text())


# ---------------------------------------------------------------------------
# Golden-path and invalid-path sweeps over all 22 types
# ---------------------------------------------------------------------------

class TestSchemaSweep(unittest.TestCase):
    """22 valid envelopes pass; 22 invalid envelopes fail with schema errors."""

    def test_every_valid_example_validates(self):
        files = sorted(EXAMPLES.glob("*.valid.json"))
        self.assertEqual(len(files), 22, "expected 22 *.valid.json examples")
        for path in files:
            with self.subTest(example=path.name):
                env = json.loads(path.read_text())
                result = validate_envelope(env)
                self.assertTrue(
                    result.valid,
                    f"{path.name} should validate; errors: {[e.message[:60] for e in result.errors]}",
                )
                self.assertEqual([], result.errors)

    def test_every_invalid_example_rejected(self):
        files = sorted(EXAMPLES.glob("*.invalid.json"))
        self.assertEqual(len(files), 22, "expected 22 *.invalid.json examples")
        for path in files:
            with self.subTest(example=path.name):
                env = json.loads(path.read_text())
                result = validate_envelope(env)
                self.assertFalse(result.valid, f"{path.name} should fail validation")
                self.assertGreaterEqual(len(result.errors), 1)
                for err in result.errors:
                    self.assertTrue(err.code.startswith("E_"))


# ---------------------------------------------------------------------------
# Envelope-level behavior
# ---------------------------------------------------------------------------

class TestEnvelopeBehavior(unittest.TestCase):
    def test_not_a_dict_is_rejected(self):
        result = validate_envelope("not a dict")  # type: ignore[arg-type]
        self.assertFalse(result.valid)
        self.assertEqual(result.errors[0].code, CODES["E_MISSING_FIELD"])

    def test_note_field_stripped_and_warned(self):
        env = _load_example("comparison.valid.json")
        env["_note"] = "a note"
        result = validate_envelope(env)
        self.assertTrue(result.valid)
        codes = [w.code for w in result.warnings]
        self.assertIn(CODES["W_NOTE_FIELD_STRIPPED"], codes)

    def test_missing_title_emits_warning(self):
        env = _load_example("comparison.valid.json")
        env.pop("title", None)
        result = validate_envelope(env)
        self.assertTrue(result.valid)
        codes = [w.code for w in result.warnings]
        self.assertIn(CODES["W_MISSING_TITLE"], codes)

    def test_unknown_major_version_warns(self):
        env = _load_example("comparison.valid.json")
        env["schema_version"] = "9.0"
        result = validate_envelope(env)
        codes = [w.code for w in result.warnings]
        self.assertIn(CODES["W_UNKNOWN_MAJOR"], codes)

    def test_valid_result_has_zero_errors(self):
        env = _load_example("decision_tree.valid.json")
        result = validate_envelope(env)
        self.assertIsInstance(result, ValidationResult)
        self.assertTrue(result.valid)
        self.assertEqual(0, len(result.errors))


# ---------------------------------------------------------------------------
# Causal loop diagram — deep structural checks
# ---------------------------------------------------------------------------

class TestCausalLoopDiagram(unittest.TestCase):
    def _cld_spec(self) -> dict:
        return copy.deepcopy(_load_example("causal_loop_diagram.valid.json")["spec"])

    def test_valid_cld_has_no_findings(self):
        errs = _check_causal_loop_diagram(self._cld_spec())
        errors = [e for e in errs if e.severity == "error"]
        self.assertEqual([], errors)

    def test_loop_polarity_parity_mismatch(self):
        spec = self._cld_spec()
        # The canonical loop has one '-' edge → type B (odd count).
        # Flip the declaration to R and expect E_GRAPH_CYCLE.
        spec["loops"][0]["type"] = "R"
        errs = _check_causal_loop_diagram(spec)
        codes = [e.code for e in errs if e.severity == "error"]
        self.assertIn(CODES["E_GRAPH_CYCLE"], codes)

    def test_declared_loop_non_cycle(self):
        """A loop whose members assert an edge that doesn't exist is flagged."""
        spec = self._cld_spec()
        # Replace links so the V->T edge is missing; loop still claims V,T,F.
        spec["links"] = [
            {"from": "T", "to": "F", "polarity": "+"},
            {"from": "F", "to": "V", "polarity": "-"},
        ]
        errs = _check_causal_loop_diagram(spec)
        codes = [e.code for e in errs]
        self.assertIn(CODES["E_UNRESOLVED_REF"], codes)

    def test_unresolved_edge_endpoint(self):
        spec = self._cld_spec()
        spec["links"][0]["to"] = "UNKNOWN"
        errs = _check_causal_loop_diagram(spec)
        codes = [e.code for e in errs if e.severity == "error"]
        self.assertIn(CODES["E_UNRESOLVED_REF"], codes)

    def test_duplicate_variable_id(self):
        spec = self._cld_spec()
        spec["variables"].append({"id": "V", "label": "duplicate"})
        errs = _check_causal_loop_diagram(spec)
        codes = [e.code for e in errs if e.severity == "error"]
        self.assertIn(CODES["E_UNRESOLVED_REF"], codes)

    def test_orphan_node_warning_without_allow_isolated(self):
        spec = self._cld_spec()
        spec["variables"].append({"id": "X", "label": "Orphan"})
        errs = _check_causal_loop_diagram(spec)
        warns = [e for e in errs if e.severity == "warning"]
        self.assertTrue(any(w.code == CODES["W_ORPHAN_NODE"] for w in warns))

    def test_orphan_allowed_when_flag_set(self):
        spec = self._cld_spec()
        spec["variables"].append({"id": "X", "label": "Orphan"})
        spec["allow_isolated"] = True
        errs = _check_causal_loop_diagram(spec)
        warns = [e for e in errs if e.code == CODES["W_ORPHAN_NODE"]]
        self.assertEqual([], warns)


# ---------------------------------------------------------------------------
# Decision tree
# ---------------------------------------------------------------------------

class TestDecisionTree(unittest.TestCase):
    def _dt(self) -> dict:
        return copy.deepcopy(_load_example("decision_tree.valid.json")["spec"])

    def test_valid_tree_has_no_errors(self):
        errs = _check_decision_tree(self._dt())
        self.assertEqual([], [e for e in errs if e.severity == "error"])

    def test_probability_sum_too_low(self):
        spec = self._dt()
        spec["root"]["children"][0]["node"]["children"][1]["probability"] = 0.3  # 0.6+0.3
        errs = _check_decision_tree(spec)
        self.assertTrue(any(e.code == CODES["E_PROB_SUM"] for e in errs))

    def test_probability_out_of_range(self):
        spec = self._dt()
        spec["root"]["children"][0]["node"]["children"][0]["probability"] = 1.5
        errs = _check_decision_tree(spec)
        self.assertTrue(any(e.code == CODES["E_PROB_SUM"] for e in errs))

    def test_probability_missing_on_chance_edge(self):
        spec = self._dt()
        del spec["root"]["children"][0]["node"]["children"][0]["probability"]
        errs = _check_decision_tree(spec)
        self.assertTrue(any(e.code == CODES["E_PROB_SUM"] for e in errs))

    def test_probability_on_decision_edge_rejected(self):
        spec = self._dt()
        spec["root"]["children"][0]["probability"] = 0.5  # decision node has no prob
        errs = _check_decision_tree(spec)
        self.assertTrue(any(e.code == CODES["E_PROB_SUM"] for e in errs))

    def test_terminal_missing_payoff_in_decision_mode(self):
        spec = self._dt()
        del spec["root"]["children"][0]["node"]["children"][0]["node"]["payoff"]
        errs = _check_decision_tree(spec)
        self.assertTrue(any(e.code == CODES["E_UNRESOLVED_REF"] for e in errs))


# ---------------------------------------------------------------------------
# IBIS grammar
# ---------------------------------------------------------------------------

class TestIbisGrammar(unittest.TestCase):
    def _ibis(self) -> dict:
        return copy.deepcopy(_load_example("ibis.valid.json")["spec"])

    def test_legal_triples(self):
        errs = _check_ibis(self._ibis())
        self.assertEqual([], [e for e in errs if e.severity == "error"])

    def test_pro_cannot_respond_to_question(self):
        spec = self._ibis()
        spec["edges"].append({"from": "P1", "to": "Q1", "type": "responds_to"})
        errs = _check_ibis(spec)
        self.assertTrue(any(e.code == CODES["E_IBIS_GRAMMAR"] for e in errs))

    def test_idea_cannot_support_idea(self):
        spec = self._ibis()
        spec["edges"].append({"from": "I1", "to": "I1", "type": "supports"})
        errs = _check_ibis(spec)
        self.assertTrue(any(e.code == CODES["E_IBIS_GRAMMAR"] for e in errs))

    def test_con_must_object_to_idea(self):
        spec = self._ibis()
        spec["edges"].append({"from": "C1", "to": "Q1", "type": "objects_to"})
        errs = _check_ibis(spec)
        self.assertTrue(any(e.code == CODES["E_IBIS_GRAMMAR"] for e in errs))

    def test_questions_edge_must_originate_from_question(self):
        spec = self._ibis()
        spec["edges"].append({"from": "I1", "to": "Q1", "type": "questions"})
        errs = _check_ibis(spec)
        self.assertTrue(any(e.code == CODES["E_IBIS_GRAMMAR"] for e in errs))

    def test_unresolved_edge_endpoint_reported(self):
        spec = self._ibis()
        spec["edges"].append({"from": "I1", "to": "NOT_REAL", "type": "responds_to"})
        errs = _check_ibis(spec)
        self.assertTrue(any(e.code == CODES["E_UNRESOLVED_REF"] for e in errs))


# ---------------------------------------------------------------------------
# Stock and flow
# ---------------------------------------------------------------------------

class TestStockAndFlow(unittest.TestCase):
    def _snf(self) -> dict:
        return copy.deepcopy(_load_example("stock_and_flow.valid.json")["spec"])

    def test_valid_snf_no_errors(self):
        errs = _check_stock_and_flow(self._snf())
        self.assertEqual([], [e for e in errs if e.severity == "error"])

    def test_flow_endpoint_unresolved(self):
        spec = self._snf()
        spec["flows"][0]["to"] = "GHOST"
        errs = _check_stock_and_flow(spec)
        self.assertTrue(any(e.code == CODES["E_UNRESOLVED_REF"] for e in errs))

    def test_isolated_stock_warning(self):
        spec = self._snf()
        spec["stocks"].append({"id": "orphan_stock", "label": "lonely"})
        errs = _check_stock_and_flow(spec)
        self.assertTrue(any(e.code == CODES["W_STOCK_ISOLATED"] for e in errs))

    def test_aux_info_link_cycle_rejected(self):
        spec = self._snf()
        spec["auxiliaries"] = [{"id": "a"}, {"id": "b"}]
        spec["info_links"] = [
            {"from": "a", "to": "b"},
            {"from": "b", "to": "a"},
        ]
        errs = _check_stock_and_flow(spec)
        self.assertTrue(any(e.code == CODES["E_GRAPH_CYCLE"] for e in errs))


# ---------------------------------------------------------------------------
# Fishbone
# ---------------------------------------------------------------------------

class TestFishbone(unittest.TestCase):
    def test_framework_violation(self):
        spec = copy.deepcopy(_load_example("fishbone.valid.json")["spec"])
        spec["categories"].append({"name": "Aardvark", "causes": [{"text": "x"}]})
        errs = _check_fishbone(spec)
        self.assertTrue(any(e.code == CODES["E_UNRESOLVED_REF"] for e in errs))

    def test_depth_exceeds_three(self):
        spec = copy.deepcopy(_load_example("fishbone.valid.json")["spec"])
        spec["categories"] = [{
            "name": "Machine",
            "causes": [
                {"text": "L1", "sub_causes": [
                    {"text": "L2", "sub_causes": [
                        {"text": "L3", "sub_causes": [
                            {"text": "L4"},
                        ]},
                    ]},
                ]},
            ],
        }]
        errs = _check_fishbone(spec)
        self.assertTrue(any("exceeds depth 3" in e.message for e in errs))

    def test_effect_as_solution_soft_warn(self):
        spec = copy.deepcopy(_load_example("fishbone.valid.json")["spec"])
        spec["effect"] = "Reduce deployment failures"
        errs = _check_fishbone(spec)
        self.assertTrue(any(e.code == CODES["W_EFFECT_SOLUTION_PHRASED"] for e in errs))


# ---------------------------------------------------------------------------
# Influence diagram
# ---------------------------------------------------------------------------

class TestInfluenceDiagram(unittest.TestCase):
    def _id_spec(self) -> dict:
        return copy.deepcopy(_load_example("influence_diagram.valid.json")["spec"])

    def test_requires_exactly_one_value_node(self):
        spec = self._id_spec()
        spec["nodes"].append({"id": "V2", "label": "Profit2", "kind": "value"})
        errs = _check_influence_diagram(spec)
        self.assertTrue(any(e.code == CODES["E_UNRESOLVED_REF"] and "value node" in e.message for e in errs))

    def test_temporal_order_violation(self):
        spec = self._id_spec()
        # valid order is [C1, D1]; reverse it so C1->D1 becomes "later → earlier"
        spec["temporal_order"] = ["D1", "C1"]
        errs = _check_influence_diagram(spec)
        self.assertTrue(any("temporal_order" in e.message for e in errs))

    def test_functional_cycle_rejected(self):
        spec = self._id_spec()
        # Add C1 <- V1 functional arc to introduce a cycle C1->V1->C1.
        spec["arcs"].append({"from": "V1", "to": "C1", "type": "functional"})
        errs = _check_influence_diagram(spec)
        self.assertTrue(any(e.code == CODES["E_GRAPH_CYCLE"] for e in errs))


# ---------------------------------------------------------------------------
# ACH matrix
# ---------------------------------------------------------------------------

class TestAchMatrix(unittest.TestCase):
    def _ach(self) -> dict:
        return copy.deepcopy(_load_example("ach_matrix.valid.json")["spec"])

    def test_nondiagnostic_row_warning(self):
        spec = self._ach()
        spec["cells"]["E1"] = {"H1": "C", "H2": "C"}
        errs = _check_ach_matrix(spec)
        self.assertTrue(any(e.code == CODES["W_ACH_NONDIAGNOSTIC"] for e in errs))

    def test_missing_cell_error(self):
        spec = self._ach()
        del spec["cells"]["E1"]["H2"]
        errs = _check_ach_matrix(spec)
        self.assertTrue(any(e.code == CODES["E_UNRESOLVED_REF"] for e in errs))


# ---------------------------------------------------------------------------
# Quadrant matrix
# ---------------------------------------------------------------------------

class TestQuadrantMatrix(unittest.TestCase):
    def _q(self) -> dict:
        return copy.deepcopy(_load_example("quadrant_matrix.valid.json")["spec"])

    def test_scenario_planning_empty_narrative_blocked(self):
        spec = self._q()
        spec["quadrants"]["TL"]["narrative"] = ""
        errs = _check_quadrant_matrix(spec)
        self.assertTrue(any("narrative" in e.message for e in errs))

    def test_empty_axes_rationale_blocked(self):
        spec = self._q()
        spec["axes_independence_rationale"] = "   "
        errs = _check_quadrant_matrix(spec)
        self.assertTrue(any("axes_independence_rationale" in e.path for e in errs))


# ---------------------------------------------------------------------------
# Concept map
# ---------------------------------------------------------------------------

class TestConceptMap(unittest.TestCase):
    def test_cross_link_warning_absent_triggers(self):
        spec = copy.deepcopy(_load_example("concept_map.valid.json")["spec"])
        for p in spec["propositions"]:
            p.pop("is_cross_link", None)
        errs = _check_concept_map(spec)
        self.assertTrue(any(e.code == CODES["W_NO_CROSS_LINKS"] for e in errs))

    def test_unresolved_concept_ref(self):
        spec = copy.deepcopy(_load_example("concept_map.valid.json")["spec"])
        spec["propositions"][0]["from_concept"] = "GHOST"
        errs = _check_concept_map(spec)
        self.assertTrue(any(e.code == CODES["E_UNRESOLVED_REF"] for e in errs))


# ---------------------------------------------------------------------------
# Tornado
# ---------------------------------------------------------------------------

class TestTornado(unittest.TestCase):
    def test_sort_by_swing_unsorted_rejected(self):
        spec = copy.deepcopy(_load_example("tornado.valid.json")["spec"])
        # Put the low-swing param first.
        spec["parameters"].reverse()
        errs = _check_tornado(spec)
        self.assertTrue(any("sorted by" in e.message for e in errs))

    def test_sort_by_custom_does_not_trigger(self):
        spec = copy.deepcopy(_load_example("tornado.valid.json")["spec"])
        spec["sort_by"] = "custom"
        spec["parameters"].reverse()
        errs = _check_tornado(spec)
        self.assertEqual([], errs)


# ---------------------------------------------------------------------------
# Causal DAG
# ---------------------------------------------------------------------------

class TestCausalDag(unittest.TestCase):
    def test_valid_dsl_passes(self):
        spec = copy.deepcopy(_load_example("causal_dag.valid.json")["spec"])
        self.assertEqual([], _check_causal_dag(spec))

    def test_cycle_detected(self):
        spec = {"dsl": "dag { a -> b; b -> a }", "focal_exposure": "a", "focal_outcome": "b"}
        errs = _check_causal_dag(spec)
        self.assertTrue(any(e.code == CODES["E_GRAPH_CYCLE"] for e in errs))

    def test_focal_exposure_missing(self):
        spec = {"dsl": "dag { a -> b }", "focal_exposure": "ghost", "focal_outcome": "b"}
        errs = _check_causal_dag(spec)
        self.assertTrue(any(e.code == CODES["E_UNRESOLVED_REF"] for e in errs))

    def test_empty_dsl_rejected(self):
        errs = _check_causal_dag({"dsl": "", "focal_exposure": "", "focal_outcome": ""})
        self.assertTrue(any(e.code == CODES["E_DSL_PARSE"] for e in errs))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestHelpers(unittest.TestCase):
    def test_has_cycle_detects_self_loop(self):
        self.assertTrue(_has_cycle({"a": ["a"]}))

    def test_has_cycle_detects_2_cycle(self):
        self.assertTrue(_has_cycle({"a": ["b"], "b": ["a"]}))

    def test_has_cycle_returns_false_on_dag(self):
        self.assertFalse(_has_cycle({"a": ["b"], "b": ["c"], "c": []}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
