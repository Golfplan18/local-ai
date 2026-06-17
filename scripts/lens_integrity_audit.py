#!/usr/bin/env python3
"""Audit Ora mode-to-lens integrity against the runtime lens library.

The picker exposes lenses from two sources:
  - direct mode declarations in ``modes/*`` under ``lens_dependencies``
  - inverse declarations in ``knowledge/mental-models/*`` under
    ``applicability``

This script reports both surfaces and keeps unresolved direct declarations
visible so data/library drift cannot hide behind the UI.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MODE_DIR = ROOT / "modes"
LENS_DIR = ROOT / "knowledge" / "mental-models"


def _strip_dependency_note(raw_value: str) -> str:
    value = (raw_value or "").strip()
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        value = value[1:-1].strip()
    return re.sub(r"\s+\([^)]*\)\s*$", "", value).strip()


def _extract_lens_dependencies(text: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    start = None
    base_indent = 0
    for idx, line in enumerate(lines):
        if re.match(r"^\s*lens_dependencies:\s*$", line):
            start = idx + 1
            base_indent = len(line) - len(line.lstrip())
            break
    if start is None:
        return []

    rows: list[dict[str, str]] = []
    category = ""
    for line in lines[start:]:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if indent <= base_indent and not stripped.startswith("-"):
            break

        header = re.match(r"^(required|optional|foundational):(?:\s*\[\])?\s*$", stripped)
        if header:
            category = header.group(1)
            continue

        bullet = re.match(r"^-\s+(.+?)\s*$", stripped)
        if not bullet or not category:
            continue
        raw = bullet.group(1).strip()
        lens_id = _strip_dependency_note(raw)
        if lens_id:
            rows.append({
                "id": lens_id,
                "category": category,
                "raw": raw,
            })
    return rows


def _extract_lens_applicability(text: str) -> list[str]:
    inline = re.search(r"^applicability:\s*\[(.*?)\]\s*$", text, re.M)
    if inline:
        return [
            item.strip().strip("'\"")
            for item in inline.group(1).split(",")
            if item.strip()
        ]

    block = re.search(r"^applicability:\s*\n((?:\s+-\s+.+\n?)+)", text, re.M)
    if not block:
        return []
    return [
        re.sub(r"^\s+-\s+", "", line).strip().strip("'\"")
        for line in block.group(1).splitlines()
        if line.strip()
    ]


def _mode_files(root: Path) -> list[Path]:
    return sorted((root / "modes").glob("*.md"))


def _lens_files(root: Path) -> list[Path]:
    return sorted((root / "knowledge" / "mental-models").glob("*.md"))


def build_report(root: Path = ROOT) -> dict[str, Any]:
    mode_paths = _mode_files(root)
    lens_paths = _lens_files(root)
    lens_ids = {path.stem for path in lens_paths}
    mode_ids = {path.stem for path in mode_paths}

    inverse_by_mode: dict[str, list[str]] = defaultdict(list)
    nonmode_applicability: list[dict[str, str]] = []
    for path in lens_paths:
        text = path.read_text(encoding="utf-8")
        for target in _extract_lens_applicability(text):
            if target in mode_ids:
                inverse_by_mode[target].append(path.stem)
            else:
                nonmode_applicability.append({
                    "lens": path.stem,
                    "applicability": target,
                })

    mode_rows: list[dict[str, Any]] = []
    unresolved_counter: Counter[str] = Counter()
    unresolved_modes: dict[str, list[dict[str, str]]] = defaultdict(list)
    direct_resolved_count = 0
    declared_count = 0
    inverse_visible_count = 0

    for path in mode_paths:
        mode_id = path.stem
        deps = _extract_lens_dependencies(path.read_text(encoding="utf-8"))
        declared_count += len(deps)
        direct: list[dict[str, str]] = []
        unresolved: list[dict[str, str]] = []
        seen_visible: set[str] = set()

        for dep in deps:
            if dep["id"] in lens_ids:
                direct.append(dep)
                direct_resolved_count += 1
                seen_visible.add(dep["id"])
            else:
                unresolved.append(dep)
                unresolved_counter[dep["id"]] += 1
                unresolved_modes[dep["id"]].append({
                    "mode": mode_id,
                    "category": dep["category"],
                    "raw": dep["raw"],
                })

        inverse = []
        for lens_id in sorted(inverse_by_mode.get(mode_id, [])):
            if lens_id in seen_visible:
                continue
            inverse.append({
                "id": lens_id,
                "category": "related",
            })
            inverse_visible_count += 1

        mode_rows.append({
            "mode": mode_id,
            "direct": direct,
            "inverse": inverse,
            "unresolved": unresolved,
            "visible_count": len(direct) + len(inverse),
        })

    unresolved_by_id = []
    for lens_id, count in unresolved_counter.most_common():
        categories = Counter(item["category"] for item in unresolved_modes[lens_id])
        unresolved_by_id.append({
            "id": lens_id,
            "count": count,
            "categories": dict(categories),
            "modes": unresolved_modes[lens_id],
        })

    summary = {
        "mode_count": len(mode_paths),
        "lens_count": len(lens_paths),
        "declared_links": declared_count,
        "direct_resolved_links": direct_resolved_count,
        "inverse_visible_links": inverse_visible_count,
        "visible_links": direct_resolved_count + inverse_visible_count,
        "unresolved_declared_links": sum(unresolved_counter.values()),
        "unique_unresolved_ids": len(unresolved_counter),
        "modes_with_unresolved": sum(1 for row in mode_rows if row["unresolved"]),
        "nonmode_applicability_entries": len(nonmode_applicability),
    }
    return {
        "summary": summary,
        "unresolved_by_id": unresolved_by_id,
        "modes": mode_rows,
        "nonmode_applicability": nonmode_applicability,
    }


def _print_text(report: dict[str, Any], top: int) -> None:
    summary = report["summary"]
    print("Lens integrity audit")
    print("====================")
    for key in (
        "mode_count",
        "lens_count",
        "declared_links",
        "direct_resolved_links",
        "inverse_visible_links",
        "visible_links",
        "unresolved_declared_links",
        "unique_unresolved_ids",
        "modes_with_unresolved",
        "nonmode_applicability_entries",
    ):
        print(f"{key}: {summary[key]}")

    unresolved = report["unresolved_by_id"][:top]
    if not unresolved:
        print("\nNo unresolved direct lens dependencies.")
        return
    print(f"\nTop {len(unresolved)} unresolved direct lens dependencies")
    for row in unresolved:
        modes = ", ".join(item["mode"] for item in row["modes"][:8])
        categories = ", ".join(
            f"{category}={count}"
            for category, count in sorted(row["categories"].items())
        )
        print(f"- {row['id']} ({row['count']}; {categories}) :: {modes}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--top", type=int, default=30)
    args = parser.parse_args()

    report = build_report(args.root)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_text(report, args.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
