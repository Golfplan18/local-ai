"""Filesystem-event bridge for Ora runtime hygiene.

The bridge consumes operating-system file notifications. It does not poll for
state and it never schedules a fallback sweep. Existing watcher modules remain
the authoritative diff/evaluation implementations during G1.10 migration, but
they run only after a relevant write event or an explicit one-shot command.
"""
from __future__ import annotations

import os
import json
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp

try:
    import export as _export
except ImportError:  # pragma: no cover
    from orchestrator import export as _export


def _resources_root() -> Path:
    """The inbound folder resources_watcher actually converts from.

    It is the external ``~/Documents/Ora Resources`` (configurable), NOT
    ``ORA_HOME/Resources`` — that path has never existed, so from the G1.10
    cutover until 2026-08-16 no dropped document ever raised an event.
    """
    return Path(_export.current_resources_dir())


def _roots() -> list[str]:
    candidates = [Path(_rp.VAULT_STR), _resources_root()]
    return [str(path.resolve()) for path in candidates if path.is_dir()]


def _under(path: str, root: str | Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


_IGNORED_PARTS = {".git", ".obsidian", ".trash", "__pycache__"}

# Vault subtrees that are machine-synced mirrors rather than user writes.
#
# `MSI News` is the rsync'd cloud-pipeline mirror. A mirror refresh is not a
# vault edit, and treating it as one is self-sustaining: the sync writes ~17k
# files, the notification fires, the handler runs vault_git_sync +
# vault_cloud_sync, and the sync writes them again. Until 2026-08-16 the loop
# was hidden because a batch that size overflowed the OS argument limit and
# killed the lane before it could recur — the crash was acting as an
# accidental circuit breaker. Fixing the crash exposed the loop, so the
# exclusion has to be explicit.
#
# `daily_note.SKIP_DIRS` already excludes this directory for the same reason
# ("machine-synced articles, not the user's work"); this is the event-side
# half of that rule, which was never written.
_MIRROR_DIRS = {"MSI News"}
_AUTONOMOUS_HANDLER_SENTINEL = "autonomous-handlers.disabled"


def autonomous_hygiene_enabled() -> bool:
    """Return whether exact-write News/Engram judgment may run.

    The data-root sentinel is an operational circuit breaker, not a scheduler
    control and not a fallback queue. It suppresses only the two autonomous
    mutation handlers while leaving all other OS-event consumers active.
    """
    configured = os.environ.get("ORA_AUTONOMOUS_HYGIENE", "on").strip().lower()
    if configured in {"0", "false", "off", "disabled"}:
        return False
    sentinel = (Path(_rp.DATA_DIR_STR) / "runtime-hygiene" /
                _AUTONOMOUS_HANDLER_SENTINEL)
    return not sentinel.exists()


def _actionable(path: str) -> bool:
    """Exclude repository/editor internals and transient files.

    In particular, the event-triggered Git step changes ``.git``. Treating
    those writes as new vault content would recursively dispatch itself.
    """
    candidate = Path(path)
    if any(part in _IGNORED_PARTS for part in candidate.parts):
        return False
    if _in_mirror(candidate):
        return False
    return not candidate.name.startswith((".", "~$"))


def _in_mirror(candidate: Path) -> bool:
    """True when the path is inside a machine-synced vault mirror.

    Anchored at the vault root, so a user-authored note that merely happens to
    have a folder of the same name deeper in the tree is still a real write.
    """
    try:
        parts = candidate.resolve().relative_to(Path(_rp.VAULT_STR).resolve()).parts
    except (ValueError, OSError):
        return False
    return bool(parts) and parts[0] in _MIRROR_DIRS


def _artifact_kind(path: str) -> str | None:
    """Classify one exact top-level Markdown artifact.

    The accepted News/Engram contract is deliberately limited to direct
    collection children because the existing resolver addresses artifacts by
    collection-local slug. Nested content is not silently granted authority.
    """
    exact = Path(path).resolve()
    try:
        parts = exact.relative_to(Path(_rp.VAULT_STR).resolve()).parts
        if len(parts) == 2 and parts[0] == "Resources":
            return "resource"
        if len(parts) == 2 and parts[0] == "Engrams":
            return "engram"
    except ValueError:
        pass
    try:
        parts = exact.relative_to(_resources_root().resolve()).parts
        return "inbound_resource" if len(parts) == 1 else None
    except ValueError:
        return None


def dispatch_paths(paths: set[str]) -> dict:
    """Dispatch one coalesced set of exact changed paths."""
    from oversight_events import emit

    paths = {str(Path(path).resolve()) for path in paths if _actionable(path)}

    existing_markdown = {
        str(Path(path).resolve()) for path in paths
        if str(path).endswith(".md") and Path(path).is_file()
    }
    vault_changes = {path for path in paths if _under(path, _rp.VAULT_STR)}
    resource_changes = {
        path for path in paths if _under(path, _resources_root())
    }
    summary = {
        "paths": sorted(paths), "supersession_events": [],
        "self_mutations_suppressed": [],
        "autonomous_handlers_suppressed": [],
        "ped_events": 0, "corpus_events": 0,
        "workflow_checked": False, "revisit_checked": False,
        "resources_checked": False, "operational_hook": None, "errors": [],
    }

    for path in sorted(existing_markdown):
        if _artifact_kind(path) not in {"resource", "engram"}:
            continue
        if not autonomous_hygiene_enabled():
            summary["autonomous_handlers_suppressed"].append({
                "path": path, "reason": "operational circuit breaker",
            })
            continue
        try:
            from orchestrator.runtime_hygiene import EventLedger, artifact_identity
            from orchestrator.tools.supersession_sweep import process_artifact_write
            causing_event = EventLedger().completed_mutation_causing(
                artifact_identity(path))
            if causing_event:
                summary["self_mutations_suppressed"].append({
                    "path": path, "causing_event_id": causing_event,
                })
                continue
            result = process_artifact_write(path)
            summary["supersession_events"].append(result)
            if result.get("status") != "completed":
                summary["errors"].append(
                    f"supersession {path}: event {result.get('event_id', '?')} "
                    f"ended {result.get('status', 'unknown')}: "
                    f"{result.get('error', 'no error detail')}"
                )
        except Exception as exc:
            summary["errors"].append(f"supersession {path}: {exc}")

    if vault_changes:
        try:
            import ped_watcher
            events = ped_watcher.sweep()
            for event in events:
                emit(event)
            summary["ped_events"] = len(events)
        except Exception as exc:
            summary["errors"].append(f"ped watcher: {exc}")
        try:
            import corpus_watcher
            events = corpus_watcher.sweep()
            for event in events:
                emit(event)
            summary["corpus_events"] = len(events)
        except Exception as exc:
            summary["errors"].append(f"corpus watcher: {exc}")
        try:
            import workflow_spec_sweeper
            workflow_spec_sweeper.sweep(emit_event=emit)
            summary["workflow_checked"] = True
        except Exception as exc:
            summary["errors"].append(f"workflow watcher: {exc}")
        try:
            import revisit_sweeper
            revisit_sweeper.sweep(emit_event=emit)
            revisit_sweeper.register_age_review_deadlines()
            summary["revisit_checked"] = True
        except Exception as exc:
            summary["errors"].append(f"revisit watcher: {exc}")

    if resource_changes:
        try:
            import resources_watcher
            resources_watcher.sweep()
            summary["resources_checked"] = True
        except Exception as exc:
            summary["errors"].append(f"resources watcher: {exc}")
    if vault_changes:
        hook = (Path(_rp.ORA_HOME) / "operations" / "g1-10-current" /
                "macos" / "vault-event-pipeline.py")
        if hook.is_file():
            # A coalesced batch can hold thousands of paths. One --path pair
            # per file overflows the OS argument-length limit and, because
            # this was the only block in this function without a guard, took
            # the whole listener down with it (2,257 recorded crashes before
            # 2026-08-16). The paths go through a temp file instead, and the
            # block degrades like its six siblings.
            try:
                exact_paths = sorted(
                    str(Path(path).resolve()) for path in vault_changes
                )
                with tempfile.NamedTemporaryFile(
                    "w", encoding="utf-8", suffix=".paths", delete=False
                ) as handle:
                    # JSON array, not newline-delimited: a newline is a legal
                    # macOS filename character, and splitting on one would
                    # manufacture two bogus paths and bind them into the
                    # hook's exactly-once event contract.
                    json.dump(exact_paths, handle)
                    paths_file = handle.name
                try:
                    result = subprocess.run(
                        ["/opt/homebrew/bin/python3", str(hook),
                         "--paths-file", paths_file],
                        capture_output=True, text=True,
                    )
                finally:
                    try:
                        os.unlink(paths_file)
                    except OSError:
                        pass
                event_id = None
                try:
                    event_id = json.loads(
                        result.stdout.splitlines()[-1]
                    ).get("event_id")
                except (IndexError, json.JSONDecodeError, AttributeError):
                    pass
                summary["operational_hook"] = {
                    "event_id": event_id, "exit_status": result.returncode,
                }
                if result.returncode:
                    summary["errors"].append(
                        f"vault operational hook failed ({result.returncode}): "
                        f"{result.stderr[-1000:]}"
                    )
            except Exception as exc:
                summary["errors"].append(f"vault operational hook: {exc}")
    return summary


def run(stop_event: threading.Event) -> None:
    """Block on OS notifications and dispatch coalesced exact paths."""
    from watchfiles import watch
    from orchestrator.runtime_hygiene import restore_incomplete_events

    restored = restore_incomplete_events()
    if restored:
        print(f"[runtime_event_dispatcher] restored interrupted events: {restored}")
    roots = _roots()
    if not roots:
        raise RuntimeError("runtime event dispatcher has no existing watch root")
    for changes in watch(*roots, stop_event=stop_event, debounce=500, step=100):
        paths = {path for _change, path in changes if _actionable(path)}
        if not paths:
            continue
        summary = dispatch_paths(paths)
        if summary["errors"]:
            print(f"[runtime_event_dispatcher] errors: {summary['errors']}")


def heartbeat() -> dict:
    return {
        "watcher": "runtime_event_dispatcher",
        "beat_at": datetime.now(timezone.utc).isoformat(),
        "roots": _roots(),
        "mechanism": "os-file-events",
    }
