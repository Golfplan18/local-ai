"""Oversight health check — detects stale watchers and surfaces warnings.

Reads each watcher's heartbeat file at ``~/ora/data/oversight/<name>-heartbeat.json``
and computes how long since the last beat. A watcher is "stale" when its
heartbeat is older than 2× its expected interval — that means the watcher
has missed at least one full cycle, which is enough signal to surface to
the user.

Used by the chat handler to inject a system note into responses when the
oversight apparatus is degraded. Per Reference — Meta-Layer Architecture
§10 O1.

Author: meta-layer implementation per Reference — Meta-Layer Architecture §10 O1.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Optional


WORKSPACE = os.path.expanduser("~/ora/")
OVERSIGHT_DATA_DIR = os.path.join(WORKSPACE, "data/oversight/")

# Expected intervals — must match oversight_daemon defaults
HEARTBEAT_INTERVALS = {
    "ped_watcher": 60,
    "corpus_watcher": 60,
    "workflow_spec_sweeper": 300,
    "revisit_sweeper": 3600,
}

STALE_MULTIPLIER = 2  # heartbeat older than 2× interval is stale


def heartbeat_path(watcher_name: str) -> str:
    return os.path.join(OVERSIGHT_DATA_DIR, f"{watcher_name}-heartbeat.json")


def read_heartbeat(watcher_name: str) -> Optional[float]:
    """Return seconds-since-epoch of the watcher's last heartbeat, or None
    if the heartbeat file is missing or malformed.
    """
    path = heartbeat_path(watcher_name)
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    beat_at = data.get("beat_at")
    if not beat_at:
        return None
    try:
        # ISO format with timezone
        if beat_at.endswith("Z"):
            beat_at = beat_at[:-1] + "+00:00"
        return datetime.fromisoformat(beat_at).timestamp()
    except (ValueError, TypeError):
        return None


def check_health() -> list[dict]:
    """Run all health checks. Returns a list of warning dicts.

    Two categories of warning:
      - daemon_down: oversight is in use but no watcher has beaten recently
      - stale: a specific watcher's heartbeat is older than its threshold

    Missing heartbeat files (not yet written) don't trigger per-watcher
    warnings — only stale ones do — because a missing file is ambiguous
    (could be early-startup or never-ran). The daemon_down warning catches
    the "nothing is running" case.
    """
    warnings: list[dict] = []

    # If there are no projects under oversight at all, the daemon doesn't
    # need to be running and warnings would be noise.
    if not _oversight_active():
        return warnings

    now = time.time()
    any_recent_heartbeat = False

    per_watcher: list[dict] = []
    for watcher, interval in HEARTBEAT_INTERVALS.items():
        threshold = interval * STALE_MULTIPLIER
        beat_at = read_heartbeat(watcher)
        if beat_at is None:
            continue
        age = now - beat_at
        # "recent" for daemon-alive purposes = within 2× the longest watcher
        # interval (i.e. within 2 hours, since revisit_sweeper is hourly)
        if age < HEARTBEAT_INTERVALS["revisit_sweeper"] * 2:
            any_recent_heartbeat = True
        if age > threshold:
            per_watcher.append({
                "watcher": watcher,
                "status": "stale",
                "age_seconds": int(age),
                "threshold_seconds": threshold,
                "message": (
                    f"{watcher}: last heartbeat {_format_age(age)} ago "
                    f"(expected within {interval}s)"
                ),
            })

    # If oversight is active but nothing has beaten recently, the daemon is
    # likely not running. One overall warning, not per-watcher.
    if not any_recent_heartbeat:
        warnings.append({
            "watcher": "daemon",
            "status": "daemon_down",
            "age_seconds": None,
            "threshold_seconds": None,
            "message": (
                "Oversight daemon is not running. Restart the server with "
                "./start.sh or run python orchestrator/oversight_daemon.py "
                "for a one-shot sweep."
            ),
        })
        return warnings

    warnings.extend(per_watcher)
    return warnings


def format_warnings_as_chat_note(warnings: list[dict]) -> str:
    """Format warnings as a system note suitable for prepending to a chat
    response. Returns an empty string when there are no warnings.
    """
    if not warnings:
        return ""
    lines = [
        "> ⚠️ **Meta-layer oversight: degraded**",
    ]
    for w in warnings:
        lines.append(f"> - {w['message']}")
    lines.append(
        "> "
    )
    lines.append(
        "> The oversight daemon may not be running, or one or more watchers have stalled. "
        "If this persists, restart with `./start.sh` or check `~/ora/data/oversight/` for stale heartbeat files."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


# ---------- Helpers ----------

def _oversight_active() -> bool:
    """Return True if oversight is in use (any project registered)."""
    if not os.path.isdir(OVERSIGHT_DATA_DIR):
        return False
    for entry in os.listdir(OVERSIGHT_DATA_DIR):
        full = os.path.join(OVERSIGHT_DATA_DIR, entry)
        if os.path.isdir(full):
            if (os.path.isfile(os.path.join(full, "ped-path.json"))
                    or os.path.isfile(os.path.join(full, "workflow-pointer.json"))):
                return True
    return False


def _format_age(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds / 60)}m"
    return f"{int(seconds / 3600)}h"


# ---------- CLI smoke test ----------

if __name__ == "__main__":
    warnings = check_health()
    if not warnings:
        print("Oversight health: OK")
    else:
        print(format_warnings_as_chat_note(warnings))
