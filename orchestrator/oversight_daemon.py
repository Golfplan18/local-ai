"""Oversight daemon — background loop that runs the watcher sweepers.

A lightweight singleton background thread that runs the PED watcher,
corpus watcher, workflow spec sweeper, and revisit sweeper at configured
intervals. Each sweeper emits its events through the oversight_events bus,
which the oversight router consumes.

Designed to be started from boot.py at server start — parallel to the
existing scheduler — and stopped on shutdown.

Per Reference — Meta-Layer Architecture §6 W2/W3/W4/W5 + §10 O1.

Author: meta-layer implementation per Reference — Meta-Layer Architecture.
"""
from __future__ import annotations

import os
import re
import threading
import time
from datetime import datetime, timezone

# Configurable intervals
DEFAULT_PED_WATCHER_INTERVAL_SEC = int(os.environ.get("ORA_PED_WATCHER_SEC", "60"))
DEFAULT_CORPUS_WATCHER_INTERVAL_SEC = int(os.environ.get("ORA_CORPUS_WATCHER_SEC", "60"))
DEFAULT_WORKFLOW_SWEEPER_INTERVAL_SEC = int(os.environ.get("ORA_WORKFLOW_SWEEPER_SEC", "300"))
DEFAULT_REVISIT_SWEEPER_INTERVAL_SEC = int(os.environ.get("ORA_REVISIT_SWEEPER_SEC", "3600"))
DEFAULT_RETENTION_SWEEPER_INTERVAL_SEC = int(os.environ.get("ORA_RETENTION_SWEEPER_SEC", "21600"))
DEFAULT_MAINTENANCE_SCHEDULER_INTERVAL_SEC = int(os.environ.get("ORA_MAINTENANCE_SCHEDULER_SEC", "3600"))

# Watchdog cadence + per-lane stall thresholds. The fast lane runs cheap
# file-diff watchers and should never be busy for more than seconds; the
# slow lane runs mechanical housekeeping (retention sweeps, vault-wide
# maintenance tasks) that can legitimately take tens of minutes.
DEFAULT_WATCHDOG_CHECK_SEC = int(os.environ.get("ORA_DAEMON_WATCHDOG_SEC", "30"))
DEFAULT_FAST_STALL_SEC = int(os.environ.get("ORA_DAEMON_FAST_STALL_SEC", "300"))
DEFAULT_SLOW_STALL_SEC = int(os.environ.get("ORA_DAEMON_SLOW_STALL_SEC", "7200"))

# Vault path — the canonical location for PEDs and other oversight artifacts.
VAULT_PATH = os.path.expanduser(os.environ.get("ORA_VAULT_PATH", "~/Documents/vault/"))

# Every module whose _write_heartbeat the daemon drives. The fast lane
# writes each one at startup, and the tests' oversight_sandbox fixture
# redirects each one's HEARTBEAT_FILE — importing this tuple keeps the
# two lists mechanically in sync.
WATCHER_HEARTBEAT_MODULES = (
    "ped_watcher",
    "corpus_watcher",
    "workflow_spec_sweeper",
    "revisit_sweeper",
    "retention_sweeper",
    "maintenance_scheduler",
)


def scan_vault_and_register_peds() -> list[tuple[str, str]]:
    """Walk the vault, identify PED files, and register any that aren't yet
    pointed at by ``~/ora/data/oversight/<nexus>/ped-path.json``.

    A PED is identified by having ``type: PED`` (or ``type: ped``) in YAML
    frontmatter, OR by a filename starting with ``PED `` or matching the
    pattern ``Project Matrix <Name>.md`` (the registry's matrix-file
    convention).

    Returns: list of (nexus, ped_path) for newly-registered projects.
    """
    if not os.path.isdir(VAULT_PATH):
        return []

    from ped_watcher import (
        list_known_projects,
        write_ped_pointer,
    )

    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None

    already_registered = set(list_known_projects())
    newly_registered: list[tuple[str, str]] = []

    for root, dirs, files in os.walk(VAULT_PATH):
        # Skip archive and noise directories
        if any(skip in root for skip in ("Old AI Working Files", "/.obsidian", "/Sessions")):
            continue
        for filename in files:
            if not filename.endswith(".md"):
                continue
            full_path = os.path.join(root, filename)
            ped_record = _identify_ped(full_path, yaml)
            if not ped_record:
                continue
            nexus = ped_record["nexus"]
            if nexus in already_registered:
                continue
            try:
                write_ped_pointer(nexus, full_path)
                newly_registered.append((nexus, full_path))
                already_registered.add(nexus)
            except Exception as e:
                print(f"[oversight_daemon] failed to register {nexus}: {e}")

    return newly_registered


