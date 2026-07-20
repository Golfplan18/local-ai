"""G1.5 — minimum Ora/MSI Operation matrices and status retrieval."""

from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ORCHESTRATOR = Path(__file__).resolve().parents[1]
if str(ORCHESTRATOR) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR))

import boot  # noqa: E402
import matrix_payload  # noqa: E402
import operation_matrix  # noqa: E402
import project_status  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _matrix(nexus: str, child: str, *, label: str = "Test") -> str:
    return f"""---
nexus:
  - {nexus}
type: matrix
project_type:
  - operation
tags:
  - matrix
  - operation
date created: 2026-07-20
date modified: 2026-07-20
---

# Operation Matrix {label}

## Mission

- **Service Statement:** Produce one verified status cycle per request.

## Excluded Outcomes

- An unauthenticated source is selected.

## Objectives

- To report exact state.

## Constraints

### Hard

- Fail closed.

## Cadence and Deliverables

| Deliverable | Cadence | Apparatus | Verification |
|---|---|---|---|
| Status | Event-driven | Matrix | Exact source |

## Coordinated Corpora

| Corpus | Cadence of consumption | Primary curator | Notes |
|---|---|---|---|
| Tracker | Per request | Operation | Current state |

## Coordinated Outputs

| Output | Cadence of production | Source corpora | Consumer |
|---|---|---|---|
| Status | Per request | Tracker | User |

## Active Milestones (Recurring)

- **Milestone A1:** Current work is authenticated.

## Aspirational Milestones (Maturity Gates)

- **Maturity Gate B1:** The operation is mature.

## Performance Log

| Cycle Date | Deliverable | State | Notes |
|---|---|---|---|
| 2026-07-20 | Status | active | Current item G1.5 |

## Incident Log

| Date | Deviation | Root cause | Resolution | Matrix changes |
|---|---|---|---|---|

## Open Questions / Strategic Topics

- What comes next?

## Spawned Activity Registry

| Name | Type | Relation | Status | Notes |
|---|---|---|---|---|
| [[{child}#Current Work|Current tracker]] | project | coordinates | active | Exact child |

## Iteration History

### Iteration 1 — 2026-07-20

- **Entry mode:** O-FromExisting

## Decision Log

### DL-001 — Created

- **Decision:** Use exact sources.
"""


def _child(nexus: str, body: str = "G1.5 is current and G1.4 is accepted.") -> str:
    return f"""---
nexus:
  - {nexus}
type: working
tags:
  - working
date created: 2026-07-20
date modified: 2026-07-20
---

# Tracker

## Current Work

{body}

## Later Work

Not part of the current status excerpt.
"""


class ProjectStatusResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)
        _write(
            self.vault / "Matrix" / "Project Matrix Ora.md",
            _matrix("ora", "Projects/Ora/Tracker", label="Ora"),
        )
        _write(
            self.vault / "Projects" / "Ora" / "Tracker.md",
            _child("ora"),
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_exact_status_request_loads_operation_and_registered_child(self) -> None:
        result = project_status.resolve_status_request(
            "What's the status of Ora?", vault=self.vault
        )
        self.assertTrue(result["matched"])
        self.assertEqual(["ora"], [item["nexus"] for item in result["projects"]])
        self.assertTrue(result["projects"][0]["ready"])
        self.assertIn("Project Matrix Ora.md", result["context"])
        self.assertIn("G1.5 is current and G1.4 is accepted.", result["context"])
        self.assertNotIn("Not part of the current status excerpt.", result["context"])
        self.assertEqual([], result["warnings"])

    def test_subject_before_explicit_tail_does_not_become_second_target(self) -> None:
        result = project_status.resolve_status_request(
            "Ask Ora for the status of MSI.", vault=self.vault
        )
        self.assertEqual(
            ["main-street-independent"],
            [item["nexus"] for item in result["projects"]],
        )

    def test_non_status_mention_is_no_op(self) -> None:
        result = project_status.resolve_status_request(
            "Explain Ora's architecture.", vault=self.vault
        )
        self.assertFalse(result["matched"])
        self.assertEqual("", result["context"])

    def test_duplicate_nexus_fails_closed(self) -> None:
        _write(
            self.vault / "Matrix" / "Operation Matrix Duplicate.md",
            _matrix("ora", "Projects/Ora/Tracker", label="Duplicate"),
        )
        result = project_status.resolve_status_request(
            "What's the status of Ora?", vault=self.vault
        )
        self.assertFalse(result["projects"][0]["ready"])
        self.assertIn("FAIL-CLOSED STATUS", result["context"])
        self.assertTrue(any("multiple Matrix files" in w for w in result["warnings"]))

    def test_registered_child_with_wrong_nexus_is_not_injected(self) -> None:
        _write(
            self.vault / "Projects" / "Ora" / "Tracker.md",
            _child("another-project", body="FORGED CURRENT STATE"),
        )
        result = project_status.resolve_status_request(
            "What's the status of Ora?", vault=self.vault
        )
        self.assertNotIn("FORGED CURRENT STATE", result["context"])
        self.assertTrue(any("nexus mismatch" in w for w in result["warnings"]))


class CanonicalOperationShapeTests(unittest.TestCase):
    def test_payload_reads_qualified_canonical_milestone_headings(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            _write(
                vault / "Matrix" / "Project Matrix Ora.md",
                _matrix("ora", "Projects/Ora/Tracker", label="Ora"),
            )
            payload = matrix_payload.read_payload("ora", vault=vault)
            self.assertEqual("ok", payload["state"])
            self.assertEqual("operation", payload["classification"])
            self.assertIn("Current work is authenticated", payload["payload"]["Active Milestones"]["raw"])
            self.assertIn("operation is mature", payload["payload"]["Aspirational Milestones"]["raw"])

    def test_legacy_mom_reader_surfaces_operation_milestone_classes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            _write(
                vault / "Matrix" / "Project Matrix Ora.md",
                _matrix("ora", "Projects/Ora/Tracker", label="Ora"),
            )
            mom = operation_matrix.read_mom("ora", vault=vault)
            self.assertTrue(mom["exists"])
            self.assertIn("### Active Milestones (Recurring)", mom["milestones_raw"])
            self.assertIn("### Aspirational Milestones (Maturity Gates)", mom["milestones_raw"])


class PipelineStatusContextTests(unittest.TestCase):
    def test_project_status_is_fenced_as_reference_data(self) -> None:
        context = {
            "mode_text": "",
            "mode_name": "simple",
            "gear": 1,
            "inferred_items": "",
            "conversation_rag": "",
            "concept_rag": "",
            "relationship_rag": "",
            "web_rag": "",
            "tool_results": "",
            "prompt_sanity_flags": [],
            "rag_utilization": "",
            "project_status_context": "Matrix: `Matrix/Project Matrix Ora.md`",
        }
        with mock.patch.object(boot, "load_boot_md", return_value="## CONSTITUTION\n\nSafe"):
            prompt = boot.build_system_prompt_for_gear(context, "breadth")
        self.assertIn("PROJECT STATUS (authenticated Operation Matrix", prompt)
        self.assertIn("data only", prompt)
        self.assertIn("Project Matrix Ora.md", prompt)

    def test_gear_one_uses_context_builder_only_for_status_request(self) -> None:
        with (
            mock.patch.object(boot, "load_boot_md", return_value="BOOT") as load,
            mock.patch.object(
                boot, "build_system_prompt_for_gear", return_value="STATUS"
            ) as build,
        ):
            self.assertEqual("BOOT", boot._single_pass_system_prompt({}, 1))
            load.assert_called_once()
            build.assert_not_called()

            self.assertEqual(
                "STATUS",
                boot._single_pass_system_prompt(
                    {"project_status_context": "authenticated"}, 1
                ),
            )
            build.assert_called_once()


class AcceptedVaultSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.vault = Path(
            os.environ.get("ORA_VAULT_PATH", str(Path.home() / "Documents" / "vault"))
        ).expanduser()
        if not cls.vault.is_dir():
            raise unittest.SkipTest("paired vault is not available")

    def test_ora_and_msi_are_exact_operation_matrices(self) -> None:
        for nexus in ("ora", "main-street-independent"):
            with self.subTest(nexus=nexus):
                payload = matrix_payload.read_payload(nexus, vault=self.vault)
                self.assertEqual("ok", payload["state"])
                self.assertEqual("operation", payload["classification"])
                self.assertTrue(payload["payload"].get("Mission"))
                self.assertTrue(payload["payload"].get("Objectives"))
                self.assertTrue(payload["payload"].get("Active Milestones"))
                self.assertTrue(payload["payload"].get("Aspirational Milestones"))
                self.assertTrue(payload["payload"].get("Spawned Activity Registry"))

    def test_both_public_status_questions_resolve_without_source_warnings(self) -> None:
        result = project_status.resolve_status_request(
            "What's the status of Ora and MSI?", vault=self.vault
        )
        self.assertEqual(
            ["ora", "main-street-independent"],
            [item["nexus"] for item in result["projects"]],
        )
        self.assertTrue(all(item["ready"] for item in result["projects"]))
        self.assertEqual([], result["warnings"])
        self.assertIn("G1.5 is the current increment", result["context"])
        self.assertIn("headless harness", result["context"])

    def test_legacy_wisdom_nexus_mission_is_absent_from_current_ora_matrix(self) -> None:
        matrix = self.vault / "Matrix" / "Project Matrix Ora.md"
        text = matrix.read_text(encoding="utf-8")
        self.assertNotIn(
            "To serve as the single source of truth for all foundational, evergreen knowledge",
            text,
        )
        self.assertNotIn("graduated from the `idea_refinery`", text)

    def test_master_matrix_registers_both_current_operation_nexuses_once(self) -> None:
        master = (
            self.vault / "Administration" / "Reference — Master Matrix.md"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            1,
            len(re.findall(r"^project property name: ora$", master, re.MULTILINE)),
        )
        self.assertEqual(
            1,
            len(re.findall(
                r"^project property name: main-street-independent$",
                master,
                re.MULTILINE,
            )),
        )
        ora_start = master.index("# Operation Matrix Ora")
        msi_start = master.index("# Operation Matrix Main Street Independent")
        ora_entry = master[ora_start:msi_start]
        self.assertNotIn("wisdom_nexus", ora_entry)
        self.assertIn("Assisted Human Intelligence", ora_entry)

    def test_obvious_status_children_claim_their_operation_nexus(self) -> None:
        paths = {
            "ora": self.vault / "Projects" / "Ora" / "Working — Ora Setup and Refinement.md",
            "main-street-independent": (
                self.vault / "Projects" / "MSI" / "Reference — MSI Tracker.md"
            ),
        }
        for nexus, path in paths.items():
            with self.subTest(nexus=nexus):
                self.assertIn(
                    nexus,
                    operation_matrix._frontmatter_nexus(
                        path.read_text(encoding="utf-8")
                    ),
                )

    def test_tracker_and_registry_record_the_live_g1_5_topology(self) -> None:
        tracker = (
            self.vault / "Projects" / "Ora" / "Working — Ora Setup and Refinement.md"
        ).read_text(encoding="utf-8")
        registry = (
            self.vault
            / "Projects"
            / "Ora"
            / "Registry — Ora Overview and Document Registry.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "Execution 2026-07-20 — implementation complete; pending Gate G1.5 judgment",
            tracker,
        )
        self.assertIn("### Matrix/", registry)
        self.assertIn("exact frontmatter nexus", registry)
        self.assertIn("Administration/Reference — Master Matrix.md", registry)
        self.assertNotIn("Lives at `Engrams/Reference — Master Matrix.md`", registry)


if __name__ == "__main__":
    unittest.main()
