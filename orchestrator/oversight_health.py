"""Oversight health check — detects unavailable runtime lanes.

Production oversight blocks on operating-system events and exact persisted
deadlines, so idleness is healthy and cannot be judged from a clock heartbeat.
The server checks the actual in-process threads. Legacy heartbeat reading is
retained for explicit compatibility operation and for the independent MLX
worker.

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

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator import runtime_paths as _rp


# Roots flow from runtime_paths (ORA_HOME-relocatable). The health reader
# must resolve the same heartbeat files the watcher writers produce —
# test_portability asserts the pairing module by module.
WORKSPACE = _rp.WORKSPACE


def _oversight_data_dir() -> str:
    # Resolved at CALL time (not baked at import) so the reader tracks the live
    # DATA_DIR / ORA_HOME regardless of import ordering. The watcher/heartbeat
    # writers now resolve the same way, so writer and reader can never split
    # because either was first imported under a relocated
    # runtime_paths.DATA_DIR_STR (the risk-gate-before-portability bug class).
    # An explicit monkeypatch of the module attribute still wins; __getattr__
    # surfaces the live value otherwise. Mirrors mlx_mutex (PR #240).
    override = globals().get("OVERSIGHT_DATA_DIR")
    if override is not None:
        return override
    return os.path.join(_rp.DATA_DIR_STR, "oversight")


def __getattr__(name: str) -> str:
    # PEP 562: keep OVERSIGHT_DATA_DIR readable as a module attribute
    # (test_portability's writer/reader agreement checks) while resolving it
    # live per access.
    if name == "OVERSIGHT_DATA_DIR":
        return _oversight_data_dir()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# Expected intervals — must match oversight_daemon defaults
HEARTBEAT_INTERVALS = {
    "ped_watcher": 60,
    "corpus_watcher": 60,
    "workflow_spec_sweeper": 300,
    "revisit_sweeper": 3600,
    "retention_sweeper": 21600,
    "maintenance_scheduler": 3600,
    "resources_watcher": 300,
    # Phase 2c: the local MLX worker heartbeat. "Alive" means Ora's
    # MLX-aware code path is responsive; staleness surfaces as a chat
    # warning the same way watcher staleness does. Emitted by
    # mlx_mutex.start_heartbeat at server startup.
    "mlx_worker": 30,
}

STALE_MULTIPLIER = 2  # heartbeat older than 2× interval is stale

# Watchdog restarts of one runtime lane before it is reported as flapping.
# Provisional — a genuinely healthy lane restarts zero times, so any non-zero
# count is a signal; 3 only suppresses one-off restarts around a code reload.
LANE_RESTART_WARN_COUNT = 3


def heartbeat_path(watcher_name: str) -> str:
    # The watcher modules write to files with dash-separated names
    # (e.g. "ped-watcher-heartbeat.json"), but the keys in
    # HEARTBEAT_INTERVALS are the Python module names with underscores
    # (e.g. "ped_watcher"). Convert underscore → dash for the on-disk
    # filename. This mismatch caused check_health() to read None for
    # every watcher and unconditionally report "daemon_down."
    on_disk_name = watcher_name.replace("_", "-")
    return os.path.join(_oversight_data_dir(), f"{on_disk_name}-heartbeat.json")


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
    now = time.time()
    any_recent_heartbeat = False

    # The production runtime is event/deadline driven. Thread liveness is the
    # authoritative signal while those blocking lanes are active; retired
    # watcher timestamps must not make an idle event listener look stale.
    runtime = None
    try:
        import oversight_daemon
        runtime = oversight_daemon.runtime_health()
    except Exception:
        runtime = None
    if runtime and runtime.get("running"):
        for lane in ("event_lane", "deadline_lane"):
            if not runtime.get(lane):
                warnings.append({
                    "watcher": lane,
                    "status": "runtime_lane_down",
                    "age_seconds": None,
                    "threshold_seconds": None,
                    "message": f"Oversight {lane.replace('_', ' ')} is not running.",
                })
        # A lane the watchdog keeps resurrecting passes every liveness check
        # while losing every event between the crash and the next 30s tick.
        restarts = runtime.get("lane_restarts") or {}
        restart_at = runtime.get("lane_restart_at") or {}
        for lane, count in sorted(restarts.items()):
            if count < LANE_RESTART_WARN_COUNT:
                continue
            last = restart_at.get(lane)
            recency = (
                f", most recently {_format_age(now - last)} ago"
                if isinstance(last, (int, float)) else ""
            )
            warnings.append({
                "watcher": lane,
                "status": "runtime_lane_flapping",
                "age_seconds": int(now - last) if isinstance(last, (int, float)) else None,
                "threshold_seconds": None,
                "message": (
                    f"Oversight {lane.replace('_', ' ')} has been restarted "
                    f"{count} times{recency}. It is running, but work arriving "
                    f"during each crash is dropped — check the server log."
                ),
            })
        # MLX has its own real clock heartbeat; preserve that independent
        # health check without consulting retired maintenance heartbeats.
        beat_at = read_heartbeat("mlx_worker")
        if beat_at is not None:
            age = now - beat_at
            threshold = HEARTBEAT_INTERVALS["mlx_worker"] * STALE_MULTIPLIER
            if age > threshold:
                warnings.append({
                    "watcher": "mlx_worker", "status": "stale",
                    "age_seconds": int(age),
                    "threshold_seconds": threshold,
                    "message": (
                        f"mlx_worker: last heartbeat {_format_age(age)} ago "
                        f"(expected within {HEARTBEAT_INTERVALS['mlx_worker']}s)"
                    ),
                })
        return warnings

    # Past this point the checks are about the oversight WATCHERS, which only
    # matter once a project is registered — the runtime-lane checks above are
    # unconditional because those lanes drive daily notes, trace expiry and
    # inbound conversion whether or not any project is under oversight. Before
    # 2026-08-16 this gate sat at the top of the function and suppressed the
    # lane checks too, which is why 2,257 event-lane crashes went unreported.
    if not _oversight_active():
        return warnings

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

    # Execution Review Phase 1 — telemetry-incomplete banner. If the
    # tool-event recorder has failed to write, the dispatch-signal
    # substrate is blind and downstream routing/packets are untrustworthy.
    # Surface it the same way as daemon_down/stale so the user sees it in
    # the active conversation. (Gated actions still fail closed regardless;
    # this is about observability, not enforcement.)
    try:
        try:
            import tool_events as _te_h
        except ImportError:
            from orchestrator import tool_events as _te_h
        _th = _te_h.get_telemetry_health()
        if _th.get("incomplete"):
            warnings.append({
                "watcher": "tool_events",
                "status": "telemetry_incomplete",
                "age_seconds": None,
                "threshold_seconds": None,
                "message": (
                    f"Tool-event recording has failed {_th['failures']} time(s) "
                    f"this run (last: {_th.get('last_error', '')[:160]}). "
                    "Execution-review telemetry is incomplete — reality-contact "
                    "observation for this session may be partial."
                ),
            })
    except Exception:
        pass

    return warnings


def format_warnings_as_chat_note(warnings: list[dict]) -> str:
    """Format warnings as a system note suitable for prepending to a chat
    response. Returns an empty string when there are no warnings.

    All warnings describe a degraded runtime observer or telemetry source.
    """
    if not warnings:
        return ""

    lines: list[str] = []
    lines.append("> ⚠️ **Meta-layer oversight: degraded**")
    for warning in warnings:
        lines.append(f"> - {warning['message']}")
    lines.append("> ")
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
    oversight_dir = _oversight_data_dir()
    if not os.path.isdir(oversight_dir):
        return False
    for entry in os.listdir(oversight_dir):
        full = os.path.join(oversight_dir, entry)
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
