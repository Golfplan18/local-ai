"""G1.18 automated Process authoring and isolated execution.

This module is deliberately an adapter over the accepted G1.1 objects.  It
does not own a second process state machine: definitions are validated by
``process_contracts``, registered by ``ProcessDefinitionRegistry``, Runs are
advanced only by ``GovernedProcessRuntime``, and availability is conferred only
by ``ProcessLibraryLifecycleService``.

The older Project Integration Program described Trigger, Model Profile, and
Style fields on a Process Definition and execution through
``milestone_executor``.  The issued G1.1 contract does not permit those root
fields.  G1.18 therefore keeps model/style selection in the exact Run input
binding, leaves Trigger to G1.19, and uses a separate no-tools worker only as an
actuator for a G1.1 action node.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:
    from . import process_contracts as contracts
    from . import project_meta
    from .governed_process_runtime import (
        CorrectionDecisionRequired,
        GovernedProcessRuntime,
        GovernedRuntimeError,
        RunConflictError,
        RunNotFoundError,
    )
    from .model_profiles import ModelProfileError, resolve_effective_profile
    from .process_automation_worker import assess_criteria as mechanically_assess_criteria
    from .process_definition_registry import (
        ProcessDefinitionRegistry,
        ProcessDefinitionRegistryError,
        process_definition_content_digest,
    )
    from .process_library_lifecycle import (
        ProcessLibraryError,
        ProcessLibraryLifecycleService,
    )
    from .process_management_interview import (
        ManagementInterviewError,
        ManagementInterviewService,
    )
    from .runtime_paths import atomic_write_text
    from .tools import bash_execute as _bash_execute
except ImportError:  # pragma: no cover - direct module execution/tests
    import process_contracts as contracts  # type: ignore
    import project_meta  # type: ignore
    from governed_process_runtime import (  # type: ignore
        CorrectionDecisionRequired,
        GovernedProcessRuntime,
        GovernedRuntimeError,
        RunConflictError,
        RunNotFoundError,
    )
    from model_profiles import ModelProfileError, resolve_effective_profile  # type: ignore
    from process_automation_worker import assess_criteria as mechanically_assess_criteria  # type: ignore
    from process_definition_registry import (  # type: ignore
        ProcessDefinitionRegistry,
        ProcessDefinitionRegistryError,
        process_definition_content_digest,
    )
    from process_library_lifecycle import (  # type: ignore
        ProcessLibraryError,
        ProcessLibraryLifecycleService,
    )
    from process_management_interview import (  # type: ignore
        ManagementInterviewError,
        ManagementInterviewService,
    )
    from runtime_paths import atomic_write_text  # type: ignore
    from tools import bash_execute as _bash_execute  # type: ignore


AUTOMATION_SCHEMA_VERSION = "ora.process-automation/1.0"
BLUEPRINT_SCHEMA_VERSION = "ora.process-blueprint/1.0"
WORKER_SCHEMA_VERSION = "ora.process-worker-request/1.0"
TRIGGER_INVOCATION_SCHEMA_VERSION = "ora.process-trigger-invocation/1.0"
AUTHORING_PROPOSED_EVENT = "automation_authoring_proposed"
AUTHORING_REVISION_EVENT = "automation_authoring_revision_requested"
CONDITIONS = ["approved_plan_digest_matches"]
INPUT_SELECTOR = "scope:declared_inputs"
OUTPUT_SELECTOR = "scope:declared_outputs"
DEFINITION_SELECTOR = "scope:process_definition"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:/-]*$")
_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CONTROL_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")
_EXTERNAL_OPERATION_RE = re.compile(
    r"(?:send|publish|upload|delete|remove|write[_-]?(?:file|repo)|mutate|"
    r"commit|push|message|email[_-]?send|activate|schedule|trigger)",
    flags=re.IGNORECASE,
)


class ProcessAutomationError(RuntimeError):
    """Base class for G1.18 input, authority, and execution refusals."""


class ProcessAutomationInputRequired(ProcessAutomationError):
    pass


class ProcessAutomationConflict(ProcessAutomationError):
    pass


class ProcessAutomationIntegrityError(ProcessAutomationError):
    pass


class ProcessAutomationWorkerError(ProcessAutomationError):
    pass


class ProcessAutomationWorkerControlled(ProcessAutomationWorkerError):
    """The Principal stopped one exact live isolated worker."""

    def __init__(self, action: str, execution_id: str):
        super().__init__(f"isolated worker received authenticated {action} control")
        self.action = action
        self.execution_id = execution_id


class _ProcessAutomationControlApplied(ProcessAutomationError):
    """Internal loop signal: a requested pause/stop was durably applied."""


_ACTIVE_WORKER_LOCK = threading.RLock()
_ACTIVE_AUTOMATION_WORKERS: dict[str, dict[str, Any]] = {}


def active_automation_worker(run_id: str) -> dict[str, Any] | None:
    """Return a bounded live-process observation, never the Popen handle."""

    with _ACTIVE_WORKER_LOCK:
        entry = _ACTIVE_AUTOMATION_WORKERS.get(str(run_id))
        if entry is None:
            return None
        process = entry["process"]
        return {
            key: copy.deepcopy(value)
            for key, value in entry.items()
            if key != "process"
        } | {
            "alive": process.poll() is None,
            "returncode": process.poll(),
        }


def _request_active_worker_control(run_id: str, action: str) -> dict[str, Any]:
    if action not in {"pause", "stop"}:
        raise ProcessAutomationInputRequired("worker control must be pause or stop")
    with _ACTIVE_WORKER_LOCK:
        entry = _ACTIVE_AUTOMATION_WORKERS.get(str(run_id))
        if entry is None or entry["process"].poll() is not None:
            raise ProcessAutomationConflict("the Run has no live isolated worker")
        if entry.get("control_action") not in {None, action}:
            raise ProcessAutomationConflict("a different worker control is already pending")
        entry["control_action"] = action
        pid = int(entry["pid"])
        execution_id = str(entry["execution_id"])
    message = _bash_execute.stop_process(pid)
    if message.startswith("PID ") or message.startswith("Error stopping"):
        raise ProcessAutomationConflict(message)
    return {
        "execution_id": execution_id,
        "pid": pid,
        "action": action,
        "stop_result": message,
    }


def automation_run_controls(
    runtime: GovernedProcessRuntime,
    run_id: str,
) -> dict[str, Any]:
    """Derive the exact stale-safe control contract from persisted Run state."""

    run = runtime.load_run(run_id)
    definition = runtime.load_definition(run_id)
    nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
    node = nodes[run["current_node_id"]]
    worker = active_automation_worker(run_id)
    records = runtime.load_records(run_id)
    latest_pause = next(
        (
            record for record in reversed(records)
            if (record.get("event") or {}).get("event_type") == "run_paused"
        ),
        None,
    )
    latest_resume = next(
        (
            record for record in reversed(records)
            if (record.get("event") or {}).get("event_type") == "run_resumed"
        ),
        None,
    )
    if (
        latest_pause is not None
        and latest_resume is not None
        and int(latest_resume["sequence"]) > int(latest_pause["sequence"])
    ):
        latest_pause = None
    pause_kind = str(
        ((((latest_pause or {}).get("event") or {}).get("details") or {}).get(
            "pause_kind"
        ) or "")
    ) or None
    available: list[str] = []
    if run["state"] == "running":
        available = ["pause", "stop"]
    elif run["state"] == "pending":
        available = ["stop"]
        if pause_kind in {"user_control", "failure_recovery"} or (
            pause_kind is None and node["kind"] != "human_checkpoint"
        ):
            available.insert(0, "resume")
    body = {
        "schema_version": "ora.process-run-controls/1.0",
        "run_id": run_id,
        "run_state": run["state"],
        "current_node_id": run["current_node_id"],
        "updated_at": run["updated_at"],
        "last_sequence": run["last_sequence"],
        "available_actions": available,
        "active_worker": worker,
        "pause_kind": pause_kind,
    }
    return {**body, "control_state_digest": _digest_json(body)}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digest_json(value: Any) -> str:
    return _digest_text(_canonical_json(value))


def _definition_ref(definition: Mapping[str, Any]) -> dict[str, str]:
    return {
        "definition_id": str(definition["definition_id"]),
        "version": str(definition["version"]),
        "digest": str(definition["digest"]),
    }


def _safe_id(value: str, label: str) -> str:
    result = str(value or "").strip().lower()
    if not _ID_RE.fullmatch(result):
        raise ProcessAutomationInputRequired(f"{label} must be a stable lowercase identifier")
    return result


def _safe_text(value: Any, label: str, *, limit: int = 20_000) -> str:
    result = " ".join(str(value or "").split())
    if not result:
        raise ProcessAutomationInputRequired(f"{label} must be non-empty")
    if len(result) > limit:
        raise ProcessAutomationInputRequired(f"{label} exceeds {limit} characters")
    return result


def _seal_definition(definition: Mapping[str, Any]) -> dict[str, Any]:
    """Bind normalized JSON content while preserving G1.1's self-reference rule."""

    out = copy.deepcopy(dict(definition))
    placeholder = "sha256:" + ("0" * 64)
    out["digest"] = placeholder
    manifest = out["package_manifest"]
    manifest["definition_ref"] = {
        "definition_id": out["definition_id"],
        "version": out["version"],
        "digest": placeholder,
    }
    entry = next(
        item for item in manifest["members"]
        if item["member_id"] == manifest["entry_member_id"]
    )
    entry["identity"]["digest"] = placeholder
    digest = process_definition_content_digest(out)
    out["digest"] = digest
    manifest["definition_ref"]["digest"] = digest
    entry["identity"]["digest"] = digest
    contracts.validate_process_definition(out)
    return out