def _identify_ped(path: str, yaml_module) -> dict | None:
    """Return {"nexus": str} if the file looks like a PED, else None.

    Heuristics:
      - YAML frontmatter has ``type: PED`` (case-insensitive)
      - Filename starts with ``PED `` (case-insensitive)
      - YAML has ``nexus:`` field; if present, use that as the project nexus.
        Otherwise derive from the filename.
    """
    filename = os.path.basename(path)
    type_is_ped = False
    nexus_value: str | None = None

    # Read the YAML frontmatter only (first 80 lines is enough)
    try:
        with open(path, encoding="utf-8") as f:
            first_chunk = f.read(8192)
    except OSError:
        return None

    fm_text = ""
    if first_chunk.startswith("---\n"):
        end = first_chunk.find("\n---\n", 4)
        if end > 0:
            fm_text = first_chunk[4:end]

    if fm_text and yaml_module is not None:
        try:
            fm = yaml_module.safe_load(fm_text) or {}
        except Exception:
            fm = {}
        if isinstance(fm, dict):
            ftype = fm.get("type", "")
            if isinstance(ftype, str) and ftype.lower() == "ped":
                type_is_ped = True
            nexus_field = fm.get("nexus")
            if isinstance(nexus_field, list) and nexus_field:
                nexus_value = str(nexus_field[0])
            elif isinstance(nexus_field, str):
                nexus_value = nexus_field

    # Filename heuristic
    filename_indicates_ped = filename.lower().startswith("ped ")

    if not (type_is_ped or filename_indicates_ped):
        return None

    if not nexus_value:
        # Derive nexus from filename: "PED My Project.md" -> "my_project"
        stem = filename
        for prefix in ("PED ", "ped "):
            if stem.startswith(prefix):
                stem = stem[len(prefix):]
                break
        stem = stem.removesuffix(".md")
        nexus_value = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")

    if not nexus_value:
        return None

    return {"nexus": nexus_value}


def scan_vault_and_register_workflows() -> list[tuple[str, str]]:
    """Walk the vault for workflow spec files and register any not yet pointed at.

    A workflow spec is identified by:
      - YAML frontmatter has ``tags`` containing ``workflow-spec`` OR
      - YAML frontmatter has ``type: framework`` with ``workflow_id`` field, OR
      - filename matches ``workflow-spec.md`` (the integration architecture
        convention)

    Returns: list of (workflow_id, workflow_spec_path) for newly-registered.
    """
    if not os.path.isdir(VAULT_PATH):
        return []

    from corpus_watcher import (
        list_known_workflows,
        write_workflow_pointer,
    )

    try:
        import yaml as _yaml  # type: ignore
    except ImportError:
        _yaml = None

    already_registered = set(list_known_workflows())
    newly_registered: list[tuple[str, str]] = []

    # Also walk ~/ora/workflows/ which is the convention for workflow spec files
    search_roots = [VAULT_PATH, os.path.expanduser("~/ora/workflows/")]

    for root_path in search_roots:
        if not os.path.isdir(root_path):
            continue
        for root, dirs, files in os.walk(root_path):
            if any(skip in root for skip in ("Old AI Working Files", "/.obsidian", "/Sessions")):
                continue
            for filename in files:
                if not filename.endswith(".md"):
                    continue
                full_path = os.path.join(root, filename)
                spec_record = _identify_workflow_spec(full_path, _yaml)
                if not spec_record:
                    continue
                workflow_id = spec_record["workflow_id"]
                if workflow_id in already_registered:
                    continue
                try:
                    write_workflow_pointer(
                        workflow_id=workflow_id,
                        project_nexus=spec_record.get("project_nexus", ""),
                        workflow_spec_path=full_path,
                        corpus_template_path=spec_record.get("corpus_template_path", ""),
                        corpus_instance_directory=spec_record.get("corpus_instance_directory", ""),
                    )
                    newly_registered.append((workflow_id, full_path))
                    already_registered.add(workflow_id)
                except Exception as e:
                    print(f"[oversight_daemon] failed to register workflow {workflow_id}: {e}")

    return newly_registered


