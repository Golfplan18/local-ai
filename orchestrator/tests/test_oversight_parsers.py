"""Tests for the meta-layer oversight parsers.

Covers ped_parser, corpus_parser, workflow_spec_parser. Each is exercised
against a synthetic markdown fixture that matches the format described in
Reference — Meta-Layer Architecture §11.
"""
from __future__ import annotations

import os
import sys
import unittest
from textwrap import dedent

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


if __name__ == "__main__":
    unittest.main()
