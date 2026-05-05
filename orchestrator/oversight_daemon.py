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

# Vault path — the canonical location for PEDs and other oversight artifacts.
VAULT_PATH = os.path.expanduser(os.environ.get("ORA_VAULT_PATH", "~/Documents/vault/"))


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

    Each watcher runs on its own cadence; all share a single thread that
    wakes once per second and dispatches due watchers.
    """

    def __init__(self):
        self._running = False
        self._thread = None
        self._last_run: dict[str, float] = {}

    def start(self):
        """Start the daemon. Idempotent."""
        if self._running:
            return
        # Wire the router as an event handler before starting the loop
        try:
            from oversight_router import install as install_router
            install_router()
        except Exception as e:
            print(f"[oversight_daemon] router install failed: {e}")

        # Auto-register any PEDs the user has placed in the vault that
        # don't yet have a per-project pointer. Idempotent — re-running
        # only registers genuinely new PEDs.
        try:
            registered = scan_vault_and_register_peds()
            if registered:
                print(f"[oversight_daemon] Auto-registered {len(registered)} project(s) from vault scan")
                for nexus, path in registered:
                    print(f"  - {nexus}: {path}")
        except Exception as e:
            print(f"[oversight_daemon] vault scan failed: {e}")

        # Auto-register any workflow specs (Shape 4 corpus-mediated workflows)
        # that aren't yet pointed at by ~/ora/data/oversight/<workflow_id>/workflow-pointer.json
        try:
            registered_workflows = scan_vault_and_register_workflows()
            if registered_workflows:
                print(f"[oversight_daemon] Auto-registered {len(registered_workflows)} workflow(s) from vault scan")
                for workflow_id, path in registered_workflows:
                    print(f"  - {workflow_id}: {path}")
        except Exception as e:
            print(f"[oversight_daemon] workflow scan failed: {e}")

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[oversight_daemon] Started")

    def stop(self):
        """Stop the daemon."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        print("[oversight_daemon] Stopped")

    def run_once(self):
        """Run all sweepers once, regardless of interval. For tests / CLI."""
        from oversight_events import emit
        self._run_ped_watcher(emit)
        self._run_corpus_watcher(emit)
        self._run_workflow_spec_sweeper(emit)
        self._run_revisit_sweeper(emit)

    def _loop(self):
        """Main loop — checks each watcher's due time once per second."""
        from oversight_events import emit

        while self._running:
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
                print(f"[oversight_daemon] loop error: {e}")

            # Sleep in 1-second increments so we can stop quickly
            for _ in range(5):
                if not self._running:
                    break
                time.sleep(1)

    def _maybe_run(self, name: str, interval: int, now: float, fn):
        last = self._last_run.get(name, 0)
        if now - last >= interval:
            self._last_run[name] = now
            fn()

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
