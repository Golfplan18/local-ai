"""Maintenance scheduler — vault-governed cadences for periodic maintenance.

`orchestrator/tools/periodic_maintenance.py` has four tasks (orphan
relationship cleanup, vault health audit, graph density metrics, archive
+ cleanup) but nothing ever scheduled them — the cron lines suggested in
scripts/run-maintenance.sh were never installed, so the only runs were
manual (last: April 2026). This module closes that gap from inside the
oversight daemon, with the user's vault as the control surface.

Control document
----------------

``<configured vault>/Projects/Ora/Reference — Ora Periodic Maintenance.md``. Its YAML
frontmatter carries the live config:

    maintenance:
      orphan_cleanup: weekly
      vault_health: monthly
      graph_density: monthly
      archive_cleanup: off
      daily_note: daily
      news_supersession: off
      engram_cleaning: off

This module is now an explicit compatibility/reporting surface; production
does not launch its clock loop. Cadence values remain parseable as migration
evidence and for an explicitly invoked one-shot diagnostic. News supersession
and Engram cleaning are event-only controls:
their clock form is permanently ``off`` and attempts to assign a cadence
fail closed. A missing document, missing block, or unparseable YAML falls
back to the defaults above — the doc can never brick maintenance.

Compatibility mechanics
-----------------------

An operator may call ``sweep()`` explicitly to inspect or execute a deliberately
enabled historical diagnostic. It re-reads the control document, compares the
last-run stamp, appends a result, and writes a compatibility heartbeat. The
production daemon never calls it, the generic scheduler cannot register it,
and no error arms a retry or other clock-driven fallback.

Standalone:

    python -m orchestrator.maintenance_scheduler [--dry-run]
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator import runtime_paths as _rp

ORA_DIR = _rp.WORKSPACE
DATA_DIR = _rp.DATA_DIR_STR
STATE_FILE = os.path.join(DATA_DIR, "maintenance-state.json")
RESULTS_FILE = os.path.join(DATA_DIR, "maintenance-results.jsonl")
_HEARTBEAT_BASENAME = "maintenance-scheduler-heartbeat.json"


def _oversight_data_dir() -> str:
    # Resolved at CALL time (not baked at import) so it tracks the live
    # DATA_DIR / ORA_HOME regardless of import ordering — baking it froze a
    # stale tempdir when this module was first imported under a test that had
    # relocated runtime_paths.DATA_DIR_STR, splitting the writer from
    # oversight_health's live reader in a full-group run. An explicit
    # monkeypatch of the module attribute still wins (oversight_sandbox /
    # suites set a real global via mock.patch.object); __getattr__ surfaces the
    # live value otherwise. Mirrors mlx_mutex._default_heartbeat_path (PR #240).
    # Reads _rp.DATA_DIR_STR (not the import-baked module-level DATA_DIR).
    override = globals().get("OVERSIGHT_DATA_DIR")
    if override is not None:
        return override
    return os.path.join(_rp.DATA_DIR_STR, "oversight")


def _heartbeat_file() -> str:
    override = globals().get("HEARTBEAT_FILE")
    if override is not None:
        return override
    return os.path.join(_oversight_data_dir(), _HEARTBEAT_BASENAME)


def __getattr__(name: str) -> str:
    # PEP 562: keep OVERSIGHT_DATA_DIR / HEARTBEAT_FILE readable as module
    # attributes (test_portability's heartbeat writer/reader agreement, the
    # sandbox's basename probe) while resolving them live per access.
    if name == "OVERSIGHT_DATA_DIR":
        return _oversight_data_dir()
    if name == "HEARTBEAT_FILE":
        return _heartbeat_file()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

CONTROL_DOC_NAME = "Reference — Ora Periodic Maintenance.md"
_CAMPAIGN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def control_doc_path() -> str:
    return str(_rp.vault_dir() / "Projects" / "Ora" / CONTROL_DOC_NAME)


DEFAULT_CONFIG = {
    # G1.10: these corpus-scale scans are explicit campaigns. Runtime writes
    # perform local validation/index propagation instead of waiting for them.
    "orphan_cleanup": "off",
    "vault_health": "off",
    "graph_density": "off",
    # Log/archive housekeeping is owned by retention_sweeper since
    # 2026-06-11; the periodic_maintenance variant stays available but
    # defaults off. The unique piece it still covers is review-queue
    # archival — flip to "monthly" in the control doc to re-enable.
    "archive_cleanup": "off",
    # Auto-generated vault daily note (temporal index) — generates
    # yesterday's note once the day is complete.
    "daily_note": "daily",
    # G1.10 (2026-07-21): corpus-wide clock sweeps are prohibited. Exact
    # Resource/Engram writes may invoke bounded event processing; historical
    # backlog work requires an explicitly identified campaign. Keep the keys
    # visible so the operational state is not hidden, but never schedule them.
    "news_supersession": "off",
    "engram_cleaning": "off",
}

EVENT_ONLY_TASKS = frozenset({"news_supersession", "engram_cleaning"})
DEADLINE_ONLY_TASKS = frozenset({"daily_note"})

# Task name → (module, callable). Each callable returns a TaskResult-shaped
# object (success / message / stats / alerts / duration_seconds).
TASK_FUNCTIONS = {
    "orphan_cleanup": ("orchestrator.tools.periodic_maintenance", "task_1_orphan_cleanup"),
    "vault_health": ("orchestrator.tools.periodic_maintenance", "task_2_vault_health"),
    "graph_density": ("orchestrator.tools.periodic_maintenance", "task_3_graph_density"),
    "archive_cleanup": ("orchestrator.tools.periodic_maintenance", "task_4_archive_cleanup"),
}

CADENCE_SECONDS = {
    "daily": 1 * 86400,
    "weekly": 7 * 86400,
    "monthly": 28 * 86400,
}

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_heartbeat():
    os.makedirs(_oversight_data_dir(), exist_ok=True)
    with open(_heartbeat_file(), "w") as f:
        json.dump({"watcher": "maintenance_scheduler", "beat_at": _now_iso()}, f)


def load_config() -> dict:
    """Read cadences from the control doc's frontmatter ``maintenance:``
    block, falling back to DEFAULT_CONFIG per-key on any problem.
    Unknown task names in the doc are ignored; unknown cadence values
    fall back to that task's default."""
    config = dict(DEFAULT_CONFIG)
    path = control_doc_path()
    if not os.path.isfile(path):
        return config
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        m = _FRONTMATTER_RE.match(text)
        if not m:
            return config
        import yaml
        fm = yaml.safe_load(m.group(1)) or {}
        block = fm.get("maintenance") or {}
        if not isinstance(block, dict):
            return config
        for task, cadence in block.items():
            if task not in DEFAULT_CONFIG:
                continue
            # YAML 1.1 parses a bare `off` as boolean False — map it back.
            if cadence is False:
                cadence = "off"
            elif cadence is True:
                continue  # `on` is not a cadence; keep the default
            else:
                cadence = str(cadence).strip().lower()
            if task in EVENT_ONLY_TASKS:
                # A vault edit cannot covert an event-only mutator back into
                # a periodic corpus sweep. Explicit campaigns use their own
                # command surface and never this scheduler.
                config[task] = "off"
            elif cadence == "off" or cadence in CADENCE_SECONDS:
                config[task] = cadence
    except Exception:
        return dict(DEFAULT_CONFIG)
    return config


def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def due_tasks(config: dict, state: dict, now: float | None = None) -> list[str]:
    """Tasks whose cadence window has elapsed since their last stamp.
    A task never run before is due immediately (unless off)."""
    now = time.time() if now is None else now
    due = []
    for task, cadence in config.items():
        if task in EVENT_ONLY_TASKS or task in DEADLINE_ONLY_TASKS:
            continue
        if cadence == "off":
            continue
        window = CADENCE_SECONDS.get(cadence)
        if window is None:
            continue
        last = state.get(task)
        if last is None:
            due.append(task)
            continue
        try:
            last_ts = datetime.fromisoformat(last).timestamp()
        except (ValueError, TypeError):
            due.append(task)
            continue
        if now - last_ts >= window:
            due.append(task)
    return due


def _run_task(task: str) -> dict:
    """Run one explicitly selected compatibility task."""
    import importlib
    mod_name, fn_name = TASK_FUNCTIONS[task]
    fn = getattr(importlib.import_module(mod_name), fn_name)
    result = fn()
    return {
        "task": task,
        "ran_at": _now_iso(),
        "success": bool(getattr(result, "success", False)),
        "message": getattr(result, "message", ""),
        "stats": getattr(result, "stats", {}) or {},
        "alerts": list(getattr(result, "alerts", []) or []),
        "duration_seconds": round(float(getattr(result, "duration_seconds", 0.0)), 2),
    }


def sweep(dry_run: bool = False, now: float | None = None,
          campaign_id: str | None = None) -> dict:
    """Run one explicit historical diagnostic campaign.

    The cadence calculation is migration-compatible task selection, not a
    production clock. A mutating invocation requires a bounded, auditable
    campaign identity.
    """
    config = load_config()
    state = _load_state()
    due = due_tasks(config, state, now=now)
    summary = {"config": config, "due": due, "ran": [], "failed": [],
               "dry_run": dry_run, "campaign_id": campaign_id}
    if dry_run:
        return summary
    if due and (not isinstance(campaign_id, str)
                or not _CAMPAIGN_ID_RE.fullmatch(campaign_id)):
        raise ValueError(
            "explicit maintenance campaign id required (1-128 safe characters)"
        )

    for task in due:
        # Stamp at start, not just at completion — if the task wedges or
        # the process dies mid-run, it must not be re-dispatched on the
        # very next sweep (the 2026-06-12 daemon wedge re-armed itself on
        # every server restart precisely because no stamp ever landed).
        state[task] = _now_iso()
        _save_state(state)
        try:
            record = _run_task(task)
        except Exception as e:
            record = {"task": task, "ran_at": _now_iso(), "success": False,
                      "message": f"scheduler-level failure: {e}", "stats": {},
                      "alerts": [], "duration_seconds": 0.0}
        record["campaign_id"] = campaign_id
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(RESULTS_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
        # Stamp even on failure — a broken task must not retry every
        # hour and hammer the vault; it retries on its normal cadence
        # and the failure is visible in maintenance-results.jsonl.
        state[task] = record["ran_at"]
        print(f"[maintenance_scheduler] {task}: "
              f"{'ok' if record['success'] else 'FAILED'} "
              f"in {record.get('duration_seconds', 0.0):.1f}s — {record.get('message', '')}")
        (summary["ran"] if record["success"] else summary["failed"]).append(task)

    if due:
        _save_state(state)
    _write_heartbeat()
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--campaign-id")
    args = parser.parse_args()
    out = sweep(dry_run=args.dry_run, campaign_id=args.campaign_id)
    print(json.dumps(out, indent=2))
