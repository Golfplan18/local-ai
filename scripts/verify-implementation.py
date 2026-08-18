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
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
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
FRAMEWORK_PAIR_DISPOSITIONS = {"paired", "missing_runtime", "no_runtime_twin"}
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
FRAMEWORK_RECEIPT_PATTERN = re.compile(
    r"<!-- dcp-framework-finding-receipt (\{.*?\}) -->"
)

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


def _normalized_framework_body(path: Path, *, strip_vault_yaml: bool) -> str:
    """Return the exact G1.13 comparison body.

    Newlines are normalized, vault frontmatter and its one separator blank line
    are removed, and terminal newline count is ignored. No prose, headings,
    interior whitespace, ordering, or links are normalized.
    """
    content = read_file(path).replace("\r\n", "\n").replace("\r", "\n")
    if strip_vault_yaml and content.startswith("---\n"):
        end = content.find("\n---\n", 4)
        if end == -1:
            raise FrameworkManifestError(
                f"unterminated vault YAML frontmatter: {path}"
            )
        content = content[end + 5:]
        if content.startswith("\n"):
            content = content[1:]
    return content.rstrip("\n")


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
    if not isinstance(expected_counts, dict) or set(expected_counts) != {
        "active_frameworks",
        "missing_runtime",
        "no_runtime_twin",
        "paired",
        "total_entries",
    }:
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
        canonical_digest = _sha256_text(
            _normalized_framework_body(canonical, strip_vault_yaml=True)
        )
        if entry.disposition == "no_runtime_twin":
            no_runtime_twin += 1
            continue
        assert runtime is not None
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
        canonical_body = _normalized_framework_body(canonical, strip_vault_yaml=True)
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
            f"no-twin={evaluation.no_runtime_twin}, "
            f"findings={len(evaluation.findings)}",
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
        raise FrameworkManifestError(
            f"escalation queue lock already exists: {lock}"
        ) from exc
    os.close(lock_fd)
    temp: Optional[Path] = None
    try:
        evaluation = evaluate_framework_pair_manifest(
            manifest_path=manifest_path,
            vault_root=vault_root,
            ora_root=ora_root,
        )
        content = read_file(queue)
        existing = verify_framework_finding_receipts(content)
        existing_identities = {
            _framework_finding_identity(finding.payload) for finding in existing
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
        py_result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "orchestrator/tests"],
            capture_output=True, text=True, cwd=str(ORA_ROOT), timeout=600
        )
        if py_result.returncode != 0:
            result.passed = False
            tail = py_result.stderr.strip().split("\n")[-10:]
            result.details.append("Python tests FAILED. Tail:")
            result.details.extend(tail)
        else:
            tail = py_result.stderr.strip().split("\n")[-3:]
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
    "debt": check_architectural_debt,
    "routing": check_routing_accuracy,
    "tests": check_test_suites,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", choices=list(CHECK_FUNCTIONS.keys()) + ["all"], default="all")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--enqueue-framework-findings",
        action="store_true",
        help=(
            "atomically append authenticated findings to the existing DCP "
            "queue; valid only with --check framework-pairs"
        ),
    )
    args = parser.parse_args()

    if args.enqueue_framework_findings and args.check != "framework-pairs":
        parser.error(
            "--enqueue-framework-findings requires --check framework-pairs"
        )

    if args.check == "all":
        checks_to_run = list(CHECK_FUNCTIONS.keys())
    else:
        checks_to_run = [args.check]

    print(f"Running {len(checks_to_run)} verification check(s)...\n")
    print(f"  Vault root: {VAULT_ROOT}")
    print(f"  Ora root:   {ORA_ROOT}\n")

    results: list[CheckResult] = []
    for check_name in checks_to_run:
        check_fn = CHECK_FUNCTIONS[check_name]
        print(f"--- {check_name} ---")
        try:
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
