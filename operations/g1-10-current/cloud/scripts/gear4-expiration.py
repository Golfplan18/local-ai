#!/usr/bin/env python3
"""Register or execute one exact Gear-4 graveyard expiration deadline."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = (Path.home() / "gear4-stale-sessions").resolve()
RECEIPTS = Path.home() / ".local" / "state" / "ora" / "gear4-expiration.jsonl"


def exact_entry(raw: str) -> Path:
    path = Path(raw).expanduser().resolve()
    if path.parent != ROOT or path == ROOT:
        raise ValueError("expiration target must be one exact graveyard entry")
    return path


def receipt(kind: str, path: Path, **fields) -> None:
    RECEIPTS.parent.mkdir(parents=True, exist_ok=True)
    record = {"kind": kind, "path": str(path),
              "recorded_at": datetime.now(timezone.utc).isoformat(), **fields}
    with RECEIPTS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def entry_identity(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_dev}:{stat.st_ino}"


def register(path: Path) -> int:
    if not path.is_dir() or path.is_symlink():
        raise ValueError("graveyard entry must be an existing real directory")
    identity = entry_identity(path)
    unit = "ora-gear4-expire-" + hashlib.sha256(
        f"{path}\0{identity}".encode()).hexdigest()[:20]
    existing = subprocess.run(
        ["systemctl", "--user", "show", f"{unit}.timer",
         "--property=LoadState", "--value"],
        capture_output=True, text=True,
    )
    if existing.returncode == 0 and existing.stdout.strip() == "loaded":
        receipt("deadline_registration_replayed", path, unit=unit,
                entry_identity=identity)
        return 0
    argv = [
        "systemd-run", "--user", "--collect", f"--unit={unit}",
        "--on-active=14d", sys.executable, str(Path(__file__).resolve()),
        "delete", str(path), "--identity", identity,
    ]
    result = subprocess.run(argv, capture_output=True, text=True)
    receipt("deadline_registered", path, unit=unit, entry_identity=identity,
            exit_status=result.returncode)
    return result.returncode


def delete(path: Path, expected_identity: str) -> int:
    if not path.exists():
        receipt("deadline_idempotent_absence", path,
                entry_identity=expected_identity)
        return 0
    if not path.is_dir() or path.is_symlink():
        raise ValueError("refusing non-directory or symlink expiration target")
    current_identity = entry_identity(path)
    if current_identity != expected_identity:
        raise ValueError(
            "refusing to delete a replacement at the expired locator: "
            f"{current_identity} != {expected_identity}"
        )
    shutil.rmtree(path)
    receipt("deadline_completed", path, entry_identity=expected_identity)
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("register", "delete"))
    parser.add_argument("path")
    parser.add_argument("--identity")
    args = parser.parse_args(argv)
    target = exact_entry(args.path)
    if args.action == "register":
        if args.identity is not None:
            parser.error("--identity is runtime-issued by registration")
        return register(target)
    if not args.identity or not all(
            part.isdigit() for part in args.identity.split(":", 1)):
        parser.error("delete requires the runtime-issued device:inode identity")
    return delete(target, args.identity)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