_SCHEMA_TYPES = {"string", "number", "integer", "boolean", "object", "array"}
_COMMON_SCHEMA_KEYS = {"type", "enum", "const"}
_TYPE_SCHEMA_KEYS = {
    "string": {"minLength", "maxLength"},
    "number": {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"},
    "integer": {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"},
    "boolean": set(),
    "object": {"properties", "required", "additionalProperties", "minProperties", "maxProperties"},
    "array": {"items", "minItems", "maxItems", "uniqueItems"},
}


def _json_type_ok(value: Any, declared: str) -> bool:
    if declared == "string":
        return isinstance(value, str)
    if declared == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        try:
            return math.isfinite(float(value))
        except (OverflowError, ValueError):
            return False
    if declared == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "object":
        return isinstance(value, Mapping)
    if declared == "array":
        return isinstance(value, list)
    return False


def _canonical_value_identity(value: Any, label: str) -> str:
    try:
        return _canonical_json(value)
    except (TypeError, ValueError) as exc:
        raise ProcessAutomationInputRequired(f"{label} must be JSON-serializable") from exc


def _bounded_nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProcessAutomationInputRequired(f"{label} must be a nonnegative integer")
    return value


def _finite_number(value: Any, label: str) -> int | float:
    if not _json_type_ok(value, "number"):
        raise ProcessAutomationInputRequired(f"{label} must be a finite number")
    return value


def _normalize_schema_node(
    value: Any,
    label: str,
    *,
    require_properties: bool = False,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProcessAutomationInputRequired(f"{label} must be a schema object")
    raw = copy.deepcopy(dict(value))
    declared = raw.get("type")
    if declared not in _SCHEMA_TYPES:
        raise ProcessAutomationInputRequired(f"{label}.type is unsupported")
    allowed = _COMMON_SCHEMA_KEYS | _TYPE_SCHEMA_KEYS[declared]
    unsupported = sorted(set(raw) - allowed)
    if unsupported:
        raise ProcessAutomationInputRequired(
            f"{label} has unsupported schema keyword(s): {', '.join(unsupported)}"
        )
    clean: dict[str, Any] = {"type": declared}
    if "enum" in raw:
        enum = raw["enum"]
        if not isinstance(enum, list) or not enum:
            raise ProcessAutomationInputRequired(f"{label}.enum must be a nonempty array")
        identities = [_canonical_value_identity(item, f"{label}.enum") for item in enum]
        if len(identities) != len(set(identities)):
            raise ProcessAutomationInputRequired(f"{label}.enum contains duplicates")
        if any(not _json_type_ok(item, declared) for item in enum):
            raise ProcessAutomationInputRequired(f"{label}.enum contains a value of the wrong type")
        clean["enum"] = enum
    if "const" in raw:
        if not _json_type_ok(raw["const"], declared):
            raise ProcessAutomationInputRequired(f"{label}.const has the wrong type")
        _canonical_value_identity(raw["const"], f"{label}.const")
        clean["const"] = raw["const"]
    if declared == "string":
        for field in ("minLength", "maxLength"):
            if field in raw:
                clean[field] = _bounded_nonnegative_integer(raw[field], f"{label}.{field}")
        if clean.get("maxLength") is not None and clean.get("minLength", 0) > clean["maxLength"]:
            raise ProcessAutomationInputRequired(f"{label}.minLength exceeds maxLength")
    elif declared in {"number", "integer"}:
        for field in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
            if field in raw:
                clean[field] = _finite_number(raw[field], f"{label}.{field}")
        if "multipleOf" in raw:
            multiple = _finite_number(raw["multipleOf"], f"{label}.multipleOf")
            if multiple <= 0:
                raise ProcessAutomationInputRequired(f"{label}.multipleOf must be greater than zero")
            clean["multipleOf"] = multiple
        lower = clean.get("minimum")
        upper = clean.get("maximum")
        if lower is not None and upper is not None and lower > upper:
            raise ProcessAutomationInputRequired(f"{label}.minimum exceeds maximum")
    elif declared == "object":
        properties = raw.get("properties")
        if not isinstance(properties, Mapping) or (require_properties and not properties):
            raise ProcessAutomationInputRequired(f"{label}.properties must be a nonempty object")
        clean_properties: dict[str, Any] = {}
        for raw_name, raw_property in (properties or {}).items():
            name = str(raw_name)
            if not _FIELD_RE.fullmatch(name):
                raise ProcessAutomationInputRequired(
                    f"{label} contains an invalid field declaration: {name!r}"
                )
            clean_properties[name] = _normalize_schema_node(
                raw_property, f"{label}.{name}",
            )
        required = raw.get("required", [])
        if (
            not isinstance(required, list)
            or any(not isinstance(item, str) or item not in clean_properties for item in required)
        ):
            raise ProcessAutomationInputRequired(f"{label}.required references an unknown field")
        if len(required) != len(set(required)):
            raise ProcessAutomationInputRequired(f"{label}.required contains duplicates")
        additional = raw.get("additionalProperties", False)
        if additional is not False:
            raise ProcessAutomationInputRequired(
                f"{label}.additionalProperties supports only false"
            )
        clean.update({
            "properties": clean_properties,
            "required": list(required),
            "additionalProperties": False,
        })
        for field in ("minProperties", "maxProperties"):
            if field in raw:
                clean[field] = _bounded_nonnegative_integer(raw[field], f"{label}.{field}")
        if clean.get("maxProperties") is not None and clean.get("minProperties", 0) > clean["maxProperties"]:
            raise ProcessAutomationInputRequired(f"{label}.minProperties exceeds maxProperties")
    elif declared == "array":
        if "items" not in raw:
            raise ProcessAutomationInputRequired(f"{label}.items is required")
        clean["items"] = _normalize_schema_node(raw["items"], f"{label}.items")
        for field in ("minItems", "maxItems"):
            if field in raw:
                clean[field] = _bounded_nonnegative_integer(raw[field], f"{label}.{field}")
        if clean.get("maxItems") is not None and clean.get("minItems", 0) > clean["maxItems"]:
            raise ProcessAutomationInputRequired(f"{label}.minItems exceeds maxItems")
        if "uniqueItems" in raw:
            if not isinstance(raw["uniqueItems"], bool):
                raise ProcessAutomationInputRequired(f"{label}.uniqueItems must be boolean")
            clean["uniqueItems"] = raw["uniqueItems"]
    return clean


def _normalize_json_schema(value: Any, label: str) -> dict[str, Any]:
    schema = _normalize_schema_node(value, label, require_properties=True)
    if schema["type"] != "object":
        raise ProcessAutomationInputRequired(f"{label}.type must be object")
    return schema


def _normalize_acceptance_criteria(
    value: Any,
    *,
    input_schema: Mapping[str, Any],
    output_schema: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ProcessAutomationInputRequired("acceptance_criteria must be a nonempty array")
    input_properties = input_schema["properties"]
    output_properties = output_schema["properties"]
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        label = f"acceptance_criteria[{index}]"
        if not isinstance(raw, Mapping):
            raise ProcessAutomationInputRequired(
                f"{label} is unassessable; criteria must use a supported structured kind"
            )
        kind = str(raw.get("kind") or "")
        common = {"criterion_id", "description", "kind"}
        kind_fields = {
            "field_equals": {"field", "expected"},
            "field_prefix": {"field", "expected"},
            "field_contains": {"field", "expected"},
            "email_grounding": {"classification_field", "summary_field"},
            "no_external_effects": set(),
        }
        if kind not in kind_fields:
            raise ProcessAutomationInputRequired(f"{label}.kind is unsupported or unassessable")
        expected_keys = common | kind_fields[kind]
        if set(raw) != expected_keys:
            raise ProcessAutomationInputRequired(
                f"{label} fields are invalid; missing={sorted(expected_keys - set(raw))}, "
                f"unsupported={sorted(set(raw) - expected_keys)}"
            )
        criterion_id = _safe_id(str(raw["criterion_id"]), f"{label}.criterion_id")
        if criterion_id in seen:
            raise ProcessAutomationInputRequired("acceptance_criteria contains duplicate IDs")
        seen.add(criterion_id)
        criterion = {
            "criterion_id": criterion_id,
            "description": _safe_text(raw["description"], f"{label}.description", limit=1_000),
            "kind": kind,
        }
        if kind in {"field_equals", "field_prefix", "field_contains"}:
            field = str(raw["field"])
            if field not in output_properties:
                raise ProcessAutomationInputRequired(f"{label}.field is not a declared output")
            criterion["field"] = field
            if kind == "field_equals":
                _validate_schema_value(
                    raw["expected"], output_properties[field], f"{label}.expected",
                )
                criterion["expected"] = copy.deepcopy(raw["expected"])
            else:
                if output_properties[field]["type"] != "string":
                    raise ProcessAutomationInputRequired(f"{label}.field must be a string output")
                criterion["expected"] = _safe_text(
                    raw["expected"], f"{label}.expected", limit=2_000,
                )
        elif kind == "email_grounding":
            classification_field = str(raw["classification_field"])
            summary_field = str(raw["summary_field"])
            if not {"subject", "body"}.issubset(input_properties):
                raise ProcessAutomationInputRequired(
                    f"{label} requires declared subject and body inputs"
                )
            if any(input_properties[name]["type"] != "string" for name in ("subject", "body")):
                raise ProcessAutomationInputRequired(f"{label} requires string subject and body inputs")
            for field in (classification_field, summary_field):
                if field not in output_properties or output_properties[field]["type"] != "string":
                    raise ProcessAutomationInputRequired(
                        f"{label} requires declared string classification and summary outputs"
                    )
            criterion.update({
                "classification_field": classification_field,
                "summary_field": summary_field,
            })
        normalized.append(criterion)
    return normalized


def validate_blueprint(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the G1.18 authoring result before it can become a definition."""

    if not isinstance(value, Mapping):
        raise ProcessAutomationInputRequired("process blueprint must be an object")
    allowed = {
        "schema_version", "definition_id", "version", "title", "purpose",
        "project_ref", "input_schema", "output_schema", "stages",
        "acceptance_criteria", "max_attempts", "labels",
    }
    if set(value) != allowed:
        missing = sorted(allowed - set(value))
        extra = sorted(set(value) - allowed)
        bits = []
        if missing:
            bits.append("missing " + ", ".join(missing))
        if extra:
            bits.append("unsupported " + ", ".join(extra))
        raise ProcessAutomationInputRequired("process blueprint fields are invalid: " + "; ".join(bits))
    if value.get("schema_version") != BLUEPRINT_SCHEMA_VERSION:
        raise ProcessAutomationInputRequired("unsupported process blueprint schema")
    definition_id = _safe_id(str(value["definition_id"]), "definition_id")
    if not definition_id.startswith("user/"):
        raise ProcessAutomationInputRequired("authored Process definition_id must begin with user/")
    version = _safe_id(str(value["version"]), "version")
    title = _safe_text(value["title"], "title", limit=200)
    purpose = _safe_text(value["purpose"], "purpose", limit=2_000)
    project_ref = _safe_id(str(value["project_ref"]), "project_ref")
    input_schema = _normalize_json_schema(value["input_schema"], "input_schema")
    output_schema = _normalize_json_schema(value["output_schema"], "output_schema")
    raw_stages = value["stages"]
    if not isinstance(raw_stages, list) or not raw_stages:
        raise ProcessAutomationInputRequired("stages must be a non-empty array")
    stages: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_operations: set[str] = set()
    seen_output_keys: set[str] = set()
    action_count = checkpoint_count = 0
    for index, raw_stage in enumerate(raw_stages):
        if not isinstance(raw_stage, Mapping):
            raise ProcessAutomationInputRequired(f"stages[{index}] must be an object")
        kind = str(raw_stage.get("kind") or "")
        node_id = _safe_id(str(raw_stage.get("node_id") or ""), f"stages[{index}].node_id")
        if node_id in seen or node_id in {"final-review", "accepted", "blocked"}:
            raise ProcessAutomationInputRequired(f"stages[{index}].node_id is duplicate or reserved")
        seen.add(node_id)
        if kind == "action":
            if set(raw_stage) != {"kind", "node_id", "label", "operation", "instruction", "output_key"}:
                raise ProcessAutomationInputRequired(
                    f"action stage {node_id!r} has missing or unsupported fields"
                )
            operation = _safe_id(str(raw_stage["operation"]), f"stages[{index}].operation")
            if _EXTERNAL_OPERATION_RE.search(operation):
                raise ProcessAutomationInputRequired(
                    f"action {operation!r} names an effect reserved beyond G1.18"
                )
            if operation in seen_operations:
                raise ProcessAutomationInputRequired(
                    f"action operation {operation!r} is duplicated"
                )
            seen_operations.add(operation)
            output_key = str(raw_stage["output_key"])
            if not _FIELD_RE.fullmatch(output_key) or output_key not in output_schema["properties"]:
                raise ProcessAutomationInputRequired(
                    f"action {node_id!r} output_key must name a declared output"
                )
            if output_key in seen_output_keys:
                raise ProcessAutomationInputRequired(
                    f"action output_key {output_key!r} is duplicated"
                )
            seen_output_keys.add(output_key)
            stages.append({
                "kind": "action",
                "node_id": node_id,
                "label": _safe_text(raw_stage["label"], f"stages[{index}].label", limit=240),
                "operation": operation,
                "instruction": _safe_text(raw_stage["instruction"], f"stages[{index}].instruction"),
                "output_key": output_key,
            })
            action_count += 1
        elif kind == "human_checkpoint":
            if set(raw_stage) != {"kind", "node_id", "label", "authority_request_type"}:
                raise ProcessAutomationInputRequired(
                    f"human checkpoint {node_id!r} has missing or unsupported fields"
                )
            stages.append({
                "kind": "human_checkpoint",
                "node_id": node_id,
                "label": _safe_text(raw_stage["label"], f"stages[{index}].label", limit=240),
                "authority_request_type": _safe_id(
                    str(raw_stage["authority_request_type"]),
                    f"stages[{index}].authority_request_type",
                ),
            })
            checkpoint_count += 1
        else:
            raise ProcessAutomationInputRequired(
                f"stages[{index}].kind must be action or human_checkpoint"
            )
    if action_count < 1 or checkpoint_count < 1:
        raise ProcessAutomationInputRequired(
            "an authored Process requires at least one action and one human checkpoint"
        )
    if stages[-1]["kind"] != "action":
        raise ProcessAutomationInputRequired("the final authored stage must produce the result")
    missing_outputs = sorted(set(output_schema["required"]) - seen_output_keys)
    if missing_outputs:
        raise ProcessAutomationInputRequired(
            "required outputs have no producing action: " + ", ".join(missing_outputs)
        )
    clean_criteria = _normalize_acceptance_criteria(
        value["acceptance_criteria"],
        input_schema=input_schema,
        output_schema=output_schema,
    )
    max_attempts = value["max_attempts"]
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not (1 <= max_attempts <= 8):
        raise ProcessAutomationInputRequired("max_attempts must be an integer from 1 through 8")
    labels = value["labels"]
    if not isinstance(labels, list):
        raise ProcessAutomationInputRequired("labels must be an array")
    clean_labels = [_safe_id(str(item), "label") for item in labels]
    if len(clean_labels) != len(set(clean_labels)):
        raise ProcessAutomationInputRequired("labels contains duplicates")
    return {
        "schema_version": BLUEPRINT_SCHEMA_VERSION,
        "definition_id": definition_id,
        "version": version,
        "title": title,
        "purpose": purpose,
        "project_ref": project_ref,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "stages": stages,
        "acceptance_criteria": clean_criteria,
        "max_attempts": max_attempts,
        "labels": clean_labels,
    }


def compile_blueprint(value: Mapping[str, Any]) -> dict[str, Any]:
    """Compile one reviewed blueprint to the issued G1.1 definition schema."""

    blueprint = validate_blueprint(value)
    nodes: list[dict[str, Any]] = []
    operation_contracts: dict[str, dict[str, str]] = {}
    stages = blueprint["stages"]
    for index, stage in enumerate(stages):
        next_id = stages[index + 1]["node_id"] if index + 1 < len(stages) else "final-review"
        if stage["kind"] == "action":
            nodes.append({
                "node_id": stage["node_id"],
                "kind": "action",
                "label": stage["label"],
                "operation": stage["operation"],
                "next_node_id": next_id,
                "authority_grant_ids": ["process-execution"],
                "artifact_access": [INPUT_SELECTOR, OUTPUT_SELECTOR],
                "evidence_requirement_ids": ["result_verified"],
                "external_effect": False,
            })
            operation_contracts[stage["operation"]] = {
                "node_id": stage["node_id"],
                "instruction": stage["instruction"],
                "output_key": stage["output_key"],
            }
        else:
            nodes.append({
                "node_id": stage["node_id"],
                "kind": "human_checkpoint",
                "label": stage["label"],
                "authority_request_type": stage["authority_request_type"],
                "on_approved_node_id": next_id,
                "on_denied_node_id": "blocked",
                "on_unavailable_node_id": "blocked",
            })
    nodes.extend([
        {
            "node_id": "final-review",
            "kind": "verification_boundary",
            "label": "Independently verify the exact Process result",
            "evidence_requirement_ids": ["result_verified"],
            "routes": {"ACCEPT": "accepted", "REVISE": stages[-1]["node_id"], "BLOCKED": "blocked"},
        },
        {"node_id": "accepted", "kind": "terminal_state", "label": "Accepted", "outcome": "accepted"},
        {"node_id": "blocked", "kind": "terminal_state", "label": "Blocked", "outcome": "blocked"},
    ])
    output_schema = copy.deepcopy(blueprint["output_schema"])
    output_schema["x-ora-process"] = {
        "schema_version": AUTOMATION_SCHEMA_VERSION,
        "operation_contracts": operation_contracts,
        "acceptance_criteria": blueprint["acceptance_criteria"],
        "max_correction_attempts": blueprint["max_attempts"],
        "max_attempts": (
            sum(stage["kind"] == "action" for stage in stages)
            + 1  # the baseline final verification is itself an attempt
            + blueprint["max_attempts"]
        ),
        "external_effects": False,
        "triggers": False,
    }
    definition_id = blueprint["definition_id"]
    version = blueprint["version"]
    placeholder = "sha256:" + ("0" * 64)
    definition = {
        "schema_version": contracts.CONTRACT_SCHEMA_VERSION,
        "object_family": "process_definition",
        "definition_id": definition_id,
        "version": version,
        "digest": placeholder,
        "title": blueprint["title"],
        "purpose": blueprint["purpose"],
        "status": "approved",
        "scope": {"kind": "project", "selector": blueprint["project_ref"]},
        "input_schema": blueprint["input_schema"],
        "output_schema": output_schema,
        "graph": {
            "schema_version": contracts.GRAPH_SCHEMA_VERSION,
            "graph_id": f"{definition_id}/{version}",
            "entry_node_id": stages[0]["node_id"],
            "nodes": nodes,
        },
        "package_manifest": {
            "schema_version": contracts.PACKAGE_SCHEMA_VERSION,
            "package_id": definition_id,
            "package_version": version,
            "definition_ref": {
                "definition_id": definition_id,
                "version": version,
                "digest": placeholder,
            },
            "entry_member_id": "definition",
            "members": [{
                "member_id": "definition",
                "role": "process_definition",
                "required": True,
                "media_type": "application/vnd.ora.process-definition+json",
                "locator": {"kind": "registry", "ref": f"processes/{definition_id}@{version}"},
                "identity": {
                    "kind": "content_digest",
                    "digest": placeholder,
                    "coverage": ["complete_content"],
                    "captured_at": "2026-01-01T00:00:00Z",
                    "fresh_until": "9999-12-31T23:59:59Z",
                },
            }],
        },
        "labels": sorted({"automated-process", *blueprint["labels"]}),
    }
    return _seal_definition(definition)


def email_processing_blueprint(project_ref: str = "ora") -> dict[str, Any]:
    """The bounded G1.18 worked proof: process an email, never send it."""

    return validate_blueprint({
        "schema_version": BLUEPRINT_SCHEMA_VERSION,
        "definition_id": "user/email-processing",
        "version": "1.0.0",
        "title": "Email Processing",
        "purpose": "Classify and summarize one inbound email, then prepare a draft only after human review.",
        "project_ref": project_ref,
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string"},
                "sender": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["message_id", "sender", "subject", "body"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "classification": {"type": "string"},
                "summary": {"type": "string"},
                "draft": {"type": "string"},
            },
            "required": ["classification", "summary", "draft"],
        },
        "stages": [
            {
                "kind": "action", "node_id": "classify", "label": "Classify the inbound email",
                "operation": "email.classify", "instruction": "Classify urgency and intent without changing or sending anything.",
                "output_key": "classification",
            },
            {
                "kind": "action", "node_id": "summarize", "label": "Summarize the email",
                "operation": "email.summarize", "instruction": "Produce a faithful concise summary of the exact inbound email.",
                "output_key": "summary",
            },
            {
                "kind": "human_checkpoint", "node_id": "draft-approval",
                "label": "Approve preparation of a reply draft; this does not authorize sending",
                "authority_request_type": "prepare_email_draft",
            },
            {
                "kind": "action", "node_id": "draft", "label": "Prepare an unsent reply draft",
                "operation": "email.draft", "instruction": "Prepare a reply draft. Do not send, publish, or contact anyone.",
                "output_key": "draft",
            },
        ],
        "acceptance_criteria": [
            {
                "criterion_id": "email-grounding",
                "description": "The classification and summary are derived from the exact inbound message.",
                "kind": "email_grounding",
                "classification_field": "classification",
                "summary_field": "summary",
            },
            {
                "criterion_id": "unsent-draft",
                "description": "The reply is explicitly an unsent draft.",
                "kind": "field_prefix",
                "field": "draft",
                "expected": "UNSENT DRAFT",
            },
            {
                "criterion_id": "no-external-effects",
                "description": "The definition and Run contain no external effect.",
                "kind": "no_external_effects",
            },
        ],
        "max_attempts": 3,
        "labels": ["email", "proof"],
    })


def _base_contracts(
    definition: Mapping[str, Any],
    *,
    principal_id: str,
    max_attempts: int,
    plan_id: str,
    objective: str,
    selectors: Sequence[str],
    granted_actions: Sequence[str],
) -> dict[str, Any]:
    node_ids = [str(node["node_id"]) for node in definition["graph"]["nodes"]]
    verification_nodes = [
        node for node in definition["graph"]["nodes"]
        if node["kind"] == "verification_boundary"
    ]
    now = _utc_now()
    plan_body = {
        "plan_id": plan_id,
        "version": "1.0.0",
        "objective": objective,
        "approved_by": principal_id,
        "approved_at": now,
        "approved_node_ids": node_ids,
        "constraints": [
            "No external effects are authorized.",
            "Every action executes through the exact persisted Process Run node.",
        ],
        "non_goals": ["scheduling", "outbound communication", "Persona selection"],
    }
    plan_body["digest"] = _digest_json(plan_body)
    return {
        "approved_plan": plan_body,
        "authority": {
            "principal_id": principal_id,
            "grants": [{
                "grant_id": "process-execution",
                "actions": sorted(set(granted_actions)),
                "resource_selectors": sorted(set(selectors)),
                "effect_types": ["local_reversible"],
                "conditions": CONDITIONS,
            }],
            "reserved_actions": [
                "activate", "delete", "message", "publish", "schedule", "send",
            ],
        },
        "artifact_scope": {
            "read_selectors": sorted(set(selectors)),
            "write_selectors": sorted(set(selectors)),
            "external_effect_selectors": [],
        },
        "bounded_judgment": [{
            "judgment_id": f"judgment-{node['node_id']}",
            "node_id": node["node_id"],
            "verified_circumstances": [
                "The exact result and independent evidence identities are persisted.",
            ],
            "question": "Does the exact result satisfy every declared acceptance criterion?",
            "permitted_conclusions": ["criteria_met", "execution_defect", "blocked"],
            "permitted_directives": sorted(node["routes"]),
            "permitted_actions": ["evaluate_evidence"],
            "authority_grant_ids": ["process-execution"],
            "artifact_selectors": [OUTPUT_SELECTOR],
            "required_evidence_ids": ["result_verified"],
            "evaluator_boundary": f"review-{node['node_id']}",
            "stop_conditions": ["stale_evidence", "unsupported_result"],
            "return_node_id": node["node_id"],
            "escalation_request_types": [],
        } for node in verification_nodes],
        "evidence": {
            "requirements": [{
                "evidence_id": "result_verified",
                "claim": "The exact Process result satisfies every declared acceptance criterion.",
                "method": "isolated_worker_verification",
                "producer_independence": "independent_step",
                "artifact_selectors": [OUTPUT_SELECTOR],
                "freshness_seconds": 3600,
                "required": True,
            }],
            "acceptance_rule": "all_required",
            "stale_evidence_policy": "recapture",
        },
        "correction_loop": {
            "max_attempts": max_attempts,
            "attempt": 0,
            "progress_evidence_required": True,
            "repeated_defect_limit": min(3, max_attempts),
            "allowed_directives": ["REVISE", "REPLAN", "REDEFINE", "ESCALATE", "BLOCKED"],
            "no_progress_directives": ["REPLAN", "REDEFINE", "ESCALATE", "BLOCKED"],
        },
        "continuation": {
            "checkpoint_id": "initial",
            "resume_node_id": definition["graph"]["entry_node_id"],
            "required_state_fields": ["current_node_id", "artifact_ids", "input_bindings"],
            "child_return_fields": [],
            "parent_run_id": None,
            "child_run_ids": [],
        },
        "recovery": {
            "replay_policy": "never_replay_effects",
            "checkpoint_ref": "checkpoint:initial",
            "external_effect_receipts_required": True,
            "revalidation_evidence_ids": ["result_verified"],
            "on_recovery_failure": "BLOCKED",
        },
        "stop_escalation": {
            "stop_conditions": ["authority_required", "attempt_ceiling", "worker_unavailable"],
            "blocked_conditions": ["identity_drift", "recovery_unsafe"],
            "authority_request_types": [],
            "authority_return_target": principal_id,
        },
    }


def _process_run(
    definition: Mapping[str, Any],
    *,
    run_id: str,
    entrypoint: str,
    principal_id: str,
    input_bindings: Mapping[str, Any],
    parent_run_id: str | None = None,
    constructed_definition_refs: Sequence[Mapping[str, Any]] = (),
    max_attempts: int = 3,
    selectors: Sequence[str] = (INPUT_SELECTOR, OUTPUT_SELECTOR),
    granted_actions: Sequence[str] = (
        "evaluate_evidence", "execute_process_step", "produce_artifact", "record_evidence",
    ),
) -> dict[str, Any]:
    now = _utc_now()
    contracts_value = _base_contracts(
        definition,
        principal_id=principal_id,
        max_attempts=max_attempts,
        plan_id=f"plan-{run_id}",
        objective=f"Execute exact Process Definition {_definition_ref(definition)}",
        selectors=selectors,
        granted_actions=granted_actions,
    )
    contracts_value["continuation"]["parent_run_id"] = parent_run_id
    run = {
        "schema_version": contracts.CONTRACT_SCHEMA_VERSION,
        "object_family": "process_run",
        "run_id": run_id,
        "definition_ref": _definition_ref(definition),
        "state": "created",
        "entrypoint": entrypoint,
        "current_node_id": definition["graph"]["entry_node_id"],
        "input_bindings": copy.deepcopy(dict(input_bindings)),
        "contracts": contracts_value,
        "relationships": {
            "parent_run_id": parent_run_id,
            "invoked_by_run_id": parent_run_id,
            "invoked_definition_refs": [],
            "constructed_definition_refs": [copy.deepcopy(dict(item)) for item in constructed_definition_refs],
            "return_to_run_id": parent_run_id,
        },
        "artifact_ids": [],
        "last_sequence": 0,
        "created_at": now,
        "updated_at": now,
        "labels": ["automated-process", "g1-18"],
    }
    contracts.validate_process_run(run)
    return run


def _construction_definition(target: Mapping[str, Any]) -> dict[str, Any]:
    target_ref = _definition_ref(target)
    blueprint = {
        "schema_version": BLUEPRINT_SCHEMA_VERSION,
        "definition_id": "ora/reusable-process-construction",
        "version": "1.0.0",
        "title": "Reusable Process Construction",
        "purpose": "Review, construct, register, and independently verify one exact reusable Process Definition.",
        "project_ref": "ora",
        "input_schema": {
            "type": "object",
            "properties": {"target_definition_ref": {"type": "object"}},
            "required": ["target_definition_ref"],
        },
        "output_schema": {
            "type": "object",
            "properties": {"registration_receipt": {"type": "object"}},
            "required": ["registration_receipt"],
        },
        "stages": [],
        "acceptance_criteria": ["The exact reviewed definition is registered without activation."],
        "max_attempts": 3,
        "labels": ["construction"],
    }
    placeholder = "sha256:" + ("0" * 64)
    definition = {
        "schema_version": contracts.CONTRACT_SCHEMA_VERSION,
        "object_family": "process_definition",
        "definition_id": blueprint["definition_id"],
        "version": blueprint["version"],
        "digest": placeholder,
        "title": blueprint["title"],
        "purpose": blueprint["purpose"],
        "status": "approved",
        "scope": {"kind": "universal", "selector": "all"},
        "input_schema": {
            "type": "object",
            "properties": {"target_definition_ref": {"const": target_ref}},
            "required": ["target_definition_ref"],
        },
        "output_schema": blueprint["output_schema"],
        "graph": {
            "schema_version": contracts.GRAPH_SCHEMA_VERSION,
            "graph_id": "ora/reusable-process-construction/1.0.0",
            "entry_node_id": "review-definition",
            "nodes": [
                {
                    "node_id": "review-definition", "kind": "human_checkpoint",
                    "label": "Approve this exact reusable Process Definition",
                    "authority_request_type": "process_definition_approval",
                    "on_approved_node_id": "construct-definition",
                    "on_denied_node_id": "blocked", "on_unavailable_node_id": "blocked",
                },
                {
                    "node_id": "construct-definition", "kind": "action",
                    "label": "Construct the exact approved reusable Process Definition",
                    "operation": "construct_reusable_process_definition",
                    "next_node_id": "register-definition",
                    "authority_grant_ids": ["process-execution"],
                    "artifact_access": [DEFINITION_SELECTOR],
                    "evidence_requirement_ids": ["result_verified"],
                    "external_effect": False,
                },
                {
                    "node_id": "register-definition", "kind": "action",
                    "label": "Register the exact version without activation",
                    "operation": "register_reusable_process_definition",
                    "next_node_id": "final-review",
                    "authority_grant_ids": ["process-execution"],
                    "artifact_access": [DEFINITION_SELECTOR, OUTPUT_SELECTOR],
                    "evidence_requirement_ids": ["result_verified"],
                    "external_effect": False,
                },
                {
                    "node_id": "final-review", "kind": "verification_boundary",
                    "label": "Independently verify construction and registration",
                    "evidence_requirement_ids": ["result_verified"],
                    "routes": {"ACCEPT": "accepted", "BLOCKED": "blocked"},
                },
                {"node_id": "accepted", "kind": "terminal_state", "label": "Accepted", "outcome": "accepted"},
                {"node_id": "blocked", "kind": "terminal_state", "label": "Blocked", "outcome": "blocked"},
            ],
        },
        "package_manifest": {
            "schema_version": contracts.PACKAGE_SCHEMA_VERSION,
            "package_id": blueprint["definition_id"],
            "package_version": blueprint["version"],
            "definition_ref": {
                "definition_id": blueprint["definition_id"],
                "version": blueprint["version"], "digest": placeholder,
            },
            "entry_member_id": "definition",
            "members": [{
                "member_id": "definition", "role": "process_definition", "required": True,
                "media_type": "application/vnd.ora.process-definition+json",
                "locator": {"kind": "registry", "ref": "processes/ora/reusable-process-construction@1.0.0"},
                "identity": {
                    "kind": "content_digest", "digest": placeholder,
                    "coverage": ["complete_content"],
                    "captured_at": "2026-01-01T00:00:00Z", "fresh_until": "9999-12-31T23:59:59Z",
                },
            }],
        },
        "labels": ["construction", "g1-18"],
    }
    return _seal_definition(definition)


def _latest_result_artifact(runtime: GovernedProcessRuntime, run_id: str) -> dict[str, Any] | None:
    run = runtime.load_run(run_id)
    for artifact_id in reversed(run["artifact_ids"]):
        artifact = runtime.load_artifact(run_id, artifact_id)
        if artifact["role"] == "result":
            return artifact
    return None


def _validate_schema_value(value: Any, schema: Mapping[str, Any], label: str) -> None:
    declared = str(schema.get("type") or "")
    if not _json_type_ok(value, declared):
        raise ProcessAutomationInputRequired(f"{label} has the wrong type")
    identity = _canonical_value_identity(value, label)
    if "enum" in schema and identity not in {
        _canonical_value_identity(item, f"{label}.enum") for item in schema["enum"]
    }:
        raise ProcessAutomationInputRequired(f"{label} violates enum")
    if "const" in schema and identity != _canonical_value_identity(schema["const"], f"{label}.const"):
        raise ProcessAutomationInputRequired(f"{label} violates const")
    if declared == "string":
        if len(value) < int(schema.get("minLength", 0)):
            raise ProcessAutomationInputRequired(f"{label} violates minLength")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise ProcessAutomationInputRequired(f"{label} violates maxLength")
    elif declared in {"number", "integer"}:
        if "minimum" in schema and value < schema["minimum"]:
            raise ProcessAutomationInputRequired(f"{label} violates minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ProcessAutomationInputRequired(f"{label} violates maximum")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise ProcessAutomationInputRequired(f"{label} violates exclusiveMinimum")
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            raise ProcessAutomationInputRequired(f"{label} violates exclusiveMaximum")
        if "multipleOf" in schema:
            try:
                remainder = Decimal(str(value)) % Decimal(str(schema["multipleOf"]))
            except (InvalidOperation, ValueError) as exc:
                raise ProcessAutomationInputRequired(f"{label} violates multipleOf") from exc
            if remainder != 0:
                raise ProcessAutomationInputRequired(f"{label} violates multipleOf")
    elif declared == "object":
        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        missing = sorted(set(required) - set(value))
        extra = (
            sorted(set(value) - set(properties))
            if schema.get("additionalProperties") is False else []
        )
        if missing or extra:
            raise ProcessAutomationInputRequired(
                f"{label} fields are invalid; missing={missing}, unsupported={extra}"
            )
        if len(value) < int(schema.get("minProperties", 0)):
            raise ProcessAutomationInputRequired(f"{label} violates minProperties")
        if "maxProperties" in schema and len(value) > int(schema["maxProperties"]):
            raise ProcessAutomationInputRequired(f"{label} violates maxProperties")
        for name, item in value.items():
            if name in properties:
                _validate_schema_value(item, properties[name], f"{label}.{name}")
    elif declared == "array":
        if len(value) < int(schema.get("minItems", 0)):
            raise ProcessAutomationInputRequired(f"{label} violates minItems")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ProcessAutomationInputRequired(f"{label} violates maxItems")
        if schema.get("uniqueItems"):
            identities = [_canonical_value_identity(item, f"{label}[]") for item in value]
            if len(identities) != len(set(identities)):
                raise ProcessAutomationInputRequired(f"{label} violates uniqueItems")
        for index, item in enumerate(value):
            _validate_schema_value(item, schema["items"], f"{label}[{index}]")


def _validate_instance(value: Mapping[str, Any], schema: Mapping[str, Any], label: str) -> dict[str, Any]:
    _validate_schema_value(value, schema, label)
    return copy.deepcopy(dict(value))


class IsolatedProcessWorker:
    """Run one no-tools action in a separate process with an exact request."""

    def __init__(
        self,
        *,
        command: Sequence[str] | None = None,
        timeout_seconds: int = 180,
        runner: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ):
        self.command = list(command) if command else [
            sys.executable, str(Path(__file__).with_name("process_automation_worker.py")),
        ]
        self.timeout_seconds = timeout_seconds
        self._runner = runner

    def invoke(
        self,
        request: Mapping[str, Any],
        *,
        run_id: str | None = None,
        node_id: str | None = None,
        attempt: int | None = None,
        on_started: Callable[[Mapping[str, Any]], None] | None = None,
        on_finished: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        payload = copy.deepcopy(dict(request))
        if payload.get("schema_version") != WORKER_SCHEMA_VERSION:
            raise ProcessAutomationWorkerError("worker request schema is invalid")
        request_digest = _digest_json(payload)
        if self._runner is not None:
            boundary = "injected_test_worker"
            execution_id = "worker-" + uuid.uuid4().hex
            started = {
                "execution_id": execution_id,
                "run_id": run_id,
                "node_id": node_id,
                "attempt": attempt,
                "pid": None,
                "boundary": boundary,
                "request_digest": request_digest,
            }
            if on_started is not None:
                on_started(started)
            try:
                raw = self._runner(copy.deepcopy(payload))
            except Exception:
                if on_finished is not None:
                    on_finished({
                        **started,
                        "outcome": "failed",
                        "returncode": None,
                        "control_action": None,
                    })
                raise
            if on_finished is not None:
                on_finished({
                    **started,
                    "outcome": "exited",
                    "returncode": 0,
                    "control_action": None,
                })
        else:
            env = {
                key: value for key, value in os.environ.items()
                if key in {
                    "HOME", "PATH", "LANG", "LC_ALL", "ORA_HOME", "ORA_VAULT",
                    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
                }
            }
            env["ORA_PROCESS_WORKER"] = "1"
            execution_id = "worker-" + uuid.uuid4().hex
            process: subprocess.Popen[str] | None = None
            started: dict[str, Any] | None = None
            start_notified = False
            outcome = "spawn_failed"
            control_action = None
            try:
                if run_id:
                    with _ACTIVE_WORKER_LOCK:
                        if str(run_id) in _ACTIVE_AUTOMATION_WORKERS:
                            raise ProcessAutomationConflict(
                                "the Run already has a live isolated worker"
                            )
                process = subprocess.Popen(
                    self.command,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.PIPE,
                    env=env,
                    cwd=str(Path(__file__).resolve().parents[1]),
                )
                boundary = "separate_no_tools_process"
                started = {
                    "execution_id": execution_id,
                    "run_id": run_id,
                    "node_id": node_id,
                    "attempt": attempt,
                    "pid": process.pid,
                    "boundary": boundary,
                    "request_digest": request_digest,
                }
                _bash_execute.MANAGED_PROCESSES.append(process)
                with _ACTIVE_WORKER_LOCK:
                    if run_id:
                        _ACTIVE_AUTOMATION_WORKERS[str(run_id)] = {
                            **copy.deepcopy(started),
                            "control_action": None,
                            "process": process,
                        }
                    # Keep the in-memory owner and persisted start atomic from
                    # Inspector readers in this process.
                    if on_started is not None:
                        on_started(started)
                    start_notified = True
                stdout, stderr = process.communicate(
                    _canonical_json(payload), timeout=self.timeout_seconds,
                )
                with _ACTIVE_WORKER_LOCK:
                    entry = _ACTIVE_AUTOMATION_WORKERS.get(str(run_id))
                    control_action = (
                        entry.get("control_action") if entry is not None else None
                    )
                outcome = "controlled" if control_action else "exited"
            except subprocess.TimeoutExpired as exc:
                outcome = "timeout"
                if process is not None and process.poll() is None:
                    _bash_execute.stop_process(process.pid)
                raise ProcessAutomationWorkerError(
                    f"isolated worker unavailable: {type(exc).__name__}: {exc}"
                ) from exc
            except OSError as exc:
                raise ProcessAutomationWorkerError(
                    f"isolated worker unavailable: {type(exc).__name__}: {exc}"
                ) from exc
            except Exception:
                if process is not None and process.poll() is None:
                    _bash_execute.stop_process(process.pid)
                raise
            finally:
                if process is not None:
                    try:
                        with _ACTIVE_WORKER_LOCK:
                            entry = _ACTIVE_AUTOMATION_WORKERS.get(str(run_id))
                            if entry is not None:
                                control_action = entry.get("control_action")
                            if start_notified and started is not None and on_finished is not None:
                                on_finished({
                                    **started,
                                    "outcome": outcome,
                                    "returncode": process.poll(),
                                    "control_action": control_action,
                                })
                    finally:
                        with _ACTIVE_WORKER_LOCK:
                            _ACTIVE_AUTOMATION_WORKERS.pop(str(run_id), None)
                        if process in _bash_execute.MANAGED_PROCESSES:
                            _bash_execute.MANAGED_PROCESSES.remove(process)
            if control_action:
                raise ProcessAutomationWorkerControlled(
                    str(control_action), execution_id,
                )
            if process is None:
                raise ProcessAutomationWorkerError("isolated worker failed to start")
            if process.returncode != 0:
                reason = stderr.strip() or f"exit status {process.returncode}"
                raise ProcessAutomationWorkerError(f"isolated worker failed: {reason[:1000]}")
            try:
                raw = json.loads(stdout)
            except json.JSONDecodeError as exc:
                raise ProcessAutomationWorkerError("isolated worker returned invalid JSON") from exc
        if not isinstance(raw, Mapping):
            raise ProcessAutomationWorkerError("isolated worker result must be an object")
        required = {"status", "request_digest", "output", "report"}
        if set(raw) != required or raw.get("request_digest") != request_digest:
            raise ProcessAutomationWorkerError("isolated worker result does not bind the exact request")
        if raw.get("status") not in {"PASS", "FAIL"}:
            raise ProcessAutomationWorkerError("isolated worker status is invalid")
        result = copy.deepcopy(dict(raw))
        result["boundary"] = boundary
        result["response_digest"] = _digest_json(raw)
        return result


class ProcessAutomationService:
    """Author, register, promote, and execute reusable G1.1 Processes."""

    def __init__(
        self,
        *,
        runtime: GovernedProcessRuntime | None = None,
        registry: ProcessDefinitionRegistry | None = None,
        registry_root: str | Path | None = None,
        management_interview: ManagementInterviewService | None = None,
        library: ProcessLibraryLifecycleService | None = None,
        worker: IsolatedProcessWorker | None = None,
    ):
        self.runtime = runtime or GovernedProcessRuntime()
        self.registry = registry or ProcessDefinitionRegistry(registry_root)
        self.interview = management_interview or ManagementInterviewService(runtime=self.runtime)
        self.library = library or ProcessLibraryLifecycleService(
            runtime=self.runtime, registry_root=self.registry.root,
        )
        self.worker = worker or IsolatedProcessWorker()

    # ---------------------------------------------------- Run observability
    def _invoke_run_worker(
        self,
        run_id: str,
        node_id: str,
        request: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Persist the exact lifetime of one isolated worker invocation."""

        run = self.runtime.load_run(run_id)
        attempt = int(run["contracts"]["correction_loop"]["attempt"])
        starts: dict[str, dict[str, Any]] = {}

        def on_started(meta: Mapping[str, Any]) -> None:
            details = {
                "run_id": run_id,
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "execution_id": str(meta["execution_id"]),
                "node_id": node_id,
                "attempt": attempt,
                "pid": meta.get("pid"),
                "worker_boundary": str(meta["boundary"]),
                "worker_request_digest": str(meta["request_digest"]),
            }
            record = self.runtime._record_runtime_event(
                run_id,
                "process_worker_started",
                details,
                node_id=node_id,
            )
            starts[str(meta["execution_id"])] = record

        def on_finished(meta: Mapping[str, Any]) -> None:
            start = starts.get(str(meta["execution_id"]))
            if start is None:
                raise ProcessAutomationIntegrityError(
                    "worker finished without its authenticated start record"
                )
            self.runtime._record_runtime_event(
                run_id,
                "process_worker_finished",
                {
                    "run_id": run_id,
                    "definition_ref": copy.deepcopy(run["definition_ref"]),
                    "execution_id": str(meta["execution_id"]),
                    "worker_start_record_id": start["record_id"],
                    "node_id": node_id,
                    "attempt": attempt,
                    "pid": meta.get("pid"),
                    "worker_boundary": str(meta["boundary"]),
                    "worker_request_digest": str(meta["request_digest"]),
                    "outcome": str(meta["outcome"]),
                    "returncode": meta.get("returncode"),
                    "control_action": meta.get("control_action"),
                },
                node_id=node_id,
            )

        return self.worker.invoke(
            request,
            run_id=run_id,
            node_id=node_id,
            attempt=attempt,
            on_started=on_started,
            on_finished=on_finished,
        )

    @staticmethod
    def _unmatched_worker_start(
        records: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any] | None:
        finished = {
            str((record.get("event") or {}).get("details", {}).get("execution_id") or "")
            for record in records
            if (record.get("event") or {}).get("event_type")
            == "process_worker_finished"
        }
        for record in reversed(records):
            event = record.get("event") or {}
            details = event.get("details") or {}
            if (
                event.get("event_type") == "process_worker_started"
                and str(details.get("execution_id") or "") not in finished
            ):
                attempt_completed = any(
                    later["sequence"] > record["sequence"]
                    and (later.get("event") or {}).get("event_type")
                    == "attempt_completed"
                    and (later.get("event") or {}).get("details", {}).get("segment_id")
                    == details.get("node_id")
                    for later in records
                )
                if not attempt_completed:
                    return record
        return None

    def _recover_orphaned_worker(self, run_id: str) -> bool:
        run = self.runtime.load_run(run_id)
        if run["state"] != "running" or active_automation_worker(run_id) is not None:
            return False
        orphan = self._unmatched_worker_start(self.runtime.load_records(run_id))
        if orphan is None:
            return False
        details = orphan["event"]["details"]
        if details.get("node_id") != run["current_node_id"]:
            raise ProcessAutomationIntegrityError(
                "orphaned worker start does not match the current Run node"
            )
        try:
            self.runtime.complete_automation_attempt(
                run_id,
                run["current_node_id"],
                defect_codes=["worker_orphaned_after_restart"],
                evidence_refs=[],
                artifact_digests=[],
            )
        except RunConflictError:
            pass
        current = self.runtime.load_run(run_id)
        if current["state"] == "running":
            self.runtime.pause_run(
                run_id,
                f"orphan-recovery-{str(details['execution_id'])[-20:]}",
                segment_id=current["current_node_id"],
                resume_node_id=current["current_node_id"],
                reason="Isolated worker ownership was lost across restart; replay is withheld",
                pause_kind="failure_recovery",
            )
        return True

    @staticmethod
    def _blocked_node_id(definition: Mapping[str, Any]) -> str:
        return next(
            node["node_id"]
            for node in definition["graph"]["nodes"]
            if node["kind"] == "terminal_state" and node["outcome"] == "blocked"
        )

    def run_controls(self, run_id: str) -> dict[str, Any]:
        return automation_run_controls(self.runtime, run_id)

    def _record_control_applied(
        self,
        run_id: str,
        *,
        request_record: Mapping[str, Any],
        action: str,
        execution_id: str | None,
    ) -> dict[str, Any]:
        existing = [
            record for record in self.runtime.load_records(run_id)
            if (record.get("event") or {}).get("event_type")
            == "process_run_control_applied"
            and (record.get("event") or {}).get("details", {}).get(
                "control_request_record_id"
            ) == request_record["record_id"]
        ]
        if existing:
            expected = existing[0]["event"]["details"]
            if (
                len(existing) != 1
                or expected.get("action") != action
                or expected.get("execution_id") != execution_id
                or expected.get("control_request_record_id")
                != request_record.get("record_id")
            ):
                raise ProcessAutomationIntegrityError(
                    "Run control application history conflicts"
                )
            return existing[0]
        run = self.runtime.load_run(run_id)
        request_details = (request_record.get("event") or {}).get("details") or {}
        if (
            request_details.get("run_id") != run_id
            or request_details.get("definition_ref") != run["definition_ref"]
            or request_details.get("action") != action
            or request_details.get("execution_id") != execution_id
            or request_details.get("run_state") != run["state"]
            or request_details.get("node_id") != run["current_node_id"]
            or request_details.get("decision_by")
            != run["contracts"]["authority"]["principal_id"]
        ):
            raise ProcessAutomationConflict(
                "Run control request is stale against the exact current boundary"
            )
        return self.runtime._record_runtime_event(
            run_id,
            "process_run_control_applied",
            {
                "run_id": run_id,
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "control_request_record_id": request_record["record_id"],
                "idempotency_key": request_record["event"]["details"]["idempotency_key"],
                "action": action,
                "execution_id": execution_id,
                "source_run_state": run["state"],
                "node_id": run["current_node_id"],
                "attempt": run["contracts"]["correction_loop"]["attempt"],
            },
            node_id=run["current_node_id"],
        )

    def _apply_active_worker_control(
        self,
        run_id: str,
        action: str,
        execution_id: str,
    ) -> None:
        records = self.runtime.load_records(run_id)
        request_record = next(
            (
                record for record in reversed(records)
                if (record.get("event") or {}).get("event_type")
                == "process_run_control_requested"
                and (record.get("event") or {}).get("details", {}).get("execution_id")
                == execution_id
                and (record.get("event") or {}).get("details", {}).get("action")
                == action
            ),
            None,
        )
        if request_record is None:
            raise ProcessAutomationIntegrityError(
                "worker control lacks its authenticated request record"
            )
        run = self.runtime.load_run(run_id)
        try:
            self.runtime.complete_automation_attempt(
                run_id,
                run["current_node_id"],
                defect_codes=[f"user_{action}"],
                evidence_refs=[],
                artifact_digests=[],
            )
        except RunConflictError:
            pass
        self._record_control_applied(
            run_id,
            request_record=request_record,
            action=action,
            execution_id=execution_id,
        )
        current = self.runtime.load_run(run_id)
        if action == "pause":
            self.runtime.pause_run(
                run_id,
                f"user-pause-{execution_id[-20:]}",
                segment_id=current["current_node_id"],
                resume_node_id=current["current_node_id"],
                reason="Principal paused the exact active isolated worker",
                pause_kind="user_control",
                control_request_record_id=request_record["record_id"],
            )
        else:
            definition = self.runtime.load_definition(run_id)
            self.runtime.block_by_process_run_control(
                run_id,
                control_request_record_id=request_record["record_id"],
                target_node_id=self._blocked_node_id(definition),
                reason="Principal stopped the exact active Process Run",
            )

    def control_run(
        self,
        run_id: str,
        *,
        action: str,
        control_state_digest: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if action not in {"pause", "resume", "stop"}:
            raise ProcessAutomationInputRequired("Run control action is invalid")
        if not _CONTROL_KEY_RE.fullmatch(str(idempotency_key or "")):
            raise ProcessAutomationInputRequired("Run control idempotency key is invalid")
        records = self.runtime.load_records(run_id)
        prior = [
            record for record in records
            if (record.get("event") or {}).get("event_type")
            == "process_run_control_requested"
            and (record.get("event") or {}).get("details", {}).get("idempotency_key")
            == idempotency_key
        ]
        if prior:
            if len(prior) != 1 or prior[0]["event"]["details"].get("action") != action:
                raise ProcessAutomationConflict("Run control retry identity conflicts")
            applied = [
                record for record in records
                if (record.get("event") or {}).get("event_type")
                == "process_run_control_applied"
                and (record.get("event") or {}).get("details", {}).get(
                    "control_request_record_id"
                ) == prior[0]["record_id"]
            ]
            if len(applied) > 1:
                raise ProcessAutomationIntegrityError(
                    "Run control retry has multiple application records"
                )
            if not applied:
                request = prior[0]
                details = request["event"]["details"]
                current = self.runtime.load_run(run_id)
                if (
                    details.get("run_id") != run_id
                    or details.get("definition_ref") != current["definition_ref"]
                    or details.get("decision_by")
                    != current["contracts"]["authority"]["principal_id"]
                ):
                    raise ProcessAutomationIntegrityError(
                        "Run control retry does not bind current authority"
                    )
                execution_id = details.get("execution_id")
                expected_state = details.get("run_state")
                if expected_state not in {"running", "pending"}:
                    raise ProcessAutomationIntegrityError(
                        "Run control retry lacks its exact persisted source state"
                    )
                if (
                    current["state"] != expected_state
                    or current["current_node_id"] != details.get("node_id")
                ):
                    raise ProcessAutomationConflict(
                        "unapplied Run control is stale against the current state"
                    )
                if execution_id:
                    finishes = [
                        record for record in records
                        if (record.get("event") or {}).get("event_type")
                        == "process_worker_finished"
                        and (record.get("event") or {}).get("details", {}).get(
                            "execution_id"
                        ) == execution_id
                    ]
                    if finishes and (
                        len(finishes) != 1
                        or finishes[0]["event"]["details"].get("control_action")
                        != action
                    ):
                        raise ProcessAutomationConflict(
                            "unapplied control did not stop its exact worker"
                        )
                self._record_control_applied(
                    run_id,
                    request_record=request,
                    action=action,
                    execution_id=execution_id,
                )
                if action == "pause" and current["state"] == "running":
                    self.runtime.pause_run(
                        run_id,
                        f"recovered-user-pause-{current['last_sequence']}",
                        segment_id=current["current_node_id"],
                        resume_node_id=current["current_node_id"],
                        reason="Recovered the Principal's persisted pause decision",
                        pause_kind="user_control",
                        control_request_record_id=request["record_id"],
                    )
                elif action == "stop" and current["state"] in {"running", "pending"}:
                    definition = self.runtime.load_definition(run_id)
                    self.runtime.block_by_process_run_control(
                        run_id,
                        control_request_record_id=request["record_id"],
                        target_node_id=self._blocked_node_id(definition),
                        reason="Recovered the Principal's persisted stop decision",
                    )
                elif action == "resume" and current["state"] == "pending":
                    self.runtime.resume_run(
                        run_id,
                        control_request_record_id=request["record_id"],
                    )
                    self.execute(run_id)
            else:
                request = prior[0]
                details = request["event"]["details"]
                applied_details = applied[0]["event"]["details"]
                if (
                    applied_details.get("action") != action
                    or applied_details.get("run_id") != run_id
                    or applied_details.get("definition_ref")
                    != details.get("definition_ref")
                    or applied_details.get("idempotency_key")
                    != details.get("idempotency_key")
                    or applied_details.get("source_run_state")
                    != details.get("run_state")
                    or applied_details.get("node_id") != details.get("node_id")
                ):
                    raise ProcessAutomationIntegrityError(
                        "Run control application does not authenticate its request"
                    )
                records = self.runtime.load_records(run_id)
                effect_type = "run_paused" if action == "pause" else "run_resumed"
                effect = next(
                    (
                        record for record in records
                        if (record.get("event") or {}).get("event_type") == effect_type
                        and (record.get("event") or {}).get("details", {}).get(
                            "control_request_record_id"
                        ) == request["record_id"]
                    ),
                    None,
                ) if action in {"pause", "resume"} else None
                current = self.runtime.load_run(run_id)
                if effect is None and current["state"] == details.get("run_state"):
                    if current["current_node_id"] != details.get("node_id"):
                        raise ProcessAutomationConflict(
                            "applied Run control is stale at a different node"
                        )
                    if action == "pause":
                        self.runtime.pause_run(
                            run_id,
                            f"recovered-user-pause-{current['last_sequence']}",
                            segment_id=current["current_node_id"],
                            resume_node_id=current["current_node_id"],
                            reason="Recovered the Principal's applied pause decision",
                            pause_kind="user_control",
                            control_request_record_id=request["record_id"],
                        )
                    elif action == "resume":
                        self.runtime.resume_run(
                            run_id,
                            control_request_record_id=request["record_id"],
                        )
                        self.execute(run_id)
                    elif action == "stop":
                        definition = self.runtime.load_definition(run_id)
                        self.runtime.block_by_process_run_control(
                            run_id,
                            control_request_record_id=request["record_id"],
                            target_node_id=self._blocked_node_id(definition),
                            reason="Recovered the Principal's applied stop decision",
                        )
                elif effect is None and action in {"pause", "resume"}:
                    raise ProcessAutomationConflict(
                        "applied Run control lacks its exact persisted effect"
                    )
            return {
                "status": "idempotent_retry",
                "request_record_id": prior[0]["record_id"],
                "run": self.run_state(run_id),
                "controls": self.run_controls(run_id),
            }

        controls = self.run_controls(run_id)
        if controls["control_state_digest"] != control_state_digest:
            raise ProcessAutomationConflict("Run control state is stale")
        if action not in controls["available_actions"]:
            raise ProcessAutomationConflict("Run control is unavailable in the current state")
        worker = controls.get("active_worker")
        execution_id = str((worker or {}).get("execution_id") or "") or None
        run = self.runtime.load_run(run_id)
        request_record = self.runtime._record_runtime_event(
            run_id,
            "process_run_control_requested",
            {
                "run_id": run_id,
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "idempotency_key": idempotency_key,
                "control_state_digest": control_state_digest,
                "action": action,
                "execution_id": execution_id,
                "run_state": run["state"],
                "node_id": run["current_node_id"],
                "attempt": run["contracts"]["correction_loop"]["attempt"],
                "decision_by": run["contracts"]["authority"]["principal_id"],
            },
            node_id=run["current_node_id"],
        )
        if action in {"pause", "stop"} and worker is not None:
            _request_active_worker_control(run_id, action)
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                current = self.runtime.load_run(run_id)
                if current["state"] != "running":
                    break
                time.sleep(0.01)
            current = self.runtime.load_run(run_id)
            if current["state"] == "running":
                raise ProcessAutomationConflict(
                    "worker stopped but the durable Run control is still reconciling"
                )
        elif action == "pause":
            self._record_control_applied(
                run_id,
                request_record=request_record,
                action=action,
                execution_id=None,
            )
            run = self.runtime.load_run(run_id)
            self.runtime.pause_run(
                run_id,
                f"user-pause-{run['last_sequence']}",
                segment_id=run["current_node_id"],
                resume_node_id=run["current_node_id"],
                reason="Principal paused the Process Run",
                pause_kind="user_control",
                control_request_record_id=request_record["record_id"],
            )
        elif action == "stop":
            self._record_control_applied(
                run_id,
                request_record=request_record,
                action=action,
                execution_id=None,
            )
            definition = self.runtime.load_definition(run_id)
            self.runtime.block_by_process_run_control(
                run_id,
                control_request_record_id=request_record["record_id"],
                target_node_id=self._blocked_node_id(definition),
                reason="Principal stopped the Process Run",
            )
        else:
            self._record_control_applied(
                run_id,
                request_record=request_record,
                action=action,
                execution_id=None,
            )
            self.runtime.resume_run(
                run_id,
                control_request_record_id=request_record["record_id"],
            )
            try:
                return {
                    "status": "applied",
                    "request_record_id": request_record["record_id"],
                    "run": self.execute(run_id),
                    "controls": self.run_controls(run_id),
                }
            except ProcessAutomationWorkerError:
                raise
        return {
            "status": "applied",
            "request_record_id": request_record["record_id"],
            "run": self.run_state(run_id),
            "controls": self.run_controls(run_id),
        }

    # ----------------------------------------------------------- authoring
    def _authoring_records(self, dialogue_ref: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        state = self.interview.get_state(dialogue_ref)
        if state is None:
            raise ProcessAutomationInputRequired("Dialogue has no management interview")
        if state["status"] != "ready_for_plan":
            raise ProcessAutomationInputRequired("management interview must be complete before authoring")
        records = [
            record for record in self.runtime.load_records(state["run_id"])
            if (record.get("event") or {}).get("event_type")
            in {AUTHORING_PROPOSED_EVENT, AUTHORING_REVISION_EVENT}
        ]
        return state, records

    def get_authoring(self, dialogue_ref: str) -> dict[str, Any]:
        interview, records = self._authoring_records(dialogue_ref)
        proposal_records = [
            record for record in records
            if record["event"]["event_type"] == AUTHORING_PROPOSED_EVENT
        ]
        latest = proposal_records[-1] if proposal_records else None
        proposal = None
        status = "ready_to_author"
        construction = None
        if latest is not None:
            details = latest["event"]["details"]
            required = {
                "schema_version", "proposal_id", "proposal_digest", "answers_digest",
                "definition", "definition_ref", "blueprint_digest", "idempotency_key",
                "execution_context", "worker_receipt",
            }
            if set(details) != required or details.get("schema_version") != AUTOMATION_SCHEMA_VERSION:
                raise ProcessAutomationIntegrityError("authoring proposal envelope is invalid")
            definition = contracts.validate_process_definition(details["definition"])
            if (
                details["definition_ref"] != _definition_ref(definition)
                or definition["digest"] != process_definition_content_digest(definition)
                or details["proposal_digest"] != _digest_json({
                    "answers_digest": details["answers_digest"],
                    "definition": definition,
                    "blueprint_digest": details["blueprint_digest"],
                    "execution_context": details["execution_context"],
                })
                or details["answers_digest"] != interview["answers_digest"]
            ):
                raise ProcessAutomationIntegrityError("authoring proposal identity is stale or forged")
            later_revisions = [
                record for record in records
                if int(record["sequence"]) > int(latest["sequence"])
                and record["event"]["event_type"] == AUTHORING_REVISION_EVENT
            ]
            status = "revision_requested" if later_revisions else "awaiting_definition_approval"
            proposal = copy.deepcopy(details)
            run_id = "process-construction-" + details["proposal_digest"].split(":", 1)[1][:32]
            try:
                run = self.runtime.load_run(run_id)
            except RunNotFoundError:
                run = None
            if run is not None:
                if (
                    run["input_bindings"].get("proposal_digest") != details["proposal_digest"]
                    or run["relationships"].get("parent_run_id") != interview["run_id"]
                ):
                    raise ProcessAutomationIntegrityError("construction Run does not bind the proposal")
                closure = self.library.get_run_lifecycle(run_id)
                construction = {
                    "run_id": run_id,
                    "run_state": run["state"],
                    "current_node_id": run["current_node_id"],
                    "lifecycle": closure,
                }
                if closure.get("closure", {}).get("disposition") == "promote":
                    status = "available"
                elif run["state"] == "completed":
                    status = "awaiting_promotion"
                else:
                    status = "constructing"
        return {
            "schema_version": AUTOMATION_SCHEMA_VERSION,
            "dialogue_ref": dialogue_ref,
            "management_run_id": interview["run_id"],
            "project_ref": interview["project_ref"],
            "answers_digest": interview["answers_digest"],
            "status": status,
            "proposal": proposal,
            "construction": construction,
            "persona_available": False,
            "trigger_created": False,
            "authority_effects": [],
        }

    def _default_author_blueprint(self, interview: Mapping[str, Any], *, project_ref: str) -> tuple[dict[str, Any], dict[str, Any]]:
        request = {
            "schema_version": WORKER_SCHEMA_VERSION,
            "kind": "author",
            "operation": "author.process_definition",
            "instruction": (
                "Produce one deterministic, non-effectful Process blueprint from the exact "
                "management answers. Include at least one human checkpoint. Do not include "
                "triggers, scheduling, outbound communication, Persona, file mutation, or activation."
            ),
            "inputs": {"answers": interview["answers"], "project_ref": project_ref},
            "prior_outputs": {},
            "expected_output_key": "blueprint",
            "acceptance_criteria": ["The output conforms exactly to ora.process-blueprint/1.0."],
            "execution_context": {"config_name": None, "style_prompt": ""},
        }
        receipt = self.worker.invoke(request)
        if receipt["status"] != "PASS" or not isinstance(receipt["output"], Mapping):
            raise ProcessAutomationWorkerError("authoring worker did not produce a valid blueprint")
        output = receipt["output"]
        blueprint = output.get("blueprint") if isinstance(output.get("blueprint"), Mapping) else output
        return validate_blueprint(blueprint), receipt

    def propose(
        self,
        dialogue_ref: str,
        *,
        idempotency_key: str,
        blueprint: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = _safe_id(idempotency_key, "idempotency_key")
        interview, records = self._authoring_records(dialogue_ref)
        existing = [
            record for record in records
            if record["event"]["event_type"] == AUTHORING_PROPOSED_EVENT
            and record["event"]["details"].get("idempotency_key") == key
        ]
        if existing:
            return self.get_authoring(dialogue_ref)
        project_ref = _safe_id(interview["project_ref"], "project_ref")
        if blueprint is None:
            exact_blueprint, worker_receipt = self._default_author_blueprint(
                interview, project_ref=project_ref,
            )
        else:
            exact_blueprint = validate_blueprint(blueprint)
            worker_receipt = {
                "boundary": "principal_supplied_blueprint",
                "request_digest": _digest_json({"answers_digest": interview["answers_digest"]}),
                "response_digest": _digest_json(exact_blueprint),
                "status": "PASS",
            }
        if exact_blueprint["project_ref"] != project_ref:
            raise ProcessAutomationConflict("blueprint project differs from the management interview")
        definition = compile_blueprint(exact_blueprint)
        execution_context = {
            "project_ref": project_ref,
            "model_profile_binding": "resolved_per_run_and_step",
            "style_profile_binding": "resolved_per_run",
        }
        proposal_body = {
            "answers_digest": interview["answers_digest"],
            "definition": definition,
            "blueprint_digest": _digest_json(exact_blueprint),
            "execution_context": execution_context,
        }
        proposal_digest = _digest_json(proposal_body)
        proposal_id = "proposal-" + proposal_digest.split(":", 1)[1][:32]
        prior_proposals = [
            record for record in records
            if record["event"]["event_type"] == AUTHORING_PROPOSED_EVENT
        ]
        if prior_proposals:
            prior = prior_proposals[-1]
            revision_after_prior = any(
                int(record["sequence"]) > int(prior["sequence"])
                and record["event"]["event_type"] == AUTHORING_REVISION_EVENT
                for record in records
            )
            if (
                revision_after_prior
                and prior["event"]["details"].get("proposal_digest")
                == proposal_digest
            ):
                raise ProcessAutomationConflict(
                    "a requested revision must produce a changed proposal identity"
                )
        self.runtime.record_automation_authoring_event(
            interview["run_id"],
            AUTHORING_PROPOSED_EVENT,
            {
                "schema_version": AUTOMATION_SCHEMA_VERSION,
                "proposal_id": proposal_id,
                "proposal_digest": proposal_digest,
                **proposal_body,
                "definition_ref": _definition_ref(definition),
                "idempotency_key": key,
                "worker_receipt": worker_receipt,
            },
            node_id=self.runtime.load_run(interview["run_id"])["current_node_id"],
        )
        return self.get_authoring(dialogue_ref)

    def request_revision(
        self, dialogue_ref: str, *, proposal_id: str, reason: str,
    ) -> dict[str, Any]:
        state = self.get_authoring(dialogue_ref)
        proposal = state.get("proposal")
        if not proposal or proposal["proposal_id"] != proposal_id:
            raise ProcessAutomationConflict("revision does not name the current proposal")
        if state["construction"] is not None:
            raise ProcessAutomationConflict("an approved construction cannot be revised in place")
        exact_reason = _safe_text(reason, "revision reason", limit=2_000)
        self.runtime.record_automation_authoring_event(
            state["management_run_id"],
            AUTHORING_REVISION_EVENT,
            {
                "schema_version": AUTOMATION_SCHEMA_VERSION,
                "proposal_id": proposal_id,
                "proposal_digest": proposal["proposal_digest"],
                "reason": exact_reason,
                "reason_digest": _digest_text(exact_reason),
            },
        )
        return self.get_authoring(dialogue_ref)

    def approve_and_register(
        self,
        dialogue_ref: str,
        *,
        proposal_id: str,
        proposal_digest: str,
        decision_by: str,
    ) -> dict[str, Any]:
        state = self.get_authoring(dialogue_ref)
        proposal = state.get("proposal")
        if not proposal or state["status"] not in {
            "awaiting_definition_approval", "constructing", "awaiting_promotion", "available",
        }:
            raise ProcessAutomationConflict("no current approvable Process proposal exists")
        if (
            proposal["proposal_id"] != proposal_id
            or proposal["proposal_digest"] != proposal_digest
        ):
            raise ProcessAutomationConflict("approval does not bind the current proposal identity")
        principal = _safe_id(decision_by, "decision_by")
        if principal != "principal:user":
            raise ProcessAutomationConflict("Process Definition approval requires principal:user")
        target = contracts.validate_process_definition(proposal["definition"])
        construction = _construction_definition(target)
        run_id = "process-construction-" + proposal_digest.split(":", 1)[1][:32]
        run = _process_run(
            construction,
            run_id=run_id,
            entrypoint="process_authoring",
            principal_id=principal,
            input_bindings={
                "dialogue_ref": dialogue_ref,
                "project_ref": state["project_ref"],
                "management_run_id": state["management_run_id"],
                "answers_digest": state["answers_digest"],
                "proposal_id": proposal_id,
                "proposal_digest": proposal_digest,
                "target_definition_ref": _definition_ref(target),
            },
            parent_run_id=state["management_run_id"],
            constructed_definition_refs=[_definition_ref(target)],
            max_attempts=3,
            selectors=[DEFINITION_SELECTOR, OUTPUT_SELECTOR],
            granted_actions=[
                "construct_definition", "evaluate_evidence", "produce_artifact",
                "record_evidence", "register_definition",
            ],
        )
        try:
            self.runtime.create_run(construction, run)
            self.runtime.mark_run_ready(run_id, reason="Exact Process proposal is ready for principal review")
            self.runtime.start_run(run_id, reason="Begin exact reusable Process construction")
        except RunConflictError:
            persisted = self.runtime.load_run(run_id)
            if persisted["input_bindings"] != run["input_bindings"]:
                raise ProcessAutomationIntegrityError("deterministic construction Run identity collided")
        current = self.runtime.load_run(run_id)
        if current["state"] == "running" and current["current_node_id"] == "review-definition":
            self.runtime.resolve_human_checkpoint(
                run_id, "approved", decision_by=principal,
                reason="Principal approved the exact proposal identity",
            )
        current = self.runtime.load_run(run_id)
        definition_artifact_id = "definition-" + target["digest"].split(":", 1)[1][:24]
        if current["state"] == "running" and current["current_node_id"] == "construct-definition":
            try:
                self.runtime.load_artifact(run_id, definition_artifact_id)
            except RunNotFoundError:
                self.runtime.record_inline_artifact(
                    run_id,
                    definition_artifact_id,
                    json.dumps(target, sort_keys=True, ensure_ascii=False),
                    role="process_definition",
                    node_id="construct-definition",
                    action="construct_definition",
                    selector=DEFINITION_SELECTOR,
                    satisfied_conditions=CONDITIONS,
                    media_type="application/vnd.ora.process-definition+json",
                )
            self.runtime.complete_action_node(
                run_id, "construct_reusable_process_definition",
                reason="Exact reviewed definition constructed",
                artifact_ids=[definition_artifact_id],
            )
        current = self.runtime.load_run(run_id)
        registration_artifact_id = "registration-" + target["digest"].split(":", 1)[1][:24]
        if current["state"] == "running" and current["current_node_id"] == "register-definition":
            result = self.runtime.register_process_definition(
                run_id,
                self.registry,
                target,
                definition_artifact_id=definition_artifact_id,
                registration_artifact_id=registration_artifact_id,
                selector=DEFINITION_SELECTOR,
                satisfied_conditions=CONDITIONS,
            )
            self.runtime.complete_action_node(
                run_id, "register_reusable_process_definition",
                reason="Exact Process Definition registered without activation",
                artifact_ids=[result["artifact"]["artifact_id"]],
            )
        current = self.runtime.load_run(run_id)
        if current["state"] == "running" and current["current_node_id"] == "final-review":
            receipt = self.runtime.load_artifact(run_id, registration_artifact_id)
            evidence_id = "registration-evidence-" + target["digest"].split(":", 1)[1][:24]
            try:
                evidence = self.runtime.load_artifact(run_id, evidence_id)
            except RunNotFoundError:
                evidence = self.runtime.record_inline_artifact(
                    run_id,
                    evidence_id,
                    _canonical_json({
                        "definition_ref": _definition_ref(target),
                        "registration_artifact_id": receipt["artifact_id"],
                        "registration_digest": receipt["identity"]["digest"],
                        "registry_root": str(self.registry.root.resolve()),
                        "verified": True,
                    }),
                    role="evidence",
                    node_id="final-review",
                    action="record_evidence",
                    selector=OUTPUT_SELECTOR,
                    source_artifact_ids=[registration_artifact_id],
                    satisfied_conditions=CONDITIONS,
                    media_type="application/json",
                )["artifact"]
            review = self.runtime.record_final_review(
                run_id,
                artifact_id=registration_artifact_id,
                evidence_id="result_verified",
                evidence_artifact_id=evidence["artifact_id"],
                outcome="PASS",
                reviewer_id="reviewer:process-registry",
                independent=True,
                satisfied_conditions=CONDITIONS,
            )
            self.runtime.apply_transition(
                run_id, "ACCEPT", target_node_id="accepted",
                reason="Exact construction and registration identities verified",
                evaluation_boundary="review-final-review",
                evidence_refs=review["evidence_refs"],
            )
        lifecycle = self.library.get_run_lifecycle(run_id)
        if lifecycle["status"] == "awaiting_disposition":
            lifecycle = self.library.close_run(
                run_id,
                disposition="promote",
                decision_by=principal,
                promoted_definition_ref=_definition_ref(target),
                capability_artifact_id=definition_artifact_id,
            )
        return self.get_authoring(dialogue_ref)

    # ----------------------------------------------------------- execution
    def _available_definition(
        self, definition_ref: Mapping[str, Any], project_ref: str,
    ) -> dict[str, Any]:
        if not isinstance(definition_ref, Mapping):
            raise ProcessAutomationInputRequired("definition_ref must be an exact object")
        try:
            definition = self.registry.resolve(
                str(definition_ref.get("definition_id") or ""),
                str(definition_ref.get("version") or ""),
                str(definition_ref.get("digest") or ""),
            )
        except ProcessDefinitionRegistryError as exc:
            raise ProcessAutomationInputRequired("exact Process Definition is unavailable") from exc
        entries = self.library.list_entries(project_ref=project_ref)["entries"]
        matches = [
            item for item in entries
            if item["definition_ref"] == _definition_ref(definition)
            and item["lifecycle_status"] == "available"
        ]
        if len(matches) != 1:
            raise ProcessAutomationInputRequired(
                "automated execution requires one exact promoted Process Library entry"
            )
        metadata = (definition.get("output_schema") or {}).get("x-ora-process")
        if not isinstance(metadata, Mapping) or metadata.get("schema_version") != AUTOMATION_SCHEMA_VERSION:
            raise ProcessAutomationInputRequired("Process Definition lacks the G1.18 execution contract")
        if metadata.get("external_effects") is not False or metadata.get("triggers") is not False:
            raise ProcessAutomationInputRequired("G1.18 executes only non-effectful unscheduled Processes")
        return definition

    def _execution_context(
        self,
        *,
        project_ref: str,
        process_profile: str | None,
        step_profiles: Mapping[str, Any] | None,
        one_run_profile: str | None,
        style_profile: str | None,
        definition: Mapping[str, Any],
    ) -> dict[str, Any]:
        step_profiles = copy.deepcopy(dict(step_profiles or {}))
        operations = {
            node["operation"] for node in definition["graph"]["nodes"]
            if node["kind"] == "action"
        }
        if sorted(set(step_profiles) - operations):
            raise ProcessAutomationInputRequired("step Model Profile names an unknown operation")
        resolutions: dict[str, Any] = {}
        for operation in sorted(operations):
            try:
                resolutions[operation] = resolve_effective_profile(
                    project_nexus=project_ref,
                    process_profile=process_profile,
                    step_profile=(str(step_profiles[operation]) if operation in step_profiles else None),
                    one_run_profile=one_run_profile,
                )
            except ModelProfileError as exc:
                raise ProcessAutomationInputRequired(
                    f"Model Profile resolution failed for {operation}: {exc}"
                ) from exc
        style_id = style_profile
        if style_id is None:
            try:
                record = project_meta.read_project_meta(project_ref) or {}
            except Exception:
                record = {}
            candidate = record.get("output_style")
            style_id = candidate if isinstance(candidate, str) and candidate.strip() else None
        style_prompt = ""
        if style_id:
            try:
                try:
                    from . import style_assembly, style_store
                except ImportError:
                    import style_assembly  # type: ignore
                    import style_store  # type: ignore
                style_prompt = style_assembly.compose(
                    style_id, register="written", gear=4,
                    custom_entries=style_store.load_custom_profiles() or None,
                )
            except Exception as exc:
                raise ProcessAutomationInputRequired(
                    f"Style Profile {style_id!r} cannot be resolved: {exc}"
                ) from exc
        body = {
            "project_ref": project_ref,
            "process_profile": process_profile,
            "step_profiles": step_profiles,
            "one_run_profile": one_run_profile,
            "model_resolutions": resolutions,
            "style_profile": style_id,
            "style_prompt": style_prompt,
            "style_prompt_digest": _digest_text(style_prompt),
        }
        return {**body, "binding_digest": _digest_json(body)}

    def begin_run(
        self,
        *,
        definition_ref: Mapping[str, Any],
        project_ref: str,
        inputs: Mapping[str, Any],
        idempotency_key: str,
        principal_id: str = "principal:user",
        process_profile: str | None = None,
        step_profiles: Mapping[str, Any] | None = None,
        one_run_profile: str | None = None,
        style_profile: str | None = None,
    ) -> dict[str, Any]:
        return self._begin_run(
            definition_ref=definition_ref,
            project_ref=project_ref,
            inputs=inputs,
            idempotency_key=idempotency_key,
            principal_id=principal_id,
            process_profile=process_profile,
            step_profiles=step_profiles,
            one_run_profile=one_run_profile,
            style_profile=style_profile,
            trigger_binding=None,
        )

    def begin_triggered_run(
        self,
        *,
        trigger_binding: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Begin the one invocation persisted by an authenticated firing claim.

        The public begin_run path cannot supply this binding.  ProcessTriggerService
        installs the authenticator on its shared service instance; constructing a
        generic automation service and calling this method directly fails closed.
        No caller-supplied invocation field is accepted at this boundary.
        """

        authenticator = getattr(self, "trigger_authenticator", None)
        if not callable(authenticator):
            raise ProcessAutomationIntegrityError(
                "standing Trigger execution requires the authenticated Trigger Manager"
            )
        try:
            authenticated = authenticator(trigger_binding)
        except Exception as exc:
            raise ProcessAutomationIntegrityError(
                "standing Trigger firing identity did not authenticate"
            ) from exc
        if not isinstance(authenticated, Mapping) or set(authenticated) != {
            "invocation_contract", "bound_run_id",
        }:
            raise ProcessAutomationIntegrityError(
                "Trigger authenticator did not return one complete invocation contract"
            )
        return self._begin_prepared_run(
            authenticated["invocation_contract"],
            expected_bound_run_id=authenticated["bound_run_id"],
        )

    def prepare_triggered_invocation(
        self,
        *,
        definition_ref: Mapping[str, Any],
        project_ref: str,
        inputs: Mapping[str, Any],
        idempotency_key: str,
        principal_id: str,
        trigger_binding: Mapping[str, Any],
        process_profile: str | None = None,
        step_profiles: Mapping[str, Any] | None = None,
        style_profile: str | None = None,
    ) -> dict[str, Any]:
        """Resolve the immutable invocation that a firing claim will persist.

        This method is read-only.  Execution still requires the ledger-backed
        authenticator installed by ProcessTriggerService.
        """

        definition, contract = self._prepare_run_contract(
            definition_ref=definition_ref,
            project_ref=project_ref,
            inputs=inputs,
            idempotency_key=idempotency_key,
            principal_id=principal_id,
            process_profile=process_profile,
            step_profiles=step_profiles,
            one_run_profile=None,
            style_profile=style_profile,
            trigger_binding=trigger_binding,
        )
        return contract

    def _begin_run(
        self,
        *,
        definition_ref: Mapping[str, Any],
        project_ref: str,
        inputs: Mapping[str, Any],
        idempotency_key: str,
        principal_id: str,
        process_profile: str | None,
        step_profiles: Mapping[str, Any] | None,
        one_run_profile: str | None,
        style_profile: str | None,
        trigger_binding: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        definition, contract = self._prepare_run_contract(
            definition_ref=definition_ref,
            project_ref=project_ref,
            inputs=inputs,
            idempotency_key=idempotency_key,
            principal_id=principal_id,
            process_profile=process_profile,
            step_profiles=step_profiles,
            one_run_profile=one_run_profile,
            style_profile=style_profile,
            trigger_binding=trigger_binding,
        )
        return self._create_prepared_run(
            definition, contract, expected_bound_run_id=None,
        )

    def _prepare_run_contract(
        self,
        *,
        definition_ref: Mapping[str, Any],
        project_ref: str,
        inputs: Mapping[str, Any],
        idempotency_key: str,
        principal_id: str,
        process_profile: str | None,
        step_profiles: Mapping[str, Any] | None,
        one_run_profile: str | None,
        style_profile: str | None,
        trigger_binding: Mapping[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        project = _safe_id(project_ref, "project_ref")
        key = _safe_id(idempotency_key, "idempotency_key")
        principal = _safe_id(principal_id, "principal_id")
        definition = self._available_definition(definition_ref, project)
        exact_inputs = _validate_instance(inputs, definition["input_schema"], "inputs")
        exact_step_profiles = copy.deepcopy(dict(step_profiles or {}))
        execution_context = self._execution_context(
            project_ref=project,
            process_profile=process_profile,
            step_profiles=exact_step_profiles,
            one_run_profile=one_run_profile,
            style_profile=style_profile,
            definition=definition,
        )
        identity = {
            "definition_ref": _definition_ref(definition),
            "project_ref": project,
            "inputs": exact_inputs,
            "idempotency_key": key,
            "principal_id": principal,
            "execution_context": execution_context,
        }
        if trigger_binding is not None:
            identity["trigger_binding"] = copy.deepcopy(dict(trigger_binding))
        invocation_digest = _digest_json(identity)
        run_id = "automated-run-" + invocation_digest.split(":", 1)[1][:32]
        contract = {
            "schema_version": TRIGGER_INVOCATION_SCHEMA_VERSION,
            **copy.deepcopy(identity),
            "process_profile": process_profile,
            "step_profiles": exact_step_profiles,
            "one_run_profile": one_run_profile,
            "style_profile": style_profile,
            "invocation_digest": invocation_digest,
            "run_id": run_id,
        }
        return definition, contract

    def _begin_prepared_run(
        self,
        contract: Mapping[str, Any],
        *,
        expected_bound_run_id: str | None,
    ) -> dict[str, Any]:
        required = {
            "schema_version", "definition_ref", "project_ref", "inputs",
            "idempotency_key", "principal_id", "execution_context",
            "process_profile", "step_profiles", "one_run_profile",
            "style_profile", "invocation_digest", "run_id",
        }
        optional = {"trigger_binding"}
        if (
            not isinstance(contract, Mapping)
            or set(contract) - required - optional
            or required - set(contract)
            or contract.get("schema_version") != TRIGGER_INVOCATION_SCHEMA_VERSION
        ):
            raise ProcessAutomationIntegrityError(
                "persisted Trigger invocation contract is malformed"
            )
        if contract.get("trigger_binding") is None and "trigger_binding" in contract:
            raise ProcessAutomationIntegrityError("Trigger binding cannot be null")
        definition, recomputed = self._prepare_run_contract(
            definition_ref=contract["definition_ref"],
            project_ref=str(contract["project_ref"]),
            inputs=contract["inputs"],
            idempotency_key=str(contract["idempotency_key"]),
            principal_id=str(contract["principal_id"]),
            process_profile=contract["process_profile"],
            step_profiles=contract["step_profiles"],
            one_run_profile=contract["one_run_profile"],
            style_profile=contract["style_profile"],
            trigger_binding=contract.get("trigger_binding"),
        )
        if dict(contract) != recomputed:
            raise ProcessAutomationIntegrityError(
                "persisted Trigger invocation no longer authenticates"
            )
        return self._create_prepared_run(
            definition, recomputed,
            expected_bound_run_id=expected_bound_run_id,
        )

    def _create_prepared_run(
        self,
        definition: Mapping[str, Any],
        recomputed: Mapping[str, Any],
        *,
        expected_bound_run_id: str | None,
    ) -> dict[str, Any]:
        run_id = recomputed["run_id"]
        if expected_bound_run_id is not None and expected_bound_run_id != run_id:
            raise ProcessAutomationIntegrityError(
                "firing claim is already bound to another Run identity"
            )
        metadata = definition["output_schema"]["x-ora-process"]
        input_bindings = {
            key: copy.deepcopy(recomputed[key])
            for key in (
                "definition_ref", "project_ref", "inputs", "idempotency_key",
                "principal_id", "execution_context", "invocation_digest",
            )
        }
        if "trigger_binding" in recomputed:
            input_bindings["trigger_binding"] = copy.deepcopy(
                recomputed["trigger_binding"]
            )
        run = _process_run(
            definition,
            run_id=run_id,
            entrypoint="automated_process",
            principal_id=str(recomputed["principal_id"]),
            input_bindings=input_bindings,
            max_attempts=int(metadata["max_attempts"]),
        )
        try:
            self.runtime.create_run(definition, run)
            self.runtime.mark_run_ready(run_id, reason="Exact promoted definition and inputs are bound")
            self.runtime.start_run(run_id, reason="Begin isolated automated Process execution")
        except RunConflictError:
            persisted = self.runtime.load_run(run_id)
            if persisted["input_bindings"] != run["input_bindings"]:
                raise ProcessAutomationIntegrityError("automated Run identity collided")
        return self.run_state(run_id)

    def _content_dir(self, run_id: str) -> Path:
        directory = self.runtime._run_dir(run_id) / "artifact-content"
        if directory.exists() and directory.is_symlink():
            raise ProcessAutomationIntegrityError("artifact content directory may not be a symlink")
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _record_content_artifact(
        self,
        run_id: str,
        artifact_id: str,
        value: Any,
        *,
        role: str,
        node_id: str,
        source_artifact_ids: Sequence[str],
    ) -> dict[str, Any]:
        text = json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
        path = self._content_dir(run_id) / f"{artifact_id}.json"
        if path.exists() and path.is_symlink():
            raise ProcessAutomationIntegrityError("artifact content path may not be a symlink")
        if path.exists():
            if path.read_text(encoding="utf-8") != text:
                raise ProcessAutomationIntegrityError("artifact content identity collided")
        else:
            atomic_write_text(path, text)
        now = _utc_now()
        run = self.runtime.load_run(run_id)
        artifact = {
            "schema_version": contracts.CONTRACT_SCHEMA_VERSION,
            "object_family": "artifact",
            "artifact_id": artifact_id,
            "role": role,
            "status": "candidate",
            "media_type": "application/json",
            "locator": {"kind": "file", "ref": str(path.resolve())},
            "identity": {
                "kind": "content_digest",
                "digest": _digest_text(text),
                "coverage": ["complete_content"],
                "captured_at": now,
                "fresh_until": (datetime.now(timezone.utc) + timedelta(days=3650)).isoformat().replace("+00:00", "Z"),
            },
            "lineage": {
                "run_id": run_id,
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "producing_node_id": node_id,
                "source_artifact_ids": list(source_artifact_ids),
                "event_record_id": f"event-{uuid.uuid4().hex}",
            },
            "created_at": now,
        }
        return self.runtime.record_artifact(
            artifact,
            action="produce_artifact",
            selectors=[OUTPUT_SELECTOR],
            satisfied_conditions=CONDITIONS,
        )["artifact"]

    @staticmethod
    def _read_content(artifact: Mapping[str, Any]) -> Any:
        locator = artifact.get("locator") or {}
        if locator.get("kind") != "file":
            raise ProcessAutomationIntegrityError("automation output is not a durable file Artifact")
        path = Path(str(locator.get("ref") or ""))
        if not path.is_file() or path.is_symlink():
            raise ProcessAutomationIntegrityError("automation output content is unavailable")
        text = path.read_text(encoding="utf-8")
        if _digest_text(text) != artifact["identity"]["digest"]:
            raise ProcessAutomationIntegrityError("automation output content has drifted")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProcessAutomationIntegrityError("automation output content is invalid JSON") from exc

    def _prior_outputs(self, run_id: str) -> tuple[dict[str, Any], list[str]]:
        run = self.runtime.load_run(run_id)
        outputs: dict[str, Any] = {}
        ids: list[str] = []
        definition = self.runtime.load_definition(run_id)
        metadata = definition["output_schema"]["x-ora-process"]["operation_contracts"]
        nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
        for artifact_id in run["artifact_ids"]:
            artifact = self.runtime.load_artifact(run_id, artifact_id)
            node = nodes.get(artifact["lineage"]["producing_node_id"])
            if artifact["role"] not in {"working", "result"} or not node or node["kind"] != "action":
                continue
            contract = metadata.get(node["operation"])
            if not contract:
                continue
            content = self._read_content(artifact)
            if not isinstance(content, Mapping) or contract["output_key"] not in content:
                raise ProcessAutomationIntegrityError("persisted step output violates its definition")
            outputs[contract["output_key"]] = copy.deepcopy(content[contract["output_key"]])
            ids.append(artifact_id)
        return outputs, ids

    def _reauthenticate_execution_context(self, run: Mapping[str, Any]) -> None:
        stored = run["input_bindings"].get("execution_context")
        if not isinstance(stored, Mapping):
            raise ProcessAutomationIntegrityError("Run lacks an execution-context binding")
        definition = self.runtime.load_definition(run["run_id"])
        current = self._execution_context(
            project_ref=stored["project_ref"],
            process_profile=stored.get("process_profile"),
            step_profiles=stored.get("step_profiles"),
            one_run_profile=stored.get("one_run_profile"),
            style_profile=stored.get("style_profile"),
            definition=definition,
        )
        if current != stored:
            raise ProcessAutomationIntegrityError(
                "Project, Model Profile, or Style binding changed after Run creation"
            )

    def execute(self, run_id: str) -> dict[str, Any]:
        """Advance until terminal or a persisted human/failure checkpoint."""

        while True:
            run = self.runtime.load_run(run_id)
            if run["state"] in {"completed", "blocked", "cancelled"}:
                return self.run_state(run_id)
            if run["state"] == "pending":
                # A checkpoint with an unresolved human decision remains pending;
                # callers must use resolve_checkpoint rather than replay execution.
                if self.run_state(run_id)["status"] == "awaiting_human_checkpoint":
                    return self.run_state(run_id)
                controls = self.run_controls(run_id)
                if controls.get("pause_kind") == "user_control":
                    raise ProcessAutomationConflict(
                        "user-paused Run requires the authenticated Resume control"
                    )
                self.runtime.resume_run(run_id)
                run = self.runtime.load_run(run_id)
            if run["state"] != "running":
                raise ProcessAutomationConflict(f"Run is not executable from state {run['state']!r}")
            if self._recover_orphaned_worker(run_id):
                return self.run_state(run_id)
            self._reauthenticate_execution_context(run)
            definition = self.runtime.load_definition(run_id)
            nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
            node = nodes[run["current_node_id"]]
            if node["kind"] == "human_checkpoint":
                checkpoint_id = f"human-{node['node_id']}-{run['last_sequence']}"
                self.runtime.pause_run(
                    run_id, checkpoint_id,
                    segment_id=node["node_id"], resume_node_id=node["node_id"],
                    reason="Explicit human checkpoint requires the Principal",
                    pause_kind="human_handoff",
                )
                return self.run_state(run_id)
            if node["kind"] == "action":
                try:
                    self._execute_action(run_id, definition, node)
                except _ProcessAutomationControlApplied:
                    return self.run_state(run_id)
                continue
            if node["kind"] == "verification_boundary":
                try:
                    self._verify_result(run_id, definition, node)
                except _ProcessAutomationControlApplied:
                    return self.run_state(run_id)
                continue
            raise ProcessAutomationIntegrityError(
                f"G1.18 executor does not support node kind {node['kind']!r}"
            )

    def _execute_action(
        self, run_id: str, definition: Mapping[str, Any], node: Mapping[str, Any],
    ) -> None:
        run = self.runtime.load_run(run_id)
        checkpoint_id = f"pre-{node['node_id']}-{run['contracts']['correction_loop']['attempt'] + 1}"
        self.runtime.create_checkpoint(
            run_id, checkpoint_id,
            segment_id=node["node_id"], resume_node_id=node["node_id"],
        )
        try:
            self.runtime.begin_automation_attempt(run_id, node["node_id"])
        except CorrectionDecisionRequired:
            blocked_node_id = next(
                graph_node["node_id"]
                for graph_node in definition["graph"]["nodes"]
                if graph_node["kind"] == "terminal_state"
                and graph_node["outcome"] == "blocked"
            )
            self.runtime.block_at_attempt_ceiling(
                run_id,
                segment_id=node["node_id"],
                target_node_id=blocked_node_id,
                reason=(
                    "Action attempt admission reached the immutable Run ceiling "
                    "before isolated execution"
                ),
            )
            return
        prior_outputs, source_ids = self._prior_outputs(run_id)
        metadata = definition["output_schema"]["x-ora-process"]
        contract = metadata["operation_contracts"][node["operation"]]
        execution_context = run["input_bindings"]["execution_context"]
        resolution = execution_context["model_resolutions"][node["operation"]]
        request = {
            "schema_version": WORKER_SCHEMA_VERSION,
            "kind": "execute",
            "operation": node["operation"],
            "instruction": contract["instruction"],
            "inputs": copy.deepcopy(run["input_bindings"]["inputs"]),
            "prior_outputs": prior_outputs,
            "expected_output_key": contract["output_key"],
            "acceptance_criteria": metadata["acceptance_criteria"],
            "execution_context": {
                "config_name": resolution["selected"]["runtime_name"],
                "model_profile_digest": resolution["selected"]["digest"],
                "style_profile": execution_context["style_profile"],
                "style_prompt": execution_context["style_prompt"],
            },
        }
        try:
            receipt = self._invoke_run_worker(run_id, node["node_id"], request)
            if receipt["status"] != "PASS":
                raise ProcessAutomationWorkerError(receipt["report"])
            output = receipt["output"]
            if not isinstance(output, Mapping) or set(output) != {contract["output_key"]}:
                raise ProcessAutomationWorkerError("worker output does not match the exact step contract")
            artifact_id = (
                f"step-{node['node_id']}-"
                f"{receipt['response_digest'].split(':', 1)[1][:20]}"
            )
            next_node = next(
                item for item in definition["graph"]["nodes"]
                if item["node_id"] == node["next_node_id"]
            )
            role = "result" if next_node["kind"] == "verification_boundary" else "working"
            artifact_value = (
                {**copy.deepcopy(prior_outputs), **copy.deepcopy(dict(output))}
                if role == "result" else output
            )
            if role == "result":
                _validate_instance(
                    artifact_value, definition["output_schema"], "result",
                )
            artifact = self._record_content_artifact(
                run_id, artifact_id, artifact_value,
                role=role, node_id=node["node_id"], source_artifact_ids=source_ids,
            )
            self.runtime.complete_automation_attempt(
                run_id, node["node_id"], defect_codes=[], evidence_refs=[],
                artifact_digests=[artifact["identity"]["digest"]],
            )
            execution_context_digest = execution_context["binding_digest"]
            self.runtime._record_runtime_event(
                run_id,
                "isolated_process_step_completed",
                {
                    "run_id": run_id,
                    "definition_ref": copy.deepcopy(run["definition_ref"]),
                    "node_id": node["node_id"],
                    "operation": node["operation"],
                    "attempt": self.runtime.load_run(run_id)["contracts"]["correction_loop"]["attempt"],
                    "worker_boundary": receipt["boundary"],
                    "worker_request_digest": receipt["request_digest"],
                    "worker_response_digest": receipt["response_digest"],
                    "execution_context_binding_digest": execution_context_digest,
                    "artifact_id": artifact["artifact_id"],
                    "artifact_identity_digest": artifact["identity"]["digest"],
                },
                node_id=node["node_id"],
                artifact_ids=[artifact["artifact_id"]],
            )
            self.runtime.complete_action_node(
                run_id, node["operation"],
                reason="Isolated worker produced the exact declared output",
                completion_details={
                    "worker_boundary": receipt["boundary"],
                    "worker_request_digest": receipt["request_digest"],
                    "worker_response_digest": receipt["response_digest"],
                    "model_profile_digest": request["execution_context"]["model_profile_digest"],
                    "execution_context_binding_digest": execution_context_digest,
                },
                artifact_ids=[artifact_id],
            )
        except ProcessAutomationWorkerControlled as exc:
            self._apply_active_worker_control(
                run_id, exc.action, exc.execution_id,
            )
            raise _ProcessAutomationControlApplied() from exc
        except Exception as exc:
            if isinstance(exc, (ProcessAutomationIntegrityError, GovernedRuntimeError)):
                defect = "runtime_integrity_failure"
            else:
                defect = "isolated_worker_failure"
            error_body = {
                "error_type": type(exc).__name__,
                "error": str(exc)[:1_000],
            }
            try:
                self.runtime.complete_automation_attempt(
                    run_id, node["node_id"], defect_codes=[defect],
                    evidence_refs=[], artifact_digests=[],
                )
            except RunConflictError:
                pass
            current = self.runtime.load_run(run_id)
            attempt = int(current["contracts"]["correction_loop"]["attempt"])
            trace_record_ids = [
                record["record_id"]
                for record in self.runtime.load_records(run_id)
                if (record.get("event") or {}).get("event_type")
                in {"process_worker_started", "process_worker_finished"}
                and record.get("node_id") == node["node_id"]
                and (record.get("event") or {}).get("details", {}).get("attempt")
                == attempt
            ]
            self.runtime._record_runtime_event(
                run_id,
                "isolated_process_action_failed",
                {
                    "run_id": run_id,
                    "definition_ref": copy.deepcopy(current["definition_ref"]),
                    "node_id": node["node_id"],
                    "operation": node["operation"],
                    "attempt": attempt,
                    "defect_code": defect,
                    "error_type": error_body["error_type"],
                    "error": error_body["error"],
                    "error_digest": _digest_json(error_body),
                    "worker_trace_record_ids": trace_record_ids,
                    "retryable": True,
                },
                node_id=node["node_id"],
            )
            if current["state"] == "running" and current["current_node_id"] == node["node_id"]:
                failure_checkpoint = f"failure-{node['node_id']}-{current['last_sequence']}"
                self.runtime.pause_run(
                    run_id, failure_checkpoint,
                    segment_id=node["node_id"], resume_node_id=node["node_id"],
                    reason=f"{defect}: {type(exc).__name__}",
                    pause_kind="failure_recovery",
                )
            raise ProcessAutomationWorkerError(
                f"Process action {node['node_id']} failed and is restart-safe: {exc}"
            ) from exc

    @staticmethod
    def _validated_criterion_assessments(
        receipt: Mapping[str, Any],
        declared: Sequence[Mapping[str, Any]],
        request: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        output = receipt.get("output")
        if not isinstance(output, Mapping) or set(output) != {"verification", "criteria"}:
            raise ProcessAutomationIntegrityError(
                "verification worker did not return the exact assessment envelope"
            )
        assessments = output.get("criteria")
        if not isinstance(assessments, list) or len(assessments) != len(declared):
            raise ProcessAutomationIntegrityError(
                "verification worker did not assess every declared criterion"
            )
        clean: list[dict[str, Any]] = []
        for expected, raw in zip(declared, assessments):
            if not isinstance(raw, Mapping) or set(raw) != {
                "criterion_id", "kind", "satisfied", "reason", "observation_digest",
            }:
                raise ProcessAutomationIntegrityError(
                    "verification worker returned a malformed criterion assessment"
                )
            assessment = copy.deepcopy(dict(raw))
            if (
                assessment["criterion_id"] != expected["criterion_id"]
                or assessment["kind"] != expected["kind"]
                or not isinstance(assessment["satisfied"], bool)
                or not isinstance(assessment["reason"], str)
                or not assessment["reason"].strip()
                or not re.fullmatch(
                    r"sha256:[0-9a-f]{64}", str(assessment["observation_digest"])
                )
            ):
                raise ProcessAutomationIntegrityError(
                    "verification assessment does not bind its declared criterion"
                )
            clean.append(assessment)
        expected_assessments = mechanically_assess_criteria(request)
        if clean != expected_assessments:
            raise ProcessAutomationIntegrityError(
                "verification worker assessments do not match mechanical reevaluation"
            )
        passed = bool(clean) and all(item["satisfied"] is True for item in clean)
        if (
            output.get("verification") is not passed
            or (receipt.get("status") == "PASS") is not passed
        ):
            raise ProcessAutomationIntegrityError(
                "verification status contradicts the criterion assessments"
            )
        return clean

    def _persist_verification_failure(
        self,
        run_id: str,
        definition: Mapping[str, Any],
        node: Mapping[str, Any],
        result: Mapping[str, Any],
        request: Mapping[str, Any],
        start_record: Mapping[str, Any],
        attempt: int,
        exc: Exception,
    ) -> None:
        try:
            self.runtime.complete_automation_attempt(
                run_id, node["node_id"],
                defect_codes=["verification_worker_failure"],
                evidence_refs=[], artifact_digests=[],
            )
        except RunConflictError:
            pass
        current = self.runtime.load_run(run_id)
        maximum = int(current["contracts"]["correction_loop"]["max_attempts"])
        exhausted = attempt >= maximum
        error_body = {
            "error_type": type(exc).__name__,
            "error": str(exc)[:1_000],
        }
        self.runtime._record_runtime_event(
            run_id,
            "isolated_process_verification_failed",
            {
                "run_id": run_id,
                "definition_ref": copy.deepcopy(current["definition_ref"]),
                "node_id": node["node_id"],
                "attempt": attempt,
                "max_attempts": maximum,
                "verification_start_record_id": start_record["record_id"],
                "worker_request_digest": _digest_json(request),
                "execution_context_binding_digest": (
                    current["input_bindings"]["execution_context"]["binding_digest"]
                ),
                "result_artifact_id": result["artifact_id"],
                "result_identity_digest": result["identity"]["digest"],
                "error_type": error_body["error_type"],
                "error": error_body["error"],
                "error_digest": _digest_json(error_body),
                "retryable": not exhausted,
                "exhausted": exhausted,
            },
            node_id=node["node_id"],
            artifact_ids=[result["artifact_id"]],
        )
        if exhausted:
            self.runtime.apply_transition(
                run_id, "BLOCKED", target_node_id=node["routes"]["BLOCKED"],
                reason="Isolated verification retry ceiling was exhausted",
                evaluation_boundary=f"review-{node['node_id']}",
                evidence_refs=[{
                    "evidence_id": "result_verified",
                    "artifact_id": result["artifact_id"],
                    "identity_digest": result["identity"]["digest"],
                    "outcome": "FAIL",
                }],
            )
        else:
            current = self.runtime.load_run(run_id)
            checkpoint_id = f"failure-{node['node_id']}-{current['last_sequence']}"
            self.runtime.pause_run(
                run_id, checkpoint_id,
                segment_id=node["node_id"], resume_node_id=node["node_id"],
                reason=f"verification_worker_failure: {type(exc).__name__}",
                pause_kind="failure_recovery",
            )

    def _verify_result(
        self, run_id: str, definition: Mapping[str, Any], node: Mapping[str, Any],
    ) -> None:
        result = _latest_result_artifact(self.runtime, run_id)
        if result is None:
            raise ProcessAutomationIntegrityError("verification boundary has no result Artifact")
        content = self._read_content(result)
        metadata = definition["output_schema"]["x-ora-process"]
        declared_criteria = copy.deepcopy(metadata["acceptance_criteria"])
        declared_criteria_digest = _digest_json(declared_criteria)
        records = self.runtime.load_records(run_id)
        external_effect_event_count = sum(
            (record.get("event") or {}).get("event_type") == "action_completed"
            and bool(((record.get("event") or {}).get("details") or {}).get("external_effect"))
            for record in records
        )
        run = self.runtime.load_run(run_id)
        execution_context_digest = (
            run["input_bindings"]["execution_context"]["binding_digest"]
        )
        request = {
            "schema_version": WORKER_SCHEMA_VERSION,
            "kind": "verify",
            "operation": "verify.process_result",
            "instruction": "Independently assess every declared criterion against the exact result.",
            "inputs": copy.deepcopy(run["input_bindings"]["inputs"]),
            "prior_outputs": content,
            "expected_output_key": "verification",
            "acceptance_criteria": declared_criteria,
            "execution_context": {
                "config_name": None,
                "style_prompt": "",
                "result_artifact_id": result["artifact_id"],
                "result_identity_digest": result["identity"]["digest"],
                "execution_context_binding_digest": execution_context_digest,
                "verification_attestations": {
                    "definition_external_effects": any(
                        graph_node.get("kind") == "action"
                        and graph_node.get("external_effect") is True
                        for graph_node in definition["graph"]["nodes"]
                    ),
                    "definition_triggers": metadata["triggers"],
                    "external_effect_event_count": external_effect_event_count,
                },
            },
        }
        next_attempt = int(run["contracts"]["correction_loop"]["attempt"]) + 1
        self.runtime.create_checkpoint(
            run_id, f"pre-{node['node_id']}-{next_attempt}",
            segment_id=node["node_id"], resume_node_id=node["node_id"],
        )
        try:
            attempt_record = self.runtime.begin_automation_attempt(
                run_id, node["node_id"],
            )
        except CorrectionDecisionRequired as exc:
            current = self.runtime.load_run(run_id)
            error_body = {
                "error_type": type(exc).__name__,
                "error": str(exc)[:1_000],
            }
            self.runtime._record_runtime_event(
                run_id,
                "isolated_process_verification_failed",
                {
                    "run_id": run_id,
                    "definition_ref": copy.deepcopy(current["definition_ref"]),
                    "node_id": node["node_id"],
                    "attempt": current["contracts"]["correction_loop"]["attempt"],
                    "max_attempts": current["contracts"]["correction_loop"]["max_attempts"],
                    "verification_start_record_id": None,
                    "worker_request_digest": _digest_json(request),
                    "execution_context_binding_digest": execution_context_digest,
                    "result_artifact_id": result["artifact_id"],
                    "result_identity_digest": result["identity"]["digest"],
                    "error_type": error_body["error_type"],
                    "error": error_body["error"],
                    "error_digest": _digest_json(error_body),
                    "failure_stage": "attempt_admission",
                    "retryable": False,
                    "exhausted": True,
                },
                node_id=node["node_id"],
                artifact_ids=[result["artifact_id"]],
            )
            self.runtime.block_at_attempt_ceiling(
                run_id,
                segment_id=node["node_id"],
                target_node_id=node["routes"]["BLOCKED"],
                reason=(
                    "Verification attempt admission reached the immutable Run "
                    "ceiling before worker execution"
                ),
            )
            return
        attempt = int(attempt_record["event"]["details"]["attempt"])
        start_record = self.runtime._record_runtime_event(
            run_id,
            "isolated_process_verification_started",
            {
                "run_id": run_id,
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "node_id": node["node_id"],
                "attempt": attempt,
                "worker_request_digest": _digest_json(request),
                "execution_context_binding_digest": execution_context_digest,
                "result_artifact_id": result["artifact_id"],
                "result_identity_digest": result["identity"]["digest"],
                "declared_criteria_digest": declared_criteria_digest,
                "declared_criterion_ids": [
                    criterion["criterion_id"] for criterion in declared_criteria
                ],
            },
            node_id=node["node_id"],
            artifact_ids=[result["artifact_id"]],
        )
        try:
            receipt = self._invoke_run_worker(run_id, node["node_id"], request)
            assessments = self._validated_criterion_assessments(
                receipt, declared_criteria, request,
            )
        except ProcessAutomationWorkerControlled as exc:
            self._apply_active_worker_control(
                run_id, exc.action, exc.execution_id,
            )
            raise _ProcessAutomationControlApplied() from exc
        except Exception as exc:
            self._persist_verification_failure(
                run_id, definition, node, result, request,
                start_record, attempt, exc,
            )
            raise ProcessAutomationWorkerError(
                f"Process verification failed and is restart-safe: {exc}"
            ) from exc
        outcome = "PASS" if receipt["status"] == "PASS" else "FAIL"
        assessments_digest = _digest_json(assessments)
        evidence_id = (
            f"evidence-{attempt}-"
            f"{receipt['response_digest'].split(':', 1)[1][:20]}"
        )
        evidence = self.runtime.record_inline_artifact(
            run_id, evidence_id,
            _canonical_json({
                "worker_boundary": receipt["boundary"],
                "request_digest": receipt["request_digest"],
                "response_digest": receipt["response_digest"],
                "outcome": outcome,
                "report": receipt["report"],
                "declared_criteria_digest": declared_criteria_digest,
                "criteria_assessments": assessments,
                "criteria_assessments_digest": assessments_digest,
                "result_artifact_id": result["artifact_id"],
                "result_identity_digest": result["identity"]["digest"],
            }),
            role="evidence", node_id=node["node_id"],
            action="record_evidence", selector=OUTPUT_SELECTOR,
            source_artifact_ids=[result["artifact_id"]],
            satisfied_conditions=CONDITIONS, media_type="application/json",
        )["artifact"]
        self.runtime._record_runtime_event(
            run_id,
            "isolated_process_verification_completed",
            {
                "run_id": run_id,
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "node_id": node["node_id"],
                "attempt": attempt,
                "verification_start_record_id": start_record["record_id"],
                "worker_boundary": receipt["boundary"],
                "worker_request_digest": receipt["request_digest"],
                "worker_response_digest": receipt["response_digest"],
                "execution_context_binding_digest": execution_context_digest,
                "result_artifact_id": result["artifact_id"],
                "result_identity_digest": result["identity"]["digest"],
                "evidence_artifact_id": evidence["artifact_id"],
                "evidence_identity_digest": evidence["identity"]["digest"],
                "declared_criteria_digest": declared_criteria_digest,
                "declared_criterion_ids": [
                    criterion["criterion_id"] for criterion in declared_criteria
                ],
                "criteria_assessments": assessments,
                "criteria_assessments_digest": assessments_digest,
                "outcome": outcome,
            },
            node_id=node["node_id"],
            artifact_ids=[result["artifact_id"], evidence["artifact_id"]],
        )
        self.runtime.complete_automation_attempt(
            run_id, node["node_id"],
            defect_codes=[] if outcome == "PASS" else ["acceptance_criteria_failed"],
            evidence_refs=[],
            artifact_digests=[
                result["identity"]["digest"], evidence["identity"]["digest"],
            ],
        )
        review = self.runtime.record_final_review(
            run_id,
            artifact_id=result["artifact_id"],
            evidence_id="result_verified",
            evidence_artifact_id=evidence["artifact_id"],
            outcome=outcome,
            reviewer_id="reviewer:isolated-process-worker",
            independent=True,
            satisfied_conditions=CONDITIONS,
        )
        current = self.runtime.load_run(run_id)
        exhausted = (
            int(current["contracts"]["correction_loop"]["attempt"])
            >= int(current["contracts"]["correction_loop"]["max_attempts"])
        )
        directive = "ACCEPT" if outcome == "PASS" else ("BLOCKED" if exhausted else "REVISE")
        target = node["routes"][directive]
        self.runtime.apply_transition(
            run_id, directive, target_node_id=target,
            reason=(
                "Every declared criterion passed for the exact result identity"
                if outcome == "PASS" else
                "One or more declared criteria failed for the exact result identity"
            ),
            evaluation_boundary=f"review-{node['node_id']}",
            evidence_refs=review["evidence_refs"],
        )

    def resolve_checkpoint(
        self,
        run_id: str,
        *,
        outcome: str,
        decision_by: str,
    ) -> dict[str, Any]:
        state = self.run_state(run_id)
        if state["status"] != "awaiting_human_checkpoint":
            raise ProcessAutomationConflict("Run is not awaiting a human checkpoint")
        exact_decision_by = _safe_id(decision_by, "decision_by")
        if outcome not in {"approved", "denied", "unavailable"}:
            raise ProcessAutomationInputRequired("checkpoint outcome is invalid")
        run = self.runtime.load_run(run_id)
        if exact_decision_by != run["contracts"]["authority"]["principal_id"]:
            raise ProcessAutomationConflict(
                "the exact Run principal must resolve this human checkpoint"
            )
        self.runtime.resume_run(run_id)
        self.runtime.resolve_human_checkpoint(
            run_id, outcome,
            decision_by=exact_decision_by,
            reason="Principal resolved the exact persisted Process checkpoint",
        )
        if outcome == "approved":
            return self.execute(run_id)
        return self.run_state(run_id)

    def run_state(self, run_id: str) -> dict[str, Any]:
        run = self.runtime.load_run(run_id)
        definition = self.runtime.load_definition(run_id)
        nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
        node = nodes[run["current_node_id"]]
        result = _latest_result_artifact(self.runtime, run_id)
        status = run["state"]
        controls = self.run_controls(run_id)
        if run["state"] == "pending" and controls.get("pause_kind") == "user_control":
            status = "paused_by_user"
        elif run["state"] == "pending" and node["kind"] == "human_checkpoint":
            status = "awaiting_human_checkpoint"
        elif run["state"] == "pending":
            status = "paused_after_failure"
        body = {
            "schema_version": AUTOMATION_SCHEMA_VERSION,
            "run_id": run_id,
            "definition_ref": copy.deepcopy(run["definition_ref"]),
            "project_ref": run["input_bindings"].get("project_ref"),
            "invocation_digest": run["input_bindings"].get("invocation_digest"),
            "run_state": run["state"],
            "status": status,
            "current_node": {
                "node_id": node["node_id"], "kind": node["kind"], "label": node["label"],
                "authority_request_type": node.get("authority_request_type"),
            },
            "attempt": run["contracts"]["correction_loop"]["attempt"],
            "max_attempts": run["contracts"]["correction_loop"]["max_attempts"],
            "checkpoint_id": run["contracts"]["continuation"]["checkpoint_id"],
            "pause_kind": controls.get("pause_kind"),
            "result": None,
            "standing_automation": bool(run["input_bindings"].get("trigger_binding")),
        }
        if run["input_bindings"].get("trigger_binding"):
            body["trigger_binding"] = copy.deepcopy(
                run["input_bindings"]["trigger_binding"]
            )
        if result is not None:
            body["result"] = {
                "artifact_id": result["artifact_id"],
                "identity_digest": result["identity"]["digest"],
                "content": self._read_content(result),
            }
        return {**body, "state_digest": _digest_json(body)}


__all__ = [
    "AUTOMATION_SCHEMA_VERSION",
    "BLUEPRINT_SCHEMA_VERSION",
    "IsolatedProcessWorker",
    "ProcessAutomationConflict",
    "ProcessAutomationError",
    "ProcessAutomationInputRequired",
    "ProcessAutomationIntegrityError",
    "ProcessAutomationService",
    "ProcessAutomationWorkerControlled",
    "ProcessAutomationWorkerError",
    "active_automation_worker",
    "automation_run_controls",
    "compile_blueprint",
    "email_processing_blueprint",
    "validate_blueprint",
]
