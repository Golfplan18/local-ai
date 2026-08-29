"""Oversight daemon — event and deadline runtime for oversight maintenance.

A lightweight singleton that blocks on operating-system file events and exact
persisted deadlines. Manual ``run_once`` remains available for diagnostics and
maintenance; production ``start()`` has no interval scheduler.

Designed to be started from boot.py at server start — parallel to the
existing scheduler — and stopped on shutdown.

Per Reference — Meta-Layer Architecture §6 W2/W3/W4/W5 + §10 O1.

Author: meta-layer implementation per Reference — Meta-Layer Architecture.
"""
from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator import runtime_paths as _rp

# Watchdog cadence for the live event and deadline lanes.
DEFAULT_WATCHDOG_CHECK_SEC = int(os.environ.get("ORA_DAEMON_WATCHDOG_SEC", "30"))

# Vault path — the canonical location for PEDs and other oversight artifacts.
_DEFAULT_VAULT_PATH = _rp.VAULT_STR
VAULT_PATH = _DEFAULT_VAULT_PATH  # compatibility patch hook
_SCAN_SKIP_DIRS = {"Archive", ".obsidian", "Sessions"}


def _vault_path() -> str:
    if VAULT_PATH != _DEFAULT_VAULT_PATH:
        return VAULT_PATH
    return str(_rp.vault_dir())


def _prune_scan_dirs(dirs: list[str]) -> None:
    """Prune by path component, independent of slash direction."""
    dirs[:] = [name for name in dirs if name not in _SCAN_SKIP_DIRS]


def _local_timezone_name() -> str:
    """Resolve a named IANA zone; fixed offsets cannot govern calendar work."""
    configured = os.environ.get("ORA_LOCAL_TIMEZONE", "").strip()
    if configured:
        try:
            ZoneInfo(configured)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown ORA_LOCAL_TIMEZONE: {configured}") from exc
        return configured
    try:
        resolved = str(Path("/etc/localtime").resolve())
    except OSError as exc:
        raise RuntimeError("cannot resolve the local named timezone") from exc
    marker = "/zoneinfo/"
    if marker not in resolved:
        raise RuntimeError(
            "calendar deadlines require ORA_LOCAL_TIMEZONE or a named /etc/localtime zone"
        )
    name = resolved.split(marker, 1)[1]
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"local timezone is not an IANA zone: {name}") from exc
    return name


def _calendar_midnight_after(completed_date: str, timezone_name: str) -> datetime:
    from datetime import date, timedelta
    day = date.fromisoformat(completed_date)
    return datetime.combine(
        day + timedelta(days=1), datetime.min.time(), tzinfo=ZoneInfo(timezone_name),
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
    vault_path = _vault_path()
    if not os.path.isdir(vault_path):
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

    for root, dirs, files in os.walk(vault_path):
        _prune_scan_dirs(dirs)
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
    vault_path = _vault_path()
    if not os.path.isdir(vault_path):
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

    # Also walk the configured Ora workspace's workflow-spec directory.
    search_roots = [vault_path, str(_rp.ORA_HOME / "workflows")]

    for root_path in search_roots:
        if not os.path.isdir(root_path):
            continue
        for root, dirs, files in os.walk(root_path):
            _prune_scan_dirs(dirs)
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
    """Event/deadline runtime for oversight work.

    Production owns two blocking lanes: operating-system file notifications
    and a persisted exact-deadline queue. The watchdog restarts either lane
    if it exits. Manual maintenance remains available through :meth:`run_once`.
    """

    def __init__(self):
        self._running = False
        self._watchdog_thread: threading.Thread | None = None
        # Watchdog restarts per lane, and when the most recent one happened.
        # A lane that keeps dying reads as "alive" on every liveness check;
        # only the count exposes the loop.
        self._lane_restarts: dict[str, int] = {}
        self._lane_restart_at: dict[str, float] = {}
        self._event_thread: threading.Thread | None = None
        self._deadline_thread: threading.Thread | None = None
        self._bootstrap_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._deadline_queue = None

    def start(self):
        """Start the daemon without putting vault reconciliation on boot's
        synchronous critical path."""
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
        self._stop_event.clear()
        from orchestrator.runtime_hygiene import (
            deadline_queue,
            recover_retention_intents,
        )
        self._deadline_queue = deadline_queue()
        recovery = recover_retention_intents(queue=self._deadline_queue)
        if recovery["failed"]:
            print("[oversight_daemon] retention intent recovery failed: "
                  f"{recovery['failed']}")
        self._ensure_daily_note_deadline()
        self._ensure_log_retention_deadline()
        self._event_thread = threading.Thread(
            target=self._event_loop, daemon=True, name="oversight-file-events")
        self._deadline_thread = threading.Thread(
            target=self._deadline_loop, daemon=True, name="oversight-deadlines")
        self._event_thread.start()
        self._deadline_thread.start()
        # Server startup is a real event. Its full registration reconciliation
        # can take minutes on a populated vault, so run it once after both live
        # blocking lanes are listening; never put it back on the HTTP bind path.
        self._bootstrap_thread = threading.Thread(
            target=self._bootstrap_reconciliation, daemon=True,
            name="oversight-startup-reconciliation")
        self._bootstrap_thread.start()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog, daemon=True, name="oversight-watchdog")
        self._watchdog_thread.start()
        print("[oversight_daemon] Started (OS file events + exact persisted deadlines; "
              "no sweep cadence)")

    def _bootstrap_reconciliation(self):
        self._initial_vault_scan()
        try:
            import revisit_sweeper
            revisit_sweeper.register_age_review_deadlines(self._deadline_queue)
        except Exception as exc:
            print(f"[oversight_daemon] revisit deadline registration failed: {exc}")
        try:
            # Re-arm the occurrences the persisted Trigger set already
            # declares. This is reconciliation of exact contracts, not a scan
            # for undiscovered work.
            from orchestrator import triggers
            armed = triggers.service().arm_active_calendar_triggers()
            if armed:
                print(f"[oversight_daemon] armed {len(armed)} calendar Trigger(s)")
        except Exception as exc:
            print(f"[oversight_daemon] Trigger arming failed: {exc}")

    def _event_loop(self):
        try:
            from orchestrator.runtime_event_dispatcher import run
            run(self._stop_event)
        except Exception as exc:
            if self._running:
                print(f"[oversight_daemon] event lane failed: {exc}")

    def _deadline_loop(self):
        assert self._deadline_queue is not None
        handlers = {
            "daily_note": self._handle_daily_note_deadline,
            "project_revisit": self._handle_project_revisit_deadline,
            "trace_retention": self._handle_trace_retention_deadline,
            "log_retention": self._handle_log_retention_deadline,
            "trigger_calendar": self._handle_trigger_calendar_deadline,
        }
        try:
            self._deadline_queue.run(handlers, self._stop_event)
        except Exception as exc:
            if self._running:
                print(f"[oversight_daemon] deadline lane failed: {exc}")

    def _ensure_daily_note_deadline(self, completed_date: str | None = None,
                                    timezone_name: str | None = None):
        timezone_name = timezone_name or _local_timezone_name()
        zone = ZoneInfo(timezone_name)
        day = (datetime.fromisoformat(completed_date).date()
               if completed_date else datetime.now(zone).date())
        due = _calendar_midnight_after(day.isoformat(), timezone_name)
        legacy_key = f"daily-note:{day.isoformat()}"
        legacy = self._deadline_queue.get(legacy_key)
        if legacy and legacy.get("status") == "pending":
            self._deadline_queue.cancel(
                legacy_key,
                reason=("migrated from fixed-offset calendar deadline to "
                        f"named timezone {timezone_name}"),
            )
        timezone_key = hashlib.sha256(timezone_name.encode("utf-8")).hexdigest()[:12]
        return self._deadline_queue.put(
            f"daily-note-v2:{day.isoformat()}:{timezone_key}",
            due.isoformat(), "daily_note",
            {"completed_date": day.isoformat(), "timezone": timezone_name},
        )

    def _handle_daily_note_deadline(self, payload: dict):
        from datetime import date, timedelta
        from orchestrator.tools.daily_note import task_daily_note
        completed_date = str(payload["completed_date"])
        # Legacy persisted contracts did not include a named zone. Resolve it
        # once at dispatch and ensure every chained contract carries the name.
        timezone_name = str(payload.get("timezone") or _local_timezone_name())
        date.fromisoformat(completed_date)
        ZoneInfo(timezone_name)
        try:
            result = task_daily_note(date_str=completed_date)
            if not getattr(result, "success", False):
                raise RuntimeError(getattr(result, "message", "daily note failed"))
            return {
                "status": "completed", "completed_date": completed_date,
                "message": getattr(result, "message", ""),
            }
        finally:
            # The next calendar day is a distinct time-caused contract, not a
            # retry of this deadline. Advance from the persisted contract—not
            # wall-clock "yesterday"—so restart catches up each missed day
            # without silently binding evidence to the wrong calendar date.
            next_day = date.fromisoformat(completed_date) + timedelta(days=1)
            self._ensure_daily_note_deadline(
                next_day.isoformat(), timezone_name=timezone_name,
            )

    def _ensure_log_retention_deadline(self, completed_date: str | None = None,
                                       timezone_name: str | None = None):
        """Arm one exact deadline for age- and size-caused log retention.

        G1.10 removed this sweeper's 6-hour interval and moved trace expiry to
        per-trace deadlines, but nothing was left to drive log ageing or
        archive expiry — they stopped on 2026-07-21. Age is the cause here and
        no event can announce it, so the sanctioned primitive is an exact
        persisted deadline that arms its successor, not a rediscovery scan.
        """
        timezone_name = timezone_name or _local_timezone_name()
        zone = ZoneInfo(timezone_name)
        day = (datetime.fromisoformat(completed_date).date()
               if completed_date else datetime.now(zone).date())
        due = _calendar_midnight_after(day.isoformat(), timezone_name)
        timezone_key = hashlib.sha256(timezone_name.encode("utf-8")).hexdigest()[:12]
        return self._deadline_queue.put(
            f"log-retention:{day.isoformat()}:{timezone_key}",
            due.isoformat(), "log_retention",
            {"completed_date": day.isoformat(), "timezone": timezone_name},
        )

    def _handle_log_retention_deadline(self, payload: dict):
        from datetime import date, timedelta
        import retention_sweeper
        completed_date = str(payload["completed_date"])
        timezone_name = str(payload.get("timezone") or _local_timezone_name())
        date.fromisoformat(completed_date)
        ZoneInfo(timezone_name)
        try:
            summary = retention_sweeper.sweep_log_retention()
            return {
                "status": "completed", "completed_date": completed_date,
                "logs_archived": summary.get("logs_archived", 0),
                "archives_deleted": summary.get("archives_deleted", 0),
                "bytes_freed": summary.get("bytes_freed", 0),
                "errors": summary.get("errors", []),
            }
        finally:
            # Advance from the persisted contract, not wall-clock "today", so a
            # restart catches up each missed day exactly once.
            next_day = date.fromisoformat(completed_date) + timedelta(days=1)
            self._ensure_log_retention_deadline(
                next_day.isoformat(), timezone_name=timezone_name,
            )

    def _handle_trigger_calendar_deadline(self, payload: dict):
        """Dispatch one user-authored calendar Trigger occurrence.

        The Trigger service claims the firing here and runs the work off this
        lane — a framework run takes minutes and this thread also owns the
        daily note, log retention, and every trace expiration.
        """
        from orchestrator import triggers
        return triggers.service().handle_calendar_deadline(payload)

    def _handle_project_revisit_deadline(self, payload: dict):
        from oversight_events import emit
        import revisit_sweeper
        event = revisit_sweeper.sweep_project(payload["nexus"], payload["ped_path"])
        if event:
            emit(event)
        return {"status": "completed", "event_emitted": bool(event)}

    def _handle_trace_retention_deadline(self, payload: dict):
        import shutil
        from pathlib import Path
        from orchestrator import pipeline_trace
        import retention_sweeper

        trace_ref = payload.get("trace_ref")
        expected_finalized_at = payload.get("finalized_at")
        parts = pipeline_trace._trace_ref_parts(trace_ref)
        if parts is None:
            raise ValueError("invalid trace-retention reference")
        conversation_id, turn = parts
        with _rp.conversation_lifecycle_lock(conversation_id):
            try:
                exact = pipeline_trace._safe_trace_dir(
                    conversation_id, turn, create=False,
                )
            except Exception as exc:
                return {
                    "status": "preserved_uncertain", "trace_ref": trace_ref,
                    "reason": f"trace directory is inconsistent: {exc}",
                }
            if not exact.exists() and not exact.is_symlink():
                return {"status": "already_absent", "trace_ref": trace_ref}
            if exact.is_symlink() or not exact.is_dir():
                return {
                    "status": "preserved_uncertain", "trace_ref": trace_ref,
                    "reason": "trace directory is not an owned ordinary directory",
                }
            manifest, uncertainty = retention_sweeper._read_retention_manifest(
                Path(exact), conversation_id, turn,
            )
            if uncertainty is not None:
                return {
                    "status": "preserved_uncertain", "trace_ref": trace_ref,
                    "reason": uncertainty,
                }
            if manifest.get("finalized_at") != expected_finalized_at:
                return {
                    "status": "preserved_uncertain", "trace_ref": trace_ref,
                    "reason": "manifest finalization identity is inconsistent",
                }
            if manifest.get("retention_state") == "pinned":
                return {"status": "preserved_pinned", "trace_ref": trace_ref}
            shutil.rmtree(exact)
            try:
                exact.parent.rmdir()
            except OSError:
                pass
            return {"status": "deleted", "trace_ref": trace_ref}

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
        self._stop_event.set()
        if self._deadline_queue is not None:
            self._deadline_queue.wake()
        for t in (self._event_thread, self._deadline_thread,
                  self._bootstrap_thread, self._watchdog_thread):
            if t:
                t.join(timeout=5)
        print("[oversight_daemon] Stopped")

    def run_once(self):
        """Run the manual maintenance and watcher sweepers once."""
        from oversight_events import emit
        self._run_ped_watcher(emit)
        self._run_corpus_watcher(emit)
        self._run_workflow_spec_sweeper(emit)
        self._run_revisit_sweeper(emit)
        self._run_retention_sweeper()
        self._run_maintenance_scheduler()
        self._run_resources_watcher()

    def _watchdog(self):
        """Monitor and recover the production event/deadline lanes."""
        while self._running:
            for _ in range(DEFAULT_WATCHDOG_CHECK_SEC):
                if not self._running:
                    return
                time.sleep(1)
            try:
                if self._event_thread is not None and not self._event_thread.is_alive():
                    print("[oversight_daemon] WATCHDOG: event lane died — restarting")
                    self._record_restart("event_lane")
                    self._event_thread = threading.Thread(
                        target=self._event_loop, daemon=True,
                        name="oversight-file-events-restart")
                    self._event_thread.start()
                if (self._deadline_thread is not None
                        and not self._deadline_thread.is_alive()):
                    print("[oversight_daemon] WATCHDOG: deadline lane died — restarting")
                    self._record_restart("deadline_lane")
                    self._deadline_thread = threading.Thread(
                        target=self._deadline_loop, daemon=True,
                        name="oversight-deadlines-restart")
                    self._deadline_thread.start()
            except Exception as e:
                import traceback
                print(f"[oversight_daemon] watchdog error: {e}\n{traceback.format_exc()}")

    def _record_restart(self, lane: str) -> None:
        """Count watchdog restarts so a crash loop is distinguishable from health.

        Thread liveness alone always reads healthy under a watchdog: the lane
        is dead for under 30s and alive again by the next check. The event lane
        crashed 2,257 times before 2026-08-16 without one warning reaching the
        user. The count is what makes the loop visible.
        """
        self._lane_restarts[lane] = self._lane_restarts.get(lane, 0) + 1
        self._lane_restart_at[lane] = time.time()

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

    def _run_resources_watcher(self):
        # External document conversion + vault conformance.  The module owns
        # its audit events; this wrapper only keeps daemon failures loud.
        try:
            import resources_watcher
            summary = resources_watcher.sweep()
            if (summary["processed"] or summary["orphans_moved"]
                    or summary["errors"]):
                print(
                    "[oversight_daemon] resources: "
                    f"processed={summary['processed']} "
                    f"orphans_moved={summary['orphans_moved']} "
                    f"errors={len(summary['errors'])}",
                )
        except Exception as e:
            print(f"[oversight_daemon] resources_watcher failed: {e}")


