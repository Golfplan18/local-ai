"""Tests for the meta-layer oversight parsers.

Covers ped_parser, corpus_parser, workflow_spec_parser. Each is exercised
against a synthetic markdown fixture that matches the format described in
Reference — Meta-Layer Architecture §11.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from textwrap import dedent
from unittest import mock

# Make orchestrator/ importable
HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.dirname(HERE)
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)

from ped_parser import (  # noqa: E402
    parse_ped_text,
    Constraint,
)
from corpus_parser import parse_corpus_text  # noqa: E402
from workflow_spec_parser import (  # noqa: E402
    parse_workflow_spec_text,
    check_reference_integrity,
)
import oversight_context as oc  # noqa: E402


class TestOversightContextRuntimePath(unittest.TestCase):
    def test_bundle_pef_default_uses_current_shared_vault(self):
        vault = Path("/tmp/oversight-context-vault")
        with mock.patch.object(oc._rp, "vault_dir", return_value=vault):
            bundle = oc.OversightContextBundle(event={}, event_class="unknown")
        self.assertEqual(
            Path(bundle.pef_toolkit_reference),
            vault / "Framework — Problem Evolution.md",
        )


# ---------- PED parser tests ----------

class TestPEDParser(unittest.TestCase):

    SAMPLE_PED = dedent("""\
        ---
        nexus:
          - test_project
        type: PED
        date created: 2026-05-04
        ---

        # Test Project Problem Evolution Document

        ## Problem Definition

        We need to make sure the meta-layer oversight apparatus actually works.

        ## Mission

        - **Resolution Statement:** All four phases of the meta-layer apparatus run end-to-end without manual intervention, completing one full project cycle.
        - **Core Essence:** Demonstrate that the oversight architecture is operational.
        - **Emotional Drivers:**
          - I want this to actually work, not just look like it works.
          - I need confidence that drift will be caught at framework seams.

        ## Excluded Outcomes

        - The system runs but logs are empty — no events are firing.
        - Events fire but no verdicts are produced.
        - Verdicts produce but no Decision Log entries are written.

        ## Constraints

        - **Hard:** Must use existing Ora orchestrator infrastructure. Violation: would require parallel runtime.
        - **Soft:** Prefer minimal new dependencies. Cost of violation: maintenance burden.
        - **Working Assumption:** PED files are markdown with consistent structure. Revisit trigger: when a PED format change is proposed.

        ## Objectives

        - To demonstrate the meta-layer apparatus end-to-end.
        - To verify drift detection at framework transitions.

        ## Active Milestones

        - [ ] PED parser produces structured records from real PEDs
        - [x] Watchers detect file-state changes
        - [ ] Verdict actions write Decision Log entries

        ## Aspirational Milestones

        - **Milestone B1:** Live integration with a real Shape 4 corpus-mediated workflow.
        - **Milestone B2:** Heartbeat monitoring catches a deliberately-killed watcher within 6 minutes.

        ## Decision Log

        ### 2026-05-04 — Project initialized
        - Initial Oversight Specification written via OS-Setup
        - Pattern detected: Single framework, project-tied

        ## Oversight Specification

        ```yaml
        oversight_specification:
          triggers_active: [milestone_claimed, framework_complete]
          framework_chain:
            - id: terrain-mapping
            - id: process-inference
          per_milestone_criteria: use_declared
          revisit_triggers: []
          escalation_contact: user
        ```
        """)

    def test_frontmatter(self):
        ped = parse_ped_text(self.SAMPLE_PED, "test.md")
        self.assertEqual(ped.frontmatter.get("nexus"), ["test_project"])

    def test_title(self):
        ped = parse_ped_text(self.SAMPLE_PED, "test.md")
        self.assertEqual(ped.title, "Test Project Problem Evolution Document")

    def test_mission(self):
        ped = parse_ped_text(self.SAMPLE_PED, "test.md")
        self.assertIn("All four phases", ped.mission_resolution_statement)
        self.assertIn("Demonstrate", ped.mission_core_essence)
        self.assertEqual(len(ped.mission_emotional_drivers), 2)

    def test_excluded_outcomes(self):
        ped = parse_ped_text(self.SAMPLE_PED, "test.md")
        self.assertEqual(len(ped.excluded_outcomes), 3)
        self.assertIn("logs are empty", ped.excluded_outcomes[0])

    def test_constraints(self):
        ped = parse_ped_text(self.SAMPLE_PED, "test.md")
        self.assertEqual(len(ped.constraints), 3)
        types = sorted([c.classification for c in ped.constraints])
        self.assertEqual(types, ["Hard", "Soft", "Working Assumption"])
        wa = next(c for c in ped.constraints if c.classification == "Working Assumption")
        self.assertIn("PED files are markdown", wa.statement)
        self.assertIn("when a PED format change is proposed", wa.revisit_trigger)

    def test_objectives(self):
        ped = parse_ped_text(self.SAMPLE_PED, "test.md")
        self.assertEqual(len(ped.objectives), 2)

    def test_active_milestones_checkboxes(self):
        ped = parse_ped_text(self.SAMPLE_PED, "test.md")
        self.assertEqual(len(ped.active_milestones), 3)
        self.assertFalse(ped.active_milestones[0].is_complete)
        self.assertTrue(ped.active_milestones[1].is_complete)
        self.assertFalse(ped.active_milestones[2].is_complete)

    def test_aspirational_milestones_bold_format(self):
        ped = parse_ped_text(self.SAMPLE_PED, "test.md")
        self.assertEqual(len(ped.aspirational_milestones), 2)
        self.assertEqual(ped.aspirational_milestones[0].milestone_id, "B1")

    def test_decision_log(self):
        ped = parse_ped_text(self.SAMPLE_PED, "test.md")
        self.assertEqual(len(ped.decision_log), 1)
        self.assertEqual(ped.decision_log[0].date, "2026-05-04")

    def test_oversight_specification(self):
        ped = parse_ped_text(self.SAMPLE_PED, "test.md")
        self.assertIsNotNone(ped.oversight_specification)
        spec = ped.oversight_specification
        self.assertIn("milestone_claimed", spec.triggers_active)
        self.assertEqual(len(spec.framework_chain), 2)
        self.assertEqual(spec.escalation_contact, "user")


# ---------- Corpus parser tests ----------

class TestCorpusParser(unittest.TestCase):

    SAMPLE_TEMPLATE = dedent("""\
        ---
        type: corpus_template
        template_version: 1.0
        ---

        # Marketing Monthly Corpus Template

        ## Sections

        ```yaml
        sections:
          - id: weekly_sales
            name: Weekly Sales
            source: pff-mortgage-pipeline
            missing_data_behavior: hold-and-warn
            oversight:
              schema: |
                Required columns: week_start, week_end, unit_volume, dollar_volume
              cadence: weekly
              cross_section_rules:
                - "week_start and week_end must align with campaigns section"
              triggers_active: [section_populated, validated]
          - id: campaigns
            name: Campaign Performance
            source: pff-campaign-extractor
            missing_data_behavior: default-empty
            oversight:
              schema: |
                Required columns: campaign_id, period_start, period_end, impressions, conversions
              cadence: weekly
              cross_section_rules: []
              triggers_active: [section_populated]
        chain_relationships:
          - direction: output
            other_corpus: company_quarterly_rollup
            sections_involved: [weekly_sales, campaigns]
        ```
        """)

    def test_template_detection(self):
        c = parse_corpus_text(self.SAMPLE_TEMPLATE, "test.md")
        self.assertTrue(c.is_template)

    def test_section_count(self):
        c = parse_corpus_text(self.SAMPLE_TEMPLATE, "test.md")
        self.assertEqual(len(c.sections), 2)

    def test_section_oversight_loaded(self):
        c = parse_corpus_text(self.SAMPLE_TEMPLATE, "test.md")
        s0 = c.sections[0]
        self.assertEqual(s0.section_id, "weekly_sales")
        self.assertEqual(s0.source_pff, "pff-mortgage-pipeline")
        self.assertIsNotNone(s0.oversight)
        self.assertEqual(s0.oversight.cadence, "weekly")
        self.assertEqual(len(s0.oversight.cross_section_rules), 1)

    def test_chain_relationships(self):
        c = parse_corpus_text(self.SAMPLE_TEMPLATE, "test.md")
        self.assertEqual(len(c.chain_relationships), 1)
        rel = c.chain_relationships[0]
        self.assertEqual(rel.direction, "output")
        self.assertEqual(rel.other_corpus, "company_quarterly_rollup")


# ---------- Workflow spec parser tests ----------

class TestWorkflowSpecParser(unittest.TestCase):

    SAMPLE_SPEC = dedent("""\
        ---
        nexus:
          - test_project
        type: framework
        tags: [workflow-spec]
        workflow_id: marketing-monthly-corpus
        workflow: Marketing Monthly Corpus
        owner: marketing-team
        corpus_template: ~/ora/workflows/marketing/corpus-template.md
        corpus_instance_directory: ~/ora/workflows/marketing/instances
        pffs:
          - name: pff-mortgage-pipeline
            path: ~/ora/frameworks/pff-mortgage-pipeline.md
            writes_to_section: weekly_sales
          - name: pff-campaign-extractor
            path: ~/ora/frameworks/pff-campaign-extractor.md
            writes_to_section: campaigns
        offs:
          - name: monthly-board-memo
            path: ~/ora/frameworks/off-monthly-board-memo.md
            reads_from_sections: [weekly_sales, campaigns]
        chain_relationships:
          - direction: output
            other_corpus: company_quarterly_rollup
            sections_involved: [weekly_sales, campaigns]
        oversight:
          chain_propagation_rules:
            - source: marketing-monthly-corpus
              dependent: company-quarterly-rollup
              action: re_validate
              condition: section_updated
          off_dependency_rules:
            - off_id: monthly-board-memo
              sections_required: [weekly_sales, campaigns]
              stale_threshold_days: 7
          cadence_coordination:
            - sequence: [pff-mortgage-pipeline, pff-campaign-extractor]
              reason: campaign attribution depends on sales window closing first
          escalation_overrides:
            chain_propagation: source_corpus_owner
        ---

        # Marketing Monthly Corpus

        Body text describing the workflow.
        """)

    def test_top_level_fields(self):
        spec = parse_workflow_spec_text(self.SAMPLE_SPEC, "test.md")
        self.assertEqual(spec.workflow_id, "marketing-monthly-corpus")
        self.assertEqual(spec.workflow_name, "Marketing Monthly Corpus")
        self.assertEqual(spec.owner, "marketing-team")

    def test_pffs_offs(self):
        spec = parse_workflow_spec_text(self.SAMPLE_SPEC, "test.md")
        self.assertEqual(len(spec.pffs), 2)
        self.assertEqual(len(spec.offs), 1)
        self.assertEqual(spec.pffs[0].writes_to_section, "weekly_sales")
        self.assertEqual(spec.offs[0].reads_from_sections, ["weekly_sales", "campaigns"])

    def test_oversight_rules(self):
        spec = parse_workflow_spec_text(self.SAMPLE_SPEC, "test.md")
        self.assertIsNotNone(spec.oversight)
        self.assertEqual(len(spec.oversight.chain_propagation_rules), 1)
        rule = spec.oversight.chain_propagation_rules[0]
        self.assertEqual(rule.action, "re_validate")
        self.assertEqual(len(spec.oversight.off_dependency_rules), 1)
        self.assertEqual(spec.oversight.off_dependency_rules[0].stale_threshold_days, 7)

    def test_reference_integrity_clean(self):
        spec = parse_workflow_spec_text(self.SAMPLE_SPEC, "test.md")
        # All sections present, files marked existing
        existing = {p.path: True for p in spec.pffs}
        existing.update({o.path: True for o in spec.offs})
        issues = check_reference_integrity(
            spec,
            corpus_template_sections=["weekly_sales", "campaigns"],
            framework_files_exist=existing,
        )
        self.assertEqual(issues, [])

    def test_reference_integrity_missing_file(self):
        spec = parse_workflow_spec_text(self.SAMPLE_SPEC, "test.md")
        existing = {p.path: False for p in spec.pffs}  # all PFFs missing
        existing.update({o.path: True for o in spec.offs})
        issues = check_reference_integrity(
            spec,
            corpus_template_sections=["weekly_sales", "campaigns"],
            framework_files_exist=existing,
        )
        missing = [i for i in issues if i.issue_type == "missing_file"]
        self.assertEqual(len(missing), 2)

    def test_reference_integrity_stale_section(self):
        spec = parse_workflow_spec_text(self.SAMPLE_SPEC, "test.md")
        # Pretend the corpus template lacks one of the sections
        issues = check_reference_integrity(
            spec,
            corpus_template_sections=["weekly_sales"],  # campaigns missing
        )
        stale = [i for i in issues if i.issue_type == "stale_reference"]
        self.assertGreaterEqual(len(stale), 1)


# ---------- Diff helpers ----------

class TestPEDWatcherDiff(unittest.TestCase):

    def test_milestone_state_change_detected(self):
        from ped_watcher import diff_milestones

        prior = {"milestones": {"M1": False, "M2": True}}
        current = {"milestones": {"M1": True, "M2": True}}

        changes = diff_milestones(prior, current)
        self.assertEqual(changes, [("M1", False, True)])

    def test_no_change(self):
        from ped_watcher import diff_milestones

        prior = {"milestones": {"M1": False}}
        current = {"milestones": {"M1": False}}
        self.assertEqual(diff_milestones(prior, current), [])

    def test_new_milestone_completed(self):
        from ped_watcher import diff_milestones

        prior = {"milestones": {"M1": False}}
        current = {"milestones": {"M1": False, "M2": True}}
        # New milestone completed counts as a change
        changes = diff_milestones(prior, current)
        self.assertIn(("M2", False, True), changes)


# ---------- Event classification ----------

class TestOversightContextClassification(unittest.TestCase):

    def test_project_level(self):
        from oversight_context import classify_event
        self.assertEqual(classify_event({"event_type": "MilestoneClaimed"}), "project-level")
        self.assertEqual(classify_event({"event_type": "FrameworkComplete"}), "project-level")

    def test_workflow_level(self):
        from oversight_context import classify_event
        self.assertEqual(classify_event({"event_type": "CorpusSectionPopulated"}), "workflow-level")
        self.assertEqual(classify_event({"event_type": "ChainPropagationRequired"}), "workflow-level")

    def test_unknown(self):
        from oversight_context import classify_event
        self.assertEqual(classify_event({"event_type": "Foo"}), "unknown")


# ---------- Routing ----------

class TestOversightRouting(unittest.TestCase):

    def test_standalone_event_skipped(self):
        from oversight_router import should_route_to_oversight
        self.assertFalse(should_route_to_oversight({
            "event_type": "FrameworkComplete",
            # no project_nexus, no workflow_id
        }))

    def test_project_event_routed(self):
        from oversight_router import should_route_to_oversight
        self.assertTrue(should_route_to_oversight({
            "event_type": "MilestoneClaimed",
            "project_nexus": "test_project",
        }))

    def test_milestone_complete_only_routes_on_drift(self):
        from oversight_router import should_route_to_oversight
        self.assertFalse(should_route_to_oversight({
            "event_type": "MilestoneComplete",
            "project_nexus": "test_project",
            "drift_status": "IN_SCOPE",
        }))
        self.assertTrue(should_route_to_oversight({
            "event_type": "MilestoneComplete",
            "project_nexus": "test_project",
            "drift_status": "DRIFT_DETECTED",
        }))

    def test_log_only_events_skipped(self):
        from oversight_router import should_route_to_oversight
        self.assertFalse(should_route_to_oversight({
            "event_type": "FrameworkStarted",
            "project_nexus": "test_project",
        }))


# ---------- Matrix-type-aware lock loading (Process Coherence v3.0) ----------
#
# Closes DCP Drift Report 2026-05-10 Finding 1: oversight_context now reads
# project_type from matrix frontmatter and dispatches to one of four
# classifications (project / operation / passion / incubator). Each
# classification surfaces a different lock set per Process Coherence v3.0
# Layer 1 step 2 and Framework — Operations Manifest's Universal
# Problem-Definition Lock extension.

class TestMatrixClassification(unittest.TestCase):
    """Exercise classify_matrix() across the full input space.

    The classifier reads frontmatter project_type and resolves to one of
    four classifications. Tests cover absent / single-string / single-element
    list / multi-element list (with and without classification tokens) /
    invalid-type frontmatter.
    """

    def _ped_with_frontmatter(self, frontmatter_yaml: str):
        from ped_parser import parse_ped_text
        body = (
            "---\n"
            f"{frontmatter_yaml}\n"
            "---\n\n"
            "# Test Matrix\n\n"
            "## Mission\n\n"
            "- **Resolution Statement:** Trivial endpoint statement.\n"
        )
        return parse_ped_text(body, file_path="/tmp/test-matrix.md")

    def test_project_type_absent_defaults_to_project(self):
        from oversight_context import classify_matrix
        ped = self._ped_with_frontmatter("nexus:\n  - test")
        classification, warnings = classify_matrix(ped)
        self.assertEqual(classification, "project")
        self.assertEqual(len(warnings), 1)
        self.assertIn("project_type absent", warnings[0])

    def test_project_type_string_project(self):
        from oversight_context import classify_matrix
        ped = self._ped_with_frontmatter("project_type: project")
        classification, warnings = classify_matrix(ped)
        self.assertEqual(classification, "project")
        self.assertEqual(warnings, [])

    def test_project_type_string_operation(self):
        from oversight_context import classify_matrix
        ped = self._ped_with_frontmatter("project_type: operation")
        classification, warnings = classify_matrix(ped)
        self.assertEqual(classification, "operation")
        self.assertEqual(warnings, [])

    def test_project_type_string_passion(self):
        from oversight_context import classify_matrix
        ped = self._ped_with_frontmatter("project_type: passion")
        classification, warnings = classify_matrix(ped)
        self.assertEqual(classification, "passion")
        self.assertEqual(warnings, [])

    def test_project_type_string_incubator(self):
        from oversight_context import classify_matrix
        ped = self._ped_with_frontmatter("project_type: incubator")
        classification, warnings = classify_matrix(ped)
        self.assertEqual(classification, "incubator")
        self.assertEqual(warnings, [])

    def test_project_type_list_with_one_classification_plus_content(self):
        # Per the Project Type Registry convention, a matrix may declare
        # both a classification and content tokens (e.g., a Project that's
        # also a book-shaped deliverable).
        from oversight_context import classify_matrix
        ped = self._ped_with_frontmatter("project_type:\n  - operation\n  - book")
        classification, warnings = classify_matrix(ped)
        self.assertEqual(classification, "operation")
        self.assertEqual(warnings, [])

    def test_project_type_list_content_only_defaults_to_project(self):
        # The registry allows content-only declarations (e.g., a knowledge
        # cluster). Default to project with a warning so the user can
        # tighten the matrix later if needed.
        from oversight_context import classify_matrix
        ped = self._ped_with_frontmatter("project_type:\n  - book\n  - knowledge")
        classification, warnings = classify_matrix(ped)
        self.assertEqual(classification, "project")
        self.assertEqual(len(warnings), 1)
        self.assertIn("no classification token", warnings[0])

    def test_project_type_multiple_classifications_raises(self):
        from oversight_context import classify_matrix, InvalidProjectTypeError
        ped = self._ped_with_frontmatter("project_type:\n  - operation\n  - passion")
        with self.assertRaises(InvalidProjectTypeError) as cm:
            classify_matrix(ped)
        self.assertIn("multiple classifications", str(cm.exception))
        self.assertEqual(cm.exception.matrix_path, "/tmp/test-matrix.md")

    def test_project_type_invalid_python_type_raises(self):
        from oversight_context import classify_matrix, InvalidProjectTypeError
        # YAML int isn't a valid project_type representation.
        ped = self._ped_with_frontmatter("project_type: 42")
        with self.assertRaises(InvalidProjectTypeError) as cm:
            classify_matrix(ped)
        self.assertIn("unsupported", str(cm.exception))


class TestTypeSpecificLockLoading(unittest.TestCase):
    """Verify each classification's lock set matches Process Coherence v3.0."""

    def _build_ped(self, frontmatter_yaml: str, mission_section: str,
                   excluded: str = "", constraints: str = "",
                   cadence: str = "") -> "ParsedPED":
        from ped_parser import parse_ped_text
        parts = [
            "---",
            frontmatter_yaml,
            "---",
            "",
            "# Test Matrix",
            "",
            "## Mission",
            "",
            mission_section,
        ]
        if excluded:
            parts += ["", "## Excluded Outcomes", "", excluded]
        if constraints:
            parts += ["", "## Constraints", "", constraints]
        if cadence:
            parts += ["", "## Cadence and Deliverables", "", cadence]
        return parse_ped_text("\n".join(parts), file_path="/tmp/test-matrix.md")

    def test_project_locks_have_resolution_statement(self):
        from oversight_context import load_locks_for_matrix
        ped = self._build_ped(
            "project_type: project",
            "- **Resolution Statement:** The thing is built and shipped.",
            excluded="- The thing looks built but isn't.",
            constraints="- **Hard:** Budget cap. Cost of violation: project death.",
        )
        locks, classification, warnings = load_locks_for_matrix(ped)
        self.assertEqual(classification, "project")
        self.assertEqual(locks["matrix_classification"], "project")
        self.assertEqual(
            locks["mission_resolution_statement"],
            "The thing is built and shipped.",
        )
        self.assertIn("The thing looks built but isn't.", locks["excluded_outcomes"])
        self.assertEqual(len(locks["constraints"]), 1)
        self.assertEqual(locks["constraints"][0]["classification"], "Hard")
        # Project locks DON'T carry operation-specific or passion-specific fields.
        self.assertNotIn("mission_service_statement", locks)
        self.assertNotIn("cycle_shape_near_miss_patterns", locks)
        self.assertNotIn("cadence_rule", locks)

    def test_operation_locks_have_service_statement_cadence_and_near_miss(self):
        from oversight_context import (
            load_locks_for_matrix,
            CYCLE_SHAPE_NEAR_MISS_PATTERNS,
        )
        ped = self._build_ped(
            "project_type: operation",
            (
                "- **Service Statement:** Publish a weekly column on Sundays.\n"
                "- **Core Essence:** Sustained editorial cadence.\n"
            ),
            excluded="- Cadence met but quality degraded.",
            constraints="- **Hard:** No skipping weeks. Cost: subscriber churn.",
            cadence="| Deliverable | Cadence | Apparatus |\n| Column | Weekly Sunday 9am | MSI editorial board |",
        )
        locks, classification, warnings = load_locks_for_matrix(ped)
        self.assertEqual(classification, "operation")
        self.assertEqual(locks["matrix_classification"], "operation")
        self.assertEqual(
            locks["mission_service_statement"],
            "Publish a weekly column on Sundays.",
        )
        self.assertEqual(
            locks["mission_core_essence"],
            "Sustained editorial cadence.",
        )
        self.assertEqual(
            locks["cycle_shape_near_miss_patterns"],
            CYCLE_SHAPE_NEAR_MISS_PATTERNS,
        )
        self.assertIn("Weekly Sunday 9am", locks["cadence_rule"])
        # Operation locks DON'T carry the project-only Resolution Statement.
        self.assertNotIn("mission_resolution_statement", locks)
        self.assertNotIn("mission_critical_unknown", locks)

    def test_passion_locks_have_core_essence_emotional_drivers_no_endpoint(self):
        from oversight_context import load_locks_for_matrix
        ped = self._build_ped(
            "project_type: passion",
            (
                "- **Core Essence:** Cultivate philosophical depth in mathematics.\n"
                "- **Emotional Drivers:**\n"
                "  - I want to feel mathematically literate.\n"
                "  - I need to engage with deep ideas.\n"
            ),
            constraints=(
                "- **Soft:** Limit reading to 30 minutes a day. "
                "Cost of violation: encroaches on family time.\n"
                "- **Working Assumption:** Books are the right medium. "
                "Revisit trigger: when a course form proves more effective.\n"
            ),
        )
        locks, classification, warnings = load_locks_for_matrix(ped)
        self.assertEqual(classification, "passion")
        self.assertEqual(locks["matrix_classification"], "passion")
        self.assertEqual(
            locks["mission_core_essence"],
            "Cultivate philosophical depth in mathematics.",
        )
        self.assertEqual(len(locks["mission_emotional_drivers"]), 2)
        # Passion locks have NO endpoint.
        self.assertNotIn("mission_resolution_statement", locks)
        self.assertNotIn("mission_service_statement", locks)
        self.assertNotIn("excluded_outcomes", locks)
        # Soft + Working Assumption only — no Hard constraints for a Passion.
        for c in locks["constraints"]:
            self.assertIn(c["classification"], ("Soft", "Working Assumption"))
        # Classification-drift warning is surfaced in the lock set itself
        # so a downstream evaluator sees it without re-reading the spec.
        self.assertIn("passion_terminal_claim_warning", locks)

    def test_incubator_locks_have_critical_unknown(self):
        from oversight_context import load_locks_for_matrix
        ped = self._build_ped(
            "project_type: incubator",
            (
                "- **Critical Unknown:** Whether the dataset has signal at all.\n"
                "- **Resolution Statement:** The Critical Unknown — whether the "
                "dataset has signal at all — has been answered in the form of a "
                "preregistered analysis and a yes/no verdict.\n"
            ),
            excluded="- Conclusion based on cherry-picked subsets.",
            constraints="- **Hard:** No p-hacking. Cost: invalidates the answer.",
        )
        locks, classification, warnings = load_locks_for_matrix(ped)
        self.assertEqual(classification, "incubator")
        self.assertEqual(locks["matrix_classification"], "incubator")
        self.assertEqual(
            locks["mission_critical_unknown"],
            "Whether the dataset has signal at all.",
        )
        self.assertIn(
            "preregistered analysis",
            locks["mission_resolution_statement"],
        )

    def test_invalid_classification_propagates_through_load_context(self):
        from oversight_context import (
            OversightContextBundle,
            _load_project_level_context,
        )
        # Fixture: a matrix file on disk with multiple classifications.
        # _load_project_level_context catches InvalidProjectTypeError and
        # surfaces it as a load_error rather than crashing the bundle build.
        import tempfile
        from textwrap import dedent
        body = dedent("""\
            ---
            nexus:
              - bad_test
            project_type:
              - operation
              - passion
            ---

            # Bad Matrix

            ## Mission

            - **Resolution Statement:** Whatever.
        """)
        with tempfile.TemporaryDirectory() as td:
            ped_file = os.path.join(td, "PED.md")
            with open(ped_file, "w") as f:
                f.write(body)
            # Stub load_ped_path so it returns our temp file.
            import oversight_context as oc
            original = oc.load_ped_path
            try:
                oc.load_ped_path = lambda nexus: ped_file
                bundle = OversightContextBundle(
                    event={"event_type": "MilestoneClaimed", "project_nexus": "bad_test"},
                    event_class="project-level",
                )
                _load_project_level_context(
                    {"event_type": "MilestoneClaimed", "project_nexus": "bad_test"},
                    bundle,
                )
            finally:
                oc.load_ped_path = original
        self.assertEqual(len(bundle.load_errors), 1)
        self.assertIn("multiple classifications", bundle.load_errors[0])
        self.assertIsNone(bundle.project_level_locks)


if __name__ == "__main__":
    unittest.main()