def _identify_workflow_spec(path: str, yaml_module) -> dict | None:
    """Return workflow record dict if file is a workflow spec, else None."""
    filename = os.path.basename(path)

    try:
        with open(path, encoding="utf-8") as f:
            first_chunk = f.read(8192)
    except OSError:
        return None

    fm_text = ""
    if first_chunk.startswith("---\n"):
        end = first_chunk.find("\n---\n", 4)
        if end > 0:
            fm_text = first_chunk[4:end]

    if not fm_text or yaml_module is None:
        # Filename heuristic only
        if filename == "workflow-spec.md":
            workflow_id = os.path.basename(os.path.dirname(path)) or "unnamed_workflow"
            return {"workflow_id": workflow_id}
        return None

    try:
        fm = yaml_module.safe_load(fm_text) or {}
    except Exception:
        fm = {}

    if not isinstance(fm, dict):
        return None

    tags = fm.get("tags", []) or []
    if isinstance(tags, str):
        tags = [tags]

    is_workflow_spec = (
        "workflow-spec" in tags
        or "workflow_spec" in tags
        or filename == "workflow-spec.md"
        or (fm.get("type") == "framework" and fm.get("workflow_id"))
    )

    if not is_workflow_spec:
        return None

    workflow_id = (
        fm.get("workflow_id")
        or fm.get("workflow")
        or os.path.basename(os.path.dirname(path))
        or os.path.splitext(filename)[0]
    )
    workflow_id = re.sub(r"[^a-z0-9]+", "_", str(workflow_id).lower()).strip("_")

    project_nexus = ""
    nexus_field = fm.get("nexus")
    if isinstance(nexus_field, list) and nexus_field:
        project_nexus = str(nexus_field[0])
    elif isinstance(nexus_field, str):
        project_nexus = nexus_field

    return {
        "workflow_id": workflow_id,
        "project_nexus": project_nexus,
        "corpus_template_path": _resolve_path(fm.get("corpus_template", ""), path),
        "corpus_instance_directory": _resolve_path(fm.get("corpus_instance_directory", ""), path),
    }


def _resolve_path(p: str, relative_to: str) -> str:
    """Expand ~ and resolve relative paths relative to a reference file."""
    if not p:
        return ""
    p = os.path.expanduser(p)
    if not os.path.isabs(p):
        p = os.path.normpath(os.path.join(os.path.dirname(relative_to), p))
    return p


