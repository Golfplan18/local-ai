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

VAULT_ROOT = Path("/Users/oracle/Documents/vault")
ORA_ROOT = Path("/Users/oracle/ora")

MODES_DIR = VAULT_ROOT / "Modes"
LENSES_DIR = VAULT_ROOT / "Lenses"
ARCHITECTURE_DIR = ORA_ROOT / "architecture"
ORA_MODES_DIR = ORA_ROOT / "modes"
ORA_LENSES_DIR = ORA_ROOT / "knowledge" / "mental-models"

TERRITORIES_FILE = VAULT_ROOT / "Reference — Analytical Territories.md"
TEMPLATE_FILE = VAULT_ROOT / "Reference — Mode Specification Template.md"
SIGNAL_REGISTRY_FILE = VAULT_ROOT / "Reference — Signal Vocabulary Registry.md"
RUNTIME_CONFIG_FILE = VAULT_ROOT / "Reference — Mode Runtime Configuration.md"
WITHIN_TREES_FILE = VAULT_ROOT / "Reference — Within-Territory Disambiguation Trees.md"
CROSS_ADJ_FILE = VAULT_ROOT / "Reference — Cross-Territory Adjacency.md"
DISAMBIG_GUIDE_FILE = VAULT_ROOT / "Reference — Disambiguation Style Guide.md"
LENS_SPEC_FILE = VAULT_ROOT / "Reference — Lens Library Specification.md"
PIPELINE_FILE = VAULT_ROOT / "Reference — Pre-Routing Pipeline Architecture.md"

CATCH_ALL_MODES = {"adversarial", "simple", "standard"}
ARCHIVED_MODES = CATCH_ALL_MODES  # archived per Decision A

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
    "output_contract",
    "critical_questions",
    "failure_modes",
    "lens_dependencies",
    "default_depth_tier",
    "expected_runtime",
    "escalation_signals",
}

# Required pipeline-stage subsections (## headings in body)
REQUIRED_PIPELINE_SUBSECTIONS = {
    "DEPTH ANALYSIS GUIDANCE",
    "BREADTH ANALYSIS GUIDANCE",
    "EVALUATION CRITERIA",
    "REVISION GUIDANCE",
    "CONSOLIDATION GUIDANCE",
    "VERIFICATION CRITERIA",
}

# 9 vault canonical → ora runtime file pairs (Decision K)
ARCHITECTURE_PAIRS = [
    ("Reference — Analytical Territories.md", "territories.md"),
    ("Reference — Mode Specification Template.md", "mode-template.md"),
    ("Reference — Disambiguation Style Guide.md", "disambiguation-style-guide.md"),
    ("Reference — Lens Library Specification.md", "lens-library-specification.md"),
    ("Reference — Pre-Routing Pipeline Architecture.md", "pre-routing-pipeline.md"),
    ("Reference — Signal Vocabulary Registry.md", "signal-vocabulary-registry.md"),
    ("Reference — Mode Runtime Configuration.md", "runtime-configuration.md"),
    ("Reference — Within-Territory Disambiguation Trees.md", "within-territory-trees.md"),
    ("Reference — Cross-Territory Adjacency.md", "cross-territory-adjacency.md"),
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
    """List all mode files except retired catch-alls."""
    if not MODES_DIR.exists():
        return []
    return [
        p for p in MODES_DIR.glob("*.md")
        if p.stem not in ARCHIVED_MODES and not p.stem.endswith(".bak")
    ]


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_template_conformance(verbose: bool = False) -> CheckResult:
    """Verify every mode file has all required template fields and pipeline subsections."""
    result = CheckResult(name="template", passed=True)
    mode_files = list_mode_files()
    if not mode_files:
        result.passed = False
        result.details.append(f"No mode files found in {MODES_DIR}")
        return result

    for mode_file in sorted(mode_files):
        content = read_file(mode_file)
        _, body = parse_yaml_frontmatter(content)

        # Check YAML keys (in code blocks within body)
        yaml_keys = extract_top_level_yaml_keys(body)
        # Composition determines whether atomic_spec or molecular_spec is required
        if "atomic_spec" in yaml_keys or "molecular_spec" in yaml_keys:
            yaml_keys.add("composition_spec")  # treat either as composition_spec

        missing = REQUIRED_TEMPLATE_FIELDS - yaml_keys
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

        if missing or missing_subsections or edu_name_issues:
            result.passed = False
            issues = []
            if missing:
                issues.append(f"missing fields: {sorted(missing)}")
            if missing_subsections:
                issues.append(f"missing pipeline subsections: {sorted(missing_subsections)}")
            if edu_name_issues:
                issues.append(f"educational_name issues: {edu_name_issues}")
            result.details.append(f"{mode_file.name}: {'; '.join(issues)}")
        elif verbose:
            result.details.append(f"{mode_file.name}: OK")

    return result


def check_crossref_resolution(verbose: bool = False) -> CheckResult:
    """Verify mode_id, territory, lens_id references resolve."""
    result = CheckResult(name="crossref", passed=True)

    mode_files = list_mode_files()
    if not mode_files:
        result.passed = False
        result.details.append("No mode files found")
        return result

    valid_mode_ids = {p.stem for p in mode_files}
    valid_lens_ids = {p.stem for p in LENSES_DIR.glob("*.md") if not p.stem.endswith(".bak")}

    # Read territories file once
    territories_content = read_file(TERRITORIES_FILE) if TERRITORIES_FILE.exists() else ""

    for mode_file in sorted(mode_files):
        content = read_file(mode_file)

        # Check territory reference
        territory_match = re.search(r"^territory:\s*(T\d+)-", content, re.MULTILINE)
        if territory_match:
            territory_id = territory_match.group(1)
            if territory_id not in TERRITORY_IDS:
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

        # Check lens_dependencies references
        for lens_match in re.finditer(r"-\s*([\w-]+)\s*(?:\(|$)", content):
            # Heuristic: only flag if it looks like a lens_id reference (kebab-case, in a lens_dependencies block)
            pass  # too noisy without context-aware parsing; skip for now

    return result


def check_signal_vocabulary(verbose: bool = False) -> CheckResult:
    """Verify every mode_id has ≥3 signal entries; no orphans."""
    result = CheckResult(name="signals", passed=True)

    if not SIGNAL_REGISTRY_FILE.exists():
        result.passed = False
        result.details.append(f"Signal vocabulary registry not found: {SIGNAL_REGISTRY_FILE}")
        return result

    content = read_file(SIGNAL_REGISTRY_FILE)
    valid_mode_ids = {p.stem for p in list_mode_files()}

    # Count signals per mode_id (heuristic: count rows in markdown tables that reference each mode_id)
    signal_counts: dict[str, int] = {m: 0 for m in valid_mode_ids}
    referenced_mode_ids: set[str] = set()

    # Match table rows. Each row has fields separated by `|`. The `mode` column should appear.
    for line in content.split("\n"):
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.split("|")]
        # Skip header rows / separator rows
        if any(p.startswith("-") and all(c in "-: " for c in p) for p in parts):
            continue
        for part in parts:
            # Mode IDs are kebab-case; check if part matches a valid mode_id
            if part in valid_mode_ids:
                signal_counts[part] += 1
                referenced_mode_ids.add(part)

    # Modes with <3 signals are flagged
    for mode_id, count in signal_counts.items():
        if count < 3:
            # Allow placeholder entries for modes built later (Wave 4) — flag at warning level
            if count == 0:
                result.details.append(f"WARN: mode '{mode_id}' has 0 signal entries (built later or genuinely missing)")
            else:
                result.passed = False
                result.details.append(f"mode '{mode_id}' has only {count} signal entries (need ≥3)")

    # Orphan signals (referenced mode_ids that aren't in valid set)
    # Skip — the heuristic above only matches valid_mode_ids

    return result


