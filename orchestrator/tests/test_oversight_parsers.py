"""Tests for the meta-layer oversight parsers.

Covers ped_parser, corpus_parser, workflow_spec_parser. Each is exercised
against a synthetic markdown fixture that matches the format described in
Reference — Meta-Layer Architecture §11.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace
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
            vault / "Projects" / "Ora" / "Framework — Problem Evolution.md",
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

    def test_malformed_frontmatter_is_explicitly_invalid(self):
        malformed = dedent("""\
            ---
            type: [corpus_template
            template_version: 1.0
            ---

            # Broken Corpus

            ## Sections
            """)
        corpus = parse_corpus_text(malformed, "broken.md")
        self.assertFalse(corpus.is_valid)
        self.assertIsNone(corpus.is_template)
        self.assertIn("Invalid YAML frontmatter", corpus.parse_error)

    def test_falsey_non_mapping_frontmatter_is_explicitly_invalid(self):
        body = "# Corpus\n\n## Sections\n\n### Section SalesQ2 — Quarterly Sales\n"
        for frontmatter in ("[]", "false", "0", "null"):
            with self.subTest(frontmatter=frontmatter):
                corpus = parse_corpus_text(
                    f"---\n{frontmatter}\n---\n\n{body}",
                    "falsey-frontmatter.md",
                )
                self.assertFalse(corpus.is_valid)
                self.assertIsNone(corpus.is_template)
                self.assertIn("expected a mapping", corpus.parse_error)

    def test_falsey_non_collection_tags_are_explicitly_invalid(self):
        body = "# Corpus\n\n## Sections\n\n### Section SalesQ2 — Quarterly Sales\n"
        for tags in ("{}", "false", "0", "null"):
            with self.subTest(tags=tags):
                corpus = parse_corpus_text(
                    f"---\ntype: incubator\ntags: {tags}\n---\n\n{body}",
                    "falsey-tags.md",
                )
                self.assertFalse(corpus.is_valid)
                self.assertIsNone(corpus.is_template)
                self.assertIn("tags must be a string or list", corpus.parse_error)

    def test_explicit_section_id_case_is_preserved(self):
        corpus = parse_corpus_text(dedent("""\
            ---
            type: corpus_template
            ---

            # Case-Sensitive Corpus

            ## Sections

            ### Section SalesQ2 — Quarterly Sales

            ### Auto Generated Name
            """), "case.md")
        self.assertTrue(corpus.is_valid)
        self.assertEqual(
            [section.section_id for section in corpus.sections],
            ["SalesQ2", "auto_generated_name"],
        )

    def test_canonical_incubator_tag_is_detected_as_instance(self):
        corpus = parse_corpus_text(dedent("""\
            ---
            type: incubator
            tags: [corpus-instance]
            period_identifier: Q2 2026
            ---

            # Quarterly Corpus — Q2 2026
            """), "instance.md")
        self.assertTrue(corpus.is_valid)
        self.assertFalse(corpus.is_template)
        self.assertEqual(corpus.instance_period, "Q2 2026")


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

    def test_publication_failure_is_retried_once_before_checkpoint(self):
        import ped_watcher
        from oversight_events import clear_handlers, emit, register_handler
        import oversight_events

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "oversight"
            ped_path = root / "ped.md"
            ped_path.write_text(
                "# Test\n\n## Active Milestones\n\n- [ ] Durable transition\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    ped_watcher, "OVERSIGHT_DATA_DIR", str(data), create=True,
                ),
                mock.patch.object(
                    oversight_events, "EVENT_LOG_PATH", str(root / "events.jsonl"),
                ),
            ):
                ped_watcher.write_ped_pointer("fixture", str(ped_path))
                ped_watcher.sweep(emit_event=lambda _event: None)
                ped_path.write_text(
                    "# Test\n\n## Active Milestones\n\n- [x] Durable transition\n",
                    encoding="utf-8",
                )

                event_log = root / "events.jsonl"
                real_write = os.write
                writes = 0

                def partial_write_then_fail(fd, payload):
                    nonlocal writes
                    writes += 1
                    if writes == 1:
                        prefix = max(1, len(payload) // 2)
                        return real_write(fd, payload[:prefix])
                    raise OSError("durable publication unavailable")

                with mock.patch.object(
                    oversight_events.os, "write",
                    side_effect=partial_write_then_fail,
                ):
                    with self.assertRaisesRegex(OSError, "publication unavailable"):
                        ped_watcher.sweep(emit_event=emit)
                self.assertFalse(
                    ped_watcher.load_last_state("fixture")["milestones"][
                        "Durable transition"
                    ]
                )
                self.assertTrue(event_log.read_bytes())
                self.assertFalse(event_log.read_bytes().endswith(b"\n"))

                handler_attempts = []
                clear_handlers()
                self.addCleanup(clear_handlers)
                def flaky_handler(event):
                    handler_attempts.append(event["publication_id"])
                    if len(handler_attempts) == 1:
                        raise OSError("downstream handler unavailable")

                register_handler(flaky_handler)
                with self.assertRaisesRegex(
                    OSError, "downstream handler unavailable",
                ):
                    ped_watcher.sweep(emit_event=emit)
                self.assertFalse(
                    ped_watcher.load_last_state("fixture")["milestones"][
                        "Durable transition"
                    ]
                )
                failed_records = [
                    json.loads(line)
                    for line in event_log.read_text(
                        encoding="utf-8"
                    ).splitlines()
                ]
                self.assertFalse(any(
                    oversight_events._DELIVERY_MARKER in record
                    for record in failed_records
                ))

                events = ped_watcher.sweep(emit_event=emit)
                self.assertEqual(len(handler_attempts), 2)
                self.assertEqual(len(set(handler_attempts)), 1)
                records = [
                    json.loads(line)
                    for line in event_log.read_text(encoding="utf-8").splitlines()
                    if "publication_id" in json.loads(line)
                ]
                self.assertEqual(len(records), 1)
                self.assertEqual(
                    records[0]["publication_id"], events[0].publication_id,
                )
                acknowledgments = [
                    json.loads(line)
                    for line in event_log.read_text(
                        encoding="utf-8"
                    ).splitlines()
                    if oversight_events._DELIVERY_MARKER in json.loads(line)
                ]
                self.assertEqual(len(acknowledgments), 1)
                self.assertEqual(ped_watcher.sweep(emit_event=emit), [])

    def test_stable_publication_is_idempotent_when_checkpoint_retries(self):
        import ped_watcher
        from oversight_events import clear_handlers, emit, register_handler
        import oversight_events
        import oversight_relationships
        import oversight_router
        import runtime_hygiene
        from orchestrator import oversight_router as qualified_router

        # The installed router may have been imported through either supported
        # module spelling (or may be the pre-reload function object). Match its
        # normalized module plus exact qualified name, never its name alone.
        self.assertIsNot(
            qualified_router.process_event, oversight_router.process_event,
        )
        alternate_event = {
            "event_type": "MilestoneClaimed",
            "publication_id": "alternate-module-publication",
        }
        frozen_alternate_event = {
            **alternate_event,
            "milestone_text": "Frozen before publication",
        }
        clear_handlers()
        register_handler(qualified_router.process_event)
        with mock.patch.object(
            oversight_router, "prepare_watcher_publication",
            return_value={
                "subject": {"publication_event": frozen_alternate_event},
            },
        ) as prepare:
            self.assertTrue(
                oversight_events._prepare_watcher_router(alternate_event),
            )
        prepare.assert_called_once()
        self.assertEqual(alternate_event, frozen_alternate_event)

        def unrelated_process_event(_event):
            return None

        unrelated_process_event.__qualname__ = (
            oversight_router.process_event.__qualname__
        )
        unrelated_process_event.__module__ = "unrelated.oversight_router"
        clear_handlers()
        register_handler(unrelated_process_event)
        with mock.patch.object(
            oversight_router, "prepare_watcher_publication",
        ) as prepare:
            self.assertFalse(
                oversight_events._prepare_watcher_router({
                    "event_type": "MilestoneClaimed",
                    "publication_id": "unrelated-module-publication",
                })
            )
        prepare.assert_not_called()
        clear_handlers()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "oversight"
            ped_path = root / "ped.md"
            ped_path.write_text(
                "# Test\n\n## Active Milestones\n\n- [ ] Stable identity\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    ped_watcher, "OVERSIGHT_DATA_DIR", str(data), create=True,
                ),
                mock.patch.object(
                    oversight_events, "EVENT_LOG_PATH", str(root / "events.jsonl"),
                ),
                mock.patch.object(
                    oversight_router, "ROUTER_LOG_PATH", root / "router.jsonl",
                ),
                mock.patch.object(
                    runtime_hygiene, "_root",
                    side_effect=lambda: root / "runtime-hygiene",
                ),
            ):
                ped_watcher.write_ped_pointer("fixture", str(ped_path))
                ped_watcher.sweep(emit_event=lambda _event: None)
                ped_path.write_text(
                    "# Test\n\n## Active Milestones\n\n- [x] Stable identity\n",
                    encoding="utf-8",
                )
                handler_attempts = []
                clear_handlers()
                self.addCleanup(clear_handlers)

                def record_handler_attempt(event):
                    handler_attempts.append(event["publication_id"])

                register_handler(oversight_router.process_event)
                register_handler(record_handler_attempt)

                event_log = root / "events.jsonl"
                real_fsync = os.fsync
                event_fsync_calls = 0

                def fail_first_fsync(fd):
                    nonlocal event_fsync_calls
                    is_event_log = (
                        event_log.exists()
                        and os.fstat(fd).st_ino == event_log.stat().st_ino
                    )
                    if is_event_log and event_fsync_calls == 0:
                        event_fsync_calls += 1
                        raise OSError("event fsync unavailable")
                    return real_fsync(fd)

                with mock.patch.object(
                    oversight_events.os, "fsync", side_effect=fail_first_fsync,
                ):
                    with self.assertRaisesRegex(OSError, "fsync unavailable"):
                        ped_watcher.sweep(emit_event=emit)
                self.assertFalse(
                    ped_watcher.load_last_state("fixture")["milestones"][
                        "Stable identity"
                    ]
                )
                self.assertEqual(len(event_log.read_text(
                    encoding="utf-8",
                ).splitlines()), 1)

                event_inode = event_log.stat().st_ino
                event_log_synced = False

                def record_fsync(fd):
                    nonlocal event_log_synced
                    if os.fstat(fd).st_ino == event_inode:
                        event_log_synced = True
                    return real_fsync(fd)

                with mock.patch.object(
                    oversight_events.os, "fsync", side_effect=record_fsync,
                ):
                    ped_watcher.sweep(emit_event=emit)
                self.assertTrue(event_log_synced)
                # Seeing an already-written event line proves only byte
                # publication. With no separate delivery acknowledgment, the
                # stable identity still has to reach downstream once.
                self.assertEqual(len(handler_attempts), 1)
                self.assertEqual(
                    len((root / "router.jsonl").read_text(
                        encoding="utf-8",
                    ).splitlines()),
                    1,
                )
                ledger = runtime_hygiene.EventLedger()
                first_delivery_id, _identity = (
                    oversight_router._watcher_delivery_identity({
                        "event_type": "MilestoneClaimed",
                        "publication_id": handler_attempts[0],
                    })
                )
                first_delivery = ledger.get(first_delivery_id)
                self.assertEqual(first_delivery["status"], "completed")
                self.assertIsInstance(first_delivery.get("receipt"), dict)
                self.assertTrue(first_delivery.get("effects_completed_at"))

                # A delivery-marker failure happens after every router sink and
                # its receipt, but before the claim may become terminal.
                ped_path.write_text(
                    "# Test\n\n## Active Milestones\n\n"
                    "- [x] Stable identity\n- [x] Second identity\n",
                    encoding="utf-8",
                )
                with mock.patch.object(
                    oversight_events, "_mark_publication_delivered",
                    side_effect=OSError("delivery marker unavailable"),
                ):
                    with self.assertRaisesRegex(
                        OSError, "delivery marker unavailable",
                    ):
                        ped_watcher.sweep(emit_event=emit)
                self.assertNotIn(
                    "Second identity",
                    ped_watcher.load_last_state("fixture")["milestones"],
                )
                second_publication_id = handler_attempts[-1]
                second_delivery_id, _identity = (
                    oversight_router._watcher_delivery_identity({
                        "event_type": "MilestoneClaimed",
                        "publication_id": second_publication_id,
                    })
                )
                second_delivery = ledger.get(second_delivery_id)
                self.assertEqual(second_delivery["status"], "claimed")
                self.assertIsInstance(second_delivery.get("receipt"), dict)
                self.assertTrue(second_delivery.get("effects_completed_at"))
                frozen_subject = second_delivery["subject"]

                # Startup recovery leaves only this delivery kind claimed. A
                # normal interrupted firing retains its existing terminal
                # failure behavior.
                ordinary_id = runtime_hygiene.event_identity(
                    "trigger_firing", {"trigger_id": "restart-control"},
                )
                ledger.claim(
                    event_id=ordinary_id,
                    event_type="trigger_firing",
                    subject={"trigger_id": "restart-control"},
                )
                restored = runtime_hygiene.restore_incomplete_events(ledger)
                self.assertIn(ordinary_id, restored)
                self.assertNotIn(second_delivery_id, restored)
                self.assertEqual(ledger.get(ordinary_id)["status"], "failed")
                self.assertEqual(
                    ledger.get(second_delivery_id)["status"], "claimed",
                )
                self.assertEqual(
                    ledger.get(second_delivery_id)["subject"], frozen_subject,
                )

                # The next retry sees the receipt and skips every router sink.
                # Its marker and router acknowledgment become durable before a
                # simulated watcher-checkpoint failure.
                with mock.patch.object(
                    ped_watcher, "write_state",
                    side_effect=OSError("checkpoint unavailable"),
                ):
                    with self.assertRaisesRegex(
                        OSError, "checkpoint unavailable",
                    ):
                        ped_watcher.sweep(emit_event=emit)
                self.assertNotIn(
                    "Second identity",
                    ped_watcher.load_last_state("fixture")["milestones"],
                )
                self.assertEqual(len(handler_attempts), 3)
                self.assertEqual(handler_attempts[1], handler_attempts[2])
                self.assertEqual(
                    len((root / "router.jsonl").read_text(
                        encoding="utf-8",
                    ).splitlines()),
                    2,
                )
                self.assertEqual(
                    ledger.get(second_delivery_id)["status"], "completed",
                )
                self.assertEqual(
                    ledger.get(second_delivery_id)["subject"], frozen_subject,
                )

                # Terminal retention may now prune that completed router
                # claim while the watcher still owes its checkpoint.
                with mock.patch.object(
                    runtime_hygiene, "LEDGER_TERMINAL_RETENTION", 1,
                ):
                    for index in range(2):
                        prune_id = runtime_hygiene.event_identity(
                            "watcher-prune-fixture", {"index": index},
                        )
                        ledger.claim(
                            event_id=prune_id,
                            event_type="watcher-prune-fixture",
                            subject={"index": index},
                        )
                        ledger.transition(
                            prune_id, {"claimed"}, "completed",
                            completed_at=ped_watcher._now_iso(),
                        )
                self.assertIsNone(ledger.get(second_delivery_id))

                # The retry has deliberately different transient metadata.
                # The durable marker is authoritative: it must suppress plan
                # preparation, every handler/fan-out, and any claim recreation;
                # the narrow missing-claim acknowledgment is idempotent success
                # and lets the watcher checkpoint advance.
                acknowledged = []
                real_acknowledge = (
                    oversight_router.acknowledge_watcher_publication
                )

                def record_acknowledgment(event):
                    outcome = real_acknowledge(event)
                    acknowledged.append(outcome)
                    return outcome

                changed_time = "2099-01-01T00:00:00+00:00"
                with (
                    mock.patch.object(
                        oversight_router, "prepare_watcher_publication",
                        side_effect=AssertionError(
                            "durable marker must bypass plan preparation"
                        ),
                    ),
                    mock.patch.object(
                        oversight_router, "acknowledge_watcher_publication",
                        side_effect=record_acknowledgment,
                    ),
                    mock.patch.object(
                        ped_watcher, "_now_iso", return_value=changed_time,
                    ),
                ):
                    ped_watcher.sweep(emit_event=emit)
                self.assertEqual(acknowledged, [True])
                self.assertEqual(
                    ped_watcher.load_last_state("fixture")["snapshot_at"],
                    changed_time,
                )
                self.assertIsNone(ledger.get(second_delivery_id))
                self.assertEqual(len(handler_attempts), 3)
                self.assertEqual(
                    len((root / "router.jsonl").read_text(
                        encoding="utf-8",
                    ).splitlines()),
                    2,
                )
                records = [
                    json.loads(line)
                    for line in event_log.read_text(
                        encoding="utf-8"
                    ).splitlines()
                ]
                publications = [
                    record for record in records if "publication_id" in record
                ]
                acknowledgments = [
                    record for record in records
                    if oversight_events._DELIVERY_MARKER in record
                ]
                self.assertEqual(len(publications), 2)
                self.assertEqual(len(acknowledgments), 2)
                self.assertEqual(
                    {record["publication_id"] for record in publications},
                    {record[oversight_events._DELIVERY_MARKER]
                     for record in acknowledgments},
                )

        def write_child(path, parent_nexus, spawned_from, *, complete):
            mark = "x" if complete else " "
            path.write_text(dedent(f"""\
                ---
                nexus:
                  - fixture
                type: PED
                parent_nexus: {parent_nexus}
                spawned_from_milestone: {spawned_from}
                ---

                # Child

                ## Active Milestones

                - [{mark}] Stable parent identity

                ## Decision Log

                """), encoding="utf-8")

        def write_parent(path, nexus):
            path.write_text(dedent(f"""\
                ---
                nexus:
                  - {nexus}
                type: PED
                ---

                # Parent

                ## Active Milestones

                - [ ] Observe child

                ## Decision Log

                """), encoding="utf-8")

        for original_available in (True, False):
            with self.subTest(
                stable_parent_destination_available=original_available,
            ):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    data = root / "oversight"
                    child_path = root / "child.md"
                    parent_a_path = root / "parent-a.md"
                    parent_b_path = root / "parent-b.md"
                    fanout_events = root / "fanout-events.jsonl"
                    fanout_actions = root / "fanout-actions.jsonl"
                    write_parent(parent_a_path, "parent-a")
                    write_parent(parent_b_path, "parent-b")
                    write_child(
                        child_path,
                        "parent-a",
                        "Original parent milestone",
                        complete=False,
                    )
                    with (
                        mock.patch.object(
                            ped_watcher,
                            "OVERSIGHT_DATA_DIR",
                            str(data),
                            create=True,
                        ),
                        mock.patch.object(
                            oversight_events,
                            "EVENT_LOG_PATH",
                            str(root / "events.jsonl"),
                        ),
                        mock.patch.object(
                            oversight_relationships,
                            "EVENTS_LOG_PATH",
                            str(fanout_events),
                        ),
                        mock.patch.object(
                            oversight_relationships,
                            "ACTIONS_LOG_PATH",
                            str(fanout_actions),
                        ),
                        mock.patch.object(
                            oversight_router,
                            "ROUTER_LOG_PATH",
                            root / "router.jsonl",
                        ),
                        mock.patch.object(
                            runtime_hygiene,
                            "_root",
                            side_effect=lambda: root / "runtime-hygiene",
                        ),
                    ):
                        ped_watcher.write_ped_pointer(
                            "fixture", str(child_path),
                        )
                        ped_watcher.write_ped_pointer(
                            "parent-a", str(parent_a_path),
                        )
                        ped_watcher.write_ped_pointer(
                            "parent-b", str(parent_b_path),
                        )
                        ped_watcher.sweep(emit_event=lambda _event: None)
                        write_child(
                            child_path,
                            "parent-a",
                            "Original parent milestone",
                            complete=True,
                        )
                        clear_handlers()
                        register_handler(oversight_router.process_event)

                        # The router's complete parent plan must already be
                        # durable when the event-row write begins. A crash in
                        # this exact gap may not run any visible sink, and a
                        # later rescan must not re-read changed routing facts.
                        event_log = root / "events.jsonl"
                        real_write = os.write

                        def fail_before_event_row(fd, payload):
                            is_event_log = (
                                event_log.exists()
                                and os.fstat(fd).st_ino
                                == event_log.stat().st_ino
                            )
                            if not is_event_log:
                                return real_write(fd, payload)
                            deliveries = runtime_hygiene.EventLedger().list_events(
                                event_type="watcher_router_delivery",
                            )
                            self.assertEqual(len(deliveries), 1)
                            subject = deliveries[0]["subject"]
                            plan = subject["parent_notification"]
                            self.assertEqual(plan["parent_nexus"], "parent-a")
                            self.assertEqual(
                                plan["parent_ped_path"],
                                str(parent_a_path.resolve()),
                            )
                            self.assertEqual(
                                plan["synthesized_event"]
                                ["spawned_from_milestone"],
                                "Original parent milestone",
                            )
                            self.assertEqual(
                                subject["publication_event"]["milestone_text"],
                                "Stable parent identity",
                            )
                            self.assertFalse((root / "router.jsonl").exists())
                            self.assertNotIn(
                                "Child Project Update: fixture",
                                parent_a_path.read_text(encoding="utf-8"),
                            )
                            self.assertFalse(fanout_events.exists())
                            self.assertFalse(fanout_actions.exists())
                            raise OSError("event row unavailable")

                        with mock.patch.object(
                            oversight_events.os,
                            "write",
                            side_effect=fail_before_event_row,
                        ):
                            with self.assertRaisesRegex(
                                OSError, "event row unavailable",
                            ):
                                ped_watcher.sweep(emit_event=emit)

                        self.assertTrue(event_log.exists())
                        self.assertEqual(event_log.read_bytes(), b"")
                        self.assertFalse(
                            ped_watcher.load_last_state("fixture")["milestones"]
                            ["Stable parent identity"]
                        )
                        delivery = runtime_hygiene.EventLedger().list_events(
                            event_type="watcher_router_delivery",
                        )
                        self.assertEqual(len(delivery), 1)
                        delivery_record = delivery[0]
                        delivery_id = delivery_record["event_id"]
                        frozen_subject = delivery_record["subject"]
                        self.assertEqual(delivery_record["status"], "claimed")
                        self.assertNotIn("receipt", delivery_record)
                        self.assertNotIn(
                            "effects_completed_at", delivery_record,
                        )
                        plan = frozen_subject["parent_notification"]

                        write_child(
                            child_path,
                            "parent-b",
                            "Changed parent milestone",
                            complete=True,
                        )
                        if not original_available:
                            parent_a_path.unlink()
                            with self.assertRaisesRegex(
                                OSError,
                                "bound parent PED destination is unavailable",
                            ):
                                ped_watcher.sweep(emit_event=emit)
                            self.assertFalse(
                                ped_watcher.load_last_state("fixture")
                                ["milestones"]["Stable parent identity"]
                            )
                            self.assertNotIn(
                                "Child Project Update: fixture",
                                parent_b_path.read_text(encoding="utf-8"),
                            )
                            self.assertFalse(fanout_events.exists())
                            self.assertFalse(fanout_actions.exists())
                            retained = runtime_hygiene.EventLedger().get(
                                delivery_id,
                            )
                            self.assertEqual(retained["status"], "claimed")
                            self.assertEqual(retained["subject"], frozen_subject)
                            self.assertNotIn("receipt", retained)
                            self.assertEqual(
                                runtime_hygiene.restore_incomplete_events(), [],
                            )
                            continue

                        with mock.patch.object(
                            oversight_relationships,
                            "_append_events_log",
                            side_effect=OSError("fan-out event log unavailable"),
                        ):
                            with self.assertRaisesRegex(
                                OSError, "fan-out event log unavailable",
                            ):
                                ped_watcher.sweep(emit_event=emit)

                        first_parent = parent_a_path.read_text(encoding="utf-8")
                        self.assertEqual(
                            first_parent.count("Child Project Update: fixture"),
                            1,
                        )
                        self.assertIn(
                            "Original parent milestone", first_parent,
                        )
                        self.assertFalse(
                            ped_watcher.load_last_state("fixture")["milestones"]
                            ["Stable parent identity"]
                        )
                        self.assertNotIn(
                            delivery_id,
                            runtime_hygiene.restore_incomplete_events(),
                        )
                        recovered_delivery = runtime_hygiene.EventLedger().get(
                            delivery_id,
                        )
                        self.assertEqual(recovered_delivery["status"], "claimed")
                        self.assertEqual(
                            recovered_delivery["subject"], frozen_subject,
                        )
                        self.assertEqual(plan["parent_nexus"], "parent-a")
                        self.assertEqual(
                            plan["parent_ped_path"],
                            str(parent_a_path.resolve()),
                        )
                        self.assertEqual(
                            plan["synthesized_event"]
                            ["spawned_from_milestone"],
                            "Original parent milestone",
                        )

                        ped_watcher.sweep(emit_event=emit)
                        completed_delivery = runtime_hygiene.EventLedger().get(
                            delivery_id,
                        )
                        self.assertEqual(
                            completed_delivery["status"], "completed",
                        )
                        self.assertEqual(
                            completed_delivery["subject"], frozen_subject,
                        )
                        self.assertIsInstance(
                            completed_delivery.get("receipt"), dict,
                        )
                        self.assertTrue(
                            completed_delivery.get("effects_completed_at"),
                        )
                        final_parent_a = parent_a_path.read_text(
                            encoding="utf-8",
                        )
                        final_parent_b = parent_b_path.read_text(
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            final_parent_a.count(
                                "Child Project Update: fixture",
                            ),
                            1,
                        )
                        self.assertIn(
                            plan["decision_log_entry"].rstrip(),
                            final_parent_a,
                        )
                        self.assertNotIn(
                            "Changed parent milestone", final_parent_a,
                        )
                        self.assertNotIn(
                            "Child Project Update: fixture", final_parent_b,
                        )
                        self.assertEqual(
                            [
                                json.loads(line)
                                for line in fanout_events.read_text(
                                    encoding="utf-8",
                                ).splitlines()
                            ],
                            [plan["synthesized_event"]],
                        )
                        self.assertEqual(
                            [
                                json.loads(line)
                                for line in fanout_actions.read_text(
                                    encoding="utf-8",
                                ).splitlines()
                            ],
                            [plan["actions_log_entry"]],
                        )
                        self.assertEqual(
                            len((root / "router.jsonl").read_text(
                                encoding="utf-8",
                            ).splitlines()),
                            1,
                        )
                        self.assertTrue(
                            ped_watcher.load_last_state("fixture")["milestones"]
                            ["Stable parent identity"]
                        )

    def test_ped_and_corpus_checkpoints_preserve_prior_bytes_on_failure(self):
        import corpus_watcher
        import ped_watcher

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "oversight"
            with (
                mock.patch.object(
                    ped_watcher, "OVERSIGHT_DATA_DIR", str(data), create=True,
                ),
                mock.patch.object(
                    corpus_watcher, "OVERSIGHT_DATA_DIR", str(data), create=True,
                ),
            ):
                ped_watcher.write_state("fixture", {"snapshot_at": "old-ped"})
                ped_path = Path(ped_watcher.project_state_path("fixture"))
                ped_before = ped_path.read_bytes()
                with mock.patch.object(
                    ped_watcher._rp, "atomic_write_text",
                    side_effect=OSError("checkpoint interrupted"),
                ):
                    with self.assertRaisesRegex(OSError, "interrupted"):
                        ped_watcher.write_state(
                            "fixture", {"snapshot_at": "new-ped"},
                        )
                self.assertEqual(ped_path.read_bytes(), ped_before)

                corpus_watcher.write_corpus_state(
                    "workflow", "instance.md", {"snapshot_at": "old-corpus"},
                )
                corpus_path = Path(corpus_watcher.corpus_state_path(
                    "workflow", "instance.md",
                ))
                corpus_before = corpus_path.read_bytes()
                with mock.patch.object(
                    corpus_watcher._rp, "atomic_write_text",
                    side_effect=OSError("checkpoint interrupted"),
                ):
                    with self.assertRaisesRegex(OSError, "interrupted"):
                        corpus_watcher.write_corpus_state(
                            "workflow", "instance.md",
                            {"snapshot_at": "new-corpus"},
                        )
                self.assertEqual(corpus_path.read_bytes(), corpus_before)

    def test_revisit_publication_id_uses_stable_deadline_not_rendered_age(self):
        import revisit_sweeper

        ped = SimpleNamespace(
            constraints=[],
            iteration_history=[{"iteration": 7, "raw_text": "2026-01-01"}],
        )
        with (
            mock.patch.object(revisit_sweeper, "parse_ped_file", return_value=ped),
            mock.patch.object(
                revisit_sweeper, "evaluate_age_based_review",
                side_effect=[
                    "Last iteration was 31 days ago (latest iteration #7)",
                    "Last iteration was 32 days ago (latest iteration #7)",
                ],
            ),
            mock.patch.object(
                revisit_sweeper, "age_review_deadline",
                return_value="2026-01-31T00:00:00+00:00",
            ),
        ):
            first = revisit_sweeper.sweep_project("fixture", "/tmp/ped.md")
            second = revisit_sweeper.sweep_project("fixture", "/tmp/ped.md")
        self.assertNotEqual(first.triggers_fired, second.triggers_fired)
        self.assertEqual(first.publication_id, second.publication_id)

    def test_deregistration_publishes_after_move_and_retries(self):
        import corpus_watcher
        import workflow_spec_sweeper

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "oversight"
            spec_path = str(Path(tmp) / "missing-workflow-spec.md")
            with (
                mock.patch.object(
                    corpus_watcher, "OVERSIGHT_DATA_DIR", str(data), create=True,
                ),
                mock.patch.object(
                    workflow_spec_sweeper, "OVERSIGHT_DATA_DIR",
                    str(data), create=True,
                ),
            ):
                corpus_watcher.write_workflow_pointer(
                    "workflow", "project", spec_path, "", "",
                )
                pointer = corpus_watcher.load_workflow_pointer("workflow")
                state = {
                    "pointer_registered_at": pointer["registered_at"],
                    "workflow_spec_path": spec_path,
                    "consecutive_misses": 3,
                    "first_missed_at": "2026-01-01T00:00:00+00:00",
                    "last_missed_at": "2026-01-01T00:10:00+00:00",
                    "drift_emitted": True,
                }
                workflow_spec_sweeper._save_sweeper_state("workflow", state)
                pointer_path = Path(corpus_watcher.workflow_pointer_path("workflow"))
                tombstone = Path(str(pointer_path) + ".deregistered")
                attempts = []

                def flaky_emit(event):
                    self.assertFalse(pointer_path.exists())
                    self.assertTrue(tombstone.exists())
                    attempts.append(event["publication_id"])
                    if len(attempts) == 1:
                        raise OSError("publication interrupted")

                with self.assertRaisesRegex(OSError, "publication interrupted"):
                    workflow_spec_sweeper._deregister_workflow(
                        "workflow", pointer, state, flaky_emit,
                    )
                workflow_spec_sweeper._recheck_one_tombstone(
                    str(data), "workflow", flaky_emit,
                )
                self.assertEqual(attempts, [attempts[0], attempts[0]])
                self.assertIsNone(
                    workflow_spec_sweeper._load_sweeper_state(
                        "workflow", pointer,
                    ) or None
                )

    def test_reregistration_publishes_after_restore_and_retries(self):
        import corpus_watcher
        import workflow_spec_sweeper

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "oversight"
            spec = Path(tmp) / "workflow-spec.md"
            with (
                mock.patch.object(
                    corpus_watcher, "OVERSIGHT_DATA_DIR", str(data), create=True,
                ),
                mock.patch.object(
                    workflow_spec_sweeper, "OVERSIGHT_DATA_DIR",
                    str(data), create=True,
                ),
            ):
                corpus_watcher.write_workflow_pointer(
                    "workflow", "project", str(spec), "", "",
                )
                pointer = corpus_watcher.load_workflow_pointer("workflow")
                state = {
                    "pointer_registered_at": pointer["registered_at"],
                    "workflow_spec_path": str(spec),
                    "consecutive_misses": 3,
                    "first_missed_at": "2026-01-01T00:00:00+00:00",
                    "last_missed_at": "2026-01-01T00:10:00+00:00",
                    "drift_emitted": True,
                }
                workflow_spec_sweeper._save_sweeper_state("workflow", state)
                workflow_spec_sweeper._deregister_workflow(
                    "workflow", pointer, state, lambda _event: None,
                )
                spec.write_text("# restored\n", encoding="utf-8")
                pointer_path = Path(corpus_watcher.workflow_pointer_path("workflow"))
                tombstone = Path(str(pointer_path) + ".deregistered")
                attempts = []

                def flaky_emit(event):
                    self.assertTrue(pointer_path.exists())
                    self.assertTrue(tombstone.exists())
                    attempts.append(event["publication_id"])
                    if len(attempts) == 1:
                        raise OSError("publication interrupted")

                with self.assertRaisesRegex(OSError, "publication interrupted"):
                    workflow_spec_sweeper._recheck_one_tombstone(
                        str(data), "workflow", flaky_emit,
                    )
                workflow_spec_sweeper._recheck_one_tombstone(
                    str(data), "workflow", flaky_emit,
                )
                self.assertEqual(attempts, [attempts[0], attempts[0]])
                self.assertTrue(pointer_path.exists())
                self.assertFalse(tombstone.exists())


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
        self.assertEqual(len(warnings), 1)
        self.assertIn("scalar string", warnings[0])

    def test_project_type_string_operation(self):
        from oversight_context import classify_matrix
        ped = self._ped_with_frontmatter("project_type: operation")
        classification, warnings = classify_matrix(ped)
        self.assertEqual(classification, "operation")
        self.assertEqual(len(warnings), 1)
        self.assertIn("scalar string", warnings[0])

    def test_project_type_string_passion(self):
        from oversight_context import classify_matrix
        ped = self._ped_with_frontmatter("project_type: passion")
        classification, warnings = classify_matrix(ped)
        self.assertEqual(classification, "passion")
        self.assertEqual(len(warnings), 1)
        self.assertIn("scalar string", warnings[0])

    def test_project_type_string_incubator(self):
        from oversight_context import classify_matrix
        ped = self._ped_with_frontmatter("project_type: incubator")
        classification, warnings = classify_matrix(ped)
        self.assertEqual(classification, "incubator")
        self.assertEqual(len(warnings), 1)
        self.assertIn("scalar string", warnings[0])

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
