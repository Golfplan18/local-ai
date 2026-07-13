"""Tests for type-specific Matrix payload readers.

Covers matrix_payload.read_payload for all five classifications:
Project, Passion (legacy + newer), Operation, and Incubator.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.dirname(HERE)
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)

from matrix_payload import read_payload  # noqa: E402


# ---- Fixtures ----

_PROJECT_MATRIX = """\
---
nexus:
  - my-project
project_type:
  - project
type: matrix
---

# Project Matrix My Project

## Mission

- **Resolution Statement:** Ship the widget by December.

## Objectives

- To build the widget.
- To test the widget.

## Milestones

- [x] Design complete
- [ ] Build complete
- [ ] Ship to customers
"""

_PASSION_LEGACY_MATRIX = """\
---
nexus:
  - my-passion
project_type:
  - passion
type: matrix
---

# Passion Matrix My Passion

## Mission

- **Core Essence:** Explore the world.
- **Emotional Drivers:**
    - I want to learn.
    - I feel curious.

## Objectives

- To read broadly.
- To write reflections.

## Milestones

- [ ] Read 10 books
- [x] Write first essay

## Projects

Some projects content.

## Files

Some files content.

## Problem Solving

Some problem-solving content.

## Spawned Activity Registry

| Name | Status |
|---|---|
| Sub-project A | Active |
"""

_PASSION_NEWER_MATRIX = """\
---
nexus:
  - new-passion
project_type:
  - passion
type: matrix
---

# Passion Matrix New Passion

## Mission

- **Core Essence:** Practice daily.

## Practices

- Morning meditation.
- Evening journaling.

## Directions of Travel

- Deepen contemplative practice.
- Explore non-dual awareness.

## Operations

No recurring operations yet.

## Open Items

- Find a teacher.
"""

_OPERATION_MATRIX = """\
---
nexus:
  - my-operation
project_type:
  - operation
type: matrix
---

# Operation Matrix My Operation

## Mission

- **Service Statement:** Publish weekly.
- **Core Essence:** Sustained cadence.

## Excluded Outcomes

1. Cadence met but quality degraded.
2. Output produced but not consumed.

## Objectives

- To write one article per week.
- To maintain editorial standards.

## Constraints

### Hard

- No skipping weeks.

## Cadence and Deliverables

| Deliverable | Cadence |
|---|---|
| Article | Weekly Friday 9am |

## Coordinated Corpora

Research notes.

## Coordinated Outputs

Weekly article.

## Active Milestones

- [ ] Publish 4 consecutive weeks

## Aspirational Milestones

- **Milestone B1:** 52 consecutive weeks.

## Performance Log

| Week | Status | Notes |
|---|---|---|
| 2026-W01 | Published | On time |

## Incident Log

No incidents.

## Open Questions / Strategic Topics

- When to expand to podcasts?

## Spawned Activity Registry

| Name | Status |
|---|---|
| Research arm | Planning |

## Iteration History

Iteration 1 complete.

## Decision Log

### 2026-01-01 — Launch decision
- Decided to start weekly cadence.
"""

_INCUBATOR_MATRIX = """\
---
nexus:
  - my-incubator
project_type:
  - incubator
type: matrix
---

# Incubator Matrix My Incubator

## Critical Unknown

Whether the dataset has signal at all.

## Candidate Classifications

- Project (if signal exists)
- Workshop Report (if no signal)

## Exploration Plan

1. Run exploratory analysis.
2. Validate with holdout set.

## Source Intersection

Originated from a conversation about data quality.

## Founding Iteration Entry

Recognized during IIF Mode 3 on 2026-07-01.
"""

_INCUBATOR_MINIMAL_MATRIX = """\
---
nexus:
  - minimal-incubator
project_type:
  - incubator
type: matrix
---

# Incubator Matrix Minimal

## Critical Unknown

Is this viable?

## Candidate Classifications

- Project
- Passion

## Exploration Plan

Think about it.
"""

_NO_PROJECT_TYPE_MATRIX = """\
---
nexus:
  - no-type
type: matrix
---

# Matrix No Type

## Mission

Something.

## Objectives

- Goal 1.
"""


class TestReadPayload(unittest.TestCase):
    """Exercise read_payload(nexus, folder_name, vault=) against a temp vault."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self._tmp.name)
        self.mdir = self.vault / "Matrix"
        self.mdir.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _write_matrix(self, filename: str, content: str):
        (self.mdir / filename).write_text(content, encoding="utf-8")

    # ---- Missing / Commons ----

    def test_missing_nexus(self):
        result = read_payload("nonexistent", vault=self.vault)
        self.assertFalse(result["exists"])
        self.assertEqual(result["state"], "missing")
        self.assertEqual(result["payload"], {})

    def test_commons(self):
        result = read_payload("commons", vault=self.vault)
        self.assertEqual(result["state"], "missing")

    # ---- Project ----

    def test_project_payload(self):
        self._write_matrix("Project Matrix My Project.md", _PROJECT_MATRIX)
        result = read_payload("my-project", vault=self.vault)
        self.assertTrue(result["exists"])
        self.assertEqual(result["state"], "ok")
        self.assertEqual(result["classification"], "project")
        payload = result["payload"]
        self.assertIn("Mission", payload)
        self.assertIn("Resolution Statement", payload["Mission"])
        self.assertIn("Objectives", payload)
        self.assertIn("build the widget", payload["Objectives"])
        # Milestones should have task parsing.
        self.assertIn("Milestones", payload)
        mile = payload["Milestones"]
        self.assertIn("raw", mile)
        self.assertIn("tasks", mile)
        self.assertEqual(len(mile["tasks"]), 3)
        self.assertTrue(mile["tasks"][0]["done"])  # Design complete
        self.assertFalse(mile["tasks"][1]["done"])  # Build complete

    def test_project_missing_sections_omitted(self):
        """Sections not present in the Matrix file are not in the payload."""
        self._write_matrix("Project Matrix My Project.md", _PROJECT_MATRIX)
        result = read_payload("my-project", vault=self.vault)
        # Project payload should NOT have Operation-specific sections.
        self.assertNotIn("Excluded Outcomes", result["payload"])
        self.assertNotIn("Constraints", result["payload"])

    # ---- Passion (legacy) ----

    def test_passion_legacy_payload(self):
        self._write_matrix("Passion Matrix My Passion.md", _PASSION_LEGACY_MATRIX)
        result = read_payload("my-passion", vault=self.vault)
        self.assertEqual(result["state"], "ok")
        self.assertEqual(result["classification"], "passion")
        payload = result["payload"]
        self.assertIn("Mission", payload)
        self.assertIn("Core Essence", payload["Mission"])
        self.assertIn("Objectives", payload)
        self.assertIn("Milestones", payload)
        self.assertIn("Projects", payload)
        self.assertIn("Files", payload)
        self.assertIn("Problem Solving", payload)
        self.assertIn("Spawned Activity Registry", payload)

    # ---- Passion (newer) ----

    def test_passion_newer_payload(self):
        self._write_matrix("Passion Matrix New Passion.md", _PASSION_NEWER_MATRIX)
        result = read_payload("new-passion", vault=self.vault)
        self.assertEqual(result["state"], "ok")
        self.assertEqual(result["classification"], "passion")
        payload = result["payload"]
        self.assertIn("Mission", payload)
        self.assertIn("Practices", payload)
        self.assertIn("Directions of Travel", payload)
        self.assertIn("Operations", payload)
        self.assertIn("Open Items", payload)
        # Newer shape should NOT have legacy sections.
        self.assertNotIn("Milestones", payload)
        self.assertNotIn("Objectives", payload)

    # ---- Operation ----

    def test_operation_payload(self):
        self._write_matrix("Operation Matrix My Operation.md", _OPERATION_MATRIX)
        result = read_payload("my-operation", vault=self.vault)
        self.assertEqual(result["state"], "ok")
        self.assertEqual(result["classification"], "operation")
        payload = result["payload"]
        self.assertIn("Mission", payload)
        self.assertIn("Service Statement", payload["Mission"])
        self.assertIn("Excluded Outcomes", payload)
        self.assertIn("Objectives", payload)
        self.assertIn("Constraints", payload)
        self.assertIn("Cadence and Deliverables", payload)
        self.assertIn("Coordinated Corpora", payload)
        self.assertIn("Coordinated Outputs", payload)
        self.assertIn("Active Milestones", payload)
        self.assertIn("Aspirational Milestones", payload)
        self.assertIn("Performance Log", payload)
        self.assertIn("Incident Log", payload)
        self.assertIn("Open Questions / Strategic Topics", payload)
        self.assertIn("Spawned Activity Registry", payload)
        self.assertIn("Iteration History", payload)
        self.assertIn("Decision Log", payload)

    def test_operation_milestones_have_task_parsing(self):
        self._write_matrix("Operation Matrix My Operation.md", _OPERATION_MATRIX)
        result = read_payload("my-operation", vault=self.vault)
        active = result["payload"]["Active Milestones"]
        self.assertIn("tasks", active)
        self.assertEqual(len(active["tasks"]), 1)
        self.assertFalse(active["tasks"][0]["done"])

    # ---- Incubator ----

    def test_incubator_payload(self):
        self._write_matrix("Incubator Matrix My Incubator.md", _INCUBATOR_MATRIX)
        result = read_payload("my-incubator", vault=self.vault)
        self.assertEqual(result["state"], "ok")
        self.assertEqual(result["classification"], "incubator")
        payload = result["payload"]
        self.assertIn("Critical Unknown", payload)
        self.assertIn("signal", payload["Critical Unknown"])
        self.assertIn("Candidate Classifications", payload)
        self.assertIn("Exploration Plan", payload)
        self.assertIn("Source Intersection", payload)
        self.assertIn("Founding Iteration Entry", payload)

    def test_incubator_minimal_no_optional_sections(self):
        """Incubator with only required sections — optional sections absent."""
        self._write_matrix("Incubator Matrix Minimal.md", _INCUBATOR_MINIMAL_MATRIX)
        result = read_payload("minimal-incubator", vault=self.vault)
        self.assertEqual(result["state"], "ok")
        payload = result["payload"]
        self.assertIn("Critical Unknown", payload)
        self.assertIn("Candidate Classifications", payload)
        self.assertIn("Exploration Plan", payload)
        self.assertNotIn("Source Intersection", payload)
        self.assertNotIn("Founding Iteration Entry", payload)

    # ---- No project_type (compat default → project) ----

    def test_no_project_type_reads_as_project(self):
        self._write_matrix("Matrix No Type.md", _NO_PROJECT_TYPE_MATRIX)
        result = read_payload("no-type", vault=self.vault)
        self.assertEqual(result["state"], "ok")
        self.assertEqual(result["classification"], "project")
        self.assertIn("Mission", result["payload"])
        # Warning about missing project_type.
        self.assertTrue(any("absent" in w for w in result["warnings"]))

    # ---- Ambiguous / Invalid ----

    def test_ambiguous_returns_ambiguous(self):
        self._write_matrix(
            "Project Matrix Clash A.md",
            "---\nnexus:\n  - clash\nproject_type:\n  - project\ntype: matrix\n---\n\n# A\n\n## Mission\n\nA.\n",
        )
        self._write_matrix(
            "Project Matrix Clash B.md",
            "---\nnexus:\n  - clash\nproject_type:\n  - project\ntype: matrix\n---\n\n# B\n\n## Mission\n\nB.\n",
        )
        result = read_payload("clash", vault=self.vault)
        self.assertEqual(result["state"], "ambiguous")
        self.assertEqual(result["payload"], {})

    def test_invalid_multiple_classifications(self):
        self._write_matrix(
            "Project Matrix Bad.md",
            "---\nnexus:\n  - bad\nproject_type:\n  - project\n  - operation\ntype: matrix\n---\n\n# Bad\n\n## Mission\n\nX.\n",
        )
        result = read_payload("bad", vault=self.vault)
        self.assertEqual(result["state"], "invalid")
        self.assertEqual(result["payload"], {})


if __name__ == "__main__":
    unittest.main()
