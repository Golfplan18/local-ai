#!/usr/bin/env python3
"""Stage 7 — safely apply the permanent-note migration to its worktree.

ONE-TIME MIGRATION TOOL. Delete with the rest of scripts/engram-migration/.

Dry-run is the default.  A real apply is restricted to the dedicated
``~/engram-work`` worktree at its recorded branch and baseline commit.  The
entire operation is planned and validated before the first write.  KEEP output
is durably created before any member moves, and every move is resumable without
overwriting or deleting source material.

Existing relationships are deliberately omitted.  They are keyed by the old
claim titles and Stage 10 rebuilds them after this migration.
"""
from __future__ import annotations

import argparse
import collections
import ctypes
import errno
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


ARCHIVE_SUBDIR = "Engram Over-extraction 2026-08"
ABSORBED_SUBDIR = "Engram Absorbed Sources 2026-08"
MIGRATION_MARKER = "permanent-note-2026-08"
EXPECTED_WORKTREE = (Path.home() / "engram-work").resolve()
LIVE_VAULT = (Path.home() / "Documents" / "vault").resolve()
EXPECTED_BRANCH = "engram-permanent-notes"
EXPECTED_BASELINE = "c8e5c3782f12b9f063be4d103555ef2d922f8416"
EXPECTED_SHARDS = 487
EXPECTED_UNITS = 72_737
EXPECTED_MEMBERS = 122_118

STAGE2_KEYS = {"unit_id", "parent_id", "size", "members"}
MEMBER_KEYS = {"file", "title", "body", "type", "side"}
STAGE3_KEYS = {"unit_id", "verdict", "member_files", "specifics", "note"}
STAGE3_VERDICTS = {"KEEP", "RESOURCES", "ARCHIVE"}
STAGE5_REQUIRED = {
    "unit_id", "verdict", "standard_concept", "new_title", "new_body",
    "facets_absorbed", "note",
}
STAGE5_OPTIONAL = {"member_files", "written_by"}
STAGE9_SCHEMA = "ora-stage9-merges-v1"

_SLUG_STRIP = re.compile(r"[^a-z0-9\s\-]+")
_SLUG_WS = re.compile(r"[\s\-]+")
_FRONT_CLOSE = re.compile(r"^---[ \t]*$", re.MULTILINE)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LIBC = ctypes.CDLL(None, use_errno=True)
_RENAMEX_NP = getattr(_LIBC, "renamex_np", None)
if _RENAMEX_NP is not None:
    _RENAMEX_NP.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
    _RENAMEX_NP.restype = ctypes.c_int
_RENAME_EXCL = 0x00000004


class MigrationError(RuntimeError):
    """A fail-closed precondition or data-integrity error."""


class _UniqueKeyLoader(getattr(yaml, "CSafeLoader", yaml.SafeLoader)):
    pass


def _construct_unique_mapping(loader: yaml.SafeLoader, node: yaml.Node,
                              deep: bool = False) -> dict:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark,
                "found an unhashable key", key_node.start_mark,
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark,
                f"found duplicate key {key!r}", key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True)
class MemberMove:
    member: dict
    action: str
    source: Path
    destination: Path
    state: str  # pending_move, pending_transform, or complete


@dataclass(frozen=True)
class UnitPlan:
    unit_id: str
    publication_action: str | None
    source_action: str
    output: Path | None
    output_content: str | None
    output_state: str | None
    moves: tuple[MemberMove, ...]
    suffixed_output: bool = False


@dataclass(frozen=True)
class ApplyPlan:
    temp: Path
    resources: Path
    archive: Path
    absorbed: Path
    units: tuple[UnitPlan, ...]
    current_engram_count: int


def slugify(text: str, max_words: int = 8) -> str:
    s = _SLUG_STRIP.sub(" ", (text or "").lower())
    parts = [p for p in _SLUG_WS.sub("-", s).strip("-").split("-") if p]
    return "-".join(parts[:max_words]) or "untitled"


def _require_plain_directory(path: Path, *, allow_missing: bool = False) -> None:
    if path.is_symlink():
        raise MigrationError(f"symlinked directory is unsafe: {path}")
    if not path.exists():
        if allow_missing:
            return
        raise MigrationError(f"missing directory: {path}")
    if not path.is_dir():
        raise MigrationError(f"not a directory: {path}")


