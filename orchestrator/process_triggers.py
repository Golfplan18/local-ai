"""G1.19 durable Trigger Manager over governed Process Automation.

A Trigger is a separately authorized activation object.  It never modifies a
Process Definition and it never executes work itself: every firing is bound to
one exact promoted definition and enters the accepted G1.18/G1.20 Run path.

Time is allowed only when passage of time is the declared input and the spec
contains the written Runtime-Principle justification.  The clock driver is
app-managed and explicitly intermittent; there is no cron/launchd fallback.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    import runtime_paths as _runtime_paths
    from active_project import canonicalize_project_nexus
    from process_automation import ProcessAutomationService
except ImportError:  # pragma: no cover - package import context
    from orchestrator import runtime_paths as _runtime_paths
    from orchestrator.active_project import canonicalize_project_nexus
    from orchestrator.process_automation import ProcessAutomationService


TRIGGER_SCHEMA_VERSION = "ora.process-trigger/1.0"
TRIGGER_RECORD_SCHEMA_VERSION = "ora.process-trigger-record/1.0"
TRIGGER_KINDS = frozenset({"manual", "event", "inbound", "time"})
EVENT_TYPES = frozenset({"file_change", "framework_completion", "milestone_check_in"})
_ID_RE = re.compile(r"[a-z0-9][a-z0-9._:-]{0,255}")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
_process_lock = threading.RLock()
_lock_state = threading.local()


class ProcessTriggerError(RuntimeError):
    """Base class for a rejected Trigger operation."""


class ProcessTriggerInputRequired(ProcessTriggerError):
    """The request lacks a valid exact input or explicit decision."""


class ProcessTriggerConflict(ProcessTriggerError):
    """The requested operation conflicts with durable Trigger state."""


class ProcessTriggerIntegrityError(ProcessTriggerError):
    """Persisted Trigger identity or lineage does not authenticate."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _safe_id(value: Any, label: str) -> str:
    exact = str(value or "").strip().lower()
    if not _ID_RE.fullmatch(exact):
        raise ProcessTriggerInputRequired(f"{label} must be a stable lowercase identifier")
    return exact


def _safe_text(value: Any, label: str, *, limit: int = 4000) -> str:
    exact = " ".join(str(value or "").split())
    if not exact or len(exact) > limit:
        raise ProcessTriggerInputRequired(f"{label} must contain 1-{limit} characters")
    return exact


def _exact_ref(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"definition_id", "version", "digest"}:
        raise ProcessTriggerInputRequired(
            "definition_ref must contain exact definition_id, version, and digest"
        )
    result = {
        "definition_id": str(value["definition_id"] or "").strip(),
        "version": str(value["version"] or "").strip(),
        "digest": str(value["digest"] or "").strip(),
    }
    if not result["definition_id"] or not result["version"] or not _DIGEST_RE.fullmatch(result["digest"]):
        raise ProcessTriggerInputRequired("definition_ref values do not form an exact identity")
    return result


