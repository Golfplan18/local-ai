"""Bounded capability discovery and controlled probes for Process Inference.

This module supplies mechanical Phase 1.5 primitives.  It does not select a
cognitive route or create a second execution engine: callers provide capability
sources and an already-governed Process Run.  The functions query declared
sources, classify actions from provider metadata, persist an immutable probe
contract, and bind attempts, evidence, receipts, and stop observations through
the existing ``GovernedProcessRuntime`` surface.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CAPABILITY_CATEGORIES = (
    "tool",
    "skill",
    "framework",
    "process_definition",
    "solution_pattern",
)
ACTION_EFFECT_CLASSES = frozenset({"inspection", "mutation"})
PROBE_OUTCOMES = frozenset({"confirmed", "disconfirmed", "ambiguous"})
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_READ_ONLY_SANDBOX_PROFILE = """(version 1)
(allow default)
(deny file-write*)
(deny network*)
"""


class CapabilityDiscoveryError(ValueError):
    """Raised when capability or probe metadata is incomplete or contradictory."""


@dataclass(frozen=True)
class ReadOnlyInspectionCommand:
    """An inspection executable constrained by the OS read-only sandbox."""

    argv: tuple[str, ...]
    cwd: str | None = None
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        if not self.argv or any(not isinstance(arg, str) or not arg for arg in self.argv):
            raise CapabilityDiscoveryError(
                "read-only inspection argv must be a nonempty tuple of strings"
            )
        executable = Path(self.argv[0])
        if not executable.is_absolute() or not executable.is_file():
            raise CapabilityDiscoveryError(
                "read-only inspection executable must be an existing absolute path"
            )
        if self.cwd is not None and not Path(self.cwd).is_dir():
            raise CapabilityDiscoveryError(
                "read-only inspection cwd must be an existing directory"
            )
        if (
            not isinstance(self.timeout_seconds, int)
            or isinstance(self.timeout_seconds, bool)
            or self.timeout_seconds < 1
        ):
            raise CapabilityDiscoveryError(
                "read-only inspection timeout_seconds must be an integer >= 1"
            )


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CapabilityDiscoveryError(f"{field} must be a nonempty string")
    return value.strip()


def _digest(value: Any, field: str) -> str:
    result = _text(value, field)
    if not _DIGEST_RE.fullmatch(result):
        raise CapabilityDiscoveryError(f"{field} must be an exact sha256 digest")
    return result


def _canonical_json_digest(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def validate_capability(
    capability: Mapping[str, Any],
    *,
    expected_category: str | None = None,
) -> dict[str, Any]:
    """Return a normalized capability record with explicit action effects."""

    if not isinstance(capability, Mapping):
        raise CapabilityDiscoveryError("capability must be an object")
    result = copy.deepcopy(dict(capability))
    result["capability_id"] = _text(result.get("capability_id"), "capability_id")
    result["category"] = _text(result.get("category"), "category")
    if result["category"] not in CAPABILITY_CATEGORIES:
        raise CapabilityDiscoveryError(
            f"category must be one of {', '.join(CAPABILITY_CATEGORIES)}"
        )
    if expected_category and result["category"] != expected_category:
        raise CapabilityDiscoveryError(
            f"capability category {result['category']!r} does not match queried "
            f"source {expected_category!r}"
        )
    result["version"] = _text(result.get("version"), "version")
    result["identity_digest"] = _digest(
        result.get("identity_digest"), "identity_digest"
    )
    result["locator"] = _text(result.get("locator"), "locator")

    raw_actions = result.get("actions")
    if not isinstance(raw_actions, list) or not raw_actions:
        raise CapabilityDiscoveryError("actions must be a nonempty list")
    actions: list[dict[str, str]] = []
    action_names: set[str] = set()
    for index, raw in enumerate(raw_actions):
        if not isinstance(raw, Mapping):
            raise CapabilityDiscoveryError(f"actions[{index}] must be an object")
        action = _text(raw.get("action"), f"actions[{index}].action")
        if action in action_names:
            raise CapabilityDiscoveryError(f"duplicate declared action: {action}")
        effect_class = _text(
            raw.get("effect_class"), f"actions[{index}].effect_class"
        )
        if effect_class not in ACTION_EFFECT_CLASSES:
            raise CapabilityDiscoveryError(
                f"actions[{index}].effect_class must be inspection or mutation"
            )
        effect_type = _text(raw.get("effect_type"), f"actions[{index}].effect_type")
        actions.append(
            {
                "action": action,
                "effect_class": effect_class,
                "effect_type": effect_type,
            }
        )
        action_names.add(action)
    result["actions"] = actions
    return result


def query_available_capabilities(
    objective: str,
    providers: Mapping[str, Callable[[str], Iterable[Mapping[str, Any]]]],
) -> dict[str, Any]:
    """Query all five PIF capability categories without inventing bindings.

    An absent or failed provider is recorded as unavailable.  A malformed
    record fails closed because accepting ambiguous action or identity metadata
    would make later authority checks meaningless.
    """

    objective = _text(objective, "objective")
    if not isinstance(providers, Mapping):
        raise CapabilityDiscoveryError("providers must be a category mapping")

    capabilities: list[dict[str, Any]] = []
    source_status: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    for category in CAPABILITY_CATEGORIES:
        provider = providers.get(category)
        if provider is None:
            source_status[category] = {
                "status": "unavailable",
                "count": 0,
                "reason": "no query provider bound",
            }
            continue
        if not callable(provider):
            raise CapabilityDiscoveryError(f"provider for {category} is not callable")
        try:
            raw_records = list(provider(objective))
        except Exception as exc:  # source failure is evidence, not a binding
            source_status[category] = {
                "status": "failed",
                "count": 0,
                "reason": f"{type(exc).__name__}: {exc}",
            }
            continue
        normalized: list[dict[str, Any]] = []
        for raw in raw_records:
            record = validate_capability(raw, expected_category=category)
            capability_id = record["capability_id"]
            if capability_id in seen_ids:
                raise CapabilityDiscoveryError(
                    f"capability_id must be unique across queried sources: {capability_id}"
                )
            seen_ids.add(capability_id)
            normalized.append(record)
        capabilities.extend(normalized)
        source_status[category] = {
            "status": "queried",
            "count": len(normalized),
            "reason": None,
        }

    capabilities.sort(key=lambda item: (item["category"], item["capability_id"]))
    record = {
        "objective": objective,
        "queried_categories": list(CAPABILITY_CATEGORIES),
        "capabilities": capabilities,
        "source_status": source_status,
    }
    record["discovery_digest"] = _canonical_json_digest(record)
    return record


def classify_capability_action(
    capability: Mapping[str, Any],
    action: str,
) -> dict[str, str]:
    """Classify an action only from the capability's declared metadata."""

    normalized = validate_capability(capability)
    action = _text(action, "action")
    for declared in normalized["actions"]:
        if declared["action"] == action:
            return copy.deepcopy(declared)
    raise CapabilityDiscoveryError(
        f"action {action!r} is not declared by capability "
        f"{normalized['capability_id']!r}"
    )


def record_capability_discovery(
    runtime: Any,
    run_id: str,
    discovery: Mapping[str, Any],
    *,
    node_id: str | None = None,
) -> dict[str, Any]:
    """Persist a capability query as a non-authoritative Run observation."""

    expected = _canonical_json_digest(
        {key: copy.deepcopy(value) for key, value in discovery.items() if key != "discovery_digest"}
    )
    if discovery.get("discovery_digest") != expected:
        raise CapabilityDiscoveryError("capability discovery digest does not match its content")
    return runtime.record_event(
        run_id,
        "capability_discovery_observed",
        copy.deepcopy(dict(discovery)),
        node_id=node_id,
    )


def _validate_probe_contract(
    contract: Mapping[str, Any],
    capability: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    if not isinstance(contract, Mapping):
        raise CapabilityDiscoveryError("probe contract must be an object")
    probe = copy.deepcopy(dict(contract))
    cap = validate_capability(capability)
    for field in (
        "probe_id",
        "assumption_id",
        "capability_id",
        "action",
        "selector",
        "node_id",
        "segment_id",
        "evidence_selector",
        "success_condition",
        "failure_condition",
        "ambiguous_route",
    ):
        probe[field] = _text(probe.get(field), field)
    if probe["capability_id"] != cap["capability_id"]:
        raise CapabilityDiscoveryError("probe capability_id does not match capability identity")
    declared = classify_capability_action(cap, probe["action"])
    if probe.get("effect_class") not in (None, declared["effect_class"]):
        raise CapabilityDiscoveryError(
            "probe effect_class contradicts the capability action declaration"
        )
    probe["effect_class"] = declared["effect_class"]
    if probe.get("effect_type") not in (None, declared["effect_type"]):
        raise CapabilityDiscoveryError(
            "probe effect_type contradicts the capability action declaration"
        )
    probe["effect_type"] = declared["effect_type"]

    maximum = probe.get("max_attempts")
    if (
        not isinstance(maximum, int)
        or isinstance(maximum, bool)
        or maximum < 1
    ):
        raise CapabilityDiscoveryError("max_attempts must be an integer >= 1")
    for field in ("authority_conditions", "stop_conditions"):
        value = probe.get(field, [])
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item for item in value
        ):
            raise CapabilityDiscoveryError(f"{field} must be a list of strings")
        if field == "stop_conditions" and not value:
            raise CapabilityDiscoveryError(
                "stop_conditions must declare at least one persisted stop boundary"
            )
        if len(set(value)) != len(value):
            raise CapabilityDiscoveryError(f"{field} contains duplicate identities")
        probe[field] = list(value)
    probe["evidence_requirement"] = _text(
        probe.get("evidence_requirement"), "evidence_requirement"
    )

    if probe["effect_class"] == "mutation":
        if probe.get("reversible") is not True:
            raise CapabilityDiscoveryError(
                "a controlled mutation probe must be explicitly reversible"
            )
        if maximum != 1:
            raise CapabilityDiscoveryError(
                "a mutation probe binds one immutable idempotency key and requires "
                "max_attempts = 1"
            )
        for field in ("idempotency_key", "recovery_route", "checkpoint_id"):
            probe[field] = _text(probe.get(field), field)
        probe["pre_state_digest"] = _digest(
            probe.get("pre_state_digest"), "pre_state_digest"
        )
        probe["recovery_identity_digest"] = _digest(
            probe.get("recovery_identity_digest"), "recovery_identity_digest"
        )
        expected_recovery_identity = _canonical_json_digest(
            {"recovery_route": probe["recovery_route"]}
        )
        if probe["recovery_identity_digest"] != expected_recovery_identity:
            raise CapabilityDiscoveryError(
                "recovery_identity_digest does not bind the declared recovery_route"
            )
    return probe, cap, declared