def _require_regular(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise MigrationError(f"expected a regular, non-symlink file: {path}")


def _safe_leaf(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or value in {".", ".."}:
        raise MigrationError(f"unsafe {label}: {value!r}")
    if (Path(value).name != value or "/" in value or "\\" in value
            or "\x00" in value or not value.endswith(".md")):
        raise MigrationError(f"unsafe {label}: {value!r}")
    return value


def parse_front(text: str, *, path: Path | None = None) -> tuple[dict, str]:
    """Parse strict YAML frontmatter with duplicate-key rejection."""
    label = str(path) if path else "note"
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        raise MigrationError(f"missing YAML frontmatter: {label}")
    close = _FRONT_CLOSE.search(normalized, 4)
    if close is None:
        raise MigrationError(f"unterminated YAML frontmatter: {label}")
    raw = normalized[4:close.start()]
    try:
        front = yaml.load(raw, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise MigrationError(f"malformed YAML frontmatter in {label}: {exc}") from exc
    if front is None:
        front = {}
    if not isinstance(front, dict):
        raise MigrationError(f"frontmatter is not a mapping: {label}")
    return front, normalized[close.end():].lstrip("\n")


def _yaml_text(value: object, *, field: str, path: Path) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return str(value)
    raise MigrationError(
        f"{field} must be a scalar or list of scalars in {path}; got {type(value).__name__}"
    )


def _metadata_values(front: dict, field: str, path: Path) -> list[str]:
    value = front.get(field)
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return [_yaml_text(item, field=field, path=path) for item in values]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(v for v in values if v and v not in {"null", "~"}))


def _source_date(front: dict, path: Path) -> str | None:
    value = front.get("date created")
    if value is None or value == "":
        return None
    result = _yaml_text(value, field="date created", path=path)
    if not _ISO_DATE.fullmatch(result):
        raise MigrationError(f"invalid date created {result!r} in {path}")
    try:
        date.fromisoformat(result)
    except ValueError as exc:
        raise MigrationError(f"invalid date created {result!r} in {path}") from exc
    return result


def _read_note(path: Path) -> tuple[str, dict, str]:
    _require_regular(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise MigrationError(f"cannot read {path}: {exc}") from exc
    front, body = parse_front(text, path=path)
    return text, front, body


def _verify_member_note(path: Path, member: dict) -> tuple[str, dict]:
    text, front, body = _read_note(path)
    title = member["title"]
    first = body.splitlines()[0] if body.splitlines() else ""
    if first != f"# {title}":
        raise MigrationError(f"member title no longer matches Stage 2 at {path}")
    expected_body = member.get("body") or ""
    if expected_body and expected_body not in body:
        raise MigrationError(f"member body no longer matches Stage 2 at {path}")
    return text, front


def _load_json_array(path: Path, label: str) -> list:
    _require_regular(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MigrationError(f"malformed {label} file {path}: {exc}") from exc
    if not isinstance(payload, list):
        raise MigrationError(f"{label} file is not a JSON array: {path}")
    return payload


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise MigrationError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _invalid_json_constant(value: str) -> None:
    raise MigrationError(f"invalid JSON constant: {value}")


def _load_json_object(path: Path, label: str) -> dict:
    _require_regular(path)
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_json_object,
            parse_constant=_invalid_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MigrationError(f"malformed {label} file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise MigrationError(f"{label} file is not a JSON object: {path}")
    return payload


def _flat_tree_fingerprint(path: Path, label: str) -> dict:
    """Match stage5_run._flat_tree_fingerprint over exact names and bytes."""
    _require_plain_directory(path)
    digest = hashlib.sha256()
    files = sorted(path.iterdir(), key=lambda item: item.name)
    for item in files:
        if item.is_symlink() or not item.is_file():
            raise MigrationError(f"unexpected entry in {label} directory: {item}")
        name = item.name.encode("utf-8")
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        with item.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    return {"files": len(files), "sha256": digest.hexdigest()}


def _load_stage9_merges(
    migration: Path, stage5: dict[str, dict], stage5_fingerprint: dict,
) -> tuple[dict[str, tuple[str, ...]], dict[str, str]]:
    """Validate the exact Stage 9 manifest and return keeper/loser mappings."""
    path = migration / "stage9_merges.json"
    manifest = _load_json_object(path, "Stage 9 merge manifest")
    if set(manifest) != {"schema", "stage5_fingerprint", "merge_sets"}:
        raise MigrationError("Stage 9 merge manifest has unexpected or missing keys")
    if manifest["schema"] != STAGE9_SCHEMA:
        raise MigrationError(f"unexpected Stage 9 merge schema: {manifest['schema']!r}")
    fingerprint = manifest["stage5_fingerprint"]
    if (
        not isinstance(fingerprint, dict)
        or set(fingerprint) != {"files", "sha256"}
        or not isinstance(fingerprint.get("files"), int)
        or isinstance(fingerprint.get("files"), bool)
        or fingerprint["files"] < 1
        or not isinstance(fingerprint.get("sha256"), str)
        or not _SHA256.fullmatch(fingerprint["sha256"])
    ):
        raise MigrationError("Stage 9 merge manifest has an invalid Stage 5 fingerprint")
    if fingerprint != stage5_fingerprint:
        raise MigrationError("Stage 9 merge manifest does not match active Stage 5 bytes")

    merge_sets = manifest["merge_sets"]
    if not isinstance(merge_sets, list):
        raise MigrationError("Stage 9 merge_sets must be a JSON array")
    keepers: dict[str, tuple[str, ...]] = {}
    losers: dict[str, str] = {}
    assigned: set[str] = set()
    prior_keeper: str | None = None
    for index, merge_set in enumerate(merge_sets):
        if (
            not isinstance(merge_set, dict)
            or set(merge_set) != {"keeper_unit_id", "member_unit_ids"}
        ):
            raise MigrationError(f"malformed Stage 9 merge set {index}")
        keeper = merge_set["keeper_unit_id"]
        members = merge_set["member_unit_ids"]
        if (
            not isinstance(keeper, str)
            or not keeper
            or not isinstance(members, list)
            or len(members) < 2
            or any(not isinstance(unit_id, str) or not unit_id for unit_id in members)
            or members != sorted(members)
            or len(set(members)) != len(members)
            or members[0] != keeper
        ):
            raise MigrationError(f"malformed or unsorted Stage 9 merge set {index}")
        if prior_keeper is not None and keeper <= prior_keeper:
            raise MigrationError("Stage 9 merge sets are not sorted by keeper_unit_id")
        prior_keeper = keeper
        overlap = assigned.intersection(members)
        if overlap:
            raise MigrationError(
                f"Stage 9 merge sets overlap at {sorted(overlap)[0]}"
            )
        missing = [unit_id for unit_id in members if unit_id not in stage5]
        if missing:
            raise MigrationError(f"Stage 9 merge member is absent from Stage 5: {missing[0]}")
        if stage5[keeper].get("verdict") != "KEEP":
            raise MigrationError(f"Stage 9 keeper is not final KEEP: {keeper}")
        for loser in members[1:]:
            if stage5[loser].get("verdict") != "ARCHIVE":
                raise MigrationError(f"Stage 9 loser is not final ARCHIVE: {loser}")
            losers[loser] = keeper
        assigned.update(members)
        keepers[keeper] = tuple(members)
    return keepers, losers


def _read_result_directory(directory: Path, pattern: re.Pattern[str],
                           label: str) -> tuple[list[Path], list[dict]]:
    _require_plain_directory(directory)
    paths: list[Path] = []
    for path in sorted(directory.iterdir(), key=lambda p: p.name):
        if path.is_symlink() or not path.is_file() or not pattern.fullmatch(path.name):
            raise MigrationError(f"unexpected {label} directory entry: {path}")
        paths.append(path)
    if not paths:
        raise MigrationError(f"no {label} files in {directory}")
    rows: list[dict] = []
    for path in paths:
        for index, row in enumerate(_load_json_array(path, label)):
            if not isinstance(row, dict):
                raise MigrationError(f"non-object {label} row: {path}[{index}]")
            rows.append(row)
    return paths, rows


def validate_repair_gate(migration: Path) -> None:
    """Require a complete, strictly shaped Stage 6 result with zero HARD rows."""
    repair_path = migration / "repair.json"
    rows = _load_json_array(repair_path, "Stage 6 repair")
    allowed = {"unit_id", "violations", "new_title", "shard", "detail"}
    required = {"unit_id", "violations", "new_title", "shard"}
    hard = 0
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not required.issubset(row) or set(row) - allowed:
            raise MigrationError(f"malformed Stage 6 repair row {index}")
        if (not isinstance(row["unit_id"], str) or not row["unit_id"]
                or not isinstance(row["new_title"], str)
                or not isinstance(row["shard"], str)
                or ("detail" in row and not isinstance(row["detail"], str))
                or not isinstance(row["violations"], list)
                or not row["violations"]
                or any(not isinstance(v, str) or not v for v in row["violations"])):
            raise MigrationError(f"malformed Stage 6 repair row {index}")
        hard += any(v.startswith("HARD") for v in row["violations"])
    if hard:
        raise MigrationError(
            f"{hard:,} Stage 6 repair records carry a HARD violation; repair and rerun Stage 6"
        )


def _validate_stage2(row: dict, *, where: str) -> None:
    if (set(row) != STAGE2_KEYS or not isinstance(row.get("unit_id"), str)
            or not row["unit_id"] or not isinstance(row.get("parent_id"), str)
            or not row["parent_id"] or not isinstance(row.get("size"), int)
            or isinstance(row.get("size"), bool) or row["size"] < 1
            or not isinstance(row.get("members"), list)
            or len(row["members"]) != row["size"]):
        raise MigrationError(f"malformed Stage 2 unit at {where}")
    for member in row["members"]:
        if (not isinstance(member, dict) or set(member) != MEMBER_KEYS
                or any(not isinstance(member.get(k), str) for k in MEMBER_KEYS)):
            raise MigrationError(f"malformed Stage 2 member in {row['unit_id']}")
        _safe_leaf(member["file"], label="member filename")


def _validate_stage3_shape(row: dict) -> None:
    if (set(row) != STAGE3_KEYS or not isinstance(row.get("unit_id"), str)
            or not row["unit_id"] or row.get("verdict") not in STAGE3_VERDICTS
            or not isinstance(row.get("member_files"), list)
            or any(not isinstance(v, str) or not v for v in row["member_files"])
            or not isinstance(row.get("specifics"), list)
            or any(not isinstance(v, str) or not v for v in row["specifics"])
            or not isinstance(row.get("note"), str)):
        raise MigrationError(f"malformed Stage 3 record for {row.get('unit_id')!r}")


def _validate_stage3(row: dict, source: dict | None) -> None:
    _validate_stage3_shape(row)
    if source is None:
        raise MigrationError(f"malformed Stage 3 record for {row.get('unit_id')!r}")
    expected = collections.Counter(m["file"] for m in source["members"])
    if collections.Counter(row["member_files"]) != expected:
        raise MigrationError(f"Stage 3 member coverage mismatch for {row['unit_id']}")


def _validate_stage5(row: dict, source: dict | None) -> None:
    if (not STAGE5_REQUIRED.issubset(row)
            or set(row) - (STAGE5_REQUIRED | STAGE5_OPTIONAL)
            or not isinstance(row.get("unit_id"), str) or not row["unit_id"]
            or row.get("verdict") not in {"KEEP", "ARCHIVE"}
            or not isinstance(row.get("standard_concept"), str)
            or not isinstance(row.get("new_title"), str)
            or not isinstance(row.get("new_body"), str)
            or not isinstance(row.get("facets_absorbed"), int)
            or isinstance(row.get("facets_absorbed"), bool)
            or row["facets_absorbed"] < 0
            or not isinstance(row.get("note"), str) or source is None
            or ("written_by" in row and not isinstance(row["written_by"], str))):
        raise MigrationError(f"malformed Stage 5 record for {row.get('unit_id')!r}")
    if "member_files" in row:
        files = row["member_files"]
        if (not isinstance(files, list)
                or collections.Counter(files) != collections.Counter(
                    m["file"] for m in source["members"]
                )):
            raise MigrationError(f"Stage 5 member coverage mismatch for {row['unit_id']}")
    if row["verdict"] == "KEEP":
        if (not row["new_title"].strip() or "\n" in row["new_title"]
                or not row["new_body"].strip()):
            raise MigrationError(f"empty or multiline Stage 5 KEEP output for {row['unit_id']}")


def _unique_by_id(rows: list[dict], label: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in rows:
        unit_id = row.get("unit_id")
        if not isinstance(unit_id, str) or not unit_id:
            raise MigrationError(f"{label} row lacks a unit_id")
        if unit_id in result:
            raise MigrationError(f"duplicate {label} unit_id: {unit_id}")
        result[unit_id] = row
    return result


def preflight_stage9(migration: Path) -> None:
    """Validate Stage 9 against active Stage 3/5 before Stage 6 writes."""
    stage5_dir = migration / "stage5"
    fingerprint = _flat_tree_fingerprint(stage5_dir, "active Stage 5")
    _, rows = _read_result_directory(
        stage5_dir, re.compile(r"result_.*\.json"), "Stage 5 result",
    )
    if _flat_tree_fingerprint(stage5_dir, "active Stage 5") != fingerprint:
        raise MigrationError("active Stage 5 changed during Stage 9 preflight")
    stage5 = _unique_by_id(rows, "Stage 5")
    merges = _load_stage9_merges(migration, stage5, fingerprint)

    stage3_dir = migration / "stage3"
    stage3_fingerprint = _flat_tree_fingerprint(stage3_dir, "active Stage 3")
    _, stage3_rows = _read_result_directory(
        stage3_dir, re.compile(r"result_.*\.json"), "Stage 3 result",
    )
    if _flat_tree_fingerprint(stage3_dir, "active Stage 3") != stage3_fingerprint:
        raise MigrationError("active Stage 3 changed during Stage 9 preflight")
    stage3 = _unique_by_id(stage3_rows, "Stage 3")
    for row in stage3_rows:
        _validate_stage3_shape(row)
    manifest_members = {
        unit_id for member_ids in merges[0].values() for unit_id in member_ids
    }
    non_keep = sorted(
        unit_id for unit_id in manifest_members
        if unit_id not in stage3 or stage3[unit_id]["verdict"] != "KEEP"
    )
    if non_keep:
        raise MigrationError(
            f"Stage 9 member is not a current Stage 3 KEEP: {non_keep[0]}"
        )

    if _flat_tree_fingerprint(stage5_dir, "active Stage 5") != fingerprint:
        raise MigrationError("active Stage 5 changed during Stage 9 preflight")
    if _flat_tree_fingerprint(stage3_dir, "active Stage 3") != stage3_fingerprint:
        raise MigrationError("active Stage 3 changed during Stage 9 preflight")
    if _load_stage9_merges(migration, stage5, fingerprint) != merges:
        raise MigrationError("Stage 9 merge manifest changed during preflight")


def _is_under(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def validate_apply_target(vault: Path, migration: Path) -> None:
    """Restrict destructive CLI execution to the recorded worktree state."""
    vault_real = vault.resolve(strict=True)
    migration_real = migration.resolve(strict=True)
    if _is_under(vault_real, LIVE_VAULT) or _is_under(migration_real, LIVE_VAULT):
        raise MigrationError("the live vault is never an apply target")
    if vault_real != EXPECTED_WORKTREE:
        raise MigrationError(f"apply target must be {EXPECTED_WORKTREE}, got {vault_real}")
    if migration_real != EXPECTED_WORKTREE / ".migration":
        raise MigrationError("apply migration directory must be ~/engram-work/.migration")
    if _RENAMEX_NP is None:
        raise MigrationError("this apply requires macOS renamex_np for no-clobber moves")

    def git(*arguments: str) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(vault_real), *arguments], check=True,
                capture_output=True, text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise MigrationError(f"cannot verify migration worktree: {exc}") from exc
        return result.stdout.strip()

    if git("branch", "--show-current") != EXPECTED_BRANCH:
        raise MigrationError(f"apply requires branch {EXPECTED_BRANCH}")
    if git("rev-parse", "HEAD") != EXPECTED_BASELINE:
        raise MigrationError(f"apply requires baseline HEAD {EXPECTED_BASELINE}")


def run_stage6_gate(migration: Path) -> None:
    """Recompute Stage 6 immediately before a real apply; stale gates are unsafe."""
    checker = Path(__file__).with_name("stage6_check.py")
    _require_regular(checker)
    try:
        result = subprocess.run(
            [sys.executable, str(checker), "--migration", str(migration)],
            capture_output=True, text=True,
        )
    except OSError as exc:
        raise MigrationError(f"cannot rerun Stage 6: {exc}") from exc
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n",
              file=sys.stderr)
    if result.returncode:
        raise MigrationError(f"Stage 6 gate failed with exit code {result.returncode}")


def _discover_existing_outputs(engrams: Path, original_names: set[str],
                               expected_keep: set[str]) -> tuple[dict[str, Path], set[str], int]:
    outputs: dict[str, Path] = {}
    occupied: set[str] = set()
    count = 0
    for path in sorted(engrams.glob("*.md"), key=lambda p: p.name):
        _require_regular(path)
        count += 1
        if path.name in original_names:
            occupied.add(path.name)
            continue
        _, front, _ = _read_note(path)
        if front.get("migration") != MIGRATION_MARKER:
            occupied.add(path.name)
            continue
        unit_id = front.get("migration_unit")
        if not isinstance(unit_id, str) or unit_id not in expected_keep:
            raise MigrationError(f"unexpected migration output: {path}")
        if unit_id in outputs:
            raise MigrationError(f"duplicate migration output for {unit_id}")
        outputs[unit_id] = path
    return outputs, occupied, count


def _locate_member(member: dict, action: str, engrams: Path, destination_dir: Path,
                   unit_id: str) -> tuple[MemberMove, dict]:
    name = member["file"]
    source = engrams / name
    destination = destination_dir / name
    source_exists = source.exists() or source.is_symlink()
    destination_exists = destination.exists() or destination.is_symlink()
    if source_exists and destination_exists:
        raise MigrationError(f"source and destination both exist for {unit_id}: {name}")
    if not source_exists and not destination_exists:
        raise MigrationError(f"missing source and completed move for {unit_id}: {name}")
    current = source if source_exists else destination
    text, front = _verify_member_note(current, member)
    if action == "RESOURCES":
        # Prove conversion is possible during planning, before any unit writes.
        _resource_content(text, current)
    if source_exists:
        state = "pending_move"
    elif action == "RESOURCES":
        _, front, _ = _read_note(destination)
        if front.get("type") == "resource":
            state = "complete"
        elif front.get("type") == "engram":
            state = "pending_transform"
        else:
            raise MigrationError(f"unexpected resource type at {destination}")
    else:
        state = "complete"
    return MemberMove(member, action, source, destination, state), front


def _build_note(rec: dict, members: list[dict], member_fronts: dict[str, tuple[dict, Path]],
                unit_id: str, run_date: str,
                existing_dates: tuple[str, str] | None = None) -> tuple[str, str]:
    dates: list[str] = []
    nexus: list[str] = []
    sources: list[str] = []
    dossiers: list[str] = []
    dossier_sections: list[str] = []
    voices: list[str] = []
    platforms: list[str] = []
    for member in members:
        front, path = member_fronts[member["file"]]
        source_date = _source_date(front, path)
        if source_date:
            dates.append(source_date)
        nexus.extend(_metadata_values(front, "nexus", path))
        sources.extend(_metadata_values(front, "source_chat", path))
        sources.extend(_metadata_values(front, "source_path", path))
        dossiers.extend(_metadata_values(front, "source_dossier", path))
        dossier_sections.extend(_metadata_values(front, "source_dossier_section", path))
        voices.extend(_metadata_values(front, "source_voice", path))
        platforms.extend(_metadata_values(front, "source_platform", path))

    created = min(dates) if dates else run_date
    modified = run_date
    if existing_dates is not None:
        created, modified = existing_dates
    types = [m["type"] for m in members if m.get("type")]
    note_type = collections.Counter(types).most_common(1)[0][0] if types else "principle"
    front: dict[str, object] = {
        "nexus": _dedupe(nexus),
        "type": "engram",
        "tags": ["atomic", note_type],
        "date created": created,
        "date modified": modified,
    }
    if rec.get("standard_concept"):
        front["standard_concept"] = rec["standard_concept"]
    front["absorbed_count"] = len(members)
    front["absorbed_from"] = [m["file"] for m in members]
    if sources:
        front["sources"] = _dedupe(sources)
    if dossiers:
        front["source_dossiers"] = _dedupe(dossiers)
    if dossier_sections:
        front["source_dossier_sections"] = _dedupe(dossier_sections)
    if voices:
        front["source_voices"] = _dedupe(voices)
    if platforms:
        front["source_platforms"] = _dedupe(platforms)
    front["migration"] = MIGRATION_MARKER
    front["migration_unit"] = unit_id
    if rec.get("written_by"):
        front["written_by"] = rec["written_by"]

    yaml_text = yaml.safe_dump(
        front, allow_unicode=True, sort_keys=False, default_flow_style=False,
        width=1000,
    )
    content = (
        f"---\n{yaml_text}---\n\n# {rec['new_title'].strip()}\n\n"
        f"{rec['new_body'].strip()}\n"
    )
    filename = f"{created}_{slugify(rec['new_title'])}.md"
    return filename, content


def _existing_output_dates(path: Path, unit_id: str) -> tuple[str, str]:
    _, front, _ = _read_note(path)
    if front.get("migration") != MIGRATION_MARKER or front.get("migration_unit") != unit_id:
        raise MigrationError(f"output does not identify migration unit {unit_id}: {path}")
    values: list[str] = []
    for field in ("date created", "date modified"):
        value = _yaml_text(front.get(field), field=field, path=path)
        if not _ISO_DATE.fullmatch(value):
            raise MigrationError(f"invalid {field} in existing output {path}")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise MigrationError(f"invalid {field} in existing output {path}") from exc
        values.append(value)
    return values[0], values[1]


def build_plan(vault: Path, migration: Path, *, run_date: str,
               require_full_corpus: bool) -> ApplyPlan:
    _require_plain_directory(vault)
    _require_plain_directory(migration)
    _require_regular(migration / "stage9_merges.json")
    engrams = vault / "Engrams"
    resources = vault / "Resources"
    archive = vault / "Archive" / ARCHIVE_SUBDIR
    absorbed = vault / "Archive" / ABSORBED_SUBDIR
    temp = migration / "stage7_tmp"
    _require_plain_directory(engrams)
    _require_plain_directory(resources, allow_missing=True)
    _require_plain_directory(vault / "Archive", allow_missing=True)
    _require_plain_directory(archive, allow_missing=True)
    _require_plain_directory(absorbed, allow_missing=True)
    _require_plain_directory(temp, allow_missing=True)

    shard_paths, shard_rows = _read_result_directory(
        migration / "shards", re.compile(r"shard_\d+\.json"), "Stage 2 shard",
    )
    for index, row in enumerate(shard_rows):
        _validate_stage2(row, where=f"row {index}")
    units = _unique_by_id(shard_rows, "Stage 2")
    all_members = [member for row in shard_rows for member in row["members"]]
    member_names = [member["file"] for member in all_members]
    duplicates = [name for name, count in collections.Counter(member_names).items() if count != 1]
    if duplicates:
        raise MigrationError(f"member filename belongs to multiple units: {duplicates[0]}")
    if require_full_corpus and (
        len(shard_paths) != EXPECTED_SHARDS or len(units) != EXPECTED_UNITS
        or len(all_members) != EXPECTED_MEMBERS
    ):
        raise MigrationError(
            "Stage 2 corpus count mismatch: "
            f"shards={len(shard_paths)}, units={len(units)}, members={len(all_members)}"
        )

    _, stage3_rows = _read_result_directory(
        migration / "stage3", re.compile(r"result_.*\.json"), "Stage 3 result",
    )
    stage3 = _unique_by_id(stage3_rows, "Stage 3")
    if set(stage3) != set(units):
        missing = sorted(set(units) - set(stage3))
        extra = sorted(set(stage3) - set(units))
        raise MigrationError(f"Stage 3 coverage mismatch: missing={missing[:3]}, extra={extra[:3]}")
    for row in stage3_rows:
        _validate_stage3(row, units.get(row["unit_id"]))

    stage5_dir = migration / "stage5"
    stage5_fingerprint = _flat_tree_fingerprint(stage5_dir, "active Stage 5")
    _, stage5_rows = _read_result_directory(
        stage5_dir, re.compile(r"result_.*\.json"), "Stage 5 result",
    )
    if _flat_tree_fingerprint(stage5_dir, "active Stage 5") != stage5_fingerprint:
        raise MigrationError("active Stage 5 changed while it was being read")
    stage5 = _unique_by_id(stage5_rows, "Stage 5")
    expected_stage5 = {uid for uid, row in stage3.items() if row["verdict"] == "KEEP"}
    if set(stage5) != expected_stage5:
        missing = sorted(expected_stage5 - set(stage5))
        extra = sorted(set(stage5) - expected_stage5)
        raise MigrationError(f"Stage 5 coverage mismatch: missing={missing[:3]}, extra={extra[:3]}")
    for row in stage5_rows:
        _validate_stage5(row, units.get(row["unit_id"]))

    merge_keepers, merge_losers = _load_stage9_merges(
        migration, stage5, stage5_fingerprint,
    )

    original_names = set(member_names)
    publication_ids = {
        uid for uid, rec in stage5.items() if rec["verdict"] == "KEEP"
    }
    existing_outputs, occupied, current_count = _discover_existing_outputs(
        engrams, original_names, publication_ids,
    )
    # Locate every source before assigning outputs.  This proves that the
    # entire plan is executable and supplies metadata from either the original
    # location or a recognized completed move.
    moves_by_unit: dict[str, tuple[MemberMove, ...]] = {}
    member_fronts: dict[str, tuple[dict, Path]] = {}
    publication_by_unit: dict[str, str | None] = {}
    source_action_by_unit: dict[str, str] = {}
    for unit_id in sorted(units):
        verdict3 = stage3[unit_id]["verdict"]
        if verdict3 == "KEEP":
            publication_action = (
                "KEEP" if stage5[unit_id]["verdict"] == "KEEP" else None
            )
            source_action = (
                "ABSORB"
                if publication_action == "KEEP" or unit_id in merge_losers
                else "ARCHIVE"
            )
        else:
            publication_action = None
            source_action = verdict3
        publication_by_unit[unit_id] = publication_action
        source_action_by_unit[unit_id] = source_action
        target_dir = (
            absorbed if source_action == "ABSORB" else
            resources if source_action == "RESOURCES" else archive
        )
        located = [
            _locate_member(member, source_action, engrams, target_dir, unit_id)
            for member in units[unit_id]["members"]
        ]
        unit_moves = tuple(move for move, _ in located)
        moves_by_unit[unit_id] = unit_moves
        for move, front in located:
            current_path = (
                move.source if move.state == "pending_move" else move.destination
            )
            member_fronts[move.member["file"]] = (front, current_path)

    reserved = set(original_names) | set(occupied)
    output_details: dict[str, tuple[Path, str, str, bool]] = {}
    for unit_id in sorted(publication_ids):
        existing = existing_outputs.get(unit_id)
        existing_dates = _existing_output_dates(existing, unit_id) if existing else None
        provenance_units = merge_keepers.get(unit_id, (unit_id,))
        provenance_members = [
            member
            for provenance_unit in provenance_units
            for member in units[provenance_unit]["members"]
        ]
        base_name, content = _build_note(
            stage5[unit_id], provenance_members, member_fronts,
            unit_id, run_date, existing_dates,
        )
        candidate = base_name
        suffix = 0
        while candidate in reserved:
            suffix += 1
            candidate = f"{base_name[:-3]}-{suffix}.md"
        reserved.add(candidate)
        output_path = engrams / candidate
        if existing is not None and existing != output_path:
            raise MigrationError(
                f"existing output path is not deterministic for {unit_id}: "
                f"{existing.name} != {candidate}"
            )
        if existing is not None:
            existing_text = existing.read_text(encoding="utf-8")
            if existing_text != content:
                raise MigrationError(f"existing output content mismatch for {unit_id}: {existing}")
            output_state = "complete"
        else:
            if output_path.exists() or output_path.is_symlink():
                raise MigrationError(f"output collision: {output_path}")
            output_state = "pending"
        output_details[unit_id] = (output_path, content, output_state, suffix > 0)

    planned_units: list[UnitPlan] = []
    for unit_id in sorted(units):
        publication_action = publication_by_unit[unit_id]
        source_action = source_action_by_unit[unit_id]
        if publication_action == "KEEP":
            output, content, state, suffixed = output_details[unit_id]
        else:
            output, content, state, suffixed = None, None, None, False
        planned_units.append(UnitPlan(
            unit_id=unit_id,
            publication_action=publication_action,
            source_action=source_action,
            output=output,
            output_content=content,
            output_state=state,
            moves=moves_by_unit[unit_id],
            suffixed_output=suffixed,
        ))
    planned_member_names = [
        move.member["file"] for unit in planned_units for move in unit.moves
    ]
    if collections.Counter(planned_member_names) != collections.Counter(member_names):
        raise MigrationError("Stage 7 does not assign every Stage 2 member exactly once")
    if _flat_tree_fingerprint(stage5_dir, "active Stage 5") != stage5_fingerprint:
        raise MigrationError("active Stage 5 changed during Stage 7 planning")
    if _load_stage9_merges(
        migration, stage5, stage5_fingerprint,
    ) != (merge_keepers, merge_losers):
        raise MigrationError("Stage 9 merge manifest changed during Stage 7 planning")
    return ApplyPlan(
        temp, resources, archive, absorbed,
        tuple(planned_units), current_count,
    )


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _rename_no_replace(source: Path, destination: Path) -> None:
    """Atomically move one file while refusing a destination that appears."""
    if _RENAMEX_NP is None:
        raise MigrationError("macOS renamex_np is unavailable")
    ctypes.set_errno(0)
    result = _RENAMEX_NP(
        os.fsencode(source), os.fsencode(destination), _RENAME_EXCL,
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise MigrationError(f"destination appeared during move: {destination}")
    raise OSError(error, os.strerror(error), str(source), str(destination))


def _write_temp(temp_dir: Path, content: str) -> Path:
    temp = temp_dir / f"stage7-{os.getpid()}-{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(temp, flags, 0o644)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return temp


def _atomic_create(path: Path, content: str, temp_dir: Path) -> None:
    if path.exists() or path.is_symlink():
        raise MigrationError(f"refusing to overwrite output: {path}")
    temp = _write_temp(temp_dir, content)
    try:
        os.link(temp, path)
        _fsync_directory(path.parent)
    except FileExistsError as exc:
        raise MigrationError(f"output appeared during apply: {path}") from exc
    finally:
        temp.unlink(missing_ok=True)


def _atomic_replace_owned(path: Path, content: str, temp_dir: Path) -> None:
    _require_regular(path)
    temp = _write_temp(temp_dir, content)
    try:
        os.replace(temp, path)
        _fsync_directory(path.parent)
    finally:
        temp.unlink(missing_ok=True)


def _resource_content(text: str, path: Path) -> str:
    front, _ = parse_front(text, path=path)
    if front.get("type") == "resource":
        return text
    if front.get("type") != "engram":
        raise MigrationError(f"cannot convert non-engram type at {path}")
    normalized = text.replace("\r\n", "\n")
    close = _FRONT_CLOSE.search(normalized, 4)
    assert close is not None
    head = normalized[:close.start()]
    head, count = re.subn(r"^type:[^\n]*$", "type: resource", head,
                          count=1, flags=re.MULTILINE)
    if count != 1:
        raise MigrationError(f"cannot locate scalar type field at {path}")
    return head + normalized[close.start():]


def ensure_output(unit: UnitPlan, temp_dir: Path) -> None:
    if (
        unit.publication_action != "KEEP"
        or unit.output is None
        or unit.output_content is None
    ):
        return
    if unit.output.exists() or unit.output.is_symlink():
        _require_regular(unit.output)
        if unit.output.read_text(encoding="utf-8") != unit.output_content:
            raise MigrationError(f"output changed during apply: {unit.output}")
        return
    _atomic_create(unit.output, unit.output_content, temp_dir)


def apply_move(move: MemberMove, temp_dir: Path) -> None:
    source_exists = move.source.exists() or move.source.is_symlink()
    destination_exists = move.destination.exists() or move.destination.is_symlink()
    if source_exists and destination_exists:
        raise MigrationError(f"refusing move collision: {move.destination}")
    if source_exists:
        _verify_member_note(move.source, move.member)
        if move.source.is_symlink():
            raise MigrationError(f"refusing symlink source: {move.source}")
        _rename_no_replace(move.source, move.destination)
        _fsync_directory(move.source.parent)
        _fsync_directory(move.destination.parent)
    elif not destination_exists:
        raise MigrationError(f"source disappeared during apply: {move.source}")

    _verify_member_note(move.destination, move.member)
    if move.action == "RESOURCES":
        current = move.destination.read_text(encoding="utf-8")
        transformed = _resource_content(current, move.destination)
        if transformed != current:
            _atomic_replace_owned(move.destination, transformed, temp_dir)


def execute_plan(plan: ApplyPlan) -> None:
    for directory in (
        plan.temp, plan.resources, plan.archive.parent, plan.archive, plan.absorbed,
    ):
        if directory.exists() or directory.is_symlink():
            _require_plain_directory(directory)
        else:
            directory.mkdir()
            _fsync_directory(directory.parent)
    for unit in plan.units:
        if unit.publication_action == "KEEP":
            ensure_output(unit, plan.temp)
        for move in unit.moves:
            apply_move(move, plan.temp)


def plan_stats(plan: ApplyPlan) -> collections.Counter:
    stats: collections.Counter = collections.Counter()
    for unit in plan.units:
        stats["units_planned"] += 1
        if unit.publication_action == "KEEP":
            stats["keep_units"] += 1
        source_label = {
            "ABSORB": "absorbed",
            "ARCHIVE": "archive",
            "RESOURCES": "resources",
        }[unit.source_action]
        stats[f"{source_label}_units"] += 1
        if unit.suffixed_output:
            stats["suffixed_output_names"] += 1
        if unit.output_state == "pending":
            stats["pending_note_writes"] += 1
        elif unit.output_state == "complete":
            stats["completed_note_writes"] += 1
        for move in unit.moves:
            move_label = {
                "ABSORB": "absorbed",
                "ARCHIVE": "archive",
                "RESOURCES": "resources",
            }[move.action]
            stats[f"{move_label}_members"] += 1
            stats[f"{move.state}_member_ops"] += 1
    pending_moves = stats["pending_move_member_ops"]
    stats["engrams_now"] = plan.current_engram_count
    stats["engrams_after_plan"] = (
        plan.current_engram_count + stats["pending_note_writes"] - pending_moves
    )
    return stats


def print_plan(plan: ApplyPlan, *, applied: bool) -> None:
    mode = "APPLIED" if applied else "DRY RUN (nothing changed)"
    print(f"[stage7] {mode}")
    stats = plan_stats(plan)
    order = (
        "units_planned", "keep_units", "absorbed_units", "archive_units",
        "resources_units",
        "pending_note_writes", "completed_note_writes", "suffixed_output_names",
        "absorbed_members", "archive_members", "resources_members",
        "pending_move_member_ops", "pending_transform_member_ops",
        "complete_member_ops", "engrams_now", "engrams_after_plan",
    )
    for key in order:
        print(f"   {key:32s} {stats[key]:8,}")


def require_zero_pending(plan: ApplyPlan) -> None:
    stats = plan_stats(plan)
    pending = (
        stats["pending_note_writes"]
        + stats["pending_move_member_ops"]
        + stats["pending_transform_member_ops"]
    )
    if pending:
        raise MigrationError(
            f"post-apply plan still contains {pending:,} pending operations"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--vault", default=str(Path.home() / "engram-work"))
    parser.add_argument(
        "--migration", default=str(Path.home() / "engram-work" / ".migration"),
    )
    parser.add_argument("--apply", action="store_true",
                        help="apply the fully validated plan (default: dry run)")
    args = parser.parse_args()

    vault = Path(args.vault).absolute()
    migration = Path(args.migration).absolute()
    try:
        if _is_under(vault.resolve(), LIVE_VAULT) or _is_under(migration.resolve(), LIVE_VAULT):
            raise MigrationError("the live vault is never read or written by Stage 7")
        if args.apply:
            validate_apply_target(vault, migration)
            preflight_stage9(migration)
            run_stage6_gate(migration)
        validate_repair_gate(migration)
        full = vault.resolve() == EXPECTED_WORKTREE
        run_date = date.today().isoformat()
        plan = build_plan(
            vault, migration, run_date=run_date, require_full_corpus=full,
        )
        print_plan(plan, applied=False)
        if args.apply:
            # Planning can take tens of seconds over 122,118 source notes.  Do
            # not accept a branch or HEAD change during that read-only window.
            validate_apply_target(vault, migration)
            execute_plan(plan)
            final_plan = build_plan(
                vault, migration, run_date=run_date, require_full_corpus=full,
            )
            require_zero_pending(final_plan)
            print_plan(final_plan, applied=True)
        return 0
    except (MigrationError, OSError, UnicodeError) as exc:
        print(f"[stage7] REFUSING: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
