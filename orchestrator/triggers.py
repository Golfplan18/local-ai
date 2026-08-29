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

_PROCESS_LOCK = threading.RLock()
#: trigger_id -> event_id of the firing currently executing in this process.
_RUNNING: dict[str, str] = {}


class TriggerError(RuntimeError):
    """Base class for a rejected Trigger operation."""


class TriggerInputRequired(TriggerError):
    """The request lacks a valid exact input."""


class TriggerConflict(TriggerError):
    """The request conflicts with durable Trigger state."""


# ── small helpers ────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


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
        command = _pr._resolve_command(project, tool.command)
        return {
            "kind": kind,
            "nexus": project.nexus,
            "tool": tool.name,
            "interface": tool.interface,
            "command": list(command),
            "command_digest": _digest(list(command)),
        }
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


def _record_view(record: Mapping[str, Any], *, firings: list | None = None) -> dict:
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
    }
    if spec["cause"] == "calendar" and record.get("status") == "active":
        view["next_due_at"] = record.get("next_due_at")
    if firings is not None:
        view["firings"] = firings
    return view


def _resolution_note(spec: Mapping[str, Any]) -> str:
    """A one-line, human-readable description of what will run."""
    action = spec["action"]
    if action["kind"] == "project_tool":
        args = " ".join(action.get("args") or [])
        return f"project tool {action['nexus']}:{action['tool']} {args}".strip()
    if action["kind"] == "email_send":
        return (f"email via Fastmail to {', '.join(action['to'])}: "
                f"{action['subject']}")
    return f"framework {action['framework']}"


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
            records = list(_load()["triggers"].values())
        # One ledger read for the whole listing. Reading it per Trigger meant
        # re-parsing a multi-megabyte state file once per card on every poll.
        ledger_rows = self.ledger.list_events(event_type=FIRING_EVENT_TYPE)
        views = []
        for record in sorted(records, key=lambda item: item["spec"]["trigger_id"]):
            if not include_retired and record.get("status") == "retired":
                continue
            views.append(_record_view(record, firings=self._firing_rows(
                ledger_rows, record["spec"]["trigger_id"], limit=1)))
        return views

    def get(self, trigger_id: str, *, firing_limit: int = 25) -> dict:
        record = self._require(_safe_id(trigger_id, "trigger_id"))
        return _record_view(record, firings=self.firings(
            record["spec"]["trigger_id"], limit=firing_limit))

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
            rows.append({
                "event_id": record.get("event_id"),
                "trigger_id": subject.get("trigger_id"),
                "cause": subject.get("cause"),
                "source": subject.get("source"),
                "status": status,
                "outcome": receipt.get("outcome") or (
                    "running" if status == "claimed" else status),
                "claimed_at": record.get("claimed_at"),
                "finished_at": record.get("completed_at") or record.get("updated_at"),
                "receipt": receipt or None,
                "error": record.get("error"),
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
        return _record_view(record, firings=self.firings(trigger_id, limit=5))

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
        """The exact rendered request a human approves before deployment."""
        record = self._require(_safe_id(trigger_id, "trigger_id"))
        spec = record["spec"]
        binding = resolve_action_binding(spec["action"])
        return {
            "trigger_id": spec["trigger_id"],
            "name": spec["name"],
            "spec_digest": _digest(spec),
            "cause": spec["cause"],
            "condition": copy.deepcopy(spec["condition"]),
            "will_run": _resolution_note(spec),
            "action_binding": binding,
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
            digest = _digest(spec)
            if expected_spec_digest != digest:
                raise TriggerConflict(
                    "the Trigger changed since it was reviewed; re-read it and "
                    "approve the current specification"
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
            binding = resolve_action_binding(spec["action"])
            record.update({
                "status": "active", "activated_at": _now(),
                "approved_spec_digest": digest, "approved_action_binding": binding,
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

        The payload carries no specification digest. The handler reloads the
        current Trigger and re-authenticates at dispatch, so an edit can never
        collide with an already-bound immutable deadline contract.
        """
        record = self._require(trigger_id)
        spec = record["spec"]
        if spec["cause"] != "calendar" or record.get("status") != "active":
            return None
        moment = after or datetime.now(timezone.utc)
        due = next_occurrence(spec["condition"]["schedule"], moment)
        key = f"trigger:{trigger_id}:{due.isoformat()}"
        self.queue.put(key, due.isoformat(), DEADLINE_EVENT_TYPE, {
            "trigger_id": trigger_id,
            "scheduled_for": normalized_instant(due.isoformat()),
            "timezone": spec["condition"]["schedule"]["timezone"],
        })
        with _PROCESS_LOCK, _exclusive():
            state = _load()
            current = state["triggers"].get(trigger_id)
            still_active = (current is not None
                            and current.get("status") == "active")
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
        return self._fire(record, "manual", {"request_id": request})

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
                record = self._require(spec["trigger_id"])
                firing = self._fire(record, "file_change", {
                    "paths": [_bound_identity(path) for path in matched],
                })
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
        record = self._require(trigger_id)
        spec = record["spec"]
        try:
            if spec["cause"] != "calendar":
                return {"outcome": "stale",
                        "detail": "Trigger is no longer a calendar Trigger"}
            if record.get("status") != "active":
                return {"outcome": "stale",
                        "detail": f"Trigger is {record.get('status')}"}
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
                })
                return {"outcome": "skipped", "event_id": firing.get("event_id"),
                        "late_by_seconds": int(late_by)}
            firing = self._fire(record, "calendar", {
                "scheduled_for": scheduled_for,
            }, extra_receipt={"late_by_seconds": int(max(0.0, late_by))})
            return {"outcome": "dispatched", "event_id": firing.get("event_id"),
                    "late_by_seconds": int(max(0.0, late_by))}
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
              extra_receipt: dict | None = None) -> dict:
        """Claim one firing in the shared ledger, then run it off-lane."""
        ledger = self.ledger
        with _PROCESS_LOCK:
            # Re-read under the same lock used by rollback.  The caller's
            # earlier view may have been retired while it was preparing this
            # firing, and must not be allowed to mint a claim afterward.
            trigger_id = record["spec"]["trigger_id"]
            current = self._require(trigger_id)
            if current.get("status") == "retired":
                raise TriggerConflict("a retired Trigger cannot be fired")
            spec = current["spec"]
            framework_binding = None
            framework_prepared = None
            if spec["action"]["kind"] == "framework":
                # Resolve and compare the exact composed contract before a
                # firing claim exists.  The same in-memory snapshot is handed
                # to execution; neither step rereads the Framework.
                framework_binding, framework_prepared = (
                    _resolve_framework_action_binding(spec["action"])
                )
                if current.get("status") == "active":
                    if current.get("approved_spec_digest") != _digest(spec):
                        raise TriggerConflict(
                            "the approved specification no longer matches this "
                            "Trigger; re-review and re-activate it"
                        )
                    approved = current.get("approved_action_binding")
                    if approved != framework_binding:
                        raise TriggerConflict(
                            "action_definition_drifted: what this Trigger would run "
                            "has changed since it was approved. Re-review and "
                            "re-activate it."
                        )
            subject = {
                "trigger_id": trigger_id,
                "spec_digest": _digest(spec),
                "cause": cause,
                "source": copy.deepcopy(dict(source)),
            }
            event_id = event_identity(FIRING_EVENT_TYPE, subject)
            claim, created = ledger.claim(
                event_id=event_id, event_type=FIRING_EVENT_TYPE, subject=subject)
            if not created:
                return {"event_id": event_id, "status": claim.get("status"),
                        "duplicate": True}
            if forced_receipt is not None:
                ledger.transition(event_id, {"claimed"}, "completed",
                                  receipt=forced_receipt, completed_at=_now())
                return {"event_id": event_id, "status": "completed",
                        "receipt": forced_receipt}
            already = _RUNNING.get(trigger_id)
            if already:
                receipt = {
                    "outcome": "skipped",
                    "reason": "a firing for this Trigger is already running",
                    "blocking_event_id": already,
                }
                ledger.transition(event_id, {"claimed"}, "completed",
                                  receipt=receipt, completed_at=_now())
                return {"event_id": event_id, "status": "completed",
                        "receipt": receipt}
            _RUNNING[trigger_id] = event_id
        self._executor(lambda: self._execute(
            trigger_id, event_id, extra_receipt=extra_receipt,
            framework_binding=framework_binding,
            framework_prepared=framework_prepared,
            claimed_spec_digest=_digest(spec),
        ))
        return {"event_id": event_id, "status": "claimed"}

    def _execute(self, trigger_id: str, event_id: str, *,
                 extra_receipt: dict | None = None,
                 framework_binding: dict | None = None,
                 framework_prepared=None,
                 claimed_spec_digest: str | None = None) -> None:
        ledger = self.ledger
        try:
            record = self._require(trigger_id)
            spec = record["spec"]
            if claimed_spec_digest and _digest(spec) != claimed_spec_digest:
                raise TriggerConflict(
                    "the Trigger specification changed after its firing was claimed"
                )
            binding = (
                framework_binding
                if framework_binding is not None
                else resolve_action_binding(spec["action"])
            )
            approved = record.get("approved_action_binding")
            if record.get("status") == "active":
                if record.get("approved_spec_digest") != _digest(spec):
                    raise TriggerConflict(
                        "the approved specification no longer matches this "
                        "Trigger; re-review and re-activate it"
                    )
                if approved and approved != binding:
                    raise TriggerConflict(
                        "action_definition_drifted: what this Trigger would run "
                        "has changed since it was approved. Re-review and "
                        "re-activate it."
                    )
            # The Trigger identity scopes the email approval request but is
            # not part of the provider binding digest itself.
            if spec["action"]["kind"] in {"email_send", "framework"}:
                binding = {**binding, "trigger_id": trigger_id}
            on_provider_contact = lambda: ledger.transition(
                event_id, {"claimed"}, "claimed",
                receipt={"outcome": "sending", "provider_contacted": True},
                provider_contacted=True,
            )
            if self._terminate_actions:
                receipt = _execute_action_with_deadline(
                    spec["action"], binding,
                    prepared=framework_prepared,
                    on_provider_contact=on_provider_contact,
                    timeout_sec=self._firing_timeout_sec,
                )
            else:
                receipt = _execute_action(
                    spec["action"], binding,
                    prepared=framework_prepared,
                    on_provider_contact=on_provider_contact,
                )
            if extra_receipt:
                receipt.update(extra_receipt)
            self._stage_completion_deliveries(trigger_id, event_id)
            completed = ledger.transition(
                event_id, {"claimed"}, "completed",
                receipt=receipt, completed_at=_now(),
            )
            self._dispatch_completion(
                trigger_id, event_id, source_completion=completed,
            )
        except BaseException as exc:
            # Record before anything else: a firing that dies without evidence
            # is indistinguishable from one that never ran.
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
            with _PROCESS_LOCK:
                if _RUNNING.get(trigger_id) == event_id:
                    _RUNNING.pop(trigger_id, None)

    def _stage_completion_deliveries(self, source_trigger_id: str,
                                     source_event_id: str) -> None:
        """Persist exact dependant deliveries before exposing completion."""
        with _PROCESS_LOCK, _exclusive():
            state = _load()
            source_record = state["triggers"].get(source_trigger_id)
            if source_record is None:
                raise TriggerConflict(
                    f"completion source {source_trigger_id!r} no longer exists"
                )
            source_spec_digest = _digest(source_record["spec"])
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
                }
                delivery_id = event_identity("trigger_completion_delivery", subject)
                if delivery_id in state["completion_deliveries"]:
                    continue
                state["completion_deliveries"][delivery_id] = {
                    "delivery_id": delivery_id,
                    **subject,
                    "source_event_type": FIRING_EVENT_TYPE,
                    "source_spec_digest": source_spec_digest,
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

    def _deliver_completion(self, delivery: Mapping[str, Any]) -> None:
        target = str(delivery["dependent_trigger_id"])
        record = self._require(target)
        spec = record["spec"]
        if record.get("status") != "active" or _digest(spec) != delivery.get(
            "dependent_spec_digest"
        ):
            raise TriggerConflict(
                f"completion delivery target {target!r} changed after publication"
            )
        self._fire(record, "trigger_completion", {
            "source_trigger_id": delivery["source_trigger_id"],
            "source_event_id": delivery["source_event_id"],
        })
        self._finish_completion_delivery(str(delivery["delivery_id"]))

    def _dispatch_completion(
        self, source_trigger_id: str, source_event_id: str, *,
        source_completion: Mapping[str, Any] | None = None,
    ) -> None:
        """Persist completion eligibility, then deliver each dependant."""
        if source_completion is not None:
            source_subject = source_completion.get("subject") or {}
            proof = {
                "event_id": source_completion.get("event_id"),
                "event_type": source_completion.get("event_type"),
                "trigger_id": source_subject.get("trigger_id"),
                "spec_digest": source_subject.get("spec_digest"),
                "completed_at": source_completion.get("completed_at"),
            }
            if (source_completion.get("status") != "completed"
                    or proof["event_id"] != source_event_id
                    or proof["event_type"] != FIRING_EVENT_TYPE
                    or proof["trigger_id"] != source_trigger_id
                    or not proof["spec_digest"]
                    or not proof["completed_at"]):
                raise TriggerConflict(
                    "completion delivery requires a completed source firing"
                )
            with _PROCESS_LOCK, _exclusive():
                state = _load()
                changed = False
                for delivery in state["completion_deliveries"].values():
                    if delivery.get("source_event_id") == source_event_id:
                        delivery["source_completion"] = proof
                        changed = True
                if changed:
                    _save(state)
        for delivery in self._pending_completion_deliveries(source_event_id):
            try:
                self._deliver_completion(delivery)
            except Exception as exc:
                print(f"[triggers] completion dispatch to "
                      f"{delivery.get('dependent_trigger_id')} failed: {exc}")

    def replay_completion_deliveries(self) -> list[str]:
        """Replay each unfinished dependant delivery once at process startup."""
        delivered: list[str] = []
        for delivery in self._pending_completion_deliveries():
            source_event_id = str(delivery.get("source_event_id") or "")
            proof = delivery.get("source_completion")
            source_completed = (
                isinstance(proof, dict)
                and proof.get("event_id") == source_event_id
                and proof.get("event_type") == FIRING_EVENT_TYPE
                and proof.get("trigger_id") == delivery.get("source_trigger_id")
                and proof.get("spec_digest") == delivery.get(
                    "source_spec_digest"
                )
                and bool(proof.get("completed_at"))
            )
            source = None if source_completed else self.ledger.get(source_event_id)
            if not source_completed and (
                source is None or source.get("status") != "completed"
            ):
                if source is not None and source.get("status") == "failed":
                    self._finish_completion_delivery(str(delivery["delivery_id"]))
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
    The thread is a daemon and never outlives the process — a firing killed by
    shutdown is failed by ``restore_incomplete_events`` at the next start, and
    is terminal, because a failed event is not retried by a clock.
    """
    threading.Thread(target=work, daemon=True, name="ora-trigger-firing").start()


def _action_process_main(connection, action: dict, binding: dict) -> None:
    """Process-side action entry point; reports provider contact and outcome."""
    if os.name == "posix":
        os.setsid()
        if action.get("kind") == "project_tool":
            # The project tool is a child process in this group. Let it
            # acknowledge SIGTERM and let invoke_project_tool reap it before
            # this supervisor exits; exec resets this caught handler to the
            # default disposition in the tool itself.
            signal.signal(signal.SIGTERM, lambda *_args: None)
    try:
        receipt = _execute_action(
            action, binding, prepared=None,
            on_provider_contact=lambda: connection.send(
                ("provider_contact", None)
            ),
        )
        connection.send(("result", receipt))
    except BaseException as exc:
        with contextlib.suppress(Exception):
            connection.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        connection.close()


def _terminate_action_process(process) -> None:
    """Terminate the whole action process group and wait for acknowledgment."""
    if process.pid is None:
        return
    if os.name == "posix":
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
        # If the child had not reached setsid yet, there was no process group
        # to signal. Terminating the wrapper still closes that startup race.
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
    else:  # pragma: no cover - exercised at the Windows release checkpoint
        with contextlib.suppress(OSError):
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True, check=False,
            )
    process.join(TERMINATION_GRACE_SEC)
    if process.is_alive():
        if os.name == "posix":
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        elif hasattr(process, "kill"):
            process.kill()
        else:  # pragma: no cover - old Python fallback
            process.terminate()
        process.join()
    if process.is_alive():
        raise RuntimeError("Trigger action did not acknowledge termination")


def _execute_action_with_deadline(
    action: Mapping[str, Any], binding: Mapping[str, Any], *, prepared,
    on_provider_contact: Callable[[], None] | None, timeout_sec: float,
) -> dict:
    """Run real action work across a boundary the deadline can terminate."""
    if timeout_sec <= 0:
        raise ValueError("Trigger firing timeout must be positive")
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(
        target=_action_process_main,
        args=(send, dict(action), dict(binding)),
        daemon=True,
        name="ora-trigger-action",
    )
    try:
        # Include start itself in the cleanup boundary: a platform launcher
        # can create the OS process and then fail while finishing the parent
        # bookkeeping. If a pid exists, finally must still reap it.
        process.start()
        send.close()
        deadline = time.monotonic() + timeout_sec
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _terminate_action_process(process)
                raise TimeoutError(
                    f"Trigger firing exceeded its {timeout_sec:g}s deadline"
                )
            if receive.poll(min(remaining, 0.1)):
                try:
                    kind, payload = receive.recv()
                except EOFError:
                    kind, payload = "closed", None
                if kind == "provider_contact":
                    if on_provider_contact is not None:
                        on_provider_contact()
                    continue
                process.join(TERMINATION_GRACE_SEC)
                if process.is_alive():
                    _terminate_action_process(process)
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
            send.close()
        receive.close()
        # No parent-side failure may release TriggerService._RUNNING while
        # action work still exists. This covers callback errors and all other
        # exceptions outside the explicit timeout/result branches.
        if process.pid is not None:
            if process.is_alive():
                _terminate_action_process(process)
            else:
                process.join()


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
            kwargs["stdin_json"] = action.get("stdin") or {}
        else:
            kwargs["args"] = list(action.get("args") or [])
        result = _pr.invoke_project_tool(action["nexus"], action["tool"], **kwargs)
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