def _parse_instant(value: Any, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ProcessTriggerInputRequired(f"{label} must be an ISO-8601 instant") from exc
    if parsed.tzinfo is None:
        raise ProcessTriggerInputRequired(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _write_json(path: Path, value: Any) -> None:
    _runtime_paths.atomic_write_text(
        path, json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    )


def _read_json(path: Path) -> Any:
    if not path.is_file() or path.is_symlink():
        raise ProcessTriggerIntegrityError(f"Trigger storage is missing or unsafe: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProcessTriggerIntegrityError(f"Trigger storage is unreadable: {path}") from exc


def _validate_runtime_principle(raw: Any) -> dict[str, str]:
    required = {
        "declared_cause", "runtime_impossibility", "runtime_alternative",
        "availability_boundary", "no_clock_fallback",
    }
    if not isinstance(raw, Mapping) or set(raw) != required:
        raise ProcessTriggerInputRequired(
            "time triggers require the complete written Runtime-Principle justification"
        )
    result = {key: _safe_text(raw[key], f"runtime_principle.{key}") for key in required}
    if result["declared_cause"] != "passage of time is the declared input":
        raise ProcessTriggerInputRequired("time must itself be the declared Process input")
    if len(result["runtime_impossibility"]) < 40:
        raise ProcessTriggerInputRequired("runtime impossibility requires a substantive written reason")
    if result["runtime_alternative"] != "no runtime event can represent passage of time":
        raise ProcessTriggerInputRequired("a viable runtime event must be used instead of a clock")
    if result["availability_boundary"] != "only while ora is running":
        raise ProcessTriggerInputRequired("time availability must disclose app intermittency")
    if result["no_clock_fallback"] != "no cron, launchd, or deferred sweep fallback":
        raise ProcessTriggerInputRequired("time triggers may not install a clock fallback")
    return result


def _validate_schedule(raw: Any) -> dict[str, Any]:
    allowed = {
        "timezone", "local_time", "cadence", "weekdays", "start_date",
        "missed_policy", "grace_seconds",
    }
    if not isinstance(raw, Mapping) or set(raw) - allowed:
        raise ProcessTriggerInputRequired("schedule fields are invalid")
    timezone_name = str(raw.get("timezone") or "").strip()
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ProcessTriggerInputRequired("schedule timezone must be a named IANA timezone") from exc
    local_time = str(raw.get("local_time") or "")
    try:
        time.fromisoformat(local_time)
    except ValueError as exc:
        raise ProcessTriggerInputRequired("schedule local_time must be HH:MM or HH:MM:SS") from exc
    cadence = str(raw.get("cadence") or "")
    if cadence not in {"daily", "weekly"}:
        raise ProcessTriggerInputRequired("schedule cadence must be daily or weekly")
    weekdays = sorted(set(raw.get("weekdays") or []))
    if cadence == "weekly" and (not weekdays or any(type(day) is not int or day < 0 or day > 6 for day in weekdays)):
        raise ProcessTriggerInputRequired("weekly schedules require weekday integers 0-6")
    if cadence == "daily" and weekdays:
        raise ProcessTriggerInputRequired("daily schedules may not declare weekdays")
    try:
        date.fromisoformat(str(raw.get("start_date") or ""))
    except ValueError as exc:
        raise ProcessTriggerInputRequired("schedule start_date must be YYYY-MM-DD") from exc
    missed = str(raw.get("missed_policy") or "")
    if missed not in {"run_once", "skip"}:
        raise ProcessTriggerInputRequired("schedule missed_policy must be run_once or skip")
    grace = raw.get("grace_seconds", 300)
    if type(grace) is not int or grace < 0 or grace > 86400:
        raise ProcessTriggerInputRequired("schedule grace_seconds must be an integer from 0 to 86400")
    return {
        "timezone": timezone_name,
        "local_time": local_time,
        "cadence": cadence,
        "weekdays": weekdays,
        "start_date": str(raw["start_date"]),
        "missed_policy": missed,
        "grace_seconds": grace,
    }


def _normalize_path_selector(value: Any) -> str:
    text = str(value or "").strip()
    if not text or "\x00" in text:
        raise ProcessTriggerInputRequired("file-change selector is invalid")
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ProcessTriggerInputRequired("file-change selectors must be absolute")
    return str(path.resolve())


def _validate_condition(kind: str, raw: Any) -> dict[str, Any]:
    condition = copy.deepcopy(dict(raw or {})) if isinstance(raw, Mapping) else None
    if condition is None:
        raise ProcessTriggerInputRequired("condition must be an object")
    if kind == "manual":
        if condition:
            raise ProcessTriggerInputRequired("manual triggers do not accept a condition")
        return {}
    if kind == "inbound":
        if set(condition) != {"channel", "source_scope"}:
            raise ProcessTriggerInputRequired("inbound condition requires channel and source_scope")
        channel = str(condition["channel"] or "")
        if channel not in {"email", "telegram"}:
            raise ProcessTriggerInputRequired("inbound channel must be email or telegram")
        return {"channel": channel, "source_scope": _safe_text(condition["source_scope"], "source_scope")}
    event_type = str(condition.get("event_type") or "")
    if kind == "event" and event_type == "file_change":
        if set(condition) != {"event_type", "path_selectors"}:
            raise ProcessTriggerInputRequired("file-change condition fields are invalid")
        selectors = sorted({_normalize_path_selector(item) for item in condition["path_selectors"]})
        if not selectors:
            raise ProcessTriggerInputRequired("file-change requires an exact path or directory selector")
        return {"event_type": event_type, "path_selectors": selectors}
    if kind == "event" and event_type == "framework_completion":
        if set(condition) != {"event_type", "source_definition_ref"}:
            raise ProcessTriggerInputRequired("framework-completion condition fields are invalid")
        return {"event_type": event_type, "source_definition_ref": _exact_ref(condition["source_definition_ref"])}
    if kind == "time" and event_type in {"milestone_check_in", "time"}:
        if set(condition) != {"event_type", "schedule"}:
            raise ProcessTriggerInputRequired("time condition fields are invalid")
        return {"event_type": event_type, "schedule": _validate_schedule(condition["schedule"])}
    raise ProcessTriggerInputRequired("trigger kind and condition event_type do not agree")


def _validate_bindings(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, Mapping):
        raise ProcessTriggerInputRequired("input_bindings must be an object")
    result: dict[str, dict[str, Any]] = {}
    for field, binding in raw.items():
        key = _safe_id(field, "input field")
        if not isinstance(binding, Mapping):
            raise ProcessTriggerInputRequired(f"input binding {key} must be an object")
        source = str(binding.get("source") or "")
        if source == "literal" and set(binding) == {"source", "value"}:
            result[key] = {"source": source, "value": copy.deepcopy(binding["value"])}
        elif source in {
            "changed_paths", "changed_artifacts", "source_path", "source_run_id",
            "source_result", "project_snapshot",
        } and set(binding) == {"source"}:
            result[key] = {"source": source}
        else:
            raise ProcessTriggerInputRequired(f"input binding {key} uses an unsupported source")
    return result


def normalize_trigger_spec(raw: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "trigger_id", "name", "definition_ref", "project_ref", "kind",
        "condition", "input_bindings", "principal_id",
    }
    optional = {"runtime_principle", "process_profile", "step_profiles", "style_profile"}
    if not isinstance(raw, Mapping) or set(raw) - required - optional or required - set(raw):
        raise ProcessTriggerInputRequired("Trigger specification fields are invalid")
    kind = str(raw["kind"] or "")
    if kind not in TRIGGER_KINDS:
        raise ProcessTriggerInputRequired("kind must be manual, event, inbound, or time")
    project_ref = canonicalize_project_nexus(str(raw["project_ref"] or ""))
    if not project_ref:
        raise ProcessTriggerInputRequired("project_ref is required")
    runtime_principle = None
    if kind == "time":
        runtime_principle = _validate_runtime_principle(raw.get("runtime_principle"))
    elif raw.get("runtime_principle") is not None:
        raise ProcessTriggerInputRequired("only time triggers accept a Runtime-Principle justification")
    step_profiles = raw.get("step_profiles") or {}
    if not isinstance(step_profiles, Mapping):
        raise ProcessTriggerInputRequired("step_profiles must be an object")
    return {
        "schema_version": TRIGGER_SCHEMA_VERSION,
        "trigger_id": _safe_id(raw["trigger_id"], "trigger_id"),
        "name": _safe_text(raw["name"], "name", limit=200),
        "definition_ref": _exact_ref(raw["definition_ref"]),
        "project_ref": project_ref,
        "kind": kind,
        "condition": _validate_condition(kind, raw["condition"]),
        "input_bindings": _validate_bindings(raw["input_bindings"]),
        "principal_id": _safe_id(raw["principal_id"], "principal_id"),
        "runtime_principle": runtime_principle,
        "process_profile": (str(raw.get("process_profile") or "").strip() or None),
        "step_profiles": copy.deepcopy(dict(step_profiles)),
        "style_profile": (str(raw.get("style_profile") or "").strip() or None),
    }


def _local_occurrence(local_day: date, local_value: str, zone: ZoneInfo) -> datetime:
    wall = datetime.combine(local_day, time.fromisoformat(local_value))
    candidate = wall.replace(tzinfo=zone, fold=0)
    # A spring-forward wall time may not exist. Advance to the first real local
    # instant so calendar intent is preserved without retaining a stale offset.
    for _ in range(181):
        round_trip = candidate.astimezone(timezone.utc).astimezone(zone)
        if round_trip.replace(tzinfo=None) == candidate.replace(tzinfo=None):
            return candidate.astimezone(timezone.utc)
        candidate += timedelta(minutes=1)
    raise ProcessTriggerIntegrityError("could not resolve calendar occurrence")


def _occurrences(schedule: Mapping[str, Any], after: datetime, through: datetime) -> list[datetime]:
    zone = ZoneInfo(str(schedule["timezone"]))
    local_after = after.astimezone(zone).date()
    start = date.fromisoformat(str(schedule["start_date"]))
    day = max(start, local_after - timedelta(days=1))
    end = through.astimezone(zone).date() + timedelta(days=1)
    found: list[datetime] = []
    while day <= end:
        selected = schedule["cadence"] == "daily" or day.weekday() in schedule["weekdays"]
        if selected:
            instant = _local_occurrence(day, str(schedule["local_time"]), zone)
            if after < instant <= through:
                found.append(instant)
        day += timedelta(days=1)
    return sorted(found)


class ProcessTriggerService:
    """Authenticated Trigger definitions, lifecycle, dispatch, and recovery."""

    def __init__(
        self,
        *,
        root: str | Path | None = None,
        automation: ProcessAutomationService | None = None,
        now: Callable[[], str] | None = None,
        vault: str | Path | None = None,
        sessions_root: str | Path | None = None,
    ) -> None:
        self.root = Path(root or (Path(_runtime_paths.DATA_DIR_STR) / "process-triggers")).expanduser().resolve()
        self.definitions = self.root / "definitions"
        self.anchors = self.root / "anchors"
        self.records = self.root / "records"
        self.lock_path = self.root / "ledger"
        self.automation = automation or ProcessAutomationService()
        # The generic automation service cannot mint a standing-Trigger Run.
        # Only this service installs the ledger authenticator used by its
        # dedicated begin_triggered_run boundary.
        self.automation.trigger_authenticator = self.authenticate_firing
        self._now = now or _utc_now
        self.vault = Path(vault or _runtime_paths.VAULT_STR).expanduser().resolve()
        self.sessions_root = Path(sessions_root or _runtime_paths.CONVERSATIONS_STR).expanduser().resolve()

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise ProcessTriggerIntegrityError("Trigger root may not be a symlink")
        for directory in (self.definitions, self.anchors, self.records):
            directory.mkdir(exist_ok=True)
            if directory.is_symlink():
                raise ProcessTriggerIntegrityError("Trigger storage directories may not be symlinks")

    @contextmanager
    def _locked(self):
        with _process_lock:
            self._ensure_root()
            depth = int(getattr(_lock_state, "depth", 0))
            if depth:
                _lock_state.depth = depth + 1
                try:
                    yield
                finally:
                    _lock_state.depth = depth
                return
            try:
                with _runtime_paths.locked_file(self.lock_path):
                    _lock_state.depth = 1
                    yield
            finally:
                _lock_state.depth = 0

    @staticmethod
    def _storage_key(trigger_id: str) -> str:
        return hashlib.sha256(trigger_id.encode("utf-8")).hexdigest()

    def _paths(self, trigger_id: str) -> tuple[Path, Path, Path]:
        key = self._storage_key(_safe_id(trigger_id, "trigger_id"))
        return self.definitions / f"{key}.json", self.anchors / f"{key}.json", self.records / f"{key}.json"

    def _load_spec(self, trigger_id: str) -> tuple[dict[str, Any], str]:
        definition_path, anchor_path, _ = self._paths(trigger_id)
        envelope = _read_json(definition_path)
        anchor = _read_json(anchor_path)
        if not isinstance(envelope, Mapping) or set(envelope) != {"spec", "spec_digest"}:
            raise ProcessTriggerIntegrityError("Trigger definition envelope is malformed")
        try:
            spec = normalize_trigger_spec({key: value for key, value in envelope["spec"].items() if key != "schema_version"})
        except (AttributeError, ProcessTriggerError) as exc:
            raise ProcessTriggerIntegrityError("Trigger definition does not validate") from exc
        digest = _digest_json(spec)
        expected_anchor = {
            "schema_version": TRIGGER_SCHEMA_VERSION,
            "trigger_id": spec["trigger_id"],
            "spec_digest": digest,
        }
        if envelope["spec"] != spec or envelope["spec_digest"] != digest or anchor != expected_anchor:
            raise ProcessTriggerIntegrityError("Trigger definition identity does not authenticate")
        if spec["trigger_id"] != _safe_id(trigger_id, "trigger_id"):
            raise ProcessTriggerIntegrityError("Trigger storage key resolved to another identity")
        return spec, digest

    def _load_records(self, trigger_id: str) -> list[dict[str, Any]]:
        _, _, path = self._paths(trigger_id)
        if not path.exists():
            return []
        raw = _read_json(path)
        if not isinstance(raw, list):
            raise ProcessTriggerIntegrityError("Trigger record ledger is malformed")
        prior = None
        validated: list[dict[str, Any]] = []
        for sequence, record in enumerate(raw, 1):
            if not isinstance(record, Mapping):
                raise ProcessTriggerIntegrityError("Trigger record is malformed")
            body = {key: copy.deepcopy(value) for key, value in record.items() if key != "record_digest"}
            if (
                body.get("schema_version") != TRIGGER_RECORD_SCHEMA_VERSION
                or body.get("sequence") != sequence
                or body.get("prior_record_digest") != prior
                or record.get("record_digest") != _digest_json(body)
            ):
                raise ProcessTriggerIntegrityError("Trigger record chain does not authenticate")
            prior = str(record["record_digest"])
            validated.append(copy.deepcopy(dict(record)))
        return validated

    def _append(self, trigger_id: str, event_type: str, details: Mapping[str, Any]) -> dict[str, Any]:
        records = self._load_records(trigger_id)
        body = {
            "schema_version": TRIGGER_RECORD_SCHEMA_VERSION,
            "sequence": len(records) + 1,
            "trigger_id": trigger_id,
            "event_type": event_type,
            "details": copy.deepcopy(dict(details)),
            "recorded_at": self._now(),
            "prior_record_digest": records[-1]["record_digest"] if records else None,
        }
        record = {**body, "record_digest": _digest_json(body)}
        records.append(record)
        _, _, path = self._paths(trigger_id)
        _write_json(path, records)
        return copy.deepcopy(record)

    def _assert_available(self, spec: Mapping[str, Any]) -> None:
        entries = self.automation.library.list_entries(project_ref=spec["project_ref"])["entries"]
        matches = [
            row for row in entries
            if row.get("definition_ref") == spec["definition_ref"]
            and row.get("lifecycle_status") == "available"
            and row.get("automated_execution_available") is True
        ]
        if len(matches) != 1:
            raise ProcessTriggerConflict("Trigger requires one exact active automated Process Library entry")
        if spec["condition"].get("event_type") == "milestone_check_in":
            if "project_snapshot" not in {
                binding["source"] for binding in spec["input_bindings"].values()
            }:
                raise ProcessTriggerConflict(
                    "milestone check-in must bind the authenticated project_snapshot"
                )
            try:
                definition = self.automation.registry.resolve(
                    spec["definition_ref"]["definition_id"],
                    spec["definition_ref"]["version"],
                    spec["definition_ref"]["digest"],
                )
            except Exception as exc:
                raise ProcessTriggerIntegrityError(
                    "milestone check-in definition could not be reauthenticated"
                ) from exc
            if not any(
                node.get("kind") == "human_checkpoint"
                for node in definition["graph"]["nodes"]
            ):
                raise ProcessTriggerConflict(
                    "milestone check-in requires a declared human checkpoint"
                )

    @staticmethod
    def _ref_key(ref: Mapping[str, Any]) -> tuple[str, str, str]:
        return (str(ref["definition_id"]), str(ref["version"]), str(ref["digest"]))

    def _assert_no_framework_cycle(self, proposed: Mapping[str, Any]) -> None:
        specs = [copy.deepcopy(dict(proposed))]
        if self.definitions.exists():
            for path in sorted(self.definitions.glob("*.json")):
                envelope = _read_json(path)
                existing_id = str((envelope.get("spec") or {}).get("trigger_id") or "")
                if existing_id == proposed["trigger_id"]:
                    continue
                existing, _ = self._load_spec(existing_id)
                specs.append(existing)
        edges: dict[tuple[str, str, str], set[tuple[str, str, str]]] = {}
        for spec in specs:
            condition = spec["condition"]
            if spec["kind"] != "event" or condition.get("event_type") != "framework_completion":
                continue
            source = self._ref_key(condition["source_definition_ref"])
            target = self._ref_key(spec["definition_ref"])
            edges.setdefault(source, set()).add(target)

        visiting: set[tuple[str, str, str]] = set()
        visited: set[tuple[str, str, str]] = set()

        def visit(node: tuple[str, str, str]) -> None:
            if node in visiting:
                raise ProcessTriggerConflict(
                    "framework-completion Trigger graph contains a causal cycle"
                )
            if node in visited:
                return
            visiting.add(node)
            for target in edges.get(node, set()):
                visit(target)
            visiting.remove(node)
            visited.add(node)

        for node in tuple(edges):
            visit(node)

    def _activation_request(self, spec: Mapping[str, Any], digest: str) -> dict[str, Any]:
        body = {
            "trigger_id": spec["trigger_id"],
            "spec_digest": digest,
            "definition_ref": copy.deepcopy(spec["definition_ref"]),
            "project_ref": spec["project_ref"],
            "principal_id": spec["principal_id"],
            "decision": "approve_activation",
        }
        return {**body, "request_digest": _digest_json(body)}

    def authenticate_firing(self, binding: Mapping[str, Any]) -> dict[str, Any]:
        required = {
            "schema_version", "trigger_id", "spec_digest", "firing_id", "source_digest",
        }
        if not isinstance(binding, Mapping) or set(binding) != required:
            raise ProcessTriggerIntegrityError("trigger Run binding is malformed")
        if binding.get("schema_version") != TRIGGER_SCHEMA_VERSION:
            raise ProcessTriggerIntegrityError("trigger Run binding schema is unsupported")
        with self._locked():
            spec, digest = self._load_spec(str(binding["trigger_id"]))
            if digest != binding["spec_digest"]:
                raise ProcessTriggerIntegrityError("trigger Run spec identity changed")
            matches = [
                row for row in self._load_records(spec["trigger_id"])
                if row["event_type"] == "firing_claimed"
                and row["details"].get("firing_id") == binding["firing_id"]
            ]
            if len(matches) != 1 or matches[0]["details"].get("source_digest") != binding["source_digest"]:
                raise ProcessTriggerIntegrityError("trigger Run lacks one authenticated firing claim")
        return copy.deepcopy(dict(binding))

    def create(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        spec = normalize_trigger_spec(raw)
        digest = _digest_json(spec)
        with self._locked():
            definition_path, anchor_path, records_path = self._paths(spec["trigger_id"])
            if definition_path.exists() or anchor_path.exists() or records_path.exists():
                expected_envelope = {"spec": spec, "spec_digest": digest}
                expected_anchor = {
                    "schema_version": TRIGGER_SCHEMA_VERSION,
                    "trigger_id": spec["trigger_id"],
                    "spec_digest": digest,
                }
                if definition_path.exists() and _read_json(definition_path) != expected_envelope:
                    raise ProcessTriggerConflict("Trigger identity is already bound to different content")
                if anchor_path.exists() and _read_json(anchor_path) != expected_anchor:
                    raise ProcessTriggerConflict("Trigger anchor is bound to different content")
                if records_path.exists() and not definition_path.exists() and not anchor_path.exists():
                    raise ProcessTriggerIntegrityError("orphan Trigger records cannot establish a definition")
                # Restart-safe repair of an interrupted exact create. At least
                # one independently matching immutable surface must preexist;
                # the current request supplies and reauthenticates the other.
                if not definition_path.exists():
                    _write_json(definition_path, expected_envelope)
                if not anchor_path.exists():
                    _write_json(anchor_path, expected_anchor)
                if not records_path.exists():
                    self._append(spec["trigger_id"], "trigger_created", {
                        "spec_digest": digest,
                        "definition_ref": spec["definition_ref"],
                        "project_ref": spec["project_ref"],
                        "principal_id": spec["principal_id"],
                    })
                self._load_spec(spec["trigger_id"])
                self._load_records(spec["trigger_id"])
                return self.get(spec["trigger_id"])
            self._assert_available(spec)
            self._assert_no_framework_cycle(spec)
            _write_json(definition_path, {"spec": spec, "spec_digest": digest})
            _write_json(anchor_path, {
                "schema_version": TRIGGER_SCHEMA_VERSION,
                "trigger_id": spec["trigger_id"],
                "spec_digest": digest,
            })
            self._append(spec["trigger_id"], "trigger_created", {
                "spec_digest": digest,
                "definition_ref": spec["definition_ref"],
                "project_ref": spec["project_ref"],
                "principal_id": spec["principal_id"],
            })
            return self.get(spec["trigger_id"])

    @staticmethod
    def _lifecycle(records: Sequence[Mapping[str, Any]]) -> str:
        status = "draft"
        for record in records:
            if record["event_type"] == "trigger_activated":
                status = "active"
            elif record["event_type"] == "trigger_paused":
                status = "paused"
            elif record["event_type"] == "trigger_resumed":
                status = "active"
            elif record["event_type"] == "trigger_retired":
                status = "retired"
        return status

    def get(self, trigger_id: str) -> dict[str, Any]:
        if not self.root.exists():
            raise ProcessTriggerConflict("Trigger does not exist")
        with self._locked():
            spec, digest = self._load_spec(trigger_id)
            records = self._load_records(trigger_id)
            firings = self._firing_views(records)
            body = {
                "spec": spec,
                "spec_digest": digest,
                "status": self._lifecycle(records),
                "activation_request": self._activation_request(spec, digest),
                "firings": firings,
                "last_record_digest": records[-1]["record_digest"] if records else None,
            }
            return {**body, "state_digest": _digest_json(body)}

    def list(self) -> dict[str, Any]:
        items = []
        if not self.root.exists():
            body = {"schema_version": TRIGGER_SCHEMA_VERSION, "triggers": items}
            return {**body, "projection_digest": _digest_json(body)}
        with self._locked():
            for path in sorted(self.definitions.glob("*.json")):
                if path.is_symlink():
                    raise ProcessTriggerIntegrityError("Trigger definition path may not be a symlink")
                envelope = _read_json(path)
                trigger_id = str((envelope.get("spec") or {}).get("trigger_id") or "")
                items.append(self.get(trigger_id))
        body = {"schema_version": TRIGGER_SCHEMA_VERSION, "triggers": items}
        return {**body, "projection_digest": _digest_json(body)}

    def activate(
        self, trigger_id: str, *, expected_spec_digest: str,
        approval: Mapping[str, Any], idempotency_key: str,
    ) -> dict[str, Any]:
        key = _safe_id(idempotency_key, "idempotency_key")
        with self._locked():
            spec, digest = self._load_spec(trigger_id)
            if expected_spec_digest != digest:
                raise ProcessTriggerConflict("Trigger changed before activation")
            expected = self._activation_request(spec, digest)
            if not isinstance(approval, Mapping) or dict(approval) != {
                "decision": "approve_activation",
                "principal_id": spec["principal_id"],
                "request_digest": expected["request_digest"],
            }:
                raise ProcessTriggerConflict("activation lacks the exact Principal decision")
            if spec["kind"] == "inbound":
                raise ProcessTriggerConflict("inbound activation is unavailable until G1.21 authenticates the channel")
            self._assert_available(spec)
            self._assert_no_framework_cycle(spec)
            records = self._load_records(trigger_id)
            matches = [row for row in records if row["event_type"] == "trigger_activated" and row["details"].get("idempotency_key") == key]
            if matches:
                if matches[-1]["details"].get("spec_digest") != digest:
                    raise ProcessTriggerIntegrityError("activation idempotency identity collided")
                return self.get(trigger_id)
            if self._lifecycle(records) not in {"draft", "paused"}:
                raise ProcessTriggerConflict("Trigger is not activatable")
            self._append(trigger_id, "trigger_activated", {
                "spec_digest": digest,
                "approval_request_digest": expected["request_digest"],
                "approved_by": spec["principal_id"],
                "idempotency_key": key,
            })
            return self.get(trigger_id)

    def lifecycle(self, trigger_id: str, *, action: str, expected_state_digest: str, idempotency_key: str) -> dict[str, Any]:
        key = _safe_id(idempotency_key, "idempotency_key")
        if action not in {"pause", "resume", "retire"}:
            raise ProcessTriggerInputRequired("Trigger lifecycle action is invalid")
        with self._locked():
            state = self.get(trigger_id)
            if state["state_digest"] != expected_state_digest:
                raise ProcessTriggerConflict("Trigger state changed before lifecycle action")
            records = self._load_records(trigger_id)
            event_type = f"trigger_{action}d" if action != "pause" else "trigger_paused"
            matches = [row for row in records if row["event_type"] == event_type and row["details"].get("idempotency_key") == key]
            if matches:
                return self.get(trigger_id)
            allowed = {"pause": {"active"}, "resume": {"paused"}, "retire": {"draft", "active", "paused"}}
            if state["status"] not in allowed[action]:
                raise ProcessTriggerConflict(f"Trigger cannot {action} from {state['status']}")
            self._append(trigger_id, event_type, {
                "spec_digest": state["spec_digest"],
                "principal_id": state["spec"]["principal_id"],
                "idempotency_key": key,
            })
            return self.get(trigger_id)

    @staticmethod
    def _firing_views(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        firings: dict[str, dict[str, Any]] = {}
        for record in records:
            if not record["event_type"].startswith("firing_"):
                continue
            firing_id = str(record["details"].get("firing_id") or "")
            if not firing_id:
                raise ProcessTriggerIntegrityError("firing record lacks an identity")
            view = firings.setdefault(firing_id, {"firing_id": firing_id})
            view.update(copy.deepcopy(record["details"]))
            view["status"] = record["event_type"].removeprefix("firing_")
            view["last_record_digest"] = record["record_digest"]
        return sorted(firings.values(), key=lambda row: row["firing_id"])

    def _project_snapshot(self, project_ref: str) -> dict[str, Any]:
        try:
            from operation_matrix import resolve_matrix_path
            from conversation_memory import iter_conversations, load_conversation_json
        except ImportError:  # pragma: no cover
            from orchestrator.operation_matrix import resolve_matrix_path
            from orchestrator.conversation_memory import iter_conversations, load_conversation_json
        matrix_path = resolve_matrix_path(project_ref, vault=self.vault)
        if matrix_path is None or not matrix_path.is_file() or matrix_path.is_symlink():
            raise ProcessTriggerConflict("milestone check-in requires one authenticated project Matrix")
        matrix_text = matrix_path.read_text(encoding="utf-8")
        dialogues = []
        for summary in iter_conversations(self.sessions_root):
            if project_ref not in summary.get("project_ids", []):
                continue
            if summary.get("tag") in {"private", "stealth"}:
                continue
            envelope = load_conversation_json(summary["conversation_id"], self.sessions_root) or {}
            excerpts = []
            for message in (envelope.get("messages") or [])[-8:]:
                if not isinstance(message, Mapping):
                    continue
                content = str(message.get("content") or "")[:2000]
                excerpts.append({"role": str(message.get("role") or ""), "content": content})
            dialogues.append({
                "conversation_id": summary["conversation_id"],
                "title": summary["title"],
                "last_activity_at": summary["last_activity_at"],
                "excerpts": excerpts,
            })
        body = {
            "project_ref": project_ref,
            "matrix": {"locator": str(matrix_path.resolve()), "content": matrix_text},
            "dialogues": dialogues,
            "privacy_scope": "standard Project Dialogues only; private and stealth excluded",
            "captured_at": self._now(),
        }
        return {**body, "snapshot_digest": _digest_json(body)}

    def _source_from_run(self, source_run_id: str, expected_ref: Mapping[str, Any], project_ref: str) -> dict[str, Any]:
        runtime = self.automation.runtime
        run = runtime.load_run(source_run_id)
        if run["state"] != "completed" or run["definition_ref"] != expected_ref:
            raise ProcessTriggerConflict("framework completion source is not the exact completed definition")
        if run["input_bindings"].get("project_ref") != project_ref:
            raise ProcessTriggerConflict("framework completion source belongs to another project")
        accepts = [
            record for record in runtime.load_records(source_run_id)
            if (record.get("transition") or {}).get("directive") == "ACCEPT"
        ]
        if len(accepts) != 1:
            raise ProcessTriggerIntegrityError("framework completion lacks one authenticated ACCEPT transition")
        state = self.automation.run_state(source_run_id)
        result = state.get("result")
        if not isinstance(result, Mapping):
            raise ProcessTriggerIntegrityError("framework completion lacks an authenticated result")
        body = {
            "kind": "framework_completion",
            "source_run_id": source_run_id,
            "source_definition_ref": copy.deepcopy(run["definition_ref"]),
            "source_accept_record_digest": _digest_json(accepts[0]),
            "source_result": copy.deepcopy(dict(result)),
        }
        return {**body, "source_digest": _digest_json(body)}

    def _resolve_inputs(self, spec: Mapping[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
        inputs: dict[str, Any] = {}
        snapshot = None
        for field, binding in spec["input_bindings"].items():
            kind = binding["source"]
            if kind == "literal":
                value = copy.deepcopy(binding["value"])
            elif kind == "changed_paths":
                value = copy.deepcopy(source.get("changed_paths"))
            elif kind == "changed_artifacts":
                value = copy.deepcopy(source.get("changed_artifacts"))
            elif kind == "source_path":
                value = source.get("source_path")
            elif kind == "source_run_id":
                value = source.get("source_run_id")
            elif kind == "source_result":
                value = copy.deepcopy(source.get("source_result"))
            elif kind == "project_snapshot":
                snapshot = snapshot or self._project_snapshot(spec["project_ref"])
                value = copy.deepcopy(snapshot)
            else:  # validated on create
                raise ProcessTriggerIntegrityError("persisted input source is unsupported")
            if value is None:
                raise ProcessTriggerConflict(f"firing source cannot resolve input {field}")
            inputs[field] = value
        return inputs

    def _claim(self, spec: Mapping[str, Any], digest: str, source: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        source_body = copy.deepcopy(dict(source))
        if source_body.get("kind") in {"time", "milestone_check_in"}:
            source_identity = {
                "kind": source_body["kind"],
                "scheduled_for": source_body.get("scheduled_for"),
            }
        elif source_body.get("kind") == "file_change":
            source_identity = {
                "kind": "file_change",
                "changed_artifacts": source_body.get("changed_artifacts"),
            }
        elif source_body.get("kind") == "manual":
            source_identity = {
                key: source_body.get(key) for key in ("kind", "request_id", "requested_by")
            }
        elif source_body.get("kind") == "framework_completion":
            source_identity = {
                key: source_body.get(key) for key in (
                    "kind", "source_run_id", "source_definition_ref",
                    "source_accept_record_digest", "source_result",
                )
            }
        else:
            source_identity = source_body
        source_digest = _digest_json(source_identity)
        firing_id = "firing-" + _digest_json({
            "trigger_id": spec["trigger_id"], "spec_digest": digest, "source_digest": source_digest,
        }).split(":", 1)[1][:40]
        existing = [row for row in self._firing_views(self._load_records(spec["trigger_id"])) if row["firing_id"] == firing_id]
        if existing:
            if existing[0].get("source_digest") != source_digest:
                raise ProcessTriggerIntegrityError("firing identity collided")
            return existing[0], False
        inputs = self._resolve_inputs(spec, source_body)
        invocation_key = "trigger-" + hashlib.sha256(firing_id.encode("utf-8")).hexdigest()
        details = {
            "firing_id": firing_id,
            "spec_digest": digest,
            "source": source_body,
            "source_digest": source_digest,
            "observed_source_digest": _digest_json(source_body),
            "inputs": inputs,
            "inputs_digest": _digest_json(inputs),
            "invocation_idempotency_key": invocation_key,
        }
        if source_body.get("scheduled_for"):
            details["scheduled_for"] = source_body["scheduled_for"]
        self._append(spec["trigger_id"], "firing_claimed", details)
        return {**details, "status": "claimed"}, True

    def _continue_firing(self, spec: Mapping[str, Any], digest: str, firing: Mapping[str, Any]) -> dict[str, Any]:
        trigger_binding = {
            "schema_version": TRIGGER_SCHEMA_VERSION,
            "trigger_id": spec["trigger_id"],
            "spec_digest": digest,
            "firing_id": firing["firing_id"],
            "source_digest": firing["source_digest"],
        }
        try:
            state = self.automation.begin_triggered_run(
                definition_ref=spec["definition_ref"],
                project_ref=spec["project_ref"],
                inputs=firing["inputs"],
                idempotency_key=firing["invocation_idempotency_key"],
                principal_id=spec["principal_id"],
                process_profile=spec.get("process_profile"),
                step_profiles=spec.get("step_profiles"),
                style_profile=spec.get("style_profile"),
                trigger_binding=trigger_binding,
            )
            with self._locked():
                views = {row["firing_id"]: row for row in self._firing_views(self._load_records(spec["trigger_id"]))}
                current = views[firing["firing_id"]]
                if current["status"] == "claimed":
                    self._append(spec["trigger_id"], "firing_run_bound", {
                        **{key: copy.deepcopy(firing[key]) for key in (
                            "firing_id", "spec_digest", "source_digest", "invocation_idempotency_key",
                        )},
                        "run_id": state["run_id"],
                        "run_state_digest": state["state_digest"],
                    })
            final = self.automation.execute(state["run_id"])
            with self._locked():
                firing_event = {
                    "completed": "firing_completed",
                    "blocked": "firing_blocked",
                    "cancelled": "firing_cancelled",
                }.get(final["run_state"], "firing_waiting")
                self._append(spec["trigger_id"], firing_event, {
                    "firing_id": firing["firing_id"],
                    "spec_digest": digest,
                    "source_digest": firing["source_digest"],
                    "run_id": final["run_id"],
                    "run_status": final["status"],
                    "run_state_digest": final["state_digest"],
                })
            return self.get(spec["trigger_id"])
        except Exception as exc:
            with self._locked():
                self._append(spec["trigger_id"], "firing_failed", {
                    "firing_id": firing["firing_id"],
                    "spec_digest": digest,
                    "source_digest": firing["source_digest"],
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:2000],
                })
            raise

    def fire_manual(self, trigger_id: str, *, request_id: str, requested_by: str) -> dict[str, Any]:
        source = {"kind": "manual", "request_id": _safe_id(request_id, "request_id"), "requested_by": _safe_id(requested_by, "requested_by")}
        with self._locked():
            spec, digest = self._load_spec(trigger_id)
            if self._lifecycle(self._load_records(trigger_id)) != "active" or spec["kind"] != "manual":
                raise ProcessTriggerConflict("manual firing requires an active manual Trigger")
            if source["requested_by"] != spec["principal_id"]:
                raise ProcessTriggerConflict("manual firing requires the bound Principal")
            self._assert_available(spec)
            firing, created = self._claim(spec, digest, source)
        return self._continue_firing(spec, digest, firing) if created else self.get(trigger_id)

    @staticmethod
    def _path_matches(path: str, selector: str) -> bool:
        exact = Path(path).resolve()
        bound = Path(selector).resolve()
        return exact == bound or (bound.is_dir() and bound in exact.parents)

    @staticmethod
    def _file_identity(path: str) -> dict[str, Any]:
        exact = Path(path).resolve()
        if not exact.exists():
            return {"path": str(exact), "kind": "absent"}
        if exact.is_symlink() or not exact.is_file():
            raise ProcessTriggerConflict("file-change source must be a real file or an absent path")
        digest = hashlib.sha256()
        content = bytearray()
        with exact.open("rb") as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                if len(content) < 1024 * 1024:
                    content.extend(chunk[: 1024 * 1024 - len(content)])
        stat = exact.stat()
        try:
            excerpt = bytes(content).decode("utf-8")
        except UnicodeDecodeError:
            excerpt = ""
        return {
            "path": str(exact),
            "kind": "file",
            "content_digest": "sha256:" + digest.hexdigest(),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "utf8_excerpt": excerpt,
            "excerpt_complete": stat.st_size <= 1024 * 1024,
        }

    def dispatch_paths(self, paths: Sequence[str]) -> dict[str, Any]:
        exact_paths = sorted({str(Path(path).resolve()) for path in paths})
        fired, failures = [], []
        for state in self.list()["triggers"]:
            spec = state["spec"]
            if state["status"] != "active" or spec["kind"] != "event" or spec["condition"].get("event_type") != "file_change":
                continue
            matched = [path for path in exact_paths if any(self._path_matches(path, selector) for selector in spec["condition"]["path_selectors"])]
            if not matched:
                continue
            artifacts = [self._file_identity(path) for path in matched]
            source = {
                "kind": "file_change", "changed_paths": matched,
                "changed_artifacts": artifacts, "source_path": matched[0],
            }
            try:
                with self._locked():
                    self._assert_available(spec)
                    firing, created = self._claim(spec, state["spec_digest"], source)
                result = self._continue_firing(spec, state["spec_digest"], firing) if created else self.get(spec["trigger_id"])
                fired.append({"trigger_id": spec["trigger_id"], "state_digest": result["state_digest"]})
            except Exception as exc:
                failures.append({"trigger_id": spec["trigger_id"], "error": str(exc)})
        return {"paths": exact_paths, "fired": fired, "failures": failures}

    def dispatch_framework_completion(self, source_run_id: str) -> dict[str, Any]:
        fired, failures = [], []
        for state in self.list()["triggers"]:
            spec = state["spec"]
            if state["status"] != "active" or spec["kind"] != "event" or spec["condition"].get("event_type") != "framework_completion":
                continue
            try:
                source = self._source_from_run(
                    source_run_id, spec["condition"]["source_definition_ref"], spec["project_ref"]
                )
                with self._locked():
                    self._assert_available(spec)
                    firing, created = self._claim(spec, state["spec_digest"], source)
                result = self._continue_firing(spec, state["spec_digest"], firing) if created else self.get(spec["trigger_id"])
                fired.append({"trigger_id": spec["trigger_id"], "state_digest": result["state_digest"]})
            except ProcessTriggerConflict:
                continue
            except Exception as exc:
                failures.append({"trigger_id": spec["trigger_id"], "error": str(exc)})
        return {"source_run_id": source_run_id, "fired": fired, "failures": failures}

    def run_due(self, *, now: str | None = None) -> dict[str, Any]:
        current = _parse_instant(now or self._now(), "now")
        fired, skipped, failures = [], [], []
        for state in self.list()["triggers"]:
            spec = state["spec"]
            if state["status"] != "active" or spec["kind"] != "time":
                continue
            schedule = spec["condition"]["schedule"]
            records = self._load_records(spec["trigger_id"])
            activation = next(row for row in records if row["event_type"] == "trigger_activated")
            cursor = _parse_instant(activation["recorded_at"], "activation time") - timedelta(microseconds=1)
            windows = []
            for record in records:
                if record["event_type"] in {"firing_claimed", "firing_skipped"} and record["details"].get("scheduled_for"):
                    cursor = max(cursor, _parse_instant(record["details"]["scheduled_for"], "scheduled_for"))
            windows = _occurrences(schedule, cursor, current)
            if not windows:
                continue
            selected = windows[-1]
            overdue = (current - selected).total_seconds() > int(schedule["grace_seconds"])
            if overdue and schedule["missed_policy"] == "skip":
                with self._locked():
                    self._append(spec["trigger_id"], "firing_skipped", {
                        "firing_id": "skip-" + hashlib.sha256(f"{spec['trigger_id']}:{selected.isoformat()}".encode()).hexdigest()[:40],
                        "spec_digest": state["spec_digest"],
                        "source_digest": _digest_json({"scheduled_for": selected.isoformat()}),
                        "scheduled_for": selected.isoformat().replace("+00:00", "Z"),
                        "missed_count": len(windows),
                        "reason": "Ora was not running within the declared grace window",
                    })
                skipped.append(spec["trigger_id"])
                continue
            source = {
                "kind": spec["condition"]["event_type"],
                "scheduled_for": selected.isoformat().replace("+00:00", "Z"),
                "observed_at": current.isoformat().replace("+00:00", "Z"),
                "coalesced_windows": len(windows),
            }
            try:
                with self._locked():
                    self._assert_available(spec)
                    firing, created = self._claim(spec, state["spec_digest"], source)
                    if created:
                        # Durable cursor for both successful and failed attempts.
                        self._append(spec["trigger_id"], "firing_scheduled", {
                            "firing_id": firing["firing_id"],
                            "spec_digest": state["spec_digest"],
                            "source_digest": firing["source_digest"],
                            "scheduled_for": source["scheduled_for"],
                            "coalesced_windows": len(windows),
                        })
                result = self._continue_firing(spec, state["spec_digest"], firing) if created else self.get(spec["trigger_id"])
                fired.append({"trigger_id": spec["trigger_id"], "state_digest": result["state_digest"]})
            except Exception as exc:
                failures.append({"trigger_id": spec["trigger_id"], "error": str(exc)})
        return {"observed_at": current.isoformat().replace("+00:00", "Z"), "fired": fired, "skipped": skipped, "failures": failures}

    def recover_incomplete(self) -> dict[str, Any]:
        recovered, failures = [], []
        for state in self.list()["triggers"]:
            if state["status"] not in {"active", "paused"}:
                continue
            spec = state["spec"]
            for firing in state["firings"]:
                if firing["status"] not in {"claimed", "run_bound", "scheduled"}:
                    continue
                try:
                    result = self._continue_firing(spec, state["spec_digest"], firing)
                    recovered.append({"trigger_id": spec["trigger_id"], "firing_id": firing["firing_id"], "state_digest": result["state_digest"]})
                except Exception as exc:
                    failures.append({"trigger_id": spec["trigger_id"], "firing_id": firing["firing_id"], "error": str(exc)})
        return {"recovered": recovered, "failures": failures}

    def synchronize_run(self, run_id: str) -> dict[str, Any]:
        """Refresh one Trigger firing after a public Run action.

        A human checkpoint belongs to the governed Run, not to a second Trigger
        state machine.  This join records the newly authenticated Run digest and
        emits framework-completion only after the exact Run reaches ACCEPT.
        """

        matches: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
        for state in self.list()["triggers"]:
            for firing in state["firings"]:
                if firing.get("run_id") == run_id:
                    matches.append((state, state["spec"], firing))
        if len(matches) > 1:
            raise ProcessTriggerIntegrityError("one Run is bound to multiple Trigger firings")
        if not matches:
            return {"run_id": run_id, "trigger_binding": None, "framework_dispatch": None}
        state, spec, firing = matches[0]
        run_state = self.automation.run_state(run_id)
        event_type = {
            "completed": "firing_completed",
            "blocked": "firing_blocked",
            "cancelled": "firing_cancelled",
        }.get(run_state["run_state"], "firing_waiting")
        if (
            firing["status"] != event_type.removeprefix("firing_")
            or firing.get("run_state_digest") != run_state["state_digest"]
        ):
            with self._locked():
                self._append(spec["trigger_id"], event_type, {
                    "firing_id": firing["firing_id"],
                    "spec_digest": state["spec_digest"],
                    "source_digest": firing["source_digest"],
                    "run_id": run_id,
                    "run_status": run_state["status"],
                    "run_state_digest": run_state["state_digest"],
                })
        framework_dispatch = None
        if run_state["run_state"] == "completed":
            framework_dispatch = self.dispatch_framework_completion(run_id)
        return {
            "run_id": run_id,
            "trigger_binding": self.get(spec["trigger_id"]),
            "framework_dispatch": framework_dispatch,
        }

    def attention_projection(self) -> list[dict[str, Any]]:
        rows = []
        for state in self.list()["triggers"]:
            latest = state["firings"][-1] if state["firings"] else None
            rows.append({
                "trigger_id": state["spec"]["trigger_id"],
                "name": state["spec"]["name"],
                "definition_ref": state["spec"]["definition_ref"],
                "project_ref": state["spec"]["project_ref"],
                "status": state["status"],
                "trigger_binding": {
                    "kind": state["spec"]["kind"],
                    "condition": state["spec"]["condition"],
                    "spec_digest": state["spec_digest"],
                },
                "authority_binding": {"principal_id": state["spec"]["principal_id"]},
                "latest_firing": latest,
                "state_digest": state["state_digest"],
            })
        return rows


class ProcessTriggerClock:
    """Intermittent app-owned clock; it never installs an OS fallback."""

    def __init__(self, service: ProcessTriggerService | None = None, *, interval_seconds: float = 30.0):
        self.service = service or ProcessTriggerService()
        self.interval_seconds = max(1.0, float(interval_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.service.recover_incomplete()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ora-process-trigger-clock", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.service.run_due()
            except Exception as exc:  # health is visible; the loop cannot forge success
                print(f"[process-trigger-clock] {type(exc).__name__}: {exc}")
            self._stop.wait(self.interval_seconds)

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=min(5.0, self.interval_seconds + 1.0))


__all__ = [
    "EVENT_TYPES", "ProcessTriggerClock", "ProcessTriggerConflict",
    "ProcessTriggerError", "ProcessTriggerInputRequired",
    "ProcessTriggerIntegrityError", "ProcessTriggerService", "TRIGGER_KINDS",
    "TRIGGER_SCHEMA_VERSION", "normalize_trigger_spec",
]
