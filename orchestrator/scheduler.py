"""Retired interval scheduler compatibility surface.

G1.10 removed production interval dispatch. Exact event work uses
``runtime_event_dispatcher`` and justified temporal work uses persisted
one-shot ``runtime_hygiene.DeadlineQueue`` records. The old registry remains
readable for migration evidence, but this module cannot execute it.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime

WORKSPACE = os.path.expanduser("~/ora/")
REGISTRY_PATH = os.path.join(WORKSPACE, "config/scheduled-tasks.json")
OUTPUT_DIR = os.path.join(WORKSPACE, "output/scheduled/")


def _load_registry() -> dict:
    """Load the scheduled tasks registry."""
    if not os.path.exists(REGISTRY_PATH):
        return {"tasks": [], "settings": {
            "max_concurrent": 3, "default_model_slot": "small",
            "default_timeout_minutes": 10, "max_task_age_hours": 72,
        }}
    try:
        with open(REGISTRY_PATH) as f:
            return json.load(f)
    except Exception:
        return {"tasks": [], "settings": {}}


def _save_registry(registry: dict):
    """Save the scheduled tasks registry."""
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)


def _run_task(task: dict, registry: dict):
    """Fail closed even if a legacy caller reaches the private helper."""
    raise RuntimeError(
        "legacy scheduled task execution retired by G1.10; registry records "
        "are migration evidence only"
    )


class Scheduler:
    """Background scheduler that checks and runs tasks on an interval."""

    def __init__(self):
        self._running = False
        self._thread = None
        self._active_tasks = 0

    def start(self):
        """Fail closed; arbitrary recurring prompts have no runtime authority."""
        raise RuntimeError(
            "interval scheduler retired by G1.10; use an exact event contract "
            "or an authenticated one-shot deadline"
        )

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        print("[scheduler] Stopped")

    def _loop(self):
        raise RuntimeError("retired interval scheduler cannot run")

    def _check_tasks(self):
        """Fail closed even if a legacy caller bypasses :meth:`start`."""
        raise RuntimeError("retired interval scheduler cannot check or run tasks")


# Module-level singleton
_scheduler = None


def get_scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler
