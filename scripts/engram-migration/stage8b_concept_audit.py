#!/usr/bin/env python3
"""Stage 8b — emit a complete deterministic standard-concept audit workload.

The artifact contains every active Stage 5 KEEP note with a nonempty normalized
``standard_concept``, grouped without deciding whether any label is valid.  It
is bound to both the active Stage 5 byte tree and the validated Stage 8 artifact.
"""
from __future__ import annotations

import argparse
import collections
import difflib
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

SINGLETON_IS_SUSPECT = 1
OVER_BROAD_MIN = 150
DRIFT_RATIO = 0.86
SCHEMA_VERSION = "ora-stage8b-concept-audit-v1"


def _load_stage8_module():
    path = Path(__file__).with_name("stage8_lexical.py")
    spec = importlib.util.spec_from_file_location("_ora_stage8_lexical", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Stage 8 implementation: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S8 = _load_stage8_module()


def _snapshot(row: dict) -> dict:
    return {
        "unit_id": row["unit_id"],
        "title": row["new_title"],
        "standard_concept": row["standard_concept"],
        "body": row["new_body"],
    }


def _drift_candidates(counts: collections.Counter[str]) -> list[dict]:
    buckets: dict[str, list[str]] = collections.defaultdict(list)
    for concept in sorted(counts):
        words = concept.split()
        buckets[words[0][:4] if words else ""].append(concept)
    candidates = []
    for key in sorted(buckets):
        concepts = buckets[key]
        for index, left in enumerate(concepts):
            for right in concepts[index + 1:]:
                ratio = difflib.SequenceMatcher(None, left, right).ratio()
                if ratio >= DRIFT_RATIO:
                    candidates.append({
                        "a": left,
                        "b": right,
                        "ratio": round(ratio, 6),
                        "a_count": counts[left],
                        "b_count": counts[right],
                    })
    return candidates


def build_artifact(rows: dict[str, dict], fingerprint: dict, stage8_sha256: str, over_broad: int) -> dict:
    if over_broad < 2:
        raise S8.Stage8Error("over-broad threshold must be at least 2")
    grouped: dict[str, list[dict]] = collections.defaultdict(list)
    for unit_id in sorted(rows):
        row = rows[unit_id]
        raw_concept = row["standard_concept"]
        concept = S8.norm_concept(raw_concept)
        if row["verdict"] == "KEEP" and raw_concept.strip() and not concept:
            raise S8.Stage8Error(
                f"nonempty standard_concept normalizes to empty for {unit_id}"
            )
        if row["verdict"] == "KEEP" and raw_concept.strip():
            grouped[concept].append(row)
    counts = collections.Counter({concept: len(members) for concept, members in grouped.items()})
    groups = []
    for index, concept in enumerate(sorted(grouped)):
        members = grouped[concept]
        variants = collections.Counter(row["standard_concept"] for row in members)
        groups.append({
            "audit_id": f"a{index:06d}",
            "normalized_concept": concept,
            "frequency": len(members),
            "review_flags": {
                "singleton": len(members) == SINGLETON_IS_SUSPECT,
                "over_broad": len(members) >= over_broad,
            },
            "raw_variants": [
                {"value": value, "count": count}
                for value, count in sorted(variants.items())
            ],
            "members": [_snapshot(row) for row in members],
        })
    workload_ids = [member["unit_id"] for group in groups for member in group["members"]]
    if len(workload_ids) != len(set(workload_ids)):
        raise S8.Stage8Error("concept audit contains duplicate note memberships")
    expected_ids = {
        unit_id for unit_id, row in rows.items()
        if row["verdict"] == "KEEP" and row["standard_concept"].strip()
    }
    if set(workload_ids) != expected_ids:
        raise S8.Stage8Error("concept audit does not exactly cover named KEEP notes")
    return {
        "schema": SCHEMA_VERSION,
        "stage5_fingerprint": fingerprint,
        "stage8_artifact": {
            "filename": "stage8_groups.json",
            "sha256": stage8_sha256,
            "schema": S8.SCHEMA_VERSION,
        },
        "parameters": {
            "singleton_frequency": SINGLETON_IS_SUSPECT,
            "over_broad_minimum": over_broad,
            "drift_ratio": DRIFT_RATIO,
        },
        "counts": {
            "keep_notes_with_standard_concept": len(workload_ids),
            "normalized_concepts": len(groups),
            "raw_concept_variants": len({row["standard_concept"] for members in grouped.values() for row in members}),
            "singleton_concepts": sum(group["review_flags"]["singleton"] for group in groups),
            "over_broad_concepts": sum(group["review_flags"]["over_broad"] for group in groups),
            "drift_candidates": len(_drift_candidates(counts)),
        },
        "drift_candidates": _drift_candidates(counts),
        "groups_canonical_json_sha256": hashlib.sha256(
            json.dumps(groups, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "groups": groups,
    }


def validate_audit(artifact: object, expected: dict) -> None:
    if artifact != expected:
        raise S8.Stage8Error("concept audit fails deterministic integrity validation")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migration", default=str(Path.home() / "engram-work" / ".migration"))
    parser.add_argument("--over-broad", type=int, default=OVER_BROAD_MIN)
    args = parser.parse_args()
    migration = Path(args.migration)
    stage8_path = migration / "stage8_groups.json"
    destination = migration / "concept_audit.json"
    started = time.monotonic()
    try:
        rows, fingerprint = S8.load_stage5(migration / "stage5")
        stage8 = S8.read_json(stage8_path, "Stage 8 artifact")
        S8.validate_artifact(stage8, rows, fingerprint)
        stage8_sha256 = S8.file_sha256(stage8_path)
        artifact = build_artifact(rows, fingerprint, stage8_sha256, args.over_broad)
        S8.atomic_write(destination, S8.json_bytes(artifact))
        validate_audit(S8.read_json(destination, "written concept audit"), artifact)
    except (S8.Stage8Error, RuntimeError) as exc:
        print(f"[stage8b] failed: {exc}", file=sys.stderr)
        return 1
    counts = artifact["counts"]
    print(f"[stage8b] Stage 5 fingerprint: {fingerprint['sha256']}")
    print(f"[stage8b] Stage 8 artifact sha256: {stage8_sha256}")
    print(
        f"[stage8b] named KEEP notes={counts['keep_notes_with_standard_concept']:,} "
        f"normalized concepts={counts['normalized_concepts']:,} "
        f"raw variants={counts['raw_concept_variants']:,}"
    )
    print(f"[stage8b] wrote {destination} sha256={S8.file_sha256(destination)} in {time.monotonic()-started:.3f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