def persist_controlled_probe_contract(
    runtime: Any,
    run_id: str,
    contract: Mapping[str, Any],
    capability: Mapping[str, Any],
) -> dict[str, Any]:
    """Preflight and persist one immutable Controlled Probe Contract."""

    probe, cap, declared = _validate_probe_contract(contract, capability)
    mutation = declared["effect_class"] == "mutation"
    scope_kind = "external" if mutation else "read"
    grant_ids = runtime.authorize_action(
        run_id,
        declared["action"],
        [probe["selector"]],
        satisfied_conditions=probe["authority_conditions"],
        effect_type=declared["effect_type"],
        scope_kind=scope_kind,
    )
    evidence_grant_ids = runtime.authorize_action(
        run_id,
        "record_evidence",
        [probe["evidence_selector"]],
        satisfied_conditions=probe["authority_conditions"],
        effect_type="local_reversible",
        scope_kind="write",
    )
    run = runtime.load_run(run_id)
    plan = run["contracts"]["approved_plan"]
    mutation_safety = None
    if mutation:
        mutation_safety = {
            "reversible": True,
            "pre_state_digest": probe["pre_state_digest"],
            "idempotency_key": probe["idempotency_key"],
            "checkpoint_id": probe["checkpoint_id"],
            "required_receipt_fields": [
                "effect_id",
                "pre_state_digest",
                "post_state_digest",
                "idempotency_key",
            ],
            "recovery_route": probe["recovery_route"],
            "recovery_identity_digest": probe["recovery_identity_digest"],
        }
    persisted = {
        "contract_version": "1.0",
        "run_id": run_id,
        "definition_ref": copy.deepcopy(run["definition_ref"]),
        "approved_plan_ref": {
            "plan_id": plan["plan_id"],
            "version": plan["version"],
            "digest": plan["digest"],
        },
        "probe_id": probe["probe_id"],
        "assumption_id": probe["assumption_id"],
        "capability_identity": {
            "capability_id": cap["capability_id"],
            "category": cap["category"],
            "version": cap["version"],
            "identity_digest": cap["identity_digest"],
            "locator": cap["locator"],
        },
        "action_identity": copy.deepcopy(declared),
        "selector": probe["selector"],
        "node_id": probe["node_id"],
        "segment_id": probe["segment_id"],
        "authority_conditions": probe["authority_conditions"],
        "matched_grant_ids": grant_ids,
        "evidence_selector": probe["evidence_selector"],
        "evidence_grant_ids": evidence_grant_ids,
        "evidence_requirement": probe["evidence_requirement"],
        "success_condition": probe["success_condition"],
        "failure_condition": probe["failure_condition"],
        "ambiguous_route": probe["ambiguous_route"],
        "max_attempts": probe["max_attempts"],
        "stop_condition_ids": probe["stop_conditions"],
        "mutation_safety": mutation_safety,
    }
    return runtime.persist_controlled_probe_contract(run_id, persisted)


