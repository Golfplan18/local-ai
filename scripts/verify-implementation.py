#!/usr/bin/env python3
"""
Verification script for the Analytical Territories and Modes Implementation.

Runs at the end of each phase (smoke test) and at end of full execution (full check).
Catches mechanical errors after autonomous execution completes. Quality issues
(analytical correctness, educational appropriateness) require user judgment and
are NOT verified here.

Usage:
    python3 verify-implementation.py [--check <category>] [--verbose]

Categories:
    template       — Template conformance for every mode in /Modes/
    crossref       — Cross-reference resolution (mode_id, territory, lens_id)
    signals        — Signal vocabulary registry (≥3 entries per mode_id; no orphans)
    runtime        — Runtime config completeness (entry per mode_id)
    drift          — Drift parity for registered pairs
    framework-pairs — Full manifest-backed vault/runtime framework coverage
    framework-pairs-audit — Fail-open-hook view with exact accepted states classified
    documentation-integrity — Focused five-repository documentation gate
    debt           — Architectural debt (no stale references)
    routing        — Routing accuracy (post-Phase-6+9 only)
    tests          — Python and JS test suites pass
    all            — Run all checks (default)

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
    2 — script error (e.g., missing files)
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ORA_ROOT = Path(
    os.environ.get("ORA_HOME") or Path(__file__).resolve().parents[1]
).expanduser().resolve()
if str(ORA_ROOT) not in sys.path:
    sys.path.insert(0, str(ORA_ROOT))
from orchestrator import runtime_paths as _rp  # noqa: E402

VAULT_ROOT = _rp.vault_dir().resolve()
VAULT_ORA = VAULT_ROOT / "Projects" / "Ora"

MODES_DIR = VAULT_ROOT / "Modes"
LENSES_DIR = VAULT_ROOT / "Lenses"
ORA_MODES_DIR = ORA_ROOT / "modes"
ORA_LENSES_DIR = ORA_ROOT / "knowledge" / "mental-models"

TERRITORIES_FILE = VAULT_ORA / "Reference — Analytical Territories.md"
TEMPLATE_FILE = VAULT_ORA / "Reference — Mode Specification Template.md"
SIGNAL_REGISTRY_FILE = VAULT_ORA / "Registry — Signal Vocabulary Registry.md"
MODE_REGISTRY_FILE = VAULT_ORA / "Registry — Mode Registry.md"
WITHIN_TREES_FILE = VAULT_ORA / "Reference — Within-Territory Disambiguation Trees.md"
CROSS_ADJ_FILE = VAULT_ORA / "Reference — Cross-Territory Adjacency.md"
DISAMBIG_GUIDE_FILE = VAULT_ORA / "Reference — Disambiguation Style Guide.md"
LENS_SPEC_FILE = VAULT_ORA / "Reference — Lens Library Specification.md"
PIPELINE_FILE = VAULT_ORA / "Reference — Pre-Routing Pipeline Architecture.md"
FRAMEWORK_PAIR_MANIFEST_FILE = (
    VAULT_ROOT / "Projects" / "Ora" /
    "Reference — Vault Ora Framework Pair Manifest.md"
)
FRAMEWORK_ESCALATION_QUEUE_FILE = (
    VAULT_ROOT / "Administration" / "DCP" /
    "Working — Documentation-Code Parity Escalation Queue.md"
)

FRAMEWORK_MANIFEST_BEGIN = "<!-- BEGIN DCP FRAMEWORK PAIR MANIFEST JSON -->"
FRAMEWORK_MANIFEST_END = "<!-- END DCP FRAMEWORK PAIR MANIFEST JSON -->"
FRAMEWORK_MANIFEST_ID = "ora/vault-runtime-framework-pairs@1"
FRAMEWORK_PAIR_DISPOSITIONS = {
    "paired",
    "missing_runtime",
    "no_runtime_twin",
    "specified_not_built",
}
SPECIFIED_NOT_BUILT_BANNER = (
    "> **Specified, not built.** This framework describes intended behavior. "
    "No runtime framework body is installed, callable, or picker-visible."
)
SPECIFIED_NOT_BUILT_DCP_BANNER = (
    "> **Specified, not built as a runtime framework.** A limited deterministic "
    "framework-pair detector and post-commit queue hook exist. The DCP Sweep, "
    "Audit, Reconcile, Specify, and Deprecate framework described here is not "
    "installed or callable as a runtime framework."
)
SPECIFIED_NOT_BUILT_BANNERS = (
    SPECIFIED_NOT_BUILT_BANNER,
    SPECIFIED_NOT_BUILT_DCP_BANNER,
)
FRAMEWORK_RUNTIME_EXCLUSIONS = {"frameworks/README.md"}
# Directory prefixes whose contents are never runtime frameworks. `personal/`
# is gitignored (.gitignore: "frameworks/personal/"), so it exists only in a
# working tree; without this a working-tree run reports an unregistered-runtime
# finding that a run against pinned branches cannot see.
FRAMEWORK_RUNTIME_EXCLUDED_DIRS = ("frameworks/personal/",)
# Fields carried in a finding receipt as evidence but excluded from its
# identity. `manifest_sha256` digests the whole manifest document, so a
# cosmetic manifest edit would otherwise mint a new identity for an unchanged
# finding; the body digests describe the current state of a drift, not which
# drift it is. Identity is the problem; these are the evidence about it.
FRAMEWORK_FINDING_EVIDENCE_FIELDS = frozenset(
    {"manifest_sha256", "canonical_body_sha256", "runtime_body_sha256"}
)
# Heading that begins the queue's historical region. Receipts below it record
# findings the user has already dispositioned; they are still authenticated,
# but they no longer suppress a fresh finding. Without this split, closing a
# receipt would silently blind the detector to the same drift recurring.
FRAMEWORK_QUEUE_CLOSED_HEADING = "\n## Closed entries\n"
# A crashed run leaves its lock behind. Held by a human at a terminal that is
# a visible error; on an unattended path it wedges every later run silently and
# permanently, which is worse than the race the lock guards against. After this
# age the lock is treated as abandoned, removed loudly, and the run proceeds.
FRAMEWORK_QUEUE_LOCK_STALE_SECONDS = 900
FRAMEWORK_RECEIPT_PATTERN = re.compile(
    r"<!-- dcp-framework-finding-receipt (\{.*?\}) -->"
)

DOCUMENTATION_CONFIGURATION_FILE = (
    VAULT_ORA / "Reference — Documentation-Code Parity Configuration.md"
)
DOCUMENTATION_OWNERSHIP_BEGIN = (
    "<!-- BEGIN DCP DOCUMENTATION OWNERSHIP JSON -->"
)
DOCUMENTATION_OWNERSHIP_END = (
    "<!-- END DCP DOCUMENTATION OWNERSHIP JSON -->"
)
DOCUMENTATION_OWNERSHIP_ID = "ora/documentation-integrity-ownership@1"
DOCUMENTATION_ACCEPTED_FINDINGS_BEGIN = (
    "<!-- BEGIN DCP ACCEPTED FINDINGS JSON -->"
)
DOCUMENTATION_ACCEPTED_FINDINGS_END = (
    "<!-- END DCP ACCEPTED FINDINGS JSON -->"
)
DOCUMENTATION_ACCEPTED_FINDINGS_ID = (
    "ora/documentation-integrity-accepted-findings@1"
)
DOCUMENTATION_REPOSITORIES = ("vault", "ora", "app", "org", "msi")
DOCUMENTATION_SURFACE_CLASSES = {
    "user-facing",
    "operator-facing",
    "internal",
    "generated",
}
DOCUMENTATION_REFERENCE_TYPES = {"path", "symbol", "endpoint", "route"}
DOCUMENTATION_DISCOVERY_TYPES = {
    "tracked_glob",
    "json_catalog",
    "regex_registry",
}
DOCUMENTATION_PROPAGATION_TYPES = {
    "none",
    "ora_body_only",
    "framework_pair",
    "site_reverse_parity",
}
DOCUMENTATION_DISCOVERY_MAX_SOURCES = 256
DOCUMENTATION_DISCOVERY_MAX_ITEMS = 10_000
DOCUMENTATION_DISCOVERY_MAX_FILE_BYTES = 5_000_000
DOCUMENTATION_STANDALONE_PROSE_FILES = {
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "SUPPORT.md",
    "GOVERNANCE.md",
}
PROTECTED_FRAMEWORK_FINDING_OWNERS = {
    (
        "unregistered_canonical_framework",
        "unregistered-canonical:0e9383eef0b192d1",
    ): "G1.22",
    (
        "paired_runtime_missing",
        "pair:c82da19f72e570a5",
    ): "G1.27",
}

RETIRED_MODE_IDS = {"adversarial", "standard"}
NON_MODE_FILES = {"INDEX"}  # vault navigation files that live in /Modes/ but aren't modes
EXCLUDED_MODE_FILES = RETIRED_MODE_IDS | NON_MODE_FILES
UTILITY_MODE_IDS = {"factual-lookup", "general-inquiry", "subjective-inquiry", "simple"}

# The 21 territory IDs (T1-T21)
TERRITORY_IDS = {f"T{i}" for i in range(1, 22)}

# Required template fields (YAML keys at top level)
REQUIRED_TEMPLATE_FIELDS = {
    "mode_id",
    "canonical_name",
    "suffix_rule",
    "educational_name",
    "territory",
    "gradation_position",
    "adjacent_modes_in_territory",
    "trigger_conditions",
    "disambiguation_routing",
    "when_not_to_invoke",
    "composition",
    "input_contract",
    "critical_questions",
    "failure_modes",
    "lens_dependencies",
    "default_depth_tier",
    "expected_runtime",
    "escalation_signals",
}

SIMPLE_BYPASS_REQUIRED_FIELDS = {
    "mode_id",
    "canonical_name",
    "suffix_rule",
    "educational_name",
    "territory",
    "trigger_conditions",
    "input_contract",
    "output_contract",
    "expected_runtime",
}

# Required pipeline-stage subsections (## headings in body)
REQUIRED_PIPELINE_SUBSECTIONS = {
    "DEPTH ANALYSIS GUIDANCE",
    "BREADTH ANALYSIS GUIDANCE",
    "ANALYTICAL BRIEF AND EVALUATION CRITERIA",
    "REVISION GUIDANCE",
    "CONSOLIDATION GUIDANCE",
    "VERIFICATION CRITERIA",
    "OUTPUT FORMAT GUIDANCE",
    "DEFAULT GEAR",
    "RAG PROFILE",
}

# Vault canonical → Ora operational pairs. Ora paths are repository-relative so
# the same check covers architecture mirrors and runtime framework copies.
DRIFT_PAIRS = [
    ("Projects/Ora/Reference — Analytical Territories.md", "architecture/territories.md"),
    ("Projects/Ora/Reference — Mode Specification Template.md", "architecture/mode-template.md"),
    ("Projects/Ora/Reference — Disambiguation Style Guide.md", "architecture/disambiguation-style-guide.md"),
    ("Projects/Ora/Reference — Lens Library Specification.md", "architecture/lens-library-specification.md"),
    ("Projects/Ora/Reference — Pre-Routing Pipeline Architecture.md", "architecture/pre-routing-pipeline.md"),
    ("Projects/Ora/Registry — Signal Vocabulary Registry.md", "architecture/signal-vocabulary-registry.md"),
    ("Projects/Ora/Reference — Within-Territory Disambiguation Trees.md", "architecture/within-territory-trees.md"),
    ("Projects/Ora/Reference — Cross-Territory Adjacency.md", "architecture/cross-territory-adjacency.md"),
    ("Projects/Ora/Reference — Trusted Web Sources.md", "architecture/trusted-web-sources.md"),
    (
        "Projects/Ora/Framework — Conversation Processing Pipeline.md",
        "frameworks/book/conversation-processing.md",
    ),
    ("Projects/Ora/Framework — Process Inference.md", "frameworks/book/process-inference.md"),
    ("Projects/Ora/Framework — Process Formalization.md", "frameworks/book/process-formalization.md"),
    ("Projects/Ora/Framework — Programming.md", "frameworks/book/programming.md"),
    ("Projects/Ora/Framework — Problem Evolution.md", "frameworks/book/problem-evolution.md"),
    ("Projects/Ora/Specification — F-Quality-Gate.md", "frameworks/book/f-quality-gate.md"),
]
# Compatibility alias for callers that imported the original architecture-only
# registry name before it grew to cover operational framework copies.
ARCHITECTURE_PAIRS = DRIFT_PAIRS


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    passed: bool
    details: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


class FrameworkManifestError(ValueError):
    """The canonical framework-pair manifest is malformed or unsafe."""


class DocumentationIntegrityError(ValueError):
    """The focused documentation-integrity contract is incomplete or unsafe."""


@dataclass(frozen=True)
class FrameworkPairEntry:
    pair_id: str
    canonical_path: str
    runtime_path: Optional[str]
    disposition: str
    finding_severity: str
    last_known_clean: Optional[str]
    rationale: str


@dataclass(frozen=True)
class FrameworkPairManifest:
    manifest_id: str
    manifest_sha256: str
    entries: tuple[FrameworkPairEntry, ...]
    expected_counts: dict[str, int]


@dataclass(frozen=True)
class FrameworkPairFinding:
    payload: dict[str, Any]
    finding_digest: str


@dataclass(frozen=True)
class FrameworkPairEvaluation:
    manifest: FrameworkPairManifest
    findings: tuple[FrameworkPairFinding, ...]
    paired_clean: int
    paired_drifted: int
    missing_runtime: int
    no_runtime_twin: int
    specified_not_built: int


@dataclass(frozen=True)
class DocumentationRepositoryState:
    name: str
    root: Path
    base_commit: str
    head_commit: str
    changed_paths: tuple[str, ...]


@dataclass(frozen=True)
class DocumentationReference:
    reference_type: str
    repository: str
    path: str
    value: Optional[str] = None


@dataclass(frozen=True)
class DocumentationRepositoryIdentity:
    remote: str
    value: str


@dataclass(frozen=True)
class DocumentationOwner:
    repository: str
    pattern: str


@dataclass(frozen=True)
class DocumentationSurface:
    surface_id: str
    surface_class: str
    owners: tuple[DocumentationOwner, ...]
    canonical_path: str
    canonical_section: Optional[str]
    propagation: dict[str, Any]
    consumers: tuple[str, ...]
    references: tuple[DocumentationReference, ...]


@dataclass(frozen=True)
class DocumentationDiscoveryAssociation:
    pattern: str
    surface_id: str


@dataclass(frozen=True)
class DocumentationDiscoverySource:
    source_id: str
    source_type: str
    repository: str
    path: Optional[str]
    selector: str
    item_field: Optional[str]
    associations: tuple[DocumentationDiscoveryAssociation, ...]


@dataclass(frozen=True)
class DocumentationOwnershipRegistry:
    surfaces: tuple[DocumentationSurface, ...]
    discovery: dict[str, tuple[DocumentationDiscoverySource, ...]]
    repository_identities: dict[str, DocumentationRepositoryIdentity]


@dataclass(frozen=True)
class DocumentationAcceptedFinding:
    finding_type: str
    pair_id: str
    canonical_path: Optional[str]
    runtime_path: Optional[str]
    disposition: str
    severity: str
    owner: str
    repository_commits: dict[str, str]


@dataclass(frozen=True)
class DocumentationIntegrityEvaluation:
    repositories: dict[str, DocumentationRepositoryState]
    affected_surfaces: tuple[str, ...]
    findings: tuple[str, ...]
    evidence: tuple[str, ...]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_file(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def parse_yaml_frontmatter(content: str) -> tuple[Optional[dict], str]:
    """Parse YAML frontmatter at the top of a markdown file.

    Returns (frontmatter dict or None, body string).
    Naive parser — matches the shape of vault YAML (key: value, list: \n  - item).
    Returns the YAML lines as a flat dict; nested structures are left as raw strings.
    """
    if not content.startswith("---\n"):
        return None, content
    end = content.find("\n---\n", 4)
    if end == -1:
        return None, content
    yaml_block = content[4:end]
    body = content[end + 5:]

    # Naive parse: top-level keys
    fm: dict = {}
    current_key = None
    current_list: Optional[list] = None
    for line in yaml_block.split("\n"):
        if not line.strip():
            continue
        if line.startswith("  - "):
            if current_list is not None:
                current_list.append(line[4:].strip())
            continue
        if ": " in line and not line.startswith(" "):
            k, v = line.split(": ", 1)
            fm[k.strip()] = v.strip()
            current_key = k.strip()
            current_list = None
        elif line.endswith(":") and not line.startswith(" "):
            current_key = line[:-1].strip()
            current_list = []
            fm[current_key] = current_list
    return fm, body


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_repo_relative_path(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise FrameworkManifestError(f"{field_name} must be a nonempty string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise FrameworkManifestError(
            f"{field_name} must be a normalized repository-relative path: {value!r}"
        )
    return value


def _normalized_framework_content(
    content: str,
    *,
    strip_vault_yaml: bool,
    label: str,
) -> str:
    """Return the exact G1.13 comparison body.

    Newlines are normalized, vault frontmatter and its one separator blank line
    are removed, and terminal newline count is ignored. No prose, headings,
    interior whitespace, ordering, or links are normalized.
    """
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    if strip_vault_yaml and content.startswith("---\n"):
        end = content.find("\n---\n", 4)
        if end == -1:
            raise FrameworkManifestError(
                f"unterminated vault YAML frontmatter: {label}"
            )
        content = content[end + 5:]
        if content.startswith("\n"):
            content = content[1:]
    return content.rstrip("\n")


def _normalized_framework_body(path: Path, *, strip_vault_yaml: bool) -> str:
    return _normalized_framework_content(
        read_file(path),
        strip_vault_yaml=strip_vault_yaml,
        label=str(path),
    )


def _bounded_repo_path(root: Path, relative_path: str) -> Path:
    """Resolve a manifest path without allowing a symlink escape."""
    root = root.resolve()
    candidate = root / relative_path
    current = root
    for part in Path(relative_path).parts:
        current = current / part
        if current.is_symlink():
            raise FrameworkManifestError(
                f"manifest path contains a symlink: {relative_path}"
            )
    if candidate.exists():
        try:
            candidate.resolve(strict=True).relative_to(root)
        except ValueError as exc:
            raise FrameworkManifestError(
                f"manifest path escapes its repository root: {relative_path}"
            ) from exc
    return candidate


def load_framework_pair_manifest(
    manifest_path: Optional[Path] = None,
) -> FrameworkPairManifest:
    path = manifest_path or FRAMEWORK_PAIR_MANIFEST_FILE
    content = read_file(path)
    if content.count(FRAMEWORK_MANIFEST_BEGIN) != 1 or content.count(
        FRAMEWORK_MANIFEST_END
    ) != 1:
        raise FrameworkManifestError(
            "manifest must contain exactly one authenticated JSON block"
        )
    start = content.index(FRAMEWORK_MANIFEST_BEGIN) + len(FRAMEWORK_MANIFEST_BEGIN)
    end = content.index(FRAMEWORK_MANIFEST_END, start)
    block = content[start:end].strip()
    match = re.fullmatch(r"```json\s*\n(.*?)\n```", block, re.DOTALL)
    if not match:
        raise FrameworkManifestError("manifest JSON block has invalid fencing")
    try:
        document = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise FrameworkManifestError(f"manifest JSON is invalid: {exc}") from exc
    if not isinstance(document, dict):
        raise FrameworkManifestError("manifest JSON root must be an object")
    if document.get("schema_version") != 1:
        raise FrameworkManifestError("manifest schema_version must equal 1")
    if document.get("manifest_id") != FRAMEWORK_MANIFEST_ID:
        raise FrameworkManifestError(
            f"manifest_id must equal {FRAMEWORK_MANIFEST_ID!r}"
        )
    expected_counts = document.get("expected_counts")
    legacy_count_fields = {
        "active_frameworks",
        "missing_runtime",
        "no_runtime_twin",
        "paired",
        "total_entries",
    }
    specified_count_fields = legacy_count_fields | {"specified_not_built"}
    if (
        not isinstance(expected_counts, dict)
        or frozenset(expected_counts) not in {
            frozenset(legacy_count_fields),
            frozenset(specified_count_fields),
        }
    ):
        raise FrameworkManifestError("manifest expected_counts contract is incomplete")
    if any(not isinstance(value, int) or value < 0 for value in expected_counts.values()):
        raise FrameworkManifestError("manifest expected_counts values must be integers")

    raw_entries = document.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise FrameworkManifestError("manifest entries must be a nonempty list")
    entries: list[FrameworkPairEntry] = []
    pair_ids: set[str] = set()
    canonical_paths: set[str] = set()
    runtime_paths: set[str] = set()
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            raise FrameworkManifestError(f"entry {index} must be an object")
        required = {
            "pair_id",
            "canonical_path",
            "runtime_path",
            "disposition",
            "comparison",
            "finding_severity",
            "last_known_clean",
            "rationale",
        }
        if set(raw) != required:
            raise FrameworkManifestError(
                f"entry {index} fields differ from the locked schema"
            )
        pair_id = raw["pair_id"]
        if not isinstance(pair_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._:-]*", pair_id):
            raise FrameworkManifestError(f"entry {index} has invalid pair_id")
        if pair_id in pair_ids:
            raise FrameworkManifestError(f"duplicate pair_id: {pair_id}")
        pair_ids.add(pair_id)
        canonical_path = _safe_repo_relative_path(
            raw["canonical_path"], field_name="canonical_path"
        )
        if not canonical_path.startswith(("Projects/Ora/", "Projects/MSI/")):
            raise FrameworkManifestError(
                f"canonical_path is outside registered framework roots: {canonical_path}"
            )
        if canonical_path in canonical_paths:
            raise FrameworkManifestError(
                f"duplicate canonical_path: {canonical_path}"
            )
        canonical_paths.add(canonical_path)
        disposition = raw["disposition"]
        if disposition not in FRAMEWORK_PAIR_DISPOSITIONS:
            raise FrameworkManifestError(
                f"entry {pair_id} has invalid disposition: {disposition!r}"
            )
        if raw["comparison"] != "normalized_body_exact":
            raise FrameworkManifestError(
                f"entry {pair_id} must use normalized_body_exact"
            )
        runtime_path = raw["runtime_path"]
        if disposition == "no_runtime_twin":
            if runtime_path is not None:
                raise FrameworkManifestError(
                    f"entry {pair_id} must not declare a runtime_path"
                )
        else:
            runtime_path = _safe_repo_relative_path(
                runtime_path, field_name="runtime_path"
            )
            if not runtime_path.startswith("frameworks/"):
                raise FrameworkManifestError(
                    f"runtime_path is outside frameworks/: {runtime_path}"
                )
            if runtime_path in runtime_paths:
                raise FrameworkManifestError(
                    f"duplicate runtime_path: {runtime_path}"
                )
            runtime_paths.add(runtime_path)
        severity = raw["finding_severity"]
        if severity not in {"load-bearing", "stale", "missing-feature"}:
            raise FrameworkManifestError(
                f"entry {pair_id} has invalid finding_severity"
            )
        last_known_clean = raw["last_known_clean"]
        if last_known_clean is not None and not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", str(last_known_clean)
        ):
            raise FrameworkManifestError(
                f"entry {pair_id} has invalid last_known_clean"
            )
        rationale = raw["rationale"]
        if not isinstance(rationale, str) or not rationale.strip():
            raise FrameworkManifestError(f"entry {pair_id} lacks rationale")
        entries.append(
            FrameworkPairEntry(
                pair_id=pair_id,
                canonical_path=canonical_path,
                runtime_path=runtime_path,
                disposition=disposition,
                finding_severity=severity,
                last_known_clean=last_known_clean,
                rationale=rationale,
            )
        )

    actual_counts = {
        disposition: sum(entry.disposition == disposition for entry in entries)
        for disposition in FRAMEWORK_PAIR_DISPOSITIONS
    }
    active_frameworks = sum(
        Path(entry.canonical_path).name.startswith("Framework — ")
        for entry in entries
    )
    derived_counts = {
        "active_frameworks": active_frameworks,
        "missing_runtime": actual_counts["missing_runtime"],
        "no_runtime_twin": actual_counts["no_runtime_twin"],
        "paired": actual_counts["paired"],
        "total_entries": len(entries),
    }
    if "specified_not_built" in expected_counts:
        derived_counts["specified_not_built"] = actual_counts[
            "specified_not_built"
        ]
    elif actual_counts["specified_not_built"]:
        raise FrameworkManifestError(
            "manifest expected_counts must include specified_not_built when used"
        )
    if expected_counts != derived_counts:
        raise FrameworkManifestError(
            f"manifest expected_counts do not match entries: {derived_counts}"
        )
    normalized_document = _canonical_json(document)
    return FrameworkPairManifest(
        manifest_id=document["manifest_id"],
        manifest_sha256=_sha256_text(normalized_document),
        entries=tuple(entries),
        expected_counts=dict(expected_counts),
    )


def _framework_finding(
    manifest: FrameworkPairManifest,
    *,
    pair_id: str,
    finding_type: str,
    severity: str,
    canonical_path: Optional[str],
    runtime_path: Optional[str],
    disposition: str,
    canonical_body_sha256: Optional[str],
    runtime_body_sha256: Optional[str],
) -> FrameworkPairFinding:
    payload = {
        "schema_version": 1,
        "manifest_id": manifest.manifest_id,
        "manifest_sha256": manifest.manifest_sha256,
        "pair_id": pair_id,
        "finding_type": finding_type,
        "severity": severity,
        "canonical_path": canonical_path,
        "runtime_path": runtime_path,
        "disposition": disposition,
        "canonical_body_sha256": canonical_body_sha256,
        "runtime_body_sha256": runtime_body_sha256,
    }
    return FrameworkPairFinding(
        payload=payload,
        finding_digest=_sha256_text(_canonical_json(payload)),
    )


def _framework_finding_identity(payload: dict[str, Any]) -> str:
    """Stable identity of a finding, independent of its evidence fields.

    `finding_digest` remains the tamper seal over the entire payload and is
    what authenticates a receipt. Deduplication uses this instead, so an
    unchanged problem is recognised across manifest revisions and across
    edits to the bodies it reports on. Legacy receipts need no migration:
    their identity is derived from the payload they already carry.
    """
    identity = {
        key: value
        for key, value in payload.items()
        if key not in FRAMEWORK_FINDING_EVIDENCE_FIELDS
    }
    return _sha256_text(_canonical_json(identity))


def _registered_framework_keys(ora_root: Path) -> set[str]:
    """Read the one authority for callable and picker-visible frameworks."""
    path = _bounded_repo_path(
        ora_root,
        "config/framework-invocability.json",
    )
    if not path.is_file():
        raise FrameworkManifestError(
            "framework invocability authority is missing: "
            "config/framework-invocability.json"
        )
    try:
        document = json.loads(read_file(path))
    except (OSError, json.JSONDecodeError) as exc:
        raise FrameworkManifestError(
            f"framework invocability authority is invalid: {exc}"
        ) from exc
    if not isinstance(document, dict):
        raise FrameworkManifestError(
            "framework invocability authority must be a JSON object"
        )

    def key(value: Any) -> str:
        if not isinstance(value, str):
            raise FrameworkManifestError(
                "framework invocability entries must be strings"
            )
        name = Path(value.strip()).name
        return (name[:-3] if name.endswith(".md") else name).lower()

    registered: set[str] = set()
    for field_name in ("invocable_frameworks", "pickable_frameworks"):
        values = document.get(field_name, [])
        if not isinstance(values, list):
            raise FrameworkManifestError(
                f"framework invocability {field_name} must be a list"
            )
        registered.update(key(value) for value in values)
    aliases = document.get("aliases", {})
    if not isinstance(aliases, dict):
        raise FrameworkManifestError("framework invocability aliases must be an object")
    for alias, target in aliases.items():
        registered.add(key(alias))
        registered.add(key(target))
    return registered


def _has_visible_specified_not_built_banner(body: str, banner: str) -> bool:
    """Match the approved standalone banner in the document preamble.

    The lifecycle marker is a visible blockquote near the beginning of the
    canonical, not a sentence that happens to be quoted in a later design or
    history section.  The preamble ends at the first visible H2.  Fenced
    examples and HTML comments do not count as visible lifecycle state.
    """
    fence_character: Optional[str] = None
    fence_length = 0
    in_html_comment = False

    for raw_line in body.splitlines():
        if fence_character is not None:
            if re.fullmatch(
                rf"[ \t]{{0,3}}{re.escape(fence_character)}"
                rf"{{{fence_length},}}[ \t]*",
                raw_line,
            ):
                fence_character = None
                fence_length = 0
            continue

        visible_parts: list[str] = []
        cursor = 0
        while cursor < len(raw_line):
            if in_html_comment:
                comment_end = raw_line.find("-->", cursor)
                if comment_end < 0:
                    cursor = len(raw_line)
                    break
                in_html_comment = False
                cursor = comment_end + 3
                continue
            comment_start = raw_line.find("<!--", cursor)
            if comment_start < 0:
                visible_parts.append(raw_line[cursor:])
                break
            visible_parts.append(raw_line[cursor:comment_start])
            in_html_comment = True
            cursor = comment_start + 4

        line = "".join(visible_parts).rstrip()
        fence_match = re.match(r"^[ \t]{0,3}(`{3,}|~{3,})", line)
        if fence_match:
            fence = fence_match.group(1)
            fence_character = fence[0]
            fence_length = len(fence)
            continue
        if re.match(r"^[ \t]{0,3}##(?:[ \t]+|$)", line):
            break
        if line == banner:
            return True
    return False


def evaluate_framework_pair_manifest(
    *,
    manifest_path: Optional[Path] = None,
    vault_root: Optional[Path] = None,
    ora_root: Optional[Path] = None,
) -> FrameworkPairEvaluation:
    vault = (vault_root or VAULT_ROOT).resolve()
    ora = (ora_root or ORA_ROOT).resolve()
    manifest = load_framework_pair_manifest(manifest_path)
    findings: list[FrameworkPairFinding] = []
    paired_clean = 0
    paired_drifted = 0
    missing_runtime = 0
    no_runtime_twin = 0
    specified_not_built = 0
    invocability_keys: Optional[set[str]] = None
    invocability_unverifiable = False

    registered_runtime_paths = {
        entry.runtime_path
        for entry in manifest.entries
        if entry.runtime_path is not None
    }
    registered_framework_canonicals = {
        entry.canonical_path
        for entry in manifest.entries
        if Path(entry.canonical_path).name.startswith("Framework — ")
    }

    for entry in manifest.entries:
        canonical = _bounded_repo_path(vault, entry.canonical_path)
        runtime = (
            _bounded_repo_path(ora, entry.runtime_path)
            if entry.runtime_path
            else None
        )
        if not canonical.is_file():
            findings.append(
                _framework_finding(
                    manifest,
                    pair_id=entry.pair_id,
                    finding_type="canonical_missing",
                    severity="load-bearing",
                    canonical_path=entry.canonical_path,
                    runtime_path=entry.runtime_path,
                    disposition=entry.disposition,
                    canonical_body_sha256=None,
                    runtime_body_sha256=None,
                )
            )
            continue
        canonical_body = _normalized_framework_body(
            canonical, strip_vault_yaml=True
        )
        canonical_digest = _sha256_text(canonical_body)
        if entry.disposition == "no_runtime_twin":
            no_runtime_twin += 1
            continue
        assert runtime is not None
        if entry.disposition == "specified_not_built":
            specified_not_built += 1
            required_banner = (
                SPECIFIED_NOT_BUILT_DCP_BANNER
                if entry.canonical_path.endswith(
                    "Framework — Documentation-Code Parity.md"
                )
                else SPECIFIED_NOT_BUILT_BANNER
            )
            if not _has_visible_specified_not_built_banner(
                canonical_body, required_banner
            ):
                findings.append(
                    _framework_finding(
                        manifest,
                        pair_id=entry.pair_id,
                        finding_type="specified_not_built_banner_missing",
                        severity="load-bearing",
                        canonical_path=entry.canonical_path,
                        runtime_path=entry.runtime_path,
                        disposition=entry.disposition,
                        canonical_body_sha256=canonical_digest,
                        runtime_body_sha256=None,
                    )
                )
            if runtime.is_file():
                runtime_digest = _sha256_text(
                    _normalized_framework_body(runtime, strip_vault_yaml=False)
                )
                findings.append(
                    _framework_finding(
                        manifest,
                        pair_id=entry.pair_id,
                        finding_type="specified_not_built_runtime_present",
                        severity="load-bearing",
                        canonical_path=entry.canonical_path,
                        runtime_path=entry.runtime_path,
                        disposition=entry.disposition,
                        canonical_body_sha256=canonical_digest,
                        runtime_body_sha256=runtime_digest,
                    )
                )
            if invocability_keys is None:
                try:
                    invocability_keys = _registered_framework_keys(ora)
                except FrameworkManifestError:
                    invocability_unverifiable = True
                    invocability_keys = set()
            if invocability_unverifiable:
                findings.append(
                    _framework_finding(
                        manifest,
                        pair_id=entry.pair_id,
                        finding_type=(
                            "specified_not_built_invocability_unverifiable"
                        ),
                        severity="load-bearing",
                        canonical_path=entry.canonical_path,
                        runtime_path=entry.runtime_path,
                        disposition=entry.disposition,
                        canonical_body_sha256=canonical_digest,
                        runtime_body_sha256=None,
                    )
                )
            runtime_key = Path(entry.runtime_path).stem.lower()
            if runtime_key in invocability_keys:
                findings.append(
                    _framework_finding(
                        manifest,
                        pair_id=entry.pair_id,
                        finding_type="specified_not_built_registered",
                        severity="load-bearing",
                        canonical_path=entry.canonical_path,
                        runtime_path=entry.runtime_path,
                        disposition=entry.disposition,
                        canonical_body_sha256=canonical_digest,
                        runtime_body_sha256=None,
                    )
                )
            continue
        if entry.disposition == "missing_runtime":
            missing_runtime += 1
            if runtime.is_file():
                runtime_digest = _sha256_text(
                    _normalized_framework_body(runtime, strip_vault_yaml=False)
                )
                finding_type = "unapproved_runtime_twin_present"
            else:
                runtime_digest = None
                finding_type = "missing_runtime_twin"
            findings.append(
                _framework_finding(
                    manifest,
                    pair_id=entry.pair_id,
                    finding_type=finding_type,
                    severity="missing-feature",
                    canonical_path=entry.canonical_path,
                    runtime_path=entry.runtime_path,
                    disposition=entry.disposition,
                    canonical_body_sha256=canonical_digest,
                    runtime_body_sha256=runtime_digest,
                )
            )
            continue
        for banner in SPECIFIED_NOT_BUILT_BANNERS:
            if _has_visible_specified_not_built_banner(canonical_body, banner):
                findings.append(
                    _framework_finding(
                        manifest,
                        pair_id=entry.pair_id,
                        finding_type="paired_carries_specified_not_built_banner",
                        severity="load-bearing",
                        canonical_path=entry.canonical_path,
                        runtime_path=entry.runtime_path,
                        disposition=entry.disposition,
                        canonical_body_sha256=canonical_digest,
                        runtime_body_sha256=None,
                    )
                )
                break
        if not runtime.is_file():
            findings.append(
                _framework_finding(
                    manifest,
                    pair_id=entry.pair_id,
                    finding_type="paired_runtime_missing",
                    severity="load-bearing",
                    canonical_path=entry.canonical_path,
                    runtime_path=entry.runtime_path,
                    disposition=entry.disposition,
                    canonical_body_sha256=canonical_digest,
                    runtime_body_sha256=None,
                )
            )
            continue
        runtime_body = _normalized_framework_body(runtime, strip_vault_yaml=False)
        runtime_digest = _sha256_text(runtime_body)
        if canonical_body != runtime_body:
            paired_drifted += 1
            findings.append(
                _framework_finding(
                    manifest,
                    pair_id=entry.pair_id,
                    finding_type="normalized_body_drift",
                    severity=entry.finding_severity,
                    canonical_path=entry.canonical_path,
                    runtime_path=entry.runtime_path,
                    disposition=entry.disposition,
                    canonical_body_sha256=canonical_digest,
                    runtime_body_sha256=runtime_digest,
                )
            )
        else:
            paired_clean += 1

    actual_runtime_paths = {
        path.relative_to(ora).as_posix()
        for path in (ora / "frameworks").rglob("*.md")
        if path.relative_to(ora).as_posix() not in FRAMEWORK_RUNTIME_EXCLUSIONS
        and not path.relative_to(ora).as_posix().startswith(
            FRAMEWORK_RUNTIME_EXCLUDED_DIRS
        )
    }
    for runtime_path in sorted(actual_runtime_paths - registered_runtime_paths):
        runtime = _bounded_repo_path(ora, runtime_path)
        findings.append(
            _framework_finding(
                manifest,
                pair_id=f"unregistered-runtime:{_sha256_text(runtime_path)[:16]}",
                finding_type="unregistered_runtime_framework",
                severity="load-bearing",
                canonical_path=None,
                runtime_path=runtime_path,
                disposition="unregistered",
                canonical_body_sha256=None,
                runtime_body_sha256=_sha256_text(
                    _normalized_framework_body(runtime, strip_vault_yaml=False)
                ),
            )
        )

    actual_framework_canonicals = {
        path.relative_to(vault).as_posix()
        for root in (vault / "Projects" / "Ora", vault / "Projects" / "MSI")
        if root.is_dir()
        for path in root.glob("Framework — *.md")
    }
    for canonical_path in sorted(
        actual_framework_canonicals - registered_framework_canonicals
    ):
        canonical = _bounded_repo_path(vault, canonical_path)
        findings.append(
            _framework_finding(
                manifest,
                pair_id=f"unregistered-canonical:{_sha256_text(canonical_path)[:16]}",
                finding_type="unregistered_canonical_framework",
                severity="load-bearing",
                canonical_path=canonical_path,
                runtime_path=None,
                disposition="unregistered",
                canonical_body_sha256=_sha256_text(
                    _normalized_framework_body(canonical, strip_vault_yaml=True)
                ),
                runtime_body_sha256=None,
            )
        )

    findings.sort(
        key=lambda finding: (
            0 if finding.payload["finding_type"] == "missing_runtime_twin" else 1,
            finding.payload["canonical_path"] or "",
            finding.payload["runtime_path"] or "",
        )
    )
    return FrameworkPairEvaluation(
        manifest=manifest,
        findings=tuple(findings),
        paired_clean=paired_clean,
        paired_drifted=paired_drifted,
        missing_runtime=missing_runtime,
        no_runtime_twin=no_runtime_twin,
        specified_not_built=specified_not_built,
    )


def check_framework_pair_manifest(verbose: bool = False) -> CheckResult:
    """Verify complete manifest coverage and exact normalized-body parity."""
    result = CheckResult(name="framework-pairs", passed=True)
    try:
        evaluation = evaluate_framework_pair_manifest()
    except (OSError, FrameworkManifestError) as exc:
        result.passed = False
        result.details.append(f"Manifest integrity failure: {exc}")
        return result
    if evaluation.findings:
        result.passed = False
        for finding in evaluation.findings:
            payload = finding.payload
            result.details.append(
                f"{payload['finding_type']}: {payload['pair_id']} "
                f"[{payload['severity']}; receipt={finding.finding_digest}]"
            )
    if verbose:
        result.details.insert(
            0,
            "Manifest "
            f"{evaluation.manifest.manifest_id} "
            f"sha256={evaluation.manifest.manifest_sha256}; "
            f"paired clean={evaluation.paired_clean}, "
            f"paired drifted={evaluation.paired_drifted}, "
            f"missing twins={evaluation.missing_runtime}, "
            f"specified-not-built={evaluation.specified_not_built}, "
            f"no-twin={evaluation.no_runtime_twin}, "
            f"findings={len(evaluation.findings)}",
        )
    return result


# ---------------------------------------------------------------------------
# Focused documentation-integrity gate
# ---------------------------------------------------------------------------

def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DocumentationIntegrityError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_markdown_json_block(
    content: str,
    *,
    begin: str,
    end: str,
    label: str,
) -> dict[str, Any]:
    if content.count(begin) != 1 or content.count(end) != 1:
        raise DocumentationIntegrityError(
            f"{label} must contain exactly one authenticated JSON block"
        )
    start = content.index(begin) + len(begin)
    finish = content.index(end, start)
    fenced = content[start:finish].strip()
    match = re.fullmatch(r"```json\s*\n(.*?)\n```", fenced, re.DOTALL)
    if not match:
        raise DocumentationIntegrityError(f"{label} JSON block has invalid fencing")
    try:
        document = json.loads(
            match.group(1), object_pairs_hook=_unique_json_object
        )
    except (json.JSONDecodeError, DocumentationIntegrityError) as exc:
        raise DocumentationIntegrityError(f"{label} JSON is invalid: {exc}") from exc
    if not isinstance(document, dict):
        raise DocumentationIntegrityError(f"{label} JSON root must be an object")
    return document


def _documentation_relative_path(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise DocumentationIntegrityError(f"{field_name} must be a nonempty string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise DocumentationIntegrityError(
            f"{field_name} must be a normalized repository-relative path: {value!r}"
        )
    return value


def _parse_documentation_reference(
    raw: Any, *, label: str
) -> DocumentationReference:
    if not isinstance(raw, dict):
        raise DocumentationIntegrityError(f"{label} must be an object")
    reference_type = raw.get("type")
    if reference_type not in DOCUMENTATION_REFERENCE_TYPES:
        raise DocumentationIntegrityError(
            f"{label} has unsupported reference type: {reference_type!r}"
        )
    expected = {"type", "repository", "path"}
    value_field: Optional[str] = None
    if reference_type != "path":
        value_field = reference_type
        expected.add(reference_type)
    if set(raw) != expected:
        raise DocumentationIntegrityError(
            f"{label} fields differ from the {reference_type} contract"
        )
    repository = raw["repository"]
    if repository not in DOCUMENTATION_REPOSITORIES:
        raise DocumentationIntegrityError(
            f"{label} names an unknown repository: {repository!r}"
        )
    path = _documentation_relative_path(raw["path"], field_name=f"{label}.path")
    value: Optional[str] = None
    if value_field:
        raw_value = raw[value_field]
        if not isinstance(raw_value, str) or not raw_value:
            raise DocumentationIntegrityError(
                f"{label}.{value_field} must be a nonempty string"
            )
        value = raw_value
    return DocumentationReference(
        reference_type=reference_type,
        repository=repository,
        path=path,
        value=value,
    )


def _parse_documentation_repository_identity(
    raw: Any, *, label: str
) -> DocumentationRepositoryIdentity:
    if not isinstance(raw, dict) or set(raw) != {"identity"}:
        raise DocumentationIntegrityError(
            f"{label} fields differ from the repository identity contract"
        )
    identity = raw["identity"]
    if not isinstance(identity, dict) or set(identity) != {
        "type",
        "remote",
        "value",
    }:
        raise DocumentationIntegrityError(
            f"{label}.identity fields differ from the locked schema"
        )
    if identity["type"] != "git_remote":
        raise DocumentationIntegrityError(
            f"{label}.identity.type must equal 'git_remote'"
        )
    for field_name in ("remote", "value"):
        value = identity[field_name]
        if not isinstance(value, str) or not value.strip():
            raise DocumentationIntegrityError(
                f"{label}.identity.{field_name} must be a nonempty string"
            )
    return DocumentationRepositoryIdentity(
        remote=identity["remote"],
        value=identity["value"],
    )


def _parse_documentation_discovery_source(
    raw: Any, *, label: str
) -> DocumentationDiscoverySource:
    if not isinstance(raw, dict):
        raise DocumentationIntegrityError(f"{label} must be an object")
    source_type = raw.get("type")
    if source_type not in DOCUMENTATION_DISCOVERY_TYPES:
        raise DocumentationIntegrityError(
            f"{label} has unsupported discovery type: {source_type!r}"
        )
    common = {"source_id", "type", "repository", "associations"}
    if source_type == "tracked_glob":
        expected = common | {"glob"}
    elif source_type == "json_catalog":
        expected = common | {"path", "pointer", "item_field"}
    else:
        expected = common | {"path", "pattern"}
    if set(raw) != expected:
        raise DocumentationIntegrityError(
            f"{label} fields differ from the {source_type} contract"
        )

    source_id = raw["source_id"]
    if not isinstance(source_id, str) or not re.fullmatch(
        r"[a-z0-9][a-z0-9._:-]*", source_id
    ):
        raise DocumentationIntegrityError(f"{label}.source_id is invalid")
    repository = raw["repository"]
    if repository not in DOCUMENTATION_REPOSITORIES:
        raise DocumentationIntegrityError(f"{label}.repository is invalid")

    associations_raw = raw["associations"]
    if not isinstance(associations_raw, list) or not associations_raw:
        raise DocumentationIntegrityError(
            f"{label}.associations must be a nonempty list"
        )
    associations: list[DocumentationDiscoveryAssociation] = []
    association_keys: set[tuple[str, str]] = set()
    for index, association_raw in enumerate(associations_raw):
        association_label = f"{label}.associations[{index}]"
        if not isinstance(association_raw, dict) or set(association_raw) != {
            "pattern",
            "surface_id",
        }:
            raise DocumentationIntegrityError(
                f"{association_label} fields differ from the locked schema"
            )
        pattern = association_raw["pattern"]
        surface_id = association_raw["surface_id"]
        if not isinstance(pattern, str) or not pattern:
            raise DocumentationIntegrityError(
                f"{association_label}.pattern must be a nonempty string"
            )
        if not isinstance(surface_id, str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9._:-]*", surface_id
        ):
            raise DocumentationIntegrityError(
                f"{association_label}.surface_id is invalid"
            )
        key = (pattern, surface_id)
        if key in association_keys:
            raise DocumentationIntegrityError(
                f"duplicate discovery association in {label}: {key}"
            )
        association_keys.add(key)
        associations.append(DocumentationDiscoveryAssociation(pattern, surface_id))

    path: Optional[str] = None
    item_field: Optional[str] = None
    if source_type == "tracked_glob":
        selector = _documentation_relative_path(
            raw["glob"], field_name=f"{label}.glob"
        )
    else:
        path = _documentation_relative_path(
            raw["path"], field_name=f"{label}.path"
        )
        if source_type == "json_catalog":
            selector = raw["pointer"]
            if not isinstance(selector, str) or (
                selector and not selector.startswith("/")
            ):
                raise DocumentationIntegrityError(
                    f"{label}.pointer must be an empty or absolute JSON pointer"
                )
            item_field = raw["item_field"]
            if item_field is not None and (
                not isinstance(item_field, str)
                or not re.fullmatch(r"[A-Za-z0-9_.:-]+", item_field)
            ):
                raise DocumentationIntegrityError(
                    f"{label}.item_field must be null or a simple field name"
                )
        else:
            selector = raw["pattern"]
            if not isinstance(selector, str) or not selector:
                raise DocumentationIntegrityError(
                    f"{label}.pattern must be a nonempty regex"
                )
            if len(selector) > 1_000:
                raise DocumentationIntegrityError(
                    f"{label}.pattern exceeds the bounded regex size"
                )
            try:
                compiled = re.compile(selector, re.MULTILINE)
            except re.error as exc:
                raise DocumentationIntegrityError(
                    f"{label}.pattern is invalid: {exc}"
                ) from exc
            if "item" not in compiled.groupindex:
                raise DocumentationIntegrityError(
                    f"{label}.pattern must define a named 'item' capture"
                )

    return DocumentationDiscoverySource(
        source_id=source_id,
        source_type=source_type,
        repository=repository,
        path=path,
        selector=selector,
        item_field=item_field,
        associations=tuple(associations),
    )


def _parse_documentation_propagation(raw: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise DocumentationIntegrityError(f"{label} must be an object")
    propagation_type = raw.get("type")
    if propagation_type not in DOCUMENTATION_PROPAGATION_TYPES:
        raise DocumentationIntegrityError(
            f"{label} has unsupported propagation type: {propagation_type!r}"
        )
    if propagation_type == "none":
        expected = {"type"}
    elif propagation_type == "ora_body_only":
        expected = {"type", "repository", "path"}
        if raw.get("repository") != "ora":
            raise DocumentationIntegrityError(
                f"{label} ora_body_only target must be the Ora repository"
            )
        _documentation_relative_path(raw.get("path"), field_name=f"{label}.path")
    elif propagation_type == "framework_pair":
        expected = {"type", "pair_id"}
        if not isinstance(raw.get("pair_id"), str) or not raw["pair_id"]:
            raise DocumentationIntegrityError(f"{label}.pair_id is required")
    else:
        expected = {"type", "repository", "script", "arguments"}
        if raw.get("repository") != "app":
            raise DocumentationIntegrityError(
                f"{label} site_reverse_parity must use the app publisher"
            )
        script = _documentation_relative_path(
            raw.get("script"), field_name=f"{label}.script"
        )
        if not script.endswith(".mjs"):
            raise DocumentationIntegrityError(
                f"{label}.script must name the registered Node .mjs checker"
            )
        arguments = raw.get("arguments")
        if (
            not isinstance(arguments, list)
            or any(not isinstance(value, str) for value in arguments)
        ):
            raise DocumentationIntegrityError(
                f"{label}.arguments must be a list of strings"
            )
        joined = "\n".join(arguments)
        for required in ("vault", "app", "org", "msi"):
            if "{" + required + "_root}" not in joined:
                raise DocumentationIntegrityError(
                    f"{label}.arguments must forward {{{required}_root}}"
                )
        if any(value in {"--write", "--fix", "--update"} for value in arguments):
            raise DocumentationIntegrityError(
                f"{label} must be verification-only, not a generator"
            )
    if set(raw) != expected:
        raise DocumentationIntegrityError(f"{label} fields differ from its contract")
    return dict(raw)


def _parse_documentation_ownership_registry(
    content: str,
    *,
    label: str,
) -> DocumentationOwnershipRegistry:
    document = _load_markdown_json_block(
        content,
        begin=DOCUMENTATION_OWNERSHIP_BEGIN,
        end=DOCUMENTATION_OWNERSHIP_END,
        label=label,
    )
    if set(document) != {
        "schema_version",
        "registry_id",
        "repositories",
        "discovery",
        "surfaces",
    }:
        raise DocumentationIntegrityError(
            "documentation ownership/discovery root fields differ from the locked schema"
        )
    if document["schema_version"] != 1:
        raise DocumentationIntegrityError(
            "documentation ownership/discovery schema_version must equal 1"
        )
    if document["registry_id"] != DOCUMENTATION_OWNERSHIP_ID:
        raise DocumentationIntegrityError(
            f"documentation ownership registry_id must equal {DOCUMENTATION_OWNERSHIP_ID!r}"
        )
    repositories_raw = document["repositories"]
    if not isinstance(repositories_raw, dict) or set(repositories_raw) != set(
        DOCUMENTATION_REPOSITORIES
    ):
        raise DocumentationIntegrityError(
            "documentation ownership repositories must declare identities for "
            "vault, ora, app, org, and msi exactly"
        )
    repository_identities = {
        repository: _parse_documentation_repository_identity(
            repositories_raw[repository],
            label=f"repositories.{repository}",
        )
        for repository in DOCUMENTATION_REPOSITORIES
    }
    discovery_raw = document["discovery"]
    if not isinstance(discovery_raw, dict) or set(discovery_raw) != DOCUMENTATION_SURFACE_CLASSES:
        raise DocumentationIntegrityError(
            "documentation discovery must name all four surface classes exactly"
        )
    discovery: dict[str, tuple[DocumentationDiscoverySource, ...]] = {}
    discovery_source_ids: set[str] = set()
    source_count = 0
    for surface_class, raw_sources in discovery_raw.items():
        if not isinstance(raw_sources, list) or not raw_sources:
            raise DocumentationIntegrityError(
                f"documentation discovery {surface_class} must be a nonempty list"
            )
        sources: list[DocumentationDiscoverySource] = []
        for index, raw in enumerate(raw_sources):
            source = _parse_documentation_discovery_source(
                raw, label=f"discovery.{surface_class}[{index}]"
            )
            if source.source_id in discovery_source_ids:
                raise DocumentationIntegrityError(
                    f"duplicate discovery source_id: {source.source_id}"
                )
            discovery_source_ids.add(source.source_id)
            sources.append(source)
            source_count += 1
        discovery[surface_class] = tuple(sources)
    if source_count > DOCUMENTATION_DISCOVERY_MAX_SOURCES:
        raise DocumentationIntegrityError(
            "documentation discovery exceeds the bounded source count"
        )

    raw_surfaces = document["surfaces"]
    if not isinstance(raw_surfaces, list) or not raw_surfaces:
        raise DocumentationIntegrityError("documentation surfaces must be a nonempty list")
    surfaces: list[DocumentationSurface] = []
    surface_ids: set[str] = set()
    owner_keys: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(raw_surfaces):
        label = f"surfaces[{index}]"
        if not isinstance(raw, dict) or set(raw) != {
            "surface_id",
            "class",
            "owners",
            "canonical",
            "propagation",
            "consumers",
            "references",
        }:
            raise DocumentationIntegrityError(
                f"{label} fields differ from the locked schema"
            )
        surface_id = raw["surface_id"]
        if not isinstance(surface_id, str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9._:-]*", surface_id
        ):
            raise DocumentationIntegrityError(f"{label}.surface_id is invalid")
        if surface_id in surface_ids:
            raise DocumentationIntegrityError(f"duplicate surface_id: {surface_id}")
        surface_ids.add(surface_id)
        surface_class = raw["class"]
        if surface_class not in DOCUMENTATION_SURFACE_CLASSES:
            raise DocumentationIntegrityError(f"{label}.class is invalid")
        owners_raw = raw["owners"]
        if not isinstance(owners_raw, list) or not owners_raw:
            raise DocumentationIntegrityError(f"{label}.owners must be nonempty")
        owners: list[DocumentationOwner] = []
        for owner_index, owner_raw in enumerate(owners_raw):
            owner_label = f"{label}.owners[{owner_index}]"
            if not isinstance(owner_raw, dict) or set(owner_raw) != {
                "repository",
                "pattern",
            }:
                raise DocumentationIntegrityError(
                    f"{owner_label} fields differ from the locked schema"
                )
            repository = owner_raw["repository"]
            if repository not in DOCUMENTATION_REPOSITORIES:
                raise DocumentationIntegrityError(
                    f"{owner_label}.repository is invalid"
                )
            pattern = _documentation_relative_path(
                owner_raw["pattern"], field_name=f"{owner_label}.pattern"
            )
            owner_key = (surface_id, repository, pattern)
            if owner_key in owner_keys:
                raise DocumentationIntegrityError(
                    f"duplicate documentation owner pattern: {owner_key}"
                )
            owner_keys.add(owner_key)
            owners.append(DocumentationOwner(repository, pattern))
        canonical_raw = raw["canonical"]
        if not isinstance(canonical_raw, dict) or set(canonical_raw) != {
            "path",
            "section",
        }:
            raise DocumentationIntegrityError(
                f"{label}.canonical fields differ from the locked schema"
            )
        canonical_path = _documentation_relative_path(
            canonical_raw["path"], field_name=f"{label}.canonical.path"
        )
        canonical_section = canonical_raw["section"]
        if canonical_section is not None and (
            not isinstance(canonical_section, str) or not canonical_section.strip()
        ):
            raise DocumentationIntegrityError(
                f"{label}.canonical.section must be null or a nonempty string"
            )
        consumers_raw = raw["consumers"]
        if (
            not isinstance(consumers_raw, list)
            or any(not isinstance(value, str) for value in consumers_raw)
            or len(consumers_raw) != len(set(consumers_raw))
        ):
            raise DocumentationIntegrityError(
                f"{label}.consumers must be a unique string list"
            )
        references_raw = raw["references"]
        if not isinstance(references_raw, list):
            raise DocumentationIntegrityError(f"{label}.references must be a list")
        references = tuple(
            _parse_documentation_reference(
                reference, label=f"{label}.references[{reference_index}]"
            )
            for reference_index, reference in enumerate(references_raw)
        )
        surfaces.append(
            DocumentationSurface(
                surface_id=surface_id,
                surface_class=surface_class,
                owners=tuple(owners),
                canonical_path=canonical_path,
                canonical_section=canonical_section,
                propagation=_parse_documentation_propagation(
                    raw["propagation"], label=f"{label}.propagation"
                ),
                consumers=tuple(consumers_raw),
                references=references,
            )
        )
    for surface in surfaces:
        unknown = set(surface.consumers) - surface_ids
        if unknown:
            raise DocumentationIntegrityError(
                f"surface {surface.surface_id} names unknown consumers: {sorted(unknown)}"
            )
        if surface.surface_id in surface.consumers:
            raise DocumentationIntegrityError(
                f"surface {surface.surface_id} cannot consume itself"
            )
    surfaces_by_id = {surface.surface_id: surface for surface in surfaces}
    for surface_class, sources in discovery.items():
        for source in sources:
            for association in source.associations:
                surface = surfaces_by_id.get(association.surface_id)
                if surface is None:
                    raise DocumentationIntegrityError(
                        f"discovery source {source.source_id} associates with unknown "
                        f"surface {association.surface_id}"
                    )
                if surface.surface_class != surface_class:
                    raise DocumentationIntegrityError(
                        f"discovery source {source.source_id} class {surface_class} "
                        f"cannot associate with {surface.surface_id} class "
                        f"{surface.surface_class}"
                    )
    return DocumentationOwnershipRegistry(
        surfaces=tuple(surfaces),
        discovery=discovery,
        repository_identities=repository_identities,
    )


def load_documentation_ownership_registry(
    configuration_path: Path,
) -> DocumentationOwnershipRegistry:
    return _parse_documentation_ownership_registry(
        read_file(configuration_path),
        label="documentation ownership/discovery",
    )


def _parse_documentation_accepted_findings(
    content: str,
    *,
    label: str,
) -> tuple[DocumentationAcceptedFinding, ...]:
    document = _load_markdown_json_block(
        content,
        begin=DOCUMENTATION_ACCEPTED_FINDINGS_BEGIN,
        end=DOCUMENTATION_ACCEPTED_FINDINGS_END,
        label=label,
    )
    if set(document) != {"schema_version", "baseline_id", "findings"}:
        raise DocumentationIntegrityError(
            "documentation accepted-findings root fields differ from the locked schema"
        )
    if document["schema_version"] != 1:
        raise DocumentationIntegrityError(
            "documentation accepted-findings schema_version must equal 1"
        )
    if document["baseline_id"] != DOCUMENTATION_ACCEPTED_FINDINGS_ID:
        raise DocumentationIntegrityError(
            f"documentation baseline_id must equal {DOCUMENTATION_ACCEPTED_FINDINGS_ID!r}"
        )
    raw_findings = document["findings"]
    if not isinstance(raw_findings, list):
        raise DocumentationIntegrityError(
            "documentation accepted findings must be a list"
        )
    findings: list[DocumentationAcceptedFinding] = []
    identities: set[tuple[Any, ...]] = set()
    anchors: set[tuple[str, str]] = set()
    for index, raw in enumerate(raw_findings):
        label = f"accepted-findings[{index}]"
        if not isinstance(raw, dict) or set(raw) != {
            "finding_type",
            "pair_id",
            "canonical_path",
            "runtime_path",
            "disposition",
            "severity",
            "owner",
            "repository_commits",
        }:
            raise DocumentationIntegrityError(
                f"{label} fields differ from the locked schema"
            )
        for field_name in (
            "finding_type",
            "pair_id",
            "disposition",
            "severity",
            "owner",
        ):
            if not isinstance(raw[field_name], str) or not raw[field_name]:
                raise DocumentationIntegrityError(
                    f"{label}.{field_name} must be a nonempty string"
                )
        for field_name in ("canonical_path", "runtime_path"):
            value = raw[field_name]
            if value is not None:
                _documentation_relative_path(
                    value, field_name=f"{label}.{field_name}"
                )
        commits = raw["repository_commits"]
        if not isinstance(commits, dict) or set(commits) != set(
            DOCUMENTATION_REPOSITORIES
        ):
            raise DocumentationIntegrityError(
                f"{label}.repository_commits must name all five repositories"
            )
        for repository, commit in commits.items():
            if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
                raise DocumentationIntegrityError(
                    f"{label}.repository_commits.{repository} must be a full commit SHA"
                )
        identity = (
            raw["finding_type"],
            raw["pair_id"],
            raw["canonical_path"],
            raw["runtime_path"],
            raw["disposition"],
            raw["severity"],
        )
        if identity in identities:
            raise DocumentationIntegrityError(
                f"duplicate accepted framework finding: {raw['pair_id']}"
            )
        identities.add(identity)
        anchor = (raw["finding_type"], raw["pair_id"])
        if anchor in anchors:
            raise DocumentationIntegrityError(
                f"accepted finding anchor is not unique: {anchor}"
            )
        anchors.add(anchor)
        protected_owner = PROTECTED_FRAMEWORK_FINDING_OWNERS.get(
            (raw["finding_type"], raw["pair_id"])
        )
        if protected_owner and raw["owner"] != protected_owner:
            raise DocumentationIntegrityError(
                f"{raw['pair_id']} remains owned by {protected_owner}, not {raw['owner']}"
            )
        findings.append(
            DocumentationAcceptedFinding(
                finding_type=raw["finding_type"],
                pair_id=raw["pair_id"],
                canonical_path=raw["canonical_path"],
                runtime_path=raw["runtime_path"],
                disposition=raw["disposition"],
                severity=raw["severity"],
                owner=raw["owner"],
                repository_commits=dict(commits),
            )
        )
    return tuple(findings)


def load_documentation_accepted_findings(
    configuration_path: Path,
) -> tuple[DocumentationAcceptedFinding, ...]:
    return _parse_documentation_accepted_findings(
        read_file(configuration_path),
        label="documentation accepted findings",
    )


def _framework_body_digest_at_commit(
    *,
    root: Path,
    commit: str,
    relative_path: Optional[str],
    strip_vault_yaml: bool,
    repository_name: str,
) -> Optional[str]:
    if relative_path is None:
        return None
    state = DocumentationRepositoryState(
        name=repository_name,
        root=root,
        base_commit=commit,
        head_commit=commit,
        changed_paths=(),
    )
    content = _git_blob_at_revision(
        state,
        relative_path,
        commit,
        revision_label="accepted-finding pin",
    )
    if content is None:
        return None
    normalized = _normalized_framework_content(
        content,
        strip_vault_yaml=strip_vault_yaml,
        label=f"{repository_name}:{commit}:{relative_path}",
    )
    return _sha256_text(normalized)


def _is_exact_accepted_external_finding(
    finding: FrameworkPairFinding,
    accepted: DocumentationAcceptedFinding,
    *,
    vault_root: Path,
    ora_root: Path,
) -> bool:
    payload = finding.payload
    if (
        payload.get("finding_type"),
        payload.get("pair_id"),
        payload.get("canonical_path"),
        payload.get("runtime_path"),
        payload.get("disposition"),
        payload.get("severity"),
    ) != (
        accepted.finding_type,
        accepted.pair_id,
        accepted.canonical_path,
        accepted.runtime_path,
        accepted.disposition,
        accepted.severity,
    ):
        return False
    canonical_digest = _framework_body_digest_at_commit(
        root=vault_root,
        commit=accepted.repository_commits["vault"],
        relative_path=accepted.canonical_path,
        strip_vault_yaml=True,
        repository_name="vault",
    )
    runtime_digest = _framework_body_digest_at_commit(
        root=ora_root,
        commit=accepted.repository_commits["ora"],
        relative_path=accepted.runtime_path,
        strip_vault_yaml=False,
        repository_name="ora",
    )
    return (
        payload.get("canonical_body_sha256") == canonical_digest
        and payload.get("runtime_body_sha256") == runtime_digest
    )


def check_framework_pair_audit(verbose: bool = False) -> CheckResult:
    """Classify only the two exact external findings as audit non-failures."""
    result = CheckResult(name="framework-pairs-audit", passed=True)
    try:
        evaluation = evaluate_framework_pair_manifest()
        accepted_records = load_documentation_accepted_findings(
            DOCUMENTATION_CONFIGURATION_FILE
        )
        accepted_by_anchor = {
            (record.finding_type, record.pair_id): record
            for record in accepted_records
            if (record.finding_type, record.pair_id)
            in PROTECTED_FRAMEWORK_FINDING_OWNERS
        }
        exact_anchors: set[tuple[str, str]] = set()
        accepted_details: list[str] = []
        audit_failure_count = 0
        for finding in evaluation.findings:
            payload = finding.payload
            anchor = (payload["finding_type"], payload["pair_id"])
            accepted = accepted_by_anchor.get(anchor)
            if accepted is not None and _is_exact_accepted_external_finding(
                finding,
                accepted,
                vault_root=VAULT_ROOT,
                ora_root=ORA_ROOT,
            ):
                exact_anchors.add(anchor)
                accepted_details.append(
                    "accepted external finding: "
                    f"{accepted.finding_type}:{accepted.pair_id} "
                    f"[{accepted.owner}; receipt={finding.finding_digest}]"
                )
                continue
            result.passed = False
            audit_failure_count += 1
            result.details.append(
                "new or changed framework finding: "
                f"{payload['finding_type']}:{payload['pair_id']} "
                f"[{payload['severity']}; receipt={finding.finding_digest}]"
            )
        for anchor, accepted in sorted(accepted_by_anchor.items()):
            if anchor not in exact_anchors:
                result.passed = False
                audit_failure_count += 1
                result.details.append(
                    "accepted external finding is no longer exact: "
                    f"{accepted.finding_type}:{accepted.pair_id} [{accepted.owner}]"
                )
        result.details[:0] = accepted_details
        if verbose:
            result.details.insert(
                0,
                "Manifest "
                f"{evaluation.manifest.manifest_id} "
                f"sha256={evaluation.manifest.manifest_sha256}; "
                f"paired clean={evaluation.paired_clean}, "
                f"paired drifted={evaluation.paired_drifted}, "
                f"accepted external={len(exact_anchors)}, "
                f"audit failures={audit_failure_count}",
            )
    except (OSError, FrameworkManifestError, DocumentationIntegrityError) as exc:
        result.passed = False
        result.details.append(f"Framework-pair audit classification failure: {exc}")
    return result


def _git_read(root: Path, *arguments: str, binary: bool = False) -> str | bytes:
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    run = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=not binary,
        env=env,
    )
    if run.returncode != 0:
        error = run.stderr.decode("utf-8", "replace") if binary else run.stderr
        raise DocumentationIntegrityError(
            f"git {' '.join(arguments)} failed in {root}: {error.strip()}"
        )
    return run.stdout


def _git_blob_at_revision(
    state: DocumentationRepositoryState,
    relative_path: str,
    revision: str,
    *,
    revision_label: str,
) -> Optional[str]:
    listing = _git_read(
        state.root,
        "ls-tree",
        "-z",
        revision,
        "--",
        relative_path,
        binary=True,
    )
    assert isinstance(listing, bytes)
    records = [record for record in listing.split(b"\0") if record]
    if not records:
        return None
    if len(records) != 1:
        raise DocumentationIntegrityError(
            f"{revision_label} path is ambiguous: {state.name}:{relative_path}"
        )
    metadata, separator, listed_path = records[0].partition(b"\t")
    if not separator or listed_path.decode("utf-8") != relative_path:
        raise DocumentationIntegrityError(
            f"{revision_label} path could not be authenticated: "
            f"{state.name}:{relative_path}"
        )
    mode = metadata.split(b" ", 1)[0]
    if mode not in {b"100644", b"100755"}:
        raise DocumentationIntegrityError(
            f"{revision_label} path is not a regular tracked file: "
            f"{state.name}:{relative_path}"
        )
    content = _git_read(
        state.root,
        "show",
        f"{revision}:{relative_path}",
    )
    assert isinstance(content, str)
    return content


def _git_blob_at_commit(
    state: DocumentationRepositoryState,
    relative_path: str,
) -> Optional[str]:
    return _git_blob_at_revision(
        state,
        relative_path,
        state.base_commit,
        revision_label="pinned base",
    )


def _load_base_documentation_ownership_registry(
    vault: DocumentationRepositoryState,
    configuration_relative_path: str,
) -> Optional[DocumentationOwnershipRegistry]:
    content = _git_blob_at_commit(vault, configuration_relative_path)
    if content is None:
        return None
    begin_count = content.count(DOCUMENTATION_OWNERSHIP_BEGIN)
    end_count = content.count(DOCUMENTATION_OWNERSHIP_END)
    if begin_count == 0 and end_count == 0:
        return None
    if begin_count != 1 or end_count != 1:
        raise DocumentationIntegrityError(
            "pinned vault base has a malformed ownership/discovery block; it "
            "is not an eligible bootstrap state"
        )
    return _parse_documentation_ownership_registry(
        content,
        label="pinned-base documentation ownership/discovery",
    )


def _load_base_documentation_accepted_findings(
    vault: DocumentationRepositoryState,
    configuration_relative_path: str,
) -> Optional[tuple[DocumentationAcceptedFinding, ...]]:
    content = _git_blob_at_commit(vault, configuration_relative_path)
    if content is None:
        return None
    begin_count = content.count(DOCUMENTATION_ACCEPTED_FINDINGS_BEGIN)
    end_count = content.count(DOCUMENTATION_ACCEPTED_FINDINGS_END)
    if begin_count == 0 and end_count == 0:
        return None
    if begin_count != 1 or end_count != 1:
        raise DocumentationIntegrityError(
            "pinned vault base has a malformed accepted-finding block; it is "
            "not an eligible bootstrap state"
        )
    return _parse_documentation_accepted_findings(
        content,
        label="pinned-base documentation accepted findings",
    )


def _load_documentation_repository_states(
    roots: dict[str, Path | str],
    base_commits: dict[str, str],
) -> dict[str, DocumentationRepositoryState]:
    if set(roots) != set(DOCUMENTATION_REPOSITORIES):
        missing = sorted(set(DOCUMENTATION_REPOSITORIES) - set(roots))
        extra = sorted(set(roots) - set(DOCUMENTATION_REPOSITORIES))
        raise DocumentationIntegrityError(
            f"all five explicit roots are mandatory; missing={missing}, extra={extra}"
        )
    if set(base_commits) != set(DOCUMENTATION_REPOSITORIES):
        missing = sorted(set(DOCUMENTATION_REPOSITORIES) - set(base_commits))
        extra = sorted(set(base_commits) - set(DOCUMENTATION_REPOSITORIES))
        raise DocumentationIntegrityError(
            f"all five explicit base commits are mandatory; missing={missing}, extra={extra}"
        )
    resolved_roots: dict[str, Path] = {}
    for name in DOCUMENTATION_REPOSITORIES:
        supplied = Path(roots[name]).expanduser()
        if not supplied.is_absolute():
            raise DocumentationIntegrityError(
                f"{name} root must be an explicit absolute path"
            )
        root = supplied.resolve()
        if not root.is_dir():
            raise DocumentationIntegrityError(f"{name} root is not a directory: {root}")
        resolved_roots[name] = root
    grouped_roots: dict[Path, list[str]] = {}
    for name, root in resolved_roots.items():
        grouped_roots.setdefault(root, []).append(name)
    duplicates = {
        str(root): names
        for root, names in grouped_roots.items()
        if len(names) > 1
    }
    if duplicates:
        raise DocumentationIntegrityError(
            f"the five repository roots must be distinct; duplicates={duplicates}"
        )

    states: dict[str, DocumentationRepositoryState] = {}
    for name in DOCUMENTATION_REPOSITORIES:
        root = resolved_roots[name]
        top = str(_git_read(root, "rev-parse", "--show-toplevel")).strip()
        if Path(top).resolve() != root:
            raise DocumentationIntegrityError(
                f"{name} root is not the repository top level: {root}"
            )
        base = base_commits[name]
        if not isinstance(base, str) or not re.fullmatch(r"[0-9a-f]{40}", base):
            raise DocumentationIntegrityError(
                f"{name} base must be an explicit full commit SHA"
            )
        resolved_base = str(
            _git_read(root, "rev-parse", "--verify", f"{base}^{{commit}}")
        ).strip()
        if resolved_base != base:
            raise DocumentationIntegrityError(
                f"{name} base does not resolve to the supplied commit"
            )
        head = str(_git_read(root, "rev-parse", "--verify", "HEAD^{commit}")).strip()
        ancestor = subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", base, head],
            capture_output=True,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
        if ancestor.returncode != 0:
            raise DocumentationIntegrityError(
                f"{name} base is not an ancestor of its task HEAD"
            )
        dirty = _git_read(root, "status", "--porcelain", "-z", binary=True)
        if dirty:
            raise DocumentationIntegrityError(
                f"{name} task worktree must be clean before documentation verification"
            )
        changed = _git_read(
            root,
            "diff",
            "--no-renames",
            "--name-only",
            "--diff-filter=ACDMRTUXB",
            "-z",
            base,
            head,
            "--",
            binary=True,
        )
        assert isinstance(changed, bytes)
        changed_paths = tuple(
            sorted(
                value.decode("utf-8")
                for value in changed.split(b"\0")
                if value
            )
        )
        states[name] = DocumentationRepositoryState(
            name=name,
            root=root,
            base_commit=base,
            head_commit=head,
            changed_paths=changed_paths,
        )
    return states


def _validate_documentation_repository_identities(
    repositories: dict[str, DocumentationRepositoryState],
    identities: dict[str, DocumentationRepositoryIdentity],
) -> None:
    if set(identities) != set(DOCUMENTATION_REPOSITORIES):
        raise DocumentationIntegrityError(
            "repository identity markers must cover all five labels"
        )
    for name in DOCUMENTATION_REPOSITORIES:
        state = repositories[name]
        identity = identities[name]
        try:
            actual = str(
                _git_read(
                    state.root,
                    "config",
                    "--get",
                    f"remote.{identity.remote}.url",
                )
            ).strip()
        except DocumentationIntegrityError as exc:
            raise DocumentationIntegrityError(
                f"{name} repository identity marker could not be read from "
                f"remote {identity.remote!r}"
            ) from exc
        if actual != identity.value:
            raise DocumentationIntegrityError(
                f"{name} root does not match its declared repository identity: "
                f"remote {identity.remote!r} is {actual!r}, expected "
                f"{identity.value!r}"
            )


def _bounded_documentation_path(root: Path, relative_path: str) -> Path:
    try:
        return _bounded_repo_path(root, relative_path)
    except FrameworkManifestError as exc:
        raise DocumentationIntegrityError(str(exc)) from exc


def _documentation_pattern_specificity(pattern: str) -> tuple[int, int, int]:
    literal = sum(character not in "*?[]" for character in pattern)
    return literal, pattern.count("/") + 1, len(pattern)


def _documentation_surface_state_identity(
    surface: DocumentationSurface,
) -> tuple[Any, ...]:
    """Return the material, order-insensitive identity of one surface version."""
    return (
        surface.surface_id,
        surface.surface_class,
        tuple(sorted((owner.repository, owner.pattern) for owner in surface.owners)),
        surface.canonical_path,
        surface.canonical_section,
        _canonical_json(surface.propagation),
        tuple(sorted(surface.consumers)),
        tuple(
            sorted(
                (
                    reference.reference_type,
                    reference.repository,
                    reference.path,
                    reference.value,
                )
                for reference in surface.references
            )
        ),
    )


def _documentation_discovery_source_identity(
    surface_class: str,
    source: DocumentationDiscoverySource,
) -> tuple[Any, ...]:
    """Return the material, order-insensitive identity of one discovery rule."""
    return (
        surface_class,
        source.source_id,
        source.source_type,
        source.repository,
        source.path,
        source.selector,
        source.item_field,
        tuple(
            sorted(
                (association.pattern, association.surface_id)
                for association in source.associations
            )
        ),
    )


def _documentation_path_changed(
    state: DocumentationRepositoryState,
    path: str,
) -> bool:
    """Report a path delta even when Git represents it as one side of a rename."""
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    run = subprocess.run(
        [
            "git",
            "-C",
            str(state.root),
            "diff",
            "--quiet",
            state.base_commit,
            state.head_commit,
            "--",
            path,
        ],
        capture_output=True,
        env=env,
    )
    if run.returncode == 0:
        return False
    if run.returncode == 1:
        return True
    raise DocumentationIntegrityError(
        f"git diff --quiet failed for {state.name}:{path}: "
        f"{run.stderr.decode('utf-8', 'replace').strip()}"
    )


def _documentation_owner_for_path(
    registry: DocumentationOwnershipRegistry,
    repository: str,
    path: str,
) -> Optional[DocumentationSurface]:
    matches: list[tuple[tuple[int, int, int], DocumentationSurface]] = []
    for surface in registry.surfaces:
        for owner in surface.owners:
            if owner.repository == repository and fnmatch.fnmatchcase(
                path, owner.pattern
            ):
                matches.append(
                    (_documentation_pattern_specificity(owner.pattern), surface)
                )
    if not matches:
        return None
    strongest = max(specificity for specificity, _surface in matches)
    winners = {
        surface.surface_id: surface
        for specificity, surface in matches
        if specificity == strongest
    }
    if len(winners) != 1:
        raise DocumentationIntegrityError(
            f"ambiguous most-specific documentation owner for {repository}:{path}: "
            f"{sorted(winners)}"
        )
    return next(iter(winners.values()))


def _discovery_source_content_at_revision(
    source: DocumentationDiscoverySource,
    repositories: dict[str, DocumentationRepositoryState],
    revision: str,
    *,
    revision_label: str,
    allow_missing: bool,
) -> Optional[str]:
    assert source.path is not None
    content = _git_blob_at_revision(
        repositories[source.repository],
        source.path,
        revision,
        revision_label=revision_label,
    )
    if content is None:
        if allow_missing:
            return None
        raise DocumentationIntegrityError(
            f"declared discovery source is missing: "
            f"{source.repository}:{source.path} at {revision_label}"
        )
    if len(content.encode("utf-8")) > DOCUMENTATION_DISCOVERY_MAX_FILE_BYTES:
        raise DocumentationIntegrityError(
            f"discovery source exceeds the bounded file size: "
            f"{source.repository}:{source.path} at {revision_label}"
        )
    return content


def _json_pointer_value(document: Any, pointer: str, *, label: str) -> Any:
    current = document
    if not pointer:
        return current
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
            continue
        if isinstance(current, list) and re.fullmatch(r"0|[1-9][0-9]*", token):
            index = int(token)
            if index < len(current):
                current = current[index]
                continue
        raise DocumentationIntegrityError(
            f"{label} JSON pointer does not resolve: {pointer!r}"
        )
    return current


def _enumerate_documentation_discovery_source(
    source: DocumentationDiscoverySource,
    repositories: dict[str, DocumentationRepositoryState],
    revision: str,
    *,
    revision_label: str,
    allow_missing: bool = False,
) -> dict[str, str]:
    payloads_by_item: dict[str, list[str]] = {}

    def register(item: Any, payload: str) -> None:
        if not isinstance(item, str) or not item:
            raise DocumentationIntegrityError(
                f"discovery source {source.source_id} produced a non-string item"
            )
        payloads_by_item.setdefault(item, []).append(payload)

    if source.source_type == "tracked_glob":
        state = repositories[source.repository]
        listing = _git_read(
            state.root,
            "ls-tree",
            "-r",
            "-z",
            revision,
            "--",
            binary=True,
        )
        assert isinstance(listing, bytes)
        for raw in listing.split(b"\0"):
            if not raw:
                continue
            metadata, separator, raw_path = raw.partition(b"\t")
            fields = metadata.split(b" ")
            if not separator or len(fields) != 3:
                raise DocumentationIntegrityError(
                    f"discovery source {source.source_id} produced malformed "
                    f"tracked-tree evidence at {revision_label}"
                )
            path = raw_path.decode("utf-8")
            if fnmatch.fnmatchcase(path, source.selector):
                register(path, fields[2].decode("ascii"))
    elif source.source_type == "json_catalog":
        content = _discovery_source_content_at_revision(
            source,
            repositories,
            revision,
            revision_label=revision_label,
            allow_missing=allow_missing,
        )
        if content is None:
            return {}
        try:
            document = json.loads(
                content, object_pairs_hook=_unique_json_object
            )
        except (json.JSONDecodeError, DocumentationIntegrityError) as exc:
            raise DocumentationIntegrityError(
                f"discovery source {source.source_id} is invalid JSON at "
                f"{revision_label}: {exc}"
            ) from exc
        collection = _json_pointer_value(
            document,
            source.selector,
            label=f"discovery source {source.source_id} at {revision_label}",
        )
        if isinstance(collection, dict):
            if source.item_field is None:
                for item, payload in collection.items():
                    register(item, _canonical_json(payload))
            else:
                for payload in collection.values():
                    item = (
                        payload.get(source.item_field)
                        if isinstance(payload, dict)
                        else None
                    )
                    register(item, _canonical_json(payload))
        elif isinstance(collection, list):
            for payload in collection:
                item = (
                    payload
                    if source.item_field is None
                    else (
                        payload.get(source.item_field)
                        if isinstance(payload, dict)
                        else None
                    )
                )
                register(item, _canonical_json(payload))
        else:
            raise DocumentationIntegrityError(
                f"discovery source {source.source_id} pointer must resolve to "
                "an object or list"
            )
    else:
        content = _discovery_source_content_at_revision(
            source,
            repositories,
            revision,
            revision_label=revision_label,
            allow_missing=allow_missing,
        )
        if content is None:
            return {}
        compiled = re.compile(source.selector, re.MULTILINE)
        for match in compiled.finditer(content):
            register(match.group("item"), match.group(0))

    item_count = sum(len(payloads) for payloads in payloads_by_item.values())
    if item_count > DOCUMENTATION_DISCOVERY_MAX_ITEMS:
        raise DocumentationIntegrityError(
            f"discovery source {source.source_id} exceeds the bounded item count"
        )
    return {
        item: _sha256_text(_canonical_json(sorted(payloads)))
        for item, payloads in sorted(payloads_by_item.items())
    }


def _discovery_surface_for_item(
    source: DocumentationDiscoverySource,
    item: str,
) -> Optional[str]:
    matches = [
        (_documentation_pattern_specificity(association.pattern), association)
        for association in source.associations
        if fnmatch.fnmatchcase(item, association.pattern)
    ]
    if not matches:
        return None
    strongest = max(specificity for specificity, _association in matches)
    winners = {
        association.surface_id
        for specificity, association in matches
        if specificity == strongest
    }
    if len(winners) != 1:
        raise DocumentationIntegrityError(
            f"ambiguous discovery association for {source.source_id}:{item}: "
            f"{sorted(winners)}"
        )
    return next(iter(winners))


def _is_code_bearing_change(repository: str, path: str) -> bool:
    """Return whether an otherwise-unmapped path needs coordinated context.

    A Markdown suffix does not establish that a file is passive prose. Ora's
    installed documentation mirrors, site content collections, and many vault
    Markdown controls are consumed by machines. Complete task context resolves
    registered canonicals and derivatives through the ownership map before this
    conservative fallback is reached. Only a small set of exact top-level
    repository prose files is safe to exempt without that context.
    """
    name = Path(path).name
    if "/" not in path and name in DOCUMENTATION_STANDALONE_PROSE_FILES:
        return False
    return True


def _registered_document_surfaces_for_path(
    registry: DocumentationOwnershipRegistry,
    repository: str,
    path: str,
) -> tuple[DocumentationSurface, ...]:
    """Resolve registered documentation paths not repeated as owner globs.

    Canonical vault documents and exact body-only mirrors are already explicit
    in the ownership record. Treating them as registered paths lets complete
    task context govern them while the no-context classifier remains
    conservative. Multiple surfaces may intentionally share a derivative, so
    return every match rather than inventing a winner.
    """
    matches: dict[str, DocumentationSurface] = {}
    for surface in registry.surfaces:
        if repository == "vault" and path == surface.canonical_path:
            matches[surface.surface_id] = surface
        propagation = surface.propagation
        if (
            propagation["type"] == "ora_body_only"
            and repository == propagation["repository"]
            and path == propagation["path"]
        ):
            matches[surface.surface_id] = surface
    return tuple(matches[surface_id] for surface_id in sorted(matches))


def _markdown_has_section(content: str, section: str) -> bool:
    return _markdown_section_content(
        content,
        section,
        label="canonical markdown",
    ) is not None


def _markdown_section_content(
    content: str,
    section: str,
    *,
    label: str,
) -> Optional[str]:
    """Return one named Markdown section, including its nested subsections.

    A declared canonical section is an exact routing boundary. The section
    begins at its matching heading and ends at the next heading of the same or
    higher level. Duplicate matching headings are ambiguous and therefore
    cannot safely discharge a documentation obligation.
    """
    expected = re.sub(r"^#{1,6}\s+", "", section.strip())
    headings = list(
        re.finditer(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", content, re.MULTILINE)
    )
    matches = [
        (index, heading)
        for index, heading in enumerate(headings)
        if heading.group(2).strip() == expected
    ]
    if len(matches) > 1:
        raise DocumentationIntegrityError(
            f"{label} has ambiguous duplicate section {expected!r}"
        )
    if not matches:
        return None
    index, heading = matches[0]
    level = len(heading.group(1))
    finish = len(content)
    for following in headings[index + 1:]:
        if len(following.group(1)) <= level:
            finish = following.start()
            break
    # Separator blank lines belong to the Markdown boundary, not to either
    # named section.  Normalize only that trailing boundary so inserting a
    # following sibling section cannot falsely discharge this owner.
    return content[heading.start():finish].rstrip(" \t\r\n") + "\n"


def _documentation_canonical_changed(
    vault: DocumentationRepositoryState,
    surface: DocumentationSurface,
) -> bool:
    """Compare the declared canonical scope between the pinned base and HEAD."""
    if surface.canonical_section is None:
        return _documentation_path_changed(vault, surface.canonical_path)

    base_content = _git_blob_at_revision(
        vault,
        surface.canonical_path,
        vault.base_commit,
        revision_label="pinned base",
    )
    head_content = _git_blob_at_revision(
        vault,
        surface.canonical_path,
        vault.head_commit,
        revision_label="task HEAD",
    )
    if base_content is None or head_content is None:
        return base_content != head_content
    base_section = _markdown_section_content(
        base_content,
        surface.canonical_section,
        label=f"pinned base {surface.canonical_path}",
    )
    head_section = _markdown_section_content(
        head_content,
        surface.canonical_section,
        label=f"task HEAD {surface.canonical_path}",
    )
    return base_section != head_section


def _python_symbols(content: str) -> set[str]:
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        raise DocumentationIntegrityError(f"declared Python symbol file is invalid: {exc}") from exc
    symbols: set[str] = set()

    def walk(body: list[ast.stmt], prefix: str = "") -> None:
        for node in body:
            name = getattr(node, "name", None)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qualified = f"{prefix}.{name}" if prefix else name
                symbols.add(qualified)
                if isinstance(node, ast.ClassDef):
                    walk(node.body, qualified)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        symbols.add(f"{prefix}.{target.id}" if prefix else target.id)

    walk(tree.body)
    return symbols


def _resolve_documentation_reference(
    reference: DocumentationReference,
    repositories: dict[str, DocumentationRepositoryState],
) -> Optional[str]:
    state = repositories[reference.repository]
    path = _bounded_documentation_path(state.root, reference.path)
    if not path.exists():
        return (
            f"declared {reference.reference_type} reference is missing: "
            f"{reference.repository}:{reference.path}"
        )
    if reference.reference_type == "path":
        return None
    if not path.is_file():
        return (
            f"declared {reference.reference_type} reference is not a file: "
            f"{reference.repository}:{reference.path}"
        )
    content = read_file(path)
    assert reference.value is not None
    if reference.reference_type == "symbol":
        if path.suffix == ".py":
            resolved = reference.value in _python_symbols(content)
        else:
            resolved = bool(
                re.search(
                    rf"\b(?:class|function|const|let|var|export\s+function)\s+"
                    rf"{re.escape(reference.value)}\b",
                    content,
                )
            )
    else:
        quoted = re.compile(
            rf"(['\"]){re.escape(reference.value)}\1"
        )
        resolved = bool(quoted.search(content))
    if not resolved:
        return (
            f"declared {reference.reference_type} reference does not resolve: "
            f"{reference.repository}:{reference.path}:{reference.value}"
        )
    return None


def _framework_baseline_identity_from_payload(
    payload: dict[str, Any],
) -> tuple[Any, ...]:
    return (
        payload.get("finding_type"),
        payload.get("pair_id"),
        payload.get("canonical_path"),
        payload.get("runtime_path"),
        payload.get("disposition"),
        payload.get("severity"),
    )


def _framework_baseline_identity_from_record(
    finding: DocumentationAcceptedFinding,
) -> tuple[Any, ...]:
    return (
        finding.finding_type,
        finding.pair_id,
        finding.canonical_path,
        finding.runtime_path,
        finding.disposition,
        finding.severity,
    )


def _accepted_finding_anchor(
    finding: DocumentationAcceptedFinding,
) -> tuple[str, str]:
    return finding.finding_type, finding.pair_id


def _accepted_finding_exact_state(
    finding: DocumentationAcceptedFinding,
) -> tuple[Any, ...]:
    return (
        finding.finding_type,
        finding.pair_id,
        finding.canonical_path,
        finding.runtime_path,
        finding.disposition,
        finding.severity,
        finding.owner,
        tuple(
            (name, finding.repository_commits[name])
            for name in DOCUMENTATION_REPOSITORIES
        ),
    )


def _final_commit_trailers(state: DocumentationRepositoryState) -> list[str]:
    message = str(_git_read(state.root, "log", "-1", "--format=%B", state.head_commit))
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    parsed = subprocess.run(
        ["git", "-C", str(state.root), "interpret-trailers", "--parse"],
        input=message,
        capture_output=True,
        text=True,
        env=env,
    )
    if parsed.returncode != 0:
        raise DocumentationIntegrityError(
            "git interpret-trailers --parse failed in "
            f"{state.root}: {parsed.stderr.strip()}"
        )
    return [
        match.group(1)
        for match in re.finditer(
            r"^Documentation-No-Impact: ([a-z0-9][a-z0-9._:-]*)\s*$",
            parsed.stdout,
            re.MULTILINE,
        )
    ]


def _run_registered_propagation(
    surface: DocumentationSurface,
    *,
    repositories: dict[str, DocumentationRepositoryState],
    framework_evaluation: FrameworkPairEvaluation,
) -> Optional[str]:
    propagation = surface.propagation
    propagation_type = propagation["type"]
    if propagation_type == "none":
        return None
    vault = repositories["vault"]
    canonical = _bounded_documentation_path(vault.root, surface.canonical_path)
    if propagation_type == "ora_body_only":
        target_state = repositories[propagation["repository"]]
        target = _bounded_documentation_path(target_state.root, propagation["path"])
        if not target.is_file():
            return (
                f"propagation mismatch for {surface.surface_id}: body-only mirror "
                f"is missing at {propagation['repository']}:{propagation['path']}"
            )
        canonical_body = _normalized_framework_body(
            canonical, strip_vault_yaml=True
        )
        target_body = _normalized_framework_body(
            target, strip_vault_yaml=False
        )
        if canonical_body != target_body:
            return (
                f"propagation mismatch for {surface.surface_id}: body-only mirror "
                f"differs at {propagation['repository']}:{propagation['path']}"
            )
        return None
    if propagation_type == "framework_pair":
        pair_id = propagation["pair_id"]
        if not any(
            entry.pair_id == pair_id for entry in framework_evaluation.manifest.entries
        ):
            return (
                f"propagation mismatch for {surface.surface_id}: unknown framework "
                f"pair {pair_id}"
            )
        pair_findings = [
            finding
            for finding in framework_evaluation.findings
            if finding.payload.get("pair_id") == pair_id
        ]
        if pair_findings:
            return (
                f"propagation mismatch for {surface.surface_id}: framework pair "
                f"{pair_id} has {len(pair_findings)} finding(s)"
            )
        return None
    repository = repositories[propagation["repository"]]
    script = _bounded_documentation_path(repository.root, propagation["script"])
    if not script.is_file():
        return (
            f"propagation mismatch for {surface.surface_id}: registered site "
            f"checker is missing at app:{propagation['script']}"
        )
    replacements = {
        "{" + name + "_root}": str(state.root)
        for name, state in repositories.items()
    }
    replacements.update(
        {
            "{" + name + "_base}": state.base_commit
            for name, state in repositories.items()
        }
    )
    arguments: list[str] = []
    for value in propagation["arguments"]:
        rendered = value
        for placeholder, replacement in replacements.items():
            rendered = rendered.replace(placeholder, replacement)
        if re.search(r"\{[a-z_]+}", rendered):
            return (
                f"propagation mismatch for {surface.surface_id}: unresolved "
                f"site-check placeholder in {value!r}"
            )
        arguments.append(rendered)
    run = subprocess.run(
        ["node", str(script), *arguments],
        cwd=str(repository.root),
        capture_output=True,
        text=True,
        timeout=120,
        env={
            **os.environ,
            **{
                "DCP_" + name.upper() + "_ROOT": str(state.root)
                for name, state in repositories.items()
            },
            **{
                "DCP_" + name.upper() + "_BASE": state.base_commit
                for name, state in repositories.items()
            },
        },
    )
    if run.returncode != 0:
        report = (run.stdout + "\n" + run.stderr).strip()
        return (
            f"propagation mismatch for {surface.surface_id}: site reverse-parity "
            f"checker failed ({run.returncode}): {report[-500:]}"
        )
    return None


def evaluate_documentation_integrity(
    *,
    roots: dict[str, Path | str],
    base_commits: dict[str, str],
) -> DocumentationIntegrityEvaluation:
    # This must be first: no configuration, manifest, or referenced file is
    # touched until every repository/root/base in the explicit task contract
    # has been validated. There is deliberately no live-root fallback.
    repositories = _load_documentation_repository_states(roots, base_commits)
    vault = repositories["vault"]
    ora = repositories["ora"]
    configuration_relative_path = (
        "Projects/Ora/Reference — Documentation-Code Parity Configuration.md"
    )
    configuration_path = _bounded_documentation_path(
        vault.root,
        configuration_relative_path,
    )
    if not configuration_path.is_file():
        raise DocumentationIntegrityError(
            "canonical Documentation-Code Parity Configuration is missing"
        )
    registry = load_documentation_ownership_registry(configuration_path)
    base_registry = _load_base_documentation_ownership_registry(
        vault,
        configuration_relative_path,
    )
    _validate_documentation_repository_identities(
        repositories,
        registry.repository_identities,
    )
    accepted = load_documentation_accepted_findings(configuration_path)
    base_accepted = _load_base_documentation_accepted_findings(
        vault,
        configuration_relative_path,
    )
    if base_accepted is None:
        raise DocumentationIntegrityError(
            "pinned vault base predates the activated accepted-finding block"
        )

    findings: list[str] = []
    evidence: list[str] = [
        f"read {name} at {state.head_commit} from {state.root} "
        f"({len(state.changed_paths)} changed path(s))"
        for name, state in repositories.items()
    ]

    # Activation ended the one-time bootstrap path. A task may carry an exact
    # accepted row forward or remove it after resolution, but a pre-activation
    # base may never re-enter the historical bootstrap state.
    base_by_anchor = {
        _accepted_finding_anchor(finding): finding
        for finding in base_accepted
    }
    accepted_by_anchor = {
        _accepted_finding_anchor(finding): finding
        for finding in accepted
    }
    for anchor, finding in sorted(accepted_by_anchor.items()):
        base_finding = base_by_anchor.get(anchor)
        if base_finding is None:
            findings.append(
                "accepted finding addition is not authorized by the pinned "
                f"vault base: {finding.finding_type}:{finding.pair_id}"
            )
        elif _accepted_finding_exact_state(
            finding
        ) != _accepted_finding_exact_state(base_finding):
            findings.append(
                "accepted finding material mutation is not authorized by "
                f"the pinned vault base: {finding.finding_type}:{finding.pair_id}"
            )

    current_surfaces_by_id = {
        surface.surface_id: surface for surface in registry.surfaces
    }
    base_surfaces_by_id = (
        {
            surface.surface_id: surface
            for surface in base_registry.surfaces
        }
        if base_registry is not None
        else {}
    )
    registries_by_version: dict[str, DocumentationOwnershipRegistry] = {
        "current": registry,
    }
    surfaces_by_version: dict[str, dict[str, DocumentationSurface]] = {
        "current": current_surfaces_by_id,
    }
    if base_registry is not None:
        registries_by_version["base"] = base_registry
        surfaces_by_version["base"] = base_surfaces_by_id

    # Impacts retain the complete material surface state. A stable surface id
    # can legitimately point at a different canonical or propagation rule in
    # the task HEAD; collapsing by id would let that registry edit erase the
    # prior documentation obligation.
    affected_repositories: dict[tuple[Any, ...], set[str]] = {}
    affected_origins: dict[tuple[Any, ...], set[str]] = {}
    surface_states: dict[tuple[Any, ...], DocumentationSurface] = {}

    def affect(
        surface: DocumentationSurface,
        repository_name: str,
        origin: str,
    ) -> bool:
        key = _documentation_surface_state_identity(surface)
        surface_states[key] = surface
        before_repositories = set(affected_repositories.get(key, set()))
        before_origins = set(affected_origins.get(key, set()))
        affected_repositories.setdefault(key, set()).add(repository_name)
        affected_origins.setdefault(key, set()).add(origin)
        return (
            affected_repositories[key] != before_repositories
            or affected_origins[key] != before_origins
        )

    # A registry definition is state, not an authority that may rewrite its
    # own past. Added, removed, and materially changed surfaces therefore feed
    # both their prior and current identities into this task's disposition.
    if base_registry is None:
        evidence.append(
            "ownership/discovery pinned base is absent; task HEAD is the "
            "initial bootstrap registry"
        )
        for surface in registry.surfaces:
            affect(surface, "vault", "current")
    else:
        for surface_id in sorted(
            set(base_surfaces_by_id) | set(current_surfaces_by_id)
        ):
            base_surface = base_surfaces_by_id.get(surface_id)
            current_surface = current_surfaces_by_id.get(surface_id)
            if base_surface is None:
                assert current_surface is not None
                affect(current_surface, "vault", "current")
            elif current_surface is None:
                affect(base_surface, "vault", "base")
            elif _documentation_surface_state_identity(
                base_surface
            ) != _documentation_surface_state_identity(current_surface):
                affect(base_surface, "vault", "base")
                affect(current_surface, "vault", "current")

    def discovery_sources(
        ownership: DocumentationOwnershipRegistry,
    ) -> dict[str, tuple[str, DocumentationDiscoverySource]]:
        return {
            source.source_id: (surface_class, source)
            for surface_class, sources in ownership.discovery.items()
            for source in sources
        }

    base_sources = discovery_sources(base_registry) if base_registry else {}
    current_sources = discovery_sources(registry)

    # The discovery union is configuration, not prose. Base inventory uses the
    # pinned base rule and associations; HEAD inventory uses the current rule.
    # Definition changes affect their prior and current families in the vault
    # commit, while actual catalogue/item deltas affect the source repository.
    for source_id in sorted(set(base_sources) | set(current_sources)):
        base_entry = base_sources.get(source_id)
        current_entry = current_sources.get(source_id)
        base_items: dict[str, str] = {}
        current_items: dict[str, str] = {}
        base_ok = True
        current_ok = True

        if base_entry is not None:
            base_class, base_source = base_entry
            try:
                base_items = _enumerate_documentation_discovery_source(
                    base_source,
                    repositories,
                    repositories[base_source.repository].base_commit,
                    revision_label="pinned base",
                    allow_missing=True,
                )
            except DocumentationIntegrityError as exc:
                findings.append(f"discovery {base_class}/{source_id}: {exc}")
                base_ok = False
        if current_entry is not None:
            current_class, current_source = current_entry
            try:
                current_items = _enumerate_documentation_discovery_source(
                    current_source,
                    repositories,
                    repositories[current_source.repository].head_commit,
                    revision_label="task HEAD",
                )
            except DocumentationIntegrityError as exc:
                findings.append(f"discovery {current_class}/{source_id}: {exc}")
                current_ok = False

        base_item_ids = set(base_items)
        current_item_ids = set(current_items)
        added_items = current_item_ids - base_item_ids
        removed_items = base_item_ids - current_item_ids
        materially_changed_items = {
            item
            for item in base_item_ids & current_item_ids
            if base_items[item] != current_items[item]
        }
        evidence.append(
            f"discovery {source_id} enumerated "
            f"base={len(base_items)}, current={len(current_items)}, "
            f"added={len(added_items)}, removed={len(removed_items)}, "
            f"materially-changed={len(materially_changed_items)}"
        )

        base_mappings: dict[str, Optional[str]] = {}
        if base_entry is not None and base_ok:
            base_class, base_source = base_entry
            for item in sorted(base_item_ids):
                try:
                    base_mappings[item] = _discovery_surface_for_item(
                        base_source, item
                    )
                except DocumentationIntegrityError as exc:
                    findings.append(f"discovery {base_class}/{source_id}: {exc}")

        current_mappings: dict[str, Optional[str]] = {}
        if current_entry is not None and current_ok:
            current_class, current_source = current_entry
            for item in sorted(current_item_ids):
                try:
                    surface_id = _discovery_surface_for_item(current_source, item)
                except DocumentationIntegrityError as exc:
                    findings.append(f"discovery {current_class}/{source_id}: {exc}")
                    continue
                current_mappings[item] = surface_id
                if surface_id is None:
                    findings.append(
                        f"unmapped discovered item: {source_id}:{item}"
                    )

        definition_changed = (
            base_entry is None
            or current_entry is None
            or _documentation_discovery_source_identity(*base_entry)
            != _documentation_discovery_source_identity(*current_entry)
        )
        if definition_changed:
            for origin, entry, version_surfaces in (
                ("base", base_entry, base_surfaces_by_id),
                ("current", current_entry, current_surfaces_by_id),
            ):
                if entry is None:
                    continue
                _surface_class, source = entry
                for association in source.associations:
                    affect(
                        version_surfaces[association.surface_id],
                        "vault",
                        origin,
                    )

        same_enumerator = False
        if base_entry is not None and current_entry is not None:
            _base_class, base_source = base_entry
            _current_class, current_source = current_entry
            same_enumerator = (
                base_source.source_type,
                base_source.repository,
                base_source.path,
                base_source.selector,
                base_source.item_field,
            ) == (
                current_source.source_type,
                current_source.repository,
                current_source.path,
                current_source.selector,
                current_source.item_field,
            )
        if same_enumerator:
            data_changed_items = (
                added_items | removed_items | materially_changed_items
            )
            assert base_entry is not None and current_entry is not None
            _base_class, base_source = base_entry
            _current_class, current_source = current_entry
            for item in sorted(data_changed_items):
                base_surface_id = base_mappings.get(item)
                if base_surface_id is not None:
                    affect(
                        base_surfaces_by_id[base_surface_id],
                        base_source.repository,
                        "base",
                    )
                current_surface_id = current_mappings.get(item)
                if current_surface_id is not None:
                    affect(
                        current_surfaces_by_id[current_surface_id],
                        current_source.repository,
                        "current",
                    )

    for surface in registry.surfaces:
        canonical = _bounded_documentation_path(
            vault.root, surface.canonical_path
        )
        if not canonical.is_file():
            findings.append(
                f"canonical missing for {surface.surface_id}: "
                f"vault:{surface.canonical_path}"
            )
            continue
        if surface.canonical_section and not _markdown_has_section(
            read_file(canonical), surface.canonical_section
        ):
            findings.append(
                f"canonical section missing for {surface.surface_id}: "
                f"{surface.canonical_section!r} in {surface.canonical_path}"
            )

    for repository_name, state in repositories.items():
        for path in state.changed_paths:
            mapped = False
            for origin, ownership in registries_by_version.items():
                owner = _documentation_owner_for_path(
                    ownership, repository_name, path
                )
                if owner is not None:
                    affect(owner, repository_name, origin)
                    mapped = True
                    continue
                registered_surfaces = _registered_document_surfaces_for_path(
                    ownership, repository_name, path
                )
                for surface in registered_surfaces:
                    affect(surface, repository_name, origin)
                    mapped = True
            if not mapped and _is_code_bearing_change(repository_name, path):
                findings.append(
                    f"unmapped code change: {repository_name}:{path}"
                )

    # Shared-mechanism consumers inherit the same affected repositories, so
    # their version-correct references, propagation, and disposition are
    # evaluated together. Consumer removal in HEAD cannot erase the base edge.
    pending = list(affected_repositories)
    while pending:
        key = pending.pop()
        surface = surface_states[key]
        repositories_for_surface = set(affected_repositories[key])
        origins_for_surface = set(affected_origins[key])
        for origin in origins_for_surface:
            for consumer_id in surface.consumers:
                consumer = surfaces_by_version[origin][consumer_id]
                consumer_key = _documentation_surface_state_identity(consumer)
                changed = False
                for repository_name in repositories_for_surface:
                    changed = affect(consumer, repository_name, origin) or changed
                if changed:
                    pending.append(consumer_key)

    affected_surfaces = tuple(
        sorted({surface.surface_id for surface in surface_states.values()})
    )
    no_impact_surface_ids_by_repository: dict[str, set[str]] = {
        name: set() for name in DOCUMENTATION_REPOSITORIES
    }
    canonical_changed_by_state: dict[tuple[Any, ...], bool] = {}
    for key, repository_names in affected_repositories.items():
        surface = surface_states[key]
        canonical_changed = _documentation_canonical_changed(vault, surface)
        canonical_changed_by_state[key] = canonical_changed
        if canonical_changed:
            continue
        for repository_name in repository_names:
            no_impact_surface_ids_by_repository[repository_name].add(
                surface.surface_id
            )

    # A task may declare no impact only for a surface the gate actually
    # attributed to that repository's diff.  Unknown, cross-repository, and
    # duplicate trailers otherwise create the appearance of review evidence
    # for work the gate never evaluated.
    trailer_cache: dict[str, list[str]] = {}
    for repository_name, state in repositories.items():
        if state.head_commit == state.base_commit:
            continue
        trailers = _final_commit_trailers(state)
        trailer_cache[repository_name] = trailers
        allowed = no_impact_surface_ids_by_repository[repository_name]
        for surface_id in sorted(set(trailers)):
            count = trailers.count(surface_id)
            if surface_id not in allowed:
                findings.append(
                    f"unused Documentation-No-Impact trailer in "
                    f"{repository_name} final commit: {surface_id} does not "
                    "correspond to a no-impact disposition owed by that repository"
                )
            elif count > 1:
                findings.append(
                    f"surplus Documentation-No-Impact trailer in "
                    f"{repository_name} final commit: {surface_id} appears "
                    f"{count} times"
                )

    current_state_keys = {
        _documentation_surface_state_identity(surface)
        for surface in registry.surfaces
    }
    for key in sorted(affected_repositories, key=repr):
        surface = surface_states[key]
        if key in current_state_keys:
            for reference in surface.references:
                error = _resolve_documentation_reference(reference, repositories)
                if error:
                    findings.append(f"surface {surface.surface_id}: {error}")

    disposition_checks: set[tuple[str, str, str]] = set()
    for key in sorted(affected_repositories, key=repr):
        surface = surface_states[key]
        canonical_changed = canonical_changed_by_state[key]
        if canonical_changed:
            continue
        for repository_name in sorted(affected_repositories[key]):
            disposition_key = (
                surface.surface_id,
                surface.canonical_path,
                repository_name,
            )
            if disposition_key in disposition_checks:
                continue
            disposition_checks.add(disposition_key)
            if repository_name not in trailer_cache:
                trailer_cache[repository_name] = _final_commit_trailers(
                    repositories[repository_name]
                )
            trailers = trailer_cache[repository_name]
            count = trailers.count(surface.surface_id)
            if count != 1:
                findings.append(
                    f"documentation disposition missing for {surface.surface_id} in "
                    f"{repository_name} final commit: expected exactly one "
                    f"Documentation-No-Impact trailer, found {count}"
                )

    manifest_path = _bounded_documentation_path(
        vault.root,
        "Projects/Ora/Reference — Vault Ora Framework Pair Manifest.md",
    )
    try:
        framework_evaluation = evaluate_framework_pair_manifest(
            manifest_path=manifest_path,
            vault_root=vault.root,
            ora_root=ora.root,
        )
    except (OSError, FrameworkManifestError) as exc:
        raise DocumentationIntegrityError(
            f"framework-pair integrity could not be evaluated: {exc}"
        ) from exc

    current_by_identity = {
        _framework_baseline_identity_from_payload(finding.payload): finding
        for finding in framework_evaluation.findings
    }
    accepted_by_identity = {
        _framework_baseline_identity_from_record(finding): finding
        for finding in accepted
    }
    for identity, current in sorted(
        current_by_identity.items(), key=lambda item: repr(item[0])
    ):
        if identity not in accepted_by_identity:
            findings.append(
                "new or changed framework finding is not accepted: "
                f"{current.payload['finding_type']}:{current.payload['pair_id']}"
            )
    for identity, baseline in sorted(
        accepted_by_identity.items(), key=lambda item: repr(item[0])
    ):
        if identity not in current_by_identity:
            findings.append(
                "stale accepted framework finding must be removed after resolution: "
                f"{baseline.finding_type}:{baseline.pair_id}"
            )
        for repository_name, commit in baseline.repository_commits.items():
            state = repositories[repository_name]
            try:
                _git_read(state.root, "cat-file", "-e", f"{commit}^{{commit}}")
            except DocumentationIntegrityError:
                findings.append(
                    f"accepted finding {baseline.pair_id} references unreadable "
                    f"{repository_name} commit {commit}"
                )

    propagation_keys: set[tuple[str, Optional[str], str]] = set()
    for key in sorted(affected_repositories, key=repr):
        if key not in current_state_keys:
            continue
        surface = surface_states[key]
        propagation_key = (
            surface.canonical_path,
            surface.canonical_section,
            _canonical_json(surface.propagation),
        )
        if propagation_key in propagation_keys:
            continue
        propagation_keys.add(propagation_key)
        error = _run_registered_propagation(
            surface,
            repositories=repositories,
            framework_evaluation=framework_evaluation,
        )
        if error:
            findings.append(error)

    # A registered checker is verification-only. If it wrote anything, the
    # task fails even if its own process returned zero.
    for name, state in repositories.items():
        dirty = _git_read(
            state.root, "status", "--porcelain", "-z", binary=True
        )
        if dirty:
            findings.append(
                f"verification mutated the {name} worktree; pre-push checks must be read-only"
            )

    evidence.append(
        "result is referential/state evidence only; semantic documentation "
        "accuracy remains an independent-review decision"
    )
    return DocumentationIntegrityEvaluation(
        repositories=repositories,
        affected_surfaces=affected_surfaces,
        findings=tuple(findings),
        evidence=tuple(evidence),
    )


def check_documentation_integrity(
    verbose: bool = False,
    *,
    roots: Optional[dict[str, Path | str]] = None,
    base_commits: Optional[dict[str, str]] = None,
) -> CheckResult:
    result = CheckResult(name="documentation-integrity", passed=True)
    try:
        evaluation = evaluate_documentation_integrity(
            roots=roots or {},
            base_commits=base_commits or {},
        )
    except (OSError, DocumentationIntegrityError) as exc:
        result.passed = False
        result.details.append(f"Documentation integrity contract failure: {exc}")
        return result
    if evaluation.findings:
        result.passed = False
        result.details.extend(evaluation.findings)
    if verbose:
        result.details[:0] = list(evaluation.evidence)
        result.details.append(
            "affected surfaces: "
            + (", ".join(evaluation.affected_surfaces) or "none")
        )
    return result


def verify_framework_finding_receipts(content: str) -> list[FrameworkPairFinding]:
    """Authenticate every machine-readable framework finding in queue text."""
    findings: list[FrameworkPairFinding] = []
    for match in FRAMEWORK_RECEIPT_PATTERN.finditer(content):
        try:
            receipt = json.loads(match.group(1))
            payload = receipt["finding"]
            digest = receipt["finding_digest"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise FrameworkManifestError(
                "malformed framework finding receipt in escalation queue"
            ) from exc
        if not isinstance(payload, dict) or not isinstance(digest, str):
            raise FrameworkManifestError(
                "malformed framework finding receipt in escalation queue"
            )
        computed = _sha256_text(_canonical_json(payload))
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or digest != computed:
            raise FrameworkManifestError(
                "framework finding receipt digest mismatch in escalation queue"
            )
        findings.append(FrameworkPairFinding(payload=payload, finding_digest=digest))
    return findings


def _queue_lock_age_seconds(lock: Path) -> Optional[float]:
    """Seconds since the lock was created, or None if it cannot be read."""
    try:
        return max(0.0, time.time() - lock.stat().st_mtime)
    except OSError:
        return None


def _open_queue_region(content: str) -> str:
    """The portion of the queue holding findings that are still open."""
    index = content.find(FRAMEWORK_QUEUE_CLOSED_HEADING)
    return content if index == -1 else content[:index]


def _render_framework_queue_entry(
    finding: FrameworkPairFinding,
    *,
    queue_id: str,
    detected_on: str,
) -> str:
    payload = finding.payload
    receipt = _canonical_json(
        {"finding": payload, "finding_digest": finding.finding_digest}
    )
    runtime_digest = payload["runtime_body_sha256"] or "absent"
    canonical_digest = payload["canonical_body_sha256"] or "absent"
    return (
        f"### {queue_id} — Authenticated framework-pair finding: "
        f"`{payload['pair_id']}`\n\n"
        f"<!-- dcp-framework-finding-receipt {receipt} -->\n\n"
        f"- **Date detected:** {detected_on} (G1.14 deterministic detector)\n"
        f"- **Drift class:** {payload['severity']}; "
        f"`{payload['finding_type']}`.\n"
        f"- **Manifest:** `{payload['manifest_id']}`; "
        f"SHA-256 `{payload['manifest_sha256']}`.\n"
        f"- **Canonical:** `{payload['canonical_path'] or 'unregistered'}`; "
        f"normalized-body SHA-256 `{canonical_digest}`.\n"
        f"- **Runtime:** `{payload['runtime_path'] or 'none'}`; "
        f"normalized-body SHA-256 `{runtime_digest}`.\n"
        f"- **Expected disposition:** `{payload['disposition']}`.\n"
        f"- **Finding receipt:** SHA-256 `{finding.finding_digest}` over the "
        "canonical JSON payload embedded above.\n"
        "- **Required action:** Preserve this as an explicit downstream "
        "reconciliation decision. G1.14 does not create, synchronize, or "
        "activate a framework copy.\n"
        "- **User decision:** *(blank)*\n"
    )


def enqueue_framework_pair_findings(
    *,
    manifest_path: Optional[Path] = None,
    vault_root: Optional[Path] = None,
    ora_root: Optional[Path] = None,
    queue_path: Optional[Path] = None,
) -> tuple[int, int]:
    """Atomically append authenticated findings; retries are idempotent."""
    queue = queue_path or FRAMEWORK_ESCALATION_QUEUE_FILE
    if queue.is_symlink() or not queue.is_file():
        raise FrameworkManifestError(
            f"escalation queue must be an existing regular non-symlink file: {queue}"
        )
    queue_mode = queue.stat().st_mode & 0o777
    lock = queue.with_name(queue.name + ".lock")
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        age = _queue_lock_age_seconds(lock)
        if age is None or age < FRAMEWORK_QUEUE_LOCK_STALE_SECONDS:
            raise FrameworkManifestError(
                f"escalation queue lock already exists: {lock}"
            ) from exc
        print(
            f"WARNING: removing abandoned escalation queue lock {lock} "
            f"(age {int(age)}s > {FRAMEWORK_QUEUE_LOCK_STALE_SECONDS}s). "
            "A previous run did not release it.",
            file=sys.stderr,
        )
        try:
            os.unlink(lock)
            lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except OSError as retry_exc:
            # Another run won the race and took the lock legitimately.
            raise FrameworkManifestError(
                f"escalation queue lock already exists: {lock}"
            ) from retry_exc
    os.close(lock_fd)
    temp: Optional[Path] = None
    try:
        evaluation = evaluate_framework_pair_manifest(
            manifest_path=manifest_path,
            vault_root=vault_root,
            ora_root=ora_root,
        )
        content = read_file(queue)
        # Authenticate every receipt in the file, closed ones included — a
        # tampered historical receipt is still tampering. Deduplicate only
        # against the open region, so a finding the user closed can be
        # detected again if the drift recurs.
        existing = verify_framework_finding_receipts(content)
        existing_identities = {
            _framework_finding_identity(finding.payload)
            for finding in verify_framework_finding_receipts(
                _open_queue_region(content)
            )
        }
        new_findings = [
            finding
            for finding in evaluation.findings
            if _framework_finding_identity(finding.payload) not in existing_identities
        ]
        if not new_findings:
            return 0, len(evaluation.findings)
        numbers = [int(value) for value in re.findall(r"^### E-(\d+)\b", content, re.MULTILINE)]
        next_number = max(numbers, default=0) + 1
        detected_on = dt.date.today().isoformat()
        missing_blocks: list[str] = []
        escalation_blocks: list[str] = []
        for finding in new_findings:
            block = _render_framework_queue_entry(
                finding,
                queue_id=f"E-{next_number:03d}",
                detected_on=detected_on,
            )
            next_number += 1
            if finding.payload["finding_type"] == "missing_runtime_twin":
                missing_blocks.append(block)
            else:
                escalation_blocks.append(block)
        missing_anchor = "\n---\n\n## Escalate class\n"
        escalation_anchor = "\n---\n\n## Deprecation-candidate class\n"
        if missing_anchor not in content or escalation_anchor not in content:
            raise FrameworkManifestError(
                "escalation queue insertion anchors are missing"
            )
        if missing_blocks:
            insertion = "\n" + "\n".join(missing_blocks) + "\n"
            content = content.replace(missing_anchor, insertion + missing_anchor, 1)
        if escalation_blocks:
            insertion = "\n" + "\n".join(escalation_blocks) + "\n"
            content = content.replace(
                escalation_anchor, insertion + escalation_anchor, 1
            )
        content = re.sub(
            r"^(date modified:)\s*.*$",
            rf"\1 {detected_on}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
        temp = queue.with_name(f".{queue.name}.tmp-{os.getpid()}")
        temp_fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(temp_fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, queue_mode)
        os.replace(temp, queue)
        temp = None
        return len(new_findings), len(evaluation.findings)
    finally:
        if temp is not None:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def extract_top_level_yaml_keys(content: str) -> set[str]:
    """Extract top-level YAML keys from a YAML-like body (mode file body uses YAML
    code blocks for the locked template). Returns set of keys found at top level."""
    keys: set[str] = set()
    in_yaml_block = False
    for line in content.split("\n"):
        if line.strip().startswith("```yaml") or line.strip().startswith("```YAML"):
            in_yaml_block = True
            continue
        if line.strip() == "```":
            in_yaml_block = False
            continue
        if in_yaml_block:
            # Top-level keys are at column 0 with no leading whitespace
            if line and not line.startswith(" ") and not line.startswith("\t") and not line.startswith("#"):
                if ":" in line:
                    k = line.split(":")[0].strip()
                    if k:
                        keys.add(k)
    return keys


def extract_h2_sections(body: str) -> set[str]:
    """Extract `## HEADING` titles from markdown body."""
    h2s = set()
    for line in body.split("\n"):
        if line.startswith("## ") and not line.startswith("### "):
            h2s.add(line[3:].strip())
    return h2s


def list_mode_files() -> list[Path]:
    """List the 64 active resident + utility mode files."""
    if not MODES_DIR.exists():
        return []
    return [
        p for p in MODES_DIR.glob("*.md")
        if p.stem not in EXCLUDED_MODE_FILES and not p.stem.endswith(".bak")
    ]


def _registry_mode_ids() -> tuple[set[str], set[str]]:
    """Return (resident, deferred) IDs from the canonical Mode Registry.

    The registry deliberately separates the 60 resident analysis modes from
    fourteen CR-6 candidates. Deferred IDs are valid routing references but do
    not require a runtime file until promoted.
    """
    if not MODE_REGISTRY_FILE.exists():
        return set(), set()
    content = read_file(MODE_REGISTRY_FILE)
    resident_start = content.find("## Per-Territory Mode Entries")
    resident_end = content.find("## Lens Library Cross-Reference", resident_start)
    deferred_start = content.find("## Deferred Candidates (CR-6)")
    deferred_end = content.find("## Cross-References", deferred_start)
    resident_block = content[resident_start:resident_end]
    deferred_block = content[deferred_start:deferred_end]
    entry_pattern = re.compile(r"^- \*\*`([a-z0-9-]+)`\*\*", re.MULTILINE)
    inline_pattern = re.compile(r"`([a-z0-9-]+)`")
    return set(entry_pattern.findall(resident_block)), set(inline_pattern.findall(deferred_block))


def _declared_mode_id(content: str) -> Optional[str]:
    match = re.search(r"^mode_id:\s*([a-z0-9-]+)\s*$", content, re.MULTILINE)
    return match.group(1) if match else None


def _lens_dependencies(content: str) -> set[str]:
    """Extract lens IDs only from the YAML lens_dependencies block."""
    match = re.search(
        r"^lens_dependencies:\s*$\n(?P<block>(?:^[ \t]+.*(?:\n|$))*)",
        content,
        re.MULTILINE,
    )
    if not match:
        return set()
    return {
        item.group(1)
        for item in re.finditer(
            r"^\s{4}-\s*([a-z0-9-]+)(?:\s|\(|$)",
            match.group("block"),
            re.MULTILINE,
        )
    }


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_template_conformance(verbose: bool = False) -> CheckResult:
    """Verify the current 64-file mode schema and canonical registry split."""
    result = CheckResult(name="template", passed=True)
    mode_files = list_mode_files()
    if not mode_files:
        result.passed = False
        result.details.append(f"No mode files found in {MODES_DIR}")
        return result

    if len(mode_files) != 64:
        result.passed = False
        result.details.append(f"Expected 64 mode files; found {len(mode_files)}")

    resident_ids, deferred_ids = _registry_mode_ids()
    file_ids = {p.stem for p in mode_files}
    expected_residents = file_ids - UTILITY_MODE_IDS
    if not MODE_REGISTRY_FILE.exists():
        result.passed = False
        result.details.append(f"Mode registry not found: {MODE_REGISTRY_FILE}")
    else:
        missing_residents = expected_residents - resident_ids
        stale_residents = resident_ids - expected_residents
        if missing_residents:
            result.passed = False
            result.details.append(
                f"Mode registry missing resident IDs: {sorted(missing_residents)}")
        if stale_residents:
            result.passed = False
            result.details.append(
                f"Mode registry has resident IDs without files: {sorted(stale_residents)}")
        if len(deferred_ids) != 14:
            result.passed = False
            result.details.append(
                f"Expected 14 deferred CR-6 IDs in registry; found {len(deferred_ids)}")

    for mode_file in sorted(mode_files):
        content = read_file(mode_file)
        _, body = parse_yaml_frontmatter(content)

        declared_id = _declared_mode_id(body)
        identity_issues = []
        if declared_id != mode_file.stem:
            identity_issues.append(
                f"declared mode_id {declared_id!r} != filename {mode_file.stem!r}")

        # Check YAML keys (in code blocks within body)
        yaml_keys = extract_top_level_yaml_keys(body)
        # Composition determines whether atomic_spec or molecular_spec is required
        if "atomic_spec" in yaml_keys or "molecular_spec" in yaml_keys:
            yaml_keys.add("composition_spec")  # treat either as composition_spec

        required_fields = (
            SIMPLE_BYPASS_REQUIRED_FIELDS
            if mode_file.stem == "simple"
            else REQUIRED_TEMPLATE_FIELDS
        )
        missing = required_fields - yaml_keys
        # composition_spec is satisfied by atomic_spec OR molecular_spec; remove from missing
        # if neither present, missing.add('composition_spec')... but that's not in REQUIRED set
        # The required set only has top-level fields the template lists. Let's just check.

        # Check pipeline-stage subsections (## headings in body)
        h2s = extract_h2_sections(body)
        missing_subsections = REQUIRED_PIPELINE_SUBSECTIONS - h2s

        # educational_name word count and acronym check (parse from raw text)
        edu_name_match = re.search(r"^educational_name:\s*(.+?)$", body, re.MULTILINE)
        edu_name_issues = []
        if edu_name_match:
            edu_name = edu_name_match.group(1).strip()
            words = edu_name.split()
            if len(words) > 15:
                edu_name_issues.append(f"educational_name >15 words ({len(words)})")
            # Check for acronyms (3+ uppercase letters in a row) without expansion / contextualizing parenthetical
            acronyms = re.findall(r"\b[A-Z]{3,}\b", edu_name)
            for acronym in acronyms:
                # Acceptable: acronym appears within a parenthetical with other explanatory content
                # (this is the educational parenthetical convention — the parens carries the named technique + context)
                parens_with_acronym = rf"\([^)]*\b{acronym}\b[^)]*[a-z][^)]*\)"
                if re.search(parens_with_acronym, edu_name):
                    continue
                # Acceptable: acronym followed by explicit sub-parens with expansion
                followed_by_parens = rf"\b{acronym}\b\s*\([^)]+\)"
                if re.search(followed_by_parens, edu_name):
                    continue
                # Acceptable: acronym preceded by its expansion (the words it stands for)
                # Heuristic: acronym in the educational_name where the educational_name has lower-case words
                # contextualizing it. Skip if the educational_name length excluding the acronym is >5 words
                # (i.e., there's substantive context).
                rest = re.sub(rf"\b{acronym}\b", "", edu_name).strip()
                word_count = len([w for w in rest.split() if w.isalpha() or "-" in w])
                if word_count >= 5:
                    continue
                edu_name_issues.append(f"acronym '{acronym}' lacks sub-parens expansion or contextualizing text")

        if missing or missing_subsections or edu_name_issues or identity_issues:
            result.passed = False
            issues = []
            if missing:
                issues.append(f"missing fields: {sorted(missing)}")
            if missing_subsections:
                issues.append(f"missing pipeline subsections: {sorted(missing_subsections)}")
            if edu_name_issues:
                issues.append(f"educational_name issues: {edu_name_issues}")
            if identity_issues:
                issues.extend(identity_issues)
            result.details.append(f"{mode_file.name}: {'; '.join(issues)}")
        elif verbose:
            result.details.append(f"{mode_file.name}: OK")

    return result


def check_crossref_resolution(verbose: bool = False) -> CheckResult:
    """Verify active/deferred/utility mode, territory, and lens references."""
    result = CheckResult(name="crossref", passed=True)

    mode_files = list_mode_files()
    if not mode_files:
        result.passed = False
        result.details.append("No mode files found")
        return result

    active_mode_ids = {p.stem for p in mode_files}
    resident_ids, deferred_ids = _registry_mode_ids()
    valid_mode_ids = active_mode_ids | deferred_ids
    valid_lens_ids = {
        p.stem for p in LENSES_DIR.glob("*.md")
        if p.stem != "INDEX" and not p.stem.endswith(".bak")
    }

    # Read territories file once
    territories_content = read_file(TERRITORIES_FILE) if TERRITORIES_FILE.exists() else ""

    for mode_file in sorted(mode_files):
        content = read_file(mode_file)

        # Check territory reference
        territory_match = re.search(r"^territory:\s*(T\d+)-", content, re.MULTILINE)
        if mode_file.stem == "simple":
            if not re.search(r"^territory:\s*T-bypass\s*$", content, re.MULTILINE):
                result.passed = False
                result.details.append(
                    f"{mode_file.name}: direct bypass must declare territory T-bypass")
            territory_match = None
        if territory_match:
            territory_id = territory_match.group(1)
            if mode_file.stem in UTILITY_MODE_IDS:
                if territory_id != "T0":
                    result.passed = False
                    result.details.append(
                        f"{mode_file.name}: utility mode must use T0, found '{territory_id}'")
            elif territory_id not in TERRITORY_IDS:
                result.passed = False
                result.details.append(f"{mode_file.name}: invalid territory '{territory_id}'")
            elif territory_id not in territories_content:
                result.passed = False
                result.details.append(f"{mode_file.name}: territory '{territory_id}' not present in territories file")

        # Check adjacent_modes_in_territory references
        for adj_match in re.finditer(r"mode_id:\s*([\w-]+)", content):
            ref_id = adj_match.group(1)
            if ref_id and ref_id not in valid_mode_ids and ref_id != "null":
                # Skip the mode_id at the top of its own file
                if ref_id != mode_file.stem:
                    result.passed = False
                    result.details.append(f"{mode_file.name}: references unknown mode_id '{ref_id}'")

        # Deferred CR-6 IDs are valid references without runtime files. Every
        # lens dependency, by contrast, must resolve to an installed lens now.
        for lens_id in sorted(_lens_dependencies(content)):
            if lens_id not in valid_lens_ids:
                result.passed = False
                result.details.append(
                    f"{mode_file.name}: references unknown lens_id '{lens_id}'")

    if verbose:
        result.details.append(
            f"Resolved {len(active_mode_ids)} active mode IDs "
            f"({len(resident_ids)} resident + {len(UTILITY_MODE_IDS)} utility), "
            f"{len(deferred_ids)} deferred IDs, and {len(valid_lens_ids)} content lens IDs "
            "(INDEX.md excluded)")

    return result


def check_signal_vocabulary(verbose: bool = False) -> CheckResult:
    """Verify every mode_id has ≥3 signal entries; no orphans."""
    result = CheckResult(name="signals", passed=True)

    if not SIGNAL_REGISTRY_FILE.exists():
        result.passed = False
        result.details.append(f"Signal vocabulary registry not found: {SIGNAL_REGISTRY_FILE}")
        return result

    content = read_file(SIGNAL_REGISTRY_FILE)
    valid_mode_ids = {p.stem for p in list_mode_files()} - UTILITY_MODE_IDS

    # Count signals per mode_id (heuristic: count rows in markdown tables that reference each mode_id)
    signal_counts: dict[str, int] = {m: 0 for m in valid_mode_ids}
    referenced_mode_ids: set[str] = set()

    # Match table rows. The third data column is the mode ID.
    all_referenced_mode_ids: set[str] = set()
    for line in content.split("\n"):
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.split("|")]
        # Skip header rows / separator rows
        if any(p.startswith("-") and all(c in "-: " for c in p) for p in parts):
            continue
        if len(parts) < 5:
            continue
        mode_id = parts[3]
        if not re.fullmatch(r"[a-z0-9-]+", mode_id) or mode_id == "mode":
            continue
        all_referenced_mode_ids.add(mode_id)
        if mode_id in valid_mode_ids:
            signal_counts[mode_id] += 1
            referenced_mode_ids.add(mode_id)

    # Modes with <3 signals are flagged
    for mode_id, count in signal_counts.items():
        if count < 3:
            result.passed = False
            result.details.append(f"mode '{mode_id}' has only {count} signal entries (need ≥3)")

    orphan_ids = all_referenced_mode_ids - valid_mode_ids
    for mode_id in sorted(orphan_ids):
        result.passed = False
        result.details.append(f"signal registry references non-resident mode '{mode_id}'")

    if verbose and result.passed:
        result.details.append(
            f"All {len(valid_mode_ids)} resident modes have ≥3 signals; "
            "utility/bypass modes are correctly exempt")

    return result


def check_runtime_config(verbose: bool = False) -> CheckResult:
    """Verify every mode carries the in-file runtime contract.

    Reversed 2026-05-12: runtime fields no longer live in a separate file.
    Each mode file declares its own gear in a ## DEFAULT GEAR section.
    """
    result = CheckResult(name="runtime", passed=True)

    missing: list[tuple[str, list[str]]] = []
    for path in list_mode_files():
        content = read_file(path)
        absent = []
        if not re.search(r"^## DEFAULT GEAR\s*$", content, re.MULTILINE):
            absent.append("## DEFAULT GEAR")
        if not re.search(r"^## RAG PROFILE\s*$", content, re.MULTILINE):
            absent.append("## RAG PROFILE")
        if path.stem == "simple":
            if not re.search(r"^gear:\s*1\s*$", content, re.MULTILINE):
                absent.append("gear: 1")
        elif not re.search(r"^default_depth_tier:\s*\S+", content, re.MULTILINE):
            absent.append("default_depth_tier")
        if not re.search(r"^expected_runtime:\s*\S+", content, re.MULTILINE):
            absent.append("expected_runtime")
        if absent:
            missing.append((path.stem, absent))

    for mode_id, absent in sorted(missing):
        result.passed = False
        result.details.append(f"mode '{mode_id}' is missing: {', '.join(absent)}")

    if verbose and not missing:
        result.details.append(
            "All 64 mode files declare depth/runtime fields, ## DEFAULT GEAR, and ## RAG PROFILE")

    return result


def check_drift_parity(verbose: bool = False) -> CheckResult:
    """Verify registered vault/Ora file pairs match (modulo vault YAML)."""
    result = CheckResult(name="drift", passed=True)

    for vault_name, ora_name in DRIFT_PAIRS:
        vault_path = VAULT_ROOT / vault_name
        ora_path = ORA_ROOT / ora_name

        if not vault_path.exists():
            result.passed = False
            result.details.append(f"Vault file missing: {vault_path}")
            continue
        if not ora_path.exists():
            result.passed = False
            result.details.append(f"Ora file missing: {ora_path}")
            continue

        vault_content = read_file(vault_path)
        ora_content = read_file(ora_path)

        # Strip YAML from vault
        _, vault_body = parse_yaml_frontmatter(vault_content)
        # Normalize trailing whitespace
        vault_body = vault_body.rstrip()
        ora_content = ora_content.rstrip()
        # Strip leading newlines (from YAML stripping)
        vault_body = vault_body.lstrip("\n")
        ora_content = ora_content.lstrip("\n")

        if vault_body != ora_content:
            # Find first divergence line for actionable feedback
            v_lines = vault_body.split("\n")
            o_lines = ora_content.split("\n")
            first_diff = None
            for i, (v, o) in enumerate(zip(v_lines, o_lines)):
                if v != o:
                    first_diff = i + 1
                    break
            if first_diff is None and len(v_lines) != len(o_lines):
                first_diff = min(len(v_lines), len(o_lines)) + 1
            result.passed = False
            result.details.append(f"Drift: {vault_name} ↔ {ora_name} differ (first diff at line {first_diff})")
        elif verbose:
            version_match = re.search(
                r"(?im)^\s*[*_]?Version\s+([^\s*_]+)", vault_body
            )
            version = version_match.group(1) if version_match else "unversioned"
            digest = hashlib.sha256(vault_body.encode("utf-8")).hexdigest()
            result.details.append(
                f"OK: {vault_name} ↔ {ora_name} "
                f"[version={version}, sha256={digest}]"
            )

    return result


def _markdown_files_matching(
        searches: list[tuple[str, bool]], *,
        excluded_paths: Optional[set[str]] = None) -> dict[str, list[str]]:
    """Find vault Markdown matching several searches in one filesystem pass.

    The debt check concerns vault Markdown, so binary resources and repository
    internals are deliberately excluded. This also keeps the check available on
    a stock Windows install where ``grep`` is not present. Reading each note
    once matters on large or synced vaults, especially on Windows.
    """
    matchers = [
        (pattern, re.compile(pattern) if regex else None)
        for pattern, regex in searches
    ]
    matches = {pattern: [] for pattern, _regex in searches}
    for path in VAULT_ROOT.rglob("*.md"):
        normalized_path = path.as_posix()
        # The caller would discard these matches anyway. Avoid opening large
        # archived or otherwise excluded trees just to filter them afterward.
        if excluded_paths and any(
                excluded in normalized_path for excluded in excluded_paths):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern, matcher in matchers:
            if (matcher.search(content) if matcher else pattern in content):
                # Downstream exclusion rules use repository-style forward
                # slashes; normalize so they match native Windows paths.
                matches[pattern].append(normalized_path)
    return matches


def _markdown_files_containing(pattern: str, *, regex: bool = False) -> list[str]:
    """Single-search convenience wrapper used by focused verification."""
    return _markdown_files_matching([(pattern, regex)])[pattern]


def check_architectural_debt(verbose: bool = False) -> CheckResult:
    """Verify no active identifiers point at retired routing artifacts.

    Human-readable rename and retirement history is valid documentation. This
    check therefore targets executable identifiers and file paths, not every
    prose mention of the old display names.
    """
    result = CheckResult(name="debt", passed=True)

    # Stale reference patterns to check
    stale_patterns = [
        ("T19-visual-and-spatial-structure",
         "retired T19 identifier (renamed to T19-spatial-composition)"),
    ]

    # Files to exclude (archival locations + this script + the implementation plan + by-design retire mentions)
    excluded_paths = {
        "Archive",
        "Working — Analytical Territories and Modes Implementation Plan.md",
        "verify-implementation.py",
        "verify-implementation.md",
        "Reference — Implementation Verification Script.md",  # canonical of the script — describes what it searches
        ".obsidian/",  # Obsidian plugin data files
        ".git/",  # git internals (binary index, packed refs, etc.)
        ".bak",  # backup files
        "Reference — Pre-Routing Pipeline Architecture.md",  # by-design mention of retired directory
        "Reference — Architecture of Analytical Territories and Modes.md",  # research report — frozen historical record
        "Reference — Spatial Composition Modes and T19 Reanalysis.md",  # research report — references old name in rename note
        "Reference — T19 Reanalysis — Spatial Dynamics as Distinct Analytical Territory.md",  # research report
        "Reference — Mode Classification Directory.md",  # the file being archived itself
        "Framework — System File Drift Correction.md",  # registers the pair being archived
        "Reference — Analytical Territories.md",  # contains intentional rename note for T19
        "Working — Book — Analytical Methods Technical Outline.md",  # book chapter describing the retired directory and T19 by name (historical content)
        "Modes/spatial-reasoning.md",  # mode spec contains rename note
        "Reference — Mode Registry.md",  # rewritten Phase 7; cross-references retired directory by design (transition note)
        "Reference — Ora Overview and Document Registry.md",  # registry note about retired directory
        "Framework — Spatial Composition.md",  # T19 framework with rename note from old name
        "Framework — Structural Relationship Mapping.md",  # T11 framework with re-home note from old T19
        "Working — Reference — Practitioner's Field Manual Book Outline.md",  # TODO-flagged for Phase 7+ deep rewrite
        "Working — Reference — Natural Language Programming Book Outline.md",  # TODO-flagged for Phase 7+ deep rewrite
        "Working — Reference — The Adversarial AI Agent Book Outline.md",  # TODO-flagged for Phase 7+ deep rewrite
        "Working — Book — Analytical Methods Accessible Outline.md",  # TODO-flagged for Phase 7+ deep rewrite
        "Working — Framework — Mode Specification Rebuild Plan.md",  # historical plan; references retired Phase A.5
        "Reference — Pipeline Routing Test Corpus.md",  # 220-prompt corpus; tests behavior including legacy mentions
    }

    catch_all_patterns = {
        catch_all: rf"\b{re.escape(catch_all)}\.md\b"
        for catch_all in sorted(RETIRED_MODE_IDS)
    }
    searches = [(pattern, False) for pattern, _description in stale_patterns]
    searches.extend((pattern, True) for pattern in catch_all_patterns.values())
    matches = _markdown_files_matching(searches, excluded_paths=excluded_paths)

    for pattern, description in stale_patterns:
        # Search vault root + Modes + Lenses
        for line in matches[pattern]:
            if any(excl in line for excl in excluded_paths):
                continue
            result.passed = False
            result.details.append(f"Stale reference '{pattern}' in: {line}")

    retired_directory = ORA_ROOT / "frameworks" / "mode-classification-directory.md"
    if retired_directory.exists():
        result.passed = False
        result.details.append(
            f"Retired Mode Classification Directory still live: {retired_directory}")

    # Check for retired catch-all mode references in mode files / framework files
    for catch_all, pattern in catch_all_patterns.items():
        for line in matches[pattern]:
            if any(excl in line for excl in excluded_paths):
                continue
            if f"Modes/{catch_all}.md" in line:
                continue  # the file itself is allowed during transition
            if "Archive" in line:
                continue
            result.details.append(f"WARN: reference to catch-all '{catch_all}' in: {line}")

    return result


def check_routing_accuracy(verbose: bool = False) -> CheckResult:
    """Re-run the 220-prompt test corpus through the orchestrator.

    Phase 9: invokes scripts/run-corpus-routing-test.py and parses the
    overall accuracy. Passes when each stage is at or above 90%.
    """
    result = CheckResult(name="routing", passed=True)
    harness = ORA_ROOT / "scripts" / "run-corpus-routing-test.py"
    if not harness.exists():
        result.passed = False
        result.details.append(f"Corpus harness not found: {harness}")
        return result
    try:
        run = subprocess.run(
            [sys.executable, str(harness)],
            capture_output=True, text=True, timeout=300
        )
    except subprocess.TimeoutExpired:
        result.passed = False
        result.details.append("Corpus harness timeout (>5 min)")
        return result

    if run.returncode != 0:
        result.passed = False
        result.details.append(f"Harness failed (rc={run.returncode}): "
                              f"{run.stderr.strip()[:300]}")
        return result

    out = run.stdout
    stages = {}
    for line in out.split("\n"):
        m = re.match(r"^Stage (\d+): ([\d.]+)%", line.strip())
        if m:
            stages[int(m.group(1))] = float(m.group(2))

    for s in (1, 2, 3):
        pct = stages.get(s, 0.0)
        if pct < 90.0:
            result.passed = False
            result.details.append(f"Stage {s} accuracy {pct:.1f}% < 90% target")
        else:
            result.details.append(f"Stage {s} accuracy {pct:.1f}% (target met)")
    return result


def check_test_suites(verbose: bool = False) -> CheckResult:
    """Run Python and JS test suites."""
    result = CheckResult(name="tests", passed=True)

    # Python tests
    try:
        # pytest, not `unittest discover`: unittest never collected the eight
        # files that use module-level `def test_` functions, so this check
        # passed on ~61 fewer tests than exist. `-p no:cacheprovider` stops it
        # writing a .pytest_cache directory into the checkout under review.
        py_result = subprocess.run(
            [sys.executable, "-m", "pytest", "orchestrator/tests", "-q",
             "-p", "no:cacheprovider"],
            capture_output=True, text=True, cwd=str(ORA_ROOT), timeout=600
        )
        # unittest wrote its summary to stderr; pytest writes to stdout, so the
        # reported tail comes from stdout or this silently reports nothing.
        report = (py_result.stdout or py_result.stderr).strip()
        if py_result.returncode != 0:
            result.passed = False
            tail = report.split("\n")[-10:]
            result.details.append("Python tests FAILED. Tail:")
            result.details.extend(tail)
        else:
            tail = report.split("\n")[-3:]
            result.details.append(f"Python tests OK: {tail[-1] if tail else ''}")
    except subprocess.TimeoutExpired:
        result.passed = False
        result.details.append("Python test suite timeout (>10 min)")
    except FileNotFoundError as e:
        result.passed = False
        result.details.append(f"Python test runner not found: {e}")

    # JS tests
    js_test_dir = ORA_ROOT / "server" / "static" / "ora-visual-compiler" / "tests"
    if js_test_dir.exists():
        try:
            js_result = subprocess.run(
                ["node", "run.js"],
                capture_output=True, text=True, cwd=str(js_test_dir), timeout=300
            )
            if js_result.returncode != 0:
                result.passed = False
                tail = js_result.stdout.strip().split("\n")[-10:]
                result.details.append("JS tests FAILED. Tail:")
                result.details.extend(tail)
            else:
                tail = js_result.stdout.strip().split("\n")[-3:]
                result.details.append(f"JS tests OK: {tail[-1] if tail else ''}")
        except subprocess.TimeoutExpired:
            result.passed = False
            result.details.append("JS test suite timeout (>5 min)")

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

CHECK_FUNCTIONS = {
    "template": check_template_conformance,
    "crossref": check_crossref_resolution,
    "signals": check_signal_vocabulary,
    "runtime": check_runtime_config,
    "drift": check_drift_parity,
    "framework-pairs": check_framework_pair_manifest,
    "framework-pairs-audit": check_framework_pair_audit,
    "documentation-integrity": check_documentation_integrity,
    "debt": check_architectural_debt,
    "routing": check_routing_accuracy,
    "tests": check_test_suites,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", choices=list(CHECK_FUNCTIONS.keys()) + ["all"], default="all")
    parser.add_argument("--verbose", action="store_true")
    for repository_name in DOCUMENTATION_REPOSITORIES:
        parser.add_argument(
            f"--{repository_name}-root",
            help=(
                f"explicit {repository_name} task-worktree root; mandatory "
                "for --check documentation-integrity"
            ),
        )
        parser.add_argument(
            f"--{repository_name}-base",
            help=(
                f"full {repository_name} base commit; mandatory for "
                "--check documentation-integrity"
            ),
        )
    parser.add_argument(
        "--enqueue-framework-findings",
        action="store_true",
        help=(
            "atomically append authenticated findings to the existing DCP "
            "queue; valid only with --check framework-pairs or the narrow "
            "framework-pairs-audit"
        ),
    )
    args = parser.parse_args()

    if args.enqueue_framework_findings and args.check not in {
        "framework-pairs",
        "framework-pairs-audit",
    }:
        parser.error(
            "--enqueue-framework-findings requires --check framework-pairs "
            "or --check framework-pairs-audit"
        )

    documentation_roots = {
        name: getattr(args, f"{name}_root")
        for name in DOCUMENTATION_REPOSITORIES
        if getattr(args, f"{name}_root") is not None
    }
    documentation_bases = {
        name: getattr(args, f"{name}_base")
        for name in DOCUMENTATION_REPOSITORIES
        if getattr(args, f"{name}_base") is not None
    }
    if args.check == "documentation-integrity":
        if set(documentation_roots) != set(DOCUMENTATION_REPOSITORIES) or set(
            documentation_bases
        ) != set(DOCUMENTATION_REPOSITORIES):
            parser.error(
                "--check documentation-integrity requires all five explicit "
                "--<repo>-root and --<repo>-base arguments"
            )
    elif documentation_roots or documentation_bases:
        parser.error(
            "documentation task roots/bases are valid only with "
            "--check documentation-integrity"
        )

    if args.check == "all":
        # The five-root task gate has no defaults and is intentionally never
        # smuggled into the broad legacy `all` category.
        checks_to_run = [
            name
            for name in CHECK_FUNCTIONS
            if name not in {"documentation-integrity", "framework-pairs-audit"}
        ]
    else:
        checks_to_run = [args.check]

    print(f"Running {len(checks_to_run)} verification check(s)...\n")
    if args.check == "documentation-integrity":
        for name in DOCUMENTATION_REPOSITORIES:
            print(
                f"  {name:5} root: {documentation_roots[name]} "
                f"(base {documentation_bases[name]})"
            )
        print()
    else:
        print(f"  Vault root: {VAULT_ROOT}")
        print(f"  Ora root:   {ORA_ROOT}\n")

    results: list[CheckResult] = []
    for check_name in checks_to_run:
        check_fn = CHECK_FUNCTIONS[check_name]
        print(f"--- {check_name} ---")
        try:
            if check_name == "documentation-integrity":
                result = check_fn(
                    verbose=args.verbose,
                    roots=documentation_roots,
                    base_commits=documentation_bases,
                )
            else:
                result = check_fn(verbose=args.verbose)
        except Exception as e:
            result = CheckResult(name=check_name, passed=False)
            result.details.append(f"EXCEPTION: {e}")
        results.append(result)

        if result.skipped:
            print(f"  SKIPPED: {result.skip_reason}\n")
            continue

        status = "PASS" if result.passed else "FAIL"
        print(f"  {status}")
        if result.details and (args.verbose or not result.passed):
            for detail in result.details[:50]:
                print(f"    {detail}")
            if len(result.details) > 50:
                print(f"    ... and {len(result.details) - 50} more")
        print()

    if args.enqueue_framework_findings:
        try:
            appended, current = enqueue_framework_pair_findings()
        except (OSError, FrameworkManifestError) as exc:
            print(f"Queue write FAILED: {exc}\n")
            return 2
        print(
            "Queue write: "
            f"{appended} authenticated finding(s) appended; "
            f"{current} current finding(s); retry-safe.\n"
        )

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = [r for r in results if r.passed and not r.skipped]
    failed = [r for r in results if not r.passed and not r.skipped]
    skipped = [r for r in results if r.skipped]
    print(f"Passed:  {len(passed)} — {[r.name for r in passed]}")
    print(f"Failed:  {len(failed)} — {[r.name for r in failed]}")
    print(f"Skipped: {len(skipped)} — {[r.name for r in skipped]}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
