"""Adversarial coverage for G1.14 manifest detection and queue receipts."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
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
        "specified_not_built": "specified",
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
        "specified_not_built": sum(
            entry["disposition"] == "specified_not_built" for entry in entries
        ),
        "total_entries": len(entries),
    }
    document = {
        "schema_version": 1,
        "manifest_id": VERIFY.FRAMEWORK_MANIFEST_ID,
        "source_audit": "test",
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
        (self.ora / "config").mkdir(parents=True)
        self.write_invocability()
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

    def write_invocability(
        self,
        *,
        invocable: list[str] | None = None,
        pickable: list[str] | None = None,
        aliases: dict[str, str] | None = None,
    ) -> None:
        (self.ora / "config" / "framework-invocability.json").write_text(
            json.dumps(
                {
                    "_schema_version": 1,
                    "invocable_frameworks": invocable or [],
                    "pickable_frameworks": pickable or [],
                    "aliases": aliases or {},
                    "internal_only_frameworks": [],
                }
            ),
            encoding="utf-8",
        )

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

    def test_specified_not_built_requires_banner_absence_and_no_registration(self):
        body = f"# A\n\n{VERIFY.SPECIFIED_NOT_BUILT_BANNER}\n"
        canonical = self.write_canonical("Framework — A.md", body)
        _write_manifest(
            self.manifest,
            [_entry(canonical, "frameworks/book/a.md", "specified_not_built")],
        )

        evaluation = self.evaluate()

        self.assertEqual(evaluation.findings, ())
        self.assertEqual(evaluation.specified_not_built, 1)

    def test_specified_not_built_missing_exact_banner_fails(self):
        canonical = self.write_canonical("Framework — A.md")
        _write_manifest(
            self.manifest,
            [_entry(canonical, "frameworks/book/a.md", "specified_not_built")],
        )

        finding_types = {
            finding.payload["finding_type"] for finding in self.evaluate().findings
        }

        self.assertIn("specified_not_built_banner_missing", finding_types)

    def test_hidden_or_example_banner_does_not_satisfy_lifecycle_state(self):
        hidden_forms = {
            "backtick fence": (
                "# A\n\n```markdown\n"
                f"{VERIFY.SPECIFIED_NOT_BUILT_BANNER}\n"
                "```\n"
            ),
            "tilde fence": (
                "# A\n\n~~~markdown\n"
                f"{VERIFY.SPECIFIED_NOT_BUILT_BANNER}\n"
                "~~~\n"
            ),
            "multiline HTML comment": (
                "# A\n\n<!--\n"
                f"{VERIFY.SPECIFIED_NOT_BUILT_BANNER}\n"
                "-->\n"
            ),
        }

        for label, body in hidden_forms.items():
            with self.subTest(label=label):
                canonical = self.write_canonical("Framework — A.md", body)
                _write_manifest(
                    self.manifest,
                    [
                        _entry(
                            canonical,
                            "frameworks/book/a.md",
                            "specified_not_built",
                        )
                    ],
                )

                finding_types = {
                    finding.payload["finding_type"]
                    for finding in self.evaluate().findings
                }

                self.assertIn(
                    "specified_not_built_banner_missing", finding_types
                )

    def test_hidden_h2_does_not_end_preamble_before_visible_banner(self):
        hidden_h2_forms = {
            "backtick fence": "```markdown\n## Example\n```",
            "tilde fence": "~~~markdown\n## Example\n~~~",
            "multiline HTML comment": "<!--\n## Example\n-->",
        }

        for label, hidden_h2 in hidden_h2_forms.items():
            with self.subTest(label=label):
                body = (
                    f"# A\n\n{hidden_h2}\n\n"
                    f"{VERIFY.SPECIFIED_NOT_BUILT_BANNER}\n\n"
                    "## Real section\n"
                )
                canonical = self.write_canonical("Framework — A.md", body)
                _write_manifest(
                    self.manifest,
                    [
                        _entry(
                            canonical,
                            "frameworks/book/a.md",
                            "specified_not_built",
                        )
                    ],
                )

                self.assertEqual(self.evaluate().findings, ())

    def test_specified_not_built_runtime_or_invocability_exposure_fails(self):
        body = f"# A\n\n{VERIFY.SPECIFIED_NOT_BUILT_BANNER}\n"
        canonical = self.write_canonical("Framework — A.md", body)
        runtime = self.write_runtime("a.md", body)
        self.write_invocability(
            invocable=["a.md"],
            pickable=["a"],
            aliases={"public-a": "a.md"},
        )
        _write_manifest(
            self.manifest,
            [_entry(canonical, runtime, "specified_not_built")],
        )

        finding_types = {
            finding.payload["finding_type"] for finding in self.evaluate().findings
        }

        self.assertEqual(
            finding_types,
            {
                "specified_not_built_runtime_present",
                "specified_not_built_registered",
            },
        )

    def test_paired_entry_cannot_carry_either_approved_banner(self):
        body = f"# A\n\n{VERIFY.SPECIFIED_NOT_BUILT_BANNER}\n"
        canonical = self.write_canonical("Framework — A.md", body)
        runtime = self.write_runtime("a.md", body)
        _write_manifest(self.manifest, [_entry(canonical, runtime, "paired")])

        finding_types = {
            finding.payload["finding_type"] for finding in self.evaluate().findings
        }

        self.assertEqual(
            finding_types, {"paired_carries_specified_not_built_banner"}
        )

    def test_later_explanatory_banner_quote_is_not_lifecycle_state(self):
        body = (
            "# A\n\nActive framework.\n\n## Lifecycle examples\n\n"
            f"{VERIFY.SPECIFIED_NOT_BUILT_BANNER}\n"
        )
        canonical = self.write_canonical("Framework — A.md", body)
        runtime = self.write_runtime("a.md", body)
        _write_manifest(self.manifest, [_entry(canonical, runtime, "paired")])

        self.assertEqual(self.evaluate().findings, ())

    def test_legacy_manifest_count_envelope_remains_accepted(self):
        canonical = self.write_canonical("Framework — A.md")
        runtime = self.write_runtime("a.md")
        _write_manifest(self.manifest, [_entry(canonical, runtime)])
        content = self.manifest.read_text(encoding="utf-8")
        self.manifest.write_text(
            re.sub(r'\n\s*"specified_not_built": 0,', "", content),
            encoding="utf-8",
        )

        evaluation = self.evaluate()

        self.assertEqual(evaluation.findings, ())
        self.assertNotIn("specified_not_built", evaluation.manifest.expected_counts)

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

    def test_cosmetic_manifest_edit_does_not_requeue_an_unchanged_finding(self):
        """A manifest edit that changes no entry must append nothing.

        `manifest_sha256` digests the whole manifest document, so before the
        identity split any edit — a typo in a rationale — minted a fresh
        identity for every open finding and the next enqueue duplicated the
        entire queue.
        """
        canonical = self.write_canonical("Framework — A.md")
        entry = _entry(canonical, "frameworks/book/a.md", "missing_runtime")
        _write_manifest(self.manifest, [entry])
        first = VERIFY.enqueue_framework_pair_findings(
            manifest_path=self.manifest,
            vault_root=self.vault,
            ora_root=self.ora,
            queue_path=self.queue,
        )
        before = self.queue.read_bytes()
        digest_before = VERIFY.load_framework_pair_manifest(self.manifest).manifest_sha256

        cosmetic = dict(entry, rationale="Reworded rationale; no entry changed.")
        _write_manifest(self.manifest, [cosmetic])
        digest_after = VERIFY.load_framework_pair_manifest(self.manifest).manifest_sha256
        second = VERIFY.enqueue_framework_pair_findings(
            manifest_path=self.manifest,
            vault_root=self.vault,
            ora_root=self.ora,
            queue_path=self.queue,
        )

        self.assertNotEqual(digest_before, digest_after)
        self.assertEqual(first, (1, 1))
        self.assertEqual(second, (0, 1))
        self.assertEqual(before, self.queue.read_bytes())

    def test_identity_ignores_evidence_but_digest_still_seals_it(self):
        """Body digests are evidence, not identity — and stay under the seal."""
        canonical = self.write_canonical("Framework — A.md")
        _write_manifest(
            self.manifest,
            [_entry(canonical, "frameworks/book/a.md", "missing_runtime")],
        )
        finding = self.evaluate().findings[0]

        moved = dict(
            finding.payload,
            manifest_sha256="0" * 64,
            canonical_body_sha256="1" * 64,
        )
        self.assertEqual(
            VERIFY._framework_finding_identity(finding.payload),
            VERIFY._framework_finding_identity(moved),
        )
        # The tamper seal must still cover every evidence field it reports.
        self.assertNotEqual(
            VERIFY._sha256_text(VERIFY._canonical_json(finding.payload)),
            VERIFY._sha256_text(VERIFY._canonical_json(moved)),
        )
        # A genuinely different problem on the same pair keeps its own identity.
        other = dict(finding.payload, finding_type="normalized_body_drift")
        self.assertNotEqual(
            VERIFY._framework_finding_identity(finding.payload),
            VERIFY._framework_finding_identity(other),
        )

    def test_legacy_receipt_authenticates_without_migration(self):
        """Receipts written before the identity split must still verify."""
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
        receipts = VERIFY.verify_framework_finding_receipts(
            self.queue.read_text(encoding="utf-8")
        )
        self.assertEqual(len(receipts), 1)
        payload = receipts[0].payload
        # The seal is still the digest over the full payload, evidence included.
        self.assertEqual(
            receipts[0].finding_digest,
            VERIFY._sha256_text(VERIFY._canonical_json(payload)),
        )
        self.assertIn("manifest_sha256", payload)

    def test_gitignored_runtime_directory_raises_no_finding(self):
        """frameworks/personal/ exists only in a working tree; ignore it."""
        canonical = self.write_canonical("Framework — A.md")
        _write_manifest(
            self.manifest,
            [_entry(canonical, "frameworks/book/a.md", "paired")],
        )
        self.write_runtime("a.md")
        personal = self.ora / "frameworks" / "personal"
        personal.mkdir(parents=True)
        (personal / "README.md").write_text("Personal frameworks.\n", encoding="utf-8")

        findings = self.evaluate().findings
        self.assertEqual(
            [], [f for f in findings if f.payload["finding_type"] == "unregistered_runtime_framework"]
        )

    def test_a_closed_finding_can_be_detected_again(self):
        """Closing a receipt must not blind the detector to a recurrence.

        Receipts below the "## Closed entries" heading are history. They stay
        authenticated, but they no longer suppress a fresh finding — otherwise
        dispositioning an entry would permanently hide that drift.
        """
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
        text = self.queue.read_text(encoding="utf-8")
        self.assertEqual(1, text.count("dcp-framework-finding-receipt"))

        # Re-running while the finding is open appends nothing.
        self.assertEqual(
            (0, 1),
            VERIFY.enqueue_framework_pair_findings(
                manifest_path=self.manifest,
                vault_root=self.vault,
                ora_root=self.ora,
                queue_path=self.queue,
            ),
        )

        # Move the entry into the historical region, as closing it does.
        start = text.index("### E-")
        entry = text[start:]
        closed = text[:start] + "\n## Closed entries\n\n" + entry
        self.queue.write_text(closed, encoding="utf-8")

        # Still authenticates — closing is not tampering.
        self.assertEqual(
            1,
            len(
                VERIFY.verify_framework_finding_receipts(
                    self.queue.read_text(encoding="utf-8")
                )
            ),
        )
        # And the still-present drift is queued again.
        appended, current = VERIFY.enqueue_framework_pair_findings(
            manifest_path=self.manifest,
            vault_root=self.vault,
            ora_root=self.ora,
            queue_path=self.queue,
        )
        self.assertEqual((1, 1), (appended, current))
        self.assertEqual(
            2, self.queue.read_text(encoding="utf-8").count("dcp-framework-finding-receipt")
        )

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

    def test_abandoned_queue_lock_is_reclaimed_loudly(self):
        """A crashed run must not wedge every later run forever.

        Held by a human at a terminal, a refused lock is a visible error. On
        the commit-trigger path it would block every subsequent enqueue
        silently and permanently — worse than the race the lock guards.
        """
        import os
        import time as _time

        canonical = self.write_canonical("Framework — A.md")
        _write_manifest(
            self.manifest,
            [_entry(canonical, "frameworks/book/a.md", "missing_runtime")],
        )
        lock = self.queue.with_name(self.queue.name + ".lock")
        lock.write_text("", encoding="utf-8")

        # A fresh lock is still honoured — a concurrent run is not abandoned.
        with self.assertRaises(VERIFY.FrameworkManifestError):
            VERIFY.enqueue_framework_pair_findings(
                manifest_path=self.manifest,
                vault_root=self.vault,
                ora_root=self.ora,
                queue_path=self.queue,
            )

        # Age it past the threshold; now it is abandoned and reclaimable.
        old = _time.time() - (VERIFY.FRAMEWORK_QUEUE_LOCK_STALE_SECONDS + 60)
        os.utime(lock, (old, old))
        appended, current = VERIFY.enqueue_framework_pair_findings(
            manifest_path=self.manifest,
            vault_root=self.vault,
            ora_root=self.ora,
            queue_path=self.queue,
        )
        self.assertEqual((1, 1), (appended, current))
        self.assertFalse(lock.exists(), "lock not released after reclaim")

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
    def test_production_manifest_matches_approved_activation_state(self):
        evaluation = VERIFY.evaluate_framework_pair_manifest()
        counts = evaluation.manifest.expected_counts

        self.assertEqual(
            counts,
            {
                "active_frameworks": 92,
                "missing_runtime": 0,
                "no_runtime_twin": 38,
                "paired": 63,
                "specified_not_built": 7,
                "total_entries": 108,
            },
        )
        # Dispositions declared by the manifest itself — invariant under
        # remediation, because fixing a drifted pair does not change which
        # entries the manifest says have no runtime twin.
        self.assertEqual(evaluation.missing_runtime, 0)
        self.assertEqual(evaluation.no_runtime_twin, 38)
        self.assertEqual(evaluation.specified_not_built, 7)

        # paired_clean/paired_drifted are MEASURED against the live trees, so
        # the 49/14 recorded at the 2026-07-22 acceptance is a snapshot of that
        # day, not an invariant: remediating a drifted pair moves one from
        # drifted to clean, which is the point of the audit. Video/D35 is the
        # one protected paired entry whose declared runtime path is absent; it
        # is neither clean nor body-drifted. Assert the conservation law with
        # that exact state included, without misclassifying it as clean.
        paired_runtime_missing = sum(
            finding.payload["finding_type"] == "paired_runtime_missing"
            and finding.payload["disposition"] == "paired"
            for finding in evaluation.findings
        )
        self.assertEqual(paired_runtime_missing, 1)
        self.assertEqual(
            evaluation.paired_clean
            + evaluation.paired_drifted
            + paired_runtime_missing,
            counts["paired"],
        )
        self.assertEqual(
            evaluation.paired_clean
            + evaluation.paired_drifted
            + paired_runtime_missing
            + evaluation.missing_runtime
            + evaluation.no_runtime_twin
            + evaluation.specified_not_built,
            counts["total_entries"],
        )

        # Every finding is one of the detector's declared kinds. A subset check
        # rather than set equality: pinning the exact two kinds seen in 2026-07
        # would force the detector to hide a genuine finding of a newer kind.
        self.assertLessEqual(
            {finding.payload["finding_type"] for finding in evaluation.findings},
            {
                "missing_runtime_twin",
                "normalized_body_drift",
                "paired_runtime_missing",
                "unregistered_runtime_framework",
                "unregistered_canonical_framework",
            },
        )

        # The severity RULE, of which the old 10/4/7 histogram was one day's
        # arithmetic: a missing runtime twin is always a missing feature, and
        # every such entry yields exactly one finding.
        self.assertEqual(
            sum(
                finding.payload["finding_type"] == "missing_runtime_twin"
                for finding in evaluation.findings
            ),
            evaluation.missing_runtime,
        )
        for finding in evaluation.findings:
            if finding.payload["finding_type"] == "missing_runtime_twin":
                self.assertEqual(finding.payload["severity"], "missing-feature")

        # These two protected findings stay exactly with their external
        # owners. The lifecycle transition for the seven candidates must not
        # absorb or rename either identity.
        findings_by_identity = {
            (finding.payload["finding_type"], finding.payload["pair_id"]): finding
            for finding in evaluation.findings
        }
        system_protection = findings_by_identity[
            (
                "unregistered_canonical_framework",
                "unregistered-canonical:0e9383eef0b192d1",
            )
        ]
        self.assertEqual(
            system_protection.payload["canonical_path"],
            "Projects/Ora/Framework — System Protection and Outbound Security.md",
        )
        video = findings_by_identity[
            ("paired_runtime_missing", "pair:c82da19f72e570a5")
        ]
        self.assertEqual(
            video.payload["runtime_path"],
            "frameworks/book/video-editing-suggestions.md",
        )

        # No finding invented and none swallowed.
        self.assertEqual(
            sum(
                finding.payload["finding_type"] == "normalized_body_drift"
                for finding in evaluation.findings
            ),
            evaluation.paired_drifted,
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

    def test_accepted_g1_14_tranche_survives_intact_in_the_queue(self):
        """The 2026-07-22 acceptance is a frozen record; guard it as one.

        This previously asserted that the queue's receipts equalled the
        detector's CURRENT findings. That could only hold on the day of the
        audit: remediation since then took drifted pairs from 14 to 3, so the
        live finding set legitimately no longer matches the receipts written
        then. Tying a frozen record to a live measurement made a successful
        remediation look like a regression.

        What is still guaranteed, and is what the receipts exist for: the
        accepted tranche is intact, the queue only ever grows, and no receipt
        is duplicated or silently rewritten.
        """
        content = VERIFY.FRAMEWORK_ESCALATION_QUEUE_FILE.read_text(encoding="utf-8")
        receipts = VERIFY.verify_framework_finding_receipts(content)

        # Freeze the exact accepted 2026-07-22 tranche. Later runs and the two
        # externally owned findings may add authenticated receipts, so a count
        # of every detector-tagged line is not the historical contract.
        accepted_manifest = (
            "17775559f49b5459f2a9cd1f196de90051cef8cc1150699aa12fc99582d78a46"
        )
        expected_accepted_digests = {
            "94488f13b08f9100595f9aa2aa81b499fcf734c92e6639f0271c7628188233dd",
            "73a8d6825ef055a4f6120afb5712c1d950646547ef71fb0960e8aee9cf026be6",
            "a88d3a7cdacf182ea077c603e916c789c01013ad0675850e036c7940520fdcc4",
            "22fd5dbfdc31788bdf5d6e0f4f075a0962402dbf2f39b04b2383d5588a13876f",
            "86055318febe7c62c1a21f0b92d2feb6dd4b39e429b792c837a15f82302c3e5f",
            "426d24034c4224f83d72f687d8dc746d719cb4bba34fdf9101f31501a4e89076",
            "3dde581e131993ea369cba8c0bfc3d015d29a74f57dd07e55d91971175d0e408",
            "8bdfc4f6e806ee9ee68a8c00d99919fb26594224d097afb2f8d3670969a3d8b9",
            "7f0c88f4887362d1a492d21b7b72ee687c1fccbb27534baf2ac837a9664da4f5",
            "f0b3e259d2c09f2fd2c4f3376cacee66c103a9ea3b2d2215b4d15100ce5e67b3",
            "ccba42e23d4ed9062f3adabf87ea354f29d90731d9457f1036f193a1319bd1a9",
            "f25061cd9f6de66419ee0525bde8a0fbdccc3ef18451ab16b6ea833a93610e6a",
            "01ca7632eed1b7a30a8d715f442dfe9586e9733b07e585814d6643c4d3fcad16",
            "284611894cdf72bbd8c0a707eaccd18b72bfd89c84f1c449b6dda6a6b96ed52c",
            "d2191491c75aa8d1c098fed7c723f0a9a52beac9ff1cecd7c189ba98e6c0726b",
            "335fce40a1acd104625d59f199c104e637bdbeb881e470f0976931159e4e00a1",
            "8d9ef5f321c84c5469d619c4f500024e29b16f29e9259295e7a6df96a8c05f3c",
            "996002cf07a3a11c0689e6f7b20352e3b9dd25cd0e43d664f3e8d259d796d080",
            "b75c68f48c7b7cc93b7a7207b58a7231a4411b3431bca2b8ede7eed791ab1159",
            "2d27c64989cd9faaad9cfb0fbc496a43143f0cd57345941ef5756775ddb9315c",
            "733127eab5556268e45d0956b74f60532344b72504c0dafb11c77403aa6f1fef",
        }
        accepted_receipts = {
            receipt.finding_digest
            for receipt in receipts
            if receipt.payload["manifest_sha256"] == accepted_manifest
            and receipt.payload["finding_type"]
            in {"missing_runtime_twin", "normalized_body_drift"}
        }
        self.assertEqual(accepted_receipts, expected_accepted_digests)

        # The queue is append-only. Later escalations (E-093, the deferred
        # unregistered-canonical finding) add receipts; none may disappear.
        self.assertGreaterEqual(len(receipts), 21)

        digests = [receipt.finding_digest for receipt in receipts]
        self.assertEqual(
            len(digests), len(set(digests)),
            "a finding digest appears twice — a receipt was duplicated",
        )
        for receipt in receipts:
            self.assertTrue(
                receipt.finding_digest and len(receipt.finding_digest) >= 32,
                "receipt carries no usable finding digest",
            )


if __name__ == "__main__":
    unittest.main()