class OversightDaemon:
    """Background scheduler for oversight watchers.

    Sweeps run on two lanes so heavy housekeeping can never starve the
    heartbeats the health check watches:

      - **fast lane**: ped / corpus / workflow-spec / revisit watchers —
        cheap file-diff sweeps on 60s–3600s cadences.
      - **slow lane**: retention sweeper + maintenance scheduler (vault-wide
        walks, can legitimately run for many minutes), plus the one-shot
        vault auto-registration scan.

    A watchdog thread monitors both lanes' iteration ticks. When a lane
    stalls past its threshold (a sweep wedged in a long computation or an
    unbounded call), the watchdog logs the stuck thread's Python stack and
    starts a replacement lane thread; the abandoned thread exits at its
    next generation check if it ever unwedges. This is what turned the
    2026-06-12 incident (maintenance task spinning for hours, every
    heartbeat stale, degraded banner on every chat reply) from an outage
    into a logged restart.
    """

    def __init__(self):
        self._running = False
        self._fast_thread: threading.Thread | None = None
        self._slow_thread: threading.Thread | None = None
        self._watchdog_thread: threading.Thread | None = None
        self._last_run: dict[str, float] = {}
        # Lane generations: bumped on every (re)start of a lane. A lane
        # thread exits as soon as it notices its generation is stale, so a
        # watchdog restart can't leave two live loops racing each other.
        self._fast_gen = 0
        self._slow_gen = 0
        # Last time each lane completed a loop iteration.
        self._fast_tick = 0.0
        self._slow_tick = 0.0
        self._vault_scan_done = False

    def start(self):
        """Start the daemon. Idempotent.

        Only fast actions run synchronously; slow ones (vault auto-scans)
        run inside the slow-lane thread so server startup is not blocked.
        The vault scans walk every markdown file under ``VAULT_PATH``,
        which can take several minutes on a populated vault — keeping
        them on the startup critical path made ``./start.sh --oversight``
        time out before binding the HTTP port.
        """
        if self._running:
            return
        # Wire the router as an event handler before starting the loop.
        # Router install is fast (~20ms); leave it on the synchronous path
        # so the daemon is fully wired before start() returns.
        try:
            from oversight_router import install as install_router
            install_router()
        except Exception as e:
            print(f"[oversight_daemon] router install failed: {e}")

        self._running = True
        self._start_fast_lane()
        self._start_slow_lane()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog, daemon=True, name="oversight-watchdog")
        self._watchdog_thread.start()
        print("[oversight_daemon] Started (fast/slow sweep lanes + watchdog; "
              "vault auto-registration on slow lane)")

    def _start_fast_lane(self):
        self._fast_gen += 1
        self._fast_tick = time.time()
        self._fast_thread = threading.Thread(
            target=self._fast_loop, args=(self._fast_gen,), daemon=True,
            name=f"oversight-fast-{self._fast_gen}")
        self._fast_thread.start()

    def _start_slow_lane(self):
        self._slow_gen += 1
        self._slow_tick = time.time()
        self._slow_thread = threading.Thread(
            target=self._slow_loop, args=(self._slow_gen,), daemon=True,
            name=f"oversight-slow-{self._slow_gen}")
        self._slow_thread.start()

    def _initial_vault_scan(self):
        """Auto-register PEDs and workflow specs found in the vault.

        Idempotent — only newly-discovered files get pointer-written.
        Slow on large vaults (the scan walks every .md file and parses
        YAML frontmatter), which is why it runs in the daemon thread
        rather than on the server's startup path.
        """
        try:
            registered = scan_vault_and_register_peds()
            if registered:
                print(f"[oversight_daemon] Auto-registered {len(registered)} project(s) from vault scan")
                for nexus, path in registered:
                    print(f"  - {nexus}: {path}")
        except Exception as e:
            print(f"[oversight_daemon] vault scan failed: {e}")

        try:
            registered_workflows = scan_vault_and_register_workflows()
            if registered_workflows:
                print(f"[oversight_daemon] Auto-registered {len(registered_workflows)} workflow(s) from vault scan")
                for workflow_id, path in registered_workflows:
                    print(f"  - {workflow_id}: {path}")
        except Exception as e:
            print(f"[oversight_daemon] workflow scan failed: {e}")

    def stop(self):
        """Stop the daemon."""
        self._running = False
        for t in (self._fast_thread, self._slow_thread, self._watchdog_thread):
            if t:
                t.join(timeout=5)
        print("[oversight_daemon] Stopped")

    def run_once(self):
        """Run all sweepers once, regardless of interval. For tests / CLI."""
        from oversight_events import emit
        self._run_ped_watcher(emit)
        self._run_corpus_watcher(emit)
        self._run_workflow_spec_sweeper(emit)
        self._run_revisit_sweeper(emit)
        self._run_retention_sweeper()
        self._run_maintenance_scheduler()

    def _fast_loop(self, gen: int):
        """Fast lane — cheap file-diff watchers, once-per-5s due check."""
        from oversight_events import emit

        # Write an immediate heartbeat for each watcher so the health
        # check sees a fresh signal as soon as the daemon starts, rather
        # than stale heartbeats from a prior run ("daemon down").
        for watcher_mod_name in WATCHER_HEARTBEAT_MODULES:
            try:
                _mod = __import__(watcher_mod_name)
                _mod._write_heartbeat()
            except Exception as e:
                print(f"[oversight_daemon] startup heartbeat for {watcher_mod_name} failed: {e}")

        while self._running and self._fast_gen == gen:
            now = time.time()
            try:
                self._maybe_run("ped_watcher", DEFAULT_PED_WATCHER_INTERVAL_SEC, now,
                                lambda: self._run_ped_watcher(emit))
                self._maybe_run("corpus_watcher", DEFAULT_CORPUS_WATCHER_INTERVAL_SEC, now,
                                lambda: self._run_corpus_watcher(emit))
                self._maybe_run("workflow_spec_sweeper", DEFAULT_WORKFLOW_SWEEPER_INTERVAL_SEC, now,
                                lambda: self._run_workflow_spec_sweeper(emit))
                self._maybe_run("revisit_sweeper", DEFAULT_REVISIT_SWEEPER_INTERVAL_SEC, now,
                                lambda: self._run_revisit_sweeper(emit))
            except Exception as e:
                import traceback
                print(f"[oversight_daemon] fast-lane loop error: {e}\n{traceback.format_exc()}")

            if self._fast_gen == gen:
                self._fast_tick = time.time()
            self._lane_sleep(5, lambda: self._fast_gen == gen)

    def _slow_loop(self, gen: int):
        """Slow lane — mechanical housekeeping that may run for minutes.

        Runs the one-shot vault auto-registration scan first (previously
        on the fast path, where its multi-minute walk delayed the first
        watcher sweeps; before that it was on the synchronous ``start()``
        path, where it blocked the HTTP port from binding).
        """
        if not self._vault_scan_done:
            self._initial_vault_scan()
            self._vault_scan_done = True

        while self._running and self._slow_gen == gen:
            now = time.time()
            try:
                self._maybe_run("retention_sweeper", DEFAULT_RETENTION_SWEEPER_INTERVAL_SEC, now,
                                self._run_retention_sweeper)
                self._maybe_run("maintenance_scheduler", DEFAULT_MAINTENANCE_SCHEDULER_INTERVAL_SEC, now,
                                self._run_maintenance_scheduler)
            except Exception as e:
                import traceback
                print(f"[oversight_daemon] slow-lane loop error: {e}\n{traceback.format_exc()}")

            if self._slow_gen == gen:
                self._slow_tick = time.time()
            self._lane_sleep(5, lambda: self._slow_gen == gen)

    def _lane_sleep(self, seconds: int, gen_is_current):
        """Sleep in 1-second increments so stop() and lane replacement
        take effect quickly."""
        for _ in range(seconds):
            if not self._running or not gen_is_current():
                break
            time.sleep(1)

    def _watchdog(self):
        """Monitor both lanes; restart a lane whose loop has stalled.

        A stalled lane means a sweep is stuck inside a long computation or
        an unbounded call. Python threads can't be killed, so the watchdog
        logs the stuck thread's stack (the diagnostic that otherwise needs
        an external profiler), bumps the lane generation, and starts a
        replacement thread. ``_last_run`` is preserved, so the sweep that
        wedged is not immediately re-dispatched by the new thread.
        """
        while self._running:
            for _ in range(DEFAULT_WATCHDOG_CHECK_SEC):
                if not self._running:
                    return
                time.sleep(1)
            try:
                self._check_lane("fast", self._fast_thread, self._fast_tick,
                                 DEFAULT_FAST_STALL_SEC, self._start_fast_lane)
                self._check_lane("slow", self._slow_thread, self._slow_tick,
                                 DEFAULT_SLOW_STALL_SEC, self._start_slow_lane)
            except Exception as e:
                import traceback
                print(f"[oversight_daemon] watchdog error: {e}\n{traceback.format_exc()}")

    def _check_lane(self, name: str, thread, tick: float, stall_sec: int, restart):
        if thread is None or not self._running:
            return
        age = time.time() - tick
        if not thread.is_alive():
            print(f"[oversight_daemon] WATCHDOG: {name} lane thread died — restarting lane")
            restart()
        elif age > stall_sec:
            print(f"[oversight_daemon] WATCHDOG: {name} lane has not completed a loop "
                  f"iteration in {int(age)}s (threshold {stall_sec}s) — dumping stack "
                  f"and restarting lane")
            self._dump_thread_stack(thread, f"{name} lane (stalled)")
            restart()

    @staticmethod
    def _dump_thread_stack(thread, label: str):
        """Log the current Python stack of a (presumably wedged) thread."""
        try:
            import sys
            import traceback
            frame = sys._current_frames().get(thread.ident)
            if frame is not None:
                stack = "".join(traceback.format_stack(frame))
                print(f"[oversight_daemon] {label} stack (most recent call last):\n{stack}")
            else:
                print(f"[oversight_daemon] {label}: no frame found for thread {thread.ident}")
        except Exception as e:
            print(f"[oversight_daemon] stack dump for {label} failed: {e}")

    def _maybe_run(self, name: str, interval: int, now: float, fn):
        last = self._last_run.get(name, 0)
        if now - last >= interval:
            self._last_run[name] = now
            started = time.time()
            fn()
            duration = time.time() - started
            if duration > interval:
                print(f"[oversight_daemon] {name} sweep took {duration:.1f}s — "
                      f"longer than its {interval}s interval; next run is delayed")

    def _run_ped_watcher(self, emit):
        try:
            import ped_watcher
            events = ped_watcher.sweep()
            for evt in events:
                emit(evt)
        except Exception as e:
            print(f"[oversight_daemon] ped_watcher failed: {e}")

    def _run_corpus_watcher(self, emit):
        try:
            import corpus_watcher
            events = corpus_watcher.sweep()
            for evt in events:
                emit(evt)
        except Exception as e:
            print(f"[oversight_daemon] corpus_watcher failed: {e}")

    def _run_workflow_spec_sweeper(self, emit):
        try:
            import workflow_spec_sweeper
            workflow_spec_sweeper.sweep(emit_event=emit)
        except Exception as e:
            print(f"[oversight_daemon] workflow_spec_sweeper failed: {e}")

    def _run_revisit_sweeper(self, emit):
        try:
            import revisit_sweeper
            revisit_sweeper.sweep(emit_event=emit)
        except Exception as e:
            print(f"[oversight_daemon] revisit_sweeper failed: {e}")

    def _run_retention_sweeper(self):
        # Mechanical housekeeping — no oversight events to emit.
        try:
            import retention_sweeper
            summary = retention_sweeper.sweep()
            acted = (summary["traces_removed"] or summary["logs_archived"]
                     or summary["archives_deleted"] or summary["server_log_rotated"]
                     or summary["jsonl_rotated"] or summary["sessions_archived"])
            if acted:
                print(f"[oversight_daemon] retention sweep: {summary}")
        except Exception as e:
            print(f"[oversight_daemon] retention_sweeper failed: {e}")

    def _run_maintenance_scheduler(self):
        # Vault-governed periodic maintenance (Reference — Ora Periodic
        # Maintenance.md drives cadences). Mechanical — no events.
        try:
            import maintenance_scheduler
            summary = maintenance_scheduler.sweep()
            if summary["ran"] or summary["failed"]:
                print(f"[oversight_daemon] maintenance: ran={summary['ran']} failed={summary['failed']}")
        except Exception as e:
            print(f"[oversight_daemon] maintenance_scheduler failed: {e}")


# ---------- Module-level singleton ----------

_daemon = None


def get_daemon() -> OversightDaemon:
    global _daemon
    if _daemon is None:
        _daemon = OversightDaemon()
    return _daemon


# ---------- CLI smoke test ----------

if __name__ == "__main__":
    """Run all sweepers once and exit."""
    d = get_daemon()
    d.run_once()
    print("[oversight_daemon] One-shot sweep complete.")
