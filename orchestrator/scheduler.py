"""Lightweight task scheduler — runs periodic tasks using the orchestrator."""

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
    """Execute a single scheduled task."""
    try:
        from boot import load_boot_md, load_endpoints, get_slot_endpoint, call_model
    except ImportError as e:
        print(f"[scheduler] Import error: {e}")
        return

    config = load_endpoints()
    slot = task.get("model_slot", "small")
    endpoint = get_slot_endpoint(config, slot)
    if not endpoint:
        print(f"[scheduler] No endpoint for slot: {slot}")
        return

    system_prompt = load_boot_md()
    messages = [
        {"role": "system", "content": system_prompt + "\n\n[SCHEDULED TASK — autonomous mode. spawn_subagent and schedule_task are unavailable.]"},
        {"role": "user", "content": task["prompt"]},
    ]

    try:
        response = call_model(messages, endpoint)
    except Exception as e:
        response = f"[scheduler] Model error: {e}"

    # Write output
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(OUTPUT_DIR, f"{task['id']}_{ts}.md")
    with open(output_path, "w") as f:
        f.write(f"# Scheduled Task Output\n\n")
        f.write(f"Task: {task['id']}\n")
        f.write(f"Prompt: {task['prompt']}\n")
        f.write(f"Run at: {datetime.now().isoformat()}\n\n---\n\n")
        f.write(response)

    # Update registry
    task["last_run"] = datetime.now().isoformat()
    task["run_count"] = task.get("run_count", 0) + 1

    # Auto-deactivate old tasks
    settings = registry.get("settings", {})
    max_age_hours = settings.get("max_task_age_hours", 72)
    interval = task.get("interval_minutes", 30)
    if task["run_count"] * interval > max_age_hours * 60:
        task["active"] = False
        print(f"[scheduler] Task {task['id']} deactivated (exceeded max age)")

    _save_registry(registry)


class Scheduler:
    """Background scheduler that checks and runs tasks on an interval."""

    def __init__(self):
        self._running = False
        self._thread = None
        self._active_tasks = 0

    def start(self):
        """Start the scheduler as a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[scheduler] Started")

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        print("[scheduler] Stopped")

    def _loop(self):
        """Main scheduler loop — checks every 60 seconds."""
        while self._running:
            try:
                self._check_tasks()
            except Exception as e:
                print(f"[scheduler] Error: {e}")
            # Sleep in 1-second increments so we can stop quickly
            for _ in range(60):
                if not self._running:
                    break
                time.sleep(1)

    def _check_tasks(self):
        """Check all active tasks and run any that are due."""
        registry = _load_registry()
        settings = registry.get("settings", {})
        max_concurrent = settings.get("max_concurrent", 3)

        for task in registry.get("tasks", []):
            if not task.get("active", True):
                continue
            if self._active_tasks >= max_concurrent:
                break

            # Check if task is due
            interval = task.get("interval_minutes", 30)
            last_run = task.get("last_run")
            if last_run:
                from datetime import datetime as _dt
                try:
                    last = _dt.fromisoformat(last_run)
                    elapsed = (datetime.now() - last).total_seconds() / 60
                    if elapsed < interval:
                        continue
                except Exception:
                    pass

            # Run the task
            self._active_tasks += 1
            try:
                _run_task(task, registry)
            finally:
                self._active_tasks -= 1


# Module-level singleton
_scheduler = None


def get_scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler
