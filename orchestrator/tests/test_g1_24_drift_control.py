"""G1.24 drift-control closure invariants."""
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VAULT = Path(
    os.environ.get("ORA_VAULT_PATH")
    or os.environ.get("ORA_VAULT")
    or (Path.home() / "Documents" / "vault")
).resolve()
VAULT_ORA = VAULT / "Projects" / "Ora"
ACCESSIBLE = VAULT_ORA / "Reference — Ora Accessible Overview.md"
ACCESSIBLE_MIRROR = ROOT / "docs" / "accessible-overview.md"
TRACKER = VAULT_ORA / "Working — Ora Setup and Refinement.md"
REGISTRY = VAULT_ORA / "Registry — Ora Overview and Document Registry.md"


def canonical_body_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    if not raw.startswith(b"---\n"):
        raise AssertionError(f"missing YAML frontmatter: {path}")
    end = raw.find(b"\n---\n", 4)
    if end < 0:
        raise AssertionError(f"unterminated YAML frontmatter: {path}")
    body = raw[end + 5 :]
    if body.startswith(b"\n"):
        body = body[1:]
    return body


class TestG124DriftControl(unittest.TestCase):
    def test_accessible_overview_is_an_exact_body_only_mirror(self):
        self.assertEqual(
            canonical_body_bytes(ACCESSIBLE),
            ACCESSIBLE_MIRROR.read_bytes(),
        )

    def test_accessible_overview_preserves_verified_runtime_provenance(self):
        canonical = ACCESSIBLE.read_text(encoding="utf-8")
        mirror = ACCESSIBLE_MIRROR.read_text(encoding="utf-8")
        for token in (
            "Closure currency note: Commons is the universal all-Dialogue view",
            "Commons rename pass: the default project",
            "Code-level rename landed (ora PR #218, commit `062b67a7`",
        ):
            with self.subTest(token=token):
                self.assertIn(token, canonical)
                self.assertIn(token, mirror)

    def test_tracker_and_registry_share_one_structured_current_boundary(self):
        pattern = re.compile(
            r"\*\*Current executable Gate-1 boundary:\*\* (G1\.\d+)"
        )
        tracker = pattern.findall(TRACKER.read_text(encoding="utf-8"))
        registry = pattern.findall(REGISTRY.read_text(encoding="utf-8"))
        self.assertEqual(len(tracker), 1)
        self.assertEqual(len(registry), 1)
        self.assertEqual(tracker, registry)

    def test_closeout_suites_do_not_encode_a_transient_gate_status(self):
        obsolete = (
            "G1.18’s bounded criterion, recovery, schema, attempt-reservation, "
            "and generic-API-isolation corrections are implemented and await "
            "independent re-judgment"
        )
        for name in (
            "test_phase_3_3_user_guidance.py",
            "test_phase_3_5_closeout.py",
        ):
            with self.subTest(name=name):
                source = (ROOT / "orchestrator" / "tests" / name).read_text(
                    encoding="utf-8"
                )
                self.assertNotIn(obsolete, source)


if __name__ == "__main__":
    unittest.main()