# ---------- Module-level singleton ----------

_daemon = None


def get_daemon() -> OversightDaemon:
    global _daemon
    if _daemon is None:
        _daemon = OversightDaemon()
    return _daemon


def runtime_health() -> dict:
    """Return the in-process event/deadline liveness contract.

    Unlike a heartbeat timestamp, this remains accurate while the event
    listener is correctly blocked awaiting an OS notification.
    """
    daemon = _daemon
    if daemon is None or not daemon._running:
        return {
            "running": False, "event_lane": False, "deadline_lane": False,
            "lane_restarts": {}, "lane_restart_at": {},
        }
    return {
        "running": True,
        "event_lane": bool(
            daemon._event_thread is not None and daemon._event_thread.is_alive()
        ),
        "deadline_lane": bool(
            daemon._deadline_thread is not None
            and daemon._deadline_thread.is_alive()
        ),
        # Liveness says "alive right now"; the restart count says "and it has
        # died N times getting there". Both are needed to judge lane health.
        "lane_restarts": dict(daemon._lane_restarts),
        "lane_restart_at": dict(daemon._lane_restart_at),
    }


# ---------- CLI smoke test ----------

if __name__ == "__main__":
    """Run all sweepers once and exit."""
    d = get_daemon()
    d.run_once()
    print("[oversight_daemon] One-shot sweep complete.")
