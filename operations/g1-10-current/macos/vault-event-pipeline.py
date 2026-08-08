#!/opt/homebrew/bin/python3
"""Exactly-once Mac operational hooks for one coalesced vault write event."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
VAULT = Path(os.environ.get("ORA_VAULT") or Path.home() / "Documents" / "vault").resolve()
STATE_ROOT = Path(os.environ.get("ORA_HOME") or Path.home() / "ora") / "data" / "runtime-hygiene"
STATE_FILE = STATE_ROOT / "mac-vault-event-state.json"
AUDIT_FILE = STATE_ROOT / "mac-vault-events.jsonl"
LOCK_FILE = STATE_ROOT / ".mac-vault-events.lock"


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema_version": 1, "events": {}}


def _append(value: dict) -> None:
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _run(name: str, argv: list[str]) -> dict:
    result = subprocess.run(argv, capture_output=True, text=True)
    return {
        "name": name, "argv": argv, "exit_status": result.returncode,
        "stdout_tail": result.stdout[-4000:], "stderr_tail": result.stderr[-4000:],
    }


def _event_contract(paths: list[str]) -> list[dict]:
    identities = []
    for raw in sorted(set(paths)):
        path = Path(raw).expanduser().resolve()
        try:
            path.relative_to(VAULT)
        except ValueError as exc:
            raise ValueError(f"path is outside the vault: {path}") from exc
        if path.is_file():
            identities.append({
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
        else:
            identities.append({"path": str(path), "sha256": "missing"})
    return identities


def _issue_event_id(identities: list[dict]) -> str:
    body = json.dumps(
        {"identities": identities, "nonce": secrets.token_hex(32)},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return "mac-vault-" + hashlib.sha256(body).hexdigest()


def _needs_derive(identities: list[dict]) -> bool:
    """Route-bearing canonicals may have any Markdown filename or depth."""
    for item in identities:
        relative = Path(item["path"]).relative_to(VAULT)
        if (relative.suffix.lower() == ".md" and len(relative.parts) >= 3
                and relative.parts[0] == "Projects"
                and relative.parts[1] in {"Ora", "MSI"}):
            return True
    return False


def _persist(state: dict, record: dict) -> None:
    state["events"][record["event_id"]] = record
    _atomic_json(STATE_FILE, state)
    _append(record)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id")
    parser.add_argument("--path", action="append", default=[])
    args = parser.parse_args(argv)
    if not args.path:
        parser.error("at least one exact --path is required")
    identities = _event_contract(args.path)
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state = _load()
        if args.event_id:
            if not (args.event_id.startswith("mac-vault-")
                    and len(args.event_id) == len("mac-vault-") + 64
                    and all(c in "0123456789abcdef" for c in args.event_id[10:])):
                raise ValueError("invalid event id")
            event_id = args.event_id
            record = state["events"].get(event_id)
            if record is None:
                raise ValueError("retry event id was not issued by this runtime")
        else:
            event_id = _issue_event_id(identities)
            record = None
        if record is None:
            record = {
                "event_id": event_id,
                "identities": identities,
                "paths": [item["path"] for item in identities],
                "status": "claimed",
                "steps": [],
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            _persist(state, record)
        elif record.get("identities") != identities:
            raise ValueError("event subject drifted after the persisted claim")
        elif record.get("status") == "completed":
            print(json.dumps(record, sort_keys=True))
            return 0

        required = [("vault_git_sync", [
            "/opt/homebrew/bin/python3", str(HERE / "vault-git-sync.py")])]
        if _needs_derive(identities):
            required.append(("derive_and_push", [
                str(HERE / "vault-derive-sync.sh"), "--push"]))
        required.append(("vault_cloud_sync", [
            "/opt/homebrew/bin/python3", str(HERE / "vault-cloud-sync.py")]))

        completed = {
            step.get("name"): step for step in record.get("steps", [])
            if step.get("exit_status") == 0
        }
        record["steps"] = [completed[name] for name, _argv in required
                           if name in completed]
        record["status"] = "running"
        record["resumed_at"] = datetime.now(timezone.utc).isoformat()
        _persist(state, record)
        for name, step_argv in required:
            if name in completed:
                continue
            step = _run(name, step_argv)
            record["steps"].append(step)
            if step["exit_status"] != 0:
                record["status"] = "failed"
                record["failed_step"] = name
                record["completed_at"] = datetime.now(timezone.utc).isoformat()
                _persist(state, record)
                print(json.dumps(record, sort_keys=True))
                return 1
            completed[name] = step
            _persist(state, record)

        record.pop("failed_step", None)
        record["status"] = "completed"
        record["completed_at"] = datetime.now(timezone.utc).isoformat()
        _persist(state, record)
        print(json.dumps(record, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
