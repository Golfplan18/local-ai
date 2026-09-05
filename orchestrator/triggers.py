"""User-authored Triggers over the exact-event / exact-deadline substrate.

A Trigger is a separately authorized activation object. It never modifies the
thing it activates and it never executes work itself: every firing binds one
exact, already-registered unit of work and runs it through that unit's own
entry point.

This module owns no engine. It compiles to the two primitives
``Framework — Event-Driven Hygiene Patterns`` allows and nothing else:

* a **calendar** Trigger arms one persisted :class:`~runtime_hygiene.DeadlineQueue`
  record for its next occurrence and arms the successor from the persisted
  contract when that one fires;
* every other cause is an **exact event** — an operating-system file
  notification, an authenticated firing completion, or an explicit human
  request.

There is no interval scanner, no sweep, no cron/launchd unit, and no clock
fallback. A local application acts only while it is running; that boundary is
stated in :data:`INTERMITTENCY_NOTICE` rather than papered over.

Every firing is an :class:`~runtime_hygiene.EventLedger` record, so idempotency,
append-only evidence, and restart recovery come from the substrate rather than
from a second store. The only durable object this module adds is the Trigger.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import multiprocessing
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import date, datetime, time as clock_time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover - package import context
    from orchestrator import runtime_paths as _rp

try:
    from runtime_hygiene import (
        DeadlineQueue, EventLedger, artifact_identity, deadline_queue,
        event_identity, instant_timestamp, normalized_instant,
    )
except ImportError:  # pragma: no cover - package import context
    from orchestrator.runtime_hygiene import (
        DeadlineQueue, EventLedger, artifact_identity, deadline_queue,
        event_identity, instant_timestamp, normalized_instant,
    )


SCHEMA_VERSION = 1

CAUSES = ("manual", "file_change", "calendar", "trigger_completion")
ACTION_KINDS = ("project_tool", "framework", "email_send")
STATUSES = ("draft", "active", "paused", "retired")
CADENCES = ("daily", "weekly")
MISSED_POLICIES = ("run_once", "skip")

#: Ledger event type for every Trigger firing, whatever its cause.
FIRING_EVENT_TYPE = "trigger_firing"
#: Deadline-queue event type for a calendar Trigger's armed occurrence.
DEADLINE_EVENT_TYPE = "trigger_calendar"

#: The exact availability boundary a local application can honestly promise.
#: G1.19 made the user retype four fixed sentences to say this; it is a
#: property of the runtime, not of any one Trigger, so it is rendered once.
INTERMITTENCY_NOTICE = (
    "Acts only while Ora is running. There is no cron, launchd, or sweep "
    "fallback, and no promise of 24/7 coverage while the machine is off."
)

#: A calendar Trigger may not be activated without a written reason that time
#: itself is the cause. This is the Runtime Principle enforced mechanically.
MIN_JUSTIFICATION_CHARS = 40

#: How long a firing may run before the executor stops waiting on it. A
#: framework run is minutes; a project tool has its own subprocess timeout.
#: Provisional — not calibrated against real long jobs.
FIRING_TIMEOUT_SEC = int(os.environ.get("ORA_TRIGGER_FIRING_TIMEOUT_SEC") or 3600)

#: Characters of action output retained on a firing receipt. The full output
#: belongs to the tool or the framework, not to this evidence record.
RECEIPT_EXCERPT_CHARS = 600
TERMINATION_GRACE_SEC = 5.0

#: macOS's existing, least-privileged idle-sleep assertion tool.  It is
#: launched only inside the already-existing action process and is bound to
#: that process's pid; it is not a daemon, scheduler, or second runner.
_MACOS_CAFFEINATE = "/usr/bin/caffeinate"

_PROCESS_LOCK = threading.RLock()
#: trigger_id -> event_id of the firing currently executing in this process.
_RUNNING: dict[str, str] = {}


class TriggerError(RuntimeError):
    """Base class for a rejected Trigger operation."""


class TriggerInputRequired(TriggerError):
    """The request lacks a valid exact input."""


class TriggerConflict(TriggerError):
    """The request conflicts with durable Trigger state."""


class TriggerStaleEvent(TriggerConflict):
    """An event names a Trigger admission that is no longer current."""


class TriggerTerminationUnacknowledged(TriggerError):
    """The action tree could not be proved stopped after termination."""

    def __init__(self, message: str, *, process_identity: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.process_identity = (
            copy.deepcopy(dict(process_identity))
            if isinstance(process_identity, Mapping)
            else None
        )


def _termination_exception(
    exc: BaseException,
) -> TriggerTerminationUnacknowledged | None:
    """Find a termination failure even when receipt code wrapped it."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        if isinstance(current, TriggerTerminationUnacknowledged):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None


# ── small helpers ────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _admission_identity(record: Mapping[str, Any]) -> str:
    """Bind one event to the exact revocable Trigger admission it observed."""
    spec = record.get("spec")
    return _digest({
        "spec_digest": _digest(spec) if isinstance(spec, Mapping) else None,
        "status": record.get("status"),
        "activated_at": record.get("activated_at"),
        "approved_spec_digest": record.get("approved_spec_digest"),
        "approved_action_binding": record.get("approved_action_binding"),
    })


def _completion_proof(
    source_completion: Mapping[str, Any] | None,
) -> dict[str, str] | None:
    """Derive one complete, authenticated source-completion proof."""
    if not isinstance(source_completion, Mapping):
        return None
    source_subject = source_completion.get("subject")
    if (
        source_completion.get("status") != "completed"
        or not isinstance(source_subject, Mapping)
    ):
        return None
    proof = {
        "event_id": source_completion.get("event_id"),
        "event_type": source_completion.get("event_type"),
        "trigger_id": source_subject.get("trigger_id"),
        "spec_digest": source_subject.get("spec_digest"),
        "admission_identity": source_subject.get("admission_identity"),
        "completed_at": source_completion.get("completed_at"),
    }
    if (
        proof["event_type"] != FIRING_EVENT_TYPE
        or any(
            not isinstance(value, str) or not value.strip()
            for value in proof.values()
        )
    ):
        return None
    return proof


def _completion_proof_matches_delivery(
    delivery: Mapping[str, Any],
    proof: Mapping[str, Any] | None,
) -> bool:
    """Authenticate every source identity before exposing or running a delivery."""
    if not isinstance(delivery, Mapping) or not isinstance(proof, Mapping):
        return False
    expected = {
        "event_id": delivery.get("source_event_id"),
        "event_type": delivery.get("source_event_type"),
        "trigger_id": delivery.get("source_trigger_id"),
        "spec_digest": delivery.get("source_spec_digest"),
        "admission_identity": delivery.get("source_admission_identity"),
    }
    if (
        expected["event_type"] != FIRING_EVENT_TYPE
        or any(
            not isinstance(value, str) or not value.strip()
            for value in expected.values()
        )
        or not isinstance(proof.get("completed_at"), str)
        or not str(proof.get("completed_at")).strip()
    ):
        return False
    return all(proof.get(key) == value for key, value in expected.items())


def _active_run_sleep_available() -> bool:
    """Whether this host can make the scoped macOS idle-sleep assertion."""
    return (
        sys.platform == "darwin"
        and os.path.isfile(_MACOS_CAFFEINATE)
        and os.access(_MACOS_CAFFEINATE, os.X_OK)
    )


def _local_routine_descriptor(action_kind: str | None = None) -> dict:
    """Describe only the execution facts the current Trigger runner proves."""
    sleep_available = _active_run_sleep_available()
    authority = {"binding": "exact_action_binding"}
    if action_kind is not None:
        authority["action_kind"] = action_kind
    return {
        "execution_target": "local",
        "remote_execution_supported": False,
        "authority": authority,
        "debug": {
            "firing_event_type": FIRING_EVENT_TYPE,
            "receipt_available": True,
            "error_available": True,
        },
        "active_run_sleep_protection": {
            "available": sleep_available,
            "platform": "macos" if sys.platform == "darwin" else sys.platform,
            "scope": "active_action_only" if sleep_available else None,
            "prevents": "idle_system_sleep" if sleep_available else None,
            "release_boundary": (
                "action_scope_exit" if sleep_available else None
            ),
        },
        "wake_from_sleep_supported": False,
    }


def _safe_id(value: Any, label: str) -> str:
    exact = str(value or "").strip().lower()
    if not exact or len(exact) > 128:
        raise TriggerInputRequired(f"{label} must be 1-128 characters")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_.:")
    if not set(exact) <= allowed or not exact[0].isalnum():
        raise TriggerInputRequired(
            f"{label} must start alphanumeric and use only a-z 0-9 . _ - :"
        )
    return exact


def _safe_text(value: Any, label: str, *, limit: int = 4000, minimum: int = 1) -> str:
    exact = " ".join(str(value or "").split())
    if len(exact) < minimum or len(exact) > limit:
        raise TriggerInputRequired(
            f"{label} must contain {minimum}-{limit} characters"
        )
    return exact


def _exact_text(value: Any, label: str, *, limit: int = 4000) -> str:
    """Validate request text without rewriting its whitespace or line bytes."""
    exact = str(value or "")
    if not exact.strip() or len(exact) > limit:
        raise TriggerInputRequired(
            f"{label} must contain 1-{limit} characters"
        )
    return exact


def _excerpt(value: Any) -> str:
    text = value if isinstance(value, str) else _canonical_json(value)
    text = text.strip()
    if len(text) <= RECEIPT_EXCERPT_CHARS:
        return text
    return text[:RECEIPT_EXCERPT_CHARS] + "…"


# ── durable store ────────────────────────────────────────────────────────
#
# One consolidated file, resolved at CALL time from the same data root the
# event ledger and the deadline queue use. Deliberately NOT rebased through
# ``sandboxed_file``: a Trigger's firings live in the ledger and its calendar
# occurrences live in the queue, and neither of those is rebased either.
# Sending the specification to a quarantine directory while its own evidence
# stayed live would split one object across two roots — worse than either
# consistent choice. Redirecting ``_rp.DATA_DIR_STR`` moves all three
# together, which is what the tests do.


def _root() -> Path:
    return Path(_rp.DATA_DIR_STR) / "triggers"


def _store_path() -> Path:
    return _root() / "triggers.json"


def _lock_path() -> Path:
    return _root() / ".triggers.lock"


@contextlib.contextmanager
def _exclusive():
    # locked_file adds ``.lock`` itself. Removing the suffix preserves the
    # established ``.triggers.lock`` sidecar rather than creating a second lock.
    with _rp.locked_file(_lock_path().with_suffix("")):
        yield


def _load() -> dict:
    try:
        value = json.loads(_store_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "schema_version": SCHEMA_VERSION,
            "triggers": {},
            "completion_deliveries": {},
        }
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise TriggerConflict("unsupported trigger store schema")
    value.setdefault("completion_deliveries", {})
    if not isinstance(value["completion_deliveries"], dict):
        raise TriggerConflict("unsupported completion-delivery state")
    return value


def _save(state: dict) -> None:
    _rp.atomic_write_text(
        _store_path(),
        json.dumps(state, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
    )


# ── calendar arithmetic ──────────────────────────────────────────────────


def _local_occurrence(day: date, local_time: str, zone: ZoneInfo) -> datetime:
    """One local wall time on one local day, as a UTC instant.

    A spring-forward wall time does not exist. Advance to the first real local
    instant so the calendar intent is preserved without inheriting a stale
    fixed offset — the framework's requirement that calendar work derive each
    boundary in its named zone.
    """
    wall = datetime.combine(day, clock_time.fromisoformat(local_time))
    candidate = wall.replace(tzinfo=zone, fold=0)
    for _ in range(181):
        round_trip = candidate.astimezone(timezone.utc).astimezone(zone)
        if round_trip.replace(tzinfo=None) == candidate.replace(tzinfo=None):
            return candidate.astimezone(timezone.utc)
        candidate += timedelta(minutes=1)
    raise TriggerConflict("could not resolve a real local calendar occurrence")


def next_occurrence(schedule: Mapping[str, Any], after: datetime) -> datetime:
    """Return the one exact next occurrence strictly after ``after``.

    Resolved arithmetically, never by scanning forward on a clock.
    """
    zone = ZoneInfo(str(schedule["timezone"]))
    start = date.fromisoformat(str(schedule["start_date"]))
    day = max(start, after.astimezone(zone).date())
    for _ in range(8):
        selected = (schedule["cadence"] == "daily"
                    or day.weekday() in schedule["weekdays"])
        if selected:
            instant = _local_occurrence(day, str(schedule["local_time"]), zone)
            if instant > after:
                return instant
        day += timedelta(days=1)
    raise TriggerConflict("schedule has no resolvable future occurrence")


# ── validation ───────────────────────────────────────────────────────────


def _watch_roots() -> list[str]:
    """The roots the OS-notification lane actually watches.

    Derived from the dispatcher's own accessor, never a second literal — a
    file selector pointed at a path nothing watches would never fire, and the
    silence would be indistinguishable from "no work arrived".
    """
    try:
        from runtime_event_dispatcher import _roots
    except ImportError:  # pragma: no cover - package import context
        from orchestrator.runtime_event_dispatcher import _roots
    return _roots()


def _dispatcher_exclusions(path: Path) -> str | None:
    """Return why the dispatcher would drop this path, or None."""
    try:
        from runtime_event_dispatcher import _actionable
    except ImportError:  # pragma: no cover - package import context
        from orchestrator.runtime_event_dispatcher import _actionable
    if not _actionable(str(path)):
        return (
            "the file-event lane deliberately ignores this path (repository or "
            "editor internals, a dotfile, or a machine-synced vault mirror)"
        )
    return None


def _validate_selectors(raw: Any) -> list[str]:
    if not isinstance(raw, (list, tuple)) or not raw:
        raise TriggerInputRequired(
            "a file-change Trigger needs at least one path selector"
        )
    roots = _watch_roots()
    selectors: set[str] = set()
    for item in raw:
        text = str(item or "").strip()
        if not text or "\x00" in text:
            raise TriggerInputRequired("file-change selector is invalid")
        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            raise TriggerInputRequired(
                f"file-change selectors must be absolute paths: {text}"
            )
        exact = str(candidate.resolve())
        if not any(_within(exact, root) for root in roots):
            raise TriggerInputRequired(
                f"{exact} is not inside a watched root, so a file event there "
                f"would never reach Ora. Watched roots: "
                f"{', '.join(roots) or '(none — the event lane has no root)'}"
            )
        reason = _dispatcher_exclusions(Path(exact))
        if reason:
            raise TriggerInputRequired(f"{exact} can never fire: {reason}")
        selectors.add(exact)
    return sorted(selectors)


def _within(path: str, root: str) -> bool:
    return _rp.within_base(path, root) or _rp.norm_key(path) == _rp.norm_key(root)


def _validate_calendar(raw: Any) -> dict:
    allowed = {"timezone", "local_time", "cadence", "weekdays", "start_date",
               "missed_policy", "grace_seconds"}
    if not isinstance(raw, Mapping) or set(raw) - allowed:
        raise TriggerInputRequired("calendar schedule fields are invalid")
    zone_name = str(raw.get("timezone") or "").strip()
    try:
        ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise TriggerInputRequired(
            "schedule timezone must be a named IANA zone (e.g. America/New_York); "
            "a fixed offset cannot survive a DST change"
        ) from exc
    local_time = str(raw.get("local_time") or "")
    try:
        clock_time.fromisoformat(local_time)
    except ValueError as exc:
        raise TriggerInputRequired("local_time must be HH:MM or HH:MM:SS") from exc
    cadence = str(raw.get("cadence") or "")
    if cadence not in CADENCES:
        raise TriggerInputRequired("cadence must be daily or weekly")
    weekdays = sorted({item for item in (raw.get("weekdays") or [])})
    if cadence == "weekly":
        if not weekdays or any(type(day) is not int or not 0 <= day <= 6
                               for day in weekdays):
            raise TriggerInputRequired(
                "a weekly schedule needs weekday integers 0 (Monday) to 6 (Sunday)"
            )
    elif weekdays:
        raise TriggerInputRequired("a daily schedule may not declare weekdays")
    start_date = str(raw.get("start_date") or date.today().isoformat())
    try:
        date.fromisoformat(start_date)
    except ValueError as exc:
        raise TriggerInputRequired("start_date must be YYYY-MM-DD") from exc
    missed = str(raw.get("missed_policy") or "run_once")
    if missed not in MISSED_POLICIES:
        raise TriggerInputRequired("missed_policy must be run_once or skip")
    grace = raw.get("grace_seconds", 300)
    if type(grace) is not int or not 0 <= grace <= 86400:
        raise TriggerInputRequired("grace_seconds must be an integer from 0 to 86400")
    return {
        "timezone": zone_name, "local_time": local_time, "cadence": cadence,
        "weekdays": weekdays, "start_date": start_date,
        "missed_policy": missed, "grace_seconds": grace,
    }


def _validate_condition(cause: str, raw: Any) -> dict:
    condition = dict(raw or {}) if isinstance(raw, Mapping) else None
    if condition is None:
        raise TriggerInputRequired("condition must be an object")
    if cause == "manual":
        if condition:
            raise TriggerInputRequired("a manual Trigger takes no condition")
        return {}
    if cause == "file_change":
        if set(condition) != {"path_selectors"}:
            raise TriggerInputRequired(
                "a file-change condition holds exactly path_selectors"
            )
        return {"path_selectors": _validate_selectors(condition["path_selectors"])}
    if cause == "calendar":
        if set(condition) != {"schedule"}:
            raise TriggerInputRequired("a calendar condition holds exactly a schedule")
        return {"schedule": _validate_calendar(condition["schedule"])}
    if cause == "trigger_completion":
        if set(condition) != {"source_trigger_id"}:
            raise TriggerInputRequired(
                "a completion condition holds exactly source_trigger_id"
            )
        return {
            "source_trigger_id": _safe_id(
                condition["source_trigger_id"], "source_trigger_id"),
        }
    raise TriggerInputRequired(f"unknown cause {cause!r}")


def _validate_action(raw: Any) -> dict:
    if not isinstance(raw, Mapping):
        raise TriggerInputRequired("action must be an object")
    kind = str(raw.get("kind") or "")
    if kind == "project_tool":
        if set(raw) - {"kind", "nexus", "tool", "args", "stdin"}:
            raise TriggerInputRequired("project_tool action fields are invalid")
        args = raw.get("args") or []
        if not isinstance(args, (list, tuple)):
            raise TriggerInputRequired("project_tool args must be a list")
        action = {
            "kind": kind,
            "nexus": _safe_id(raw.get("nexus"), "nexus"),
            "tool": _safe_text(raw.get("tool"), "tool name", limit=128),
            "args": [str(item) for item in args],
        }
        if raw.get("stdin") is not None:
            action["stdin"] = copy.deepcopy(raw["stdin"])
        return action
    if kind == "framework":
        if set(raw) - {"kind", "framework", "input", "project_nexus"}:
            raise TriggerInputRequired("framework action fields are invalid")
        action = {
            "kind": kind,
            "framework": _safe_text(raw.get("framework"), "framework", limit=200),
            "input": _exact_text(raw.get("input"), "framework input", limit=4000),
        }
        if raw.get("project_nexus"):
            action["project_nexus"] = _safe_id(raw["project_nexus"], "project_nexus")
        return action
    if kind == "email_send":
        try:
            try:
                from email_channel import normalize_action
            except ImportError:  # pragma: no cover - package import context
                from orchestrator.email_channel import normalize_action
            return normalize_action(raw)
        except Exception as exc:
            raise TriggerInputRequired(str(exc)) from exc
    raise TriggerInputRequired(
        "action kind must be project_tool, framework, or email_send. A literal "
        "command is not accepted: declare the script once as a project tool in "
        "an ora-project.json manifest, then name it here."
    )


def normalize_spec(raw: Mapping[str, Any]) -> dict:
    """Validate one Trigger specification into its canonical form."""
    if not isinstance(raw, Mapping):
        raise TriggerInputRequired("Trigger specification must be an object")
    known = {"trigger_id", "name", "cause", "condition", "action",
             "runtime_justification", "principal_id"}
    unknown = set(raw) - known
    if unknown:
        raise TriggerInputRequired(
            f"unknown Trigger fields: {', '.join(sorted(unknown))}"
        )
    cause = str(raw.get("cause") or "")
    if cause not in CAUSES:
        raise TriggerInputRequired(f"cause must be one of {', '.join(CAUSES)}")
    justification = str(raw.get("runtime_justification") or "").strip()
    if cause == "calendar":
        if len(" ".join(justification.split())) < MIN_JUSTIFICATION_CHARS:
            raise TriggerInputRequired(
                "a calendar Trigger requires a written runtime-impossibility "
                f"justification of at least {MIN_JUSTIFICATION_CHARS} characters: "
                "say why no runtime event can represent this cause. If an event "
                "can, use that cause instead."
            )
        justification = _safe_text(justification, "runtime_justification")
    elif justification:
        raise TriggerInputRequired(
            "only a calendar Trigger carries a runtime-impossibility justification"
        )
    action = _validate_action(raw.get("action"))
    if action["kind"] == "email_send" and cause != "manual":
        raise TriggerInputRequired(
            "email_send is manual-only in this slice; use cause=manual"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "trigger_id": _safe_id(raw.get("trigger_id"), "trigger_id"),
        "name": _safe_text(raw.get("name"), "name", limit=200),
        "cause": cause,
        "condition": _validate_condition(cause, raw.get("condition")),
        "action": action,
        "runtime_justification": justification or None,
        "principal_id": _safe_id(
            raw.get("principal_id") or "principal:user", "principal_id"),
    }


# ── action binding ───────────────────────────────────────────────────────


def _resolve_framework_action_binding(
    action: Mapping[str, Any],
) -> tuple[dict, Any]:
    try:
        from framework_preflight import prepare_framework_execution
        from framework_parser import FRAMEWORKS_DIR
    except ImportError:  # pragma: no cover - package import context
        from orchestrator.framework_preflight import prepare_framework_execution
        from orchestrator.framework_parser import FRAMEWORKS_DIR
    try:
        prepared = prepare_framework_execution(
            action["framework"],
            action["input"],
            project_nexus=action.get("project_nexus"),
        )
    except Exception as exc:
        raise TriggerConflict(f"Framework preflight refusal: {exc}") from exc
    path = Path(FRAMEWORKS_DIR) / prepared.canonical_filename
    if not path.is_file():
        raise TriggerConflict(f"framework file is missing: {path}")
    identity = artifact_identity(path)
    contract_digest = "sha256:" + hashlib.sha256(
        prepared.contract_text.encode("utf-8")
    ).hexdigest()
    return ({
        "kind": "framework",
        "framework": prepared.canonical_filename,
        "path": identity["path"],
        # Approval binds the exact composed contract, not merely its base file.
        "command_digest": contract_digest,
        "project_nexus": prepared.project_nexus,
        "project_profile": prepared.project_profile,
    }, prepared)


def _public_action_binding(binding: Mapping[str, Any]) -> dict:
    """Return the stable, JSON-shaped part of an execution binding."""
    try:
        import project_registry as _pr
    except ImportError:  # pragma: no cover - package import context
        from orchestrator import project_registry as _pr
    return _pr.public_execution_binding(binding)


def _activation_approval_digest(spec: Mapping[str, Any],
                                binding: Mapping[str, Any]) -> str:
    """Bind one review token to both the Trigger and the program it names."""

    return _digest({
        "spec": spec,
        "action_binding": _public_action_binding(binding),
    })


def resolve_action_binding(action: Mapping[str, Any]) -> dict:
    """Authenticate that the named unit of work exists, and bind its identity.

    The binding is what activation approves. Re-resolving it before every
    firing is what stops a manifest edited after approval from silently
    changing what runs.
    """
    kind = action["kind"]
    if kind == "project_tool":
        try:
            import project_registry as _pr
        except ImportError:  # pragma: no cover - package import context
            from orchestrator import project_registry as _pr
        project = _pr.get_project(action["nexus"])
        if project is None:
            raise TriggerConflict(
                f"no project registered with nexus {action['nexus']!r}"
            )
        tool = project.tools.get(action["tool"])
        if tool is None:
            raise TriggerConflict(
                f"project {action['nexus']!r} has no tool {action['tool']!r}; "
                f"available: {sorted(project.tools.keys())}"
            )
        if (tool.interface == _pr.TOOL_INTERFACE_STDIN_STDOUT
                and action.get("args")):
            raise TriggerConflict(
                "a stdin-stdout-json project tool cannot also receive argv arguments"
            )
        if (tool.interface == _pr.TOOL_INTERFACE_ARGV_STDOUT
                and "stdin" in action):
            raise TriggerConflict(
                "an argv-stdout-json project tool cannot also receive stdin input"
            )
        stdin_json = action["stdin"] if "stdin" in action else {}
        try:
            binding = _pr.project_execution_binding(
                project,
                tool,
                kind="tool",
                args_digest=_pr.project_args_digest(
                    tool,
                    args=list(action.get("args") or []),
                    stdin_json=stdin_json,
                ),
                pointer_dir=_pr.POINTER_DIR,
            )
        except Exception as exc:
            raise TriggerConflict(
                f"project tool binding could not be authenticated: {exc}"
            ) from exc
        return _public_action_binding(binding)
    if kind == "framework":
        binding, _prepared = _resolve_framework_action_binding(action)
        return binding
    if kind == "email_send":
        try:
            try:
                from email_channel import prepare_message
            except ImportError:  # pragma: no cover - package import context
                from orchestrator.email_channel import prepare_message
            message = prepare_message(action)
        except Exception as exc:
            raise TriggerConflict(f"email message is not usable: {exc}") from exc
        return {
            "kind": kind,
            "provider": "fastmail",
            "message_digest": message.digest,
            "mime_digest": "sha256:" + hashlib.sha256(message.mime).hexdigest(),
            "persona_id": message.persona_id,
            "persona_name": message.persona_name,
        }
    raise TriggerInputRequired(f"unknown action kind {kind!r}")


# ── state views ──────────────────────────────────────────────────────────


def _record_view(record: Mapping[str, Any], *, firings: list | None = None,
                 completion_deliveries: Iterable[Mapping[str, Any]] = ()) -> dict:
    spec = record["spec"]
    view = {
        "spec": copy.deepcopy(spec),
        "spec_digest": _digest(spec),
        "status": record.get("status", "draft"),
        "created_at": record.get("created_at"),
        "activated_at": record.get("activated_at"),
        "approved_spec_digest": record.get("approved_spec_digest"),
        "approved_action_binding": record.get("approved_action_binding"),
        "armed_deadline_key": record.get("armed_deadline_key"),
        "intermittency": INTERMITTENCY_NOTICE if spec["cause"] == "calendar" else "",
        "routine": _local_routine_descriptor(spec["action"]["kind"]),
    }
    current_spec_digest = _digest(spec)
    current_admission_identity = _admission_identity(record)
    pending_completions = []
    for delivery in completion_deliveries:
        if delivery.get("dependent_trigger_id") != spec["trigger_id"]:
            continue
        proof = delivery.get("source_completion")
        if not _completion_proof_matches_delivery(delivery, proof):
            continue
        unchanged = (
            delivery.get("dependent_spec_digest") == current_spec_digest
            and delivery.get("dependent_admission_identity")
            == current_admission_identity
        )
        pending_completions.append({
            "source_trigger_id": delivery.get("source_trigger_id"),
            "source_event_id": delivery.get("source_event_id"),
            "source_completed_at": proof.get("completed_at"),
            "created_at": delivery.get("created_at"),
            "state": (
                "pending_retry" if unchanged
                else "blocked_by_trigger_change"
            ),
        })
    pending_completions.sort(key=lambda item: (
        item.get("created_at") or "", item.get("source_event_id") or "",
    ))
    view["pending_completions"] = pending_completions
    if spec["cause"] == "calendar" and record.get("status") == "active":
        view["next_due_at"] = record.get("next_due_at")
    if firings is not None:
        view["firings"] = firings
    return view


def _resolution_note(spec: Mapping[str, Any], *,
                     binding: Mapping[str, Any] | None = None) -> str:
    """A one-line review of the exact material action, including its input."""
    action = spec["action"]
    if action["kind"] == "project_tool":
        resolved = binding or resolve_action_binding(action)
        if resolved.get("interface") == "stdin-stdout-json":
            stdin_json = action["stdin"] if "stdin" in action else {}
            invocation = f"stdin={_canonical_json(stdin_json)}"
        else:
            invocation = f"args={_canonical_json(action.get('args') or [])}"
        return (
            f"project tool {action['nexus']}:{action['tool']} with exact "
            f"{invocation}"
        )
    if action["kind"] == "email_send":
        return (
            f"email via Fastmail with exact action={_canonical_json(action)}"
        )
    resolved = binding or resolve_action_binding(action)
    project_context = ""
    if (
        resolved.get("project_nexus") is not None
        or resolved.get("project_profile") is not None
    ):
        project_context = (
            " for resolved project nexus="
            f"{json.dumps(resolved.get('project_nexus'), ensure_ascii=False)}"
            " and profile="
            f"{json.dumps(resolved.get('project_profile'), ensure_ascii=False)}"
        )
    return (
        f"framework {action['framework']}{project_context} with exact "
        f"input={json.dumps(action['input'], ensure_ascii=False)}"
    )


# ── the service ──────────────────────────────────────────────────────────


class TriggerService:
    """Authoring, lifecycle, dispatch, and firing evidence for Triggers."""

    def __init__(self, *, queue: DeadlineQueue | None = None,
                 ledger: EventLedger | None = None,
                 executor: Callable[[Callable[[], None]], None] | None = None,
                 firing_timeout_sec: float | None = None,
                 terminate_actions: bool | None = None):
        self._queue = queue
        self._ledger = ledger
        # Injectable so tests run a firing inline instead of racing a thread.
        self._executor = executor or _spawn_firing_thread
        # Production action work crosses a process boundary so the declared
        # whole-firing deadline can stop real work. Existing inline test
        # executors stay direct unless the test explicitly exercises timeout.
        self._terminate_actions = (
            executor is None if terminate_actions is None else terminate_actions
        )
        self._firing_timeout_sec = (
            FIRING_TIMEOUT_SEC if firing_timeout_sec is None
            else float(firing_timeout_sec)
        )

    @property
    def queue(self) -> DeadlineQueue:
        return self._queue if self._queue is not None else deadline_queue()

    @property
    def ledger(self) -> EventLedger:
        return self._ledger if self._ledger is not None else EventLedger()

    # ---- read ----

    def list_triggers(self, *, include_retired: bool = False) -> list[dict]:
        with _PROCESS_LOCK, _exclusive():
            state = _load()
            records = list(state["triggers"].values())
            completion_deliveries = list(
                state["completion_deliveries"].values()
            )
        # One ledger read for the whole listing. Reading it per Trigger meant
        # re-parsing a multi-megabyte state file once per card on every poll.
        ledger_rows = self.ledger.list_events(event_type=FIRING_EVENT_TYPE)
        views = []
        for record in sorted(records, key=lambda item: item["spec"]["trigger_id"]):
            if not include_retired and record.get("status") == "retired":
                continue
            views.append(_record_view(
                record,
                firings=self._firing_rows(
                    ledger_rows, record["spec"]["trigger_id"], limit=1,
                ),
                completion_deliveries=completion_deliveries,
            ))
        return views

    def get(self, trigger_id: str, *, firing_limit: int = 25) -> dict:
        trigger_id = _safe_id(trigger_id, "trigger_id")
        with _PROCESS_LOCK, _exclusive():
            state = _load()
            record = state["triggers"].get(trigger_id)
            if record is None:
                raise TriggerConflict(f"no Trigger with id {trigger_id!r}")
            completion_deliveries = list(
                state["completion_deliveries"].values()
            )
        return _record_view(
            record,
            firings=self.firings(trigger_id, limit=firing_limit),
            completion_deliveries=completion_deliveries,
        )

    def inspect(self, trigger_id: str) -> dict:
        """Return the exact local email message, without provider contact."""
        record = self._require(_safe_id(trigger_id, "trigger_id"))
        action = record["spec"]["action"]
        if action["kind"] != "email_send":
            raise TriggerConflict("only an email Trigger has an exact message to inspect")
        try:
            try:
                from email_channel import inspect_message
            except ImportError:  # pragma: no cover - package import context
                from orchestrator.email_channel import inspect_message
            return inspect_message(action)
        except Exception as exc:
            raise TriggerConflict(f"email message is not usable: {exc}") from exc

    def _require(self, trigger_id: str) -> dict:
        with _PROCESS_LOCK, _exclusive():
            record = _load()["triggers"].get(trigger_id)
        if record is None:
            raise TriggerConflict(f"no Trigger with id {trigger_id!r}")
        return record

    def firings(self, trigger_id: str | None = None, *, limit: int = 25) -> list[dict]:
        """Recent firings, newest first, read from the shared event ledger."""
        return self._firing_rows(
            self.ledger.list_events(event_type=FIRING_EVENT_TYPE),
            trigger_id, limit=limit)

    @staticmethod
    def _firing_rows(ledger_rows: list[dict], trigger_id: str | None,
                     *, limit: int) -> list[dict]:
        rows = []
        for record in ledger_rows:
            subject = record.get("subject") or {}
            if trigger_id and subject.get("trigger_id") != trigger_id:
                continue
            receipt = record.get("receipt") or {}
            # ``outcome`` is the human projection of the ledger status; the
            # status itself is evidence and is never rewritten. A firing still
            # on its worker thread reads "running", not "claimed", because the
            # ledger's vocabulary is not the user's.
            status = record.get("status")
            termination_pending = bool(
                status == "claimed"
                and record.get("termination_unacknowledged_at")
            )
            rows.append({
                "event_id": record.get("event_id"),
                "trigger_id": subject.get("trigger_id"),
                "cause": subject.get("cause"),
                "source": subject.get("source"),
                "status": status,
                "outcome": receipt.get("outcome") or (
                    "termination_unacknowledged" if termination_pending
                    else "running" if status == "claimed" else status),
                "claimed_at": record.get("claimed_at"),
                "finished_at": (
                    None if status == "claimed"
                    else record.get("completed_at") or record.get("updated_at")
                ),
                "receipt": receipt or None,
                "error": (
                    record.get("termination_error") if termination_pending
                    else record.get("error")
                ),
            })
        rows.sort(key=lambda row: (row.get("claimed_at") or ""), reverse=True)
        return rows[:limit] if limit else rows

    # ---- authoring ----

    def create(self, raw: Mapping[str, Any]) -> dict:
        spec = normalize_spec(raw)
        resolve_action_binding(spec["action"])
        with _PROCESS_LOCK, _exclusive():
            state = _load()
            if spec["trigger_id"] in state["triggers"]:
                raise TriggerConflict(
                    f"a Trigger with id {spec['trigger_id']!r} already exists"
                )
            self._assert_no_completion_cycle(state, spec)
            record = {
                "spec": spec, "status": "draft", "created_at": _now(),
                "activated_at": None, "approved_spec_digest": None,
                "approved_action_binding": None, "armed_deadline_key": None,
                "next_due_at": None,
            }
            state["triggers"][spec["trigger_id"]] = record
            _save(state)
        return _record_view(record, firings=[])

    def update(self, trigger_id: str, raw: Mapping[str, Any]) -> dict:
        """Replace a Trigger's specification.

        Editing is allowed only while draft or paused, and always returns the
        Trigger to draft: the approval was of an exact digest, so a changed
        spec has not been approved.
        """
        trigger_id = _safe_id(trigger_id, "trigger_id")
        merged = dict(raw)
        merged["trigger_id"] = trigger_id
        spec = normalize_spec(merged)
        resolve_action_binding(spec["action"])
        armed_key = None
        with _PROCESS_LOCK, _exclusive():
            state = _load()
            record = state["triggers"].get(trigger_id)
            if record is None:
                raise TriggerConflict(f"no Trigger with id {trigger_id!r}")
            if record.get("status") not in {"draft", "paused"}:
                raise TriggerConflict(
                    f"a {record.get('status')} Trigger cannot be edited; pause it first"
                )
            self._assert_no_completion_cycle(state, spec)
            armed_key = record.get("armed_deadline_key")
            record.update({
                "spec": spec, "status": "draft", "activated_at": None,
                "approved_spec_digest": None, "approved_action_binding": None,
                "armed_deadline_key": None, "next_due_at": None,
            })
            _save(state)
        self._cancel_deadline(armed_key, "Trigger specification was edited")
        return self.get(trigger_id, firing_limit=5)

    def _assert_no_completion_cycle(self, state: Mapping[str, Any],
                                    proposed: Mapping[str, Any]) -> None:
        """A completion chain must terminate.

        Ported from G1.19's framework-completion cycle check, reduced to
        Trigger identities because the Process Definitions it walked are gone.
        """
        edges: dict[str, str] = {}
        for record in state["triggers"].values():
            spec = record["spec"]
            if spec["trigger_id"] == proposed["trigger_id"]:
                continue
            if spec["cause"] == "trigger_completion":
                edges[spec["trigger_id"]] = spec["condition"]["source_trigger_id"]
        if proposed["cause"] == "trigger_completion":
            edges[proposed["trigger_id"]] = \
                proposed["condition"]["source_trigger_id"]
        node = proposed["trigger_id"]
        seen = {node}
        while node in edges:
            node = edges[node]
            if node in seen:
                raise TriggerConflict(
                    "completion Triggers would form a cycle; a chain must terminate"
                )
            seen.add(node)

    # ---- lifecycle ----

    def activation_review(self, trigger_id: str) -> dict:
        """The exact action and binding a human approves before deployment."""
        record = self._require(_safe_id(trigger_id, "trigger_id"))
        spec = record["spec"]
        binding = resolve_action_binding(spec["action"])
        return {
            "trigger_id": spec["trigger_id"],
            "name": spec["name"],
            # Keep the established wire name used by the browser and slash
            # surfaces. The approval token now covers the public program
            # binding as well as the normalized specification.
            "spec_digest": _activation_approval_digest(spec, binding),
            # Firings remain identified by the specification itself; program
            # identity is authenticated independently by the binding.
            "firing_spec_digest": _digest(spec),
            "cause": spec["cause"],
            "condition": copy.deepcopy(spec["condition"]),
            "will_run": _resolution_note(spec, binding=binding),
            "action_binding": binding,
            "routine": _local_routine_descriptor(spec["action"]["kind"]),
            "runtime_justification": spec.get("runtime_justification"),
            "intermittency": (INTERMITTENCY_NOTICE
                              if spec["cause"] == "calendar" else ""),
            "status": record.get("status"),
        }

    def activate(self, trigger_id: str, *, expected_spec_digest: str) -> dict:
        trigger_id = _safe_id(trigger_id, "trigger_id")
        with _PROCESS_LOCK, _exclusive():
            state = _load()
            record = state["triggers"].get(trigger_id)
            if record is None:
                raise TriggerConflict(f"no Trigger with id {trigger_id!r}")
            spec = record["spec"]
            binding = resolve_action_binding(spec["action"])
            approval_digest = _activation_approval_digest(spec, binding)
            if expected_spec_digest != approval_digest:
                raise TriggerConflict(
                    "the Trigger specification or bound action changed since it "
                    "was reviewed; re-read it and approve the current action"
                )
            if record.get("status") != "draft":
                raise TriggerConflict(
                    f"only a draft Trigger can be activated (this one is "
                    f"{record.get('status')})"
                )
            if spec["cause"] == "calendar" and not spec.get("runtime_justification"):
                raise TriggerConflict(
                    "a calendar Trigger cannot be activated without a written "
                    "runtime-impossibility justification"
                )
            spec_digest = _digest(spec)
            record.update({
                "status": "active", "activated_at": _now(),
                "approved_spec_digest": spec_digest,
                "approved_action_binding": binding,
            })
            _save(state)
        self._arm_calendar(trigger_id)
        return self.get(trigger_id)

    def lifecycle(self, trigger_id: str, action: str) -> dict:
        trigger_id = _safe_id(trigger_id, "trigger_id")
        if action not in {"pause", "resume", "retire"}:
            raise TriggerInputRequired("action must be pause, resume, or retire")
        allowed = {"pause": {"active"}, "resume": {"paused"},
                   "retire": {"draft", "active", "paused"}}
        target = {"pause": "paused", "resume": "active", "retire": "retired"}[action]
        armed_key = None
        with _PROCESS_LOCK, _exclusive():
            state = _load()
            record = state["triggers"].get(trigger_id)
            if record is None:
                raise TriggerConflict(f"no Trigger with id {trigger_id!r}")
            current = record.get("status")
            if current not in allowed[action]:
                raise TriggerConflict(f"a {current} Trigger cannot {action}")
            record["status"] = target
            if action == "resume":
                # Resuming mints a new admission identity. An event captured
                # before authority was revoked must not become executable
                # merely because the same specification is active again.
                record["activated_at"] = _now()
            if action != "resume":
                armed_key = record.get("armed_deadline_key")
                record["armed_deadline_key"] = None
                record["next_due_at"] = None
            _save(state)
        if armed_key:
            self._cancel_deadline(armed_key, f"Trigger was {target}")
        if action == "resume":
            self._arm_calendar(trigger_id)
        return self.get(trigger_id)

    def rollback(self, trigger_id: str) -> dict:
        """Cancel an unsent email and retire its Trigger.

        Once a successful firing has crossed the provider boundary there is
        no recall promise; the caller must resolve that state rather than
        pretending rollback can undo an external send.
        """
        trigger_id = _safe_id(trigger_id, "trigger_id")
        # Keep run admission, authority revocation, and retirement under one
        # process lock.  A run claims its EventLedger row and enters _RUNNING
        # under the same lock in _fire, so this cannot retire between a run's
        # admission check and approval consumption.
        with _PROCESS_LOCK:
            record = self._require(trigger_id)
            action = record["spec"]["action"]
            if action["kind"] != "email_send":
                raise TriggerConflict("rollback is only available for email Triggers")
            if _RUNNING.get(trigger_id):
                raise TriggerConflict(
                    "this email send is still running; rollback cannot race it"
                )
            for firing in self.firings(trigger_id, limit=0):
                receipt = firing.get("receipt") or {}
                if receipt.get("provider_contacted"):
                    raise TriggerConflict(
                        "this email has reached the provider; rollback cannot recall it"
                    )
            try:
                try:
                    from email_channel import rollback_authority
                except ImportError:  # pragma: no cover - package import context
                    from orchestrator.email_channel import rollback_authority
                authority = rollback_authority(action, trigger_id)
            except Exception as exc:
                raise TriggerConflict(f"email approval rollback failed: {exc}") from exc
            view = self.lifecycle(trigger_id, "retire")
        view["rollback"] = authority
        return view

    # ---- calendar arming ----

    def _cancel_deadline(self, key: str | None, reason: str) -> None:
        if not key:
            return
        with contextlib.suppress(Exception):
            self.queue.cancel(key, reason=reason)

    def _arm_calendar(self, trigger_id: str, *, after: datetime | None = None) -> str | None:
        """Arm exactly one persisted deadline for the next occurrence.

        The payload carries the exact specification and admission identities
        observed here. The handler may reload current state for display and
        re-arming, but can execute only this immutable contract.
        """
        record = self._require(trigger_id)
        spec = record["spec"]
        if spec["cause"] != "calendar" or record.get("status") != "active":
            return None
        expected_spec_digest = _digest(spec)
        expected_admission_identity = _admission_identity(record)
        moment = after or datetime.now(timezone.utc)
        due = next_occurrence(spec["condition"]["schedule"], moment)
        key = (
            f"trigger:{trigger_id}:{due.isoformat()}:"
            f"{expected_admission_identity.removeprefix('sha256:')}"
        )
        self.queue.put(key, due.isoformat(), DEADLINE_EVENT_TYPE, {
            "trigger_id": trigger_id,
            "scheduled_for": normalized_instant(due.isoformat()),
            "timezone": spec["condition"]["schedule"]["timezone"],
            "expected_spec_digest": expected_spec_digest,
            "expected_admission_identity": expected_admission_identity,
        })
        with _PROCESS_LOCK, _exclusive():
            state = _load()
            current = state["triggers"].get(trigger_id)
            still_active = (
                current is not None
                and current.get("status") == "active"
                and _admission_identity(current) == expected_admission_identity
            )
            if still_active:
                current["armed_deadline_key"] = key
                current["next_due_at"] = normalized_instant(due.isoformat())
                _save(state)
        if not still_active:
            # The Trigger was paused or retired between resolving the
            # occurrence and recording it. The deadline is already persisted,
            # so cancel it here rather than leaving a contract nothing owns.
            self._cancel_deadline(key, "Trigger left the active state while arming")
            return None
        return key

    def arm_active_calendar_triggers(self) -> list[str]:
        """Reconcile once at startup. Not a scan for work — a re-arm of the
        exact occurrences the persisted Trigger set already declares."""
        armed = []
        for view in self.list_triggers():
            spec = view["spec"]
            if spec["cause"] != "calendar" or view["status"] != "active":
                continue
            try:
                key = self._arm_calendar(spec["trigger_id"])
            except Exception as exc:
                print(f"[triggers] could not arm {spec['trigger_id']}: {exc}")
                continue
            if key:
                armed.append(key)
        return armed

    # ---- firing ----

    def _close_recovered_protection(self, record: Mapping[str, Any]) -> None:
        """Close one existing protected start only after its process is dead."""
        execution_id = record.get("protection_execution_id")
        if execution_id is None:
            return
        if not isinstance(execution_id, str) or not execution_id:
            raise TriggerError(
                "unresolved Trigger protection identity is invalid"
            )
        try:
            try:
                import system_protection as _sp
            except ImportError:  # pragma: no cover - package context
                from orchestrator import system_protection as _sp
            audit = _sp.verify_audit()
            starts = [
                row for row in audit
                if row.get("execution_id") == execution_id
                and row.get("event_type") == "protected_action_started"
            ]
            terminals = [
                row for row in audit
                if row.get("execution_id") == execution_id
                and row.get("event_type") in {
                    "protected_action_completed", "protected_action_failed",
                }
            ]
            if len(starts) != 1:
                raise TriggerError(
                    "unresolved Trigger lacks one authenticated protected start"
                )
            if len(terminals) > 1:
                raise TriggerError(
                    "unresolved Trigger has duplicate protected terminal receipts"
                )
            start = starts[0]
            request = start.get("request")
            if not isinstance(request, Mapping):
                raise TriggerError(
                    "unresolved Trigger protected start request is invalid"
                )
            raw_selectors = request.get("selectors")
            if not isinstance(raw_selectors, list):
                raise TriggerError(
                    "unresolved Trigger protected selectors are invalid"
                )
            execution = _sp.ProtectionExecution(
                execution_id=execution_id,
                request_digest=str(start.get("request_digest") or ""),
                start_digest=str(start.get("record_digest") or ""),
                action=str(request.get("action") or ""),
                selectors=tuple(str(value) for value in raw_selectors),
                approval_id=str(start.get("approval_id") or ""),
                approval_action=str(start.get("approval_action") or ""),
                approval_args_hash=str(start.get("approval_args_hash") or ""),
            )
            if terminals:
                terminal = terminals[0]
                if (
                    terminal.get("start_digest") != execution.start_digest
                    or terminal.get("request_digest") != execution.request_digest
                ):
                    raise TriggerError(
                        "unresolved Trigger protected terminal identity changed"
                    )
                return
            raw_pre_state = request.get("pre_state")
            if not isinstance(raw_pre_state, list) or not all(
                isinstance(value, Mapping)
                and value.get("kind") == "logical"
                for value in raw_pre_state
            ):
                raise TriggerError(
                    "unresolved Trigger protected logical state is invalid"
                )
            _sp.complete_execution(
                execution,
                ok=False,
                result={
                    "error": str(
                        record.get("termination_error")
                        or "Trigger action ended without an acknowledged termination"
                    ),
                    "process_tree_death_confirmed": True,
                },
                post_state=[copy.deepcopy(dict(value)) for value in raw_pre_state],
            )
        except TriggerError:
            raise
        except Exception as exc:
            raise TriggerError(
                f"unresolved Trigger protection receipt could not close: {exc}"
            ) from exc

    def reconcile_unresolved_firings(
        self, trigger_id: str | None = None,
    ) -> dict[str, list[str]]:
        """Honor durable process claims until their trees are proved dead."""
        selected = _safe_id(trigger_id, "trigger_id") if trigger_id else None
        summary: dict[str, list[str]] = {
            "retained": [], "released": [], "errors": [],
        }
        rows = self.ledger.list_events(event_type=FIRING_EVENT_TYPE)
        rows.sort(key=lambda row: str(row.get("claimed_at") or ""))
        for row in rows:
            subject = row.get("subject") or {}
            row_trigger_id = str(subject.get("trigger_id") or "")
            event_id = str(row.get("event_id") or "")
            process_identity = row.get("process_identity")
            if (
                row.get("status") != "claimed"
                or not event_id
                or not row_trigger_id
                or (selected is not None and row_trigger_id != selected)
                or not isinstance(process_identity, Mapping)
            ):
                continue
            with _PROCESS_LOCK:
                live_guard = _RUNNING.get(row_trigger_id)
            if (
                live_guard == event_id
                and not row.get("termination_unacknowledged_at")
            ):
                summary["retained"].append(event_id)
                continue
            if not _process_identity_death_confirmed(process_identity):
                if (
                    live_guard != event_id
                    and not row.get("termination_unacknowledged_at")
                ):
                    # A fresh process has an in-memory guard. Reaching this
                    # branch without one means startup inherited the durable
                    # identity but not the worker connection, so later
                    # admission must re-check death rather than treating it as
                    # a healthy worker forever.
                    try:
                        self.ledger.transition(
                            event_id, {"claimed"}, "claimed",
                            termination_unacknowledged_at=_now(),
                            termination_error=(
                                "restart recovery: Trigger action process tree "
                                "is still live or its death cannot be proved"
                            ),
                        )
                    except Exception as exc:
                        summary["errors"].append(f"{event_id}: {exc}")
                with _PROCESS_LOCK:
                    if _RUNNING.get(row_trigger_id) in {None, event_id}:
                        _RUNNING[row_trigger_id] = event_id
                summary["retained"].append(event_id)
                continue
            try:
                current = self.ledger.get(event_id)
                if current is None or current.get("status") != "claimed":
                    with _PROCESS_LOCK:
                        if _RUNNING.get(row_trigger_id) == event_id:
                            _RUNNING.pop(row_trigger_id, None)
                    continue
                self._close_recovered_protection(current)
                confirmed_at = _now()
                prior_error = str(
                    current.get("termination_error")
                    or "restart recovery: Trigger action process ended without "
                       "an acknowledged termination"
                )
                self.ledger.transition(
                    event_id, {"claimed"}, "failed",
                    error=(f"{prior_error}; process-tree death was positively "
                           "confirmed"),
                    completed_at=confirmed_at,
                )
            except Exception as exc:
                with _PROCESS_LOCK:
                    if _RUNNING.get(row_trigger_id) in {None, event_id}:
                        _RUNNING[row_trigger_id] = event_id
                summary["retained"].append(event_id)
                summary["errors"].append(f"{event_id}: {exc}")
                continue
            with _PROCESS_LOCK:
                if _RUNNING.get(row_trigger_id) == event_id:
                    _RUNNING.pop(row_trigger_id, None)
            summary["released"].append(event_id)
        return summary

    def _reconcile_before_admission(self, trigger_id: str) -> None:
        """Refresh only a durable unresolved guard, never a healthy worker."""
        with _PROCESS_LOCK:
            guarded_event_id = _RUNNING.get(trigger_id)
        if guarded_event_id:
            guarded = self.ledger.get(guarded_event_id)
            if guarded is None:
                # An opaque process-local guard may belong to a worker whose
                # durable claim has not been observed yet. Retain it.
                return
            if guarded.get("status") == "claimed":
                if not guarded.get("termination_unacknowledged_at"):
                    return
            else:
                with _PROCESS_LOCK:
                    if _RUNNING.get(trigger_id) == guarded_event_id:
                        _RUNNING.pop(trigger_id, None)
        self.reconcile_unresolved_firings(trigger_id)

    def run_manual(self, trigger_id: str, *, request_id: str | None = None) -> dict:
        """Fire one Trigger on an explicit human request.

        Allowed while draft or paused as well as active: running a Trigger
        once is how you find out whether it does what you meant before you
        deploy it. A retired Trigger never runs.
        """
        trigger_id = _safe_id(trigger_id, "trigger_id")
        record = self._require(trigger_id)
        if record.get("status") == "retired":
            raise TriggerConflict("a retired Trigger cannot be run")
        request = _safe_text(
            request_id or f"{_now()}:{os.getpid()}", "request_id", limit=200)
        return self._fire(
            record, "manual", {"request_id": request},
            expected_spec_digest=_digest(record["spec"]),
            expected_admission_identity=_admission_identity(record),
        )

    def dispatch_paths(self, paths: Iterable[str]) -> dict:
        """Fire every active file-change Trigger matched by an exact write."""
        exact = sorted({str(Path(path).resolve()) for path in paths})
        summary = {"fired": [], "errors": []}
        if not exact:
            return summary
        for view in self.list_triggers():
            spec = view["spec"]
            if spec["cause"] != "file_change" or view["status"] != "active":
                continue
            matched = [path for path in exact
                       if any(_within(path, selector)
                              for selector in spec["condition"]["path_selectors"])]
            if not matched:
                continue
            try:
                firing = self._fire(view, "file_change", {
                    "paths": [_bound_identity(path) for path in matched],
                }, expected_spec_digest=_digest(spec),
                    expected_admission_identity=_admission_identity(view))
                summary["fired"].append({
                    "trigger_id": spec["trigger_id"],
                    "event_id": firing.get("event_id"),
                    "paths": len(matched),
                    # A redelivery of bytes already fired returns the original
                    # claim and runs nothing. Reporting it as a fresh firing
                    # would overstate what happened in the lane's own log.
                    "duplicate": bool(firing.get("duplicate")),
                })
            except Exception as exc:
                summary["errors"].append(f"{spec['trigger_id']}: {exc}")
        return summary

    def handle_calendar_deadline(self, payload: Mapping[str, Any]) -> dict:
        """Deadline-lane entry point. Runs the firing off-lane and re-arms."""
        trigger_id = _safe_id(payload.get("trigger_id"), "trigger_id")
        scheduled_for = normalized_instant(str(payload["scheduled_for"]))
        zone_name = str(payload.get("timezone") or "")
        expected_spec_digest = str(payload.get("expected_spec_digest") or "")
        expected_admission_identity = str(
            payload.get("expected_admission_identity") or ""
        )
        record = self._require(trigger_id)
        spec = record["spec"]
        try:
            if spec["cause"] != "calendar":
                return {"outcome": "stale",
                        "detail": "Trigger is no longer a calendar Trigger"}
            if record.get("status") != "active":
                return {"outcome": "stale",
                        "detail": f"Trigger is {record.get('status')}"}
            if not expected_admission_identity:
                return {
                    "outcome": "stale",
                    "detail": (
                        "calendar deadline predates authenticated admission "
                        "support; its action was not run"
                    ),
                }
            schedule = spec["condition"]["schedule"]
            late_by = time.time() - instant_timestamp(scheduled_for)
            overdue = late_by > int(schedule["grace_seconds"])
            if overdue and schedule["missed_policy"] == "skip":
                firing = self._fire(record, "calendar", {
                    "scheduled_for": scheduled_for,
                }, forced_receipt={
                    "outcome": "skipped",
                    "reason": ("Ora was not running inside the declared grace "
                               "window and this Trigger's missed policy is skip"),
                    "late_by_seconds": int(late_by),
                }, expected_spec_digest=expected_spec_digest,
                    expected_admission_identity=expected_admission_identity)
                return {"outcome": "skipped", "event_id": firing.get("event_id"),
                        "late_by_seconds": int(late_by)}
            firing = self._fire(record, "calendar", {
                "scheduled_for": scheduled_for,
            }, extra_receipt={"late_by_seconds": int(max(0.0, late_by))},
                expected_spec_digest=expected_spec_digest,
                expected_admission_identity=expected_admission_identity)
            return {"outcome": "dispatched", "event_id": firing.get("event_id"),
                    "late_by_seconds": int(max(0.0, late_by))}
        except TriggerStaleEvent as exc:
            return {"outcome": "stale", "detail": str(exc)}
        finally:
            # The next occurrence is a distinct time-caused contract, not a
            # retry of this one. Advancing past *now* rather than replaying
            # every missed window is what stops a week-long outage becoming a
            # burst of seven firings when the laptop opens.
            try:
                after = max(
                    datetime.fromisoformat(scheduled_for),
                    datetime.now(timezone.utc),
                )
                self._arm_calendar(trigger_id, after=after)
            except Exception as exc:
                print(f"[triggers] could not re-arm {trigger_id} "
                      f"({zone_name or 'no zone'}): {exc}")

    def _fire(self, record: Mapping[str, Any], cause: str, source: Mapping[str, Any],
              *, forced_receipt: dict | None = None,
              extra_receipt: dict | None = None,
              expected_spec_digest: str | None = None,
              expected_admission_identity: str | None = None) -> dict:
        """Admit and claim one immutable firing, then run it off-lane."""
        ledger = self.ledger
        trigger_id = record["spec"]["trigger_id"]
        self._reconcile_before_admission(trigger_id)
        if expected_spec_digest is None:
            expected_spec_digest = _digest(record["spec"])
        if expected_admission_identity is None:
            expected_admission_identity = _admission_identity(record)
        with _PROCESS_LOCK, _exclusive():
            # Re-read while holding the Trigger store lock used by lifecycle
            # changes.  The caller's earlier view may have been paused or
            # retired while preparing this firing, and revocation must win
            # before either a standing receipt or a firing claim is minted.
            current = _load()["triggers"].get(trigger_id)
            if current is None:
                raise TriggerConflict(f"no Trigger with id {trigger_id!r}")
            current_spec_digest = _digest(current["spec"])
            current_admission_identity = _admission_identity(current)
            if (
                expected_spec_digest != current_spec_digest
                or expected_admission_identity != current_admission_identity
            ):
                raise TriggerStaleEvent(
                    "the event names an earlier Trigger specification or "
                    "admission; current authority was not substituted"
                )
            status = current.get("status")
            if status == "retired":
                raise TriggerConflict("a retired Trigger cannot be fired")
            if cause != "manual" and status != "active":
                raise TriggerConflict(
                    f"a nonmanual firing requires an active Trigger (this one is {status})"
                )
            spec = copy.deepcopy(current["spec"])
            spec_digest = current_spec_digest
            framework_prepared = None
            if spec["action"]["kind"] == "framework":
                # Resolve and compare the exact composed contract before a
                # firing claim exists.  The same in-memory snapshot is handed
                # to execution; neither step rereads the Framework.
                action_binding, framework_prepared = (
                    _resolve_framework_action_binding(spec["action"])
                )
                action_binding = _public_action_binding(action_binding)
            else:
                action_binding = resolve_action_binding(spec["action"])
            if status == "active":
                if current.get("approved_spec_digest") != spec_digest:
                    raise TriggerConflict(
                        "the approved specification no longer matches this "
                        "Trigger; re-review and re-activate it"
                    )
                if current.get("approved_action_binding") != action_binding:
                    raise TriggerConflict(
                        "action_definition_drifted: what this Trigger would run "
                        "has changed since it was approved. Re-review and "
                        "re-activate it."
                    )
            subject = {
                "trigger_id": trigger_id,
                "spec_digest": spec_digest,
                "admission_identity": current_admission_identity,
                "cause": cause,
                "source": copy.deepcopy(dict(source)),
            }
            event_id = event_identity(FIRING_EVENT_TYPE, subject)
            existing = ledger.get(event_id)
            if existing is not None:
                return {"event_id": event_id, "status": existing.get("status"),
                        "duplicate": True}
            already = _RUNNING.get(trigger_id)
            if forced_receipt is not None:
                claim, created = ledger.claim(
                    event_id=event_id, event_type=FIRING_EVENT_TYPE,
                    subject=subject,
                )
                if not created:
                    return {"event_id": event_id, "status": claim.get("status"),
                            "duplicate": True}
                ledger.transition(event_id, {"claimed"}, "completed",
                                  receipt=forced_receipt, completed_at=_now())
                return {"event_id": event_id, "status": "completed",
                        "receipt": forced_receipt}
            if already:
                claim, created = ledger.claim(
                    event_id=event_id, event_type=FIRING_EVENT_TYPE,
                    subject=subject,
                )
                if not created:
                    return {"event_id": event_id, "status": claim.get("status"),
                            "duplicate": True}
                receipt = {
                    "outcome": "skipped",
                    "reason": "a firing for this Trigger is already running",
                    "blocking_event_id": already,
                }
                ledger.transition(event_id, {"claimed"}, "completed",
                                  receipt=receipt, completed_at=_now())
                return {"event_id": event_id, "status": "completed",
                        "receipt": receipt}

            protection_execution = None
            if spec["action"]["kind"] == "project_tool":
                try:
                    try:
                        import system_protection as _sp
                    except ImportError:  # pragma: no cover - package context
                        from orchestrator import system_protection as _sp
                    if status == "active":
                        protection_execution = _sp.authorize_trigger_project_action(
                            trigger_record=current,
                            binding=action_binding,
                        )
                    else:
                        # A manual draft/paused run is not covered by Trigger
                        # activation. It uses the existing Paused one-shot path.
                        protection_execution = _sp.authorize_project_action(
                            "project_tool_execute",
                            binding=action_binding,
                            surface="trigger",
                        )
                except _sp.SystemProtectionError as exc:
                    raise TriggerConflict(f"System Protection: {exc}") from exc

            try:
                claim, created = ledger.claim(
                    event_id=event_id, event_type=FIRING_EVENT_TYPE,
                    subject=subject,
                )
            except BaseException as exc:
                if protection_execution is not None:
                    try:
                        _sp.complete_execution(
                            protection_execution,
                            ok=False,
                            result={"error": f"firing claim failed: {exc}"},
                            post_state=_sp.project_binding_states(action_binding),
                        )
                    except Exception as receipt_error:
                        raise _sp.ProtectionAuditError(
                            "Trigger firing claim failed and its failure receipt "
                            f"could not persist: {receipt_error}"
                        ) from exc
                raise
            if not created:
                if protection_execution is not None:
                    _sp.complete_execution(
                        protection_execution,
                        ok=False,
                        result={"error": "duplicate firing identity"},
                        post_state=_sp.project_binding_states(action_binding),
                    )
                return {"event_id": event_id, "status": claim.get("status"),
                        "duplicate": True}
            _RUNNING[trigger_id] = event_id
        action_snapshot = copy.deepcopy(spec["action"])
        binding_snapshot = copy.deepcopy(action_binding)
        try:
            self._executor(lambda: self._execute(
                trigger_id,
                event_id,
                action_snapshot=action_snapshot,
                binding_snapshot=binding_snapshot,
                claimed_spec_digest=spec_digest,
                claimed_admission_identity=current_admission_identity,
                extra_receipt=extra_receipt,
                framework_prepared=framework_prepared,
                protection_execution=protection_execution,
            ))
        except BaseException as exc:
            # Action and termination failures are consumed inside _execute.
            # Reaching this branch means the executor itself failed to launch
            # the worker, so retain the ordinary launch-failure behavior.
            with contextlib.suppress(Exception):
                ledger.transition(
                    event_id, {"claimed"}, "failed",
                    error=f"{type(exc).__name__}: {exc}", completed_at=_now(),
                )
            if protection_execution is not None:
                try:
                    _sp.complete_execution(
                        protection_execution,
                        ok=False,
                        result={"error": f"{type(exc).__name__}: {exc}"},
                        post_state=_sp.project_binding_states(binding_snapshot),
                    )
                except Exception as receipt_error:
                    with _PROCESS_LOCK:
                        if _RUNNING.get(trigger_id) == event_id:
                            _RUNNING.pop(trigger_id, None)
                    raise _sp.ProtectionAuditError(
                        "Trigger worker launch failed and its failure receipt "
                        f"could not persist: {receipt_error}"
                    ) from exc
            with _PROCESS_LOCK:
                if _RUNNING.get(trigger_id) == event_id:
                    _RUNNING.pop(trigger_id, None)
            raise
        return {"event_id": event_id, "status": "claimed"}

    def _execute(self, trigger_id: str, event_id: str, *,
                 action_snapshot: Mapping[str, Any],
                 binding_snapshot: Mapping[str, Any],
                 claimed_spec_digest: str,
                 claimed_admission_identity: str,
                 extra_receipt: dict | None = None,
                 framework_prepared=None,
                 protection_execution=None) -> None:
        ledger = self.ledger
        protection_closed = False
        release_running = True
        try:
            action = copy.deepcopy(dict(action_snapshot))
            binding = copy.deepcopy(dict(binding_snapshot))
            # The Trigger identity scopes the email approval request but is
            # not part of the provider binding digest itself.
            if action["kind"] in {"email_send", "framework"}:
                binding = {**binding, "trigger_id": trigger_id}
            on_provider_contact = lambda: ledger.transition(
                event_id, {"claimed"}, "claimed",
                receipt={"outcome": "sending", "provider_contacted": True},
                provider_contacted=True,
            )

            def on_process_started(process_identity: Mapping[str, Any]) -> None:
                fields: dict[str, Any] = {
                    "process_identity": copy.deepcopy(dict(process_identity)),
                }
                if protection_execution is not None:
                    fields["protection_execution_id"] = (
                        protection_execution.execution_id
                    )
                ledger.transition(
                    event_id, {"claimed"}, "claimed", **fields,
                )

            def run_action():
                if self._terminate_actions:
                    return _execute_action_with_deadline(
                        action, binding,
                        prepared=framework_prepared,
                        on_provider_contact=on_provider_contact,
                        on_process_started=on_process_started,
                        timeout_sec=self._firing_timeout_sec,
                    )
                return _execute_action(
                    action, binding,
                    prepared=framework_prepared,
                    on_provider_contact=on_provider_contact,
                )

            if protection_execution is not None:
                try:
                    try:
                        import system_protection as _sp
                    except ImportError:  # pragma: no cover - package context
                        from orchestrator import system_protection as _sp
                    with _sp.protected_effect(protection_execution):
                        receipt = run_action()
                    _sp.complete_execution(
                        protection_execution,
                        ok=True,
                        result={"receipt_digest": _sp.params_digest(receipt)},
                        post_state=_sp.project_binding_states(binding_snapshot),
                    )
                    protection_closed = True
                except BaseException as action_error:
                    if _termination_exception(action_error) is not None:
                        # The protected start and firing claim both remain
                        # nonterminal until the same process identity is later
                        # proved dead. Calling complete_execution here would
                        # falsely describe possibly-live work as finished.
                        raise
                    if not protection_closed:
                        try:
                            _sp.complete_execution(
                                protection_execution,
                                ok=False,
                                result={"error": "Trigger project-tool execution failed"},
                                post_state=_sp.project_binding_states(binding_snapshot),
                            )
                            protection_closed = True
                        except Exception as receipt_error:
                            raise _sp.ProtectionAuditError(
                                "Trigger effect failed and its failure receipt "
                                f"could not persist: {receipt_error}"
                            ) from action_error
                    raise
            else:
                receipt = run_action()
            if extra_receipt:
                receipt.update(extra_receipt)
            self._stage_completion_deliveries(
                trigger_id, event_id, source_spec_digest=claimed_spec_digest,
                source_admission_identity=claimed_admission_identity,
            )
            completed = ledger.transition(
                event_id, {"claimed"}, "completed",
                receipt=receipt, completed_at=_now(),
            )
            self._dispatch_completion(
                trigger_id, event_id, source_completion=completed,
            )
        except BaseException as exc:
            termination = _termination_exception(exc)
            release_running = termination is None
            if termination is not None:
                current = ledger.get(event_id) or {}
                process_identity = (
                    termination.process_identity
                    or current.get("process_identity")
                    or {
                        "kind": "unproven_process_tree",
                        "root_pid": None,
                        "complete": False,
                    }
                )
                fields: dict[str, Any] = {
                    "process_identity": copy.deepcopy(dict(process_identity)),
                    "termination_unacknowledged_at": _now(),
                    "termination_error": f"{type(exc).__name__}: {exc}",
                }
                if protection_execution is not None:
                    fields.setdefault(
                        "protection_execution_id",
                        protection_execution.execution_id,
                    )
                try:
                    ledger.transition(
                        event_id, {"claimed"}, "claimed", **fields,
                    )
                except Exception as evidence_error:
                    # The process-local guard remains. A start-barrier record
                    # normally already carries the process identity, so
                    # startup can still retain it if this later annotation
                    # alone failed.
                    print(
                        "[triggers] unresolved termination evidence could not "
                        f"be updated for {event_id}: {evidence_error}"
                    )
            else:
                # Record before anything else: an ordinary firing that dies
                # without evidence is indistinguishable from one that never ran.
                with contextlib.suppress(Exception):
                    ledger.transition(event_id, {"claimed"}, "failed",
                                      error=f"{type(exc).__name__}: {exc}",
                                      completed_at=_now())
            # An ordinary failure is this firing's business and stops here. An
            # interpreter-level exit is the process's business and must not be
            # swallowed by a worker thread.
            if not isinstance(exc, Exception):
                raise
        finally:
            if release_running:
                with _PROCESS_LOCK:
                    if _RUNNING.get(trigger_id) == event_id:
                        _RUNNING.pop(trigger_id, None)

    def _stage_completion_deliveries(self, source_trigger_id: str,
                                     source_event_id: str, *,
                                     source_spec_digest: str,
                                     source_admission_identity: str) -> None:
        """Persist exact dependant deliveries before exposing completion."""
        with _PROCESS_LOCK, _exclusive():
            state = _load()
            source_record = state["triggers"].get(source_trigger_id)
            if source_record is None:
                raise TriggerConflict(
                    f"completion source {source_trigger_id!r} no longer exists"
                )
            changed = False
            for record in state["triggers"].values():
                spec = record["spec"]
                if (spec["cause"] != "trigger_completion"
                        or record.get("status") != "active"
                        or spec["condition"]["source_trigger_id"] != source_trigger_id):
                    continue
                subject = {
                    "source_trigger_id": source_trigger_id,
                    "source_event_id": source_event_id,
                    "dependent_trigger_id": spec["trigger_id"],
                    "dependent_spec_digest": _digest(spec),
                    "dependent_admission_identity": _admission_identity(record),
                }
                delivery_id = event_identity("trigger_completion_delivery", subject)
                if delivery_id in state["completion_deliveries"]:
                    continue
                state["completion_deliveries"][delivery_id] = {
                    "delivery_id": delivery_id,
                    **subject,
                    "source_event_type": FIRING_EVENT_TYPE,
                    "source_spec_digest": source_spec_digest,
                    "source_admission_identity": source_admission_identity,
                    "created_at": _now(),
                }
                changed = True
            if changed:
                _save(state)

    def _pending_completion_deliveries(
        self, source_event_id: str | None = None,
    ) -> list[dict]:
        with _PROCESS_LOCK, _exclusive():
            deliveries = list(_load()["completion_deliveries"].values())
        if source_event_id is not None:
            deliveries = [
                delivery for delivery in deliveries
                if delivery.get("source_event_id") == source_event_id
            ]
        return sorted(deliveries, key=lambda item: (
            item.get("created_at", ""), item.get("delivery_id", "")
        ))

    def _finish_completion_delivery(self, delivery_id: str) -> None:
        with _PROCESS_LOCK, _exclusive():
            state = _load()
            if state["completion_deliveries"].pop(delivery_id, None) is not None:
                _save(state)

    def _persist_completion_proof(
        self, source_event_id: str, proof: Mapping[str, Any],
    ) -> list[dict]:
        """Bind proof to every matching staged delivery in one atomic write."""
        with _PROCESS_LOCK, _exclusive():
            state = _load()
            matching = [
                delivery
                for delivery in state["completion_deliveries"].values()
                if delivery.get("source_event_id") == source_event_id
            ]
            for delivery in matching:
                if not _completion_proof_matches_delivery(delivery, proof):
                    raise TriggerConflict(
                        "source completion does not authenticate its staged delivery"
                    )
                current = delivery.get("source_completion")
                if current is not None and current != proof:
                    raise TriggerConflict(
                        "staged completion delivery carries conflicting proof"
                    )
            changed = False
            for delivery in matching:
                if delivery.get("source_completion") is None:
                    delivery["source_completion"] = dict(proof)
                    changed = True
            if changed:
                _save(state)
            return [copy.deepcopy(delivery) for delivery in matching]

    def _deliver_completion(self, delivery: Mapping[str, Any]) -> None:
        target = str(delivery["dependent_trigger_id"])
        record = self._require(target)
        self._fire(record, "trigger_completion", {
            "source_trigger_id": delivery["source_trigger_id"],
            "source_event_id": delivery["source_event_id"],
        }, expected_spec_digest=str(
            delivery.get("dependent_spec_digest") or ""
        ), expected_admission_identity=str(
            delivery.get("dependent_admission_identity") or ""
        ))
        self._finish_completion_delivery(str(delivery["delivery_id"]))

    def _dispatch_completion(
        self, source_trigger_id: str, source_event_id: str, *,
        source_completion: Mapping[str, Any] | None = None,
    ) -> None:
        """Persist completion eligibility, then deliver each dependant."""
        proof = _completion_proof(source_completion)
        if (
            proof is None
            or proof["event_id"] != source_event_id
            or proof["trigger_id"] != source_trigger_id
        ):
            raise TriggerConflict(
                "completion delivery requires a completed source firing"
            )
        deliveries = self._persist_completion_proof(source_event_id, proof)
        for delivery in deliveries:
            try:
                self._deliver_completion(delivery)
            except Exception as exc:
                print(f"[triggers] completion dispatch to "
                      f"{delivery.get('dependent_trigger_id')} failed: {exc}")

    def replay_completion_deliveries(self) -> list[str]:
        """Replay each unfinished dependant delivery once at process startup."""
        delivered: list[str] = []
        pending = self._pending_completion_deliveries()
        source_event_ids = list(dict.fromkeys(
            str(delivery.get("source_event_id") or "")
            for delivery in pending
        ))
        for source_event_id in source_event_ids:
            deliveries = [
                delivery for delivery in pending
                if delivery.get("source_event_id") == source_event_id
            ]
            proven = all(
                _completion_proof_matches_delivery(
                    delivery, delivery.get("source_completion"),
                )
                for delivery in deliveries
            )
            if not proven:
                # The pending snapshot was read after releasing the Trigger
                # lock. Read the ledger independently, then acquire only the
                # Trigger lock to make the exact proof durable for every child.
                source = self.ledger.get(source_event_id)
                proof = _completion_proof(source)
                if proof is None or not all(
                    _completion_proof_matches_delivery(delivery, proof)
                    for delivery in deliveries
                ):
                    if source is not None and source.get("status") == "failed":
                        for delivery in deliveries:
                            self._finish_completion_delivery(
                                str(delivery["delivery_id"])
                            )
                    continue
                try:
                    deliveries = self._persist_completion_proof(
                        source_event_id, proof,
                    )
                except Exception as exc:
                    print(f"[triggers] startup completion proof for "
                          f"{source_event_id} failed: {exc}")
                    continue
            for delivery in deliveries:
                if not _completion_proof_matches_delivery(
                    delivery, delivery.get("source_completion"),
                ):
                    continue
                try:
                    self._deliver_completion(delivery)
                    delivered.append(str(delivery["delivery_id"]))
                except Exception as exc:
                    print(f"[triggers] startup completion replay to "
                          f"{delivery.get('dependent_trigger_id')} failed: {exc}")
        return delivered

    # ---- inspection ----

    def internal_deadline_summary(self) -> dict:
        """Pending deadlines this surface does NOT own, counted honestly.

        The queue holds thousands of internal maintenance contracts. Listing
        them would bury the Triggers; hiding them would misrepresent what is
        scheduled. One counted line does neither.
        """
        try:
            counts = self.queue.pending_counts()
        except Exception:
            return {"total": 0, "by_event_type": {}, "available": False}
        internal = {key: value for key, value in counts.items()
                    if key != DEADLINE_EVENT_TYPE}
        return {
            "total": sum(internal.values()),
            "by_event_type": dict(sorted(internal.items())),
            "available": True,
        }


def _bound_identity(path: str) -> dict:
    """Bind one changed file's exact identity into the firing subject."""
    try:
        identity = artifact_identity(path)
        return {"path": identity["path"], "sha256": identity["sha256"],
                "size": identity["size"], "exists": True}
    except (OSError, ValueError):
        return {"path": str(Path(path).expanduser()), "sha256": None,
                "size": None, "exists": False}


def _spawn_firing_thread(work: Callable[[], None]) -> None:
    """Run a firing off the lane that dispatched it.

    The deadline lane also serves daily notes, log retention, and thousands of
    trace expirations; a framework run that takes minutes must not hold it.
    The thread is a daemon and never outlives the process. Restart recovery
    fails an interrupted claim with no live process identity. A claim carrying
    a spawned process identity instead remains nonterminal until Trigger
    recovery positively confirms that its process tree is dead.
    """
    threading.Thread(target=work, daemon=True, name="ora-trigger-firing").start()


@contextlib.contextmanager
def _active_run_sleep_protection():
    """Prevent macOS idle sleep only while this action process is working.

    ``caffeinate -i`` is the existing macOS mechanism.  ``-w`` binds the
    assertion to this action process, so an abrupt process death releases it
    even when Python cannot run ``finally``.  Normal exits explicitly terminate
    and reap the helper before the result crosses back to the parent.
    """
    if sys.platform != "darwin":
        yield
        return
    if not _active_run_sleep_available():
        raise TriggerError(
            "macOS active-run sleep protection is unavailable; action work "
            "was not started"
        )
    try:
        guard = subprocess.Popen(
            [_MACOS_CAFFEINATE, "-i", "-w", str(os.getpid())],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError as exc:
        raise TriggerError(
            f"macOS active-run sleep protection could not start: {exc}"
        ) from exc
    if guard.poll() is not None:
        code = guard.wait()
        raise TriggerError(
            "macOS active-run sleep protection exited before action work "
            f"started (exit {code})"
        )
    try:
        yield
    finally:
        if guard.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                guard.terminate()
        try:
            guard.wait(timeout=TERMINATION_GRACE_SEC)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                guard.kill()
            try:
                guard.wait(timeout=TERMINATION_GRACE_SEC)
            except subprocess.TimeoutExpired as exc:
                raise TriggerError(
                    "macOS active-run sleep protection did not release"
                ) from exc


def _action_process_identity() -> dict[str, Any]:
    """Describe this action process with the platform's termination identity."""
    if _uses_posix_process_groups():
        return {
            "kind": "posix_process_group",
            "root_pid": os.getpid(),
            "process_group_id": os.getpgrp(),
            "complete": True,
            "action_may_have_started": False,
        }
    return {
        "kind": "windows_process_tree",
        "root_pid": os.getpid(),
        "process_ids": [os.getpid()],
        # This pre-action wrapper identity is replaced by the parent with an
        # assigned Job identity before the start barrier can open.
        "complete": False,
        "action_may_have_started": False,
    }


def _parent_process_identity(process) -> dict[str, Any]:
    """Best available identity when the child start barrier did not finish."""
    pid = process.pid
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return {
            "kind": "unproven_process_tree",
            "root_pid": None,
            "complete": False,
            "action_may_have_started": False,
        }
    if _uses_posix_process_groups():
        return {
            "kind": "posix_process_group",
            "root_pid": pid,
            "process_group_id": pid,
            # Without the child acknowledgment, setsid may not have completed.
            "complete": False,
            "action_may_have_started": False,
        }
    return {
        "kind": "windows_process_tree",
        "root_pid": pid,
        "process_ids": [pid],
        "complete": False,
        "action_may_have_started": False,
    }


def _process_exists(process_id: int) -> bool:
    """Return whether one POSIX process identity still exists."""
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _process_identity_death_confirmed(identity: Mapping[str, Any]) -> bool:
    """Prove an existing action-tree identity dead, or fail closed."""
    kind = identity.get("kind")
    try:
        if kind == "windows_job_object":
            if _uses_posix_process_groups():
                return False
            return _windows_job_identity_death_confirmed(identity)
        if (
            kind == "posix_process_group"
            and identity.get("action_may_have_started") is not False
        ):
            # A post-start POSIX descendant can leave the recorded group with
            # setsid().  Root/group absence therefore cannot prove that all
            # action work ended, including for identities written by older code.
            return False
        if identity.get("complete") is not True:
            # Before the durable start barrier, only the wrapper can exist. Its
            # absence therefore proves no action work began. Once the barrier
            # may have opened, an incomplete Windows tree cannot account for
            # descendants and must remain blocked even if the root disappears.
            if identity.get("action_may_have_started") is not False:
                return False
            root_pid = identity.get("root_pid")
            if (
                not isinstance(root_pid, int) or isinstance(root_pid, bool)
                or root_pid <= 0
            ):
                return False
            if kind == "posix_process_group":
                return (
                    _uses_posix_process_groups()
                    and not _process_exists(root_pid)
                )
            if kind == "windows_process_tree":
                return (
                    not _uses_posix_process_groups()
                    and not _windows_live_processes({root_pid})
                )
            return False
        if kind == "posix_process_group":
            if not _uses_posix_process_groups():
                return False
            root_pid = identity.get("root_pid")
            group_id = identity.get("process_group_id")
            if (
                not isinstance(root_pid, int) or isinstance(root_pid, bool)
                or root_pid <= 0
                or not isinstance(group_id, int) or isinstance(group_id, bool)
                or group_id <= 0
            ):
                return False
            return (
                not _process_exists(root_pid)
                and not _process_group_exists(group_id)
            )
        if kind == "windows_process_tree":
            if _uses_posix_process_groups():
                return False
            raw_process_ids = identity.get("process_ids")
            if not isinstance(raw_process_ids, list) or not raw_process_ids:
                return False
            process_ids = set()
            for value in raw_process_ids:
                if (
                    not isinstance(value, int) or isinstance(value, bool)
                    or value <= 0
                ):
                    return False
                process_ids.add(value)
            return not _windows_live_processes(process_ids)
    except Exception:
        return False
    return False


def _action_process_main(
    connection, action: dict, binding: dict, durable_start: bool = False,
) -> None:
    """Process-side action entry point; reports provider contact and outcome."""
    if os.name == "posix":
        os.setsid()
        if action.get("kind") == "project_tool":
            # The project tool is a child process in this group. Let it
            # acknowledge SIGTERM and let invoke_project_tool reap it before
            # this supervisor exits; exec resets this caught handler to the
            # default disposition in the tool itself.
            signal.signal(signal.SIGTERM, lambda *_args: None)

    hold_for_parent_release = False

    def provider_contact_boundary() -> None:
        # Provider I/O may begin only after the parent has durably recorded
        # that rollback can no longer claim cancellation.  The acknowledgment
        # turns the pipe into a write-ahead barrier rather than a notification.
        connection.send(("provider_contact", None))
        kind, _payload = connection.recv()
        if kind != "provider_contact_ack":
            raise RuntimeError("provider contact was not durably acknowledged")

    try:
        if durable_start:
            # No user action begins until the parent has durably attached the
            # platform containment identity to the already-claimed firing.
            connection.send(("process_started", _action_process_identity()))
            kind, _payload = connection.recv()
            if kind != "process_started_ack":
                raise RuntimeError(
                    "action process identity was not durably acknowledged"
                )
            # POSIX retains the independently addressable process group after
            # this wrapper exits. On Windows the parent has now assigned this
            # held wrapper to a non-breakaway Job. The duplex barrier remains
            # through result/error handling so the parent can persist current
            # Job membership, release the wrapper, and prove ActiveProcesses
            # reached zero before terminal evidence.
            hold_for_parent_release = not _uses_posix_process_groups()
        with _active_run_sleep_protection():
            receipt = _execute_action(
                action, binding, prepared=None,
                on_provider_contact=provider_contact_boundary,
            )
        connection.send(("result", receipt))
    except BaseException as exc:
        with contextlib.suppress(Exception):
            connection.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        if hold_for_parent_release:
            # Result/error serialization can itself fail.  The wrapper still
            # waits on the same duplex boundary so parent cleanup can terminate
            # the kernel-owned Windows Job instead of inferring descendant
            # death from the wrapper's lifetime.
            while True:
                try:
                    kind, _payload = connection.recv()
                except (EOFError, OSError):
                    break
                if kind == "process_release":
                    break
        connection.close()


def _process_group_exists(process_group_id: int) -> bool:
    """Return whether a POSIX action group still has any member."""
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _uses_posix_process_groups() -> bool:
    return os.name == "posix"


def _create_windows_job_boundary(root_pid: int):
    """Use the repository's existing native Windows Job primitive lazily."""
    try:
        import windows_appcontainer as _wac
    except ImportError:  # pragma: no cover - package import context
        from orchestrator import windows_appcontainer as _wac
    return _wac._create_trigger_job(root_pid)


def _windows_job_identity_death_confirmed(
    identity: Mapping[str, Any],
) -> bool:
    """Ask the persisted named Job whether any contained process is active."""
    try:
        import windows_appcontainer as _wac
    except ImportError:  # pragma: no cover - package import context
        from orchestrator import windows_appcontainer as _wac
    return _wac._trigger_job_death_confirmed(dict(identity))


def _windows_live_processes(process_ids: set[int]) -> set[int]:
    """Return captured Windows process identities that still exist."""
    if not process_ids:
        return set()
    joined = ",".join(str(value) for value in sorted(process_ids))
    result = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            f"Get-Process -Id {joined} -ErrorAction SilentlyContinue | "
            "ForEach-Object { Write-Output $_.Id }",
        ],
        capture_output=True, text=True, check=False,
        timeout=TERMINATION_GRACE_SEC,
    )
    if result.returncode != 0:
        raise TriggerTerminationUnacknowledged(
            "Windows process tree could not be verified after termination"
        )
    try:
        return {
            int(line.strip()) for line in result.stdout.splitlines()
            if line.strip()
        }
    except ValueError as exc:
        raise TriggerTerminationUnacknowledged(
            "Windows process verification returned an invalid identity list"
        ) from exc


