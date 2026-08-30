"""Focused behavioral coverage for the five-repository documentation gate."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify-implementation.py"
MODULE_NAME = "ora_verify_documentation_integrity"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = VERIFY
SPEC.loader.exec_module(VERIFY)


def git(root: Path, *arguments: str) -> str:
    run = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        check=True,
    )
    return run.stdout.strip()


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class DocumentationIntegrityFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ora-documentation-integrity-")
        self.addCleanup(self.temp.cleanup)
        temp_root = Path(self.temp.name)
        self.roots = {
            name: temp_root / name for name in VERIFY.DOCUMENTATION_REPOSITORIES
        }
        for name, root in self.roots.items():
            root.mkdir()
            git(root, "init", "-q")
            git(root, "config", "user.email", "dcp-test@example.invalid")
            git(root, "config", "user.name", "DCP Test")
            git(
                root,
                "remote",
                "add",
                "origin",
                f"https://example.invalid/{name}.git",
            )
            write(root / "README.md", f"# {name}\n")

        write(
            self.roots["vault"] / "Projects/Ora/Reference — Feature.md",
            "---\nnexus:\n  - ora\ntype: reference\n---\n\n"
            "# Feature\n\n## Behavior\n\nInitial behavior.\n",
        )
        write(
            self.roots["ora"] / "orchestrator/feature.py",
            "def feature():\n    return 'initial'\n",
        )
        write(
            self.roots["ora"] / "docs/feature.md",
            "# Feature\n\n## Behavior\n\nInitial behavior.\n",
        )
        write(
            self.roots["ora"] / "config/framework-invocability.json",
            json.dumps(
                {
                    "_schema_version": 1,
                    "invocable_frameworks": ["a.md"],
                    "pickable_frameworks": [],
                    "aliases": {},
                    "internal_only_frameworks": [],
                }
            ),
        )
        write(self.roots["msi"] / "generated/base.md", "# Generated base\n")
        self.framework_a = "Projects/Ora/Framework — A.md"
        self.runtime_a = "frameworks/book/a.md"
        write(
            self.roots["vault"] / self.framework_a,
            "---\nnexus:\n  - ora\ntype: framework\n---\n\n# A\n\nBody.\n",
        )
        write(self.roots["ora"] / self.runtime_a, "# A\n\nBody.\n")
        self.manifest_entries = [
            self._manifest_entry(
                "pair:a", self.framework_a, self.runtime_a, "paired"
            )
        ]
        self.accepted_findings: list[dict] = []
        self._write_manifest()
        self._write_configuration()

        for root in self.roots.values():
            git(root, "add", ".")
            git(root, "commit", "-qm", "Initial fixture")
        self.bases = {
            name: git(root, "rev-parse", "HEAD")
            for name, root in self.roots.items()
        }

    def _manifest_entry(
        self,
        pair_id: str,
        canonical_path: str,
        runtime_path: str | None,
        disposition: str,
    ) -> dict:
        return {
            "pair_id": pair_id,
            "canonical_path": canonical_path,
            "runtime_path": runtime_path,
            "disposition": disposition,
            "comparison": "normalized_body_exact",
            "finding_severity": (
                "missing-feature" if disposition == "missing_runtime" else "load-bearing"
            ),
            "last_known_clean": "2026-08-28" if disposition == "paired" else None,
            "rationale": "Focused documentation-integrity fixture.",
        }

    def _write_manifest(self) -> None:
        counts = {
            "active_frameworks": len(self.manifest_entries),
            "missing_runtime": sum(
                entry["disposition"] == "missing_runtime"
                for entry in self.manifest_entries
            ),
            "no_runtime_twin": sum(
                entry["disposition"] == "no_runtime_twin"
                for entry in self.manifest_entries
            ),
            "paired": sum(
                entry["disposition"] == "paired" for entry in self.manifest_entries
            ),
            "specified_not_built": sum(
                entry["disposition"] == "specified_not_built"
                for entry in self.manifest_entries
            ),
            "total_entries": len(self.manifest_entries),
        }
        document = {
            "schema_version": 1,
            "manifest_id": VERIFY.FRAMEWORK_MANIFEST_ID,
            "source_audit": "test",
            "normalization": "test",
            "expected_counts": counts,
            "entries": self.manifest_entries,
        }
        write(
            self.roots["vault"]
            / "Projects/Ora/Reference — Vault Ora Framework Pair Manifest.md",
            "# Framework pairs\n\n"
            f"{VERIFY.FRAMEWORK_MANIFEST_BEGIN}\n```json\n"
            f"{json.dumps(document, indent=2, sort_keys=True)}\n```\n"
            f"{VERIFY.FRAMEWORK_MANIFEST_END}\n",
        )

    def _ownership_document(self) -> dict:
        discovery = {
            "user-facing": [
                {
                    "source_id": "ora.runtime-functions",
                    "type": "regex_registry",
                    "repository": "ora",
                    "path": "orchestrator/feature.py",
                    "pattern": r"^def\s+(?P<item>[a-z_][a-z0-9_]*)\s*\(",
                    "associations": [
                        {"pattern": "feature", "surface_id": "ora.feature"}
                    ],
                }
            ],
            "operator-facing": [
                {
                    "source_id": "vault.framework-manifest",
                    "type": "tracked_glob",
                    "repository": "vault",
                    "glob": "Projects/Ora/Reference — Vault Ora Framework Pair Manifest.md",
                    "associations": [
                        {
                            "pattern": "Projects/Ora/Reference — Vault Ora Framework Pair Manifest.md",
                            "surface_id": "ora.framework-library",
                        }
                    ],
                }
            ],
            "internal": [
                {
                    "source_id": "ora.framework-catalog",
                    "type": "json_catalog",
                    "repository": "ora",
                    "path": "config/framework-invocability.json",
                    "pointer": "/invocable_frameworks",
                    "item_field": None,
                    "associations": [
                        {"pattern": "a.md", "surface_id": "ora.internal-catalog"}
                    ],
                }
            ],
            "generated": [
                {
                    "source_id": "msi.generated-files",
                    "type": "tracked_glob",
                    "repository": "msi",
                    "glob": "generated/*.md",
                    "associations": [
                        {
                            "pattern": "generated/base.md",
                            "surface_id": "site.generated",
                        }
                    ],
                }
            ],
        }
        surfaces = [
            {
                "surface_id": "dcp.configuration",
                "class": "operator-facing",
                "owners": [
                    {
                        "repository": "vault",
                        "pattern": (
                            "Projects/Ora/Reference — Documentation-Code Parity "
                            "Configuration.md"
                        ),
                    }
                ],
                "canonical": {
                    "path": (
                        "Projects/Ora/Reference — Documentation-Code Parity "
                        "Configuration.md"
                    ),
                    "section": None,
                },
                "propagation": {"type": "none"},
                "consumers": [],
                "references": [],
            },
            {
                "surface_id": "ora.feature",
                "class": "user-facing",
                "owners": [
                    {"repository": "ora", "pattern": "orchestrator/**"}
                ],
                "canonical": {
                    "path": "Projects/Ora/Reference — Feature.md",
                    "section": "Behavior",
                },
                "propagation": {
                    "type": "ora_body_only",
                    "repository": "ora",
                    "path": "docs/feature.md",
                },
                "consumers": [],
                "references": [
                    {
                        "type": "symbol",
                        "repository": "ora",
                        "path": "orchestrator/feature.py",
                        "symbol": "feature",
                    }
                ],
            },
            {
                "surface_id": "ora.framework-library",
                "class": "operator-facing",
                "owners": [
                    {"repository": "ora", "pattern": "frameworks/**"}
                ],
                "canonical": {
                    "path": "Projects/Ora/Reference — Vault Ora Framework Pair Manifest.md",
                    "section": None,
                },
                "propagation": {
                    "type": "framework_pair",
                    "pair_id": "missing:b",
                },
                "consumers": [],
                "references": [],
            },
            {
                "surface_id": "ora.internal-catalog",
                "class": "internal",
                "owners": [
                    {"repository": "ora", "pattern": "config/**"}
                ],
                "canonical": {
                    "path": "Projects/Ora/Reference — Feature.md",
                    "section": "Behavior",
                },
                "propagation": {"type": "none"},
                "consumers": [],
                "references": [],
            },
            {
                "surface_id": "site.generated",
                "class": "generated",
                "owners": [
                    {"repository": "msi", "pattern": "generated/**"}
                ],
                "canonical": {
                    "path": "Projects/Ora/Reference — Feature.md",
                    "section": "Behavior",
                },
                "propagation": {"type": "none"},
                "consumers": [],
                "references": [],
            },
        ]
        return {
            "schema_version": 1,
            "registry_id": VERIFY.DOCUMENTATION_OWNERSHIP_ID,
            "repositories": {
                name: {
                    "identity": {
                        "type": "git_remote",
                        "remote": "origin",
                        "value": f"https://example.invalid/{name}.git",
                    }
                }
                for name in VERIFY.DOCUMENTATION_REPOSITORIES
            },
            "discovery": discovery,
            "surfaces": surfaces,
        }

    def _write_configuration(
        self,
        *,
        include_accepted: bool = True,
        ownership: dict | None = None,
    ) -> None:
        ownership = ownership or self._ownership_document()
        baseline = {
            "schema_version": 1,
            "baseline_id": VERIFY.DOCUMENTATION_ACCEPTED_FINDINGS_ID,
            "findings": self.accepted_findings,
        }
        accepted_block = ""
        if include_accepted:
            accepted_block = (
                f"\n{VERIFY.DOCUMENTATION_ACCEPTED_FINDINGS_BEGIN}\n```json\n"
                f"{json.dumps(baseline, indent=2, sort_keys=True)}\n```\n"
                f"{VERIFY.DOCUMENTATION_ACCEPTED_FINDINGS_END}\n"
            )
        write(
            self.roots["vault"]
            / "Projects/Ora/Reference — Documentation-Code Parity Configuration.md",
            "# Documentation-Code Parity Configuration\n\n"
            f"{VERIFY.DOCUMENTATION_OWNERSHIP_BEGIN}\n```json\n"
            f"{json.dumps(ownership, indent=2, sort_keys=True)}\n```\n"
            f"{VERIFY.DOCUMENTATION_OWNERSHIP_END}\n"
            f"{accepted_block}",
        )

    def _write_configuration_without_ownership(self) -> None:
        baseline = {
            "schema_version": 1,
            "baseline_id": VERIFY.DOCUMENTATION_ACCEPTED_FINDINGS_ID,
            "findings": self.accepted_findings,
        }
        write(
            self.roots["vault"]
            / "Projects/Ora/Reference — Documentation-Code Parity Configuration.md",
            "# Documentation-Code Parity Configuration\n\n"
            f"{VERIFY.DOCUMENTATION_ACCEPTED_FINDINGS_BEGIN}\n```json\n"
            f"{json.dumps(baseline, indent=2, sort_keys=True)}\n```\n"
            f"{VERIFY.DOCUMENTATION_ACCEPTED_FINDINGS_END}\n",
        )

    def commit(self, repository: str, message: str) -> str:
        root = self.roots[repository]
        git(root, "add", "-A")
        git(root, "commit", "-qm", message)
        return git(root, "rev-parse", "HEAD")

    def check(self, *, verbose: bool = False, roots=None, bases=None):
        return VERIFY.check_documentation_integrity(
            verbose=verbose,
            roots=roots if roots is not None else self.roots,
            base_commits=bases if bases is not None else self.bases,
        )

    def update_feature_canonical(self, text: str, *, mirror: bool) -> None:
        body = f"# Feature\n\n## Behavior\n\n{text}\n"
        write(
            self.roots["vault"] / "Projects/Ora/Reference — Feature.md",
            "---\nnexus:\n  - ora\ntype: reference\n---\n\n" + body,
        )
        if mirror:
            write(self.roots["ora"] / "docs/feature.md", body)

    def install_accepted_missing_finding(self, *, pin_after: bool = True) -> None:
        canonical = "Projects/Ora/Framework — B.md"
        runtime = "frameworks/book/b.md"
        write(
            self.roots["vault"] / canonical,
            "---\nnexus:\n  - ora\ntype: framework\n---\n\n# B\n\nBody.\n",
        )
        self.manifest_entries.append(
            self._manifest_entry("missing:b", canonical, runtime, "missing_runtime")
        )
        self._write_manifest()
        self.accepted_findings = [
            {
                "finding_type": "missing_runtime_twin",
                "pair_id": "missing:b",
                "canonical_path": canonical,
                "runtime_path": runtime,
                "disposition": "missing_runtime",
                "severity": "missing-feature",
                "owner": "G1.99",
                "repository_commits": dict(self.bases),
            }
        ]
        self._write_configuration()
        accepted_commit = self.commit("vault", "Record exact accepted finding")
        if pin_after:
            self.bases["vault"] = accepted_commit


class DocumentationIntegrityBehaviorTests(DocumentationIntegrityFixture):
    def test_unmapped_markdown_classifier_allows_only_exact_root_prose(self):
        for repository in VERIFY.DOCUMENTATION_REPOSITORIES:
            self.assertFalse(
                VERIFY._is_code_bearing_change(repository, "README.md")
            )
            for instruction_file in ("AGENTS.md", "CLAUDE.md"):
                with self.subTest(
                    repository=repository, instruction_file=instruction_file
                ):
                    self.assertTrue(
                        VERIFY._is_code_bearing_change(
                            repository, instruction_file
                        )
                    )
        machine_consumed = (
            ("ora", "docs/technical-documentation.md"),
            ("ora", "help/accessible-overview.md"),
            ("ora", "help/user-guide.md"),
            ("app", "src/content/reference/runtime.md"),
            ("org", "src/content/docs/runtime.md"),
            ("msi", "src/content/news/runtime.md"),
            (
                "vault",
                "Projects/Ora/Reference — Documentation-Code Parity Configuration.md",
            ),
            (
                "vault",
                "Projects/Ora/Reference — Vault Ora Framework Pair Manifest.md",
            ),
            ("vault", "Modes/runtime-mode.md"),
            ("org", "docs/operator-guide.md"),
        )
        for repository, path in machine_consumed:
            with self.subTest(repository=repository, path=path):
                self.assertTrue(
                    VERIFY._is_code_bearing_change(repository, path)
                )

    def test_unmapped_change_fails(self):
        write(self.roots["ora"] / "newarea/tool.py", "VALUE = 1\n")
        self.commit("ora", "Add new top-level code area")

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(any("unmapped code change" in item for item in result.details))

    def test_new_regex_registry_item_fails_until_associated(self):
        write(
            self.roots["ora"] / "orchestrator/feature.py",
            "def feature():\n    return 'initial'\n\n"
            "def surprise_route():\n    return 'new'\n",
        )
        self.commit(
            "ora",
            "Register new route\n\nDocumentation-No-Impact: ora.feature",
        )

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                "unmapped discovered item: ora.runtime-functions:surprise_route"
                in item
                for item in result.details
            ),
            result.details,
        )

    def test_new_json_catalog_item_fails_until_associated(self):
        catalog_path = self.roots["ora"] / "config/framework-invocability.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        catalog["invocable_frameworks"].append("new.md")
        write(catalog_path, json.dumps(catalog))
        self.commit(
            "ora",
            "Register catalog entry\n\n"
            "Documentation-No-Impact: ora.internal-catalog",
        )

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                "unmapped discovered item: ora.framework-catalog:new.md" in item
                for item in result.details
            ),
            result.details,
        )

    def test_new_tracked_glob_item_fails_until_associated(self):
        write(self.roots["msi"] / "generated/new.md", "# New generated file\n")
        self.commit(
            "msi",
            "Add generated registration\n\n"
            "Documentation-No-Impact: site.generated",
        )

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                "unmapped discovered item: msi.generated-files:generated/new.md"
                in item
                for item in result.details
            ),
            result.details,
        )

    def test_discovery_association_requires_an_explicit_surface_id(self):
        ownership = self._ownership_document()
        association = ownership["discovery"]["internal"][0]["associations"][0]
        del association["surface_id"]
        self._write_configuration(ownership=ownership)
        self.commit("vault", "Remove discovery capability association")

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                "associations[0] fields differ from the locked schema" in item
                for item in result.details
            ),
            result.details,
        )

    def test_discovery_deltas_affect_associated_family_beyond_broad_path_owner(self):
        ownership = self._ownership_document()
        source = ownership["discovery"]["internal"][0]
        source["item_field"] = "name"
        source["associations"] = [
            {"pattern": item, "surface_id": "ora.internal-catalog"}
            for item in ("kept.md", "removed.md", "added.md")
        ]
        for surface in ownership["surfaces"]:
            if surface["surface_id"] == "ora.internal-catalog":
                surface["owners"] = [
                    {
                        "repository": "ora",
                        "pattern": "config/registered-only/**",
                    }
                ]
        ownership["surfaces"].append(
            {
                "surface_id": "ora.config-files",
                "class": "internal",
                "owners": [{"repository": "ora", "pattern": "config/**"}],
                "canonical": {
                    "path": "Projects/Ora/Reference — Feature.md",
                    "section": "Behavior",
                },
                "propagation": {"type": "none"},
                "consumers": [],
                "references": [],
            }
        )
        catalog_path = self.roots["ora"] / "config/framework-invocability.json"
        catalog = {
            "_schema_version": 1,
            "invocable_frameworks": [
                {"name": "kept.md", "handler": "old-handler"},
                {"name": "removed.md", "handler": "removed-handler"},
            ],
            "pickable_frameworks": [],
            "aliases": {},
            "internal_only_frameworks": [],
        }
        write(catalog_path, json.dumps(catalog))
        self._write_configuration(ownership=ownership)
        self.bases["ora"] = self.commit("ora", "Pin structured catalog base")
        self.bases["vault"] = self.commit("vault", "Pin discovery associations")

        catalog["invocable_frameworks"] = [
            {"name": "kept.md", "handler": "new-handler"},
            {"name": "added.md", "handler": "added-handler"},
        ]
        write(catalog_path, json.dumps(catalog))
        self.commit(
            "ora",
            "Change structured registrations\n\n"
            "Documentation-No-Impact: ora.config-files",
        )

        result = self.check(verbose=True)

        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                "documentation disposition missing for ora.internal-catalog"
                in item
                for item in result.details
            ),
            result.details,
        )
        self.assertTrue(
            any(
                "discovery ora.framework-catalog enumerated base=2, current=2, "
                "added=1, removed=1, materially-changed=1" in item
                for item in result.details
            ),
            result.details,
        )

    def test_discovery_reassignment_preserves_prior_and_current_families(self):
        ownership = self._ownership_document()
        ownership["surfaces"].append(
            {
                "surface_id": "ora.reassigned-catalog",
                "class": "internal",
                "owners": [
                    {
                        "repository": "ora",
                        "pattern": "config/reassigned/**",
                    }
                ],
                "canonical": {
                    "path": "Projects/Ora/Reference — Feature.md",
                    "section": "Behavior",
                },
                "propagation": {"type": "none"},
                "consumers": [],
                "references": [],
            }
        )
        self._write_configuration(ownership=ownership)
        self.bases["vault"] = self.commit(
            "vault", "Pin both catalog capability families"
        )

        source = ownership["discovery"]["internal"][0]
        source["associations"] = [
            {"pattern": "a.md", "surface_id": "ora.reassigned-catalog"}
        ]
        self._write_configuration(ownership=ownership)
        self.commit(
            "vault",
            "Reassign catalog capability\n\n"
            "Documentation-No-Impact: ora.reassigned-catalog",
        )

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                "documentation disposition missing for ora.internal-catalog "
                "in vault final commit" in item
                for item in result.details
            ),
            result.details,
        )
        self.assertFalse(
            any(
                "documentation disposition missing for ora.reassigned-catalog"
                in item
                for item in result.details
            ),
            result.details,
        )

    def test_required_canonical_update_fails_without_disposition(self):
        write(
            self.roots["ora"] / "orchestrator/feature.py",
            "def feature():\n    return 'changed'\n",
        )
        self.commit("ora", "Change feature behavior")

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(
            any("documentation disposition missing" in item for item in result.details)
        )

    def test_change_elsewhere_in_canonical_does_not_discharge_named_section(self):
        write(
            self.roots["ora"] / "orchestrator/feature.py",
            "def feature():\n    return 'changed'\n",
        )
        canonical_body = (
            "# Feature\n\n## Behavior\n\nInitial behavior.\n\n"
            "## Maintenance notes\n\nChanged outside the owned section.\n"
        )
        write(
            self.roots["vault"] / "Projects/Ora/Reference — Feature.md",
            "---\nnexus:\n  - ora\ntype: reference\n---\n\n" + canonical_body,
        )
        write(self.roots["ora"] / "docs/feature.md", canonical_body)
        self.commit("vault", "Change another canonical section")
        self.commit("ora", "Change feature behavior and mirror")

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                "documentation disposition missing for ora.feature"
                in item
                for item in result.details
            ),
            result.details,
        )

    def test_rename_attributes_both_prior_and_current_ownership_families(self):
        ownership = self._ownership_document()
        for suffix in ("old", "new"):
            canonical = f"Projects/Ora/Reference — Rename {suffix.title()}.md"
            write(
                self.roots["vault"] / canonical,
                "---\nnexus:\n  - ora\ntype: reference\n---\n\n"
                f"# Rename {suffix.title()}\n\n## Behavior\n\n{suffix.title()} family.\n",
            )
            ownership["surfaces"].append(
                {
                    "surface_id": f"ora.rename-{suffix}",
                    "class": "internal",
                    "owners": [
                        {
                            "repository": "ora",
                            "pattern": f"orchestrator/rename-{suffix}/**",
                        }
                    ],
                    "canonical": {"path": canonical, "section": "Behavior"},
                    "propagation": {"type": "none"},
                    "consumers": [],
                    "references": [],
                }
            )

        old_path = self.roots["ora"] / "orchestrator/rename-old/feature.py"
        write(old_path, "def renamed_feature():\n    return 'unchanged'\n")
        self._write_configuration(ownership=ownership)
        self.bases["ora"] = self.commit("ora", "Pin old ownership family")
        self.bases["vault"] = self.commit("vault", "Pin rename ownership families")

        new_directory = self.roots["ora"] / "orchestrator/rename-new"
        new_directory.mkdir(parents=True)
        git(
            self.roots["ora"],
            "mv",
            "orchestrator/rename-old/feature.py",
            "orchestrator/rename-new/feature.py",
        )
        self.commit(
            "ora",
            "Move feature to new ownership family\n\n"
            "Documentation-No-Impact: ora.rename-new",
        )

        result = self.check(verbose=True)

        self.assertFalse(result.passed)
        self.assertIn(
            "affected surfaces: ora.rename-new, ora.rename-old",
            result.details,
        )
        self.assertTrue(
            any(
                "documentation disposition missing for ora.rename-old"
                in item
                for item in result.details
            ),
            result.details,
        )
        self.assertFalse(
            any(
                "documentation disposition missing for ora.rename-new"
                in item
                for item in result.details
            ),
            result.details,
        )

    def test_broken_declared_reference_fails(self):
        (self.roots["ora"] / "orchestrator/feature.py").unlink()
        self.update_feature_canonical("Feature was removed.", mirror=True)
        self.commit("ora", "Remove feature implementation")
        self.commit("vault", "Document feature removal")

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(
            any("declared symbol reference is missing" in item for item in result.details)
        )

    def test_reviewed_no_impact_trailer_allows_refactor(self):
        write(
            self.roots["ora"] / "orchestrator/feature.py",
            "def feature():\n    value = 'initial'\n    return value\n",
        )
        self.commit(
            "ora",
            "Refactor feature\n\nDocumentation-No-Impact: ora.feature",
        )

        result = self.check()

        self.assertTrue(result.passed, result.details)

    def test_no_impact_trailer_is_rejected_when_canonical_section_changed(self):
        write(
            self.roots["ora"] / "orchestrator/feature.py",
            "def feature():\n    return 'changed'\n",
        )
        self.update_feature_canonical("Changed behavior.", mirror=True)
        self.commit("vault", "Document changed feature behavior")
        self.commit(
            "ora",
            "Change feature behavior\n\nDocumentation-No-Impact: ora.feature",
        )

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                "unused Documentation-No-Impact trailer in ora final commit: "
                "ora.feature"
                in item
                for item in result.details
            ),
            result.details,
        )

    def test_matching_subject_line_is_not_a_git_trailer(self):
        write(
            self.roots["ora"] / "orchestrator/feature.py",
            "def feature():\n    value = 'initial'\n    return value\n",
        )
        self.commit(
            "ora",
            "Documentation-No-Impact: ora.feature\n\n"
            "Refactor feature without changing behavior.",
        )

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                "Documentation-No-Impact trailer, found 0" in item
                for item in result.details
            ),
            result.details,
        )

    def test_matching_body_example_is_not_a_git_trailer(self):
        write(
            self.roots["ora"] / "orchestrator/feature.py",
            "def feature():\n    value = 'initial'\n    return value\n",
        )
        self.commit(
            "ora",
            "Refactor feature\n\n"
            "For example, a task might contain this line:\n"
            "Documentation-No-Impact: ora.feature\n\n"
            "This final paragraph is explanatory prose.",
        )

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                "Documentation-No-Impact trailer, found 0" in item
                for item in result.details
            ),
            result.details,
        )

    def test_duplicate_terminal_git_trailers_fail(self):
        write(
            self.roots["ora"] / "orchestrator/feature.py",
            "def feature():\n    value = 'initial'\n    return value\n",
        )
        self.commit(
            "ora",
            "Refactor feature\n\n"
            "Documentation-No-Impact: ora.feature\n"
            "Documentation-No-Impact: ora.feature",
        )

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                "Documentation-No-Impact trailer, found 2" in item
                for item in result.details
            ),
            result.details,
        )

    def test_registered_body_only_mirror_is_governed_by_surface_mapping(self):
        write(
            self.roots["ora"] / "docs/feature.md",
            "# Feature\n\n## Behavior\n\nChanged mirror only.\n",
        )
        self.commit(
            "ora",
            "Change installed mirror\n\nDocumentation-No-Impact: ora.feature",
        )

        result = self.check()

        self.assertFalse(result.passed)
        self.assertFalse(
            any(
                "unmapped code change: ora:docs/feature.md" in item
                for item in result.details
            ),
            result.details,
        )
        self.assertTrue(
            any("propagation mismatch for ora.feature" in item for item in result.details),
            result.details,
        )

    def test_unregistered_machine_consumed_markdown_fails_closed(self):
        write(
            self.roots["app"] / "src/content/runtime/page.md",
            "# Published runtime page\n",
        )
        self.commit("app", "Add publisher-managed Markdown")

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                "unmapped code change: app:src/content/runtime/page.md" in item
                for item in result.details
            ),
            result.details,
        )

    def test_propagation_mismatch_fails(self):
        write(
            self.roots["ora"] / "orchestrator/feature.py",
            "def feature():\n    return 'new behavior'\n",
        )
        self.update_feature_canonical("New behavior.", mirror=False)
        self.commit("ora", "Change feature behavior")
        self.commit("vault", "Document new feature behavior")

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(any("propagation mismatch" in item for item in result.details))

    def test_exact_baseline_ratchet_and_resolved_entry_removal(self):
        self.install_accepted_missing_finding()
        exact = self.check()
        self.assertTrue(exact.passed, exact.details)

        # Promotion resolves the accepted finding, but retaining its baseline
        # row is itself a failure.
        write(self.roots["ora"] / "frameworks/book/b.md", "# B\n\nBody.\n")
        for entry in self.manifest_entries:
            if entry["pair_id"] == "missing:b":
                entry["disposition"] = "paired"
                entry["finding_severity"] = "load-bearing"
                entry["last_known_clean"] = "2026-08-28"
        self._write_manifest()
        self.commit("ora", "Build registered framework twin")
        self.commit("vault", "Promote framework pair")

        stale = self.check()
        self.assertFalse(stale.passed)
        self.assertTrue(
            any("stale accepted framework finding" in item for item in stale.details)
        )

        self.accepted_findings = []
        self._write_configuration()
        self.commit("vault", "Remove resolved accepted finding")

        removed = self.check()
        self.assertTrue(removed.passed, removed.details)

    def test_same_task_cannot_authorize_its_new_framework_finding(self):
        self.install_accepted_missing_finding(pin_after=False)

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(
            any("accepted finding addition is not authorized" in item for item in result.details),
            result.details,
        )

    def test_same_task_cannot_materially_mutate_carried_finding(self):
        self.install_accepted_missing_finding()
        self.accepted_findings[0]["owner"] = "G1.100"
        self._write_configuration()
        self.commit("vault", "Attempt to transfer accepted-finding ownership")

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(
            any("accepted finding material mutation" in item for item in result.details),
            result.details,
        )

    def test_initial_ownership_bootstrap_validates_every_current_surface(self):
        ownership = self._ownership_document()
        for surface in ownership["surfaces"]:
            if surface["surface_id"] == "ora.framework-library":
                surface["propagation"]["pair_id"] = "pair:a"
            if surface["surface_id"] == "ora.feature":
                surface["references"][0]["symbol"] = "missing_feature"

        write(
            self.roots["ora"] / "docs/feature.md",
            "# Feature\n\n## Behavior\n\nStale bootstrap mirror.\n",
        )
        self.bases["ora"] = self.commit("ora", "Pin stale pre-coverage mirror")
        self._write_configuration_without_ownership()
        self.bases["vault"] = self.commit(
            "vault", "Pin configuration before ownership coverage"
        )

        self._write_configuration(ownership=ownership)
        self.commit(
            "vault",
            "Bootstrap ownership coverage\n\n"
            "Documentation-No-Impact: ora.feature\n"
            "Documentation-No-Impact: ora.framework-library\n"
            "Documentation-No-Impact: ora.internal-catalog\n"
            "Documentation-No-Impact: site.generated",
        )

        result = self.check(verbose=True)

        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                "declared symbol reference does not resolve" in item
                for item in result.details
            ),
            result.details,
        )
        self.assertTrue(
            any(
                "propagation mismatch for ora.feature" in item
                for item in result.details
            ),
            result.details,
        )
        self.assertTrue(
            any(
                "ownership/discovery pinned base is absent" in item
                for item in result.details
            ),
            result.details,
        )

    def test_initial_ownership_bootstrap_passes_after_exact_dispositions(self):
        ownership = self._ownership_document()
        for surface in ownership["surfaces"]:
            if surface["surface_id"] == "ora.framework-library":
                surface["propagation"]["pair_id"] = "pair:a"

        self._write_configuration_without_ownership()
        self.bases["vault"] = self.commit(
            "vault", "Pin configuration before ownership coverage"
        )
        self._write_configuration(ownership=ownership)
        self.commit(
            "vault",
            "Bootstrap reviewed ownership coverage\n\n"
            "Documentation-No-Impact: ora.feature\n"
            "Documentation-No-Impact: ora.framework-library\n"
            "Documentation-No-Impact: ora.internal-catalog\n"
            "Documentation-No-Impact: site.generated",
        )

        result = self.check()

        self.assertTrue(result.passed, result.details)

    def test_preactivation_base_cannot_bootstrap_an_accepted_finding_block(self):
        self._write_configuration(include_accepted=False)
        self.bases["vault"] = self.commit("vault", "Pre-bootstrap configuration")
        self._write_configuration()
        self.commit("vault", "Bootstrap accepted-finding block")

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                "pinned vault base predates the activated accepted-finding block"
                in item
                for item in result.details
            ),
            result.details,
        )

    def test_incomplete_repository_coverage_fails_before_configuration_work(self):
        incomplete_roots = dict(self.roots)
        incomplete_roots.pop("msi")

        result = self.check(roots=incomplete_roots)

        self.assertFalse(result.passed)
        self.assertIn("all five explicit roots are mandatory", result.details[0])

    def test_duplicate_repository_roots_fail_before_coverage_evidence(self):
        duplicate_roots = dict(self.roots)
        duplicate_roots["org"] = duplicate_roots["app"]

        result = self.check(roots=duplicate_roots)

        self.assertFalse(result.passed)
        self.assertIn("repository roots must be distinct", result.details[0])
        self.assertFalse(any(item.startswith("read ") for item in result.details))

    def test_swapped_repository_labels_fail_identity_markers_before_evidence(self):
        swapped_roots = dict(self.roots)
        swapped_bases = dict(self.bases)
        swapped_roots["app"], swapped_roots["org"] = (
            swapped_roots["org"],
            swapped_roots["app"],
        )
        swapped_bases["app"], swapped_bases["org"] = (
            swapped_bases["org"],
            swapped_bases["app"],
        )

        result = self.check(roots=swapped_roots, bases=swapped_bases)

        self.assertFalse(result.passed)
        self.assertIn("declared repository identity", result.details[0])
        self.assertFalse(any(item.startswith("read ") for item in result.details))

    def test_propagation_deduplication_includes_canonical_identity(self):
        other_canonical = "Projects/Ora/Reference — Other Feature.md"
        write(
            self.roots["vault"] / other_canonical,
            "---\nnexus:\n  - ora\ntype: reference\n---\n\n"
            "# Other Feature\n\n## Behavior\n\nOther behavior.\n",
        )
        write(
            self.roots["ora"] / "orchestrator/other.py",
            "def other():\n    return 'other'\n",
        )
        write(
            self.roots["ora"] / "orchestrator/feature.py",
            "def feature():\n    value = 'initial'\n    return value\n",
        )
        ownership = self._ownership_document()
        ownership["surfaces"].append(
            {
                "surface_id": "ora.other",
                "class": "user-facing",
                "owners": [
                    {"repository": "ora", "pattern": "orchestrator/other.py"}
                ],
                "canonical": {"path": other_canonical, "section": "Behavior"},
                "propagation": {
                    "type": "ora_body_only",
                    "repository": "ora",
                    "path": "docs/feature.md",
                },
                "consumers": [],
                "references": [],
            }
        )
        self._write_configuration(ownership=ownership)
        self.commit(
            "ora",
            "Change two capability families\n\n"
            "Documentation-No-Impact: ora.feature",
        )
        self.commit("vault", "Register second canonical family")

        result = self.check()

        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                "propagation mismatch for ora.other" in item
                for item in result.details
            ),
            result.details,
        )

    def test_valid_complete_task_reads_all_five_repositories(self):
        write(
            self.roots["ora"] / "orchestrator/feature.py",
            "def feature():\n    return 'complete'\n",
        )
        self.update_feature_canonical("Complete behavior.", mirror=True)
        self.commit("ora", "Implement complete behavior")
        self.commit("vault", "Document complete behavior")

        result = self.check(verbose=True)

        self.assertTrue(result.passed, result.details)
        for repository in VERIFY.DOCUMENTATION_REPOSITORIES:
            self.assertTrue(
                any(item.startswith(f"read {repository} ") for item in result.details),
                result.details,
            )
        self.assertTrue(
            any("referential/state evidence only" in item for item in result.details)
        )


class ProductionDocumentationContractTests(unittest.TestCase):
    def production_roots(self) -> dict[str, Path]:
        roots: dict[str, Path] = {}
        for name in VERIFY.DOCUMENTATION_REPOSITORIES:
            value = os.environ.get(f"DCP_{name.upper()}_ROOT")
            if not value:
                self.skipTest("explicit five-root production contract is unavailable")
            roots[name] = Path(value).resolve()
        return roots

    def test_production_ownership_map_resolves_declared_contract(self):
        roots = self.production_roots()
        registry = VERIFY.load_documentation_ownership_registry(
            VERIFY.DOCUMENTATION_CONFIGURATION_FILE
        )
        states: dict[str, VERIFY.DocumentationRepositoryState] = {}
        for name, root in roots.items():
            head = git(root, "rev-parse", "HEAD")
            states[name] = VERIFY.DocumentationRepositoryState(
                name=name,
                root=root,
                base_commit=head,
                head_commit=head,
                changed_paths=(),
            )

        self.assertEqual(
            {surface.surface_class for surface in registry.surfaces},
            VERIFY.DOCUMENTATION_SURFACE_CLASSES,
        )
        self.assertEqual(
            set(registry.discovery), VERIFY.DOCUMENTATION_SURFACE_CLASSES
        )
        for surface in registry.surfaces:
            self.assertIn(
                surface.propagation["type"],
                VERIFY.DOCUMENTATION_PROPAGATION_TYPES,
            )
            canonical = VERIFY._bounded_documentation_path(
                roots["vault"], surface.canonical_path
            )
            self.assertTrue(canonical.is_file(), surface.surface_id)
            if surface.canonical_section is not None:
                self.assertTrue(
                    VERIFY._markdown_has_section(
                        VERIFY.read_file(canonical), surface.canonical_section
                    ),
                    f"{surface.surface_id}: {surface.canonical_section}",
                )
            for reference in surface.references:
                self.assertIsNone(
                    VERIFY._resolve_documentation_reference(reference, states),
                    surface.surface_id,
                )

        thinking_tools = next(
            surface
            for surface in registry.surfaces
            if surface.surface_id == "ora.thinking-tools"
        )
        self.assertEqual(thinking_tools.propagation["type"], "ora_body_only")
        self.assertEqual(thinking_tools.propagation["path"], "thinking-tools.md")

    def test_production_audit_accepts_only_the_two_exact_external_findings(self):
        self.production_roots()
        result = VERIFY.check_framework_pair_audit(verbose=True)

        self.assertTrue(result.passed, result.details)
        self.assertTrue(
            any(
                "accepted external=2, audit failures=0" in detail
                for detail in result.details
            ),
            result.details,
        )
        self.assertEqual(
            sum(detail.startswith("accepted external finding:")
                for detail in result.details),
            2,
        )


if __name__ == "__main__":
    unittest.main()