def _validate_probe_result(
    value: Mapping[str, Any],
    *,
    mutation: bool,
    idempotency_key: str | None,
    pre_state_digest: str | None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CapabilityDiscoveryError("probe executor must return an object")
    result = copy.deepcopy(dict(value))
    outcome = _text(result.get("outcome"), "probe result outcome")
    if outcome not in PROBE_OUTCOMES:
        raise CapabilityDiscoveryError(
            "probe result outcome must be confirmed, disconfirmed, or ambiguous"
        )
    result["outcome"] = outcome
    result["evidence"] = _text(result.get("evidence"), "probe result evidence")
    if mutation:
        receipt = result.get("receipt")
        if not isinstance(receipt, Mapping):
            raise CapabilityDiscoveryError(
                "a mutation probe result requires an external-effect receipt"
            )
        receipt = copy.deepcopy(dict(receipt))
        for field in ("effect_id", "pre_state_digest", "post_state_digest", "idempotency_key"):
            if field.endswith("_digest"):
                receipt[field] = _digest(receipt.get(field), f"receipt.{field}")
            else:
                receipt[field] = _text(receipt.get(field), f"receipt.{field}")
        if receipt["idempotency_key"] != idempotency_key:
            raise CapabilityDiscoveryError(
                "mutation receipt idempotency_key does not match the approved probe"
            )
        if receipt["pre_state_digest"] != pre_state_digest:
            raise CapabilityDiscoveryError(
                "mutation receipt pre_state_digest does not match the persisted pre-state identity"
            )
        result["receipt"] = receipt
    elif result.get("receipt") is not None:
        raise CapabilityDiscoveryError("an inspection probe must not claim a mutation receipt")
    return result


def _execute_read_only_inspection(
    boundary: ReadOnlyInspectionCommand,
    request: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(boundary, ReadOnlyInspectionCommand):
        raise CapabilityDiscoveryError(
            "inspection probes require a ReadOnlyInspectionCommand; arbitrary callables "
            "are not a mechanically read-only execution boundary"
        )
    sandbox = Path("/usr/bin/sandbox-exec")
    if not sandbox.is_file():
        raise CapabilityDiscoveryError(
            "read-only inspection sandbox is unavailable; inspection withheld"
        )
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    try:
        completed = subprocess.run(
            [str(sandbox), "-p", _READ_ONLY_SANDBOX_PROFILE, *boundary.argv],
            input=json.dumps(request, sort_keys=True, separators=(",", ":")),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=boundary.cwd,
            env=environment,
            timeout=boundary.timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CapabilityDiscoveryError(
            f"read-only inspection boundary failed: {type(exc).__name__}: {exc}"
        ) from exc
    if completed.returncode != 0:
        reason = completed.stderr.strip() or f"exit status {completed.returncode}"
        raise CapabilityDiscoveryError(
            f"read-only inspection boundary refused or failed the command: {reason}"
        )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CapabilityDiscoveryError(
            "read-only inspection command must emit exactly one JSON result"
        ) from exc
    if not isinstance(result, Mapping):
        raise CapabilityDiscoveryError(
            "read-only inspection command JSON result must be an object"
        )
    return result


def execute_controlled_probe(
    runtime: Any,
    run_id: str,
    probe_id: str,
    executor: Callable[[Mapping[str, Any]], Mapping[str, Any]] | ReadOnlyInspectionCommand,
) -> dict[str, Any]:
    """Execute only from a persisted contract and runtime-allocated attempt."""

    probe_id = _text(probe_id, "probe_id")
    started = runtime.begin_controlled_probe_attempt(run_id, probe_id)
    if started["status"] == "withheld":
        return started
    probe = started["contract"]
    declared = probe["action_identity"]
    capability_identity = probe["capability_identity"]
    mutation = declared["effect_class"] == "mutation"
    mutation_safety = probe.get("mutation_safety") or {}
    attempt = started["attempt"]
    request = {
        "run_id": run_id,
        "probe_id": probe["probe_id"],
        "assumption_id": probe["assumption_id"],
        "contract_digest": started["contract_digest"],
        "definition_ref": copy.deepcopy(probe["definition_ref"]),
        "approved_plan_ref": copy.deepcopy(probe["approved_plan_ref"]),
        "capability_id": capability_identity["capability_id"],
        "capability_identity_digest": capability_identity["identity_digest"],
        "action": declared["action"],
        "effect_class": declared["effect_class"],
        "effect_type": declared["effect_type"],
        "selector": probe["selector"],
        "attempt": attempt,
        "max_attempts": probe["max_attempts"],
        "pre_state_digest": mutation_safety.get("pre_state_digest"),
        "idempotency_key": mutation_safety.get("idempotency_key"),
    }
    executor_started = False
    try:
        if mutation:
            if not callable(executor) or isinstance(executor, ReadOnlyInspectionCommand):
                raise CapabilityDiscoveryError(
                    "mutation probe executor must be a callable"
                )
            runtime.create_checkpoint(
                run_id,
                mutation_safety["checkpoint_id"],
                segment_id=probe["segment_id"],
                resume_node_id=probe["node_id"],
            )
            executor_started = True
            raw_result = executor(copy.deepcopy(request))
        else:
            raw_result = _execute_read_only_inspection(executor, request)
    except Exception as exc:
        if mutation and executor_started:
            # The executor may have changed external state before failing.
            # Persist the possible effect without a receipt so recovery is
            # mechanically blocked rather than assuming that replay is safe.
            runtime.record_action(
                run_id,
                action=declared["action"],
                selectors=[probe["selector"]],
                satisfied_conditions=probe["authority_conditions"],
                effect_type=declared["effect_type"],
                external_effect=True,
                details={
                    "probe_id": probe["probe_id"],
                    "contract_digest": started["contract_digest"],
                    "capability_id": capability_identity["capability_id"],
                    "outcome": "effect_unknown_after_executor_failure",
                    "pre_state_digest": mutation_safety["pre_state_digest"],
                    "idempotency_key": mutation_safety["idempotency_key"],
                },
            )
        runtime.complete_controlled_probe_attempt(
            run_id,
            probe_id,
            status="failed",
            outcome=None,
            details={
                "error_type": type(exc).__name__,
                "error": str(exc),
                "recovery_identity_digest": mutation_safety.get(
                    "recovery_identity_digest"
                ),
            },
        )
        raise
    try:
        result = _validate_probe_result(
            raw_result,
            mutation=mutation,
            idempotency_key=mutation_safety.get("idempotency_key"),
            pre_state_digest=mutation_safety.get("pre_state_digest"),
        )
    except Exception as exc:
        if mutation:
            # A returned result without a valid exact receipt is still a
            # possible external effect.  Recording it receiptless makes the
            # existing recovery contract refuse replay/resume.
            runtime.record_action(
                run_id,
                action=declared["action"],
                selectors=[probe["selector"]],
                satisfied_conditions=probe["authority_conditions"],
                effect_type=declared["effect_type"],
                external_effect=True,
                details={
                    "probe_id": probe["probe_id"],
                    "contract_digest": started["contract_digest"],
                    "capability_id": capability_identity["capability_id"],
                    "outcome": "receipt_invalid_or_missing",
                    "pre_state_digest": mutation_safety["pre_state_digest"],
                    "idempotency_key": mutation_safety["idempotency_key"],
                },
            )
        runtime.complete_controlled_probe_attempt(
            run_id,
            probe_id,
            status="failed",
            outcome=None,
            details={
                "error_type": type(exc).__name__,
                "error": str(exc),
                "recovery_identity_digest": mutation_safety.get(
                    "recovery_identity_digest"
                ),
            },
        )
        raise

    artifact_ids: list[str] = []
    receipt_artifact_id: str | None = None
    if mutation:
        receipt_artifact_id = f"probe-{probe['probe_id']}-{attempt}-receipt"
        receipt_text = json.dumps(result["receipt"], sort_keys=True, separators=(",", ":"))
        receipt = runtime.record_inline_artifact(
            run_id,
            receipt_artifact_id,
            receipt_text,
            role="external_effect_receipt",
            node_id=probe["node_id"],
            action="record_evidence",
            selector=probe["evidence_selector"],
            satisfied_conditions=probe["authority_conditions"],
            media_type="application/json",
        )
        artifact_ids.append(receipt_artifact_id)
        runtime.record_action(
            run_id,
            action=declared["action"],
            selectors=[probe["selector"]],
            satisfied_conditions=probe["authority_conditions"],
            effect_type=declared["effect_type"],
            external_effect=True,
            receipt_artifact_id=receipt_artifact_id,
            details={
                "probe_id": probe["probe_id"],
                "assumption_id": probe["assumption_id"],
                "contract_digest": started["contract_digest"],
                "capability_id": capability_identity["capability_id"],
                "capability_identity_digest": capability_identity["identity_digest"],
                "receipt_identity_digest": receipt["artifact"]["identity"]["digest"],
                "pre_state_digest": mutation_safety["pre_state_digest"],
                "idempotency_key": mutation_safety["idempotency_key"],
            },
        )

    evidence_artifact_id = f"probe-{probe['probe_id']}-{attempt}-evidence"
    evidence = runtime.record_inline_artifact(
        run_id,
        evidence_artifact_id,
        result["evidence"],
        role="evidence",
        node_id=probe["node_id"],
        action="record_evidence",
        selector=probe["evidence_selector"],
        satisfied_conditions=probe["authority_conditions"],
    )
    artifact_ids.append(evidence_artifact_id)
    completed = runtime.complete_controlled_probe_attempt(
        run_id,
        probe_id,
        status="completed",
        outcome=result["outcome"],
        details={
            "assumption_id": probe["assumption_id"],
            "capability_id": capability_identity["capability_id"],
            "capability_identity_digest": capability_identity["identity_digest"],
            "action": declared["action"],
            "effect_class": declared["effect_class"],
            "effect_type": declared["effect_type"],
            "selector": probe["selector"],
            "evidence_artifact_id": evidence_artifact_id,
            "evidence_identity_digest": evidence["artifact"]["identity"]["digest"],
            "receipt_artifact_id": receipt_artifact_id,
            "success_condition": probe["success_condition"],
            "failure_condition": probe["failure_condition"],
            "ambiguous_route": probe["ambiguous_route"],
            "stop_conditions": copy.deepcopy(probe["stop_conditions"]),
            "recovery_identity_digest": mutation_safety.get(
                "recovery_identity_digest"
            ),
        },
        artifact_ids=artifact_ids,
    )
    return {
        "status": "executed",
        "outcome": result["outcome"],
        "attempt_record": started["record"],
        "contract_digest": started["contract_digest"],
        "completed_record": completed,
        "evidence_artifact_id": evidence_artifact_id,
        "receipt_artifact_id": receipt_artifact_id,
    }


def markdown_registry_entry(text: str, heading: str) -> str:
    """Extract one level-three Markdown registry entry by exact heading."""

    marker = f"### {heading}\n"
    start = text.find(marker)
    if start < 0:
        raise CapabilityDiscoveryError(f"registry entry not found: {heading}")
    end = text.find("\n### ", start + len(marker))
    return text[start : end if end >= 0 else len(text)]


def verify_registry_entry(
    text: str,
    heading: str,
    *,
    version: str,
    required_semantics: Sequence[str],
) -> str:
    """Verify a registry entry's current version and load-bearing semantics."""

    entry = markdown_registry_entry(text, heading)
    explicit_version = re.search(
        r"^- \*\*Version:\*\* ([^\s]+)\s*$", entry, re.MULTILINE
    )
    if explicit_version:
        version_matches = explicit_version.group(1) == version
    else:
        version_matches = any(
            token in entry for token in (f"(v{version},", f" v{version} ")
        )
    if not version_matches:
        raise CapabilityDiscoveryError(
            f"registry entry {heading!r} does not declare current version {version}"
        )
    missing = [phrase for phrase in required_semantics if phrase not in entry]
    if missing:
        raise CapabilityDiscoveryError(
            f"registry entry {heading!r} is missing semantics: {', '.join(missing)}"
        )
    return entry


def resolve_registered_vault_framework(
    registry_path: str | Path,
    heading: str,
    *,
    vault_root: str | Path,
    expected_version: str,
    required_source_tokens: Sequence[str] = (),
) -> dict[str, Any]:
    """Resolve and verify a registry entry that points directly at the vault."""

    registry_path = Path(registry_path).resolve()
    registry_text = registry_path.read_text(encoding="utf-8")
    entry = verify_registry_entry(
        registry_text,
        heading,
        version=expected_version,
        required_semantics=("(canonical)",),
    )
    match = re.search(r"^- \*\*File Location:\*\* (.+)$", entry, re.MULTILINE)
    if not match:
        raise CapabilityDiscoveryError(f"registry entry {heading!r} has no File Location")
    locations = [part.strip() for part in match.group(1).split(";")]
    vault_location = next(
        (
            item.split(" (canonical)", 1)[0]
            for item in locations
            if "Documents/vault/" in item and "(canonical)" in item
        ),
        None,
    )
    if vault_location is None:
        raise CapabilityDiscoveryError(
            f"registry entry {heading!r} does not declare a direct vault canonical"
        )
    suffix = vault_location.split("Documents/vault/", 1)[1]
    resolved_vault_root = Path(vault_root).resolve()
    source_path = (resolved_vault_root / suffix).resolve()
    try:
        source_path.relative_to(resolved_vault_root)
    except ValueError as exc:
        raise CapabilityDiscoveryError(
            f"registered canonical escapes the vault root: {source_path}"
        ) from exc
    if not source_path.is_file():
        raise CapabilityDiscoveryError(f"registered canonical does not exist: {source_path}")
    source_text = source_path.read_text(encoding="utf-8")
    if not re.search(rf"\bVersion[ _*]*{re.escape(expected_version)}\b", source_text):
        raise CapabilityDiscoveryError(
            f"registered canonical {source_path} is not version {expected_version}"
        )
    missing = [token for token in required_source_tokens if token not in source_text]
    if missing:
        raise CapabilityDiscoveryError(
            f"registered canonical is missing required semantics: {', '.join(missing)}"
        )
    return {
        "heading": heading,
        "version": expected_version,
        "registry_path": str(registry_path),
        "source_path": str(source_path),
        "source_digest": "sha256:"
        + hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
    }
