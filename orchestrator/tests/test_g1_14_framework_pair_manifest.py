"""Adversarial coverage for G1.14 manifest detection and queue receipts."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify-implementation.py"
MODULE_NAME = "ora_verify_implementation_g1_14"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = VERIFY
SPEC.loader.exec_module(VERIFY)


def _entry(
    canonical: str,
    runtime: str | None,
    disposition: str = "paired",
    *,
    severity: str = "load-bearing",
) -> dict:
    prefix = {
        "paired": "pair",
        "missing_runtime": "missing",
        "no_runtime_twin": "no-twin",
    }[disposition]
    pair_id = f"{prefix}:{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"
    return {
        "pair_id": pair_id,
        "canonical_path": canonical,
        "runtime_path": runtime,
        "disposition": disposition,
        "comparison": "normalized_body_exact",
        "finding_severity": severity,
        "last_known_clean": "2026-07-21" if disposition == "paired" else None,
        "rationale": "Focused test classification.",
    }


def _write_manifest(path: Path, entries: list[dict]) -> None:
    counts = {
        "active_frameworks": sum(
            Path(entry["canonical_path"]).name.startswith("Framework — ")
            for entry in entries
        ),
        "missing_runtime": sum(
            entry["disposition"] == "missing_runtime" for entry in entries
        ),
        "no_runtime_twin": sum(
            entry["disposition"] == "no_runtime_twin" for entry in entries
        ),
        "paired": sum(entry["disposition"] == "paired" for entry in entries),
        "total_entries": len(entries),
    }
    document = {
        "schema_version": 1,
        "manifest_id": VERIFY.FRAMEWORK_MANIFEST_ID,
        "source_audit": "test",
        "as_of": "2026-07-22",
        "normalization": "test",
        "expected_counts": counts,
        "entries": entries,
    }
    path.write_text(
        "# Test manifest\n\n"
        f"{VERIFY.FRAMEWORK_MANIFEST_BEGIN}\n"
        "```json\n"
        f"{json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)}\n"
        "```\n"
        f"{VERIFY.FRAMEWORK_MANIFEST_END}\n",
        encoding="utf-8",
    )


class TemporaryManifestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ora-g1-14-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.vault = root / "vault"
        self.ora = root / "ora"
        (self.vault / "Projects" / "Ora").mkdir(parents=True)
        (self.vault / "Projects" / "MSI").mkdir(parents=True)
        (self.ora / "frameworks" / "book").mkdir(parents=True)
        self.manifest = root / "manifest.md"
        self.queue = root / "queue.md"
        self.queue.write_text(
            "---\n"
            "nexus:\n  - ora\n"
            "date modified: 2026-07-21\n"
            "---\n\n"
            "# Queue\n\n"
            "## Missing-feature class\n\n"
            "---\n\n"
            "## Escalate class\n\n"
            "---\n\n"
            "## Deprecation-candidate class\n",
            encoding="utf-8",
        )

    def write_canonical(self, name: str, body: str = "# Shared\n\nBody.\n") -> str:
        path = self.vault / "Projects" / "Ora" / name
        path.write_text(
            "---\nnexus:\n  - ora\ntype: framework\n---\n\n" + body,
            encoding="utf-8",
        )
        return path.relative_to(self.vault).as_posix()

    def write_runtime(self, name: str, body: str = "# Shared\n\nBody.\n") -> str:
        path = self.ora / "frameworks" / "book" / name
        path.write_text(body, encoding="utf-8")
        return path.relative_to(self.ora).as_posix()

    def evaluate(self):
        return VERIFY.evaluate_framework_pair_manifest(
            manifest_path=self.manifest,
            vault_root=self.vault,
            ora_root=self.ora,
        )


class FrameworkPairManifestAdversarialTests(TemporaryManifestCase):
    def test_clean_pair_uses_locked_normalization_and_is_read_only(self):
        canonical = self.write_canonical("Framework — A.md")
        runtime = self.write_runtime("a.md")
        _write_manifest(self.manifest, [_entry(canonical, runtime)])
        before = {
            canonical: (self.vault / canonical).read_bytes(),
            runtime: (self.ora / runtime).read_bytes(),
        }

        evaluation = self.evaluate()

        self.assertEqual(evaluation.findings, ())
        self.assertEqual(evaluation.paired_clean, 1)
        self.assertEqual(before[canonical], (self.vault / canonical).read_bytes())
        self.assertEqual(before[runtime], (self.ora / runtime).read_bytes())

    def test_manifest_omission_cannot_hide_vault_or_runtime_files(self):
        canonical = self.write_canonical("Framework — A.md")
        runtime = self.write_runtime("a.md")
        self.write_canonical("Framework — Omitted.md", "# Omitted\n")
        self.write_runtime("omitted.md", "# Omitted\n")
        _write_manifest(self.manifest, [_entry(canonical, runtime)])

        types = {finding.payload["finding_type"] for finding in self.evaluate().findings}

        self.assertEqual(
            types,
            {"unregistered_canonical_framework", "unregistered_runtime_framework"},
        )

    def test_body_drift_binds_exact_subject_digests(self):
        canonical = self.write_canonical("Framework — A.md", "# Canonical\n")
        runtime = self.write_runtime("a.md", "# Runtime\n")
        _write_manifest(self.manifest, [_entry(canonical, runtime)])

        finding = self.evaluate().findings[0]

        self.assertEqual(finding.payload["finding_type"], "normalized_body_drift")
        self.assertEqual(
            finding.payload["canonical_body_sha256"],
            hashlib.sha256(b"# Canonical").hexdigest(),
        )
        self.assertEqual(
            finding.payload["runtime_body_sha256"],
            hashlib.sha256(b"# Runtime").hexdigest(),
        )

    def test_missing_twin_remains_a_finding(self):
        canonical = self.write_canonical("Framework — A.md")
        _write_manifest(
            self.manifest,
            [_entry(canonical, "frameworks/book/a.md", "missing_runtime")],
        )

        finding = self.evaluate().findings[0]

        self.assertEqual(finding.payload["finding_type"], "missing_runtime_twin")
        self.assertEqual(finding.payload["severity"], "missing-feature")

    def test_out_of_band_twin_does_not_self_authorize(self):
        canonical = self.write_canonical("Framework — A.md")
        runtime = self.write_runtime("a.md")
        _write_manifest(
            self.manifest,
            [_entry(canonical, runtime, "missing_runtime")],
        )

        finding = self.evaluate().findings[0]

        self.assertEqual(
            finding.payload["finding_type"], "unapproved_runtime_twin_present"
        )

    def test_path_escape_is_rejected_before_filesystem_access(self):
        canonical = self.write_canonical("Framework — A.md")
        runtime = self.write_runtime("a.md")
        entry = _entry(canonical, runtime)
        entry["canonical_path"] = "../outside.md"
        _write_manifest(self.manifest, [entry])

        with self.assertRaisesRegex(VERIFY.FrameworkManifestError, "repository-relative"):
            self.evaluate()

    def test_symlinked_manifest_target_is_rejected(self):
        external = Path(self.temp.name) / "external.md"
        external.write_text("# External\n", encoding="utf-8")
        canonical_path = "Projects/Ora/Framework — Linked.md"
        (self.vault / canonical_path).symlink_to(external)
        runtime = self.write_runtime("linked.md", "# External\n")
        _write_manifest(self.manifest, [_entry(canonical_path, runtime)])

        with self.assertRaisesRegex(VERIFY.FrameworkManifestError, "contains a symlink"):
            self.evaluate()

    def test_duplicate_runtime_target_is_rejected(self):
        a = self.write_canonical("Framework — A.md")
        b = self.write_canonical("Framework — B.md")
        runtime = self.write_runtime("a.md")
        _write_manifest(self.manifest, [_entry(a, runtime), _entry(b, runtime)])

        with self.assertRaisesRegex(VERIFY.FrameworkManifestError, "duplicate runtime_path"):
            self.evaluate()

    def test_count_envelope_tampering_is_rejected(self):
        canonical = self.write_canonical("Framework — A.md")
        runtime = self.write_runtime("a.md")
        _write_manifest(self.manifest, [_entry(canonical, runtime)])
        content = self.manifest.read_text(encoding="utf-8")
        self.manifest.write_text(
            content.replace('"total_entries": 1', '"total_entries": 2'),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(VERIFY.FrameworkManifestError, "expected_counts"):
            self.evaluate()

    def test_queue_write_is_authenticated_atomic_and_retry_idempotent(self):
        canonical = self.write_canonical("Framework — A.md")
        _write_manifest(
            self.manifest,
            [_entry(canonical, "frameworks/book/a.md", "missing_runtime")],
        )

        mode_before = self.queue.stat().st_mode & 0o777
        first = VERIFY.enqueue_framework_pair_findings(
            manifest_path=self.manifest,
            vault_root=self.vault,
            ora_root=self.ora,
            queue_path=self.queue,
        )
        first_bytes = self.queue.read_bytes()
        second = VERIFY.enqueue_framework_pair_findings(
            manifest_path=self.manifest,
            vault_root=self.vault,
            ora_root=self.ora,
            queue_path=self.queue,
        )

        self.assertEqual(first, (1, 1))
        self.assertEqual(second, (0, 1))
        self.assertEqual(first_bytes, self.queue.read_bytes())
        self.assertEqual(self.queue.stat().st_mode & 0o777, mode_before)
        receipts = VERIFY.verify_framework_finding_receipts(
            self.queue.read_text(encoding="utf-8")
        )
        self.assertEqual(len(receipts), 1)
        self.assertFalse(self.queue.with_name(self.queue.name + ".lock").exists())

    def test_queue_receipt_tampering_fails_closed(self):
        canonical = self.write_canonical("Framework — A.md")
        _write_manifest(
            self.manifest,
            [_entry(canonical, "frameworks/book/a.md", "missing_runtime")],
        )
        VERIFY.enqueue_framework_pair_findings(
            manifest_path=self.manifest,
            vault_root=self.vault,
            ora_root=self.ora,
            queue_path=self.queue,
        )
        content = self.queue.read_text(encoding="utf-8")
        match = VERIFY.FRAMEWORK_RECEIPT_PATTERN.search(content)
        assert match is not None
        receipt = json.loads(match.group(1))
        receipt["finding"]["severity"] = "stale"
        tampered = content[:match.start(1)] + json.dumps(
            receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ) + content[match.end(1):]

        with self.assertRaisesRegex(VERIFY.FrameworkManifestError, "digest mismatch"):
            VERIFY.verify_framework_finding_receipts(tampered)

    def test_existing_lock_rejects_write_without_queue_change(self):
        canonical = self.write_canonical("Framework — A.md")
        _write_manifest(
            self.manifest,
            [_entry(canonical, "frameworks/book/a.md", "missing_runtime")],
        )
        lock = self.queue.with_name(self.queue.name + ".lock")
        lock.write_text("held", encoding="utf-8")
        before = self.queue.read_bytes()

        with self.assertRaisesRegex(VERIFY.FrameworkManifestError, "lock already exists"):
            VERIFY.enqueue_framework_pair_findings(
                manifest_path=self.manifest,
                vault_root=self.vault,
                ora_root=self.ora,
                queue_path=self.queue,
            )

        self.assertEqual(before, self.queue.read_bytes())

    def test_symlinked_queue_is_rejected_without_touching_target(self):
        canonical = self.write_canonical("Framework — A.md")
        _write_manifest(
            self.manifest,
            [_entry(canonical, "frameworks/book/a.md", "missing_runtime")],
        )
        target = Path(self.temp.name) / "outside-queue.md"
        target.write_text(self.queue.read_text(encoding="utf-8"), encoding="utf-8")
        self.queue.unlink()
        self.queue.symlink_to(target)
        before = target.read_bytes()

        with self.assertRaisesRegex(VERIFY.FrameworkManifestError, "non-symlink"):
            VERIFY.enqueue_framework_pair_findings(
                manifest_path=self.manifest,
                vault_root=self.vault,
                ora_root=self.ora,
                queue_path=self.queue,
            )

        self.assertEqual(target.read_bytes(), before)


class AcceptedG114BaselineTests(unittest.TestCase):
    def test_production_manifest_reproduces_g1_13_exactly(self):
        evaluation = VERIFY.evaluate_framework_pair_manifest()
        counts = evaluation.manifest.expected_counts

        self.assertEqual(
            counts,
            {
                "active_frameworks": 92,
                "missing_runtime": 7,
                "no_runtime_twin": 38,
                "paired": 63,
                "total_entries": 108,
            },
        )
        self.assertEqual(evaluation.paired_clean, 49)
        self.assertEqual(evaluation.paired_drifted, 14)
        self.assertEqual(evaluation.missing_runtime, 7)
        self.assertEqual(evaluation.no_runtime_twin, 38)
        self.assertEqual(len(evaluation.findings), 21)
        self.assertEqual(
            {finding.payload["finding_type"] for finding in evaluation.findings},
            {"missing_runtime_twin", "normalized_body_drift"},
        )
        self.assertEqual(
            sum(
                finding.payload["severity"] == "load-bearing"
                for finding in evaluation.findings
            ),
            10,
        )
        self.assertEqual(
            sum(
                finding.payload["severity"] == "stale"
                for finding in evaluation.findings
            ),
            4,
        )
        self.assertEqual(
            sum(
                finding.payload["severity"] == "missing-feature"
                for finding in evaluation.findings
            ),
            7,
        )
        for finding in evaluation.findings:
            self.assertEqual(
                finding.finding_digest,
                hashlib.sha256(
                    VERIFY._canonical_json(finding.payload).encode("utf-8")
                ).hexdigest(),
            )

    def test_archived_plan_is_historical_and_all_vault_registry_refs_agree(self):
        active = (
            VERIFY.VAULT_ROOT
            / "Projects"
            / "Ora"
            / "Framework — Implementation Plan for Analytical Territories and Modes.md"
        )
        archived = (
            VERIFY.VAULT_ROOT
            / "Archive"
            / "Framework — Implementation Plan for Analytical Territories and Modes.md.archived-2026-07-22"
        )
        self.assertFalse(active.exists())
        self.assertTrue(archived.is_file())
        registries = [
            VERIFY.VAULT_ROOT / "Projects" / "Ora" / "Registry — Framework Registry.md",
            VERIFY.VAULT_ROOT
            / "Projects"
            / "Ora"
            / "Registry — Ora Overview and Document Registry.md",
        ]
        for registry in registries:
            text = registry.read_text(encoding="utf-8")
            self.assertIn(
                "Archive/Framework — Implementation Plan for Analytical Territories and Modes.md.archived-2026-07-22",
                text,
            )
            self.assertNotIn(
                "~/Documents/vault/Framework — Implementation Plan for Analytical Territories and Modes.md",
                text,
            )

    def test_canonical_dcp_records_bounded_g1_14_mechanics(self):
        framework = (
            VERIFY.VAULT_ROOT
            / "Projects"
            / "Ora"
            / "Framework — Documentation-Code Parity.md"
        ).read_text(encoding="utf-8")
        configuration = (
            VERIFY.VAULT_ROOT
            / "Projects"
            / "Ora"
            / "Reference — Documentation-Code Parity Configuration.md"
        ).read_text(encoding="utf-8")
        combined = framework + configuration
        for required in (
            "Reference — Vault Ora Framework Pair Manifest.md",
            "scripts/verify-implementation.py --check framework-pairs",
            "--enqueue-framework-findings",
            "no standalone DCP runtime",
            "no framework-write",
        ):
            self.assertIn(required, combined)

    def test_production_queue_receipts_match_current_findings_exactly(self):
        evaluation = VERIFY.evaluate_framework_pair_manifest()
        content = VERIFY.FRAMEWORK_ESCALATION_QUEUE_FILE.read_text(encoding="utf-8")
        receipts = VERIFY.verify_framework_finding_receipts(content)

        self.assertEqual(len(receipts), 21)
        self.assertEqual(
            {receipt.finding_digest for receipt in receipts},
            {finding.finding_digest for finding in evaluation.findings},
        )
        self.assertEqual(content.count("(G1.14 deterministic detector)"), 21)


if __name__ == "__main__":
    unittest.main()
