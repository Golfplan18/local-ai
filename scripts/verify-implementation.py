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
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ORA_ROOT = Path(
    os.environ.get("ORA_HOME") or Path(__file__).resolve().parents[1]
).expanduser().resolve()
VAULT_ROOT = Path(
    os.environ.get("ORA_VAULT_PATH")
    or os.environ.get("ORA_VAULT")
    or (Path.home() / "Documents" / "vault")
).expanduser().resolve()

MODES_DIR = VAULT_ROOT / "Modes"
LENSES_DIR = VAULT_ROOT / "Lenses"
ARCHITECTURE_DIR = ORA_ROOT / "architecture"
ORA_MODES_DIR = ORA_ROOT / "modes"
ORA_LENSES_DIR = ORA_ROOT / "knowledge" / "mental-models"

TERRITORIES_FILE = VAULT_ROOT / "Reference — Analytical Territories.md"
TEMPLATE_FILE = VAULT_ROOT / "Reference — Mode Specification Template.md"
SIGNAL_REGISTRY_FILE = VAULT_ROOT / "Registry — Signal Vocabulary Registry.md"
MODE_REGISTRY_FILE = VAULT_ROOT / "Registry — Mode Registry.md"
WITHIN_TREES_FILE = VAULT_ROOT / "Reference — Within-Territory Disambiguation Trees.md"
CROSS_ADJ_FILE = VAULT_ROOT / "Reference — Cross-Territory Adjacency.md"
DISAMBIG_GUIDE_FILE = VAULT_ROOT / "Reference — Disambiguation Style Guide.md"
LENS_SPEC_FILE = VAULT_ROOT / "Reference — Lens Library Specification.md"
PIPELINE_FILE = VAULT_ROOT / "Reference — Pre-Routing Pipeline Architecture.md"

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

# 9 vault canonical → Ora runtime architecture pairs
ARCHITECTURE_PAIRS = [
    ("Reference — Analytical Territories.md", "territories.md"),
    ("Reference — Mode Specification Template.md", "mode-template.md"),
    ("Reference — Disambiguation Style Guide.md", "disambiguation-style-guide.md"),
    ("Reference — Lens Library Specification.md", "lens-library-specification.md"),
    ("Reference — Pre-Routing Pipeline Architecture.md", "pre-routing-pipeline.md"),
    ("Registry — Signal Vocabulary Registry.md", "signal-vocabulary-registry.md"),
    ("Reference — Within-Territory Disambiguation Trees.md", "within-territory-trees.md"),
    ("Reference — Cross-Territory Adjacency.md", "cross-territory-adjacency.md"),
    ("Reference — Trusted Web Sources.md", "trusted-web-sources.md"),
]


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
    """Verify the 9 architecture file pairs match (modulo vault YAML)."""
    result = CheckResult(name="drift", passed=True)

    for vault_name, ora_name in ARCHITECTURE_PAIRS:
        vault_path = VAULT_ROOT / vault_name
        ora_path = ARCHITECTURE_DIR / ora_name

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
            result.details.append(f"OK: {vault_name} ↔ {ora_name}")

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
    "debt": check_architectural_debt,
    "routing": check_routing_accuracy,
    "tests": check_test_suites,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", choices=list(CHECK_FUNCTIONS.keys()) + ["all"], default="all")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

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