def _release_completed_windows_process(
    process, connection, job_boundary, *,
    on_process_identity: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Release the held wrapper, terminate its Job, and prove membership zero."""
    try:
        process_identity = job_boundary.identity(action_may_have_started=True)
    except BaseException as exc:
        raise TriggerTerminationUnacknowledged(
            "Windows Job membership could not be captured before release",
        ) from exc
    if on_process_identity is not None:
        try:
            on_process_identity(process_identity)
        except BaseException as exc:
            raise TriggerTerminationUnacknowledged(
                "Windows Job membership could not be durably recorded",
                process_identity=process_identity,
            ) from exc
    try:
        connection.send(("process_release", None))
    except BaseException as exc:
        raise TriggerTerminationUnacknowledged(
            "Windows action wrapper release could not be acknowledged",
            process_identity=process_identity,
        ) from exc
    persistence_error: BaseException | None = None
    try:
        process.join(TERMINATION_GRACE_SEC)
        job_boundary.terminate_and_wait(TERMINATION_GRACE_SEC)
        process.join(TERMINATION_GRACE_SEC)
        final_identity = job_boundary.identity(action_may_have_started=True)
        if on_process_identity is not None:
            try:
                on_process_identity(final_identity)
            except BaseException as exc:
                persistence_error = exc
    except BaseException as exc:
        raise TriggerTerminationUnacknowledged(
            "Windows Job death could not be verified after wrapper release",
            process_identity=process_identity,
        ) from exc
    if (
        process.is_alive()
        or final_identity.get("active_processes") != 0
        or final_identity.get("owner_handle_zero_observed") is not True
    ):
        raise TriggerTerminationUnacknowledged(
            "Windows Job remained live after wrapper release",
            process_identity=final_identity,
        )
    if persistence_error is not None:
        raise TriggerTerminationUnacknowledged(
            "Windows Job terminal membership could not be durably recorded",
            process_identity=final_identity,
        ) from persistence_error
    return final_identity


def _terminate_action_process(
    process, *,
    on_process_identity: Callable[[Mapping[str, Any]], None] | None = None,
    windows_job=None,
    action_may_have_started: bool = False,
    known_process_identity: Mapping[str, Any] | None = None,
) -> None:
    """Terminate the whole action process group and wait for acknowledgment."""
    if process.pid is None:
        if process.is_alive():
            retained_identity = _parent_process_identity(process)
            if (
                _uses_posix_process_groups()
                and action_may_have_started
            ):
                if isinstance(known_process_identity, Mapping):
                    retained_identity = copy.deepcopy(dict(known_process_identity))
                retained_identity["complete"] = False
                retained_identity["action_may_have_started"] = True
            raise TriggerTerminationUnacknowledged(
                "Trigger action has no terminable process identity",
                process_identity=retained_identity,
            )
        return
    if _uses_posix_process_groups():
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
        # If the child had not reached setsid yet, there was no process group
        # to signal. Terminating the wrapper still closes that startup race.
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
    elif windows_job is not None:  # pragma: no cover - simulated on POSIX
        try:
            process_identity = windows_job.identity(
                action_may_have_started=action_may_have_started,
            )
        except BaseException as exc:
            process_identity = (
                copy.deepcopy(dict(known_process_identity))
                if isinstance(known_process_identity, Mapping)
                else None
            )
            try:
                windows_job.terminate_and_wait(TERMINATION_GRACE_SEC)
                process.join(TERMINATION_GRACE_SEC)
            except BaseException as termination_error:
                raise TriggerTerminationUnacknowledged(
                    "Windows Job membership and termination could not be acknowledged",
                    process_identity=process_identity,
                ) from termination_error
            raise TriggerTerminationUnacknowledged(
                "Windows Job membership could not be captured before termination",
                process_identity=process_identity,
            ) from exc
        # Persist the Job identity before terminating. Unlike a point-in-time
        # parent graph, this identity still contains intermediate-parent exit
        # and late-child creation because the kernel owns membership.
        persistence_error: BaseException | None = None
        if on_process_identity is not None:
            try:
                on_process_identity(process_identity)
            except BaseException as exc:
                persistence_error = exc
        try:
            windows_job.terminate_and_wait(TERMINATION_GRACE_SEC)
            process.join(TERMINATION_GRACE_SEC)
            final_identity = windows_job.identity(
                action_may_have_started=action_may_have_started,
            )
            if on_process_identity is not None:
                try:
                    on_process_identity(final_identity)
                except BaseException as exc:
                    persistence_error = persistence_error or exc
        except BaseException as exc:
            raise TriggerTerminationUnacknowledged(
                "Windows Job termination did not complete",
                process_identity=process_identity,
            ) from exc
        if (
            process.is_alive()
            or final_identity.get("active_processes") != 0
            or final_identity.get("owner_handle_zero_observed") is not True
        ):
            raise TriggerTerminationUnacknowledged(
                "Windows Job did not acknowledge complete termination",
                process_identity=final_identity,
            )
        if persistence_error is not None and action_may_have_started:
            raise TriggerTerminationUnacknowledged(
                "Windows Job membership could not be durably recorded",
                process_identity=final_identity,
            ) from persistence_error
        return
    else:
        # No Job identity means the durable start barrier never opened. The
        # held wrapper is the only possible process, so ordinary wrapper
        # termination retains the established no-action recovery semantics.
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
    process.join(TERMINATION_GRACE_SEC)
    group_exists = (
        _uses_posix_process_groups() and _process_group_exists(process.pid)
    )
    if process.is_alive() or group_exists:
        if _uses_posix_process_groups():
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        if process.is_alive():
            if hasattr(process, "kill"):
                process.kill()
            else:  # pragma: no cover - old Python fallback
                process.terminate()
        deadline = time.monotonic() + TERMINATION_GRACE_SEC
        while process.is_alive() and time.monotonic() < deadline:
            process.join(min(0.05, max(0.0, deadline - time.monotonic())))
        if _uses_posix_process_groups():
            while (_process_group_exists(process.pid)
                   and time.monotonic() < deadline):
                time.sleep(0.01)
    group_exists = (
        _uses_posix_process_groups() and _process_group_exists(process.pid)
    )
    if process.is_alive() or group_exists:
        process_identity = _parent_process_identity(process)
        if action_may_have_started:
            if isinstance(known_process_identity, Mapping):
                process_identity = copy.deepcopy(dict(known_process_identity))
            process_identity["complete"] = False
            process_identity["action_may_have_started"] = True
        elif group_exists:
            process_identity["complete"] = True
        raise TriggerTerminationUnacknowledged(
            "Trigger action process group did not acknowledge termination",
            process_identity=process_identity,
        )


def _execute_action_with_deadline(
    action: Mapping[str, Any], binding: Mapping[str, Any], *, prepared,
    on_provider_contact: Callable[[], None] | None, timeout_sec: float,
    on_process_started: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict:
    """Run real action work across a boundary the deadline can terminate."""
    if timeout_sec <= 0:
        raise ValueError("Trigger firing timeout must be positive")
    if not _uses_posix_process_groups() and on_process_started is None:
        raise ValueError(
            "Windows Job execution requires a durable process-identity callback"
        )
    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=True)
    process = context.Process(
        target=_action_process_main,
        args=(child_connection, dict(action), dict(binding), True),
        daemon=True,
        name="ora-trigger-action",
    )
    process_identity: dict[str, Any] | None = None
    windows_job = None
    windows_job_termination_acknowledged = False
    action_start_acknowledged = False
    posix_timeout_after_start = False

    def persist_process_identity(identity: Mapping[str, Any]) -> None:
        nonlocal process_identity
        durable_identity = copy.deepcopy(dict(identity))
        process_identity = durable_identity
        if on_process_started is not None:
            on_process_started(durable_identity)

    try:
        # Include start itself in the cleanup boundary: a platform launcher
        # can create the OS process and then fail while finishing the parent
        # bookkeeping. If a pid exists, finally must still reap it.
        process.start()
        child_connection.close()
        deadline = time.monotonic() + timeout_sec
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                posix_timeout_after_start = (
                    _uses_posix_process_groups() and action_start_acknowledged
                )
                raise TimeoutError(
                    f"Trigger firing exceeded its {timeout_sec:g}s deadline"
                )
            if parent_connection.poll(min(remaining, 0.1)):
                try:
                    kind, payload = parent_connection.recv()
                except EOFError:
                    kind, payload = "closed", None
                if kind == "process_started":
                    if not isinstance(payload, Mapping):
                        raise RuntimeError(
                            "Trigger action returned an invalid process identity"
                        )
                    if _uses_posix_process_groups():
                        process_identity = copy.deepcopy(dict(payload))
                        admitted_identity = {
                            **process_identity,
                            # Persist this conservative marker before granting
                            # permission to cross the action-start barrier.
                            "complete": False,
                            "action_may_have_started": True,
                        }
                    else:
                        if windows_job is not None:
                            raise RuntimeError(
                                "Trigger action repeated its process-start barrier"
                            )
                        if process.pid is None:
                            raise RuntimeError(
                                "Trigger action has no Windows process id"
                            )
                        # The wrapper is blocked on this duplex message. Attach
                        # it to the repository's non-breakaway Job before any
                        # durable start acknowledgment can reach the child.
                        windows_job = _create_windows_job_boundary(process.pid)
                        admitted_identity = windows_job.identity(
                            action_may_have_started=True,
                        )
                    persist_process_identity(admitted_identity)
                    # Persistence is the last point at which the parent can
                    # still prove that no action work began. Once the ack is
                    # attempted it may have reached the child even if the
                    # local send reports an error, so every unwind from here
                    # must retain the conservative post-start Job identity.
                    action_start_acknowledged = True
                    parent_connection.send(("process_started_ack", None))
                    continue
                if kind == "provider_contact":
                    if on_provider_contact is not None:
                        on_provider_contact()
                    parent_connection.send(("provider_contact_ack", None))
                    continue
                if (
                    not _uses_posix_process_groups()
                    and windows_job is not None
                    and action_start_acknowledged
                ):
                    process_identity = _release_completed_windows_process(
                        process,
                        parent_connection,
                        windows_job,
                        on_process_identity=persist_process_identity,
                    )
                    windows_job_termination_acknowledged = True
                else:
                    process.join(TERMINATION_GRACE_SEC)
                    if process.is_alive():
                        raise RuntimeError(
                            "Trigger action returned without terminating"
                        )
                if kind == "result":
                    return payload
                if kind == "error":
                    raise TriggerError(str(payload))
                raise RuntimeError("Trigger action exited without a result")
            if not process.is_alive():
                process.join()
                raise RuntimeError(
                    f"Trigger action process exited with code {process.exitcode}"
                )
    finally:
        with contextlib.suppress(Exception):
            child_connection.close()
        try:
            # Keep the duplex connection open through cleanup. A post-start
            # Windows child waits on it while the parent snapshots and stops
            # the kernel-owned Job on every unwind.
            if process.pid is not None:
                group_exists = (
                    _uses_posix_process_groups()
                    and _process_group_exists(process.pid)
                )
                needs_windows_job_cleanup = (
                    windows_job is not None
                    and not windows_job_termination_acknowledged
                )
                if process.is_alive() or group_exists or needs_windows_job_cleanup:
                    try:
                        _terminate_action_process(
                            process,
                            on_process_identity=persist_process_identity,
                            windows_job=windows_job,
                            action_may_have_started=action_start_acknowledged,
                            known_process_identity=process_identity,
                        )
                    except TriggerTerminationUnacknowledged as exc:
                        retained_identity = exc.process_identity
                        if (
                            _uses_posix_process_groups()
                            and action_start_acknowledged
                        ):
                            if isinstance(process_identity, Mapping):
                                retained_identity = copy.deepcopy(
                                    dict(process_identity)
                                )
                            elif not isinstance(retained_identity, Mapping):
                                retained_identity = _parent_process_identity(process)
                            else:
                                retained_identity = copy.deepcopy(
                                    dict(retained_identity)
                                )
                            retained_identity["complete"] = False
                            retained_identity["action_may_have_started"] = True
                        if (
                            not (
                                _uses_posix_process_groups()
                                and action_start_acknowledged
                            )
                            and isinstance(process_identity, Mapping)
                            and (
                                not isinstance(retained_identity, Mapping)
                                or (
                                    process_identity.get("kind")
                                    == "windows_job_object"
                                    and retained_identity.get("kind")
                                    != "windows_job_object"
                                )
                                or (
                                    retained_identity.get("kind")
                                    != "windows_job_object"
                                    and retained_identity.get("complete") is not True
                                    and process_identity.get("complete") is True
                                )
                            )
                        ):
                            retained_identity = process_identity
                        raise TriggerTerminationUnacknowledged(
                            str(exc), process_identity=retained_identity,
                        ) from exc
                    except Exception as exc:
                        raise TriggerTerminationUnacknowledged(
                            "Trigger action termination could not be acknowledged",
                            process_identity=(
                                process_identity or _parent_process_identity(process)
                            ),
                        ) from exc
                else:
                    process.join()
                if posix_timeout_after_start:
                    retained_identity = (
                        copy.deepcopy(dict(process_identity))
                        if isinstance(process_identity, Mapping)
                        else _parent_process_identity(process)
                    )
                    retained_identity["complete"] = False
                    retained_identity["action_may_have_started"] = True
                    raise TriggerTerminationUnacknowledged(
                        f"Trigger firing exceeded its {timeout_sec:g}s deadline; "
                        "the known POSIX process group was terminated, but "
                        "descendant session escape cannot be excluded",
                        process_identity=retained_identity,
                    )
        finally:
            try:
                if windows_job is not None:
                    windows_job.close()
                    if process.pid is not None and process.is_alive():
                        process.join(TERMINATION_GRACE_SEC)
                    if process.pid is not None and process.is_alive():
                        raise RuntimeError(
                            "wrapper remained live after Job handle closure"
                        )
            except BaseException as exc:
                raise TriggerTerminationUnacknowledged(
                    "Windows Job ownership handle could not be closed",
                    process_identity=process_identity,
                ) from exc
            finally:
                parent_connection.close()
                if process.pid is not None and not process.is_alive():
                    close_process = getattr(process, "close", None)
                    if callable(close_process):
                        # ``join`` reaps the child; ``close`` releases the
                        # multiprocessing process handle on Windows.
                        with contextlib.suppress(Exception):
                            close_process()


def _execute_action(
    action: Mapping[str, Any], binding: Mapping[str, Any], *,
    prepared=None,
    on_provider_contact: Callable[[], None] | None = None,
) -> dict:
    """Run one already-authenticated unit of work and describe the result."""
    started = time.time()
    if action["kind"] == "project_tool":
        try:
            import project_registry as _pr
        except ImportError:  # pragma: no cover - package import context
            from orchestrator import project_registry as _pr
        kwargs: dict[str, Any] = {}
        if binding.get("interface") == _pr.TOOL_INTERFACE_STDIN_STDOUT:
            kwargs["stdin_json"] = action["stdin"] if "stdin" in action else {}
        else:
            kwargs["args"] = list(action.get("args") or [])
        result = _pr.invoke_project_tool(
            action["nexus"], action["tool"],
            expected_binding=dict(binding),
            **kwargs,
        )
        return {
            "outcome": "ran", "kind": "project_tool",
            "nexus": action["nexus"], "tool": action["tool"],
            "duration_seconds": round(time.time() - started, 3),
            "output_excerpt": _excerpt(result) if result is not None else "",
        }
    if action["kind"] == "framework":
        if prepared is None:
            current_binding, prepared = _resolve_framework_action_binding(action)
            if binding.get("trigger_id"):
                current_binding = {
                    **current_binding, "trigger_id": binding["trigger_id"],
                }
            if current_binding != dict(binding):
                raise TriggerConflict(
                    "action_definition_drifted before the action process started"
                )
        try:
            import milestone_executor as _me
            import pipeline_trace as _pt
            from boot import _run_visual_hook, load_routing_config
        except ImportError:  # pragma: no cover - package import context
            from orchestrator import milestone_executor as _me
            from orchestrator import pipeline_trace as _pt
            from orchestrator.boot import _run_visual_hook, load_routing_config
        trace_dir = _pt.start_trace(
            binding.get("trigger_id"), raw_input=action["input"],
            conversation_tag="trigger",
        )
        trace_status = "error"
        try:
            result = _me.execute_framework(
                binding["framework"], action["input"], load_routing_config(),
                project_nexus=action.get("project_nexus"),
                trace_dir=trace_dir,
                conversation_tag="trigger",
                input_context=dict(prepared.input_context),
                prepared=prepared,
            )
            if not getattr(result, "success", False):
                raise TriggerConflict(
                    f"framework {binding['framework']} failed: "
                    f"{getattr(result, 'failure_reason', 'no reason recorded')}"
                )
            visual_context = {
                "cleaned_prompt": action["input"],
                "execution_context": "autonomous",
                "framework_id": binding["framework"],
                "project_nexus": action.get("project_nexus"),
                "trace_dir": trace_dir,
            }
            final_output = _run_visual_hook(
                getattr(result, "final_output", ""),
                visual_context,
            )
            visual_outcome = visual_context.get("_visual_outcome")
            trace_status = (
                "error" if (visual_outcome or {}).get("state") == "failed"
                else "completed"
            )
        finally:
            _pt.finalize_manifest(
                trace_dir, kind="trigger-framework", status_hint=trace_status,
                framework_id=binding["framework"],
            )
        return {
            "outcome": "ran", "kind": "framework",
            "framework": binding["framework"],
            "execution_id": getattr(result, "execution_id", ""),
            "milestones": len(getattr(result, "milestones", []) or []),
            "duration_seconds": round(time.time() - started, 3),
            "output_excerpt": _excerpt(final_output),
            "visual_outcome": visual_outcome,
        }
    if action["kind"] == "email_send":
        try:
            try:
                from email_channel import send_trigger
            except ImportError:  # pragma: no cover - package import context
                from orchestrator.email_channel import send_trigger
            result = send_trigger(
                action, binding.get("trigger_id") or "",
                on_provider_contact=on_provider_contact,
            )
        except Exception:
            # The caller adds the Trigger id to the binding only for this
            # local dispatch seam. Keep the fallback explicit for direct
            # helper tests that call _execute_action with a bare binding.
            raise
        result["duration_seconds"] = round(time.time() - started, 3)
        return result
    raise TriggerInputRequired(f"unknown action kind {action['kind']!r}")


# ---------- module-level singleton ----------

_service: TriggerService | None = None
_service_lock = threading.Lock()


def service() -> TriggerService:
    """The process-shared service, so every surface writes one store."""
    global _service
    with _service_lock:
        if _service is None:
            _service = TriggerService()
        return _service


def available_actions() -> dict:
    """What a Trigger may be pointed at right now.

    The authoring form reads this so a tool or framework name cannot be
    mistyped into a Trigger that can never resolve.
    """
    tools = []
    try:
        try:
            import project_registry as _pr
        except ImportError:  # pragma: no cover - package import context
            from orchestrator import project_registry as _pr
        for project in _pr.list_projects():
            for name, tool in sorted(project.tools.items()):
                tools.append({
                    "nexus": project.nexus, "project_name": project.name,
                    "tool": name, "description": tool.description,
                    "interface": tool.interface,
                })
    except Exception as exc:
        print(f"[triggers] could not list project tools: {exc}")
    frameworks = []
    try:
        try:
            from framework_invocability import user_invocable_framework_ids
        except ImportError:  # pragma: no cover - package import context
            from orchestrator.framework_invocability import (
                user_invocable_framework_ids,
            )
        frameworks = user_invocable_framework_ids()
    except Exception as exc:
        print(f"[triggers] could not list frameworks: {exc}")
    return {
        "project_tools": tools,
        "frameworks": frameworks,
        # G1.21 intentionally exposes one channel action.  It is manual-only
        # and is created with an exact message payload, then inspected locally
        # before its first provider call.
        "channel_actions": [{
            "kind": "email_send", "provider": "fastmail",
            "cause": "manual",
            "description": "Send one exact, Persona-disclosed email via Fastmail/JMAP",
        }],
        "routine": _local_routine_descriptor(),
        "watch_roots": _watch_roots(),
        "intermittency": INTERMITTENCY_NOTICE,
    }


__all__ = [
    "ACTION_KINDS", "CAUSES", "DEADLINE_EVENT_TYPE", "FIRING_EVENT_TYPE",
    "INTERMITTENCY_NOTICE", "MIN_JUSTIFICATION_CHARS", "STATUSES",
    "TriggerConflict", "TriggerError", "TriggerInputRequired", "TriggerService",
    "available_actions", "next_occurrence", "normalize_spec",
    "resolve_action_binding", "service",
]
