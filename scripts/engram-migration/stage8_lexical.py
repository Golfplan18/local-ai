#!/usr/bin/env python3
"""Stage 8 — build a lossless deterministic cross-domain merge workload.

This one-time migration stage reads the complete active Stage 5 result tree,
derives three candidate signals, proves that the serialized groups cover their
exact edge union, and atomically replaces ``stage8_groups.json``.  It never
modifies notes and never decides a merge.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable

DEFAULT_JACCARD = 0.25
EXPECTED_ROWS = 64_417
EXPECTED_KEEP = 64_144
EXPECTED_ARCHIVE = 273
SCHEMA_VERSION = "ora-stage8-lossless-v1"
FINGERPRINT_FRAMING = "uint64be(name_bytes)+name+uint64be(content_bytes)+content"
UNIT_ID = re.compile(r"^u\d{6}(?:\.\d{2})?$")
RESULT_NAME = re.compile(
    r"^(?:result_preserved_\d{6}|result_u\d{6}(?:_\d{2})?)\.json$"
)
REQUIRED_ROW_KEYS = {
    "unit_id", "verdict", "standard_concept", "new_title", "new_body",
    "facets_absorbed", "note",
}
OPTIONAL_ROW_KEYS = {"member_files"}

STOP = set("""a an the of to in and or that is are for by with as on it this be can when
not from their there they which who what into than more most rather only its each every
those these such over under between within without through across against about""".split())


class Stage8Error(RuntimeError):
    """A fail-closed input or integrity failure."""


def content_words(value: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z]+", value.lower())
        if word not in STOP and len(word) > 3
    }


def _stem(word: str) -> str:
    if len(word) <= 4:
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("ing"):
        return word[:-3]
    if word.endswith(("ses", "xes", "zes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def norm_concept(value: str) -> str:
    value = re.sub(r"\(.*?\)", "", value).strip().lower()
    value = re.sub(r"^(the|a|an)\s+", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(_stem(word) for word in value.split()).strip()


def _require_string(row: dict, key: str, where: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise Stage8Error(f"{where}: {key} must be a string")
    return value


def _validate_row(row: object, where: str) -> dict:
    if not isinstance(row, dict):
        raise Stage8Error(f"{where}: row must be an object")
    keys = set(row)
    if not REQUIRED_ROW_KEYS <= keys or keys - REQUIRED_ROW_KEYS - OPTIONAL_ROW_KEYS:
        missing = sorted(REQUIRED_ROW_KEYS - keys)
        extra = sorted(keys - REQUIRED_ROW_KEYS - OPTIONAL_ROW_KEYS)
        raise Stage8Error(f"{where}: schema keys missing={missing!r} extra={extra!r}")
    unit_id = _require_string(row, "unit_id", where)
    if not UNIT_ID.fullmatch(unit_id):
        raise Stage8Error(f"{where}: invalid unit_id {unit_id!r}")
    verdict = _require_string(row, "verdict", where)
    if verdict not in {"KEEP", "ARCHIVE"}:
        raise Stage8Error(f"{where}: invalid verdict {verdict!r}")
    for key in ("standard_concept", "new_title", "new_body", "note"):
        _require_string(row, key, where)
    facets = row["facets_absorbed"]
    if isinstance(facets, bool) or not isinstance(facets, int) or facets < 0:
        raise Stage8Error(f"{where}: facets_absorbed must be a nonnegative integer")
    if verdict == "KEEP" and (not row["new_title"].strip() or not row["new_body"].strip()):
        raise Stage8Error(f"{where}: KEEP row requires nonempty new_title and new_body")
    if "member_files" in row:
        members = row["member_files"]
        if (
            not isinstance(members, list)
            or any(not isinstance(item, str) or not item for item in members)
            or len(members) != len(set(members))
        ):
            raise Stage8Error(f"{where}: member_files must be a list of unique nonempty strings")
    return row


def _update_fingerprint(digest: "hashlib._Hash", name: str, payload: bytes) -> None:
    encoded = name.encode("utf-8")
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)
    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)


def _strict_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise Stage8Error(f"duplicate JSON object key: {key!r}")
        value[key] = item
    return value


def _invalid_json_constant(value: str) -> None:
    raise Stage8Error(f"non-standard JSON constant: {value}")


def load_stage5(
    stage5: Path,
    expected_rows: int = EXPECTED_ROWS,
    expected_keep: int = EXPECTED_KEEP,
    expected_archive: int = EXPECTED_ARCHIVE,
) -> tuple[dict[str, dict], dict]:
    """Load the entire flat Stage 5 tree or fail without returning partial data."""
    if stage5.is_symlink() or not stage5.is_dir():
        raise Stage8Error(f"Stage 5 directory is missing or unsafe: {stage5}")
    try:
        entries = sorted(stage5.iterdir(), key=lambda item: item.name)
    except OSError as exc:
        raise Stage8Error(f"cannot enumerate Stage 5 directory {stage5}: {exc}") from exc
    if not entries:
        raise Stage8Error(f"Stage 5 directory is empty: {stage5}")

    digest = hashlib.sha256()
    rows: dict[str, dict] = {}
    verdicts: collections.Counter[str] = collections.Counter()
    total_bytes = 0
    for path in entries:
        if path.is_symlink() or not path.is_file() or not RESULT_NAME.fullmatch(path.name):
            raise Stage8Error(f"unexpected Stage 5 entry: {path}")
        try:
            payload = path.read_bytes()
            decoded = json.loads(
                payload,
                object_pairs_hook=_strict_object,
                parse_constant=_invalid_json_constant,
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise Stage8Error(f"malformed Stage 5 result {path}: {exc}") from exc
        if not isinstance(decoded, list):
            raise Stage8Error(f"Stage 5 result is not an array: {path}")
        _update_fingerprint(digest, path.name, payload)
        total_bytes += len(payload)
        for index, candidate in enumerate(decoded):
            row = _validate_row(candidate, f"{path.name}[{index}]")
            unit_id = row["unit_id"]
            if unit_id in rows:
                raise Stage8Error(f"duplicate Stage 5 unit_id: {unit_id}")
            rows[unit_id] = row
            verdicts[row["verdict"]] += 1

    # Stage 5 writers publish atomically, but a concurrent tree replacement
    # could otherwise bind rows from one instant to a filename list from
    # another.  Re-read the exact flat tree and require byte-for-byte stability.
    verification = hashlib.sha256()
    try:
        final_entries = sorted(stage5.iterdir(), key=lambda item: item.name)
    except OSError as exc:
        raise Stage8Error(f"cannot re-enumerate Stage 5 directory {stage5}: {exc}") from exc
    if [path.name for path in final_entries] != [path.name for path in entries]:
        raise Stage8Error("Stage 5 tree changed while it was being loaded")
    for path in final_entries:
        if path.is_symlink() or not path.is_file() or not RESULT_NAME.fullmatch(path.name):
            raise Stage8Error(f"unexpected Stage 5 entry during verification: {path}")
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise Stage8Error(f"cannot verify Stage 5 result {path}: {exc}") from exc
        _update_fingerprint(verification, path.name, payload)
    if verification.digest() != digest.digest():
        raise Stage8Error("Stage 5 tree changed while it was being loaded")

    actual = (len(rows), verdicts["KEEP"], verdicts["ARCHIVE"])
    expected = (expected_rows, expected_keep, expected_archive)
    if actual != expected:
        raise Stage8Error(
            "Stage 5 corpus counts differ from the required complete corpus: "
            f"rows/KEEP/ARCHIVE={actual!r}, expected={expected!r}"
        )
    return rows, {
        "algorithm": "sha256",
        "framing": FINGERPRINT_FRAMING,
        "files": len(entries),
        "bytes": total_bytes,
        "rows": len(rows),
        "verdicts": {"KEEP": verdicts["KEEP"], "ARCHIVE": verdicts["ARCHIVE"]},
        "sha256": digest.hexdigest(),
    }


def member_snapshot(row: dict) -> dict:
    return {
        "unit_id": row["unit_id"],
        "title": row["new_title"],
        "standard_concept": row["standard_concept"],
        "body": row["new_body"],
    }


def _pairs(members: Iterable[str]) -> set[tuple[str, str]]:
    ordered = sorted(members)
    return {(a, b) for index, a in enumerate(ordered) for b in ordered[index + 1:]}


def derive_signals(notes: dict[str, dict], threshold: float) -> dict:
    if not 0.0 <= threshold <= 1.0:
        raise Stage8Error("Jaccard threshold must be between 0 and 1")
    by_concept: dict[str, list[str]] = collections.defaultdict(list)
    by_parent: dict[str, list[str]] = collections.defaultdict(list)
    for unit_id, row in notes.items():
        concept = norm_concept(row["standard_concept"])
        if row["standard_concept"].strip() and not concept:
            raise Stage8Error(
                f"nonempty standard_concept normalizes to empty for {unit_id}"
            )
        if concept:
            by_concept[concept].append(unit_id)
        if "." in unit_id:
            by_parent[unit_id.split(".", 1)[0]].append(unit_id)
    concepts = {key: sorted(value) for key, value in by_concept.items() if len(value) > 1}
    siblings = {key: sorted(value) for key, value in by_parent.items() if len(value) > 1}
    concept_edges = set().union(*(_pairs(value) for value in concepts.values())) if concepts else set()
    sibling_edges = set().union(*(_pairs(value) for value in siblings.values())) if siblings else set()

    tokens = {unit_id: content_words(row["new_title"]) for unit_id, row in notes.items()}
    inverted: dict[str, list[str]] = collections.defaultdict(list)
    for unit_id, words in tokens.items():
        for word in words:
            inverted[word].append(unit_id)
    checked: set[tuple[str, str]] = set()
    lexical_scores: dict[tuple[str, str], tuple[int, int]] = {}
    for word in sorted(inverted):
        bucket = sorted(inverted[word])
        if len(bucket) < 2 or len(bucket) > 400:
            continue
        for index, left in enumerate(bucket):
            for right in bucket[index + 1:]:
                pair = (left, right)
                if pair in checked:
                    continue
                checked.add(pair)
                intersection = len(tokens[left] & tokens[right])
                union = len(tokens[left] | tokens[right])
                if union and intersection / union >= threshold:
                    lexical_scores[pair] = (intersection, union)
    lexical_edges = set(lexical_scores)
    prior_edges = concept_edges | sibling_edges
    lexical_only = lexical_edges - prior_edges
    return {
        "concepts": concepts,
        "siblings": siblings,
        "lexical_scores": lexical_scores,
        "lexical_only": lexical_only,
        "concept_edges": concept_edges,
        "sibling_edges": sibling_edges,
        "lexical_edges": lexical_edges,
        "union_edges": prior_edges | lexical_edges,
        "checked_lexical_pairs": len(checked),
    }


def _groups_sha256(groups: list[dict]) -> str:
    payload = json.dumps(groups, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_artifact(rows: dict[str, dict], fingerprint: dict, threshold: float) -> dict:
    notes = {unit_id: row for unit_id, row in rows.items() if row["verdict"] == "KEEP"}
    signals = derive_signals(notes, threshold)
    pending: list[dict] = []
    for concept, members in sorted(signals["concepts"].items()):
        raw_variants = collections.Counter(notes[unit_id]["standard_concept"] for unit_id in members)
        pending.append({
            "kind": "normalized-concept",
            "provenance": {
                "normalized_concept": concept,
                "raw_variants": [
                    {"value": value, "count": count}
                    for value, count in sorted(raw_variants.items())
                ],
            },
            "members": [member_snapshot(notes[unit_id]) for unit_id in members],
        })
    for parent, members in sorted(signals["siblings"].items()):
        pending.append({
            "kind": "sibling-parent",
            "provenance": {"parent_unit_id": parent},
            "members": [member_snapshot(notes[unit_id]) for unit_id in members],
        })
    for left, right in sorted(signals["lexical_only"]):
        intersection, union = signals["lexical_scores"][(left, right)]
        pending.append({
            "kind": "lexical-only-pair",
            "provenance": {
                "threshold": threshold,
                "intersection_words": sorted(content_words(notes[left]["new_title"]) & content_words(notes[right]["new_title"])),
                "intersection_count": intersection,
                "union_count": union,
                "jaccard": intersection / union,
            },
            "members": [member_snapshot(notes[left]), member_snapshot(notes[right])],
        })
    groups = [{"group_id": f"g{index:06d}", **group} for index, group in enumerate(pending)]

    represented = set()
    for group in groups:
        members = [member["unit_id"] for member in group["members"]]
        if len(members) < 2:
            raise Stage8Error(f"zero-edge group produced: {group['group_id']}")
        represented.update(_pairs(members))
    if represented != signals["union_edges"]:
        raise Stage8Error(
            "serialized groups do not exactly cover the signal union: "
            f"missing={len(signals['union_edges'] - represented):,} "
            f"extra={len(represented - signals['union_edges']):,}"
        )
    kind_counts = collections.Counter(group["kind"] for group in groups)
    kind_memberships = collections.Counter()
    for group in groups:
        kind_memberships[group["kind"]] += len(group["members"])
    counts = {
        "keep_notes": len(notes),
        "keep_notes_with_standard_concept": sum(bool(row["standard_concept"].strip()) for row in notes.values()),
        "groups": len(groups),
        "memberships": sum(len(group["members"]) for group in groups),
        "groups_by_kind": dict(sorted(kind_counts.items())),
        "memberships_by_kind": dict(sorted(kind_memberships.items())),
        "edges": {
            "sibling_parent": len(signals["sibling_edges"]),
            "normalized_concept": len(signals["concept_edges"]),
            "title_jaccard": len(signals["lexical_edges"]),
            "lexical_only": len(signals["lexical_only"]),
            "union": len(signals["union_edges"]),
        },
        "lexical_pairs_evaluated": signals["checked_lexical_pairs"],
    }
    return {
        "schema": SCHEMA_VERSION,
        "stage5_fingerprint": fingerprint,
        "parameters": {
            "title_jaccard_threshold": threshold,
            "lexical_block_max_document_frequency": 400,
            "content_word_min_length": 4,
        },
        "counts": counts,
        "integrity": {
            "groups_canonical_json_sha256": _groups_sha256(groups),
            "coverage": "every derived union edge is represented by at least one complete group",
        },
        "groups": groups,
    }


def validate_artifact(artifact: object, rows: dict[str, dict], fingerprint: dict) -> None:
    """Re-derive all signals and require exact artifact identity and coverage."""
    if not isinstance(artifact, dict) or artifact.get("schema") != SCHEMA_VERSION:
        raise Stage8Error("Stage 8 artifact has an unsupported schema")
    if artifact.get("stage5_fingerprint") != fingerprint:
        raise Stage8Error("Stage 8 artifact is not bound to the active Stage 5 tree")
    parameters = artifact.get("parameters")
    groups = artifact.get("groups")
    if not isinstance(parameters, dict) or not isinstance(groups, list):
        raise Stage8Error("Stage 8 artifact structure is malformed")
    threshold = parameters.get("title_jaccard_threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise Stage8Error("Stage 8 artifact has an invalid Jaccard threshold")
    expected = build_artifact(rows, fingerprint, float(threshold))
    if artifact != expected:
        raise Stage8Error("Stage 8 artifact fails deterministic integrity validation")


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as output:
            temporary = output.name
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        temporary = None
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def read_json(path: Path, label: str) -> object:
    if path.is_symlink() or not path.is_file():
        raise Stage8Error(f"{label} is missing or unsafe: {path}")
    try:
        return json.loads(
            path.read_bytes(),
            object_pairs_hook=_strict_object,
            parse_constant=_invalid_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Stage8Error(f"cannot read {label} {path}: {exc}") from exc


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migration", default=str(Path.home() / "engram-work" / ".migration"))
    parser.add_argument("--jaccard", type=float, default=DEFAULT_JACCARD)
    args = parser.parse_args()
    migration = Path(args.migration)
    destination = migration / "stage8_groups.json"
    started = time.monotonic()
    try:
        rows, fingerprint = load_stage5(migration / "stage5")
        artifact = build_artifact(rows, fingerprint, args.jaccard)
        validate_artifact(artifact, rows, fingerprint)
        atomic_write(destination, json_bytes(artifact))
        validate_artifact(read_json(destination, "written Stage 8 artifact"), rows, fingerprint)
    except Stage8Error as exc:
        print(f"[stage8] failed: {exc}", file=sys.stderr)
        return 1
    counts = artifact["counts"]
    print(f"[stage8] Stage 5 fingerprint: {fingerprint['sha256']}")
    print(
        f"[stage8] edges sibling={counts['edges']['sibling_parent']:,} "
        f"concept={counts['edges']['normalized_concept']:,} "
        f"lexical={counts['edges']['title_jaccard']:,} "
        f"lexical-only={counts['edges']['lexical_only']:,} "
        f"union={counts['edges']['union']:,}"
    )
    print(f"[stage8] groups={counts['groups']:,} memberships={counts['memberships']:,}")
    print(f"[stage8] wrote {destination} sha256={file_sha256(destination)} in {time.monotonic()-started:.3f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
