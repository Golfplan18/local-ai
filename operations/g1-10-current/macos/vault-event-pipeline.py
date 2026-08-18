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
# Finished events retained in the live state map. Provisional — large enough
# that a redelivered notification is still recognised as a duplicate, small
# enough that the file stays cheap to rewrite on every step. Terminal records
# stay in the append-only audit log permanently regardless.
TERMINAL_EVENT_RETENTION = int(
    os.environ.get("ORA_VAULT_EVENT_STATE_RETENTION") or 500
)


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


def _rotate_if_oversized() -> None:
    """Roll the audit sink aside once it passes the size threshold.

    This file reached 113 MB by 2026-08-16 with no upper bound. The append is
    the size-threshold event; there is no clock here. Failing to rotate must
    never cost the caller its write, so the whole body is guarded — including
    reading the threshold, where a malformed env var would otherwise raise.
    """
    try:
        try:
            limit_mb = float(os.environ.get("ORA_RUNTIME_AUDIT_ROTATE_MB") or 32)
        except (TypeError, ValueError):
            limit_mb = 32.0
        try:
            keep = int(os.environ.get("ORA_RUNTIME_AUDIT_ARCHIVE_KEEP") or 6)
        except (TypeError, ValueError):
            keep = 6
        limit = limit_mb * 1024 * 1024
        if limit <= 0 or not AUDIT_FILE.is_file():
            return
        if AUDIT_FILE.stat().st_size <= limit:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive = AUDIT_FILE.with_name(f"{AUDIT_FILE.name}.{stamp}")
        # rename replaces silently on POSIX; never overwrite an archive.
        suffix = 0
        while archive.exists():
            suffix += 1
            archive = AUDIT_FILE.with_name(f"{AUDIT_FILE.name}.{stamp}.{suffix}")
        AUDIT_FILE.rename(archive)
        if keep > 0:
            # By mtime, not name: pruning frees collision suffixes for
            # reuse, so a name sort can rank a just-written archive as the
            # oldest and delete it immediately.
            siblings = sorted(
                (p for p in AUDIT_FILE.parent.glob(f"{AUDIT_FILE.name}.*")
                 if p.is_file()),
                key=lambda p: (p.stat().st_mtime_ns, p.name),
            )
            for stale in siblings[:max(0, len(siblings) - keep)]:
                try:
                    stale.unlink()
                except OSError:
                    pass
    except Exception:
        return


def _append(value: dict) -> None:
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _rotate_if_oversized()
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


def _identities_digest(identities: list[dict]) -> str:
    """Deterministic digest of the exact event contract."""
    canonical = json.dumps(identities, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _record_digest(record: dict) -> str | None:
    """Contract digest of a persisted record, old shape or new.

    Records written before 2026-08-17 carry the identity list inline and no
    digest; their digest is derived from that list so a legacy claim can still
    be drift-checked and resumed.
    """
    digest = record.get("identities_digest")
    if digest:
        return str(digest)
    legacy = record.get("identities")
    return _identities_digest(legacy) if legacy is not None else None


def _compact(record: dict, digest: str) -> dict:
    """Reduce a record to the referenced-contract shape.

    The identity list is the event contract: immutable, and therefore worth
    persisting exactly once rather than on every state transition. A batch
    carries one entry per changed file, so re-emitting it at claim, resume,
    each step boundary and completion multiplied a single event's write cost
    by the number of transitions — and the state file, which is rewritten and
    fsync'd in full on each of those, carried it too. The 2026-08-17 MSI-mirror
    loop made the cost visible (17,731 paths per record, ~157 MB of fsync per
    notification), but the shape was wrong for every large batch, not just that
    one. After this, transitions carry the digest and the count; the list
    itself lives in the append-only audit log, written once at claim.
    """
    out = dict(record)
    if "path_count" not in out:
        legacy = out.get("identities") or out.get("paths") or []
        out["path_count"] = len(legacy)
    out.pop("identities", None)
    out.pop("paths", None)
    out["identities_digest"] = digest
    return out


def _persist(state: dict, record: dict, *, contract: list[dict] | None = None) -> None:
    state["events"][record["event_id"]] = record
    _prune_terminal_events(state)
    _atomic_json(STATE_FILE, state)
    # The contract is evidence and is written to the append-only log exactly
    # once, on the claim that binds it. Later lines reference it by digest.
    _append({**record, "identities": contract} if contract is not None else record)


def _prune_terminal_events(state: dict) -> int:
    """Keep a bounded window of finished events in the live state map.

    The map is rewritten in full and fsync'd on every step of every event, so
    its size is write amplification on each notification, not just disk. By
    2026-08-16 it held 4,452 finished events in 31 MB — roughly 157 MB of
    fsync per event, for entries nothing reads.

    Only terminal records are eligible: anything still in flight is retained
    regardless of age. The retained window is what duplicate suppression
    needs — a redelivery arrives within moments, not thousands of events
    later — and every record remains permanently in the append-only audit
    log either way, so this prunes the working set, not the evidence.
    """
    events = state.get("events") or {}
    terminal = [
        (record.get("completed_at") or record.get("started_at") or "", key)
        for key, record in events.items()
        if record.get("status") in ("completed", "failed")
    ]
    if len(terminal) <= TERMINAL_EVENT_RETENTION:
        return 0
    terminal.sort()
    for _stamp, key in terminal[:len(terminal) - TERMINAL_EVENT_RETENTION]:
        events.pop(key, None)
    return len(terminal) - TERMINAL_EVENT_RETENTION


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id")
    parser.add_argument("--path", action="append", default=[])
    # A large coalesced batch (an iCloud sync settling, a bulk commit) exceeds
    # the OS argument-length limit when every path is its own --path pair.
    # --paths-file carries the identical exact paths as a JSON array with no
    # size ceiling; the two forms compose and the contract is unchanged.
    parser.add_argument("--paths-file")
    args = parser.parse_args(argv)
    exact_paths = list(args.path)
    if args.paths_file:
        # JSON, not newline-delimited: a newline (or any of the separators
        # str.splitlines() honours) is legal in a macOS filename, and splitting
        # on one would silently manufacture two bogus paths and bind them into
        # the exactly-once event contract.
        listed = json.loads(Path(args.paths_file).read_text(encoding="utf-8"))
        if not isinstance(listed, list) or not all(isinstance(x, str) for x in listed):
            parser.error("--paths-file must contain a JSON array of exact paths")
        exact_paths.extend(x for x in listed if x.strip())
    if not exact_paths:
        parser.error("at least one exact --path or --paths-file entry is required")
    identities = _event_contract(exact_paths)
    digest = _identities_digest(identities)
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
                "identities_digest": digest,
                "path_count": len(identities),
                "status": "claimed",
                "steps": [],
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            _persist(state, record, contract=identities)
        elif _record_digest(record) != digest:
            # Digest comparison is exactly as strong as comparing the lists,
            # and does not require the list to be resident in the state file.
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
        record = _compact(record, digest)
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