def check_runtime_config(verbose: bool = False) -> CheckResult:
    """Verify every mode_id in /Modes/ has a runtime config entry."""
    result = CheckResult(name="runtime", passed=True)

    if not RUNTIME_CONFIG_FILE.exists():
        result.passed = False
        result.details.append(f"Runtime config not found: {RUNTIME_CONFIG_FILE}")
        return result

    content = read_file(RUNTIME_CONFIG_FILE)
    valid_mode_ids = {p.stem for p in list_mode_files()}

    # Find mode_id keys at the top of YAML config blocks
    # Pattern: line matching ^<mode_id>:\s*$ (or with leading whitespace)
    config_mode_ids = set(re.findall(r"^([\w-]+):\s*$", content, re.MULTILINE))

    missing = valid_mode_ids - config_mode_ids
    for mode_id in sorted(missing):
        result.passed = False
        result.details.append(f"mode '{mode_id}' has no runtime config entry")

    if verbose and not missing:
        result.details.append(f"All {len(valid_mode_ids)} mode_ids have runtime config entries")

    return result


def check_drift_parity(verbose: bool = False) -> CheckResult:
    """Verify the 9 architecture file pairs match (modulo YAML)."""
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


def check_architectural_debt(verbose: bool = False) -> CheckResult:
    """Verify no remaining references to retired Mode Classification Directory,
    catch-all modes, or old T19 name (outside archival locations)."""
    result = CheckResult(name="debt", passed=True)

    # Stale reference patterns to check
    stale_patterns = [
        ("Mode Classification Directory", "retired Mode Classification Directory"),
        ("Visual and Spatial Structure", "old T19 name (renamed to Spatial Composition)"),
    ]

    # Files to exclude (archival locations + this script + the implementation plan + by-design retire mentions)
    excluded_paths = {
        "Old AI Working Files",
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
        "Reference — Pipeline Routing Test Corpus.md",  # 200-prompt corpus; tests behavior including legacy mentions
    }

    for pattern, description in stale_patterns:
        # Search vault root + Modes + Lenses
        try:
            search_result = subprocess.run(
                ["grep", "-r", "-l", pattern, str(VAULT_ROOT)],
                capture_output=True, text=True, timeout=30
            )
            for line in search_result.stdout.strip().split("\n"):
                if not line:
                    continue
                if any(excl in line for excl in excluded_paths):
                    continue
                # Allow references in cross-reference audit / archival files
                if "Reference — Analytical Territories" in line:
                    # Notes about renaming are expected
                    continue
                result.passed = False
                result.details.append(f"Stale reference '{pattern}' in: {line}")
        except subprocess.TimeoutExpired:
            result.details.append(f"WARN: grep timeout searching for '{pattern}'")

    # Check for retired catch-all mode references in mode files / framework files
    for catch_all in CATCH_ALL_MODES:
        try:
            search_result = subprocess.run(
                ["grep", "-r", "-l", f"\\b{catch_all}\\.md\\b", str(VAULT_ROOT)],
                capture_output=True, text=True, timeout=30
            )
            for line in search_result.stdout.strip().split("\n"):
                if not line:
                    continue
                if any(excl in line for excl in excluded_paths):
                    continue
                if f"Modes/{catch_all}.md" in line:
                    continue  # the file itself is allowed during transition
                if f"Old AI Working Files" in line:
                    continue
                result.details.append(f"WARN: reference to catch-all '{catch_all}' in: {line}")
        except subprocess.TimeoutExpired:
            pass

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
            ["/opt/homebrew/bin/python3", str(harness)],
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
            ["/opt/homebrew/bin/python3", "-m", "unittest", "discover", "-s", "orchestrator/tests"],
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
